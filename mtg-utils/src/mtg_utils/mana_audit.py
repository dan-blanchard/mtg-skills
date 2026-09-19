"""Mana base audit: land count and color balance analysis."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import click

from mtg_utils._analysis.roles import is_ramp
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    color_sources,
    count_color_pips,
    is_land,
)
from mtg_utils.commander_cost import effective_commander_cost
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.hydrated_deck import HydratedDeck, sidecar_path

# Constructed mana base constants (60-card formats)
_CONSTRUCTED_BASELINE_LANDS = 24
_CONSTRUCTED_NEUTRAL_CMC = 3.0
_CONSTRUCTED_MAX_CURVE_ADJ = 2
_CONSTRUCTED_MIN_LANDS = 20
_CONSTRUCTED_MAX_LANDS = 27
_CONSTRUCTED_FAIL_TOLERANCE = 2
# Limited mana base constants (40-card sealed / draft): 17 of 40 is the norm every
# primer agrees on, one fewer for a low curve or real land-fetch ramp, one more for
# a top-heavy pool — a tight band, not the constructed formula scaled down (which
# would call the 17-land default over-landed).
_LIMITED_BASELINE_LANDS = 17
_LIMITED_LOW_CMC = 2.5
_LIMITED_HIGH_CMC = 3.5
_LIMITED_RAMP_FOR_CUT = 3
_LIMITED_MIN_LANDS = 16
_LIMITED_MAX_LANDS = 18
# The flood line sits this far above the band's top (deck-forge CONTEXT: Flood line).
FLOOD_MARGIN = 2


def burgess_formula(*, colors: int, commander_cmc: int, deck_size: int = 100) -> int:
    """Return Burgess recommended land count, scaled to deck size."""
    base = 31 + colors + commander_cmc
    return round(base * deck_size / 100)


def karsten_adjustment(*, ramp_count: int, deck_size: int = 100) -> int:
    """Return Karsten-adjusted land count, scaled to deck size."""
    base = max(36, 42 - math.floor(ramp_count / 2.5))
    return round(base * deck_size / 100)


def land_band(
    *, colors: int, commander_cmc: int, ramp_count: int, deck_size: int = 100
) -> tuple[int, int]:
    """Return the deck-specific land band (floor, top) for a commander-family
    deck (ADR-0041).

    ``floor`` is the lower of raw Burgess and the Karsten ramp adjustment;
    ``top`` is the higher, a comfortable-maximum reference — never a failure
    line. Burgess (colors + commander CMC) and Karsten (ramp count) each
    capture a fact the other ignores, so treating either alone as a hard
    floor produces contradictory verdicts on a deck where they disagree (a
    high-color/high-CMC, heavy-ramp deck can push raw Burgess above the
    Karsten-adjusted count, and a light-ramp deck can do the reverse)."""
    burgess = burgess_formula(
        colors=colors, commander_cmc=commander_cmc, deck_size=deck_size
    )
    karsten = karsten_adjustment(ramp_count=ramp_count, deck_size=deck_size)
    return (min(burgess, karsten), max(burgess, karsten))


def limited_land_target(*, ramp_count: int, avg_cmc: float, deck_size: int = 40) -> int:
    """The limited land target: 17 per 40, minus one for a low curve (avg MV < 2.5)
    or for real ramp (three or more land-fetch / mana producers — the ADR-0051 ramp
    read, which already counts a land put onto the battlefield), plus one for a high
    curve (avg MV > 3.5), clamped to 16-18 and scaled to the deck's size."""
    base = _LIMITED_BASELINE_LANDS
    if (
        avg_cmc > 0 and avg_cmc < _LIMITED_LOW_CMC
    ) or ramp_count >= _LIMITED_RAMP_FOR_CUT:
        base -= 1
    elif avg_cmc > _LIMITED_HIGH_CMC:
        base += 1
    base = max(_LIMITED_MIN_LANDS, min(_LIMITED_MAX_LANDS, base))
    return round(base * deck_size / 40)


