"""ADR-0035 Stage-3b (c) — dropped-clause synthesis + input-side convergence.

CI-safe tests (no phase / bulk / network): the SYNTHESIS_ARMS registry, the
firing / convergence MECHANISM on synthetic compat Cards, idempotence, and the
shared substrate-purity guard's non-vacuity. The corpus-wide LIVE/CONVERGED
assertion is a gated test at the bottom (needs the local phase card-data + bulk).
"""

from __future__ import annotations

import os

import pytest

from mtg_utils._card_ir.dropped_clauses import (
    _DEFERRED_RAW_ARMS,
    _DEFERRED_TRIGGER_ARMS,
    ARM_NAMES,
    SYNTHESIS_ARMS,
    apply_dropped_clause_synthesis,
    synthesize_with_trace,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter

# ── the applied-arm registry (non-vacuity of the ported set) ──────────────────


def test_synthesis_arms_is_non_empty_and_unique():
    """The applied (c) arm set is real (23 arms) with no duplicate keys — a vacuous
    registry would make every downstream convergence assertion worthless."""
    assert len(SYNTHESIS_ARMS) == 23
    assert len(ARM_NAMES) == len(set(ARM_NAMES)) == 23


def test_deferred_arms_are_not_applied():
    """The deferred (c) arms — the trigger-synthesizers that over-fire on the compat
    base (depend on project-only pre-passes) and the per-effect-raw readers that
    can't fire on this seam — are never applied, and never collide with the applied
    set. This is the cut_check-holding + false-convergence-avoiding exclusion."""
    assert set(_DEFERRED_TRIGGER_ARMS) == {
        "combat_damage_recipients",
        "damage_to_opp",
        "opponent_cast_scope",
    }
    assert set(_DEFERRED_RAW_ARMS) == {
        "becomes_tap_untap",
        "modal_mass_exile",
        "discard_unless",
    }
    deferred = set(_DEFERRED_TRIGGER_ARMS) | set(_DEFERRED_RAW_ARMS)
    assert not (deferred & set(ARM_NAMES))


# ── the firing / convergence MECHANISM (synthetic compat Cards) ────────────────


def _card(oracle_name: str, abilities: tuple[Ability, ...]) -> Card:
    return Card(
        oracle_id="x",
        name=oracle_name,
        faces=(Face(name=oracle_name, abilities=abilities),),
    )


def test_colorless_subject_fires_on_a_dropped_clause():
    """A card that references a colorless creature but whose compat effects carry no
    ``ColorCount:EQ:0`` predicate is a GAP: the arm fires and synthesizes the
    marker (the mirror-built card lacks the structure phase dropped)."""
    gap = _card(
        "Test Colorless Payoff",
        (Ability(kind="static", effects=(Effect(category="other"),)),),
    )
    _card_out, fired = synthesize_with_trace(
        gap, "Colorless creatures you control get +1/+1."
    )
    assert "colorless_subject" in fired


def test_colorless_subject_converges_when_structure_present():
    """When the compat card ALREADY carries the ``ColorCount:EQ:0`` predicate — the
    state a future pin reaches when phase parses the qualifier — the arm's guard
    trips and it NO-OPS: CONVERGED. This is exactly the input-side convergence
    signal the check reads."""
    parsed = _card(
        "Test Colorless Payoff",
        (
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="other",
                        subject=Filter(
                            controller="you", predicates=("ColorCount:EQ:0",)
                        ),
                    ),
                ),
            ),
        ),
    )
    _card_out, fired = synthesize_with_trace(
        parsed, "Colorless creatures you control get +1/+1."
    )
    assert "colorless_subject" not in fired


def test_historic_subject_fires_and_converges():
    """Same gap→converge mechanism for a second arm (historic_matters), so the
    convergence check is proven on more than one clause shape."""
    oracle = "You may cast historic spells as though they had flash."
    gap = _card(
        "Test Historic Payoff",
        (Ability(kind="static", effects=(Effect(category="other"),)),),
    )
    _out, fired = synthesize_with_trace(gap, oracle)
    assert "historic_subject" in fired

    parsed = _card(
        "Test Historic Payoff",
        (
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="other",
                        subject=Filter(controller="you", predicates=("Historic",)),
                    ),
                ),
            ),
        ),
    )
    _out2, fired2 = synthesize_with_trace(parsed, oracle)
    assert "historic_subject" not in fired2


def test_no_arm_fires_on_an_inert_card():
    """A vanilla card (no dropped clause in its oracle) triggers no synthesis —
    the arms are guarded, not blanket appenders."""
    inert = _card(
        "Grizzly Bears",
        (Ability(kind="static", effects=(Effect(category="other"),)),),
    )
    out, fired = synthesize_with_trace(inert, "")
    assert fired == frozenset()
    assert out == inert


