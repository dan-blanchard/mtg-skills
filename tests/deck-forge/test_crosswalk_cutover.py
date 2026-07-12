"""ADR-0035 Stage-3a — the flag-gated crosswalk cutover (Steps 0-3).

The PRIME invariant lives in the existing suites: with the flag OFF (the default)
every other test passes UNCHANGED. These tests pin the *new* behavior — the flag
itself, the ``ir_for`` Seam-B switch, the ``trees_for`` resolver, and the hybrid's
three-way Seam-A dispatch — and prove flag-OFF isolation (the crosswalk path is
never consulted). CI-safe: the concept trees come from the committed
``crosswalk_fixture_cards.json`` phase records + the committed mirror schema, with
no bulk / sidecar / phase / network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache

import pytest

from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._card_ir.project import project_card
from mtg_utils._card_ir.tree_synthesis import has_structural_kill_engine
from mtg_utils._deck_forge import _ir_lookup as il
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._migrated_keys import MIGRATED_KEYS
from mtg_utils._deck_forge._signals_ir import (
    CLASS_TRIBES,
    _is_big_mana_ir,
    _is_kill_engine_ir,
    extract_signals_ir,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.crosswalk_signals import (
    PORTED_KEYS,
    _floor_token_maker_subjects,
    _is_big_mana_tree,
    extract_crosswalk_signals,
)
from mtg_utils._deck_forge.signals import (
    extract_signals_hybrid,
    producible_static_keys,
)
from mtg_utils.card_ir import Card, Face

FIXTURE = "crosswalk_fixture_cards.json"
FLAG = "MTG_SKILLS_CROSSWALK_SIGNALS"


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
def _clean_flag(monkeypatch):
    """Every test starts with the flag explicitly OFF and the memoized indexes
    cleared. ADR-0035 Stage-4 inverted the default to ON, so ``delenv`` no longer
    means OFF — each test that wants the legacy (revert) path sets ``"0"`` (here for
    the default, or explicitly in-test); the default-ON is pinned by
    ``test_flag_defaults_on``."""
    monkeypatch.setenv(FLAG, "0")
    il.clear_caches()
    yield
    il.clear_caches()


# ── Step 0: the flag ────────────────────────────────────────────────────────


def test_flag_defaults_on(monkeypatch):
    # ADR-0035 Stage-4 flip: unset ⇒ ON (the new default).
    monkeypatch.delenv(FLAG, raising=False)
    assert il.crosswalk_enabled() is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        # ADR-0035 Stage-4: empty / whitespace ⇒ ON (only the explicit negative
        # tokens above keep the legacy revert path).
        ("", True),
        ("   ", True),
    ],
)
def test_flag_parses_env(monkeypatch, value, expected):
    monkeypatch.setenv(FLAG, value)
    assert il.crosswalk_enabled() is expected


# ── flag-OFF isolation (the prime-invariant guard) ───────────────────────────


def test_flag_off_never_consults_trees_for(monkeypatch):
    """With the flag OFF the hybrid must not touch the crosswalk seam at all —
    a trees_for that raises proves the path is dead when the flag is off."""

    def _boom(_card):
        raise AssertionError("trees_for must not be called with the flag OFF")

    monkeypatch.setattr(il, "trees_for", _boom)
    bulk, _tree, _key = _ported_case()
    # ir=None, flag OFF → pure regex path, no crosswalk, no crash.
    extract_signals_hybrid(bulk, None)


# ── Step 2: ir_for Seam-B switch ─────────────────────────────────────────────


def test_ir_for_switches_on_flag(monkeypatch):
    old = Card(oracle_id="o", name="Old", faces=(Face(name="Old", abilities=()),))
    new = Card(oracle_id="o", name="Xwalk", faces=(Face(name="Xwalk", abilities=()),))
    monkeypatch.setattr(il, "_index", _returns({"o": old}))
    monkeypatch.setattr(il, "_crosswalk_index", _returns({"o": new}))
    card = {"oracle_id": "o"}

    monkeypatch.setenv(FLAG, "0")
    assert il.ir_for(card) is old  # flag OFF → legacy sidecar
    assert il.old_ir_for(card) is old

    monkeypatch.setenv(FLAG, "1")
    assert il.ir_for(card) is new  # flag ON → crosswalk sidecar
    assert il.old_ir_for(card) is old  # old_ir_for never switches


def test_ir_for_degrades_when_crosswalk_sidecar_missing(monkeypatch):
    old = Card(oracle_id="o", name="Old", faces=(Face(name="Old", abilities=()),))
    monkeypatch.setattr(il, "_index", _returns({"o": old}))
    monkeypatch.setattr(il, "_crosswalk_index", _returns(None))  # unbuilt
    monkeypatch.setenv(FLAG, "1")
    assert il.ir_for({"oracle_id": "o"}) is old  # ON but no sidecar → legacy


# ── Step 3: trees_for resolver ───────────────────────────────────────────────


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
    """The production seam (``extract_signals_hybrid``, flag ON): Avatar Aang's
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
    monkeypatch.setenv(FLAG, "1")
    keys = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert keys >= _BEND_KEYS


