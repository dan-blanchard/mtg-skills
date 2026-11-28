"""The "a creature dies" links and waits (``_analysis.links.deaths``), on real
cards (ADR-0056). A link carries facts, never a verdict; these pin the facts a
real card's text gives each route, each side, each delivery, and ``feeds``."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.links import deaths
from mtg_utils._analysis.links.deaths import (
    EFFECT_ROUTES,
    NO_DEATH_EFFECTS,
    ROUTES,
    UNREAD_DEATH_EFFECTS,
    DeathLink,
    DeathWait,
    card_death_links,
    card_death_waits,
    feeds,
)
from mtg_utils._card_ir.mirror import EFFECT_VARIANTS
from mtg_utils.testkit import test_card


def _links(name: str) -> tuple[DeathLink, ...]:
    return card_death_links(test_card(name))


def _waits(name: str) -> tuple[DeathWait, ...]:
    return card_death_waits(test_card(name))


def _facts(link: DeathLink) -> tuple:
    """Every fact but the card's name."""
    return (
        link.route,
        link.whose,
        link.reach,
        link.role,
        link.delivery,
        link.repeatable,
        link.verb,
    )


# ── the roster gate ────────────────────────────────────────────────────────────


def test_every_phase_effect_is_classified():
    """phase's ``Effect`` enum is closed: each variant is a death route, an
    effect that makes no creature die by itself, or one that can and isn't read
    yet. A new variant fails here until someone classifies it."""
    routes, quiet, unread = (
        set(EFFECT_ROUTES),
        set(NO_DEATH_EFFECTS),
        set(UNREAD_DEATH_EFFECTS),
    )
    assert not routes & quiet
    assert not routes & unread
    assert not quiet & unread
    assert routes | quiet | unread == set(EFFECT_VARIANTS)


def test_every_route_names_its_rule():
    assert {route for route, _reach in EFFECT_ROUTES.values()} <= set(ROUTES)
    assert set(deaths.RECOVERED_ROUTES.values()) <= set(ROUTES)
    assert all(rule.endswith("700.4") for rule, _certain in ROUTES.values())


# ── one card per route, side, reach, role and delivery ─────────────────────────


@pytest.mark.parametrize(
    ("name", "facts"),
    [
        # destroy: one creature, either side, a spell, once
        (
            "Doom Blade",
            ("destroy", "either", "one", "effect", "spell", False, "Destroy"),
        ),
        (
            "Wrath of God",
            ("destroy", "either", "all", "effect", "spell", False, "DestroyAll"),
        ),
        # sacrifice as a cost, yours, repeatable
        (
            "Viscera Seer",
            ("sacrifice", "yours", "one", "cost", "activated", True, "Sacrifice"),
        ),
        # an edict: their creature, a trigger that repeats
        (
            "Grave Pact",
            (
                "sacrifice",
                "theirs",
                "one",
                "effect",
                "triggered:dies",
                True,
                "Sacrifice",
            ),
        ),
        # the card itself, its own enters trigger: once
        (
            "Vexing Devil",
            (
                "sacrifice",
                "self",
                "one",
                "effect",
                "triggered:enters",
                False,
                "Sacrifice",
            ),
        ),
        # damage, one or all
        (
            "Lightning Bolt",
            ("damage", "either", "one", "effect", "spell", False, "DealDamage"),
        ),
        (
            "Pyroclasm",
            ("damage", "either", "all", "effect", "spell", False, "DamageAll"),
        ),
        ("Prey Upon", ("fight", "either", "one", "effect", "spell", False, "Fight")),
        # shrink: a -N/-N pump, -1/-1 counters on every creature
        ("Disfigure", ("shrink", "either", "one", "effect", "spell", False, "Pump")),
        (
            "Black Sun's Zenith",
            ("shrink", "either", "all", "effect", "spell", False, "PutCounterAll"),
        ),
        (
            "Massacre Wurm",
            ("shrink", "theirs", "all", "effect", "triggered:enters", False, "PumpAll"),
        ),
        # an activated ability whose cost sacrifices the card goes off once
        (
            "Bounty Agent",
            ("destroy", "either", "one", "effect", "activated", False, "Destroy"),
        ),
        # a static toughness reduction: all of theirs, or the one enchanted
        (
            "Elesh Norn, Grand Cenobite",
            ("shrink", "theirs", "all", "static", "static", True, "AddToughness"),
        ),
        (
            "Dead Weight",
            ("shrink", "either", "one", "static", "static", True, "AddToughness"),
        ),
    ],
)
def test_a_cards_link_facts(name, facts):
    assert facts in {_facts(link) for link in _links(name)}


def test_an_unparsed_clause_links_through_its_recovered_concept():
    """Whipkeeper's "deals damage to target creature equal to the damage already
    dealt to it this turn" is a clause phase leaves unparsed; the recovery
    stage's ``deal_damage`` concept stands in (``RECOVERED_ROUTES``). Its
    ``whose`` is the recovery stage's scope, not pinned here."""
    (link,) = _links("Whipkeeper")
    assert (link.route, link.role, link.delivery, link.repeatable, link.verb) == (
        "damage",
        "effect",
        "activated",
        True,
        "Unimplemented",
    )


