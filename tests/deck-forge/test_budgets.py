"""Tests for slot budgets vs the (soft) Command Zone template (band model, ADR-0024)."""

from mtg_utils._deck_forge.budgets import protects, role_of, slot_budgets

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
COUNTERSPELL = {
    "name": "Counterspell",
    "type_line": "Instant",
    "oracle_text": "Counter target spell.",
    "keywords": [],
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


def test_empty_deck_bands_scale_to_deck_size():
    b100 = slot_budgets([], deck_size=100)
    assert b100["ramp"]["min"] == 10
    assert b100["ramp"]["max"] == 12
    assert b100["lands"]["min"] == 36
    assert b100["lands"]["max"] == 38
    b60 = slot_budgets([], deck_size=60)
    assert b60["ramp"]["min"] == 6  # round(10 * 0.6)
    assert b60["ramp"]["max"] == 7  # round(12 * 0.6)


def test_role_classification_folds_counterspells_into_interaction():
    assert "lands" in role_of(FOREST)
    assert "ramp" in role_of(LLANOWAR)
    assert "interaction" in role_of(MURDER)
    assert "interaction" in role_of(COUNTERSPELL)  # counterspell folds into interaction
    assert "card_draw" in role_of(DIVINATION)
    assert "board_wipe" in role_of(WRATH)


def test_protection_is_advisory_not_a_counted_role():
    # Counterspell counts as both interaction (template) AND protection (Tier-2 flag).
    assert protects(COUNTERSPELL) is True
    assert protects(MURDER) is False
    assert "protection" not in role_of(COUNTERSPELL)  # never a counted role


def test_protection_requires_granting_not_a_self_keyword():
    # A permanent that is merely indestructible/hexproof itself protects only itself.
    self_indestructible = {
        "name": "Darksteel Reactor",
        "type_line": "Artifact",
        "oracle_text": "Indestructible",
        "keywords": ["Indestructible"],
    }
    self_hexproof = {
        "name": "Carnage Tyrant",
        "type_line": "Creature — Dinosaur",
        "oracle_text": "Trample, hexproof",
        "keywords": ["Trample", "Hexproof"],
    }
    assert protects(self_indestructible) is False
    assert protects(self_hexproof) is False
    # Granting a protective quality to ANOTHER permanent does count.
    grants = {
        "name": "Swiftfoot Boots",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has hexproof and haste. Equip {1}",
    }
    save = {
        "name": "Boros Charm",
        "type_line": "Instant",
        "oracle_text": "Permanents you control gain indestructible until end of turn.",
    }
    assert protects(grants) is True
    assert protects(save) is True
    # Pillow-fort / attack-deterrent effects protect YOU the player.
    pillow = {
        "name": "Ghostly Prison",
        "type_line": "Enchantment",
        "oracle_text": "Creatures can't attack you unless their controller pays {2} "
        "for each creature that's attacking you.",
    }
    assert protects(pillow) is True


def test_protection_excludes_self_only_saves():
    # A creature that only phases/regenerates ITSELF is self-protection — doesn't count.
    self_phase = {
        "name": "Frenetic Efreet",
        "type_line": "Creature — Efreet",
        "oracle_text": "{0}: Flip a coin. If you win the flip, Frenetic Efreet phases "
        "out. If you lose the flip, sacrifice it.",
    }
    assert protects(self_phase) is False
    # Saving / shielding OTHERS still counts.
    fog = {
        "name": "Fog",
        "type_line": "Instant",
        "oracle_text": "Prevent all combat damage that would be dealt this turn.",
    }
    save_target = {
        "name": "Sejiri Refuge Save",
        "type_line": "Instant",
        "oracle_text": "Regenerate target creature you control.",
    }
    assert protects(fog) is True
    assert protects(save_target) is True


def test_current_counts_reflect_deck():
    b = slot_budgets([FOREST, LLANOWAR, MURDER, DIVINATION, WRATH], deck_size=100)
    assert b["lands"]["current"] == 1
    assert b["ramp"]["current"] == 1
    assert b["card_draw"]["current"] == 1
    assert b["board_wipe"]["current"] == 1
    assert b["interaction"]["current"] >= 1


def test_deviation_signs_short_in_band_and_over():
    # 1 ramp source against a 10-12 band → short by 9.
    short = slot_budgets([LLANOWAR], deck_size=100)
    assert short["ramp"]["deviation"] == -9
    assert short["ramp"]["remaining"] == 9
    # 12 ramp sources → in band → deviation 0, remaining 0.
    rocks = [
        {
            "name": f"Rock {i}",
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}.",
            "produced_mana": ["C"],
        }
        for i in range(12)
    ]
    inband = slot_budgets(rocks, deck_size=100)
    assert inband["ramp"]["deviation"] == 0
    assert inband["ramp"]["remaining"] == 0
    # 15 ramp sources → over the 12 ceiling → +3.
    over = slot_budgets(rocks + rocks[:3], deck_size=100)
    assert over["ramp"]["deviation"] == 3


def test_shape_scales_control_interaction_up():
    flat = slot_budgets([], deck_size=100, shape=None)
    control = slot_budgets([], deck_size=100, shape="control")
    assert flat["interaction"]["max"] == 12
    assert control["interaction"]["min"] == 12
    assert control["interaction"]["max"] == 15
    # Aggro trims wraths.
    aggro = slot_budgets([], deck_size=100, shape="aggro")
    assert aggro["board_wipe"]["max"] == 2
