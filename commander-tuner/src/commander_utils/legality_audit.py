"""Audit a deck for format legality, color identity, and singleton rule.

Runs three independent checks against a parsed deck + hydrated card data:

1. **Format legality**: every card's ``legalities[<format>]`` must be ``legal``
   or ``restricted`` (the codebase convention — see ``find_commanders``,
   ``card_search``, ``scryfall_lookup``).
2. **Color identity**: every card's ``color_identity`` must be a subset of
   the commander(s)' combined color identity. Brawl/Historic Brawl grant a
   colorless-commander exemption allowing any number of basic lands of one
   chosen basic land type (Comprehensive Rules gloss on rule 903.5d).
3. **Singleton rule**: no card may appear more than once, except basic lands
   and cards whose oracle text reads "A deck can have any number of cards
   named X" (Hare Apparent, Rat Colony, etc.) or "A deck can have up to N
   cards named X" (Seven Dwarves, Nazgûl).

The module is a data producer, not a gate: it always exits 0. Callers
inspect ``overall_status`` to decide what to do with the result.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from commander_utils._sidecar import atomic_write_json, sha_keyed_path
from commander_utils.format_config import get_format_config

# Basic land subtypes that produce colored mana. Wastes is a basic land too,
# but it has an empty color identity, so it always passes the subset check
# without needing the colorless-Brawl exemption.
_COLORED_BASIC_SUBTYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})

_LEGAL_STATUSES = frozenset({"legal", "restricted"})

_ANY_NUMBER_PATTERN = "A deck can have any number of cards named"
_UP_TO_N_PATTERN = re.compile(r"A deck can have up to (\w+) cards named", re.IGNORECASE)
_WORD_TO_INT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _is_basic_land(card: dict) -> bool:
    return "Basic" in (card.get("type_line") or "")


def _basic_subtype(card: dict) -> str | None:
    """Return the basic land subtype (e.g. 'Plains') from a type_line, or None."""
    type_line = card.get("type_line") or ""
    if "Basic" not in type_line:
        return None
    # type_line looks like "Basic Land — Plains" or "Basic Snow Land — Forest".
    _, _, after = type_line.partition("—")
    for token in after.strip().split():
        if token in _COLORED_BASIC_SUBTYPES or token == "Wastes":
            return token
    return None


def check_format_legality(
    hydrated_cards: list[dict],
    legality_key: str,
) -> list[dict]:
    """Return a list of cards whose legality is not ``legal`` or ``restricted``."""
    violations: list[dict] = []
    for card in hydrated_cards:
        legalities = card.get("legalities") or {}
        status = legalities.get(legality_key, "not_legal")
        if status not in _LEGAL_STATUSES:
            violations.append({"name": card.get("name", "?"), "legality": status})
    return violations


def _commander_color_identity(
    deck_json: dict,
    hydrated_by_name: dict[str, dict],
) -> set[str]:
    ci: set[str] = set()
    for entry in deck_json.get("commanders") or []:
        card = hydrated_by_name.get(entry.get("name", ""))
        if card is not None:
            ci.update(card.get("color_identity") or [])
    return ci


def check_color_identity(
    deck_json: dict,
    hydrated_cards: list[dict],
    config: dict,
) -> list[dict]:
    """Return a list of cards outside the commander's color identity.

    Honors the Brawl/Historic Brawl colorless-commander exemption (one basic
    land subtype of the pilot's choice).
    """
    hydrated_by_name = {c.get("name", ""): c for c in hydrated_cards}
    commander_ci = _commander_color_identity(deck_json, hydrated_by_name)
    commander_ci_sorted = sorted(commander_ci)
    deck_card_names = {entry["name"] for entry in deck_json.get("cards") or []}

    # Compute colorless-Brawl exemption (if applicable).
    exempt_basic_subtype: str | None = None
    mixed_basic_violation_subtypes: list[str] = []
    if not commander_ci and config.get("colorless_any_basic"):
        basic_subtypes: set[str] = set()
        for card in hydrated_cards:
            if card.get("name") not in deck_card_names:
                continue
            sub = _basic_subtype(card)
            if sub is None or sub == "Wastes":
                continue
            basic_subtypes.add(sub)
        if len(basic_subtypes) == 1:
            exempt_basic_subtype = next(iter(basic_subtypes))
        elif len(basic_subtypes) > 1:
            mixed_basic_violation_subtypes = sorted(basic_subtypes)

    violations: list[dict] = []
    for card in hydrated_cards:
        name = card.get("name", "?")
        if name not in deck_card_names:
            continue  # skip commanders — they define the identity
        card_ci = set(card.get("color_identity") or [])

        # Mixed-basics failure (all offending basics flagged)
        if mixed_basic_violation_subtypes:
            sub = _basic_subtype(card)
            if sub in mixed_basic_violation_subtypes:
                violations.append(
                    {
                        "name": name,
                        "card_identity": sorted(card_ci),
                        "commander_identity": commander_ci_sorted,
                        "reason": "colorless_deck_must_pick_one_basic_type",
                        "found_types": mixed_basic_violation_subtypes,
                    }
                )
                continue

        if card_ci.issubset(commander_ci):
            continue

        # Single-basic-type exemption for colorless Brawl/HB
        if (
            exempt_basic_subtype is not None
            and _basic_subtype(card) == exempt_basic_subtype
        ):
            continue

        violations.append(
            {
                "name": name,
                "card_identity": sorted(card_ci),
                "commander_identity": commander_ci_sorted,
                "reason": "not_in_commander_identity",
            }
        )
    return violations


def _named_card_cap(oracle_text: str) -> int | None:
    """Return the "up to N" cap from oracle text, or None if not present."""
    match = _UP_TO_N_PATTERN.search(oracle_text)
    if match is None:
        return None
    return _WORD_TO_INT.get(match.group(1).lower())


def check_singletons(
    deck_json: dict,
    hydrated_by_name: dict[str, dict],
    _config: dict,
) -> list[dict]:
    """Return a list of singleton-rule violations.

    Exemptions:
    - Basic lands (unlimited copies always legal)
    - Cards with "A deck can have any number of cards named X" oracle text
    - Cards with "A deck can have up to <N> cards named X" oracle text, as
      long as ``quantity <= N``
    """
    violations: list[dict] = []
    for entry in deck_json.get("cards") or []:
        name = entry.get("name", "?")
        quantity = int(entry.get("quantity", 1))
        if quantity <= 1:
            continue

        card = hydrated_by_name.get(name)
        if card is None:
            # Unhydrated card — legality check will surface it via a separate
            # path if it's missing from the deck's hydrated data.
            continue

        if _is_basic_land(card):
            continue

        oracle = card.get("oracle_text") or ""
        if _ANY_NUMBER_PATTERN in oracle:
            continue

        cap = _named_card_cap(oracle)
        if cap is not None:
            if quantity <= cap:
                continue
            violations.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "limit": cap,
                    "reason": "exceeds_named_card_cap",
                }
            )
            continue

        violations.append(
            {
                "name": name,
                "quantity": quantity,
                "limit": 1,
                "reason": "singleton",
            }
        )
    return violations


def legality_audit(deck_json: dict, hydrated_cards: list[dict]) -> dict:
    """Run all three legality checks and return a structured result."""
    config = get_format_config(deck_json)
    legality_key = config["legality_key"]

    format_violations = check_format_legality(hydrated_cards, legality_key)
    ci_violations = check_color_identity(deck_json, hydrated_cards, config)
    hydrated_by_name = {c.get("name", ""): c for c in hydrated_cards}
    singleton_violations = check_singletons(deck_json, hydrated_by_name, config)

    counts = {
        "format_legality": len(format_violations),
        "color_identity": len(ci_violations),
        "singleton": len(singleton_violations),
    }
    total_violations = sum(counts.values())
    overall_status = "PASS" if total_violations == 0 else "FAIL"

    total_cards = int(deck_json.get("total_cards", 0)) or sum(
        int(e.get("quantity", 1))
        for e in (deck_json.get("cards") or []) + (deck_json.get("commanders") or [])
    )

    return {
        "format": deck_json.get("format", "commander"),
        "overall_status": overall_status,
        "total_cards": total_cards,
        "counts": counts,
        "violations": {
            "format_legality": format_violations,
            "color_identity": ci_violations,
            "singleton": singleton_violations,
        },
    }


def _format_violation_line(
    reason: str,
    violations: list[dict],
    max_items: int = 5,
) -> str:
    if not violations:
        return f"  {reason} (0):"
    shown = violations[:max_items]
    names = []
    for v in shown:
        if reason == "format_legality":
            names.append(f"{v['name']} ({v['legality']})")
        elif reason == "color_identity":
            ci = "".join(v.get("card_identity") or []) or "C"
            cmd_ci = "".join(v.get("commander_identity") or []) or "C"
            if v.get("reason") == "colorless_deck_must_pick_one_basic_type":
                names.append(f"{v['name']} (mixed basics)")
            else:
                names.append(f"{v['name']} ({ci} not in {cmd_ci})")
        elif v.get("reason") == "exceeds_named_card_cap":
            names.append(f"{v['name']} ({v['quantity']}/{v['limit']})")
        else:
            names.append(f"{v['name']} ({v['quantity']}x)")
    more = len(violations) - len(shown)
    suffix = f", +{more} more" if more > 0 else ""
    return f"  {reason} ({len(violations)}): {', '.join(names)}{suffix}"


def render_text_report(result: dict) -> str:
    counts = result.get("counts") or {}
    total = sum(counts.values())
    status = result.get("overall_status", "?")
    fmt = result.get("format", "?")
    total_cards = result.get("total_cards", 0)
    if total:
        header = f"legality-audit: {status} — {total} violations in {fmt}"
    else:
        header = f"legality-audit: {status} — {total_cards} cards, format={fmt}"
    violations = result.get("violations") or {}
    lines = [header, ""]
    lines.extend(
        _format_violation_line(reason, violations.get(reason) or [])
        for reason in ("format_legality", "color_identity", "singleton")
    )
    return "\n".join(lines) + "\n"


def _default_output_path(*args: object) -> Path:
    return sha_keyed_path("legality-audit", *args)


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
def main(
    deck_path: Path,
    hydrated_path: Path,
    output_path: Path | None,
) -> None:
    """Audit a deck for format legality, color identity, and singleton rule."""
    deck_content = deck_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = json.loads(hydrated_content)

    result = legality_audit(deck, hydrated)

    if output_path is None:
        output_path = _default_output_path(deck_content, hydrated_content)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
