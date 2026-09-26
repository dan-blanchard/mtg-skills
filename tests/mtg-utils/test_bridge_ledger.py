"""Convergence hook for the ledgered bridges (ADR-0039).

A ledgered bridge is a gap-gated, corpus-bounded, self-retiring text read
(``mtg_utils._analysis.bridge_ledger``). This suite is the mechanism that
keeps every bridge visible until it retires:

* ``gap`` goes False on a pinned card → the typed substrate now carries the
  structure → the test fails RETIRE-READY: delete the ledger row + its lane
  call, rewrite the mechanism pin structural, keep the membership pin (the
  graduation rule).
* ``match`` goes False while ``gap`` still holds → the diagnostic/text shape
  changed under the pattern (pattern rot) → fix the read, don't widen it.

Runs CI-safe off the committed card snapshot's phase records
(``testkit.test_phase_records``), like ``test_crosswalk.py``; the builder
reads every pin straight from the ledger, so each is in the snapshot. A pin
whose face has no phase record at all (a ``missing_face`` bridge) is built
through the production W2c text-only path off the card's real bulk face
(ADR-0039 W7) — see :func:`_tree`.
"""

import ast
import copy
import dataclasses
import inspect
from collections.abc import Callable
from functools import cache, lru_cache
from pathlib import Path

import pytest

from mtg_utils._analysis import bridge_ledger
from mtg_utils._analysis.bridge_ledger import BRIDGE_KINDS, BRIDGES
from mtg_utils._card_ir.crosswalk import ConceptTree, build_concept_tree, tag_of
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import load_committed_schema
from mtg_utils._card_ir.trees import _text_only_trees
from mtg_utils.testkit import test_card, test_phase_records, test_signals

# ADR-0039 W7: the pins whose face has NO phase record at all (the missing_face
# kind), each mapped to that face — Insult // Injury's and Driven // Despair's
# Aftermath back halves, and the Tomb of Annihilation dungeon phase never parses.
_MISSING_FACE_PINS = {
    "Insult // Injury": "Injury",
    "Driven // Despair": "Despair",
    "Tomb of Annihilation": "Tomb of Annihilation",
}


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


@cache
def _tree(name: str) -> ConceptTree:
    # A frozen tree, never mutated here (``_fixed_view`` copies the nodes it
    # rewrites), so one build per pin serves every check.
    # A missing-face pin has no ``strict_load_card``-able record (a real record
    # would misrepresent the shape — there is nothing for phase to have
    # emitted). Build it via the SAME W2c text-only path production uses, off
    # the card's real bulk face.
    record = test_card(name)
    records = test_phase_records(name)
    if name in _MISSING_FACE_PINS:
        trees = _text_only_trees(record, tuple(records), oracle_id=record["oracle_id"])
        (tree,) = (t for t in trees if t.name == _MISSING_FACE_PINS[name])
        return tree
    rec = next(
        (r for r in records if r["name"] == name),
        next(r for r in records if r["name"] == name.split(" // ", maxsplit=1)[0]),
    )
    root = strict_load_card(rec, _schema(), name=rec["name"])
    return build_concept_tree(root, name=rec["name"])


_PIN_CASES = [(b, pin) for b in BRIDGES.values() for pin in b.pins]


@pytest.mark.parametrize(
    ("bridge", "pin"), _PIN_CASES, ids=[f"{b.bridge_id}:{p}" for b, p in _PIN_CASES]
)
def test_bridge_still_needed_and_serving(bridge, pin):
    tree = _tree(pin)
    assert bridge.gap(tree), (
        f"{bridge.bridge_id}: RETIRE-READY — the typed substrate now carries "
        f"the structure for {pin!r}. Delete the ledger row and its lane call, "
        f"rewrite the mechanism pin structural, keep the membership pin (the "
        f"graduation rule). Retirement path was: {bridge.todo}"
    )
    assert bridge.match(tree), (
        f"{bridge.bridge_id}: pattern rot — the gap still holds for {pin!r} "
        f"but the bounded read no longer matches; fix the read (do not widen "
        f"it past its census: {bridge.census})"
    )
    assert bridge.fires(tree)


