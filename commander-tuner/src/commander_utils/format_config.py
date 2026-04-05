"""Format configuration for Commander variants."""

from __future__ import annotations

FORMAT_CONFIGS: dict[str, dict] = {
    "commander": {
        "deck_size": 100,
        "life_total": 40,
        "multiplayer_life_total": 40,
        "commander_damage": True,
        "legality_key": "commander",
        "planeswalker_commander_requires_text": True,
        "free_mulligan": False,
        "colorless_any_basic": False,
    },
    "brawl": {
        "deck_size": 60,
        "life_total": 25,
        "multiplayer_life_total": 30,
        "commander_damage": False,
        "legality_key": "standardbrawl",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": True,
        "colorless_any_basic": True,
    },
    "historic_brawl": {
        "deck_size": 100,
        "life_total": 25,
        "multiplayer_life_total": 30,
        "commander_damage": False,
        "legality_key": "brawl",
        "planeswalker_commander_requires_text": False,
        "free_mulligan": True,
        "colorless_any_basic": True,
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
        msg = f"Unknown format: {fmt!r}. Valid formats: {', '.join(FORMAT_CONFIGS)}"
        raise ValueError(msg)
    cfg = dict(FORMAT_CONFIGS[fmt])
    if "deck_size" in deck_json:
        cfg["deck_size"] = deck_json["deck_size"]
    return cfg
