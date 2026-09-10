"""Tests for ``mtg_utils.commander_cost`` — the ADR-0044 effective commander cost.

Two layers: the IR read (real cards via the committed snapshot, no phase cache /
network) and the closed-form estimator (hand-computed fixtures)."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from mtg_utils import commander_cost as cc
from mtg_utils.commander_cost import (
    STATUS_MODELLED,
    STATUS_NONE,
    SelfDiscount,
    colored_pips,
    contribution,
    effective_commander_cost,
    expected_operand,
    matches_population,
    read_self_discount,
)
from mtg_utils.testkit import test_card, test_card_ir

FLYER_POWER = SelfDiscount(
    kind="sum",
    property="Power",
    per_unit=1,
    core_types=("Creature",),
    subtypes=(),
    keywords=("Flying",),
)
CREATURE_COUNT = SelfDiscount(
    kind="count",
    property=None,
    per_unit=1,
    core_types=("Creature",),
    subtypes=(),
    keywords=(),
)


def _creature(name, cmc, power, *, flying=True, qty=1):
    rec = {
        "name": name,
        "cmc": float(cmc),
        "mana_cost": f"{{{cmc - 1}}}{{U}}" if cmc > 1 else "{U}",
        "type_line": "Creature — Bird",
        "power": str(power),
        "toughness": "1",
        "keywords": ["Flying"] if flying else [],
    }
    return (rec, qty)


ISLAND = (
    {"name": "Island", "cmc": 0.0, "type_line": "Basic Land — Island", "keywords": []},
    30,
)


class TestIRRead:
    """Real cards, real phase parse (from the snapshot's stored face records)."""

    def test_lord_of_the_eagles_reads_flyer_power_sum(self):
        test_card_ir("The Lord of the Eagles")  # seeds the trees memo (CI-safe)
        d = read_self_discount(test_card("The Lord of the Eagles"))
        assert d == FLYER_POWER
        assert "total Power" in d.describe()
        assert "with Flying" in d.describe()

    def test_ghalta_reads_creature_power_sum_no_keyword(self):
        test_card_ir("Ghalta, Primal Hunger")
        d = read_self_discount(test_card("Ghalta, Primal Hunger"))
        assert isinstance(d, SelfDiscount)
        assert (d.kind, d.property, d.per_unit) == ("sum", "Power", 1)
        assert d.core_types == ("Creature",)
        assert d.keywords == ()

    def test_graveyard_operand_is_reported_unmodelled(self):
        # Karador: "costs {1} less for each creature card in your graveyard" —
        # a ZoneCardCount operand needs a self-mill model (deferred, ADR-0044).
        test_card_ir("Karador, Ghost Chieftain")
        d = read_self_discount(test_card("Karador, Ghost Chieftain"))
        assert d == "unmodelled (ZoneCardCount)"

    def test_per_turn_operand_is_reported_unmodelled(self):
        # Thrasta: "costs {3} less for each other spell cast this turn".
        test_card_ir("Thrasta, Tempest's Roar")
        d = read_self_discount(test_card("Thrasta, Tempest's Roar"))
        assert d.startswith("unmodelled (")

    def test_card_without_clause_reads_none(self):
        test_card_ir("Sol Ring")
        assert read_self_discount(test_card("Sol Ring")) == STATUS_NONE

    def test_missing_ir_reads_no_ir(self):
        # No oracle_id → trees_for degrades to () → the reported no-IR status.
        assert read_self_discount({"name": "Nobody", "cmc": 4.0}) == cc.STATUS_NO_IR


class TestPopulationMatch:
    def test_type_and_keyword_required(self):
        flyer, _ = _creature("Bird", 2, 2)
        walker, _ = _creature("Walker", 2, 2, flying=False)
        assert matches_population(flyer, FLYER_POWER)
        assert not matches_population(walker, FLYER_POWER)
        assert matches_population(walker, CREATURE_COUNT)
        assert not matches_population(ISLAND[0], CREATURE_COUNT)

    def test_dfc_matches_on_front_face_only(self):
        rec = {
            "name": "Front // Back",
            "type_line": "Creature — Human // Land",
            "keywords": ["Flying"],
            "card_faces": [{"power": "3", "toughness": "3", "cmc": 3.0}, {}],
        }
        assert matches_population(rec, FLYER_POWER)
        assert contribution(rec, FLYER_POWER) == 3

    def test_variable_power_is_conservative(self):
        star, _ = _creature("Star", 3, "*")
        assert contribution(star, FLYER_POWER) == 0
        assert contribution(star, CREATURE_COUNT) == 1

    def test_permanent_word_excludes_spells(self):
        perm = SelfDiscount("count", None, 1, ("Permanent",), (), ())
        assert matches_population({"type_line": "Artifact", "keywords": []}, perm)
        assert not matches_population({"type_line": "Instant", "keywords": []}, perm)


class TestColoredPips:
    @pytest.mark.parametrize(
        ("cost", "pips"),
        [
            ("{7}{U}{U}", 2),
            ("{10}{G}{G}", 2),
            ("{X}{U}{U}", 2),
            ("{2}{U/B}{U/P}", 2),
            ("{C}{C}", 2),
            ("{3}", 0),
            ("", 0),
            (None, 0),
        ],
    )
    def test_counts_only_irreducible_symbols(self, cost, pips):
        assert colored_pips(cost) == pips


class TestExpectedOperand:
    def test_hypergeometric_sum_within_budget(self):
        # 99-card library, turn 4: each card seen w.p. (7+3)/99; budget 1+2+3 = 6.
        deck = [
            _creature("A", 1, 1),
            _creature("B", 2, 2),
            _creature("C", 3, 3),
            ISLAND,
        ]
        seen = Fraction(10, 99)
        expected = float(seen * (1 + 2 + 3))
        assert expected_operand(
            deck, FLYER_POWER, turn=4, library_size=99
        ) == pytest.approx(expected)

    def test_mana_budget_truncates_cheapest_first(self):
        # Turn 2: budget = 1 mana. Thirty 2-drop 2-power flyers: expected copies
        # 30 * 8/99 ≈ 2.42 → 4.85 mana wanted, only 1 allowed → the fraction that
        # fits is 1/4.85, so the expected power is 2.42 * 2 / 4.85 = 1.0.
        deck = [_creature("Drake", 2, 2, qty=30), ISLAND]
        assert expected_operand(
            deck, FLYER_POWER, turn=2, library_size=99
        ) == pytest.approx(1.0)

    def test_cheapest_first_ordering_favours_low_curve(self):
        # Turn 2 (budget 1 mana): one 1-drop with 2 power and ten 4-drops with 4
        # power. Cheapest-first takes the 1-drop whole (2 power for 8/99 mana) and
        # fills the rest of the budget with 4-drops at 1 power per mana, so the
        # total is 2*8/99 + (1 - 8/99). Taking the 4-drops first would spend the
        # whole budget at 1 power per mana and yield exactly 1.0.
        deck = [_creature("Seer", 1, 2), _creature("Sphinx", 4, 4, qty=10), ISLAND]
        seen = Fraction(8, 99)
        expected = float(seen * 2 + (1 - seen))
        got = expected_operand(deck, FLYER_POWER, turn=2, library_size=99)
        assert got == pytest.approx(expected)
        assert got > 1.0

    def test_count_kind_counts_bodies_not_power(self):
        deck = [_creature("A", 1, 5), _creature("B", 1, 0, flying=False), ISLAND]
        assert expected_operand(
            deck, CREATURE_COUNT, turn=4, library_size=99
        ) == pytest.approx(float(Fraction(10, 99) * 2))

    def test_zero_turn_or_library_is_zero(self):
        assert (
            expected_operand(
                [_creature("A", 1, 1)], FLYER_POWER, turn=0, library_size=99
            )
            == 0
        )
        assert (
            expected_operand(
                [_creature("A", 1, 1)], FLYER_POWER, turn=3, library_size=0
            )
            == 0
        )


class TestEffectiveCommanderCost:
    LORD = {
        "name": "Lord",
        "oracle_id": "fake-lord",
        "cmc": 9.0,
        "mana_cost": "{7}{U}{U}",
        "type_line": "Legendary Creature — Bird Noble",
        "keywords": ["Flash", "Flying"],
    }

    def _deck_with_flyer_power(self, total_power_per_drop: int, count: int):
        # `count` copies each of 1-, 2-, 3-drop flyers with the given power.
        return [
            _creature("One", 1, total_power_per_drop, qty=count),
            _creature("Two", 2, total_power_per_drop, qty=count),
            _creature("Three", 3, total_power_per_drop, qty=count),
            ISLAND,
        ]

    def test_modelled_lord_lands_on_affordable_turn(self, monkeypatch):
        monkeypatch.setattr(cc, "read_self_discount", lambda _rec: FLYER_POWER)
        deck = self._deck_with_flyer_power(2, 10)
        block = effective_commander_cost(self.LORD, deck, library_size=99)
        assert block["status"] == STATUS_MODELLED
        assert block["printed"] == 9
        assert block["pips"] == 2
        # Recompute the fixed point by hand from the same estimator.
        for turn in range(1, 10):
            ex = math.floor(
                expected_operand(deck, FLYER_POWER, turn=turn, library_size=99)
            )
            residual = max(2, 9 - ex)
            if residual <= turn:
                break
        assert block["effective"] == turn
        assert block["residual"] == residual
        assert block["turns"][-1] == {
            "turn": turn,
            "expected_operand": ex,
            "residual": residual,
        }
        assert block["effective"] < 9
        assert block["effective"] >= block["residual"] >= 2

    def test_empty_board_deck_degrades_to_printed(self, monkeypatch):
        monkeypatch.setattr(cc, "read_self_discount", lambda _rec: FLYER_POWER)
        block = effective_commander_cost(self.LORD, [ISLAND], library_size=99)
        assert block["status"] == STATUS_MODELLED
        assert block["effective"] == 9
        assert block["residual"] == 9
        assert len(block["turns"]) == 9

    def test_unmodelled_status_keeps_printed_and_reports(self, monkeypatch):
        monkeypatch.setattr(
            cc, "read_self_discount", lambda _rec: "unmodelled (ZoneCardCount)"
        )
        deck = self._deck_with_flyer_power(3, 10)
        block = effective_commander_cost(self.LORD, deck, library_size=99)
        assert block["status"] == "unmodelled (ZoneCardCount)"
        assert (block["effective"], block["residual"]) == (9, 9)
        assert block["operand"] is None
        assert block["turns"] == []

    def test_no_clause_keeps_printed(self, monkeypatch):
        monkeypatch.setattr(cc, "read_self_discount", lambda _rec: STATUS_NONE)
        block = effective_commander_cost(
            {"name": "Vanilla", "cmc": 4.0, "mana_cost": "{2}{G}{G}"},
            [],
            library_size=99,
        )
        assert block["status"] == STATUS_NONE
        assert block["effective"] == 4

    def test_never_below_pips_even_with_huge_board(self, monkeypatch):
        monkeypatch.setattr(cc, "read_self_discount", lambda _rec: FLYER_POWER)
        deck = [_creature("Huge", 0, 20, qty=40), ISLAND]
        block = effective_commander_cost(self.LORD, deck, library_size=99)
        assert block["residual"] == 2
        assert block["effective"] == 2