def test_ledger_hygiene():
    """Every row is complete: a named retirement path, an authored census,
    at least one pin that resolves to a real card face, a known kind, and an id key that
    matches the row."""
    for bridge_id, b in BRIDGES.items():
        assert bridge_id == b.bridge_id
        assert b.kind in BRIDGE_KINDS, f"{bridge_id}: unknown kind {b.kind!r}"
        assert b.todo.strip(), f"{bridge_id}: empty retirement TODO"
        assert b.census.strip(), f"{bridge_id}: empty census"
        assert b.pins, f"{bridge_id}: no convergence pins"
        for pin in b.pins:
            assert _tree(pin) is not None, f"{bridge_id}: pin {pin!r} has no tree"


# ── ADR-0048: the row owns its emission; no lane names a bridge ──────────────────

_VALID_SCOPES = {"you", "opponents", "each", "any"}


def test_every_row_serves_a_manifest_key_with_a_valid_scope():
    from mtg_utils._analysis.lanes.manifest import SERVED_SIGNAL_KEYS

    for bridge_id, b in BRIDGES.items():
        assert b.key in SERVED_SIGNAL_KEYS, f"{bridge_id}: key {b.key!r} is not served"
        assert b.scope in _VALID_SCOPES, f"{bridge_id}: scope {b.scope!r}"


def test_no_lane_names_a_bridge_id():
    """Retiring a bridge is deleting its row: the lanes package may not contain a
    bridge id literal anywhere (the one ``bridge_signals`` lane fires every row)."""
    from mtg_utils._analysis import lanes

    lanes_dir = Path(lanes.__file__).parent
    for path in lanes_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for bridge_id in BRIDGES:
            assert f'"{bridge_id}"' not in text, f"{path.name} names {bridge_id!r}"


def test_bridge_signals_emits_the_row_for_every_pin():
    from mtg_utils._analysis.bridge_ledger import bridge_signals, bridges_for

    for b in BRIDGES.values():
        assert b in bridges_for(b.key)
        for pin in b.pins:
            sigs = bridge_signals(_tree(pin))
            assert any(s.key == b.key and s.scope == b.scope for s in sigs), (
                f"{b.bridge_id}: no {b.key}/{b.scope} signal for {pin!r}"
            )
            if b.quote_oracle:
                assert any(s.key == b.key and s.text for s in sigs)


# ── Preventive invariants: kind ↔ evidence, gap purity, clause-keyed gaps ────────
# (mtg-utils/CONTEXT.md "Dropped clause" / "Gap predicate" / "Ledgered bridge").
# Each reads the pins' real trees; each was added after a review caught a row
# filed under the wrong kind, a gap re-walking the tree, and a gap keyed on a
# residue CLASS rather than the residue carrying the row's own clause.

_NEUTRAL = "Unrelated parked clause."


def _edited(tree: ConceptTree, texts: dict[str, str], *, oracle: str) -> ConceptTree:
    """A real :class:`ConceptTree` — a deep copy of ``tree`` — whose parked texts
    are rewritten per ``texts`` (residue and hollow-static descriptions, an
    ``Unrecognized`` node's ``text``, and the grounding ``raw`` their concept
    nodes carry) and whose oracle is ``oracle``. Every presence read and every
    raw walk a match makes then sees the same edit, so the view can't drift from
    what the ledger reads."""
    edited = copy.deepcopy(tree)
    for unit in edited.iter_units():
        nodes = [*unit.iter_typed(), *unit.static_defs()]
        for n in nodes:
            if (d := _desc(n)) in texts:
                object.__setattr__(n, "description", texts[d])
            if tag_of(n) == "Unrecognized" and (t := _unrecognized(n)) in texts:
                object.__setattr__(n, "text", texts[t])
        for c in unit.iter_concepts():
            if c.raw in texts:
                object.__setattr__(c, "raw", texts[c.raw])
    return dataclasses.replace(edited, oracle=oracle)


def _desc(node) -> str:
    return getattr(node, "description", "") or ""


def _unrecognized(node) -> str:
    return getattr(node, "text", "") or ""


