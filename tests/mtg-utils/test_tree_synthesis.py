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
    _SPELLCAST_TRIGGER_RX,
    SYNTHESIS_ARM_IDS,
    _arm_spellcast_matters,
    _has_structural_lifegain,
    _is_creature_death_subject,
    _is_self_recursion_return,
    _matches_spellcast_idiom,
    apply_tree_synthesis,
    has_gain_life_amplifier,
    has_life_gained_this_turn,
    has_life_gained_trigger,
    has_repeatable_engine,
    has_self_dies_value,
    has_self_etb_value,
    has_selfloss_engine,
    has_structural_spellcast,
    has_structural_stax_taxes,
    has_structural_superfriends,
    has_structural_symmetric_stax,
    has_structural_tutor,
    has_structural_untap_engine,
    has_trigger_draw_bleed,
    has_value_tap_ability,
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
    assert "attack_matters" in SYNTHESIS_ARM_IDS
    assert "lifegain_matters" in SYNTHESIS_ARM_IDS
    assert "wants_cloning" in SYNTHESIS_ARM_IDS


# ── wants_cloning fold (ADR-0036): Tier-1 reads + bucket-B synth (Gate E) ──────
# The LOW clone-TARGET membership heuristic (CR 707 copy / 704.5j legend rule).
# Arm 1 (legendary creature engine / non-mana tap) + arm 2 (cmc>=5 self-ETB/dies
# value) are structural; the bucket-B synth recovers the modal / conditional-count
# ETB tail phase folds to ``other``. RECOVERED members FIRE; shed over-fires DON'T.


def _wants_cloning_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _wants_cloning

    tree = apply_tree_synthesis(_fixture_tree(name))
    return bool(_wants_cloning(tree))


def test_wants_cloning_arm1_repeatable_engine_fires():
    # Koma: "At the beginning of each upkeep, create a Serpent" — a per-turn engine
    # phase types as a ``phase`` trigger (bucket-A structural read).
    tree = _fixture_tree("Koma, Cosmos Serpent")
    assert has_repeatable_engine(tree)
    assert _wants_cloning_fires("Koma, Cosmos Serpent")


def test_wants_cloning_arm1_value_tap_fires():
    # Krenko: "{T}: Create X 1/1 Goblins" — a non-mana tap engine (bucket-A).
    tree = _fixture_tree("Krenko, Mob Boss")
    assert has_value_tap_ability(tree)
    assert _wants_cloning_fires("Krenko, Mob Boss")


def test_wants_cloning_arm2_self_etb_value_fires():
    # Gyruda: "When ~ enters, mill / reanimate" — a self-ETB value trigger.
    tree = _fixture_tree("Gyruda, Doom of Depths")
    assert has_self_etb_value(tree)
    assert _wants_cloning_fires("Gyruda, Doom of Depths")


def test_wants_cloning_arm2_self_dies_value_fires():
    # Kokusho: "When ~ dies, each opponent loses 5 life" — reuses the death fold's
    # self-dies VALUE predicate.
    tree = _fixture_tree("Kokusho, the Evening Star")
    assert has_self_dies_value(tree)
    assert _wants_cloning_fires("Kokusho, the Evening Star")


@pytest.mark.parametrize("name", ["Baleful Beholder", "Bladecoil Serpent"])
def test_wants_cloning_synth_recovers_modal_etb(name):
    # A modal ("choose one —") / conditional-count ("for each {U}{U} spent, draw")
    # self-ETB whose value phase folds to ``other`` — bucket-B synth recovers it,
    # gap-gated (no structural self-ETB value present).
    tree = _fixture_tree(name)
    assert not has_self_etb_value(tree)
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["wants_cloning"]
    _arm, node = synthesize_nodes(tree)[0]
    assert node.concept == "synth_wants_cloning"
    assert isinstance(node.node, SynthesizedNode)
    assert node.scope == "you"
    assert _wants_cloning_fires(name)


def test_wants_cloning_sheds_lone_mana_dork():
    # Llanowar Elves: the only tap ability is "{T}: Add {G}" (effect ``ramp``), the
    # structural mana-dork carve-out — NOT a clone-worthy value engine (CR 707).
    tree = _fixture_tree("Llanowar Elves")
    assert not has_value_tap_ability(tree)
    assert not _wants_cloning_fires("Llanowar Elves")


def test_wants_cloning_sheds_vanilla_high_cmc_fatty():
    # Colossal Dreadmaw (cmc 6, trample, no ETB/dies value) is not a clone-want.
    tree = _fixture_tree("Colossal Dreadmaw")
    assert not has_self_etb_value(tree)
    assert not has_self_dies_value(tree)
    assert not _wants_cloning_fires("Colossal Dreadmaw")


def test_wants_cloning_synth_gap_gate_aligned_with_lane():
    # The bucket-B synth no-ops when a structural self-ETB/dies value is present
    # (the gap-gate calls the SAME has_self_etb_value / has_self_dies_value the lane
    # fires on) — Gyruda / Kokusho fire structurally, so no synth node is added.
    for name in ("Gyruda, Doom of Depths", "Kokusho, the Evening Star"):
        tree = _fixture_tree(name)
        assert "wants_cloning" not in [arm for arm, _ in synthesize_nodes(tree)]


# ── wants_cloning fold fix (ADR-0036): self-return exclusion + engine recovery ─
# Fix-forward on f1c1c0c. (1) The bucket-B synth must SHED self-return dies-recursion:
# the bare ``_self_dies_value`` regex's ``returns?`` payoff re-admitted the cards the
# structural self-return/shuffle exclusion correctly shed (CR 700.4), so the synth's
# raw-text value gate now routes through :func:`_is_self_recursion_return` (the idiom
# mirror of the structural exclusion). (2) Recover the genuine once-each-turn
# own-ability VALUE engines the repeatable-engine read dropped, without re-admitting
# the restriction / legend-static over-fires (CR 601.3e / 602.5f).


def test_is_self_recursion_return_idiom_precision():
    # SHED: the source returns/reshuffles ITSELF (resilience).
    assert _is_self_recursion_return("return it to the battlefield tapped", "Ojer Taq")
    assert _is_self_recursion_return(
        "you may put it into its owner's library third from the top", "God-Eternal"
    )
    assert _is_self_recursion_return(
        "if he wasn't a Spirit, return this card to the battlefield", "Fang"
    )
    assert _is_self_recursion_return(
        "return it to its owner's hand and create a 1/1 Spirit", "Kaya"
    )
    # KEEP: a return-OTHER payoff (Chivalrous Chevalier) is genuine clone value.
    assert not _is_self_recursion_return(
        "return a creature you control to its owner's hand", "Chivalrous Chevalier"
    )
    assert not _is_self_recursion_return("destroy all nonland permanents", "Child")


