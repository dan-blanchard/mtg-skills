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

import re
from collections.abc import Sequence

from mtg_utils.card_classify import get_oracle_text, is_land, is_ramp
from mtg_utils.theme_presets import get_preset

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

# Targeted removal + counterspells fold together into one `interaction` role (ADR-0024).
_INTERACTION_PRESETS = ("removal", "creature-removal", "counterspell", "bounce")

# Protection (Tier-2, advisory) must GRANT a protective quality to another permanent — a
# card that merely HAS indestructible/hexproof itself (Darksteel Reactor) protects only
# itself, not your board, so the keyword-on-itself presets are deliberately NOT used. We
# anchor on a granting verb + the keyword in oracle text (reminder text stripped).
_PROTECT_GRANT = re.compile(
    r"\b(?:gains?|have|has|gets?)\b[^.]*?"
    r"\b(?:hexproof|indestructible|ward|shroud|protection from)\b",
    re.IGNORECASE,
)
# Single-use saves that protect your stuff for a turn.
_PROTECT_SAVE = re.compile(
    r"\bregenerate\b|\bprevent (?:the next|all|that)\b|\bphases? out\b",
    re.IGNORECASE,
)


def _matches_preset(card: dict, name: str) -> bool:
    try:
        return get_preset(name).matches(card)
    except KeyError:
        return False


def _matches_any(card: dict, names: Sequence[str]) -> bool:
    return any(_matches_preset(card, name) for name in names)


def role_of(card: dict) -> set[str]:
    """Hard-counted template roles a card fills (a card may fill several)."""
    roles: set[str] = set()
    if is_land(card):
        roles.add("lands")
    elif is_ramp(card):
        roles.add("ramp")
    if _matches_preset(card, "card-draw") or _matches_preset(card, "cantrip"):
        roles.add("card_draw")
    if _matches_preset(card, "board-wipe"):
        roles.add("board_wipe")
    if _matches_any(card, _INTERACTION_PRESETS):
        roles.add("interaction")
    return roles


def protects(card: dict) -> bool:
    """Tier-2 (advisory, ADR-0024): does this card protect your own board/commander?

    Counts counterspells (answer removal) and cards that GRANT a protective quality to
    another permanent or save it for a turn — NOT a permanent that merely has hexproof /
    indestructible / ward on itself (which protects only itself, not your board).
    """
    if _matches_preset(card, "counterspell"):
        return True
    text = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")  # strip reminder text
    return bool(_PROTECT_GRANT.search(text) or _PROTECT_SAVE.search(text))


def bands_for(shape: str | None) -> dict[str, tuple[int, int]]:
    """The role→(min,max) bands for a Shape (or flat Command Zone bands when None)."""
    bands = dict(COMMANDER_TEMPLATE)
    if shape:
        bands.update(_SHAPE_BANDS.get(shape, {}))
    return bands


def slot_budgets(
    records: Sequence[dict | None], *, deck_size: int = 100, shape: str | None = None
) -> dict[str, dict]:
    """Return ``{role: {min, max, target, current, remaining, deviation}}`` vs the band.

    ``deviation`` is 0 inside the band, negative when short of the floor, positive when
    over the ceiling. ``remaining`` is the gap up to the floor (0 once in band).
    ``target`` is the band ceiling, kept for the existing Budgets-panel bar.
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