def _parked_texts(tree) -> list[str]:
    """Every text phase parked rather than parsed: residue descriptions, hollow
    static defs, and ``Unrecognized`` condition/filter nodes' ``text``."""
    unrecognized = [
        _unrecognized(n) for n in tree.iter_typed() if tag_of(n) == "Unrecognized"
    ]
    return list(
        dict.fromkeys([*tree.residues(), *tree.hollow_statics(), *unrecognized])
    )


def _clause_carriers(bridge, tree) -> list[str] | None:
    """The residue / hollow-static texts that carry ``bridge``'s clause on ``tree``:
    each one ALONE (as the whole oracle, the only parked text left saying
    anything) satisfies the match. ``None`` when inconclusive — the match fires
    with no text at all (it reads structure, not the clause's words), so text
    can't locate the clause."""
    texts = _parked_texts(tree)

    def only(keep: str | None) -> ConceptTree:
        return _edited(tree, {t: "" for t in texts if t != keep}, oracle=keep or "")

    if bridge.match(only(None)):
        return None
    return [t for t in texts if bridge.match(only(t))]


def _fixed_view(tree, carriers: list[str]) -> ConceptTree:
    """``tree`` as it reads once phase fixes the clause while an UNRELATED line of
    the same residue class stays parked: each carrier residue / hollow def keeps
    its node but says nothing about the clause."""
    return _edited(tree, dict.fromkeys(carriers, _NEUTRAL), oracle=tree.oracle)


# A misparse is an upstream parse failure that leaves no residue: phase emitted
# the clause as a WRONG typed node, so no parked text carries it. Each entry
# names the wrong node; the check below fails if a listed row ever does carry
# its clause in a residue (the entry is then stale).
_MISPARSE_ROWS = {
    "cheat_kept_destination_hand_misparse": (
        "RevealUntil.kept_destination parsed as 'Hand' when the revealer and "
        "the putter differ"
    ),
    "moku_haste_grant_misscoped_selfref": (
        "the haste grant to OTHER creatures parsed as a SelfRef static def"
    ),
}

# Rows whose match reads structure, not the clause's words: text can't locate
# the clause (``_clause_carriers`` is None on every pin), so the text rules
# can't judge the kind. Each is judged instead by the structural evidence its
# kind allows (see the test). A listed row whose clause text CAN be located is
# stale; an unlisted row whose clause text can't fails the kind test.
_STRUCTURE_MATCHED_ROWS = {
    "kaya_emblem_cast_from_exile_drop": (
        "the emblem's CastFromZone lost its in-exile filter"
    ),
    "warchanter_skald_condition_dropped": ("the Taps trigger has no condition at all"),
    "plus_one_hierophant_previouseffectamount_dropped_kind": (
        "the ModifyCost's counted kind is missing from its operand"
    ),
    "moku_haste_grant_misscoped_selfref": "a misparse (see _MISPARSE_ROWS)",
}


