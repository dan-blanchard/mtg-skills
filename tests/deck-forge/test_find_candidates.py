"""engine.find_candidates — the unified Find pipeline as a free function over ForgeState
(ADR-0021, completing the candidate-pipeline extraction ADR-0013 parked). These exercise
the SELECTION surface directly (no HTTP): the focus/filter/idle branch, in-deck
stripping, focused-avenue crediting, staples resolution, paper_only propagation, and the
CandidatePage paging math. The HTTP serialization (projection / owned / 503) is pinned in
test_find.py.

Several of these migrated here from the now-deleted /api/search, /api/packages, and
/api/explore route tests (ADR-0015 superseded those endpoints with /api/find).
"""

import re

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.state import DeckSession, ForgeState

# A tiny searchable catalog. "Both" serves both the sacrifice and token lanes.
CATALOG = [
    {
        "name": "Sac Outlet",
        "oracle_text": "Sacrifice a creature: draw a card.",
        "type_line": "Artifact",
        "cmc": 2.0,
        "color_identity": ["B"],
        "prices": {"usd": "1.00"},
    },
    {
        "name": "Token Maker",
        "oracle_text": "Create a 1/1 green Saproling creature token.",
        "type_line": "Enchantment",
        "cmc": 3.0,
        "color_identity": ["G"],
        "prices": {"usd": "2.00"},
    },
    {
        "name": "Both",
        "oracle_text": "Sacrifice a creature: create two 1/1 tokens.",
        "type_line": "Creature — Horror",
        "cmc": 4.0,
        "color_identity": ["B", "G"],
        "prices": {"usd": "3.00"},
    },
]


def _recording_search(catalog):
    """A fake search_fn that filters the catalog and records the kwargs each call got
    (so a test can assert e.g. paper_only propagation)."""
    calls: list[dict] = []

    def fake(oracle=None, card_type=None, name=None, limit=100, offset=0, **kw):
        calls.append({"oracle": oracle, "card_type": card_type, "name": name, **kw})
        res = catalog
        if oracle:
            rx = re.compile(oracle, re.IGNORECASE)
            res = [c for c in res if rx.search(c.get("oracle_text", ""))]
        if card_type:
            res = [c for c in res if card_type.lower() in c["type_line"].lower()]
        if name:
            res = [c for c in res if name.lower() in c["name"].lower()]
        return res[offset : offset + limit]

    fake.calls = calls
    return fake


def _avenue(aid, label, oracle, **search):
    return {
        "id": aid,
        "label": label,
        "description": "",
        "scope": "",
        "source": "agent",
        "search": {"oracle": oracle, **search},
    }


def _state(*, search_fn=None, focused=(), agent_avenues=(), session=None):
    state = ForgeState(
        by_name={},
        search_fn=search_fn or _recording_search(CATALOG),
        session=session or DeckSession("commander"),
        bulk_available=True,
    )
    state.agent_avenues = list(agent_avenues)
    state.focused_avenue_ids = set(focused)
    return state


def _names(page):
    return [row["card"]["name"] for row in page.rows]


# ── branch: focused avenues ───────────────────────────────────────────────────


def test_focused_avenues_or_merge_and_rank_by_fit():
    sac = _avenue("agent:1", "Sacrifice", "sacrifice")
    tok = _avenue("agent:2", "Tokens", "create.*token")
    state = _state(focused=("agent:1", "agent:2"), agent_avenues=(sac, tok))
    page = engine.find_candidates(state, engine.FindParams())
    assert set(_names(page)) == {"Sac Outlet", "Token Maker", "Both"}
    assert _names(page)[0] == "Both"  # serves both focused lanes → ranks first
    assert page.rows[0]["score"]["synergy_fit"] == 2
    assert page.total == 3


def test_strips_cards_already_in_deck():
    """A focused-lane candidate already in the deck is excluded (was pinned via the
    deleted /api/packages and /api/explore in-deck tests)."""
    sac = _avenue("agent:1", "Sacrifice", "sacrifice")
    session = DeckSession("commander")
    session.add("Sac Outlet", 1)  # already in the deck
    state = _state(focused=("agent:1",), agent_avenues=(sac,), session=session)
    page = engine.find_candidates(state, engine.FindParams())
    assert "Sac Outlet" not in _names(page)
    assert "Both" in _names(page)  # still surfaced (serves the sacrifice lane)


def test_focused_avenue_credits_its_own_candidates():
    """A card surfaced BY the focused lane scores for it (synergy_fit >= 1 and the
    avenue label is in `served`) — otherwise it reads as an irrelevant zero-fit hit.
    Migrated from the deleted test_explore_credits_candidates_for_the_explored_avenue."""
    manland = {
        "name": "Treetop Village",
        "type_line": "Land",
        "cmc": 0.0,
        "color_identity": ["G"],
        "oracle_text": "Treetop Village becomes a 3/3 green Ape creature until end of turn.",
        "prices": {"usd": "0.50"},
    }
    av = _avenue(
        "agent:1", "Creature-lands", "becomes a [^.]*creature", card_type="Land"
    )
    state = _state(
        search_fn=_recording_search([manland]),
        focused=("agent:1",),
        agent_avenues=(av,),
    )
    page = engine.find_candidates(state, engine.FindParams())
    top = page.rows[0]["score"]
    assert top["synergy_fit"] >= 1
    assert "Creature-lands" in top["served"]


