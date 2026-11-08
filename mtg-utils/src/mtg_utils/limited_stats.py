"""Untapped.gg MTG Arena limited card stats, turned into guide-ready numbers.

    limited-stats --set FRA [--premium-sealed PATH] [--premium-draft PATH]
                  [--pool-min-games 60] [--margin 10] [--tier-gap 5] [--clash 10]
                  [--min-games 30] [--json]
    limited-stats --set FRA --event SEALED [--premium-json PATH] [--json]

Untapped.gg publishes per-card limited stats for every Arena set, keyed by the
card's Arena **titleId** (not its grpid), split by deck archetype (a WUBRG
colour bitmask, plus ``ALL``) and by rank bucket. This module reads that
payload and computes the numbers a set guide quotes: each card's games-in-hand
win rate (GIH WR), not-drawn win rate (GNS WR) and the improvement when drawn
(IWD), card-weighted colour-pair win rates, the best commons per colour, bomb
candidates and hyped-but-losing rares.

With no ``--event`` it reads both Arena Sealed and Premier Draft and puts a
**pooled view** first (:func:`build_pooled`): every pair and card is measured
against its own format's average, then pooled across the formats by games, so
the two formats' different baselines don't mix. That is the view a 2HG
prerelease guide reads: 2HG is sealed, but Sealed alone is too thin to rank most
pairs or cards. ``--event`` keeps the single-format report.

Computation is pure (:func:`build_report` over a payload + a titleId index);
fetching is separate (:func:`fetch_card_stats`, :func:`fetch_card_index`) and
caches the free card-stats response and the two mtgajson files under
``<cache_dir>/untapped/`` for 24 hours. The premium payload needs a logged-in
browser session, so it is saved to a file and passed with ``--premium-json``.

The free tier truncates each stats row (trailing values dropped, and the
``not_available_*`` / side-in / side-out fields left out entirely) and omits
the diamond and mythic rank buckets, so every index read here defaults to 0,
and a missing not-drawn count is derived as ``games - available_games``.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import UTC, datetime
from pathlib import Path

import click
import requests

from mtg_utils._http import BROWSER_HEADERS, HttpFetcher, cache_root, is_fresh
from mtg_utils._sidecar import atomic_write_bytes
from mtg_utils.arena_card_db import arena_title

# The v2 query (2026-11: the v1 ``card_stats_limited_by_set`` answers 204 for every
# set). The payload shape is unchanged; the time interval is the page's own default.
API_URL = (
    "https://api.mtga.untapped.gg/api/v1/analytics/query/card_stats_limited_by_set_v2"
)
TIME_INTERVAL = "LATEST_EVENT"
CARDS_URL = "https://mtgajson.untapped.gg/v1/latest/cards.json"
LOC_URL = "https://mtgajson.untapped.gg/v1/latest/loc_en.json"

HEADERS = {"User-Agent": BROWSER_HEADERS["User-Agent"], "Accept": "application/json"}
_TIMEOUT = 60

# The stats row layout the premium tier serves in full. A payload's own
# ``metadata.fields`` wins when present (the free tier declares a shorter one).
DEFAULT_FIELDS: list[list[str]] = [
    [
        "games",
        "wins",
        "in_main_games",
        "in_main_games_dist",
        "in_side_games",
        "in_side_games_dist",
    ],
    [
        "available_games",
        "available_wins",
        "played_games",
        "played_wins",
        "not_available_games",
        "not_available_wins",
    ],
    [
        "in_opening_hands",
        "in_opening_hand_wins",
        "side_in_games",
        "side_in_wins",
        "side_out_games",
        "side_out_wins",
    ],
]

_COLORS = "WUBRG"
# Arena's rarity codes. arena_card_db keeps 2..5 only (it skips basics); a stats
# payload can carry a basic, so 1 is named here.
_RARITIES = {1: "basic", 2: "common", 3: "uncommon", 4: "rare", 5: "mythic"}
_CACHE_SECONDS = 24 * 3600
_RANK_ORDER = ("bronze", "silver", "gold", "platinum", "diamond", "mythic", "all")
_SMALL_SAMPLE_FLOOR = 10
_UNDERPERFORM_WR = 50.0
_EXAMPLE_EVENTS = "PREMIER_DRAFT, QUICK_DRAFT, SEALED"
# The formats the pooled view reads, Sealed first (the closer format for 2HG).
POOL_EVENTS = ("SEALED", "PREMIER_DRAFT")
# A card needs this many games drawn in each format before a gap between the
# formats is listed as a disagreement.
_CLASH_FLOOR = 20


# --- Pure helpers --------------------------------------------------------------


def decode_archetype(key: str) -> str:
    """An Untapped archetype key (WUBRG bitmask, W=1 … G=16) as ``"WU"``-style.

    ``"ALL"`` passes through; ``"0"`` (no colour bits) is ``"C"``.
    """
    if not key.isdigit():
        return key
    mask = int(key)
    colors = "".join(c for i, c in enumerate(_COLORS) if mask & (1 << i))
    return colors or "C"


def _pct(num: float, den: float) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def _field_positions(fields: list[list[str]] | None) -> dict[str, tuple[int, int]]:
    layout = fields or DEFAULT_FIELDS
    return {
        name: (section, idx)
        for section, names in enumerate(layout)
        for idx, name in enumerate(names)
    }


def _value(row: list, pos: tuple[int, int] | None) -> int:
    """One count from a (possibly truncated) stats row; anything missing is 0."""
    if pos is None:
        return 0
    section, idx = pos
    try:
        value = row[section][idx]
    except (LookupError, TypeError):
        return 0
    return (
        value if isinstance(value, int | float) and not isinstance(value, bool) else 0
    )


_COUNT_FIELDS = (
    "games",
    "wins",
    "available_games",
    "available_wins",
    "not_available_games",
    "not_available_wins",
    "in_opening_hands",
    "in_opening_hand_wins",
)


def _sum_buckets(
    buckets: dict[str, list], positions: dict[str, tuple[int, int]]
) -> dict[str, int]:
    """Sum the count fields across every rank bucket of one archetype."""
    totals = dict.fromkeys(_COUNT_FIELDS, 0)
    for row in buckets.values():
        if not isinstance(row, list):
            continue
        for name in _COUNT_FIELDS:
            totals[name] += _value(row, positions.get(name))
    if "not_available_games" not in positions:
        # Free tier: not-drawn = in the deck but never seen.
        totals["not_available_games"] = totals["games"] - totals["available_games"]
        totals["not_available_wins"] = totals["wins"] - totals["available_wins"]
    return totals


def build_card_index(
    cards: list[dict],
    loc: list[dict],
    set_code: str,
    title_ids: set[str],
) -> dict[str, dict]:
    """titleId -> ``{name, rarity, colors, set}`` from the two mtgajson files, for
    the *title_ids* a stats payload lists.

    Rarity / colours come from a printing in ``set_code`` when one exists,
    else the first printing seen (a reprint or special guest keeps its own
    ``set`` so the guide can mark it). A split card's ``A /// B`` name is
    written ``A // B``, as ``arena_card_db`` reads Arena's own titles.
    """
    names: dict[str, str] = {}
    for entry in loc:
        key = str(entry.get("id"))
        if key in title_ids and key not in names:
            names[key] = arena_title(None, str(entry.get("text", ""))) or ""
    want = set_code.upper()
    chosen: dict[str, dict] = {}
    for rec in cards:
        key = str(rec.get("titleId"))
        if key not in title_ids:
            continue
        in_set = str(rec.get("set", "")).upper() == want
        prior = chosen.get(key)
        if prior is None or (in_set and str(prior.get("set", "")).upper() != want):
            chosen[key] = rec
    index: dict[str, dict] = {}
    for key in set(chosen) | set(names):
        rec = chosen.get(key, {})
        color_ids = sorted(
            {c for c in rec.get("colors") or [] if isinstance(c, int) and 1 <= c <= 5}
        )
        index[key] = {
            "name": names.get(key) or f"titleId {key}",
            "rarity": _RARITIES.get(rec.get("rarity", 0), "unknown"),
            "colors": "".join(_COLORS[c - 1] for c in color_ids),
            "set": rec.get("set"),
        }
    return index


def card_rows(payload: dict, index: dict[str, dict]) -> list[dict]:
    """One row per card over the ``ALL`` archetype, summed across rank buckets."""
    positions = _field_positions(payload.get("metadata", {}).get("fields"))
    rows = []
    for title_id, archetypes in (payload.get("data") or {}).items():
        buckets = archetypes.get("ALL") if isinstance(archetypes, dict) else None
        if not buckets:
            continue
        t = _sum_buckets(buckets, positions)
        meta = index.get(str(title_id), {})
        gih_wr = _pct(t["available_wins"], t["available_games"])
        gns_wr = _pct(t["not_available_wins"], t["not_available_games"])
        rows.append(
            {
                "title_id": str(title_id),
                "name": meta.get("name") or f"titleId {title_id}",
                "rarity": meta.get("rarity", "unknown"),
                "colors": meta.get("colors", ""),
                "set": meta.get("set"),
                "gp": t["games"],
                "gp_wr": _pct(t["wins"], t["games"]),
                "gih": t["available_games"],
                "gih_wr": gih_wr,
                "gns": t["not_available_games"],
                "gns_wr": gns_wr,
                "iwd": (
                    round(gih_wr - gns_wr, 1)
                    if gih_wr is not None and gns_wr is not None
                    else None
                ),
                "oh": t["in_opening_hands"],
                "oh_wr": _pct(t["in_opening_hand_wins"], t["in_opening_hands"]),
            }
        )
    return rows


def _meta_games(payload: dict) -> dict[str, dict[str, int]]:
    games = payload.get("metadata", {}).get("games") or {}
    return games if isinstance(games, dict) else {}


def color_pair_rates(payload: dict) -> dict[str, list[dict]]:
    """Card-weighted win rate per archetype: Σwins / Σgames over every card.

    A relative ranking, not a deck win rate: each deck counts once per card in
    it, and Untapped's user base skews it upward. ``games`` is the archetype's
    deck-game count from ``metadata.games``, summed over ranks.
    """
    positions = _field_positions(payload.get("metadata", {}).get("fields"))
    wins: dict[str, int] = {}
    games: dict[str, int] = {}
    for archetypes in (payload.get("data") or {}).values():
        if not isinstance(archetypes, dict):
            continue
        for key, buckets in archetypes.items():
            if key == "ALL" or not isinstance(buckets, dict):
                continue
            t = _sum_buckets(buckets, positions)
            wins[key] = wins.get(key, 0) + t["wins"]
            games[key] = games.get(key, 0) + t["games"]
    meta_games = _meta_games(payload)
    out: dict[str, list[dict]] = {"two_color": [], "mono": [], "multicolor": []}
    for key, card_games in games.items():
        colors = decode_archetype(key)
        entry = {
            "key": key,
            "colors": colors,
            "games": sum((meta_games.get(key) or {}).values()),
            "card_games": card_games,
            "win_rate": _pct(wins[key], card_games),
        }
        group = {1: "mono", 2: "two_color"}.get(len(colors), "multicolor")
        out[group].append(entry)
    for group in out.values():
        group.sort(key=lambda e: (-(e["win_rate"] or 0.0), -e["games"]))
    return out


def _by_gih_wr(rows: list[dict], *, ascending: bool = False) -> list[dict]:
    sign = 1 if ascending else -1
    return sorted(rows, key=lambda r: (sign * (r["gih_wr"] or 0.0), -r["gih"]))


def best_commons(rows: list[dict], min_games: int) -> dict[str, list[dict]]:
    """Commons with ``gih >= min_games`` by GIH WR, grouped by colour.

    Mono-coloured commons under their colour, colourless under ``"C"``, and
    hybrid / gold commons together under ``"multicolor"``.
    """
    groups: dict[str, list[dict]] = {c: [] for c in _COLORS}
    groups["C"] = []
    groups["multicolor"] = []
    for row in rows:
        if row["rarity"] != "common" or row["gih"] < min_games:
            continue
        colors = row["colors"]
        key = colors if len(colors) == 1 else ("C" if not colors else "multicolor")
        groups[key].append(row)
    return {k: _by_gih_wr(v) for k, v in groups.items()}


def _rare_median(rows: list[dict], min_games: int) -> float | None:
    """Median GIH WR of the rares / mythics with a full sample (all of them when
    none has one)."""
    rares = [
        r for r in rows if r["rarity"] in {"rare", "mythic"} and r["gih_wr"] is not None
    ]
    pool = [r["gih_wr"] for r in rares if r["gih"] >= min_games] or [
        r["gih_wr"] for r in rares
    ]
    return round(statistics.median(pool), 1) if pool else None


def bomb_candidates(rows: list[dict], min_games: int) -> list[dict]:
    """Rares / mythics (plus uncommons beating the rare median) by GIH WR.

    Anything with at least 10 GIH is listed; ``sample`` is ``"ok"`` at
    ``min_games`` and ``"small"`` below it (render it bracketed).
    """
    median = _rare_median(rows, min_games)
    out = []
    for row in rows:
        if row["gih"] < _SMALL_SAMPLE_FLOOR or row["gih_wr"] is None:
            continue
        standout = (
            row["rarity"] == "uncommon"
            and median is not None
            and row["gih_wr"] > median
        )
        if row["rarity"] not in {"rare", "mythic"} and not standout:
            continue
        out.append(
            {
                **row,
                "sample": "ok" if row["gih"] >= min_games else "small",
                "standout_uncommon": standout,
            }
        )
    return _by_gih_wr(out)


def underperformers(rows: list[dict]) -> list[dict]:
    """Rares / mythics with GIH WR under 50% (and at least 10 GIH), worst first."""
    return _by_gih_wr(
        [
            r
            for r in rows
            if r["rarity"] in {"rare", "mythic"}
            and r["gih"] >= _SMALL_SAMPLE_FLOOR
            and r["gih_wr"] is not None
            and r["gih_wr"] < _UNDERPERFORM_WR
        ],
        ascending=True,
    )


def games_by_rank(payload: dict) -> dict[str, int]:
    """Total deck games per rank (``metadata.games["ALL"]``), plus ``"total"``."""
    ranks = _meta_games(payload).get("ALL") or {}
    ordered = {r: int(ranks[r]) for r in _RANK_ORDER if r in ranks}
    ordered.update({r: int(n) for r, n in ranks.items() if r not in ordered})
    ordered["total"] = sum(v for k, v in ordered.items() if k != "total")
    return ordered


def payload_source(payload: dict) -> str:
    """``"premium"`` when the payload carries the full field layout, else ``"file"``."""
    fields = payload.get("metadata", {}).get("fields") or []
    names = {n for section in fields if isinstance(section, list) for n in section}
    return "premium" if "not_available_games" in names else "file"


def build_report(
    payload: dict,
    index: dict[str, dict],
    *,
    set_code: str,
    event: str,
    source: str,
    fetched_at: str | None,
    min_games: int = 30,
) -> dict:
    """The whole guide-ready structure (what ``--json`` prints)."""
    rows = card_rows(payload, index)
    return {
        "summary": {
            "set": set_code.upper(),
            "event": event,
            "source": source,
            "fetched_at": fetched_at,
            "min_games": min_games,
            "games": games_by_rank(payload),
            "cards": len(rows),
            "rare_median_gih_wr": _rare_median(rows, min_games),
        },
        "color_pairs": {
            "method": "card-weighted",
            **color_pair_rates(payload),
        },
        "best_commons": best_commons(rows, min_games),
        "bomb_candidates": bomb_candidates(rows, min_games),
        "underperformers": underperformers(rows),
        "cards": _by_gih_wr(rows),
    }


# --- The pooled view ---------------------------------------------------------------


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def average_iwd(rows: list[dict], min_games: int) -> float | None:
    """The average card's IWD in one format: the mean over cards with a full
    sample (every card with an IWD when none has one)."""
    rated = [r for r in rows if r["iwd"] is not None]
    full = [r["iwd"] for r in rated if r["gih"] >= min_games]
    return _mean(full or [r["iwd"] for r in rated])


def _average_pair(pairs: list[dict]) -> float | None:
    """The games-weighted average two-colour pair rate of one format."""
    total = sum(p["games"] for p in pairs)
    return sum(p["games"] * p["win_rate"] for p in pairs) / total if total else None


def pair_tiers(
    reports: dict[str, dict], *, tier_gap: float = 5.0, clash: float = 10.0
) -> list[dict]:
    """Two-colour pairs pooled across formats.

    Each format's pair rate is taken against that format's games-weighted
    average pair, then the formats are pooled by deck games. ``tier`` is
    ``top`` / ``bottom`` at ``tier_gap`` points either side of average, else
    ``middle``. ``error`` is a rough one-sigma (binomial at 50% over the pooled
    games). ``clash`` marks a pair whose formats are ``clash`` or more points
    apart.
    """
    per: dict[str, dict[str, dict]] = {}
    for event, report in reports.items():
        pairs = [
            p
            for p in report["color_pairs"]["two_color"]
            if p["games"] and p["win_rate"] is not None
        ]
        base = _average_pair(pairs)
        if base is None:
            continue
        for p in pairs:
            per.setdefault(p["colors"], {})[event] = {
                "games": p["games"],
                "win_rate": p["win_rate"],
                "vs_average": p["win_rate"] - base,
            }
    out = []
    for colors, by_event in per.items():
        games = sum(e["games"] for e in by_event.values())
        rel = sum(e["games"] * e["vs_average"] for e in by_event.values()) / games
        rels = [e["vs_average"] for e in by_event.values()]
        tier = "top" if rel >= tier_gap else "bottom" if rel <= -tier_gap else "middle"
        out.append(
            {
                "colors": colors,
                "games": games,
                "vs_average": round(rel, 1),
                "error": round(50 / math.sqrt(games), 1),
                "tier": tier,
                "clash": len(rels) > 1 and max(rels) - min(rels) >= clash,
                "events": {
                    ev: {**e, "vs_average": round(e["vs_average"], 1)}
                    for ev, e in by_event.items()
                },
            }
        )
    out.sort(key=lambda e: (-e["vs_average"], -e["games"]))
    return out


def pooled_cards(reports: dict[str, dict], *, min_games: int = 30) -> list[dict]:
    """One row per card: IWD pooled across formats by games drawn.

    ``iwd`` is the pooled IWD itself; ``vs_average`` pools each format's IWD
    minus that format's average card (:func:`average_iwd`), the number the
    thresholds read. ``events`` keeps each format's own figures.
    """
    averages = {
        ev: average_iwd(report["cards"], min_games) for ev, report in reports.items()
    }
    cards: dict[str, dict] = {}
    for event, report in reports.items():
        avg = averages[event]
        for row in report["cards"]:
            if row["iwd"] is None or not row["gih"] or avg is None:
                continue
            card = cards.setdefault(
                row["title_id"],
                {k: row[k] for k in ("title_id", "name", "rarity", "colors", "set")}
                | {"events": {}},
            )
            card["events"][event] = {
                "gih": row["gih"],
                "iwd": row["iwd"],
                "vs_average": round(row["iwd"] - avg, 1),
            }
    out = []
    for card in cards.values():
        events = card["events"].values()
        drawn = sum(e["gih"] for e in events)
        iwd = sum(e["gih"] * e["iwd"] for e in events) / drawn
        rel = sum(e["gih"] * e["vs_average"] for e in events) / drawn
        out.append(
            card | {"gih": drawn, "iwd": round(iwd, 1), "vs_average": round(rel, 1)}
        )
    out.sort(key=lambda c: (-c["vs_average"], -c["gih"]))
    return out


def color_depth(cards: list[dict], pool_min_games: int) -> dict[str, dict]:
    """Per mono colour: the commons' mean pooled IWD against the average card,
    over commons with ``pool_min_games`` drawn."""
    out = {}
    for color in _COLORS:
        rels = [
            c["vs_average"]
            for c in cards
            if c["rarity"] == "common"
            and c["colors"] == color
            and c["gih"] >= pool_min_games
        ]
        mean = _mean(rels)
        out[color] = {
            "vs_average": None if mean is None else round(mean, 1),
            "commons": len(rels),
        }
    return out


def format_disagreements(cards: list[dict], *, clash: float = 10.0) -> list[dict]:
    """Cards whose formats are ``clash`` or more points apart against their own
    averages, each with ``_CLASH_FLOOR`` games drawn per format: where a card
    plays differently in sealed (a copy-count card like a draft-collected
    package, say). Widest gap first."""
    out = []
    for card in cards:
        rels = [
            e["vs_average"] for e in card["events"].values() if e["gih"] >= _CLASH_FLOOR
        ]
        if len(rels) > 1 and max(rels) - min(rels) >= clash:
            out.append(card | {"gap": round(max(rels) - min(rels), 1)})
    out.sort(key=lambda c: -c["gap"])
    return out


def build_pooled(
    reports: dict[str, dict],
    *,
    missing: dict[str, str] | None = None,
    min_games: int = 30,
    pool_min_games: int = 60,
    margin: float = 10.0,
    tier_gap: float = 5.0,
    clash: float = 10.0,
) -> dict:
    """The pooled view over each format's :func:`build_report`.

    A standout or underperformer is ``margin`` points from the average card
    with ``pool_min_games`` drawn across the formats; the data bombs are the
    rares / mythics among the standouts, and every rare / mythic under that
    sample is listed as thin (a reviewer's call, not the data's), special
    guests from other sets included (they're in the set's boosters), once a
    handful have been drawn so a card seen once doesn't crowd the list.
    """
    cards = pooled_cards(reports, min_games=min_games)
    sampled = [c for c in cards if c["gih"] >= pool_min_games]
    standouts = [c for c in sampled if c["vs_average"] >= margin]
    rare = {"rare", "mythic"}
    formats = {}
    for event, report in reports.items():
        pairs = [
            p
            for p in report["color_pairs"]["two_color"]
            if p["games"] and p["win_rate"] is not None
        ]
        avg_pair = _average_pair(pairs)
        avg_iwd = average_iwd(report["cards"], min_games)
        formats[event] = {
            "source": report["summary"]["source"],
            "fetched_at": report["summary"]["fetched_at"],
            "games": report["summary"]["games"]["total"],
            "average_pair": None if avg_pair is None else round(avg_pair, 1),
            "average_iwd": None if avg_iwd is None else round(avg_iwd, 1),
        }
    return {
        "events": list(reports),
        "missing": missing or {},
        "thresholds": {
            "pool_min_games": pool_min_games,
            "margin": margin,
            "tier_gap": tier_gap,
            "clash": clash,
            "clash_floor": _CLASH_FLOOR,
        },
        "formats": formats,
        "pairs": pair_tiers(reports, tier_gap=tier_gap, clash=clash),
        "color_depth": color_depth(cards, pool_min_games),
        "standouts": standouts,
        "data_bombs": [c for c in standouts if c["rarity"] in rare],
        "underperformers": sorted(
            (c for c in sampled if c["vs_average"] <= -margin),
            key=lambda c: c["vs_average"],
        ),
        "thin_rares": [
            c
            for c in cards
            if c["rarity"] in rare and _SMALL_SAMPLE_FLOOR <= c["gih"] < pool_min_games
        ],
        "disagreements": format_disagreements(cards, clash=clash),
        "cards": cards,
    }


# --- Fetching --------------------------------------------------------------------


def cache_dir() -> Path:
    """``<cache root>/untapped`` (``_http.cache_root``)."""
    return cache_root() / "untapped"


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(
        timespec="seconds"
    )


def _server_message(resp: requests.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text.strip()
    return body if isinstance(body, str) else json.dumps(body)[:300]


def fetch_card_stats(set_code: str, event: str) -> tuple[dict, str]:
    """The free card-stats payload and when it was fetched (24h cache)."""
    set_code, event = set_code.upper(), event.upper()
    path = cache_dir() / f"card_stats_{set_code}_{event}.json"
    if not is_fresh(path):
        resp = requests.get(
            f"{API_URL}/free",
            params={
                "CardSetFilter": set_code,
                "LimitedEventTypeFilter": event,
                "LimitedEventTimeIntervalFilter": TIME_INTERVAL,
            },
            headers=HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 204 or not resp.content.strip():
            raise click.ClickException(
                f"no Untapped data yet for {set_code}/{event}: an empty answer "
                f"(HTTP {resp.status_code}) from {API_URL}. If the set-guide page "
                "shows stats, Untapped has moved the query again; read the page's "
                "network calls for the new path"
            )
        if resp.status_code >= 400:
            raise _rejected(set_code, event, _server_message(resp))
        payload = _check_data(resp.json(), set_code, event)
        atomic_write_bytes(path, resp.content)  # never an empty or error answer
        return payload, _mtime_iso(path)
    return json.loads(path.read_text(encoding="utf-8")), _mtime_iso(path)


def mtgajson_files() -> tuple[list[dict], list[dict]]:
    """Untapped's public Arena card files — ``cards.json`` (every printing: grpid,
    titleId, rarity, set) and ``loc_en.json`` (titleId -> English text) — cached for
    24 hours under :func:`cache_dir`. ``arena-meta`` names deckstring cards with them
    too."""
    fetcher = HttpFetcher(
        cache_dir(),
        user_agent=BROWSER_HEADERS["User-Agent"],
        max_age_seconds=_CACHE_SECONDS,
    )
    cards = json.loads(fetcher.fetch(CARDS_URL, "cards.json"))
    loc = json.loads(fetcher.fetch(LOC_URL, "loc_en.json"))
    return cards, loc


def fetch_card_index(set_code: str, title_ids: set[str]) -> dict[str, dict]:
    """titleId -> name / rarity / colours / set from the cached mtgajson files."""
    cards, loc = mtgajson_files()
    return build_card_index(cards, loc, set_code, title_ids)


def _rejected(set_code: str, event: str, message: str) -> click.ClickException:
    return click.ClickException(
        f"Untapped rejected {set_code.upper()}/{event.upper()}: {message} "
        f"(event types include {_EXAMPLE_EVENTS})"
    )


def _check_data(payload: object, set_code: str, event: str) -> dict:
    """*payload* when it is a stats payload with data. A string is Untapped's
    error message (an unknown event type, say); no ``data`` means no stats yet."""
    if isinstance(payload, str):
        raise _rejected(set_code, event, payload)
    if not isinstance(payload, dict) or not payload.get("data"):
        raise click.ClickException(
            f"no Untapped data yet for {set_code.upper()}/{event.upper()}"
        )
    return payload


# --- Rendering -------------------------------------------------------------------


def _fmt(value: float | None) -> str:
    return "--" if value is None else f"{value:.1f}%"


def _gih(row: dict) -> str:
    wr = _fmt(row["gih_wr"])
    return f"[{wr}]" if row.get("sample") == "small" else wr


def _set_note(row: dict, set_code: str) -> str:
    card_set = row.get("set")
    return f" ({card_set})" if card_set and card_set.upper() != set_code else ""


def _label(row: dict, set_code: str) -> str:
    """``Name (SET) [rarity colours]`` — the set only when it isn't *set_code*."""
    return (
        f"{row['name']}{_set_note(row, set_code)}"
        f" [{row['rarity']} {row['colors'] or 'C'}]"
    )


