"""Board wipe — how well a card sweeps the board (the ``board_wipe`` role).

A sweep is an effect the shared lanes call one — ``mass_removal_effects`` /
``mass_bounce_effects`` / ``mass_shrink_effects`` (``lanes.mana_and_wipes``:
the ``mass_removal`` and ``mass_bounce`` keys' own walks, and the one-shot mass
shrink, one-sided or not, the board-wipe role counts beside them) — or a static
population shrink (Elesh Norn, ``static_population_shrinks``). The read takes
those effects as the lanes hand them, vetoes included (a your-side or combat-only
shrink, an Aura's own creature). An overload spell counts too: phase keeps only
its targeted mode, and overload swaps every "target" for "each" (CR 702.96a), so
Cyclonic Rift and Damn read as the sweeps they are cast for, their base mode's
effect at the overload cost (``crosswalk.overload_sweep``, the lanes' own read).
A sweep of only your own permanents, or of your own cards (Glimpse of
Tomorrow), is not one; nor is "and all other permanents with the same name"
trailing a targeted kill (Maelstrom Pulse); nor an exile the same ability
returns to the battlefield (Planar Guide, Sudden Disappearance: the shared
tree's blink return); nor one on a transform back face (Jin-Gitaxias's
Great Synthesis). A spree mode costs its own additional cost (Final Showdown), and an
enters trigger the X paid to cast its permanent (The Meathook Massacre). A clean
sweep is one the card is cast or activated for, never one an event fires
(Sarkhan's Unsealing), and one at four mana or less (Wrath of God) is the
reference wipe.

Fitted on the 562 commander-legal cards whose MAIN job is the sweep (an instant
or sorcery's own spell, or the ETB, chapter or activated ability of a permanent
that is neither a creature nor a planeswalker): cross-validated Spearman 0.497
against play-rate; the precon guides' wipe adds sit at the 94th percentile of
their color identity's wipes by this read (91st by play-rate); among each deck's
wipes the read's bottom two hold 9 guide cuts of 50 (play-rate's 10, mana
value's 7). Strong enough to ORDER candidates. The score is given to every card
with a sweep of its own — a creature or planeswalker with one too — though only
the job cards were fitted.

Read since 2026-10-24's last pass: an X paid in cards is an X (Sickening
Dreams, CR 107.3a); a pitch cost is the cards it pitches (Force of Despair, CR
118.9); a rider keeping your lands tapped is the next turn's mana (Bontu's Last
Reckoning, CR 502.3); a shrink that repeats whenever a creature dies this turn
chains (Massacre Girl, CR 603.7a); a choice the sweep's filter never reads limits
it (Harsh Mercy, Sudden Demise, Void); a draw "each player who controls" a
creature gets is no rider for the caster (Shatter the Sky, Depopulate); and the
clauses phase drops whole are read by name (``_CLAUSE_DROPPED``: Extinction,
Do or Die), each retired by its canary. An X the card
defines (CR 107.3) scales when the deck fills what it counts (Mutilate's Swamps,
Terror Tide's permanent cards in your graveyard) and is narrow when the count
is bounded (Deluge of Doom's card types, Essence Pulse's life gained,
:data:`_BOUNDED`); a sweep behind a coin flip is gated (Boompile, CR
705.1-705.2); a creature's activation costs its mana as any permanent's does
(Jaya Ballard, Task Mage; Infected Vermin; CR 602.2); a discount behind a
board-count condition is taken on the board the read assumes, one behind any
other condition at half (Hour of Revelation, Avenge; CR 601.2f); and tokens the
wiped players create are theirs (CR 111.2), no rider and no clean sweep (March
of Souls, The Phasing of Zhalfir, Mogg Infestation).

Read since 2026-10-25: an amount that is no count reads by what its rules text
names, never by phase's wrapper — the size of an object of the caster's own at
``KILL_SIZE`` (one paid as a cost: Ichor Explosion's sacrificed creature,
Corpse Explosion's exiled one; Cloudkill's greatest mana value of a commander
you own), a "this way" set of the caster's own cards scaling (Specter of
Mortality's creature cards exiled from your graveyard), and any other narrow
(Volcanic Eruption's "Destroy X target Mountains", anyone's, capped by X).
Given its deck (``JobRead.in_deck``), the read takes a count of a type only a
deck built on it holds (Olivia's Wrath's Vampires, Gates Ablaze's Gates) and
the size of a sacrificed creature off the deck itself (:func:`_deck_magnitude`),
the sweep killing in proportion: Olivia's Wrath reads 0.32 in Blood Rites
(0.15 deck-free), Gates Ablaze -0.08, 0.02 and 0.14 among 3, 8 and 15 Gates.
The caster picks the object a size reads off when it is a target among the
creatures they control (Chandra's Ignition and Waltz of Rage, "Target creature
you control deals damage equal to its power"; Nibelheim Aflame, Showstopping
Surprise and Nova Flame's "it") or the creature they sacrifice in the sweep's
own instructions (Rupture, CR 608.2c / 701.21a), so it reads as a cost's object
does. A size of the source itself reads its printed one (Jack of Hearts,
Volatile Hero's dying power; the effect uses his last known power, CR 608.2h,
which the read takes at the card's own, its own call), a negative power reading
0 (CR 107.1b).

Left unread (none a guide add or a pick of the 25-precon tune): an exile of
each permanent sharing a name (Eye of Singularity); a blocked-by slice phase
drops (Glyph of Reincarnation); a pitch or a discarded X counts a card as
one mana, so Sunscour's two white cards read as a two-mana Wrath (no
card-disadvantage feature); and a size read off a card the caster takes from a
graveyard (Volcanic Vision's instant or sorcery, Too Greedily, Too Deep's
creature card from any graveyard) reads narrow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    JOB_READS,
    KILL_SIZE,
    activation_mana,
    cast_cost,
    faces,
    fixed_value,
    front_mana_cost,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.lanes._shared import sacrifice_actor_scope
from mtg_utils._analysis.lanes.mana_and_wipes import (
    mass_bounce_effects,
    mass_removal_effects,
    mass_shrink_effects,
    static_population_shrinks,
)
from mtg_utils._analysis.signal_trees import derived_memo, signal_trees_for
from mtg_utils._analysis.write_back import MISSING
from mtg_utils._card_ir.crosswalk import (
    _DIRECTED_PLAYER_TAGS,
    BASIC_LAND_TYPE_COLORS,
    EFFECT_CONCEPTS,
    SWEPT_PERMANENT_TYPES,
    affected_tag,
    change_zone_dirs,
    count_operand_qty,
    effect_filter,
    effect_owner_player_scope,
    filter_admits,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_owners,
    filter_predicates,
    filter_subtypes,
    iter_cost_leaves,
    iter_static_defs,
    iter_typed_nodes,
    mana_value_of_cost,
    modify_cost_mode,
    overload_sweep,
    picked_by_caster,
    quantity_referent,
    quantity_scope,
    quantity_threshold,
    recipient_tag,
    static_affected,
    static_mode_tag,
    tag_of,
)
from mtg_utils._card_ir.trees import fixed_stat, object_facts, phase_records_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtg_utils._card_ir.crosswalk import (
        AbilityUnit,
        ConceptNode,
        ConceptTree,
        ObjectFacts,
    )
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

#: The permanent types a sweep is read as reaching: the lanes' swept types
#: (``crosswalk.SWEPT_PERMANENT_TYPES``), "permanent" read as all of them.
_SWEPT = SWEPT_PERMANENT_TYPES - {"Permanent"}
_SWEEP_TYPES = _SWEPT | {"Permanent", "Battle"}
#: The card types a ``Non`` entry can take out of the sweep; any other negated
#: word (non-Dragon) spares a class instead.
_CORE_TYPES = _SWEPT | {"Land", "Battle"}
#: Leaves the permanent gone for good (sacrifice is not destruction, CR 701.21a).
_KILLS = frozenset({"destroy", "exile", "tuck", "sacrifice"})
#: A variable amount the caster sizes (X) or a count of the board's creatures.
_SCALING = 99
#: A count of something narrow (spells cast from exile this turn, the Beasts on
#: the battlefield) or a bounded one (:data:`_BOUNDED`).
_NARROW_COUNT = 2
#: Counts with a small cap, or a floor of the card's own, whatever the deck
#: holds: distinct card types (Deluge of Doom's, among the CR 205.2a types a
#: graveyard holds), basic land types (domain: five, CR 305.6), the life gained
#: this turn (Essence Pulse gains its own 2 first), and cards in hand, which the
#: cleanup step cuts back to the maximum hand size, normally seven (CR 402.2,
#: 514.1), and which the caster spends casting spells (Kagemaro, First to
#: Suffer). The read's own call: each reads as ``_NARROW_COUNT``.
_BOUNDED = frozenset(
    {"DistinctCardTypes", "BasicLandTypeCount", "LifeGainedThisTurn", "HandSize"}
)
#: Object counts: what is on the battlefield (``ObjectCount``) or in a zone
#: (``ZoneCardCount``). Of yours (``crosswalk.quantity_scope``), the deck fills
#: them (Mutilate's Swamps, Dead of Winter's snow permanents, Terisiare's
#: Devastation's artifacts, Terror Tide's permanent cards in your graveyard), so
#: they scale, unless they name a type only a deck built on it holds
#: (:func:`_built_around`).
_FILLED = frozenset({"ObjectCount", "ZoneCardCount"})
#: The units a card is cast or activated for: a trigger from elsewhere (cycling,
#: a delayed cast trigger) is a second read.
_PRIMARY = frozenset({"spell", "etb", "chapter", "activated", "loyalty", "static"})
#: A slice of the board a choice the filter never reads limits the sweep to
#: (Sudden Demise's chosen colour, Void's number, Extinction's type): narrow.
_CHOSEN_SLICE = "ChosenSlice"
#: Filter predicates that hit only a combat / state / colour / keyword slice.
_NARROW = frozenset(
    {
        "Attacking",
        "Blocking",
        "BlockStatus",
        "Tapped",
        "Untapped",
        "CombatRelation",
        "BlockedThisTurn",
        "DealtDamageThisTurn",
        "WasDealtDamageThisTurn",
        "EnteredThisTurn",
        "ZoneChangedThisTurn",
        "WithKeyword",
        "WithoutKeyword",
        "HasColor",
        "IsChosenColor",
        "ColorCount",
        "EnchantedBy",
        "SharesQuality",
        "HasSupertype",
        "Token",
        "ControlledContinuouslySinceTurnBegan",
        "ManaValueParity",
        "DistinctFrom",
        _CHOSEN_SLICE,
    }
)
#: Filter predicates that leave standing a class the caster can arrange to be
#: theirs: nontoken, nonlegendary, no counters, a named exclusion.
_SPARES = frozenset(
    {
        "NonToken",
        "NotSupertype",
        "Counters",
        "Not",
        "NotColor",
        "NotHistoric",
        "IsChosenCreatureType",
    }
)
#: A fixed mana-value or power bound (Culling Ritual, Dusk).
_SIZED = frozenset({"Cmc", "PtComparison"})
#: A bound the caster sets (Pernicious Deed's X, Expel the Interlopers' number).
_CHOSEN_QTY = frozenset({"Variable", "CostXPaid", "ChosenNumber"})
#: The creatures on the battlefield when a Commander deck casts its wipe — what
#: a "{1} less for each creature on the battlefield" discount is worth
#: (Blasphemous Act, Vanquish the Horde). The count is every creature, yours and
#: the opponents' (the cards' own text), at the table ``_UNDAUNTED`` reads: two a
#: seat over four seats, a board worth wiping. The read's own call (2026-10-24);
#: at six, Vanquish's {6}{W}{W} read two mana and Blasphemous Act's {8}{R} three,
#: though on any board of eight or more Act costs {R} and Vanquish {W}{W}.
_BOARD_CREATURES = 8
#: A discount behind a condition holds or not as the cost is locked in (CR
#: 601.2f). One counting the board's permanents (Hour of Revelation's "ten or more
#: nonland permanents on the battlefield") holds on the board the read casts a
#: wipe into (``_BOARD_CREATURES``' creatures and the artifacts and enchantments
#: beside them), so it is taken whole; any other (Avenge's "if a player attacked
#: you during their last turn") a deck-free read can't see, so it is taken at
#: this share. The read's own call, as the ramp read halves the mana a condition
#: gates.
_CONDITIONAL_DISCOUNT = 0.5
#: The X that clears a Commander board when nothing on the card says more.
_BOARD_X = 4
#: Undaunted's discount at a four-player table: {1} per opponent (CR 702.125a).
_UNDAUNTED = 3
#: What the reference wipe costs: a clean sweep of every creature at four mana
#: (Wrath of God, Damnation, Supreme Verdict) is the board wipe a Commander deck
#: is built around, and one at three (Toxic Deluge, Blasphemous Act on a full
#: board) only better. The read's own call (2026-10-24): at three, Wrath of God
#: and Damnation scored 0.32, below a six-mana Final Showdown.
_REFERENCE_COST = 4
#: The cost at or under which a sweep that lets creatures through is the cheap,
#: small kind (Pyroclasm, Anger of the Gods).
_CHEAP = 3
#: What a card paid from hand (a pitch, a discarded X) costs, in mana: one, the
#: price of the cheapest cantrip (Opt's {U}). The read's own call, a floor: the
#: read has no card-disadvantage feature.
_CARD_MANA = 1.0
#: Sweeps whose limiting clause phase (v0.104.0) drops whole — no ``Choose``
#: node, no filter predicate, nothing structural left to read — by what the
#: clause does. Extinction destroys only "the creature type of your choice"
#: (narrow); Swarmyard Massacre's "-1/-1 for each" spares Insects, Rats, Spiders
#: and Squirrels (its count is yours, which the read takes at two either way);
#: Do or Die destroys one of two piles of a target player's creatures (CR
#: 700.3: one-sided, the other pile spared). Each is retired by its
#: ``test_*_dropped_canary`` once phase types the clause. Census 2026-10-24: the
#: commander-legal sweeps whose text limits them and whose tree carries no
#: limit.
_CLAUSE_DROPPED: dict[str, str] = {
    "Extinction": "narrow",
    "Do or Die": "pile",
}


@dataclass(frozen=True)
class _Sweep:
    """One mass effect: what it does, to what, under what terms."""

    mode: str  # destroy | exile | tuck | sacrifice | damage | shrink | bounce | ...
    types: frozenset[str]  # the permanent types it reaches (``_SWEPT``)
    ctrl: str | None  # whose permanents: Opponent / TargetPlayer / None (all)
    preds: frozenset[str]  # the filter's predicates (a caster-set bound dropped)
    spares: bool  # a Not arm, a non-subtype, "other", or each player keeps some
    mag: int | None  # damage / toughness taken; None = not a sized effect
    kind: str  # spell | etb | chapter | trigger | activated | loyalty | static
    gated: bool  # a condition, a delayed trigger, or text phase couldn't parse
    delayed: bool  # under a CreateDelayedTrigger (Kozilek's Return's 5 damage)
    x_floor: int | None  # "if X is n or more"
    x_bound: bool  # a size bound the caster sets
    act_mana: int | None  # an activated ability's mana cost
    self_sac: bool  # the activation sacrifices its source (one use)
    event: str | None  # a trigger's event
    overload: bool
    modal: bool  # a modal spell, or more than one sweep unit
    rider: bool  # a draw, token or life for the caster in the same unit
    discount: tuple[str, float, int] | None  # (board|fixed, generic, cap) reduction
    face_cmc: int | None  # the face's own printed mana value
    mode_cost: int  # a spree / tiered mode's own additional cost (CR 702.172a)
    x_cards: bool = False  # an X paid in cards (a discard of X, CR 107.3a)
    drawback: bool = False  # keeps your lands tapped (CR 502.3)
    refills: bool = False  # the wiped players get tokens back (CR 111.2)
    # The quantity of an amount the deck decides (:func:`_deck_amount`).
    amount: object = field(default=None, compare=False, repr=False)


#: The field a sweep effect's size sits on: a damage amount, a shrink's
#: toughness.
_AMOUNT_FIELDS = {
    "DamageAll": "amount",
    "DealDamage": "amount",
    "PumpAll": "toughness",
    "Pump": "toughness",
}


def _amount_qty(node: TypedMirrorNode, field: str) -> object | None:
    """The quantity under a non-fixed amount on ``node.field``, through phase's
    ``Quantity`` / ``Multiply`` / ``Offset`` wrappers (a shrink's ``Multiply(-1,
    …)`` is only its sign)."""
    return count_operand_qty(
        node, fields=(field,), wrappers=("Quantity", "Multiply", "Offset")
    )


def _scale(
    node: TypedMirrorNode, field: str, unit: AbilityUnit, own_power: int | None
) -> int:
    """A non-fixed amount on ``node.field`` (a damage amount, a shrink's
    toughness), read by what it counts: ``_SCALING`` for an X the caster sizes,
    a count of the board's creatures (Chain Reaction), a count the deck fills
    (:data:`_FILLED`) or a set of the caster's own cards the unit moves
    (:func:`_tracked_set_fills`); ``_NARROW_COUNT`` for a bounded count
    (:data:`_BOUNDED`), a count of anything narrower, or a set the unit's other
    effects make of any player's cards; ``KILL_SIZE`` for a size of one of the
    caster's own objects (:func:`_own_size`); the source's own power, its printed
    ``own_power``, a negative one reading 0 (CR 107.1b: "If a calculation that
    would determine the result of an effect yields a negative number, zero is
    used instead"). Anything else reads narrow."""
    amount = getattr(node, field, None)
    if tag_of(amount) == "Variable":
        return _SCALING
    qty = _amount_qty(node, field)
    tag = tag_of(qty)
    if tag in ("Variable", "CostXPaid"):
        return _SCALING
    if tag in _BOUNDED:
        return _NARROW_COUNT
    if tag in _FILLED and quantity_scope(qty) == "you":
        return _NARROW_COUNT if _built_around(qty) else _SCALING
    if tag == "ObjectCount":
        creatures = "Creature" in filter_core_types(getattr(qty, "filter", None))
        return _SCALING if creatures else _NARROW_COUNT
    if tag == "FilteredTrackedSetSize":
        return _SCALING if _tracked_set_fills(node, unit) else _NARROW_COUNT
    if _own_size(qty, unit, node) is not None:
        return KILL_SIZE
    if (
        tag == "Power"
        and quantity_referent(qty, unit).kind == "self"
        and own_power is not None
    ):
        return max(own_power, 0)
    return _NARROW_COUNT


def _tracked_set_fills(node: TypedMirrorNode, unit: AbilityUnit) -> bool:
    """Whether a "this way" set the amount counts is the caster's own cards: the
    unit's other effect that fills it moves cards of yours (Specter of
    Mortality's "exile one or more creature cards from your graveyard", as many
    as the deck's graveyard holds). Volcanic Eruption's "Destroy X target
    Mountains" can take anyone's, yours too, but no scope makes them yours and
    X and the Mountains on the battlefield cap them, so its set reads narrow."""
    return any(
        c.node is not node and c.concept in _MOVES and c.scope == "you"
        for c in unit.effects
    )


#: The concepts that move cards a "this way" set then counts.
_MOVES = frozenset({"change_zone", "destroy", "sacrifice", "discard", "mill"})
#: A size read off an object (its power, its toughness, its mana value).
_OBJECT_SIZES = {"Power": "power", "Toughness": "toughness", "ObjectManaValue": "cmc"}


def _picked_by_caster(qty: object, unit: AbilityUnit, holder: object) -> bool:
    """:func:`crosswalk.picked_by_caster` with the lanes' sacrifice-actor read."""
    return picked_by_caster(qty, unit, holder, sacrifice_actor=sacrifice_actor_scope)


def _own_size(qty: object, unit: AbilityUnit, holder: object) -> str | None:
    """The size (``power`` / ``toughness`` / ``cmc``) a quantity reads off the
    caster's own objects, else ``None``: an object the caster picks
    (:func:`_picked_by_caster` — a cost's, Ichor Explosion's sacrificed creature,
    Corpse Explosion's exiled creature card, Disaster Radius's revealed one; a
    target creature you control; a creature the sweep has you sacrifice), or the
    greatest mana value among the commanders you own, on the battlefield or in
    the command zone (Cloudkill). A deck-free read takes it at ``KILL_SIZE``, the
    size the reads take a Commander board's creatures at — the read's own call;
    a deck reads it at its own biggest (:func:`_deck_magnitude`)."""
    tag = tag_of(qty)
    if tag in _OBJECT_SIZES and _picked_by_caster(qty, unit, holder):
        return _OBJECT_SIZES[tag]
    if tag == "PropertyAggregate" and getattr(qty, "property", None) == "ManaValue":
        filt = getattr(getattr(qty, "source", None), "filter", None)
        if "You" in filter_owners(filt) or filter_controller(filt) == "You":
            return "cmc"
    return None


def _built_around(qty: object) -> bool:
    """Whether a count of yours names a subtype other than a basic land type (CR
    305.6): Gates Ablaze's Gates, Olivia's Wrath's Vampires, Thundercloud
    Shaman's Giants. Only a deck built on that type fills it, which a deck-free
    read can't see, so it reads narrow; Mutilate's Swamps come with the basics.
    The deck read (:func:`_deck_magnitude`) counts the deck's own."""
    subtypes = set(filter_subtypes(getattr(qty, "filter", None)))
    return bool(subtypes - set(BASIC_LAND_TYPE_COLORS))


def _deck_amount(c: ConceptNode, unit: AbilityUnit) -> object | None:
    """The quantity of a sweep amount its deck decides, else ``None``: a count of
    a type only a deck built on it holds (:func:`_built_around`), or a size of
    one of the caster's own objects (:func:`_own_size`). A deck's
    records don't say which is its commander, so Cloudkill's commander's mana
    value stays the deck-free read's."""
    field = _AMOUNT_FIELDS.get(tag_of(c.node) or "")
    if field is None or fixed_value(getattr(c.node, field, None)) is not None:
        return None
    qty = _amount_qty(c.node, field)
    if tag_of(qty) in _FILLED and quantity_scope(qty) == "you" and _built_around(qty):
        return qty
    return (
        qty
        if tag_of(qty) in _OBJECT_SIZES and _picked_by_caster(qty, unit, c.node)
        else None
    )


def _magnitude(c: ConceptNode, u: AbilityUnit, own_power: int | None) -> int | None:
    """A damage sweep's damage or a shrink's toughness loss: its fixed number,
    else :func:`_scale` (``own_power``: the card's printed power)."""
    field = _AMOUNT_FIELDS.get(tag_of(c.node) or "")
    if field is None:
        return None
    v = fixed_value(getattr(c.node, field, None))
    if v is None:
        return _scale(c.node, field, u, own_power)
    return -v if field == "toughness" else v


def _mode(c: ConceptNode) -> str:
    tag = tag_of(c.node)
    if tag in ("ChangeZoneAll", "ChangeZone"):
        dest = change_zone_dirs(c.node)[1]
        return {"Exile": "exile", "Library": "tuck", "Hand": "bounce"}.get(
            dest or "", "other"
        )
    return {
        "DestroyAll": "destroy",
        "Destroy": "destroy",
        "DamageAll": "damage",
        "DealDamage": "damage",
        "PumpAll": "shrink",
        "Pump": "shrink",
        "BounceAll": "bounce",
        "Bounce": "bounce",
        "ChooseAndSacrificeRest": "sacrifice",
    }.get(tag or "", "other")


def _unit_kind(u: AbilityUnit, *, walker: bool) -> str:
    """The base kind (``_common.unit_kind``), with a planeswalker's activation
    as ``loyalty`` and a Saga's lore-counter trigger as ``chapter``."""
    kind = unit_kind(u)
    if kind == "activated" and walker:
        return "loyalty"
    if kind == "trigger" and "counter_added" in (u.trigger_event or "").lower():
        return "chapter"
    return kind


def _x_bounded(filt: object) -> bool:
    """A size bound the caster sets is flexibility, not a restriction."""
    for n in iter_typed_nodes(filt):
        if tag_of(n) in _SIZED:
            v = getattr(n, "value", None)
            if tag_of(v) == "Ref" and tag_of(getattr(v, "qty", None)) in _CHOSEN_QTY:
                return True
    return False


def _gates(u: AbilityUnit) -> tuple[set[int], set[int]]:
    """The ids of the nodes under a CreateDelayedTrigger, and of those under a
    sub-ability's own condition (Martial Coup's "if X is 5 or more") or a coin
    flip's outcome (Boompile's "if you win the flip": a flip a player wins half
    the time, CR 705.1-705.2)."""
    delayed: set[int] = set()
    gated: set[int] = set()
    for n in iter_typed_nodes(u.node):
        if tag_of(n) == "CreateDelayedTrigger":
            delayed.update(id(m) for m in iter_typed_nodes(n) if m is not n)
        if EFFECT_CONCEPTS.get(tag_of(n) or "") == "flip_coin":
            gated.update(id(m) for m in iter_typed_nodes(n) if m is not n)
        effect = getattr(n, "effect", None)
        if n is not u.node and tag_of(getattr(n, "condition", None)) and tag_of(effect):
            gated.update(id(m) for m in iter_typed_nodes(effect))
    return delayed, gated


def _x_floor(u: AbilityUnit) -> int | None:
    """The n in an "if X is n or more" condition on the unit."""
    for n in iter_typed_nodes(u.node):
        if (
            tag_of(n) in ("QuantityCheck", "QuantityComparison")
            and getattr(n, "comparator", None) == "GE"
            and tag_of(getattr(getattr(n, "lhs", None), "qty", None))
            in ("CostXPaid", "Variable")
        ):
            v = fixed_value(getattr(n, "rhs", None))
            if v is not None:
                return v
    return None


def _discount(tree: ConceptTree) -> tuple[str, float, int] | None:
    """The card's own cost reduction (CR 601.2f): ``("board", n, cap)`` for "{n}
    less for each creature on the battlefield", ``("fixed", n, cap)`` for a flat
    one or one behind a board-count condition (Hour of Revelation), and one
    behind any other condition (Avenge) at ``_CONDITIONAL_DISCOUNT`` of its
    ``n``. ``cap`` is the face's generic mana: a generic reduction never touches
    the colored part of the cost (CR 118.7a), so Vanquish the Horde never costs
    less than {W}{W}."""
    for u in tree.units:
        if u.origin != "static":
            continue
        for sdef in iter_static_defs(u.node):
            if modify_cost_mode(sdef) != "Reduce" or affected_tag(sdef, u) != "SelfRef":
                continue
            inner = getattr(getattr(sdef, "mode", None), "inner", None)
            generic = getattr(getattr(inner, "amount", None), "generic", 0)
            count = getattr(inner, "dynamic_count", None)
            board = tag_of(count) == "ObjectCount" and "Creature" in filter_core_types(
                getattr(count, "filter", None)
            )
            cut = float(generic) if isinstance(generic, int) else 0.0
            cond = getattr(sdef, "condition", None)
            if tag_of(cond) is not None and not quantity_threshold(cond, _board_count):
                cut *= _CONDITIONAL_DISCOUNT
            return ("board" if board else "fixed", cut, _face_generic(tree))
    return None


def _board_count(lhs: object) -> bool:
    """Whether a condition's quantity counts the battlefield's permanents,
    creatures among them: a count the read's board meets (Hour of Revelation)."""
    qty = getattr(lhs, "qty", None)
    if tag_of(lhs) != "Ref" or tag_of(qty) != "ObjectCount":
        return False
    cores = filter_core_types(getattr(qty, "filter", None))
    return "Creature" in cores or "Permanent" in cores


def _face_generic(tree: ConceptTree) -> int:
    """The generic mana in ``tree``'s face's printed cost, off phase's own face
    record (its ``mana_cost.generic``)."""
    for face in phase_records_for(tree.oracle_id):
        if face.get("name") == tree.name:
            generic = (face.get("mana_cost") or {}).get("generic")
            return generic if isinstance(generic, int) else 0
    return 0


def _x_in_cards(u: AbilityUnit) -> bool:
    """The unit's own cost discards X cards (Sickening Dreams' additional cost,
    which the crosswalk merges onto its spell unit): an X the caster announces
    (CR 107.3a), paid in cards rather than mana."""
    return any(
        cn.concept == "discard"
        and tag_of(getattr(getattr(cn.node, "count", None), "qty", None))
        in ("Variable", "CostXPaid")
        for cn in u.costs or ()
    )


def _keeps_lands_tapped(u: AbilityUnit) -> bool:
    """The unit also stops your lands untapping (Bontu's Last Reckoning's "Lands
    you control don't untap during your next untap step"): a drawback, since the
    untap step is when you untap them (CR 502.3)."""
    return any(
        static_mode_tag(d) == "CantUntap"
        and "Land" in filter_core_types(static_affected(d, u))
        and filter_controller(static_affected(d, u), u) == "You"
        for d in iter_static_defs(u.node)
    )


def _death_chain(u: AbilityUnit) -> bool:
    """The unit creates a delayed trigger that shrinks the board again whenever
    a creature dies this turn (Massacre Girl, CR 603.7a): each death triggers it
    once more (its ruling: more than one dying at once triggers it that many
    times), so a first death chains through the board."""
    for n in iter_typed_nodes(u.node):
        if tag_of(n) != "CreateDelayedTrigger":
            continue
        trig = getattr(getattr(n, "condition", None), "trigger", None)
        if (
            getattr(trig, "origin", None) == "Battlefield"
            and getattr(trig, "destination", None) == "Graveyard"
            and "Creature" in filter_core_types(getattr(trig, "valid_card", None))
            and any(
                tag_of(m) == "PumpAll"
                for m in iter_typed_nodes(getattr(n, "effect", None))
            )
        ):
            return True
    return False


def _dropped_choice(u: AbilityUnit, filt: object) -> str | None:
    """How a choice the unit makes limits a sweep whose filter never reads it
    (no ``IsChosen…`` predicate, no chosen-number bound): phase keeps Harsh
    Mercy's "each player chooses a creature type" and Sudden Demise's "choose a
    colour" as a ``Choose`` node but drops the clause the choice limits. When
    each player chooses, each keeps their pick (``"spares"``); otherwise the
    sweep reaches only the chosen slice (``"narrow"``). ``None`` when the unit
    chooses nothing or the filter reads the choice (Kindred Dominance's
    ``Not IsChosenCreatureType``, Expel the Interlopers' chosen number)."""
    if not any(tag_of(n) == "Choose" for n in iter_typed_nodes(u.node)):
        return None
    reads_choice = any(
        "Chosen" in (tag_of(n) or "") for n in iter_typed_nodes(filt)
    ) or any("Chosen" in p for p in filter_predicates(filt))
    if reads_choice:
        return None
    scope = tag_of(getattr(u.node, "player_scope", None))
    return "spares" if scope == "All" else "narrow"


def _tree_sweeps(tree: ConceptTree, *, walker: bool) -> list[_Sweep]:
    # Each sweep effect, by node id, with whether it sweeps only because
    # overload made its "target" "each" (CR 702.96a-b).
    sweeps = {
        id(c.node): overload_sweep(tree, u, c) is not None
        for u, c in (
            *mass_removal_effects(tree),
            *mass_bounce_effects(tree),
            *mass_shrink_effects(tree),
        )
    }
    units = [u for u in tree.units if any(id(c.node) in sweeps for c in u.effects)]
    discount = _discount(tree)
    dropped = _CLAUSE_DROPPED.get(tree.name)
    out: list[_Sweep] = []
    for u in units:
        delayed, gated = _gates(u)
        chain = _death_chain(u)
        x_cards = _x_in_cards(u)
        drawback = _keeps_lands_tapped(u)
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(u.node, "cost", None))}
        unparsed = any(tag_of(n) == "Unimplemented" for n in iter_typed_nodes(u.node))
        # Tokens another player creates in the sweep's own unit, a directed
        # recipient (``crosswalk._DIRECTED_PLAYER_TAGS``): March of Souls' "its
        # controller creates" a Spirit for each creature destroyed. Whoever creates
        # a token owns and controls it (CR 111.2), so the wiped boards come back
        # as bodies (The Phasing of Zhalfir, Mogg Infestation).
        refills = any(
            c.concept == "make_token" and recipient_tag(c.node) in _DIRECTED_PLAYER_TAGS
            for c in u.effects
        )
        # Value to the caster riding the sweep: a draw, token or life that is yours
        # (not the wiped players' tokens, not Settle's land), done by you, not by
        # "each player who controls" something (Shatter the Sky's and
        # Depopulate's draws, whose owner wrapper names the players).
        rider = any(
            id(c.node) not in sweeps
            and c.scope == "you"
            and c.concept in ("draw", "make_token", "gain_life")
            and recipient_tag(c.node) not in _DIRECTED_PLAYER_TAGS
            and effect_owner_player_scope(u.node, c.node) is None
            for c in u.effects
        )
        cond = getattr(u.node, "condition", None) or getattr(
            getattr(u.node, "sub_ability", None), "condition", None
        )
        for c in u.effects:
            ov = sweeps.get(id(c.node))
            if ov is None:
                continue
            # An exile the unit returns to the battlefield is a flicker, never a
            # wipe: the shared tree's blink return (``ConceptNode.returns_to``)
            # marks it (Planar Guide).
            if c.returns_to == "battlefield":
                continue
            tag = tag_of(c.node)
            filt = (
                getattr(c.node, "sacrifice_filter", None)
                if tag == "ChooseAndSacrificeRest"
                else effect_filter(c.node)
            )
            cores = set(filter_core_types(filt))
            ctrl = filter_controller(filt, u)
            if (
                not cores & _SWEEP_TYPES
                or ctrl == "You"
                or "You" in filter_owners(filt)
            ):
                continue
            preds = set(filter_predicates(filt)) - {"Another", "InZone", "Owned"}
            if "SameNameAsParentTarget" in preds:
                continue  # a targeted kill's tail (Maelstrom Pulse), not a sweep
            x_bound = _x_bounded(filt)
            if x_bound:
                preds -= _SIZED
            choice = _dropped_choice(u, filt) or dropped
            if choice == "narrow":
                preds.add(_CHOSEN_SLICE)
            if choice == "pile":
                ctrl = "TargetPlayer"
            non = set(filter_non_types(filt))
            types = (cores | (_SWEPT if "Permanent" in cores else set())) & _SWEPT
            mag = _magnitude(c, u, tree.power)
            if chain and tag == "PumpAll" and id(c.node) not in delayed:
                mag = _SCALING
            # An activation that taps or sacrifices nothing repeats for mana:
            # Pestilence's 1 damage is as much as you pay for.
            if (
                u.kind == "Activated"
                and mag is not None
                and not walker
                and not leaves & {"Tap", "Sacrifice", "Loyalty"}
            ):
                mag = _SCALING
            out.append(
                _Sweep(
                    mode=_mode(c),
                    types=frozenset(types - non),
                    ctrl=ctrl,
                    preds=frozenset(preds),
                    spares=bool(non - _CORE_TYPES)
                    or "Another" in filter_predicates(filt)
                    or any(tag_of(n) == "Not" for n in iter_typed_nodes(filt))
                    # each player keeps what was chosen and sacrifices the rest
                    or tag == "ChooseAndSacrificeRest"
                    or choice in ("spares", "pile"),
                    mag=mag,
                    kind=_unit_kind(u, walker=walker),
                    gated=id(c.node) in gated or tag_of(cond) is not None or unparsed,
                    delayed=id(c.node) in delayed,
                    x_floor=_x_floor(u),
                    x_bound=x_bound,
                    act_mana=activation_mana(u),
                    self_sac="Sacrifice" in leaves,
                    event=u.trigger_event,
                    overload=ov,
                    modal=bool(tree.card_modal_mode_descriptions) or len(units) > 1,
                    rider=rider,
                    discount=discount,
                    face_cmc=tree.cmc if tree.has_printed_cost else None,
                    mode_cost=_mode_cost(tree, u),
                    x_cards=x_cards,
                    drawback=drawback,
                    refills=refills,
                    amount=_deck_amount(c, u),
                )
            )
    return out


