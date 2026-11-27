"""What a resolution did in Arena against what phase's parse of it says it does.

Two layers, both over the resolving ability's **own** effects (an annotation whose
source is another object, such as a replacement effect another permanent applies, is
set aside, not scored):

* **Kinds** (:func:`compare_kinds`): Arena's annotations and phase's effects in one
  vocabulary: damage, life, draw, a zone move by its zones (a conjured card's out
  of Arena's ``Limbo``), tokens, counters (a player's poison among them), a
  continuous effect, a counter of a spell or of an ability the resolution
  targets. Arena doing something phase's parse doesn't predict is a finding;
  phase predicting something Arena didn't log is one only for an effect that must
  happen. An effect that may not (:func:`uncertain`: optional, in a branch the
  controller doesn't decide, up to one target, one of several modes) is
  ``conditional`` when it doesn't.
* **Strict checks** (:func:`strict_checks`): the facts phase states as fixed, checked
  against the amounts and objects Arena logged: a fixed damage, life, draw, token or
  counter amount, or one that is the X the spell or ability was cast with (Arena
  logs the X chosen); a pump's power and toughness change; who drew, gained life,
  or controls the tokens; a token's, counter's, damaged object's or moved
  object's type; whose object moved. An amount from an
  effect that may not happen is a ceiling. A count Arena exceeded passes when a
  permanent on the board has a replacement phase types for that event
  (:func:`explain_excess`: a token doubler, Quantum Riddler's extra draw).

Every read of phase's tree goes through ``crosswalk``.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

from mtg_utils._arena_crosscheck.align import PhaseAbility
from mtg_utils._arena_crosscheck.log import (
    NO_X,
    ChosenX,
    Effect,
    Resolution,
    num,
    word,
)
from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    acts_on_a_group,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    chosen_x_sign,
    combat_damage_hits_opponent,
    control_recipient_scope,
    counter_kind,
    effect_conditional,
    effect_filter,
    effect_is_delayed,
    effect_owner_optional,
    effect_player_reach,
    effect_reaches_player,
    effect_targets_optional,
    effects_exclusive,
    filter_controller_side,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    has_fixed_count,
    in_uncertain_branch,
    iter_typed_nodes,
    list_field,
    named_permanent_refs,
    player_counter_kind,
    recipient_tag,
    ref_qty_tag,
    tag_of,
    token_creator_side,
    triggering_player_side,
)

__all__ = [
    "Board",
    "Check",
    "KindResult",
    "arena_kinds",
    "compare_kinds",
    "explain_excess",
    "own_effects",
    "strict_checks",
]

_ZONES = ("Battlefield", "Exile", "Graveyard", "Hand", "Library", "Stack")
_MOVES = frozenset(f"move:{a}->{b}" for a in _ZONES for b in _ZONES)

#: Arena kinds that are bookkeeping, never scored.
#: (``marked``: a designation Arena marks an object with, which a conjured or
#: perpetually changed card carries too; only a Case's solve is read off it.)
UNSCORED = frozenset({"reveal", "trigger", "warp_exile", "replaced", "marked"})

_CATEGORY_KIND = {
    "Draw": "draw",
    "Discard": "discard",
    "Sacrifice": "sacrifice",
    "Destroy": "destroy",
    "Countered": "counter_spell",
    "Warp": "warp_exile",
}
_ANNOTATION_KIND = {
    "TokenCreated": "token",
    "CounterAdded": "counter_add",
    "CounterRemoved": "counter_remove",
    "LayeredEffectCreated": "continuous",
    "PowerToughnessModCreated": "continuous",
    "GainDesignation": "designation",
    "Designation": "marked",
    "AttachmentCreated": "attach",
    "ControllerChanged": "gain_control",
    "TappedUntappedPermanent": "tap_untap",
    "RevealedCardCreated": "reveal",
    "DisqualifiedEffect": "replaced",
    "AbilityInstanceCreated": "trigger",
    # an ability it targets leaving the stack: countered (CR 701.6a)
    "AbilityInstanceDeleted": "counter_spell",
}


def own_effects(res: Resolution) -> tuple[list[Effect], list[Effect]]:
    """The resolution's effects split into its own (sourced by the resolving object,
    its card, a player or the game) and the rest. An ability instance deleted is
    its own only when it is one the resolution targets: countered (CR 701.6a),
    which Arena files under the countered ability's source."""
    own = {res.instance, res.parent, None, *res.seats}

    def is_own(e: Effect) -> bool:
        if "AbilityInstanceDeleted" in e.types:
            return bool(e.affected) and set(e.affected) <= res.targets
        return e.affector in own

    mine = [e for e in res.effects if is_own(e)]
    rest = [e for e in res.effects if not is_own(e)]
    return mine, rest