@pytest.mark.parametrize("bridge", list(BRIDGES.values()), ids=list(BRIDGES))
def test_kind_matches_the_pins_evidence(bridge):
    """A row's ``kind`` is a claim about what phase left for its clause, checked
    against every pin (CONTEXT.md "Dropped clause", BRIDGE_KINDS):

    * ``missing_face`` — the pin's tree is text-only (phase emitted no record);
      no other kind's pin is.
    * ``dropped_clause`` — the clause left no node: no residue or hollow static
      on the pin carries it.
    * ``upstream_parse_failure`` — phase tried and failed: a residue or hollow
      static carries the clause, or the row is a listed misparse (a wrong typed
      node, which text can't locate — ``_MISPARSE_ROWS``).
    * ``grammar_straggler`` — OUR grammar's frontier; what phase emitted says
      nothing about it, so there is no mechanical evidence rule.

    A pin whose match fires with no text at all can't be judged by text; its row
    must be listed in ``_STRUCTURE_MATCHED_ROWS`` and is judged structurally: a
    dropped clause's gap reads no residue text (nothing was parked to key on),
    and a parse failure's gap does, unless the row is a listed misparse."""
    for pin in bridge.pins:
        tree = _tree(pin)
        if bridge.kind == "missing_face":
            assert tree.is_text_only, f"{bridge.bridge_id}: {pin!r} has phase units"
            continue
        assert not tree.is_text_only, (
            f"{bridge.bridge_id}: {pin!r} is text-only — the kind is missing_face"
        )
        carriers = _clause_carriers(bridge, tree)
        if carriers is None:
            if bridge.kind == "grammar_straggler":
                continue
            assert bridge.bridge_id in _STRUCTURE_MATCHED_ROWS, (
                f"{bridge.bridge_id}: {pin!r}'s match fires with no text, so the "
                f"kind can't be judged by text — list the row in "
                f"_STRUCTURE_MATCHED_ROWS, or give its match the clause's words"
            )
            keys_on_residue = bool(
                _ledger_hits(bridge.gap.__name__, _residue_text_read)
            )
            if bridge.kind == "dropped_clause":
                assert not keys_on_residue, (
                    f"{bridge.bridge_id}: a dropped clause parks nothing, yet its "
                    f"gap keys on residue text — the kind is upstream_parse_failure"
                )
            elif bridge.kind == "upstream_parse_failure":
                assert keys_on_residue or bridge.bridge_id in _MISPARSE_ROWS, (
                    f"{bridge.bridge_id}: a parse failure with no residue for its "
                    f"gap to key on — a dropped_clause, or a misparse to list"
                )
            continue
        if bridge.kind == "dropped_clause":
            assert not carriers, (
                f"{bridge.bridge_id}: {pin!r}'s clause survives in {carriers!r} — "
                f"phase tried and failed; the kind is upstream_parse_failure"
            )
        elif bridge.kind == "upstream_parse_failure":
            if bridge.bridge_id in _MISPARSE_ROWS:
                assert not carriers, (
                    f"{bridge.bridge_id}: listed as a misparse but {pin!r}'s clause "
                    f"survives in {carriers!r} — drop the _MISPARSE_ROWS entry"
                )
            else:
                assert carriers, (
                    f"{bridge.bridge_id}: no residue or hollow static carries "
                    f"{pin!r}'s clause — a dropped_clause, or a misparse to list "
                    f"in _MISPARSE_ROWS"
                )


def test_misparse_entries_name_parse_failure_rows():
    for bridge_id in _MISPARSE_ROWS:
        assert BRIDGES[bridge_id].kind == "upstream_parse_failure", bridge_id


@pytest.mark.parametrize("bridge_id", sorted(_STRUCTURE_MATCHED_ROWS))
def test_structure_matched_entries_are_live(bridge_id):
    """A listed row really is structure-matched on every phase-parsed pin, and
    of a kind the text rules would otherwise judge."""
    bridge = BRIDGES[bridge_id]
    assert bridge.kind in {"dropped_clause", "upstream_parse_failure"}, bridge_id
    for pin in bridge.pins:
        tree = _tree(pin)
        if tree.is_text_only:
            continue
        assert _clause_carriers(bridge, tree) is None, (
            f"{bridge_id}: {pin!r}'s clause is now located by text — drop the "
            f"_STRUCTURE_MATCHED_ROWS entry"
        )


# CONTEXT.md "Gap predicate": a gate composes the ConceptTree presence reads
# (``has_typed`` / ``has_concept`` / ``has_static_mode`` / ``has_trigger`` /
# ``has_residue`` / ``is_text_only`` over ``iter_typed``; ``residues``,
# ``effect_residues``, ``hollow_statics``; ``iter_concepts`` / ``effect_concepts`` / ``has_effect`` /
# ``is_type``; ``iter_units`` for a unit's own context, read through the unit's
# ``iter_typed`` / ``static_defs`` / ``effects``) and pure predicates over what
# they return. These names are the raw walks it must never make itself:
# ``.units`` is the entry to every per-unit walk, and the two iterators walk a
# unit's node. No exemptions: a gap that needs context the reads don't expose
# gets a new presence read, not a pass.
_RAW_WALK_ATTRS = frozenset({"units"})
_RAW_WALK_NAMES = frozenset({"iter_typed_nodes", "iter_static_defs"})

_LEDGER_FUNCS = {
    n.name: n
    for n in ast.parse(inspect.getsource(bridge_ledger)).body
    if isinstance(n, ast.FunctionDef)
}


