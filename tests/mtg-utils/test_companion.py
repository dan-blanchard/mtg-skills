"""Tests for the Ikoria companion deckbuilding-condition validators.

Every real card comes from the testkit snapshot by name (ADR-0056); only a deck
quantity is overlaid. The one hand-built record is the DFC name-dispatch machinery
("… // Hypothetical Back"), which no real companion has.
"""

import pytest

from mtg_utils.companion import (
    COMPANION_NAMES,
    companion_violations,
    is_companion,
)
from mtg_utils.testkit import test_card


def _card(
    name,
    type_line="Creature — Human",
    cmc=0.0,
    mana_cost="",
    oracle_text="",
    keywords=None,
    quantity=None,
    card_faces=None,
    layout=None,
):
    card = {
        "name": name,
        "type_line": type_line,
        "cmc": cmc,
        "mana_cost": mana_cost,
        "oracle_text": oracle_text,
        "keywords": keywords or [],
    }
    if quantity is not None:
        card["quantity"] = quantity
    if card_faces is not None:
        card["card_faces"] = card_faces
    if layout is not None:
        card["layout"] = layout
    return card


def _real(name, quantity=None):
    """The real card *name* from the testkit snapshot, with only a deck quantity
    overlaid."""
    card = test_card(name)
    if quantity is not None:
        card["quantity"] = quantity
    return card


def _companion(name):
    return test_card(name)


FOREST = _real("Forest")
WASTES = _real("Wastes")


class TestCompanionNames:
    def test_exactly_ten(self):
        assert len(COMPANION_NAMES) == 10

    def test_contains_the_ikoria_ten(self):
        assert "Lurrus of the Dream-Den" in COMPANION_NAMES
        assert "Yorion, Sky Nomad" in COMPANION_NAMES


class TestIsCompanion:
    def test_via_keywords(self):
        assert is_companion(_real("Lurrus of the Dream-Den"))

    def test_via_oracle_text_fallback(self):
        # The real Zirda with its keywords list dropped, so only the oracle
        # "Companion —" line can identify it.
        card = {**_real("Zirda, the Dawnwaker"), "keywords": []}
        assert is_companion(card)

    def test_negative(self):
        # A real near miss: "Doctor's companion" is a partner variant, not the
        # Ikoria companion keyword.
        card = _real("Sarah Jane Smith")
        assert "companion" in card["oracle_text"].lower()
        assert is_companion(card) is False

    def test_non_companion_raises(self):
        with pytest.raises(ValueError, match="not a known companion"):
            companion_violations(_real("Grizzly Bears"), [])