def test_avatar_aang_regression_no_fire_control(monkeypatch):
    """A no-bend card stays silent on all four keys through the same union path —
    the fix doesn't turn the bend lanes into a blanket floor."""
    bulk, tree, _key = _ported_case()
    if tree.oracle_id == _AANG_OID:
        pytest.skip("ported-case card is Avatar Aang itself")
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    monkeypatch.setenv(FLAG, "1")
    keys = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert not (_BEND_KEYS & keys)


# ── Step 3: hybrid three-way dispatch ────────────────────────────────────────


def test_hybrid_serves_ported_from_crosswalk(monkeypatch):
    bulk, tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))

    monkeypatch.setenv(FLAG, "0")
    off = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key not in off  # ir=None + flag OFF → no IR/crosswalk source

    monkeypatch.setenv(FLAG, "1")
    on = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key in on  # flag ON → the crosswalk supplies it


def test_hybrid_falls_back_when_tree_unavailable(monkeypatch):
    """Flag ON but trees_for → () degrades to the legacy path (ir param honored)."""
    bulk, _tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns(()))
    monkeypatch.setenv(FLAG, "1")
    on = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key not in on  # no tree, ir=None → regex only


def test_hybrid_crosswalk_merge_never_consults_old_ir(monkeypatch):
    """ADR-0039 task #80 step 3: ``MIGRATED_KEYS - PORTED_KEYS`` (the old
    "residual" tail) is EMPTY — every migrated key graduated to a
    crosswalk-native lane — and the membership floor's own former
    ``old_ir_for`` dependency was rewired to read the concept tree directly
    (:func:`_is_big_mana_tree` / ``has_structural_kill_engine`` /
    :func:`_floor_token_maker_subjects`). So the crosswalk merge must NEVER
    fetch ``old_ir_for`` — a genuine regression to the pre-rewire residual
    fallback would show up here as a spurious call."""
    bulk, tree, _key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    calls: list[dict] = []

    def _spy(card):
        calls.append(card)

    monkeypatch.setattr(il, "old_ir_for", _spy)
    monkeypatch.setenv(FLAG, "1")
    extract_signals_hybrid(bulk, None)
    assert not calls, "old_ir_for must never be consulted by the crosswalk merge"


def test_hybrid_reconciliation_single_fire(monkeypatch):
    """No duplicate (key, scope, subject) survives the shared reconciliation tail,
    even though the crosswalk applies its own reconciliations before the merge."""
    bulk, tree, _key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    monkeypatch.setenv(FLAG, "1")
    sigs = extract_signals_hybrid(bulk, None)
    idents = [(s.key, s.scope, s.subject) for s in sigs]
    assert len(idents) == len(set(idents))