#: The counters damage to a permanent of a card type removes: loyalty from a
#: planeswalker (CR 120.3c, 306.8), defense from a battle (CR 120.3h, 310.6).
DAMAGE_COUNTERS = {"Planeswalker": "loyalty", "Battle": "defense"}


def _damage_result(
    e: Effect,
    damage_to: dict[int, int],
    counter_name: Callable[[int | None], str | None],
) -> bool:
    """Whether a ``CounterRemoved`` is the result of damage in the same
    resolution: each object it takes counters from was dealt damage there, is
    of a type whose counters damage removes (:data:`DAMAGE_COUNTERS`), and
    loses that kind, all its removals of it together no more than the damage
    (a planeswalker with 1 loyalty dealt 3 damage loses 1). ``damage_to`` is
    what each object's damage has left to explain: an explained removal takes
    its amount from it, so a removal beyond the damage (the card's own "remove
    a loyalty counter" beside it) stays unexplained."""
    kind = _counter_norm(counter_name(num(e.details, "counter_type", None)))
    amount = num(e.details, "transaction_amount") or 0
    explained = bool(e.affected) and all(
        i in damage_to
        and amount <= damage_to[i]
        and any(DAMAGE_COUNTERS.get(t) == kind for t in w.get("card_types", ()))
        for i, w in zip(e.affected, e.who, strict=False)
    )
    if explained:
        for i in e.affected:
            damage_to[i] -= amount
    return explained


def arena_kinds(
    effects: Iterable[Effect],
    counter_name: Callable[[int | None], str | None] = lambda _: None,
) -> set[str]:
    """The kinds of what a resolution's own effects did. Life lost to damage
    and counters damage removed (:func:`_damage_result`) are the damage's, no
    kind of their own; ``counter_name`` names a logged counter type."""
    effects = list(effects)
    damaged = {i for e in effects if "DamageDealt" in e.types for i in e.affected}
    damage_to: dict[int, int] = collections.Counter()
    for e in effects:
        if "DamageDealt" in e.types:
            for i in e.affected:
                damage_to[i] += num(e.details, "damage") or 0
    kinds: set[str] = set()
    for e in effects:
        t = set(e.types)
        if "CounterRemoved" in t and _damage_result(e, damage_to, counter_name):
            continue
        if "DamageDealt" in t:
            kinds.add("damage")
        elif "ModifiedLife" in t:
            life = num(e.details, "life") or 0
            if life > 0:
                kinds.add("gain_life")
            elif life < 0 and not set(e.affected) & damaged:
                kinds.add("lose_life")
        elif "ZoneTransfer" in t:
            cat = word(e.details, "category", "?")
            src = word(e.details, "zone_src", "?")
            dest = word(e.details, "zone_dest", "?")
            kinds.add(_CATEGORY_KIND.get(cat) or f"move:{src}->{dest}")
        else:
            kinds.update(_ANNOTATION_KIND[k] for k in t if k in _ANNOTATION_KIND)
    return kinds


def _moves(test: Callable[[str, str], bool]) -> frozenset[str]:
    return frozenset(m for m in _MOVES if test(*m.removeprefix("move:").split("->")))


def _zone(value: object) -> str | None:
    return value if isinstance(value, str) or value is None else tag_of(value)


_SAME = frozenset(
    {"gain_life", "lose_life", "draw", "discard", "sacrifice", "destroy", "attach"}
)
_TOKEN_MAKERS = frozenset(
    {
        "make_token",
        "amass",
        "incubate",
        "investigate",
        "populate",
        "copy_token",
    }
)
#: Continuous effects: a double of power and toughness (CR 701.10a) and a
#: becoming a copy (CR 707.2's copiable values) among them.
_CONTINUOUS = frozenset(
    {
        "pump",
        "set_pt",
        "grant_keyword",
        "add_type",
        "goad",
        "phasing",
        "double_pt",
        "become_copy",
    }
)
_CONTINUOUS_TAGS = frozenset(
    {"GenericEffect", "Animate", "AddRestriction", "CantBlock"}
)
_LIBRARY_VERBS = frozenset(
    {
        "tutor",
        "dig",
        "discover",
        "explore",
        "connive",
        "surveil",
        "scry",
        "mill",
        "exile_top",
        "cast_from_zone",
        "reveal_until",
    }
)
#: The modifications Arena logs a layered effect for: P/T, keywords, types,
#: colours, abilities. A generic effect with none of them changes only a rule.
_VISIBLE = frozenset(
    {
        "AddPower",
        "AddToughness",
        "SetPower",
        "SetToughness",
        "AddKeyword",
        "RemoveKeyword",
        "AddType",
        "RemoveType",
        "AddSubtype",
        "SetColor",
        "AddColor",
        "GrantAbility",
        "GrantTrigger",
        "RemoveAllAbilities",
    }
)
_TAP_TAGS = frozenset({"Tap", "Untap", "TapAll", "UntapAll", "SetTapState"})
#: A token's own static P/T logs a layered effect, as do a +1/+1 counter's P/T and
#: a control change.
_TOKEN_SHOWS = frozenset({"token", "counter_add", "continuous", "move:Library->Hand"})
_LIBRARY_SHOWS = _moves(lambda a, _b: a == "Library") | {
    "draw",
    "discard",
    "counter_add",
    "reveal",
}