def land_band_readout(
    *, land_count: int, floor: int, top: int, warn_below_top: bool
) -> dict:
    """The ONE land-band readout every surface reads (ADR-0041, finished):
    ``{floor, top, flood, count, status}``.

    ``floor`` is the hard gate — ``FAIL`` only below it. ``top`` is the target /
    comfortable maximum; ``flood`` is ``top + FLOOD_MARGIN``, above which the deck
    is over-landed and the status is the advisory ``FLOOD`` (never a gate — an
    all-lands combo deck is a legitimate build). Between floor and top a
    Commander-family deck is ``PASS`` (the top is a reference, not a line) while
    60-card constructed reads ``WARN`` (``warn_below_top``): the recommended count
    is a target it is a little short of. Only ``FAIL`` gates anything downstream."""
    flood = top + FLOOD_MARGIN
    if land_count < floor:
        status = "FAIL"
    elif warn_below_top and land_count < top:
        status = "WARN"
    elif land_count > flood:
        status = "FLOOD"
    else:
        status = "PASS"
    return {
        "floor": floor,
        "top": top,
        "flood": flood,
        "count": land_count,
        "status": status,
    }


def constructed_land_target(
    *,
    ramp_count: int,
    avg_cmc: float,
    deck_size: int = 60,
) -> int:
    """Return recommended land count for 60-card constructed formats.

    Baseline is 24 lands (for a 60-card deck), adjusted down by ramp
    and by curve profile. Aggressive decks (avg CMC < 2.5) can go lower;
    control decks (avg CMC > 3.5) want more. Result is clamped to [20, 27]
    and scaled proportionally if deck_size differs from 60.
    """
    base = _CONSTRUCTED_BASELINE_LANDS - math.floor(ramp_count / 2)
    if avg_cmc > 0:
        curve_adj = round(avg_cmc - _CONSTRUCTED_NEUTRAL_CMC)
        cap = _CONSTRUCTED_MAX_CURVE_ADJ
        base += max(-cap, min(cap, curve_adj))
    base = max(_CONSTRUCTED_MIN_LANDS, min(_CONSTRUCTED_MAX_LANDS, base))
    return round(base * deck_size / 60)


def _mana_cost_for_pips(card: dict) -> str:
    """The mana-cost string to scan for colored pips.

    Modal DFCs (e.g. Malakir Rebirth // Malakir Mire) carry no top-level
    ``mana_cost`` — Scryfall puts the costs on ``card_faces`` — so reading only the
    top-level field silently drops their colored pips. Fall back to the faces in that
    case. Normal/split/transform/adventure cards keep a truthy top-level cost and are
    unaffected (split's combined "{1}{R} // {1}{U}" already carries both halves' pips).
    """
    mana_cost = card.get("mana_cost")
    if mana_cost:
        return mana_cost
    faces = card.get("card_faces") or []
    return " ".join(f.get("mana_cost") or "" for f in faces)


def pip_demand(cards: list[dict]) -> dict[str, int]:
    """Count colored pips (W, U, B, R, G) across all card mana costs."""
    counts: dict[str, int] = {}
    for card in cards:
        for color, n in count_color_pips(_mana_cost_for_pips(card)).items():
            counts[color] = counts.get(color, 0) + n
    return dict(sorted(counts.items()))


def color_balance(
    pips: dict[str, int], land_colors: dict[str, int], total_lands: int
) -> dict:
    """Evaluate whether land color production matches pip demand."""
    if not pips or total_lands == 0:
        return {"status": "PASS", "flags": []}

    total_pips = sum(pips.values())
    flags: list[str] = []
    worst_deficit = 0.0

    for color, pip_count in pips.items():
        pip_pct = pip_count / total_pips * 100
        land_count = land_colors.get(color, 0)
        land_pct = land_count / total_lands * 100
        deficit = pip_pct - land_pct
        worst_deficit = max(worst_deficit, deficit)
        if deficit > 5:
            flags.append(
                f"{color}: needs {pip_pct:.1f}% but only {land_pct:.1f}%"
                f" of lands produce it (deficit {deficit:.1f}pp)"
            )

    if worst_deficit > 10:
        status = "FAIL"
    elif worst_deficit > 5:
        status = "WARN"
    else:
        status = "PASS"
        flags = []

    return {"status": status, "flags": flags}


