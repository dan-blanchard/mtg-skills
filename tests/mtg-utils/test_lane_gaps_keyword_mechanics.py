"""Phase B lane fixes in ``lanes/keyword_mechanics.py`` (2026-10-20): the
spellcast spell-class subject, council votes, domain enablers, disjunctive and
keyword block triggers, mass / replacement graveyard hate, and the
cast_from_exile impulse subject. Real cards via ``mtg_utils.testkit``."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import residue_is, tag_of
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


# ── (1) spellcast_matters spell-class subject ──────────────────────────────


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Talrand, Sky Summoner", "instant_sorcery"),
        ("Monastery Swiftspear", "noncreature"),  # printed prowess, CR 702.108a
        ("Aetherflux Reservoir", "any"),
        ("Clarion Spirit", "second_spell"),  # "your second spell each turn"
        ("Ardbert, Warrior of Darkness", "color"),  # "a white spell"
    ],
)
def test_spellcast_subject_reads_the_watched_spell(name, subject):
    idents = _idents(name)
    assert "spellcast_matters|you|" in idents
    assert f"spellcast_matters|you|{subject}" in idents


def test_prowess_token_maker_is_a_noncreature_cast_payoff():
    """Goblin Wizardry's Wizards have prowess (a token keyword)."""
    idents = _idents("Goblin Wizardry")
    assert {"spellcast_matters|you|", "spellcast_matters|you|noncreature"} <= idents


def test_tribal_cast_trigger_gets_no_spellcast_subject():
    """A "whenever you cast an Elf spell" trigger stays the tribal lanes': the subject
    lane never adds the key to a card the bare lane leaves out."""
    assert "spellcast_matters" not in _keys("Lys Alana Huntmaster")


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Geist of Saint Thalia", "noncreature"),
        ("Goblin Electromancer", "instant_sorcery"),
    ],
)
def test_cost_reduction_subject_reads_the_discounted_spell(name, subject):
    assert f"cost_reduction|you|{subject}" in _idents(name)


# ── (2) voting ─────────────────────────────────────────────────────────────


def test_council_dilemma_residue_is_a_vote():
    assert "voting_makers|each|" in _idents("Lieutenants of the Guard")


def test_extra_vote_is_a_voting_payoff():
    """Ballot Broker's "While voting, you may vote an additional time" (CR
    701.38d) — phase's ``GrantsExtraVote`` static mode."""
    idents = _idents("Ballot Broker")
    assert "voting_matters|each|" in idents
    assert "voting_makers|each|" not in idents


@pytest.mark.retirement_canary
def test_council_vote_is_still_a_residue_canary():
    """Retirement canary for ``_voting_makers``' residue arm: phase v0.104.0
    parks the council's dilemma vote as an ``Unimplemented`` "vote for …"
    residue. Once phase types it as a ``Vote`` effect, delete the
    ``residue_is(c.node, "vote")`` arm and this canary."""
    nodes = [
        c.node
        for t in trees_for(test_card("Lieutenants of the Guard"))
        for u in t.units
        for c in u.effects
    ]
    assert any(residue_is(n, "vote") for n in nodes), (
        "Lieutenants of the Guard: RETIRE-READY — phase now types the vote "
        f"({sorted({tag_of(n) for n in nodes})})"
    )


# ── (3) domain enablers ────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Prismatic Omen", "Nylea's Presence"])
def test_basic_land_type_grant_is_a_domain_enabler(name):
    assert "domain_matters|you|" in _idents(name)


@pytest.mark.parametrize("name", ["Thran Portal", "Blood Moon"])
def test_self_typing_land_and_type_set_are_no_domain_enabler(name):
    assert "domain_matters" not in _keys(name)


# ── (4) block triggers ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Brushwagg",  # blocks or becomes blocked
        "Elder Gargaroth",  # attacks or blocks
        "Khenra Eternal",  # printed afflict
        "Konda, Lord of Eiganjo",  # printed bushido
        "Agility",  # granted flanking
        "Retaliation",  # granted "whenever this creature becomes blocked"
    ],
)
def test_block_trigger_is_blocked_matters(name):
    assert "blocked_matters|you|" in _idents(name)


def test_self_sacrifice_block_trigger_is_a_drawback():
    """Mardu Blazebringer: "When this creature attacks or blocks, sacrifice it
    at end of combat" — its drawback, no payoff for blocking."""
    assert "blocked_matters" not in _keys("Mardu Blazebringer")


# ── (5) opponent_exile_makers ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Soul-Guide Lantern", "Leyline of the Void", "Dauthi Voidwalker"]
)
def test_mass_and_replacement_graveyard_hate(name):
    assert "opponent_exile_makers|opponents|" in _idents(name)


@pytest.mark.parametrize("name", ["Kalitas, Traitor of Ghet", "Rest in Peace"])
def test_die_replacement_and_every_graveyard_are_not_opponent_hate(name):
    """Kalitas names the creature's controller (a "would die" replacement, CR
    404.1: a graveyard is its owner's); Rest in Peace hits every graveyard."""
    assert "opponent_exile_makers" not in _keys(name)


# ── (6) cast_from_exile ────────────────────────────────────────────────────


def test_impulse_draw_reads_the_impulse_subject():
    idents = _idents("Act on Impulse")
    assert "cast_from_exile|you|impulse" in idents
    assert "cast_from_exile|you|" not in idents


@pytest.mark.parametrize(
    "name",
    [
        "Court of Locthwain",  # an opponent's library: theft, not impulse
        "Faldorn, Dread Wolf Herald",  # "whenever you cast a spell from exile"
        "Cast Through Time",  # granted rebound, CR 702.88a
    ],
)
def test_cast_from_exile_permission_or_payoff_is_bare(name):
    assert "cast_from_exile|you|" in _idents(name)
