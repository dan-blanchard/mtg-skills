"""Tests for mark_owned — populate owned_cards from a parsed collection."""

import json

from click.testing import CliRunner

from commander_utils.mark_owned import main, mark_owned


class TestMarkOwned:
    def test_basic_intersection(self):
        deck = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Command Tower", "quantity": 1},
                {"name": "Mana Crypt", "quantity": 1},
            ],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Sol Ring", "quantity": 2},
                {"name": "Command Tower", "quantity": 4},
                {"name": "Lightning Bolt", "quantity": 3},
            ],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == ["Command Tower", "Sol Ring"]

    def test_commander_counted_as_owned(self):
        """A commander present in the collection should show up in owned_cards."""
        deck = {
            "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Atraxa, Praetors' Voice", "quantity": 1},
                {"name": "Sol Ring", "quantity": 2},
            ],
        }
        result = mark_owned(deck, collection)
        assert "Atraxa, Praetors' Voice" in result["owned_cards"]
        assert "Sol Ring" in result["owned_cards"]

    def test_diacritic_folding(self):
        """ASCII-only deck name should match diacritic-bearing collection entry."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Lim-Dul's Vault", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Lim-D\u00fbl's Vault", "quantity": 1}],
        }
        result = mark_owned(deck, collection)
        # Original deck spelling is preserved in the written owned list.
        assert result["owned_cards"] == ["Lim-Dul's Vault"]

    def test_owned_cards_is_string_list(self):
        """Result must be a list of plain strings, matching price-check's schema."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = mark_owned(deck, collection)
        assert all(isinstance(n, str) for n in result["owned_cards"])

    def test_zero_quantity_collection_row_still_counts_as_owned(self):
        """``mark-owned`` intentionally does not inspect quantity — it only
        cares about "is this name in the collection at all." A wishlist/
        binder row exported at ``quantity=0`` from Moxfield will still mark
        the card as owned. This is a deliberate choice (the sibling script
        ``find-commanders`` has ``--min-quantity`` for that) and a pinned
        test exists so a future reader doesn't "fix" it by accident.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 0}],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == ["Sol Ring"]

    def test_does_not_mutate_input(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
            "owned_cards": [],
        }
        original = json.loads(json.dumps(deck))
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        mark_owned(deck, collection)
        assert deck == original


class TestCLI:
    def test_writes_output_file(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        coll_path = tmp_path / "collection.json"
        out_path = tmp_path / "out.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )
        coll_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(deck_path), str(coll_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        written = json.loads(out_path.read_text())
        assert written["owned_cards"] == ["Sol Ring"]
        # Pin the human-readable summary format so a refactor of
        # _collect_names can't silently regress the stdout contract.
        assert "1 of 1 unique deck cards owned" in result.output

    def test_in_place_overwrite(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        coll_path = tmp_path / "collection.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )
        coll_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(coll_path)])
        assert result.exit_code == 0, result.output
        written = json.loads(deck_path.read_text())
        assert written["owned_cards"] == ["Sol Ring"]
