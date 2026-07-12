"""Endpoint tests for the M2 deterministic engine (signals/budgets/packages/combos)."""

from fastapi.testclient import TestClient

from mtg_utils._card_ir.crosswalk import ConceptTree
from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Card, Face
from mtg_utils.deck import split_type_line
from mtg_utils.testkit import _seed_trees, test_card_ir

# ADR-0039 task #80 step 6: extract_signals_hybrid is now crosswalk-only, so an
# engine-level test needs a resolvable concept tree (Seam A), not just a
# synthetic Card IR (Seam B) — a bare oracle_id/Card mapping alone silently
# produces no signal now.


def _text_only_tree(card: dict) -> ConceptTree:
    """A zero-unit ``ConceptTree`` carrying only the synthetic card's own
    whole-card metadata — the shape ``_ir_lookup``'s own W2c phase-missing-face
    synthesis produces. Enough for the crosswalk's membership floor and its
    "b12" whole-card text mirrors (which read ``tree.oracle`` directly), but
    NOT for a genuinely structural lane that needs a real typed unit (a
    trigger/effect node) — those keys need a REAL card's tree (see
    ``_jyoti_client`` below, which seeds one from the committed snapshot via
    ``mtg_utils.testkit``)."""
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


def _wire_ir(monkeypatch, mapping: dict, cards: list[dict] = ()):
    """Wire a {oracle_id: Card} IR index (Seam B) plus a text-only tree per
    ``cards`` (Seam A) into the engine for the test. ``cards`` empty leaves
    ``trees_for`` untouched — for a REAL card (e.g. Jyoti below), the caller
    pre-seeds ``_ir_lookup``'s trees memo via ``mtg_utils.testkit`` instead,
    so a text-only (zero-unit) tree here would shadow the real one."""
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: mapping)
    if not cards:
        return
    trees = {c["oracle_id"]: (_text_only_tree(c),) for c in cards}
    monkeypatch.setattr(
        _ir_lookup,
        "trees_for",
        lambda card, bulk=None: trees.get(card.get("oracle_id") or "", ()),  # noqa: ARG005
    )


CMD = {
    "name": "ETB Boss",
    "type_line": "Legendary Creature — Elf",
    "cmc": 4.0,
    "color_identity": ["G", "W"],
    # ADR-0039 task #80 step 6: artifacts_matter (not creature_etb — a genuinely
    # structural lane needing a real typed trigger unit a synthetic text-only
    # tree can't supply) fires from the crosswalk's whole-card text mirror with
    # zero units, so it stays testable through a synthetic fixture. The label/
    # search-spec assertions below check "Artifacts" accordingly; the endpoint
    # plumbing under test (does a migrated key surface through /api/signals and
    # /api/snapshot avenues) is unaffected by which key demonstrates it.
    "oracle_text": "Whenever you cast an artifact spell, draw a card.",
    "prices": {"usd": "5.00"},
    "oracle_id": "etb-boss-oid",
}
CMD_IR = Card(oracle_id="etb-boss-oid", name="ETB Boss", faces=(Face(name="ETB Boss"),))
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
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR}, [CMD])
    sigs = _client().get("/api/signals").json()["signals"]
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
    assert budgets["lands"]["min"] == 36
    assert budgets["lands"]["max"] == 38
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
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR}, [CMD])
    snap = _client().get("/api/snapshot").json()
    assert snap["budgets"]["ramp"]["max"] == 12
    assert any(s["key"] == "artifacts_matter" for s in snap["signals"])


def test_snapshot_avenues_include_engine_avenue_with_search_spec(monkeypatch):
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR}, [CMD])
    snap = _client().get("/api/snapshot").json()
    etb = next(a for a in snap["avenues"] if a["id"] == "engine:artifacts_matter:you")
    assert etb["source"] == "engine"
    assert etb["label"]
    assert "oracle" in etb["search"]  # carries what to search for


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
# A rich Scryfall record (color_identity/cmc/prices the minimal snapshot drops) is
# layered over the real oracle_id so the engine sees both halves the way production does.
JYOTI = {
    "name": "Jyoti, Moag Ancient",
    "type_line": "Legendary Creature — Elemental",
    "cmc": 4.0,
    "color_identity": ["G", "U"],
    "oracle_text": (
        "When Jyoti enters, create a 1/1 green Forest Dryad land creature token for each time you've cast your commander from the command zone this game. (They're affected by summoning sickness.)\nAt the beginning of each combat, land creatures you control get +X/+X until end of turn, where X is Jyoti's power."
    ),
    "prices": {"usd": "0.21"},
}


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
    record = dict(JYOTI, oracle_id=jyoti_ir.oracle_id)
    session = DeckSession("commander")
    session.add("Jyoti, Moag Ancient", zone="commanders")
    state = ForgeState(
        by_name={"Jyoti, Moag Ancient": record},
        search_fn=lambda **_: [],
        session=session,
        bulk_available=True,
    )
    return TestClient(build_app(state))


def test_avenues_deduped_when_same_spec_via_two_scopes(monkeypatch):
    """Two cards both opening the Artifacts avenue must resolve to one spec and
    not produce duplicate identically-labeled avenues. ADR-0039 task #80 step 6:
    artifacts_matter fires from the crosswalk's whole-card text mirror with zero
    units, so a text-only tree per card (no structural anthem IR needed) is
    enough to exercise the dedup path."""
    lord_a = {
        "name": "Lord A",
        "type_line": "Legendary Creature",
        "color_identity": ["G"],
        "oracle_id": "lord-a-oid",
        "oracle_text": "Whenever you cast an artifact spell, draw a card.",
        "prices": {"usd": "1"},
    }
    lord_b = {
        "name": "Lord B",
        "type_line": "Creature",
        "color_identity": ["G"],
        "oracle_id": "lord-b-oid",
        "oracle_text": "Artifacts you control get +1/+0.",
        "prices": {"usd": "1"},
    }
    _wire_ir(monkeypatch, {}, [lord_a, lord_b])
    session = DeckSession("commander")
    session.add("Lord A", zone="commanders")
    session.add("Lord B")
    index = {"Lord A": lord_a, "Lord B": lord_b}
    state = ForgeState(
        by_name=index, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    avenues = TestClient(build_app(state)).get("/api/snapshot").json()["avenues"]
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
    # At least one avenue is precisely typed (card_type or a structured oracle
    # regex), proving precision is owned by the engine rather than hand-rolled.
    assert any(
        a["search"].get("card_type") or a["search"].get("oracle") for a in avenues
    ), avenues
    # Engine avenues remain explorable with a stable id.
    assert all(a["id"] for a in avenues)
