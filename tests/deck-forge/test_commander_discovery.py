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
    res = _client().post("/api/commanders/discover", json={"theme": "lifegain"}).json()
    assert [r["name"] for r in res["results"]] == ["Lifelord"]


def test_novelty_hard_gates_out_unsupported_commanders():
    res = _client().post("/api/commanders/discover", json={"sort": "novelty"}).json()
    names = {r["name"] for r in res["results"]}
    assert "Vanilla Vance" not in names  # 0 support → gated out
    assert names == {"Lifelord", "Tokenlord"}
    assert all("novelty" in r for r in res["results"])


def test_support_is_collection_specific_not_lane_width():
    """B3 / Q9: a commander you own deeply in a DISTINCTIVE lane (a niche tribe) outranks
    one whose lane is merely BROAD (artifacts — nearly every artifact 'supports' it). Both
    are owned to the same depth, so the old within-collection IDF tied them; the new
    format-relative weight (a rare lane is worth more per card) breaks the tie toward the
    distinctive collection — what the user actually cares about."""

    def _card(name, ci, type_line, oracle):
        return {
            "name": name,
            "type_line": type_line,
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

    art_cmd = _cmd("Artificer Prime", ["W"], "Artifacts you control get +1/+1.")
    scare_cmd = _cmd(
        "Scarecrow Lord",
        ["U"],
        "Other Scarecrow creatures you control get +1/+1.",
        subtype="Scarecrow",
    )
    # Equal owned depth: 6 cards feeding each commander's lane.
    art_owned = [_card(f"Trinket {i}", [], "Artifact", "") for i in range(6)]
    scare_owned = [
        _card(f"Husk {i}", ["U"], "Creature — Scarecrow", "") for i in range(6)
    ]
    # Filler keeps each commander's owned-in-identity total well above its lane count.
    w_fill = [_card(f"W Filler {i}", ["W"], "Creature — Human", "") for i in range(20)]
    u_fill = [
        _card(f"U Filler {i}", ["U"], "Creature — Merfolk", "") for i in range(20)
    ]
    # Pool-only artifacts (NOT owned): they make the artifacts lane BROAD in the format,
    # so each owned artifact is worth little; Scarecrows stay rare, so each is worth a lot.
    pad = [_card(f"Relic {i}", [], "Artifact", "") for i in range(20)]

    owned = [art_cmd, scare_cmd, *art_owned, *scare_owned, *w_fill, *u_fill]
    by_name = {c["name"]: c for c in [*owned, *pad]}
    state = ForgeState(
        by_name=by_name,
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_available=True,
    )
    engine.set_collection(
        state, "paper", {"cards": [{"name": c["name"], "quantity": 1} for c in owned]}
    )
    res = (
        TestClient(build_app(state))
        .post("/api/commanders/discover", json={"sort": "support"})
        .json()
    )
    order = [r["name"] for r in res["results"]]
    by = {r["name"]: r for r in res["results"]}
    assert order.index("Scarecrow Lord") < order.index("Artificer Prime")
    assert (
        by["Scarecrow Lord"]["support_depth"] > by["Artificer Prime"]["support_depth"]
    )


def test_collection_change_invalidates_the_lane_serve_cache():
    """Perf fix: discovery caches, per slot, the set of owned names serving each lane
    (so support is a set intersection, not a per-commander regex scan). That cache MUST
    be dropped when the slot's collection changes — else newly-owned support is invisible.

    Goes empty→full: a stale (empty) served set would intersect to 0 even after the
    lifegain cards are added, so a passing assert proves the cache was invalidated."""
    client = _client()
    # 1. paper slot = the two commanders only, no support → first discovery caches an
    #    (empty) served set for the lifegain lane.
    client.post(
        "/api/collection/import",
        json={"slot": "paper", "text": "1 Lifelord\n1 Tokenlord"},
    )
    bare = client.post("/api/commanders/discover", json={"sort": "support"}).json()
    assert (
        next(r for r in bare["results"] if r["name"] == "Lifelord")["support_depth"]
        == 0
    )
    # 2. add the eight lifegain enablers; discovery must now see them (cache invalidated).
    full_text = "1 Lifelord\n1 Tokenlord\n" + "\n".join(
        f"1 Life Gift {i}" for i in range(8)
    )
    client.post("/api/collection/import", json={"slot": "paper", "text": full_text})
    full = client.post("/api/commanders/discover", json={"sort": "support"}).json()
    lifelord = next(r for r in full["results"] if r["name"] == "Lifelord")
    assert lifelord["support_depth"] > 0  # stale empty cache would keep this 0
    assert any(lane["label"] == "Lifegain" for lane in lifelord["lanes"])


def test_lane_density_persists_to_a_bulk_keyed_sidecar(tmp_path):
    """The format-relative lane densities (the ~55s first-discovery sweep) persist to a
    sidecar keyed by the bulk file, so a fresh state reuses them instead of recomputing —
    and a different bulk (a download-bulk refresh) transparently starts fresh."""
    bulk = tmp_path / "bulk.json"
    bulk.write_text("[]", encoding="utf-8")

    # First discovery computes some densities and saves the sidecar.
    s1 = _state()
    s1.bulk_path = bulk
    TestClient(build_app(s1)).post("/api/commanders/discover", json={"sort": "support"})
    assert s1.lane_density  # densities were computed
    sidecar = engine._density_sidecar_path(s1)
    assert sidecar is not None
    assert sidecar.exists()

    # A fresh state on the SAME bulk seeds its densities from the sidecar (no recompute).
    s2 = _state()
    s2.bulk_path = bulk
    engine._load_lane_density(s2)
    assert s2.lane_density == s1.lane_density

    # A DIFFERENT bulk file → different sidecar key → no stale densities loaded.
    other = tmp_path / "other.json"
    other.write_text("[]", encoding="utf-8")
    s3 = _state()
    s3.bulk_path = other
    engine._load_lane_density(s3)
    assert s3.lane_density == {}


def test_unknown_theme_returns_400_not_500():
    # An unknown preset name is a clean 400 (like the slot/format guards), not an
    # opaque 500 from theme_presets.matches raising KeyError.
    r = _client().post(
        "/api/commanders/discover", json={"theme": "not_a_real_preset_xyz"}
    )
    assert r.status_code == 400