def test_route_rule_and_certainty():
    """A destroy, a sacrifice or a move is certain; damage, a fight and a
    shrink kill only when the number is big enough (CR 704.5g / 704.5f)."""
    (blade,) = _links("Doom Blade")
    assert (blade.rule, blade.certain) == ("CR 701.8a + 700.4", True)
    (bolt,) = _links("Lightning Bolt")
    assert (bolt.rule, bolt.certain) == ("CR 704.5g + 701.8a + 700.4", False)
    (shrink,) = _links("Disfigure")
    assert (shrink.rule, shrink.certain) == ("CR 704.5f + 700.4", False)


def test_a_counted_shrink_is_read():
    """A counted negative toughness is a shrink too (``reads.negative_pt_field``):
    Mutilate's "All creatures get -1/-1 until end of turn for each Swamp you
    control"."""
    facts = {_facts(link) for link in _links("Mutilate")}
    assert ("shrink", "either", "all", "effect", "spell", False, "PumpAll") in facts


def test_a_granted_ability_links():
    """Wolfhunter's Quiver's equipped creature has "{T}: This creature deals 1
    damage to any target" (CR 113.1a: abilities can be granted by effects)."""
    facts = {_facts(link) for link in _links("Wolfhunter's Quiver")}
    assert (
        "damage",
        "either",
        "one",
        "effect",
        "granted:activated",
        True,
        "DealDamage",
    ) in facts


@pytest.mark.parametrize(
    ("name", "keyword", "facts"),
    [
        ("Silumgar Butcher", "Exploit", ("yours", "effect", "triggered:enters")),
        ("Mycoloth", "Devour", ("yours", "effect", "replacement")),
        ("Light 'Em Up", "Casualty", ("yours", "cost", "cost")),
        ("Torch the Tower", "Bargain", ("yours", "cost", "cost")),
    ],
)
def test_a_keywords_sacrifice(name, keyword, facts):
    (link,) = [link for link in _links(name) if link.verb == keyword]
    assert (link.route, link.whose, link.role, link.delivery) == ("sacrifice", *facts)
    assert link.rule.startswith(deaths.KEYWORD_SACRIFICES[keyword][0])
    assert link.repeatable is False


# ── who sacrifices (CR 701.21a) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "whose"),
    [
        # "At the beginning of each player's upkeep, that player sacrifices …"
        ("Braids, Cabal Minion", "either"),
        # "Each player … sacrifices all creatures they control"
        ("Living Death", "either"),
        # "Whenever an opponent searches their library, that player sacrifices …"
        ("Ob Nixilis, Unshackled", "theirs"),
        # combat damage to a player: that player sacrifices
        ("Demon of Loathing", "theirs"),
        # "Any number of target players each … sacrifice": you can be one
        ("Priest of Forgotten Gods", "either"),
        # "Any number of target opponents each sacrifice …"
        ("Will of the Abzan", "theirs"),
        # "Target opponent sacrifices a creature of their choice."
        ("Cruel Edict", "theirs"),
        # "Target player sacrifices a creature of their choice.": you can be it
        ("Diabolic Edict", "either"),
        # its -2 "Target player sacrifices", its -6 "That player sacrifices …"
        ("Liliana of the Veil", "either"),
        # "any player may sacrifice two creatures": you among them
        ("Prowling Pangolin", "either"),
        ("Smokestack", "either"),  # each player's upkeep
    ],
)
def test_whose_creature_a_sacrifice_kills(name, whose):
    edicts = [
        link
        for link in _links(name)
        if link.route == "sacrifice" and link.role == "effect" and link.whose != "self"
    ]
    assert edicts
    assert {link.whose for link in edicts} == {whose}


def test_your_own_sacrifice_cost_is_yours():
    (cost,) = [link for link in _links("Viscera Seer") if link.role == "cost"]
    assert cost.whose == "yours"


def test_a_saga_chapter_goes_off_once():
    """The Eldest Reborn's chapter I, "Each opponent sacrifices a creature or
    planeswalker": a chapter triggers as the lore counters reach its number
    (CR 715.2b), once."""
    (link,) = _links("The Eldest Reborn")
    assert (link.whose, link.delivery, link.repeatable) == (
        "theirs",
        "triggered:counter_added",
        False,
    )


def test_an_enters_or_attacks_trigger_repeats():
    """Korvold's "Whenever Korvold enters or attacks, sacrifice another
    permanent" goes off on each attack (``reads.unit_repeats(attacks_again=
    True)``)."""
    (link,) = _links("Korvold, Fae-Cursed King")
    assert (link.delivery, link.repeatable) == ("triggered:entersorattacks", True)


@pytest.mark.parametrize(
    ("name", "certain"),
    [
        # "any opponent may have it deal 4 damage to them. If a player does,
        # sacrifice this creature": the opponent decides
        ("Vexing Devil", False),
        # "its controller sacrifices a permanent … unless they pay {1}"
        ("Fade Away", False),
        # evoke's "if its evoke cost was paid": its controller decides
        ("Mulldrifter", True),
        # "sacrifice this creature unless you discard a card": its controller
        ("Masticore", True),
    ],
)
def test_a_sacrifice_another_player_decides_is_uncertain(name, certain):
    sacrifices = [link for link in _links(name) if link.route == "sacrifice"]
    assert sacrifices
    assert {link.certain for link in sacrifices} == {certain}


