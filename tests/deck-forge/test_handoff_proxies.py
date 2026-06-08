"""Run-here handoff (#6, ADR-0016): POST /api/handoff/proxies renders a printable proxy
PDF IN-PROCESS (reportlab, no API key) and returns it as a download — so "Print proxies"
works in the browser with no Claude session attached."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _card(name, type_line, *, cmc=2.0, cost="{1}{G}", pt=None):
    rec = {
        "name": name,
        "type_line": type_line,
        "cmc": cmc,
        "mana_cost": cost,
        "color_identity": ["G"],
        "oracle_text": f"{name} does a thing.",
        "keywords": [],
    }
    if pt:
        rec["power"], rec["toughness"] = pt
    return rec


IDX = {
    "Verdant Lord": _card(
        "Verdant Lord",
        "Legendary Creature — Elf",
        cmc=4,
        cost="{2}{G}{G}",
        pt=("4", "4"),
    ),
    "Grizzly Bears": _card("Grizzly Bears", "Creature — Bear", pt=("2", "2")),
    "Giant Growth": _card("Giant Growth", "Instant", cmc=1, cost="{G}"),
    "Forest": {
        "name": "Forest",
        "type_line": "Basic Land — Forest",
        "cmc": 0.0,
        "mana_cost": "",
        "color_identity": [],
        "oracle_text": "",
        "keywords": [],
    },
}


def _client(*, empty=False):
    session = DeckSession("commander")
    if not empty:
        session.add("Verdant Lord", zone="commanders")
        session.add("Grizzly Bears")
        session.add("Giant Growth")
        session.add("Forest", 5)
    state = ForgeState(
        by_name=IDX, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    return TestClient(build_app(state))


def test_proxies_returns_a_pdf_download():
    r = _client().post("/api/handoff/proxies")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_proxies_empty_deck_is_a_clean_error():
    r = _client(empty=True).post("/api/handoff/proxies")
    assert r.status_code == 400