def phase_kind(c: ConceptNode) -> tuple[str, frozenset[str]]:
    """``(name, the Arena kinds that show it)`` for one phase effect; an empty set
    is a kind Arena logs nothing for (mana, a reveal), never scored."""
    tag = (tag_of(c.node) or "").removeprefix("T_effect__")
    con = c.concept
    if con == "deal_damage" or tag == "Fight":
        return "damage", frozenset(
            {"damage", "gain_life"}
        )  # lifelink gains as it deals
    if con in _SAME:
        return con, frozenset({con})
    if con in ("gain_control", "give_control"):  # layer 2, CR 613.1b
        return con, frozenset({"gain_control", "continuous"})
    if con in _TOKEN_MAKERS:
        return "token", _TOKEN_SHOWS
    if con == "conjure":
        # a card made in a zone (no token): Arena moves it there out of Limbo
        dest = _zone(change_zone_dirs(c.node)[1])
        return con, frozenset(f"move:Limbo->{z}" for z in ((dest,) if dest else _ZONES))
    if con in ("place_counter", "proliferate", "multiply_counter"):
        # doubling counters gives as many again (CR 701.10e)
        return "counter_add", frozenset({"counter_add", "continuous"})
    if con == "give_player_counter":  # a counter on a player (CR 122.1): poison
        return "counter_add", frozenset({"counter_add"})
    if con == "remove_counter":
        return con, frozenset({"counter_remove"})
    if con == "end_the_turn":
        # CR 724.1b: exile every object on the stack, the resolving one included
        return con, frozenset({"move:Stack->Exile"})
    if tag == "SolveCase":  # "this Case becomes solved", a designation (CR 719.3b)
        return "solve", frozenset({"marked"})
    if tag == "Intensify":  # Arena keeps a card's intensity as a designation
        return "intensify", frozenset({"designation"})
    if tag == "SetClassLevel":
        # a level gives the Class its abilities (CR 716.2a): a layered effect in
        # Arena's log for a static one, nothing for a trigger or replacement
        return "class_level", frozenset({"continuous"})
    if tag == "GenericEffect" and not _VISIBLE & {
        tag_of(n) for n in iter_typed_nodes(c.node)
    }:
        return "rule_change", frozenset()  # a permission or restriction: not logged
    if con in _CONTINUOUS or tag in _CONTINUOUS_TAGS:
        return "continuous", frozenset({"continuous"})
    if con in ("become_monarch", "venture") or tag == "BecomePrepared":
        return "designation", frozenset({"designation"})
    if con == "bounce":
        return con, frozenset({"move:Battlefield->Hand", "move:Stack->Hand"})
    if con == "change_zone":
        origin, dest = (_zone(z) for z in change_zone_dirs(c.node))
        shown = set(_moves(lambda a, b: b == dest and (origin is None or a == origin)))
        if dest == "Graveyard":
            shown |= {"sacrifice", "destroy"}
        if dest == "Exile" and origin is None:
            shown.add("counter_spell")  # a countered spell exiled instead
        if list_field(c.node, "enter_with_counters"):
            shown.add("counter_add")  # "exile it … with a stash counter on it"
        return f"move:{origin or '*'}->{dest}", frozenset(shown)
    if con in _LIBRARY_VERBS:
        return con, _LIBRARY_SHOWS
    if tag == "Counter":
        # a rider on what it counters ("that permanent loses all abilities")
        rider = _VISIBLE & {tag_of(n) for n in iter_typed_nodes(c.node)}
        return "counter_spell", frozenset(
            {"counter_spell"} | ({"continuous"} if rider else set())
        )
    if tag in _TAP_TAGS:
        return "tap_untap", frozenset({"tap_untap"})
    if tag == "PutAtLibraryPosition":
        return "move:*->Library", _moves(lambda _a, b: b == "Library")
    return f"other:{tag or con}", frozenset()


