"""Lane false positives the serve-ident census exposed (docs/plans/serve-idents-
and-avenue-support.md §2 "Lane false positives").

A spec that serves off a lane's idents inherits every card the lane misfires on,
so each fix below is pinned on the real card that exposed it, beside a real card
the lane must keep.
"""

import pytest

from mtg_utils._analysis.lanes.graveyard_lifeloss import self_mill_fill
from mtg_utils._card_ir.crosswalk import (
    answers_its_target,
    change_zone_dirs,
    effect_filter,
    filter_controller,
    filter_inzone_zones,
    filter_owned_controller,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


# ── a keyword word in the card's own name is not the keyword ─────────────────


def test_impending_flux_is_no_suspend_payoff():
    # A Paradox / foretell sorcery that names itself; no impending ability
    # (CR 702.176a) and no time counter.
    assert "suspend_matters|you|" not in _idents("Impending Flux")
    assert "suspend_matters|you|" in _idents("Ancestral Vision")


@pytest.mark.parametrize("name", ["The Book of Exalted Deeds", "Exalted Angel"])
def test_exalted_in_a_name_is_no_exalted(name):
    assert "exalted_lone_attacker|you|" not in _idents(name)


@pytest.mark.parametrize("name", ["Rafiq of the Many", "Sublime Archangel"])
def test_exalted_cards_keep_the_lane(name):
    assert "exalted_lone_attacker|you|" in _idents(name)


# ── a suspect counter is not the suspect action ───────────────────────────────


def test_suspect_counters_are_not_suspecting():
    # Investigator's Journal enters with suspect counters (a named counter,
    # CR 122.1); it never suspects a creature (CR 701.60a).
    assert "suspect_makers|you|" not in _idents("Investigator's Journal")
    assert "suspect_makers|you|" in _idents("Case of the Stashed Skeleton")


# ── a flavor word is not a partner ability ────────────────────────────────────


def test_astarions_friends_mode_is_no_partner():
    # "Friends —" is a modal flavor word (CR 207.2d) MTGJSON lists as a
    # keyword; the partner abilities are CR 702.124a's list.
    assert "partner_background|you|" not in _idents("Astarion, the Decadent")
    assert "partner_background|you|" in _idents("Thrasios, Triton Hero")


# ── colorless hate is not a colorless payoff ──────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Consign to Memory", "Ceremonious Rejection", "Infernal Reckoning"]
)
def test_colorless_hate_is_no_colorless_payoff(name):
    # Countering a colorless spell cancels it (CR 701.6a); exiling a colorless
    # creature answers it too — reading both as hate, not a payoff, is the
    # lane's own decision.
    assert "colorless_matters|you|" not in _idents(name)


@pytest.mark.parametrize(
    "name", ["Forsaken Monument", "Kozilek's Sentinel", "Ugin, the Ineffable"]
)
def test_colorless_payoffs_keep_the_lane(name):
    assert "colorless_matters|you|" in _idents(name)


# ── graveyard_matters|you is a payoff on cards in YOUR graveyard ──────────────


@pytest.mark.parametrize("name", ["Bulette", "Deathreap Ritual"])
def test_morbid_is_a_death_payoff_not_a_graveyard_one(name):
    # "If a creature died this turn": dies means put into a graveyard from
    # the battlefield (CR 700.4) — a death condition, not cards in a graveyard.
    idents = _idents(name)
    assert not any(i.startswith("graveyard_matters|") for i in idents)
    assert "death_matters|any|" in idents


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # "exile target player's graveyard"
        ("Bojuka Bog", "opponents"),
        ("Angel of Finality", "opponents"),
        # "exile up to one target card from a graveyard"
        ("Afterthought Sentry", "any"),
    ],
)
def test_graveyard_hate_is_no_own_graveyard_payoff(name, scope):
    idents = _idents(name)
    assert "graveyard_matters|you|" not in idents
    assert f"graveyard_matters|{scope}|" in idents


@pytest.mark.parametrize(
    "name", ["Sidisi, Brood Tyrant", "Golgari Grave-Troll", "Gravedigger"]
)
def test_own_graveyard_payoffs_keep_the_lane(name):
    assert "graveyard_matters|you|" in _idents(name)


def test_an_exile_from_your_own_graveyard_beside_hate_keeps_you():
    # "Exile target instant or sorcery card from your graveyard and target
    # instant or sorcery card from an opponent's graveyard": one half is hate,
    # the other uses your graveyard.
    idents = _idents("Spelltwine")
    assert "graveyard_matters|you|" in idents
    assert "graveyard_matters|opponents|" in idents


def test_an_opponents_triggered_mill_is_not_yours():
    # "Whenever an opponent loses life, that player mills that many cards."
    test_card_ir("Mindcrank")
    assert not any(self_mill_fill(t) for t in trees_for(test_card("Mindcrank")))
    assert "graveyard_makers|you|" not in _idents("Mindcrank")


# ── Retirement canary: "that player's graveyard" with no owner ───────────────


@pytest.mark.parametrize("name", ["Skullsnatcher", "Zombie Cannibal"])
def test_gy_hate_that_players_graveyard_scope(name):
    # "exile … from that player's graveyard" — the damaged player, an opponent.
    idents = _idents(name)
    assert "graveyard_matters|opponents|" in idents
    assert "graveyard_matters|any|" not in idents
    assert "graveyard_matters|you|" not in idents


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Skullsnatcher", "Zombie Cannibal"])
def test_gy_hate_that_players_graveyard_canary(name):
    """Retirement canary for the ``_GY_OPP_RE`` description check in
    ``graveyard_lifeloss._graveyard_matters``'s graveyard-hate arm: phase
    v0.104.0 drops "that player's" off the exile's target filter, so the
    filter names no owner and reads "a graveyard"."""
    test_card_ir(name)
    exiles = [
        c.node
        for t in trees_for(test_card(name))
        for u in t.units
        for c in u.effects
        if answers_its_target(c.node)
        and (
            change_zone_dirs(c.node)[0] == "Graveyard"
            or "Graveyard" in filter_inzone_zones(effect_filter(c.node))
        )
    ]
    assert exiles
    assert all(
        not (
            filter_owned_controller(effect_filter(n))
            or filter_controller(effect_filter(n))
        )
        for n in exiles
    ), (
        "graveyard_lifeloss: RETIRE-READY — phase now carries the owner of "
        f"{name}'s graveyard exile. Delete the _GY_OPP_RE check in the "
        "graveyard-hate arm of _graveyard_matters and this canary."
    )