def test_hybrid_three_way_key_partition():
    """The Seam-A split is a three-way partition, not a clean swap: PORTED and the
    residual set are disjoint and their union is the served (stripped-from-regex)
    set. ADR-0039 W8 (the KEPT-twelve wave) promoted all 12 Stage-2 KEPT keys —
    base_power_matters, big_mana, cheat_from_top, copy_limit, damage_redirect,
    excess_damage, extra_draw_step, free_cast, ki_counter_matters,
    kicked_spell_matters, land_destruction, named_synergy — off the residual set
    and into PORTED. No permanent KEPT lane remains.

    ADR-0039 W8 FINISHER (2026-07-12): ``creatures_matter`` was the LAST
    Stage-4 residual key (a per-card node-path classifier fully adjudicated
    its 53-card true-gap tail — Formidable's typed condition tag, two tiny
    typed container-descent reads, eight ledgered bridges, and a fully
    corpus-verified shed set — see ``_creatures_matter``'s own docstring).
    ``residual`` is now legitimately EMPTY — the terminal state of the
    residual grind, not a bug: ``_crosswalk_merge`` (signals.py) already
    degrades gracefully when ``residual`` is empty (``served = PORTED_KEYS
    | residual`` collapses to ``PORTED_KEYS``; the ``if sig.key in
    residual`` re-supply loop simply adds nothing). Deleting the legacy IR
    path itself (task #80/#82) is a SEPARATE, later step this test does not
    gate — it only pins the key-partition INVARIANT, which holds for an
    empty residual set exactly as it does for a non-empty one."""
    residual = MIGRATED_KEYS - PORTED_KEYS
    assert residual == frozenset(), (
        "creatures_matter (ADR-0039 W8 finisher) was the last residual key — "
        "the residual set is now correctly EMPTY, the terminal state of the "
        "residual grind. If this assertion fails on a NON-empty residual, a "
        "key regressed out of PORTED_KEYS; investigate before 'fixing' this "
        "test back to non-empty."
    )
    kept_twelve = {
        "base_power_matters",
        "big_mana",
        "cheat_from_top",
        "copy_limit",
        "damage_redirect",
        "excess_damage",
        "extra_draw_step",
        "free_cast",
        "ki_counter_matters",
        "kicked_spell_matters",
        "land_destruction",
        "named_synergy",
    }
    assert kept_twelve <= PORTED_KEYS
    assert kept_twelve.isdisjoint(residual)
    assert PORTED_KEYS.isdisjoint(residual)
    assert (PORTED_KEYS | residual) == (PORTED_KEYS | MIGRATED_KEYS)


# ── producible-key gate under the flag ───────────────────────────────────────


def test_producible_unions_ported_under_flag(monkeypatch):
    monkeypatch.setenv(FLAG, "0")
    off = producible_static_keys()
    monkeypatch.setenv(FLAG, "1")
    on = producible_static_keys()
    assert off <= on  # flag ON is a superset
    # The three PORTED-only maker lanes appear only under the flag.
    assert {"amass_makers", "copy_permanent", "incubate_makers"} <= on
    assert {"amass_makers", "copy_permanent", "incubate_makers"}.isdisjoint(off)


def test_gate_resolves_every_producible_key_under_flag(monkeypatch):
    """The import-time key-agreement gate must still pass with the flag ON —
    every crosswalk-produced key (incl. the 3 PORTED-only lanes) resolves."""
    from mtg_utils._deck_forge.signal_specs import (
        _assert_every_producible_key_resolves,
    )

    monkeypatch.setenv(FLAG, "1")
    _assert_every_producible_key_resolves()  # raises AssertionError on an orphan


def test_new_specs_are_inert_flag_off(monkeypatch):
    """The three added specs must not change the flag-OFF producible set (the keys
    are never produced by the regex path)."""
    monkeypatch.setenv(FLAG, "0")
    off = producible_static_keys()
    assert {"amass_makers", "copy_permanent", "incubate_makers"}.isdisjoint(off)


