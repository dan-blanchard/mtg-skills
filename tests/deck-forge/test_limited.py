"""deck-forge serves the limited family: a sealed / draft build bounded by its opened
pool (ADR-0055). The sideboard is DERIVED (the pool less the deck), the pool is the
copy limit, Find and Tune search the pool and nothing else, and the pool panel
enumerates every colour pair on equal footing."""

import json

import pytest
from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.engine import DeckRuleError
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _rec(name, type_line, cmc, colors, *, rarity="common", keywords=(), power=None):
    rec = {
        "id": f"id-{name}",
        "oracle_id": f"oid-{name}",
        "name": name,
        "type_line": type_line,
        "cmc": float(cmc),
        "colors": list(colors),
        "color_identity": list(colors),
        "oracle_text": "",
        "keywords": list(keywords),
        "rarity": rarity,
        "set": "hob",
        "collector_number": name[:3],
        "layout": "normal",
        "legalities": {},
        "prices": {"usd": "0.10"},
    }
    if power is not None:
        rec["power"], rec["toughness"] = str(power), str(power)
    return rec


BEAR = _rec("Bear", "Creature — Bear", 2, ["G"], power=2)
EAGLE = _rec("Eagle", "Creature — Bird", 3, ["W"], keywords=["Flying"], power=3)
TROLL = _rec("Troll", "Creature — Troll", 5, ["G"], rarity="rare", power=6)
PONY = _rec("Pony", "Creature — Horse", 1, ["W"], power=1)
FOREST = _rec("Forest", "Basic Land — Forest", 0, [])
PLAINS = _rec("Plains", "Basic Land — Plains", 0, [])
OFF_POOL = _rec("Dragon", "Creature — Dragon", 6, ["R"], rarity="mythic", power=6)
INDEX = {c["name"]: c for c in (BEAR, EAGLE, TROLL, PONY, FOREST, PLAINS, OFF_POOL)}

ARENA = "Deck\n2 Bear\n1 Eagle\n17 Forest\n\nSideboard\n1 Bear\n1 Troll\n3 Pony\n"


def _refusing_search(**_):
    raise AssertionError("a pool-bounded build must never search the database")


def _state(fmt="sealed", *, pool=(), cards=(), search_fn=None) -> ForgeState:
    session = DeckSession(fmt)
    for name, qty in pool:
        session.add(name, qty, zone="pool")
    for name, qty in cards:
        session.add(name, qty)
    return ForgeState(
        by_name=INDEX,
        search_fn=search_fn or _refusing_search,
        session=session,
        bulk_available=True,
    )


def _client(state):
    return TestClient(build_app(state))


# --- import -----------------------------------------------------------------------


