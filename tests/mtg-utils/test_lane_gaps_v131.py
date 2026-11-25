"""Lane decisions taken after the phase v0.131.0 pin bump (2026-11-24): reads
that changed which cards carry a signal, each by a rule of the lane's own."""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import iter_static_defs, pt_mod_signs
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _static_defs(name: str) -> list:
    return [
        sdef
        for tree in trees_for(test_card(name))
        for unit in tree.units
        for sdef in iter_static_defs(unit.node)
    ]


# ── A counted pump is a pump, whichever way phase writes it ─────────────────────


@pytest.mark.parametrize(
    ("name", "targeted"),
    [
        # "gets +1/+0 for each card you've drawn this turn"
        ("Fists of Flame", True),
        # "gets +X/+0, where X is its power"
        ("Berserk", True),
        # "creatures you control … get +X/+X … where X is the number of creatures"
        ("Craterhoof Behemoth", False),
    ],
)
def test_a_counted_pump_is_a_pump_maker(name, targeted):
    """A targeted one is a spell's boost of one chosen creature (ADR-0065)."""
    idents = _idents(name)
    assert ("effect_boost", "you", "") in idents
    assert (("boosts_others", "you", "target_spell") in idents) is targeted


@pytest.mark.parametrize(
    "name",
    [
        # begin combat: "+1/+1 for each card type among cards in your graveyard"
        "Ursine Monstrosity",
        # begin combat: "another target creature you control … gets +X/+X"
        "Xenagos, God of Revels",
        # attacks: "creatures you control … get +X/+X"
        "Pathbreaker Ibex",
    ],
)
def test_a_counted_combat_pump_is_a_combat_buff(name):
    assert ("combat_trigger_boost", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # "Whenever ~ attacks or blocks, it gets +X/+X until end of turn" (the
        # pump itself rewritten from a where-X residue)
        "Freelance Muscle",
        # "Whenever ~ attacks or blocks, other Humans you control get +1/+1"
        "Hamlet Captain",
        # "Whenever ~ attacks, it gets +1/-2 until end of turn": power goes up
        "Cave People",
    ],
)
def test_an_attacks_or_blocks_pump_is_a_combat_buff(name):
    assert ("combat_trigger_boost", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # flanking: "the blocking creature gets -1/-1 until end of turn"
        "Benalish Cavalry",
        # "Whenever ~ attacks or blocks, put a -1/-1 counter on it."
        "Dusk Urchins",
        # "target creature defending player controls gets -2/-0"
        "Fear of Falling",
        # "it gets -1/-1 until end of turn for each creature blocking it beyond
        # the first": a shrink by a count
        "Jungle Wurm",
    ],
)
def test_a_combat_shrink_is_no_combat_buff(name):
    assert "combat_trigger_boost" not in {
        key for key, _scope, _subject in _idents(name)
    }


def test_a_counted_shrink_is_no_raise():
    # Toxrill, the Corrosive: "Creatures you don't control get -1/-1 for each
    # slime counter on them" — a ``Multiply`` by a negative factor.
    assert {pt_mod_signs(d) for d in _static_defs("Toxrill, the Corrosive")} == {
        (-1, -1)
    }
    assert (1, 1) in {pt_mod_signs(d) for d in _static_defs("Craterhoof Behemoth")}


# ── "Those creatures gain X" after a mass effect lands on that group ────────────


@pytest.mark.parametrize(
    ("name", "keyword"),
    [
        # "Put a +1/+1 counter on each creature you control. Those creatures
        # gain vigilance until end of turn."
        ("Ajani Goldmane", "vigilance"),
        # "Untap all creatures you control. They gain hexproof and
        # indestructible until end of turn."
        ("Join Shields", "hexproof"),
        # "Creatures you control get +1/+1 … those creatures gain indestructible"
        ("Break of Day", "indestructible"),
    ],
)
def test_a_grant_to_the_team_a_mass_effect_named_is_a_team_boost_or_grant(
    name, keyword
):
    idents = _idents(name)
    assert ("team_boost_or_grant", "you", "") in idents
    assert ("team_boost_or_grant", "you", keyword) in idents
    assert ("keyword_grant_target", "you", "") not in idents


def test_a_grant_to_part_of_the_team_names_its_keyword_only():
    # Sandstorm Salvager: "Put a +1/+1 counter on each creature token you
    # control. Those creatures gain trample" — your tokens, not the whole team.
    idents = _idents("Sandstorm Salvager")
    assert ("team_boost_or_grant", "you", "trample") in idents
    assert ("team_boost_or_grant", "you", "") not in idents


@pytest.mark.parametrize(
    "name",
    [
        # "Gain control of all creatures with power 4 or greater … Untap those
        # creatures. They gain haste": creatures you take, not your team.
        "Mob Rule",
        # "each attacking creature": no controller named.
        "Captain America, Skybound",
    ],
)
def test_a_grant_to_a_group_that_is_not_your_team_is_no_team_boost_or_grant(name):
    assert not {i for i in _idents(name) if i[0] == "team_boost_or_grant"}


def test_those_creatures_after_chosen_targets_stays_a_targeted_grant():
    # Arm the Cathars: three targeted pumps, then "Those creatures gain vigilance".
    idents = _idents("Arm the Cathars")
    assert ("keyword_grant_target", "you", "vigilance") in idents
    assert not {i for i in idents if i[0] == "team_boost_or_grant"}