# ── ADR-0035 Stage-3a MEMBERSHIP / cares-about FLOOR port ─────────────────────
# The flag-ON crosswalk is membership-AGNOSTIC on the broad "commander cares about
# X" floor (a vanilla Enchantment → enchantments_matter, an Artifact →
# artifacts_matter, an Equipment / big body → voltron_matters, an own-subtype /
# token-profile tribe → type_matters). The port reproduces that
# ``extract_signals_ir`` floor inside ``extract_crosswalk_signals`` behind a
# keyword-only ``include_membership`` (default False).
#
# The GATE below measures the WHOLE floor over EVERY key, not a hand-picked subset —
# the floor is defined structurally as ``extract_signals_ir(include=True) minus
# extract_signals_ir(include=False)`` per card. It is partitioned into the
# UNCONDITIONAL floor (must reproduce 100%) and the go_wide-GATED ``CLASS_TRIBES``
# ``type_matters`` lanes (tracked against the crosswalk's own go_wide keys). The
# go_wide gate keys are ``creatures_matter``/``attack_matters``/``anthem_static``.
# ADR-0035 Stage-4 routed all three into ``_STAGE4_RESIDUAL`` (served by
# ``old_ir_for``), so the flag-ON hybrid's go_wide now matches the IR's exactly and
# the class-tribe floor is fully reproduced — the pre-Stage-4 go_wide cascade
# (recall < 100% while the lanes were PORTED) collapses to empty.
_GO_WIDE_KEYS = frozenset({"creatures_matter", "attack_matters", "anthem_static"})


@lru_cache(maxsize=1)
def _faces_by_oid() -> dict[str, list[dict]]:
    """Fixture phase face-records grouped by oracle_id (``project_card`` input)."""
    out: dict[str, list[dict]] = {}
    for rec in _fixture_records():
        oid = rec.get("scryfall_oracle_id")
        if oid:
            out.setdefault(oid, []).append(rec)
    return out


def _floor_case(oid: str, faces: list[dict]):
    """Build (bulk_record, concept_tree, legacy_Card) for a fixture card, or None
    when the phase record drifts. The bulk record's ``type_line`` is reconstructed
    from the tree's typed supertype/type/subtype fields so the membership floor
    reads the REAL card types (the fixture carries no Scryfall type_line)."""
    nm = faces[0].get("name") or ""
    try:
        root = strict_load_card(faces[0], _schema(), name=nm)
        tree = build_concept_tree(root, name=nm, oracle_id=oid)
        ir = project_card(faces)
    except Exception:  # noqa: BLE001 — skip drift/odd cards, as _ported_case does
        return None
    parts = list(tree.card_supertypes) + list(tree.card_types)
    type_line = " ".join(parts)
    if tree.card_subtypes:
        type_line += " — " + " ".join(tree.card_subtypes)
    bulk = {
        "oracle_id": oid,
        "name": nm,
        "oracle_text": faces[0].get("oracle_text") or "",
        "type_line": type_line,
        "keywords": [],
        "cmc": tree.cmc,
    }
    return bulk, tree, ir


def _hybrid_idents(monkeypatch, bulk, tree, ir, *, flag: bool, include: bool):
    """Every signal ident from ``extract_signals_hybrid`` with the flag ON/OFF and
    the given ``include_membership``, wiring the crosswalk seam to the fixture tree +
    legacy Card (as the cutover tests do). ALL keys — the honest gate below measures
    the whole floor, not a hand-picked lane subset."""
    if flag:
        monkeypatch.setenv(FLAG, "1")
    else:
        monkeypatch.setenv(FLAG, "0")
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    monkeypatch.setattr(il, "_index", _returns({ir.oracle_id: ir}))
    sigs = extract_signals_hybrid(bulk, ir, include_membership=include)
    return {(s.key, s.scope, s.subject) for s in sigs}


def test_extract_crosswalk_signals_no_floor_by_default():
    """The shadow-harness contract: called WITHOUT ``include_membership`` (default
    False), the crosswalk fires no membership floor — so every existing crosswalk
    test / the shadow diff (which never pass the arg) stays byte-identical."""
    oid, faces = next(iter(_faces_by_oid().items()))
    built = _floor_case(oid, faces)
    if built is None:  # pragma: no cover — the first card always builds in practice
        pytest.skip("first fixture card drifts")
    _bulk_rec, tree, _ir = built
    base = extract_crosswalk_signals(tree, keywords=frozenset())
    # An enchantment/artifact type_line can NOT open a floor lane without the arg.
    withrec = extract_crosswalk_signals(tree, keywords=frozenset(), record=_bulk_rec)
    assert {(s.key, s.scope, s.subject) for s in base} == {
        (s.key, s.scope, s.subject) for s in withrec
    }


