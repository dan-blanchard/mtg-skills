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
from mtg_utils._card_ir.mirror.generated_types import (
    S_static_abilities,
    T_affected__SelfRef,
    T_affected__Typed,
    T_effect__BounceAll,
    T_effect__Counter,
    T_effect__DestroyAll,
    T_effect__GenericEffect,
    T_filters__StackSpell,
    T_filters__Typed,
    T_modifications__AddPower,
    T_modifications__AddToughness,
    T_properties__HasColor,
    T_properties__Owned,
    T_target__And,
    T_target__Typed,
)
from mtg_utils._card_ir.tree_synthesis import (
    _SPELLCAST_TRIGGER_RX,
    SYNTHESIS_ARM_IDS,
    _arm_animate_artifact,
    _arm_clue_matters,
    _arm_color_change,
    _arm_color_hoser,
    _arm_crimes_matter,
    _arm_curse_matters,
    _arm_flash_matters,
    _arm_island_matters,
    _arm_life_payment_insurance,
    _arm_manland,
    _arm_opponent_exile_matters,
    _arm_pump_makers,
    _arm_sacrifice_protection,
    _arm_spellcast_matters,
    _arm_suspect_matters,
    _arm_suspend_matters,
    _arm_vehicles_matter,
    _arm_void_warp_makers,
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
    has_structural_arcane,
    has_structural_clue_matters,
    has_structural_color_hoser,
    has_structural_counter_distribute,
    has_structural_crimes_matter,
    has_structural_curse_matters,
    has_structural_keyword_counter,
    has_structural_life_payment_insurance,
    has_structural_manland,
    has_structural_outlaw,
    has_structural_proliferate,
    has_structural_pump_makers,
    has_structural_self_counter_grow,
    has_structural_spellcast,
    has_structural_stax_taxes,
    has_structural_superfriends,
    has_structural_suspend_matters,
    has_structural_symmetric_stax,
    has_structural_theft_makers,
    has_structural_tutor,
    has_structural_untap_engine,
    has_structural_vehicles_matter,
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
    # gap-gated (no structural self-ETB value present). Baleful Beholder's "Fear
    # Ray — Creatures you control gain menace" modal ALSO independently
    # synthesizes evasion_self (ADR-0036 fold, a genuine grant, unrelated to
    # this wants_cloning claim) — filter to the arm under test.
    tree = _fixture_tree(name)
    assert not has_self_etb_value(tree)
    fired = dict(synthesize_nodes(tree))
    assert "wants_cloning" in fired
    node = fired["wants_cloning"]
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
    # condition, not the go-wide attack_matters lane. It correctly co-fires
    # the ADR-0036 exalted_lone_attacker bucket-B arm instead (the SAME
    # idiom is genuinely that lane's turf) — updated when that arm landed.
    tree = _gap_tree("Whenever this creature attacks alone, you draw a card.")
    fired = dict(synthesize_nodes(tree))
    assert "attack_matters" not in fired
    assert "exalted_lone_attacker" in fired


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
    # (ADR-0036/0037 self_counter_grow fold): this text ALSO genuinely puts a
    # +1/+1 counter on the source itself, so the self_counter_grow bucket-B
    # arm co-fires — the evasion_self/exalted_lone_attacker precedent for a
    # new arm legitimately widening a shared-text assertion.
    tree = _gap_tree("Whenever you gain life, put a +1/+1 counter on this creature.")
    fired = dict(synthesize_nodes(tree))
    assert set(fired) == {"lifegain_matters", "self_counter_grow"}
    node = fired["lifegain_matters"]
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
    ],
)
def test_spellcast_noops(name):
    # neither arm fires: an opponent/any-caster punisher and an
    # artifact/enchantment-only watched spell both route AWAY from I/S
    # Spellslinger density.
    tree = _fixture_tree(name)
    assert has_structural_spellcast(tree) is False
    assert synthesize_nodes(tree) == ()
    assert apply_tree_synthesis(tree) is tree


def test_spellcast_noop_shanid_sleepers_scourge():
    # FIX 2: "cast a legendary spell" is a supertype-restricted untyped
    # trigger that routes AWAY from I/S Spellslinger density — spellcast_matters
    # does NOT synthesize. Shanid's "Other legendary creatures you control
    # have menace" DOES independently synthesize evasion_self (ADR-0036 fold,
    # a genuine grant — unrelated to the spellcast claim this test makes).
    tree = _fixture_tree("Shanid, Sleepers' Scourge")
    assert has_structural_spellcast(tree) is False
    assert _arm_spellcast_matters(tree) is None
    assert [arm for arm, _ in synthesize_nodes(tree)] == ["evasion_self"]


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


# ── evasion_self fold (ADR-0036/0037) ───────────────────────────────────────────


def _evasion_kw(name: str) -> frozenset[str]:
    import json
    from pathlib import Path

    from mtg_utils._card_ir.mirror.build import fixtures_dir

    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    fix = json.loads(Path(path).read_text())
    return frozenset(fix.get("scryfall_keywords", {}).get(name, ()))


def _evasion_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _evasion_self

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "evasion_self" for s in _evasion_self(tree))


def _evasion_kwfield_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_field_signals_b15

    return any(
        s.key == "evasion_self"
        for s in _keyword_field_signals_b15(_evasion_kw(name), name)
    )


def _evasion_end_to_end_fires(name: str) -> bool:
    """The FULL crosswalk pipeline (lane + keyword-field arms combined) —
    what a bucket-A-only card (no synth node) actually surfaces through
    ``extract_crosswalk_signals``."""
    from mtg_utils._deck_forge.crosswalk_signals import extract_crosswalk_signals

    tree = _fixture_tree(name)
    sigs = extract_crosswalk_signals(
        tree, keys=frozenset({"evasion_self"}), keywords=_evasion_kw(name)
    )
    return any(s.key == "evasion_self" for s in sigs)


@pytest.mark.parametrize(
    "name",
    [
        "Barbarian General",  # own Scryfall keyword: Horsemanship
        "Ayumi, the Last Visitor",  # own keyword: Landwalk / Legendary landwalk
        # (ADR-0036 bucket-A extension — the generic landwalk-family umbrella,
        # a genuine ADD over the deleted mirror, which only matched the five
        # basic-land-type walk WORDS and never this variant).
    ],
)
def test_evasion_self_bucket_a_structural(name):
    """The card's OWN Scryfall keyword field fires the signal with NO synth
    node needed (:func:`_keyword_field_signals_b15` — bucket-A, unchanged/
    extended); the ``_evasion_self`` TEXT lane itself stays silent (no
    can't-be-blocked / granted-keyword idiom survives reminder-stripping)."""
    assert _evasion_kwfield_fires(name) is True
    assert _evasion_end_to_end_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Etrata, the Silencer",  # "Etrata can't be blocked." — CR 509.1b
        "Surrakar Marauder",  # granted intimidate-in-text (landfall trigger)
        "Legions of Lim-Dûl",  # bare "Snow swampwalk" ability-declaration line
    ],
)
def test_evasion_self_bucket_b_synth(name):
    """A genuine can't-be-blocked / granted-keyword / bare-landwalk-line tail
    phase carries no Tier-1 read for — the synth arm fills it."""
    from mtg_utils._card_ir.tree_synthesis import _arm_evasion_self

    tree = _fixture_tree(name)
    assert _evasion_kwfield_fires(name) is False  # no OWN keyword, genuine gap
    node = _arm_evasion_self(tree)
    assert node is not None
    assert node.concept == "synth_evasion_self"
    assert node.scope == "you"
    assert _evasion_lane_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Great Wall",  # evasion-DENIAL ("blocked as though ... didn't have
        # plainswalk") — CR 702.14 denial, a separate ``_evasion_denial`` lane
        "Trip Wire",  # horsemanship-hoser removal target, not a grant
        "J. Jonah Jameson",  # bare "creature you control with menace" REFERENCE
        # (the Suspect grant's own "has menace" lives only in reminder text)
    ],
)
def test_evasion_self_shed_overfires(name):
    from mtg_utils._card_ir.tree_synthesis import _arm_evasion_self

    tree = _fixture_tree(name)
    assert _evasion_kwfield_fires(name) is False
    assert _arm_evasion_self(tree) is None
    assert _evasion_lane_fires(name) is False


