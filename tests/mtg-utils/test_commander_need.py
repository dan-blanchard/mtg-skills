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


def test_a_commander_that_counts_its_own_counters_wants_them_grown():
    # Zimone's X spells cost less "for each +1/+1 counter on ~" (a CountersOn
    # operand scoped to the source) and she grows only herself: the deck wants
    # her counters grown and kept — proliferate, doublers, movers, the payoffs
    # that read a creature's counters — never a plain counter maker.
    needs = _needs("Zimone, Infinite Analyst")
    need = next(n for n in needs if n.label == "counters on the commander")
    assert need.kind == "resource"
    for name in ("Branching Evolution", "Evolution Sage", "The Ozolith"):
        assert satisfies(test_card(name), need), name
    assert not satisfies(test_card("Rampant Growth"), need)
    assert not satisfies(test_card("Beast Within"), need)


def test_a_commander_that_only_grows_itself_opens_no_counter_need():
    # Valgavoth's counter is a stat on himself and nothing of his counts it;
    # Mirko likewise: no counter payoff is asked for.
    for name in ("Valgavoth, Harrower of Souls", "Mirko, Obsessive Theorist"):
        labels = _labels(_needs(name))
        assert "counters on the commander" not in labels, name
        assert "plus one consumers" not in labels, name


def test_a_commander_that_grows_others_too_keeps_the_consumers_need():
    # Captain America puts a counter on "that Hero" AND on himself: the Heroes'
    # counters feed the deck's counter payoffs, so the self-grow skip never
    # applies to him.
    needs = _needs("Captain America, Team Leader")
    consumers = next(n for n in needs if n.label == "plus one consumers")
    assert satisfies(test_card("The Ozolith"), consumers) or satisfies(
        test_card("Herald of Secret Streams"), consumers
    )


def test_a_commander_with_abilities_wants_its_multipliers():
    """A trigger doubler or an ability copier of an ability the commander has (a
    copy of an ability is an ability, CR 707.10) and a clone of it supply the
    "multipliers of the commander" need, read against this commander; a copier
    of a kind it lacks, a ramp spell and the ``keep`` family (Sundial under
    Saheeli: the ``commander_keeps`` issue's own page) do not."""
    needs = _needs("Adeline, Resplendent Cathar")  # an attack trigger, no activation
    mult = next(n for n in needs if n.label == "multipliers of the commander")
    assert mult.kind == "payoff"
    assert satisfies(test_card("Strionic Resonator"), mult)
    assert satisfies(test_card("Spark Double"), mult)
    assert not satisfies(test_card("Rings of Brighthearth"), mult)  # activated only
    assert not satisfies(test_card("Rampant Growth"), mult)
    saheeli = _needs("Saheeli, Radiant Creator")
    keep = next(n for n in saheeli if n.label == "multipliers of the commander")
    assert not satisfies(test_card("Sundial of the Infinite"), keep)


def test_a_commanders_own_type_is_not_a_need():
    # Mirko is a Vampire Detective; his text names neither, so no tribe need.
    assert not any("Vampire" in n.label for n in _needs("Mirko, Obsessive Theorist"))


def test_graveyard_arrival_from_anywhere_is_a_fill_need_not_a_death():
    # "Whenever one or more land cards are put into your graveyard from anywhere"
    # (The Gitrog Monster): an arrival into the graveyard "from anywhere" is never
    # a leaves-the-battlefield ability (CR 603.6c), so the deck is asked for ways
    # to put land cards there — land sacrifice above all — not for creatures dying.
    needs = _needs("The Gitrog Monster")
    labels = _labels(needs)
    assert "Land cards reaching your graveyard" in labels
    assert "creatures that dies" not in labels
    fill = next(n for n in needs if n.label == "Land cards reaching your graveyard")
    assert {"land_sacrifice_makers", "mill_makers", "discard_makers"} <= fill.keys
    # A land subtype is a land too (Yuma's Deserts).
    yuma = _needs("Yuma, Proud Protector")
    desert = next(n for n in yuma if n.label == "Desert cards reaching your graveyard")
    assert "land_sacrifice_makers" in desert.keys
    assert "creatures that dies" not in _labels(yuma)
    # Creature cards reach the graveyard by dying too (Sefris).
    sefris = _needs("Sefris of the Hidden Ways")
    creatures = next(
        n for n in sefris if n.label == "Creature cards reaching your graveyard"
    )
    assert {"sacrifice_outlets", "edict_makers", "mill_makers"} <= creatures.keys
    # A token is not a card (CR 108.2): token makers feed no card-arrival need.
    assert "token_maker" not in creatures.keys
    # The umbrella graveyard_makers key never tests a need (it made the need
    # 12% of the pool, never specific).
    assert "graveyard_makers" not in fill.keys


