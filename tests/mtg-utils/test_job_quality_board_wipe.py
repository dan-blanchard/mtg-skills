"""The board-wipe read (``job_quality.board_wipe``): how well a card sweeps the
board, off its own trees — real cards (ADR-0056)."""

from dataclasses import replace

import pytest

from mtg_utils._analysis.job_quality import board_wipe, job_score
from mtg_utils._analysis.lanes.mana_and_wipes import mass_removal_effects
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    effect_filter,
    filter_core_types,
    filter_predicates,
)
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = job_score(_real(name), "board_wipe")
    assert score is not None, name
    return score


@pytest.mark.parametrize("clean", ["Wrath of God", "Toxic Deluge", "Farewell"])
def test_a_clean_sweep_reads_above_a_two_damage_one(clean):
    """Pyroclasm's 2 damage leaves most of a Commander board standing; a sweep
    that destroys, exiles or shrinks without limit clears it."""
    assert board_wipe.features(_real(clean))["clean"] == 1.0
    assert board_wipe.features(_real("Pyroclasm"))["small"] == 1.0
    assert _score(clean) > _score("Pyroclasm")


def test_a_self_discounted_sweep_reads_as_cheap():
    """Blasphemous Act costs {1} less for each creature on the battlefield: on a
    Commander table that wants a wipe it is a cheap clean sweep, not a 9-drop."""
    features = board_wipe.features(_real("Blasphemous Act"))
    assert features["cheap_clean"] == 1.0
    assert _score("Blasphemous Act") > _score("Wrath of God")


def test_a_one_sided_sweep_reads_above_its_symmetric_twin():
    """Ruinous Ultimatum destroys the nonland permanents only your opponents
    control; Exterminatus destroys every nonland permanent, yours too."""
    assert board_wipe.features(_real("Ruinous Ultimatum"))["one_sided"] == 1.0
    assert board_wipe.features(_real("Exterminatus"))["one_sided"] == 0.0
    assert _score("Ruinous Ultimatum") > _score("Exterminatus")


def test_an_overload_spell_reads_as_its_overloaded_sweep():
    """Phase keeps only Cyclonic Rift's and Damn's targeted modes; overload makes
    them a sweep (CR 702.96a), cast for the overload cost."""
    rift = board_wipe.features(_real("Cyclonic Rift"))
    assert rift["one_sided"] == 1.0
    assert rift["flexible"] == 1.0
    assert rift["cost"] == 7.0
    damn = board_wipe.features(_real("Damn"))
    assert damn["clean"] == 1.0
    assert damn["cost"] == 4.0
    assert _score("Cyclonic Rift") > _score("Evacuation")


def test_a_one_sided_mass_shrink_reads_as_a_one_sided_sweep():
    """Massacre Wurm's "creatures your opponents control get -2/-2" is a sweep
    the lanes hand the read (``mass_shrink_effects``), one-sided and small."""
    features = board_wipe.features(_real("Massacre Wurm"))
    assert features["one_sided"] == 1.0
    assert features["small"] == 1.0


def test_an_overloaded_power_only_shrink_is_no_sweep():
    """Downsize's "-4/-0", overloaded, shrinks no toughness, so it kills nothing
    (CR 704.5f): no sweep (``crosswalk.overload_sweep`` reads only a negative
    toughness as one). The read once took any overloaded pump."""
    assert board_wipe.features(_real("Downsize")) is None


@pytest.mark.parametrize("name", ["Lightning Bolt", "Swords to Plowshares"])
def test_a_card_with_no_sweep_is_none(name):
    """Single-target removal is the removal job, not this one."""
    assert job_score(_real(name), "board_wipe") is None


def test_a_spree_sweep_costs_its_mode():
    """Final Showdown's "Destroy all creatures" is a spree mode costing {3}{W}{W}
    on top of its {W} (CR 702.172a): a six-mana sweep, below Wrath of God."""
    card = _real("Final Showdown")
    assert signal_trees_for(card, bulk=card)[0].card_modal_mode_costs == (1, 1, 5)
    assert board_wipe.features(card)["cost"] == 6.0
    assert _score("Wrath of God") > _score("Final Showdown")


def test_an_enters_sweep_costs_the_x_paid_to_cast_it():
    """The Meathook Massacre's enters trigger reads the X paid to cast it (CR
    107.3m), so its -X/-X costs that X beside {B}{B}, not two mana."""
    assert board_wipe.features(_real("The Meathook Massacre"))["cost"] > 2.0
    assert _score("Wrath of God") > _score("The Meathook Massacre")


