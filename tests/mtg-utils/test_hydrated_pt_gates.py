"""P/T-dependent classifiers must work on *hydrated* cards, not just raw bulk records.

``scryfall_lookup.CARD_FIELDS`` is a strict whitelist, and ``power``/``toughness``
were missing from it. Because ``card_classify.card_pt_int`` defaults a missing field
to ``0``, every gate of the form ``card_pt_int(card) >= N`` silently evaluated False
for anything that went through ``scryfall-lookup --batch`` — which is the only input
the tuner, deck-rank and the goldfish accept.

Those gates were therefore dead in production while passing their own unit tests
(which build card dicts by hand, with P/T present). These tests close that gap by
asserting the classifiers against records that have actually been through hydration.
"""

from mtg_utils._deck_forge.text_reads import _VOLTRON_TOKEN_MAKE_RE  # noqa: F401
from mtg_utils._tuner.metrics import _is_wincon_card
from mtg_utils.card_classify import card_pt_int
from mtg_utils.scryfall_lookup import lookup_single


def _hydrate(name, bulk):
    card = lookup_single(name, bulk_path=bulk)
    assert card is not None, f"{name} missing from the fixture bulk"
    return card


class TestHydratedCardsCarryPT:
    def test_hydrated_creature_reports_real_power(self, sample_bulk_data):
        korvold = _hydrate("Korvold, Fae-Cursed King", sample_bulk_data)
        assert card_pt_int(korvold) == 4
        assert card_pt_int(korvold, "toughness") == 4

    def test_missing_pt_still_defaults_to_zero(self, sample_bulk_data):
        # The default is load-bearing for noncreatures; it must survive the fix.
        assert card_pt_int(_hydrate("Sol Ring", sample_bulk_data)) == 0


class TestWinconGateOnHydratedInput:
    """``_is_wincon_card`` classifies a big evasive body as a win condition via
    ``is_creature(card) and card_pt_int(card) >= 6``. With P/T stripped this arm
    could never fire on a hydrated deck, so large fliers were invisible to the
    tuner's wincon count and the scorecard under-reported win conditions.
    """

    def test_big_evasive_creature_is_a_wincon(self, sample_bulk_data):
        # No patching: Ancient Wyrm is a 7/7 flier in the fixture bulk, so this
        # fails outright if hydration drops P/T (card_pt_int returns 0 → gate False).
        wyrm = _hydrate("Ancient Wyrm", sample_bulk_data)
        assert card_pt_int(wyrm) == 7
        assert _is_wincon_card(wyrm) is True

    def test_small_evasive_creature_is_not_a_wincon(self, sample_bulk_data):
        # The other side of the gate: Korvold is a 4/4 flier — evasive but under 6.
        korvold = _hydrate("Korvold, Fae-Cursed King", sample_bulk_data)
        assert card_pt_int(korvold) == 4
        assert _is_wincon_card(korvold) is False

    def test_big_creature_without_evasion_is_not_a_wincon(self, sample_bulk_data):
        ground = dict(_hydrate("Ancient Wyrm", sample_bulk_data))
        ground["oracle_text"] = "Vanilla beater."
        ground["keywords"] = []
        assert _is_wincon_card(ground) is False
