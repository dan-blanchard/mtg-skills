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
        # A static over an Or of two typed arms, each carrying Bello's "mana
        # value 4 or greater" floor on its subject.
        ("Bello, Bard of the Brambles", {"Artifact>=4", "Enchantment>=4"}),
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
        for subject in (
            "",
            "Artifact",
            "Artifact>=4",
            "Enchantment",
            "Planeswalker",
            "Battle",
        )
    }
    assert labels == {"Animation"}


def test_the_subject_spelling_round_trips():
    assert signal_keys.animate_subject("Artifact", 4) == "Artifact>=4"
    assert signal_keys.animate_subject("Artifact", None) == "Artifact"
    assert signal_keys.split_animate_subject("Artifact>=4") == ("Artifact", 4)
    assert signal_keys.split_animate_subject("Enchantment") == ("Enchantment", None)
    assert signal_keys.split_animate_subject("") == ("", None)


@pytest.mark.parametrize("subject", ["Artifact>=x", "Artifact>=", ">=4", "Artifact>=0"])
def test_a_malformed_animation_subject_raises(subject):
    """Only ``animate_subject`` spells a subject, so a malformed floor is a bug."""
    with pytest.raises(ValueError, match="malformed"):
        signal_keys.split_animate_subject(subject)


def test_an_animation_spec_counts_every_floor_of_its_type_as_a_doer():
    """A floor-3 artifact animator's avenue counts Bello (``Artifact>=4``, a
    creature, so a doer only through his ident) and March of the Machines
    (unfloored) among its doers."""
    serve = spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Artifact>=3")).serve
    assert serve.matches(test_card("Bello, Bard of the Brambles"))
    assert serve.matches(test_card("March of the Machines"))


def test_a_floored_animation_serves_only_permanents_at_its_floor():
    """Bello animates noncreature artifacts and enchantments of mana value 4 or
    greater: Gilded Lotus (5) and Doubling Season (5) feed his avenue, Sol Ring
    (1) and Glorious Anthem (3) don't — the floor narrows the types arm only, so
    an unfloored artifact animator (March of the Machines) still serves as a
    doer, and the add search asks for mana value 4 too."""
    artifact = spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Artifact>=4"))
    enchantment = spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Enchantment>=4"))
    assert artifact.serve.types_cmc_min == 4
    assert artifact.search == {"card_type": "artifact", "cmc_min": 4}
    assert artifact.serve.matches(test_card("Gilded Lotus"))
    assert not artifact.serve.matches(test_card("Sol Ring"))
    assert artifact.serve.matches(test_card("March of the Machines"))
    assert enchantment.serve.matches(test_card("Doubling Season"))
    assert not enchantment.serve.matches(test_card("Glorious Anthem"))
    # An unfloored animation feeds on every noncreature artifact.
    assert spec_for(_sig(signal_keys.ANIMATE_MAKERS, "Artifact")).serve.matches(
        test_card("Sol Ring")
    )


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


def test_not_types_vetoes_only_the_types_arm_and_the_new_fields_round_trip():
    serve = Serve(
        types=frozenset({"artifact"}),
        not_types=frozenset({"creature"}),
        names=frozenset({"solemn simulacrum"}),
        types_cmc_min=4,
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


# ── the floor in focus ────────────────────────────────────────────────────────


def _animation_members(animators: tuple[str, ...]) -> set[str]:
    """The Animation avenue's members in a small deck led by ``animators``, served
    the way the tuner classifies a deck (``score_candidate`` over the deck's
    signals, ``focus`` over the classes)."""
    from mtg_utils._analysis.ranking import score_candidate
    from mtg_utils._tuner.classify import CardClass
    from mtg_utils._tuner.metrics import focus

    signals = [s for n in animators for s in test_signals(n)]
    feeders = ("Gilded Lotus", "Doubling Season", "Sol Ring", "Glorious Anthem")
    classes = []
    for name in (*animators, *feeders):
        served = tuple(
            score_candidate(test_card(name), active_signals=signals)["served"]
        )
        bucket = "commander" if name == animators[0] else "engine"
        classes.append(
            CardClass(
                name=name,
                bucket=bucket,
                roles=(),
                served=served,
                dual_purpose=False,
                cmc=2.0,
                record={"name": name},
            )
        )
    held = frozenset(
        (s.key, s.scope, s.subject)
        for s in test_signals(animators[0])
        if s.key == signal_keys.ANIMATE_MAKERS
    )
    fr = focus(classes, deck_size=10, deck_signals=signals, commander_idents=held)
    rows = {a["label"]: a for a in fr["viable_avenues"]}
    return set(rows["Animation"]["cards"])


def test_under_bello_alone_the_animation_lane_is_the_floored_one():
    """Bello animates mana value 4 or greater: Gilded Lotus and Doubling Season
    feed his lane, Sol Ring and Glorious Anthem stay out."""
    members = _animation_members(("Bello, Bard of the Brambles",))
    assert {"Gilded Lotus", "Doubling Season"} <= members
    assert not {"Sol Ring", "Glorious Anthem"} & members


def test_a_floorless_animator_beside_bello_widens_the_one_animation_avenue():
    """Every animation subject shares the "Animation" label, so Bello's floored
    artifacts and March of the Machines' every-artifact read as one avenue whose
    members are the union — the wider set: Sol Ring joins, Glorious Anthem (an
    enchantment under 4, which only Bello's floored arm reaches) stays out."""
    members = _animation_members(
        ("Bello, Bard of the Brambles", "March of the Machines")
    )
    assert {"Gilded Lotus", "Doubling Season", "Sol Ring", "March of the Machines"} <= (
        members
    )
    assert "Glorious Anthem" not in members