def _mode_cost(tree: ConceptTree, u: AbilityUnit) -> int:
    """The additional cost a spree or tiered spell asks for the mode ``u`` is
    (CR 702.172a / 702.183a): Final Showdown's "Destroy all creatures" is
    {3}{W}{W} on top of its {W}. 0 for any other unit."""
    costs = tree.card_modal_mode_costs
    if u.origin == "ability" and 0 <= u.index < len(costs):
        return costs[u.index]
    return 0


def _static_sweep(shrinks: Sequence[tuple[AbilityUnit, object]]) -> _Sweep:
    """A static population shrink (``static_population_shrinks``): its largest
    toughness reduction, and whose creatures it shrinks."""
    mag, ctrl = 0, None
    for u, sdef in shrinks:
        for mod in getattr(sdef, "modifications", None) or ():
            if tag_of(mod) == "AddToughness":
                v = getattr(mod, "value", None)
                size = -v if isinstance(v, int) and v < 0 else _SCALING
                if size > mag:
                    mag = size
                    ctrl = filter_controller(static_affected(sdef, u), u)
    return _Sweep(
        mode="shrink",
        types=frozenset({"Creature"}),
        ctrl=ctrl,
        preds=frozenset(),
        spares=False,
        mag=mag or _SCALING,
        kind="static",
        gated=False,
        delayed=False,
        x_floor=None,
        x_bound=False,
        act_mana=None,
        self_sac=False,
        event=None,
        overload=False,
        modal=False,
        rider=False,
        discount=None,
        face_cmc=None,
        mode_cost=0,
    )


