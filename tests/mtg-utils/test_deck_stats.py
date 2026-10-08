"""Tests for deck statistics calculator."""

import json

from click.testing import CliRunner

from mtg_utils.deck_stats import (
    deck_stats,
    detect_bracket,
    main,
    render_text_report,
)
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.parse_deck import parse_deck
from mtg_utils.testkit import test_card


def _hd(deck, hydrated):
    """A HydratedDeck for the analysis under test (records= is the CLI/file path)."""
    return HydratedDeck.from_parsed(deck, records=hydrated)


def _gc(name):
    """A fictional game changer (machinery: only the flag is read)."""
    return {"name": name, "game_changer": True, "oracle_text": "", "type_line": "X"}


def _plain(name):
    return {"name": name, "oracle_text": "Draw a card.", "type_line": "Sorcery"}


class TestDetectBracket:
    """Mechanical Commander-bracket estimate from game changers, mass land denial,
    and curve speed (the signals we can read deterministically)."""

    def test_no_pillars_is_core(self):
        b = detect_bracket([_plain("a"), _plain("b")], 3.0)
        assert b["bracket"] == 2
        assert b["name"] == "Core"

    def test_one_game_changer_is_upgraded(self):
        # game_changer is a Scryfall-served flag the snapshot doesn't carry.
        tithe = {**test_card("Smothering Tithe"), "game_changer": True}
        b = detect_bracket([tithe, _plain("x")], 3.0)
        assert b["bracket"] == 3
        assert "Smothering Tithe" in b["game_changers"]

    def test_four_game_changers_is_optimized(self):
        b = detect_bracket([_gc(f"G{i}") for i in range(4)], 3.0)
        assert b["bracket"] == 4

    def test_mass_land_denial_is_optimized(self):
        b = detect_bracket([test_card("Armageddon"), _plain("x")], 3.0)
        assert b["bracket"] == 4
        assert "Armageddon" in b["mass_land_denial"]

    def test_fast_curve_flag(self):
        assert detect_bracket([_plain("a")], 1.8)["fast_curve"] is True
        assert detect_bracket([_plain("a")], 3.5)["fast_curve"] is False


