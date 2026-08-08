"""Unit tests for the oracle_id -> signal-idents sidecar (task #90).

``TestByteEquivalenceAgainstRealSnapshot`` is the correctness bar: the
sidecar must be a pure CACHE of ``extract_signals``'s live output,
never a divergent second system. Every other class uses a monkeypatched
``extract_signals`` + synthetic bulk files so the suite runs in CI
with no real bulk / phase cache / network.
"""

from __future__ import annotations

import pickle

from mtg_utils._deck_forge import signals_index
from mtg_utils._deck_forge.signals import Signal


def _sig(key, scope="you", subject=""):
    return Signal(key, scope, subject, "", "Fake Card", "high")


class TestBuildSignalsIndex:
    def test_dedupes_by_oracle_id_first_wins(self, monkeypatch):
        calls = []

        def fake_extract(rec, *_args, **_kwargs):
            calls.append(rec["name"])
            return [_sig("ramp")]

        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals", fake_extract
        )
        records = [
            {"oracle_id": "oid-1", "name": "Printing A"},
            {"oracle_id": "oid-1", "name": "Printing B"},  # same card, reprint
            {"oracle_id": "oid-2", "name": "Other Card"},
        ]
        index = signals_index.build_signals_index(records)

        assert set(index) == {"oid-1", "oid-2"}
        # Only the FIRST printing of oid-1 was ever extracted.
        assert calls == ["Printing A", "Other Card"]

    def test_skips_records_without_oracle_id(self, monkeypatch):
        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [_sig("ramp")],
        )
        records = [{"name": "No Oracle Id"}, {"oracle_id": "", "name": "Empty"}]
        assert signals_index.build_signals_index(records) == {}

    def test_ident_format_is_key_pipe_scope_pipe_subject(self, monkeypatch):
        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [
                _sig("type_matters", "you", "Goblin"),
                _sig("ramp", "you", ""),
            ],
        )
        records = [{"oracle_id": "oid-1", "name": "Card"}]
        index = signals_index.build_signals_index(records)
        assert index["oid-1"] == ("ramp|you|", "type_matters|you|Goblin")

    def test_empty_signal_list_is_a_real_cached_answer(self, monkeypatch):
        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [],
        )
        records = [{"oracle_id": "oid-1", "name": "Vanilla"}]
        index = signals_index.build_signals_index(records)
        assert index == {"oid-1": ()}


class TestSignalSourceFiles:
    def test_includes_the_known_lane_and_tree_layer_files(self):
        names = {p.name for p in signals_index.signal_source_files()}
        # The lane-facing modules (ADR-0035/0039) named in the task.
        assert "signals.py" in names
        # crosswalk_signals.py was split into the lanes/ subpackage — the
        # closure reaches every lane-family module through its __init__.
        for lane_module in (
            "manifest.py",
            "_shared.py",
            "core_makers.py",
            "board_and_ramp.py",
            "counters_voltron.py",
            "graveyard_lifeloss.py",
            "keyword_mechanics.py",
            "mana_and_wipes.py",
            "card_advantage.py",
            "triggers_damage.py",
            "stax_and_tempo.py",
            "removal_tutors.py",
            "protection_and_sweep.py",
        ):
            assert lane_module in names
        assert "membership_floor.py" in names
        assert "text_reads.py" in names
        assert "signal_base.py" in names
        assert "_subtypes.py" in names
        assert "bridge_ledger.py" in names
        assert "signal_keys.py" in names  # from pkg import submodule form
        # The _card_ir concept-tree layer. crosswalk.py and tree_synthesis.py
        # are packages now — the closure reaches their split modules.
        assert "core.py" in names  # crosswalk/core.py
        assert "reads.py" in names  # crosswalk/reads.py
        assert "_registry.py" in names  # tree_synthesis/_registry.py
        assert "recovery.py" in names
        assert "text_idioms.py" in names
        assert "overlay_corrections.py" in names
        assert "_ir_lookup.py" in names
        assert "schema.py" in names  # mirror/schema.py — codegen'd substrate

    def test_excludes_signal_specs_which_does_not_feed_extraction(self):
        # signal_specs/ builds card_search serve/search kwargs from a Signal
        # AFTER extraction — it never feeds extract_signals's own output, so
        # it must not force a spurious rebuild on every edit. Checked by
        # PATH PARTS, not basename: signal_specs is now a package
        # (`_deck_forge/signal_specs/__init__.py`, `core.py`, `data_1.py`, …),
        # so no file in the closure is literally named "signal_specs.py" —
        # a basename check is vacuously true regardless of whether the
        # package ever entered the closure. Verified this assertion isn't
        # itself vacuous by temporarily splicing a synthetic
        # `.../signal_specs/core.py` path into the files tuple and
        # confirming `not any(...)` fails against it (reverted before
        # committing this test).
        files = signals_index.signal_source_files()
        assert not any("signal_specs" in p.parts for p in files)


