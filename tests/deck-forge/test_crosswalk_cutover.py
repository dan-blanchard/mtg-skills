"""ADR-0035 Stage-3a — the flag-gated crosswalk cutover (Steps 0-3).

The PRIME invariant lives in the existing suites: with the flag OFF (the default)
every other test passes UNCHANGED. These tests pin the *new* behavior — the flag
itself, the ``ir_for`` Seam-B switch, the ``tree_for`` resolver, and the hybrid's
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
    """Every test starts with the flag OFF and the memoized indexes cleared."""
    monkeypatch.delenv(FLAG, raising=False)
    il.clear_caches()
    yield
    il.clear_caches()


# ── Step 0: the flag ────────────────────────────────────────────────────────


def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert il.crosswalk_enabled() is False


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
        ("", False),
    ],
)
def test_flag_parses_env(monkeypatch, value, expected):
    monkeypatch.setenv(FLAG, value)
    assert il.crosswalk_enabled() is expected


# ── flag-OFF isolation (the prime-invariant guard) ───────────────────────────


def test_flag_off_never_consults_tree_for(monkeypatch):
    """With the flag OFF the hybrid must not touch the crosswalk seam at all —
    a tree_for that raises proves the path is dead when the flag is off."""

    def _boom(_card):
        raise AssertionError("tree_for must not be called with the flag OFF")

    monkeypatch.setattr(il, "tree_for", _boom)
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

    monkeypatch.delenv(FLAG, raising=False)
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


# ── Step 3: tree_for resolver ────────────────────────────────────────────────


def test_tree_for_degrades_without_phase_data(monkeypatch):
    monkeypatch.setattr(il, "_phase_record_index", _returns(None))
    assert il.tree_for({"oracle_id": "x"}) is None


def test_tree_for_none_without_oracle_id():
    assert il.tree_for({"name": "no oid"}) is None


def test_tree_for_builds_and_memoizes(monkeypatch):
    bulk, _tree, _key = _ported_case()
    oid = bulk["oracle_id"]
    # Feed the resolver our fixture record + schema directly.
    rec = next(r for r in _fixture_records() if r.get("scryfall_oracle_id") == oid)
    monkeypatch.setattr(il, "_phase_record_index", _returns({oid: rec}))
    monkeypatch.setattr(il, "_committed_schema", _returns(_schema()))
    got = il.tree_for(bulk)
    assert got is not None
    assert got.oracle_id == oid
    assert oid in il._TREE_MEMO  # memoized


# ── Step 3: hybrid three-way dispatch ────────────────────────────────────────


def test_hybrid_serves_ported_from_crosswalk(monkeypatch):
    bulk, tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "tree_for", _returns(tree))

    monkeypatch.delenv(FLAG, raising=False)
    off = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key not in off  # ir=None + flag OFF → no IR/crosswalk source

    monkeypatch.setenv(FLAG, "1")
    on = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key in on  # flag ON → the crosswalk supplies it


def test_hybrid_falls_back_when_tree_unavailable(monkeypatch):
    """Flag ON but tree_for → None degrades to the legacy path (ir param honored)."""
    bulk, _tree, ported_key = _ported_case()
    monkeypatch.setattr(il, "tree_for", _returns(None))
    monkeypatch.setenv(FLAG, "1")
    on = {s.key for s in extract_signals_hybrid(bulk, None)}
    assert ported_key not in on  # no tree, ir=None → regex only


def test_hybrid_residual_keys_consult_old_ir(monkeypatch):
    """The 12 residual keys (MIGRATED not in PORTED) stay on the legacy IR path:
    the crosswalk merge must fetch ``old_ir_for``, never the flag-switched
    ``ir_for`` (which under the flag is the crosswalk Card)."""
    bulk, tree, _key = _ported_case()
    monkeypatch.setattr(il, "tree_for", _returns(tree))
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
    monkeypatch.setattr(il, "tree_for", _returns(tree))
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
    monkeypatch.delenv(FLAG, raising=False)
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
    monkeypatch.delenv(FLAG, raising=False)
    off = producible_static_keys()
    assert {"amass_makers", "copy_permanent", "incubate_makers"}.isdisjoint(off)
