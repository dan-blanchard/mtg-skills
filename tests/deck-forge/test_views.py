"""Direct tests for the wire-serialization seam (views.py) — no TestClient.

These pin the four card-view shapes the SPA consumes, all built on one ``project``.
"""

from mtg_utils._deck_forge import views
from mtg_utils._deck_forge.state import DeckSession, ForgeState

ATRAXA = {
    "name": "Atraxa, Praetors' Voice",
    "type_line": "Legendary Creature — Phyrexian Angel Horror",
    "cmc": 4.0,
    "color_identity": ["W", "U", "B", "G"],
    "oracle_text": "Flying, vigilance, deathtouch, lifelink",
}
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "cmc": 0.0,
    "color_identity": ["G"],
    "oracle_text": "({T}: Add {G}.)",
    "layout": "normal",
}


def test_project_is_atomic_with_commander_and_layout():
    p = views.project(ATRAXA, "commander")
    assert p["can_be_commander"] is True  # legendary creature
    assert "layout" in p
    assert "name" not in p  # the projection carries neither name…
    assert "quantity" not in p  # …nor quantity


def test_card_view_known_and_unknown_branches():
    by_name = {"Forest": FOREST}
    known = views.card_view("Forest", 10, by_name, "commander")
    assert known["quantity"] == 10
    assert known["unknown"] is False
    assert known["type_line"] == "Basic Land — Forest"
    unknown = views.card_view("Mystery Card", 1, by_name, "commander")
    assert unknown == {"name": "Mystery Card", "quantity": 1, "unknown": True}


def test_result_view_is_name_plus_projection_no_score():
    v = views.result_view(ATRAXA, "commander")
    assert v["name"] == "Atraxa, Praetors' Voice"
    assert "score" not in v
    assert "quantity" not in v
    assert v["cmc"] == 4.0


def test_candidate_view_carries_score():
    v = views.candidate_view({"card": ATRAXA, "score": {"synergy_fit": 3}}, "commander")
    assert v["name"] == "Atraxa, Praetors' Voice"
    assert v["score"] == {"synergy_fit": 3}
    assert "quantity" not in v


def test_combo_card_view_known_and_unknown():
    known = views.combo_card_view("Forest", FOREST, in_deck=True, fmt="commander")
    assert known["in_deck"] is True
    assert known["type_line"] == "Basic Land — Forest"
    unknown = views.combo_card_view("Mystery", None, in_deck=False, fmt="commander")
    assert unknown == {"name": "Mystery", "in_deck": False}


def test_deck_view_shape():
    session = DeckSession("commander")
    session.add("Atraxa, Praetors' Voice", zone="commanders")
    session.add("Forest", 10)
    state = ForgeState(
        by_name={"Atraxa, Praetors' Voice": ATRAXA, "Forest": FOREST},
        search_fn=lambda **_: [],
        session=session,
    )
    dv = views.deck_view(state)
    assert dv["format"] == "commander"
    assert dv["commanders"][0]["name"] == "Atraxa, Praetors' Voice"
    assert dv["cards"][0]["quantity"] == 10
    assert dv["sideboard"] == []
