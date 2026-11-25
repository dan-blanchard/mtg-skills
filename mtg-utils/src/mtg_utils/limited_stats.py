"""Untapped.gg MTG Arena limited card stats, turned into guide-ready numbers.

    limited-stats --set FRA [--premium-sealed PATH] [--premium-draft PATH]
                  [--pool-min-games 60] [--margin 10] [--confidence 90]
                  [--tier-gap 5] [--clash 10] [--min-games 30]
                  [--reviews | --reviews-json PATH] [--json]
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
pairs or cards. Every card's pooled lift carries a ± range (``--confidence``,
:func:`iwd_standard_error`), and a card is a standout, underperformer or data
bomb only when the cautious end of that range clears ``--margin``; one whose
estimate clears it but whose range does not is listed as *leaning*.
``--event`` keeps the single-format report.

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
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import click
import requests

from mtg_utils._http import BROWSER_HEADERS, HttpFetcher, cache_root, is_fresh
from mtg_utils._sidecar import atomic_write_bytes
from mtg_utils.arena_card_db import arena_title
from mtg_utils.names import normalize_card_name

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
#: chunk.science's set pages: ``/<CODE>`` redirects to the set's page, whose
#: ``data/<code>.<hash>.js`` script holds every reviewer's grade per card.
REVIEWS_URL = "https://chunk.science"
#: The reviewer average at or over which a rare the data is too thin for is a
#: bomb (0-100; A- is 90): the guide skill's own evidence rule.
REVIEWER_BOMB_MEAN = 90.0
# A card needs this many games drawn in each format before a gap between the
# formats is listed as a disagreement.
_CLASH_FLOOR = 20
#: The confidence (percent) of a pooled card's ± range; a label needs the
#: range's cautious end to clear the margin (``--confidence``).
DEFAULT_CONFIDENCE = 90.0


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


def iwd_standard_error(
    drawn_games: int, drawn_wins: int, undrawn_games: int, undrawn_wins: int
) -> float | None:
    """The standard error of one format's IWD, in percentage points.

    The IWD is the win rate in the games the card was drawn minus the win rate
    in the games it sat in the deck undrawn. Each rate is a share of wins, and
    the uncertainty of a share of ``n`` games is ``sqrt(p * (1 - p) / n)``; the
    two groups of games are treated as independent, so the two variances add
    and the difference's error is the square root of the sum. ``p`` is read the
    Agresti-Caffo way, one win and one loss added to each group (``(w + 1) /
    (n + 2)`` over ``n + 2`` games), so a group that won every game still has a
    width; at the 60+
    games a label needs, that moves the result by under 0.1 point for an even
    record and up to about 0.2 for a lopsided one (55-5 over 60 games).
    The IWD itself stays the plain difference. ``None`` when either group has
    no games (there is no IWD then either).

    What it leaves out:

    - The format's average card, which the pooled view subtracts, is treated as
      exact. It is a mean over a few hundred cards' IWDs, so the games' noise in
      it is ``sqrt(Σ se²) / N``, about a tenth of a typical card's error
      (measured: 0.14 against 1.5 points in TRK Sealed, 0.65 against 8.7 in FRA
      draft): acceptable.
    - Games are not independent. One deck plays several games of a run (and,
      in Bo3, of a match), and a good deck wins more whether or not the card is
      drawn. That clustering widens each rate's true error, but the drawn and
      undrawn games come from the same decks, so deck strength moves both rates
      together and largely cancels in their difference. The payload holds no
      per-deck counts to measure either effect, so the net is unknown: read the
      range as the games' own noise, not a guarantee.
    - Bias. An IWD favours cards drawn in long games (more draws) and is skewed
      by who plays a card; the error says how noisy the number is, not whether
      it measures the card's strength.
    - On the free tier the undrawn counts are derived, ``games - drawn``
      (:func:`_sum_buckets`): ``games`` also counts the games the card sat in
      the sideboard and never in the main deck (``games - in_main_games``:
      0.85% of TRK draft card-games, but 28% of Brazen Bluff's draft not-drawn
      games), and the payload gives no wins split to take them out. The error
      is the error of that same derived estimate.
    """
    if drawn_games <= 0 or undrawn_games <= 0:
        return None
    drawn = (drawn_wins + 1) / (drawn_games + 2)
    undrawn = (undrawn_wins + 1) / (undrawn_games + 2)
    variance = drawn * (1 - drawn) / (drawn_games + 2) + undrawn * (1 - undrawn) / (
        undrawn_games + 2
    )
    return 100.0 * math.sqrt(variance)


def z_score(confidence: float) -> float:
    """The two-sided normal multiplier for a *confidence* percentage (90 ->
    1.645): a range of ``z`` standard errors either side holds the true value
    that share of the time. 0 is the point estimate alone."""
    return statistics.NormalDist().inv_cdf(0.5 + confidence / 200.0)


def card_rows(payload: dict, index: dict[str, dict]) -> list[dict]:
    """One row per card over the ``ALL`` archetype, summed across rank buckets.

    ``iwd_se`` is the IWD's standard error (:func:`iwd_standard_error`)."""
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
        se = iwd_standard_error(
            t["available_games"],
            t["available_wins"],
            t["not_available_games"],
            t["not_available_wins"],
        )
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
                "iwd_se": None if se is None else round(se, 2),
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


