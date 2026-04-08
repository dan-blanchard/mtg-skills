"""Tests for mark_owned — populate owned_cards from a parsed collection."""

import json

from click.testing import CliRunner

from commander_utils.mark_owned import main, mark_owned


class TestMarkOwned:
    def test_basic_intersection(self):
        """``owned_cards`` is written as ``[{name, quantity}]`` dicts —
        same shape as ``cards``/``commanders`` — with the quantity
        taken from the collection side of the intersection."""
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
        assert result["owned_cards"] == [
            {"name": "Command Tower", "quantity": 4},
            {"name": "Sol Ring", "quantity": 2},
        ]

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
        names = {entry["name"] for entry in result["owned_cards"]}
        assert names == {"Atraxa, Praetors' Voice", "Sol Ring"}

    def test_diacritic_folding(self):
        """ASCII-only deck name should match diacritic-bearing collection entry.

        Deck-side spelling is preserved in the written ``owned_cards``
        entry; collection-side quantity is recorded.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Lim-Dul's Vault", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Lim-D\u00fbl's Vault", "quantity": 3}],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Lim-Dul's Vault", "quantity": 3},
        ]

    def test_owned_cards_schema_is_dicts(self):
        """Result matches the canonical ``[{name, quantity}]`` schema
        that price-check consumes and that ``cards``/``commanders`` use.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = mark_owned(deck, collection)
        assert all(
            isinstance(entry, dict)
            and isinstance(entry.get("name"), str)
            and isinstance(entry.get("quantity"), int)
            for entry in result["owned_cards"]
        )

    def test_zero_quantity_collection_row_is_not_owned(self):
        """A Moxfield wishlist/binder row exported at ``quantity=0`` is
        NOT marked as owned: "zero copies" is not owning the card. The
        previous string-schema implementation pinned the opposite
        behavior (quantity was ignored entirely); first-class quantity
        in the dict schema lets us do the right thing.
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
        assert result["owned_cards"] == []

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
        assert written["owned_cards"] == [{"name": "Sol Ring", "quantity": 1}]
        # Pin the human-readable summary format so a refactor of
        # _collect_entries can't silently regress the stdout contract.
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
        assert written["owned_cards"] == [{"name": "Sol Ring", "quantity": 1}]
