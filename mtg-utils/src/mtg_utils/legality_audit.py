"""Audit a deck for format legality, color identity, and singleton rule.

Runs three independent checks against a parsed deck + hydrated card data:

1. **Format legality**: every card's ``Format.legality`` status must be ``legal``
   or ``restricted`` (the one legality read — ``mtg_utils.formats``, ADR-0045).
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

from collections.abc import Mapping
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    build_card_lookup,
    has_any_number_exemption,
    is_basic_land,
    named_card_cap,
)
from mtg_utils.companion import companion_violations, is_companion
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.formats import LEGAL_STATUSES, Format
from mtg_utils.hydrated_deck import HydratedDeck, sidecar_path
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
    # 100.2a (60-card minimum), 100.2b (40-card limited minimum) and 903.5a
    # (100-card Commander minimum).
    "below_minimum": ("100.2a", "100.2b", "903.5a"),
    # 100.2b: a limited deck is built from the opened product plus basic lands.
    "not_in_pool": ("100.2b",),
    # Vintage restricted list (effectively a custom copy limit).
    "restricted": ("100.2a",),
    # Generic banned/not-legal in a format.
    "banned": ("100.6",),
    "not_legal": ("100.6",),
    # 903.6: a Commander deck must designate a commander.
    "no_commander_selected": ("903.6",),
    # Same rule covers "designation didn't resolve to a real card", but the
    # immediate fix is tooling (typo, stale cache) rather than rules.
    "commander_not_in_hydrated": ("903.6",),
    # 103.2b: a player may reveal at most one companion.
    "companion_multiple": ("103.2b",),
    # 702.139a: companion is a keyword ability — the revealed card must have it.
    "companion_not_companion": ("702.139a",),
    # 702.139b: the companion's condition constrains the STARTING deck.
    "companion_condition": ("702.139b",),
}

# Basic land subtypes that produce colored mana. Wastes is a basic land too,
# but it has an empty color identity, so it always passes the subset check
# without needing the colorless-Brawl exemption.
_COLORED_BASIC_SUBTYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


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
    fmt: Format,
    *,
    deck_card_names: set[str] | None = None,
) -> list[dict]:
    """Return a list of cards whose ``fmt.legality`` is not ``legal`` or ``restricted``
    (the status is the violation's ``legality``; Competitive Brawl's ban override and
    the Arena-pool gate are the Format's business).

    When *deck_card_names* is provided, only cards whose name appears in the
    set are checked. This allows callers to pass a combined main+sideboard
    name set while still feeding the full hydrated list.
    """
    violations: list[dict] = []
    for card in hydrated_cards:
        name = card.get("name", "?")
        if deck_card_names is not None and name not in deck_card_names:
            continue
        status = fmt.legality(card)
        if status in LEGAL_STATUSES:
            continue
        violations.append({"name": name, "legality": status})
    return violations


def _commander_color_identity(
    deck_json: dict,
    hydrated_by_name: Mapping[str, dict],
) -> set[str]:
    ci: set[str] = set()
    for entry in deck_json.get("commanders") or []:
        card = hydrated_by_name.get(entry.get("name", ""))
        if card is not None:
            ci.update(card.get("color_identity") or [])
    return ci


def check_commander_zone(
    deck_json: dict,
    fmt: Format,
    hydrated_by_name: Mapping[str, dict] | None = None,
) -> list[dict]:
    """Verify the commander zone is populated AND fully hydratable for
    commander-format decks.

    Two failure modes both produce the same downstream symptom — an
    empty derived commander color identity, which makes
    ``check_color_identity`` cascade-blame every non-colorless card in
    the mainboard (with the would-be commander listed FIRST):

    * ``no_commander_selected``: the ``commanders`` list is empty (e.g.,
      the user forgot to run set-commander, or it silently failed in an
      older version).
    * ``commander_not_in_hydrated``: a commander entry's name doesn't
      resolve in the hydrated cache — almost always a typo in a hand-
      edited deck JSON, occasionally a stale hydrated cache pointed at
      a deck JSON whose commanders were changed without re-running
      ``scryfall-lookup --batch``.

    Strict scope: ANY unresolvable commander entry flags the whole zone.
    Partial resolution (one of two partner commanders typo'd) would shift
    the cascading misdiagnosis from "every non-colorless card" to "every
    card outside the resolved-half's identity" — same bug class, different
    color. Forcing the user to fix the typo before any downstream check
    runs gives clean output rather than a partial-and-wrong audit.

    A legitimate colorless commander (e.g., Kozilek) resolves in
    ``hydrated_by_name`` with empty ``color_identity``, so it is NOT
    flagged here — the distinction is "name resolves" vs "name doesn't
    resolve", not "identity is empty".
    """
    if not fmt.has_commander:
        return []
    commanders = deck_json.get("commanders") or []
    if not commanders:
        return [{"reason": "no_commander_selected"}]
    if hydrated_by_name is not None:
        unresolved = [
            entry.get("name", "")
            for entry in commanders
            if not entry.get("name") or entry["name"] not in hydrated_by_name
        ]
        if unresolved:
            return [
                {
                    "reason": "commander_not_in_hydrated",
                    "unresolved_names": unresolved,
                }
            ]
    return []


def check_color_identity(
    deck_json: dict,
    hydrated_cards: list[dict],
    fmt: Format,
) -> list[dict]:
    """Return a list of cards outside the commander's color identity.

    Returns an empty list for non-commander formats (no color identity
    restriction). Honors the Brawl/Historic Brawl colorless-commander
    exemption (one basic land subtype of the pilot's choice).
    """
    if not fmt.has_commander:
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
    if not commander_ci and fmt.colorless_any_basic:
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


def card_copy_limit(card: dict, fmt: Format) -> int | None:
    """How many copies of ``card`` a deck may run in ``fmt`` — the ONE owner of the
    exemption ladder every copy-limit read follows (the audit below and the hub's
    add rule alike): a basic land or an "any number" card is unlimited (``None``);
    a named cap ("up to seven") is its own limit; a restricted card is one; else the
    Format's ``max_copies`` (CR 100.2a constructed, CR 903.5b Commander)."""
    if is_basic_land(card) or has_any_number_exemption(card):
        return None
    cap = named_card_cap(card)
    if cap is not None:
        return cap
    return 1 if fmt.legality(card) == "restricted" else fmt.max_copies


def check_copy_limits(
    deck_json: dict,
    hydrated_by_name: Mapping[str, dict],
    fmt: Format,
) -> list[dict]:
    """Return a list of copy-limit violations.

    The per-card limit comes from ``fmt.max_copies`` (1 for singleton
    formats, 4 for constructed). Exemptions:

    - Basic lands (unlimited copies always legal)
    - Cards with "A deck can have any number of cards named X" oracle text
    - Cards with "A deck can have up to <N> cards named X" oracle text, as
      long as ``quantity <= N``

    Cards whose ``Format.legality`` is ``restricted`` (Vintage) are capped
    at 1 copy regardless of the format default.

    Counts are computed across mainboard + sideboard combined, matching MTG
    rules (the copy limit spans both zones).
    """
    max_copies = fmt.max_copies or 0  # None (no limit) never reads as restricted

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
        limit = card_copy_limit(card, fmt)
        if limit is None or quantity <= limit:
            continue
        if named_card_cap(card) is not None:
            reason = "exceeds_named_card_cap"
        elif limit == 1 and max_copies > 1:
            reason = "restricted"  # Vintage: capped at 1 regardless of max_copies
        else:
            reason = "copy_limit"
        violations.append(
            {"name": name, "quantity": quantity, "limit": limit, "reason": reason}
        )
    return violations


def check_companion(
    deck_json: dict,
    hydrated_by_name: Mapping[str, dict],
    fmt: Format,
) -> list[dict]:
    """Validate the deck's ``companion`` zone (empty list → no violations).

    Three reasons, each mapped to a CR rule in ``_REASON_TO_CR_RULES``:

    - ``companion_multiple``: more than one companion card revealed (CR 103.2b).
    - ``companion_not_companion``: an entry without the companion keyword ability
      (CR 702.139a) — needs the hydrated record; un-hydratable entries are
      skipped gracefully (no data, no verdict).
    - ``companion_condition``: the deckbuilding condition fails against the
      STARTING deck — commanders + mainboard, excluding sideboard and the
      companion itself (CR 702.139b) — via ``companion_violations``. The
      ``deck_minimum`` fed to Yorion's check derives from the ``Format``:
      exact-size singleton formats (Commander family, CR 903.5a: minimum =
      maximum) pass None; 60-card constructed passes its 60-card minimum
      (``min_deck_size`` — the CR floor, whatever size the build targets).
    """
    entries = deck_json.get("companion") or []
    if not entries:
        return []
    violations: list[dict] = []
    total = sum(int(e.get("quantity", 1)) for e in entries)
    if total > 1:
        violations.append(
            {
                "companion_count": total,
                "limit": 1,
                "names": [e.get("name", "?") for e in entries],
                "reason": "companion_multiple",
            }
        )
    deck_minimum = None if fmt.is_singleton else fmt.min_deck_size
    starting_deck: list[dict] = []
    for section in ("commanders", "cards"):
        for entry in deck_json.get(section) or []:
            record = hydrated_by_name.get(entry.get("name", ""))
            if record is not None:
                starting_deck.append(
                    {**record, "quantity": int(entry.get("quantity", 1))}
                )
    for entry in entries:
        name = entry.get("name", "")
        record = hydrated_by_name.get(name)
        if record is None:
            continue  # un-hydratable companion: skip gracefully
        if not is_companion(record):
            violations.append({"name": name, "reason": "companion_not_companion"})
            continue
        try:
            condition = companion_violations(
                record, starting_deck, deck_minimum=deck_minimum
            )
        except ValueError:
            continue  # companion keyword but not one of the ten known companions
        violations.extend(
            {
                "name": name,
                "card": v.get("card"),
                "detail": v.get("reason"),
                "rule": v.get("rule"),
                "reason": "companion_condition",
            }
            for v in condition
        )
    return violations


def check_sideboard_size(deck_json: dict, fmt: Format) -> list[dict]:
    """Return a violation if the sideboard exceeds the format's limit.

    The ``companion`` zone is deliberately not counted: a companion is neither
    part of the deck nor of the sideboard (CR 702.139a-b).
    """
    max_sb = fmt.sideboard_size
    if max_sb is None or max_sb == 0:
        return []  # no sideboard (Commander) / no cap (limited: the unused pool)
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


def check_pool_containment(
    deck_json: dict,
    hydrated_by_name: Mapping[str, dict],
    fmt: Format,
) -> list[dict]:
    """A pool-bounded deck (sealed / draft) is drawn from its opened pool: every copy
    in the main deck and sideboard must be in the ``pool`` zone at that quantity
    (CR 100.2b), basic lands excepted (the product's basics are unlimited). Empty
    for any other format."""
    if not fmt.pool_bounded:
        return []
    pool: dict[str, int] = {}
    for entry in deck_json.get("pool") or []:
        pool[entry["name"]] = pool.get(entry["name"], 0) + int(entry.get("quantity", 1))
    used: dict[str, int] = {}
    for section in ("cards", "sideboard"):
        for entry in deck_json.get(section) or []:
            used[entry["name"]] = used.get(entry["name"], 0) + int(
                entry.get("quantity", 1)
            )
    violations: list[dict] = []
    for name, quantity in used.items():
        card = hydrated_by_name.get(name)
        if card is not None and is_basic_land(card):
            continue
        in_pool = pool.get(name, 0)
        if quantity > in_pool:
            violations.append(
                {
                    "name": name,
                    "quantity": quantity,
                    "in_pool": in_pool,
                    "reason": "not_in_pool",
                }
            )
    return violations


def check_deck_minimum(deck_json: dict, fmt: Format) -> list[dict]:
    """Return a violation if the mainboard is below the format minimum.

    Counts commanders + mainboard only — the ``companion`` zone is outside the
    deck (CR 702.139a-b), so it never pads the total toward the minimum.
    """
    min_size = fmt.min_deck_size
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


def legality_audit(hd: HydratedDeck) -> dict:
    """Run all legality checks and return a structured result."""
    deck_json = hd.deck
    fmt = hd.format

    # Collect all card names across main + sideboard for format legality.
    # Include both deck-side names (which may be Arena display names) and
    # canonical hydrated names so aliased cards aren't silently skipped.
    hydrated_by_name = hd.by_name
    all_deck_names: set[str] = set()
    # "companion" is included deliberately: the companion sits outside the deck
    # (CR 702.139a) but must still be a format-legal card, so it participates in
    # the format-legality check (and only that one).
    for section in ("commanders", "cards", "sideboard", "companion"):
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
        hd.records, fmt, deck_card_names=all_deck_names
    )
    commander_zone_violations = check_commander_zone(deck_json, fmt, hydrated_by_name)
    # Suppress color-identity cascade when the commander zone is unset:
    # the would-be commander identity is empty, so every non-colorless
    # card would be flagged spuriously, drowning the real error.
    if commander_zone_violations:
        ci_violations: list[dict] = []
    else:
        ci_violations = check_color_identity(deck_json, hd.records, fmt)
    copy_violations = check_copy_limits(deck_json, hydrated_by_name, fmt)
    sb_violations = check_sideboard_size(deck_json, fmt)
    deck_min_violations = check_deck_minimum(deck_json, fmt)
    companion_zone_violations = check_companion(deck_json, hydrated_by_name, fmt)
    pool_violations = check_pool_containment(deck_json, hydrated_by_name, fmt)

    counts = {
        "format_legality": len(format_violations),
        "commander_zone": len(commander_zone_violations),
        "color_identity": len(ci_violations),
        "copy_limits": len(copy_violations),
        "sideboard_size": len(sb_violations),
        "deck_minimum": len(deck_min_violations),
        "companion": len(companion_zone_violations),
        "pool_containment": len(pool_violations),
    }
    total_violations = sum(counts.values())
    overall_status = "PASS" if total_violations == 0 else "FAIL"

    total_cards = int(deck_json.get("total_cards", 0)) or sum(
        int(e.get("quantity", 1))
        for e in (deck_json.get("cards") or []) + (deck_json.get("commanders") or [])
    )

    return {
        "format": fmt.name,
        "overall_status": overall_status,
        "total_cards": total_cards,
        "counts": counts,
        "violations": {
            "format_legality": format_violations,
            "commander_zone": commander_zone_violations,
            "color_identity": ci_violations,
            "copy_limits": copy_violations,
            "sideboard_size": sb_violations,
            "deck_minimum": deck_min_violations,
            "companion": companion_zone_violations,
            "pool_containment": pool_violations,
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
        elif reason == "commander_zone":
            v_reason = v.get("reason")
            if v_reason == "commander_not_in_hydrated":
                unresolved = ", ".join(v.get("unresolved_names") or []) or "?"
                names.append(
                    f"invalid commander selected (check for typos): {unresolved}"
                )
            else:
                names.append(
                    "no commander selected — run set-commander to populate "
                    "the commanders list"
                )
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
        elif reason == "pool_containment":
            names.append(f"{v['name']} ({v['quantity']}x, {v['in_pool']} in pool)")
        elif reason == "companion":
            v_reason = v.get("reason")
            if v_reason == "companion_multiple":
                names.append(f"{v['companion_count']} companions (max 1)")
            elif v_reason == "companion_not_companion":
                names.append(f"{v['name']} (no companion ability)")
            else:  # companion_condition
                offender = v.get("card") or "deck-level"
                names.append(f"{v['name']}: condition failed ({offender})")
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
    "commander_zone",
    "color_identity",
    "copy_limits",
    "sideboard_size",
    "deck_minimum",
    "companion",
    "pool_containment",
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
        # Skip checks that aren't relevant (e.g., sideboard for commander,
        # companion for decks with no companion zone)
        if not v and check in (
            "sideboard_size",
            "deck_minimum",
            "companion",
            "pool_containment",
        ):
            continue
        lines.append(_format_violation_line(check, v))
    # Surface a CR-citations lookup failure in stdout, not just the JSON
    # sidecar. Agents skim the summary first; silent JSON-only errors
    # were missed in the live session.
    err = result.get("rule_citations_error")
    if err:
        lines.append("")
        lines.append(f"WARN: rule_citations not attached — {err}")
    return "\n".join(lines) + "\n"


def _default_output_path(*args: object) -> Path:
    return sha_keyed_path("legality-audit", *args)


def _attach_rule_citations(
    result: dict,
    rules_file: Path | None,
    input_path: Path | None = None,
) -> None:
    """Enrich each violation group with CR citations keyed on its reason.

    Silently no-ops (records ``rule_citations_error``) if the CR isn't
    available; ``--cite-rules`` is additive enrichment, not a gate.

    ``input_path`` is forwarded to ``resolve_rules_path`` so the default
    search can find a CR next to the deck/hydrated JSON when the skill
    is invoked via ``uv run --directory <skill>`` (which rebases cwd
    away from the user's working dir).
    """
    try:
        path = resolve_rules_path(rules_file, input_path=input_path)
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
@bulk_data_option
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
@click.option(
    "--cite-rules/--no-cite-rules",
    "cite_rules",
    default=True,
    show_default=True,
    help=(
        "Attach MTG Comprehensive Rules citations for each violation "
        "reason. Pass --no-cite-rules to skip. When no CR file is found "
        "next to the deck JSON or in cwd, citations are silently "
        "omitted (with an error note in the JSON)."
    ),
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
    bulk_data: Path | None,
    output_path: Path | None,
    rules_file: Path | None,
    *,
    cite_rules: bool,
) -> None:
    """Audit DECK_PATH for format legality, color identity, and singleton rule."""
    result = legality_audit(acquire_for_cli(deck_path, bulk_data))

    if cite_rules:
        _attach_rule_citations(result, rules_file, input_path=deck_path)

    if output_path is None:
        output_path = _default_output_path(
            deck_path.read_text(encoding="utf-8"), sidecar_path(deck_path)
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    click.echo(render_text_report(result), nl=False)
    click.echo(f"\nFull JSON: {output_path}")
