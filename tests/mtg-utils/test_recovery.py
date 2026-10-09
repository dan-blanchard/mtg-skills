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

from dataclasses import replace

from mtg_utils._card_ir._substrate_purity import assert_substrate_pure, l1_identity
from mtg_utils._card_ir.crosswalk import OTHER, ConceptTree, build_concept_tree, tag_of
from mtg_utils._card_ir.recovery import TokenRule, apply_unimplemented_recovery
from mtg_utils.testkit import test_phase_records


def _fixture_tree(name: str) -> ConceptTree:
    """Build one real card's RAW ConceptTree from its snapshot phase record
    (CI-safe: no phase/network), mirroring ``test_tree_synthesis._fixture_tree``."""
    from mtg_utils._card_ir.mirror import strict_load_card
    from mtg_utils._card_ir.mirror.build import load_committed_schema

    rec = next(r for r in test_phase_records(name) if r["name"] == name)
    root = strict_load_card(rec, load_committed_schema(), name=name)
    return build_concept_tree(root, name=name)


# Probe card for the allowlisted-recovery tests: the first card alphabetically
# in the old crosswalk fixture corpus with EXACTLY ONE role=effect ConceptNode that is
# concept=="other", tag_of(node)=="Unimplemented", carries non-empty raw, and
# whose raw parses (via parse_clause, falling back to scan_clause) to a
# grammar token NOT in the production ALLOWLIST — "Defiling Tears"' "become black,
# gets +1/-1, and gains '{B}: Regenerate ~.'" -> "regenerate". (Was "Averna, the
# Chaos Bloom"'s "reanimate" until the v0.104.0 bump added that token to the
# production ALLOWLIST, so build_concept_tree recovers it already; "Akki
# Lavarunner"'s "transform" before the v0.45.0 bump.)
# The name is written at each call site, a literal the snapshot scan can see.
_PROBE_TOKEN = "regenerate"

# The tag-gate test's card, '"Lifetime" Pass Holder', is a real card whose sole
# role=effect "other" node's tag is NOT Unimplemented ("OpenAttractions"), so the
# tag gate must skip it regardless of its raw.


def test_empty_allowlist_is_identity():
    """The production (empty) ALLOWLIST is a behavior-neutral no-op: every
    fixture tree comes back BY IDENTITY."""
    for name in ("Akki Lavarunner", '"Name Sticker" Goblin', "Abbot of Keral Keep"):
        tree = _fixture_tree(name)
        assert apply_unimplemented_recovery(tree) is tree


def test_recovers_allowlisted_token():
    tree = _fixture_tree("Defiling Tears")
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
    tree = _fixture_tree("Defiling Tears")
    table = {"some_other_token": TokenRule(concept="whatever", category="whatever")}
    out = apply_unimplemented_recovery(tree, table)

    node = out.units[0].effects[0]
    assert node.concept == OTHER
    assert node.recovered_by == ""


def test_non_unimplemented_other_untouched():
    tree = _fixture_tree('"Lifetime" Pass Holder')
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
    tree = _fixture_tree("Defiling Tears")
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
    """RETIRED-ROW graduation pin (task #84): Curator of Sun's Creation's
    re-trigger ("discover again for the same value") parses NATIVELY at
    phase v0.23.0 — a typed ``Discover`` node carrying a
    ``TriggeringDiscoverValue`` mana_value_limit under a ``Discover``-mode
    trigger — so the ALLOWLIST's "discover" token row was retired (its
    re-census found zero remaining Unimplemented-discover residues) and the
    discover_makers lane's ``effect_concepts("discover")`` read now sees
    the real node with NO recovery decoration."""
    tree = _fixture_tree("Curator of Sun's Creation")
    nodes = tree.effect_concepts("discover")
    assert len(nodes) == 1
    assert nodes[0].concept == "discover"
    assert nodes[0].recovered_by == ""
    assert tag_of(nodes[0].node) == "Discover"


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


def test_dice_trig_shaped_roll_is_a_typed_replacement_not_recovered():
    """Pixie Guide's "If you would roll one or more dice, instead roll that
    many dice plus one and ignore the lowest roll." — through v0.66.0 an
    ``Unimplemented('replacement_structure')`` residue the production
    ALLOWLIST's roll_die guard left unrecovered (a dice-roll REFERENCE, not an
    instruction to roll — CR 706.6 / 614.1a). phase v0.86.0 parses it as a
    ``replacements[]`` unit (``event: RollDice``) whose ``execute`` carries a
    TYPED ``RollDie``: the concept is decorated straight off the node (no
    recovery stamp), and the dice_makers gate reads the unit's origin to keep
    a roll-replacement out of the maker lane."""
    tree = _fixture_tree("Pixie Guide")
    (unit,) = tree.units
    assert unit.origin == "replacement"
    assert getattr(unit.node, "event", None) == "RollDice"
    (node,) = unit.effects
    assert node.concept == "roll_die"
    assert node.recovered_by == ""
    assert tag_of(node.node) == "RollDie"


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


