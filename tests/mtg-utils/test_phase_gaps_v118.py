"""Real-card pins for the reads the phase v0.118.0 pin bump taught (renamed shapes,
fail-closed residues), and the retirement canaries of the peeled-subject read and
the recovered graveyard land play. Sower of Discord's and Helm of Obedience's
parked clauses are bridge-ledger rows, retired by ``test_bridge_ledger``'s gap
check; here only the idents they serve are pinned."""

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


@pytest.mark.retirement_canary
def test_graveyard_land_play_is_still_a_residue_canary():
    """``crosswalk.plays_lands_from_graveyard``'s recovered arm: phase's static
    parser fails on Serra Paragon's "Once during each of your turns, you may play a
    land from your graveyard or cast a permanent spell with mana value 3 or less
    from your graveyard" and parks it whole; the seam recovers it as a
    ``cast_from_zone`` naming a land and your graveyard."""
    parked = [
        ab["effect"].get("description") or ""
        for rec in test_phase_records("Serra Paragon")
        for ab in rec.get("abilities") or ()
        if ab["effect"].get("name") == "static_structure"
    ]
    assert any("play a land from your graveyard" in d for d in parked), (
        "plays_lands_from_graveyard's recovered arm: RETIRE-READY — phase types "
        "Serra Paragon's graveyard permission. Once no parked clause plays a land "
        "from your graveyard, delete the recovered arm and this canary."
    )


@pytest.mark.parametrize("name", ["Serra Paragon", "Eye of Duskmantle"])
def test_recovered_graveyard_land_play_recurs_lands(name):
    """Playing a land puts it onto the battlefield from the zone it was in (CR
    116.2a), here your graveyard: what keeps a lands deck's lands, as Crucible of
    Worlds does."""
    idents = _idents(name)
    assert ("permanent_recast", "you", "land") in idents
    assert ("landfall", "you", "") in idents


def test_serra_paragon_is_a_recast_engine():
    """Serra Paragon's "cast a permanent spell with mana value 3 or less from your
    graveyard" is the repeatable permanent-recast engine
    (``has_permanent_recast``): the mana-value cap sits between the spell and its
    zone, which the recovered-arm regex admits."""
    assert ("permanent_recast", "you", "") in _idents("Serra Paragon")


def test_graveyard_land_prohibition_recurs_nothing():
    """Tomik's "Your opponents can't play land cards from graveyards" names no
    graveyard of yours."""
    assert ("permanent_recast", "you", "land") not in _idents(
        "Tomik, Distinguished Advokist"
    )


def test_chosen_players_drain():
    """Sower of Discord: of two chosen players, the other loses the life when one
    is dealt damage (its rulings: that loss isn't damage, only a life-total change,
    CR 119.3), so two chosen opponents drain each other."""
    assert ("lifeloss_makers", "opponents", "") in _idents("Sower of Discord")


def test_mill_until_creature_steals_it():
    """Helm of Obedience puts a milled creature card of the opponent's onto the
    battlefield under your control (CR 110.2: you control it)."""
    assert ("gain_control", "you", "") in _idents("Helm of Obedience")


# ── exile_instead: a mana rider exiling the spell it pays for, parked ─────────


def _forgers_foundry_rider() -> dict:
    (rec,) = test_phase_records("Forger's Foundry")
    return (rec["abilities"][0].get("sub_ability") or {}).get("effect") or {}


@pytest.mark.retirement_canary
def test_mana_spent_exile_is_still_a_residue_canary():
    """Forger's Foundry's "When you spend this mana to cast …, you may exile that
    spell instead of putting it into its owner's graveyard as it resolves": phase
    parks the rider, which the recovery grammar reads as ``exile_instead``."""
    rider = _forgers_foundry_rider()
    retire = (
        "Forger's Foundry: RETIRE-READY — phase types its mana rider. Once no "
        "residue carries it, delete the exile_instead row of "
        "clause_grammar.REPLACEMENT_TOKENS and its recovery.ALLOWLIST entry, and "
        "check that crosswalk.diverts_from_graveyard reads phase's new form."
    )
    assert rider.get("type") == "Unimplemented", retire
    assert "instead of putting it into" in (rider.get("description") or ""), retire


def test_a_parked_exile_instead_recovers_and_reads_no_graveyard_card():
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card, test_card_ir

    test_card_ir("Forger's Foundry")  # seeds the trees from the snapshot
    tokens = [
        c.recovered_by
        for t in trees_for(test_card("Forger's Foundry"))
        for c in t.iter_concepts()
    ]
    assert "exile_instead" in tokens
    assert "graveyard_matters" not in {s.key for s in test_signals("Forger's Foundry")}


# ── blight: a draw and a blight parked as one clause ──────────────────────────


@pytest.mark.retirement_canary
def test_draw_and_blight_is_still_a_residue_canary():
    """Sinister Gnarlbark's "draw a card and blight 1": phase parks the clause,
    whose blight (CR 701.68a) the recovery grammar reads as ``blight``."""
    (rec,) = test_phase_records("Sinister Gnarlbark")
    effect = rec["triggers"][0]["execute"]["effect"]
    assert effect["type"] == "Unimplemented", (
        "Sinister Gnarlbark: RETIRE-READY — phase types its draw and blight. Once "
        "no residue carries a blight, delete the blight verb of "
        "clause_grammar._SIMPLE_VERB, its recovery.ALLOWLIST entry and the "
        "recovered arm of crosswalk.blight_placements."
    )


def test_a_parked_blight_recovers_as_a_blight():
    from mtg_utils._card_ir.crosswalk import blight_placements
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card, test_card_ir

    test_card_ir("Sinister Gnarlbark")  # seeds the trees from the snapshot
    (unit,) = [u for t in trees_for(test_card("Sinister Gnarlbark")) for u in t.units]
    assert [c.recovered_by for c in unit.effects] == ["draw", "blight"]
    assert blight_placements(unit)
    assert ("minus_counters_matter", "you", "") in _idents("Sinister Gnarlbark")


@pytest.mark.parametrize(
    ("clause", "token"),
    [
        ("blight 1", "blight"),
        ("each opponent blights X", "blight"),
        # Rottenmouth Viper: a counter named blight is no blight
        ("for each blight counter on it", None),
    ],
)
def test_blight_verb_takes_its_count(clause, token):
    from mtg_utils._card_ir.clause_grammar import parse_clause, scan_clause

    assert (parse_clause(clause) or scan_clause(clause)) == token
