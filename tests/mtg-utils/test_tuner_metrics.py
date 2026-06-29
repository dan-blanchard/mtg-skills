"""Tuner Tier-2 metrics: win-condition heuristic detection (grill F6)."""

from mtg_utils._tuner.metrics import _is_wincon_card


def _card(name, oracle, type_line="Instant", power=None):
    rec = {"name": name, "oracle_text": oracle, "type_line": type_line}
    if power is not None:
        rec["power"] = power
    return rec


def test_self_loss_drawback_is_not_a_wincon():
    # A self-loss drawback ("you lose the game") is the opposite of a finisher (CR 104.3e
    # — a player losing is a drawback to its controller). Pact of Negation is a free
    # counter, not a closer; the subjectless r"loses? the game" wrongly counted it.
    pact = _card(
        "Pact of Negation",
        "Counter target spell. At the beginning of your next upkeep, pay {3}{U}{U}. "
        "If you don't, you lose the game.",
    )
    assert _is_wincon_card(pact) is False


def test_platinum_angel_self_protection_is_not_a_wincon():
    angel = _card(
        "Platinum Angel",
        "You can't lose the game and your opponents can't win the game.",
        type_line="Artifact Creature — Angel",
        power="4",
    )
    assert _is_wincon_card(angel) is False


def test_opponent_loses_the_game_is_a_wincon():
    # A genuine alt-win makes an OPPONENT lose (CR 104.3e). Still detected.
    lab = _card(
        "Mortal Combat",
        "At the beginning of your upkeep, if there are twenty or more creature cards "
        "in your graveyard, target opponent loses the game.",
        type_line="Enchantment",
    )
    assert _is_wincon_card(lab) is True


def test_scaling_group_drain_is_a_wincon():
    # Yuriko's printed base drain is the deck's archetypal finisher and was uncounted —
    # the pattern list had the burn analog ("damage to each opponent equal") but no
    # life-loss sibling. Not trigger-multiplication (no commander doubler involved).
    yuriko = _card(
        "Yuriko, the Tiger's Shadow",
        "Whenever a Ninja you control deals combat damage to a player, reveal the top "
        "card of your library and put that card into your hand. Each opponent loses "
        "life equal to that card's mana value.",
        type_line="Legendary Creature — Human Ninja",
        power="1",
    )
    assert _is_wincon_card(yuriko) is True


def test_small_fixed_pinger_is_not_a_group_drain_wincon():
    # A 1-life incidental drip is not a finisher — keep the drain pattern scaling-scoped.
    blood_artist = _card(
        "Blood Artist",
        "Whenever Blood Artist or another creature dies, target player loses 1 life "
        "and you gain 1 life.",
        type_line="Creature — Vampire",
        power="0",
    )
    assert _is_wincon_card(blood_artist) is False