# ── W1 batch-4 fight_makers (third-resolution / modal-bullet recovery) ─────


def test_parse_clause_matches_fight_verb():
    from mtg_utils._card_ir.clause_grammar import parse_clause

    assert parse_clause("~ fights up to one target creature") == "fight"
    assert parse_clause("This creature fights another target creature") == "fight"


def test_fight_makers_promoted_via_production_allowlist():
    """Gimli, Mournful Avenger's third-resolution rider ("When this
    ability resolves for the third time this turn, ~ fights up to one
    target creature you don't control.") lands as an Unimplemented
    effect; the production ALLOWLIST's "fight" token entry re-decorates
    it in place to the native "fight" concept (CR 701.12)."""
    tree = _fixture_tree("Gimli, Mournful Avenger")
    nodes = tree.effect_concepts("fight")
    assert len(nodes) == 1
    assert nodes[0].concept == "fight"
    assert nodes[0].recovered_by == "fight"
    assert tag_of(nodes[0].node) == "Unimplemented"


# ── ADR-0038 W5 tails "damage" (computed-amount deal-damage recovery) ──────


def test_parse_clause_matches_damage_verb():
    from mtg_utils._card_ir.clause_grammar import parse_clause

    assert parse_clause("deal damage to any target equal to X") == "damage"
    assert (
        parse_clause("deals 4 damage to that player unless they control a commander")
        == "damage"
    )


def test_direct_damage_promoted_via_production_allowlist():
    """Soulblast's "deals damage to any target equal to the total power of
    the sacrificed creatures" (CR 120.1) is a computed-amount ``DealDamage``
    phase's own ``Ref``/``Qty`` grammar can't structure at all, leaving the
    WHOLE clause as an Unimplemented residue; the production ALLOWLIST's
    "damage" token entry re-decorates it in place to the native
    "deal_damage" concept — no typed ``target`` field survives, so
    ``direct_damage`` direction-gates on the seam's ``OTHER_PLAYER`` mark."""
    tree = _fixture_tree("Soulblast")
    nodes = tree.effect_concepts("deal_damage")
    assert len(nodes) == 1
    assert nodes[0].concept == "deal_damage"
    assert nodes[0].recovered_by == "damage"
    assert tag_of(nodes[0].node) == "Unimplemented"


def test_damage_recovery_rejects_face_up_replacement_sense():
    """Illusionary Mask's face-down replacement clause LISTS "assigns or
    deals damage, is dealt damage, or becomes tapped" among several
    conditions a face-down creature would trigger (CR 707.4a turning face
    up) — not an independent damage EFFECT. The ``_NON_DAMAGE_SENSE`` seam
    guard rejects it; the node stays concept=="other", never re-decorated."""
    tree = _fixture_tree("Illusionary Mask")
    assert tree.effect_concepts("deal_damage") == ()
    other_raws = [c.raw for c in tree.iter_concepts() if c.concept == OTHER]
    assert any("turned face up" in (r or "") for r in other_raws)


def test_damage_recovery_rejects_combat_damage_condition_sense():
    """Skyway Robber's Escape rider grants a NEW triggered ability whose
    quoted CONDITION mentions "deals combat damage to a player" — a
    trigger-condition description, not a ``DealDamage`` EFFECT (CR 510.1c
    combat damage is a categorically different mechanism than a spell/
    ability's own damage effect). The ``_NON_DAMAGE_SENSE`` seam guard
    rejects it (both parsers already failed on this line, so it survives as
    an ``Unimplemented`` residue either way)."""
    tree = _fixture_tree("Skyway Robber")
    assert tree.effect_concepts("deal_damage") == ()


# ── read_clause: the seam's one reading of a recovered clause ──────────────────
# Clause strings here are machinery input (the reader is a pure text read); the
# real-card pins for the lanes that test these marks live in
# test_v0104_lane_guards.py.

import pytest  # noqa: E402

