"""Commander discovery (#2, ADR-0018): intent-ranked owned commanders from the active
Collection slot — Support depth (breadth-down-weighted owned support) or Novelty (signal
rarity, hard-gated by support). Never EDHREC popularity."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtg_utils import theme_presets
from mtg_utils._analysis.signal_specs import Serve
from mtg_utils._card_ir import compat_lookup as _ir_lookup
from mtg_utils._card_ir import trees
from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import discovery, engine
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face
from mtg_utils.deck import split_type_line


def _oid(name):
    return name.lower().replace(" ", "-").replace(",", "")


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
        "oracle_id": _oid(name),
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
        "oracle_id": _oid(name),
    }


LIFELORD = _cmd("Lifelord", ["W"], "Whenever you gain life, put a +1/+1 counter on it.")
# ADR-0039 task #80 step 6: Tokenlord's lane is a Saproling tribal anthem (own-subtype
# type_matters), not an ETB-token payoff (creature_etb) — creature_etb needs a REAL
# typed trigger unit the text-only synthetic trees below cannot provide (no phase
# record exists for a made-up card), while type_matters fires from a whole-card
# text mirror + the membership floor with zero units. The TOK_SUP token-makers below
# open the SAME type_matters(Saproling) lane via their own token-maker cross-open, so
# the support linkage this suite tests is unaffected — only the SPECIFIC mechanic
# demonstrating it changed.
TOKENLORD = _cmd(
    "Tokenlord",
    ["G"],
    "Other Saproling creatures you control get +1/+1.",
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
# ADR-0027 β: lifegain_matters migrated to the Card IR (a structural arm + a byte-
# identical kept-mirror that reads the record's reminder-stripped oracle), so the hybrid
# serves it ONLY from the IR path. Lifelord's "Whenever you gain life" lane (and the
# "You gain 3 life" support its lifegain serve credits) depend on it, so wire a bare Card
# per synthetic oracle_id — the mirror reads the oracle off the record, so the IR need
# carry no abilities. This mirrors production (real commanders carry real IR).
_BARE_IR_INDEX = {
    c["oracle_id"]: Card(
        oracle_id=c["oracle_id"], name=c["name"], faces=(Face(name=c["name"]),)
    )
    for c in ALL
}


def _text_only_tree(card: dict) -> ConceptTree:
    """A zero-unit ``ConceptTree`` carrying only the synthetic card's own
    whole-card metadata (types/subtypes/cmc/oracle text) — the SAME shape
    ``_ir_lookup``'s own W2c phase-missing-face synthesis produces. No typed
    substrate exists for a hand-built fixture (there is no real phase
    record), but the crosswalk's membership floor + its "b12" whole-card
    text mirrors (e.g. lifegain_matters' reminder-stripped-oracle mirror)
    read ``tree.oracle`` / ``tree.card_types`` / ``tree.card_subtypes``
    directly — no units needed (ADR-0039 task #80 step 6: verified against
    the production ``extract_crosswalk_signals`` + ``apply_membership_floor``
    call for exactly this shape)."""
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


_TREES_BY_OID = {c["oracle_id"]: (_text_only_tree(c),) for c in ALL}


@pytest.fixture(autouse=True)
def _wire_bare_ir(monkeypatch):
    # ir_for (ADR-0039 task #80 step 6: crosswalk-only, no flag branch) reads
    # the crosswalk index.
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: _BARE_IR_INDEX)
    # trees_for (the concept-tree resolver — extract_signals's ONLY signal source, task #80
    # step 6) needs a resolvable concept tree per synthetic oracle_id; these
    # fixtures have no real phase record to resolve, so wire the text-only
    # trees built above.
    monkeypatch.setattr(
        trees,
        "trees_for",
        lambda card, bulk=None, **_kw: _TREES_BY_OID.get(  # noqa: ARG005
            card.get("oracle_id") or "", ()
        ),
    )


def _pile(cards):
    return {"cards": [{"name": c["name"], "quantity": 1} for c in cards]}


def _state(fmt="commander", *, bulk=None, pile=PILE):
    state = ForgeState(
        by_name=BY_NAME,
        search_fn=lambda **_: [],
        session=DeckSession(fmt),
        bulk_available=True,
        bulk_path=bulk,
    )
    engine.set_collection(state, "paper", pile)
    return state


@pytest.fixture
def sidecar_dir(tmp_path, monkeypatch):
    """Redirect the discovery sidecars (``sha_keyed_path`` writes under ``$TMPDIR``)
    into a per-test directory, so a test can see exactly which files a pass wrote."""
    out = tmp_path / "sidecars"
    out.mkdir()
    monkeypatch.setenv("TMPDIR", str(out))
    return out


@pytest.fixture
def bulk(tmp_path):
    path = tmp_path / "bulk.json"
    path.write_text("[]", encoding="utf-8")
    return path


@pytest.fixture
def scans(monkeypatch):
    """Counts every ``Serve.matches`` call — the unit of work BOTH discovery sweeps
    are made of (the pool-wide lane-density scan and the collection served-name
    scan). Zero new calls across a pass means the pass recomputed nothing."""
    calls: list = []
    real = Serve.matches

    def counting(self, card):
        calls.append(card.get("name"))
        return real(self, card)

    monkeypatch.setattr(Serve, "matches", counting)
    return calls


def _density_files(sidecar_dir):
    return sorted(sidecar_dir.glob("deck-forge-lane-density-*.json"))


def _served_files(sidecar_dir):
    return sorted(sidecar_dir.glob("deck-forge-served-*.json"))


def _support(state):
    rows = discovery.discover_commanders(state, sort="support")
    return {r["name"]: (r["support_depth"], r["lanes"]) for r in rows}


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


def test_support_is_collection_specific_not_lane_width(monkeypatch):
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
            "oracle_id": _oid(name),
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
    # ADR-0027: type_matters / artifacts_matter migrated → hybrid path. The discovery
    # endpoint resolves each card's IR via ``compat_lookup.ir_for``; these locally-built cards
    # aren't in the module _BARE_IR_INDEX / _TREES_BY_OID, so wire a bare Card per
    # oracle_id (the compat-Card resolver) plus a text-only tree per oracle_id (the concept-tree resolver — ADR-0039 task
    # #80 step 6: extract_signals's ONLY signal source) so their tribal/artifact
    # lanes fire.
    local_ir = {
        c["oracle_id"]: Card(
            oracle_id=c["oracle_id"], name=c["name"], faces=(Face(name=c["name"]),)
        )
        for c in by_name.values()
    }
    local_trees = {c["oracle_id"]: (_text_only_tree(c),) for c in by_name.values()}
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: local_ir)
    monkeypatch.setattr(
        trees,
        "trees_for",
        lambda card, bulk=None, **_kw: local_trees.get(  # noqa: ARG005
            card.get("oracle_id") or "", ()
        ),
    )
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


def test_a_changed_collection_never_serves_the_old_collections_names():
    """Discovery caches the set of owned names serving each lane (so support is a set
    intersection, not a per-commander scan). A changed collection must never read the
    previous collection's sets — else newly-owned support is invisible.

    Goes empty→full: a stale (empty) served set would intersect to 0 even after the
    lifegain cards are added, so a passing assert proves the old sets weren't read."""
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
    # 2. add the eight lifegain enablers; discovery must now see them.
    full_text = "1 Lifelord\n1 Tokenlord\n" + "\n".join(
        f"1 Life Gift {i}" for i in range(8)
    )
    client.post("/api/collection/import", json={"slot": "paper", "text": full_text})
    full = client.post("/api/commanders/discover", json={"sort": "support"}).json()
    lifelord = next(r for r in full["results"] if r["name"] == "Lifelord")
    assert lifelord["support_depth"] > 0  # a stale empty set would keep this 0
    assert any(lane["label"] == "Lifegain" for lane in lifelord["lanes"])
    # 3. …and back: clearing the slot drops the support again.
    client.post("/api/collection/clear", json={"slot": "paper"})
    gone = client.post("/api/commanders/discover", json={"sort": "support"}).json()
    assert gone["results"] == []


def test_a_warm_for_a_replaced_collection_cannot_poison_the_new_one(monkeypatch):
    """The race the content-keyed cache closes: a background warm starts for
    collection A, the user imports collection B into the SAME slot mid-warm, and the
    warm keeps running. Keyed by slot, the warm re-created the slot's cache with A's
    served names AFTER B's import had invalidated it, and B's discovery read them.
    Keyed by the collection's own content, A's warm fills A's entry and B reads B's.

    A = the commanders alone (every lane's served set is EMPTY); B adds the eight
    lifegain enablers — so reading A's sets for B would report no support."""
    bare = _pile([LIFELORD, TOKENLORD])
    state = _state(pile=bare)
    real_lanes = discovery._commander_lanes
    imported: list = []

    def lanes_then_reimport(record):
        if not imported:  # mid-warm: the user imports B into the same slot
            imported.append(True)
            engine.set_collection(state, "paper", PILE)
        return real_lanes(record)

    monkeypatch.setattr(discovery, "_commander_lanes", lanes_then_reimport)
    discovery.warm(state, "paper")  # started for A; finishes after B landed
    assert imported

    depth, lanes = _support(state)["Lifelord"]
    assert depth > 0
    assert {"label": "Lifegain", "owned": 8} in lanes
    # …and it is exactly what a state that only ever saw B reports.
    assert _support(state) == _support(_state())


def test_warm_and_discover_share_the_cache_across_threads():
    """Discovery runs in the threadpool while a post-import warm runs as a background
    task: both fill the same ``DiscoveryCache`` from worker threads."""
    expected = _support(_state())
    state = _state()
    out: list = []
    errors: list = []

    def run(fn):
        try:
            out.append(fn())
        except Exception as exc:  # noqa: BLE001 — the assertion is "no thread raised"
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(lambda: discovery.warm(state, "paper"),)),
        *(
            threading.Thread(target=run, args=(lambda: _support(state),))
            for _ in range(3)
        ),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors
    assert [r for r in out if r is not None] == [expected] * 3