def _x_amount(c: ConceptNode, fld: str, x: ChosenX) -> int | None:
    """An effect's ``fld`` when it is an X Arena logged: the X its own spell or
    ability was cast with, or — for an amount phase reads off the X paid for a
    permanent's spell, its enters ability's (CR 107.3m) — that spell's."""
    paid = ref_qty_tag(c.node, fld) == "CostXPaid"
    sign = 1 if paid else chosen_x_sign(c.node, fld)
    if x.own is not None and sign is not None:
        return sign * x.own
    return x.spell if paid else None


def _may_be_zero(c: ConceptNode, fld: str, x: ChosenX) -> bool:
    """Whether an effect's amount can be nothing: one that scales, unless it is
    an X Arena logged (:func:`_x_amount`) and that X isn't zero."""
    return amount_is_scaling(c.node, fld) and not _x_amount(c, fld, x)


def uncertain(ability: PhaseAbility, c: ConceptNode, x: ChosenX = NO_X) -> bool:
    """Whether an effect may not happen: optional, conditional, in a branch its
    controller doesn't decide, one of two alternatives, with no target required,
    or of an amount that can be zero (``x`` is the X Arena logged, if any)."""
    root, node = ability.root, c.node
    return (
        effect_owner_optional(root, node)
        or effect_conditional(root, node)
        or in_uncertain_branch(root, node)
        or effect_targets_optional(root, node)
        or any(
            effects_exclusive(root, node, other.node)
            for other in ability.effects
            if other is not c
        )
        or _may_be_zero(c, "amount", x)
        or _may_be_zero(c, "count", x)
    )


#: Phase's kinds Arena may log nothing for even when they happen, so their
#: absence says nothing: a Class's new level shows only through a static ability
#: it gives (:func:`phase_kind`).
_MAY_LOG_NOTHING = frozenset({"class_level"})

#: One phase effect: its ability, its concept node, whether it may not happen.
_Eff = tuple[PhaseAbility, ConceptNode, bool]


def _effects(chosen: Sequence[PhaseAbility], x: ChosenX = NO_X) -> list[_Eff]:
    """Each effect of the chosen abilities, with whether it may not happen: any
    effect of one of several modes may not, nor any that follows one that may
    not in its ability (Bilbo's exile of the spell it may cast). An effect of a
    delayed trigger the ability sets up is left out: it is that trigger's
    resolution, which Arena logs by itself (Summon: Fenrir's "when you next cast
    a creature spell this turn, …")."""
    several = len(chosen) > 1
    out: list[_Eff] = []
    for a in chosen:
        before = False
        for c in a.effects:
            if effect_is_delayed(a.root, c.node):
                continue
            before = before or several or uncertain(a, c, x)
            out.append((a, c, before))
    return out


@dataclass(frozen=True)
class KindResult:
    #: ``agree`` / ``conditional`` / ``phase-extra`` / ``arena-extra``.
    status: str
    phase: tuple[str, ...]
    unexplained: tuple[str, ...]
    unseen: tuple[str, ...]


class Board(NamedTuple):
    """The permanents on the battlefield as a resolution began: how many of each
    name each side (``you`` / ``opponent``, of the resolution's controller) had,
    the resolving ability's card, and whether that card was one of them."""

    names: collections.Counter[tuple[str, str]]
    source: str | None = None
    source_present: bool = False


def _empty_group(c: ConceptNode, board: Board | None) -> bool:
    """Whether a group effect over the permanents of a name ("each other creature
    you control named Baloth Packhunter") found none on Arena's board: a group is
    every object its filter matches, no target, and may be no object at all."""
    filt = effect_filter(c.node)
    names = named_permanent_refs([filt]) if filt is not None else ()
    if board is None or not names or not acts_on_a_group(c.node):
        return False
    side = _SIDE_WORD.get(filter_controller_side(filt) or "")
    other = "Another" in filter_predicates(filt)
    for name in names:
        n = sum(
            k for (nm, s), k in board.names.items() if nm == name and side in (None, s)
        )
        if other and board.source_present and name == board.source:
            n -= 1  # "each other": not the resolving card itself
        if n > 0:
            return False
    return True


