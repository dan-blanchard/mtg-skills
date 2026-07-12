"""Smoke tests for the deck-forge-derived CLIs deck-wizard reuses (D): deck-signals,
slot-budgets, deck-rank. Each is a thin wrapper over a pure _deck_forge function, so
these check the CLI plumbing (parse deck + hydrated JSON, render) on real card props."""

import json

from click.testing import CliRunner

from mtg_utils import testkit
from mtg_utils.deck_rank import main as deck_rank_main
from mtg_utils.deck_signals import main as deck_signals_main
from mtg_utils.slot_budgets import main as slot_budgets_main

# Seed the crosswalk trees memo from the committed snapshot (CI-safe, no phase
# cache / network) so these hand-rolled CLI fixtures below — real card oracle
# text, with the matching real oracle_id threaded in — resolve through the
# SAME production extract_signals_hybrid path a real deck-forge session uses
# (ADR-0039 task #80 step 6: extract_signals_hybrid no longer falls back to a
# regex answer when a fixture's oracle_id has no resolvable Card IR tree — the
# ONLY way to prove the CLI plumbing sees a real signal is a real, resolvable
# tree). The return values are unused; the call's side effect
# (``testkit._seed_trees``) is what matters, and it registers each name for
# ``build-card-snapshot``'s AST scan.
testkit.test_signals("Krenko, Mob Boss")
testkit.test_signals("Mountain")
testkit.test_signals("Goblin Chieftain")

KRENKO = {
    "name": "Krenko, Mob Boss",
    "oracle_id": "68418069-f615-40ef-ae0d-764192acae00",
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
    "oracle_id": "a3fb7228-e76b-4e96-a40e-20b5fed75685",
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
    "oracle_id": "368b4052-174e-4458-a6e6-eaf8093aa0fe",
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