def test_wants_cloning_sheds_self_return_dies_recursion():
    # Ivory Gargoyle: "When this creature dies, return it to the battlefield ..." — a
    # self-return (undying-style resilience). The structural has_self_dies_value sheds
    # it (change_zone SelfRef excluded); the bucket-B synth must ALSO shed it. CR 700.4.
    tree = _fixture_tree("Ivory Gargoyle")
    assert not has_self_dies_value(tree)
    assert "wants_cloning" not in [arm for arm, _ in synthesize_nodes(tree)]
    assert not _wants_cloning_fires("Ivory Gargoyle")


def test_wants_cloning_sheds_self_shuffle_back_dies():
    # God-Eternal Rhonas: "When ~ dies ... put it into its owner's library third from
    # the top" — a shuffle-back self-protection rider, not a clone value.
    tree = _fixture_tree("God-Eternal Rhonas")
    assert not has_self_dies_value(tree)
    assert "wants_cloning" not in [arm for arm, _ in synthesize_nodes(tree)]
    assert not _wants_cloning_fires("God-Eternal Rhonas")


def test_wants_cloning_recovers_once_per_turn_cast_permission():
    # Evelyn: "Once each turn, you may play a card from exile ..." — a recurring
    # card-advantage engine phase types as a PlayFromExile permission with
    # frequency=OncePerTurn; has_repeatable_engine reads it structurally (arm 1).
    tree = _fixture_tree("Evelyn, the Covetous")
    assert has_repeatable_engine(tree)
    assert _wants_cloning_fires("Evelyn, the Covetous")


def test_wants_cloning_synth_recovers_mairsil_folded_grant():
    # Mairsil: "has all activated abilities ... activate each ... only once each turn"
    # — the canonical clone-combo target, whose grant phase folds to Unimplemented (a
    # genuine bucket-B parse gap the structural repeatable-engine read can't see).
    tree = _fixture_tree("Mairsil, the Pretender")
    assert not has_repeatable_engine(tree)
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["wants_cloning"]
    assert _wants_cloning_fires("Mairsil, the Pretender")


def test_wants_cloning_sheds_legend_static_cost_reducer():
    # Bruenor Battlehammer: "you may pay {0} rather than pay the equip cost of the
    # first equip ability you activate each turn" — a legend-rule static cost-reducer,
    # NOT a once-each-turn card-advantage engine (CR 601.3e). Stays shed.
    assert not has_repeatable_engine(_fixture_tree("Bruenor Battlehammer"))
    assert not _wants_cloning_fires("Bruenor Battlehammer")


def test_wants_cloning_genuine_bucket_b_etb_survives_exclusion():
    # Baleful Beholder (a modal "choose one —" ETB, one of the genuine bucket-B
    # recoveries) is unaffected by the self-return exclusion (its payoff returns
    # nothing to itself) and keeps firing via the synth.
    assert _wants_cloning_fires("Baleful Beholder")


# ── attack_matters synth arm (ADR-0036 fold) ──────────────────────────────────


def test_attack_synth_fires_on_bucket_b_gap():
    # a "whenever ~ attacks" trigger phase left description-only (the gap shape).
    tree = _gap_tree("Whenever another creature you control attacks, draw a card.")
    fired = synthesize_nodes(tree)
    assert [arm for arm, _ in fired] == ["attack_matters"]
    _arm, node = fired[0]
    assert node.concept == "synth_attack_matters"
    assert isinstance(node.node, SynthesizedNode)
    assert node.node.arm_id == "attack_matters"
    assert node.scope == "you"


def test_attack_synth_fires_on_attacking_causes():
    # the Isshin family (CR 508.2a/603.2) — phase emits no attack trigger.
    tree = _gap_tree(
        "If a creature attacking causes a triggered ability of a permanent you "
        "control to trigger, that ability triggers an additional time."
    )
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["attack_matters"]


def test_attack_synth_fires_on_positive_raid_count():
    # the untyped Raid count ("you attacked with …" — Windbrisk Heights).
    tree = _gap_tree(
        "You may play the exiled card if you attacked with three or more "
        "creatures this turn."
    )
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["attack_matters"]


def test_attack_synth_vetoes_attacks_alone():
    # CR 506.5 / 702.83: "attacks alone" is a single-attacker (exalted/voltron)
    # condition, not the go-wide attack_matters lane.
    tree = _gap_tree("Whenever this creature attacks alone, you draw a card.")
    assert synthesize_nodes(tree) == ()


def test_attack_synth_vetoes_defensive_attacks_you():
    # CR 508.1a: "attacks you" watches the OPPONENT's declaration — a defensive
    # pillowfort trigger, not an offensive attack payoff.
    tree = _gap_tree(
        "Whenever a creature attacks you, it gets -2/-0 until end of turn."
    )
    assert synthesize_nodes(tree) == ()


def test_attack_synth_vetoes_cant_attack_hoser():
    # CR 508.1c: a "can't attack" restriction is a hoser, not a payoff (Bloodthirster
    # — the "already attacked this turn" clause the mirror over-fired on).
    tree = _gap_tree(
        "This creature can't attack a player it has already attacked this turn."
    )
    assert synthesize_nodes(tree) == ()


def test_attack_synth_noops_on_negated_didnt_attack():
    # "didn't attack this turn" is anti-attack durdle, not a payoff — the positive
    # Raid idiom requires past-tense "you attacked".
    tree = _gap_tree(
        "At the beginning of your end step, if this creature didn't attack this "
        "turn, put a +1/+1 counter on it."
    )
    assert synthesize_nodes(tree) == ()


