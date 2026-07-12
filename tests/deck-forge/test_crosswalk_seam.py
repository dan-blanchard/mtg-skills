"""The crosswalk seam (ADR-0035) — the ONE serving path's resolvers + dispatch.

Renamed from ``test_crosswalk_cutover.py`` (ADR-0039 task #80 step 7): the
Stage-3a ``MTG_SKILLS_CROSSWALK_SIGNALS`` cutover flag, the legacy revert path
it gated (step 6), and the legacy ``project_card`` builder the old file still
baseline-compared against (step 7) are all GONE. ``extract_signals_hybrid`` has
exactly one serving path — ``trees_for`` resolves a card's per-face concept
trees, the ported crosswalk lanes run over each, and the membership floor runs
once at the merge level. These tests pin what remains true of that ONE path —
the ``ir_for`` / ``trees_for`` Seam-A/B resolvers, the hybrid's crosswalk-only
dispatch, the residual-empty key partition, and the DFC face-union. The
membership-floor behavior pins moved to ``test_signals_floor.py`` in the same
step (named for what they test). CI-safe: the concept trees come from the
committed ``crosswalk_fixture_cards.json`` phase records + the committed mirror
schema — no bulk / sidecar / phase / network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache

import pytest

from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._deck_forge import _ir_lookup as il
from mtg_utils._deck_forge._migrated_keys import MIGRATED_KEYS
from mtg_utils._deck_forge.crosswalk_signals import (
    PORTED_KEYS,
    extract_crosswalk_signals,
)
from mtg_utils._deck_forge.signals import (
    extract_signals_hybrid,
    producible_static_keys,
)
from mtg_utils.card_ir import Card, Face

FIXTURE = "crosswalk_fixture_cards.json"


def _returns(value: object) -> Callable[..., object]:
    """A monkeypatch stand-in that ignores its args and returns ``value``."""

    def _fn(*_args: object, **_kwargs: object) -> object:
        return value

    return _fn


@lru_cache(maxsize=1)
def _fixture_records() -> list[dict]:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return list(json.loads(path.read_text())["cards"].values())


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _tree_for_record(rec: dict):
    nm = rec.get("name") or ""
    root = strict_load_card(rec, _schema(), name=nm)
    return build_concept_tree(
        root, name=nm, oracle_id=rec.get("scryfall_oracle_id") or ""
    )


def _bulk(rec: dict) -> dict:
    """A minimal Scryfall-shaped record joined to a phase record by oracle_id."""
    return {
        "oracle_id": rec.get("scryfall_oracle_id") or "",
        "name": rec.get("name") or "",
        "oracle_text": rec.get("oracle_text") or "",
        "type_line": "Legendary Creature — Human",
        "keywords": [],
    }


@lru_cache(maxsize=1)
def _ported_case() -> tuple[dict, object, str]:
    """A fixture card whose crosswalk fires at least one PORTED key: return
    (bulk_record, concept_tree, one_ported_key)."""
    for rec in _fixture_records():
        oid = rec.get("scryfall_oracle_id")
        if not oid:
            continue
        try:
            tree = _tree_for_record(rec)
        except Exception:  # noqa: BLE001 — skip drift/odd cards in the search
            continue
        sigs = extract_crosswalk_signals(tree, keywords=frozenset())
        ported = [s.key for s in sigs if s.key in PORTED_KEYS]
        if ported:
            return _bulk(rec), tree, ported[0]
    pytest.skip("no PORTED-firing card found in fixture")


@pytest.fixture(autouse=True)
def _clean_caches():
    """Every test starts with the memoized indexes / trees memo cleared."""
    il.clear_caches()
    yield
    il.clear_caches()


# ── Seam B: ir_for ────────────────────────────────────────────────────────────


def test_ir_for_reads_the_crosswalk_index(monkeypatch):
    card = Card(oracle_id="o", name="X", faces=(Face(name="X", abilities=()),))
    monkeypatch.setattr(il, "_crosswalk_index", _returns({"o": card}))
    assert il.ir_for({"oracle_id": "o"}) is card


def test_ir_for_returns_none_when_crosswalk_sidecar_missing(monkeypatch):
    """ADR-0039 task #80 step 4: an unbuilt crosswalk sidecar degrades ``ir_for``
    to ``None`` — the same "nothing here" contract ``production.default_state``
    uses for a missing bulk file — NEVER a silent fall-through to a different
    builder's Card."""
    monkeypatch.setattr(il, "_crosswalk_index", _returns(None))  # unbuilt
    assert il.ir_for({"oracle_id": "o"}) is None


