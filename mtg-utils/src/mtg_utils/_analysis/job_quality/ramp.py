"""Ramp — how well a nonland card accelerates your mana (the ``ramp`` role,
``roles.is_ramp``).

Each ramp source a card carries is read off its own ability unit and classed by
how it repeats: every turn with nothing asked (a {T} mana ability, a land put onto
the battlefield, an upkeep trigger, a Treasure each time an opponent draws), only
when something else happens (attacking, casting, fodder to sacrifice, other
creatures to tap, counters to spend, a condition), or once (a ritual, an enters
Treasure, a rock that sacrifices itself, a dies trigger). The reliable mana a turn
it adds, against what it costs to deploy (``payback``), is the read's main term.

Fitted on the 1,479 commander-legal nonland cards whose main job is ramp (at
least as many of their effectful abilities carry a ramp component as carry
anything else): cross-validated Spearman 0.284 against play-rate; the precon
guides' ramp adds sit at the 80th percentile of their color identity's ramp by
this read (90th by play-rate), and the bottom two ramp cards of each precon by
this read hold 15 of the guides' cuts (19 by play-rate, 9 by mana value). Every
card with a ramp component is scored, not only the fitted ones. Too weak to order
candidates; it GATES them (``JobRead.orders``). The rest is card age,
reprints, rituals and Treasure payoffs played for their deck's plan, and costs
phase drops (Pyramid of the Pantheon's brick counters, Gaea's Balance's five lands).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    cast_cost,
    fixed_value,
    front_mana_cost,
    mana_in,
    one_unit,
)
from mtg_utils._analysis.lanes import additional_land_play
from mtg_utils._analysis.lanes._shared import YOU_EACH
from mtg_utils._analysis.lanes.board_and_ramp import granted_mana_defs
from mtg_utils._analysis.lanes.counters_voltron import TOKEN_OWNER_IS_YOU
from mtg_utils._analysis.roles import is_ramp
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.tree_synthesis.mana_ramp_lands import (
    has_structural_extra_land_drop,
)
from mtg_utils._card_ir.crosswalk import (
    filter_core_types,
    filter_subtypes,
    iter_cost_leaves,
    land_searches,
    mana_ability_gates,
    tag_of,
)
from mtg_utils._card_ir.crosswalk.reads import (
    amount_factor,
    has_fixed_count,
    is_self_enters_trigger,
    iter_search_landings,
    mana_replacement_multiplier,
    mana_restrictions,
    mana_spell_type_restriction,
    trigger_phase,
    trigger_scope,
    unit_own_mana,
    watches_itself,
)
from mtg_utils.card_classify import color_sources
from mtg_utils.theme_presets import signal_keys_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

#: A dynamic count (Gaea's Cradle-style "for each", a creature's power) reads as
#: two mana a turn — the read's own guess, the board decides.
_SCALING = 2
_BASIC_TYPES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})
#: Events where the card itself leaves: a dies trigger's mana comes once, later.
_LEAVES = frozenset({"dies", "leaves", "leavesbattlefield", "ltb"})
#: A land put by a condition or a dies trigger may never come.
_LAND_WEIGHT = {"turn": 1.0, "now": 1.0, "cond": 0.5, "late": 0.5}
#: Replacements that only set the card up as it enters (tapped, a chosen color,
#: its counters): not an ability doing another job.
_TRIVIAL_REPLACEMENTS = frozenset({"Choose", "SetTapState", "PutCounter"})


@dataclass
class _Read:
    """What a card's ramp sources add up to."""

    turn: float = 0.0  # reliable mana a turn, beside the {T} abilities
    tap_best: float = 0.0  # its best {T} mana ability (they share one tap)
    cond: bool = False  # a source that needs something else to happen
    land_bf: float = 0.0  # lands it puts onto your battlefield
    land_sac: int = 0  # lands its spell sacrifices as a cost (Harrow)
    land_tapped: bool = False
    land_untapped: bool = False
    land_hand: bool = False  # a found land goes to your hand (Cultivate)
    land_act_cost: int | None = None  # a fetcher's activation (Wayfarer's Bauble)
    dork: bool = False  # a creature taps for it
    rock: bool = False  # a noncreature taps for it with no mana in
    restricted: list[bool] = field(default_factory=list)
    extra_land: float = 0.0
    granted: float = 0.0
    scales: bool = False
    paid: bool = False  # one mana per counter paid for (Everflowing Chalice)
    from_hand: bool = False  # a spirit guide: paid from hand, never cast
    gives: bool = False  # Treasure an opponent creates too
    treasure: bool = False  # Treasure you keep: any color (``color_sources`` skips it)
    equip: int = 0
    other_units: int = 0  # effectful abilities with no ramp component


