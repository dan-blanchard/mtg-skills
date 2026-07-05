"""ADR-0037 tree-synthesis stage — CI-safe mechanism + purity tests.

Covers the reusable enabler (no phase/network/bulk): the synth arm fires on a
genuine bucket-B gap and no-ops when phase already carries a typed death node; the
stage preserves the phase L1 fingerprint despite adding a synthetic node; and — the
load-bearing NON-VACUITY property — the relaxed substrate-purity check still
catches a phase-node mutation/removal after a legal synthetic addition.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mtg_utils._card_ir._substrate_purity import (
    SubstratePurityError,
    SynthesizedNode,
    assert_substrate_pure,
    l1_identity,
    l1_nodes,
)
from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptNode, ConceptTree
from mtg_utils._card_ir.tree_synthesis import (
    SYNTHESIS_ARM_IDS,
    _is_creature_death_subject,
    apply_tree_synthesis,
    synthesize_nodes,
)


def _fixture_tree(name: str) -> ConceptTree:
    """Build one committed-fixture card's ConceptTree (CI-safe: no phase/network)."""
    import json
    from pathlib import Path

    from mtg_utils._card_ir.mirror import strict_load_card
    from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema

    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    if not path.exists():
        pytest.skip("crosswalk_fixture_cards.json not present")
    rec = json.loads(Path(path).read_text())["cards"][name]
    root = strict_load_card(rec, load_committed_schema(), name=name)
    return build_tree(root, name)


def build_tree(root: object, name: str) -> ConceptTree:
    from mtg_utils._card_ir.crosswalk import build_concept_tree

    return build_concept_tree(root, name=name)


def _gap_tree(oracle: str) -> ConceptTree:
    """A unit-less tree carrying only oracle text — the bucket-B gap shape (phase
    emitted no typed death node), so the synth arm's structural gate is empty."""
    return ConceptTree(name="Gap", oracle_id="x", oracle=oracle)


# ── the synth arm: fires on a gap, no-ops when a typed death node exists ───────


def test_synth_arm_fires_on_bucket_b_gap():
    tree = _gap_tree("Whenever another creature dies, draw a card.")
    fired = synthesize_nodes(tree)
    assert [arm for arm, _ in fired] == ["death_matters"]
    _arm, node = fired[0]
    assert node.concept == "synth_death_matters"
    assert isinstance(node.node, SynthesizedNode)
    assert node.node.arm_id == "death_matters"


def test_apply_tree_synthesis_adds_one_synthetic_unit():
    tree = _gap_tree("Whenever another creature dies, each opponent loses 1 life.")
    out = apply_tree_synthesis(tree)
    assert len(out.units) == len(tree.units) + 1
    synth = [c for c in out.iter_concepts() if c.concept == "synth_death_matters"]
    assert len(synth) == 1


def test_synth_arm_noops_when_no_death_idiom():
    tree = _gap_tree("Draw two cards. You gain 2 life.")
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_synth_arm_noops_on_bare_self_death():
    # CR 700.4: "When ~ dies" self-death is self_death_payoff, a different lane.
    tree = _gap_tree("When Grim Servant dies, it deals 3 damage to any target.")
    assert synthesize_nodes(tree) == ()


@pytest.mark.parametrize("name", ["Blood Artist", "Bone Picker", "Midnight Reaper"])
def test_synth_arm_noops_when_structural_death_present(name):
    # phase carries a typed death node (a dies trigger / a morbid state check), so
    # the arm fills no gap and the stage returns the tree by identity.
    tree = _fixture_tree(name)
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_is_creature_death_subject_rejects_token_only_subtype():
    # The gap-gate/lane-read shared predicate (CR 700.4): a recognised creature
    # subtype is death; a token-only subtype absent from the card-face vocab
    # (Tentacle — The Watcher in the Water) is NOT recognised structural, so the
    # dies-trigger falls through to the SUBTYPE synth arm instead of the crack.
    assert _is_creature_death_subject(("Creature",))
    assert _is_creature_death_subject(("Zombie",))
    assert _is_creature_death_subject(("Human",))
    assert not _is_creature_death_subject(("Tentacle",))  # token-only, non-vocab
    assert not _is_creature_death_subject(("Clue",))  # non-creature — does not die


def test_synth_recovers_nonvocab_subtype_death():
    # The Watcher in the Water class: "whenever a <non-vocab creature subtype> you
    # control dies" — the lane's creature-subject read cannot resolve the subtype,
    # so the SUBTYPE synth arm recovers it (0 genuine members lost).
    tree = _gap_tree(
        "Whenever a Tentacle you control dies, each opponent loses 1 life."
    )
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["death_matters"]


# ── purity: the stage preserves the phase L1 fingerprint ──────────────────────


