"""Untapped.gg MTG Arena limited card stats, turned into guide-ready numbers.

    limited-stats --set FRA [--event PREMIER_DRAFT] [--premium-json PATH]
                  [--min-games 30] [--json]

Untapped.gg publishes per-card limited stats for every Arena set, keyed by the
card's Arena **titleId** (not its grpid), split by deck archetype (a WUBRG
colour bitmask, plus ``ALL``) and by rank bucket. This module reads that
payload and computes the numbers a set guide quotes: each card's games-in-hand
win rate (GIH WR), not-drawn win rate (GNS WR) and the improvement when drawn
(IWD), card-weighted colour-pair win rates, the best commons per colour, bomb
candidates and hyped-but-losing rares.

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
import statistics
from datetime import UTC, datetime
from pathlib import Path

import click
import requests

from mtg_utils._http import BROWSER_HEADERS, HttpFetcher, cache_root, is_fresh
from mtg_utils._sidecar import atomic_write_bytes
from mtg_utils.arena_card_db import _title

API_URL = (
    "https://api.mtga.untapped.gg/api/v1/analytics/query/card_stats_limited_by_set"
)
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
            names[key] = _title(None, str(entry.get("text", ""))) or ""
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
            params={"CardSetFilter": set_code, "LimitedEventTypeFilter": event},
            headers=HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 204 or not resp.content.strip():
            raise click.ClickException(f"no Untapped data yet for {set_code}/{event}")
        if resp.status_code >= 400:
            raise _rejected(set_code, event, _server_message(resp))
        payload = _check_data(resp.json(), set_code, event)
        atomic_write_bytes(path, resp.content)  # never an empty or error answer
        return payload, _mtime_iso(path)
    return json.loads(path.read_text(encoding="utf-8")), _mtime_iso(path)


def fetch_card_index(set_code: str, title_ids: set[str]) -> dict[str, dict]:
    """titleId -> name / rarity / colours / set from the cached mtgajson files."""
    fetcher = HttpFetcher(
        cache_dir(),
        user_agent=BROWSER_HEADERS["User-Agent"],
        max_age_seconds=_CACHE_SECONDS,
    )
    cards = json.loads(fetcher.fetch(CARDS_URL, "cards.json"))
    loc = json.loads(fetcher.fetch(LOC_URL, "loc_en.json"))
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


# --- CLI -------------------------------------------------------------------------


@click.command()
@click.option("--set", "set_code", required=True, help="Arena set code, e.g. FRA.")
@click.option(
    "--event",
    default="PREMIER_DRAFT",
    show_default=True,
    help=f"Untapped limited event type ({_EXAMPLE_EVENTS}).",
)
@click.option(
    "--premium-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="A saved card_stats_limited_by_set payload (e.g. the premium one).",
)
@click.option(
    "--min-games",
    default=30,
    show_default=True,
    type=click.IntRange(min=1),
    help="GIH floor for a full-sample stat.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the full structure.")
def main(
    set_code: str,
    event: str,
    premium_json: Path | None,
    min_games: int,
    as_json: bool,  # noqa: FBT001 — a click flag
) -> None:
    """Untapped.gg limited card stats for SET as guide-ready numbers."""
    if premium_json is not None:
        raw = json.loads(premium_json.read_text(encoding="utf-8"))
        payload = _check_data(raw, set_code, event)
        source = payload_source(payload)
        fetched_at = _mtime_iso(premium_json)
    else:
        payload, fetched_at = fetch_card_stats(set_code, event)
        source = "free"
    index = fetch_card_index(set_code, set(payload["data"]))
    report = build_report(
        payload,
        index,
        set_code=set_code,
        event=event.upper(),
        source=source,
        fetched_at=fetched_at,
        min_games=min_games,
    )
    click.echo(json.dumps(report, indent=2) if as_json else render_text(report))
