"""Partner color widening through the LIVE routes (#3, ADR-0019). test_ranking covers the
sort math in isolation; this covers the wiring: engine.avenues flags the partner avenue
``widening: True`` and /api/find threads the deck's identity in as ``widening_base`` so the
broadest color-openers surface first."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

PARTNER_ORACLE = "Partner (You can have two commanders if both have partner.)"


def _legend(name, ci, oracle):
    return {
        "name": name,
        "type_line": "Legendary Creature — Human",
        "cmc": 3.0,
        "color_identity": ci,
        "oracle_text": oracle,
        "mana_cost": "{2}{W}",
        "prices": {"usd": "1"},
        "legalities": {"commander": "legal"},
        "keywords": [],
        "power": "3",
        "toughness": "3",
    }


# A mono-white commander with a plain partner ability → the Partner / Background avenue.
PAIR_LORD = _legend("Pair Lord", ["W"], PARTNER_ORACLE)
# Two legal partners the (faked) search returns: a 4-color opener and a mono-white one.
WIDE = _legend("Wide Partner", ["U", "B", "R", "G"], PARTNER_ORACLE)
MONO = _legend("Mono Partner", ["W"], PARTNER_ORACLE)


def _state():
    session = DeckSession("commander")
    session.add("Pair Lord", zone="commanders")
    return ForgeState(
        by_name={c["name"]: c for c in (PAIR_LORD, WIDE, MONO)},
        search_fn=lambda **_: [WIDE, MONO],
        session=session,
        bulk_available=True,
    )


def test_partner_avenue_is_flagged_for_widening():
    snap = TestClient(build_app(_state())).get("/api/snapshot").json()
    partner = [a for a in snap["avenues"] if a.get("widening")]
    assert len(partner) == 1
    assert partner[0]["label"] == "Partner / Background"


def test_find_sorts_partners_by_color_widening_first():
    client = TestClient(build_app(_state()))
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
