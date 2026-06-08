"""Tests for the deck-forge card index (build_by_name).

It folds lookups (NFKD) via the shared name-index core, so search's proper-case names
and any case/diacritic spelling resolve to the same record — the original Jyoti
add-validation bug (proper-case search output vs a lowercased index) is moot under
folding. The stored record keeps its real proper-case name for display.
"""

from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.production import build_by_name, resume_or_new


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


def test_folds_lookups_and_keeps_proper_case_record():
    # Folding (not proper-case keying) is what keeps a searchable card addable now:
    # the proper-case name AND a lowercased spelling both resolve, and the stored
    # record keeps its real name for display.
    cards = [
        {"name": "Jyoti, Moag Ancient", "layout": "normal", "prices": {"usd": "5"}}
    ]
    idx = build_by_name(cards)
    assert idx.get("Jyoti, Moag Ancient")["name"] == "Jyoti, Moag Ancient"
    assert idx.get("jyoti, moag ancient")["name"] == "Jyoti, Moag Ancient"


def test_tokens_and_art_series_skipped():
    cards = [
        {"name": "Real Card", "layout": "normal", "prices": {}},
        {"name": "Soldier", "layout": "token", "prices": {}},
        {"name": "Showcase", "layout": "art_series", "prices": {}},
        {"name": "Memo", "layout": "normal", "set_type": "memorabilia", "prices": {}},
    ]
    idx = build_by_name(cards)
    assert "Real Card" in idx
    assert "Soldier" not in idx
    assert "Showcase" not in idx
    assert "Memo" not in idx


def test_dedupes_to_cheapest_printing():
    cards = [
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "3.00"}},
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "1.00"}},
        {"name": "Sol Ring", "layout": "normal", "prices": {"usd": "9.00"}},
    ]
    assert build_by_name(cards)["Sol Ring"]["prices"]["usd"] == "1.00"
