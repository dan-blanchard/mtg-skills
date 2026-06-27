"""Smoke tests for the deck-tune CLI (ADR-0029) — the thin adapter that runs the
deterministic tuner as deck-wizard's Step-6 spine. The tuner core is tested in
test_tuner_tune.py; these cover the CLI plumbing (format guard, injection, output)."""

import json

import pytest
from click.testing import CliRunner

from mtg_utils import combo_search
from mtg_utils.deck_tune import main as deck_tune_main

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "cmc": 4.0,
    "color_identity": ["R"],
    "oracle_text": "{T}: Create X 1/1 red Goblin creature tokens.",
    "legalities": {"commander": "legal"},
}
MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "cmc": 0.0,
    "color_identity": ["R"],
    "oracle_text": "",
    "produced_mana": ["R"],
    "legalities": {"commander": "legal"},
}
HYDRATED = [KRENKO, MOUNTAIN]
COMMANDER_DECK = {
    "format": "commander",
    "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
    "cards": [{"name": "Mountain", "quantity": 10}],
    "sideboard": [],
}
CONSTRUCTED_DECK = {
    "format": "modern",
    "commanders": [],
    "cards": [{"name": "Mountain", "quantity": 10}],
}


@pytest.fixture(autouse=True)
def _offline_and_fast(monkeypatch):
    # combo_search hits Commander Spellbook; keep the suite network-free.
    monkeypatch.setattr(combo_search, "combo_search", lambda _hd: {"combos": []})
    # The smoke test covers the adapter, not the (production-only) sidecar build —
    # no-op it so we don't pay the one-time Card IR build cost per test.
    monkeypatch.setattr("mtg_utils.deck_tune._ensure_ir", lambda: None)


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def _bulk(tmp_path):
    p = tmp_path / "bulk.json"
    p.write_text("[]", encoding="utf-8")
    return str(p)


def test_refuses_constructed_format(tmp_path):
    deck = _write(tmp_path, "deck.json", CONSTRUCTED_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, hyd, "--bulk-data", _bulk(tmp_path)]
    )
    assert res.exit_code != 0
    assert "Commander-family" in res.output


def test_diagnoses_a_commander_deck(tmp_path):
    deck = _write(tmp_path, "deck.json", COMMANDER_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    out_path = tmp_path / "tune.json"
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, hyd, "--bulk-data", _bulk(tmp_path), "--output", str(out_path)],
    )
    assert res.exit_code == 0, res.output
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert "scorecard" in out
    assert out["swaps"] == []  # max-swaps defaults to 0
    assert out["scorecard"]["bracket"] is None  # no --bracket → no gate


def test_bracket_flag_runs_the_gate(tmp_path):
    deck = _write(tmp_path, "deck.json", COMMANDER_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    out_path = tmp_path / "tune.json"
    res = CliRunner().invoke(
        deck_tune_main,
        [
            deck,
            hyd,
            "--bulk-data",
            _bulk(tmp_path),
            "--bracket",
            "2",
            "--output",
            str(out_path),
        ],
    )
    assert res.exit_code == 0, res.output
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["scorecard"]["bracket"]["target_bracket"] == 2
    assert "pass" in out["scorecard"]["bracket"]
