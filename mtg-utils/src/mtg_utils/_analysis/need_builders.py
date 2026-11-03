"""Reading a commander's text into needs: its effects, statics, triggers,
conditions, resources, redundancy and payoffs, off phase's concept trees
(split out of ``commander_need``)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from functools import partial
from typing import TYPE_CHECKING

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis.card_reads import plays_extra_lands
from mtg_utils._analysis.signal_base import Ident, ident_key
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    counter_kind,
    counter_kind_any,
    effect_player_reach,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_mana_value_floor,
    filter_non_types,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    iter_typed_nodes,
    or_arms,
    tag_of,
    trigger_def_event,
    trigger_scope,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._analysis.need_model import (
    HIGH_TOUGHNESS,
    Need,
    _type_words,
    card_type_count,
)
from mtg_utils._analysis.need_reads import (
    _CREATURE_TYPE_WORDS,
    _EVASION_KEYS,
    _EVASION_KEYWORDS,
    _EVENT_MAKER_KEYS,
    _OWN_DAMAGE_KEYWORDS,
    _animates_attackers,
    _cheap_spell,
    _drains_on_opponents_turns,
    _evasion_for,
    _grants_all_creature_types_node,
    _grants_the_commander,
    _has_x_cost,
    _holds_counters,
    _makes_tokens_of,
    _mana_value_reaches,
    _places_counters,
    _puts_minus_counters,
    _sacrifices_a_creature,
    _sacrifices_artifacts,
    _sacrifices_lands,
    _spends_counters,
    _stat,
    _supports_attackers,
    _takes_from_your_graveyard,
    _typal_payoff,
    typal_payoff_for,
)

#: Keys whose emitters put the commander's OWN cards into the graveyard (a
#: self-mill, a surveil, a loot, a sacrifice): what a graveyard-count or
#: card-type condition is raised by.
_LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(s.lower() for s in LAND_SUBTYPES)


#: Keys whose emitters put cards INTO your graveyard from outside the battlefield
#: (what a "put into your graveyard from anywhere" trigger is fed by). The
#: umbrella ``graveyard_makers`` is left out (:data:`_UMBRELLA_KEYS`): with it the
#: need is 12% of the pool and never specific; the fill is mill and discard.
_GRAVEYARD_FILL_KEYS: frozenset[str] = frozenset(
    {"mill_makers", "discard_makers", "discard_outlet"}
)


#: Keys whose emitters take cards OUT of the commander's graveyard (what a
#: "whenever one or more cards leave your graveyard" trigger is fed by).
_GRAVEYARD_LEAVE_KEYS: frozenset[str] = frozenset(
    {
        "creature_recursion",
        "reanimator",
        "permanent_recast",
    }
)


#: Umbrella keys a tenth of the pool carries: never a need's test on their own
#: (``graveyard_matters`` under Quintorius made "cards leaving your graveyard"
#: a 1,240-card page topped by Faithless Looting and Farewell, a hair under the
#: broad cutoff, so a graveyard commander's theme cuts went to it).
#: The signal keys a commander's own text emits when it spends or counts
#: deaths: the token makers among them want sacrifice outlets for their tokens
#: (``_resource_needs``).
_DEATH_KEYS: frozenset[str] = frozenset({"death_matters", "sacrifice_outlets"})


_UMBRELLA_KEYS: frozenset[str] = frozenset(
    {
        "graveyard_matters",
        "graveyard_makers",
        "permanent_etb",
        "enchantments_matter",
        "artifacts_matter",
        "creatures_matter",
        "attack_matters",
    }
)


#: Keys whose emitters grow or keep the counters already on your creatures, the
#: commander's own among them: proliferate, a counter doubler or bonus, a counter
#: mover, and the payoffs that read a creature's counters. What a commander whose
#: text counts the counters on itself (Zimone, Infinite Analyst's "costs {1} less
#: for each +1/+1 counter on ~") asks the deck for; the makers that put a counter
#: on a creature are left out (a sixth of a green pool).
_COUNTER_GROWTH_KEYS: frozenset[str] = frozenset(
    {
        "proliferate_makers",
        "counter_doubling",
        "counter_replace_bonus",
        "counter_move",
        "plus_one_matters",
    }
)


#: A doer key → the consumers ``metrics._cares_keys`` doesn't name, and the
#: idents among them:
#:
#: * ``plus_one_makers``: the payoffs that read your creatures' counters (a
#:   keyword for each creature with a counter — Chocobo Knights, Bramblewood
#:   Paragon; CR 122.1) and the movers that keep the counters a creature had
#:   when it leaves (The Ozolith, Resourceful Defense; CR 122.8).
#: * ``token_copy_makers``: the token payoffs, since "create a token that's a
#:   copy" puts a token onto the battlefield (CR 111.1 — Satya's attacker):
#:   Junk Winder's "Whenever a token you control enters", Ojer Taq's tripling.
#: * ``land_sacrifice_makers``: the cards that return lands from your graveyard,
#:   where a sacrificed land goes (CR 701.21a) — Life from the Loam, Crucible of
#:   Worlds, Ramunap Excavator (``permanent_recast|you|land``).
#: * ``land_sacrifice_makers`` also wants the extra land drops that replay the
#:   sacrificed lands and keep the drops coming — a land put from the hand
#:   (``extra_land_drop``: Burgeoning) or an additional land play
#:   (``card_reads.plays_extra_lands``: Exploration, Azusa, Oracle of Mul Daya,
#:   which the landfall lane folds into its umbrella key). The first adds Desert
#:   Bloom's guides make, while the tuner trimmed Oracle of Mul Daya as surplus
#:   ramp (2026-11-01).
#: * ``plus_one_makers`` also: the doublers, the replacement bonuses and the
#:   proliferators, which multiply the counters the commander places (a
#:   proliferate adds a counter of a kind already there, CR 701.34a) — the
#:   adds every +1/+1 counters guide makes (Doubling Season, Hardened Scales,
#:   Evolution Sage), which Bright-Palm's consumers need left out while its
#:   two-need obscurities led his page (Call for Backup, 2026-11-02).
_EXTRA_CONSUMER_KEYS: Mapping[str, frozenset[str]] = {
    "plus_one_makers": frozenset(
        {
            "counter_grants_kw",
            "counter_move",
            "counter_doubling",
            "counter_replace_bonus",
            "proliferate_makers",
        }
    ),
    "token_copy_makers": frozenset({"tokens_matter", "token_doubling"}),
    "land_sacrifice_makers": frozenset({"extra_land_drop"}),
}


_EXTRA_CONSUMER_IDENTS: Mapping[str, frozenset[str]] = {
    "land_sacrifice_makers": frozenset({"permanent_recast|you|land"}),
}


_EXTRA_CONSUMER_PREDICATES: Mapping[str, Callable[[dict], bool]] = {
    "land_sacrifice_makers": plays_extra_lands,
    "food_makers": _sacrifices_artifacts,
}


#: Payoff keys with no maker lane behind them: the payoff is the doing, so a
#: commander carrying one asks for cards with the same key
#: (``_redundancy_needs``).
_PAYOFF_REDUNDANCY_KEYS: frozenset[str] = frozenset({"graveyard_leave_matters"})


#: A commander payoff ident with no trigger mode of its own → the type-line
#: words a card needs to satisfy it.
_TYPE_PAYOFF_KEYS: Mapping[str, frozenset[str]] = {
    "artifacts_matter": frozenset({"artifact"}),
    "enchantments_matter": frozenset({"enchantment"}),
    "superfriends_matters": frozenset({"planeswalker"}),
    "voltron_matters": frozenset({"aura", "equipment"}),
    "lands_matter": frozenset({"land"}),
    "historic_matters": frozenset({"legendary", "artifact", "saga"}),
}


#: Core type → the token-maker keys that also put that type onto the
#: battlefield (an artifact-token maker enters an artifact).
_TYPE_TOKEN_KEYS: Mapping[str, frozenset[str]] = {
    "creature": frozenset({TOKEN_MAKER, "mass_token_makers"}),
    "artifact": frozenset(
        {"treasure_makers", "clue_makers", "food_makers", "blood_makers"}
    ),
    "enchantment": frozenset(),
}


def _walk(node: object, depth: int = 0) -> Iterator[object]:
    """Every ability-wrapper node under ``node`` (the node itself first)."""
    if depth > 40 or not isinstance(node, TypedMirrorNode):
        return
    yield node
    for fname in (
        "effect",
        "sub_ability",
        "execute",
        "mode_abilities",
        "static_abilities",
        "else_ability",
    ):
        child = getattr(node, fname, None)
        if not _present(child):
            continue
        if isinstance(child, list):
            for m in child:
                yield from _walk(m, depth + 1)
        else:
            yield from _walk(child, depth + 1)


#: The mana value from which a spell is "big" for a commander whose effect
#: scales with the greatest mana value among the spells cast this turn (Rootha's
#: X/X flier with haste: a five-mana spell makes a top-end body). The read's own
#: line, not a rule's.
BIG_SPELL_MV = 5


def _filter_colorless(filt: object) -> bool:
    """Whether the filter admits colorless objects only (a ``ColorCount``
    equal to zero — Zhulodok; CR 105.2c)."""
    for n in iter_typed_nodes(filt):
        if (
            tag_of(n) == "ColorCount"
            and getattr(n, "comparator", None) == "EQ"
            and int(getattr(n, "count", -1) or 0) == 0
        ):
            return True
    return False


def _spell_floor_need(
    filt: object, floor: int, desc: str, *, on_battlefield: bool = False
) -> Need | None:
    """The need for spells the filter admits at mana value ``floor`` or more:
    the filter's types and colour, the floor from its ``Cmc`` bound or the
    caller's line. ``on_battlefield``: the filter reads permanents, whose X is
    0 (CR 202.3e) — Walking Ballista is no artifact at 4+ for Bello, Bard of
    the Brambles (Animated Army, 2026-11-02)."""
    if floor <= 0:
        return None

    def arm_words(arm: object) -> tuple[frozenset[str], frozenset[str]]:
        """The type words an arm asks for and the ones it negates (Bello's
        "non-Equipment artifact" → {artifact}, {equipment})."""
        core = filter_core_types(arm) if _present(arm) else ()
        subs = filter_subtypes(arm) if _present(arm) else ()
        non = filter_non_types(arm) if _present(arm) else ()
        return (
            frozenset(
                w.lower() for w in (*core, *subs) if w.lower() not in ("card", "spell")
            ),
            frozenset(w.lower() for w in non),
        )

    # An ``Or`` filter admits a card of any arm's types ("instant or sorcery
    # spells": either); an arm naming no type admits every spell.
    arms = tuple(arm_words(arm) for arm in or_arms(filt)) if _present(filt) else ()
    arms = () if any(not a for a, _non in arms) else arms
    words = frozenset().union(*(a for a, _non in arms)) if arms else frozenset()
    colorless = _filter_colorless(filt)

    def holds(c: dict) -> bool:
        tw = _type_words(c)
        if "land" in tw:
            return False
        if arms and not any(a <= tw and not (non & tw) for a, non in arms):
            return False
        if colorless and c.get("colors"):
            return False
        if on_battlefield:
            return float(c.get("cmc") or 0) >= floor
        return _mana_value_reaches(c, floor)

    kinds = (" or ".join(sorted(words)) + " ") if words else ""
    label = f"{'colorless ' if colorless else ''}{kinds}spells at {floor}+ mana"
    return Need("payoff", label, desc, predicate=holds, mana_floor=int(floor))


def _spells_cast_filter(qty: object) -> object | None:
    """The spell filter of a ``SpellsCastThisTurn`` quantity or a ``TurnJournal``
    of ``SpellsCast`` (``None`` when it counts every spell)."""
    tag = tag_of(qty)
    if tag == "SpellsCastThisTurn":
        filt = getattr(qty, "filter", None)
        return filt if _present(filt) else None
    if tag == "TurnJournal" and tag_of(getattr(qty, "journal", None)) == "SpellsCast":
        filt = getattr(qty, "filter", None)
        return filt if _present(filt) else None
    return None


#: The line a sacrificed creature's power must reach, at most what mana value,
#: for a commander whose effect scales with that power (Dina, Essence Brewer's
#: "where X is the sacrificed creature's power"): a body that pays it off well
#: for what it costs. The read's own line, not a rule's.
FODDER_POWER = 5


FODDER_MV = 4


def _sacrificed_power_need(desc: str) -> Need:
    """A commander effect scaled by the power of the creature its cost
    sacrifices — phase's ``Power`` of ``CostPaidObject``, the sacrificed creature
    as it last existed on the battlefield (Dina's ruling): the need is cheap
    bodies with a high printed power (CR 208.1)."""
    return Need(
        "payoff",
        f"sacrifice fodder with power {FODDER_POWER}+ "
        f"at mana value {FODDER_MV} or less",
        desc,
        predicate=lambda c: (
            "creature" in _type_words(c)
            and _stat(c, "power") >= FODDER_POWER
            and float(c.get("cmc") or 0) <= FODDER_MV
        ),
    )


#: The mana value a permanent card reaches to be a target worth a commander's
#: graveyard-to-battlefield effect: the top end a deck cheats in rather than
#: casts — Death Toll's guides add Overlord of the Balemurk (7) and Hoarding
#: Broodlord (8) and keep Hornet Queen (7), and the deck's own Vile Mutilator,
#: Giant Adephage and Moldgraf Monstrosity sit there. At six the need is a tenth
#: of a two-colour pool (broad, :data:`BROAD_SHARE`), at seven a twenty-fifth.
#: This read's own line, no rule's.
REANIMATION_MV = 7


#: The card types a card has once it is on the battlefield (the permanent types
#: among :data:`CARD_TYPES`).
_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"artifact", "battle", "creature", "enchantment", "planeswalker"}
)


def _sizes_the_card(node: object) -> bool:
    """Whether the node bounds the card's own size — its mana value, power or
    toughness, as a filter property (Alesha's "power 2 or less") or a quantity
    checked of the target (Meren's "mana value is less than or equal to the
    number of experience counters": ``ObjectManaValue`` of ``Target``): the
    commander states its own line, which the payload read leaves to it."""
    return any(tag_of(n) in _SIZE_TAGS for n in iter_typed_nodes(node))


#: The typed tags that read a card's size: the filter properties and the
#: object quantities.
_SIZE_TAGS: frozenset[str] = frozenset(
    {"Cmc", "Power", "Toughness", "ObjectManaValue", "ObjectPower", "ObjectToughness"}
)


def _graveyard_return_filters(unit_node: object) -> Iterator[object]:
    """The filter of each card the unit puts from a graveyard onto the
    battlefield: a ``ChangeZone`` to the battlefield whose target sits in a
    graveyard (``InZone: Graveyard``) or whose origin is one, or whose
    ``ParentTarget`` is a card an earlier effect of the unit took from one
    (Winter's exile-then-return)."""
    nodes = list(iter_typed_nodes(unit_node))
    from_graveyard = [
        target
        for n in nodes
        for target in (getattr(n, "target", None),)
        if _present(target) and "Graveyard" in filter_inzone_zones(target)
    ]
    for n in nodes:
        if tag_of(n) != "ChangeZone" or getattr(n, "destination", None) != (
            "Battlefield"
        ):
            continue
        target = getattr(n, "target", None)
        if _present(target) and (
            "Graveyard" in filter_inzone_zones(target)
            or getattr(n, "origin", None) == "Graveyard"
        ):
            yield target
        elif tag_of(target) == "ParentTarget" and from_graveyard:
            yield from_graveyard[0]


def _reanimation_target_need(filt: object, desc: str) -> Need | None:
    """What a commander's graveyard-to-battlefield effect is FOR: a permanent
    card of the filter's types at :data:`REANIMATION_MV` or more, the payload
    the deck fills its graveyard to return. A land is no payload (Teval's
    "return a land card": the lands reads' own), nor a card of a creature type
    (the tribe's page); another player's graveyard is not the deck's. The
    caller skips a unit that sizes the card itself (:func:`_sizes_the_card`:
    Meren, Alesha)."""
    if filter_controller(filt) not in (None, "You"):
        return None
    core = {w.lower() for w in filter_core_types(filt)} - {"card", "permanent"}
    subs = {w.lower() for w in filter_subtypes(filt)}
    if "land" in core or subs:
        # A land is no payload; a return filtered to a creature type is the
        # tribe's — its members are the payload whatever they cost (Sidar
        # Jabari's Knights; Admiral Brass's Pirates, which come back as 4/4s),
        # and the tribal page holds them.
        return None
    non = frozenset(w.lower() for w in filter_non_types(filt))
    words = frozenset(core)

    def holds(c: dict) -> bool:
        tw = _type_words(c)
        if not tw & _PERMANENT_TYPES or "land" in tw:
            return False
        if words and not words <= tw:
            return False
        if non & tw:
            return False
        return float(c.get("cmc") or 0) >= REANIMATION_MV

    what = " ".join(sorted(words)) or "permanent"
    return Need(
        "payoff",
        f"{what} cards worth returning at {REANIMATION_MV}+ mana",
        desc,
        predicate=holds,
    )


#: The counter kinds a counter-spender need is never read for: +1/+1 counters
#: are the ``plus_one_makers`` consumers' (``_resource_needs``), loyalty a
#: planeswalker's own (``_loyalty_need``), and -1/-1 counters shrink.
_SPENDER_SKIP_KINDS = frozenset({"P1P1", "M1M1", "LOYALTY"})


def _counter_kind_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A commander that puts counters of another kind on other permanents
    (CR 122.1) wants the cards that spend that kind: Inspirit, Flagship
    Vessel's "two charge counters on up to one other target artifact" each
    combat feeds Titan Forge's and Golem Foundry's "Remove three charge
    counters" — both went to mana rocks on Counter Intelligence's theme page
    (2026-11-02). A counter it puts only on itself is its own business."""
    seen: set[str] = set()
    for n in iter_typed_nodes(unit_node):
        if tag_of(n) != "PutCounter":
            continue
        kind = counter_kind_any(n)
        if not kind or kind in _SPENDER_SKIP_KINDS or kind in seen:
            continue
        if tag_of(getattr(n, "target", None)) == "SelfRef":
            continue
        seen.add(kind)
        yield Need(
            "resource",
            f"cards that spend {kind.lower()} counters",
            desc,
            predicate=_spends_counters(kind),
        )
        # And the cards that put more of them where the spenders are, as the
        # commander does: Coretapper's "Put a charge counter on target
        # artifact" went to Talisman of Creativity under Inspirit, whose deck
        # holds five charge spenders (Counter Intelligence, 2026-11-02).
        yield Need(
            "resource",
            f"cards that put {kind.lower()} counters on other permanents",
            desc,
            predicate=_places_counters(kind),
        )


#: Maker keys a structural read feeds besides their lane (:func:`satisfies`).
_MAKER_PREDICATES: Mapping[str, Callable[[dict], bool]] = {
    "land_sacrifice_makers": _sacrifices_lands,
}


def _counted_counter_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A commander whose text counts your permanents with counters of one kind
    wants the cards that are such permanents: Rose Tyler's "each other
    permanent you control with a time counter on it" — The Moment, which
    puts a time counter on itself each upkeep, went to Martial Coup (Timey
    Wimey, 2026-11-02). +1/+1, -1/-1 and loyalty counters have needs of
    their own (:data:`_SPENDER_SKIP_KINDS`)."""
    seen: set[str] = set()
    for n in iter_typed_nodes(unit_node):
        if tag_of(n) != "ObjectCount":
            continue
        filt = getattr(n, "filter", None)
        if not _present(filt) or filter_controller(filt) != "You":
            continue
        if "Permanent" not in filter_core_types(filt) and "Creature" not in (
            filter_core_types(filt)
        ):
            continue
        for prop in iter_typed_nodes(filt):
            if tag_of(prop) != "Counters":
                continue
            counters = getattr(prop, "counters", None)
            kind = (
                getattr(counters, "data", None)
                if tag_of(counters) == "OfType"
                else None
            )
            if not isinstance(kind, str):
                continue
            kind = kind.upper()
            if kind in _SPENDER_SKIP_KINDS or kind in seen:
                continue
            seen.add(kind)
            yield Need(
                "payoff",
                f"permanents with {kind.lower()} counters",
                desc,
                predicate=_holds_counters(kind),
            )


def _token_kind_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A token effect that treats one kind of token better — Hazel's "If that
    token is a Squirrel, instead create two": a ``ConditionInstead`` over a
    ``TargetMatchesFilter`` naming the subtype, on an effect whose target is a
    token — asks for makers of THAT kind of token, beyond the token makers of
    any kind her "copy target token" asks for (Squirreled Away's guides add Nut
    Collector, Drey Keeper and Deranged Hermit; the tuner swapped Squirrel Nest
    for Fanatic of Rhonas, 2026-11-01)."""
    nodes = list(iter_typed_nodes(unit_node))
    if not any(
        tag_of(n) == "CopyTokenOf"
        and "Token" in filter_predicates(getattr(n, "target", None))
        for n in nodes
    ):
        return
    for n in nodes:
        if tag_of(n) != "TargetMatchesFilter":
            continue
        for sub in filter_subtypes(getattr(n, "filter", None)):
            yield Need(
                "payoff",
                f"{sub} token makers",
                desc,
                idents=frozenset({f"{TOKEN_MAKER}|you|{sub}"}),
            )


def _effect_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """Needs read off a unit's EFFECTS, whatever its origin: an effect scaled by
    the greatest mana value among the turn's spells (Rootha), a draw given to an
    opponent (Ms. Bumbleflower), an effect scaled by the power of the creature
    its cost sacrifices (Dina), a typed card taken from the graveyard (Anikthea:
    that type put there, :func:`_graveyard_take_needs`), a card put from the
    graveyard onto the battlefield (Winter: the payload,
    :func:`_reanimation_target_need`), and a token effect that favours one kind
    of token (Hazel's Squirrels, :func:`_token_kind_needs`)."""
    yield from _graveyard_take_needs(unit_node, desc)
    if not _sizes_the_card(unit_node):
        for filt in _graveyard_return_filters(unit_node):
            need = _reanimation_target_need(filt, desc)
            if need is not None:
                yield need
                break
    yield from _token_kind_needs(unit_node, desc)
    yield from _counter_kind_needs(unit_node, desc)
    yield from _counted_counter_needs(unit_node, desc)
    sacrifices = _sacrifices_a_creature(unit_node)
    for n in iter_typed_nodes(unit_node):
        if (
            sacrifices
            and tag_of(n) == "Power"
            and tag_of(getattr(n, "scope", None)) == "CostPaidObject"
        ):
            yield _sacrificed_power_need(desc)
            sacrifices = False  # one need per unit
            continue
        tag = tag_of(n)
        if (
            tag == "PropertyAggregate"
            and getattr(n, "function", None) == "Max"
            and getattr(n, "property", None) == "ManaValue"
        ):
            source = getattr(n, "source", None)
            if (
                tag_of(source) == "TurnJournal"
                and tag_of(getattr(source, "journal", None)) == "SpellsCast"
            ):
                need = _spell_floor_need(
                    _spells_cast_filter(source), BIG_SPELL_MV, desc
                )
                if need is not None:
                    yield need
        elif tag == "Draw" and effect_player_reach(unit_node, n) in (
            "target",
            "opponents",
            "per_opponent",
            "each",
        ):
            yield Need(
                "payoff",
                "opponents drawing payoffs",
                desc,
                keys=frozenset({"opponent_draw_matters"}),
            )
            yield Need(
                "redundancy",
                "opponents draw like the commander",
                desc,
                idents=frozenset({"target_player_draws|any|", "group_hug_draw|each|"}),
            )


def _static_needs(node: object, desc: str) -> Iterator[Need]:
    """Needs read off a static ability's ``affected`` filter: your spells or
    permanents at a mana-value floor (Zhulodok's colorless spells with mana
    value 7 or greater); and, when the static makes your permanents creatures
    and sends them into combat — an ``AddType`` of Creature beside a granted
    combat-damage trigger or haste (Bello's 4/4 Elementals that draw on
    combat damage) — the support those attackers want
    (:data:`_ATTACKER_SUPPORT_KEYS`): the anthems, the team protection and the
    evasion grants Animated Army's guides add (Asceticism, Glorious Sunrise,
    Sight of the Scalelords, Akroma's Memorial) where play-rate gave
    Panharmonicon and Mystic Forge (2026-11-02)."""
    # A static that makes permanents every creature type (Omo's everything
    # counters, Maskwood Nexus) asks for the payoffs those types unlock: any
    # lord, anthem or tribal trigger, a choose-a-type card — the guides'
    # Roaming Throne, Lord of the Unreal, Galerider Sliver and Coat of Arms
    # for Tricky Terrain, whose counters nothing in the precon used
    # (2026-11-02). Read before the controller gate: Omo's counters land on
    # any player's permanents, hers in practice.
    if _grants_all_creature_types_node(node):
        yield Need(
            "payoff",
            "payoffs for the creature types the commander grants",
            desc,
            predicate=_typal_payoff,
        )
    aff = getattr(node, "affected", None)
    if not _present(aff) or filter_controller(aff) != "You":
        return
    floor = filter_mana_value_floor(aff)
    if floor is not None:
        need = _spell_floor_need(aff, floor, desc, on_battlefield=True)
        if need is not None:
            yield need
    if _animates_attackers(node):
        yield Need(
            "event",
            "support for the attackers the commander makes",
            desc,
            predicate=_supports_attackers,
        )


def _tribe_payoff_needs(idents: Iterable[str], source: str) -> Iterator[Need]:
    """A commander naming a creature type of yours (Hakbal's Merfolk, Sliver
    Gravemother's Slivers, Éowyn's Humans — ``subtype_ref|you|<Type>``) asks
    for that tribe's payoffs (:func:`typal_payoff_for`): the lords, anthems
    and choose-a-type cards its guides add, which a tribe slot's upgrade must
    then keep — Merfolk Mistbinder went to Triton Shorestalker (Explorers of
    the Deep, 2026-11-02)."""
    for ident in sorted(set(idents)):
        key, scope, subject = Ident.parse(ident)
        if key == "subtype_ref" and scope == "you":
            kind = subject.lower()
            if kind in _CREATURE_TYPE_WORDS:
                yield Need(
                    "payoff",
                    f"payoffs for the commander's {subject} tribe",
                    source,
                    predicate=partial(typal_payoff_for, kinds=frozenset({kind})),
                )


def _has_pred(filt: object, name: str) -> bool:
    return name in filter_predicates(filt)


def _type_need(
    core: Iterable[str], subs: Iterable[str]
) -> tuple[frozenset[frozenset[str]], frozenset[str]]:
    """The type-line tests and token-maker keys for a filter's types."""
    words = {c.lower() for c in core if c.lower() != "card"}
    words |= {s.lower() for s in subs}
    if not words:
        return frozenset(), frozenset()
    keys: set[str] = set()
    for w in words:
        keys |= _TYPE_TOKEN_KEYS.get(w, frozenset())
    return frozenset({frozenset(words)}), frozenset(keys)


def _counter_filter_kind(node: TypedMirrorNode) -> str | None:
    """The counter kind a ``CounterAdded`` trigger watches (its
    ``counter_filter.counter_type``: ``M1M1``, ``P1P1``), ``None`` when it
    watches every kind. A bare ``{counter_type: …}`` strict-loads as a
    ``MirrorVariant`` keyed ``counter_type``."""
    filt = getattr(node, "counter_filter", None)
    if isinstance(filt, MirrorVariant) and filt.key == "counter_type":
        kind = filt.inner
    else:
        kind = getattr(filt, "counter_type", None) if _present(filt) else None
    return kind if isinstance(kind, str) else None


def _graveyard_fill_need(
    core: Sequence[str], subs: Sequence[str], desc: str, *, typed_only: bool = False
) -> Need | None:
    """The need for cards of the filter's types reaching your graveyard: fed by
    every way a card gets there, and by the way the type usually does — a land
    card by land sacrifice (The Gitrog Monster), a creature card by a sacrifice
    outlet or an edict (Sefris of the Hidden Ways). Not by token makers: a
    token is not a card (CR 108.2), so a token dying is no "creature card put
    into your graveyard". ``typed_only``: no need for an untyped card."""
    keys = set(_GRAVEYARD_FILL_KEYS)
    if "Land" in core or {s.lower() for s in subs} & _LAND_SUBTYPE_WORDS:
        keys.add("land_sacrifice_makers")
    if "Creature" in core:
        keys |= {"sacrifice_outlets", "edict_makers"}
    words = tuple(w for w in core if w not in ("Card", "Permanent")) + tuple(subs)
    what = " ".join(sorted(words)) or None
    if what is None and typed_only:
        return None
    label = (
        f"{what} cards reaching your graveyard"
        if what
        else "cards reaching your graveyard"
    )
    return Need("event", label, desc, keys=frozenset(keys))


def _graveyard_take_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A commander that takes a card of a type from its own graveyard — the
    target of an effect sits there (``InZone: Graveyard``) and is typed:
    Anikthea's "non-Aura enchantment card from your graveyard", Meren's and
    Mirko's creature card, Teval's land card — wants that type put there
    (:func:`_graveyard_fill_need`): Enduring Enchantments' guides add the
    discard outlets and self-mill that drop enchantments, where the tuner paged
    every popular enchantment (2026-11-01). An untyped card (Winter's "any
    number of cards") asks nothing the condition read does not."""
    seen: set[str] = set()
    for n in iter_typed_nodes(unit_node):
        filt = getattr(n, "target", None)
        if not _present(filt) or "Graveyard" not in filter_inzone_zones(filt):
            continue
        if filter_controller(filt) not in (None, "You"):
            continue
        if filter_owned_controller(filt) not in (None, "You"):
            continue
        need = _graveyard_fill_need(
            filter_core_types(filt), filter_subtypes(filt), desc, typed_only=True
        )
        if need is not None and need.label not in seen:
            seen.add(need.label)
            yield need


def _event_need(node: TypedMirrorNode, desc: str) -> Need | None:
    event = trigger_def_event(node)
    scope = trigger_scope(node)
    valid = getattr(node, "valid_card", None)
    core = filter_core_types(valid) if _present(valid) else ()
    subs = filter_subtypes(valid) if _present(valid) else ()
    preds = filter_predicates(valid) if _present(valid) else ()
    label = f"{event} makers"
    if event in ("surveil", "scry"):
        return Need(
            "event",
            f"{event} outlets",
            desc,
            idents=frozenset({f"topdeck_selection|you|{event}"}),
        )
    if event == "enters":
        types, keys = _type_need(core, subs)
        if "Token" in preds:
            keys = keys | _TYPE_TOKEN_KEYS.get("creature", frozenset())
            types = frozenset()
        if types or keys:
            return Need(
                "event",
                f"{' '.join(sorted(core + subs)) or 'permanent'} enters",
                desc,
                keys=keys,
                types=types,
            )
        return None
    if event == "cast_spell":
        if "HasXInManaCost" in preds:
            # "Whenever you cast your first spell with {X} in its mana cost
            # each turn" (Zimone, Infinite Analyst): the X spells. Stonecoil
            # Serpent went to Badgermole Cub on her page (Quandrix Unlimited,
            # 2026-11-02).
            return Need("event", "spells with {X}", desc, predicate=_has_x_cost)
        floor = filter_mana_value_floor(valid) if _present(valid) else None
        if floor is not None:
            return _spell_floor_need(valid, floor, desc)
        types, _keys = _type_need(core, subs)
        return (
            Need("event", f"cast {' '.join(sorted(core + subs))}", desc, types=types)
            if types
            else None
        )
    if event == "changes_zone":
        origin = getattr(node, "origin", None)
        dest = getattr(node, "destination", None)
        if origin == "Graveyard":
            return Need(
                "event",
                "cards leaving your graveyard",
                desc,
                keys=_GRAVEYARD_LEAVE_KEYS,
                predicate=_takes_from_your_graveyard,
            )
        if dest == "Graveyard":
            # "put into your graveyard from anywhere" (CR 603.6c: never a
            # leaves-the-battlefield ability).
            return _graveyard_fill_need(core, subs, desc)
        return None
    if event == "attacks":
        # "creatures enchanted by an Aura you control attack" (Killian): the
        # attachment is the need; a bare attack trigger is fed by every creature.
        if "HasAttachment" in preds or "EnchantedBy" in preds:
            # "enchanted by an Aura you control" names Auras alone (CR 303.4a:
            # an Aura enchants; Equipment is attached, CR 301.5); a bare
            # attachment filter admits both.
            aura_only = "aura" in desc.lower()
            words = {"aura"} if aura_only else {"aura", "equipment"}
            return Need(
                "event",
                "attachments",
                desc,
                types=frozenset({frozenset({w}) for w in words}),
                keys=frozenset() if aura_only else frozenset({"voltron_makers"}),
            )
        return None
    if event in ("dies", "leaves", "sacrificed", "exploited"):
        if "Land" in core:
            # "Whenever you sacrifice a land" (Hearthhull, the Worldseed) is fed
            # by land sacrifice (:func:`_sacrifices_lands`), never by creature
            # fodder: an event need, so the upgrade gate keeps it — Sprouting
            # Goblin's "Sacrifice a land: Draw a card" went to Shadow,
            # Mysterious Assassin while it was only the broad payoff (World
            # Shaper, 2026-11-02).
            if event != "sacrificed":
                return None
            return Need(
                "event", "lands you sacrifice", desc, predicate=_sacrifices_lands
            )
        keys = set(_EVENT_MAKER_KEYS[event])
        if "Token" in preds:
            keys = set(_TYPE_TOKEN_KEYS["creature"]) | {"sacrifice_outlets"}
        elif "NonToken" in preds:
            # "Whenever you sacrifice a nontoken Elemental" (Ashling, the
            # Limitless): a token is no nontoken creature, so the token makers
            # feed nothing; the outlets and edicts do.
            keys -= _TYPE_TOKEN_KEYS["creature"]
        return Need(
            "event",
            f"creatures that {event.replace('_', ' ')}",
            desc,
            keys=frozenset(keys),
        )
    if event == "counter_added" and _counter_filter_kind(node) == "M1M1":
        # "Whenever one or more -1/-1 counters are put on a creature" (Auntie
        # Ool, Cursewretch): fed by the -1/-1 counter lane's cards, a
        # proliferate, and a mover — moving a counter puts it onto the second
        # object (CR 122.5: The Ozolith's counters onto a target creature). A
        # -X/-X effect (``debuff_makers``: Disfigure) puts no counter.
        # And the cards that put them on: wither's or infect's damage to a
        # creature is -1/-1 counters (CR 702.80a, 702.90c), and a -1/-1
        # counter effect places them outright — Kulrath Knight went as a
        # ramp fill's cut under Auntie Ool (Blight Curse, 2026-11-02).
        return Need(
            "event",
            "-1/-1 counters put on creatures",
            desc,
            keys=frozenset(
                {"minus_counters_matter", "proliferate_makers", "counter_move"}
            ),
            predicate=_puts_minus_counters,
        )
    if event == "deals_damage" and tag_of(getattr(node, "valid_source", None)) == (
        "SelfRef"
    ):
        return _own_damage_grant_need(desc)
    if event == "deals_damage":
        # A keyword granted to a target is evasion only when the keyword is:
        # Zack Fair's indestructible supplied Ellivere's "enchanted creature
        # ... deals combat damage" and took Gylwain's Roles' slot (Virtue and
        # Valor, 2026-11-02).
        idents = frozenset(
            f"{key}|you|{k}"
            for key in ("keyword_bodies", "keyword_grant_target")
            for k in _EVASION_KEYWORDS
        )
        source_types = filter_subtypes(getattr(node, "valid_source", None))
        if source_types:
            # "Whenever one or more outlaws you control deal combat damage"
            # (Olivia, Opulent Outlaw; outlaws are Assassins, Mercenaries,
            # Pirates, Rogues and Warlocks, CR 700.12): an evasive body
            # outside those types connects for nothing — Hangarback Walker's
            # flying Thopters took Tenured Inkcaster's slot (Most Wanted,
            # 2026-11-02). A grant to your team or a target still feeds it.
            return Need(
                "event",
                "evasion for your attackers",
                desc,
                predicate=partial(_evasion_for, frozenset(source_types)),
            )
        return Need(
            "event",
            "evasion for your attackers",
            desc,
            keys=_EVASION_KEYS - {"keyword_grant_target"},
            idents=idents,
        )
    keys = _EVENT_MAKER_KEYS.get(event)
    if not keys:
        return None
    if event == "life_lost" and scope == "you":
        return None  # a self-life-loss watcher is fed by its own costs; not a need
    if event == "life_lost" and trigger_turn_constraint(node) in _OPPONENT_TURN_GATES:
        # "Whenever an opponent loses life for the first time during each of
        # their turns" (Valgavoth, Harrower of Souls): the makers that fire on
        # an OPPONENT'S turn — a trigger watching what opponents do (Rug of
        # Smothering's spells, Razorkin Needlehead's draws, Roiling Vortex's
        # upkeeps) — not your own spells' and artifacts' riders (Guttersnipe,
        # Reckless Fireweaver), which the tuner added where Endless
        # Punishment's guides add the punishers (2026-11-01).
        return Need(
            "event",
            "life loss on opponents' turns",
            desc,
            predicate=_drains_on_opponents_turns,
        )
    return Need("event", label, desc, keys=keys)


#: A trigger's turn gates that fire on opponents' turns (phase's ``constraint``).
_OPPONENT_TURN_GATES = frozenset({"OncePerOpponentPerTurn", "OnlyDuringOpponentsTurn"})


def _own_damage_grant_need(desc: str) -> Need:
    """A combat-damage trigger of the commander's own ("Whenever Sidar Jabari
    deals combat damage to a player"): only what reaches the commander feeds
    it — a grant to a target or the team of evasion or double strike (Duelist's
    Heritage), a grant to your commander, a lure. Another creature's own flying
    does not."""
    return Need(
        "event",
        "evasion and double strike for the commander",
        desc,
        keys=frozenset({"team_evasion_grant", "lure_makers"}),
        idents=frozenset(
            f"{prefix}|you|{kw}"
            for kw in _OWN_DAMAGE_KEYWORDS
            for prefix in ("keyword_grant_target", "team_buff")
        ),
        predicate=_grants_the_commander,
    )


def _cheap_spells_need(desc: str) -> Need:
    return Need("payoff", "cheap spells", desc, predicate=_cheap_spell, leads=False)


def _cast_power_need(cond: object, desc: str) -> Need | None:
    """A cast trigger's check of the cast spell's power ("If that spell's power
    is 4 or greater, draw a card. If that spell's power is 6 or greater, …" —
    Eshki, Temur's Roar): phase reads the triggering spell as ``CostPaidObject``
    in a ``SpellCast`` trigger (Cabaretti Revels' and Jodah's "lesser mana value"
    the same way). The need is creature cards whose printed power reaches the
    floor (CR 208.1: a creature card's power is printed in its lower right);
    a ``*`` power reads 0."""
    if getattr(cond, "comparator", None) not in ("GE", "GT"):
        return None
    lhs = getattr(cond, "lhs", None)
    qty = getattr(lhs, "qty", None) if _present(lhs) else None
    if tag_of(qty) != "Power" or tag_of(getattr(qty, "scope", None)) != (
        "CostPaidObject"
    ):
        return None
    rhs = getattr(cond, "rhs", None)
    if tag_of(rhs) != "Fixed":
        return None
    floor = int(getattr(rhs, "value", 0) or 0) + (
        1 if getattr(cond, "comparator", None) == "GT" else 0
    )
    if floor <= 0:
        return None
    return Need(
        "payoff",
        f"creature spells with power {floor}+",
        desc,
        predicate=lambda c, floor=floor: (
            "creature" in _type_words(c) and _stat(c, "power") >= floor
        ),
    )


def _condition_need(
    cond: object, desc: str, *, cast_trigger: bool = False
) -> Need | None:
    tag = tag_of(cond)
    if tag == "AbilityUseCountThisTurn" and cast_trigger:
        # "If this is the second time this ability has resolved this turn" on
        # a cast trigger (Ms. Bumbleflower): two spells a turn.
        if int(getattr(cond, "n", 0) or 0) >= 2:
            return _cheap_spells_need(desc)
        return None
    if tag == "QuantityCheck" and cast_trigger:
        return _cast_power_need(cond, desc)
    if tag != "QuantityComparison":
        return None
    lhs = getattr(cond, "lhs", None)
    qty = getattr(lhs, "qty", None) if _present(lhs) else None
    if qty is None:
        return None
    qtag = tag_of(qty)
    if qtag == "SpellsCastThisTurn":
        rhs = getattr(cond, "rhs", None)
        n = int(getattr(rhs, "value", 0) or 0) if tag_of(rhs) == "Fixed" else 0
        if n >= 2:
            return _cheap_spells_need(desc)
        filt = _spells_cast_filter(qty)
        core = filter_core_types(filt) if filt is not None else ()
        subs = filter_subtypes(filt) if filt is not None else ()
        types, _keys = _type_need(core, subs)
        return (
            Need("event", f"cast {' '.join(sorted(core + subs))}", desc, types=types)
            if types
            else None
        )
    if qtag == "DistinctCardTypes":
        # Raised by a card that is two types at once, or by a self-mill /
        # surveil that puts several cards (and so several types) in at once.
        return Need(
            "condition",
            "card types in your graveyard",
            desc,
            keys=frozenset({"mill_makers"}),
            idents=frozenset({"topdeck_selection|you|surveil"}),
            predicate=lambda c: card_type_count(c) >= 2,
        )
    if qtag == "ZoneCardCount":
        zone = getattr(qty, "zone", None)
        if zone == "Graveyard":
            return Need(
                "condition", "cards in your graveyard", desc, keys=_GRAVEYARD_FILL_KEYS
            )
        if zone == "Hand":
            return Need(
                "condition",
                "cards in hand",
                desc,
                keys=frozenset({"card_draw_engine", "big_hand_makers"}),
            )
        return None
    if qtag == "ObjectCount":
        filt = getattr(qty, "filter", None)
        core = filter_core_types(filt) if _present(filt) else ()
        subs = filter_subtypes(filt) if _present(filt) else ()
        types, keys = _type_need(core, subs)
        if types or keys:
            return Need(
                "condition",
                f"{' '.join(sorted(core + subs))} you control",
                desc,
                types=types,
                keys=keys,
            )
        preds = filter_predicates(filt) if _present(filt) else ()
        if "Token" in preds:
            return Need(
                "condition",
                "tokens you control",
                desc,
                keys=_TYPE_TOKEN_KEYS["creature"],
            )
    if qtag == "BattlefieldEntriesThisTurn":
        # "If another Human entered the battlefield under your control this
        # turn" (Éowyn, Shieldmaiden): the cards that put one onto the
        # battlefield — members of the type, and makers of its tokens.
        # Increasing Devotion's five Humans went to Burnished Hart under her
        # (Riders of Rohan, 2026-11-02).
        filt = getattr(qty, "filter", None)
        core = filter_core_types(filt) if _present(filt) else ()
        subs = filter_subtypes(filt) if _present(filt) else ()
        types, keys = _type_need(core, subs)
        idents = frozenset(f"{TOKEN_MAKER}|you|{sub}" for sub in subs)
        if types or keys or idents:
            return Need(
                "condition",
                f"{' '.join(sorted(core + subs))} entering this turn",
                desc,
                types=types,
                keys=keys,
                idents=idents,
            )
        return None
    if qtag in ("Devotion", "DevotionCount"):
        return None
    return None


def _counter_placement(trees: Sequence[ConceptTree]) -> tuple[bool, bool]:
    """Two facts about the commander's +1/+1 counters: whether any land on
    something other than itself (Captain America, Team Leader's "a +1/+1 counter
    on that Hero and a +1/+1 counter on ~"), and whether its own text counts the
    counters on itself (Zimone, Infinite Analyst's "for each +1/+1 counter on ~":
    a ``CountersOn`` operand scoped to the source)."""
    elsewhere = counts_own = False
    for tree in trees:
        for unit in tree.units:
            for c in unit.effect_concepts("place_counter"):
                node = c.node
                if tag_of(node) not in ("PutCounter", "PutCounterAll"):
                    continue
                if counter_kind(node) != "P1P1":
                    continue
                if tag_of(getattr(node, "target", None)) != "SelfRef":
                    elsewhere = True
            for n in iter_typed_nodes(unit.node):
                if (
                    tag_of(n) == "CountersOn"
                    and tag_of(getattr(n, "scope", None)) == "Source"
                ):
                    counts_own = True
    return elsewhere, counts_own


def _resource_needs(
    idents: Iterable[str], desc: str, *, trees: Sequence[ConceptTree] = ()
) -> Iterator[Need]:
    """What the commander produces → the payoffs that consume it."""
    from mtg_utils._tuner.metrics import _cares_keys

    seen: set[str] = set()
    idents = tuple(idents)
    # A commander that grows ONLY itself (Mirko's "+1/+1 counter on ~") makes no
    # counters the deck's counter payoffs could use; one that also grows others
    # (Captain America's Heroes) does. When its own text counts the counters on
    # itself (Zimone), the deck wants them grown and kept: proliferate, doublers,
    # the counter movers (``_COUNTER_GROWTH_KEYS``) — the upgrade guides' adds
    # for her (Branching Evolution, Evolution Sage, The Ozolith), none of which a
    # Mirko or Valgavoth guide reaches for.
    elsewhere, counts_own = _counter_placement(trees)
    self_grow = (
        any(i.startswith("self_counter_grow|") for i in idents) and not elsewhere
    )
    if self_grow and counts_own:
        yield Need(
            "resource",
            "counters on the commander",
            desc,
            keys=_COUNTER_GROWTH_KEYS,
        )
    # Every kind of creature token the commander makes feeds that kind's
    # payoffs (Clavileño's Vampires AND Demons): one consumers need over all
    # of them, whatever order the idents came in.
    token_kinds = frozenset(
        Ident.parse(ident).subject
        for ident in idents
        if ident.startswith(f"{TOKEN_MAKER}|") and Ident.parse(ident).subject
    )
    for ident in idents:
        key = ident_key(ident)
        if key == "plus_one_makers" and self_grow:
            continue
        if _self_life_payment(ident):
            continue
        if key in _UMBRELLA_KEYS:
            continue  # the umbrella's consumers are the umbrella
        if key == TOKEN_MAKER or key.endswith("_makers"):
            consumers = {k for k in _cares_keys(key) if k != key}
            consumers -= _UMBRELLA_KEYS
            consumers |= _EXTRA_CONSUMER_KEYS.get(key, frozenset())
            if key == TOKEN_MAKER:
                consumers |= {"sacrifice_outlets", "death_matters"}
            extra_idents = _EXTRA_CONSUMER_IDENTS.get(key, frozenset())
            if not (consumers or extra_idents) or key in seen:
                continue
            seen.add(key)
            idents_ = (
                frozenset(f"type_matters|you|{kind}" for kind in token_kinds)
                if key == TOKEN_MAKER
                else frozenset()
            ) | extra_idents
            yield Need(
                "resource",
                f"{key.replace('_makers', '').replace('_', ' ')} consumers",
                desc,
                keys=frozenset(consumers),
                idents=idents_,
                predicate=_EXTRA_CONSUMER_PREDICATES.get(key),
            )
            if key == TOKEN_MAKER and any(ident_key(i) in _DEATH_KEYS for i in idents):
                # The outlets on their own: the consumers need bundles every
                # token payoff and reads as broad in most pools (over
                # ``BROAD_SHARE``), so it leads no page and gates no upgrade —
                # Village Rites went for Esper Sentinel under Clavileño, whose
                # guides want more outlets (Blood Rites, 2026-11-02). Outlets
                # alone are six percent of a two-color pool. Only where the
                # commander's own text spends or counts deaths (Clavileño's
                # death trigger, Ghave's sacrifice cost): a token maker whose
                # tokens are the plan (Anikthea's enchantment copies, Teval's
                # Druids) wants no outlet for them — read for every token maker,
                # the 25 lost Parallel Lives, Rootborn Defenses and Ramunap
                # Excavator (2026-11-02).
                yield Need(
                    "resource",
                    "sacrifice outlets for the commander's tokens",
                    desc,
                    keys=frozenset({"sacrifice_outlets"}),
                )


def _loyalty_need(rec: Mapping) -> Need | None:
    """A planeswalker commander's loyalty is the loyalty counters on it (CR
    306.5c), and a proliferate gives it one more (CR 701.34a): the deck wants
    proliferate (Quintorius, History Chaser — Patrolling Peacemaker)."""
    if "planeswalker" not in _type_words(rec):
        return None
    return Need(
        "resource",
        "loyalty on the commander",
        rec.get("name", ""),
        keys=frozenset({"proliferate_makers"}),
    )


def _self_life_payment(ident: str) -> bool:
    """A ``lifeloss_makers`` ident scoped to the commander's own controller
    (Hazel's "pay 2 life"): a cost the commander pays, not life loss the
    deck's drain payoffs consume or a drain to make more of — the same call
    :func:`_event_need` makes for a self-life-loss watcher."""
    return ident.startswith("lifeloss_makers|you|")


def _doer_name(key: str) -> str:
    return key.replace("_makers", "").replace("_", " ")


#: The subject a type payoff ident carries for the event its trigger watches
#: (``lanes.board_and_ramp``'s type-payoff watchers: ``etb`` an enters trigger,
#: ``cast`` a cast trigger) → the label word.
_TYPE_EVENT_SUBJECTS: Mapping[str, str] = {"etb": "entering", "cast": "cast"}


def _redundancy_needs(idents: Iterable[str], desc: str) -> Iterator[Need]:
    """Cards that do what the commander itself does (its doer idents): the
    frameworks' "redundancy of the commander's key effect" (goad under Nelly,
    mill under Winter, Warrior tokens under Zurgo). The specificity floor
    keeps a generic doer (an attack trigger) from becoming a need."""
    for ident in idents:
        key, _scope, subject = Ident.parse(ident)
        if key in _UMBRELLA_KEYS and subject in _TYPE_EVENT_SUBJECTS:
            # The commander's own trigger on a card type entering or being cast
            # ("Whenever an enchantment you control enters" — Killian: the
            # ``enchantments_matter|you|etb`` ident): the cards with that same
            # trigger do what it does (Grim Guardian's constellation, Victor's
            # eerie, Ondu Spiritdancer). The umbrella key alone stays out.
            yield Need(
                "redundancy",
                f"{_TYPE_EVENT_SUBJECTS[subject]} "
                f"{key.removesuffix('s_matter').replace('_', ' ')} payoffs "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )
            continue
        if key in _UMBRELLA_KEYS or _self_life_payment(ident):
            continue
        if key == TOKEN_MAKER or key.endswith("_makers"):
            yield Need(
                "redundancy",
                f"{_doer_name(key)}{(' ' + subject) if subject else ''} "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )
        elif key in _PAYOFF_REDUNDANCY_KEYS:
            # A payoff that IS the doing — Teval's "whenever one or more cards
            # leave your graveyard" has no maker lane behind it; the cards that
            # do what he does carry the same key (Desecrated Tomb, Chalk
            # Outline, Tormod, the Desecrator: Sultai Arisen's guides' adds).
            yield Need(
                "redundancy",
                f"{key.removesuffix('_matters').replace('_', ' ')} payoffs "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )


def _payoff_needs(
    idents: Iterable[str], desc: str, *, floor_read: bool = False
) -> Iterator[Need]:
    """A commander payoff with no trigger of its own → what feeds it.

    ``floor_read``: the commander's trees already gave a mana-value-floor need
    (:func:`_spell_floor_need` off its own filter). That read keeps the filter's
    negations — Bello's "non-Equipment artifact" — where the ``animate_makers``
    ident's subject (``Artifact>=4``) drops them, so the ident's need is skipped:
    with both, Hammer of Nazahn and Leyline Axe led Animated Army's page as
    artifacts at 4+ mana Bello never animates (2026-11-01)."""
    idents = list(idents)
    keys_held = {ident_key(ident) for ident in idents}
    # The commander's own suit is Auras: an ``aura_*`` ident and no equipment one.
    aura_only = any(k.startswith("aura_") for k in keys_held) and not any(
        "equip" in k for k in keys_held
    )
    for ident in idents:
        key, _scope, subject = Ident.parse(ident)
        if key == "type_matters":
            # A tribe the commander pays off is the tribal avenue's page already
            # (its members, plus changelings); a need page of it would add the
            # same cards twice over.
            continue
        if key in _TYPE_PAYOFF_KEYS:
            words = _TYPE_PAYOFF_KEYS[key]
            if key == "voltron_matters" and aura_only:
                # A voltron commander whose own suit is Auras (Ellivere's
                # Virtuous Roles) asks for Auras: an Equipment is a suit it
                # never wears (Virtue and Valor's guides add Auras and
                # enchantress draw; its pages led with Hammer of Nazahn and
                # Thran Power Suit, 2026-11-01).
                words = frozenset({"aura"})
            keys: set[str] = set()
            for w in words:
                keys |= _TYPE_TOKEN_KEYS.get(w, frozenset())
            if subject == "token":
                # A payoff for the type's TOKENS (Gimbal's "artifact tokens you
                # control with different names"): the token makers alone, never
                # every card of the type — a mana rock is an artifact, not what
                # Gimbal counts. Measured 2026-11-01 on Tinker Time: the
                # Artifacts page led with Fellwar Stone, Mind Stone and Thought
                # Vessel over Big Score and Idol of Oblivion.
                if keys:
                    # And any card making a token of the type — a Thopter, a
                    # Servo, a copy "except it's an artifact": Gimbal counts
                    # every differently named artifact token, and Feldon of the
                    # Third Path went as a draw fill's cut (Tinker Time,
                    # 2026-11-02).
                    yield Need(
                        "payoff",
                        f"{' '.join(sorted(words))} token makers",
                        desc,
                        keys=frozenset(keys),
                        predicate=_makes_tokens_of(frozenset(words)),
                    )
                continue
            yield Need(
                "payoff",
                f"{key.replace('_', ' ')}",
                desc,
                types=frozenset({frozenset({w}) for w in words}),
                keys=frozenset(keys),
            )
        elif key == "keyword_tribe" and subject:
            # A lord of a keyword wants bodies with the keyword. Only a few
            # keywords are a ``keyword_bodies`` lane (evasion, haste); the
            # rest (defender — Felothar's walls) are read off the card's own
            # keyword list, the bodies lane's source too.
            kw = subject.lower()
            yield Need(
                "payoff",
                f"{kw} bodies",
                desc,
                idents=frozenset({f"keyword_bodies|you|{kw}"}),
                predicate=lambda c, kw=kw: (
                    kw in {k.lower() for k in c.get("keywords") or ()}
                ),
            )
        elif key == "animate_makers" and ">=" in subject and not floor_read:
            word, _sep, floor = subject.partition(">=")
            w, n = word.lower(), int(floor or 0)
            yield Need(
                "payoff",
                f"noncreature {w} at {n}+ mana",
                desc,
                predicate=lambda c, w=w, n=n: (
                    w in _type_words(c)
                    and "creature" not in _type_words(c)
                    and float(c.get("cmc") or 0) >= n
                ),
                mana_floor=n,
            )
        elif key == "colorless_matters":
            yield Need(
                "payoff",
                "colorless spells",
                desc,
                predicate=lambda c: (
                    not c.get("colors") and "land" not in _type_words(c)
                ),
            )
        elif key == "toughness_combat":
            # A commander that reads toughness (Felothar assigns combat damage
            # by it, Pantlaza discovers for it) wants a HIGH toughness, not a
            # butt: Ghalta, Primal Hunger's 12 serves Pantlaza as Wall of Souls'
            # 4 serves Felothar. "Toughness over power" put Snubhorn Sentry and
            # Looming Altisaur ahead of Ghalta and Gishath on the Dinosaur page
            # (2026-11-01).
            yield Need(
                "payoff",
                "high toughness",
                desc,
                predicate=lambda c: (
                    _stat(c, "toughness") >= HIGH_TOUGHNESS
                    and "creature" in _type_words(c)
                ),
            )
        elif key == "energy_matters":
            # Energy is a counter on a player (CR 107.14), so a proliferate
            # gives you one more (CR 701.34a: "permanents and/or players that
            # have a counter") — Metastatic Evangel under Satya.
            yield Need(
                "payoff",
                "energy makers",
                desc,
                keys=frozenset({"energy_makers", "proliferate_makers"}),
            )
        elif key == "spellcast_matters":
            yield Need(
                "payoff",
                "instants and sorceries",
                desc,
                types=frozenset({frozenset({"instant"}), frozenset({"sorcery"})}),
                leads=False,
            )
        elif key == "second_spell_matters":
            yield _cheap_spells_need(desc)
        elif key.startswith("wants_"):
            base = key[len("wants_") :]
            makers = (
                {TOKEN_MAKER, "mass_token_makers"}
                if base == "fodder"
                else {f"{base}_makers"}
            )
            makers &= _served_keys()
            if makers:
                yield Need("payoff", f"{base} makers", desc, keys=frozenset(makers))
        elif key == "tokens_matter":
            # A token payoff (Hazel's "tap X untapped tokens", "copy target
            # token you control") is fed by token makers of any kind — the
            # ``wants_fodder`` keys, since no ``tokens_makers`` key is served.
            yield Need(
                "payoff",
                "token makers",
                desc,
                keys=frozenset({TOKEN_MAKER, "mass_token_makers"}),
            )
        elif key.endswith("_matters"):
            base = key[: -len("_matters")]
            maker = f"{base}_makers"
            if maker in _served_keys() and maker not in _UMBRELLA_KEYS:
                yield Need(
                    "payoff",
                    f"{base} makers",
                    desc,
                    keys=frozenset({maker}),
                    predicate=_MAKER_PREDICATES.get(maker),
                )


def _served_keys() -> frozenset[str]:
    from mtg_utils._analysis.lanes import SERVED_SIGNAL_KEYS

    return frozenset(SERVED_SIGNAL_KEYS)