def compare_kinds(
    observed: set[str],
    chosen: Sequence[PhaseAbility],
    x: ChosenX = NO_X,
    board: Board | None = None,
) -> KindResult:
    """Arena's kinds against phase's effects. An effect that may not happen, or a
    group effect ``board`` shows had no object to act on (:func:`_empty_group`),
    is ``conditional`` when Arena logged nothing for it."""
    kinds = [
        (*phase_kind(c), maybe or _empty_group(c, board))
        for _, c, maybe in _effects(chosen, x)
    ]
    covered: set[str] = set()
    for _, shown, _ in kinds:
        covered |= shown & observed
    unexplained = tuple(sorted(observed - covered - UNSCORED))
    missing = [
        (k, maybe)
        for k, shown, maybe in kinds
        if shown and not shown & observed and k not in _MAY_LOG_NOTHING
    ]
    unseen = tuple(sorted({k for k, _ in missing}))
    if unexplained:
        status = "arena-extra"
    elif any(not maybe for _, maybe in missing):
        status = "phase-extra"
    elif missing:
        status = "conditional"
    else:
        status = "agree"
    return KindResult(status, tuple(k for k, _, _ in kinds), unexplained, unseen)


@dataclass
class Check:
    check: str
    expected: object
    observed: object
    ok: bool
    explained_by: tuple[str, ...] = ()


def _fixed_all(
    nodes: Iterable[ConceptNode], fld: str, x: ChosenX = NO_X
) -> list[int] | None:
    """Each node's known ``fld``: a fixed number, or an X Arena logged
    (:func:`_x_amount`). ``None`` when any is neither."""
    out = []
    for c in nodes:
        if has_fixed_count(c.node, fld):
            out.append(amount_factor(c.node, fld))
        elif (amount := _x_amount(c, fld, x)) is not None:
            out.append(amount)
        else:
            return None
    return out


_REACH_SIDES = {
    None: frozenset({"you"}),
    "opponents": frozenset({"opponent"}),
    "per_opponent": frozenset({"opponent"}),
    "each": frozenset({"you", "opponent"}),
}
_ANY_SIDE = frozenset({"you", "opponent"})
#: An effect's recipient that is its controller: none written, or ``Controller``.
_YOUR_RECIPIENTS = frozenset({None, "Controller"})


#: A filter's or token creator's side (``crosswalk``) → the side of the board it is.
_SIDE_WORD = {"you": "you", "opponents": "opponent"}
_GENERIC = frozenset({"Permanent", "Card"})


def _filter_types(c: ConceptNode) -> set[str]:
    filt = effect_filter(c.node)
    if filt is None:
        return set()
    return {*filter_core_types(filt), *filter_subtypes(filt)} - _GENERIC


#: A filter that names objects by what they are; any other (``ParentTarget``,
#: ``SelfRef``, ``TrackedSet`` …) names an object another effect picked out.
_OPEN_FILTER_TAGS = frozenset({"Typed", "Any"})


def _named_types(nodes: Iterable[ConceptNode]) -> set[str]:
    """The types the effects' objects can have, or none when one of them takes an
    object of any type (Heritage Reclamation's "destroy target artifact" beside
    its "exile up to one target card from a graveyard"). An effect on an object
    an earlier one named ("then return that card", "it deals 2 damage to that
    creature") adds no type of its own."""
    types: set[str] = set()
    for c in nodes:
        named = _filter_types(c)
        if not named and tag_of(effect_filter(c.node)) in _OPEN_FILTER_TAGS:
            return set()
        types |= named
    return types


def _counter_norm(name: str | None) -> str:
    name = (name or "").lower().replace("+1/+1", "p1p1").replace("-1/-1", "m1m1")
    return re.sub(r"[^a-z0-9]", "", name)


def _fits(expected: int, observed: int, *, ceiling: bool) -> bool:
    return observed <= expected if ceiling else observed == expected


@dataclass
class _Checks:
    """One resolution's strict checks: what Arena logged, and the checks so far."""

    mine: Sequence[Effect]
    controller: int | None
    counter_name: Callable[[int | None], str | None]
    #: The X Arena logged for the resolution, if any.
    x: ChosenX = NO_X
    #: The resolving object's id: the spell itself, for a move of its own.
    instance: int | None = None
    out: list[Check] = field(default_factory=list)

    def add(self, name: str, expected: object, observed: object, ok: object) -> None:
        self.out.append(Check(name, expected, observed, bool(ok)))

    def side(self, seat: int | None) -> str | None:
        if seat is None or self.controller is None:
            return None
        return "you" if seat == self.controller else "opponent"

    def sides(self, effects: Sequence[_Eff]) -> frozenset[str]:
        """The sides the effects' player reach allows: ``you`` when unmarked and
        the effect names no other player. A player named through another object
        ("its controller draws a card": Prophesied End) can be either side."""
        out: frozenset[str] = frozenset()
        for a, c, _ in effects:
            reach = effect_player_reach(a.root, c.node)
            named = recipient_tag(c.node) not in _YOUR_RECIPIENTS
            if reach is None and named:
                return _ANY_SIDE
            out |= _REACH_SIDES.get(reach, _ANY_SIDE)
        return out

    def check_sides(self, name: str, effects: Sequence[_Eff], seats: Iterable) -> None:
        sides = self.sides(effects)
        if sides != _ANY_SIDE:
            for seat in seats:
                side = self.side(seat)
                self.add(name, sorted(sides), side, side in sides)

    def logged(self, kind: str) -> list[Effect]:
        return [e for e in self.mine if kind in e.types]