#: oracle_id -> its sweeps, for the deck read, which asks again for a card the
#: deck-free score already read. Bounded: the oldest entry goes first.
_SWEEPS_MEMO: dict[str, list[_Sweep]] = derived_memo()
_SWEEPS_MEMO_MAX = 4096


def _sweeps(card: dict) -> list[_Sweep]:
    oid = card.get("oracle_id") or ""
    hit = _SWEEPS_MEMO.get(oid) if oid else None
    if hit is not None:
        return hit
    out = _card_sweeps(card)
    if oid and (out or signal_trees_for(card, bulk=card)):
        while len(_SWEEPS_MEMO) >= _SWEEPS_MEMO_MAX:
            del _SWEEPS_MEMO[next(iter(_SWEEPS_MEMO))]
        _SWEEPS_MEMO[oid] = out
    return out


def _card_sweeps(card: dict) -> list[_Sweep]:
    trees = list(signal_trees_for(card, bulk=card))
    walker = "Planeswalker" in (card.get("type_line") or "")
    # A face after the first with no printed mana cost is a transforming card's
    # back face (only its mana value is the front's, CR 712.8e): the read's own
    # decision is that a face reached by transforming is no wipe on demand
    # (Jin-Gitaxias's Great Synthesis behind seven cards in hand, Avacyn, the
    # Purifier, Elesh Norn's Argent Etchings). Dropping every costless
    # later face is intended; a modal or split face prints its own cost and
    # stays. A back face cast transformed for an alternative cost (CR 712.11a;
    # disturb, 702.146a) is dropped too; no such face sweeps.
    out = [
        s
        for i, tree in enumerate(trees)
        if i == 0 or tree.has_printed_cost
        for s in _tree_sweeps(tree, walker=walker)
    ]
    if not out:
        shrinks = [s for tree in trees for s in static_population_shrinks(tree)]
        if shrinks:
            out.append(_static_sweep(shrinks))
    return out


