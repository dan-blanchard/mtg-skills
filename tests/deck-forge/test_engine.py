"""Direct tests for the deck-forge engine seam (engine.py) — no TestClient.

The whole point of extracting the engine: its invariants (commander-only membership,
partner-slot scoping, the snapshot composition) are now testable through a plain
``ForgeState`` instead of only through ``TestClient(build_app(state)).get(...)``.
"""

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.state import DeckSession, ForgeState

ISHAI = {
    "name": "Ishai, Ojutai Dragonspeaker",
    "type_line": "Legendary Creature — Bird Monk",
    "cmc": 2.0,
    "color_identity": ["W", "U"],
    "oracle_text": "Flying\nPartner (You can have two commanders if both have partner.)",
    "legalities": {"commander": "legal"},
}
ATRAXA = {
    "name": "Atraxa, Praetors' Voice",
    "type_line": "Legendary Creature — Phyrexian Angel Horror",
    "cmc": 4.0,
    "color_identity": ["W", "U", "B", "G"],
    "oracle_text": "Flying, vigilance, deathtouch, lifelink",
    "legalities": {"commander": "legal"},
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "cmc": 0.0,
    "color_identity": ["G"],
    "oracle_text": "({T}: Add {G}.)",
}
INDEX = {c["name"]: c for c in (ISHAI, ATRAXA, FOREST)}


def _state(commanders=(), cards=()):
    session = DeckSession("commander")
    for c in commanders:
        session.add(c, 1, zone="commanders")
    for name, qty in cards:
        session.add(name, qty)
    return ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)


def test_hydrate_joins_session_to_records():
    st = _state(commanders=["Atraxa, Praetors' Voice"], cards=[("Forest", 10)])
    hd = engine.hydrate(st)
    assert {r["name"] for r in hd.records} == {"Atraxa, Praetors' Voice", "Forest"}


def test_deck_color_identity_is_sorted_union():
    st = _state(commanders=["Atraxa, Praetors' Voice"])
    assert engine.deck_color_identity(st) == "BGUW"


def test_partner_search_only_with_exactly_one_partner_commander():
    one = _state(commanders=["Ishai, Ojutai Dragonspeaker"])
    assert engine.partner_search(one) is not None
    two = _state(commanders=["Ishai, Ojutai Dragonspeaker", "Atraxa, Praetors' Voice"])
    assert engine.partner_search(two) is None  # slot filled
    assert engine.partner_search(_state()) is None  # no commander


def test_avenues_drop_partner_when_slot_full():
    two = _state(commanders=["Ishai, Ojutai Dragonspeaker", "Atraxa, Praetors' Voice"])
    labels = {a["label"] for a in engine.avenues(two, engine.hydrate(two).records)}
    assert "Partner / Background" not in labels


def test_avenues_append_agent_avenues():
    st = _state(commanders=["Atraxa, Praetors' Voice"])
    st.agent_avenues.append(
        {
            "id": "agent:1",
            "label": "Custom",
            "description": "",
            "scope": "",
            "source": "agent",
            "search": {},
        }
    )
    labels = [a["label"] for a in engine.avenues(st, engine.hydrate(st).records)]
    assert "Custom" in labels


def test_snapshot_composes_expected_keys():
    st = _state(commanders=["Atraxa, Praetors' Voice"], cards=[("Forest", 10)])
    snap = engine.snapshot(st)
    for key in (
        "build_id",
        "build_name",
        "deck",
        "stats",
        "bracket",
        "mana",
        "budgets",
        "signals",
        "avenues",
        "warnings",
    ):
        assert key in snap, key


def test_legality_warnings_flags_too_many_cards():
    # commander target is 100; 1 commander + 100 mainboard copies = 101 > 100.
    st = _state(commanders=["Atraxa, Praetors' Voice"], cards=[("Forest", 100)])
    warns = engine.legality_warnings(engine.hydrate(st), max_cards=st.session.deck_size)
    cats = {w["category"] for w in warns}
    assert "deck_maximum" in cats
    assert any("101" in w["message"] for w in warns)


def test_legality_warnings_flags_unimported_cards():
    # A deck name that resolves to no Scryfall record (typo / failed import) must fail
    # legality, not vanish silently.
    st = _state(
        commanders=["Atraxa, Praetors' Voice"],
        cards=[("Definitely Not A Real Card", 1)],
    )
    warns = engine.legality_warnings(engine.hydrate(st), max_cards=st.session.deck_size)
    cats = {w["category"] for w in warns}
    assert "unimported" in cats
    assert any("Definitely Not A Real Card" in w["message"] for w in warns)


def test_legality_warnings_clean_deck_has_no_size_or_import_warnings():
    st = _state(commanders=["Atraxa, Praetors' Voice"], cards=[("Forest", 10)])
    warns = engine.legality_warnings(engine.hydrate(st), max_cards=st.session.deck_size)
    cats = {w["category"] for w in warns}
    assert "deck_maximum" not in cats
    assert "unimported" not in cats


def test_explore_filters_respects_avenue_color_identity():
    # An avenue carrying its own color_identity (partner avenues -> WUBRG) overrides
    # the deck's identity; otherwise it falls back to the deck's.
    override = engine.explore_filters(
        {"oracle": "x", "color_identity": "WUBRG"}, color_identity="G", fmt="commander"
    )
    assert override["color_identity"] == "WUBRG"
    fallback = engine.explore_filters(
        {"oracle": "x"}, color_identity="G", fmt="commander"
    )
    assert fallback["color_identity"] == "G"
