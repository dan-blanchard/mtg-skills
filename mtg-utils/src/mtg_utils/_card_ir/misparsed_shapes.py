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
  lane's own decision; "perpetually" is Arena-only, outside the Comprehensive
  Rules — the repo's digital supplement, DD1.1, defines it). A residue the
  shared clause grammar reads as such a change (``clause_grammar.split_pump``)
  is written in that form, one change per subject that names a creature on
  the battlefield, on the target phase writes for the words: ``Any`` for "~"
  (Wary Zone Guard), ``SelfRef`` for an "it" after an instruction that leaves
  "~" on the battlefield or returns it there
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
  graveyard", "the topmost creature card in your library" — read in place by
  ``crosswalk.perpetual.card_boost_zones``, the ``card_boost`` lane), a group
  (the next row's), a creature "of your choice" (Alora, Cheerful Thief: chosen,
  not targeted), an X, a condition (Mace of Disruption).
  ``test_parked_perpetual_pump_canary`` fails once phase types them.

* **A perpetual boost to your team phase parks.** "Creatures you control
  perpetually get +1/+1" (Legion of Clay) is a ``perpetual_modify_pt`` residue,
  and phase has no perpetual form for a population on the battlefield (its
  engine enumerates one only in another zone). Dan's ruling (2026-11-25): it is
  written as a team pump with no end date, phase's ``PumpAll`` over the group
  (the ``Typed`` filter "creatures you control" types, with ``Another`` for
  "other", the subtype for "other Dinosaurs", ``IsChosenCreatureType`` for "of
  the chosen type") on a body lasting ``Permanent`` (phase's ``Duration`` for no
  end date, which GenericEffect bodies carry) — a direct rewrite, not a
  ``PumpAll`` the pump view marks perpetual: the view keys on
  ``ApplyPerpetual``, and a perpetual change over a group would have to be a
  node phase doesn't write before the view could read it. Every team lane then
  reads it as any other one-shot team pump. A clause naming cards beside the
  group ("creatures you control and creature cards in your hand, library, and
  graveyard" — Arming Gala; Coalition Construct, Stalwart Speartail, Lae'zel,
  Primal Warrior) keeps its residue for the cards, the pump chained after it;
  phase cut Arming Gala's residue at its zone list's comma, so its clause is
  read from the description (``clause_grammar.residue_clause``). A change to
  every card you own reaches your permanents of them too ("All creature cards
  you own with mana value 2 or less perpetually get +1/+0" — Naktamun Shines
  Again; Network Marauder, Unbreakable Remnant): that half is the same team
  pump over your owned permanents of those cards (``Owned``, with the cards'
  types, subtype, ``Cmc`` bound or ``Named``), the residue kept for the cards
  in every other zone. The subject is read by
  ``clause_grammar.perpetual_change``. Eight cards at v0.131.0.
  ``test_parked_perpetual_team_pump_canary`` and
  ``test_parked_perpetual_owned_team_pump_canary`` fail once phase types
  them.

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

* **A keyword's pump with no duration.** Exalted, battle cry and bushido are
  triggered abilities whose pump lasts until end of turn (CR 702.83a: "that
  creature gets +1/+1 until end of turn"; 702.91a: "each other attacking
  creature gets +1/+0 until end of turn"; 702.45a: "it gets +N/+N until end of
  turn"). Phase expands each keyword into its trigger (Akrasan Squire, Accorder
  Paladin, Samurai of the Pale Curtain) but leaves the body's ``duration``
  ``null``, which it writes ``UntilEndOfTurn`` for the same pump printed out
  (Glaze Fiend). Phase's intended shape, not a misparse: its engine resolves a
  pump with no duration as until end of turn (``pump::resolve``;
  vetting-2026-11-27), so this row writes the engine's default out for our
  reads, which see a timed pump only (51 of the 89 cards with one of the
  keywords would lose ``effect_boost``, measured 2026-11-27). A trigger with the
  keyword's own shape — its mode, the object it watches, the pump and where it
  lands — on a face that has the keyword gets the duration. It never retires, so
  it carries no canary (``test_keyword_pump_duration_is_the_engine_default_
  written_out`` pins it).

* **A trigger's "it" phase binds to the wrong object.** Four shapes, each
  read off the structure alone. (1) "Whenever ~ attacks, you may pay {E}{E}.
  If you do, put a +1/+1 counter on it" (the Thriving cycle, Riparian Tiger,
  Voltaic Brawler; 16 cards): the pump, counter or grant after only a
  ``PayCost`` is written on ``ParentTarget``, which names no earlier object;
  in a trigger that watches only the card, the "it" is the card, phase's
  ``SelfRef``. (2) Heroic's "Whenever you cast a spell that targets ~, put a
  +1/+1 counter on it" (Fabled Hero; 4 cards) writes the counter on
  ``TriggeringSource``, the spell; a counter goes on a permanent, and the spell
  targets the card, so it is ``SelfRef``. (3) A noncreature Aura's "it gets
  +3/+3" (Paroxysm) is written on ``SelfRef``, but a noncreature permanent has
  no power or toughness (CR 208.3): it is the enchanted creature.
  (4) A +1/+1 counter on "it" right after a move to a hand or to exile (First
  Responder, Torrent Sculptor): a counter on a card off the battlefield grows
  nothing, and the text names the card, so it is ``SelfRef``.
  ``test_paid_then_it_canary``, ``test_heroic_it_canary``,
  ``test_aura_self_pump_canary`` and ``test_moved_away_it_canary`` fail once
  phase binds them.