def test_membership_floor_reproduced_in_flag_on_commander(monkeypatch):
    """THE GATE (honest, full-floor). The membership / cares-about floor is the FULL
    per-card delta ``extract_signals_ir(include=True)`` minus
    ``extract_signals_ir(include=False)`` measured over EVERY key across the whole
    committed fixture — NOT a hand-picked lane subset (the old 3-lane gate
    self-blindly skipped ``type_matters`` and falsely reported parity). Each
    membership-sourced lane is partitioned:

      (a) the UNCONDITIONAL floor — own card-type (artifacts/enchantments),
          own-subtype ``TRIBAL_SUBTYPES`` tribes, token-profile tribes, and every
          non-go_wide cross-open (voltron / big_mana / kill_engine / wants_cloning /
          blink_flicker …). This MUST reproduce 100% under the flag-ON crosswalk
          commander path — a single loss is a real helper bug, never documented away.

      (b) the go_wide-GATED ``CLASS_TRIBES`` ``type_matters`` lanes.
          ``extract_signals_ir`` fires these only when its own go_wide (any of
          ``creatures_matter`` / ``attack_matters`` / ``anthem_static``) is set. Those
          three are PORTED lanes whose crosswalk recall is < 100% by adjudication, so
          where the crosswalk's go_wide legitimately differs from the IR's, the
          class-tribe floor differs too. A miss here is ALLOWED only when it is
          provably a go_wide cascade: the crosswalk fired NONE of the go_wide keys
          while the IR fired at least one.
          Any class-tribe miss with the crosswalk go_wide still set would be a real
          helper bug and fails the per-lane assertion below."""
    uncond_total = uncond_ok = 0
    gated_total = gated_ok = 0
    gated_cascade: list[tuple[str, tuple[str, str, str]]] = []
    unconditional_lost: list[tuple[str, tuple[str, str, str]]] = []
    for oid, faces in _faces_by_oid().items():
        built = _floor_case(oid, faces)
        if built is None:
            continue
        bulk, tree, ir = built
        on_all = {
            (s.key, s.scope, s.subject)
            for s in extract_signals_ir(bulk, ir, include_membership=True)
        }
        off_all = {
            (s.key, s.scope, s.subject)
            for s in extract_signals_ir(bulk, ir, include_membership=False)
        }
        membership_sourced = on_all - off_all
        if not membership_sourced:
            continue
        on_cmd = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=True, include=True)
        ir_go_wide = {k for (k, _s, _sub) in on_all if k in _GO_WIDE_KEYS}
        xwalk_go_wide = {k for (k, _s, _sub) in on_cmd if k in _GO_WIDE_KEYS}
        for lane in membership_sourced:
            key, _scope, subject = lane
            gated = key == signal_keys.TYPE_MATTERS and subject.lower() in CLASS_TRIBES
            if gated:
                gated_total += 1
                if lane in on_cmd:
                    gated_ok += 1
                    continue
                # Allowed ONLY as a go_wide cascade: the crosswalk's own go_wide
                # lanes differ from the IR's (crosswalk fired none, IR fired one),
                # so the class-tribe floor legitimately gates off. Any other miss
                # (crosswalk go_wide still set) is a real bug and trips here.
                cascade_msg = (
                    f"CLASS_TRIBES floor lane {lane} for {bulk['name']!r} lost with "
                    f"crosswalk go_wide={sorted(xwalk_go_wide)} vs IR go_wide="
                    f"{sorted(ir_go_wide)} — not a go_wide cascade"
                )
                assert not xwalk_go_wide, cascade_msg  # crosswalk went narrow
                assert ir_go_wide, cascade_msg  # IR went wide (why the lane fired)
                gated_cascade.append((bulk["name"], lane))
            else:
                uncond_total += 1
                if lane in on_cmd:
                    uncond_ok += 1
                else:
                    unconditional_lost.append((bulk["name"], lane))
    # (a) the load-bearing invariant: the unconditional floor is reproduced 100%.
    assert not unconditional_lost, (
        f"UNCONDITIONAL membership floor lost under flag-ON: {unconditional_lost[:20]}"
    )
    assert uncond_ok == uncond_total
    # A broad floor was actually measured — not a 3-lane toy.
    assert uncond_total > 100, f"expected a broad floor, saw {uncond_total} lanes"
    # (b) every class-tribe floor lane is accounted for: reproduced, or an allowed
    # go_wide cascade (the per-lane assert above proves each cascade is legitimate).
    # The go_wide keys (creatures_matter / attack_matters / anthem_static) are now
    # PORTED (crosswalk-native, ADR-0038/0039), so the flag-ON hybrid's go_wide is
    # the crosswalk's OWN structural computation — genuinely narrower than the IR's
    # on cards whose go-wide traces to old-IR's board_count hallucination (ADR-0039
    # task #80 step 3 dropped the byte-parity reproduction of that artifact from
    # ``_type_matters_go_wide``, matching ``_creatures_matter``'s own precedent for
    # the standalone key). The partition invariant (every lane is EITHER reproduced
    # OR a provable cascade) is what guards the floor — non-emptiness of either
    # bucket is not required.
    assert gated_ok + len(gated_cascade) == gated_total


