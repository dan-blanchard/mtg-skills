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
from mtg_utils._deck_forge import _ir_lookup as il
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._migrated_keys import MIGRATED_KEYS
from mtg_utils._deck_forge._signals_ir import CLASS_TRIBES, extract_signals_ir
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


def test_hybrid_residual_keys_consult_old_ir(monkeypatch):
    """The 12 residual keys (MIGRATED not in PORTED) stay on the legacy IR path:
    the crosswalk merge must fetch ``old_ir_for``, never the flag-switched
    ``ir_for`` (which under the flag is the crosswalk Card)."""
    bulk, tree, _key = _ported_case()
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    calls: list[dict] = []

    def _spy(card):
        calls.append(card)

    monkeypatch.setattr(il, "old_ir_for", _spy)
    monkeypatch.setenv(FLAG, "1")
    extract_signals_hybrid(bulk, None)
    assert calls, "old_ir_for must be consulted for the residual keys under the flag"


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
    set. The two permanent KEPT lanes are in the residual set (never the crosswalk)."""
    residual = MIGRATED_KEYS - PORTED_KEYS
    assert residual, "the residual set must be non-empty (do not delete the IR path)"
    assert "damage_redirect" in residual
    assert "land_destruction" in residual
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
    _bulk_rec, tree, ir = built
    base = extract_crosswalk_signals(tree, keywords=frozenset())
    # An enchantment/artifact type_line can NOT open a floor lane without the arg.
    withrec = extract_crosswalk_signals(
        tree, keywords=frozenset(), record=_bulk_rec, ir=ir
    )
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
    # ADR-0035 Stage-4: the go_wide keys (creatures_matter / attack_matters /
    # anthem_static) are in ``_STAGE4_RESIDUAL`` — served by ``old_ir_for`` on the
    # hybrid residual arm — so the flag-ON hybrid's go_wide now equals the IR's and
    # the class-tribe floor is fully reproduced (the pre-Stage-4 cascade residual
    # collapses to empty). Non-emptiness is therefore no longer required; the
    # partition invariant is what guards the floor.
    assert gated_ok + len(gated_cascade) == gated_total


def test_membership_floor_inert_in_candidate_mode():
    """Candidate mode (``include_membership=False`` — the 99) must be UNCHANGED by
    the port: the crosswalk floor never fires, so flag-ON candidate mode adds no
    floor lane over its own pre-port baseline. Proven structurally: with the floor
    gated OFF, the crosswalk output is identical whether or not ``record``/``ir`` are
    threaded."""
    for oid, faces in _faces_by_oid().items():
        built = _floor_case(oid, faces)
        if built is None:
            continue
        bulk, tree, ir = built
        without = extract_crosswalk_signals(tree, keywords=frozenset())
        # include_membership defaults False → threading record/ir is a no-op.
        threaded = extract_crosswalk_signals(
            tree,
            keywords=frozenset(),
            include_membership=False,
            record=bulk,
            ir=ir,
        )
        assert [(s.key, s.scope, s.subject) for s in without] == [
            (s.key, s.scope, s.subject) for s in threaded
        ]