* **A pump in a verb list whose subject phase dropped.** "Until end of turn,
  target creature becomes black, gets +1/-1, and gains \"{B}: Regenerate ~.\""
  (Defiling Tears) is one ``unparsed_verb_arguments`` residue holding the verbs
  alone ("become black, gets +1/-1, and gains …"), with the body's
  ``UntilEndOfTurn`` and no target. The subject is read from the description
  (``clause_grammar.verb_list_pump``: the words before the list's first verb,
  the rest of the clause the residue's own), and the pump typed ahead of the
  residue as phase types "Target creature gets +2/-2 until end of turn" (Lash
  of Malice): a ``Pump`` on the ``Typed`` target, which phase dropped. The
  residue stays for the colour change and the granted ability, which no typed
  form here says faithfully. ``test_verb_list_pump_canary`` fails once phase
  types it.
* **A boon flattened into a pump.** "You get a boon with \"When you cast your
  next creature spell, it perpetually gets +1/+0.\"" (Flaming Fist Duskguard)
  is a ``Pump`` on the controller; Valiant Farewell's, a ``Pump`` on the "it" of
  its leaves-the-battlefield delayed trigger. Both are rewritten to phase's own
  ``CreateBoon`` (Jaheira, Stirring Harper's), so the card reads as boosting a
  creature spell. A pump on a player or on a creature that just left changes
  nothing; the boon text tells the two from Dark Salvation's player ``Pump``.
  ``test_flattened_boon_canary`` fails once phase types them.
* **A bite's target written on its dealer.** "Tap target untapped creature you
  control. If you do, it deals damage equal to its power to target attacking
  or blocking creature an opponent controls" (Spirit Flare; Crush Underfoot,
  Thorin, Mountain-king) types the damage on ``ParentTarget`` — the creature of
  yours the earlier effect named, which deals it — so the card reads as damage
  to itself, no bite. Where the description names a target creature as the
  recipient (``clause_grammar.power_damage_target``), the target is written
  back as phase types its own bites (Sylvan Smite: the ``Typed`` creature and
  ``damage_source: Target``, the earlier effect's creature dealing it;
  Catti-brie of Mithral Hall's ``Or`` of an attacking and a blocking one; "up
  to one" as ``multi_target``). ``test_bite_target_canary`` fails once phase
  types it.
* **A choice typed as a target.** "Choose a Giant creature you control" (Crush
  Underfoot) is a heading ``TargetOnly``, as if it targeted, and so is every
  selection of an ability that states a choice and names no target ("Choose
  five permanents you control" — Clarion Ultimatum; "then choose any number of
  permanents you control" — Ripples of Potential); the word "target" names no
  such object (CR 115.10a), so the choice is marked as made on resolution,
  phase's ``target_choice_timing: Resolution`` (``clause_grammar.
  opens_with_choice`` / ``chooses_without_target``). ``test_untargeted_choice_canary``
  fails once phase marks it.
* **One object a player controls named without "target".** "Create a token that's a
  copy of a permanent you control" (Awaken the Maelstrom), "transform an
  Incubator token you control" (Sunder the Gateway's mode, read off the card's
  mode description), "turn a creature you control face up" (Bustle), "may
  choose a creature they control" (Flaming Gambit: that player's creature)
  are typed as targets; the
  one such effect of its tag gets phase's resolution mark
  (``clause_grammar.untargeted_object_effects``). ``test_untargeted_object_
  canary`` fails once phase marks them.
* **A parked "For any number of opponents" head.** Windgrace's Judgment's head
  is an ``unrecognized_clause_head`` before a ``Destroy`` typed ``You``; it is
  written as Juvenile Mist Dragon's one target per opponent
  (``clause_grammar.per_opponent_head``). ``test_parked_per_opponent_head_
  canary`` fails once phase types it.
* **Three Alchemy "it"s and a draw trigger.** Penregon Besieged's parked
  "choose a creature with the least toughness among creatures your opponents
  control" (``clause_grammar.chosen_creature``) is typed as Crush Underfoot's
  ``TargetOnly`` choice made on resolution, so its "It perpetually gets -1/-1"
  lands on that creature; Territorial Strike's "If a Dragon creature was beheld, it
  perpetually gets +2/+2", written on the destroyed permanent, is written on
  phase's ``CostPaidObject`` (the beheld Dragon, CR 701.4a); Scour the Scene's
  "choose a creature card in your hand or a creature you control", a choice
  from the hand alone, gets the battlefield as phase's ``additional_zones``;
  Darigaaz's Whelp's ``Unknown`` "Whenever you draw a Dragon card" is phase's
  ``Drawn`` mode with the subtype on ``valid_card``
  (``clause_grammar.drawn_card_subtype``). ``test_parked_choice_canary``,
  ``test_beheld_it_canary``, ``test_hand_or_battlefield_choice_canary`` and
  ``test_parked_draw_trigger_canary`` fail once phase types them.

Pure functions over plain dicts; nothing here reads the mirror or a tree.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Iterator
from typing import NamedTuple

from mtg_utils._card_ir.clause_grammar import (
    CardGroup,
    ChosenCreature,
    ParkedPump,
    PerpetualSubject,
    PowerDamageTarget,
    PumpSubject,
    SplitPump,
    attached_attackers_kind,
    binding_sentence,
    chooses_without_target,
    chosen_creature,
    drawn_card_subtype,
    lead_object,
    opens_with_choice,
    parked_perpetual_change,
    parked_pump,
    per_opponent_head,
    power_damage_target,
    split_pump,
    subtype_keyword_grant,
    untargeted_object_effects,
    verb_list_pump,
)
from mtg_utils._card_ir.dropped_keywords import PHASE_KEYWORDS, add_keyword, static_def
from mtg_utils._card_ir.perpetual_rules import (
    PERPETUAL_RESIDUES,
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
    return _group_filter(who)


def _group_filter(who: PumpSubject) -> dict:
    """The ``Typed`` filter phase writes for a group of creatures or the one an
    Equipment or Aura is attached to: "equipped creature" (``EquippedBy``),
    "other creatures you control" (``Another``), "attacking creatures", "Ally
    creatures you control" (the subtype), "of the chosen type"
    (``IsChosenCreatureType`` — Coalition Construct)."""
    types: list[object] = ["Creature"]
    if who.subtype is not None:
        types.append({"Subtype": who.subtype})
    named = (
        who.attachment,
        "Another" if who.other else None,
        "Attacking" if who.attacking else None,
        "IsChosenCreatureType" if who.chosen_type else None,
    )
    return {
        "type": "Typed",
        "type_filters": types,
        "controller": "You" if who.yours else None,
        "properties": [{"type": name} for name in named if name is not None],
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
        return _target_filter(who)
    return None


def _target_filter(who: PumpSubject) -> dict:
    """The ``Typed`` filter phase writes for a targeted creature: "target
    creature", "target creature an opponent controls" (Davriel's Withering), "up
    to one target Soldier" (the subtype alone)."""
    return {
        "type": "Typed",
        "type_filters": [
            {"Subtype": who.subtype} if who.subtype is not None else "Creature"
        ],
        "controller": "You" if who.yours else "Opponent" if who.opponents else None,
        "properties": [],
    }


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
        PERPETUAL_RESIDUES
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


def _owned_filter(cards: CardGroup) -> dict:
    """The ``Typed`` filter phase writes for your permanents of the cards a
    perpetual change names "you own" in every zone: the card types and subtype
    ("artifact creature cards" — Network Marauder; "Spacecraft cards"), the
    mana value bound (``Cmc`` — Naktamun Shines Again's "with mana value 2 or
    less") and the name (``Named`` — Unbreakable Remnant), owned by you
    (``Owned``, CR 108.3)."""
    types: list[object] = list(cards.card_types)
    if cards.subtype is not None:
        types.append({"Subtype": cards.subtype})
    properties: list[dict] = [{"type": "Owned", "controller": "You"}]
    if cards.mana_value_max is not None:
        properties.append(
            {
                "type": "Cmc",
                "comparator": "LE",
                "value": {"type": "Fixed", "value": cards.mana_value_max},
            }
        )
    if cards.named is not None:
        properties.append({"type": "Named", "name": cards.named})
    return {
        "type": "Typed",
        "type_filters": types,
        "controller": None,
        "properties": properties,
    }


def _team_targets(subject: PerpetualSubject) -> dict | None:
    """The population on the battlefield a perpetual change's subject names,
    as phase's filter: a group of your creatures (:func:`_group_filter`), or
    your permanents of the cards you own (:func:`_owned_filter`)."""
    if (
        isinstance(subject, PumpSubject)
        and subject.recipient == "group"
        and subject.yours
    ):
        return _group_filter(subject)
    if isinstance(subject, CardGroup) and subject.owned and subject.filter_read:
        return _owned_filter(subject)
    return None


def _perpetual_team_split(body: dict, description: str) -> _PumpSplit | None:
    """The team pump with no end date (a ``PumpAll`` lasting ``Permanent``) for
    each population on the battlefield a parked perpetual change names: a group
    of your creatures ("creatures you control perpetually get +1/+1" — Legion of
    Clay), and your permanents of the cards it names "you own" in every zone
    ("All creature cards you own with mana value 2 or less …" — Naktamun Shines
    Again). The residue stays beside it for the cards outside the battlefield
    ("… and creature cards in your hand, library, and graveyard" — Arming Gala;
    every card you own). Phase writes no perpetual change over a population on
    the battlefield (its engine enumerates one only in another zone). ``None``
    for a clause naming no such population, another object on the battlefield
    (the perpetual row's), or an amount that isn't fixed."""
    effect = body.get("effect") or {}
    if effect.get("type") != "Unimplemented" or effect.get("name") != (
        "perpetual_modify_pt"
    ):
        return None
    change = parked_perpetual_change(str(effect.get("description") or ""), description)
    if change is None:
        return None
    teams = [t for s in change.subjects if (t := _team_targets(s)) is not None]
    if not teams or any(
        isinstance(s, PumpSubject) and s.recipient != "group" for s in change.subjects
    ):
        return None
    power, toughness = _fixed(change.power), _fixed(change.toughness)
    if power is None or toughness is None:
        return None
    return _PumpSplit(
        effects=[
            (
                {
                    "type": "PumpAll",
                    "power": copy.deepcopy(power),
                    "toughness": copy.deepcopy(toughness),
                    "target": target,
                },
                False,
            )
            for target in teams
        ],
        keep=len(teams) < len(change.subjects)
        or any(isinstance(s, CardGroup) for s in change.subjects),
        before=False,
        duration="Permanent",
    )


def _verb_list_split(body: dict, description: str) -> _PumpSplit | None:
    """The typed pump until end of turn among a verb list phase parked without
    its subject ("Until end of turn, target creature becomes black, gets
    +1/-1, and gains \"{B}: Regenerate ~.\"" — Defiling Tears, whose residue is
    "become black, gets +1/-1, and gains …"): a ``Pump`` on the target the
    description names (``clause_grammar.verb_list_pump``), as phase types "Target
    creature gets +2/-2 until end of turn" (Lash of Malice), ahead of the
    residue, which keeps the colour change and the granted ability."""
    effect = body.get("effect") or {}
    if (
        effect.get("type") != "Unimplemented"
        or effect.get("name") != _SECOND_VERB_RESIDUE
        or body.get("duration") != "UntilEndOfTurn"
    ):
        return None
    pump = verb_list_pump(str(effect.get("description") or ""), description)
    if pump is None or pump.subject.recipient != "target":
        return None
    who = pump.subject
    target = _target_filter(who)
    return _PumpSplit(
        effects=[
            (
                {
                    "type": "Pump",
                    "power": _pump_amount(pump.power),
                    "toughness": _pump_amount(pump.toughness),
                    "target": target,
                },
                who.up_to,
            )
        ],
        keep=True,
        before=True,
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


#: The pump keywords phase expands into a trigger, in its spelling, with the
#: trigger each one defines: its mode(s), the object it watches, and where the
#: pump lands. Exalted: "Whenever a creature you control attacks alone, that
#: creature gets +1/+1 until end of turn" (CR 702.83a); battle cry: "Whenever
#: this creature attacks, each other attacking creature gets +1/+0 until end of
#: turn" (702.91a); bushido N: "Whenever this creature blocks or becomes
#: blocked, it gets +N/+N until end of turn" (702.45a).
_KEYWORD_PUMPS: dict[str, tuple[frozenset[str], str, str, str]] = {
    "Exalted": (frozenset({"Attacks"}), "Typed", "Pump", "TriggeringSource"),
    "Battlecry": (frozenset({"Attacks"}), "SelfRef", "PumpAll", "Typed"),
    "Bushido": (frozenset({"Blocks", "BecomesBlocked"}), "SelfRef", "Pump", "SelfRef"),
}


def _raw_keyword(kw: object) -> str:
    """A raw keyword's name: a bare spelling, or a parameterized one's key
    (``{"Bushido": 1}``)."""
    if isinstance(kw, dict) and len(kw) == 1:
        kw = next(iter(kw))
    return kw if isinstance(kw, str) else ""


def _keyword_pump_bodies(rec: dict) -> list[dict]:
    """The trigger bodies phase built from a pump keyword the face has
    (:data:`_KEYWORD_PUMPS`) and left with no ``duration``: the keyword's
    trigger shape, its pump alone, nothing timed."""
    shapes = [
        _KEYWORD_PUMPS[name]
        for name in {_raw_keyword(k) for k in rec.get("keywords") or ()}
        if name in _KEYWORD_PUMPS
    ]
    out: list[dict] = []
    for trig in rec.get("triggers") or ():
        body = trig.get("execute") if isinstance(trig, dict) else None
        if not isinstance(body, dict) or body.get("duration") is not None:
            continue
        effect = body.get("effect") or {}
        watched = (trig.get("valid_card") or {}).get("type")
        target = (effect.get("target") or {}).get("type")
        if body.get("sub_ability") is None and any(
            trig.get("mode") in modes
            and watched == watch
            and effect.get("type") == verb
            and target == lands
            for modes, watch, verb, lands in shapes
        ):
            out.append(body)
    return out


#: The effects whose "it" a trigger's anaphora rows retarget: the ones that
#: raise or grant something to a creature.
_ANAPHOR_EFFECTS = frozenset({"Pump", "PutCounter", "GenericEffect"})


def _paid_then_it_bodies(rec: dict) -> list[dict]:
    """The "you may pay X. If you do, it …" bodies of a trigger that watches only
    the card (``valid_card`` ``SelfRef``): every body before it a ``PayCost``,
    so its ``ParentTarget`` names no earlier object — the "it" is the card
    (Riparian Tiger, the Thriving cycle, Voltaic Brawler; 16 cards at v0.131.0,
    every one "it" the card)."""
    out: list[dict] = []
    for trig in rec.get("triggers") or ():
        if not isinstance(trig, dict) or (trig.get("valid_card") or {}).get("type") != (
            "SelfRef"
        ):
            continue
        chain = list(_chain(trig.get("execute")))
        for i, body in enumerate(chain):
            effect = body.get("effect") or {}
            if (
                i
                and effect.get("type") in _ANAPHOR_EFFECTS
                and (effect.get("target") or {}).get("type") == "ParentTarget"
                and all(
                    (b.get("effect") or {}).get("type") == "PayCost" for b in chain[:i]
                )
            ):
                out.append(effect)
    return out


def _targets_the_card(filt: object) -> bool:
    """A cast trigger's ``valid_card`` that is "a spell that targets ~"."""
    return isinstance(filt, dict) and any(
        isinstance(p, dict)
        and p.get("type") == "Targets"
        and (p.get("filter") or {}).get("type") == "SelfRef"
        for p in filt.get("properties") or ()
    )


def _heroic_it_effects(rec: dict) -> list[dict]:
    """The effects of "Whenever you cast a spell that targets ~, put a +1/+1
    counter on it" (Fabled Hero, Lagonna-Band Trailblazer, Bloodcrazed Hoplite,
    Sage of Hours: the 4 at v0.131.0) that phase writes on ``TriggeringSource``,
    the spell: a counter goes on a permanent, and the spell targets the card."""
    out: list[dict] = []
    for trig in rec.get("triggers") or ():
        if not isinstance(trig, dict) or trig.get("mode") != "SpellCast":
            continue
        if not _targets_the_card(trig.get("valid_card")):
            continue
        for body in _chain(trig.get("execute")):
            effect = body.get("effect") or {}
            if (
                effect.get("type") in _ANAPHOR_EFFECTS
                and (effect.get("target") or {}).get("type") == "TriggeringSource"
            ):
                out.append(effect)
    return out


#: The moves that take an object off the battlefield, after which a +1/+1
#: counter on "it" can't be that object's.
_MOVES_AWAY = frozenset({"Hand", "Exile"})


def _moved_away_its(rec: dict) -> list[dict]:
    """A +1/+1 counter on ``ParentTarget`` right after an effect that moved its
    object to a hand or to exile: "return another creature you control to its
    owner's hand, then put … +1/+1 counters … on this creature" (First
    Responder), "exile an instant or sorcery card from your graveyard. Put … +1/+1
    counters on this creature" (Torrent Sculptor). A counter on a card in a hand
    or in exile makes nothing bigger, and the text names the card; phase binds
    the "it" to the moved object. The 2 at v0.131.0 (the other 9 counters put on
    an exiled card are time, hit or discovery counters, and stay)."""
    out: list[dict] = []
    for body in _ability_bodies(rec):
        effect = body.get("effect") or {}
        moved = effect.get("type") == "Bounce" or (
            effect.get("type") == "ChangeZone"
            and effect.get("destination") in _MOVES_AWAY
        )
        sub = body.get("sub_ability")
        counter = (sub.get("effect") or {}) if isinstance(sub, dict) else {}
        if (
            moved
            and counter.get("type") == "PutCounter"
            and counter.get("counter_type") == "P1P1"
            and (counter.get("target") or {}).get("type") == "ParentTarget"
        ):
            out.append(counter)
    return out


#: The boon a "you get a boon with 'When you cast your next creature spell, it
#: perpetually gets +N/+M'" grants: phase's own ``CreateBoon`` shape (Jaheira,
#: Stirring Harper's, keywords dropped), the ``ApplyPerpetual`` filled per card.
_BOON_TEXT = 'boon with "when you cast your next creature spell, it perpetually gets'


def _creature_spell_boon(pump: dict) -> dict:
    """Phase's ``CreateBoon`` for a next-creature-spell perpetual pump of
    ``pump``'s size."""
    return {
        "type": "CreateBoon",
        "recipient": {"type": "Controller"},
        "trigger": {
            "mode": "SpellCast",
            "execute": {
                "kind": "Spell",
                "effect": {
                    "type": "ApplyPerpetual",
                    "target": {"type": "ParentTarget"},
                    "modification": {
                        "kind": "ModifyPowerToughness",
                        "power": copy.deepcopy(pump.get("power")),
                        "toughness": copy.deepcopy(pump.get("toughness")),
                    },
                },
                "cost": None,
                "sub_ability": None,
                "duration": None,
                "description": None,
                "target_prompt": None,
                "condition": None,
                "optional_targeting": False,
                "optional": False,
                "forward_result": False,
            },
            "valid_card": {
                "type": "Typed",
                "type_filters": ["Creature"],
                "controller": None,
                "properties": [],
            },
            "origin": None,
            "destination": None,
            "trigger_zones": ["Battlefield"],
            "phase": None,
            "optional": False,
            "damage_kind": "Any",
            "secondary": False,
            "valid_target": {"type": "Controller"},
            "valid_source": None,
            "description": None,
            "constraint": None,
            "condition": None,
            "batched": False,
        },
    }


def _flattened_boons(rec: dict) -> list[dict]:
    """The bodies whose ``effect`` is a next-creature-spell boon phase flattened
    into a plain ``Pump``: one on the controller (Flaming Fist Duskguard), or on
    the "it" of a leaves-the-battlefield delayed trigger (Valiant Farewell). A
    pump on a player, or on a creature that just left the battlefield, changes
    nothing, so either structure is a flattened grant; the boon text tells them
    from Dark Salvation's player-targeted ``Pump`` (the one other ``Pump`` on a
    player at v0.131.0). Phase types every other boon as ``CreateBoon``."""
    out: list[dict] = []
    for body, description, _trig, _earlier in _described_bodies(rec):
        if _BOON_TEXT not in description.lower():
            continue
        effect = body.get("effect") or {}
        if (
            effect.get("type") == "Pump"
            and (effect.get("target") or {}).get("type") == "Controller"
        ):
            out.append(body)
        elif effect.get("type") == "CreateDelayedTrigger" and str(
            (effect.get("condition") or {}).get("type") or ""
        ).startswith("WhenLeavesPlay"):
            inner = effect.get("effect")
            if not isinstance(inner, dict):
                continue
            pump = inner.get("effect") or {}
            if (
                pump.get("type") == "Pump"
                and (pump.get("target") or {}).get("type") == "ParentTarget"
            ):
                out.append(inner)
    return out


_ENCHANTED_CREATURE = {
    "type": "Typed",
    "type_filters": ["Creature"],
    "controller": None,
    "properties": [{"type": "EnchantedBy"}],
}


def _aura_self_pumps(rec: dict) -> list[dict]:
    """The pumps a noncreature Aura's trigger writes on ``SelfRef``: a
    noncreature permanent has no power or toughness (CR 208.3), so "it gets
    +3/+3" is the enchanted creature (Paroxysm, the one at v0.131.0). A bestow
    card is a creature when not attached and stays out."""
    card_type = rec.get("card_type") or {}
    if not isinstance(card_type, dict):
        return []
    if "Aura" not in (card_type.get("subtypes") or ()) or "Creature" in (
        card_type.get("core_types") or ()
    ):
        return []
    if any(_raw_keyword(k) == "Bestow" for k in rec.get("keywords") or ()):
        return []
    return [
        effect
        for trig in rec.get("triggers") or ()
        if isinstance(trig, dict)
        for body in _ability_bodies(trig.get("execute"))
        if (effect := body.get("effect") or {}).get("type") == "Pump"
        and (effect.get("target") or {}).get("type") == "SelfRef"
    ]


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
    if split.duration is not None:
        target["duration"] = split.duration
    target["sub_ability"] = _chained(rest, tail)
    if "multi_target" in first:
        target["multi_target"] = first["multi_target"]


#: A power-sized amount read off "its" — the pronoun's own subject (``Anaphoric``).
_ITS_POWER = {"type": "Ref", "qty": {"type": "Power", "scope": {"type": "Anaphoric"}}}


def _power_damage_filter(read: PowerDamageTarget) -> dict:
    """The filter phase writes for the target a bite names: a ``Typed`` creature
    (or subtype) with its controller, one arm per combat state ("target
    attacking or blocking creature an opponent controls": an ``Or`` of an
    attacking and a blocking one — Catti-brie of Mithral Hall)."""

    def arm(states: tuple[str, ...]) -> dict:
        return {
            "type": "Typed",
            "type_filters": [
                {"Subtype": read.subtype} if read.subtype is not None else "Creature"
            ],
            "controller": read.controller,
            "properties": [{"type": s} for s in states],
        }

    if len(read.states) > 1:
        return {"type": "Or", "filters": [arm((s,)) for s in read.states]}
    return arm(read.states)


def _bite_recipients(rec: dict) -> list[tuple[dict, PowerDamageTarget]]:
    """Each body whose damage equal to "its" power phase wrote on
    ``ParentTarget`` — the creature of yours the earlier effect named, the dealer
    itself — where the description names a target creature as the recipient
    (:func:`~mtg_utils._card_ir.clause_grammar.power_damage_target`): Spirit
    Flare, Crush Underfoot, Thorin, Mountain-king (3 cards at v0.133.0). It is
    written as phase writes its own bites ("Then that creature deals damage
    equal to its power to target creature you don't control" — Sylvan Smite):
    the recipient's filter, and ``damage_source: Target``, the earlier effect's
    creature dealing the damage (without it the spell, or Thorin himself, would
    deal it). The structure alone over-matches: of the 8 legal faces with this
    ``DealDamage`` after an earlier effect, Garruk Relentless's "to him" and
    Alpha Brawl's "to that creature" are no target creature (the grammar's
    read), Delirium's ability has no description to read (its sub-ability's),
    and Beastie Beatdown's dealer heads its own ability."""
    out: list[tuple[dict, PowerDamageTarget]] = []
    for body, description, _trig, earlier in _described_bodies(rec):
        effect = body.get("effect")
        if not (
            isinstance(effect, dict)
            and effect.get("type") == "DealDamage"
            and (effect.get("target") or {}).get("type") == "ParentTarget"
            and effect.get("amount") == _ITS_POWER
            and not effect.get("damage_source")
            and earlier.last is not None
        ):
            continue
        dealer = earlier.last.get("target") or {}
        if dealer.get("type") != "Typed" or dealer.get("controller") != "You":
            continue
        read = power_damage_target(description)
        if read is not None:
            out.append((body, read))
    return out


def _least_or_most(chosen: ChosenCreature) -> list[dict]:
    """The ``PtComparison`` phase writes for "a creature with the least toughness
    among creatures your opponents control" (Olórin's Searing Light's "the
    greatest power among creatures that player controls")."""
    if chosen.extreme is None:
        return []
    function, stat = chosen.extreme
    return [
        {
            "type": "PtComparison",
            "stat": stat,
            "scope": "Current",
            "comparator": "EQ",
            "value": {
                "type": "Ref",
                "qty": {
                    "type": "PropertyAggregate",
                    "function": function,
                    "property": stat,
                    "source": {
                        "type": "Objects",
                        "filter": {
                            "type": "Typed",
                            "type_filters": ["Creature"],
                            "controller": chosen.controller,
                            "properties": [],
                        },
                    },
                },
            },
        }
    ]


def _parked_choices(rec: dict) -> list[tuple[dict, dict]]:
    """``(body, effect)`` for each parked "choose a creature …" an
    ``ApplyPerpetual`` of its ``ParentTarget`` follows (Penregon Besieged's
    "choose a creature with the least toughness among creatures your opponents
    control. It perpetually gets -1/-1"; 1 card at v0.133.0): the choice is
    typed as phase types "Choose a Giant creature you control" (Crush
    Underfoot's ``TargetOnly``), chosen as it resolves, not targeted (CR
    115.10a: ``target_choice_timing: Resolution``, phase's mark on Daily
    Regimen), so the change lands on the chosen creature."""
    out: list[tuple[dict, dict]] = []
    for body in _ability_bodies(rec):
        effect = body.get("effect") or {}
        nxt = (body.get("sub_ability") or {}).get("effect") or {}
        if not (
            effect.get("type") == "Unimplemented"
            and effect.get("name") == "unparsed_verb_arguments"
            and nxt.get("type") == "ApplyPerpetual"
            and (nxt.get("target") or {}).get("type") == "ParentTarget"
        ):
            continue
        chosen = chosen_creature(str(effect.get("description") or ""))
        if chosen is None:
            continue
        out.append(
            (
                body,
                {
                    "type": "TargetOnly",
                    "target": {
                        "type": "Typed",
                        "type_filters": ["Creature"],
                        "controller": chosen.controller,
                        "properties": _least_or_most(chosen),
                    },
                },
            )
        )
    return out


def _untargeted_choices(rec: dict) -> list[dict]:
    """The bodies phase types as a ``TargetOnly`` for a choice that names no
    target. Two shapes: a heading "choose a …" whose clause names no target
    (:func:`~mtg_utils._card_ir.clause_grammar.opens_with_choice`: "Choose a
    Giant creature you control. It deals damage equal to its power to target
    creature" — Crush Underfoot; its ruling: "You choose that Giant as Crush
    Underfoot resolves"; Guard Dogs), and every ``TargetOnly`` of an ability
    whose text states a choice and names no target anywhere
    (:func:`~mtg_utils._card_ir.clause_grammar.chooses_without_target`: "Choose
    five permanents you control" — Clarion Ultimatum; "Choose up to X …" —
    Temporal Firestorm; "Proliferate, then choose any number of permanents you
    control" — Ripples of Potential; "each defending player chooses …" —
    Camouflage; 32 faces, 33 bodies, at v0.133.0). An object a spell or ability
    affects is a target only when the word "target" names it (CR 115.10a), so
    the choice is
    marked as made on resolution (``target_choice_timing: Resolution``, phase's
    mark on Daily Regimen), read by ``crosswalk.effect_chosen_on_resolution``."""
    out: list[dict] = []
    heads = [
        *((a, a.get("description")) for a in rec.get("abilities") or ()),
        *((t.get("execute"), t.get("description")) for t in rec.get("triggers") or ()),
    ]
    for head, description in heads:
        text = str(description or "")
        whole = chooses_without_target(text)
        for at, body in enumerate(_chain(head)):
            if (
                (body.get("effect") or {}).get("type") == "TargetOnly"
                and not body.get("target_choice_timing")
                and (whole or (at == 0 and opens_with_choice(text)))
            ):
                out.append(body)
    return out


def _described_heads(rec: dict) -> Iterator[tuple[object, str]]:
    """``(head body, its text)`` for each ability and trigger; a modal spell's
    mode, which phase writes as one ability with no description of its own,
    takes the card's mode description in the same position (Sunder the
    Gateway's "Incubate 2, then transform an Incubator token you control")."""
    abilities = list(rec.get("abilities") or ())
    modes = (rec.get("modal") or {}).get("mode_descriptions") or ()
    by_mode = len(modes) == len(abilities)
    for i, a in enumerate(abilities):
        text = a.get("description") if isinstance(a, dict) else None
        if not text and by_mode:
            text = modes[i]
        yield a, str(text or "")
    for t in rec.get("triggers") or ():
        yield t.get("execute"), str(t.get("description") or "")


def _untargeted_objects(rec: dict) -> list[dict]:
    """The bodies whose single object phase types as a target where the text
    names it without "target" (:func:`~mtg_utils._card_ir.
    clause_grammar.untargeted_object_effects`): "Create a token that's a copy
    of a permanent you control" (Awaken the Maelstrom), "transform an Incubator
    token you control" (Sunder the Gateway), "You may turn a creature you
    control face up" (Bustle), and another player's "may choose a creature they
    control" (Flaming Gambit, Crashing Boars: the creature is that player's,
    though phase writes its filter ``controller: You`` too). Phase types the
    same object chosen as the effect resolves with ``target_choice_timing:
    Resolution`` (Followed Footsteps' copy of the enchanted creature, Agitator
    Ant's counters), so that mark is written: an object a spell or ability
    affects is a target only when "target" names it (CR 115.10a). Keyed on
    structure (one such effect of that tag in the ability, its target ``Typed``
    with ``controller: You``, no timing yet) and read through the clause
    grammar; the census at v0.133.0 is in the canary's docstring."""
    out: list[dict] = []
    for head, description in _described_heads(rec):
        tags = untargeted_object_effects(description)
        if not tags:
            continue
        # the ability's own instructions and its modes', never a cost's
        chain = [b for b, _earlier in _chains_with_modes(head)]
        for tag in tags:
            hits = [
                b
                for b in chain
                if (b.get("effect") or {}).get("type") == tag
                and ((b["effect"].get("target") or {}).get("type") == "Typed")
            ]
            if len(hits) != 1:
                continue
            (body,) = hits
            if body["effect"]["target"].get("controller") == "You" and not body.get(
                "target_choice_timing"
            ):
                out.append(body)
    return out


#: Phase's count for one target per opponent ("for each opponent, tap up to one
#: target creature that player controls" — Juvenile Mist Dragon).
_UP_TO_ONE_PER_OPPONENT = {
    "min": 0,
    "max": {
        "type": "Ref",
        "qty": {"type": "PlayerCount", "filter": {"type": "Opponent"}},
    },
}


def _parked_per_opponent_heads(rec: dict) -> list[dict]:
    """The heading bodies phase parks as an ``unrecognized_clause_head`` "For any
    number of opponents" (:func:`~mtg_utils._card_ir.clause_grammar.
    per_opponent_head`) ahead of a targeted effect it types ``controller: You``:
    "For any number of opponents, destroy target nonland permanent that player
    controls" (Windgrace's Judgment; the only such head at v0.133.0). Choosing
    any number of opponents and one target each is up to one target per
    opponent, which phase types as Juvenile Mist Dragon's "for each opponent,
    tap up to one target creature that player controls": the effect on a
    ``TargetPlayer`` filter with ``multi_target`` up to the opponent count."""
    out: list[dict] = []
    for body in rec.get("abilities") or ():
        effect = (body or {}).get("effect") or {}
        sub = (body or {}).get("sub_ability") or {}
        target = (sub.get("effect") or {}).get("target") or {}
        if (
            effect.get("type") == "Unimplemented"
            and effect.get("name") == "unrecognized_clause_head"
            and per_opponent_head(str(effect.get("description") or ""))
            and target.get("type") == "Typed"
            and target.get("controller") == "You"
        ):
            out.append(body)
    return out


def _is_behold(cost: object) -> bool:
    """A face's ``additional_cost`` that beholds (CR 701.4a), optional or not."""
    if not isinstance(cost, dict):
        return False
    if cost.get("type") == "Optional":
        cost = (cost.get("data") or {}).get("cost")
    return isinstance(cost, dict) and cost.get("type") == "Behold"


def _beheld_its(rec: dict) -> list[dict]:
    """The ``ApplyPerpetual`` effects phase wrote on ``ParentTarget`` under an
    "if a [quality] was beheld" condition (``AdditionalCostPaid``) on a face
    whose additional cost beholds: "Destroy target nonland permanent. If a
    Dragon creature was beheld, it perpetually gets +2/+2" (Territorial Strike;
    1 card at v0.133.0) puts the change on the destroyed permanent, where the
    "it" is the beheld Dragon — a card revealed from your hand or a permanent
    you control (CR 701.4a, 701.4b). Written on phase's ``CostPaidObject``, the
    object a cost named."""
    if not _is_behold(rec.get("additional_cost")):
        return []
    return [
        effect
        for body in _ability_bodies(rec)
        if (body.get("condition") or {}).get("type") == "AdditionalCostPaid"
        and (effect := body.get("effect") or {}).get("type") == "ApplyPerpetual"
        and (effect.get("target") or {}).get("type") == "ParentTarget"
    ]


def _hand_or_battlefield_choices(rec: dict) -> list[dict]:
    """The ``ChooseFromZone`` effects that choose from a hand among an ``Or``
    holding a creature you control: "choose a creature card in your hand or a
    creature you control" (Scour the Scene; 1 card at v0.133.0). A card in a
    hand has no controller (CR 108.4), so the arm is the battlefield's; it is
    written as phase's multi-zone choice (``additional_zones`` — Mapping the
    Maze's hand or graveyard)."""
    out: list[dict] = []
    for body in _ability_bodies(rec):
        effect = body.get("effect") or {}
        filt = effect.get("filter") or {}
        if (
            effect.get("type") == "ChooseFromZone"
            and effect.get("zone") == "Hand"
            and not effect.get("additional_zones")
            and filt.get("type") == "Or"
            and any(
                isinstance(arm, dict) and arm.get("controller") == "You"
                for arm in filt.get("filters") or ()
            )
        ):
            out.append(effect)
    return out


def _parked_draw_triggers(rec: dict) -> list[tuple[dict, str]]:
    """``(trigger, subtype)`` for each draw trigger phase leaves an ``Unknown``
    mode that the clause grammar reads as watching you draw a card of one
    subtype (:func:`~mtg_utils._card_ir.clause_grammar.drawn_card_subtype`):
    "Whenever you draw a Dragon card, it perpetually gets +1/+1" (Darigaaz's
    Whelp; 1 card at v0.133.0). Written as phase's ``Drawn`` mode on you
    (Aether Syphon's "Whenever you draw a card") with the drawn card's subtype
    on ``valid_card``."""
    out: list[tuple[dict, str]] = []
    for trig in rec.get("triggers") or ():
        mode = trig.get("mode") if isinstance(trig, dict) else None
        if isinstance(mode, dict) and isinstance(mode.get("Unknown"), str):
            subtype = drawn_card_subtype(mode["Unknown"])
            if subtype is not None:
                out.append((trig, subtype))
    return out


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
        for body, description, trig, earlier in _described_bodies(rec)
        if (
            split := _perpetual_split(body, rec, trig, earlier)
            or _second_verb_split(body, trig, earlier)
            or _perpetual_team_split(body, description)
            or _verb_list_split(body, description)
        )
        is not None
    ]
    static_lines = [
        (body, static)
        for body in rec.get("abilities") or ()
        if isinstance(body, dict) and (static := _static_pump_line(body))
    ]
    keyword_pumps = _keyword_pump_bodies(rec)
    paid_its = _paid_then_it_bodies(rec)
    heroic_its = _heroic_it_effects(rec)
    aura_pumps = _aura_self_pumps(rec)
    moved_its = _moved_away_its(rec)
    boons = _flattened_boons(rec)
    bites = _bite_recipients(rec)
    choices = _parked_choices(rec)
    beheld = _beheld_its(rec)
    two_zone_choices = _hand_or_battlefield_choices(rec)
    draw_triggers = _parked_draw_triggers(rec)
    untargeted = _untargeted_choices(rec) + _untargeted_objects(rec)
    per_opponent = _parked_per_opponent_heads(rec)
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
        keyword_pumps,
        paid_its,
        heroic_its,
        aura_pumps,
        moved_its,
        boons,
        bites,
        choices,
        beheld,
        two_zone_choices,
        draw_triggers,
        untargeted,
        per_opponent,
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
    for body in keyword_pumps:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["duration"] = "UntilEndOfTurn"
    for effect in (*paid_its, *heroic_its, *moved_its):
        target = memo[id(effect)]
        assert isinstance(target, dict)
        target["target"] = {"type": "SelfRef"}
    for effect in aura_pumps:
        target = memo[id(effect)]
        assert isinstance(target, dict)
        target["target"] = copy.deepcopy(_ENCHANTED_CREATURE)
    for body, split in splits:
        target = memo[id(body)]
        assert isinstance(target, dict)
        _place_split(target, split)
    for body in boons:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["effect"] = _creature_spell_boon(target["effect"])
    for body, read in bites:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["effect"]["target"] = _power_damage_filter(read)
        target["effect"]["damage_source"] = "Target"
        if read.up_to and not target.get("multi_target"):
            target["multi_target"] = {"min": 0, "max": {"type": "Fixed", "value": 1}}
    for body, typed in choices:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["effect"] = typed
        target["target_choice_timing"] = "Resolution"
    for body in untargeted:
        target = memo[id(body)]
        assert isinstance(target, dict)
        target["target_choice_timing"] = "Resolution"
    for body in per_opponent:
        target = memo[id(body)]
        assert isinstance(target, dict)
        sub = target["sub_ability"]
        target["effect"] = sub["effect"]
        target["effect"]["target"]["controller"] = "TargetPlayer"
        target["sub_ability"] = sub.get("sub_ability")
        target["multi_target"] = copy.deepcopy(_UP_TO_ONE_PER_OPPONENT)
    for effect in beheld:
        target = memo[id(effect)]
        assert isinstance(target, dict)
        target["target"] = {"type": "CostPaidObject"}
    for effect in two_zone_choices:
        target = memo[id(effect)]
        assert isinstance(target, dict)
        target["additional_zones"] = ["Battlefield"]
    for trig, subtype in draw_triggers:
        target = memo[id(trig)]
        assert isinstance(target, dict)
        target["mode"] = "Drawn"
        target["valid_target"] = {"type": "Controller"}
        target["valid_card"] = {
            "type": "Typed",
            "type_filters": [{"Subtype": subtype}],
            "controller": None,
            "properties": [],
        }
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
