"""``_card_ir.crosswalk.perpetual``: a perpetual power/toughness change read as the
pump it is when it lands on a creature on the battlefield (the lane's own
decision: "perpetually" is an Arena-only mechanic outside the Comprehensive
Rules, defined by the repo's digital supplement, DD1.1)."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import tag_of
from mtg_utils._card_ir.crosswalk.reads import ability_zones
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _units(name: str) -> list:
    test_card_ir(name)  # seeds the card's trees from the snapshot
    return [u for t in trees_for(test_card(name)) for u in t.units]


def _pump_targets(name: str) -> list[str | None]:
    """The target tag of each pump the card's units decorate."""
    return [
        tag_of(getattr(c.node, "target", None))
        for u in _units(name)
        for c in u.effects
        if c.concept == "pump"
    ]


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


@pytest.mark.parametrize(
    ("name", "target"),
    [
        # "~ perpetually gets +1/+1" in a trigger it has on the battlefield
        ("Steady Tortoise // Harried Dash", "SelfRef"),
        # "Return ~ from your graveyard to the battlefield tapped. It perpetually
        # gets +1/+1": the card the return put onto the battlefield
        ("Vladimir and Godfrey", "SelfRef"),
        # "target creature an opponent controls perpetually gets -1/-2"
        ("Davriel's Withering", "Typed"),
        # "that creature perpetually gets -2/-0": the creature blocking it
        ("Wizened Githzerai", "ParentTarget"),
    ],
)
def test_a_perpetual_change_on_the_battlefield_is_a_pump(name, target):
    assert target in _pump_targets(name)


@pytest.mark.parametrize(
    "name",
    [
        # "choose a creature card in your hand. It perpetually gets +2/+2"
        "Veteran Charger",
        # "When ~ dies, it perpetually gets +2/+2": the card in the graveyard
        "Tomakul Phoenix",
        # "Activate only if ~ is in your graveyard"
        "Diminished Returner",
        # "Return target card from your graveyard to your hand. If it's a
        # creature card, it perpetually gets +3/+3"
        "Giant Regrowth",
        # a Vehicle that isn't a creature has no power or toughness (CR 301.7a)
        "Soul Shredder",
    ],
)
def test_a_perpetual_change_off_the_battlefield_is_no_pump(name):
    assert _pump_targets(name) == []


def test_the_typed_change_stays_in_the_tree():
    """Only the unit's effect decoration changes: the reads of the change's other
    parts (a keyword it grants, a graveyard return) walk the typed node."""
    assert any(
        tag_of(n) == "ApplyPerpetual"
        for u in _units("Steady Tortoise // Harried Dash")
        for n in u.iter_typed()
    )


def test_the_lanes_read_a_perpetual_pump_with_no_special_case():
    assert ("combat_trigger_boost", "you", "") in _idents(
        "Steady Tortoise // Harried Dash"
    )
    assert ("self_boost", "you", "activated") in _idents("Scion of Shiv")
    assert ("debuff_makers", "any", "") in _idents("Davriel's Withering")
    assert not {k for k, _s, _sub in _idents("Veteran Charger")} & {
        "self_boost",
        "effect_boost",
        "debuff_makers",
    }


def test_an_activation_restricted_to_the_graveyard_names_its_zone():
    """ "Activate only if ~ is in your graveyard and its toughness is 2 or
    greater": the ``SourceInZone`` conjunct of the condition."""
    zones = [
        ability_zones(u.node)
        for u in _units("Diminished Returner")
        if any(tag_of(n) == "ApplyPerpetual" for n in u.iter_typed())
    ]
    assert zones == [frozenset({"Graveyard"})]


def test_a_perpetual_pump_of_the_card_itself_is_no_pump_maker():
    """Ichor Aberration only grows itself: no ``effect_boost``, though a sibling
    effect of its trigger ("you may cast it from your graveyard this turn") is
    timed (Dan's call, 2026-11-25)."""
    assert ("effect_boost", "you", "") not in _idents("Ichor Aberration")
    assert any(
        c.perpetual
        for u in _units("Ichor Aberration")
        for c in u.effects
        if c.concept == "pump"
    )


def test_a_perpetual_pump_of_a_chosen_creature_is_a_pump_maker():
    """ "Target creature you control perpetually gets +1/+0" (Prairie
    Survivalist): a permanent pump of one chosen creature of yours is a pump
    maker, the targeted kind, as a pump until end of turn is: a triggered
    ability's boost of one chosen creature (ADR-0065)."""
    idents = _idents("Prairie Survivalist")
    assert ("effect_boost", "you", "") in idents
    assert ("boosts_others", "you", "target_ability") in idents