_TOP_COMMONS = 5
_TOP_BOMBS = 15


def render_text(report: dict) -> str:
    s = report["summary"]
    code = s["set"]
    lines = [
        (
            f"# {code} {s['event']} — Untapped.gg"
            f" ({s['source']}, fetched {s['fetched_at']})"
        ),
        "",
        "## Summary",
        "games: "
        + ", ".join(f"{rank} {n}" for rank, n in s["games"].items() if rank != "total")
        + f" (total {s['games']['total']})",
        (
            f"cards: {s['cards']}; rare/mythic median GIH WR"
            f" {_fmt(s['rare_median_gih_wr'])}; sample floor {s['min_games']} GIH"
        ),
        "",
        "## Colour pairs (card-weighted win rate; a relative ranking, skews high)",
    ]
    pairs = report["color_pairs"]
    for label, group in (
        ("two-colour", "two_color"),
        ("3+ colours", "multicolor"),
        ("mono", "mono"),
    ):
        if not pairs[group]:
            continue
        lines.append(f"{label}:")
        lines.extend(
            f"  {e['colors']:<5} {_fmt(e['win_rate']):>6}  ({e['games']} games)"
            for e in pairs[group]
        )
    lines += ["", f"## Best commons by colour (GIH WR, >= {s['min_games']} GIH)"]
    for color, rows in report["best_commons"].items():
        if not rows:
            continue
        top = ", ".join(
            f"{r['name']}{_set_note(r, code)} {_fmt(r['gih_wr'])}"
            for r in rows[:_TOP_COMMONS]
        )
        lines.append(f"  {color}: {top}")
    lines += ["", "## Bomb candidates (GIH WR; [bracketed] = small sample)"]
    for r in report["bomb_candidates"][:_TOP_BOMBS]:
        flag = " standout uncommon" if r["standout_uncommon"] else ""
        iwd = "--" if r["iwd"] is None else f"{r['iwd']:+.1f}"
        lines.append(
            f"  {_gih(r):>8}  {_label(r, code)}{flag}  GIH {r['gih']}, IWD {iwd}"
        )
    lines += ["", "## Underperformers (rares/mythics under 50% GIH WR)"]
    if not report["underperformers"]:
        lines.append("  none")
    for r in report["underperformers"]:
        lines.append(f"  {_fmt(r['gih_wr']):>6}  {_label(r, code)}  GIH {r['gih']}")
    return "\n".join(lines)


