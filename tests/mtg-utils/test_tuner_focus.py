"""Focus metric: lands and Spine-role avenues are not themes; near-dupes collapse."""

from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import Signal
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.metrics import focus


def _cc(name, bucket, served, roles=()):
    return CardClass(
        name=name,
        bucket=bucket,
        roles=tuple(roles),
        served=tuple(served),
        dual_purpose=(bucket == "spine" and bool(served)),
        cmc=2.0,
        record={"name": name},
    )


def test_lands_and_spine_avenues_are_not_themes():
    ramp_sig = Signal(
        key="ramp_matters",
        scope="you",
        subject="",
        text="",
        source="Sol Ring",
        confidence="high",
    )
    ramp_label = spec_for(ramp_sig).label  # "Ramp / big mana"
    classes = [
        _cc("Command Tower", "land", [ramp_label]),
        _cc("Hallowed Fountain", "land", [ramp_label]),
        _cc("Sol Ring", "spine", [ramp_label], roles=["ramp"]),
        _cc("Token Maker A", "engine", ["Tokens"]),
        _cc("Token Maker B", "engine", ["Tokens"]),
        _cc("Token Maker C", "engine", ["Tokens"]),
    ]
    # deck_size 10 → viability floor 2, so 3 token-makers clears it.
    fr = focus(classes, deck_size=10, deck_signals=[ramp_sig])
    labels = {a["label"] for a in fr["viable_avenues"]}
    assert ramp_label not in labels  # a Spine-role avenue is scaffolding, not a theme
    assert "Tokens" in labels
    # No land ever appears as theme support.
    for a in fr["viable_avenues"]:
        assert "Command Tower" not in a["cards"]
        assert "Hallowed Fountain" not in a["cards"]


def test_near_duplicate_avenues_collapse_to_one():
    # The same cards back both labels (one theme described two ways) → one survives.
    classes = [
        _cc(f"Spell {i}", "engine", ["Spellslinger", "Magecraft / spellslinger"])
        for i in range(4)
    ]
    fr = focus(classes, deck_size=10)
    assert len(fr["viable_avenues"]) == 1
