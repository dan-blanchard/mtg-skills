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


# ── batch hygiene ─────────────────────────────────────────────────────────────


def test_all_emitted_keys_are_in_the_ported_set():
    """The crosswalk only emits keys it claims to have ported (no leakage)."""
    for name in _cards():
        assert _keys(name) <= PORTED_KEYS
