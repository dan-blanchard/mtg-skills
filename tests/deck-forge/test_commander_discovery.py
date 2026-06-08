"""Commander discovery (#2, ADR-0018): intent-ranked owned commanders from the active
Collection slot — Support depth (breadth-down-weighted owned support) or Novelty (signal
rarity, hard-gated by support). Never EDHREC popularity."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState


def _cmd(name, ci, oracle, subtype="Human"):
    return {
        "name": name,
        "type_line": f"Legendary Creature — {subtype}",
        "cmc": 3.0,
        "color_identity": ci,
        "oracle_text": oracle,
        "mana_cost": "{2}{G}",
        "prices": {"usd": "1"},
        "legalities": {"commander": "legal"},
        "keywords": [],
        "power": "3",
        "toughness": "3",
    }


def _sup(name, ci, oracle):
    return {
        "name": name,
        "type_line": "Creature — Spirit",
        "cmc": 2.0,
        "color_identity": ci,
        "oracle_text": oracle,
        "mana_cost": "{1}{G}",
        "prices": {"usd": "1"},
        "legalities": {"commander": "legal"},
        "keywords": [],
        "power": "1",
        "toughness": "1",
    }


LIFELORD = _cmd("Lifelord", ["W"], "Whenever you gain life, put a +1/+1 counter on it.")
TOKENLORD = _cmd(
    "Tokenlord",
    ["G"],
    "Whenever a creature token enters the battlefield under your control, draw a card.",
    subtype="Elf",
)
VANILLA = _cmd("Vanilla Vance", ["U"], "", subtype="Bird")  # no actionable lane

LIFE_SUP = [_sup(f"Life Gift {i}", ["W"], "You gain 3 life.") for i in range(8)]
TOK_SUP = [
    _sup(f"Token Spell {i}", ["G"], "Create a 1/1 green Saproling creature token.")
    for i in range(2)
]
# Filler keeps the breadth denominator > a lane's own-count, so the IDF weight is > 0.
W_FILLER = [_sup(f"Plains Walker {i}", ["W"], "") for i in range(4)]
G_FILLER = [_sup(f"Forest Friend {i}", ["G"], "") for i in range(3)]

ALL = [LIFELORD, TOKENLORD, VANILLA, *LIFE_SUP, *TOK_SUP, *W_FILLER, *G_FILLER]
BY_NAME = {c["name"]: c for c in ALL}
PILE = {"cards": [{"name": c["name"], "quantity": 1} for c in ALL]}


def _state(fmt="commander"):
    state = ForgeState(
        by_name=BY_NAME,
        search_fn=lambda **_: [],
        session=DeckSession(fmt),
        bulk_available=True,
    )
    engine.set_collection(state, "paper", PILE)
    return state


def _client():
    return TestClient(build_app(_state()))


def test_only_commander_eligible_owned_cards_are_surfaced():
    res = _client().post("/api/commanders/discover", json={"sort": "support"}).json()
    names = {r["name"] for r in res["results"]}
    assert names == {"Lifelord", "Tokenlord", "Vanilla Vance"}  # support cards excluded
    assert res["active_slot"] == "paper"


def test_support_sort_ranks_by_owned_support_not_lane_count():
    res = _client().post("/api/commanders/discover", json={"sort": "support"}).json()
    order = [r["name"] for r in res["results"]]
    # Lifelord (8 owned lifegain enablers) > Tokenlord (2) > Vanilla (0 support).
    assert order == ["Lifelord", "Tokenlord", "Vanilla Vance"]
    lifelord = res["results"][0]
    assert lifelord["support_depth"] > res["results"][1]["support_depth"] > 0
    assert lifelord["supported_lanes"] >= 1  # the lifegain lane clears the floor
    assert any(lane["label"] == "Lifegain" for lane in lifelord["lanes"])
    assert res["results"][-1]["support_depth"] == 0  # vanilla


def test_color_filter_narrows_the_pool():
    res = (
        _client()
        .post("/api/commanders/discover", json={"sort": "support", "colors": "W"})
        .json()
    )
    assert [r["name"] for r in res["results"]] == ["Lifelord"]


def test_theme_filter_keeps_only_matching_commanders():
    res = (
        _client()
        .post("/api/commanders/discover", json={"theme": "lifegain"})
        .json()
    )
    assert [r["name"] for r in res["results"]] == ["Lifelord"]


def test_novelty_hard_gates_out_unsupported_commanders():
    res = _client().post("/api/commanders/discover", json={"sort": "novelty"}).json()
    names = {r["name"] for r in res["results"]}
    assert "Vanilla Vance" not in names  # 0 support → gated out
    assert names == {"Lifelord", "Tokenlord"}
    assert all("novelty" in r for r in res["results"])


def test_unknown_theme_returns_400_not_500():
    # An unknown preset name is a clean 400 (like the slot/format guards), not an
    # opaque 500 from theme_presets.matches raising KeyError.
    r = _client().post(
        "/api/commanders/discover", json={"theme": "not_a_real_preset_xyz"}
    )
    assert r.status_code == 400