def test_evasion_self_flying_only_does_not_fire():
    """flying is DELIBERATELY not evasion_self (soft evasion, CR 702.9)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_evasion_self
    from mtg_utils._deck_forge.crosswalk_signals import _evasion_self

    tree = _gap_tree("Flying")
    assert _arm_evasion_self(tree) is None
    synth = apply_tree_synthesis(tree)
    assert not any(s.key == "evasion_self" for s in _evasion_self(synth))


def test_evasion_self_synth_registered():
    assert "evasion_self" in SYNTHESIS_ARM_IDS


def test_evasion_self_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_evasion_self`` node
    ALONE — oracle carrying no evasion idiom — makes the ``_evasion_self``
    lane emit the signal (proves the synth read is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _evasion_self

    synth = ConceptNode(
        concept="synth_evasion_self",
        node=SynthesizedNode(arm_id="evasion_self", description="x"),
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
    sigs = _evasion_self(tree)
    assert any(s.key == "evasion_self" for s in sigs)


# ── theft_makers fold (ADR-0036/0037 Stage 5) ───────────────────────────────────


def _theft_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _theft_makers_lane

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _theft_makers_lane(tree)
    return any(s.key == "theft_makers" and s.scope == "opponents" for s in sigs)


@pytest.mark.parametrize(
    "name",
    [
        "Chaos Wand",  # ExileFromTopUntil{player:Opponent} + cast_from_zone
        "Sen Triplets",  # Hand-zone CastFromZone beside an opponent TargetOnly
        "Grenzo, Crooked Jailer",  # Heist{target:Opponent}
        "Ancient Vendetta",  # SearchLibrary target_player Typed(Opponent)
        "Bribery",  # SearchLibrary opponent library (single zone, genuine ADD)
    ],
)
def test_theft_makers_bucket_a_structural(name):
    """Five Tier-1 structural arms recover the mirror's population with NO
    synth node needed — ``has_structural_theft_makers`` is the lane's OWN
    gate, so the two can never diverge (GAP-GATE-ALIGNMENT)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_theft_makers

    tree = _fixture_tree(name)
    assert has_structural_theft_makers(tree) is True
    assert _arm_theft_makers(tree) is None  # already structural — no-op
    assert _theft_lane_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Axavar, Fate Thief",  # "discard a card, then heist…" — phase drops
        # the heist clause of the compound sentence entirely
        "Lae'zel, Illithid Thrall",  # "conjure...from an opponent's library"
        # — Conjure carries no player/zone field at all
        "Lobotomy",  # "search that player's graveyard, hand, and library" —
        # phase leaves the whole clause Unimplemented
    ],
)
def test_theft_makers_bucket_b_synth(name):
    """A genuine phase-parse gap (no typed steal/heist node reachable) the
    synth arm fills — the whole point of the ADR-0037 enabler."""
    from mtg_utils._card_ir.tree_synthesis import _arm_theft_makers

    tree = _fixture_tree(name)
    assert has_structural_theft_makers(tree) is False  # genuine gap
    node = _arm_theft_makers(tree)
    assert node is not None
    assert node.concept == "synth_theft_makers"
    assert node.scope == "opponents"
    assert _theft_lane_fires(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Guff Rewrites History",  # self-cast symmetric: "Each player may
        # cast the nonland card THEY exiled" — no opponent benefit
        "Possibility Storm",  # self-cast symmetric replacement: "a player
        # casts a spell… that player may cast" — the ORIGINAL caster, not
        # a directed opponent
        "Light Up the Stage",  # the [P5] direction trap: a SELF-exile
        # impulse draw (Controller digger, no opponent wrapper) — CR 613.1b
        # requires an opponent zone, not your own library
    ],
)
def test_theft_makers_shed_overfires(name):
    """Cards the deleted mirror word-matched but are NOT genuine
    steal/mill/play-from-opponents members — dropping them is the fold's
    adjudicated IMPROVEMENT (ADR-0036), not a regression."""
    from mtg_utils._card_ir.tree_synthesis import _arm_theft_makers

    tree = _fixture_tree(name)
    assert has_structural_theft_makers(tree) is False
    assert _arm_theft_makers(tree) is None
    assert _theft_lane_fires(name) is False


def test_theft_makers_synth_registered():
    assert "theft_makers" in SYNTHESIS_ARM_IDS


