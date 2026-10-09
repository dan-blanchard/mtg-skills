"""Route tests for the Meta panel (ADR-0059): GET /api/meta reads the arena-meta
cache, Refresh fetches (here: stubbed), Tune reads the cached meta archetype."""

import json

import pytest
from fastapi.testclient import TestClient

from mtg_utils._arena_meta import meta as m
from mtg_utils._arena_meta import untapped
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import test_card

# A synthetic commander (an obviously fictional name, machinery only) and real deck
# cards.
CMD = {
    "name": "Test Commander Alpha",
    "type_line": "Legendary Creature — Goblin Warrior",
    "cmc": 4.0,
    "color_identity": ["R"],
    "oracle_text": "{T}: Create a 1/1 red Goblin creature token.",
}
RABBLE = test_card("Goblin Rabblemaster")
MOUNTAIN = test_card("Mountain")
INDEX = {c["name"]: c for c in (CMD, RABBLE, MOUNTAIN)}


def _snapshot(*extra: tuple[str, int]) -> m.Snapshot:
    """The cached Brawl_Ladder meta; ``extra`` adds cards to archetype 1's list."""
    plat = {"platinum": m.Record(400, 220)}
    return m.Snapshot(
        event="Brawl_Ladder",
        period={"id": 763, "description": "Set Release", "start": "2026-09-29"},
        fetched_at="2026-10-05T12:00:00+00:00",
        archetypes={
            1: m.MetaArchetype(1, "Mono-Red / Test Commander Alpha", "R", plat),
            2: m.MetaArchetype(2, "Mono-Blue / Someone Else", "U", plat),
        },
        decks=(
            m.MetaDeck(
                1,
                ("Test Commander Alpha",),
                (
                    ("Mountain", 30),
                    ("Goblin Matron", 1),
                    ("Goblin Rabblemaster", 1),
                    *extra,
                ),
                (),
                plat,
            ),
            m.MetaDeck(2, ("Someone Else",), (("Island", 30),), (), plat),
        ),
        lands=frozenset({"Mountain", "Island"}),
    )


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    path = untapped.meta_dir() / "Brawl_Ladder.current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_snapshot().to_json()))
    return path


def _client(fmt="competitive_brawl"):
    session = DeckSession(fmt)
    session.add("Test Commander Alpha", zone="commanders")
    session.add("Goblin Rabblemaster")
    session.add("Mountain")
    state = ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)
    return TestClient(build_app(state)), state


@pytest.mark.usefixtures("cache")
def test_meta_reads_the_cache_and_matches_the_commander():
    client, _ = _client()
    data = client.get("/api/meta").json()
    assert data["available"]
    assert data["cached"]
    report = data["report"]
    assert report["match"] == {
        "archetype": "Mono-Red / Test Commander Alpha",
        "by": "commander",
        "overlap": 1.0,
    }
    assert {c["name"] for c in report["core"]["cards"]} == {
        "Mountain",
        "Goblin Matron",
        "Goblin Rabblemaster",
    }
    assert [r["name"] for r in report["field"]][:1] == [
        "Mono-Red / Test Commander Alpha"
    ]


def test_meta_with_nothing_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    data = _client()[0].get("/api/meta").json()
    assert data == {
        "available": True,
        "event": "Brawl_Ladder",
        "signed_in": False,
        "cached": False,
    }


@pytest.mark.usefixtures("cache")
def test_a_format_without_an_arena_queue_has_no_meta():
    data = _client("commander")[0].get("/api/meta").json()
    assert data["available"] is False


@pytest.mark.usefixtures("cache")
def test_bad_ranks_are_a_400():
    assert _client()[0].get("/api/meta?ranks=wood%2B").status_code == 400


@pytest.mark.usefixtures("cache")
def test_tune_reads_the_cached_meta_archetype():
    client, _ = _client()
    sc = client.post("/api/tune", json={"max_swaps": 0}).json()["scorecard"]
    assert sc["meta"]["archetype"]["name"] == "Mono-Red / Test Commander Alpha"
    assert [c["name"] for c in sc["meta"]["missing_core"]] == ["Goblin Matron"]
    off = client.post("/api/tune", json={"max_swaps": 0, "meta_archetype": "off"})
    assert off.json()["scorecard"]["meta"] is None


@pytest.mark.usefixtures("cache")
def test_refresh_reports_a_sign_in_it_needs(monkeypatch):
    def needs_sign_in(*_a, **_k):
        raise untapped.SignInRequiredError

    monkeypatch.setattr(untapped, "load_snapshot", needs_sign_in)
    r = _client()[0].post("/api/meta/refresh", json={})
    assert r.status_code == 409
    assert r.json()["sign_in"] is True
    assert "arena-meta --login" in r.json()["error"]


