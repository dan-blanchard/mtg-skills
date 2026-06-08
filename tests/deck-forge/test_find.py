"""The unified Find surface (#5): POST /api/find is the single card-finding path that
replaces separate search + explore. With one or more focused avenues it OR-merges their
candidate pools and ranks by focused-lane fit (a card serving more focused lanes wins);
with nothing focused it's a manual search scored against everything (today's behavior);
with neither focus nor filters it returns nothing (an idle prompt, not the whole vault)."""

import re

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
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


# ── transport-level invariants (serialization / guards / ownership) ───────────
# Migrated here from the deleted /api/search and /api/packages route tests, since
# /api/find is now the single card-finding endpoint (ADR-0015 / ADR-0021).

LLANOWAR = {
    "name": "Llanowar Elves",
    "type_line": "Creature — Elf Druid",
    "mana_cost": "{G}",
    "cmc": 1.0,
    "color_identity": ["G"],
    "oracle_text": "{T}: Add {G}.",
    "rarity": "common",
    "prices": {"usd": "0.15"},
    "image_uris": {"normal": "https://img/elf-normal.jpg"},
}
PLANESWALKER = {
    "name": "Test Walker",
    "type_line": "Legendary Planeswalker — Test",
    "mana_cost": "{2}{U}",
    "cmc": 3.0,
    "color_identity": ["U"],
    "oracle_text": "+1: Draw a card.",
    "rarity": "mythic",
    "prices": {"usd": "5.00"},
    "legalities": {"commander": "legal", "brawl": "legal", "standardbrawl": "legal"},
}


def _client_returning(cards):
    state = ForgeState(
        by_name={},
        search_fn=lambda **_: cards,
        session=DeckSession("commander"),
        bulk_available=True,
    )
    return TestClient(build_app(state)), state


def test_find_returns_503_without_bulk():
    state = ForgeState(
        by_name={},
        search_fn=_fake_search,
        session=DeckSession("commander"),
        bulk_available=False,
    )
    resp = TestClient(build_app(state)).post("/api/find", json={"name": "x"})
    assert resp.status_code == 503
    assert "download-bulk" in resp.json()["error"]


def test_results_carry_projection_and_images():
    client, _ = _client_returning([LLANOWAR])
    res = client.post("/api/find", json={"type": "Creature"}).json()["results"]
    assert res[0]["name"] == "Llanowar Elves"
    assert res[0]["images"]["normal"] == "https://img/elf-normal.jpg"
    assert res[0]["cmc"] == 1.0


def test_can_be_commander_is_format_aware():
    # A legendary planeswalker is a commander in historic_brawl but not in commander.
    client, _ = _client_returning([PLANESWALKER])
    body = {"name": "Test Walker"}
    cmd = client.post("/api/find", json=body).json()["results"][0]
    assert cmd["can_be_commander"] is False  # default commander format
    client.post("/api/deck/format", json={"format": "historic_brawl"})
    hb = client.post("/api/find", json=body).json()["results"][0]
    assert hb["can_be_commander"] is True


def test_owned_candidate_carries_ownership_keys():
    # F3: owned/owned_qty flow through views.candidate_view (the active Collection slot,
    # ADR-0018); a non-owned candidate carries no ownership keys (byte-compatible wire).
    tok = _avenue("agent:1", "Tokens", "create.*token")
    client, state = _client(focused=("agent:1",), agent_avenues=(tok,))
    engine.set_collection(state, "paper", {"cards": [{"name": "Token Maker", "quantity": 2}]})
    res = client.post("/api/find", json={"limit": 25}).json()["results"]
    tm = next(r for r in res if r["name"] == "Token Maker")
    assert tm["owned"] is True
    assert tm["owned_qty"] == 2
    other = next(r for r in res if r["name"] == "Both")  # in the pool, not owned
    assert "owned" not in other
