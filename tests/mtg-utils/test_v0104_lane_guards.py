"""Pins for the lane reads phase v0.104.0's newer parse
exposed (ADR-0056: every card read by name from the committed snapshot).

Each pin names the card, the key it must NOT carry (or the scope it must
carry), and the v0.104.0 shape the guard reads.
"""

import pytest

from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[str]:
    return {f"{s.key}|{s.scope}|{s.subject}" for s in test_signals(name)}


def test_chosen_group_bounce_is_not_mass_bounce():
    # "Return each chosen creature to your hand": a ``BounceAll`` whose owning
    # ability reads ``reads_chosen_group`` — the chosen set, not the board.
    assert not any(
        i.startswith("mass_bounce|") for i in _idents("The Eagles Are Coming!")
    )


def test_saga_self_return_is_not_permanent_recast():
    # Chapter III: "Exile this Saga, then return it to the battlefield" beside
    # a granted cast-from-graveyard permission — a SelfRef return from the
    # battlefield, not a graveyard re-delivery.
    assert not any(
        i.startswith("permanent_recast|") for i in _idents("Urabrask // The Great Work")
    )


def test_each_other_player_loses_is_not_you():
    # "its owner draws that many cards and each other player loses that much
    # life": ``AllExcept{exclude: ParentObjectTargetOwner}`` on the Goat's own
    # dies trigger resolves to ``Others``.
    # "each other player" includes a Two-Headed Giant teammate (CR 102.3), so
    # the lane's symmetric "each" scope — never "you".
    idents = _idents("Oft-Nabbed Goat")
    assert "lifeloss_makers|each|" in idents
    assert "lifeloss_makers|you|" not in idents


# ── lifegain_matters: a self-bleed counts only when it can recur ────────────────
# Phase v0.104.0 types "you lose N life for each …" as a Controller loss, which
# the scaling self-loss arm read on one-shot spells and leave-the-battlefield
# triggers too. Engines only: a repeated loss wants lifegain sustain.


@pytest.mark.parametrize(
    "name",
    [
        "The One Ring",  # upkeep: lose 1 life for each burden counter
        "Demonic Lore",
        "Morinfen Avatar",
        "Netherborn Altar",  # activated
        "Embalmed Brawler",  # whenever it attacks or blocks
        "Dark Confidant",
        "Phyrexian Arena",  # the draw-bleed pin
    ],
)
def test_recurring_self_bleed_opens_lifegain(name):
    assert "lifegain_matters|you|" in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Rain of Daggers",  # a spell: lose 2 life for each creature destroyed
        "Reign of Terror",
        "Stroke of Luck",
        "Revival Experiment",
        "Blex, Vexing Pest // Search for Blex",
        "Krovikan Whispers",  # once, when it's put into a graveyard
        "Phyrexian Etchings",
    ],
)
def test_one_shot_self_bleed_is_not_lifegain(name):
    assert "lifegain_matters|you|" not in _idents(name)


# ── own_target_spell: a real target, on the battlefield ─────────────────────────
# The lane is an instant or sorcery that targets YOUR PERMANENT; a permanent is a
# card or token on the battlefield (CR 110.1).


@pytest.mark.parametrize(
    "name",
    [
        # Graveyard cards: phase v0.104.0 writes "from your graveyard" as
        # ``controller: You`` + ``InZone: Graveyard``.
        "Pull from the Deep",
        "Reconstruct History",
        "Relive the Past",
        "Retrieve",
        "Rise from the Wreck",
        "Shreds of Sanity",
        "Thwart the Grave",
        "Finale of Promise",
        # Untargeted mass pumps: a ``PumpAll`` filter targets nothing.
        "Roar of Jukai",
        "Unnerving Assault",
    ],
)
def test_own_target_spell_needs_a_battlefield_target(name):
    assert "own_target_spell|you|" not in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        "Duelist's Flame",  # targeted pump
        # "put X +1/+1 counters on target creature you control"
        "Yuna's Whistle",
        "Ephemerate",
        "Infuriate",
    ],
)
def test_own_target_spell_keeps_targeted_own_permanents(name):
    assert "own_target_spell|you|" in _idents(name)


# ── Recovery-arm near misses ───────────────────────────────────────────────────
# Phase v0.104.0 parks these clauses whole; the recovery stage reads their verb.
# Each pair: the clause that must NOT earn the key, beside one that must.