def test_membership_floor_inert_in_candidate_mode():
    """Candidate mode (``include_membership=False`` — the 99) must be UNCHANGED by
    the port: the crosswalk floor never fires, so flag-ON candidate mode adds no
    floor lane over its own pre-port baseline. Proven structurally: with the floor
    gated OFF, the crosswalk output is identical whether or not ``record`` is
    threaded."""
    for oid, faces in _faces_by_oid().items():
        built = _floor_case(oid, faces)
        if built is None:
            continue
        bulk, tree, _ir = built
        without = extract_crosswalk_signals(tree, keywords=frozenset())
        # include_membership defaults False → threading record is a no-op.
        threaded = extract_crosswalk_signals(
            tree,
            keywords=frozenset(),
            include_membership=False,
            record=bulk,
        )
        assert [(s.key, s.scope, s.subject) for s in without] == [
            (s.key, s.scope, s.subject) for s in threaded
        ]


def _floor_case_for(name: str):
    """A single named fixture card's floor case (see :func:`_floor_case`), or
    ``None`` if the card isn't present / drifts."""
    for oid, faces in _faces_by_oid().items():
        if faces and faces[0].get("name") == name:
            return _floor_case(oid, faces)
    return None


def test_land_destruction_promoted_floor(monkeypatch):
    """ADR-0039 W8 (land_destruction PROMOTED off the KEPT twelve): the
    shared ``_apply_membership_floor`` (imported by BOTH ``extract_signals_
    ir`` and ``extract_crosswalk_signals``, one source, zero drift) fires
    land_destruction for a CREATURE commander whose own oracle matches
    "destroy target land(s)" (Goblin Settler — "When this creature enters,
    destroy target land", CR 305.6) under ``include_membership=True`` on
    BOTH the flag-OFF (legacy) and flag-ON (crosswalk) hybrid paths, and
    fires on NEITHER path with ``include_membership=False`` (the 99-card
    candidate-mode gate)."""
    built = _floor_case_for("Goblin Settler")
    if built is None:
        pytest.skip("Goblin Settler fixture record drifts")
    bulk, tree, ir = built
    on_off_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=False, include=True)
    on_on_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=True, include=True)
    assert ("land_destruction", "you", "") in on_off_path
    assert ("land_destruction", "you", "") in on_on_path
    off_99 = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=True, include=False)
    assert "land_destruction" not in {k for k, _s, _su in off_99}


