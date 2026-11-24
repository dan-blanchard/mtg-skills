"""Real-card pins for the reads the phase v0.131.0 pin bump taught (renamed shapes,
newly typed clauses), and the retirement canary of the spell that "grows itself".
The renamed shapes written back on the raw records are pinned in
``test_shape_compat``."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.trees import _iter_raw_dicts
from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {s.key for s in test_signals(name)}


def _nodes(node: object) -> list[dict]:
    return list(_iter_raw_dicts(node, lambda _d: True))


# ── SpellsCast / LifeLost: the turn window moved onto a field ────────────────


@pytest.mark.parametrize(
    "name", ["Brightspear Zealot", "Effortless Master", "Xerex Strobe-Knight"]
)
def test_second_spell_reads_this_turns_spell_count(name):
    """ "If you've cast two or more spells this turn": a ``SpellsCast`` quantity
    with no ``window`` (``SpellsCastThisTurn`` before)."""
    assert ("second_spell_matters", "you", "") in _idents(name)


def test_last_turns_spell_count_is_no_second_spell():
    # the werewolves' "if no spells were cast last turn": ``window: LastTurn``
    assert "second_spell_matters" not in _keys("Afflicted Deserter")


@pytest.mark.parametrize(
    "name", ["Sygg, River Cutthroat", "Bloodchief Ascension", "Rakdos, Lord of Riots"]
)
def test_life_lost_this_turn_matters(name):
    assert "lifeloss_matters" in _keys(name)


# ── CastWithFlash: flash's own static mode ───────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Vedalken Orrery", "Leyline of Anticipation", "Teferi, Time Raveler"]
)
def test_cast_as_though_they_had_flash(name):
    idents = _idents(name)
    assert ("flash_grant", "you", "") in idents
    assert "spell_keyword_grant" in {key for key, _scope, _subject in idents}


def test_flash_for_auras_and_equipment_is_voltron():
    # Sigarda's Aid: "You may cast Aura and Equipment spells as though they had
    # flash" — the typed spell filter rides the bare CastWithFlash mode too.
    assert "voltron_matters" in _keys("Sigarda's Aid")


# ── The Oblivion Ring pair: two triggers, no duration ────────────────────────


@pytest.mark.parametrize(
    "name", ["Oblivion Ring", "Fiend Hunter", "Journey to Nowhere", "Banisher Priest"]
)
def test_exile_until_the_card_leaves(name):
    """The older wording's enters trigger beside "When ~ leaves the battlefield,
    return the exiled card" (a ``ChangeZoneAll`` of ``ExiledBySource``), and the
    newer "until ~ leaves the battlefield" duration (CR 610.3)."""
    assert ("exile_until_leaves", "you", "") in _idents(name)


def test_a_leaves_return_alone_is_no_exile_until_leaves():
    # Parallax Wave exiles off an activated ability, not its own enters trigger.
    assert "exile_until_leaves" not in _keys("Parallax Wave")


# ── A granted "return it": the creature it was granted to ────────────────────


@pytest.mark.parametrize("name", ["Feign Death", "Supernatural Stamina"])
def test_granted_dies_return_puts_another_permanent_in(name):
    """ "Target creature gains 'When this creature dies, return it to the
    battlefield'": the granted trigger's ``SelfRef`` is the creature it was
    granted to, a permanent other than the card."""
    assert ("permanent_etb", "you", "put") in _idents(name)


@pytest.mark.parametrize("name", ["Narcomoeba", "Bronzehide Lion"])
def test_a_card_returning_itself_is_no_put(name):
    assert ("permanent_etb", "you", "put") not in _idents(name)


# ── CreateDrawReplacement: the Words cycle's own effect ──────────────────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Words of Worship", ("lifegain_makers", "you", "")),
        ("Words of War", ("direct_damage", "you", "")),
        ("Words of Wilding", ("token_maker", "you", "Bear")),
    ],
)
def test_draw_replacement_effect_is_the_abilitys_effect(name, ident):
    """ "The next time you would draw a card this turn, … instead" (CR 614.1a):
    what replaces the draw is one of the ability's effects."""
    assert ident in _idents(name)


# ── False positives the new shapes brought ───────────────────────────────────


