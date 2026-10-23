"""Card draw — how well a card nets you cards (the ``card_draw`` role,
``roles.role_of``).

Each draw a card carries is read off its own ability unit: how many cards it
gives you, less what the same unit takes back. That means a discard (a loot or a
rummage), the cards a Brainstorm puts back, a hand returned to the library
(Mindmoil), and a discard paid as a cost. Connive draws, then discards
(CR 701.50a), and cycling is "[Cost], Discard this card: Draw a card"
(CR 702.29a). Both net nothing, so they are card filtering, not card draw. A
card whose draws net it no card scores ``None``: Faithless Looting, Frantic
Search, Ledger Shredder, any cycler.

The read then classes how the draw repeats. A one-shot is a spell, an enters or
dies trigger, or a "sacrifice this" ability; it is read by its cards per mana.
An engine is a trigger, an activation or a draw replacement. A trigger is read
by what it needs to keep firing: each turn, an opponent's cast or draw (three
opponents, so three times as often), something the deck controls (casting,
creatures dying or entering), or combat. Its ``flow`` is the card advantage per
firing times the expected firings per turn cycle in a four-player pod. That
rate is scaled down for:

- a narrow watched object (a subtype, a colour, one card type, a property);
- an engine watching only itself;
- an opponent's event that counts only on your turn;
- a Curse that watches one opponent;
- a payment asked at each firing.

A symmetric draw's advantage is your cards less each opponent's, so Howling
Mine's flow is 0. It still nets you a card, so it scores.

Fitted on the 1,824 commander-legal cards whose main job is draw. A creature
qualifies only when its engine watches more than itself or it draws two or more
on entering; any other card, when its draw is not a one-card rider on another
job (a removal spell's cantrip, a mana rock's "sacrifice: draw"). Every card
that nets a card is scored, not only the fitted ones.

Results:

- Cross-validated Spearman 0.33 against play-rate (0.35 with a ``symmetric``
  feature, dropped: its +0.29 fit only the group-hug decks' Howling Mine-likes,
  and put Howling Mine above Phyrexian Arena).
- The precon guides' draw adds sit at the 75th percentile of their color
  identity's draw by this read (89th by play-rate).
- The bottom two draw-role members of each precon by this read hold 15 of the
  guides' cuts (17 by play-rate, 16 by mana value). Counting only the cards
  whose main job is draw, the bottom two hold 15 of 46 picks against
  play-rate's 11 and mana value's 9: the role's members with another main job
  (Mind Stone, Solemn Simulacrum) are what the guides keep.

Too weak to order candidates; it GATES them (``JobRead.orders``).
The rest is popularity rather than misreads:

- legendary creatures played as commanders, not in the 99;
- card age;
- draw spells that scale with the board (Return of the Wildspeaker), played
  above this read;
- costs and drawbacks phase drops (Silverquill Silencer's chosen name,
  Moderation's one-spell lock, Shared Discovery's tapped creatures).

The deck context (``draw_fuel`` / ``deck_fit``, ``JobRead.fit``): an engine
runs only on the fuel its deck supplies, so in a deck the read is scaled by the
share of the engine the deck can fuel. That share is the deck's share of
nonland cards feeding the engine against the share at which it runs at full
rate, capped at 1. Skullclamp's "equipped creature dies" wants X/1 creatures
and creature-token makers (the ``token_maker`` lane), full at a quarter of the
deck. Archmage Emeritus wants instants and sorceries; a creature-death,
creature-cast, enters or combat engine wants creatures; an enchantress wants
enchantments. Those are full at a third. Measured on the 25 precons
(2026-10-19):

- Skullclamp's fit is 1.0 in the token and aristocrat decks (BloodRites,
  SquirreledAway, MarduSurge). It is 0.33 in VelociRampTor (big dinosaurs) and
  0.39 in AbzanArmor and EndlessPunishment.
- Archmage Emeritus's fit is 0.29 in EnduringEnchantments and 1.0 in QuickDraw.

With the tuner gating an upgrade at fit 0.5 and ordering by the read in the
deck, Skullclamp went from 11 adds to 8, with no guide match lost (230 swaps,
109 cut matches, 30 add matches before and after). AbzanArmor's add became
Sylvan Library, and GraveyardOverdrive's and FaeDominion's became Deadly
Dispute (a FaeDominion guide add, as Skullclamp was).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    NO_COST,
    activation_mana,
    cast_cost,
    faces,
    front_mana_cost,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.lanes.card_advantage import _draw_engine_scope
from mtg_utils._analysis.roles import role_of
from mtg_utils._card_ir.crosswalk import (
    ENTERS_EVENTS,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    controller_paid_cost_leaves,
    discard_recipient_scope,
    effect_player_reach,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    has_fixed_count,
    is_opponent_cast_trigger_def,
    is_self_discard_cost,
    iter_cost_leaves,
    recipient_tag,
    tag_of,
    trigger_caster_scope,
    trigger_scope,
    trigger_subject_scope,
    trigger_turn_constraint,
    triggering_player_side,
    watches_itself,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.theme_presets import _signal_keys_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptNode

#: A scaling count the read can't size (X, a tracked set) reads as three cards.
_SCALING = 3
#: What other scaling counts are worth, by what they count (the count's ``qty``).
#: Copies of the card itself in a graveyard (Accumulated Knowledge) count as one.
_QTY_ESTIMATE = {"CardsDiscardedThisTurn": 1, "HandSize": 4, "CountersOn": 2}
#: Counts of your own objects: the draw grows with your board.
_BOARD_QTY = frozenset({"ObjectCount", "PropertyAggregate"})
#: Watched-object properties a deck rarely has many of.
_NARROW_PREDS = frozenset(
    {
        "Counters",
        "WithKeyword",
        "Cmc",
        "HasSupertype",
        "Targets",
        "FaceDown",
        "Historic",
        "EquippedBy",
        "EnchantedBy",
        "ManaValueParity",
        "HasAdventure",
        "Attacking",
        "Modified",
        "WasKicked",
        "HasAttachment",
        "ColorCount",
        "InZone",
    }
)
#: Object tags naming the permanent an Aura or Equipment is attached to.
_ATTACHED_TAGS = frozenset({"AttachedTo", "EquippedBy", "EnchantedBy"})
#: Expected firings per turn cycle in a four-player pod (you and three
#: opponents), by what the trigger needs.
_RATE = {
    "turn": 1.0,
    "opp_draw": 3.0,
    "opp_cast": 3.0,
    "any_cast": 4.0,
    "you_cast": 1.5,
    "creature_cast": 1.0,
    "deaths": 1.0,
    "equipped_dies": 1.0,
    "enters": 1.0,
    "combat": 1.0,
    "self_draw": 1.0,
    "other": 0.3,
}
_SELF_FUEL = frozenset(
    {"you_cast", "creature_cast", "deaths", "enters", "equipped_dies", "self_draw"}
)
_OPP_FUEL = frozenset({"opp_cast", "any_cast"})
_ENGINE_KINDS = frozenset({"trigger", "activated", "replacement", "loyalty"})
_ONE_SHOT = frozenset({"spell", "etb", "sac", "ltb"})
_COMBAT_EVENTS = frozenset(
    {
        "attacks",
        "deals_damage",
        "becomes_blocked",
        "blocks",
        "attacksorblocks",
        "attackerunblocked",
        "youattackunblocked",
    }
)
#: Keywords that cut a spell's cost by what the deck has (delve, CR 702.66a:
#: exile graveyard cards for generic mana; affinity, improvise, convoke).
_COST_REDUCERS = frozenset({"Delve", "Affinity", "Improvise", "Convoke"})
#: The template roles a draw card can also fill.
_OTHER_ROLES = frozenset({"ramp", "interaction", "board_wipe"})


@dataclass
class _Source:
    """One ability unit that draws: what it nets you, how it repeats, at what cost."""

    # spell | etb | sac | ltb | trigger | activated | replacement | loyalty | cycling
    kind: str
    got: int  # cards you draw
    net: int  # got, less what the unit takes back
    each: bool  # every player draws (a symmetric draw)
    wheel: bool  # discards a whole hand
    scaling: bool  # the count scales (X, a count)
    board: bool  # the count grows with your board
    fuel: str | None  # what a trigger needs to fire again (``_RATE``'s keys)
    narrow: float  # 1.0 for a broad watched object, down to 0.4
    self_watch: bool  # only this object (or the one it's attached to) fires it
    opt_mana: bool  # each firing asks a payment
    act_mana: int | None  # an activated ability's mana
    tap: bool  # the activation taps
    treasure: int  # Treasures the unit makes (mana back)
    watched: frozenset[str]  # the card types a trigger's watched object names
    fodder: bool  # it sacrifices another permanent per draw
    rate: float = 0.0


def _count(c: ConceptNode, field: str = "count") -> int:
    if amount_is_scaling(c.node, field):
        t, named, _board = _scaling_qty(c, field)
        return 1 if named else _QTY_ESTIMATE.get(t or "", _SCALING)
    if has_fixed_count(c.node, field):
        return amount_factor(c.node, field)
    return 1


def _scaling_qty(c: ConceptNode, field: str = "count") -> tuple[str | None, bool, bool]:
    """What a scaling count counts: its ``qty`` tag, whether it counts copies of a
    named card, whether it counts your own board."""
    cnt = getattr(c.node, field, None)
    inner = getattr(cnt, "inner", None) if tag_of(cnt) == "Offset" else cnt
    qty = getattr(inner, "qty", None)
    t = tag_of(qty)
    filt = getattr(qty, "filter", None) or getattr(
        getattr(qty, "source", None), "filter", None
    )
    named = filt is not None and "Named" in filter_predicates(filt)
    board = t in _BOARD_QTY and not named and filter_controller(filt) == "You"
    return t, named, board


def _drawer(unit: AbilityUnit, c: ConceptNode) -> str:
    """Who draws: ``you``, ``each`` player, or an ``opp`` (a gift)."""
    rt = recipient_tag(c.node)
    if rt == "TriggeringPlayer" and unit.origin == "trigger":
        side = triggering_player_side(unit)  # "that player": who the trigger watched
        if side == "opponents":
            return "opp"
        if side is None:
            return "each"
    if rt == "ParentTargetController":
        return "opp"  # the countered or removed object's controller (Arcane Denial)
    reach = effect_player_reach(unit.node, c.node)
    if reach in ("opponents", "per_opponent"):
        return "opp"
    scope = _draw_engine_scope(unit, c)
    if scope == "opponents":
        return "opp"
    return "each" if scope == "each" or reach == "each" else "you"


def _sacs_self(unit: AbilityUnit) -> bool:
    return any(
        c.concept == "sacrifice"
        and tag_of(getattr(c.node, "target", None)) == "SelfRef"
        for c in unit.effects
    )


def _kind(unit: AbilityUnit) -> str:
    """The base kind (``_common.unit_kind``), refined by what makes the draw
    repeat: cycling, a loyalty or a "sacrifice this" ability; a draw
    replacement; an enters or dies trigger only when it watches the card itself
    (once), else a trigger."""
    if unit.origin == "keyword":
        return "cycling"
    kind = unit_kind(unit)
    leaves = list(iter_cost_leaves(getattr(unit.node, "cost", None)))
    if kind == "activated":
        if any(
            tag_of(leaf) == "Discard" and getattr(leaf, "self_ref", False)
            for leaf in leaves
        ):
            return "cycling"
        if any(
            tag_of(leaf) in ("Loyalty", "RemoveLoyalty", "AddLoyalty")
            for leaf in leaves
        ):
            return "loyalty"
        if _sacs_self(unit) or any(
            tag_of(leaf) == "Sacrifice"
            and tag_of(getattr(leaf, "target", None)) == "SelfRef"
            for leaf in leaves
        ):
            return "sac"  # "{cost}, Sacrifice this: draw" happens once
        return "activated"
    if unit.origin == "ability":
        return "spell"
    if unit.origin == "replacement":
        return (
            "replacement" if getattr(unit.node, "event", None) == "Draw" else "trigger"
        )
    if unit.origin == "trigger":
        if kind == "etb" and watches_itself(unit.node):
            return "etb"
        if _sacs_self(unit):
            return "sac"
        if unit.trigger_event in ("dies", "leaves") and watches_itself(unit.node):
            return "ltb"  # "when this dies, draw" happens once
        return "trigger"
    return unit.origin or "other"


def _fuel(unit: AbilityUnit) -> str:
    """What a draw trigger needs to fire again."""
    ev = unit.trigger_event or ""
    node = unit.node
    if unit.origin == "replacement":
        return "other"
    if ev in {"phase", "landplayed"}:
        return "turn"
    if ev == "drawn":
        if tag_of(getattr(node, "valid_target", None)) == "AttachedTo":
            return "opp_draw"  # a Curse on one opponent (rated a third below)
        return (
            "opp_draw" if trigger_scope(node) in ("opponents", "each") else "self_draw"
        )
    if ev in ("cast_spell", "spellcastorcopy"):
        if is_opponent_cast_trigger_def(node):
            return "opp_cast"
        types = set(filter_core_types(getattr(node, "valid_card", None)))
        if trigger_caster_scope(node) is None and not types:
            return "any_cast"
        return "creature_cast" if types == {"Creature"} else "you_cast"
    if ev in ("dies", "sacrificed", "leaves", "exploited"):
        if tag_of(getattr(node, "valid_card", None)) in _ATTACHED_TAGS:
            return "equipped_dies"
        return "deaths"
    if ev in ENTERS_EVENTS or ev == "changes_zone":
        return "enters"
    if ev in _COMBAT_EVENTS:
        return "combat"
    return "other"


def _narrow(unit: AbilityUnit) -> float:
    """How broad the watched object is: 1.0; 0.6 for one noncreature, nonland
    card type or a rare property; 0.4 for a subtype or a colour."""
    f = 1.0
    for field in ("valid_card", "valid_source"):
        vc = getattr(unit.node, field, None)
        if vc is None:
            continue
        preds = set(filter_predicates(vc))
        if filter_subtypes(vc) or "HasColor" in preds:
            f = min(f, 0.4)
        if preds & _NARROW_PREDS:
            f = min(f, 0.6)
        core = set(filter_core_types(vc)) - {"Card", "Permanent", "Spell"}
        if (
            core
            and not core & {"Creature", "Land"}
            and not core >= {"Instant", "Sorcery"}
        ):
            f = min(f, 0.6)
    return f


def _watched_types(unit: AbilityUnit) -> frozenset[str]:
    """The card types a trigger's watched object names: Creature for a creature
    dying or entering (and for the creature an Equipment is attached to),
    Instant and Sorcery for Archmage Emeritus's spells, Enchantment for an
    enchantress."""
    out: set[str] = set()
    for field in ("valid_card", "valid_source"):
        vc = getattr(unit.node, field, None)
        if vc is None:
            continue
        if tag_of(vc) in _ATTACHED_TAGS:
            out.add("Creature")
        out |= set(filter_core_types(vc)) - {"Card", "Permanent", "Spell"}
    return frozenset(out)


def _rate(unit: AbilityUnit, src: _Source) -> float:
    """Expected firings per turn cycle."""
    if src.kind == "replacement":
        return 1.0  # replaces each of your draws
    if src.kind in ("activated", "loyalty"):
        return 1.0 if (src.act_mana or 0) <= 2 else 0.6
    if src.kind != "trigger" or src.fuel is None:
        return 0.0
    r = _RATE.get(src.fuel, 0.3) * src.narrow
    constraint = trigger_turn_constraint(unit.node)
    if src.fuel == "deaths" and trigger_subject_scope(unit.node) == "any":
        r *= 2  # any player's creature
    if src.fuel == "turn" and constraint is None and not src.each:
        r *= 2  # "each upkeep, you draw"
    if unit.trigger_event == "entersorattacks":
        r *= 1.5
    if src.self_watch and src.fuel != "equipped_dies":
        r *= 0.5  # one object fires it (an Equipment moves, so it isn't)
    if src.fuel in ("opp_cast", "any_cast", "opp_draw") and (
        constraint == "OnlyDuringYourTurn"
    ):
        r *= 0.3  # opponents rarely act on your turn
    if src.fuel in ("opp_cast", "opp_draw") and (
        tag_of(getattr(unit.node, "valid_target", None)) == "AttachedTo"
    ):
        r /= 3  # one opponent, not three
    if src.opt_mana:
        r *= 0.5
    return r


def _sources(card: dict) -> list[_Source]:
    out: list[_Source] = []
    aura = "Aura" in (card.get("type_line") or "")
    for tree in trees_for(card, bulk=card):
        for unit in tree.units:
            draws = [c for c in unit.effects if c.concept == "draw"]
            if not draws and not unit.has_effect("connive"):
                continue
            got, each, scaling, board = 0, False, False, False
            for c in draws:
                who = _drawer(unit, c)
                if who == "opp":
                    continue
                each |= who == "each"
                got += _count(c)
                scaling |= amount_is_scaling(c.node, "count")
                board |= amount_is_scaling(c.node, "count") and _scaling_qty(c)[2]
            lost, wheel = 0, False
            for c in unit.effects:
                if c.concept == "discard" and discard_recipient_scope(c.node) in (
                    None,
                    "you",
                    "each",
                ):
                    if amount_is_scaling(c.node, "count") and not has_fixed_count(
                        c.node, "count"
                    ):
                        wheel, lost = True, lost + _SCALING
                    else:
                        lost += _count(c)
                elif c.concept == "put_library_position" and c.scope == "you":
                    lost += _count(c)  # Brainstorm's two back
                elif c.concept == "change_zone" and change_zone_dirs(c.node) == (
                    "Hand",
                    "Library",
                ):
                    lost += _SCALING  # Mindmoil: your hand goes back first
                elif c.concept == "connive":  # draw, then discard (CR 701.50a)
                    got, lost = got + _count(c), lost + _count(c)
            paid = controller_paid_cost_leaves(unit)
            lost += sum(1 for pc in paid if is_self_discard_cost(pc.leaf))
            kind = _kind(unit)
            fuel = _fuel(unit) if kind == "trigger" else None
            watched = [
                tag_of(getattr(unit.node, f, None))
                for f in ("valid_source", "valid_card")
            ]
            if (
                fuel in ("deaths", "equipped_dies")
                and aura
                and (watched[1] in _ATTACHED_TAGS)
            ):
                kind, fuel = "ltb", None  # an Aura's "enchanted creature dies": once
            src = _Source(
                watched=_watched_types(unit) if kind == "trigger" else frozenset(),
                kind=kind,
                got=got,
                net=got - lost,
                each=each,
                wheel=wheel,
                scaling=scaling,
                board=board,
                fuel=fuel,
                narrow=_narrow(unit) if unit.origin == "trigger" else 1.0,
                self_watch=unit.origin == "trigger"
                and (
                    watches_itself(unit.node)
                    or any(t in {"SelfRef"} | _ATTACHED_TAGS for t in watched)
                ),
                opt_mana=any(
                    pc.how == "optional" and tag_of(pc.leaf) == "Mana" for pc in paid
                )
                or any(tag_of(c.node) == "PayCost" for c in unit.effects),
                act_mana=activation_mana(unit) if kind == "activated" else None,
                tap=any(
                    tag_of(leaf) == "Tap"
                    for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
                ),
                treasure=sum(
                    _count(c)
                    for c in unit.effects
                    if c.concept == "make_token" and "Treasure" in c.subject
                ),
                fodder=any(
                    tag_of(pc.leaf) == "Sacrifice"
                    and tag_of(getattr(pc.leaf, "target", None)) != "SelfRef"
                    for pc in paid
                )
                or any(
                    c.concept == "sacrifice"
                    and c.scope == "you"
                    and tag_of(getattr(c.node, "target", None)) != "SelfRef"
                    for c in unit.effects
                ),
            )
            src.rate = _rate(unit, src)
            out.append(src)
    return out


def _advantage(s: _Source) -> int:
    """Cards gained on the table: a symmetric draw gives each opponent as many."""
    return s.net - (s.got if s.each else 0)


def _draw_cost(card: dict, sources: list[_Source]) -> float:
    """The mana the card costs on the curve: its cast cost
    (``_common.cast_cost``; a card with no mana cost keeps that fixed cost). A
    cost-reduction keyword's spell is capped at 3. An X draw spell pays about
    one mana per card. Treasures it makes come back."""
    if unpriced(card):
        return NO_COST
    mana_cost = front_mana_cost(card)
    cost = max(0.0, cast_cost(card))
    if set(card.get("keywords") or ()) & _COST_REDUCERS:
        cost = min(cost, 3.0)
    if "{X}" in mana_cost and any(s.scaling for s in sources):
        cost += _SCALING
    return max(0.0, cost - max((s.treasure for s in sources), default=0))


def _ends_itself(card: dict) -> bool:
    """Whether the card carries cumulative upkeep (CR 702.24a): a permanent
    whose upkeep cost climbs every turn until you stop paying and sacrifice it."""
    return any(
        "CumulativeUpkeep" in tree.card_keywords for tree in trees_for(card, bulk=card)
    )


def features(card: dict) -> dict[str, float] | None:
    """The card-draw read's features for ``card``, or ``None`` when no draw of its
    own nets it a card (looting, rummaging, connive, cycling, a gift)."""
    sources = _sources(card)
    mine = [s for s in sources if s.got > 0 and s.kind != "cycling"]
    if not mine or max(s.net for s in mine) <= 0:
        return None
    engines = [s for s in mine if s.kind in _ENGINE_KINDS]
    now = [s for s in mine if s.kind in _ONE_SHOT and s.kind != "ltb"]
    cost = _draw_cost(card, sources)
    one_eff = 0.0
    if now:
        one_eff = _advantage(max(now, key=_advantage)) / max(1.0, cost)
    act_eff = max(
        (
            s.got / max(1.0, (s.act_mana or 0) + (0.5 if s.tap else 0))
            for s in engines
            if s.kind == "activated"
        ),
        default=0.0,
    )
    triggers = [s for s in engines if s.kind == "trigger"]
    fuels = {s.fuel for s in triggers}
    broad = {s.fuel for s in triggers if s.narrow == 1.0 and not s.opt_mana}
    if any(s.kind == "replacement" for s in engines):
        fuels.add("turn")
        broad.add("turn")
    flow = max((max(0, _advantage(s)) * s.rate for s in engines), default=0.0)
    face = faces(card)[0]
    # An engine on a permanent with cumulative upkeep doesn't last: its upkeep
    # cost grows by one payment every turn and it is sacrificed when you stop
    # paying (CR 702.24a), so Mystic Remora draws for a few turns, then goes.
    # It keeps its draw rate while it runs (``flow``) but none of a lasting
    # engine's credit. Dan's call, not a fitted weight: play-rate
    # scores Remora with the lasting engines, and the read had it above Rhystic
    # Study.
    lasting = float(not _ends_itself(card))
    return {
        "engine": float(bool(engines)) * lasting,
        "flow": math.log2(1 + flow),
        "self_fuel": float(bool(broad & _SELF_FUEL) and "turn" not in broad) * lasting,
        "opp_fuel": float(bool(broad & _OPP_FUEL) and "turn" not in broad) * lasting,
        "combat": float(
            bool(fuels) and fuels <= {"combat", "other"} and "combat" in fuels
        )
        * lasting,
        "act_engine": float(
            any(s.kind in ("activated", "loyalty") for s in engines) and not fuels
        )
        * lasting,
        "one_eff": max(-1.0, min(one_eff, 2.0)),
        "act_eff": min(act_eff, 2.0),
        "cheap": float(cost <= 2),
        "board_scaling": float(any(s.board for s in mine)),
        "fodder": float(all(s.fodder for s in mine)),
        "wheel": float(any(s.wheel for s in mine)),
        "sac_draw": float(all(s.kind == "sac" for s in mine)),
        "self_watch": float(bool(triggers) and all(s.self_watch for s in triggers)),
        "body": float("Creature" in face),
        "other_roles": float(len(role_of(card) & _OTHER_ROLES)),
    }


#: Card draw's weights, log10 play-rate per unit (ridge fit, 2026-10-19,
#: standardised weight / feature sd, rounded; ``auto_engine`` rounded to 0.01 of
#: noise and was dropped, ``symmetric`` dropped as popularity — see above).
WEIGHTS: dict[str, float] = {
    "opp_fuel": 0.63,  # an engine opponents' casts fire (Rhystic Study, Esper Sentinel)
    "act_engine": -0.34,  # an engine only an activation runs ({3}, {T}: draw)
    "self_fuel": 0.30,  # an engine the deck's own plays fire (Beast Whisperer)
    "wheel": 0.27,  # discards a hand and draws a new one
    "board_scaling": 0.23,  # draws more the bigger your board (Shamanic Revelation)
    "engine": 0.23,  # it draws again and again
    "sac_draw": -0.17,  # its only draw is a "sacrifice this" (a cracked rock)
    "one_eff": 0.16,  # a one-shot's cards per mana (cap 2)
    "act_eff": 0.16,  # an activated engine's cards per activation mana (cap 2)
    "other_roles": 0.12,  # per other template role it fills (ramp, interaction, wipe)
    "fodder": 0.12,  # each draw eats another permanent (Village Rites, Deadly Dispute)
    "self_watch": -0.10,  # only it (or what it's attached to) fires the engine
    "combat": 0.10,  # an engine combat damage fires (Toski, Bident of Thassa)
    "cheap": 0.08,  # costs 2 or less
    "body": -0.06,  # a creature: dies to a sweeper
    "flow": 0.05,  # log2(1 + an engine's cards a turn cycle)
}


# ── Deck context: the fuel an engine needs from its deck ─────────────────────

#: A deck fuel: what share of the nonland deck feeds the engine, against the
#: share at which it runs at full rate (``_FUEL_REFERENCE``).
#: ``x1_creatures_or_tokens``: an Equipment's "equipped creature dies"
#: (Skullclamp), whose -1 toughness kills an X/1 and whose engine wants bodies
#: cheap to lose: X/1 creatures and creature-token makers.
_FUEL_REFERENCE: dict[str, float] = {
    "x1_creatures_or_tokens": 1 / 4,
    "creatures": 1 / 3,
    "instants_sorceries": 1 / 3,
    "enchantments": 1 / 3,
    "artifacts": 1 / 3,
}
#: The fuels a deck must supply, by the trigger's fuel class.
_DECK_FUELS = frozenset({"deaths", "enters", "creature_cast", "you_cast", "combat"})


def _source_fuel(s: _Source) -> str | None:
    """The deck fuel one draw trigger runs on, or ``None`` when every deck
    supplies it (a turn, an opponent's spell, a land entering, any spell)."""
    if s.kind != "trigger" or s.fuel is None:
        return None
    if s.fuel == "equipped_dies":
        return "x1_creatures_or_tokens"
    if s.fuel not in _DECK_FUELS:
        return None
    if s.watched & {"Instant", "Sorcery"} and not s.watched - {"Instant", "Sorcery"}:
        return "instants_sorceries"
    if "Creature" in s.watched or s.fuel in ("deaths", "creature_cast", "combat"):
        return "creatures"
    if s.watched == {"Enchantment"}:
        return "enchantments"
    if s.watched == {"Artifact"}:
        return "artifacts"
    return None


#: oracle_id -> the card's deck fuel.
_FUEL_MEMO: dict[str, str | None] = {}


def draw_fuel(card: dict) -> str | None:
    """What ``card``'s draw engine needs its deck to be full of
    (``_FUEL_REFERENCE``'s keys), or ``None`` when it runs in any deck: no
    engine, or one fired by the turn, opponents or any spell. The engine is
    the one that flows the most cards."""
    oid = card.get("oracle_id")
    if oid and oid in _FUEL_MEMO:
        return _FUEL_MEMO[oid]
    engines = [
        s
        for s in _sources(card)
        if s.got > 0 and s.kind in _ENGINE_KINDS and _advantage(s) > 0
    ]
    best = max(engines, key=lambda s: _advantage(s) * s.rate, default=None)
    fuel = _source_fuel(best) if best is not None else None
    if oid and trees_for(card, bulk=card):
        _FUEL_MEMO[oid] = fuel
    return fuel


def _feeds(record: dict, fuel: str) -> bool:
    """Whether one deck card feeds ``fuel``: by its type line, its printed
    toughness, and the token-maker lane (``token_maker``: it makes creature
    tokens for you)."""
    face = faces(record)[0]
    if fuel == "instants_sorceries":
        return "Instant" in face or "Sorcery" in face
    if fuel == "enchantments":
        return "Enchantment" in face
    if fuel == "artifacts":
        return "Artifact" in face
    makes_bodies = "token_maker" in _signal_keys_for(record)
    if fuel == "creatures":
        return "Creature" in face or makes_bodies
    toughness = str(record.get("toughness") or "")
    return ("Creature" in face and toughness in ("0", "1")) or makes_bodies


#: (the deck's oracle ids, fuel) -> the share of its nonland cards feeding it.
#: The deck's fuel shares, keyed by the deck sequence's identity and the fuel;
#: each entry holds the deck itself, so a reused id can't alias another deck.
_SHARE_MEMO: dict[tuple[int, str], tuple[Sequence[dict], float]] = {}


def _fuel_share(deck_records: Sequence[dict], fuel: str) -> float:
    """The share of the deck's nonland cards (one record per copy) feeding
    ``fuel``."""
    key = (id(deck_records), fuel)
    hit = _SHARE_MEMO.get(key)
    if hit is not None and hit[0] is deck_records:
        return hit[1]
    if len(_SHARE_MEMO) > 256:
        _SHARE_MEMO.clear()
    nonland = [r for r in deck_records if "Land" not in faces(r)[0]]
    fed = sum(1 for r in nonland if _feeds(r, fuel))
    share = fed / len(nonland) if nonland else 0.0
    _SHARE_MEMO[key] = (deck_records, share)
    return share


def deck_fit(card: dict, deck_records: Sequence[dict]) -> float:
    """The share of ``card``'s draw engine the deck can fuel, in [0, 1]: the
    deck's share of nonland cards feeding :func:`draw_fuel`, against the share
    at which it runs at full rate, capped at 1. 1.0 for a card with no
    deck-dependent fuel, or with no deck to read."""
    fuel = draw_fuel(card)
    if fuel is None or not deck_records:
        return 1.0
    return min(1.0, _fuel_share(deck_records, fuel) / _FUEL_REFERENCE[fuel])
