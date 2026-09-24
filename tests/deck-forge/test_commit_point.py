"""The hub's commit point and build switch (ADR-0013's transport side effects, once).

Every state-changing route ends the same way — persist the build IF the deck changed,
take the snapshot, broadcast it to every open browser, return it — and that tail is
``app._commit``. These tests cross the HTTP seam for every such route and pin both
halves: exactly one snapshot is broadcast and it is the one returned; and the build
file is written by the routes that change the DECK and by no other.

``engine.switch_build`` and the lane functions are engine rules, so they are tested as
plain functions over a ``ForgeState``.
"""

import json

import pytest
from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import test_card

FOREST = test_card("Forest")
ELVES = test_card("Llanowar Elves")
INDEX = {c["name"]: c for c in (FOREST, ELVES)}
SAVED_DECK = {
    "format": "commander",
    "medium": "paper",
    "deck_size": 100,
    "commanders": [],
    "cards": [{"name": "Forest", "quantity": 4}],
    "sideboard": [],
    "companion": [],
}


class _RecordingHub(EventHub):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[dict] = []

    def publish(self, data: str) -> None:
        self.published.append(json.loads(data))
        super().publish(data)


class _RecordingStore(BuildStore):
    """A real ``BuildStore`` that also counts the LIVE build's saves."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.saved_ids: list[str] = []

    def save(self, build_id, name, deck):
        self.saved_ids.append(build_id)
        return super().save(build_id, name, deck)


@pytest.fixture
def hub_state(tmp_path):
    session = DeckSession("historic_brawl")  # a format with a medium and size choice
    session.add("Llanowar Elves", 1)
    state = ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: [],
        session=session,
        hub=_RecordingHub(),
        store=_RecordingStore(tmp_path / "builds"),
        build_id="live",
        build_name="Live",
    )
    state.store.save("other", "Other", SAVED_DECK)
    state.store.saved_ids.clear()
    engine.add_agent_avenue(state, label="Seeded lane", description="", search={})
    return state


def _post(path, body=None):
    return lambda client: client.post(path, json=body or {})


def _delete(path):
    return lambda client: client.delete(path)


# (id, request, persists the LIVE build?)
ROUTES = [
    ("deck/add", _post("/api/deck/add", {"name": "Forest", "qty": 2}), True),
    ("deck/remove", _post("/api/deck/remove", {"name": "Llanowar Elves"}), True),
    ("deck/format", _post("/api/deck/format", {"format": "commander"}), True),
    ("deck/medium", _post("/api/deck/medium", {"medium": "paper"}), True),
    ("deck/deck-size", _post("/api/deck/deck-size", {"deck_size": 100}), True),
    ("deck/balance-lands", _post("/api/deck/balance-lands"), True),
    (
        "deck/printing",
        _post("/api/deck/printing", {"name": "Llanowar Elves", "printing_id": None}),
        True,
    ),
    ("builds/new", _post("/api/builds/new", {"format": "commander"}), True),
    (
        "builds/import",
        _post("/api/builds/import", {"text": "2 Forest", "format": "commander"}),
        True,
    ),
    (
        "builds/rename-live",
        _post("/api/builds/rename", {"id": "live", "name": "N"}),
        True,
    ),
    # A load must not rewrite the file it just read.
    ("builds/load", _post("/api/builds/load", {"id": "other"}), False),
    # Renaming ANOTHER build writes that build's file, never the live one.
    (
        "builds/rename-other",
        _post("/api/builds/rename", {"id": "other", "name": "N"}),
        False,
    ),
    # A Collection is global to the hub — not part of any build.
    (
        "collection/import",
        _post("/api/collection/import", {"slot": "paper", "text": "1 Forest"}),
        False,
    ),
    ("collection/clear", _post("/api/collection/clear", {"slot": "paper"}), False),
    # Lanes and focus pins are per-build RUNTIME state, never in the build file.
    ("avenues/add", _post("/api/avenues", {"label": "Tokens"}), False),
    ("avenues/remove", _delete("/api/avenues/agent:1"), False),
    ("avenues/focus", _post("/api/avenues/agent:1/focus"), False),
]


@pytest.mark.parametrize(
    ("request_fn", "persists"),
    [pytest.param(fn, persists, id=rid) for rid, fn, persists in ROUTES],
)
def test_every_state_changing_route_commits_once(hub_state, request_fn, persists):
    client = TestClient(build_app(hub_state))
    resp = request_fn(client)
    assert resp.status_code == 200, resp.text
    returned = resp.json()

    # Exactly one broadcast, and it is the snapshot the caller got back (a route may
    # wrap it in an envelope — build_id / avenue / imported / slot — never alter it).
    assert len(hub_state.hub.published) == 1
    (published,) = hub_state.hub.published
    assert "deck" in published
    assert {k: returned[k] for k in published} == published

    live_saves = [i for i in hub_state.store.saved_ids if i == hub_state.build_id]
    assert len(live_saves) == (1 if persists else 0)
    if persists:
        on_disk = hub_state.store.load(hub_state.build_id)
        assert on_disk["deck"] == hub_state.session.to_deck_dict()
        assert on_disk["name"] == hub_state.build_name


def test_trim_lands_persists_only_when_it_changed_something(hub_state):
    client = TestClient(build_app(hub_state))
    resp = client.post("/api/deck/trim-lands").json()
    changed = bool(resp["trimmed"]["add"] or resp["trimmed"]["remove"])
    assert not changed  # one Elf, no lands: nothing to trim
    assert hub_state.store.saved_ids == []
    # …but the (unchanged) snapshot is still broadcast, with the route's readout on it.
    (published,) = hub_state.hub.published
    assert published["trimmed"] == resp["trimmed"]


def test_balance_lands_broadcasts_its_readout(hub_state):
    client = TestClient(build_app(hub_state))
    resp = client.post("/api/deck/balance-lands").json()
    (published,) = hub_state.hub.published
    assert published["balanced"] == resp["balanced"]


def test_deleting_the_live_build_switches_persists_and_broadcasts(hub_state):
    client = TestClient(build_app(hub_state))
    client.post("/api/deck/add", json={"name": "Forest"})  # give "live" a file
    hub_state.hub.published.clear()
    hub_state.store.saved_ids.clear()

    resp = client.delete("/api/builds/live").json()
    assert resp["deleted"] is True
    assert resp["current"] != "live"
    assert hub_state.build_id == resp["current"]
    # The fresh build is persisted under its NEW id (autosave must never re-create
    # the deleted one) and every open browser hears about the switch.
    assert hub_state.store.saved_ids == [resp["current"]]
    assert hub_state.store.load("live") is None
    (published,) = hub_state.hub.published
    assert published["build_id"] == resp["current"]
    assert hub_state.session.card_names() == []


def test_deleting_another_build_leaves_the_live_one_alone(hub_state):
    client = TestClient(build_app(hub_state))
    resp = client.delete("/api/builds/other").json()
    assert resp == {"deleted": True, "current": "live", "builds": []}
    assert hub_state.hub.published == []
    assert hub_state.store.saved_ids == []


def test_a_rejected_mutation_commits_nothing(hub_state):
    client = TestClient(build_app(hub_state))
    assert client.post("/api/deck/format", json={"format": "nope"}).status_code == 400
    assert client.post("/api/deck/add", json={"name": "Not A Card"}).status_code == 404
    assert hub_state.hub.published == []
    assert hub_state.store.saved_ids == []


@pytest.mark.parametrize(
    "request_fn",
    [
        pytest.param(_post("/api/builds/new", {"format": "commander"}), id="new"),
        pytest.param(
            _post("/api/builds/import", {"text": "2 Forest", "format": "commander"}),
            id="import",
        ),
        pytest.param(_post("/api/builds/load", {"id": "other"}), id="load"),
        pytest.param(_delete("/api/builds/live"), id="delete-live"),
    ],
)
def test_every_build_switch_drops_the_previous_builds_lanes(hub_state, request_fn):
    client = TestClient(build_app(hub_state))
    client.post("/api/deck/add", json={"name": "Forest"})  # so delete-live has a file
    client.post("/api/avenues/agent:1/focus")
    assert hub_state.agent_avenues
    assert hub_state.focused_avenue_ids
    assert request_fn(client).status_code == 200
    assert hub_state.agent_avenues == []
    assert hub_state.focused_avenue_ids == set()


# ── engine.switch_build ──────────────────────────────────────────────────────


def _bare_state():
    return ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        build_id="old",
        build_name="Old",
    )


def test_switch_build_changes_everything_that_is_per_build():
    state = _bare_state()
    engine.add_agent_avenue(state, label="Old lane", description="", search={})
    state.focused_avenue_ids.add("agent:1")
    fresh = DeckSession("brawl")

    engine.switch_build(state, fresh, name="Fresh")

    assert state.session is fresh
    assert state.build_name == "Fresh"
    assert state.agent_avenues == []
    assert state.focused_avenue_ids == set()


def test_switch_build_mints_an_id_unless_given_one():
    state = _bare_state()
    engine.switch_build(state, DeckSession("commander"), name="A")
    first = state.build_id
    assert first
    assert first != "old"
    engine.switch_build(state, DeckSession("commander"), name="B")
    assert state.build_id != first  # a new id per switch
    engine.switch_build(state, DeckSession("commander"), name="C", build_id="saved1")
    assert state.build_id == "saved1"  # a load keeps the stored build's id


# ── agent lanes and focus pins ───────────────────────────────────────────────


def test_add_agent_avenue_numbers_lanes_and_never_reuses_an_id():
    state = _bare_state()
    first = engine.add_agent_avenue(
        state, label="Tokens", description="go wide", search={"oracle": "token"}
    )
    assert first == {
        "id": "agent:1",
        "label": "Tokens",
        "description": "go wide",
        "scope": "",
        "source": "agent",
        "search": {"oracle": "token"},
    }
    engine.remove_avenue(state, "agent:1")
    second = engine.add_agent_avenue(state, label="Again", description="", search={})
    assert second["id"] == "agent:2"
    assert state.agent_avenues == [second]


def test_remove_avenue_also_unpins_it():
    state = _bare_state()
    engine.add_agent_avenue(state, label="Tokens", description="", search={})
    engine.toggle_avenue_focus(state, "agent:1")
    engine.remove_avenue(state, "agent:1")
    assert state.agent_avenues == []
    assert state.focused_avenue_ids == set()  # a removed lane can't stay focused
    engine.remove_avenue(state, "agent:1")  # removing a missing lane is a no-op


def test_toggle_avenue_focus_flips_both_ways():
    state = _bare_state()
    engine.toggle_avenue_focus(state, "signal:lifegain")
    assert state.focused_avenue_ids == {"signal:lifegain"}
    engine.toggle_avenue_focus(state, "signal:lifegain")
    assert state.focused_avenue_ids == set()
