"""Tests for card classification helpers."""

import re

from mtg_utils.card_classify import (
    PartnerAbility,
    build_card_lookup,
    can_partner,
    classify_cube_category,
    color_sources,
    get_oracle_text,
    has_any_number_exemption,
    is_commander,
    is_creature,
    is_fixing_land,
    is_land,
    named_card_cap,
    partner_abilities,
    ramp_by_text,
    valid_partner_search,
)
from mtg_utils.testkit import test_card


class TestIsLand:
    def test_basic_land(self):
        assert is_land({"type_line": "Land"}) is True

    def test_dual_land(self):
        assert is_land({"type_line": "Land — Swamp Forest"}) is True

    def test_creature_is_not_land(self):
        assert is_land({"type_line": "Creature — Vampire"}) is False

    def test_artifact_is_not_land(self):
        assert is_land({"type_line": "Artifact"}) is False

    def test_transform_saga_into_land_is_not_a_land(self):
        # Cast as the FRONT (Enchantment Saga); the transformed back land doesn't make
        # it a manabase land. (Welcome to . . . // Jurassic Park.)
        card = {
            "layout": "transform",
            "type_line": "Enchantment — Saga // Legendary Land",
            "card_faces": [
                {"type_line": "Enchantment — Saga"},
                {"type_line": "Legendary Land"},
            ],
        }
        assert is_land(card) is False

    def test_transform_with_front_land_is_a_land(self):
        card = {
            "layout": "transform",
            "type_line": "Legendary Land // Legendary Creature — Horror",
            "card_faces": [
                {"type_line": "Legendary Land"},
                {"type_line": "Legendary Creature — Horror"},
            ],
        }
        assert is_land(card) is True

    def test_modal_dfc_land_back_still_counts(self):
        # MDFC: either face is playable, so a land back IS a real manabase option.
        card = {
            "layout": "modal_dfc",
            "type_line": "Sorcery // Land",
            "card_faces": [{"type_line": "Sorcery"}, {"type_line": "Land"}],
        }
        assert is_land(card) is True


class TestIsCreature:
    def test_creature_vampire(self):
        assert is_creature({"type_line": "Creature — Vampire"}) is True

    def test_legendary_creature(self):
        assert is_creature({"type_line": "Legendary Creature — Dragon Noble"}) is True

    def test_artifact_is_not_creature(self):
        assert is_creature({"type_line": "Artifact"}) is False

    def test_land_is_not_creature(self):
        assert is_creature({"type_line": "Land"}) is False

    def test_transform_saga_into_creature_is_not_a_creature(self):
        # Enters as the front Saga, not a creature.
        card = {
            "layout": "transform",
            "type_line": "Enchantment — Saga // Legendary Creature — Dragon",
            "card_faces": [
                {"type_line": "Enchantment — Saga"},
                {"type_line": "Legendary Creature — Dragon"},
            ],
        }
        assert is_creature(card) is False

    def test_werewolf_front_creature_is_a_creature(self):
        card = {
            "layout": "transform",
            "type_line": "Creature — Human Werewolf // Creature — Werewolf",
            "card_faces": [
                {"type_line": "Creature — Human Werewolf"},
                {"type_line": "Creature — Werewolf"},
            ],
        }
        assert is_creature(card) is True


class TestGetOracleTextFaceBoundary:
    """A sentence-scoped regex must NOT bridge two DFC faces of the folded oracle —
    a single-face effect can't be 'completed' by the other side of the card."""

    def test_keyword_only_face_is_period_terminated(self):
        # face0 ("Flying") has no trailing period, so `flying[^.]*token` could otherwise
        # bridge into face1's "create a token" and read as "makes flying tokens".
        card = {
            "layout": "transform",
            "card_faces": [
                {"oracle_text": "Flying"},
                {"oracle_text": "Create a 1/1 white Soldier creature token."},
            ],
        }
        folded = get_oracle_text(card)
        assert re.search(r"flying[^.]*token", folded, re.IGNORECASE) is None

    def test_face_already_ending_in_period_is_unchanged(self):
        card = {
            "layout": "transform",
            "card_faces": [
                {"oracle_text": "This creature has flying."},
                {"oracle_text": "Create a 1/1 token."},
            ],
        }
        # no doubled period, and the bridge is still blocked
        folded = get_oracle_text(card)
        assert ".." not in folded
        assert re.search(r"flying[^.]*token", folded, re.IGNORECASE) is None

    def test_within_face_match_still_works(self):
        # The fix must NOT break a local match: a back-face land that taps for mana is
        # still detectable within its own face (Dan: back-face lands should still count).
        card = {
            "layout": "transform",
            "card_faces": [
                {"oracle_text": "Draw a card"},
                {"oracle_text": "{T}: Add {G} for each Dinosaur you control."},
            ],
        }
        assert "Add {G}" in get_oracle_text(card)

    def test_vanilla_creature_with_null_faces_returns_empty(self):
        # A vanilla creature (Catacomb Crocodile) hydrated through the MTGJSON adapter
        # carries oracle_text "" AND card_faces None -- the key is present, so a
        # .get() default never applied and the join crashed on iterating None.
        card = {"layout": "normal", "oracle_text": "", "card_faces": None}
        assert get_oracle_text(card) == ""

    def test_card_with_no_faces_key_returns_empty(self):
        assert get_oracle_text({"layout": "normal"}) == ""


