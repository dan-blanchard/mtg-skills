"""Limited readouts: what a set holds, and what a pool supports in each colour pair.

Two pure, deterministic functions over card records — no agent, no network — plus
their CLIs. ``set_scan`` answers the question a sealed builder keeps guessing at
from the 67 cards they opened instead of the 250 their opponents draw from: how
much removal the set has and at which rarity, its sweepers, how many evasive
bodies, and the biggest creatures an answer has to handle. ``pool_color_pairs``
enumerates every colour pair (and mono colour) a pool supports — playables,
creatures, removal, evasion, big bodies, rares — before any opinion is formed,
so the pair a build commits to is chosen against the alternatives on equal footing
(docs/plans/limited-sealed-support.md).

Removal and sweepers are the template roles (``_analysis.roles.role_of`` — a view
over the signal path, ADR-0051); evasion is the record's keywords
(``card_classify.EVASION_KEYWORDS``); bodies are printed power / toughness.

    set-scan --set HOB [--bulk-data PATH] [--json]
    pool-colors <deck.json> [--bulk-data PATH] [--json]
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from itertools import combinations
from pathlib import Path

import click

from mtg_utils._analysis.roles import role_of
from mtg_utils.card_classify import (
    EVASION_KEYWORDS,
    card_pt_int,
    has_evasion,
    is_creature,
    is_land,
)
from mtg_utils.card_pool import CardPool
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option, resolve_bulk_path

_COLORS = "WUBRG"
_RARITIES = ("common", "uncommon", "rare", "mythic")
_BIG_TOUGHNESS = 6
_BIG_POWER = 4
_TOP_BODIES = 10


def _curve_bucket(cmc: float) -> str:
    return "7+" if cmc >= 7 else str(int(cmc))


def set_scan(records: Sequence[dict], *, code: str | None = None) -> dict:
    """The readout over one set's records (one per distinct card)."""
    by_rarity: dict[str, int] = dict.fromkeys(_RARITIES, 0)
    removal: list[dict] = []
    removal_by_rarity: dict[str, int] = dict.fromkeys(_RARITIES, 0)
    sweepers: list[str] = []
    evasion_by_keyword: dict[str, int] = {}
    creatures: list[dict] = []
    curve: dict[str, int] = {}
    for rec in records:
        rarity = rec.get("rarity") or "unknown"  # never inflate a real bucket
        by_rarity[rarity] = by_rarity.get(rarity, 0) + 1
        roles = role_of(rec)
        if "interaction" in roles:
            removal.append(rec)
            removal_by_rarity[rarity] = removal_by_rarity.get(rarity, 0) + 1
        if "board_wipe" in roles:
            sweepers.append(rec.get("name", ""))
        if is_creature(rec):
            creatures.append(rec)
            for kw in rec.get("keywords") or []:
                if kw in EVASION_KEYWORDS:
                    evasion_by_keyword[kw] = evasion_by_keyword.get(kw, 0) + 1
        if not is_land(rec):
            bucket = _curve_bucket(float(rec.get("cmc", 0.0) or 0.0))
            curve[bucket] = curve.get(bucket, 0) + 1

    def body(rec: dict) -> dict:
        return {
            "name": rec.get("name", ""),
            "power": card_pt_int(rec, "power"),
            "toughness": card_pt_int(rec, "toughness"),
            "rarity": rec.get("rarity", ""),
            "cmc": rec.get("cmc", 0.0),
        }

    by_toughness = sorted(
        creatures,
        key=lambda r: (-card_pt_int(r, "toughness"), -card_pt_int(r, "power")),
    )
    by_power = sorted(
        creatures,
        key=lambda r: (-card_pt_int(r, "power"), -card_pt_int(r, "toughness")),
    )
    return {
        "code": (code or "").upper() or None,
        "size": len(records),
        "by_rarity": by_rarity,
        "creatures": len(creatures),
        "removal": {
            "total": len(removal),
            "by_rarity": removal_by_rarity,
            "cards": sorted(r.get("name", "") for r in removal),
        },
        "sweepers": sorted(sweepers),
        "evasion": {
            "total": sum(1 for r in creatures if has_evasion(r)),
            "by_keyword": dict(sorted(evasion_by_keyword.items())),
        },
        "biggest_bodies": {
            "by_toughness": [body(r) for r in by_toughness[:_TOP_BODIES]],
            "by_power": [body(r) for r in by_power[:_TOP_BODIES]],
        },
        "toughness_6_plus": sum(
            1 for r in creatures if card_pt_int(r, "toughness") >= _BIG_TOUGHNESS
        ),
        "curve": dict(sorted(curve.items(), key=lambda kv: (len(kv[0]), kv[0]))),
    }


def _pairs() -> list[str]:
    return [*list(_COLORS), *("".join(p) for p in combinations(_COLORS, 2))]


