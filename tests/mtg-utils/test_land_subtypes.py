"""``LAND_SUBTYPES`` is the CR 205.3i list, no more and no less — one owner for
every land-membership test in the lanes and the bridge ledger."""

from mtg_utils._analysis._subtypes import LAND_SUBTYPES

CR_205_3I = {
    "plains",
    "island",
    "swamp",
    "mountain",
    "forest",
    "wastes",
    "cave",
    "desert",
    "gate",
    "lair",
    "locus",
    "mine",
    "power-plant",
    "sphere",
    "tower",
    "town",
    "urza's",
}


def test_land_subtypes_is_the_cr_205_3i_list():
    assert frozenset(CR_205_3I) == LAND_SUBTYPES