def test_ir_for_returns_none_without_oracle_id(monkeypatch):
    card = Card(oracle_id="o", name="X", faces=(Face(name="X", abilities=()),))
    monkeypatch.setattr(il, "_crosswalk_index", _returns({"o": card}))
    assert il.ir_for({"name": "no oid"}) is None


# ── Seam A: trees_for ─────────────────────────────────────────────────────────


def test_trees_for_degrades_without_phase_data(monkeypatch):
    monkeypatch.setattr(il, "_phase_record_index", _returns(None))
    assert il.trees_for({"oracle_id": "x"}) == ()


def test_trees_for_none_without_oracle_id():
    assert il.trees_for({"name": "no oid"}) == ()


def test_trees_for_builds_and_memoizes(monkeypatch):
    bulk, _tree, _key = _ported_case()
    oid = bulk["oracle_id"]
    # Feed the resolver our fixture record + schema directly.
    rec = next(r for r in _fixture_records() if r.get("scryfall_oracle_id") == oid)
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    got = il.trees_for(bulk)
    assert got != ()
    assert got[0].oracle_id == oid
    assert oid in il._TREES_MEMO  # memoized


# ── DFC face-union (ADR-0035/0038 task #74) ─────────────────────────────────
_AANG_OID = "b4872bac-5822-4c35-9b73-38c4e3ffa477"
_BEND_KEYS = frozenset(
    {"airbend_makers", "earthbend_matters", "waterbend_matters", "firebending_makers"}
)


