"""Deck statistics calculator."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import click

from mtg_utils._card_ir.trees import trees_for
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import is_land
from mtg_utils.deck import accumulate_deck_metrics
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.hydrated_deck import HydratedDeck, sidecar_path
from mtg_utils.theme_presets import get_preset


def _detect_alternative_costs(card: dict) -> list[dict]:
    """The card's other ways to pay for it: every printed keyword cost phase reads
    (``ConceptTree.card_alt_costs`` — suspend, evoke, flashback, buyback, morph,
    ninjutsu …, each with its ``cost_kind``: alternative / additional / special
    action / ability, see ``crosswalk.AltCost``), plus an adventure's or a
    modal DFC's other half, read off the record's faces."""
    alt_costs: list[dict] = [
        {"type": alt.kind, "cost": alt.cost, "cost_kind": alt.cost_kind}
        for tree in trees_for(card)
        for alt in tree.card_alt_costs
    ]

    # Card faces: adventure and MDFC — casting the other half is a choice of which
    # half to cast (CR 715.3, 712.11b), not a cost the card prints.
    card_faces = card.get("card_faces")
    layout = card.get("layout", "")
    if card_faces and layout == "adventure" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "adventure",
                "cost": card_faces[1].get("mana_cost", ""),
                "cost_kind": "other_face",
            }
        )
    elif card_faces and layout == "modal_dfc" and len(card_faces) >= 2:
        alt_costs.append(
            {
                "type": "mdfc_back",
                "cost": card_faces[1].get("mana_cost", ""),
                "cost_kind": "other_face",
            }
        )

    return alt_costs


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
    # Mass land denial: the ``mass_land_denial`` signal key (the Commander
    # Brackets' definition, ADR-0030 — Armageddon, Wildfire, Winter Orb, Blood Moon).
    mld = get_preset("mass-land-denial")
    mld_cards = sorted({c["name"] for c in hydrated if c and mld.matches(c)})
    fast_curve = bool(hydrated) and 0 < avg_cmc <= _FAST_CURVE_CMC
    if mld_cards or len(game_changers) >= 4:
        bracket, name = 4, "Optimized"
    elif game_changers:
        bracket, name = 3, "Upgraded"
    else:
        bracket, name = 2, "Core"
    return {
        "bracket": bracket,
        "name": name,
        "game_changers": game_changers,
        "mass_land_denial": mld_cards,
        "fast_curve": fast_curve,
    }


def deck_stats(hd: HydratedDeck) -> dict:
    """Compute deck statistics from a HydratedDeck (deck + joined card records)."""
    # .entries pairs each deck entry with its record (or None) in one walk, so the
    # deck-side quantity and the record can't desync. Reused below for alt-costs.
    main_entries = hd.entries(zones=("commanders", "cards"))
    m = accumulate_deck_metrics(
        ((entry.get("quantity", 1), card) for entry, card in main_entries),
        deck_mana=hd.deck_mana,
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


def _default_output_path(deck_path: Path) -> Path:
    # Keyed by the deck's content AND its hydrated sidecar (mtime/size), so a bulk
    # refresh that re-joins the deck also re-keys the report.
    return sha_keyed_path(
        "deck-stats", deck_path.read_text(encoding="utf-8"), sidecar_path(deck_path)
    )


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
def main(deck_path: Path, bulk_data: Path | None, output_path: Path | None) -> None:
    """Compute deck statistics for DECK_PATH."""
    result = deck_stats(acquire_for_cli(deck_path, bulk_data))

    if output_path is None:
        output_path = _default_output_path(deck_path)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
