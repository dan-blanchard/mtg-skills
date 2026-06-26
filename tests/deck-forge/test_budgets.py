"""Tests for slot budgets vs the (soft) Command Zone template (band model, ADR-0024)."""

from mtg_utils._deck_forge.budgets import _ir_draws, protects, role_of, slot_budgets
from mtg_utils.card_ir import Ability, Card, Effect, Face
from mtg_utils.testkit import test_card_ir

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
    "oracle_text": "Destroy all creatures. They can't be regenerated.",
}
FLESHBAG = {
    "name": "Fleshbag Marauder",
    "type_line": "Creature — Zombie Warrior",
    "oracle_text": (
        "When this creature enters, each player sacrifices a creature of their choice."
    ),
}
PACIFISM = {
    "name": "Pacifism",
    "type_line": "Enchantment — Aura",
    "oracle_text": "Enchant creature\nEnchanted creature can't attack or block.",
}
# Over-fire guard: a creature whose OWN "can't attack or block" is a drawback (keyed on
# "This creature", not "Enchanted creature") is not removal.
LUPINE = {
    "name": "Lupine Prototype",
    "type_line": "Artifact Creature — Wolf Construct",
    "oracle_text": "This creature can't attack or block unless a player has no cards in hand.",
}
# Over-fire guard: sacrifice as an activated COST (you choose to pay) is not an edict.
VISCERA = {
    "name": "Viscera Seer",
    "type_line": "Creature — Vampire Wizard",
    "oracle_text": "Sacrifice a creature: Scry 1.",
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


def test_edicts_and_pacify_auras_count_as_interaction():
    # role_of is the universal coverage fallback, so forced-sacrifice (edicts) and
    # pacification auras — both REMOVAL regardless of commander — must register as
    # interaction. Fleshbag (creature-edict) and Pacifism (neutralize aura) were missed.
    assert "interaction" in role_of(FLESHBAG)
    assert "interaction" in role_of(PACIFISM)
    # Over-fire guards: a sacrifice COST (Viscera Seer) and a creature with a "can't
    # attack" DRAWBACK on itself (Lupine Prototype) are not removal.
    assert "interaction" not in role_of(VISCERA)
    assert "interaction" not in role_of(LUPINE)


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
        "oracle_text": 'Indestructible (Effects that say "destroy" don\'t destroy this artifact.)\nAt the beginning of your upkeep, you may put a charge counter on this artifact.\nWhen this artifact has twenty or more charge counters on it, you win the game.',
        "keywords": ["Indestructible"],
    }
    self_hexproof = {
        "name": "Carnage Tyrant",
        "type_line": "Creature — Dinosaur",
        "oracle_text": "This spell can't be countered.\nTrample, hexproof",
        "keywords": ["Trample", "Hexproof"],
    }
    assert protects(self_indestructible) is False
    assert protects(self_hexproof) is False
    # Granting a protective quality to ANOTHER permanent does count.
    grants = {
        "name": "Swiftfoot Boots",
        "type_line": "Artifact — Equipment",
        "oracle_text": "Equipped creature has hexproof and haste. (It can't be the target of spells or abilities your opponents control. It can attack and {T} no matter when it came under your control.)\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    }
    save = {
        "name": "Boros Charm",
        "type_line": "Instant",
        "oracle_text": "Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain indestructible until end of turn.\n• Target creature gains double strike until end of turn.",
    }
    assert protects(grants) is True
    assert protects(save) is True
    # Pillow-fort / attack-deterrent effects protect YOU the player.
    pillow = {
        "name": "Ghostly Prison",
        "type_line": "Enchantment",
        "oracle_text": "Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you.",
    }
    assert protects(pillow) is True


def test_protection_excludes_self_only_saves():
    # A creature that only phases/regenerates ITSELF is self-protection — doesn't count.
    self_phase = {
        "name": "Frenetic Efreet",
        "type_line": "Creature — Efreet",
        "oracle_text": "Flying\n{0}: Flip a coin. If you win the flip, this creature phases out. If you lose the flip, sacrifice this creature. (While it's phased out, it's treated as though it doesn't exist. It phases in before you untap during your next untap step.)",
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


# ── card_draw via Card IR (ADR-0027, A3) ─────────────────────────────────────
# role_of resolves card_draw from the candidate's IR ``draw`` category when present
# (the dict fixtures above carry no oracle_id, so they exercise the preset
# fallback). These exercise the structured ``_ir_draws`` classifier directly.


def _ir(*abilities: Ability) -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=abilities),))


def test_ir_draw_for_you_fills_card_draw():
    # Real projected IR: "Draw two cards" (Divination → draw/you) and an upkeep draw
    # (Phyrexian Arena → draw/you + lose_life/you) both fill it.
    assert _ir_draws(test_card_ir("Divination")) is True
    assert _ir_draws(test_card_ir("Phyrexian Arena")) is True
    # Symmetric "each player draws" (Howling Mine → draw/any) still fills your slot.
    assert _ir_draws(test_card_ir("Howling Mine")) is True
    # Connive (Ledger Shredder → connive) is card advantage too — its own IR category.
    assert _ir_draws(test_card_ir("Ledger Shredder")) is True


def test_ir_non_draw_and_opponent_draw_do_not_fill_card_draw():
    # Real projected IR: a damage spell (Lightning Bolt → damage/any) is not draw.
    assert _ir_draws(test_card_ir("Lightning Bolt")) is False
    # Logic probe (kept synthetic): a pure opponent-only draw (a giveaway, scope 'opp')
    # doesn't fill YOUR card_draw slot. No real card projects to a draw/opp effect —
    # phase attributes "target opponent draws" to scope 'you' (e.g. Master of the Feast),
    # so this pins the scope=='opp' branch of _ir_draws that real IR can't reach today.
    giveaway = _ir(
        Ability(kind="spell", effects=(Effect(category="draw", scope="opp"),))
    )
    assert _ir_draws(giveaway) is False