def test_attack_synth_noops_when_no_attack_idiom():
    tree = _gap_tree("Draw two cards. You gain 2 life.")
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_attack_synth_noops_when_structural_attack_present():
    # phase carries a typed attacks trigger (Accorder Paladin — battle cry), so the
    # arm fills no gap and the stage returns the tree by identity.
    tree = _fixture_tree("Accorder Paladin")
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_attack_matters_lane_reads_synth_node_end_to_end():
    """The fold path, mirror-independent: a synth ``attack_matters`` node ALONE —
    with an oracle carrying no attack idiom — makes ``_attack_tapped_matters`` emit
    the signal. Proves the synth read is the ACTIVE Tier-1 source once the mirror is
    deleted.
    """
    from mtg_utils._deck_forge.crosswalk_signals import _attack_tapped_matters

    synth_cnode = ConceptNode(
        concept="synth_attack_matters",
        node=SynthesizedNode(arm_id="attack_matters", description="x"),
        role="effect",
        scope="you",
        subject=(),
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
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _attack_tapped_matters(tree)
    assert any(s.key == "attack_matters" for s in sigs)


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


# ── lifegain_matters synth arm + Tier-1 fold (ADR-0036/0037) ──────────────────


def test_lifegain_synth_fires_on_whenever_you_gain_gap():
    tree = _gap_tree("Whenever you gain life, put a +1/+1 counter on this creature.")
    fired = synthesize_nodes(tree)
    assert [arm for arm, _ in fired] == ["lifegain_matters"]
    _arm, node = fired[0]
    assert node.concept == "synth_lifegain_matters"
    assert isinstance(node.node, SynthesizedNode)
    assert node.node.arm_id == "lifegain_matters"
    assert node.scope == "you"


def test_lifegain_synth_fires_on_gain_or_lose():
    # Moonstone Harbinger / Wax-Wane Witness — the combined "gain OR lose life"
    # trigger is still a your-lifegain payoff (triggers when you gain).
    tree = _gap_tree(
        "Whenever you gain or lose life during your turn, this creature gets +1/+0."
    )
    assert [a for a, _ in synthesize_nodes(tree)] == ["lifegain_matters"]


def test_lifegain_synth_fires_on_gained_this_turn_text():
    # Regna / Licia / Shanna — phase folds "gained life this turn" into untyped text.
    tree = _gap_tree(
        "At the beginning of each end step, if your team gained life this turn, "
        "create two 1/1 white Warrior creature tokens."
    )
    assert [a for a, _ in synthesize_nodes(tree)] == ["lifegain_matters"]


def test_lifegain_synth_noops_on_pure_source():
    # CR 119: "whenever ~ dies, you gain 1 life" is a lifegain SOURCE (makers), not
    # a payoff — the word order is not "whenever YOU gain life" (the death arm may
    # still fire on the dies clause; the LIFEGAIN arm must not).
    tree = _gap_tree("Whenever a creature dies, you gain 1 life.")
    assert "lifegain_matters" not in [a for a, _ in synthesize_nodes(tree)]


def test_lifegain_synth_noops_on_opponent_gain():
    # A hoser that watches an OPPONENT's lifegain is a different lane.
    tree = _gap_tree("Whenever an opponent gains life, that player loses 2 life.")
    assert "lifegain_matters" not in [a for a, _ in synthesize_nodes(tree)]


def test_lifegain_synth_noops_on_no_idiom():
    tree = _gap_tree("Draw two cards. Each player loses 2 life.")
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


@pytest.mark.parametrize(
    ("name", "pred"),
    [
        ("Archangel of Thune", has_life_gained_trigger),  # arm a
        ("Taborax, Hope's Demise", has_trigger_draw_bleed),  # arm b (dies)
        ("Phyrexian Arena", has_trigger_draw_bleed),  # arm b (upkeep — added)
        (
            "Kothophed, Soul Hoarder",
            has_trigger_draw_bleed,
        ),  # arm b (other — recovered)
        (
            "Nikara, Lair Scavenger",
            has_trigger_draw_bleed,
        ),  # arm b (leaves — recovered)
        ("Xathrid Demon", has_selfloss_engine),  # arm c
        ("Accomplished Alchemist", has_life_gained_this_turn),  # arm d
        ("Voracious Wurm", has_life_gained_this_turn),  # arm d (mirror-missed add)
        ("Alhammarret's Archive", has_gain_life_amplifier),  # arm e
    ],
)
def test_lifegain_structural_arms_fire_and_suppress_synth(name, pred):
    # Each structural arm reads a typed node, so the synth gap gate no-ops (the
    # gap-gate-alignment: _has_structural_lifegain calls these SAME predicates).
    tree = _fixture_tree(name)
    assert pred(tree) is True
    assert _has_structural_lifegain(tree) is True
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


@pytest.mark.parametrize(
    "name", ["Sunbond", "Moonstone Harbinger", "Regna, the Redeemer"]
)
def test_lifegain_synth_fires_on_fixture_bucket_b(name):
    # Granted / description-only lifegain payoffs phase emits no typed node for.
    # Membership, not equality: a card may legitimately co-fire another synth arm
    # (Moonstone Harbinger's "Bats you control get +1/+0" is also a type_matters
    # bucket-B gap), so we assert the lifegain arm is AMONG the fired arms.
    tree = _fixture_tree(name)
    assert _has_structural_lifegain(tree) is False
    assert "lifegain_matters" in [a for a, _ in synthesize_nodes(tree)]


def test_lifegain_matters_lane_reads_synth_node_end_to_end():
    """The fold path, mirror-independent: a synth ``lifegain_matters`` node ALONE —
    oracle carrying no lifegain idiom — makes ``_lifegain_matters`` emit the signal.
    Proves the synth read is the ACTIVE Tier-1 source once the mirror is deleted.
    """
    from mtg_utils._deck_forge.crosswalk_signals import _lifegain_matters

    synth_cnode = ConceptNode(
        concept="synth_lifegain_matters",
        node=SynthesizedNode(arm_id="lifegain_matters", description="x"),
        role="effect",
        scope="you",
        subject=(),
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
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _lifegain_matters(tree)
    assert any(s.key == "lifegain_matters" for s in sigs)


@pytest.mark.parametrize("name", ["Blood Artist", "Caustic Hound"])
def test_lifegain_over_fires_are_shed(name):
    """CR 119 over-fire shed (the mirror's cross-clause false positives): a pure
    lifegain SOURCE (Blood Artist — "whenever a creature dies, you gain 1 life") is
    ``lifegain_makers``, NOT ``lifegain_matters``; a symmetric each-player-loses
    drain (Caustic Hound) is neither. The rewritten Tier-1 lane emits no
    ``lifegain_matters`` for either.
    """
    from mtg_utils._deck_forge.crosswalk_signals import _lifegain_matters

    tree = apply_tree_synthesis(_fixture_tree(name))
    assert not any(s.key == "lifegain_matters" for s in _lifegain_matters(tree))


@pytest.mark.parametrize(
    "name",
    [
        "Kothophed, Soul Hoarder",  # trigger event "other" (permanent → graveyard)
        "Nikara, Lair Scavenger",  # trigger event "leaves"
        "Phyrexian Arena",  # trigger event "upkeep"
    ],
)
def test_lifegain_broadened_draw_bleed_recovered(name):
    """ADR-0036 recall-completion: a triggered draw-and-self-bleed engine on a
    NON-dies event (Kothophed "other" / Nikara "leaves" / Phyrexian Arena "upkeep")
    is the SAME repeated card-flow engine the dies-only read missed. The broadened
    :func:`has_trigger_draw_bleed` reads it Tier-1, so the lane fires and the synth
    gap gate no-ops (no double count).
    """
    from mtg_utils._deck_forge.crosswalk_signals import _lifegain_matters

    tree = _fixture_tree(name)
    assert has_trigger_draw_bleed(tree) is True
    assert _has_structural_lifegain(tree) is True
    assert synthesize_nodes(tree) == ()
    assert any(s.key == "lifegain_matters" for s in _lifegain_matters(tree))


# ── arm: spellcast_matters (ADR-0036 fold) ────────────────────────────────────
# The you-cast (Spellslinger) payoff, CR 601.2/603.2. Two Tier-1 arms: a phase
# typed/untyped you-cast trigger (has_structural_spellcast) and the bucket-B
# description-only synth (_arm_spellcast_matters — emblems/sagas/granted, cost
# reducers, recasters). Each named card below is committed to the fixture snapshot.


@pytest.mark.parametrize(
    "name",
    [
        "Archmage Emeritus",  # magecraft compound cast-or-copy event
        "Aetherflux Reservoir",  # untyped "whenever you cast a spell" trigger
    ],
)
def test_spellcast_structural_fires(name):
    # phase carries a typed/untyped you-cast trigger, so the Tier-1 gate reads it
    # directly and the bucket-B synth no-ops (no double count).
    tree = _fixture_tree(name)
    assert has_structural_spellcast(tree) is True
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


@pytest.mark.parametrize(
    "name",
    [
        "Goblin Electromancer",  # static cost reducer ("I&S you cast cost {1} less")
        "Jaya, Fiery Negotiator",  # -8 emblem "cast a red I/S spell, copy it twice"
    ],
)
def test_spellcast_synth_fires_on_bucket_b(name):
    # description-only build-around phase emits no typed cast node for → bucket-B.
    # (Jaya also carries an attack idiom on its -2, so assert membership not sole.)
    tree = _fixture_tree(name)
    assert has_structural_spellcast(tree) is False
    assert "spellcast_matters" in [a for a, _ in synthesize_nodes(tree)]


def test_spellcast_synth_recovers_jaya_color_restricted_emblem():
    """FIX 1: Jaya, Fiery Negotiator's -8 emblem ("Whenever you cast a red instant
    or sorcery spell, copy it twice") is a genuine I/S copy payoff (CR 601.2/603.2)
    — the watched spell IS instant-or-sorcery-typed, "red" is merely an extra
    restriction. The color adjective used to break the bucket-B trigger idiom.
    """
    tree = _fixture_tree("Jaya, Fiery Negotiator")
    assert _matches_spellcast_idiom(tree.oracle or "") is True
    node = _arm_spellcast_matters(tree)
    assert node is not None
    assert node.concept == "synth_spellcast_matters"
    assert node.scope == "you"


@pytest.mark.parametrize(
    "name",
    [
        "Eidolon of the Great Revel",  # symmetric any-caster punisher (no you-scope)
        "Alela, Artful Provocateur",  # artifact/enchantment-only carve-out → type lane
        "Shanid, Sleepers' Scourge",  # FIX 2: "cast a legendary spell" → legends_matter
    ],
)
def test_spellcast_noops(name):
    # neither arm fires: an opponent/any-caster punisher, an
    # artifact/enchantment-only watched spell, and a supertype-restricted
    # (legendary) untyped trigger all route AWAY from I/S Spellslinger density.
    tree = _fixture_tree(name)
    assert has_structural_spellcast(tree) is False
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_spellcast_trigger_rx_color_allowed_only_before_instant_or_sorcery():
    """FIX 1 contract: an optional color/type adjective is permitted ONLY when it
    precedes the "instant or sorcery"/"instant and sorcery" anchor. A color-only
    "a black spell" with no I/S anchor (Mountain Titan, the Defiler cycle) stays
    excluded, matching the structural gate's subtype/supertype carve-out.
    """
    rx = _SPELLCAST_TRIGGER_RX
    # allowed: color before the I/S anchor
    assert rx.search("whenever you cast a red instant or sorcery spell, copy it")
    assert rx.search("whenever you cast a black instant and sorcery spell")
    # unchanged: bare and I/S-typed forms still match
    assert rx.search("whenever you cast an instant or sorcery spell")
    assert rx.search("whenever you cast a spell")
    assert rx.search("whenever you cast a noncreature spell")
    # excluded: color-only with NO I/S anchor (Mountain Titan / Defiler cycle)
    assert not rx.search("whenever you cast a black spell")
    assert not rx.search("whenever you cast a green permanent spell")


def test_spellcast_matters_lane_reads_synth_node_end_to_end():
    """The fold path, mirror-independent: a synth ``spellcast_matters`` node ALONE —
    oracle carrying no spellcast idiom — makes ``_spellcast_matters`` emit the
    signal. Proves the synth read is the ACTIVE Tier-1 source (the deleted
    ``_detect_spellcast_matters`` mirror no longer participates).
    """
    from mtg_utils._deck_forge.crosswalk_signals import _spellcast_matters

    synth_cnode = ConceptNode(
        concept="synth_spellcast_matters",
        node=SynthesizedNode(arm_id="spellcast_matters", description="x"),
        role="effect",
        scope="you",
        subject=(),
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
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _spellcast_matters(tree)
    assert any(s.key == "spellcast_matters" for s in sigs)


def test_spellcast_matters_lane_fires_on_jaya_end_to_end():
    # FIX 1, full lane: apply_tree_synthesis attaches the recovered synth node and
    # the lane emits spellcast_matters for the Jaya emblem.
    from mtg_utils._deck_forge.crosswalk_signals import _spellcast_matters

    tree = apply_tree_synthesis(_fixture_tree("Jaya, Fiery Negotiator"))
    sigs = _spellcast_matters(tree)
    assert any(s.key == "spellcast_matters" for s in sigs)


# ── type_matters fold (ADR-0036/0037 — first SUBJECT-carrying synth arm) ───────


def _type_subjects(name):
    """The type_matters subjects the folded lane emits for a fixture card (over
    the synthesized tree — the real Tier-1 path: Arm B union the synth node)."""
    from mtg_utils._deck_forge.crosswalk_signals import _type_matters_lane

    tree = apply_tree_synthesis(_fixture_tree(name))
    return {s.subject for s in _type_matters_lane(tree) if s.key == "type_matters"}


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # bucket-A / Arm-B structural: phase carries a subject-bearing Typed filter
        # (lord static / count), so the lane fires WITHOUT the synth arm.
        ("Lord of Atlantis", {"Merfolk"}),
        ("Goblin King", {"Goblin"}),
        ("Lovisa Coldeyes", {"Barbarian", "Warrior", "Berserker"}),
    ],
)
def test_type_matters_arm_b_structural(name, subjects):
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_type_matters,
        structural_type_subjects,
    )

    tree = _fixture_tree(name)
    assert subjects <= structural_type_subjects(tree)  # Arm B carries them
    assert _arm_type_matters(tree) is None  # gap-gated: synth adds nothing new
    assert _type_subjects(name) == subjects


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        ("Yuriko, the Tiger's Shadow", {"Ninja"}),  # keyword-implied (ninjutsu)
        ("Bramblewood Paragon", {"Warrior"}),  # description-only tribal
        ("Don Andres, the Renegade", {"Pirate"}),  # TYPE-GRANT ("is a Pirate...")
    ],
)
def test_type_matters_bucket_b_synth(name, subjects):
    """The SUBJECT-carrying synth recovers the tribal subtype phase leaves
    subject-less, gap-gated against Arm B (which carries none of these)."""
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_type_matters,
        structural_type_subjects,
    )

    tree = _fixture_tree(name)
    assert subjects & structural_type_subjects(tree) == set()  # Arm B misses it
    node = _arm_type_matters(tree)
    assert node is not None
    assert node.concept == "synth_type_matters"
    assert set(node.subject) == subjects  # the resolved subtype(s) on the node
    assert _type_subjects(name) == subjects  # lane emits one Signal per element


