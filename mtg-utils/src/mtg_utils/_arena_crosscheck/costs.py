"""The costs in Arena's legal-action lists against phase's parse (ADR-0064).

Arena lists each player's legal actions in its game states (``actions``: an
``actionType``, the object, ``abilityGrpId``, ``alternativeGrpId``, the
``manaCost`` it would charge). The reader keeps the log's own player's (the
seats ``ActionsAvailableReq`` asks; an opponent's actions are listed only for
their public objects, and their hidden cards never) once per game and cost
(``log.Offer``). Three checks, by kind:

* **spell cost**: a cast's mana cost against the card's (or the face's)
  printed mana cost, plus commander tax (CR 903.8: {2} for each earlier cast
  from the command zone this game), plus each fixed cost change phase types
  that applies (a ``ModifyCost`` static of the card itself with no condition
  and no count, or of a permanent on the battlefield whose spell filter the
  strict filter read matches: CR 601.2f);
* **ability cost**: an activation's mana cost against the mana cost of the
  phase ability it pairs with (``align.pair``);
* **alternative**: an alternative way to cast that Arena offers by a keyword
  (its ``alternativeGrpId``'s ``BaseId``: flashback, escape, evoke, warp,
  dash, sneak, harmonize …) against the alternative costs phase reads off
  the card (``ConceptTree.card_alt_costs``), and its mana cost against
  phase's where both are mana alone.

A cost that differs is a finding only when nothing the log can't show could
explain it; otherwise the row names the reason (:data:`COST_STATUSES`).
"""

from __future__ import annotations

import collections
import re
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, cast

from mtg_utils._arena_crosscheck.align import PhaseAbility, pair
from mtg_utils._arena_crosscheck.amounts import CountBoard, evaluate
from mtg_utils._arena_crosscheck.log import ObjectEvent, Offer, Permanent, Resolution
from mtg_utils._card_ir.crosswalk import (
    ConceptTree,
    LoggedObject,
    ObjectFacts,
    cost_symbols,
    filter_admits,
    filter_controller_side,
    modify_cost_mode,
    modify_cost_spell_filter,
    next_spell_discount,
    static_mode_field,
    tag_of,
)
from mtg_utils._card_ir.mirror import TypedMirrorNode

if TYPE_CHECKING:
    from mtg_utils.arena_card_db import CardText

__all__ = ["COST_STATUSES", "CostChecker"]

#: The costs check's statuses (a row's ``status``).
COST_STATUSES: dict[str, str] = {
    "agree": "Arena's cost is phase's, compared",
    "kind-only": "the alternative is on both sides; its cost wasn't compared (one "
    "of them isn't mana alone, or Arena lists none)",
    "rebalanced": "a rebalanced (A-) card: Arena prices it its own way",
    "tax-unknown": "a commander cast whose earlier casts this log may not hold "
    "(the log begins after the game's first turn)",
    "earlier-reduction": "Arena's price is lower than phase's and its player "
    "resolved earlier that turn an ability that may make a one-shot discount "
    "on a later spell ('the next spell you cast this turn costs {N} less': "
    "phase's ReduceNextSpellCost, or a clause it parked; Peerless Samurai)",
    "cost-mismatch": "the finding: Arena's cost differs and nothing the log "
    "can't show explains it",
    "alternative-unknown": "the finding: Arena offers an alternative by a "
    "keyword phase reads no alternative cost for",
    "cost-modified": "a cost change phase types that this read can't evaluate "
    "(a condition, a count), or a card keyword that changes a cost (affinity, "
    "undaunted, convoke, delve, improvise, …) applies",
    "unparsed-source": "a permanent on the battlefield phase has no parse of "
    "could change the cost",
    "payment-choice": "a mana symbol this read doesn't compare (Phyrexian, snow)",
    "no-card": "the object's card isn't known",
    "no-phase-parse": "phase has no parse of the card",
    "unpaired": "the ability pairs with no phase ability confidently",
    "permission": "another object's ability lets it be cast (its "
    "sourceId): it may change what is paid ('mana of any type can be spent')",
    "unkeyed-alternative": "an alternative Arena offers by no keyword (a "
    "spell's own 'you may … rather than pay', or one another effect grants: "
    "'Cast without paying mana cost')",
}

