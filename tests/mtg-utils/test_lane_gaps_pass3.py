"""The lane recall gaps the 2026-10-31 third pass closed (``docs/plans/backlog.md``:
"Lane gaps still open", Pass D's lane follow-ups and "Our reads still missing a
v0.118.0 shape"). Real cards only (ADR-0056): each closed gap, and the near miss
that stays out."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keyed(name: str, *keys: str) -> set[tuple[str, str, str]]:
    return {i for i in _idents(name) if i[0] in keys}


# ── edict_makers: a forced sacrifice (CR 701.21a) ────────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # "Choose two target creatures controlled by the same player. That
        # player sacrifices one of them of their choice."
        ("Incriminate", "opponents"),
        # "For each creature, its controller sacrifices it unless they pay X life."
        ("Killing Wave", "each"),
        # "When you cast this spell, each player sacrifices X creatures." (parked)
        ("Gluttonous Hellkite", "each"),
        # a granted "Whenever this creature deals combat damage to a player, that
        # player sacrifices a creature of their choice" (read like a printed one)
        ("Demon of Wailing Agonies", "each"),
        # the secretly chosen creature's sacrifice (a ledgered bridge)
        ("Malik, Grim Manipulator", "opponents"),
    ],
)
def test_a_forced_sacrifice_is_an_edict(name, scope):
    assert ("edict_makers", scope, "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # "that player chooses up to two creatures they control, then sacrifices
        # the rest": the kept set, keep_n_wrath's (Incriminate's shape otherwise)
        "Archfiend of Depravity",
        # "Each player chooses up to two creatures they control, then sacrifices
        # the rest"
        "Covetous Elegy",
        # you choose a permanent of each type for each player, the rest go
        "Tragic Arrogance",
    ],
)
def test_a_keep_n_wrath_stays_off_the_edict_page(name):
    assert not _keyed(name, "edict_makers")
    assert _keyed(name, "keep_n_wrath")


def test_an_emblems_edict_is_no_edict():
    """Sorin, Solemn Visitor's -6 emblem: "At the beginning of each opponent's
    upkeep, that player sacrifices a creature of their choice." An ultimate's
    emblem fills no slot the card plays in (the tutor read's footing)."""
    assert not _keyed("Sorin, Solemn Visitor", "edict_makers")


# ── card_draw_engine / opponent_draw_matters ─────────────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # Equipped creature has "At the beginning of your upkeep, draw a card."
        ("Avarice Amulet", "you"),
        # Enchanted creature has "Whenever this creature deals combat damage to a
        # player, draw a card."
        ("Combat Research", "you"),
        # "target attacking creature connives X, where X is the number of
        # attacking creatures" (CR 701.50d: draws X cards)
        ("Raffine, Scheming Seer", "you"),
        # aftermath halves phase emits no record for (ledgered)
        ("Spring // Mind", "you"),
        ("Leave // Chance", "you"),
        ("Commit // Memory", "each"),
    ],
)
def test_a_granted_trigger_connive_x_or_aftermath_draw_is_a_draw_engine(name, scope):
    assert ("card_draw_engine", scope, "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # a connive of one each trigger is a loot, not bulk draw
        "Ledger Shredder",
        # Ral's draw two rides only the -8 emblem: an ultimate's emblem fills no
        # draw slot (the tutor read's footing)
        "Ral, Izzet Viceroy",
    ],
)
def test_a_single_connive_or_an_emblem_draw_is_no_draw_engine(name):
    assert not _keyed(name, "card_draw_engine")


@pytest.mark.parametrize(
    "name",
    [
        # "Whenever enchanted player draws a card, they lose 2 life and you gain
        # 2 life"
        "Curse of Fool's Wisdom",
        # Enchant opponent / "Whenever enchanted opponent draws a card, you may
        # draw a card"
        "Psychic Possession",
    ],
)
def test_an_enchanted_opponents_draw_watcher_is_an_opponent_draw_payoff(name):
    assert ("opponent_draw_matters", "opponents", "") in _idents(name)


# ── proliferate (CR 701.34a) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # "Whenever you proliferate, each opponent loses 2 life and you gain 2"
        "Scheming Aspirant",
        # "Whenever you proliferate, choose one — …"
        "Venser, Corpse Puppet",
        # "When you proliferate, return this card from your graveyard to your hand"
        "Voidwing Hybrid",
    ],
)
def test_a_whenever_you_proliferate_trigger_is_a_proliferate_payoff(name):
    assert ("proliferate_matters", "you", "") in _idents(name)
    assert not _keyed(name, "proliferate_makers")


def test_a_granted_proliferate_is_a_proliferate_maker():
    """Ichormoon Gauntlet: "Planeswalkers you control have '[0]: Proliferate'"."""
    assert ("proliferate_makers", "you", "") in _idents("Ichormoon Gauntlet")


# ── type_matters: a legendary token the card doesn't make ───────────────────