# ── A harm in a mode you need not choose is no drawback ─────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # enters: "Choose one — • Exile … You gain 2 life. • Investigate. You
        # lose 2 life."
        "Commander Raffi Musiker",
        # dies: "Choose one — • Each opponent discards two cards and loses 2
        # life. • Put target non-Dragon creature card … You lose 2 life."
        "Junji, the Midnight Sky",
    ],
)
def test_a_harm_in_one_mode_of_several_is_no_drawback(name):
    assert not {i for i in _idents(name) if i[0] == "self_drawback"}


def test_modes_that_each_come_up_in_turn_keep_the_drawback():
    # Demonic Pact: "choose one that hasn't been chosen — … • You lose the game."
    assert ("self_drawback", "you", "harm") in _idents("Demonic Pact")


@pytest.mark.parametrize(
    "name",
    [
        # "each player Angel of Destiny attacked this turn loses the game": a
        # target-less ``LoseTheGame`` under ``player_scope: OpponentAttacked``.
        "Angel of Destiny",
        # "each opponent who doesn't control an Elf loses 1 life": a
        # ``ControlsCount`` scope whose ``relation`` is the opponents.
        "Thornbow Archer",
    ],
)
def test_a_loss_the_ability_scopes_to_opponents_is_no_drawback(name):
    assert not {i for i in _idents(name) if i[0] == "self_drawback"}


# ── A cast copy of a named card can be a permanent ──────────────────────────────


def test_a_cast_copy_of_a_named_card_is_a_battlefield_put():
    # Garth One-Eye: "Create a copy of the card with the chosen name. You may
    # cast the copy" — Shivan Dragon and Black Lotus among the names.
    assert ("permanent_etb", "you", "put") in _idents("Garth One-Eye")


# ── A zone list on the card's filter names its zones ────────────────────────────


@pytest.mark.parametrize("name", ["Huskburster Swarm", "Sailors' Bane"])
def test_a_count_over_exile_and_graveyard_counts_exile(name):
    # "costs {1} less to cast for each creature card you own in exile and in
    # your graveyard": an ``InAnyZone`` of the two zones.
    assert ("exile_matters", "you", "") in _idents(name)


def test_a_put_from_hand_or_the_command_zone_is_a_put_from_hand():
    # Next of Kin: "When enchanted creature dies, you may put a creature card
    # you own with lesser mana value from your hand or from the command zone
    # onto the battlefield."
    idents = _idents("Next of Kin")
    assert ("cheat_into_play", "you", "Creature") in idents
    assert ("death_matters", "any", "") in idents


def test_a_put_from_hand_or_graveyard_is_both_a_cheat_and_a_reanimation():
    # Swift Warkite: "you may put a creature card with mana value 3 or less
    # from your hand or graveyard onto the battlefield."
    idents = _idents("Swift Warkite")
    assert ("cheat_into_play", "you", "Creature") in idents
    assert ("creature_recursion", "you", "battlefield") in idents


# ── Shapes phase v0.131.0 wrote anew, each read where the old one was ───────────


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        # "Each other creature you control gets +1/+1": ``DistinctFrom`` the
        # ability's target, the rest of the team.
        ("Phalanx Tactics", ("team_boost_or_grant", "you", "pump")),
        # "exile target card from defending player's graveyard": the owner typed.
        ("Graven Abomination", ("opponent_exile_makers", "opponents", "")),
        ("Rysorian Badger", ("opponent_exile_makers", "opponents", "")),
        # "untap all Forests put onto the battlefield this way. They become 3/3
        # green creatures": a ``TrackedSet`` after a mass effect.
        ("Hunting Wilds", ("land_creatures_matter", "you", "animator")),
        ("Hunting Wilds", ("land_protection", "you", "")),
        # an exile over the battlefield and the graveyards alike
        ("Shadows' Verdict", ("mass_removal", "you", "")),
        # "Any opponent may … If a player does, ~ deals damage to that player"
        ("Sin Prodder", ("lifeloss_makers", "opponents", "")),
        # "If you control a Forest, rather than pay this spell's mana cost, …"
        ("Invigorate", ("subtype_ref", "you", "Forest")),
        ("Reverent Silence", ("subtype_ref", "you", "Forest")),
        # "draw a card for each kind of counter on it"
        ("Blitzball Stadium", ("draw_for_each", "you", "")),
        # "Target opponent sacrifices a creature with the greatest power …"
        ("Will of the Abzan", ("edict_makers", "opponents", "target")),
    ],
)
def test_a_new_shape_is_read_where_the_old_one_was(name, ident):
    assert ident in _idents(name)


def test_an_exile_of_graveyard_cards_alone_is_no_sweep():
    # Bojuka Bog: "exile target player's graveyard" — no battlefield arm.
    assert "mass_removal" not in {i[0] for i in _idents("Bojuka Bog")}


def test_a_player_who_cannot_attack_this_turn_is_a_pillowfort():
    # Peace in Our Time: "that player may draw a card. If they do, they can't
    # attack this turn" — a ``CantAttack`` on the trigger's player.
    assert ("pillowfort", "you", "") in _idents("Peace in Our Time")


def test_a_play_permission_is_an_enters_payload():
    # Ensign Pavel Chekov: "When ~ enters, each opponent exiles … You may play
    # the chosen cards for as long as they remain exiled."
    assert ("self_etb_payload", "you", "") in _idents("Ensign Pavel Chekov")
