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

_FAKE_CARD = {
    "id": "card-solring",
    "name": "Sol Ring",
    "oracle_id": "oid-solring",
    "legalities": {},
}
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
        session = _mock_session()
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings(
                "Sol Ring",
                session=session,
                refresh=True,
            )
        assert result["name"] == "Sol Ring"
        assert result["oracle_id"] == "oid-solring"
        assert len(result["rulings"]) == 2
        session.get.assert_called_once_with(
            "https://api.scryfall.com/cards/card-solring/rulings",
            timeout=15,
        )

    def test_rulings_lookup_uses_card_id_not_oracle_id(self, tmp_path):
        card = {
            "id": "card-uuid",
            "oracle_id": "oracle-uuid",
            "name": "Karn, the Great Creator",
        }
        session = _mock_session()

        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=card):
            lookup_rulings(
                "Karn, the Great Creator",
                session=session,
                refresh=True,
            )

        session.get.assert_called_once_with(
            "https://api.scryfall.com/cards/card-uuid/rulings",
            timeout=15,
        )
        assert (_cache_dir() / "oracle-uuid.json").exists()

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

    def test_local_hit_never_calls_http(self, tmp_path):
        """Task #89: a rulings-index hit must serve locally — zero network."""
        rulings_index = {
            "oid-solring": (
                {"date": "2020-01-01", "text": "Taps for 2."},
                {"date": "2022-06-01", "text": "Still legal."},
            )
        }
        session = MagicMock()
        session.get.side_effect = AssertionError("local hit must not call HTTP")
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings(
                "Sol Ring",
                rulings_index=rulings_index,
                session=session,
            )
        assert result["oracle_id"] == "oid-solring"
        assert result["source"] == "mtgjson-bulk"
        assert result["rulings"] == [
            {"published_at": "2020-01-01", "comment": "Taps for 2."},
            {"published_at": "2022-06-01", "comment": "Still legal."},
        ]
        session.get.assert_not_called()

    def test_local_miss_falls_back_to_api(self, tmp_path):
        """A rulings-index that lacks the resolved oracle_id must fall
        back to the (unchanged, PR #21 id-threaded) Scryfall API path."""
        rulings_index: dict = {"some-other-oid": ({"date": "x", "text": "y"},)}
        session = _mock_session()
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings(
                "Sol Ring",
                rulings_index=rulings_index,
                session=session,
                refresh=True,
            )
        assert result["source"] == "scryfall-api"
        assert len(result["rulings"]) == 2
        session.get.assert_called_once_with(
            "https://api.scryfall.com/cards/card-solring/rulings",
            timeout=15,
        )

    def test_no_rulings_index_falls_back_to_api(self, tmp_path):
        """No bulk configured at all (``rulings_index=None``,
        ``bulk_path=None``) preserves the pre-#89 API-only behavior."""
        session = _mock_session()
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            result = lookup_rulings("Sol Ring", session=session, refresh=True)
        assert result["source"] == "scryfall-api"
        session.get.assert_called_once_with(
            "https://api.scryfall.com/cards/card-solring/rulings",
            timeout=15,
        )

    def test_local_and_api_output_schema_equivalence(self):
        """A local-served entry and an API-served entry for the same
        underlying rulings must be byte-identical in shape — the CLI
        text report and JSON sidecar don't special-case the source."""
        rulings_index = {
            "oid-solring": ({"date": "2020-01-01", "text": "Taps for 2."},)
        }
        with patch("mtg_utils.rulings_lookup.lookup_single", return_value=_FAKE_CARD):
            local = lookup_rulings(
                "Sol Ring",
                rulings_index=rulings_index,
                session=MagicMock(),
            )
            api_session = MagicMock()
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "data": [{"published_at": "2020-01-01", "comment": "Taps for 2."}]
            }
            api_session.get.return_value = resp
            api = lookup_rulings("Sol Ring", session=api_session, refresh=True)

        assert local["rulings"] == api["rulings"]
        assert set(local.keys()) == set(api.keys())
        assert local["source"] == "mtgjson-bulk"
        assert api["source"] == "scryfall-api"

    def test_batch_hits_api_only_for_local_misses(self, tmp_path):
        """Batch mode (#89 item 3): the rulings index loads once and the
        API is only hit for cards that miss it locally."""
        bulk_path = tmp_path / "AllPrintings.json"
        bulk_path.write_text("{}", encoding="utf-8")

        cards = {
            "Sol Ring": {**_FAKE_CARD, "name": "Sol Ring"},
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
            patch("mtg_utils.scryfall_lookup._load_bulk_index", lambda _p: {}),
            patch(
                "mtg_utils.rulings_lookup.load_rulings_index",
                return_value=rulings_index,
            ),
            patch(
                "mtg_utils.rulings_lookup._new_session",
                return_value=_mock_session(),
            ),
        ):
            results = lookup_rulings_batch(
                ["Sol Ring", "Local Card"],
                bulk_path=bulk_path,
            )

        by_name = {r["name"]: r for r in results}
        assert by_name["Sol Ring"]["source"] == "scryfall-api"
        assert by_name["Local Card"]["source"] == "mtgjson-bulk"
        assert by_name["Local Card"]["rulings"] == [
            {"published_at": "2015-01-01", "comment": "Local ruling."}
        ]

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
    @pytest.fixture(autouse=True)
    def _no_local_bulk(self, monkeypatch):
        # main() falls back to default_bulk_path() when --bulk-data is
        # omitted, so on a dev machine with a cached AllPrintings these
        # tests would silently build/read the real rulings sidecar and
        # exercise a different branch than on CI. Pin the no-bulk branch;
        # the local-first path has its own fixture-backed tests above.
        monkeypatch.setattr("mtg_utils.rulings_lookup.default_bulk_path", lambda: None)

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