def _signed(value: float | None) -> str:
    return "--" if value is None else f"{value:+.1f}"


def _per_event(events: dict[str, dict], count: str) -> str:
    return " · ".join(
        f"{ev} {_signed(e['vs_average'])} ({e[count]})" for ev, e in events.items()
    )


def _card_line(card: dict, code: str, *, bracket: bool = False) -> str:
    iwd = _signed(card["iwd"])
    iwd = f"[{iwd}]" if bracket else iwd
    return (
        f"  {iwd:>7}  {_label(card, code)}  vs avg {_signed(card['vs_average'])},"
        f" {card['gih']} drawn  ({_per_event(card['events'], 'gih')})"
    )


def render_pooled(pooled: dict, set_code: str) -> str:
    code = set_code.upper()
    th = pooled["thresholds"]
    lines = [
        f"# {code} pooled — {' + '.join(pooled['events'])} (Untapped.gg)",
        "Each pair and card is measured against its own format's average, then",
        "pooled across the formats by games.",
        "",
        "## Formats",
    ]
    for event, f in pooled["formats"].items():
        lines.append(
            f"  {event}: {f['source']}, fetched {f['fetched_at']}, {f['games']} games;"
            f" average pair {_fmt(f['average_pair'])},"
            f" average card IWD {_signed(f['average_iwd'])}"
        )
    for event, reason in pooled["missing"].items():
        lines.append(f"  {event}: missing ({reason})")
    lines += [
        "",
        f"## Colour pairs (vs the average pair; tiers at ±{th['tier_gap']:g})",
    ]
    for e in pooled["pairs"]:
        flag = "  <- formats clash" if e["clash"] else ""
        lines.append(
            f"  {e['tier']:<6}  {e['colors']:<3} {_signed(e['vs_average']):>6}"
            f" (±{e['error']:.1f}, {e['games']} games)"
            f"  {_per_event(e['events'], 'games')}{flag}"
        )
    lines += [
        "",
        (
            "## Colour depth at common (mean IWD vs the average card;"
            f" commons with {th['pool_min_games']}+ drawn)"
        ),
        "  "
        + " · ".join(
            f"{color} {_signed(d['vs_average'])} ({d['commons']})"
            for color, d in pooled["color_depth"].items()
        ),
    ]
    sections = (
        (
            (
                f"## Standouts (IWD {th['margin']:g}+ over the average card,"
                f" {th['pool_min_games']}+ drawn)"
            ),
            pooled["standouts"],
            False,
        ),
        (
            "## Data bombs (rares / mythics among the standouts)",
            pooled["data_bombs"],
            False,
        ),
        (
            f"## Underperformers (IWD {th['margin']:g}+ under the average card)",
            pooled["underperformers"],
            False,
        ),
        (
            (
                f"## Thin rares (under {th['pool_min_games']} drawn: a reviewer's"
                " call; [bracketed])"
            ),
            pooled["thin_rares"],
            True,
        ),
    )
    for heading, cards, bracket in sections:
        lines += ["", heading]
        lines.extend(_card_line(c, code, bracket=bracket) for c in cards)
        if not cards:
            lines.append("  none")
    lines += [
        "",
        (
            f"## Formats disagree ({th['clash']:g}+ points apart,"
            f" {th['clash_floor']}+ drawn in each)"
        ),
    ]
    lines.extend(
        f"  {c['gap']:>5.1f}  {_label(c, code)}  {_per_event(c['events'], 'gih')}"
        for c in pooled["disagreements"]
    )
    if not pooled["disagreements"]:
        lines.append("  none")
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------------