#: Arena's mana colors → the printed symbol letters.
_LETTERS = {
    "White": "W",
    "Blue": "U",
    "Black": "B",
    "Red": "R",
    "Green": "G",
    "Colorless": "C",
    "X": "X",
}
#: Card keywords that change what a cast costs, or how it is paid, which this
#: read doesn't evaluate: affinity (CR 702.41a), undaunted (702.125a), convoke
#: (702.51a), delve (702.66a), improvise (702.126a), assist (702.132a).
_COST_KEYWORDS = frozenset(
    {"affinity", "undaunted", "convoke", "delve", "improvise", "assist"}
)
_SYMBOL = re.compile(r"\{([^}]+)\}")


class Cost(collections.Counter):
    """A mana cost as a multiset: ``"generic"`` counts generic mana, each
    other key a symbol (``"W"``, ``"X"``, a hybrid ``"R/W"`` with its halves
    sorted)."""

    def text(self) -> str:
        out = f"{{{self['generic']}}}" if self["generic"] else ""
        return out + "".join(
            f"{{{k}}}" for k in sorted(self.elements()) if k != "generic"
        )


def arena_cost(mana: Iterable[tuple[tuple[str, ...], int]]) -> Cost | None:
    """Arena's ``manaCost`` as a :class:`Cost`; ``None`` for a color this read
    doesn't know."""
    out = Cost()
    for colors, count in mana:
        if colors == ("Generic",):
            out["generic"] += count
            continue
        letters = [_LETTERS.get(c) for c in colors]
        if None in letters:
            return None
        out["/".join(sorted(x for x in letters if x))] += count
    return out


def printed_cost(text: str | None) -> Cost | None:
    """A printed mana cost (``"{2}{R/W}{X}"``) as a :class:`Cost`; ``None``
    for a symbol this read doesn't compare (Phyrexian, snow)."""
    out = Cost()
    for raw in _SYMBOL.findall(text or ""):
        sym = raw.upper()
        if sym.isdigit():
            out["generic"] += int(sym)
            continue
        parts = sym.split("/")
        if "P" in parts or "S" in parts:
            return None
        if parts[0].isdigit():  # a {2/W}: its generic half
            return None
        out["/".join(sorted(parts))] += 1
    return out


def _change(mode: str, amount: object, cost: Cost) -> Cost | None:
    """``cost`` with a fixed ``ModifyCost`` amount applied (CR 601.2f: a
    reduction takes generic mana only down to zero), or ``None`` for an
    amount this read can't apply."""
    change = printed_cost(cost_symbols(amount)) if tag_of(amount) == "Cost" else None
    if change is None:
        return None
    out = Cost(cost)
    if mode == "Raise":
        out.update(change)
        return out
    if mode != "Reduce" or set(change) - {"generic"}:
        return None  # a colored reduction: which symbol it takes, unread
    out["generic"] = max(0, out["generic"] - change["generic"])
    return out


def _mana_part(cost: object) -> object | None:
    """The mana cost inside an ability's cost (``Mana``, or one part of a
    ``Composite``), ``None`` for none."""
    if tag_of(cost) == "Mana":
        return getattr(cost, "cost", None)
    if tag_of(cost) == "Composite":
        parts = [_mana_part(c) for c in getattr(cost, "costs", ()) or ()]
        found = [p for p in parts if p is not None]
        return found[0] if len(found) == 1 else None
    return None