def test_a_chosen_players_creatures_keep_their_controller():
    """ "~ deals 2 damage to each creature target player controls. Those
    creatures perpetually get +2/+0" (Chaos Balor's attack mode): the player can
    be you, so it is a combat buff of yours; the view is a ``PumpAll`` over that
    filter, ``TargetPlayer`` kept."""
    assert ("combat_trigger_boost", "you", "") in _idents("Chaos Balor")
    views = [
        c.node
        for u in _units("Chaos Balor")
        for c in u.effects
        if c.concept == "pump" and c.perpetual
    ]
    assert views
    assert all(tag_of(v) == "PumpAll" for v in views)
    assert {getattr(v.target, "controller", None) for v in views} == {"TargetPlayer"}


@pytest.mark.parametrize(
    ("controller", "raises", "yours"),
    [
        ("Opponent", True, False),  # "each creature your opponents control"
        ("Opponent", False, True),  # a shrink of theirs is still read
        ("TargetPlayer", True, True),  # Chaos Balor: the player can be you
        ("You", True, True),
        (None, True, True),
    ],
)
def test_a_raise_on_only_an_opponents_population_is_no_pump_of_yours(
    controller, raises, yours
):
    """No real card at v0.131.0 has a perpetual change over a population only
    opponents control (Chaos Balor's is the one tracked population), so the rule
    is tested on its own."""
    from mtg_utils._card_ir.perpetual_rules import population_pump_is_yours

    assert population_pump_is_yours(controller, raises=raises) is yours


def test_a_returned_card_growing_is_no_firebreather():
    """ "{2}{W}: Return ~ from your graveyard to the battlefield tapped. It
    perpetually gets +1/+1" (Vladimir and Godfrey): the pump lands on the card
    only because the ability put it onto the battlefield — recursion that grows
    it, no mana sink of a creature already there (Dan's call, 2026-11-25).
    Scion of Shiv's "{2}{R}: ~ perpetually gets +1/+0" is one."""
    assert ("self_boost", "you", "activated") not in _idents("Vladimir and Godfrey")
    assert ("self_boost", "you", "") in _idents("Vladimir and Godfrey")
    assert ("self_boost", "you", "activated") in _idents("Scion of Shiv")
    assert ("self_boost", "you", "activated") in _idents("Longtusk Stalker")


# ── card_boost: a perpetual boost to your cards outside the battlefield ─────────


def _card_boosts(name: str) -> set[str]:
    return {s.subject for s in test_signals(name) if s.key == "card_boost"}


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # "choose a creature card in your hand. It perpetually gets +2/+2"
        ("Veteran Charger", {"hand"}),
        # "Return target card from your graveyard to your hand. If it's a
        # creature card, it perpetually gets +3/+3"
        ("Giant Regrowth", {"hand"}),
        # "Whenever a creature card is put into your hand from your library, it
        # perpetually gets +X/+0": the trigger's card
        ("Volatile Rift", {"hand"}),
        # a delayed "When you cast a creature spell, it perpetually gets +X/+X",
        # nested in the effect that makes it: the spell on the stack
        ("Rothga, Bonded Engulfer", {"stack"}),
        # "If a Dragon creature was beheld, it perpetually gets +2/+2": the
        # beheld Dragon (``misparsed_shapes`` writes phase's ``CostPaidObject``),
        # a card revealed from your hand or a permanent you control (CR 701.4a)
        ("Territorial Strike", {"hand"}),
        # "choose a creature card in your hand or a creature you control"
        ("Scour the Scene", {"hand"}),
        # "Whenever you draw a Dragon card, it perpetually gets +1/+1" (the
        # drawn card), beside its kicked seek's
        ("Darigaaz's Whelp", {"hand"}),
    ],
)
def test_a_typed_perpetual_boost_off_the_battlefield_is_a_card_boost(name, subjects):
    assert _card_boosts(name) == subjects


@pytest.mark.parametrize(
    "name",
    [
        # the card itself, in the graveyard: the card growing
        "Tomakul Phoenix",
        # a shrink is no boost
        "Hook Horror",
        "Undersimplify",
        # "Exile target creature" granting it "if this card is exiled, it
        # perpetually gets +1/+1": the exiled card can be anyone's
        "Tawnos Endures",
        # the condition is parked with the change
        "Mace of Disruption",
        # a creature on the battlefield is pumped, not boosted as a card
        "Steady Tortoise // Harried Dash",
    ],
)
def test_no_card_boost(name):
    assert _card_boosts(name) == set()


