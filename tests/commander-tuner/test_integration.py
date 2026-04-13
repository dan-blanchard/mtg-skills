"""Integration test: parse deck → lookup cards → check EDHREC."""

from unittest.mock import MagicMock, patch

from mtg_utils.edhrec_lookup import edhrec_lookup
from mtg_utils.parse_deck import parse_deck
from mtg_utils.scryfall_lookup import _load_bulk_index, lookup_single


class TestFullPipeline:
    def test_parse_then_lookup(self, moxfield_deck, sample_bulk_data):
        """Parse a deck list, then look up each card in Scryfall."""
        deck = parse_deck(moxfield_deck)
        assert len(deck["commanders"]) == 1
        assert deck["commanders"][0] == {
            "name": "Korvold, Fae-Cursed King",
            "quantity": 1,
        }

        bulk_index = _load_bulk_index(sample_bulk_data)

        # Look up commander
        commander = lookup_single(deck["commanders"][0]["name"], bulk_index=bulk_index)
        assert commander is not None
        assert "Flying" in commander["oracle_text"]
        assert "sacrifice" in commander["oracle_text"].lower()

        # Look up all cards
        found = 0
        for card in deck["cards"]:
            result = lookup_single(card["name"], bulk_index=bulk_index)
            if result is not None:
                found += 1
                assert result["oracle_text"] is not None

        # All cards in fixture should be in sample bulk data
        assert found == len(deck["cards"])

    def test_commander_color_identity(self, moxfield_deck, sample_bulk_data):
        """Verify we can check color identity compliance."""
        deck = parse_deck(moxfield_deck)
        bulk_index = _load_bulk_index(sample_bulk_data)

        commander = lookup_single(deck["commanders"][0]["name"], bulk_index=bulk_index)
        commander_identity = set(commander["color_identity"])  # {B, G, R}

        for card in deck["cards"]:
            result = lookup_single(card["name"], bulk_index=bulk_index)
            if result is not None:
                card_identity = set(result["color_identity"])
                assert card_identity.issubset(commander_identity), (
                    f"{result['name']} has identity {card_identity} "
                    f"outside commander's {commander_identity}"
                )

    def test_game_changer_counting(self, sample_bulk_data):
        """Verify we can count Game Changers for bracket compliance."""
        bulk_index = _load_bulk_index(sample_bulk_data)

        game_changers = [
            name
            for name, card in bulk_index.items()
            if card.get("game_changer") and " // " not in card.get("name", "")
        ]
        # Our fixture has Rhystic Study as a game changer
        gc_names = [bulk_index[n]["name"] for n in game_changers]
        assert "Rhystic Study" in gc_names

    def test_edhrec_integration(self, sample_edhrec_response):
        """Verify EDHREC data extraction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_edhrec_response
        mock_resp.raise_for_status = MagicMock()

        with patch("mtg_utils.edhrec_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = edhrec_lookup(["Korvold, Fae-Cursed King"])

        # High synergy cards should be extracted
        hs_names = [c["name"] for c in result["high_synergy"]]
        assert "Pitiless Plunderer" in hs_names
        assert "Mayhem Devil" in hs_names
