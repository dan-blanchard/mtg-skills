"""Smoke tests for the deck-forge-derived CLIs deck-wizard reuses (D): deck-signals,
slot-budgets, deck-rank. Each is a thin wrapper over a pure _deck_forge function, so
these check the CLI plumbing (parse deck + hydrated JSON, render) on real card props."""

import json

from click.testing import CliRunner

from mtg_utils.deck_rank import main as deck_rank_main
from mtg_utils.deck_signals import main as deck_signals_main
from mtg_utils.slot_budgets import main as slot_budgets_main

KRENKO = {
    "name": "Krenko, Mob Boss",
    "type_line": "Legendary Creature — Goblin Warrior",
    "cmc": 4.0,
    "mana_cost": "{2}{R}{R}",
    "color_identity": ["R"],
    "oracle_text": (
        "{T}: Create a number of 1/1 red Goblin creature tokens equal to the number "
        "of Goblins you control."
    ),
    "keywords": [],
    "power": "3",
    "toughness": "3",
    "prices": {"usd": "2.00"},
    "legalities": {"commander": "legal"},
}
MOUNTAIN = {
    "name": "Mountain",
    "type_line": "Basic Land — Mountain",
    "cmc": 0.0,
    "mana_cost": "",
    "color_identity": ["R"],
    "oracle_text": "",
    "keywords": [],
    "prices": {"usd": "0.10"},
    "produced_mana": ["R"],
    "legalities": {"commander": "legal"},
}
CHIEFTAIN = {
    "name": "Goblin Chieftain",
    "type_line": "Creature — Goblin",
    "cmc": 3.0,
    "mana_cost": "{1}{R}{R}",
    "color_identity": ["R"],
    "oracle_text": (
        "Haste\nOther Goblin creatures you control get +1/+1 and have haste."
    ),
    "keywords": ["Haste"],
    "power": "2",
    "toughness": "2",
    "prices": {"usd": "1.00"},
    "legalities": {"commander": "legal"},
}

DECK = {
    "format": "commander",
    "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
    "cards": [{"name": "Mountain", "quantity": 10}],
    "sideboard": [],
}
HYDRATED = [KRENKO, MOUNTAIN]


def _write(tmp_path, name, obj):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def test_deck_signals_surfaces_the_commander_tribe(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(deck_signals_main, [deck, hyd, "--json"])
    assert res.exit_code == 0, res.output
    rows = json.loads(res.stdout)
    assert any(r["subject"] == "Goblin" and r["actionable"] for r in rows)


def test_slot_budgets_counts_lands(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(slot_budgets_main, [deck, hyd, "--json"])
    assert res.exit_code == 0, res.output
    budgets = json.loads(res.stdout)
    assert budgets["lands"]["current"] == 10


def test_deck_rank_orders_a_goblin_payoff_by_synergy(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    cands = _write(tmp_path, "cands.json", [CHIEFTAIN])
    res = CliRunner().invoke(deck_rank_main, [deck, hyd, cands, "--json"])
    assert res.exit_code == 0, res.output
    ranked = json.loads(res.stdout)
    assert ranked
    assert ranked[0]["name"] == "Goblin Chieftain"
    assert ranked[0]["synergy_fit"] >= 1  # serves the Goblin lane


def test_deck_rank_rejects_a_bare_name_list(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    cands = _write(tmp_path, "cands.json", ["Goblin Chieftain"])
    res = CliRunner().invoke(deck_rank_main, [deck, hyd, cands])
    assert res.exit_code != 0  # records required, not bare names
