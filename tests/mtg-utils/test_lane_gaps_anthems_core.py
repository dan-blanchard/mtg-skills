"""Phase D lane gaps, anthems_core slice: ``anthem_static`` reads symmetric
colour / chosen-type groups, "+1/+1 for each" anthems and emblem anthems (CR
613.4c, CR 114.4); ``win_lose_game`` no longer fires on a loss aimed at you
(CR 104.2b / 104.3e); ``type_changers`` reads a single target made the creature
type of your choice (CR 613.1d), scoped "any"; ``draw_matters`` reads granted
draw triggers, your draw-step extra draws (CR 504.1) and drops the punishers.

Every card is a real one, read through the production ``extract_signals``
(``mtg_utils.testkit.test_signals``, ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _of(name: str, key: str) -> set[tuple[str, str]]:
    return {(scope, subj) for k, scope, subj in _idents(name) if k == key}


# ── anthem_static ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Bad Moon", ""),  # symmetric colour anthem: "Black creatures"
        ("Gauntlet of Might", ""),
        ("Hall of Triumph", ""),  # "creatures you control of the chosen color"
        ("Brass Herald", ""),  # "Creatures of the chosen type"
        ("Lord of Atlantis", "Merfolk"),  # a creature type alone, no core type
        ("Armament Master", "Kor"),  # "+2/+2 for each Equipment attached"
        ("Commander's Insignia", ""),  # "+1/+1 for each time you've cast"
        ("Elspeth, Sun's Champion", ""),  # emblem, CR 114.4
        ("Gideon, Ally of Zendikar", ""),  # emblem
        ("Glorious Anthem", ""),
    ],
)
def test_anthem_static_reads_the_group(name, subject):
    assert ("you", subject) in _of(name, "anthem_static")


@pytest.mark.parametrize(
    "name",
    [
        "Coat of Arms",  # a bare symmetric "each creature" global stays out
        "Overrun",  # until end of turn: a pump (CR 611.2a)
        "Nissa, Ascended Animist",  # her ultimate lasts until end of turn
        "Sorin, Solemn Visitor",  # "until your next turn"
        "Virulent Plague",  # -2/-2: a debuff
    ],
)
def test_anthem_static_skips_pumps_and_globals(name):
    assert not _of(name, "anthem_static")


# ── win_lose_game ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Thassa's Oracle",  # you win
        "Vorpal Sword",  # a granted "that player loses the game"
        "Vraska, Golgari Queen",  # an emblem's
        "Angel of Destiny",  # "each player … attacked this turn loses"
        "Nicol Bolas, Dragon-God",  # "each opponent who doesn't control …"
        "Hidetsugu Consumes All // Vessel of the All-Consuming",  # recovered
    ],
)
def test_win_lose_game_reads_wins_and_opponent_losses(name):
    assert _of(name, "win_lose_game") == {("any", "")}


@pytest.mark.parametrize(
    "name",
    ["Pact of Negation", "Final Fortune", "Lich's Mastery", "Transcendence"],
)
def test_win_lose_game_skips_a_loss_aimed_at_you(name):
    assert not _of(name, "win_lose_game")


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("Angel of Destiny", (0, "triggers", 1, "execute", "effect")),
        ("Nicol Bolas, Dragon-God", (0, "abilities", 3, "effect")),
    ],
)
def test_lose_the_game_player_dropped_canary(name, path):
    """Retirement canary for ``_win_lose_game``'s untargeted-loss arm: phase
    v0.104.0 drops the losing player of "each player Angel of Destiny attacked
    this turn loses the game" and "each opponent who doesn't control a
    legendary creature or planeswalker loses the game"."""
    node: object = test_phase_records(name)
    for step in path:
        node = node[step]  # type: ignore[index]
    assert isinstance(node, dict)
    assert node.get("type") == "LoseTheGame"
    assert "target" not in node, (
        f"{name}: RETIRE-READY — phase now names the losing player. Drop the "
        "MISSING-target arm of core_makers._win_lose_game (and this canary) "
        "once both cards still fire through ends_the_game."
    )


# ── type_changers: a single target, the type of your choice ─────────────────


@pytest.mark.parametrize(
    ("name", "subject"),
    [
        ("Imagecrafter", ""),  # "becomes that type until end of turn"
        ("Unnatural Selection", ""),
        ("Trickery Charm", ""),  # the mode "the creature type of your choice"
        ("Amoeboid Changeling", "all"),  # "gains all creature types"
    ],
)
def test_single_target_type_change_is_scoped_any(name, subject):
    assert ("any", subject) in _of(name, "type_changers")


def test_single_target_type_change_never_reaches_the_tribal_scopes():
    # ADR-0040: the tribal serves read scopes you / each only.
    assert {scope for scope, _ in _of("Imagecrafter", "type_changers")} == {"any"}
    assert ("you", "") in _of("Xenograft", "type_changers")


def test_single_target_fixed_subtype_is_a_polymorph():
    assert not _of("Turn to Frog", "type_changers")


# ── draw_matters ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "The Locust God",
        "Diviner's Wand",  # granted to the equipped creature
        "Teferi, Hero of Dominaria",  # an emblem's
    ],
)
def test_draw_matters_reads_draw_payoffs(name):
    assert ("you", "") in _of(name, "draw_matters")


@pytest.mark.parametrize(
    "name",
    [
        "Grafted Skullcap",
        "Sylvan Library",
        "Lord Skitter's Blessing",  # the recovered "you draw an additional card"
        "Sarkhan, the Dragonspeaker",  # an emblem's draw-step trigger
    ],
)
def test_draw_matters_reads_your_draw_step_extra_draws(name):
    assert ("you", "draw_step") in _of(name, "draw_matters")


@pytest.mark.parametrize(
    "name",
    [
        "Phyrexian Tyranny",  # hurts whoever draws
        "Spiteful Visions",
        "Curse of Fool's Wisdom",  # the enchanted player's draws
        "Ob Nixilis Reignited",  # the emblem goes to an opponent
        "Howling Mine",  # each player's draw step: card_draw_engine|each
    ],
)
def test_draw_matters_skips_punishers_and_other_players_draws(name):
    assert not _of(name, "draw_matters")
