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
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    build_card_lookup,
    has_any_number_exemption,
    named_card_cap,
)
from mtg_utils.format_config import get_format_config
from mtg_utils.rules_lookup import load_rules, resolve_rules_path

# Map legality-audit violation reasons to the Comprehensive Rules rules
# that govern them. Used by ``--cite-rules`` to attach CR citations so
# the agent can explain *why* a violation triggered, not just that it
# did. Rule numbers are stable across CR updates; rule *text* is pulled
# live from the downloaded CR.
_REASON_TO_CR_RULES: dict[str, tuple[str, ...]] = {
    # 903.5b: Commander singleton rule. 100.2a: 60-card-format copy limit.
    "copy_limit": ("100.2a", "903.5b"),
    # 100.2a also covers basic-land exemption. 903.5b includes the
    # "any number of cards named X" exemption.
    "exceeds_named_card_cap": ("100.2a",),
    # 903.4 = commander identity. 903.5d = Brawl colorless-basic
    # exemption.
    "color_identity": ("903.4", "903.5d"),
    # Basic land type mixing in colorless Brawl — same rule.
    "colorless_deck_must_pick_one_basic_type": ("903.5d",),
    # 100.4a: sideboard max 15 cards.
    "sideboard_too_large": ("100.4a",),
    # 100.2a (60-card minimum) and 903.5a (100-card Commander minimum).
    "below_minimum": ("100.2a", "903.5a"),
    # Vintage restricted list (effectively a custom copy limit).
    "restricted": ("100.2a",),
    # Generic banned/not-legal in a format.
    "banned": ("100.6",),
    "not_legal": ("100.6",),
}

# Basic land subtypes that produce colored mana. Wastes is a basic land too,
# but it has an empty color identity, so it always passes the subset check
# without needing the colorless-Brawl exemption.
_COLORED_BASIC_SUBTYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})

