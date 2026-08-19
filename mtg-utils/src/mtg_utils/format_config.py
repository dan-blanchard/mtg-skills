"""Format configuration for MTG deck formats."""

from __future__ import annotations

# Arena's Competitive Brawl (June 2026) bans ten cards outright — as commander
# AND in the 99 — and legalizes everything else on Arena, including the ~28
# cards the ordinary Brawl queue bans. MTGJSON/Scryfall publish no legality key
# for it, so the audit runs off the `brawl` key plus these two overrides:
# `banned` under that key is legal here, `not_legal` still is not (it means the
# card isn't in the Arena pool at all).
#
# Source: https://mtg.wiki/page/Competitive_Brawl (banned list as of 2026-08).
# Re-verify after each B&R announcement; this list is a point-in-time snapshot.
COMPETITIVE_BRAWL_BANNED: frozenset[str] = frozenset(
    {
        "Ajani, Nacatl Pariah",
        "A-Nadu, Winged Wisdom",
        "Lutri, the Spellchaser",
        "Oko, Thief of Crowns",
        "Old Stickfingers",
        "Ragavan, Nimble Pilferer",
        "Rusko, Clockmaker",
        "Tamiyo, Inquisitive Student",
        "Wrenn and Six",
        "Tajic, Legion's Valor",
    }
)

FORMAT_CONFIGS: dict[str, dict] = {
    # ── Commander / Brawl variants (singleton, has commander) ──
    "commander": {
        "deck_size": 100,
        "sideboard_size": 0,
        "life_total": 40,
        "multiplayer_life_total": 40,
        "has_commander": True,
        "is_singleton": True,
        "max_copies": 1,
        "commander_damage": True,
        "legality_key": "commander",
        "planeswalker_commander_requires_text": True,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": False,
    },
    "brawl": {
        "deck_size": 60,
        "sideboard_size": 0,
        "life_total": 25,
        "multiplayer_life_total": 30,
        "has_commander": True,
        "is_singleton": True,
        "max_copies": 1,
        "commander_damage": False,
        "legality_key": "standardbrawl",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": True,
        "colorless_any_basic": True,
        "arena_format": True,
    },
    "historic_brawl": {
        "deck_size": 100,
        "sideboard_size": 0,
        "life_total": 25,
        "multiplayer_life_total": 30,
        "has_commander": True,
        "is_singleton": True,
        "max_copies": 1,
        "commander_damage": False,
        "legality_key": "brawl",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": True,
        "colorless_any_basic": True,
        "arena_format": True,
    },
    "competitive_brawl": {
        "deck_size": 100,
        "sideboard_size": 0,
        "life_total": 25,
        # Arena is 1v1 only; there is no multiplayer Competitive Brawl.
        "multiplayer_life_total": 25,
        "has_commander": True,
        "is_singleton": True,
        "max_copies": 1,
        "commander_damage": False,
        "legality_key": "brawl",
        "planeswalker_commander_requires_text": False,
        # Unlike ordinary Brawl, Competitive Brawl has no free mulligan.
        "free_mulligan": False,
        "colorless_any_basic": True,
        "arena_format": True,
        # Treat `banned` under the `brawl` key as legal, and enforce this
        # format's own ban list by name instead.
        "ignores_legality_key_bans": True,
        "banned_cards": COMPETITIVE_BRAWL_BANNED,
    },
    # ── Constructed formats (60-card, 4-of, sideboard) ──
    # Fields shared with commander variants are included for uniform access.
    "standard": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "standard",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": True,
    },
    "alchemy": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "alchemy",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": True,
    },
    "historic": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "historic",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": True,
    },
    "timeless": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "timeless",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": True,
    },
    "pioneer": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "pioneer",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": True,
    },
    "modern": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "modern",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": False,
    },
    "premodern": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "premodern",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": False,
    },
    "legacy": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "legacy",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": False,
    },
    "vintage": {
        "deck_size": 60,
        "sideboard_size": 15,
        "life_total": 20,
        "has_commander": False,
        "is_singleton": False,
        "max_copies": 4,
        "commander_damage": False,
        "legality_key": "vintage",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": False,
        "colorless_any_basic": False,
        "arena_format": False,
    },
}


def get_format_config(deck_json: dict) -> dict:
    """Return format config for a deck, with deck_size override support.

    Reads 'format' from deck_json (default: 'commander').
    If deck_json contains an explicit 'deck_size', overrides the config default.
    Raises ValueError for unknown format names.
    """
    fmt = deck_json.get("format", "commander")
    if fmt not in FORMAT_CONFIGS:
        valid = ", ".join(sorted(FORMAT_CONFIGS))
        msg = f"Unknown format: {fmt!r}. Valid formats: {valid}"
        raise ValueError(msg)
    cfg = dict(FORMAT_CONFIGS[fmt])
    if "deck_size" in deck_json:
        cfg["deck_size"] = deck_json["deck_size"]
    return cfg


def is_constructed_format(fmt: str) -> bool:
    """True for non-commander 60-card constructed formats."""
    cfg = FORMAT_CONFIGS.get(fmt, {})
    return not cfg.get("has_commander", True)


def is_arena_format(fmt: str) -> bool:
    """True for formats primarily played on MTG Arena."""
    return FORMAT_CONFIGS.get(fmt, {}).get("arena_format", False)
