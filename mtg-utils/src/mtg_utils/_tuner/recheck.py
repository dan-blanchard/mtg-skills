"""The proposal read whole: the adds the deck the proposal leaves can't fuel
(``_unfueled_adds``) and the next fuelled add for a dropped one's cut
(split out of ``swaps``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from mtg_utils._analysis.card_reads import has_trees
from mtg_utils._analysis.commander_need import (
    grants_all_creature_types,
)
from mtg_utils._analysis.job_quality import read_for
from mtg_utils._tuner.card_gates import (
    _chosen_type_on_battlefield,
)
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.upgrade_gates import (
    _DECK_FIT_FLOOR,
)

#: The jobs whose read scales by what the deck fuels (``JobRead.fit``) and that
#: the whole proposal is read again for (:func:`_unfueled_adds`).
_FUELED_JOBS = ("card_draw", "protection")


def _unfueled_adds(
    committed: Sequence[tuple[CardClass | None, dict, float, bool]],
    deck: Sequence[dict],
    commanders: Sequence[Mapping] = (),
) -> list[int]:
    """The indexes of ``committed`` swaps whose add does a fueled job
    (``_FUELED_JOBS``) below ``_DECK_FIT_FLOOR`` in the deck the whole
    proposal leaves (every cut out, every add in): its fuel cut by the same
    proposal, or never there — Losheel, Clockwork Scholar went onto Deep Clue
    Sea's theme page with five artifact creatures to draw on (2026-11-02).
    Under a commander making its creatures every type (Omo), a draw on a
    chosen type the battlefield shows is fed whatever the type lines say:
    Kindred Discovery's "enters or attacks" (Tricky Terrain)."""
    from mtg_utils._analysis.job_quality import card_draw

    every_type = any(grants_all_creature_types(dict(c)) for c in commanders)
    after = list(deck)
    for cut, _add, _cost, _charged in committed:
        if cut is None:
            continue
        for i, rec in enumerate(after):
            if rec.get("name") == cut.name:
                del after[i]
                break
    after.extend(add for _cut, add, _cost, _charged in committed)
    out = []
    for i, (_cut, add, _cost, _charged) in enumerate(committed):
        for job in _FUELED_JOBS:
            read = read_for(job)
            if read is None or not has_trees(add) or read.score(add) is None:
                continue
            if (
                job == "card_draw"
                and every_type
                and card_draw.draw_fuel(add) == "chosen_type"
                and _chosen_type_on_battlefield(add)
            ):
                continue
            if read.deck_fit(add, after) < _DECK_FIT_FLOOR:
                out.append(i)
                break
    return out


#: How many of a search's next candidates a dropped add's cut tries.
_REPICK_TRIES = 3


def _next_fueled_add(
    search: tuple[dict, dict] | None,
    cut: CardClass,
    find_add: Callable[..., tuple[dict, float, bool] | None],
    committed: Sequence[tuple[CardClass | None, dict, float, bool]],
    deck: Sequence[dict],
    commanders: Sequence[Mapping],
    unfueled: set[str],
) -> tuple[dict, float, bool] | None:
    """The next add ``search`` finds (``find_add`` skips ``unfueled``) that the
    deck the proposal leaves fuels (:func:`_unfueled_adds`); a candidate it
    doesn't joins ``unfueled``. ``None`` after ``_REPICK_TRIES`` or when the
    search runs dry, or for an add no search found."""
    if search is None:
        return None
    spec, options = search
    for _ in range(_REPICK_TRIES):
        picked = find_add(spec, **options)
        if picked is None:
            return None
        trial = [*committed, (cut, picked[0], 0.0, False)]
        if len(trial) - 1 not in _unfueled_adds(trial, deck, commanders):
            return picked
        unfueled.add(picked[0].get("name", ""))
    return None