def test_the_four_mana_wrath_is_a_reference_sweep():
    """A clean sweep of every creature at four mana is the board wipe a deck is
    built around: Wrath of God reads as a cheap clean sweep, about as well as
    Toxic Deluge, never below a six-mana one."""
    assert board_wipe.features(_real("Wrath of God"))["cheap_clean"] == 1.0
    assert _score("Toxic Deluge") - _score("Wrath of God") < 0.1


def test_an_event_triggered_sweep_is_not_clean():
    """Sarkhan's Unsealing sweeps only when you cast a power-7 creature: no wipe
    you can cast when you need one."""
    assert board_wipe.features(_real("Sarkhan's Unsealing"))["clean"] == 0.0


@pytest.mark.parametrize(
    "name",
    [
        # "Exile all creatures", then the next end step returns them: a mass
        # flicker (the shared tree's blink return, ``ConceptNode.returns_to``).
        "Planar Guide",
        # "Exile each creature that crewed it", read by phase as every creature,
        # comes back at the next end step: a flicker.
        "Golden Argosy",
        # The Great Synthesis's bounce is on a transform back face, reached by
        # transforming (its mana value is only the front's, CR 712.8e): the
        # read's own decision is that it is no wipe on demand.
        "Jin-Gitaxias // The Great Synthesis",
    ],
)
def test_a_returning_or_transformed_sweep_is_no_wipe(name):
    assert job_score(_real(name), "board_wipe") is None


@pytest.mark.retirement_canary
def test_golden_argosy_crew_exile_reads_as_every_creature():
    """Phase reads Golden Argosy's "exile each creature that crewed it this turn"
    as every creature (a bare ``Creature`` filter), which is the only reason it
    reads as a sweep for the flicker veto to stop. Once phase parses the crew
    filter this fails: the veto's Argosy case above pins nothing any more
    (Planar Guide still pins the veto), so drop the case."""
    card = _real("Golden Argosy")
    filters = [
        (filter_core_types(f), filter_predicates(f))
        for tree in signal_trees_for(card, bulk=card)
        for _u, c in mass_removal_effects(tree)
        if (f := effect_filter(c.node)) is not None
    ]
    assert filters == [(("Creature",), ())], (
        "Golden Argosy: RETIRE-READY — phase reads the crew filter now; drop "
        "test_a_returning_or_transformed_sweep_is_no_wipe's Argosy case."
    )


def test_the_wipe_calibration_order():
    """The reference wipes in the read's order. A {1}-per-creature discount is
    read at a board of eight creatures (two a seat at a four-player table) and
    never touches the colored mana (CR 118.7a), so Blasphemous Act ({8}{R}) is
    cast for {R} and Vanquish the Horde ({6}{W}{W}) for {W}{W}: Act reads above
    Vanquish, Vanquish above Toxic Deluge, Deluge above Wrath of God and
    Damnation (four), which read alike."""
    scores = {
        name: _score(name)
        for name in (
            "Vanquish the Horde",
            "Blasphemous Act",
            "Toxic Deluge",
            "Wrath of God",
            "Damnation",
        )
    }
    assert board_wipe.features(_real("Blasphemous Act"))["cost"] == 1.0
    assert board_wipe.features(_real("Vanquish the Horde"))["cost"] == 2.0
    assert scores["Damnation"] == scores["Wrath of God"]
    assert (
        scores["Blasphemous Act"]
        > scores["Vanquish the Horde"]
        > scores["Toxic Deluge"]
        > scores["Wrath of God"]
    )


def test_an_x_paid_in_cards_is_an_x():
    """Sickening Dreams discards X cards as its additional cost (CR 107.3a: the
    caster announces X): X damage at a card each, not a two-mana clean sweep."""
    features = board_wipe.features(_real("Sickening Dreams"))
    assert features["flexible"] == 1.0
    assert features["cheap_clean"] == 0.0
    assert features["cost"] > 4


def test_a_pitch_cost_is_the_cards_it_pitches():
    """Force of Despair may be cast by exiling a black card from hand instead of
    its mana cost (CR 118.9): a card's worth, not three mana."""
    assert board_wipe.features(_real("Force of Despair"))["cost"] == 1.0


def test_keeping_your_lands_tapped_costs_the_next_turn():
    """Bontu's Last Reckoning keeps every land you control tapped through your
    next untap step (CR 502.3, its ruling): no three-mana reference wipe."""
    features = board_wipe.features(_real("Bontu's Last Reckoning"))
    assert features["cheap_clean"] == 0.0
    assert _score("Bontu's Last Reckoning") < _score("Damnation")