def test_lane_density_persists_to_a_bulk_keyed_sidecar(tmp_path, sidecar_dir, bulk):
    """The format-relative lane densities (the ~55s first-discovery sweep) persist to a
    sidecar keyed by the bulk file, so a fresh state reuses them instead of recomputing —
    and a different bulk (a download-mtgjson refresh) transparently starts fresh."""
    first = _support(_state(bulk=bulk))  # computes the densities, saves the sidecar
    assert len(_density_files(sidecar_dir)) == 1

    # A DIFFERENT bulk file → a different sidecar key → nothing stale is read: the
    # sweep runs again and writes its own sidecar beside the first.
    other = tmp_path / "other.json"
    other.write_text("[ ]", encoding="utf-8")
    assert _support(_state(bulk=other)) == first
    assert len(_density_files(sidecar_dir)) == 2


def test_a_fresh_state_on_the_same_bulk_and_collection_recomputes_nothing(
    sidecar_dir, bulk, scans
):
    """A server restart: both caches seed from their sidecars, so the second state's
    discovery runs no lane scan at all — and ranks identically."""
    first = _support(_state(bulk=bulk))
    assert scans  # the cold pass did scan
    assert len(_density_files(sidecar_dir)) == 1
    assert len(_served_files(sidecar_dir)) == 1

    scans.clear()
    assert _support(_state(bulk=bulk)) == first
    assert scans == []