# Color → its basic land. "C" (colorless) → Wastes, for an Eldrazi/colorless deck.
_BASIC_FOR_COLOR = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
    "C": "Wastes",
}


def allocate_basic_lands(
    shortfall: int,
    recommended: int,
    pips: dict[str, int],
    production: dict[str, int],
    fallback_colors: list[str] | None = None,
) -> dict[str, int]:
    """Distribute ``shortfall`` basic lands across colors to best pass the mana gate.

    Water-fills toward the deck's pip demand against what existing lands already
    produce: each color's target production is ``recommended * pip%``; the shortfall is
    allocated proportional to each color's remaining deficit (so an over-produced color
    gets nothing), with largest-remainder rounding so the counts sum exactly to
    ``shortfall``. Falls back to pip demand if the base is already balanced, to the
    commander's color identity when there are no pips yet, and to Wastes for a truly
    colorless deck. Returns {basic-land name: count to add}."""
    if shortfall <= 0:
        return {}
    weights_base = dict(pips) if pips else dict.fromkeys(fallback_colors or [], 1)
    colors = [c for c in weights_base if c in _BASIC_FOR_COLOR]
    if not colors:
        return {_BASIC_FOR_COLOR["C"]: shortfall}

    total = sum(weights_base[c] for c in colors)
    target = {c: recommended * weights_base[c] / total for c in colors}
    deficit = {c: max(0.0, target[c] - production.get(c, 0)) for c in colors}
    balanced = sum(deficit.values()) <= 1e-9
    weights = {c: weights_base[c] for c in colors} if balanced else deficit
    wsum = sum(weights.values()) or 1.0

    raw = {c: shortfall * weights[c] / wsum for c in colors}
    alloc = {c: int(raw[c]) for c in colors}
    remainder = shortfall - sum(alloc.values())
    for c in sorted(colors, key=lambda c: raw[c] - alloc[c], reverse=True)[:remainder]:
        alloc[c] += 1
    return {_BASIC_FOR_COLOR[c]: alloc[c] for c in colors if alloc[c] > 0}


_BASIC_NAMES = frozenset(_BASIC_FOR_COLOR.values())
_COLOR_FOR_BASIC = {name: color for color, name in _BASIC_FOR_COLOR.items()}


