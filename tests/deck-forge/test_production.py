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
