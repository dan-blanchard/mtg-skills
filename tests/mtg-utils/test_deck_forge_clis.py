"""Smoke tests for the deck-forge-derived CLIs deck-wizard reuses (D): deck-signals,
slot-budgets, deck-rank. Each is a thin wrapper over a pure _deck_forge function, so
these check the CLI plumbing (parse deck + hydrated JSON, render) on real cards."""

import json

from click.testing import CliRunner

from mtg_utils import testkit
from mtg_utils.deck_rank import main as deck_rank_main
from mtg_utils.deck_signals import main as deck_signals_main
from mtg_utils.slot_budgets import main as slot_budgets_main

# Real cards from the testkit snapshot (ADR-0056), with only their per-printing
# prices overlaid. ``test_signals`` seeds the crosswalk trees memo from the
# committed snapshot (CI-safe, no phase cache / network), so the CLI resolves each
# card through the SAME production extract_signals path a real deck-forge session
# uses; its return value is unused.
testkit.test_signals("Krenko, Mob Boss")
testkit.test_signals("Mountain")
testkit.test_signals("Goblin Chieftain")

KRENKO = {**testkit.test_card("Krenko, Mob Boss"), "prices": {"usd": "2.00"}}
MOUNTAIN = {**testkit.test_card("Mountain"), "prices": {"usd": "0.10"}}
CHIEFTAIN = {**testkit.test_card("Goblin Chieftain"), "prices": {"usd": "1.00"}}

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
    res = CliRunner().invoke(deck_signals_main, [deck, "--bulk-data", hyd, "--json"])
    assert res.exit_code == 0, res.output
    rows = json.loads(res.stdout)
    assert any(r["subject"] == "Goblin" and r["actionable"] for r in rows)


def test_slot_budgets_counts_lands(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(slot_budgets_main, [deck, "--bulk-data", hyd, "--json"])
    assert res.exit_code == 0, res.output
    budgets = json.loads(res.stdout)
    assert budgets["lands"]["current"] == 10


def test_slot_budgets_serves_the_familys_rows_with_labels(tmp_path):
    modern = {
        "format": "modern",
        "commanders": [],
        "cards": [{"name": "Mountain", "quantity": 20}],
    }
    deck = _write(tmp_path, "deck.json", modern)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    res = CliRunner().invoke(slot_budgets_main, [deck, "--bulk-data", hyd, "--json"])
    assert res.exit_code == 0, res.output
    budgets = json.loads(res.stdout)
    assert list(budgets) == ["lands", "interaction", "card_draw", "creatures"]
    assert budgets["creatures"]["label"] == "Creatures (type line)"
    assert budgets["creatures"]["advisory"] is True
    text = CliRunner().invoke(slot_budgets_main, [deck, "--bulk-data", hyd])
    assert "Interaction (incl. sweepers)" in text.output


def test_deck_rank_orders_a_goblin_payoff_by_synergy(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    cands = _write(tmp_path, "cands.json", [CHIEFTAIN])
    res = CliRunner().invoke(
        deck_rank_main, [deck, cands, "--bulk-data", hyd, "--json"]
    )
    assert res.exit_code == 0, res.output
    ranked = json.loads(res.stdout)
    assert ranked
    assert ranked[0]["name"] == "Goblin Chieftain"
    assert ranked[0]["synergy_fit"] >= 1  # serves the Goblin lane


def test_deck_rank_rejects_a_bare_name_list(tmp_path):
    deck = _write(tmp_path, "deck.json", DECK)
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    cands = _write(tmp_path, "cands.json", ["Goblin Chieftain"])
    res = CliRunner().invoke(deck_rank_main, [deck, cands, "--bulk-data", hyd])
    assert res.exit_code != 0  # records required, not bare names


def _cache_meta(tmp_path, monkeypatch, *cards: str) -> None:
    """A cached Historic Brawl meta (ADR-0059) whose one Krenko archetype list runs
    ``cards``."""
    from mtg_utils._arena_meta import meta as m
    from mtg_utils._arena_meta import untapped

    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "cache"))
    plat = {"platinum": m.Record(400, 220)}
    snap = m.Snapshot(
        event="Play_Brawl_Historic",
        period={"id": 763, "description": "Set Release", "start": "2026-09-29"},
        fetched_at="2026-10-05T12:00:00+00:00",
        archetypes={1: m.MetaArchetype(1, "Mono-Red / Krenko, Mob Boss", "R", plat)},
        decks=(
            m.MetaDeck(
                1,
                ("Krenko, Mob Boss",),
                (("Mountain", 30), *((c, 1) for c in cards)),
                (),
                plat,
            ),
        ),
        lands=frozenset({"Mountain"}),
    )
    path = untapped.meta_dir() / "Play_Brawl_Historic.current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(snap.to_json()))


def test_deck_rank_breaks_synergy_ties_by_meta_share(
    tmp_path, monkeypatch, meta_tiebreak_pair
):
    staple, rogue = meta_tiebreak_pair
    _cache_meta(tmp_path, monkeypatch, "Test Meta Staple")
    # Historic Brawl defaults to Arena (digital); the same deck at a paper table
    # reads no meta.
    deck = _write(tmp_path, "deck.json", {**DECK, "format": "historic_brawl"})
    hyd = _write(tmp_path, "hyd.json", HYDRATED)
    cands = _write(tmp_path, "cands.json", [rogue, staple])

    def ranked(*flags: str) -> list[tuple[str, float | None]]:
        res = CliRunner().invoke(
            deck_rank_main, [deck, cands, "--bulk-data", hyd, "--json", *flags]
        )
        assert res.exit_code == 0, res.output
        return [(r["name"], r.get("meta_share")) for r in json.loads(res.stdout)]

    assert ranked() == [("Test Meta Staple", 1.0), ("Test Meta Rogue", 0.0)]
    # Off, or a paper build: synergy, price, curve, as before.
    without = [("Test Meta Rogue", None), ("Test Meta Staple", None)]
    assert ranked("--meta", "off") == without
    assert ranked("--medium", "paper") == without
