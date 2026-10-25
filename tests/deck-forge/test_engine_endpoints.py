"""Endpoint tests for the M2 deterministic engine (signals/budgets/packages/combos)."""

from fastapi.testclient import TestClient

from mtg_utils._card_ir import compat_lookup as _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import _seed_trees, test_card, test_card_ir

# ADR-0039 task #80 step 6: extract_signals is now crosswalk-only, so an
# engine-level test needs a resolvable concept tree (the concept-tree resolver), not just a
# synthetic Card IR (the compat-Card resolver) — a bare oracle_id/Card mapping alone silently
# produces no signal now.


def _wire_ir(monkeypatch, mapping: dict):
    """Wire a {oracle_id: Card} IR index (the compat-Card resolver) into the
    engine for the test. A REAL card's trees come from its snapshot phase
    records, which the caller pre-seeds via ``mtg_utils.testkit``."""
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: mapping)


def _real_deck_client(monkeypatch, commander: str, *cards: str) -> TestClient:
    """A deck of REAL snapshot cards (ADR-0056): each card's trees memo seeded
    from the committed snapshot's phase records (``_seed_trees``), the way
    :func:`_jyoti_client` builds Jyoti's."""
    names = (commander, *cards)
    irs = {}
    for name in names:
        _seed_trees(name)
        ir = test_card_ir(name)
        irs[ir.oracle_id] = ir
    _wire_ir(monkeypatch, irs)
    session = DeckSession("commander")
    session.add(commander, zone="commanders")
    for name in cards:
        session.add(name)
    state = ForgeState(
        by_name={n: {**test_card(n), "prices": {"usd": "1.00"}} for n in names},
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    return TestClient(build_app(state))


#: A real artifacts deck: Galazeth Prismari's grant to the artifacts you
#: control and Steel Overseer's counters on them (artifacts_matter, CR 301).
_ARTIFACT_DECK = ("Galazeth Prismari", "Steel Overseer")


CMD = {
    "name": "ETB Boss",
    "type_line": "Legendary Creature — Elf",
    "cmc": 4.0,
    "color_identity": ["G", "W"],
    "oracle_text": "Whenever an artifact you control enters, draw a card.",
    "prices": {"usd": "5.00"},
    "oracle_id": "etb-boss-oid",
}
TOK = {
    "name": "Token Maker",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "color_identity": ["W"],
    "oracle_text": "Create three 1/1 Soldier creature tokens.",
    "prices": {"usd": "0.50"},
}
ALREADY = {
    "name": "In Deck Tokens",
    "type_line": "Sorcery",
    "cmc": 2.0,
    "color_identity": ["G"],
    "oracle_text": "Create two 1/1 creature tokens.",
    "prices": {"usd": "1.00"},
}
INDEX = {c["name"]: c for c in (CMD, TOK, ALREADY)}


def _client(*, search_results=None, combos_fn=None, bulk=True):
    session = DeckSession("commander")
    session.add("ETB Boss", zone="commanders")
    session.add("In Deck Tokens")
    state = ForgeState(
        by_name=INDEX,
        search_fn=lambda **_: list(search_results or []),
        session=session,
        bulk_available=bulk,
        combos_fn=combos_fn,
    )
    return TestClient(build_app(state))


def test_signals_endpoint_surfaces_scoped_actionable_signal(monkeypatch):
    sigs = (
        _real_deck_client(monkeypatch, *_ARTIFACT_DECK)
        .get("/api/signals")
        .json()["signals"]
    )
    etb = next(s for s in sigs if s["key"] == "artifacts_matter")
    assert etb["scope"] == "you"
    assert etb["actionable"] is True
    assert "Artifacts" in etb["label"]


def test_presets_endpoint_lists_discoverable_presets():
    presets = _client().get("/api/presets").json()["presets"]
    assert len(presets) > 20
    names = {p["name"] for p in presets}
    assert {"tokens", "blink", "ramp"} & names  # a few well-known ones present
    assert all(p["description"] for p in presets)
    # sorted by name for stable UI ordering
    assert [p["name"] for p in presets] == sorted(names)


def test_budgets_endpoint_returns_template_bands():
    budgets = _client().get("/api/budgets").json()["budgets"]
    # ADR-0041: "lands" is now the fixture commander's deck-specific band
    # (ETB Boss: 2 colors G/W, CMC 4, 0 ramp → Burgess 37, Karsten 42), not
    # the static Command Zone 36-38 — the other roles stay on the flat band.
    assert budgets["lands"]["min"] == 37
    assert budgets["lands"]["max"] == 42
    assert budgets["ramp"]["min"] == 10
    assert budgets["ramp"]["max"] == 12
    # `interaction` replaces `removal` (counterspells fold in, ADR-0024).
    assert "interaction" in budgets
    assert "removal" not in budgets


def test_combos_endpoint_uses_injected_fn():
    def fake(_deck):
        return {"combos": [{"cards": ["A", "B"]}], "near_misses": []}

    data = _client(combos_fn=fake).get("/api/combos").json()
    assert data["combos"][0]["cards"] == ["A", "B"]


def test_combos_endpoint_graceful_without_fn():
    data = _client(combos_fn=None).get("/api/combos").json()
    assert data["combos"] == []
    assert "error" in data


def test_combos_endpoint_enriches_card_views():
    def fake(_deck):
        return {"combos": [{"cards": ["ETB Boss", "Token Maker"]}], "near_misses": []}

    data = _client(combos_fn=fake).get("/api/combos").json()
    views = {v["name"]: v for v in data["combos"][0]["card_views"]}
    assert views["ETB Boss"]["in_deck"] is True  # the commander
    assert views["Token Maker"]["in_deck"] is False
    assert "type_line" in views["ETB Boss"]  # hydrated like search/synergies tiles


def test_snapshot_includes_bracket_estimate():
    snap = _client().get("/api/snapshot").json()
    assert snap["bracket"]["bracket"] == 2  # no game changers / MLD in the fixture
    assert snap["bracket"]["name"] == "Core"


def test_snapshot_includes_live_budgets_and_signals(monkeypatch):
    snap = _real_deck_client(monkeypatch, *_ARTIFACT_DECK).get("/api/snapshot").json()
    assert snap["budgets"]["ramp"]["max"] == 12
    assert any(s["key"] == "artifacts_matter" for s in snap["signals"])


def test_snapshot_avenues_include_engine_avenue_with_search_spec(monkeypatch):
    snap = _real_deck_client(monkeypatch, *_ARTIFACT_DECK).get("/api/snapshot").json()
    avs = {a["id"]: a for a in snap["avenues"]}
    etb = avs["engine:artifacts_matter:you"]
    assert etb["source"] == "engine"
    assert etb["label"]
    # ADR-0026: the payoff avenue of an ident serve carries no pattern and no card
    # type — it pages by the serve it carries (the lanes' idents); the artifacts
    # themselves are the Source avenue's card-type fetch.
    assert "oracle" not in etb["search"]
    assert "card_type" not in etb["search"]
    assert "artifacts_matter|you|*" in etb["serve"]["signal_idents"]
    assert "types" not in etb["serve"]
    src = avs["engine:artifacts_matter:you:src"]
    assert src["label"] == "Artifacts (pieces)"
    assert list(src["search"]["card_type"]) == ["artifact"]


def test_add_agent_avenue_appears_in_snapshot():
    client = _client()
    snap = client.post(
        "/api/avenues",
        json={"label": "Flicker my own ETBs", "search": {"oracle": "exile .* return"}},
    ).json()
    agent_avenues = [a for a in snap["avenues"] if a["source"] == "agent"]
    assert agent_avenues[0]["label"] == "Flicker my own ETBs"
    assert agent_avenues[0]["id"] == "agent:1"


def test_agent_avenue_can_be_removed():
    client = _client()
    snap = client.post(
        "/api/avenues",
        json={"label": "Too broad", "search": {"oracle": "create .*Plant"}},
    ).json()
    rid = next(a["id"] for a in snap["avenues"] if a["source"] == "agent")
    after = client.delete(f"/api/avenues/{rid}").json()
    assert all(a["id"] != rid for a in after["avenues"])


# ADR-0027 / #25: land_creatures_matter is IR-served. Jyoti is a REAL card whose
# real projected IR makes a Land+Creature token and anthems land creatures, so the
# engine reads the real Card IR (joined by the real oracle_id) — no hand-built mirror.
# The real record comes from the snapshot by name; only its price is overlaid.
JYOTI = {**test_card("Jyoti, Moag Ancient"), "prices": {"usd": "0.21"}}


def _jyoti_client(monkeypatch):
    jyoti_ir = test_card_ir("Jyoti, Moag Ancient")
    # ADR-0039 task #80 step 6: Jyoti's real land_creatures_matter / token_maker
    # signals need REAL typed units (a synthetic zero-unit tree produces
    # nothing for a card this structurally rich) — pre-seed the trees memo
    # from the committed snapshot's stored phase records (the same mechanism
    # `mtg_utils.testkit.test_signals` uses), keyed by Jyoti's real oracle_id,
    # so the engine's own (real, unmonkeypatched) trees_for finds it.
    _seed_trees("Jyoti, Moag Ancient")
    _wire_ir(monkeypatch, {jyoti_ir.oracle_id: jyoti_ir})
    session = DeckSession("commander")
    session.add("Jyoti, Moag Ancient", zone="commanders")
    state = ForgeState(
        by_name={"Jyoti, Moag Ancient": JYOTI},
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    return TestClient(build_app(state))


def test_avenues_deduped_when_same_spec_via_two_scopes(monkeypatch):
    """Two cards both opening the Artifacts avenue (Galazeth Prismari's grant,
    Steel Overseer's counters) must resolve to one spec and not produce
    duplicate identically-labeled avenues."""
    client = _real_deck_client(monkeypatch, *_ARTIFACT_DECK)
    avenues = client.get("/api/snapshot").json()["avenues"]
    labels = [a["label"] for a in avenues]
    assert labels.count("Artifacts") == 1, labels
    assert len(labels) == len(set(labels)), labels


def test_jyoti_yields_multiple_precise_avenues_not_just_go_wide(monkeypatch):
    """The reported bug: a land-creatures commander surfaced only 'Go wide'. The
    engine must now offer several avenues, including the land-creatures theme, each
    carrying a precise (typed and/or phrased) search.

    ADR-0038 W6 endgame: token_maker's promotion off the residual legacy-fallback
    path re-ranks this single-card synthetic deck's tied signals (every signal here
    shares the SAME support count and confidence, so ``rank_deck_signals``'s stable
    sort falls through to insertion order, which shifts with token_maker's
    residual/ported routing — a benign tie-break artifact of this test's minimal
    setup, not a real-deck effect; verified the underlying signal SET is byte-
    identical either way). Jyoti's own token IS a Dryad LAND creature, so
    ``token_maker``'s "Dryad tokens"/"Dryad payoffs" avenues are the PRECISE
    engine-derived name for the same land-creatures theme the generic label used to
    carry — accept either phrasing rather than pinning to insertion order."""
    avenues = _jyoti_client(monkeypatch).get("/api/snapshot").json()["avenues"]
    labels = [a["label"] for a in avenues]
    assert len(avenues) >= 3, labels
    # The defining theme is surfaced — not collapsed into generic go-wide.
    assert any(
        ("land" in label.lower() and "creature" in label.lower())
        or "dryad" in label.lower()
        for label in labels
    ), labels
    assert not all(label == "Go-wide anthems" for label in labels), labels
    # At least one avenue is precisely typed (a card type or a serve it pages
    # by), proving precision is owned by the engine rather than hand-rolled.
    assert any(a["search"].get("card_type") or a.get("serve") for a in avenues), avenues
    # Engine avenues remain explorable with a stable id.
    assert all(a["id"] for a in avenues)
