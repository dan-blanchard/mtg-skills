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
    _matches_spellcast_idiom,
    apply_tree_synthesis,
    has_gain_life_amplifier,
    has_life_gained_this_turn,
    has_life_gained_trigger,
    has_selfloss_engine,
    has_structural_spellcast,
    has_trigger_draw_bleed,
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