def _concept(effects: Sequence[_Eff], *concepts: str) -> list[_Eff]:
    return [e for e in effects if e[1].concept in concepts]


def _damage(ctx: _Checks, effects: list[_Eff]) -> list[int]:
    nodes = _concept(effects, "deal_damage")
    damage = [
        (num(e.details, "damage") or 0, w)
        for e in ctx.logged("DamageDealt")
        for w in e.who
    ]
    values = [d for d, _ in damage]
    if not nodes or not damage:
        return values
    amounts = _fixed_all((c for _, c, _ in nodes), "amount", ctx.x)
    if amounts is not None:
        ceiling = any(maybe for _, _, maybe in nodes)
        ok = (
            all(v in amounts for v in values)
            or sum(values) == sum(amounts)  # divided as you choose
            or (ceiling and sum(values) <= sum(amounts))
        )
        ctx.add("damage amount", amounts, values, ok)
    subject = _named_types(c for _, c, _ in nodes)
    # "target player or planeswalker": the types name only the object half
    to_player = any(effect_reaches_player(c.node, a.root) for a, c, _ in nodes)
    for _, w in damage:
        if subject and "player" in w:
            expected = sorted(subject) + (["player"] if to_player else [])
            ctx.add("damage target type", expected, "player", ok=to_player)
        elif subject and w.get("card_types"):
            have = {*w["card_types"], *w.get("subtypes", ())}
            ctx.add("damage target type", sorted(subject), sorted(have), have & subject)
    reaches = {effect_player_reach(a.root, c.node) for a, c, _ in nodes}
    if reaches <= {"opponents", "per_opponent"}:  # None is "any target" for damage
        for seat in {w["player"] for _, w in damage if "player" in w}:
            side = ctx.side(seat)
            ctx.add("damaged player", "opponent", side, side == "opponent")
    return values


def _life(ctx: _Checks, effects: list[_Eff], damage: list[int]) -> None:
    damaged = {i for e in ctx.logged("DamageDealt") for i in e.affected}
    life = [
        (num(e.details, "life") or 0, w.get("player"))
        for e in ctx.logged("ModifiedLife")
        for w in e.who
    ]
    gains = [(v, p) for v, p in life if v > 0]
    losses = [(v, p) for v, p in life if v < 0 and p not in damaged]
    for concept, observed in (("gain_life", gains), ("lose_life", losses)):
        nodes = _concept(effects, concept)
        if not nodes or not observed:
            continue
        values = sorted(abs(v) for v, _ in observed)
        amounts = _fixed_all((c for _, c, _ in nodes), "amount", ctx.x)
        if amounts is not None:
            ceiling = any(maybe for _, _, maybe in nodes)
            lifelink = concept == "gain_life" and sum(values) == sum(amounts) + sum(
                damage
            )
            ok = (
                all(v in amounts for v in values)
                or (ceiling and all(v <= max(amounts) for v in values))
                or lifelink
            )
            ctx.add(f"{concept} amount", amounts, values, ok)
        ctx.check_sides(f"{concept} player", nodes, (p for _, p in observed))


def _draws(ctx: _Checks, effects: list[_Eff]) -> None:
    nodes = _concept(effects, "draw")
    draws = [
        e.zone_dest_owner
        for e in ctx.logged("ZoneTransfer")
        if word(e.details, "category") == "Draw"
    ]
    if not nodes or not draws:
        return
    amounts = _fixed_all((c for _, c, _ in nodes), "count", ctx.x)
    if amounts is not None:
        ceiling = any(maybe for _, _, maybe in nodes)
        total = sum(amounts)
        for n in collections.Counter(draws).values():
            ok = _fits(total, n, ceiling=ceiling) or n in amounts
            ctx.add("draw count", total, n, ok)
    ctx.check_sides("drawing player", nodes, set(draws))


