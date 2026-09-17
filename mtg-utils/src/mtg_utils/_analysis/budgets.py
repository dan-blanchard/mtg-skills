"""Slot budgets vs the (soft) Command Zone deckbuilding template.

Role targets are *nudges* (D8): the hard land/curve gate lives in ``mana_audit``. Each
role budget reports min/max band, current, remaining (to the floor), and deviation
(distance outside the band) so the build loop can size a "choose up to N" batch and the
Tune surface can rank template gaps.

The template is **bands** (Command Zone Ep. 658, verified multi-source), not single
points, and ``slot_budgets`` takes an optional ``shape``: ``None`` (the always-on
Budgets panel) uses flat bands; a Shape (the Tune surface, near-complete deck) scales
them.
Counterspells fold into a single ``interaction`` role; win-cons and protection are NOT
counted roles here — they are Tier-2 advisory flags (ADR-0024).
"""

from __future__ import annotations

from collections.abc import Sequence

from mtg_utils._analysis.roles import role_of

# Command Zone template bands, per 100 cards (min, max). Scaled by deck size for Brawl.
COMMANDER_TEMPLATE: dict[str, tuple[int, int]] = {
    "lands": (36, 38),
    "ramp": (10, 12),
    "card_draw": (10, 12),
    "interaction": (10, 12),
    "board_wipe": (3, 4),
}

# Shape-scaled band overrides (ADR-0024 — the literature scales by archetype, not by
# power bracket). Only roles that differ from the base are listed; the rest keep it.
_SHAPE_BANDS: dict[str, dict[str, tuple[int, int]]] = {
    "control": {"interaction": (12, 15), "board_wipe": (5, 7), "card_draw": (10, 14)},
    "aggro": {"interaction": (8, 10), "ramp": (8, 10), "board_wipe": (1, 2)},
    "combo": {"interaction": (8, 12), "board_wipe": (2, 3)},
    "midrange": {},
}


def bands_for(shape: str | None) -> dict[str, tuple[int, int]]:
    """The role→(min,max) bands for a Shape (or flat Command Zone bands when None)."""
    bands = dict(COMMANDER_TEMPLATE)
    if shape:
        bands.update(_SHAPE_BANDS.get(shape, {}))
    return bands


def banded_slot_budgets(
    records: Sequence[dict | None],
    land_band: dict,
    *,
    deck_size: int,
    shape: str | None = None,
) -> dict[str, dict]:
    """:func:`slot_budgets` over *records* (a deck's ``expanded()`` cards) with the
    lands row set to *land_band*, the mana audit's own ``{floor, top, …}`` readout
    (ADR-0041) — passed in so a caller that already audited never audits twice, and
    no caller re-derives the band."""
    return slot_budgets(
        records,
        deck_size=deck_size,
        shape=shape,
        land_band=(land_band["floor"], land_band["top"]),
    )


def slot_budgets(
    records: Sequence[dict | None],
    *,
    deck_size: int = 100,
    shape: str | None = None,
    land_band: tuple[int, int],
) -> dict[str, dict]:
    """Return ``{role: {min, max, target, current, remaining, deviation}}`` vs the band.

    ``deviation`` is 0 inside the band, negative when short of the floor, positive when
    over the ceiling. ``remaining`` is the gap up to the floor (0 once in band).
    ``target`` is the band ceiling, kept for the existing Budgets-panel bar.

    ``land_band`` (floor, top) is the deck-specific "lands" row: ``mana_audit``'s
    ``land_band`` (ADR-0041), which every deck carries. It is REQUIRED, so this call
    and the mana verdict provably read the same band — a re-derivation here from this
    call's own ramp tally (scoped to *records*, which callers commonly pass as cards +
    sideboard with commanders excluded) is exactly the second band ADR-0041 exists to
    eliminate, and no longer exists.
    """
    scale = deck_size / 100
    bands = bands_for(shape)
    current: dict[str, int] = dict.fromkeys(bands, 0)
    for record in records:
        if not record:
            continue
        for role in role_of(record):
            if role in current:
                current[role] += 1
    out: dict[str, dict] = {}
    for role, (lo, hi) in bands.items():
        if role == "lands":
            rmin, rmax = land_band  # already scaled to deck_size
        else:
            rmin = round(lo * scale)
            rmax = round(hi * scale)
        have = current[role]
        if have < rmin:
            deviation = have - rmin
        elif have > rmax:
            deviation = have - rmax
        else:
            deviation = 0
        out[role] = {
            "min": rmin,
            "max": rmax,
            "target": rmax,
            "current": have,
            "remaining": max(0, rmin - have),
            "deviation": deviation,
        }
    return out
