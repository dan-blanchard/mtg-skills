"""Collection + derived ownership (#2, ADR-0018): a global, two-slot Collection whose
ownership is DERIVED per snapshot from the active (format-keyed) slot — never stored —
with basic lands excluded from the readout."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import collection, engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _rec(name, type_line, ci):
    return {
        "name": name,
        "type_line": type_line,
        "cmc": 1.0,
        "color_identity": ci,
        "oracle_text": "",
        "prices": {"usd": "1"},
        "legalities": {"commander": "legal", "brawl": "legal"},
    }


BY_NAME = {
    "Sol Ring": _rec("Sol Ring", "Artifact", []),
    "Cultivate": _rec("Cultivate", "Sorcery", ["G"]),
    "Llanowar Elves": _rec("Llanowar Elves", "Creature — Elf Druid", ["G"]),
    "Forest": _rec("Forest", "Basic Land — Forest", ["G"]),
}
PAPER = "10 Sol Ring\n2 Cultivate\n20 Forest\n"


def _state(fmt="commander"):
    session = DeckSession(fmt)
    for n in ("Sol Ring", "Cultivate", "Llanowar Elves", "Forest"):
        session.add(n)
    return ForgeState(
        by_name=BY_NAME,
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )


def test_import_marks_owned_and_excludes_basics():
    client = TestClient(build_app(_state()))
    snap = client.post(
        "/api/collection/import", json={"text": PAPER, "slot": "paper"}
    ).json()
    by = {c["name"]: c for c in snap["deck"]["cards"]}
    assert by["Sol Ring"]["owned"] is True
    assert by["Sol Ring"]["owned_qty"] == 10  # collection count, not deck count
    assert by["Cultivate"]["owned"] is True
    assert "owned" not in by["Llanowar Elves"]  # not in the collection
    assert "owned" not in by["Forest"]  # basic land — excluded
    summary = snap["collection"]
    assert summary["active_slot"] == "paper"
    assert summary["owned"] == 2
    assert summary["deck_total"] == 3  # Forest (basic) excluded from N-of-M
    assert summary["slots"]["paper"] == 3


def test_reads_are_strictly_single_slot_by_format():
    client = TestClient(build_app(_state(fmt="commander")))
    client.post("/api/collection/import", json={"text": PAPER, "slot": "paper"})
    # Switching to an Arena format makes `arena` the active slot — and it's empty, so a
    # paper deck's ownership does NOT leak across (no union, no fallback).
    snap = client.post("/api/deck/format", json={"format": "historic_brawl"}).json()
    assert snap["collection"]["active_slot"] == "arena"
    assert snap["collection"]["owned"] == 0
    assert all("owned" not in c for c in snap["deck"]["cards"])


def test_clear_collection_drops_ownership():
    client = TestClient(build_app(_state()))
    client.post("/api/collection/import", json={"text": PAPER, "slot": "paper"})
    snap = client.post("/api/collection/clear", json={"slot": "paper"}).json()
    assert snap["collection"]["owned"] == 0
    assert snap["collection"]["slots"]["paper"] == 0


def test_unknown_slot_is_rejected():
    client = TestClient(build_app(_state()))
    r = client.post("/api/collection/import", json={"text": PAPER, "slot": "binder"})
    assert r.status_code == 400


def test_owned_quantities_reads_only_the_active_slot():
    state = _state()
    engine.set_collection(
        state, "paper", {"cards": [{"name": "Sol Ring", "quantity": 4}]}
    )
    assert engine.owned_quantities(state) == {"Sol Ring": 4}
    state.session.format = "brawl"  # arena slot — never imported
    assert engine.owned_quantities(state) == {}


def test_owned_collection_surfaces_cards_not_in_the_deck():
    # The tuner costs CANDIDATE adds (cards NOT yet in the deck), so owned_collection
    # must return the WHOLE active slot — unlike the deck-scoped owned_quantities.
    # Regression: feeding the tuner the deck-scoped map made every candidate read as
    # un-owned, so a zero wildcard budget filled nothing and owned cards burned budget.
    state = _state()  # deck: Sol Ring, Cultivate, Llanowar Elves, Forest
    engine.set_collection(
        state,
        "paper",
        {
            "cards": [
                {"name": "Cultivate", "quantity": 1},  # in the deck
                {"name": "Kodama's Reach", "quantity": 1},  # NOT in the deck (candidate)
                {"name": "Forest", "quantity": 30},  # basic — excluded
            ]
        },
    )
    owned = engine.owned_collection(state)
    assert owned == {"Cultivate": 1, "Kodama's Reach": 1}  # whole slot, basics dropped
    # The deck-scoped map can't see the candidate — the bug this function fixes.
    assert "Kodama's Reach" not in engine.owned_quantities(state)


def test_collection_store_round_trips(tmp_path):
    store = CollectionStore(tmp_path / "collection.json")
    store.save({"paper": {"cards": [{"name": "Sol Ring", "quantity": 3}]}})
    loaded = store.load()
    assert loaded["paper"]["cards"][0]["name"] == "Sol Ring"
    assert "arena" not in loaded  # only present slots are written


def test_arena_flavor_name_alias_matches_ownership():
    # ADR-0018: ownership uses mark_owned's DFC / Arena-alias logic. The deck lists the
    # canonical name; the Arena collection lists the flavor/printed name — they must match.
    from mtg_utils.names import normalize_card_name

    by_name = {"Masked Meower": _rec("Masked Meower", "Creature — Cat", ["W"])}
    session = DeckSession("historic_brawl")  # → active slot is arena
    session.add("Masked Meower")
    state = ForgeState(
        by_name=by_name,
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    state.name_aliases = {
        normalize_card_name("Skittering Kitten"): normalize_card_name("Masked Meower")
    }
    engine.set_collection(
        state, "arena", {"cards": [{"name": "Skittering Kitten", "quantity": 1}]}
    )
    # Owned under the Arena name → the canonical deck card reads as owned.
    assert engine.owned_quantities(state) == {"Masked Meower": 1}


def test_find_candidates_carry_the_owned_flag():
    # The "Owned only" Find facet filters on this wire field (candidate.owned).
    by_name = {
        "Sol Ring": _rec("Sol Ring", "Artifact", []),
        "Llanowar Elves": _rec("Llanowar Elves", "Creature — Elf", ["G"]),
    }
    state = ForgeState(
        by_name=by_name,
        search_fn=lambda **_: [by_name["Sol Ring"], by_name["Llanowar Elves"]],
        session=DeckSession("commander"),
        bulk_available=True,
    )
    engine.set_collection(
        state, "paper", {"cards": [{"name": "Sol Ring", "quantity": 3}]}
    )
    client = TestClient(build_app(state))
    res = client.post("/api/find", json={"name": "a", "limit": 25}).json()["results"]
    by_res = {c["name"]: c for c in res}
    assert by_res["Sol Ring"]["owned"] is True
    assert by_res["Sol Ring"]["owned_qty"] == 3  # the collection count
    assert "owned" not in by_res["Llanowar Elves"]  # un-owned → no flag


def test_quantity_zero_rows_are_excluded_everywhere():
    # Untapped / Arena exports include quantity-0 rows for cards the user doesn't own.
    # They must not count toward the collection size, ownership, or commander discovery
    # (mirrors find-commanders / mark-owned --min-quantity 1).
    by_name = {
        "Sol Ring": _rec("Sol Ring", "Artifact", []),
        "Ghave, Guru of Spores": _rec(
            "Ghave, Guru of Spores", "Legendary Creature — Fungus Shaman", ["B", "G"]
        ),
    }
    session = DeckSession("commander")
    session.add("Sol Ring")
    state = ForgeState(
        by_name=by_name,
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    # Owned: Sol Ring x2. NOT owned (wishlist row): Sol Ring is owned, Ghave qty 0.
    engine.set_collection(
        state,
        "paper",
        {
            "cards": [
                {"name": "Sol Ring", "quantity": 2},
                {"name": "Ghave, Guru of Spores", "quantity": 0},
            ]
        },
    )
    # Size counts only the owned card, not the qty-0 wishlist row.
    assert collection.slot_sizes(state.collections)["paper"] == 1
    # Ownership: Sol Ring owned, Ghave (qty 0) not owned.
    assert engine.owned_quantities(state) == {"Sol Ring": 2}
    # Discovery never surfaces the un-owned Ghave even though it's commander-eligible.
    found = engine.discover_commanders(state, sort="support")
    assert all(r["name"] != "Ghave, Guru of Spores" for r in found)


def test_load_collections_restores_and_precomputes_index(tmp_path):
    # ADR-0018 "auto-loaded on launch": the persisted file restores into live state with
    # its ownership lookup precomputed, so ownership is visible without a re-import.
    from mtg_utils._deck_forge.production import _load_collections
    from mtg_utils.mark_owned import owned_quantity

    store = CollectionStore(tmp_path / "collection.json")
    store.save({"paper": {"cards": [{"name": "Sol Ring", "quantity": 2}]}})
    collections, index = _load_collections(store)
    assert collections["paper"]["cards"][0]["name"] == "Sol Ring"
    assert "paper" in index  # precomputed, not lazily on first snapshot
    entries, lookup = index["paper"]
    assert owned_quantity("Sol Ring", entries, lookup) == 2
