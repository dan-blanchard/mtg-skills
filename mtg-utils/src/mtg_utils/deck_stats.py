"""Deck statistics calculator."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    get_oracle_text,
    is_land,
)
from mtg_utils.deck import accumulate_deck_metrics
from mtg_utils.hydrated_deck import HydratedDeck

ALTERNATIVE_COST_KEYWORDS = {
    "suspend",
    "evoke",
    "foretell",
    "flashback",
    "escape",
    "dash",
    "disturb",
    "madness",
    "miracle",
    "blitz",
    "prototype",
    "spectacle",
    "emerge",
    "ninjutsu",
    "overload",
    "plot",
    "bestow",
    "mutate",
    "prowl",
    "retrace",
    "surge",
    "buyback",
}

_MORPH_KEYWORDS = {"morph", "disguise", "megamorph"}


def _detect_alternative_costs(card: dict) -> list[dict]:
    """Detect alternative casting costs from keywords and oracle text."""
    keywords = [kw.lower() for kw in card.get("keywords", [])]
    oracle = get_oracle_text(card)
    alt_costs: list[dict] = []

    for kw in keywords:
        if kw in ALTERNATIVE_COST_KEYWORDS:
            pattern = re.compile(
                rf"{re.escape(kw)}(?:\s|—|\u2014)\s*(.+?)(?:\n|\.|$|\()",
                re.IGNORECASE,
            )
            match = pattern.search(oracle)
            if match:
                alt_costs.append({"type": kw, "cost": match.group(1).strip()})
        elif kw in _MORPH_KEYWORDS:
            alt_costs.append({"type": kw, "cost": "{3} (face down)"})
            pattern = re.compile(
                rf"{re.escape(kw)}(?:\s|—|\u2014)\s*(.+?)(?:\n|\.|$|\()",
                re.IGNORECASE,
            )
            match = pattern.search(oracle)
            if match:
                cost = match.group(1).strip()
                alt_costs.append({"type": f"{kw} (face up)", "cost": cost})

    # Card faces: adventure and MDFC
    card_faces = card.get("card_faces")
    layout = card.get("layout", "")
    if card_faces and layout == "adventure" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "adventure",
                "cost": card_faces[1].get("mana_cost", ""),
            }
        )
    elif card_faces and layout == "modal_dfc" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "mdfc_back",
                "cost": card_faces[1].get("mana_cost", ""),
            }
        )

    return alt_costs


# Mass land denial / destruction — a Commander-bracket pillar (Armageddon, Jokulhaups,
# Pox-style symmetric land sac, Back to Basics / Winter Orb "lands don't untap" locks).
# Spot land removal ("destroy target land") is deliberately NOT matched.
_MASS_LAND_DENIAL_RE = re.compile(
    r"destroy all lands|destroy all nonbasic lands"
    r"|each (?:player|opponent) sacrifices?[^.]*\blands?\b"
    r"|nonbasic lands don't untap|lands don't untap during",
    re.IGNORECASE,
)
# avg CMC at or below this reads as a fast, high-power curve.
_FAST_CURVE_CMC = 2.3


def detect_bracket(hydrated: Sequence[dict | None], avg_cmc: float) -> dict:
    """Estimate the Commander bracket mechanically from the signals we can read:
    Game Changers (Scryfall's ``game_changer`` flag), mass land denial, and curve
    speed. Maps to brackets 2-4. Bracket 1 (Exhibition, intentionally weak) and 5
    (cEDH, metagame-defined) aren't determinable from the list alone.

      - mass land denial OR 4+ game changers -> 4 (Optimized)
      - 1-3 game changers                    -> 3 (Upgraded)
      - otherwise                            -> 2 (Core)

    Returns the bracket plus the evidence (game-changer names, MLD card names, and a
    fast-curve flag) so the UI can show the reasoning."""
    game_changers = sorted({c["name"] for c in hydrated if c and c.get("game_changer")})
    mass_land_denial = sorted(
        {
            c["name"]
            for c in hydrated
            if c and _MASS_LAND_DENIAL_RE.search(get_oracle_text(c) or "")
        }
    )
    fast_curve = bool(hydrated) and 0 < avg_cmc <= _FAST_CURVE_CMC
    if mass_land_denial or len(game_changers) >= 4:
        bracket, name = 4, "Optimized"
    elif game_changers:
        bracket, name = 3, "Upgraded"
    else:
        bracket, name = 2, "Core"
    return {
        "bracket": bracket,
        "name": name,
        "game_changers": game_changers,
        "mass_land_denial": mass_land_denial,
        "fast_curve": fast_curve,
    }


def deck_stats(hd: HydratedDeck) -> dict:
    """Compute deck statistics from a HydratedDeck (deck + joined card records)."""
    # .entries pairs each deck entry with its record (or None) in one walk, so the
    # deck-side quantity and the record can't desync. Reused below for alt-costs.
    main_entries = hd.entries(zones=("commanders", "cards"))
    m = accumulate_deck_metrics(
        (entry.get("quantity", 1), card) for entry, card in main_entries
    )
    total_cards = m["total"]
    land_count = m["land_count"]
    creature_count = m["creature_count"]
    ramp_count = m["ramp_count"]
    game_changer_count = m["game_changer_count"]
    avg_cmc = m["avg_cmc"]
    curve = m["curve"]
    sources = m["color_sources"]

    # Detect alternative costs
    alternative_cost_cards: list[dict] = []
    for entry, card in main_entries:
        if card is None or is_land(card):
            continue
        alt_costs = _detect_alternative_costs(card)
        if alt_costs:
            alternative_cost_cards.append(
                {
                    "name": entry["name"],
                    "cmc": float(card.get("cmc") or 0),
                    "alt_costs": alt_costs,
                }
            )

    result = {
        "total_cards": total_cards,
        "land_count": land_count,
        "creature_count": creature_count,
        "ramp_count": ramp_count,
        "game_changer_count": game_changer_count,
        "avg_cmc": round(avg_cmc, 2),
        "curve": dict(sorted(curve.items())),
        "color_sources": dict(sorted(sources.items())),
        "alternative_cost_cards": alternative_cost_cards,
    }

    _add_sideboard_stats(result, hd)
    return result


def _add_sideboard_stats(result: dict, hd: HydratedDeck) -> None:
    if not hd.sideboard:
        return
    sb_total = 0
    sb_curve: Counter[int] = Counter()
    for entry, card in hd.entries(zones=("sideboard",)):
        qty = entry.get("quantity", 1)
        sb_total += qty
        if card is not None and not is_land(card):
            cmc = float(card.get("cmc") or 0)
            sb_curve[int(cmc)] += qty
    result["sideboard_total"] = sb_total
    result["sideboard_curve"] = dict(sorted(sb_curve.items()))


def render_text_report(stats: dict) -> str:
    lines: list[str] = []
    lines.append(f"deck-stats: {stats.get('total_cards', 0)} cards total")
    lines.append("")
    lines.append(
        f"Lands: {stats.get('land_count', 0)}, "
        f"Creatures: {stats.get('creature_count', 0)}, "
        f"Ramp: {stats.get('ramp_count', 0)}, "
        f"Game Changers: {stats.get('game_changer_count', 0)}"
    )
    lines.append(f"Avg CMC (nonland): {stats.get('avg_cmc', 0)}")

    curve = stats.get("curve") or {}
    if curve:
        curve_str = " | ".join(f"{k}:{v}" for k, v in sorted(curve.items()))
        lines.append(f"Curve: {curve_str}")

    sources = stats.get("color_sources") or {}
    if sources:
        src_str = ", ".join(f"{k}={v}" for k, v in sorted(sources.items()))
        lines.append(f"Color sources: {src_str}")

    alt_cost = stats.get("alternative_cost_cards") or []
    if alt_cost:
        lines.append(f"Alternative-cost cards: {len(alt_cost)}")
        for entry in alt_cost:
            costs = ", ".join(c["type"] for c in entry.get("alt_costs", []))
            lines.append(f"  - {entry['name']} (CMC {entry['cmc']}, {costs})")

    sb_total = stats.get("sideboard_total")
    if sb_total:
        lines.append(f"Sideboard: {sb_total} cards")
        sb_curve = stats.get("sideboard_curve") or {}
        if sb_curve:
            sb_curve_str = " | ".join(f"{k}:{v}" for k, v in sorted(sb_curve.items()))
            lines.append(f"Sideboard curve: {sb_curve_str}")

    return "\n".join(lines) + "\n"


def _default_output_path(deck_content: str, hydrated_content: str) -> Path:
    return sha_keyed_path("deck-stats", deck_content, hydrated_content)


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(deck_path: Path, hydrated_path: Path, output_path: Path | None) -> None:
    """Compute deck statistics from parsed deck and hydrated card data."""
    deck_content = deck_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = json.loads(hydrated_content)
    result = deck_stats(HydratedDeck.from_parsed(deck, records=hydrated))

    if output_path is None:
        output_path = _default_output_path(deck_content, hydrated_content)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
