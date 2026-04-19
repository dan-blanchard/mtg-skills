"""Tests for Scryfall per-card rulings fetcher."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mtg_utils.rulings_lookup import (
    _cache_dir,
    lookup_rulings,
    lookup_rulings_batch,
    main,
)

_FAKE_CARD = {"name": "Sol Ring", "oracle_id": "oid-solring", "legalities": {}}
_FAKE_RULINGS = [
    {"published_at": "2020-01-01", "comment": "Taps for 2."},
    {"published_at": "2022-06-01", "comment": "Still legal."},
]


@pytest.fixture(autouse=True)
def _isolated_rulings_cache(tmp_path, monkeypatch):
    """Redirect ``$TMPDIR`` so rulings cache files land in a per-test dir."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    # Ensure the module picks up the redirect (``_cache_dir`` reads the
    # env var on every call, so no manual reset needed).
    assert _cache_dir().parent == tmp_path


def _mock_session() -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"data": _FAKE_RULINGS}
    session = MagicMock()
    session.get.return_value = resp
    return session


class TestLookupRulings:
    def test_returns_card_rulings(self, tmp_path):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings(
                "Sol Ring",
                session=_mock_session(),
                refresh=True,
            )
        assert result["name"] == "Sol Ring"
        assert result["oracle_id"] == "oid-solring"
        assert len(result["rulings"]) == 2

    def test_cached_result_reused(self, tmp_path):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            s1 = _mock_session()
            lookup_rulings("Sol Ring", session=s1, refresh=True)
            # Second call should NOT hit the network (we pass a session
            # that would blow up if .get were called).
            s2 = MagicMock()
            s2.get.side_effect = AssertionError("cache should serve this call")
            result = lookup_rulings("Sol Ring", session=s2, refresh=False)
        assert len(result["rulings"]) == 2

    def test_refresh_flag_bypasses_cache(self, tmp_path):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            lookup_rulings("Sol Ring", session=_mock_session(), refresh=True)
            s = _mock_session()
            lookup_rulings("Sol Ring", session=s, refresh=True)
        # Two calls to Scryfall: one to seed the cache, one because
        # --refresh was set.
        assert s.get.call_count == 1

    def test_missing_card_returns_empty_oracle_id(self):
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=None):
            result = lookup_rulings("Nonexistent", session=_mock_session())
        assert result["oracle_id"] is None
        assert result["rulings"] == []

    def test_card_without_oracle_id(self):
        token = {"name": "Token", "oracle_id": None, "legalities": {}}
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=token):
            result = lookup_rulings("Token", session=_mock_session())
        assert result["oracle_id"] is None
        assert result["rulings"] == []

    def test_batch_returns_list(self, tmp_path):
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
        ):
            results = lookup_rulings_batch(["Sol Ring", "Sol Ring"])
        assert len(results) == 2

    def test_batch_loads_bulk_index_once(self, tmp_path):
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
            return {"sol ring": _FAKE_CARD}

        with (
            patch("mtg_utils.scryfall_lookup._load_bulk_index", _fake_load),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
        ):
            results = lookup_rulings_batch(
                ["Sol Ring"] * 10,
                bulk_path=bulk_path,
            )

        assert len(results) == 10
        assert load_count == 1, (
            f"expected 1 bulk load for 10-card batch, got {load_count}"
        )


class TestCLI:
    def test_cli_single_card(self, tmp_path):
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--card", "Sol Ring"])
        assert result.exit_code == 0, result.output
        assert "Sol Ring" in result.output
        assert "Full JSON:" in result.output

    def test_cli_batch_file(self, tmp_path):
        names_path = tmp_path / "names.json"
        names_path.write_text(json.dumps(["Sol Ring", "Sol Ring"]))

        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(main, ["--batch", str(names_path)])
        assert result.exit_code == 0, result.output
        assert "2 card(s)" in result.output

    def test_cli_batch_deck_json(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                }
            )
        )
        with (
            patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
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