def _tokens(ctx: _Checks, effects: list[_Eff]) -> None:
    nodes = _concept(effects, "make_token")
    tokens = [w for e in ctx.logged("TokenCreated") for w in e.who]
    if not nodes or not tokens:
        return
    amounts = _fixed_all((c for _, c, _ in nodes), "count", ctx.x)
    if amounts is not None:
        ceiling = any(maybe for _, _, maybe in nodes)
        ok = _fits(sum(amounts), len(tokens), ceiling=ceiling)
        ctx.add("token count", sum(amounts), len(tokens), ok)
    creators = {
        token_creator_side(a.unit, c.node) if a.unit is not None else None
        for a, c, _ in nodes
    }
    sides = {_SIDE_WORD.get(side) for side in creators}
    for w in tokens:
        have = {x.lower() for x in (*w.get("card_types", ()), *w.get("subtypes", ()))}
        if not have:
            continue
        fitting = [
            c for _, c, _ in nodes if {t.lower() for t in c.subject if t} <= have
        ]
        ctx.add(
            "token type", [list(c.subject) for _, c, _ in nodes], sorted(have), fitting
        )
        if None not in sides:  # every maker names its creator's side
            side = ctx.side(w.get("controller"))
            want = sorted(s for s in sides if s is not None)
            ctx.add("token controller", want, side, side in sides)


def _counter_kind(c: ConceptNode) -> str:
    if c.concept == "give_player_counter":  # a player's counter (CR 122.1)
        return player_counter_kind(c.node)
    return counter_kind(c.node)


def _counter_player_sides(a: PhaseAbility, c: ConceptNode) -> frozenset[str] | None:
    """The side of the player a player's counter goes to, where phase's parse
    fixes it: the player filter's side ("target opponent gets a poison counter"),
    or a trigger's "that player" — an opponent when the trigger watches combat
    damage a creature of yours deals to a player, which only an attacking creature
    deals, to the player it attacks (CR 510.1b), its controller's opponent (CR
    506.2)."""
    side = _SIDE_WORD.get(filter_controller_side(effect_filter(c.node)) or "")
    if side is not None:
        return frozenset({side})
    if recipient_tag(c.node) == "TriggeringPlayer" and a.unit is not None:
        if combat_damage_hits_opponent(a.unit.node):
            return frozenset({"opponent"})
        side = _SIDE_WORD.get(triggering_player_side(a.unit) or "")
        if side is not None:
            return frozenset({side})
    return None


def _counters(ctx: _Checks, effects: list[_Eff]) -> None:
    nodes = _concept(effects, "place_counter", "give_player_counter")
    added = [
        (
            _counter_norm(ctx.counter_name(num(e.details, "counter_type", None))),
            num(e.details, "transaction_amount", 1),
        )
        for e in ctx.logged("CounterAdded")
    ]
    if not nodes or not added:
        return
    kinds = {_counter_norm(_counter_kind(c)): (c, maybe) for _, c, maybe in nodes}
    players = [
        _counter_player_sides(a, c)
        for a, c, _ in nodes
        if c.concept == "give_player_counter"
    ]
    if players and None not in players:
        want = frozenset().union(*(p for p in players if p is not None))
        for e in ctx.logged("CounterAdded"):
            for w in e.who:
                if "player" in w:
                    side = ctx.side(w["player"])
                    ctx.add("counter player", sorted(want), side, side in want)
    for kind, n in added:
        ctx.add("counter type", sorted(kinds), kind, kind in kinds)
        if kind in kinds:
            c, maybe = kinds[kind]
            expected = _fixed_all([c], "count", ctx.x)
            if expected is not None and n is not None:
                ok = _fits(expected[0], n, ceiling=maybe)
                ctx.add("counter amount", expected[0], n, ok)


#: Phase's effects that change power and toughness by an amount.
_PUMP_TAGS = frozenset({"Pump", "PumpAll"})


def _pumps(ctx: _Checks, effects: list[_Eff]) -> None:
    """A pump's size against the power / toughness change Arena logged for each
    object it reached (CR 613.4c). Only where every continuous effect of the
    ability is a pump of a known size: a base-P/T set or an animation logs its
    own change beside it."""
    logged = [
        (num(e.details, "power") or 0, num(e.details, "toughness") or 0)
        for e in ctx.logged("PowerToughnessModCreated")
    ]
    continuous = [c for _, c, _ in effects if phase_kind(c)[0] == "continuous"]
    pumps = [c for c in continuous if tag_of(c.node) in _PUMP_TAGS]
    if not logged or not pumps or len(pumps) != len(continuous):
        return
    power = _fixed_all(pumps, "power", ctx.x)
    toughness = _fixed_all(pumps, "toughness", ctx.x)
    if power is None or toughness is None:
        return
    sizes = sorted(set(zip(power, toughness, strict=True)))
    for change in logged:
        ctx.add("pump amount", [list(s) for s in sizes], list(change), change in sizes)