def _mana_amount(node: object) -> tuple[int, bool | str]:
    """(mana per use, scales?) of a ``Mana`` effect: a Fixed count, a colors list's
    length, Mixed's colors + colorless; ``"paid"`` for counters on itself."""
    p = getattr(node, "produced", None)
    if p is None:
        return 0, False
    cnt = getattr(p, "count", None)
    if cnt is not None:
        if tag_of(cnt) == "Fixed":
            v = fixed_value(cnt)
            return (1 if v is None else v), False
        qty = getattr(cnt, "qty", None)
        if tag_of(qty) == "CountersOn" and tag_of(getattr(qty, "scope", None)) == (
            "Source"
        ):
            return 1, "paid"
        return _SCALING, True
    if tag_of(p) == "Mixed":
        cl = getattr(p, "colorless_count", 0)
        colors = getattr(p, "colors", None) or []
        return len(colors) + (cl if isinstance(cl, int) else 0), False
    colors = getattr(p, "colors", None)
    if isinstance(colors, list) and colors:
        return len(colors), False
    if tag_of(p) == "DistinctColorsAmongPermanents":
        return _SCALING, True
    return 1, False


def _cost_shape(ability: object) -> tuple[int, bool, bool, bool]:
    """(mana in, spends the card itself, needs something else, taps) of an
    ability's cost. Sacrificing or exiling the card itself (Lotus Petal, Simian
    Spirit Guide) is one use; sacrificing another permanent, tapping other
    creatures or removing counters needs a supply the board may not have."""
    cost = getattr(ability, "cost", None)
    self_spent, other, tap = False, False, False
    for leaf in iter_cost_leaves(cost):
        t = tag_of(leaf)
        if t == "Sacrifice":
            if tag_of(getattr(leaf, "target", None)) == "SelfRef":
                self_spent = True
            else:
                other = True
        elif t in ("Exile", "Discard"):
            self_spent = True
        elif t in ("TapCreatures", "RemoveCounter"):
            other = True
        elif t == "Tap":
            tap = True
    return mana_in(cost), self_spent, other, tap


def _restricted(eff: TypedMirrorNode) -> bool:
    """The mana carries a spend restriction (CR 106.6): a spell type, a zone, a
    kicked spell, abilities only."""
    rs = getattr(eff, "restrictions", None)
    return bool(isinstance(rs, (list, tuple)) and rs) or bool(
        mana_restrictions(eff) or mana_spell_type_restriction(eff)
    )


def _unread_rider(unit: AbilityUnit) -> bool:
    """A residue phase couldn't parse sits beside the mana (Thran Turbine's spend
    clause, Soulbright Seeker's third-resolution condition): a condition the tree
    can't show."""
    return any(
        tag_of(c.node) in ("Unimplemented", "GenericEffect") for c in unit.effects
    )


def _trigger_class(unit: AbilityUnit) -> str:
    if is_self_enters_trigger(unit):
        return "now"
    if unit.trigger_event == "tapsformana" or trigger_phase(unit.node) is not None:
        return "turn"
    if trigger_scope(unit.node) in ("opponents", "each"):
        return "turn"  # an opponent's own draw or cast comes every turn cycle
    if watches_itself(unit.node) and (unit.trigger_event or "") in _LEAVES:
        return "late"
    return "cond"


