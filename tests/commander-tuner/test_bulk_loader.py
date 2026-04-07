"""Tests for bulk_loader sidecar caching."""

import json
import os
import pickle
from pathlib import Path

import pytest

from commander_utils.bulk_loader import (
    SIDECAR_VERSION,
    _sidecar_path,
    build_sidecar,
    load_bulk_cards,
)


@pytest.fixture
def bulk_path(tmp_path: Path) -> Path:
    cards = [
        {"name": "Sol Ring", "type_line": "Artifact"},
        {"name": "Lightning Bolt", "type_line": "Instant"},
    ]
    path = tmp_path / "default-cards.json"
    path.write_text(json.dumps(cards))
    return path


def test_cold_load_builds_sidecar(bulk_path: Path):
    sidecar = _sidecar_path(bulk_path)
    assert not sidecar.exists()

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 2
    assert sidecar.exists()


def test_warm_load_uses_sidecar_not_json(bulk_path: Path):
    # Cold load to build the sidecar
    load_bulk_cards(bulk_path)

    # Corrupt the JSON; warm load should still succeed because it reads
    # the sidecar (which still has the good data and a fresh-enough mtime).
    bulk_path.write_text("not valid json", encoding="utf-8")
    # Reset the JSON's mtime to before the sidecar so the freshness check
    # accepts the sidecar — write_text bumps mtime to "now", which would
    # otherwise invalidate the sidecar.
    sidecar = _sidecar_path(bulk_path)
    older = sidecar.stat().st_mtime - 10
    os.utime(bulk_path, (older, older))

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 2
    assert cards[0]["name"] == "Sol Ring"


def test_stale_sidecar_triggers_rebuild(bulk_path: Path):
    # Cold load builds the sidecar
    load_bulk_cards(bulk_path)
    sidecar = _sidecar_path(bulk_path)
    sidecar_mtime = sidecar.stat().st_mtime

    # Update the JSON to a new value with a strictly newer mtime
    new_cards = [{"name": "Counterspell", "type_line": "Instant"}]
    bulk_path.write_text(json.dumps(new_cards))
    newer = sidecar_mtime + 10
    os.utime(bulk_path, (newer, newer))

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 1
    assert cards[0]["name"] == "Counterspell"
    # The sidecar must have been rewritten with the new contents
    with sidecar.open("rb") as f:
        payload = pickle.load(f)
    assert payload["cards"][0]["name"] == "Counterspell"


def test_missing_sidecar_falls_back_to_json(bulk_path: Path):
    # Build then delete the sidecar
    load_bulk_cards(bulk_path)
    sidecar = _sidecar_path(bulk_path)
    sidecar.unlink()
    assert not sidecar.exists()

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 2
    # Sidecar should be rebuilt
    assert sidecar.exists()


def test_version_mismatch_triggers_rebuild(bulk_path: Path):
    sidecar = _sidecar_path(bulk_path)
    # Hand-write a sidecar with a wrong version
    with sidecar.open("wb") as f:
        pickle.dump(
            {"version": SIDECAR_VERSION + 99, "cards": [{"name": "Bogus"}]},
            f,
        )
    # Touch sidecar to be newer than JSON so the freshness check would
    # otherwise accept it.
    newer = bulk_path.stat().st_mtime + 10
    os.utime(sidecar, (newer, newer))

    cards = load_bulk_cards(bulk_path)
    # Bogus version is rejected — we should see the real JSON contents
    assert len(cards) == 2
    assert cards[0]["name"] == "Sol Ring"


def test_corrupt_sidecar_falls_back_to_json(bulk_path: Path):
    sidecar = _sidecar_path(bulk_path)
    sidecar.write_bytes(b"not a valid pickle stream")
    # Make sidecar fresh-enough so freshness wouldn't reject it on its own
    newer = bulk_path.stat().st_mtime + 10
    os.utime(sidecar, (newer, newer))

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 2
    # And the corrupt file should have been overwritten with a real sidecar
    with sidecar.open("rb") as f:
        payload = pickle.load(f)
    assert payload["version"] == SIDECAR_VERSION
    assert len(payload["cards"]) == 2


def test_build_sidecar_eagerly(bulk_path: Path):
    sidecar = _sidecar_path(bulk_path)
    assert not sidecar.exists()
    result = build_sidecar(bulk_path)
    assert result == sidecar
    assert sidecar.exists()
    with sidecar.open("rb") as f:
        payload = pickle.load(f)
    assert payload["version"] == SIDECAR_VERSION
    assert len(payload["cards"]) == 2


def test_concurrent_writers_dont_observe_partial(bulk_path: Path):
    """The atomic-rename pattern guarantees readers never see a half-written
    sidecar even if a writer crashes mid-stream. Simulate by leaving a
    .tmp turd behind and confirming load still works.
    """
    sidecar = _sidecar_path(bulk_path)
    leftover_tmp = sidecar.with_name(sidecar.name + ".tmp")
    leftover_tmp.write_bytes(b"partial garbage")

    cards = load_bulk_cards(bulk_path)
    assert len(cards) == 2
    # Real sidecar should now exist; the leftover tmp is irrelevant
    assert sidecar.exists()