def test_without_a_bulk_nothing_is_persisted(sidecar_dir):
    _support(_state())  # bulk_path=None → in-memory caches only
    assert list(sidecar_dir.iterdir()) == []


def test_warm_persists_both_caches_so_discover_computes_nothing_new(
    sidecar_dir, bulk, scans
):
    """Importing a collection warms BOTH sidecars in the background, so the user never
    pays the cold discovery cost: after ``warm`` the discover on the same state, and on
    a fresh one, scans nothing."""
    state = _state(bulk=bulk)
    discovery.warm(state, "paper")
    assert len(_density_files(sidecar_dir)) == 1
    assert len(_served_files(sidecar_dir)) == 1

    scans.clear()
    warmed = _support(state)
    assert scans == []
    assert _support(_state(bulk=bulk)) == warmed
    assert scans == []
    assert warmed["Lifelord"][0] > 0


def test_served_sets_are_content_addressed_per_collection(sidecar_dir, bulk, scans):
    """The served-name sidecar keys by the collection's exact owned-name set, so
    several collections each stay warm and none reads another's."""
    full = _state(bulk=bulk)
    discovery.warm(full, "paper")
    bare = _state(bulk=bulk, pile=_pile([LIFELORD, TOKENLORD]))
    discovery.warm(bare, "paper")
    assert len(_served_files(sidecar_dir)) == 2  # one per distinct collection
    assert len(_density_files(sidecar_dir)) == 1  # the pool-wide one is shared

    scans.clear()
    assert _support(_state(bulk=bulk))["Lifelord"][0] > 0
    assert _support(_state(bulk=bulk, pile=_pile([LIFELORD, TOKENLORD])))[
        "Lifelord"
    ] == (0, [])
    assert scans == []  # both collections were warm