def test_a_death_triggered_shrink_chains():
    """Massacre Girl's delayed trigger gives each other creature -1/-1 again
    whenever a creature dies this turn (CR 603.7a; its ruling: once per death),
    so the chain kills, not a -1/-1 sweep."""
    features = board_wipe.features(_real("Massacre Girl"))
    assert features["lethal"] == 1.0
    assert features["small"] == 0.0


def test_a_draw_each_player_may_get_is_no_rider():
    """Shatter the Sky's draw goes to each player who controls a power-4
    creature, not to the caster: no rider, unlike Kaya's Wrath's life."""
    assert board_wipe.features(_real("Shatter the Sky"))["rider"] == 0.0
    assert board_wipe.features(_real("Kaya's Wrath"))["rider"] == 1.0
    assert _score("Shatter the Sky") == _score("Wrath of God")


def test_a_choice_the_filter_never_reads_limits_the_sweep():
    """Phase keeps Harsh Mercy's "each player chooses a creature type" and Sudden
    Demise's "choose a color" as a Choose node but drops the clause the choice
    limits: each player keeps their type (a spare), Sudden Demise reaches one
    colour (narrow). Kindred Dominance's filter reads its choice."""
    mercy = board_wipe.features(_real("Harsh Mercy"))
    assert mercy["spares"] == 1.0
    assert mercy["clean"] == 0.0
    assert board_wipe.features(_real("Sudden Demise"))["narrow"] == 1.0
    assert board_wipe.features(_real("Kindred Dominance"))["spares"] == 1.0


@pytest.mark.retirement_canary
def test_harsh_mercy_chosen_type_dropped_canary():
    """Phase (v0.104.0) drops Harsh Mercy's "that aren't of a type chosen this
    way": its DestroyAll's filter carries no predicate. RETIRE-READY when this
    fails: ``board_wipe._dropped_choice`` then reads nothing for it (the filter
    reads the choice) and pins nothing; keep it for the next drop or delete it."""
    (face,) = test_phase_records("Harsh Mercy")
    (spell,) = face["abilities"]
    assert spell["effect"]["type"] == "Choose"
    assert spell["sub_ability"]["effect"]["target"]["properties"] == []


@pytest.mark.parametrize(
    ("name", "feature"),
    [
        ("Extinction", "narrow"),
        ("Swarmyard Massacre", "spares"),
        ("Do or Die", "one_sided"),
    ],
)
def test_a_dropped_limiting_clause_is_read_by_name(name, feature):
    """``board_wipe._CLAUSE_DROPPED``: Extinction reaches one creature type,
    Swarmyard Massacre spares four, Do or Die destroys one pile of a target
    player's creatures (CR 700.3)."""
    assert board_wipe.features(_real(name))[feature] == 1.0


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Extinction", "Swarmyard Massacre", "Do or Die"])
def test_clause_dropped_canary(name):
    """Phase (v0.104.0) leaves these sweeps' limiting clause out: the sweep's
    filter is a bare ``Creature`` with no predicate, and nothing chooses.
    RETIRE-READY when this fails: delete the card's ``_CLAUSE_DROPPED`` row."""
    (face,) = test_phase_records(name)
    (ability,) = face["abilities"]
    node = ability
    while node["effect"]["type"] not in ("DestroyAll", "PumpAll"):
        node = node["sub_ability"]
    target = node["effect"]["target"]
    assert target["type_filters"] == ["Creature"]
    assert target["properties"] == []
    assert target["controller"] is None
    assert "Choose" not in str(face)


@pytest.mark.parametrize(
    ("name", "scales"),
    [
        ("Deluge of Doom", False),
        ("Essence Pulse", False),
        ("Planar Despair", False),
        ("Kagemaro, First to Suffer", False),
        ("Mutilate", True),
        ("Terror Tide", True),
        ("Terisiare's Devastation", True),
        ("Gates Ablaze", False),
    ],
)
def test_an_x_the_card_defines_scales_when_the_deck_fills_it(name, scales):
    """An X the card defines (CR 107.3) is narrow when its count is bounded:
    Deluge of Doom's distinct card types (CR 205.2a), Planar Despair's basic land
    types (five, CR 305.6), Essence Pulse's life gained this turn (its own 2
    first), Kagemaro's cards in hand (cut to seven at cleanup, CR 402.2). It
    scales when the deck fills the count: Mutilate's Swamps, Terror Tide's
    permanent cards in your graveyard, Terisiare's Devastation's artifacts; not a
    type only a deck built on it holds (Gates Ablaze's Gates)."""
    features = board_wipe.features(_real(name))
    assert features["lethal"] == float(scales)
    assert features["small"] == float(not scales)