def test_theft_makers_lane_reads_synth_node_end_to_end():
    """Fold path, mirror-independent: a synth ``synth_theft_makers`` node
    ALONE — oracle carrying no theft idiom — makes the ``_theft_makers_lane``
    emit the signal (proves the synth read is the ACTIVE Tier-1 source)."""
    from mtg_utils._deck_forge.crosswalk_signals import _theft_makers_lane

    synth = ConceptNode(
        concept="synth_theft_makers",
        node=SynthesizedNode(arm_id="theft_makers", description="x"),
        role="effect",
        scope="opponents",
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
    sigs = _theft_makers_lane(tree)
    assert any(s.key == "theft_makers" and s.scope == "opponents" for s in sigs)


# ── batch T1-abilitywords fold (ADR-0036/0037 Stage 5) ──────────────────────────
# coven_matters — the first of five small tail lanes in this batch.


def _coven_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _coven_matters_lane

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _coven_matters_lane(tree)
    return any(s.key == "coven_matters" for s in sigs)


def test_coven_matters_bucket_b_synth():
    """coven is an ABILITY WORD (CR 207.2c) — phase carries no typed node
    for it (a generic QuantityCheck/ObjectCountDistinct shared by unrelated
    distinct-count cards), so this arm is the lane's SOLE source."""
    from mtg_utils._card_ir.tree_synthesis import _arm_coven_matters

    tree = _fixture_tree("Leinore, Autumn Sovereign")
    node = _arm_coven_matters(tree)
    assert node is not None
    assert node.concept == "synth_coven_matters"
    assert _coven_lane_fires("Leinore, Autumn Sovereign") is True


def test_coven_matters_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_coven_matters

    tree = _fixture_tree("Chaos Wand")
    assert _arm_coven_matters(tree) is None
    assert _coven_lane_fires("Chaos Wand") is False


def test_coven_matters_synth_registered():
    assert "coven_matters" in SYNTHESIS_ARM_IDS


def test_coven_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _coven_matters_lane

    synth = ConceptNode(
        concept="synth_coven_matters",
        node=SynthesizedNode(arm_id="coven_matters", description="x"),
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
    sigs = _coven_matters_lane(tree)
    assert any(s.key == "coven_matters" for s in sigs)


def _celebration_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _celebration_matters

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _celebration_matters(tree)
    return any(s.key == "celebration_matters" for s in sigs)


def test_celebration_matters_bucket_b_synth():
    """celebration is an ABILITY WORD (CR 207.2c) — no structured rules
    object for phase to parse, so this arm is the lane's SOLE source."""
    from mtg_utils._card_ir.tree_synthesis import _arm_celebration_matters

    tree = _fixture_tree("Ash, Party Crasher")
    node = _arm_celebration_matters(tree)
    assert node is not None
    assert node.concept == "synth_celebration_matters"
    assert _celebration_lane_fires("Ash, Party Crasher") is True


def test_celebration_matters_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_celebration_matters

    tree = _fixture_tree("Chaos Wand")
    assert _arm_celebration_matters(tree) is None
    assert _celebration_lane_fires("Chaos Wand") is False


def test_celebration_matters_synth_registered():
    assert "celebration_matters" in SYNTHESIS_ARM_IDS


def test_celebration_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _celebration_matters

    synth = ConceptNode(
        concept="synth_celebration_matters",
        node=SynthesizedNode(arm_id="celebration_matters", description="x"),
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
    sigs = _celebration_matters(tree)
    assert any(s.key == "celebration_matters" for s in sigs)


def _outlaw_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _outlaw_matters_lane

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _outlaw_matters_lane(tree)
    return any(s.key == "outlaw_matters" for s in sigs)


@pytest.mark.parametrize(
    "name",
    [
        "At Knifepoint",  # CR 700.12 five-subtype AnyOf filter
        "Shoot the Sheriff",  # Non-negated literal "Outlaw" pseudo-subtype
    ],
)
def test_outlaw_matters_structural(name):
    """Direct/bucket-A: a typed filter naming the outlaw group — no synth
    node needed, ``has_structural_outlaw`` is the lane's OWN gate."""
    from mtg_utils._card_ir.tree_synthesis import _arm_outlaw_matters

    tree = _fixture_tree(name)
    assert has_structural_outlaw(tree) is True
    assert _arm_outlaw_matters(tree) is None  # already structural — no-op
    assert _outlaw_lane_fires(name) is True


def test_outlaw_matters_bucket_b_synth():
    """Hellspur Brute's "Affinity for outlaws" cost reducer — phase drops
    the whole static ability (zero units for the whole card), a genuine
    phase gap the synth arm fills."""
    from mtg_utils._card_ir.tree_synthesis import _arm_outlaw_matters

    tree = _fixture_tree("Hellspur Brute")
    assert has_structural_outlaw(tree) is False
    node = _arm_outlaw_matters(tree)
    assert node is not None
    assert node.concept == "synth_outlaw_matters"
    assert _outlaw_lane_fires("Hellspur Brute") is True


def test_outlaw_matters_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_outlaw_matters

    tree = _fixture_tree("Chaos Wand")
    assert has_structural_outlaw(tree) is False
    assert _arm_outlaw_matters(tree) is None
    assert _outlaw_lane_fires("Chaos Wand") is False


def test_outlaw_matters_synth_registered():
    assert "outlaw_matters" in SYNTHESIS_ARM_IDS


def test_outlaw_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _outlaw_matters_lane

    synth = ConceptNode(
        concept="synth_outlaw_matters",
        node=SynthesizedNode(arm_id="outlaw_matters", description="x"),
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
    sigs = _outlaw_matters_lane(tree)
    assert any(s.key == "outlaw_matters" for s in sigs)


def _arcane_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _arcane_matters

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _arcane_matters(tree)
    return any(s.key == "arcane_matters" for s in sigs)


def test_arcane_matters_structural():
    """Direct: a typed filter naming the Arcane spell subtype in a cast
    payoff (Tallowisp) — no synth node needed."""
    from mtg_utils._card_ir.tree_synthesis import _arm_arcane_matters

    tree = _fixture_tree("Tallowisp")
    assert has_structural_arcane(tree) is True
    assert _arm_arcane_matters(tree) is None  # already structural — no-op
    assert _arcane_lane_fires("Tallowisp") is True


def test_arcane_matters_bucket_b_synth():
    """Glacial Ray's "Splice onto Arcane" — phase drops the whole static
    ability (zero units for the whole card), a genuine phase gap."""
    from mtg_utils._card_ir.tree_synthesis import _arm_arcane_matters

    tree = _fixture_tree("Glacial Ray")
    assert has_structural_arcane(tree) is False
    node = _arm_arcane_matters(tree)
    assert node is not None
    assert node.concept == "synth_arcane_matters"
    assert _arcane_lane_fires("Glacial Ray") is True


def test_arcane_matters_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_arcane_matters

    tree = _fixture_tree("Chaos Wand")
    assert has_structural_arcane(tree) is False
    assert _arm_arcane_matters(tree) is None
    assert _arcane_lane_fires("Chaos Wand") is False


def test_arcane_matters_synth_registered():
    assert "arcane_matters" in SYNTHESIS_ARM_IDS


def test_arcane_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _arcane_matters

    synth = ConceptNode(
        concept="synth_arcane_matters",
        node=SynthesizedNode(arm_id="arcane_matters", description="x"),
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
    sigs = _arcane_matters(tree)
    assert any(s.key == "arcane_matters" for s in sigs)


def _exalted_textual_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _exalted_textual

    tree = apply_tree_synthesis(_fixture_tree(name))
    sigs = _exalted_textual(tree)
    return any(s.key == "exalted_lone_attacker" for s in sigs)


@pytest.mark.parametrize(
    "name",
    [
        "Agents of S.H.I.E.L.D.",  # textual payoff, no own exalted keyword
        "Emissary of Soulfire",  # "put an exalted counter" grant, no keyword
    ],
)
def test_exalted_textual_bucket_b_synth(name):
    """No competing Tier-1 predicate exists for this arm (the phase
    SourceAttackingAlone/AttackingAlone/BlockingAlone/CombatAlone tags
    structure an UNRELATED evasion mechanic — see the shed-overfire test
    below), so this is the lane's SOLE source."""
    from mtg_utils._card_ir.tree_synthesis import _arm_exalted_lone_attacker

    tree = _fixture_tree(name)
    node = _arm_exalted_lone_attacker(tree)
    assert node is not None
    assert node.concept == "synth_exalted_lone_attacker"
    assert _exalted_textual_lane_fires(name) is True


def test_exalted_textual_shed_overfire_cant_be_blocked_alone():
    """Dream Prowler ("can't be blocked as long as it's attacking alone")
    is a conditional EVASION clause (CR 702.14-adjacent, evasion_self's
    turf), NOT an exalted bonus — the phase ``SourceAttackingAlone`` tag it
    carries is deliberately NOT read here (probed: a genuine 4-card
    over-fire on the corpus)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_exalted_lone_attacker

    tree = _fixture_tree("Dream Prowler")
    assert _arm_exalted_lone_attacker(tree) is None
    assert _exalted_textual_lane_fires("Dream Prowler") is False


def test_exalted_textual_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_exalted_lone_attacker

    tree = _fixture_tree("Chaos Wand")
    assert _arm_exalted_lone_attacker(tree) is None
    assert _exalted_textual_lane_fires("Chaos Wand") is False


def test_exalted_lone_attacker_synth_registered():
    assert "exalted_lone_attacker" in SYNTHESIS_ARM_IDS


def test_exalted_textual_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _exalted_textual

    synth = ConceptNode(
        concept="synth_exalted_lone_attacker",
        node=SynthesizedNode(arm_id="exalted_lone_attacker", description="x"),
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
    sigs = _exalted_textual(tree)
    assert any(s.key == "exalted_lone_attacker" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): power_matters ──────────────────


def test_power_matters_bucket_b_aggregate_synth():
    """The Formidable ability word / aggregate power scaler (CR 208/207.2c) —
    phase folds the threshold into an empty-predicate board_count carrier, so
    no structural datum distinguishes it; this arm is the residual source."""
    from mtg_utils._card_ir.tree_synthesis import _arm_power_matters

    tree = _gap_tree(
        "Formidable — At the beginning of combat on your turn, if creatures "
        "you control have total power 8 or greater, target creature gains "
        "flying until end of turn."
    )
    node = _arm_power_matters(tree)
    assert node is not None
    assert node.concept == "synth_power_matters"
    assert node.scope == "you"


def test_power_matters_no_fire_on_unrelated_text():
    from mtg_utils._card_ir.tree_synthesis import _arm_power_matters

    assert _arm_power_matters(_gap_tree("Draw a card.")) is None


def test_power_matters_synth_registered():
    assert "power_matters" in SYNTHESIS_ARM_IDS


def test_power_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _predicate_build_around

    synth = ConceptNode(
        concept="synth_power_matters",
        node=SynthesizedNode(arm_id="power_matters", description="x"),
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
    sigs = _predicate_build_around(tree)
    assert any(s.key == "power_matters" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): keyword_counter ────────────────


def _keyword_counter_lane_fires(tree: ConceptTree) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_counter

    return any(
        s.key == "keyword_counter" for s in _keyword_counter(apply_tree_synthesis(tree))
    )


def test_keyword_counter_bucket_a_structural():
    """Arwen, Mortal Queen's indestructible enters-with — phase types the
    counter kind directly on a place_counter effect (CR 122.1b)."""
    tree = _fixture_tree("Arwen, Mortal Queen")
    assert has_structural_keyword_counter(tree) is True
    assert _keyword_counter_lane_fires(tree) is True


def test_keyword_counter_bucket_b_synth():
    """Boot Nipper's counter-kind CHOICE nests outside the effect chain in a
    ChooseOneOf branch — a genuine phase-parse gap (measured: 25/107 corpus
    fires)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_keyword_counter

    tree = _gap_tree(
        "This creature enters with your choice of a deathtouch counter or a "
        "lifelink counter on it."
    )
    assert has_structural_keyword_counter(tree) is False
    node = _arm_keyword_counter(tree)
    assert node is not None
    assert node.concept == "synth_keyword_counter"
    assert node.scope == "any"
    assert _keyword_counter_lane_fires(tree) is True


def test_keyword_counter_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_keyword_counter

    tree = _fixture_tree("Mycoloth")
    assert has_structural_keyword_counter(tree) is False
    assert _arm_keyword_counter(tree) is None
    assert _keyword_counter_lane_fires(tree) is False


def test_keyword_counter_synth_registered():
    assert "keyword_counter" in SYNTHESIS_ARM_IDS


def test_keyword_counter_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_counter

    synth = ConceptNode(
        concept="synth_keyword_counter",
        node=SynthesizedNode(arm_id="keyword_counter", description="x"),
        role="effect",
        scope="any",
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
    sigs = _keyword_counter(tree)
    assert any(s.key == "keyword_counter" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): counter_distribute ─────────────


def _counter_distribute_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _counter_distribute

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "counter_distribute" for s in _counter_distribute(tree))


def test_counter_distribute_bucket_a_structural():
    """Cathars' Crusade's mass ``PutCounterAll`` of kind P1P1 (CR 115.7f)."""
    tree = _fixture_tree("Cathars' Crusade")
    assert has_structural_counter_distribute(tree) is True
    assert _counter_distribute_lane_fires("Cathars' Crusade") is True


def test_counter_distribute_bucket_b_synth():
    """Bramblewood Paragon's "enters with an additional +1/+1 counter" group
    buff phase types identically to an unrelated single-target pump — a
    genuine gap (ADR-0027 #24, re-confirmed this batch: 163/383 residue)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_counter_distribute

    tree = _fixture_tree("Bramblewood Paragon")
    assert has_structural_counter_distribute(tree) is False
    node = _arm_counter_distribute(tree)
    assert node is not None
    assert node.concept == "synth_counter_distribute"
    assert node.scope == "you"
    assert _counter_distribute_lane_fires("Bramblewood Paragon") is True


def test_counter_distribute_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_counter_distribute

    tree = _fixture_tree("Scavenging Ooze")
    assert has_structural_counter_distribute(tree) is False
    assert _arm_counter_distribute(tree) is None
    assert _counter_distribute_lane_fires("Scavenging Ooze") is False


def test_counter_distribute_synth_registered():
    assert "counter_distribute" in SYNTHESIS_ARM_IDS


def test_counter_distribute_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _counter_distribute

    synth = ConceptNode(
        concept="synth_counter_distribute",
        node=SynthesizedNode(arm_id="counter_distribute", description="x"),
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
    sigs = _counter_distribute(tree)
    assert any(s.key == "counter_distribute" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): proliferate_matters ────────────


def _proliferate_matters_lane_fires_high(tree: ConceptTree) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _proliferate_matters_lane

    return any(
        s.key == "proliferate_matters" and s.confidence == "high"
        for s in _proliferate_matters_lane(apply_tree_synthesis(tree))
    )


def test_proliferate_matters_bucket_a_structural_permanent_counter():
    """Myojin of Cleansing Fire's divinity enters-with counter — phase types
    the kind directly on a place_counter effect."""
    tree = _fixture_tree("Myojin of Cleansing Fire")
    assert has_structural_proliferate(tree) is True
    assert _proliferate_matters_lane_fires_high(tree) is True


def test_proliferate_matters_bucket_a_structural_player_counter():
    """Ezuri, Claw of Progress's "you get an experience counter" — a
    ``give_player_counter`` effect whose OWN ``counter_kind`` field (a
    DIFFERENT phase field name than the permanent-side ``counter_type``)
    reads Experience (NEW this batch — recovers 17 corpus cards the old
    enters-with-anchored mirror missed, e.g. Captain Marvel's activated
    indestructible counter)."""
    tree = _fixture_tree("Ezuri, Claw of Progress")
    assert has_structural_proliferate(tree) is True
    assert _proliferate_matters_lane_fires_high(tree) is True


def test_proliferate_matters_bucket_b_synth():
    """Ion Storm's activation-cost reference ("remove a +1/+1 counter or a
    charge counter") is a pure text reference phase does not type as a node
    this batch — a genuine gap (measured: 9/167 corpus residue)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_proliferate_matters

    tree = _gap_tree(
        "{1}{R}, Remove a +1/+1 counter or a charge counter from a permanent "
        "you control: This enchantment deals 2 damage to any target."
    )
    assert has_structural_proliferate(tree) is False
    node = _arm_proliferate_matters(tree)
    assert node is not None
    assert node.concept == "synth_proliferate_matters"
    assert node.scope == "you"
    assert _proliferate_matters_lane_fires_high(tree) is True


def test_proliferate_matters_no_fire_on_unrelated_card():
    from mtg_utils._card_ir.tree_synthesis import _arm_proliferate_matters

    tree = _fixture_tree("Bramblewood Paragon")
    assert has_structural_proliferate(tree) is False
    assert _arm_proliferate_matters(tree) is None
    assert _proliferate_matters_lane_fires_high(tree) is False


def test_proliferate_matters_synth_registered():
    assert "proliferate_matters" in SYNTHESIS_ARM_IDS


def test_proliferate_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _proliferate_matters_lane

    synth = ConceptNode(
        concept="synth_proliferate_matters",
        node=SynthesizedNode(arm_id="proliferate_matters", description="x"),
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
    sigs = _proliferate_matters_lane(tree)
    assert any(s.key == "proliferate_matters" and s.confidence == "high" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): self_counter_grow ──────────────


def _self_counter_grow_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _self_counter_grow

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "self_counter_grow" for s in _self_counter_grow(tree))


def test_self_counter_grow_bucket_a_structural():
    """Scavenging Ooze's self-anchored ``PutCounter{P1P1, SelfRef}`` (CR
    122.1)."""
    tree = _fixture_tree("Scavenging Ooze")
    assert has_structural_self_counter_grow(tree) is True
    assert _self_counter_grow_lane_fires("Scavenging Ooze") is True


def test_self_counter_grow_bucket_a_structural_monstrosity():
    """Arbor Colossus's Monstrosity keyword action (CR 701.37)."""
    tree = _fixture_tree("Arbor Colossus")
    assert has_structural_self_counter_grow(tree) is True
    assert _self_counter_grow_lane_fires("Arbor Colossus") is True


def test_self_counter_grow_bucket_b_synth():
    """Sunbond's granted "put that many +1/+1 counters on this creature"
    ability lives only in a granted-ability STRING (Enchant creature's
    GrantAbility payload) — phase carries no typed PutCounter node for it, a
    genuine gap (measured: 21/1555 mirror-clause residue, 103 over-fires
    excluded via the narrowed idiom)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_self_counter_grow

    tree = _fixture_tree("Sunbond")
    assert has_structural_self_counter_grow(tree) is False
    node = _arm_self_counter_grow(tree)
    assert node is not None
    assert node.concept == "synth_self_counter_grow"
    assert node.scope == "you"
    assert _self_counter_grow_lane_fires("Sunbond") is True


def test_self_counter_grow_no_fire_on_unrelated_card():
    """Bramblewood Paragon's board-wide "on it" grant is counter_distribute's
    turf, NOT self_counter_grow's (the loose "on it" arm stays excluded)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_self_counter_grow

    tree = _fixture_tree("Bramblewood Paragon")
    assert has_structural_self_counter_grow(tree) is False
    assert _arm_self_counter_grow(tree) is None
    assert _self_counter_grow_lane_fires("Bramblewood Paragon") is False


def test_self_counter_grow_synth_registered():
    assert "self_counter_grow" in SYNTHESIS_ARM_IDS


def test_self_counter_grow_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _self_counter_grow

    synth = ConceptNode(
        concept="synth_self_counter_grow",
        node=SynthesizedNode(arm_id="self_counter_grow", description="x"),
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
    sigs = _self_counter_grow(tree)
    assert any(s.key == "self_counter_grow" for s in sigs)


# ── batch T2-counters (ADR-0036/0037 Stage 5): poison_matters ─────────────────


def _poison_matters_lane_fires(name: str) -> bool:
    from mtg_utils._deck_forge.crosswalk_signals import _poison_matters

    tree = apply_tree_synthesis(_fixture_tree(name))
    return any(s.key == "poison_matters" for s in _poison_matters(tree))


def test_poison_matters_bucket_b_synth():
    """Caress of Phyrexia's poison-GIVER that spells out "poison counter"
    instead of bearing Infect — no competing Tier-1 predicate (the
    celebration/coven no-competing-predicate precedent), so this is the
    lane's SOLE source."""
    from mtg_utils._card_ir.tree_synthesis import _arm_poison_matters

    tree = _fixture_tree("Caress of Phyrexia")
    node = _arm_poison_matters(tree)
    assert node is not None
    assert node.concept == "synth_poison_matters"
    assert node.scope == "opponents"
    assert _poison_matters_lane_fires("Caress of Phyrexia") is True


def test_poison_matters_giver_fires():
    """Fynn, the Fangbearer's poison-giver payoff."""
    assert _poison_matters_lane_fires("Fynn, the Fangbearer") is True


def test_poison_matters_no_fire_on_reminder_only_infect():
    """Glistener Elf's Infect keyword bearer — a reminder-only "poison
    counter" mention that stays stripped; Infect bearers ride poison_makers,
    not poison_matters (the ADR-0034 partition)."""
    from mtg_utils._card_ir.tree_synthesis import _arm_poison_matters

    tree = _fixture_tree("Glistener Elf")
    assert _arm_poison_matters(tree) is None
    assert _poison_matters_lane_fires("Glistener Elf") is False


def test_poison_matters_synth_registered():
    assert "poison_matters" in SYNTHESIS_ARM_IDS


def test_poison_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _poison_matters

    synth = ConceptNode(
        concept="synth_poison_matters",
        node=SynthesizedNode(arm_id="poison_matters", description="x"),
        role="effect",
        scope="opponents",
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
    sigs = _poison_matters(tree)
    assert any(s.key == "poison_matters" for s in sigs)


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): island_matters ─────────────


def test_island_matters_bucket_b_synth():
    """Dandân's Island-control attack restriction — no competing Tier-1
    predicate, so this is the lane's SOLE source."""
    tree = _fixture_tree("Dandân")
    node = _arm_island_matters(tree)
    assert node is not None
    assert node.concept == "synth_island_matters"
    assert node.scope == "you"


def test_island_matters_no_fire_on_islandwalk_bearer():
    """Segovian Leviathan's islandwalk bearer is island_MAKERS material,
    never island_matters."""
    assert _arm_island_matters(_fixture_tree("Segovian Leviathan")) is None


def test_island_matters_synth_registered():
    assert "island_matters" in SYNTHESIS_ARM_IDS


def test_island_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _island_matters

    synth = ConceptNode(
        concept="synth_island_matters",
        node=SynthesizedNode(arm_id="island_matters", description="x"),
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
    sigs = _island_matters(tree)
    assert any(s.key == "island_matters" for s in sigs)


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): animate_artifact ───────────


def test_animate_artifact_bucket_b_synth():
    """Karn, Silver Golem's artifact-becomes-creature grant — no competing
    Tier-1 predicate (the batch-12 adjudication)."""
    tree = _fixture_tree("Karn, Silver Golem")
    node = _arm_animate_artifact(tree)
    assert node is not None
    assert node.concept == "synth_animate_artifact"
    assert node.scope == "you"


def test_animate_artifact_no_fire_on_bare_type_conferral():
    """Liquimetal Coating's becomes-an-artifact conferral is a non-match."""
    assert _arm_animate_artifact(_fixture_tree("Liquimetal Coating")) is None


def test_animate_artifact_synth_registered():
    assert "animate_artifact" in SYNTHESIS_ARM_IDS


def test_animate_artifact_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _animate_artifact

    synth = ConceptNode(
        concept="synth_animate_artifact",
        node=SynthesizedNode(arm_id="animate_artifact", description="x"),
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
    sigs = _animate_artifact(tree)
    assert any(s.key == "animate_artifact" for s in sigs)


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): color_change ───────────────


def test_color_change_bucket_b_synth():
    """Alchor's Tomb's color-changing effect — no competing Tier-1
    predicate (the raw ``animate`` anchor over-fires ~94%, batch-12)."""
    tree = _fixture_tree("Alchor's Tomb")
    node = _arm_color_change(tree)
    assert node is not None
    assert node.concept == "synth_color_change"
    assert node.scope == "you"


def test_color_change_no_fire_on_becomes_colorless():
    """Ancient Kavu's "becomes colorless" is a deliberate non-match."""
    assert _arm_color_change(_fixture_tree("Ancient Kavu")) is None


def test_color_change_synth_registered():
    assert "color_change" in SYNTHESIS_ARM_IDS


def test_color_change_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _color_change

    synth = ConceptNode(
        concept="synth_color_change",
        node=SynthesizedNode(arm_id="color_change", description="x"),
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
    sigs = _color_change(tree)
    assert any(s.key == "color_change" for s in sigs)


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): vehicles_matter ────────────


def test_vehicles_matter_structural_gate_true_on_existing_arms():
    """has_structural_vehicles_matter mirrors the lane's own arms a-c —
    Gearshift Ace's Crews trigger, Aeronaut Admiral's Vehicle-subtype
    static."""
    assert has_structural_vehicles_matter(_fixture_tree("Gearshift Ace"))
    assert has_structural_vehicles_matter(_fixture_tree("Aeronaut Admiral"))


def test_vehicles_matter_bucket_b_synth_gap_gated():
    """Anchor to Reality's "Equipment or Vehicle card" tutor — the residual
    crew/Vehicle idiom arms a-c miss, gated against
    has_structural_vehicles_matter (which is False here)."""
    tree = _fixture_tree("Anchor to Reality")
    assert has_structural_vehicles_matter(tree) is False
    node = _arm_vehicles_matter(tree)
    assert node is not None
    assert node.concept == "synth_vehicles_matter"


def test_vehicles_matter_no_fire_when_structural_gate_true():
    """The synth never double-covers a card arms a-c already see."""
    assert _arm_vehicles_matter(_fixture_tree("Gearshift Ace")) is None


def test_vehicles_matter_no_fire_on_plain_vehicle():
    """A card that IS a Vehicle (Smuggler's Copter) never fires from its
    own nodes — neither the structural gate nor the synth."""
    tree = _fixture_tree("Smuggler's Copter")
    assert has_structural_vehicles_matter(tree) is False
    assert _arm_vehicles_matter(tree) is None


def test_vehicles_matter_synth_registered():
    assert "vehicles_matter" in SYNTHESIS_ARM_IDS


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): manland ────────────────────


def test_manland_structural_selfref_self_animate():
    """Crawling Barrens' self-animate GenericEffect (a SelfRef-affected
    AddType Creature on a card that IS itself a Land) — a genuine RECOVER
    the deleted mirror missed (no "land" word precedes "becomes a 0/0
    Elemental creature")."""
    assert has_structural_manland(_fixture_tree("Crawling Barrens"))
    assert _arm_manland(_fixture_tree("Crawling Barrens")) is None


def test_manland_structural_landish_affected_genju():
    """Genju of the Falls' Aura animates the ENCHANTED Island — a landish-
    AFFECTED (EnchantedBy Island-subtype filter) nested static a plain
    top-level walk misses."""
    assert has_structural_manland(_fixture_tree("Genju of the Falls"))


def test_manland_bucket_b_synth_gap_gated():
    """Emergent Sequence's search-then-animate tracked chain — phase drops
    the ParentTarget thread through the ChangeZone's "Any" forward-result
    target, a genuine gap the structural arm can't reach."""
    tree = _fixture_tree("Emergent Sequence")
    assert has_structural_manland(tree) is False
    node = _arm_manland(tree)
    assert node is not None
    assert node.concept == "synth_manland"


def test_manland_land_type_change_veto():
    """The adjudicated over-fire class: "target land becomes a Forest/
    Plains/Island" is a land TYPE-CHANGE idiom, not an animate — the
    accompanying "creature" word is always an unrelated self-reference
    ("until THIS CREATURE leaves the battlefield")."""
    for name in ("Gaea's Liege", "Graceful Antelope", "Tide Shaper"):
        tree = _fixture_tree(name)
        assert has_structural_manland(tree) is False
        assert _arm_manland(tree) is None, name


def test_manland_synth_registered():
    assert "manland" in SYNTHESIS_ARM_IDS


# ── batch T4-mechanic-kw (ADR-0036/0037 Stage 5): curse_matters ──────────────


def test_curse_matters_structural_gate_true_on_existing_arm():
    """Witchbane Orb's Curse-subtype DestroyAll effect target — one of the
    lane's two genuinely structural arms."""
    assert has_structural_curse_matters(_fixture_tree("Witchbane Orb"))
    assert _arm_curse_matters(_fixture_tree("Witchbane Orb")) is None


def test_curse_matters_bucket_b_synth_gap_gated():
    """Curse of Misfortunes' search-filter drop — the residual bare-
    reference idiom the two structural arms miss."""
    tree = _fixture_tree("Curse of Misfortunes")
    assert has_structural_curse_matters(tree) is False
    node = _arm_curse_matters(tree)
    assert node is not None
    assert node.concept == "synth_curse_matters"


def test_curse_matters_no_fire_on_membership_only():
    """Cruel Reality IS an Aura — Curse; BEING one never fires (the live
    :2509-2510 deferral) — neither the structural gate nor the synth."""
    tree = _fixture_tree("Cruel Reality")
    assert has_structural_curse_matters(tree) is False
    assert _arm_curse_matters(tree) is None


def test_curse_matters_synth_registered():
    assert "curse_matters" in SYNTHESIS_ARM_IDS


def test_curse_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _curse_matters

    synth = ConceptNode(
        concept="synth_curse_matters",
        node=SynthesizedNode(arm_id="curse_matters", description="x"),
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
    sigs = _curse_matters(tree)
    assert any(s.key == "curse_matters" for s in sigs)


# ── batch T4-mechanic-kw: clue_matters ───────────────────────────────────────


def test_clue_matters_structural_gate_true_on_existing_arm():
    """Tireless Tracker's "Whenever you sacrifice a Clue" — a Sacrificed-
    mode trigger naming Clue, one of the shared food/clue helper's two
    genuinely structural arms (reimplemented by
    :func:`has_structural_clue_matters`); the synth never double-covers
    it."""
    tree = _fixture_tree("Tireless Tracker")
    assert has_structural_clue_matters(tree) is True
    assert _arm_clue_matters(tree) is None


def test_clue_matters_bucket_b_synth_gap_gated():
    """Bygone Bishop's bare "investigate" residue (a cast-trigger, not a
    sacrifice/Sacrificed-mode node) — the residual the two structural arms
    of the shared helper miss."""
    tree = _fixture_tree("Bygone Bishop")
    assert has_structural_clue_matters(tree) is False
    node = _arm_clue_matters(tree)
    assert node is not None
    assert node.concept == "synth_clue_matters"


def test_clue_matters_synth_registered():
    assert "clue_matters" in SYNTHESIS_ARM_IDS


def test_clue_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _clue_matters_lane

    synth = ConceptNode(
        concept="synth_clue_matters",
        node=SynthesizedNode(arm_id="clue_matters", description="x"),
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
    sigs = _clue_matters_lane(tree)
    assert any(s.key == "clue_matters" for s in sigs)


# ── batch T4-mechanic-kw: suspend_matters ────────────────────────────────────


def test_suspend_matters_structural_gate_true_on_time_counter_node():
    """Ancestral Vision's Suspend 4 — a ``PutCounter{counter_type=Time}``
    typed node, the lane's structural arm."""
    assert has_structural_suspend_matters(_fixture_tree("Ancestral Vision"))
    assert _arm_suspend_matters(_fixture_tree("Ancestral Vision")) is None


def test_suspend_matters_bucket_b_synth_gap_gated():
    """Overlord of the Mistmoors' Impending 4 — the keyword bearer survives
    reminder-stripping as bare "Impending", but phase carries no
    ``PutCounter{counter_type=Time}`` node for it (a genuine gap the
    structural arm misses)."""
    tree = _fixture_tree("Overlord of the Mistmoors")
    assert has_structural_suspend_matters(tree) is False
    node = _arm_suspend_matters(tree)
    assert node is not None
    assert node.concept == "synth_suspend_matters"


def test_suspend_matters_no_fire_on_suspended_card_boundary():
    """Clockspinning's "suspended card" does NOT match ``\\bsuspend\\b`` —
    the sharpest boundary (neither the structural gate nor the synth)."""
    tree = _fixture_tree("Clockspinning")
    assert has_structural_suspend_matters(tree) is False
    assert _arm_suspend_matters(tree) is None


def test_suspend_matters_synth_registered():
    assert "suspend_matters" in SYNTHESIS_ARM_IDS


def test_suspend_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _suspend_matters

    synth = ConceptNode(
        concept="synth_suspend_matters",
        node=SynthesizedNode(arm_id="suspend_matters", description="x"),
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
    sigs = _suspend_matters(tree)
    assert any(s.key == "suspend_matters" for s in sigs)


# ── batch T4-mechanic-kw: flash_matters (full relocation, no gate) ──────────


def test_flash_matters_bucket_b_synth_sole_source():
    """Faerie Tauntings' "whenever you cast a spell during an opponent's
    turn" — no competing Tier-1 predicate (structural is a probed trap),
    so this is the lane's SOLE source."""
    tree = _fixture_tree("Faerie Tauntings")
    node = _arm_flash_matters(tree)
    assert node is not None
    assert node.concept == "synth_flash_matters"
    assert node.scope == "you"


def test_flash_matters_no_fire_on_unrelated_card():
    assert _arm_flash_matters(_fixture_tree("Llanowar Elves")) is None


def test_flash_matters_synth_registered():
    assert "flash_matters" in SYNTHESIS_ARM_IDS


def test_flash_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _flash_matters_lane

    synth = ConceptNode(
        concept="synth_flash_matters",
        node=SynthesizedNode(arm_id="flash_matters", description="x"),
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
    sigs = _flash_matters_lane(tree)
    assert any(s.key == "flash_matters" for s in sigs)


# ── batch T4-mechanic-kw: crimes_matter ──────────────────────────────────────


def test_crimes_matter_structural_gate_true_on_commit_crime_trigger():
    """At Knifepoint's raw ``CommitCrime`` trigger mode — the lane's
    structural arm."""
    assert has_structural_crimes_matter(_fixture_tree("At Knifepoint"))
    assert _arm_crimes_matter(_fixture_tree("At Knifepoint")) is None


def test_crimes_matter_bucket_b_synth_gap_gated():
    """Nimble Brigand's keyword-less crime CONDITION form ("if you've
    committed a crime this turn") — phase has no condition kind for it, a
    genuine gap the structural CommitCrime-trigger arm misses."""
    tree = _fixture_tree("Nimble Brigand")
    assert has_structural_crimes_matter(tree) is False
    node = _arm_crimes_matter(tree)
    assert node is not None
    assert node.concept == "synth_crimes_matter"


def test_crimes_matter_no_fire_on_unrelated_card():
    assert _arm_crimes_matter(_fixture_tree("Llanowar Elves")) is None


def test_crimes_matter_synth_registered():
    assert "crimes_matter" in SYNTHESIS_ARM_IDS


def test_crimes_matter_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _crimes_matter

    synth = ConceptNode(
        concept="synth_crimes_matter",
        node=SynthesizedNode(arm_id="crimes_matter", description="x"),
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
    sigs = _crimes_matter(tree)
    assert any(s.key == "crimes_matter" for s in sigs)


# ── batch T4-mechanic-kw: suspect_matters (full relocation, no gate) ───────


def test_suspect_matters_bucket_b_synth_native_effect_state_form():
    """Agency Coroner's native Suspect effect raw carries the "suspected"
    STATE form (not the verb) — no competing Tier-1 predicate."""
    tree = _fixture_tree("Agency Coroner")
    node = _arm_suspect_matters(tree)
    assert node is not None
    assert node.concept == "synth_suspect_matters"


def test_suspect_matters_bucket_b_synth_marker_fallback():
    """Airtight Alibi's Unsuspect/``CantBecomeSuspected`` face projects no
    visible suspect concept — the ``_SUSPECT_REF`` marker fallback route."""
    tree = _fixture_tree("Airtight Alibi")
    node = _arm_suspect_matters(tree)
    assert node is not None
    assert node.concept == "synth_suspect_matters"


def test_suspect_matters_no_fire_when_verb_wins():
    """J. Jonah Jameson's "suspect up to one target creature" is the VERB
    form only (no bare "suspected" state elsewhere) — suspect_makers
    material, never suspect_matters (the polarity-from-pop pin)."""
    assert _arm_suspect_matters(_fixture_tree("J. Jonah Jameson")) is None


def test_suspect_matters_synth_registered():
    assert "suspect_matters" in SYNTHESIS_ARM_IDS


def test_suspect_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _suspect_matters_lane

    synth = ConceptNode(
        concept="synth_suspect_matters",
        node=SynthesizedNode(arm_id="suspect_matters", description="x"),
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
    sigs = _suspect_matters_lane(tree)
    assert any(s.key == "suspect_matters" for s in sigs)


# ── batch T5-niche-a: pump_makers (bucket-A widen + bucket-B tail) ─────────


def _pump_static_tree(affected):
    """A GenericEffect wrapping a nested Continuous static AddPower/
    AddToughness grant — the phase shape a temporary team/targeted buff
    ("Creatures you control get +2/+2 until end of turn") renders as,
    distinct from a top-level Pump/PumpAll effect tag."""
    static = S_static_abilities(
        active_zones=[],
        affected=affected,
        affected_zone=None,
        characteristic_defining=False,
        condition=None,
        description="get +2/+2",
        effect_zone=None,
        mode="Continuous",
        modifications=[
            T_modifications__AddPower(value=2),
            T_modifications__AddToughness(value=2),
        ],
    )
    effect = T_effect__GenericEffect(
        duration="UntilEndOfTurn", static_abilities=[static], target=None
    )
    unit = AbilityUnit(
        origin="ability",
        index=0,
        node=effect,
        kind="Spell",
        trigger_event=None,
        effects=(
            ConceptNode(
                concept="other",
                node=effect,
                role="effect",
                scope="each",
                subject=(),
                raw="",
            ),
        ),
        costs=(),
        statics=(),
    )
    return ConceptTree(name="X", oracle_id="x", oracle="X", units=(unit,))


def test_pump_makers_structural_arm_giant_growth():
    """Giant Growth's direct ``Pump`` effect (Fixed +3/+3) — the live
    effects-role structural arm."""
    assert has_structural_pump_makers(_fixture_tree("Giant Growth")) is True


def test_pump_makers_bucket_a_nested_static_team_buff():
    """A "Creatures you control get +2/+2 until end of turn"-shaped card:
    phase renders the temporary team buff as a ``GenericEffect`` wrapping a
    nested ``Continuous`` static (Adamant Will / Cavalier of Flame's real
    shape) rather than a top-level ``Pump``/``PumpAll`` tag — the SAME
    mechanic, a different phase shape (ADR-0036/0037 bucket-A widen)."""
    tree = _pump_static_tree(
        T_affected__Typed(controller="You", properties=[], type_filters=[])
    )
    assert has_structural_pump_makers(tree) is True


def test_pump_makers_self_buff_veto_not_structural():
    """A SelfRef-affected nested static (Clickslither / Crazed Armodon's
    firebreathing self-buff shape) is self_pump's country, NOT
    pump_makers."""
    tree = _pump_static_tree(T_affected__SelfRef())
    assert has_structural_pump_makers(tree) is False


def test_pump_makers_no_fire_on_unrelated_card():
    assert has_structural_pump_makers(_fixture_tree("Llanowar Elves")) is False
    assert _arm_pump_makers(_fixture_tree("Llanowar Elves")) is None


def test_pump_makers_bucket_b_synth_dynamic_amount_residue():
    """Kessig Wolf Run-shaped "Target creature gets +X/+0 … until end of
    turn" — a dynamic/X amount with no raw text to ground a positive/
    negative tell; the deleted ``PUMP_MATTERS_REGEX`` kept-mirror relocated,
    gap-gated against :func:`has_structural_pump_makers`."""
    tree = ConceptTree(
        name="X",
        oracle_id="x",
        oracle="{X}{R}{G}: Target creature gets +X/+0 and gains trample "
        "until end of turn.",
        units=(),
    )
    assert has_structural_pump_makers(tree) is False
    node = _arm_pump_makers(tree)
    assert node is not None
    assert node.concept == "synth_pump_makers"


def test_pump_makers_synth_registered():
    assert "pump_makers" in SYNTHESIS_ARM_IDS


def test_pump_makers_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _pump_makers_lane

    synth = ConceptNode(
        concept="synth_pump_makers",
        node=SynthesizedNode(arm_id="pump_makers", description="x"),
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
    sigs = _pump_makers_lane(tree)
    assert any(s.key == "pump_makers" for s in sigs)


# ── batch T5-niche-a: opponent_exile_matters (full relocation, no gate) ────


def test_opponent_exile_matters_bucket_b_synth_sole_source():
    """Umbris, Fear Manifest's "gets +1/+1 for each card your opponents own
    in exile" — phase never structures the scaling reference at all (a
    genuine gap), so no competing Tier-1 predicate exists."""
    tree = _fixture_tree("Umbris, Fear Manifest")
    node = _arm_opponent_exile_matters(tree)
    assert node is not None
    assert node.concept == "synth_opponent_exile_matters"
    assert node.scope == "opponents"


def test_opponent_exile_matters_no_fire_on_unrelated_card():
    assert _arm_opponent_exile_matters(_fixture_tree("Llanowar Elves")) is None


def test_opponent_exile_matters_synth_registered():
    assert "opponent_exile_matters" in SYNTHESIS_ARM_IDS


def test_opponent_exile_matters_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _opponent_exile_matters_lane

    synth = ConceptNode(
        concept="synth_opponent_exile_matters",
        node=SynthesizedNode(arm_id="opponent_exile_matters", description="x"),
        role="effect",
        scope="opponents",
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
    sigs = _opponent_exile_matters_lane(tree)
    assert any(s.key == "opponent_exile_matters" for s in sigs)


# ── batch T5-niche-a: color_hoser (bucket-A widen + bucket-B tail) ──────────


def _single_effect_tree(effect_node):
    unit = AbilityUnit(
        origin="ability",
        index=0,
        node=effect_node,
        kind="Spell",
        trigger_event=None,
        effects=(
            ConceptNode(
                concept="other",
                node=effect_node,
                role="effect",
                scope="you",
                subject=(),
                raw="",
            ),
        ),
        costs=(),
        statics=(),
    )
    return ConceptTree(name="X", oracle_id="x", oracle="X", units=(unit,))


def test_color_hoser_bucket_a_mass_destroy_direct_carrier():
    """Anarchy-shaped "Destroy all white permanents." — the mass DestroyAll
    form carries the SAME direct top-level Typed/HasColor target the live
    single-target arm reads."""
    effect = T_effect__DestroyAll(
        cant_regenerate=False,
        target=T_target__Typed(
            controller=None,
            properties=[T_properties__HasColor(color="White")],
            type_filters=["Permanent"],
        ),
    )
    assert has_structural_color_hoser(_single_effect_tree(effect)) is True


def test_color_hoser_bucket_a_counter_and_composite():
    """Gainsay-shaped "Counter target blue spell." — phase types the Counter
    target as an And-composite (StackSpell + Typed/HasColor), not a bare
    Typed filter; the direct-carrier read descends one level into it."""
    effect = T_effect__Counter(
        target=T_target__And(
            filters=[
                T_filters__StackSpell(),
                T_filters__Typed(
                    controller=None,
                    properties=[T_properties__HasColor(color="Blue")],
                    type_filters=[],
                ),
            ]
        ),
    )
    assert has_structural_color_hoser(_single_effect_tree(effect)) is True


def test_color_hoser_bounceall_self_owned_not_structural():
    """Word of Undoing's "all white Auras you own" — the ownership rides an
    Owned{controller: You} PROPERTY (not the plain controller field); a
    self-service bounce-combo, NOT color hosing (the over-fire this gate
    excludes)."""
    effect = T_effect__BounceAll(
        target=T_target__Typed(
            controller=None,
            properties=[
                T_properties__HasColor(color="White"),
                T_properties__Owned(controller="You"),
            ],
            type_filters=["Aura"],
        ),
    )
    assert has_structural_color_hoser(_single_effect_tree(effect)) is False


def test_color_hoser_bounceall_opponent_owned_is_structural():
    """Llawan-shaped "return all blue creatures your opponents control" — an
    opponent-owned BounceAll is genuine hosing."""
    effect = T_effect__BounceAll(
        target=T_target__Typed(
            controller="Opponent",
            properties=[T_properties__HasColor(color="Blue")],
            type_filters=["Creature"],
        ),
    )
    assert has_structural_color_hoser(_single_effect_tree(effect)) is True


def test_color_hoser_logged_gap_two_color_disjunction_stays_off():
    """Deathmark's "Destroy target green or white creature." — a two-color
    disjunction carries NO direct HasColor; the logged GAP this fold does
    NOT close (pinned negative, unchanged by the widen)."""
    tree = _fixture_tree("Deathmark")
    assert has_structural_color_hoser(tree) is False
    assert _arm_color_hoser(tree) is None


def test_color_hoser_synth_registered():
    assert "color_hoser" in SYNTHESIS_ARM_IDS


def test_color_hoser_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _color_hoser

    synth = ConceptNode(
        concept="synth_color_hoser",
        node=SynthesizedNode(arm_id="color_hoser", description="x"),
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
    sigs = _color_hoser(tree)
    assert any(s.key == "color_hoser" for s in sigs)


# ── batch T5-niche-a: void_warp_makers (full relocation, no gate) ──────────


def test_void_warp_makers_bucket_b_synth_keyword_bearer():
    """Starfield Vocalist's "Warp {1}{U}" keyword bearer — no competing
    Tier-1 predicate (the Scryfall keyword array under-fires the granters,
    so it can't reproduce the full population either)."""
    tree = _fixture_tree("Starfield Vocalist")
    node = _arm_void_warp_makers(tree)
    assert node is not None
    assert node.concept == "synth_void_warp_makers"
    assert node.scope == "you"


def test_void_warp_makers_bucket_b_synth_emdash_form():
    """Timeline Culler's em-dash "Warp—{B}" / graveyard self-cast form."""
    tree = _fixture_tree("Timeline Culler")
    node = _arm_void_warp_makers(tree)
    assert node is not None
    assert node.concept == "synth_void_warp_makers"


def test_void_warp_makers_no_fire_on_unrelated_card():
    assert _arm_void_warp_makers(_fixture_tree("Llanowar Elves")) is None


def test_void_warp_makers_synth_registered():
    assert "void_warp_makers" in SYNTHESIS_ARM_IDS


def test_void_warp_makers_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _void_warp_makers

    synth = ConceptNode(
        concept="synth_void_warp_makers",
        node=SynthesizedNode(arm_id="void_warp_makers", description="x"),
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
    sigs = _void_warp_makers(tree)
    assert any(s.key == "void_warp_makers" for s in sigs)


# ── batch T5-niche-a: sacrifice_protection (full relocation, no gate) ──────


def test_sacrifice_protection_bucket_b_synth_sole_source():
    """Sigarda, Host of Herons's "can't be sacrificed" — phase parses the
    ability as ``Unimplemented`` ([P42]), so no competing Tier-1 predicate
    exists; the two literal phrases stay the only full-coverage tell."""
    tree = _fixture_tree("Sigarda, Host of Herons")
    node = _arm_sacrifice_protection(tree)
    assert node is not None
    assert node.concept == "synth_sacrifice_protection"
    assert node.scope == "you"


def test_sacrifice_protection_no_fire_on_unrelated_card():
    assert _arm_sacrifice_protection(_fixture_tree("Llanowar Elves")) is None


def test_sacrifice_protection_synth_registered():
    assert "sacrifice_protection" in SYNTHESIS_ARM_IDS


def test_sacrifice_protection_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _sacrifice_protection

    synth = ConceptNode(
        concept="synth_sacrifice_protection",
        node=SynthesizedNode(arm_id="sacrifice_protection", description="x"),
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
    sigs = _sacrifice_protection(tree)
    assert any(s.key == "sacrifice_protection" for s in sigs)


# ── batch T5-niche-a: life_payment_insurance (bucket-B tail) ────────────────


def test_life_payment_insurance_structural_arco_flagellant():
    """Arco-Flagellant NOW parses ``Activated.cost/PayLife`` at v0.9.0 — a
    genuine structural cost-census fire."""
    tree = _fixture_tree("Arco-Flagellant")
    assert has_structural_life_payment_insurance(tree) is True
    assert _arm_life_payment_insurance(tree) is None


def test_life_payment_insurance_bucket_b_synth_granted_ability_residue():
    """Forgotten Monument-shaped "Other Caves you control have '{T}, Pay 1
    life: Add one mana of any color.'" — the granted-ability TEXT payload
    phase never structures onto THIS card (no typed PayLife leaf of its
    own), a genuine gap."""
    tree = ConceptTree(
        name="X",
        oracle_id="x",
        oracle=(
            'Other Caves you control have "{T}, Pay 1 life: Add one mana of any color."'
        ),
        units=(),
    )
    assert has_structural_life_payment_insurance(tree) is False
    node = _arm_life_payment_insurance(tree)
    assert node is not None
    assert node.concept == "synth_life_payment_insurance"


def test_life_payment_insurance_no_fire_on_unrelated_card():
    assert (
        has_structural_life_payment_insurance(_fixture_tree("Llanowar Elves")) is False
    )
    assert _arm_life_payment_insurance(_fixture_tree("Llanowar Elves")) is None


def test_life_payment_insurance_synth_registered():
    assert "life_payment_insurance" in SYNTHESIS_ARM_IDS


def test_life_payment_insurance_lane_reads_synth_node_end_to_end():
    from mtg_utils._deck_forge.crosswalk_signals import _life_payment_insurance

    synth = ConceptNode(
        concept="synth_life_payment_insurance",
        node=SynthesizedNode(arm_id="life_payment_insurance", description="x"),
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
    sigs = _life_payment_insurance(tree)
    assert any(s.key == "life_payment_insurance" for s in sigs)
