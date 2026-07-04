"""Partner color widening through the LIVE routes (#3, ADR-0019). test_ranking covers the
sort math in isolation; this covers the wiring: engine.avenues flags the partner avenue
``widening: True`` and /api/find threads the deck's identity in as ``widening_base`` so the
broadest color-openers surface first."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face

PARTNER_ORACLE = "Partner (You can have two commanders if both have partner.)"


def _legend(name, ci, oracle):
    return {
        "name": name,
        # ADR-0027 t2b4a-B: partner_background is IR-served from the Scryfall `Partner`
        # keyword array (the record's keywords + a non-None IR routes the hybrid to the
        # IR path), so the partner fixtures carry the keyword + an oracle_id.
        "oracle_id": f"oid-{name.lower().replace(' ', '-')}",
        "type_line": "Legendary Creature — Human",
        "cmc": 3.0,
        "color_identity": ci,
        "oracle_text": oracle,
        "mana_cost": "{2}{W}",
        "prices": {"usd": "1"},
        "legalities": {"commander": "legal"},
        "keywords": ["Partner"],
        "power": "3",
        "toughness": "3",
    }


# A mono-white commander with a plain partner ability → the Partner / Background avenue.
PAIR_LORD = _legend("Pair Lord", ["W"], PARTNER_ORACLE)
# Two legal partners the (faked) search returns: a 4-color opener and a mono-white one.
WIDE = _legend("Wide Partner", ["U", "B", "R", "G"], PARTNER_ORACLE)
MONO = _legend("Mono Partner", ["W"], PARTNER_ORACLE)


def _bare_ir(oid: str) -> Card:
    return Card(oracle_id=oid, name=oid, faces=(Face(name=oid, abilities=()),))


def _client(monkeypatch):
    # Wire a non-None IR per fixture oracle_id so the hybrid path serves the migrated
    # partner_background key (it reads the record's `keywords`, but needs ir is not None
    # to take the IR arm). ADR-0027 hybrid dispatch, joined by oracle_id.
    ir_index = {
        c["oracle_id"]: _bare_ir(c["oracle_id"]) for c in (PAIR_LORD, WIDE, MONO)
    }
    # ADR-0035 Stage-4: the crosswalk flag defaults ON → ir_for reads the crosswalk
    # index first; wire BOTH so the synthetic IR resolves regardless of the flag.
    monkeypatch.setattr(_ir_lookup, "_index", lambda: ir_index)
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: ir_index)
    session = DeckSession("commander")
    session.add("Pair Lord", zone="commanders")
    state = ForgeState(
        by_name={c["name"]: c for c in (PAIR_LORD, WIDE, MONO)},
        search_fn=lambda **_: [WIDE, MONO],
        session=session,
        bulk_available=True,
    )
    return TestClient(build_app(state))


def test_partner_avenue_is_flagged_for_widening(monkeypatch):
    snap = _client(monkeypatch).get("/api/snapshot").json()
    partner = [a for a in snap["avenues"] if a.get("widening")]
    assert len(partner) == 1
    assert partner[0]["label"] == "Partner / Background"


def test_find_sorts_partners_by_color_widening_first(monkeypatch):
    client = _client(monkeypatch)
    snap = client.get("/api/snapshot").json()
    partner_id = next(a["id"] for a in snap["avenues"] if a.get("widening"))
    client.post(f"/api/avenues/{partner_id}/focus")

    res = client.post("/api/find", json={"limit": 25}).json()["results"]
    names = [c["name"] for c in res]
    # The 4-color opener (widens W → WUBRG, +4) outranks the mono-white partner (+0),
    # proving the deck identity flowed in as widening_base on the live route.
    assert names[0] == "Wide Partner"
    by_res = {c["name"]: c for c in res}
    assert by_res["Wide Partner"]["score"]["color_widening"] == 4
    assert by_res["Mono Partner"]["score"]["color_widening"] == 0