def reconcile_basic_lands(
    hd: HydratedDeck, *, target_total: int | None = None
) -> dict[str, dict[str, int]]:
    """Plan the basic-land changes that move the mana base to a target land count,
    returning ``{"add": {name: qty}, "remove": {name: qty}}``.

    With ``target_total=None`` (default) the target is the FAIL FLOOR clamped to never
    drop below the current count — so it tops a short deck up to the floor AND
    rebalances the basics of a deck already at/above it (swapping over- for
    under-produced colors, net-zero count). Pass an explicit ``target_total`` to aim
    elsewhere: the 'Trim lands' FLOOD remedy passes the band's *top*, below the
    current one, so the same color-demand allocation removes the over-produced basics
    down to target. Only the standard basics are managed; nonbasic lands (duals, fixing,
    snow basics) are treated as fixed production the basics fill in around — so a deck
    whose nonbasics alone exceed the target trims every basic and stops there."""
    audit = mana_audit(hd)
    land_count = audit["land_count"]
    if target_total is None:
        target_total = max(land_count, audit["land_band"]["floor"])

    current: dict[str, int] = {}
    for entry in hd.cards:
        color = _COLOR_FOR_BASIC.get(entry["name"])
        if color:
            current[color] = current.get(color, 0) + entry["quantity"]

    nonbasic_count = land_count - sum(current.values())
    desired_basic_total = max(0, target_total - nonbasic_count)
    production = audit["land_color_production"]
    nonbasic_prod = {
        c: production.get(c, 0) - current.get(c, 0)
        for c in set(production) | set(current)
    }

    ci: set[str] = set()
    for entry in hd.commanders:
        cmd_name = entry.get("name")
        record = hd.by_name.get(cmd_name) if isinstance(cmd_name, str) else None
        if record:
            ci.update(record.get("color_identity") or [])

    desired_named = allocate_basic_lands(
        desired_basic_total,
        target_total,
        audit["pip_demand"],
        nonbasic_prod,
        fallback_colors=sorted(ci),
    )
    desired = {_COLOR_FOR_BASIC[name]: qty for name, qty in desired_named.items()}

    add: dict[str, int] = {}
    remove: dict[str, int] = {}
    for color in set(current) | set(desired):
        delta = desired.get(color, 0) - current.get(color, 0)
        name = _BASIC_FOR_COLOR[color]
        if delta > 0:
            add[name] = delta
        elif delta < 0:
            remove[name] = -delta
    return {"add": add, "remove": remove}


def _add_color_sources(
    colors_dict: dict[str, int], card_color_srcs: set[str], qty: int
) -> None:
    """Add qty to each color in colors_dict based on card_color_srcs."""
    if "any" in card_color_srcs:
        for c in "WUBRG":
            colors_dict[c] = colors_dict.get(c, 0) + qty
    else:
        for c in card_color_srcs:
            if c != "C":
                colors_dict[c] = colors_dict.get(c, 0) + qty


def _commander_stats(
    commanders: list[dict],
    card_lookup: Mapping[str, dict],
    deck_entries: Sequence[tuple[Mapping, int]] = (),
    *,
    library_size: int = 99,
) -> tuple[int, int, dict]:
    """Return ``(commander_cost, color_count, commander_cost_block)``.

    ``commander_cost`` is the ADR-0044 **effective commander cost** — the
    affordable turn for a self-discounting commander, the printed mana value
    otherwise — taken as the max across partners (the same rule the printed
    value used). The block carries every commander's per-turn table and status
    so the degrade to printed mana value is always visible, never silent.
    """
    color_identity: set[str] = set()
    blocks: list[dict] = []
    for cmd_entry in commanders:
        card = card_lookup.get(cmd_entry["name"])
        if card is None:
            continue
        color_identity.update(card.get("color_identity", []))
        blocks.append(
            effective_commander_cost(card, deck_entries, library_size=library_size)
        )
    used = max((b["effective"] for b in blocks), default=0)
    printed = max((b["printed"] for b in blocks), default=0)
    block = {"used": used, "printed": printed, "commanders": blocks}
    return (used, len(color_identity), block)


def _scan_entries(
    all_entries: list[dict], card_lookup: Mapping[str, dict]
) -> tuple[int, int, list[float], list[dict], dict[str, int], dict[str, int]]:
    """Scan all entries and return (land_count, ramp_count, nonland_cmcs,
    pip_cards, land_color_production, rock_colors)."""
    land_count = 0
    ramp_count = 0
    nonland_cmcs: list[float] = []
    pip_cards: list[dict] = []
    land_color_production: dict[str, int] = {}
    rock_colors: dict[str, int] = {}

    for entry in all_entries:
        qty = entry.get("quantity", 1)
        card = card_lookup.get(entry["name"])
        if card is None:
            continue

        if is_land(card):
            land_count += qty
            _add_color_sources(land_color_production, color_sources(card), qty)
        else:
            nonland_cmcs.extend([card.get("cmc", 0.0)] * qty)
            pip_cards.extend([card] * qty)

        if is_ramp(card):
            ramp_count += qty
            if not is_land(card):
                _add_color_sources(rock_colors, color_sources(card), qty)

    return (
        land_count,
        ramp_count,
        nonland_cmcs,
        pip_cards,
        land_color_production,
        rock_colors,
    )


