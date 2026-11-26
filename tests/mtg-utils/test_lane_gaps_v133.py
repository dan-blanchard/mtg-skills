"""Reads that learned a shape phase v0.133.0 wrote anew (pin bump of 2026-11-25)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import exile_pile_counter_kind
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


def _pile_kinds(name: str) -> list[str | None]:
    return [
        exile_pile_counter_kind(unit.node)
        for tree in trees_for(test_card(name))
        for unit in tree.units
        if unit.origin == "static"
    ]


def test_a_play_from_exile_static_over_a_counter_marked_pile_is_exile_matters():
    """Tinybones, Bauble Burglar's "you may play cards you don't own with stash
    counters on them from exile": phase v0.133.0 types it as an
    ``ExileCastPermission`` static over a ``CounterLinked`` pool (it parked the
    clause before), so the pile of stash-marked cards in exile is the resource."""
    assert "stash" in _pile_kinds("Tinybones, Bauble Burglar")
    assert "exile_matters" in _keys("Tinybones, Bauble Burglar")


@pytest.mark.parametrize("name", ["Nightveil Specter", "Uba Mask"])
def test_a_play_from_exile_static_over_its_own_pile_names_no_counter(name):
    """A permission over the cards the card itself exiled (a ``Persistent`` or
    ``ThisTurn`` pool) marks no pile with a counter."""
    assert set(_pile_kinds(name)) <= {None}


@pytest.mark.parametrize(
    ("name", "key"),
    [
        # "perpetually gains 'This spell costs {1} less to cast.'"
        ("Scalar Scholar", "cost_reduction"),
        # "Enchanted land has 'Untap this land during each other player's untap step.'"
        ("Urban Burgeoning", "untap_engine"),
    ],
)
def test_a_quoted_static_grant_reads_as_its_mode(name, key):
    """Phase v0.133.0 keeps a quoted static's whole definition
    (``GrantStaticAbility``) where it wrote ``AddStaticMode``; the reads take
    its mode through ``crosswalk.added_static_mode``, so both forms read alike."""
    assert key in _keys(name)


# ── Dan's rulings on the bump (2026-11-25) ─────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "key", "present"),
    [
        # backup: "can't be blocked by creatures with power 2 or less" granted
        # to the target (CR 702.165a) — a gift, an ability grant
        ("Chomping Kavu", "keyword_grant_target|you|ability", True),
        # "gain 'This creature can't block'" — a drawback, never a grant
        ("Incite Hysteria", "keyword_grant_target|you|ability", False),
        # the grant to the card itself is no grant to another creature
        ("Ogre Marauder", "keyword_grant_target|you|ability", False),
    ],
)
def test_a_quoted_static_grant_is_an_ability_grant_only_where_it_gives(
    name, key, present
):
    idents = {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}
    assert (key in idents) is present


@pytest.mark.parametrize(
    ("name", "key"),
    [
        # the returned creature is an opponent's
        ("Immortal Obligation", "keyword_grant_target|you|ability"),
        ("Immortal Obligation", "creatures_matter|you|"),
        # a hand attack's discard filter names no plan of yours
        ("Shatter Assumptions", "colorless_matters|you|"),
        ("Trapfinder's Trick", "subtype_ref|you|Trap"),
    ],
)
def test_what_lands_only_on_an_opponents_cards_is_never_yours(name, key):
    idents = {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}
    assert key not in idents


def test_a_hand_attacks_spell_type_is_still_named():
    """Trap is a spell type (CR 205.3k): the subtype survives, on any side."""
    idents = {
        f"{s.key}|{s.scope}|{s.subject}" for s in test_signals("Trapfinder's Trick")
    }
    assert "subtype_ref|any|Trap" in idents


@pytest.mark.parametrize("name", ["Hive Mind", "Transgress the Mind"])
def test_a_filter_word_that_names_no_cr_subtype_is_no_subtype_ref(name):
    """Hive Mind's "choose new targets for their copy" typed as a ``New``
    filter (phase v0.133.0) and Transgress the Mind's stray ``A``: no CR 205.3
    subtype, so no ``subtype_ref``."""
    assert not any(s.key == "subtype_ref" for s in test_signals(name))


@pytest.mark.retirement_canary
def test_parked_opponent_spell_tax_canary():
    """Soul Partition's "A spell cast by an opponent this way costs {2} more to
    cast": phase v0.133.0 parks it (``unrecognized_clause_head``); the
    ``opponent_spell_tax`` recovery token reads it as a stax tax. Only
    opponents' spells are taxed, so no ``symmetric_stax``."""
    recovered = [
        c
        for tree in trees_for(test_card("Soul Partition"))
        for c in tree.iter_concepts()
        if c.recovered_by == "opponent_spell_tax"
    ]
    assert recovered, (
        "recovery opponent_spell_tax: RETIRE-READY — phase types Soul Partition's "
        "surcharge. Delete the opponent_spell_tax token, its clause_grammar row "
        "and this canary, if no other card still fires it."
    )
    keys = {s.key for s in test_signals("Soul Partition")}
    assert "stax_taxes" in keys
    assert "symmetric_stax" not in keys