class TestRampByText:
    """The no-coverage text degrade (``_analysis.roles.is_ramp`` owns the real
    answer — see ``tests/deck-forge/test_roles.py``)."""

    def test_number_word_mana(self):
        # "Add three mana of any one color" (Gilded Lotus): no "{" / "one mana" after
        # "add" — the blind spot that made the text read disagree with the signal path.
        card = test_card("Gilded Lotus")
        assert ramp_by_text(card) is True

    def test_sol_ring(self):
        card = test_card("Sol Ring")
        assert ramp_by_text(card) is True

    def test_sakura_tribe_elder(self):
        card = test_card("Sakura-Tribe Elder")
        assert ramp_by_text(card) is True

    def test_cultivate(self):
        card = test_card("Cultivate")
        assert ramp_by_text(card) is True

    def test_ashnods_altar(self):
        card = test_card("Ashnod's Altar")
        assert ramp_by_text(card) is True

    def test_command_tower_not_ramp(self):
        card = test_card("Command Tower")
        assert ramp_by_text(card) is False

    def test_blood_artist_not_ramp(self):
        card = test_card("Blood Artist")
        assert ramp_by_text(card) is False

    def test_birds_of_paradise(self):
        card = test_card("Birds of Paradise")
        assert ramp_by_text(card) is True

    def test_arcane_signet(self):
        card = test_card("Arcane Signet")
        assert ramp_by_text(card) is True

    def test_bloom_tender(self):
        card = test_card("Bloom Tender")
        assert ramp_by_text(card) is True

    def test_lotus_cobra(self):
        card = test_card("Lotus Cobra")
        assert ramp_by_text(card) is True

    def test_three_tree_city_land_not_ramp(self):
        """Lands that produce mana should not be classified as ramp."""
        card = test_card("Three Tree City")
        assert ramp_by_text(card) is False

    def test_an_offer_you_cant_refuse_not_ramp(self):
        """Opponent-directed Treasure is anti-ramp: the "Add one mana" lives only in the
        token reminder and the Treasures go to the countered spell's controller."""
        card = test_card("An Offer You Can't Refuse")
        assert ramp_by_text(card) is False

    def test_you_directed_treasure_is_ramp(self):
        """A Treasure-maker you keep (Dockside / Brass's Bounty) is ramp, even though the
        "Add one mana" is only in the token reminder text."""
        card = test_card("Brass's Bounty")
        assert ramp_by_text(card) is True

    def test_typed_subtype_land_fetch_to_battlefield_is_ramp(self):
        # "Search your library for a Forest card ... onto the battlefield" is ramp, but
        # the raw "land" substring test missed it ("Forest card" has no "land"); Farseek
        # only passed because "Island" contains "land". Match the land by subtype name.
        natures_lore = test_card("Nature's Lore")
        three_visits = test_card("Three Visits")
        farseek = test_card("Farseek")
        assert ramp_by_text(natures_lore) is True
        assert ramp_by_text(three_visits) is True
        assert ramp_by_text(farseek) is True

    def test_land_tutor_to_hand_is_not_ramp(self):
        # A land TUTOR that puts the card into your hand (Moonsilver Key, Sylvan Scrying)
        # is not acceleration — it adds no mana and drops no land. The library-search
        # branch must require the fetched card to enter the battlefield.
        moonsilver_key = test_card("Moonsilver Key")
        assert ramp_by_text(moonsilver_key) is False

    def test_conditional_mox_still_counts_as_ramp(self):
        """ramp_by_text counts a conditionally-gated rock the user chose to run (it DOES add
        mana directly). The tuner's separate reliable-ramp filter is what keeps it from
        being SUGGESTED into a deck that can't turn it on."""
        card = test_card("Mox Opal")
        assert ramp_by_text(card) is True

    def test_variable_amount_mana_dork_is_ramp(self):
        """A dork that adds "an amount of {G}" (devotion/counter-scaled — Karametra's
        Acolyte, Marwyn) is ramp even though the mana symbol isn't adjacent to "Add"."""
        karametra = test_card("Karametra's Acolyte")
        assert ramp_by_text(karametra) is True

    def test_mana_amplifier_is_ramp(self):
        """A mana AMPLIFIER ("add an additional {X}" per land tapped — Nirkana Revenant,
        Crypt Ghast, Caged Sun) ramps you even though the mana symbol isn't adjacent to
        "Add"; symmetric amplifiers still ramp the controller."""
        nirkana = test_card("Nirkana Revenant")
        crypt_ghast = test_card("Crypt Ghast")
        assert ramp_by_text(nirkana) is True
        assert ramp_by_text(crypt_ghast) is True

    def test_extra_land_and_land_from_hand_are_ramp(self):
        """Land-acceleration that adds no mana directly: extra land drops (Azusa) and
        putting a land from hand into play (Arboreal Grazer) both ramp via lands."""
        azusa = test_card("Azusa, Lost but Seeking")
        grazer = test_card("Arboreal Grazer")
        assert ramp_by_text(azusa) is True
        assert ramp_by_text(grazer) is True
        # Over-fire guard: a plain beater that merely mentions "land" is not ramp.
        beater = test_card("Ravenous Baboons")
        assert ramp_by_text(beater) is False