def _pct_dict(counts: dict[str, int], total: int) -> dict[str, float]:
    """Convert a counts dict to percentage dict (sorted)."""
    if not total:
        return {}
    return {c: round(v / total * 100, 1) for c, v in sorted(counts.items())}


def _overall_status(statuses: list[str]) -> str:
    """Return worst status from a list of PASS/WARN/FAIL values."""
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def mana_audit(hd: HydratedDeck) -> dict:
    """Run a full mana base audit on the deck."""
    card_lookup = hd.by_name

    # ``hd.format`` already carries the deck's explicit size (a 60-card paper Historic
    # Brawl, an 80-card Yorion deck, a 40-card limited pool) so the Burgess/Karsten/
    # constructed land math scales to the real size.
    deck_size = hd.format.deck_size
    has_commander = hd.format.has_commander

    commanders = hd.commanders
    # Only analyze mainboard cards (sideboard doesn't affect mana base)
    all_entries = list(commanders) + list(hd.cards)

    deck_entries = [
        (card_lookup[e["name"]], int(e.get("quantity", 1)))
        for e in hd.cards
        if e["name"] in card_lookup
    ]
    commander_cmc, colors, commander_cost = _commander_stats(
        commanders,
        card_lookup,
        deck_entries,
        library_size=max(1, deck_size - len(commanders)),
    )
    (
        land_count,
        ramp_count,
        nonland_cmcs,
        pip_cards,
        land_color_production,
        rock_colors,
    ) = _scan_entries(all_entries, card_lookup)

    avg_cmc = round(sum(nonland_cmcs) / len(nonland_cmcs), 2) if nonland_cmcs else 0.0

    def commander_band() -> tuple[int, int, dict]:
        burgess_result = burgess_formula(
            colors=colors, commander_cmc=commander_cmc, deck_size=deck_size
        )
        karsten_result = karsten_adjustment(ramp_count=ramp_count, deck_size=deck_size)
        # ADR-0041: ONE deck-specific band — the lower of Karsten and raw
        # Burgess is the floor, the higher the top (see ``land_band``) —
        # replaces treating raw Burgess alone as the hard floor (which could
        # exceed the static template's ceiling on a heavy-ramp, high-color /
        # high-CMC deck with no land count able to satisfy both).
        floor, top = land_band(
            colors=colors,
            commander_cmc=commander_cmc,
            ramp_count=ramp_count,
            deck_size=deck_size,
        )
        return (
            floor,
            top,
            {
                "burgess_formula": {
                    "colors": colors,
                    # ADR-0044: the effective commander cost (affordable turn), which
                    # equals the printed mana value unless the commander's own
                    # cost-reduction operand was modelled — see ``commander_cost``.
                    "commander_cmc": commander_cmc,
                    "printed_cmc": commander_cost["printed"],
                    "result": burgess_result,
                },
                "commander_cost": commander_cost,
                "karsten_adjustment": {
                    "ramp_count": ramp_count,
                    "result": karsten_result,
                },
            },
        )

    def limited_band() -> tuple[int, int, dict]:
        # Sealed / draft: the 17-of-40 norm, a tight 16-18 band (ADR-0055) — the
        # floor never drops below the band's own minimum — never the constructed
        # formula scaled down (which reads 17 lands as over-landed).
        top = limited_land_target(
            ramp_count=ramp_count, avg_cmc=avg_cmc, deck_size=deck_size
        )
        floor = max(round(_LIMITED_MIN_LANDS * deck_size / 40), top - 1)
        return (
            floor,
            top,
            {
                "limited_land_target": {
                    "ramp_count": ramp_count,
                    "avg_cmc": avg_cmc,
                    "result": top,
                }
            },
        )

    def constructed_band() -> tuple[int, int, dict]:
        top = constructed_land_target(
            ramp_count=ramp_count, avg_cmc=avg_cmc, deck_size=deck_size
        )
        # The 20-land clamp is a 60-card figure; scale it like the target
        # so a deck labelled with a constructed format at another size isn't held
        # to a 60-card floor.
        min_lands = round(_CONSTRUCTED_MIN_LANDS * deck_size / 60)
        floor = max(min_lands, top - _CONSTRUCTED_FAIL_TOLERANCE)
        return (
            floor,
            top,
            {
                "constructed_land_target": {
                    "ramp_count": ramp_count,
                    "avg_cmc": avg_cmc,
                    "result": top,
                }
            },
        )

    # One band per family, dispatched the way the templates and calibrations are.
    bands = {
        "commander": commander_band,
        "limited": limited_band,
        "constructed": constructed_band,
    }
    floor, top, formula_info = bands[hd.format.family]()

    pips = pip_demand(pip_cards)
    total_pips = sum(pips.values())
    pip_demand_pct = (
        {c: round(v / total_pips * 100, 1) for c, v in pips.items()}
        if total_pips
        else {}
    )

    cb = color_balance(pips, land_color_production, land_count)
    # ONE band for every deck (Commander family AND constructed): the budgets row,
    # the gate, the flood line and the SPA readout all read this and nothing else.
    band = land_band_readout(
        land_count=land_count, floor=floor, top=top, warn_below_top=not has_commander
    )
    gate_status = "PASS" if band["status"] == "FLOOD" else band["status"]

    return {
        "land_count": land_count,
        "land_band": band,
        **formula_info,
        "ramp_count": ramp_count,
        "avg_cmc": avg_cmc,
        "pip_demand": pips,
        "pip_demand_pct": pip_demand_pct,
        "land_color_production": dict(sorted(land_color_production.items())),
        "land_color_pct": _pct_dict(land_color_production, land_count),
        "rock_color_pct": _pct_dict(rock_colors, sum(rock_colors.values())),
        "color_balance_status": cb["status"],
        "color_balance_flags": cb["flags"],
        "overall_status": _overall_status([gate_status, cb["status"]]),
    }


