from __future__ import annotations

from mtg_utils.lgs_search import relax_prefs


def test_relax_prefs_drops_constraints():
    base = {"max_condition": "lp", "allow_foil": False, "prefer_set": "C21"}
    relaxed = relax_prefs(base)
    assert relaxed["max_condition"] == "any"
    assert relaxed["allow_foil"] is True
    assert relaxed["prefer_set"] is None


def test_relax_prefs_does_not_mutate_input():
    base = {"max_condition": "lp", "allow_foil": False, "prefer_set": "C21"}
    relax_prefs(base)
    assert base == {"max_condition": "lp", "allow_foil": False, "prefer_set": "C21"}