def pooled_cards(
    reports: dict[str, dict],
    *,
    min_games: int = 30,
    confidence: float = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """One row per card: IWD pooled across formats by games drawn.

    ``iwd`` is the pooled IWD itself; ``vs_average`` pools each format's IWD
    minus that format's average card (:func:`average_iwd`), the number the
    thresholds read. ``events`` keeps each format's own figures.

    ``se`` is the pooled lift's standard error: the pooled lift is a weighted
    mean of the formats' lifts (weights ``g_e``, the games drawn in each), and
    the formats are separate games, so its variance is ``Σ g_e² se_e² / (Σ
    g_e)²`` over each format's :func:`iwd_standard_error`. ``plus_minus`` is
    ``se`` times :func:`z_score` of *confidence*: the half-width of the range,
    shared by ``iwd`` and ``vs_average`` (the average is taken as exact). Each
    format's entry carries its own ``se`` and ``plus_minus`` too.
    """
    z = z_score(confidence)
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
                "se": row["iwd_se"],
                "plus_minus": round(z * row["iwd_se"], 1),
            }
    out = []
    for card in cards.values():
        events = card["events"].values()
        drawn = sum(e["gih"] for e in events)
        iwd = sum(e["gih"] * e["iwd"] for e in events) / drawn
        rel = sum(e["gih"] * e["vs_average"] for e in events) / drawn
        se = math.sqrt(sum((e["gih"] * e["se"]) ** 2 for e in events)) / drawn
        out.append(
            card
            | {
                "gih": drawn,
                "iwd": round(iwd, 1),
                "vs_average": round(rel, 1),
                "se": round(se, 2),
                "plus_minus": round(z * se, 1),
            }
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


# --- Reviewer consensus -----------------------------------------------------------

_DATA_ASSIGNMENT_RX = re.compile(r"\s*window\.\w+\s*=\s*")


def _review_key(name: str) -> str:
    """A card name as the two sites both spell it: accents, case, punctuation
    and spacing folded (Arena's "All Good Things . . ." is chunk.science's
    "All Good Things...")."""
    return re.sub(r"[^a-z0-9]", "", normalize_card_name(name))


def parse_reviews(script: str) -> dict[str, dict]:
    """chunk.science's set data script (``window.<CODE>_DATA = {...};``) as
    folded card name (:func:`_review_key`) -> ``{name, rarity, mean, sources}``:
    the reviewers' average grade (0-100) and how many graded the card. A
    double-faced card answers to its whole name and its front face. Raises
    ``ValueError`` on any other script."""
    assignment = _DATA_ASSIGNMENT_RX.match(script)
    if assignment is None:
        msg = "not a chunk.science set data script (no `window.<CODE>_DATA = `)"
        raise ValueError(msg)
    data = json.loads(script[assignment.end() :].rstrip().rstrip(";"))
    out: dict[str, dict] = {}
    for card in data.get("cards") or []:
        consensus = card.get("consensus") or {}
        name, mean = card.get("name"), consensus.get("mean")
        if not name or mean is None:
            continue
        row = {
            "name": name,
            "rarity": str(card.get("rarity") or "").lower(),
            "mean": float(mean),
            "sources": int(consensus.get("sourceCount") or 0),
        }
        for spelling in (name, name.split(" // ")[0]):
            out.setdefault(_review_key(spelling), row)
    return out


def _review_of(card: dict, reviews: dict[str, dict]) -> dict | None:
    """The review of a stats row's card, by its whole name (Arena names a
    double-faced card by its front face, which :func:`parse_reviews` also
    keys)."""
    return reviews.get(_review_key(str(card.get("name") or "")))


def reviewer_bombs(
    cards: list[dict], reviews: dict[str, dict], pool_min_games: int
) -> list[dict]:
    """The rares and mythics the data is too thin to judge (under
    ``pool_min_games`` drawn across the formats, the ones with no stats row
    included) that the reviewers grade a bomb (:data:`REVIEWER_BOMB_MEAN` or
    better), highest grade first. Each row carries the grade, the reviewer count
    and the games drawn; ``iwd`` is there only where some were."""
    drawn = {}
    for card in cards:
        if (review := _review_of(card, reviews)) is not None:
            drawn[review["name"]] = card
    out = []
    graded = {r["name"]: r for r in reviews.values()}.values()
    for review in sorted(graded, key=lambda r: (-r["mean"], r["name"])):
        if review["rarity"] not in ("rare", "mythic"):
            continue
        if review["mean"] < REVIEWER_BOMB_MEAN:
            continue
        card = drawn.get(review["name"])
        if card is not None and card["gih"] >= pool_min_games:
            continue  # the data's to call
        out.append(
            {
                "name": card["name"] if card is not None else review["name"],
                "rarity": review["rarity"],
                "review_mean": review["mean"],
                "review_sources": review["sources"],
                "gih": card["gih"] if card is not None else 0,
                "iwd": card["iwd"] if card is not None else None,
                "set": card.get("set") if card is not None else None,
            }
        )
    return out


def _with_review(card: dict, reviews: dict[str, dict]) -> dict:
    """*card* with the reviewers' average grade and count, when they graded it."""
    review = _review_of(card, reviews)
    if review is None:
        return card
    return card | {"review_mean": review["mean"], "review_sources": review["sources"]}


def build_pooled(
    reports: dict[str, dict],
    *,
    missing: dict[str, str] | None = None,
    min_games: int = 30,
    pool_min_games: int = 60,
    margin: float = 10.0,
    tier_gap: float = 5.0,
    clash: float = 10.0,
    confidence: float = DEFAULT_CONFIDENCE,
    reviews: dict[str, dict] | None = None,
) -> dict:
    """The pooled view over each format's :func:`build_report`.

    A standout is a card with ``pool_min_games`` drawn across the formats
    whose lift is ``margin`` points over the average card even at the low end
    of its range (``vs_average - plus_minus``, at *confidence*:
    :func:`pooled_cards`); an underperformer is ``margin`` under it even at the
    high end. A card whose point estimate clears the margin but whose cautious
    end does not is ``leaning`` (``lean``: ``"standout"`` / ``"underperformer"``),
    never a label. The data bombs are the rares / mythics among the standouts,
    and every rare / mythic under the games floor is listed as thin (a
    reviewer's call, not the data's), special guests from other sets included
    (they're in the set's boosters), once a handful have been drawn so a card
    seen once doesn't crowd the list. The floor stays beside the range: it is
    not redundant (on FRA's thin data, five cards under 60 drawn clear the
    range at 90%, from Flesh Duplicate's 2 games to Garruk, Veiled Butcher's
    24; ten at 80%, two at 95%), and under it the
    range itself is least trustworthy (few decks, so the clustering
    :func:`iwd_standard_error` can't see matters most).

    ``reviews`` (:func:`parse_reviews`) puts the reviewers' average grade and
    count on each thin rare and each leaning rare / mythic (``review_mean`` /
    ``review_sources``: the data can't call either, so the reviewers do) and adds
    ``reviewer_bombs`` (:func:`reviewer_bombs`); without it both are absent.
    """
    cards = pooled_cards(reports, min_games=min_games, confidence=confidence)
    sampled = [c for c in cards if c["gih"] >= pool_min_games]
    # Rounded as printed, so a reader can check the arithmetic on the page.
    standouts = [
        c for c in sampled if round(c["vs_average"] - c["plus_minus"], 1) >= margin
    ]
    under = [
        c for c in sampled if round(c["vs_average"] + c["plus_minus"], 1) <= -margin
    ]
    labelled = {c["title_id"] for c in (*standouts, *under)}
    # Leaning standouts first, then leaning underperformers, each furthest first.
    leaning = [
        c | {"lean": "standout" if c["vs_average"] > 0 else "underperformer"}
        for c in sorted(
            sampled, key=lambda c: (c["vs_average"] < 0, -abs(c["vs_average"]))
        )
        if abs(c["vs_average"]) >= margin and c["title_id"] not in labelled
    ]
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
            # The undrawn games behind each IWD and its error: Premium counts
            # them, the free tier derives them (:func:`iwd_standard_error`).
            "not_drawn": (
                "counted" if report["summary"]["source"] == "premium" else "derived"
            ),
        }
    thin_rares = [
        c
        for c in cards
        if c["rarity"] in rare and _SMALL_SAMPLE_FLOOR <= c["gih"] < pool_min_games
    ]
    graded = {}
    if reviews is not None:
        thin_rares = [_with_review(c, reviews) for c in thin_rares]
        leaning = [
            _with_review(c, reviews) if c["rarity"] in rare else c for c in leaning
        ]
        graded = {"reviewer_bombs": reviewer_bombs(cards, reviews, pool_min_games)}
    return {
        "events": list(reports),
        "missing": missing or {},
        "thresholds": {
            "pool_min_games": pool_min_games,
            "margin": margin,
            "tier_gap": tier_gap,
            "clash": clash,
            "clash_floor": _CLASH_FLOOR,
            "confidence": confidence,
            "z": round(z_score(confidence), 3),
        },
        "formats": formats,
        "pairs": pair_tiers(reports, tier_gap=tier_gap, clash=clash),
        "color_depth": color_depth(cards, pool_min_games),
        "standouts": standouts,
        "data_bombs": [c for c in standouts if c["rarity"] in rare],
        "underperformers": sorted(under, key=lambda c: c["vs_average"]),
        "leaning": leaning,
        "thin_rares": thin_rares,
        **graded,
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


def _reviews_script_url(page: str, page_url: str, set_code: str) -> str | None:
    """The set data script a chunk.science set page loads: its ``<script src>``
    ending ``data/<code>.<hash>.js`` (never ``<code>_17lands…``)."""
    wanted = re.compile(
        r'<script[^>]*\bsrc="([^"]*/data/'
        + re.escape(set_code.lower())
        + r'\.[0-9a-f]+\.js)"'
    )
    found = wanted.search(page)
    return urljoin(page_url, found.group(1)) if found else None


def fetch_reviews(set_code: str) -> tuple[dict[str, dict], str]:
    """chunk.science's reviewer grades for the set (:func:`parse_reviews`) and
    when they were fetched: the set page, then the data script it loads, kept 24
    hours under ``<cache>/reviews/<CODE>.js``."""
    code = set_code.upper()
    path = cache_root() / "reviews" / f"{code}.js"
    if not is_fresh(path):
        page = requests.get(f"{REVIEWS_URL}/{code}", headers=HEADERS, timeout=_TIMEOUT)
        if page.status_code >= 400:
            raise click.ClickException(
                f"no reviewer page for {code} at {REVIEWS_URL} "
                f"(HTTP {page.status_code})"
            )
        url = _reviews_script_url(page.text, page.url, code)
        if url is None:
            raise click.ClickException(
                f"{page.url} loads no data/{code.lower()}.<hash>.js script: "
                "chunk.science changed its page, or has no page for this set"
            )
        script = requests.get(url, headers=HEADERS, timeout=_TIMEOUT)
        if script.status_code >= 400:
            raise click.ClickException(f"{url}: HTTP {script.status_code}")
        try:
            # the bytes, not ``.text``: served without a charset, requests would
            # read the script's UTF-8 as Latin-1 and the cache would not
            reviews = parse_reviews(script.content.decode("utf-8"))
        except ValueError as exc:
            raise click.ClickException(f"{url}: {exc}") from exc
        atomic_write_bytes(path, script.content)  # only ever a script that parses
        return reviews, _mtime_iso(path)
    return parse_reviews(path.read_text(encoding="utf-8")), _mtime_iso(path)


def cached_stat_names(set_code: str) -> dict[str, str | None]:
    """Card name -> home set for every card the set's cached stats payloads
    list, read off the cache alone (no network): the cards in the set's
    boosters, its bonus sheet's guests among them, which the bulk files under
    their home set. Empty when nothing is cached (``limited-stats`` has not been
    run for the set on this machine)."""
    payloads = sorted(cache_dir().glob(f"card_stats_{set_code.upper()}_*.json"))
    files = [cache_dir() / name for name in ("cards.json", "loc_en.json")]
    if not payloads or not all(f.is_file() for f in files):
        return {}
    title_ids = {
        str(title_id)
        for path in payloads
        for title_id in json.loads(path.read_text(encoding="utf-8")).get("data") or {}
    }
    cards, loc = (json.loads(f.read_text(encoding="utf-8")) for f in files)
    return {
        row["name"]: row["set"]
        for title_id, row in build_card_index(cards, loc, set_code, title_ids).items()
        if row["name"] != f"titleId {title_id}"
    }


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


def _plus_minus(entry: dict, *, ranged: bool) -> str:
    return f" ±{entry['plus_minus']:.1f}" if ranged and "plus_minus" in entry else ""


def _per_event(events: dict[str, dict], count: str, *, ranged: bool = False) -> str:
    return " · ".join(
        f"{ev} {_signed(e['vs_average'])}{_plus_minus(e, ranged=ranged)} ({e[count]})"
        for ev, e in events.items()
    )


def _review_note(card: dict) -> str:
    if "review_mean" not in card:
        return ""
    return f"  reviewers {card['review_mean']:.1f} ({card['review_sources']})"


def _card_line(
    card: dict, code: str, *, bracket: bool = False, ranged: bool = False
) -> str:
    """One card of the pooled view; *ranged* prints its ± (no ± at confidence
    0, where the line is the point estimate's, as before the range)."""
    pm = _plus_minus(card, ranged=ranged)
    iwd = f"{_signed(card['iwd'])}{pm}"
    iwd = f"[{iwd}]" if bracket else iwd
    lean = f"{card['lean']}?  " if "lean" in card else ""
    leaning_rare = card.get("lean") == "standout" and card["rarity"] in {
        "rare",
        "mythic",
    }
    mark = "*" if leaning_rare else " "
    return (
        f" {mark}{iwd:>{13 if ranged else 7}}  {lean}{_label(card, code)}"
        f"  vs avg {_signed(card['vs_average'])}{pm},"
        f" {card['gih']} drawn  ({_per_event(card['events'], 'gih', ranged=ranged)})"
        f"{_review_note(card)}"
    )


def _one_sided(confidence: float) -> float:
    """The one-sided level of a two-sided *confidence* range: a label tests one
    end only, so a 90% range is a 95% call."""
    return 50.0 + confidence / 2.0


def _reviewer_bomb_line(card: dict, code: str) -> str:
    data = (
        f"[{_signed(card['iwd'])}], {card['gih']} drawn"
        if card["gih"]
        else "no stats under this name"
    )
    return (
        f"  {card['review_mean']:>5.1f}  {card['name']}{_set_note(card, code)}"
        f" [{card['rarity']}]  {card['review_sources']} reviewers  ({data})"
    )


def _leaning_lines(leaning: list[dict], code: str, margin: float) -> list[str]:
    """The leaning list, leaning standouts first, then leaning underperformers."""
    lines = [
        "",
        (
            f"## Leaning (the estimate clears {margin:g} points, the range reaches"
            " back inside: not a label)"
        ),
    ]
    for lean, title in (
        (
            "standout",
            (
                "leaning standouts (* rare / mythic: a bomb only if reviewers"
                " grade it one)"
            ),
        ),
        ("underperformer", "leaning underperformers"),
    ):
        group = [c for c in leaning if c["lean"] == lean]
        if group:
            lines.append(f"  {title}:")
            lines.extend(_card_line(c, code, ranged=True) for c in group)
    if not leaning:
        lines.append("  none")
    return lines


def render_pooled(pooled: dict, set_code: str) -> str:
    code = set_code.upper()
    th = pooled["thresholds"]
    # Confidence 0 is the point estimate alone: the text is the one before the
    # range existed (no ± on the cards, no leaning list, the old headings).
    ranged = th["confidence"] > 0
    lines = [
        f"# {code} pooled — {' + '.join(pooled['events'])} (Untapped.gg)",
        "Each pair and card is measured against its own format's average, then",
        "pooled across the formats by games.",
    ]
    if ranged:
        lines.append(
            f"A card's ± is a two-sided {th['confidence']:g}% range of its IWD (and"
            " of its lift over the average card). A label needs the cautious end"
            f" of it to clear {th['margin']:g} points, and tests that one end"
            f" only: a one-sided {_one_sided(th['confidence']):g}% call."
        )
    lines += ["", "## Formats"]
    for event, f in pooled["formats"].items():
        lines.append(
            f"  {event}: {f['source']}, fetched {f['fetched_at']}, {f['games']} games;"
            f" average pair {_fmt(f['average_pair'])},"
            f" average card IWD {_signed(f['average_iwd'])}"
            + (
                "; not drawn = games - drawn (free tier: the IWD and its ± count"
                " a sideboard game as not drawn)"
                if ranged and f["not_drawn"] == "derived"
                else ""
            )
        )
    for event, reason in pooled["missing"].items():
        lines.append(f"  {event}: missing ({reason})")
    lines += [
        "",
        (
            f"## Colour pairs (vs the average pair; tiers at ±{th['tier_gap']:g}"
            + ("; a pair's ± is one rough sigma)" if ranged else ")")
        ),
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
    at_end = " at the low end of its range" if ranged else ""
    sections = (
        (
            (
                f"## Standouts (IWD {th['margin']:g}+ over the average card{at_end},"
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
            (
                f"## Underperformers (IWD {th['margin']:g}+ under the average card"
                + (" at the high end of its range)" if ranged else ")")
            ),
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
        lines.extend(_card_line(c, code, bracket=bracket, ranged=ranged) for c in cards)
        if not cards:
            lines.append("  none")
        if ranged and heading.startswith("## Underperformers"):
            lines += _leaning_lines(pooled["leaning"], code, th["margin"])
    if "reviewer_bombs" in pooled:
        lines += [
            "",
            (
                f"## Reviewer bombs (rares / mythics under {th['pool_min_games']}"
                f" drawn that reviewers average {REVIEWER_BOMB_MEAN:g}+;"
                " chunk.science)"
            ),
        ]
        lines.extend(_reviewer_bomb_line(c, code) for c in pooled["reviewer_bombs"])
        if not pooled["reviewer_bombs"]:
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
@click.option(
    "--confidence",
    default=DEFAULT_CONFIDENCE,
    show_default=True,
    type=click.FloatRange(min=0, max=100, max_open=True),
    help=(
        "Pooled view: the two-sided percent confidence of each card's ± range; a"
        " standout / underperformer needs the range's cautious end past --margin,"
        " so a label is a one-sided call at 50 + confidence/2 (90 -> 95%). 0 ="
        " the point estimate alone."
    ),
)
@click.option(
    "--reviews",
    "with_reviews",
    is_flag=True,
    help=(
        "Pooled view: fetch chunk.science's reviewer grades (cached 24 h), put"
        " the average on each thin rare and list the reviewer bombs."
    ),
)
@click.option(
    "--reviews-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A saved chunk.science data/<code>.<hash>.js script, instead of fetching.",
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
    confidence: float,
    with_reviews: bool,  # noqa: FBT001 — a click flag
    reviews_json: Path | None,
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
        if with_reviews or reviews_json:
            raise click.UsageError(
                "--reviews / --reviews-json are for the pooled view; drop --event"
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
    reviews = None
    if reviews_json is not None:
        try:
            reviews = parse_reviews(reviews_json.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise click.ClickException(f"{reviews_json}: {exc}") from exc
    elif with_reviews:
        reviews, _fetched = fetch_reviews(set_code)
    pooled = build_pooled(
        reports,
        missing=missing,
        min_games=min_games,
        pool_min_games=pool_min_games,
        margin=margin,
        tier_gap=tier_gap,
        clash=clash,
        confidence=confidence,
        reviews=reviews,
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
