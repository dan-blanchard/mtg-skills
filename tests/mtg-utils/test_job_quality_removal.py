"""The removal read (``job_quality.removal``): how well a card does single-target
removal, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import job_score, read_for, removal
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return job_score(_real(name), "interaction")


def test_cheap_unconditional_instant_removal_reads_best():
    """Swords to Plowshares and Path to Exile (one mana, any creature, instant,
    exile) read above Murder (three mana), which reads above Doom Blade (the
    same, held to nonblack creatures)."""
    swords, path = _score("Swords to Plowshares"), _score("Path to Exile")
    assert swords == path
    assert swords > _score("Murder") > _score("Doom Blade")


def test_a_small_burn_reads_below_a_kill():
    """Three damage misses most of a Commander board: Lightning Bolt reads as
    conditional removal, below Swords to Plowshares."""
    assert removal.features(_real("Lightning Bolt"))["small"] == 1.0
    assert _score("Lightning Bolt") < _score("Swords to Plowshares")


def test_a_sacrifice_activation_reads_as_a_poor_engine():
    """Goblin Firebomb destroys any permanent, but only for {7}, tapping and
    sacrificing itself: below Beast Within's three-mana instant."""
    assert removal.features(_real("Goblin Firebomb"))["activated_sac"] == 1.0
    assert _score("Goblin Firebomb") < _score("Beast Within")


def test_a_land_back_reads_as_a_free_slot():
    """A modal double-faced card whose back is a land costs no spell slot."""
    assert removal.features(_real("Fell the Profane // Fell Mire"))["land_back"] == 1.0


@pytest.mark.parametrize(
    "name",
    [
        "Stifle",  # countering an ability alone is no interaction answer
        "Animate Dead",  # a -1/-0 on the creature it returns never removes one
        "Llanowar Elves",
    ],
)
def test_no_removal_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None


def test_an_edict_on_each_opponent_is_removal():
    """Grave Pact's "each other player sacrifices a creature" is removal, and
    one that regeneration can't answer: sacrificing doesn't destroy (CR
    701.21a)."""
    assert removal.features(_real("Grave Pact"))["edict_each"] == 1.0


def test_job_score_routes_interaction_to_the_removal_read():
    card = _real("Murder")
    feats = removal.features(card)
    assert feats is not None
    weighted = round(sum(removal.WEIGHTS[k] * v for k, v in feats.items()), 3)
    assert job_score(card, "interaction") == weighted
    assert job_score(card, "card_draw") is None
    assert job_score(card, None) is None


def test_read_for_names_which_reads_order_candidates():
    """Removal and ramp only gate an upgrade's candidates; board wipes, card draw
    and protection also order them, blended with play-rate (ADR-0060)."""
    orders = {
        job: read.orders
        for job in ("interaction", "protection", "board_wipe", "ramp", "card_draw")
        if (read := read_for(job)) is not None
    }
    assert orders == {
        "interaction": False,
        "protection": True,
        "board_wipe": True,
        "ramp": False,
        "card_draw": True,
    }
    assert read_for("counter") is None
    assert read_for(None) is None


def test_read_for_names_where_theme_fit_and_the_read_order_the_tuner():
    """Theme fit breaks a near tie on the read for card draw and ramp; the wipe
    read orders the wipe fill (measured on the 25 precons, 2026-10-24)."""
    jobs = ("interaction", "protection", "board_wipe", "ramp", "card_draw")
    assert {j for j in jobs if read_for(j).theme_ties} == {"card_draw", "ramp"}
    assert {j for j in jobs if read_for(j).fill_orders} == {"board_wipe"}


def test_a_double_faced_card_is_priced_by_its_front_face():
    """A modal double-faced card carries its mana cost per face, not on the
    record: Fell the Profane costs {2}{B}{B}, not the no-mana-cost constant."""
    from mtg_utils._analysis.job_quality._common import front_mana_cost, unpriced

    card = _real("Fell the Profane // Fell Mire")
    assert front_mana_cost(card) == "{2}{B}{B}"
    assert not unpriced(card)


def test_a_fight_the_synthesis_stage_adds_reads_as_removal():
    """The read walks the signal trees (``signal_trees_for``), so a clause phase
    leaves to the tree-synthesis stage reaches it as it reaches the lanes:
    Tolsimir's Wolves fight a creature you don't control (a fight is each
    creature dealing damage equal to its power to the other, CR 701.14a)."""
    assert _score("Tolsimir, Friend to Wolves") is not None


