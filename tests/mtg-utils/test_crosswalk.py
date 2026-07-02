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
from mtg_utils._deck_forge.crosswalk_signals import (
    PORTED_KEYS,
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


@pytest.mark.parametrize("name", ["Inspiring Call", "Bioshift"])
def test_plus_one_matters_structural_arms(name):
    assert ("plus_one_matters", "you", "") in _idents(name)


def test_any_counter_matters_predicate_arm():
    assert ("any_counter_matters", "you", "") in _idents("Concord with the Kami")


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
    ["Sram, Senior Edificer", "Reyav, Master Smith"],  # cast-spell / attachment-state
)
def test_voltron_matters_payoff(name):
    assert ("voltron_matters", "you", "") in _idents(name)


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


def test_goad_makers_structural_and_keyword():
    # Disrupt Decorum carries a GoadAll effect AND the Scryfall Goad keyword.
    assert ("goad_makers", "opponents", "") in _idents("Disrupt Decorum")


def test_regenerate_makers_fires():
    assert ("regenerate_makers", "you", "") in _idents("River Boa")


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


def test_copy_permanent_and_clone():
    # Crystalline Resonance copies a Permanent → copy_permanent + clone_makers.
    idents = _idents("Crystalline Resonance")
    assert ("copy_permanent", "you", "") in idents
    assert ("clone_makers", "you", "") in idents


@pytest.mark.parametrize("name", ["Clone", "Spark Double"])
def test_clone_makers_fires(name):
    assert ("clone_makers", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Twincast", "Mirror Match"])
def test_clone_makers_excludes_spell_and_token_copy(name):
    """A spell-copy (Twincast) and a token-copy (Mirror Match — a
    ``CopyTokenBlockingAttacker``) are NOT creature clones (Dan's clone-vs-token-copy
    boundary, CR 707.1)."""
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


def test_modified_matters_payoff():
    """Chishiro places +1/+1 counters on modified creatures you control — a Modified
    filter predicate, controller you → modified_matters (CR 700.9)."""
    assert ("modified_matters", "you", "") in _idents("Chishiro, the Shattered Blade")


def test_modified_matters_excludes_plain_anthem():
    """A generic creatures-you-control anthem (Glorious Anthem) carries no Modified
    predicate → no modified_matters."""
    assert "modified_matters" not in _keys("Glorious Anthem")


def test_multicolor_matters_anthem():
    """Knight of New Alara anthems multicolored creatures you control — a ColorCount
    GE 2 predicate, controller you → multicolor_matters (CR 105.2)."""
    assert ("multicolor_matters", "you", "") in _idents("Knight of New Alara")


@pytest.mark.parametrize("name", ["Forsaken Monument", "Conduit of Ruin"])
def test_colorless_matters(name):
    """A ColorCount EQ 0 reference (Forsaken Monument's anthem; Conduit of Ruin's
    colorless tutor, unscoped) → colorless_matters you (CR 105.2)."""
    assert ("colorless_matters", "you", "") in _idents(name)


def test_color_lanes_do_not_cross():
    """A multicolor anthem (Knight of New Alara) is not colorless, and a colorless
    anthem (Forsaken Monument) is not multicolor — the comparator/count splits."""
    assert "colorless_matters" not in _keys("Knight of New Alara")
    assert "multicolor_matters" not in _keys("Forsaken Monument")


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


def test_cost_reduction_excludes_ramp_rock():
    """A flat ramp rock (Sol Ring) carries no ModifyCost static → no cost_reduction."""
    assert "cost_reduction" not in _keys("Sol Ring")


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


def test_convoke_makers_excludes_granter():
    """Chief Engineer GRANTS convoke ("spells you cast have convoke") and carries no
    Convoke keyword → the keyword lane does not fire (the granter is a documented
    live_only tail)."""
    assert "convoke_makers" not in _keys("Chief Engineer")


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


@pytest.mark.parametrize(
    ("name", "should_fire"),
    [
        ("Burgeoning", True),  # put a land from HAND onto the battlefield
        ("Elvish Rejuvenator", True),  # Dig destination Battlefield, Land
        ("Planar Genesis", False),  # Dig destination HAND — card selection
        ("Sneak Attack", False),  # a CREATURE cheat → cheat_into_play
    ],
)
def test_extra_land_drop_zone_and_type_gates(name, should_fire):
    """extra_land_drop fires on a land PUT into play (CR 305.9 — a put, not a
    play); a dig-to-hand and a creature cheat stay out (checklist #2/#4)."""
    assert (("extra_land_drop", "you", "") in _idents(name)) is should_fire


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
    ("name", "should_fire"),
    [
        ("Wrath of God", True),  # DestroyAll creatures
        ("Blasphemous Act", True),  # DamageAll creatures
        ("Merciless Eviction", True),  # mass exile (ChangeZoneAll → Exile)
        ("Languish", True),  # negative PumpAll — typed -4/-4 (structural)
        ("Armageddon", False),  # destroy all LANDS → land_destruction
        ("Living Death", False),  # graveyard-zone mass exile → GY recursion
    ],
)
def test_mass_removal_arms_and_gates(name, should_fire):
    """mass_removal fires the four typed wipe arms and excludes the land-only
    sweep and the graveyard mass-exile (CR 115.10 / 406, checklist #2)."""
    assert (("mass_removal", "you", "") in _idents(name)) is should_fire


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
    ("name", "should_fire"),
    [
        ("Commander's Insignia", True),  # creatures YOU control team anthem
        ("Craterhoof Behemoth", True),  # one-shot team scaling anthem
        ("Coat of Arms", False),  # symmetric "each creature" — controller any
        ("Shivan Dragon", False),  # single-target self pump
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


# ── batch hygiene ─────────────────────────────────────────────────────────────


def test_all_emitted_keys_are_in_the_ported_set():
    """The crosswalk only emits keys it claims to have ported (no leakage)."""
    for name in _cards():
        assert _keys(name) <= PORTED_KEYS
