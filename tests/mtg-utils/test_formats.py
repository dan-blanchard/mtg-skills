"""Tests for ``mtg_utils.formats`` — the one module that answers every format question.

Legality runs against REAL cards from the committed snapshot (``testkit.test_card``),
so the table-driven rules are proven on the record shape production reads, never on a
hand-built ``legalities`` dict that can drift from it. Statuses below were verified
against the MTGJSON bulk when the cards were added; a snapshot regen after a B&R
change re-pins them.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mtg_utils.formats import (
    COMMANDER_FORMATS,
    COMPETITIVE_BRAWL_BANNED,
    FORMATS,
    Format,
    Game,
    format_options,
    get_format,
    medium_is_digital,
)
from mtg_utils.testkit import test_card

HB = FORMATS["historic_brawl"]
CB = FORMATS["competitive_brawl"]
CMD = FORMATS["commander"]


# ---------- table ----------


class TestTable:
    def test_commander_family_is_every_format_with_a_command_zone(self):
        assert COMMANDER_FORMATS == (
            "commander",
            "brawl",
            "historic_brawl",
            "competitive_brawl",
        )
        for name in COMMANDER_FORMATS:
            assert FORMATS[name].has_commander
            assert FORMATS[name].is_singleton
            assert not FORMATS[name].is_constructed
        assert FORMATS["modern"].is_constructed

    def test_get_format_fails_loud(self):
        assert get_format("brawl") is FORMATS["brawl"]
        with pytest.raises(ValueError, match="Unknown format"):
            get_format("made_up_format")

    def test_competitive_brawl_table_row(self):
        assert CB.legality_key == "brawl"
        assert CB.ignores_legality_key_bans
        assert CB.banned_cards is COMPETITIVE_BRAWL_BANNED
        assert "oko, thief of crowns" in CB.banned_keys
        assert CB.is_arena_only
        assert CB.arena_pool
        assert not CB.free_mulligan
        assert FORMATS["brawl"].free_mulligan
        assert CB.multiplayer_life_total is None  # no multiplayer variant

    def test_arena_pool_is_exactly_the_arena_defined_legality_keys(self):
        gated = {f.name for f in FORMATS.values() if f.arena_pool}
        assert gated == {
            "brawl",
            "historic_brawl",
            "competitive_brawl",
            "alchemy",
            "historic",
            "timeless",
        }
        # Standard / Pioneer are Arena formats whose pool is defined in paper.
        assert FORMATS["standard"].is_arena
        assert not FORMATS["standard"].arena_pool

    def test_family_is_the_shape_rule_switch(self):
        # Every family decision reads ``family`` — never a format name.
        assert {f.family for f in FORMATS.values()} == {"commander", "constructed"}
        assert format_options(()) == []

    def test_medium_flags_must_agree(self):
        with pytest.raises(ValueError, match="is_arena_only requires is_arena"):
            replace(FORMATS["modern"], is_arena_only=True)
        with pytest.raises(ValueError, match="primary_medium"):
            replace(FORMATS["modern"], primary_medium="digital")
        for name in COMMANDER_FORMATS:
            assert FORMATS[name].family == "commander"
            assert FORMATS[name].size_is_minimum is False
        for name in ("standard", "modern", "vintage"):
            assert FORMATS[name].family == "constructed"
            assert FORMATS[name].has_commander is False
            assert FORMATS[name].max_copies == 4
            assert FORMATS[name].sideboard_size == 15
            # CR 100.2a sets only a minimum for constructed.
            assert FORMATS[name].size_is_minimum is True


# ---------- legality (real cards) ----------


class TestLegality:
    def test_key_banned_card_is_banned_in_historic_brawl_legal_in_competitive(self):
        # Mana Drain: `brawl` says banned; Competitive Brawl legalizes the key's bans.
        drain = test_card("Mana Drain")
        assert HB.legality(drain) == "banned"
        assert CB.legality(drain) == "legal"
        assert HB.is_legal(drain) is False
        assert CB.is_legal(drain) is True

    def test_own_ban_list_is_enforced_by_name(self):
        # Ragavan is legal under `brawl` but on Competitive Brawl's own ten-card list.
        ragavan = test_card("Ragavan, Nimble Pilferer")
        assert HB.legality(ragavan) == "legal"
        assert CB.legality(ragavan) == "banned"
        # Oko is banned under the key AND on the list — the list wins, still banned.
        assert CB.legality(test_card("Oko, Thief of Crowns")) == "banned"
        assert CMD.legality(test_card("Oko, Thief of Crowns")) == "legal"

    def test_restricted_and_banned_are_distinct_statuses(self):
        lotus = test_card("Black Lotus")
        assert FORMATS["vintage"].legality(lotus) == "restricted"
        assert FORMATS["vintage"].is_legal(lotus) is True
        assert CMD.legality(lotus) == "banned"
        assert HB.legality(lotus) == "not_legal"

    def test_not_legal_means_absent_from_the_pool_even_under_the_override(self):
        # Sol Ring isn't on Arena at all: not_legal under `brawl`, and Competitive
        # Brawl's ban override never promotes not_legal.
        ring = test_card("Sol Ring")
        assert HB.legality(ring) == "not_legal"
        assert CB.legality(ring) == "not_legal"
        assert CMD.legality(ring) == "legal"

    def test_unreleased_is_reported_only_with_the_oracle_set(self):
        ring = test_card("Sol Ring")
        assert HB.legality(ring) == "not_legal"
        pre = frozenset({ring["oracle_id"]})
        assert HB.legality(ring, unreleased=pre) == "unreleased"
        # Never widens a card that carries a real status.
        assert CMD.legality(ring, unreleased=pre) == "legal"
        lotus = test_card("Black Lotus")
        assert (
            CMD.legality(lotus, unreleased=frozenset({lotus["oracle_id"]})) == "banned"
        )
        # ``is_legal`` stays strict: pre-release is a widening callers opt into.
        assert HB.is_legal(ring, unreleased=pre) is False

    def test_arena_pool_gate_reads_oracle_level_availability(self):
        # A record the adapter marks as having NO Arena printing is not legal in an
        # Arena-pool format even when MTGJSON's key says legal; a paper-pool format
        # (Commander) ignores availability. No real card exercises this today — the
        # bulk has zero oracles that are `brawl`-legal without an Arena printing
        # (MTGJSON has cleaned up the pw24 Lord of Atlantis case the adapter's gate
        # was written for) — so the gate is proven on a real record with the field
        # flipped, and the no-evidence contract on a hand-built one.
        drain = test_card("Mana Drain")
        assert CB.legality(drain) == "legal"
        assert CB.legality({**drain, "arena_available": False}) == "not_legal"
        assert CMD.legality({**drain, "arena_available": False}) == "legal"
        no_evidence = {"name": "X", "legalities": {"brawl": "legal"}}
        assert HB.legality(no_evidence) == "legal"

    def test_ban_list_matches_folded_names(self):
        # The list holds canonical names; a record whose name differs only in case or
        # Unicode form (an Arena export, a printed_name alias) still matches.
        folded = {"name": "ragavan, nimble pilferer", "legalities": {}}
        assert CB.legality(folded) == "banned"
        assert CB.legality({"name": "Wrenn and Six", "legalities": {}}) == "banned"

    def test_unreleased_flag_form(self):
        # ``unreleased=True`` is the per-record form the hub's views use once the
        # caller has established the card is pre-release.
        ring = test_card("Sol Ring")
        assert HB.legality(ring, unreleased=True) == "unreleased"
        vehicle = {**ring, "type_line": "Legendary Artifact — Vehicle"}
        assert HB.commander_eligibility(vehicle, unreleased=True)["eligible"]

    def test_real_records_carry_the_availability_field(self):
        # The snapshot projection keeps ``arena_available`` so the gate is live on
        # real records, not only on hand-built ones.
        assert test_card("Sol Ring")["arena_available"] is False
        assert test_card("Mana Drain")["arena_available"] is True


# ---------- commander eligibility ----------


class TestCommanderEligibility:
    def test_legal_legend_is_eligible(self):
        thranduil = test_card("Thranduil, the Elvenking")
        assert HB.commander_eligibility(thranduil)["eligible"] is True
        assert CMD.commander_eligibility(thranduil)["eligible"] is True

    def test_planeswalker_rule_is_the_formats(self):
        chandra = test_card("Chandra, Torch of Defiance")
        # Brawl family: any legendary planeswalker; Commander needs the text.
        assert HB.commander_eligibility(chandra)["eligible"] is True
        assert CMD.commander_eligibility(chandra)["eligible"] is False

    def test_legality_gates_eligibility(self):
        # Chandra isn't Standard-legal, so she can't lead a (Standard) Brawl deck.
        chandra = test_card("Chandra, Torch of Defiance")
        assert FORMATS["brawl"].commander_eligibility(chandra)["eligible"] is False
        # A banned legend is never eligible, however legendary.
        assert (
            CB.commander_eligibility(test_card("Oko, Thief of Crowns"))["eligible"]
            is False
        )

    def test_no_command_zone_means_nothing_is_eligible(self):
        # Ragavan is Modern-legal and legendary; Modern has no commanders.
        ragavan = test_card("Ragavan, Nimble Pilferer")
        assert FORMATS["modern"].legality(ragavan) == "legal"
        assert FORMATS["modern"].commander_eligibility(ragavan) == {
            "eligible": False,
            "requires_partner": False,
        }

    def test_unreleased_legend_is_eligible_with_the_set(self):
        # Pre-release brewing: a spoiled legend reads not_legal everywhere until
        # release day; the widening admits exactly it.
        legend = {
            "name": "Spoiled Legend",
            "oracle_id": "oid-pre",
            "type_line": "Legendary Creature — Elf",
            "legalities": {"brawl": "not_legal"},
        }
        assert HB.commander_eligibility(legend)["eligible"] is False
        out = HB.commander_eligibility(legend, unreleased=frozenset({"oid-pre"}))
        assert out["eligible"] is True


# ---------- medium & size ----------


class TestMediumAndSize:
    def test_media_and_default(self):
        assert CMD.media == ("paper",)
        assert CMD.default_medium == "paper"
        assert HB.media == ("digital", "paper")
        assert HB.default_medium == "digital"
        assert CB.media == ("digital",)
        assert CB.default_medium == "digital"
        assert FORMATS["modern"].media == ("paper",)
        # Paper-defined formats Arena also hosts default to paper; the Arena-only
        # constructed formats never offer paper.
        for name in ("standard", "pioneer"):
            assert FORMATS[name].media == ("paper", "digital"), name
            assert FORMATS[name].default_medium == "paper", name
        for name in ("alchemy", "historic", "timeless"):
            assert FORMATS[name].media == ("digital",), name
            assert FORMATS[name].is_arena_only, name

    def test_resolve_medium_honours_only_allowed_overrides(self):
        assert HB.resolve_medium("paper") == "paper"
        assert HB.resolve_medium(None) == "digital"
        assert CMD.resolve_medium("digital") == "paper"  # commander is paper-only
        assert CB.resolve_medium("paper") == "digital"  # Arena-only

    def test_multiplayer_and_starting_life_follow_medium(self):
        # Arena is one-on-one for every format; a paper table is multiplayer iff the
        # format has a multiplayer variant, at that variant's life total.
        assert CMD.is_multiplayer("paper") is True
        assert CMD.starting_life("paper") == 40
        assert HB.is_multiplayer("digital") is False
        assert HB.starting_life("digital") == 25
        assert HB.is_multiplayer("paper") is True
        assert HB.starting_life("paper") == 30
        assert CB.is_multiplayer("digital") is False
        assert CB.starting_life("digital") == 25
        assert FORMATS["standard"].is_multiplayer("paper") is False
        assert FORMATS["standard"].starting_life("paper") == 20

    def test_game_resolves_life_table_and_commander_damage(self):
        # Commander damage is Commander's extra loss rule (CR 903.10a); Brawl games do
        # not use it in any medium (CR 903.12h).
        assert CMD.game("paper") == Game(
            medium="paper", life=40, multiplayer=True, commander_damage=True
        )
        assert HB.game("digital") == Game(
            medium="digital", life=25, multiplayer=False, commander_damage=False
        )
        assert HB.game("paper") == Game(
            medium="paper", life=30, multiplayer=True, commander_damage=False
        )
        assert CB.game(None).commander_damage is False
        # An override the format cannot honour resolves like resolve_medium.
        assert CMD.game("digital").medium == "paper"
        assert FORMATS["standard"].game("paper").life == 20

    def test_medium_is_digital_is_the_one_string_compare(self):
        assert medium_is_digital("digital") is True
        assert medium_is_digital("paper") is False

    def test_cost_mode_follows_medium(self):
        assert Format.cost_mode("digital") == "wildcards"
        assert Format.cost_mode("paper") == "usd"

    def test_paper_only_follows_the_medium_not_is_arena(self):
        # The search pool is the MEDIUM's: a paper Historic Brawl table buys paper
        # printings even though the format `is_arena`.
        assert HB.paper_only("paper") is True
        assert HB.paper_only("digital") is False
        assert HB.paper_only(None) is False  # defaults digital
        # An override the format cannot honour resolves first (Commander is paper).
        assert CMD.paper_only("digital") is True
        assert CMD.paper_only() is True

    def test_size_choices_only_paper_historic_brawl_may_choose(self):
        assert HB.size_choices("paper") == (60, 100)
        assert HB.size_choices("digital") == (100,)
        assert CMD.size_choices("paper") == (100,)
        assert FORMATS["brawl"].size_choices("digital") == (60,)

    def test_resolve_deck_size_override_lies_dormant_unless_choosable(self):
        assert HB.resolve_deck_size(60, "paper") == 60
        assert HB.resolve_deck_size(60, "digital") == 100
        assert HB.resolve_deck_size(None, "paper") == 100
        assert CMD.resolve_deck_size(60, "paper") == 100
        # Constructed sizes are minimums, not a choice list: any valid size holds.
        assert FORMATS["standard"].resolve_deck_size(80, "paper") == 80
        assert CMD.resolve_deck_size(80, "paper") == 100  # exact-size family
        assert FORMATS["standard"].resolve_deck_size(0, "paper") == 60
        assert FORMATS["standard"].resolve_deck_size(None, "digital") == 60

    def test_size_rule_citations(self):
        for name in COMMANDER_FORMATS:
            assert FORMATS[name].size_rule, name
        assert FORMATS["brawl"].size_rule == "CR 903.12d"
        assert CB.size_rule == "CR 903.5a"
        assert FORMATS["standard"].size_rule is None


# ---------- for_deck ----------


class TestForDeck:
    def test_defaults_to_commander(self):
        assert Format.for_deck({}) is CMD

    def test_applies_a_legal_explicit_size(self):
        fmt = Format.for_deck({"format": "historic_brawl", "deck_size": 60})
        assert fmt.deck_size == 60
        assert fmt.name == "historic_brawl"
        # Everything else is the table's row.
        assert fmt.legality_key == "brawl"
        assert Format.for_deck({"format": "historic_brawl", "deck_size": 100}) is HB

    def test_all_size_choices_spans_every_medium(self):
        assert HB.all_size_choices == (60, 100)
        assert CMD.all_size_choices == (100,)
        assert FORMATS["brawl"].all_size_choices == (60,)

    def test_commander_family_rejects_an_impossible_size(self):
        with pytest.raises(ValueError, match="deck_size 73 is not legal for commander"):
            Format.for_deck({"format": "commander", "deck_size": 73})
        with pytest.raises(ValueError, match="expected \\[60, 100\\]"):
            Format.for_deck({"format": "historic_brawl", "deck_size": 99})

    def test_constructed_accepts_any_size(self):
        # An 80-card Yorion deck and a 40-card limited pool both label themselves
        # with the constructed format whose legality they borrow.
        assert Format.for_deck({"format": "standard", "deck_size": 80}).deck_size == 80
        assert Format.for_deck({"format": "timeless", "deck_size": 40}).deck_size == 40

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown format"):
            Format.for_deck({"format": "made_up_format"})

    def test_values_are_frozen(self):
        with pytest.raises(AttributeError):
            CMD.deck_size = 99  # type: ignore[misc]
        assert replace(CMD, deck_size=99).deck_size == 99
        assert CMD.deck_size == 100


# ---------- SPA table ----------


class TestSpaTable:
    def test_format_options_is_every_format_in_table_order(self):
        rows = format_options()
        assert [r["id"] for r in rows] == list(FORMATS)
        assert [r["id"] for r in format_options(COMMANDER_FORMATS)] == list(
            COMMANDER_FORMATS
        )
        by_id = {r["id"]: r for r in rows}
        assert by_id["commander"] == {
            "id": "commander",
            "label": "Commander",
            "family": "commander",
            "has_commander": True,
            "max_copies": 1,
            "sideboard_size": 0,
            "size_is_minimum": False,
            "media": ["paper"],
            "medium_labels": {"paper": "Paper"},
            "default_medium": "paper",
            "deck_size": 100,
            "size_choices": {"paper": [100]},
        }
        assert by_id["historic_brawl"]["size_choices"] == {
            "digital": [100],
            "paper": [60, 100],
        }
        assert by_id["competitive_brawl"]["media"] == ["digital"]
        # The family facts the SPA keys its zones, stepper and pills off.
        modern = by_id["modern"]
        assert modern["family"] == "constructed"
        assert modern["has_commander"] is False
        assert modern["max_copies"] == 4
        assert modern["sideboard_size"] == 15
        assert modern["size_is_minimum"] is True
        assert modern["media"] == ["paper"]
        assert by_id["standard"]["media"] == ["paper", "digital"]
        assert by_id["alchemy"]["media"] == ["digital"]