@pytest.mark.parametrize(
    "name",
    [
        "Craterhoof Behemoth",  # generic "creatures you control" — CARD_TYPE_SUBJECTS
        "Dockside Extortionist",  # Treasure token — NON_CREATURE_TOKEN denylist
        "Greasefang, Okiba Boss",  # Vehicle GY-recursion routes to vehicles_matter
    ],
)
def test_type_matters_shed_overfires(name):
    """The vocab gate sheds a bare card-type noun, a NON_CREATURE_TOKEN artifact
    subtype, and the Vehicle typed-GY-recursion (routed to vehicles_matter, a
    different lane) — no type_matters subject is minted (zero false positives)."""
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_type_matters,
        structural_type_subjects,
    )

    tree = _fixture_tree(name)
    assert structural_type_subjects(tree) == set()
    assert _arm_type_matters(tree) is None
    assert _type_subjects(name) == set()


def test_type_matters_synth_registered():
    assert "type_matters" in SYNTHESIS_ARM_IDS


def test_type_matters_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_type_matters`` node carrying
    a subtype tuple ALONE — oracle carrying no tribal idiom — makes the lane emit
    one type_matters Signal per element (the deleted producers do not participate).
    """
    from mtg_utils._deck_forge.crosswalk_signals import _type_matters_lane

    synth = ConceptNode(
        concept="synth_type_matters",
        node=SynthesizedNode(arm_id="type_matters", description="x"),
        role="effect",
        scope="you",
        subject=("Goblin", "Elf"),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    subs = {s.subject for s in _type_matters_lane(tree) if s.key == "type_matters"}
    assert subs == {"Goblin", "Elf"}


# ── keyword_tribe fold (ADR-0036/0037 — SUBJECT-carrying, per-scope synth) ─────


def _keyword_pairs(name):
    """The (scope, subject) keyword-tribe pairs the folded lane emits for a fixture
    card (over the synthesized tree — Arm B union the synth nodes)."""
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_tribe

    tree = apply_tree_synthesis(_fixture_tree(name))
    return {
        (s.scope, s.subject) for s in _keyword_tribe(tree) if s.key == "keyword_tribe"
    }


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # bucket-A / Arm-B structural: phase carries a controller-You WithKeyword filter
        # (anthem / count), so the lane fires WITHOUT the synth arm.
        (
            "Favorable Winds",
            {"Flying"},
        ),  # "creatures you control with flying get +1/+1"
        ("Winged Portent", {"Flying"}),  # "for each creature you control with flying"
        # keyword-sharing anthem (Odric grants keywords your board already has)
        (
            "Odric, Lunarch Marshal",
            {
                "Deathtouch",
                "Flying",
                "Haste",
                "Hexproof",
                "Indestructible",
                "Lifelink",
                "Menace",
                "Reach",
                "Skulk",
                "Trample",
                "Vigilance",
            },
        ),
    ],
)
def test_keyword_tribe_arm_b_structural(name, subjects):
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_keyword_tribe,
        structural_keyword_subjects,
    )

    tree = _fixture_tree(name)
    assert subjects <= structural_keyword_subjects(tree)  # Arm B carries them
    assert _arm_keyword_tribe(tree) is None  # gap-gated: synth adds nothing new
    assert _keyword_pairs(name) == {("you", s) for s in subjects}


@pytest.mark.parametrize(
    "name",
    [
        "Isperia the Inscrutable",  # keyword TUTOR (search for a creature with flying)
    ],
)
def test_keyword_tribe_bucket_b_synth(name):
    """The SUBJECT-carrying synth recovers a keyword phase leaves keyword-less (a
    tutor), gap-gated against Arm B (which carries none of these), scope "you"."""
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_keyword_tribe,
        structural_keyword_subjects,
    )

    tree = _fixture_tree(name)
    assert structural_keyword_subjects(tree) == set()  # Arm B misses it
    node = _arm_keyword_tribe(tree)
    assert node is not None
    assert node.concept == "synth_keyword_tribe"
    assert node.scope == "you"
    assert "Flying" in node.subject
    assert _keyword_pairs(name) == {("you", "Flying")}


def test_keyword_tribe_any_scope_symmetric_anthem():
    """Inniaz carries BOTH a symmetric-anthem ("creatures with flying") AND a your-tribe
    reference, so the lane emits Flying at scope "any" (the any-scope synth arm) AND
    scope "you" — the two scopes stay distinct through the fold."""
    from mtg_utils._card_ir.tree_synthesis import _arm_keyword_tribe_any

    tree = _fixture_tree("Inniaz, the Gale Force")
    node = _arm_keyword_tribe_any(tree)
    assert node is not None
    assert node.scope == "any"
    assert "Flying" in node.subject
    assert _keyword_pairs("Inniaz, the Gale Force") == {
        ("any", "Flying"),
        ("you", "Flying"),
    }


@pytest.mark.parametrize(
    "name",
    [
        "Wind Drake",  # bare "Flying" keyword — self-granted, references no population
        "Aerial Predation",  # "destroy target creature with flying" — anti-flyer removal
        "Clip Wings",  # edict ("each opponent sacrifices a creature with flying")
    ],
)
def test_keyword_tribe_shed_overfires(name):
    """CR 702: a card that merely HAS a keyword, an anti-keyword removal spell, and an
    edict targeting keyworded creatures are NOT keyword-tribe payoffs — no subject is
    minted (the sacrifice carve-out sheds phase's spurious controller-You edict tag)."""
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_keyword_tribe,
        _arm_keyword_tribe_any,
        structural_keyword_subjects,
    )

    tree = _fixture_tree(name)
    assert structural_keyword_subjects(tree) == set()
    assert _arm_keyword_tribe(tree) is None
    assert _arm_keyword_tribe_any(tree) is None
    assert _keyword_pairs(name) == set()