def _lethal(s: _Sweep) -> bool:
    return s.mode in _KILLS or (
        s.mode in ("damage", "shrink") and (s.mag or 0) >= KILL_SIZE
    )


def _overload_cost(card: dict) -> int | None:
    """The overload cost's mana value, X as 0 (CR 202.3e) — the cost the sweep is
    cast for."""
    for tree in signal_trees_for(card, bulk=card):
        for alt in tree.card_alt_costs:
            if alt.kind == "overload":
                return mana_value_of_cost(alt.cost)
    return None


def _pitch_cards(card: dict) -> int | None:
    """The fewest cards an alternative cost with no mana in it asks (CR 118.9):
    Force of Despair's black card exiled from hand, Sunscour's two white cards,
    Pulverize's two Mountains sacrificed; a life payment asks none. ``None``
    when the card has no such cost. ``casting_options`` is a phase record field
    the concept tree does not carry (as ``_common.free_cast`` reads it)."""
    counts = []
    for face in phase_records_for(card.get("oracle_id") or ""):
        for opt in face.get("casting_options") or ():
            if opt.get("kind") != "AlternativeCost" or "Mana" in json.dumps(
                opt.get("cost")
            ):
                continue
            n = 0
            for leaf in _cost_leaves(opt.get("cost")):
                if leaf.get("type") in ("Exile", "Discard", "Sacrifice"):
                    count = leaf.get("count", 1)
                    n += count if isinstance(count, int) else 1
            counts.append(n)
    return min(counts) if counts else None