@pytest.mark.parametrize("name", ["Eye of Vecna", "Hand of Vecna"])
def test_a_combo_pieces_related_legendary_token_is_no_tribe(name):
    """The bulk relates Vecna (a Zombie God token Book of Vile Darkness makes)
    to Eye and Hand of Vecna too; neither makes it, so neither sits on the
    Zombie page."""
    tribes = {subject for _key, _scope, subject in _keyed(name, "type_matters")}
    assert not tribes & {"Zombie", "God"}


@pytest.mark.parametrize("name", ["Simian Sling", "Tormentor's Helm"])
def test_a_parked_damage_to_defending_player_is_life_loss(name):
    """Its "it deals 1 damage to defending player" when it becomes blocked parks
    as ``blocked_attacker_damage_source``; damage to a player is life loss (CR
    120.3a)."""
    assert ("lifeloss_makers", "opponents", "") in _idents(name)


def test_a_parked_damage_to_the_creatures_blocking_it_is_no_sweep():
    """Trailblazer's Torch's "it deals 2 damage to each creature blocking it"
    hits only the blockers: no board wipe."""
    assert not _keyed("Trailblazer's Torch", "mass_removal", "lifeloss_makers")


def test_a_token_copy_of_itself_keeps_its_tribe():
    """Council of Reeds makes "a token that's a copy of Council of Reeds"."""
    assert ("type_matters", "you", "Scientist") in _idents("Council of Reeds")


# ── self_etb_payload: a boon ────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Underbridge Warlock", "Reflective Rimekin"])
def test_a_boon_on_entering_is_an_enters_payload(name):
    """Its enters trigger gives you a one-time boon: the value each entry
    re-delivers."""
    assert ("self_etb_payload", "you", "") in _idents(name)


# ── debuff_makers: a counter on the creature attacking you ──────────────────


def test_a_minus_counter_on_a_creature_attacking_you_is_a_debuff():
    """Tasha, Unholy Archmage's "+1: Until your next turn, whenever a creature
    attacks you or Tasha, put a -1/-1 counter on that creature": the attacker is
    an opponent's (CR 508.1a)."""
    assert ("debuff_makers", "any", "") in _idents("Tasha, Unholy Archmage")


# ── graveyard_matters: a pick from each graveyard ───────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        # "Then you may exile a creature or planeswalker card from each graveyard."
        ("King Narfi's Betrayal", "any"),
        # "For each player, choose a creature card in that player's graveyard."
        ("Ghouls' Night Out", "any"),
        # "exile a card at random from each opponent's graveyard"
        ("Kefka, Dancing Mad", "opponents"),
    ],
)
def test_a_pick_from_each_graveyard_reaches_the_graveyards_it_names(name, scope):
    assert ("graveyard_matters", scope, "") in _idents(name)


# ── recovery marks on parked clauses ────────────────────────────────────────


def test_a_player_a_draw_count_names_is_no_drawer():
    """Biomantic Mastery: "draw a card for each creature another target player
    controls" — you draw; the target player is the count's."""
    assert not _keyed("Biomantic Mastery", "target_player_draws")
    assert ("card_draw_engine", "you", "") in _idents("Biomantic Mastery")


def test_the_attacking_players_loss_is_an_opponents():
    """Souls of the Faultless: "you gain that much life and attacking player
    loses that much life" — a defender, so the attacking player is an opponent."""
    assert _keyed("Souls of the Faultless", "lifeloss_makers") == {
        ("lifeloss_makers", "opponents", "")
    }


def test_choosing_an_opponent_leaves_your_own_mill_yours():
    """Ursine Monstrosity: "mill a card and choose an opponent at random"."""
    idents = _idents("Ursine Monstrosity")
    assert ("mill_makers", "opponents", "") not in idents
    assert ("graveyard_makers", "you", "") in idents


def test_a_parked_trigger_condition_is_no_instruction():
    """Val, Marooned Surveyor: "Whenever you discover, investigate, scry,
    surveil, or seek one or more cards, …" — the parked "investigate, …" is the
    trigger's condition, so Val makes no Clue."""
    assert not _keyed("Val, Marooned Surveyor", "clue_makers")


def test_an_instruction_list_after_a_trigger_head_still_recovers():
    """Urza's Construction Drone's "When ~ enters, conjure cards named …, and
    Urza's Tower into your library, then shuffle" is an instruction."""
    assert ("self_etb_payload", "you", "") in _idents("Urza's Construction Drone")


@pytest.mark.parametrize(
    ("name", "yours"),
    [
        # "… then an opponent creates two Treasure tokens and they scry 2"
        ("Ingenious Mastery", False),
        # "you and each opponent who voted for a choice you voted for may scry 2"
        ("Model of Unity", True),
    ],
)
def test_another_players_scry_curates_nothing_of_yours(name, yours):
    assert (("topdeck_selection", "you", "scry") in _idents(name)) is yours
