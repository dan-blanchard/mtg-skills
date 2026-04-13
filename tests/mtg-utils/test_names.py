"""Tests for mtg_utils.names — card-name normalization."""

from mtg_utils.names import normalize_card_name


class TestNormalizeCardName:
    def test_lowercases(self):
        assert normalize_card_name("Sol Ring") == "sol ring"

    def test_strips_diacritics(self):
        assert normalize_card_name("Lim-D\u00fbl's Vault") == "lim-dul's vault"

    def test_ascii_only_input_unchanged_aside_from_case(self):
        assert normalize_card_name("Lim-Dul's Vault") == "lim-dul's vault"

    def test_ascii_and_diacritic_forms_normalize_equal(self):
        """The load-bearing invariant: both spellings of a card must
        collapse to the same key. If this ever breaks, the owned-cards
        intersection silently drops cards and budget totals lie."""
        ascii_form = normalize_card_name("Lim-Dul's Vault")
        accented = normalize_card_name("Lim-D\u00fbl's Vault")
        assert ascii_form == accented

    def test_empty_string(self):
        assert normalize_card_name("") == ""

    def test_double_faced_card_name_preserved(self):
        """Split/DFC names contain `//` and should survive normalization
        (case-folded but not altered otherwise)."""
        assert normalize_card_name("Fire // Ice") == "fire // ice"
