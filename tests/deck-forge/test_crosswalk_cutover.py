"""The crosswalk seam (ADR-0035) — post-cutover invariants (ADR-0039 task #80
step 6).

The ADR-0035 Stage-3a ``MTG_SKILLS_CROSSWALK_SIGNALS`` cutover flag and the
legacy revert path it gated are GONE (task #80 step 6): ``extract_signals_hybrid``
now has exactly one serving path — ``trees_for`` resolves a card's per-face
concept trees, the ported crosswalk lanes run over each, and the membership
floor runs once at the merge level. These tests pin what remains true of that
ONE path — the ``ir_for`` / ``trees_for`` Seam-A/B resolvers, the hybrid's
crosswalk-only dispatch, the residual-empty key partition, and the membership
floor (including the ADR-0039 task #80 step 6 DFC fix: the floor now unions its
structural facts across every face, closing the per-face isolation gap step 3
left) — plus the legacy-``extract_signals_ir`` baseline comparisons that still
make sense while ``project_card`` exists (step 7 decides that builder's fate).
CI-safe: the concept trees come from the committed ``crosswalk_fixture_cards.json``
phase records + the committed mirror schema (single-face cases) or the committed
``mtg_utils.testkit`` card snapshot (the DFC multi-face pins, which need TWO
phase records sharing one oracle_id) — no bulk / sidecar / phase / network.
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
from mtg_utils._deck_forge._signals_ir import CLASS_TRIBES, extract_signals_ir
from mtg_utils._deck_forge._signals_ir import _is_big_mana_ir as _is_big_mana_ir_legacy
from mtg_utils._deck_forge._signals_ir import (
    _is_kill_engine_ir as _is_kill_engine_ir_legacy,
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
from mtg_utils.testkit import test_signals

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


# ── ADR-0035 Stage-3a MEMBERSHIP / cares-about FLOOR (still legacy-compared) ──
# The crosswalk is membership-AGNOSTIC on the broad "commander cares about X"
# floor (a vanilla Enchantment → enchantments_matter, an Artifact →
# artifacts_matter, an Equipment / big body → voltron_matters, an own-subtype /
# token-profile tribe → type_matters) unless ``apply_membership_floor`` runs
# (``extract_signals_hybrid``'s ``include_membership=True`` path — the
# commander-only gate). The GATE below measures the WHOLE floor over EVERY
# key, not a hand-picked subset — defined structurally as
# ``extract_signals_ir(include=True) minus extract_signals_ir(include=False)``
# per card, still a genuine legacy-baseline comparison while ``project_card``
# exists (step 7 decides that builder's fate — this comparison dies with it).
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


def _hybrid_idents(monkeypatch, bulk, tree, *, include: bool):
    """Every signal ident from ``extract_signals_hybrid`` (the crosswalk-only
    path), wiring the crosswalk seam to the fixture tree — as the cutover tests
    do. ALL keys — the honest gate below measures the whole floor, not a
    hand-picked lane subset."""
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    sigs = extract_signals_hybrid(bulk, include_membership=include)
    return {(s.key, s.scope, s.subject) for s in sigs}


def test_membership_floor_reproduced_in_commander_mode(monkeypatch):
    """THE GATE (honest, full-floor). The membership / cares-about floor is the FULL
    per-card delta ``extract_signals_ir(include=True)`` minus
    ``extract_signals_ir(include=False)`` measured over EVERY key across the whole
    committed fixture — NOT a hand-picked lane subset (an early hand-picked 3-lane
    gate self-blindly skipped ``type_matters`` and falsely reported parity). Each
    membership-sourced lane is partitioned:

      (a) the UNCONDITIONAL floor — own card-type (artifacts/enchantments),
          own-subtype ``TRIBAL_SUBTYPES`` tribes, token-profile tribes, and every
          non-go_wide cross-open (voltron / big_mana / kill_engine / wants_cloning /
          blink_flicker …). This MUST reproduce 100% under the crosswalk commander
          path — a single loss is a real helper bug, never documented away.

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
        on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
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
        f"UNCONDITIONAL membership floor lost under the crosswalk path: "
        f"{unconditional_lost[:20]}"
    )
    assert uncond_ok == uncond_total
    # A broad floor was actually measured — not a 3-lane toy.
    assert uncond_total > 100, f"expected a broad floor, saw {uncond_total} lanes"
    # (b) every class-tribe floor lane is accounted for: reproduced, or an allowed
    # go_wide cascade (the per-lane assert above proves each cascade is legitimate).
    assert gated_ok + len(gated_cascade) == gated_total


