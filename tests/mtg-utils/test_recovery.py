"""ADR-0038 Unimplemented recovery stage — CI-safe, real-card fixtures.

Covers the behavior-neutral introduction (empty production ``ALLOWLIST``):
the empty-allowlist fast path returns the tree by identity; an allowlisted
token re-decorates its ``other``/``Unimplemented`` node in place while every
other node is untouched; a token absent from the allowlist leaves the node
unrecovered; a ``concept == "other"`` node whose tag is NOT ``Unimplemented``
is never touched; and a second recovery pass over an already-recovered node
is a no-op (the ``recovered_by`` short-circuit).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mtg_utils._card_ir._substrate_purity import assert_substrate_pure, l1_identity
from mtg_utils._card_ir.crosswalk import OTHER, ConceptTree, build_concept_tree, tag_of
from mtg_utils._card_ir.recovery import TokenRule, apply_unimplemented_recovery


def _fixture_tree(name: str) -> ConceptTree:
    """Build one committed-fixture card's ConceptTree (CI-safe: no
    phase/network), mirroring ``test_tree_synthesis._fixture_tree``."""
    from mtg_utils._card_ir.mirror import strict_load_card
    from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema

    path = fixtures_dir() / "crosswalk_fixture_cards.json"
    if not path.exists():
        pytest.skip("crosswalk_fixture_cards.json not present")
    rec = json.loads(Path(path).read_text())["cards"][name]
    root = strict_load_card(rec, load_committed_schema(), name=name)
    return build_concept_tree(root, name=name)


# Probe card for the allowlisted-recovery tests: the first card alphabetically
# in the fixture corpus with EXACTLY ONE role=effect ConceptNode that is
# concept=="other", tag_of(node)=="Unimplemented", carries non-empty raw, and
# whose raw parses (via parse_clause, falling back to scan_clause) to a
# grammar token — "Akki Lavarunner"'s single effect ("flip it") -> "transform".
_PROBE_CARD = "Akki Lavarunner"
_PROBE_TOKEN = "transform"

# A handful of snapshot cards for the identity fast-path test.
_IDENTITY_CARDS = ["Akki Lavarunner", '"Name Sticker" Goblin', "Abbot of Keral Keep"]

# A real card whose sole role=effect "other" node's tag is NOT Unimplemented
# ("OpenAttractions"), so the tag gate must skip it regardless of its raw.
_NON_UNIMPLEMENTED_CARD = '"Lifetime" Pass Holder'


def test_empty_allowlist_is_identity():
    """The production (empty) ALLOWLIST is a behavior-neutral no-op: every
    fixture tree comes back BY IDENTITY."""
    for name in _IDENTITY_CARDS:
        tree = _fixture_tree(name)
        assert apply_unimplemented_recovery(tree) is tree


def test_recovers_allowlisted_token():
    tree = _fixture_tree(_PROBE_CARD)
    unit = tree.units[0]
    node = unit.effects[0]
    assert node.concept == OTHER
    assert tag_of(node.node) == "Unimplemented"
    assert node.raw
    before_node_obj = node.node

    table = {_PROBE_TOKEN: TokenRule(concept="test_concept", category="test_category")}
    before = l1_identity(tree)
    out = apply_unimplemented_recovery(tree, table)

    recovered = out.units[0].effects[0]
    assert recovered.concept == "test_concept"
    assert recovered.category == "test_category"
    assert recovered.recovered_by == _PROBE_TOKEN
    # Re-decoration keeps the SAME .node object (substrate purity by
    # construction) — never a rebuilt/replaced mirror node.
    assert recovered.node is before_node_obj

    # Every other node in the tree is untouched (the probe card has exactly
    # one unit and one effect, so there is nothing else to check positionally
    # beyond costs/statics, which stay empty).
    assert out.units[0].costs == unit.costs
    assert out.units[0].statics == unit.statics
    assert len(out.units) == len(tree.units)

    # The purity guard itself must not raise (same L1 node objects survive).
    assert_substrate_pure(before, out)


def test_token_not_in_allowlist_untouched():
    tree = _fixture_tree(_PROBE_CARD)
    table = {"some_other_token": TokenRule(concept="whatever", category="whatever")}
    out = apply_unimplemented_recovery(tree, table)

    node = out.units[0].effects[0]
    assert node.concept == OTHER
    assert node.recovered_by == ""


def test_non_unimplemented_other_untouched():
    tree = _fixture_tree(_NON_UNIMPLEMENTED_CARD)
    node = tree.units[0].effects[0]
    assert node.concept == OTHER
    assert tag_of(node.node) != "Unimplemented"

    # Force the raw to something the grammar WOULD parse ("raw" is a
    # grounding-only decoration field, not substrate — see ConceptNode's
    # docstring), to prove the tag gate (not the empty-raw gate) is what
    # skips this node. The underlying phase node/tag is real, unmodified.
    assert node.raw == ""
    parseable_raw = "Draw a card."
    from mtg_utils._card_ir.clause_grammar import parse_clause

    assert parse_clause(parseable_raw) == "draw"
    forced_unit = replace(
        tree.units[0],
        effects=(replace(node, raw=parseable_raw), *tree.units[0].effects[1:]),
    )
    forced_tree = replace(tree, units=(forced_unit, *tree.units[1:]))

    table = {"draw": TokenRule(concept="test_concept", category="test_category")}
    out = apply_unimplemented_recovery(forced_tree, table)

    recovered = out.units[0].effects[0]
    assert recovered.concept == OTHER
    assert recovered.recovered_by == ""


def test_already_recovered_not_rerecovered():
    tree = _fixture_tree(_PROBE_CARD)
    table = {_PROBE_TOKEN: TokenRule(concept="test_concept", category="test_category")}

    once = apply_unimplemented_recovery(tree, table)
    node = once.units[0].effects[0]
    assert node.concept == "test_concept"  # already off "other" — OTHER gate
    assert node.recovered_by == _PROBE_TOKEN

    # The recovered_by gate is belt-and-braces on top of the OTHER gate:
    # a second pass over the same (already recovered) tree is a no-op.
    twice = apply_unimplemented_recovery(once, table)
    assert twice is once


# ── ADR-0038 per-key allowlist promotions (production ALLOWLIST, not a
# hand-built table) — #72 discover_makers ─────────────────────────────────


def test_discover_makers_promoted_via_production_allowlist():
    """Curator of Sun's Creation's re-trigger ("discover again for the same
    value") lands as an Unimplemented effect; the production ALLOWLIST's
    "discover" token entry re-decorates it in place (concept="discover",
    recovered_by="discover") so the discover_makers lane's typed
    ``effect_concepts("discover")`` structural read sees it directly — no
    tree_synthesis marker arm needed."""
    tree = _fixture_tree("Curator of Sun's Creation")
    nodes = tree.effect_concepts("discover")
    assert len(nodes) == 1
    assert nodes[0].concept == "discover"
    assert nodes[0].recovered_by == "discover"
    assert tag_of(nodes[0].node) == "Unimplemented"


# ── #72 evasion_denial (static-token recovery) ─────────────────────────────


def test_static_token_matches_evasion_denial_idiom():
    from mtg_utils._card_ir.clause_grammar import static_token

    raw = (
        "Static pattern matched but line failed static parser: Creatures "
        "with landwalk abilities can be blocked as though they didn't have "
        "those abilities."
    )
    assert static_token(raw) == "evasion_denial"


def test_static_token_none_for_unrecognized_static():
    from mtg_utils._card_ir.clause_grammar import static_token

    assert static_token("Static pattern matched but line failed: gibberish") is None


def test_evasion_denial_promoted_via_production_allowlist():
    """Staff of the Ages's own static parser fails on "Creatures with
    landwalk abilities can be blocked as though they didn't have those
    abilities.", leaving an Unimplemented parse-failure residue that is
    STILL role=effect (not role=static); the production ALLOWLIST's
    "evasion_denial" token entry (matched via
    clause_grammar.static_token, parse_clause/scan_clause both miss it)
    re-decorates it in place."""
    tree = _fixture_tree("Staff of the Ages")
    nodes = tree.effect_concepts("evasion_denial")
    assert len(nodes) == 1
    assert nodes[0].concept == "evasion_denial"
    assert nodes[0].recovered_by == "evasion_denial"
    assert nodes[0].role == "effect"
    assert tag_of(nodes[0].node) == "Unimplemented"


# ── #72 end_the_turn (shared-grammar player-subject + verb) ────────────────


def test_parse_clause_matches_end_the_turn_player_grant():
    from mtg_utils._card_ir.clause_grammar import parse_clause

    assert (
        parse_clause("The player whose turn it is may end the turn") == "end_the_turn"
    )


def test_end_the_turn_promoted_via_production_allowlist():
    """Obeka's activated-ability grant ("The player whose turn it is may
    end the turn") lands as an Unimplemented effect; the production
    ALLOWLIST's "end_the_turn" token entry (the "the player whose turn it
    is " subject peel + "end the turn" verb tag, both new shared-grammar
    rows) re-decorates it in place."""
    tree = _fixture_tree("Obeka, Brute Chronologist")
    nodes = tree.effect_concepts("end_the_turn")
    assert len(nodes) == 1
    assert nodes[0].concept == "end_the_turn"
    assert nodes[0].recovered_by == "end_the_turn"
    assert tag_of(nodes[0].node) == "Unimplemented"


# ── W1 dice_makers (roll_die spell/cost-form recovery) ─────────────────────


def test_parse_clause_matches_roll_die_spell_form():
    from mtg_utils._card_ir.clause_grammar import parse_clause

    assert parse_clause("Roll two d6 and choose one result") == "roll_die"


def test_dice_makers_promoted_via_production_allowlist():
    """Valiant Endeavor's "Roll two d6 and choose one result" is the SPELL
    form of a die roll (distinct from the native ``RollDie`` doer node) and
    lands as an Unimplemented effect; the production ALLOWLIST's "roll_die"
    token entry re-decorates it in place (CR 706)."""
    tree = _fixture_tree("Valiant Endeavor")
    nodes = tree.effect_concepts("roll_die")
    assert len(nodes) == 1
    assert nodes[0].concept == "roll_die"
    assert nodes[0].recovered_by == "roll_die"
    assert tag_of(nodes[0].node) == "Unimplemented"


def test_dice_trig_shaped_roll_not_recovered():
    """Pixie Guide's "If you would roll one or more dice, instead roll that
    many dice plus one and ignore the lowest roll." parses to "roll_die" too
    (the cursor lands on the "instead roll" remainder) but its raw ALSO
    matches ``_DICE_TRIG`` (the old-IR's doer/payoff discriminator: a
    dice-roll REFERENCE, not an instruction to roll — CR 706 / CR 614) — the
    production ALLOWLIST's roll_die guard leaves it unrecovered rather than
    conflating a replacement modifier with a maker."""
    tree = _fixture_tree("Pixie Guide")
    assert tree.effect_concepts("roll_die") == ()
    node = tree.units[0].effects[0]
    assert node.concept == OTHER
    assert node.recovered_by == ""
    assert tag_of(node.node) == "Unimplemented"


# ── W2 coin_flip (static-token flip-fixing/modal recovery) ─────────────────


def test_static_token_matches_coin_flip_idiom():
    from mtg_utils._card_ir.clause_grammar import static_token

    assert static_token("flip a coin") == "coin_flip"
    assert (
        static_token(
            "The first time you flip one or more coins each turn, those "
            "coins come up heads and you win those flips."
        )
        == "coin_flip"
    )


def test_coin_flip_promoted_via_production_allowlist_static():
    """Edgar, King of Figaro's "Two-Headed Coin" flip-fixing static lands
    as an Unimplemented effect (no SIMPLE_VERB "flip" arm exists); the
    production ALLOWLIST's "coin_flip" token entry (matched via
    ``static_token``, NOT the imperative-verb grammar) re-decorates it to
    the native "flip_coin" concept (CR 705.3)."""
    tree = _fixture_tree("Edgar, King of Figaro")
    nodes = tree.effect_concepts("flip_coin")
    assert len(nodes) == 1
    assert nodes[0].concept == "flip_coin"
    assert nodes[0].recovered_by == "coin_flip"
    assert tag_of(nodes[0].node) == "Unimplemented"


def test_coin_flip_promoted_via_production_allowlist_modal():
    """Molten Sentry's modal ETB flip ("As ~ enters, flip a coin. ...")
    lands as an Unimplemented effect; the same ALLOWLIST row recovers it
    (CR 705.1)."""
    tree = _fixture_tree("Molten Sentry")
    nodes = tree.effect_concepts("flip_coin")
    assert len(nodes) == 1
    assert nodes[0].concept == "flip_coin"
    assert nodes[0].recovered_by == "coin_flip"
    assert tag_of(nodes[0].node) == "Unimplemented"


# ── W1 batch-4 stax_taxes (opponent cast-lock dynamic-threshold recovery) ──


def test_static_token_matches_stax_cast_lock_idiom():
    from mtg_utils._card_ir.clause_grammar import static_token

    assert static_token("Each opponent can't cast noncreature spells") == (
        "stax_cast_lock"
    )
    assert static_token("your opponents can't cast spells") == "stax_cast_lock"


def test_stax_taxes_promoted_via_production_allowlist():
    """Lavinia, Azorius Renegade's "Each opponent can't cast noncreature
    spells with mana value greater than the number of lands that player
    controls" is a DYNAMIC-threshold restriction phase's own static
    parser can't build, leaving an Unimplemented parse-failure residue;
    the production ALLOWLIST's "stax_cast_lock" token entry (matched via
    ``static_token``, since neither ``parse_clause`` nor ``scan_clause``
    finds an imperative verb in a "can't X" clause) re-decorates it
    straight to the REAL "stax_taxes" concept -- no synth_* marker."""
    tree = _fixture_tree("Lavinia, Azorius Renegade")
    nodes = tree.effect_concepts("stax_taxes")
    assert len(nodes) == 1
    assert nodes[0].concept == "stax_taxes"
    assert nodes[0].recovered_by == "stax_cast_lock"
    assert tag_of(nodes[0].node) == "Unimplemented"
