"""Tests for Scryfall per-card rulings fetcher."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner

from mtg_utils import _scryfall
from mtg_utils.rulings_lookup import (
    _cache_dir,
    lookup_rulings,
    lookup_rulings_batch,
    main,
)

# A fictional card: its ids and rulings are invented machinery (ADR-0056).
_FAKE_CARD = {
    "id": "card-test-relic",
    "name": "Test Relic",
    "oracle_id": "oid-test-relic",
    "legalities": {},
}
_FAKE_RULINGS = [
    {"published_at": "2020-01-01", "comment": "Taps for 2."},
    {"published_at": "2022-06-01", "comment": "Still legal."},
]


_RULINGS_URL = "https://api.scryfall.com/cards/card-test-relic/rulings"


@pytest.fixture(autouse=True)
def _isolated_rulings_cache(tmp_path, monkeypatch):
    """Point the cache root at a per-test dir: the rulings cache lives under it."""
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    assert _cache_dir() == tmp_path / "scryfall" / "rulings"


@pytest.fixture
def wire(scryfall_wire):
    """Scryfall answering every rulings request with ``_FAKE_RULINGS``."""
    scryfall_wire.route("/rulings", {"object": "list", "data": _FAKE_RULINGS})
    return scryfall_wire


class TestLookupRulings:
    def test_returns_card_rulings(self, wire):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings("Test Relic", refresh=True)
        assert result["name"] == "Test Relic"
        assert result["oracle_id"] == "oid-test-relic"
        assert len(result["rulings"]) == 2
        assert wire.urls() == [_RULINGS_URL]
        assert wire.timeouts == [_scryfall.TIMEOUT_SECONDS]

    def test_rulings_lookup_uses_card_id_not_oracle_id(self, wire):
        card = {
            "id": "card-uuid",
            "oracle_id": "oracle-uuid",
            "name": "Test Walker",
        }
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=card):
            lookup_rulings("Test Walker", refresh=True)

        assert wire.urls() == ["https://api.scryfall.com/cards/card-uuid/rulings"]
        assert (_cache_dir() / "oracle-uuid.json").exists()

    def test_cached_result_reused(self, wire):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            lookup_rulings("Test Relic", refresh=True)
            # Second call should NOT hit the network.
            result = lookup_rulings("Test Relic", refresh=False)
        assert len(result["rulings"]) == 2
        assert wire.urls() == [_RULINGS_URL]

    def test_cache_expires_after_thirty_days(self, wire):
        import os
        import time

        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            lookup_rulings("Test Relic")
            cached = _cache_dir() / "oid-test-relic.json"
            old = time.time() - 31 * 86400
            os.utime(cached, (old, old))
            lookup_rulings("Test Relic")
        assert wire.urls() == [_RULINGS_URL, _RULINGS_URL]

    def test_refresh_flag_bypasses_cache(self, wire):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            lookup_rulings("Test Relic", refresh=True)
            lookup_rulings("Test Relic", refresh=True)
        # Two calls to Scryfall: one to seed the cache, one because
        # --refresh was set.
        assert wire.urls() == [_RULINGS_URL, _RULINGS_URL]

    def test_missing_card_returns_empty_oracle_id(self, wire):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=None):
            result = lookup_rulings("Nonexistent")
        assert result["oracle_id"] is None
        assert result["rulings"] == []
        assert wire.urls() == []

    def test_card_without_oracle_id(self, wire):
        token = {"name": "Token", "oracle_id": None, "legalities": {}}
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=token):
            result = lookup_rulings("Token")
        assert result["oracle_id"] is None
        assert result["rulings"] == []

    def test_batch_returns_list(self, wire):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            results = lookup_rulings_batch(["Test Relic", "Test Relic"])
        assert len(results) == 2
        assert wire.urls() == [_RULINGS_URL]  # the second is a cache hit

    def test_local_hit_never_calls_http(self, scryfall_wire):
        """Task #89: a rulings-index hit must serve locally — zero network."""
        rulings_index = {
            "oid-test-relic": (
                {"date": "2020-01-01", "text": "Taps for 2."},
                {"date": "2022-06-01", "text": "Still legal."},
            )
        }
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings("Test Relic", rulings_index=rulings_index)
        assert result["oracle_id"] == "oid-test-relic"
        assert result["source"] == "mtgjson-bulk"
        assert result["rulings"] == [
            {"published_at": "2020-01-01", "comment": "Taps for 2."},
            {"published_at": "2022-06-01", "comment": "Still legal."},
        ]
        assert scryfall_wire.urls() == []

    def test_local_miss_falls_back_to_api(self, wire):
        """A rulings-index that lacks the resolved oracle_id must fall
        back to the (unchanged, PR #21 id-threaded) Scryfall API path."""
        rulings_index: dict = {"some-other-oid": ({"date": "x", "text": "y"},)}
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings(
                "Test Relic", rulings_index=rulings_index, refresh=True
            )
        assert result["source"] == "scryfall-api"
        assert len(result["rulings"]) == 2
        assert wire.urls() == [_RULINGS_URL]

    def test_no_rulings_index_falls_back_to_api(self, wire):
        """No bulk configured at all (``rulings_index=None``,
        ``bulk_path=None``) preserves the pre-#89 API-only behavior."""
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings("Test Relic", refresh=True)
        assert result["source"] == "scryfall-api"
        assert wire.urls() == [_RULINGS_URL]

    def test_a_scryfall_error_raises(self, scryfall_wire):
        # Error handling is the caller's, as before the shared client: a 500 raises.
        scryfall_wire.route("/rulings", (500, b"oops"))
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
            pytest.raises(requests.HTTPError),
        ):
            lookup_rulings("Test Relic")

    def test_local_and_api_output_schema_equivalence(self, scryfall_wire):
        """A local-served entry and an API-served entry for the same
        underlying rulings must be byte-identical in shape — the CLI
        text report and JSON sidecar don't special-case the source."""
        rulings_index = {
            "oid-test-relic": ({"date": "2020-01-01", "text": "Taps for 2."},)
        }
        scryfall_wire.route(
            "/rulings",
            {"data": [{"published_at": "2020-01-01", "comment": "Taps for 2."}]},
        )
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            local = lookup_rulings("Test Relic", rulings_index=rulings_index)
            api = lookup_rulings("Test Relic", refresh=True)

        assert local["rulings"] == api["rulings"]
        assert set(local.keys()) == set(api.keys())
        assert local["source"] == "mtgjson-bulk"
        assert api["source"] == "scryfall-api"

    def test_batch_hits_api_only_for_local_misses(self, tmp_path, wire):
        """Batch mode (#89 item 3): the rulings index loads once and the
        API is only hit for cards that miss it locally."""
        bulk_path = tmp_path / "AllPrintings.json"
        bulk_path.write_text("{}", encoding="utf-8")

        cards = {
            "Test Relic": {**_FAKE_CARD, "name": "Test Relic"},
            "Local Card": {
                "id": "card-local",
                "oracle_id": "oid-local-hit",
                "name": "Local Card",
            },
        }
        rulings_index = {
            "oid-local-hit": ({"date": "2015-01-01", "text": "Local ruling."},)
        }

        def _fake_lookup_single(name, *, bulk_path=None, bulk_index=None):
            del bulk_path, bulk_index
            return cards[name]

        with (
            patch(
                "mtg_utils.rulings_lookup.lookup_single",
                side_effect=_fake_lookup_single,
            ),
            patch(
                "mtg_utils.card_pool.CardPool.load",
                lambda _p: SimpleNamespace(by_name={}),
            ),
            patch(
                "mtg_utils.rulings_lookup.load_rulings_index",
                return_value=rulings_index,
            ),
        ):
            results = lookup_rulings_batch(
                ["Test Relic", "Local Card"],
                bulk_path=bulk_path,
            )

        by_name = {r["name"]: r for r in results}
        assert by_name["Test Relic"]["source"] == "scryfall-api"
        assert by_name["Local Card"]["source"] == "mtgjson-bulk"
        assert by_name["Local Card"]["rulings"] == [
            {"published_at": "2015-01-01", "comment": "Local ruling."}
        ]

    def test_batch_loads_bulk_index_once(self, tmp_path, wire):
        """Pins the I-1 perf fix: the bulk pickle sidecar is loaded
        exactly once per batch invocation, not once per card.
        Regressing this would make 100-card batches pay ~30s of
        avoidable per-card pickle loads."""
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text("[]", encoding="utf-8")

        load_count = 0

        def _fake_load(_path):
            nonlocal load_count
            load_count += 1
            return SimpleNamespace(by_name={"Test Relic": _FAKE_CARD})

        with (
            patch("mtg_utils.card_pool.CardPool.load", _fake_load),
        ):
            results = lookup_rulings_batch(
                ["Test Relic"] * 10,
                bulk_path=bulk_path,
            )

        assert len(results) == 10
        assert load_count == 1, (
            f"expected 1 bulk load for 10-card batch, got {load_count}"
        )


