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
returns to the battlefield (Planar Guide, Sudden Disappearance, Golden Argosy:
the shared tree's blink return); nor one on a transform back face (Jin-Gitaxias's
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

Left unread: X paid in cards rather than mana (Sickening Dreams), a drawback
rider (Bontu's Last Reckoning), Massacre Girl's chain, and what phase drops —
"for each" scaling (Swarmyard Massacre), a chosen-type or pile spare (Harsh
Mercy, Do or Die), a pitch cost (Force of Despair).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    KILL_SIZE,
    activation_mana,
    cast_cost,
    faces,
    fixed_value,
    front_mana_cost,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.lanes.mana_and_wipes import (
    mass_bounce_effects,
    mass_removal_effects,
    mass_shrink_effects,
    static_population_shrinks,
)
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    SWEPT_PERMANENT_TYPES,
    affected_tag,
    change_zone_dirs,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_owners,
    filter_predicates,
    iter_cost_leaves,
    iter_static_defs,
    iter_typed_nodes,
    mana_value_of_cost,
    modify_cost_mode,
    overload_sweep,
    static_affected,
    tag_of,
)
from mtg_utils._card_ir.trees import phase_records_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptNode, ConceptTree

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
#: A count of something narrow (your Gates, spells cast from exile this turn).
_NARROW_COUNT = 2
#: The units a card is cast or activated for: a trigger from elsewhere (cycling,
#: a delayed cast trigger) is a second read.
_PRIMARY = frozenset({"spell", "etb", "chapter", "activated", "loyalty", "static"})
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
    discount: tuple[str, int, int] | None  # (board|fixed, generic, cap) reduction
    face_cmc: int | None  # the face's own printed mana value
    mode_cost: int  # a spree / tiered mode's own additional cost (CR 702.172a)


def _scale(qty: object) -> int:
    """A non-fixed amount: ``_SCALING`` for X or a count of the board's creatures
    (Chain Reaction) or a Multiply of one (Cloudkill); ``_NARROW_COUNT`` for a
    count of anything narrower."""
    tag = tag_of(qty)
    if tag == "Variable":
        return _SCALING
    if tag == "Quantity":
        inner = getattr(qty, "value", None)
        return _SCALING if tag_of(inner) == "Multiply" else _NARROW_COUNT
    if tag == "Offset":
        return _scale(getattr(qty, "inner", None))
    if tag == "Ref":
        inner = getattr(qty, "qty", None)
        if tag_of(inner) in ("Variable", "CostXPaid"):
            return _SCALING
        if tag_of(inner) == "ObjectCount":
            filt = getattr(inner, "filter", None)
            if (
                "Creature" in filter_core_types(filt)
                and filter_controller(filt) != "You"
            ):
                return _SCALING
    return _NARROW_COUNT


def _magnitude(c: ConceptNode) -> int | None:
    tag = tag_of(c.node)
    if tag in ("DamageAll", "DealDamage"):
        amount = getattr(c.node, "amount", None)
        v = fixed_value(amount)
        return v if v is not None else _scale(amount)
    if tag in ("PumpAll", "Pump"):
        tough = getattr(c.node, "toughness", None)
        v = fixed_value(tough)
        return -v if v is not None else _scale(tough)
    return None


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
    sub-ability's own condition (Martial Coup's "if X is 5 or more")."""
    delayed: set[int] = set()
    gated: set[int] = set()
    for n in iter_typed_nodes(u.node):
        if tag_of(n) == "CreateDelayedTrigger":
            delayed.update(id(m) for m in iter_typed_nodes(n) if m is not n)
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


def _discount(tree: ConceptTree) -> tuple[str, int, int] | None:
    """The card's own cost reduction (CR 601.2f): ``("board", n, cap)`` for "{n}
    less for each creature on the battlefield", ``("fixed", n, cap)`` for a flat
    or conditional one (Hour of Revelation, Avenge). ``cap`` is the face's
    generic mana: a generic reduction never touches the colored part of the cost
    (CR 118.7a), so Vanquish the Horde never costs less than {W}{W}."""
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
            return (
                "board" if board else "fixed",
                generic if isinstance(generic, int) else 0,
                _face_generic(tree),
            )
    return None


def _face_generic(tree: ConceptTree) -> int:
    """The generic mana in ``tree``'s face's printed cost, off phase's own face
    record (its ``mana_cost.generic``)."""
    for face in phase_records_for(tree.oracle_id):
        if face.get("name") == tree.name:
            generic = (face.get("mana_cost") or {}).get("generic")
            return generic if isinstance(generic, int) else 0
    return 0


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
    out: list[_Sweep] = []
    for u in units:
        delayed, gated = _gates(u)
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(u.node, "cost", None))}
        unparsed = any(tag_of(n) == "Unimplemented" for n in iter_typed_nodes(u.node))
        # Value to the caster riding the sweep: a draw, token or life that is yours
        # (not Mogg Infestation's goblins for the wiped player, not Settle's land).
        rider = any(
            id(c.node) not in sweeps
            and c.scope == "you"
            and c.concept in ("draw", "make_token", "gain_life")
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
            # marks it (Golden Argosy, whose "each creature that crewed it"
            # phase reads as every creature).
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
            non = set(filter_non_types(filt))
            types = (cores | (_SWEPT if "Permanent" in cores else set())) & _SWEPT
            mag = _magnitude(c)
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
                    or tag == "ChooseAndSacrificeRest",
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


def _sweeps(card: dict) -> list[_Sweep]:
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


def _cost(card: dict, best: _Sweep, *, x: bool) -> float:
    """The mana the sweep costs as cast: the card's cast cost
    (``_common.cast_cost``; a card with no mana cost keeps that fixed cost); a
    split half's own cost; the overload cost; a spree or tiered mode's own cost;
    the card's own discount; X at its floor or ``_BOARD_X`` — for a spell, and
    for a permanent's enters trigger, whose X is the one paid to cast it (CR
    107.3m: The Meathook Massacre, Spiteful Banditry); plus an activation's mana
    on a noncreature permanent."""
    cost = cast_cost(card)
    if unpriced(card):
        return cost
    front, *backs = faces(card)
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
    if x and best.kind in ("spell", "etb"):
        cost += best.x_floor or _BOARD_X
    if (
        best.kind == "activated"
        and best.act_mana is not None
        and "Creature" not in front
    ):
        cost += best.act_mana + (_BOARD_X if best.x_bound else 0)
    return cost


def features(card: dict) -> dict[str, float] | None:
    """The board-wipe read's features for ``card``, or ``None`` when it has no
    sweep of its own."""
    sweeps = _sweeps(card)
    if not sweeps:
        return None
    best = max(
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
    x = "{X}" in front_mana_cost(card)
    cost = _cost(card, best, x=x)
    lethal = _lethal(best)
    creatures = "Creature" in best.types
    # A sweep on demand: one the card is cast or activated for, not one an
    # event elsewhere fires (Sarkhan's Unsealing's power-7 cast trigger).
    clean = (
        best.kind in _PRIMARY
        and lethal
        and creatures
        and not best.preds & (_NARROW | _SIZED | _SPARES)
        and not best.spares
        and not best.gated
        and not best.delayed
    )
    return {
        "creatures": float(creatures),
        "breadth": float(len(best.types)),
        "lethal": float(lethal),
        "bounce": float(best.mode == "bounce"),
        "small": float(
            best.mode in ("damage", "shrink") and (best.mag or 0) < KILL_SIZE
        ),
        "one_sided": float(best.ctrl in ("Opponent", "TargetPlayer")),
        "spares": float(best.spares or bool(best.preds & _SPARES)),
        "narrow": float(bool(best.preds & _NARROW)),
        "flexible": float(best.modal or best.overload or x or best.x_bound),
        "cost": min(max(cost, 1.0), 9.0),
        "cheap": float(not clean and cost <= _CHEAP),
        "clean": float(clean),
        "cheap_clean": float(clean and cost <= _REFERENCE_COST),
        "repeat": float(
            any(
                (s.kind == "activated" and not s.self_sac)
                or (s.kind == "trigger" and s.event != "cycled")
                for s in sweeps
            )
        ),
        "rider": float(any(s.rider for s in sweeps)),
    }


#: Board wipe's weights, log10 play-rate per unit (ridge fit, 2026-10-19,
#: standardised weight / feature sd, rounded). ``cheap`` and ``cheap_clean``
#: keep their fitted weights over features redrawn 2026-10-24 around the
#: reference wipe (``_REFERENCE_COST``). With the cost and sweep fixes of the
#: same day (``job_reads.py``): Spearman against play-rate 0.501 over 800 cards
#: (0.487 over 807), the guides' wipe adds at the 84th percentile of their
#: identity's wipes (79th), 8 of 19 in its top decile (8).
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
