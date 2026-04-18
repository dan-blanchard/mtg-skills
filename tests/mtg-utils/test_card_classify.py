"""Tests for card classification helpers."""

from mtg_utils.card_classify import (
    build_card_lookup,
    classify_cube_category,
    color_sources,
    is_commander,
    is_creature,
    is_land,
    is_ramp,
)


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


class TestIsCommander:
    def test_legendary_creature(self):
        card = {"type_line": "Legendary Creature — Dragon Noble"}
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": False}

    def test_legendary_vehicle(self):
        card = {"type_line": "Legendary Artifact — Vehicle"}
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": False}

    def test_legendary_spacecraft_with_pt(self):
        card = {
            "type_line": "Legendary Artifact — Spacecraft",
            "power": "3",
            "toughness": "5",
        }
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": False}

    def test_legendary_spacecraft_without_pt(self):
        card = {"type_line": "Legendary Artifact — Spacecraft"}
        result = is_commander(card)
        assert result == {"eligible": False, "requires_partner": False}

    def test_legendary_planeswalker_commander_format(self):
        card = {"type_line": "Legendary Planeswalker — Jace"}
        result = is_commander(card, format="commander")
        assert result == {"eligible": False, "requires_partner": False}

    def test_legendary_planeswalker_brawl_format(self):
        card = {"type_line": "Legendary Planeswalker — Jace"}
        result = is_commander(card, format="brawl")
        assert result == {"eligible": True, "requires_partner": False}

    def test_can_be_your_commander_text(self):
        card = {
            "type_line": "Legendary Enchantment",
            "oracle_text": "Leyline of the Guildpact can be your commander.",
        }
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": False}

    def test_choose_a_background(self):
        card = {
            "type_line": "Legendary Creature — Human Ranger",
            "oracle_text": "Choose a Background",
        }
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": True}

    def test_choose_a_background_non_creature(self):
        card = {
            "type_line": "Legendary Enchantment",
            "oracle_text": "Choose a Background\nSome other text.",
        }
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": True}

    def test_legendary_background_enchantment(self):
        card = {"type_line": "Legendary Enchantment — Background"}
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": True}

    def test_non_legendary_creature(self):
        card = {"type_line": "Creature — Goblin Warrior"}
        result = is_commander(card)
        assert result == {"eligible": False, "requires_partner": False}

    def test_instant(self):
        card = {"type_line": "Instant"}
        result = is_commander(card)
        assert result == {"eligible": False, "requires_partner": False}