def test_a_sacrificed_artifact_type_is_no_creature():
    """Gilded Goose's "Sacrifice a Food": Food is an artifact type (CR
    205.3g), not a creature type (CR 205.3m), so its costs kill nothing."""
    assert _links("Gilded Goose") == ()


# ── waits ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "wait"),
    [
        ("Zulaport Cutthroat", ("dies", "yours", True, ("Creature",))),
        ("Blood Artist", ("dies", "any", True, ("Creature",))),
        ("Massacre Wurm", ("dies", "theirs", False, ("Creature",))),
        ("Doomed Traveler", ("dies", "self", False, ())),
        # an Equipment's equipped creature is yours (CR 702.6a)
        ("Skullclamp", ("dies", "yours", False, ("Creature",))),
        (
            "Halvar, God of Battle // Sword of the Realms",
            ("dies", "yours", False, ("Creature",)),
        ),
        # an Aura's: anyone's ("Enchant creature"), or the side its enchant
        # restriction names ("Enchant creature you control")
        ("Abduction", ("dies", "any", False, ("Creature",))),
        ("Necrogen Communion", ("dies", "yours", False, ("Creature",))),
        ("Mortician Beetle", ("sacrificed", "any", False, ("Creature",))),
        ("Silumgar Butcher", ("exploited", "any", False, ("Creature",))),
    ],
)
def test_a_cards_wait(name, wait):
    assert wait in {(w.event, w.whose, w.another, w.types) for w in _waits(name)}


def test_an_equipments_static_shrink_is_on_your_creature():
    """Skullclamp's "Equipped creature gets +1/-1": the equipped creature is
    yours (CR 702.6a); Dead Weight's "Enchant creature" can be anyone's."""
    (clamp,) = _links("Skullclamp")
    assert (clamp.route, clamp.whose, clamp.reach) == ("shrink", "yours", "one")
    (weight,) = _links("Dead Weight")
    assert weight.whose == "either"


@pytest.mark.parametrize(
    ("name", "event", "tokens"),
    [
        ("Gluttonous Guest", "sacrificed", True),  # "you sacrifice a Blood token"
        ("Ashling, the Limitless", "sacrificed", False),  # "a nontoken Elemental"
        ("Zulaport Cutthroat", "dies", None),
    ],
)
def test_a_wait_says_whether_it_watches_tokens(name, event, tokens):
    assert _wait(name, event).tokens is tokens


def test_a_sacrifice_wait_names_what_it_watches():
    """A sacrifice wait is kept whatever it watches; its types say what:
    Korvold's "Whenever you sacrifice a permanent"."""
    korvold = _wait("Korvold, Fae-Cursed King", "sacrificed")
    assert (korvold.whose, korvold.types) == ("yours", ("Permanent",))


def test_a_card_with_no_death_trigger_waits_for_nothing():
    assert _waits("Doom Blade") == ()


# ── feeds ──────────────────────────────────────────────────────────────────────


def _one(name: str, route: str) -> DeathLink:
    return next(link for link in _links(name) if link.route == route)


def _wait(name: str, event: str) -> DeathWait:
    return next(w for w in _waits(name) if w.event == event)


def test_a_destroyed_creature_was_not_sacrificed():
    """A sacrifice is its own act, its controller moving the permanent (CR
    701.21a); destruction comes only from a "destroy" effect or the lethal
    damage and deathtouch state-based actions (CR 701.8b). A destroy feeds no
    sacrifice wait."""
    beetle = _wait("Mortician Beetle", "sacrificed")
    assert not feeds(_one("Doom Blade", "destroy"), beetle)
    assert feeds(_one("Viscera Seer", "sacrifice"), beetle)


def test_feeds_reads_whose_creature_dies():
    yours = _wait("Zulaport Cutthroat", "dies")
    theirs = _wait("Massacre Wurm", "dies")
    anyone = _wait("Blood Artist", "dies")
    edict = _one("Grave Pact", "sacrifice")  # their creature
    outlet = _one("Viscera Seer", "sacrifice")  # your creature
    removal = _one("Doom Blade", "destroy")  # either
    assert not feeds(edict, yours)
    assert feeds(edict, theirs)
    assert feeds(outlet, yours)
    assert not feeds(outlet, theirs)
    assert feeds(removal, yours)
    assert feeds(removal, theirs)
    assert feeds(removal, anyone)


def test_the_card_itself_feeds_a_wait_on_yours_not_on_itself_elsewhere():
    devil = _one("Vexing Devil", "sacrifice")
    assert devil.whose == "self"
    assert feeds(devil, _wait("Zulaport Cutthroat", "dies"))
    # equipped by Skullclamp, the card itself is the creature it watches
    assert feeds(devil, _wait("Skullclamp", "dies"))
    assert not feeds(devil, _wait("Doomed Traveler", "dies"))