def test_apply_is_idempotent():
    """Running the stage twice equals running it once (every arm guards on the
    structure it adds) — the load-bearing property for re-entrancy."""
    gap = _card(
        "Test Colorless Payoff",
        (Ability(kind="static", effects=(Effect(category="other"),)),),
    )
    oracle = "Colorless creatures you control get +1/+1."
    once = apply_dropped_clause_synthesis(gap, oracle)
    twice = apply_dropped_clause_synthesis(once, oracle)
    assert twice == once


# ── the shared substrate-purity guard's non-vacuity (bucket-b + bucket-c home) ─


def _fixture_tree(name: str):
    """Build one committed-fixture card's ConceptTree (CI-safe: no phase/network)."""
    import json
    from pathlib import Path

    from mtg_utils._card_ir.crosswalk import build_concept_tree
    from mtg_utils._card_ir.mirror import strict_load_card
    from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema

    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    if not path.exists():
        pytest.skip("crosswalk_fixture_cards.json not present")
    rec = json.loads(Path(path).read_text())["cards"][name]
    root = strict_load_card(rec, load_committed_schema(), name=name)
    return build_concept_tree(root, name=name)


def test_shared_substrate_purity_guard_is_not_vacuous():
    """The shared id-based guard (now the home for BOTH overlay_corrections and
    dropped_clauses) catches a byte-identical L1 node swap that the byte-level
    ``l1_bytes`` check is blind to. If this stops raising, every substrate-purity
    assertion the two stages make is worthless — the load-bearing failure path for
    the whole Layer-2 boundary.

    Simulates the exact illegal move an arm could make: rebuild ONE L1 mirror node
    (``dataclasses.replace`` on the frozen node → byte-identical but NEW object) and
    land it at its tree position."""
    from dataclasses import replace

    from mtg_utils._card_ir._substrate_purity import (
        SubstratePurityError,
        assert_substrate_pure,
        l1_bytes,
        l1_identity,
    )

    tree = _fixture_tree("Smite")
    before = l1_identity(tree)

    unit = tree.units[0]
    effect0 = unit.effects[0]
    rebuilt = replace(effect0.node)  # byte-identical, NEW object
    assert rebuilt is not effect0.node
    assert rebuilt.to_dict() == effect0.node.to_dict()
    leaked_unit = replace(
        unit, effects=(replace(effect0, node=rebuilt), *unit.effects[1:])
    )
    leaked = replace(tree, units=(leaked_unit, *tree.units[1:]))

    # byte-check BLIND to the swap …
    assert l1_bytes(leaked) == l1_bytes(tree)
    # … id-based guard catches it (the load-bearing failure path).
    with pytest.raises(SubstratePurityError):
        assert_substrate_pure(before, leaked)


# ── gated corpus convergence (needs local phase card-data + bulk; never CI) ────


@pytest.mark.skipif(
    not os.environ.get("MTG_SKILLS_RUN_CONVERGENCE"),
    reason="corpus convergence scan is gated (needs phase card-data + bulk); "
    "set MTG_SKILLS_RUN_CONVERGENCE=1 to run",
)
def test_all_applied_arms_are_live_at_the_pin():
    """Every currently-applied (c) arm still FINDS A GAP (fires on >=1 corpus card)
    at the phase pin — none has silently converged. When a future pin bump teaches
    phase to parse a clause, that arm drops to 0 firings and this test NAMES it as
    retire-ready. Grounded on the strict mirror (the compat card the arm reads is
    built from the mirror)."""
    import json
    from pathlib import Path

    from mtg_utils import _phase
    from mtg_utils._card_ir.card_ir_convergence import (
        convergence_verdicts,
        scan_arm_firings,
    )
    from mtg_utils._card_ir.mirror.build import load_committed_schema
    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    bulk_path = default_bulk_path()
    assert bulk_path is not None, "no bulk; run download-mtgjson"
    data = json.loads(Path(_phase.ensure_card_data()).read_text())
    records = list(data.values()) if isinstance(data, dict) else list(data)
    bulk_index: dict[str, dict] = {}
    for c in load_bulk_cards(bulk_path):
        oid = c.get("oracle_id")
        if oid and oid not in bulk_index:
            bulk_index[oid] = c
    firings, scanned = scan_arm_firings(records, bulk_index, load_committed_schema())
    assert scanned > 10000
    verdicts = convergence_verdicts(firings)
    converged = [a for a in ARM_NAMES if verdicts[a] == "CONVERGED"]
    assert not converged, (
        f"arms converged (retire-ready) at this pin: {converged} — "
        "retire them from dropped_clauses.SYNTHESIS_ARMS"
    )
