"""Commander multipliers — the deck cards the cut checklist treats as near-untouchable.

A card multiplies a commander when it:

- **copies the commander** — a token copy or ``BecomeCopy`` clone whose copied object
  can be the commander (Helm of the Host's token "isn't legendary", its ruling; a copy
  limited to a nonlegendary creature, Kiki-Jiki or Cytoshape, never copies a legendary
  commander), or a copy of the commander *spell* (Double Major; Echoes of Eternity's
  cast copy);
- **makes an ability the commander has trigger additional times** (CR 603.2d) — a
  ``DoubleTriggers`` static whose cause reaches one of its triggers (Isshin's ruling:
  only "triggered abilities with conditions that are directly related to attacking";
  Yarok's "a permanent entering" includes a land, so it doubles landfall) and whose
  affected filter covers it. A doubler of permanents' abilities never reaches a
  trigger that functions on the stack — "When you cast this spell" (CR 109.2: a type
  word alone means a permanent);
- **copies such an ability** (CR 707.10) — a ``CopySpell`` of a stack ability of the
  kind the commander has (Strionic Resonator: triggered; Rings of Brighthearth:
  non-mana activated, as it's activated);
- **lends the commander its activated abilities from another zone** (Thranduil, the
  Elvenking "has all activated abilities of all Elf cards in your graveyard").

A doubler's cause is matched to the commander's trigger by card TYPE, so Panharmonicon
("an artifact or creature entering") doesn't count for a landfall commander even
though an artifact land would set off both.

Every read is over phase's corrected trees except one gap: phase parks Thranduil's
grant as an ``Unimplemented`` residue, so the grant's type and zone are read from that
residue's own text — only while it is there, guarded by a ``retirement_canary`` test.
The candidate card's side (its type, its activated abilities) is read off its tree.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
from mtg_utils._card_ir.crosswalk.reads import (
    ObjectFacts,
    copied_ability_kind,
    double_triggers_cause,
    filter_admits,
    filter_core_types,
    tag_of,
    trigger_subject,
)
from mtg_utils._card_ir.trees import object_facts, trees_for

# A DoubleTriggers cause -> the commander trigger event it reaches.
_CAUSE_EVENTS = {
    "EntersBattlefield": "enters",
    "CreatureDying": "dies",
    "CreatureAttacking": "attacks",
}
_PERMANENT_TYPES = frozenset(
    {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
)
# The gap-gated text read: phase's residue for the zone grant it can't parse ("~ has
# all activated abilities of all Elf cards in your graveyard"). Retire with the canary.
ZONE_GRANT_RESIDUE = "has all activated abilities of all"
_ZONE_GRANT_RE = re.compile(
    re.escape(ZONE_GRANT_RESIDUE) + r" (\w+) cards? (?:in your (\w+)|(exiled) with)",
    re.IGNORECASE,
)


class _Trigger:
    """One of the commander's triggered abilities: its event, the types it watches,
    and whether it functions on the battlefield (vs. on the stack)."""

    def __init__(self, unit: AbilityUnit) -> None:
        self.event = unit.trigger_event
        self.watched = set(trigger_subject(unit.node))
        zones = getattr(unit.node, "trigger_zones", None)
        self.on_battlefield = not isinstance(zones, list) or "Battlefield" in zones


class _Commander:
    """What a commander's trees say it is and has."""

    def __init__(self, record: Mapping) -> None:
        self.name = record.get("name") or ""
        self.trees: tuple[ConceptTree, ...] = trees_for(dict(record))
        self.facts: ObjectFacts = object_facts(dict(record))
        self.triggers = [
            _Trigger(unit) for tree in self.trees for unit in tree.iter_units("trigger")
        ]
        self.activated = any(
            unit.kind == "Activated"
            and getattr(unit.node, "is_mana_ability", None) is not True
            for tree in self.trees
            for unit in tree.iter_units("ability")
        )

    def doubled_by(
        self, affected: object, cause: str, cause_types: tuple[str, ...]
    ) -> bool:
        """Whether a ``DoubleTriggers`` static reaches one of the commander's
        triggers: the cause fires it, and the affected filter covers the commander as
        the trigger's source — a permanent for a battlefield trigger, a spell
        (phase's ``Card`` type) for a stack one."""
        event = _CAUSE_EVENTS.get(cause)
        wanted = set(cause_types) or (
            set(_PERMANENT_TYPES) if cause == "EntersBattlefield" else {"Creature"}
        )
        if "Permanent" in wanted:
            wanted = set(_PERMANENT_TYPES)
        for trigger in self.triggers:
            if not self._source_covered(
                affected, on_battlefield=trigger.on_battlefield
            ):
                continue
            if cause == "Any":
                return True
            # A trigger watching the commander itself (SelfRef) watches its own types.
            seen = trigger.watched or set(self.facts.types)
            if trigger.event == event and ("Permanent" in seen or seen & wanted):
                return True
        return False

    def _source_covered(self, affected: object, *, on_battlefield: bool) -> bool:
        branches = (
            list(getattr(affected, "filters", ()) or ())
            if tag_of(affected) == "Or"
            else [affected]
        )
        for branch in branches:
            names_spell = "Card" in filter_core_types(branch)
            if names_spell == on_battlefield:
                continue  # a spell clause for a permanent's trigger, or vice versa
            if filter_admits(branch, self.facts) is not False:
                return True
        return False