class TestColorSources:
    def test_overgrown_tomb(self):
        card = test_card("Overgrown Tomb")
        assert color_sources(card) == {"B", "G"}

    def test_command_tower_any(self):
        card = test_card("Command Tower")
        assert color_sources(card) == {"any"}

    def test_sol_ring_colorless(self):
        card = test_card("Sol Ring")
        assert color_sources(card) == {"C"}

    def test_no_mana_production(self):
        card = test_card("Blood Artist")
        assert color_sources(card) == set()

    def test_basic_plains(self):
        card = test_card("Plains")
        assert color_sources(card) == {"W"}

    def test_every_listed_color(self):
        """ "Add {W}, {U}, or {B}" is all three colours — the old text read stopped at
        the first symbol and reported {W} alone."""
        assert color_sources(test_card("Arcane Sanctum")) == {"W", "U", "B"}
        assert color_sources(test_card("Noble Hierarch")) == {"G", "W", "U"}
        assert color_sources(test_card("Obelisk of Grixis")) == {"U", "B", "R"}

    def test_filter_land_reads_its_combinations(self):
        """Cascade Bluffs: {T}: Add {C}, or {U/R}, {T}: Add {U}{U}, {U}{R}, or {R}{R} —
        blue and red, not "any"."""
        assert color_sources(test_card("Cascade Bluffs")) == {"U", "R"}

    def test_any_one_color_of_several(self):
        """ "Add three mana of any one color" (Lotus Field) is any colour."""
        assert color_sources(test_card("Lotus Field")) == {"any"}

    def test_mentioning_mana_is_not_producing_it(self):
        """Trinisphere's "less than three mana" names no mana it adds."""
        assert color_sources(test_card("Trinisphere")) == set()

    def test_treasure_maker_is_not_a_color_source(self):
        """The Treasure token is the object with the mana ability (CR 111.10a); a
        one-shot sacrifice is ramp, not a colour source (this module's own decision)."""
        assert color_sources(test_card("Smothering Tithe")) == set()
        assert color_sources(test_card("Deadly Dispute")) == set()

    def test_landcycling_adds_no_color(self):
        """Basic landcycling puts the land into your hand (CR 702.29e); Ash Barrens's
        own mana is colorless."""
        assert color_sources(test_card("Ash Barrens")) == {"C"}

    def test_cryptic_spires_reads_any(self):
        """Cryptic Spires' two colours are circled as it goes into the deck (its
        rulings) — a deck-dependent producer, like Command Tower."""
        assert color_sources(test_card("Cryptic Spires")) == {"any"}

    def test_self_granted_mana_ability(self):
        """Urza's Saga chapter I: "This Saga gains '{T}: Add {C}.'"."""
        assert color_sources(test_card("Urza's Saga")) == {"C"}