def _render_single_audit(audit: dict) -> list[str]:
    lines: list[str] = []
    status = audit.get("overall_status", "?")
    land_count = audit.get("land_count", 0)
    colors = set(audit.get("pip_demand") or {})
    colors_str = "".join(sorted(colors)) if colors else "C"
    lines.append(f"mana-audit: {status} — {land_count} lands ({colors_str} deck)")
    lines.append("")

    # A size-minimum family (constructed or limited) carries one target block; the
    # Commander family carries Burgess + Karsten.
    target_block = audit.get("constructed_land_target") or audit.get(
        "limited_land_target"
    )
    burgess = audit.get("burgess_formula") or {}
    band = audit.get("land_band") or {}
    if target_block:
        lines.append(
            f"Land count: {land_count} "
            f"(target: {band.get('top', '?')}, floor: {band.get('floor', '?')}, "
            f"flood: {band.get('flood', '?')}, status: {band.get('status', '?')})"
        )
    else:
        lines.append(
            f"Land count: {land_count} "
            f"(band: {band.get('floor', '?')}-{band.get('top', '?')}, "
            f"flood: {band.get('flood', '?')}, "
            f"Burgess: {burgess.get('result', '?')}, "
            f"Karsten: {audit.get('karsten_adjustment', {}).get('result', '?')}, "
            f"status: {band.get('status', '?')})"
        )
    for block in (audit.get("commander_cost") or {}).get("commanders", ()):
        if block.get("status") == "modelled":
            lines.append(
                f"Commander cost: {block.get('name')} printed {block.get('printed')}, "
                f"effective {block.get('effective')} (pays {block.get('residual')} on "
                f"turn {block.get('effective')}; {block.get('operand')}; "
                f"{block.get('assumptions')})"
            )
        elif block.get("status") != "none":
            lines.append(
                f"Commander cost: {block.get('name')} printed {block.get('printed')}, "
                f"used as-is — {block.get('status')}"
            )
    lines.append(f"Ramp count: {audit.get('ramp_count', 0)}")
    lines.append(f"Avg CMC: {audit.get('avg_cmc', 0)}")

    pip_demand_pct = audit.get("pip_demand_pct") or {}
    land_color_pct = audit.get("land_color_pct") or {}
    rock_color_pct = audit.get("rock_color_pct") or {}
    all_colors = sorted(set(pip_demand_pct) | set(land_color_pct) | set(rock_color_pct))
    if all_colors:
        lines.append("Color balance:")
        for c in all_colors:
            pd = pip_demand_pct.get(c, 0)
            lp = land_color_pct.get(c, 0)
            rp = rock_color_pct.get(c, 0)
            lines.append(
                f"  {c}: pip demand={pd}%, land production={lp}%, rock production={rp}%"
            )
    cb_status = audit.get("color_balance_status", "?")
    cb_flags = audit.get("color_balance_flags") or []
    lines.append(f"Color balance status: {cb_status}")
    if cb_flags:
        lines.extend(f"  ! {flag}" for flag in cb_flags)
    return lines


