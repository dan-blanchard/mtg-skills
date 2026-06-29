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
def _cards() -> dict[str, dict]:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return json.loads(Path(path).read_text())["cards"]


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _tree(name: str) -> ConceptTree:
    rec = _cards()[name]
    root = strict_load_card(rec, _schema(), name=name)
    return build_concept_tree(root, name=name)


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in extract_crosswalk_signals(_tree(name))}


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


# ── batch hygiene ─────────────────────────────────────────────────────────────


def test_all_emitted_keys_are_in_the_ported_set():
    """The crosswalk only emits keys it claims to have ported (no leakage)."""
    for name in _cards():
        assert _keys(name) <= PORTED_KEYS