def _unit_class(
    unit: AbilityUnit, ability: object | None = None, *, spell_card: bool = False
) -> str:
    """How one ramp source of ``unit`` repeats: ``turn`` / ``cond`` / ``now`` /
    ``late``. ``ability`` is the node carrying it when the card grants itself the
    ability (Urza's Saga's chapter I)."""
    granted_self = ability is not None and ability is not unit.node
    if spell_card and unit.origin in ("static", "replacement"):
        k = "now"  # an instant or sorcery does what it does once
    elif unit.origin in ("static", "replacement"):
        k = "turn"
    elif (unit.origin == "ability" and unit.kind == "Activated") or granted_self:
        _m, self_spent, other, _t = _cost_shape(ability if granted_self else unit.node)
        k = "now" if self_spent else ("cond" if other else "turn")
    elif unit.origin == "ability":
        k = "now"  # a spell resolves once
    elif unit.origin == "trigger":
        k = _trigger_class(unit)
    elif unit.origin == "synth":
        # A synthesized clause carries no kind, cost or trigger of its own, so
        # how often it repeats is unknown: read as conditional.
        k = "cond"
    else:
        k = "turn"
    if k == "turn" and (
        _unread_rider(unit) or getattr(unit.node, "condition", None) is not None
    ):
        k = "cond"
    return k


def _unit_ramps(tree: ConceptTree, unit: AbilityUnit) -> bool:
    """Whether ``unit`` carries a ramp component of its own: a mana ability, a
    Treasure maker, a land search onto the battlefield, an extra land drop, a mana
    doubler, a granted mana ability."""
    if next(unit_own_mana(unit), None) is not None:
        return True
    if any(c.concept == "make_token" and "Treasure" in c.subject for c in unit.effects):
        return True
    one = one_unit(tree, unit)
    if any(s.to_battlefield and not s.cycling for s in land_searches(one)):
        return True
    return bool(
        additional_land_play(one)
        or has_structural_extra_land_drop(one)
        or mana_replacement_multiplier(unit.node) >= 2
        or unit.has_effect("extra_land_drop")
        or granted_mana_defs(one)
    )


def _effectful(unit: AbilityUnit) -> bool:
    # The synthesis unit is no ability of the card's: it holds the clauses phase
    # left unparsed inside the card's own abilities (``signal_trees``).
    if unit.origin in ("keyword", "synth"):
        return False
    if unit.origin == "replacement":
        return not all(tag_of(c.node) in _TRIVIAL_REPLACEMENTS for c in unit.effects)
    return bool(unit.effects or unit.statics or unit.origin == "static")


def _own_mana(r: _Read, tree: ConceptTree, unit: AbilityUnit, *, sc: bool) -> float:
    """The card's own mana abilities in ``unit``: the best reliable one that
    doesn't tap (abilities sharing {T} go to ``r.tap_best``)."""
    best = 0.0
    creature = tree.is_type("Creature")
    for eff, ability in unit_own_mana(unit):
        amount, scales = _mana_amount(eff)
        restricted = _restricted(eff)
        r.restricted.append(restricted)
        k = _unit_class(unit, ability, spell_card=sc)
        activated = (
            unit.origin == "ability" and unit.kind == "Activated"
        ) or ability is not unit.node
        mana_in, _s, _o, taps = (
            _cost_shape(ability) if activated else (0, False, False, False)
        )
        if k == "turn":
            r.paid |= scales == "paid"
            r.scales |= scales is True
            worth = ((_SCALING if scales is True else amount) - mana_in) * (
                0.5 if restricted else 1.0
            )
            if activated and taps:
                r.tap_best = max(r.tap_best, worth)
            else:
                best = max(best, worth)
            if activated:
                # CR 302.6: a creature's {T} ability waits a turn; a rock's doesn't.
                r.dork |= creature
                r.rock |= not creature and not mana_in
        elif k == "now":
            r.from_hand |= activated and any(
                tag_of(n) in ("Exile", "Discard")
                for n in iter_cost_leaves(getattr(ability, "cost", None))
            )
        elif k == "cond":
            r.cond = True
    return best


def _treasure(r: _Read, unit: AbilityUnit, *, sc: bool) -> None:
    """Treasure makers: a Treasure adds one mana once (CR 111.10a), and its creator
    owns it (CR 111.2) — one an opponent creates is theirs."""
    for c in unit.effects:
        if c.concept != "make_token" or "Treasure" not in c.subject:
            continue
        owner = getattr(c.node, "owner", None)
        if c.scope not in YOU_EACH or not (
            owner is None or tag_of(owner) in TOKEN_OWNER_IS_YOU
        ):
            r.gives = True
            continue
        r.treasure = True
        n = amount_factor(c.node, "count") if has_fixed_count(c.node, "count") else 2
        k = _unit_class(unit, spell_card=sc)
        if unit.origin == "ability" and unit.kind == "Activated" and k == "turn":
            k = "cond"  # an activated Treasure maker pays for each Treasure
        if k == "turn":
            if unit.origin == "trigger" and trigger_scope(unit.node) in (
                "opponents",
                "each",
            ):
                n *= 2  # each opponent's draw or cast: several a turn cycle
            r.turn += min(n, 2)
        elif k == "cond":
            r.cond = True


