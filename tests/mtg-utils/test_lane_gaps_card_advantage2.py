"""Phase D lane gaps, the card_advantage2 slice (``lanes/card_advantage.py`` and
``crosswalk.own_turn_step_triggers``).

``topdeck_stack`` names where the card it stacks comes from (a subject beside the
bare ident, which the play-from-the-top cross-open also emits) and reads a tutor
to the top; ``topdeck_selection`` names scry and surveil; a trigger at the
beginning of your upkeep / draw step / end step is that step's payoff key
(``upkeep_triggers`` / ``draw_step_triggers`` / ``end_step_triggers``). Real cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_signals

_STEP_TRIGGER_KEYS = {"upkeep_triggers", "draw_step_triggers", "end_step_triggers"}


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _subjects(name: str, key: str) -> set[str]:
    return {su for k, sc, su in _idents(name) if k == key and sc == "you"}


# ── topdeck_stack: the stacked card's origin ─────────────────────────────────


@pytest.mark.parametrize(
    ("name", "origin"),
    [
        ("Reclaim", "graveyard"),
        ("Brainstorm", "hand"),
        # A "put a card from your hand on top" activation cost.
        ("Leashling", "hand"),
        # "Search your library for a card, then shuffle and put that card on top"
        # names its card ``Any``: a tutor to the top stacks.
        ("Vampiric Tutor", "library"),
        # The reveal-then-place dig phase leaves with no put node (the kept mirror).
        ("Diabolic Vision", "library"),
        ("Scroll Rack", "exile"),
        ("Sensei's Divining Top", "battlefield"),
    ],
)
def test_topdeck_stack_names_the_stacked_cards_origin(name, origin):
    assert {"", origin} <= _subjects(name, "topdeck_stack")


def test_play_from_the_top_cross_open_carries_no_origin():
    # Future Sight stacks nothing: signals.py cross-opens the bare ident only.
    assert _subjects("Future Sight", "topdeck_stack") == {""}


# ── topdeck_selection: scry and surveil ──────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "action"), [("Opt", "scry"), ("Dissolve", "scry"), ("Consider", "surveil")]
)
def test_topdeck_selection_names_scry_and_surveil(name, action):
    assert {"", action} <= _subjects(name, "topdeck_selection")


def test_look_at_the_top_selection_names_no_action():
    assert _subjects("Ponder", "topdeck_selection") == {""}


# ── step triggers: the payoffs an extra step repeats ─────────────────────────


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Phyrexian Arena", "upkeep_triggers"),
        ("Sylvan Library", "draw_step_triggers"),
        ("Chimil, the Inner Sun", "end_step_triggers"),
        # "Each end step, each opponent loses …": the scoped player is counted in
        # the amount, not the step's player.
        ("Wound Reflection", "end_step_triggers"),
        # A graveyard trigger that brings the card back is a payoff.
        ("Squee, Goblin Nabob", "upkeep_triggers"),
        # A cost with an upside stays: a token for a life; a counter it builds up.
        ("Bitterblossom", "upkeep_triggers"),
        ("Thallid", "upkeep_triggers"),
        # "Each opponent loses 1 life" is a drain, not a cost.
        ("God-Pharaoh's Statue", "end_step_triggers"),
    ],
)
def test_step_trigger_is_the_extra_step_payoff(name, key):
    assert (key, "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # Each player's step, acting on that player: symmetric, not your payoff.
        "Braids, Cabal Minion",
        "Howling Mine",
        # The chosen player's upkeep.
        "Black Vise",
        # A drawback that only takes the card away.
        "Ball Lightning",
        "Masticore",
        "Blitz Hellion",
        # A drawback that only costs you: damage, life, your lands, the card.
        "Juzám Djinn",
        "Force of Nature",
        "Leviathan",
        "Wild Dogs",
        # A -1/-1 counter on itself.
        "Magmaroth",
        # Cumulative upkeep is its own trigger mode.
        "Mystic Remora",
    ],
)
def test_step_trigger_leaves_out_symmetric_named_and_drawback(name):
    assert not any(k in _STEP_TRIGGER_KEYS for k, _sc, _su in _idents(name))


def test_extra_step_maker_is_not_a_step_trigger():
    idents = _idents("Obeka, Splitter of Seconds")
    assert ("extra_upkeep", "you", "") in idents
    # A payoff is never the maker: Phyrexian Arena repeats, it adds no step.
    assert ("extra_upkeep", "you", "") not in _idents("Phyrexian Arena")


# ── impulse_top_play: a play permission over "a card exiled with ~" ──────────


@pytest.mark.parametrize("name", ["Raphael, Most Attitude", "Kayla's Music Box"])
def test_impulse_reads_a_permission_over_cards_exiled_with_it(name):
    # The exile and the permission are separate abilities; the permission names
    # its cards as ``And[InZone Exile, ExiledBySource]``.
    assert ("impulse_top_play", "you", "") in _idents(name)
