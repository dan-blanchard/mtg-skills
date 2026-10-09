"""The crosswalk reads behind ``roles.protects`` (ADR-0051): protective keyword
grants, saves, and attack deterrents — each for something of yours other than
the card itself.

Every card is a real one from the testkit snapshot (ADR-0056); each read runs over
the same corrected trees phase's records build in production.
"""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import (
    attack_deterrent,
    protective_grant_recipients,
    protective_saves,
    tag_of,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card


def _trees(name: str):
    trees = trees_for(test_card(name))
    assert trees, f"{name}: no trees"
    return trees


def _grants(name: str) -> set[tuple[str, str]]:
    return {g for t in _trees(name) for g in protective_grant_recipients(t)}


def _saves(name: str) -> set[tuple[str, str]]:
    return {s for t in _trees(name) for s in protective_saves(t)}


def _deterrent(name: str) -> str | None:
    kinds = {attack_deterrent(t) for t in _trees(name)} - {None}
    return next(iter(kinds), None)


# ── Protective keyword grants (CR 702.11b-d, 702.12b, 702.16b, 702.18a, 702.21a) ──


@pytest.mark.parametrize(
    ("name", "grant"),
    [
        ("Avacyn, Angel of Hope", ("indestructible", "permanent")),  # "Another"
        ("Darksteel Forge", ("indestructible", "permanent")),  # artifacts
        ("Sterling Grove", ("shroud", "permanent")),  # other enchantments
        ("Swiftfoot Boots", ("hexproof", "permanent")),  # equipped creature
        ("Tamiyo's Safekeeping", ("hexproof", "permanent")),  # target permanent
        ("Apostle's Blessing", ("protection", "permanent")),  # a ChooseOneOf branch
        ("Giver of Runes", ("protection", "permanent")),  # another target creature
        ("Heroic Intervention", ("indestructible", "permanent")),  # your permanents
        ("Stonehoof Chieftain", ("indestructible", "permanent")),  # the attacker
        ("Break of Day", ("indestructible", "permanent")),  # "those creatures"
        ("Crackling Emergence", ("indestructible", "permanent")),  # enchanted land
        # A granted ability's "this creature" is the equipped creature.
        ("Giant's Amulet", ("hexproof", "permanent")),
        # Making a creature a Citizen adds the Creature type to a creature — it
        # animates nothing, so the hexproof shields it.
        ("Secret Identity", ("hexproof", "permanent")),
        # "put it onto the battlefield … it gains … hexproof" — the card the
        # ability put onto the battlefield.
        ("Doors of Durin", ("hexproof", "permanent")),
        # An Aura's "that creature" is the enchanted creature (CR 303.4b).
        ("Maze's Mantle", ("hexproof", "permanent")),
        # Umbra armor on an Aura shields the enchanted permanent (CR 702.89a):
        # Dog Umbra's own conditional grant, Estrid's Mask token.
        ("Dog Umbra", ("umbra armor", "permanent")),
        ("Estrid, the Masked", ("umbra armor", "permanent")),
        # Player protection: "You have hexproof" (CR 702.11c), shroud (702.18a),
        # "you gain protection from everything" (702.16b).
        ("Leyline of Sanctity", ("hexproof", "player")),
        ("True Believer", ("shroud", "player")),
        ("Teferi's Protection", ("protection", "player")),
        ("Shalai, Voice of Plenty", ("hexproof", "player")),
        ("Shalai, Voice of Plenty", ("hexproof", "permanent")),
    ],
)
def test_protective_grants_to_something_else(name, grant):
    assert grant in _grants(name)


@pytest.mark.parametrize(
    "name",
    [
        "Dragonlord Ojutai",  # "~ has hexproof as long as it's untapped"
        "Yahenni, Undying Partisan",  # "Sacrifice another creature: ~ gains …"
        "Falkenrath Aristocrat",
        "Fleecemane Lion",  # monstrous: it has hexproof and indestructible
        "Paradise Druid",
        "Estwald Shieldbasher",  # "Whenever ~ attacks … it gains indestructible"
        "Pristine Skywise",  # a cast trigger's "it" is the card itself
        "Teferi's Reproach",  # protection for the target opponent
        # The keyword comes with animating the permanent (Avalanche Caller:
        # "becomes a 4/4 Elemental creature with hexproof and haste").
        "Avalanche Caller",
        "Sylvan Awakening",
        "Kamahl, Heart of Krosa",
        "Wrenn and Realmbreaker",
        "Kamahl's Will",
        "Sparkshaper Visionary",
        # Rewrites the creature's types outright: a neutralising Aura.
        "Darksteel Mutation",
    ],
)
def test_self_only_and_opponent_grants_are_not_protection(name):
    assert not _grants(name)


# ── Saves (CR 701.19a regeneration, 702.26b phasing, 615.1 prevention) ──────────


@pytest.mark.parametrize(
    ("name", "save"),
    [
        ("Regenerate", ("regenerate", "permanent")),
        ("Zombie Master", ("regenerate", "permanent")),  # granted to other Zombies
        ("Teferi's Protection", ("phase_out", "permanent")),
        ("Fog", ("prevent_damage", "permanent")),
        ("Circle of Protection: Red", ("prevent_damage", "player")),
        ("Security Blockade", ("prevent_damage", "player")),  # granted to its land
        ("Samite Blessing", ("prevent_damage", "permanent")),
        ("Urza's Armor", ("prevent_damage", "player")),  # PreventionMinus shield
        ("Palisade Giant", ("prevent_damage", "player")),  # damage to you → to it
        # "If a permanent you control would be put into a graveyard … exile it
        # instead. Return it to the battlefield" (a CR 614.1a replacement).
        ("Cosmic Intervention", ("return", "permanent")),
        # "damage that would reduce your life total to less than 1 reduces it to
        # 1 instead" (a replacement, CR 614.1a).
        ("Angel's Grace", ("life_floor", "player")),
        ("Angel of Grace", ("life_floor", "player")),
        # A regeneration you can aim at your own creature (CR 701.19a).
        ("Gore Vassal", ("regenerate", "permanent")),
        # An OPTIONAL shield you aim ("you may prevent") is yours to use.
        ("Battletide Alchemist", ("prevent_damage", "player")),
        # "If damage would be dealt to you" — no recipient filter survives the
        # parse, but no source class makes it symmetric either.
        ("Delaying Shield", ("prevent_damage", "player")),
        # Defensive neutralisers (CR 615.1): prevention of the damage an
        # opponent's object would deal shields you and your board.
        ("Dovin, Hand of Control", ("prevent_damage", "player")),
        ("Kiora, the Crashing Wave", ("prevent_damage", "player")),
        ("Resistance Fighter", ("prevent_damage", "permanent")),
    ],
)
def test_saves_for_something_else(name, save):
    assert save in _saves(name)


@pytest.mark.parametrize(
    "name",
    [
        "Thrun, the Last Troll",  # "{1}{G}: Regenerate ~"
        "Frenetic Efreet",  # its own coin-flip phase-out
        "Mossbridge Troll",  # "If ~ would be destroyed, regenerate it"
        "Experiment One",  # "Remove two +1/+1 counters: Regenerate ~"
        "Fog Bank",  # "dealt to and dealt by ~"
        # "Prevent all damage that would be dealt by enchanted creature": a pacifying
        # Aura (a static ability's continuous effect, CR 611.3), not a shield for yours.
        "Temporal Isolation",
        "Hostility",  # prevents its own spells' damage to an opponent
        "Sapphire Charm",  # "Target creature an opponent controls phases out"
        "Skeletonize",  # the Skeleton token regenerates itself
        "Leyline of the Void",  # exiles an opponent's cards, returns nothing
        # A permanent's shield over every player's objects alike — protecting no
        # one's board in particular (Crumbling Sanctuary's ruling: "The ability
        # affects all players").
        "Crumbling Sanctuary",
        "Plated Pegasus",
        # Phased out until it leaves the battlefield: removal, not a save (its
        # ruling: the creature "doesn't phase in during its controller's untap
        # step as normal" — CR 702.26a's untap-step phase-in).
        "Oubliette",
        "The Phasing of Zhalfir",
        "Commandeer",  # a spell thief: the spell_redirect key's, not a save
    ],
)
def test_self_only_pacifying_and_hostile_saves_are_not_protection(name):
    assert not _saves(name)


# ── Attack deterrents (CR 508.1c restrictions, 508.1h attack costs) ─────────────


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Ghostly Prison", "attack_tax"),
        ("Propaganda", "attack_tax"),
        ("Sphere of Safety", "attack_tax"),
        ("Norn's Annex", "attack_tax"),
        ("Archangel of Tithes", "attack_tax"),  # beside "as long as it's untapped"
        ("Blazing Archon", "attack_ban"),
        ("Vow of Duty", "attack_ban"),
        ("Promise of Loyalty", "attack_ban"),  # a sorcery's "each of those creatures"
        ("Crawlspace", "attack_limit"),
        ("Silent Arbiter", "attack_limit"),
        # Granted to your planeswalkers: "this planeswalker" is each of them.
        ("Tomik, Orzhov Lawmage", "attack_limit"),
        # A player's creatures can't attack you for a turn (CR 508.1c).
        ("Orzhov Advokist", "attack_ban"),
        ("The Second Doctor", "attack_ban"),
        ("Willie Lumpkin, Postman", "attack_ban"),
    ],
)
def test_attack_deterrents(name, kind):
    assert _deterrent(name) == kind