def _cost_leaves(cost: object) -> list[dict]:
    """A raw phase cost's leaves: a ``Composite``'s parts, else itself."""
    if not isinstance(cost, dict):
        return []
    if cost.get("type") == "Composite":
        return [leaf for part in cost.get("costs") or () for leaf in _cost_leaves(part)]
    return [cost]


def _cost(card: dict, best: _Sweep, *, x: bool) -> float:
    """The mana the sweep costs as cast: the card's cast cost
    (``_common.cast_cost``; a card with no mana cost keeps that fixed cost); a
    split half's own cost; the overload cost; a spree or tiered mode's own cost;
    the card's own discount; a pitch cost's cards (:func:`_pitch_cards`, each
    ``_CARD_MANA``) when fewer; twice the cost when it keeps your lands tapped;
    X at its floor or ``_BOARD_X`` (a card each for an X paid in cards) — for a
    spell, and for a permanent's enters trigger, whose X is the one paid to cast
    it (CR 107.3m: The Meathook Massacre, Spiteful Banditry); plus an
    activation's mana."""
    cost = cast_cost(card)
    if unpriced(card):
        return cost
    backs = faces(card)[1:]
    if backs and best.face_cmc is not None:
        cost = min(cost, float(best.face_cmc))
    if "Undaunted" in (card.get("keywords") or ()):
        cost -= _UNDAUNTED
    if best.overload:
        cost = float(_overload_cost(card) or cost)
    cost += best.mode_cost
    if best.discount is not None:
        kind, generic, cap = best.discount
        cut = generic * _BOARD_CREATURES if kind == "board" else generic
        cost = max(1.0, cost - min(cut, cap))
    pitch = _pitch_cards(card)
    if pitch is not None:
        cost = min(cost, pitch * _CARD_MANA)
    if x and best.kind in ("spell", "etb"):
        cost += (best.x_floor or _BOARD_X) * (_CARD_MANA if best.x_cards else 1)
    if best.drawback:
        # Your lands stay tapped through your next untap step, even ones that
        # weren't tapped (its ruling): the next turn's mana, read as the
        # sweep's own cost again — the read's own call.
        cost *= 2
    if best.kind == "activated" and best.act_mana is not None:
        # Activating an ability pays its costs (CR 602.2; the activation cost is
        # everything before the colon, 602.1a), a creature's too: Jaya Ballard,
        # Task Mage's sweep is {5}{R}{R} on top of the card.
        cost += best.act_mana + (_BOARD_X if best.x_bound else 0)
    return cost


