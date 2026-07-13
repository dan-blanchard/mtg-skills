"""Unit tests for the MTGJSON oracle-id-keyed rulings sidecar (task #89).

Synthetic ``AllPrintings``-shaped input so the suite runs in CI with no
MTGJSON data on disk. Modeled on the real per-printing shape: every
printing of a card carries an identical copy of its rulings, keyed by
``identifiers.scryfallOracleId``.
"""

from __future__ import annotations

import json

from mtg_utils._mtgjson.rulings_index import (
    RULINGS_SIDECAR_VERSION,
    build_rulings_index,
    load_rulings_index,
)

_ALLPRINTINGS = {
    "data": {
        "2X2": {
            "type": "expansion",
            "name": "Double Masters 2022",
            "releaseDate": "2022-07-08",
            "cards": [
                {
                    "name": "Chaos Warp",
                    "uuid": "uuid-2x2-chaos-warp",
                    "identifiers": {"scryfallOracleId": "oid-chaos-warp"},
                    "rulings": [
                        {
                            "date": "2011-09-22",
                            "text": "A permanent card is a card with one "
                            "or more of the following card types.",
                        },
                        {
                            "date": "2011-09-22",
                            "text": "If the permanent is an illegal "
                            "target, it won't resolve.",
                        },
                    ],
                },
                {
                    "name": "Sol Ring",
                    "uuid": "uuid-2x2-sol-ring",
                    "identifiers": {"scryfallOracleId": "oid-sol-ring"},
                    "rulings": [],
                },
            ],
        },
        "CMD": {
            "type": "commander",
            "name": "Commander",
            "releaseDate": "2011-06-17",
            "cards": [
                # A reprint of Chaos Warp — same oracle id, identical
                # rulings (the oracle-level-duplication pattern). Proves
                # aggregation dedupes rather than double-counting.
                {
                    "name": "Chaos Warp",
                    "uuid": "uuid-cmd-chaos-warp",
                    "identifiers": {"scryfallOracleId": "oid-chaos-warp"},
                    "rulings": [
                        {
                            "date": "2011-09-22",
                            "text": "A permanent card is a card with one "
                            "or more of the following card types.",
                        },
                        {
                            "date": "2011-09-22",
                            "text": "If the permanent is an illegal "
                            "target, it won't resolve.",
                        },
                    ],
                },
                # A card with no rulings at all — must not appear in the
                # built index.
                {
                    "name": "Forest",
                    "uuid": "uuid-cmd-forest",
                    "identifiers": {"scryfallOracleId": "oid-forest"},
                },
            ],
        },
    }
}


def _write_allprintings(tmp_path):
    path = tmp_path / "AllPrintings.json"
    path.write_text(json.dumps(_ALLPRINTINGS), encoding="utf-8")
    return path


class TestBuildRulingsIndex:
    def test_aggregates_and_dedupes_across_printings(self, tmp_path):
        path = _write_allprintings(tmp_path)
        index = build_rulings_index(path)

        assert "oid-chaos-warp" in index
        # Two distinct rulings, not four — the 2X2 and CMD printings
        # carry identical copies and must be deduped, not unioned as
        # separate entries.
        assert len(index["oid-chaos-warp"]) == 2
        assert index["oid-chaos-warp"][0] == {
            "date": "2011-09-22",
            "text": "A permanent card is a card with one or more of the "
            "following card types.",
        }

    def test_card_without_rulings_omitted(self, tmp_path):
        path = _write_allprintings(tmp_path)
        index = build_rulings_index(path)
        assert "oid-sol-ring" not in index
        assert "oid-forest" not in index


class TestLoadRulingsIndex:
    def test_none_bulk_path_returns_none(self):
        assert load_rulings_index(None) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert load_rulings_index(tmp_path / "AllPrintings.json") is None

    def test_non_mtgjson_filename_returns_none(self, tmp_path):
        # A legacy Scryfall bulk file carries no rulings at all — must
        # not attempt to parse it as MTGJSON.
        path = tmp_path / "default-cards.json"
        path.write_text("[]", encoding="utf-8")
        assert load_rulings_index(path) is None

    def test_builds_and_caches_sidecar(self, tmp_path):
        path = _write_allprintings(tmp_path)
        sidecar = path.with_name(path.name + ".rulings.pkl")
        assert not sidecar.exists()

        index = load_rulings_index(path)
        assert index is not None
        assert "oid-chaos-warp" in index
        assert sidecar.exists()

        # Second call reads the cached sidecar rather than reparsing —
        # verified indirectly by mutating the source file so a reparse
        # would pick up the change while a cache hit would not.
        stale_data = json.loads(path.read_text(encoding="utf-8"))
        stale_data["data"]["2X2"]["cards"][0]["rulings"].append(
            {"date": "2099-01-01", "text": "should not appear"}
        )
        # Don't touch the file's mtime forward of the sidecar's, so the
        # freshness check still prefers the cache.
        path.write_text(json.dumps(stale_data), encoding="utf-8")
        sidecar_mtime = sidecar.stat().st_mtime
        import os

        os.utime(path, (sidecar_mtime - 10, sidecar_mtime - 10))

        cached = load_rulings_index(path)
        assert len(cached["oid-chaos-warp"]) == 2

    def test_sidecar_version_tag(self, tmp_path):
        path = _write_allprintings(tmp_path)
        load_rulings_index(path)
        sidecar = path.with_name(path.name + ".rulings.pkl")
        import pickle

        with sidecar.open("rb") as f:
            payload = pickle.load(f)
        assert payload["version"] == RULINGS_SIDECAR_VERSION