class CostChecker:
    """The costs check over one log set (module docstring)."""

    def __init__(
        self,
        text: CardText,
        card_of: Callable[[str], dict | None],
        trees_of: Callable[[dict], Sequence[ConceptTree]],
        abilities_of: Callable[[str], Sequence[PhaseAbility] | None],
    ) -> None:
        self.text = text
        self._card_of = card_of
        self._trees_of = trees_of
        self._abilities_of = abilities_of
        self._trees: dict[str, tuple[ConceptTree, ...]] = {}
        #: phase's alternative cost kinds Arena never offered for a card it
        #: offered the log's player to cast in a game, by kind: counted, no
        #: finding (an alternative Arena doesn't list may be one the moment
        #: doesn't allow: a graveyard's flashback while the card is in hand)
        self.never_offered: collections.Counter = collections.Counter()

    def trees(self, name: str | None) -> tuple[ConceptTree, ...]:
        if name is None:
            return ()
        if name not in self._trees:
            record = self._card_of(name)
            self._trees[name] = tuple(self._trees_of(record)) if record else ()
        return self._trees[name]

    def rows(
        self,
        offers: Sequence[Offer],
        local: dict[tuple[str, int], frozenset[int]],
        events: Sequence[ObjectEvent],
        resolutions: Sequence[Resolution] = (),
        first_turns: dict[tuple[str, int], int] | None = None,
    ) -> list[dict]:
        """One row per distinct local action Arena offered (module docstring)."""
        self._resolved = collections.defaultdict(list)
        for r in resolutions:
            if self._discounts(r):
                self._resolved[(r.game, r.turn, r.controller)].append(r.message)
        self._first_turns = first_turns or {}
        command_casts: dict[tuple, list[int]] = collections.defaultdict(list)
        for e in events:
            if e.event == "cast_spell" and e.origin == "Command":
                card = self.text.card(e.grpid)
                command_casts[(e.game, card.paper_name if card else None)].append(
                    e.message
                )
        out = []
        offered: dict[tuple, set[str]] = collections.defaultdict(set)
        for o in offers:
            if o.seat not in local.get(o.game, ()):
                continue  # another player's actions
            if o.kind == "Cast":
                alt = self.text.ability(o.alternative) if o.alternative else None
                offered[(o.game, self._name(o.grpid))].add(
                    ((alt.keyword if alt else "") or "").lower().replace(" ", "")
                )
            card = self.text.card(o.grpid)
            name = card.paper_name if card else None
            if card is not None and card.token:
                continue  # a token's ability has no card to look up
            if card is not None and card.rebalanced:
                kinds = {"Activate": "ability cost", "Cast": "spell cost"}
                kind = "alternative" if o.alternative else kinds.get(o.kind)
                if kind:
                    out.append(
                        {
                            "game": list(o.game),
                            "turn": o.turn,
                            "card": name,
                            "arena_cost": c.text()
                            if (c := arena_cost(o.mana))
                            else None,
                            "kind": kind,
                            "status": "rebalanced",
                        }
                    )
                continue
            row: dict = {
                "game": list(o.game),
                "turn": o.turn,
                "card": name,
                "arena_cost": (c.text() if (c := arena_cost(o.mana)) else None),
            }
            if o.kind == "Activate":
                row.update(kind="ability cost", **self._ability(o, name))
            elif o.kind == "Cast" and o.alternative is not None:
                row.update(kind="alternative", **self._alternative(o, name))
            elif o.kind == "Cast" and o.source not in (None, o.instance):
                # another object's permission casts it (and may say how it is
                # paid: "mana of any type can be spent")
                row.update(kind="spell cost", status="permission")
            elif o.kind == "Cast":
                taxed = len(
                    [m for m in command_casts.get((o.game, name), ()) if m < o.message]
                )
                row.update(kind="spell cost", **self._spell(o, name, taxed))
            else:
                continue
            if row.get("skip"):
                continue
            out.append(row)
        for (_game, name), kinds in offered.items():
            for alt in {a for t in self.trees(name) for a in t.card_alt_costs}:
                folded = alt.kind.replace(" ", "")
                if alt.cost_kind == "alternative" and folded not in kinds:
                    self.never_offered[alt.kind] += 1
        return out

    # -- spell costs ------------------------------------------------------
    def _spell(self, o: Offer, name: str | None, taxed: int) -> dict:
        record = self._card_of(name) if name else None
        if record is None:
            return {"status": "no-card"}
        face = next(
            (f for f in record.get("card_faces") or () if f.get("name") == name),
            record,
        )
        printed = printed_cost(face.get("mana_cost"))
        arena = arena_cost(o.mana)
        if not face.get("mana_cost") and not o.mana:
            return {"skip": True}
        if printed is None or arena is None:
            return {"status": "payment-choice"}
        base = Cost(printed)
        if o.zone == "Command" and taxed:
            base["generic"] += 2 * taxed  # commander tax, CR 903.8
        expected, applied, unread = self._expected(o, name, base)
        out = {
            "phase_cost": expected.text(),
            "printed": face.get("mana_cost"),
            "tax": 2 * taxed if o.zone == "Command" else 0,
            "changed_by": applied,
        }
        keywords = {k.lower() for k in record.get("keywords") or ()}
        status = self._verdict(o, arena, expected, unread, keywords)
        if (
            status == "cost-mismatch"
            and o.zone == "Command"
            and self._first_turns.get(o.game, 0) > 1
        ):
            status = "tax-unknown"  # its earlier casts may be before this log
        return {**out, "status": status}

    def _verdict(
        self,
        o: Offer,
        arena: Cost,
        expected: Cost,
        unread: Sequence[str],
        keywords: frozenset[str] | set[str] = frozenset(),
    ) -> str:
        """``agree``, or why a cost that differs is no finding, or the
        finding."""
        if arena == expected:
            return "agree"
        if unread or keywords & _COST_KEYWORDS or o.modified_cost:
            return "cost-modified"
        if _cheaper(arena, expected) and any(
            m <= o.message for m in self._resolved.get((o.game, o.turn, o.seat), ())
        ):
            return "earlier-reduction"
        if any(not self.trees(self._name(p.grpid)) for p in o.permanents):
            return "unparsed-source"
        return "cost-mismatch"

    def _discounts(self, r: Resolution) -> bool:
        """Whether the resolution may make a one-shot discount on a later
        spell (``crosswalk.next_spell_discount``): the phase ability it pairs
        with (a spell's every ability), or its card's when it pairs with
        none, holds one or a clause phase parked."""
        name = self._name(r.source_grpid)
        abilities = self._abilities_of(name) if name else None
        if not abilities:
            return False
        chosen = [a for a in abilities if a.kind == "Spell"]
        if r.kind == "ability":
            ability = self.text.ability(r.grpid)
            paired = pair(
                ability.text,
                abilities,
                keyword=ability.keyword,
                numeral=ability.numeral,
            ).ability
            chosen = [paired] if paired is not None else list(abilities)
        return any(
            a.unit is not None and next_spell_discount(a.unit.node) for a in chosen
        )

    def _name(self, grp: int | None) -> str | None:
        card = self.text.card(grp)
        return card.paper_name if card else None

    def _cost_changes(
        self, o: Offer, name: str | None
    ) -> tuple[list[tuple[str, object, str]], list[str]]:
        """The fixed cost changes phase types that apply to the cast, with
        their sources, and the sources of any that apply (or may) that this
        read can't evaluate: the card's own (its spell filter read too:
        Mystical Dispute's "if it targets a blue spell" is a filter the log
        can't show) and each permanent's on the battlefield."""
        changes: list[tuple[str, object, str]] = []
        unread: list[str] = []
        sources: list[tuple[str | None, int | None, bool]] = [(name, o.seat, True)]
        sources += [(self._name(p.grpid), p.controller, False) for p in o.permanents]
        for source, controller, own in sources:
            for tree in self.trees(source):
                for unit in tree.units:
                    for sdef in unit.static_defs():
                        mode = modify_cost_mode(sdef)
                        affected = getattr(sdef, "affected", None)
                        if mode is None or (tag_of(affected) == "SelfRef") != own:
                            continue
                        applies = _applies(sdef, affected, controller, o.seat, o.facts)
                        if applies is False:
                            continue
                        if applies and _fixed(sdef):
                            amount = static_mode_field(sdef, "amount")
                            changes.append((mode, amount, source or "?"))
                        else:
                            unread.append(source or "?")
        return changes, unread

    def _expected(
        self, o: Offer, name: str | None, base: Cost
    ) -> tuple[Cost, list[str], list[str]]:
        """``base`` with the cost changes that apply (:meth:`_cost_changes`),
        their sources, and the sources this read can't evaluate."""
        expected = Cost(base)
        changes, unread = self._cost_changes(o, name)
        for mode, amount, source in changes:
            changed = _change(mode, amount, expected)
            if changed is None:
                unread.append(source)
                continue
            expected = changed
        return expected, [s for *_, s in changes], unread

    # -- ability costs ----------------------------------------------------
    def _ability(self, o: Offer, name: str | None) -> dict:
        ability = self.text.ability(o.ability)
        abilities = self._abilities_of(name) if name else None
        if abilities is None:
            return {"status": "no-phase-parse"}
        arena = arena_cost(o.mana)
        pairing = pair(
            ability.text,
            abilities,
            keyword=ability.keyword,
            numeral=ability.numeral,
            keep=lambda a: a.origin == "ability",
        )
        phase = pairing.ability
        cost = getattr(phase.unit.node, "cost", None) if phase and phase.unit else None
        mana = _mana_part(cost)
        expected = printed_cost(cost_symbols(mana)) if mana is not None else Cost()
        if not o.mana and not expected:
            return {"skip": True}  # no mana on either side: nothing to compare
        out = {"arena_text": ability.text, "phase_text": phase.desc if phase else None}
        if phase is None:
            return {**out, "status": "unpaired"}
        if arena is None or expected is None:
            return {**out, "status": "payment-choice"}
        node = phase.unit.node if phase.unit else None
        reduction = getattr(node, "cost_reduction", None)
        reduced = isinstance(reduction, TypedMirrorNode)
        if reduced:
            # "This ability costs {1} less to activate for each legendary
            # creature you control" (CR 602.2b): a count on the board as the
            # action is listed, with no condition (``amounts``)
            less = _reduction(reduction, o)
            if less is not None:
                expected = Cost(expected)
                expected["generic"] = max(0, expected["generic"] - less)
                reduced = False
        out["phase_cost"] = expected.text()
        if arena == expected:
            return {**out, "status": "agree"}
        if reduced or any(
            _changes_abilities(t)
            for p in o.permanents
            for t in self.trees(self._name(p.grpid))
        ):
            return {**out, "status": "cost-modified"}
        if any(not self.trees(self._name(p.grpid)) for p in o.permanents):
            return {**out, "status": "unparsed-source"}
        return {**out, "status": "cost-mismatch"}

    # -- alternatives ------------------------------------------------------
    def _alternative(self, o: Offer, name: str | None) -> dict:
        ability = self.text.ability(o.alternative)
        out = {"arena_text": ability.text, "alternative": ability.keyword}
        if not ability.keyword:
            return {**out, "status": "unkeyed-alternative"}
        trees = self.trees(name)
        if not trees:
            return {**out, "status": "no-phase-parse"}
        kind = ability.keyword.lower().replace(" ", "")
        alts = [a for t in trees for a in t.card_alt_costs]
        found = [a for a in alts if a.kind.replace(" ", "") == kind]
        if not found:
            return {**out, "status": "alternative-unknown"}
        phase = printed_cost(found[0].cost) if _ONLY_MANA.match(found[0].cost) else None
        arena = arena_cost(o.mana)
        if phase is not None and arena is not None and o.mana:
            expected, applied, unread = self._expected(o, name, phase)
            return {
                **out,
                "phase_cost": expected.text(),
                "changed_by": applied,
                "status": self._verdict(o, arena, expected, unread),
            }
        return {**out, "phase_cost": found[0].cost, "status": "kind-only"}