def render_text_report(result: dict) -> str:
    """Render mana_audit() output as a human-readable text report."""
    if "primary" in result and "comparison" in result:
        # --compare mode
        primary = result["primary"]
        comparison = result["comparison"]
        delta = result.get("delta", {})
        lines: list[str] = []
        lines.append(
            f"mana-audit --compare: {primary.get('source', 'primary')} "
            f"vs {comparison.get('source', 'comparison')}"
        )
        lines.append("")
        lines.append("--- Primary ---")
        lines.extend(_render_single_audit(primary))
        lines.append("")
        lines.append("--- Comparison ---")
        lines.extend(_render_single_audit(comparison))
        lines.append("")
        lines.append(
            f"Delta: land_count={delta.get('land_count', 0):+d}, "
            f"avg_cmc={delta.get('avg_cmc', 0):+.2f}, "
            f"ramp_count={delta.get('ramp_count', 0):+d}"
        )
        return "\n".join(lines) + "\n"

    return "\n".join(_render_single_audit(result)) + "\n"


def _default_output_path(*args: object) -> Path:
    return sha_keyed_path("mana-audit", *args)


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option(
    "--compare",
    type=click.Path(exists=True, path_type=Path),
    metavar="<new-deck-json>",
    default=None,
    help="Compare against another deck version.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(
    deck_path: Path,
    bulk_data: Path | None,
    compare: Path | None,
    output_path: Path | None,
) -> None:
    """Audit DECK_PATH's mana base for land count and color balance."""
    hd = acquire_for_cli(deck_path, bulk_data)

    if compare:
        new_deck_path = compare
        primary = mana_audit(hd)
        primary["source"] = deck_path.name
        comparison = mana_audit(acquire_for_cli(new_deck_path, bulk_data))
        comparison["source"] = new_deck_path.name

        result = {
            "primary": primary,
            "comparison": comparison,
            "delta": {
                "land_count": comparison["land_count"] - primary["land_count"],
                "avg_cmc": round(comparison["avg_cmc"] - primary["avg_cmc"], 2),
                "ramp_count": comparison["ramp_count"] - primary["ramp_count"],
            },
        }
        if output_path is None:
            output_path = _default_output_path(
                deck_path.read_text(encoding="utf-8"),
                sidecar_path(deck_path),
                new_deck_path.read_text(encoding="utf-8"),
                sidecar_path(new_deck_path),
            )
    else:
        result = mana_audit(hd)
        if output_path is None:
            output_path = _default_output_path(
                deck_path.read_text(encoding="utf-8"), sidecar_path(deck_path)
            )

    output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
