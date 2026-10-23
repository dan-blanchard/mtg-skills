"""Phase B lane gaps, the keyword-grant slice (``lanes/triggers_damage.py``).

The granted keyword rides as the subject of every keyword-grant ident; a
one-shot flash grant, an effect-made damage amplifier and a symmetric cast
punisher each reach their key. Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import iter_mod_sites, tag_of, unit_keyword_grants
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


# ── keyword subjects ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # A single-target grant keeps its subject-less ident and names the keyword.
        ("Tainted Strike", ("keyword_grant_target", "you", "infect")),
        ("Jump", ("keyword_grant_target", "you", "flying")),
        ("Act of Treason", ("keyword_grant_target", "you", "haste")),
        # The generic team's evasion grant, and the symmetric global grant.
        ("Levitation", ("team_evasion_grant", "you", "flying")),
        ("Concordant Crossroads", ("all_creatures_kw_grant", "any", "haste")),
        # Your team, any subset: generic, typed, attacking, and the creature a
        # watcher of your creatures triggers on.
        ("Fervor", ("team_buff", "you", "haste")),
        ("Bonescythe Sliver", ("team_buff", "you", "double strike")),
        ("Blade Historian", ("team_buff", "you", "double strike")),
        # A creature type alone names creatures ("other Spiders you control").
        ("Cosmic Spider-Man", ("team_buff", "you", "flying")),
        ("Rafiq of the Many", ("team_buff", "you", "double strike")),
        # An emblem's static (the deep walk).
        ("Domri Rade", ("team_buff", "you", "haste")),
        # The suit-up recipient: "Equipped / Enchanted creature has <kw>", and a
        # modal arm of "Whenever equipped creature attacks".
        ("Fireshrieker", ("aura_equip_kw_grant", "you", "double strike")),
        ("Lightning Greaves", ("aura_equip_kw_grant", "you", "haste")),
        ("Phyresis", ("aura_equip_kw_grant", "you", "infect")),
        ("The Spear of Leonidas", ("aura_equip_kw_grant", "you", "double strike")),
    ],
)
def test_keyword_grant_names_the_keyword(name, ident):
    assert ident in _idents(name)


def test_subject_less_idents_keep_their_shape():
    """The subject-bearing idents are additive: Tainted Strike keeps
    ``keyword_grant_target|you|``; a team anthem (Akroma's Memorial) still
    carries no ``keyword_grant_target`` and a suit-up Equipment no subject-less
    ``aura_equip_kw_grant`` (that one is "Auras / Equipment you control have")."""
    assert ("keyword_grant_target", "you", "") in _idents("Tainted Strike")
    assert "keyword_grant_target" not in _keys("Akroma's Memorial")
    assert ("team_buff", "you", "flying") in _idents("Akroma's Memorial")
    assert ("aura_equip_kw_grant", "you", "") not in _idents("Fireshrieker")


def test_drawback_grant_names_no_subject():
    """Cumulative upkeep (CR 702.24a: pay an increasing cost or sacrifice it) is
    a drawback an Aura hangs on a creature (Mana Chains), not a keyword a theme
    wants granted."""
    assert not {i for i in _idents("Mana Chains") if i[2] == "cumulative upkeep"}


def test_unknown_keyword_placeholder_names_no_subject():
    """phase writes a keyword it can't name as an ``Unknown`` placeholder —
    Concerted Effort's landwalk and protection — which names no keyword a
    theme could want (``_DRAWBACK_GRANT_KW``); the keywords it does name still
    ride as subjects of the team grant."""
    idents = _idents("Concerted Effort")
    assert not {i for i in idents if i[2] == "unknown"}
    assert ("team_buff", "you", "trample") in idents


def test_watched_creature_grant_is_a_team_buff():
    """Ogre Battledriver's "Whenever another creature you control enters, that
    creature gets +2/+0 and gains haste until end of turn": the grant lands on
    the creature the trigger watched, one of yours."""
    assert ("team_buff", "you", "haste") in _idents("Ogre Battledriver")


@pytest.mark.retirement_canary
def test_ogre_battledriver_it_is_still_an_unresolved_parent_target_canary():
    """Retirement canary for the unresolved-``ParentTarget`` arm of
    ``triggers_damage._keyword_grant_lanes``: phase v0.104.0 writes Ogre
    Battledriver's "that creature … gains haste" as an ``AddKeyword`` whose
    ``affected`` is a ``ParentTarget`` no target in the unit resolves
    (``unit_keyword_grants`` reads none), so the lane reads it as the creature
    the trigger watched."""
    test_signals("Ogre Battledriver")  # seeds the snapshot's trees (CI-safe)
    unresolved = [
        mod
        for tree in trees_for(test_card("Ogre Battledriver"))
        for unit in tree.units
        if unit.origin == "trigger"
        for sdef, mod in iter_mod_sites(unit.node, deep=True)
        if tag_of(mod) == "AddKeyword"
        and tag_of(getattr(sdef, "affected", None)) == "ParentTarget"
        and all(mod is not m for _r, m in unit_keyword_grants(unit))
    ]
    assert unresolved, (
        "triggers_damage._keyword_grant_lanes: RETIRE-READY — phase now resolves "
        'Ogre Battledriver\'s "that creature" (a TriggeringSource or a target '
        "unit_keyword_grants reads). Re-check Mammoth Harness's unresolved one and "
        "drop the ParentTarget half of the watched-creature arm if none is left."
    )


# ── one-shot flash grants ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Borne Upon a Wind", "Alchemist's Refuge", "Emergence Zone"]
)
def test_one_shot_flash_grant(name):
    """ "You may cast spells this turn as though they had flash" — a
    GenericEffect's static granting the CastWithKeyword static for the turn
    (CR 702.8a)."""
    keys = _keys(name)
    assert {"flash_grant", "flash_makers", "spell_keyword_grant"} <= keys


def test_next_spell_flash_grant():
    """Quicken's "The next sorcery spell you cast this turn can be cast as
    though it had flash" — a GrantNextSpellAbility whose modifier is phase's
    CastAsThoughFlash. One next spell is a flash grant, not the flash_makers
    enabler that builds an instant-speed deck (test_keyword_gaps' Quicken pin)."""
    assert "flash_grant" in _keys("Quicken")
    assert "flash_makers" not in _keys("Quicken")


# ── damage amplifiers an effect sets up ─────────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Isengard Unleashed", "Goblin Goliath", "Desperate Gambit"]
)
def test_effect_made_damage_doubler(name):
    """A spell's / ability's "if a source you control would deal damage this
    turn …, it deals double / triple that damage instead" (CR 614.1a), and
    Desperate Gambit's won flip, are damage doublers; the doubler deals no
    damage itself, so Isengard Unleashed stays out of direct_damage."""
    assert ("damage_doubling", "you", "") in _idents(name)


def test_effect_made_doubler_is_not_burn():
    assert "direct_damage" not in _keys("Isengard Unleashed")


# ── symmetric cast punishers ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Eidolon of the Great Revel", "Pyrostatic Pillar", "Oppression"]
)
def test_symmetric_cast_punisher(name):
    """ "Whenever a player casts …, ~ deals 2 damage to that player" /
    "that player discards a card" punishes the caster."""
    assert ("opponent_cast_matters", "opponents", "") in _idents(name)


@pytest.mark.parametrize("name", ["Niv-Mizzet, Parun", "Angel's Feather"])
def test_symmetric_cast_payoff_is_no_punisher(name):
    """A symmetric cast trigger that pays YOU (a card, a life) punishes no one."""
    assert "opponent_cast_matters" not in _keys(name)