def test_trees_for_returns_every_face_for_a_dfc(monkeypatch):
    """Avatar Aang // Aang, Master of Elements share one oracle_id across two phase
    records (a DFC); ``trees_for`` must return BOTH, not first-record-wins — the
    task #74 bug (a first-record-wins index dropped whichever face iterated second,
    silently starving any lane whose only node lives on that face)."""
    recs = tuple(
        r for r in _fixture_records() if r.get("scryfall_oracle_id") == _AANG_OID
    )
    assert len(recs) == 2, "fixture must carry both Avatar Aang faces"
    monkeypatch.setattr(il, "_phase_record_index", _returns({_AANG_OID: recs}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    trees = il.trees_for({"oracle_id": _AANG_OID})
    assert {t.name for t in trees} == {"Avatar Aang", "Aang, Master of Elements"}


# ── ADR-0038 W2c: text-only face trees ──────────────────────────────────────
# phase emits NO record at all for some multi-face halves (every aftermath
# second half corpus-wide, one two-face split gap — the refined census in
# ``_ir_lookup``'s module comment). ``trees_for`` fills that with one
# zero-unit ConceptTree per phase-missing face, built off the bulk (MTGJSON)
# record's own ``card_faces`` text, ONLY when the caller threads ``bulk=``.


def _synthetic_bulk(
    oid: str, first_name: str, first_oracle: str, *, second_face: dict | None
) -> dict:
    """A minimal two-face bulk record: face 0 matches the real phase record
    (``first_name`` / ``first_oracle``), face 1 is whatever the caller wants
    (a phase-missing face, or ``None`` to omit the second face entirely)."""
    faces = [
        {
            "name": first_name,
            "oracle_text": first_oracle,
            "type_line": "Creature — Goblin",
        }
    ]
    if second_face is not None:
        faces.append(second_face)
    return {
        "oracle_id": oid,
        "name": f"{first_name} // ???",
        "layout": "aftermath",
        "cmc": 3.0,
        "card_faces": faces,
    }


def test_text_only_tree_added_for_a_phase_missing_face(monkeypatch):
    """A bulk face with no name-matched phase record among the oid's group
    becomes an extra zero-unit ConceptTree carrying its own bulk oracle
    text, ONLY when the caller supplies ``bulk=``."""
    rec = next(
        r for r in _fixture_records() if r.get("name") == '"Name Sticker" Goblin'
    )
    oid = rec["scryfall_oracle_id"]
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    bulk = _synthetic_bulk(
        oid,
        '"Name Sticker" Goblin',
        rec["oracle_text"],
        second_face={
            "name": "Fabricated Ghost Face",
            "oracle_text": "Draw a card, then discard a card.",
            "type_line": "Sorcery",
            "mana_cost": "{1}{U}",
        },
    )

    # No ``bulk=`` → phase-record trees only (the pre-W2c shape, unchanged).
    trees_no_bulk = il.trees_for({"oracle_id": oid})
    assert {t.name for t in trees_no_bulk} == {'"Name Sticker" Goblin'}

    il.clear_caches()
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    trees = il.trees_for({"oracle_id": oid}, bulk=bulk)
    names = {t.name for t in trees}
    assert names == {'"Name Sticker" Goblin', "Fabricated Ghost Face"}
    ghost = next(t for t in trees if t.name == "Fabricated Ghost Face")
    assert ghost.units == ()  # no typed substrate — an honest empty
    assert ghost.oracle == "Draw a card, then discard a card."
    assert ghost.card_types == ("Sorcery",)
    assert ghost.cmc == 2  # {1}{U}
    assert ghost.has_printed_cost is True


def test_vanilla_single_face_bulk_yields_no_text_only_tree(monkeypatch):
    """A ``bulk`` record with no (or a single) ``card_faces`` entry never
    synthesizes a text-only tree — the ``len(faces) != 2`` gate."""
    rec = next(
        r for r in _fixture_records() if r.get("name") == '"Name Sticker" Goblin'
    )
    oid = rec["scryfall_oracle_id"]
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    vanilla_bulk = {"oracle_id": oid, "name": '"Name Sticker" Goblin', "cmc": 3.0}
    trees = il.trees_for({"oracle_id": oid}, bulk=vanilla_bulk)
    assert {t.name for t in trees} == {'"Name Sticker" Goblin'}


def test_empty_oracle_phase_missing_face_yields_no_tree(monkeypatch):
    """A phase-missing face with blank ``oracle_text`` carries nothing to
    read, so it is skipped rather than synthesizing an empty tree."""
    rec = next(
        r for r in _fixture_records() if r.get("name") == '"Name Sticker" Goblin'
    )
    oid = rec["scryfall_oracle_id"]
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    bulk = _synthetic_bulk(
        oid,
        '"Name Sticker" Goblin',
        rec["oracle_text"],
        second_face={"name": "Blank Face", "oracle_text": "", "type_line": "Land"},
    )
    trees = il.trees_for({"oracle_id": oid}, bulk=bulk)
    assert {t.name for t in trees} == {'"Name Sticker" Goblin'}


def test_three_way_split_excluded_from_text_only_synthesis(monkeypatch):
    """A 3+-face record (the Un-set funny-layout "Smelt // Herd // Saw"
    shape) is excluded outright — real tournament Magic never has more than
    two faces on a split/aftermath/adventure/transform/modal_dfc card, so
    ``len(card_faces) != 2`` is the defer-not-hack gate (see the module
    comment above ``_TEXT_ONLY_EXCLUDED_LAYOUTS`` in ``_ir_lookup``)."""
    rec = next(
        r for r in _fixture_records() if r.get("name") == '"Name Sticker" Goblin'
    )
    oid = rec["scryfall_oracle_id"]
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: (rec,)}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    bulk = {
        "oracle_id": oid,
        "name": '"Name Sticker" Goblin // B // C',
        "layout": "split",
        "cmc": 3.0,
        "card_faces": [
            {
                "name": '"Name Sticker" Goblin',
                "oracle_text": rec["oracle_text"],
                "type_line": "Creature — Goblin",
            },
            {"name": "B", "oracle_text": "Some effect.", "type_line": "Instant"},
            {"name": "C", "oracle_text": "Another effect.", "type_line": "Instant"},
        ],
    }
    trees = il.trees_for({"oracle_id": oid}, bulk=bulk)
    assert {t.name for t in trees} == {'"Name Sticker" Goblin'}


def test_avatar_aang_union_fires_all_four_bend_keys(monkeypatch):
    """The production seam (``extract_signals_hybrid``): Avatar Aang's
    ElementalBend / RegisterBending nodes live on the FRONT face only, but a
    first-record-wins tree resolver could pick the BACK face first (phase's own
    dict-key ordering sorts "aang, master of elements" before "avatar aang") and
    silently drop them. The union of both faces' trees must fire all three bend
    lanes plus the keyword-sourced firebending_makers — the whole card's bend
    profile, regardless of which face happened to be read first."""
    recs = tuple(
        r for r in _fixture_records() if r.get("scryfall_oracle_id") == _AANG_OID
    )
    bulk = {
        "oracle_id": _AANG_OID,
        "name": "Avatar Aang // Aang, Master of Elements",
        "oracle_text": "\n".join(r.get("oracle_text") or "" for r in recs),
        "type_line": "Legendary Creature — Human Avatar Ally",
        "keywords": ["Flying", "Firebending"],
    }
    monkeypatch.setattr(il, "_phase_record_index", _returns({_AANG_OID: recs}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    keys = {s.key for s in extract_signals_hybrid(bulk)}
    assert keys >= _BEND_KEYS


def test_avatar_aang_regression_no_fire_control(monkeypatch):
    """A no-bend card stays silent on all four keys through the same union path —
    the fix doesn't turn the bend lanes into a blanket floor."""
    bulk, tree, _key = _ported_case()
    if tree.oracle_id == _AANG_OID:
        pytest.skip("ported-case card is Avatar Aang itself")
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    keys = {s.key for s in extract_signals_hybrid(bulk)}
    assert not (_BEND_KEYS & keys)


# ── The hybrid's crosswalk-only dispatch ─────────────────────────────────────


def test_hybrid_serves_ported_from_crosswalk(monkeypatch):
    bulk, tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    on = {s.key for s in extract_signals_hybrid(bulk)}
    assert ported_key in on


def test_hybrid_no_signal_when_tree_unavailable(monkeypatch):
    """No trees (``trees_for`` → ``()``) means no crosswalk source and no
    fallback (ADR-0039 task #80 step 6: the legacy regex / Card-IR paths are
    gone) — a graceful empty answer for that lane, never a crash."""
    bulk, _tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns(()))
    on = {s.key for s in extract_signals_hybrid(bulk)}
    assert ported_key not in on


def test_hybrid_reconciliation_single_fire(monkeypatch):
    """No duplicate (key, scope, subject) survives the shared reconciliation tail,
    even though the crosswalk applies its own reconciliations before the merge."""
    bulk, tree, _key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    sigs = extract_signals_hybrid(bulk)
    idents = [(s.key, s.scope, s.subject) for s in sigs]
    assert len(idents) == len(set(idents))


def test_migrated_keys_residual_empty():
    """The key-partition invariant (ADR-0039 W8 finisher): ``MIGRATED_KEYS -
    PORTED_KEYS`` is EMPTY — every historically-migrated key graduated to a
    crosswalk-native lane. ``extract_signals_hybrid`` (signals.py) has no
    residual arm at all any more (task #80 step 6 deleted it); this test
    guards the key-level precondition that made that deletion safe — a
    future regression that shrinks ``PORTED_KEYS`` below ``MIGRATED_KEYS``
    would silently stop serving a key with no fallback, so it must trip
    here first."""
    residual = MIGRATED_KEYS - PORTED_KEYS
    assert residual == frozenset(), (
        "a migrated key regressed out of PORTED_KEYS with no legacy fallback "
        f"left to catch it: {sorted(residual)}"
    )
    assert MIGRATED_KEYS <= PORTED_KEYS


# ── producible-key gate ───────────────────────────────────────────────────────


def test_producible_includes_crosswalk_only_lanes():
    """The three PORTED-only maker lanes (never regex-producible) still resolve
    through the key-agreement gate."""
    keys = producible_static_keys()
    assert {"amass_makers", "copy_permanent", "incubate_makers"} <= keys


def test_gate_resolves_every_producible_key():
    """The import-time key-agreement gate passes — every crosswalk-produced key
    (incl. the 3 PORTED-only lanes) resolves to a serve/search spec."""
    from mtg_utils._deck_forge.signal_specs import (
        _assert_every_producible_key_resolves,
    )

    _assert_every_producible_key_resolves()  # raises AssertionError on an orphan
