"""Tests for the hub's production wiring (resume_or_new). The card index it serves
is the ``CardPool``'s (ADR-0046), tested in tests/mtg-utils/test_card_pool.py."""

from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.production import resume_or_new


def test_resume_or_new_resumes_latest(tmp_path):
    store = BuildStore(tmp_path)
    store.save(
        "b1",
        "My Deck",
        {
            "format": "commander",
            "commanders": [{"name": "X", "quantity": 1}],
            "cards": [],
            "sideboard": [],
        },
    )
    session, build_id, name = resume_or_new(store, "commander")
    assert build_id == "b1"
    assert name == "My Deck"
    assert session.to_deck_dict()["commanders"] == [{"name": "X", "quantity": 1}]


def test_resume_or_new_starts_fresh_when_empty(tmp_path):
    session, _build_id, name = resume_or_new(BuildStore(tmp_path), "commander")
    assert name == "Untitled"
    assert session.to_deck_dict()["cards"] == []


def test_combos_are_memoized_per_deck_content(monkeypatch):
    """A Tune re-run on an unchanged deck (a rejected add) must not be a second live
    Commander Spellbook call."""
    from mtg_utils import combo_search
    from mtg_utils._deck_forge import production

    calls: list = []
    monkeypatch.setattr(
        combo_search, "combo_search", lambda hd: calls.append(hd) or {"combos": []}
    )
    monkeypatch.setattr(production, "_COMBO_MEMO", {})
    deck = {"format": "commander", "commanders": [], "cards": [{"name": "Opt"}]}
    by_name = {"Opt": {"name": "Opt", "type_line": "Instant"}}
    assert production._combos(deck, by_name) == {"combos": []}
    assert production._combos(dict(deck), by_name) == {"combos": []}
    assert len(calls) == 1
    other = {**deck, "cards": [{"name": "Opt"}, {"name": "Opt"}]}
    production._combos(other, by_name)
    assert len(calls) == 2
