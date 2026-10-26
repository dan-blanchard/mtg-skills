"""ADR-0035 Stage-3a Step-1 — the crosswalk-backed sidecar builder + loader.

CI-safe: builds the sidecar from real cards' phase records out of the committed
card snapshot (``testkit.test_phase_records``; an explicit ``card_data_path`` so
``ensure_card_data`` never runs), then round-trips it through
``load_crosswalk_card_ir``. No bulk / network / cargo.
"""

from __future__ import annotations

import json

import pytest

from mtg_utils._card_ir import load
from mtg_utils._card_ir.build import build_crosswalk_sidecar
from mtg_utils._card_ir.load import (
    CROSSWALK_SIDECAR_VERSION,
    load_crosswalk_card_ir,
)
from mtg_utils.card_ir import Card
from mtg_utils.testkit import test_phase_records


@pytest.fixture(autouse=True)
def _persisted_spans(monkeypatch):
    """These tests read sidecars under tmp_path: the span index is persisted
    beside them, as in production (``tests/conftest.py`` keeps it in memory)."""
    monkeypatch.delenv("MTG_SKILLS_CARD_IR_SPANS", raising=False)


@pytest.fixture
def card_data_file(tmp_path):
    """A small phase ``card-data.json``: a vanilla creature, a mana creature, a
    token maker, a DFC (two faces, one oracle_id) and a split card."""
    records: list[dict] = []
    for name in (
        "Grizzly Bears",
        "Llanowar Elves",
        "Krenko, Mob Boss",
        "Avatar Aang // Aang, Master of Elements",
        "Fire // Ice",
    ):
        records.extend(test_phase_records(name))
    cdp = tmp_path / "card-data.json"
    cdp.write_text(json.dumps(records))
    return cdp


def test_build_writes_versioned_sidecar(card_data_file, tmp_path):
    out = tmp_path / "card-ir-crosswalk.json"
    path, stats = build_crosswalk_sidecar(card_data_file, out)
    assert path == out
    assert stats["cards"] > 0
    payload = json.loads(out.read_text())
    assert payload["version"] == CROSSWALK_SIDECAR_VERSION
    assert "phase_tag" in payload
    assert len(payload["cards"]) == stats["cards"]


def test_loader_round_trips_compat_cards(card_data_file, tmp_path):
    out = tmp_path / "card-ir-crosswalk.json"
    _path, stats = build_crosswalk_sidecar(card_data_file, out)
    cards = load_crosswalk_card_ir(out)
    assert len(cards) == stats["cards"]
    oid, card = next(iter(cards.items()))
    assert isinstance(card, Card)
    assert card.oracle_id == oid
    # Every compat Card is round-trippable (the on-disk contract ir_for reads).
    assert Card.from_dict(card.to_dict()).to_dict() == card.to_dict()


def test_loader_rejects_wrong_version(card_data_file, tmp_path):
    out = tmp_path / "card-ir-crosswalk.json"
    build_crosswalk_sidecar(card_data_file, out)
    payload = json.loads(out.read_text())
    payload["version"] = CROSSWALK_SIDECAR_VERSION + 999
    out.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="version"):
        load_crosswalk_card_ir(out)


def test_loader_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="build-card-ir-crosswalk"):
        load_crosswalk_card_ir(tmp_path / "absent.json")


def _as_dicts(cards) -> dict:
    return {oid: cards[oid].to_dict() for oid in cards}


def _decoded(raw_cards: dict) -> dict:
    return {oid: Card.from_dict(raw).to_dict() for oid, raw in raw_cards.items()}


def test_loader_reads_each_card_from_its_span(card_data_file, tmp_path, monkeypatch):
    """The loader decodes a card from its span of the sidecar (the span index
    beside it), never the whole file: every card reads as the whole-file
    decode does, and a later process reads the stored index."""
    out = tmp_path / "card-ir-crosswalk.json"
    build_crosswalk_sidecar(card_data_file, out)
    whole = json.loads(out.read_text())["cards"]
    assert _as_dicts(load_crosswalk_card_ir(out)) == _decoded(whole)
    assert (tmp_path / "card-ir-crosswalk.json.spans.pkl").exists()

    load.clear_memory_cache()

    def no_rebuild(*_args):
        raise AssertionError("the stored index was rebuilt")

    monkeypatch.setattr(load, "_span_index", no_rebuild)
    assert _as_dicts(load_crosswalk_card_ir(out)) == _decoded(whole)


def test_a_rewritten_sidecar_rebuilds_its_span_index(card_data_file, tmp_path):
    """The index is keyed by the sidecar's mtime and size: a rewritten sidecar
    (here: one card fewer, in another layout) reads from a fresh index."""
    out = tmp_path / "card-ir-crosswalk.json"
    build_crosswalk_sidecar(card_data_file, out)
    load_crosswalk_card_ir(out)
    payload = json.loads(out.read_text())
    dropped = next(iter(payload["cards"]))
    del payload["cards"][dropped]
    out.write_text(json.dumps(payload, separators=(",", ":")))
    load.clear_memory_cache()
    cards = load_crosswalk_card_ir(out)
    assert dropped not in cards
    assert _as_dicts(cards) == _decoded(payload["cards"])


def test_a_non_ascii_sidecar_is_decoded_whole(card_data_file, tmp_path):
    """Spans are byte offsets only in an ASCII file (what ``json.dump`` writes);
    a sidecar with raw non-ASCII text is decoded whole instead."""
    out = tmp_path / "card-ir-crosswalk.json"
    build_crosswalk_sidecar(card_data_file, out)
    payload = json.loads(out.read_text())
    oid = next(iter(payload["cards"]))
    payload["cards"][oid]["n"] = "Æther — test"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    load.clear_memory_cache()
    assert _as_dicts(load_crosswalk_card_ir(out)) == _decoded(payload["cards"])
