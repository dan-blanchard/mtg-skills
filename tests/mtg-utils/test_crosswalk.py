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
    never base_pt_set; a flat pump (Giant Growth) has no Set mods."""
    assert "base_pt_set" not in _keys("Living Plane")
    assert "base_pt_set" not in _keys("Giant Growth")


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


def test_target_player_draws_excludes_scoped_player_group_draw():
    """Fix (d): Academy Loremaster's "that player may draw" under an
    each-player draw-step trigger is a ``ScopedPlayer`` GROUP draw — the
    card_draw_engine each-arm, never a directed gift (the live routing to
    target_player_draws is the documented divergence)."""
    assert "target_player_draws" not in _keys("Academy Loremaster")
    assert ("card_draw_engine", "each", "") in _idents("Academy Loremaster")


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
    (a LOW that dedupes under the HIGH ident)."""
    assert ("type_matters", "you", "Goblin") in _idents("Krenko, Mob Boss")
    assert _confidences("Krenko, Mob Boss", "type_matters") == {"high"}


def test_type_matters_gates_no_subject_no_signal():
    """A generic anthem (Glorious Anthem) captures no subject; a Food-token
    maker's profile is NON_CREATURE_TOKEN-denied (Gilded Goose never mints
    a Food subject — CR 111.10 / 205.3g; its Bird membership row is the
    separate own-subtype arm)."""
    assert "type_matters" not in _keys("Glorious Anthem")
    goose = _idents("Gilded Goose")
    assert ("type_matters", "you", "Food") not in goose
    assert ("type_matters", "you", "Bird") in goose


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