_LEGAL_STATUSES = frozenset({"legal", "restricted"})


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
    *,
    deck_card_names: set[str] | None = None,
) -> list[dict]:
    """Return a list of cards whose legality is not ``legal`` or ``restricted``.

    When *deck_card_names* is provided, only cards whose name appears in the
    set are checked. This allows callers to pass a combined main+sideboard
    name set while still feeding the full hydrated list.
    """
    violations: list[dict] = []
    for card in hydrated_cards:
        name = card.get("name", "?")
        if deck_card_names is not None and name not in deck_card_names:
            continue
        legalities = card.get("legalities") or {}
        status = legalities.get(legality_key, "not_legal")
        if status not in _LEGAL_STATUSES:
            violations.append({"name": name, "legality": status})
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

    Returns an empty list for non-commander formats (no color identity
    restriction). Honors the Brawl/Historic Brawl colorless-commander
    exemption (one basic land subtype of the pilot's choice).
    """
    if not config.get("has_commander", True):
        return []
    hydrated_by_name = build_card_lookup(hydrated_cards)
    commander_ci = _commander_color_identity(deck_json, hydrated_by_name)
    commander_ci_sorted = sorted(commander_ci)
    deck_card_names: set[str] = set()
    for entry in deck_json.get("cards") or []:
        deck_name = entry["name"]
        deck_card_names.add(deck_name)
        card = hydrated_by_name.get(deck_name)
        if card is not None:
            deck_card_names.add(card.get("name", ""))

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


def check_copy_limits(
    deck_json: dict,
    hydrated_by_name: dict[str, dict],
    config: dict,
) -> list[dict]:
    """Return a list of copy-limit violations.

    The per-card limit comes from ``config["max_copies"]`` (1 for singleton
    formats, 4 for constructed). Exemptions:

    - Basic lands (unlimited copies always legal)
    - Cards with "A deck can have any number of cards named X" oracle text
    - Cards with "A deck can have up to <N> cards named X" oracle text, as
      long as ``quantity <= N``

    For Vintage, cards with ``legalities.vintage == "restricted"`` are capped
    at 1 copy regardless of the format default.

    Counts are computed across mainboard + sideboard combined, matching MTG
    rules (the copy limit spans both zones).
    """
    max_copies = config.get("max_copies", 1)
    legality_key = config.get("legality_key", "")

    # Aggregate quantities across mainboard and sideboard
    combined_quantities: dict[str, int] = {}
    for section in ("cards", "sideboard"):
        for entry in deck_json.get(section) or []:
            name = entry.get("name", "?")
            qty = int(entry.get("quantity", 1))
            combined_quantities[name] = combined_quantities.get(name, 0) + qty

    violations: list[dict] = []
    for name, quantity in combined_quantities.items():
        card = hydrated_by_name.get(name)
        if card is None:
            continue

        if _is_basic_land(card):
            continue

        if has_any_number_exemption(card):
            continue

        cap = named_card_cap(card)
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

        # Vintage restricted: capped at 1 regardless of format max_copies
        effective_limit = max_copies
        if legality_key == "vintage":
            legalities = card.get("legalities") or {}
            if legalities.get("vintage") == "restricted":
                effective_limit = 1

        if quantity > effective_limit:
            is_restricted = effective_limit == 1 and max_copies > 1
            reason = "restricted" if is_restricted else "copy_limit"
            violations.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "limit": effective_limit,
                    "reason": reason,
                }
            )
    return violations


def check_sideboard_size(deck_json: dict, config: dict) -> list[dict]:
    """Return a violation if the sideboard exceeds the format's limit."""
    max_sb = config.get("sideboard_size", 0)
    if max_sb == 0:
        return []
    sb_total = sum(int(e.get("quantity", 1)) for e in deck_json.get("sideboard") or [])
    if sb_total > max_sb:
        return [
            {
                "sideboard_count": sb_total,
                "limit": max_sb,
                "reason": "sideboard_too_large",
            }
        ]
    return []


def check_deck_minimum(deck_json: dict, config: dict) -> list[dict]:
    """Return a violation if the mainboard is below the format minimum."""
    min_size = config.get("deck_size", 60)
    total_cards = int(deck_json.get("total_cards", 0)) or sum(
        int(e.get("quantity", 1))
        for e in (deck_json.get("cards") or []) + (deck_json.get("commanders") or [])
    )
    if total_cards < min_size:
        return [
            {
                "total_cards": total_cards,
                "minimum": min_size,
                "reason": "below_minimum",
            }
        ]
    return []


def legality_audit(deck_json: dict, hydrated_cards: list[dict]) -> dict:
    """Run all legality checks and return a structured result."""
    config = get_format_config(deck_json)
    legality_key = config["legality_key"]

    # Collect all card names across main + sideboard for format legality.
    # Include both deck-side names (which may be Arena display names) and
    # canonical hydrated names so aliased cards aren't silently skipped.
    hydrated_by_name = build_card_lookup(hydrated_cards)
    all_deck_names: set[str] = set()
    for section in ("commanders", "cards", "sideboard"):
        for entry in deck_json.get(section) or []:
            deck_name = entry.get("name", "")
            all_deck_names.add(deck_name)
            # If this deck name resolves to a hydrated card with a different
            # canonical name, include that too so check_format_legality's
            # card.get("name") filter matches.
            card = hydrated_by_name.get(deck_name)
            if card is not None:
                all_deck_names.add(card.get("name", ""))

    format_violations = check_format_legality(
        hydrated_cards,
        legality_key,
        deck_card_names=all_deck_names,
    )
    ci_violations = check_color_identity(deck_json, hydrated_cards, config)
    copy_violations = check_copy_limits(deck_json, hydrated_by_name, config)
    sb_violations = check_sideboard_size(deck_json, config)
    deck_min_violations = check_deck_minimum(deck_json, config)

    counts = {
        "format_legality": len(format_violations),
        "color_identity": len(ci_violations),
        "copy_limits": len(copy_violations),
        "sideboard_size": len(sb_violations),
        "deck_minimum": len(deck_min_violations),
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
            "copy_limits": copy_violations,
            "sideboard_size": sb_violations,
            "deck_minimum": deck_min_violations,
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
        elif reason == "sideboard_size":
            names.append(f"{v['sideboard_count']}/{v['limit']}")
        elif reason == "deck_minimum":
            names.append(f"{v['total_cards']}/{v['minimum']}")
        elif v.get("reason") == "exceeds_named_card_cap":
            names.append(f"{v['name']} ({v['quantity']}/{v['limit']})")
        elif v.get("reason") == "restricted":
            names.append(f"{v['name']} ({v['quantity']}x, restricted=1)")
        else:
            names.append(f"{v['name']} ({v['quantity']}x, limit={v.get('limit', '?')})")
    more = len(violations) - len(shown)
    suffix = f", +{more} more" if more > 0 else ""
    return f"  {reason} ({len(violations)}): {', '.join(names)}{suffix}"


_REPORT_CHECKS = (
    "format_legality",
    "color_identity",
    "copy_limits",
    "sideboard_size",
    "deck_minimum",
)


def render_text_report(result: dict) -> str:
    counts = result.get("counts") or {}
    total = sum(counts.values())
    status = result.get("overall_status", "?")
    fmt = result.get("format", "?")
    total_cards = result.get("total_cards", 0)
    if total:
        header = f"legality-audit: {status} — {total} violation(s) in {fmt}"
    else:
        header = f"legality-audit: {status} — {total_cards} cards, format={fmt}"
    violations = result.get("violations") or {}
    lines = [header, ""]
    for check in _REPORT_CHECKS:
        v = violations.get(check) or []
        # Skip checks that aren't relevant (e.g., sideboard for commander)
        if not v and check in ("sideboard_size", "deck_minimum"):
            continue
        lines.append(_format_violation_line(check, v))
    return "\n".join(lines) + "\n"


def _default_output_path(*args: object) -> Path:
    return sha_keyed_path("legality-audit", *args)


def _attach_rule_citations(result: dict, rules_file: Path | None) -> None:
    """Enrich each violation group with CR citations keyed on its reason.

    Silently no-ops (records ``rule_citations_error``) if the CR isn't
    available; ``--cite-rules`` is additive enrichment, not a gate.
    """
    try:
        path = resolve_rules_path(rules_file)
    except FileNotFoundError as exc:
        result["rule_citations_error"] = str(exc)
        return

    parsed = load_rules(path)

    citations: dict[str, list[dict]] = {}
    for group, violations in (result.get("violations") or {}).items():
        seen_reasons: set[str] = set()
        group_citations: list[dict] = []
        for v in violations:
            reason = v.get("reason", group)
            if reason in seen_reasons:
                continue
            seen_reasons.add(reason)
            for rule_num in _REASON_TO_CR_RULES.get(reason, ()):
                rule = parsed["rules"].get(rule_num)
                if rule is None:
                    continue
                group_citations.append(
                    {
                        "reason": reason,
                        "rule": rule_num,
                        "snippet": (rule.get("text") or rule.get("title") or "")[:300],
                    },
                )
        if group_citations:
            citations[group] = group_citations
    result["rule_citations"] = citations


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
@click.option(
    "--cite-rules",
    "cite_rules",
    is_flag=True,
    help="Attach MTG Comprehensive Rules citations for each violation reason.",
)
@click.option(
    "--rules-file",
    "rules_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Comprehensive Rules TXT path. Defaults to newest comprehensive-rules*.txt.",
)
def main(
    deck_path: Path,
    hydrated_path: Path,
    output_path: Path | None,
    rules_file: Path | None,
    *,
    cite_rules: bool,
) -> None:
    """Audit a deck for format legality, color identity, and singleton rule."""
    deck_content = deck_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    deck = json.loads(deck_content)
    hydrated = json.loads(hydrated_content)

    result = legality_audit(deck, hydrated)

    if cite_rules:
        _attach_rule_citations(result, rules_file)

    if output_path is None:
        output_path = _default_output_path(deck_content, hydrated_content)
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