def _best(sweeps: Sequence[_Sweep]) -> _Sweep:
    """The sweep the card is read by: one it is cast or activated for first,
    then the deadliest and broadest."""
    return max(
        sweeps,
        key=lambda s: (
            s.kind in _PRIMARY and not s.delayed,
            _lethal(s),
            "Creature" in s.types,
            len(s.types),
            s.mode in ("exile", "tuck"),
            not s.preds,
        ),
    )


def features(card: dict, deck: Sequence[dict] | None = None) -> dict[str, float] | None:
    """The board-wipe read's features for ``card``, or ``None`` when it has no
    sweep of its own. Given ``deck`` (its cards' records), an amount the deck
    decides (:func:`_deck_amount`) is read off it (:func:`_deck_magnitude`), and
    a damage or shrink of that size kills in proportion to ``KILL_SIZE`` (its
    ``lethal``, ``small`` and ``clean`` shares), so the read rises smoothly with
    what the deck holds — the read's own call."""
    sweeps = _sweeps(card)
    if not sweeps:
        return None
    if deck is not None:
        sweeps = _in_deck(sweeps, deck)
    best = _best(sweeps)
    x = "{X}" in front_mana_cost(card) or best.x_cards
    cost = _cost(card, best, x=x)
    sized = best.mode in ("damage", "shrink")
    if deck is not None and best.amount is not None and sized:
        kill = min(max(best.mag or 0.0, 0.0) / KILL_SIZE, 1.0)
    else:
        kill = float(_lethal(best))
    creatures = "Creature" in best.types
    # A sweep on demand: one the card is cast or activated for, not one an
    # event elsewhere fires (Sarkhan's Unsealing's power-7 cast trigger).
    clean = kill * (
        best.kind in _PRIMARY
        and creatures
        and not best.preds & (_NARROW | _SIZED | _SPARES)
        and not best.spares
        and not best.gated
        and not best.delayed
        and not best.refills
    )
    return {
        "creatures": float(creatures),
        "breadth": float(len(best.types)),
        "lethal": kill,
        "bounce": float(best.mode == "bounce"),
        "small": (1.0 - kill) if sized else 0.0,
        "one_sided": float(best.ctrl in ("Opponent", "TargetPlayer")),
        "spares": float(best.spares or bool(best.preds & _SPARES)),
        "narrow": float(bool(best.preds & _NARROW)),
        "flexible": float(best.modal or best.overload or x or best.x_bound),
        "cost": min(max(cost, 1.0), 9.0),
        "cheap": (1.0 - clean) * (cost <= _CHEAP),
        "clean": clean,
        "cheap_clean": clean * (cost <= _REFERENCE_COST),
        "repeat": float(
            any(
                (s.kind == "activated" and not s.self_sac)
                or (s.kind == "trigger" and s.event != "cycled")
                for s in sweeps
            )
        ),
        "rider": float(any(s.rider for s in sweeps)),
    }