def _load(set_code: str, event: str, premium: Path | None) -> tuple[dict, str, str]:
    """One format's payload, its source and when it was fetched."""
    if premium is not None:
        raw = json.loads(premium.read_text(encoding="utf-8"))
        payload = _check_data(raw, set_code, event)
        return payload, payload_source(payload), _mtime_iso(premium)
    payload, fetched_at = fetch_card_stats(set_code, event)
    return payload, "free", fetched_at


def _report(
    payload: dict,
    index: dict,
    set_code: str,
    event: str,
    source: str,
    fetched_at: str,
    min_games: int,
) -> dict:
    return build_report(
        payload,
        index,
        set_code=set_code,
        event=event,
        source=source,
        fetched_at=fetched_at,
        min_games=min_games,
    )


@click.command()
@click.option("--set", "set_code", required=True, help="Arena set code, e.g. FRA.")
@click.option(
    "--event",
    default=None,
    help=(
        f"One Untapped limited event type ({_EXAMPLE_EVENTS}). Omit it for the"
        " pooled Sealed + Premier Draft view."
    ),
)
@click.option(
    "--premium-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A saved card_stats_limited_by_set_v2 payload for --event.",
)
@click.option(
    "--premium-sealed",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A saved SEALED payload for the pooled view (else the free one).",
)
@click.option(
    "--premium-draft",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A saved PREMIER_DRAFT payload for the pooled view (else the free one).",
)
@click.option(
    "--min-games",
    default=30,
    show_default=True,
    type=click.IntRange(min=1),
    help="GIH floor for a full-sample stat within one format.",
)
@click.option(
    "--pool-min-games",
    default=60,
    show_default=True,
    type=click.IntRange(min=1),
    help="Games drawn, across the formats, before a card is a standout or not.",
)
@click.option(
    "--margin",
    default=10.0,
    show_default=True,
    type=click.FloatRange(min=0),
    help="IWD points from the average card for a standout / underperformer.",
)
@click.option(
    "--tier-gap",
    default=5.0,
    show_default=True,
    type=click.FloatRange(min=0),
    help="Points from the average pair for a top / bottom pair.",
)
@click.option(
    "--clash",
    default=10.0,
    show_default=True,
    type=click.FloatRange(min=0),
    help="Points apart before the formats count as disagreeing.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the full structure.")