@pytest.mark.parametrize(
    ("name", "ident", "fires"),
    [
        # "put a +1/+1 counter on target creature of defending player's choice":
        # the opponent aims it, so it is no combat buff of yours.
        ("Erithizon", "combat_buff_engine|you|", False),
        ("Cait, Cage Brawler", "combat_buff_engine|you|", True),
        # Power-scaled damage to a PLAYER is not a creature ping.
        ("Consuming Ferocity", "creature_ping|you|", False),
        ("Consuming Ferocity", "direct_damage|you|", True),
        ("Iron Mastiff", "creature_ping|you|", False),
        ("Iron Mastiff", "damage_equal_power|you|", True),
        ("Combo Attack", "creature_ping|you|", True),
        # "adapts as though it had no +1/+1 counters": places no counter.
        ("Biomancer's Familiar", "plus_one_makers|you|", False),
        ("Feast on the Fallen", "plus_one_makers|you|", True),
        # A replacement's "instead … you lose the game" is no win/lose plan.
        ("Enduring Angel // Angelic Enforcer", "win_lose_game|any|", False),
        ("Pact of Negation", "win_lose_game|any|", True),
        # A replacement's "exile it instead" is no ETB value to copy.
        ("Gut, Fanatical Priestess", "wants_cloning|you|", False),
        ("Uldaros Theorix", "wants_cloning|you|", True),
    ],
)
def test_recovered_verb_near_misses(name, ident, fires):
    assert (ident in _idents(name)) is fires


@pytest.mark.parametrize(
    ("name", "fires"),
    [
        # "Create a copy of the card with the chosen name": a new card from a
        # fixed list, not a copy of a permanent in play.
        ("Garth One-Eye", False),
        # "create a token that's a copy of that creature": a permanent in play.
        ("Hate Mirage", True),
    ],
)
def test_token_copy_needs_an_object_in_play(name, fires):
    assert ("token_copy_makers|you|" in _idents(name)) is fires


# ── Recovered clauses read through the seam's marks (ADR-0038) ────────────────
# Phase v0.104.0 parks these clauses as Unimplemented residues; the recovery
# stage decorates each node with its reading of the clause and the lanes test
# that reading.


@pytest.mark.parametrize(
    ("name", "ident"),
    [
        ("Old Man Willow", "sacrifice_outlets|you|"),  # imperative sacrifice
        ("Curator's Ward", "card_draw_engine|you|"),  # draw two cards (MANY)
        ("Aurora Champion", "tapper_engine|any|"),  # tap target creature
        ("Krond the Dawn-Clad", "exile_removal|you|"),  # exile target permanent
        ("Syrix, Carrier of the Flame", "removal|you|"),  # damage to any target
        ("Syrix, Carrier of the Flame", "damage_equal_power|you|"),
        ("Psychic Pickpocket", "bounce_tempo|you|"),  # target nonland permanent
        ("Shatterskull Charger", "bounce_tempo|you|"),  # return it (itself)
        ("Command the Stage", "self_recurring|you|"),  # return this card
        ("Tom, Bert, and William", "dies_recursion|you|"),  # return them
        ("Dawn Evangel", "creature_recursion|you|"),
        ("Flowstone Sculpture", "self_pump|you|"),  # +1/+1 counter on ~
        ("Darigaaz Reincarnated", "named_counter_misc|you|"),  # egg counter
        (
            "Shaile, Dean of Radiance // Embrose, Dean of Shadow",
            "counter_distribute|you|",
        ),
        ("Underbridge Warlock", "graveyard_makers|you|"),  # you mill
    ],
)
def test_recovered_clause_reads_the_seams_marks(name, ident):
    assert ident in _idents(name)


@pytest.mark.parametrize(
    ("name", "absent"),
    [
        # "deals damage equal to its power to its controller": a player recipient.
        ("Consuming Ferocity", "creature_ping|"),
        # Erithizon's counter goes on a creature of the defending player's choice.
        ("Erithizon", "combat_buff_engine|"),
        # "You may cast this card from your graveyard or from exile": the card's
        # own cast (SELF), not a pile of cards in exile.
        ("Squee, the Immortal", "exile_matters|"),
    ],
)
def test_recovered_clause_marks_keep_the_typed_vetoes(name, absent):
    assert not any(i.startswith(absent) for i in _idents(name))


def test_reanimation_from_an_opponents_graveyard_fills_no_graveyard_of_yours():
    # "the top creature card of defending player's graveyard": the typed Ashen
    # Powder (an opponent's graveyard) fires no graveyard_makers either.
    assert not any(i.startswith("graveyard_makers|") for i in _idents("Bone Dancer"))
    assert not any(i.startswith("graveyard_makers|") for i in _idents("Ashen Powder"))
    # "all creature cards in your opponents' graveyards" (THEIRS).
    assert not any(
        i.startswith("graveyard_makers|") for i in _idents("Supper for Spiders")
    )
    # Geth's Summons: the typed "from your graveyard" half fires; the corrupted
    # "from that player's graveyard" half (the opponents' side) does not.
    assert {
        i for i in _idents("Geth's Summons") if i.startswith("graveyard_makers|")
    } == {"graveyard_makers|you|"}