@pytest.mark.usefixtures("cache")
def test_refresh_fetches_then_answers_from_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        untapped, "load_snapshot", lambda event, **kw: calls.append((event, kw))
    )
    r = _client()[0].post("/api/meta/refresh", json={})
    assert r.status_code == 200
    ((event, kwargs),) = calls
    assert event == "Brawl_Ladder"
    assert kwargs["refresh"] is True
    assert r.json()["cached"] is True


@pytest.mark.usefixtures("cache")
def test_login_opens_the_sign_in_window(monkeypatch):
    import threading

    opened = threading.Event()
    monkeypatch.setattr(untapped, "login", opened.set)
    client, _ = _client()
    assert client.post("/api/meta/login").json() == {"started": True}
    assert opened.wait(timeout=5)


@pytest.mark.usefixtures("cache")
def test_meta_takes_a_wildcard_allowance():
    client, _ = _client()
    assert client.get("/api/meta?wildcards=rare%3D2").status_code == 200
    assert client.get("/api/meta?wildcards=gold%3D2").status_code == 400


@pytest.mark.usefixtures("cache")
def test_the_panels_on_open_check_fetches_only_when_stale(monkeypatch):
    calls = []
    monkeypatch.setattr(
        untapped, "load_snapshot", lambda _event, **kw: calls.append(kw["refresh"])
    )
    client, _ = _client()
    client.post("/api/meta/refresh", json={"force": False})
    client.post("/api/meta/refresh", json={})
    assert calls == [False, True]


def test_refresh_fills_a_bo3_decks_own_queue(tmp_path, monkeypatch):
    """A Bo3 deck reads the Bo1 cache as a fallback, but Refresh fetches Bo3."""
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    bo1 = untapped.meta_dir() / "Ladder.current.json"
    bo1.parent.mkdir(parents=True)
    bo1.write_text(json.dumps({**_snapshot().to_json(), "event": "Ladder"}))
    fetched = []
    monkeypatch.setattr(
        untapped, "load_snapshot", lambda event, **_kw: fetched.append(event)
    )
    session = DeckSession("standard")
    session.add("Mountain")
    session.add("Mountain", zone="sideboard")
    state = ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)
    client = TestClient(build_app(state))
    assert client.get("/api/meta").json()["event"] == "Ladder"  # the fallback
    client.post("/api/meta/refresh", json={})
    assert fetched == ["Traditional_Ladder"]


# --- Find: the meta share breaks synergy ties (ADR-0059) ---------------------------
# Two synthetic candidates (machinery only) with the same text, so the same synergy:
# the rogue is cheaper, but only the staple is in the meta archetype's list.
_STAPLE = {
    "name": "Test Meta Staple",
    "type_line": "Sorcery",
    "cmc": 2.0,
    "color_identity": ["R"],
    "oracle_text": "Create a 1/1 red Goblin creature token.",
    "prices": {"usd": "5.00"},
}
_ROGUE = {**_STAPLE, "name": "Test Meta Rogue", "prices": {"usd": "0.10"}}


def _find_client(tmp_path, monkeypatch, *, cached: bool = True):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    if cached:
        path = untapped.meta_dir() / "Brawl_Ladder.current.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(_snapshot(("Test Meta Staple", 1)).to_json()))
    client, state = _client()
    state.search_fn = lambda **_: [_ROGUE, _STAPLE]
    return client


def _find(client, **extra):
    data = client.post("/api/find", json={"name": "Test Meta", **extra}).json()
    return [(r["name"], r["score"].get("meta_share")) for r in data["results"]]


def test_find_breaks_synergy_ties_by_meta_share(tmp_path, monkeypatch):
    client = _find_client(tmp_path, monkeypatch)
    assert _find(client) == [("Test Meta Staple", 1.0), ("Test Meta Rogue", 0.0)]
    # "off" skips the meta, as Tune's does: price decides again, no share served.
    assert _find(client, meta_archetype="off") == [
        ("Test Meta Rogue", None),
        ("Test Meta Staple", None),
    ]


def test_find_without_a_cached_meta_ranks_as_before(tmp_path, monkeypatch):
    client = _find_client(tmp_path, monkeypatch, cached=False)
    assert _find(client) == [("Test Meta Rogue", None), ("Test Meta Staple", None)]
