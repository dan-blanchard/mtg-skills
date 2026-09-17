"""The template-role owner (ADR-0051): ``roles.is_ramp`` is ONE answer, read off the
signal path, for every surface that counts or sources ramp.

Real snapshot cards throughout (``mtg_utils.testkit``) — the production
``extract_signals`` path, not hand-built oracle dicts. The text degrade
(``card_classify.ramp_by_text``) keeps its own tests in ``test_card_classify.py``.
"""

import pytest

from mtg_utils._analysis.roles import is_ramp, role_of
from mtg_utils._tuner.swaps import _ROLE_SEARCH, _reliable_ramp
from mtg_utils.testkit import snapshot_records, test_card, test_signals
from mtg_utils.theme_presets import get_preset, has_signal_coverage


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


@pytest.mark.parametrize(
    "name",
    [
        "Sol Ring",  # rock
        "Llanowar Elves",  # dork
        "Cultivate",  # land-fetch-to-battlefield (lf_ramp)
        # Number-word mana — the text read's blind spot ("Add three mana of any one
        # color" has no "{" / "one mana" after "add"), so these never counted.
        "Gilded Lotus",
        "Black Lotus",
        "Zaxara, the Exemplary",
        "Azusa, Lost but Seeking",  # extra land PLAY (the concept arm)
        "Burgeoning",  # land PUT (extra_land_drop)
        "Dockside Extortionist",  # a Treasure maker you keep
        "Uncle Iroh",  # firebending
    ],
)
def test_ramp_is_read_off_the_signal_path(name):
    card = _real(name)
    assert is_ramp(card)
    assert "ramp" in role_of(card)


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Bolt",
        "Demonic Tutor",
        "Sylvan Scrying",  # a land tutor TO HAND adds no mana and drops no land
        "Murder",
    ],
)
def test_non_ramp_is_not_ramp(name):
    assert not is_ramp(_real(name))


def test_a_land_is_the_mana_base_never_ramp():
    # Command Tower fires the `ramp` KEY (a fixing land) — the role still says no:
    # lands are the `lands` role and the land band's business (CR 305).
    tower = _real("Command Tower")
    assert get_preset("ramp").matches(tower)
    assert not is_ramp(tower)
    assert role_of(tower) == {"lands"}


def test_a_card_the_signal_path_cannot_see_degrades_to_text():
    rock = {
        "name": "Test Rock",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}.",
    }
    assert not has_signal_coverage(rock)
    assert is_ramp(rock)
    bear = {"name": "Test Bear", "type_line": "Creature — Bear", "oracle_text": ""}
    assert not is_ramp(bear)


def test_covered_card_never_falls_back_to_text():
    # Covered + no ramp signal ⇒ not ramp, even when the text read would say yes: a
    # DFC whose BACK face is a land joins "{T}: Add …" into the card's oracle text.
    bolt = _real("Lightning Bolt")
    assert has_signal_coverage(bolt)
    lying = {**bolt, "oracle_text": "{T}: Add {R}."}
    assert not is_ramp(lying)


def test_the_tuner_sources_ramp_by_the_preset_the_role_counts_by():
    """ADR-0051's point: over a real pool, what the tuner's ramp search admits
    (preset + its precision filter) is a subset of what the role counts — no card is
    suggested "for ramp" that the budgets row wouldn't then count as ramp."""
    (preset_name,) = _ROLE_SEARCH["ramp"]["preset_names"]
    preset = get_preset(preset_name)
    sourced = [r for r in snapshot_records() if preset.matches(r) and _reliable_ramp(r)]
    assert len(sourced) > 30
    assert all("ramp" in role_of(r) for r in sourced)
    # …and every nonland the role counts is reachable by that search's preset.
    counted = [r for r in snapshot_records() if is_ramp(r)]
    assert all(preset.matches(r) for r in counted)