class TestColorSourcesFetchLands:
    def test_polluted_delta(self):
        card = test_card("Polluted Delta")
        assert color_sources(card) == {"U", "B"}

    def test_prismatic_vista(self):
        card = test_card("Prismatic Vista")
        assert color_sources(card) == {"any"}

    def test_verdant_catacombs(self):
        card = test_card("Verdant Catacombs")
        assert color_sources(card) == {"B", "G"}

    def test_flooded_strand(self):
        card = test_card("Flooded Strand")
        assert color_sources(card) == {"W", "U"}

    def test_fabled_passage(self):
        card = test_card("Fabled Passage")
        assert color_sources(card) == {"any"}

    def test_seething_landscape(self):
        card = test_card("Seething Landscape")
        assert color_sources(card) == {"U", "B", "R"}

    def test_two_named_types(self):
        """Krosan Verge finds "a Forest card and a Plains card"; its own mana is {C}."""
        assert color_sources(test_card("Krosan Verge")) == {"G", "W"}

    def test_opponents_search_is_not_yours(self):
        """Ghost Quarter's basic land goes to the destroyed land's controller."""
        assert color_sources(test_card("Ghost Quarter")) == {"C"}


class TestFixingLand:
    def test_dual_and_any_color_lands_fix(self):
        for name in (
            "Overgrown Tomb",
            "Command Tower",
            "Lotus Field",
            "Cryptic Spires",
        ):
            assert is_fixing_land(test_card(name)) is True, name

    def test_fetch_land_fixes(self):
        assert is_fixing_land(test_card("Evolving Wilds")) is True

    def test_landcycling_any_basic_fixes(self):
        """Ash Barrens' basic landcycling puts a basic of your choice into your hand
        (CR 702.29e): a colour found, whatever the destination."""
        assert is_fixing_land(test_card("Ash Barrens")) is True

    def test_your_search_after_the_opponents(self):
        """Demolition Field: "That land's controller may search their library ...
        You may search your library for a basic land card, put it onto the
        battlefield" — the second search is yours."""
        field = test_card("Demolition Field")
        assert color_sources(field) == {"any"}
        assert is_fixing_land(field) is True

    def test_mono_and_colorless_lands_do_not(self):
        for name in ("Forest", "Ancient Tomb", "Ghost Quarter"):
            assert is_fixing_land(test_card(name)) is False, name


