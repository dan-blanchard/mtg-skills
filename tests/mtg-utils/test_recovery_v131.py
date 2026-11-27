"""Real-card pins for the recovered readings the phase v0.131.0 pin bump taught:
clauses phase now fails closed on and parks as residues (``unparsed_verb_arguments``
and kin) that it typed at v0.118.0. Each recovered reading only runs on an
``Unimplemented`` node, so a phase fix retires it by itself; the clauses no
recovered reading can carry are bridge-ledger rows, retired by
``test_bridge_ledger``'s gap check."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


# ── A parked sweep (``recovery.EACH_PERMANENT``; ``removal_tutors.recovered_sweep``)


@pytest.mark.parametrize(
    "name",
    [
        "Harsh Mercy",  # "Destroy all creatures that aren't of a type chosen …"
        "Celestial Judgment",  # "Destroy each creature not chosen this way"
        "Tropical Storm",  # "deal X damage to each creature with flying and …"
        "Disorder",  # "deal 2 damage to each white creature and each player …"
    ],
)
def test_a_parked_destroy_or_burn_sweep_is_mass_removal(name):
    idents = _idents(name)
    assert ("mass_removal", "you", "") in idents
    # its creatures die (CR 700.4): the sweep half of a mass-death turn
    assert ("mass_removal", "you", "creature") in idents


def test_a_parked_exile_sweep_is_mass_removal_without_deaths():
    # "exile each creature not chosen by any player this way": exiled, not dead
    idents = _idents("Sculpted Sunburst")
    assert ("mass_removal", "you", "") in idents
    assert ("mass_removal", "you", "creature") not in idents


@pytest.mark.parametrize(
    "name",
    [
        # "deal damage to each opponent equal to the number of tapped creatures
        # that opponent controls": each player, not each creature
        "Mjölnir, Storm Hammer",
        # "it deals 2 damage to each creature blocking it": one combat's
        # creatures, not the board
        "Trailblazer's Torch",
    ],
)
def test_a_parked_burn_over_players_or_one_combat_is_no_sweep(name):
    assert not any(k == "mass_removal" for k, _s, _t in _idents(name))


def test_a_parked_mass_bounce_is_mass_bounce_and_tempo():
    # "Return all nonland permanents not chosen this way to their owners' hands"
    idents = _idents("Consuming Tide")
    assert ("mass_bounce", "any", "") in idents
    assert ("bounce_tempo", "you", "") in idents


# ── A parked burn to a player other than you is life loss (CR 120.3a) ───────────


@pytest.mark.parametrize(
    "name",
    [
        "Chandra's Flame Wave",  # "to target player and each creature …"
        "Flame Wave",  # "to target player or planeswalker and each creature …"
        "Incite Rebellion",  # "to that player and each creature that player …"
    ],
)
def test_a_parked_burn_to_another_player_drains(name):
    assert ("lifeloss_makers", "opponents", "") in _idents(name)


# ── A parked reanimation you perform is yours (CR 110.2a) ───────────────────────


@pytest.mark.parametrize("name", ["Necromantic Selection", "Zero Point Ballad"])
def test_a_parked_reanimation_you_perform_is_recursion(name):
    # "return a creature card put into a graveyard this way to the battlefield
    # under your control"
    idents = _idents(name)
    assert ("creature_recursion", "you", "battlefield") in idents
    assert ("permanent_recast", "you", "reanimate") in idents


def test_a_parked_each_player_mass_reanimation_is_recursion_en_masse():
    # "return all creature cards of a type chosen this way from their graveyard
    # to the battlefield": each player's own, every one of them
    idents = _idents("Patriarch's Bidding")
    assert ("creature_recursion", "you", "battlefield") in idents
    assert ("creature_recursion", "you", "mass") in idents


def test_a_parked_reanimation_from_an_opponents_graveyard():
    # "for each opponent, put a creature card from that player's graveyard … onto
    # the battlefield under your control": a creature that reanimates
    # (reanimator), but out of an opponent's graveyard only — the recursion
    # lanes' graveyard-hate gate (crosswalk.graveyard_recursion's Opponent veto)
    idents = _idents("The Weaver King")
    assert ("reanimator", "you", "") in idents
    assert not any(k == "creature_recursion" for k, _s, _t in idents)


def test_a_parked_exile_is_a_cast_permissions_exile_source():
    # "exile all cards from that player's hand, then they draw that many cards.
    # You may play lands and cast spells from among the exiled cards …"
    assert ("cast_from_exile", "you", "") in _idents("Elder Brain")


# ── A parked counter removal (token ``remove_counter``) ─────────────────────────


def test_a_parked_counter_removal_from_exiled_cards_is_exile_matters():
    # "Then remove a time counter from each other card you own in exile"
    idents = _idents("Alaundo the Seer")
    assert ("exile_matters", "you", "") in idents
    # a removal of one niche kind is no kindless counter doer
    assert not any(k == "any_counter_makers" for k, _s, _t in idents)


# ── A prevention parked with a listed rider (``prevention_listed_rider``) ───────


@pytest.mark.parametrize("name", ["Bloatfly Swarm", "Sekki, Seasons' Guide"])
def test_a_prevention_with_a_listed_rider_is_damage_prevention(name):
    idents = _idents(name)
    assert ("damage_prevention", "you", "") in idents
    # "If damage would be dealt to ~": a shield of the card alone
    assert not any(k == "board_protection" for k, _s, _t in idents)


def test_a_parked_preventions_later_instruction_recovers_its_own_verb():
    # Sekki's "… and create that many 1/1 colorless Spirit creature tokens" is a
    # token the card makes, not part of the prevention's reading
    assert ("permanent_etb", "you", "put") in _idents("Sekki, Seasons' Guide")


# ── The seam's patterns, on lines no card parks today ───────────────────────────


@pytest.mark.parametrize(
    ("before", "who"),
    [
        ("Target player reveals their hand and discards", "target player"),
        ("When ~ enters, target player discards", "target player"),
        # synthetic: a second subject between the player and the verb
        ("Each opponent loses 1 life and you gain 1 life and draw", None),
        ("Target opponent reveals their hand, then discards", None),
    ],
)
def test_peeled_subject_reads_one_and_joined_verb(before, who):
    from mtg_utils._card_ir.recovery import _PEELED_SUBJECT_RX

    found = _PEELED_SUBJECT_RX.search(before)
    assert (found.group(1).lower() if found else None) == who


@pytest.mark.parametrize(
    ("clause", "board"),
    [
        ("destroy all creatures that aren't of a type chosen this way", True),
        ("destroy all artifacts and enchantments", True),
        ("exile each creature not chosen this way", True),
        # synthetic: cards in a zone, and one combat's creatures
        ("exile all artifact and enchantment cards from all graveyards", False),
        ("exile all artifact creature cards from all graveyards", False),
        ("destroy each creature blocking it", False),
    ],
)
def test_each_permanent_object_is_a_board_not_cards_in_a_zone(clause, board):
    import re

    from mtg_utils._card_ir.recovery import _EACH_PERMANENT_OBJECT

    head = r"\b(?:destroy|exile)\s+"
    assert (
        bool(re.search(head + _EACH_PERMANENT_OBJECT, clause, re.IGNORECASE)) is board
    )


@pytest.mark.parametrize("name", ["Antagonism", "Impatience"])
def test_a_parked_burn_on_each_players_step_hits_you_too(name):
    """ "At the beginning of each player's end step, ~ deals 2 damage to that
    player unless …": the step's player, you included — ``each``, never the
    opponents alone."""
    idents = _idents(name)
    assert ("lifeloss_makers", "each", "") in idents
    assert ("lifeloss_makers", "opponents", "") not in idents


# ── A basic land type names a land (CR 205.3i) ──────────────────────────────────


def test_a_parked_destroy_of_all_plains_is_land_destruction():
    """Raiding Party: "Then destroy all Plains that weren't chosen this way by
    any player" — parked, read as a sweep over lands (two ledger rows before)."""
    idents = _idents("Raiding Party")
    assert ("land_destruction", "you", "destroy") in idents
    assert ("mass_land_denial", "each", "destroy") in idents