def _reduction(reduction: object, o: Offer) -> int | None:
    """An activated ability's own ``cost_reduction`` evaluated on the board
    the action was listed with: ``amount_per`` times its count, when it has
    no condition and the count is one the log shows (``amounts``)."""
    per = getattr(reduction, "amount_per", None)
    condition = getattr(reduction, "condition", None)
    if not isinstance(per, int) or isinstance(condition, TypedMirrorNode):
        return None
    board = CountBoard(
        o.permanents,
        (),
        o.seat,
        frozenset(p.controller for p in o.permanents if p.controller is not None),
        o.instance,
        frozenset(),
    )
    count = evaluate(reduction, "count", board)
    return per * count if isinstance(count, int) else None


def _cheaper(arena: Cost, expected: Cost) -> bool:
    """Whether Arena's cost is phase's less something: no symbol more, and
    less in all."""
    return all(arena[k] <= expected[k] for k in arena) and sum(arena.values()) < sum(
        expected.values()
    )


#: A printed cost of mana symbols alone.
_ONLY_MANA = re.compile(r"^(\{[^}]+\})+$")


def _fixed(sdef: object) -> bool:
    """Whether a ``ModifyCost`` static changes a cost by a fixed amount with
    no condition and no count."""
    amount = static_mode_field(sdef, "amount")
    return (
        getattr(sdef, "condition", None) is None
        and static_mode_field(sdef, "dynamic_count") is None
        and tag_of(amount) == "Cost"
    )