class TestCopyLimitExemptions:
    """CR 100.2a's four-of rule; the rulings of each card say its last ability
    "lets you ignore the 'four-of' rule"."""

    def test_any_number(self):
        rats = test_card("Relentless Rats")
        assert has_any_number_exemption(rats) is True
        assert named_card_cap(rats) is None

    def test_up_to_n(self):
        assert has_any_number_exemption(test_card("Seven Dwarves")) is False
        assert named_card_cap(test_card("Seven Dwarves")) == 7
        assert named_card_cap(test_card("Nazgûl")) == 9

    def test_ordinary_card(self):
        elves = test_card("Llanowar Elves")
        assert has_any_number_exemption(elves) is False
        assert named_card_cap(elves) is None


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

    def test_legendary_planeswalker_requires_text_by_default(self):
        # Commander's rule: a planeswalker needs "can be your commander".
        card = {"type_line": "Legendary Planeswalker — Jace"}
        result = is_commander(card)
        assert result == {"eligible": False, "requires_partner": False}

    def test_legendary_planeswalker_eligible_when_text_not_required(self):
        # The Brawl family's rule arrives as the flag (Format passes its own).
        card = {"type_line": "Legendary Planeswalker — Jace"}
        result = is_commander(card, planeswalker_commander_requires_text=False)
        assert result == {"eligible": True, "requires_partner": False}

    def test_can_be_your_commander_text(self):
        card = test_card("Teferi, Temporal Archmage")
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": False}

    def test_choose_a_background(self):
        card = test_card("Wilson, Refined Grizzly")
        result = is_commander(card)
        assert result == {"eligible": True, "requires_partner": True}

    def test_can_be_your_commander_read_by_phase(self):
        """Grist, the Hunger Tide's ruling: it "can be your commander as its first
        ability works before the game begins during deck construction" — phase's
        own verdict, where the old "can be your commander" text read missed it."""
        card = test_card("Grist, the Hunger Tide")
        assert is_commander(card) == {"eligible": True, "requires_partner": False}

    def test_plain_planeswalker_needs_the_brawl_flag(self):
        card = test_card("Chandra, Torch of Defiance")
        assert is_commander(card)["eligible"] is False
        assert is_commander(card, planeswalker_commander_requires_text=False)[
            "eligible"
        ]

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
        card = test_card("Savannah Lions")
        assert classify_cube_category(card) == "W"

    def test_mono_red_instant(self):
        card = test_card("Lightning Bolt")
        assert classify_cube_category(card) == "R"

    def test_multicolor(self):
        card = test_card("Lightning Helix")
        assert classify_cube_category(card) == "M"

    def test_multicolor_three_color(self):
        card = test_card("Esper Charm")
        assert classify_cube_category(card) == "M"

    def test_colorless_non_fixing_artifact(self):
        """Plain colorless artifact with no mana production → C."""
        card = test_card("Sensei's Divining Top")
        assert classify_cube_category(card) == "C"

    def test_colorless_creature(self):
        card = test_card("Ornithopter")
        assert classify_cube_category(card) == "C"

    def test_mana_producing_land(self):
        """A mono-color land that taps for mana → L (mana-producing land)."""
        card = test_card("Castle Embereth")
        assert classify_cube_category(card) == "L"

    def test_dual_land_goes_to_land_bucket(self):
        """Dual lands that tap for mana are L, not F. Fixing is about multi-
        color sources that don't just tap for mana directly."""
        card = test_card("Overgrown Tomb")
        assert classify_cube_category(card) == "L"

    def test_command_tower_is_land(self):
        """Command Tower taps for mana of any color → L (mana-producing)."""
        card = test_card("Command Tower")
        assert classify_cube_category(card) == "L"

    def test_evolving_wilds_is_fixing(self):
        """Evolving Wilds doesn't tap for mana — only sacrifices to fetch
        a basic. Per cube-utils, this is F (fixing)."""
        card = test_card("Evolving Wilds")
        assert classify_cube_category(card) == "F"

    def test_fetchland_is_fixing(self):
        """Fetch lands (Polluted Delta, Flooded Strand) don't tap for mana,
        only sacrifice to search → F."""
        card = test_card("Flooded Strand")
        assert classify_cube_category(card) == "F"

    def test_colorless_land_is_land_bucket(self):
        card = test_card("Ancient Tomb")
        assert classify_cube_category(card) == "L"

    def test_any_one_color_land_is_land_bucket(self):
        """Lotus Field taps for "three mana of any one color" → L (the old text read
        missed the number-word wording and filed it under F)."""
        assert classify_cube_category(test_card("Lotus Field")) == "L"

    def test_cryptic_spires_is_land_bucket(self):
        assert classify_cube_category(test_card("Cryptic Spires")) == "L"

    def test_self_granted_mana_is_land_bucket(self):
        assert classify_cube_category(test_card("Urza's Saga")) == "L"

    def test_basic_land_is_land_bucket(self):
        """A basic with no oracle text still produces mana via its type line → L.
        The real Mountain carries "({T}: Add {R}.)" reminder text; it is stripped
        here so the type-line branch is what classifies it."""
        card = {**test_card("Mountain"), "oracle_text": ""}
        assert classify_cube_category(card) == "L"

    def test_sol_ring_is_fixing(self):
        """Sol Ring: colorless artifact that produces mana → F (mana rock)."""
        card = test_card("Sol Ring")
        assert classify_cube_category(card) == "F"

    def test_arcane_signet_is_fixing(self):
        """Arcane Signet: mana rock that produces any color → F."""
        card = test_card("Arcane Signet")
        assert classify_cube_category(card) == "F"

    def test_cultivate_is_green(self):
        """Cultivate: green land-fetcher → G (slots into the green pack position)."""
        card = test_card("Cultivate")
        assert classify_cube_category(card) == "G"

    def test_sakura_tribe_elder_is_green(self):
        """Sakura-Tribe Elder: green creature → G, not F."""
        card = test_card("Sakura-Tribe Elder")
        assert classify_cube_category(card) == "G"

    def test_birds_of_paradise_is_green(self):
        """Mana dork with color identity G → G slot. Each pack reserves one
        mono-color slot per color, and Birds helps drafters committing to G."""
        card = test_card("Birds of Paradise")
        assert classify_cube_category(card) == "G"

    def test_llanowar_elves_is_green(self):
        """Mono-G mana dork → G bucket, not F."""
        card = test_card("Llanowar Elves")
        assert classify_cube_category(card) == "G"

    def test_wayfarers_bauble_is_fixing(self):
        """Colorless land-fetcher → F. No color identity, so no mono-color
        slot competes."""
        card = test_card("Wayfarer's Bauble")
        assert classify_cube_category(card) == "F"

    def test_chromatic_lantern_is_fixing(self):
        """Colorless mana rock producing any color → F."""
        card = test_card("Chromatic Lantern")
        assert classify_cube_category(card) == "F"

    def test_multicolor_non_fixing(self):
        """Multicolor creature that doesn't produce mana or fetch → M."""
        card = test_card("Aurelia, the Warleader")
        assert classify_cube_category(card) == "M"


