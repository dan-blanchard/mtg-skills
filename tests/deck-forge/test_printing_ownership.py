"""Printing- and foil-aware ownership: /api/printings owned counts + owned-first sort,
the card-level vs printing-level tri-state (``owned`` vs ``owned_printing``), deck
import auto-pinning from a "(SET) 123 *F*" suffix, finish validation on
POST /api/deck/printing, foil price display, export round-trip, and old-format
(name-only) collection.json backward compatibility."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import collection, engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.parse_deck import parse_deck_text


def _printing(set_code, collector, usd, released, finishes=("nonfoil",), **prices):
    return {
        "name": "Sol Ring",
        "oracle_id": "oid-sol-ring",
        "id": f"id-{set_code}",
        "set": set_code.lower(),
        "set_name": f"{set_code} set",
        "collector_number": collector,
        "released_at": released,
        "rarity": "uncommon",
        "finishes": list(finishes),
        "prices": {"usd": usd, **prices},
        "image_uris": {"small": f"https://img/{set_code}/small.jpg"},
        "type_line": "Artifact",
        "cmc": 1.0,
        "color_identity": [],
        "oracle_text": "{T}: Add {C}{C}.",
        "mana_cost": "{1}",
        "legalities": {"commander": "legal"},
        "keywords": [],
    }


CHEAP = _printing("lea", "1", "2.00", "1993-08-05")  # nonfoil only
PREMIUM = _printing(
    "c21", "263", "5.00", "2021-04-23", finishes=("nonfoil", "foil"), usd_foil="9.00"
)
NEWEST = _printing("otj", "451", "4.00", "2024-04-19", finishes=("nonfoil", "etched"))

CULTIVATE = {
    "name": "Cultivate",
    "oracle_id": "oid-cultivate",
    "id": "id-cultivate",
    "set": "m21",
    "collector_number": "177",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "color_identity": ["G"],
    "oracle_text": "",
    "prices": {"usd": "1.00"},
    "legalities": {"commander": "legal"},
}


def _state():
    return ForgeState(
        by_name={"Sol Ring": CHEAP, "Cultivate": CULTIVATE},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_available=True,
        printings_by_oracle={
            "oid-sol-ring": [NEWEST, PREMIUM, CHEAP],  # newest first
            "oid-cultivate": [CULTIVATE],
        },
        printing_by_id={
            "id-lea": CHEAP,
            "id-c21": PREMIUM,
            "id-otj": NEWEST,
            "id-cultivate": CULTIVATE,
        },
    )


# Sol Ring owned with printing detail (3 nonfoil LEA + 1 foil C21); Cultivate owned
# name-only (no printing detail → tri-state absent).
DETAILED_PILE = {
    "cards": [
        {
            "name": "Sol Ring",
            "quantity": 4,
            "printings": [
                {"set": "lea", "collector_number": "1", "quantity": 3},
                {
                    "set": "c21",
                    "collector_number": "263",
                    "quantity": 0,
                    "foil_quantity": 1,
                },
            ],
        },
        {"name": "Cultivate", "quantity": 2},
    ]
}


def _client(state=None):
    state = state or _state()
    return TestClient(build_app(state)), state


# ---------------------------------------------------------------- /api/printings


def test_printings_carry_owned_counts_and_sort_owned_first():
    client, state = _client()
    engine.set_collection(state, "paper", DETAILED_PILE)
    res = client.get("/api/printings?name=Sol Ring").json()
    # Owned first by total desc (LEA 3, C21 1), then unowned newest-first (OTJ).
    assert [p["set"] for p in res["printings"]] == ["lea", "c21", "otj"]
    by_set = {p["set"]: p for p in res["printings"]}
    assert (by_set["lea"]["owned_qty"], by_set["lea"]["owned_foil_qty"]) == (3, 0)
    assert (by_set["c21"]["owned_qty"], by_set["c21"]["owned_foil_qty"]) == (0, 1)
    assert (by_set["otj"]["owned_qty"], by_set["otj"]["owned_foil_qty"]) == (0, 0)
    assert res["card_owned"] is True
    assert res["card_owned_qty"] == 4  # the authoritative name-level total


def test_printings_without_detail_keep_newest_first_and_zero_counts():
    client, state = _client()
    # Name-only ownership: card_owned still true, per-printing counts all 0.
    engine.set_collection(
        state, "paper", {"cards": [{"name": "Sol Ring", "quantity": 2}]}
    )
    res = client.get("/api/printings?name=Sol Ring").json()
    assert [p["set"] for p in res["printings"]] == ["otj", "c21", "lea"]
    assert all(
        p["owned_qty"] == 0 and p["owned_foil_qty"] == 0 for p in res["printings"]
    )
    assert res["card_owned"] is True
    assert res["card_owned_qty"] == 2


def test_printings_unowned_card_envelope():
    client, _ = _client()
    res = client.get("/api/printings?name=Sol Ring").json()
    assert res["card_owned"] is False
    assert res["card_owned_qty"] == 0


def test_etched_finish_counts_as_foil_in_printing_detail():
    # A flat parse_deck-style entry with finish "etched" lands in the foil bucket.
    idx = collection.printing_index(
        {
            "cards": [
                {
                    "name": "Sol Ring",
                    "quantity": 2,
                    "set": "otj",
                    "collector_number": "451",
                    "finish": "etched",
                }
            ]
        }
    )
    assert idx["sol ring"][("otj", "451")] == (0, 2)


# --------------------------------------------- card-level vs printing-level tri-state


def test_owned_printing_tristate_on_deck_cards():
    client, state = _client()
    engine.set_collection(state, "paper", DETAILED_PILE)
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    client.post("/api/deck/add", json={"name": "Cultivate"})

    # Default (cheapest = LEA) printing is owned at printing level.
    snap = client.get("/api/snapshot").json()
    by = {c["name"]: c for c in snap["deck"]["cards"]}
    assert by["Sol Ring"]["owned"] is True
    assert by["Sol Ring"]["owned_printing"] is True
    # Cultivate is owned name-only: detail unknown → tri-state field absent.
    assert by["Cultivate"]["owned"] is True
    assert "owned_printing" not in by["Cultivate"]

    # Pin the unowned OTJ printing: card stays owned, printing does not.
    snap = client.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-otj"}
    ).json()
    card = next(c for c in snap["deck"]["cards"] if c["name"] == "Sol Ring")
    assert card["owned"] is True
    assert card["owned_printing"] is False

    # Pin the owned (foil) C21 printing: printing-level owned again.
    snap = client.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-c21"}
    ).json()
    card = next(c for c in snap["deck"]["cards"] if c["name"] == "Sol Ring")
    assert card["owned_printing"] is True


def test_no_collection_means_no_ownership_fields_at_all():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    card = client.get("/api/snapshot").json()["deck"]["cards"][0]
    assert "owned" not in card
    assert "owned_printing" not in card


# ------------------------------------------------------------ backward compatibility


def test_old_format_collection_json_loads_name_only(tmp_path):
    # A collection.json saved before printing-awareness (plain name+quantity rows)
    # must load fine: name-level ownership works, no printing marks anywhere.
    from mtg_utils._deck_forge.production import _load_collections

    store = CollectionStore(tmp_path / "collection.json")
    store.save({"paper": {"cards": [{"name": "Sol Ring", "quantity": 2}]}})
    collections, index = _load_collections(store)
    printings = {
        slot: collection.printing_index(pile) for slot, pile in collections.items()
    }
    assert printings == {"paper": {}}  # no detail — and no crash

    state = _state()
    state.collections = collections
    state.collection_index = index
    state.collection_printings = printings
    client = TestClient(build_app(state))
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    card = client.get("/api/snapshot").json()["deck"]["cards"][0]
    assert card["owned"] is True
    assert card["owned_qty"] == 2
    assert "owned_printing" not in card  # name-only ownership: tri-state absent


def test_collection_import_aggregates_parse_deck_printing_keys():
    # A Moxfield-style paste with set/collector/finish feeds the printing detail.
    client, state = _client()
    client.post(
        "/api/collection/import",
        json={"text": "3 Sol Ring (LEA) 1\n", "slot": "paper"},
    )
    detail = engine.owned_printing_detail(state, "Sol Ring")
    assert detail == {("lea", "1"): (3, 0)}


# ----------------------------------------------------------------- deck import pinning


def test_deck_import_auto_pins_set_collector_and_stores_finish():
    client, state = _client()
    text = "1 Sol Ring (C21) 263 *F*\n1 Cultivate\n"
    data = client.post(
        "/api/builds/import", json={"text": text, "format": "commander"}
    ).json()
    card = next(c for c in data["deck"]["cards"] if c["name"] == "Sol Ring")
    assert card["printing_id"] == "id-c21"
    assert card["finish"] == "foil"
    assert state.session.printing_of("Sol Ring") == "id-c21"
    assert state.session.finish_of("Sol Ring") == "foil"
    # Cultivate carried no suffix → unpinned.
    cultivate = next(c for c in data["deck"]["cards"] if c["name"] == "Cultivate")
    assert "printing_id" not in cultivate


def test_deck_import_leaves_unresolvable_pairs_unpinned():
    client, state = _client()
    data = client.post(
        "/api/builds/import",
        json={"text": "1 Sol Ring (XYZ) 999\n", "format": "commander"},
    ).json()
    card = data["deck"]["cards"][0]
    assert "printing_id" not in card  # cheapest default, no error
    assert state.session.printing_of("Sol Ring") is None


def test_deck_import_drops_a_finish_the_printing_does_not_offer():
    client, state = _client()
    # LEA has no foil finish: the pin resolves, the invalid finish is dropped.
    client.post(
        "/api/builds/import",
        json={"text": "1 Sol Ring (LEA) 1 *F*\n", "format": "commander"},
    )
    assert state.session.printing_of("Sol Ring") == "id-lea"
    assert state.session.finish_of("Sol Ring") is None


# ------------------------------------------------------- finish on /api/deck/printing


def test_set_printing_accepts_a_valid_finish_and_shows_foil_price():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    snap = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "foil"},
    ).json()
    card = snap["deck"]["cards"][0]
    assert card["finish"] == "foil"
    assert card["prices"]["usd"] == "9.00"  # usd_foil drives the display price
    assert card["prices"]["usd_foil"] == "9.00"  # original keys kept (additive)


def test_set_printing_finish_falls_back_to_usd_when_finish_price_missing():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    snap = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-otj", "finish": "etched"},
    ).json()
    card = snap["deck"]["cards"][0]
    assert card["finish"] == "etched"
    assert card["prices"]["usd"] == "4.00"  # no usd_etched on the record → usd


def test_set_printing_rejects_a_finish_the_printing_lacks():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    r = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-lea", "finish": "foil"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "etched"},
    )
    assert r.status_code == 400
    r = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "shiny"},
    )
    assert r.status_code == 400


def test_set_printing_finish_requires_a_printing():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    r = client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": None, "finish": "foil"},
    )
    assert r.status_code == 400


def test_repinning_without_finish_clears_it():
    client, state = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "foil"},
    )
    assert state.session.finish_of("Sol Ring") == "foil"
    snap = client.post(
        "/api/deck/printing", json={"name": "Sol Ring", "printing_id": "id-c21"}
    ).json()
    assert state.session.finish_of("Sol Ring") is None
    assert "finish" not in snap["deck"]["cards"][0]
    assert snap["deck"]["cards"][0]["prices"]["usd"] == "5.00"  # nonfoil price again


def test_clearing_the_printing_clears_the_finish_too():
    client, state = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "foil"},
    )
    client.post("/api/deck/printing", json={"name": "Sol Ring", "printing_id": None})
    assert state.session.printing_of("Sol Ring") is None
    assert state.session.finish_of("Sol Ring") is None


def test_finish_round_trips_through_session_persistence():
    session = DeckSession("commander")
    session.add("Sol Ring")
    session.set_printing("Sol Ring", "id-c21", finish="foil")
    rebuilt = DeckSession.from_deck_dict(session.to_deck_dict())
    assert rebuilt.printing_of("Sol Ring") == "id-c21"
    assert rebuilt.finish_of("Sol Ring") == "foil"


# ------------------------------------------------------------------- export round-trip


def test_export_emits_finish_marker_and_round_trips():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-c21", "finish": "foil"},
    )
    text = client.get("/api/export?fmt=moxfield").json()["text"]
    assert "1 Sol Ring (C21) 263 *F*" in text

    # The exported text parses back to the same printing keys parse_deck emits…
    parsed = parse_deck_text(text, format="commander")
    entry = parsed["cards"][0]
    assert (entry["set"], entry["collector_number"], entry["finish"]) == (
        "c21",
        "263",
        "foil",
    )

    # …and importing it into a fresh hub re-pins the same printing + finish.
    client2, state2 = _client()
    client2.post("/api/builds/import", json={"text": text, "format": "commander"})
    assert state2.session.printing_of("Sol Ring") == "id-c21"
    assert state2.session.finish_of("Sol Ring") == "foil"


def test_export_etched_marker():
    client, _ = _client()
    client.post("/api/deck/add", json={"name": "Sol Ring"})
    client.post(
        "/api/deck/printing",
        json={"name": "Sol Ring", "printing_id": "id-otj", "finish": "etched"},
    )
    text = client.get("/api/export?fmt=moxfield").json()["text"]
    assert "1 Sol Ring (OTJ) 451 *E*" in text