def test_big_mana_promoted_floor(monkeypatch):
    """ADR-0039 W8 (big_mana PROMOTED off the KEPT twelve): Sol Ring's
    ``{T}: Add {C}{C}`` fires the shared ``_apply_membership_floor``'s
    big_mana arm on BOTH the flag-OFF (``_is_big_mana_ir``, reading the OLD
    projected ``Card``'s ``ramp`` Effect with ``amount.factor>1``, CR 106.4)
    and flag-ON (``_is_big_mana_tree``, reading the SAME magnitude off the
    concept tree's ``ramp`` effect-concept, ADR-0039 task #80 step 3) hybrid
    paths under ``include_membership=True`` — two independent structural
    reads of the same real card, not one shared computation any more."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    bulk, tree, ir = built
    on_off_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=False, include=True)
    on_on_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=True, include=True)
    assert ("big_mana", "you", "") in on_off_path
    assert ("big_mana", "you", "") in on_on_path


# ── ADR-0039 task #80 step 3 — the membership floor's rewired detectors ──────
# Direct unit pins for the three structural facts ``_apply_membership_floor``
# used to read off the OLD projected ``Card`` and now reads off the concept
# tree instead, one detector at a time, each verified against the LEGACY
# reader over the SAME real card (positive: the legacy reader also fires;
# negative: neither reader fires) — the mechanism moved, membership did not.


def test_is_big_mana_tree_direct_ramp_effect():
    """Positive, direct ramp effect: Sol Ring's ``{T}: Add {C}{C}`` is a
    ``ramp`` effect concept whose typed ``produced`` is
    ``Colorless(count=Fixed(2))`` — factor > 1 (CR 106.4). Matches
    ``_is_big_mana_ir`` on the SAME card's legacy projection."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir(ir) is True


def test_is_big_mana_tree_granted_mana_ability():
    """Positive, GRANTED mana ability: Discreet Retreat's Aura grants
    enchanted land "{T}: Add two mana of any one color" — the magnitude
    lives on the granted ``GrantAbility`` definition's own effect
    (:func:`_granted_mana_defs`), not a direct ``ramp`` effect concept on
    Discreet Retreat's own ability (``tree.effect_concepts("ramp")`` is
    empty for this card — verified this session). Matches ``_is_big_mana_ir``
    on the SAME card's legacy projection (CR 106.4)."""
    built = _floor_case_for("Discreet Retreat")
    if built is None:
        pytest.skip("Discreet Retreat fixture record drifts")
    _bulk, tree, ir = built
    assert not tree.effect_concepts("ramp")
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir(ir) is True


def test_is_big_mana_tree_returnasaura_granted_mana_gain():
    """GENUINE recall gain (corpus-adjudicated, ADR-0039 task #80 step 3):
    Harold and Bob, First Numens's ``ReturnAsAura`` effect grants "Enchanted
    Forest has '{T}: Add three mana of any one color...'" — factor 3, CR
    106.4. ``_is_big_mana_tree`` reads it via
    :func:`_iter_returnasaura_mana_defs`; the OLD IR does NOT structure a
    ``ReturnAsAura``-granted ability into a ramp-category ``Effect`` at all,
    so ``_is_big_mana_ir``'s ``ir.all_abilities()`` walk finds nothing to
    check — a real gap the old projection had, not something this rewire
    introduces (full commander-legal re-measure this session found 0
    regressions and 3 such gains: this card plus Food Chain / Metamorphosis's
    dynamically-scaling "Add X mana... where X is 1 plus..." bodies, both
    outside the committed fixture)."""
    built = _floor_case_for("Harold and Bob, First Numens")
    if built is None:
        pytest.skip("Harold and Bob, First Numens fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir(ir) is False


def test_is_big_mana_tree_single_mana_dork_negative():
    """Negative: Llanowar Elves' ``{T}: Add {G}`` is exactly ONE mana —
    factor == 1, not big mana (CR 106.4). Matches ``_is_big_mana_ir`` on the
    SAME card's legacy projection."""
    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is False
    assert _is_big_mana_ir(ir) is False


def test_floor_kill_engine_reads_tree_directly():
    """The floor's kill_engine arm now reads ``has_structural_kill_engine``
    off the tree (CR 701.8a: "To destroy a permanent, move it from the
    battlefield to its owner's graveyard") instead of ``_is_kill_engine_ir``
    off the OLD ``Card`` — verified equivalent on a genuine repeatable-
    destroy engine (Visara the Dreadful's "{2}{B}{B}, {T}: Destroy target
    creature.") and a creature with no such ability (Llanowar Elves),
    matching ``_is_kill_engine_ir`` on the SAME cards' legacy projections
    both ways."""
    built = _floor_case_for("Visara the Dreadful")
    if built is None:
        pytest.skip("Visara the Dreadful fixture record drifts")
    _bulk, tree, ir = built
    assert has_structural_kill_engine(tree) is True
    assert _is_kill_engine_ir(ir) is True

    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree, ir = built
    assert has_structural_kill_engine(tree) is False
    assert _is_kill_engine_ir(ir) is False


def test_floor_token_maker_subjects_directed_raw_mirror():
    """Positive, raw-mirror recovery: "Each player OTHER THAN target player
    creates a 5/5 red Dragon creature token" (Death by Dragons) and "its
    controller creates a 3/3 white Angel creature token" (Soul of
    Emancipation) both leave phase's ``Token`` node ``Unimplemented`` (no
    typed ``types`` field) — the floor cares only that the card's own
    ability NAMES a creature-token subtype (CR 111.2/205.3), not who
    receives it (unlike the ``token_maker`` KEY lane's own directed-gift
    exclusion), so :func:`_floor_token_maker_subjects` recovers both via the
    per-concept raw mirror. Matches legacy's OLD ``ir.all_abilities()`` walk
    on the SAME cards."""
    built = _floor_case_for("Death by Dragons")
    if built is None:
        pytest.skip("Death by Dragons fixture record drifts")
    _bulk, tree, _ir = built
    assert "Dragon" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)

    built = _floor_case_for("Soul of Emancipation")
    if built is None:
        pytest.skip("Soul of Emancipation fixture record drifts")
    _bulk, tree, _ir = built
    assert "Angel" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)


