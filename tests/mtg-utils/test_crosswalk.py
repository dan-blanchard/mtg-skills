"""Stage-2 gate for the Layer-2 concept overlay + first concept batch (ADR-0035).

The crosswalk is ADDITIVE — nothing in production reads it; these tests are the
shipped deliverable. They run CI-safe off two committed fixtures
(``crosswalk_fixture_cards.json`` = a curated slice of phase ``card-data.json``
records, ``phase_mirror_schema.json`` = the generated mirror schema): strict-load
each record → build the concept overlay → derive the ported Signals — with **no**
bulk / sidecar / phase / network.

The baked granularity fixtures are load-bearing: a flat-overlay regression (one
that collapsed the per-ability / whole-card join structure) fails these loud.

  * **(a) per-ability sibling co-occurrence** — Psychic Frog & Nezahal must NOT
    fire ``discard_makers`` (their draw and discard live in DIFFERENT ability
    units, and the discard is a cost), while Faithless Looting / The Locust God
    (draw + discard in one unit) must.
  * **(b) per-ability aggregation** — the animate-land split-subject (Natural
    Emergence / Sylvan Advocate) reconstructs ``land_creatures_matter``; the
    symmetric all-lands animate (Living Plane) is correctly scoped out.
  * **(c) whole-card reconciliation** — a spell-copier (Twincast) cross-opens
    ``spellcast_matters`` LOW.
"""

from __future__ import annotations

import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptTree,
    build_concept_tree,
)
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._card_ir.overlay_corrections import (
    SubstratePurityError,
    _assert_substrate_pure,
    _l1_identity,
    _l1_nodes,
    apply_overlay_corrections,
    l1_bytes,
)
from mtg_utils._deck_forge.crosswalk_signals import (
    _PORTED_KEYS_STAGE3,
    extract_crosswalk_signals,
)

FIXTURE = "crosswalk_fixture_cards.json"


@lru_cache(maxsize=1)
def _fixture() -> dict:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return json.loads(Path(path).read_text())


def _cards() -> dict[str, dict]:
    return _fixture()["cards"]


def _kw(name: str) -> frozenset[str]:
    """The card's real Scryfall keyword array (the mill_makers field-lookup source).

    Not in the phase typed substrate (phase carries no ``Mill`` keyword), so the
    fixture stores it alongside the phase records — the shadow diff reads the same
    array off the bulk record. Absent == no keywords.
    """
    return frozenset(_fixture().get("scryfall_keywords", {}).get(name, ()))


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _tree(name: str) -> ConceptTree:
    rec = _cards()[name]
    root = strict_load_card(rec, _schema(), name=name)
    return build_concept_tree(root, name=name)


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {
        (s.key, s.scope, s.subject)
        for s in extract_crosswalk_signals(_tree(name), keywords=_kw(name))
    }


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── framework: tree-preserving overlay + lossless "other" ─────────────────────


def test_overlay_is_tree_preserving_with_typed_units():
    """Every unit is an AbilityUnit hanging off a verbatim typed node."""
    tree = _tree("Krenko, Mob Boss")
    assert tree.units, "expected at least one ability unit"
    for unit in tree.units:
        assert isinstance(unit, AbilityUnit)
        assert unit.origin in ("ability", "trigger", "static", "replacement")
        # the unit carries the verbatim typed node (round-trips losslessly)
        assert (
            unit.node.to_dict()
            == _cards()["Krenko, Mob Boss"][
                {
                    "ability": "abilities",
                    "trigger": "triggers",
                    "static": "static_abilities",
                    "replacement": "replacements",
                }[unit.origin]
            ][unit.index]
        )


def test_other_concept_carries_verbatim_typed_node():
    """An unrecognized effect decorates as ``OTHER`` carrying its verbatim node."""
    # Krenko's tap activation makes a Token (recognized); its activation cost / any
    # non-batch effect carries through as OTHER. Find one and assert losslessness.
    tree = _tree("Nezahal, Primal Tide")
    others = [c for c in tree.iter_concepts() if c.concept == OTHER]
    assert others, "expected at least one carried-verbatim 'other' concept"
    for c in others:
        # the carried node is the verbatim typed instance — to_dict round-trips
        assert isinstance(c.node.to_dict(), dict)


def test_make_token_is_subject_bearing():
    """A creature-token effect surfaces the token's types on its concept node."""
    tree = _tree("Krenko, Mob Boss")
    toks = tree.effect_concepts("make_token")
    assert toks
    assert "Goblin" in toks[0].subject


# ── Batch 2 framework capabilities (new typed reads) ──────────────────────────


def test_card_types_whole_card_type_read():
    """The card's own core types ride the tree (is-creature / is-land gates)."""
    assert _tree("Sol Ring").is_type("Artifact")
    assert _tree("Command Tower").is_type("Land")
    assert _tree("Blood Artist").is_type("Creature")
    assert not _tree("Sol Ring").is_type("Land")


def test_filter_predicate_token_survives():
    """``filter_predicates`` surfaces the ``Token`` predicate off a typed filter —
    the read tokens_matter gates on (distinct from the Creature type word)."""
    from mtg_utils._card_ir.crosswalk import filter_predicates

    tree = _tree("Intangible Virtue")
    static = next(u for u in tree.units if u.origin == "static")
    preds = filter_predicates(static.node.affected)
    assert "Token" in preds
    assert "Creature" in static.statics[0].subject  # type word ≠ predicate


def test_trigger_subject_reads_watched_object():
    """``trigger_subject`` reads the watched OBJECT's types; a bare self-death is
    empty (the death-vs-self-death gate)."""
    from mtg_utils._card_ir.crosswalk import trigger_subject

    cobra = _tree("Lotus Cobra")
    land_trig = next(u for u in cobra.units if u.trigger_event == "enters")
    assert "Land" in trigger_subject(land_trig.node)
    solemn = _tree("Solemn Simulacrum")
    death = next(u for u in solemn.units if u.trigger_event == "dies")
    assert trigger_subject(death.node) == ()  # bare SelfRef


def test_change_zone_dirs_reads_origin_destination():
    """``change_zone_dirs`` exposes a ChangeZone EFFECT's (origin, destination) —
    reanimation reads (Graveyard, Battlefield)."""
    from mtg_utils._card_ir.crosswalk import change_zone_dirs

    tree = _tree("Sheoldred, Whispering One")
    cz = next(c for c in tree.effect_concepts("change_zone"))
    assert change_zone_dirs(cz.node) == ("Graveyard", "Battlefield")


# ── granularity (a): per-ability sibling co-occurrence (discard_makers) ────────


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Faithless Looting", True),  # draw + discard in ONE ability unit
        ("The Locust God", True),  # activated loot: draw effect + discard
        ("Psychic Frog", False),  # draw TRIGGER + discard COST, diff units
        ("Nezahal, Primal Tide", False),  # draw trigger + discard cost, diff units
    ],
)
def test_discard_makers_per_ability_co_occurrence(name, should_fire):
    assert (("discard_makers", "you", "") in _idents(name)) is should_fire


def test_psychic_frog_draw_and_discard_are_in_different_units():
    """The structural guard a flat overlay would break: Psychic Frog's draw is a
    trigger-unit effect and its discard is an activation COST of another unit —
    never co-located, so the per-ability gate cannot fire."""
    tree = _tree("Psychic Frog")
    draw_units = [u for u in tree.units if u.has_effect("draw")]
    disc_effect_units = [u for u in tree.units if u.effect_concepts("discard")]
    assert draw_units, "Psychic Frog draws on combat damage"
    assert not disc_effect_units, "Psychic Frog's discard is a cost, not an effect"
    # the discard IS present — as a cost-role concept on a different unit
    disc_costs = [c for u in tree.units for c in u.costs if c.concept == "discard"]
    assert disc_costs, "the discard is preserved as a cost-role concept"


# ── granularity (b): per-ability aggregation (animate-land split-subject) ──────


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Sylvan Advocate", True),  # dual Land+Creature subject anthem
        ("Natural Emergence", True),  # your-lands animator (static AddType Creature)
        ("Living Plane", False),  # symmetric ALL-lands animate — scoped out
    ],
)
def test_land_creatures_matter_aggregation(name, should_fire):
    assert (("land_creatures_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        "Badgermole",  # first-class Animate node (earthbend — Land you control)
        "Awakener Druid",  # threaded one-shot ("target Forest becomes a creature")
    ],
)
def test_land_creatures_matter_animator_alignment(name):
    """recall-completion b2 (ADR-0034): align the you-scoped land animator with the
    land_protection breadth. The static-only ``_is_creature_animator`` missed the
    first-class ``Animate`` EFFECT node (Badgermole's earthbend) and the threaded
    one-shot animate (Awakener Druid) — both turn YOUR land into a creature, the same
    land-creatures payoff land_protection already caught (CR 305 / 110.1)."""
    assert ("land_creatures_matter", "you", "") in _idents(name)


# ADR-0038 W3 batch 4 (lands-and-ramp cluster): the mass-static / threaded
# search-chain animator additions. Verified CR: 305.7 ("setting a land's
# subtype doesn't add or remove any card types [such as creature]"),
# 110.1 (permanent), 305 / 110.1 (land + creature generally).
@pytest.mark.parametrize(
    "name",
    [
        "Rude Awakening",  # Entwine mode: mass static, affected controller='You'
        "Rampaging Growth",  # ParentTarget-threaded search-then-animate chain
    ],
)
def test_land_creatures_matter_mass_and_threaded_search_animate(name):
    assert ("land_creatures_matter", "you", "") in _idents(name)


def test_land_creatures_matter_excludes_land_type_only_change():
    """Dryad of the Ilysian Grove: "Lands you control are every basic land type
    in addition to their other types" changes land SUBTYPE only — no Creature
    type is ever added (CR 305.7). Not a land-creatures anthem/animator, even
    though the card's OTHER ability ("play an additional land") legitimately
    fires ``landfall``."""
    assert "land_creatures_matter" not in _keys("Dryad of the Ilysian Grove")


# ── granularity (c): whole-card reconciliation (spell-copy → spellcast) ────────


@pytest.mark.parametrize("name", ["Twincast", "Thousand-Year Storm"])
def test_spell_copy_cross_opens_spellcast(name):
    idents = _idents(name)
    assert ("spell_copy_makers", "you", "") in idents
    assert ("spellcast_matters", "you", "") in idents


def test_reconciliation_only_fires_with_spell_copy():
    """A card with no spell-copier does not get the spellcast cross-open."""
    assert "spellcast_matters" not in _keys("Thassa's Oracle")


# ── the remaining batch concepts ──────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Thassa's Oracle", "Door to Nothingness"])
def test_win_lose_game_terminal_effect(name):
    assert ("win_lose_game", "any", "") in _idents(name)


def test_token_maker_subject_resolution():
    assert ("token_maker", "you", "Goblin") in _idents("Krenko, Mob Boss")
    assert ("token_maker", "you", "Insect") in _idents("The Locust God")


def test_token_maker_nested_descent():
    """ADR-0038 W5b: :func:`iter_nested_token_effects` reaches a make_token
    effect buried inside a granted static/triggered ability the flat per-unit
    walk never surfaces as its own unit-level effect — a GrantStaticAbility
    definition (Presence of Gond's Aura grant: "Enchanted creature has '{T}:
    Create a 1/1 green Elf Warrior creature token.'"; Veteran Soldier's
    "Commander creatures you own have '...for each opponent, create a 1/1
    white Soldier creature token...'") and a CreateEmblem (Kiora, the Crashing
    Wave's -5: "You get an emblem with '...create a 9/9 blue Kraken creature
    token.'"). CR 111.2/205.3i."""
    assert ("token_maker", "you", "Warrior") in _idents("Presence of Gond")
    assert ("token_maker", "you", "Soldier") in _idents("Veteran Soldier")
    assert ("token_maker", "you", "Kraken") in _idents("Kiora, the Crashing Wave")


def test_token_maker_detective_singularize_fix():
    """ADR-0038 W5b: ``detective`` is already singular, but the blanket
    ``endswith("ve")`` stemming rule in ``_singularize`` mis-derived it as
    "detectif" (matching the "Wolves" -> "Wolf" plural pattern), silently
    dropping the subject for every Detective-token maker (Museum Nightwatch:
    "When this creature dies, create a 2/2 white and blue Detective creature
    token."). Fixed via an ``IRREGULAR_SINGULAR`` identity-mapping exception
    (the "djinn"/"efreet" precedent)."""
    assert ("token_maker", "you", "Detective") in _idents("Museum Nightwatch")


def test_token_maker_empty_types_mirror_fallback():
    """ADR-0038 W5b: phase's ``Token`` effect carries NO ``types`` at all for
    Brudiclad, Telchor Engineer's own triggered maker ("create a 2/1 blue
    Phyrexian Myr artifact creature token") — resolved via the SAME bucket-B
    ``_mirror_token_maker_type_subjects`` mirror ``type_matters``'s
    token-profile membership reconciliation already uses (ADR-0036/0037
    T10-finalize2), literal-gated on "create ... creature token(s)" so a
    non-creature (Treasure/Clue) empty-typed token never wrongly fires. A
    THIRD-person "creates?" widening on the SHARED ``_TOKEN_MAKER_PATTERN``
    was tried and REVERTED in this pass — that pattern is the SAME one
    legacy's own kept-mirror scans on every clause, so widening it widened
    legacy's OWN ground truth to opponent-directed "Its controller
    creates ..." clauses too (a corpus-wide re-measurement showed live_only
    INCREASE, not shrink). ADR-0038 W5c closes the symmetric case via a
    LOCAL, lane-only regex instead (:func:`test_token_maker_each_player_
    creates_widening`) — the shared pattern itself stays unwidened."""
    assert ("token_maker", "you", "Myr") in _idents("Brudiclad, Telchor Engineer")


def test_token_maker_excludes_token_copy_boundary():
    """CRITICAL BOUNDARY (CR 707): "create a token that's a copy of ..."
    (Rite of Replication) is ``token_copy_makers`` (a separate, already-
    PROMOTED concept — ``CopyTokenOf``/``Populate``/``BecomeCopy``), never
    ``token_maker`` — neither the structural nor the nested-descent arm
    (:func:`iter_nested_token_effects`) reads a ``Token`` tag off a
    token-COPY clause because phase never nests one there (corpus-verified).
    """
    assert "token_maker" not in _keys("Rite of Replication")


def test_token_maker_recovered_node_unconditional_mirror():
    """ADR-0038 W5c: the byte-identical kept mirror (``_detect_token_maker``)
    now runs UNCONDITIONALLY per clause, closing the recovered-node tail
    with NO OTHER structural make_token anchor on the card — a whole-clause
    Unimplemented residue (Consuming Blob's "create a green Ooze creature
    token with '...'") decorates with an EMPTY types tuple via the
    ``make_token`` recovery row, but W5b's ``need_mirror`` flag only trips
    when the SAME per-unit loop iterates at least one node, so a LONE
    empty-types node with no sibling stayed gap-only under that gate. CR
    701.7/111.2."""
    assert ("token_maker", "you", "Ooze") in _idents("Consuming Blob")


def test_token_maker_each_player_creates_widening():
    """ADR-0038 W5c: a LOCAL "each player creates" regex (CR 111.2 — you're
    one of the "each player"s, so you get a token too), scoped to
    ``_token_maker`` only — never the SHARED ``_TOKEN_MAKER_PATTERN`` W5b's
    reverted attempt widened (see :func:`test_token_maker_empty_types_
    mirror_fallback`). Catches the inflected third-person "creates"
    (Elephant Resurgence: "Each player creates a green Elephant creature
    token."). Deliberately excludes an "other than target player" qualifier
    (Death by Dragons: "Each player other than target player creates a 5/5
    red Dragon creature token with flying." — the excluded player could be
    YOU, so it is not symmetric)."""
    assert ("token_maker", "you", "Elephant") in _idents("Elephant Resurgence")
    assert "token_maker" not in _keys("Death by Dragons")
    assert ("token_copy_makers", "you", "") in _idents("Rite of Replication")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("The Locust God", True),  # "whenever you draw a card" — Drawn trigger
        ("A-Orcish Bowmasters", False),  # opponent-draw punisher — not draw_matters
        ("Mulldrifter", False),  # self-ETB value, no draw trigger
    ],
)
def test_draw_matters_trigger_event(name, should_fire):
    assert (("draw_matters", "you", "") in _idents(name)) is should_fire


# ── Batch 2 (ADR-0035 Stage 2): the next 12 concepts ──────────────────────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Blood Artist", ("death_matters", "any", "")),  # Or[self, another creature]
        ("Midnight Reaper", ("death_matters", "you", "")),  # creature you control
    ],
)
def test_death_matters_fires_with_scope(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Solemn Simulacrum", "Mulldrifter"],  # bare-self death / no death trigger
)
def test_death_matters_excludes_self_and_nondeath(name):
    assert "death_matters" not in _keys(name)


def test_extra_turns_fires():
    assert ("extra_turns", "you", "") in _idents("Time Warp")


@pytest.mark.parametrize(
    "name",
    ["Gray Merchant of Asphodel", "Basilisk Collar"],  # gain_life / granted lifelink
)
def test_lifegain_makers_fires(name):
    assert ("lifegain_makers", "you", "") in _idents(name)


def test_own_lifelink_keyword_fires_lifegain_makers():
    # ADR-0035 Stage-A recall (+325 corpus): the card's OWN printed lifelink
    # keyword opens lifegain_makers via the keyword path (mirrors
    # _signals_ir._IR_KEYWORD_MAP["lifelink"]) — the _lifegain_makers typed lane
    # reads only gain_life effects + GRANTED lifelink, so a vanilla-lifelink
    # creature (no grant node) needed this keyword row.
    from mtg_utils._deck_forge.crosswalk_signals import _keyword_field_signals

    sigs = _keyword_field_signals(frozenset({"Lifelink"}), "Aerial Responder")
    assert ("lifegain_makers", "you", "") in {(s.key, s.scope, s.subject) for s in sigs}
    # a non-lifegain evergreen keyword does not open the lane
    assert not _keyword_field_signals(frozenset({"Flying"}), "Bird")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 119.3) — a GainLife effect buried ANYWHERE
        # under a unit, reached via the has_nested_roll_die / has_nested_
        # flip_coin / has_nested_fight precedent (one iter_typed_nodes deep
        # walk, no per-container code): a GrantTrigger on an Aura's OWN
        # enchanted permanent (Farmstead — "Enchanted land has 'At the
        # beginning of your upkeep, you may pay {W}{W}. If you do, you gain
        # 1 life.'"), a GrantAbility activated ability on an Aura (Ephara's
        # Radiance — "Enchanted creature has '{1}{W}, {T}: You gain 3
        # life.'") or granted to EVERY permanent of a type (Victual Sliver
        # — "All Slivers have '{2}, Sacrifice this permanent: You gain 4
        # life.'"), and the SAME GrantTrigger buried a level DEEPER still
        # inside a created TOKEN's own static_abilities (Send in the Pest
        # — "create a ... Pest ... token with 'Whenever ~ attacks, you gain
        # 1 life.'").
        "Farmstead",
        "Ephara's Radiance",
        "Victual Sliver",
        "Send in the Pest",
    ],
)
def test_lifegain_makers_nested_grant_arm(name):
    assert ("lifegain_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 119.3) — the bucket-B text-idiom bridge
        # (arms 1-3 above find NOTHING — no GainLife node anywhere): Drain
        # Life's capped-lifegain formula ("gain life equal to the damage
        # dealt, but not more life than ...") and Soul Burn's sibling both
        # phase-parse as a bare Unimplemented "gain" clause; Predator's
        # Rapport's "gain life equal to that creature's power plus its
        # toughness" the same; Necravolver's kicker-BRANCHED granted
        # trigger ("with 'Whenever ~ deals damage, you gain that much
        # life.'") fails to structure as a clean GrantTrigger because the
        # grant itself is conditional on which kicker was paid.
        "Drain Life",
        "Soul Burn",
        "Predator's Rapport",
        "Necravolver",
    ],
)
def test_lifegain_makers_text_idiom_bridge(name):
    assert ("lifegain_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 — the text-idiom bridge's per-CLAUSE exclusion
        # (boundary lesson (iii)): "Whenever you gain life, <payoff>" is the
        # ubiquitous lifegain_MATTERS trigger CONDITION (a card that CARES
        # about gaining life, not a SOURCE of it) — phase parses the
        # WheneverEvent condition itself perfectly structurally, so this is
        # a precision gate, not a parser-gap workaround. Covers the "gain OR
        # LOSE life" variant (Wax-Wane Witness) and the "for the first time
        # each turn" variant (Deathless Knight), neither of which put a
        # comma immediately after "life" in the SAME shape as a genuine
        # source clause.
        "Ajani's Pridemate",
        "Sanguine Bond",
        "Wax-Wane Witness",
        "Deathless Knight",
    ],
)
def test_lifegain_makers_excludes_lifegain_matters_trigger_condition(name):
    assert "lifegain_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 119.3) — ADJUDICATED SHEDS. Legacy's OLD
        # IR mis-projects EVERY "target opponent gains N life" / "each
        # OTHER player gains N life" effect's scope as "any" (a genuine
        # scope-derivation bug in the retired project.py pipeline, verified
        # this session via old_ir_for), so legacy's own scope in
        # ("you","any") gate incorrectly admits an OPPONENT-benefit
        # drawback/alt-cost as a lifegain SOURCE. The crosswalk reads
        # phase's ACTUAL structured player field (Typed controller=
        # "Opponent", or an "Another" player property) and correctly
        # excludes all of them — none is a genuine lifegain_makers member.
        "Fiery Justice",
        "Invigorate",
        "Phelddagrif",
        "Soldevi Steam Beast",
        "Armistice",
        "Reverent Silence",
        "Questing Phelddagrif",
        # Flames of the Blood Hand is a lifegain PREVENTION shield ("that
        # player gains no life instead"), never a source at all.
        "Flames of the Blood Hand",
    ],
)
def test_lifegain_makers_excludes_opponent_benefit_gain(name):
    assert "lifegain_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 119.3) — beyond-legacy GAINS legacy misses
        # (its own gain_life scope-derivation gap, same root cause as the
        # opponent-benefit sheds above, but these targets are genuinely
        # "you"/"any"/symmetric-team benefits, not opponent-only):
        # Restorative Technique's "Target player gains 2 life" (an
        # unrestricted targeted gain — could target yourself); Explore the
        # Vastlands's "Each player gains 3 life" (symmetric team gain — you
        # gain too).
        "Restorative Technique",
        "Explore the Vastlands",
    ],
)
def test_lifegain_makers_beyond_legacy_gain(name):
    assert ("lifegain_makers", "you", "") in _idents(name)


def test_reanimator_is_creature_gated():
    # Sheoldred IS a creature returning creatures GY→battlefield.
    assert ("reanimator", "you", "") in _idents("Sheoldred, Whispering One")
    # GY→hand (Raise Dead, a spell) and exile-return (Oblivion Ring) are not.
    assert "reanimator" not in _keys("Raise Dead")
    assert "reanimator" not in _keys("Oblivion Ring")


def test_plus_one_makers_counter_kind_gated():
    assert ("plus_one_makers", "you", "") in _idents("Forgotten Ancient")
    # Throne of Geth proliferates — not a +1/+1 placement.
    assert "plus_one_makers" not in _keys("Throne of Geth")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Fanatic of Mogis", True),  # each opponent — reaches a player
        ("Lightning Bolt", True),  # any target — reaches a player
        ("Pyroclasm", False),  # each creature — removal, not burn
        ("Flame Slash", False),  # target creature — removal
    ],
)
def test_direct_damage_player_reach(name, should_fire):
    assert (("direct_damage", "you", "") in _idents(name)) is should_fire


def test_landfall_fires():
    assert ("landfall", "you", "") in _idents("Lotus Cobra")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Ashnod's Altar", True),  # a you-sac activation COST is the outlet
        ("Mortician Beetle", True),  # a "sacrificed" trigger payoff
        ("Diabolic Edict", False),  # an edict (target player sacrifices)
    ],
)
def test_sacrifice_outlets_edict_split(name, should_fire):
    assert (("sacrifice_outlets", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        "Archangel of Thune",  # life_gained trigger
        "Dark Confidant",  # scaling self-loss (lose-life-equal-to-mana-value)
        "Disciple of Perdition",  # dies + draw + lose_life co-occurrence (gran. a)
    ],
)
def test_lifegain_matters_fires(name):
    assert ("lifegain_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        # ADR-0036/0037 Stage 5 #60: a HIGH-life-total win-condition / static
        # payoff (:func:`has_high_life_total_payoff`) — life as a RESOURCE,
        # not just a one-time gain (CR 104.2 / 119.3).
        ("Felidar Sovereign", True),  # win-the-game upkeep threshold (>= 40)
        ("Test of Endurance", True),  # win-the-game upkeep threshold (>= 50)
        ("Divinity of Pride", True),  # static +4/+4 as long as >= 25 life
        ("Serra Ascendant", True),  # static pump/flying as long as >= 30 life
        ("Blood Baron of Vizkopa", True),  # static pump/flying, opponent gate too
        # A LOW-life ("N or less") gate is the OPPOSITE polarity — a
        # different, near-death signal, not read here.
        ("Convalescence", False),  # upkeep gain-life ONLY if <= 10 life
    ],
)
def test_lifegain_matters_high_life_total_payoff(name, should_fire):
    assert (("lifegain_matters", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Flickerwisp", True),  # exile + sibling return-to-battlefield
        ("Cloudshift", True),  # exile your creature, then return it
        ("Chrome Mox", False),  # exile-imprint, NEVER returns
        ("Path to Exile", False),  # exile removal + a DIFFERENT land's ETB
        ("Man-o'-War", False),  # bounce-to-HAND, not a flicker
    ],
)
def test_blink_flicker_sibling_return(name, should_fire):
    assert (("blink_flicker", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Intangible Virtue", True),  # YOUR token anthem
        ("Anointer Priest", True),  # YOUR-token ETB trigger
        ("Virulent Plague", False),  # symmetric -2/-2 token hoser
    ],
)
def test_tokens_matter_token_predicate(name, should_fire):
    assert (("tokens_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Sol Ring", True),  # nonland, makes 2 — acceleration
        ("Command Tower", True),  # land, any-identity — fixing
        ("Llanowar Elves", True),  # nonland dork — acceleration
        ("Forest", False),  # basic land single-color tap — the mana base
    ],
)
def test_ramp_land_base_vs_accel_fixing(name, should_fire):
    assert (("ramp", "you", "") in _idents(name)) is should_fire


# ADR-0038 W3 batch 4 (lands-and-ramp cluster): the GRANTED mana ability
# descent (mechanism (b) — a GrantAbility.definition precedent). Verified CR:
# 106.1 (mana), 605.1a (mana ability definition), 305 (land base split).
@pytest.mark.parametrize(
    "name",
    [
        "Joiner Adept",  # "Lands you control have '{T}: Add one mana of any
        # color.'" — LAND recipient, FIXING (any color) -> fire
        "Citanul Hierophants",  # "Creatures you control have '{T}: Add {G}.'"
        # — nonland recipient -> fire unconditionally
        "Awakening Zone",  # a CREATED TOKEN's own nested granted mana ability
        # ("It has 'Sacrifice this token: Add {C}.'")
    ],
)
def test_ramp_granted_mana_ability_descent(name):
    assert ("ramp", "you", "") in _idents(name)


# ── Batch-2 over-fire regressions (rules-lawyer adjudicated; ADR-0035) ─────────
# The systemic root: phase's ``{Non: X}`` negation wrapper was flattened to its
# POSITIVE inner type word, so a "nonland permanent" satisfied ``"Land" in subject``
# and a "noncreature" satisfied ``"Creature" in subject``. The fix drops the Non
# wrapper (CR 207.2c / 400.7); these pin the four adjudicated over-fires gone while
# the legitimate positive reads survive.


@pytest.mark.parametrize(
    "name",
    ["Brainstealer Dragon", "Builder's Talent"],  # "a nonland permanent enters"
)
def test_landfall_not_fired_by_nonland_permanent(name):
    """A ``{Non: Land}`` "nonland permanent" enters-trigger must NOT read as
    landfall — the negation is dropped, never flattened to a positive ``Land``."""
    assert "landfall" not in _keys(name)


def test_real_landfall_still_fires_after_non_fix():
    """A genuine "a land enters" trigger (positive ``Land``) is unaffected."""
    assert ("landfall", "you", "") in _idents("Lotus Cobra")


# ── ADR-0038 W3 batch 4 (lands-and-ramp cluster): landfall's enabler tail ──────
# Verified CR: 207.2c (landfall ability word), 305.1/305.2/305.4 (land-play
# rules), 400.7 (zone-change identity), 603.6a (enters-the-battlefield trigger).


@pytest.mark.parametrize(
    "name",
    [
        "Searing Blaze",  # "Landfall — if you had a land enter ... this turn"
        "Crucible of Worlds",  # GraveyardCastPermission mode, affected=Land
        "Exploration",  # MayPlayAdditionalLand static mode
        "Gysahl Greens",  # created token's OWN nested land-ETB GrantTrigger
        "Splendid Reclamation",  # change_zone Graveyard->Battlefield, Land subject
    ],
)
def test_landfall_enabler_tail_structural_arms(name):
    assert ("landfall", "you", "") in _idents(name)


def test_landfall_excludes_colon_bridged_shed():
    """Tameshi, Reality Architect: "Return a land you control to its owner's
    hand: Return target artifact or enchantment card ... from your graveyard
    to the battlefield" — the land BOUNCES to hand as an activation cost; the
    graveyard->battlefield return targets only artifact/enchantment, never
    land (CR 305.1). An adjudicated legacy over-fire (the old regex's
    colon-bridge), not a genuine landfall enabler."""
    assert "landfall" not in _keys("Tameshi, Reality Architect")


def test_reanimator_not_fired_by_noncreature_return():
    """Astelli Reclaimer returns a "noncreature, nonland permanent" card from the
    graveyard — the ``{Non: Creature}`` must not satisfy the is-creature gate."""
    assert "reanimator" not in _keys("Astelli Reclaimer")


@pytest.mark.parametrize(
    "name",
    ["Grave Pact", "Dictate of Erebos"],  # "each opponent sacrifices" — an EDICT
)
def test_sacrifice_outlets_not_fired_by_edict(name):
    """An "each opponent sacrifices a creature" edict (phase mislabels the
    sacrificed subject ``controller: You`` but tags the ability ``player_scope:
    Opponent``) is NOT a you-sac outlet (CR 701.21a)."""
    assert "sacrifice_outlets" not in _keys(name)


def test_sacrifice_outlets_self_sac_preserved():
    """Mycoloth's Devour ("you may sacrifice any number of creatures") still fires
    — it carries no opponents ``player_scope`` to veto it (CR 702.82a)."""
    assert ("sacrifice_outlets", "you", "") in _idents("Mycoloth")


@pytest.mark.parametrize(
    "name",
    [
        "Siege-Gang Commander",  # "{1}{R}, Sacrifice a Goblin:" Composite cost
        "Vampiric Rites",  # "{1}{B}, Sacrifice a creature:" Composite cost
    ],
)
def test_sacrifice_outlets_composite_cost_leaf(name):
    """ADR-0038 W4 giants: a ``Sacrifice`` cost folded into a Composite
    activation cost (mana + sacrifice) decorates as ONE opaque concept at
    the top level — :func:`iter_cost_leaves` walks the Composite/OneOf
    nesting to surface the individual Sacrifice leaf (CR 602.1a — a cost is
    always paid by the activator, so no edict/controller read applies)."""
    assert ("sacrifice_outlets", "you", "") in _idents(name)


def test_sacrifice_outlets_or_filter_controller_recurses():
    """Boilerbilges Ripper's "you may sacrifice another creature OR
    enchantment" is an ``Or`` filter at the target's top level; the
    controller ``You`` tag lives on a SUB-arm, not the ``Or`` wrapper
    itself. ADR-0038 W4 giants bugfix: the controller read now recurses
    ``Or``/``And`` via :func:`~mtg_utils._card_ir.crosswalk.filter_controller`
    (the OLD bare ``tag_of(target) == "Typed"`` gate always returned False
    for a multi-type target, even when a sub-arm named ``You``)."""
    assert ("sacrifice_outlets", "you", "") in _idents("Boilerbilges Ripper")


def test_sacrifice_outlets_cast_additional_cost_text_idiom():
    """ "As an additional cost to cast this spell, sacrifice a creature."
    (Goremand, CR 601.2f) surfaces NO typed Sacrifice node anywhere in
    phase's tree for a Spell ability (probed byte-for-byte: the ability's
    own ``cost`` field is ``None`` — the mana cost lives outside
    ``abilities`` entirely). A last-resort ``tree.oracle`` text idiom is
    the ONLY available source (ADR-0038 W4 giants)."""
    assert ("sacrifice_outlets", "you", "") in _idents("Goremand")


@pytest.mark.parametrize(
    "name",
    [
        "Light 'Em Up",  # Casualty 2 (CR 702.153a)
        "High Fae Negotiator",  # Bargain (CR 702.166a)
    ],
)
def test_sacrifice_outlets_casualty_bargain_keyword(name):
    """Casualty / Bargain are BOTH "As an additional cost to cast this
    spell, you may sacrifice a <creature/artifact/enchantment/token>" (CR
    702.153a / 702.166a) — phase's typed tree carries no node for either
    keyword's cost at all, so the Scryfall keyword array is the only
    structured source (:data:`_SWEEP_KEYWORD_LANES` row, ADR-0038 W4
    giants)."""
    assert ("sacrifice_outlets", "you", "") in _idents(name)


def test_sacrifice_outlets_mandatory_shed_last_voyage():
    """MANDATORY SHED (recorded session adjudication, ADR-0038 W4 giants):
    "When this Aura leaves the battlefield, sacrifice enchanted creature."
    — Last Voyage of the _____'s sacrificed subject carries an
    ``EnchantedBy`` predicate and NO ``controller`` tag; it is a forced
    Aura-death consequence (CR 303.4b), not a discretionary outlet, and
    must never fire ``sacrifice_outlets``."""
    assert "sacrifice_outlets" not in _keys("Last Voyage of the _____")


@pytest.mark.parametrize(
    "name",
    [
        "Sheoldred's Edict",  # modal "Each opponent sacrifices a ..." charm
        "Tomb Blade",  # "unless THAT PLAYER sacrifices" damage-avoidance
    ],
)
def test_sacrifice_outlets_shed_opponent_directed(name):
    """A modal "each opponent sacrifices" charm (Sheoldred's Edict) and an
    "unless that player sacrifices" damage-avoidance clause (Tomb Blade,
    the alt-cost payer is the effect's TARGET, not this ability's
    controller) are OPPONENT-directed, not you-sac outlets — the legacy
    flat-parsed IR mis-scopes both to "any" and over-fires; this session
    adjudicated the class a SHED (CR 701.21a)."""
    assert "sacrifice_outlets" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Tectonic Split",  # "sacrifice half the lands you control" (cast cost)
        "Infernal Denizen",  # "sacrifice two Swamps" (Composite cost leaf)
    ],
)
def test_sacrifice_outlets_land_only_excluded(name):
    """A land-only sacrifice subject — whether the bare core type ``Land``
    or an ALL-:data:`~mtg_utils._deck_forge.crosswalk_signals._LAND_SUBTYPES`
    subtype list (Swamp, Mountain, ...) — stays ``land_sacrifice_makers``
    territory (CR 701.21), never ``sacrifice_outlets``, across BOTH the
    additional-cost-to-cast text idiom and the Composite cost-leaf arm
    (ADR-0038 W4 giants)."""
    assert "sacrifice_outlets" not in _keys(name)


def test_sacrifice_outlets_land_subtype_effect_arm_excluded():
    """ADR-0038 W5 tails bugfix: a land-SUBTYPE-only ``Sacrifice`` EFFECT
    ("sacrifice a Swamp" — Akuta, Born of Ash's upkeep trigger) previously
    slipped past the effect arm's exclusion, which only tested the bare
    core-type tuple ``("Land",)`` and never the CR 205.3i subtype
    vocabulary (:data:`~mtg_utils._deck_forge.crosswalk_signals._LAND_SUBTYPES`)
    the cost-leaf arm already read. Both arms now share ONE subject-presence
    read (:func:`~mtg_utils._deck_forge.crosswalk_signals._sac_subject_present`),
    so a Swamp-only sacrifice stays ``land_sacrifice_makers`` territory here
    too (CR 701.21a — a player may only sacrifice a permanent they control;
    the LAND-subtype scoping is a lane boundary, not a rules distinction)."""
    assert "sacrifice_outlets" not in _keys("Akuta, Born of Ash")


@pytest.mark.parametrize(
    "name",
    [
        "Hardened Tactician",  # "{1}, Sacrifice a token: Draw a card."
        "Rat King, Pale Piper",  # "{2}, Sacrifice a token: Draw a card."
    ],
)
def test_sacrifice_outlets_token_predicate_cost_leaf(name):
    """ADR-0038 W5 tails: a ``Token`` PREDICATE-only sacrifice subject
    ("sacrifice a token") carries NO core type or subtype word —
    :func:`~mtg_utils._card_ir.crosswalk.filter_core_types` /
    :func:`~mtg_utils._card_ir.crosswalk.filter_subtypes` only read a
    filter's ``type_filters``, never its ``properties`` predicate list
    where phase tags ``Token`` — so it previously fell through the ``not
    core and not sub`` empty-subject gate in the Composite cost-leaf walk.
    A token IS a permanent (CR 111.1) and a cost is always paid by the
    activator (CR 602.1a), so this is unambiguously a you-sac outlet."""
    assert ("sacrifice_outlets", "you", "") in _idents(name)


def test_sacrifice_outlets_token_predicate_effect_arm():
    """ADR-0038 W5 tails: the SAME ``Token``-predicate gap
    (:func:`test_sacrifice_outlets_token_predicate_cost_leaf`) also hit the
    EFFECT arm — Chitterspitter's "you may sacrifice a token" trigger
    carries an explicit ``controller: You`` on a Token-predicate-only
    filter; :func:`~mtg_utils._deck_forge.crosswalk_signals._is_you_sac_subject`
    now reads the shared :func:`~mtg_utils._deck_forge.crosswalk_signals._sac_subject_present`
    helper instead of the pre-flattened ``c.subject`` tuple, so this fires
    too (CR 111.1, CR 701.21a)."""
    assert ("sacrifice_outlets", "you", "") in _idents("Chitterspitter")


@pytest.mark.parametrize(
    "name",
    [
        "Lord of the Pit",  # "sacrifice a creature other than ~" — bare imperative
        "Disciple of Bolas",  # "sacrifice another creature" — ETB effect
    ],
)
def test_sacrifice_outlets_unset_controller_defaults_to_you(name):
    """ADR-0038 W6 endgame — the DOMINANT residual class: a Sacrifice EFFECT
    whose target carries NO ``controller`` tag at all now defaults to you
    (CR 109.5 — "you"/"your" means an object's controller; Magic's
    templating omits an explicit "you" subject on a bare imperative
    addressed to the ability's own controller)."""
    assert ("sacrifice_outlets", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Witch-king, Bringer of Ruin",  # "defending player sacrifices ..."
        "Labyrinth Raptor",  # "defending player sacrifices ..."
    ],
)
def test_sacrifice_outlets_unset_controller_other_actor_excluded(name):
    """ADR-0038 W6 endgame: phase leaves the ``controller`` tag EQUALLY
    unset for "defending player sacrifices a creature" as it does for a
    genuine bare-imperative self-sac (see
    :func:`test_sacrifice_outlets_unset_controller_defaults_to_you`) — a
    naive unset-to-you default over-fires here. The clause-head
    disambiguator (:func:`~mtg_utils._deck_forge.crosswalk_signals.
    _sac_effect_names_other_actor`) reads the owning ability's OWN
    templated text and heads the sacrifice clause with "defending player,"
    a non-controller actor (CR 701.21a — a player may only sacrifice a
    permanent THEY control)."""
    assert "sacrifice_outlets" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Nicol Bolas, Planeswalker",  # "-9: ... discards ..., then sacrifices ..."
        "Undercity Plague",  # "Target player loses..., discards..., sacrifices..."
    ],
)
def test_sacrifice_outlets_unset_controller_compound_predicate_excluded(name):
    """ADR-0038 W6 endgame: a compound predicate shares ONE subject across
    several comma-joined verbs — "That player or that planeswalker's
    controller discards seven cards, then sacrifices seven permanents"
    (Nicol Bolas) and "Target player loses 1 life, discards a card, then
    sacrifices a permanent" (Undercity Plague) both put real distance
    between the actor and "sacrifices". A first-attempt proximity-window
    probe missed both and over-fired; the clause-head test
    (:func:`~mtg_utils._deck_forge.crosswalk_signals._sac_effect_names_
    other_actor`) correctly heads the WHOLE sentence, not just the words
    immediately before "sacrifices" (CR 701.21a)."""
    assert "sacrifice_outlets" not in _keys(name)


def test_sacrifice_outlets_granted_activated_cost():
    """ADR-0038 W6 endgame: Lunarch Mantle's Aura grants an enchanted
    creature "Sacrifice a permanent: This creature gains flying" — a
    GRANTED activated ability whose OWN cost carries a non-land Sacrifice
    leaf. A COST is always paid by the ACTIVATOR (CR 602.1a); for a granted
    ability that's whoever controls the recipient permanent, which deck-
    signal purposes treat as "you" (a beneficial Aura is overwhelmingly
    attached to your own creature)."""
    assert ("sacrifice_outlets", "you", "") in _idents("Lunarch Mantle")


def test_sacrifice_outlets_ward_cost_excluded():
    """ADR-0038 W6 endgame: Mishra, Tamer of Mak Fawa's granted "Ward—
    Sacrifice a permanent" is a Ward cost — phase's ``tag_of`` collapses
    ``T_Ward__Sacrifice`` to the SAME ``"Sacrifice"`` string as a regular
    cost leaf, but a Ward cost is paid by the OPPONENT who targeted the
    warded permanent (CR 702.21a: "counter that spell or ability unless
    THAT PLAYER pays [cost]"), never the ability's own controller — the
    granted-cost descent excludes it by CLASS NAME, not tag."""
    assert "sacrifice_outlets" not in _keys("Mishra, Tamer of Mak Fawa")


def test_death_matters_not_fired_by_noncreature_arrival():
    """Scrapheap watches an artifact/enchantment put into the graveyard from the
    battlefield — only CREATURES "die" (CR 700.4), so it must not fire."""
    assert "death_matters" not in _keys("Scrapheap")


@pytest.mark.parametrize(
    "name",
    ["Kithkin Mourncaller", "Rakish Crew"],  # creature-subtype dies payoffs
)
def test_death_matters_creature_subtype_preserved(name):
    """A dies-trigger watching creature subtypes — Kithkin/Elf, and an ``AnyOf`` of
    Assassin/Mercenary/Pirate/Rogue/Warlock — is a real creature-death payoff that
    must survive the CR-700.4 creature gate."""
    assert "death_matters" in _keys(name)


def test_filter_type_words_drops_non_negation():
    """``{Non: Land}`` is DROPPED (not flattened to ``Land``) — the systemic root of
    the landfall / reanimator over-fires (CR 207.2c / 400.7)."""
    from mtg_utils._card_ir.crosswalk import trigger_subject

    bsd = _tree("Brainstealer Dragon")
    enters = next(u for u in bsd.units if u.trigger_event == "enters")
    subj = trigger_subject(enters.node)
    assert "Land" not in subj  # the "nonland" arm must not surface Land
    assert "Permanent" in subj  # the positive "Permanent" word survives


def test_filter_type_words_recurses_anyof():
    """An ``{AnyOf: [{Subtype: Assassin}, …]}`` disjunction surfaces its inner
    subtypes (parallel to the Or/And recursion) — Rakish Crew's creature set."""
    from mtg_utils._card_ir.crosswalk import trigger_subject

    rc = _tree("Rakish Crew")
    dies = next(u for u in rc.units if u.trigger_event == "dies")
    subj = trigger_subject(dies.node)
    assert "Assassin" in subj
    assert "Mercenary" in subj


# ── Batch 3 (ADR-0035 Stage 2): big over-fire lanes + doer cluster ────────────


def test_batch3_framework_filter_helpers():
    """The new typed filter reads: core-vs-subtype split, controller, count operand."""
    from mtg_utils._card_ir.crosswalk import (
        count_operand_filter,
        effect_filter,
        filter_controller,
        filter_core_types,
        filter_subtypes,
    )

    # Stoneforge's tutor filter names the Equipment SUBTYPE, not a core type.
    sm = _tree("Stoneforge Mystic")
    tut = next(c for c in sm.effect_concepts("tutor"))
    f = effect_filter(tut.node)
    assert "Equipment" in filter_subtypes(f)
    assert "Equipment" not in filter_core_types(f)
    # Padeem's anthem affected filter is a generic own-board Artifact set.
    pad = _tree("Padeem, Consul of Innovation")
    static = next(u for u in pad.units if u.origin == "static")
    aff = static.node.affected
    assert "Artifact" in filter_core_types(aff)
    assert not filter_subtypes(aff)
    assert filter_controller(aff) == "You"
    # Inspiring Call's draw counts creatures-you-control with a +1/+1 counter.
    ic = _tree("Inspiring Call")
    draw = next(c for c in ic.effect_concepts("draw"))
    cf = count_operand_filter(draw.node)
    assert cf is not None
    assert filter_controller(cf) == "You"


def test_counter_pred_kinds_reads_typed_counters_predicate():
    """``counter_pred_kinds`` surfaces the P1P1 kind off a typed Counters predicate."""
    from mtg_utils._card_ir.crosswalk import (
        count_operand_filter,
        counter_pred_kinds,
    )

    ic = _tree("Inspiring Call")
    draw = next(c for c in ic.effect_concepts("draw"))
    assert "P1P1" in counter_pred_kinds(count_operand_filter(draw.node))


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Glorious Anthem", True),  # generic creatures-you-control anthem
        ("Inspiring Call", True),  # count operand over your creatures
        ("Goblin King", False),  # SUBTYPE anthem — type_matters, not this
    ],
)
def test_creatures_matter_generic_gate(name, should_fire):
    assert (("creatures_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        # ADR-0038 W4 giant-key batch: team-anthem arm widened from
        # static-origin-only ``unit.statics`` to a whole-unit
        # ``iter_static_defs`` descent, so a ONE-SHOT GenericEffect-nested
        # (Overrun) or CreateEmblem-nested (Capitoline Triad) static def
        # fires the SAME arm as a permanent static-origin anthem — CR
        # 611.2c (the resolving effect's affected set is fixed when it
        # begins), 613.4c layer 7c.
        ("Overrun", True),  # GenericEffect-nested AddPower/AddToughness
        ("The Capitoline Triad", True),  # CreateEmblem-nested SetPower/SetToughness
        # A scaling continuous anthem (AddDynamicPower/AddDynamicToughness,
        # not the fixed Add* pair) rides the same static-def arm — CR 107.3.
        ("Call for Unity", True),
        # GrantAbility/GrantTrigger — granting a whole new ability is the
        # same team-payoff shape as granting a bare keyword (CR 113.10).
        ("Lightning Volley", True),
        # A plain top-level PumpAll role=effect (no nested static def at
        # all — the whole effect IS the modification) over the generic
        # filter — CR 611.2c/613.4c.
        ("Warrior's Honor", True),
        ("Fortify", True),
        # A scaling Pump/PumpAll whose magnitude rides ``power``/
        # ``toughness`` (not ``amount``/``count``/``value``) — CR 107.3.
        ("Might of the Masses", True),
        # A Multiply-scaled count operand (2x life for each creature) —
        # CR 107.3.
        ("Peach Garden Oath", True),
        # A Mana effect's count nested one level deeper on ``produced`` —
        # CR 107.3.
        ("Circle of Dreams Druid", True),
        # SHEDS — corpus-adjudicated, deliberately NOT ported this batch:
        # the LOW regex floor (any creature-token maker) is a bare mention
        # count, not a structural cares-about read (Siege-Gang Commander).
        ("Siege-Gang Commander", False),
        # A SUBTYPE-restricted anthem (Dragon-only) fails the no-subtype
        # gate — type_matters territory, not this lane (CR 604.1 scopes a
        # static ability's own wording; "Other Dragon creatures" names a
        # subtype, not the generic population).
        ("Karrthus, Tyrant of Jund", False),
        # A SYMMETRIC "on the battlefield" count (any controller) fails the
        # "You" controller gate — a genuinely broader population than
        # "creatures you control" (ADR-0038 boundary lesson (ii)).
        ("Blasphemous Act", False),
        # A "creatures BLOCKING it" count (Rampage) — a different subject
        # entirely, not "creatures you control".
        ("Craw Giant", False),
    ],
)
def test_creatures_matter_w4_giant_batch(name, should_fire):
    assert (("creatures_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        # ADR-0038 W5 tails: mass untap ("untap all creatures you control")
        # is a board-wide pseudo-vigilance payoff, the same team-payoff
        # shape as an anthem — CR 701.26/701.26b.
        ("Vitalize", True),  # top-level ability, no trigger wrapper
        ("Aurelia, the Warleader", True),  # attack-trigger-nested
        # "untap ALL OTHER creatures you control" — the ``Another`` filter
        # property lives outside type_filters/subtypes, so it doesn't
        # perturb the generic-filter gate.
        ("Combat Celebrant", True),
        # A SINGLE-target untap-as-cost ("untap A tapped creature you
        # control") is scope='Single', not 'All' — never reaches the mass
        # gate, stays a utility cost, not a go-wide payoff.
        ("Halo Fountain", False),
        # The DYNAMIC base-P/T-set pair (SetPowerDynamic/SetToughnessDynamic
        # — "creatures you control have base power and toughness X/X") rides
        # the SAME team-anthem arm as the fixed Set*/Add* pairs — CR 613.4b.
        ("Biomass Mutation", True),
        ("Mirror Entity", True),
    ],
)
def test_creatures_matter_w5_tails_batch(name, should_fire):
    assert (("creatures_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        # ADR-0038 W6 endgame: an ``Aggregate`` (Max Power) count operand —
        # "X is the greatest power among creatures you control" — reads the
        # exact GENERIC population a summed count operand does, via a
        # max/min reduction instead of a sum (CR 107.3 computed value; CR
        # 208.1 power characteristic).
        ("Monstrous Onslaught", True),  # DealDamage amount
        ("Rishkar's Expertise", True),  # Draw count
        ("Essence Harvest", True),  # GainLife/LoseLife amount
        ("Peema Aether-Seer", True),  # GainEnergy amount
        # A self-referential base-power CDA ("~'s power is equal to the
        # greatest mana value among creatures you control" — a
        # SetDynamicPower STATIC modification, role=="static") reads the
        # SAME generic-filter Aggregate shape but computes the permanent's
        # OWN characteristic (CR 613.4b), not a payoff distributed to the
        # team — the role=="effect" gate excludes it, mirroring the
        # team-anthem arm's own self-referential-CDA exclusion.
        ("Towering Gibbon", False),
        # SHEDS — corpus-adjudicated, deliberately NOT ported (the same LOW
        # regex floor / different-subject classes W4/W5 already
        # established, re-pinned here with fresh representatives):
        # a "creatures ATTACKING you" count (Blessed Reversal) is a
        # different subject, not "creatures you control" — same boundary as
        # Craw Giant's blocking count.
        ("Blessed Reversal", False),
        # Devour's sacrifice count (CR 702.82a/614.1c: "you may sacrifice
        # any number of creatures" feeding an ETB counter placement) is
        # grouped with the LOW regex floor, not a structural "creatures you
        # control" cares-about read — the sacrificed creatures are a
        # DIFFERENT (self-consuming) population, not the board.
        ("Bloodspore Thrinax", False),
    ],
)
def test_creatures_matter_w6_endgame_batch(name, should_fire):
    assert (("creatures_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "ident", "should_fire"),
    [
        ("Padeem, Consul of Innovation", ("artifacts_matter", "you", ""), True),
        ("Enlightened Tutor", ("artifacts_matter", "you", ""), True),  # composite
        ("Enlightened Tutor", ("enchantments_matter", "you", ""), True),
        ("Dockside Extortionist", ("artifacts_matter", "you", ""), True),  # Treasure
        ("Bartered Cow", ("artifacts_matter", "you", ""), True),  # Food token
        # Edict over-fire: "each opponent sacrifices an artifact or enchantment" is a
        # you-controlled-subject phase mislabel — must NOT open either type lane.
        ("Tribute to the Wild", ("artifacts_matter", "you", ""), False),
        ("Tribute to the Wild", ("enchantments_matter", "you", ""), False),
    ],
)
def test_artifacts_enchantments_matter(name, ident, should_fire):
    assert (ident in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Foul-Tongue Shriek", True),  # count of attacking creatures you control
        ("Aetherize", False),  # "all attacking creatures" (controller any) — removal
    ],
)
def test_attack_matters_controller_gate(name, should_fire):
    assert (("attack_matters", "you", "") in _idents(name)) is should_fire


def test_tapped_matters_fires():
    assert ("tapped_matters", "you", "") in _idents("Toil to Renown")


# ── recall-completion b1: genuine payoff arms (ADR-0034 role-aware) ────────────


def test_attack_matters_attacks_trigger():
    """recall-completion b1: an ``attacks`` trigger-event is an attack_matters
    payoff — Accorder Paladin's battle-cry trigger, Isshin's attack-doubling. The
    SIBLING doer/type lanes stay byte-unmoved (no re-conflation)."""
    assert ("attack_matters", "you", "") in _idents("Accorder Paladin")
    assert ("attack_matters", "you", "") in _idents("Isshin, Two Heavens as One")
    # sibling lanes on Accorder Paladin are unchanged (combat-buff doer + type)
    assert {"combat_buff_engine", "type_matters"} <= _keys("Accorder Paladin")


def test_spellcast_matters_trigger_and_prowess():
    """recall-completion b1: a you-cast ``cast_spell`` trigger over a typed
    noncreature subject (Talrand, Young Pyromancer) and the Prowess keyword (Abbot
    of Keral Keep) fire spellcast_matters; the token/type sibling lanes are
    unchanged."""
    assert ("spellcast_matters", "you", "") in _idents("Talrand, Sky Summoner")
    assert ("spellcast_matters", "you", "") in _idents("Young Pyromancer")
    assert ("spellcast_matters", "you", "") in _idents("Abbot of Keral Keep")
    # Talrand's token/type doer lanes stay byte-unmoved
    assert ("token_maker", "you", "Drake") in _idents("Talrand, Sky Summoner")


def test_plus_one_matters_counters_scaler():
    """recall-completion b1: a ``CountersOn`` P1P1 count-operand ("for each +1/+1
    counter on ~" — Mycoloth) fires plus_one_matters; its plus_one_makers /
    token_maker doer siblings stay byte-unmoved."""
    assert ("plus_one_matters", "you", "") in _idents("Mycoloth")
    assert {"plus_one_makers", "token_maker"} <= _keys("Mycoloth")


def test_tokens_matter_created_trigger_and_count():
    """recall-completion b1: a ``TokenCreated`` trigger (Akim) and a Token-predicate
    count-operand (Audience with Trostani) fire tokens_matter."""
    assert ("tokens_matter", "you", "") in _idents("Akim, the Soaring Wind")
    assert ("tokens_matter", "you", "") in _idents("Audience with Trostani")


def test_ltb_matters_self_leaves_trigger():
    """recall-completion b1: a SelfRef self-LTB value trigger (Skyclave Apparition
    — "when this leaves the battlefield, create a token") fires ltb_matters — no
    separate self_ltb lane, so no re-conflation."""
    assert ("ltb_matters", "you", "") in _idents("Skyclave Apparition")


def test_power_matters_ferocious_condition():
    """recall-completion b1: a Ferocious power-threshold CONDITION ("as long as you
    control a creature with power 4 or greater" — Beastbond Outcaster) fires
    power_matters via the condition-site read; low_power_matters must NOT (GE/GT
    only)."""
    assert ("power_matters", "you", "") in _idents("Beastbond Outcaster")
    assert "low_power_matters" not in _keys("Beastbond Outcaster")


def test_tapped_matters_static_anthem():
    """recall-completion b1: a static anthem over your tapped creatures ("other
    tapped creatures you control have indestructible" — Adept Watershaper) fires
    tapped_matters (the effect-only arm skipped statics)."""
    assert ("tapped_matters", "you", "") in _idents("Adept Watershaper")


def test_death_matters_morbid_condition():
    """recall-completion b1: the morbid "if a creature died this turn" family (Bone
    Picker) fires death_matters scope "any" via the byte-identical kept mirror."""
    assert ("death_matters", "any", "") in _idents("Bone Picker")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Karn's Bastion", True),  # proliferate
        ("Aether Snap", True),  # kindless "remove all counters"
        ("Bioshift", True),  # counter MOVE
        ("Tangle Wire", False),  # fade-counter remove (kind set) — excluded
    ],
)
def test_any_counter_makers_kind_gate(name, should_fire):
    assert (("any_counter_makers", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Hapatra, Vizier of Poisons", True),  # M1M1 placement
        ("Cathars' Crusade", False),  # P1P1 placement — the +1/+1 lane, not this
    ],
)
def test_minus_counters_matter_kind_gate(name, should_fire):
    assert (("minus_counters_matter", "you", "") in _idents(name)) is should_fire


def test_minus_counters_matter_cost_embedded_placement():
    """ADR-0038 W3 batch 4: Devoted Druid's "Put a -1/-1 counter on this
    creature: Untap this creature" places the ``PutCounter`` inside the
    ability's OWN ``EffectCost``, invisible to ``effect_concepts`` (which
    reads only the payoff chain) — a full node walk over the unit still
    finds it. CR 601.2b (effect costs) / 122.1."""
    assert ("minus_counters_matter", "you", "") in _idents("Devoted Druid")


def test_minus_counters_matter_persist_enter_with_counters():
    """ADR-0038 W3 batch 4: Kitchen Finks' Persist ("return it to the
    battlefield ... with a -1/-1 counter on it") carries the M1M1 entry on
    the re-entry ``ChangeZone``'s ``enter_with_counters`` field in v0.20.0's
    mirror — a substrate SHAPE change from the legacy adapter's discrete
    ``PutCounter`` Effect, not a lane gap. Persist's OWN reminder text is
    entirely parenthetical, so only this structural read reaches it (the
    kept-mirror text fallback can't — reminder-stripped). CR 122.6/702.79a."""
    assert ("minus_counters_matter", "you", "") in _idents("Kitchen Finks")


def test_minus_counters_matter_kept_mirror_replacement_dampener():
    """ADR-0038 W3 batch 4: Vizier of Remedies' "-1/-1 counters minus one
    are put on it instead" is a counter-quantity REPLACEMENT (CR 614), not a
    ``PutCounter`` placement itself — recovered by the legacy's own
    "-1/-1 counter" kept-mirror text fallback (the CARES-ABOUT residue,
    matching the ``_signals_ir`` two-arm identity). CR 122.1/614."""
    assert ("minus_counters_matter", "you", "") in _idents("Vizier of Remedies")


@pytest.mark.parametrize("name", ["Inspiring Call", "Bioshift"])
def test_plus_one_matters_structural_arms(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W4 giant batch (CR 122.1) — a mass STATIC grant whose OWN
        # ``affected`` names a P1P1-bearing filter directly (Outlast's tribal
        # anthem idiom, mirrors ``_any_counter_matters``'s Rishkar arm gated
        # to P1P1 instead of Any).
        "Abzan Falconer",
    ],
)
def test_plus_one_matters_static_affected_arm(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_plus_one_matters_trigger_valid_card_arm():
    """Marchesa, the Black Rose (CR 122.1 / 603.2): "whenever a creature you
    control with a +1/+1 counter on it dies" rides the DIES trigger's own
    ``valid_card`` filter — mirrors ``_any_counter_matters``'s counter-HAVE
    trigger arm, gated to P1P1 instead of Any."""
    assert ("plus_one_matters", "you", "") in _idents("Marchesa, the Black Rose")


def test_plus_one_matters_has_counters_condition_arm():
    """Lightwalker (CR 604.2): "~ has flying as long as it has a +1/+1
    counter on it" is a whole-unit static CONDITION (``HasCounters``) riding
    ``SelfRef`` — no subject/count-operand filter exists for the other arms
    to read."""
    assert ("plus_one_matters", "you", "") in _idents("Lightwalker")


@pytest.mark.parametrize("name", ["Triskelion", "Walking Ballista"])
def test_plus_one_matters_removecounter_cost_arm(name):
    """Triskelion / Walking Ballista (CR 118.7): "Remove a +1/+1 counter
    from ~: …" is a P1P1-kind ``RemoveCounter`` activation COST — a +1/+1
    counter sink/outlet, mirrors ``_counter_manipulation``'s
    ``iter_cost_leaves`` walk."""
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_plus_one_matters_mirrorvariant_counter_filter_arm():
    """Fathom Mage (CR 122.1 / 603.2): "Whenever a +1/+1 counter is put on
    ~, you may draw a card" is a THRESHOLD-less ``counter_added`` trigger —
    no Saga chapter number, so the mirror runtime loads its ``counter_filter``
    as an untagged single-field ``MirrorVariant`` rather than the full
    struct. :func:`trigger_counter_filter` (``_card_ir/crosswalk.py``) reads
    both encodings."""
    assert ("plus_one_matters", "you", "") in _idents("Fathom Mage")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W4 giant batch — NOT ported: a ``counter_added`` trigger
        # whose kind is anything OTHER than P1P1. Legacy's OWN
        # ``_PAYOFF_TRIGGER_KEYS["counter_added"]`` row fires plus_one_matters
        # UNCONDITIONALLY on every ``counter_added`` trigger with NO kind
        # gate — a Saga's lore-counter chapter has nothing to do with +1/+1
        # counters (CR 714.2b vs 122.1); Nest of Scarabs / Hapatra fire off a
        # -1/-1-counter trigger (CR 122.1 kind carries the distinction).
        # Deliberately negative-pinned.
        "The War in Heaven",
        "Nest of Scarabs",
        "Hapatra, Vizier of Poisons",
    ],
)
def test_plus_one_matters_excludes_non_p1p1_counter_added_trigger(name):
    assert "plus_one_matters" not in _keys(name)


def test_plus_one_matters_excludes_kind_agnostic_have_reference():
    """The Swarmlord (CR 122.1): "whenever a creature you control with a
    counter on it dies" carries an explicit ``Any``-kind Counters predicate
    on its DIES trigger's ``valid_card`` (the SAME structural node
    ``any_counter_matters`` correctly reads via
    ``test_any_counter_matters_trigger_valid_card_arm``) — legacy's
    per-ability ``project._narrow_counter_refs`` regex (``_P1P1_HAVE_REF``)
    carries a kind-agnostic "with/has a counter on it" alternative despite
    its "+1/+1-counter ref recovery" framing, double-tagging plus_one_matters
    even though the referenced kind is explicitly Any. Deliberately
    negative-pinned — a kind-agnostic reference belongs to
    any_counter_matters, not here."""
    assert "plus_one_matters" not in _keys("The Swarmlord")
    assert ("any_counter_matters", "you", "") in _idents("The Swarmlord")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W5 tails (CR 603.4, intervening "if"): a TRIGGER's own
        # ``HasCounters(P1P1)`` condition — the static-only HasCounters arm
        # (test_plus_one_matters_has_counters_condition_arm, Lightwalker)
        # widened to read off ANY unit origin via the shared
        # ``iter_condition_sites``/``_condition_leaves`` descent, so a
        # trigger's own upkeep-condition self-reference reaches it too.
        "Sarulf, Realm Eater",
        "Ingenious Prodigy",
    ],
)
def test_plus_one_matters_trigger_own_has_counters_condition_arm(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_plus_one_matters_static_is_present_condition_arm():
    """Prehistoric Turtlesaurus (CR 604.2 / 601.2f): "This spell costs {1}
    less to cast if you control a creature with a +1/+1 counter on it" rides
    an ``IsPresent`` static CONDITION (not ``HasCounters``) — the SAME
    condition-site descent, widened to also read the ``IsPresent`` tag."""
    assert ("plus_one_matters", "you", "") in _idents("Prehistoric Turtlesaurus")


def test_plus_one_matters_static_cant_attack_has_counters_condition():
    """Slumbering Dragon (CR 604.2): "This creature can't attack or block
    unless it has five or more +1/+1 counters on it" is a static CantAttack
    restriction gated by a ``HasCounters(P1P1)`` condition — a genuine
    beyond-legacy gain (a live corpus re-measure shows crosswalk-only, not
    reproduced by legacy's regex)."""
    assert ("plus_one_matters", "you", "") in _idents("Slumbering Dragon")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W5 tails — a gap-marker TEXT fallback narrowly scoped to
        # the SAME unit's own description/text field (never the whole-card
        # raw): Pipsqueak's condition decorates as ``Not(Unrecognized(text=
        # …))`` (a raw parse residue, CR 122.1's kind carried only in the
        # text); Skarrgan Hellkite's "Activate only if ~ has a +1/+1 counter
        # on it" decorates as an EMPTY ``RequiresCondition`` (CR 602.5, no
        # captured payload). A full commander-legal corpus census found
        # exactly these 2 cards (3 printings) matching the marker+text gate.
        "Pipsqueak, Rebel Strongarm",
        "Skarrgan Hellkite",
    ],
)
def test_plus_one_matters_gap_marker_text_fallback(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_plus_one_matters_counter_added_this_turn_qty_arm():
    """Iridescent Hornbeetle (CR 122.1): "create a token for each +1/+1
    counter you've put on creatures under your control this turn" is a
    ``CounterAddedThisTurn`` qty node — a THIS-TURN placement tally, a
    sibling of the ``CountersOn`` live-board-state count the existing arm
    reads, but with the kind riding a nested ``counters.data`` field
    instead of a bare ``counter_type`` string."""
    assert ("plus_one_matters", "you", "") in _idents("Iridescent Hornbeetle")


def test_plus_one_matters_excludes_maker_only_conflation():
    """Scholar of New Horizons (CR 122.1): "This creature enters with a
    +1/+1 counter on it" is a pure P1P1 PLACEMENT — no cares-about text of
    its own (its OTHER ability's "Remove a counter from a permanent you
    control" cost is kind-agnostic Any, not P1P1-specific). Legacy's
    conflated plus_one_matters fires on ANY p1p1 placement; the crosswalk
    correctly splits maker from matters (mirrors the ADR-0038 W4
    any_counter_matters/any_counter_makers split) — deliberately
    negative-pinned. ``plus_one_makers`` fires instead."""
    assert "plus_one_matters" not in _keys("Scholar of New Horizons")
    assert ("plus_one_makers", "you", "") in _idents("Scholar of New Horizons")


def test_plus_one_matters_modify_cost_spell_filter_targets_arm():
    """Titanic Brawl (CR 601.2f): "This spell costs {1} less to cast if it
    TARGETS a creature you control with a +1/+1 counter on it" nests the
    P1P1 predicate inside a ``ModifyCost`` static's ``spell_filter`` OWN
    ``Targets`` property — distinct from Prehistoric Turtlesaurus's
    top-level ``IsPresent`` condition (that card cares about a creature you
    control anywhere; this one cares specifically about the spell's own
    target)."""
    assert ("plus_one_matters", "you", "") in _idents("Titanic Brawl")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — a P1P1 self-count THRESHOLD condition rides
        # ``QuantityCheck`` (CR 122.1), a DIFFERENT node shape from the
        # HasCounters/IsPresent condition leaves the W5 tails arm already
        # reads: ``lhs`` is a ``Ref`` wrapping a ``CountersOn`` qty (the SAME
        # qty tag the pump-scaling arm reads off an effect's count operand,
        # here riding a condition's comparison operand instead). Incubation
        # Druid's activated-ability sub_ability condition ("If this creature
        # has a +1/+1 counter on it, add three mana instead") hits the
        # ``ConditionInstead``-WRAPPED shape (CR 601.2f "instead" variant —
        # unwrapped locally, not via the shared ``_condition_leaves`` helper,
        # since the corpus's 101 ConditionInstead-wrapping-QuantityCheck
        # instances span many unrelated conditions); Dual-Sun Technique and
        # Oblivion's Hunger hit the BARE (unwrapped) ``QuantityCheck`` shape.
        # Non-P1P1 kinds (depletion/lore/quest/soul/time/landmark/omen/point
        # — a full corpus scan) correctly gate out via the ``counter_type``
        # check.
        "Incubation Druid",
        "Dual-Sun Technique",
        "Oblivion's Hunger",
    ],
)
def test_plus_one_matters_quantity_check_condition_arm(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_plus_one_matters_target_has_keyword_instead_text_fallback():
    """Bring Low (CR 601.2f / 122.1): "~ deals 3 damage to target creature.
    If that creature has a +1/+1 counter on it, ~ deals 5 damage to it
    instead" decorates the condition as ``TargetHasKeywordInstead`` whose
    ``keyword`` field is an ``Unknown``-tagged raw-text residue ("a +1/+1
    counter on it") rather than a real keyword — a gap-marker text fallback
    narrowly scoped to the ``Unknown`` variant (a NAMED keyword — Flying,
    Infect, Toxic — never reaches this branch; the corpus's 14
    TargetHasKeywordInstead instances split 3 P1P1-text / 3 named-keyword /
    8 unrelated power-toughness-comparison text, so the ``_P1P1_COND_TEXT_RX``
    gate is load-bearing, not redundant)."""
    assert ("plus_one_matters", "you", "") in _idents("Bring Low")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — NOT ported: the CDA "power greater than its
        # base power" text idiom legacy's ``_P1P1_HAVE_REF`` regex treats as
        # a +1/+1-counter proxy. CR 208.4b: "power greater than base power"
        # is a comparison against the LAYER-applied current value, true for
        # ANY power-increasing effect (a temporary pump spell, a static
        # anthem, Evolve) — a +1/+1 counter is only ONE of several possible
        # causes, so the state itself carries no counter KIND (CR 122.1) and
        # is not a genuine counter reference at all. Deliberately
        # negative-pinned across all three corpus members.
        "Baird, Argivian Recruiter",
        "Kutzil, Malamet Exemplar",
        "Ms. Marvel, Elastic Ally",
    ],
)
def test_plus_one_matters_excludes_power_greater_than_base_power_cda(name):
    assert "plus_one_matters" not in _keys(name)


def test_plus_one_matters_excludes_no_counters_eq0_predicate():
    """Hindervines (CR 122.1): "Prevent all combat damage ... by creatures
    with NO +1/+1 counters on them" carries a P1P1 predicate with the EQ-0
    "no counters" comparator — the INVERSE of a counter-caring payoff (an
    absence punisher, not a build-around). :func:`counter_pred_kinds`
    deliberately excludes the EQ-0 form corpus-wide (shared by every counter
    lane, not just this one) — deliberately negative-pinned."""
    assert "plus_one_matters" not in _keys("Hindervines")


def test_plus_one_matters_excludes_valid_source_any_kind_reference():
    """Yathan Tombguard (CR 122.1 / 603.2): "Whenever a creature you control
    with a counter on it deals combat damage to a player, ..." rides a
    ``deals_damage`` trigger's ``valid_source`` field (the damage SOURCE'S
    own watched filter) — a DIFFERENT field from the ``counter_added`` /
    ``dies``-style triggers' ``valid_card`` the existing kind-agnostic-HAVE
    exclusion (test_plus_one_matters_excludes_kind_agnostic_have_reference)
    already covers. The Counters predicate here is explicit ``Any`` kind, so
    it's the SAME shed class (a kind-agnostic reference is not a +1/+1
    payoff), just a structurally distinct node shape — deliberately
    negative-pinned as a second representative."""
    assert "plus_one_matters" not in _keys("Yathan Tombguard")


def test_any_counter_matters_predicate_arm():
    assert ("any_counter_matters", "you", "") in _idents("Concord with the Kami")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — the PUMP arm's dynamic count-operand QTY node
        # (CR 122.1): Luxior's ``AddDynamicPower(value=Ref(qty=CountersOn))``
        # (kind-agnostic, "for each counter on it") and Withering Hex's
        # scaled-Multiply debuff form (``AddDynamicPower(value=Multiply(factor=-1,
        # inner=Ref(qty=CountersOn(counter_type='plague'))))`` — a NAMED kind,
        # still routes here since its raw isn't "+1/+1 counter" text).
        "Luxior, Giada's Gift",
        "Withering Hex",
    ],
)
def test_any_counter_matters_pump_qty_arm(name):
    assert ("any_counter_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — a mass STATIC restriction/grant whose OWN
        # ``affected`` names the counter-bearing filter directly (CR 122.1):
        # Rishkar's "each creature you control with a counter on it has …"
        # (a whole-unit static, not a per-modification concept).
        "Rishkar, Peema Renegade",
        # Nils's "each creature with one or more counters on it can't attack
        # you …" — the SAME whole-unit static shape, a restriction not a grant.
        "Nils, Discipline Enforcer",
        # A one-shot conferred grant nested inside a ``GenericEffect``'s OWN
        # ``static_abilities`` (Baxter's keyword-flying grant; Bulwark Ox's
        # hexproof/indestructible grant) — descended via ``iter_static_defs``.
        "Baxter, Fly in the Ointment",
        "Bulwark Ox",
    ],
)
def test_any_counter_matters_static_descent_arms(name):
    assert ("any_counter_matters", "you", "") in _idents(name)


def test_any_counter_matters_beyond_legacy_gain():
    """Perrie, the Pulverizer (ADR-0038 W3 batch 3, CR 122.1): a genuine
    counter-count pump ("+X/+X, where X is the number of different kinds of
    counters among permanents you control") the legacy ``old_ir_for`` MISSES —
    its own raw-text slice for this effect is 'gain trample and gets +X/+X'
    (the "where X is …" explanation clause lives elsewhere), so legacy's
    ``"counter" in raw.lower()`` gate never matches. The crosswalk reads the
    STRUCTURED ``CountersOnObjects`` qty node instead — a beyond-legacy gain,
    not an over-fire (never test-pinned against the legacy arm since it never
    fired there)."""
    assert ("any_counter_matters", "you", "") in _idents("Perrie, the Pulverizer")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 122.1 / 603.2) — a counter-HAVE TRIGGER:
        # "whenever a creature you control with a counter on it dies" (The
        # Swarmlord, Puca's Covenant) / "... attacks" (Skyboon Evangelist) /
        # "... with counters on it dies" (Cleopatra) / "attack with one or
        # more creatures with counters on them" (Metropolis Angel). The
        # Counters:Any predicate rides the TRIGGER's own watched-object
        # filter (``valid_card``), never an effect/static filter.
        "The Swarmlord",
        "Cleopatra, Exiled Pharaoh",
        "Puca's Covenant",
        "Skyboon Evangelist",
        "Metropolis Angel",
    ],
)
def test_any_counter_matters_trigger_valid_card_arm(name):
    assert ("any_counter_matters", "you", "") in _idents(name)


def test_any_counter_matters_player_counter_poison_arm():
    """Mycosynth Fiend / Vishgraz, the Doomhive ("gets +1/+1 for each poison
    counter your opponents have", CR 122.1): the player-counter scale is a
    distinct qty node (``PlayerCounter``, ``kind`` field) from the
    permanent-scoped ``CountersOn``/``CountersOnObjects`` (``counter_type``
    field). Legacy fires any_counter_matters for Poison specifically."""
    assert ("any_counter_matters", "you", "") in _idents("Mycosynth Fiend")
    assert ("any_counter_matters", "you", "") in _idents("Vishgraz, the Doomhive")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 — Experience carries its OWN dedicated lane
        # (experience_matters, ADR-0034) and must NOT also open
        # any_counter_matters via the PlayerCounter qty arm above — the
        # corpus's only other PlayerCounter kind (Poison) legitimately does.
        "Kalemne, Disciple of Iroas",
        "Kelsien, the Plague",
        "Minthara, Merciless Soul",
        "Azula, Ruthless Firebender",
    ],
)
def test_any_counter_matters_excludes_experience_counter(name):
    assert "any_counter_matters" not in _keys(name)


def test_any_counter_matters_buried_token_static_text_idiom():
    """Moira Brown, Guide Author (CR 122.1): the granted token's OWN static
    ability ("Equipped creature gets +1/+1 for each quest counter among
    permanents you control") is buried two levels deep (trigger → make_token
    effect → the token's own static_abilities), and phase's parse of that
    buried def drops the "for each quest counter" scale to a FIXED
    ``AddPower(value=1)``/``AddToughness(value=1)`` pair — no ``Ref``/
    ``dynamic_count`` for :func:`count_operand_qty` to read. A bucket-B
    text-idiom fallback on the def's own ``description`` (gated on
    count_operand_qty finding NOTHING, so a genuine structured scale is never
    double-read) recovers it."""
    assert ("any_counter_matters", "you", "") in _idents("Moira Brown, Guide Author")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 122.1) — beyond-legacy GAINS. All four share
        # the "each creature you control with a counter on it has/gains
        # <keyword>" static shape, which the crosswalk already reads
        # structurally via the SAME whole-unit static ``affected`` arm that
        # fires for Rishkar/Nils. Legacy MISSES this class: its
        # ``_mass_creature_grant_marker`` regex fallback requires the bare
        # PLURAL phrase "creatures you control" immediately followed by
        # gain/have (project.py's ``_BARE_CREATURES_YOU_CONTROL`` anchor) —
        # "each creature you control WITH A COUNTER ON IT has ward {1}" is
        # singular AND carries an intervening modifier clause, so the regex
        # never matches, and the OLD IR's structured keyword-grant markers
        # (``_mass_creature_grant_marker`` / ``_global_ability_grant_markers``)
        # synthesize a BARE ``Creature`` filter for the grant target,
        # dropping the Counters predicate entirely — legacy never had a path
        # to see it. Root-caused this session (2026-07): Rishkar/Nils fire
        # because THEIR phase parse is a Boost/GenericEffect with a real
        # structured Counters-predicate subject the old IR's effect-subject
        # read (``_signals_ir`` ~8591) already covers; these four are
        # GrantStaticAbility shapes the old IR's marker-synthesis simplifies
        # away. A genuine crosswalk improvement, not an over-fire.
        "Cathedral Acolyte",
        "Innkeeper's Talent",
        "Iroh, Dragon of the West",
        "Matt Murdock, Justice Seeker",
        "Michelangelo, Mutant BFF",
    ],
)
def test_any_counter_matters_keyword_grant_beyond_legacy_gain(name):
    assert ("any_counter_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Control Magic", True),  # ChangeController static — theft
        ("Act of Treason", True),  # GainControl effect — theft
        ("Donate", False),  # GiveControl (you give your own away)
        ("Brooding Saurian", False),  # Owned reset (each player regains own)
    ],
)
def test_gain_control_theft_vs_donate_reset(name, should_fire):
    assert (("gain_control", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Dockside Extortionist", ("treasure_makers", "you", "")),
        ("Tireless Tracker", ("clue_makers", "you", "")),  # investigate
        ("Bartered Cow", ("food_makers", "you", "")),
        ("Voldaren Bloodcaster", ("blood_makers", "you", "")),
    ],
)
def test_resource_token_makers(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize(
    "name",
    # genuine mills carrying the Scryfall ``Mill`` keyword (the field-lookup source)
    ["Stitcher's Supplier", "Glimpse the Unthinkable", "Hedron Crab"],
)
def test_mill_makers_fires(name):
    assert ("mill_makers", "any", "") in _idents(name)


def test_proliferate_makers_fires():
    assert ("proliferate_makers", "you", "") in _idents("Karn's Bastion")


def test_energy_makers_fires():
    assert ("energy_makers", "you", "") in _idents("Aetherworks Marvel")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Stoneforge Mystic", True),  # Equipment-card tutor
        ("Kor Outfitter", True),  # attach ANOTHER Equipment onto a creature
        ("Bonesplitter", False),  # self-equip (the gear) — payload, not a maker
    ],
)
def test_voltron_makers_attach_other_vs_self(name, should_fire):
    assert (("voltron_makers", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — the unattach maker idiom (CR 701.3d): a
        # structural ``Unattach`` cost (bare, self-unattach-as-a-COST idiom
        # — "{T}, Unattach ~: <effect>") nested inside a granted ability's
        # ``GrantAbility.definition``.
        "Leonin Bola",
        # a structural ``UnattachAll`` EFFECT whose ``attachment`` is NOT
        # SelfRef (stripping gear from an opponent's/any creature — the
        # Reconfigure self-toggle exclusion, CR 702.151j, does not apply).
        "Disarm",
        # the ``Attach`` gear resolved by a SIBLING effect in the SAME unit
        # (phase's ``ParentTarget``/``TriggeringSource`` back-reference is
        # POSITION-relative): a ``gain_control`` effect whose OWN ``target``
        # is directly ``Typed(Equipment)``.
        "Ogre Geargrabber",
        # …or a sibling ``TargetOnly`` node's own ``target`` directly
        # ``Typed(Equipment)`` (Stolen Uniform's two-target chain).
        "Stolen Uniform",
        # a ``ChangeZone`` reanimating an Aura/Equipment CARD onto the
        # battlefield (CR 303.4c/301.5c require such a card enter attached
        # — a fully STRUCTURAL tell via the target's own subtype, no text
        # idiom needed).
        "Hakim, Loreweaver",
        "One Last Job",  # a Spree mode with NO ability-level description at all
        # the SAME reanimate-with-attach idiom, but this card's ChangeZone
        # target is an UNRESOLVED back-reference (multi-hop) — the
        # LAST-RESORT per-ability description scan, gated on a Battlefield
        # ChangeZone existing in the SAME unit (never whole-card).
        "Unfinished Business",
        # the "aura/equipment you control becomes attached" trigger idiom:
        # phase has no structural trigger EVENT for this at all (an
        # unresolved ``mode=Unknown`` MirrorVariant) — the unit's own
        # description is the sole residue.
        "Siona, Captain of the Pyleas",
        "Eriette, the Beguiler",
        # a residual clause phase drops entirely into an ``Unimplemented``
        # node's OWN description (one clause, never cross-clause bleed).
        "Akiri, Fearless Voyager",  # "unattach an Equipment from a creature..."
        "Reckless Crew",  # "...you may attach an Equipment you control to it"
        "Liberated Livestock",  # the REVERSED "aura ... attached" word order
    ],
)
def test_voltron_makers_recovered_mechanisms(name):
    """ADR-0038 W3 batch 3 (CR 301.5/303.4/701.3d): voltron_makers recovers
    the unattach-maker / sibling-gear-attach / reanimate-with-attach /
    becomes-attached / Unimplemented-residue mechanisms the base structural
    gate above misses. Verified against the real Card IR this session; each
    card's phase record is pinned in ``crosswalk_fixture_cards.json``."""
    assert ("voltron_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — adjudicated SHEDS: legacy's own
        # ``VOLTRON_MAKER_REGEX`` over-fires on these via its bare
        # "(return|put)…aura…attached" branch, but NONE of the three
        # perform the CR 701.3a Attach action (take an Aura/Equipment/
        # Fortification and put it onto an object) — verified this session.
        "Animal Friend",  # COUNTS existing attachments (a payoff), no attach action
        "Portal of Sanctuary",  # a Bounce (return to hand), never an attach
        "Seedling Charm",  # a Bounce (return an Aura to its owner's hand)
    ],
)
def test_voltron_makers_sheds_no_attach_action(name):
    """ADR-0038 W3 batch 3 (CR 701.3a): a card whose text superficially
    matches the legacy "aura … attached" word idiom but performs no CR
    701.3a Attach action (a count of existing attachments, or a bounce)
    correctly does NOT open voltron_makers — an adjudicated shed of a
    legacy over-fire."""
    assert "voltron_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — adjudicated GAINS beyond the legacy Card
        # IR: ``Fumble``'s ``GainControlAll`` (Aura/Equipment subtype +
        # ``AttachedToRecipient``) then ``AttachAll`` to another creature
        # is the SAME "steal gear and reattach" pattern as Ogre Geargrabber
        # (CR 301.5/303.4/720), just as a MASS form legacy's own regex
        # doesn't recognize (`AttachAll` is a distinct phase tag from the
        # `Attach`/`attach` word regex branches). ``Auriok Survivors``'
        # ChangeZone-onto-battlefield Equipment reanimation is the SAME
        # structural tell as Hakim/One Last Job, just missed by legacy's
        # own ``VOLTRON_MAKER_REGEX`` (its "attach [target/all/…]
        # equipment/aura" branch requires the literal word "attach"
        # immediately, which "you may return target Equipment card... If
        # you do, you may attach it" does not satisfy at the right
        # position).
        "Fumble",
        "Auriok Survivors",
    ],
)
def test_voltron_makers_structural_gains_beyond_legacy(name):
    """ADR-0038 W3 batch 3: a genuine CR 301.5/303.4/720 gear-attach action
    legacy's own regex/structural detector misses entirely — verified
    structurally correct against the real Card IR this session."""
    assert ("voltron_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Sram, Senior Edificer", "Reyav, Master Smith"],  # cast-spell / attachment-state
)
def test_voltron_matters_payoff(name):
    assert ("voltron_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W5 tails — equip/reconfigure/fortify-ability cost reducers
        # (CR 702.6c / 601.2f): a ``ReduceAbilityCost`` static keyed on
        # ``equip`` (Bureau Headmaster, Fervent Champion, Éowyn) or a
        # granted cost-reduced Equip keyword (Nahiri, Storm of Stone).
        "Bureau Headmaster",
        "Fervent Champion",
        "Éowyn, Lady of Rohan",
        "Nahiri, Storm of Stone",
        # a ``SourceIsEquipped`` self-referential CONDITION gating a static
        # (CR 301.5c "as long as ~ is equipped" — Patriot, Auriok
        # Steelshaper, Cloud's double-trigger, Cloud's double strike).
        "Patriot, Young Avenger",
        "Auriok Steelshaper",
        "Cloud, Midgar Mercenary",
        "Cloud, Planet's Champion",
        # a cast-cost reducer whose spell_filter is Equipment/Aura (CR
        # 601.2f — Transcendent Envoy's Aura discount, Cid's Equipment/
        # Vehicle discount) or a granted Flash to Aura/Equipment spells
        # (CR 702.8a — Sigarda's Aid).
        "Transcendent Envoy",
        "Cid, Freeflier Pilot",
        "Sigarda's Aid",
        # the ability's OWN activation cost_reduction scaling on an
        # Equipment COUNT (Plate Armor's equip cost, CR 601.2f).
        "Plate Armor",
        # an attachment-STATE predicate on a trigger's CONDITION filter,
        # not valid_card/valid_source (Koll's dies-if-enchanted-or-equipped
        # gate, CR 301.5c/303.4b).
        "Koll, the Forgemaster",
        # a damage/count operand scaled on a bare Equipment COUNT — a
        # genuine "cares how much gear I have" tell, distinct from a bare
        # subtype on a TARGET/effect subject (Armed Response direct Ref;
        # Slash of Light's Sum of two counts; Nahiri, Heir of the
        # Ancients' Multiply-wrapped "twice the number of"). CR 107.3.
        "Armed Response",
        "Slash of Light",
        "Nahiri, Heir of the Ancients",
        # an ``Unrecognized``-condition text residue carrying the SAME
        # self-referential "is equipped" tell phase couldn't structure
        # (Enkira's "~ is equipped, it must be blocked"). CR 301.5c.
        "Enkira, Hostile Scavenger",
        # a static's own ``affected`` filter carrying the attachment-STATE
        # predicate — read off the (static_def, mod) pair, since
        # ``iter_concepts()`` yields the MODIFICATION as the concept node,
        # not the static def that carries ``affected`` (Hemlock Vial's
        # "each equipped creature", Blacksmith's Talent's ``HasAttachment``
        # anthem, Resistance Reunited's EquippedBy grant — all on a card
        # that is NOT itself an Equipment/Aura, so the self-payload
        # exclusion doesn't apply). CR 301.5c/303.4b.
        "Hemlock Vial",
        "Blacksmith's Talent",
        "Resistance Reunited",
    ],
)
def test_voltron_matters_recovered_mechanisms(name):
    """ADR-0038 W5 tails: voltron_matters recovers the equip/cast cost-
    reduction, SourceIsEquipped condition, trigger-condition-filter,
    ability cost_reduction, bare-count-scaling, and Unrecognized-residue /
    static-affected mechanisms the base structural gate misses. Each card's
    phase record is pinned in ``crosswalk_fixture_cards.json``."""
    assert ("voltron_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W5 tails — adjudicated SHEDS: legacy's own
        # ``VOLTRON_PAYOFF_REGEX`` over-fires on these via its bare
        # ``equipment you control`` / ``equipped creature`` substring
        # branches, but NONE of them carry a genuine PAYOFF (a "cares
        # about attached gear" tell) — every one is either a voltron_
        # makers-only attach ACTION (CR 701.3a — the card PERFORMS the
        # attaching, it doesn't reward being attached) or a housekeeping
        # clause (Benevolent Blessing's "doesn't remove" carve-out is a
        # protection-timing clarification, CR 702.16e, not a build-around).
        # Verified this session against the real Card IR.
        "Hammer of Nazahn",  # ETB attach trigger only, no separate payoff
        "Battlefield Improvisation",  # "you may attach…Equipment…to it"
        "Nahiri, the Lithomancer",  # "[+2]: …attach an Equipment…to it"
        "Unexpected Request",  # "you may attach an Equipment…to that creature"
        "Armed and Armored",  # "Attach any number of Equipment…to it"
        "Super-Soldier Serum",  # attach-on-attack trigger, self Aura payload
        "Goldwardens' Gambit",  # per-token attach (Unimplemented residue)
        "Inventory Management",  # repeat-attach for each Aura/Equipment owned
        "Resolute Strike",  # "…you may attach an Equipment…to it"
        "Benevolent Blessing",  # protection carve-out, not a payoff
    ],
)
def test_voltron_matters_sheds_attach_action_or_housekeeping(name):
    """ADR-0038 W5 tails (CR 701.3a / 301.5c): a card whose text superficially
    matches the legacy "equipment/aura you control … attached" word idiom but
    performs no genuine payoff — either an attach ACTION (voltron_makers
    territory) or a non-build-around housekeeping clause — correctly does NOT
    open voltron_matters. Adjudicated sheds of a legacy over-fire."""
    assert "voltron_matters" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W5 tails — MANDATORY SHEDS (session-adjudicated): four
        # Unfinity "Guest" creatures whose ONLY conditional-keyword text
        # ("This creature has X as long as you control a stickered
        # permanent") has nothing to do with Equipment/Aura attachment.
        # Legacy's voltron_matters fires these ONLY via the LOW-confidence
        # bare "commander damage (CR 903.10a)" membership fallback — a
        # completely different notion ("is this creature a good body to
        # put gear on") than the crosswalk's structural PAYOFF gate
        # ("does this card care about attached gear"). The crosswalk never
        # implements that fallback, so these correctly stay off the lane.
        "Big Winner",
        "Croakid Amphibonaut",
        "Grabby Tabby",
        "Scared Stiff",
    ],
)
def test_voltron_matters_sheds_commander_damage_fallback(name):
    """ADR-0038 W5 tails: the legacy IR's bare commander-damage MEMBERSHIP
    fallback (power>=2, no other plan, CR 903.10a) is a different notion
    from voltron_matters' structural "cares about attached gear" PAYOFF gate
    — the crosswalk correctly never fires it. Mandatory sheds, adjudicated
    this session."""
    assert "voltron_matters" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — additional representatives of the 62-card
        # commander-damage MEMBERSHIP-fallback shed class (see
        # test_voltron_matters_sheds_commander_damage_fallback for the
        # original 4 Unfinity mandatory sheds). Every one of these fires
        # the legacy bare "no other plan + power>=2" fallback (CR 903.10a)
        # with NO other voltron_matters arm; the crosswalk correctly never
        # implements that fallback. Sliver-heavy because a tribal-lord
        # ability isn't itself a high-confidence "other plan" signal in
        # legacy's own IR-arm set. Verified this session against the real
        # Card IR.
        "Lymph Sliver",
        "Armor Sliver",
        "Ward Sliver",
        "Notion Thief",
        "Bogardan Hellkite",
        "Changeling Titan",
        "Ayumi, the Last Visitor",
    ],
)
def test_voltron_matters_sheds_commander_damage_fallback_w6(name):
    """ADR-0038 W6 endgame: further representatives of the mass commander-
    damage MEMBERSHIP-fallback shed class, corpus-verified against the real
    Card IR this session. CR 903.10a."""
    assert "voltron_matters" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — a trigger DEFINITION phase couldn't
        # structure AT ALL (an ``Unknown`` ``mode`` MirrorVariant carrying
        # only the raw clause, no reachable ``valid_card``/``condition``)
        # but whose own preserved ``description`` carries the SAME voltron
        # attachment-STATE tell the structural gate reads off a typed
        # filter elsewhere (Kassandra, Eagle Bearer: "Whenever a creature
        # you control with a legendary Equipment attached to it deals
        # combat damage to a player, draw a card" — the SAME Unknown-mode
        # node the combat-damage lanes already recover via
        # ``_unknown_mode_combat_damage_to_player``, extended here to
        # voltron_matters via ``_unknown_mode_voltron_attachment``). CR
        # 301.5c/303.4b.
        "Kassandra, Eagle Bearer",
        # a modal mode's own effect (a fully-structured CastFromZone, NOT
        # an Unimplemented) carrying a mana-value CONSTRAINT scaled on the
        # greatest mana value among Equipment — a ``Ref`` over an
        # ``Aggregate`` qty, which ``ref_count_filter`` doesn't cover (it
        # only unwraps ``ObjectCount``). Tetsuo, Imperial Champion: "cast
        # an instant or sorcery spell from your hand with mana value less
        # than or equal to the greatest mana value among Equipment
        # attached to it." CR 107.3/301.5c.
        "Tetsuo, Imperial Champion",
        # a mana ability's own ``restrictions`` list scoping the produced
        # mana to Equipment spells / an equip-ability activation (Ronin,
        # Shadow Stalker: "Spend this mana only to cast Equipment spells or
        # activate equip abilities") — correctly-parsed but previously
        # unread by the cost-REDUCER arms above. CR 106.6.
        "Ronin, Shadow Stalker",
    ],
)
def test_voltron_matters_recovered_mechanisms_w6(name):
    """ADR-0038 W6 endgame: voltron_matters recovers an Unknown-mode
    trigger's own text residue, a modal mode's Aggregate mana-value
    constraint, and a mana ability's Equipment-scoped restriction — three
    mechanisms the W5 tail characterized as genuine residual gaps
    (Kassandra's "trigger mode=Unknown", Tetsuo's "Aggregate-qty gap",
    Ronin's "nested mana-restriction-variant gap") that turned out to be
    closable off EXISTING typed nodes, corpus-verified this session (all
    three read ONLY the one node's own structured/preserved field, never a
    whole-card scan)."""
    assert ("voltron_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — the SAME mana-restriction mechanism above,
        # on a non-creature LAND (proves the arm is unconditional, not
        # creature-gated) and on a card that already fired voltron_matters
        # via a DIFFERENT arm (proves the new arm is additive, not a
        # regression risk). Corpus-verified: legacy never fires Tournament
        # Grounds (a land carries no commander-damage fallback), so this is
        # a genuine BREADTH gain (on-theme, not an over-fire) rather than a
        # live_only closure. CR 106.6.
        "Tournament Grounds",
        "Freya Crescent",
    ],
)
def test_voltron_matters_mana_restriction_breadth_w6(name):
    """ADR-0038 W6 endgame: the mana-restriction arm fires on a land with
    no creature body (Tournament Grounds) and stays additive on a card
    that already carried voltron_matters via another arm (Freya
    Crescent's own equip-ability restriction). CR 106.6."""
    assert ("voltron_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W6 endgame — adjudicated SHEDS: legacy's bare
        # ``VOLTRON_PAYOFF_REGEX`` "equipment attached to it" word tell
        # fires on these, but neither is a build-around PAYOFF — both are
        # REMOVAL/theft effects that reference an opponent's attacking
        # creature's Equipment as a side effect of the removal, not a
        # "this deck cares about MY gear" tell. Soul Nova exiles the
        # attacking creature AND all Equipment attached to it (CR 301.5c);
        # Shackles of Treachery steals a creature and grants it a one-turn
        # "destroy attached Equipment on damage" trigger (temporary
        # theft-and-punish, CR 105.1/711). Verified this session against
        # the real Card IR: neither's Equipment-target filter carries a
        # reachable attachment-STATE predicate (phase's typed target is a
        # bare Equipment-subtype filter with no linkage to the removed/
        # stolen creature) — moot regardless, since even a linked shape
        # would be a REMOVAL target, not a payoff.
        "Soul Nova",
        "Shackles of Treachery",
    ],
)
def test_voltron_matters_sheds_removal_target_reference(name):
    """ADR-0038 W6 endgame: a REMOVAL/theft spell that references an
    opponent's attacking creature's Equipment as a side effect of the
    removal is not a voltron PAYOFF — correctly does not open
    voltron_matters. Adjudicated sheds of a legacy over-fire (CR 301.5c)."""
    assert "voltron_matters" not in _keys(name)


def test_voltron_matters_residual_dropped_clauses():
    """ADR-0038 W6 endgame — genuine residual (defer, no clause_grammar.py
    change this wave, per ADR-0039): four cards whose phase parse silently
    DROPS the exact clause voltron_matters needs, with zero recoverable
    residue anywhere in the tree (verified via direct node inspection this
    session, not just a diff count):

    * Warchanter Skald — the trigger's own ``condition`` field is ``None``;
      "if it's enchanted or equipped" survives ONLY inside the trigger's
      whole-clause ``description`` string, indistinguishable from a
      genuinely-absent condition on any other trigger (CR 301.5c).
    * Judgment Bolt — "and X damage to that creature's controller, where X
      is the number of Equipment you control" is dropped in its entirety;
      the single ``S_abilities`` unit carries only the base 5-damage
      effect, no second recipient/scaling node anywhere (CR 107.3).
    * Forge Anew — the "pay {0} rather than the equip cost" clause parses
      as a bare unlinked ``PayCost`` effect with no reachable Equipment/
      equip-keyword tag tying it to the granted timing permission
      (CR 601.2f).
    * Animal Friend — the granted trigger's ``PutCounter`` effect count is
      ``T_count__Fixed(value=1)``; "for each Aura and Equipment attached to
      ~ other than ~" is dropped from the count entirely, not merely
      un-descended-into (CR 107.3/301.5c).

    Each is a genuine phase grammar gap (the count/condition-building rule
    for this exact clause shape), not a crosswalk_signals.py detector gap —
    closing it needs a phase-mirror grammar change, which is out of scope
    for a single-wave session per the recipe's "no clause_grammar.py
    changes" rule. Ledgered here as the W6 bridge-ledger input."""
    for name in ("Warchanter Skald", "Judgment Bolt", "Forge Anew", "Animal Friend"):
        assert "voltron_matters" not in _keys(name)


def test_voltron_matters_residual_dropped_scaling():
    """ADR-0038 W6 endgame — genuine residual (defer): Sage's Reverie's
    "draw a card for each Aura you control that's attached to a creature" /
    "Enchanted creature gets +1/+1 for each Aura you control that's
    attached to a creature" both parse as FIXED values (``T_count__Fixed
    (value=1)`` on the Draw, ``AddPower(value=1)``/``AddToughness(value=1)``
    on the static) — the "for each Aura ... attached" scaling clause is
    dropped from BOTH sites entirely, with no dynamic Ref/Aggregate operand
    anywhere in the tree to read. A genuine phase grammar gap (CR
    107.3/301.5c), deferred per ADR-0039 (no clause_grammar.py change this
    wave)."""
    assert "voltron_matters" not in _keys("Sage's Reverie")


# ── Batch-3 over-fire regressions (rules-lawyer adjudicated; ADR-0035) ─────────
# Three blocking crosswalk-only over-fires the Stage-2 shadow diff surfaced:
#   1. gain_control fired on GIVE-AWAY / chaos control changes (CR 110.2 / 603.10d —
#      the beneficiary is an opponent, not you).
#   2. enchantments_matter fired on a MODAL "each opponent sacrifices an enchantment"
#      edict (CR 701.21a — a player only sacrifices a permanent THEY control); the
#      sac's mode-arm player_scope was below the batch-2 unit-level edict guard's reach.
#   3. mill_makers, as a structural ``Mill``-effect port, re-introduced the three
#      phase mislabels (Bone Dancer / Scroll Rack / Soldevi Digger) ADR-0027 dropped
#      by moving mill_makers to the Scryfall ``Mill`` keyword (CR 701.17a).


@pytest.mark.parametrize(
    "name",
    [
        "Sky Swallower",  # target opponent gains control of all YOUR permanents
        "Fateful Handoff",  # an opponent gains control of that permanent (ParentTarget)
        "Rogue Skycaptain",  # an opponent gains control of it (ParentTarget)
        "Wishclaw Talisman",  # an opponent gains control of THIS artifact (SelfRef)
        "Inniaz, the Gale Force",  # each player gains control (player_scope on execute)
        "Scrambleverse",  # each player gains control (player_scope on deep sub_ability)
    ],
)
def test_gain_control_not_fired_by_giveaway(name):
    """A control change whose NEW controller is an opponent / each player is a
    give-away or chaos swap, not a you-gain payoff (CR 110.2 / 603.10d)."""
    assert "gain_control" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Mind Control",  # ChangeController enchant — the new controller is you
        "Control Magic",  # ChangeController enchant
        "Act of Treason",  # GainControl of an opponent's creature (controller-null)
        # phase mislabels "target creature that OPPONENT controls" as controller:You
        # AND the unit has an unrelated per-opponent tap loop — the give-away guard
        # must read the gain-control's OWN wrapper scope, not the sibling loop's.
        "Nihiloor",
    ],
)
def test_gain_control_youtheft_preserved(name):
    """Genuine you-take-control still fires past the give-away guard (CR 720)."""
    assert ("gain_control", "you", "") in _idents(name)


def test_enchantments_matter_not_fired_by_modal_edict():
    """Baleful Beholder's mode 1 ("Each opponent sacrifices an enchantment of their
    choice") is enchantment HATE, an opponent edict — the mode-arm player_scope is
    Opponent, so neither enchantments_matter NOR sacrifice_outlets fires (CR 701.21a).
    """
    keys = _keys("Baleful Beholder")
    assert "enchantments_matter" not in keys
    assert "sacrifice_outlets" not in keys


def test_enchantments_matter_payoff_preserved():
    """A genuine your-enchantments payoff (Enlightened Tutor's Enchantment tutor)
    still fires past the modal-edict guard."""
    assert ("enchantments_matter", "you", "") in _idents("Enlightened Tutor")


@pytest.mark.parametrize(
    "name",
    [
        "Bone Dancer",  # opp-GY→battlefield REANIMATION — phase mislabels as Mill
        "Soldevi Digger",  # GY→library-bottom recycle — phase mislabels as Mill
    ],
)
def test_mill_makers_not_fired_by_phase_mislabel(name):
    """The keyword field-lookup (no Scryfall ``Mill`` keyword) drops the phase
    ``Mill``-effect mislabels the structural port re-introduced (CR 701.17a)."""
    assert "mill_makers" not in _keys(name)


# ── Batch 4 (ADR-0035 Stage 2): graveyard pair + doer cluster + copy cluster ──


def test_fight_makers_fires():
    assert ("fight_makers", "you", "") in _idents("Prey Upon")
    # Lightning Bolt is a DealDamage burn, not a Fight — must NOT fire.
    assert "fight_makers" not in _keys("Lightning Bolt")


def test_fight_makers_allowlisted_residue():
    """ADR-0038 W1 batch-4: Gimli, Mournful Avenger's third-resolution
    rider ("When this ability resolves for the third time this turn, ~
    fights up to one target creature you don't control.") lands as an
    Unimplemented effect the grammar's "fight" SIMPLE_VERB token
    re-decorates to the native "fight" concept (CR 701.12)."""
    assert ("fight_makers", "you", "") in _idents("Gimli, Mournful Avenger")


def test_fight_makers_nested_granted():
    """A ``Fight`` tag buried inside a GRANTED-ability construct (or a
    chained sub_ability's "Otherwise" branch) the flat per-unit
    concept-node walk never surfaces as its own node: Cherished
    Hatchling's cast-a-Dinosaur GrantTrigger, Kiora, Master of the
    Depths' -8 CreateEmblem, Aggressive Biomancy's token-copy exception
    clause, Tunnel of Love's "Otherwise, the chosen creatures fight each
    other" (a ``ParentTarget``-scoped Fight). :func:`has_nested_fight`
    reaches all four shapes."""
    for name in (
        "Cherished Hatchling",
        "Kiora, Master of the Depths",
        "Aggressive Biomancy",
        "Tunnel of Love",
    ):
        assert ("fight_makers", "you", "") in _idents(name), name


def test_fight_makers_whole_card_residue_no_node():
    """Tolsimir, Friend to Wolves' "that creature fights up to one target
    creature you don't control" -- the trigger's own ``execute`` is a
    bare ``GainLife``, no ``sub_ability`` chain at all, so phase drops
    the fight clause WHOLLY (no node of any kind, ADR-0038 no-residue
    class 2). ``tree_synthesis._arm_fight_makers`` relocates the legacy
    ``_FIGHT_RAW`` face-level mirror to gap-gated projection time,
    emitting the real "fight" concept."""
    assert ("fight_makers", "you", "") in _idents("Tolsimir, Friend to Wolves")


def test_goad_makers_structural_and_keyword():
    # Disrupt Decorum carries a GoadAll effect AND the Scryfall Goad keyword.
    assert ("goad_makers", "opponents", "") in _idents("Disrupt Decorum")


def test_goad_makers_single_target_force_bridge():
    """ADR-0038 W3 batch 3: ``_GOAD_STYLE_FORCE`` (CR 701.15b) lifts a
    single-target "target creature ... attacks ... if able" compulsion to
    goad_makers even when phase types it as a bare ``Unimplemented``
    clause, not a dedicated Goad effect — Alluring Siren."""
    assert ("goad_makers", "opponents", "") in _idents("Alluring Siren")


def test_goad_makers_reward_bridge():
    """ADR-0038 W3 batch 3: ``_GOAD_REWARD_REF`` (CR 701.15b's "attacks a
    player other than ..." redirect) lifts the goad REWARD/payoff idiom —
    Gahiji, Honored One rewards a creature attacking one of your
    opponents."""
    assert ("goad_makers", "opponents", "") in _idents("Gahiji, Honored One")


def test_goad_makers_granted_combo_not_forceblock():
    """ADR-0038 W3 batch 3: Boros Battleshaper's GRANTED "up to one target
    creature attacks or blocks this combat if able" (an AddStaticMode
    MustAttack+MustBlock combo) is textually indistinguishable from the
    ForceBlock idiom's "block(s) it/that <noun>" shape but carries no
    ForceBlock tag — a genuine goad_makers member, not excluded."""
    assert ("goad_makers", "opponents", "") in _idents("Boros Battleshaper")


def test_goad_makers_excludes_force_block():
    """ADR-0038 W3 batch 3 (CR 509.1c): Avalanche Tusker's "attacks,
    target creature ... blocks it this combat if able" is a dedicated
    ForceBlock provoke effect, not goad — the ForceBlock-shaped clause
    ("blocks it") must not fire goad_makers via the
    ``_GOAD_STYLE_FORCE`` text bridge."""
    assert "goad_makers" not in _keys("Avalanche Tusker")


def test_regenerate_makers_fires():
    assert ("regenerate_makers", "you", "") in _idents("River Boa")


# ADR-0038 W3 batch 2 unit 7 — the regenerate_makers GrantAbility deep-walk
# arm (CR 701.19a): a GRANTED "'{cost}: Regenerate this creature/permanent'"
# at any nesting depth — a tribal lord static (the Sliver cycle), an Aura's
# static, a spell's one-shot GenericEffect grant, a conditional static, or
# an animated land.
@pytest.mark.parametrize(
    "name",
    [
        "Clot Sliver",
        "Crypt Sliver",
        "Poultice Sliver",
        "Sedge Sliver",
        "Consecrated by Blood",
        "Molting Snakeskin",
        "Savage Silhouette",
        "Skeletal Grimace",
        "Drudge Spell",
        "Gobhobbler Rats",
        "Life Matrix",
        "Resuscitate",
        "Run Wild",
        "Skeletonize",
        "Spawning Pool",
        "Villainous Ogre",
        "Zombie Master",
    ],
)
def test_regenerate_makers_grant_ability_arm(name):
    assert ("regenerate_makers", "you", "") in _idents(name)


def test_regenerate_makers_last_resort_word_mirror():
    """Last-resort mirror (checked only when the structural arms find
    nothing), corpus-verified safe as a FALLBACK ONLY (267 of ~268
    non-"can't"-excluded commander-legal "regenerate" hits already fire
    the structural arms): a kicker-conditional ETB grant whose execute
    chain silently drops the granted-ability tail with no node at all
    (Anavolver, Degavolver), a compound "become <color>, gets +X/+Y, and
    gains <ability>" Unimplemented residue (Defiling Tears), and a
    multi-conditional static whose trailing conjunct folds into an
    Unrecognized condition-text tail (Tribal Golem). Pongify's "can't be
    regenerated" (the INVERSE — CR 701.19a note) never fires."""
    assert ("regenerate_makers", "you", "") in _idents("Anavolver")
    assert ("regenerate_makers", "you", "") in _idents("Degavolver")
    assert ("regenerate_makers", "you", "") in _idents("Defiling Tears")
    assert ("regenerate_makers", "you", "") in _idents("Tribal Golem")
    assert "regenerate_makers" not in _keys("Pongify")


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("Gray Merchant of Asphodel", "opponents"),  # drain (player_scope on wrapper)
        ("Dark Confidant", "you"),  # self-loss upkeep
        ("Erebos, God of the Dead", "you"),  # paylife cost buys a draw
    ],
)
def test_lifeloss_makers_scope_split(name, scope):
    assert ("lifeloss_makers", scope, "") in _idents(name)


def test_lifeloss_makers_land_paylife_excluded():
    """Horizon Canopy's ``Pay 1 life: draw`` is a LAND mana-source paylife — the land
    gate excludes it (CR 118.8), so no lifeloss_makers (the painland trap)."""
    assert "lifeloss_makers" not in _keys("Horizon Canopy")


def test_lifeloss_matters_trigger_and_keyword():
    assert ("lifeloss_matters", "opponents", "") in _idents("Exquisite Blood")
    # Light Up the Stage's Spectacle condition is reminder-text only → keyword route.
    assert ("lifeloss_matters", "opponents", "") in _idents("Light Up the Stage")


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Diabolic Edict", ("edict_makers", "opponents", "")),  # subject TargetPlayer
        ("Grave Pact", ("edict_makers", "opponents", "")),  # player_scope on wrapper
        ("Fleshbag Marauder", ("edict_makers", "each", "")),  # player_scope All
    ],
)
def test_edict_makers_fires(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize("name", ["Mycoloth", "Viscera Seer"])
def test_edict_makers_excludes_you_sac(name):
    """A you-sac (Mycoloth — sacrificed subject controller You; Viscera Seer — a sac
    COST, never an effect) is NOT an edict (CR 701.21a)."""
    assert "edict_makers" not in _keys(name)


def test_land_sacrifice_makers_fires():
    assert ("land_sacrifice_makers", "you", "") in _idents("Zuran Orb")
    # Ashnod's Altar sacrifices a CREATURE, not a land → sacrifice_outlets, not this.
    assert "land_sacrifice_makers" not in _keys("Ashnod's Altar")


# ADR-0038 W3 batch 4 (lands-and-ramp cluster): a Sacrifice cost LEAF phase
# buries where the per-ability concept walk never surfaces it. Verified CR:
# 701.21 (sacrifice), 400.7 (zone-change identity).
@pytest.mark.parametrize(
    "name",
    [
        "Soldevi Sage",  # "{T}, Sacrifice two lands:" — a Composite cost leaf
        "Cosmic Larva",  # "sacrifice this unless you sacrifice two lands" —
        # the alternative cost lives on the trigger's own unless_pay.cost
    ],
)
def test_land_sacrifice_makers_composite_and_unless_pay(name):
    assert ("land_sacrifice_makers", "you", "") in _idents(name)


def test_land_sacrifice_makers_excludes_land_dies_watcher():
    """Dingus Egg: "Whenever a land is put into a graveyard from the
    battlefield, ~ deals 2 damage to that land's controller" watches a land
    DYING by ANY means (destroy, sacrifice, or otherwise) — a payoff/punisher,
    not the actor performing a sacrifice (CR 701.21)."""
    assert "land_sacrifice_makers" not in _keys("Dingus Egg")


# ── batch-4 over-fire fixes (3 rules-lawyer-adjudicated scope gates, ADR-0035) ──
#   Fix 1: lifeloss direction reads the LoseLife RECIPIENT, not phase's trigger_scope
#     (mis-scoped to "you" for an opponent-object trigger — phase bug [P5], CR 119.3).
#   Fix 2: a triggered "that player sacrifices" upkeep edict (ScopedPlayer) scopes by
#     the trigger's turn constraint — symmetric each-player wraths → /each (CR 701.21a).
#   Fix 3: land_sacrifice_makers fires only on a SELF land-sac, excluding opponent
#     land-edicts that phase mislabels [P1]/[P3] (CR 701.21a).


@pytest.mark.parametrize(
    "name",
    [
        # phase mis-scopes trigger_scope="you" off an OPPONENT's object (bug [P5]):
        "Archfiend of the Dross",  # recipient ParentTargetController ("its controller")
        "Ashenmoor Liege",  # recipient TriggeringPlayer ("that player")
    ],
)
def test_lifeloss_makers_wrong_direction_excluded(name):
    """A drain whose LoseLife recipient is a RELATIVE/opponent player is opponent-loss,
    NOT a self-loss — it must scope /opponents, never /you (CR 119.3)."""
    idents = _idents(name)
    assert ("lifeloss_makers", "you", "") not in idents  # the wrong-direction over-fire
    assert ("lifeloss_makers", "opponents", "") in idents  # correct direction


def test_lifeloss_makers_self_loss_preserved():
    """Agent Venom's "you draw a card and lose 1 life" carries NO LoseLife recipient —
    a genuine self-loss, preserved at scope you (CR 119.3)."""
    assert ("lifeloss_makers", "you", "") in _idents("Agent Venom")


# ── ADR-0038 W4 giants (lifeloss_makers residual grind) ────────────────────
# Verified CR: 119.3 (loss adjusts the life total), 119.4 (paying life IS a
# cost but causes that much life loss), 118.3b / 118.8 (paying life / an
# additional cost).


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # a GRANTED ability's own quoted definition carries a real LoseLife
        # leaf a top-level unit.effects/.statics scan never flattens — an
        # iter_typed_nodes deep walk of the WHOLE unit finds it either way.
        ("Caustic Tar", "opponents"),  # "Enchanted land has '{T}: Target
        # player loses 3 life.'" — GrantAbility.definition.effect
        ("Pillory of the Sleepless", "you"),  # granted self-loss upkeep
        # trigger (GrantTrigger.trigger.execute.effect)
    ],
)
def test_lifeloss_makers_granted_ability_descent(name, scope):
    assert ("lifeloss_makers", scope, "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # a pay-life COST reachable only via a deep walk (not the top-level
        # unit.costs Composite scan): Gallowbraid's cumulative-upkeep
        # unless_pay.cost (payer=Controller); Wand of Denial's optional
        # "you may pay 2 life. If you do, ..." trigger-body PayCost effect
        # (payer=Controller).
        "Gallowbraid",
        "Wand of Denial",
    ],
)
def test_lifeloss_makers_deep_paylife_self_payer(name):
    assert ("lifeloss_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # a "unless [someone else] pays life" cost is a TAX the card imposes
        # on another player, not this card's own life payment — the payer
        # tag (ParentTargetController) is rejected by
        # _lifeloss_self_paid_cost's Controller/SelfRef/You gate.
        "Vectis Dominator",  # "unless its controller pays 2 life"
        "Killing Wave",  # "unless they pay X life" (each creature's
        # controller, not the caster)
    ],
)
def test_lifeloss_makers_excludes_non_controller_payer(name):
    assert "lifeloss_makers" not in _keys(name)


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # an Unimplemented "X loses N life [equal to ...]" residue phase's
        # own amount-ref grammar can't structure, recovered via the shared
        # clause_grammar "lose_life" token (ADR-0038 Unimplemented recovery
        # ALLOWLIST — recovery.py, no grammar growth).
        ("Final Punishment", "opponents"),
        ("Jaws of Defeat", "opponents"),
    ],
)
def test_lifeloss_makers_unimplemented_recovery(name, scope):
    assert ("lifeloss_makers", scope, "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # a "lost life this turn" CONDITION/reference (a WATCHER — the card
        # cares whether life was lost, it doesn't itself perform the loss,
        # CR 119.3) is a lifeloss_matters payoff, never lifeloss_makers —
        # phase structures the consequence as its OWN typed node (PlaceCounter
        # here) with a condition wrapper, so it never even reaches an
        # Unimplemented residue this lane could misread.
        "Savage Gorger",
        "Rakdos, Lord of Riots",
    ],
)
def test_lifeloss_makers_excludes_lost_this_turn_condition(name):
    assert "lifeloss_makers" not in _keys(name)


# ── ADR-0038 W5b (lifeloss_makers tail grind) ───────────────────────────────
# Verified CR: 119.3 (life loss / who loses), 119.4 (paying life IS a cost),
# 118.8 (an additional cost), 614 (replacement effects).


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # a GRANTED activated ability's OWN cost pays life — a shape a flat
        # top-level unit.costs/unit.effects scan never reaches (the grant
        # IS the only role=static concept at this unit's surface; the
        # granted ability's own cost/effect live a level deeper, inside
        # GrantAbility.definition). Mirrors the OLD-IR life_payment marker's
        # unconditional-you convention.
        ("Underworld Connections", "you"),  # "{T}, Pay 1 life: Draw a
        # card." granted to the enchanted land
        ("Hibernation Sliver", "you"),  # "Pay 2 life: Return this
        # permanent to its owner's hand." granted to all Slivers
    ],
)
def test_lifeloss_makers_granted_ability_paylife(name, scope):
    assert ("lifeloss_makers", scope, "") in _idents(name)


def test_lifeloss_makers_granted_ability_paylife_excludes_ramp():
    """Lithoform Blight grants the enchanted land TWO abilities — a plain
    "{T}: Add {C}" and a painland "{T}, Pay 1 life: Add one mana of any
    color." Both map to the ``ramp`` concept, so the granted-paylife arm's
    LOCAL non-ramp check (reading the SAME GrantAbility.definition's own
    effect, not the whole unit) correctly excludes it — the painland trap
    (CR 118.8), same principle as the top-level Horizon Canopy exclusion."""
    assert "lifeloss_makers" not in _keys("Lithoform Blight")


@pytest.mark.parametrize(
    "name",
    [
        # a paylife ``unless_pay`` nested in a GRANTED trigger — the
        # wrapper IS found by the existing deep walk (payer=Controller,
        # PayLife in its cost), but the OLD non-ramp gate read only
        # unit.effects (empty for a STATIC-origin unit whose only role=
        # static concept is the grant itself); the granted payoff
        # (Sacrifice / ChangeZone) is reachable only by walking INTO the
        # grant, so the gate now scans the WHOLE unit's EFFECT_CONCEPTS
        # tags instead of just its top-level unit.effects.
        "Vile Consumption",  # "sacrifice this creature unless you pay 1
        # life" granted to all creatures
        "Morgul-Knife Wound",  # "exile this creature unless you pay 2
        # life" granted to the enchanted creature
    ],
)
def test_lifeloss_makers_granted_unless_pay_non_ramp_gate(name):
    assert ("lifeloss_makers", "you", "") in _idents(name)


def test_lifeloss_makers_withercrown_deferred_gap():
    """Withercrown's granted trigger ("you lose 1 life unless you sacrifice
    this creature") collapses to ONE Unimplemented residue nested under
    unit.statics (GrantTrigger.trigger.execute.effect) — OUTSIDE
    ``apply_unimplemented_recovery``'s unit.effects-only scan (recovery.py's
    own docstring: "a genuine cost/static ConceptNode is never
    re-decorated; that migrates later, per-key"). A genuine, already-known
    phase-structuring gap, not a shed class — stays unrecovered this wave."""
    assert "lifeloss_makers" not in _keys("Withercrown")


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # phase degrades a CONDITION- or optional-"you may have"-wrapped
        # "each opponent loses N life" to a completely uninformative Typed
        # recipient filter (controller=None, no properties, no
        # type_filters) — the SAME shared _scope_from_player_node Typed
        # branch that correctly returns "each" for every OTHER caller
        # would misread this specific narrow shape as "each" too. The lane
        # distrusts an "each" read backed by this exact shape
        # (lifeloss_recipient_is_degraded_typed) and falls through to its
        # own text-based disambiguation, which correctly resolves
        # "opponents" from the raw "each opponent" text.
        ("Baba Lysaga, Night Witch", "opponents"),
        ("Vohar, Vodalian Desecrator", "opponents"),
        ("Faerie Tauntings", "opponents"),
    ],
)
def test_lifeloss_makers_degraded_typed_each_opponent(name, scope):
    idents = _idents(name)
    assert ("lifeloss_makers", scope, "") in idents
    assert ("lifeloss_makers", "each", "") not in idents


@pytest.mark.parametrize("name", ["Braids, Cabal Minion", "Smokestack"])
def test_edict_makers_symmetric_upkeep_scoped_each(name):
    """A triggered "at the beginning of each player's upkeep, that player sacrifices"
    edict (ScopedPlayer, no turn constraint) is SYMMETRIC — it hits YOU too, so it
    scopes /each, NOT the /opponents over-fire (CR 701.21a), matching the live lane."""
    idents = _idents(name)
    assert ("edict_makers", "opponents", "") not in idents  # the scope over-fire
    assert ("edict_makers", "each", "") in idents


def test_edict_makers_opponent_upkeep_scoped_opponents():
    """Sheoldred's "each opponent's upkeep, that player sacrifices" (ScopedPlayer +
    OnlyDuringOpponentsTurn) stays a real opponent edict — /opponents (CR 701.21a)."""
    assert ("edict_makers", "opponents", "") in _idents("Sheoldred, Whispering One")


@pytest.mark.parametrize("name", ["Smallpox", "Death Cloud"])
def test_edict_makers_symmetric_wrath_preserved(name):
    """A symmetric "each player sacrifices a creature" wrath (player_scope All) keeps
    firing /each — the genuine improvement (CR 701.21a)."""
    assert ("edict_makers", "each", "") in _idents(name)


# ── b3 recall (ADR-0034): trigger-wrapped forced-choice edicts the direct
#    opp/each arm missed — DefendingPlayer (Annihilator) and
#    ParentTargetController ("that permanent's controller sacrifices …").


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # Annihilator N — DefendingPlayer sacrifices N permanents of their choice
        # (CR 702.85a), a forced player-choice sac → /opponents.
        ("Breaker of Creation", "opponents"),
        # "Whenever a creature dies, that creature's controller sacrifices a land
        # of their choice" — ParentTargetController, symmetric → /each.
        ("Burning Sands", "each"),
    ],
)
def test_edict_makers_trigger_wrapped_forced_actor(name, scope):
    """A trigger-wrapped edict whose forced actor is the DefendingPlayer
    (Annihilator) or the ParentTargetController ("that … controller
    sacrifices") is a real player-choice sacrifice (CR 701.21a), scoped to
    match the live IR lane."""
    assert ("edict_makers", scope, "") in _idents(name)


def test_edict_makers_excludes_optional_bounce_downside():
    """Chain of Vapor's activated "that permanent's controller MAY sacrifice a
    land" is an OPTIONAL bounce rider, not a forced edict — the trigger-origin
    gate on ParentTargetController keeps it silent (CR 701.21a)."""
    assert "edict_makers" not in _keys("Chain of Vapor")


@pytest.mark.parametrize(
    "name",
    [
        "Yawning Fissure",  # [P1] "each opponent sacrifices a land" (filt You, scope Opp)
        "Din of the Fireherd",  # [P3] chained land sac after "target opponent ..."
    ],
)
def test_land_sacrifice_makers_excludes_opponent_land_edict(name):
    """An opponent land-EDICT (land destruction) is NOT a self land-sac engine — the
    lane reads the surrounding opponent scope past phase's [P1]/[P3] direction
    mislabels and excludes it (CR 701.21a)."""
    assert "land_sacrifice_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Zuran Orb",  # "Sacrifice a land:" — a you-sac cost
        "Smallpox",  # "each player ... sacrifices a land" — symmetric, you sac too
        "Death Cloud",  # symmetric X-land sac
    ],
)
def test_land_sacrifice_makers_self_and_symmetric_preserved(name):
    """A self / symmetric land sacrifice (you sac your own lands) still fires
    (CR 701.21 / 305.6)."""
    assert ("land_sacrifice_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Bile Blight", ("debuff_makers", "any", "")),  # negative Pump
        ("Black Sun's Zenith", ("debuff_makers", "any", "")),  # M1M1 on all creatures
        ("Humility", ("debuff_makers", "you", "")),  # mass base-toughness set ≤2
    ],
)
def test_debuff_makers_anchors(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize("name", ["Darksteel Mutation", "Glorious Anthem"])
def test_debuff_makers_excludes_single_aura_and_buff(name):
    """A single-Aura shrink (Darksteel Mutation — affected carries ``EnchantedBy``) is
    a neutralize, not a mass -1/-1 enabler; a positive anthem (Glorious Anthem) is a
    buff. Neither fires debuff_makers (CR 613.4c / checklist #6)."""
    assert "debuff_makers" not in _keys(name)


def test_lure_makers_fires():
    assert ("lure_makers", "you", "") in _idents("Lure")
    # Academic Dispute's single-target ForceBlock is a provoke-style effect, not the
    # all-creatures-must-block lure mode — must NOT fire.
    assert "lure_makers" not in _keys("Academic Dispute")


def test_lure_makers_must_be_blocked_idiom():
    """ADR-0038 W3 batch 3 (CR 509.1c/h): the "must be blocked ... if
    able" bucket-B idiom (``_LURE_MUST``, imported single-source from
    project.py's own card-level marker recovery) — Canopy Stalker's
    intrinsic "This creature must be blocked if able" phase drops to a
    bare Unimplemented clause."""
    assert ("lure_makers", "you", "") in _idents("Canopy Stalker")


def test_lure_makers_able_to_block_idiom():
    """ADR-0038 W3 batch 3 (CR 509.1c/h): the "able to block ... do so"
    bucket-B idiom (``_LURE_ABLE``) — Talruum Piper's "All creatures with
    flying able to block this creature do so."."""
    assert ("lure_makers", "you", "") in _idents("Talruum Piper")


def test_lure_makers_fires_on_the_lead_text_only_face_tree():
    """Destined // Lead — the Aftermath back half "Lead" has NO phase record
    (phase never emits aftermath second halves), so production coverage comes
    from the W2c text-only face tree ``trees_for`` synthesizes off the bulk
    face (task #76). This was the single card that blocked lure_makers'
    promotion in W3 batch 3: the wave's measurement harness predated
    ``trees_for`` and never saw the synthesized face. Reconstruct the tree
    via the production constructor and assert the ``_LURE_ABLE`` idiom reads
    it — "all creatures able to block ... do so" is a blocking requirement
    (CR 509.1c: "effects that say a creature must block")."""
    from mtg_utils._deck_forge._ir_lookup import _text_only_tree

    face = {
        "name": "Lead",
        "mana_cost": "{3}{G}",
        "type_line": "Sorcery",
        "oracle_text": (
            "Aftermath (Cast this spell only from your graveyard. "
            "Then exile it.)\n"
            "All creatures able to block target creature this turn do so."
        ),
    }
    tree = _text_only_tree(
        face, {"cmc": 6.0}, oracle_id="7ebde396-6672-491a-a6ce-1de49b12379b"
    )
    assert tree is not None
    assert tree.units == ()  # zero typed substrate — text idioms only
    idents = {
        (s.key, s.scope, s.subject)
        for s in extract_crosswalk_signals(tree, keywords=frozenset())
    }
    assert ("lure_makers", "you", "") in idents


def test_copy_permanent_and_clone():
    # Crystalline Resonance copies a Permanent → copy_permanent + clone_makers.
    idents = _idents("Crystalline Resonance")
    assert ("copy_permanent", "you", "") in idents
    assert ("clone_makers", "you", "") in idents


@pytest.mark.parametrize("name", ["Clone", "Spark Double"])
def test_clone_makers_fires(name):
    assert ("clone_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 (CR 707.2) — a BecomeCopy back-reference target
        # recovered via THIS SAME unit's other concept's own structured subject
        # words: Dimir Doppelganger's Exile-target Creature filter
        # (``ParentTarget``); Brudiclad's created-token types (a bare
        # ``ParentTarget`` whose sibling ``make_token`` carries the type);
        # Curie's exiled-artifact-creature cost (``TrackedSet``, recovered via
        # the clause's own "copy of <type>" text since the top-level Composite
        # cost carries no top-level filter).
        "Dimir Doppelganger",
        "Brudiclad, Telchor Engineer",
        "Curie, Emergent Intelligence",
        # The clause's own "copy of <type>" text (Cytoshape's sibling "choose a
        # nonlegendary creature" clause carries no filter at all, but the
        # BecomeCopy's OWN unit description literally says "copy of that
        # CREATURE").
        "Cytoshape",
        # The trigger's OWN watched-object filter, read via
        # :func:`~mtg_utils._card_ir.crosswalk.trigger_subject` when the copy has
        # no sibling EFFECT to borrow from (Sarkhan's "a Dragon you control
        # enters" trigger).
        "Sarkhan, Soul Aflame",
        # A sibling STRUCTURED filter takes priority over the whole-unit "copy
        # of <type>" text scan — Dermotaxi's tap-cost Creature filter recovers
        # the RIGHT answer where the text scan would find the WRONG one (the
        # "except it's a Vehicle artifact in addition to its other types" rider
        # falls inside the text-scan's 60-char window and would misclassify the
        # copy as Artifact).
        "Dermotaxi",
        # A core-type word literally named in a sibling's own raw clause text
        # (Kaya's Unimplemented "choose a CREATURE CARD from among them" — no
        # structured filter, no "copy of <type>" text, only the sibling's own
        # raw wording).
        "Kaya, Spirits' Justice",
        # A core-type word ANYWHERE in this SAME unit's own description, when
        # the qualifier PRECEDES "copy of" instead of following it (Vesuvan
        # Drifter's "If you reveal a CREATURE card this way, ~ becomes a copy
        # of THAT CARD").
        "Vesuvan Drifter",
        # A BecomeCopy BURIED inside a granted ability's own quoted definition
        # (Shameless Charlatan — "Commander creatures you own have '{2}{U}:
        # This creature becomes a copy of another target creature.'"), reached
        # by descending the unit's own ``GrantAbility`` static concept.
        "Shameless Charlatan",
        # A bare "Card" sibling filter (no permanent-type info) is excluded so
        # a LATER, more specific tier gets a chance — Lazav, Familiar
        # Stranger's "exile A CARD from a graveyard" sibling would otherwise
        # mask the unit description's own "If a CREATURE card was exiled".
        "Lazav, Familiar Stranger",
        # The true last resort: a core-type word ANYWHERE in the whole-card
        # oracle, reached only when every unit-scoped tier fails (Volatile
        # Chimera — the "creature cards you drafted" qualifier lives on a
        # WHOLLY SEPARATE deckbuilding ability, cross-unit). Safe because it is
        # gated behind a real structural ``BecomeCopy`` node already existing.
        "Volatile Chimera",
    ],
)
def test_clone_makers_backref_recovery_arms(name):
    assert ("clone_makers", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (CR 707.2 general copy-effect rule / CR 707.5
        # "enters ... as a copy" become-a-copy-as-it-enters rule): all five are
        # phase static-parser failures that emit NO ``BecomeCopy`` node at
        # all — a ``Static pattern matched but line failed static parser``
        # or bare ``unknown`` Unimplemented clause, never a mis-typed node
        # ``_clone_copied_words`` could descend into. The bucket-B
        # ``_clone_text_idiom`` per-clause text scan (:func:`_copy_clone`'s
        # last-resort fallback) reads the idiom straight off the reminder-
        # stripped face oracle.
        "Vesuvan Shapeshifter",
        "Shapeshifter's Marrow",
        "Essence of the Wild",
        "Metamorphic Alteration",
        "The Fourteenth Doctor",
        # Blade of Shared Souls (CR 707.2): "you may have that creature
        # become a copy of another target creature you control" phase-parses
        # as an ``Unimplemented`` clause (``name='have'``) — same bucket-B
        # class as the five above; corpus re-measure (2026-07) confirms 0
        # genuine clone_makers members lost, so this card is no longer a
        # deferred parser gap.
        "Blade of Shared Souls",
        # Ludevic, Necrogenius's TRANSFORM back face: "As this creature
        # transforms into Olag, Ludevic's Hubris, it becomes a copy of a
        # creature card exiled with it..." has no BecomeCopy node ANYWHERE
        # on the back face (a bare ``unknown`` Unimplemented Spell-kind
        # ability, not even a static) — the text idiom is the only signal.
        "Olag, Ludevic's Hubris",
    ],
)
def test_clone_makers_text_idiom_bridge(name):
    assert ("clone_makers", "you", "") in _idents(name)


def test_clone_makers_text_idiom_beyond_legacy_gain():
    """Dinosaur Headdress (Paleontologist's Pick-Axe's craft-transform back
    face): "Equipped creature is a copy of the last chosen card" is a
    genuine CR 707.2 clone effect the legacy regex-mirror never covered
    either (corpus-verified 2026-07: legacy ``old_ir_for`` also misses this
    card) — an adjudicated crosswalk-only GAIN via the same text-idiom
    bridge, not an over-fire class."""
    assert ("clone_makers", "you", "") in _idents("Dinosaur Headdress")


@pytest.mark.parametrize("name", ["Twincast", "Mirror Match"])
def test_clone_makers_excludes_spell_and_token_copy(name):
    """A spell-copy (Twincast) and a token-copy (Mirror Match — a
    ``CopyTokenBlockingAttacker``) are NOT creature clones (Dan's clone-vs-token-copy
    boundary, CR 707.1)."""
    assert "clone_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 — the text-idiom bridge's per-CLAUSE exclusion
        # gates (boundary lesson (iii)): "create a TOKEN that's a copy of ~"
        # is the token_copy_makers structural surface (``CopyTokenOf``), a
        # different lane entirely, and must NOT also fire clone_makers.
        "Dance of Many",
        "Splitting Slime",
        "Dual Nature",
        "Theoretical Duplication",
        # Echoing Deeps copies a LAND card, not a Permanent/Creature — the
        # idiom's "land card" per-clause exclusion (legacy agrees this
        # isn't clone_makers).
        "Echoing Deeps",
    ],
)
def test_clone_makers_text_idiom_excludes_token_and_land_copy(name):
    assert "clone_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    ["Cackling Counterpart", "Trostani, Selesnya's Voice", "Mirror Match"],
)
def test_token_copy_makers_fires(name):
    assert ("token_copy_makers", "you", "") in _idents(name)


def test_token_copy_makers_excludes_selfref_self_copy():
    """Adorned Pouncer's Eternalize self-copy is a ``CopyTokenOf`` with a ``SelfRef``
    target (a copy of THIS card, not a copy-others payoff) — must NOT fire (CR 707)."""
    assert "token_copy_makers" not in _keys("Adorned Pouncer")


def test_connive_makers_fires():
    assert ("connive_makers", "you", "") in _idents("Hypnotic Grifter")


def test_explore_makers_structural_only_excludes_payoff():
    assert ("explore_makers", "you", "") in _idents("Merfolk Branchwalker")
    # Wildgrowth Walker is an explore PAYOFF ("whenever a creature you control
    # explores") with NO Explore effect — only a watch-trigger. Read structurally, it
    # must NOT fire, even though its Scryfall keyword array carries "Explore" (the
    # keyword field-lookup would over-fire — CR 701.44a).
    assert "explore_makers" not in _keys("Wildgrowth Walker")


def test_suspect_makers_fires():
    assert ("suspect_makers", "you", "") in _idents("Nelly Borca, Impulsive Accuser")


@pytest.mark.parametrize("name", ["Coastal Piracy", "Bident of Thassa"])
def test_combat_damage_to_opp_fires(name):
    assert ("combat_damage_to_opp", "opponents", "") in _idents(name)


def test_combat_damage_to_opp_excludes_damage_to_you():
    """Contested War Zone triggers on combat damage dealt to YOU (``valid_target:
    Controller``) — a defensive trigger, not the aggressive lane (CR 510.1c)."""
    assert "combat_damage_to_opp" not in _keys("Contested War Zone")


def test_graveyard_makers_structural_and_keyword():
    # Reanimate: a ChangeZone (Graveyard, Battlefield), scope you (the recursion
    # target carries no controller — the self-graveyard default, NOT opponents).
    assert ("graveyard_makers", "you", "") in _idents("Reanimate")
    # Faithless Looting: the Flashback keyword field-lookup.
    assert ("graveyard_makers", "you", "") in _idents("Faithless Looting")
    # Stitcher's Supplier: a Mill effect with destination Graveyard (self-mill).
    assert ("graveyard_makers", "you", "") in _idents("Stitcher's Supplier")


@pytest.mark.parametrize("name", ["Scroll Rack", "Banisher Priest"])
def test_graveyard_makers_excludes_mislabels(name):
    """A library↔hand swap phase MISLABELS as ``Mill`` with destination=Hand (Scroll
    Rack) and an exile-return reanimate has origin=Exile (Banisher Priest) — neither is
    a graveyard interaction (CR 701.17a / 603.6e); the dest/origin reads exclude them.
    """
    assert "graveyard_makers" not in _keys(name)


def test_graveyard_matters_keyword():
    # Stinkweed Imp carries the Dredge keyword → graveyard_matters.
    assert ("graveyard_matters", "you", "") in _idents("Stinkweed Imp")


# ── Batch 5: the named-mechanic long tail (ADR-0035 Stage 2) ──────────────────


def test_monarch_makers_and_matters_split():
    """A ``BecomeMonarch`` doer (Azure Fleet Admiral) fires makers; an ``IsMonarch``
    payoff condition (Throne Warden) fires matters ONLY — the maker/payoff split
    (CR 725)."""
    assert ("monarch_makers", "you", "") in _idents("Azure Fleet Admiral")
    assert "monarch_matters" not in _keys("Azure Fleet Admiral")
    assert ("monarch_matters", "you", "") in _idents("Throne Warden")
    assert "monarch_makers" not in _keys("Throne Warden")


def test_monarch_makers_phase_drops_opponent_direction():
    """phase carries a BARE ``BecomeMonarch`` for "target opponent becomes the
    monarch" (Jared Carthalion) — it drops the give-away direction, so the lane
    fires you, MATCHING the live ``monarch`` doer's identical limitation (a shared
    phase gap, documented, not a crosswalk over-fire)."""
    assert ("monarch_makers", "you", "") in _idents("Jared Carthalion, True Heir")


def test_discover_makers_structural():
    """A ``Discover`` effect (Geological Appraiser) fires structurally (CR 701.57)."""
    assert ("discover_makers", "you", "") in _idents("Geological Appraiser")


@pytest.mark.parametrize("name", ["Bar the Gate", "Avenging Hunter"])
def test_venture_makers_fires(name):
    """A ``VentureIntoDungeon`` (Bar the Gate) / ``TakeTheInitiative`` (Avenging
    Hunter) doer fires venture_makers (CR 701.49 / the Initiative)."""
    assert ("venture_makers", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Gloom Stalker", "Imoen, Mystic Trickster"])
def test_venture_matters_is_condition_only(name):
    """A ``CompletedADungeon`` (Gloom Stalker) / ``IsInitiative`` (Imoen) payoff
    condition fires venture_matters — and NOT makers (no venture effect)."""
    assert ("venture_matters", "you", "") in _idents(name)
    assert "venture_makers" not in _keys(name)


def test_daynight_makers_vs_matters_keyword():
    """A ``SetDayNight`` doer (Brimstone Vandal) fires makers (CR 731); a daybound
    werewolf (Reckless Stormseeker — the keyword PAYOFF) fires matters via the
    keyword field-lookup and NOT makers (no SetDayNight effect)."""
    assert ("daynight_makers", "you", "") in _idents("Brimstone Vandal")
    assert "daynight_matters" not in _keys("Brimstone Vandal")
    assert ("daynight_matters", "you", "") in _idents("Reckless Stormseeker")
    assert "daynight_makers" not in _keys("Reckless Stormseeker")


@pytest.mark.parametrize("name", ["Blink Dog", "Divine Smite"])
def test_phasing_makers_blanket_both_directions(name):
    """phasing_makers is a BLANKET maker (matching the live undirected doer): a self
    phase-out (Blink Dog — protection) and an opponent-directed phase-out (Divine
    Smite — denial) both fire you (CR 702.26)."""
    assert ("phasing_makers", "you", "") in _idents(name)


def test_phasing_makers_keyword_field_lookup():
    """ADR-0037/0038 W3: the printed Phasing KEYWORD (CR 702.26a) carries NO
    effect node at all — Breezekeeper is keywords=["Flying", "Phasing"] with
    zero abilities/triggers/statics, so the structural ``PhaseOut``/
    ``PhaseIn`` effect-node read never reaches it; a keyword-field lookup
    does."""
    assert ("phasing_makers", "you", "") in _idents("Breezekeeper")


def test_phasing_makers_grammar_recovery_and_trigger_mode_payoff():
    """ADR-0037/0038 W3: Dream Fighter's "~ and that creature phase out" is a
    genuine Unimplemented residue the shared clause grammar's "phase(s)
    in/out" verb idiom recovers to the native ``phasing`` concept (CR
    702.26a). The War Doctor's "Whenever one or more other permanents phase
    out, put a time counter on ~" is a WATCHER, not a doer — legacy's OWN
    project.py deliberately treats this as phasing_makers too (a "phasing
    payoff marker"), reproduced via phase's native ``PhaseOut`` TRIGGER
    MODE (normalizes trigger_event to "phaseout")."""
    assert ("phasing_makers", "you", "") in _idents("Dream Fighter")
    assert ("phasing_makers", "you", "") in _idents("The War Doctor")


def test_phasing_makers_combat_phase_noun_no_fire():
    """ADR-0037/0038 W3: "attacks during its controller's next combat PHASE"
    (Trench Behemoth) is a phase-of-the-TURN noun, never the CR 702.26a
    "phase(s) in/out" verb idiom — the grammar's phasing token requires the
    immediate next word be "in"/"out" precisely to keep this OFF (a
    corpus-verified over-fire class a bare "phase" keyword match once
    caught)."""
    assert "phasing_makers" not in _keys("Trench Behemoth")


@pytest.mark.parametrize("name", ["Equipoise", "Spectral Adversary"])
def test_phasing_makers_then_compound_clause_grammar_recovery(name):
    """ADR-0038 deferral sweep: a COMPOUND "..., then ... phase(s) out"
    clause anchors ``parse_clause`` on its leading verb (Equipoise —
    choose; Spectral Adversary — put counters), a real match that would
    short-circuit dispatch before the phasing idiom is ever seen; the
    ``_THEN_PHASING`` grammar arm (tried first) recognizes the CR 702.26a
    idiom in the literal-"then" continuation instead."""
    assert ("phasing_makers", "you", "") in _idents(name)


def test_phasing_makers_flip_coin_branch_descent():
    """ADR-0038 deferral sweep: Frenetic Efreet's ``PhaseOut`` lives NESTED
    inside the ``FlipCoin`` node's ``win_effect`` branch — never a
    top-level unit effect, so the per-unit ``effect_concepts`` walk misses
    it; :func:`iter_typed_nodes`'s generic deep walk reaches it (CR
    702.26, the Dementia Sliver grant-descent precedent)."""
    assert ("phasing_makers", "you", "") in _idents("Frenetic Efreet")


def test_phasing_makers_no_residue_text_fallback():
    """ADR-0038 deferral sweep: phase drops Perch Protection's WHOLE "if
    the gift was promised, all permanents you control phase out" segment —
    no ``PhaseOut`` node, no Unimplemented raw anywhere in the tree — so
    the last-resort CR 702.26a idiom match over the reminder-stripped
    oracle (:func:`_kept`) is the only read that can reach it. The
    reminder strip is load-bearing: a card that merely GRANTS the Phasing
    keyword carries the identical "phases in or out" idiom in its CR
    702.26a REMINDER text (Cloak of Invisibility), and legacy never fires
    granters."""
    assert ("phasing_makers", "you", "") in _idents("Perch Protection")
    assert "phasing_makers" not in _keys("Cloak of Invisibility")


def test_voting_makers_allplayers_gate_excludes_friend_or_foe():
    """A council/dilemma vote (Coercive Portal — ``voter_scope: AllPlayers``) fires
    voting_makers /each (CR 701.38); phase OVER-TAGS Battlebond "choose friend or
    foe" (Khorvath's Fury — ``voter_scope: ControllerLabels``) as ``Vote`` too, and
    the AllPlayers gate excludes it STRUCTURALLY (a clean improvement over the live
    raw-idiom guard)."""
    assert ("voting_makers", "each", "") in _idents("Coercive Portal")
    assert "voting_makers" not in _keys("Khorvath's Fury")


def test_ring_tempters_and_matters_split():
    """A ``RingTemptsYou`` doer (Boromir) fires ring_tempters; a buried
    ``IsRingBearer`` payoff condition with NO tempt trigger (Sauron, the Necromancer)
    fires ring_matters structurally — neither leaks into the other (CR 701.54)."""
    assert ("ring_tempters", "you", "") in _idents("Boromir, Warden of the Tower")
    assert "ring_matters" not in _keys("Boromir, Warden of the Tower")
    assert ("ring_matters", "you", "") in _idents("Sauron, the Necromancer")
    assert "ring_tempters" not in _keys("Sauron, the Necromancer")


def test_ring_matters_trigger_event_payoff():
    """ADR-0038 W1 batch-4: a top-level trigger whose event is
    ``RingTemptsYou`` (CR 701.54d "Whenever the Ring tempts you") is a
    payoff for ANY tempt, including one from a DIFFERENT card — Nazgûl
    fires BOTH ring_tempters (its own ETB tempt) AND ring_matters (its
    "Whenever the Ring tempts you, put a +1/+1 counter on each Wraith"
    payoff trigger)."""
    assert ("ring_tempters", "you", "") in _idents("Nazgûl")
    assert ("ring_matters", "you", "") in _idents("Nazgûl")


def test_ring_matters_ring_bearer_text_fallback():
    """A whole-card "Ring-bearer" reference the flat condition-tag walk
    doesn't reach — mirrors legacy's own raw-text discriminator (a
    SANCTIONED byte-identical mirror for this half): Call of the Ring's
    "whenever you choose a creature as your Ring-bearer" (no IsRingBearer
    condition node) and Dúnedain Rangers' "if you don't control a
    Ring-bearer" (a gating condition on the maker's OWN tempt trigger,
    not a separate payoff clause — still fires per legacy's own broad
    match, CR 701.54)."""
    assert ("ring_matters", "you", "") in _idents("Call of the Ring")
    assert ("ring_matters", "you", "") in _idents("Dúnedain Rangers")


def test_ring_matters_improvements_over_legacy_text_bug():
    """Two genuine crosswalk-side improvements (not shed): Ringwraiths'
    "When the Ring tempts you, return this card from your graveyard" is
    the SAME payoff shape as Nazgûl's, but legacy's own raw-text check
    requires the literal word "whenever" (it misses "When ...") — a
    legacy text-matching bug, not a deliberate doer/payoff distinction.
    One Ring to Rule Them All's Saga chapter I ("The Ring tempts you,
    then each player mills cards equal to your Ring-bearer's power")
    scales off the Ring-bearer's power — an unambiguous payoff legacy
    misses because phase splits the tempt and the mill into separate
    effect nodes, so neither one's own raw carries both "ring tempts
    you" and "ring-bearer" together; the whole-card scan reads them
    regardless of how phase split the clause."""
    assert ("ring_matters", "you", "") in _idents("Ringwraiths")
    assert ("ring_matters", "you", "") in _idents("One Ring to Rule Them All")


def test_amass_makers_new_lane():
    """An ``Amass`` effect (Aven Eternal) fires the new amass_makers lane (CR
    701.47)."""
    assert ("amass_makers", "you", "") in _idents("Aven Eternal")


def test_incubate_makers_new_lane():
    """An ``Incubate`` effect (Brimaz, Blight of Oreskos) fires the new
    incubate_makers lane (CR 701.53)."""
    assert ("incubate_makers", "you", "") in _idents("Brimaz, Blight of Oreskos")


@pytest.mark.parametrize("name", ["Cloudform", "Cryptic Coat"])
def test_facedown_makers_fires(name):
    """A ``Manifest`` (Cloudform) / ``Cloak`` (Cryptic Coat) doer fires
    facedown_makers (CR 701.40 / 701.58 / 708)."""
    assert ("facedown_makers", "you", "") in _idents(name)


def test_facedown_makers_morph_keyword():
    """A morph body (Abzan Guide) is CAST face down via the printed keyword and
    carries NO Manifest/Cloak effect — the Scryfall keyword field-lookup is the
    uniform anchor over morph/megamorph/disguise/manifest-dread (CR 708 / 702.37)."""
    assert ("facedown_makers", "you", "") in _idents("Abzan Guide")


def test_facedown_makers_excludes_facedown_predicate():
    """Dream Chisel carries a ``FaceDown`` filter PREDICATE ("face-down creature
    spells you cast cost less") but no Manifest/Cloak effect — the cares-about state
    is NOT a maker (CR 708)."""
    assert "facedown_makers" not in _keys("Dream Chisel")


def test_dice_makers_fires():
    """A ``RollDie`` effect (Adorable Kitten) fires dice_makers (CR 706)."""
    assert ("dice_makers", "you", "") in _idents("Adorable Kitten")


def test_dice_makers_recovers_spell_form_roll():
    """ADR-0038 recovery: "Roll two d6 and choose one result" lands in phase
    as an Unimplemented effect (the SPELL/COST form of a die roll, distinct
    from the native ``RollDie`` doer node); the shared grammar's "roll_die"
    token re-decorates it so dice_makers fires (CR 706)."""
    assert ("dice_makers", "you", "") in _idents("Valiant Endeavor")


def test_dice_makers_fires_roll_to_visit_attractions():
    """Command Performance's "Roll to visit your Attractions" is phase's
    ``RollToVisitAttractions`` tag — a DISTINCT node from ``RollDie`` but the
    same CR 706 die-roll action per CR 701.52a ("roll a six-sided die …");
    the concept-map maps it straight to "roll_die"."""
    assert ("dice_makers", "you", "") in _idents("Command Performance")


def test_dice_makers_nested_composite_cost():
    """Clay Golem's "{6}, Roll a d8: Monstrosity X" carries a REAL nested
    ``RollDie`` node inside its ``Composite`` cost's ``EffectCost`` — not
    surfaced as its own flat concept-node (the cost decorates as one opaque
    ``Composite`` node). ``has_structural_dice_makers``'s nested fallback
    (:func:`has_nested_roll_die`) reaches it (CR 706)."""
    assert ("dice_makers", "you", "") in _idents("Clay Golem")


def test_dice_makers_nested_granted_ability():
    """Captain Rex Nebula's "Crash Land" grant carries a REAL nested
    ``RollDie`` node inside the ``GrantAbility`` definition's chained
    ``sub_ability`` — not surfaced as its own flat concept-node (the grant
    decorates as one opaque node with no raw). The structural nested
    fallback reaches it (CR 706)."""
    assert ("dice_makers", "you", "") in _idents("Captain Rex Nebula")


def test_dice_makers_excludes_dice_reference_shape():
    """ADR-0034 shed: Pixie Guide's "Grant an Advantage — If you would roll
    one or more dice, instead roll that many dice plus one and ignore the
    lowest roll." is a REPLACEMENT modifying an EXISTING/future roll, not an
    instruction to roll — the grammar's cursor-anchored parse lands on the
    "instead roll" remainder, matching the SAME dice-REFERENCE shape the
    old-IR's ``_DICE_TRIG`` discriminator routes to dice_matters (never
    dice_makers). The recovery guard reuses ``_DICE_TRIG`` verbatim so this
    stays unrecovered (CR 706, CR 614 replacement effects)."""
    assert "dice_makers" not in _keys("Pixie Guide")


def test_dice_makers_reroll_only_synthesis():
    """Stage-A synthesis (ADR-0037/0038): Monitor Monitor's "Once each turn,
    you may pay {1} to reroll one or more dice you rolled." carries NO
    ``RollDie`` node anywhere (nested or flat) — a genuine no-residue gap.
    CR 706.8b: rerolling a stored result IS rolling that die again
    ("roll one of the kind of die noted for each of them"), so
    ``tree_synthesis._arm_dice_makers`` fills the gap from ``tree.oracle``,
    emitting the REAL "roll_die" concept."""
    assert ("dice_makers", "you", "") in _idents("Monitor Monitor")


def test_coin_flip_recovers_flip_fixing_static():
    """ADR-0038 recovery: Edgar, King of Figaro's "Two-Headed Coin — The
    first time you flip one or more coins each turn, those coins come up
    heads and you win those flips." lands as an Unimplemented node with no
    SIMPLE_VERB "flip" arm; the shared grammar's STATIC_TOKENS "coin_flip"
    row re-decorates it to the native "flip_coin" concept (CR 705.3)."""
    assert ("coin_flip", "you", "") in _idents("Edgar, King of Figaro")


def test_coin_flip_recovers_modal_etb_flip():
    """ADR-0038 recovery: Molten Sentry's "As ~ enters, flip a coin. If the
    coin comes up heads, ..." lands as an Unimplemented node; the STATIC_
    TOKENS "coin_flip" row re-decorates it (CR 705.1)."""
    assert ("coin_flip", "you", "") in _idents("Molten Sentry")


def test_coin_flip_nested_granted_ability():
    """Frenetic Sliver's "All Slivers have '{0}: ... flip a coin ...'"
    carries a REAL nested ``FlipCoin`` node inside the ``GrantAbility``
    definition — not surfaced as its own flat concept-node (the grant
    decorates as one opaque node). The structural nested fallback
    (:func:`has_nested_flip_coin`) reaches it (CR 705.1)."""
    assert ("coin_flip", "you", "") in _idents("Frenetic Sliver")


def test_coin_flip_payoff_synthesis_win_loss_trigger():
    """Stage-A synthesis (ADR-0037/0038): Chance Encounter's "Whenever you
    win a coin flip, put a luck counter..." trigger CONDITION phase
    flattens to event='other', leaving no FlipCoin node at all. Legacy's
    own ``coin_flip`` category conflates doer + this payoff
    (``_sweep_detectors`` labels it "coin-flip payoffs plus flip-fixing"),
    so ``tree_synthesis._arm_coin_flip_payoff`` fills the gap from
    ``tree.oracle``, emitting the REAL "flip_coin" concept (CR 705.2)."""
    assert ("coin_flip", "you", "") in _idents("Chance Encounter")


def test_coin_flip_payoff_synthesis_win_and_lose_triggers():
    """Karplusan Minotaur's cumulative-upkeep "Flip a coin" cost payment
    leaves no residue at all, but its "Whenever you win/lose a coin flip,
    ~ deals 1 damage..." payoff triggers are caught by the SAME synthesis
    arm as Chance Encounter (CR 705.2)."""
    assert ("coin_flip", "you", "") in _idents("Karplusan Minotaur")


def test_connive_makers_nested_granted_trigger_aura():
    """Security Bypass's "Enchanted creature has 'Whenever this creature
    deals combat damage to a player, it connives.'" carries a REAL nested
    ``Connive`` node inside the static ability's ``GrantTrigger``
    modification — not surfaced as its own flat concept-node (the grant
    decorates as one opaque node). The ``iter_nested_trigger_defs`` shared
    descent (:func:`has_nested_connive`) reaches it (CR 701.50a)."""
    assert ("connive_makers", "you", "") in _idents("Security Bypass")


def test_connive_makers_nested_granted_trigger_copy_exception():
    """Copycrook's "You may have this creature enter as a copy of any
    creature ..., except it has 'Whenever this creature attacks, it
    connives.'" carries the SAME nested ``GrantTrigger``/``Connive`` shape
    as Security Bypass, but buried inside a ``BecomeCopy`` replacement's
    ``additional_modifications`` rather than a static's ``modifications``
    — the shared descent walks both (CR 701.50a)."""
    assert ("connive_makers", "you", "") in _idents("Copycrook")


def test_connive_makers_no_residue_synthesis():
    """Stage-A synthesis (ADR-0037/0038): Unstable Experiment's "Target
    player draws a card, then up to one target creature you control
    connives." — phase parses only the ``Draw`` half; the "then ... target
    creature ... connives" clause drops entirely (``sub_ability = None``,
    no node at all). ``tree_synthesis._arm_connive_makers`` fills the gap
    from ``tree.oracle``, emitting the REAL "connive" concept (CR
    701.50a)."""
    assert ("connive_makers", "you", "") in _idents("Unstable Experiment")


@pytest.mark.parametrize("name", ["Glorious Purpose", "Iron Monger, Sadistic Tycoon"])
def test_connive_makers_excludes_connive_state_payoff(name):
    """ADR-0034 shed: "Whenever a creature you control connives, ..." is a
    connive-STATE PAYOFF watching for OTHER creatures' connive action, not
    an instruction TO a permanent (CR 701.50a: "Certain spells and
    abilities instruct a permanent to connive"). Legacy's Scryfall
    ``connive`` keyword-field lookup over-fires on both cards (the keyword
    tags any card that MENTIONS the mechanic, doer or payoff alike); the
    structural read stays doer-only by construction, so connive_makers
    correctly never fires here — the payoff belongs to a separate key."""
    assert "connive_makers" not in _keys(name)


@pytest.mark.parametrize("name", ["Act on Impulse", "Aloe Alchemist"])
def test_cast_from_exile_structural_permission(name):
    """A ``GrantCastingPermission`` whose permission is ``PlayFromExile`` (Act on
    Impulse — impulse exile-and-play) or ``Plotted`` (Aloe Alchemist — plot) fires
    cast_from_exile STRUCTURALLY (the batch's marquee fidelity gain over the live
    word-mirror; CR 116 / 702.170)."""
    assert ("cast_from_exile", "you", "") in _idents(name)


def test_cast_from_exile_excludes_plain_exile_removal():
    """Path to Exile is an ``Exile`` REMOVAL with no play permission — not a
    cast-from-exile build-around (CR 406)."""
    assert "cast_from_exile" not in _keys("Path to Exile")


@pytest.mark.parametrize(
    "name",
    ["Gonti, Lord of Luxury", "Territorial Bruntar"],
)
def test_cast_from_exile_dig_and_reveal_until_evidence(name):
    """ADR-0038 W3 batch 5: a ``PlayFromExile`` grant reads exile-zone
    evidence from a ``Dig`` effect with ``destination == "Exile"`` (Gonti's
    "look at the top four... exile one of them face down") or an
    ``ExileFromTopUntil`` node (Territorial Bruntar's "exile cards from the
    top of your library until you exile a nonland card") preceding it in the
    SAME unit — :func:`_cast_from_exile_unit_evidence`. CR 406.1 / 601.2."""
    assert ("cast_from_exile", "you", "") in _idents(name)


def test_cast_from_exile_cost_evidence():
    """ADR-0038 W3 batch 5: Primordial Mist's activated ability pays its OWN
    exile as the COST (``EffectCost`` wrapping a ``ChangeZone{destination:
    Exile}``) — "Exile a face-down permanent you control face up: You may
    play that card this turn." Cost-role evidence counts (paid before the
    grant resolves). CR 406.1 / 601.2."""
    assert ("cast_from_exile", "you", "") in _idents("Primordial Mist")


def test_cast_from_exile_cross_unit_evidence():
    """ADR-0038 W3 batch 5: Muse Vessel splits exile-then-cast across TWO
    activated abilities — "{3}, {T}: Target player exiles a card from their
    hand." (a ``ChangeZone{Exile}`` with no grant of its own) and "{1}:
    Choose a card exiled with ~. You may play that card this turn." (the
    grant, with no local exile producer). :func:`_cast_from_exile` scans
    every unit of the FACE, not just the grant's own unit, so the artifact's
    shared exile pool still counts. CR 406.1 / 601.2."""
    assert ("cast_from_exile", "you", "") in _idents("Muse Vessel")


@pytest.mark.parametrize("name", ["Vega, the Watcher", "Misthollow Griffin"])
def test_cast_from_exile_text_idiom_fallback(name):
    """ADR-0038 W3 batch 5 — bucket-d text-idiom fallback: Vega's payoff
    Trigger carries ``spell_cast_origin: NotEquals(Hand)`` with NO exile
    zone attached structurally ("Whenever you cast a spell from anywhere
    other than your hand, draw a card."), and Misthollow Griffin's self-cast
    permission is a bare ``CastFromZone`` effect with no zone at all
    ("You may cast this card from exile."). Both are read via
    :func:`mtg_utils._card_ir.supplement._CAST_FROM_EXILE_P` against
    ``tree.oracle`` — the SAME word-grammar the OLD projection's
    ``_recover_cast_from_exile_zone`` already ran against this exact text
    (not new grammar growth). Deliberately NOT read as a bare
    ``CastFromZone``-presence structural arm: that node is reused for
    graveyard-cast grants too (Yawgmoth's Will, Snapcaster Mage) and would
    flood the lane. CR 406.1 / 601.3b."""
    assert ("cast_from_exile", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Ark of Hunger", "Skyclave Shade", "Mission Briefing"],
)
def test_cast_from_exile_excludes_graveyard_sourced_grants(name):
    """ADR-0038 W3 batch 5 sheds — phase emits the SAME ``PlayFromExile``
    permission tag for a handful of cast-from-GRAVEYARD abilities that share
    the "you may cast/play it [later]" shape as a genuine exile grant, a
    real zone-fidelity gap in the substrate (not fixable from here without
    clause-grammar growth; CR 702.34 Flashback governs the graveyard zone,
    not CR 406):

    * Ark of Hunger — ``{T}: Mill a card. You may play that card this
      turn.`` (``Mill`` destination Graveyard, no exile anywhere).
    * Skyclave Shade — ``...if this card is in your graveyard and it's your
      turn, you may cast it from your graveyard this turn.`` (a dies-rider
      cast-from-graveyard permission, textually named "graveyard").
    * Mission Briefing — ``Surveil 2, then choose an instant or sorcery card
      in your graveyard. You may cast it this turn. If that spell would be
      put into your graveyard, exile it instead.`` — the ``ChangeZone{Exile}``
      sibling is a POST-cast redirect (it appears AFTER the grant in the
      unit's effect order), not the source zone; the card the grant lets you
      cast is chosen FROM the graveyard.
    """
    assert "cast_from_exile" not in _keys(name)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Behold the Multiverse", "foretell_makers"),
        ("Bituminous Blast", "cascade_makers"),
        ("Ancestral Vision", "suspend_makers"),
    ],
)
def test_keyword_makers_field_lookup(name, key):
    """foretell / cascade / suspend have NO typed effect tag — they ride the Scryfall
    keyword array field-lookup (CR 702.143 / 702.85 / 702.62)."""
    assert (key, "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Plague Stinger", "Bloated Contaminator"])
def test_poison_makers_keyword(name):
    """infect (Plague Stinger) / toxic (Bloated Contaminator) → poison_makers
    opponents (the poison-counter dealers, CR 702.90 / 702.164)."""
    assert ("poison_makers", "opponents", "") in _idents(name)


def test_poison_makers_excludes_corrupted_payoff():
    """Apostle of Invasion carries an ``OpponentPoisonAtLeast`` Corrupted PAYOFF
    condition but no infect/toxic/poisonous keyword — it CARES about poison, it does
    not DEAL it (CR 702.90)."""
    assert "poison_makers" not in _keys("Apostle of Invasion")


@pytest.mark.parametrize("name", ["Pit Scorpion", "Marsh Viper"])
def test_poison_makers_direct_give_player_counter(name):
    """ADR-0038 W3 batch 4: a direct ``GivePlayerCounter(poison)`` DOER with NO
    infect/toxic/poisonous keyword at all ("that player gets a poison
    counter") — the keyword-array arm can't reach it; ``_PLAYER_COUNTER_
    MAKER["poison"]`` does (CR 120.3b / 104.3d)."""
    assert ("poison_makers", "opponents", "") in _idents(name)


def test_poison_makers_word_mirror_granted_keyword():
    """Corrupted Conscience GRANTS infect to the enchanted creature ("Enchanted
    creature has infect") — a different object than the Aura's own Scryfall
    keyword array, so the keyword-bearer arm misses it; the whole-card
    ``_POISON_WORD_MIRROR`` (a SANCTIONED byte-identical mirror of legacy's own
    poison_makers word regex) recovers it (CR 702.90)."""
    assert ("poison_makers", "opponents", "") in _idents("Corrupted Conscience")


@pytest.mark.parametrize("name", ["Serpent Generator", "Ajani, Sleeper Agent"])
def test_poison_makers_nested_giver_in_created_object(name):
    """A poison ``GivePlayerCounter`` buried inside a CreateToken's own token
    definition (Serpent Generator's Snake token: "Whenever this creature
    deals damage to a player, that player gets a poison counter.") or a
    CreateEmblem's granted trigger (Ajani, Sleeper Agent's ultimate emblem:
    "target opponent gets two poison counters.") — the top-level
    ``effect_concepts`` walk only sees the CreateToken/CreateEmblem effect
    itself; :func:`iter_typed_nodes`'s deep walk reaches the nested giver
    (CR 111.7 token copiable values / CR 114.1 emblems). Ajani is an
    ADJUDICATED GAIN over legacy: the OLD lossy IR projects "You get an
    emblem with ..." as one opaque, undecomposed ``emblem``-category effect
    (verified via ``old_ir_for`` — no nested ``GivePlayerCounter`` survives),
    so legacy's poison_makers can never see into it."""
    assert ("poison_makers", "opponents", "") in _idents(name)


def test_keyword_field_lookup_immune_to_name_collision():
    """The keyword field-lookups read the STRUCTURED array — a card carrying none of
    the batch-5 keywords (Lightning Bolt) can never fire foretell/cascade/suspend/
    poison, immune to the name / ability-word collisions the deleted regex floors
    suffered (checklist #3)."""
    keys = _keys("Lightning Bolt")
    for k in ("foretell_makers", "cascade_makers", "suspend_makers", "poison_makers"):
        assert k not in keys


# ── batch 6: counter-KIND / count-operand / property cluster ─────────────────


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Glistener Seer", "oil_counter_makers"),  # places an oil counter
        ("Petalmane Baku", "ki_counter_makers"),  # places a ki counter
        ("Boon of Safety", "shield_counter_makers"),  # places a shield counter
    ],
)
def test_off_p1p1_counter_makers(name, key):
    """A place_counter of an off-+1/+1 named kind (oil / ki / shield) fires its
    dedicated MAKER lane, scope you (CR 122.1)."""
    assert (key, "you", "") in _idents(name)


def test_counter_makers_kind_discriminates():
    """A pure +1/+1 placer (Cathars' Crusade) must NOT fire any off-+1/+1 counter
    maker — the counter_type is the whole discriminator (split-lane principle)."""
    keys = _keys("Cathars' Crusade")
    for k in ("oil_counter_makers", "ki_counter_makers", "shield_counter_makers"):
        assert k not in keys


def test_oil_counter_matters_payoff():
    """Urabrask's Anointer scales off oil counters on creatures you control — a
    Counters-OfType-oil filter predicate → oil_counter_matters (CR 122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Urabrask's Anointer")


def test_oil_maker_is_not_an_oil_payoff():
    """A bare oil PLACER with no payoff filter (Glistener Seer) fires the maker, not
    the matters lane."""
    assert "oil_counter_matters" not in _keys("Glistener Seer")


def test_oil_counter_matters_deep_static_condition():
    """Armored Scrapgorger's / Ichor Synthesizer's "as long as it has N oil
    counters on it, it gets +X/+Y" is a self-referencing static whose
    ``HasCounters`` CONDITION lives on the containing static's OWN node —
    the concept node IS the AddPower/AddToughness modification, never its
    container, so the flat per-concept-node walk never reaches it.
    :func:`oil_counter_kind_refs`'s whole-unit deep walk does (CR 122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Armored Scrapgorger")
    assert ("oil_counter_matters", "you", "") in _idents("Ichor Synthesizer")


def test_oil_counter_matters_deep_static_affected():
    """Ichorplate Golem's "Creatures you control with oil counters on them
    get +1/+1" carries its ``Counters`` predicate on the static's OWN
    ``affected`` field, not on the AddPower/AddToughness concept node the
    flat walk decorates (CR 122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Ichorplate Golem")


def test_oil_counter_matters_deep_scaling_pump():
    """Kuldotha Cackler's "it gets +X/+0 ... where X is the number of
    permanents you control with oil counters on them" buries the
    Counters-OfType-oil filter inside the Pump effect's ``power`` Ref->
    ObjectCount scaling operand — a nesting depth :func:`count_operand_
    filter`'s field-name check (amount/count/value) doesn't reach (CR
    122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Kuldotha Cackler")


def test_oil_counter_matters_deep_cost_reduction():
    """Cinderslash Ravager's "costs {1} less to cast for each permanent you
    control with oil counters on it" buries the filter inside a
    ``ModifyCost``'s ``dynamic_count`` field (CR 122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Cinderslash Ravager")


def test_oil_counter_matters_deep_gating_subability():
    """Oil-Gorger Troll's "if you control a permanent with an oil counter
    on it, draw a card" buries the filter inside a chained sub-ability's
    ``QuantityCheck`` gating condition (CR 122.1)."""
    assert ("oil_counter_matters", "you", "") in _idents("Oil-Gorger Troll")


def test_rad_counter_makers_scope_opponents():
    """A rad-counter giver (Tato Farmer) fires rad_counter_makers — fixed scope
    opponents, a mill-and-bleed kill clock (CR 728), read off GivePlayerCounter."""
    assert ("rad_counter_makers", "opponents", "") in _idents("Tato Farmer")


def test_experience_makers_scope_you():
    """An experience-counter giver (Mizzix) fires experience_makers you — a personal
    resource, the opposite direction to rad (checklist #5)."""
    assert ("experience_makers", "you", "") in _idents("Mizzix of the Izmagnus")


def test_player_counter_makers_do_not_cross():
    """The rad giver (Tato Farmer) is not an experience maker, and the experience
    giver (Mizzix) is not a rad maker — the kind routes the lane (checklist #5)."""
    assert "experience_makers" not in _keys("Tato Farmer")
    assert "rad_counter_makers" not in _keys("Mizzix of the Izmagnus")


def test_rad_counter_makers_whole_card_residue():
    """ADR-0038 W1 batch-4: most rad clauses land as an Unimplemented "get
    ... rad counters" effect the shared clause grammar's KIND-BLIND
    "get(s) ... counter(s)" token can't safely recover (it also matches
    +1/+1 / ki / oil / shield / poison / energy). Legacy's OWN detection
    is a whole-card raw-text fallback (project._RAD_REF, ANY direction,
    scope "opponents", gated to no structural rad effect) — mirrored
    byte-for-byte: Contaminated Drink's "you get half X rad counters",
    Feral Ghoul's trigger-carried "each opponent gets a number of rad
    counters", Harold and Bob, First Numens' clause buried inside a
    granted quoted ability text with NO node of any kind, and Survivor's
    Med Kit's OPPOSITE direction ("Target player loses all rad
    counters") all fire — legacy's fallback doesn't discriminate
    give vs. lose. CR 122.1i / 728."""
    for name in (
        "Contaminated Drink",
        "Feral Ghoul",
        "Harold and Bob, First Numens",
        "Survivor's Med Kit",
    ):
        assert ("rad_counter_makers", "opponents", "") in _idents(name), name


def test_experience_matters_scaler():
    """Ezuri scales a +1/+1 placement by experience counters (Ref.qty=PlayerCounter
    kind=Experience) → experience_matters you (CR 122.1)."""
    assert ("experience_matters", "you", "") in _idents("Ezuri, Claw of Progress")


def test_experience_matters_excludes_poison_player_counter():
    """A PlayerCounter scaler of a DIFFERENT kind (Mycosynth Fiend — poison) must
    NOT fire experience_matters; the kind gate is the discriminator (checklist #4)."""
    assert "experience_matters" not in _keys("Mycosynth Fiend")


def test_experience_maker_is_not_a_matters_scaler():
    """Mizzix gives experience (a maker) but carries no experience count-operand
    scaler → no experience_matters."""
    assert "experience_matters" not in _keys("Mizzix of the Izmagnus")


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Gray Merchant of Asphodel", "devotion_matters"),  # CR 700.5
        ("Burakos, Party Leader", "party_matters"),  # CR 700.8
        ("Tribal Flames", "domain_matters"),  # CR 700.6 (BasicLandTypeCount)
    ],
)
def test_named_count_operand_payoffs(name, key):
    """A named count-operand SCALER (devotion / party / domain) fires its payoff
    lane, scope you — read off the typed Ref.qty tag."""
    assert (key, "you", "") in _idents(name)


def test_count_operand_lanes_do_not_cross():
    """The named scalers are kind-specific: a devotion scaler (Gray Merchant) is not
    party/domain, and a domain scaler (Tribal Flames) is not devotion/party."""
    gm = _keys("Gray Merchant of Asphodel")
    assert "party_matters" not in gm
    assert "domain_matters" not in gm
    tf = _keys("Tribal Flames")
    assert "devotion_matters" not in tf
    assert "party_matters" not in tf


@pytest.mark.parametrize(
    ("name", "key"),
    [
        # recall-completion b2: the DIRECT (non-Ref) named scaler — a scaler nested
        # under a wrapper the Ref-only count_operand_qty read missed.
        ("Aspect of Hydra", "devotion_matters"),  # Pump.power/toughness.value.Ref
        ("Daybreak Chimera", "devotion_matters"),  # static ModifyCost.dynamic_count
        ("Artillery Blast", "domain_matters"),  # DealDamage.amount.Offset.inner
        ("Allied Assault", "party_matters"),  # Pump.power/toughness.value.Ref
        ("Ardent Electromancer", "party_matters"),  # Mana.produced.count.Ref
    ],
)
def test_direct_named_scaler_payoffs(name, key):
    """recall-completion b2 (ADR-0034): a named count-operand scaler that is NOT a
    plain Ref on amount/count/value — nested under a Pump P/T Quantity, a DealDamage
    Offset, a Mana produced-count, or a static ModifyCost dynamic_count — fires its
    payoff lane structurally (CR 700.5 / 700.6 / 700.8)."""
    assert (key, "you", "") in _idents(name)


def test_modified_matters_payoff():
    """Chishiro places +1/+1 counters on modified creatures you control — a Modified
    filter predicate, controller you → modified_matters (CR 700.9)."""
    assert ("modified_matters", "you", "") in _idents("Chishiro, the Shattered Blade")


def test_modified_matters_trigger_subject():
    """recall-completion b2 (ADR-0034): a "whenever a MODIFIED creature you control
    attacks" trigger (Arna Kennerüd) carries the Modified predicate on the trigger
    subject (valid_card), controller you → modified_matters (CR 700.9). The
    effect/static reads never saw a trigger subject."""
    assert ("modified_matters", "you", "") in _idents("Arna Kennerüd, Skycaptain")


def test_modified_matters_excludes_plain_anthem():
    """A generic creatures-you-control anthem (Glorious Anthem) carries no Modified
    predicate → no modified_matters."""
    assert "modified_matters" not in _keys("Glorious Anthem")


def test_multicolor_matters_anthem():
    """Knight of New Alara anthems multicolored creatures you control — a ColorCount
    GE 2 predicate, controller you → multicolor_matters (CR 105.2)."""
    assert ("multicolor_matters", "you", "") in _idents("Knight of New Alara")


@pytest.mark.parametrize("name", ["Cloven Casting", "Aurora Eidolon"])
def test_multicolor_matters_trigger_subject(name):
    """recall-completion b2 (ADR-0034): a "whenever you cast a multicolored spell"
    trigger (Cloven Casting, Aurora Eidolon) carries the ColorCount GE 2 predicate on
    the trigger subject → multicolor_matters. The you-scope of an unscoped spell
    filter comes from the trigger's own scope (CR 105.2)."""
    assert ("multicolor_matters", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Obsidian Obelisk", "Pillar of the Paruns"])
def test_multicolor_matters_mana_restriction(name):
    """A ``Mana`` effect's ``SpellType: Multicolored`` spend restriction
    ("Spend this mana only to cast a multicolored spell" — Obsidian
    Obelisk, Pillar of the Paruns) is a structural multicolor build-around
    (CR 105.2c)."""
    assert ("multicolor_matters", "you", "") in _idents(name)


def test_multicolor_matters_dropped_predicate_synthesis():
    """Stage-A synthesis (ADR-0037/0038): Fallaji Wayfarer's "Multicolored
    spells you cast have convoke." grants a keyword via a ``CastWithKeyword``
    static whose ``affected`` filter carries NO ``ColorCount`` predicate at
    all — phase drops the "multicolored" qualifier entirely, keeping it only
    in the static's description. ``tree_synthesis._arm_multicolor_matters``
    fills the gap from ``tree.oracle`` (CR 105.2)."""
    assert ("multicolor_matters", "you", "") in _idents("Fallaji Wayfarer")


def test_multicolor_matters_color_pair_prefix_synthesis():
    """Stage-A synthesis (ADR-0037/0038): Niv-Mizzet Reborn's "For each
    color pair, choose a card that's exactly those colors from among them"
    lands as an Unimplemented effect whose PARSEABLE verb ("choose") lives
    after the "for each color pair" prefix the grammar peels and discards
    — the cares-about content never reaches the recovered concept. The
    synthesis arm reads ``tree.oracle`` directly instead (CR 105.2)."""
    assert ("multicolor_matters", "you", "") in _idents("Niv-Mizzet Reborn")


@pytest.mark.parametrize("name", ["Forsaken Monument", "Conduit of Ruin"])
def test_colorless_matters(name):
    """A ColorCount EQ 0 reference (Forsaken Monument's anthem; Conduit of Ruin's
    colorless tutor, unscoped) → colorless_matters you (CR 105.2)."""
    assert ("colorless_matters", "you", "") in _idents(name)


def test_colorless_matters_trigger_subject():
    """recall-completion b2 (ADR-0034): a "whenever you cast a colorless spell"
    trigger (Kozilek's Sentinel) carries the ColorCount EQ 0 predicate on the trigger
    subject → colorless_matters (CR 105.2)."""
    assert ("colorless_matters", "you", "") in _idents("Kozilek's Sentinel")


def test_color_lanes_do_not_cross():
    """A multicolor anthem (Knight of New Alara) is not colorless, and a colorless
    anthem (Forsaken Monument) is not multicolor — the comparator/count splits."""
    assert "colorless_matters" not in _keys("Knight of New Alara")
    assert "multicolor_matters" not in _keys("Forsaken Monument")


def test_colorless_matters_cost_role_sacrifice():
    """ADR-0037/0038 W3: a COST-role colorless filter is still a genuine
    cares-about hook (Barrage Tyrant: "{2}{R}, Sacrifice another
    colorless creature: …" — a narrow colorless_matters-ONLY exception to
    the cost-role skip; the cost node itself is a ``Composite`` bundling
    Mana + Sacrifice, so :func:`iter_cost_leaves` recurses to the
    Sacrifice leaf carrying the ``ColorCount EQ 0`` target filter). CR
    105.2."""
    assert ("colorless_matters", "you", "") in _idents("Barrage Tyrant")


def test_colorless_matters_condition_site():
    """ADR-0037/0038 W3: the colorless-count CONDITION sibling of the
    existing Power-threshold condition-site read — "if you control
    another colorless creature" (Dominator Drone's ETB, filter controller
    ``ScopedPlayer`` under an ``Opponent`` player_scope wrapper) / "as
    long as you control no other colorless creatures" (Dust Stalker's
    end-step bounce, filter controller ``You``). CR 105.2 / 208.1."""
    assert ("colorless_matters", "you", "") in _idents("Dominator Drone")
    assert ("colorless_matters", "you", "") in _idents("Dust Stalker")


def test_colorless_matters_reference_idiom_synthesis():
    """ADR-0038 deferral sweep unit 6: phase drops the "colorless"
    qualifier off a cast-restriction/cost-reduction entirely (Herald of
    Kozilek: "Colorless spells you cast cost {1} less to cast" —
    ``cost_reduction`` carries no ``ColorCount`` predicate at all), the
    SAME class of gap ``_arm_multicolor_matters`` already closes for
    multicolor. ``tree_synthesis._arm_colorless_matters`` (ported
    verbatim from the OLD-IR's own
    ``supplement._recover_colorless_subject``, SIDECAR #24e) synthesizes
    the REFERENCE node from ``tree.oracle``, gated on
    ``has_structural_colorless_matters`` so a card the typed read already
    covers never doubles. Grizzled Angler // Grisly Anglerfish's front
    face ("if there is a colorless creature card in your graveyard,
    transform this creature") is the DFC case — the synthesis arm reads
    THIS face's own ``tree.oracle`` (fixture keyed by the single-face
    name, matching how phase's own card-data.json stores DFC faces as
    separate records). CR 105.2c."""
    assert ("colorless_matters", "you", "") in _idents("Herald of Kozilek")
    assert ("colorless_matters", "you", "") in _idents("Grizzled Angler")


def test_power_matters_high():
    """Shaman of the Great Hunt scales off creatures you control with power 4 or
    greater — a fixed PtComparison Power GE, controller you → power_matters."""
    assert ("power_matters", "you", "") in _idents("Shaman of the Great Hunt")


def test_low_power_matters():
    """Arabella scales off creatures you control with power 2 or less — a fixed
    PtComparison Power LE → low_power_matters (the go-low split, CR 208.1)."""
    assert ("low_power_matters", "you", "") in _idents("Arabella, Abandoned Doll")


def test_power_lanes_split_by_direction():
    """High-power and low-power are inherently different properties (split-lane): a
    GE payoff (Shaman) is not low_power; an LE payoff (Arabella) is not power."""
    assert "low_power_matters" not in _keys("Shaman of the Great Hunt")
    assert "power_matters" not in _keys("Arabella, Abandoned Doll")


def test_power_removal_target_not_a_build_around():
    """ "Destroy target creature with power 4 or greater" (Big Game Hunter) is a
    controller-any REMOVAL target, not a you-controlled build-around → no
    power_matters (checklist #6)."""
    assert "power_matters" not in _keys("Big Game Hunter")


# ADR-0038 W3 batch 2 unit 5 — the low_power_matters (and sibling power_
# matters/multicolor_matters/colorless_matters/vanilla_matters) shared
# _predicate_build_around widening: a trigger's OWN watched-subject filter
# ("whenever a creature you control with power N or less enters/attacks" —
# Ezuri, Claw of Progress, Cavalcade of Calamity) was never read at all
# (iter_concepts only surfaces role=effect/cost/static concepts, never a
# trigger's bare valid_card). CR 208.1 / 207.2c.
@pytest.mark.parametrize(
    "name",
    [
        "Cavalcade of Calamity",
        "Ezuri, Claw of Progress",
        "Irreverent Gremlin",
        "MacCready, Lamplight Mayor",
        "Marketwatch Phantom",
        "Mentor of the Meek",
        "Neighborhood Guardian",
        "Overseer of Vault 76",
        "Raid Bombardment",
        "Saradoc, Master of Buckland",
        "Serra Redeemer",
        "Shirei, Shizo's Caretaker",
        "Snarling Gorehound",
        "Vicious Clown",
        "Welcoming Vampire",
        "Wispdrinker Vampire",
    ],
)
def test_low_power_matters_trigger_subject_arm(name):
    assert ("low_power_matters", "you", "") in _idents(name)


def test_low_power_matters_unconditional_static_arm():
    """Delney, Streetwise Lookout's CantBeBlockedBy/DoubleTriggers modes
    carry no ``modifications`` list — their OWN static concept-decoration
    is empty (the previous ``if unit.statics`` gate skipped them) — but
    ``.affected`` still gates a real power-N build-around. CR 208.1."""
    assert ("low_power_matters", "you", "") in _idents("Delney, Streetwise Lookout")


def test_low_power_matters_nested_generic_effect_static_arm():
    """Merry-Go-Round's Attraction Visit ("Creatures you control with power
    2 or less gain horsemanship until end of turn") nests its static
    INSIDE the trigger's one-shot ``GenericEffect.static_abilities`` —
    :func:`iter_static_defs`'s def-level walk (the :func:`iter_mod_sites`
    sibling) reaches it regardless of unit origin. CR 208.1."""
    assert ("low_power_matters", "you", "") in _idents("Merry-Go-Round")


def test_low_power_matters_ability_target_and_delayed_trigger_arm():
    """Subira, Tulzidi Caravanner's first ability carries the PtComparison
    on the ACTIVATED ABILITY's own ``target`` field (not the nested
    CantBeBlocked static's bare ``ParentTarget`` affected); the second
    ability's delayed trigger carries it on
    ``CreateDelayedTrigger.condition.trigger.valid_source`` — the Boros
    Reckoner/damage-reflect nesting precedent
    (:func:`iter_delayed_trigger_condition_defs`). CR 208.1."""
    assert ("low_power_matters", "you", "") in _idents("Subira, Tulzidi Caravanner")


def test_predicate_build_around_sibling_lane_bonus_gains():
    """The SAME shared widening also closes gaps in the already-promoted
    sibling lanes (unaffected by residual status, proven correct by this
    batch): Threefold Signal's "Each spell you cast that's exactly three
    colors has replicate" (a mode-only CastWithKeyword static, no
    modifications list) -> multicolor_matters; Mycoid Shepherd / Challenger
    Troll's trigger/static power-4+-or-greater watchers -> power_matters.
    Zero regression verified: colorless_matters and vanilla_matters stay
    byte-identical to the pre-widening corpus census."""
    assert ("multicolor_matters", "you", "") in _idents("Threefold Signal")
    assert ("power_matters", "you", "") in _idents("Mycoid Shepherd")
    assert ("power_matters", "you", "") in _idents("Challenger Troll")


@pytest.mark.parametrize("name", ["Muraganda Petroglyphs", "Ruxa, Patient Professor"])
def test_vanilla_matters(name):
    """A HasNoAbilities payoff (Muraganda's symmetric anthem; Ruxa's you-controlled
    vanilla care) → vanilla_matters you (CR 113.3)."""
    assert ("vanilla_matters", "you", "") in _idents(name)


def test_coin_flip_doer():
    """Krark instructs a coin flip — a FlipCoin effect → coin_flip you (CR 705.1)."""
    assert ("coin_flip", "you", "") in _idents("Krark, the Thumbless")


def test_coin_flip_excludes_die_roll():
    """A die-roller (Adorable Kitten — RollDie → dice_makers, CR 706) carries no
    FlipCoin effect; coin and dice stay split."""
    assert "coin_flip" not in _keys("Adorable Kitten")


def test_opponent_discard_hand_attack():
    """Mind Rot forces a targeted player to discard — a Discard effect whose
    recipient is a targeted player → opponent_discard opponents (CR 701.9)."""
    assert ("opponent_discard", "opponents", "") in _idents("Mind Rot")


def test_opponent_discard_excludes_self_loot():
    """A self-loot (Faithless Looting — "draw two, then discard two", a you-scoped
    discard) is the ported discard_makers lane, NOT opponent_discard (checklist #5)."""
    assert "opponent_discard" not in _keys("Faithless Looting")


def test_opponent_discard_excludes_target_player_loot():
    """ "Target player draws a card, then discards a card" (Cephalid Looter) tags the
    discard recipient ``ParentTarget`` — but a SIBLING draw names the same single
    targeted player, so the controller self-targets to filter cards, not a hand
    attack (checklist #4 — loot role, not opponent_discard)."""
    assert "opponent_discard" not in _keys("Cephalid Looter")


# ── ADR-0038 W4 giants: opponent_discard wheel-wrapper + reveal-choose arms ──


def test_opponent_discard_wheel_wrapper_is_each():
    """Wheel of Fortune's own discard node ("Each player discards their
    hand, then draws seven cards.") tags its recipient plain ``Controller``
    — the per-iteration actor of the ability-level ``player_scope: All``
    loop, not a real self-target. :func:`discard_recipient_scope` alone
    reads that as "you" and skips it; the wrapper-actor fallback
    (:func:`effect_owner_player_scope` == "All") resolves it to the
    symmetric ``each`` (CR 701.9 — the wheel hits every player, including
    opponents). The extra "opponents"-scope duplicate the LEGACY kept-word
    mirror emits for this same wheel effect is a mirror over-fire, not a
    second genuine signal — it stays absent."""
    idents = _idents("Wheel of Fortune")
    assert ("opponent_discard", "each", "") in idents
    assert ("opponent_discard", "opponents", "") not in idents


def test_opponent_discard_wheel_wrapper_per_opponent_edict():
    """Burglar Rat's "each opponent discards a card" ETB carries the SAME
    plain-``Controller`` recipient shape as the symmetric wheel, but its
    wrapper actor is ``Opponent`` (:data:`_OPP_DISCARD_ACTORS`), not
    ``All`` — the per-opponent edict resolves to ``opponents``, disjoint
    from the symmetric-wheel ``each`` arm above. CR 701.9 / 102.2."""
    assert ("opponent_discard", "opponents", "") in _idents("Burglar Rat")


def test_opponent_discard_reveal_choose_discard_that_card():
    """Thoughtseize's "reveal hand, choose a card, THAT player discards
    THAT card" resolves through phase's ``DiscardCard`` tag (count=1,
    target=ParentTarget — the just-identified player from the sibling
    ``RevealHand``), distinct from a self-count ``Discard`` ("discards N
    cards"). Folding ``DiscardCard`` into the same "discard" concept
    (crosswalk.py ``EFFECT_CONCEPTS``) surfaces the entire reveal-and-
    choose hand-attack family (Duress, Inquisition of Kozilek, Coercion)
    through the existing recipient-scope read. CR 701.9 / 701.9a."""
    assert ("opponent_discard", "opponents", "") in _idents("Thoughtseize")


def test_opponent_discard_discardcard_excludes_card_reference():
    """Sindbad's "draw a card and reveal it. If it isn't a land card,
    discard it" ALSO carries a ``DiscardCard target=ParentTarget`` node —
    but here ``ParentTarget`` back-references the just-REVEALED CARD (a
    ``RevealTop`` producer, landmine #7i: phase back-reference tags are
    POSITION-relative), never a player. The sibling-``reveal_hand`` gate
    (only a player-facing ``RevealHand`` legitimizes a DiscardCard's
    ParentTarget as a player) keeps this self card-filter OUT — it is
    NOT a hand attack."""
    assert "opponent_discard" not in _keys("Sindbad")


def test_opponent_discard_symmetric_watcher():
    """Spirit Cairn's "whenever A PLAYER discards a card, you may pay {W}…"
    watches EITHER player (phase leaves both ``valid_card.controller`` and
    ``valid_target`` unset — the identical shape a genuinely self-only
    watcher like Archfiend of Ifnir's cycling trigger also carries, so no
    typed field distinguishes them). The per-unit reminder-stripped
    ``description`` text check (:data:`_SYMMETRIC_DISCARD_WATCH_RX`) is
    the sole discriminator; it fires opponent_discard ALONGSIDE
    discard_matters (a symmetric watcher pays off both self- and
    opponent-discards — CR 701.9 / 102.2), matching the design precedent
    already set for this card in the retained kept-word mirror's tail."""
    idents = _idents("Spirit Cairn")
    assert ("opponent_discard", "opponents", "") in idents
    assert ("discard_matters", "you", "") in idents


def test_opponent_discard_excludes_self_only_watcher():
    """Archfiend of Ifnir's "whenever you cycle or discard a card" is
    SELF-only (CR 702.29a) — the identical unscoped typed shape Spirit
    Cairn's symmetric watcher carries, but its description text never
    matches ``\\ba player discards\\b``, so the text-mirror fallback
    correctly leaves it out of opponent_discard (discard_matters only)."""
    idents = _idents("Archfiend of Ifnir")
    assert "opponent_discard" not in {k for k, _s, _su in idents}
    assert ("discard_matters", "you", "") in idents


def test_opponent_discard_excludes_same_target_draw_then_discard():
    """Compulsive Research's "target player draws three cards. Then that
    player discards two cards unless they discard a land card" tags its
    discard recipient ``ParentTarget`` with a sibling draw naming the SAME
    targeted ``Player`` — the identical Cephalid-Looter loot shape
    (:func:`_is_target_player_loot`): the controller can point this at
    themselves to filter cards, so it is not treated as a forced
    opponent-only hand attack, matching Cephalid Looter's precedent."""
    assert "opponent_discard" not in _keys("Compulsive Research")


def test_opponent_discard_excludes_laquatus_creativity():
    """ADR-0038 W5 tails: Laquatus's Creativity's "target player draws
    cards equal to the number of cards in their hand, then discards that
    many cards" is the SAME Cephalid-Looter loot shape as Compulsive
    Research — the discard's ``ParentTarget`` recipient and the sibling
    draw's ``Player`` recipient name the SAME single targeted player, so
    :func:`_is_target_player_loot` excludes it too (CR 701.9 / 701.8a).
    Legacy's inclusion of this card (but not Cephalid Looter, whose
    near-identical "target player draws a card, then discards a card"
    phrasing is structurally the same shape) is driven by the deleted
    kept-word mirror's incidental phrase adjacency, not a principled
    distinction — Laquatus's own text has no "that player discards"
    substring for the mirror to match on either, so this is purely a
    same-shape structural exclusion, no text quirk in play."""
    assert "opponent_discard" not in _keys("Laquatus's Creativity")


def test_opponent_discard_vote_per_choice_effect_opponent():
    """ADR-0038 W5 tails: Capital Punishment's "Each opponent ...
    discards a card for each taxes vote" lives under a ``Vote``
    ``per_choice_effect`` branch, not the unit's own direct effect chain
    — :func:`iter_typed_nodes`'s deep walk finds the buried ``Discard``
    node, and the branch's OWN ``player_scope: Opponent`` (found by the
    lane-local :func:`_nested_owner_player_scope`, since neither
    ``per_choice_effect`` nor a Vote branch's own wrapper is on the
    shared :func:`effect_owner_player_scope`'s fixed effect/sub_ability/
    execute/mode_abilities chain) resolves the per-opponent edict
    scope. CR 701.9 / 701.38 (Vote)."""
    assert ("opponent_discard", "opponents", "") in _idents("Capital Punishment")


def test_opponent_discard_vote_per_choice_effect_each():
    """ADR-0038 W5 tails: Sail into the West's "each player may discard
    their hand and draw seven cards" Vote branch carries ``player_scope:
    All`` on its OWN ``per_choice_effect`` wrapper — the SAME
    :func:`_nested_owner_player_scope` descent resolves the symmetric
    wheel scope ``each``, matching the Wheel-of-Fortune wrapper-fallback
    precedent one level deeper (behind a Vote, not a bare ability). CR
    701.9 / 701.38."""
    assert ("opponent_discard", "each", "") in _idents("Sail into the West")


def test_opponent_discard_grant_ability_definition_wheel():
    """ADR-0038 W5 tails: Mindlash Sliver's granted "{1}, Sacrifice ~:
    Each player discards a card." lives under a static's ``GrantAbility.
    definition`` — a field :func:`effect_owner_player_scope`'s fixed
    chain never reaches either (the same gap Capital Punishment's Vote
    branch hits). :func:`_nested_owner_player_scope` resolves the
    granted ability's OWN ``player_scope: All`` to the symmetric ``each``
    wheel scope. CR 701.9 / 613.1f (Layer 6 ability-granting continuous
    effect)."""
    assert ("opponent_discard", "each", "") in _idents("Mindlash Sliver")


def test_opponent_discard_team_scoped_grant_stays_each_no_opponents():
    """ADR-0038 W5 tails: Azra Bladeseeker's clause-grammar-recovered
    "each player on your TEAM may discard a card" (phase drops the whole
    clause to an ``Unimplemented`` residue re-decorated via the
    ``discard`` ALLOWLIST row) carries no typed player field of its own
    — the owner fallback reads the ability's ``player_scope: All`` and
    resolves ``each``, matching legacy's own recovered-node read. A
    "your team" restriction is 2HG-scoped and never reaches a true
    opponent (CR 102.2 defines "opponent" against every OTHER player),
    so this stays the SAME single ``each`` identity a genuine
    "each player" wheel gets — no separate "opponents" identity is
    manufactured for it."""
    idents = _idents("Azra Bladeseeker")
    assert ("opponent_discard", "each", "") in idents
    assert ("opponent_discard", "opponents", "") not in idents


# ── batch 7: phase / control / terminal-effect cluster + keyword survivors ────


@pytest.mark.parametrize(
    "name",
    ["Aurelia, the Warleader", "Moraug, Fury of Akoum", "Combat Celebrant"],
)
def test_extra_combats_additional_combat_phase(name):
    """An AdditionalPhase effect whose phase is a combat phase → extra_combats you
    (CR 505 / 506)."""
    assert ("extra_combats", "you", "") in _idents(name)


def test_extra_combats_excludes_extra_turn():
    """An extra TURN (Time Warp — ExtraTurn → extra_turns) is a different effect tag,
    never extra_combats."""
    assert "extra_combats" not in _keys("Time Warp")


def test_extra_combats_excludes_vanilla():
    """A vanilla creature carries no AdditionalPhase → no extra_combats."""
    assert "extra_combats" not in _keys("Grizzly Bears")


@pytest.mark.parametrize(
    "name", ["Goblin Electromancer", "Helm of Awakening", "Ruby Medallion"]
)
def test_cost_reduction_static_reduce(name):
    """A static ModifyCost of direction Reduce over a class of spells → cost_reduction
    you (CR 601.2f). Helm of Awakening (all spells, controller null) fires alongside
    the you-cast reducers — the controller is NOT gated, only direction."""
    assert ("cost_reduction", "you", "") in _idents(name)


def test_cost_reduction_excludes_tax():
    """Thalia's "noncreature spells cost {1} more" is a ModifyCost of direction Raise
    → excluded by the direction gate (the live _COST_INCREASE screen)."""
    assert "cost_reduction" not in _keys("Thalia, Guardian of Thraben")


@pytest.mark.parametrize("name", ["Discontinuity", "Hierophant Bio-Titan"])
def test_cost_reduction_excludes_residual_self_discount(name):
    """Phase marks 220/226 "this spell costs" self-discounts affected=SelfRef
    (the existing gate), but 6 residual cards parse as Typed[Card] +
    spell_filter=null — the SAME shape as Helm of Awakening's symmetric
    reducer, distinguishable only by the static's own description
    (phase_parse_errors [P8], refined 2026-07-02). The node-local
    "this spell costs" screen (mirror of the live _COST_SELF_DISCOUNT)
    keeps them out; Helm-class symmetric reducers still fire (pinned by
    test_cost_reduction_static_reduce)."""
    assert "cost_reduction" not in _keys(name)


def test_cost_reduction_excludes_ramp_rock():
    """A flat ramp rock (Sol Ring) carries no ModifyCost static → no cost_reduction."""
    assert "cost_reduction" not in _keys("Sol Ring")


@pytest.mark.parametrize("name", ["Training Grounds", "Fervent Champion"])
def test_cost_reduction_reduce_ability_cost(name):
    """ADR-0038 W3 batch 4: a ``ReduceAbilityCost{Reduce}`` static (a
    v0.20.0 typed mode DISTINCT from ``ModifyCost`` — CR 601.2f/118.7 covers
    activated-ability costs too) → cost_reduction you. Training Grounds
    (generic creatures-you-control team reducer, ``affected=Typed``) and
    Fervent Champion (a keyword-scoped "Equip abilities that target ~"
    reducer, ``affected=None`` — the reduction rides ``keyword``+``activator``
    fields, not a filter)."""
    assert ("cost_reduction", "you", "") in _idents(name)


def test_cost_reduction_any_node_description_residue():
    """Ghostfire Blade's "~'s equip ability costs {2} less to activate if it
    targets a colorless creature" fails phase's static parser entirely
    (an ``Unimplemented`` node, "Static pattern matched but line failed
    static parser") — read off that node's OWN description via the SAME
    three textual gates (genuine reducer, not a self-discount, not an
    increase) the deleted ``_COST_REDUCER_MIRROR`` applied, node-scoped
    (ADR-0038 W3 batch 4). CR 601.2f/118.7."""
    assert ("cost_reduction", "you", "") in _idents("Ghostfire Blade")


def test_cost_reduction_whole_tree_kept_mirror_fallback():
    """Henzie "Toolbox" Torre's second sentence ("Blitz costs you pay cost
    {1} less for each time you've cast your commander from the command zone
    this game") has NO node at all anywhere in phase's record — not even an
    Unimplemented placeholder. The final kept-mirror text fallback (the SAME
    three gates, scanned per-clause over the reminder-stripped face oracle)
    is the only path to it (ADR-0038 W3 batch 4). CR 601.2f/118.7."""
    assert ("cost_reduction", "you", "") in _idents('Henzie "Toolbox" Torre')


def test_cost_reduction_excludes_multi_sentence_self_discount():
    """Geistlight Snare: "This spell costs {1} less to cast if you control a
    Spirit. It also costs {1} less to cast if you control an enchantment."
    — the self-discount tell only names "this spell costs" in the FIRST
    sentence; the "It also costs ... less" continuation is the SAME rider,
    not an unrelated clause, so the kept-mirror fallback's self-discount
    veto is CARD-LEVEL (searches the whole reminder-stripped oracle), not
    per-clause — otherwise the second sentence would slip through and
    false-fire (ADR-0038 W3 batch 4; the structural arm ALSO independently
    excludes it via ``affected=SelfRef``)."""
    assert "cost_reduction" not in _keys("Geistlight Snare")


def test_cost_reduction_named_keyword_cost_beyond_legacy_gain():
    """ADR-0038 W3 batch 4 adjudicated GAIN (beyond legacy's narrow 6-keyword
    closed list — blitz/cycling/kicker/flashback/escape/ninjutsu): Warbringer's
    "Dash costs you pay cost {2} less" is a genuine CR 601.2f/118.7 alternative-
    cost reducer (Dash IS an alternative cost, CR 702.109) even though legacy's
    OLD arm never recognized it. Pinned as an intentional beyond-legacy
    precision widening, not a shed."""
    assert ("cost_reduction", "you", "") in _idents("Warbringer")


@pytest.mark.parametrize("name", ["Donate", "Bazaar Trader", "Harmless Offering"])
def test_donate_makers_give_away(name):
    """A GiveControl whose recipient is a non-you player (a targeted player or an
    explicit opponent) → donate_makers you (CR 110.2, checklist #2)."""
    assert ("donate_makers", "you", "") in _idents(name)


def test_donate_makers_excludes_theft():
    """Control Magic STEALS (GainControl → gain_control), the opposite direction —
    never donate_makers."""
    assert "donate_makers" not in _keys("Control Magic")


def test_donate_makers_excludes_control_reset():
    """Brooding Saurian's "each player gains control of permanents they own" is a
    GainControlAll control-RESET, not a give-away → no donate_makers."""
    assert "donate_makers" not in _keys("Brooding Saurian")


@pytest.mark.parametrize(
    "name",
    [
        "Alexios, Deimos of Kosmos",  # ScopedPlayer: "each player's upkeep, that
        # player gains control of Alexios"
        "Risky Move",  # ScopedPlayer: "each player's upkeep, that player gains
        # control of this enchantment"
        "Blim, Comedic Genius",  # TriggeringPlayer: combat damage → "that player
        # gains control of target permanent you control"
        "Kain, Traitorous Dragoon",  # TriggeringPlayer: combat damage → "that
        # player gains control of Kain"
        "Drooling Ogre",  # TriggeringPlayer: "whenever a player casts an
        # artifact spell, that player gains control of this creature"
        "Discerning Financier",  # ParentTargetController: "Choose another
        # player. That player gains control of target Treasure you control"
        "Goblin Festival",  # ParentTargetController: "choose one of your
        # opponents. That player gains control of this enchantment"
    ],
)
def test_donate_makers_dynamic_recipient_recovers(name):
    """ADR-0038 recovery: phase's ``ScopedPlayer`` / ``TriggeringPlayer`` /
    ``ParentTargetController`` recipient tags are all "that player" back-
    references :func:`_scope_from_player_node` doesn't resolve --
    :func:`control_recipient_scope`'s local ``_DONATE_RECIPIENT_SCOPES``
    mapping closes the gap (CR 110.2)."""
    assert ("donate_makers", "you", "") in _idents(name)


def test_donate_makers_mass_self_give_away_via_theft_tag():
    """Sky Swallower's "target opponent gains control of all other
    permanents you control" is phase's ``GainControlAll`` THEFT tag, but
    the beneficiary is a non-you player and the target is YOUR OWN board
    (controller='You') — the SAME give-away direction as a native
    GiveControl, mirroring the first ``_gives_control_to_other`` branch
    (CR 110.2)."""
    assert ("donate_makers", "you", "") in _idents("Sky Swallower")


def test_donate_makers_excludes_owned_control_reset_via_theft_tag():
    """Herald of Leshrac's "each player gains control of each land they own
    that you control" carries an ``Owned`` target predicate — a
    control-RESET to the original OWNER (CR 110.2a), not a give-away, even
    though it's shaped like Sky Swallower's mass GainControlAll."""
    assert "donate_makers" not in _keys("Herald of Leshrac")


@pytest.mark.parametrize(
    "name",
    [
        "Crag Saurian",  # "that source's controller gains control"
        "Contested War Zone",  # "that creature's controller gains control"
        "Starke of Rath",  # "That permanent's controller gains control"
        "Fractured Loyalty",  # "that spell or ability's controller gains control"
        "Act of Authority",  # "its controller gains control"
    ],
)
def test_donate_makers_excludes_revenge_idiom(name):
    """ADR-0034 shed: the "'s controller gains/gain control" idiom hands
    control to whoever's SOURCE damaged/destroyed/targeted the permanent —
    a consequence of an OPPONENT's own action, never a deliberate gift.
    Live's own ``_DONATE_RAW`` deliberately excludes this phrasing (it
    lives only in the SEPARATE gain_control theft-exclusion regex,
    ``_GIVE_CONTROL_AWAY``); recovering it wholesale via
    ``_gives_control_to_other`` pulled these 5 cards in as false positives
    (corpus-measured, not assumed) — :data:`_CONTROL_REVENGE_RE` excludes
    them, matching legacy's narrower scope."""
    assert "donate_makers" not in _keys(name)


def test_donate_makers_excludes_ambiguous_clash_control_flip():
    """ADR-0034 shed: Captivating Glance's clash-based control swap targets
    "enchanted creature" — an unrestricted Aura target, not guaranteed to
    be something YOU control. The winning/losing branches are symmetric
    (either player could gain it), so this is not a clean "you give away
    YOUR OWN permanent" doer."""
    assert "donate_makers" not in _keys("Captivating Glance")


def test_donate_makers_excludes_granted_revenge_tax():
    """ADR-0034 shed: Custody Battle's granted "at the beginning of YOUR
    upkeep, target opponent gains control of this creature unless YOU
    sacrifice a land" is scoped relative to the ENCHANTED creature's OWN
    controller (whoever that is), not necessarily the Aura's caster —
    mechanically a tax-or-lose-it THREAT typically cast on an opponent's
    creature, not a self-donate."""
    assert "donate_makers" not in _keys("Custody Battle")


def test_donate_makers_recovers_regex_gap_intervening_clause():
    """Coveted Jewel's "that player draws three cards and gains control of
    this artifact" is a genuine donate (CR 110.2), but legacy's own
    ``_DONATE_RAW`` regex requires "that player" IMMEDIATELY followed by
    "gains control of" — the intervening "draws three cards and" clause
    defeats the literal match. The structural read has no such adjacency
    requirement, closing a genuine legacy RECALL gap (not an over-fire)."""
    assert ("donate_makers", "you", "") in _idents("Coveted Jewel")


def test_donate_makers_recovers_subjunctive_gain_form():
    """Assault Suit's "you may have that player gain control of equipped
    creature" uses the subjunctive "gain" (no trailing "s") after "may
    have" — legacy's ``_DONATE_RAW`` regex requires the indicative "gains
    control of" and misses this surface variation. The structural read
    (typed recipient + scope) is form-agnostic."""
    assert ("donate_makers", "you", "") in _idents("Assault Suit")


@pytest.mark.parametrize("name", ["Call the Crash", "Current Curriculum"])
def test_conjure_makers_structural(name):
    """A Conjure effect → conjure_makers you (DD2 / DD5)."""
    assert ("conjure_makers", "you", "") in _idents(name)


def test_conjure_makers_excludes_ability_name_false_positive():
    """Silvanus's Invoker's ability is NAMED "Conjure Elemental" but carries no
    Conjure effect node — the structural read drops the live \\bconjure\\b regex
    false-positive (fidelity gain)."""
    assert "conjure_makers" not in _keys("Silvanus's Invoker")


def test_conjure_makers_excludes_token_maker():
    """A token maker (Krenko — make_token) is a different effect tag, not Conjure."""
    assert "conjure_makers" not in _keys("Krenko, Mob Boss")


@pytest.mark.parametrize("name", ["Alley Grifters", "Aether Membrane"])
def test_blocked_matters_trigger_event(name):
    """A becomes_blocked (attacker-side) or blocks (blocker-side) trigger →
    blocked_matters you (CR 509)."""
    assert ("blocked_matters", "you", "") in _idents(name)


def test_blocked_matters_excludes_attacks_trigger():
    """An attacks-only trigger (Arabella) is attack_matters, not blocked_matters."""
    assert "blocked_matters" not in _keys("Arabella, Abandoned Doll")


def test_initiative_makers_take_the_initiative():
    """A TakeTheInitiative effect → initiative_makers you, read distinctly from the
    venture concept it folds into so venture_makers still co-fires (CR 726)."""
    ids = _idents("Caves of Chaos Adventurer")
    assert ("initiative_makers", "you", "") in ids
    assert ("venture_makers", "you", "") in ids  # the co-fire is preserved


def test_initiative_makers_excludes_pure_venture():
    """Acererak ventures into a dungeon (VentureIntoDungeon) but never takes the
    initiative → venture_makers yes, initiative_makers NO."""
    keys = _keys("Acererak the Archlich")
    assert "venture_makers" in keys
    assert "initiative_makers" not in keys


def test_initiative_matters_condition():
    """Passageway Seer's "if you have the initiative" payoff (IsInitiative condition)
    → initiative_matters you; it also takes the initiative → initiative_makers."""
    ids = _idents("Passageway Seer")
    assert ("initiative_matters", "you", "") in ids
    assert ("initiative_makers", "you", "") in ids


def test_initiative_matters_excludes_take_only():
    """A take-only initiative card (Caves of Chaos Adventurer) carries no IsInitiative
    condition → initiative_makers yes, initiative_matters NO (checklist #4)."""
    keys = _keys("Caves of Chaos Adventurer")
    assert "initiative_makers" in keys
    assert "initiative_matters" not in keys


def test_initiative_matters_excludes_monarch():
    """A monarch card (Azure Fleet Admiral — IsMonarch designation) is a different
    designation → no initiative_matters."""
    assert "initiative_matters" not in _keys("Azure Fleet Admiral")


@pytest.mark.parametrize("name", ["Time Stop", "Sundial of the Infinite"])
def test_end_the_turn_structural(name):
    """An EndTheTurn effect → end_the_turn you (CR 724)."""
    assert ("end_the_turn", "you", "") in _idents(name)


def test_end_the_turn_excludes_extra_turn():
    """Time Warp's ExtraTurn (→ extra_turns) is a different effect tag, never
    end_the_turn."""
    assert "end_the_turn" not in _keys("Time Warp")


def test_end_the_turn_recovery_promoted():
    """CR 724 — Obeka's player-scoped grant ("The player whose turn it is
    may end the turn") is an Unimplemented effect the ADR-0038 shared
    clause grammar re-decorates (a new player-subject peel + verb tag), so
    the SAME typed read Time Stop/Sundial of the Infinite use fires here
    too, no marker special-case."""
    assert ("end_the_turn", "you", "") in _idents("Obeka, Brute Chronologist")


@pytest.mark.parametrize(
    "name", ["Bojuka Bog", "Angel of Finality", "Author of Shadows"]
)
def test_opponent_exile_makers_graveyard_hate(name):
    """A ChangeZone (Graveyard → Exile) targeting a whole player's graveyard, or
    opponent-scoped, → opponent_exile_makers opponents (CR 406, graveyard hate).
    Author of Shadows ("exile all opponents' graveyards") is a crosswalk_only
    fidelity GAIN over the live word-mirror."""
    assert ("opponent_exile_makers", "opponents", "") in _idents(name)


def test_opponent_exile_makers_excludes_self_blink():
    """Cloudshift exiles and returns YOUR creature (origin not Graveyard) → no
    opponent_exile_makers."""
    assert "opponent_exile_makers" not in _keys("Cloudshift")


def test_opponent_exile_makers_excludes_replacement():
    """Leyline of the Void's GY→exile is a REPLACEMENT whose ChangeZone has no
    Graveyard origin → the ChangeZone arm does not fire (the replacement arm is a
    documented live_only tail)."""
    assert "opponent_exile_makers" not in _keys("Leyline of the Void")


def test_opponent_exile_makers_excludes_any_card_exile():
    """Scavenging Ooze exiles a single CARD from a graveyard (target a Typed card, not
    a player) — ambiguous with self-graveyard-exile-for-value, so the player-target
    gate correctly excludes it (matching the live, which also does not fire it)."""
    assert "opponent_exile_makers" not in _keys("Scavenging Ooze")


@pytest.mark.parametrize("name", ["Bitter Work", "Boom Scholar"])
def test_exhaust_makers_keyword(name):
    """The Scryfall Exhaust keyword → exhaust_makers you (CR 702.177)."""
    assert ("exhaust_makers", "you", "") in _idents(name)


def test_boast_makers_keyword_co_fires_attack_matters():
    """The Scryfall Boast keyword → boast_makers you AND attack_matters you (the live
    preset co-fire, CR 702.142)."""
    ids = _idents("Dragonkin Berserker")
    assert ("boast_makers", "you", "") in ids
    assert ("attack_matters", "you", "") in ids


def test_boast_exhaust_keyword_negative():
    """A card without the Boast / Exhaust keyword (Young Pyromancer) fires neither."""
    keys = _keys("Young Pyromancer")
    assert "boast_makers" not in keys
    assert "exhaust_makers" not in keys


@pytest.mark.parametrize("name", ["Chord of Calling", "Venerated Loxodon"])
def test_convoke_makers_keyword(name):
    """The Scryfall Convoke keyword (the BEARER) → convoke_makers you (CR 702.51)."""
    assert ("convoke_makers", "you", "") in _idents(name)


def test_convoke_makers_recovers_static_granter():
    """Corrected classification (ADR-0037/0038 W1 batch-3, replaces the old
    ``test_convoke_makers_excludes_granter``): Chief Engineer GRANTS
    convoke ("Artifact spells you cast have convoke.") via a typed
    ``CastWithKeyword`` static — a real structural read
    (:func:`cast_with_keyword_name`), not a Scryfall keyword-field lookup
    (Chief Engineer carries no ``Convoke`` keyword itself). CR 702.51: the
    grant lets YOUR creatures help pay for those spells, the same "convoke
    doer" capability the keyword-BEARER form represents — legacy's own
    corpus detection already conflates both roles under one key, so the
    old "excludes_granter" assertion was pinning a residual GAP, not an
    intended exclusion. The prior corpus-vs-legacy diff confirmed all 9
    live_only granter cards (Chief Engineer among them) are genuine
    convoke_makers members."""
    assert ("convoke_makers", "you", "") in _idents("Chief Engineer")


def test_convoke_makers_recovers_next_spell_grant():
    """Wand of the Worldsoul's "{T}: The next spell you cast this turn has
    convoke." is a ONE-SHOT ``GrantNextSpellAbility`` effect — a DIFFERENT
    typed shape than the always-on ``CastWithKeyword`` static (Chief
    Engineer) but the SAME CR 702.51 granter capability, read via
    :func:`granted_next_spell_keyword`."""
    assert ("convoke_makers", "you", "") in _idents("Wand of the Worldsoul")


def test_convoke_makers_recovers_dfc_face_granter():
    """Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight's front face
    ("Creature spells you cast have convoke.") carries the SAME
    ``CastWithKeyword`` static shape as Chief Engineer — the DFC/split
    granter tail (Dazzling Theater, Caetus, Sea Tyrant of Segovia) that
    production's front-face-selection happens to resolve to the
    convoke-bearing half in every corpus case."""
    assert ("convoke_makers", "you", "") in _idents("Eirdu, Carrier of Dawn")


@pytest.mark.parametrize("name", ["Storm-Kiln Artist", "Archmage Emeritus"])
def test_magecraft_matters_keyword(name):
    """The Scryfall Magecraft keyword (the only reachable anchor — the trigger lives
    in stripped reminder text) → magecraft_matters you (CR 207.2c)."""
    assert ("magecraft_matters", "you", "") in _idents(name)


def test_magecraft_matters_excludes_plain_spellcast():
    """Young Pyromancer's "whenever you cast an instant or sorcery" carries no
    Magecraft keyword (no "or copy" clause) → spellcast_matters, not magecraft."""
    assert "magecraft_matters" not in _keys("Young Pyromancer")


# ── batch 8: mana / card-flow / removal / pump / library-top cluster ─────────


@pytest.mark.parametrize(
    "name",
    [
        "Mana Reflection",  # ProduceMana replacement, Multiply x2
        "Virtue of Strength",  # Multiply x3 (basic lands)
        "Crypt Ghast",  # TapsForMana trigger, produced.contribution Additional
    ],
)
def test_mana_amplifier_structural(name):
    """A mana doubler fires mana_amplifier (CR 106.4 / 605.1 / 614.1): the
    ProduceMana Multiply replacement (Mana Reflection) and the tap-for-mana
    additional-contribution trigger (Crypt Ghast — a structural read of the
    live raw tail)."""
    assert ("mana_amplifier", "you", "") in _idents(name)


def test_mana_amplifier_excludes_plain_ramp():
    """A plain producer (Sol Ring — a ramp effect, no replacement/Additional)
    is acceleration, never a doubler."""
    assert "mana_amplifier" not in _keys("Sol Ring")


def test_mana_amplifier_excludes_single_land_ramp_aura():
    """Wild Growth's "enchanted land … adds an additional {G}" watches ONE
    attached land (valid_card ``AttachedTo``) — a ramp Aura, not a class-wide
    doubling engine; the Typed-class gate excludes it."""
    assert "mana_amplifier" not in _keys("Wild Growth")


# ADR-0038 W3 batch 2 unit 1 — the ``TriggerEventManaType`` produced-tag arm
# ("add one mana of any type that [land/permanent] produced" — CR 106.4 /
# 605): a DISTINCT typed shape from the ``Additional``-contribution arm
# (Crypt Ghast) above, since ``contribution`` is unset on this variant.
@pytest.mark.parametrize(
    "name",
    [
        "Mirari's Wake",  # land tap -> match-type doubler
        "Zendikar Resurgent",  # land tap -> match-type doubler
        "Vorinclex, Voice of Hunger",  # land tap -> match-type doubler
        "Nikya of the Old Ways",  # land tap -> match-type doubler
        "Kinnan, Bonder Prodigy",  # NONLAND permanent tap
        "Roxanne, Starfall Savant",  # artifact TOKEN tap
        "Sasaya's Essence",  # per-other-namesake-land scaling variant
    ],
)
def test_mana_amplifier_trigger_event_mana_type(name):
    """The TapsForMana trigger's ``Mana`` effect ``produced`` tag
    ``TriggerEventManaType`` is a doubler regardless of the watched
    producer's card type (land / nonland permanent / token) — CR 106.4."""
    assert ("mana_amplifier", "you", "") in _idents(name)


def test_mana_amplifier_double_mana_pool():
    """Doubling Cube's "{3}, {T}: Double the amount of each type of unspent
    mana you have" is a whole-card ``double_quantity`` (``Double`` effect,
    any origin — CR 106.4) whose ``target_kind`` is ``ManaPool``, mirroring
    the sibling ``life_total_set`` / counter-doubling ``Double`` reads."""
    assert ("mana_amplifier", "you", "") in _idents("Doubling Cube")


def test_mana_amplifier_dork_support_word_mirror():
    """Raggadragga, Goreguts Boss's "Each creature you control with a mana
    ability gets +2/+2" is a filtered team-pump (CR 605) phase's static
    parser cannot express (Unimplemented residue, no filter node to recover
    structurally) — last-resort word mirror, corpus-verified singleton
    (the only commander-legal card with the literal singular phrase "with a
    mana ability"; Power Sink's "lands with mana abilities" is the plural,
    unrelated tax-effect form)."""
    assert ("mana_amplifier", "you", "") in _idents("Raggadragga, Goreguts Boss")


# ADR-0038 W3 batch 2 unit 1 — beyond-legacy gains: SYMMETRIC "whenever a
# player taps a land for mana, that player adds one mana of any type that
# land produced" doublers. The legacy regex's ``add (?:an additional|...)``
# alternation requires the literal imperative "add", so third-person "adds"
# (the "that player adds" phrasing every symmetric doubler uses) never
# matched — an incidental legacy gap, not a deliberate any-vs-you policy
# (Gauntlet of Might / Gauntlet of Power / Vernal Bloom / Nyxbloom Ancient
# are the SAME symmetric-or-controller-scoped shape and were already
# pre-existing crosswalk-only gains before this batch). CR 106.4 doublers
# are doublers regardless of who benefits; the signal's "you" scope (matching
# every other mana_amplifier arm) reads "you get build-around value from
# having this doubler in play", not "only you benefit".
@pytest.mark.parametrize(
    "name",
    [
        "Mana Flare",
        "Heartbeat of Spring",
        "Dictate of Karametra",
        "Zhur-Taa Ancient",
        "Lavaleaper",  # basic lands only, still the same produced tag
        "Overabundance",  # doubler + self-damage rider, doubler arm alone gates
        "Winter's Night",  # doubler + opponent no-untap rider
        "Barbflare Gremlin",  # doubler conditional on Barbflare being tapped
        "Gauntlet of Might",  # pre-existing (Additional-contribution arm)
        "Gauntlet of Power",  # pre-existing (Additional-contribution arm)
        "Vernal Bloom",  # pre-existing (Additional-contribution arm)
        "Nyxbloom Ancient",  # pre-existing (Multiply x3 replacement arm)
    ],
)
def test_mana_amplifier_symmetric_beyond_legacy_gain(name):
    """Symmetric / any-controller mana doublers fire mana_amplifier — a
    genuine beyond-legacy recall gain, not an over-fire (CR 106.4)."""
    assert ("mana_amplifier", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Burgeoning", True),  # put a land from HAND onto the battlefield
        ("Elvish Rejuvenator", True),  # Dig destination Battlefield, Land
        ("Sneak Attack", False),  # a CREATURE cheat → cheat_into_play
    ],
)
def test_extra_land_drop_zone_and_type_gates(name, should_fire):
    """extra_land_drop fires on a land PUT into play (CR 305.4 — a put, not a
    play); a dig-to-hand and a creature cheat stay out (checklist #2/#4)."""
    assert (("extra_land_drop", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        "Aminatou's Augury",  # synth: land put buried in an exile_top raw
        "Averna, the Chaos Bloom",  # synth: cascade reanimate, no Land filter
        "Journey to the Lost City",  # synth: dropped d20-branch put
        "Bonny Pall, Clearcutter",  # synth: "hand or graveyard" disjunction
        "Dread Tiller",  # synth: "hand or graveyard" disjunction
        "Riveteers Confluence",  # synth: modal "hand or graveyard" disjunction
    ],
)
def test_extra_land_drop_idiom_bridge_synthesis(name):
    """ADR-0037/0038 synthesis: the YOUR "put a land card from your hand/
    among them/among those cards/among the exiled cards ... onto the
    battlefield" idiom (CR 305.4/720) phase leaves wholly or partially
    unstructured — a cascade-from-exile reanimate with no Land filter
    (Averna), a land put buried inside an exile/dropped-branch raw
    (Aminatou's Augury, Journey to the Lost City), or a "from hand OR
    graveyard" disjunction that defeats phase's controller pin on an
    otherwise-typed ChangeZone (Bonny Pall, Dread Tiller, Riveteers
    Confluence — controller=None, no InZone property).
    ``tree_synthesis._arm_extra_land_drop`` mirrors the OLD-IR
    ``_recover_extra_land_drop`` idiom-scan byte-for-byte."""
    assert ("extra_land_drop", "you", "") in _idents(name)


def test_extra_land_drop_planar_genesis_now_fires():
    """Planar Genesis's own typed Dig is destination=Hand (a card-
    selection effect, correctly excluded by the structural arm), but its
    "you may put a land card from among them onto the battlefield tapped"
    modal branch is a GENUINE extra land drop (CR 305.4) legacy's own
    regex-bridge already recognized — the idiom-bridge synthesis arm now
    recovers it too (a corrected classification, not a new over-fire: this
    key's corpus crosswalk-vs-old-IR measurement went from live_only=7 to
    live_only=0 with Planar Genesis in the "both" set)."""
    assert ("extra_land_drop", "you", "") in _idents("Planar Genesis")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Mana Flare", True),  # "that player adds" — TriggeringPlayer recipient
        ("Magus of the Vineyard", True),  # each player's upkeep — ScopedPlayer
        ("Sol Ring", False),  # controller-only ramp, no recipient
        ("Crypt Ghast", False),  # YOUR additional mana — not a group gift
    ],
)
def test_group_mana_recipient_direction(name, should_fire):
    """group_mana reads the Mana effect's typed RECIPIENT (CR 106.4) — the
    non-controller direction the old lossy IR dropped to raw (checklist #5)."""
    assert (("group_mana", "each", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Shamanic Revelation", True),  # draw for each creature — ObjectCount
        ("Braingeyser", False),  # draw X — Ref→Variable, the cast cost
        ("Tamiyo's Logbook", False),  # fixed draw; for-each is a cost rider
    ],
)
def test_draw_for_each_scaling_gate(name, should_fire):
    """draw_for_each admits a board-count scaler and rejects bare X-draws and
    fixed draws whose for-each lives in a sibling clause (CR 107.3,
    granularity a)."""
    assert (("draw_for_each", "you", "") in _idents(name)) is should_fire


# ── ADR-0038 W3 batch 6 (draw-etb-tokens cluster): draw_for_each widening ──
# (196 both / 17 live_only, down from 74 — NOT YET PROMOTED, see
# ``_draw_for_each``'s docstring for the full per-shape triage of what's
# still residual.)


def test_draw_for_each_local_tracked_count_tags():
    """:data:`_DRAW_FOR_EACH_TRACKED_TAGS` admits an UNAMBIGUOUS delayed/
    tracked count with no text gate — Syphon Mind's
    ``FilteredTrackedSetSize`` ("You draw a card for each card discarded
    this way" — the Draw itself lives on a description-less
    ``sub_ability``, recovered via the widened owning-UNIT description
    fallback), Change of Fortune's ``CardsDiscardedThisTurn``, Inspired
    Sphinx's ``PlayerCount`` ("for each opponent"). CR 107.3."""
    assert ("draw_for_each", "you", "") in _idents("Syphon Mind")
    assert ("draw_for_each", "you", "") in _idents("Change of Fortune")
    assert ("draw_for_each", "you", "") in _idents("Inspired Sphinx")


def test_draw_for_each_excludes_that_many_engine():
    """``EventContextAmount``/``PreviousEffectAmount`` are DELIBERATELY
    absent from :data:`_DRAW_FOR_EACH_TRACKED_TAGS` — Cold-Eyed Selkie's
    "Whenever this creature deals combat damage to a player, you may draw
    that many cards" shares the SAME qty tag as a genuine draw_for_each
    member (Struggle for Project Purity's "for each card drawn this way")
    but is a damage-scaled draw ENGINE, not a board-count scale; legacy
    does not tag it draw_for_each and the phrase gate (no "for each"/
    "equal to the number of" wording) correctly keeps it out."""
    assert "draw_for_each" not in _keys("Cold-Eyed Selkie")


def test_draw_for_each_where_x_is_phrasing_gain():
    """Beyond-legacy gain: Peer Past the Veil's "draw X cards, where X is
    the number of card types among cards in your graveyard" is a genuine
    CR 107.3 board-count scale legacy's regex misses — the deleted
    producer only recognized "for each"/"equal to the number of" wording,
    not "where X is the number of"."""
    assert ("draw_for_each", "you", "") in _idents("Peer Past the Veil")


def test_recovered_draw_reaches_draw_lanes():
    """ADR-0038 post-giants batch (CR 121.1, verified via rules-lookup
    this session): the "draw" recovery ALLOWLIST row — a computed-amount
    draw phase parks as one Unimplemented residue. Curse of Surveillance's
    "draw cards equal to the number of Curses attached to that player"
    (the class the salvage-trimmed first attempt at this row targeted) now
    reaches both the engine and the for-each lanes; Kumena's Awakening's
    each-player upkeep draw reaches the engine + group-hug reads. Blast
    radius at introduction: 6 changed cards corpus-wide, all adjudicated
    genuine; the Bladecoil/Grothama boundary pins that trimmed the first
    attempt hold (the seam guard + lane gates draw the line)."""
    idents = _idents("Curse of Surveillance")
    assert ("card_draw_engine", "you", "") in idents
    assert ("draw_for_each", "you", "") in idents
    kum = _idents("Kumena's Awakening")
    assert ("card_draw_engine", "you", "") in kum


# ── ADR-0038 W5 tails: draw_for_each reversed-order phrase + deep descent ──


@pytest.mark.parametrize(
    "name",
    [
        "Tempt with Bunnies",  # "For each opponent who does, you draw a card"
        "Braids, Arisen Nightmare",  # "For each opponent who doesn't, ... draw a card"
        "Mob Verdict",  # "For each vote you received, draw a card."
        "Hollow Marauder",  # "For each of those opponents who didn't ..., draw a card."
        "Bladecoil Serpent",  # "for each {U}{U} spent to cast it, draw a card."
        "Mutalith Vortex Beast",  # "For each flip you win, draw a card."
    ],
)
def test_draw_for_each_reversed_phrase_order(name):
    """The per-opponent modal "for each X, ... draw(s) a card" idiom puts
    the conditional AHEAD of the main clause (CR grammar) — the REVERSED
    word order the FORWARD-only phrase gate missed. Each of these carries
    a Fixed(1) Draw node with no scaling qty tag of its own; the raw text
    lives on the enclosing unit's own top-level description (the widened
    fallback), not a per-node wrapper. CR 107.3."""
    assert ("draw_for_each", "you", "") in _idents(name)


def test_draw_for_each_reversed_phrase_requires_card_object():
    """MANDATORY EXCLUSION: Truce's "For each card less than two a player
    draws this way, that player gains 2 life." would false-match the bare
    reversed alternative on "draws" as a BACK-REFERENCE to the EARLIER
    already-resolved Fixed(2) draw (feeding a LIFE GAIN, not a new scaling
    draw) — the object gate (``draws?`` must be immediately followed by a
    "card(s)" object) correctly excludes it; "draws this way" fails."""
    assert "draw_for_each" not in _keys("Truce")


def test_draw_for_each_vote_per_choice_descent():
    """Truth or Consequences' "You draw cards equal to the number of truth
    votes." lives on ``Vote.per_choice_effect[i].effect`` — a SEPARATE
    branch ``effect_concepts`` never reaches (same shape as the
    GrantTrigger descent above). CR 701.38 (Vote) / 107.3."""
    assert ("draw_for_each", "you", "") in _idents("Truth or Consequences")


def test_draw_for_each_fires_on_text_only_face_tree():
    """ADR-0038 W5b tail: Mouth // Feed's Aftermath back half "Feed" —
    "Draw a card for each creature you control with power 3 or greater."
    — has NO phase record at all (phase never emits aftermath second
    halves), so ``tree.units == ()`` (task #76's text-only face tree, the
    SAME shape ``lure_makers``'s Destined // Lead pin covers). No typed
    Draw node exists for the unit-based arms to walk, so this lane's
    OWN ``_DRAW_FOR_EACH_PHRASE_RE`` clause-scoped text gate — already
    trusted as a fallback when a typed Draw node's wrapper carries no
    grounding raw — runs over the whole (units-empty) face text instead.
    CR 121.1/107.3."""
    from mtg_utils._deck_forge._ir_lookup import _text_only_tree

    face = {
        "name": "Feed",
        "mana_cost": "{2}{G}",
        "type_line": "Sorcery",
        "oracle_text": (
            "Aftermath (Cast this spell only from your graveyard. "
            "Then exile it.)\n"
            "Draw a card for each creature you control with power 3 "
            "or greater."
        ),
    }
    tree = _text_only_tree(
        face, {"cmc": 5.0}, oracle_id="1b6c1f5d-2b1e-4f3a-9c1e-9f6b8e3d2a11"
    )
    assert tree is not None
    assert tree.units == ()  # zero typed substrate — text idioms only
    idents = {
        (s.key, s.scope, s.subject)
        for s in extract_crosswalk_signals(tree, keywords=frozenset())
    }
    assert ("draw_for_each", "you", "") in idents


def test_recovered_draw_seam_guard_rejects_non_draw_senses():
    """The _NON_DRAW_SENSE seam guard (the exact trap that got the first
    "draw" row trimmed): Divine Intervention's "the game is a draw" is a
    game-result noun, not a CR 121.1 card draw — the recovery seam rejects
    it before any lane can see it, so the card fires NO draw lane."""
    assert not {k for k in _keys("Divine Intervention") if "draw" in k}


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Faithless Looting", True),  # self-loot (you discard)
        ("Dark Deal", True),  # symmetric each-player wheel — hits you too
        ("Mind Rot", False),  # targeted hand attack → opponent_discard
        ("The Eldest Reborn", False),  # saga "each opponent discards" mislabel
    ],
)
def test_discard_outlet_direction_gates(name, should_fire):
    """discard_outlet is SELF/symmetric loot fuel (CR 701.9): the wrapper
    player_scope read rejects the phase-mislabeled opponent-directed saga
    discard STRUCTURALLY (the live path needed two raw vetoes)."""
    assert (("discard_outlet", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        "Seismic Assault",  # bare top-level cost ("Discard a land card:")
        "Insolent Neonate",  # Composite leaf ("Discard a card, Sacrifice...")
        "Oriss, Samite Guardian",  # Grandeur "Discard another card named ~:"
    ],
)
def test_discard_outlet_cost_position_dominant_gap(name):
    """ADR-0038 W4 giants: the DOMINANT gap this key carried — "Discard a
    card: <effect>" is a COST, never surfacing through
    :meth:`AbilityUnit.effect_concepts` at all. :func:`_iter_discard_cost_nodes`
    finds a bare top-level ``Discard`` cost (Seismic Assault) and a leaf
    folded into a Composite activation cost (Insolent Neonate's
    "Discard a card, Sacrifice this creature:", Oriss's Grandeur
    "Discard another card named ~:" — phase parks the "named X" filter it
    can't structure as a SIBLING ``Unimplemented`` cost leaf, leaving the
    Discard leaf itself intact) equally (CR 602.1a — a cost is always paid
    by the activator)."""
    assert ("discard_outlet", "you", "") in _idents(name)


def test_discard_outlet_granted_ability_descent():
    """A GRANTED "Discard a card:" ability's own cost lives inside a
    static's ``GrantAbility.definition`` — invisible to the grantor's own
    top-level ``unit.costs`` walk. Hollowhead Sliver ("Sliver creatures you
    control have '{T}, Discard a card: Draw a card.'") and Mindlash Sliver
    ("All Slivers have '..., Sacrifice this permanent: Each player
    discards a card.'" — a granted SYMMETRIC wheel, the SAME "hits you too"
    reasoning as Dark Deal) both surface via the deep descent."""
    assert ("discard_outlet", "you", "") in _idents("Hollowhead Sliver")
    assert ("discard_outlet", "you", "") in _idents("Mindlash Sliver")


def test_discard_outlet_else_ability_effect_descent():
    """An EFFECT-position discard phase nests past
    ``effect_concepts``'s ``_EFFECT_CHILD_FIELDS`` reach — The Destined
    Thief's "draw a card, then discard a card. If you have a full party,
    instead draw three cards." models the base discard as a conditional
    REPLACEMENT's ``sub_ability.else_ability.effect`` (the "instead" arm
    replaces it with a bigger draw). The deep descent reaches it; CR
    701.8a."""
    assert ("discard_outlet", "you", "") in _idents("The Destined Thief")


def test_discard_outlet_alt_cast_cost_kept_mirror():
    """ "As an additional cost to cast this spell, discard …" surfaces NO
    typed ``Discard`` node anywhere in phase's tree for a Spell ability
    (the Spell's own ``cost`` field is ``None`` — mirrors
    ``_CAST_ADD_SAC_RX``'s documented sacrifice_outlets gap). The
    byte-identical deleted SWEEP regex, run per-clause over the kept
    oracle, recovers both Devastating Dreams ("discard X cards at
    random") and Kaervek's Spite ("discard your hand") — CR 601.2f."""
    assert ("discard_outlet", "you", "") in _idents("Devastating Dreams")
    assert ("discard_outlet", "you", "") in _idents("Kaervek's Spite")


def test_discard_outlet_self_ref_cycling_excluded():
    """A ``self_ref`` COST leaf ("Discard THIS card:") is Cycling /
    Eternalize / Unearth-style alt-cost fodder, not an outlet — mirrors the
    old IR's cost-part split ("discardself" vs "discard") that keeps a
    pure-cycling card OUT. Krosan Tusker carries ONLY a cycling ability
    (``self_ref=True`` on its Discard cost leaf), so it must NOT fire."""
    assert "discard_outlet" not in _keys("Krosan Tusker")


def test_discard_outlet_wheel_effect_fidelity_gain():
    """Beyond-legacy gain: Wheel of Fortune's "Each player discards their
    hand, then draws seven cards" is a genuine symmetric wheel (CR
    701.8a — it hits YOU too, the exact "Dark Deal" shape this lane's own
    docstring names). The legacy flat-parsed IR's opponent-raw veto regex
    over-broadly matches the literal words "each"+"player"+"discards"
    (intended only for a mis-scoped "each OPPONENT discards" ETB) and
    incorrectly excludes it; the structural
    :func:`effect_owner_player_scope` read here correctly does NOT veto a
    symmetric ``All`` actor, so this fires where legacy doesn't (adjudicated
    a fidelity gain this session, left uncorrected)."""
    assert ("discard_outlet", "you", "") in _idents("Wheel of Fortune")


@pytest.mark.parametrize(
    "name",
    [
        "Torment of Hailfire",  # unless_pay: "unless that player discards"
        "K'un-Lun Warrior",  # ChooseOneOf branches: ambiguous chooser
        "Mox Diamond",  # replacement MayCost decline-cost, not an outlet
    ],
)
def test_discard_outlet_skip_fields_shed(name):
    """MANDATORY SHED (recorded session adjudication, ADR-0038 W4 giants):
    :data:`_DISCARD_OUTLET_SKIP_FIELDS` (``unless_pay`` / ``branches`` /
    ``per_choice_effect`` / ``mode``) keeps three DIFFERENT-payer /
    ambiguous-chooser / non-discretionary shapes out, matching legacy
    (which reads none of them either): Torment of Hailfire's "each
    opponent loses 3 life unless that player discards" alt-cost payer is
    the effect's TARGET, not this ability's controller (the SAME
    ``unless_pay`` shape sacrifice_outlets deliberately excludes); K'un-Lun
    Warrior's "you may discard a card or sacrifice an artifact" modal
    ``ChooseOneOf`` shares its exact node shape with Osseous Sticktwister's
    "each opponent may sacrifice OR discard" (an opponent chooser
    :func:`effect_owner_player_scope` can't reach through — both stay out
    rather than risk the +60 crosswalk_only over-fire probed this session);
    Mox Diamond's "you may discard a land instead" is a replacement's
    decline-cost, not a discretionary value engine (CR 602.1a / 603.6)."""
    assert "discard_outlet" not in _keys(name)


def test_discard_outlet_additional_generic_walk_gains():
    """The deep descent finds a ``Discard`` cost/effect node reachable
    through ANY untagged field, not just the specific shapes named above
    — two more beyond-legacy gains this session left uncorrected: The
    Infamous Cruelclaw's "cast that card by discarding a card rather than
    paying its mana cost" (an alternative CASTING cost, CR 601.2b, living
    on its own ``alt_ability_cost`` field — unambiguously paid by the
    caster) and Flubs, the Fool's "draw a card if you have no cards in
    hand. Otherwise, discard a card." (the SAME conditional-replacement
    ``else_ability`` shape as The Destined Thief, a second corpus
    instance)."""
    assert ("discard_outlet", "you", "") in _idents("The Infamous Cruelclaw")
    assert ("discard_outlet", "you", "") in _idents("Flubs, the Fool")


@pytest.mark.parametrize(
    "name",
    [
        "Timeline Inquiry",
        "Tainted Indulgence",
        "Waterbending Lesson",
        "Wonderscape Sage",
        "Oblivious Bookworm",
        "Breakthrough",
    ],
)
def test_discard_outlet_recovered_self_loot(name):
    """ADR-0038 post-giants batch (CR 701.8a, verified via rules-lookup
    this session): the giants wave's last discard_outlet class — "Draw N
    cards. Then discard a card unless <condition>." phrased as TWO
    sentences parks the whole tail as one Unimplemented residue — is now
    recovered by the "discard" ALLOWLIST row; the lane's recovered-node
    direction gate (raw reject-list) admits the bare self imperative.
    Breakthrough's "discard the rest" is the plain one-sentence sibling.
    These also fire discard_makers (a draw + discard in the same unit is
    the loot contract) — a beyond-legacy gain class on that promoted
    lane, adjudicated genuine."""
    assert ("discard_outlet", "you", "") in _idents(name)
    assert ("discard_outlet", "you", "") in _idents("Katara, Seeking Revenge")


@pytest.mark.parametrize("name", ["Nebuchadnezzar", "Bladecoil Serpent"])
def test_discard_outlet_recovered_direction_gate_excludes_opponent(name):
    """The recovered-node direction gate (ADR-0038 post-giants batch): a
    recovered discard's raw is a TRUNCATED clause, so an opponent-directed
    discard can LOOK imperative — Nebuchadnezzar's "discard all cards with
    that name revealed this way" lost its "Target opponent reveals ..."
    subject to the clause split; Bladecoil Serpent's "each opponent
    discards a card" carries it inline. Neither is a self-loot outlet
    (CR 701.8a's discard actor is the affected player, not you)."""
    assert "discard_outlet" not in _keys(name)


def test_discard_outlet_recovered_symmetric_wheel_included():
    """Noxious Vapors ("Each player ... discards all other nonland
    cards") through the recovered path: a SYMMETRIC discard hits you too
    — the Dark Deal wheel precedent — so it IS an outlet (and an
    opponent_discard member, both)."""
    idents = _idents("Noxious Vapors")
    assert ("discard_outlet", "you", "") in idents


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Wrath of God", True),  # DestroyAll creatures
        ("Blasphemous Act", True),  # DamageAll creatures
        ("Merciless Eviction", True),  # mass exile (ChangeZoneAll → Exile)
        ("Languish", True),  # negative PumpAll — typed -4/-4 (structural)
        ("Armageddon", False),  # destroy all LANDS → land_destruction
        ("Living Death", False),  # graveyard-zone mass exile → GY recursion
        ("Knight of Valor", False),  # flanking template — one combat's blocker
        ("Baneblade Scoundrel", False),  # becomes-blocked -1/-1 — not a board
    ],
)
def test_mass_removal_arms_and_gates(name, should_fire):
    """mass_removal fires the four typed wipe arms and excludes the land-only
    sweep and the graveyard mass-exile (CR 115.10 / 406, checklist #2)."""
    assert (("mass_removal", "you", "") in _idents(name)) is should_fire


def test_mass_removal_combat_debuff_vetoes():
    """A flanking-style -1/-1 hits one combat's blockers, never the board
    (CR 702.25a) — but phase drops the "blocking it" clause from the PumpAll
    filter (phase_parse_bug [P12]), leaving Knight of Valor a bare
    WithoutKeyword:Flanking sweep and Baneblade Scoundrel a bare
    Typed[Creature] sweep. Two vetoes restore the scope: the
    WithoutKeyword:Flanking predicate (the flanking template's blocker
    filter) and the becomes_blocked/blocks trigger unit. The combat payoff
    itself still reads (blocked_matters)."""
    assert "mass_removal" not in _keys("Knight of Valor")
    assert "mass_removal" not in _keys("Baneblade Scoundrel")
    assert "blocked_matters" in _keys("Baneblade Scoundrel")
    assert "blocked_matters" in _keys("Knight of Valor")


def test_mass_removal_languish_negative_amount_is_typed():
    """The substrate carries Languish's -4/-4 as a typed Fixed(-4) PumpAll —
    the live raw-only debuff arm reads structurally here (fidelity gain)."""
    from mtg_utils._card_ir.crosswalk import pump_is_negative

    tree = _tree("Languish")
    pump = next(c for c in tree.effect_concepts("pump"))
    assert pump_is_negative(pump.node)


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Evacuation", True),  # BounceAll creatures
        ("Devastation Tide", True),  # BounceAll nonland permanents
        ("Boomerang", False),  # single-target Bounce → bounce_tempo
        ("Cyclonic Rift", False),  # base mode targeted; Overload = parse drop
    ],
)
def test_mass_bounce_mass_gate(name, should_fire):
    """mass_bounce fires only the BounceAll board sweep (CR 115.10). Cyclonic
    Rift's Overload each-mode is a phase modal-alt-cost parse drop
    (phase_parse_bug) — the crosswalk reads only the targeted base mode."""
    assert (("mass_bounce", "any", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Swords to Plowshares", True),  # single-target exile removal
        ("Path to Exile", True),  # sibling put is a DIFFERENT card (Any)
        ("Cloudshift", False),  # exiles YOUR OWN (blink)
        ("Eldrazi Displacer", False),  # sibling TrackedSet return (blink)
        ("Bojuka Bog", False),  # graveyard-zone exile (GY hate)
        ("Merciless Eviction", False),  # mass exile → mass_removal
    ],
)
def test_exile_removal_vetoes(name, should_fire):
    """exile_removal keeps the genuine one-way single-target exile (CR 406.1 /
    115.1) and vetoes blink (own/returned object, checklist #9), graveyard
    zones (checklist #2), and the mass form."""
    assert (("exile_removal", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Avenger of Zendikar", True),  # a token for each land you control
        ("Wilderness Elemental", False),  # scales with OPPONENT lands
        ("Pallimud", False),  # chosen player's lands (SourceChosenPlayer)
    ],
)
def test_lands_matter_controller_gate(name, should_fire):
    """lands_matter reads the count operand's Land population, controller-
    gated (checklist #6 — proactive vs the live ungated arm): an opponent-
    lands punisher is not a your-lands build-around."""
    assert (("lands_matter", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Jolene, the Plunder Queen", ("treasure_matters", "you", "")),  # cost
        ("Wedding Security", ("blood_matters", "you", "")),  # effect
    ],
)
def test_resource_token_sac_payoffs(name, ident):
    """The sacrifice-PAYOFF half of the Treasure/Blood lanes (CR 111.10 /
    701.21, role-split per ADR-0034): a sacrifice effect (Wedding Security)
    or a Composite-nested sacrifice cost (Jolene)."""
    assert ident in _idents(name)


def test_resource_token_matters_role_split():
    """A pure MAKER (Dockside's Treasures; Voldaren Bloodcaster's Blood) fires
    the *_makers lane and never the sacrifice payoff (checklist #4)."""
    assert "treasure_matters" not in _keys("Dockside Extortionist")
    assert "blood_matters" not in _keys("Voldaren Bloodcaster")


def test_resource_token_matters_excludes_non_token_sac():
    """A generic creature sac outlet (Ashnod's Altar) names no Treasure/Blood
    subtype — no resource payoff."""
    keys = _keys("Ashnod's Altar")
    assert "treasure_matters" not in keys
    assert "blood_matters" not in keys


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Glorious Anthem", True),  # generic +1/+1 team anthem
        ("Goblin King", True),  # subtyped "Other Goblins get +1/+1"
        ("Virulent Plague", False),  # -2/-2 hoser — negative values
        ("Shivan Dragon", False),  # activated self firebreathing, not static
    ],
)
def test_anthem_static_group_and_sign_gates(name, should_fire):
    """anthem_static fires a STATIC non-negative +N/+N over a creature group
    (CR 604.3 / 613.4 7c); a debuff and an activated self-pump stay out."""
    assert (("anthem_static", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Craterhoof Behemoth", True),  # +X/+X for each creature you control
        ("Commander's Insignia", True),  # commander-cast count anthem
        ("Shivan Dragon", False),  # fixed +1/+0 firebreathing
        ("Grim Hireling", False),  # -X/-X — a bare X (Variable), not a scale
    ],
)
def test_scaling_pump_gate(name, should_fire):
    """scaling_pump admits a board-count +X/+X (typed dynamic P/T mods) and
    rejects fixed pumps and bare-X activations (CR 107.3, split-lane #4)."""
    assert (("scaling_pump", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3: an Aggregate (Max) qty tag — "the greatest
        # <property> among <population>" is a board-state-driven scaler by
        # construction (CR 107.3), the same category as a bare count.
        "Carrion Grub",  # +X/+0, greatest power among graveyard creatures
        "Emissary Escort",  # +X/+0, greatest mana value among other artifacts
        # A Sum of TWO separate board counts (Ref(ObjectCount) +
        # Ref(ZoneCardCount)) — ``ref_count_qty`` never reaches a ``Sum``'s
        # per-expr list; checked per-expr, any scaling member qualifies.
        "Cid, Timeless Artificer",
        "Desmond Miles",
        # A count condition too complex for phase to structure at all
        # (CR 107.3) degrades the modification to a flat literal ``value``
        # indistinguishable, node-shape-wise, from a genuine fixed anthem —
        # the node's OWN description ("for each"/"equal to the number of")
        # is the only surviving residue.
        "Strata Scythe",  # for each land w/ the same name as the exiled card
        "Nyxathid",  # -1/-1 for each card in the chosen player's hand
        # A token's own self-pump nested two hops deep through a granted
        # ability (``GrantAbility``/``GrantStaticAbility``.definition) —
        # ``iter_mod_sites`` never descends into a modification's OWN
        # ``definition`` field; re-rooted via the generic deep walk (the
        # same ``GrantAbility.definition`` descent
        # ``has_structural_power_tap_engine`` establishes).
        "Urza's Saga",  # Saga chapter grants a Construct-token pump ability
        "Sound the Call",  # token's own GrantStaticAbility pump
        "Iron Man Armor",  # becomes-a-creature GrantStaticAbility pump
        "Dollhouse of Horrors",  # CopyTokenOf additional_modifications
        # An Aggregate value on a plain (non-Pump/PumpAll) AddDynamicPower
        # continuous mod (a Living Weapon Equipment's own stat line).
        "Tangleweave Armor",  # greatest mana value among your commanders
        # Minn's created Illusion token's OWN static (reached directly,
        # no GrantAbility hop — the plain nested-static_abilities path).
        "Minn, Wily Illusionist",
    ],
)
def test_scaling_pump_recovered_dynamic_shapes(name):
    """ADR-0038 W3 batch 3 (CR 107.3 / 613.4c): scaling_pump recovers the
    Aggregate/Sum/GrantAbility-nested/degraded-literal dynamic P/T shapes
    the base ``ref_count_qty``/tag-set gate missed. Verified against the
    real Card IR this session; each card's phase record is pinned in
    ``crosswalk_fixture_cards.json``."""
    assert ("scaling_pump", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 — a ``PumpAll`` mass anthem whose power/
        # toughness is ``Quantity``-wrapped (``T_power__Quantity(value=
        # Ref(...))``) was previously silently under-served: the base gate
        # read ``ref_count_qty`` directly on the unwrapped field, which
        # never matched a ``Quantity`` node, so a genuine board-count mass
        # anthem read as if fixed. Adjudicated GAIN beyond the legacy Card
        # IR (``old_ir_for``'s separate, lossier pipeline structurally
        # drops the "pump" effect's ``amount`` for these entirely — CR
        # 107.3 confirms each is a genuine board-count scaler regardless).
        "Alistair, the Brigadier",  # +X/+X, historic permanents you control
        "Cloudkill",  # -X/-X, greatest mana value of a commander you own
        "Jazal Goldmane",  # attacking creatures +X/+X, # of attackers
    ],
)
def test_scaling_pump_pumpall_quantity_unwrap_gain(name):
    """ADR-0038 W3 batch 3: the ``PumpAll`` ``Quantity``-unwrap fix (CR
    107.3) is an adjudicated GAIN beyond the legacy Card IR's own blind
    spot for these mass-anthem shapes — verified structurally correct
    against the real Card IR this session."""
    assert ("scaling_pump", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 (PROMOTED): the single-target ``Pump`` tag
        # (Goblin Piledriver's "+2/+0 ... for each other attacking Goblin")
        # is the SAME CR 107.3 / 613.4c board-count scaler as a mass
        # ``PumpAll`` — these are the 5 originally-live_only cards this
        # key's promotion recovers, one per required-widening reason.
        "Embiggen",  # ObjectTypelineComponentCount widening (target's own
        # supertype/type/subtype count — CR 205.1)
        "Gold Rush",  # Typed target, ObjectCount (Treasures) — already-
        # accepted qty tag, needed only the Pump-tag admit
        "Gran Pulse Ochu",  # ZoneCardCount widening (own graveyard)
        "Ral's Staticaster",  # ZoneCardCount widening (own hand)
        "Sunbathing Rootwalla",  # SelfRef, BasicLandTypeCount (Domain) —
        # already-accepted qty tag, needed only the Pump-tag admit
    ],
)
def test_scaling_pump_single_target_recovered(name):
    """ADR-0038 W3 batch 4 (CR 107.3, 613.4c): re-admitting the single-
    target ``Pump`` tag (alongside ``PumpAll``) in ``_pump_scaling_lanes``,
    plus widening ``_SCALING_QTY_TAGS`` with ``ZoneCardCount`` and
    ``ObjectTypelineComponentCount``, recovers every one of the 5 genuine
    legacy-recognized members this key was residual over. 0 genuine members
    lost vs a live corpus re-measure this session."""
    assert ("scaling_pump", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 4 — representative BEYOND-LEGACY gains, one per
        # accepted single-target-Pump sub-shape (every sub-shape in the
        # ~130-card corpus was read + classified this session; the target
        # tag never gates ``scaling_pump`` — see docstring).
        "Goblin Piledriver",  # SelfRef firebreather, tribal ObjectCount
        "Herald of Amity",  # Typed target-creature grant, Aura ObjectCount
        "General Marhault Elsdragon",  # TriggeringSource team-enabler
        # ("whenever a creature you control becomes blocked, IT gets...")
        "Growth Cycle",  # ParentTarget same-object chain ("Target creature
        # gets +3/+3... It gets an additional +2/+2 for each...")
        "Dark Salvation",  # phase mis-tags ``target=Player`` (the pump's
        # qty scope is "that player['s Zombies]", not the actual target
        # creature) — the lane never gates on ``target``, so this still
        # fires correctly regardless of the position-relative mistag.
        "Bonehoard",  # ZoneCardCount widening via the mod-site path (all
        # graveyards' creature cards) — a Living Weapon Equipment's own
        # continuous ``AddDynamicPower``/``AddDynamicToughness``.
        "Knight of the Reliquary",  # ZoneCardCount widening (own graveyard
        # land cards), a creature's own static self-pump.
        "Wight of Precinct Six",  # ZoneCardCount widening (opponents'
        # graveyards' creature cards).
    ],
)
def test_scaling_pump_single_target_subshapes(name):
    """ADR-0038 W3 batch 4: every single-target-Pump sub-shape (by phase's
    ``target`` tag: SelfRef / Typed / TriggeringSource / ParentTarget /
    Player) fires ``scaling_pump`` — no card-count/target-type veto
    separates a genuine class here (tried and rejected this session; the
    boundary is the qty TAG, not the counted population or the target
    shape). CR 107.3, 613.4c."""
    assert ("scaling_pump", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Giant Growth",  # single-target Pump, FIXED +3/+3 — Typed target,
        # no qty tag at all; never scales regardless of the tag widening.
        "Mana-Charged Dragon",  # single-target Pump, SelfRef target, bare-X
        # ("mana paid this way" — Variable) qty; a cost/choice echo stays
        # excluded even for a single-target Pump (split-lane #4).
    ],
)
def test_scaling_pump_single_target_still_excludes_non_scaling(name):
    """ADR-0038 W3 batch 4 guard: admitting the single-target ``Pump`` tag
    does not admit a FIXED pump or a bare-X cost-echo — ``_is_scaling_count``
    still gates both (CR 107.3)."""
    assert "scaling_pump" not in _keys(name)


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Commander's Insignia", True),  # creatures YOU control team anthem
        ("Craterhoof Behemoth", True),  # one-shot team scaling anthem
        ("Coat of Arms", False),  # symmetric "each creature" — controller any
        ("Shivan Dragon", False),  # single-target self pump
        # ADR-0038 W3 batch 4: a genuine scaling single-target Pump is
        # NEVER a count_anthem, however it scales — that stays PumpAll-only
        # (checklist #6, re-confirmed post the single-target Pump admit).
        ("Goblin Piledriver", False),
        ("Herald of Amity", False),
    ],
)
def test_count_anthem_team_subject_gate(name, should_fire):
    """count_anthem is the TEAM-subject subset of scaling_pump: a generic
    creatures-you-control affected filter (checklist #6 — a symmetric global
    is not a your-team anthem)."""
    assert (("count_anthem", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Shivan Dragon", True),  # {R}: +1/+0 firebreather (Pump SelfRef)
        ("Walking Ballista", True),  # {4}: put a +1/+1 counter on SELF
        ("Glorious Anthem", False),  # static team anthem, not activated
        ("Grim Hireling", False),  # activated pump of a TARGET creature
    ],
)
def test_self_pump_activated_self_anchor(name, should_fire):
    """self_pump fires the activated SELF pump / self +1/+1 placement (the
    mana-sink shape, CR 122.1); statics and target-pumps stay out."""
    assert (("self_pump", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Always Watching", True),  # nontoken creatures you control: vigilance
        ("Akroma's Memorial", True),  # broad evergreen union grant
        ("Craterhoof Behemoth", True),  # one-shot team "gain trample"
        ("Goblin King", False),  # tribal (subtyped) grant → type_matters
        ("Grizzly Bears", False),  # no grant at all
    ],
)
def test_team_buff_generic_team_gate(name, should_fire):
    """team_buff fires an evergreen keyword granted to your GENERIC creature
    board (CR 604.3 / 702); a tribal narrowing fails the gate (checklist
    #6)."""
    assert (("team_buff", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Sneak Attack", True),  # creature from hand
        ("Elvish Piper", True),  # creature from hand (activated)
        ("Bribery", True),  # from an OPPONENT's library — still your cheat
        ("Burgeoning", False),  # a LAND put → extra_land_drop
        ("Leyline of Anticipation", False),  # opening-hand BeginGame setup
        # phase drops "basic land" to filter Any — no type evidence, no guess
        # (a supplement-fixable parse drop, reported for adjudication):
        ("Planar Engineering", False),
        # the punished player's compensation fetch (ParentTargetController):
        ("Settle the Wreckage", False),
    ],
)
def test_cheat_into_play_gates(name, should_fire):
    """cheat_into_play fires the non-land Hand/Library→Battlefield put (CR
    110.2 / 400.7); the land carve-out and the typed BeginGame opening-hand
    kind stay out (checklist #2/#4)."""
    assert (("cheat_into_play", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Light Up the Stage", True),  # ExileTop + PlayFromExile grant
        ("Act on Impulse", True),
        ("Etali, Primal Storm", True),  # ExileTop + CastFromZone sibling
        ("Bolas's Citadel", False),  # ONGOING static → play_from_top
        ("Aloe Alchemist", False),  # Plotted grant, no ExileTop — plot only
        ("Gonti, Night Minister", False),  # opponent-library theft engine
    ],
)
def test_impulse_top_play_sibling_pair(name, should_fire):
    """impulse_top_play needs the exile-the-top + play-permission SIBLING pair
    in one non-static unit (CR 601.3b, granularity a); the ongoing static
    permission is the disjoint play_from_top lane (checklist #3)."""
    assert (("impulse_top_play", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Bolas's Citadel", True),  # TopOfLibraryCastPermission static mode
        ("Future Sight", True),
        ("Light Up the Stage", False),  # one-shot impulse, not ongoing
        ("Capricious Sliver", False),  # granted impulse trigger (Continuous)
    ],
)
def test_play_from_top_static_mode(name, should_fire):
    """play_from_top reads phase's dedicated TopOfLibraryCastPermission static
    mode (CR 116 / 601.3b) — the granted-impulse static (Capricious Sliver)
    carries a different mode and stays out structurally (no raw veto
    needed)."""
    assert (("play_from_top", "you", "") in _idents(name)) is should_fire


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Bioshift", True),  # MoveCounters counter_type P1P1
        ("Walking Ballista", True),  # remove-as-COST {OfType: P1P1}
        ("Carnifex Demon", True),  # Composite cost, {OfType: M1M1}
        ("Tangle Wire", False),  # fade-counter remove — kind gate
        ("Power Conduit", False),  # kindless {Any} remove — not p1p1/m1m1
    ],
)
def test_counter_manipulation_kind_gate(name, should_fire):
    """counter_manipulation fires the +1/+1 / -1/-1 move-or-remove (CR 122.1 /
    122.6), including the remove-as-cost read through Composite nesting; the
    kind gate keeps fade/charge/kindless spends out (split-lane #4)."""
    assert (("counter_manipulation", "you", "") in _idents(name)) is should_fire


# ── batch 9: discard/draw payoffs, death loops, engines, library-top, grants ─


def test_discard_matters_cycle_is_discard():
    """CR 702.29a: cycling IS a discard — Archfiend of Ifnir's
    ``CycledOrDiscarded`` trigger fires discard_matters (watcher not the
    opponent)."""
    assert ("discard_matters", "you", "") in _idents("Archfiend of Ifnir")


def test_discard_matters_opponent_watcher_routes_to_opponent_discard():
    """Megrim watches the OPPONENT's discard (``valid_card`` controller
    Opponent — checklist #5: the recipient node, never the mislabeled
    trigger_scope) → the disjoint opponent_discard punisher lane, never
    discard_matters."""
    assert "discard_matters" not in _keys("Megrim")
    assert ("opponent_discard", "opponents", "") in _idents("Megrim")


def test_discard_matters_excludes_loot_outlet():
    """Careful Study is a loot OUTLET (draw+discard effects, no Discarded
    trigger) — discard_makers, never the payoff lane."""
    keys = _keys("Careful Study")
    assert "discard_matters" not in keys
    assert "discard_makers" in keys


@pytest.mark.parametrize("name", ["Nekusar, the Mindrazer", "Underworld Dreams"])
def test_opponent_draw_matters_fires(name):
    """A ``Drawn`` trigger watching the opponents (CR 121.1) fires the
    wheel-punisher lane, scope "opponents"."""
    assert ("opponent_draw_matters", "opponents", "") in _idents(name)


def test_opponent_draw_matters_disjoint_from_draw_matters():
    """Niv-Mizzet, Parun watches YOUR draws → draw_matters only; the two
    scope-gated lanes stay set-disjoint."""
    assert "opponent_draw_matters" not in _keys("Niv-Mizzet, Parun")
    assert ("draw_matters", "you", "") in _idents("Niv-Mizzet, Parun")
    assert "draw_matters" not in _keys("Underworld Dreams")


@pytest.mark.parametrize("name", ["Solemn Simulacrum", "Kokusho, the Evening Star"])
def test_self_death_payoff_fires(name):
    """A SelfRef dies trigger with a recognized payoff (Solemn's draw,
    Kokusho's drain — CR 700.4 / 603.6c) fires self_death_payoff."""
    assert ("self_death_payoff", "you", "") in _idents(name)


def test_self_death_payoff_excludes_aristocrats_and_self_return():
    """Blood Artist's subject-bearing watcher is death_matters (the
    aristocrats lane); Kitchen Finks' dies unit carries only the persist
    SELF-RETURN (→ dies_recursion), not a death VALUE payoff."""
    assert "self_death_payoff" not in _keys("Blood Artist")
    assert "self_death_payoff" not in _keys("Kitchen Finks")


def test_self_death_payoff_excludes_shuffle_back_protection():
    """Kozilek's "put into a graveyard from anywhere → shuffle that
    graveyard into its owner's library" is self-preservation (a dies-to-
    Library move), never a death VALUE payoff."""
    assert "self_death_payoff" not in _keys("Kozilek, Butcher of Truth")


@pytest.mark.parametrize("name", ["Young Wolf", "Kitchen Finks", "Feign Death"])
def test_dies_recursion_structural(name):
    """The dies-self-return shape (CR 702.93a undying / 702.79a persist)
    fires dies_recursion: the bearers parse to the literal dies-return
    trigger (Young Wolf, Kitchen Finks) and the GRANT form walks the
    GrantTrigger subtree (Feign Death)."""
    assert ("dies_recursion", "you", "") in _idents(name)


def test_dies_recursion_excludes_value_payoff_and_reanimate():
    """Solemn Simulacrum's dies-draw has no self-return (→
    self_death_payoff); Reanimate returns OTHERS from a graveyard (→
    creature_recursion/reanimator), never dies_recursion."""
    assert "dies_recursion" not in _keys("Solemn Simulacrum")
    assert "dies_recursion" not in _keys("Reanimate")


# ADR-0038 W3 batch 2 unit 3 — the dies_recursion AddKeyword{Persist/
# Undying} arm (CR 702.93a/702.79a): the keyword ITSELF is the dies-return
# ability, so granting it — to self (activated/conditional-static), another
# creature (an ETB/spell grant), or a typed filter (a team-wide "other
# creatures have undying" lord) — is dies-recursion tech regardless of the
# grant's own trigger/static/activated shape or nesting depth (Haunted
# One's grant nests TWICE: GrantStaticAbility -> GrantTrigger -> pump
# sub-ability's AddKeyword).
@pytest.mark.parametrize(
    "name",
    [
        "Antler Skulkin",  # activated, grants to a TARGET creature
        "Cauldron Haze",  # spell, grants to any number of targets
        "Cauldron of Souls",  # activated, grants to any number of targets
        "Dusk Legion Sergeant",  # activated, grants to a typed filter
        "Endling",  # activated, self-grant
        "Isilu, Carrier of Twilight",  # static, typed-filter grant
        "Mikaeus, the Unhallowed",  # static, "other creatures … have undying"
        "Rattleblaze Scarecrow",  # conditional static self-grant
        "Rhys, the Evermore",  # ETB trigger, grants to a target
        "Undying Evil",  # instant, grants to a target
        "Wingrattle Scarecrow",  # conditional static self-grant
        "Haunted One",  # doubly-nested commander grant
    ],
)
def test_dies_recursion_add_keyword_grant_arm(name):
    assert ("dies_recursion", "you", "") in _idents(name)


# ADR-0038 W3 batch 2 unit 3 — the dies_recursion Aura/Equipment AttachedTo
# watcher arm: "When enchanted/equipped creature dies, return it/this card
# to the battlefield" widens the trigger's own watcher from a bare
# ``SelfRef`` to an Aura's ``AttachedTo`` (CR 303.4c) — the Aura/Equipment
# GRANTS the attached creature (or itself) dies-recursion, so the
# Aura/Equipment card is the dies_recursion member.
@pytest.mark.parametrize(
    "name",
    [
        "Changing Loyalty",  # returns the enchanted CREATURE
        "Fungal Fortitude",  # returns the enchanted CREATURE, tapped
        "Journey to Eternity",  # returns the creature, then flips itself
        "Abduction",  # returns the enchanted creature (control-theft Aura)
        "Avatar Destiny",  # returns the enchanted creature
        "False Demise",  # returns the ENCHANTED CARD (Aura self-return)
        "Fool's Demise",  # returns the ENCHANTED CARD
        "Ghoulish Impetus",  # returns the ENCHANTED CARD
        "Gift of Immortality",  # returns the ENCHANTED CARD
        "Infectious Rage",  # returns the ENCHANTED CARD
        "Kaya's Ghostform",  # dies OR exile, returns the ENCHANTED CARD
        "Minion's Return",  # returns the ENCHANTED CARD
        "Necrogen Communion",  # returns the ENCHANTED CARD
        "Necrotic Plague",  # returns the ENCHANTED CARD to a new host
        "Next of Kin",  # returns the ENCHANTED CARD
        "Oathkeeper, Takeno's Daisho",  # Equipment: equipped creature dies
        "Radiant Grace",  # returns the ENCHANTED CARD, flips itself
        "Reins of the Vinesteed",  # returns the ENCHANTED CARD
        "Resurrection Orb",  # Equipment: equipped creature dies
        "Screams from Within",  # returns the ENCHANTED CARD
        "Shade's Form",  # returns the ENCHANTED CARD
        "Skin Invasion",  # returns the ENCHANTED CARD, flips itself
        "Takklemaggot",  # returns the ENCHANTED CARD to a new host
        "Unhallowed Pact",  # returns the ENCHANTED CARD
        "Unholy Indenture",  # returns the ENCHANTED CARD with a counter
    ],
)
def test_dies_recursion_aura_equipment_attached_to_arm(name):
    assert ("dies_recursion", "you", "") in _idents(name)


# ADR-0038 W3 batch 2 unit 3 — the dies_recursion own-dies self-return arm
# (a creature's OWN dies trigger, no keyword — the SAME "return it to the
# battlefield" shape Young Wolf's undying expands to, just spelled out in
# full oracle text instead of a keyword): a plain conditional return
# (Old-Growth Troll, Reborn Hero, Wave of Rats, Tenacious Dead, Retched
# Wretch, Unstoppable Slasher, Infernal Vessel, Princess Yue), a Phoenix-
# style modal branch (Bogardan Phoenix, Lamplight Phoenix), a
# same-type-share condition (Fang Roku's Companion, Otherworldly Escort),
# a self-transforming Aura-Land loop (Harold and Bob, Earth Village
# Ruffians' land-creature analog), an exile-then-reattach (Lucius the
# Eternal), and a delayed-trigger return AT THE BEGINNING OF THE NEXT END
# STEP (Loyal Cathar — a flat ``ParentTarget`` with NO producer effect
# preceding it, so it binds to the trigger's own source); a player-chosen
# attach point that still returns under YOUR OWN control (Accursed
# Witch's "attached to target opponent", ``enters_under: You`` — also a
# no-producer flat ``ParentTarget``) stays included — only an
# ambiguous/opponent-owned return excludes (the sibling hot-potato test
# below).
@pytest.mark.parametrize(
    "name",
    [
        "Old-Growth Troll",
        "Reborn Hero",
        "Wave of Rats",
        "Tenacious Dead",
        "Retched Wretch",
        "Unstoppable Slasher",
        "Infernal Vessel",
        "Princess Yue",
        "Bogardan Phoenix",
        "Lamplight Phoenix",
        "Fang, Roku's Companion",
        "Otherworldly Escort",
        "Harold and Bob, First Numens",
        "Earth Village Ruffians",
        "Lucius the Eternal",
        "Loyal Cathar",
        "Accursed Witch",
        "Nine-Lives Familiar",
    ],
)
def test_dies_recursion_own_dies_self_return_arm(name):
    assert ("dies_recursion", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Matter Reshaper", "Clone Shell", "Summoner's Egg"])
def test_dies_recursion_excludes_dies_value_of_another_card(name):
    """The lane's contract is CR 702.93a/702.79a's "return IT to the
    battlefield" — the SAME object that died (CR 603.6c's
    leaves-the-battlefield reference). A dies trigger that puts a
    DIFFERENT card onto the battlefield is dies-VALUE, not recursion:
    Matter Reshaper's revealed top card (phase back-refs it
    ``ParentTarget`` AFTER a ``RevealTop`` producer — the produced card,
    not the dying self) and Clone Shell / Summoner's Egg's face-down
    imprinted card (``TriggeringSource`` next to a ``TurnFaceUp``
    producer). Adjudication override of the W3-batch-2 unit-3 widening,
    which pinned these three as members — conflating two inherently
    different properties (a repeatable death-loop body vs one-shot
    cheat-into-play advantage)."""
    assert "dies_recursion" not in _keys(name)


# ADR-0038 W3 batch 2 unit 3 — the "Enduring" cycle (Bloomburrow):
# "Enchantment Creature — <Animal> Glimmer" bodies whose dies trigger
# returns as a NON-creature enchantment. Own-dies self-return, listed
# separately only because the whole cycle shares one design (CR 700.4).
@pytest.mark.parametrize(
    "name",
    [
        "Enduring Courage",
        "Enduring Curiosity",
        "Enduring Innocence",
        "Enduring Tenacity",
        "Enduring Vitality",
    ],
)
def test_dies_recursion_enduring_cycle(name):
    assert ("dies_recursion", "you", "") in _idents(name)


def test_dies_recursion_replacement_then_delayed_return():
    """Darigaaz Reincarnated's "If ~ would die, instead exile it with three
    egg counters on it" (a REPLACEMENT redirect, CR 614.1 — not a dies
    TRIGGER) + a separate later counter-driven upkeep trigger that
    eventually returns it to the battlefield is a phoenix analog of CR
    702.93a/79a's self-return, read via the DEDICATED replacement+delayed-
    return arm (:func:`_has_exile_then_return_replacement`)."""
    assert ("dies_recursion", "you", "") in _idents("Darigaaz Reincarnated")


def test_dies_recursion_excludes_hot_potato_return():
    """Endless Whispers's "choose target opponent. That player puts this
    card … onto the battlefield UNDER THEIR CONTROL" hands the returned
    object to the CHOSEN opponent (``enters_under`` unset, not "You") — a
    hot-potato give-away, not personal recursion value; legacy never fires
    dies_recursion here either. The discriminator: a player-chosen dies
    trigger is excluded UNLESS the matched return explicitly says
    ``enters_under: "You"`` (Accursed Witch's sibling test keeps that
    case)."""
    assert "dies_recursion" not in _keys("Endless Whispers")


@pytest.mark.parametrize(
    "name", ["Alesha, Who Smiles at Death", "Reanimate", "Soul Salvage"]
)
def test_creature_recursion_arms(name):
    """creature_recursion fires the GY→battlefield reanimation arm (Alesha,
    Reanimate) and the GY→hand recall arm (Soul Salvage — Bounce over a
    Creature ``InZone: Graveyard``). CR 700.4 / 404."""
    assert ("creature_recursion", "you", "") in _idents(name)


def test_creature_recursion_needs_creature_core_and_gy_zone():
    """Regrowth's "target card" has no Creature core → no fire (never
    guess); a battlefield bounce (Boomerang) has no graveyard zone → tempo,
    not recursion."""
    assert "creature_recursion" not in _keys("Regrowth")
    assert "creature_recursion" not in _keys("Boomerang")


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("Divination", "you"),  # Draw Fixed 2 — the bulk arm
        ("Phyrexian Arena", "you"),  # Phase Upkeep + Draw Controller
        ("Howling Mine", "each"),  # Phase Draw + ScopedPlayer recipient
        ("Alhammarret's Archive", "you"),  # Draw-replacement (event=Draw)
    ],
)
def test_card_draw_engine_structural_arms(name, scope):
    """card_draw_engine reads the typed amount, the Phase-mode trigger unit
    (the anchor and the Draw SHARE a unit — granularity a, the read the
    stale live-mirror justification said phase couldn't carry), and the
    Draw-replacement doubler (CR 121.1/121.2)."""
    assert ("card_draw_engine", scope, "") in _idents(name)


@pytest.mark.parametrize("name", ["Opt", "Elvish Visionary"])
def test_card_draw_engine_excludes_cantrips(name):
    """A bare cantrip (Opt — count 1) and a one-shot ETB draw (Elvish
    Visionary — the live mirror's ETB skip) are not engines."""
    assert "card_draw_engine" not in _keys(name)


def test_group_hug_draw_player_scope_all():
    """Temple Bell's Draw rides a ``player_scope: All`` wrapper ("each
    player draws a card" — CR 121.1) → group_hug_draw each."""
    assert ("group_hug_draw", "each", "") in _idents("Temple Bell")


def test_group_hug_draw_excludes_controller_draw():
    """Divination draws for YOU only — no group gift."""
    assert "group_hug_draw" not in _keys("Divination")


def test_group_hug_draw_excludes_scoped_player_each_draw():
    """Howling Mine's each-player Phase-trigger Draw carries the
    ``ScopedPlayer`` recipient — that's card_draw_engine's each-arm
    (CR 121.1), NOT the group-hug gift; ``ScopedPlayer`` is deliberately
    absent from ``_EACH_DRAW_RECIPIENTS``."""
    assert "group_hug_draw" not in _keys("Howling Mine")


def test_group_hug_draw_dropped_subject_synthesis():
    """Stage-A recovery (ADR-0037/0038): Grothama, All-Devouring's
    leaves-the-battlefield trigger ("each player draws cards equal to the
    damage dealt to ~ this turn by sources they control") lands in phase as
    an Unimplemented effect whose own raw text is just the damage-count
    clause — the "each player" SUBJECT is consumed by phase's own parse and
    survives only in the whole-card oracle, so re-decoration (which reads
    the clause's own text) can't reach it.
    ``tree_synthesis._arm_group_hug_draw`` fills the gap from
    ``tree.oracle`` instead, emitting the REAL "draw" concept with
    ``scope="each"`` (ADR-0037/0038, no ``synth_*`` marker), read by the
    lane's synthesized-node branch."""
    assert ("group_hug_draw", "each", "") in _idents("Grothama, All-Devouring")


def test_target_player_draws_directed():
    """Bloodgift Demon's Draw carries the typed ``Player`` recipient (a
    directed/forced draw, CR 121.1) → target_player_draws any."""
    assert ("target_player_draws", "any", "") in _idents("Bloodgift Demon")


def test_target_player_draws_excludes_self_loot_and_group():
    """Careful Study's draw is ``Controller`` (the v0.8.0 self-loot phantom
    is typed away in v0.9.0 — pinned regardless); Temple Bell's each-player
    draw is the group lane."""
    assert "target_player_draws" not in _keys("Careful Study")
    assert "target_player_draws" not in _keys("Temple Bell")


def test_target_player_draws_excludes_replacement_tax():
    """Chains of Mephistopheles' replacement rewrites the draw ("… discards
    a card [and draws] instead") — a rules rewrite, not a directed forced
    draw; replacement units are skipped."""
    assert "target_player_draws" not in _keys("Chains of Mephistopheles")


def test_activated_draw_tap_gate():
    """Sensei's Divining Top's ``{T}: draw`` fires activated_draw (CR
    601.2b); Archfiend of Ifnir's cycling (``Composite[Mana, Discard]``, no
    Tap leaf) stays out."""
    assert ("activated_draw", "you", "") in _idents("Sensei's Divining Top")
    assert "activated_draw" not in _keys("Archfiend of Ifnir")


@pytest.mark.parametrize("name", ["Preordain", "Sensei's Divining Top"])
def test_topdeck_selection_fires(name):
    """topdeck_selection fires the first-class Scry doer (Preordain) and the
    controller-owned Dig-to-library (SDT). CR 701.22 / 401.1."""
    assert ("topdeck_selection", "you", "") in _idents(name)


def test_topdeck_selection_excludes_opponent_peek():
    """Orcish Spy digs an OPPONENT's library (``player: Player``) — the
    library OWNER is the boundary (checklist #5)."""
    assert "topdeck_selection" not in _keys("Orcish Spy")


def test_topdeck_selection_excludes_search_reveal():
    """Auditore Ambush's "searches their library … reveals it" found-card
    reveal is phase-mislabeled ``RevealTop(player=Controller)`` inside the
    SAME unit as the ``SearchLibrary`` (phase_parse_bug — a found-card
    reveal is not a top-of-library reveal, CR 701.23). The co-residence
    veto keeps the tutor-reveal out; the standalone RevealTop doer still
    fires (rules-lawyer-adjudicated, batch 9)."""
    assert "topdeck_selection" not in _keys("Auditore Ambush")


# ADR-0038 W4 giant (topdeck_selection promotion): five widened/new arms +
# the raw-bleed bucket-B idiom, each pinned against a fixture-built tree.
# CR citations verified via rules-lookup this session (701.13a exile /
# 701.17 mill / 701.20a reveal / 701.22a scry / 701.25a surveil / 401.1
# library-zone ownership / 401.5 look-at-top statics).


def test_topdeck_selection_exile_top_impulse():
    """Urza, Lord High Artificer's "exile the top card" impulse-draw activation
    is an ``ExileTop(player=Controller)`` doer (CR 701.13a) — a shape the
    deleted SWEEP regex's "look at"/"reveal" alternatives never covered."""
    assert ("topdeck_selection", "you", "") in _idents("Urza, Lord High Artificer")


def test_topdeck_selection_reveal_until_dig():
    """Hermit Druid's "reveal cards from the top of your library until you
    reveal a nonland card" is a ``RevealUntil`` dig-until (CR 701.20a) whose
    digger (:func:`reveal_until_player`) resolves "you"."""
    assert ("topdeck_selection", "you", "") in _idents("Hermit Druid")


def test_topdeck_selection_may_look_at_top_static():
    """Bolas's Citadel's "You may look at the top card of your library any
    time" is a ``MayLookAtTopOfLibrary`` static mode (CR 401.5) — the
    deleted SWEEP regex's "top N cards" grammar can't express a bare "top
    card" with no count word, so this whole class was legacy-uncovered."""
    assert ("topdeck_selection", "you", "") in _idents("Bolas's Citadel")


def test_topdeck_selection_mill_then_battlefield():
    """Eivor, Wolf-Kissed's "mill that many cards. You may put a ... card
    from among them onto the battlefield" is a Mill + ChangeZone(Battlefield,
    TrackedSetFiltered) back-reference (CR 701.17 mill / 401.1)."""
    assert ("topdeck_selection", "you", "") in _idents("Eivor, Wolf-Kissed")


def test_topdeck_selection_manifest_bucket_b():
    """Whisperwood Elemental's granted "manifest the top card of your
    library" (CR 701.40) has no Scry/Surveil/Dig/RevealTop/ExileTop node at
    all — the bucket-B verb+top-phrase text idiom is the only way in."""
    assert ("topdeck_selection", "you", "") in _idents("Whisperwood Elemental")


def test_topdeck_selection_exile_top_activated_cost_bucket_b():
    """Arc-Slogger's "Exile the top ten cards of your library: ~ deals 2
    damage ..." activation cost folds into a bare ``Unimplemented`` cost
    node (no ExileTop) — the bucket-B text idiom (CR 701.13a) recovers it."""
    assert ("topdeck_selection", "you", "") in _idents("Arc-Slogger")


def test_topdeck_selection_excludes_opponent_library_exile_top():
    """Gonti, Lord of Luxury digs a TARGET OPPONENT's library with
    ``Dig(player=Controller)`` — the node's ``player`` field names who
    PERFORMS the dig, never whose library it is (CR 401.1); the raw-text
    owner veto (:func:`_topdeck_owner_ok`) is load-bearing here."""
    assert "topdeck_selection" not in _keys("Gonti, Lord of Luxury")


@pytest.mark.parametrize(
    "name",
    [
        "Arjun, the Shifting Flame",  # bottom-of-library, not top (legacy bug)
        "Winter, Cynical Opportunist",  # unrelated Delirium clause bleed
        "Ecological Appreciation",  # tutor-and-reveal, no "top" text at all
    ],
)
def test_topdeck_selection_adjudicated_sheds(name):
    """Three genuine legacy ``old_ir_for`` false positives this session's
    corpus re-measure found and deliberately does NOT reproduce (ADR-0038
    W4 giant batch, live_only 440 -> 4, all adjudicated) — none is a real
    top-of-library curation instance."""
    assert "topdeck_selection" not in _keys(name)


@pytest.mark.parametrize("name", ["Brainstorm", "Sensei's Divining Top"])
def test_topdeck_stack_fires(name):
    """topdeck_stack fires the hand-to-top put (Brainstorm — filter
    controller You) and the SelfRef top put (SDT). CR 401.4."""
    assert ("topdeck_stack", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Chronostutter",  # NthFromTop — precise-insertion removal
        "Griptide",  # bounce-to-top REMOVAL (controller None)
        "Aethermage's Touch",  # rest-to-Bottom cleanup
    ],
)
def test_topdeck_stack_position_and_owner_gates(name):
    """The position gate (Top only) and the owner gate (You/SelfRef) keep
    tuck-removal and cleanup puts out (CR 401.4)."""
    assert "topdeck_stack" not in _keys(name)


@pytest.mark.parametrize("name", ["Anafenza, the Foremost", "Accorder Paladin"])
def test_combat_buff_engine_fires(name):
    """A combat-frame trigger + a pump/counter effect in the SAME unit fires
    combat_buff_engine (CR 508): Anafenza's attack counter; Accorder
    Paladin's Battle-cry expansion (the keyword-payoff recall — checklist
    #3)."""
    assert ("combat_buff_engine", "you", "") in _idents(name)


def test_combat_buff_engine_excludes_combat_damage():
    """Skirk Commando's DamageDone trigger is deliberately excluded so
    Renown/self_counter_grow shapes never over-fire."""
    assert "combat_buff_engine" not in _keys("Skirk Commando")


def test_land_sacrifice_matters_gitrog():
    """The Gitrog Monster's ``ChangesZoneAll`` → Graveyard land watcher
    (§0.2 mass-mode derivation) fires land_sacrifice_matters; the upkeep
    sac OUTLET stays the disjoint land_sacrifice_makers key."""
    assert ("land_sacrifice_matters", "you", "") in _idents("The Gitrog Monster")


def test_land_sacrifice_matters_excludes_landfall():
    """A land-ETB watcher (Lotus Cobra) is the landfall lane, not the
    lands-to-graveyard payoff."""
    assert "land_sacrifice_matters" not in _keys("Lotus Cobra")


def test_exile_matters_watcher():
    """Ketramose's dest-Exile watcher over a non-self subject fires
    exile_matters (CR 406.1)."""
    assert ("exile_matters", "you", "") in _idents("Ketramose, the New Dawn")


def test_exile_matters_count_operand():
    """recall-completion b2 (ADR-0034): a P/T / X scaler that COUNTS cards standing
    in exile (Beacon Bolt — "damage equal to the instant/sorcery cards you own in
    exile and your graveyard") carries a ZoneCardCount over the exile zone in its
    amount → exile_matters. A structural count-operand read distinct from to:exile
    removal / from:exile cast (CR 406.1)."""
    assert ("exile_matters", "you", "") in _idents("Beacon Bolt")


def test_exile_matters_excludes_self_state_and_dig_cast():
    """God-Eternal Bontu's "when this is exiled" is SELF-state (the live
    #24b boundary); Aetherworks Marvel exiles as part of a dig-cast with no
    exile-watcher trigger; Kaya's Ghostform watches its ENCHANTED object
    (``AttachedTo`` — recursion insurance on one object, not
    exile-as-resource)."""
    assert "exile_matters" not in _keys("God-Eternal Bontu")
    assert "exile_matters" not in _keys("Aetherworks Marvel")
    assert "exile_matters" not in _keys("Kaya's Ghostform")


@pytest.mark.parametrize("name", ["Crackling Drake", "Cosmogoyf"])
def test_exile_matters_static_pt_scaler_arm(name):
    """ADR-0038 W3 batch 5: a characteristic-defining P/T-setting static
    ability carries its exile-zone count operand inside ``modifications``,
    not on an ``amount``/``count``/``value`` effect field — STATIC units
    never populate ``unit.effects`` at all, so the existing count-operand arm
    never reaches it. A direct deep scan of the static node's subtree finds
    either shape: Crackling Drake's ``ZoneCardCount{zone: Exile}``
    ("total number of instant and sorcery cards you own in exile and in your
    graveyard") or Cosmogoyf's plain ``ObjectCount`` over an
    ``InZone{zone: Exile}``-filtered card count ("number of cards you own in
    exile"). CR 406.1 / 613.4c."""
    assert ("exile_matters", "you", "") in _idents(name)


def test_exile_matters_exiled_with_source_arm():
    """ADR-0038 W3 batch 5: Gorex's "choose a card at random exiled with
    Gorex" reads directly from the standing exile pile a MAKER put there
    earlier — a ``ChooseFromZone{zone: Exile, filter: ExiledBySource}``. CR
    406.1."""
    assert ("exile_matters", "you", "") in _idents("Gorex, the Tombshell")


def test_exile_matters_excludes_bare_choose_from_zone_pile_staging():
    """ADR-0038 W3 batch 5 shed: phase emits a BARE
    ``ChooseFromZone{zone: Exile, filter: MISSING}`` as an internal staging
    detail for "look at the top N, separate into piles, choose one" effects
    (Steam Augury) — the piles sit in exile as an implementation artifact,
    never named "exile" in the oracle text at all. Corpus census found 71
    such cards; the ``filter: ExiledBySource`` gate (Gorex, above) is the
    load-bearing discriminant that keeps this lane from flooding on them."""
    assert "exile_matters" not in _keys("Steam Augury")


@pytest.mark.parametrize("name", ["Psychomancer", "Laelia, the Blade Reforged"])
def test_exile_matters_trigger_watcher_baseline_population(name):
    """ADR-0038 W3 batch 6: the pre-existing trigger-watcher arm (a
    ``ChangesZone`` destination-Exile trigger over a NON-self subject) was
    already firing correctly on a ~10-card population the legacy regex never
    recognized (cw_only, unpinned since batch 5). Investigated this session
    (per-card CR reading, not dismissed as noise): Psychomancer's "put into a
    graveyard from the battlefield OR is put into exile from the battlefield"
    hybrid dies/exile watcher and Laelia's "one or more cards are put into
    exile from your library and/or your graveyard" both explicitly watch
    cards landing in exile as a build-around resource — CR 406.1. No code
    change was needed; this pins the population so it stops silently
    depending on an un-tested arm."""
    assert ("exile_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Altaïr Ibn-La'Ahad",
        "Livio, Oathsworn Sentinel",
    ],
)
def test_exile_matters_counter_gated_persistent_pile_arm(name):
    """ADR-0038 W3 batch 6 — the "exiled with a [named] counter"
    persistent-pile arm: a per-card-unique counter kind (Altaïr's "memory"
    counter, Livio's "aegis" counter) tracks a maker-populated exile pile the
    SAME way Gorex's ``ExiledBySource`` does, but structured as a plain
    ``Typed`` filter carrying BOTH an ``InZone{zone: Exile}`` property AND a
    ``Counters`` property (of ANY non-"time" kind), reached anywhere in the
    unit's subtree — not just a ``ChooseFromZone``. Altaïr's is on a
    ``CopyTokenOf.source_filter``; Livio's is on the SAME ``ChangeZoneAll``
    filter that cheat_into_play excludes it from (Livio is genuinely
    exile_matters even though it's NOT cheat_into_play — a temporary-exile
    removal-and-release still cares about its own tracked exile pile). CR
    406.1."""
    assert ("exile_matters", "you", "") in _idents(name)


def test_exile_matters_excludes_suspend_time_counter_reuse():
    """ADR-0038 W3 batch 6 shed: phase structures Suspend's "target permanent
    or suspended card [with a time counter]" the SAME way the counter-gated
    persistent-pile arm reads (a suspended card IS structurally in exile with
    a time counter, CR 702.62a) even though Timecrafting's oracle text never
    says "exile" at all. Corpus census (2026-07): every commander-legal "time
    counter on a suspended card" hit shares this shape (Shivan Sand-Mage,
    Fury Charm, Timebender, Clockspinning, Rose Tyler, Amy Pond) — the
    suspend-mechanic's own generic counter manipulation, not an
    exile-as-resource build-around. Gated on ``counter_type == 'time'``: the
    ONLY counter kind reused this way in the corpus."""
    assert "exile_matters" not in _keys("Timecrafting")


def test_exile_matters_remove_counter_from_exiled_card_arm():
    """ADR-0038 W3 batch 6: Mari, the Killing Quill's granted ability
    ("remove a hit counter from a card that player owns in exile") is a
    ``RemoveCounter`` whose OWN ``target`` filter carries
    ``InZone{zone: Exile}`` — the counter kind lives on the effect's
    ``counter_type`` field here, not a filter ``Counters`` property, so the
    persistent-pile arm (which reads filter properties) misses it; a direct
    field read closes the gap. Same "time" counter Suspend-reuse exclusion
    applies (verified against the same corpus). CR 406.1."""
    assert ("exile_matters", "you", "") in _idents("Mari, the Killing Quill")


def test_exile_matters_static_exiled_by_source_arm():
    """ADR-0038 W3 batch 6: Lumbering Battlement's "gets +2/+2 for each card
    exiled WITH IT" counts its OWN maker-populated pile via a static
    ``ObjectCount`` filter carrying ``ExiledBySource`` (not ``InZone{Exile}``)
    — the batch 5 static P/T-scaler arm only read the InZone shape; widened
    to also accept the ExiledBySource shape (the SAME predicate Gorex's
    triggered arm already reads). CR 406.1 / 613.4c."""
    assert (
        "exile_matters",
        "you",
        "",
    ) in _idents("Lumbering Battlement")


@pytest.mark.parametrize(
    "name",
    [
        "Ruin Processor",
        "Oblivion Sower",
        "Rootcoil Creeper",
    ],
)
def test_exile_matters_general_target_arm_change_zone(name):
    """ADR-0038 W5 tails: ANY effect (any origin) whose OWN
    ``target``/``filter`` field is a fresh ``Typed`` selection filter
    carrying ``InZone{zone: Exile}`` references a card STANDING in exile as
    a resource, regardless of what the effect then DOES with it — Ruin
    Processor's trigger sends it to a graveyard ("put a card an opponent
    owns from exile into that player's graveyard"), Oblivion Sower's trigger
    puts it onto the battlefield instead, Rootcoil Creeper's activated
    ability returns it to hand. All three are a ``ChangeZone`` whose
    ``target`` is the Typed+InZone shape — distinct from the
    ``ParentTarget``/``TrackedSet`` blink tell (Flickerwisp / Ephemerate /
    Banisher Priest track ONE already-known object, never re-select via a
    fresh filter). CR 406.1."""
    assert ("exile_matters", "you", "") in _idents(name)


def test_exile_matters_general_target_arm_cast_from_zone():
    """ADR-0038 W5 tails: Tasha, the Witch Queen's -3 ("cast a spell from
    among cards in exile with page counters on them") is a ``CastFromZone``
    whose ``target`` is the SAME Typed+InZone{Exile} shape the ChangeZone
    arm reads — a persistent-pile cast engine, not a one-shot Suspend/
    Foretell self-cast (those target ``SelfRef``/``ParentTarget``, never a
    fresh selection filter). CR 406.1."""
    assert ("exile_matters", "you", "") in _idents("Tasha, the Witch Queen")


def test_exile_matters_general_target_arm_modal_bounce_and_bury():
    """ADR-0038 W5 tails: Sentinel of Lost Lore's ETB is modal — mode 1
    (``Bounce``) returns a card you own in exile with an Adventure to hand;
    mode 2 (``PutAtLibraryPosition``) buries an opponent's exiled Adventure
    card. Both targets are the same Typed+InZone{Exile} shape; the third
    mode (graveyard exile) is unrelated. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents("Sentinel of Lost Lore")


def test_exile_matters_general_target_arm_aggregate():
    """ADR-0038 W5 tails: Ulamog, the Defiler's ETB replacement ("enters with
    a number of +1/+1 counters on it equal to the greatest mana value among
    cards in exile") is a ``PutCounter`` whose count is an ``Aggregate`` qty
    with its OWN ``filter`` carrying InZone{Exile} — a third count-operand
    shape (alongside ZoneCardCount / ObjectCount) the general target/filter
    scan reaches for free since ``Aggregate.filter`` is also a
    ``filter``-named field (Ashiok, Wicked Manipulator's -7 shares the exact
    same shape — CR 406.1 / 613.4c)."""
    assert ("exile_matters", "you", "") in _idents("Ulamog, the Defiler")


def test_exile_matters_general_target_arm_excludes_suspend_reuse_widened():
    """ADR-0038 W5 tails regression guard: Rose Tyler's "put a time counter
    on it for each suspended card you own" sums an ``ObjectCount`` whose
    filter carries BOTH ``InZone{Exile}`` and ``Counters: time`` — the
    identical Suspend-mechanic-reuse shape
    ``test_exile_matters_excludes_suspend_time_counter_reuse`` already
    excludes via the counter-gated-pile arm. The broader general
    target/filter scan and the widened ZoneCardCount/ObjectCount deep scan
    (below) MUST apply the SAME "time" gate or they silently re-admit her
    (caught + fixed this session: an early draft of the widened deep scan
    omitted the gate). CR 406.1 / 702.62a."""
    assert "exile_matters" not in _keys("Rose Tyler")


@pytest.mark.parametrize(
    "name",
    [
        "Crypt Incursion",
        "March of Otherworldly Light",
    ],
)
def test_exile_matters_filtered_tracked_set_size_exiled(name):
    """ADR-0038 W5 tails: a ``FilteredTrackedSetSize`` qty whose
    ``caused_by`` field is ``'Exiled'`` counts the cards an EARLIER effect
    in the SAME resolution chain just exiled — Crypt Incursion's "gain 3
    life for each card exiled this way", March of Otherworldly Light's
    "costs {2} less to cast for each card exiled this way". ``caused_by``
    also carries Destroyed/Sacrificed/Discarded/Milled for OTHER
    zone-change payoffs (2026-07 census); gated narrowly to ``'Exiled'``.
    supplement.py's deleted regex intentionally kept this whole population
    as real exile_matters members. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents(name)


def test_exile_matters_exiled_from_hand_this_resolution():
    """ADR-0038 W5 tails: the "hate a card name" cycle (The Stone Brain /
    Unmoored Ego / Lost Legacy / Necromentia / Deadly Cover-Up / The End /
    Test of Talents) pays its victim off with a bare
    ``ExiledFromHandThisResolution`` qty node — no fields at all. 2026-07
    corpus census: exactly these 7 commander-legal cards, zero false
    positives. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents("The Stone Brain")


def test_exile_matters_search_outside_game_face_up_exile():
    """ADR-0038 W5 tails: Karn, the Great Creator's -2 ("reveal an artifact
    card you own from outside the game or choose a face-up artifact card
    you own in exile") is a ``SearchOutsideGame`` whose ``source_pool`` is
    ``SideboardAndFaceUpExile`` — the ONLY ``source_pool`` variant the
    substrate carries, so tagging it is zero-guess. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents("Karn, the Great Creator")


def test_exile_matters_static_affected_cast_from_exile_keyword_grant():
    """ADR-0038 W5 tails: Wild-Magic Sorcerer's "The first spell you cast
    from exile each turn has cascade" is a STATIC ability whose OWN
    ``affected`` scope is a Typed filter carrying InZone{Exile} — a keyword
    grant restricted to spells cast FROM the exile zone (a build-around
    that wants an ongoing exile pile to cast from). 2026-07 census: exactly
    4 commander-legal cards (also Party Thrasher / Hoarding Broodlord /
    Rassilon, the War President). CR 406.1 / 613.4c."""
    assert ("exile_matters", "you", "") in _idents("Wild-Magic Sorcerer")


@pytest.mark.parametrize(
    "name",
    [
        "Howling Galefang",
        "Dreadlight Monstrosity",
    ],
)
def test_exile_matters_gap_marker_text_fallback(name):
    """ADR-0038 W5 tails: gap-marker text fallback, narrowly scoped (the
    SAME precedent ``plus_one_matters`` established for Pipsqueak / Skarrgan
    Hellkite, CR 602.5). Howling Galefang's "has haste as long as you own a
    card in exile that has an Adventure" decorates as
    ``Unrecognized(text=…)`` (a raw parse residue); Dreadlight Monstrosity's
    "Activate only if you own a card in exile" decorates as an EMPTY
    ``RequiresCondition`` (``data.inner is None``) with no text of its own,
    so the fallback reads the SAME unit's own ``description`` field
    instead. A 2026-07 corpus census of "owns? a card in exile" across
    every commander-legal card found exactly these two (plus Warden of the
    Beyond), zero false positives. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Serpentine Curve",
        "Niko Defies Destiny",
    ],
)
def test_exile_matters_widened_deep_scan_wrapped_count(name):
    """ADR-0038 W5 tails: a Token/PutCounter-style effect's OWN scaling
    count can nest a ZoneCardCount/ObjectCount UNDER a wrapper field
    (Serpentine Curve's "put X +1/+1 counters on it, where X is … cards you
    own in exile" nests a ``ZoneCardCount`` under ``enter_with_counters``,
    which the amount/count/value-scoped count-operand arm never reaches) or
    inside a scaling operator (Niko Defies Destiny's "gain 2 life for each
    foretold card you own in exile" nests an ``ObjectCount`` under
    ``Multiply`` instead of sitting bare on ``amount``). A full per-effect
    subtree scan (mirroring the STATIC arm's own deep scan) reaches both
    shapes regardless of nesting depth or field name. CR 406.1."""
    assert ("exile_matters", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Whirler Virtuoso", "Aetherworks Marvel"])
def test_energy_matters_pay_energy_sink(name):
    """A ``PayEnergy`` cost leaf buying a non-mana effect is the energy SINK
    payoff (CR 107.14)."""
    assert ("energy_matters", "you", "") in _idents(name)


def test_energy_matters_excludes_fixing_land_gainer():
    """Aether Hub's pay-{E} ability buys only MANA (the painland-pattern
    non-ramp gate) — it stays energy_makers, not a sink engine."""
    assert "energy_matters" not in _keys("Aether Hub")
    assert ("energy_makers", "you", "") in _idents("Aether Hub")


def test_counter_move_dedicated_key():
    """Nesting Grounds' ``MoveCounters`` fires the dedicated counter_move
    key (CR 122.1); a placer (Renata) never does."""
    assert ("counter_move", "you", "") in _idents("Nesting Grounds")
    assert "counter_move" not in _keys("Renata, Called to the Hunt")


def test_explore_matters_first_class_mode():
    """Wildgrowth Walker's ``Explored`` trigger mode fires explore_matters
    (CR 701.44) — a structural fidelity gain over the live raw
    discriminator; the DOER (Merfolk Branchwalker) stays explore_makers
    only."""
    assert ("explore_matters", "you", "") in _idents("Wildgrowth Walker")
    assert "explore_matters" not in _keys("Merfolk Branchwalker")
    assert "explore_makers" not in _keys("Wildgrowth Walker")


def test_dice_matters_roll_trigger():
    """Brazen Dwarf's ``RolledDie`` trigger fires dice_matters (CR 706.1);
    the roller (Adorable Kitten — RollDie effect) stays dice_makers."""
    assert ("dice_matters", "you", "") in _idents("Brazen Dwarf")
    assert "dice_matters" not in _keys("Adorable Kitten")


def test_extra_upkeep_and_end_step():
    """AdditionalPhase kind routes the non-combat extra phases (CR 500.8):
    Upkeep (Paradox Haze — scope "you" though the recipient is the
    enchanted TriggeringPlayer, mirroring the live build-around scope) and
    End (Y'shtola Rhul)."""
    assert ("extra_upkeep", "you", "") in _idents("Paradox Haze")
    assert ("extra_end_step", "you", "") in _idents("Y'shtola Rhul")


def test_extra_phase_lanes_disjoint():
    """A combat AdditionalPhase (Aurelia) is extra_combats only; the upkeep/
    end keys never fire it, and Paradox Haze never fires extra_combats."""
    keys = _keys("Aurelia, the Warleader")
    assert "extra_upkeep" not in keys
    assert "extra_end_step" not in keys
    assert "extra_combats" not in _keys("Paradox Haze")


def test_facedown_matters_turn_face_up_effect():
    """Break Open's ``TurnFaceUp`` effect references existing face-down
    permanents (CR 708.1) → facedown_matters; the Manifest/Cloak DOERS
    (Cloudform) stay facedown_makers."""
    assert ("facedown_matters", "you", "") in _idents("Break Open")
    assert "facedown_matters" not in _keys("Cloudform")


# ── ADR-0038 W3 batch 6 (facedown_matters promotion) ───────────────────────
# The batch-5 zones agent proved the legacy population is scope-mismatched:
# a plain morph/manifest/cloak MAKER with no genuine payoff fires the legacy
# ``_matters`` lane purely because its OLD-IR per-face keyword tuple drops
# the keyword for a non-mana morph cost (Gathan Raiders "Morph—Discard a
# card" keywords=() vs Krosan Colossus "Morph {4}{U}" keywords=('Morph',)) —
# an artifact of that projection quirk, not a principled cares-about
# boundary (CR 702.37a: Morph is the cast-as-2/2 ability; the maker never
# references an EXISTING face-down object). live_only re-measured at HEAD:
# every one of the 61 legacy-only cards is either this maker-idiom shed
# (33, negative-pinned below) or a genuine structural gap now closed (28
# recovered) — live_only == exactly the shed set, the promotion gate.
@pytest.mark.parametrize(
    "name",
    [
        "Ixidron",  # mass turn-face-down + face-down-count read (CR 613)
        "Nosy Goblin",  # Destroy target w/ FaceDown property (CR 708.2)
        "Kadena, Slinking Sorcerer",  # ETB draw on a face-down creature
        "Karlov Watchdog",  # static mode CantBeTurnedFaceUp (CR 708.3)
        "Paranormal Analyst",  # trigger_event manifestdread (CR 701.62)
        "Smoke Teller",  # Unimplemented{name=look} "target face-down..."
        "Exiled Doomsayer",  # morph-cost tax (CR 702.37a)
    ],
)
def test_facedown_matters_recovered_structural(name):
    """Genuine face-down PAYOFF/reference cards the batch-6 structural arms
    (FaceDown-typed marker deep scan, ``manifestdread``/``turnfaceup``
    trigger events, ``EnchantedIsFaceDown``/``CantBeTurnedFaceUp`` typed
    modes, and the ``look``/``turn``-named Unimplemented residue reads)
    recover — none of these fire via the last-resort text fallback."""
    assert ("facedown_matters", "you", "") in _idents(name)


def test_facedown_matters_enchanted_is_facedown_condition():
    """Unable to Scream's static carries a typed ``EnchantedIsFaceDown``
    condition ("as long as enchanted creature is face down, it can't be
    turned face up") — the lock references an EXTERNAL face-down state,
    not its own maker action (CR 708.2)."""
    assert ("facedown_matters", "you", "") in _idents("Unable to Scream")


@pytest.mark.parametrize(
    "name",
    [
        "Gathan Raiders",  # plain Morph maker, non-mana cost (CR 702.37a)
        "Whisperwood Elemental",  # plain Manifest maker (CR 701.62 sibling)
        "Gift of Doom",  # self "as ~ is turned face up" morph rider only
    ],
)
def test_facedown_matters_excludes_plain_maker(name):
    """A plain morph/manifest MAKER with no reference to an EXTERNAL
    face-down object never fires facedown_matters — it belongs to
    facedown_makers only (CR 702.37a / 701.62). The legacy population's
    firing on these was the ``_recover_facedown`` regex catching the
    maker's own reminder text, not a genuine payoff; adjudicated shed."""
    assert "facedown_matters" not in _keys(name)


def test_facedown_matters_excludes_name_collision():
    """Cloak and Dagger, Entwined has NO face-down reference in its oracle
    text at all (deathtouch/lifelink + a hand-reveal ETB) — the legacy
    population's firing here was purely a regex name-collision on its own
    "Cloak" name fragment, not a mechanic reference. Adjudicated shed."""
    assert "facedown_matters" not in _keys("Cloak and Dagger, Entwined")


@pytest.mark.parametrize(
    "name",
    [
        "Primal Whisperer",  # "+2/+2 for each face-down creature" count
        "Cyber Conversion",  # "Turn target creature face down" (CR 708.1)
        "Oblivious Bookworm",  # broad "entered ... face down / turned ...
        # face up this turn" condition, not self-referential
    ],
)
def test_facedown_matters_beyond_legacy_gain(name):
    """Genuine facedown_matters cards the legacy regex never covered (no
    "turn ... face up" phrasing in its allowlist for a "turn X face down"
    removal effect, or a bare count/condition read) — beyond-legacy gains,
    CR-grounded (CR 613 count, 708.1 turn-face-down, 708.2/708.3
    condition)."""
    assert ("facedown_matters", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("name", "extra_flash"),
    [
        ("Leyline of Anticipation", True),  # CastWithKeyword{Flash} static
        ("Snapcaster Mage", False),  # targeted AddKeyword{Flashback} grant
    ],
)
def test_spell_keyword_grant_arms(name, extra_flash):
    """spell_keyword_grant fires the CastWithKeyword static (Leyline — also
    flash_grant + flash_makers) and the targeted spell-class AddKeyword
    grant (Snapcaster's flashback recursion grant). CR 702.8 / 702.34 /
    601.3e."""
    idents = _idents(name)
    assert ("spell_keyword_grant", "you", "") in idents
    assert (("flash_grant", "you", "") in idents) is extra_flash
    assert (("flash_makers", "you", "") in idents) is extra_flash


def test_spell_keyword_grant_excludes_bearer_and_nongrant():
    """A PRINTED-keyword bearer (Faithless Looting's own Flashback) carries
    no grant node; Anafenza grants nothing — neither fires."""
    assert "spell_keyword_grant" not in _keys("Faithless Looting")
    assert "spell_keyword_grant" not in _keys("Anafenza, the Foremost")


@pytest.mark.parametrize(
    "name", ["Crashing Tide", "Colossal Rattlewurm", "Graveyard Shift"]
)
def test_spell_keyword_grant_excludes_conditional_self_flash(name):
    """A conditional PRINTED self-flash ("~ has flash as long as …") parses
    as ``AddKeyword{Flash}`` with ``affected=SelfRef`` — the card grants
    ITSELF castability (CR 702.8a), not your spells: not a flash engine.
    The SelfRef veto keeps all three lanes out (rules-lawyer-adjudicated,
    batch 9)."""
    keys = _keys(name)
    assert "spell_keyword_grant" not in keys
    assert "flash_grant" not in keys
    assert "flash_makers" not in keys


@pytest.mark.parametrize("name", ["Duress", "Addle", "Telepathy"])
def test_hand_disruption_fires(name):
    """hand_disruption fires the opponent-directed RevealHand effect
    (Duress — Typed Opponent; Addle — targeted Player) and the RevealHand
    static reaching opponents' hands (Telepathy). CR 402.3."""
    assert ("hand_disruption", "opponents", "") in _idents(name)


@pytest.mark.parametrize("name", ["Goblin Secret Agent", "Land Grant", "Manabond"])
def test_hand_disruption_excludes_self_reveal(name):
    """A SELF-reveal never fires — the reveal must reach ANOTHER player's
    hand: Goblin Secret Agent's upkeep reveal (``Controller``), Land
    Grant's alt-cost reveal, and Manabond's "reveal your hand" (phase's
    bare ``Any`` CARDS target carries no player evidence — never guess)."""
    assert "hand_disruption" not in _keys(name)


def test_hand_disruption_defending_player_recipient():
    """ADR-0037/0038 W3: ``DefendingPlayer`` (Port Inspector: "look at
    defending player's hand") is opponent-directed BY RULE (CR 506.2 — the
    b11 tap_down precedent), joining the always-fire recipient set."""
    assert ("hand_disruption", "opponents", "") in _idents("Port Inspector")


def test_hand_disruption_chosen_player_backreference():
    """ADR-0037/0038 W3: a ``ChosenPlayer`` recipient backreference
    resolves to whichever player a SIBLING ``Choose{choice_type:
    Opponent}`` in the same unit selected (Anointed Peacekeeper: "look at
    an opponent's hand, then choose any card name" — a CR 614/616
    replacement effect chaining Choose -> RevealHand)."""
    assert ("hand_disruption", "opponents", "") in _idents("Anointed Peacekeeper")


def test_hand_disruption_wrapper_player_scope_fallback():
    """ADR-0037/0038 W3: an ambiguous bare ``Any`` RevealHand recipient
    (indistinguishable from a self-reveal by ITS OWN target field) is
    opponent-directed when the OWNING wrapper's ``player_scope`` is
    symmetric-or-wider (Kamahl's Summons: "each player reveals ... from
    their hand" — player_scope All) or explicitly opponent-scoped (Valki,
    God of Lies: "each opponent reveals their hand" — player_scope
    Opponent, carrying the "for each opponent" edict the RevealHand's OWN
    target never does)."""
    assert ("hand_disruption", "opponents", "") in _idents("Kamahl's Summons")
    assert ("hand_disruption", "opponents", "") in _idents("Valki, God of Lies")


def test_hand_disruption_nested_grant_descent():
    """ADR-0037/0038 W3: a ``RevealHand`` buried inside a GRANTED activated
    ability (Dementia Sliver's tribal static: "All Slivers have '{T}:
    Choose a card name. Target opponent reveals a card at random from
    their hand...'") is never its own top-level unit — reached via
    :func:`iter_typed_nodes`'s generic deep walk over the static's
    ``GrantAbility.definition`` field."""
    assert ("hand_disruption", "opponents", "") in _idents("Dementia Sliver")


def test_hand_disruption_hand_revealed_grammar_recovery():
    """ADR-0037/0038 W3: "have defending player play with their hand
    revealed" (Stromgald Spy) is a genuine Unimplemented residue the
    shared clause grammar's third-person-only "hand revealed" static
    idiom recovers to the native RevealHand static mode's own
    ``reveal_hand`` concept — the lane trusts a recovered node
    unconditionally (``ConceptNode.recovered_by``) since the recovered
    ``.node`` carries no target field of its own to re-check."""
    assert ("hand_disruption", "opponents", "") in _idents("Stromgald Spy")


def test_hand_disruption_imperative_reveal_hand_grammar_recovery():
    """ADR-0038 deferral sweep: Alhammarret's "each opponent reveals their
    hand. You choose the name of a nonland card ..." two-sentence blob is
    a genuine Unimplemented residue with no other structure; the
    imperative third-person "reveal(s) {their} hand" grammar arm (token
    ``reveal_hand``, mirroring the STATIC "hand revealed" idiom's
    third-person-only gate) recovers it (CR 402.3)."""
    assert ("hand_disruption", "opponents", "") in _idents("Alhammarret, High Arbiter")


def test_hand_disruption_target_creature_controller_shape():
    """ADR-0038 deferral sweep: Friendly Fire's "target creature's
    controller reveals a card at random from their hand" binds the reveal
    to the targeted creature's controller only in PROSE — phase structures
    a bare ``RevealHand{Any}`` with no player linkage; the corpus-unique
    TargetOnly{Creature}-first-effect + RevealHand{Any} shape is the
    structural read."""
    assert ("hand_disruption", "opponents", "") in _idents("Friendly Fire")


@pytest.mark.parametrize("name", ["Thoughtcutter Agent", "Psychotic Episode"])
def test_hand_disruption_detriment_directed_text_confirmation(name):
    """ADR-0038 deferral sweep (detriment-directed targeting, Dan
    2026-07-10): phase structures only the OTHER half of the compound
    (Thoughtcutter Agent's ``LoseLife``; Psychotic Episode's
    ``RevealTop``) — the hand-reveal half leaves no node at all. A
    detriment-directed recipient (:func:`detriment_directed_scope` ==
    "opponents"; CR 603.3d's targeting freedom acknowledged, not
    contradicted) COMBINED with the ability's own text confirming the
    specific missing "reveals their hand" fact fires the lane."""
    assert ("hand_disruption", "opponents", "") in _idents(name)


def test_hand_disruption_each_player_symmetric_shed():
    """ADR-0038 deferral sweep: Wild Evocation ("at the beginning of EACH
    PLAYER'S upkeep, that player reveals a card at random ...") is the
    each-player SYMMETRIC class — an adjudicated legacy over-fire SHED.
    "Each player" is never folded into "opponents"; it is the
    detriment-directed principle's own stated boundary (its RevealHand
    target is ``ScopedPlayer``, a per-iteration trigger variable)."""
    assert "hand_disruption" not in _keys("Wild Evocation")


def test_hand_disruption_controller_backreference_recall_gain():
    """ADR-0038 deferral sweep: Lay Bare's "Counter target spell. Look at
    its controller's hand." back-references the countered spell's
    controller — legacy's regex misses the backreference, an adjudicated
    beyond-legacy RECALL GAIN over the same look-at-hand class legacy
    already fires (Peek, Glasses of Urza)."""
    assert ("hand_disruption", "opponents", "") in _idents("Lay Bare")


# ── batch 9: the three adjudicated batch-8 follow-up fixes ────────────────────


def test_cheat_into_play_subtype_only_type_evidence():
    """Fix (a): Academy Researchers' put carries a SUBTYPE-only filter
    (``{Subtype: Aura}``, cores ∅) — a non-land subtype IS type evidence
    (phase's filter is correct and complete), so the cheat fires."""
    assert ("cheat_into_play", "you", "") in _idents("Academy Researchers")


@pytest.mark.parametrize("name", ["Nature's Lore", "Path to Exile"])
def test_cheat_into_play_land_puts_stay_out(name):
    """The land carve-out survives fix (a): Nature's Lore (core Land +
    Subtype Forest) and Path to Exile (basic-Land compensation fetch) are
    excluded by the cores gate BEFORE the subtype path can run — pinned so
    the subtype path can never resurrect them."""
    assert "cheat_into_play" not in _keys(name)


def test_cheat_into_play_dig_to_battlefield_arm():
    """Fix (b): Aethermage's Touch's ``Dig`` lands a Creature on the
    battlefield (destination gate + non-Land cores) — a put, not a cast (CR
    401.1)."""
    assert ("cheat_into_play", "you", "") in _idents("Aethermage's Touch")


def test_cheat_into_play_dig_arm_negatives():
    """The dig arm's gates: Elvish Rejuvenator's land dig stays
    extra_land_drop; Aetherworks Marvel's dig-and-CAST has destination None
    (a cast, not a put)."""
    assert "cheat_into_play" not in _keys("Elvish Rejuvenator")
    assert ("extra_land_drop", "you", "") in _idents("Elvish Rejuvenator")
    assert "cheat_into_play" not in _keys("Aetherworks Marvel")


def test_cheat_into_play_arcum_directed_search_narrowing():
    """Fix (c): Arcum Dagsson's search resolves through the sacrificed
    ARTIFACT's controller (``ParentTargetController`` with NO player-target
    marker in the unit — CR 115.1: you choose the target, so the directed
    player is routinely YOU) — the narrowed veto no longer excludes it."""
    assert ("cheat_into_play", "you", "") in _idents("Arcum Dagsson")


def test_cheat_into_play_settle_stays_out():
    """Settle the Wreckage stays out on BOTH gates: its wipe filter carries
    ``controller: TargetPlayer`` (the player-target marker keeps the
    ParentTargetController veto), AND its search filter is ``Any`` (no type
    evidence — never guess)."""
    assert "cheat_into_play" not in _keys("Settle the Wreckage")


@pytest.mark.parametrize("name", ["Polymorph", "Jalira, Master Polymorphist"])
def test_cheat_into_play_reveal_until_arm(name):
    """ADR-0038 W3 batch 5 fix (d): a ``RevealUntil`` whose
    ``kept_destination`` is Battlefield IS the reveal-until-a-match-then-put
    engine (CR 701.15) — Polymorph destroys a creature then reveals until a
    creature card is found and puts it onto the battlefield; Jalira's
    activated ability does the same with a nonlegendary-creature filter."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_change_zone_all_arm():
    """ADR-0038 W3 batch 5 fix (c): Warp World's symmetric "each player
    puts all artifact, creature, and land cards revealed this way onto the
    battlefield" rides ``ChangeZoneAll`` with an UNTRACKED (None) origin and
    its real type filter one level deeper on a ``TrackedSetFiltered``
    target — :func:`_change_zone_all_cores` digs the nested filter the
    direct ``effect_filter`` read misses. CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents("Warp World")


@pytest.mark.parametrize("name", ["Call of the Wild", "Clone Shell"])
def test_cheat_into_play_revealed_has_card_type_arm(name):
    """ADR-0038 W3 batch 5 fix (e): the type check rides a typed
    ``RevealedHasCardType`` CONDITION on the sub-ability, not a filter on the
    ``ChangeZone`` itself — :func:`iter_condition_sites` reaches it.
    Call of the Wild: "Reveal the top card. If it's a creature card, put it
    onto the battlefield." (``ParentTarget``). Clone Shell: the imprint
    cycle's "turn the exiled card face up... put it onto the battlefield"
    (``TriggeringSource``, gated to a unit with a ``turn_face_up`` producer —
    landmine #7i). CR 400.7 / 701.36c."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Angel's Herald", "Llanowar Sentinel"])
def test_cheat_into_play_named_tutor_arm(name):
    """ADR-0038 W3 batch 5 fix (f): a ``SearchLibrary`` naming a SPECIFIC
    card carries NO type_filters at all (CR 201.4 — a name isn't a type), so
    the sibling-core / sibling-subtype fallbacks both come up empty. Corpus
    census (2026-07): every commander-legal single-tutor, named,
    coreless unit paired with a ``ChangeZone{Battlefield}`` names a
    creature, never a land — a Named property alone is sufficient type
    evidence for this narrow (single-tutor) shape."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Living Death", "Faith's Reward", "Verdant Crescendo"],
)
def test_cheat_into_play_excludes_reanimation_and_ambiguous_tutor_pairing(name):
    """ADR-0038 W3 batch 5 sheds — three distinct false-positive risks the
    ChangeZoneAll/named-tutor widenings introduced, each closed by a
    targeted structural gate rather than reverting the widening:

    * Living Death — "Each player exiles all creature cards from their
      graveyard... puts all cards they exiled this way onto the
      battlefield." The classic EDH "reanimator" card: exile is a rules
      workaround for the symmetric wording, not a cheat build-around. An
      EARLIER Graveyard-origin zone change in the same unit excludes it
      (checklist #2; CR 400.7 / 700.4).
    * Faith's Reward — "Return to the battlefield all permanent cards in
      your graveyard that were put there from the battlefield this turn."
      Origin is left untracked (None) but the target filter carries an
      ``InZone: Graveyard`` property directly — excluded on that.
    * Verdant Crescendo — "Search your library for a basic land card and
      put it onto the battlefield tapped. Search your library and graveyard
      for a card named Nissa... reveal it, put it into your hand" — TWO
      tutor calls in one unit; phase mis-tags the SECOND search's
      ChangeZone destination as Battlefield even though the card text puts
      it into hand. :func:`_sibling_named_tutor_no_core` requires EXACTLY
      ONE tutor per unit — an ambiguous multi-tutor pairing never fires.
    """
    assert "cheat_into_play" not in _keys(name)


@pytest.mark.parametrize(
    "name", ["Arbiter of the Ideal", "Hew the Entwood", "Pyxis of Pandemonium"]
)
def test_cheat_into_play_batch5_cw_only_baseline_gains(name):
    """ADR-0038 W3 batch 6 — three cw_only cards flagged "pending closer
    review" at the end of batch 5, investigated this session and confirmed
    LEGIT gains (the existing arms already fire correctly; the legacy regex
    simply never recognized them, so they were never pinned):

    * Arbiter of the Ideal — the batch 5 fix (e) RevealedHasCardType arm
      (Inspired trigger: reveal top, "if it's an artifact, creature, or land
      card, you may put it onto the battlefield" — CR 400.7).
    * Hew the Entwood — the batch 5 fix (c) ChangeZoneAll arm reading the
      nonland-card type filter (``Typed(['Card', Non(Land)])``).
    * Pyxis of Pandemonium — the SAME ChangeZoneAll arm on the symmetric
      "each player turns face up all cards they own exiled with this
      artifact, then puts all permanent cards among them onto the
      battlefield" idiom.
    """
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Boneyard Parley", "Rejoin the Fight"])
def test_cheat_into_play_excludes_graveyard_intermediate_pile(name):
    """ADR-0038 W3 batch 6 sheds — two more graveyard-sourced reanimation
    shapes the ChangeZoneAll/origin=None arm needed to exclude, both
    "pending closer review" at the end of batch 5:

    * Boneyard Parley — "Exile up to five target creature cards from
      graveyards... Put all cards from the pile of your choice onto the
      battlefield under your control." An EARLIER ``ChangeZone`` leaves
      ``origin=None`` (untracked) but its OWN target filter carries the
      ``InZone: Graveyard`` evidence instead of a tracked origin — the
      sibling scan now reads that filter too (checklist #2; CR 400.1).
    * Rejoin the Fight — "Mill three cards... each opponent chooses a
      creature card in your graveyard... Return each card chosen this way to
      the battlefield under your control." Reanimates via a direct
      ``ChooseFromZone{zone: Graveyard}`` selector, no ``ChangeZone`` at all
      — the sibling scan also excludes on that shape.
    """
    assert "cheat_into_play" not in _keys(name)


def test_cheat_into_play_excludes_counter_gated_removal_release():
    """ADR-0038 W3 batch 6 shed: Livio, Oathsworn Sentinel's "Return all
    exiled cards with aegis counters on them to the battlefield under their
    owners' control" reads the SAME ChangeZoneAll shape as Warp World, but
    its filter carries a ``Counters`` property (an "exiled WITH a counter"
    persistent-pile marker) sourced from a TARGETED battlefield creature
    (its own earlier activated ability exiles "another target creature") and
    explicitly returns it to its OWNER, not the caster — a temporary-exile
    REMOVAL effect (Banisher-Priest class), not a cheat build-around (CR
    610.3c — a returned object defaults to its owner's control absent an
    explicit transfer). A 2026-07 corpus census found Livio is the SOLE
    Counters-bearing filter in the ChangeZoneAll{Battlefield, origin: None}
    population — Warp World / Over the Top / Manabond / Tezzeret, Master of
    the Bridge / Pyxis of Pandemonium all carry EMPTY filter properties, so
    the narrow Counters-presence gate leaves every other gain untouched."""
    assert "cheat_into_play" not in _keys("Livio, Oathsworn Sentinel")


def test_cheat_into_play_target_matches_filter_reveal_arm():
    """ADR-0038 W3 batch 6 widens the fix (e) reveal-then-put condition tag
    accepted: a ``TargetMatchesFilter`` on the SAME reveal-producing chain is
    the SAME "if it's a permanent/creature/land card" check phase sometimes
    structures as a target-match instead of ``RevealedHasCardType`` — Chaos
    Warp: "reveals the top card...If it's a permanent card, they put it onto
    the battlefield." Corpus census: every other commander-legal
    ``TargetMatchesFilter`` hit on a reveal-producing unit is this exact
    idiom (Aid from the Cowl, Skirk Drill Sergeant, N'Yami-Class Mother
    Ship, Bison Whistle). CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents("Chaos Warp")


def test_cheat_into_play_excludes_dies_recursion_chain_order():
    """ADR-0038 W3 batch 6 shed: the TargetMatchesFilter widening exposed a
    latent looseness in the existing TriggeringSource+turn_face_up carve-out
    (originally written for Clone Shell / Summoner's Egg's imprint cycle,
    which chains ``turn_face_up`` FIRST then the ``change_zone`` put). Yarus,
    Roar of the Old Gods's "Whenever a face-down creature you control DIES,
    return it to the battlefield... if it's a permanent card, then turn it
    face up" chains the ``change_zone`` FIRST — the put's ``TriggeringSource``
    there is the ORIGINAL dies-trigger subject (the just-died creature
    itself, CR 700.4), not a forwarded turn_face_up result — dies_recursion,
    not a cheat (checklist #2). ``unit.effects`` preserves the linear
    sub_ability chain order (verified 2026-07), so requiring the
    turn_face_up's index precede the change_zone's index is a precise,
    zero-guess fix that leaves Clone Shell / Summoner's Egg untouched."""
    assert "cheat_into_play" not in _keys("Yarus, Roar of the Old Gods")


@pytest.mark.parametrize("name", ["Finale of Devastation", "Boonweaver Giant"])
def test_cheat_into_play_tutor_untracked_origin_arm(name):
    """ADR-0038 W5 tails gain: a same-unit ``tutor`` (SearchLibrary) sibling
    is STILL search-and-put type evidence when the put's own ``ChangeZone``
    origin is untracked (None) rather than "Library" — phase leaves origin
    untracked for this idiom far more often than tracked (CR 400.7). Finale
    of Devastation's single-zone ``Library``/``Graveyard`` tutor names
    Creature directly; Boonweaver Giant's THREE-zone
    (Graveyard/Hand/Library) Aura tutor stays included too — CR 400.7 makes
    no distinction by source zone, and a 2026-07 corpus census found no
    Graveyard-touching tutor among the 46 same-unit hits searches Graveyard
    ALONE (every one also searches Hand and/or Library), so this widening
    never collides with the pure-graveyard reanimation lane."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Zara, Renegade Recruiter", "Treacherous Urge"])
def test_cheat_into_play_reveal_hand_untracked_origin_arm(name):
    """ADR-0038 W5 tails gain: the SAME untracked-origin widening also
    covers a same-unit ``reveal_hand`` sibling — Zara's "look at defending
    player's hand... put a creature card from it onto the battlefield under
    your control" and Treacherous Urge's "target opponent reveals their
    hand. You may put a creature card from it onto the battlefield under
    your control" (CR 400.7 — the hand is simply another zone the cheat
    reads from, same as the library). A 2026-07 census found only 5
    same-unit tutor/reveal_hand + ``ChangeZone{Battlefield, origin: None}``
    hits total off reveal_hand, all genuine (the 2 lacking type evidence —
    Retraced Image's name-match, Eladamri's ambiguous hand-or-library
    reveal — correctly stay excluded, never guessed)."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Armored Skyhunter", "Gilgamesh, Master-at-Arms"])
def test_cheat_into_play_dig_subtype_only_arm(name):
    """ADR-0038 W5 tails gain: the fix (a) subtype-only type-evidence
    fallback (already given to the ChangeZone arm) now ALSO covers the Dig
    arm — Armored Skyhunter's "look at the top six cards... put an Aura or
    Equipment card from among them onto the battlefield" and Gilgamesh's
    Equipment-only dig carry no CORE type at all (CR 205.3 — a subtype
    isn't a core type), so the core-only read came up empty and never
    guessed until this fallback."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_dig_subtype_land_subtype_stays_out():
    """ADR-0038 W5 tails shed guard: Nine-Fingers Keene's "you may put a
    Gate card from among them onto the battlefield" is EXCLUDED by the new
    Dig subtype fallback, not a gap in it — ``Gate`` is itself a LAND
    subtype (CR 205.3i — Gate is a land type), so this is genuine land ramp
    (extra_land_drop), not a cheat build-around; the existing
    ``_LAND_SUBTYPES`` gate correctly declines to fire."""
    assert "cheat_into_play" not in _keys("Nine-Fingers Keene")


@pytest.mark.parametrize("name", ["Indomitable Creativity", "Dubious Challenge"])
def test_cheat_into_play_exile_origin_tracked_set_arm(name):
    """ADR-0038 W5 tails gain: a ``ChangeZoneAll{Battlefield, origin: Exile}``
    whose own target is a BARE, untyped ``TrackedSet`` reads its type
    evidence off the SAME unit's earlier LIBRARY-sourced exile-populating
    producer (CR 400.7) — Indomitable Creativity's
    ``RevealUntil{kept_destination: Exile}`` filter directly, Dubious
    Challenge's ``ChangeZone{destination: Exile}`` chained after a ``Dig``
    (the Dig sibling proves the exile step is library-top, not a blink of
    an existing permanent)."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_exile_origin_arm_excludes_self_blink():
    """ADR-0038 W5 tails shed guard: Sword of Hearth and Home's "exile
    equipped creature, then return it to the battlefield under its owner's
    control" ALSO carries a ``ChangeZoneAll{Battlefield, origin: Exile,
    target: TrackedSet}`` shape, but its exile step targets an EXISTING
    battlefield permanent (a self-blink, origin untracked, no dig/
    reveal_until sibling proving a library-top pile) — CR 610.3c defaults
    the return to the OWNER's control, and this is retriggering the
    creature's own ETB value, not a cheat build-around. The producer gate
    (origin: Library OR a same-unit dig/reveal_until sibling) correctly
    excludes it."""
    assert "cheat_into_play" not in _keys("Sword of Hearth and Home")


def test_cheat_into_play_mixed_land_tutor_requires_enters_under():
    """ADR-0038 W5 tails shed guard: Archdruid's Charm's "Search your
    library for a creature or land card... Put it onto the battlefield
    tapped if it's a land card. Otherwise, put it into your hand" collapses
    onto ONE unconditional ``ChangeZone`` — phase drops the "otherwise
    hand" branch entirely, so the mixed Or(Creature, Land) tutor filter
    can't be trusted as "this exact set enters the battlefield" (never
    guess). Eternal Dominion's genuine unconditional multi-type
    Bribery-class cheat ("Search target opponent's library for an
    artifact, creature, enchantment, or land card. Put that card onto the
    battlefield under your control.") carries the stronger ``enters_under:
    You`` marker and stays included — the gate requires it only when the
    sibling tutor's core set MIXES Land with a non-Land type."""
    assert "cheat_into_play" not in _keys("Archdruid's Charm")
    assert ("cheat_into_play", "you", "") in _idents("Eternal Dominion")


def test_cheat_into_play_mutate_exile_from_top_until_arm():
    """ADR-0038 W5 tails gain: Illuna, Apex of Wishes's "Whenever this
    creature mutates, exile cards from the top of your library until you
    exile a nonland permanent card. Put that card onto the battlefield or
    into your hand" (CR 702.140a — mutate) rides phase's
    ``ExileFromTopUntil`` node (already mapped to the ``reveal_until``
    concept), whose type evidence lives on a ``NextMatches`` condition
    wrapping its ``until`` field — a different SITE than ``RevealUntil``'s
    ``kept_destination``/``filter`` pair the existing fix (d) arm reads."""
    assert ("cheat_into_play", "you", "") in _idents("Illuna, Apex of Wishes")


def test_cheat_into_play_exile_top_producer_arm():
    """ADR-0038 W5 tails gain: ``exile_top`` joins the fix (e) reveal-
    producer tuple — Primal Surge's "Exile the top card of your library. If
    it's a permanent card, you may put it onto the battlefield" (CR 400.7)
    carries its type check as a ``TargetMatchesFilter{Permanent}``
    condition on the SAME chain, exactly the shape fix (e) already reads
    for ``reveal_top``/``reveal_until``/``dig``/``turn_face_up`` producers —
    ``exile_top`` was simply missing from the producer gate."""
    assert ("cheat_into_play", "you", "") in _idents("Primal Surge")


@pytest.mark.parametrize("name", ["Tezzeret, Artifice Master", "Garruk, Unleashed"])
def test_cheat_into_play_nested_emblem_tutor_put_arm(name):
    """ADR-0038 W5 tails gain: the planeswalker "you get an emblem with 'At
    the beginning of your end step, search your library for a [type] card,
    put it onto the battlefield, then shuffle'" idiom (CR 400.7 / 121.4a —
    an emblem is not a card, so its granted ability is read straight off
    the ``CreateEmblem`` construct) is the SAME search-and-put pair the
    main tutor arm reads, just nested inside the emblem's own granted
    trigger definition (``CreateEmblem.triggers[].execute`` — the linear
    raw ``S_execute``/``S_sub_ability`` phase chain, not a flat
    ``unit.effects`` ConceptNode list), reached via the SAME
    ``iter_nested_trigger_defs`` shared descent every other granted-ability
    lane already uses."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name", ["From Father to Son", "The Five Doctors", "The Hunger Tide Rises"]
)
def test_cheat_into_play_w5_conditional_gain_baseline(name):
    """ADR-0038 W5 tails gain: three MORE cw_only cards surfaced by the
    tutor-widening investigation, confirmed LEGIT gains (existing arms fire
    correctly; legacy's regex simply never recognized the phrasing):

    * From Father to Son — "Search your library for a Vehicle card...put
      it into your hand. If this spell was cast from a graveyard, put that
      card onto the battlefield instead" — a ``ConditionInstead{
      CastFromZone: Graveyard}`` gates the SAME tutor+put pair (CR 400.7
      applies regardless of the triggering condition).
    * The Five Doctors — "...put them into your hand. If this spell was
      kicked, put those cards onto the battlefield instead" — an
      ``AdditionalCostPaid`` (kicker) condition gates it; its Doctor-subtype
      tutor filter carries no core type, needing the subtype fallback too.
    * The Hunger Tide Rises — Saga chapter IV: "Search your library and/or
      graveyard for a creature card...and put it onto the battlefield" —
      unconditional, single Creature core; legacy's regex apparently misses
      the Saga chapter-ability phrasing entirely.
    """
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_nested_grant_trigger_reveal_until_arm():
    """ADR-0038 W5b gain: Shifting Shadow's Aura grants (via ``GrantTrigger``,
    CR 113.6) "At the beginning of your upkeep, destroy this creature.
    Reveal cards from the top of your library until you reveal a creature
    card. Put that card onto the battlefield and attach Shifting Shadow to
    it..." — the SAME ``RevealUntil{kept_destination: Battlefield}`` shape
    fix (d) already reads at the top level (CR 400.7), just nested inside
    the granted trigger's own raw effect chain
    (:func:`iter_nested_trigger_defs`) rather than a flat
    ``unit.effects`` ConceptNode. A 2026-07 corpus census of every
    commander-legal nested-granted-trigger chain found this is the ONLY
    ``RevealUntil{Battlefield}`` hit besides Time Lord Regeneration
    (below); both carry a Creature core."""
    assert ("cheat_into_play", "you", "") in _idents("Shifting Shadow")


def test_cheat_into_play_nested_grant_trigger_reveal_until_time_lord():
    """ADR-0038 W5b gain: Time Lord Regeneration's "target Time Lord you
    control gains 'When this creature dies, reveal cards from the top of
    your library until you reveal a Time Lord creature card. Put that card
    onto the battlefield...'" — the granted delayed dies-trigger carries a
    nested ``RevealUntil{kept_destination: Battlefield}`` with a Time Lord
    subtype-and-Creature-core filter, read by the same nested descent as
    Shifting Shadow (CR 400.7)."""
    assert ("cheat_into_play", "you", "") in _idents("Time Lord Regeneration")


@pytest.mark.parametrize("name", ["Hunting Grounds", "Summoner's Grimoire"])
def test_cheat_into_play_nested_grant_trigger_hand_put_arm(name):
    """ADR-0038 W5b gain: a nested ``GrantTrigger``'s own ``ChangeZone
    {Battlefield, origin: Hand}`` is the SAME hand-put shape the top-level
    arm already admits (CR 400.7) — Hunting Grounds's Threshold grant
    ("Whenever an opponent casts a spell, you may put a creature card
    from your hand onto the battlefield") and Summoner's Grimoire's
    Equipment grant ("Whenever this creature attacks, you may put a
    creature card from your hand onto the battlefield..."), both read via
    the SAME nested descent as the RevealUntil arm above. Narrowly gated
    to origin ``'Hand'`` — a nested ``'Library'`` origin is already the
    SearchLibrary+ChangeZone tutor pair :func:`_nested_emblem_tutor_put`
    reads (Tezzeret, Artifice Master; Garruk, Unleashed), and a nested
    ``'Graveyard'`` origin is reanimation (checklist #2), never admitted
    here."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_nested_grant_trigger_excludes_reanimation():
    """ADR-0038 W5b shed guard: a 2026-07 census of every commander-legal
    nested-``GrantTrigger``/``CreateEmblem`` chain carrying a
    Battlefield-destined ``ChangeZone`` found a large "return this
    creature to the battlefield" self-reanimation class (Feign Death,
    Undying Malice, Rekindling Phoenix, Liliana, Waker of the Dead,
    Archpriest of Shadows, Guardian Scalelord, and more) — every one
    carries EITHER an explicit ``origin: 'Graveyard'`` (excluded by the
    Hand-only origin allow-list) OR an untyped, subject-less
    ``ChangeZone`` with no core/subtype filter at all (a back-reference to
    the just-exiled/died creature, not a type search — excluded by the
    never-guess type-evidence gate). Verified zero false hits: this arm
    never fires for Feign Death."""
    assert "cheat_into_play" not in _keys("Feign Death")


@pytest.mark.parametrize(
    "name",
    [
        "Call to the Kindred",
        "Lord of the Void",
        "Lonis, Cryptozoologist",
        "Anzrag's Rampage",
    ],
)
def test_cheat_into_play_untracked_origin_extends_to_dig_reveal_exile_top(name):
    """ADR-0038 W6 endgame gain: the SAME untracked-origin (``origin: None``)
    trust the tutor/reveal_hand widening already gives (W5 tails) extends to
    a ``dig``/``reveal_top``/``exile_top`` sibling — each of these ALSO
    populates a library/exile-top ``TrackedSet`` the ChangeZone's own
    ``target=TrackedSetFiltered`` names by its OWN core type
    (:func:`_change_zone_all_cores`), never a type borrowed from the
    sibling:

    * Call to the Kindred — a tribal ``Dig`` sibling; the put's own
      ``TrackedSetFiltered`` filter carries ``SharesQuality{CreatureType}``
      + a Creature core.
    * Lord of the Void — an ``ExileTop`` sibling; the put's own
      ``TrackedSetFiltered`` carries a bare Creature core.
    * Lonis, Cryptozoologist — a ``RevealTop`` sibling (an OPPONENT's
      library, control is orthogonal per CR 400.7); the put's own
      ``TrackedSetFiltered`` carries ``Cmc<=X`` + a nonland-Permanent core.
    * Anzrag's Rampage — an ``ExileTop`` sibling; the put's own
      ``TrackedSetFiltered`` carries ``And[Creature, ExiledBySource]``.

    Corpus-verified narrow (2026-07 census of every commander-legal
    ``dig``/``reveal_top``/``exile_top`` + ChangeZone{Battlefield, origin:
    None} pair, 63 hits): the land-only / self-blink shapes this widening
    could otherwise catch stay excluded downstream (see the shed guard
    below). CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_untracked_origin_widening_excludes_land_only():
    """ADR-0038 W6 endgame shed guard: the dig/reveal_top/exile_top origin
    widening above does NOT resurrect a land-only put as a cheat. Zimone's
    Experiment's "Put all land cards revealed this way onto the
    battlefield tapped and put all creature cards revealed this way into
    your hand" carries a ``Dig`` sibling (now admitted by the widening)
    feeding a ``ChangeZoneAll{Battlefield, origin: None, target:
    TrackedSetFiltered{filter: Typed(['Land'])}}`` — the SAME
    ``cores <= {"Land"}`` gate every other arm uses still excludes it
    (extra_land_drop's territory, not a cheat; the SEPARATE Hand-destined
    ChangeZoneAll for the creature half is not a battlefield put at all).
    """
    assert "cheat_into_play" not in _keys("Zimone's Experiment")


@pytest.mark.parametrize("name", ["Whiskervale Forerunner", "Break Out"])
def test_cheat_into_play_reveal_producer_own_filter_fallback(name):
    """ADR-0038 W6 endgame gain: when the fix-(e) reveal-producer chain
    carries NO ``RevealedHasCardType``/``TargetMatchesFilter`` condition at
    all — Whiskervale Forerunner's own gate is ``IsYourTurn()`` (a TIMING
    condition, not a type check); Break Out's "if that card has mana value
    2 or less" is swallowed with no residue — the SAME sibling ``Dig``
    that gates entry into the walk already carries real type evidence on
    its OWN filter (Creature core, cmc-limited but that doesn't change the
    core read), read via :func:`_reveal_producer_cores` /
    :func:`_reveal_producer_subtypes` (the dig/reveal_top/exile_top
    counterpart of :func:`_sibling_selector_cores`). Only tried when the
    condition walk found nothing type-shaped, so an explicit land-only
    condition elsewhere is never overridden. CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name", ["Hei Bai, Forest Guardian", "Songbirds' Blessing", "Genesis Storm"]
)
def test_cheat_into_play_kept_optional_to_battlefield_arm(name):
    """ADR-0038 W6 endgame gain: fix (d)'s RevealUntil destination read
    widens to ALSO accept phase's typed ``kept_optional_to == "Battlefield"``
    field (alongside the existing ``kept_destination == "Battlefield"``
    check) — the "you may put that card onto the battlefield [otherwise it
    stays with the rest]" OPTIONAL-put idiom, where ``kept_destination``
    itself carries the DEFAULT (non-optional) resting place:

    * Hei Bai, Forest Guardian — ``kept_destination: 'Library'``,
      ``kept_optional_to: 'Battlefield'``, a Shrine-subtype filter.
    * Songbirds' Blessing — ``kept_destination: 'Hand'``,
      ``kept_optional_to: 'Battlefield'``, an Aura-subtype filter.
    * Genesis Storm — ``kept_destination: 'Library'``,
      ``kept_optional_to: 'Battlefield'``, a nonland-Permanent core filter.

    Same never-guess core/subtype type-evidence gate either way (a
    land-only ``kept_optional_to`` filter still never fires). CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents(name)


def test_cheat_into_play_named_tutor_or_widening():
    """ADR-0038 W6 endgame gain: fix (f)'s named-tutor-with-no-core check
    (:func:`_sibling_named_tutor_no_core`) generalizes to an ``Or`` of
    named alternatives via :func:`_filter_all_named` — Agency Outfitter's
    "search your graveyard, hand and/or library for a card named
    Magnifying Glass and/or a card named Thinking Cap and put them onto
    the battlefield" carries ``Or[Typed(Named='magnifying glass'),
    Typed(Named='thinking cap')]``, neither branch carrying a core type of
    its own — the SAME "a name isn't a type" reasoning as the single-Named
    case (CR 201.4), just requiring EVERY Or branch to be Named (a mixed
    Or with a bare/core-typed branch is never trusted here)."""
    assert ("cheat_into_play", "you", "") in _idents("Agency Outfitter")


def test_cheat_into_play_untracked_origin_widening_bonus_gain():
    """ADR-0038 W6 endgame bonus gain (surfaced by the exile_top origin
    widening, NOT in the original 50 live_only sample — legacy misses it
    too): Xenagos, the Reveler's "[-6]: Exile the top seven cards of your
    library. You may put any number of creature and/or land cards from
    among them onto the battlefield" carries ``ChangeZone{Battlefield,
    origin: None, target: TrackedSetFiltered{filter: Or[Typed(Creature),
    Typed(Land)]}}`` — an ``exile_top`` sibling (now admitted by the
    origin widening) feeding a put whose OWN target filter names BOTH
    Creature and Land directly (unlike Archdruid's Charm's phase-collapsed
    modal, there is no swallowed "otherwise" branch here — the card
    genuinely, unconditionally allows creature cards too), so
    ``cores = {"Creature", "Land"}`` is not ``<= {"Land"}`` and the arm
    fires — the SAME multi-type Bribery-class reasoning Eternal Dominion's
    "artifact, creature, enchantment, or land" carve-out already
    established. CR 400.7."""
    assert ("cheat_into_play", "you", "") in _idents("Xenagos, the Reveler")


@pytest.mark.parametrize(
    "name",
    ["Talon Gates of Madara", "Boreas Charger", "Campus Renovation"],
)
def test_cheat_into_play_w6_endgame_shed_classes(name):
    """ADR-0038 W6 endgame sheds: three distinct legacy over-fires, none
    touching the widenings above (each correctly excludes on its own
    established gate):

    * Talon Gates of Madara — "{4}: Put this card from your hand onto the
      battlefield" is a LAND (Land — Gate) putting ITSELF via a bare
      ``SelfRef`` target — no core/subtype filter at all (a self-reference,
      not a type search — the genuine no-type-evidence self-put shape;
      Urban Retreat and Zareth San's "Put this card from your hand onto
      the battlefield" activated ability share the identical ``SelfRef``
      shape, unpinned here for brevity).
    * Boreas Charger — "Search your library for a number of Plains cards...
      put one of them onto the battlefield tapped" is a LAND search+put
      (extra_land_drop's territory, CR 205.3i); phase additionally drops
      the Plains subtype to an untyped filter, but the verdict (land, not a
      cheat) holds either way.
    * Campus Renovation — "Return...an artifact or enchantment card from
      your graveyard to the battlefield" is reanimation (``origin:
      'Graveyard'``, checklist #2, CR 400.7), NOT this lane; the card's
      separate "Exile the top two cards...you may play those cards" is an
      impulse-draw CAST permission (``GrantCastingPermission``), not a
      "without casting" put either (CR 601 — playing the card still uses
      normal casting/playing rules).
    """
    assert "cheat_into_play" not in _keys(name)


def test_cheat_into_play_warp_granting_is_not_a_cheat():
    """ADR-0038 W6 endgame shed: Tannuk, Steadfast Second's "Artifact cards
    and red creature cards in your hand have warp {2}{R}" is a legacy
    over-fire on a THEMATIC membership hunch (the deleted live-path
    detector's own comment: "a commander handing out warp is a cheat deck
    wanting fat creatures + cheat enablers"), not a mechanical match.
    CR 702.185a: Warp is an alternative CAST cost ("You may cast this card
    from your hand by paying [cost] rather than its mana cost") — the card
    still goes on the stack and is CAST, the opposite of CR 110.2/400.7's
    "put onto the battlefield WITHOUT casting it." No ``ChangeZone``/
    ``RevealUntil``/tutor node exists anywhere in Tannuk's tree; the
    warp grant is a pure static ``AddKeyword`` modification."""
    assert "cheat_into_play" not in _keys("Tannuk, Steadfast Second")


# ── batch 10: trigger-event / effect-tag / grant / P/T / static-mode ─────────


def test_creature_etb_trigger_arm():
    """CR 603.6a: Soul Warden's "Whenever another creature enters" watcher
    (controller null → you-scope) fires creature_etb; the SelfRef enters-draw
    (Elvish Visionary) is ETB value on itself, never a payoff engine."""
    assert ("creature_etb", "you", "") in _idents("Soul Warden")
    assert "creature_etb" not in _keys("Elvish Visionary")


@pytest.mark.parametrize("name", ["Panharmonicon", "Yarok, the Desecrated"])
def test_creature_etb_doubler_arm(name):
    """Arm 2 (the known-lossy-case improvement over the live byte mirror):
    a ``DoubleTriggers`` static whose ``EntersBattlefield`` cause covers
    creatures — Panharmonicon's ``[Artifact, Creature]``, Yarok's empty
    any-permanent form (Panharmonicon ruling 2021-03-19: "…causes a
    triggered ability of a permanent you control to trigger, that ability
    triggers an additional time")."""
    assert ("creature_etb", "you", "") in _idents(name)
    assert ("trigger_doubling", "you", "") in _idents(name)


def test_permanent_etb_generic_engine():
    """Amareth's "another permanent you control enters" (Permanent core +
    controller You — checklist #6) is permanent_etb, NOT creature_etb; Soul
    Warden's Creature core routes the other way."""
    assert ("permanent_etb", "you", "") in _idents("Amareth, the Lustrous")
    assert "creature_etb" not in _keys("Amareth, the Lustrous")
    assert "permanent_etb" not in _keys("Soul Warden")


def test_ltb_matters_fires_and_gates():
    """CR 603.6c: Luminous Phantom's LeavesBattlefield watcher fires. recall-
    completion b1 (ADR-0034): a SelfRef self-LTB VALUE trigger (Thalakos Seer —
    "when this leaves the battlefield, draw a card") NOW fires ``ltb_matters``
    scope "you" — there is no separate self_ltb lane, so live keys both self and
    other leaves on ltb_matters (verified live). The graveyard-ARRIVAL "from
    anywhere" watcher (Compost — CR 603.6c explicitly de-classifies it as an LTB
    ability) still never fires."""
    assert ("ltb_matters", "you", "") in _idents("Luminous Phantom")
    assert ("ltb_matters", "you", "") in _idents("Thalakos Seer")
    assert "ltb_matters" not in _keys("Compost")


def test_creature_cast_trigger_type_gate():
    """CR 701.5a: Beast Whisperer's creature-spell cast watcher fires scope
    "any"; Talrand's instant/sorcery Or-filter and Kambal's NONcreature
    filter (the ``{Non: Creature}`` negation is dropped, never flattened)
    stay out."""
    assert ("creature_cast_trigger", "any", "") in _idents("Beast Whisperer")
    assert "creature_cast_trigger" not in _keys("Talrand, Sky Summoner")
    assert "creature_cast_trigger" not in _keys("Kambal, Consul of Allocation")


def test_creature_cast_trigger_nested_emblem():
    """Garruk, Caller of Beasts's -7 ultimate "You get an emblem with
    'Whenever you cast a creature spell, ...'" carries the trigger def in
    a ``CreateEmblem`` effect's ``triggers`` list — the shared
    granted-trigger descent's ``CreateEmblem`` shape (ADR-0037/0038 W1
    batch-3, CR 701.5a)."""
    assert ("creature_cast_trigger", "any", "") in _idents("Garruk, Caller of Beasts")


def test_creature_cast_trigger_nested_token_grant():
    """Blink's Saga Chapter II/IV creates an Alien Angel token whose OWN
    static grants "Whenever an opponent casts a creature spell, ~ isn't a
    creature ..." — a ``GrantTrigger`` nested inside the Token effect
    inside the Chapter trigger's execute chain. Scope-blind by design
    (creature_cast_trigger hard-emits "any" regardless of who casts)."""
    assert ("creature_cast_trigger", "any", "") in _idents("Blink")


def test_creature_cast_trigger_nested_emblem_bonus_recall():
    """Ajani, Sleeper Agent's -6 emblem "Whenever you cast a creature or
    planeswalker spell, target opponent gets two poison counters." is the
    SAME CreateEmblem.triggers shape as Garruk — a genuine recall-
    completion the structural descent reaches beyond the residual
    live_only set (legacy's regex-based detection never structured this
    quoted emblem text at all, so it's a NEW crosswalk-only hit, not a
    role-mismatched over-fire — the Or-filter's Creature arm is a real
    creature-spell watch per CR 701.5a)."""
    assert ("creature_cast_trigger", "any", "") in _idents("Ajani, Sleeper Agent")


@pytest.mark.parametrize(
    "name",
    [
        "Boreal Outrider",
        "Communal Brewing",
        "Kozilek's Return",
        "Runadi, Behemoth Caller",
        "Volo, Itinerant Scholar",
        "Wildgrowth Archaic",
        "Glimpse of Nature",
    ],
)
def test_creature_cast_trigger_no_residue_synthesis(name):
    """Stage-A synthesis (ADR-0037/0038): "whenever you cast a[n] ...
    creature spell" phase re-templates as a REPLACEMENT effect on the
    entering creature (Boreal Outrider's SwallowedClause self-only
    collapse; Communal Brewing / Runadi / Wildgrowth Archaic's
    correctly-filtered replacement) or a ``CreateDelayedTrigger`` condition
    (Kozilek's Return's Eldrazi+CMC filter; Glimpse of Nature's "this
    turn" one-shot), or drops into a garbage placeholder node entirely
    (Volo's token-grant quote parse) — no shape the flat trigger-unit walk
    or the granted-trigger descent reaches.
    ``tree_synthesis._arm_creature_cast_trigger`` fills the gap from
    ``tree.oracle`` directly (CR 701.5a)."""
    assert ("creature_cast_trigger", "any", "") in _idents(name)


def test_opponent_cast_matters_recipient_gate():
    """Kambal's cast-player recipient (``valid_target Typed controller
    Opponent`` — checklist #5) fires scope "opponents"; the symmetric "a
    player casts" punisher (Eidolon of the Great Revel — CR 102.1: "a
    player" includes you) and the self-cast watcher (Beast Whisperer) stay
    out."""
    assert (
        "opponent_cast_matters",
        "opponents",
        "",
    ) in _idents("Kambal, Consul of Allocation")
    assert "opponent_cast_matters" not in _keys("Eidolon of the Great Revel")
    assert "opponent_cast_matters" not in _keys("Beast Whisperer")


def test_opponent_cast_matters_nested_static_grant():
    """Hunting Grounds's Threshold-gated static grants "Whenever an
    opponent casts a spell, ..." — a REAL nested ``SpellCast`` trigger def
    inside the static ability's ``GrantTrigger`` modification, not
    surfaced as its own flat trigger unit. The ``iter_nested_trigger_defs``
    shared descent (:func:`is_opponent_cast_trigger_def`, ADR-0037/0038 W1
    batch-3) reaches it (CR 102.2/102.3)."""
    assert ("opponent_cast_matters", "opponents", "") in _idents("Hunting Grounds")


def test_opponent_cast_matters_nested_emblem_trigger():
    """Jace, Unraveler of Secrets's -8 ultimate "You get an emblem with
    'Whenever an opponent casts their first spell each turn, counter that
    spell.'" carries the trigger def in a ``CreateEmblem`` effect's
    ``triggers`` list — the shared descent's SECOND shape (CR 102.2/102.3;
    CR 605.4)."""
    assert (
        "opponent_cast_matters",
        "opponents",
        "",
    ) in _idents("Jace, Unraveler of Secrets")


def test_opponent_cast_matters_soulbond_no_residue_synthesis():
    """Stage-A synthesis (ADR-0037/0038): Thundering Mightmare's
    soulbond-paired "Whenever an opponent casts a spell, put a +1/+1
    counter on this creature" carries NO node at all — the static's
    ``SourceIsPaired`` condition parses, but ``modifications`` is a
    genuinely EMPTY list (phase drops the granted trigger text entirely,
    not even an Unimplemented placeholder). ``tree_synthesis.
    _arm_opponent_cast_matters`` fills the gap from ``tree.oracle`` (CR
    102.2/102.3)."""
    assert (
        "opponent_cast_matters",
        "opponents",
        "",
    ) in _idents("Thundering Mightmare")


def test_combat_damage_matters_kind_and_recipient():
    """CR 510.1b: Coastal Piracy's CombatOnly player-connect fires
    combat_damage_matters; a creature recipient (Serpentine Basilisk) and
    the any-damage connect (Hypnotic Specter) route elsewhere."""
    assert ("combat_damage_matters", "opponents", "") in _idents("Coastal Piracy")
    assert "combat_damage_matters" not in _keys("Serpentine Basilisk")
    assert "combat_damage_matters" not in _keys("Hypnotic Specter")


def test_damage_to_opp_matters_any_kind():
    """CR 120.3: Hypnotic Specter's ``damage_kind Any`` opponent-connect
    fires damage_to_opp_matters; Coastal Piracy's CombatOnly kind is the
    combat lane, not this one."""
    assert ("damage_to_opp_matters", "opponents", "") in _idents("Hypnotic Specter")
    assert "damage_to_opp_matters" not in _keys("Coastal Piracy")


# ADR-0038 W3 batch 2 unit 4 — the damage_to_opp_matters nested granted-
# trigger arm (damage_to_player_trigger_kind, one predicate over BOTH a
# top-level trigger and a nested GrantTrigger def — the opponent_cast_
# matters/connive precedent): a damage-connect payoff granted through an
# Aura (Snake Umbra, Helm of the Ghastlord), a card's own static
# (Serpent Generator's token grant), or a planeswalker ultimate emblem
# (Vraska, Scheming Gorgon).
@pytest.mark.parametrize(
    "name",
    [
        "Snake Umbra",
        "Helm of the Ghastlord",
        "Serpent Generator",
        "Vraska, Scheming Gorgon",
    ],
)
def test_damage_to_opp_matters_nested_grant_arm(name):
    assert ("damage_to_opp_matters", "opponents", "") in _idents(name)


# ADR-0038 W3 batch 2 unit 4 — a SANCTIONED byte-identical mirror of the
# deleted DAMAGE_TO_OPP_MATTERS_REGEX (CR 119.3/510.1c): covers the tail
# phase can't structure as a ``deals_damage`` trigger — an Unknown-mode
# trigger (Talon of Pain), a combat-damage trigger whose OWN effect ALSO
# deals damage to the same player in a LATER clause the non-greedy regex
# span reaches (Sword of War and Peace), and a direct ETB/ability damage
# BURST with no reactive trigger shape at all (Fanatic of Mogis, Gruesome
# Scourger, Meria's Outrider, Sycorax Commander's villainous choice,
# Emberwilde Captain's monarch-punish, Magebane Lizard's noncreature-cast
# punisher, Bloodfeather Phoenix's cast-payoff, Asgardian Inspiration's
# noncombat-damage payoff, Arm with Aether's grant, Sorcerer Class's Class
# level, Stormbreath Dragon's monstrosity trigger, Tandem Lookout's
# soulbond grant, Vraska Swarm's Eminence's counter payoff).
@pytest.mark.parametrize(
    "name",
    [
        "Talon of Pain",
        "Sword of War and Peace",
        "Fanatic of Mogis",
        "Gruesome Scourger",
        "Meria's Outrider",
        "Sycorax Commander",
        "Emberwilde Captain",
        "Magebane Lizard",
        "Bloodfeather Phoenix",
        "Asgardian Inspiration",
        "Arm with Aether",
        "Sorcerer Class",
        "Stormbreath Dragon",
        "Tandem Lookout",
        "Vraska, Swarm's Eminence",
    ],
)
def test_damage_to_opp_matters_mirror_fallback(name):
    assert ("damage_to_opp_matters", "opponents", "") in _idents(name)


def test_damage_to_opp_matters_planeswalker_recipient_beyond_legacy_gain():
    """Hooded Blightfang's "Whenever a creature you control with deathtouch
    deals damage to a planeswalker, destroy that planeswalker" reaches a
    Planeswalker recipient — the SAME player-or-planeswalker reach
    combat_damage_matters already treats as "opponents" (Coastal Piracy's
    own docstring), read here via the nested tribal-source connect trigger.
    A genuine beyond-legacy recall gain (CR 120.3 / 510.1b), not an
    over-fire — legacy fires nothing damage-related for this card."""
    assert ("damage_to_opp_matters", "opponents", "") in _idents("Hooded Blightfang")


def test_second_spell_matters_constraint_arm():
    """The probe win (CR 603.2): Cori-Steel Cutter's SpellCast trigger
    carries ``constraint {NthSpellThisTurn, n: 2}`` — a clean structural
    read of the qualifier the old projection dropped. A bare SpellCast
    (Talrand) and the n=1 first-spell form (Alela, Cunning Conqueror) never
    fire."""
    assert ("second_spell_matters", "you", "") in _idents("Cori-Steel Cutter")
    assert "second_spell_matters" not in _keys("Talrand, Sky Summoner")
    assert "second_spell_matters" not in _keys("Alela, Cunning Conqueror")


def test_second_spell_matters_condition_arm():
    """The CONDITION form: Xerex Strobe-Knight's "Activate only if you've
    cast two or more spells this turn" is a ``YouCastSpellCountAtLeast
    count=2`` activation-restriction condition (CR 601)."""
    assert ("second_spell_matters", "you", "") in _idents("Xerex Strobe-Knight")


def test_second_spell_matters_static_condition_arm():
    """The static-continuous CONDITION form (b3 recall): Brightspear Zealot's
    "+2/+0 as long as you've cast two or more spells this turn" hangs a
    ``QuantityComparison`` over ``SpellsCastThisTurn`` (GE 2) on a
    continuous ability — a spell-velocity payoff (CR 603.2). A "three or
    more spells" static (Arclight Phoenix — a broader velocity lane, not
    the second-spell counter) never fires."""
    assert ("second_spell_matters", "you", "") in _idents("Brightspear Zealot")
    assert "second_spell_matters" not in _keys("Arclight Phoenix")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3 (CR 603.2) — the OnlyIfQuantity replacement-
        # condition variant :func:`~mtg_utils._card_ir.crosswalk.
        # spell_velocity_static_two` now also accepts (identical comparator/
        # lhs/rhs shape to QuantityComparison): Effortless Master's ETB
        # "enters with two +1/+1 counters if you've cast two or more spells
        # this turn".
        "Effortless Master",
        # The per-node text bridge (:func:`~mtg_utils._deck_forge.
        # crosswalk_signals._second_spell_node_text`) for a ``ModifyCost``
        # static whose ordinal-count qualifier carries NO structured field at
        # all ("The second spell you cast each turn costs {N} less to cast").
        "Alisaie Leveilleur",
        "Highspire Bell-Ringer",
        "Monk Class",
        "Uthros Psionicist",
        "Raging Battle Mouse",
        # The SAME text bridge for an ETB trigger whose ordinal condition is
        # dropped entirely (Codespell Cleric — "if it was the second spell you
        # cast this turn").
        "Codespell Cleric",
    ],
)
def test_second_spell_matters_node_text_bridge(name):
    assert ("second_spell_matters", "you", "") in _idents(name)


def test_second_spell_matters_ordinal_any_player_text_bridge():
    """Erayo, Soratami Ascendant (CR 601 casting spells): "Whenever the
    fourth spell of a turn is cast, flip Erayo" is a kind-agnostic,
    ANY-PLAYER ordinal count phase parses as a bare ``Unknown``-mode trigger
    with no count qualifier at all — identical in shape to a plain
    spellcast trigger. The SAME per-node text bridge as the "you cast"
    forms above now also matches "of (a|each|that) turn is cast" (passive,
    no "you"), distinct enough from the werewolf transform condition and
    Ertai's Scorn's opponent-scoped discount that neither cross-matches
    (both lack an ordinal word). The legacy IR's own byte-mirror
    (``_SECOND_SPELL_MIRROR`` in ``_signals_ir.py``) fires the SAME way —
    pinned in ``tests/deck-forge/test_signals_effect_axes.py::
    test_spell_count_storm_widen``."""
    assert ("second_spell_matters", "you", "") in _idents("Erayo, Soratami Ascendant")


@pytest.mark.parametrize("name", ["Ertai's Scorn", "Call of the Full Moon"])
def test_second_spell_matters_excludes_unrelated_two_spells_text(name):
    """Two legacy over-fires the ``"cast two or more spells"`` bare-text regex
    catches but which are NOT the spell-velocity build-around (ADJUDICATED
    SHEDS, ADR-0038 W3 batch 3): Ertai's Scorn's cost reduction counts the
    OPPONENT's spell count (``SpellsCastThisTurn scope=Opponents``), excluded by
    :func:`~mtg_utils._card_ir.crosswalk.spell_velocity_static_two`'s own
    Controller-scope gate (a documented b3 design boundary, not this session's
    call); Call of the Full Moon's "if a player cast two or more spells LAST
    turn" is the Innistrad werewolf day/night TRANSFORM condition (CR 603.4
    intervening-if + CR 712 Transform) — a normal triggered ability with an
    unrelated mechanic that merely shares the word "spells", never a spell-
    velocity payoff. The narrower "<ordinal> spell YOU CAST (each|this) turn"
    node-text bridge never matches either card's actual wording."""
    assert "second_spell_matters" not in _keys(name)


@pytest.mark.parametrize(
    "name", ["Werewolf Ransacker", "Krallenhorde Howler", "Howlpack Alpha"]
)
def test_second_spell_matters_excludes_werewolf_transform_class(name):
    """ADR-0038 W3 batch 4 — re-verified representatives of the ~32-card
    Innistrad werewolf TRANSFORM-back-face class (CR 603.4 intervening-if +
    CR 712 Transform), same ADJUDICATED-SHED family as Call of the Full
    Moon above: "At the beginning of each upkeep, if a player cast two or
    more spells last turn, transform this creature." Legacy's bare
    ``"cast two or more spells"`` regex over-fires on all ~32; the crosswalk
    correctly excludes them on TWO independent grounds, not just wording
    luck: (1) the condition's qty node is ``SpellsCastLastTurn``, not
    :func:`~mtg_utils._card_ir.crosswalk.spell_velocity_static_two`'s
    required ``SpellsCastThisTurn``; (2) the werewolf's OWN generated
    description never contains "you cast" or an ordinal word, so
    ``_second_spell_node_text`` doesn't match either. A genuine crosswalk
    precision gain over the legacy byte mirror, not an over-fire risk."""
    assert "second_spell_matters" not in _keys(name)


def test_xspell_matters_two_arms():
    """CR 107.3: Zaxara's ``HasXInManaCost`` cast-watcher predicate and
    Rosheen's ``XCostOnly`` mana restriction both fire; a spell that merely
    HAS {X} in its own cost (Hydroid Krasis) never does."""
    assert ("xspell_matters", "you", "") in _idents("Zaxara, the Exemplary")
    assert ("xspell_matters", "you", "") in _idents("Rosheen Meanderer")
    assert "xspell_matters" not in _keys("Hydroid Krasis")


def test_counter_control_stack_counter_only():
    """CR 701.6a: Counterspell's ``Counter {StackSpell}`` fires; the "can't
    be countered" permission statics (Vexing Shusher) are not a counter
    effect."""
    assert ("counter_control", "you", "") in _idents("Counterspell")
    assert "counter_control" not in _keys("Vexing Shusher")


def test_bounce_tempo_direction_gate():
    """CR 402.1: Unsummon's bounce of an unowned creature is tempo; the
    self-bounce value engine (Aviary Mechanic — subject controller You,
    checklist #2) never fires."""
    assert ("bounce_tempo", "you", "") in _idents("Unsummon")
    assert "bounce_tempo" not in _keys("Aviary Mechanic")


@pytest.mark.parametrize(
    "name",
    [
        "Abzan Devotee",  # SelfRef self-return from graveyard
        "Altar of the Wretched",  # SelfRef activated self-return
        "Aphetto Dredging",  # targeted "from your graveyard" recall
    ],
)
def test_bounce_tempo_excludes_graveyard_returns(name):
    """Phase emits a ZONE-LESS Bounce for graveyard-to-hand returns
    (phase_parse_bug [P21] — the InZone:Graveyard marker is dropped), so
    they are byte-shaped like battlefield tempo bounces. Two adjudicated
    gates restore the boundary: a SelfRef-subject veto (a self-return is
    recursion value, never tempo — also correct for battlefield self-bounce
    per the Aviary Mechanic gate) and the [P8]-precedent node-local
    description screen for targeted "from ... graveyard" recalls (CR 402.1
    vs 404.1: a graveyard return is recursion, not tempo)."""
    assert "bounce_tempo" not in _keys(name)


def test_bounce_tempo_gy_screen_keeps_live_positives():
    """The [P21] gates must not over-cut the live lane's members: battlefield
    SELF-bounce fires (Blinking Spirit — SelfRef with no graveyard clause;
    live includes the self-bounce family), and a unit pairing a genuine
    tempo bounce with a graveyard recall in one description blob fires off
    the tempo half (Aether Helix — two bounce effects, so the single-bounce
    screen stands down)."""
    assert ("bounce_tempo", "you", "") in _idents("Blinking Spirit")
    assert ("bounce_tempo", "you", "") in _idents("Aether Helix")


def test_bounce_tempo_p21_empty_desc_residue_pinned():
    """KNOWN [P21] residue, deliberately still firing: phase drops BOTH the
    InZone:Graveyard marker AND the nested unit's description for the
    pay-to-return self-recursion family (Asgardian Inspiration — "return
    this card from your graveyard" survives only in the card oracle, which
    the crosswalk must not re-grep). 23 cards corpus-wide; the Stage-3 [P21]
    supplement arm re-types these — flip this pin when it lands."""
    assert "bounce_tempo" in _keys("Asgardian Inspiration")


def test_power_double_typed_tag():
    """CR 613.4c: Unleash Fury's ``DoublePT mode=Power`` fires; a flat pump
    (Giant Growth — a ``Pump`` node, not a doubling tag) never does."""
    assert ("power_double", "you", "") in _idents("Unleash Fury")
    assert "power_double" not in _keys("Giant Growth")


@pytest.mark.parametrize("name", ["Snakeskin Veil", "Jump"])
def test_keyword_grant_target_single_target(name):
    """CR 613.1f: an ``AddKeyword`` whose affected is ``ParentTarget`` (the
    single-target tell) fires keyword_grant_target; a team anthem (Akroma's
    Memorial) is the team lanes' shape, not this one."""
    assert ("keyword_grant_target", "you", "") in _idents(name)


def test_keyword_grant_target_excludes_team_anthem():
    assert "keyword_grant_target" not in _keys("Akroma's Memorial")


def test_keyword_grant_target_trigger_threaded_target():
    """ADR-0038 W3 batch 4: the threaded-target walk (``It gains X`` idiom)
    now runs for TRIGGER-origin units too, not just abilities — Conquering
    Manticore's ETB "gain control of target creature ... Untap that
    creature. It gains haste" threads the GainControl's Typed target through
    the Untap/GenericEffect chain to the ParentTarget-affected haste static
    (the SAME shape as the ability-form idiom, just riding a GainControl
    producer effect first). Was a caller-side origin gate (``iter_
    single_target_grants`` only ran for ``unit.origin == "ability"``), not a
    missing accessor. CR 613.1f."""
    assert ("keyword_grant_target", "you", "") in _idents("Conquering Manticore")


@pytest.mark.parametrize(
    "name", ["Chariot of the Sun", "Infuse with Vitality", "Balloon Stand"]
)
def test_keyword_grant_target_kept_mirror_fallback(name):
    """ADR-0038 W3 batch 4: three phase-parse-loss residues with NO
    AddKeyword node anywhere for the grant — Chariot of the Sun's "gains
    flying and has base toughness 1" drops the AddKeyword modification
    silently (only SetToughness survives); Infuse with Vitality's "gains
    deathtouch and \"...\"" and Balloon Stand's modal Visit branch are both
    entirely ``Unimplemented``/unparsed. Recovered by the deleted SWEEP
    detector's exact regex, scanned whenever keyword_grant_target hasn't
    already fired structurally (the legacy's own residue path). CR 613.1f."""
    assert ("keyword_grant_target", "you", "") in _idents(name)


def test_keyword_grant_target_kept_mirror_protection_choice():
    """ADR-0038 W3 batch 4: Giver of Runes' "Another target creature you
    control gains protection from colorless or from the color of your
    choice" is a modal ``ChooseOneOf`` the flat/deep threaded-target walks
    don't descend into (widening the SHARED ``iter_threaded_target_statics``
    helper to follow ``ChooseOneOf.branches`` corpus-verified WRONG — it
    over-fired on 6 "target creature gains your choice of KEYWORD1 or
    KEYWORD2" modal cards legacy does NOT recognize, e.g. Apostle's
    Blessing/Angelic Intervention/Practiced Offense). The kept-mirror text
    fallback recovers Giver of Runes narrowly (its literal "target creature
    you control gains protection" prefix) without that structural widening
    or its over-fire. CR 613.1f."""
    assert ("keyword_grant_target", "you", "") in _idents("Giver of Runes")


def test_keyword_grant_target_reanimate_with_haste_beyond_legacy_gain():
    """ADR-0038 W3 batch 4 adjudicated GAIN: Yggdrasil, Rebirth Engine's
    "Put a creature card exiled with Yggdrasil onto the battlefield under
    your control. It gains haste until end of turn." is a genuine CR
    613.1f single-target keyword grant to the just-reanimated creature (the
    threaded-target walk already covered this ability-origin shape before
    this batch); legacy's OLD arm never recognized the exile-zone target
    filter. Pinned as an intentional beyond-legacy precision gain, not a
    shed."""
    assert ("keyword_grant_target", "you", "") in _idents("Yggdrasil, Rebirth Engine")


def test_protection_grant_arms():
    """CR 702.16a/702.11a: Gods Willing's parameterized ``{Protection: …}``
    variant (the KEY is the keyword name) and Snakeskin Veil's hexproof
    single-target grant both fire; a non-protective grant (Jump — flying)
    never does."""
    assert ("protection_grant", "you", "") in _idents("Gods Willing")
    assert ("protection_grant", "you", "") in _idents("Snakeskin Veil")
    assert "protection_grant" not in _keys("Jump")


def test_all_creatures_kw_grant_symmetric_gate():
    """Concordant Crossroads' "All creatures have haste" (controller NULL —
    the symmetric global, checklist #5 → scope "any") fires; Levitation's
    "Creatures you control" is the your-team shape, not the symmetric one."""
    assert ("all_creatures_kw_grant", "any", "") in _idents("Concordant Crossroads")
    assert "all_creatures_kw_grant" not in _keys("Levitation")


def test_team_evasion_grant_generic_team_gate():
    """Levitation's team flying grant fires (CR 702.9); the chosen-type
    tribal grant (Cover of Darkness — an ``IsChosenCreatureType`` predicate
    fails the generic-team gate; the live path rides its mirror there —
    supplement tail) and the symmetric all-creatures grant (Concordant
    Crossroads) never fire."""
    assert ("team_evasion_grant", "you", "") in _idents("Levitation")
    assert "team_evasion_grant" not in _keys("Cover of Darkness")
    assert "team_evasion_grant" not in _keys("Concordant Crossroads")


@pytest.mark.parametrize(
    "name",
    [
        # ADR-0038 W3 batch 3: the BROADER team_evasion_grant forms — a
        # byte-identical port of live's own SANCTIONED kept-oracle mirror
        # (``_IR_KEPT_DETECTORS``), deliberately broader than the narrow
        # structural ``_is_team_creature_grant`` gate (subtype/color/power/
        # equipped-qualified + ONE-SHOT grants + the "can't be blocked"
        # AddStaticMode idiom, which carries no AddKeyword concept mapping
        # of its own). CR 702.9/702.13/702.28/702.31/702.36/702.111/
        # 702.118/509.1b (evasion ability definition).
        "Galerider Sliver",  # tribal: Sliver creatures you control have flying
        "Deepchannel Mentor",  # color: Blue creatures you control can't be blocked
        "Anikthea, Hand of Erebos",  # core-type: Other enchantment creatures
        "Delney, Streetwise Lookout",  # power-qualified can't-be-blocked
        "Dread Charge",  # one-shot color-qualified can't-be-blocked
        "Agility Bobblehead",  # one-shot activated-ability can't-be-blocked
        "Dalakos, Crafter of Wonders",  # Equipped-qualified team grant
    ],
)
def test_team_evasion_grant_broader_kept_mirror(name):
    """ADR-0038 W3 batch 3: team_evasion_grant's kept-oracle mirror recovers
    the tribal/color/core-type/power/equipped/one-shot/can't-be-blocked
    forms the narrow structural gate above deliberately excludes (that gate
    stays scoped to the fully-generic continuous team anthem). Verified
    against the real Card IR this session; each card's phase record is
    pinned in ``crosswalk_fixture_cards.json``."""
    assert ("team_evasion_grant", "you", "") in _idents(name)


def test_aura_equip_kw_grant_subgroup_gate():
    """Rashel's "Auras you control have exalted" (Subtype Aura + controller
    You) fires; the name-scoped controller-null Equipment cycle (Shield of
    Kaldra) and the equipped-CREATURE recipient grant (Cori-Steel Cutter's
    haste — no Aura/Equipment subtype on the affected filter) never fire."""
    assert ("aura_equip_kw_grant", "you", "") in _idents("Rashel, Fist of Torm")
    assert "aura_equip_kw_grant" not in _keys("Shield of Kaldra")
    assert "aura_equip_kw_grant" not in _keys("Cori-Steel Cutter")


def test_base_pt_set_set_and_switch_arms():
    """CR 613.4b/613.4d: Polymorphist's Jest (SetPower+SetToughness on one
    mod site) and Merfolk Thaumaturgist (``SwitchPT``) fire scope "any"."""
    assert ("base_pt_set", "any", "") in _idents("Polymorphist's Jest")
    assert ("base_pt_set", "any", "") in _idents("Merfolk Thaumaturgist")


def test_base_pt_set_animate_carve_out():
    """THE over-fire gate (live history): the mass land animator (Living
    Plane — a Land-cored affected filter) is a land_creatures_matter theme,
    never base_pt_set; a flat pump (Giant Growth) has no Set mods. ADR-0038
    W3 batch 4: the carve-out is TEXT-driven (Living Plane's "are 1/1
    creatures" names neither ``_BASE_PT_RAW_HOOK`` nor
    ``_BASE_PT_ANIMATE_HOOK``), not a core-type/subtype gate — see
    ``test_base_pt_set_self_transform_hooks`` for the SelfRef/artifact-target
    members a core-type gate previously dropped."""
    assert "base_pt_set" not in _keys("Living Plane")
    assert "base_pt_set" not in _keys("Giant Growth")


@pytest.mark.parametrize("name", ["Figure of Destiny", "Singing Tree"])
def test_base_pt_set_self_transform_hooks(name):
    """ADR-0038 W3 batch 4 (corpus re-measure): membership is TEXT-HOOK
    driven (``_BASE_PT_RAW_HOOK`` — a literal "base power"/"base toughness"),
    not subject-core-type driven — a prior cut blanket-excluded EVERY
    SelfRef site (Angel's Tomb/man-lands' carve-out), which also wrongly
    dropped Figure of Destiny's self-level-up cycle ("becomes a Kithkin
    Spirit with base power and toughness 2/2"). Singing Tree's "has base
    power 0" is a SINGLE stat (SetPower alone, no SetToughness) — CR
    613.4b's "and/or" covers it; a prior cut required BOTH stats present."""
    assert ("base_pt_set", "any", "") in _idents(name)


def test_base_pt_set_artifact_target_animate_hook():
    """ADR-0038 W3 batch 4: Ensoul Artifact's "Enchanted artifact is a
    creature with base power and toughness N/N in addition to its other
    types" is a TARGETED (not self) Artifact-cored site that DOES name a
    hook (both RAW and ANIMATE) — a prior cut's blanket Land/Artifact
    core-type exclusion dropped it too, conflating it with the TEXT-
    excluded mass animators (Living Plane, which names neither hook).
    CR 613.4b."""
    assert ("base_pt_set", "any", "") in _idents("Ensoul Artifact")
    assert ("base_pt_set", "any", "") in _idents("Riddleform")


def test_base_pt_set_excludes_object_stats_reference():
    """ADR-0038 W3 batch 4: Eldrazi Mimic's "change this creature's base
    power and toughness to that creature's power and toughness" is a
    DYNAMIC pair whose value Refs ANOTHER object's OWN Power/Toughness — a
    copy-stats idiom, not the toolbox's SCALAR dynamic form (Trench
    Gorger's exiled-card count DOES fire). The raw text still literally
    names "base power"/"base toughness", so the hook alone can't
    discriminate — pop-verified False against legacy."""
    assert "base_pt_set" not in _keys("Eldrazi Mimic")
    assert ("base_pt_set", "any", "") in _idents("Trench Gorger")


def test_base_pt_set_excludes_off_battlefield_gate():
    """ADR-0038 W3 batch 4: Grist, the Hunger Tide's "As long as ~ isn't on
    the battlefield, it's a 1/1 Insect creature in addition to its other
    types" (a Commander-eligibility marker) is gated by a condition negating
    on-battlefield presence — CR 613's layers apply to a permanent ON the
    battlefield, so an off-battlefield-only P/T set is never a genuine
    build-around; pop-verified False against legacy."""
    assert "base_pt_set" not in _keys("Grist, the Hunger Tide")


def test_base_pt_set_animate_effect_shape():
    """ADR-0038 W3 batch 6: Belligerent Yearling's "you may have ~'s base
    power become equal to that creature's power" trigger carries its base
    ``power`` as a DIRECT field on a top-level ``Animate`` effect — never
    decomposed into a SetPower modification at all, a distinct node shape
    from the sites-loop's SetPower/SetToughness pair. A power-ONLY set
    equal to ANOTHER object's power (not a full Eldrazi-Mimic-style
    power+toughness identity copy) still qualifies — CR 613.4b's
    "and/or"."""
    assert ("base_pt_set", "any", "") in _idents("Belligerent Yearling")


# ── ADR-0038 W5 tails: base_pt_set deep GenericEffect/CreateEmblem descent ──


def test_base_pt_set_modal_mode_ability_descent():
    """Storvald, Frost Giant Jarl's "Whenever ~ enters or attacks, choose
    one or both — Target creature has base power and toughness 7/7 ... /
    Target creature has base power and toughness 1/1 ..." — each MODAL
    mode's own ``S_mode_abilities.effect`` (a ``GenericEffect``) carries its
    OWN ``target`` field, self-contained per mode; the nested static's
    ``ParentTarget`` resolves through THAT mode's target, not the outer
    trigger's (which carries none). CR 613.4b / 700.2 (modal choice)."""
    assert ("base_pt_set", "any", "") in _idents("Storvald, Frost Giant Jarl")


def test_base_pt_set_create_emblem_statics_descent():
    """The Capitoline Triad's activated ability grants an emblem with
    "Creatures you control have base power and toughness 9/9" — a
    continuous ability living directly on ``CreateEmblem.statics``, no
    target/ParentTarget involved at all. CR 613.4b / 114.2 (emblems)."""
    assert ("base_pt_set", "any", "") in _idents("The Capitoline Triad")


def test_base_pt_set_create_emblem_trigger_descent():
    """Tezzeret the Schemer's -7 emblem grants a TRIGGERED ability ("At the
    beginning of combat on your turn, target artifact you control becomes
    an artifact creature with base power and toughness 5/5") — the
    ``GenericEffect`` lives under ``CreateEmblem.triggers[i].execute.
    effect``, arbitrarily deeper than the unit's own top-level effect
    chain the OLD single-level arm read. CR 613.4b / 114.2."""
    assert ("base_pt_set", "any", "") in _idents("Tezzeret the Schemer")


def test_base_pt_set_triggering_source_resolves():
    """Creepy Puppeteer's "you may have THAT creature's base power and
    toughness become 4/3" back-references the OTHER attacker from the SAME
    trigger event (``TriggeringSource``, CR 603.2) — a definite,
    resolvable subject, same footing as a SelfRef/Typed target."""
    assert ("base_pt_set", "any", "") in _idents("Creepy Puppeteer")


def test_base_pt_set_mismatched_scalar_reuse_not_excluded():
    """Sita Varma's "have the base power and toughness of each other
    creature you control become equal to Sita Varma's power" sets BOTH
    ``SetPowerDynamic`` AND ``SetToughnessDynamic`` to a Ref of the SAME
    ``qty=Power`` (never ``Toughness``) — a mismatched-quantity SCALAR
    reuse (CR 613.4b), not the full-identity "become a copy of that
    creature's power AND toughness" idiom :func:`refs_other_object_stats`
    excludes (see ``test_base_pt_set_excludes_object_stats_reference``,
    unaffected — Eldrazi Mimic's pair IS matched: Power->Power AND
    Toughness->Toughness). Legacy's own regex-based
    ``_recover_dynamic_base_pt_set`` (arm 6) names Sita Varma as a worked
    example of this exact idiom."""
    assert ("base_pt_set", "any", "") in _idents("Sita Varma, Masked Racer")


def test_base_pt_set_granted_ability_definition_descent():
    """Gigantoplasm's BecomeCopy-quoted granted ACTIVATED ability ("{X}: ~
    has base power and toughness X/X") carries its ``SetPowerDynamic``/
    ``SetToughnessDynamic`` pair on ``BecomeCopy.additional_modifications``'
    ``GrantAbility.definition.effect`` (a ``GenericEffect`` with
    ``affected=SelfRef``) — reached only by the deep ``iter_typed_nodes``
    descent, not the unit's own direct effect chain. CR 613.4b / 707
    (copy effects)."""
    assert ("base_pt_set", "any", "") in _idents("Gigantoplasm")


def test_variable_pt_cda_gate():
    """CR 604.3 / 613.4a: Tarmogoyf's ``characteristic_defining`` static with
    ``SetDynamicPower`` fires scope "any"; a fixed-number set (Polymorphist's
    Jest) is base_pt_set, not the CDA lane."""
    assert ("variable_pt", "any", "") in _idents("Tarmogoyf")
    assert "variable_pt" not in _keys("Polymorphist's Jest")


def test_trigger_doubling_excludes_replacement_doublers():
    """Panharmonicon's ``DoubleTriggers`` static fires (see the doubler-arm
    test for the positive); Doubling Season's token/counter REPLACEMENT
    doublers (``quantity_modification`` nodes) are split lanes and never
    fire trigger_doubling."""
    assert "trigger_doubling" not in _keys("Doubling Season")


def test_trigger_doubling_granted_static_recovery():
    """Stage-A recovery (ADR-0038): Dungeon Delver's "Commander creatures
    you own have 'Room abilities of dungeons you own trigger an additional
    time.'" lands as a ``GrantStaticAbility`` node phase doesn't decompose
    further (no ``DoubleTriggers`` mode exists to read) — read structurally
    off the grant's own raw text (CR 603.2)."""
    assert ("trigger_doubling", "you", "") in _idents("Dungeon Delver")


def test_trigger_doubling_granted_trigger_recovery():
    """The Masamune's Equip grant ("Equipped creature has 'If a creature
    dying causes a triggered ability of this creature or an emblem you own
    to trigger, that ability triggers an additional time.'") lands as a
    ``GrantStaticAbility`` node — the SAME structural read as Dungeon
    Delver, just granted via Equip instead of a Commander-creature anthem."""
    assert ("trigger_doubling", "you", "") in _idents("The Masamune")


def test_trigger_doubling_excludes_replacement_action_repeaters():
    """ADR-0034 shed: The Valeyard's "they face that choice an additional
    time" (a villainous-choice REPLACEMENT, CR 701.55c) and "you may vote an
    additional time" (a multi-vote REPLACEMENT, CR 701.38d) share the "an
    additional time" phrase with CR 603.2 trigger-doubling but neither
    clause contains the word "trigger" — a REPEATED ACTION, never a
    triggered-ability doubler. The old-IR's own broad ``\\ban additional
    time\\b`` fallback regex over-fires here; the crosswalk's tighter
    ``trigger(s) ... an additional time`` idiom correctly excludes it."""
    assert "trigger_doubling" not in _keys("The Valeyard")


@pytest.mark.parametrize("name", ["Warmonger Hellkite", "Juggernaut"])
def test_forced_attack_static_mode(name):
    """CR 508.1d: a ``MustAttack`` static fires scope "any" — the table-wide
    force (Warmonger Hellkite) AND the SelfRef drawback (Juggernaut, kept IN
    to match live)."""
    assert ("forced_attack", "any", "") in _idents(name)


def test_forced_attack_excludes_goad():
    """Goad is a distinct typed tag (CR 701.15a) — Disrupt Decorum stays in
    goad_makers, never forced_attack."""
    assert "forced_attack" not in _keys("Disrupt Decorum")


def test_forced_attack_structural_no_affected():
    """ADR-0038 W3 batch 3: a bare self-compulsion with NO ``affected``
    node at all (Kookus — "attacks this turn if able" flattened into a
    separate damage-punisher effect by legacy's regex cascade, but phase
    still structures a genuine MustAttack static) is a real forced_attack
    member — a beyond-legacy gain, CR 508.1d."""
    assert ("forced_attack", "any", "") in _idents("Kookus")


def test_forced_attack_excludes_self_must_attack_or_block():
    """ADR-0038 W3 batch 3 (CR 508.1d + CR 509.1c): Iron Golem / Khârn the
    Betrayer's OWN "attacks or blocks each combat if able" is a COMBINED
    self MustAttack+MustBlock static — legacy's project.py classifies this
    ``restriction``, never ``force_attack`` (two genuinely different CR
    rules, not one lane). Must NOT fire, structurally or via the text
    fallback."""
    assert "forced_attack" not in _keys("Iron Golem")
    assert "forced_attack" not in _keys("Khârn the Betrayer")


def test_forced_attack_grants_combo_not_excluded():
    """ADR-0038 W3 batch 3: Boros Battleshaper's GRANTED "up to one target
    creature attacks or blocks this combat if able" (an ``AddStaticMode``
    MustAttack+MustBlock combo delivered via a trigger to a TARGET,
    ``affected`` = ParentTarget, not SelfRef) is NOT the self-combo
    restriction above — legacy fires force_attack for it (the structural
    restriction override is project.py's card-level static reader only)."""
    assert ("forced_attack", "any", "") in _idents("Boros Battleshaper")


def test_forced_attack_excludes_last_created_token():
    """ADR-0038 W3 batch 3: Legion Warboss's MustAttack static affects
    ``LastCreated`` — the freshly-created Goblin token, not the card's own
    engine (phase's tags are position-relative post-producer-effect). Must
    NOT fire forced_attack for the card."""
    assert "forced_attack" not in _keys("Legion Warboss")


def test_forced_attack_text_idiom_fallback():
    """ADR-0038 W3 batch 3 (CR 508.1d): the bucket-B "attacks ... if able"
    text idiom (``_FORCE_ATTACK``, imported single-source from
    supplement.py's own clause-grammar recovery) — Ekundu Cyclops's "If a
    creature you control attacks, this creature also attacks if able"
    phase drops to a bare Unimplemented clause."""
    assert ("forced_attack", "any", "") in _idents("Ekundu Cyclops")


def test_forced_attack_nearest_opponent_idiom():
    """ADR-0038 W3 batch 3 (CR 508.1c): the "attack only the nearest
    opponent" directional-restriction idiom (``_FORCE_ATTACK_REF``,
    imported single-source from project.py's own card-level marker
    recovery) — Mystic Barrier."""
    assert ("forced_attack", "any", "") in _idents("Mystic Barrier")


def test_forced_attack_punisher_idiom():
    """ADR-0038 W3 batch 3 (CR 508.1d's requirement family): the "didn't
    attack this turn" PUNISHER idiom, scope "you" — Erg Raiders. Phase
    carries no node for a punishment triggered off a creature's PAST
    inaction (only the ``AttackedThisTurn`` state-check property)."""
    assert ("forced_attack", "you", "") in _idents("Erg Raiders")


def test_forced_attack_excludes_force_block():
    """ADR-0038 W3 batch 3 (CR 509.1c): Avalanche Tusker's "Whenever ~
    attacks, target creature ... blocks it this combat if able" is a
    dedicated ForceBlock provoke effect — "attacks" is only the trigger
    condition, "if able" binds to "blocks", not "attacks". Must NOT fire
    forced_attack."""
    assert "forced_attack" not in _keys("Avalanche Tusker")


def test_forced_attack_per_clause_force_block_gate():
    """ADR-0038 W3 batch 3: Magnetic Web carries BOTH a real team
    compulsion ("all creatures with magnet counters on them attack if
    able") AND a SEPARATE ForceBlock trigger ("... block that creature
    this turn if able") in the SAME card — the ForceBlock exclusion must
    be scoped per-CLAUSE, not whole-tree, or the real compulsion would be
    wrongly suppressed too."""
    assert ("forced_attack", "any", "") in _idents("Magnetic Web")


def test_forced_attack_excludes_force_block_named_referent():
    """ADR-0038 W3 batch 3 (CR 509.1c): Tolsimir, Midnight's Light's
    "target creature an opponent controls blocks THAT WOLF this combat if
    able" is the SAME ForceBlock idiom with a named-subtype back-reference
    instead of "that creature" — the exclusion pattern must generalize
    (any noun after "that"), not just the literal word "creature"."""
    assert "forced_attack" not in _keys("Tolsimir, Midnight's Light")


def test_forced_attack_excludes_created_token_compulsion():
    """ADR-0038 W3 batch 3: Furygale Flocking's created tokens "that
    attack that opponent this turn if able" carry the compulsion on a
    FRESH TOKEN, not the card's own engine — the SAME LastCreated-style
    exclusion the structural MustAttack arm applies, ported to the text
    idiom (Legion Warboss precedent). Must NOT fire forced_attack."""
    assert "forced_attack" not in _keys("Furygale Flocking")


def test_forced_attack_beyond_legacy_gains():
    """ADR-0038 W3 batch 3 (CR 508.1d): three MORE beyond-legacy gains
    legacy's per-effect-category-early-wins cascade masks (the whole
    ability resolves to an earlier-matching category before the
    compulsion tail ever reaches recovery) — Illusionist's Gambit
    ("restriction" swallows the additional-combat compulsion), Sizzling
    Soloist ("cant_block" swallows the single-target opponent compulsion),
    The Brothers' War (a Saga chapter's "Choose two target players" leads
    the sentence)."""
    assert ("forced_attack", "any", "") in _idents("Illusionist's Gambit")
    assert ("forced_attack", "any", "") in _idents("Sizzling Soloist")
    assert ("forced_attack", "any", "") in _idents("The Brothers' War")


@pytest.mark.parametrize("name", ["Fog", "Story Circle"])
def test_damage_prevention_effect_tag(name):
    """CR 615.1: a ``PreventDamage`` effect fires scope "you"."""
    assert ("damage_prevention", "you", "") in _idents(name)


def test_damage_prevention_excludes_protection_grant():
    """Gods Willing grants protection (CR 702.16a) — a different typed node,
    routed to protection_grant, never a PreventDamage read."""
    assert "damage_prevention" not in _keys("Gods Willing")


def test_damage_equal_power_fling_shape():
    """CR 120.3: Fling's ``DealDamage`` with a Power-qty ``Ref`` amount
    reaching ``{Any}`` fires; a fixed-amount ping (Prodigal Sorcerer) never
    does."""
    assert ("damage_equal_power", "you", "") in _idents("Fling")
    assert "damage_equal_power" not in _keys("Prodigal Sorcerer")


def test_damage_equal_power_or_and_player_recipient():
    """recall-completion b2 (ADR-0034): Brion Stoutarm throws a creature "to target
    player or planeswalker" — a Power-qty ``Ref`` DealDamage whose recipient is an
    ``Or`` CONTAINING a player. The ``_DEP_PLAYER_TAGS`` / Typed-Player read only saw
    a top-level player node; the Or/And recursion now reaches it (CR 120.3)."""
    assert ("damage_equal_power", "you", "") in _idents("Brion Stoutarm")


# NB: land_destruction stays KEPT (the batch-8 reclassification upheld) — the
# structural membership-gated arm reproduces the live 23-card set 23/23 but
# adds 2 non-byte-identical extras (Goblin Grenadiers, Orcish Settlers), so it
# fails the spec's byte-match condition for superseding the KEPT verdict.


# ── batch 10: the four adjudicated batch-9 follow-up fixes ────────────────────


def test_facedown_matters_manifest_dread_node():
    """Fix (a): the first-class ``ManifestDread`` node (CR 701.55) fires
    facedown_matters + facedown_makers (Abhorrent Oculus — live fires the
    pair; manifest dread both makes the face-down 2/2 and selects for the
    face-down theme)."""
    keys = _keys("Abhorrent Oculus")
    assert "facedown_matters" in keys
    assert "facedown_makers" in keys


def test_facedown_matters_plain_manifest_maker_stays_out():
    """The tag read keeps a plain Manifest/Cloak DOER (Cloudform — shares the
    ``facedown`` concept) out of the payoff arm."""
    assert "facedown_matters" not in _keys("Cloudform")
    assert "facedown_makers" in _keys("Cloudform")


def test_combat_buff_engine_reads_nested_mod_sites():
    """Fix (b): Aethershield Artificer's begin-combat pump is a fully-typed
    ``AddPower``/``AddToughness`` mod site inside a ``GenericEffect`` (a
    static-role pump in the SAME unit, granularity a) — the engine fires."""
    assert ("combat_buff_engine", "you", "") in _idents("Aethershield Artificer")


def test_combat_buff_engine_keyword_only_grant_stays_out():
    """The nested-mod read is pump-gated: a combat-frame trigger conferring
    only KEYWORDS/other effects (Alela, Cunning Conqueror's opponent-turn
    spell trigger; no combat pump site) never fires."""
    assert "combat_buff_engine" not in _keys("Alela, Cunning Conqueror")


def test_topdeck_stack_tracked_set_dig():
    """Fix (c): Ancestral Knowledge's ``PutAtLibraryPosition position=Top``
    over a ``TrackedSet`` fed by a SAME-unit Controller ``Dig`` (the tracked
    set IS your dug top-of-library — CR 401.4) fires topdeck_stack."""
    assert ("topdeck_stack", "you", "") in _idents("Ancestral Knowledge")
    assert ("topdeck_selection", "you", "") in _idents("Ancestral Knowledge")


def test_topdeck_stack_tracked_set_needs_own_dig():
    """The TrackedSet arm is Dig-joined per unit: Griptide's bounce-to-top
    REMOVAL (no Controller Dig sibling) still never fires."""
    assert "topdeck_stack" not in _keys("Griptide")


@pytest.mark.parametrize(
    "name",
    [
        "Nael, Avizoa Aeronaut",  # Dig(Controller)-fed ParentTarget
        "Scroll Rack",  # exile-from-hand-fed ExiledBySource
        "Mirror of Fate",  # ChangeZoneAll(Library)-fed TrackedSet
        "Mortuary",  # dies-trigger's own ParentTarget (no Dig at all)
        "Munda, Ambush Leader",  # Dig-only, no put node — sweep mirror
        "Leashling",  # activation-cost put, no Dig/put node — sweep mirror
    ],
)
def test_topdeck_stack_back_reference_widening(name):
    """ADR-0038 W3 batch 4 (draw-etb-tokens cluster): the back-reference
    widening (ParentTarget/TrackedSet/ExiledBySource + self-anchor "on top
    of your library" confirmation) and the legacy kept-mirror
    (``TOPDECK_STACK_SWEEP_REGEX``, card-level) recover the corpus-verified
    live_only set (CR 401.4) with zero genuine members lost."""
    assert ("topdeck_stack", "you", "") in _idents(name)


def test_topdeck_stack_nested_grant_descent():
    """Scion of Halaster's Background grants Commander creatures a
    replacement draw ("look at the top two ... other back on top") whose
    ``PutAtLibraryPosition`` lives inside ``GrantAbility.definition.
    sub_ability`` — the SAME ``.definition`` descent precedent
    :func:`_self_pump`'s sibling scan establishes for a granted mod site
    (CR 401.4)."""
    assert ("topdeck_stack", "you", "") in _idents("Scion of Halaster")


def test_topdeck_stack_opponent_library_excluded():
    """Cruel Fate's "target opponent's library" Dig carries a
    ``player=Controller`` field (the DIGGER, never the library owner —
    phase has no library-owner field at all) feeding a structurally
    byte-identical TrackedSet to a self top-stack; the self-anchor text
    check ("on top of YOUR library") correctly excludes it since the
    clause names "that player's library" instead (CR 401.4)."""
    assert "topdeck_stack" not in _keys("Cruel Fate")


def test_topdeck_stack_replacement_origin_excluded():
    """Library of Leng's discard-to-top REPLACEMENT ("you may put it on
    top of your library instead") is excluded — legacy's project.py never
    walks ``card.replacements`` for this concept at all (verified: no
    topdeck_stack Effect in ``old_ir_for``), so admitting it here would be
    an un-adjudicated beyond-legacy claim."""
    assert "topdeck_stack" not in _keys("Library of Leng")


def test_topdeck_stack_selection_idiom_excluded():
    """Telling Time's "look at 3, one to hand / one on top / one on
    bottom" is a Dig-only selection idiom with no separate put node and no
    sweep-mirror match ("on top of your library" but not "... in any
    order") — topdeck_selection's territory, not topdeck_stack's."""
    assert "topdeck_stack" not in _keys("Telling Time")


def test_topdeck_stack_nested_rolldie_result_excluded():
    """Loathsome Troll's graveyard-recursion d20 result ("1-9 | Put this
    card on top of your library") lives inside a modal ``RollDie.results``
    branch — the nested-grant descent is scoped to
    ``GrantAbility``/``GrantTrigger``/``GrantStaticAbility`` only, never a
    blanket deep walk, so this stays out (legacy's project.py doesn't walk
    it either)."""
    assert "topdeck_stack" not in _keys("Loathsome Troll")


def test_target_player_draws_excludes_scoped_player_group_draw():
    """Fix (d): Academy Loremaster's "that player may draw" under an
    each-player draw-step trigger is a ``ScopedPlayer`` GROUP draw — the
    card_draw_engine each-arm, never a directed gift (the live routing to
    target_player_draws is the documented divergence)."""
    assert "target_player_draws" not in _keys("Academy Loremaster")
    assert ("card_draw_engine", "each", "") in _idents("Academy Loremaster")


# ── ADR-0038 W3 batch 6 (draw-etb-tokens cluster): target_player_draws ──────
# widening (158 both / 95 live_only, down from 145 — NOT YET PROMOTED, see
# ``_target_player_draws``'s docstring for the phrase-gate rationale).


def test_target_player_draws_widened_recipient_tags():
    """:data:`_TARGETED_DRAW_WIDENED_TAGS` — Lord of Tresserhorn's
    ``Typed(Opponent)`` ("target opponent draws two cards"), Call to
    Heel's ``ParentTargetController`` ("Its controller draws a card" off
    a bounced creature), Curse of Chaos's ``TriggeringPlayer`` (the
    attacking player draws), each verified same-clause via
    :data:`_TARGET_PLAYER_DRAW_PHRASE_RE`. CR 121.1."""
    assert ("target_player_draws", "any", "") in _idents("Lord of Tresserhorn")
    assert ("target_player_draws", "any", "") in _idents("Call to Heel")
    assert ("target_player_draws", "any", "") in _idents("Curse of Chaos")


def test_target_player_draws_excludes_trailing_unattributed_draw_bleed():
    """The phrase gate excludes a phase templating quirk: "Destroy target
    land. Its controller may search their library ... Draw a card." tags
    the trailing, textually-unattributed "Draw a card." sentence
    ``ParentTargetController`` even though that sentence never names a
    controller (CR 608.2h — an unattributed effect defaults to the
    caster, not the earlier clause's target). Price of Freedom / Cleansing
    Wildfire's own draw clause has no player-reference wording, so the
    same-clause phrase check correctly excludes it."""
    assert "target_player_draws" not in _keys("Price of Freedom")
    assert "target_player_draws" not in _keys("Cleansing Wildfire")


# ── ADR-0038 W5 tails: target_player_draws (95 → 75 live_only; NOT YET ──────
# PROMOTED — a Saga-chapter / modal-choice / vote / granted-ability-text
# residual class stays structurally unreachable, see the key's docstring
# for the full accounting). CR 121.1 throughout.


def test_target_player_draws_paired_scoped_player_idiom():
    """A ``ScopedPlayer`` recipient IS admitted when the SAME unit also owns
    an ``OriginalController``-tagged Draw — the "you and target
    opponent/that player each draw" idiom (phase splits it into TWO
    sibling Draw nodes, one per side). An UNPAIRED ``ScopedPlayer`` (no
    ``OriginalController`` sibling — Academy Loremaster's lone
    each-player-draw-step node, pinned above) stays group_hug_draw
    territory."""
    for name in (
        "Intellectual Offering",
        "Tenuous Truce",
        "Diviner Spirit",
        "Xyris, the Writhing Storm",
        "Black Widow, Intel Expert",
        "Sergeant John Benton",
    ):
        assert ("target_player_draws", "any", "") in _idents(name), name


def test_target_player_draws_any_recipient_tag():
    """``Any`` is admitted unconditionally (:data:`_TARGETED_DRAW_TAGS`) — the
    "you and X each draw" idiom's COLLAPSED single-node form phase uses
    instead of the paired ``OriginalController``/``ScopedPlayer`` shape
    above. Corpus-verified as the ONLY tag used for a ``Draw`` recipient
    across the whole commander-legal corpus (6 hits, all this idiom)."""
    for name in (
        "Karazikar, the Eye Tyrant",
        "Zurzoth, Chaos Rider",
        "Nelly Borca, Impulsive Accuser",
        "Cait, Cage Brawler",
        "Splinter, Aging Champion",
    ):
        assert ("target_player_draws", "any", "") in _idents(name), name


def test_target_player_draws_recovered_directed_residue():
    """A RECOVERED "draw" residue (recovery.py's ALLOWLIST token row) is
    admitted when its own truncated raw clause carries a direction word
    adjacent to "draws" with no "if"/"unless" boundary crossed — Forget's
    "draws as many cards as they discarded this way", Soldevi Sentry's
    "that player may draw a card"."""
    assert ("target_player_draws", "any", "") in _idents("Forget")
    assert ("target_player_draws", "any", "") in _idents("Soldevi Sentry")


def test_target_player_draws_recovered_residue_excludes_conditional_backref():
    """Faramir, Prince of Ithilien's "you draw a card if they didn't attack
    you that turn" names "they" as the subject of a CONDITION clause, not
    the drawer (the drawer is plainly "you", stated earlier in the SAME
    clause) — the "if"/"unless" boundary guard keeps it out."""
    assert "target_player_draws" not in _keys("Faramir, Prince of Ithilien")


def test_target_player_draws_recovered_residue_excludes_each_player_owner_scope():
    """A recovered "draw" residue whose owning unit carries
    ``player_scope: All`` (Grothama, All-Devouring's damage-scaled
    leaves-trigger) is the group_hug_draw synthesis arm's OWN territory,
    never a directed gift — the ``effect_owner_player_scope(...) == "All"``
    guard keeps it out regardless of stray direction pronouns in the raw
    ("sources they controlled" is a backref to the damage-dealers, not the
    drawer)."""
    assert "target_player_draws" not in _keys("Grothama, All-Devouring")
    assert ("group_hug_draw", "each", "") in _idents("Grothama, All-Devouring")


def test_target_player_draws_possessive_controller_phrase():
    """A ``\\w+'s (?:controller|owner)`` phrase alternative admits the
    OBJECT-possessive spelling of the same-clause attribution — "That
    creature's controller draws X cards" (Nin, the Pain Artist; Nessian
    Boar), "That spell's controller may draw a card" (Vex)."""
    assert ("target_player_draws", "any", "") in _idents("Nin, the Pain Artist")
    assert ("target_player_draws", "any", "") in _idents("Nessian Boar")
    assert ("target_player_draws", "any", "") in _idents("Vex")


def test_target_player_draws_bare_opponent_and_participle_player_phrases():
    """A bare ``(?:an|each) opponent`` alternative (no "target" prefix)
    admits Baleful Mastery's "an opponent draws a card" (a
    ``ChosenPlayer``-controller ``Typed`` node). A
    ``(?:that|the) (?:\\w+ )?player`` alternative admits a
    PARTICIPLE-modified back-reference — Breena, the Demagogue's "that
    attacking player draws a card", Norn's Decree's "the attacking player
    draws a card" (``TriggeringSourceController``)."""
    assert ("target_player_draws", "any", "") in _idents("Baleful Mastery")
    assert ("target_player_draws", "any", "") in _idents("Breena, the Demagogue")
    assert ("target_player_draws", "any", "") in _idents("Norn's Decree")


def test_target_player_draws_choose_player_phrase():
    """A standalone ``choose ... player ... draws`` alternative admits a
    SEQUENTIAL-choice recipient — Gluntch, the Bestower's "Choose a second
    player to draw a card." (a ``ChosenPlayer``-controller ``Typed`` node,
    the same structural shape as Baleful Mastery's opponent filter, just
    phrased as an explicit choice)."""
    assert ("target_player_draws", "any", "") in _idents("Gluntch, the Bestower")


def test_target_player_draws_parent_target_owner_tag():
    """``ParentTargetOwner`` (the OWNER, not controller, of a previously
    targeted object) joins :data:`_TARGETED_DRAW_WIDENED_TAGS` — Oft-Nabbed
    Goat's "its owner draws that many cards" (CR 121.1/608.2h, the
    object-chain analog of ``ParentTargetController``)."""
    assert ("target_player_draws", "any", "") in _idents("Oft-Nabbed Goat")


# ── ADR-0038 W6 endgame: target_player_draws (75 → 70 live_only; STILL NOT ──
# PROMOTED — 6 genuine "dropped clause" gaps remain, see the key's docstring
# for the full accounting). CR 121.1 / 701.38 throughout.


def test_target_player_draws_paired_widened_tag_idiom_no_text():
    """The paired admission bypasses the phrase gate entirely when the SAME
    unit owns a self-tagged Draw — Fall of the First Civilization and Love
    Song of Night and Day's Saga chapter I ("You and target opponent each
    draw two cards.") and Your Temple Is Under Attack's "Strike a Deal"
    mode all carry a synthetic/absent ``unit.node.description`` ("Chapter
    1", or nothing at all) the phrase gate can never match — the pairing
    itself proves directedness independent of any text."""
    for name in (
        "Fall of the First Civilization",
        "Love Song of Night and Day",
        "Your Temple Is Under Attack",
    ):
        assert ("target_player_draws", "any", "") in _idents(name), name


def test_target_player_draws_paired_controller_tag_idiom():
    """The self half of the pairing now also accepts the ordinary
    ``Controller`` tag, not just ``OriginalController`` — The Legend of
    Yangchen's "You may have target opponent draw three cards. If you do,
    draw three cards." pairs ``Typed``/``Controller`` (a Saga chapter II
    with the same synthetic-description gap as the cases above)."""
    assert ("target_player_draws", "any", "") in _idents("The Legend of Yangchen")


def test_target_player_draws_vote_per_choice_paired_descent():
    """A ``Vote`` ``per_choice_effect`` branch (CR 701.38) carrying BOTH a
    self-tagged Draw and a ``ScopedPlayer`` Draw is the SAME paired idiom
    nested one level deeper behind a vote outcome — Master of Ceremonies's
    "For each player who chose secrets, you and that player each draw a
    card." lives on a branch ``effect_concepts`` never reaches at all."""
    assert ("target_player_draws", "any", "") in _idents("Master of Ceremonies")


def test_target_player_draws_excludes_each_opponent_scoped_player_group():
    """An ``each opponent's draw step`` ``ScopedPlayer`` trigger (Malignant
    Growth) is the SAME unpaired-group territory as the ``each player``
    case (Academy Loremaster, pinned above) — no ``OriginalController``/
    ``Controller`` sibling, so it stays group_hug_draw territory, not a
    directed gift. Rites of Flourishing is the SAME each-player-draw-step
    idiom for completeness."""
    assert "target_player_draws" not in _keys("Malignant Growth")
    assert "target_player_draws" not in _keys("Rites of Flourishing")


def test_target_player_draws_excludes_replacement_symmetric_draw_cap():
    """Alms Collector's "instead you and that player each draw a card" is a
    REPLACEMENT rewrite (CR 614), not a forced gift — replacement units are
    skipped regardless of the paired wording inside them (same discipline
    as :func:`test_target_player_draws_excludes_replacement_tax`)."""
    assert "target_player_draws" not in _keys("Alms Collector")


def test_target_player_draws_excludes_may_have_you_draw_idiom():
    """ "Target opponent may have you draw a card" (Bane, Lord of Darkness;
    Combustible Gearhulk) names the OPPONENT as the CHOOSER, not the
    recipient — the drawer is still "you" (CR 121.1's recipient reads the
    ``Draw`` node's own target, not the ``may``-grant's chooser), so this
    stays a self-cantrip, never a directed gift."""
    assert "target_player_draws" not in _keys("Bane, Lord of Darkness")
    assert "target_player_draws" not in _keys("Combustible Gearhulk")


def test_target_player_draws_excludes_bled_leadership_vacuum():
    """Leadership Vacuum's trailing, textually-unattributed "Draw a card."
    sentence defaults to the caster (CR 608.2h) — the SAME bleed exclusion
    as :func:`test_target_player_draws_excludes_trailing_unattributed_draw_
    bleed`, just off a "Target player returns each commander..." lead-in
    instead of a "controller may" one."""
    assert "target_player_draws" not in _keys("Leadership Vacuum")


def test_target_player_draws_excludes_recovered_each_and_self_branches():
    """Mathise, Surge Channeler's d20 table recovers TWO "draw" residues —
    "Each player draws a card." (group, no directed-recipient word) and
    "You draw a card." (self, no directed-recipient word) — neither
    matches :data:`_RECOVERED_DRAW_DIRECTED_RE`'s word list, so both
    correctly stay out."""
    assert "target_player_draws" not in _keys("Mathise, Surge Channeler")


def test_target_player_draws_excludes_unreached_modal_no_text():
    """Fatal Lore, Season of the Burrow, Ertai Resurrected, and Balor each
    carry a modal ``ParentTargetController``/``Typed`` Draw with NO
    self-tagged sibling to pair against AND no reachable clause text
    anywhere in the typed tree (``unit.node.description`` is ``None`` or a
    synthetic trigger-condition label like "Whenever ~ attacks") — a
    genuine "dropped clause" gap, not fixable without a
    ``clause_grammar.py`` change (grammar-blocked this wave, ADR-0039)."""
    for name in ("Fatal Lore", "Season of the Burrow", "Ertai Resurrected", "Balor"):
        assert "target_player_draws" not in _keys(name), name


def test_target_player_draws_excludes_unreachable_granted_ability_text():
    """Thief of Existence's granted "target opponent draws a card" text
    lives ONLY inside a quoted string on an unrelated effect's
    ``description`` field — no typed ``Draw`` node exists anywhere in the
    tree for any arm to reach."""
    assert "target_player_draws" not in _keys("Thief of Existence")


def test_target_player_draws_excludes_does_the_same_ellipsis():
    """The Wedding of River Song's "Then target opponent does the same" is
    an ellipsis repeat-for-another-player phase never structures into a
    second typed ``Draw`` node — only the original "you draw two cards"
    survives structurally."""
    assert "target_player_draws" not in _keys("The Wedding of River Song")


def test_target_player_draws_excludes_vote_council_self_payoff():
    """Vault 11: Voter's Dilemma's "if no creature got votes, each player
    draws a card" is a GROUP outcome (``All`` player_scope), not a Vote
    ``per_choice_effect`` branch at all — stays out via the SAME
    absent-text path as the modal cases above (no reachable clause text,
    no self-tagged pairing sibling)."""
    assert "target_player_draws" not in _keys("Vault 11: Voter's Dilemma")


# ── Batch 11: replacement-doubler cluster (§A) ────────────────────────────────


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Doubling Season", True),  # CreateToken replacement, Times 2, You
        ("Parallel Lives", True),
        ("Primal Vigor", True),  # symmetric no-owner-scope — beneficiary is you
        ("Hardened Scales", False),  # AddCounter event — the counter lane
        ("Vizier of Remedies", False),  # Minus reducer
    ],
)
def test_token_doubling_replacement_read(name, should_fire):
    """CR 614.1a + 111.1: a CreateToken replacement with an INCREASE
    quantity_modification is the token doubler; an AddCounter event or a
    reducer never fires. Case law (Doubling Season): two Seasons = four
    times the tokens."""
    assert (("token_doubling", "you", "") in _idents(name)) is should_fire


def test_token_doubling_co_fires_copy_and_matters():
    """Live ADR-0027 C5 co-fire reproduced: a token doubler forks token-copy
    spells and is a go-wide payoff — token_copy_makers + tokens_matter open
    alongside."""
    idents = _idents("Parallel Lives")
    assert ("token_copy_makers", "you", "") in idents
    assert ("tokens_matter", "you", "") in idents


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Doubling Season", True),  # AddCounter Times 2, Permanent/You
        ("Hardened Scales", True),  # Plus 1 — live counter_doubling co-fires
        ("Vorel of the Hull Clade", True),  # arm b: Double {Counters} effect
        ("Kalonian Hydra", True),  # arm c: triggered MultiplyCounter x2
        ("Vizier of Remedies", False),  # Minus — a REDUCER (M1M1 minus one)
        ("Parallel Lives", False),  # CreateToken event — the token lane
    ],
)
def test_counter_doubling_arms(name, should_fire):
    """CR 614.1a + 122.1: the AddCounter increase replacement (live's
    counter_doubling category is Times AND Plus — measured live parity:
    Hardened Scales carries both keys), the one-shot Double{Counters}
    (Vorel — the live byte-mirror's "phase mangles Vorel" complaint was
    STALE), and the triggered MultiplyCounter (Kalonian Hydra). Case law
    (Vorel): "essentially double the counters on the target"."""
    assert (("counter_doubling", "you", "") in _idents(name)) is should_fire


def test_counter_replace_bonus_increase_gate():
    """CR 614.1a: the increase gate IS the gate — Hardened Scales (Plus 1,
    valid_card Creature/You) and the Doubling Season co-fire arm fire;
    Vizier of Remedies' Minus never does. Case law (Hardened Scales): "that
    many plus one instead"."""
    assert ("counter_replace_bonus", "you", "") in _idents("Hardened Scales")
    assert ("counter_replace_bonus", "you", "") in _idents("Doubling Season")
    assert "counter_replace_bonus" not in _keys("Vizier of Remedies")


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Furnace of Rath", True),  # bare Double — every damage doubled
        ("Gisela, Blade of Goldnight", True),  # opponent-directed Double
        ("Gratuitous Violence", True),  # your-creatures source filter
        ("Blind Fury", True),  # creature-only Double still amplifies
        ("Palisade Giant", False),  # NO damage_modification — a shield
        ("Vizier of Remedies", False),  # not a DamageDone event
    ],
)
def test_damage_doubling_replacement_read(name, should_fire):
    """CR 614.1a + 120.3: a DamageDone replacement carrying an AMPLIFY
    damage_modification (Double/Triple/Plus — live's category includes the
    Torbran +N amplifiers, measured); the prevention/redirect shields carry
    no damage_modification and never fire."""
    assert (("damage_doubling", "you", "") in _idents(name)) is should_fire


def test_damage_doubling_direct_damage_co_fire_is_player_gated():
    """Live ADR-0027 C7 reproduced: a player-reaching doubler (Furnace —
    filterless; Gisela — opponent-side filter) co-fires direct_damage; the
    creature-only doubler (Blind Fury — ``damage_target_filter:
    "CreatureOnly"``) does not (measured live parity)."""
    assert ("direct_damage", "you", "") in _idents("Furnace of Rath")
    assert ("direct_damage", "you", "") in _idents("Gisela, Blade of Goldnight")
    assert "direct_damage" not in _keys("Blind Fury")


# ── Batch 11: damage-trigger cluster (§B) ─────────────────────────────────────


def test_damage_reflect_co_occurrence():
    """CR 603.2 + 120.3: Boros Reckoner's DamageReceived trigger + same-unit
    DealDamage fires; Phytohydra (a DealtDamage REPLACEMENT with a
    PutCounter execute — different node family) and Michiko (a DamageDone
    watcher) never do. Case law (Boros Reckoner): the reflected damage
    "isn't combat damage"."""
    assert ("damage_reflect", "you", "") in _idents("Boros Reckoner")
    assert "damage_reflect" not in _keys("Phytohydra")
    assert "damage_reflect" not in _keys("Michiko Konda, Truth Seeker")


def test_damage_reflect_delayed_trigger_recovery():
    """Stage-A recovery (ADR-0038): Arcbond's "Choose target creature.
    Whenever that creature is dealt damage this turn, it deals that much
    damage to each other creature and each player." creates a delayed
    trigger via ``CreateDelayedTrigger`` — the watcher (``DamageReceived``
    mode) lives on ``condition.trigger``, the resulting ``DamageAll``
    effect on a SIBLING ``effect`` field, never co-located the way a
    top-level trigger unit is. Read via the deep-walk fallback (CR 120.3)."""
    assert ("damage_reflect", "you", "") in _idents("Arcbond")


def test_damage_reflect_compound_subject_recovery():
    """Stage-A recovery (ADR-0038): Donna Noble's "Whenever ~ or a creature
    it's paired with is dealt damage, ~ deals that much damage to target
    opponent." carries a compound subject ("~ OR a creature it's paired
    with") that defeats phase's own trigger-mode derivation — the trigger's
    ``mode`` decorates as an ``Unknown`` variant wrapping the raw "is dealt
    damage" phrase rather than the native ``DamageReceived`` tag. Read
    directly off ``mode``/``execute``, bypassing the lossy
    ``_trigger_event`` normalization (CR 120.3)."""
    assert ("damage_reflect", "you", "") in _idents("Donna Noble")


def test_damage_reflect_granted_trigger_recovery():
    """Stage-A recovery (ADR-0038): Spiteful Sliver's "Sliver creatures you
    control have 'Whenever ~ is dealt damage, it deals that much damage to
    target player or planeswalker.'" lands as a ``GrantTrigger``
    modification on a static — the SAME ``mode``/``execute``-co-located
    shape a top-level trigger uses, just nested one level inside the
    grant (CR 120.3)."""
    assert ("damage_reflect", "you", "") in _idents("Spiteful Sliver")


def test_damage_to_you_punish_direction_gates():
    """CR 603.2 + 102.2/102.3: Michiko's DamageDone + valid_target
    {Controller} + Opponent-controlled valid_source fires (the live "no
    structural shape" comment was STALE); Boros Reckoner (DamageReceived)
    and Hypnotic Specter (target Opponent — the wrong direction) never do.
    Case law (Michiko): "One permanent is sacrificed each time an
    opponent's source deals damage"."""
    assert (
        "damage_to_you_punish",
        "opponents",
        "",
    ) in _idents("Michiko Konda, Truth Seeker")
    assert "damage_to_you_punish" not in _keys("Boros Reckoner")
    assert "damage_to_you_punish" not in _keys("Hypnotic Specter")


def test_combat_damage_to_creature_recipient_gate():
    """CR 510.1c: Serpentine Basilisk's CombatOnly Creature-recipient fires
    scope "any"; Seshiro's Player recipient routes to the player-connect
    lanes instead."""
    assert ("combat_damage_to_creature", "any", "") in _idents("Serpentine Basilisk")
    assert "combat_damage_to_creature" not in _keys("Seshiro the Anointed")


def test_tribe_damage_trigger_population_gate():
    """CR 510.1b: a YOUR-controlled creature POPULATION source (Seshiro's
    Snakes — subtype; Coastal Piracy's Creature core) reaching a player
    fires; a SelfRef single doer (Hypnotic Specter) and an
    opponent-controlled source (Michiko) never do (checklist #6 — the You
    gate on valid_source IS the lane)."""
    assert ("tribe_damage_trigger", "you", "") in _idents("Seshiro the Anointed")
    assert ("tribe_damage_trigger", "you", "") in _idents("Coastal Piracy")
    assert "tribe_damage_trigger" not in _keys("Hypnotic Specter")
    assert "tribe_damage_trigger" not in _keys("Michiko Konda, Truth Seeker")
    assert "tribe_damage_trigger" not in _keys("Serpentine Basilisk")


# ADR-0038 W3 batch 2 unit 6 — the tribe_damage_trigger nested granted-
# trigger / delayed-trigger-condition arm (damage_to_player_trigger_kind +
# _is_tribe_damage_source, the SAME two-tree-position walk damage_to_opp_
# matters uses): a Background's GrantTrigger (Feywild Visitor), a
# planeswalker loyalty ability's CreateDelayedTrigger.condition (Dovin,
# Jace Cunning Castaway, Kaito Shizuki, Vraska Golgari Queen), a Saga
# chapter (The Girl in the Fireplace), and an activated-ability delayed
# trigger (Killian's Confidence, Surge to Victory, Thunderblade Charge,
# Flitterwing Nuisance, Subira's second ability).
@pytest.mark.parametrize(
    "name",
    [
        "Feywild Visitor",
        "Popular Entertainer",
        "Dovin, Grand Arbiter",
        "Jace, Cunning Castaway",
        "Kaito Shizuki",
        "Vraska, Golgari Queen",
        "The Girl in the Fireplace",
        "Killian's Confidence",
        "Surge to Victory",
        "Thunderblade Charge",
        "Flitterwing Nuisance",
        "Subira, Tulzidi Caravanner",
    ],
)
def test_tribe_damage_trigger_nested_grant_and_delayed_arm(name):
    assert ("tribe_damage_trigger", "you", "") in _idents(name)


# ADR-0038 W3 batch 2 unit 6 — the _is_tribe_damage_source ANY-subtype
# widening (CR 510.1a: only a creature can deal combat damage, so a
# source filter naming a non-creature-core subtype like Vehicle is STILL
# a creature at the moment it connects — the population is animated/
# crewed). Edward Kenway / Setzer / The Thanos-Copter / The Omenkeel all
# watch "a Vehicle you control deals combat damage"; Adéwalé / Aphelia /
# Mistway Spy / Zurgo and Ojutai watch a tribal subtype (Assassin/Pirate/
# Gorgon/Dragon); Cosima's back face (The Omenkeel) is the DFC case.
@pytest.mark.parametrize(
    "name",
    [
        "Edward Kenway",
        "Setzer, Wandering Gambler",
        "The Thanos-Copter",
        "The Omenkeel",
        "Adéwalé, Breaker of Chains",
        "Aphelia, Viper Whisperer",
        "Mistway Spy",
        "Zurgo and Ojutai",
    ],
)
def test_tribe_damage_trigger_any_subtype_source_arm(name):
    assert ("tribe_damage_trigger", "you", "") in _idents(name)


def test_tribe_damage_trigger_or_recipient_arm():
    """The damage_recipient_is_player Or-recursion (CR 510.1c): "deals
    combat damage to a player or planeswalker/battle" reaches a player in
    the Player branch of the Or filter even though the OTHER branch is
    object-typed (Zagras / Hooded Blightfang / Vraska Swarm's Eminence /
    The Raven's Warning — beyond-legacy gains, legacy fires nothing
    tribe_damage_trigger-related for these; a genuine recall gain, not an
    over-fire)."""
    assert ("tribe_damage_trigger", "you", "") in _idents("Zagras, Thief of Heartbeats")
    assert ("tribe_damage_trigger", "you", "") in _idents("Hooded Blightfang")
    assert ("tribe_damage_trigger", "you", "") in _idents("Vraska, Swarm's Eminence")
    assert ("tribe_damage_trigger", "you", "") in _idents("The Raven's Warning")


def test_batched_combat_damage_mode_joins_the_event_read():
    """b10 follow-up (d): the ``DamageDoneOnceByController`` batched mode
    ("whenever one or more Rogues you control deal combat damage to a
    player" — Anowon) joins the shared deals_damage read — the combat
    connect, the ported to_opp lane, and the tribal population lane all
    fire (measured live parity)."""
    idents = _idents("Anowon, the Ruin Thief")
    assert ("combat_damage_matters", "opponents", "") in idents
    assert ("combat_damage_to_opp", "opponents", "") in idents
    assert ("tribe_damage_trigger", "you", "") in idents


def test_combat_damage_to_opp_excludes_planeswalker_only_recipient():
    """CR 102.1: a planeswalker is not a player. Zagras, Thief of Heartbeats's
    "Whenever a creature you control deals combat damage to a PLANESWALKER,
    destroy that planeswalker" satisfies ``combat_damage_matters`` (CR
    510.1b's player-OR-planeswalker read) but not this PLAYER-specific lane
    (CR 510.1c)."""
    idents = _idents("Zagras, Thief of Heartbeats")
    assert ("combat_damage_matters", "opponents", "") in idents
    assert "combat_damage_to_opp" not in {k for k, _s, _su in idents}


@pytest.mark.parametrize("name", ["Fire Giant's Fury", "Kang Dynasty"])
def test_combat_damage_unknown_mode_description_fallback(name):
    """ADR-0038 W3 batch 4: a GRANTED/DELAYED combat-damage trigger def whose
    ``mode`` phase leaves ``MirrorVariant(key="Unknown")`` entirely (Fire
    Giant's Fury's pump-attached delayed trigger "Whenever it deals combat
    damage to a player this turn, exile ..."; Kang Dynasty's Saga-granted
    watcher "whenever any of those creatures deals combat damage to a
    player, draw a card") — verified via direct node inspection
    (mode.key=="Unknown", damage_kind left the generic "Any"), so
    ``damage_to_player_trigger_kind`` bails on the event-tag check before it
    ever reaches the recipient. The node's OWN ``description`` field still
    carries the clause; :func:`_unknown_mode_combat_damage_to_player` reads
    it structurally (per-node, never a whole-card scan; CR 510.1b/c)."""
    idents = _idents(name)
    assert ("combat_damage_matters", "opponents", "") in idents
    assert ("combat_damage_to_opp", "opponents", "") in idents


@pytest.mark.parametrize(
    "name",
    [
        "Predators' Hour",  # AddKeyword-modification quote (menace + "Whenever
        # ~ deals combat damage to a player, exile ..." baked into the
        # description, no GrantTrigger node at all)
        "Sokrates, Athenian Teacher",  # activated-ability-granted
        # AddTargetReplacement quote ("if ~ would deal combat damage to a
        # player, prevent that damage. ...")
        "Steel Hellkite",  # passive "was dealt combat damage by ~ this
        # turn" reference inside an unrelated {X} activated ability's
        # target filter -- no trigger/replacement node names it at all
        "Trendy Circus Pirate",  # Unfinity Sticker Sheet TK-template: the
        # {TK} mana cost defeats phase's cost parser entirely, collapsing
        # the WHOLE triggered line to one opaque Unimplemented residue
    ],
)
def test_combat_damage_bare_quoted_grant_text_fallback(name):
    """ADR-0038 W3 batch 6: no typed trigger def (top-level/nested/delayed)
    reaches any of these -- :func:`~mtg_utils._card_ir.supplement.
    combat_damage_recipients_from_text` (reused verbatim, single-source from
    the OLD projection's own synthetic ``combat_damage`` trigger recovery)
    reads the FACE's own oracle as a last resort. CR 510.1b/510.1c/510.2."""
    idents = _idents(name)
    assert ("combat_damage_matters", "opponents", "") in idents
    assert ("combat_damage_to_opp", "opponents", "") in idents


@pytest.mark.parametrize("name", ["Kassandra, Eagle Bearer", "Spawning Kraken"])
def test_combat_damage_matters_top_level_unknown_mode_text_fallback(name):
    """ADR-0038 W3 batch 6: a TOP-LEVEL trigger unit whose ``mode`` phase
    leaves ``Unknown`` (Kassandra's Equipment-gated "Whenever a creature you
    control with a legendary Equipment attached to it deals combat damage to
    a player, draw a card"; Spawning Kraken's tribal "Whenever a Kraken,
    Leviathan, Octopus, or Serpent you control deals combat damage to a
    player, create ..." whose ``Unimplemented`` execute chain defeats the
    typed kind read) already fired ``combat_damage_to_opp`` via
    :func:`_unknown_mode_combat_damage_to_player` (that fallback was already
    wired into :func:`_combat_damage_to_opp_fires` for ANY node, including a
    bare top-level unit) but NOT ``combat_damage_matters`` -- the sibling
    lane's top-level ``emit(damage_to_player_trigger_kind(unit.node))`` call
    never tried the Unknown-mode fallback at all. Recovered via the SAME
    text-recovery fallback as the bare-quoted-grant class above (CR
    510.1b/510.1c)."""
    idents = _idents(name)
    assert ("combat_damage_matters", "opponents", "") in idents
    assert ("combat_damage_to_opp", "opponents", "") in idents


def test_combat_damage_matters_dfc_face_oracle_not_bulk_top_level():
    """ADR-0038 W3 batch 6: Optimus Prime's front-face DFC record carries no
    top-level ``oracle_text`` (blank/None at the bulk level) -- the delayed
    "When that creature deals combat damage to a player this turn, convert
    ~" clause is buried as a ``SequentialSibling`` Unimplemented sub-ability
    of the "Autobot Leader" back face's OWN attack trigger, readable only
    off THAT face's own ``tree.oracle`` (never the blank bulk field). CR
    510.1b/510.1c."""
    idents = _idents("Optimus Prime, Autobot Leader")
    assert ("combat_damage_matters", "opponents", "") in idents
    assert ("combat_damage_to_opp", "opponents", "") in idents


@pytest.mark.parametrize("name", ["Raphael, the Nightwatcher", "Blade Historian"])
def test_combat_damage_to_opp_double_strike_grant_low_confidence(name):
    """ADR-0038 W3 batch 6: a LOW-confidence heuristic -- "Attacking
    creatures you control have double strike" makes attackers connect with
    a player TWICE, a combat-damage-to-player payoff whose oracle never
    says "combat damage" at all (:data:`COMBAT_DAMAGE_TO_OPP_DS_GRANT_
    REGEX`, reused verbatim from the deleted legacy producer -- Raphael,
    Blade Historian, Berserkers' Onslaught, a disjoint corpus-bounded
    3-card class). ``combat_damage_matters`` does NOT fire for this class
    (legacy's own producer only ever adds ``combat_damage_to_opp``). CR
    510.1c."""
    idents = _idents(name)
    assert ("combat_damage_to_opp", "opponents", "") in idents
    assert "combat_damage_matters" not in {k for k, _s, _su in idents}


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Pestilence", True),  # DamageAll + player_filter All
        ("Earthquake", True),  # the X-form the deleted regex missed
        ("Witty Roastmaster", False),  # each-OPPONENT — one-sided (259 corpus)
        ("Pyroclasm", False),  # creatures-only sweep, no player reach
    ],
)
def test_symmetric_damage_each_player_filter_gate(name, should_fire):
    """CR 102.2/102.3: the each-PLAYER vs each-OPPONENT split is the whole
    gate, read off the effect's OWN player_filter node (checklist #5)."""
    assert (("symmetric_damage_each", "each", "") in _idents(name)) is should_fire


def test_aoe_ping_repeatable_gate():
    """CR 120.3: Pestilence's activated ``{B}`` DamageAll-creatures is a
    repeatable pinger; the one-shot Spell sweeps (Pyroclasm — mass_removal
    country; Earthquake — §9 only) never fire."""
    assert ("aoe_ping", "you", "") in _idents("Pestilence")
    assert "aoe_ping" not in _keys("Pyroclasm")
    assert "aoe_ping" not in _keys("Earthquake")


def test_creature_ping_power_scaled_gate():
    """CR 120.3: Ram Through's POWER-scaled Ref amount into a Creature-cored
    target fires; a fixed-amount pinger (Prodigal Sorcerer) never does."""
    assert ("creature_ping", "you", "") in _idents("Ram Through")
    assert "creature_ping" not in _keys("Prodigal Sorcerer")


@pytest.mark.parametrize("name", ["Abyssal Hunter", "Wave of Reckoning"])
def test_creature_ping_doer_widening_non_creature_recipient(name):
    """ADR-0038 W3 batch 4: creature_ping's real discriminator is the DOER,
    not the recipient — "a creature deals damage equal to ITS OWN power"
    fires regardless of who it reaches. Abyssal Hunter's recipient is a
    ``ParentTarget`` back-reference ("Tap target creature. This creature
    deals damage equal to its power to that creature"); Wave of Reckoning's
    is a self-fight ("Each creature deals damage to itself equal to its
    power" — CR 120.3). Neither is a structurally Creature-typed ``target``,
    so both need the widened raw-text confirmation
    (:data:`_POWER_SELF_RECIP` / :data:`_POWER_ITS_OWN_DOER`)."""
    assert ("creature_ping", "you", "") in _idents(name)


def test_creature_ping_adjudicated_gain_delirium():
    """ADJUDICATED GAIN over legacy: Delirium ("Tap target creature that
    player controls. That creature deals damage equal to its power to the
    player.") is a genuine CR 120.3 doer-based creature_ping member — a
    creature dealing damage equal to ITS OWN power, the exact shape legacy
    itself counts on Garruk Relentless / Alpha Brawl / Wisecrack (a doer
    creature reflexively burning a DIFFERENT recipient still counts).
    Legacy misses it only because its own empty-raw oracle fallback
    (``_CREATURE_PING_ORACLE``) is narrower than its raw-meaningful branch,
    and Delirium's per-effect raw happens to be empty in the OLD
    projection — a legacy fallback-regex gap, not a principled exclusion."""
    assert ("creature_ping", "you", "") in _idents("Delirium")


@pytest.mark.parametrize("name", ["Waltz of Rage", "Heartfire Hero"])
def test_creature_ping_damage_all_each_player_tag_widening(name):
    """ADR-0038 W3 batch 6: the anchor read only ``DealDamage``-tagged
    nodes; a "target creature you control deals damage equal to its power
    to each other creature" idiom (Waltz of Rage) types as ``DamageAll``
    (``damage_source='Target'`` -- the SOURCE dealing the damage is
    explicitly the earlier ``TargetOnly`` target), and a "when ~ dies, it
    deals damage equal to its power to each opponent" idiom (Heartfire
    Hero) types as ``DamageEachPlayer``. Both already decorate as the
    ``deal_damage`` CONCEPT (the crosswalk's tag->concept table maps all
    three DealDamage/DamageAll/DamageEachPlayer tags to it) but the lane's
    OWN per-node tag filter excluded anything but ``DealDamage``. CR 120.3.
    """
    assert ("creature_ping", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Burning Anger", "Brawl"])
def test_creature_ping_nested_grant_deep_walk(name):
    """ADR-0038 W3 batch 6: a DealDamage/DamageAll node buried inside a
    GRANTED ability's OWN definition (an Aura's "Enchanted creature has
    '{T}: This creature deals damage equal to its power to any target.'" —
    Burning Anger; a static's "all creatures gain '{T}: This creature deals
    damage equal to its power to target creature.'" — Brawl) is reachable
    ONLY via a deep :func:`~mtg_utils._card_ir.crosswalk.iter_typed_nodes`
    walk — no unit's own ``effects`` tuple carries it (the granting
    static's own effect chain IS the grant modification, not the granted
    ability's inner effects). No per-node ``raw`` exists at this depth, so
    the doer-confirm reads the reminder-stripped whole-face oracle
    directly. CR 120.3."""
    assert ("creature_ping", "you", "") in _idents(name)


def test_creature_ping_parent_target_recipient_text_confirm():
    """ADR-0038 W3 batch 6: Lie in Wait ("Return target creature card from
    your graveyard to your hand. ~ deals damage equal to THAT CARD's power
    to target creature.") sources its power from a DIFFERENT object (the
    returned card, ``qty.scope=Demonstrative``) — the doer-confirm text
    patterns (:data:`_POWER_ITS_OWN_DOER` "its power", :data:`_POWER_SELF_
    RECIP` "to itself") never match "that card's power". The recipient IS
    structurally Creature-typed per CR 120.3, but phase's ``target`` field
    is a bare ``ParentTarget`` back-reference with no Filter to read —
    legacy's OWN structural read fires creature_ping off a Creature
    recipient ALONE, so :data:`_POWER_RECIP_CREATURE_TEXT`'s strict
    "power to target creature" anchor recovers it as a recipient-side text
    confirm (never a bare "to <n> creature" scan — see the constant's own
    over-fire-reverted docstring). CR 120.3."""
    assert ("creature_ping", "you", "") in _idents("Lie in Wait")


@pytest.mark.parametrize("name", ["Cut Propulsion", "Betrayal at the Vault"])
def test_creature_ping_multiply_and_empty_type_filters(name):
    """ADR-0038 W3 batch 6: Cut Propulsion's conditional "it deals TWICE
    THAT MUCH damage to itself instead" (flying branch) doubles an
    ``EventContextAmount`` anaphoric reference, not a bare ``Power`` ref —
    phase never separately models the un-doubled base clause, so the
    Multiply anchor widens to admit ``EventContextAmount`` too, gated
    behind the SAME :data:`_POWER_MULT_DOER` "power" text confirm (CR
    120.3). Betrayal at the Vault's DamageAll recipient
    ("each of two other target creatures") carries an EMPTY
    ``type_filters`` list (no Creature core type to read structurally) —
    it falls through to the SAME :data:`_POWER_SELF_RECIP`/
    :data:`_POWER_ITS_OWN_DOER` doer-confirm text arm every non-creature-
    typed recipient already uses ("Target creature you control deals
    damage equal to ITS POWER" — CR 120.3)."""
    assert ("creature_ping", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    ["Osseous Sticktwister", "Storm, Queen of Wakanda", "Lukka, Wayward Bonder"],
)
def test_creature_ping_adjudicated_gains_narrow_legacy_fallback(name):
    """ADJUDICATED GAINS over legacy (the SAME class as the already-ported
    Delirium precedent — a legacy fallback-regex gap, not a principled
    exclusion): Osseous Sticktwister's "... this creature deals damage
    equal to its power to each opponent who didn't sacrifice a permanent"
    never matches legacy's ``_CREATURE_PING_ORACLE`` (which requires a bare
    "to (another )?target" tail, not "to each opponent who..."); Storm,
    Queen of Wakanda's "Storm deals damage equal to HER power to that
    creature" uses a pronoun legacy's ``_POWER_ITS_OWN_DOER``-style regex
    never covers (only literal "its power"); Lukka's ultimate emblem
    ("Whenever a creature you control enters, it deals damage equal to its
    power to ANY TARGET") -- legacy's oracle-fallback regex's "to
    (?:another )?target" alt requires the bare word "target" immediately,
    never "any target". All three are genuine CR 120.3 doer-based
    creature_ping members (a creature/object dealing damage equal to its
    OWN power) the structural read now reaches; corpus-verified as this
    batch's only over-vs-legacy delta alongside Delirium."""
    assert ("creature_ping", "you", "") in _idents(name)


# ── Batch 11: counter / ETB / cast trigger-event cluster (§C) ────────────────


def test_counter_place_trigger_typed_lore_gate():
    """CR 122.1 + 714.2b: Scurry Oak's P1P1 CounterAdded payoff fires; a
    Saga's chapters ARE lore-CounterAdded triggers ("{rN}—[Effect]" means
    "When one or more lore counters are put onto this Saga…") — History of
    Benalia's three lore-typed chapters must not open a counters
    build-around. The typed counter_filter is a CLEANER gate than live's
    type_line sniff."""
    assert ("counter_place_trigger", "you", "") in _idents("Scurry Oak")
    assert "counter_place_trigger" not in _keys("History of Benalia")


def test_counter_place_trigger_effect_and_opponent_vetoes():
    """Cathars' Crusade PLACES counters via effect (ChangesZone trigger +
    PutCounterAll — no CounterAdded mode) and stays out; Kros's
    opponent-side population punisher ("creature you don't control" —
    valid_card controller Opponent) is vetoed (checklist #6)."""
    assert "counter_place_trigger" not in _keys("Cathars' Crusade")
    assert "counter_place_trigger" not in _keys("Kros, Defense Contractor")


def test_tribal_etb_multi_vocab_gate():
    """CR 603.6a: Noxious Ghoul's Or[SelfRef, Zombie] watcher surfaces the
    vocab-validated Zombie subtype through the Or walk; Soul Warden's
    generic Creature watcher is creature_etb, not tribal."""
    assert ("tribal_etb_multi", "you", "") in _idents("Noxious Ghoul")
    assert "tribal_etb_multi" not in _keys("Soul Warden")


def test_typed_enters_punish_damage_direction():
    """CR 603.6a + 102.2/102.3: Witty Roastmaster's your-creature ETB +
    typed ``DamageEachPlayer {player_filter: Opponent}`` fires (the shape
    live could only recover from raw); Suture Priest (opponent-enterer
    watcher / GainLife payoff) and Soul Warden (no damage) never do."""
    assert ("typed_enters_punish", "you", "") in _idents("Witty Roastmaster")
    assert "typed_enters_punish" not in _keys("Suture Priest")
    assert "typed_enters_punish" not in _keys("Soul Warden")


def test_noncreature_cast_punish_non_entry_gate():
    """CR 603.2 + 102.2 (scope "any" — "a player" includes you): Ruric
    Thar's ``{Non: Creature}`` watched-spell entry is the discriminator,
    read via the negation-aware non-type read; Beast Whisperer (Creature
    core) stays out."""
    assert ("noncreature_cast_punish", "any", "") in _idents("Ruric Thar, the Unbowed")
    assert "noncreature_cast_punish" not in _keys("Beast Whisperer")


def test_noncreature_cast_punish_prowess_caster_gate():
    """Checklist #5 (corpus-measured — 126 prowess over-fires without it):
    the YOU-cast noncreature REWARD (Burning Prophet — ``valid_target
    {Controller}``) is prowess, not a punisher, and never fires; Ruric
    Thar's recipient-less symmetric watcher still does."""
    assert "noncreature_cast_punish" not in _keys("Burning Prophet")


# ── Batch 11: tap cluster (§D) ───────────────────────────────────────────────


def test_tap_down_opponent_and_detain_arms():
    """CR 701.26a + 701.35 (Detain glossary: "temporarily stops a permanent
    from attacking, blocking, or having its activated abilities
    activated"): Dungeon Geists' opponent-controlled tap target fires arm
    a; Azorius Arrester's Detain fires arm b; the controller-null taps
    (Master Decoy, Frost Titan) are tapper_engine only — live's strict opp
    gate."""
    assert ("tap_down", "opponents", "") in _idents("Dungeon Geists")
    assert ("tap_down", "opponents", "") in _idents("Azorius Arrester")
    assert "tap_down" not in _keys("Master Decoy")
    assert "tap_down" not in _keys("Frost Titan")


def test_tapper_engine_real_target_and_cost_self_exclusion():
    """CR 701.26a: Master Decoy / Frost Titan's SetTapState with a real
    Typed target fire scope "any" (Frost Titan also via the typed CantUntap
    static rider); Prodigal Sorcerer's tap-as-COST emits no SetTapState
    effect and self-excludes (live's subject-is-not-None gate)."""
    assert ("tapper_engine", "any", "") in _idents("Master Decoy")
    assert ("tapper_engine", "any", "") in _idents("Frost Titan")
    assert ("tapper_engine", "any", "") in _idents("Dungeon Geists")
    assert "tapper_engine" not in _keys("Prodigal Sorcerer")


def test_tap_untap_matters_trigger_events():
    """CR 603.2e + 701.26a: the becomes-tapped payoff (Attentive Sunscribe —
    Taps mode) and the Inspired becomes-untapped payoff (Pain Seer — Untaps
    mode, SelfRef live-included) fire; the tap DOER (Master Decoy) never
    does."""
    assert ("tap_untap_matters", "you", "") in _idents("Attentive Sunscribe")
    assert ("tap_untap_matters", "you", "") in _idents("Pain Seer")
    assert "tap_untap_matters" not in _keys("Master Decoy")


# ── Batch 11: library / zone cluster (§E) ────────────────────────────────────


def test_dig_until_own_library_gate():
    """CR 701.20a: Hermit Druid's RevealUntil with player {Controller}
    fires; the FIXED-count reveal (Fact or Fiction — a RevealTop node, a
    different node type) never does."""
    assert ("dig_until", "you", "") in _idents("Hermit Druid")
    assert "dig_until" not in _keys("Fact or Fiction")


def test_dig_until_excludes_their_library_mis_stamps():
    """Phase stamps ``player: Controller`` on "EACH OPPONENT reveals cards
    from the top of THEIR library" (Mind Grind — the [P17]/[P28]
    Controller mis-stamp family on RevealUntil), so the digger gate alone
    passes on opponent-mill cards live excludes. The [P8]/[P21]-precedent
    "their library" description screen restores the boundary; all 69
    both-members are "your library" digs (parity-verified), pinned by the
    Hermit Druid positive above."""
    assert "dig_until" not in _keys("Mind Grind")


def test_dig_until_exile_from_top_until_tag():
    """CR 701.13 + 701.20a: ``ExileFromTopUntil`` is phase's EXILE-side
    sibling of ``RevealUntil`` — the same dig-until-a-condition shape,
    just to Exile instead of staying revealed (Demonlord Belzenlok: "exile
    cards from the top of your library until you exile a nonland card").
    The TAG_MAP maps it to the SAME ``reveal_until`` concept as RevealUntil
    (ADR-0037/0038 W3), so the lane's structural arm covers it with no
    special-case (:func:`reveal_until_player` reads ``.player`` generically
    off either tag)."""
    assert ("dig_until", "you", "") in _idents("Demonlord Belzenlok")


def test_dig_until_nested_grant_descent():
    """A GRANTED trigger (Time Lord Regeneration's "gains ... 'When this
    creature dies, reveal cards from the top of your library until you
    reveal a Time Lord creature card...'") carries its own RevealUntil
    execute effect that is never its own top-level concept node — the
    connive_makers / opponent_cast_matters shared descent
    (``iter_nested_trigger_defs``) reaches it (ADR-0037/0038 W3). CR
    701.20a."""
    assert ("dig_until", "you", "") in _idents("Time Lord Regeneration")


def test_dig_until_unimplemented_grammar_recovery():
    """Mass Polymorph's "reveal cards from the top of your library until
    you reveal that many creature cards" is a genuine Unimplemented
    residue (phase's own reveal-until parser doesn't structure a
    COUNT-tracked "that many" stop condition) — the shared clause
    grammar's ``dig_until`` token re-decorates it to the real
    ``reveal_until`` concept (ADR-0038 / ADR-0037/0038 W3), which the lane
    trusts unconditionally via ``ConceptNode.recovered_by`` (the grammar's
    "your library" ... "until" gate already establishes the digger is
    YOU). CR 701.20a."""
    assert ("dig_until", "you", "") in _idents("Mass Polymorph")


def test_dig_until_no_residue_multi_card_fallback():
    """Invasion of Alara's ETB "exile cards from the top of your library
    until you exile TWO nonland cards with mana value 4 or less" defeats
    phase's own ExileFromTopUntil DynamicQty parser — it degrades to a
    bare single-card ``ChangeZone`` with NO Unimplemented node surviving
    to re-decorate (a genuine ADR-0038-amendment "no residue" class 2
    gap). The whole-card oracle-text fallback
    (``_DIG_UNTIL_NO_RESIDUE_RE``) recovers it structurally (ADR-0037/0038
    W3). CR 701.13/701.20a."""
    assert ("dig_until", "you", "") in _idents("Invasion of Alara")


def test_exile_until_leaves_duration_gate():
    """CR 611.2b + 603.6c: both O-Ring forms carry ``UntilHostLeavesPlay``
    on the exiling unit (Banisher Priest single-trigger; Oblivion Ring's
    ETB trigger — the return half alone never fires per CR 603.6c's
    from-anywhere caveat); a bare exile removal (Path to Exile — no
    duration) is the ported exile_removal, not this lane. Case law
    (Banisher Priest): a token exiled this way ceases to exist."""
    assert ("exile_until_leaves", "you", "") in _idents("Banisher Priest")
    assert ("exile_until_leaves", "you", "") in _idents("Oblivion Ring")
    assert "exile_until_leaves" not in _keys("Path to Exile")


# ── Batch 11: bonus ports (§F) ───────────────────────────────────────────────


def test_typed_spellcast_you_cast_discriminator():
    """CR 603.2 + 102.2: the typed you-cast discriminator — Lys Alana's
    "Whenever you cast an Elf spell" carries ``valid_target {Controller}``
    and fires subject Elf (REPLACES live's "you cast" oracle-regex gate);
    the symmetric hoser (Elvish Handservant — no valid_target) and the
    subtype-less creature-cast watcher (Beast Whisperer) never fire."""
    assert ("typed_spellcast", "you", "Elf") in _idents("Lys Alana Huntmaster")
    assert "typed_spellcast" not in _keys("Elvish Handservant")
    assert "typed_spellcast" not in _keys("Beast Whisperer")


# ADR-0038 W3 batch 2 unit 2 — the typed_spellcast CastWithKeyword arm (CR
# 601.3e's cast-keyword grant is a cast payoff same as a cost discount):
# top-level (Ezio's Freerunning, Hunting Velociraptor's Prowl, The First
# Sliver's Cascade, and the "you may cast X spells as though they had
# flash" family) and the SAME arm reads BOTH tree positions via
# iter_nested_spellcast_static_modes -- a GrantStaticAbility.definition
# nesting (Acolyte of Bahamut) and a created token's own static_abilities
# nesting (The Eleventh Hour).
@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Ezio Auditore da Firenze", "Assassin"),
        ("Hunting Velociraptor", "Dinosaur"),
        ("The First Sliver", "Sliver"),
        ("Ashling, the Limitless", "Elemental"),
        ("Blur of Heroism", "Hero"),
        ("Breath of the Sleepless", "Spirit"),
        ("Mai and Zuko", "Ally"),
        ("Rattlechains", "Spirit"),
        ("Renari, Merchant of Marvels", "Dragon"),
        ("Singer of Swift Rivers", "Merfolk"),
        ("Whirlwing Stormbrood", "Dragon"),
    ],
)
def test_typed_spellcast_cast_with_keyword_arm(name, subject):
    assert ("typed_spellcast", "you", subject) in _idents(name)


def test_typed_spellcast_nested_grant_descent():
    """The GrantStaticAbility.definition nesting (Acolyte of Bahamut's
    "Commander creatures you own have '... Dragon spell ... costs {2}
    less ...'") and the created-token static_abilities nesting (The
    Eleventh Hour's Human token granting "Doctor spells you cast cost {1}
    less") both fire via the SAME deep-walk arm as the top-level static
    form. CR 601.2f."""
    assert ("typed_spellcast", "you", "Dragon") in _idents("Acolyte of Bahamut")
    assert ("typed_spellcast", "you", "Doctor") in _idents("The Eleventh Hour")


def test_typed_spellcast_reduce_next_spell_cost_arm():
    """Invasion of the Giants' Saga chapter III ("The next Giant spell you
    cast this turn costs {2} less to cast") is a ONE-SHOT
    ``ReduceNextSpellCost`` effect, a distinct typed node from the
    persistent ``ModifyCost`` static. CR 601.2f / 714."""
    assert ("typed_spellcast", "you", "Giant") in _idents("Invasion of the Giants")


def test_typed_spellcast_replicate_grant_text_idiom():
    """ "Each <Subtype> spell you cast has replicate" (Hatchery Sliver, Ian
    Chesterton's "Each Saga spell you cast has replicate") phase's static
    parser cannot express -- a last-resort text idiom over the Unimplemented
    residue's own parse-failure description, corpus-verified singleton per
    subject (the third corpus hit, Djinn Illuminatus's "sorcery", is not a
    creature-subtype vocab word and silently drops). CR 601.2f / 702."""
    assert ("typed_spellcast", "you", "Sliver") in _idents("Hatchery Sliver")
    assert ("typed_spellcast", "you", "Saga") in _idents("Ian Chesterton")


def test_typed_spellcast_alt_cost_text_idiom():
    """Kentaro, the Smiling Cat's "You may pay {X} rather than pay the mana
    cost for Samurai spells you cast" is an alternative-cost PayCost effect
    with NO subject field at all (phase drops "for Samurai spells you cast"
    entirely) -- last-resort whole-card text idiom, corpus-verified
    singleton (the only "for <word> spells you cast" hit across the whole
    commander-legal bulk corpus that resolves to a real creature-subtype
    vocab word). CR 601.2f."""
    assert ("typed_spellcast", "you", "Samurai") in _idents("Kentaro, the Smiling Cat")


# ADR-0038 W3 batch 2 unit 2 — beyond-legacy gains: the SECOND subtype in an
# "X spells and Y spells you cast cost {N} less" list (the legacy regex's
# `\b([A-Za-z]+?)s? spells? you cast\b` pattern only anchors on the word
# IMMEDIATELY preceding "you cast" -- an incidental verb-adjacency gap, not
# a deliberate single-subtype policy: `filter_subtypes` already recurses
# Or/And filters and reads every subtype), and the full "outlaw" group
# (Assassin/Mercenary/Pirate/Rogue/Warlock, CR 702.136) a valid_card/
# affected AnyOf filter decomposes into per-subtype signals.
@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        ("Ballyrush Banneret", {"Kithkin", "Soldier"}),
        ("Bosk Banneret", {"Treefolk", "Shaman"}),
        ("Brighthearth Banneret", {"Elemental", "Warrior"}),
        ("Frogtosser Banneret", {"Goblin", "Rogue"}),
        ("Stonybrook Banneret", {"Merfolk", "Wizard"}),
        ("Herald of War", {"Angel", "Human"}),
        (
            "The Destined Warrior",
            {"Cleric", "Rogue", "Warrior", "Wizard"},
        ),
        (
            "Discreet Retreat",
            {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"},
        ),
        (
            "Double Down",
            {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"},
        ),
    ],
)
def test_typed_spellcast_multi_subtype_beyond_legacy_gain(name, subjects):
    got = {s for k, _sc, s in _idents(name) if k == "typed_spellcast"}
    assert subjects <= got


def test_typed_spellcast_eldrazi_trigger_gain():
    """Emrakul's Influence's "Whenever you cast an Eldrazi creature spell
    with mana value 7 or greater, draw two cards" fires via the pre-existing
    cast_spell trigger arm -- a genuine beyond-legacy recall gain (CR
    109.3 / 601.2 / 603.2)."""
    assert ("typed_spellcast", "you", "Eldrazi") in _idents("Emrakul's Influence")


def test_legends_matter_filter_property():
    """CR 205.4d: Reki's ``HasSupertype: Legendary`` watched-spell filter
    fires; being legendary ITSELF (Ruric Thar — no Legendary-referencing
    filter) is not legends-matter."""
    assert ("legends_matter", "you", "") in _idents("Reki, the History of Kamigawa")
    assert "legends_matter" not in _keys("Ruric Thar, the Unbowed")


def test_historic_matters_filter_property():
    """CR 700.6 ("The term historic refers to an object that has the
    legendary supertype, the artifact card type, or the Saga subtype"):
    Jhoira's ``Historic`` filter property fires; Reki's Legendary-only
    filter does not cross-fire."""
    assert ("historic_matters", "you", "") in _idents("Jhoira, Weatherlight Captain")
    assert "historic_matters" not in _keys("Reki, the History of Kamigawa")


@pytest.mark.parametrize(
    "name",
    [
        "Curator's Ward",  # LeavesBattlefield "if it was historic" condition
        "Sanctum Spirit",  # activation cost "Discard a historic card"
        "Jhoira's Familiar",  # ModifyCost affected drops the Historic filter
        "Banish to Another Universe",  # Affinity for historic permanents
        "The Eighth Doctor",  # multi-clause Unimplemented, no Historic node
        "Havi, the All-Father",  # Unrecognized static condition, raw text only
    ],
)
def test_historic_matters_bare_word_bridge_synthesis(name):
    """ADR-0037/0038 synthesis: CR 700.10 defines historic (artifact,
    legendary, Saga), but phase drops the qualifier ENTIRELY for these six
    shapes — no typed Historic filter property survives anywhere in the
    tree, only the bare word in the whole-card oracle.
    ``tree_synthesis._arm_historic_matters`` mirrors the OLD-IR
    ``_recover_historic_subject``/``_HISTORIC_REF`` bare-word fallback
    byte-for-byte."""
    assert ("historic_matters", "you", "") in _idents(name)


def test_self_blink_chain_join():
    """CR 611.2b (contrast 603.6c): Aetherling's ChangeZone SelfRef→Exile +
    the delayed ParentTarget return in the SAME unit fires (live is
    kept-mirror-ONLY — STALE for the v0.9.0 mirror); exiling ANOTHER target
    (Banisher Priest, Oblivion Ring) fails the SelfRef gate."""
    assert ("self_blink", "you", "") in _idents("Aetherling")
    assert "self_blink" not in _keys("Banisher Priest")
    assert "self_blink" not in _keys("Oblivion Ring")


def test_self_blink_saga_and_unearth_vetoes_scoped_by_live_parity():
    """Corpus-measured, SCOPED gates (parity-before-veto): the
    transforming-Saga lore-chapter flip ("Exile this Saga, then return it
    to the battlefield transformed" — The Restoration of Eiganjo; 29
    corpus, live uniformly no-fire; CR 714.2b) and unearth's
    graveyard-origin self-return (Anathemancer — CR 702.84a) never fire —
    but the NON-Saga transform flip live DOES fire (Liliana, Heretical
    Healer's dies-flip, measured) stays IN: a blanket enter_transformed
    veto would have regressed live members."""
    assert "self_blink" not in _keys("The Restoration of Eiganjo")
    assert "self_blink" not in _keys("Anathemancer")
    assert ("self_blink", "you", "") in _idents("Liliana, Heretical Healer")


# ── Batch 11: batch-10 adjudicated follow-ups ────────────────────────────────


def test_ltb_matters_condition_arm_zone_precise():
    """Follow-up (a): the Revolt-family typed ``ZoneChangeCountThisTurn
    {from: Battlefield}`` condition with controller You fires (Airdrop
    Aeronauts); Morbid's ``to: Graveyard`` variant (Tragic Slip — a death
    check) is zone-precise and never fires."""
    assert ("ltb_matters", "you", "") in _idents("Airdrop Aeronauts")
    assert "ltb_matters" not in _keys("Tragic Slip")


def test_creature_etb_entered_this_turn_arm():
    """Follow-up (b): the "you had a creature enter under your control this
    turn" condition family carries a typed ``EnteredThisTurn`` qty whose
    filter is Creature-cored + controller You (Bellowing Elk); the
    Celebration nonland-permanent form (Ash, Party Crasher) fails the
    Creature gate (measured live parity)."""
    assert ("creature_etb", "you", "") in _idents("Bellowing Elk")
    assert "creature_etb" not in _keys("Ash, Party Crasher")


# ── ADR-0038 W3 batch 6 (draw-etb-tokens cluster): creature_etb PROMOTED ────


def test_creature_etb_nested_grant_descent():
    """Arm 4: a ``CreateEmblem``/``GrantTrigger`` nested creature-ETB def
    fires via :func:`is_creature_etb_trigger_def` applied to
    :func:`iter_nested_trigger_defs`'s yield — Kiora, Master of the Depths's
    -8 emblem ("Whenever a creature you control enters, you may have it
    fight target creature") and Nurturing Presence's Aura grant (Enchanted
    creature has "Whenever a creature you control enters, ~ gets +1/+1
    ..."). CR 603.6a."""
    assert ("creature_etb", "you", "") in _idents("Kiora, Master of the Depths")
    assert ("creature_etb", "you", "") in _idents("Nurturing Presence")


def test_creature_etb_delayed_trigger_descent():
    """Arm 5: a ``CreateDelayedTrigger``'s ``WheneverEvent`` watcher fires
    via :func:`iter_delayed_trigger_condition_defs` — First Day of Class
    (an Instant installing a temporary "whenever a creature you control
    enters this turn" watcher, not itself a top-level trigger unit).
    CR 603.6a / 603.2."""
    assert ("creature_etb", "you", "") in _idents("First Day of Class")


def test_creature_etb_entersorattacks_widening():
    """The compound ``entersorattacks`` event (Kindred Discovery's
    "Whenever a creature you control of the chosen type enters or attacks,
    draw a card") folds into :func:`is_creature_etb_trigger_def` — CR 603.2
    (one trigger condition naming two alternative events; the predicate
    only asserts the entering half applies)."""
    assert ("creature_etb", "you", "") in _idents("Kindred Discovery")


def test_creature_etb_unknown_mode_description_fallback():
    """Arm 6: :func:`_unknown_mode_creature_etb` reads an Unknown-mode
    trigger's OWN ``description`` when phase's typed ``valid_card`` parse
    can't represent the filter — Symmetry Matrix's "power equal to its
    toughness" filter defeats structural parse and falls back to
    ``mode.key == "Unknown"``. CR 603.6a."""
    assert ("creature_etb", "you", "") in _idents("Symmetry Matrix")


def test_creature_etb_unimplemented_ability_fallback():
    """Arm 7: :func:`_unimplemented_ability_creature_etb` reads a WHOLE-
    ability Unimplemented node's own description — the Stickers family's
    ``{TK}``-templated line (Familiar Beeble Mascot: "Whenever a creature
    enters under your control, creatures you control get +1/+1 until end
    of turn"). Full-corpus re-measure: exactly 3 Stickers cards fire,
    nothing else. CR 603.6a."""
    assert ("creature_etb", "you", "") in _idents("Familiar Beeble Mascot")


def test_creature_etb_soulbond_graft_gain():
    """cw_only gain (pre-existing top-level Arm 1, verified this batch): CR
    702.95a's Soulbond and CR 702.58a's Graft each parse as TWO trigger
    units — the SelfRef "when this creature enters, pair/graft" half
    (excluded, ETB value on itself) and a "whenever ANOTHER creature you
    control enters" half with a Creature-typed ``valid_card`` that fires
    normally (Silverblade Paladin, Cytoplast Root-Kin)."""
    assert ("creature_etb", "you", "") in _idents("Silverblade Paladin")
    assert ("creature_etb", "you", "") in _idents("Cytoplast Root-Kin")


def test_creature_etb_shed_cast_trigger_counter_modifier():
    """Adjudicated SHED (class 1): "whenever you cast a creature spell,
    that creature enters with N additional counters" (Boreal Outrider) is a
    CAST-triggered replacement of how the permanent enters (CR 614.12), not
    an ENTERS-event trigger — ``creature_cast_trigger``'s own docstring
    already names this card as ITS gap, confirming the lane boundary."""
    assert "creature_etb" not in _keys("Boreal Outrider")


def test_creature_etb_shed_combat_damage_recency_condition():
    """Adjudicated SHED (class 2): a combat-damage trigger merely
    CONDITIONED on "that creature entered this turn" (Samut, Vizier of
    Naktamun) is watching combat damage (CR 510.1b), not entering — the
    recency check is a condition on an unrelated trigger, not an ETB
    payoff."""
    assert "creature_etb" not in _keys("Samut, Vizier of Naktamun")


def test_creature_etb_shed_cross_clause_regex_bleed():
    """Adjudicated SHED (class 3): legacy's whole-card regex mirror spans
    an unrelated "a"/"creature"/"enter[s]" across a newline-joined,
    period-less span of UNRELATED ability lines (Kitnap's Gift reminder
    "a card" + "Enchant creature" + "this Aura enters" bleeding together)
    — never a real creature-ETB trigger. The per-node description arms
    (Arms 6/7) don't reproduce this because each node's description is
    scoped to ONE ability, never blended with a sibling's text."""
    assert "creature_etb" not in _keys("Kitnap")


def test_creature_etb_shed_noncreature_doubler():
    """Adjudicated SHED (class 4): the ``DOUBLER`` regex fires on a
    LAND-entering trigger doubler with no Creature filter at all (Traveling
    Chocobo: "If a land or Bird you control entering ... triggers an
    additional time") — CR 603.6a requires the watched event's filter
    include the Creature core type; Arm 2's structural
    ``double_triggers_cause_core_types`` gate correctly excludes it."""
    assert "creature_etb" not in _keys("Traveling Chocobo")


def test_creature_etb_shed_selfref_own_targeting_filter():
    """Adjudicated SHED (class 5): Sweet-Gum Recluse's SelfRef "When this
    creature enters, put counters on ... target creatures that entered this
    turn" — the ONLY "creature ... enter" match is its OWN targeting
    restriction, not a payoff engine watching OTHER creatures enter;
    consistent with the SelfRef-exclusion design (Elvish Visionary)."""
    assert "creature_etb" not in _keys("Sweet-Gum Recluse")


def test_creature_etb_delayed_had_enter_arm():
    """Arm 8: :func:`_delayed_had_enter_creature_etb` reads a trigger's own
    description for the legacy ``_ETB_HAD_RE`` idiom regardless of mode —
    Ephara, God of the Polis's upkeep-gated "if you had another creature
    enter ... last turn, draw a card" has no ``etb`` event at all in
    phase's model (an upkeep-phase trigger with a historical qty
    condition), so no structural arm can ever reach it. Full-corpus
    re-measure: only Ephara's own description matches."""
    assert ("creature_etb", "you", "") in _idents("Ephara, God of the Polis")


def test_damage_prevention_shield_replacement_arm():
    """Follow-up (c): the CR 615 prevention-shield MEMBERSHIP via typed
    ``shield_kind {Prevention}`` on a DamageDone replacement (Palisade
    Giant family) — redirect SEMANTICS deliberately uncaptured
    (damage_redirect stays KEPT); an amplify replacement with no shield
    (Furnace of Rath) never fires this lane."""
    assert ("damage_prevention", "you", "") in _idents("Palisade Giant")
    assert "damage_prevention" not in _keys("Furnace of Rath")


def test_damage_prevention_shield_excludes_offensive_curse():
    """Treacherous Link ("All damage that would be dealt to enchanted
    creature is dealt to its controller instead") is an OFFENSIVE curse —
    phase emits a bare shield_kind{Prevention} structurally identical to
    Pariah ([P29]). The description screen keys on the SHIELDED subject:
    "dealt to enchanted creature is dealt to" → veto; Pariah ("dealt to
    YOU is dealt to enchanted creature instead") and Mirror Strike
    ("dealt to YOU ... dealt to its controller instead") protect you —
    Pariah keeps firing, Mirror Strike's non-fire is pinned (adjudicated
    corpus scan: exactly two redirect-to-controller shields exist)."""
    assert "damage_prevention" not in _keys("Treacherous Link")
    assert ("damage_prevention", "you", "") in _idents("Pariah")


def test_opponent_cast_matters_spell_cast_or_copy_mode():
    """Follow-up (e): the batched ``SpellCastOrCopy`` mode joins the read —
    Mage Hunter's opponent-scoped valid_target fires; the Controller-scoped
    Magecraft form (Archmage Emeritus) stays out on the same recipient
    gate."""
    assert ("opponent_cast_matters", "opponents", "") in _idents("Mage Hunter")
    assert "opponent_cast_matters" not in _keys("Archmage Emeritus")


def test_base_pt_set_dynamic_pair_arm():
    """Follow-up (f): the DYNAMIC base-P/T-set pair ``SetPowerDynamic`` +
    ``SetToughnessDynamic`` fires on both shapes — the one-shot nested
    static ("base power and toughness X/X" — Biomass Mutation) and the
    top-level equipped-creature static (Aettir and Priwen). Distinct from
    the SetDynamicPower CDA tags (variable_pt — Tarmogoyf's */*)."""
    assert ("base_pt_set", "any", "") in _idents("Biomass Mutation")
    assert ("base_pt_set", "any", "") in _idents("Aettir and Priwen")


# ── Batch 12: §A trigger-event payoff cluster ────────────────────────────────


def test_scry_surveil_matters_trigger_not_effect():
    """CR 701.22a / 701.25a: a Scry/Surveil TRIGGER mode is the payoff
    (Arwen Undómiel's "whenever you scry", Whispering Snitch / Mirko's
    surveil watchers); a bare Scry EFFECT node (Opt — a doer, gate #4
    membership) never fires — doers ride the ported topdeck_selection."""
    for name in ("Arwen Undómiel", "Whispering Snitch", "Mirko, Obsessive Theorist"):
        assert ("scry_surveil_matters", "you", "") in _idents(name)
    assert "scry_surveil_matters" not in _keys("Opt")


def test_cycling_matters_mode_and_selfref_gate():
    """CR 702.29a: a Cycled / CycledOrDiscarded trigger whose valid_card is
    not SelfRef fires (Astral Slide — null watcher; Archfiend of Ifnir —
    Typed/Another); the "when you cycle THIS card" bonus (Agonasaur Rex —
    SelfRef) is membership, not a cycling-theme payoff."""
    assert ("cycling_matters", "you", "") in _idents("Astral Slide")
    assert ("cycling_matters", "you", "") in _idents("Archfiend of Ifnir")
    assert "cycling_matters" not in _keys("Agonasaur Rex")


def test_exert_matters_vigilance_grant_and_johan_mirror():
    """CR 701.43a + 702.20b: the mass-vigilance enabler (Always Watching —
    generic your-creatures grant, NonToken allowed) and the Johan word
    mirror fire; the Exerted trigger is MEMBERSHIP (Combat Celebrant never
    fires, gate #4) and a subtype-scoped vigilance grant (Pheres-Band
    Warchief's Centaurs) fails the generic-team gate."""
    assert ("exert_matters", "you", "") in _idents("Always Watching")
    assert ("exert_matters", "you", "") in _idents("Johan")
    assert "exert_matters" not in _keys("Combat Celebrant")
    assert "exert_matters" not in _keys("Pheres-Band Warchief")


def test_entered_attacker_mirror_per_clause():
    """CR 302.6 / 603.10a: FULLY STRUCTURAL (ADR-0036/0037 fold — the
    lane-time ``ENTERED_ATTACKER_REGEX`` per-clause read is RETIRED) — a
    trigger whose derived event is an attack/combat-damage event carrying an
    ``EnteredThisTurn``/``SourceEnteredThisTurn`` node anywhere in the
    trigger (Pick Up the Pace, Samut); Cradle to Grave's "destroy ... that
    entered this turn" has no attack/combat-damage TRIGGER and never fires.
    The structural read is a NET RECALL IMPROVEMENT over the retired mirror:
    "Iron Man, Master of Machines"'s "Whenever Iron Man attacks, if an
    artifact entered the battlefield UNDER YOUR CONTROL this turn, draw a
    card" — the mirror's phrase anchor required "entered the battlefield"
    immediately followed by "this turn", missing the "under your control"
    insertion — now fires via the structural read."""
    assert ("entered_attacker", "you", "") in _idents("Pick Up the Pace")
    assert ("entered_attacker", "you", "") in _idents("Samut, Vizier of Naktamun")
    assert ("entered_attacker", "you", "") in _idents("Iron Man, Master of Machines")
    assert "entered_attacker" not in _keys("Cradle to Grave")


def test_saga_matters_lore_and_saga_reference_arms():
    """CR 714.2/714.4 (case law Satsuki: putting a lore counter usually
    triggers the next chapter): a lore-counter manipulation on a NON-Saga
    card (Keldon Warcaller, Satsuki) and a Saga-subtype static reference
    (Barbara Wright's read-ahead grant) fire; a Saga's OWN chapters / ETB
    lore replacement are membership (An Unearthly Child, History of
    Benalia — gate #4), and a multi-choice tutor that merely CAN fetch a
    Saga (Search for Glory — [P16], live-verified no-fire) stays out."""
    for name in ("Keldon Warcaller", "Satsuki, the Living Lore", "Barbara Wright"):
        assert ("saga_matters", "you", "") in _idents(name)
    for name in ("An Unearthly Child", "History of Benalia", "Search for Glory"):
        assert "saga_matters" not in _keys(name)


# ── Batch 12: §B effect-node lanes ───────────────────────────────────────────


def test_life_total_set_player_shaped_target_gate():
    """CR 119.5 + 701.12c (case law Magister Sphinx): SetLifeTotal with a
    PLAYER target, ExchangeLifeTotals, and Double{LifeTotal} fire scope
    "any"; the SetLifeTotal-onto-a-CREATURE-filter misparse family
    (Baffling Defenses — a perpetual P/T set) is vetoed, and a plain
    GainLife (Whispering Snitch) never reaches the lane."""
    assert ("life_total_set", "any", "") in _idents("Magister Sphinx")
    assert ("life_total_set", "any", "") in _idents("Axis of Mortality")
    assert ("life_total_set", "any", "") in _idents("Celestial Mantle")
    assert "life_total_set" not in _keys("Baffling Defenses")
    assert "life_total_set" not in _keys("Whispering Snitch")


def test_unspent_mana_structural_mode_and_mirror():
    """CR 106.4 / 500.5 (case law Kruphix): the StepEndUnspentMana static
    mode (Retain — Upwelling; Transform — Horizon Stone, Kruphix) fires
    structurally; the byte-identical UNSPENT_MANA_REGEX mirror covers the
    burst-rider tail; a plain rock (Sol Ring) never fires."""
    assert ("unspent_mana", "you", "") in _idents("Horizon Stone")
    assert ("unspent_mana", "you", "") in _idents("Upwelling")
    assert ("unspent_mana", "you", "") in _idents("Kruphix, God of Horizons")
    assert "unspent_mana" not in _keys("Sol Ring")


def test_opp_top_exile_direction_gates():
    """CR 406.1: ExileTop whose player is Typed{controller: Opponent}
    (Ashiok, Nightmare Weaver) or a directed Player target (Circu) fires;
    a Controller-resolving player node ([P5]/[P17]) would be self-mill and
    never fires. Ashiok, Wicked Manipulator's pay-life self-exile IS
    Controller-side (a ChangeZone, doubly out) — but its [-7] "target
    player exiles the top X" is a genuine directed ``Player`` ExileTop,
    the SAME typed shape as Circu's, so it fires (a documented deviation
    from the spec's negative: the spec's "resolves to Controller" premise
    was probed false for that node, and a tag-Player veto would drop
    Circu, a live member — parity-before-veto)."""
    assert ("opp_top_exile", "you", "") in _idents("Ashiok, Nightmare Weaver")
    assert ("opp_top_exile", "you", "") in _idents("Circu, Dimir Lobotomist")
    assert ("opp_top_exile", "you", "") in _idents("Ashiok, Wicked Manipulator")


def test_kill_engine_repeatable_creature_gate():
    """CR 305.6 / 701.8: a repeatable-frame single-target creature Destroy
    on a card that is itself a Creature fires LOW (Visara, Avatar of Woe,
    Royal Assassin's qualified "tapped creature" the narrow live regex
    missed rides the same structural read); a one-shot ETB destroy
    (Nekrataal) and a DestroyAll wipe on a noncreature (Wrath of God)
    never fire."""
    for name in ("Visara the Dreadful", "Avatar of Woe", "Royal Assassin"):
        assert ("kill_engine", "you", "") in _idents(name)
    sigs = extract_crosswalk_signals(_tree("Visara the Dreadful"))
    assert all(s.confidence == "low" for s in sigs if s.key == "kill_engine")
    assert "kill_engine" not in _keys("Nekrataal")
    assert "kill_engine" not in _keys("Wrath of God")


# ── Batch 12: §C control / land cluster ──────────────────────────────────────


def test_control_exchange_owned_return_shape_only():
    """CR 701.12b / 108.3: the exile-leaf-with-Owned:you + sibling
    return-to-battlefield chain join fires (Meneldor); Oblivion Sower's
    Owned:TargetPlayer theft-ramp and a plain blink (Cloudshift — controller
    You, no Owned predicate) stay out. The 18 ExchangeControl nodes stay in
    gain_control's country (live-extractor-verified on Gilded Drake /
    Daring Thief — the spec's mandatory parity check)."""
    assert ("control_exchange", "you", "") in _idents("Meneldor, Swift Savior")
    assert "control_exchange" not in _keys("Oblivion Sower")
    assert "control_exchange" not in _keys("Cloudshift")
    assert "control_exchange" not in _keys("Gilded Drake")


def test_control_exchange_excludes_owned_and_controlled_blink():
    """Yorion exiles permanents you OWN **and** CONTROL — own+control is a
    pure value blink (no steal-recovery is possible; CR 108.3 owned vs
    701.12b exchanged control), rules-lawyer-adjudicated blocking in
    batch 12. The veto is the CONJUNCTION on the same filter; Meneldor's
    Owned:You with controller null keeps firing (the steal-recovery
    shape)."""
    assert "control_exchange" not in _keys("Yorion, Sky Nomad")


def test_land_exchange_land_cored_exchange():
    """CR 701.12b: ExchangeControl whose target filters are Land-cored
    fires (Political Trickery, Vedalken Plotter); Gilded Drake's
    creature-for-creature exchange stays out."""
    assert ("land_exchange", "you", "") in _idents("Political Trickery")
    assert ("land_exchange", "you", "") in _idents("Vedalken Plotter")
    assert "land_exchange" not in _keys("Gilded Drake")


def test_land_denial_pure_your_land_phaseout():
    """CR 702.26: PhaseOut whose filter is pure Typed[Land] controller You
    fires (Taniwha); Reality Ripple's Or-filter one-shot and Clever
    Concealment's nonland-permanent phase-out never fire."""
    assert ("land_denial", "you", "") in _idents("Taniwha")
    assert "land_denial" not in _keys("Reality Ripple")
    assert "land_denial" not in _keys("Clever Concealment")


def test_land_protection_widened_animator_and_manland_mirror():
    """CR 613.1d / 305: the b1 animator arm widened to ("you","any")
    controllers fires on the symmetric all-lands animate (Living Plane —
    live-parity: live passes the widened tuple) and the Tier-1 manland
    self-animate structural read (ADR-0036/0037 fold) recovers Restless
    Anchorage; Reality Ripple's phase-out is not an animator."""
    assert ("land_protection", "you", "") in _idents("Living Plane")
    assert ("land_protection", "you", "") in _idents("Restless Anchorage")
    assert "land_protection" not in _keys("Reality Ripple")


def test_land_protection_manland_structural_recovery_and_synth_tail():
    """A genuine RECOVER the deleted mirror missed (Crawling Barrens: no
    "land" word precedes "becomes a 0/0 Elemental creature"), a landish-
    AFFECTED recovery (Genju of the Falls' Aura animates the ENCHANTED
    Island), a bucket-B synth-tail genuine member (Emergent Sequence's
    search-then-animate chain), and three adjudicated land-type-change
    over-fires shed (Gaea's Liege, Graceful Antelope, Tide Shaper — "target
    land becomes a Forest/Plains/Island" is a type change, not an
    animate)."""
    assert ("land_protection", "you", "") in _idents("Crawling Barrens")
    assert ("land_protection", "you", "") in _idents("Genju of the Falls")
    assert ("land_protection", "you", "") in _idents("Emergent Sequence")
    assert "land_protection" not in _keys("Gaea's Liege")
    assert "land_protection" not in _keys("Graceful Antelope")
    assert "land_protection" not in _keys("Tide Shaper")


def test_evasion_denial_ignore_landwalk_mode():
    """CR 702.14: the IgnoreLandwalkForBlocking static mode fires scope
    "opponents" (Great Wall's plainswalk, Crevasse's mountainwalk); a
    single-creature pacify Aura (Pacifism) is not evasion denial."""
    assert ("evasion_denial", "opponents", "") in _idents("Great Wall")
    assert ("evasion_denial", "opponents", "") in _idents("Crevasse")
    assert "evasion_denial" not in _keys("Pacifism")


def test_evasion_denial_static_parse_failure_recovery():
    """CR 509.1b/702.14 — Staff of the Ages's own static parser fails
    ("Creatures with landwalk abilities can be blocked as though they
    didn't have those abilities."), leaving an Unimplemented parse-failure
    residue that is STILL role=effect; the ADR-0038
    clause_grammar.STATIC_TOKENS row recovers it to concept="evasion_denial"
    via recovery.ALLOWLIST, so the SAME typed read the clean
    IgnoreLandwalkForBlocking statics use (Great Wall, Crevasse) picks it
    up — no marker special-case."""
    assert "evasion_denial" in _keys("Staff of the Ages")


# ── Batch 12: §D mirror-parity lanes ─────────────────────────────────────────


def test_animate_artifact_mirror_primary():
    """CR 613.1d + 702.122b: Tier-1 (ADR-0036/0037 fold — the
    ``ANIMATE_ARTIFACT_REGEX`` mirror relocated verbatim to a bucket-B
    ``tree_synthesis`` arm, no competing Tier-1 predicate) fires (Karn,
    Silver Golem; Titania's Song); a bare becomes-an-artifact type
    conferral (Liquimetal Coating, Mycosynth Lattice) never fires."""
    assert ("animate_artifact", "you", "") in _idents("Karn, Silver Golem")
    assert ("animate_artifact", "you", "") in _idents("Titania's Song")
    assert "animate_artifact" not in _keys("Liquimetal Coating")
    assert "animate_artifact" not in _keys("Mycosynth Lattice")


def test_color_change_mirror_primary():
    """CR 105.3: Tier-1 (ADR-0036/0037 fold — the ``COLOR_CHANGE_REGEX``
    mirror relocated verbatim to a bucket-B ``tree_synthesis`` arm) fires
    (Alchor's Tomb, Distorting Lens); "becomes colorless" (Ancient Kavu)
    is a regex non-match and eternalize's token SetColor (Adorned Pouncer)
    never reaches the lane — the raw structural SetColor read over-fires
    ~94% and stays unported."""
    assert ("color_change", "you", "") in _idents("Alchor's Tomb")
    assert ("color_change", "you", "") in _idents("Distorting Lens")
    assert "color_change" not in _keys("Ancient Kavu")
    assert "color_change" not in _keys("Adorned Pouncer")


def test_type_change_protection_payload_vocab_gate():
    """CR 702.16 + 613.1d: AddKeyword{Protection: {CardType: <arg>}} with a
    vocab-validated creature-subtype arg fires (Gor Muldrak's Salamanders —
    the "phase drops the argument" note was STALE); protection from a COLOR
    (White Knight) never fires."""
    assert ("type_change", "you", "") in _idents("Gor Muldrak, Amphinologist")
    assert "type_change" not in _keys("White Knight")


# ── Batch 12: §E statics / taxes / counters cluster ──────────────────────────


def test_stax_taxes_structural_census():
    """CR 101.2 + 604.1, scope from each static's OWN who/affected node:
    CantAttack onto opponents' creatures (Propaganda), ModifyCost{Raise}
    directed at opponents (Aura of Silence — gate ii's non-you direction),
    MustAttack onto opponents (Fumiko), the opponents-enter-tapped
    replacement (Authority of the Consuls), and the opponent hand-size
    reducer (Gnat Miser) all fire stax_taxes."""
    for name in (
        "Propaganda",
        "Aura of Silence",
        "Fumiko the Lowblood",
        "Authority of the Consuls",
        "Gnat Miser",
    ):
        assert ("stax_taxes", "opponents", "") in _idents(name), name


def test_symmetric_stax_census_and_residue_mirror():
    """CR 604.1: an AllPlayers/unscoped restriction fires symmetric_stax
    (Warmonger Hellkite's MustAttack, Root Maze's symmetric enters-tapped);
    Winter Orb's unparsed "players can't untap" clause rides the
    byte-identical residue mirror; a symmetric COST tax (Sphere of
    Resistance) co-fires stax_taxes (live's stax_tax-kind co-fire)."""
    assert ("symmetric_stax", "each", "") in _idents("Warmonger Hellkite")
    assert ("symmetric_stax", "each", "") in _idents("Root Maze")
    assert ("symmetric_stax", "each", "") in _idents("Winter Orb")
    assert ("symmetric_stax", "each", "") in _idents("Sphere of Resistance")
    assert ("stax_taxes", "opponents", "") in _idents("Sphere of Resistance")


def test_stax_cast_activation_lock_cofire():
    """An AllPlayers cast/activation LOCK is both a symmetric restriction
    and a tax the caster-you cares about (live fires both on Stony
    Silence's CantBeActivated{AllPlayers})."""
    assert ("symmetric_stax", "each", "") in _idents("Stony Silence")
    assert ("stax_taxes", "opponents", "") in _idents("Stony Silence")


def test_stax_pacify_and_untap_blessing_vetoes():
    """Gate (i): the single-creature pacify veto is LOAD-BEARING — Pacifism
    and Arrest (EnchantedBy-predicated restriction statics) open NEITHER
    lane; gate (iii): an untap BLESSING (Seedborn Muse's
    UntapsDuringEachOtherPlayersUntapStep) is not a restriction."""
    for name in ("Pacifism", "Arrest", "Seedborn Muse"):
        ks = _keys(name)
        assert "stax_taxes" not in ks, name
        assert "symmetric_stax" not in ks, name


def test_stax_taxes_add_restriction_prohibit_activity():
    """ADR-0038 W1 batch-4: a one-shot ``AddRestriction`` effect (Silence's
    "your opponents can't cast spells this turn") carries WHOM it hobbles
    on ``restriction.affected_players`` -- a DIFFERENT shape than the
    continuous static census (no ``affected``/``modifications`` pair, so
    :func:`iter_static_defs` never yields it). OpponentsOfSourceController
    -> stax. CR 604.1 / 720."""
    assert ("stax_taxes", "opponents", "") in _idents("Silence")


def test_stax_taxes_createemblem_nested_static():
    """Narset Transcendent's ultimate grants an emblem carrying a nested
    CantBeCast{who: Opponents} static under ``CreateEmblem.statics`` --
    :func:`iter_static_defs` gained "statics" to its field-walk so the
    emblem's granted lock reads structurally (the only field in the
    schema shaped this way, so the extension is safe and narrow)."""
    assert ("stax_taxes", "opponents", "") in _idents("Narset Transcendent")


def test_stax_taxes_target_opponent_controller_value():
    """A filter names its controller "TargetOpponent" for "target opponent
    controls" (Exhaustion's CantUntap) -- the SAME opponent-directed lock
    as the bare "Opponent" value (Propaganda's "an opponent controls"),
    CR 604.1."""
    assert ("stax_taxes", "opponents", "") in _idents("Exhaustion")


def test_stax_taxes_reduce_ability_cost_opponent_scoped():
    """Eidolon of Obstruction's "loyalty abilities of planeswalkers your
    opponents control cost {1} more to activate" is a KEYWORD-scoped cost
    tax (``ReduceAbilityCost{mode: Raise}``) -- the ``ModifyCost{Raise}``
    sibling for a named-ability-kind cost raise, explicitly opponent-
    controller-gated. CR 601.2f."""
    assert ("stax_taxes", "opponents", "") in _idents("Eidolon of Obstruction")


def test_stax_taxes_reduce_ability_cost_unscoped_excluded():
    """An UNSCOPED ``ReduceAbilityCost{Raise}`` (Suppression Field's bare
    "activated abilities cost {2} more to activate unless they're mana
    abilities", ctrl None) does NOT co-fire stax_taxes -- unlike
    ModifyCost{Raise}'s unscoped-tax co-fire (Sphere of Resistance), this
    mode requires an explicit opponent controller (measured cw_only
    over-fire; a single-target Aura cost tax like Oppressive Rays' carries
    no controller tag either and is excluded by the same narrow gate)."""
    assert "stax_taxes" not in _keys("Suppression Field")


def test_stax_taxes_grammar_recovery_dynamic_threshold():
    """Lavinia, Azorius Renegade's "Each opponent can't cast noncreature
    spells with mana value greater than the number of lands that player
    controls" is a DYNAMIC-threshold restriction phase's own static parser
    can't build, leaving an Unimplemented parse-failure residue. The
    ADR-0038 clause-grammar STATIC_TOKENS "opponents? can't cast" idiom
    re-decorates it straight to the real "stax_taxes" concept (no
    synth_* marker)."""
    assert ("stax_taxes", "opponents", "") in _idents("Lavinia, Azorius Renegade")


def test_stax_taxes_punisher_third_party_possessive():
    """A SelfRef combat restriction ("~ can't attack or block unless an
    opponent has eight or more cards in THEIR graveyard" -- Relic Golem)
    is normally a self-drawback, not a lock on opponents -- but its own
    clause names a third party's zone, mirroring old-IR's broad
    third-party-possessive scope repair (supplement._BROAD_THIRD_PARTY)
    byte-for-byte."""
    assert ("stax_taxes", "opponents", "") in _idents("Relic Golem")


def test_keyword_counter_kind_gate_and_mirror():
    """CR 122.1b: a place/remove of a counter whose kind is in the live
    _KEYWORD_COUNTER_KINDS closed set fires scope "any" (Arwen, Mortal
    Queen's indestructible enters-with + remove-as-cost); the
    counter-kind-dropped choice tail (Wingfold Pteron) rides the
    KEYWORD_COUNTER_REGEX mirror; a stun counter (Icebind Pillar — CR
    122.1d, a replacement-maker, not a 122.1b keyword counter) and a plain
    +1/+1 placement (Cathedral Acolyte) never fire."""
    assert ("keyword_counter", "any", "") in _idents("Arwen, Mortal Queen")
    assert ("keyword_counter", "any", "") in _idents("Wingfold Pteron")
    assert "keyword_counter" not in _keys("Icebind Pillar")
    assert "keyword_counter" not in _keys("Cathedral Acolyte")


def test_counter_grants_kw_pred_kind_and_controller_gates():
    """A keyword granted to YOUR creatures that HAVE a counter — the
    Counters predicate of kind P1P1 (Bramblewood Paragon) or the
    kind-agnostic Any (Cathedral Acolyte's ward) with controller You;
    an enters-with-counter chooser (Wingfold Pteron) and a plain team
    grant with no Counters predicate (Always Watching) never fire."""
    assert ("counter_grants_kw", "you", "") in _idents("Bramblewood Paragon")
    assert ("counter_grants_kw", "you", "") in _idents("Cathedral Acolyte")
    assert "counter_grants_kw" not in _keys("Wingfold Pteron")
    assert "counter_grants_kw" not in _keys("Always Watching")


def test_counter_distribute_structural_marker_and_mirror():
    """CR 115.7f + 601.2d: the mass PutCounterAll P1P1 onto your creatures
    (Cathars' Crusade), the typed distribute marker phase v0.9.0 DOES carry
    (Verdurous Gearhulk — the spec's [P-fold] claim was stale; the mirror
    co-fires), and the enters-with-ADDITIONAL replacement (Bramblewood
    Paragon, mirror arm) fire; a SELF-enters-with (Endless One —
    self_counter_grow country) and a lore-kind PutCounterAll (Satsuki)
    never fire."""
    assert ("counter_distribute", "you", "") in _idents("Cathars' Crusade")
    assert ("counter_distribute", "you", "") in _idents("Verdurous Gearhulk")
    assert ("counter_distribute", "you", "") in _idents("Bramblewood Paragon")
    assert "counter_distribute" not in _keys("Endless One")
    assert "counter_distribute" not in _keys("Satsuki, the Living Lore")


# ── Batch 12: §F reference / condition lanes ─────────────────────────────────


def test_superfriends_matters_condition_site_only():
    """CR 306.5: a condition-site Planeswalker filter with controller not
    Opponent fires (Historian of Zhalfir's ControlsType, Arisen Gorgon's
    IsPresent) and the named-planeswalker activation gate reads typed
    (Companion of the Trials' YouControlNamedPlaneswalker — a logged add
    over live's projection); a target-matching removal condition
    (Chandra's Defeat — TargetMatchesFilter), a PW-removal effect target
    (Hero's Downfall), and BEING a planeswalker (Jace Beleren) never
    fire."""
    assert ("superfriends_matters", "you", "") in _idents("Historian of Zhalfir")
    assert ("superfriends_matters", "you", "") in _idents("Arisen Gorgon")
    assert ("superfriends_matters", "you", "") in _idents("Companion of the Trials")
    assert "superfriends_matters" not in _keys("Chandra's Defeat")
    assert "superfriends_matters" not in _keys("Hero's Downfall")
    assert "superfriends_matters" not in _keys("Jace Beleren")


def test_superfriends_matters_skips_whenever_event_recipients():
    """A WheneverEvent damage-watcher condition carries the combat-damage
    RECIPIENT list Or[Player, Planeswalker] (an attacked opposing
    planeswalker per CR 506.2) — that is event plumbing, not a
    planeswalker-you-control reference. The scan stops at WheneverEvent
    subtrees (rules-lawyer-adjudicated blocking, batch 12); Hunter's
    Insight and Flitterwing Nuisance stay out while the condition-site
    positives above keep firing."""
    assert "superfriends_matters" not in _keys("Hunter's Insight")
    assert "superfriends_matters" not in _keys("Flitterwing Nuisance")


def test_commander_matters_filter_property_not_metadata():
    """CR 903.3: the IsCommander filter property fires (Bastion Protector,
    Anara); the card-level is_commander/brawl_commander metadata flags are
    NEVER read — a legendary creature with no commander reference (Visara)
    stays out (eligibility is not caring)."""
    assert ("commander_matters", "you", "") in _idents("Bastion Protector")
    assert ("commander_matters", "you", "") in _idents("Anara, Wolvid Familiar")
    assert "commander_matters" not in _keys("Visara the Dreadful")


def test_big_hand_makers_modes_and_reducer_quirk():
    """CR 402.2: the NoMaximumHandSize static mode (Reliquary Tower,
    Kruphix) and the MaximumHandSize{SetTo/AdjustedBy} family fire — the
    reducers (Cursed Rack, Gnat Miser) are kept by live's mirror parity
    (the spec's mandatory reducer-quirk check; logged for a future lane
    split); Time Stop's reminder-only "maximum hand size" is stripped and
    never fires."""
    assert ("big_hand_makers", "you", "") in _idents("Reliquary Tower")
    assert ("big_hand_makers", "you", "") in _idents("Kruphix, God of Horizons")
    assert ("big_hand_makers", "you", "") in _idents("Cursed Rack")
    assert ("big_hand_makers", "you", "") in _idents("Gnat Miser")
    assert "big_hand_makers" not in _keys("Time Stop")


def test_big_hand_matters_your_hand_operand():
    """CR 402.2: a HandSize operand reading YOUR hand fires — the dynamic
    P/T pair (Maro, Psychosis Crawler), the threshold condition (Akki
    Underling), and Body of Knowledge fires BOTH halves; a "discards down
    to"-style end-the-turn card (Time Stop) and the opponent-hand reducer
    (Gnat Miser — [P5], no your-hand operand) never fire matters."""
    assert ("big_hand_matters", "you", "") in _idents("Maro")
    assert ("big_hand_matters", "you", "") in _idents("Psychosis Crawler")
    assert ("big_hand_matters", "you", "") in _idents("Akki Underling")
    bok = _keys("Body of Knowledge")
    assert {"big_hand_matters", "big_hand_makers"} <= bok
    assert "big_hand_matters" not in _keys("Time Stop")
    assert "big_hand_matters" not in _keys("Gnat Miser")


def test_vehicles_matter_arms_and_membership_gates():
    """CR 301.7 + 702.122: the Crews trigger (Gearshift Ace), the
    vehicle-subtype static (Aeronaut Admiral; Depala's "Each Vehicle you
    control" — a structural add over live's plural-literal miss, logged),
    and the Vehicle graveyard-recursion (Greasefang) fire; a card that IS
    a Vehicle never fires from its own nodes — BecomesCrewed/SelfRef
    (Ghost Ark) and a plain Vehicle (Smuggler's Copter) stay out."""
    assert ("vehicles_matter", "you", "") in _idents("Gearshift Ace")
    assert ("vehicles_matter", "you", "") in _idents("Aeronaut Admiral")
    assert ("vehicles_matter", "you", "") in _idents("Depala, Pilot Exemplar")
    assert ("vehicles_matter", "you", "") in _idents("Greasefang, Okiba Boss")
    assert "vehicles_matter" not in _keys("Ghost Ark")
    assert "vehicles_matter" not in _keys("Smuggler's Copter")


def test_vehicles_matter_bucket_b_synth_tail():
    """Tier-1 (ADR-0036/0037 fold): Anchor to Reality's "Equipment or
    Vehicle card" tutor is the residual crew/Vehicle idiom arms a-c miss —
    the deleted ``VEHICLES_MATTER_REGEX`` mirror relocated to a bucket-B
    ``tree_synthesis`` arm, gap-gated against the same three arms."""
    assert ("vehicles_matter", "you", "") in _idents("Anchor to Reality")


# ── Batch 12: batch-11 adjudicated follow-ups ────────────────────────────────


def test_typed_spellcast_static_cost_reduction_arm():
    """Follow-up (a): the STATIC tribal cost-reduction form (CR 601.2f
    couples the discount to the cast event) — a ModifyCost{Reduce} whose
    spell_filter carries a vocab creature subtype and whose affected is
    your cards emits typed_spellcast with the subject (Goblin Warchief);
    the self-discount (Avatar of Woe — affected SelfRef, no spell_filter
    subtype) never fires; the existing cost_reduction firing is
    unchanged."""
    assert ("typed_spellcast", "you", "Goblin") in _idents("Goblin Warchief")
    assert ("cost_reduction", "you", "") in _idents("Goblin Warchief")
    assert "typed_spellcast" not in _keys("Avatar of Woe")


def test_tap_down_defending_player_and_gated_target_player():
    """Follow-up (b): SetTapState{Tap} onto a DefendingPlayer-controlled
    filter fires unconditionally (Master of Diversion, Sidar Jabari — CR
    506.2 makes it opponent-directed) and a TargetPlayer-controlled filter
    fires ONLY under an attack/damage-trigger unit (Hammers of Moradin);
    the one-shot/activated TargetPlayer sweeps (Sleep, Dawnglare Invoker)
    are the genuine supplement tail and never fire."""
    assert ("tap_down", "opponents", "") in _idents("Master of Diversion")
    assert ("tap_down", "opponents", "") in _idents("Sidar Jabari")
    assert ("tap_down", "opponents", "") in _idents("Hammers of Moradin")
    assert "tap_down" not in _keys("Sleep")
    assert "tap_down" not in _keys("Dawnglare Invoker")


def test_tap_down_target_opponent_and_skip_next_step():
    """ADR-0037/0038 W3: ``TargetOpponent`` ("tap all creatures TARGET
    OPPONENT controls" — Assassin Gauntlet) joins the always-opponent set
    unconditionally; ``SkipNextStep{step: Untap}`` (a phase v0.20 addition,
    CR 502.3) is a DISTINCT effect from SetTapState — "each opponent skips
    their next untap step" (Brine Elemental) fires via the wrapper's own
    ``player_scope`` actor, not the effect's own ``target`` (which reads
    Controller, the per-opponent iteration variable)."""
    assert ("tap_down", "opponents", "") in _idents("Assassin Gauntlet")
    assert ("tap_down", "opponents", "") in _idents("Brine Elemental")


def test_tap_down_opponents_turn_mis_stamp():
    """ADR-0037/0038 W3: phase mis-stamps ``controller: You`` on "at the
    beginning of combat on each OPPONENT'S TURN, tap target creature that
    player controls" (Citadel Siege's Dragons chapter — the SAME
    per-iteration-variable mis-stamp class as RevealUntil's [P28] "their
    library" bug), recovered via the unit's own raw text."""
    assert ("tap_down", "opponents", "") in _idents("Citadel Siege")


def test_tap_down_parent_target_clause_fallback_and_self_tap_no_fire():
    """ADR-0037/0038 W3: a ``ParentTarget`` sub-effect whose real target
    filter lives on an earlier SIBLING in the SequentialSibling chain
    ("tap target creature an opponent controls and put a stun counter on
    it" — Mind Spiral) is read via the DIRECT owning wrapper's own
    ISOLATED clause text, narrowed to the sentence naming "tap". Dread
    Cacodemon's "destroy all creatures your opponents control, then tap
    all OTHER creatures YOU control" must NOT fire — the tap's own
    controller is You and its DIRECT owning wrapper carries no isolated
    clause text of its own, so the unrelated sibling "opponents control"
    phrase (attributable to the destroy, not the tap) is never consulted
    (a corpus-verified over-fire class this sentence-isolation fixes)."""
    assert ("tap_down", "opponents", "") in _idents("Mind Spiral")
    assert "tap_down" not in _keys("Dread Cacodemon")


def test_tap_down_triggering_player_opponent_scoped_watcher():
    """ADR-0037/0038 W3: a trigger whose OWN watched-object filter is
    opponent-scoped (Mana Web: "whenever a land AN OPPONENT controls is
    tapped for mana, tap all lands THAT PLAYER controls" — a
    ``controller: You`` mis-stamp on the SAME idiom War's Toll's
    ``TriggeringPlayer`` carries structurally) fires via
    ``valid_card.controller == "Opponent"`` on the trigger unit — the
    bound "you"/"that player" IS that opponent by definition."""
    assert ("tap_down", "opponents", "") in _idents("Mana Web")


def test_tap_down_per_opponent_multi_target_and_no_residue_fallback():
    """ADR-0037/0038 W3: a "for each opponent, tap up to one target
    creature THAT PLAYER controls" loop reads structurally two ways —
    Juvenile Mist Dragon's wrapper carries a real ``multi_target.max``
    scaled by opponent COUNT (``PlayerCount`` qty filtered to
    ``Opponent`` — CR 506.4's "each opponent" default), while Omega,
    Heartless Evolution's Wave Cannon drops the per-opponent loop
    structure ENTIRELY (a genuine no-residue class phase's own parser
    swallows — the SAME class dig_until's own no-residue fallback
    recovers), caught only by the tightly-scoped whole-card idiom match."""
    assert ("tap_down", "opponents", "") in _idents("Juvenile Mist Dragon")
    assert ("tap_down", "opponents", "") in _idents("Omega, Heartless Evolution")


def test_tap_down_skip_next_step_detriment_directed_targeting():
    """ADR-0038 deferral sweep unit 5 (Dan's detriment-directed-targeting
    principle, 2026-07-10): Yosei, the Morning Star's "target player skips
    their next untap step" is a bare targeted-player ``SkipNextStep``
    recipient (tag ``Player``, not one of the existing Opponent/
    DefendingPlayer/TriggeringPlayer-in-attack-trigger arms) — opponent-
    directed for signal purposes via ``detriment_directed_scope`` even
    though CR 603.3d lets the controller legally target themself. Avizoa's
    "You skip your next untap step" as a self-paid activation COST for a
    pump (``target=Controller()``) is the no-fire control: a genuinely
    self-directed, non-detrimental-in-context shape that
    ``detriment_directed_scope`` correctly reads as "you", never
    "opponents"."""
    assert ("tap_down", "opponents", "") in _idents("Yosei, the Morning Star")
    assert "tap_down" not in _keys("Avizoa")


def test_tap_down_casting_restriction_oracle_fallback():
    """ADR-0037/0038 W3: Delirium's "Cast this spell only during an
    opponent's turn" restriction is a card-level ``casting_restrictions``
    field with no ability/wrapper description anywhere to carry it — the
    ``controller: You`` mis-stamped "Tap target creature that player
    controls" clause is recovered via the LAST-RESORT whole-card oracle
    fallback (single-ability spell, so no sibling-clause misattribution
    risk — see ``_tap_owner_text``)."""
    assert ("tap_down", "opponents", "") in _idents("Delirium")


# ADR-0038 W3 batch 2 unit 8 (the tap_down measured-residual follow-up):
# two ALREADY-correct cw_only gains, newly pinned (both were already firing
# before this batch, via precedents documented at their own arm's call
# site — Icingdeath via the GrantTrigger-in-a-created-Token arm, Kang
# Dynasty via the "for each opponent, tap ... TargetPlayer controls"
# multi_target arm), a genuine last-resort recovery, and an adjudicated
# shed.
def test_tap_down_grant_trigger_in_created_token():
    """Icingdeath, Frost Tyrant's death trigger creates an Equipment token
    whose OWN static_abilities nests a GrantTrigger ("whenever equipped
    creature attacks, tap target creature defending player controls") —
    the SAME GrantTrigger-in-Attacks-trigger arm Grasp of the Hieromancer
    already reads, just three levels deeper (Token.static_abilities ->
    GrantTrigger.trigger.execute.effect)."""
    assert ("tap_down", "opponents", "") in _idents("Icingdeath, Frost Tyrant")


def test_tap_down_saga_chapter_per_opponent_target_player():
    """Kang Dynasty's Saga chapters I/II ("For each opponent, tap up to
    one target creature that player controls") carry the SetTapState's
    TargetPlayer controller with a multi_target.max scaled by opponent
    COUNT (PlayerCount{filter: Opponent}) — the same per-opponent
    multi_target arm Juvenile Mist Dragon already reads."""
    assert ("tap_down", "opponents", "") in _idents("Kang Dynasty")


def test_tap_down_stickers_mechanic_text_idiom():
    """Unhinged Beast Hunt's Stickers-mechanic ability ("Whenever ~
    attacks, tap each creature an opponent controls with the same power
    and/or same toughness as ~") defeats phase's parser entirely (an
    Unimplemented "unknown"-name residue — the {TK} placeholder-pip
    syntax, no SetTapState node anywhere in the tree) — last-resort
    whole-card text idiom, corpus-verified singleton (the only
    commander-legal card with this exact phrase)."""
    assert ("tap_down", "opponents", "") in _idents("Unhinged Beast Hunt")


def test_tap_down_excludes_self_targeted_tap_as_removal_cost():
    """Teferi Akosa of Zhalfir's loyalty -3 ("Tap any number of untapped
    creatures YOU CONTROL. When you do, shuffle target nonland permanent
    an opponent controls...") taps YOUR OWN creatures as a COST enabling
    an unrelated removal effect (the shuffled permanent, not the tapped
    creatures, is opponent-controlled) — the typed ``controller: You``
    gate on the SetTapState's own target already correctly excludes this;
    legacy's category-based "any tap effect credits tap_down regardless
    of direction" read is a miscredit, adjudicated as a SHED (not a
    genuine gap)."""
    assert "tap_down" not in _keys("Teferi Akosa of Zhalfir")


# ── Batch 13: §A pure Scryfall-keyword field-lookups ─────────────────────────


def test_companion_keyword_bearer_vs_doctors_companion():
    """CR 702.139: the Companion keyword fires the deckbuild-constraint lane
    (Lurrus); "Doctor's companion" is the PARTNER family (Rose Tyler) and
    deliberately never fires companion_keyword."""
    assert ("companion_keyword", "you", "") in _idents("Lurrus of the Dream-Den")
    ks = _keys("Rose Tyler")
    assert "companion_keyword" not in ks
    assert "partner_background" in ks


def test_has_banding_bearer_vs_granter_reverse_trap():
    """CR 702.22: the Banding keyword bearer fires (Timber Wolves); the
    keyword-LESS banding GRANTER (Baton of Morale — AddKeyword{Banding})
    must NOT fire the membership lane (the batch-13 reverse trap)."""
    assert ("has_banding", "you", "") in _idents("Timber Wolves")
    assert "has_banding" not in _keys("Baton of Morale")


def test_has_dash_sole_keyword_producer():
    """CR 702.109: the Dash keyword array is the SOLE producer (Zurgo
    Bellstriker); a haste granter (Goblin Motivator) never fires."""
    assert ("has_dash", "you", "") in _idents("Zurgo Bellstriker")
    assert "has_dash" not in _keys("Goblin Motivator")


def test_has_enlist_keyword_bearer():
    """CR 702.154: the Enlist bearer fires (Argivian Cavalier); a tapper
    outlet that merely taps creatures (Springleaf Drum) never fires."""
    assert ("has_enlist", "you", "") in _idents("Argivian Cavalier")
    assert "has_enlist" not in _keys("Springleaf Drum")


def test_specialize_matters_digital_lane():
    """DD4 (digital supplement): the Specialize bearer fires (Gale — the
    Historic Brawl lane); "Choose a background" (Faceless One) routes to
    the partner lane, never specialize."""
    assert ("specialize_matters", "you", "") in _idents("Gale, Conduit of the Arcane")
    ks = _keys("Faceless One")
    assert "specialize_matters" not in ks
    assert "partner_background" in ks


def test_alt_cost_keyword_three_strings():
    """CR 118/601 + 702.190a/.188a/.187a-c: Sneak / Web-slinging / Mayhem
    bearers fire; a TEXTUAL alternative cost (Force of Will) and Dash (a
    separate lane) never fire."""
    for name in (
        "Elektra, Daughter of the Hand",
        "Spider-UK",
        "Green Goblin, Back for More",
    ):
        assert ("alt_cost_keyword", "you", "") in _idents(name), name
    assert "alt_cost_keyword" not in _keys("Force of Will")
    assert "alt_cost_keyword" not in _keys("Zurgo Bellstriker")


def test_partner_background_family_and_negatives():
    """CR 702.124/.124a/.124k/.124m/.124i: Partner (Thrasios), Doctor's
    companion (Rose Tyler), Choose a Background (Abdel Adrian) all fire;
    Companion (Lurrus) is the separate lane and an actual Background CARD
    (Raised by Giants — the lane is the commander side) never fires."""
    for name in ("Thrasios, Triton Hero", "Rose Tyler", "Abdel Adrian, Gorion's Ward"):
        assert ("partner_background", "you", "") in _idents(name), name
    assert "partner_background" not in _keys("Lurrus of the Dream-Den")
    assert "partner_background" not in _keys("Raised by Giants")


# ── Batch 13: §B keyword + top-up lanes ──────────────────────────────────────


def test_madness_matters_keyword_and_grant_anchor():
    """CR 702.35: the Madness bearer (Anje's Ravager), the keyword-less
    "has madness" GRANTER (Falkenrath Gorger — v0.9.0 FAILED static, raw
    survives) and the "if it has madness" payoff (Anje Falkenrath) fire;
    a discard-exile-play engine with no madness text (Containment
    Construct) never fires."""
    assert ("madness_matters", "you", "") in _idents("Anje's Ravager")
    assert ("madness_matters", "you", "") in _idents("Falkenrath Gorger")
    assert ("madness_matters", "you", "") in _idents("Anje Falkenrath")
    assert "madness_matters" not in _keys("Containment Construct")


def test_affinity_type_keyword_and_castwith_static():
    """CR 702.41: the Affinity bearer (Qumulox) and the keyword-less
    granter's CastWithKeyword{Affinity} static (Tezzeret, Master of the
    Bridge) fire — subject stays "" (the type travels in serve prose);
    a generic cost reducer (Foundry Inspector) never fires."""
    assert ("affinity_type", "you", "") in _idents("Qumulox")
    assert ("affinity_type", "you", "") in _idents("Tezzeret, Master of the Bridge")
    assert "affinity_type" not in _keys("Foundry Inspector")


def test_scavenge_fuel_keyword_and_addkeyword_granter():
    """CR 702.97: the Scavenge bearer (Dreg Mangler) and the clean
    AddKeyword{Scavenge} granter (Varolz) fire; a graveyard hoser
    (Deathrite Shaman) never fires."""
    assert ("scavenge_fuel", "you", "") in _idents("Dreg Mangler")
    assert ("scavenge_fuel", "you", "") in _idents("Varolz, the Scar-Striped")
    assert "scavenge_fuel" not in _keys("Deathrite Shaman")


def test_has_soulbond_keyword_and_reference_tail():
    """CR 702.95: the Soulbond bearer (Silverblade Paladin) and the
    1-card keyword-less reference (Flowering Lumberknot — condition-text
    only) fire; a support pairer (Together Forever) never fires."""
    assert ("has_soulbond", "you", "") in _idents("Silverblade Paladin")
    assert ("has_soulbond", "you", "") in _idents("Flowering Lumberknot")
    assert "has_soulbond" not in _keys("Together Forever")


def test_has_mutate_keyword_and_condition_tail_pins_gap():
    """CR 702.140: the Mutate bearer (Otrimi) and the "if it has mutate"
    condition payoff (Pollywog Symbiote) fire; Essence Symbiote (a genuine
    mutate payoff with a clean v0.9.0 Mutates trigger) is NOT in the live
    pop — the negative pins the parity boundary AND documents the gap
    (candidate adjudicated widen, not part of this port)."""
    assert ("has_mutate", "you", "") in _idents("Otrimi, the Ever-Playful")
    assert ("has_mutate", "you", "") in _idents("Pollywog Symbiote")
    assert "has_mutate" not in _keys("Essence Symbiote")


def test_has_ninjutsu_both_keywords_and_satoru():
    """CR 702.49: Ninjutsu (Higure), Commander ninjutsu (Yuriko) and the
    keyword-less granter's AddKeyword{Ninjutsu} static (Satoru Umezawa)
    fire; an unblockable enabler (Key to the City) never fires."""
    assert ("has_ninjutsu", "you", "") in _idents("Higure, the Still Wind")
    assert ("has_ninjutsu", "you", "") in _idents("Yuriko, the Tiger's Shadow")
    assert ("has_ninjutsu", "you", "") in _idents("Satoru Umezawa")
    assert "has_ninjutsu" not in _keys("Key to the City")


def test_has_undying_persist_keywords_grants_and_name_trap():
    """CR 702.93 (undying) / 702.79 (persist): the bearers (Butcher Ghoul,
    Puppeteer Clique), the AddKeyword granters (Mikaeus{Undying}, Cauldron
    of Souls{Persist}) fire; Persistent Petitioners (name-substring trap —
    both gates immune) never fires."""
    assert ("has_undying_persist", "you", "") in _idents("Butcher Ghoul")
    assert ("has_undying_persist", "you", "") in _idents("Puppeteer Clique")
    assert ("has_undying_persist", "you", "") in _idents("Mikaeus, the Unhallowed")
    assert ("has_undying_persist", "you", "") in _idents("Cauldron of Souls")
    assert "has_undying_persist" not in _keys("Persistent Petitioners")


def test_has_devour_keyword_and_token_profile_tail():
    """CR 702.82: the Devour bearer (Mycoloth) and the token-profile tail
    (Dragon Broodmother — token keywords carry {Devour: 2}) fire; a sac
    outlet (Viscera Seer) never fires."""
    assert ("has_devour", "you", "") in _idents("Mycoloth")
    assert ("has_devour", "you", "") in _idents("Dragon Broodmother")
    assert "has_devour" not in _keys("Viscera Seer")


def test_has_changeling_keyword_typed_reads_and_clone_negative():
    """CR 702.73: the Changeling bearer (Chameleon Colossus), the
    token-profile Changeling (Maskwood Nexus) and the AddAllCreatureTypes
    modification (Mistform Ultimus) fire; Clone (no changeling /
    every-creature-type text) never fires."""
    assert ("has_changeling", "you", "") in _idents("Chameleon Colossus")
    assert ("has_changeling", "you", "") in _idents("Maskwood Nexus")
    assert ("has_changeling", "you", "") in _idents("Mistform Ultimus")
    assert "has_changeling" not in _keys("Clone")


def test_myriad_grant_keyword_and_addkeyword_granters():
    """CR 702.116: the Myriad bearer (Herald of the Host), the
    AddKeyword{Myriad} granter (Blade of Selves) and the copy-EXCEPTION
    conferral (Muddle — "except it has myriad" rides the copy node's
    additional_modifications, CR 707.9a) fire; a nonlegendary copy-maker
    with no myriad (Helm of the Host) never fires."""
    assert ("myriad_grant", "you", "") in _idents("Herald of the Host")
    assert ("myriad_grant", "you", "") in _idents("Blade of Selves")
    assert ("myriad_grant", "you", "") in _idents("Muddle, the Ever-Changing")
    assert "myriad_grant" not in _keys("Helm of the Host")


# ── Batch 13: §C structural arms ─────────────────────────────────────────────


def test_boast_matters_typed_nodes_only():
    """CR 702.142: the KeywordAbilityActivated{Boast} trigger mode
    (Frenzied Raider) and the ModifyActivationLimit{keyword: boast} static
    (Birgi face record) fire; the BEARER (Varragoth → ported boast_makers)
    must NOT fire the payoff lane. The ModifyActivationLimit guard is
    keyword=="boast" (Wonder Man carries keyword "power-up")."""
    assert ("boast_matters", "you", "") in _idents("Frenzied Raider")
    assert ("boast_matters", "you", "") in _idents("Birgi, God of Storytelling")
    ks = _keys("Varragoth, Bloodsky Sire")
    assert "boast_matters" not in ks
    assert "boast_makers" in ks


def test_cascade_matters_typed_reads_and_multicascade_quirk():
    """CR 702.85: CastWithKeyword{Cascade} (Maelstrom Nexus), the "as you
    cascade" anchor (Averna) and the DELIBERATE multi-cascade-body quirk
    ("cascade, cascade" — Apex Devastator, ported as-is) fire; the
    single-cascade bearer (Bloodbraid Elf → cascade_makers) stays out."""
    assert ("cascade_matters", "you", "") in _idents("Maelstrom Nexus")
    assert ("cascade_matters", "you", "") in _idents("Averna, the Chaos Bloom")
    assert ("cascade_matters", "you", "") in _idents("Apex Devastator")
    ks = _keys("Bloodbraid Elf")
    assert "cascade_matters" not in ks
    assert "cascade_makers" in ks


def test_convoke_matters_cast_trigger_anchor_only():
    """CR 702.51: a cast_spell trigger whose sentence carries "convoke"
    fires (Kasla — herself a Convoke bearer; Joyful Stormsculptor); the
    bearer (Chord of Calling → convoke_makers) and the CastWithKeyword
    granter (Chief Engineer → spell_keyword_grant, verified live) never
    fire the payoff lane."""
    assert ("convoke_matters", "you", "") in _idents("Kasla, the Broken Halo")
    assert ("convoke_matters", "you", "") in _idents("Joyful Stormsculptor")
    ks = _keys("Chord of Calling")
    assert "convoke_matters" not in ks
    assert "convoke_makers" in ks
    cks = _keys("Chief Engineer")
    assert "convoke_matters" not in cks
    assert "spell_keyword_grant" in cks


def test_curse_matters_subtype_reads_and_mirror():
    """CR 205.3h: the Curse trigger-subject read (Lynde), the Curse
    effect-subject read (Witchbane Orb) and the kept mirror (Curse of
    Misfortunes — search filter still dropped in v0.9.0, [P11] family)
    fire; MEMBERSHIP stays out — Cruel Reality (an Aura Curse CARD)
    never fires."""
    assert ("curse_matters", "you", "") in _idents("Lynde, Cheerful Tormentor")
    assert ("curse_matters", "you", "") in _idents("Witchbane Orb")
    assert ("curse_matters", "you", "") in _idents("Curse of Misfortunes")
    assert "curse_matters" not in _keys("Cruel Reality")


def test_foretell_matters_foretold_predicate_only():
    """CR 702.143: the typed Foretold-predicate read fires (Niko Defies
    Destiny — the property nests inside the count operand's filter);
    bearers AND granters/payoff-triggers ride the PORTED foretell_makers
    (Ranar, Glorious Protector) and never fire the matters lane."""
    assert ("foretell_matters", "you", "") in _idents("Niko Defies Destiny")
    # Ranar (keyword-less payoff-trigger granter) rides foretell_makers
    # live-side via the projection marker — a documented pre-existing b5
    # live_only residue crosswalk-side; the batch-13 gate is that he never
    # fires the matters lane.
    assert "foretell_matters" not in _keys("Ranar the Ever-Watchful")
    gks = _keys("Glorious Protector")
    assert "foretell_matters" not in gks
    assert "foretell_makers" in gks


def test_keyword_soup_per_site_count_and_same_true_absorb():
    """CR 702: >=5 DISTINCT evergreen AddKeyword mods within ONE ability
    site fire (Odric's 13 under one trigger execute; Chromanticore's bestow
    static's 5); the "same is true" absorb arm catches the collapsed
    keyword-copy idiom (Urborg Scavengers); a 4-keyword equipment (Sword
    of Vengeance) and a single conditional grant (Lightwalker) never
    fire. Cairn Wanderer is a Changeling whose keywords are CONDITIONAL on
    graveyard contents ("has flying as long as a creature with flying is in
    a graveyard…"); at the v0.15.0 pin phase re-parses that idiom out of the
    flat >=5-AddKeyword shape, so it fires has_changeling (it IS a changeling)
    but no longer keyword_soup — an acceptable churn, the lane's positive
    coverage stays on Odric/Chromanticore/Urborg."""
    assert ("keyword_soup", "you", "") in _idents("Odric, Lunarch Marshal")
    cks = _keys("Cairn Wanderer")
    assert "has_changeling" in cks
    assert "keyword_soup" not in cks  # v0.15.0 re-parse (conditional-GY-keyword)
    assert ("keyword_soup", "you", "") in _idents("Chromanticore")
    assert ("keyword_soup", "you", "") in _idents("Urborg Scavengers")
    assert "keyword_soup" not in _keys("Sword of Vengeance")
    assert "keyword_soup" not in _keys("Lightwalker")


def test_keyword_soup_same_true_scoped_to_granting_site():
    """Roshan, Hidden Magister's "The same is true" sentence extends an
    Assassin SUBTYPE grant (CR 205.1b/205.3m) — his only keyword grant is
    menace. The same-true anchor must read the granting UNIT's own text,
    never the whole kept oracle (rules-lawyer-adjudicated blocking, batch
    13; parity-verified — all 22 banked live members still fire)."""
    assert "keyword_soup" not in _keys("Roshan, Hidden Magister")


# ── Batch 13: §D kept-mirror ports ───────────────────────────────────────────


def test_island_matters_mirror():
    """CR 702.14: the pinned ISLAND_MATTERS_REGEX fires (Dandân); an
    islandwalk BEARER (Segovian Leviathan — island_MAKERS material)
    never fires the matters lane."""
    assert ("island_matters", "you", "") in _idents("Dandân")
    assert "island_matters" not in _keys("Segovian Leviathan")
    # RETRACTION (adjudicated b13): Zhou Yu IS present in phase card-data
    # v0.9.0 and fires the mirror — the implement-time "absent entirely /
    # genuinely phase-only" claim was a false provenance lookup.
    assert ("island_matters", "you", "") in _idents("Zhou Yu, Chief Commander")


def test_poison_matters_mirror_scope_opponents():
    """CR 122 + 704.5c: the "poison counter" reference mirror fires scope
    "opponents" — INCLUDING poison-givers that spell it out (Caress of
    Phyrexia, Vraska — live behavior, ported byte-identically); a
    reminder-only Infect bearer (Glistener Elf) fires only the ported
    poison_makers."""
    assert ("poison_matters", "opponents", "") in _idents("Caress of Phyrexia")
    assert ("poison_matters", "opponents", "") in _idents("Vraska, Betrayal's Sting")
    gks = _keys("Glistener Elf")
    assert "poison_matters" not in gks
    assert "poison_makers" in gks


def test_suspend_matters_mirror_breadth_and_boundary():
    """CR 702.62: the mirror deliberately fires bearers (un-parenthesized
    "Suspend 4—{1}{U}" survives stripping — Ancestral Vision, Jhoira),
    time-counter engines (As Foretold), Vanishing (Aven Riftwatcher) and
    Impending (Overlord of the Mistmoors) — breadth intended; "suspended
    card" does NOT match \\bsuspend\\b (Clockspinning — the sharpest
    boundary) and Time Warp never fires."""
    for name in (
        "Ancestral Vision",
        "As Foretold",
        "Jhoira of the Ghitu",
        "Aven Riftwatcher",
        "Overlord of the Mistmoors",
    ):
        assert ("suspend_matters", "you", "") in _idents(name), name
    assert "suspend_matters" not in _keys("Clockspinning")
    assert "suspend_matters" not in _keys("Time Warp")


def test_keyword_tribe_subject_carrying_mirror():
    """CR 109.3 + 702: the byte-identical _detect_keyword_tribe producer
    re-runs per-clause, emitting the capitalized keyword SUBJECT (the
    (key, scope, subject) triple is LOAD-BEARING): Sephara → Flying, Fynn
    → Deathtouch (cross-lane: also poison_matters), Isperia → Flying via
    the tutor pattern; a SUBTYPE tribe (Goblin King) and anti-tribe
    removal with no qualifier (Whirlwind) never fire."""
    assert ("keyword_tribe", "you", "Flying") in _idents("Sephara, Sky's Blade")
    fyn = _idents("Fynn, the Fangbearer")
    assert ("keyword_tribe", "you", "Deathtouch") in fyn
    assert ("poison_matters", "opponents", "") in fyn
    assert ("keyword_tribe", "you", "Flying") in _idents("Isperia the Inscrutable")
    assert "keyword_tribe" not in _keys("Goblin King")
    assert "keyword_tribe" not in _keys("Whirlwind")


# ── Batch 14: the first structural-remainder batch ───────────────────────────


def _confidences(name: str, key: str) -> set[str]:
    sigs = extract_crosswalk_signals(_tree(name), keywords=_kw(name))
    return {s.confidence for s in sigs if s.key == key}


def test_type_matters_mirror_subjects_are_load_bearing():
    """CR 205.3 / 109.3: the four byte-identical kept producers emit the
    vocab-validated SUBJECT — Magda's "Other Dwarves you control"
    (IGNORECASE is load-bearing), Kaalia's _TRIBE_LIST_RE hand-drop,
    Lovisa's _MULTI_TRIBE_HEAD_RE three-tribe anthem."""
    assert ("type_matters", "you", "Dwarf") in _idents("Magda, Brazen Outlaw")
    kaalia = _idents("Kaalia of the Vast")
    for sub in ("Angel", "Demon", "Dragon"):
        assert ("type_matters", "you", sub) in kaalia, sub
    lovisa = _idents("Lovisa Coldeyes")
    for sub in ("Barbarian", "Warrior", "Berserker"):
        assert ("type_matters", "you", sub) in lovisa, sub


def test_type_matters_structural_count_and_token_cross_open():
    """Krenko fires Goblin HIGH via the typed count operand
    (Ref→ObjectCount filter, the structural arm) AND the token cross-open
    (a LOW that dedupes under the HIGH ident). ADR-0038 W4: Krenko's own
    Goblin-token engine is ALSO a go-wide creature payoff
    (``structural_token_maker_type_subjects`` → ``_type_matters_go_wide``),
    so its OTHER own-type-line class tribe (Warrior — CLASS_TRIBES) now
    surfaces too, LOW, matching legacy's own cross-open (CR 205.3)."""
    idents = _idents("Krenko, Mob Boss")
    assert ("type_matters", "you", "Goblin") in idents
    assert ("type_matters", "you", "Warrior") in idents
    assert _confidences("Krenko, Mob Boss", "type_matters") == {"high", "low"}


def test_type_matters_nested_trigger_static_def_arm_b():
    """ADR-0038 W4: Gempalm Sorcerer's "When you cycle this card, Wizard
    creatures gain flying until end of turn." nests its Typed(Wizard)
    ``affected`` filter on a static-ability DEF buried inside the
    TRIGGER's own ``GenericEffect.static_abilities`` — the decorated
    concept's node anchor is the leaf ``AddKeyword`` modification, which
    carries no filter field at all. ``structural_type_subjects`` now walks
    :func:`iter_static_defs` (cycle-safe deep descent) instead of a bare
    ``unit.origin == "static"`` gate, so this HIGH structural Arm-B read
    fires (CR 205.3)."""
    idents = _idents("Gempalm Sorcerer")
    assert ("type_matters", "you", "Wizard") in idents
    assert _confidences("Gempalm Sorcerer", "type_matters") == {"high"}


def test_type_matters_go_wide_static_def_pump_any_origin():
    """ADR-0038 W4: Balmor, Battlemage Captain's "Whenever you cast an
    instant or sorcery spell, creatures you control get +1/+0 and gain
    trample until end of turn." is a TRIGGER-conferred team anthem (a
    pump + grant_keyword static DEF nested in the trigger's own effect,
    not a top-level continuous ability) over the GENERIC creature filter.
    ``_type_matters_go_wide`` reads it via :func:`iter_static_defs`
    (origin-agnostic, unlike ``_creatures_matter``'s own
    ``unit.statics``-only scan, which stays narrower since
    ``creatures_matter`` is Stage-4 RESIDUAL) — Balmor's own class tribe
    (Wizard — CLASS_TRIBES) now surfaces LOW alongside its unconditional
    race tribe (Bird — TRIBAL_SUBTYPES). CR 205.3/613.4."""
    idents = _idents("Balmor, Battlemage Captain")
    assert ("type_matters", "you", "Bird") in idents
    assert ("type_matters", "you", "Wizard") in idents
    assert _confidences("Balmor, Battlemage Captain", "type_matters") == {"low"}


def test_type_matters_go_wide_token_maker_cross_open_doomed_traveler():
    """ADR-0038 W4: Doomed Traveler's "When ~ dies, create a 1/1 white
    Spirit creature token." makes a Spirit token — a creature-type token
    MAKER (:func:`structural_token_maker_type_subjects`) is itself a
    go-wide creature payoff (mirrors legacy ``_signals_ir``'s line ~11394
    "token-maker -> creatures_matter" cross-open, CR 111.2/205.3), so
    Doomed Traveler's own class tribe (Soldier — CLASS_TRIBES) now
    surfaces LOW alongside its token-profile membership (Spirit)."""
    idents = _idents("Doomed Traveler")
    assert ("type_matters", "you", "Soldier") in idents
    assert ("type_matters", "you", "Spirit") in idents
    assert _confidences("Doomed Traveler", "type_matters") == {"low"}


def test_type_matters_gates_no_subject_no_signal():
    """A generic anthem (Glorious Anthem) captures no subject; a Food-token
    maker's profile is NON_CREATURE_TOKEN-denied (Gilded Goose never mints
    a Food subject — CR 111.10 / 205.3g; its Bird membership row is the
    separate own-subtype arm)."""
    assert "type_matters" not in _keys("Glorious Anthem")
    goose = _idents("Gilded Goose")
    assert ("type_matters", "you", "Food") not in goose
    assert ("type_matters", "you", "Bird") in goose


def test_type_matters_cost_scan_sacrifice_a_tribe():
    """ADR-0038 W5: Goblin Grenade's "As an additional cost to cast this
    spell, sacrifice a Goblin." carries its subtype on the ``Sacrifice``
    COST node's own ``target`` filter — a cost-shaped node ``unit.costs``
    now scans the SAME way as ``unit.effects`` (CR 601.2h / 701.21).
    HIGH confidence (a subject-carrying structural read, not the LOW
    go-wide membership floor)."""
    idents = _idents("Goblin Grenade")
    assert ("type_matters", "you", "Goblin") in idents
    assert _confidences("Goblin Grenade", "type_matters") == {"high"}


def test_type_matters_go_wide_combat_keyword_exert():
    """ADR-0038 W5: Ahn-Crop Crasher's "You may exert this creature as it
    attacks..." carries no board-state Typed filter at all (its target
    can't block THIS turn, scope any) — neither the count-operand nor the
    static-def go-wide arms can reach it. The printed Exert keyword (CR
    701.43) is the only anchor, mirroring legacy's ``_IR_KEYWORD_MAP``
    combat-keyword block (which routes exert straight to
    ``attack_matters``): Ahn-Crop Crasher's own class tribe (Warrior)
    surfaces LOW alongside its unconditional race tribe (Minotaur)."""
    idents = _idents("Ahn-Crop Crasher")
    assert ("type_matters", "you", "Minotaur") in idents
    assert ("type_matters", "you", "Warrior") in idents
    assert _confidences("Ahn-Crop Crasher", "type_matters") == {"low"}


def test_type_matters_go_wide_combat_keyword_bushido():
    """ADR-0038 W5: Sokenzan Spellblade's printed Bushido keyword (CR
    702.45) opens the SAME combat-keyword go-wide tell as exert — its
    class tribes (Samurai/Shaman — one of which rides TRIBAL_SUBTYPES'
    unconditional race-tribe arm, the other CLASS_TRIBES' go-wide gate)
    surface alongside its own race tribe (Ogre)."""
    idents = _idents("Sokenzan Spellblade")
    assert ("type_matters", "you", "Ogre") in idents
    assert ("type_matters", "you", "Samurai") in idents
    assert ("type_matters", "you", "Shaman") in idents


def test_type_matters_go_wide_rampage_shed_not_ported():
    """ADR-0038 W5: Elvish Berserker's Rampage 1 ("...it gets +1/+1... for
    each creature blocking it") is a DELIBERATE shed, not a gap — legacy's
    go-wide firing for this class traces to old-IR's ``_board_count_
    markers``/``_is_generic_board_filter`` (project.py), which forces
    controller "you" on ANY own-board count operand REGARDLESS of
    restricting properties (its own docstring: "controller you/unspecified
    passes"), so a creatures-BLOCKING-it count (``BlockingSource``,
    controller=None in the REAL phase substrate) is wrongly treated as a
    "creatures you control" care. This is the SAME "bare 'creature'
    mention count, not a structural cares-about read" floor
    ``_creatures_matter``'s own docstring already adjudicates as
    live_only, NOT ported, for the identical reason (CR 702.23/604.3).
    Elvish Berserker's own RACE tribe (Elf, TRIBAL_SUBTYPES) still
    surfaces unconditionally; its CLASS tribe (Berserker) must NOT."""
    idents = _idents("Elvish Berserker")
    assert ("type_matters", "you", "Elf") in idents
    assert ("type_matters", "you", "Berserker") not in idents


def test_type_matters_static_def_modification_count_operand_or_subtypes():
    """ADR-0038 W5: Bearded Axe's "Equipped creature gets +1/+1 for each
    Dwarf, Equipment, and/or Vehicle you control." carries its ``Or``-of-
    subtypes filter on the leaf ``AddDynamicPower`` MODIFICATION's own
    ``value`` field, not the static-def's ``affected`` (the generic
    "equipped creature" anchor, CR 301.5c) — ``structural_type_subjects``
    now scans each static-def's ``modifications`` list with the SAME
    ``count_operand_filter`` read the top-level effect scan uses."""
    idents = _idents("Bearded Axe")
    assert ("type_matters", "you", "Dwarf") in idents
    assert _confidences("Bearded Axe", "type_matters") == {"high"}


def test_type_matters_nested_grant_ability_definition_target():
    """ADR-0038 W5: Wolfhunter's Quiver's second granted ability ("{T}: ~
    deals 3 damage to target Werewolf creature.") carries its subtype on
    the GRANTED ability's OWN ``target`` field, buried inside
    ``GrantAbility.definition.effect`` — the static-def's own ``affected``
    stays the generic "equipped creature" anchor (CR 301.5c) and the
    top-level ``modifications`` list carries no filter of its own.
    ``structural_type_subjects`` reads it via :func:`effect_filter` over
    each ``iter_typed_nodes``-reached ``GrantAbility`` node's
    ``definition.effect`` (the SAME idiom
    :func:`has_structural_power_tap_engine` already uses)."""
    idents = _idents("Wolfhunter's Quiver")
    assert ("type_matters", "you", "Werewolf") in idents
    assert _confidences("Wolfhunter's Quiver", "type_matters") == {"high"}


def test_type_matters_modify_cost_spell_filter_multi_tribe():
    """ADR-0038 W5: The Destined Warrior's "Cleric, Rogue, Warrior, and
    Wizard spells you cast cost {1} less to cast." carries its FOUR-tribe
    ``Or`` list on the ``ModifyCost`` static mode's own ``spell_filter``
    (:func:`modify_cost_spell_filter` — the SAME shared reader
    ``_typed_spellcast``'s static arm already uses), not on ``affected``
    (a bare Card-type filter with no subtype — CR 601.2f)."""
    idents = _idents("The Destined Warrior")
    for sub in ("Cleric", "Rogue", "Warrior", "Wizard"):
        assert ("type_matters", "you", sub) in idents, sub


def test_type_matters_ref_count_filter_multiply_wrapped():
    """ADR-0038 W5: Hamlet Vanguard's "This creature enters with two +1/+1
    counters on it for each other nontoken Human you control." carries its
    Human subtype on a ``PutCounter`` whose ``count`` is ``Multiply(
    factor=2, inner=Ref(ObjectCount(filter=Typed(Subtype:Human))))`` — the
    bare ``Ref`` tag check in ``count_operand_filter`` never unwraps the
    "twice that many" scalar; ``structural_type_subjects`` now also tries
    :func:`ref_count_filter` (a strict superset). HIGH confidence (a
    subject-carrying structural read)."""
    idents = _idents("Hamlet Vanguard")
    assert ("type_matters", "you", "Human") in idents
    assert _confidences("Hamlet Vanguard", "type_matters") == {"high"}


def test_removal_destroy_and_damage_arms():
    """CR 701.8a: single-target destroy (Hero's Downfall) and burn (Flame
    Slash) of a permanent fire; the mass forms (Wrath of God — DestroyAll,
    CR 115.10) and player-only burn (Lightning Bolt — target Any) never
    fire."""
    assert ("removal", "you", "") in _idents("Hero's Downfall")
    assert ("removal", "you", "") in _idents("Flame Slash")
    assert "removal" not in _keys("Wrath of God")
    assert "removal" not in _keys("Lightning Bolt")


def test_tutor_kept_mirror_only():
    """CR 701.23a: the pinned "search your library for" mirror fires
    Demonic Tutor; Bribery searches an OPPONENT's library ("your library"
    absent — and the v0.9.0 ``target_player`` node pins the structural
    boundary too) and never fires."""
    assert ("tutor", "you", "") in _idents("Demonic Tutor")
    assert "tutor" not in _keys("Bribery")


def test_proliferate_matters_four_producers_and_boundaries():
    """CR 701.34a + 702.184a: the station keyword row (Adagia — a station
    card ACCRUES charge counters), the divinity/indestructible mirror
    (Myojin), the charge/experience mirror (Ezuri Claw), and the LOW
    remove-counter-cost mirror (Migloz — LOW asserted) fire; a Proliferate
    KEYWORD bearer is the ported proliferate_makers DOER and must not fire
    matters (Atraxa), and the "whenever you proliferate" payoff family is
    the LOGGED live gap (Ezuri, Stalker of Spheres — pins both the gap and
    the makers/matters boundary)."""
    assert ("proliferate_matters", "you", "") in _idents("Adagia, Windswept Bastion")
    assert ("proliferate_matters", "you", "") in _idents("Myojin of Cleansing Fire")
    assert ("proliferate_matters", "you", "") in _idents("Ezuri, Claw of Progress")
    assert _confidences("Migloz, Maze Crusher", "proliferate_matters") == {"low"}
    atraxa = _keys("Atraxa, Praetors' Voice")
    assert "proliferate_matters" not in atraxa
    assert "proliferate_makers" in atraxa
    ezuri = _keys("Ezuri, Stalker of Spheres")
    assert "proliferate_matters" not in ezuri
    assert "proliferate_makers" in ezuri


def test_untap_engine_structural_and_mirror_arms():
    """CR 701.26b: the scope-All mass untap (Early Harvest — probed
    verbatim), the typed multi-target subject (Candelabra "Untap X target
    lands"; Snap "Untap up to two lands" — a LIVE member, polarity from the
    banked pop), and the mirror (Seedborn Muse via "untap all", NOT an
    UntapsDuringEachOtherPlayersUntapStep static read) fire; the
    enchanted-rider (Crab Umbra — attach veto) never fires."""
    for name in ("Early Harvest", "Candelabra of Tawnos", "Snap", "Seedborn Muse"):
        assert ("untap_engine", "you", "") in _idents(name), name
    assert "untap_engine" not in _keys("Crab Umbra")


def test_theft_makers_mirror_only_and_exchange_boundary():
    """CR DD9 (heist) + 613.1b: the steal-and-cast doers fire (Dazzling
    Sphinx's exile-until; Gríma's play-from-their-hand); a control EXCHANGE
    (Gilded Drake) is ported gain_control/control_exchange country and a
    regex non-match."""
    assert ("theft_makers", "opponents", "") in _idents("Dazzling Sphinx")
    assert ("theft_makers", "opponents", "") in _idents("Gríma, Saruman's Footman")
    assert "theft_makers" not in _keys("Gilded Drake")


def test_wants_theft_facade_reconciliation():
    """CR 800.4a: the gain_control cross-open (Abduction) and the don't-own
    arm (Thieving Amalgam — also restores the facade's LOW gain_control
    half) fire wants_theft LOW; plain removal (Hero's Downfall) never
    fires."""
    assert ("wants_theft", "opponents", "") in _idents("Abduction")
    amalgam = _idents("Thieving Amalgam")
    assert ("wants_theft", "opponents", "") in amalgam
    assert ("gain_control", "you", "") in amalgam
    assert "wants_theft" not in _keys("Hero's Downfall")
    assert _confidences("Thieving Amalgam", "wants_theft") == {"low"}


def test_wants_cloning_membership_arms():
    """CR 707.1 / 704.5j / 603.6: a legendary-creature ENGINE (Koma's
    per-upkeep token engine) and a cmc>=5 self-ETB value (Gyruda) fire LOW;
    a non-creature (Glorious Anthem) and a vanilla legendary with no
    engine/ETB (Isamaru) never fire."""
    assert ("wants_cloning", "you", "") in _idents("Koma, Cosmos Serpent")
    assert ("wants_cloning", "you", "") in _idents("Gyruda, Doom of Depths")
    assert _confidences("Koma, Cosmos Serpent", "wants_cloning") == {"low"}
    assert "wants_cloning" not in _keys("Glorious Anthem")
    assert "wants_cloning" not in _keys("Isamaru, Hound of Konda")


def test_food_matters_three_arms_and_maker_boundary():
    """CR 111.10b: the sacrifice arm — cost role included, CR 701.21a a
    sacrifice cost is the controller's (Gyome; Gilded Goose's "{T},
    Sacrifice a Food: Add…" is a LIVE member, polarity from the banked
    pop), the Sacrificed-trigger arm (Experimental Confectioner) and the
    "Foods you control" marker arm (Honored Dreyleader) fire; a pure MAKER
    (Bake into a Pie — create-only) is food_makers' country."""
    for name in (
        "Gyome, Master Chef",
        "Gilded Goose",
        "Experimental Confectioner",
        "Honored Dreyleader",
    ):
        assert ("food_matters", "you", "") in _idents(name), name
    pie = _keys("Bake into a Pie")
    assert "food_matters" not in pie
    assert "food_makers" in pie


def test_clue_matters_structural_and_residue_mirror():
    """CR 701.16a + 111.10f: the word mirror carries the investigate DOER
    (Thraben Inspector — breadth intended, the b13 suspend_matters
    precedent; clue_makers co-fires), the becomes-Clue static (In Too
    Deep) and the trigger+mirror pair (Bygone Bishop); no clue text, no
    fire (Hero's Downfall)."""
    inspector = _keys("Thraben Inspector")
    assert "clue_matters" in inspector
    assert "clue_makers" in inspector
    assert ("clue_matters", "you", "") in _idents("In Too Deep")
    assert ("clue_matters", "you", "") in _idents("Bygone Bishop")
    assert "clue_matters" not in _keys("Hero's Downfall")


def test_pump_makers_duration_gate_and_firebreathing_veto():
    """CR 611.2c: the duration-scoped trick fires (Giant Growth —
    UntilEndOfTurn on the ability node, probed verbatim); the activated
    SELF-pump (Shivan Dragon — Pump{target: SelfRef}, ported self_pump's
    country), the duration-less static (Glorious Anthem) and the debuff
    (Ascendant Evincar — negative factor) never fire."""
    assert ("pump_makers", "you", "") in _idents("Giant Growth")
    assert "pump_makers" not in _keys("Shivan Dragon")
    assert "pump_makers" not in _keys("Glorious Anthem")
    assert "pump_makers" not in _keys("Ascendant Evincar")


def test_self_counter_grow_selfref_and_keyword_actions():
    """CR 122.1 + 701.46/701.37/702.104: the PutCounter{P1P1, SelfRef} arm
    (Scavenging Ooze) and the Monstrosity keyword-action node (Arbor
    Colossus) fire; the board-wide spread (Cathars' Crusade —
    PutCounterAll, ported counter_distribute's country) and a counter-less
    pump (Giant Growth) never fire."""
    assert ("self_counter_grow", "you", "") in _idents("Scavenging Ooze")
    assert ("self_counter_grow", "you", "") in _idents("Arbor Colossus")
    assert "self_counter_grow" not in _keys("Cathars' Crusade")
    assert "self_counter_grow" not in _keys("Giant Growth")


def test_flash_matters_opponent_turn_cast_payoff_mirror():
    """CR 702.8a, ADR-0034 branch B: the opponent-turn cast payoff fires
    (Faerie Tauntings; Alela's "first spell during each opponent's turn" —
    the form phase drops the qualifier on, the mirror's whole point); a
    flash-speed spell with no payoff (Snap) and a flash GRANTER (Teferi,
    Mage of Zhalfir — ported flash_makers' country) never fire."""
    assert ("flash_matters", "you", "") in _idents("Faerie Tauntings")
    assert ("flash_matters", "you", "") in _idents("Alela, Cunning Conqueror")
    assert "flash_matters" not in _keys("Snap")
    assert "flash_matters" not in _keys("Teferi, Mage of Zhalfir")


def test_activated_ability_cost_census():
    """CR 602.1: a tap-cost value engine (Prodigal Sorcerer), the Meloku
    cost-vocabulary parity pin ({1} + Return a land — ReturnToHand is
    deliberately NOT in the extra-cost exclusion set) and a generic-mana
    one-shot (Sensei's Top "{1}:") fire; a mana dork/rock (Llanowar
    Elves, Sol Ring, Azorius Signet — ramp-only effects) and a land
    (Bojuka Bog) never fire."""
    for name in (
        "Prodigal Sorcerer",
        "Meloku the Clouded Mirror",
        "Sensei's Divining Top",
    ):
        assert ("activated_ability", "you", "") in _idents(name), name
    for name in ("Llanowar Elves", "Sol Ring", "Azorius Signet", "Bojuka Bog"):
        assert "activated_ability" not in _keys(name), name


def test_mass_death_payoff_aggregate_head_only():
    """CR 700.4: the AGGREGATE "for each … died this turn" head fires
    (Gadrak, Grizzly Ghoul); the single-death morbid conditional (Skirsdag
    High Priest) and the cost reducer (Bone Picker) are plain death_matters
    country — no "for each / number of" head, no fire (checklist #4)."""
    assert ("mass_death_payoff", "you", "") in _idents("Gadrak, the Crown-Scourge")
    assert ("mass_death_payoff", "you", "") in _idents("Grizzly Ghoul")
    assert "mass_death_payoff" not in _keys("Skirsdag High Priest")
    assert "mass_death_payoff" not in _keys("Bone Picker")


def test_destroy_legendary_supertype_predicate():
    """CR 205.4 + 701.8a: the HasSupertype:Legendary target predicate fires
    (Bounty Agent, Hero's Demise — 5/5 exact live census); NotSupertype
    ("nonlegendary" — Cast Down) is the OPPOSITE and a bare destroy
    (Hero's Downfall) carries no predicate."""
    assert ("destroy_legendary", "any", "") in _idents("Bounty Agent")
    assert ("destroy_legendary", "any", "") in _idents("Hero's Demise")
    assert "destroy_legendary" not in _keys("Cast Down")
    assert "destroy_legendary" not in _keys("Hero's Downfall")


def test_opponent_exile_matters_reference_vs_doer():
    """CR 406.1, ADR-0034 split: the REFERENCES-their-exile payoff fires
    (Umbris — "for each card your opponents own in exile"); the
    graveyard-hate DOER (Bojuka Bog) is ported opponent_exile_makers."""
    assert ("opponent_exile_matters", "opponents", "") in _idents(
        "Umbris, Fear Manifest"
    )
    assert "opponent_exile_matters" not in _keys("Bojuka Bog")


def test_opponent_search_matters_trigger_modes():
    """CR 701.23/701.22/701.25: SearchedLibrary (Ob Nixilis), the
    PlayerPerformedAction composite NAMING the search (River Song) and
    Shuffled (Psychic Surgery) fire when opponent-scoped; the YOU-scoped
    scry/surveil composite (Matoya) is §R(c)'s country — cross-lane."""
    assert ("opponent_search_matters", "opponents", "") in _idents(
        "Ob Nixilis, Unshackled"
    )
    assert ("opponent_search_matters", "opponents", "") in _idents("River Song")
    assert ("opponent_search_matters", "opponents", "") in _idents("Psychic Surgery")
    matoya = _keys("Matoya, Archon Elder")
    assert "opponent_search_matters" not in matoya
    assert "scry_surveil_matters" in matoya


def test_color_hoser_mirror_and_direct_structural_carrier():
    """CR 105.2: the modal counter/destroy hoser (Blue Elemental Blast —
    direct HasColor carrier + mirror) and the non{color} debuff mirror arm
    (Ascendant Evincar) fire; the two-color disjunction (Deathmark — an
    Or-of-colors, NO direct HasColor) is the LOGGED live gap and pins
    parity; no color word, no fire (Swords to Plowshares)."""
    assert ("color_hoser", "you", "") in _idents("Blue Elemental Blast")
    assert ("color_hoser", "you", "") in _idents("Ascendant Evincar")
    assert "color_hoser" not in _keys("Deathmark")
    assert "color_hoser" not in _keys("Swords to Plowshares")


def test_coven_matters_ability_word_membership():
    """CR 207.2c: coven is an ability word — the word IS the anchor and
    BEARERS fire (Leinore, Augur of Autumn — membership IS the lane,
    checklist #4); no coven word, no fire (Glorious Anthem)."""
    assert ("coven_matters", "you", "") in _idents("Leinore, Autumn Sovereign")
    assert ("coven_matters", "you", "") in _idents("Augur of Autumn")
    assert "coven_matters" not in _keys("Glorious Anthem")


def test_crimes_matter_trigger_and_condition_anchor():
    """CR 700.13: the CommitCrime trigger mode (Gisa, Vadmir) and the
    condition-form anchor gated to no-trigger faces (Nimble Brigand, Oko
    the Ringleader — the [P20]-adjacent condition-kind hole, bucket-B
    regex-bridge) fire; targeting an opponent's creature without saying
    crime (Murder) never fires."""
    assert ("crimes_matter", "you", "") in _idents("Gisa, the Hellraiser")
    assert ("crimes_matter", "you", "") in _idents("Vadmir, New Blood")
    assert ("crimes_matter", "you", "") in _idents("Nimble Brigand")
    assert ("crimes_matter", "you", "") in _idents("Oko, the Ringleader")
    assert "crimes_matter" not in _keys("Murder")


def test_outlaw_matters_word_vs_typed_membership():
    """CR 700.12/700.12a: the word fires (Olivia; Laughing Jasper Flint —
    who also fires wants_theft via don't-own, cross-lane); an outlaw-TYPED
    tribal without the word (Anowon — Rogue lord) and a crime card with no
    outlaw word (Oko) never fire — the CR 700.12 membership direction the
    lane deliberately does not open."""
    assert ("outlaw_matters", "you", "") in _idents("Olivia, Opulent Outlaw")
    jasper = _idents("Laughing Jasper Flint")
    assert ("outlaw_matters", "you", "") in jasper
    assert ("wants_theft", "opponents", "") in jasper
    assert "outlaw_matters" not in _keys("Anowon, the Ruin Thief")
    assert "outlaw_matters" not in _keys("Oko, the Ringleader")


# ── Batch 14 §R: recall follow-ups on PORTED lanes ───────────────────────────


def test_opp_top_exile_change_zone_and_choose_chain_extensions():
    """§R(a) — CR 406.1: the exile-from-opponent-library head (Brainstealer
    Dragon, Stolen Strategy — ChangeZone→Exile + Typed{Opponent} +
    InZone:Library, probed verbatim) and the choose-from-their-zones chain
    (Covetous Urge — ChooseFromZone + sibling exile + CastFromZone) fire;
    graveyard hate (Bojuka Bog) never fires. Nassari, Dean of Expression
    was banked as the one logged add (hook: the same steal-and-cast
    contract); the shadow diff's DFC same-oid union shows live firing the
    joined "Uvilda // Nassari" record, so the arm lands the face as BOTH —
    this assertion pins the face-level firing either way."""
    assert ("opp_top_exile", "you", "") in _idents("Brainstealer Dragon")
    assert ("opp_top_exile", "you", "") in _idents("Stolen Strategy")
    assert ("opp_top_exile", "you", "") in _idents("Covetous Urge")
    assert "opp_top_exile" not in _keys("Bojuka Bog")
    assert ("opp_top_exile", "you", "") in _idents("Nassari, Dean of Expression")


def test_stax_census_cantcastfrom_and_block_modes():
    """§R(b) — CR 601.3 + 509.1b/509.1c + 701.23: CantCastFrom routes by
    ``who`` (Drannith Magistrate Opponents → stax ONLY; Grafdigger's Cage
    AllPlayers → BOTH); CantSearchLibrary routes by its OWN ``cause``
    (Stranglehold Opponents → stax; Mindlock Orb AllPlayers → symmetric
    ONLY, stax asserted absent); MustBlock / BlockRestriction ride the
    existing gates (Invasion Plans / Dense Canopy unscoped → symmetric;
    Spirespine's SelfRef + EnchantedBy rows and Air Bladder's EnchantedBy
    row open NEITHER lane)."""
    drannith = _idents("Drannith Magistrate")
    assert ("stax_taxes", "opponents", "") in drannith
    assert ("symmetric_stax", "each", "") not in drannith
    cage = _idents("Grafdigger's Cage")
    assert ("stax_taxes", "opponents", "") in cage
    assert ("symmetric_stax", "each", "") in cage
    orb = _idents("Mindlock Orb")
    assert ("symmetric_stax", "each", "") in orb
    assert ("stax_taxes", "opponents", "") not in orb
    assert ("stax_taxes", "opponents", "") in _idents("Stranglehold")
    assert ("symmetric_stax", "each", "") in _idents("Invasion Plans")
    assert ("symmetric_stax", "each", "") in _idents("Dense Canopy")
    for name in ("Spirespine", "Air Bladder"):
        ks = _keys(name)
        assert "stax_taxes" not in ks, name
        assert "symmetric_stax" not in ks, name


def test_scry_surveil_matters_composite_and_replacement_extensions():
    """§R(c) — CR 701.22a/701.25a + 614.1a: the you-scoped scry/surveil
    PlayerPerformedAction composite (Matoya, Planetarium of Wan Shi Tong)
    and the Scry-event replacements (Eligeth, Kenessos — the entire corpus
    census) fire; River Song routes to opponent_search_matters (composite
    names SearchedLibrary, valid_target Opponent) and the Proliferate
    composite (Ezuri, Stalker of Spheres) fires neither scry lane."""
    for name in (
        "Matoya, Archon Elder",
        "Planetarium of Wan Shi Tong",
        "Eligeth, Crossroads Augur",
        "Kenessos, Priest of Thassa",
    ):
        assert ("scry_surveil_matters", "you", "") in _idents(name), name
    river = _keys("River Song")
    assert "scry_surveil_matters" not in river
    assert "opponent_search_matters" in river
    ezuri = _keys("Ezuri, Stalker of Spheres")
    assert "scry_surveil_matters" not in ezuri
    assert "opponent_search_matters" not in ezuri


# ── Batch 15: the second structural-remainder batch ──────────────────────────


def test_airbend_and_earthbend_keyword_and_node_arms():
    """CR 701.65a/701.66a: the Airbend/Earthbend keyword rows (Aang,
    Airbending Master; Earthen Ally) and the RegisterBending node arm (Monk
    Gyatso's keyword-less "you may airbend" rides the keyword too, but the
    node arm covers the routing); Bitter Work is a dual-mechanic pin
    (earthbend_makers + exhaust_makers b13, NOT exhaust_matters). The
    keyword-gate: Avatar Aang's ElementalBend raw names "earthbend" but he
    carries no Earthbend keyword → routed earthbend_matters (the SOLE
    member), never earthbend_makers; Earthen Ally (keyword bearer) never
    fires matters."""
    assert ("airbend_makers", "you", "") in _idents("Aang, Airbending Master")
    assert ("airbend_makers", "you", "") in _idents("Monk Gyatso")
    assert ("airbend_makers", "you", "") in _idents("Avatar Aang")
    assert ("earthbend_makers", "you", "") in _idents("Earthen Ally")
    bitter = _keys("Bitter Work")
    assert "earthbend_makers" in bitter
    assert "exhaust_makers" in bitter
    assert "exhaust_matters" not in bitter
    aang = _idents("Avatar Aang")
    assert ("earthbend_matters", "you", "") in aang
    assert "earthbend_makers" not in _keys("Avatar Aang")
    assert "earthbend_matters" not in _keys("Earthen Ally")


def test_waterbend_split_and_double_fire_quirk():
    """CR 701.67a: keyword bearers fire waterbend_makers (Spirit Water
    Revival's additional-cast-cost form, Giant Koi, Katara); the UNgated
    node arm fires waterbend_matters for the cross-bend payoff (Avatar
    Aang) and the activated-cost doers whose primary effect phase dropped
    (Giant Koi — the live double-fire quirk, ported as-is + LOGGED).
    Polarity-from-pop pins: Katara's Waterbend ability projects clean
    (Draw) and fires NO matters arm — the 5-member set is exact, NOT "all
    activated-waterbend cards"; Spirit Water Revival's cast-cost form
    fires makers only."""
    for name in ("Spirit Water Revival", "Giant Koi", "Katara, Bending Prodigy"):
        assert ("waterbend_makers", "you", "") in _idents(name), name
    assert "waterbend_makers" not in _keys("Monk Gyatso")
    assert ("waterbend_matters", "you", "") in _idents("Avatar Aang")
    koi = _keys("Giant Koi")
    assert "waterbend_matters" in koi
    assert "waterbend_makers" in koi
    assert "waterbend_matters" not in _keys("Katara, Bending Prodigy")
    assert "waterbend_matters" not in _keys("Spirit Water Revival")


def test_firebending_mirror_keyword_split():
    """CR 702.189a (firebending is a TRIGGERED ability, unlike the other
    three bends): the kept word mirror partitions by Firebending-keyword
    presence — bearers (Fire Lord Azula, Avatar Aang) → makers; the
    keyword-less Fire-Nation reference tail (Sozin's Comet's grant, Iroh's
    counter-conditioned grant) → matters. The bending node arm must NOT
    route firebend (a naive route would double-fire past the mirror)."""
    assert ("firebending_makers", "you", "") in _idents("Fire Lord Azula")
    assert ("firebending_makers", "you", "") in _idents("Avatar Aang")
    assert "firebending_matters" not in _keys("Fire Lord Azula")
    assert ("firebending_matters", "you", "") in _idents("Sozin's Comet")
    assert ("firebending_matters", "you", "") in _idents("Iroh, Dragon of the West")
    assert "firebending_makers" not in _keys("Sozin's Comet")


def test_station_three_way_makers_split_and_matters_residue():
    """CR 702.184a/702.184c: one guard mirror, 3-way makers split — the
    Station keyword (Lumen-Class Frigate), the Spacecraft/Planet subtype
    (typed ``tree.card_subtypes``, same card), or the charge arm (Drill Too
    Deep) → station_makers; a bare Spacecraft reference (Tractor Beam's
    enchant, Focus Fire's count) → station_matters. Tapestry Warden is the
    DOCUMENTED live gap (the plural verb "stations" dodges ``\\bstation\\b``;
    CR 702.184c's own Example names it — a candidate widen via phase's
    CrewContribution node, pinned negative today, parity-first)."""
    assert ("station_makers", "you", "") in _idents("Lumen-Class Frigate")
    assert ("station_makers", "you", "") in _idents("Drill Too Deep")
    assert "station_matters" not in _keys("Lumen-Class Frigate")
    assert ("station_matters", "you", "") in _idents("Tractor Beam")
    assert ("station_matters", "you", "") in _idents("Focus Fire")
    warden = _keys("Tapestry Warden")
    assert "station_makers" not in warden
    assert "station_matters" not in warden


def test_evasion_self_keyword_and_mirror_arms():
    """CR 702.111 menace / 702.36 fear / 702.13 intimidate / 702.118 skulk
    / 702.31 horsemanship / 702.28 shadow + 509.1b: the keyword rows
    (Accursed Spirit's Intimidate) and the flat kept mirror (Aether
    Figment's "can't be blocked", no evasion keyword) fire; flying is
    DELIBERATELY soft evasion and never fires (Serra Angel)."""
    assert ("evasion_self", "you", "") in _idents("Accursed Spirit")
    assert ("evasion_self", "you", "") in _idents("Aether Figment")
    assert "evasion_self" not in _keys("Serra Angel")


def test_cant_block_grant_structural_and_gates():
    """CR 509.1b + 101.2: the CantBlock static-def arm fires the targeted
    grant (Blindblast — ParentTarget), the conditional team form (Barrage
    of Boulders) and the symmetric table static (Bedlam — do NOT scope-gate
    to opponent-only); the SELF-drawback (Arco-Flagellant — SelfRef
    affected), the forced-attack lane (Fumiko) and the pacify shape
    (Pacifism — split CantAttack+CantBlock over the same enchanted subject,
    single-target removal not evasion) never fire."""
    for name in ("Blindblast", "Barrage of Boulders", "Bedlam"):
        assert ("cant_block_grant", "you", "") in _idents(name), name
    assert "cant_block_grant" not in _keys("Arco-Flagellant")
    assert "cant_block_grant" not in _keys("Fumiko the Lowblood")
    assert "cant_block_grant" not in _keys("Pacifism")


def test_global_ability_grant_quoted_gates():
    """CR 113.3 / 604.3 / 613.1f: a QUOTED ability granted to your creature
    board fires scope "any" (Cryptolith Rite, Battery Bearer); a bare
    keyword anthem has no quote and never fires (Archetype of Imagination);
    a single-permanent GrantTrigger nested in a trigger's execute chain is
    not a top-level board grant (Mathas)."""
    assert ("global_ability_grant", "any", "") in _idents("Cryptolith Rite")
    assert ("global_ability_grant", "any", "") in _idents("Battery Bearer")
    assert "global_ability_grant" not in _keys("Archetype of Imagination")
    assert "global_ability_grant" not in _keys("Mathas, Fiend Seeker")


def test_opponent_counter_grant_direction_and_kind_gates():
    """CR 122.1 / 122.1d: a detrimental counter on an OPPONENT's permanent
    fires (Mathas — bounty; Freeze in Place — the "tap … and put a stun
    counter on IT" pronoun-loss recovery via the same-unit co-tap join); a
    beneficial +1/+1 placed to enable your own removal is the WRONG
    direction (Hunter of Eyeblights); a SELF-stun drawback has no opp
    recipient and no co-tap (Pugnacious Hammerskull)."""
    assert ("opponent_counter_grant", "opponents", "") in _idents(
        "Mathas, Fiend Seeker"
    )
    assert ("opponent_counter_grant", "opponents", "") in _idents("Freeze in Place")
    assert "opponent_counter_grant" not in _keys("Hunter of Eyeblights")
    assert "opponent_counter_grant" not in _keys("Pugnacious Hammerskull")


def test_conditional_self_protection_gates():
    """CR 702.11 hexproof / 702.12 indestructible / 702.16 protection /
    702.18 shroud / 702.21 ward: a CONDITIONED static granting a protective
    keyword to ITSELF fires (Dragonlord Ojutai — Not(SourceIsTapped);
    Fleecemane Lion — SourceIsMonstrous); intrinsic printed hexproof rides
    the keyword array, never a conditioned grant (Sigarda)."""
    assert ("conditional_self_protection", "you", "") in _idents("Dragonlord Ojutai")
    assert ("conditional_self_protection", "you", "") in _idents("Fleecemane Lion")
    assert "conditional_self_protection" not in _keys("Sigarda, Host of Herons")


def test_sacrifice_protection_kept_mirror():
    """CR 701.21a (the 20260619 CR maps Sacrifice → 701.21 — the live
    t2b5-B comment's 701.16 is STALE) + 101.2: the two literal phrases fire
    (Sigarda, Tajuru Preserver — phase parses both as Unimplemented, [P42]);
    a stax attack-tax never contains either (Ghostly Prison)."""
    assert ("sacrifice_protection", "you", "") in _idents("Sigarda, Host of Herons")
    assert ("sacrifice_protection", "you", "") in _idents("Tajuru Preserver")
    assert "sacrifice_protection" not in _keys("Ghostly Prison")


def test_life_payment_insurance_cost_census_and_marker():
    """CR 119.4: a repeatable "Pay N life:" ACTIVATION cost fires — the
    structural PayLife cost leaf (Adanto Vanguard; Arco-Flagellant, the
    historical marker case, now also structural in v0.9.0 — the internal
    arm shift inside an unchanged union is the expected divergence); a
    one-shot cast cost (Toxic Deluge) and effect-side life loss (Sign in
    Blood) never fire either arm."""
    assert ("life_payment_insurance", "you", "") in _idents("Adanto Vanguard")
    assert ("life_payment_insurance", "you", "") in _idents("Arco-Flagellant")
    assert "life_payment_insurance" not in _keys("Toxic Deluge")
    assert "life_payment_insurance" not in _keys("Sign in Blood")


def test_speed_maker_payoff_boundary():
    """CR 702.179a (Start Your Engines! initializes speed = MAKER) vs
    702.178a (Max Speed functions only AT speed 4 = PAYOFF): the dual-
    keyword bearers fire BOTH lanes (Mendicant Core, Far Fortune); the
    keyword-less speed-CHANGER fires makers only via the ChangeSpeed doer
    (Spikeshell Harrier — the doer NEVER feeds matters); a Vehicle with no
    speed text fires neither (Smuggler's Copter)."""
    for name in ("Mendicant Core, Guidelight", "Far Fortune, End Boss"):
        keys = _keys(name)
        assert "speed_makers" in keys, name
        assert "speed_matters" in keys, name
    spike = _keys("Spikeshell Harrier")
    assert "speed_makers" in spike
    assert "speed_matters" not in spike
    assert ("speed_matters", "you", "") in _idents("Vnwxt, Verbose Host")
    assert "speed_makers" not in _keys("Smuggler's Copter")


def test_exhaust_matters_trigger_mode_and_raw_anchor():
    """CR 702.177a/702.177b: the KeywordAbilityActivated{Exhaust} trigger
    mode (Sala, Deck Boss), the delayed-trigger-inside-activated payoff
    (Pit Automaton — phase Unimplemented, [P44], the raw anchor) and the
    permission static (Elvish Refueler — fires BOTH lanes: makers via the
    b13 keyword row, matters via the anchor) fire; a card merely CARRYING
    "Exhaust — {cost}:" uses the keyword and rides exhaust_makers only
    (Bitter Work — the sibling b13 lane must show zero change)."""
    assert ("exhaust_matters", "you", "") in _idents("Sala, Deck Boss")
    assert ("exhaust_matters", "you", "") in _idents("Pit Automaton")
    refueler = _keys("Elvish Refueler")
    assert "exhaust_matters" in refueler
    assert "exhaust_makers" in refueler
    bitter = _keys("Bitter Work")
    assert "exhaust_matters" not in bitter
    assert "exhaust_makers" in bitter


def test_saddle_matters_keyword_and_typed_arms():
    """CR 702.171a: one lane, no maker/matters split — the Saddle keyword
    (The Gitrog, Ravenous Ride — also a SaddledSource property carrier) and
    the keyword-less BecomeSaddled granter (Kolodin) fire; Crew alone never
    fires (Smuggler's Copter — Vehicles are not Mounts)."""
    assert ("saddle_matters", "you", "") in _idents("The Gitrog, Ravenous Ride")
    assert ("saddle_matters", "you", "") in _idents("Kolodin, Triumph Caster")
    assert "saddle_matters" not in _keys("Smuggler's Copter")


def test_suspect_matters_state_route_and_verb_boundary():
    """CR 701.60a/701.60b (suspected is a DESIGNATION, not an ability): the
    pure "suspected"-STATE reference fires matters — Agency Coroner (the
    swallowed rider, [P43], via the face marker) and Airtight Alibi (the
    Unsuspect/CantBecomeSuspected carrier); Nelly Borca's raw carries BOTH
    forms and the verb wins → routed MAKER (polarity-from-pop pin; the
    ported b4 suspect_makers lane must show zero change)."""
    assert ("suspect_matters", "you", "") in _idents("Agency Coroner")
    assert ("suspect_matters", "you", "") in _idents("Airtight Alibi")
    nelly = _keys("Nelly Borca, Impulsive Accuser")
    assert "suspect_matters" not in nelly
    assert "suspect_makers" in nelly


def test_suspect_makers_dropped_rider_synthesis():
    """CR 701.60a — Case of the Stashed Skeleton's "create a 2/1 black
    Skeleton creature token and suspect it" rider: phase emits NO residue
    node for the "suspect it" action at all (only the Token effect
    survives), so re-decoration (ADR-0038) can't reach it and
    ``tree_synthesis._arm_suspect_makers`` fills the gap — emitting the
    REAL "suspect" concept (ADR-0037/0038), read by the SAME typed
    ``effect_concepts("suspect")`` arm Nelly Borca's first-class Suspect
    effect uses, no marker special-case in the lane."""
    assert "suspect_makers" in _keys("Case of the Stashed Skeleton")


def test_void_warp_makers_mirror_and_void_payoff_boundary():
    """CR 702.185a (Warp) + 207.2c (void is an ABILITY WORD — no rules
    meaning, no phase keyword): the three mirror arms fire — the keyword
    bearer (Starfield Vocalist "Warp {1}{U}"), the granter (Tannuk "have
    warp {2}{R}"), and the em-dash + graveyard self-cast forms (Timeline
    Culler "Warp—{B}" / "using its warp ability"); the Void PAYOFF
    (Alpharael — "a spell was warped this turn") belongs to the skip-sweep
    void_warp_matters lane and never fires makers."""
    assert ("void_warp_makers", "you", "") in _idents("Starfield Vocalist")
    assert ("void_warp_makers", "you", "") in _idents("Tannuk, Steadfast Second")
    assert ("void_warp_makers", "you", "") in _idents("Timeline Culler")
    assert "void_warp_makers" not in _keys("Alpharael, Stonechosen")


# ── Batch 16: THE FINAL structural batch — porting phase complete ────────────


def test_ability_copy_mirror_and_spell_copy_boundary():
    """CR 707.10 ("A copy of an ability is itself an ability") + 113.2b: the
    byte-identical kept mirror fires the ability-copiers (Strionic Resonator)
    and the whole-suite importers ("has all activated abilities of" —
    Necrotic Ooze); a SPELL copier (Twincast — the CopySpell/StackSpell shape
    that made the structural arm over-fire 90%) never fires here (it rides
    spell_copy_makers). The stale live "CR 706.10" cite is corrected — 706 is
    now die-rolling."""
    assert ("ability_copy", "you", "") in _idents("Strionic Resonator")
    assert ("ability_copy", "you", "") in _idents("Necrotic Ooze")
    twin = _keys("Twincast")
    assert "ability_copy" not in twin
    assert "spell_copy_makers" in twin


def test_ability_strip_payoff_counter_join_and_vetoes():
    """CR 613.1f (ability-removing effects, layer 6) + 122.1b (keyword
    counters): one ability unit joins a RemoveAllAbilities modification with a
    counter-placement concept — Abigale rides PutCounter, Hellcat rides the
    ChangeZone ``enter_with_counters`` field (the parity trap: NO PutCounter
    node on the record; the SequentialSibling chain is ONE unit). Retched
    Wretch's counter ref is the trigger CONDITION (no placement — pop False);
    Turn to Frog carries the SetPower/SetToughness shrinker veto shape."""
    assert ("ability_strip_payoff", "you", "") in _idents(
        "Abigale, Eloquent First-Year"
    )
    assert ("ability_strip_payoff", "you", "") in _idents("Hellcat, Undying Vigilante")
    assert "ability_strip_payoff" not in _keys("Retched Wretch")
    assert "ability_strip_payoff" not in _keys("Turn to Frog")


def test_arcane_matters_word_mirror():
    """CR 205.3k (Arcane is a SPELL type) + 702.47a (Splice onto Arcane): the
    flat ``\\barcane\\b`` word mirror fires the payoff (Tallowisp) and the
    Splice spells (Glacial Ray); a Spirit payoff with no "arcane" token never
    fires (Geist-Honored Monk). The v0.9.0 ``{"Subtype": "Arcane"}`` filter
    is a LOGGED widen candidate — the word mirror is the parity home."""
    assert ("arcane_matters", "you", "") in _idents("Tallowisp")
    assert ("arcane_matters", "you", "") in _idents("Glacial Ray")
    assert "arcane_matters" not in _keys("Geist-Honored Monk")


def test_celebration_matters_word_mirror():
    """CR 207.2c — celebration is an ABILITY WORD (no rules meaning, no
    structured phase node — probed: Ash carries "Celebration —" only in
    strings), so the word mirror is the only home. Ash, Party Crasher and
    Raging Battle Mouse fire; an Adventure payoff never does (Edgewall
    Innkeeper)."""
    assert ("celebration_matters", "you", "") in _idents("Ash, Party Crasher")
    assert ("celebration_matters", "you", "") in _idents("Raging Battle Mouse")
    assert "celebration_matters" not in _keys("Edgewall Innkeeper")


def test_cmdzone_ability_condition_zone_read():
    """CR 113.6 (abilities usually function on the battlefield; command-zone
    abilities are stated exceptions) + 207.2c (eminence is an ability word) +
    903.6: a recursive SourceInZone('Command') condition-tree read fires the
    trigger form (Oloro) and the Eminence static (The Ur-Dragon — v0.9.0
    structures the Or[Command, Battlefield] condition). Command Beacon's
    EFFECT moves the commander FROM the zone — no zone condition, pop False.
    (The stale live "113.6k" cite is now the multi-zone trigger rule.)"""
    assert ("cmdzone_ability", "you", "") in _idents("Oloro, Ageless Ascetic")
    assert ("cmdzone_ability", "you", "") in _idents("The Ur-Dragon")
    assert "cmdzone_ability" not in _keys("Command Beacon")


def test_exalted_keyword_and_textual_arms_emit_voltron_pair():
    """CR 702.83a/702.83b + 506.5 ("attacks alone"): the Scryfall keyword row
    emits BOTH exalted_lone_attacker AND voltron_matters (the live tuple —
    an exalted commander suits up a lone attacker); the kept mirror fires
    the "attacks alone" payoffs (Sovereigns of Lost Alara). Soulbond alone
    never fires (Silverblade Paladin)."""
    rafiq = _idents("Rafiq of the Many")
    assert ("exalted_lone_attacker", "you", "") in rafiq
    assert ("voltron_matters", "you", "") in rafiq
    assert ("exalted_lone_attacker", "you", "") in _idents("Sovereigns of Lost Alara")
    assert "exalted_lone_attacker" not in _keys("Silverblade Paladin")


def test_flip_self_structural_closes_wording_gap():
    """CR 710.1/710.2 (flip cards): the flip_self lane reads the typed
    ``Unimplemented{name=='flip'}`` node phase parses every creature-flip to
    (ADR-0036 mirror fold). Fires the Kamigawa flip fronts (Nezumi
    Graverobber, Bushi Tenderfoot) AND uniformly closes the old
    ``\\bflip this creature\\b`` mirror's wording gap — Akki Lavarunner
    ("flip it") now fires where the text anchor missed it."""
    assert ("flip_self", "you", "") in _idents("Nezumi Graverobber")
    assert ("flip_self", "you", "") in _idents("Bushi Tenderfoot")
    # Gap closed: the structural read is a superset of the "flip this
    # creature" mirror (Akki's "flip it" wording defeated the text anchor).
    assert ("flip_self", "you", "") in _idents("Akki Lavarunner")


def test_free_creature_payoff_etb_gate():
    """CR 601.2f-h + 118.7 (a cost reduced to nothing is {0} — cast with no
    mana spent): an etb-event trigger with a ManaSpentCondition anywhere in
    the condition tree fires (Satoru — Or[Not(WasCast), ManaSpentCondition]);
    the CAST-trigger punisher is the opposite lane and never fires (Lavinia).
    The stale live "CR 712" cite is now Double-Faced Cards."""
    assert ("free_creature_payoff", "you", "") in _idents("Satoru, the Infiltrator")
    assert "free_creature_payoff" not in _keys("Lavinia, Azorius Renegade")


def test_free_spell_storm_selfref_scaler_shapes():
    """CR 601.2f/118.7: a SelfRef ModifyCost{Reduce} static whose
    dynamic_count is the cast-this-turn shape fires — the ObjectCount-with-
    Another form (Thrasta) and the SpellsCastThisTurn{Controller} form
    (Demilich); an opponent-cast scaler is excluded by the same gate
    (Delightful Discovery — pop False)."""
    assert ("free_spell_storm", "you", "") in _idents("Thrasta, Tempest's Roar")
    assert ("free_spell_storm", "you", "") in _idents("Demilich")
    assert "free_spell_storm" not in _keys("Delightful Discovery")


def test_island_makers_word_mirror_and_matters_boundary():
    """CR 702.14b/702.14c (islandwalk is an evasion ability): Tier-1
    (ADR-0036/0037 fold — the ``ISLAND_MAKERS_REGEX`` mirror is deleted)
    fires bearers (Thada Adel — the Scryfall keyword-field arm), granters
    (Lord of Atlantis — a structural ``AddKeyword`` read, no more Scryfall-
    array gap) and neutralizers (Mystic Decree — ``RemoveKeyword``). The
    Zhou Yu attack-restriction PAYOFF is the sibling island_matters lane
    (ported b13, zero drift) — makers stays out."""
    assert ("island_makers", "you", "") in _idents("Lord of Atlantis")
    assert ("island_makers", "you", "") in _idents("Thada Adel, Acquisitor")
    assert ("island_makers", "you", "") in _idents("Mystic Decree")
    zhou = _keys("Zhou Yu, Chief Commander")
    assert "island_makers" not in zhou
    assert "island_matters" in zhou


def test_island_makers_token_maker_structural_recovery():
    """A STRUCTURAL recovery over the deleted mirror: Chasm Skulker and
    Coral Barrier make islandwalk TOKENS (the token profile's own keyword
    list carries the ``{"Landwalk": "Island"}`` variant) — the mirror never
    saw a token's nested keyword list."""
    assert ("island_makers", "you", "") in _idents("Chasm Skulker")
    assert ("island_makers", "you", "") in _idents("Coral Barrier")


def test_island_makers_adjudicated_over_fires_shed():
    """Four mirror over-fires shed (bare REFERENCES to islandwalk
    creatures, not bearers/granters/makers): the evasion-DENIAL idiom
    (Gosta Dirk, Undertow — the sibling evasion_denial lane's territory), a
    removal spell targeting islandwalk creatures (Merfolk Assassin), and a
    symmetric-protection reference (Island Sanctuary)."""
    assert "island_makers" not in _keys("Gosta Dirk")
    assert "island_makers" not in _keys("Undertow")
    assert "island_makers" not in _keys("Merfolk Assassin")
    assert "island_makers" not in _keys("Island Sanctuary")


def test_keyword_soup_makers_context_and_count():
    """CR 122.1b (the evergreen keyword inventory) + 613.1f: the
    membership-gated mirror — team-grant context AND >= 5 distinct evergreen
    keyword words over the whole kept text — fires Odric and the cross-modal
    Akroma's Will (whose per-ability structural count never reaches 5); the
    single-creature ABSORBER (Cairn Wanderer — keyword_soup, a different
    lane) never fires makers. LOW confidence, membership block."""
    assert ("keyword_soup_makers", "you", "") in _idents("Odric, Lunarch Marshal")
    assert ("keyword_soup_makers", "you", "") in _idents("Akroma's Will")
    assert "keyword_soup_makers" not in _keys("Cairn Wanderer")


def test_meld_pair_raw_oracle_and_subject():
    """CR 701.42a/701.42b (meld pairs) + 712.1: the ONE raw-oracle mirror —
    reminder text is load-bearing: the back piece carries only "(Melds with
    X.)", which reminder-stripping would lose. Subject = THIS card's name
    (signal_keys.MELD_PAIR ∈ SUBJECT_KEYS serves the one partner). The meld
    RESULT names no partner and never fires (Brisela)."""
    assert ("meld_pair", "you", "Gisela, the Broken Blade") in _idents(
        "Gisela, the Broken Blade"
    )
    assert ("meld_pair", "you", "Bruna, the Fading Light") in _idents(
        "Bruna, the Fading Light"
    )
    assert ("meld_pair", "you", "Hanweir Garrison") in _idents("Hanweir Garrison")
    assert "meld_pair" not in _keys("Brisela, Voice of Nightmares")


def test_named_counter_misc_three_arms_and_cost_role_gate():
    """CR 122.1 (counters are individuated by NAME): (1) the closed-12-kind
    effect arm (Tetzimoc — PutCounter ck='prey'); (2) the predicate
    else-branch catch-all ("with a fuse counter" — Bomb Squad; niche≠skip);
    (3) the cost-role arm (Mazemind Tome — its page PutCounter rides the
    activation COST (EffectCost), so the effect arm skips it and the
    structural cost-subtree scan is the home; ADR-0036 mirror fold). 'time'
    owns suspend/vanishing (CR 702.62 family) and stays out (Deep-Sea
    Kraken)."""
    assert ("named_counter_misc", "you", "") in _idents("Tetzimoc, Primal Death")
    assert ("named_counter_misc", "you", "") in _idents("Mazemind Tome")
    assert ("named_counter_misc", "you", "") in _idents("Bomb Squad")
    assert "named_counter_misc" not in _keys("Deep-Sea Kraken")


def test_noncombat_damage_payoff_word_mirror():
    """CR 510.1a/510.2 (combat damage is assigned in the combat damage step —
    everything else is noncombat) + 702.19a (the CR's literal term witness):
    the byte-identical word mirror fires the doubler (Solphim), the reflector
    (Boros Reckoner) and the Unknown-mode "deals exactly" family (Ghyrson
    Starn — mirror-only home); a COMBAT-damage payoff never fires (Cold-Eyed
    Selkie). The v0.9.0 combat_scope=='NoncombatOnly' read is a LOGGED widen
    candidate. (Stale live "510.1c" corrected — that is lethal-assignment
    ordering.)"""
    assert ("noncombat_damage_payoff", "you", "") in _idents("Solphim, Mayhem Dominus")
    assert ("noncombat_damage_payoff", "you", "") in _idents("Boros Reckoner")
    assert ("noncombat_damage_payoff", "you", "") in _idents(
        "Ghyrson Starn, Kelermorph"
    )
    assert "noncombat_damage_payoff" not in _keys("Cold-Eyed Selkie")


def test_nonhuman_attackers_subject_gate():
    """CR 508.3 + 205.3m: an attacks-trigger whose subject filter carries the
    Non:Subtype:Human predicate with controller you (Winota's
    ``Typed[Creature, {Non: {Subtype: Human}}]``); a plain attack trigger
    without the Non-Human subject stays out (Hanweir Garrison — reused as
    §12's positive AND this lane's negative)."""
    assert ("nonhuman_attackers", "you", "") in _idents("Winota, Joiner of Forces")
    assert "nonhuman_attackers" not in _keys("Hanweir Garrison")


def test_one_punch_numeric_membership_gate():
    """CR 903.10a (21 commander damage) + 702.90a infect / 702.4a-b double
    strike (the amplifiers the serve credits): the field-numeric membership
    gate — creature, Fixed power >= 8, power >= 2x mana value, and a REAL
    printed cost (phase NoCost backs never enter). Phyrexian Dreadnought
    12/12 mv 1 and Death's Shadow 13/13 mv 1 fire; Emrakul 15/15 mv 15 wins
    by size, not amplification (ratio gate). LOW confidence, membership
    block."""
    assert ("one_punch", "you", "") in _idents("Phyrexian Dreadnought")
    assert ("one_punch", "you", "") in _idents("Death's Shadow")
    assert "one_punch" not in _keys("Emrakul, the Aeons Torn")


def test_per_target_payoff_mirror():
    """CR 601.2c (targets are locked at announce) + 601.2f: the kept mirror
    fires Hinata's YOUR-side per-target reduction (the corpus population is
    exactly one card); a plain self-side reducer with no per-target scaler
    never fires (Goblin Anarchomancer). Phase degrades the "for each target"
    discriminator to an empty ObjectCount — the [P49] description-screen
    recovery is Stage-3."""
    assert ("per_target_payoff", "you", "") in _idents("Hinata, Dawn-Crowned")
    assert "per_target_payoff" not in _keys("Goblin Anarchomancer")


def test_power_tap_engine_structural_and_conferred_arms():
    """CR 602.1 ("[Cost]: [Effect.]"): STRUCTURAL — an Activated tap-cost
    unit whose effect scales an ``amount``/``count`` operand off a self
    ``Power`` ref (Marwyn's ``{T}: Add {G} equal to ~'s power``), or the SAME
    shape nested inside a granted ability's ``GrantAbility.definition`` (the
    conferred/DFC-back form, Predatory Urge). One-shot power-scaling with NO
    activation cost never fires (Soul's Majesty). Also a NET RECALL
    IMPROVEMENT (ADR-0036/0037 fold) over the retired ``_POWER_TAP_
    CONFERRED_RX`` mirror: Surestrike Trident's granted "{T}, Unattach
    Surestrike Trident: This creature deals damage equal to its power..." —
    the mirror's ``\\{t\\}:`` anchor required the colon immediately after
    "{T}", missing the "{T}, Unattach ...:" cost-chain phrasing — now fires
    via the structural ``GrantAbility.definition`` walk."""
    assert ("power_tap_engine", "you", "") in _idents("Marwyn, the Nurturer")
    assert ("power_tap_engine", "you", "") in _idents("Predatory Urge")
    assert ("power_tap_engine", "you", "") in _idents("Surestrike Trident")
    assert "power_tap_engine" not in _keys("Soul's Majesty")


def test_starting_life_matters_marker_rederivation():
    """CR 103.4/103.4c (starting life totals): the verbatim ``\\bstarting
    life total\\b`` marker re-derivation fires the compare payoff (Angel of
    Destiny) and the halving effect (Torgaar); the PHRASE, not the concept —
    "your life total becomes 7" stays out (Elderscale Wurm, the old broad
    regex's over-fire)."""
    assert ("starting_life_matters", "you", "") in _idents("Angel of Destiny")
    assert ("starting_life_matters", "you", "") in _idents("Torgaar, Famine Incarnate")
    assert "starting_life_matters" not in _keys("Elderscale Wurm")


def test_toughness_combat_structural_and_value_residue():
    """CR 510.1a (the assign-equal-to-POWER default the Doran statics
    override; the stale live "510.1c" is lethal-assignment ordering) +
    613.4c + 604.3: the AssignDamageFromToughness modification fires the
    redirect half (Doran; Assault Formation — the multi-ability face); a
    Toughness-typed Ref quantity in an effect amount fires the value half
    (Angelic Chorus); AssignNoCombatDamage is NOT a from-toughness hit
    (Master of Cruelties — pop False)."""
    assert ("toughness_combat", "you", "") in _idents("Doran, the Siege Tower")
    assert ("toughness_combat", "you", "") in _idents("Angelic Chorus")
    assert ("toughness_combat", "you", "") in _idents("Assault Formation")
    assert "toughness_combat" not in _keys("Master of Cruelties")


def test_typed_anthem_multi_structural_and_color_gate():
    """CR 205.3m (creature types) + 613.4c + 105.2a (colors are NOT
    subtypes): a pump modification over a Creature filter naming >= 2
    subtypes fires — the Or-of-Typed disjunction (Lovisa — v0.9.0 structures
    what the old projection dropped) and the flat 2-subtype form (Brenard's
    Food-or-Golem); a color-only disjunction never fires (Glistening
    Deluge), nor does a keyword GRANT with no pump (Paladin Danse)."""
    assert ("typed_anthem_multi", "you", "") in _idents("Lovisa Coldeyes")
    assert ("typed_anthem_multi", "you", "") in _idents("Brenard, Ginger Sculptor")
    assert "typed_anthem_multi" not in _keys("Glistening Deluge")
    assert "typed_anthem_multi" not in _keys("Paladin Danse, Steel Maverick")


# ── Stage-2 closeout sweep: the 23 skip-lane dispositions ────────────────────


def test_attractions_matter_mirror_and_membership_floor():
    """CR 717 (Attraction cards) / 701.51 (Open an Attraction) / 702.159
    (Visit): the byte-identical kept mirror fires the openers ("Lifetime"
    Pass Holder; Coming Attraction — the word survives outside the reminder
    parens); an Attraction permanent ITSELF (Balloon Stand — visit nodes,
    reminder-stripped oracle never says "attraction") is membership and
    must NOT fire (gate #4); a plain artifact stays out."""
    assert ("attractions_matter", "you", "") in _idents('"Lifetime" Pass Holder')
    assert ("attractions_matter", "you", "") in _idents("Coming Attraction")
    assert "attractions_matter" not in _keys("Balloon Stand")
    assert "attractions_matter" not in _keys("Sol Ring")


def test_draft_spellbook_mirror_paper_and_alchemy_arms():
    """CR 905.1c/905.2b (Conspiracy draft) + DD5 (Spellbook — conjure/draft):
    the kept mirror fires the paper draft-matters card (Cogwork Librarian
    "draft a card") and the Alchemy spellbook card (Bind to Secrecy); a
    plain draw spell never fires (Divination)."""
    assert ("draft_spellbook", "you", "") in _idents("Cogwork Librarian")
    assert ("draft_spellbook", "you", "") in _idents("Bind to Secrecy")
    assert "draft_spellbook" not in _keys("Divination")


def test_each_mode_player_structural_constraint_node():
    """CR 700.2d (the same-target default these cards override): the
    ``DifferentTargetPlayers`` modal-constraint node — set-equal to the
    live 8 — fires Vindictive Lich and Shadrix Silverquill; a plain modal
    with no per-mode player constraint never fires (Cryptic Command)."""
    assert ("each_mode_player", "each", "") in _idents("Vindictive Lich")
    assert ("each_mode_player", "each", "") in _idents("Shadrix Silverquill")
    assert "each_mode_player" not in _keys("Cryptic Command")


def test_free_plot_single_card_mirror():
    """CR 702.170 (Plot): the single-card kept mirror (Fblthp, Lost on the
    Range — phase drops both plot clauses, parse-gap logged); a plain plot
    card (Aloe Alchemist — "Plot {1}{G}" keyword line only) never fires."""
    assert ("free_plot", "you", "") in _idents("Fblthp, Lost on the Range")
    assert "free_plot" not in _keys("Aloe Alchemist")


def test_legend_rule_off_structural_and_mirror_residue():
    """CR 704.5j (the legend rule): the ``LegendRuleDoesntApply`` static mode
    fires the unbounded form (Mirror Gallery) AND the bounded form v0.9.0
    now structures (Cadric — the stale "bounded is DROPPED" β note); the
    Yamazaki family rides the byte-identical mirror residue (phase keeps
    only their +2/+2 static); a legendary REFERENCE never fires
    (Blackblade Reforged)."""
    assert ("legend_rule_off", "you", "") in _idents("Mirror Gallery")
    assert ("legend_rule_off", "you", "") in _idents("Cadric, Soul Kindler")
    assert ("legend_rule_off", "you", "") in _idents("Brothers Yamazaki")
    assert "legend_rule_off" not in _keys("Blackblade Reforged")


def test_lessons_matter_filter_read_mirror_and_learn_floor():
    """CR 701.48 (Learn names the Lesson subtype): the {"Subtype": "Lesson"}
    filter read fires the cost-reducer (Uncle Iroh) and the state-check
    (Aang, A Lot to Learn); Twenty Lessons rides the word-mirror residue.
    Membership floor (gate #4): a Learn DOER (Field Trip — "Lesson" only in
    stripped reminder text) and a Lesson CARD whose oracle never says
    "lesson" (Environmental Sciences) must NOT fire."""
    assert ("lessons_matter", "you", "") in _idents("Uncle Iroh")
    assert ("lessons_matter", "you", "") in _idents("Aang, A Lot to Learn")
    assert ("lessons_matter", "you", "") in _idents("Twenty Lessons")
    assert "lessons_matter" not in _keys("Field Trip")
    assert "lessons_matter" not in _keys("Environmental Sciences")


def test_lose_unless_hand_etb_self_lose_join():
    """CR 104.3e (an effect may state that a player loses the game): the
    corpus-unique join — a self-etb trigger whose unit carries a
    Controller-recipient ``lose_game`` — fires Phage the Untouchable only.
    The end-step delayed self-lose (Final Fortune) and the opponent-lose
    activation (Door to Nothingness) never fire."""
    assert ("lose_unless_hand", "you", "") in _idents("Phage the Untouchable")
    assert "lose_unless_hand" not in _keys("Final Fortune")
    assert "lose_unless_hand" not in _keys("Door to Nothingness")


def test_miracle_grant_addkeyword_walk_and_intrinsic_floor():
    """CR 702.94 (Miracle): the AddKeyword{Miracle} mod-walk fires the
    structural granter (Lorehold, the Historian); Aminatou, Veil Piercer
    rides the byte-identical mirror residue (her grant folds). Membership
    floor (gate #4): an intrinsic Miracle BEARER (Bonfire of the Damned —
    "Miracle {cost}" keyword line) must NOT fire."""
    assert ("miracle_grant", "you", "") in _idents("Lorehold, the Historian")
    assert ("miracle_grant", "you", "") in _idents("Aminatou, Veil Piercer")
    assert "miracle_grant" not in _keys("Bonfire of the Damned")


def test_powerup_matters_scryfall_keyword_row():
    """CR 702.193 (Power-up — a one-time activated ability, cheaper the turn
    the permanent entered; the mapping row's "Unfinity acorn" rationale was
    FLAT WRONG): the sweep keyword-field row reads the caller-supplied
    Scryfall array (phase DROPS Power-up from Face.keywords — Extremis
    Elite probed), so the bearer and the payoff-granter (Wonder Man, who
    carries the keyword too) fire; a keyword-less creature never does."""
    assert ("powerup_matters", "you", "") in _idents("Extremis Elite")
    assert ("powerup_matters", "you", "") in _idents("Wonder Man, Hollywood Hero")
    assert "powerup_matters" not in _keys("Serra Angel")


def test_recast_etb_keyword_and_etb_bleed_arms():
    """CR 702.190 (Sneak — now a real CR keyword; the "no rules meaning" row
    note is STALE) + 118.9: arm (a) the Sneak Scryfall-keyword row fires
    Karai's Technique; arm (b) the structural etb-bleed join (an enters
    trigger + a discard/lose_life/sacrifice sibling whose text names "each
    opponent") fires Burglar Rat. The old ``\\bsneak\\b`` regex over-fire
    (Lightfoot Rogue) and a value etb (Wood Elves) never fire — the
    anti-goodstuff point of the lane."""
    assert ("recast_etb", "you", "") in _idents("Karai's Technique")
    assert ("recast_etb", "you", "") in _idents("Burglar Rat")
    assert "recast_etb" not in _keys("Lightfoot Rogue")
    assert "recast_etb" not in _keys("Wood Elves")


def test_secret_writedown_mirror_and_companion_reminder_floor():
    """CR 702.106a/b (hidden agenda — "secretly choose a card name") +
    400.11b/108.3 (cards from outside the game): the kept mirror fires the
    wish (Burning Wish), the secret choice (A Killer Among Us) and the
    real outside-the-game text (Karn, the Great Creator); a COMPANION's
    reminder-only "outside the game" is stripped before the scan and never
    fires (Lutri, the Spellchaser)."""
    assert ("secret_writedown", "you", "") in _idents("Burning Wish")
    assert ("secret_writedown", "you", "") in _idents("A Killer Among Us")
    assert ("secret_writedown", "you", "") in _idents("Karn, the Great Creator")
    assert "secret_writedown" not in _keys("Lutri, the Spellchaser")


def test_seek_matters_structural_effect_read():
    """DD3 (Seek — the game randomly chooses a matching card from your
    library; Arena-only is a LEGALITY property, not a skip — deck-forge
    serves historic_brawl): the ``Seek`` effect node fires Bounty of the
    Deep and Cabaretti Revels; a library SEARCH is a different node family
    and never fires (Demonic Tutor)."""
    assert ("seek_matters", "you", "") in _idents("Bounty of the Deep")
    assert ("seek_matters", "you", "") in _idents("Cabaretti Revels")
    assert "seek_matters" not in _keys("Demonic Tutor")


def test_snow_matters_structural_arms_mirror_and_membership_floor():
    """CR 205.4 (Snow is a real supertype — the live comment itself calls
    the old skip wrong): the HasSupertype:Snow filter-property read fires
    Abominable Treefolk, the ``YouControlSnowPermanentCountAtLeast``
    condition read fires Rimewind Taskmage, and the byte-identical
    ``\\bsnow\\b`` mirror (the producer) fires Skred. Membership floor
    (gate #4): a Snow-SUPERTYPE card itself (Boreal Druid — no "snow" in
    oracle) never fires off its type line."""
    assert ("snow_matters", "you", "") in _idents("Abominable Treefolk")
    assert ("snow_matters", "you", "") in _idents("Rimewind Taskmage")
    assert ("snow_matters", "you", "") in _idents("Skred")
    assert "snow_matters" not in _keys("Boreal Druid")


def test_stickers_matter_mirror_and_structural_corroboration():
    """CR 123 (Stickers) / 122.1 (ticket counters): the byte-identical
    STICKERS_MATTER_REGEX mirror (``\\{tk\\}|\\bstickers?\\b``) fires the
    sticker payoffs ("Name Sticker" Goblin), the {TK}+sticker engine (Tusk
    and Whiskers) and the PutSticker holder (Carnival Carnivore — also the
    typed corroboration arm's witness); a regular card never fires."""
    assert ("stickers_matter", "you", "") in _idents('"Name Sticker" Goblin')
    assert ("stickers_matter", "you", "") in _idents("Tusk and Whiskers")
    assert ("stickers_matter", "you", "") in _idents("Carnival Carnivore")
    assert "stickers_matter" not in _keys("Sol Ring")


def test_tap_down_blockers_single_card_mirror():
    """CR 509.1c (blocking-requirement evaluation): the single-card kept
    mirror fires Tromokratis ("can't be blocked unless all creatures
    defending player controls block it" — v0.9.0 keeps the clause only as
    Unrecognized condition TEXT on a 143-holder ``CantBeBlocked`` static,
    no fidelity gain available); a menace card (Davros) and a plain
    unblockable (Aether Figment) never fire."""
    assert ("tap_down_blockers", "you", "") in _idents("Tromokratis")
    assert "tap_down_blockers" not in _keys("Davros, Dalek Creator")
    assert "tap_down_blockers" not in _keys("Aether Figment")


def test_target_own_payoff_source_split_v40_holds():
    """CR 702.21a + 207.2c (heroic/valiant are ability words; the live
    "702.83" heroic cite is a miscite): a becomes_target trigger whose
    watched owner is you/any and whose ``valid_source`` is NOT
    opponent-restricted fires own-payoff (Heartfire Hero — source
    controller You; Loki — an "any"-owner watcher, ability-source You);
    the opponent-creature subject is scoped out (Willbreaker), the
    opponent-source redirect (Shapers' Sanctuary) must NOT double-fire
    here — the v40 fix holds — and paper Nadu's GRANTED trigger (no
    native BecomesTarget unit; live fires only the rebalanced A-Nadu)
    rides the targeting_matters mirror, never own-payoff — live parity,
    the spec's "+ Nadu (verify)" failing its own verify."""
    assert ("target_own_payoff", "you", "") in _idents("Heartfire Hero")
    assert ("target_own_payoff", "you", "") in _idents("Loki, God of Mischief")
    assert "target_own_payoff" not in _keys("Willbreaker")
    assert "target_own_payoff" not in _keys("Shapers' Sanctuary")
    nadu = _keys("Nadu, Winged Wisdom")
    assert "target_own_payoff" not in nadu
    assert "targeting_matters" in nadu


def test_target_redirect_opponent_source_branch():
    """CR 702.21a / 603.2: the same read's opponent-source branch — the
    trigger's own ``valid_source`` carries the Opponent controller
    (Shapers' Sanctuary / Battle Mammoth probed) — fires redirect; an
    unrestricted source (Heartfire Hero) stays own-payoff."""
    assert ("target_redirect", "you", "") in _idents("Shapers' Sanctuary")
    assert ("target_redirect", "you", "") in _idents("Battle Mammoth")
    assert "target_redirect" not in _keys("Heartfire Hero")


def test_targeting_matters_structural_any_and_residue_mirror():
    """CR 702.21a (the load-bearing becomes-target family rule): EVERY
    becomes_target trigger fires the broad scope-'any' lane (Willbreaker —
    opponent-subject counts too); the byte-identical residue mirror covers
    the heroic ability word (Akroan Crusader) and the granted/quoted forms
    phase emits no native trigger for (Kira, Great Glass-Spinner); a
    targeted SPELL is not a targeting payoff (Murder)."""
    assert ("targeting_matters", "any", "") in _idents("Willbreaker")
    assert ("targeting_matters", "any", "") in _idents("Akroan Crusader")
    assert ("targeting_matters", "any", "") in _idents("Kira, Great Glass-Spinner")
    assert "targeting_matters" not in _keys("Murder")


def test_theft_protection_counter_exec_gate_cuts_family_to_four():
    """CR 702.21a (Ward — the CR's own counter-when-targeted template): the
    OncePerTurn + BecomesTarget + Counter-execute join — native (Glyph
    Keeper) and via the GrantTrigger walk (Kira, Great Glass-Spinner) —
    lands exactly the live 4. The Counter-exec gate cuts the 19-card
    OncePerTurn+BecomesTarget family: Heartfire Hero (exec=PutCounter) and
    Loki, God of Mischief (exec=Draw) are the pinned negatives."""
    assert ("theft_protection", "you", "") in _idents("Glyph Keeper")
    assert ("theft_protection", "you", "") in _idents("Kira, Great Glass-Spinner")
    assert "theft_protection" not in _keys("Heartfire Hero")
    assert "theft_protection" not in _keys("Loki, God of Mischief")


def test_timing_control_mirror_scope_any():
    """CR 117.1a (timing permissions) + 307.5 ("only any time they could
    cast a sorcery"): the byte-identical kept mirror (scope "any") fires
    the symmetric lock (City of Solitude) and the opponent lock (Teferi,
    Time Raveler); a flash GRANT is the opposite direction and never fires
    (Vedalken Orrery). Phase still drops the cast-timing statics — the β
    note holds at v0.9.0."""
    assert ("timing_control", "any", "") in _idents("City of Solitude")
    assert ("timing_control", "any", "") in _idents("Teferi, Time Raveler")
    assert "timing_control" not in _keys("Vedalken Orrery")


def test_villainous_choice_mirror_and_doubler():
    """CR 701.55a-d (Face a Villainous Choice — resolves the live "CR
    701.x"): the kept mirror fires the chooser (Davros, Dalek Creator) and
    the doubler (The Valeyard — also the 1-holder
    ``GrantsExtraVillainousChoice`` corroboration witness); a generic
    "choose one" modal never fires (Cryptic Command)."""
    assert ("villainous_choice", "you", "") in _idents("Davros, Dalek Creator")
    assert ("villainous_choice", "you", "") in _idents("The Valeyard")
    assert "villainous_choice" not in _keys("Cryptic Command")


def test_void_warp_matters_mirror_and_makers_boundary():
    """CR 702.185 (Warp) + 207.2c (void is an ABILITY WORD — the stale skip
    the closeout flagged): the byte-identical VOID_WARP_MATTERS_REGEX
    mirror fires the Void payoffs (Alpharael, Stonechosen; Chorale of the
    Void); a Warp KEYWORD BEARER is the b15 makers arm only (Starfield
    Vocalist — the matters regex must not fire its keyword line)."""
    assert ("void_warp_matters", "you", "") in _idents("Alpharael, Stonechosen")
    assert ("void_warp_matters", "you", "") in _idents("Chorale of the Void")
    assert "void_warp_matters" not in _keys("Starfield Vocalist")


def test_voting_matters_trigger_event_and_effect_split():
    """CR 701.38 (Vote — fixes the mapping row's stale 701.32): the ``Vote``
    TRIGGER mode (readable today via the ``mode.lower()`` fall-through as
    trigger_event == "vote") fires the finish-voting payoffs — exactly the
    live 3 (Erestor, Grudge Keeper set-checked here); a Vote EFFECT node
    stays voting_makers (Expropriate — the trigger-vs-effect split keeps
    the ADR-0034 maker/matters partition exact)."""
    assert ("voting_matters", "each", "") in _idents("Erestor of the Council")
    assert ("voting_matters", "each", "") in _idents("Grudge Keeper")
    expro = _keys("Expropriate")
    assert "voting_matters" not in expro
    assert "voting_makers" in expro


# ── Stage-2 exit-gate follow-ups: 5 node-present routing gaps (ADR-0035) ──────
# Each closes a lane where phase parsed the data, the mirror captured a real
# node, but the crosswalk emitted nothing and no floor recovered it. Verified
# node-present + matching extract_signals_ir(include_membership=False) over the
# commander-legal corpus (no net over-fire; the full-lane count moved UP only).


def test_enchantments_matter_cast_trigger():
    """Gap 1: a TYPED "whenever you cast an enchantment spell, <payoff>" trigger
    (Argothian Enchantress, Enchantress's Presence). phase parses a ``cast_spell``
    trigger whose ``valid_card`` is Enchantment-typed + a Draw payoff body; the
    is-enchantment membership floor can't recover it (the body is a Draw). Routed
    off the watched-spell filter's core type. CR 603.2."""
    assert ("enchantments_matter", "you", "") in _idents("Argothian Enchantress")
    assert ("enchantments_matter", "you", "") in _idents("Enchantress's Presence")


@pytest.mark.parametrize(
    "name",
    [
        "Clinging Darkness",  # -4/-1 aura (negative power)
        "Chant of the Skifsang",  # -13/-0 aura
        "Animate Dead",  # -1/-0 aura (reanimation debuff rider)
    ],
)
def test_debuff_makers_static_negative_power_aura(name):
    """Gap 2: a static AURA negative-POWER pump — ``AddPower`` value < 0 on an
    EnchantedBy filter. The Pump-EFFECT arm reads Fixed power/toughness; a static
    mod carries a bare-int ``value``. Keyed on the power sign to mirror the live
    path. CR 613.4c."""
    assert ("debuff_makers", "any", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Barbed Battlegear",  # +4/-1 combat Equipment — buff, not a -1/-1 enabler
        "Boon of Emrakul",  # +3/-3 aura — positive power
    ],
)
def test_debuff_makers_excludes_positive_power_tradeoff(name):
    """Gap 2 guard: a +X/-Y combat Equipment/Aura has POSITIVE power (a buff whose
    toughness downside is a tradeoff, not a -1/-1 payoff). The live path keys off
    the power amount, so these stay out (checklist #6)."""
    assert "debuff_makers" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    ["Champion of the Flame", "Auramancer's Guise"],
)
def test_scaling_pump_and_voltron_dynamic_attached_count(name):
    """Gap 3: a dynamic self-pump scaling on an attached-object count —
    ``AddDynamicPower`` = ``Multiply(factor, Ref(ObjectCount(AttachedToRecipient)))``
    ("+X/+X for each Aura/Equipment attached to it"). The Multiply scalar hid the
    Ref from the scaling read and the AttachedToRecipient filter from the voltron
    read; both now unwrap it. CR 107.3 / 301.5c."""
    idents = _idents(name)
    assert ("scaling_pump", "you", "") in idents
    assert ("voltron_matters", "you", "") in idents


@pytest.mark.parametrize(
    "name",
    [
        "Black Vise",  # deals X to the chosen player (SourceChosenPlayer)
        "Booby Trap",  # deals 10 to the triggering player (TriggeringPlayer)
    ],
)
def test_direct_damage_chosen_and_triggering_player(name):
    """Gap 4: a ``DealDamage`` whose target is a CHOSEN / TRIGGERING player node
    (``SourceChosenPlayer`` / ``TriggeringPlayer``) reaches a player — burn the
    ``_scope_from_player_node`` map didn't recognize. CR 120.1."""
    assert ("direct_damage", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Daring Thief",  # exchange control of a nonland permanent for an opp's
        "Djinn of Infinite Deceits",  # exchange control of two creatures
    ],
)
def test_gain_control_exchange_control(name):
    """Gap 5: an ``ExchangeControl`` swaps your permanent for an opponent's — you
    gain theirs (theft). phase's lossy IR maps exchangecontrol → the gain_control
    category, but the mirror keeps the exchange_control concept, so the theft lane
    now reads it (the routing the ``_control_exchange`` docstring anticipates).
    CR 701.12b / 110.2."""
    assert ("gain_control", "you", "") in _idents(name)


# ── batch hygiene ─────────────────────────────────────────────────────────────


def test_all_emitted_keys_are_in_the_ported_set():
    """The crosswalk only emits keys it claims to have ported (no leakage).

    Measured against the full Stage-3 lane set — the ADR-0035 Stage-4 LIVE
    narrowing (``PORTED_KEYS``) is a hybrid-level routing decision, not a
    lane-existence one, so ``extract_crosswalk_signals`` still emits every built
    lane's key."""
    for name in _cards():
        assert _keys(name) <= _PORTED_KEYS_STAGE3


# ── ADR-0035 Stage-3b (b) — overlay-correction stage + substrate-purity ───────


def test_overlay_stage_never_writes_into_the_l1_substrate():
    """The substrate-purity invariant over the WHOLE fixture: the overlay stage
    decorates the Layer-2 concept overlay and leaves every Layer-1 phase-mirror
    node byte-identical AND the same object.

    This is the load-bearing safety property (ADR-0035): a correction that leaked
    into the frozen substrate — or swapped a mirror node for a rebuilt one — fails
    here loud, per card."""
    for name in _cards():
        tree = _tree(name)
        before_bytes = l1_bytes(tree)
        before_ids = [id(n) for n in _l1_nodes(tree)]
        corrected = apply_overlay_corrections(tree)
        # L1 byte-shape unchanged (never mutated in place) …
        assert l1_bytes(corrected) == before_bytes, name
        # … and every position holds the SAME object (never swapped). The stage
        # returns the input identity when it makes no correction.
        assert [id(n) for n in _l1_nodes(corrected)] == before_ids, name


def test_substrate_purity_guard_is_not_vacuous():
    """The guard's FAILURE path fires — proving the invariant is not silently
    vacuous.

    We simulate the exact illegal move an overlay arm could make: rebuild ONE L1
    mirror node and land the new object at its tree position (an arm writing L1
    would ``dataclasses.replace`` the frozen node, producing a distinct object).
    The rebuild is field-for-field IDENTICAL, so ``l1_bytes`` — the committed
    content check — cannot see the swap; the id-based ``_assert_substrate_pure``
    (the live guard) MUST. If this ever stops raising, the invariant has gone
    vacuous and every positive substrate-purity assertion is worthless."""
    tree = _tree("Smite")
    before = _l1_identity(tree)

    unit = tree.units[0]
    effect0 = unit.effects[0]
    rebuilt_node = replace(effect0.node)  # byte-identical, NEW object
    assert rebuilt_node is not effect0.node
    assert rebuilt_node.to_dict() == effect0.node.to_dict()

    leaked_effect = replace(effect0, node=rebuilt_node)
    leaked_unit = replace(unit, effects=(leaked_effect, *unit.effects[1:]))
    leaked_tree = replace(tree, units=(leaked_unit, *tree.units[1:]))

    # The byte-check is BLIND to a byte-identical node-swap …
    assert l1_bytes(leaked_tree) == l1_bytes(tree)
    # … but the live id-based guard catches it. This is the load-bearing failure.
    with pytest.raises(SubstratePurityError):
        _assert_substrate_pure(before, leaked_tree)


def _corrected_effects(name: str):
    """The (before, after) concept-node pairs for one fixture card's effects."""
    tree = _tree(name)
    corrected = apply_overlay_corrections(tree)
    pairs = []
    for ub, ua in zip(tree.units, corrected.units, strict=True):
        pairs.extend(zip(ub.effects, ua.effects, strict=True))
    return pairs


def test_overlay_dig_into_play_lands_category_on_overlay():
    """(b) _recover_dig_into_play: a reveal-until whose kept card enters the
    battlefield (Jalira) gets a COMPAT-only ``category='cheat_play'`` override —
    the signal-facing ``concept`` stays ``reveal_until`` (so the dig_until signal
    holds; the flip is compat-seam-only)."""
    hits = [
        a
        for _b, a in _corrected_effects("Jalira, Master Polymorphist")
        if a.category == "cheat_play"
    ]
    assert hits, "dig_into_play did not land"
    assert all(a.concept == "reveal_until" for a in hits)


def test_overlay_exile_removal_lands_category_and_subject():
    """(b) _recover_exile_removal: a single-target exile swallowed into a
    ``gain_life`` rider (Exile) gets ``category='exile'`` + a Creature subject on
    the overlay; the ``concept`` stays ``gain_life`` (lifegain signal holds)."""
    hits = [a for _b, a in _corrected_effects("Exile") if a.category == "exile"]
    assert hits
    assert hits[0].subject == ("Creature",)
    assert hits[0].concept == "gain_life"


def test_overlay_removal_target_subject_lands_subject():
    """(b) _recover_removal_target_subject: a destroy whose creature target phase
    dropped (Smite) gains a Creature subject on the overlay."""
    hits = [
        a
        for b, a in _corrected_effects("Smite")
        if a.concept == "destroy" and not b.subject and a.subject
    ]
    assert hits
    assert hits[0].subject == ("Creature",)


def test_overlay_edict_scope_lands_scope():
    """(b) _recover_edict_scope: a ``sacrifice`` whose sacrificer scope reads the
    controller (Dictate of Erebos) is re-scoped to ``opponents`` on the overlay."""
    hits = [
        a
        for b, a in _corrected_effects("Dictate of Erebos")
        if a.concept == "sacrifice" and b.scope != "opponents"
    ]
    assert hits
    assert hits[0].scope == "opponents"


def test_overlay_blink_returns_to_lands_marker():
    """(b) _recover_blink_returns_to: the exile half of a self-blink (Cloudshift)
    is stamped ``returns_to='battlefield'`` on the overlay."""
    hits = [
        a
        for b, a in _corrected_effects("Cloudshift")
        if a.returns_to and not b.returns_to
    ]
    assert hits
    assert hits[0].returns_to == "battlefield"


def test_overlay_graveyard_zones_lands_zone():
    """(b) _recover_graveyard_zones: a bounce whose graveyard origin phase dropped
    (Aphetto Dredging) gains ``in:graveyard`` in the overlay ``zones``."""
    hits = [
        a
        for b, a in _corrected_effects("Aphetto Dredging")
        if "in:graveyard" in a.zones and "in:graveyard" not in b.zones
    ]
    assert hits


def test_overlay_stage_is_noop_when_no_arm_fires():
    """A card no arm touches is returned by identity (cheap, allocation-free)."""
    tree = _tree("Grizzly Bears")
    assert apply_overlay_corrections(tree) is tree


# ── ADR-0038 W4 giant: graveyard_matters (structural arms + verified CR) ─────


def test_graveyard_matters_from_graveyard_target_filter():
    """Effect target/origin-in-graveyard arm: Gravedigger's ETB reads a
    ``ChangeZone`` whose target filter carries ``InZone: Graveyard`` +
    ``controller: You`` (CR 400.7 — the graveyard is a player's zone)."""
    assert ("graveyard_matters", "you", "") in _idents("Gravedigger")


def test_graveyard_matters_opponent_owned_graveyard():
    """The ``Owned`` property (not the top-level ``controller`` field, which
    describes the reanimation DESTINATION) names an opponent's graveyard —
    Ashen Powder's "creature card from an opponent's graveyard" (CR 400.7)."""
    assert ("graveyard_matters", "opponents", "") in _idents("Ashen Powder")


def test_graveyard_matters_delirium_condition():
    """Delirium (CR 400.7 zone + a card-types-among-graveyard-cards count):
    Grim Flayer's static P/T bonus is gated on a ``DistinctCardTypes``
    condition over a graveyard ``Zone`` source."""
    assert ("graveyard_matters", "you", "") in _idents("Grim Flayer")


def test_graveyard_matters_morbid_count_operand():
    """Morbid ("if a creature died this turn") keys off
    ``ZoneChangeCountThisTurn`` with ``to: Graveyard`` — CR 700.4's "dies" IS
    a battlefield→graveyard zone change. Scavenging Ghoul's counter-per-death
    effect amount reads it directly (not via a condition)."""
    assert ("graveyard_matters", "you", "") in _idents("Scavenging Ghoul")


def test_graveyard_matters_last_resort_mirror_recovery():
    """The LAST-RESORT byte-mirror recovers a genuine "cares about your
    graveyard" reference the typed substrate carries no node for at all — an
    Unfinity sticker idiom (Clandestine Chameleon's "abilities of ... cards
    in your graveyard", Roxi's power keyed partly on "cards in your graveyard
    with an art sticker") parks as an ``Unimplemented`` static-parse residue
    with no allowlisted grammar token (CR 400.7 / 404). ADR-0038 W4 session
    adjudication: both are genuine members."""
    assert ("graveyard_matters", "you", "") in _idents("Clandestine Chameleon")
    assert ("graveyard_matters", "you", "") in _idents("Roxi, Publicist to the Stars")


def test_graveyard_matters_exclusion_clause_reversal():
    """ADR-0038 W5b RE-ADJUDICATION: the W4 giant's own per-clause exclusion
    of '"Name Sticker" Goblin's "enters from anywhere OTHER THAN a graveyard
    or exile" clause (``_GY_EXCLUSION_CLAUSE_RE``) was an UNVERIFIED
    judgment call. A fresh corpus measure shows legacy's real mirror
    invocation (``_signals_ir.py``'s call to ``_graveyard_matters_clauses``
    over the WHOLE ``kept_oracle``, no exclusion filter) DOES fire
    ``('graveyard_matters', 'you')`` for this card — confirmed directly
    against ``extract_signals_ir`` over the real card. CR 400.7: a card
    whose own ETB trigger is gated on NOT arriving from a graveyard still
    mechanically references the zone. The exclusion is removed."""
    assert ("graveyard_matters", "you", "") in _idents('"Name Sticker" Goblin')


# ── ADR-0038 W5b tails: graveyard_matters (structural arms + verified CR) ────


def test_graveyard_matters_trigger_arrival_from_anywhere():
    """Trigger zone-movement arm, ``origin is None`` case (CR 400.7 / 700.4):
    Kozilek, Butcher of Truth's "is put into a graveyard from ANYWHERE"
    trigger carries an explicitly unrestricted origin (``None``) — the
    OPPOSITE of a plain "dies" trigger's explicit ``origin='Battlefield'``.
    Only the explicit-battlefield shape is excluded; ``None`` is
    unrestricted and thus includes a battlefield-to-graveyard move too."""
    assert ("graveyard_matters", "you", "") in _idents("Kozilek, Butcher of Truth")


def test_graveyard_matters_trigger_arrival_enchanted_graveyard():
    """The same origin-is-None arrival read on a non-"from anywhere"-worded
    trigger: Tezzeret's Touch's "when enchanted artifact is put into a
    graveyard" carries no explicit origin qualifier either (CR 400.7)."""
    assert ("graveyard_matters", "you", "") in _idents("Tezzeret's Touch")


def test_graveyard_matters_craft_materials_graveyard_fuel():
    """Graveyard-fuel activation cost arm, Craft materials (CR 702.167a):
    Ore-Rich Stalactite's ``Craft with four or more red instant and/or
    sorcery cards`` cost is an ``ExileMaterials`` leaf whose ``materials``
    filter names graveyard cards as valid crafting fuel — the SAME
    ``InZone`` shape a target filter carries."""
    assert ("graveyard_matters", "you", "") in _idents(
        "Ore-Rich Stalactite // Cosmium Catalyst"
    )


def test_graveyard_matters_static_scaler_forces_you():
    """A static P/T-scaling count operand ALWAYS ALSO forces 'you' (CR
    400.7): Wight of Precinct Six's "+1/+1 for each creature card in your
    OPPONENTS' graveyards" fires BOTH the field's own 'opponents' scope
    AND a forced 'you' — a static's continuous value never reaches
    legacy's per-effect zone-tagging pass, so its raw fallback separately,
    unconditionally fires 'you' for a P/T scaler. Also proves the
    ``ZoneCardCount.scope`` PLURAL-form fix (``'Opponents'``, not
    ``'Opponent'`` — distinct from ``GraveyardSize.player``'s singular
    nested tag)."""
    idents = _idents("Wight of Precinct Six")
    assert ("graveyard_matters", "you", "") in idents
    assert ("graveyard_matters", "opponents", "") in idents


def test_graveyard_matters_static_scaler_offset_unwrap():
    """The static count-operand read unwraps an ``Offset`` scalar wrapper
    (CR 400.7): Nighthawk Scavenger's "power is equal to 1 PLUS the number
    of card types among cards in your opponents' graveyards" wraps its
    ``DistinctCardTypes`` ``Ref`` in an ``Offset(offset=1)`` for the
    "1 plus …" phrasing — :func:`_gy_unwrap_scalar` reaches through it."""
    idents = _idents("Nighthawk Scavenger")
    assert ("graveyard_matters", "you", "") in idents
    assert ("graveyard_matters", "opponents", "") in idents


def test_graveyard_matters_effect_multiply_unwrap():
    """The effect count-operand read unwraps a ``Multiply`` scalar wrapper
    (CR 700.4 — "dies" is a battlefield→graveyard zone change): Silent-Chant
    Zubera's "gain 2 life FOR EACH Zubera that died this turn" wraps its
    ``ZoneChangeCountThisTurn`` ``Ref`` in a ``Multiply(factor=2, …)``."""
    assert ("graveyard_matters", "you", "") in _idents("Silent-Chant Zubera")


def test_graveyard_matters_count_marker_condition_deep_scan():
    """``_graveyard_count_markers`` deep-scan fallback (CR 400.1): Avatar of
    Woe's ModifyCost condition ("if there are ten or more creature cards
    total in all graveyards, this spell costs {6} less") carries a genuine
    ``ZoneCardCount`` the condition-gate arm structurally excludes for
    ModifyCost statics — the deep-scan fallback (gated on no earlier arm
    having fired) reaches it via a different, ungated site."""
    assert ("graveyard_matters", "you", "") in _idents("Avatar of Woe")


def test_graveyard_matters_count_marker_oracle_phrase_fallback():
    """``_graveyard_count_markers`` deep-scan fallback, oracle-regex branch
    (CR 400.1): the Shrine cycle's "X is the number of cards in ALL
    GRAVEYARDS with the same name as that spell" strands the count in a
    free-text ``Variable`` qty with no typed count node at all —
    :data:`_GY_COUNT_PHRASE_RE` recovers it over the whole face oracle."""
    assert ("graveyard_matters", "you", "") in _idents("Aven Shrine")


def test_graveyard_matters_count_marker_gated_by_target_zone_count():
    """The oracle-regex fallback stays silent when a ``TargetZoneCardCount``
    (target-dependent, unresolvable owner — CR 400.7) is present anywhere,
    even though it can't itself resolve a scope: Eldritch Pact's "X is the
    number of cards in THEIR graveyard" is covered by the same real count
    node the mirrored old IR's own per-effect zone-tagging also reaches,
    so the fallback must not ALSO force an unwanted 'you'."""
    idents = _idents("Eldritch Pact")
    assert ("graveyard_matters", "you", "") not in idents
    assert ("graveyard_matters", "opponents", "") in idents


def test_graveyard_matters_count_marker_gated_by_scoped_player():
    """The oracle-regex fallback also stays silent for a ``ScopedPlayer``-
    owned ``ZoneCardCount`` (Into the Story's ModifyCost "if an opponent
    has seven or more cards in their graveyard" — CR 400.7): a REAL count
    node this narrow structural read can't resolve to a concrete scope on
    its own, but which the mirrored old IR's ``has_struct`` gate ALSO
    reaches — a single 'opponents' fire (the field's own scope), never
    ALSO a forced 'you' (unlike a genuine ``Ability.condition`` raw
    zone-tag elsewhere)."""
    idents = _idents("Into the Story")
    assert ("graveyard_matters", "opponents", "") in idents
    assert ("graveyard_matters", "you", "") not in idents


def test_graveyard_matters_modifycost_morbid_excluded():
    """Bone Picker's ModifyCost condition is the Morbid
    ``ZoneChangeCountThisTurn`` marker ("if a creature died this turn") —
    carries no literal "graveyard" word, and the old IR this lane mirrors
    never surfaces an ability object for it at all (CR 700.4 dies; not a
    graveyard-count reference the way Avatar of Woe's literal "in all
    graveyards" is)."""
    assert "graveyard_matters" not in _keys("Bone Picker")


def test_graveyard_matters_canattackwithdefender_via_marker_only():
    """Expedition Lookout's ``CanAttackWithDefender`` condition
    (GraveyardSize, player=Opponent) is excluded from the CONDITION-GATE
    arm (the old IR this lane mirrors never builds an ``Ability``/
    ``.condition`` object for that static-mode there), but the SEPARATE
    ``_graveyard_count_markers`` deep-scan fallback below reaches the SAME
    node via a raw whole-record walk that legacy's own marker producer
    ALSO performs regardless of ability kind — confirmed against a direct
    ``extract_signals_ir`` run: legacy DOES fire
    ``('graveyard_matters', 'opponents')`` for this card, via its
    ``board_count`` marker (scope='opp'), never a forced 'you' (CR
    400.7)."""
    idents = _idents("Expedition Lookout")
    assert ("graveyard_matters", "opponents", "") in idents
    assert ("graveyard_matters", "you", "") not in idents


# ── ADR-0038 W4 giant: artifacts_matter (structural arms + verified CR) ──────


def test_artifacts_matter_sac_cost_bare():
    """SAC-COST payoff, bare activated-ability cost: Atog's "Sacrifice an
    artifact: ~ gets +2/+2" is a ``T_cost__Sacrifice`` on the ability's OWN
    ``cost`` field (role=cost), not an effect — a COST is always paid by the
    activator (CR 601.2b / 602.2), so no opponent/edict gate applies here,
    unlike the effect-sac arm."""
    assert ("artifacts_matter", "you", "") in _idents("Atog")


def test_artifacts_matter_spell_additional_cost_sacrifice():
    """SAC-COST payoff, spell-level ``additional_cost``: Costly Plunder's "As
    an additional cost to cast this spell, sacrifice an artifact or
    creature" rides the card ROOT's ``additional_cost`` (CR 601.2b), a tree
    position no ability unit's own ``cost`` field reaches — merged onto the
    Spell-kind unit's ``costs`` by ``build_concept_tree`` so the existing
    per-unit cost walk sees it."""
    assert ("artifacts_matter", "you", "") in _idents("Costly Plunder")


def test_artifacts_matter_condition_type_gate():
    """CONDITION type-gate doer: Dhund Operative's "As long as you control an
    artifact, ~ gets +1/+0 and has deathtouch" is an ``IsPresent`` condition
    on the static ability (CR 603.2 — a continuously-checked static
    condition) whose filter names Artifact in its core types."""
    assert ("artifacts_matter", "you", "") in _idents("Dhund Operative")


def test_artifacts_matter_investigate_keyword():
    """Investigate (CR 701.16) IS "create a Clue token", a colorless
    ARTIFACT (CR 205.3g). Thraben Inspector's investigate keyword-action
    carries no structured ``make_token`` subject (the Clue subtype lives
    only in unstructured reminder text), so the Scryfall keyword-array
    field-lookup is the structural anchor."""
    assert ("artifacts_matter", "you", "") in _idents("Thraben Inspector")


def test_artifacts_matter_excludes_bargain_optional_alt_cost():
    """MANDATORY SHED (ADR-0038 W4 session adjudication): Ice Out's Bargain
    keyword ("you may sacrifice an artifact, enchantment, or token as you
    cast this spell") is an OPTIONAL additional cost whose target Or-filter
    ALSO carries the catch-all ``Permanent`` core type (a Token-typed
    Permanent filter, CR 702.166a) — a generic alt-cost, not an
    artifacts/enchantments build-around. The Permanent-in-list gate on the
    SAC-COST arm drops it."""
    assert "artifacts_matter" not in _keys("Ice Out")


def test_artifacts_matter_excludes_manland_self_animate():
    """MANDATORY SHED (ADR-0038 W4 session adjudication): Blinkmoth Nexus's
    "{1}: ~ becomes a 1/1 Blinkmoth artifact creature … It's still a land"
    is a SELF-animate manland, not a build-around type-grant — legacy's own
    ``_BECOMES_TYPE_RE`` mirror never matches it either (the P/T digits
    between "becomes a" and "artifact" break the anchor), a byte-identical
    exclusion this port preserves (CR 205.1b)."""
    assert "artifacts_matter" not in _keys("Blinkmoth Nexus")


def test_artifacts_matter_excludes_symmetric_death_punisher():
    """MANDATORY SHED (ADR-0038 W4 session adjudication): Disciple of the
    Vault's "Whenever AN artifact is put into a graveyard from the
    battlefield, …" is a SYMMETRIC watcher (no ``controller: You`` on its
    ``valid_card``) that profits off ANY artifact dying, including an
    opponent's own removal (CR 700.4) — an artifact-death PUNISHER, not a
    "my deck wants artifacts" build-around. The TYPE-DIES doer requires an
    explicit YOUR-controlled watched subject; a symmetric one is excluded."""
    assert "artifacts_matter" not in _keys("Disciple of the Vault")


# ── ADR-0038 W5 tails: artifacts_matter deep descent + local type reads ──


def test_artifacts_matter_battlefield_library_bounce():
    """Rebuking Ceremony's "Put two target artifacts on top of their
    owners' libraries." is a BATTLEFIELD-sourced library-position tuck (CR
    401.4), not graveyard recursion (CR 400.7) — a DIFFERENT provision
    from the existing GY-recursion arm but the SAME broad "cares about the
    Artifact type" tell (CR 301). The origin is ``None`` (a targeted
    spell's implicit battlefield source), not ``Graveyard``."""
    assert ("artifacts_matter", "you", "") in _idents("Rebuking Ceremony")


def test_artifacts_matter_search_outside_game():
    """Golden Wish's "You may reveal an artifact or enchantment card you
    own from outside the game and put it into your hand." is the Wish
    idiom (CR 108.3) — the SAME type-restricted-search-target shape as
    tutor/dig, read locally by its own ``SearchOutsideGame`` typed tag
    (never routed through the shared ``tutor`` CONCEPT_MAP, which would
    also wrongly open the dedicated tutor SIGNAL lane for every Wish
    card — CR 701.23's "search your library" is a distinct action)."""
    idents = _idents("Golden Wish")
    assert ("artifacts_matter", "you", "") in idents
    assert ("enchantments_matter", "you", "") in idents
    assert "tutor" not in _keys("Golden Wish")


def test_artifacts_matter_choose_one_of_wrapped_sac():
    """Nimble Hobbit's "Whenever ~ attacks, you may sacrifice a Food or pay
    {2}{W}." is a modal ``ChooseOneOf`` EFFECT branch (CR 701.21a — the
    sacrifice itself is an ordinary move-to-graveyard, no different rule
    for being inside a choice) ``_walk_effect_chain`` collapses to one
    opaque concept — a deep scan finds the Food-subtype (CR 205.3g)
    Sacrifice inside the branch directly."""
    assert ("artifacts_matter", "you", "") in _idents("Nimble Hobbit")


def test_artifacts_matter_become_copy_type_restricted_target():
    """Spirit of Resilience's "you may have this creature become a copy of
    an artifact or creature card from among those cards" is a TYPE-
    RESTRICTED copy-target (CR 707), the SAME shape as tutor/dig/
    SearchOutsideGame — an ORDINARY Clone's "becomes a copy of target
    creature" (a single bland Creature-only filter) stays silent by
    construction (the type-matters lane only fires on an Artifact/
    Enchantment CORE type, never bare Creature)."""
    assert ("artifacts_matter", "you", "") in _idents("Spirit of Resilience")
    assert "artifacts_matter" not in _keys("Clone")


def test_artifacts_matter_excludes_symmetric_edict_sheds():
    """MANDATORY SHEDS (ADR-0038 W5 tails adjudication, matching the
    enchantments_matter sibling's identical exclusion of the SAME two
    cards): "Each player sacrifices an artifact, a creature, an
    enchantment, a land, and a planeswalker of their choice." (Catch //
    Release's "Release" half) and "At the beginning of each player's
    upkeep, that player sacrifices an artifact, creature, or land of
    their choice." (Braids, Cabal Minion) are SYMMETRIC EDICTS (CR
    701.21a) — every player (or the upkeep's own ScopedPlayer, not just
    You) sacrifices their OWN choice, never a "my deck wants artifacts"
    fodder outlet; ``_sac_is_edict`` correctly rejects both."""
    assert "artifacts_matter" not in _keys("Catch // Release")
    assert "artifacts_matter" not in _keys("Braids, Cabal Minion")


# ── ADR-0038 W4 giant: direct_damage (structural arms + verified CR) ─────────
#
# Census over the full commander-legal corpus (535 live_only, both=1157)
# decomposed into few structural classes, mechanism (a)/(b) per class:
#
#   * an ``Or`` target alternation ("target player or planeswalker" — CR
#     115.4's post-2020 template) the old scope arm never recursed into;
#   * a ``Typed`` target with EMPTY ``type_filters`` — phase's bare shape for
#     BOTH a controller-scoped player ("target opponent") and a fully
#     unrestricted recipient ("any other target"); only a POSITIVE type word
#     ever excludes;
#   * three bare zero-field player-designator marker tags the old scope arm
#     didn't recognize at all: ``ScopedPlayer`` ("that player" — a
#     per-player-loop back-reference), ``ParentTargetController`` ("that
#     permanent's/land's controller" — a controller is always a player, CR
#     102.1 / 109.5), ``DefendingPlayer`` ("defending player" — the attacked
#     player, CR 506.2);
#   * a damage effect buried inside a GRANTED activated/static ability's
#     ``.definition`` (a Sliver lord grant, an Aura-granted tap ability) the
#     flat per-unit ``effect_concepts`` walk never surfaces as its own
#     top-level concept — :func:`has_nested_damage_reaching_player`, the
#     ``has_nested_fight`` precedent (ADR-0038 W3 batch 3).
#
# MANDATORY SHED (ADR-0038 W4 session adjudication): the LEGACY regex mirror
# (``_signals_ir._DIRECT_DAMAGE_MIRROR``) carries a recipient-BLIND fallback
# clause (``\{t\}[^.]*?:[^.]*?deals? (?:\d+|x) damage``) meant to catch a
# tap-ability burn spell whose recipient parsing failed — but it fires on
# ANY ``{T}:``-costed damage ability regardless of recipient, over-firing on
# pure creature-removal tap abilities (Arashi, the Sky Asunder — "target
# creature with flying"; Ballista Squad — "target attacking or blocking
# creature", an ``Or`` of two Attacking/Blocking-typed alternatives, same
# bug) and the bare self-damage "deals N damage to you" drawback (Voltaic
# Visionary, Torture Chamber — a painland-style cost, CR 120.1's "an object
# that deals damage" excludes the controller unless explicitly targeted).
# Corpus audit: 88 live_only members are this exact class (66 ``Typed``, 22
# ``Or``-of-Attacking/Blocking) + 3 more are the self-damage variant — every
# one read structurally NOT-player-reaching; none is a genuine burn source.
# The key stays RESIDUAL this session (a diverse Unimplemented-residue tail
# remains — computed/complex damage amounts phase drops entirely, CR
# citations in the deferred report) but every structural class below is
# settled.


@pytest.mark.parametrize(
    "name",
    [
        "Lava Axe",  # "target player or planeswalker" — an Or(Player, Typed)
        "Aragorn, the Uniter",  # "target opponent" — Typed(tf=[], controller='Opponent')
        "Self-Destruct",  # "any other target" — Typed(tf=[], controller=None)
    ],
)
def test_direct_damage_or_and_empty_typed_reach(name):
    """(a) ``Or``-target recursion + empty-``type_filters`` ``Typed`` reach
    (CR 115.4 / 120.1): neither shape was readable by the pre-existing
    ``effect_reaches_player`` gate, which only recognized a NON-empty
    ``type_filters`` carrying the literal word "Player"."""
    assert ("direct_damage", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Ancient Runes",  # "that player" (per-player-loop) — ScopedPlayer
        "Ankh of Mishra",  # "that land's controller" — ParentTargetController
        "Falkenrath Perforator",  # "defending player" — DefendingPlayer
    ],
)
def test_direct_damage_bare_player_designator_marker_tags(name):
    """(a) three zero-field player-designator marker tags (CR 102.1 / 109.5
    controller-is-a-player; CR 506.2 defending player) the pre-existing scope
    arm didn't recognize at all."""
    assert ("direct_damage", "you", "") in _idents(name)


def test_direct_damage_nested_granted_ability():
    """(b) a damage effect buried inside an Aura-granted activated ability's
    ``GrantAbility.definition`` (Barbed Field's "Enchanted land has '{T}:
    ... deals 1 damage to any target.'") — :func:`has_nested_damage_
    reaching_player`, the ``has_nested_fight`` structural-fallback
    precedent."""
    assert ("direct_damage", "you", "") in _idents("Barbed Field")


def test_direct_damage_parent_target_sibling_aware():
    """A bare ``ParentTarget`` recipient is POSITION-relative (phase's
    back-reference tags bind to whatever earlier clause in the SAME ability
    produced the target) — ambiguous read alone, since a modal "instead"
    amendment quoting an earlier "target creature" carries the identical
    tag. Aggressive Sabotage's "Target player discards two cards. If this
    spell was kicked, it deals 3 damage to that player." resolves it by
    checking whether the SAME ability establishes an explicit player target
    elsewhere (:func:`_unit_has_player_target`) — it does (the Discard's own
    "target player"), so the ``ParentTarget`` damage recipient reaches."""
    assert ("direct_damage", "you", "") in _idents("Aggressive Sabotage")


@pytest.mark.parametrize(
    "name",
    [
        "Arashi, the Sky Asunder",  # {T}: ... target creature with flying — removal
        "Ballista Squad",  # {T}: ... target attacking or blocking creature — removal
    ],
)
def test_direct_damage_excludes_tap_ability_creature_only_shed(name):
    """MANDATORY SHED: the legacy ``{T}:``-costed damage regex fallback is
    recipient-BLIND and over-fires on pure creature removal (CR 120.1 — a
    creature/permanent-only recipient never reaches a player). The
    structural read correctly excludes both; the old regex mirror wrongly
    includes them (measured live_only, not reproduced)."""
    assert "direct_damage" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Voltaic Visionary",  # "{T}: ... deals 2 damage to you" — self, Controller
        "Torture Chamber",  # "deals damage to you" self + "target creature" removal
    ],
)
def test_direct_damage_excludes_bare_self_damage_shed(name):
    """MANDATORY SHED: a bare ``Controller`` recipient (the SOURCE's OWN
    controller — "deals N damage to you") is the incidental self-damage
    drawback, CR 120.1 — distinct from ``ParentTargetController``, which
    names a DIFFERENT (targeted/tracked) object's controller. The legacy
    regex mirror's recipient-blind ``{T}:``/bare-``to you`` fallback wrongly
    includes both (measured live_only, not reproduced)."""
    assert "direct_damage" not in _keys(name)


# ── ADR-0038 W5 tails: direct_damage (recovery.ALLOWLIST "damage" row) ───────
#
# Re-measured in a fresh worktree at the W4-giants HEAD: joined=31622, both
# 1157->1534, live_only 535->158 (unchanged from W4's own measurement — no
# drift). The diverse ~67-member Unimplemented-residue tail W4 banked as
# genuinely unrecoverable (computed damage amounts phase drops the WHOLE
# clause for) splits into two sub-classes on closer read: 85 corpus-wide
# residues tokenize to the shared clause grammar's pre-existing "damage" verb
# token (``deal[s] ... damage``) — 29 overlap direct_damage's own residual
# tail. Recovering those needs a recovery.ALLOWLIST row (not a NEW grammar
# verb — "damage" was already wired into ``_VERB`` for a different consumer)
# plus a LANE-level raw-text direction gate (a recovered node carries no
# typed ``target`` field): CR 120.1 "any target" / "each opponent" / "that
# player" / "defending player" / "target player" all reach; a bare "to you"
# stays the incidental self-damage exclusion (Iron Mastiff's own 1-9 d20 row
# never matches alone — its 10-19/20 sibling rows still fire the unit); a
# bare "target creature" (Whipkeeper) correctly stays excluded, joining the
# pre-existing creature-only shed class rather than closing a gap.
#
# Full-corpus ALL-KEYS before/after diff (recovery.ALLOWLIST with vs without
# the "damage" row): 32 changed cards, every gain scoped to ``direct_damage``
# except two adjudicated, benign side effects verified NOT to regress any
# pinned test (``include_membership``-gated, off by default in ``_idents``):
# (1) Crimson Honor Guard / Deathforge Shaman lose the STILL-residual
# ``voltron_matters`` key's OWN already-adjudicated "commander-damage
# MEMBERSHIP-fallback shed" fallback tell (see that key's own
# ``_STAGE4_RESIDUAL`` comment) — a genuine correction: once the card's
# damage effect is correctly read as its OWN burn plan, the generic
# commander-damage voltron guess correctly backs off; (2) Deathforge Shaman /
# Voracious Dragon gain ``wants_cloning`` LOW (a PROMOTED, production key) —
# their now-visible ETB damage effect correctly satisfies
# ``has_self_etb_value``'s "valuable ETB" test, a genuine improvement.
#
# Measured after the row: both 1534->1562, live_only 158->130 (28 closed —
# the 29-card overlap minus Whipkeeper, which correctly joins the shed class
# instead), crosswalk_only 119->123 (+4 genuine beyond-legacy gains: legacy's
# OWN oracle-text regex mirror, independent of this clause grammar, misses
# Enchanter's Bane / Searing Rays / Spiteful Repossession / Rumbling
# Aftershocks entirely). live_only STILL != exactly the shed class (Judgment
# Bolt / Liquid Fire / Synchronized Spellcraft / Cruel Sadist's second
# damage-to-controller clause is SILENTLY DROPPED by phase — no residue node
# at all, confirmed via direct tree dump, needs phase parser work; Vexing
# Arcanix's "target player" itself is lost upstream of the Unimplemented
# tail, RevealTop reads ``player=Controller()`` instead) — key stays
# RESIDUAL. CR 120.1 / 120.3 verified via rules-lookup this session.


def test_damage_recovery_row_closes_computed_amount_tail():
    """Soulblast's "deals damage to any target equal to the total power of
    the sacrificed creatures" (CR 120.1) — a total-power sacrifice tally
    phase's own amount grammar can't structure — lands as an Unimplemented
    residue the recovery.ALLOWLIST "damage" row re-decorates to
    "deal_damage"; the raw residue's "any target" phrase satisfies
    ``_RECOVERED_DAMAGE_REACH``."""
    assert ("direct_damage", "you", "") in _idents("Soulblast")


@pytest.mark.parametrize(
    "name",
    [
        "Mjölnir, Storm Hammer",  # "each opponent equal to the number of..."
        "Crimson Honor Guard",  # "unless"-guarded "to that player"
        "Curse Artifact",  # "unless"-guarded "to that player"
        "Deathforge Shaman",  # kicker-scaled "target player or planeswalker"
    ],
)
def test_direct_damage_recovered_reach_words(name):
    """The recovered-node raw-read direction gate (no typed ``target`` field
    survives a computed-amount Unimplemented residue): "each opponent" /
    "that player" / "target player or planeswalker" all satisfy
    ``_RECOVERED_DAMAGE_REACH`` (CR 120.1). An "unless" guard on the damage
    (Crimson Honor Guard / Curse Artifact) doesn't change the recipient —
    still a genuine burn source, just a punisher/upkeep-tax shape."""
    assert ("direct_damage", "you", "") in _idents(name)


def test_direct_damage_recovered_modal_table_defending_and_opponent_reach():
    """Iron Mastiff's d20 modal table has THREE separate damage rows in ONE
    triggered ability: "1-9: ... to you" (self, correctly excluded — the
    incidental self-damage exclusion applies to a recovered node too),
    "10-19: ... to defending player", "20: ... to each opponent". The unit
    fires on the FIRST matching concept-node; the "defending player"/"each
    opponent" sibling rows reach even though the "to you" row alone would
    not (CR 506.4c defending player)."""
    assert ("direct_damage", "you", "") in _idents("Iron Mastiff")


def test_direct_damage_recovered_creature_only_stays_excluded():
    """Whipkeeper's "deals damage to target creature equal to the damage
    already dealt to it" (CR 120.1) recovers to "deal_damage" (the amount is
    a computed reference phase drops) but its recipient phrase is bare
    "target creature" — no player-reach word — so ``_RECOVERED_DAMAGE_REACH``
    correctly excludes it. Joins the pre-existing creature-only tap-ability
    shed class rather than closing a genuine gap."""
    assert "direct_damage" not in _keys("Whipkeeper")


def test_direct_damage_recovery_false_senses_excluded():
    """Illusionary Mask's face-up-replacement clause LIST ("assigns or deals
    damage, is dealt damage, or becomes tapped" — CR 707.4a) and Skyway
    Robber's Escape rider (a granted trigger's quoted CONDITION mentioning
    "deals combat damage to a player", CR 510.1c — a categorically different
    mechanism than a spell/ability's own damage effect) are BOTH rejected at
    the recovery seam (``_NON_DAMAGE_SENSE``) — neither is a CR 120.1
    direct-damage EFFECT."""
    assert "direct_damage" not in _keys("Illusionary Mask")
    assert "direct_damage" not in _keys("Skyway Robber")


def test_direct_damage_beyond_legacy_gain_recovered_node():
    """Enchanter's Bane ("target enchantment deals damage equal to its mana
    value to its controller unless that player sacrifices it") and Rumbling
    Aftershocks ("deal damage to any target equal to the number of times
    that spell was kicked") are BEYOND-legacy gains: legacy's OWN oracle-
    text regex mirror (``_signals_ir._DIRECT_DAMAGE_MIRROR``, independent of
    this shared clause grammar) misses both entirely — the crosswalk's
    structural read is now MORE correct than legacy for this class, not
    merely reproducing it (CR 120.1)."""
    assert ("direct_damage", "you", "") in _idents("Enchanter's Bane")
    assert ("direct_damage", "you", "") in _idents("Rumbling Aftershocks")


# ── ADR-0038 W6 endgame: direct_damage (DamageAll.target reach + sheds) ──────


@pytest.mark.parametrize(
    "name",
    [
        "Aurelia, the Law Above",  # "deals 3 damage to each of your opponents"
        "Chandra, the Firebrand",  # a +1 loyalty deals damage to any target
    ],
)
def test_direct_damage_damage_all_target_reach(name):
    """(a) a ``DamageAll`` effect with NO ``player_filter`` can still reach a
    player through its ``target`` field, via the SAME
    :func:`~mtg_utils._card_ir.crosswalk._damage_target_reaches_player`
    discriminator ``DealDamage`` already uses (CR 120.1). Full-corpus scan:
    253 commander-legal ``DamageAll`` nodes carry no ``player_filter``; 238
    are Pyroclasm-shaped creature-typed sweeps (stay excluded — non-empty
    ``type_filters``, no "Player" word) and 15 are a multi-target burn spell
    or "each of your opponents" ability that serializes its recipient into
    ``target`` instead (this pair)."""
    assert ("direct_damage", "you", "") in _idents(name)


def test_direct_damage_excludes_creature_typed_damage_all_shed():
    """The SAME ``DamageAll.target`` reach carefully does NOT widen the
    Pyroclasm-shaped creature-only sweep: a non-empty ``type_filters``
    without the word "Player" stays removal, not burn (CR 120.1)."""
    assert "direct_damage" not in _keys("Pyroclasm")


@pytest.mark.parametrize(
    "name",
    [
        "Isengard Unleashed",  # damage DOUBLER (CR 614.1 replacement effect)
        "The Red Terror",  # damage-MATTERS trigger CONDITION, not its own effect
        "Charm Peddler",  # damage PREVENTION effect (CR 615.1) — deals none
    ],
)
def test_direct_damage_excludes_doubler_matters_prevention_shed(name):
    """MANDATORY SHED (ADR-0038 W6 endgame): a damage DOUBLER ("if a source
    you control would deal damage ... it deals double/triple that damage
    instead" — a CR 614.1 replacement effect), a damage-MATTERS trigger
    reading someone ELSE's damage as its trigger CONDITION rather than
    dealing its own (CR 603.2), and a damage-PREVENTION effect (CR 615.1 —
    deals no damage at all) are three categorically different, already-
    separate lanes from ``direct_damage`` per this module's own docstring
    ("Damage DOUBLERS are a separate lane"). None of the three has a
    ``DealDamage``/``DamageAll``/``DamageEachPlayer`` effect of ITS OWN
    reaching a player."""
    assert "direct_damage" not in _keys(name)


# ── ADR-0038 W4 giant: enchantments_matter (structural arms + verified CR) ───


@pytest.mark.parametrize(
    "name",
    [
        "Ironclad Slayer",  # "return target Aura or Equipment card ... to your hand"
        "Retether",  # "Return each Aura card from your graveyard to the battlefield"
        "Iridescent Drake",  # "put target Aura card from a graveyard onto the bfield"
    ],
)
def test_enchantments_matter_aura_subtype_recursion(name):
    """AURA-SUBTYPE RECURSION fallback (:func:`_type_recursion_lanes`): a
    graveyard-recursion target filtered to the SUBTYPE ``Aura`` (not the
    core type ``Enchantment``) carries ``card_types=()`` in phase's typed
    filter — ``_typed_matters_lanes`` alone returns nothing, so the
    recursion arms (``change_zone`` / ``put_library_position`` /
    ``cast_from_zone``) need the Aura-subtype fallback. CR 303.4: Aura is
    an Enchantment subtype, so a subtype-only recursion target still opens
    a LOOSE ``enchantments_matter`` member."""
    assert ("enchantments_matter", "you", "") in _idents(name)


def test_enchantments_matter_and_condition_descent():
    """AND-CONDITION LEAF descent (:func:`_condition_leaves`): "if you
    control an artifact and an enchantment" (When We Were Young, Okiba
    Salvage, Banishing Slash) types as ONE ``T_condition__And`` wrapping
    TWO ``QuantityCheck`` leaves (one per type) — the flat ``tag_of``
    switch on the condition-gate arm can't read a compound tag directly,
    so it needs to descend to the leaves first. CR 603.4 (the "intervening
    if" / conditional-ability check applies per stated condition)."""
    assert ("enchantments_matter", "you", "") in _idents("When We Were Young")
    assert ("enchantments_matter", "you", "") in _idents("Okiba Salvage")
    assert ("enchantments_matter", "you", "") in _idents("Banishing Slash")


def test_enchantments_matter_graveyard_recursion_mirror():
    """``_ENCHANTMENTS_MATTER_MIRROR`` port (the artifacts-sibling regex
    mirror, byte-identical from ``_signals_ir``): "Return ... target
    enchantment card ... from your graveyard to your hand" (Reconstruct
    History) is a MODAL multi-type recursion phase structures as several
    SEPARATE single-target effects, not one type-filtered node the
    structural recursion arm reads — the last-resort per-clause mirror
    catches it (CR 115.1/400.7 — a modal "up to one target X card" clause
    per type)."""
    assert ("enchantments_matter", "you", "") in _idents("Reconstruct History")


def test_enchantments_matter_constellation_mirror():
    """``_ENCHANTMENTS_MATTER_MIRROR`` port: "Whenever a creature or
    enchantment you control enters this turn, draw a card" (Rite of
    Harmony) is a constellation-style ETB trigger on an INSTANT (a
    Flashback spell payoff, not a permanent's own triggered ability) —
    phase structures it, but past this key's structural arm reach; the
    mirror catches it (CR 603.2 — triggered abilities)."""
    assert ("enchantments_matter", "you", "") in _idents("Rite of Harmony")


def test_enchantments_matter_affinity_keyword_line():
    """AFFINITY-FOR-ENCHANTMENTS doer (the enchantment sibling of the
    existing AFFINITY-FOR-EQUIPMENT arm): "Affinity for enchantments"
    (Brine Giant) is a bare KEYWORD LINE — the reminder text carrying "for
    each enchantment you control" is stripped by ``_kept`` (parenthetical),
    so the ``you control`` regex branch never sees it, and phase's raw
    keyword node isn't in the typed substrate's unit walk. CR 702.41a
    ("Affinity for [text]" means "costs {1} less ... for each [text] you
    control")."""
    assert ("enchantments_matter", "you", "") in _idents("Brine Giant")


@pytest.mark.parametrize(
    "name",
    [
        "Gaius van Baelsar",  # "Each player sacrifices ... an enchantment of choice"
        "Pick Your Poison",  # "Each opponent sacrifices ... an enchantment of choice"
        "Simplify",  # "Each player sacrifices an enchantment of their choice"
    ],
)
def test_enchantments_matter_excludes_enchantment_edict_shed(name):
    """MANDATORY SHED (ADR-0038 W4 session adjudication): "Each
    player/opponent sacrifices an enchantment of their choice" is an EDICT
    — the SACRIFICER is a DIFFERENT player than the one who ends up with
    fewer enchantments, so this is removal/disruption, not a "my deck
    wants enchantments" build-around (CR 701.21a — a player can only
    sacrifice a permanent THEY control; an edict's mislabeled
    ``controller: You`` target filter is the SAME shape
    ``_sac_is_edict`` already rejects for the artifacts sibling —
    Baleful Beholder's "Each opponent sacrifices an enchantment")."""
    assert "enchantments_matter" not in _keys(name)


def test_enchantments_matter_excludes_symmetric_library_reset_shed():
    """MANDATORY SHED (ADR-0038 W4 session adjudication): Harmonic
    Convergence's "Put all enchantments on top of their owners' libraries"
    is a SYMMETRIC reset (the target filter's ``controller`` is unset —
    it moves YOUR enchantments AND every opponent's) — a hate/answer
    effect for an enchantment-heavy table, not a "my deck wants
    enchantments" build-around (CR 205.2 defines Enchantment as the
    affected card type; the symmetric-controller exclusion mirrors the
    artifacts sibling's TYPE-DIES doer, which excludes a symmetric
    "any artifact dies" punisher the same way)."""
    assert "enchantments_matter" not in _keys("Harmonic Convergence")


@pytest.mark.parametrize(
    ("name", "lane"),
    [
        # The named-Aura-attached shape phase's token grammar can't
        # structure — the whole for-each-target clause parks as ONE
        # Unimplemented residue; the make_token ALLOWLIST row recovers it
        # and the raw-read branch sees "Aura enchantment token". This was
        # enchantments_matter's LAST genuine gap at promotion.
        ("Smoke Spirits' Aid", "enchantments_matter"),
        # "create a white and black Spirit enchantment creature token" —
        # same recovered shape, plain enchantment-creature wording.
        ("Daxos the Returned", "enchantments_matter"),
        # "For each different result, create a 1/1 white Clown Robot
        # artifact creature token" — a RollDie modal bullet phase parks as
        # Unimplemented; the artifact word routes the artifacts sibling.
        ("Circuits Act", "artifacts_matter"),
    ],
)
def test_recovered_make_token_type_words_route_matter_lanes(name, lane):
    """ADR-0038 post-giants batch (CR 111.2 "create" / 205.3g predefined
    artifact-token subtypes, verified via rules-lookup this session): a
    ``make_token`` node recovered off an Unimplemented residue keeps the
    phase wrapper as its ``.node`` (no typed token subject), so the
    artifacts/enchantments lane reads the create-clause's own type words
    — the dig_until / hand_revealed recovered-node precedent."""
    assert (lane, "you", "") in _idents(name)
