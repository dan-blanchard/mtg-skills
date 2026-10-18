"""The animation lane (``animate_makers``) and the land-type payoff lane
(``land_type_matters``) — ``lanes.animate_land_types`` — and their per-subject
serve specs, proven on real cards from the committed snapshot."""

from __future__ import annotations

import pytest

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis.signal_specs import Serve, serve_from_dict, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_signals


def _subjects(name: str, key: str) -> set[str]:
    return {s.subject for s in test_signals(name) if s.key == key}


def _sig(key: str, subject: str) -> Signal:
    return Signal(key, "you", subject, "", "x", "high")


# ── animate_makers ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # A static over an Or of two typed arms, each with Bello's own mana-value
        # floor (the floor is the card's, not carried on the signal).
        ("Bello, Bard of the Brambles", {"Artifact", "Enchantment"}),
        # An Aura's "enchanted artifact is a creature".
        ("Ensoul Artifact", {"Artifact"}),
        # A symmetric static over every noncreature artifact.
        ("March of the Machines", {"Artifact"}),
        ("Opalescence", {"Enchantment"}),
        # A targeted one-shot, read through the threaded target.
        ("Tezzeret, Agent of Bolas", {"Artifact"}),
        ("Karn, Silver Golem", {"Artifact"}),
        # "becomes a green Elk creature" sets the card types (artifact arm).
        ("Oko, Thief of Crowns", {"Artifact"}),
        ("Sarkhan the Masterless", {"Planeswalker"}),
    ],
)
def test_animate_makers_names_the_animated_type(name, subjects):
    assert _subjects(name, signal_keys.ANIMATE_MAKERS) == subjects


@pytest.mark.parametrize(
    "name",
    [
        # Counts artifacts, animates nothing.
        "Kappa Cannoneer",
        # Makes a permanent an artifact, never a creature.
        "Liquimetal Coating",
        # A manland animates only itself.
        "Mutavault",
        # Turns a creature into an artifact creature: it already was one.
        "Darksteel Mutation",
    ],
)
def test_animate_makers_stays_out(name):
    assert not _subjects(name, signal_keys.ANIMATE_MAKERS)


def test_animation_subject_specs_share_one_label():
    """Every animated type's spec and the subject-less one read as one avenue."""
    labels = {
        spec_for(_sig(signal_keys.ANIMATE_MAKERS, subject)).label
        for subject in ("", "Artifact", "Enchantment", "Planeswalker", "Battle")
    }
    assert labels == {"Animation"}


def test_animation_serves_noncreature_permanents_of_its_type_and_its_doers():
    """The Artifact avenue's feeders are noncreature artifacts (Sol Ring); an
    artifact creature is already a creature and feeds it only as an animator
    (Karn, Silver Golem), never by type (Solemn Simulacrum). An enchantment
    feeds the Enchantment avenue, not the Artifact one."""
    artifact = spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Artifact")).serve
    enchantment = spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Enchantment")).serve
    assert artifact.matches(test_card("Sol Ring"))
    assert artifact.matches(test_card("Karn, Silver Golem"))
    assert not artifact.matches(test_card("Solemn Simulacrum"))
    assert enchantment.matches(test_card("Glorious Anthem"))
    assert not artifact.matches(test_card("Glorious Anthem"))
    # An Aura that's also a creature can't enchant anything (CR 303.4d), and
    # every enchantment animator says "non-Aura": an Aura never feeds.
    assert not enchantment.matches(test_card("Ensoul Artifact"))


def test_the_subjectless_animation_spec_is_built_like_the_typed_ones():
    """ "" ("a permanent") dispatches to the same builder: one "Animation" label,
    every animated type as feeders, every animator as a doer."""
    spec = spec_for(_sig(signal_keys.ANIMATE_MAKERS, ""))
    assert spec.label == "Animation"
    assert spec.serve.signal_idents == frozenset({"animate_makers|you|*"})
    assert spec.serve.matches(test_card("Sol Ring"))
    assert spec.serve.matches(test_card("Glorious Anthem"))


def test_not_types_vetoes_only_the_types_arm_and_both_fields_round_trip():
    serve = Serve(
        types=frozenset({"artifact"}),
        not_types=frozenset({"creature"}),
        names=frozenset({"solemn simulacrum"}),
        lands_feed=True,
    )
    assert not Serve(
        types=frozenset({"artifact"}), not_types=frozenset({"creature"})
    ).matches(test_card("Solemn Simulacrum"))
    # The names arm still serves it: not_types restricts the types arm alone.
    assert serve.matches(test_card("Solemn Simulacrum"))
    assert serve_from_dict(serve.as_dict()) == serve


# ── land_type_matters ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # A trigger watching a Desert card put into your graveyard.
        ("Yuma, Proud Protector", {"Desert"}),
        # A distinct-name count in a win condition.
        ("Maze's End", {"Gate"}),
        # A count operand and a condition.
        ("Gatebreaker Ram", {"Gate"}),
        # An enters trigger and a play-from-graveyard permission.
        ("Hazezon, Shaper of Sand", {"Desert"}),
        # A count condition on a ramp spell.
        ("Hour of Promise", {"Desert"}),
    ],
)
def test_land_type_matters_names_the_land_type(name, subjects):
    assert _subjects(name, signal_keys.LAND_TYPE_MATTERS) == subjects


@pytest.mark.parametrize(
    "name",
    [
        # Landfall names no land type.
        "Rampaging Baloths",
        # A basic land type (CR 305.6) is a colour's mana base, not a package.
        "Kird Ape",
        # A fetch searches for a land; it pays nothing off.
        "Windswept Heath",
    ],
)
def test_land_type_matters_stays_out(name):
    assert not _subjects(name, signal_keys.LAND_TYPE_MATTERS)


def test_land_type_spec_serves_the_lands_and_the_payoffs():
    spec = spec_for(_sig(signal_keys.LAND_TYPE_MATTERS, "Desert"))
    assert spec.label == "Deserts"
    # Its lands are its feeders: focus counts them toward its depth.
    assert spec.serve.lands_feed
    assert not spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Artifact")).serve.lands_feed
    assert spec.search == {"card_type": "desert"}
    assert spec.serve.matches(test_card("Ramunap Ruins"))
    assert spec.serve.matches(test_card("Yuma, Proud Protector"))
    assert not spec.serve.matches(test_card("Forest"))
    gates = spec_for(_sig(signal_keys.LAND_TYPE_MATTERS, "Gate")).serve
    assert gates.matches(test_card("Azorius Guildgate"))
    assert not gates.matches(test_card("Ramunap Ruins"))