def test_synthesized_node_filtered_from_l1_nodes():
    tree = _fixture_tree("Smite")
    phase_nodes = l1_nodes(tree)
    synth_cnode = ConceptNode(
        concept="synth_death_matters",
        node=SynthesizedNode(arm_id="death_matters", description="x"),
        role="effect",
        scope="any",
        subject=("Creature",),
        raw="",
    )
    added = replace(tree.units[0], effects=(*tree.units[0].effects, synth_cnode))
    with_synth = replace(tree, units=(added, *tree.units[1:]))
    # the synthetic ConceptNode's .node is filtered → phase fingerprint unchanged.
    assert l1_nodes(with_synth) == phase_nodes


def test_apply_tree_synthesis_preserves_l1_identity_on_gap_card():
    # a real phase card whose oracle ALSO trips the synth regex: the added synth
    # unit must not disturb the phase L1 identity fingerprint.
    tree = _fixture_tree("Smite")
    # Force a synthesizable oracle while keeping the real phase units intact.
    forced = replace(tree, oracle="Whenever another creature dies, draw a card.")
    before = l1_identity(forced)
    out = apply_tree_synthesis(forced)
    assert out is not forced
    assert l1_identity(out) == before  # phase nodes preserved; synth filtered


# ── NON-VACUITY: the relaxed check still catches a phase-node mutation/removal ─


def test_relaxed_purity_exempts_synthetic_add_but_catches_phase_mutation():
    """The ADR-0037 load-bearing property. After a LEGAL synthetic addition:

    * a synthetic-only add passes (exempt), yet
    * a phase-node MUTATION (byte-identical rebuild → new id) is STILL caught, and
    * a phase-node REMOVAL is STILL caught.

    If this stops raising, the relaxation has silently disabled the whole
    substrate-purity boundary — synthetic additions would be a hole a real leak
    could hide in.
    """
    tree = _fixture_tree("Smite")
    before = l1_identity(tree)

    # (1) a pure synthetic addition is EXEMPT.
    synth_unit = AbilityUnit(
        origin="synth",
        index=len(tree.units),
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(
            ConceptNode(
                concept="synth_death_matters",
                node=SynthesizedNode(arm_id="death_matters", description="x"),
                role="effect",
                scope="any",
                subject=("Creature",),
                raw="",
            ),
        ),
        costs=(),
        statics=(),
    )
    added = replace(tree, units=(*tree.units, synth_unit))
    assert_substrate_pure(before, added)  # passes — synthetic add is exempt

    # (2) a phase-node MUTATION alongside the synthetic add is STILL caught.
    unit0 = tree.units[0]
    eff0 = unit0.effects[0]
    rebuilt = replace(eff0.node)  # byte-identical, NEW object → new id
    assert rebuilt is not eff0.node
    mutated_unit = replace(
        unit0, effects=(replace(eff0, node=rebuilt), *unit0.effects[1:])
    )
    leaked = replace(added, units=(mutated_unit, *added.units[1:]))
    with pytest.raises(SubstratePurityError):
        assert_substrate_pure(before, leaked)

    # (3) a phase-node REMOVAL alongside the synthetic add is STILL caught.
    dropped_unit = replace(unit0, effects=unit0.effects[1:])
    removed = replace(added, units=(dropped_unit, *added.units[1:]))
    with pytest.raises(SubstratePurityError):
        assert_substrate_pure(before, removed)


def test_synthesized_node_is_tag_inert_and_provenance():
    from mtg_utils._card_ir.crosswalk import tag_of

    n = SynthesizedNode(arm_id="death_matters", description="bucket-B")
    assert tag_of(n) is None  # inert to every tag-keyed structural read
    assert n.to_dict() == {"synthesized": "death_matters", "description": "bucket-B"}


def test_synthesis_arm_ids_registered():
    assert "death_matters" in SYNTHESIS_ARM_IDS


def test_death_matters_lane_reads_synth_node_end_to_end():
    """The fold path, mirror-independent: a synth ``death_matters`` node ALONE —
    with an oracle the ``_DEATH_MATTERS_MIRROR`` does NOT match — makes the
    ``_death_matters`` lane emit the signal. Proves the synth read is the ACTIVE
    Tier-1 source the lane will rely on once the mirror is deleted (the full fold).
    """
    from mtg_utils._deck_forge.crosswalk_signals import _death_matters

    synth_cnode = ConceptNode(
        concept="synth_death_matters",
        node=SynthesizedNode(arm_id="death_matters", description="x"),
        role="effect",
        scope="any",
        subject=("Creature",),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth_cnode,),
        costs=(),
        statics=(),
    )
    # oracle deliberately carries no "dies"/"died"/"dying" idiom → mirror silent.
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _death_matters(tree)
    assert any(s.key == "death_matters" for s in sigs)