def test_an_exile_on_a_card_that_leaves_by_itself_reads_below_cast_out():
    """An exile that lasts until the card leaves (CR 610.3) ends when the card
    goes on its own: an Aura is put into the graveyard once its host leaves (CR
    704.5m — Sheltered by Ghosts), and Static Prison sacrifices itself each turn
    unless you pay energy. Both read below Cast Out, which leaves only when an
    opponent removes it, and the one that sacrifices itself lowest."""
    sheltered = removal.features(_real("Sheltered by Ghosts"))
    prison = removal.features(_real("Static Prison"))
    assert sheltered["aura_host"] == 1.0
    assert sheltered["self_sacrifice"] == 0.0
    assert prison["self_sacrifice"] == 1.0
    assert prison["aura_host"] == 0.0
    cast_out = removal.features(_real("Cast Out"))
    assert cast_out["aura_host"] == cast_out["self_sacrifice"] == 0.0
    assert _score("Static Prison") < _score("Sheltered by Ghosts") < _score("Cast Out")


@pytest.mark.parametrize("name", ["Deadly Rollick", "Snuff Out"])
def test_a_free_alternative_cost_reads_as_cheap(name):
    """Phase carries a free alternative cost in ``casting_options``: Deadly
    Rollick is cast without paying its mana cost while you control a commander,
    Snuff Out for 4 life while you control a Swamp. Neither costs four mana."""
    assert removal.features(_real(name))["cheap"] == 1.0


def test_winnow_reads_as_conditional_removal():
    """Winnow destroys its target only "if another permanent with the same name
    is on the battlefield": a conditional answer, not the unconditional
    two-mana instant phase's parse alone would read."""
    features = removal.features(_real("Winnow"))
    assert features["unconditional"] == 0.0
    assert features["cheap_instant_unconditional"] == 0.0


@pytest.mark.retirement_canary
def test_winnow_condition_dropped_canary():
    """Phase (v0.104.0) drops Winnow's same-name condition whole: its Destroy
    carries no condition and no filter predicate, so ``removal._CONDITION_DROPPED``
    names it. RETIRE-READY when this fails: delete Winnow's row there."""
    (face,) = test_phase_records("Winnow")
    (spell,) = face["abilities"]
    assert spell["effect"]["type"] == "Destroy"
    assert spell["condition"] is None
    assert spell["effect"]["target"]["properties"] == []


def test_a_searched_card_put_on_top_is_not_a_tuck():
    """Insatiable Avarice searches your library and puts the found card on top:
    card selection (the search precedes the library placement, as a reveal or a
    mill does), never a permanent tucked off the battlefield. The read used to
    score it as soft removal with no permanent type at all."""
    assert removal.features(_real("Insatiable Avarice")) is None
    assert _score("Insatiable Avarice") is None
    # A real single-target tuck still reads.
    assert _score("Condemn") is not None


def test_a_counterspell_is_an_interaction_answer():
    """A Counter whose target reaches a spell on the stack is read (membership:
    the interaction read gates, ADR-0060), so a counterspell can replace a
    removal spell on the interaction page as the guides' Fierce Guardianship
    does; one that counters only an ability (Stifle) is not the row's answer.
    A counter of any spell is unconditional; one of a class (Negate's
    noncreature) is not."""
    assert _score("Counterspell") is not None
    assert _score("Fierce Guardianship") is not None
    assert _score("Stifle") is None
    assert removal.features(_real("Counterspell"))["unconditional"] == 1.0
    assert removal.features(_real("Negate"))["unconditional"] == 0.0
    assert removal.features(_real("Fierce Guardianship"))["cheap"] == 1.0  # free


def test_a_sorcery_speed_activation_is_not_instant_removal():
    """The one instant-speed read (``crosswalk.at_instant_speed``): an activation
    held to sorcery timing (CR 602.5d — Westfold Rider's "Sacrifice this creature:
    Destroy target artifact or enchantment. Activate only as a sorcery") is not
    usable in response, where the read used to call every activation instant; an
    unrestricted activation (Seal of Doom's sacrifice, CR 117.1b) and an instant
    (Murder, CR 117.1a) are."""
    assert removal.features(_real("Westfold Rider"))["instant"] == 0.0
    assert removal.features(_real("Seal of Doom"))["instant"] == 1.0
    assert removal.features(_real("Murder"))["instant"] == 1.0


def test_a_sorcery_cast_as_though_it_had_flash_is_instant_removal():
    """Mutual Destruction's "This spell has flash as long as you control a
    permanent with flash" rides phase's record-level ``casting_options``
    (``AsThoughHadFlash``), never an ability: CR 702.8a lets it be cast any time
    you could cast an instant, so it answers in response like Murder."""
    assert removal.features(_real("Mutual Destruction"))["instant"] == 1.0