def test_a_coin_flip_gates_the_sweep():
    """Boompile destroys every nonland permanent only if you win the flip (CR
    705.2), half the time (705.1): a conditional sweep, not a clean one."""
    features = board_wipe.features(_real("Boompile"))
    assert features["lethal"] == 1.0
    assert features["clean"] == 0.0
    assert _score("Boompile") < _score("Wrath of God")


@pytest.mark.parametrize(
    ("name", "cost"), [("Jaya Ballard, Task Mage", 9.0), ("Infected Vermin", 6.0)]
)
def test_a_creatures_activation_costs_its_mana(name, cost):
    """The activation cost is paid each time the ability is activated (CR
    602.1a), a creature's as much as an artifact's: Jaya Ballard's six damage is
    {5}{R}{R} on top of the card (capped at nine), Infected Vermin's ping {2}{B}."""
    features = board_wipe.features(_real(name))
    assert features["cost"] == cost
    assert features["cheap_clean"] == 0.0


def test_a_board_count_discount_is_taken_whole():
    """Hour of Revelation costs {3} less with ten or more nonland permanents on
    the battlefield: the board the read casts a wipe into meets it, as it meets
    Blasphemous Act's per-creature discount, so the sweep costs {W}{W}{W}."""
    features = board_wipe.features(_real("Hour of Revelation"))
    assert features["cost"] == 3.0
    assert features["cheap_clean"] == 1.0


def test_a_conditional_discount_is_taken_at_half():
    """Avenge costs {2} less only if a player attacked you during their last
    turn: the condition decides the cost as it is locked in (CR 601.2f), so the
    read takes half the discount, and Avenge is no four-mana Wrath."""
    features = board_wipe.features(_real("Avenge"))
    assert features["cost"] == 5.0
    assert features["cheap_clean"] == 0.0
    assert _score("Avenge") < _score("Wrath of God")


@pytest.mark.parametrize(
    "name", ["March of Souls", "The Phasing of Zhalfir", "Mogg Infestation"]
)
def test_tokens_for_the_wiped_players_refill_the_board(name):
    """Each creature destroyed gives its controller a token, and the player who
    creates a token controls it (CR 111.2): no rider for the caster, and the
    board comes back as bodies, so the sweep is not clean."""
    features = board_wipe.features(_real(name))
    assert features["lethal"] == 1.0
    assert features["rider"] == 0.0
    assert features["clean"] == 0.0


@pytest.mark.parametrize(
    ("name", "lethal"),
    [
        ("Ichor Explosion", True),
        ("Corpse Explosion", True),
        ("Cloudkill", True),
        ("Specter of Mortality", True),
        ("Chandra's Ignition", True),
        ("Waltz of Rage", True),
        ("Nibelheim Aflame", True),
        ("Rupture", True),
        ("Volcanic Eruption", False),
        ("Kindle the Carnage", False),
        ("Too Greedily, Too Deep", False),
    ],
)
def test_an_amount_that_is_no_count_reads_by_what_it_names(name, lethal):
    """No wrapper decides an amount that counts nothing. The size of an object
    the caster picks reads at the kill size: one paid as a cost (Ichor
    Explosion's sacrificed creature, its ruling: "as it last existed on the
    battlefield"; Corpse Explosion's exiled creature card); a target among the
    creatures they control (Chandra's Ignition's "Target creature you control
    deals damage equal to its power", its power read as the spell resolves, its
    ruling; Nibelheim Aflame's "It" back to one); or the creature the sweep's own
    instruction has them sacrifice (Rupture's "Sacrifice a creature": no player
    named, so the caster follows it, CR 608.2c, and sacrifices one they control,
    CR 701.21a). So does the greatest mana value of a commander you own
    (Cloudkill). Specter of Mortality's creature cards exiled from your own
    graveyard scale. Narrow: Volcanic Eruption's "Destroy X target Mountains" may
    take anyone's, yours too, but nothing makes them yours and X caps them;
    Kindle the Carnage's card is discarded at random, no pick; Too Greedily, Too
    Deep's creature card may come from any graveyard."""
    features = board_wipe.features(_real(name))
    assert features["lethal"] == float(lethal)
    assert features["small"] == float(not lethal)


