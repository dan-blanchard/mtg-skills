"""Tests for build_deck module."""

from commander_utils.build_deck import build_deck


class TestBuildDeck:
    def test_basic_cut_and_add(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Bad Card", "quantity": 1},
            ],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Sol Ring", "cmc": 1, "type_line": "Artifact"},
            {"name": "Bad Card", "cmc": 3, "type_line": "Creature"},
            {"name": "Good Card", "cmc": 2, "type_line": "Instant"},
        ]
        cuts = [{"name": "Bad Card", "quantity": 1}]
        adds = [{"name": "Good Card", "quantity": 1}]
        new_deck, _new_hydrated = build_deck(deck, hydrated, cuts, adds)
        card_names = [c["name"] for c in new_deck["cards"]]
        assert "Bad Card" not in card_names
        assert "Good Card" in card_names
        assert len(new_deck["cards"]) == 2

    def test_quantity_adjustment(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [
                {"name": "Mountain", "quantity": 2},
                {"name": "Island", "quantity": 2},
            ],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Mountain", "cmc": 0, "type_line": "Basic Land — Mountain"},
            {"name": "Island", "cmc": 0, "type_line": "Basic Land — Island"},
        ]
        cuts = [{"name": "Mountain", "quantity": 1}]
        adds = [{"name": "Island", "quantity": 1}]
        new_deck, _ = build_deck(deck, hydrated, cuts, adds)
        by_name = {c["name"]: c for c in new_deck["cards"]}
        assert by_name["Mountain"]["quantity"] == 1
        assert by_name["Island"]["quantity"] == 3

    def test_removes_entry_when_quantity_zero(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Bad Card", "quantity": 1}],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Bad Card", "cmc": 3, "type_line": "Creature"},
        ]
        cuts = [{"name": "Bad Card", "quantity": 1}]
        new_deck, _ = build_deck(deck, hydrated, cuts, [])
        assert len(new_deck["cards"]) == 0

    def test_does_not_modify_original(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        hydrated = [
            {"name": "Korvold", "cmc": 5, "type_line": "Creature"},
            {"name": "Sol Ring", "cmc": 1, "type_line": "Artifact"},
        ]
        build_deck(deck, hydrated, [], [{"name": "New Card", "quantity": 1}])
        assert len(deck["cards"]) == 1

    def test_merges_new_card_into_hydrated(self):
        deck = {
            "commanders": [{"name": "Korvold", "quantity": 1}],
            "cards": [],
        }
        hydrated = [{"name": "Korvold", "cmc": 5, "type_line": "Creature"}]
        new_card_data = {"name": "New Card", "cmc": 2, "type_line": "Instant"}
        adds = [{"name": "New Card", "quantity": 1}]
        _, new_hydrated = build_deck(
            deck, hydrated, [], adds, extra_hydrated=[new_card_data]
        )
        names = [c["name"] for c in new_hydrated if c]
        assert "New Card" in names