def _residue_decoration(name: str, residue: str) -> tuple[str, ...] | None:
    """The ``perpetual_cards`` the recovery stage wrote on the residue whose own
    text is ``residue``; ``None`` when the card's tree holds no such residue."""
    for unit in _units(name):
        for c in unit.effects:
            if (
                tag_of(c.node) == "Unimplemented"
                and getattr(c.node, "description", None) == residue
            ):
                return c.perpetual_cards
    return None


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "residue", "subjects"),
    [
        (
            "Feed the Bog",
            "Creature cards in your graveyard perpetually get +1/+1",
            {"graveyard"},
        ),
        (
            "Advanced Floral Invocations",
            "creature cards in your graveyard perpetually get +1/+1",
            {"graveyard"},
        ),
        (
            "Blighted Nightmare",
            "creature cards in your graveyard perpetually get +1/+1",
            {"graveyard"},
        ),
        # after a mill
        (
            "Elvish Elegy",
            "each creature card in your graveyard perpetually gets +1/+1",
            {"graveyard"},
        ),
        (
            "Mycoid Resurrection",
            (
                "Each creature card in your graveyard perpetually gets +X/+X, where "
                "X is the number of permanent cards in your graveyard"
            ),
            {"graveyard"},
        ),
        (
            "Begin Anew",
            "Creature cards in your hand perpetually get +1/+1",
            {"hand"},
        ),
        (
            "Grow Old Together",
            "Creature cards in your hand perpetually get +1/+1",
            {"hand"},
        ),
        (
            "Thoughtweft's Call",
            "Creature cards in your hand perpetually get +1/+1",
            {"hand"},
        ),
        (
            "Klement, Novice Acolyte",
            "creature cards in your hand perpetually get +1/+1",
            {"hand"},
        ),
        (
            "Kithkin Brinefarer",
            "Kithkin creature cards in your hand perpetually get +1/+1",
            {"hand"},
        ),
        (
            "Bramblearmor Brawler",
            "creature cards in your library perpetually get +1/+1",
            {"library"},
        ),
        # one signal per zone named
        (
            "Valgavoth, the Lifeline",
            "creature cards in your hand and graveyard perpetually get +1/+1",
            {"hand", "graveyard"},
        ),
        # a group on the battlefield beside cards: the cards' half (phase cut
        # Arming Gala's residue at its zone list's comma)
        (
            "Arming Gala",
            "library, and graveyard perpetually get +1/+1",
            {"hand", "library", "graveyard"},
        ),
        (
            "Lae'zel, Primal Warrior",
            (
                "other creatures you control and creature cards in your hand "
                "perpetually get +1/+1"
            ),
            {"hand"},
        ),
        (
            "Coalition Construct",
            (
                "other creatures you control of the chosen type and creature cards "
                "of that type in your hand perpetually get +1/+1"
            ),
            {"hand"},
        ),
        (
            "Stalwart Speartail",
            (
                "other Dinosaurs you control and Dinosaur cards in your hand and "
                "library perpetually get +1/+1"
            ),
            {"hand", "library"},
        ),
        (
            "Golden Sidekick",
            (
                "a random creature card in your hand perpetually gets +X/+X, where "
                "X is the amount of life you gained"
            ),
            {"hand"},
        ),
        (
            "Freyalise, Skyshroud Partisan",
            (
                "That Elf and a random Elf creature card in your hand perpetually "
                "get +1/+1"
            ),
            {"hand"},
        ),
        (
            "Dalkovan Outrider",
            "the topmost creature card in your library perpetually gets +1/+1",
            {"library"},
        ),
        (
            "Thorna and Twigtooth",
            (
                "the topmost creature card in your library perpetually gets +X/+X, "
                "where X is the number of counters removed this way"
            ),
            {"library"},
        ),
        # every card you own
        (
            "Naktamun Shines Again",
            (
                "All creature cards you own with mana value 2 or less perpetually "
                "get +1/+0"
            ),
            {"everywhere"},
        ),
        (
            "Network Marauder",
            (
                "all artifact creature cards and Spacecraft cards you own "
                "perpetually get +1/+1"
            ),
            {"everywhere"},
        ),
        (
            "Unbreakable Remnant",
            "all cards you own named Unbreakable Remnant perpetually get +1/+1",
            {"everywhere"},
        ),
        # "seek a Dragon card. ~ and that Dragon card each …"
        (
            "Darigaaz's Whelp",
            "~ and that Dragon card each perpetually get +1/+1",
            {"hand"},
        ),
        # "The duplicate …" after a typed conjure into a library, and after a
        # parked one onto its top
        (
            "Goblin Morale Sergeant",
            "The duplicate perpetually gets +1/+0 and gains haste",
            {"library"},
        ),
        (
            "Pampered Loamfrill",
            "The duplicate perpetually gets +1/+1 and gains deathtouch",
            {"library"},
        ),
        # conjured into exile, then shuffled into your library: where they end up
        (
            "Gyox, Brutal Carnivora",
            "Those duplicates perpetually get +X/+X",
            {"library"},
        ),
        # an "it" or "that card" after "choose a creature card in your hand"
        (
            "By Elspeth's Command",
            "It perpetually gets +1/+1 and gains vigilance",
            {"hand"},
        ),
        (
            "Garruk, Wrath of the Wilds",
            (
                'It perpetually gets +1/+1 and perpetually gains "This spell costs '
                '{1} less to cast."'
            ),
            {"hand"},
        ),
        (
            "Dina, Flesh Sower",
            "It perpetually gains trample and gets +X/+X, where X is ~'s power",
            {"hand"},
        ),
        (
            "Guildpact Greenwalker",
            "that card perpetually incorporates {1}{G} and gets +4/+4",
            {"hand"},
        ),
        # a card in your graveyard, then "Put it into your library second from
        # the top": where it ends up
        ("Richlau, Headmaster", "it perpetually gets +2/+2", {"library"}),
    ],
)
def test_parked_card_boost_canary(name, residue, subjects):
    """A perpetual boost phase parks on cards of yours outside the battlefield
    is decorated by the recovery stage with what it lands on
    (``recovery.mark_perpetual_cards``) and filed by ``crosswalk.perpetual.
    card_boost_zones`` where the cards end up, one ``card_boost`` subject per
    zone; the residue stays parked, no node written."""
    decoration = _residue_decoration(name, residue)
    assert decoration is not None, (
        f"card_boost parked read: RETIRE-READY — phase types {name}'s "
        f"{residue!r}. Once no residue reads as one, delete "
        "recovery.mark_perpetual_cards' perpetual_cards arm, the parked arm of "
        "crosswalk.perpetual.card_boost_zones and this canary."
    )
    assert decoration
    assert _card_boosts(name) == subjects