class TestClassifyCubeCategory:
    def test_mono_white(self):
        card = {
            "type_line": "Creature — Human Knight",
            "color_identity": ["W"],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "W"

    def test_mono_red_instant(self):
        card = {
            "type_line": "Instant",
            "color_identity": ["R"],
            "oracle_text": "Deal 3 damage to any target.",
        }
        assert classify_cube_category(card) == "R"

    def test_multicolor(self):
        card = {
            "type_line": "Creature — Human Warrior",
            "color_identity": ["W", "R"],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "M"

    def test_multicolor_three_color(self):
        card = {
            "type_line": "Creature — Sliver",
            "color_identity": ["W", "U", "B"],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "M"

    def test_colorless_non_fixing_artifact(self):
        """Plain colorless artifact with no mana production → C."""
        card = {
            "type_line": "Artifact",
            "color_identity": [],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "C"

    def test_colorless_creature(self):
        card = {
            "type_line": "Artifact Creature — Construct",
            "color_identity": [],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "C"

    def test_mana_producing_land(self):
        """A mono-color land that taps for mana → L (mana-producing land)."""
        card = {
            "type_line": "Land",
            "color_identity": ["R"],
            "oracle_text": "{T}: Add {R}.",
        }
        assert classify_cube_category(card) == "L"

    def test_dual_land_goes_to_land_bucket(self):
        """Dual lands that tap for mana are L, not F. Fixing is about multi-
        color sources that don't just tap for mana directly."""
        card = {
            "type_line": "Land — Swamp Forest",
            "color_identity": ["B", "G"],
            "oracle_text": "({T}: Add {B} or {G}.)\nAs Overgrown Tomb enters, you may pay 2 life. If you don't, it enters tapped.",
        }
        assert classify_cube_category(card) == "L"

    def test_command_tower_is_land(self):
        """Command Tower taps for mana of any color → L (mana-producing)."""
        card = {
            "type_line": "Land",
            "color_identity": [],
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
        }
        assert classify_cube_category(card) == "L"

    def test_evolving_wilds_is_fixing(self):
        """Evolving Wilds doesn't tap for mana — only sacrifices to fetch
        a basic. Per cube-utils, this is F (fixing)."""
        card = {
            "type_line": "Land",
            "color_identity": [],
            "oracle_text": "{T}, Sacrifice this land: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
        }
        assert classify_cube_category(card) == "F"

    def test_fetchland_is_fixing(self):
        """Fetch lands (Polluted Delta, Flooded Strand) don't tap for mana,
        only sacrifice to search → F."""
        card = {
            "type_line": "Land",
            "color_identity": [],
            "oracle_text": "{T}, Pay 1 life, Sacrifice this land: Search your library for a Plains or Island card, put it onto the battlefield, then shuffle.",
        }
        assert classify_cube_category(card) == "F"

    def test_colorless_land_is_land_bucket(self):
        card = {
            "type_line": "Land",
            "color_identity": [],
            "oracle_text": "{T}: Add {C}.",
        }
        assert classify_cube_category(card) == "L"

    def test_basic_land_is_land_bucket(self):
        """Basics have empty oracle text but produce mana via type line → L."""
        card = {
            "type_line": "Basic Land — Mountain",
            "color_identity": ["R"],
            "oracle_text": "",
        }
        assert classify_cube_category(card) == "L"

    def test_sol_ring_is_fixing(self):
        """Sol Ring: colorless artifact that produces mana → F (mana rock)."""
        card = {
            "type_line": "Artifact",
            "color_identity": [],
            "oracle_text": "{T}: Add {C}{C}.",
        }
        assert classify_cube_category(card) == "F"

    def test_arcane_signet_is_fixing(self):
        """Arcane Signet: mana rock that produces any color → F."""
        card = {
            "type_line": "Artifact",
            "color_identity": [],
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
        }
        assert classify_cube_category(card) == "F"

    def test_cultivate_is_green(self):
        """Cultivate: green land-fetcher → G (slots into the green pack position)."""
        card = {
            "type_line": "Sorcery",
            "color_identity": ["G"],
            "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        }
        assert classify_cube_category(card) == "G"

    def test_sakura_tribe_elder_is_green(self):
        """Sakura-Tribe Elder: green creature → G, not F."""
        card = {
            "type_line": "Creature — Snake Shaman",
            "color_identity": ["G"],
            "oracle_text": "Sacrifice Sakura-Tribe Elder: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
        }
        assert classify_cube_category(card) == "G"

    def test_birds_of_paradise_is_green(self):
        """Mana dork with color identity G → G slot. Each pack reserves one
        mono-color slot per color, and Birds helps drafters committing to G."""
        card = {
            "type_line": "Creature — Bird",
            "color_identity": ["G"],
            "oracle_text": "Flying\n{T}: Add one mana of any color.",
        }
        assert classify_cube_category(card) == "G"

    def test_llanowar_elves_is_green(self):
        """Mono-G mana dork → G bucket, not F."""
        card = {
            "type_line": "Creature — Elf Druid",
            "color_identity": ["G"],
            "oracle_text": "{T}: Add {G}.",
        }
        assert classify_cube_category(card) == "G"

    def test_wayfarers_bauble_is_fixing(self):
        """Colorless land-fetcher → F. No color identity, so no mono-color
        slot competes."""
        card = {
            "type_line": "Artifact",
            "color_identity": [],
            "oracle_text": "{2}, {T}, Sacrifice Wayfarer's Bauble: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
        }
        assert classify_cube_category(card) == "F"

    def test_chromatic_lantern_is_fixing(self):
        """Colorless mana rock producing any color → F."""
        card = {
            "type_line": "Artifact",
            "color_identity": [],
            "oracle_text": 'Lands you control have "{T}: Add one mana of any color."\n{T}: Add one mana of any color.',
        }
        assert classify_cube_category(card) == "F"

    def test_multicolor_non_fixing(self):
        """Multicolor creature that doesn't produce mana or fetch → M."""
        card = {
            "type_line": "Legendary Creature — Human Soldier",
            "color_identity": ["W", "R"],
            "oracle_text": "Whenever this creature attacks, create a 1/1 white Soldier token.",
        }
        assert classify_cube_category(card) == "M"


class TestBuildCardLookup:
    def test_canonical_name(self):
        """Cards are indexed by their canonical name."""
        hydrated = [{"name": "Lightning Bolt", "type_line": "Instant"}]
        lookup = build_card_lookup(hydrated)
        assert "Lightning Bolt" in lookup
        assert lookup["Lightning Bolt"]["type_line"] == "Instant"

    def test_dfc_front_face_alias(self):
        """DFC/MDFC cards listed by front face only still resolve.

        A deck parsed from Moxfield / Arena / plain text commonly lists a
        pathway as "Hengegate Pathway" (front face) while Scryfall's bulk
        data uses the canonical combined form "Hengegate Pathway //
        Mistgate Pathway". build_card_lookup must index both so downstream
        lookups hit regardless of which spelling the deck author used.
        """
        hydrated = [
            {
                "name": "Hengegate Pathway // Mistgate Pathway",
                "type_line": "Land // Land",
            }
        ]
        lookup = build_card_lookup(hydrated)
        assert "Hengegate Pathway // Mistgate Pathway" in lookup
        assert "Hengegate Pathway" in lookup
        assert (
            lookup["Hengegate Pathway"]
            is lookup["Hengegate Pathway // Mistgate Pathway"]
        )

    def test_dfc_front_face_matches_only_land_back(self):
        """Aliasing covers DFCs whose back face is a land (flex lands)."""
        hydrated = [
            {
                "name": "Shatterskull Smashing // Shatterskull, the Hammer Pass",
                "type_line": "Sorcery // Land",
            }
        ]
        lookup = build_card_lookup(hydrated)
        assert "Shatterskull Smashing" in lookup

    def test_printed_name_alias(self):
        """Arena printed_name still resolves to the canonical card."""
        hydrated = [
            {
                "name": "Masked Meower",
                "printed_name": "Skittering Kitten",
                "type_line": "Creature",
            }
        ]
        lookup = build_card_lookup(hydrated)
        assert "Masked Meower" in lookup
        assert "Skittering Kitten" in lookup

    def test_canonical_wins_over_alias(self):
        """When two cards collide on an alias, the canonical stays pinned.

        If card A's canonical name happens to equal card B's front-face
        or printed_name alias, A's entry must not be overwritten.
        """
        hydrated = [
            {"name": "Hengegate Pathway", "type_line": "Something Else"},
            {
                "name": "Hengegate Pathway // Mistgate Pathway",
                "type_line": "Land // Land",
            },
        ]
        lookup = build_card_lookup(hydrated)
        # First card's canonical entry is preserved despite the second
        # card trying to alias onto the same key.
        assert lookup["Hengegate Pathway"]["type_line"] == "Something Else"

    def test_none_entries_skipped(self):
        """Hydration misses (None entries) don't crash the builder."""
        hydrated = [None, {"name": "Lightning Bolt", "type_line": "Instant"}]
        lookup = build_card_lookup(hydrated)
        assert "Lightning Bolt" in lookup

    def test_non_dfc_not_aliased(self):
        """Names without ' // ' don't generate bogus front-face aliases."""
        hydrated = [{"name": "Lightning Bolt", "type_line": "Instant"}]
        lookup = build_card_lookup(hydrated)
        # Exactly one entry; no accidental aliasing.
        assert len(lookup) == 1