def main(
    set_code: str,
    event: str | None,
    premium_json: Path | None,
    premium_sealed: Path | None,
    premium_draft: Path | None,
    min_games: int,
    pool_min_games: int,
    margin: float,
    tier_gap: float,
    clash: float,
    as_json: bool,  # noqa: FBT001 — a click flag
) -> None:
    """Untapped.gg limited card stats for SET as guide-ready numbers.

    With no --event: Arena Sealed and Premier Draft, pooled view first."""
    if event is not None:
        if premium_sealed or premium_draft:
            raise click.UsageError(
                "--premium-sealed / --premium-draft are for the pooled view; with"
                " --event, pass --premium-json"
            )
        event = event.upper()
        payload, source, fetched_at = _load(set_code, event, premium_json)
        index = fetch_card_index(set_code, set(payload["data"]))
        report = _report(payload, index, set_code, event, source, fetched_at, min_games)
        click.echo(json.dumps(report, indent=2) if as_json else render_text(report))
        return
    if premium_json is not None:
        raise click.UsageError(
            "--premium-json needs --event; for the pooled view pass"
            " --premium-sealed / --premium-draft"
        )
    premium = dict(zip(POOL_EVENTS, (premium_sealed, premium_draft), strict=True))
    loaded: dict[str, tuple[dict, str, str]] = {}
    missing: dict[str, str] = {}
    for ev in POOL_EVENTS:
        try:
            loaded[ev] = _load(set_code, ev, premium[ev])
        except click.ClickException as exc:
            missing[ev] = exc.message
    if not loaded:
        raise click.ClickException("; ".join(missing.values()))
    index = fetch_card_index(
        set_code, {tid for payload, _, _ in loaded.values() for tid in payload["data"]}
    )
    reports = {
        ev: _report(payload, index, set_code, ev, source, fetched_at, min_games)
        for ev, (payload, source, fetched_at) in loaded.items()
    }
    pooled = build_pooled(
        reports,
        missing=missing,
        min_games=min_games,
        pool_min_games=pool_min_games,
        margin=margin,
        tier_gap=tier_gap,
        clash=clash,
    )
    if as_json:
        click.echo(json.dumps({"pooled": pooled, "events": reports}, indent=2))
        return
    click.echo(
        "\n\n".join(
            [
                render_pooled(pooled, set_code),
                *(render_text(r) for r in reports.values()),
            ]
        )
    )