def test_keyword_tribe_synth_registered():
    assert "keyword_tribe" in SYNTHESIS_ARM_IDS
    assert "keyword_tribe_any" in SYNTHESIS_ARM_IDS


def test_keyword_tribe_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_keyword_tribe`` node carrying a
    keyword tuple at scope "any" — oracle carrying no keyword idiom — makes the lane
    emit one keyword_tribe Signal per element at the node's scope."""
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_tribe

    synth = ConceptNode(
        concept="synth_keyword_tribe",
        node=SynthesizedNode(arm_id="keyword_tribe_any", description="x"),
        role="effect",
        scope="any",
        subject=("Flying", "Menace"),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    pairs = {
        (s.scope, s.subject) for s in _keyword_tribe(tree) if s.key == "keyword_tribe"
    }
    assert pairs == {("any", "Flying"), ("any", "Menace")}


# ── mass_death_payoff synth arm + Tier-1 fold (ADR-0036/0037) ─────────────────
# The AGGREGATE board-wipe payoff (CR 700.4): a value/effect scaling with the
# NUMBER of creatures that died this turn. Bucket-A reads the died-count in an
# effect AMOUNT position (:func:`mass_death_amount`); the cost-reduction /
# Unimplemented tail is a bucket-B synth. The morbid single-death conditional ("if
# a creature died this turn" — Bone Picker, Tragic Slip) carries the SAME count in
# a comparison operand and is death_matters, NOT this lane — the amount-vs-condition
# boundary the fold must preserve.


def _mass_death_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _mass_death_payoff

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "mass_death_payoff" for s in _mass_death_payoff(tree))