def test_a_parked_sacrifice_of_forests_sacrifices_lands():
    # Wood Elemental: "As this creature enters, sacrifice any number of
    # untapped Forests."
    assert ("land_sacrifice_makers", "you", "") in _idents("Wood Elemental")


# ── A player's board named beside the player is a sweep ─────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # "deals 2 damage to target player and each creature that player controls"
        "Chandra's Flame Wave",
        # "to that player and each creature that player controls" (two ledger
        # rows before the seam marked the board)
        "Mob Verdict",
        "Incite Rebellion",
        # "to target player or planeswalker and each creature that player or
        # that planeswalker's controller controls"
        "Flame Wave",
    ],
)
def test_a_parked_burn_over_a_players_board_is_a_sweep(name):
    assert ("mass_removal", "you", "") in _idents(name)


def test_an_ultimates_sweep_is_out_of_reach():
    # Chandra, Flame's Fury's -8 is the same clause on a planeswalker's
    # ultimate, which mass_removal leaves out (a ledger row served it before).
    assert "mass_removal" not in {i[0] for i in _idents("Chandra, Flame's Fury")}


def test_a_parked_discard_after_anothers_revealed_hand_is_theirs():
    """Persecute: "Target player reveals their hand and discards all cards of
    that color" — a typed reveal plus a parked, subject-less "discard …"; the
    seam reads the revealing player as its actor, so it is no discard outlet
    of yours. (Shatter Assumptions, this test's card until phase v0.133.0,
    types its discards now, on the revealing player.)"""
    from mtg_utils._card_ir.recovery import OTHER_PLAYER
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    discards = [
        c
        for tree in trees_for(test_card("Persecute"))
        for unit in tree.units
        for c in unit.effects
        if c.recovered_by == "discard"
    ]
    assert discards
    assert all(OTHER_PLAYER in c.reading for c in discards)
    for name in ("Persecute", "Shatter Assumptions"):
        assert "discard_outlet" not in {i[0] for i in _idents(name)}