def test_disa_reads_her_lhurgoyf_graveyard_need():
    # Phase leaves Disa's "Whenever a Lhurgoyf permanent card is put into your
    # graveyard from anywhere other than the battlefield" as an Unknown trigger
    # mode; ``misparsed_shapes`` rewrites it to the graveyard-arrival form.
    needs = _needs("Disa the Restless")
    assert "Lhurgoyf cards reaching your graveyard" in _labels(needs)
    need = next(n for n in needs if n.label == "Lhurgoyf cards reaching your graveyard")
    assert "mill_makers" in need.keys


def _need(name: str, label: str) -> Need:
    return next(n for n in _needs(name) if n.label == label)


def test_counter_payoffs_and_movers_consume_the_commanders_plus_one_counters():
    # Captain America puts +1/+1 counters on your Heroes and itself: a keyword
    # for each creature with a counter (Chocobo Knights; CR 122.1) and a mover
    # that keeps the counters a creature had as it left (The Ozolith; CR 122.8)
    # consume them, as a +1/+1 counter payoff does.
    consumers = _need("Captain America, Team Leader", "plus one consumers")
    assert satisfies(test_card("Chocobo Knights"), consumers)
    assert satisfies(test_card("The Ozolith"), consumers)
    assert satisfies(test_card("Bramblewood Paragon"), consumers)
    assert not satisfies(test_card("Raise the Alarm"), consumers)


def test_a_minus_counter_trigger_wants_minus_counters_not_plus_ones():
    # Auntie Ool's "Whenever one or more -1/-1 counters are put on a creature"
    # watches one counter kind (phase's ``counter_filter``): a +1/+1 counter
    # maker feeds it nothing; a -1/-1 counter card, a proliferate and a mover do
    # (CR 122.5: moving a counter puts it onto the second object — The Ozolith).
    needs = _needs("Auntie Ool, Cursewretch")
    assert "counter_added makers" not in _labels(needs)
    need = _need("Auntie Ool, Cursewretch", "-1/-1 counters put on creatures")
    assert satisfies(test_card("The Ozolith"), need)
    assert satisfies(test_card("Evolution Sage"), need)
    assert satisfies(test_card("Black Sun's Zenith"), need)
    assert not satisfies(test_card("Bramblewood Paragon"), need)
    assert not satisfies(test_card("Disfigure"), need)  # -2/-2, no counter


def test_a_token_copy_commander_feeds_the_token_payoffs():
    # Satya's attacking copy is a token (CR 111.1): a token payoff consumes it
    # (Junk Winder's "Whenever a token you control enters"; Anointed Procession).
    consumers = _need("Satya, Aetherflux Genius", "token copy consumers")
    assert satisfies(test_card("Junk Winder"), consumers)
    assert satisfies(test_card("Anointed Procession"), consumers)
    assert not satisfies(test_card("Counterspell"), consumers)


def test_a_parked_token_replacement_still_consumes_the_commanders_tokens():
    # Mirrormind Crown's "the first time you would create one or more tokens
    # each turn, you may instead create … copies of equipped creature" parks as
    # a residue; the ledger row ``token_creation_replacement_parked`` serves its
    # ``tokens_matter``, so Rootha's Elemental tokens feed it.
    consumers = _need("Rootha, Mastering the Moment", "token maker consumers")
    assert satisfies(test_card("Mirrormind Crown"), consumers)


def test_proliferate_makes_energy_for_an_energy_commander():
    # Energy is a counter on a player (CR 107.14) and a proliferate gives a
    # player that has a counter one more of it (CR 701.34a).
    makers = _need("Satya, Aetherflux Genius", "energy makers")
    assert satisfies(test_card("Metastatic Evangel"), makers)
    assert satisfies(test_card("Evolution Sage"), makers)
    assert not satisfies(test_card("Grizzly Bears"), makers)