def test_mass_death_synth_registered():
    assert "mass_death_payoff" in SYNTHESIS_ARM_IDS


@pytest.mark.parametrize(
    "name",
    [
        "Gadrak, the Crown-Scourge",  # bucket-A: Token.count amount read
        "Body Count",  # bucket-A add: Draw.count "died under your control this turn"
        "Blood for the Blood God!",  # bucket-B synth: cost-reduction (operand dropped)
        "Tobias, Doomed Conqueror",  # bucket-B synth: Unimplemented tail
    ],
)
def test_mass_death_lane_fires_on_recovered_members(name):
    assert _mass_death_fires(name)


@pytest.mark.parametrize("name", ["Bone Picker", "Tragic Slip"])
def test_mass_death_lane_sheds_morbid_conditional(name):
    # The morbid single-death conditional is death_matters, not mass_death: the
    # died-count sits in a comparison operand, never an effect amount.
    assert not _mass_death_fires(name)


@pytest.mark.parametrize("name", ["Gadrak, the Crown-Scourge", "Body Count"])
def test_mass_death_amount_reads_aggregate_and_gates_synth(name):
    # The amount arm fires structurally AND suppresses the synth (the gap gate calls
    # the SAME predicate the lane fires on — no double-count, no drift).
    from mtg_utils._card_ir.tree_synthesis import mass_death_amount

    base = _fixture_tree(name)
    assert mass_death_amount(base) is True
    synth = apply_tree_synthesis(base)
    assert not any(
        c.concept == "synth_mass_death_payoff" for c in synth.iter_concepts()
    )


@pytest.mark.parametrize("name", ["Bone Picker", "Tragic Slip"])
def test_mass_death_amount_excludes_comparison_operand(name):
    # A creatures-died count in a comparison ``lhs`` (morbid CONDITION) is NOT an
    # amount — the boundary that keeps the lane off death_matters cards.
    from mtg_utils._card_ir.tree_synthesis import mass_death_amount

    assert mass_death_amount(_fixture_tree(name)) is False


@pytest.mark.parametrize(
    "name", ["Blood for the Blood God!", "Tobias, Doomed Conqueror"]
)
def test_mass_death_synth_fires_on_bucket_b(name):
    tree = apply_tree_synthesis(_fixture_tree(name))
    assert any(c.concept == "synth_mass_death_payoff" for c in tree.iter_concepts())