def test_import_a_sealed_export_pools_everything_and_derives_the_sideboard():
    client = _client(_state("commander"))
    r = client.post(
        "/api/builds/import", json={"text": ARENA, "format": "sealed", "name": "HOB"}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["imported"]["pool"] == 25
    assert data["imported"]["cards"] == 20
    assert data["imported"]["sideboard"] == 5
    deck = data["deck"]
    assert {c["name"]: c["quantity"] for c in deck["cards"]} == {
        "Bear": 2,
        "Eagle": 1,
        "Forest": 17,
    }
    assert {c["name"]: c["quantity"] for c in deck["pool"]} == {
        "Bear": 3,
        "Eagle": 1,
        "Forest": 17,
        "Troll": 1,
        "Pony": 3,
    }
    # The sideboard is the pool less the deck — derived, never stored.
    assert {c["name"]: c["quantity"] for c in deck["sideboard"]} == {
        "Bear": 1,
        "Troll": 1,
        "Pony": 3,
    }


def test_import_pool_only_is_a_pool_with_no_deck_yet():
    client = _client(_state("commander"))
    data = client.post(
        "/api/builds/import",
        json={"text": ARENA, "format": "draft", "pool_only": True},
    ).json()
    assert data["deck"]["cards"] == []
    assert data["imported"]["pool"] == 25
    assert sum(c["quantity"] for c in data["deck"]["sideboard"]) == 25


# --- the pool bounds every add ------------------------------------------------------


def test_the_pool_is_the_copy_limit():
    state = _state(pool=[("Bear", 3)], cards=[("Bear", 3)])
    client = _client(state)
    r = client.post("/api/deck/add", json={"name": "Bear"})
    assert r.status_code == 400
    assert "the pool holds 3" in r.json()["error"]
    r = client.post("/api/deck/add", json={"name": "Dragon"})
    assert r.status_code == 400
    assert "not in the pool" in r.json()["error"]
    assert client.post(
        "/api/deck/add", json={"name": "Forest", "qty": 17}
    ).status_code == (
        200  # basics are unlimited and outside the pool (CR 100.2b)
    )
    # Growing the pool grows the limit.
    assert (
        client.post("/api/deck/add", json={"name": "Bear", "zone": "pool"}).status_code
        == 200
    )
    assert client.post("/api/deck/add", json={"name": "Bear"}).status_code == 200


def test_the_sideboard_is_derived_never_written():
    state = _state(pool=[("Bear", 3)], cards=[("Bear", 1)])
    client = _client(state)
    r = client.post("/api/deck/add", json={"name": "Bear", "zone": "sideboard"})
    assert r.status_code == 400
    assert "unused pool" in r.json()["error"]
    r = client.post("/api/deck/remove", json={"name": "Bear", "zone": "sideboard"})
    assert r.status_code == 400


def test_a_pool_copy_the_deck_runs_cannot_leave_the_pool():
    state = _state(pool=[("Bear", 2)], cards=[("Bear", 2)])
    client = _client(state)
    r = client.post("/api/deck/remove", json={"name": "Bear", "zone": "pool"})
    assert r.status_code == 400
    assert "cut it from the deck" in r.json()["error"]
    client.post("/api/deck/remove", json={"name": "Bear"})
    assert (
        client.post(
            "/api/deck/remove", json={"name": "Bear", "zone": "pool"}
        ).status_code
        == 200
    )


def test_moves_between_deck_and_the_derived_sideboard():
    state = _state(pool=[("Bear", 3)], cards=[("Bear", 3)])
    engine.move_card(state, "Bear", from_zone="cards", to_zone="sideboard")
    assert state.session.quantity_of("Bear") == 2
    assert state.session.derived_sideboard() == {"Bear": 1}
    engine.move_card(state, "Bear", from_zone="sideboard", to_zone="cards")
    assert state.session.quantity_of("Bear") == 3
    with pytest.raises(DeckRuleError, match="only 0 in sideboard"):
        engine.move_card(state, "Bear", from_zone="sideboard", to_zone="cards")


def test_moves_to_and_from_the_pool_never_change_the_pool():
    state = _state(pool=[("Bear", 3), ("Troll", 1)], cards=[("Bear", 2)])
    engine.move_card(state, "Troll", from_zone="pool", to_zone="cards")
    assert state.session.quantity_of("Troll") == 1
    assert state.session.quantity_of("Troll", zone="pool") == 1  # an add, not a move
    engine.move_card(state, "Bear", from_zone="cards", to_zone="pool")
    assert state.session.quantity_of("Bear") == 1
    assert state.session.quantity_of("Bear", zone="pool") == 3
    with pytest.raises(DeckRuleError, match="the pool holds 1"):
        engine.move_card(state, "Troll", from_zone="pool", to_zone="cards")
    # Between the pool and its derived sideboard there is nothing to move.
    with pytest.raises(DeckRuleError, match="already in the pool"):
        engine.move_card(state, "Bear", from_zone="pool", to_zone="sideboard")
    assert state.session.quantity_of("Bear", zone="pool") == 3


# --- crossing the pool boundary -----------------------------------------------------


def test_switching_into_and_out_of_a_pool_bounded_format_keeps_the_cards():
    state = _state("modern", cards=[("Bear", 4)])
    state.session.add("Troll", 1, zone="sideboard")
    engine.set_format(state, "sealed")
    assert state.session.zone_quantities("pool") == {"Bear": 4, "Troll": 1}
    assert state.session.derived_sideboard() == {"Troll": 1}
    engine.set_format(state, "modern")
    assert state.session.zone_quantities("sideboard") == {"Troll": 1}
    assert state.session.to_deck_dict()["sideboard"] == [
        {"name": "Troll", "quantity": 1}
    ]
    assert state.session.to_deck_dict()["pool"] == []  # a Modern deck has no pool
    # Re-entering with a stored sideboard pools it too.
    engine.set_format(state, "draft")
    assert state.session.zone_quantities("pool") == {"Bear": 4, "Troll": 1}


def test_a_saved_limited_build_round_trips_with_its_pool():
    state = _state(pool=[("Bear", 3), ("Troll", 1)], cards=[("Bear", 2)])
    again = DeckSession.from_deck_dict(state.session.to_deck_dict())
    assert again.to_deck_dict() == state.session.to_deck_dict()
    assert again.derived_sideboard() == {"Bear": 1, "Troll": 1}
    # A dict from before the pool zone existed pools its cards and sideboard.
    legacy = {
        "format": "sealed",
        "cards": [{"name": "Bear", "quantity": 2}],
        "sideboard": [{"name": "Troll", "quantity": 1}],
    }
    old = DeckSession.from_deck_dict(legacy)
    assert old.zone_quantities("pool") == {"Bear": 2, "Troll": 1}
    assert old.derived_sideboard() == {"Troll": 1}


# --- Find and Tune search the pool --------------------------------------------------


def test_a_paper_pool_search_never_drops_a_card_over_its_game():
    # A paper sealed build: the game gate a database search applies must not touch
    # pool records (an Arena-only printing you opened is still yours to play).
    state = _state(pool=[("Bear", 1)])
    state.by_name["Bear"] = {**BEAR, "games": ["arena"]}
    state.session.set_medium("paper")
    page = engine.find_candidates(state, engine.FindParams(name="bear"))
    assert [r["card"]["name"] for r in page.rows] == ["Bear"]


def test_signals_route_reads_the_counted_deck_not_the_pool():
    state = _state(pool=[("Bear", 3), ("Troll", 1)], cards=[("Bear", 2)])
    client = _client(state)
    assert (
        client.get("/api/signals").json()["signals"]
        == (client.get("/api/snapshot").json()["signals"])
    )


def test_the_deck_view_and_the_build_store_carry_the_pool(tmp_path):
    from mtg_utils._deck_forge import views
    from mtg_utils._deck_forge.persistence import BuildStore

    state = _state(pool=[("Bear", 3)], cards=[("Bear", 2)])
    dv = views.deck_view(state)
    assert [(c["name"], c["quantity"]) for c in dv["pool"]] == [("Bear", 3)]
    assert [(c["name"], c["quantity"]) for c in dv["sideboard"]] == [("Bear", 1)]
    store = BuildStore(tmp_path)
    store.save("sealed1", "HOB", state.session.to_deck_dict())
    assert [b["id"] for b in store.list()] == ["sealed1"]
    again = DeckSession.from_deck_dict(store.load("sealed1")["deck"])
    assert again.to_deck_dict() == state.session.to_deck_dict()


def test_find_searches_only_the_pool_and_strips_what_the_deck_exhausted():
    state = _state(pool=[("Bear", 2), ("Eagle", 1), ("Troll", 1)], cards=[("Bear", 2)])
    page = engine.find_candidates(state, engine.FindParams(type="Creature"))
    names = {r["card"]["name"] for r in page.rows}
    assert names == {"Eagle", "Troll"}  # Bear exhausted; Dragon never opened
    page = engine.find_candidates(state, engine.FindParams(color_identity="W"))
    assert {r["card"]["name"] for r in page.rows} == {"Eagle"}


def test_tune_runs_over_the_pool_and_never_the_database():
    state = _state(
        pool=[("Bear", 3), ("Eagle", 2), ("Troll", 1), ("Pony", 3)],
        cards=[("Bear", 2), ("Forest", 17)],
    )
    r = _client(state).post("/api/tune", json={"max_swaps": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scorecard"]["commander_fit"] is None
    assert body["scorecard"]["size"]["exact"] is False
    for s in body["swaps"]:
        assert s["add"]["name"] in {"Bear", "Eagle", "Troll", "Pony"}
        assert s["add"]["owned"] is True  # an opened pool is owned outright


# --- the snapshot's pool panel ------------------------------------------------------


def test_snapshot_serves_the_pool_panel_and_no_wildcards():
    state = _state(pool=[("Bear", 3), ("Eagle", 1), ("Troll", 1)], cards=[("Bear", 1)])
    state.session.set_medium("digital")
    snap = engine.snapshot(state)
    pool = snap["pool"]
    assert (pool["size"], pool["unused"]) == (5, 4)
    rows = {r["pair"]: r for r in pool["color_pairs"]}
    assert rows["G"]["playables"] == 4
    assert rows["WG"]["evasion"] == 1
    assert rows["WG"]["rares"] == 1
    assert snap["wildcards"] is None
    assert snap["deck"]["sideboard"][0]["name"] == "Bear"
    assert engine.snapshot(_state("modern"))["pool"] is None


def test_export_writes_the_derived_sideboard():
    state = _state(pool=[("Bear", 3), ("Troll", 1)], cards=[("Bear", 2)])
    text = _client(state).get("/api/export?fmt=arena").json()["text"]
    assert text.split("Sideboard")[1].strip().splitlines() == ["1 Bear", "1 Troll"]


# --- set scan + seed ----------------------------------------------------------------


def test_set_scan_route(tmp_path):
    state = _state()
    client = _client(state)
    assert client.get("/api/set-scan?code=hob").status_code == 503  # no bulk
    bulk = tmp_path / "bulk.json"
    bulk.write_text(json.dumps(list(INDEX.values())))
    state.bulk_path = bulk
    assert client.get("/api/set-scan?code=zzz").status_code == 404
    r = client.get("/api/set-scan?code=HOB")
    assert r.status_code == 200, r.text
    scan = r.json()
    assert scan["code"] == "HOB"
    assert scan["creatures"] == 5
    assert scan["evasion"]["by_keyword"] == {"Flying": 1}


def test_seed_keeps_what_it_replaced_for_one_undo():
    state = _state(
        pool=[("Bear", 15), ("Troll", 8), ("Eagle", 8)], cards=[("Eagle", 3)]
    )
    client = _client(state)
    assert engine.snapshot(state)["pool"]["seed_undo"] is False
    assert client.post("/api/deck/seed/undo").status_code == 400
    r = client.post("/api/deck/seed", json={"colors": "G"})
    assert r.json()["seeded"]["replaced"] == 3
    assert r.json()["pool"]["seed_undo"] is True
    snap = client.post("/api/deck/seed/undo").json()
    assert [(c["name"], c["quantity"]) for c in snap["deck"]["cards"]] == [("Eagle", 3)]
    assert snap["pool"]["seed_undo"] is False
    assert client.post("/api/deck/seed/undo").status_code == 400  # one level
    # Switching builds drops the undo: it belongs to the deck it replaced.
    client.post("/api/deck/seed", json={"colors": "G"})
    client.post("/api/builds/new", json={"format": "sealed"})
    assert client.post("/api/deck/seed/undo").status_code == 400


def test_seed_builds_a_first_deck_from_the_pool_only():
    state = _state(
        pool=[("Bear", 15), ("Troll", 8), ("Eagle", 8), ("Pony", 6), ("Dragon", 4)]
    )
    r = _client(state).post("/api/deck/seed", json={"colors": "G"})
    assert r.status_code == 200, r.text
    deck = r.json()["deck"]
    cards = {c["name"]: c["quantity"] for c in deck["cards"]}
    assert sum(cards.values()) == 40
    assert cards.get("Forest") == 17
    assert set(cards) <= {"Bear", "Troll", "Forest"}  # only green pool cards + basics
    assert cards["Bear"] <= 15  # never more copies than the pool holds
    assert r.json()["seeded"]["lands"] == 17
    assert (
        _client(_state("modern"))
        .post("/api/deck/seed", json={"colors": "G"})
        .status_code
        == 400
    )
    assert (
        _client(_state()).post("/api/deck/seed", json={"colors": "G"}).status_code
        == 400
    )