def test_a_planeswalker_commander_wants_proliferate_for_its_loyalty():
    # A planeswalker's loyalty is its loyalty counters (CR 306.5c).
    loyalty = _need("Quintorius, History Chaser", "loyalty on the commander")
    assert loyalty.kind == "resource"
    assert satisfies(test_card("Patrolling Peacemaker"), loyalty)
    labels = _labels(_needs("Captain America, Team Leader"))
    assert "loyalty on the commander" not in labels


def test_an_enchantment_entering_commander_wants_more_of_its_trigger():
    # Killian's "Whenever an enchantment you control enters": the cards with the
    # same trigger do what it does (constellation, eerie); an Aura without one
    # supplies the enchantment, not the trigger.
    need = _need(
        "Killian, Decisive Mentor", "entering enchantment payoffs like the commander"
    )
    assert need.kind == "redundancy"
    for name in (
        "Grim Guardian",
        "Ondu Spiritdancer",
        "Slumbering Keepguard",
        "Victor, Valgavoth's Seneschal",
    ):
        assert satisfies(test_card(name), need), name
    assert not satisfies(test_card("Ethereal Armor"), need)
    # A cast trigger is another event (Sythis's "Whenever you cast an
    # enchantment spell").
    assert not satisfies(test_card("Sythis, Harvest's Hand"), need)


def test_a_check_of_the_cast_spells_power_wants_big_creatures():
    # Eshki's "If that spell's power is 4 or greater, draw a card. If that
    # spell's power is 6 or greater, ~ deals damage …" (phase reads "that
    # spell" as the cast trigger's CostPaidObject).
    labels = _labels(_needs("Eshki, Temur's Roar"))
    assert {"creature spells with power 4+", "creature spells with power 6+"} <= labels
    six = _need("Eshki, Temur's Roar", "creature spells with power 6+")
    assert satisfies(test_card("Maelstrom Wanderer"), six)
    assert not satisfies(test_card("Grizzly Bears"), six)


def test_a_land_sacrifice_commander_wants_land_recursion_not_creature_fodder():
    # Hearthhull sacrifices lands: a sacrificed land goes to your graveyard (CR
    # 701.21a), whence Life from the Loam and Crucible of Worlds return it. Its
    # "Whenever you sacrifice a land" asks for no creature fodder.
    needs = _needs("Hearthhull, the Worldseed")
    consumers = _need("Hearthhull, the Worldseed", "land sacrifice consumers")
    assert satisfies(test_card("Life from the Loam"), consumers)
    assert satisfies(test_card("Crucible of Worlds"), consumers)
    assert "creatures that sacrificed" not in _labels(needs)
    # Dina sacrifices creatures: her need keeps the token fodder.
    dina = _need("Dina, Essence Brewer", "creatures that sacrificed")
    assert "token_maker" in dina.keys


def test_a_nontoken_sacrifice_trigger_is_not_fed_by_token_makers():
    # Ashling's "Whenever you sacrifice a nontoken Elemental": a token is no
    # nontoken creature, so the outlets feed it and the token makers do not.
    need = _need("Ashling, the Limitless", "creatures that sacrificed")
    assert "sacrifice_outlets" in need.keys
    assert not need.keys & {"token_maker", "mass_token_makers"}
    assert satisfies(test_card("Viscera Seer"), need)
    assert not satisfies(test_card("Raise the Alarm"), need)


def test_a_commanders_own_combat_damage_trigger_wants_grants_to_it():
    # "Whenever Sidar Jabari deals combat damage to a player": the grants that
    # reach the commander feed it — a commander grant (Sword Coast Sailor's
    # can't be blocked, Flaming Fist's double strike: CR 702.4b, it deals combat
    # damage in both steps), a target grant (Duelist's Heritage). Another
    # creature's own flying does not.
    labels = _labels(_needs("Sidar Jabari of Zhalfir"))
    assert "evasion for your attackers" not in labels
    need = _need(
        "Sidar Jabari of Zhalfir", "evasion and double strike for the commander"
    )
    for name in ("Sword Coast Sailor", "Flaming Fist", "Duelist's Heritage"):
        assert satisfies(test_card(name), need), name
    assert not satisfies(test_card("Serra Angel"), need)
    # A trigger on any of your creatures keeps the attackers' evasion need.
    assert "evasion for your attackers" in _labels(_needs("Olivia, Opulent Outlaw"))