def _lands(r: _Read, tree: ConceptTree, unit: AbilityUnit, *, sc: bool) -> None:
    """YOUR land searches: onto the battlefield is a land for good; into the hand
    is a card (Cultivate's second land). Then extra land drops: every turn still
    needs a land in hand (CR 305.2: effects may raise the one-land limit), so half
    a land a turn; once (an enters put, a spell) a quarter."""
    one = one_unit(tree, unit)
    if unit.origin == "ability" and unit.kind == "Spell":
        sacrificed = [
            c for c in unit.costs if c.concept == "sacrifice" and "Land" in c.subject
        ]
        r.land_sac = max(r.land_sac, len(sacrificed))
    if any(tag_of(c.node) == "SearchLibrary" for c in unit.effects):
        for s in land_searches(one):
            if s.cycling or not s.to_battlefield:
                continue
            k = _unit_class(unit, spell_card=sc)
            r.cond |= k == "cond"
            r.land_bf = max(r.land_bf, s.count * _LAND_WEIGHT[k])
            r.land_tapped |= s.enters_tapped
            r.land_untapped |= not s.enters_tapped
            if unit.origin == "ability" and unit.kind == "Activated":
                r.land_act_cost = _cost_shape(unit.node)[0]
            r.land_hand |= any(d == "Hand" for d, _t in iter_search_landings(unit))
    if (
        additional_land_play(one)
        or has_structural_extra_land_drop(one)
        or unit.has_effect("extra_land_drop")
    ):
        k = _unit_class(unit, spell_card=sc)
        r.extra_land = max(r.extra_land, 0.5 if k == "turn" else 0.25)


def _granted(r: _Read, tree: ConceptTree, unit: AbilityUnit, *, sc: bool) -> None:
    """Mana abilities ``unit`` grants (``board_and_ramp.granted_mana_defs``). To
    lands it adds nothing — a land taps once whichever ability it uses (Joiner
    Adept). To creatures it is new sources: several for a class (Cryptolith Rite),
    one for an Aura's or Equipment's creature, summoning sick either way (CR 302.6).
    A token's own "Sacrifice: add" (Eldrazi Spawn) is one mana per token; a granted
    trigger or loyalty ability is conditional."""
    makes_tokens = unit.has_effect("make_token")
    for definition, affected in granted_mana_defs(one_unit(tree, unit)):
        own = tag_of(affected) in (None, "SelfRef")
        if own and not makes_tokens:
            continue  # the card's own self grant: ``_own_mana`` reads it
        if (
            not own
            and tag_of(affected) in ("Typed", "Or", "And")
            and (
                "Land" in filter_core_types(affected)
                or bool(set(filter_subtypes(affected)) & _BASIC_TYPES)
            )
        ):
            continue
        cost = getattr(definition, "cost", None)
        leaves = {tag_of(n) for n in iter_cost_leaves(cost)}
        k = _unit_class(unit, spell_card=sc)
        if own or "Sacrifice" in leaves:
            if k == "turn":
                r.turn += 1
            elif k == "cond":
                r.cond = True
        elif "Loyalty" in leaves or not leaves:
            r.cond = True
        elif k == "turn":
            single = bool({"Aura", "Equipment"} & set(tree.card_subtypes))
            r.granted = max(r.granted, 1.0 if single else 2.0)
            r.dork |= "Creature" in filter_core_types(affected)


def _read(card: dict) -> _Read:
    r = _Read()
    for tree in signal_trees_for(card, bulk=card):
        sc = tree.is_type("Instant") or tree.is_type("Sorcery")
        for unit in tree.units:
            if _effectful(unit) and not _unit_ramps(tree, unit):
                r.other_units += 1
            if (
                "Equipment" in tree.card_subtypes
                and unit.kind == "Activated"
                and (unit.has_effect("attach"))
            ):
                r.equip = _cost_shape(unit.node)[0]
            r.turn += _own_mana(r, tree, unit, sc=sc)
            _treasure(r, unit, sc=sc)
            _lands(r, tree, unit, sc=sc)
            _granted(r, tree, unit, sc=sc)
    r.turn += r.tap_best
    return r


