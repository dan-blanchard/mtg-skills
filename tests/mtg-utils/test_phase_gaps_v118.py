"""Real-card pins for the reads the phase v0.118.0 pin bump taught (renamed shapes,
fail-closed residues), and the retirement canary of the peeled-subject read."""

from __future__ import annotations

import json

import pytest

from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


@pytest.mark.retirement_canary
def test_peeled_subject_canary():
    """``recovery._peeled_subject``: phase parks "target player discards a card for
    each creature it devoured" (Tar Fiend) with its subject cut, as
    "discard a card for each …"; the seam reads the player back off the unit's
    own description."""
    raw = json.dumps(test_phase_records("Tar Fiend"))
    assert '"description": "discard a card for each creature it devoured"' in raw, (
        "recovery._peeled_subject: RETIRE-READY — phase keeps the subject of Tar "
        "Fiend's parked discard (or types it). Once no parked clause loses its "
        "subject, delete _peeled_subject, _PEELED_SUBJECT_RX and this canary."
    )


@pytest.mark.parametrize("name", ["Tar Fiend", "Whispering Specter"])
def test_peeled_discard_is_the_opponents(name):
    """ "Target player / that player discards …" parked with its subject cut is an
    opponent's discard (CR 701.9a), never your own outlet."""
    idents = _idents(name)
    assert ("opponent_discard", "opponents", "") in idents
    assert ("discard_outlet", "you", "") not in idents


def test_imperative_parked_discard_stays_yours():
    """Impetuous Lootmonger's "discard a card, then heist target opponent's
    library": you discard, though the clause names an opponent."""
    assert not {k for k, _s, _su in _idents("Impetuous Lootmonger")} & {
        "opponent_discard"
    }


def test_parked_opponent_sacrifice_is_an_edict():
    """Papalymo Totolymo's parked "Each opponent who lost life this turn sacrifices
    a creature …" (CR 701.21a)."""
    assert ("edict_makers", "opponents", "") in _idents("Papalymo Totolymo")


def test_one_chosen_equipment_is_no_sweep():
    """Light of Judgment's "Destroy up to one Equipment attached to that creature"
    chooses one object: removal, not mass removal."""
    keys = {k for k, _s, _su in _idents("Light of Judgment")}
    assert "removal" in keys
    assert "mass_removal" not in keys


def test_a_graveyard_pick_reanimates():
    """Technomancer's ``ChooseFromZone`` pick feeding the ``ChangeZone``."""
    idents = _idents("Technomancer")
    assert ("creature_recursion", "you", "battlefield") in idents
    assert ("reanimator", "you", "") in idents


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # "you and target opponent each create a tapped Powerstone token": yours
        ("Thran Spider", ("artifacts_matter", "you", "token")),
        # "you and target opponent each draw a card": a gift to one opponent
        ("Farsight Adept", ("target_player_draws", "any", "")),
        # "you and that player each draw two cards": your engine, not every player's
        ("Black Widow, Intel Expert", ("card_draw_engine", "you", "")),
        # "You and that player each sacrifice a creature": an opponent is forced
        ("Infernal Offering", ("edict_makers", "opponents", "")),
        # "target opponent may draw four cards": the opponent draws
        ("Kuroki, Thief of Talents", ("card_draw_engine", "opponents", "")),
    ],
)
def test_you_and_one_opponent(name, ident):
    assert ident in _idents(name)


def test_the_pair_is_not_every_player():
    keys = {(k, s) for k, s, _su in _idents("Black Widow, Intel Expert")}
    assert ("card_draw_engine", "each") not in keys
    assert ("group_hug_draw", "each") not in keys


@pytest.mark.parametrize("name", ["Apocalypse Hydra", "Neverwinter Hydra"])
def test_enters_with_counters_on_itself(name):
    assert ("self_counter_grow", "you", "") in _idents(name)


def test_reveal_cards_from_their_hand():
    idents = _idents("Blackmail")
    assert ("hand_disruption", "opponents", "") in idents
    assert ("opponent_discard", "opponents", "") in idents


def test_parked_energy_payment():
    assert ("energy_matters", "you", "") in _idents("Pia Nalaar, Chief Mechanic")