@pytest.mark.parametrize(
    ("clause", "land"),
    [
        ("destroy all Plains that weren't chosen this way", True),
        ("sacrifice any number of untapped Forests", True),
        # a count beside the object names no land (Quarry Colossus)
        ("put it beneath the top X, where X is the number of Plains", False),
        ("destroy target non-Island land", False),
    ],
)
def test_a_land_type_names_a_land_only_as_the_object(clause, land):
    from mtg_utils._card_ir.recovery import _names_a_land_type

    assert _names_a_land_type(clause) is land


def test_a_permission_another_player_gets_is_no_enters_payload():
    # Lightstall Inquisitor: "each opponent exiles a card from their hand and
    # may play that card for as long as it remains exiled" — theirs, not yours.
    assert "self_etb_payload" not in {i[0] for i in _idents("Lightstall Inquisitor")}


# ── A population phase types as one object (``recovery.mark_populations``) ──


def _marked(name: str, tag: str) -> list[bool]:
    from mtg_utils._card_ir.crosswalk import tag_of
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    return [
        c.population
        for t in trees_for(test_card(name))
        for u in t.units
        for c in u.effects
        if tag_of(c.node) == tag
    ]


def _raw_effects(name: str, tag: str) -> list[dict]:
    from mtg_utils.testkit import test_phase_records

    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == tag:
                out.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for rec in test_phase_records(name):
        walk(rec)
    return out


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "tag"),
    [
        # "Regenerate each creature you control", typed as Loxodon Hierarch
        # Avatar's "Regenerate target creature you control" is
        ("Wrap in Vigor", "Regenerate"),
        # "All permanents you control phase out", typed as Haystack's "Target
        # creature you control phases out" is
        ("Teferi's Protection", "PhaseOut"),
        # "Put a counter of that kind on each other creature you control"
        ("Contractual Safeguard", "PutChosenCounter"),
    ],
)
def test_population_mark_canary(name, tag):
    """Phase types these mass effects exactly as their targeted forms: one
    effect on a ``Typed`` filter, no ``*All`` variant, no ``All`` scope. The
    recovery stage marks the population (``ConceptNode.population``, read by
    ``crosswalk.acts_on_a_group``) from the text. Fails once phase gives the
    effect a mass form or a scope of its own: then read that and drop the
    mark's case."""
    raw = _raw_effects(name, tag)
    assert raw, f"population mark: RETIRE-READY — phase no longer types {name}'s {tag}"
    assert all(
        (e.get("target") or {}).get("type") == "Typed"
        and ((e.get("scope") or {}).get("type") != "All")
        for e in raw
    ), f"population mark: RETIRE-READY — phase scopes {name}'s {tag}; drop the mark"
    assert True in _marked(name, tag)
    assert ("own_target_spell", "you", "") not in _idents(name)


@pytest.mark.parametrize("name", ["Mending Touch", "Haystack"])
def test_a_targeted_peer_is_no_population(name):
    """ "Regenerate target creature", "Target creature you control phases out"."""
    tag = "Regenerate" if name == "Mending Touch" else "PhaseOut"
    assert True not in _marked(name, tag)


