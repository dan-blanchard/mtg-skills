"""Tests for the hub's production wiring (resume_or_new). The card index it serves
is the ``CardPool``'s (ADR-0046), tested in tests/mtg-utils/test_card_pool.py."""

from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.production import resume_or_new
from mtg_utils.testkit import test_card


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
    by_name = {"Opt": test_card("Opt")}
    assert production._combos(deck, by_name) == {"combos": []}
    assert production._combos(dict(deck), by_name) == {"combos": []}
    assert len(calls) == 1
    other = {**deck, "cards": [{"name": "Opt"}, {"name": "Opt"}]}
    production._combos(other, by_name)
    assert len(calls) == 2


def test_warm_at_launch_installs_the_reporter_and_chains_index_then_discovery(
    monkeypatch, tmp_path
):
    from mtg_utils import theme_presets
    from mtg_utils._analysis import signals_index
    from mtg_utils._deck_forge import discovery, production
    from mtg_utils._deck_forge.state import DeckSession, ForgeState

    order: list = []
    monkeypatch.setattr(
        theme_presets, "seed_signal_key_index", lambda p: order.append(("seed", p))
    )
    monkeypatch.setattr(
        discovery, "warm", lambda _st, slot, fmt=None: order.append(("warm", slot, fmt))
    )
    bulk = tmp_path / "bulk.json"
    bulk.write_text("[]", encoding="utf-8")
    state = ForgeState(
        by_name={},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_available=True,
        bulk_path=bulk,
    )

    def reporter(*_args: object) -> None:
        return None

    try:
        thread = production.warm_at_launch(state, reporter)
        assert thread is not None
        thread.join(timeout=5)
    finally:
        signals_index.set_progress_hook(None)
    assert state.report_busy is reporter
    assert order == [("seed", bulk), ("warm", "paper", "commander")]
