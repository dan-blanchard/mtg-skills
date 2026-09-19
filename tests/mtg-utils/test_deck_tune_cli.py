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
COMPETITIVE_BRAWL_DECK = {
    "format": "competitive_brawl",
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


def test_exclude_reaches_the_tuner(tmp_path, monkeypatch):
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", COMMANDER_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, "--bulk-data", hyd, "--exclude", "Sol Ring", "--exclude", "Skullclamp"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].exclude == frozenset({"Sol Ring", "Skullclamp"})


def test_accepts_constructed_format(tmp_path, monkeypatch):
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", CONSTRUCTED_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(deck_tune_main, [deck, "--bulk-data", hyd])
    assert res.exit_code == 0, res.output
    assert captured["hd"].format.name == "modern"


def test_bracket_on_a_constructed_deck_is_noted_not_fatal(tmp_path, monkeypatch):
    _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", CONSTRUCTED_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, "--bulk-data", hyd, "--bracket", "2"]
    )
    assert res.exit_code == 0, res.output
    assert "Commander brackets do not apply" in res.output


def test_accepts_competitive_brawl_as_commander_family(tmp_path, monkeypatch):
    # Competitive Brawl is a Commander-family format (a command zone, 100-card
    # singleton); the gate must admit it, and it is Arena-only → digital medium.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", COMPETITIVE_BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(deck_tune_main, [deck, "--bulk-data", hyd])
    assert res.exit_code == 0, res.output
    assert captured["params"].medium is None  # the Format resolves it, in tune()


def test_medium_the_format_cannot_honour_is_noted_not_fatal(tmp_path, monkeypatch):
    # ``Format.resolve_medium`` ignores an override the format cannot honour (the
    # same rule deck-forge's session applies); the CLI says so on stderr and runs.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", COMPETITIVE_BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, "--bulk-data", hyd, "--medium", "paper"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "paper"  # passed through; tune() resolves it
    assert "competitive_brawl is not played in 'paper'" in res.output


def test_diagnoses_a_commander_deck(tmp_path):
    deck = _write(tmp_path, "deck.json", COMMANDER_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    out_path = tmp_path / "tune.json"
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, "--bulk-data", hyd, "--output", str(out_path)],
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
            "--bulk-data",
            hyd,
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
    """Replace deck_tune's `tune` with a spy that records the deck and the
    TuneParams it was called with. The CLI is transport only — it passes the raw
    ``--medium`` / ``--paper-only`` flags and tune() asks the Format for the rest —
    so the tests read the EFFECTIVE values the way tune() does (:func:`_medium` /
    :func:`_paper_only`)."""
    import mtg_utils.deck_tune as deck_tune_mod

    captured: dict = {}

    def spy(_hd, *, params, **_kw):
        captured["hd"] = _hd
        captured["params"] = params
        return _STUB_RESULT

    monkeypatch.setattr(deck_tune_mod, "tune", spy)
    return captured


# What a medium MEANS (the Game, the currency, the candidate pool) is tune()'s to
# resolve through the Format — pinned in test_tuner_tune.py / test_formats.py. The CLI
# is transport: these tests pin only what it hands over, and what it tells the user.


def test_an_inferred_medium_is_announced(tmp_path, monkeypatch):
    # A format played in two media says which one was inferred, so a paper table
    # isn't silently tuned as Arena; a single-medium format says nothing.
    _spy_tune(monkeypatch)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    brawl = CliRunner().invoke(
        deck_tune_main, [_write(tmp_path, "b.json", BRAWL_DECK), "--bulk-data", hyd]
    )
    assert brawl.exit_code == 0, brawl.output
    assert "--medium not given" in brawl.output
    assert "'digital'" in brawl.output
    commander = CliRunner().invoke(
        deck_tune_main, [_write(tmp_path, "c.json", COMMANDER_DECK), "--bulk-data", hyd]
    )
    assert commander.exit_code == 0, commander.output
    assert "--medium not given" not in commander.output


def test_medium_explicit_override_beats_the_inferred_default(tmp_path, monkeypatch):
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, "--bulk-data", hyd, "--medium", "paper"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].medium == "paper"
    assert captured["params"].paper_only is None  # no flag → follows the medium


def test_paper_only_explicit_flag_beats_medium_inference(tmp_path, monkeypatch):
    # A digital-medium deck that explicitly asks to stay paper-only-search
    # keeps that override rather than the medium-derived default.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main,
        [deck, "--bulk-data", hyd, "--paper-only"],
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].paper_only is True


def test_cli_passes_flags_through_untouched(tmp_path, monkeypatch):
    # Transport only: no flag → no override, so tune() follows the medium.
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(deck_tune_main, [deck, "--bulk-data", hyd])
    assert res.exit_code == 0, res.output
    assert captured["params"].medium is None
    assert captured["params"].paper_only is None


def test_wildcards_option_parses_a_per_rarity_budget(tmp_path, monkeypatch):
    captured = _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, "--bulk-data", hyd, "--wildcards", "rare=2,common=8"]
    )
    assert res.exit_code == 0, res.output
    assert captured["params"].wildcard_budget == {"rare": 2, "common": 8}


def test_wildcards_option_rejects_an_unknown_rarity(tmp_path, monkeypatch):
    _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, "--bulk-data", hyd, "--wildcards", "epic=1"]
    )
    assert res.exit_code != 0
    assert "epic=1" in res.output


def test_usd_budget_on_a_digital_build_is_noted(tmp_path, monkeypatch):
    # A digital build spends wildcards; --budget would silently do nothing.
    _spy_tune(monkeypatch)
    deck = _write(tmp_path, "deck.json", BRAWL_DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(
        deck_tune_main, [deck, "--bulk-data", hyd, "--budget", "5"]
    )
    assert res.exit_code == 0, res.output
    assert "--wildcards" in res.output


def test_a_sealed_deck_tunes_over_its_pool_never_the_bulk(tmp_path, monkeypatch):
    # The CLI hands the tuner the opened pool's own search (ADR-0055).
    import mtg_utils.deck_tune as deck_tune_mod

    captured: dict = {}

    def spy(_hd, *, search_fn, pool=None, **_kw):
        captured["search_fn"] = search_fn
        captured["pool"] = pool
        return _STUB_RESULT

    monkeypatch.setattr(deck_tune_mod, "tune", spy)
    deck = _write(
        tmp_path,
        "deck.json",
        {
            "format": "sealed",
            "commanders": [],
            "cards": [{"name": "Mountain", "quantity": 17}],
            "sideboard": [],
            "pool": [{"name": "Krenko, Mob Boss", "quantity": 2}],
        },
    )
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(deck_tune_main, [deck, "--bulk-data", hyd])
    assert res.exit_code == 0, res.output
    assert captured["pool"] == {"Krenko, Mob Boss": 2}
    found = captured["search_fn"](card_type="Creature", paper_only=True)
    assert [c["name"] for c in found] == ["Krenko, Mob Boss"]