class TestDeckStats:
    def test_total_cards(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # 1 commander + 10 cards = 11
        assert result["total_cards"] == 11

    def test_land_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # Command Tower + Overgrown Tomb
        assert result["land_count"] == 2

    def test_creature_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # Korvold (commander, creature), Viscera Seer, Blood Artist, Sakura-Tribe Elder
        assert result["creature_count"] == 4

    def test_ramp_count(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # Sol Ring, Sakura-Tribe Elder, Cultivate, Ashnod's Altar
        assert result["ramp_count"] == 4

    def test_avg_cmc_nonlands(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # Nonland cards: Korvold(5), Viscera Seer(1), Blood Artist(2),
        # Sakura-Tribe Elder(2), Deadly Rollick(4), Cultivate(3),
        # Sol Ring(1), Ashnod's Altar(3), Dictate of Erebos(5)
        # = 26 / 9 = 2.89 (rounded)
        expected = round(26.0 / 9, 2)
        assert result["avg_cmc"] == expected

    def test_curve_populated(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        assert isinstance(result["curve"], dict)
        # CMC 1 should have Sol Ring + Viscera Seer = 2
        assert result["curve"][1] == 2

    def test_color_sources(self, moxfield_deck, hydrated_cards):
        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards
        result = deck_stats(_hd(deck, hydrated))
        # Command Tower -> any, Overgrown Tomb -> B,G, Sol Ring -> C, Ashnod's Altar -> C
        assert "any" in result["color_sources"]
        assert "B" in result["color_sources"]
        assert "G" in result["color_sources"]


class TestAlternativeCostCards:
    def test_detects_suspend_cards(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(_hd(deck, alt_cost_cards))
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        assert "Star Whale" in alt
        assert any(a["type"] == "suspend" for a in alt["Star Whale"]["alt_costs"])

    def test_detects_suspend_cost(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(_hd(deck, alt_cost_cards))
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        star_whale_suspend = next(
            a for a in alt["Star Whale"]["alt_costs"] if a["type"] == "suspend"
        )
        assert "{1}{U}" in star_whale_suspend["cost"]

    def test_detects_evoke(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(_hd(deck, alt_cost_cards))
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        assert "Fury" in alt
        assert any(a["type"] == "evoke" for a in alt["Fury"]["alt_costs"])

    def test_excludes_non_alt_cost_keywords(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(_hd(deck, alt_cost_cards))
        alt = {c["name"]: c for c in result["alternative_cost_cards"]}
        # Ward, Flying, Vigilance, Trample, Double strike, Delve are NOT alternative costs
        assert "Sol Ring" not in alt
        assert "Command Tower" not in alt
        assert "Goldvein Hydra" not in alt
        assert "Murderous Cut" not in alt

    def test_omits_cards_without_alt_costs(self, alt_cost_cards):
        deck = {
            "commanders": [],
            "cards": [{"name": c["name"], "quantity": 1} for c in alt_cost_cards],
        }
        result = deck_stats(_hd(deck, alt_cost_cards))
        alt_names = {c["name"] for c in result["alternative_cost_cards"]}
        assert "Sol Ring" not in alt_names
        assert "Command Tower" not in alt_names


def _alt_costs(*names):
    deck = {"commanders": [], "cards": [{"name": n, "quantity": 1} for n in names]}
    result = deck_stats(_hd(deck, [test_card(n) for n in names]))
    return {c["name"]: c["alt_costs"] for c in result["alternative_cost_cards"]}


class TestAlternativeCostKinds:
    """Each row says what the rules make of the payment (``cost_kind``)."""

    def test_display_formats(self):
        alt = _alt_costs("Ancestral Vision", "Phyrexian Fleshgorger")
        assert {"type": "suspend", "cost": "4—{U}", "cost_kind": "special_action"} in (
            alt["Ancestral Vision"]
        )
        assert alt["Phyrexian Fleshgorger"] == [
            {
                "type": "prototype",
                "cost": "{1}{B}{B} — 3/3",
                "cost_kind": "alternative_characteristics",
            }
        ]

    def test_buyback_and_retrace_are_additional_costs(self):
        # Buyback: "You may pay an additional [cost]" (CR 702.27a). Retrace: cast from
        # the graveyard "by discarding a land card as an additional cost" (702.81a) —
        # it prints no cost of its own, so the row shows the discard.
        alt = _alt_costs("Capsize", "Raven's Crime")
        assert alt["Capsize"] == [
            {"type": "buyback", "cost": "{3}", "cost_kind": "additional"}
        ]
        assert alt["Raven's Crime"] == [
            {
                "type": "retrace",
                "cost": "Discard a land card",
                "cost_kind": "additional",
            }
        ]

    def test_ninjutsu_is_an_ability_not_a_cast(self):
        alt = _alt_costs("Yuriko, the Tiger's Shadow")
        assert alt["Yuriko, the Tiger's Shadow"] == [
            {"type": "commander ninjutsu", "cost": "{U}{B}", "cost_kind": "ability"}
        ]

    def test_adventure_is_the_other_face(self):
        alt = _alt_costs("Bonecrusher Giant // Stomp")
        assert alt["Bonecrusher Giant // Stomp"] == [
            {"type": "adventure", "cost": "{1}{R}", "cost_kind": "other_face"}
        ]

    def test_dropped_keyword_cost_is_read_off_its_line(self):
        # Phase drops "Morph—Pay 5 life" from Zombie Cutthroat's keywords; the tree
        # build recovers it off the card's own morph line.
        alt = _alt_costs("Zombie Cutthroat", "Tenacious Underdog")
        assert alt["Zombie Cutthroat"] == [
            {"type": "morph", "cost": "{3} (face down)", "cost_kind": "alternative"},
            {
                "type": "morph (face up)",
                "cost": "Pay 5 life",
                "cost_kind": "special_action",
            },
        ]
        assert alt["Tenacious Underdog"] == [
            {
                "type": "blitz",
                "cost": "{2}{B}{B}, Pay 2 life",
                "cost_kind": "alternative",
            }
        ]

    def test_granting_plot_is_not_a_plot_cost(self):
        # Fblthp lets the top card of your library be plotted; it has no plot cost.
        assert _alt_costs("Fblthp, Lost on the Range") == {}


class TestMassLandDenial:
    """The Commander Brackets' definition: destroy, exile or bounce lands, keep them
    tapped, or change their mana, four or more per player, not replaced."""

    def test_definition_examples(self):
        names = ["Ruination", "Sunder", "Winter Orb", "Blood Moon", "Wildfire"]
        b = detect_bracket([test_card(n) for n in names], 3.0)
        assert b["mass_land_denial"] == sorted(names)

    def test_all_permanent_sweeps_and_bridged_parses(self):
        # Exile or bounce of every permanent takes the lands; Burning of Xinye and
        # Global Ruin fire through ledger bridges over phase's parse failures.
        names = ["Apocalypse", "Upheaval", "Burning of Xinye", "Global Ruin"]
        b = detect_bracket([test_card(n) for n in names], 3.0)
        assert b["mass_land_denial"] == sorted(names)

    def test_one_land_edicts_and_replacements_are_not(self):
        names = [
            "Yawning Fissure",
            "Tremble",
            "From the Ashes",
            "Mungha Wurm",
            "Exhaustion",  # one untap step
            "Nightcreep",  # one turn
            "End Hostilities",  # only permanents attached to creatures
        ]
        b = detect_bracket([test_card(n) for n in names], 3.0)
        assert b["mass_land_denial"] == []
        assert b["bracket"] == 2


class TestSideboardStats:
    def test_sideboard_stats_present(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [
                {"name": "Two-Drop Trick", "quantity": 3},
                {"name": "One-Drop Trick", "quantity": 2},
            ],
        }
        hydrated = [
            test_card("Lightning Bolt"),
            {"name": "Two-Drop Trick", "cmc": 2.0, "type_line": "Instant"},
            {"name": "One-Drop Trick", "cmc": 1.0, "type_line": "Instant"},
        ]
        result = deck_stats(_hd(deck, hydrated))
        assert result["sideboard_total"] == 5
        assert result["sideboard_curve"] == {1: 2, 2: 3}

    def test_no_sideboard_stats_when_empty(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [],
        }
        hydrated = [
            test_card("Lightning Bolt"),
        ]
        result = deck_stats(_hd(deck, hydrated))
        assert "sideboard_total" not in result

    def test_no_sideboard_stats_when_absent(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        hydrated = [
            test_card("Lightning Bolt"),
        ]
        result = deck_stats(_hd(deck, hydrated))
        assert "sideboard_total" not in result

    def test_sideboard_text_report(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "One-Drop Trick", "quantity": 4}],
            "sideboard": [{"name": "Two-Drop Trick", "quantity": 3}],
        }
        hydrated = [
            {"name": "One-Drop Trick", "cmc": 1.0, "type_line": "Instant"},
            {"name": "Two-Drop Trick", "cmc": 2.0, "type_line": "Instant"},
        ]
        result = deck_stats(_hd(deck, hydrated))
        report = render_text_report(result)
        assert "Sideboard: 3 cards" in report


class TestCLI:
    def test_text_report_and_json_file(self, moxfield_deck, hydrated_cards, tmp_path):
        from conftest import json_from_cli_output

        deck = parse_deck(moxfield_deck)
        hydrated = hydrated_cards

        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(deck))
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(hydrated))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        assert "deck-stats:" in result.output
        assert "Avg CMC" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert "total_cards" in data
        assert "land_count" in data
        assert "avg_cmc" in data