# ── ADR-0039 task #80 step 3 — the membership floor's rewired detectors ──────
# Direct unit pins for the three structural facts ``_apply_membership_floor``
# used to read off the OLD projected ``Card`` and now reads off the concept
# tree instead, one detector at a time, each verified against the LEGACY
# reader over the SAME real card (positive: the legacy reader also fires;
# negative: neither reader fires) — the mechanism moved, membership did not.


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
    ir`` and ``crosswalk_signals.apply_membership_floor``, one source, zero
    drift) fires land_destruction for a CREATURE commander whose own oracle
    matches "destroy target land(s)" (Goblin Settler — "When this creature
    enters, destroy target land", CR 305.6) under ``include_membership=True``
    on the crosswalk hybrid path, and fires on neither path with
    ``include_membership=False`` (the 99-card candidate-mode gate)."""
    built = _floor_case_for("Goblin Settler")
    if built is None:
        pytest.skip("Goblin Settler fixture record drifts")
    bulk, tree, _ir = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("land_destruction", "you", "") in on_cmd
    on_99 = _hybrid_idents(monkeypatch, bulk, tree, include=False)
    assert "land_destruction" not in {k for k, _s, _su in on_99}


def test_big_mana_promoted_floor(monkeypatch):
    """ADR-0039 W8 (big_mana PROMOTED off the KEPT twelve): Sol Ring's
    ``{T}: Add {C}{C}`` fires the shared ``_apply_membership_floor``'s
    big_mana arm via ``_is_big_mana_tree`` (reading the magnitude off the
    concept tree's ``ramp`` effect-concept, ADR-0039 task #80 step 3) under
    ``include_membership=True`` on the crosswalk hybrid path."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    bulk, tree, _ir = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("big_mana", "you", "") in on_cmd


def test_is_big_mana_tree_direct_ramp_effect():
    """Positive, direct ramp effect: Sol Ring's ``{T}: Add {C}{C}`` is a
    ``ramp`` effect concept whose typed ``produced`` is
    ``Colorless(count=Fixed(2))`` — factor > 1 (CR 106.4). Matches the
    legacy ``_is_big_mana_ir`` reader on the SAME card's legacy projection."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir_legacy(ir) is True


def test_is_big_mana_tree_granted_mana_ability():
    """Positive, GRANTED mana ability: Discreet Retreat's Aura grants
    enchanted land "{T}: Add two mana of any one color" — the magnitude
    lives on the granted ``GrantAbility`` definition's own effect
    (:func:`_granted_mana_defs`), not a direct ``ramp`` effect concept on
    Discreet Retreat's own ability (``tree.effect_concepts("ramp")`` is
    empty for this card — verified this session). Matches the legacy
    ``_is_big_mana_ir`` reader on the SAME card's legacy projection (CR
    106.4)."""
    built = _floor_case_for("Discreet Retreat")
    if built is None:
        pytest.skip("Discreet Retreat fixture record drifts")
    _bulk, tree, ir = built
    assert not tree.effect_concepts("ramp")
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir_legacy(ir) is True


def test_is_big_mana_tree_returnasaura_granted_mana_gain():
    """GENUINE recall gain (corpus-adjudicated, ADR-0039 task #80 step 3):
    Harold and Bob, First Numens's ``ReturnAsAura`` effect grants "Enchanted
    Forest has '{T}: Add three mana of any one color...'" — factor 3, CR
    106.4. ``_is_big_mana_tree`` reads it via
    :func:`_iter_returnasaura_mana_defs`; the OLD IR does NOT structure a
    ``ReturnAsAura``-granted ability into a ramp-category ``Effect`` at all,
    so the legacy ``_is_big_mana_ir`` reader's ``ir.all_abilities()`` walk
    finds nothing to check — a real gap the old projection had, not
    something this rewire introduces."""
    built = _floor_case_for("Harold and Bob, First Numens")
    if built is None:
        pytest.skip("Harold and Bob, First Numens fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is True
    assert _is_big_mana_ir_legacy(ir) is False


def test_is_big_mana_tree_single_mana_dork_negative():
    """Negative: Llanowar Elves' ``{T}: Add {G}`` is exactly ONE mana —
    factor == 1, not big mana (CR 106.4). Matches the legacy
    ``_is_big_mana_ir`` reader on the SAME card's legacy projection."""
    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree, ir = built
    assert _is_big_mana_tree(tree) is False
    assert _is_big_mana_ir_legacy(ir) is False


def test_floor_kill_engine_reads_tree_directly():
    """The floor's kill_engine arm now reads ``has_structural_kill_engine``
    off the tree (CR 701.8a: "To destroy a permanent, move it from the
    battlefield to its owner's graveyard") instead of the legacy
    ``_is_kill_engine_ir`` reader off the OLD ``Card`` — verified equivalent
    on a genuine repeatable-destroy engine (Visara the Dreadful's "{2}{B}{B},
    {T}: Destroy target creature.") and a creature with no such ability
    (Llanowar Elves), matching the legacy reader on the SAME cards both
    ways."""
    built = _floor_case_for("Visara the Dreadful")
    if built is None:
        pytest.skip("Visara the Dreadful fixture record drifts")
    _bulk, tree, ir = built
    assert has_structural_kill_engine(tree) is True
    assert _is_kill_engine_ir_legacy(ir) is True

    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree, ir = built
    assert has_structural_kill_engine(tree) is False
    assert _is_kill_engine_ir_legacy(ir) is False


def test_floor_token_maker_subjects_directed_raw_mirror():
    """Positive, raw-mirror recovery: "Each player OTHER THAN target player
    creates a 5/5 red Dragon creature token" (Death by Dragons) and "its
    controller creates a 3/3 white Angel creature token" (Soul of
    Emancipation) both leave phase's ``Token`` node ``Unimplemented`` (no
    typed ``types`` field) — the floor cares only that the card's own
    ability NAMES a creature-token subtype (CR 111.2/205.3), not who
    receives it (unlike the ``token_maker`` KEY lane's own directed-gift
    exclusion), so :func:`_floor_token_maker_subjects` recovers both via the
    per-concept raw mirror."""
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
    matching the legacy reader's ``ir.all_abilities()`` walk on the same
    card."""
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
    tests/mtg-utils/test_crosswalk.py). This pins the SAME adjudication in
    ``include_membership=True`` COMMANDER mode too: the crosswalk path never
    reproduces the class-tribe Berserker lane the legacy reader's
    hallucination fires. Elvish Berserker's own RACE tribe (Elf) fires
    regardless (CR 205.3/702.23)."""
    built = _floor_case_for("Elvish Berserker")
    if built is None:
        pytest.skip("Elvish Berserker fixture record drifts")
    bulk, tree, _ir = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("type_matters", "you", "Elf") in on_cmd
    assert ("type_matters", "you", "Berserker") not in on_cmd


# ── ADR-0039 task #80 step 6 — the DFC floor-to-merge move ───────────────────
# The membership floor used to run PER FACE inside ``extract_crosswalk_signals``,
# so a two-face card whose qualifying ability lives on a DIFFERENT face than its
# creature type lost the floor's class-tribe / kill_engine cross-opens (step 3's
# documented, accepted gap — see ``crosswalk_signals._floor_token_maker_subjects``'s
# docstring at the time). Moving the floor to run ONCE per card, over every face's
# tree together (``crosswalk_signals.apply_membership_floor``, called from
# ``signals.extract_signals_hybrid``), closes it. These pins use the committed
# ``mtg_utils.testkit`` card snapshot (not ``crosswalk_fixture_cards.json`` — the
# DFC pins need TWO phase records sharing one oracle_id, keyed by name, which the
# testkit snapshot already stores for exactly this purpose) and run the REAL
# production ``test_signals`` — no fixture indirection.


def test_dfc_floor_flaxen_intruder_gains_class_tribe():
    """Flaxen Intruder // Welcome Home: the token-maker ability (making Bear
    tokens) lives on the Adventure face ("Welcome Home"), not the Creature
    face ("Flaxen Intruder" — Human Berserker). Berserker is a CLASS_TRIBES
    entry (CR 205.3), so it only opens behind the go_wide gate — which the
    merge-level union now sees fire from the sibling face's token-maker
    ability. Berserker was the exact card the ``_floor_token_maker_subjects``
    per-face-gap docstring named."""
    sigs = test_signals("Flaxen Intruder // Welcome Home")
    idents = {(s.key, s.subject) for s in sigs}
    assert ("type_matters", "Berserker") in idents


def test_dfc_floor_kianne_imbraham_gains_class_tribe():
    """Kianne, Dean of Substance // Imbraham, Dean of Theory: both faces are
    Creatures (Elf Druid // Bird Wizard), each with its own race tribe
    firing unconditionally; Wizard (Imbraham's class) only opens behind the
    go_wide gate the merge-level union now proves via the sibling face."""
    sigs = test_signals("Kianne, Dean of Substance // Imbraham, Dean of Theory")
    idents = {(s.key, s.subject) for s in sigs}
    assert ("type_matters", "Wizard") in idents
    # Both race tribes still fire unconditionally regardless (CR 205.3).
    assert ("type_matters", "Elf") in idents
    assert ("type_matters", "Bird") in idents


def test_dfc_floor_sheoldred_gains_kill_engine():
    """Sheoldred // The True Scriptures: the repeatable destroy ability (a
    Saga chapter trigger, "destroy up to one target creature or
    planeswalker") lives on the Enchantment — Saga face ("The True
    Scriptures"), never the Creature face ("Sheoldred", which has no
    destroy ability of its own). ``has_structural_kill_engine`` gates on
    ``tree.is_type("Creature")`` per-face, so a bare per-face union can't
    close this — the merge-level ``apply_membership_floor`` separates "is
    ANY face a Creature" from "does ANY face carry the repeatable destroy
    unit" (:func:`_has_repeatable_kill_unit`) and combines them at the
    whole-card level instead (CR 701.8a)."""
    sigs = test_signals("Sheoldred // The True Scriptures")
    assert any(s.key == "kill_engine" for s in sigs)
