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
BRAWL_DECK = {
    "format": "brawl",
    "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
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


_STUB_RESULT = {
    "scorecard": {},
    "swaps": [],
    "spent": 0.0,
    "wildcards_spent": None,
    "swaps_note": None,
    "commander_suggestions": None,
}


def _spy_tune(monkeypatch):
    """Replace deck_tune's `tune` with a spy that records the TuneParams it
    was called with, so the CLI's medium/paper_only inference can be
    inspected without needing a real bulk index."""
    import mtg_utils.deck_tune as deck_tune_mod

    captured: dict = {}

    def spy(_hd, *, params, **_kw):
        captured["params"] = params
        return _STUB_RESULT

    monkeypatch.setattr(deck_tune_mod, "tune", spy)
    return captured


def test_medium_defaults_paper_for_commander(tmp_path, monkeypatch):
    # ADR-0040 §4 fix (Fix 3): the CLI never threaded `medium` at all before
    # this fix — TuneParams always ran the "paper" default regardless of
    # format. Commander is paper-only, so paper stays the inferred default.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", COMMANDER_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, hyd, "--bulk-data", _bulk(tmp_path)]
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "paper"
    assert captured["params"].paper_only is True


def test_medium_defaults_digital_for_brawl(tmp_path, monkeypatch):
    # Historic Brawl / Brawl default to digital (Arena), same as deck-forge's
    # DeckSession — the ADR-0040 motivating benchmark was a Historic Brawl
    # deck, so this is the path that must actually engage the fix.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, hyd, "--bulk-data", _bulk(tmp_path)]
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "digital"
    # paper_only threads consistently with the inferred medium.
    assert captured["params"].paper_only is False


def test_medium_explicit_override_beats_the_inferred_default(tmp_path, monkeypatch):
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, hyd, "--bulk-data", _bulk(tmp_path), "--medium", "paper"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "paper"
    assert captured["params"].paper_only is True


def test_paper_only_explicit_flag_beats_medium_inference(tmp_path, monkeypatch):
    # A digital-medium deck that explicitly asks to stay paper-only-search
    # keeps that override rather than the medium-derived default.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, hyd, "--bulk-data", _bulk(tmp_path), "--paper-only"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "digital"
    assert captured["params"].paper_only is True