from mtg_utils._card_ir.recovery import (  # noqa: E402
    ALLOWLIST,
    ANY_TARGET,
    CLAUSE_MARKS,
    EACH_OBJECT,
    IMPERATIVE,
    MANY,
    ON_SELF,
    OTHER_CHOOSER,
    OTHER_PLAYER,
    PLAYER,
    POWER_SCALED,
    SELF,
    TARGET_OBJECT,
    THEIRS,
    YOUR_TARGET,
    YOURS,
    read_clause,
)


def _subject(raw: str, token: str = "") -> tuple[str, ...]:
    verb = ALLOWLIST[token].object_verb if token else ""
    return read_clause(raw, None, verb)[1]


@pytest.mark.parametrize(
    ("raw", "has_self"),
    [
        ("return this card from your graveyard to your hand", True),
        ("put ~ onto the battlefield", True),
        ("create a token that's a copy of ~", True),
        ("sacrifice ~ unless you pay {1}", True),
        # The card as the doer or a possessive is no self-object.
        ("~ deals 2 damage to any target", False),
        ("put a +1/+1 counter on each creature with power less than ~'s power", False),
        # "it" names the card only on a unit whose "it" starts out as the card.
        ("return it to the battlefield", False),
    ],
)
def test_self_is_the_card_as_the_clauses_object(raw, has_self):
    assert (SELF in _subject(raw)) is has_self


def test_on_self_is_counters_put_on_the_card():
    assert ON_SELF in _subject("put a +1/+1 counter on ~")
    assert ON_SELF not in _subject("equal to the number of +1/+1 counters on ~")


def test_imperative_is_a_clause_opening_on_its_verb():
    assert IMPERATIVE in _subject("if it's a creature, sacrifice that many permanents")
    assert IMPERATIVE in _subject("you may sacrifice another creature")
    assert IMPERATIVE not in _subject("target opponent sacrifices a creature")


def test_target_object_is_bound_to_the_tokens_verb():
    # Karn, Living Legacy's emblem: the tap is a cost; the target is the damage's.
    raw = "Tap an untapped artifact you control: ~ deals 1 damage to any target."
    assert TARGET_OBJECT not in _subject(raw, "tap")
    assert TARGET_OBJECT in _subject("tap target creature", "tap")
    assert TARGET_OBJECT in _subject("destroy up to one target artifact", "destroy")
    assert TARGET_OBJECT not in _subject(
        "deals 3 damage to the owner of target haunted creature", "damage"
    )
    assert TARGET_OBJECT in _subject(
        "deals damage equal to its power to any other target", "damage"
    )


def test_your_target_is_the_verbs_own_target():
    assert YOUR_TARGET in _subject(
        "deal damage to target creature you control equal to the damage", "damage"
    )
    # Syrix: the doer is yours, the damage's target is any target.
    assert YOUR_TARGET not in _subject(
        "target Phoenix you control deals damage equal to its power to any target",
        "damage",
    )


def test_each_object_is_bound_to_the_tokens_verb():
    assert EACH_OBJECT in _subject(
        "put a +1/+1 counter on each other creature you control", "place_counter"
    )
    assert EACH_OBJECT not in _subject(
        "Put a +1/+1 counter on ~ for each strength vote", "place_counter"
    )


@pytest.mark.parametrize(
    ("raw", "mark"),
    [
        ("all creature cards in your opponents' graveyards", THEIRS),
        ("return target creature card from your graveyard", YOURS),
        ("deals damage equal to its power to its controller", PLAYER),
        ("deals 2 damage to any other target", ANY_TARGET),
        ("deals damage equal to his power", POWER_SCALED),
        ("if it was historic, draw two cards", MANY),
        ("on target creature of defending player's choice", OTHER_CHOOSER),
    ],
)
def test_clause_marks(raw, mark):
    assert mark in _subject(raw)


def test_zones_name_the_exile_zone_not_a_linked_pile():
    assert "Exile" in read_clause("cast spells from among cards in exile")[2]
    assert "Exile" not in read_clause("play lands from among cards exiled with ~")[2]


def test_scope_names_the_opponents_side():
    assert read_clause("put the top creature card of defending player's graveyard")[
        0
    ] == ("opponents")
    assert read_clause("return this card to your hand")[0] is None


def test_clause_marks_lists_every_mark():
    marks = set(CLAUSE_MARKS)
    assert {SELF, ON_SELF, IMPERATIVE, TARGET_OBJECT, YOUR_TARGET, EACH_OBJECT} <= marks
    assert len(marks) == len(CLAUSE_MARKS)


