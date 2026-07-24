"""Tests for deck list parser."""

import json

from click.testing import CliRunner

from mtg_utils.parse_deck import main, parse_deck, parse_deck_text


class TestSuffixAndDedup:
    def test_strips_foil_marker_after_collector_number(self):
        # Moxfield/Archidekt append a foil/etched marker after the collector number.
        text = "// Deck\n1 Sol Ring (C21) 263 *F*\n1 Island (UNF) 234 *E*\n"
        names = {c["name"] for c in parse_deck_text(text)["cards"]}
        assert names == {"Sol Ring", "Island"}

    def test_commander_in_header_and_body_is_deduped(self):
        text = (
            "// Commander\n"
            "1 Korvold, Fae-Cursed King\n"
            "// Deck\n"
            "1 Korvold, Fae-Cursed King\n"
            "1 Sol Ring\n"
        )
        result = parse_deck_text(text)
        assert [c["name"] for c in result["commanders"]] == ["Korvold, Fae-Cursed King"]
        body = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" not in body  # command zone wins (singleton)
        assert "Sol Ring" in body


class TestParseMoxfield:
    def test_parses_commander(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert result["commanders"] == [
            {"name": "Korvold, Fae-Cursed King", "quantity": 1}
        ]

    def test_parses_cards(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Viscera Seer" in card_names
        assert "Blood Artist" in card_names
        assert "Sol Ring" in card_names
        assert "Command Tower" in card_names

    def test_excludes_commander_from_cards(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" not in card_names

    def test_quantities(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        cards_by_name = {c["name"]: c for c in result["cards"]}
        assert cards_by_name["Viscera Seer"]["quantity"] == 1

    def test_partner_commanders(self, partner_deck):
        result = parse_deck(partner_deck)
        names = sorted(c["name"] for c in result["commanders"])
        assert names == ["Thrasios, Triton Hero", "Tymna the Weaver"]


class TestParseMTGO:
    def test_parses_cards(self, mtgo_deck):
        result = parse_deck(mtgo_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Viscera Seer" in card_names

    def test_no_commander_without_section(self, mtgo_deck):
        result = parse_deck(mtgo_deck)
        assert result["commanders"] == []


class TestParsePlainText:
    def test_parses_names(self, plain_deck):
        result = parse_deck(plain_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Viscera Seer" in card_names

    def test_default_quantity_one(self, plain_deck):
        result = parse_deck(plain_deck)
        for card in result["cards"]:
            assert card["quantity"] == 1


class TestArenaExport:
    """Arena exports use bare section headers like 'Commander' and 'Deck'."""

    def test_arena_commander_section(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Commander\n"
            "1 Sliver Weftwinder (Y25) 25\n"
            "\n"
            "Deck\n"
            "1 Sol Ring (C21) 263\n"
            "1 Command Tower (C21) 284\n"
        )
        result = parse_deck(deck_path)
        assert len(result["commanders"]) == 1
        assert result["commanders"][0]["name"] == "Sliver Weftwinder"
        card_names = [c["name"] for c in result["cards"]]
        assert "Sol Ring" in card_names
        assert "Command Tower" in card_names
        # Headers must NOT appear as cards
        assert "Commander" not in card_names
        assert "Deck" not in card_names

    def test_arena_headers_not_in_cards(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Commander\n"
            "1 Korvold, Fae-Cursed King (ELD) 329\n"
            "\n"
            "Deck\n"
            "1 Mountain (ELD) 265\n"
            "\n"
            "Sideboard\n"
            "1 Island (ELD) 254\n"
        )
        result = parse_deck(deck_path)
        all_names = [c["name"] for c in result["commanders"]] + [
            c["name"] for c in result["cards"]
        ]
        for header in ("Commander", "Deck", "Sideboard"):
            assert header not in all_names


class TestParseCSV:
    def test_parses_csv(self, csv_deck):
        result = parse_deck(csv_deck)
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in card_names
        assert "Sol Ring" in card_names

    def test_csv_handles_commas_in_card_names(self, csv_deck):
        """Card names with commas (e.g., 'Korvold, Fae-Cursed King') must survive CSV parsing."""
        result = parse_deck(csv_deck)
        cards_by_name = {c["name"]: c for c in result["cards"]}
        assert "Korvold, Fae-Cursed King" in cards_by_name
        assert cards_by_name["Korvold, Fae-Cursed King"]["quantity"] == 1


class TestCommanderDictFormat:
    def test_commanders_are_dicts(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert len(result["commanders"]) == 1
        assert result["commanders"][0] == {
            "name": "Korvold, Fae-Cursed King",
            "quantity": 1,
        }

    def test_partner_commanders_are_dicts(self, partner_deck):
        result = parse_deck(partner_deck)
        names = sorted(c["name"] for c in result["commanders"])
        assert names == ["Thrasios, Triton Hero", "Tymna the Weaver"]
        for cmd in result["commanders"]:
            assert cmd["quantity"] == 1


class TestSetCodeStripping:
    def test_strips_moxfield_set_codes(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "1 Obeka, Splitter of Seconds (OTJ) 222\n"
            "1 Ancestral Vision (TSR) 52\n"
            "1 Sphinx of the Second Sun (PLST) CMR-99\n"
        )
        result = parse_deck(deck_path)
        names = [c["name"] for c in result["cards"]]
        assert "Obeka, Splitter of Seconds" in names
        assert "Ancestral Vision" in names
        assert "Sphinx of the Second Sun" in names


class TestFormatDetection:
    def test_detects_moxfield(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert len(result["commanders"]) > 0

    def test_detects_csv(self, csv_deck):
        result = parse_deck(csv_deck)
        assert len(result["cards"]) > 0


class TestTotalCards:
    def test_moxfield_total_cards(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        expected = sum(c["quantity"] for c in result["commanders"]) + sum(
            c["quantity"] for c in result["cards"]
        )
        assert result["total_cards"] == expected

    def test_mtgo_total_cards(self, mtgo_deck):
        result = parse_deck(mtgo_deck)
        expected = sum(c["quantity"] for c in result["cards"])
        assert result["total_cards"] == expected

    def test_total_cards_counts_multiples(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("2 Island\n3 Mountain\n1 Sol Ring\n")
        result = parse_deck(deck_path)
        assert result["total_cards"] == 6

    def test_owned_cards_initialized_empty(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert result["owned_cards"] == []

    def test_cli_includes_total_cards(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(main, [str(moxfield_deck)])
        data = json.loads(result.output)
        assert "total_cards" in data


class TestCLI:
    def test_outputs_json(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(main, [str(moxfield_deck)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "commanders" in data
        assert "cards" in data

    def test_output_flag_writes_file(self, moxfield_deck, tmp_path):
        runner = CliRunner()
        out_path = tmp_path / "nested" / "parsed.json"
        result = runner.invoke(main, [str(moxfield_deck), "--output", str(out_path)])
        assert result.exit_code == 0
        assert "parse-deck:" in result.output
        assert str(out_path.resolve()) in result.output
        assert '"commanders":' not in result.output
        data = json.loads(out_path.read_text())
        assert "commanders" in data
        assert "cards" in data

    def test_output_flag_refuses_same_path(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(
            main, [str(moxfield_deck), "--output", str(moxfield_deck)]
        )
        assert result.exit_code != 0
        assert "overwrite" in result.output


class TestFormatAndDeckSize:
    def test_default_format_is_commander(self, moxfield_deck):
        result = parse_deck(moxfield_deck)
        assert result["format"] == "commander"
        assert result["deck_size"] == 100

    def test_format_brawl(self, moxfield_deck):
        result = parse_deck(moxfield_deck, format="brawl")
        assert result["format"] == "brawl"
        assert result["deck_size"] == 60

    def test_format_historic_brawl(self, moxfield_deck):
        result = parse_deck(moxfield_deck, format="historic_brawl")
        assert result["format"] == "historic_brawl"
        assert result["deck_size"] == 100

    def test_explicit_deck_size_overrides_format(self, moxfield_deck):
        result = parse_deck(moxfield_deck, format="historic_brawl", deck_size=60)
        assert result["format"] == "historic_brawl"
        assert result["deck_size"] == 60

    def test_cli_format_flag(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(main, [str(moxfield_deck), "--format", "brawl"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["format"] == "brawl"
        assert data["deck_size"] == 60

    def test_cli_deck_size_flag(self, moxfield_deck):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(moxfield_deck), "--format", "historic_brawl", "--deck-size", "60"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["format"] == "historic_brawl"
        assert data["deck_size"] == 60


# ---------- Sideboard parsing ----------


class TestSideboardParsing:
    def test_moxfield_sideboard(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "//Deck\n4 Lightning Bolt\n4 Mountain\n\n"
            "//Sideboard\n2 Smash to Smithereens\n1 Roiling Vortex\n"
        )
        result = parse_deck(deck_path, format="pioneer")
        assert len(result["sideboard"]) == 2
        sb_names = [c["name"] for c in result["sideboard"]]
        assert "Smash to Smithereens" in sb_names
        assert "Roiling Vortex" in sb_names
        assert result["total_sideboard"] == 3

    def test_mtgo_sideboard(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Deck\n4 Lightning Bolt\n4 Mountain\n\nSideboard\n2 Smash to Smithereens\n"
        )
        result = parse_deck(deck_path, format="standard")
        assert len(result["sideboard"]) == 1
        assert result["sideboard"][0]["name"] == "Smash to Smithereens"
        assert result["sideboard"][0]["quantity"] == 2
        assert result["total_sideboard"] == 2

    def test_plain_text_sideboard(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("Deck\n4 Lightning Bolt\n\nSideboard\n3 Roiling Vortex\n")
        result = parse_deck(deck_path, format="modern")
        assert len(result["sideboard"]) == 1
        assert result["total_sideboard"] == 3

    def test_sideboard_not_in_total_cards(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("Deck\n4 Lightning Bolt\n\nSideboard\n2 Smash\n")
        result = parse_deck(deck_path, format="pioneer")
        assert result["total_cards"] == 4
        assert result["total_sideboard"] == 2

    def test_commander_folds_sideboard_into_cards(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Commander\n1 Aesi, Tyrant of Gyre Strait\n\n"
            "Deck\n30 Forest\n\nSideboard\n1 Sol Ring\n"
        )
        result = parse_deck(deck_path, format="commander")
        assert result["sideboard"] == []
        assert result["total_sideboard"] == 0
        card_names = [c["name"] for c in result["cards"]]
        assert "Sol Ring" in card_names
        assert result["total_cards"] == 32

    def test_sideboard_set_codes_stripped(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Deck\n4 Lightning Bolt (M25) 141\n\n"
            "Sideboard\n2 Smash to Smithereens (MM2) 133\n"
        )
        result = parse_deck(deck_path, format="pioneer")
        assert result["sideboard"][0]["name"] == "Smash to Smithereens"

    def test_sideboard_size_from_config(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("Deck\n4 Mountain\n")
        result = parse_deck(deck_path, format="pioneer")
        assert result["sideboard_size"] == 15

    def test_commander_sideboard_size_zero(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("//Commander\n1 Aesi\n\n//Deck\n4 Forest\n")
        result = parse_deck(deck_path, format="commander")
        assert result["sideboard_size"] == 0

    def test_cli_reports_sideboard_count(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text("Deck\n4 Lightning Bolt\n\nSideboard\n2 Smash\n")
        output_path = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(deck_path), "--format", "pioneer", "--output", str(output_path)],
        )
        assert result.exit_code == 0
        assert "2 sideboard" in result.output


# ---------- Printing retention (set / collector_number / finish) ----------


class TestPrintingRetention:
    def test_moxfield_suffix_retained(self):
        text = "// Deck\n1 Sol Ring (C21) 263\n"
        card = parse_deck_text(text)["cards"][0]
        assert card["name"] == "Sol Ring"
        assert card["set"] == "c21"
        assert card["collector_number"] == "263"
        assert "finish" not in card

    def test_foil_marker_sets_finish(self):
        text = "// Deck\n1 Lightning Bolt (2X2) 117 *F*\n"
        card = parse_deck_text(text, format="modern")["cards"][0]
        assert card["name"] == "Lightning Bolt"
        assert card["set"] == "2x2"
        assert card["collector_number"] == "117"
        assert card["finish"] == "foil"

    def test_etched_marker_sets_finish(self):
        text = "// Deck\n1 Sol Ring (C21) 263 *E*\n"
        card = parse_deck_text(text)["cards"][0]
        assert card["finish"] == "etched"

    def test_no_suffix_means_no_printing_keys(self):
        text = "// Deck\n1 Sol Ring\n"
        card = parse_deck_text(text)["cards"][0]
        assert card == {"name": "Sol Ring", "quantity": 1}

    def test_non_numeric_collector_numbers_kept_as_strings(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "1 Serum Visions (SLD) 263★\n"
            "1 Brainstorm (MH2) 123a\n"
            "1 Sphinx of the Second Sun (PLST) CMR-99\n"
        )
        result = parse_deck(deck_path)
        by_name = {c["name"]: c for c in result["cards"]}
        assert by_name["Serum Visions"]["collector_number"] == "263★"
        assert by_name["Brainstorm"]["collector_number"] == "123a"
        assert by_name["Sphinx of the Second Sun"]["collector_number"] == "CMR-99"

    def test_arena_export_suffix_retained(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Commander\n1 Korvold, Fae-Cursed King (ELD) 329\n\nDeck\n1 Mountain (ELD) 265\n"
        )
        result = parse_deck(deck_path)
        assert result["commanders"][0]["set"] == "eld"
        assert result["commanders"][0]["collector_number"] == "329"
        assert result["cards"][0]["set"] == "eld"
        assert result["cards"][0]["collector_number"] == "265"

    def test_conflicting_printings_merge_drops_keys(self):
        # Same card from two printings merges to one entry; an ambiguous
        # printing key is dropped rather than guessing which one wins.
        text = "// Deck\n2 Ethereal Armor (DSK) 7\n2 Ethereal Armor (RTR) 9\n"
        result = parse_deck_text(text, format="modern")
        assert result["cards"] == [{"name": "Ethereal Armor", "quantity": 4}]

    def test_matching_printings_merge_keeps_keys(self):
        text = "// Deck\n2 Ethereal Armor (RTR) 9\n2 Ethereal Armor (RTR) 9\n"
        card = parse_deck_text(text, format="modern")["cards"][0]
        assert card["quantity"] == 4
        assert card["set"] == "rtr"
        assert card["collector_number"] == "9"


class TestCSVPrintingColumns:
    def test_csv_printing_columns_captured(self, tmp_path):
        deck_path = tmp_path / "deck.csv"
        deck_path.write_text(
            "Count,Name,Edition,Foil,Collector Number\n"
            "1,Sol Ring,c21,,263\n"
            '1,"Korvold, Fae-Cursed King",eld,foil,329\n'
            "1,Brainstorm,sld,etched,263★\n"
        )
        result = parse_deck(deck_path)
        by_name = {c["name"]: c for c in result["cards"]}
        assert by_name["Sol Ring"]["set"] == "c21"
        assert by_name["Sol Ring"]["collector_number"] == "263"
        assert "finish" not in by_name["Sol Ring"]
        assert by_name["Korvold, Fae-Cursed King"]["finish"] == "foil"
        assert by_name["Brainstorm"]["finish"] == "etched"
        assert by_name["Brainstorm"]["collector_number"] == "263★"

    def test_csv_without_printing_columns_still_parses(self, csv_deck):
        result = parse_deck(csv_deck)
        by_name = {c["name"]: c for c in result["cards"]}
        assert "Sol Ring" in by_name
        for card in result["cards"]:
            assert "set" not in card
            assert "collector_number" not in card
            assert "finish" not in card


# ---------- Companion zone (CR 702.139a-b) ----------


class TestCompanionZone:
    def test_arena_companion_section(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Companion\n"
            "1 Jegantha, the Wellspring\n"
            "\n"
            "Deck\n"
            "4 Lightning Bolt\n"
            "4 Mountain\n"
        )
        result = parse_deck(deck_path, format="modern")
        assert result["companion"] == [
            {"name": "Jegantha, the Wellspring", "quantity": 1}
        ]
        card_names = [c["name"] for c in result["cards"]]
        assert "Jegantha, the Wellspring" not in card_names

    def test_companion_not_counted_in_totals(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Companion\n1 Lurrus of the Dream-Den\n\n"
            "Deck\n4 Lightning Bolt\n\n"
            "Sideboard\n2 Smash to Smithereens\n"
        )
        result = parse_deck(deck_path, format="pioneer")
        assert result["total_cards"] == 4
        assert result["total_sideboard"] == 2
        assert len(result["companion"]) == 1

    def test_companion_suffix_retained(self, tmp_path):
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Companion\n1 Jegantha, the Wellspring (IKO) 222\n\nDeck\n4 Mountain\n"
        )
        result = parse_deck(deck_path, format="modern")
        companion = result["companion"][0]
        assert companion["name"] == "Jegantha, the Wellspring"
        assert companion["set"] == "iko"
        assert companion["collector_number"] == "222"

    def test_moxfield_companion_section(self):
        text = "//Companion\n1 Jegantha, the Wellspring\n\n//Deck\n4 Lightning Bolt\n"
        result = parse_deck_text(text, format="modern")
        assert result["companion"] == [
            {"name": "Jegantha, the Wellspring", "quantity": 1}
        ]
        assert [c["name"] for c in result["cards"]] == ["Lightning Bolt"]

    def test_no_companion_section_defaults_empty(self, moxfield_deck, csv_deck):
        assert parse_deck(moxfield_deck)["companion"] == []
        assert parse_deck(csv_deck)["companion"] == []

    def test_companion_survives_commander_sideboard_fold(self, tmp_path):
        # Commander formats fold sideboard entries back into cards; the
        # companion zone must NOT be folded in — it sits outside the deck.
        deck_path = tmp_path / "deck.txt"
        deck_path.write_text(
            "Commander\n1 Aesi, Tyrant of Gyre Strait\n\n"
            "Companion\n1 Jegantha, the Wellspring\n\n"
            "Deck\n30 Forest\n\nSideboard\n1 Sol Ring\n"
        )
        result = parse_deck(deck_path, format="commander")
        assert result["companion"] == [
            {"name": "Jegantha, the Wellspring", "quantity": 1}
        ]
        card_names = [c["name"] for c in result["cards"]]
        assert "Jegantha, the Wellspring" not in card_names
        assert "Sol Ring" in card_names
        assert result["total_cards"] == 32