# ── An amount the deck decides ─────────────────────────────────────────────────
#
# The card read is deck-free, so a count of a type only a deck built on it holds
# reads narrow (:func:`_built_around`) and the size of the caster's own creature
# reads at ``KILL_SIZE`` (:func:`_own_size`). Given the deck, both are read off
# it, and the sweep is lethal in proportion (:func:`features`): Olivia's Wrath
# counts the Vampires Blood Rites has out.

#: id(deck) -> (deck, its cards with their facts): a tune scores one deck's
#: cards thousands of times. Bounded; the deck is held, so its id can't be
#: reused while the entry lives.
_BOARDS: dict[int, tuple[Sequence[dict], tuple[tuple[dict, ObjectFacts], ...]]] = {}
_BOARDS_MAX = 4


def _board(deck: Sequence[dict]) -> tuple[tuple[dict, ObjectFacts], ...]:
    """``deck``'s cards (one record per copy), each with its facts on the
    battlefield (``_card_ir.trees.object_facts``)."""
    hit = _BOARDS.get(id(deck))
    if hit is not None and hit[0] is deck:
        return hit[1]
    board = tuple((rec, object_facts(rec, zone="battlefield")) for rec in deck)
    while len(_BOARDS) >= _BOARDS_MAX:
        del _BOARDS[next(iter(_BOARDS))]
    _BOARDS[id(deck)] = (deck, board)
    return board


