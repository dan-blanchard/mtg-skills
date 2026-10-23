"""Phase B lane gaps, the card-advantage slice (``lanes/card_advantage.py``).

``creature_recursion`` names its destination; ``activated_draw`` drops one-shot
self-sacrificing draws and reads a granted ``{T}: Draw``; the draw lanes scope
"each opponent draws" and the optional wheels right, and read a symmetric draw
punisher; ``impulse_top_play`` reads granted, split and hideaway impulse. Real
cards only (``mtg_utils.testkit``)."""

from __future__ import annotations

import pytest

from mtg_utils.testkit import test_phase_records, test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _keys(name: str) -> set[str]:
    return {k for k, _s, _su in _idents(name)}


def _subjects(name: str, key: str, scope: str = "you") -> set[str]:
    return {su for k, sc, su in _idents(name) if k == key and sc == scope}


# ── creature_recursion: the destination is the subject ──────────────────────


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # Reanimation: the creature card goes onto the battlefield.
        ("Zombify", {"battlefield"}),
        ("Unburial Rites", {"battlefield"}),
        ("Reanimate", {"battlefield"}),
        ("Animate Dead", {"battlefield"}),
        # A mass reanimation routed through exile (the exiled set comes back);
        # ``mass`` is removal_tutors' whole-graveyard return subject.
        ("Living Death", {"battlefield", "mass"}),
        # An opponent's creature card put onto the battlefield under your control.
        ("Ashen Powder", {"battlefield"}),
        # Recall to hand, and a tuck back on top of the library.
        ("Raise Dead", {"hand"}),
        ("Soul Salvage", {"hand"}),
        ("Gravepurge", {"library"}),
        # A recovered residue keeps its token's destination (graveyard_return).
        ("Dawn Evangel", {"hand"}),
    ],
)
def test_creature_recursion_subject_is_the_destination(name, subjects):
    assert _subjects(name, "creature_recursion") == subjects


def test_opponent_graveyard_creature_under_their_control_is_not_recursion():
    """Immortal Obligation returns an opponent's creature card under THEIR
    control: graveyard hate, not your reanimation."""
    assert "creature_recursion" not in _keys("Immortal Obligation")


# ── activated_draw: a tap-to-draw engine, not a one-shot ────────────────────


@pytest.mark.parametrize(
    "name",
    ["Mind Stone", "Azorius Locket", "Chromatic Sphere", "Lantern of the Lost"],
)
def test_activated_draw_skips_an_activation_that_uses_up_its_source(name):
    """Sacrificing (CR 701.21a) or exiling (CR 701.13a) the source as a cost
    draws once."""
    assert "activated_draw" not in _keys(name)


@pytest.mark.parametrize(
    "name",
    [
        "Jayemdae Tome",
        # A second, repeatable tap-draw keeps it beside the self-sacrifice one.
        "Qiqirn Merchant",
        # A granted "{T}: Draw a card" on the enchanted creature.
        "Hard Cover",
        "Ocular Halo",
    ],
)
def test_activated_draw_fires(name):
    assert ("activated_draw", "you", "") in _idents(name)


# ── draw scopes ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Master of the Feast", "Forced Fruition"])
def test_opponents_drawing_is_scoped_opponents(name):
    assert _subjects(name, "card_draw_engine", "opponents") == {""}
    assert not _subjects(name, "card_draw_engine", "you")


@pytest.mark.parametrize("name", ["Notion Thief", "Palantír of Orthanc"])
def test_your_draw_off_an_opponent_stays_yours(name):
    """A draw replacement's Controller draw is yours (Notion Thief); a draw an
    opponent merely chooses to give you is yours (Palantír of Orthanc)."""
    assert ("card_draw_engine", "you", "") in _idents(name)
    assert not _subjects(name, "card_draw_engine", "opponents")


@pytest.mark.parametrize(
    "name", ["Snort", "Ruin Grinder", "Will of the Jeskai", "Wheel of Fortune"]
)
def test_optional_wheel_draws_for_each_player(name):
    idents = _idents(name)
    assert ("card_draw_engine", "each", "") in idents
    assert ("card_draw_engine", "you", "") not in idents
    assert ("group_hug_draw", "each", "") in idents


@pytest.mark.parametrize("name", ["Phyrexian Tyranny", "Spiteful Visions"])
def test_symmetric_draw_punisher_is_opponent_draw_matters(name):
    assert ("opponent_draw_matters", "opponents", "") in _idents(name)


@pytest.mark.retirement_canary
def test_optional_wheel_draw_scope_canary():
    """Retirement canary for ``crosswalk.optional_clause_actor``: phase v0.104.0
    writes Snort's "Each player may discard their hand and draw five cards" with
    ``player_scope: All`` on the optional discard only; the draw sub-ability
    carries none. Once phase writes it there, the owner read answers directly and
    the read can retire."""
    (ability,) = test_phase_records("Snort")[0]["abilities"]
    assert ability["optional"] is True
    assert ability["player_scope"] == {"type": "All"}
    draw = ability["sub_ability"]
    assert draw["effect"]["type"] == "Draw"
    assert draw.get("player_scope") is None, (
        "optional_clause_actor: RETIRE-READY — phase now scopes the optional "
        "wheel's draw itself"
    )


# ── impulse_top_play ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # A granted exile-the-top-and-play trigger.
        "Capricious Sliver",
        # The exile and the permission in two units.
        "Share the Spoils",
        "Uba Mask",
        # Hideaway (CR 702.75a) plus an ability that plays the exiled card.
        "Shelldock Isle",
        "Fight Rigging",
    ],
)
def test_impulse_top_play_reads_granted_split_and_hideaway(name):
    assert ("impulse_top_play", "you", "") in _idents(name)


@pytest.mark.parametrize(
    "name",
    [
        # Hideaway that only returns the card to your hand.
        "Watcher for Tomorrow",
        # A face-down card hidden from an opponent's library is theft.
        "Gonti, Lord of Luxury",
        "Thief of Sanity",
        # The top of target opponent's library.
        "Maralen, Fae Ascendant",
    ],
)
def test_impulse_top_play_excludes_theft_and_bare_hideaway(name):
    assert "impulse_top_play" not in _keys(name)