def test_warm_targets_the_named_slot_not_the_active_one(sidecar_dir, bulk):
    # A paper build importing its ARENA collection warms the arena slot's cards.
    state = _state(bulk=bulk, pile={"cards": []})
    engine.set_collection(state, "arena", PILE)
    assert state.active_slot == "paper"
    discovery.warm(state, "arena")
    assert len(_served_files(sidecar_dir)) == 1


def test_warm_is_a_noop_for_an_empty_slot(sidecar_dir, bulk):
    discovery.warm(_state(bulk=bulk, pile={"cards": []}), "paper")
    assert list(sidecar_dir.iterdir()) == []


@pytest.mark.usefixtures("sidecar_dir")
def test_warm_seeds_signal_key_index(bulk, monkeypatch):
    # Verified-review Fix 6: a whole-pool sweep's tribal Serve.signal_idents
    # arm (task #96) pays a LIVE extract_signals call per cold card
    # (~34.6k cards in production, ~141s measured for one lane) unless the
    # ident memo is seeded from the persisted signals-index sidecar FIRST.
    # warm's lane-density scan walks the whole density pool, so it must seed
    # before scanning.
    calls: list = []
    monkeypatch.setattr(
        theme_presets,
        "seed_signal_key_index",
        lambda p: calls.append(p) or False,
    )
    discovery.warm(_state(bulk=bulk), "paper")
    assert calls == [bulk]


@pytest.mark.usefixtures("sidecar_dir")
def test_discover_commanders_seeds_signal_key_index(bulk, monkeypatch):
    # Same whole-pool-sweep gap as warm: discover_commanders is the FOREGROUND
    # path (called directly on every discover, not just after a collection
    # import), so it needs the same seed.
    calls: list = []
    monkeypatch.setattr(
        theme_presets,
        "seed_signal_key_index",
        lambda p: calls.append(p) or False,
    )
    discovery.discover_commanders(_state(bulk=bulk), sort="support")
    assert calls == [bulk]


def test_only_the_commander_eligible_owned_cards_are_ranked():
    found = discovery.discover_commanders(_state(), limit=99)
    assert {r["name"] for r in found} == {"Lifelord", "Tokenlord", "Vanilla Vance"}


def test_unknown_theme_returns_400_not_500():
    # An unknown preset name is a clean 400 (like the slot/format guards), not an
    # opaque 500 from theme_presets.matches raising KeyError.
    r = _client().post(
        "/api/commanders/discover", json={"theme": "not_a_real_preset_xyz"}
    )
    assert r.status_code == 400


