"""The commander-need read (``_analysis.commander_need``): what a commander's
own text asks the deck for, and whether a card supplies it. Real cards via the
testkit (ADR-0056); the needs are read off the commander's concept trees."""

from mtg_utils._analysis.commander_need import (
    Need,
    card_type_count,
    commander_needs,
    need_predicate,
    needs_met,
    satisfies,
)
from mtg_utils.testkit import test_card, test_card_ir  # noqa: F401  (snapshot usage)


def _needs(name: str) -> tuple[Need, ...]:
    return commander_needs([test_card(name)])


def _labels(needs) -> set[str]:
    return {n.label for n in needs}


def test_winter_reads_the_delirium_condition():
    # "four or more card types among them" is a QuantityComparison over the
    # graveyard's DistinctCardTypes: the need is a two-type card or a self-mill.
    needs = _needs("Winter, Cynical Opportunist")
    labels = _labels(needs)
    assert "card types in your graveyard" in labels
    cond = next(n for n in needs if n.label == "card types in your graveyard")
    assert cond.kind == "condition"
    # A battle whose back face is a creature adds two types; an instant one.
    assert card_type_count(test_card("Invasion of Ixalan // Belligerent Regisaur")) == 2
    assert satisfies(test_card("Invasion of Ixalan // Belligerent Regisaur"), cond)
    assert satisfies(test_card("Millikin"), cond)  # an artifact creature that mills
    assert not satisfies(test_card("Beast Within"), cond)
    # Winter mills on attack: more mill is redundancy of her own effect.
    assert "mill like the commander" in labels


def test_mirko_wants_surveil_outlets():
    needs = _needs("Mirko, Obsessive Theorist")
    surveil = next(n for n in needs if n.label == "surveil outlets")
    assert surveil.kind == "event"
    assert satisfies(test_card("Curate"), surveil)
    assert not satisfies(test_card("Buried Alive"), surveil)


def test_killian_wants_auras_and_enchantments():
    needs = _needs("Killian, Decisive Mentor")
    labels = _labels(needs)
    assert "attachments" in labels  # creatures enchanted by an Aura you control attack
    fits = need_predicate(needs)
    assert fits(test_card("Ethereal Armor"))
    assert not fits(test_card("Adeline, Resplendent Cathar"))


def test_zurgo_wants_token_makers_and_their_consumers():
    needs = _needs("Zurgo Stormrender")
    labels = _labels(needs)
    assert "creatures that leaves" in labels  # a creature token you control leaves
    assert "token maker Warrior like the commander" in labels
    met = needs_met(test_card("Raise the Alarm"), needs)
    assert any(n.kind == "event" for n in met)
    assert not needs_met(test_card("Counterspell"), needs)


def test_every_token_kind_the_commander_makes_feeds_the_consumers_need():
    # Clavileño makes Vampire tokens and Demon tokens: the one "token maker
    # consumers" need carries both kinds' payoffs (it used to keep whichever
    # kind the process's hash order put first, so the plan line moved between
    # runs).
    needs = _needs("Clavileño, First of the Blessed")
    consumers = next(n for n in needs if n.label == "token maker consumers")
    assert consumers.idents == {"type_matters|you|Vampire", "type_matters|you|Demon"}
    labels = [n.label for n in needs]
    assert labels.index("token maker Demon like the commander") < labels.index(
        "token maker Vampire like the commander"
    )


def test_rootha_wants_big_instants_and_sorceries():
    # Rootha's token is an X/X where X is the greatest mana value among the
    # instant and sorcery spells cast this turn: the need is a big spell. An X
    # spell counts (CR 202.3e: X is the number chosen on the stack).
    needs = _needs("Rootha, Mastering the Moment")
    big = next(n for n in needs if n.label == "instant or sorcery spells at 5+ mana")
    assert satisfies(test_card("Blasphemous Act"), big)
    assert satisfies(test_card("Crackle with Power"), big)
    assert not satisfies(test_card("Opt"), big)
    assert not satisfies(test_card("Ulamog, the Ceaseless Hunger"), big)
    # One instant or sorcery a turn is enough for the trigger: no cheap-spells need.
    assert "cheap spells" not in _labels(needs)


def test_zhulodok_wants_colorless_spells_at_seven_or_more():
    # A static ability's affected filter: colorless (ColorCount 0, CR 105.2c)
    # spells with mana value 7 or greater.
    needs = _needs("Zhulodok, Void Gorger")
    big = next(n for n in needs if n.label == "colorless spells at 7+ mana")
    assert satisfies(test_card("Ulamog, the Ceaseless Hunger"), big)
    assert not satisfies(test_card("Sol Ring"), big)  # mana value 1
    assert not satisfies(test_card("Blasphemous Act"), big)  # red


def test_bello_wants_big_non_equipment_artifacts_and_non_aura_enchantments():
    # A static ability's affected filter with a mana-value floor and negated
    # subtypes: "each non-Equipment artifact and non-Aura enchantment you
    # control with mana value 4 or greater is a 4/4 Elemental creature".
    needs = _needs("Bello, Bard of the Brambles")
    big = next(
        n for n in needs if n.label == "artifact or enchantment spells at 4+ mana"
    )
    assert satisfies(test_card("The Great Henge"), big)
    assert not satisfies(test_card("Batterskull"), big)  # an Equipment
    assert not satisfies(test_card("Sol Ring"), big)  # mana value 1


def test_bumbleflower_wants_opponents_drawing_payoffs_and_makers():
    # "Target opponent draws a card" on every spell: the payoffs that watch
    # opponents draw, more cards that make them draw, and — "if this is the
    # second time this ability has resolved this turn" — cheap spells.
    needs = _needs("Ms. Bumbleflower")
    labels = _labels(needs)
    assert {
        "opponents drawing payoffs",
        "opponents draw like the commander",
        "cheap spells",
    } <= labels
    payoff = next(n for n in needs if n.label == "opponents drawing payoffs")
    assert satisfies(test_card("Smothering Tithe"), payoff)
    assert not satisfies(test_card("Counterspell"), payoff)
    makers = next(n for n in needs if n.label == "opponents draw like the commander")
    assert satisfies(test_card("Prosperity"), makers)


def test_an_activation_count_of_spells_is_one_cheap_spells_need():
    # Stella Lee: "whenever you cast your second spell each turn" and "activate
    # only if you've cast three or more spells this turn" are one need.
    needs = _needs("Stella Lee, Wild Card")
    assert [n.label for n in needs].count("cheap spells") == 1
    cheap = next(n for n in needs if n.label == "cheap spells")
    assert satisfies(test_card("Opt"), cheap)
    assert not satisfies(test_card("Blasphemous Act"), cheap)


def test_hazel_wants_token_makers_and_her_life_payment_is_no_resource():
    # "Tap X untapped tokens you control" and "copy target token you control":
    # tokens of any kind feed her. "Pay 2 life" is a cost she pays, not life
    # loss for drain payoffs to consume or to make more of.
    needs = _needs("Hazel of the Rootbloom")
    labels = _labels(needs)
    assert "token makers" in labels
    assert "lifeloss consumers" not in labels
    assert "lifeloss like the commander" not in labels
    tokens = next(n for n in needs if n.label == "token makers")
    assert satisfies(test_card("Raise the Alarm"), tokens)
    assert not satisfies(test_card("Counterspell"), tokens)


def test_a_commanders_own_type_is_not_a_need():
    # Mirko is a Vampire Detective; his text names neither, so no tribe need.
    assert not any("Vampire" in n.label for n in _needs("Mirko, Obsessive Theorist"))