class TestContentHash:
    def test_changes_when_a_source_file_gains_a_byte(self, tmp_path, monkeypatch):
        fake = tmp_path / "fake_lane.py"
        fake.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(signals_index, "signal_source_files", lambda: (fake,))

        before = signals_index._content_hash()
        fake.write_text("x = 1  # a comment\n", encoding="utf-8")
        after = signals_index._content_hash()

        assert before != after

    def test_stable_when_nothing_changes(self, tmp_path, monkeypatch):
        fake = tmp_path / "fake_lane.py"
        fake.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(signals_index, "signal_source_files", lambda: (fake,))

        assert signals_index._content_hash() == signals_index._content_hash()

    def test_changes_with_phase_tag(self, tmp_path, monkeypatch):
        fake = tmp_path / "fake_lane.py"
        fake.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(signals_index, "signal_source_files", lambda: (fake,))
        monkeypatch.setattr("mtg_utils._phase.PHASE_TAG", "v0.23.0")
        before = signals_index._content_hash()
        monkeypatch.setattr("mtg_utils._phase.PHASE_TAG", "v9.9.9")
        after = signals_index._content_hash()
        assert before != after

    def test_changes_with_sidecar_version(self, tmp_path, monkeypatch):
        fake = tmp_path / "fake_lane.py"
        fake.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(signals_index, "signal_source_files", lambda: (fake,))
        before = signals_index._content_hash()
        monkeypatch.setattr(signals_index, "SIGNALS_SIDECAR_VERSION", 999)
        after = signals_index._content_hash()
        assert before != after


