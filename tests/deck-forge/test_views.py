"""Direct tests for the wire-serialization seam (views.py) — no TestClient.

These pin the four card-view shapes the SPA consumes, all built on one ``project``.
"""

from mtg_utils._deck_forge import views
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.formats import FORMATS
from mtg_utils.testkit import test_card

ATRAXA = test_card("Atraxa, Praetors' Voice")
FOREST = test_card("Forest")
# A transform DFC (Saga -> creature): the top-level mana_cost is absent and
# oracle_text empty — both live on card_faces, with the back face costless.
# Fictional: the test is about the face-folding shape, not any real card.
TEST_SAGA_DFC = {
    "name": "Test Saga // Test Saga Lord",
    "layout": "transform",
    "cmc": 6.0,
    "color_identity": ["B", "R"],
    "card_faces": [
        {
            "name": "Test Saga",
            "mana_cost": "{4}{B}{B}",
            "type_line": "Enchantment — Saga",
            "oracle_text": "Draw a card.",
        },
        {
            "name": "Test Saga Lord",
            "mana_cost": "",
            "type_line": "Legendary Creature — Human Noble",
            "oracle_text": "Haste",
        },
    ],
}


def test_project_folds_dfc_mana_cost_and_oracle_from_faces():
    p = views.project(TEST_SAGA_DFC, FORMATS["commander"])
    # front-face cost surfaces (back face is costless), not the empty/absent top level
    assert p["mana_cost"] == "{4}{B}{B}"
    # both faces' oracle text folds in (was blank for DFCs before)
    assert "Draw a card." in p["oracle_text"]
    assert "Haste" in p["oracle_text"]


def test_project_is_atomic_with_commander_and_layout():
    p = views.project(ATRAXA, FORMATS["commander"])
    assert p["can_be_commander"] is True  # legendary creature
    assert "layout" in p
    assert "name" not in p  # the projection carries neither name…
    assert "quantity" not in p  # …nor quantity


def test_card_view_known_and_unknown_branches():
    by_name = {"Forest": FOREST}
    known = views.card_view("Forest", 10, by_name, FORMATS["commander"])
    assert known["quantity"] == 10
    assert known["unknown"] is False
    assert known["type_line"] == "Basic Land — Forest"
    unknown = views.card_view("Mystery Card", 1, by_name, FORMATS["commander"])
    assert unknown == {"name": "Mystery Card", "quantity": 1, "unknown": True}


def test_result_view_is_name_plus_projection_no_score():
    v = views.result_view(ATRAXA, FORMATS["commander"])
    assert v["name"] == "Atraxa, Praetors' Voice"
    assert "score" not in v
    assert "quantity" not in v
    assert v["cmc"] == 4.0


def test_candidate_view_carries_score():
    v = views.candidate_view(
        {"card": ATRAXA, "score": {"synergy_fit": 3}}, FORMATS["commander"]
    )
    assert v["name"] == "Atraxa, Praetors' Voice"
    assert v["score"] == {"synergy_fit": 3}
    assert "quantity" not in v


def test_combo_card_view_known_and_unknown():
    known = views.combo_card_view(
        "Forest", FOREST, in_deck=True, fmt=FORMATS["commander"]
    )
    assert known["in_deck"] is True
    assert known["type_line"] == "Basic Land — Forest"
    unknown = views.combo_card_view(
        "Mystery", None, in_deck=False, fmt=FORMATS["commander"]
    )
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


# --- Pre-release badging ---------------------------------------------------------
# ``project`` takes the flag from the caller (an ORACLE-level set) rather than reading
# the record's own released_at, because search dedups to the CHEAPEST printing — which
# for a reprint can itself be future-dated. These pin that contract.

# An unreleased card can't be in the snapshot, so this one is fictional.
PRE_RELEASE = {
    "name": "Unreleased Test Card",
    "type_line": "Legendary Creature — Halfling Citizen",
    "cmc": 2.0,
    "color_identity": ["W"],
    "oracle_text": "Whenever a token you control enters, you gain 1 life.",
    "oracle_id": "oid-pre",
    "released_at": "2026-08-14",
}
# A legal reprint whose cheapest printing happens to be in a future set — the exact
# shape that a naive `released_at > today` badge would mislabel.
FUTURE_REPRINT = {**test_card("Settle the Wreckage"), "released_at": "2026-08-14"}


def test_project_omits_the_badge_by_default():
    assert "unreleased" not in views.project(PRE_RELEASE, FORMATS["commander"])


def test_project_badges_when_told():
    view = views.project(PRE_RELEASE, FORMATS["commander"], unreleased=True)
    assert view["unreleased"] is True
    assert view["released_at"] == "2026-08-14"


def test_future_dated_reprint_is_not_badged():
    # Future released_at, but the caller's oracle-level set says it's legal today.
    assert "unreleased" not in views.project(FUTURE_REPRINT, FORMATS["commander"])


def test_card_view_badges_from_the_oracle_id_set():
    by_name = {
        "Unreleased Test Card": PRE_RELEASE,
        "Settle the Wreckage": FUTURE_REPRINT,
    }
    pre = views.card_view(
        "Unreleased Test Card",
        1,
        by_name,
        FORMATS["commander"],
        unreleased_ids=frozenset({"oid-pre"}),
    )
    reprint = views.card_view(
        "Settle the Wreckage",
        1,
        by_name,
        FORMATS["commander"],
        unreleased_ids=frozenset({"oid-pre"}),
    )
    assert pre["unreleased"] is True
    assert "unreleased" not in reprint


def test_card_view_defaults_to_no_badge():
    by_name = {"Unreleased Test Card": PRE_RELEASE}
    view = views.card_view("Unreleased Test Card", 1, by_name, FORMATS["commander"])
    assert "unreleased" not in view
