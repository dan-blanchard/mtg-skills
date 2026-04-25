"""Tests for set_commander — moving cards to commander zone."""

import json

import pytest
from click.testing import CliRunner

from mtg_utils.set_commander import main, set_commander


@pytest.fixture
def sample_deck() -> dict:
    """A minimal parsed deck with a few cards."""
    return {
        "commanders": [],
        "cards": [
            {"name": "Korvold, Fae-Cursed King", "quantity": 1},
            {"name": "Viscera Seer", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ],
    }


@pytest.fixture
def partner_deck() -> dict:
    """A deck with two potential partner commanders in the cards list."""
    return {
        "commanders": [],
        "cards": [
            {"name": "Thrasios, Triton Hero", "quantity": 1},
            {"name": "Tymna the Weaver", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ],
    }


class TestSetCommander:
    def test_moves_card_to_commanders(self, sample_deck):
        result = set_commander(sample_deck, ["Korvold, Fae-Cursed King"])
        commander_names = [c["name"] for c in result["commanders"]]
        card_names = [c["name"] for c in result["cards"]]
        assert "Korvold, Fae-Cursed King" in commander_names
        assert "Korvold, Fae-Cursed King" not in card_names

    def test_partner_commanders(self, partner_deck):
        result = set_commander(
            partner_deck, ["Thrasios, Triton Hero", "Tymna the Weaver"]
        )
        commander_names = [c["name"] for c in result["commanders"]]
        card_names = [c["name"] for c in result["cards"]]
        assert "Thrasios, Triton Hero" in commander_names
        assert "Tymna the Weaver" in commander_names
        assert "Thrasios, Triton Hero" not in card_names
        assert "Tymna the Weaver" not in card_names

    def test_card_not_found_raises(self, sample_deck):
        with pytest.raises(ValueError, match="not found"):
            set_commander(sample_deck, ["Nonexistent Card"])

    def test_does_not_modify_original(self, sample_deck):
        original_commanders = list(sample_deck["commanders"])
        original_cards = list(sample_deck["cards"])
        set_commander(sample_deck, ["Korvold, Fae-Cursed King"])
        assert sample_deck["commanders"] == original_commanders
        assert sample_deck["cards"] == original_cards

    def test_already_commander_is_noop(self):
        """Calling set-commander on a card already in the commander zone is a
        no-op, not an error. This makes ``parse-deck | set-commander`` safe to
        chain when parse-deck already honored a Moxfield ``Commander`` header.
        """
        deck = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = set_commander(deck, ["Korvold, Fae-Cursed King"])
        commander_names = [c["name"] for c in result["commanders"]]
        assert commander_names == ["Korvold, Fae-Cursed King"]
        assert [c["name"] for c in result["cards"]] == ["Sol Ring"]

    def test_mixed_idempotent_and_move(self):
        """Partner pair where one commander is already set and the other is in
        cards — the already-set one is untouched, the other is moved.
        """
        deck = {
            "commanders": [{"name": "Thrasios, Triton Hero", "quantity": 1}],
            "cards": [
                {"name": "Tymna the Weaver", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        result = set_commander(deck, ["Thrasios, Triton Hero", "Tymna the Weaver"])
        commander_names = {c["name"] for c in result["commanders"]}
        card_names = {c["name"] for c in result["cards"]}
        assert commander_names == {"Thrasios, Triton Hero", "Tymna the Weaver"}
        assert card_names == {"Sol Ring"}


class TestCLI:
    def test_writes_back_to_deck_in_place_by_default(self, sample_deck, tmp_path):
        """No --output flag writes the modified deck back to DECK_PATH itself.

        Regression test: previously the CLI echoed the modified JSON to stdout
        only and left DECK_PATH untouched, so any downstream tool reading
        DECK_PATH (legality-audit, scryfall-lookup --batch) saw the commander
        still in the cards list and emitted cascading color-identity failures.
        """
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), "Korvold, Fae-Cursed King"])

        assert result.exit_code == 0, result.output
        # The file on disk must reflect the change.
        on_disk = json.loads(deck_path.read_text(encoding="utf-8"))
        commander_names = [c["name"] for c in on_disk["commanders"]]
        card_names = [c["name"] for c in on_disk["cards"]]
        assert "Korvold, Fae-Cursed King" in commander_names
        assert "Korvold, Fae-Cursed King" not in card_names

    def test_output_flag_writes_to_alternate_path(self, sample_deck, tmp_path):
        """--output PATH writes there and leaves DECK_PATH untouched."""
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))
        out_path = tmp_path / "modified.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(deck_path), "Korvold, Fae-Cursed King", "--output", str(out_path)],
        )

        assert result.exit_code == 0, result.output
        # Original is unchanged.
        original = json.loads(deck_path.read_text(encoding="utf-8"))
        assert original["commanders"] == []
        # Output path has the change.
        modified = json.loads(out_path.read_text(encoding="utf-8"))
        commander_names = [c["name"] for c in modified["commanders"]]
        assert "Korvold, Fae-Cursed King" in commander_names

    def test_output_dash_writes_to_stdout(self, sample_deck, tmp_path):
        """--output - prints JSON to stdout (back-compat for piping).

        Preserves the pre-fix workflow ``set-commander deck.json Name > out``
        for callers that explicitly want stdout.
        """
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), "Korvold, Fae-Cursed King", "--output", "-"]
        )

        assert result.exit_code == 0
        # Original file must remain unchanged when stdout is requested.
        original = json.loads(deck_path.read_text(encoding="utf-8"))
        assert original["commanders"] == []
        # Stdout has the modified deck.
        data = json.loads(result.output)
        commander_names = [c["name"] for c in data["commanders"]]
        assert "Korvold, Fae-Cursed King" in commander_names

    def test_error_for_missing_card(self, sample_deck, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), "Nonexistent Card"])

        assert result.exit_code != 0
        # File must not be modified on error.
        on_disk = json.loads(deck_path.read_text(encoding="utf-8"))
        assert on_disk == sample_deck

    def test_idempotent_when_run_twice_in_place(self, sample_deck, tmp_path):
        """Running set-commander on a file that already has the requested
        commander must be a true no-op end to end: byte-for-byte identical
        on-disk content after the second invocation, no orphan tmp files
        from atomic_write_json's tempfile-and-rename path.

        Regression guard: a future refactor could accidentally call
        ``atomic_write_json`` on the no-op path and (a) leak tmp files
        if the rename fails, (b) change the on-disk byte content via
        a different JSON serializer.
        """
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(json.dumps(sample_deck))

        runner = CliRunner()
        first = runner.invoke(main, [str(deck_path), "Korvold, Fae-Cursed King"])
        assert first.exit_code == 0, first.output
        first_bytes = deck_path.read_bytes()

        second = runner.invoke(main, [str(deck_path), "Korvold, Fae-Cursed King"])
        assert second.exit_code == 0, second.output
        second_bytes = deck_path.read_bytes()

        assert first_bytes == second_bytes
        # No orphan tmp files in the working directory.
        assert {p.name for p in tmp_path.iterdir()} == {"deck.json"}


# NOTE: tests for legality_audit.check_commander_zone live in
# tests/mtg-utils/test_legality_audit.py::TestCommanderZone — they were
# colocated here briefly because the bug they cover (cascading
# color-identity errors when set-commander silently fails) compounded
# with set-commander's stdout-only bug. They moved to follow the standard
# "tests next to module" convention.