def _size(rec: dict, facts: ObjectFacts, size: str) -> int | None:
    """A deck card's printed size: its mana value (``ObjectFacts.mana_value``),
    or its front face's fixed power or toughness (``trees.fixed_stat``)."""
    if size == "cmc":
        return facts.mana_value
    face = rec if size in rec else (rec.get("card_faces") or [{}])[0]
    return fixed_stat(face.get(size))


def _deck_magnitude(s: _Sweep, deck: Sequence[dict]) -> float | None:
    """``s``'s amount as its deck decides it (:func:`_deck_amount`). The size of
    the caster's own object is the deck's biggest creature's. A count of yours
    is what the deck has out: its share of the deck's cards over a board of
    ``_BOARD_CREATURES`` permanents of your own — the read's own call, as many
    as the creatures it casts a wipe into. Blood Rites' 36 Vampires of 100 read
    2.88; fifteen Gates, 1.2."""
    board = _board(deck)
    # ``_deck_amount`` keeps a size only when the caster's own object decides it.
    size = _OBJECT_SIZES.get(tag_of(s.amount) or "")
    if size is not None:
        values = [
            v
            for rec, facts in board
            if facts.has_type("Creature") and (v := _size(rec, facts, size)) is not None
        ]
        # The size stays signed (Loot, the Anomaly's -2: "All other rules and
        # effects that check his power use the real value"), but an amount it
        # becomes is never below 0: "If a calculation that would determine the
        # result of an effect yields a negative number, zero is used instead"
        # (CR 107.1b) — Ichor Explosion sacrificing a -2/4 gives -0/-0.
        biggest = max(values, default=s.mag)
        return None if biggest is None else max(biggest, 0)
    filt = getattr(s.amount, "filter", None)
    held = sum(filter_admits(filt, facts) is True for _rec, facts in board)
    return round(_BOARD_CREATURES * held / len(board), 3) if board else 0.0


def _in_deck(sweeps: Sequence[_Sweep], deck: Sequence[dict]) -> list[_Sweep]:
    """``sweeps`` with each amount its deck decides read off ``deck``."""
    return [
        replace(s, mag=_deck_magnitude(s, deck)) if s.amount is not None else s
        for s in sweeps
    ]


#: oracle_id -> whether a sweep amount of the card's is its deck's to decide.
_DECK_DEPENDENT = JOB_READS.memo("wipe_deck_amount")


def _deck_dependent(card: dict) -> bool:
    """Whether ``card``'s features change with its deck: a sweep amount the deck
    decides (:func:`_deck_amount`: Olivia's Wrath's Vampires, Ichor Explosion's
    sacrificed creature). Memoized per oracle_id, and persisted."""
    oid = card.get("oracle_id")
    if oid and (hit := _DECK_DEPENDENT.get(oid)) is not MISSING:
        return bool(hit)
    out = any(s.amount is not None for s in _sweeps(card))
    if oid and (out or signal_trees_for(card, bulk=card)):
        _DECK_DEPENDENT.put(oid, out)
    return out


def deck_features(card: dict, deck: Sequence[dict]) -> dict[str, float] | None:
    """``card``'s features in ``deck`` when its deck decides one of its sweep
    amounts (:func:`_deck_amount`), else ``None``: the deck-free read holds
    (``JobRead.in_deck``)."""
    return features(card, deck) if _deck_dependent(card) else None


#: Board wipe's weights, log10 play-rate per unit (ridge fit, 2026-10-19,
#: standardised weight / feature sd, rounded). ``cheap`` and ``cheap_clean``
#: keep their fitted weights over features redrawn 2026-10-24 around the
#: reference wipe (``_REFERENCE_COST``). With the cost and sweep fixes of the
#: same day (``job_reads.py``): Spearman against play-rate 0.501 over 800 cards
#: (0.487 over 807), the guides' wipe adds at the 84th percentile of their
#: identity's wipes (79th), 8 of 19 in its top decile (8); with the misread
#: fixes of the module docstring, 0.510, the 84th percentile, 9 of 19; with the
#: last five (an X the card defines to the tokens for the wiped players), 0.526,
#: the 86th percentile, 9 of 19, the cut side unchanged (9 of the bottom two).
WEIGHTS: dict[str, float] = {
    "creatures": 0.21,  # sweeps creatures
    "breadth": -0.02,  # per permanent type swept
    "lethal": 0.07,  # destroys, exiles, tucks, sacrifices, or deals/shrinks 4+
    "bounce": 0.36,  # returns to hand (Evacuation, Cyclonic Rift)
    "small": -0.17,  # damage or a shrink under 4 (Pyroclasm)
    "one_sided": 0.25,  # only opponents' (or a target player's) permanents
    "spares": 0.23,  # leaves a class standing (nontoken, a chosen type, one each)
    "narrow": -0.17,  # hits only a combat / colour / keyword slice
    "flexible": 0.20,  # modal, overload, X, or a bound the caster sets
    "cost": -0.02,  # per mana as cast
    "cheap": -0.09,  # an unclean sweep at 3 or less (most are small)
    "clean": 0.14,  # every creature dies, nothing lets one through
    "cheap_clean": 0.44,  # a clean sweep at 4 or less (Wrath of God, Toxic Deluge)
    "repeat": -0.12,  # sweeps again (Pestilence)
    "rider": 0.06,  # a draw, token or life for the caster
}
