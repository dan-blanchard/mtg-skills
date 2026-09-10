"""Tests for export_deck module."""

import json

from click.testing import CliRunner

from mtg_utils.export_deck import export_moxfield, main

SAMPLE_DECK = {
    "commanders": [{"name": "Kalain, Reclusive Painter", "quantity": 1}],
    "cards": [
        {"name": "Sol Ring", "quantity": 1},
        {"name": "Swamp", "quantity": 8},
        {"name": "Mountain", "quantity": 7},
    ],
    "total_cards": 17,
}


class TestExportMoxfield:
    def test_outputs_quantity_name_lines(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert lines[0] == "1 Kalain, Reclusive Painter"
        assert lines[1] == "1 Sol Ring"
        assert lines[2] == "8 Swamp"
        assert lines[3] == "7 Mountain"

    def test_commanders_come_first(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert "Kalain" in lines[0]

    def test_line_count_matches_entries(self):
        result = export_moxfield(SAMPLE_DECK)
        lines = result.strip().split("\n")
        assert len(lines) == 4

    def test_empty_deck(self):
        result = export_moxfield({"commanders": [], "cards": []})
        assert result == ""


class TestSideboardExport:
    def test_sideboard_section_present(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [
                {"name": "Smash to Smithereens", "quantity": 3},
                {"name": "Roiling Vortex", "quantity": 2},
            ],
        }
        result = export_moxfield(deck)
        lines = result.split("\n")
        assert "Sideboard" in lines
        sb_start = lines.index("Sideboard")
        assert lines[sb_start - 1] == ""  # blank line before Sideboard
        assert lines[sb_start + 1] == "3 Smash to Smithereens"
        assert lines[sb_start + 2] == "2 Roiling Vortex"

    def test_no_sideboard_section_when_empty(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [],
        }
        result = export_moxfield(deck)
        assert "Sideboard" not in result

    def test_no_sideboard_section_when_absent(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        result = export_moxfield(deck)
        assert "Sideboard" not in result


class TestCLI:
    def test_outputs_text(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))
        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path)])
        assert result.exit_code == 0
        assert "1 Sol Ring" in result.output
        assert "1 Kalain, Reclusive Painter" in result.output


class TestCompanionExport:
    def test_companion_section_present_and_round_trips(self):
        from mtg_utils.parse_deck import parse_deck_text

        deck = {
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "companion": [{"name": "Keruga, the Macrosage", "quantity": 1}],
        }
        result = export_moxfield(deck)
        lines = result.split("\n")
        assert "Companion" in lines
        idx = lines.index("Companion")
        assert lines[idx - 1] == ""  # blank line before the section header
        assert lines[idx + 1] == "1 Keruga, the Macrosage"
        # Round-trip: parse_deck_text routes the section back into the
        # companion zone (outside the deck and sideboard, CR 702.139a-b).
        parsed = parse_deck_text(result, format="modern")
        assert parsed["companion"] == [{"name": "Keruga, the Macrosage", "quantity": 1}]
        assert "Keruga, the Macrosage" not in {e["name"] for e in parsed["cards"]}

    def test_no_companion_section_when_absent(self):
        assert "Companion" not in export_moxfield(SAMPLE_DECK)


class TestArenaStyle:
    """Arena's importer needs a ``Commander`` header to put the commander in the
    command zone and a ``Deck`` header before the mainboard; bare Moxfield lines
    import the commander as a 101st main-deck card."""

    ARENA_DECK = {
        "format": "competitive_brawl",
        "commanders": [{"name": "The Lord of the Eagles", "quantity": 1}],
        "cards": [
            {"name": "Island", "quantity": 30},
            {"name": "Counterspell", "quantity": 1},
        ],
    }

    def test_arena_layout_has_section_headers(self):
        from mtg_utils.export_deck import export_arena

        lines = export_arena(self.ARENA_DECK).split("\n")
        assert lines[0] == "Commander"
        assert lines[1] == "1 The Lord of the Eagles"
        assert lines[2] == ""
        assert lines[3] == "Deck"
        assert lines[4] == "30 Island"
        assert lines[5] == "1 Counterspell"

    def test_arena_layout_round_trips_through_parse_deck(self):
        from mtg_utils.export_deck import export_arena
        from mtg_utils.parse_deck import parse_deck_text

        parsed = parse_deck_text(
            export_arena(self.ARENA_DECK), format="competitive_brawl"
        )
        assert parsed["commanders"] == [
            {"name": "The Lord of the Eagles", "quantity": 1}
        ]
        assert {e["name"] for e in parsed["cards"]} == {"Island", "Counterspell"}
        assert parsed["total_cards"] == 32

    def test_arena_layout_sideboard_and_companion(self):
        from mtg_utils.export_deck import export_arena

        deck = {
            "format": "historic",
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [{"name": "Roiling Vortex", "quantity": 2}],
            "companion": [{"name": "Lurrus of the Dream-Den", "quantity": 1}],
        }
        lines = export_arena(deck).split("\n")
        assert lines[:3] == ["Companion", "1 Lurrus of the Dream-Den", ""]
        assert lines[3:5] == ["Deck", "4 Lightning Bolt"]
        assert lines[5:] == ["", "Sideboard", "2 Roiling Vortex"]

    def test_auto_style_picks_arena_for_arena_formats(self):
        from mtg_utils.export_deck import resolve_style

        assert resolve_style({"format": "competitive_brawl"}) == "arena"
        assert resolve_style({"format": "historic_brawl"}) == "arena"
        assert resolve_style({"format": "standard"}) == "arena"
        assert resolve_style({"format": "commander"}) == "moxfield"
        assert resolve_style({"format": "modern"}) == "moxfield"
        assert resolve_style({}) == "moxfield"
        assert resolve_style({"format": "commander"}, "arena") == "arena"

    def test_cli_auto_emits_headers_for_arena_deck(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(self.ARENA_DECK))
        result = CliRunner().invoke(main, [str(deck_path)])
        assert result.exit_code == 0, result.output
        assert result.output.startswith("Commander\n1 The Lord of the Eagles\n\nDeck\n")

    def test_cli_moxfield_style_override(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(self.ARENA_DECK))
        result = CliRunner().invoke(main, [str(deck_path), "--style", "moxfield"])
        assert result.exit_code == 0, result.output
        assert result.output.startswith("1 The Lord of the Eagles\n30 Island\n")

    def test_cli_paper_deck_stays_moxfield(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(SAMPLE_DECK))  # no "format" key
        result = CliRunner().invoke(main, [str(deck_path)])
        assert result.exit_code == 0, result.output
        assert "Commander" not in result.output
        assert result.output.startswith("1 Kalain, Reclusive Painter\n")
