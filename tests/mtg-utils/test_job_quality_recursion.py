"""The recursion read (``job_quality.recursion``): how well a card brings cards
back out of a graveyard, off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import job_score, recursion
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str, deck: list[dict] | None = None) -> float:
    score = job_score(_real(name), "recursion", deck)
    assert score is not None, name
    return score


def _deck(names: list[str]) -> list[dict]:
    return [_real(n) for n in names]


@pytest.mark.parametrize(
    "name",
    [
        "Reanimate",
        "Animate Dead",
        "Gravedigger",
        "Eternal Witness",
        "Regrowth",
        "Living Death",
        "Sun Titan",
        "Kitchen Finks",
        "Raise Dead",
        "Victimize",
        "Meren of Clan Nel Toth",
        "Feign Death",
    ],
)
def test_every_recursion_kind_scores(name):
    """A return of a creature card or any card, to the battlefield or a hand, in
    a spell, an enters trigger or an engine; and a card returning itself
    (Kitchen Finks's persist, CR 702.79a; Feign Death's granted return).
    Victimize and Meren choose the card in a clause before the return."""
    assert recursion.features(_real(name)) is not None


@pytest.mark.parametrize(
    "name", ["Lightning Bolt", "Counterspell", "Buried Alive", "Cultivate"]
)
def test_a_card_with_no_return_scores_none(name):
    """Buried Alive puts creature cards INTO a graveyard: a tutor, not
    recursion."""
    assert job_score(_real(name), "recursion") is None


def test_a_mass_reanimation_reads_above_one_creature_to_hand():
    """Living Death returns every creature card in every graveyard to the
    battlefield; Gravedigger one creature card to your hand."""
    assert recursion.features(_real("Living Death"))["mass"] == 1.0
    assert recursion.features(_real("Living Death"))["symmetric"] == 1.0
    assert _score("Living Death") > _score("Gravedigger")


def test_the_battlefield_reads_above_a_hand():
    """Animate Dead returns a creature card to the battlefield; Raise Dead to
    your hand."""
    assert recursion.features(_real("Animate Dead"))["battlefield"] == 1.0
    assert recursion.features(_real("Raise Dead"))["battlefield"] == 0.0
    assert _score("Animate Dead") > _score("Raise Dead")


def test_an_engine_repeats_and_a_spell_does_not():
    """Sun Titan's "Whenever Sun Titan enters or attacks" fires again each
    attack; Reanimate is a one-shot. Sun Titan's "mana value 3 or less" is a
    cap."""
    titan = recursion.features(_real("Sun Titan"))
    assert titan["repeat"] == 1.0
    assert titan["capped"] == 1.0
    assert titan["broad"] == 1.0  # any permanent card
    assert recursion.features(_real("Reanimate"))["repeat"] == 0.0


def test_a_return_of_a_card_chosen_in_an_earlier_clause_is_read():
    """Meren's "choose target creature card in your graveyard ... return it to
    the battlefield. Otherwise, put it into your hand" binds the return to the
    choice (``crosswalk.chosen_graveyard_recursion``): an end-step engine."""
    meren = recursion.features(_real("Meren of Clan Nel Toth"))
    assert meren["battlefield"] == 1.0
    assert meren["repeat"] == 1.0
    assert recursion.creature_only(_real("Victimize"))


def test_a_self_return_reads_as_itself_only_and_once():
    """Persist returns Kitchen Finks itself, once per counter-free death."""
    finks = recursion.features(_real("Kitchen Finks"))
    assert finks["self_only"] == 1.0
    assert finks["repeat"] == 0.0
    assert finks["battlefield"] == 1.0


def test_any_card_reads_broad():
    """Regrowth and Eternal Witness return any card; Raise Dead a creature
    card."""
    assert recursion.features(_real("Regrowth"))["broad"] == 1.0
    assert recursion.features(_real("Eternal Witness"))["broad"] == 1.0
    assert recursion.features(_real("Raise Dead"))["broad"] == 0.0


_CREATURES = ["Llanowar Elves", "Gravedigger", "Kitchen Finks", "Sun Titan"]
_SPELLS = ["Lightning Bolt", "Counterspell", "Cultivate", "Regrowth"]


def test_a_creature_light_deck_lowers_a_reanimation_spell():
    """A creature recursion needs creature cards in the deck: in a deck of
    spells Reanimate has nothing to return (a token is no card to return —
    CR 111.7); any-card recursion runs in any deck."""
    reanimate, regrowth = _real("Reanimate"), _real("Regrowth")
    spells, bodies = _deck(_SPELLS), _deck(_CREATURES)
    assert recursion.creature_only(reanimate)
    assert not recursion.creature_only(regrowth)
    assert recursion.deck_fit(reanimate, spells) == 0.0
    assert recursion.deck_fit(reanimate, bodies) > 0.5
    assert recursion.deck_fit(regrowth, spells) == 1.0
    assert _score("Reanimate", spells) < _score("Reanimate", bodies)
    assert _score("Reanimate", bodies) <= _score("Reanimate")
