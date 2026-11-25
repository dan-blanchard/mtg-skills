"""Shapes phase misparses, rewritten on the raw face records before strict load.

Beside the other raw-record corrections (``branches`` drops a branch phase
misreads, ``dropped_keywords`` restores a keyword it leaves out, ``shape_compat``
writes a renamed shape back in its old form): a row here is a clause phase types
as the wrong node, rewritten to the node phase types the same meaning as
elsewhere, so every read sees the clause the way it reads that node, with no read
taught a special case. Keyed on phase's structure, never the card's name or text.

* **A self-damage sweep.** "Each creature deals damage to itself equal to its
  power" (Solar Blaze, Wave of Reckoning; The Akroan War's chapter III, "Each
  tapped creature …") is parsed as the targeted form's damage effect with the
  target dropped. The targeted form ("Target creature deals damage to itself
  equal to its power" — Repentance) is a ``TargetOnly`` followed by
  ``DealDamage{amount: Power of Target, target: ParentTarget, damage_source:
  Target}``. Here the ``DealDamage`` heads its ability (an ``abilities`` entry or
  a trigger's ``execute``), so its ``ParentTarget`` names nothing and no read sees
  a population. Any object can deal damage (CR 120.2) and damage dealt to a
  creature is marked on it (120.3e), so each creature is marked with damage equal
  to its power, and one with toughness no greater than that is destroyed
  (704.5g): a sweep. It is rewritten to the ``DamageAll`` over every creature that
  phase types for "deals N damage to each creature", keeping phase's own
  ``amount`` and ``damage_source`` (each creature deals the damage, by its own
  power). The ``Power`` amount is the gate: a heading ``DealDamage`` of a fixed
  amount is "this creature deals N damage to itself" (Stuffy Doll; Vrondiss, Rage
  of Ancients), the card alone. The Akroan War's "tapped" is not in phase's
  record; it is read as every creature, which is a sweep either way.
  ``test_self_damage_sweep_canary`` fails once phase types the population itself.

* **A coin flip split in two.** "Flip a coin. If you win the flip, … If you lose
  the flip, …" (Desperate Gambit) is parsed as two flips: a ``FlipCoins`` with
  only its ``win_effect``, then, as its ``sub_ability``, a second ``FlipCoins``
  with the same ``flips`` and only its ``lose_effect``. The card flips one coin,
  which its flipper wins or loses (CR 705.2), and phase types every other flip
  that names both outcomes as one ``FlipCoins`` (Orcish Captain): the second
  flip's ``lose_effect`` is moved onto the first, and the second flip leaves the
  chain. The delayed form names only the losing outcome ("Flip a coin at the
  beginning of the next end step. If you lose the flip, sacrifice that
  creature" — Goblin Kites; Fickle Efreet's "flip a coin at end of combat"):
  phase types an outcome-less ``FlipCoins`` followed by the lose-only one, read
  the same way. ``test_split_coin_flip_canary`` and
  ``test_split_delayed_coin_flip_canary`` fail once phase types the one flip.

* **A chosen card type read as a creature type.** "Choose artifact or
  enchantment. Destroy all permanents of the chosen type" (Season of
  Gathering's second mode) is parsed as a ``Choose`` among ``Labeled``
  options naming card types, then a mass effect over ``Permanent`` with
  ``IsChosenCreatureType`` — a sweep of every permanent of a creature type,
  creatures included, where the card destroys only artifacts or only
  enchantments. The filter is rewritten to the listed card types (an ``Or``
  of one typed filter each), the most the choice can reach: Tinker Time took
  Season of Gathering as a creature sweeper (2026-11-02).
  ``test_chosen_card_type_sweep_canary`` fails once phase types the choice.

* **"Its controller manifests dread" with no player.** "Destroy target
  creature. Its controller manifests dread" (Unwanted Remake) types the
  manifest as a bare ``ManifestDread`` sub-ability, so every read takes it as
  yours. Phase types "Its controller investigates" after the same destroy as
  the sub-ability's ``player_scope: ParentObjectTargetController`` (Fateful
  Absence); that scope is written onto a bare ``ManifestDread`` whose parent's
  description says its controller manifests. ``test_its_controller_manifests_
  canary`` fails once phase types the player.

* **"Attack with one or more equipped creatures" with no filter.** "Whenever
  you attack a player with one or more equipped creatures, draw a card"
  (Akiri, Fearless Voyager) is a trigger whose mode phase leaves ``Unknown``
  (the clause's text), so no attack trigger at all. Phase types "Whenever you
  attack with one or more Zombies" with the attackers on ``valid_card``
  (Varina, Lich Queen) and an equipped creature as
  ``HasAttachment{Equipment}`` (Stone Haven Outfitter):
  that filter and the ``YouAttack`` mode are written on, for an equipped or
  enchanted attacker the parked clause names (read by the shared clause
  grammar, ``clause_grammar.attached_attackers_kind``).
  ``test_equipped_attack_canary`` fails once phase types the trigger.

* **A keyword grant to a subtype you control left unparsed.** "Auras attached
  to permanents you control have umbra armor" (Umbra Mystic) is an
  ``Unimplemented`` ``static_structure`` ability: phase's static parser failed
  on the line. Phase types umbra armor as the ``TotemArmor`` keyword (Hyena
  Umbra) and a keyword your permanents of a subtype have as a ``Continuous``
  static adding it (Puresteel Paladin's Equipment): a parked line the shared
  clause grammar reads as such a grant, and nothing else
  (``clause_grammar.subtype_keyword_grant``), is rewritten as that static over
  the subtype's permanents you control (an Aura attached to your permanent is
  read as yours). ``test_umbra_armor_grant_canary`` fails once phase types the
  static.

* **A spell exiled "instead" read as a move out of the graveyard.** "Counter
  target spell. If that spell is countered this way, exile it instead of putting
  it into its owner's graveyard" (Dissipate, Force of Negation, No More Lies; 21
  cards in v0.118.0, every one with that "instead") is parsed as the ``Counter``
  followed by a ``ChangeZone`` of its ``ParentTarget`` with ``origin: Graveyard``,
  ``destination: Exile``. A countered spell is put into its owner's graveyard
  (CR 701.6a), and an effect that uses "instead" is a replacement effect (614.1a):
  the spell goes from the stack to exile and never reaches the graveyard, as
  Arena logs it (one ``Countered`` move, Stack to Exile). A cast trigger's "exile
  that card instead of putting it into your graveyard as it resolves" (Gandalf of
  the Secret Fire, Goliath Daydreamer: the 2 ``SpellCast`` triggers carrying a
  ``ChangeZone`` of the cast spell out of the graveyard, both with that
  "instead") is the same misread. Phase types a spell leaving the stack with no
  ``origin`` and the spell as its target (Unsubstantiate's ``Bounce`` of a
  ``StackSpell``), so the ``origin`` is cleared: the move keeps its exile, and
  Goliath's dream counter, from no other zone. Phase's own forms hold neither:
  ``Counter.countered_spell_zone`` takes only ``Hand`` and ``Library``, and
  ``ExileResolvingSpellInsteadOfGraveyard`` (Feather, the Redeemed) no counters.
  ``crosswalk.diverts_from_graveyard`` reads the corrected shapes.
  ``test_countered_exile_instead_canary`` and
  ``test_cast_trigger_exile_instead_canary`` fail once phase types them.

* **A pump phase parks.** "Whenever ~ attacks or blocks, it gets
  +X/+X until end of turn, where X is the greatest power and/or toughness among
  other creatures you control" (Freelance Muscle) leaves an ``Unimplemented``
  ``where_x_binding`` residue holding only "where X is …": the pump itself is
  dropped, so no read sees one. Phase types a pump by an X it leaves unresolved
  as ``Pump`` / ``PumpAll`` with a ``Variable`` amount ("{X}, {T}: Target
  creature gets -X/+X until end of turn" — Belbe's Armor), on ``SelfRef`` for
  "~ gets" (Shivan Dragon), a creature filter with ``EquippedBy`` for "equipped
  creature gets" (Adventuring Gear) and one with ``controller: You`` /
  ``Another`` / ``Attacking`` for a group (Aardwolf's Advantage, Ambergris,
  Army of Allah). The residue is rewritten to that node where the shared clause
  grammar reads its sentence as a pump and nothing more
  (``clause_grammar.parked_pump``); a trigger's "it" is the trigger's own
  source, ``SelfRef`` where the trigger watches only itself and
  ``TriggeringSource`` otherwise, phase's two forms for it. Ten cards at
  v0.131.0. A clause parked whole that is such a pump is the same row: "Untap
  all creatures you control. Those creatures get +1/+1 until end of turn"
  (Gideon, Martial Paragon's ``plural_rider_after_mass_tap_population``),
  whose "those creatures" is the ``TrackedSet`` phase writes for "they" after
  a mass effect (Savage Offensive). A pump with a condition or a grant beside
  it is not ("if your team controls another Warrior, ~ gets +1/+1": the
  parked condition is the gap, and a ledger row serves it).
  ``test_parked_pump_canary`` fails once phase types the pump.

* **A perpetual pump phase parks.** "Those creatures perpetually get +2/+0"
  (Chaos Balor, after "deals 2 damage to each creature target player
  controls"), "~ and that creature perpetually get +1/+1" (Leaf-Leap Guide) are
  ``perpetual_modify_pt`` / ``unbound_subject`` residues. Phase types "~
  perpetually gets +1/+1" as ``ApplyPerpetual{target, modification:
  ModifyPowerToughness}`` (Accident-Prone Apprentice), which
  ``crosswalk.perpetual`` reads as a pump on a creature on the battlefield (the
  lane's own decision; "perpetually" is Arena-only, with no Comprehensive Rules
  entry). A residue the shared clause grammar reads as such a change
  (``clause_grammar.split_pump``) is written in that form, one change per
  subject that names a creature on the battlefield, on the target phase writes
  for the words: ``Any`` for "~" (Wary Zone Guard), ``SelfRef`` for an "it"
  after an instruction that leaves "~" on the battlefield or returns it there
  (Hex, Kellan's Companion; ``clause_grammar.lead_object``, which also tells a
  lead that takes the card away — "return ~ to its owner's hand and it …" stays
  parked), ``ParentTarget`` for "that Elf" after an untap of it or an "it"
  after "return it to the battlefield" (Vladimir and Godfrey),
  ``TriggeringSource`` for the creature whose entering triggered it (Lulu,
  Forgetful Hollyphant), ``TrackedSet`` for "those creatures" after a
  mass effect over them (Circadian Struggle), a ``Typed`` filter for a target
  (Davriel's Withering), the keywords it gains beside (Jaheira, Stirring
  Harper) and "up to one" as ``multi_target``. Where it lands is asked of
  ``_card_ir.perpetual_rules``, the rules ``crosswalk.perpetual`` asks of the
  typed tree. A residue that holds more — the
  instruction before the pump ("return ~ from your graveyard to the battlefield
  tapped and it perpetually gets +1/+0": Benalish Partisan, Managorger Phoenix,
  Hurkyl's Prodigy), a quoted ability (Sewer Plague), a grant the grammar can't
  read whole ("and gains reach, trample, and ward {2}": Wilson, Majestic Bear),
  a subject naming cards
  ("~ and that Dragon card": Darigaaz's Whelp; Freyalise, Skyshroud Partisan)
  — stays, the change chained after it (before it, where its ``ParentTarget``
  names the effect before the residue). Left parked: a subject naming only
  cards outside the battlefield (most of them: "creature cards in your
  graveyard", "the topmost creature card in your library"), a group ("creatures
  you control" — Legion of Clay, Lae'zel, Primal Warrior: phase's perpetual
  change over a population reaches only cards outside the battlefield, so no
  form says it), a creature "of your choice" (Alora, Cheerful Thief: chosen, not
  targeted), an X, a condition (Mace of Disruption).
  ``test_parked_perpetual_pump_canary`` fails once phase types them.

* **A pump as a clause's second instruction.** "Draw X cards and the chosen
  creatures get +X/+X and gain trample" (Spry and Mighty) is one
  ``unparsed_verb_arguments`` residue, which the recovery reads as the draw. The
  pump is typed after it as the ``Pump`` on the creatures the ``TargetOnly``
  chose (``ParentTarget``); the residue stays for the draw and the grant.
  ``test_second_verb_pump_canary`` fails once phase types it.

* **A static pump line parked beside a grant.** "Equipped creature gets +2/+1
  and has \"{T}, Unattach ~: Destroy target creature.\"" (Heartseeker) is a
  ``granter_reference_unreached`` ability. The pump is added as the
  ``Continuous`` static phase types for "Equipped creature gets +2/+0"
  (Bonesplitter); the residue stays for the granted ability.
  ``test_static_pump_line_canary`` fails once phase types it.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Iterator
from typing import NamedTuple

from mtg_utils._card_ir.clause_grammar import (
    ParkedPump,
    PumpSubject,
    SplitPump,
    attached_attackers_kind,
    binding_sentence,
    lead_object,
    parked_pump,
    split_pump,
    subtype_keyword_grant,
)
from mtg_utils._card_ir.dropped_keywords import PHASE_KEYWORDS, add_keyword, static_def
from mtg_utils._card_ir.perpetual_rules import (
    card_by_zones,
    earlier_object,
    tracked_population,
    trigger_object,
)

#: The fields that hold an ability's head body: a face's ``abilities`` entries
#: and a trigger's ``execute``. A ``sub_ability`` follows an earlier effect, whose
#: target its ``ParentTarget`` can name.
_HEAD_FIELDS = ("abilities", "execute")
_OWN_POWER = {"type": "Ref", "qty": {"type": "Power", "scope": {"type": "Target"}}}
_EACH_CREATURE = {
    "type": "Typed",
    "type_filters": ["Creature"],
    "controller": None,
    "properties": [],
}


def _head_bodies(node: object) -> Iterator[dict]:
    """Every ability body under ``node`` that heads its chain
    (:data:`_HEAD_FIELDS`), a granted or chapter ability's included."""
    if isinstance(node, list):
        for item in node:
            yield from _head_bodies(item)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key in _HEAD_FIELDS:
            for body in value if isinstance(value, list) else (value,):
                if isinstance(body, dict):
                    yield body
        yield from _head_bodies(value)