def test_reanimate_names_no_zone_of_its_own():
    # The grammar's reanimate token fires on any "put … onto the battlefield",
    # so the clause's own zones say whether a graveyard is involved.
    assert ALLOWLIST["reanimate"].zones == ()


def _row_reading(raw: str, token: str) -> tuple[str, ...]:
    rule = ALLOWLIST[token]
    return read_clause(
        raw,
        None,
        rule.object_verb,
        other_player=rule.other_player,
        token_types=rule.token_types,
    )[1]


@pytest.mark.parametrize(
    ("raw", "token", "other"),
    [
        # draw: another player draws, alone or beside you, never past an "if"
        ("When it regenerates this way, that player may draw a card", "draw", True),
        ("you and the attacking player each draw a card", "draw", True),
        ("you draw a card if they didn't attack you that turn", "draw", False),
        ("if it was historic, draw two cards", "draw", False),
        # discard: another player discards, or the cards are theirs
        ("each opponent discards a card", "discard", True),
        ("discard all cards with that name revealed this way", "discard", True),
        ("discard a card unless this spell was cast using teamwork", "discard", False),
        # damage: it can reach a player other than you
        (
            "~ deals 4 damage to that player unless they control a commander",
            "damage",
            True,
        ),
        ("deal damage to any target equal to X", "damage", True),
        ("~ deals damage equal to its power to you", "damage", False),
        # make_token: another player creates the token (CR 111.2)
        (
            "who voted for a choice you voted for creates a Treasure token",
            "make_token",
            True,
        ),
        ("create a Treasure token", "make_token", False),
    ],
)
def test_other_player_is_the_rows_own_reading(raw, token, other):
    assert (OTHER_PLAYER in _row_reading(raw, token)) is other


def test_a_token_rows_types_are_the_created_objects_own():
    # "Human" names the condition's creature, "Food" the token.
    reading = _row_reading(
        "if another Human died under your control this turn, create a Food token",
        "make_token",
    )
    assert "Food" in reading
    assert "Creature" not in reading
    assert "Powerstone" in _row_reading(
        "if you didn't play a card from exile this turn, create a tapped Powerstone "
        "token",
        "make_token",
    )


def test_a_token_rows_reading_goes_to_the_clause_field():
    # make_token's subject is the token's own types (token_maker reads it), so its
    # reading — like discard's and lose_life's, whose scope the overlay keeps —
    # goes to ``clause``.
    for token in ("make_token", "discard", "lose_life"):
        assert ALLOWLIST[token].into_clause, token
    assert not ALLOWLIST["draw"].into_clause


def test_imperative_includes_you_as_the_doer():
    assert IMPERATIVE in _subject(
        "if you control an enchanted creature, you lose 1 life"
    )
    assert IMPERATIVE in _subject("Then if it has two counters on it, sacrifice it")


def test_a_compound_clause_recovers_each_instruction_on_one_node():
    # "if you control an enchanted creature, you lose 1 life and you draw an
    # additional card": both verbs decorate the SAME residue node, so the
    # substrate fingerprint (each node once) is unchanged.
    tree = _fixture_tree("Lord Skitter's Blessing")
    (unit,) = (u for u in tree.units if any(c.recovered_by for c in u.effects))
    recovered = [c for c in unit.effects if c.recovered_by]
    assert [c.recovered_by for c in recovered] == ["lose_life", "draw"]
    assert recovered[0].node is recovered[1].node
    assert recovered[1].raw == "draw an additional card"


def test_a_granted_bodys_residue_is_recovered_where_the_walk_reads_it():
    from mtg_utils._card_ir.crosswalk import iter_nested_granted_effect_concepts

    tree = _fixture_tree("Shackles of Treachery")
    granted = [
        c
        for u in tree.units
        for c in iter_nested_granted_effect_concepts(u.node)
        if c.recovered_by
    ]
    assert [c.recovered_by for c in granted] == ["destroy"]
    assert TARGET_OBJECT in granted[0].subject


def test_a_second_pass_adds_no_instruction_twice():
    # Darigaaz Reincarnated's first instruction (removing an egg counter) has no
    # verb token, its later "return it to the battlefield" recovers; a second
    # pass over the built tree is a no-op.
    tree = _fixture_tree("Darigaaz Reincarnated")
    assert any(c.recovered_by == "reanimate" for u in tree.units for c in u.effects)
    assert apply_unimplemented_recovery(tree) is tree