def _applies(
    sdef: object,
    affected: object,
    controller: int | None,
    caster: int | None,
    facts: Permanent | None,
) -> bool | None:
    """Whether a ``ModifyCost`` static applies to the spell being cast: its
    caster on the side the static names (relative to the static's
    controller) and its spell filter matching the spell as logged; ``None``
    when the log can't say."""
    side = filter_controller_side(affected)
    caster_side = "you" if caster == controller else "opponents"
    if side is not None and side != caster_side:
        return False
    spell = modify_cost_spell_filter(cast("TypedMirrorNode", sdef))
    if spell is None:
        return True
    if facts is None:
        return None
    logged = LoggedObject(
        is_source=False,
        token=False,
        controller_side=caster_side,
        owner_side=caster_side,
    )
    return filter_admits(
        spell,
        ObjectFacts(
            types=frozenset(facts.card_types),
            subtypes=frozenset(facts.subtypes),
            supertypes=frozenset(facts.supertypes),
            colors=frozenset(facts.colors),
        ),
        logged,
    )


def _changes_abilities(tree: ConceptTree) -> bool:
    """Whether a card's static changes what activated abilities cost."""
    for unit in tree.units:
        for sdef in unit.static_defs():
            mode = str(tag_of(getattr(sdef, "mode", None)) or "")
            mode += str(getattr(getattr(sdef, "mode", None), "key", "") or "")
            if ("Cost" in mode and "Activ" in mode) or "AbilityCost" in mode:
                return True
    return False
