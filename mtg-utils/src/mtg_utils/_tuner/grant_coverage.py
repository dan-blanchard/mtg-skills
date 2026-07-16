"""Grant-covered roles (ADR-0040 §1, deck-forge CONTEXT.md "Grant-covered role").

Does a Spine role's resource repeat per creature/tribe body because the
COMMANDER's own text GRANTS it, rather than because the deck runs dedicated
cards for it? v1 scope: ``card_draw`` covered by a commander whose static
ability grants your creature board (or a tribal subset of it) a TRIGGERED
ability that draws a card on that recipient's own ETB/cast — the Sliver
Weftwinder shape ("Sliver creatures you control have 'When this creature
enters, ... draw a card.'").

This module NEVER moves a Slot band — ``slot_budgets`` counts literal cards
only, unchanged (ADR-0040 §1: "a mass grant never moves the number").
``covered_roles`` is consumed by ``_tuner.tune`` to *annotate* the budget row
for a covered role; ``_tuner.metrics.top_issues`` turns that annotation into
an advisory flag, and ``_tuner.swaps`` stops sourcing fills for it — the
shortfall stays visible with its real numbers, it just stops driving swaps.

The read is STRUCTURAL (Seam A concept trees — ``trees_for``), never oracle
text: a recipient card never emits the granted ability (crosswalk signal
emission stays strict per ADR-0040), so the coverage fact can only be read
off the GRANTER's own tree, by walking the grant's typed modification node.

Extending to another role: add a ``_grant_<role>`` predicate with the same
signature (``dict -> bool``) and a row in ``_ROLE_CHECKS`` — v1 wires
``card_draw`` only; do not add a role without its own CR-grounded shape
adjudication (mirroring ``_grant_draws``'s docstring).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from mtg_utils._card_ir.crosswalk import (
    filter_controller,
    filter_core_types,
    filter_predicates,
    iter_typed_nodes,
    tag_of,
)
from mtg_utils._deck_forge._ir_lookup import trees_for

# A single-permanent recipient (an Aura's EnchantedBy / an Equipment's
# EquippedBy — CR 303.4c / 301.5c) never scales with board count, so it can
# never cover a per-body Spine role no matter what it grants.
_SINGLE_PERMANENT_PREDS = frozenset({"EnchantedBy", "EquippedBy"})


def _is_creature_board_grant(sdef: object) -> bool:
    """True when a STATIC ability's ``affected`` filter is a creature-typed
    board you control (CR 205.3g / 613.1f layer 6) — the whole creature
    board, or a tribal subset of it (Weftwinder's "Sliver creatures you
    control"; subtype is not itself excluded here, unlike the broader
    ``crosswalk_signals._global_ability_grant`` gate this mirrors). Excludes
    an opponent-scoped grant and a single-permanent recipient."""
    aff = getattr(sdef, "affected", None)
    if tag_of(aff) != "Typed":
        return False
    ctrl = filter_controller(aff)
    if ctrl == "Opponent":
        return False
    preds = set(filter_predicates(aff))
    if preds & _SINGLE_PERMANENT_PREDS:
        return False
    owned = any(p == "Owned" or p.startswith("Owned") for p in preds)
    return "Creature" in filter_core_types(aff) and (ctrl == "You" or owned)


def _grant_trigger_event(trig: object) -> str | None:
    """CR 603.6a (enters) / 601.2c (casting) event read for a NESTED granted
    trigger node (phase's own ``mode``/``destination`` fields on a
    ``GrantTrigger`` modification's ``.trigger``) — the same two branches
    ``crosswalk_signals._trigger_event`` normalizes for TOP-LEVEL units,
    inlined here for this one nested position rather than reaching across
    package boundaries for a private helper. ``None`` for any other event
    (this v1 read only cares whether the grant repeats per recipient body)."""
    mode = getattr(trig, "mode", None)
    if mode in ("ChangesZone", "ChangesZoneAll"):
        dest = getattr(trig, "destination", None)
        return "enters" if dest == "Battlefield" else None
    if mode == "SpellCast":
        return "cast_spell"
    return None


def _grant_draws(record: dict) -> bool:
    """CR 113.3 (ability categories) / 604.3 (static-granted abilities) /
    603.6a: a static ability grants your creature board (or a tribal subset
    of it) a TRIGGERED ability that fires once per recipient
    entering/being cast, whose effect includes a Draw — the Sliver
    Weftwinder shape. Genuinely repeatable per body: CR 603.6a's ETB
    trigger fires independently for every qualifying permanent that
    enters, so a bigger creature count is a bigger draw engine, exactly
    like a dedicated repeatable-draw card would be.

    Structural only — walks the commander's own concept trees (Seam A,
    ``trees_for``); a recipient card never emits this (crosswalk signal
    emission stays strict per ADR-0040), so there is no signal KEY to
    consume here, only the tree."""
    for tree in trees_for(record):
        for unit in tree.units:
            if unit.origin != "static" or not _is_creature_board_grant(unit.node):
                continue
            for n in iter_typed_nodes(unit.node):
                if tag_of(n) != "GrantTrigger":
                    continue
                trig = getattr(n, "trigger", None)
                if trig is None or _grant_trigger_event(trig) is None:
                    continue
                execute = getattr(trig, "execute", None)
                if execute is None:
                    continue
                if any(tag_of(m) == "Draw" for m in iter_typed_nodes(execute)):
                    return True
    return False


# role -> structural coverage predicate. v1: card_draw only (ADR-0040 §1).
_ROLE_CHECKS: dict[str, Callable[[dict], bool]] = {"card_draw": _grant_draws}


def covered_roles(commanders: Sequence[dict]) -> dict[str, str]:
    """``{role: covering_commander_name}`` for every Spine role a commander's
    own ability GRANT structurally covers. Checks every commander (partner
    pairs included); the first commander whose grant covers a role wins
    that role's entry. Never touches a Slot band — see the module
    docstring."""
    out: dict[str, str] = {}
    for role, check in _ROLE_CHECKS.items():
        for rec in commanders:
            if check(rec):
                out[role] = rec.get("name") or ""
                break
    return out
