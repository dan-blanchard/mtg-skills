"""Slot budgets vs the (soft) Command Zone deckbuilding template.

Role targets are *nudges* (D8): the hard land/curve gate lives in ``mana_audit``.
Each role budget reports target / current / remaining so the build loop can size a
"choose up to N" batch and surface the most under-filled slot as a suggested avenue.
"""

from __future__ import annotations

from mtg_utils.card_classify import is_land, is_ramp
from mtg_utils.theme_presets import get_preset

# Command Zone template, per 100 cards. Scaled by deck size for Brawl (60).
COMMANDER_TEMPLATE: dict[str, int] = {
    "lands": 38,
    "ramp": 10,
    "card_draw": 10,
    "removal": 10,
    "board_wipe": 4,
}


def _matches_preset(card: dict, name: str) -> bool:
    try:
        return get_preset(name).matches(card)
    except KeyError:
        return False


def role_of(card: dict) -> set[str]:
    """Roles a card fills (a card may fill several)."""
    roles: set[str] = set()
    if is_land(card):
        roles.add("lands")
    elif is_ramp(card):
        roles.add("ramp")
    if _matches_preset(card, "card-draw") or _matches_preset(card, "cantrip"):
        roles.add("card_draw")
    if _matches_preset(card, "board-wipe"):
        roles.add("board_wipe")
    if _matches_preset(card, "removal") or _matches_preset(card, "creature-removal"):
        roles.add("removal")
    return roles


def slot_budgets(
    records: list[dict | None], *, deck_size: int = 100
) -> dict[str, dict]:
    """Return ``{role: {target, current, remaining}}`` against the scaled template."""
    scale = deck_size / 100
    current: dict[str, int] = dict.fromkeys(COMMANDER_TEMPLATE, 0)
    for record in records:
        if not record:
            continue
        for role in role_of(record):
            if role in current:
                current[role] += 1
    out: dict[str, dict] = {}
    for role, base in COMMANDER_TEMPLATE.items():
        target = round(base * scale)
        have = current[role]
        out[role] = {
            "target": target,
            "current": have,
            "remaining": max(0, target - have),
        }
    return out