# ── Verified-review F8: discovery sidecars invalidate on serve changes ───────
def test_discovery_sidecars_key_on_serve_definitions(
    sidecar_dir, bulk, scans, monkeypatch
):
    # A warm lane-density / served-names sidecar computed under OLD serve
    # definitions must not survive a serve change (the B-1/B-6 serve fixes
    # were silently suppressed for warm deployments). The sidecar key folds
    # in a serve-definition fingerprint: under a changed fingerprint a fresh
    # state reads neither warm sidecar — it rescans and writes its own pair.
    # (The fingerprint hashes ~40 source files, so the one way to "change a
    # serve" in a test is to swap the private fingerprint function.)
    discovery.warm(_state(bulk=bulk), "paper")
    assert len(_density_files(sidecar_dir)) == 1
    assert len(_served_files(sidecar_dir)) == 1

    monkeypatch.setattr(discovery, "_serve_fingerprint", lambda: "different")
    scans.clear()
    _support(_state(bulk=bulk))
    assert scans  # nothing warm was read
    assert len(_density_files(sidecar_dir)) == 2
    assert len(_served_files(sidecar_dir)) == 2


# ── task #90: the Novelty rarity table reads the persisted signals index ─────
# The table is only ever observable through a novelty SCORE's arithmetic, and the
# public sort also live-extracts the ranked commander's own signals, so "the pool
# sweep did not live-compute" can't be told apart through ``discover_commanders``.
# These three reach ``discovery._signal_freq`` directly. (The file's other private
# reaches are monkeypatches, not reads: ``_commander_lanes`` as the race test's
# mid-warm hook, ``_serve_fingerprint`` to simulate a serve change, and the module's
# ``extract_signals`` to count live extractions.)


def _commander_state(bulk_path=None):
    commander_rec = {
        "name": "Fake Commander",
        "type_line": "Legendary Creature — Human",
        "cmc": 2.0,
        "color_identity": ["G"],
        "oracle_text": "",
        "legalities": {"commander": "legal"},
        "oracle_id": "oid-fake-cmd",
    }
    return ForgeState(
        by_name={"Fake Commander": commander_rec},
        search_fn=lambda **_: [],
        session=DeckSession("commander"),
        bulk_path=bulk_path,
    )


def _ramp_signal(rec, *_args, **_kwargs):
    from mtg_utils._analysis.signals import Signal

    return [Signal("ramp", "you", "", "", rec.get("name", ""), "high")]


def test_signal_freq_reads_persisted_index_without_live_compute(monkeypatch):
    st = _commander_state(bulk_path=Path("/fake/AllPrintings.json"))
    fake_index = {"oid-fake-cmd": ("ramp|you|",)}
    monkeypatch.setattr(
        "mtg_utils._analysis.signals_index.load_signals_index",
        lambda path: fake_index if path == st.bulk_path else None,
    )

    def boom(_rec, *_args, **_kwargs):
        raise AssertionError("must not live-compute when the sidecar covers this oid")

    monkeypatch.setattr(discovery, "extract_signals", boom)

    freq, total = discovery._signal_freq(st)
    assert total == 1
    assert freq == {("ramp", ""): 1}


def test_signal_freq_falls_back_to_live_compute_without_a_sidecar(monkeypatch):
    st = _commander_state(bulk_path=None)  # no bulk -> load_signals_index(None) -> None
    # discovery imports extract_signals by name at module load, so the patch target
    # is discovery's imported name, not signals.py's.
    monkeypatch.setattr(discovery, "extract_signals", _ramp_signal)

    freq, total = discovery._signal_freq(st)
    assert total == 1
    assert freq == {("ramp", ""): 1}


def test_signal_freq_is_swept_once_per_format(monkeypatch):
    st = _commander_state(bulk_path=None)
    calls = []

    def counting(rec, *args, **kwargs):
        calls.append(rec["name"])
        return _ramp_signal(rec, *args, **kwargs)

    monkeypatch.setattr(discovery, "extract_signals", counting)
    discovery._signal_freq(st)
    discovery._signal_freq(st)
    assert calls == ["Fake Commander"]  # second call served from the cache