def test_focus_with_user_filter_refines_the_merged_pool():
    sac = _avenue("agent:1", "Sacrifice", "sacrifice")
    tok = _avenue("agent:2", "Tokens", "create.*token")
    state = _state(focused=("agent:1", "agent:2"), agent_avenues=(sac, tok))
    page = engine.find_candidates(state, engine.FindParams(type="Creature"))
    assert _names(page) == ["Both"]  # type=Creature AND-refines the OR-merged pool


# ── branch: filter-only / idle ────────────────────────────────────────────────


def test_no_focus_with_filter_is_manual_search():
    state = _state()
    page = engine.find_candidates(state, engine.FindParams(name="Token"))
    assert _names(page) == ["Token Maker"]


def test_no_focus_no_filter_is_idle_empty_page():
    state = _state()
    page = engine.find_candidates(state, engine.FindParams())
    assert page.rows == []
    assert page.total == 0
    assert page.has_more is False


def test_paper_only_propagates_to_search_for_commander():
    """commander is paper-only, so the filter-only branch must pass paper_only=True to
    search_fn. Migrated from the deleted test_paper_format_search_sets_paper_only."""
    search = _recording_search(CATALOG)
    state = _state(search_fn=search)
    engine.find_candidates(
        state, engine.FindParams(type="Creature", format="commander")
    )
    assert search.calls[-1]["paper_only"] is True


# ── paging math over CandidatePage ────────────────────────────────────────────


def test_slice_paging_windows_the_ranked_pool():
    """Pages a fixed page size through the stable ranked pool. Migrated from the deleted
    /api/explore and /api/search pagination tests."""
    cards = [
        {
            "name": f"C{i}",
            "type_line": "Creature — Elf",
            "cmc": 2.0,
            "color_identity": ["G"],
            "oracle_text": "",
            "prices": {"usd": "0.10"},
        }
        for i in range(20)
    ]
    state = _state(search_fn=_recording_search(cards))
    first = engine.find_candidates(
        state, engine.FindParams(name="C", limit=12, offset=0)
    )
    assert len(first.rows) == 12
    assert first.total == 20
    assert first.has_more is True
    second = engine.find_candidates(
        state, engine.FindParams(name="C", limit=12, offset=12)
    )
    assert len(second.rows) == 8
    assert second.has_more is False


# ── staples lane (migrated from the deleted TestStaplesExploreEndpoint) ────────

SOL_RING = {
    "name": "Sol Ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "color_identity": [],
    "oracle_text": "{T}: Add {C}{C}.",
    "prices": {"usd": "2.00"},
    "legalities": {"commander": "legal"},
}
CULTIVATE = {
    "name": "Cultivate",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "color_identity": ["G"],
    "oracle_text": "Search your library for up to two basic land cards.",
    "prices": {"usd": "0.25"},
    "legalities": {"commander": "legal"},
}
COUNTERSPELL = {
    "name": "Counterspell",
    "type_line": "Instant",
    "cmc": 2.0,
    "color_identity": ["U"],
    "oracle_text": "Counter target spell.",
    "prices": {"usd": "1.00"},
    "legalities": {"commander": "legal"},
}
GRUUL_COMMANDER = {
    "name": "Test Gruul Commander",
    "type_line": "Legendary Creature — Beast",
    "cmc": 4.0,
    "color_identity": ["R", "G"],
    "oracle_text": "",
    "legalities": {"commander": "legal"},
}
_STAPLES_INDEX = {
    c["name"]: c for c in (GRUUL_COMMANDER, SOL_RING, CULTIVATE, COUNTERSPELL)
}


def _focused_staples_state():
    """A Gruul deck with the always-present Staples avenue FOCUSED, and a poisoned
    search_fn: if the staples lane wrongly fell through to search_fn the test would see
    'WRONG PATH' instead of the curated names."""
    session = DeckSession("commander")
    session.add("Test Gruul Commander", 1, zone="commanders")
    state = ForgeState(
        by_name=_STAPLES_INDEX,
        search_fn=lambda **_: [{"name": "WRONG PATH", "type_line": "Land"}],
        session=session,
        bulk_available=True,
    )
    staples_av = next(
        a
        for a in engine.avenues(state, engine.hydrate(state).records)
        if a["label"] == "Staples / good stuff"
    )
    state.focused_avenue_ids = {staples_av["id"]}
    return state


def test_focused_staples_lane_resolves_curated_pool_not_search_fn():
    page = engine.find_candidates(_focused_staples_state(), engine.FindParams())
    names = {row["card"]["name"] for row in page.rows}
    assert "Sol Ring" in names  # colorless → fits the Gruul identity
    assert "Cultivate" in names  # green → in identity
    assert "Counterspell" not in names  # blue → out of identity
    assert "WRONG PATH" not in names  # never hit search_fn


def test_focused_staples_are_credited_on_theme():
    page = engine.find_candidates(_focused_staples_state(), engine.FindParams())
    sol = next(row for row in page.rows if row["card"]["name"] == "Sol Ring")
    assert sol["score"]["synergy_fit"] >= 1  # credited by the avenue's name serve
