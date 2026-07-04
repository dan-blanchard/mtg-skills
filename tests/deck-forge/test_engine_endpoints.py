"""Endpoint tests for the M2 deterministic engine (signals/budgets/packages/combos)."""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import _ir_lookup
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter
from mtg_utils.testkit import test_card_ir


def _wire_ir(monkeypatch, mapping: dict):
    """Wire a {oracle_id: Card} IR index into the engine for the test (ADR-0027:
    the hybrid path serves migrated keys — e.g. land_creatures_matter — only from the
    IR, joined by oracle_id, so an engine test for a migrated avenue must supply one).

    ADR-0035 Stage-4: the crosswalk flag defaults ON, so ``ir_for`` reads the
    crosswalk index first — wire BOTH indexes to the same mapping so a synthetic
    oracle_id resolves regardless of the flag."""
    monkeypatch.setattr(_ir_lookup, "_index", lambda: mapping)
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: mapping)


CMD = {
    "name": "ETB Boss",
    "type_line": "Legendary Creature — Elf",
    "cmc": 4.0,
    "color_identity": ["G", "W"],
    "oracle_text": "Whenever a creature you control enters, draw a card.",
    "prices": {"usd": "5.00"},
    "oracle_id": "etb-boss-oid",
}
# ADR-0027 β: creature_etb migrated to the Card IR (a byte-identical kept-mirror that
# reads the record's reminder-stripped oracle), so the hybrid serves it ONLY from the
# IR path. A bare Card joined by oracle_id routes the engine to the IR (the mirror then
# reads the oracle off the record), matching the land_creatures_matter precedent.
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
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR})
    sigs = _client().get("/api/signals").json()["signals"]
    etb = next(s for s in sigs if s["key"] == "creature_etb")
    assert etb["scope"] == "you"
    assert etb["actionable"] is True
    assert "Creatures entering" in etb["label"]


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
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR})
    snap = _client().get("/api/snapshot").json()
    assert snap["budgets"]["ramp"]["max"] == 12
    assert any(s["key"] == "creature_etb" for s in snap["signals"])


def test_snapshot_avenues_include_engine_avenue_with_search_spec(monkeypatch):
    _wire_ir(monkeypatch, {"etb-boss-oid": CMD_IR})
    snap = _client().get("/api/snapshot").json()
    etb = next(a for a in snap["avenues"] if a["id"] == "engine:creature_etb:you")
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


def _land_creature_anthem_ir(oid: str, name: str) -> Card:
    """A pump over a Land+Creature subject — the structural land_creatures_matter
    anthem the migrated IR path reads (ADR-0027)."""
    return Card(
        oracle_id=oid,
        name=name,
        faces=(
            Face(
                name=name,
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="pump",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature", "Land"), controller="you"
                                ),
                                raw="land creatures you control get +1/+1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_avenues_deduped_when_same_spec_via_two_scopes(monkeypatch):
    """Two cards both opening the Creature-lands avenue must resolve to one spec and
    not produce duplicate identically-labeled avenues. ADR-0027: land_creatures_matter
    is IR-served, so wire a structural anthem IR for each (joined by oracle_id)."""
    _wire_ir(
        monkeypatch,
        {
            "lord-a-oid": _land_creature_anthem_ir("lord-a-oid", "Lord A"),
            "lord-b-oid": _land_creature_anthem_ir("lord-b-oid", "Lord B"),
        },
    )
    session = DeckSession("commander")
    session.add("Lord A", zone="commanders")
    session.add("Lord B")
    index = {
        "Lord A": {
            "name": "Lord A",
            "type_line": "Legendary Creature",
            "color_identity": ["G"],
            "oracle_id": "lord-a-oid",
            "oracle_text": "Land creatures you control get +1/+1.",
            "prices": {"usd": "1"},
        },
        "Lord B": {
            "name": "Lord B",
            "type_line": "Creature",
            "color_identity": ["G"],
            "oracle_id": "lord-b-oid",
            "oracle_text": "Land creatures you control get +1/+0.",
            "prices": {"usd": "1"},
        },
    }
    state = ForgeState(
        by_name=index, search_fn=lambda **_: [], session=session, bulk_available=True
    )
    avenues = TestClient(build_app(state)).get("/api/snapshot").json()["avenues"]
    labels = [a["label"] for a in avenues]
    assert labels.count("Creature-lands") == 1, labels
    assert len(labels) == len(set(labels)), labels


def test_jyoti_yields_multiple_precise_avenues_not_just_go_wide(monkeypatch):
    """The reported bug: a land-creatures commander surfaced only 'Go wide'. The
    engine must now offer several avenues, including the land-creatures theme, each
    carrying a precise (typed and/or phrased) search."""
    avenues = _jyoti_client(monkeypatch).get("/api/snapshot").json()["avenues"]
    labels = [a["label"] for a in avenues]
    assert len(avenues) >= 3, labels
    # The defining theme is surfaced — not collapsed into generic go-wide.
    assert any(
        "land" in label.lower() and "creature" in label.lower() for label in labels
    ), labels
    # At least one avenue is precisely typed (card_type), proving precision is
    # owned by the engine rather than hand-rolled.
    assert any(a["search"].get("card_type") for a in avenues), avenues
    # Engine avenues remain explorable with a stable id.
    assert all(a["id"] for a in avenues)
