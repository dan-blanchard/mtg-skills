"""The alternate-commander compare (``_tuner.compare_commanders``): every command
zone the deck can field — the format's eligible singles and the legal partner
pairs — tuned and ranked. Real cards from the testkit snapshot (ADR-0056)."""

from mtg_utils import testkit
from mtg_utils._tuner import TuneParams, tune
from mtg_utils._tuner.compare_commanders import (
    candidate_command_zones,
    compare_commanders,
    issue_load,
)
from mtg_utils.hydrated_deck import HydratedDeck

NAMES = (
    "Krenko, Mob Boss",
    "Krenko, Tin Street Kingpin",  # a second eligible legend in the 99
    "Goblin Rabblemaster",
    "Goblin Warchief",
    "Gloom Pangolin",
    "Mountain",
)
for _n in NAMES:
    testkit.test_card_ir(_n)  # seed the trees memo (CI-safe)
_INDEX = {n: testkit.test_card(n) for n in NAMES}


def _fake_search(**_kw):
    return []


def _hd(commanders=("Krenko, Mob Boss",), cards=NAMES[1:]):
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": n, "quantity": 1} for n in commanders],
        "cards": [{"name": n, "quantity": 1} for n in cards],
    }
    return HydratedDeck.from_parsed(deck, by_name=_INDEX)


def test_candidate_zones_are_the_eligible_singles_current_first():
    zones = candidate_command_zones(_hd())
    assert zones[0] == ("Krenko, Mob Boss",)
    assert ("Krenko, Tin Street Kingpin",) in zones
    # A nonlegendary Goblin and a land lead nothing.
    assert all("Goblin Rabblemaster" not in z and "Mountain" not in z for z in zones)
    assert len(zones) == 2


def test_partner_pairs_are_candidate_zones():
    testkit.test_card_ir("Amy Pond")
    testkit.test_card_ir("Rory Williams")
    index = {
        **_INDEX,
        "Amy Pond": testkit.test_card("Amy Pond"),
        "Rory Williams": testkit.test_card("Rory Williams"),
    }
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
        "cards": [
            {"name": n, "quantity": 1}
            for n in ("Amy Pond", "Rory Williams", "Mountain")
        ],
    }
    zones = candidate_command_zones(HydratedDeck.from_parsed(deck, by_name=index))
    # Partner with [name] (CR 702.124j): the two pair, and only with each other.
    assert ("Amy Pond", "Rory Williams") in zones
    assert ("Amy Pond",) in zones
    assert ("Krenko, Mob Boss", "Amy Pond") not in zones


def test_compare_ranks_every_zone_and_marks_the_current_one():
    rows = compare_commanders(
        _hd(),
        tune_fn=tune,
        search_fn=_fake_search,
        params=TuneParams(max_swaps=0),
    )
    assert [r["rank"] for r in rows] == [1, 2]
    zones = {tuple(r["commanders"]) for r in rows}
    assert zones == {("Krenko, Mob Boss",), ("Krenko, Tin Street Kingpin",)}
    assert sum(r["current"] for r in rows) == 1
    # Ranked by fit (desc) then issue load (asc): the order the keys give.
    keys = [(-r["fit"], r["issues"]) for r in rows]
    assert keys == sorted(keys)
    for r in rows:
        assert 0.0 <= r["fit"] <= 1.0
        assert r["issues"] >= 0
        assert isinstance(r["swaps"], list)


def test_issue_load_sums_severities_with_one_for_an_unweighted_issue():
    sc = {"top_issues": [{"severity": 4}, {"severity": 2}, {"kind": "x"}]}
    assert issue_load(sc) == 7
    assert issue_load({}) == 0