class TestBuildCardLookup:
    def test_canonical_name(self):
        """Cards are indexed by their canonical name."""
        hydrated = [test_card("Lightning Bolt")]
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
        hydrated = [test_card("Hengegate Pathway // Mistgate Pathway")]
        lookup = build_card_lookup(hydrated)
        assert "Hengegate Pathway // Mistgate Pathway" in lookup
        assert "Hengegate Pathway" in lookup
        assert (
            lookup["Hengegate Pathway"]
            is lookup["Hengegate Pathway // Mistgate Pathway"]
        )

    def test_dfc_front_face_matches_only_land_back(self):
        """Aliasing covers DFCs whose back face is a land (flex lands)."""
        hydrated = [test_card("Shatterskull Smashing // Shatterskull, the Hammer Pass")]
        lookup = build_card_lookup(hydrated)
        assert "Shatterskull Smashing" in lookup

    def test_printed_name_alias(self):
        """Arena printed_name still resolves to the canonical card."""
        hydrated = [{**test_card("Masked Meower"), "printed_name": "Skittering Kitten"}]
        lookup = build_card_lookup(hydrated)
        assert "Masked Meower" in lookup
        assert "Skittering Kitten" in lookup

    def test_canonical_wins_over_alias(self):
        """When two cards collide on an alias, the canonical stays pinned.

        If card A's canonical name happens to equal card B's front-face
        or printed_name alias, A's entry must not be overwritten.
        """
        hydrated = [
            # Machinery: a record whose canonical name collides with the real
            # pathway's front-face alias (no real card does; the shape is the test).
            {"name": "Hengegate Pathway", "type_line": "Something Else"},
            test_card("Hengegate Pathway // Mistgate Pathway"),
        ]
        lookup = build_card_lookup(hydrated)
        # First card's canonical entry is preserved despite the second
        # card trying to alias onto the same key.
        assert lookup["Hengegate Pathway"]["type_line"] == "Something Else"

    def test_none_entries_skipped(self):
        """Hydration misses (None entries) don't crash the builder."""
        hydrated = [None, test_card("Lightning Bolt")]
        lookup = build_card_lookup(hydrated)
        assert "Lightning Bolt" in lookup

    def test_non_dfc_not_aliased(self):
        """Names without ' // ' don't generate bogus front-face aliases."""
        hydrated = [test_card("Lightning Bolt")]
        lookup = build_card_lookup(hydrated)
        # Exactly one entry; no accidental aliasing.
        assert len(lookup) == 1