class TestLoadSignalsIndex:
    def test_none_bulk_path_returns_none(self):
        assert signals_index.load_signals_index(None) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert signals_index.load_signals_index(tmp_path / "AllPrintings.json") is None

    def test_builds_persists_and_reuses_cache(self, tmp_path, monkeypatch):
        bulk = tmp_path / "AllPrintings.json"
        bulk.write_text("{}", encoding="utf-8")
        sidecar = bulk.with_name(bulk.name + ".signals.pkl")
        assert not sidecar.exists()

        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [_sig("ramp")],
        )
        records = [{"oracle_id": "oid-1", "name": "Card"}]
        index = signals_index.load_signals_index(bulk, records=records)
        assert index == {"oid-1": ("ramp|you|",)}
        assert sidecar.exists()

        # Second call must be a pure cache hit — a live extractor call here
        # would be a bug, so make one raise.
        def boom(_rec, *_args, **_kwargs):
            raise AssertionError("recomputed despite a fresh, matching sidecar")

        monkeypatch.setattr("mtg_utils._deck_forge.signals.extract_signals", boom)
        cached = signals_index.load_signals_index(bulk, records=records)
        assert cached == index

    def test_bulk_identity_change_invalidates(self, tmp_path, monkeypatch):
        bulk = tmp_path / "AllPrintings.json"
        bulk.write_text("{}", encoding="utf-8")
        calls = []

        def fake_extract(rec, *_args, **_kwargs):
            calls.append(rec["oracle_id"])
            return []

        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals", fake_extract
        )
        records = [{"oracle_id": "oid-1", "name": "Card"}]
        signals_index.load_signals_index(bulk, records=records)
        assert calls == ["oid-1"]

        # A download-mtgjson refresh: different size (and, typically, mtime).
        bulk.write_text("{}\n\n", encoding="utf-8")
        signals_index.load_signals_index(bulk, records=records)
        assert calls == ["oid-1", "oid-1"]  # rebuilt, never served stale

    def test_content_hash_change_invalidates(self, tmp_path, monkeypatch):
        bulk = tmp_path / "AllPrintings.json"
        bulk.write_text("{}", encoding="utf-8")
        calls = []

        def fake_extract(rec, *_args, **_kwargs):
            calls.append(rec["oracle_id"])
            return []

        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals", fake_extract
        )
        records = [{"oracle_id": "oid-1", "name": "Card"}]
        signals_index.load_signals_index(bulk, records=records)
        assert calls == ["oid-1"]

        # Simulate a lane-source edit: the content hash changes even though
        # the bulk file itself is untouched.
        monkeypatch.setattr(signals_index, "_content_hash", lambda: "different-hash")
        signals_index.load_signals_index(bulk, records=records)
        assert calls == ["oid-1", "oid-1"]

    def test_sidecar_payload_shape(self, tmp_path, monkeypatch):
        bulk = tmp_path / "AllPrintings.json"
        bulk.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [_sig("ramp")],
        )
        signals_index.load_signals_index(bulk, records=[{"oracle_id": "oid-1"}])
        sidecar = bulk.with_name(bulk.name + ".signals.pkl")
        with sidecar.open("rb") as f:
            payload = pickle.load(f)
        assert payload["version"] == signals_index.SIGNALS_SIDECAR_VERSION
        assert "content_hash" in payload
        assert payload["bulk_identity"][0] == str(bulk)
        assert payload["index"] == {"oid-1": ("ramp|you|",)}

    def test_loads_records_lazily_when_not_supplied(self, tmp_path, monkeypatch):
        # A non-"AllPrintings.json" name loads as a plain legacy Scryfall bulk
        # list (bulk_loader._read_source's non-MTGJSON branch).
        bulk = tmp_path / "bulk.json"
        bulk.write_text('[{"oracle_id": "oid-1", "name": "Card"}]', encoding="utf-8")
        monkeypatch.setattr(
            "mtg_utils._deck_forge.signals.extract_signals",
            lambda _rec, *_args, **_kwargs: [_sig("ramp")],
        )
        index = signals_index.load_signals_index(bulk)
        assert index == {"oid-1": ("ramp|you|",)}


class TestByteEquivalenceAgainstRealSnapshot:
    """The correctness bar (task #90): the sidecar is a pure cache — every
    stored entry must equal a fresh live ``extract_signals`` run on
    the SAME real card, over the committed snapshot fixture (no bulk/phase/
    network needed in CI)."""

    def test_matches_live_extraction_for_every_snapshot_card(self):
        from mtg_utils import testkit

        names = sorted(testkit._snapshot()["cards"])
        assert names, "the committed card snapshot must not be empty"

        records = []
        for name in names:
            testkit.test_signals(name)  # seeds the crosswalk trees memo
            records.append(testkit.test_card(name))

        index = signals_index.build_signals_index(records)

        seen_oids: set[str] = set()
        checked = 0
        for name, rec in zip(names, records, strict=True):
            oid = rec.get("oracle_id")
            if not oid or oid in seen_oids:
                continue
            seen_oids.add(oid)
            live = {
                f"{s.key}|{s.scope}|{s.subject}" for s in testkit.test_signals(name)
            }
            assert set(index.get(oid, ())) == live, name
            checked += 1
        assert checked > 0
