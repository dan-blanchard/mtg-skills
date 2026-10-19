"""Board wipe — how well a card sweeps the board (the ``board_wipe`` role).

A sweep is an ability unit the shared lanes call one — ``_mass_removal`` /
``_mass_bounce`` run on a one-unit view of the tree — or a one-sided mass shrink
those lanes leave to debuff_makers (Massacre Wurm's "creatures your opponents
control get -2/-2", read by ``_negative_pt_field``), or a static population
shrink (Elesh Norn, ``roles._static_board_shrink``). Within a sweep unit the
read takes its mass-tagged effects. An overload spell counts too: phase keeps
only its targeted mode, and overload swaps every "target" for "each" (CR
702.96a), so Cyclonic Rift and Damn read as the sweeps they are cast for, their
base mode's effect at the overload cost (``_overloaded``, the lanes' own read).
A sweep of only your own permanents, or of your own cards (Glimpse of Tomorrow),
is not one; nor is "and all other permanents with the same name" trailing a
targeted kill (Maelstrom Pulse).

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
    MASS_TAGS,
    activation_mana,
    cast_cost,
    faces,
    fixed_value,
    front_mana_cost,
    one_unit,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.lanes._shared import _negative_pt_field
from mtg_utils._analysis.lanes.mana_and_wipes import (
    _mass_bounce,
    _mass_removal,
    _overloaded,
)
from mtg_utils._analysis.roles import _static_board_shrink
from mtg_utils._card_ir.crosswalk import (
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
    pt_mod_signs,
    static_affected,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptNode, ConceptTree

#: The single-target tags an overload cost turns into "each" (CR 702.96a).
_OVERLOAD_TAGS = frozenset({"Destroy", "DealDamage", "Bounce", "ChangeZone", "Pump"})
#: The permanent types a sweep is read as reaching (lands are land destruction).
_SWEPT = frozenset({"Creature", "Artifact", "Enchantment", "Planeswalker"})
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
#: The creatures on a Commander table that wants a wipe — what a "{1} less for
#: each creature on the battlefield" discount is worth (Blasphemous Act).
_BOARD_CREATURES = 6
#: The X that clears a Commander board when nothing on the card says more.
_BOARD_X = 4
#: Undaunted's discount at a four-player table: {1} per opponent (CR 702.125a).
_UNDAUNTED = 3


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
    discount: tuple[str, int] | None  # ("board" | "fixed", generic) self reduction
    face_cmc: int | None  # the face's own printed mana value


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


def _discount(tree: ConceptTree) -> tuple[str, int] | None:
    """The card's own cost reduction (CR 601.2f): ``("board", n)`` for "{n} less
    for each creature on the battlefield", ``("fixed", n)`` for a flat or
    conditional one (Hour of Revelation, Avenge)."""
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
            )
    return None


def _is_sweep_unit(tree: ConceptTree, u: AbilityUnit) -> bool:
    one = one_unit(tree, u)
    return bool(_mass_removal(one) or _mass_bounce(one)) or any(
        tag_of(c.node) == "PumpAll"
        and _negative_pt_field(c.node, "toughness")
        and filter_controller(effect_filter(c.node), u) != "You"
        for c in u.effects
    )


def _is_overload_unit(u: AbilityUnit) -> bool:
    return (
        u.kind == "Spell"
        and not any(tag_of(c.node) in MASS_TAGS for c in u.effects)
        and any(
            tag_of(c.node) in _OVERLOAD_TAGS
            and set(filter_core_types(effect_filter(c.node))) & _SWEEP_TYPES
            for c in u.effects
        )
    )


def _tree_sweeps(tree: ConceptTree, *, walker: bool) -> list[_Sweep]:
    overload = _overloaded(tree)
    units: list[tuple[AbilityUnit, bool]] = []
    for u in tree.units:
        # An overload spell's sweep is its targeted base mode over every object
        # it could target (CR 702.96a-b); the lanes read it the same way.
        ov = overload and _is_overload_unit(u)
        if ov or _is_sweep_unit(tree, u):
            units.append((u, ov))
    discount = _discount(tree)
    out: list[_Sweep] = []
    for u, ov in units:
        tags = MASS_TAGS | (_OVERLOAD_TAGS if ov else frozenset())
        delayed, gated = _gates(u)
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(u.node, "cost", None))}
        unparsed = any(tag_of(n) == "Unimplemented" for n in iter_typed_nodes(u.node))
        # Value to the caster riding the sweep: a draw, token or life that is yours
        # (not Mogg Infestation's goblins for the wiped player, not Settle's land).
        rider = any(
            tag_of(c.node) not in tags
            and c.scope == "you"
            and c.concept in ("draw", "make_token", "gain_life")
            for c in u.effects
        )
        cond = getattr(u.node, "condition", None) or getattr(
            getattr(u.node, "sub_ability", None), "condition", None
        )
        for c in u.effects:
            tag = tag_of(c.node)
            if tag not in tags:
                continue
            if tag == "PumpAll" and not _negative_pt_field(c.node, "toughness"):
                continue
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
                )
            )
    return out


def _static_sweep(trees: list[ConceptTree]) -> _Sweep:
    """A static population shrink (``roles._static_board_shrink`` admitted it):
    its largest toughness reduction, and whose creatures it shrinks."""
    mag, ctrl = 0, None
    for tree in trees:
        for u in tree.units:
            for sdef in iter_static_defs(u.node):
                if pt_mod_signs(sdef)[1] >= 0:
                    continue
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
    )


def _sweeps(card: dict) -> list[_Sweep]:
    trees = list(trees_for(card, bulk=card))
    walker = "Planeswalker" in (card.get("type_line") or "")
    out = [s for tree in trees for s in _tree_sweeps(tree, walker=walker)]
    if not out and trees and _static_board_shrink(card):
        out.append(_static_sweep(trees))
    return out


def _lethal(s: _Sweep) -> bool:
    return s.mode in _KILLS or (
        s.mode in ("damage", "shrink") and (s.mag or 0) >= KILL_SIZE
    )


def _overload_cost(card: dict) -> int | None:
    """The overload cost's mana value, X as 0 (CR 202.3e) — the cost the sweep is
    cast for."""
    for tree in trees_for(card, bulk=card):
        for alt in tree.card_alt_costs:
            if alt.kind == "overload":
                return mana_value_of_cost(alt.cost)
    return None


def _cost(card: dict, best: _Sweep, *, x: bool) -> float:
    """The mana the sweep costs as cast: the card's cast cost
    (``_common.cast_cost``; a card with no mana cost keeps that fixed cost); a
    split half's own cost; the overload cost; the card's own discount; X at its
    floor or ``_BOARD_X``; plus an activation's mana on a noncreature permanent."""
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
    if best.discount is not None:
        kind, generic = best.discount
        cost = max(
            1.0, cost - (generic * _BOARD_CREATURES if kind == "board" else generic)
        )
    if x and best.kind == "spell":
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
    clean = (
        lethal
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
        "cheap": float(cost <= 3),
        "clean": float(clean),
        "cheap_clean": float(clean and cost <= 3),
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
#: standardised weight / feature sd, rounded).
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
    "cheap": -0.09,  # costs 3 or less (most cheap sweeps are small)
    "clean": 0.14,  # every creature dies, nothing lets one through
    "cheap_clean": 0.44,  # a clean sweep at 3 or less (Toxic Deluge)
    "repeat": -0.12,  # sweeps again (Pestilence)
    "rider": 0.06,  # a draw, token or life for the caster
}