def _is_self_damage_sweep(effect: object) -> bool:
    """A heading ``DealDamage`` each object deals to itself by its own power, with
    no earlier effect for its ``ParentTarget`` to name."""
    return (
        isinstance(effect, dict)
        and effect.get("type") == "DealDamage"
        and effect.get("damage_source") == "Target"
        and (effect.get("target") or {}).get("type") == "ParentTarget"
        and effect.get("amount") == _OWN_POWER
    )


def _ability_bodies(node: object) -> Iterator[dict]:
    """Every ability-shaped body under ``node``: a dict holding an ``effect``."""
    if isinstance(node, list):
        for item in node:
            yield from _ability_bodies(item)
        return
    if not isinstance(node, dict):
        return
    if isinstance(node.get("effect"), dict):
        yield node
    for value in node.values():
        yield from _ability_bodies(value)


def _is_split_flip(body: dict) -> bool:
    """A ``FlipCoins`` with no ``lose_effect`` (a ``win_effect`` only, or no
    outcome at all) whose ``sub_ability`` is a ``FlipCoins`` of the same
    ``flips`` with only a ``lose_effect``."""
    flip = body["effect"]
    second = (body.get("sub_ability") or {}).get("effect") or {}
    return (
        flip.get("type") == "FlipCoins"
        and second.get("type") == "FlipCoins"
        and flip.get("flips") == second.get("flips")
        and not flip.get("lose_effect")
        and bool(second.get("lose_effect"))
        and not second.get("win_effect")
    )


