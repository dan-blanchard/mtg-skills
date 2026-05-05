"""Tests for input resolution: deck JSON / text list, basics filter, collection sub."""

from __future__ import annotations

import json

from mtg_utils.lgs_search import (
    BASIC_LAND_NAMES,
    NeededCard,
    resolve_input,
    summarize_basics,
)


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


class TestResolveInput:
    def test_text_list(self, tmp_path):
        path = _write(
            tmp_path, "list.txt", "1 Sol Ring\n2 Counterspell\nLightning Bolt\n"
        )
        cards, basics = resolve_input(path, collection_path=None, include_basics=False)
        names = {c["card_name"] for c in cards}
        qty_by_name = {c["card_name"]: c["qty"] for c in cards}
        assert names == {"Sol Ring", "Counterspell", "Lightning Bolt"}
        assert qty_by_name == {"Sol Ring": 1, "Counterspell": 2, "Lightning Bolt": 1}
        assert basics == {}

    def test_text_list_filters_basics(self, tmp_path):
        path = _write(
            tmp_path,
            "list.txt",
            "18 Mountain\n12 Plains\n1 Sol Ring\n",
        )
        cards, basics = resolve_input(path, collection_path=None, include_basics=False)
        assert [c["card_name"] for c in cards] == ["Sol Ring"]
        assert basics == {"Mountain": 18, "Plains": 12}

    def test_text_list_include_basics_keeps_them(self, tmp_path):
        path = _write(tmp_path, "list.txt", "18 Mountain\n1 Sol Ring\n")
        cards, basics = resolve_input(path, collection_path=None, include_basics=True)
        names = {c["card_name"] for c in cards}
        assert names == {"Mountain", "Sol Ring"}
        assert basics == {}

    def test_text_list_keeps_snow_basics(self, tmp_path):
        path = _write(tmp_path, "list.txt", "10 Snow-Covered Mountain\n1 Sol Ring\n")
        cards, basics = resolve_input(path, collection_path=None, include_basics=False)
        names = {c["card_name"] for c in cards}
        assert "Snow-Covered Mountain" in names
        assert basics == {}

    def test_text_list_skips_blank_and_comments(self, tmp_path):
        path = _write(
            tmp_path,
            "list.txt",
            "1 Sol Ring\n\n# comment\n// also comment\n2 Counterspell\n",
        )
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        names = {c["card_name"] for c in cards}
        assert names == {"Sol Ring", "Counterspell"}

    def test_text_list_handles_trailing_x(self, tmp_path):
        # Some exports use `4x Lightning Bolt`
        path = _write(tmp_path, "list.txt", "4x Lightning Bolt\n")
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        assert cards == [NeededCard(card_name="Lightning Bolt", qty=4)]

    def test_deck_json(self, tmp_path):
        deck = {
            "format": "commander",
            "commanders": ["Atraxa, Praetors' Voice"],
            "cards": [
                {"name": "Sol Ring", "qty": 1},
                {"name": "Plains", "qty": 7},
            ],
            "sideboard": [],
        }
        path = _write(tmp_path, "deck.json", json.dumps(deck))
        cards, basics = resolve_input(path, collection_path=None, include_basics=False)
        names = {c["card_name"] for c in cards}
        assert "Atraxa, Praetors' Voice" in names
        assert "Sol Ring" in names
        assert basics == {"Plains": 7}

    def test_deck_json_merges_sideboard(self, tmp_path):
        deck = {
            "format": "modern",
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "qty": 4}],
            "sideboard": [{"name": "Lightning Bolt", "qty": 2}],
        }
        path = _write(tmp_path, "deck.json", json.dumps(deck))
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        assert cards == [NeededCard(card_name="Lightning Bolt", qty=6)]

    def test_deck_json_detected_by_first_brace(self, tmp_path):
        # Even without .json suffix, JSON content should be parsed as JSON.
        deck = {
            "format": "commander",
            "commanders": [],
            "cards": [{"name": "Sol Ring", "qty": 1}],
            "sideboard": [],
        }
        path = _write(tmp_path, "deck", json.dumps(deck))
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        assert cards == [NeededCard(card_name="Sol Ring", qty=1)]

    def test_collection_subtraction_dict(self, tmp_path):
        deck = {
            "format": "commander",
            "commanders": [],
            "cards": [
                {"name": "Sol Ring", "qty": 1},
                {"name": "Counterspell", "qty": 2},
            ],
            "sideboard": [],
        }
        coll = {"Sol Ring": 1, "Counterspell": 1}
        deck_path = _write(tmp_path, "deck.json", json.dumps(deck))
        coll_path = _write(tmp_path, "coll.json", json.dumps(coll))
        cards, _ = resolve_input(
            deck_path, collection_path=coll_path, include_basics=False
        )
        # Sol Ring: 1 needed - 1 owned = 0 → dropped. Counterspell: 2 - 1 = 1.
        assert cards == [NeededCard(card_name="Counterspell", qty=1)]

    def test_collection_subtraction_normalizes_names(self, tmp_path):
        """Arena exports strip diacritics; bulk data preserves them. Both
        sides must go through normalize_card_name so subtraction lines up.
        """
        deck = {
            "format": "commander",
            "commanders": [],
            "cards": [{"name": "Lim-Dûl's Vault", "quantity": 1}],
            "sideboard": [],
        }
        coll = {"Lim-Dul's Vault": 1}  # Arena-style ASCII-folded
        deck_path = _write(tmp_path, "deck.json", json.dumps(deck))
        coll_path = _write(tmp_path, "coll.json", json.dumps(coll))
        cards, _ = resolve_input(
            deck_path,
            collection_path=coll_path,
            include_basics=False,
        )
        assert cards == []  # 1 needed - 1 owned (post-fold) = 0 → dropped

    def test_collection_subtraction_list_of_rows(self, tmp_path):
        deck = {
            "format": "commander",
            "commanders": [],
            "cards": [{"name": "Sol Ring", "qty": 2}],
            "sideboard": [],
        }
        coll = [{"name": "Sol Ring", "qty": 1}]
        deck_path = _write(tmp_path, "deck.json", json.dumps(deck))
        coll_path = _write(tmp_path, "coll.json", json.dumps(coll))
        cards, _ = resolve_input(
            deck_path, collection_path=coll_path, include_basics=False
        )
        assert cards == [NeededCard(card_name="Sol Ring", qty=1)]

    def test_deck_json_canonical_parse_deck_shape(self, tmp_path):
        """Match the canonical parse_deck.py output: dict commanders, 'quantity' field."""
        deck = {
            "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Lightning Bolt", "quantity": 4},
            ],
            "sideboard": [{"name": "Lightning Bolt", "quantity": 2}],
        }
        path = _write(tmp_path, "deck.json", json.dumps(deck))
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        qty_by_name = {c["card_name"]: c["qty"] for c in cards}
        assert qty_by_name == {
            "Atraxa, Praetors' Voice": 1,
            "Sol Ring": 1,
            "Lightning Bolt": 6,  # 4 main + 2 side
        }

    def test_text_list_strips_set_code_suffix(self, tmp_path):
        """Moxfield/Arena exports include set codes; we should strip them."""
        path = _write(
            tmp_path, "list.txt", "4 Lightning Bolt (LEA) 161\n1 Sol Ring (C21) 263\n"
        )
        cards, _ = resolve_input(path, collection_path=None, include_basics=False)
        qty_by_name = {c["card_name"]: c["qty"] for c in cards}
        assert qty_by_name == {"Lightning Bolt": 4, "Sol Ring": 1}


class TestSummarizeBasics:
    def test_format(self):
        out = summarize_basics({"Mountain": 18, "Plains": 12})
        assert "Mountain" in out
        assert "18" in out
        assert "Plains" in out
        assert "12" in out

    def test_empty(self):
        assert summarize_basics({}) == ""


class TestBasicLandNames:
    def test_set_contents(self):
        assert (
            frozenset(
                {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"},
            )
            == BASIC_LAND_NAMES
        )