def test_floor_token_maker_subjects_structural_no_mirror_needed():
    """Positive, purely structural: Krenko, Mob Boss's own "create X 1/1 red
    Goblin creature tokens" resolves via phase's typed ``Token.types`` field
    directly — no raw-mirror fallback needed."""
    built = _floor_case_for("Krenko, Mob Boss")
    if built is None:
        pytest.skip("Krenko, Mob Boss fixture record drifts")
    _bulk, tree, _ir = built
    assert "Goblin" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)


def test_floor_token_maker_subjects_no_maker_negative():
    """Negative: Llanowar Elves makes no tokens at all — the empty set,
    matching legacy's OLD ``ir.all_abilities()`` walk on the same card."""
    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree, _ir = built
    assert _floor_token_maker_subjects(tree, CREATURE_SUBTYPES) == set()


def test_type_matters_go_wide_arm_vi_dropped_in_commander_mode(monkeypatch):
    """The dropped ``_type_matters_go_wide`` arm (vi) reproduced a KNOWN
    old-IR hallucination (a synthetic board_count ability fabricated for
    Elvish Berserker's Rampage "for each creature blocking it") — already
    adjudicated a SHED for candidate mode
    (``test_type_matters_go_wide_rampage_shed_not_ported``,
    tests/mtg-utils/test_crosswalk.py). This pins the SAME adjudication now
    holds in ``include_membership=True`` COMMANDER mode too: legacy (flag
    OFF) still fires the class-tribe Berserker lane (the hallucination is
    untouched there), but the flag-ON crosswalk path — which used to
    byte-mirror it via arm (vi) — no longer does. Elvish Berserker's own
    RACE tribe (Elf) fires on BOTH paths regardless (CR 205.3/702.23)."""
    built = _floor_case_for("Elvish Berserker")
    if built is None:
        pytest.skip("Elvish Berserker fixture record drifts")
    bulk, tree, ir = built
    on_off_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=False, include=True)
    on_on_path = _hybrid_idents(monkeypatch, bulk, tree, ir, flag=True, include=True)
    assert ("type_matters", "you", "Elf") in on_off_path
    assert ("type_matters", "you", "Elf") in on_on_path
    assert ("type_matters", "you", "Berserker") in on_off_path
    assert ("type_matters", "you", "Berserker") not in on_on_path
