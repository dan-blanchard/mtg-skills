"""Serve-ident conversions in ``signal_specs/data_3.py`` (2026-10-18).

Each converted spec's enabler arm is now the lanes' own structural idents, not an
oracle regex (docs/plans/serve-idents-and-avenue-support.md, Pass A). One row per
spec pins: the regex arm is gone, the ident arm is in place, a real card the regex
MISSED now serves, and (where the regex had one) a card it wrongly served no longer
does. Where the regex and the lane agreed card for card, the positive is a shared
card: the row then pins only that the ident arm carries the lane.
"""

import pytest

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


# (key, scope, ident, a card that serves, a card the regex wrongly served or None)
_CONVERTED = [
    (
        "commander_matters",
        "you",
        "commander_matters|you|",
        "Command Beacon",
        "Faceless One",
    ),
    ("has_devour", "you", "has_devour|you|", "Dragon Broodmother", "Devour in Flames"),
    (
        "exile_until_leaves",
        "you",
        "exile_until_leaves|you|",
        "Oblivion Ring",
        "Lumbering Battlement",
    ),
    (
        "dice_makers",
        "you",
        "dice_makers|you|",
        "Circuits Act",
        '"Lifetime" Pass Holder',
    ),
    (
        "dice_matters",
        "you",
        "dice_matters|you|",
        "Circuits Act",
        '"Lifetime" Pass Holder',
    ),
    (
        "single_target_neutralize",
        "you",
        "single_target_neutralize|you|",
        "Cursed Courtier",
        "Awakened Awareness",
    ),
    ("extra_land_drop", "you", "extra_land_drop|you|", "Kamahl's Druidic Vow", None),
    (
        "phasing_makers",
        "you",
        "phasing_makers|you|",
        "Blink Dog",
        "Cloak of Invisibility",
    ),
    (
        "firebending_makers",
        "you",
        "firebending_makers|you|",
        "Azula, On the Hunt",
        "Firebending Lesson",
    ),
    (
        "firebending_matters",
        "you",
        "firebending_matters|you|",
        "Azula, On the Hunt",
        "Firebending Lesson",
    ),
    (
        "myriad_grant",
        "you",
        "myriad_grant|you|",
        "Blade of Selves",
        "The Everflowing Well // The Myriad Pools",
    ),
    (
        "opponent_discard",
        "opponents",
        "opponent_discard|opponents|",
        "Alley Grifters",
        "Compulsive Research",
    ),
    (
        "partner_background",
        "you",
        "partner_background|you|",
        "Akiri, Line-Slinger",
        None,
    ),
    (
        "facedown_matters",
        "you",
        "facedown_matters|you|",
        "Bonethorn Valesk",
        "Cloak and Dagger, Entwined",
    ),
    (
        "facedown_makers",
        "you",
        "facedown_makers|you|",
        "Bonethorn Valesk",
        "Cloak and Dagger, Entwined",
    ),
    (
        "hand_disruption",
        "opponents",
        "hand_disruption|opponents|",
        "Lay Bare",
        "Wild Evocation",
    ),
    ("counter_control", "you", "counter_control|you|", "Glyph Keeper", None),
    ("ki_counter_makers", "you", "ki_counter_makers|you|", "Petalmane Baku", None),
    ("ki_counter_matters", "you", "ki_counter_matters|you|", "Petalmane Baku", None),
    (
        "destroy_legendary",
        "any",
        "destroy_legendary|any|",
        "Invasion of Fiora // Marchesa, Resolute Monarch",
        None,
    ),
    ("airbend_makers", "you", "airbend_makers|you|", "Aang, Airbending Master", None),
    ("earthbend_makers", "you", "earthbend_makers|you|", "Badgermole", None),
    ("earthbend_matters", "you", "earthbend_matters|you|", "Badgermole", None),
    ("waterbend_makers", "you", "waterbend_makers|you|", "Giant Koi", None),
    ("waterbend_matters", "you", "waterbend_matters|you|", "Giant Koi", None),
    ("stickers_matter", "you", "stickers_matter|you|", "Aerialephant", None),
    (
        "companion_keyword",
        "you",
        "companion_keyword|you|",
        "Jegantha, the Wellspring",
        None,
    ),
    ("has_soulbond", "you", "has_soulbond|you|", "Deadeye Navigator", None),
    ("boast_makers", "you", "boast_makers|you|", "Frenzied Raider", None),
    ("boast_matters", "you", "boast_matters|you|", "Frenzied Raider", None),
    ("exhaust_makers", "you", "exhaust_makers|you|", "Adrenaline Jockey", None),
    ("exhaust_matters", "you", "exhaust_matters|you|", "Adrenaline Jockey", None),
    ("station_makers", "you", "station_makers|you|", "Hearthhull, the Worldseed", None),
    (
        "station_matters",
        "you",
        "station_matters|you|",
        "Hearthhull, the Worldseed",
        None,
    ),
    ("tap_down", "opponents", "tap_down|opponents|", "Blustersquall", None),
    ("end_the_turn", "you", "end_the_turn|you|", "Time Stop", None),
    (
        "trigger_doubling",
        "you",
        "trigger_doubling|you|",
        "Delney, Streetwise Lookout",
        None,
    ),
    ("convoke_makers", "you", "convoke_makers|you|", "Chord of Calling", None),
    ("convoke_matters", "you", "convoke_matters|you|", "Chord of Calling", None),
    ("named_counter_misc", "you", "named_counter_misc|you|", "Bomb Squad", None),
    ("powerup_matters", "you", "powerup_matters|you|", "Extremis Elite", None),
    (
        "rad_counter_makers",
        "opponents",
        "rad_counter_makers|opponents|",
        "Feral Ghoul",
        None,
    ),
    (
        "oil_counter_makers",
        "you",
        "oil_counter_makers|you|",
        "Armored Scrapgorger",
        None,
    ),
    (
        "oil_counter_matters",
        "you",
        "oil_counter_matters|you|",
        "Armored Scrapgorger",
        None,
    ),
    ("fight_makers", "you", "fight_makers|you|", "Hans Eriksson", None),
    ("has_changeling", "you", "has_changeling|you|", "Mutavault", None),
    (
        "starting_life_matters",
        "you",
        "starting_life_matters|you|",
        "Angel of Destiny",
        None,
    ),
    ("affinity_type", "you", "affinity_type|you|", "Brine Giant", None),
    ("evasion_denial", "opponents", "evasion_denial|opponents|", "Great Wall", None),
    ("lure_makers", "you", "lure_makers|you|", "Talruum Piper", None),
    (
        "opponent_exile_matters",
        "opponents",
        "opponent_exile_matters|opponents|",
        "Umbris, Fear Manifest",
        None,
    ),
    ("villainous_choice", "you", "villainous_choice|you|", "Dr. Eggman", None),
    ("crimes_matter", "you", "crimes_matter|you|", "Gisa, the Hellraiser", None),
    ("cascade_makers", "you", "cascade_makers|you|", "Ardent Plea", None),
    ("cascade_matters", "you", "cascade_matters|you|", "Ardent Plea", None),
    ("regenerate_makers", "you", "regenerate_makers|you|", "Clot Sliver", None),
    # The +1/+1 counter package: plus_one_makers reads the keyword actions, so a
    # connive printed without its reminder text serves; the regex served a "no
    # +1/+1 counters" negation.
    (
        "amass_makers",
        "you",
        "plus_one_makers|you|",
        "Baron Helmut Zemo",
        "Hindervines",
    ),
    (
        "incubate_makers",
        "you",
        "plus_one_makers|you|",
        "Baron Helmut Zemo",
        "Hindervines",
    ),
]


@pytest.mark.parametrize(
    ("key", "scope", "ident", "serves", "dropped"),
    _CONVERTED,
    ids=[f"{k}|{s}" for k, s, *_ in _CONVERTED],
)
def test_serve_is_the_lane_not_a_regex(key, scope, ident, serves, dropped):
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    assert ident in spec.serve.signal_idents
    assert spec.serve.matches(_card(serves)), serves
    if dropped is not None:
        assert not spec.serve.matches(_card(dropped)), dropped