def test_the_sources_own_power_is_its_printed_power():
    """Jack of Hearts, Volatile Hero's dying "he deals damage equal to his power
    to each creature" uses his power as he last existed (CR 608.2h); the read
    takes the card's printed 2, its own call. A printed power is read as it is
    and an amount it becomes is never below 0 (CR 107.1b): the tree's power set
    to 5 and to -1 (machinery, no real card) sweeps for 5 and for 0."""
    card = _real("Jack of Hearts, Volatile Hero")
    (sweep,) = board_wipe._sweeps(card)
    assert sweep.mag == 2
    (tree,) = signal_trees_for(card, bulk=card)
    for printed, mag in ((5, 5), (-1, 0)):
        (sweep,) = board_wipe._tree_sweeps(replace(tree, power=printed), walker=False)
        assert sweep.mag == mag


def _deck(*names: str, size: int = 100) -> tuple[dict, ...]:
    """A deck of ``names``, filled to ``size`` cards with Forests."""
    return tuple(_real(n) for n in [*names, *["Forest"] * (size - len(names))])


def test_a_count_of_a_type_the_deck_holds_reads_what_it_has_out():
    """Olivia's Wrath's -X/-X counts the Vampires you control, Gates Ablaze's
    damage the Gates: a deck has out its share of them over a board of eight of
    its own permanents, so the sweep kills in proportion, rising smoothly with
    the count — no step. Blood Rites' 36 Vampires of 100 read 2.88."""
    wrath, gates = _real("Olivia's Wrath"), _real("Gates Ablaze")
    assert board_wipe.features(wrath)["lethal"] == 0.0
    vampires = board_wipe.features(wrath, _deck(*["Sengir Vampire"] * 36))
    assert vampires["lethal"] == pytest.approx(0.72)
    assert vampires["small"] == pytest.approx(0.28)
    assert job_score(wrath, "board_wipe", _deck()) == job_score(wrath, "board_wipe")
    lethal = [
        board_wipe.features(gates, _deck(*["Gateway Plaza"] * n))["lethal"]
        for n in (0, 3, 7, 8, 15, 50)
    ]
    assert lethal == pytest.approx([0.0, 0.06, 0.14, 0.16, 0.3, 1.0])
    scores = [
        job_score(gates, "board_wipe", _deck(*["Gateway Plaza"] * n))
        for n in (3, 7, 8, 15)
    ]
    assert scores == sorted(scores)
    assert scores[2] - scores[1] < 0.05  # no cliff between seven Gates and eight


@pytest.mark.parametrize("name", ["Ichor Explosion", "Chandra's Ignition"])
def test_a_picked_creatures_power_is_the_decks_biggest(name):
    """Ichor Explosion's X is the sacrificed creature's power, Chandra's
    Ignition's damage the power of the creature you target among your own: in a
    deck of 2/2s half a kill; with a 6/6 to pick, lethal."""
    card = _real(name)
    assert board_wipe.features(card, _deck("Grizzly Bears"))["lethal"] == (
        pytest.approx(0.5)
    )
    assert board_wipe.features(card, _deck("Colossal Dreadmaw"))["lethal"] == 1.0


def test_a_negative_power_stays_negative_in_the_deck_read():
    """Loot, the Anomaly is a -2/4. A rule that checks his power uses the real
    value (his ruling; a comparison uses a negative value, CR 107.1b), so the
    deck read's size keeps the sign. An effect's amount computed from it is 0,
    never negative (CR 107.1b; his ruling: damage "equal to a creature's power"
    is none): Ichor Explosion with only him to sacrifice is a -0/-0, no kill and
    no pump."""
    loot = _real("Loot, the Anomaly")
    (facts,) = (f for _r, f in board_wipe._board((loot,)))
    assert board_wipe._size(loot, facts, "power") == -2
    ichor = _real("Ichor Explosion")
    deck = _deck("Loot, the Anomaly")
    (sweep,) = board_wipe._in_deck(board_wipe._sweeps(ichor), deck)
    assert sweep.mag == 0
    features = board_wipe.features(ichor, deck)
    assert features["lethal"] == 0.0
    assert features["small"] == 1.0


def test_a_card_with_no_deck_decided_amount_scores_alike_in_any_deck():
    """Wrath of God's sweep owes nothing to the deck: one score everywhere."""
    assert board_wipe.deck_features(_real("Wrath of God"), _deck()) is None
    assert job_score(_real("Wrath of God"), "board_wipe", _deck()) == _score(
        "Wrath of God"
    )