def test_mass_death_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_mass_death_payoff`` node ALONE
    — oracle carrying no aggregate idiom — makes the ``_mass_death_payoff`` lane
    emit the signal (proves the synth read is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _mass_death_payoff

    synth = ConceptNode(
        concept="synth_mass_death_payoff",
        node=SynthesizedNode(arm_id="mass_death_payoff", description="x"),
        role="effect",
        scope="you",
        subject=(),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _mass_death_payoff(tree)
    assert any(s.key == "mass_death_payoff" for s in sigs)


# ── untap_engine fold (ADR-0036/0037) ──────────────────────────────────────────


def _untap_fires(name):
    from mtg_utils._deck_forge.crosswalk_signals import _untap_engine

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "untap_engine" for s in _untap_engine(tree))


@pytest.mark.parametrize(
    "name",
    [
        "Seedborn Muse",  # untap-during-each-other-player's-untap-step static
        "Candelabra of Tawnos",  # direct SetTapState, "lands" core type, X-count
        "Arbor Elf",  # direct SetTapState, LAND SUBTYPE (Forest) — widened read
        "Twiddle",  # TargetOnly + ChooseOneOf carrier ("you may tap or untap")
        "Elder Druid",  # same Twiddle-family carrier, activated ability
        "Bear Umbra",  # GrantTrigger-nested Twiddle carrier (granted aura ability)
        "Halo Fountain",  # EffectCost activation-cost carrier ("Untap a tapped…:")
        "Bender's Waterskin",  # SELF-scoped untap-during-each-step static
    ],
)
def test_untap_engine_bucket_a_structural(name):
    tree = _fixture_tree(name)
    assert has_structural_untap_engine(tree) is True
    assert _untap_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Quest for Renewal",  # counter-gated conditional static, no typed payload
        "Curse of Inertia",  # "may tap or untap" folds to a bare Tap SetTapState
        "Zariel, Archduke of Avernus",  # granted emblem ability, unstructured
    ],
)
def test_untap_engine_bucket_b_synth(name):
    tree = _fixture_tree(name)
    assert has_structural_untap_engine(tree) is False  # genuine gap
    from mtg_utils._card_ir.tree_synthesis import _arm_untap_engine

    node = _arm_untap_engine(tree)
    assert node is not None
    assert node.concept == "synth_untap_engine"
    assert node.scope == "you"
    assert _untap_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Threaten",  # untap + gain_control sibling — a steal, not an engine
        "Soldevi Golem",  # untap TARGETS an opponent-controlled creature
        "Ashaya, Soul of the Wild",  # CR 205.1a type-change; untaps nothing itself
    ],
)
def test_untap_engine_shed_overfires(name):
    from mtg_utils._card_ir.tree_synthesis import _arm_untap_engine

    tree = _fixture_tree(name)
    assert has_structural_untap_engine(tree) is False
    assert _arm_untap_engine(tree) is None
    assert _untap_fires(name) is False


def test_untap_engine_synth_registered():
    assert "untap_engine" in SYNTHESIS_ARM_IDS


def test_untap_engine_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_untap_engine`` node ALONE
    — oracle carrying no untap idiom — makes the ``_untap_engine`` lane emit
    the signal (proves the synth read is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _untap_engine

    synth = ConceptNode(
        concept="synth_untap_engine",
        node=SynthesizedNode(arm_id="untap_engine", description="x"),
        role="effect",
        scope="you",
        subject=(),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _untap_engine(tree)
    assert any(s.key == "untap_engine" for s in sigs)


# ── tutor fold (ADR-0036/0037) ─────────────────────────────────────────────────


def _tutor_fires(name):
    from mtg_utils._deck_forge.crosswalk_signals import _tutor_lane

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "tutor" for s in _tutor_lane(tree))


@pytest.mark.parametrize(
    "name",
    [
        "Demonic Tutor",  # direct SearchLibrary, no target_player -- self
        "Muddle the Mixture",  # Transmute keyword self search -- recovered
    ],
)
def test_tutor_bucket_a_structural(name):
    tree = _fixture_tree(name)
    assert has_structural_tutor(tree) is True
    assert _tutor_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Kaito Shizuki",  # emblem-granted future search, unstructured text
        "Rampant, Growth",  # bare Unimplemented top-level effect
        "Demolition Field",  # self search alongside a directed sibling search
        # -- no target_player marker at all on the "you may search" node
        # (the same phase gap as the plain rescue cases), rescued by the
        # own-library idiom; the directed-veto's "your library" escape
        # hatch keeps the sibling directed search from suppressing it.
    ],
)
def test_tutor_bucket_b_synth(name):
    tree = _fixture_tree(name)
    assert has_structural_tutor(tree) is False  # genuine gap
    from mtg_utils._card_ir.tree_synthesis import _arm_tutor

    node = _arm_tutor(tree)
    assert node is not None
    assert node.concept == "synth_tutor"
    assert node.scope == "you"
    assert _tutor_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Bribery",  # opponent's library (target_player carries Opponent)
        "Path to Exile",  # compensation search -- ParentTargetController
        "Ash Barrens",  # Typecycling-reminder land search, ability_tag=Cycling
        "Sadistic Sacrament",  # directed search, no typed direction marker
    ],
)
def test_tutor_shed_overfires(name):
    tree = _fixture_tree(name)
    assert has_structural_tutor(tree) is False
    assert _tutor_fires(name) is False


def test_tutor_synth_registered():
    assert "tutor" in SYNTHESIS_ARM_IDS
    assert "tutor_directed" in SYNTHESIS_ARM_IDS