def pool_color_pairs(records_with_qty: Iterable[tuple[dict, int]]) -> list[dict]:
    """Every mono colour and colour pair a pool supports, quantity-aware: a card
    counts toward a pair when its colour identity fits in it (a colourless card fits
    every pair, so it lifts every row equally and never changes the ranking).
    ``removal`` counts sweepers too (``interaction`` or ``board_wipe``): in limited a
    sweeper is an answer like any other, where ``set_scan`` lists sweepers apart.
    Rows sort by playables (nonland cards) then removal, descending."""
    pool = [(rec, int(qty)) for rec, qty in records_with_qty]
    rows: list[dict] = []
    for pair in _pairs():
        allowed = set(pair)
        playables = creatures = removal = evasion = power4 = rares = 0
        cmc_total = 0.0
        for rec, qty in pool:
            if is_land(rec):
                continue
            if not set(rec.get("color_identity") or []) <= allowed:
                continue
            playables += qty
            cmc_total += float(rec.get("cmc", 0.0) or 0.0) * qty
            roles = role_of(rec)
            if "interaction" in roles or "board_wipe" in roles:
                removal += qty
            if is_creature(rec):
                creatures += qty
                if has_evasion(rec):
                    evasion += qty
                if card_pt_int(rec, "power") >= _BIG_POWER:
                    power4 += qty
            if (rec.get("rarity") or "") in ("rare", "mythic"):
                rares += qty
        rows.append(
            {
                "pair": pair,
                "playables": playables,
                "creatures": creatures,
                "removal": removal,
                "evasion": evasion,
                "power_4_plus": power4,
                "rares": rares,
                "avg_cmc": round(cmc_total / playables, 2) if playables else 0.0,
            }
        )
    rows.sort(key=lambda r: (-r["playables"], -r["removal"], r["pair"]))
    return rows


def _counts(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in d.items() if v)


def render_set_scan(scan: dict) -> str:
    removal = scan["removal"]
    evasion = scan["evasion"]
    bodies = scan["biggest_bodies"]["by_toughness"][:5]
    lines = [
        (
            f"set-scan: {scan.get('code') or '?'} — {scan['size']} cards "
            f"({_counts(scan['by_rarity'])})"
        ),
        (
            f"Creatures: {scan['creatures']}  Evasive: {evasion['total']} "
            f"({_counts(evasion['by_keyword'])})"
        ),
        f"Removal: {removal['total']} ({_counts(removal['by_rarity'])})",
        f"Sweepers: {', '.join(scan['sweepers']) or 'none'}",
        f"Toughness 6+: {scan['toughness_6_plus']}",
        "Biggest bodies (by toughness): "
        + ", ".join(f"{b['name']} {b['power']}/{b['toughness']}" for b in bodies),
    ]
    return "\n".join(lines) + "\n"


def render_color_pairs(rows: list[dict]) -> str:
    header = (
        f"{'pair':5} {'play':>4} {'crea':>4} {'rmvl':>4} {'evas':>4} {'p4+':>4} "
        f"{'rare':>4} {'avg':>5}"
    )
    lines = [header]
    lines.extend(
        f"{r['pair']:5} {r['playables']:>4} {r['creatures']:>4} {r['removal']:>4} "
        f"{r['evasion']:>4} {r['power_4_plus']:>4} {r['rares']:>4} {r['avg_cmc']:>5}"
        for r in rows
    )
    return "\n".join(lines) + "\n"


@click.command("set-scan")
@click.option("--set", "set_code", required=True, help="The set code (e.g. HOB).")
@bulk_data_option
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of text.")
def set_scan_main(set_code: str, bulk_data: Path | None, *, as_json: bool) -> None:
    """What set SET holds: removal by rarity, sweepers, evasion, the biggest bodies."""
    pool = CardPool.load(resolve_bulk_path(bulk_data))
    records = pool.set_records(set_code)
    if not records:
        raise click.ClickException(f"no cards found for set {set_code!r}")
    scan = set_scan(records, code=set_code)
    click.echo(json.dumps(scan, indent=2) if as_json else render_set_scan(scan))


@click.command("pool-colors")
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def pool_colors_main(deck_json: Path, bulk_data: Path | None, *, as_json: bool) -> None:
    """Every colour pair DECK_JSON's opened pool supports, on equal footing."""
    hd = acquire_for_cli(deck_json, bulk_data)
    if not hd.format.pool_bounded:
        raise click.ClickException(
            f"{hd.format.name} has no pool — pool-colors reads a sealed / draft deck"
        )
    rows = pool_color_pairs(hd.deck_quantities(zones=("pool",)))
    click.echo(json.dumps(rows, indent=2) if as_json else render_color_pairs(rows))
