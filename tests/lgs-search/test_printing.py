"""PrintingSpec: which store listings are a pinned printing.

Printing records here are synthetic (fictional names): only the per-printing
fields the matcher reads matter — set, number, illustration, frame, border,
frame effects, promo types, finishes, layout.
"""

from __future__ import annotations

from mtg_utils._stores.printing import (
    PrintingSpec,
    label_traits,
    records_by_name,
    set_keys,
)

ART = "11111111-1111-1111-1111-111111111111"
SHOWCASE_ART = "22222222-2222-2222-2222-222222222222"


def _printing(set_code: str, number: str, **extra) -> dict:
    return {
        "name": "Testcard Paragon",
        "set": set_code,
        "collector_number": number,
        "layout": "normal",
        "illustration_id": ART,
        "frame": "2015",
        "border_color": "black",
        "full_art": False,
        "frame_effects": ["legendary"],
        "promo_types": [],
        "finishes": ["nonfoil", "foil"],
        "prices": {"usd": "1.00", "usd_foil": "2.00"},
        **extra,
    }


ORIGINAL = _printing("abc", "9", prices={"usd": "0.40"})
LIST_REPRINT = _printing("plst", "ABC-9", finishes=["nonfoil"], prices={"usd": "0.30"})
SHOWCASE = _printing(
    "abc",
    "258",
    illustration_id=SHOWCASE_ART,
    frame_effects=["legendary", "showcase"],
    promo_types=["boosterfun"],
)
PROMO_STAMPED = _printing(
    "pabc", "9p", promo=True, promo_types=["promopack", "stamped"]
)
RECORDS = (ORIGINAL, LIST_REPRINT, SHOWCASE, PROMO_STAMPED)


def _spec(set_code: str, number: str, finish: str = "nonfoil") -> PrintingSpec:
    request = {"set": set_code, "collector_number": number, "finish": finish}
    return PrintingSpec("Testcard Paragon", request, RECORDS)


def _listing(set_code: str, number: str = "", **extra) -> dict:
    return {
        "store": "x",
        "card_name": "Testcard Paragon",
        "set_code": set_code,
        "condition": "NM",
        "foil": False,
        "price": 1.0,
        "qty_available": 1,
        "listing_id": "1",
        "url": "",
        "collector_number": number,
        **extra,
    }


class TestEquivalence:
    def test_list_reprint_takes_the_original_with_the_same_art(self):
        spec = _spec("plst", "ABC-9")
        assert [(r["set"], r["collector_number"]) for r in spec.acceptable] == [
            ("plst", "ABC-9"),
            ("abc", "9"),
        ]

    def test_other_art_and_stamps_are_not_equivalent(self):
        assert [r["set"] for r in _spec("abc", "258").acceptable] == ["abc"]
        assert [r["set"] for r in _spec("pabc", "9p").acceptable] == ["pabc"]

    def test_finish_the_equivalent_lacks_excludes_it(self):
        # The List reprint is nonfoil-only, so a foil ABC 9 has no equivalent.
        foil = _spec("abc", "9", "foil")
        assert [r["set"] for r in foil.acceptable] == ["abc"]

    def test_marketing_promo_tags_dont_change_style(self):
        bundle = _printing("xyz", "1", promo_types=["bundle", "universesbeyond"])
        spec = PrintingSpec(
            "Testcard Paragon",
            {"set": "abc", "collector_number": "9", "finish": "nonfoil"},
            (ORIGINAL, bundle),
        )
        assert len(spec.acceptable) == 2

    def test_usd_is_the_cheapest_acceptable_in_the_finish(self):
        assert _spec("plst", "ABC-9").usd() == 0.30
        assert _spec("abc", "258", "foil").usd() == 2.00

    def test_list_origin_stands_in_when_the_pool_lacks_the_list_card(self):
        spec = PrintingSpec(
            "Testcard Paragon",
            {"set": "plst", "collector_number": "ABC-9", "finish": "nonfoil"},
            (ORIGINAL, SHOWCASE),
        )
        assert [r["set"] for r in spec.acceptable] == ["abc"]
        assert spec.match(_listing("PLST", "ABC-9")) == "exact"
        assert spec.match(_listing("ABC", "9")) == "equivalent"


class TestMatchByNumber:
    def test_exact_and_equivalent(self):
        spec = _spec("plst", "ABC-9")
        assert spec.match(_listing("PLST", "ABC-9")) == "exact"
        assert spec.match(_listing("ABC", "9")) == "equivalent"
        assert spec.match(_listing("ABC", "258")) is None

    def test_finish_must_agree(self):
        spec = _spec("abc", "9", "foil")
        assert spec.match(_listing("ABC", "9")) is None
        assert spec.match(_listing("ABC", "9", foil=True, finish="foil")) == "exact"
        etched = _listing("ABC", "9", foil=True, finish="etched")
        assert spec.match(etched) is None

    def test_number_case_is_ignored(self):
        assert _spec("pabc", "9p").match(_listing("PABC", "9P")) == "exact"


class TestMatchBySetAndStyle:
    def test_unlabelled_listing_is_the_plain_printing(self):
        # The pinned set: matched by set and style. Another set's printing
        # with the same art and style: an equivalent.
        assert _spec("abc", "9").match(_listing("ABC")) == "set+style"
        assert _spec("plst", "ABC-9").match(_listing("ABC")) == "equivalent"

    def test_showcase_label_is_the_showcase_printing(self):
        assert (
            _spec("abc", "258").match(_listing("ABC", variant_labels=["Showcase"]))
            == "set+style"
        )
        assert _spec("abc", "258").match(_listing("ABC")) is None
        assert (
            _spec("plst", "ABC-9").match(_listing("ABC", variant_labels=["Showcase"]))
            is None
        )

    def test_unknown_label_matches_nothing(self):
        spec = _spec("plst", "ABC-9")
        assert spec.match(_listing("ABC", variant_labels=["1/1", "Red"])) is None

    def test_ambiguous_set_is_rejected(self):
        # Two plain printings in one set, only one acceptable: the set and
        # labels can't say which the store has.
        other = _printing("abc", "10", illustration_id=SHOWCASE_ART)
        spec = PrintingSpec(
            "Testcard Paragon",
            {"set": "abc", "collector_number": "9", "finish": "nonfoil"},
            (ORIGINAL, other),
        )
        assert spec.match(_listing("ABC")) is None


class TestTokens:
    def test_token_answers_to_its_token_set(self):
        token = {**_printing("ncc", "18"), "layout": "token"}
        assert set_keys(token) == {"ncc", "tncc"}
        assert set_keys({**_printing("plst", "TELD-7"), "layout": "token"}) == {"plst"}
        spec = PrintingSpec(
            "Testcard Paragon",
            {"set": "tncc", "collector_number": "18", "finish": "nonfoil"},
            (token,),
        )
        assert spec.match(_listing("TNCC", "18")) == "exact"
        assert spec.label == "Testcard Paragon (TNCC) 18"


def test_label_traits():
    assert label_traits(["Extended Art"]) == {"extendedart"}
    assert label_traits(["Halo Foil"]) == {"halofoil"}
    assert label_traits(["THB", "created by Someone", "011"]) == frozenset()
    assert label_traits(["Commander"]) is None


def test_records_by_name_takes_a_two_faced_cards_front_face():
    front = {"name": "Testcard Front // Testcard Back", "set": "abc"}
    other = {"name": "Testcard Elsewhere", "set": "abc"}
    found = records_by_name([front, other], ["Testcard Front // Testcard Back"])
    assert found == {"Testcard Front // Testcard Back": [front]}