#: The card types a ``Labeled`` choice may name for a chosen-type sweep
#: (CR 205.2a's permanent types).
_PERMANENT_CARD_TYPES = frozenset(
    {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
)


def _chosen_card_type_sweep(body: dict) -> list[str] | None:
    """The card types a ``Choose`` among ``Labeled`` card-type options names,
    when its ``sub_ability`` is a mass effect over ``Permanent`` filtered by
    ``IsChosenCreatureType``; else ``None``."""
    effect = body["effect"]
    if effect.get("type") != "Choose":
        return None
    choice = effect.get("choice_type")
    labeled = choice.get("Labeled") if isinstance(choice, dict) else None
    options = labeled.get("options") if isinstance(labeled, dict) else None
    if not options or not set(options) <= _PERMANENT_CARD_TYPES:
        return None
    nxt = (body.get("sub_ability") or {}).get("effect") or {}
    target = nxt.get("target") or {}
    props = [
        p.get("type") for p in target.get("properties") or () if isinstance(p, dict)
    ]
    if (
        target.get("type") != "Typed"
        or target.get("type_filters") != ["Permanent"]
        or props != ["IsChosenCreatureType"]
    ):
        return None
    return list(options)


#: A parent ability's description naming its target's controller as the one
#: who manifests (:func:`_bare_target_manifest`).
_CONTROLLER_MANIFESTS_RX = re.compile(r"\bIts controller manifests dread\b")


def _bare_target_manifest(body: dict) -> bool:
    """An ability whose ``sub_ability`` is a bare ``ManifestDread`` with no
    ``player_scope``, where the ability's own description says "Its controller
    manifests dread". The structure alone over-matches: five cards carry a
    scopeless ``ManifestDread`` sub, and four of them (Fear of Impostors,
    Glitch Interpreter, Stay Hidden, Stay Silent, Unnerving Grasp) have you
    manifest — only Unwanted Remake names the target's controller (census
    2026-11-02, v0.118.0)."""
    sub = body.get("sub_ability")
    return (
        isinstance(sub, dict)
        and (sub.get("effect") or {}).get("type") == "ManifestDread"
        and not sub.get("player_scope")
        and bool(_CONTROLLER_MANIFESTS_RX.search(str(body.get("description") or "")))
    )


def _attached_attack_kind(trig: object) -> str | None:
    """``Equipment`` / ``Aura`` for a trigger phase left an ``Unknown`` mode,
    with no ``valid_card``, whose parked clause watches equipped / enchanted
    attackers
    (:func:`~mtg_utils._card_ir.clause_grammar.attached_attackers_kind`)."""
    if not isinstance(trig, dict) or trig.get("valid_card"):
        return None
    mode = trig.get("mode")
    clause = mode.get("Unknown") if isinstance(mode, dict) else None
    return attached_attackers_kind(clause) if isinstance(clause, str) else None


def _parked_subtype_grant(body: dict) -> dict | None:
    """The ``Continuous`` static phase types for a keyword grant to a subtype you
    control (Puresteel Paladin's form), for an ``Unimplemented``
    ``static_structure`` ability whose line the clause grammar reads as one
    (:func:`~mtg_utils._card_ir.clause_grammar.subtype_keyword_grant`); else
    ``None``. Of the 16 parked keyword-grant statics in phase v0.118.0's
    card-data, only Umbra Mystic's grants to one subtype you control and nothing
    else (census 2026-11-09)."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented" or effect.get("name") != (
        "static_structure"
    ):
        return None
    line = str(effect.get("description") or "")
    grant = subtype_keyword_grant(line)
    adds = (
        [a for kw in sorted(grant[1]) if (a := add_keyword(kw, line))] if grant else []
    )
    if not grant or not adds:
        return None
    affected = {
        "type": "Typed",
        "type_filters": [{"Subtype": grant[0]}],
        "controller": "You",
        "properties": [],
    }
    return static_def(affected, adds, line)


#: A trigger returning a creature card "with power less than ~'s" (Mirko,
#: Obsessive Theorist), whose bound phase v0.118.0 drops from the target.
_RELATIVE_POWER_RETURN_RX = re.compile(r"\bcreature card with power less than ~'s\b")


def _relative_power_return(trig: object) -> dict | None:
    """The target filter of a trigger's graveyard-to-battlefield return that
    carries no power bound though its description says "with power less than
    ~'s", else ``None``."""
    if not isinstance(trig, dict) or not _RELATIVE_POWER_RETURN_RX.search(
        str(trig.get("description") or "")
    ):
        return None
    effect = (trig.get("execute") or {}).get("effect") or {}
    target = effect.get("target") or {}
    props = target.get("properties") or []
    if (
        effect.get("type") != "ChangeZone"
        or effect.get("destination") != "Battlefield"
        or target.get("type") != "Typed"
        or not any(
            p.get("type") == "InZone" and p.get("zone") == "Graveyard" for p in props
        )
        or any(p.get("type") == "PtComparison" for p in props)
    ):
        return None
    return target


#: The power bound phase types for "power less than this creature's"
#: (Apprentice Sharpshooter's form, with ``LT``).
_LESS_POWER_THAN_SOURCE = {
    "type": "PtComparison",
    "stat": "Power",
    "scope": "Current",
    "comparator": "LT",
    "value": {"type": "Ref", "qty": {"type": "Power", "scope": {"type": "Source"}}},
}


def _countered_graveyard_exile(body: dict) -> dict | None:
    """The ``sub_ability`` effect of a ``Counter`` that exiles its
    ``ParentTarget`` (the countered spell) with ``origin: Graveyard``, else
    ``None``. The structure is the key: all 21 cards carrying it say "exile it
    instead" (census 2026-11-09, v0.118.0)."""
    sub = (body.get("sub_ability") or {}).get("effect") or {}
    if body["effect"].get("type") == "Counter" and _graveyard_exile_of_parent(sub):
        return sub
    return None


def _graveyard_exile_of_parent(effect: dict) -> bool:
    """A ``ChangeZone`` exiling its ``ParentTarget`` with ``origin: Graveyard``."""
    return (
        effect.get("type") == "ChangeZone"
        and effect.get("origin") == "Graveyard"
        and effect.get("destination") == "Exile"
        and (effect.get("target") or {}).get("type") == "ParentTarget"
    )


def _cast_trigger_graveyard_exile(trig: object) -> dict | None:
    """The effect of a ``SpellCast`` trigger that exiles its ``ParentTarget``
    (the cast spell) with ``origin: Graveyard``, else ``None``: the 2 cards
    carrying it say "exile that card ... instead of putting it into your
    graveyard as it resolves" (census 2026-11-09, v0.118.0)."""
    if not isinstance(trig, dict) or trig.get("mode") != "SpellCast":
        return None
    effect = (trig.get("execute") or {}).get("effect") or {}
    return effect if _graveyard_exile_of_parent(effect) else None


def _chain(body: object) -> Iterator[dict]:
    """An ability body and each ``sub_ability`` after it."""
    while isinstance(body, dict):
        yield body
        body = body.get("sub_ability")


class _Earlier(NamedTuple):
    """What precedes a body in its chain: any effect at all, one that names
    an object (a target, a filter) a later "it" could mean, and the effect just
    before it."""

    any: bool = False
    object: bool = False
    last: dict | None = None


#: An effect's ``target`` that names the card itself or a player, never an
#: object a later "it" could mean.
_NO_OBJECT_TARGETS = frozenset({"SelfRef", "Controller", "Player"})


def _names_object(body: dict) -> bool:
    target = (body.get("effect") or {}).get("target")
    return isinstance(target, dict) and target.get("type") not in _NO_OBJECT_TARGETS


def _with_earlier(chain: Iterable[dict]) -> Iterator[tuple[dict, _Earlier]]:
    earlier = _Earlier()
    for body in chain:
        yield body, earlier
        effect = body.get("effect")
        earlier = _Earlier(
            any=True,
            object=earlier.object or _names_object(body),
            last=effect if isinstance(effect, dict) else None,
        )


def _chains_with_modes(head: object) -> Iterator[tuple[dict, _Earlier]]:
    """The bodies of ``head``'s chain, and of each mode's chain a body of it
    offers (``mode_abilities``: Chaos Balor's "choose two at random")."""
    for body, earlier in _with_earlier(_chain(head)):
        yield body, earlier
        for mode in body.get("mode_abilities") or ():
            yield from _chains_with_modes(mode)


def _described_bodies(rec: dict) -> Iterator[tuple[dict, str, dict | None, _Earlier]]:
    """``(body, description, trigger, earlier)`` for every body of each ability's
    and each trigger's own chain, its modes' included: the description is the
    ability's or trigger's whole text, ``trigger`` the trigger a body runs for
    (``None`` in an ability), ``earlier`` what precedes the body in its chain."""
    for ability in rec.get("abilities") or ():
        if isinstance(ability, dict):
            description = str(ability.get("description") or "")
            for body, earlier in _chains_with_modes(ability):
                yield body, description, None, earlier
    for trig in rec.get("triggers") or ():
        if isinstance(trig, dict):
            description = str(trig.get("description") or "")
            for body, earlier in _chains_with_modes(trig.get("execute")):
                yield body, description, trig, earlier


def _pump_amount(written: str) -> dict:
    """Phase's amount node for a signed amount as written: ``Variable`` for X
    ("+X", "-X"), ``Fixed`` otherwise."""
    if written[1:].upper() == "X":
        return {"type": "Variable", "value": written.lstrip("+").upper()}
    return {"type": "Fixed", "value": int(written)}


def _pump_target(pump: ParkedPump, trig: dict | None, earlier: _Earlier) -> dict | None:
    """The target phase writes for ``pump``'s subject; ``None`` for a pronoun
    that names nothing this row can know: an "it" outside a trigger or after an
    effect that names an object (it may be that object, phase's
    ``ParentTarget``; after "you get {E}" it is still the trigger's source —
    Razorfield Ripper), a "those creatures" with no earlier effect for it to
    name."""
    who = pump.subject
    if who.recipient == "self":
        return {"type": "SelfRef"}
    if who.recipient == "it":
        if trig is None or earlier.object:
            return None
        watches_itself = (trig.get("valid_card") or {}).get("type") == "SelfRef"
        return {"type": "SelfRef" if watches_itself else "TriggeringSource"}
    if who.recipient == "those":
        return {"type": "TrackedSet", "id": 0} if earlier.any else None
    if who.recipient not in ("attached", "group"):
        return None
    types: list[object] = ["Creature"]
    if who.subtype is not None:
        types.append({"Subtype": who.subtype})
    named = (who.attachment, "Another" if who.other else None)
    properties = [{"type": name} for name in named if name is not None]
    if who.attacking:
        properties.append({"type": "Attacking"})
    return {
        "type": "Typed",
        "type_filters": types,
        "controller": "You" if who.yours else None,
        "properties": properties,
    }


#: The targets phase writes on a ``Pump`` (one object); any other is a
#: ``PumpAll``'s (a group: a filter, or the set an earlier effect acted on).
_ONE_OBJECT = frozenset({"SelfRef", "TriggeringSource"})
#: The residues a pump is parked as: the binding of its X, and the "those
#: creatures get" rider after a mass untap. Any other residue holds a clause
#: this row has no business reading (a whole parked trigger among them).
_WHOLE_PUMP_RESIDUE = "plural_rider_after_mass_tap_population"


def _parked_pump(
    body: dict, description: str, trig: dict | None, earlier: _Earlier
) -> dict | None:
    """The typed pump for a body whose effect is a residue the clause grammar
    reads as a pump until end of turn and nothing more: a
    ``where_x_binding`` cut from a pump's sentence, or a parked clause that is
    the pump itself ("Those creatures get +1/+1 until end of turn" — Gideon,
    Martial Paragon, after "Untap all creatures you control"). Else ``None``."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented":
        return None
    text = str(effect.get("description") or "")
    if effect.get("name") == "where_x_binding":
        # its own text where it holds the instruction (The Kami War's "~ gets
        # +X/+0 until end of turn, where X is …"), else its sentence
        text = binding_sentence(text, description) or text
    elif effect.get("name") != _WHOLE_PUMP_RESIDUE:
        return None
    pump = parked_pump(text)
    # A pump with no duration is a static ability's line ("Enchanted creature
    # gets -X/-X, where X is …" — Death's Approach), which phase types as a
    # static's modifications, never as this one-shot effect.
    if pump is None or not pump.until_end_of_turn:
        return None
    target = _pump_target(pump, trig, earlier)
    if target is None:
        return None
    return {
        "type": "Pump" if target["type"] in _ONE_OBJECT else "PumpAll",
        "power": _pump_amount(pump.power),
        "toughness": _pump_amount(pump.toughness),
        "target": target,
    }


#: The residues a perpetual pump is parked as: the clause, and the "it" whose
#: subject phase couldn't bind.
_PERPETUAL_RESIDUES = frozenset({"perpetual_modify_pt", "unbound_subject"})
#: The residue a pump is parked in as a clause's second instruction ("draw X
#: cards and the chosen creatures get +X/+X …" — Spry and Mighty).
_SECOND_VERB_RESIDUE = "unparsed_verb_arguments"
#: The residue a static pump line is parked as beside the ability it grants
#: ("Equipped creature gets +2/+1 and has \"…\"" — Heartseeker).
_STATIC_LINE_RESIDUE = "granter_reference_unreached"


def _typed_zones(filt: object) -> tuple[bool, list[str]]:
    """Whether ``filt`` is a ``Typed`` filter, and the zones its ``InZone``
    properties name."""
    if not isinstance(filt, dict) or filt.get("type") != "Typed":
        return False, []
    return True, [
        p.get("zone")
        for p in filt.get("properties") or ()
        if isinstance(p, dict) and p.get("type") == "InZone"
    ]


def _creature_face(rec: dict) -> bool:
    return "Creature" in ((rec.get("card_type") or {}).get("core_types") or ())


def _on_the_battlefield_self(rec: dict, trig: dict | None) -> bool:
    """The card itself, a creature, in a trigger that works on the
    battlefield (``perpetual_rules.card_by_zones``)."""
    return (
        _creature_face(rec)
        and trig is not None
        and card_by_zones(trig.get("trigger_zones") or ()) == "self"
    )


def _trigger_object(trig: dict | None) -> str:
    if trig is None:
        return "unknown"
    return trigger_object(
        trig.get("mode") if isinstance(trig.get("mode"), str) else None,
        trig.get("destination"),
        watches_self=(trig.get("valid_card") or {}).get("type") == "SelfRef",
    )


def _perpetual_target(
    who: PumpSubject, pump: SplitPump, rec: dict, trig: dict | None, earlier: _Earlier
) -> dict | None:
    """The ``ApplyPerpetual`` target phase writes for ``who``, when ``who`` is a
    creature on the battlefield; else ``None``. "~" is ``Any`` (Wary Zone
    Guard's "~ perpetually gets"); an "it" names the card the instruction
    before it names (``clause_grammar.lead_object``): "~" left on or returned
    to the battlefield is ``SelfRef`` (Hex, Kellan's Companion's "it
    perpetually gets"), "it" returned there ``ParentTarget`` (Vladimir and
    Godfrey), and a card the lead takes away is no pump; "that creature" is
    the earlier effect's target (``ParentTarget``) or the trigger's object
    (``TriggeringSource`` — Lulu, Forgetful Hollyphant's "it perpetually
    gains"); "those creatures" the population an earlier mass effect acted on
    (``TrackedSet`` — Circadian Struggle's "those cards"); a target a ``Typed``
    filter (Davriel's Withering). A group ("creatures you control") has none:
    phase's perpetual change over a population reaches only cards outside the
    battlefield. Where each lands is ``_card_ir.perpetual_rules``'s answer."""
    last = earlier.last or {}
    if who.recipient == "self":
        return {"type": "Any"} if _on_the_battlefield_self(rec, trig) else None
    if who.recipient == "it":
        # the object the instruction before it names, where it leaves it
        lead = lead_object(pump.lead) if pump.lead else None
        if lead is None or lead.place == "away" or not _creature_face(rec):
            return None
        if lead.place == "unmoved" and not _on_the_battlefield_self(rec, trig):
            return None
        return {"type": "SelfRef" if lead.who == "self" else "ParentTarget"}
    typed, zones = _typed_zones(last.get("target"))
    if who.recipient == "that":
        if earlier.object:
            found = earlier_object(
                last.get("type"),
                destination=last.get("destination"),
                choice_zone=last.get("zone"),
                target_typed=typed,
                target_zones=zones,
            )
            return {"type": "ParentTarget"} if found == "battlefield" else None
        found = _trigger_object(trig)
        return {"type": "TriggeringSource"} if found == "battlefield" else None
    if who.recipient == "those":
        found = tracked_population(
            last.get("type"), target_typed=typed, target_zones=zones
        )
        return {"type": "TrackedSet", "id": 0} if found == "battlefield" else None
    if who.recipient == "target":
        types: list[object] = [
            {"Subtype": who.subtype} if who.subtype is not None else "Creature"
        ]
        return {
            "type": "Typed",
            "type_filters": types,
            "controller": "You" if who.yours else "Opponent" if who.opponents else None,
            "properties": [],
        }
    return None


def _sub_body(effect: dict, duration: str | None, *, up_to: bool) -> dict:
    """An ability body as phase chains one after another effect, targeting "up
    to one" object when ``up_to`` (Freyalise, Skyshroud Partisan's "Untap up to
    one target Elf")."""
    body = {
        "kind": "Spell",
        "effect": effect,
        "cost": None,
        "sub_ability": None,
        "duration": duration,
        "description": None,
        "target_prompt": None,
        "condition": None,
        "optional_targeting": False,
        "optional": False,
        "forward_result": False,
        "sub_link": "SequentialSibling",
    }
    if up_to:
        body["multi_target"] = {"min": 0, "max": {"type": "Fixed", "value": 1}}
    return body


class _PumpSplit(NamedTuple):
    """The typed pumps a parked clause holds (one per subject, each with
    whether it targets "up to one" object), whether the residue stays beside
    them (it holds more than the pumps: another instruction, a quoted ability,
    a subject naming cards), whether they go before it (their ``ParentTarget``
    names the effect before the residue), and their duration."""

    effects: list[tuple[dict, bool]]
    keep: bool
    before: bool
    duration: str | None


def _fixed(written: str) -> dict | None:
    return (
        None if written[1:].upper() == "X" else {"type": "Fixed", "value": int(written)}
    )


def _perpetual_split(
    body: dict, rec: dict, trig: dict | None, earlier: _Earlier
) -> _PumpSplit | None:
    """The typed ``ApplyPerpetual`` changes of a parked perpetual pump, each on
    a creature on the battlefield (:func:`_perpetual_target`); ``None`` when it
    names none, or an amount phase's perpetual change can't hold here (an X)."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented" or effect.get("name") not in (
        _PERPETUAL_RESIDUES
    ):
        return None
    pump = split_pump(str(effect.get("description") or ""))
    if pump is None or not pump.perpetual:
        return None
    power, toughness = _fixed(pump.power), _fixed(pump.toughness)
    if power is None or toughness is None:
        return None
    targets = [
        (_perpetual_target(who, pump, rec, trig, earlier), who.up_to)
        if who is not None
        else (None, False)
        for who in pump.subjects
    ]
    typed = [(t, up_to) for t, up_to in targets if t is not None]
    if not typed:
        return None
    keywords = [PHASE_KEYWORDS.get(k) for k in pump.keywords]
    modification: dict = {
        "kind": "ModifyPowerToughness",
        "power": power,
        "toughness": toughness,
    }
    if keywords and all(keywords):
        modification["keywords"] = keywords
    keep = bool(
        pump.lead or pump.rider or len(typed) < len(targets) or None in keywords
    )
    return _PumpSplit(
        effects=[
            (
                {
                    "type": "ApplyPerpetual",
                    "target": t,
                    "modification": copy.deepcopy(modification),
                },
                up_to,
            )
            for t, up_to in typed
        ],
        keep=keep,
        before=keep
        and not pump.lead
        and any(t["type"] == "ParentTarget" for t, _up_to in typed),
        duration=None,
    )


def _second_verb_split(
    body: dict, trig: dict | None, earlier: _Earlier
) -> _PumpSplit | None:
    """The typed pump until end of turn a clause states as its second
    instruction ("draw X cards and the chosen creatures get +X/+X and gain
    trample" — Spry and Mighty), beside the residue, which keeps the first
    instruction and any grant. "The chosen creatures" are the earlier effect's
    targets (``ParentTarget``)."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented" or effect.get("name") != (
        _SECOND_VERB_RESIDUE
    ):
        return None
    pump = split_pump(str(effect.get("description") or ""))
    duration = (
        "UntilEndOfTurn"
        if (pump is not None and pump.until_end_of_turn)
        else body.get("duration")
    )
    if (
        pump is None
        or pump.perpetual
        or not pump.lead
        or len(pump.subjects) != 1
        or duration != "UntilEndOfTurn"
    ):
        return None
    (who,) = pump.subjects
    if who is None:
        return None
    if who.recipient == "chosen":
        target = {"type": "ParentTarget"} if earlier.object else None
    else:
        target = _pump_target(
            ParkedPump(who, pump.power, pump.toughness, until_end_of_turn=True),
            trig,
            earlier,
        )
    if target is None:
        return None
    one = target["type"] in _ONE_OBJECT or target["type"] == "ParentTarget"
    return _PumpSplit(
        effects=[
            (
                {
                    "type": "Pump" if one else "PumpAll",
                    "power": _pump_amount(pump.power),
                    "toughness": _pump_amount(pump.toughness),
                    "target": target,
                },
                False,
            )
        ],
        keep=True,
        before=False,
        duration="UntilEndOfTurn",
    )


def _static_pump_line(body: dict) -> dict | None:
    """The ``Continuous`` static phase types for "Equipped creature gets +2/+1"
    (Bonesplitter's), for an ability phase parked whole as a static line that
    also grants a quoted ability ("Equipped creature gets +2/+1 and has
    \"{T}, Unattach ~: Destroy target creature.\"" — Heartseeker). The residue
    stays for the quote; ``None`` for any other line."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented" or effect.get("name") != (
        _STATIC_LINE_RESIDUE
    ):
        return None
    line = str(effect.get("description") or "")
    pump = split_pump(line)
    if (
        pump is None
        or pump.perpetual
        or pump.lead
        or pump.until_end_of_turn
        or body.get("duration")
        or len(pump.subjects) != 1
        or pump.subjects[0] is None
        or pump.subjects[0].recipient != "attached"
    ):
        return None
    power, toughness = _fixed(pump.power), _fixed(pump.toughness)
    if power is None or toughness is None:
        return None
    affected = {
        "type": "Typed",
        "type_filters": ["Creature"],
        "controller": None,
        "properties": [{"type": pump.subjects[0].attachment}],
    }
    mods = [
        {"type": "AddPower", "value": power["value"]},
        {"type": "AddToughness", "value": toughness["value"]},
    ]
    return static_def(affected, mods, line)


def _chained(bodies: list[dict], tail: object) -> object:
    """``bodies`` chained one after another, then ``tail``; its head."""
    nexts = [*bodies[1:], tail]
    for i, body in enumerate(bodies):
        body["sub_ability"] = nexts[i]
    return bodies[0] if bodies else tail


def _place_split(target: dict, split: _PumpSplit) -> None:
    """Write ``split``'s pumps into the residue's body ``target`` (in place):
    chained after the residue, or the first pump in the residue's place and
    the rest after it, then the residue when it stays."""
    pumps = [_sub_body(e, split.duration, up_to=u) for e, u in split.effects]
    tail = target.get("sub_ability")
    if split.keep and not split.before:
        target["sub_ability"] = _chained(pumps, tail)
        return
    first, *rest = pumps
    if split.keep:
        rest.append(dict(target))  # the residue's body as it was
    target["effect"] = first["effect"]
    target["sub_ability"] = _chained(rest, tail)
    if "multi_target" in first:
        target["multi_target"] = first["multi_target"]


def correct_misparsed_shapes(rec: dict) -> dict:
    """``rec`` with each misparsed shape rewritten (a copy when any)."""
    sweeps = [
        body for body in _head_bodies(rec) if _is_self_damage_sweep(body.get("effect"))
    ]
    bodies = list(_ability_bodies(rec))
    split_flips = [body for body in bodies if _is_split_flip(body)]
    chosen_types = [
        (body, types)
        for body in bodies
        if (types := _chosen_card_type_sweep(body)) is not None
    ]
    manifests = [body for body in bodies if _bare_target_manifest(body)]
    attacks = [
        (trig, kind)
        for trig in rec.get("triggers") or ()
        if (kind := _attached_attack_kind(trig)) is not None
    ]
    grants = [
        (body, static)
        for body in rec.get("abilities") or ()
        if isinstance(body, dict) and (static := _parked_subtype_grant(body))
    ]
    power_returns = [
        filt
        for trig in rec.get("triggers") or ()
        if (filt := _relative_power_return(trig)) is not None
    ]
    countered_exiles = [
        sub for body in bodies if (sub := _countered_graveyard_exile(body)) is not None
    ] + [
        effect
        for trig in rec.get("triggers") or ()
        if (effect := _cast_trigger_graveyard_exile(trig)) is not None
    ]
    pumps = [
        (body, pump)
        for body, description, trig, earlier in _described_bodies(rec)
        if (pump := _parked_pump(body, description, trig, earlier)) is not None
    ]
    splits = [
        (body, split)
        for body, _description, trig, earlier in _described_bodies(rec)
        if (
            split := _perpetual_split(body, rec, trig, earlier)
            or _second_verb_split(body, trig, earlier)
        )
        is not None
    ]
    static_lines = [
        (body, static)
        for body in rec.get("abilities") or ()
        if isinstance(body, dict) and (static := _static_pump_line(body))
    ]
    found = (
        sweeps,
        split_flips,
        chosen_types,
        manifests,
        attacks,
        grants,
        power_returns,
        countered_exiles,
        pumps,
        splits,
        static_lines,
    )
    if not any(found):
        return rec
    memo: dict[int, object] = {}
    out = copy.deepcopy(rec, memo)
    for body in sweeps:
        target = memo[id(body)]
        assert isinstance(target, dict)
        effect = target["effect"]
        target["effect"] = {
            "type": "DamageAll",
            "amount": effect["amount"],
            "target": copy.deepcopy(_EACH_CREATURE),
            "damage_source": effect["damage_source"],
        }
    for body in split_flips:
        target = memo[id(body)]
        assert isinstance(target, dict)
        second = target["sub_ability"]
        target["effect"]["lose_effect"] = second["effect"]["lose_effect"]
        target["sub_ability"] = second.get("sub_ability")
    for body, types in chosen_types:
        target = memo[id(body)]
        assert isinstance(target, dict)
        swept = target["sub_ability"]["effect"]
        swept["target"] = {
            "type": "Or",
            "filters": [
                {
                    "type": "Typed",
                    "type_filters": [t],
                    "controller": None,
                    "properties": [],
                }
                for t in types
            ],
        }
    for body in manifests:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["sub_ability"]["player_scope"] = {"type": "ParentObjectTargetController"}
    for trig, kind in attacks:
        target = memo[id(trig)]
        assert isinstance(target, dict)
        target["mode"] = "YouAttack"
        target["valid_card"] = {
            "type": "Typed",
            "type_filters": ["Creature"],
            "controller": None,
            "properties": [{"type": "HasAttachment", "kind": kind}],
        }
    for filt in power_returns:
        target = memo[id(filt)]
        assert isinstance(target, dict)
        target["properties"] = [
            *target.get("properties", []),
            copy.deepcopy(_LESS_POWER_THAN_SOURCE),
        ]
    for sub in countered_exiles:
        target = memo[id(sub)]
        assert isinstance(target, dict)
        target["origin"] = None
    for body, typed in pumps:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["effect"] = typed
        target["duration"] = "UntilEndOfTurn"
    for body, split in splits:
        target = memo[id(body)]
        assert isinstance(target, dict)
        _place_split(target, split)
    if static_lines:
        out["static_abilities"] = [
            *(out.get("static_abilities") or ()),
            *(static for _body, static in static_lines),
        ]
    if grants:
        parked = {id(memo[id(body)]) for body, _static in grants}
        out["abilities"] = [
            b for b in out.get("abilities") or () if id(b) not in parked
        ]
        out["static_abilities"] = [
            *(out.get("static_abilities") or ()),
            *(static for _body, static in grants),
        ]
    return out
