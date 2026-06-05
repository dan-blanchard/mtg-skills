"""Tests for slot budgets vs the (soft) Command Zone template."""

from mtg_utils._deck_forge.budgets import role_of, slot_budgets

FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "oracle_text": "({T}: Add {G}.)",
}
LLANOWAR = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "oracle_text": "{T}: Add {G}.",
    "produced_mana": ["G"],
}
MURDER = {
    "name": "Murder",
    "type_line": "Instant",
    "oracle_text": "Destroy target creature.",
}
DIVINATION = {
    "name": "Divination",
    "type_line": "Sorcery",
    "oracle_text": "Draw two cards.",
}
WRATH = {
    "name": "Wrath of God",
    "type_line": "Sorcery",
    "oracle_text": "Destroy all creatures.",
}


def test_empty_deck_targets_scale_to_deck_size():
    b100 = slot_budgets([], deck_size=100)
    assert b100["ramp"]["target"] == 10
    assert b100["lands"]["target"] == 38
    b60 = slot_budgets([], deck_size=60)
    assert b60["ramp"]["target"] == 6  # round(10 * 0.6)


def test_role_classification():
    assert "lands" in role_of(FOREST)
    assert "ramp" in role_of(LLANOWAR)
    assert "removal" in role_of(MURDER)
    assert "card_draw" in role_of(DIVINATION)
    assert "board_wipe" in role_of(WRATH)


def test_current_counts_reflect_deck():
    b = slot_budgets([FOREST, LLANOWAR, MURDER, DIVINATION, WRATH], deck_size=100)
    assert b["lands"]["current"] == 1
    assert b["ramp"]["current"] == 1
    assert b["card_draw"]["current"] == 1
    assert b["board_wipe"]["current"] == 1
    assert b["removal"]["current"] >= 1


def test_remaining_clamps_at_zero():
    rocks = [
        {
            "name": f"Rock {i}",
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}.",
            "produced_mana": ["C"],
        }
        for i in range(15)
    ]
    b = slot_budgets(rocks, deck_size=100)
    assert b["ramp"]["current"] == 15
    assert b["ramp"]["remaining"] == 0