@pytest.mark.parametrize(
    "name", ["Whisperwood Elemental", "Pull from Eternity", "Riftsweeper"]
)
def test_a_face_up_filter_is_no_face_down_payoff(name):
    # ``Not{FaceDown}``: "face-up nontoken creatures", "target face-up exiled card"
    assert "facedown_matters" not in _keys(name)


def test_a_restriction_on_your_own_attacks_is_no_pillowfort():
    # Call for Aid: "You can't attack that player this turn."
    assert "pillowfort" not in _keys("Call for Aid")


def test_phasing_out_both_sides_of_a_block_protects_no_board():
    # Dream Fighter: "this creature and that creature phase out"
    assert "board_protection" not in _keys("Dream Fighter")


@pytest.mark.parametrize("name", ["Delaying Shield", "Force Bubble"])
def test_damage_to_you_replaced_is_a_save(name):
    """ "If damage would be dealt to you, put that many … counters on this
    enchantment instead": a replacement, no prevention (CR 615.1a), that keeps
    the damage off you."""
    assert ("board_protection", "you", "") in _idents(name)


def test_the_blockers_controller_makes_the_token():
    # Basalt Golem: "that creature's controller … create[s] a 0/2 … Wall"
    idents = _idents("Basalt Golem")
    assert ("keyword_bodies", "you", "defender") not in idents
    assert ("artifacts_matter", "you", "token") not in idents


@pytest.mark.retirement_canary
def test_spell_self_counter_misbinding_canary():
    """Emergent Sequence's "That land becomes a 0/0 … Put a +1/+1 counter on it
    for each land you had enter …": phase binds "it" to the sorcery
    (``SelfRef``), so ``has_structural_self_counter_grow`` skips instants and
    sorceries."""
    (rec,) = test_phase_records("Emergent Sequence")
    counters = [n for n in _nodes(rec) if n.get("type") == "PutCounter"]
    assert counters
    assert all(n["target"] == {"type": "SelfRef"} for n in counters), (
        "has_structural_self_counter_grow: RETIRE-READY — phase no longer binds "
        "Emergent Sequence's counters to the spell. Delete the is_spell_card "
        "guard and this canary."
    )
    assert "self_counter_grow" not in _keys("Emergent Sequence")


@pytest.mark.parametrize("name", ["Amnesia", "Persecute", "Cabal Therapy"])
def test_a_revealed_hands_discard_is_that_players(name):
    """ "Target player reveals their hand and discards all …": phase parks the
    discard with its subject cut ("discard all nonland cards"); the seam reads
    the player back through the "and"-joined verb. An opponent's discard, never
    your own outlet (CR 701.9a)."""
    idents = _idents(name)
    assert ("opponent_discard", "opponents", "") in idents
    assert ("discard_outlet", "you", "") not in idents


def test_the_damaged_players_mill_is_not_your_own():
    # Szadek: "If Szadek would deal combat damage to a player, instead … that
    # player mills that many cards" (CR 510.1b).
    idents = _idents("Szadek, Lord of Secrets")
    assert ("mill_makers", "opponents", "") in idents
    assert ("graveyard_makers", "you", "") not in idents


def test_counters_counted_across_your_creatures_are_a_plus_one_payoff():
    # Gleam of Authority: "+1/+1 for each +1/+1 counter on other creatures you
    # control" (a ``CountersOnObjects`` count).
    assert ("plus_one_matters", "you", "") in _idents("Gleam of Authority")


def test_parked_commander_discount_reports_unmodelled():
    from mtg_utils.commander_cost import read_self_discount
    from mtg_utils.testkit import test_card

    # Korvold, Gleeful Glutton: "This spell costs {1} less to cast for each card
    # type among permanents you've sacrificed this turn", parked whole.
    assert read_self_discount(test_card("Korvold, Gleeful Glutton")) == (
        "unmodelled (parked)"
    )


def test_a_land_card_watcher_is_still_a_land_watcher():
    # Centaur Vinecrasher: "Whenever a land card is put into a graveyard from
    # anywhere" — the filter names ``Land`` and ``Card``.
    assert ("land_destruction", "you", "punish") in _idents("Centaur Vinecrasher")


def test_returned_to_your_hand_is_your_permanents_leaving():
    # Azorius Aethermage: "Whenever a permanent is returned to your hand" — the
    # owner typed as an ``Owned`` property (CR 400.3), copied onto the controller.
    assert ("ltb_matters", "you", "") in _idents("Azorius Aethermage")
