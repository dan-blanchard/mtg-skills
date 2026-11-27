"""The mana a deck pays to cast a card on curve — its printed mana value, or a cheaper
unconditional alternative cost read off phase's keywords (``ConceptTree.
card_curve_costs``: warp, evoke, dash, blitz, prototype, impending). Suspend and
plot pay now and cast later, so they keep the printed value.

The tuner's curve, shape and efficiency read it: Anticausal Vestige (MV 6, warp {4})
plays as a 4-drop. A card phase hasn't parsed keeps its printed mana value.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils.commander_cost import SelfDiscount


def effective_mana_value(card: Mapping) -> float:
    """The printed mana value, or the cheapest curve alternative cost below it."""
    printed = float(card.get("cmc") or 0)
    costs = [c for tree in trees_for(dict(card)) for c in tree.card_curve_costs]
    return min([printed, *map(float, costs)])


#: What an X in a mana cost is worth when the cost a card is cast for is
#: estimated: an X spell is cast for value at X ≥ 3 (Martial Coup wants five,
#: Comet Storm three), where its printed mana value counts X as 0 (CR 202.3e).
#: The lane's own call; the tuner's mana-value bands read the same number.
X_COST_VALUE = 3.0

#: The keywords whose share of a spell's cost no fixed number states: convoke
#: (CR 702.51a), delve (702.66a) and improvise (702.126a) let tapped creatures,
#: exiled cards or tapped artifacts pay "rather than pay" that mana; affinity
#: (702.41a) costs {1} less "for each [text] you control"; emerge (702.119a) is
#: an alternative cost, reduced by the sacrificed creature's mana value. Such a
#: card counts at what THIS deck feeds it (:func:`self_paid_cost`), at its
#: printed cost where the deck feeds it nothing (Dan's decision, 2026-11-27).
SELF_PAYING_KEYWORDS = frozenset(
    {"Affinity", "Convoke", "Delve", "Emerge", "Improvise"}
)

#: The deck cards that fill its own graveyard (a self-mill, a discard outlet)
#: a delve card's graveyard needs before it counts as one that fills: two, the
#: floor the curve cap's cheat waiver holds its plans to (``curve_cap.
#: CHEAT_FLOOR``). The graveyard is no battlefield population, so the ADR-0044
#: estimator can't price it; a filled graveyard pays every generic mana.
GRAVEYARD_FILL_FLOOR = 2

#: Casting face down for {3} rather than its mana cost: morph (CR 702.37a), its
#: megamorph variant, and disguise (702.168a).
FACE_DOWN_KEYWORDS = frozenset({"Morph", "Megamorph", "Disguise"})
#: What a face-down cast pays (CR 702.37a, 702.168a).
FACE_DOWN_COST = 3.0

#: The opponents an undaunted card counts: "This spell costs {1} less to cast for
#: each opponent you have" (CR 702.125a), in a four-player Commander pod.
POD_OPPONENTS = 3


@dataclass(frozen=True)
class CastCosts:
    """What a card costs on the tuner's curve cap (ADR-0066): ``cheapest``, the
    cheapest mode it can be cast in (None: never capped), and ``top``, the cost
    the deck pays for its big mode when the card stands in the deck (None: left
    out of the deck's top end, as a card whose printed cost nobody pays)."""

    cheapest: float | None
    top: float | None


def _face_cost(mana_cost: str | None) -> float | None:
    from mtg_utils._card_ir.crosswalk.cost_text import mana_value_of_cost

    value = mana_value_of_cost(mana_cost or "")
    if value is None:
        return None
    return value + (X_COST_VALUE if "{X}" in (mana_cost or "") else 0.0)


def _population(words: Sequence[str]) -> SelfDiscount:
    from mtg_utils.commander_cost import SelfDiscount

    return SelfDiscount("count", None, 1, tuple(w.lower() for w in words), (), ())


def _token_kinds(card: Mapping) -> tuple[frozenset[str], ...]:
    """The type words of each token the card makes under your control (its
    ``make_token`` concepts, ``crosswalk.token_creator_side``): Raise the
    Alarm's Soldier creatures, Smothering Tithe's Treasure artifacts. A token a
    keyword action makes without a ``make_token`` (investigate's Clue) is not
    read."""
    from mtg_utils._card_ir.crosswalk import token_creator_side

    out: list[frozenset[str]] = []
    for tree in trees_for(dict(card))[:1]:
        for unit in tree.units:
            for c in unit.effect_concepts("make_token"):
                if c.scope == "you" and token_creator_side(unit, c.node) == "you":
                    out.append(frozenset(w.lower() for w in c.subject))
    return tuple(out)


def _payers(
    deck_entries: Sequence[tuple[Mapping, int]], words: Sequence[str]
) -> list[tuple[Mapping, int]]:
    """``deck_entries`` with each card that makes a token of ``words`` also
    standing in as one such permanent, cast at its own mana value (a creature
    making creature tokens is two bodies): one payer per maker card, the
    builder's conservative count of a token deck's tapped tokens (one token,
    though a maker may make many, and not before the maker is cast)."""
    want = {w.lower() for w in words}
    extra = []
    for rec, qty in deck_entries:
        if qty <= 0:
            continue
        if any(want <= kind for kind in _token_kinds(rec)):
            extra.append(({**rec, "type_line": " ".join(sorted(want))}, qty))
    return [*deck_entries, *extra]


def self_paid_cost(
    card: Mapping,
    deck_entries: Sequence[tuple[Mapping, int]],
    *,
    library_size: int,
    graveyard_fillers: int = 0,
) -> float:
    """What a self-paying card (:data:`SELF_PAYING_KEYWORDS`) costs in this deck:
    the least of its printed cost and what each keyword the deck feeds leaves.
    Dan's decision (2026-11-27) is that the deck's feed sets the cost; how it is
    read is the builder's (ADR-0066):

    - Convoke, improvise and affinity: the ADR-0044 estimator's affordable turn
      (``commander_cost.affordable_turn``), with the deck's own creature cards
      (convoke), artifact cards (improvise; affinity for artifacts) or cards of
      the affinity's quality as the population, one generic mana each and never
      below the colored pips: affinity takes off generic mana only (CR 702.41a,
      118.7a) and improvise pays generic mana only (CR 702.126a); a convoke
      creature can pay a pip of its own color (CR 702.51a), so for convoke the
      floor is the builder's cautious choice. A card making a token of the kind
      counts as one more (:func:`_payers`). The card itself, on the stack, is
      not one of them.
    - Delve: its colored pips where :data:`GRAVEYARD_FILL_FLOOR` of the deck's
      cards fill its graveyard, else nothing.
    - Emerge: its emerge cost less the mana value of the deck's cheapest
      creature card (never below its colored pips; the estimator casts
      cheapest-first, so that is the creature it expects out first), on the
      earliest turn the estimator expects a creature on the battlefield to
      sacrifice and the mana to pay.

    A deck that feeds none of them pays the printed cost."""
    from mtg_utils.commander_cost import (
        affordable_turn,
        colored_pips,
        expected_operand,
    )

    trees = trees_for(dict(card))
    tree = trees[0] if trees else None
    keywords = set(tree.card_keywords) if tree is not None else set()
    faces = card.get("card_faces") or []
    mana_cost = (faces[0].get("mana_cost") if faces else None) or card.get("mana_cost")
    printed = _face_cost(mana_cost)
    if printed is None:
        printed = float(card.get("cmc") or 0.0)
    pips = colored_pips(mana_cost)
    whole = math.ceil(printed)
    # The card on the stack feeds nothing of its own: one copy of it is out.
    name = card.get("name")
    deck_entries = [
        (rec, qty - (rec.get("name") == name))
        for rec, qty in deck_entries
        if qty - (rec.get("name") == name) > 0
    ]
    paid = [printed]
    populations: list[tuple[str, ...]] = []
    if "Convoke" in keywords:
        populations.append(("creature",))
    if "Improvise" in keywords:
        populations.append(("artifact",))
    if tree is not None:
        populations += [
            words for kw, words in tree.card_keyword_types if kw == "Affinity" and words
        ]
    for words in populations:
        turn, _table = affordable_turn(
            whole,
            pips,
            _population(words),
            _payers(deck_entries, words),
            library_size=library_size,
        )
        if turn is not None:
            paid.append(float(turn))
    if "Delve" in keywords and graveyard_fillers >= GRAVEYARD_FILL_FLOOR:
        paid.append(float(pips))
    emerge = [a for a in (tree.card_alt_costs if tree else ()) if a.kind == "emerge"]
    creatures = [
        float(rec.get("cmc") or 0.0)
        for rec, _qty in deck_entries
        if "Creature" in (rec.get("type_line") or "").split("//")[0]
    ]
    if emerge and creatures:
        text = emerge[0].cost.split(",")[0]
        cost = _face_cost(text)
        if cost is not None:
            residual = max(float(colored_pips(text)), cost - min(creatures))
            for turn in range(1, whole + 1):
                bodies = expected_operand(
                    deck_entries,
                    _population(("creature",)),
                    turn=turn,
                    library_size=library_size,
                )
                if bodies >= 1 and residual <= turn:
                    paid.append(float(turn))
                    break
    return min(paid)


def cast_costs(
    card: Mapping,
    deck_entries: Sequence[tuple[Mapping, int]] = (),
    *,
    library_size: int = 99,
    graveyard_fillers: int = 0,
) -> CastCosts:
    """``card``'s :class:`CastCosts`. Its modes: the printed cost, an X at
    :data:`X_COST_VALUE` (X is 0 off the stack, CR 202.3e); a split card's two
    halves (each half is cast on its own, CR 709.3, though the card's mana value
    combines them, 709.4) and an adventurer card's two ways (716.3: "normally or
    as an Adventure"); a curve alternative cost (the ones
    :func:`effective_mana_value` reads). ``cheapest`` is the least of them and
    ``top`` the printed (big) one, a split card's costlier half. Besides:

    - A modal double-faced card with a land face is never capped — it is never
      stuck in hand, played as that land (CR 712.12) — and sets the top at its
      spell's cost.
    - A face-down card (:data:`FACE_DOWN_KEYWORDS`) is cast for {3} and left out
      of the top; so is a "costs less" clause of its own the ADR-0044 estimator
      cannot price in ``deck_entries`` (checked at its printed cost), while a
      priced one counts at the estimator's affordable turn on both sides.
    - Undaunted counts at printed less :data:`POD_OPPONENTS` on both sides.
    - :data:`SELF_PAYING_KEYWORDS`: a candidate at what this deck pays
      (:func:`self_paid_cost`, its printed cost where the deck feeds it
      nothing); in the top at what the deck pays where it feeds it, else left
      out.

    The tuner's curve, shape and efficiency reads keep
    :func:`effective_mana_value`."""
    from mtg_utils.commander_cost import (
        STATUS_MODELLED,
        STATUS_NO_IR,
        STATUS_NONE,
        colored_pips,
        effective_commander_cost,
        read_self_discount,
    )

    trees = trees_for(dict(card))
    keywords = {k for tree in trees[:1] for k in tree.card_keywords}
    faces = card.get("card_faces") or []
    layout = card.get("layout") or ""
    # A multi-face record's own cost joins the faces' ("{5}{B}{B} // {3}{B}"):
    # the front face's is the card's printed one.
    mana_cost = (faces[0].get("mana_cost") if faces else None) or card.get("mana_cost")
    printed = _face_cost(mana_cost)
    if printed is None:
        printed = float(card.get("cmc") or 0.0)
    halves = [
        c
        for f in faces
        if layout in ("split", "aftermath", "adventure")
        and (c := _face_cost(f.get("mana_cost"))) is not None
    ]
    if layout in ("split", "aftermath") and halves:
        printed = max(halves)
    modes = [
        printed,
        *halves,
        *(float(c) for tree in trees for c in tree.card_curve_costs),
    ]
    if SELF_PAYING_KEYWORDS & keywords:
        paid = self_paid_cost(
            card,
            deck_entries,
            library_size=library_size,
            graveyard_fillers=graveyard_fillers,
        )
        # One the deck feeds counts at what it pays; one it can't feed is left
        # out of the top, as an unpriced "costs less" card is (the
        # coordinator's call, 2026-11-27).
        return CastCosts(min([paid, *modes[1:]]), paid if paid < printed else None)
    if "Undaunted" in keywords:
        reduced = max(float(colored_pips(mana_cost)), printed - POD_OPPONENTS)
        return CastCosts(min([reduced, *modes[1:]]), reduced)
    if layout == "modal_dfc" and any(
        "Land" in (f.get("type_line") or "") for f in faces[1:]
    ):
        return CastCosts(None, printed)
    if FACE_DOWN_KEYWORDS & keywords:
        return CastCosts(min([FACE_DOWN_COST, *modes]), None)
    discount = read_self_discount(card)
    if discount not in (STATUS_NONE, STATUS_NO_IR):
        block = (
            effective_commander_cost(card, deck_entries, library_size=library_size)
            if deck_entries
            else None
        )
        if block is None or block["status"] != STATUS_MODELLED:
            return CastCosts(min(modes), None)
        priced = float(block["effective"])
        return CastCosts(min([priced, *modes]), priced)
    return CastCosts(min(modes), printed)
