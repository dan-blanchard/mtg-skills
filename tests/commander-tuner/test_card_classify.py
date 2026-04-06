"""Tests for card classification helpers."""

from commander_utils.card_classify import color_sources, is_creature, is_land, is_ramp


class TestIsLand:
    def test_basic_land(self):
        assert is_land({"type_line": "Land"}) is True

    def test_dual_land(self):
        assert is_land({"type_line": "Land — Swamp Forest"}) is True

    def test_creature_is_not_land(self):
        assert is_land({"type_line": "Creature — Vampire"}) is False

    def test_artifact_is_not_land(self):
        assert is_land({"type_line": "Artifact"}) is False


class TestIsCreature:
    def test_creature_vampire(self):
        assert is_creature({"type_line": "Creature — Vampire"}) is True

    def test_legendary_creature(self):
        assert is_creature({"type_line": "Legendary Creature — Dragon Noble"}) is True

    def test_artifact_is_not_creature(self):
        assert is_creature({"type_line": "Artifact"}) is False

    def test_land_is_not_creature(self):
        assert is_creature({"type_line": "Land"}) is False


class TestIsRamp:
    def test_sol_ring(self):
        card = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
        }
        assert is_ramp(card) is True

    def test_sakura_tribe_elder(self):
        card = {
            "type_line": "Creature — Snake Shaman",
            "oracle_text": "Sacrifice Sakura-Tribe Elder: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
        }
        assert is_ramp(card) is True

    def test_cultivate(self):
        card = {
            "type_line": "Sorcery",
            "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        }
        assert is_ramp(card) is True

    def test_ashnods_altar(self):
        card = {
            "type_line": "Artifact",
            "oracle_text": "Sacrifice a creature: Add {C}{C}.",
        }
        assert is_ramp(card) is True

    def test_command_tower_not_ramp(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
        }
        assert is_ramp(card) is False

    def test_blood_artist_not_ramp(self):
        card = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever Blood Artist or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        assert is_ramp(card) is False

    def test_birds_of_paradise(self):
        card = {
            "type_line": "Creature — Bird",
            "oracle_text": "Flying\n{T}: Add one mana of any color.",
        }
        assert is_ramp(card) is True

    def test_arcane_signet(self):
        card = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
        }
        assert is_ramp(card) is True

    def test_bloom_tender(self):
        card = {
            "type_line": "Creature — Elf Druid",
            "oracle_text": "Vivid — {T}: For each color among permanents you control, add one mana of that color.",
        }
        assert is_ramp(card) is True

    def test_lotus_cobra(self):
        card = {
            "type_line": "Creature — Snake",
            "oracle_text": "Landfall — Whenever a land you control enters, add one mana of any color.",
        }
        assert is_ramp(card) is True

    def test_three_tree_city_land_not_ramp(self):
        """Lands that produce mana should not be classified as ramp."""
        card = {
            "type_line": "Legendary Land",
            "oracle_text": "{T}: Add {C}.\n{2}, {T}: Choose a color. Add an amount of mana of that color equal to the number of creatures you control of the chosen type.",
        }
        assert is_ramp(card) is False


class TestColorSources:
    def test_overgrown_tomb(self):
        card = {
            "type_line": "Land — Swamp Forest",
            "oracle_text": "({T}: Add {B} or {G}.)\nAs Overgrown Tomb enters the battlefield, you may pay 2 life. If you don't, it enters tapped.",
        }
        assert color_sources(card) == {"B", "G"}

    def test_command_tower_any(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
        }
        assert color_sources(card) == {"any"}

    def test_sol_ring_colorless(self):
        card = {
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
        }
        assert color_sources(card) == {"C"}

    def test_no_mana_production(self):
        card = {
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever Blood Artist or another creature dies, target player loses 1 life and you gain 1 life.",
        }
        assert color_sources(card) == set()

    def test_basic_plains(self):
        card = {
            "type_line": "Basic Land — Plains",
            "oracle_text": "{T}: Add {W}.",
        }
        assert color_sources(card) == {"W"}


class TestColorSourcesFetchLands:
    def test_polluted_delta(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for an Island or Swamp card, put it onto the battlefield, then shuffle.",
        }
        assert color_sources(card) == {"U", "B"}

    def test_prismatic_vista(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
        }
        assert color_sources(card) == {"any"}

    def test_verdant_catacombs(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for a Swamp or Forest card, put it onto the battlefield, then shuffle.",
        }
        assert color_sources(card) == {"B", "G"}

    def test_flooded_strand(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for a Plains or Island card, put it onto the battlefield, then shuffle.",
        }
        assert color_sources(card) == {"W", "U"}

    def test_fabled_passage(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land.",
        }
        assert color_sources(card) == {"any"}

    def test_seething_landscape(self):
        card = {
            "type_line": "Land",
            "oracle_text": "{T}: Add {C}.\n{T}, Sacrifice this land: Search your library for a basic Island, Swamp, or Mountain card, put it onto the battlefield tapped, then shuffle.",
        }
        assert color_sources(card) == {"U", "B", "R"}

    def test_basic_land_type_fetch(self):
        """Verify 'basic Mountain card' wording is handled."""
        card = {
            "type_line": "Land",
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for a basic Mountain card, put it onto the battlefield tapped, then shuffle.",
        }
        assert color_sources(card) == {"R"}