def _ramp_cost(card: dict, r: _Read) -> float:
    """What deploying the ramp costs: the card's cast cost (``_common.cast_cost``);
    0 for a spirit guide; one counter's price for a pay-per-counter rock (Chalice's
    multikicker {2}, Cornucopia's {X}{X}{X}); plus an equip, and a fetcher's
    activation when that is the whole ramp (Wayfarer's Bauble, Burnished Hart)."""
    mana_cost = front_mana_cost(card)
    cost = cast_cost(card)
    if r.from_hand:
        cost = 0.0
    if r.paid:
        cost = max(cost + mana_cost.count("{X}"), 2.0)
    cost += r.equip
    if r.land_act_cost is not None and r.land_bf and not r.turn:
        cost += r.land_act_cost
    return cost


def features(card: dict) -> dict[str, float] | None:
    """The ramp read's features for ``card``, or ``None`` when it is not ramp
    (``roles.is_ramp`` — the shared ramp answer, so a doubler or a Powerstone maker
    the unit walk here doesn't itemise still scores; a land is the mana base,
    never ramp)."""
    if not is_ramp(card):
        return None
    r = _read(card)
    cost = _ramp_cost(card, r)
    turn = r.turn + max(r.land_bf - r.land_sac, 0) + r.extra_land + r.granted
    keys = signal_keys_for(card)
    if "mana_amplifier" in keys:
        turn = max(turn, 2.0)  # a doubler: at least two more a turn
    gates = [
        g
        for tree in signal_trees_for(card, bulk=card)
        for g in mana_ability_gates(tree)
    ]
    # Halved: only when a condition holds (Mox Opal, CR 602.5: a prohibited
    # activation can't begin), only on some spells (CR 106.6), or shared with
    # every player (Magus of the Vineyard, a Treasure each opponent gets too).
    if (
        (gates and all(gates))
        or (r.restricted and all(r.restricted))
        or "group_mana" in keys
        or r.gives
    ):
        turn *= 0.5
    sources = color_sources(card)
    fixes = "any" in sources or len(sources - {"C"}) >= 2 or r.treasure
    return {
        "cost": min(cost, 7.0),
        "early": float(cost <= 2),
        "per_turn": min(turn, 4.0),
        "payback": min(turn / max(cost, 1.0), 2.0),
        "cond_engine": float(r.cond and not turn),
        "fixes": float(fixes),
        "land": float(r.land_bf > r.land_sac),
        "land_tapped": float(r.land_tapped and not r.land_untapped),
        "land_hand": float(r.land_hand),
        "dork": float(r.dork and not r.rock),
        "extra_land": float(r.extra_land > 0),
        "scales": float(r.scales),
        "other_units": float(min(r.other_units, 3)),
    }


#: Ramp's weights, log10 play-rate per unit (ridge fit, 2026-10-19, standardised
#: weight / feature sd, rounded; a one-shot burst's weight rounded to 0 and is
#: dropped).
WEIGHTS: dict[str, float] = {
    "payback": 1.20,  # reliable mana a turn per mana spent deploying it (cap 2)
    "land_hand": 0.34,  # a found land also goes to your hand (Cultivate)
    "dork": -0.33,  # a creature taps for it: summoning sick, dies to a sweeper
    "land_tapped": -0.21,  # its land enters tapped
    "early": 0.19,  # costs 2 or less
    "extra_land": 0.18,  # an extra land drop or a land put from hand
    "land": 0.18,  # puts a land onto your battlefield
    "per_turn": -0.16,  # mana a turn (cap 4): payback carries it; this trims the big
    "scales": 0.16,  # a count that grows with the board
    "cond_engine": 0.11,  # mana only when something happens (attacks, casts)
    "other_units": -0.06,  # per ability doing another job
    "fixes": 0.03,  # makes two or more colors, or any
    "cost": 0.02,  # per mana: offsets payback's and early's steepness
}