class TestPartnerAbility:
    """Partner pairing variants (CR 702.124) drive the deck-forge partner avenue."""

    def test_plain_partner(self):
        # CR 702.124h: pairs with another card that has partner.
        c = test_card("Ishai, Ojutai Dragonspeaker")
        assert partner_abilities(c) == {PartnerAbility("plain")}
        assert valid_partner_search(c)["partner_of"] == [["plain", ""]]
        assert can_partner([("plain", "")], test_card("Thrasios, Triton Hero"))

    def test_partner_with_named_card_only(self):
        # CR 702.124j / 702.124f: pairs ONLY with the named card, never with a plain
        # partner.
        c = test_card("Krav, the Unredeemed")
        assert partner_abilities(c) == {PartnerAbility("with", "Regna, the Redeemer")}
        search = valid_partner_search(c)["partner_of"]
        assert can_partner(search, test_card("Regna, the Redeemer"))
        assert not can_partner(search, test_card("Thrasios, Triton Hero"))

    def test_partner_group_same_group_only(self):
        # CR 702.124i: each must have the SAME partner—[text] ability.
        c = test_card("Atreus, Impulsive Son")
        assert partner_abilities(c) == {PartnerAbility("group", "Father & son")}
        search = valid_partner_search(c)["partner_of"]
        assert can_partner(search, test_card("Kratos, Stoic Father"))
        assert not can_partner(search, test_card("Leonardo, the Balance"))
        assert not can_partner(search, test_card("Thrasios, Triton Hero"))

    def test_survivors_never_pair_with_plain_partner(self):
        # CR 702.124f: partner—Survivors and partner are distinct abilities.
        ellie = test_card("Ellie, Vengeful Hunter")
        assert partner_abilities(ellie) == {PartnerAbility("group", "Survivors")}
        search = valid_partner_search(ellie)["partner_of"]
        assert can_partner(search, test_card("Joel, Resolute Survivor"))
        assert not can_partner(search, test_card("Thrasios, Triton Hero"))
        assert not can_partner([("plain", "")], ellie)

    def test_phase_named_groups(self):
        c = test_card("Cecily, Haunted Mage")
        assert partner_abilities(c) == {PartnerAbility("group", "Friends forever")}
        assert can_partner(
            valid_partner_search(c)["partner_of"],
            test_card("Bjorna, Nightfall Alchemist"),
        )
        assert partner_abilities(test_card("Leonardo, the Balance")) == {
            PartnerAbility("group", "Character select")
        }

    def test_choose_a_background_pairs_with_backgrounds(self):
        c = test_card("Wilson, Refined Grizzly")
        assert partner_abilities(c) == {PartnerAbility("choose_background")}
        search = valid_partner_search(c)["partner_of"]
        assert can_partner(search, test_card("Far Traveler"))
        assert not can_partner(search, test_card("Thrasios, Triton Hero"))

    def test_background_pairs_with_choosers(self):
        c = test_card("Far Traveler")
        assert partner_abilities(c) == {PartnerAbility("background")}
        assert can_partner(
            valid_partner_search(c)["partner_of"], test_card("Wilson, Refined Grizzly")
        )

    def test_background_that_chooses_a_background(self):
        # Faceless One's ruling: it "both has choose a Background and is itself a
        # Background".
        assert partner_abilities(test_card("Faceless One")) == {
            PartnerAbility("background"),
            PartnerAbility("choose_background"),
        }

    def test_doctors_companion_pairs_with_doctors(self):
        # CR 702.124m: a legendary Time Lord Doctor creature card with no other
        # creature types.
        c = test_card("Sarah Jane Smith")
        assert partner_abilities(c) == {PartnerAbility("doctors_companion")}
        assert can_partner(
            valid_partner_search(c)["partner_of"], test_card("The Tenth Doctor")
        )

    def test_time_lord_doctor_pairs_with_companions(self):
        c = test_card("The Tenth Doctor")
        assert partner_abilities(c) == {PartnerAbility("doctor")}
        assert can_partner(
            valid_partner_search(c)["partner_of"], test_card("Sarah Jane Smith")
        )

    def test_two_partner_abilities(self):
        # Amy Pond's rulings: two partner abilities; she uses one or the other (CR
        # 702.124g).
        amy = test_card("Amy Pond")
        assert partner_abilities(amy) == {
            PartnerAbility("doctors_companion"),
            PartnerAbility("with", "Rory Williams"),
        }
        search = valid_partner_search(amy)["partner_of"]
        assert can_partner(search, test_card("Rory Williams"))
        assert can_partner(search, test_card("The Tenth Doctor"))
        assert not can_partner(search, test_card("Thrasios, Triton Hero"))

    def test_a_saga_is_no_companion(self):
        assert partner_abilities(test_card("An Unearthly Child")) == frozenset()

    def test_no_partner_ability(self):
        c = test_card("Llanowar Elves")
        assert partner_abilities(c) == frozenset()
        assert valid_partner_search(c) is None

    def test_partner_searches_are_color_agnostic(self):
        # Legal partners aren't restricted by color identity (CR 702.124c union).
        for name in ("Ishai, Ojutai Dragonspeaker", "Krav, the Unredeemed"):
            assert valid_partner_search(test_card(name))["color_identity"] == "WUBRG"
