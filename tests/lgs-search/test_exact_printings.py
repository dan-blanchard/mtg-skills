"""--exact-printings: pinned lines from input to the marketplace.

Card records are synthetic (fictional names); only per-printing fields
matter here.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from mtg_utils._stores.manapool import ADAPTER as MANAPOOL
from mtg_utils._stores.manapool import exact_shortfalls, exact_tab_active
from mtg_utils._stores.printing import PrintingSpec
from mtg_utils.lgs_search import (
    NeededCard,
    card_key,
    optimize_marketplace,
    printing_specs,
    resolve_input,
    sweep_lgs,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"

LIST = (
    "1x Testcard Paragon (abc) 9 [Removal]\n"
    "1x Testcard Token (tabc) 3 [Tokens & Extras{noDeck}]\n"
    "1x Testcard Token (txyz) 5 [Tokens & Extras{noDeck}]\n"
    "1x Testcard Citizen (tfrc) 11 *F* [Tokens & Extras{noDeck}]\n"
    "2 Testcard Plain\n"
)


def _write(tmp_path, content: str) -> Path:
    path = tmp_path / "list.txt"
    path.write_text(content)
    return path


class TestInput:
    def test_lines_pin_their_printing(self, tmp_path):
        cards, _ = resolve_input(
            _write(tmp_path, LIST),
            collection_path=None,
            include_basics=False,
            exact_printings=True,
        )
        assert [card_key(c) for c in cards] == [
            "Testcard Paragon (ABC) 9",
            "Testcard Token (TABC) 3",
            "Testcard Token (TXYZ) 5",
            "Testcard Citizen (TFRC) 11 *F*",
            "Testcard Plain",
        ]
        assert cards[3]["printing"] == {
            "set": "tfrc",
            "collector_number": "11",
            "finish": "foil",
        }
        assert "printing" not in cards[4]

    def test_without_the_flag_printings_are_dropped_and_merged(self, tmp_path):
        cards, _ = resolve_input(
            _write(tmp_path, LIST), collection_path=None, include_basics=False
        )
        assert [(c["card_name"], c["qty"]) for c in cards] == [
            ("Testcard Paragon", 1),
            ("Testcard Token", 2),
            ("Testcard Citizen", 1),
            ("Testcard Plain", 2),
        ]
        assert not any("printing" in c for c in cards)

    def test_same_printing_lines_merge(self, tmp_path):
        text = "1 Testcard Paragon (abc) 9\n2 Testcard Paragon (ABC) 9\n"
        cards, _ = resolve_input(
            _write(tmp_path, text),
            collection_path=None,
            include_basics=False,
            exact_printings=True,
        )
        assert [(card_key(c), c["qty"]) for c in cards] == [
            ("Testcard Paragon (ABC) 9", 3)
        ]

    def test_deck_json_printing_keys(self, tmp_path):
        path = tmp_path / "deck.json"
        path.write_text(
            json.dumps(
                {
                    "cards": [
                        {
                            "name": "Testcard Paragon",
                            "quantity": 1,
                            "set": "abc",
                            "collector_number": "9",
                            "finish": "etched",
                        }
                    ]
                }
            )
        )
        cards, _ = resolve_input(
            path, collection_path=None, include_basics=False, exact_printings=True
        )
        assert [card_key(c) for c in cards] == ["Testcard Paragon (ABC) 9 *E*"]

    def test_collection_copies_are_shared_across_a_cards_lines(self, tmp_path):
        coll = tmp_path / "coll.json"
        coll.write_text(json.dumps({"Testcard Token": 1}))
        cards, _ = resolve_input(
            _write(tmp_path, LIST),
            collection_path=coll,
            include_basics=False,
            exact_printings=True,
        )
        tokens = [card_key(c) for c in cards if c["card_name"] == "Testcard Token"]
        assert tokens == ["Testcard Token (TXYZ) 5"]


def _listing(store: str, set_code: str, number: str, price: float) -> dict:
    return {
        "store": store,
        "card_name": "Testcard Token",
        "set_code": set_code,
        "collector_number": number,
        "condition": "NM",
        "foil": False,
        "price": price,
        "qty_available": 4,
        "listing_id": f"{set_code}{number}",
        "url": "",
    }


def test_sweep_searches_once_per_name_and_filters_per_line(monkeypatch):
    lgs = MagicMock()
    lgs.search.return_value = [
        _listing("tgp", "TABC", "3", 0.50),
        _listing("tgp", "TXYZ", "5", 0.75),
        _listing("tgp", "TQRS", "1", 0.10),
    ]
    monkeypatch.setattr("mtg_utils.lgs_search.LGS_ADAPTERS", {"tgp": lgs})
    monkeypatch.setattr("mtg_utils.lgs_search.LGS_STORES", ["tgp"])
    cards = [
        NeededCard(
            card_name="Testcard Token",
            qty=1,
            printing={"set": s, "collector_number": n, "finish": "nonfoil"},
        )
        for s, n in (("tabc", "3"), ("txyz", "5"))
    ]
    specs = {card_key(c): PrintingSpec(c["card_name"], c["printing"]) for c in cards}
    rows = sweep_lgs(
        cards,
        scryfall_usd_lookup={},
        prefs={"max_condition": "lp", "allow_foil": False, "prefer_set": None},
        specs=specs,
        sequential=True,
    )
    assert lgs.search.call_count == 1
    picked = [r["by_store"]["tgp"] for r in rows]
    assert [(x["set_code"], x["price"], x["printing_match"]) for x in picked] == [
        ("TABC", 0.50, "exact"),
        ("TXYZ", 0.75, "exact"),
    ]
    assert rows[0]["printing"]["set"] == "tabc"


def test_printing_specs_without_a_pool_match_only_exact():
    card = NeededCard(
        card_name="Testcard Token",
        qty=1,
        printing={"set": "tabc", "collector_number": "3", "finish": "nonfoil"},
    )
    specs = printing_specs(None, [card, NeededCard(card_name="Testcard Plain", qty=1)])
    assert list(specs) == ["Testcard Token (TABC) 3"]
    spec = specs["Testcard Token (TABC) 3"]
    assert spec.match(_listing("tgp", "TABC", "3", 1.0)) == "exact"
    assert spec.match(_listing("tgp", "TABC", "4", 1.0)) is None


def _cart(store: str, total: float, unfound: list[str] | None = None) -> dict:
    return {
        "store": store,
        "total": total,
        "items_subtotal": total,
        "shipping": 0.0,
        "lines": [],
        "unfound": unfound or [],
        "cart_url": "x",
    }


def test_marketplace_that_cant_pin_is_skipped(monkeypatch):
    tcg = MagicMock(pins_printings=False)
    tcg.bulk_submit_and_optimize.return_value = _cart("tcgplayer", 1.0)
    mp = MagicMock(pins_printings=True)
    mp.bulk_submit_and_optimize.return_value = _cart("manapool", 5.0, ["x"])
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {"tcgplayer": tcg, "manapool": mp},
    )
    lines = [
        {
            "card_name": "Testcard Token",
            "qty": 1,
            "printing": {"set": "tabc", "collector_number": "3", "finish": "foil"},
        }
    ]
    result = optimize_marketplace(lines)
    assert result is not None
    assert result["chosen"] == "manapool"
    tcg.bulk_submit_and_optimize.assert_not_called()


def test_marketplace_without_pins_uses_both(monkeypatch):
    tcg = MagicMock(pins_printings=False)
    tcg.bulk_submit_and_optimize.return_value = _cart("tcgplayer", 1.0)
    mp = MagicMock(pins_printings=True)
    mp.bulk_submit_and_optimize.return_value = _cart("manapool", 5.0)
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {"tcgplayer": tcg, "manapool": mp},
    )
    result = optimize_marketplace([{"card_name": "Testcard Token", "qty": 1}])
    assert result is not None
    assert result["chosen"] == "tcgplayer"


class TestManaPoolExactTab:
    def test_captured_page_has_exact_active(self):
        html = (FIXTURE_DIR / "mp_add_deck_exact.html").read_text("utf-8")
        assert exact_tab_active(html) is True

    def test_any_printing_active_is_not_exact(self):
        html = (FIXTURE_DIR / "mp_add_deck_exact.html").read_text("utf-8")
        soup = BeautifulSoup(html, "html.parser")
        soup.select_one('button[data-value="exactMatch"]')["data-state"] = "inactive"
        assert exact_tab_active(str(soup)) is False


class TestManaPoolLines:
    def test_line_text(self):
        plain = {"card_name": "Sol Ring", "qty": 2}
        assert MANAPOOL.line_text(plain) == "2 Sol Ring"
        pinned = {
            "card_name": "Citizen",
            "qty": 1,
            "printing": {"set": "tfrc", "collector_number": "11", "finish": "foil"},
        }
        assert MANAPOOL.line_text(pinned) == "1 Citizen [TFRC] 11 *F*"

    def test_exact_shortfalls_from_the_exact_panel(self):
        """The captured Exact panel: Daxos MUL 132z and Zombie TSOC 12 out of
        stock, 2 Hare Apparent in stock."""
        html = (FIXTURE_DIR / "mp_add_deck_exact.html").read_text("utf-8")

        def pinned(name, qty, set_code, number):
            return {
                "card_name": name,
                "qty": qty,
                "printing": {
                    "set": set_code,
                    "collector_number": number,
                    "finish": "nonfoil",
                },
            }

        lines = [
            pinned("Daxos, Blessed by the Sun", 1, "mul", "132z"),
            pinned("Hare Apparent", 2, "fdn", "15"),
            pinned("Zombie", 1, "tsoc", "12"),
        ]
        assert exact_shortfalls(html, lines) == [
            "Daxos, Blessed by the Sun [MUL] 132z (0 of 1)",
            "Zombie [TSOC] 12 (0 of 1)",
        ]


def test_invariant_counts_two_printings_of_a_card_as_two_lines():
    from mtg_utils.lgs_search import assert_no_duplicates_invariant

    lines = [
        NeededCard(
            card_name="Testcard Token",
            qty=1,
            printing={"set": s, "collector_number": "1", "finish": "nonfoil"},
        )
        for s in ("tabc", "txyz")
    ]
    allocated = [{**line, "store": "marketplace", "listing": None} for line in lines]
    assert_no_duplicates_invariant(lines, allocated)
