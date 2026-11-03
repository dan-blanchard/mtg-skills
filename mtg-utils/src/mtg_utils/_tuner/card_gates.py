"""What a deck holds and whether an add is dead in it: the deck profile, the
dead-payoff read and the unit gates it reads off phase's trees, and the
card reads the swap loop asks of a candidate (split out of ``swaps``)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis.commander_need import (
    grants_all_creature_types,
)
from mtg_utils._analysis.signal_base import Ident, ident_key
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._card_ir.creature_types import CREATURE_TYPES
from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_non_types,
    filter_owners,
    filter_predicates,
    filter_subtypes,
    iter_cost_leaves,
    iter_static_defs,
    iter_typed_nodes,
    list_field,
    static_affected,
    static_mode_tag,
    tag_of,
    trigger_def_event,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.metrics import NEUTRAL_KEYS, NO_FEEDER_READ, payoff_feeders
from mtg_utils.card_classify import (
    land_search_fixes,
)
from mtg_utils.deck import split_type_line
from mtg_utils.theme_presets import _signal_idents_for

#: The deck cards that do what a payoff cares about for the payoff to be alive
#: there; a tribe needs twice as many creatures sharing the type for a
#: choose-a-type payoff (Door of Destinies). The ``_NEED_BUILT_FLOOR`` line.
_FEEDER_FLOOR = 5


#: The CR's creature types (CR 205.3m), lower-cased — not the bulk-harvested
#: ``CREATURE_SUBTYPES``, which picks up Food and Equipment off artifact
#: creature faces.
_CREATURE_SUBTYPE_WORDS = frozenset(s.lower() for s in CREATURE_TYPES)


#: The doers a multiplier needs in the deck to be alive there: twice the floor
#: (:func:`dead_payoff`).
_MULTIPLIER_FEEDER_FLOOR = 2 * _FEEDER_FLOOR


#: The payoffs that multiply what the deck already does, and so never feed
#: themselves (:func:`dead_payoff`).
_MULTIPLIER_KEYS = frozenset(
    {"counter_doubling", "counter_replace_bonus", "token_doubling"}
)


#: The card types (and the one supertype) a payoff's unit is gated on beside a
#: creature type: a spellslinger's instants and sorceries (Talrand), an
#: artifact or enchantment cast (Sai, Master Thopterist; Starfield Mystic),
#: legends (Rising of the Day). Fed by :data:`_TYPE_GATE_FLOOR` cards of the
#: type — a quarter of the nonlands; twelve artifacts make no artifact deck
#: (Riders of Rohan's Sai, 2026-11-02) — where a creature type or a gear type
#: (Equipment, Aura) is fed by :data:`_FEEDER_FLOOR` (:func:`_unit_gates`).
_GATE_TYPE_WORDS = frozenset(
    {"instant", "sorcery", "artifact", "enchantment", "planeswalker", "legendary"}
)


_TYPE_GATE_FLOOR = 15


#: A land type gates nothing (Farseek's Plains, Knight of the White Orchid's).
_LAND_TYPE_WORDS = frozenset(s.lower() for s in LAND_SUBTYPES)


#: The type words every deck has: no gate (Asceticism's creatures).
_GENERIC_TYPE_WORDS = frozenset(
    {"creature", "permanent", "card", "spell", "land", "token", "kindred", "tribal"}
)


#: A gate on your permanents with +1/+1 counters (Inspiring Call's draw), fed
#: by the deck's counter makers; and one on your creature tokens (Intangible
#: Virtue's anthem), fed by the deck's creature-token makers — Clues and
#: Treasures are no creatures (Deep Clue Sea, 2026-11-02).
_COUNTERS_GATE = "+1/+1 counters"


_CREATURE_TOKENS_GATE = "creature tokens"


#: A gate on a color of your spells (Oketra's Monument's white creature
#: spells — a colorless card, dead in Golgari), fed by :data:`_TYPE_GATE_FLOOR`
#: cards of the color; the word is ``color:<letter>``.
_COLOR_LETTERS = {"white": "w", "blue": "u", "black": "b", "red": "r", "green": "g"}


_COUNTER_GATE_FEEDERS = frozenset({"plus_one_makers", "any_counter_makers"})


#: A gate on an opponent's discard (Waste Not's three triggers), fed by the
#: deck's discard makers; the event is the gate where the discarded card's
#: type is generic (2026-11-02).
_OPP_DISCARD_GATE = "opponents discard"


_OPP_DISCARD_FEEDERS = frozenset({"opponent_discard", "discard_makers"})


#: And on your own (Monument to Endurance's draw, Treasure and drain), fed by
#: the deck's discard outlets.
_YOU_DISCARD_GATE = "you discard"


_YOU_DISCARD_FEEDERS = frozenset({"discard_outlet", "discard_makers"})


#: The library effects whose filter is over YOUR cards though it carries no
#: controller: Heroes' Podium's legendary creature from the top, Open the
#: Armory's Aura or Equipment.
_LIBRARY_EFFECTS = frozenset({"Dig", "SearchLibrary"})


#: The effects that stand on no gate of their own: the targeting step, a
#: shuffle, an opaque residue, and anything acting on what an earlier effect
#: chose (Ripples of Potential's phase-out of what it proliferated).
_DEPENDENT_EFFECT_TAGS = frozenset({"TargetOnly", "Shuffle", "GenericEffect"})


_DEPENDENT_TARGET_TAGS = frozenset({"ParentTarget", "TrackedSet", "TrackedSetFiltered"})


def deck_profile(classes: Sequence[CardClass]) -> tuple[Counter, Counter, Counter]:
    """What the deck does, for :func:`dead_payoff`: its signal keys by the
    cards carrying them, its creatures' subtypes by count, and its cards'
    other type words by count — card types and supertypes (``instant``,
    ``artifact``, ``legendary``) and non-creature subtypes (``equipment``,
    ``aura``, ``food``), the gates :func:`_unit_gates` reads."""
    keys: Counter = Counter()
    tribes: Counter = Counter()
    types: Counter = Counter()
    for c in classes:
        for ident in _signal_idents_for(c.record, include_membership=False):
            keys[ident_key(ident)] += 1
        words, subs = split_type_line(c.record.get("type_line") or "")
        lowered = {w.lower() for w in words}
        if "creature" in lowered:
            for sub in subs:
                tribes[sub.lower()] += 1
        for word in lowered | {
            s.lower() for s in subs if s.lower() not in _CREATURE_SUBTYPE_WORDS
        }:
            types[word] += 1
        token_kinds = {
            Ident.parse(i).subject.lower()
            for i in _signal_idents_for(c.record, include_membership=False)
            if i.startswith(f"{TOKEN_MAKER}|")
        } & _CREATURE_SUBTYPE_WORDS
        if token_kinds:
            types[_CREATURE_TOKENS_GATE] += 1
        for kind in token_kinds:
            types[f"{kind} tokens"] += 1
        for color in c.record.get("colors") or ():
            types[f"color:{str(color).lower()}"] += 1
    # A commander that makes permanents every creature type (Omo, Queen of
    # Vesuva's everything counters) fields every tribe: a lord, a tribal
    # trigger or a choose-a-type card is fed whatever the type line says, as
    # the guides' Roaming Throne and Coat of Arms for Tricky Terrain are
    # (2026-11-02).
    if any(
        c.bucket == "commander" and grants_all_creature_types(c.record) for c in classes
    ):
        printed = Counter(tribes)
        tribes = _Tribes(tribes)
        tribes.printed = printed
        for word in _CREATURE_SUBTYPE_WORDS:
            tribes[word] = max(tribes[word], 2 * _FEEDER_FLOOR)
    return keys, tribes, types


class _Tribes(Counter):
    """The deck's tribes under a commander that makes its creatures every
    type, with the ``printed`` counts beside them: the grant reaches only
    creatures on the battlefield (Omo's "each nonland creature with an
    everything counter on it"), never a spell or a card in the library."""

    printed: Counter


def _chosen_type_on_battlefield(card: Mapping) -> bool:
    """Whether the card reads its chosen creature type off permanents you
    control (an anthem's affected creatures, an enters or attacks trigger's,
    Distant Melody's count), or has no chosen type at all (Coat of Arms) —
    rather than only off spells cast or cards in a library (Herald's Horn's
    discount and upkeep reveal), where a grant of every type (Omo) never
    reaches: Tricky Terrain's biggest printed tribe is four Hydras, and
    Herald's Horn went in (2026-11-02)."""
    found = False
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            node = unit.node
            off: set[int] = set()
            if unit.origin == "trigger" and getattr(node, "mode", None) == "SpellCast":
                off |= {
                    id(n) for n in iter_typed_nodes(getattr(node, "valid_card", None))
                }
            if unit.origin == "static":
                mode = getattr(node, "mode", None)
                off |= {
                    id(n) for n in iter_typed_nodes(getattr(mode, "spell_filter", None))
                }
            for n in unit.iter_typed():
                if tag_of(n) != "Typed" or not any(
                    tag_of(p) == "IsChosenCreatureType"
                    for p in list_field(n, "properties")
                ):
                    continue
                found = True
                if (
                    id(n) not in off
                    and filter_controller(n) == "You"
                    and not filter_inzone_zones(n)
                ):
                    return True
    return not found


def _mills_only_opponents(card: Mapping) -> bool:
    """Whether ``card``'s mill reaches only another player's library, filling
    no graveyard of yours (``mill_makers|opponents|`` without
    ``graveyard_makers|you|``): Mindcrank's "that player mills that many
    cards", Altar of the Brood's "each opponent mills a card"."""
    idents = _signal_idents_for(dict(card), include_membership=False)
    return "mill_makers|opponents|" in idents and "graveyard_makers|you|" not in idents


#: The share of a deck's mill cards that must fill its own graveyard for the
#: deck to be one milling itself — the read's own call: one opponent-mill card
#: in four doesn't make a self-mill deck a mill-your-opponents one.
_SELF_MILL_SHARE = 0.75


def _self_mill_deck(classes: Sequence[CardClass]) -> bool:
    """Whether the deck's mill fills its own graveyard: ``_FEEDER_FLOOR`` mill
    cards, at least ``_SELF_MILL_SHARE`` of them reaching your own library —
    Szarekh, the Silent King's Necron Dynasties (nine of nine), Graveyard
    Overdrive, Death Toll."""
    mills = [
        c
        for c in classes
        if "mill_makers|any|" in _signal_idents_for(c.record, include_membership=False)
    ]
    if len(mills) < _FEEDER_FLOOR:
        return False
    own = sum(1 for c in mills if not _mills_only_opponents(c.record))
    return own / len(mills) >= _SELF_MILL_SHARE


def _commander_already_grants(card: Mapping, commanders: Sequence[Mapping]) -> bool:
    """Whether every ability ``card`` has is a static the commander already
    applies to every creature you control: Rolling Stones's "Wall creatures can
    attack as though they didn't have defender" under Felothar the Steadfast,
    whose "Creatures you control can attack as though they didn't have
    defender" leaves it nothing to do (Abzan Armor, 2026-11-02). A
    ``Continuous`` static is a set of modifications, never compared whole."""

    if not commanders:
        return False
    units = [unit for tree in trees_for(dict(card)) for unit in tree.units]
    own = statics_of(card)
    if not own or any(unit.origin != "static" for unit in units):
        return False
    granted = set()
    for commander in commanders:
        for mode, d, unit in statics_of(commander):
            affected = static_affected(d, unit)
            if (
                "Creature" in filter_core_types(affected)
                and not filter_subtypes(affected)
                and filter_controller(affected, unit) == "You"
            ):
                granted.add(mode)
    return all(
        mode != "Continuous"
        and mode in granted
        and _affects_creatures(static_affected(d, unit))
        for mode, d, unit in own
    )


def _affects_creatures(affected: object) -> bool:
    """Whether a static's affected filter is creatures: by core type, or by a
    creature subtype alone (Animate Wall's "Enchanted Wall")."""
    if "Creature" in filter_core_types(affected):
        return True
    subtypes = {s.lower() for s in filter_subtypes(affected)}
    return bool(subtypes) and subtypes <= CREATURE_TYPES


def statics_of(rec: Mapping) -> list[tuple[str, object, AbilityUnit]]:
    """Every static def on ``rec``'s trees, with its mode and unit."""
    return [
        (static_mode_tag(d) or "", d, unit)
        for tree in trees_for(dict(rec))
        for unit in tree.units
        for d in iter_static_defs(unit.node)
    ]


def dead_payoff(
    card: Mapping, deck_keys: Counter, deck_tribes: Counter, deck_types: Counter
) -> bool:
    """Whether ``card`` is a payoff for what the deck doesn't do: every
    mechanic it cares about has fewer than :data:`_FEEDER_FLOOR` doers in the
    deck (``metrics.payoff_feeders``), the card feeds none of them itself, and
    it does nothing else on its own (no doer key beyond the structural ones,
    :data:`metrics.NEUTRAL_KEYS`, and the feeders of its own multipliers —
    Hardened Scales' extra counter is tagged a counter maker). A
    choose-a-creature-type payoff with no tribe of ten in the deck (Banner of
    Kinship, Door of Destinies, Coat of Arms under Bello), a counter doubler
    where nothing places counters. Not Etali (its poison payoff fed by its own
    poison, and a doer besides), Myr Battlesphere (its Myr are its own
    tokens), Birgi (boast unfed, but a mana doer), Farseek (a Plains is no
    tribe); a card caring about nothing the read names is never dead
    (2026-11-02).

    A unit gated on a type the deck lacks is as dead as one gated on a tribe
    (:func:`_unit_gates`): Docent of Perfection's Wizards wait on instants and
    sorceries an Eldrazi deck casts thirteen of, Puresteel Paladin's draw on
    Equipment a Humans deck holds two of, Death Baron's anthem on Zombies a
    Party deck has none of (2026-11-02)."""
    idents = _signal_idents_for(dict(card), include_membership=False)
    own_keys = {ident_key(i) for i in idents}
    makes_tokens = any(i.startswith(f"{TOKEN_MAKER}|") for i in idents)
    own_subtypes = {w.lower() for w in split_type_line(card.get("type_line") or "")[1]}
    feeders = payoff_feeders()
    verdicts: list[bool] = []
    cares: set[str] = set()
    gated = _unit_gates(card)
    for ident in idents:
        key, scope, subject = Ident.parse(ident)
        chooses_a_type = key == "chosen_type_matters" or (
            key == "subtype_ref" and subject == "shared"
        )
        if chooses_a_type:
            cares.add(key)
            verdicts.append(
                _biggest_choosable_tribe(card, deck_tribes) >= 2 * _FEEDER_FLOOR
            )
        elif key == "subtype_ref":
            # A creature type the card names among YOUR permanents (Dragon
            # Tempest's Dragons); a land type (Farseek's Plains), a gear type
            # (Sram's Auras) or another player's is no tribe the deck fields.
            # Where the trees show the gates, they are the read: Docent of
            # Perfection's Wizard tokens arrive only on the spells its gated
            # trigger waits for, so they feed no Wizard reference of its own.
            sub = subject.lower()
            if scope != "you" or sub not in _CREATURE_SUBTYPE_WORDS or gated.gates:
                continue
            cares.add(key)
            verdicts.append(
                makes_tokens
                or sub in own_subtypes
                or deck_tribes.get(sub, 0) >= _FEEDER_FLOOR
            )
        elif (fed_by := feeders.get(key)) is not None:
            cares.add(key)
            multiplier = key in _MULTIPLIER_KEYS
            self_fed = not multiplier and bool(fed_by & own_keys)
            # A doubler is for what the deck does a lot: twice the floor.
            # Anikthea's five incidental counter cards kept Hardened Scales and
            # Branching Evolution alive on her page; Hazel's eighteen token
            # makers keep Doubling Season (2026-11-02).
            floor = _MULTIPLIER_FEEDER_FLOOR if multiplier else _FEEDER_FLOOR
            verdicts.append(
                self_fed or sum(deck_keys.get(f, 0) for f in fed_by) >= floor
            )
    # A unit gated on a creature type (Dragon Tempest's "whenever a Dragon
    # you control enters"), a card type or a gear type: the gate lives in the
    # IR, not in a key. Fed by the deck's cards of the type, the card's own
    # type, or its own tokens.
    for gate in gated.gates:
        cares.add("unit_gate")
        verdicts.append(gated.fed(gate, deck_tribes, deck_types, deck_keys))
    # Gated on a tribe the deck lacks is dead whatever else the card cares
    # about: Invisible Woman's only trigger waits on "other Heroes", and the
    # +1/+1 counters it also names (fed in Abzan Armor) never reach it without
    # them (2026-11-02). Only a creature-type gate: a type tokens make (Food)
    # is counted off the type line, and the early verdict cost Food and
    # Fellowship's Trail of Crumbs (the 25 -2 adds, fresh -3).
    # So is one whose only gate is life above the starting total the deck
    # can't gain (Doctor Strange, Surgeon's pump in Avengers Assemble's three
    # lifegain cards, 2026-11-02): its own lifelink feeds no "10 life more".
    if (
        gated.gates
        and all(
            g.words <= _CREATURE_SUBTYPE_WORDS or g.words == {_LIFE_GATE}
            for g in gated.gates
        )
        and gated_without_feed(card, deck_tribes, deck_types, deck_keys)
    ):
        return True
    if not verdicts or any(verdicts):
        return False
    if gated_without_feed(card, deck_tribes, deck_types, deck_keys):
        return True
    multiplier_feeders = frozenset().union(
        *(feeders.get(k, frozenset()) for k in cares & _MULTIPLIER_KEYS)
    )
    # The umbrella payoffs (Door of Destinies' "whenever you cast a spell of
    # the chosen type" is ``spellcast_matters``) are no doing of their own.
    doers = own_keys - cares - NEUTRAL_KEYS - NO_FEEDER_READ - multiplier_feeders
    return not doers


@dataclass(frozen=True)
class _Gate:
    """One gated unit's words (a creature type, a card type, a gear type, a
    counters or creature-tokens gate; any word fed feeds the gate) and whether
    the unit is a static."""

    words: frozenset[str]
    static: bool
    # A trigger on a creature entering (``enters``): what enters is a card's
    # printed types, no type a grant on the battlefield gives (Omo).
    entering: bool = False


@dataclass(frozen=True)
class _UnitGates:
    """What :func:`_unit_gates` read off one card: its ``gates``; ``units`` —
    its triggers, statics and abilities; whether it has an ``activated``
    ability no gate holds; and what feeds its own gates — the types its
    statics grant (Ygra's Food) feed any gate; the token kinds it makes feed a
    trigger's or an ability's (Myr Battlesphere's Myr are its own; Krenko's
    Goblins) but not a static's (Docent of Perfection's Wizard anthem waits on
    the Wizards its spell trigger never makes). Its own type feeds nothing: a
    Zombie lord's anthem for other Zombies is for nobody (Death Baron), and
    Scourge of Valkas's one Dragon is itself (Endless Punishment,
    2026-11-02)."""

    gates: tuple[_Gate, ...]
    units: int
    activated: bool
    granted_words: frozenset[str]
    token_words: frozenset[str]
    makes_tokens: bool

    def fed(
        self,
        gate: _Gate,
        deck_tribes: Counter,
        deck_types: Counter,
        deck_keys: Counter | None = None,
    ) -> bool:
        """Whether the deck feeds ``gate``: a creature type by
        :data:`_FEEDER_FLOOR` creatures of it or, for a trigger's or ability's
        gate, the card's own tokens; a card type by :data:`_TYPE_GATE_FLOOR`
        cards of it — an instant-or-sorcery gate by their sum; a counters gate
        by :data:`_FEEDER_FLOOR` counter makers (``deck_keys``); a gear or
        other subtype, or the creature-tokens gate, by :data:`_FEEDER_FLOOR`
        cards or the kind the card grants."""
        words = gate.words
        own_tokens = self.token_words | {f"{w} tokens" for w in self.token_words}
        if words & self.granted_words or (not gate.static and words & own_tokens):
            return True
        card_types = words & _GATE_TYPE_WORDS
        if (
            card_types
            and sum(deck_types.get(w, 0) for w in card_types) >= _TYPE_GATE_FLOOR
        ):
            return True
        for word in words - _GATE_TYPE_WORDS:
            if word.startswith("color:"):
                if deck_types.get(word, 0) >= _TYPE_GATE_FLOOR:
                    return True
            elif word in (_OPP_DISCARD_GATE, _YOU_DISCARD_GATE):
                keys = deck_keys or Counter()
                feeders = (
                    _OPP_DISCARD_FEEDERS
                    if word == _OPP_DISCARD_GATE
                    else _YOU_DISCARD_FEEDERS
                )
                if sum(keys.get(k, 0) for k in feeders) >= _FEEDER_FLOOR:
                    return True
            elif word.startswith(_NON_PREFIX):
                others = deck_types.get("creature", 0) - deck_tribes.get(
                    word.removeprefix(_NON_PREFIX), 0
                )
                if others >= _FEEDER_FLOOR:
                    return True
            elif word == _LIFE_GATE:
                keys = deck_keys or Counter()
                if keys.get("lifegain_makers", 0) >= _FEEDER_FLOOR:
                    return True
            elif word == _TOKENS_GATE:
                keys = deck_keys or Counter()
                if self.makes_tokens or (
                    sum(keys.get(k, 0) for k in _TOKENS_GATE_FEEDERS) >= _FEEDER_FLOOR
                ):
                    return True
            elif word == _COUNTERS_GATE:
                keys = deck_keys or Counter()
                if sum(keys.get(k, 0) for k in _COUNTER_GATE_FEEDERS) >= _FEEDER_FLOOR:
                    return True
            elif word in _CREATURE_SUBTYPE_WORDS:
                # A creature entering has only its printed types: Omo's
                # everything counters are on creatures already out, so Elvish
                # Warmaster's "other Elves you control enter" waits on the
                # deck's printed Elves (Tricky Terrain, 2026-11-02).
                tribes = deck_tribes
                if gate.entering and (printed := getattr(tribes, "printed", None)):
                    tribes = printed
                # Its own tokens feed a trigger's creature-type gate only when
                # they are of the type (``token_words``, above) or of a kind the
                # read can't name: Invisible Woman's Walls feed no "other Heroes"
                # in a deck with none (Abzan Armor, 2026-11-02).
                unnamed_tokens = self.makes_tokens and not self.token_words
                if (not gate.static and unnamed_tokens) or tribes.get(
                    word, 0
                ) >= _FEEDER_FLOOR:
                    return True
            elif deck_types.get(word, 0) >= _FEEDER_FLOOR:
                return True
        return False


def _gate_words(filt: object) -> frozenset[str]:
    """The gate words of a unit's filter: its subtypes (a creature type, a
    gear type), its card types in :data:`_GATE_TYPE_WORDS`, and a legendary
    supertype — never a land type or a word every deck has."""
    words = {w.lower() for w in filter_subtypes(filt)}
    # A creature type the filter leaves out ("a non-Human creature you
    # control", Winota) is fed by the deck's creatures of any other type:
    # Riders of Rohan holds three non-Humans of 31 creatures (2026-11-02).
    words |= {
        f"{_NON_PREFIX}{w.lower()}"
        for w in filter_non_types(filt)
        if w.lower() in _CREATURE_SUBTYPE_WORDS
    }
    cores = {w.lower() for w in filter_core_types(filt)}
    words |= cores & _GATE_TYPE_WORDS
    if any(
        tag_of(n) == "HasSupertype" and getattr(n, "value", None) == "Legendary"
        for n in iter_typed_nodes(filt)
    ):
        words.add("legendary")
    preds = filter_predicates(filt)
    for n in iter_typed_nodes(filt):
        if tag_of(n) == "HasColor":
            letter = _COLOR_LETTERS.get(str(getattr(n, "color", "")).lower())
            if letter:
                words.add(f"color:{letter}")
    if "Counters" in preds:
        words.add(_COUNTERS_GATE)
    if "Token" in preds:
        # Tokens of a creature type (Gleaming Overseer's "Zombie tokens you
        # control have hexproof") are fed by the deck's makers of them, not
        # by its Zombie cards: Cavalry Charge's seven Zombie cards fed the
        # protection for tokens it never makes (2026-11-02).
        tribe_tokens = {f"{w} tokens" for w in words if w in _CREATURE_SUBTYPE_WORDS}
        if tribe_tokens:
            words = (words - _CREATURE_SUBTYPE_WORDS) | tribe_tokens
        elif "creature" in cores:
            words.add(_CREATURE_TOKENS_GATE)
    return frozenset(words - _LAND_TYPE_WORDS - _GENERIC_TYPE_WORDS)


def _ability_gate_words(node: object, effects: Sequence) -> frozenset[str]:
    """The gate words of an activated ability or a spell: a sacrifice in its
    cost names what it feeds on (Skirk Prospector's Goblin, Grinding Station's
    artifact, Sai, Master Thopterist's two artifacts), and an effect over
    permanents of YOURS does (Brass Squire's Equipment you control, Inspiring
    Call's creatures with +1/+1 counters, Krenko's Goblins) — never a target
    among anyone's (Vandalblast's artifacts, Asceticism's creature)."""
    # A cost gates the whole ability (it has to be paid: Sai's two artifacts,
    # High Perfect Morcant's "tap three untapped Elves you control" — Blight
    # Curse holds three Elves, 2026-11-02), whatever its effects reach.
    cost_words: set[str] = set()
    for leaf in iter_cost_leaves(getattr(node, "cost", None)):
        tag = tag_of(leaf)
        if tag == "Sacrifice":
            target = getattr(leaf, "target", None)
            if _present(target):
                cost_words |= _gate_words(target)
        elif tag == "TapCreatures":
            filt = getattr(leaf, "filter", None)
            if _present(filt):
                cost_words |= _gate_words(filt)
    if cost_words:
        return frozenset(cost_words)
    # The effects gate it only when every one that stands on its own is
    # gated: Tezzeret's Gambit draws two whatever its proliferate finds, where
    # Ripples of Potential's phase-out reaches only what it proliferated.
    effect_words: set[str] = set()
    ungated = False
    searched = False
    for c in effects:
        tag = tag_of(c.node)
        if tag in _DEPENDENT_EFFECT_TAGS or tag_of(getattr(c.node, "target", None)) in (
            _DEPENDENT_TARGET_TAGS
        ):
            continue
        if searched and tag == "ChangeZone":
            continue  # the found card going to hand (Open the Armory)
        searched = searched or tag in _LIBRARY_EFFECTS
        # Every typed filter the effect reaches — its target, an attachment
        # (Brass Squire's Equipment), a count (Inspiring Call's counters); a
        # library effect's filter is yours with no controller on it.
        library = tag in _LIBRARY_EFFECTS
        words: set[str] = set()
        if tag == "Proliferate":
            # Proliferate adds to counters the deck must already place:
            # Ripples of Potential under four counter makers (Family Matters).
            words.add(_COUNTERS_GATE)
        for n in iter_typed_nodes(c.node):
            # Yours: controlled, or owned in a zone (Forge Anew's "Equipment
            # card from your graveyard").
            if tag_of(n) == "Typed" and (
                library or filter_controller(n) == "You" or "You" in filter_owners(n)
            ):
                words |= _gate_words(n)
        if words:
            effect_words |= words
        else:
            ungated = True
    return frozenset(set() if ungated else effect_words)


def _unit_gates(card: Mapping) -> _UnitGates:
    """The gates on the card's triggers and statics, read off phase's trees
    (the field ``ranking._ir_gate_subtypes`` reads on the compat Card, which
    CI has no sidecar for): the words of a trigger's ``valid_card`` (Dragon
    Tempest's Dragons, Talrand's instants and sorceries, Puresteel Paladin's
    Equipment) or a static's ``affected`` (Death Baron's Skeletons and
    Zombies; a self-only static has none). Empty for a card phase has no
    trees for."""
    gates: list[_Gate] = []
    units = 0
    activated = False
    tokens: set[str] = set()
    made: set[str] = set()
    idents = _signal_idents_for(dict(card), include_membership=False)
    makes_tokens = False
    for ident in idents:
        key, _scope, subject = Ident.parse(ident)
        if key == TOKEN_MAKER:
            makes_tokens = True
            if subject:
                tokens.add(subject.lower())
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            if unit.origin == "ability":
                # An activated ability or a spell, gated by its cost or its
                # effects over your permanents (:func:`_ability_gate_words`);
                # one no gate holds is something to activate whatever the deck.
                # One phase couldn't parse (``Unimplemented``) says nothing
                # either way: Forge Anew's instant-speed equip (2026-11-02).
                if unit.effects and all(
                    tag_of(c.node) == "Unimplemented" for c in unit.effects
                ):
                    continue
                units += 1
                words = _ability_gate_words(unit.node, unit.effects)
                if words:
                    gates.append(_Gate(words, static=False))
                elif unit.kind == "Activated" and not all(
                    tag_of(getattr(c.node, "target", None)) == "SelfRef"
                    for c in unit.effects
                ):
                    # A self-only ability (Scourge of Valkas's firebreathing)
                    # is not why the card is played: nothing to activate.
                    activated = True
                continue
            if unit.origin == "trigger":
                filt = getattr(unit.node, "valid_card", None)
                if (
                    isinstance(unit.node, TypedMirrorNode)
                    and trigger_def_event(unit.node) == "discarded"
                ):
                    scope = trigger_scope(unit.node)
                    gate = (
                        _OPP_DISCARD_GATE
                        if scope in ("opponents", "each")
                        else _YOU_DISCARD_GATE
                    )
                    units += 1
                    gates.append(
                        _Gate(
                            (_gate_words(filt) if _present(filt) else frozenset())
                            | {gate},
                            static=False,
                        )
                    )
                    continue
            elif unit.origin == "static":
                filt = getattr(unit.node, "affected", None)
                if tag_of(filt) == "SelfRef":
                    filt = None
                # A static that works only while you control a creature of a
                # type (Gravecrawler's "cast this card from your graveyard as
                # long as you control a Zombie") is gated on that type: Necron
                # Dynasties holds no Zombies (2026-11-02).
                cond = getattr(unit.node, "condition", None)
                if (
                    filt is None
                    and tag_of(cond) == "IsPresent"
                    and filter_controller(getattr(cond, "filter", None)) == "You"
                ):
                    filt = getattr(cond, "filter", None)
                # A cost reduction's spell filter is its gate (Oketra's
                # Monument's white creature spells), beside the affected.
                mode_words: set[str] = set()
                for n in iter_typed_nodes(getattr(unit.node, "mode", None)):
                    if tag_of(n) == "Typed":
                        mode_words |= _gate_words(n)
                # A type the static grants feeds a gate on it: Ygra, Eater of
                # All makes other creatures Food.
                for mod in getattr(unit.node, "modifications", None) or ():
                    if tag_of(mod) == "AddSubtype":
                        made.add(str(getattr(mod, "subtype", "")).lower())
                    elif tag_of(mod) == "AddType":
                        made.add(str(getattr(mod, "core_type", "")).lower())
            else:
                continue
            units += 1
            words = _gate_words(filt) if _present(filt) else frozenset()
            if unit.origin == "static":
                words |= mode_words
            if any(
                tag_of(n) == "LifeAboveStarting"
                for n in iter_typed_nodes(getattr(unit.node, "condition", None))
            ):
                # Life above the starting total waits on the deck's lifegain:
                # Doctor Strange, Surgeon's "at least 10 life more than your
                # starting life total" closed for Avengers Assemble, which
                # holds three lifegain cards (2026-11-02).
                words = words | {_LIFE_GATE}
            if (
                unit.origin == "trigger"
                and not words
                and (
                    getattr(unit.node, "mode", None) == "TokenCreated"
                    or (_present(filt) and "Token" in filter_predicates(filt))
                )
            ):
                # A trigger on a token of any kind made or sacrificed waits on
                # the deck's token makers: Mirkwood Bats' "Whenever you create
                # or sacrifice a token" in Endless Punishment (2026-11-02).
                words = frozenset({_TOKENS_GATE})
            if not words and unit.origin == "trigger":
                words = _trigger_effect_gate_words(unit)
            if (
                not words
                and unit.origin == "trigger"
                and tag_of(filt) == "SelfRef"
                and unit.effects
                and all(tag_of(c.node) == "ChangeZone" for c in unit.effects)
            ):
                # A self-entering trigger that only moves a card of a type of
                # yours: Forge Anew's "return target Equipment card from your
                # graveyard" waits on the deck's Equipment (Virtue and Valor,
                # 2026-11-02).
                words = _ability_gate_words(unit.node, unit.effects)
            if words:
                gates.append(
                    _Gate(
                        words,
                        static=unit.origin == "static",
                        entering=unit.origin == "trigger"
                        and unit.trigger_event == "enters"
                        and tag_of(filt) != "SelfRef",
                    )
                )
            elif unit.origin == "trigger" and (kin := _kinship_words(unit, tree)):
                # Kinship pays off only when the revealed card shares a type
                # with this one: its gate is its own creature types, fed by the
                # deck's cards of them, never by the tokens it makes (Wolf-Skull
                # Shaman's Wolves for its Elf Shaman check — Squirreled Away
                # holds five, 2026-11-02). A static gate is fed that way.
                gates.append(_Gate(kin, static=True))
    return _UnitGates(
        tuple(gates), units, activated, frozenset(made), frozenset(tokens), makes_tokens
    )


#: A condition on your life above its starting total, fed by lifegain.
_LIFE_GATE = "life above starting"


#: A trigger on any token made or sacrificed, fed by the deck's makers of
#: tokens of every kind (:meth:`_UnitGates.fed`).
_TOKENS_GATE = "any tokens"


_TOKENS_GATE_FEEDERS = frozenset(
    {
        TOKEN_MAKER,
        "mass_token_makers",
        "treasure_makers",
        "clue_makers",
        "food_makers",
        "blood_makers",
    }
)


#: A gate word for a creature type a filter leaves out (:func:`_gate_words`).
_NON_PREFIX = "non-"


#: The gate of a card that opens an Attraction (CR 701.51a: only with an
#: Attraction deck, CR 717): fed only by
#: Attraction cards, which no Commander precon's deck holds.
_ATTRACTION_GATE = "attraction"


def _trigger_effect_gate_words(unit: AbilityUnit) -> frozenset[str]:
    """The gate words a trigger's effects carry when its watched object names
    none: opening an Attraction (Squirrel Squatters' "open an Attraction",
    dead without an Attraction deck — Squirreled Away, 2026-11-02), or the
    filter of a static the effect grants for the turn when every effect is
    such a grant (Chocobo Knights' "creatures you control with counters on
    them gain double strike", over three counter makers in Cavalry Charge)."""
    tags = [tag_of(c.node) for c in unit.effects]
    if "OpenAttractions" in tags:
        return frozenset({_ATTRACTION_GATE})
    counted = _counted_gate_words(unit)
    if counted:
        return counted
    if not tags or any(t != "GenericEffect" for t in tags):
        return frozenset()
    words: set[str] = set()
    for c in unit.effects:
        statics = list_field(c.node, "static_abilities")
        if not statics:
            return frozenset()
        for sdef in statics:
            filt = getattr(sdef, "affected", None)
            if not _present(filt) or filter_controller(filt) != "You":
                return frozenset()
            got = _gate_words(filt)
            if not got:
                return frozenset()
            words |= got
    return frozenset(words)


def _counted_gate_words(unit: AbilityUnit) -> frozenset[str]:
    """The gate words of a trigger every effect of which is sized by a count
    of your permanents of some type: Valley Rotcaller's "X is the number of
    other Squirrels, Bats, Lizards, and Rats you control" drains nothing in
    Most Wanted, which holds two changelings (2026-11-02). Empty when an
    effect is sized otherwise, or names no type."""
    words: set[str] = set()
    for c in unit.effects:
        got: frozenset[str] = frozenset()
        for n in iter_typed_nodes(c.node):
            if tag_of(n) != "ObjectCount":
                continue
            filt = getattr(n, "filter", None)
            if _present(filt) and filter_controller(filt) == "You":
                got = _gate_words(filt) & _CREATURE_SUBTYPE_WORDS
                if got:
                    break
        if not got:
            return frozenset()
        words |= got
    return frozenset(words)


def _kinship_words(unit: AbilityUnit, tree: ConceptTree) -> frozenset[str]:
    """The card's own creature types when ``unit`` checks that another card
    shares a creature type with it (kinship: an ``ObjectsShareQuality`` /
    ``SharesQuality`` against ``SelfRef``), else empty."""
    if not any(
        tag_of(n) in ("SharesQuality", "ObjectsShareQuality")
        and getattr(n, "quality", None) == "CreatureType"
        and tag_of(getattr(n, "reference", None)) == "SelfRef"
        for n in unit.iter_typed()
    ):
        return frozenset()
    return frozenset(
        w
        for w in (s.lower() for s in tree.card_subtypes)
        if w in _CREATURE_SUBTYPE_WORDS
    )


def gated_without_feed(
    card: Mapping,
    deck_tribes: Counter,
    deck_types: Counter,
    deck_keys: Counter | None = None,
) -> bool:
    """A card gated on what the deck lacks, dead whatever page asks: a
    choose-a-creature-type card (:func:`chooses_a_type_without_tribe`), or a
    card whose triggers and statics are mostly gated on a creature type, card
    type or gear type the deck lacks and that has nothing to activate
    (:func:`_unit_gates`) — whatever they do (Dragon Tempest's damage, a doer
    key) waits on Dragons that never come; its haste for flyers is not why it
    is played (2026-11-02). An activated ability no gate holds keeps a card
    (Asceticism's regeneration); Sai, Master Thopterist's draw costs two
    artifacts, so in a Humans deck it holds nothing."""
    if chooses_a_type_without_tribe(card, deck_tribes):
        return True
    gated = _unit_gates(card)
    if not gated.gates or 2 * len(gated.gates) < gated.units or gated.activated:
        return False
    return not any(
        gated.fed(gate, deck_tribes, deck_types, deck_keys) for gate in gated.gates
    )


def chooses_a_type_without_tribe(card: Mapping, deck_tribes: Counter) -> bool:
    """A choose-a-creature-type card (``chosen_type_matters``: Vanquisher's
    Banner, Kindred Discovery, Herald's Horn) in a deck with no tribe of
    ``2 * _FEEDER_FLOOR`` creatures: every ability it has hangs on the choice,
    its draw and its anthem alike, so it is dead whatever page asks for it —
    Vanquisher's Banner drew nothing for Bello's deck as a card-draw upgrade
    (2026-11-02)."""
    idents = _signal_idents_for(dict(card), include_membership=False)
    if not any(i.startswith("chosen_type_matters|") for i in idents):
        return False
    return _biggest_choosable_tribe(card, deck_tribes) < 2 * _FEEDER_FLOOR


def _choosable_types(card: Mapping) -> frozenset[str] | None:
    """The creature types a choose-a-type card may name when its choice is a
    list (Dawn-Blessed Pennant's "choose Elemental, Elf, Faerie, Giant,
    Goblin, Kithkin, Merfolk, or Treefolk"), lower-cased; ``None`` for a free
    choice (Vanquisher's Banner)."""
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            for n in unit.iter_typed():
                if tag_of(n) != "Choose":
                    continue
                ct = getattr(n, "choice_type", None)
                if not (isinstance(ct, MirrorVariant) and ct.key == "CreatureType"):
                    continue
                inner = ct.inner
                if isinstance(inner, MirrorVariant) and inner.key == "options":
                    opts = inner.inner
                    if isinstance(opts, list) and opts:
                        return frozenset(str(o).lower() for o in opts)
    return None


def _biggest_choosable_tribe(card: Mapping, deck_tribes: Counter) -> int:
    """The deck's biggest tribe the card may choose: any tribe for a free
    choice, only the listed ones for a listed choice — Most Wanted's twelve
    Humans fed Dawn-Blessed Pennant, which can't name one (2026-11-02)."""
    printed = getattr(deck_tribes, "printed", None)
    if printed is not None and not _chosen_type_on_battlefield(card):
        deck_tribes = printed
    options = _choosable_types(card)
    if options is None:
        return max(deck_tribes.values(), default=0)
    return max((deck_tribes.get(o, 0) for o in options), default=0)


#: A mana doubler's keys: a replacement that adds mana (Mana Reflection) or a
#: trigger on tapping for mana that adds more (Forsaken Monument).
_MANA_DOUBLER_KEYS = frozenset({"mana_amplifier", "tap_untap_matters"})


def _amplifies_mana(card: CardClass) -> bool:
    """Whether the card is a mana doubler (:data:`_MANA_DOUBLER_KEYS`) or a
    cost reducer for your spells: Ugin, the Ineffable's "Colorless spells you
    cast cost {2} less" went as Eldrazi Unbound's interaction excess
    (2026-11-02) — what it saves is mana, as a doubler's is."""
    return any(
        ident_key(i) in _MANA_DOUBLER_KEYS or i.startswith("cost_reduction|you|")
        for i in _signal_idents_for(card.record, include_membership=False)
    )


def _is_fixing(card: CardClass) -> bool:
    """A ramp source that fixes COLORS — a premium dork/rock/land-fetch the deck's mana
    base leans on (Birds of Paradise, Arcane Signet, Kodama's Reach). It reads as ramp,
    but trimming it for ramp-overflow strands the color base, so the over-band ramp cut
    sorts these LAST (cut redundant single-purpose ramp first).

    Fixing = produces ≥2 colors of battlefield mana, OR is a basic-land fetch (which
    produces no mana itself but retrieves the color the deck needs — produced_mana would
    miss it, so the worse 2-color rock was being protected while the any-basic fetcher,
    which fixes ALL the deck's colors, was cut first).

    A land search fixes by ``card_classify.land_search_fixes`` (the one rule
    ``is_fixing_land`` reads too)."""
    produced = card.record.get("produced_mana") or []
    if len({c for c in produced if c in "WUBRG"}) >= 2:
        return True
    return land_search_fixes(card.record)