def _can_be(
    target: object, unit: AbilityUnit, tree: ConceptTree, cmd: _Commander
) -> bool:
    """Whether a copy effect's ``target`` can be the commander. A ``ParentTarget``
    binds to the unit's own object filters — at least one, all admitting the
    commander (Cytoshape's "Choose a nonlegendary creature" is a residue phase
    leaves no filter for, so it can't be confirmed); an ``AttachedTo`` / equipped
    reference to what the card attaches to (its Equip / Attach target)."""
    tag = tag_of(target)
    if tag == "ParentTarget":
        filters = [n for n in unit.iter_typed() if tag_of(n) in ("Typed", "Or")]
        return bool(filters) and all(
            filter_admits(f, cmd.facts) is not False for f in filters
        )
    if tag in ("AttachedTo", "EquippedBy"):
        attach = [
            getattr(n, "target", None)
            for n in tree.iter_typed()
            if tag_of(n) == "Attach"
        ]
        return any(filter_admits(f, cmd.facts) is True for f in attach)
    return filter_admits(target, cmd.facts) is True


def _copy_reason(
    node: object, unit: AbilityUnit, tree: ConceptTree, cmd: _Commander
) -> str | None:
    tag = tag_of(node)
    if tag in ("CopyTokenOf", "BecomeCopy"):
        target = getattr(node, "target", None)
        return f"copies {cmd.name}" if _can_be(target, unit, tree, cmd) else None
    if tag != "CopySpell":
        return None
    if unit.trigger_event == "abilityactivated":
        # Rings of Brighthearth / Illusionist's Bracers copy an activated ability as
        # it's activated — an ability of whatever the trigger watches.
        watched = getattr(unit.node, "valid_card", None)
        if cmd.activated and (watched is None or _can_be(watched, unit, tree, cmd)):
            return f"copies {cmd.name}'s activated abilities"
        return None
    kind = copied_ability_kind(node)
    if kind is None:  # a spell copy: Double Major, Echoes of Eternity's cast copy
        target = getattr(node, "target", None)
        return (
            f"copies {cmd.name} as it's cast"
            if _can_be(target, unit, tree, cmd)
            else None
        )
    if (kind in ("Triggered", "Any") and cmd.triggers) or (
        kind in ("Activated", "Any") and cmd.activated
    ):
        return f"copies {cmd.name}'s abilities"
    return None


def _reason(card_trees: Sequence[ConceptTree], cmd: _Commander) -> str | None:
    """Why the card multiplies ``cmd``, or ``None``."""
    for tree in card_trees:
        for unit in tree.units:
            for node in unit.iter_typed():
                reason = _copy_reason(node, unit, tree, cmd)
                if reason:
                    return reason
        for unit in tree.iter_units("static"):
            cause = double_triggers_cause(unit.node)
            if cause is not None and cmd.doubled_by(
                getattr(unit.node, "affected", None), *cause
            ):
                return f"doubles {cmd.name}'s triggered abilities"
    return None


def _zone_grant_reason(
    card: Mapping, card_trees: Sequence[ConceptTree], cmd: _Commander
) -> str | None:
    """The gap-gated zone-grant arm (see the module docstring): the grant's type and
    zone come from the commander's residue; the candidate's side from its tree."""
    for residue in (r for tree in cmd.trees for r in tree.residues()):
        m = _ZONE_GRANT_RE.search(residue)
        if not m:
            continue
        facts = object_facts(dict(card))
        if m.group(1).lower() not in {
            t.lower() for t in (*facts.types, *facts.subtypes)
        }:
            return None
        zone = (m.group(2) or m.group(3) or "").lower()
        if any(
            unit.kind == "Activated"
            for tree in card_trees
            for unit in tree.iter_units("ability")
        ):
            return f"{cmd.name} uses its activated abilities from the {zone}"
    return None


def commander_multipliers(
    cards: Sequence[Mapping], commanders: Sequence[Mapping]
) -> dict[str, str]:
    """The deck cards that multiply a commander, by name, with the reason."""
    out: dict[str, str] = {}
    for record in commanders:
        cmd = _Commander(record)
        for card in cards:
            name = card.get("name") or ""
            if not name or name in out or name == cmd.name:
                continue
            trees = trees_for(dict(card))
            reason = _reason(trees, cmd) or _zone_grant_reason(card, trees, cmd)
            if reason:
                out[name] = reason
    return out
