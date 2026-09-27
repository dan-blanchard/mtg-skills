"""The spill check's online-price proxy: cheapest paper USD across every printing,
names resolved through the card pool (ADR-0046). Real cards come from the testkit;
only per-printing facts (id, prices, digital) are overlaid (ADR-0056)."""

from __future__ import annotations

import json

from mtg_utils.card_pool import CardPool
from mtg_utils.lgs_search import _cheapest_usd, _load_pool
from mtg_utils.testkit import test_card


def _printing(name: str, printing_id: str, **overlay: object) -> dict:
    return {**test_card(name), "id": printing_id, **overlay}


def _pool(*records: dict) -> CardPool:
    return CardPool.from_cards(list(records))


def test_no_pool_prices_everything_at_zero():
    assert _cheapest_usd(None, ["Sol Ring"]) == {"Sol Ring": 0.0}


def test_reads_each_cards_price_and_zero_for_an_unknown_name():
    pool = _pool(
        _printing("Sol Ring", "sol-c21", prices={"usd": "1.10"}),
        _printing("Counterspell", "cs-mh2", prices={"usd": "0.50"}),
    )
    out = _cheapest_usd(pool, ["Sol Ring", "Counterspell", "Not A Real Card"])
    assert out == {"Sol Ring": 1.10, "Counterspell": 0.50, "Not A Real Card": 0.0}


def test_an_unpriced_card_is_zero():
    pool = _pool(_printing("Sol Ring", "sol-c21", prices={"usd": None}))
    assert _cheapest_usd(pool, ["Sol Ring"]) == {"Sol Ring": 0.0}


def test_picks_cheapest_printing_across_reprints():
    """Printings differ wildly in price (Beast Within: original ~$5, reprints
    $0.50). The proxy takes the cheapest non-foil printing, what an online
    optimizer (TCG / MP) could plausibly source."""
    pool = _pool(
        _printing("Beast Within", "bw-pcy", prices={"usd": "5.00"}),
        _printing("Beast Within", "bw-reprint", prices={"usd": None}),
        _printing("Beast Within", "bw-cmd", prices={"usd": "0.50"}),
        _printing("Beast Within", "bw-sld", prices={"usd": "1.20"}),
    )
    assert _cheapest_usd(pool, ["Beast Within"]) == {"Beast Within": 0.50}


def test_skips_digital_only_printings():
    """Arena and MTGO printings are priced in their own ecosystems and aren't
    buyable at TCG / MP."""
    pool = _pool(
        _printing("Sol Ring", "sol-mtgo", digital=True, prices={"usd": "0.01"}),
        _printing("Sol Ring", "sol-c21", prices={"usd": "1.10"}),
    )
    assert _cheapest_usd(pool, ["Sol Ring"]) == {"Sol Ring": 1.10}


def test_an_etched_only_price_counts_but_foil_does_not():
    pool = _pool(
        _printing(
            "Sol Ring",
            "sol-etched",
            prices={"usd": None, "usd_etched": "3.50", "usd_foil": "0.75"},
        ),
    )
    assert _cheapest_usd(pool, ["Sol Ring"]) == {"Sol Ring": 3.50}


def test_a_two_faced_card_prices_under_its_front_face_name():
    """A deck list names a modal / adventure card by its front face ("Agadeem's
    Awakening"), while its record's ``name`` is the full "A // B" name. The proxy
    must still find it; before, it matched the exact full name only and priced the
    card at 0.0, so the spill check never fired on it."""
    pool = _pool(
        _printing("Agadeem's Awakening", "agadeem-znr", prices={"usd": "28.91"}),
        _printing("Brazen Borrower", "borrower-eld", prices={"usd": "0.43"}),
    )
    out = _cheapest_usd(pool, ["Agadeem's Awakening", "Brazen Borrower"])
    assert out == {"Agadeem's Awakening": 28.91, "Brazen Borrower": 0.43}


class TestLoadPool:
    """The orchestrator loads the card pool for the proxy: the --bulk-data path,
    else the auto-discovered MTGJSON bulk. Missing card data warns loudly rather
    than failing: without it the spill check goes silent (verified live to overpay
    5-30x on cards with cheap reprints)."""

    def test_an_explicit_path_loads(self, tmp_path):
        bulk = tmp_path / "bulk.json"
        bulk.write_text(
            json.dumps([_printing("Sol Ring", "sol-c21", prices={"usd": "1.10"})])
        )
        pool = _load_pool(bulk)
        assert pool is not None
        assert _cheapest_usd(pool, ["Sol Ring"]) == {"Sol Ring": 1.10}

    def test_no_card_data_warns_and_names_the_fix(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr("mtg_utils.card_pool.default_bulk_path", lambda: None)
        assert _load_pool(None) is None
        err = capsys.readouterr().err
        assert "download-mtgjson" in err
        assert "overpay" in err
