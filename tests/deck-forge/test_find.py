"""The unified Find surface (#5): POST /api/find is the single card-finding path that
replaces separate search + explore. With one or more focused avenues it OR-merges their
candidate pools and ranks by focused-lane fit (a card serving more focused lanes wins);
with nothing focused it's a manual search scored against everything (today's behavior);
with neither focus nor filters it returns nothing (an idle prompt, not the whole vault)."""

import re

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

# A tiny searchable catalog. "Both" serves both lanes (sacrifice AND make a token).
CATALOG = [
    {
        "name": "Sac Outlet",
        "oracle_text": "Sacrifice a creature: draw a card.",
        "type_line": "Artifact",
        "cmc": 2.0,
        "mana_cost": "{2}",
        "color_identity": ["B"],
        "prices": {"usd": "1.00"},
        "keywords": [],
    },
    {
        "name": "Token Maker",
        "oracle_text": "Create a 1/1 green Saproling creature token.",
        "type_line": "Enchantment",
        "cmc": 3.0,
        "mana_cost": "{2}{G}",
        "color_identity": ["G"],
        "prices": {"usd": "2.00"},
        "keywords": [],
    },
    {
        "name": "Both",
        "oracle_text": "Sacrifice a creature: create two 1/1 tokens.",
        "type_line": "Creature — Horror",
        "cmc": 4.0,
        "mana_cost": "{2}{B}{G}",
        "color_identity": ["B", "G"],
        "prices": {"usd": "3.00"},
        "keywords": [],
    },
]


def _fake_search(oracle=None, card_type=None, name=None, limit=100, offset=0, **_):
    res = CATALOG
    if oracle:
        rx = re.compile(oracle, re.IGNORECASE)
        res = [c for c in res if rx.search(c["oracle_text"])]
    if card_type:
        res = [c for c in res if card_type.lower() in c["type_line"].lower()]
    if name:
        res = [c for c in res if name.lower() in c["name"].lower()]
    return res[offset : offset + limit]


def _avenue(aid, label, oracle):
    return {
        "id": aid,
        "label": label,
        "description": "",
        "scope": "",
        "source": "agent",
        "search": {"oracle": oracle},
    }


def _client(*, focused=(), agent_avenues=()):
    state = ForgeState(
        by_name={},
        search_fn=_fake_search,
        session=DeckSession("commander"),
        bulk_available=True,
    )
    state.agent_avenues = list(agent_avenues)
    state.focused_avenue_ids = set(focused)
    return TestClient(build_app(state)), state


def _names(results):
    return [r["name"] for r in results]


def test_focus_or_merges_pools_and_ranks_by_focused_fit():
    sac = _avenue("agent:1", "Sacrifice", "sacrifice")
    tok = _avenue("agent:2", "Tokens", "create.*token")
    client, _ = _client(focused=("agent:1", "agent:2"), agent_avenues=(sac, tok))

    res = client.post("/api/find", json={"limit": 25}).json()["results"]
    # union of both lanes, and "Both" (serves 2 focused lanes) ranks first
    assert set(_names(res)) == {"Sac Outlet", "Token Maker", "Both"}
    assert _names(res)[0] == "Both"
    assert res[0]["score"]["synergy_fit"] == 2  # both focused lanes
    assert res[1]["score"]["synergy_fit"] == 1


def test_focus_with_user_filter_refines_the_merged_pool():
    sac = _avenue("agent:1", "Sacrifice", "sacrifice")
    tok = _avenue("agent:2", "Tokens", "create.*token")
    client, _ = _client(focused=("agent:1", "agent:2"), agent_avenues=(sac, tok))

    # type=Creature refines the OR-merged pool down to "Both" only
    res = client.post("/api/find", json={"type": "Creature", "limit": 25}).json()
    assert _names(res["results"]) == ["Both"]


def test_no_focus_with_filter_is_manual_search():
    client, _ = _client()
    res = client.post("/api/find", json={"name": "Token", "limit": 25}).json()
    assert _names(res["results"]) == ["Token Maker"]


def test_no_focus_no_filter_returns_nothing():
    client, _ = _client()
    res = client.post("/api/find", json={"limit": 25}).json()
    assert res["results"] == []