class TestGyruda:
    """Condition: only cards with even mana values. 0 (lands, X-in-library) is even."""

    def test_satisfied_including_land_mv0(self):
        deck = [FOREST, _real("Arcane Signet")]
        assert companion_violations(_companion("Gyruda, Doom of Depths"), deck) == []

    def test_pure_x_cost_is_mv0_even(self):
        # CR 202.3e: X is 0 in the library, so {X}{X} is mana value 0 — even.
        deck = [_real("Astral Cornucopia")]
        assert companion_violations(_companion("Gyruda, Doom of Depths"), deck) == []

    def test_odd_card_violates(self):
        deck = [_real("Opt")]
        violations = companion_violations(_companion("Gyruda, Doom of Depths"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Opt"
        assert violations[0]["rule"] == "702.139b"
        assert "even mana value" in violations[0]["reason"]

    def test_x_plus_colored_is_odd_and_violates(self):
        deck = [_real("Blaze")]
        assert (
            len(companion_violations(_companion("Gyruda, Doom of Depths"), deck)) == 1
        )


class TestJegantha:
    """Condition: no card has more than one of the same mana symbol in its cost."""

    def test_two_of_same_colored_symbol_fails(self):
        deck = [_real("Wrath of God")]
        violations = companion_violations(_companion("Jegantha, the Wellspring"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Wrath of God"
        assert "{W}" in violations[0]["reason"]

    def test_wubrg_passes(self):
        deck = [_real("Sliver Overlord")]
        assert companion_violations(_companion("Jegantha, the Wellspring"), deck) == []

    def test_double_x_fails(self):
        # Official ruling: {X}{X}{R} does not satisfy the condition. Bonfire of
        # the Damned costs exactly {X}{X}{R}: X is its only repeated symbol.
        deck = [_real("Bonfire of the Damned")]
        assert (
            len(companion_violations(_companion("Jegantha, the Wellspring"), deck)) == 1
        )

    def test_repeated_hybrid_symbol_fails(self):
        # Official ruling: {(r/g)}{(r/g)} does not satisfy the condition.
        deck = [_real("Burning-Tree Emissary")]
        assert (
            len(companion_violations(_companion("Jegantha, the Wellspring"), deck)) == 1
        )

    def test_land_with_no_cost_passes(self):
        assert (
            companion_violations(_companion("Jegantha, the Wellspring"), [FOREST]) == []
        )

    def test_adventure_faces_checked_separately(self):
        # Bonecrusher Giant {2}{R} // Stomp {1}{R}: each cost alone repeats no
        # symbol, and it was Jegantha-legal in tournament Standard.
        card = _real("Bonecrusher Giant // Stomp")
        assert (
            companion_violations(_companion("Jegantha, the Wellspring"), [card]) == []
        )


class TestKaheera:
    """Condition: each creature card is a Cat/Elemental/Nightmare/Dinosaur/Beast."""

    def test_listed_types_pass(self):
        deck = [
            _real("King of the Pride"),
            _real("Thassa's Oracle"),
        ]
        violations = companion_violations(_companion("Kaheera, the Orphanguard"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Thassa's Oracle"

    def test_noncreature_cards_are_unconstrained(self):
        deck = [
            _real("Counterspell"),
            FOREST,
            _real("Ravenous Baloth"),
        ]
        assert companion_violations(_companion("Kaheera, the Orphanguard"), deck) == []

    def test_changeling_is_every_creature_type(self):
        # CR 702.73a: changeling works everywhere, even outside the game.
        deck = [_real("Universal Automaton")]
        assert companion_violations(_companion("Kaheera, the Orphanguard"), deck) == []


class TestKeruga:
    """Condition: only cards with mana value 3+ and land cards."""

    def test_satisfied(self):
        deck = [FOREST, _real("Hill Giant")]
        assert companion_violations(_companion("Keruga, the Macrosage"), deck) == []

    def test_cheap_nonland_violates(self):
        deck = [_real("Opt")]
        violations = companion_violations(_companion("Keruga, the Macrosage"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Opt"
        assert "mana value 3 or greater" in violations[0]["reason"]


class TestLurrus:
    """Condition: each permanent card has mana value 2 or less."""

    def test_expensive_instant_passes(self):
        # Instants are not permanent cards (CR 110.4).
        deck = [_real("Fact or Fiction")]
        assert companion_violations(_companion("Lurrus of the Dream-Den"), deck) == []

    def test_mv3_creature_fails(self):
        deck = [_real("Centaur Courser")]
        violations = companion_violations(_companion("Lurrus of the Dream-Den"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Centaur Courser"
        assert "mana value 2 or less" in violations[0]["reason"]

    def test_land_is_a_permanent_card_with_mv0(self):
        assert (
            companion_violations(_companion("Lurrus of the Dream-Den"), [FOREST]) == []
        )

    def test_cheap_permanents_pass(self):
        deck = [
            _real("Esper Sentinel"),
            _real("Rancor"),
        ]
        assert companion_violations(_companion("Lurrus of the Dream-Den"), deck) == []


class TestLutri:
    """Condition: each nonland card has a different name (quantities count)."""

    def test_quantity_two_fails(self):
        deck = [_real("Opt", quantity=2)]
        violations = companion_violations(_companion("Lutri, the Spellchaser"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Opt"
        assert "different name" in violations[0]["reason"]

    def test_duplicate_entries_fail(self):
        deck = [_real("Opt"), _real("Opt")]
        assert (
            len(companion_violations(_companion("Lutri, the Spellchaser"), deck)) == 1
        )

    def test_basic_lands_are_exempt(self):
        deck = [
            _real("Forest", quantity=20),
            _real("Opt"),
            _real("Shock"),
        ]
        assert companion_violations(_companion("Lutri, the Spellchaser"), deck) == []


class TestObosh:
    """Condition: only cards with odd mana values and land cards."""

    def test_land_mv0_is_exempt(self):
        # 0 is even, but the explicit "and land cards" clause exempts lands.
        deck = [FOREST, _real("Opt")]
        assert companion_violations(_companion("Obosh, the Preypiercer"), deck) == []

    def test_even_nonland_violates(self):
        deck = [_real("Arcane Signet")]
        violations = companion_violations(_companion("Obosh, the Preypiercer"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] == "Arcane Signet"
        assert "odd mana value" in violations[0]["reason"]

    def test_mv0_nonland_violates(self):
        deck = [_real("Ornithopter")]
        assert (
            len(companion_violations(_companion("Obosh, the Preypiercer"), deck)) == 1
        )


class TestUmori:
    """Condition: each nonland card shares a card type (one type spans all)."""

    def test_artifact_creature_bridges_creatures(self):
        # Official ruling: artifact creature + enchantment creature + creature
        # is satisfied ("creature" spans all).
        deck = [
            _real("Esper Sentinel"),
            _real("Nyx-Fleece Ram"),
            _real("Grizzly Bears"),
            FOREST,
        ]
        assert companion_violations(_companion("Umori, the Collector"), deck) == []

    def test_no_single_shared_type_fails(self):
        # Official ruling: artifact creature + artifact + creature is NOT
        # satisfied — no one type spans all three.
        deck = [
            _real("Esper Sentinel"),
            _real("Sol Ring"),
            _real("Grizzly Bears"),
        ]
        violations = companion_violations(_companion("Umori, the Collector"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] is None
        assert "card type" in violations[0]["reason"]

    def test_lands_are_exempt(self):
        deck = [FOREST, _real("Dryad Arbor")]
        assert companion_violations(_companion("Umori, the Collector"), deck) == []

    def test_all_instants_pass(self):
        deck = [_real("Opt"), _real("Shock")]
        assert companion_violations(_companion("Umori, the Collector"), deck) == []


class TestYorion:
    """Condition: starting deck has at least 20 cards more than the minimum size."""

    def test_80_cards_at_minimum_60_passes(self):
        deck = [_real("Forest", quantity=80)]
        assert (
            companion_violations(_companion("Yorion, Sky Nomad"), deck, deck_minimum=60)
            == []
        )

    def test_79_cards_at_minimum_60_fails(self):
        deck = [_real("Forest", quantity=79)]
        violations = companion_violations(
            _companion("Yorion, Sky Nomad"), deck, deck_minimum=60
        )
        assert len(violations) == 1
        assert violations[0]["card"] is None
        assert "80" in violations[0]["reason"]

    def test_no_minimum_is_unsatisfiable(self):
        # Exact-size formats (Commander, CR 903.5a: min = max = 100) can never
        # be 20 over their own minimum.
        deck = [_real("Forest", quantity=100)]
        violations = companion_violations(_companion("Yorion, Sky Nomad"), deck)
        assert len(violations) == 1
        assert violations[0]["card"] is None
        assert "unsatisfiable" in violations[0]["reason"]


class TestZirda:
    """Condition: each permanent card has an activated ability."""

    def test_cycling_only_card_passes(self):
        # CR 702.29a: cycling is an activated ability. Street Wraith's only
        # activated ability is cycling (swampwalk is static).
        card = _real("Street Wraith")
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [card]) == []

    def test_cycling_via_oracle_text_without_keywords_list(self):
        # Krosan Tusker's only activated ability is cycling; its keywords list is
        # dropped so the oracle "Cycling {2}{G}" line alone must carry it.
        card = {**_real("Krosan Tusker"), "keywords": []}
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [card]) == []

    def test_reminder_text_colon_does_not_falsely_pass(self):
        # The only colon is inside the Treasure reminder text, which grants the
        # TOKEN an ability; Prosperous Innkeeper itself has none.
        card = _real("Prosperous Innkeeper")
        violations = companion_violations(_companion("Zirda, the Dawnwaker"), [card])
        assert len(violations) == 1
        assert violations[0]["card"] == "Prosperous Innkeeper"

    def test_vanilla_creature_fails(self):
        card = _real("Grizzly Bears")
        violations = companion_violations(_companion("Zirda, the Dawnwaker"), [card])
        assert len(violations) == 1
        assert "activated ability" in violations[0]["reason"]

    def test_colon_ability_passes(self):
        card = _real("Prodigal Sorcerer")
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [card]) == []

    def test_basic_land_has_intrinsic_mana_ability(self):
        # CR 305.6: a basic land type carries "{T}: Add [mana]" intrinsically;
        # Forest's only printed colon is inside reminder text.
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [FOREST]) == []

    def test_wastes_passes_via_printed_colon(self):
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [WASTES]) == []

    def test_instants_are_unconstrained(self):
        deck = [_real("Opt")]
        assert companion_violations(_companion("Zirda, the Dawnwaker"), deck) == []

    def test_equip_keyword_passes(self):
        # CR 702.6a: equip is an activated ability.
        card = _real("Bone Saw")
        assert companion_violations(_companion("Zirda, the Dawnwaker"), [card]) == []


class TestDfcNameMatching:
    def test_companion_dispatch_uses_front_face_name(self):
        companion = _card(
            "Lurrus of the Dream-Den // Hypothetical Back",
            card_faces=[
                {
                    "name": "Lurrus of the Dream-Den",
                    "type_line": "Legendary Creature — Cat Nightmare",
                },
                {"name": "Hypothetical Back", "type_line": "Creature — Nightmare"},
            ],
            layout="transform",
            keywords=["Companion"],
        )
        deck = [_real("Centaur Courser")]
        violations = companion_violations(companion, deck)
        assert len(violations) == 1
        assert violations[0]["rule"] == "702.139b"

    def test_deck_card_front_face_governs_mv_and_type(self):
        # CR 712.8a: in the library a DFC has only front-face characteristics;
        # Scryfall's top-level cmc is the front face's mana value (CR 202.3b).
        card = _real("Brutal Cathar // Moonrage Brute")
        violations = companion_violations(_companion("Lurrus of the Dream-Den"), [card])
        assert len(violations) == 1
        assert violations[0]["card"] == "Brutal Cathar"