class TestCLI:
    @pytest.fixture(autouse=True)
    def _no_local_bulk(self, monkeypatch):
        # main() falls back to default_bulk_path() when --bulk-data is
        # omitted, so on a dev machine with a cached AllPrintings these
        # tests would silently build/read the real rulings sidecar and
        # exercise a different branch than on CI. Pin the no-bulk branch;
        # the local-first path has its own fixture-backed tests above.
        monkeypatch.setattr("mtg_utils.rulings_lookup.default_bulk_path", lambda: None)

    def test_cli_single_card(self, tmp_path, wire):
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--card", "Test Relic"])
        assert result.exit_code == 0, result.output
        assert "Test Relic" in result.output
        assert "Full JSON:" in result.output

    def test_cli_batch_file(self, tmp_path, wire):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Test Relic", "Test Relic"]))

        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--batch", str(names_path)])
        assert result.exit_code == 0, result.output
        assert "2 card(s)" in result.output

    def test_cli_batch_deck_json(self, tmp_path, wire):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
                    "cards": [{"name": "Test Relic", "quantity": 1}],
                }
            )
        )
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--batch", str(deck_path)])
        assert result.exit_code == 0, result.output
        assert "2 card(s)" in result.output

    def test_cli_requires_card_or_batch(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "--card" in result.output or "--batch" in result.output

    def test_cli_nonexistent_bulk_data_fails_clean(self, tmp_path):
        """task #93: a nonexistent ``--bulk-data`` path used to raise a raw
        ``FileNotFoundError`` out of ``lookup_rulings_batch``'s eager
        ``CardPool.load`` call (task #89 repro). Click's
        ``exists=True`` now rejects it before that call ever runs — same
        pattern every other bulk-data CLI in the repo already uses
        (``card_search``, ``price_check``, ``combo_search``, ...)."""
        missing = tmp_path / "does-not-exist.json"
        runner = CliRunner()
        result = runner.invoke(
            main, ["--card", "Test Relic", "--bulk-data", str(missing)]
        )
        assert result.exit_code != 0
        assert isinstance(result.exception, SystemExit) or result.exception is None
        assert "does not exist" in result.output
        assert "Traceback" not in result.output
