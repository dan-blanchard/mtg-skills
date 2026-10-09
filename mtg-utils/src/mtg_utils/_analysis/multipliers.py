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

Every read is over phase's corrected trees. Thranduil's grant is a
``GrantAllActivatedAbilitiesOf`` modification on a static that affects the commander
itself, whose ``source`` filter names the card type and the zone (phase v0.104.0
parses it; through v0.94.0 it was a residue read by a text arm). The candidate
card's side (its type, changeling included; its activated abilities that work on
the battlefield, ``reads.activated_ability_units``) is read off its tree.

:func:`commander_multipliers` is the tuner's and proposal-check's view (one reason per
card); :func:`multiplier_reasons` lists every way one card does it, by kind, for
cut-check, and :func:`zone_grant` exposes the grant itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
from mtg_utils._card_ir.crosswalk.describe import unit_text
from mtg_utils._card_ir.crosswalk.reads import (
    ObjectFacts,
    activated_ability_units,
    bypasses_legend_rule,
    copied_ability_kind,
    double_triggers_cause,
    filter_admits,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    has_filter_property,
    iter_typed_nodes,
    tag_of,
    trigger_caster_scope,
    trigger_subject,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
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

#: A ``CopySpell`` of a stack ability → its :attr:`Multiplication.kind` (CR 707.10).
_STACK_ABILITY_KINDS = {
    "Triggered": "copy_triggered_ability",
    "Activated": "copy_activated_ability",
    "Any": "copy_activated_or_triggered",
}


#: Each :attr:`Multiplication.kind` → its family: ``"copy"`` (a copy of the
#: commander), ``"ability"`` (copies or extra triggers of its abilities) or
#: ``"zone_grant"``. The one place a kind's family is decided.
KIND_FAMILY: dict[str, str] = {
    "create_token_copy": "copy",
    "becomes_copy": "copy",
    "copy_commander_spell": "copy",
    "copy_triggered_ability": "ability",
    "copy_activated_ability": "ability",
    "copy_activated_or_triggered": "ability",
    "trigger_doubler": "ability",
    "zone_grant": "zone_grant",
}


class Multiplication(NamedTuple):
    """One way a card multiplies a commander: ``kind`` (a :data:`KIND_FAMILY`
    key), ``clause`` — the card's ability that does it, in words — and ``reason``,
    the one-line why the tuner and proposal-check print."""

    kind: str
    clause: str
    reason: str

    @property
    def family(self) -> str:
        return KIND_FAMILY[self.kind]


class ZoneGrant(NamedTuple):
    """A commander's grant of another zone's cards' activated abilities: the card
    type it names ("Elf") and the zone ("graveyard", "exile")."""

    card_type: str
    zone: str


class _Trigger:
    """One of the commander's triggered abilities: its event, the types it watches,
    and whether it functions on the battlefield (vs. on the stack)."""

    def __init__(self, unit: AbilityUnit) -> None:
        self.event = unit.trigger_event
        self.watched = set(trigger_subject(unit.node))
        zones = getattr(unit.node, "trigger_zones", None)
        self.on_battlefield = not isinstance(zones, list) or "Battlefield" in zones


def _grant_of(trees: Sequence[ConceptTree]) -> ZoneGrant | None:
    """The commander's own ``GrantAllActivatedAbilitiesOf`` whose source is one card
    type in a zone other than the battlefield (Thranduil, the Elvenking: "Elf cards
    in your graveyard"; Trazyn the Infinite: artifact cards in your graveyard)."""
    for tree in trees:
        for unit in tree.iter_units("static"):
            if tag_of(getattr(unit.node, "affected", None)) != "SelfRef":
                continue
            for mod in getattr(unit.node, "modifications", None) or ():
                if tag_of(mod) != "GrantAllActivatedAbilitiesOf":
                    continue
                source = getattr(mod, "source", None)
                words = filter_subtypes(source) or filter_core_types(source)
                zones = [z for z in filter_inzone_zones(source) if z != "Battlefield"]
                if len(words) == 1 and zones:
                    return ZoneGrant(words[0], zones[0].lower())
    return None


class Commander:
    """What a commander's trees say it is and has — built once, then asked about
    every card (:func:`multiplier_reasons`)."""

    def __init__(self, record: Mapping) -> None:
        self.name = record.get("name") or ""
        self.trees: tuple[ConceptTree, ...] = trees_for(dict(record))
        self.facts: ObjectFacts = object_facts(dict(record))
        self.triggers = [
            _Trigger(unit) for tree in self.trees for unit in tree.iter_units("trigger")
        ]
        #: Thranduil's grant (:func:`zone_grant`), or ``None``.
        self.grant: ZoneGrant | None = _grant_of(self.trees)
        #: Its non-mana activated abilities, in words (what an ability copier
        #: doubles — cut-check's ``commander_activated_abilities``).
        self.activated_texts: tuple[str, ...] = tuple(
            ability_texts(self.trees, include_mana=False)
        )
        self.activated = bool(self.activated_texts)

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


#: Filter properties that ask for a spell with targets — "target spell that targets
#: only a single permanent or player" (Chef's Kiss). A commander creature spell has
#: none: only instants, sorceries (CR 115.1a), Aura spells (115.1b) and a mutating
#: spell (702.140a) target.
_TARGETING_PROPERTIES = ("TargetsOnly", "HasSingleTarget")
#: Where a copy can find the commander: on the battlefield, or as a spell.
_COMMANDER_ZONES = frozenset({"Battlefield", "Stack"})


def _admits(filt: object, cmd: Commander, *, strict: bool) -> bool:
    """Whether a copy's filter can describe the commander where the copy looks:
    not an opponent's permanent (Venser, Fervent Forger), not a spell that targets,
    not a card in a graveyard or exile (Kaervek, the Punisher's "black card from
    your graveyard" — the commander is on the battlefield or the stack), and the
    filter admits its types (:func:`reads.filter_admits`; ``strict`` wants a
    confirmed yes, otherwise only no rules it out)."""
    if filter_controller(filt) == "Opponent":
        return False
    if any(has_filter_property(filt, p) for p in _TARGETING_PROPERTIES):
        return False
    zones = set(filter_inzone_zones(filt))
    if zones and not zones & _COMMANDER_ZONES:
        return False
    answer = filter_admits(filt, cmd.facts)
    return answer is True if strict else answer is not False


_BACK_REFERENCES = ("ParentTarget", "TriggeringSource")
_CHOSEN_TAGS = ("Typed", "Or", "And")


def _watcher(unit: AbilityUnit, node: object) -> object:
    """The trigger a back-reference in ``node`` answers to: a delayed trigger
    holding it (The Clone Saga's "When you next cast a creature spell this turn,
    copy it"; earthbend's "When it dies") — its watcher — else the unit's own."""
    for n in unit.iter_typed():
        if tag_of(n) != "CreateDelayedTrigger":
            continue
        if not any(x is node for x in iter_typed_nodes(getattr(n, "effect", None))):
            continue
        cond = getattr(n, "condition", None)
        return getattr(cond, "trigger", None) or cond
    return unit.node


def _watches_commander(trig: object, cmd: Commander) -> bool:
    """Whether the object a trigger watches can be the commander: a spell an
    opponent casts can't (Ominous Lockbox; CR 603.2's "whenever an opponent
    casts"), nor the card itself (Nacatl War-Pride's "copies of it")."""
    if isinstance(trig, TypedMirrorNode) and trigger_caster_scope(trig) == "opponents":
        return False
    watched = getattr(trig, "valid_card", None) or getattr(trig, "filter", None)
    if tag_of(watched) in (None, "SelfRef"):
        return False
    return _admits(watched, cmd, strict=False)


#: Zones a chosen object is taken from that a commander on the battlefield or the
#: stack isn't in (Jacob Frye's "target Assassin card … from your graveyard").
_ELSEWHERE = frozenset({"Graveyard", "Exile", "Library", "Hand"})


def _can_be(
    target: object,
    unit: AbilityUnit,
    tree: ConceptTree,
    cmd: Commander,
    node: object = None,
) -> bool:
    """Whether a copy effect's ``target`` can be the commander.

    A back-reference ("a copy of it", "a copy of that creature") binds to what the
    ability chose — its target filters, all admitting the commander (Rionya's
    "another target creature you control"), none taken from a graveyard or exile —
    or, choosing nothing, to what its trigger watches (:func:`_watcher`,
    :func:`_watches_commander`): "Whenever a nontoken creature you control enters …
    a copy of that creature" (Flameshadow Conjuring, Mirror March, Molten Echoes)
    can copy the commander as it enters; a choice phase leaves no filter for
    (Cytoshape's "Choose a nonlegendary creature") can't be confirmed. An
    ``AttachedTo`` / equipped reference names what the card attaches to."""
    tag = tag_of(target)
    if tag in _BACK_REFERENCES:
        chosen = [
            (t, getattr(n, "origin", None))
            for n in unit.iter_typed()
            if (t := getattr(n, "target", None)) is not None
            and tag_of(t) in _CHOSEN_TAGS
        ]
        if tag == "ParentTarget" and chosen:
            return all(
                origin not in _ELSEWHERE and _admits(f, cmd, strict=False)
                for f, origin in chosen
            )
        return _watches_commander(_watcher(unit, node), cmd)
    if tag in ("AttachedTo", "EquippedBy"):
        # Its Equip / Attach target, or an Aura's enchant types (Rowan's Talent:
        # "Enchant planeswalker").
        attach = [
            getattr(n, "target", None)
            for n in tree.iter_typed()
            if tag_of(n) == "Attach"
        ]
        if any(_admits(f, cmd, strict=True) for f in attach):
            return True
        return any(cmd.facts.has_type(t) for t in tree.card_enchant_core_types)
    return _admits(target, cmd, strict=True)


def _becomes_a_legend(
    node: object, unit: AbilityUnit, tree: ConceptTree, cmd: Commander
) -> bool:
    """Whether ``node`` makes a permanent already on the battlefield a copy of a
    legendary commander with nothing to keep both: a copy takes the original's
    supertypes (CR 707.2), the legend rule then puts one into the graveyard (CR
    704.5j — Mirage Mirror's ruling), and becoming a copy isn't entering, so no
    enters trigger fires. "Enters as a copy" (Spark Double, Clone) does enter (CR
    707.5); a token copy is created and enters too."""
    if tag_of(node) != "BecomeCopy":
        return False
    enters_as = unit.origin == "replacement" and (
        getattr(unit.node, "destination_zone", None) == "Battlefield"
    )
    return (
        not enters_as
        and cmd.facts.has_supertype("Legendary")
        and not bypasses_legend_rule(tree)
    )


def _copy_reason(
    node: object, unit: AbilityUnit, tree: ConceptTree, cmd: Commander
) -> tuple[str, str] | None:
    """``(kind, reason)`` when ``node`` copies the commander or its abilities."""
    tag = tag_of(node)
    if tag in ("CopyTokenOf", "BecomeCopy"):
        if not _can_be(getattr(node, "target", None), unit, tree, cmd, node):
            return None
        if _becomes_a_legend(node, unit, tree, cmd):
            return None
        kind = "create_token_copy" if tag == "CopyTokenOf" else "becomes_copy"
        return kind, f"copies {cmd.name}"
    if tag != "CopySpell":
        return None
    if unit.trigger_event in ("abilityactivated", "loyaltyabilityactivated"):
        # Rings of Brighthearth / Illusionist's Bracers copy an activated ability as
        # it's activated — an ability of whatever the trigger watches; Rowan's
        # Talent a loyalty ability of the planeswalker it enchants (CR 606.1).
        watched = getattr(unit.node, "valid_card", None)
        if cmd.activated and (watched is None or _can_be(watched, unit, tree, cmd)):
            return "copy_activated_ability", f"copies {cmd.name}'s activated abilities"
        return None
    kind = copied_ability_kind(node)
    if kind is None:  # a spell copy: Double Major, Echoes of Eternity's cast copy
        if any(tag_of(n) == "CastFromZone" for n in unit.iter_typed()):
            # Copying a card to cast the copy (CR 707.12) — Zethi's exiled
            # instants, Arcane Savant's card from outside the game, Kaervek's
            # graveyard card — never the commander spell on the stack.
            return None
        if not _can_be(getattr(node, "target", None), unit, tree, cmd, node):
            return None
        if unit.trigger_event == "cast_spell" and not _watches_commander(
            unit.node, cmd
        ):
            # A cast trigger copies spells only when the commander's own cast can
            # set it off: Ulalek's "Whenever you cast an Eldrazi spell" (a
            # colorless Eldrazi commander does), Verazol's kicked spell.
            return None
        return "copy_commander_spell", f"copies {cmd.name} as it's cast"
    if (kind in ("Triggered", "Any") and cmd.triggers) or (
        kind in ("Activated", "Any") and cmd.activated
    ):
        return _STACK_ABILITY_KINDS[kind], f"copies {cmd.name}'s abilities"
    return None


def _reasons(card_trees: Sequence[ConceptTree], cmd: Commander) -> list[Multiplication]:
    """Every way the card multiplies ``cmd``, one per ability."""
    out: list[Multiplication] = []
    for tree in card_trees:
        for unit in tree.units:
            for node in unit.iter_typed():
                hit = _copy_reason(node, unit, tree, cmd)
                if hit:
                    kind, reason = hit
                    out.append(Multiplication(kind, unit_text(unit, tree.name), reason))
                    break
        for unit in tree.iter_units("static"):
            cause = double_triggers_cause(unit.node)
            if cause is not None and cmd.doubled_by(
                getattr(unit.node, "affected", None), *cause
            ):
                out.append(
                    Multiplication(
                        "trigger_doubler",
                        unit_text(unit, tree.name),
                        f"doubles {cmd.name}'s triggered abilities",
                    )
                )
    return out


def zone_grant(commander: Mapping) -> ZoneGrant | None:
    """The commander's grant of another zone's cards' activated abilities, or
    ``None`` — the gap-gated text arm (see the module docstring): Thranduil, the
    Elvenking "has all activated abilities of all Elf cards in your graveyard" →
    ``ZoneGrant("Elf", "graveyard")``."""
    return _grant_of(trees_for(dict(commander)))


def ability_texts(trees: Sequence[ConceptTree], *, include_mana: bool) -> list[str]:
    """A card's activated abilities that work on the battlefield
    (``reads.activated_ability_units``), in words; ``include_mana`` keeps mana
    abilities (CR 605.1a)."""
    return [
        unit_text(unit, tree.name)
        for tree in trees
        for unit in activated_ability_units(tree, include_mana=include_mana)
    ]


def grant_abilities(card: Mapping, grant: ZoneGrant) -> list[str] | None:
    """The card's abilities a commander borrows through ``grant``, in words, or
    ``None`` when the card isn't of the granted type. A changeling card is every
    creature type in every zone (CR 702.73a, 604.3). Only abilities that work on
    the battlefield — cycling works only from its card's hand (CR 702.29a) — mana
    abilities included: a borrowed one (Priest of Titania's) is often the
    commander's best tool."""
    facts = object_facts(dict(card), zone="elsewhere")  # a card in that zone
    if not (facts.has_type(grant.card_type) or facts.has_subtype(grant.card_type)):
        return None
    return ability_texts(trees_for(dict(card)), include_mana=True)


def multiplier_reasons(card: Mapping, cmd: Commander) -> list[Multiplication]:
    """Every way ``card`` multiplies the commander, one per ability (empty when it
    doesn't, and for the commander itself) — cut-check reports these by family."""
    if not card.get("name") or card.get("name") == cmd.name:
        return []
    out = _reasons(trees_for(dict(card)), cmd)
    if cmd.grant is not None:
        abilities = grant_abilities(card, cmd.grant)
        if abilities:
            out.append(
                Multiplication(
                    "zone_grant",
                    abilities[0],
                    f"{cmd.name} uses its activated abilities from the "
                    f"{cmd.grant.zone}",
                )
            )
    return out


def commander_multipliers(
    cards: Sequence[Mapping], commanders: Sequence[Mapping]
) -> dict[str, str]:
    """The deck cards that multiply a commander, by name, with the reason."""
    out: dict[str, str] = {}
    for record in commanders:
        cmd = Commander(record)
        for card in cards:
            name = card.get("name") or ""
            if name in out:
                continue
            reasons = multiplier_reasons(card, cmd)
            if reasons:
                out[name] = reasons[0].reason
    return out