def _control(ctx: _Checks, effects: list[_Eff]) -> None:
    """Who controls each object whose control changed, against the effect: its
    controller for "gain control of" (no recipient), the recipient's side for
    "target opponent gains control of" (``control_recipient_scope``). Arena logs
    the object as the change left it."""
    want: set[str] = set()
    for _, c, _ in _concept(effects, "gain_control", "give_control"):
        scope = control_recipient_scope(c.node)
        side = "you" if scope is None else _SIDE_WORD.get(scope)
        if side is None:
            return  # a recipient of either side ("target player")
        want.add(side)
    if not want:
        return
    for e in ctx.logged("ControllerChanged"):
        for w in e.who:
            if w.get("controller") is not None:
                side = ctx.side(w["controller"])
                ctx.add("new controller", sorted(want), side, side in want)


_MOVERS = ("change_zone", "bounce", "destroy", "sacrifice")


def _moved(ctx: _Checks, effects: list[_Eff]) -> None:
    """Each moved object's type and controller against the movers'. Not checked:
    the resolving spell moved by its own "Exile ~" (a ``SelfRef`` mover), and
    what ending the turn exiles from the stack, every object there (CR 724.1b)."""
    nodes = [c for _, c, _ in _concept(effects, *_MOVERS)]
    if not nodes:
        return
    moves_itself = any(tag_of(effect_filter(c.node)) == "SelfRef" for c in nodes)
    ends_turn = bool(_concept(effects, "end_the_turn"))
    # a moved object as it was before the move (its ObjectIdChanged has the old id)
    before = {
        num(e.details, "new_id", None): e.who[0]
        for e in ctx.logged("ObjectIdChanged")
        if e.who
    }
    subject = _named_types(nodes)
    sides = {filter_controller_side(effect_filter(c.node)) for c in nodes}
    want = (
        {"opponents": "opponent", "you": "you"}.get(next(iter(sides)))
        if len(sides) == 1
        else None
    )
    for e in ctx.logged("ZoneTransfer"):
        if word(e.details, "category") in ("Draw", "Warp", "Countered"):
            continue
        zones = (word(e.details, "zone_src"), word(e.details, "zone_dest"))
        if ends_turn and zones == ("Stack", "Exile"):
            continue
        for moved in e.who:
            w = before.get(moved.get("object"), moved)
            if (
                moves_itself
                and ctx.instance is not None
                and w.get("object") == ctx.instance
            ):
                continue
            have = {*w.get("card_types", ()), *w.get("subtypes", ())}
            if subject and w.get("card_types"):
                ctx.add(
                    "moved object type", sorted(subject), sorted(have), have & subject
                )
            if want and w.get("controller") is not None:
                side = ctx.side(w["controller"])
                ctx.add("moved object controller", want, side, side == want)


def strict_checks(
    chosen: Sequence[PhaseAbility],
    mine: Sequence[Effect],
    controller: int | None,
    *,
    counter_name: Callable[[int | None], str | None],
    x: ChosenX = NO_X,
    instance: int | None = None,
) -> list[Check]:
    """Phase's fixed facts against Arena's amounts and objects (module docstring).
    ``x`` is the X Arena logged for the resolution, if any, and ``instance`` the
    resolving object's id."""
    ctx = _Checks(mine, controller, counter_name, x, instance)
    effects = _effects(chosen, x)
    damage = _damage(ctx, effects)
    _life(ctx, effects, damage)
    _draws(ctx, effects)
    _tokens(ctx, effects)
    _counters(ctx, effects)
    _pumps(ctx, effects)
    _moved(ctx, effects)
    _control(ctx, effects)
    return ctx.out


#: A count check → the word a replacement's event carries for it.
_REPLACED_EVENT = {
    "draw count": "Draw",
    "token count": "Token",
    "counter amount": "Counter",
    "damage amount": "Damage",
    "gain_life amount": "Life",
}


def explain_excess(
    checks: Iterable[Check],
    replacements: Callable[[], Sequence[tuple[str, str]]],
) -> None:
    """Pass a count Arena exceeded when a permanent of the controller's has a
    replacement phase types for that event: ``replacements()`` gives each
    ``(card name, replacement event tag)`` on their side of the board, read once."""
    board: Sequence[tuple[str, str]] | None = None
    for c in checks:
        if c.ok or c.check not in _REPLACED_EVENT:
            continue
        observed = sum(c.observed) if isinstance(c.observed, list) else c.observed
        expected = sum(c.expected) if isinstance(c.expected, list) else c.expected
        if not (isinstance(observed, int) and isinstance(expected, int)):
            continue
        if observed <= expected:
            continue
        if board is None:
            board = replacements()
        word = _REPLACED_EVENT[c.check].lower()
        hits = tuple(sorted({n for n, tag in board if word in tag.lower()}))
        if hits:
            c.ok, c.explained_by = True, hits
