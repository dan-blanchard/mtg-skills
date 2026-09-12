"""deck-hydrate: the explicit warm step over the acquisition seam (ADR-0046)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from mtg_utils.deck_hydrate import main
from mtg_utils.hydrated_deck import sidecar_path


def _deck_file(tmp_path, cards):
    deck = {
        "format": "commander",
        "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        "cards": [{"name": n, "quantity": 1} for n in cards],
        "sideboard": [],
    }
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck), encoding="utf-8")
    return path


def test_envelope_reports_sidecar_count_missing_and_digest(
    sample_bulk_data, tmp_path, monkeypatch
):
    monkeypatch.setattr("mtg_utils.scryfall_lookup.fetch_card", lambda _n: None)
    deck_path = _deck_file(tmp_path, ["Sol Ring", "Command Tower", "Totally Fake"])
    result = CliRunner().invoke(
        main, [str(deck_path), "--bulk-data", str(sample_bulk_data)]
    )
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert set(envelope) == {"sidecar_path", "card_count", "missing", "digest"}
    assert envelope["sidecar_path"] == str(sidecar_path(deck_path).resolve())
    assert envelope["card_count"] == 3
    assert envelope["missing"] == ["Totally Fake"]
    assert envelope["digest"]["categories"]["lands"] == 1
    assert "Totally Fake" in result.stderr  # the warning names the miss
    assert sidecar_path(deck_path).exists()


def test_no_bulk_is_a_clean_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    deck_path = _deck_file(tmp_path, ["Sol Ring"])
    result = CliRunner().invoke(main, [str(deck_path)])
    assert result.exit_code == 1
    assert "download-mtgjson" in result.output
    assert "Traceback" not in result.output