def test_tutor_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_tutor`` node ALONE --
    oracle carrying no tutor idiom -- makes the ``_tutor_lane`` lane emit the
    signal (proves the synth read is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _tutor_lane

    synth = ConceptNode(
        concept="synth_tutor",
        node=SynthesizedNode(arm_id="tutor", description="x"),
        role="effect",
        scope="you",
        subject=(),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _tutor_lane(tree)
    assert any(s.key == "tutor" for s in sigs)


# ── stax_taxes / symmetric_stax fold (ADR-0036/0037) ───────────────────────────


def _stax_fires(name):
    from mtg_utils._deck_forge.crosswalk_signals import _stax_lanes

    tree = apply_tree_synthesis(_fixture_tree(name))
    keys = {s.key for s in _stax_lanes(tree)}
    return "stax_taxes" in keys, "symmetric_stax" in keys


@pytest.mark.parametrize(
    "name",
    [
        "Propaganda",  # CantAttack, affected controller Opponent
        "Stranglehold",  # CantSearchLibrary, cause Opponents
    ],
)
def test_stax_taxes_bucket_a_structural(name):
    tree = _fixture_tree(name)
    assert has_structural_stax_taxes(tree) is True
    stax, _sym = _stax_fires(name)
    assert stax is True


def test_symmetric_stax_bucket_a_structural():
    tree = _fixture_tree("Bedlam")
    assert has_structural_symmetric_stax(tree) is True
    _stax, sym = _stax_fires("Bedlam")
    assert sym is True


def test_stax_taxes_bucket_b_synth():
    """Platinum Angel: 'your opponents can't win the game' -- phase emits a
    typed CantWinTheGame static (affected controller Opponent), but the
    structural census has no arm reading that mode -- a genuine bucket-B
    gap the deleted _STAX_TAXES_RESIDUE_RE covered; the synth relocates it."""
    tree = _fixture_tree("Platinum Angel")
    assert has_structural_stax_taxes(tree) is False  # genuine gap
    from mtg_utils._card_ir.tree_synthesis import _arm_stax_taxes

    node = _arm_stax_taxes(tree)
    assert node is not None
    assert node.concept == "synth_stax_taxes"
    assert node.scope == "opponents"
    stax, _sym = _stax_fires("Platinum Angel")
    assert stax is True


def test_symmetric_stax_bucket_b_synth():
    """Winter Orb: 'players can't untap more than one land' -- an
    Unimplemented player-lock idiom phase drops wholly; the deleted
    _SYMMETRIC_STAX_RESIDUE_RE covered it, the synth relocates it."""
    tree = _fixture_tree("Winter Orb")
    assert has_structural_symmetric_stax(tree) is False  # genuine gap
    from mtg_utils._card_ir.tree_synthesis import _arm_symmetric_stax

    node = _arm_symmetric_stax(tree)
    assert node is not None
    assert node.concept == "synth_symmetric_stax"
    assert node.scope == "each"
    _stax, sym = _stax_fires("Winter Orb")
    assert sym is True


@pytest.mark.parametrize(
    "name",
    [
        "Pacifism",  # single-target Aura pacify (EnchantedBy) -- gate (i) veto
        "Arrest",  # single-target Aura pacify (EnchantedBy) -- gate (i) veto
    ],
)
def test_stax_shed_overfires(name):
    from mtg_utils._card_ir.tree_synthesis import (
        _arm_stax_taxes,
        _arm_symmetric_stax,
    )

    tree = _fixture_tree(name)
    assert has_structural_stax_taxes(tree) is False
    assert has_structural_symmetric_stax(tree) is False
    assert _arm_stax_taxes(tree) is None
    assert _arm_symmetric_stax(tree) is None
    stax, sym = _stax_fires(name)
    assert stax is False
    assert sym is False


def test_stax_synth_registered():
    assert "stax_taxes" in SYNTHESIS_ARM_IDS
    assert "symmetric_stax" in SYNTHESIS_ARM_IDS


def test_stax_lane_reads_synth_nodes_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_stax_taxes`` /
    ``synth_symmetric_stax`` node ALONE -- oracle carrying no stax idiom --
    makes the ``_stax_lanes`` lane emit both signals (proves the synth read
    is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _stax_lanes

    stax_synth = ConceptNode(
        concept="synth_stax_taxes",
        node=SynthesizedNode(arm_id="stax_taxes", description="x"),
        role="effect",
        scope="opponents",
        subject=(),
        raw="",
    )
    sym_synth = ConceptNode(
        concept="synth_symmetric_stax",
        node=SynthesizedNode(arm_id="symmetric_stax", description="x"),
        role="effect",
        scope="each",
        subject=(),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(stax_synth, sym_synth),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _stax_lanes(tree)
    keys = {s.key for s in sigs}
    assert "stax_taxes" in keys
    assert "symmetric_stax" in keys


# ── superfriends_matters fold (ADR-0036/0037) ──────────────────────────────────


def _superfriends_fires(name):
    from mtg_utils._deck_forge.crosswalk_signals import _superfriends_matters

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "superfriends_matters" for s in _superfriends_matters(tree))


@pytest.mark.parametrize(
    "name",
    [
        "Historian of Zhalfir",  # condition-site ControlsType
        "Arisen Gorgon",  # condition-site IsPresent
        "Companion of the Trials",  # YouControlNamedPlaneswalker gate
        "Chandra, Acolyte of Flame",  # loyalty-counter EFFECT, non-Opp target
        "Sorin, Vengeful Bloodlord",  # PW-anthem static `affected` filter
        "The Chain Veil",  # GrantExtraLoyaltyActivations
    ],
)
def test_superfriends_bucket_a_structural(name):
    tree = _fixture_tree(name)
    assert has_structural_superfriends(tree) is True
    assert _superfriends_fires(name) is True


def test_superfriends_bucket_b_synth():
    """Oath of Teferi's "activate the loyalty abilities of planeswalkers you
    control twice each turn" is a permission ability phase leaves with no
    typed carrier — a genuine bucket-B gap the synth idiom recovers."""
    tree = _fixture_tree("Oath of Teferi")
    assert has_structural_superfriends(tree) is False  # genuine gap
    from mtg_utils._card_ir.tree_synthesis import _arm_superfriends_matters

    node = _arm_superfriends_matters(tree)
    assert node is not None
    assert node.concept == "synth_superfriends_matters"
    assert node.scope == "you"
    assert _superfriends_fires("Oath of Teferi") is True


@pytest.mark.parametrize(
    "name",
    [
        "Chandra's Defeat",  # TargetMatchesFilter — removal on the spell's own target
        "Hero's Downfall",  # a bare removal-target naming Planeswalker
        "Jace Beleren",  # BEING a planeswalker is membership, not caring
        "Hunter's Insight",  # generic damage-recipient event plumbing
        "Flitterwing Nuisance",  # same event-plumbing family
        "Chandra, Fire Artisan",  # self-only loyalty reference (no group marker)
    ],
)
def test_superfriends_shed_overfires(name):
    from mtg_utils._card_ir.tree_synthesis import _arm_superfriends_matters

    tree = _fixture_tree(name)
    assert has_structural_superfriends(tree) is False
    assert _arm_superfriends_matters(tree) is None
    assert _superfriends_fires(name) is False


def test_superfriends_synth_registered():
    assert "superfriends_matters" in SYNTHESIS_ARM_IDS


def test_superfriends_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_superfriends_matters``
    node ALONE — oracle carrying no superfriends idiom — makes the
    ``_superfriends_matters`` lane emit the signal (proves the synth read is
    the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _superfriends_matters

    synth = ConceptNode(
        concept="synth_superfriends_matters",
        node=SynthesizedNode(arm_id="superfriends_matters", description="x"),
        role="effect",
        scope="you",
        subject=(),
        raw="",
    )
    unit = AbilityUnit(
        origin="synth",
        index=0,
        node=SynthesizedNode(arm_id="_unit", description="u"),
        kind=None,
        trigger_event=None,
        effects=(synth,),
        costs=(),
        statics=(),
    )
    tree = ConceptTree(
        name="X", oracle_id="x", oracle="Do something unrelated.", units=(unit,)
    )
    sigs = _superfriends_matters(tree)
    assert any(s.key == "superfriends_matters" for s in sigs)
