"""What a resolution did in Arena against what phase's parse of it says it does.

Two layers, both over the resolving ability's **own** effects (an annotation whose
source is another object, such as a replacement effect another permanent applies, is
set aside, not scored):

* **Kinds** (:func:`compare_kinds`): Arena's annotations and phase's effects in one
  vocabulary: damage, life, draw, a zone move by its zones, tokens, counters, a
  continuous effect. Arena doing something phase's parse doesn't predict is a finding;
  phase predicting something Arena didn't log is one only for an effect that must
  happen. An effect that may not (:func:`uncertain`: optional, in a branch the
  controller doesn't decide, up to one target, one of several modes) is
  ``conditional`` when it doesn't.
* **Strict checks** (:func:`strict_checks`): the facts phase states as fixed, checked
  against the amounts and objects Arena logged: a fixed damage, life, draw, token or
  counter amount; who drew, gained life, or controls the tokens; a token's, counter's,
  damaged object's or moved object's type; whose object moved. An amount from an
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

from mtg_utils._arena_crosscheck.align import PhaseAbility
from mtg_utils._arena_crosscheck.log import Effect, Resolution, num, word
from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    counter_kind,
    effect_conditional,
    effect_filter,
    effect_owner_optional,
    effect_player_reach,
    effect_targets_optional,
    effects_exclusive,
    filter_controller_side,
    filter_core_types,
    filter_subtypes,
    has_fixed_count,
    in_uncertain_branch,
    iter_typed_nodes,
    tag_of,
    token_creator_side,
)

__all__ = [
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
UNSCORED = frozenset({"reveal", "trigger", "warp_exile", "replaced"})

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
    "AttachmentCreated": "attach",
    "ControllerChanged": "gain_control",
    "TappedUntappedPermanent": "tap_untap",
    "RevealedCardCreated": "reveal",
    "DisqualifiedEffect": "replaced",
    "AbilityInstanceCreated": "trigger",
}


def own_effects(res: Resolution) -> tuple[list[Effect], list[Effect]]:
    """The resolution's effects split into its own (sourced by the resolving object,
    its card, a player or the game) and the rest."""
    own = {res.instance, res.parent, None, *res.seats}
    mine = [e for e in res.effects if e.affector in own]
    rest = [e for e in res.effects if e.affector not in own]
    return mine, rest


def arena_kinds(effects: Iterable[Effect]) -> set[str]:
    effects = list(effects)
    damaged = {i for e in effects if "DamageDealt" in e.types for i in e.affected}
    kinds: set[str] = set()
    for e in effects:
        t = set(e.types)
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
        "conjure",
    }
)
_CONTINUOUS = frozenset(
    {"pump", "set_pt", "grant_keyword", "add_type", "goad", "phasing"}
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
    if con == "gain_control":
        return con, frozenset({con, "continuous"})
    if con in _TOKEN_MAKERS:
        return "token", _TOKEN_SHOWS
    if con in ("place_counter", "proliferate"):
        return "counter_add", frozenset({"counter_add", "continuous"})
    if con == "remove_counter":
        return con, frozenset({"counter_remove"})
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
        return f"move:{origin or '*'}->{dest}", frozenset(shown)
    if con in _LIBRARY_VERBS:
        return con, _LIBRARY_SHOWS
    if tag == "Counter":
        return "counter_spell", frozenset({"counter_spell"})
    if tag in _TAP_TAGS:
        return "tap_untap", frozenset({"tap_untap"})
    if tag == "PutAtLibraryPosition":
        return "move:*->Library", _moves(lambda _a, b: b == "Library")
    return f"other:{tag or con}", frozenset()


def uncertain(ability: PhaseAbility, c: ConceptNode) -> bool:
    """Whether an effect may not happen: optional, conditional, in a branch its
    controller doesn't decide, one of two alternatives, with no target required,
    or of an amount that can be zero."""
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
        or amount_is_scaling(node, "amount")
        or amount_is_scaling(node, "count")
    )


#: One phase effect: its ability, its concept node, whether it may not happen.
_Eff = tuple[PhaseAbility, ConceptNode, bool]


def _effects(chosen: Sequence[PhaseAbility]) -> list[_Eff]:
    """Each effect of the chosen abilities, with whether it may not happen: any
    effect of one of several modes may not, nor any that follows one that may
    not in its ability (Bilbo's exile of the spell it may cast)."""
    several = len(chosen) > 1
    out: list[_Eff] = []
    for a in chosen:
        before = False
        for c in a.effects:
            before = before or several or uncertain(a, c)
            out.append((a, c, before))
    return out


@dataclass(frozen=True)
class KindResult:
    #: ``agree`` / ``conditional`` / ``phase-extra`` / ``arena-extra``.
    status: str
    phase: tuple[str, ...]
    unexplained: tuple[str, ...]
    unseen: tuple[str, ...]


def compare_kinds(observed: set[str], chosen: Sequence[PhaseAbility]) -> KindResult:
    kinds = [(*phase_kind(c), maybe) for _, c, maybe in _effects(chosen)]
    covered: set[str] = set()
    for _, shown, _ in kinds:
        covered |= shown & observed
    unexplained = tuple(sorted(observed - covered - UNSCORED))
    missing = [
        (k, maybe) for k, shown, maybe in kinds if shown and not shown & observed
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


def _fixed_all(nodes: Iterable[ConceptNode], fld: str) -> list[int] | None:
    """Each node's fixed ``fld``, or ``None`` when any isn't fixed."""
    out = []
    for c in nodes:
        if not has_fixed_count(c.node, fld):
            return None
        out.append(amount_factor(c.node, fld))
    return out


_REACH_SIDES = {
    None: frozenset({"you"}),
    "opponents": frozenset({"opponent"}),
    "per_opponent": frozenset({"opponent"}),
    "each": frozenset({"you", "opponent"}),
}
_ANY_SIDE = frozenset({"you", "opponent"})
#: A filter's or token creator's side (``crosswalk``) → the side of the board it is.
_SIDE_WORD = {"you": "you", "opponents": "opponent"}
_GENERIC = frozenset({"Permanent", "Card"})


def _filter_types(c: ConceptNode) -> set[str]:
    filt = effect_filter(c.node)
    if filt is None:
        return set()
    return {*filter_core_types(filt), *filter_subtypes(filt)} - _GENERIC


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
    out: list[Check] = field(default_factory=list)

    def add(self, name: str, expected: object, observed: object, ok: object) -> None:
        self.out.append(Check(name, expected, observed, bool(ok)))

    def side(self, seat: int | None) -> str | None:
        if seat is None or self.controller is None:
            return None
        return "you" if seat == self.controller else "opponent"

    def sides(self, effects: Sequence[_Eff]) -> frozenset[str]:
        """The sides the effects' player reach allows (``you`` when unmarked)."""
        reaches = [effect_player_reach(a.root, c.node) for a, c, _ in effects]
        return frozenset().union(*(_REACH_SIDES.get(r, _ANY_SIDE) for r in reaches))

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
    amounts = _fixed_all((c for _, c, _ in nodes), "amount")
    if amounts is not None:
        ceiling = any(maybe for _, _, maybe in nodes)
        ok = (
            all(v in amounts for v in values)
            or sum(values) == sum(amounts)  # divided as you choose
            or (ceiling and sum(values) <= sum(amounts))
        )
        ctx.add("damage amount", amounts, values, ok)
    subject = set().union(*(_filter_types(c) for _, c, _ in nodes))
    for _, w in damage:
        if subject and "player" in w:
            ctx.add("damage target type", sorted(subject), "player", ok=False)
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
        amounts = _fixed_all((c for _, c, _ in nodes), "amount")
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
    amounts = _fixed_all((c for _, c, _ in nodes), "count")
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
    amounts = _fixed_all((c for _, c, _ in nodes), "count")
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


def _counters(ctx: _Checks, effects: list[_Eff]) -> None:
    nodes = _concept(effects, "place_counter")
    added = [
        (
            _counter_norm(ctx.counter_name(num(e.details, "counter_type", None))),
            num(e.details, "transaction_amount", 1),
        )
        for e in ctx.logged("CounterAdded")
    ]
    if not nodes or not added:
        return
    kinds = {_counter_norm(counter_kind(c.node)): (c, maybe) for _, c, maybe in nodes}
    for kind, n in added:
        ctx.add("counter type", sorted(kinds), kind, kind in kinds)
        if kind in kinds:
            c, maybe = kinds[kind]
            expected = _fixed_all([c], "count")
            if expected is not None and n is not None:
                ok = _fits(expected[0], n, ceiling=maybe)
                ctx.add("counter amount", expected[0], n, ok)


_MOVERS = ("change_zone", "bounce", "destroy", "sacrifice")


def _moved(ctx: _Checks, effects: list[_Eff]) -> None:
    nodes = [c for _, c, _ in _concept(effects, *_MOVERS)]
    if not nodes:
        return
    # a moved object as it was before the move (its ObjectIdChanged has the old id)
    before = {
        num(e.details, "new_id", None): e.who[0]
        for e in ctx.logged("ObjectIdChanged")
        if e.who
    }
    subject = set().union(*(_filter_types(c) for c in nodes))
    sides = {filter_controller_side(effect_filter(c.node)) for c in nodes}
    want = (
        {"opponents": "opponent", "you": "you"}.get(next(iter(sides)))
        if len(sides) == 1
        else None
    )
    for e in ctx.logged("ZoneTransfer"):
        if word(e.details, "category") in ("Draw", "Warp", "Countered"):
            continue
        for moved in e.who:
            w = before.get(moved.get("object"), moved)
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
) -> list[Check]:
    """Phase's fixed facts against Arena's amounts and objects (module docstring)."""
    ctx = _Checks(mine, controller, counter_name)
    effects = _effects(chosen)
    damage = _damage(ctx, effects)
    _life(ctx, effects, damage)
    _draws(ctx, effects)
    _tokens(ctx, effects)
    _counters(ctx, effects)
    _moved(ctx, effects)
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