@pytest.mark.parametrize(
    ("text", "tags"),
    [
        ("Regenerate each creature you control.", {"Regenerate"}),
        ("All permanents you control phase out.", {"PhaseOut"}),
        ("Regenerate target creature.", set()),
        ("Target creature you control phases out.", set()),
        # "each" opens no subject of "phases out": the upkeep's
        ("At the beginning of each upkeep, enchanted creature phases out.", set()),
        # players, not objects
        ("Each opponent loses 2 life and creatures they control phase out.", set()),
        ("Regenerate each player.", set()),
        # a quoted ability is the granted object's own
        (
            (
                'Enchanted creature has "At the beginning of your upkeep, all '
                'creatures you control phase out."'
            ),
            set(),
        ),
        (
            (
                "All permanents other than Disciple of Caelus Nin and the chosen "
                "permanents phase out."
            ),
            {"PhaseOut"},
        ),
        (
            (
                "You gain protection from everything, and all permanents you "
                "control phase out."
            ),
            {"PhaseOut"},
        ),
    ],
)
def test_population_effects_grammar(text, tags):
    from mtg_utils._card_ir.clause_grammar import population_effects

    assert population_effects(text) == tags


# ── The backlog reads block (2026-11-27) ────────────────────────────────────────


def _concepts(name: str) -> list[str]:
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    test_signals(name)  # seeds the card's trees
    return [
        c.concept
        for t in trees_for(test_card(name))
        for u in t.units
        for c in u.effects
    ]


def test_a_serial_list_of_instructions_is_split():
    """ "If you can't, sacrifice it, put a +1/+1 counter on enchanted creature,
    and that creature gains flying" (Cocoon): the bare comma before "put" breaks
    the list too, so the counter on the enchanted creature is read."""
    assert _concepts("Cocoon").count("place_counter") == 2
    assert ("boosts_others", "you", "counters") in _idents("Cocoon")
    # "choose that player or a permanent they control, copy that spell, and …"
    assert ("spell_copy_makers", "you", "") in _idents("Zevlor, Elturel Exile")


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        (
            (
                "If you can't, sacrifice it, put a +1/+1 counter on enchanted "
                "creature, and that creature gains flying"
            ),
            [
                "put a +1/+1 counter on enchanted creature, and that creature gains flying"
            ],
        ),
        # no closing ", and" / ", then": no list
        ("If you do, sacrifice it, put a +1/+1 counter on it", []),
        # each item names its own player: left as it was
        (
            "discard a card, they lose 2 life, you draw a card, then you sacrifice ~",
            ["sacrifice ~"],
        ),
    ],
)
def test_serial_comma_grammar(text, parts):
    from mtg_utils._card_ir.recovery import ALLOWLIST, _later_clauses

    assert [p for _s, p in _later_clauses(text, ALLOWLIST)] == parts


@pytest.mark.retirement_canary
def test_parked_seek_canary():
    """ "Seek three nonland cards, then …" (Discover the Formula) parks as an
    ``unparsed_verb_arguments`` residue; the recovery stage's ``seek`` token
    reads it as phase's ``Seek`` concept (seek is the digital supplement's DD3:
    a card at random from your library). Fails once phase types the seek."""
    assert not _raw_effects("Discover the Formula", "Seek"), (
        "recovery seek token: RETIRE-READY — phase types Discover the Formula's "
        "seek; drop this case, and the token once no residue holds a seek"
    )
    assert "seek" in _concepts("Discover the Formula")
    assert ("seek_matters", "you", "") in _idents("Discover the Formula")


def test_another_players_seek_is_not_yours():
    # "exile target creature. Its controller seeks a creature card."
    assert "seek_matters" not in {k for k, _s, _t in _idents("Obscura Polymorphist")}


@pytest.mark.parametrize("name", ["Commander Liara Portyr", "Shellfish Scholar"])
def test_a_class_cost_reduction_is_no_cast_permission(name):
    """ "spells you cast from exile this turn cost {X} less to cast" is a cost
    reduction (CR 601.2f), never a permission to cast from that zone."""
    assert "cast_from_zone" not in _concepts(name)
    assert ("cost_reduction", "you", "") in _idents(name)


@pytest.mark.parametrize(
    ("text", "reduces"),
    [
        ("Spells you cast from your graveyard this turn cost {2} less to cast", True),
        (
            "spells you cast from exile this turn cost {X} less to cast, where X is 2",
            True,
        ),
        ("You may cast spells from your graveyard this turn", False),
        ("Instant spells you cast cost {1}{U} more to cast", False),
    ],
)
def test_class_cost_reduction_grammar(text, reduces):
    from mtg_utils._card_ir.clause_grammar import class_cost_reduction

    assert class_cost_reduction(text) is reduces
