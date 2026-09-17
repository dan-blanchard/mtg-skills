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
    # Command Tower fires the `ramp` KEY (a fixing land) — the role and its preset
    # still say no: lands are the `lands` role and the land band's business (CR 305),
    # and a land-filled search page would starve the tuner's ramp sourcing.
    tower = _real("Command Tower")
    assert "ramp" in {s.key for s in test_signals("Command Tower")}
    assert not get_preset("ramp").matches(tower)
    assert not is_ramp(tower)
    assert role_of(tower) == {"lands"}


def test_a_treasure_handed_to_an_opponent_is_not_ramp():
    # Both fire `treasure_makers|you` (phase scopes the maker, not the recipient);
    # the Token node's own `owner` tells them apart.
    offer = _real("An Offer You Can't Refuse")  # "Its controller creates two Treasure"
    assert "treasure_makers" in {s.key for s in test_signals(offer["name"])}
    assert not is_ramp(offer)
    assert is_ramp(_real("Smothering Tithe"))
    # One Treasure for you, one for an opponent — still yours.
    assert is_ramp(_real("Generous Plunderer"))


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


def test_the_preset_and_the_role_agree_on_every_covered_card():
    """The agreement test that replaces the "mirrors is_ramp" comments: over the whole
    snapshot, the preset the tuner SEARCHES by and the role the budgets row COUNTS by
    are the same set — and the text degrade is never consulted for a covered card."""
    preset = get_preset(_ROLE_SEARCH["ramp"]["preset_names"][0])
    records = snapshot_records()
    matched = {r["name"] for r in records if preset.matches(r)}
    counted = {r["name"] for r in records if "ramp" in role_of(r)}
    assert matched == counted
    assert len(matched) > 40


def test_the_tuner_ramp_search_page_is_nonland_ramp():
    """A search page is small and cmc-ascending, so a preset that matched mana lands
    (the `ramp` key fires for every fixing land) filled it with lands and starved the
    sourcing. Every preset hit must survive the tuner's own nonland gate."""
    preset = get_preset("ramp")
    hits = [r for r in snapshot_records() if preset.matches(r)]
    assert hits
    assert not [r["name"] for r in hits if "Land" in (r.get("type_line") or "")]
    # The precision filter only ever removes a conditionally-gated rock.
    dropped = [r["name"] for r in hits if not _reliable_ramp(r)]
    assert all("only if you control" in test_card(n)["oracle_text"] for n in dropped)


@pytest.mark.parametrize("name", ["Skyshroud Claim", "Hunting Wilds"])
def test_multi_land_fetch_is_ramp(name):
    # "up to two Forest cards" — the text read's fetch pattern never matched it.
    assert is_ramp(_real(name))