def _ledger_hits(name: str, hit: Callable[[str, ast.AST], str | None]) -> set[str]:
    """Every label ``hit`` returns over the AST of ledger function ``name`` and of
    each module-local helper it calls, transitively (each function once)."""
    out: set[str] = set()
    seen, stack = {name}, [name]
    while stack:
        fn = stack.pop()
        for n in ast.walk(_LEDGER_FUNCS[fn]):
            if (label := hit(fn, n)) is not None:
                out.add(label)
            elif isinstance(n, ast.Name) and n.id in _LEDGER_FUNCS and n.id not in seen:
                seen.add(n.id)
                stack.append(n.id)
    return out


def _raw_walk(fn: str, n: ast.AST) -> str | None:
    if isinstance(n, ast.Attribute) and n.attr in _RAW_WALK_ATTRS:
        return f"{fn}: .{n.attr}"
    if isinstance(n, ast.Name) and n.id in _RAW_WALK_NAMES:
        return f"{fn}: {n.id}"
    return None


_RESIDUE_TEXT_READS = frozenset(
    {"residues", "effect_residues", "has_residue", "hollow_statics"}
)


def _residue_text_read(fn: str, n: ast.AST) -> str | None:
    if isinstance(n, ast.Attribute) and n.attr in _RESIDUE_TEXT_READS:
        return f"{fn}: .{n.attr}"
    return None


def _gap_names() -> list[str]:
    return sorted({b.gap.__name__ for b in BRIDGES.values()})


@pytest.mark.parametrize("gap", _gap_names())
def test_gap_composes_presence_reads(gap):
    assert gap in _LEDGER_FUNCS, f"{gap}: a gap must be a module-level def"
    walks = _ledger_hits(gap, _raw_walk)
    assert not walks, (
        f"{gap} re-walks the tree ({sorted(walks)}) — compose the ConceptTree "
        f"presence reads instead, adding one if the context isn't exposed "
        f"(CONTEXT.md 'Gap predicate')"
    )


_RESIDUE_KEYED = [
    (b, pin)
    for b in BRIDGES.values()
    if _ledger_hits(b.gap.__name__, _residue_text_read)
    for pin in b.pins
]


@pytest.mark.parametrize(
    ("bridge", "pin"),
    _RESIDUE_KEYED,
    ids=[f"{b.bridge_id}:{p}" for b, p in _RESIDUE_KEYED],
)
def test_residue_keyed_gap_retires_on_its_own_clause(bridge, pin):
    """A gap that reads residue text keys on the residue carrying ITS clause
    (CONTEXT.md "Gap predicate"): once phase fixes that clause the gap must go
    False — even with an unrelated line of the same residue class still parked —
    so the convergence check reads RETIRE-READY, never pattern rot."""
    tree = _tree(pin)
    carriers = _clause_carriers(bridge, tree)
    if not carriers:
        return  # the clause can't be located by text (see _clause_carriers)
    assert not bridge.gap(_fixed_view(tree, carriers)), (
        f"{bridge.bridge_id}: the gap still holds on {pin!r} after its clause "
        f"{carriers!r} is fixed — it keys on the residue class, not the clause"
    )


def test_no_bridge_fires_where_a_structural_read_already_serves(monkeypatch):
    """A row whose signal the non-bridge lanes already emit for a pin should have
    stood down: its gap missed the structure that arrived (pattern rot the other
    way). Production signals with the bridge lane removed must lack the row's
    ``(key, scope)`` on every pin it fires on."""
    from mtg_utils._analysis import lanes
    from mtg_utils._analysis.bridge_ledger import bridge_signals

    without = tuple(lane for lane in lanes._LANES if lane is not bridge_signals)
    assert len(without) == len(lanes._LANES) - 1
    monkeypatch.setattr(lanes, "_LANES", without)
    served: list[str] = []
    for b in BRIDGES.values():
        for pin in b.pins:
            if not b.fires(_tree(pin)):
                continue
            if (b.key, b.scope) in {(s.key, s.scope) for s in test_signals(pin)}:
                served.append(f"{b.bridge_id}: {pin!r} ({b.key}/{b.scope})")
    assert not served, "structural reads already serve: " + "; ".join(served)