@pytest.mark.parametrize(
    "name",
    [
        "Pacifism",  # a restriction on one creature, no defender named
        "The Eternal Wanderer",  # limits attacks on itself only
        "Alexios, Deimos of Kosmos",  # its own attack restriction
        "Ensnaring Bridge",  # "can't attack" names no defender
    ],
)
def test_non_deterrents(name):
    assert _deterrent(name) is None


# ── Retirement canary: a spell's misbound SelfRef ───────────────────────────────


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    "name", ["Blizzard Brawl", "Savage Order", "Promise of Loyalty"]
)
def test_spell_selfref_misbinding_canary(name):
    """Retirement canary for ``crosswalk.protection._filter_recipient``'s
    instant/sorcery ``SelfRef`` arm: phase v0.94.0 binds these spells' "the
    creature you control" / "it" / "each of those creatures" to the spell itself,
    so the read takes it as the object the spell chose."""
    selfref = [
        n
        for t in _trees(name)
        for n in t.iter_typed()
        if tag_of(getattr(n, "affected", None)) == "SelfRef"
        and (
            getattr(n, "modifications", None)
            or getattr(n, "attack_defended", None) in ("Player", "PlayerOrPlaneswalker")
        )
    ]
    assert selfref, (
        "crosswalk.protection._filter_recipient: RETIRE-READY — phase no longer "
        f"binds {name}'s effect to the spell itself. Delete _filter_recipient's "
        "instant/sorcery SelfRef arm, attack_deterrent's is_spell_card SelfRef "
        "exception, and this canary (reads.is_spell_card stays: "
        "mass_land_denial reads it)."
    )
    assert _grants(name) or _deterrent(name)


@pytest.mark.retirement_canary
def test_aura_etb_triggering_source_canary():
    """Retirement canary for ``crosswalk.protection._aura_etb_names_enchanted``:
    phase v0.94.0
    aims Maze's Mantle's "that creature gains hexproof" at the trigger's
    ``TriggeringSource`` (the Aura itself) rather than the enchanted creature."""
    targets = [
        tag_of(getattr(n, "target", None))
        for t in _trees("Maze's Mantle")
        for n in t.iter_typed()
        if tag_of(n) == "GenericEffect"
    ]
    assert "TriggeringSource" in targets, (
        "crosswalk.protection._aura_etb_names_enchanted: RETIRE-READY — phase no "
        "longer binds Maze's Mantle's grant to the triggering Aura. Delete the "
        "helper, its call in protection._back_reference_recipient, and this "
        "canary."
    )
