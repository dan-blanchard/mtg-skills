"""Partner color widening through the LIVE routes (#3, ADR-0019). test_ranking covers the
sort math in isolation; this covers the wiring: engine.avenues flags the partner avenue
``widening: True`` and /api/find threads the deck's identity in as ``widening_base`` so the
broadest color-openers surface first."""

from fastapi.testclient import TestClient

from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face
from mtg_utils.deck import split_type_line

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


def _text_only_tree(card: dict) -> ConceptTree:
    """A zero-unit ``ConceptTree`` carrying the synthetic card's own whole-card
    metadata — the shape ``_ir_lookup``'s own W2c phase-missing-face synthesis
    produces. partner_background is a keyword-field lookup (the Scryfall
    ``Partner`` keyword array, threaded separately as ``keywords`` — no typed
    substrate needed), so a zero-unit tree is enough (ADR-0039 task #80 step
    6: extract_signals_hybrid is now crosswalk-only, so these synthetic
    fixtures need a resolvable tree, not just a synthetic Card IR, to fire at
    all)."""
    type_words, sub_words = split_type_line(card.get("type_line") or "")
    return ConceptTree(
        name=card["name"],
        oracle_id=card["oracle_id"],
        units=(),
        card_types=tuple(w.capitalize() for w in type_words if w != "legendary"),
        card_subtypes=tuple(w.capitalize() for w in sub_words),
        card_supertypes=("Legendary",) if "legendary" in type_words else (),
        cmc=int(card.get("cmc") or 0),
        oracle=card.get("oracle_text") or "",
    )


def _client(monkeypatch):
    # Wire a non-None IR per fixture oracle_id (Seam B) plus a text-only tree
    # per oracle_id (Seam A — ADR-0039 task #80 step 6: extract_signals_hybrid's
    # ONLY signal source) so the crosswalk path serves the migrated
    # partner_background key.
    ir_index = {
        c["oracle_id"]: _bare_ir(c["oracle_id"]) for c in (PAIR_LORD, WIDE, MONO)
    }
    trees_index = {
        c["oracle_id"]: (_text_only_tree(c),) for c in (PAIR_LORD, WIDE, MONO)
    }
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: ir_index)
    monkeypatch.setattr(
        _ir_lookup,
        "trees_for",
        lambda card, bulk=None: trees_index.get(card.get("oracle_id") or "", ()),  # noqa: ARG005
    )
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