def test_a_card_boost_opens_its_pairings():
    """The graveyard subject pairs with reanimation and recursion, both ways;
    the hand and stack subjects with creature density, both ways (the Go-wide
    page offers them); a library boost opens no avenue of its own but is on the
    card_boost page."""
    from mtg_utils._analysis.signal_base import Signal
    from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for

    def spec(subject: str):
        return avenue_spec_for(Signal("card_boost", "you", subject, "", "", "high"))

    graveyard = spec("graveyard")
    assert graveyard is not None
    assert graveyard.label == "Boosts your cards outside the battlefield"
    assert {"Reanimation", "Creature recursion"} <= {e.label for e in graveyard.extras}
    for subject in ("hand", "stack"):
        paired = spec(subject)
        assert paired is not None
        assert [e.label for e in paired.extras] == ["Creature cards"], subject
    assert spec("library") is None
    assert spec("everywhere") is None
    assert graveyard.serve.counts_ident("card_boost|you|library")
    for key in ("reanimator", "creature_recursion"):
        assert any(
            e.serve.counts_ident("card_boost|you|graveyard")
            for e in SPECS[(key, "you")].extras
        ), key
    for subject in ("hand", "stack"):
        assert any(
            e.serve.counts_ident(f"card_boost|you|{subject}")
            for e in SPECS[("creatures_matter", "you")].extras
        ), subject


@pytest.mark.parametrize(
    "name",
    [
        # the beheld Dragon can be a creature you control (CR 701.4a)
        "Territorial Strike",
        # "… or a creature you control. It perpetually gets +1/+0"
        "Scour the Scene",
    ],
)
def test_a_boost_that_can_land_on_your_creature_is_a_pump_of_yours(name):
    """Dan's ruling (2026-11-25): a boost that CAN land on your creature counts
    as yours, beside the card in the hand it can also land on."""
    idents = _idents(name)
    assert ("effect_boost", "you", "") in idents
    assert ("boosts_others", "you", "effect") in idents
    # chosen as a cost or on resolution, never targeted
    assert ("boosts_others", "you", "target_spell") not in idents


def test_a_shrink_of_a_chosen_opponents_creature_is_a_debuff():
    """Penregon Besieged's "choose a creature with the least toughness among
    creatures your opponents control. It perpetually gets -1/-1" reads as the
    typed perpetual shrinks do (Davriel's Withering)."""
    assert ("debuff_makers", "any", "") in _idents("Penregon Besieged")
    assert ("debuff_makers", "any", "") in _idents("Davriel's Withering")
    assert not {i for i in _idents("Penregon Besieged") if i[0] == "effect_boost"}
