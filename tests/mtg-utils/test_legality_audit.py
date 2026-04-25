"""Tests for legality_audit: format legality, color identity, singleton rule."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from conftest import json_from_cli_output

from mtg_utils.legality_audit import (
    check_color_identity,
    check_copy_limits,
    check_format_legality,
    legality_audit,
    main,
)

# ---------- Card fixtures ----------


def card(
    name: str,
    *,
    type_line: str = "Instant",
    color_identity: list[str] | None = None,
    brawl: str = "legal",
    commander: str = "legal",
    standardbrawl: str = "legal",
    oracle_text: str = "",
) -> dict:
    return {
        "name": name,
        "type_line": type_line,
        "color_identity": color_identity or [],
        "oracle_text": oracle_text,
        "legalities": {
            "brawl": brawl,
            "commander": commander,
            "standardbrawl": standardbrawl,
        },
    }


def basic(name: str, color: str) -> dict:
    return card(
        name,
        type_line=f"Basic Land — {name}",
        color_identity=[color] if color != "C" else [],
    )


def deck(
    format: str = "historic_brawl",  # noqa: A002
    commanders: list[str] | None = None,
    cards: list[tuple[str, int]] | None = None,
    deck_size: int | None = None,
) -> dict:
    commanders = commanders or ["Jinnie Fay, Jetmir's Second"]
    cards = cards or []
    total = len(commanders) + sum(q for _, q in cards)
    return {
        "format": format,
        "deck_size": deck_size if deck_size is not None else total,
        "commanders": [{"name": n, "quantity": 1} for n in commanders],
        "cards": [{"name": n, "quantity": q} for n, q in cards],
        "total_cards": total,
    }


def jinnie() -> dict:
    return card(
        "Jinnie Fay, Jetmir's Second",
        type_line="Legendary Creature — Elf Druid",
        color_identity=["G", "R", "W"],
    )


# ---------- Format legality checks ----------


class TestFormatLegality:
    def test_all_legal(self):
        hydrated = [jinnie(), card("Swords to Plowshares", color_identity=["W"])]
        violations = check_format_legality(hydrated, "brawl")
        assert violations == []

    def test_banned_card(self):
        hydrated = [jinnie(), card("Sol Ring", brawl="not_legal")]
        violations = check_format_legality(hydrated, "brawl")
        assert len(violations) == 1
        assert violations[0]["name"] == "Sol Ring"
        assert violations[0]["legality"] == "not_legal"

    def test_banned_commander(self):
        # A commander banned in-format should be reported like any other card.
        bad_cmd = card(
            "Golos, Tireless Pilgrim",
            type_line="Legendary Creature — Scout",
            brawl="banned",
        )
        violations = check_format_legality([bad_cmd], "brawl")
        assert len(violations) == 1
        assert violations[0]["name"] == "Golos, Tireless Pilgrim"
        assert violations[0]["legality"] == "banned"

    def test_restricted_counts_as_legal(self):
        # Codebase convention: "restricted" passes the legality filter.
        hydrated = [card("Some Card", brawl="restricted")]
        violations = check_format_legality(hydrated, "brawl")
        assert violations == []

    def test_commander_format_uses_commander_key(self):
        # Sol Ring is legal in Commander, not legal in Brawl.
        hydrated = [card("Sol Ring", brawl="not_legal", commander="legal")]
        assert check_format_legality(hydrated, "commander") == []
        assert len(check_format_legality(hydrated, "brawl")) == 1


# ---------- Color identity checks ----------


class TestColorIdentity:
    def test_all_in_identity(self):
        hydrated = [
            jinnie(),
            card("Lightning Bolt", color_identity=["R"]),
            card("Swords to Plowshares", color_identity=["W"]),
            card("Llanowar Elves", color_identity=["G"]),
        ]
        d = deck(
            cards=[
                ("Lightning Bolt", 1),
                ("Swords to Plowshares", 1),
                ("Llanowar Elves", 1),
            ]
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert violations == []

    def test_off_identity_card(self):
        hydrated = [
            jinnie(),
            card("Counterspell", color_identity=["U"]),
        ]
        d = deck(cards=[("Counterspell", 1)])
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert len(violations) == 1
        assert violations[0]["name"] == "Counterspell"
        assert violations[0]["card_identity"] == ["U"]
        assert sorted(violations[0]["commander_identity"]) == ["G", "R", "W"]

    def test_multi_color_off_identity_reports_full_identity(self):
        hydrated = [
            jinnie(),
            card("Thornwood Falls", type_line="Land", color_identity=["G", "U"]),
        ]
        d = deck(cards=[("Thornwood Falls", 1)])
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert len(violations) == 1
        assert sorted(violations[0]["card_identity"]) == ["G", "U"]

    def test_partner_commanders_combined_identity(self):
        cmd1 = card(
            "Akiri, Line-Slinger",
            type_line="Legendary Creature — Kor Soldier",
            color_identity=["R", "W"],
            oracle_text="Partner",
        )
        cmd2 = card(
            "Silas Renn, Seeker Adept",
            type_line="Legendary Creature — Human Artificer",
            color_identity=["U", "B"],
            oracle_text="Partner",
        )
        hydrated = [cmd1, cmd2, card("Dimir Charm", color_identity=["U", "B"])]
        d = deck(
            commanders=["Akiri, Line-Slinger", "Silas Renn, Seeker Adept"],
            cards=[("Dimir Charm", 1)],
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert violations == []

    def test_wastes_in_colorless_commander(self):
        cmd = card(
            "Kozilek, the Great Distortion",
            type_line="Legendary Creature — Eldrazi",
            color_identity=[],
        )
        wastes = card("Wastes", type_line="Basic Land — Wastes", color_identity=[])
        hydrated = [cmd, wastes]
        d = deck(
            format="commander",
            commanders=["Kozilek, the Great Distortion"],
            cards=[("Wastes", 5)],
        )
        # Commander format: colorless_any_basic=False. Wastes has empty CI so no exemption needed.
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert violations == []

    def test_colorless_brawl_one_basic_type_allowed(self):
        cmd = card(
            "Karn, Living Legacy",
            type_line="Legendary Planeswalker — Karn",
            color_identity=[],
        )
        hydrated = [cmd, basic("Plains", "W")]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 30)],
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": True})
        assert violations == []

    def test_colorless_brawl_mixed_basics_all_flagged(self):
        cmd = card(
            "Karn, Living Legacy",
            type_line="Legendary Planeswalker — Karn",
            color_identity=[],
        )
        hydrated = [cmd, basic("Plains", "W"), basic("Forest", "G")]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 15), ("Forest", 15)],
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": True})
        assert len(violations) == 2
        reasons = {v["reason"] for v in violations}
        assert reasons == {"colorless_deck_must_pick_one_basic_type"}
        names = sorted(v["name"] for v in violations)
        assert names == ["Forest", "Plains"]

    def test_colorless_commander_rejects_plains(self):
        cmd = card(
            "Kozilek, the Great Distortion",
            type_line="Legendary Creature — Eldrazi",
            color_identity=[],
        )
        hydrated = [cmd, basic("Plains", "W")]
        d = deck(
            format="commander",
            commanders=["Kozilek, the Great Distortion"],
            cards=[("Plains", 5)],
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": False})
        assert len(violations) == 1
        assert violations[0]["name"] == "Plains"

    def test_colorless_brawl_single_basic_plus_wastes(self):
        # Wastes (empty CI) is always allowed alongside the chosen exempt basic.
        cmd = card(
            "Karn, Living Legacy",
            type_line="Legendary Planeswalker — Karn",
            color_identity=[],
        )
        hydrated = [
            cmd,
            basic("Plains", "W"),
            card("Wastes", type_line="Basic Land — Wastes", color_identity=[]),
        ]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 20), ("Wastes", 10)],
        )
        violations = check_color_identity(d, hydrated, {"colorless_any_basic": True})
        assert violations == []


# ---------- Commander-zone check ----------


class TestCommanderZone:
    """Empty ``commanders`` for a commander-format deck must surface ONE
    clean violation, not cascade through every R/W card in the mainboard.

    Regression: when set-commander silently failed to write the file,
    the deck JSON had ``commanders: []`` but kept the would-be commander
    in ``cards``. The legacy ``check_color_identity`` derived an empty
    commander identity, then declared every non-colorless card a
    "not_in_C" violation — listing the would-be commander FIRST and
    making it look like a 42-error cascade was about an illegal
    commander. The targeted ``check_commander_zone`` runs first and
    suppresses the color-identity cascade so the user sees the real
    cause: "no commander selected".
    """

    def test_empty_commanders_emits_single_clear_violation(self):
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [],
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Swords to Plowshares", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        hydrated = [
            {
                "name": "Lightning Bolt",
                "color_identity": ["R"],
                "legalities": {"commander": "legal"},
            },
            {
                "name": "Swords to Plowshares",
                "color_identity": ["W"],
                "legalities": {"commander": "legal"},
            },
            {
                "name": "Sol Ring",
                "color_identity": [],
                "legalities": {"commander": "legal"},
            },
        ]

        result = legality_audit(deck, hydrated)
        # Should report ONE clean error pointing at the commander zone,
        # not three "X not in C" cascading color-identity errors that
        # blame the deck's mainboard cards.
        assert result["counts"]["commander_zone"] == 1
        assert result["counts"]["color_identity"] == 0
        zone = result["violations"]["commander_zone"][0]
        assert zone["reason"] == "no_commander_selected"

    def test_populated_commanders_passes_zone_check(self):
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [{"name": "Krenko, Mob Boss", "quantity": 1}],
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Krenko, Mob Boss",
                "color_identity": ["R"],
                "legalities": {"commander": "legal"},
                "type_line": "Legendary Creature — Goblin Warrior",
            },
            {
                "name": "Lightning Bolt",
                "color_identity": ["R"],
                "legalities": {"commander": "legal"},
            },
        ]

        result = legality_audit(deck, hydrated)
        assert result["counts"]["commander_zone"] == 0

    def test_non_commander_format_skips_zone_check(self):
        """60-card constructed has no commander zone — check is a no-op."""
        deck = {
            "format": "modern",
            "deck_size": 60,
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        hydrated = [
            {
                "name": "Lightning Bolt",
                "color_identity": ["R"],
                "legalities": {"modern": "legal"},
            }
        ]
        result = legality_audit(deck, hydrated)
        assert result["counts"].get("commander_zone", 0) == 0

    def test_unresolvable_commander_name_flagged(self):
        """A typo'd commander name should produce a clear typo-targeted error.

        Without this check, the same cascading "X not in C" misdiagnosis
        from the empty-commanders case fires verbatim — because
        ``_commander_color_identity`` returns an empty set when the name
        doesn't resolve in hydrated, identical to the empty-list state.
        """
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [{"name": "Alibou, Ancient Whitnesss", "quantity": 1}],
            "cards": [
                {"name": "Lightning Bolt", "quantity": 1},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        hydrated = [
            {
                "name": "Lightning Bolt",
                "color_identity": ["R"],
                "legalities": {"commander": "legal"},
            },
            {
                "name": "Sol Ring",
                "color_identity": [],
                "legalities": {"commander": "legal"},
            },
        ]

        result = legality_audit(deck, hydrated)
        assert result["counts"]["commander_zone"] == 1
        # Color-identity cascade is suppressed — no spurious "X not in C".
        assert result["counts"]["color_identity"] == 0
        zone = result["violations"]["commander_zone"][0]
        assert zone["reason"] == "commander_not_in_hydrated"
        # Payload must name the unresolvable card so the user can fix it.
        assert "Alibou, Ancient Whitnesss" in zone.get("unresolved_names", [])

    def test_partner_with_one_typo_flags_whole_zone(self):
        """Strict mode: any unresolvable commander entry flags the zone.

        Partial resolution would shift the cascading misdiagnosis from
        "every R/W card" to "every white card" — same bug class, different
        color. Strict scope forces the user to fix the typo before any
        downstream check produces meaningful output.
        """
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [
                {"name": "Thrasios, Triton Hero", "quantity": 1},
                {"name": "Tymna teh Weeaver", "quantity": 1},
            ],
            "cards": [{"name": "Lightning Bolt", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Thrasios, Triton Hero",
                "color_identity": ["G", "U"],
                "legalities": {"commander": "legal"},
                "type_line": "Legendary Creature — Merfolk Wizard",
            },
            {
                "name": "Lightning Bolt",
                "color_identity": ["R"],
                "legalities": {"commander": "legal"},
            },
        ]

        result = legality_audit(deck, hydrated)
        assert result["counts"]["commander_zone"] == 1
        assert result["counts"]["color_identity"] == 0
        zone = result["violations"]["commander_zone"][0]
        assert zone["reason"] == "commander_not_in_hydrated"
        assert "Tymna teh Weeaver" in zone.get("unresolved_names", [])
        # The resolved name should NOT appear in the unresolved list.
        assert "Thrasios, Triton Hero" not in zone.get("unresolved_names", [])

    def test_colorless_commander_does_not_false_positive(self):
        """A legitimate colorless commander (Kozilek) resolves with empty
        color_identity. The check must distinguish "name doesn't resolve"
        from "name resolves but identity is empty"; only the former is
        flagged.
        """
        deck = {
            "format": "commander",
            "deck_size": 100,
            "commanders": [{"name": "Kozilek, Butcher of Truth", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        hydrated = [
            {
                "name": "Kozilek, Butcher of Truth",
                "color_identity": [],
                "legalities": {"commander": "legal"},
                "type_line": "Legendary Creature — Eldrazi",
            },
            {
                "name": "Sol Ring",
                "color_identity": [],
                "legalities": {"commander": "legal"},
            },
        ]
        result = legality_audit(deck, hydrated)
        assert result["counts"]["commander_zone"] == 0


# ---------- Copy limit checks ----------

_SINGLETON_CONFIG = {"max_copies": 1, "legality_key": "commander"}
_CONSTRUCTED_CONFIG = {"max_copies": 4, "legality_key": "pioneer"}


class TestCopyLimits:
    def _hyd_index(self, hydrated: list[dict]) -> dict:
        return {c["name"]: c for c in hydrated}

    def test_normal_singleton_violation(self):
        hydrated = [card("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 2)])
        v = check_copy_limits(d, self._hyd_index(hydrated), _SINGLETON_CONFIG)
        assert len(v) == 1
        assert v[0]["name"] == "Lightning Bolt"
        assert v[0]["quantity"] == 2
        assert v[0]["limit"] == 1
        assert v[0]["reason"] == "copy_limit"

    def test_basic_land_allowed(self):
        hydrated = [basic("Forest", "G")]
        d = deck(cards=[("Forest", 40)])
        assert check_copy_limits(d, self._hyd_index(hydrated), _SINGLETON_CONFIG) == []

    def test_any_number_exemption(self):
        hare = card(
            "Hare Apparent",
            type_line="Creature — Rabbit",
            color_identity=["W"],
            oracle_text=(
                "A deck can have any number of cards named Hare Apparent.\n"
                "When Hare Apparent enters, create a 1/1 white Rabbit creature token."
            ),
        )
        d = deck(cards=[("Hare Apparent", 40)])
        assert check_copy_limits(d, self._hyd_index([hare]), _SINGLETON_CONFIG) == []

    def test_up_to_n_at_cap(self):
        dwarves = card(
            "Seven Dwarves",
            type_line="Creature — Dwarf",
            color_identity=["R"],
            oracle_text=(
                "A deck can have up to seven cards named Seven Dwarves.\n"
                "Seven Dwarves gets +1/+1 for each other Dwarf named Seven Dwarves you control."
            ),
        )
        d = deck(cards=[("Seven Dwarves", 7)])
        assert check_copy_limits(d, self._hyd_index([dwarves]), _SINGLETON_CONFIG) == []

    def test_up_to_n_over_cap(self):
        dwarves = card(
            "Seven Dwarves",
            type_line="Creature — Dwarf",
            color_identity=["R"],
            oracle_text="A deck can have up to seven cards named Seven Dwarves.",
        )
        d = deck(cards=[("Seven Dwarves", 8)])
        v = check_copy_limits(d, self._hyd_index([dwarves]), _SINGLETON_CONFIG)
        assert len(v) == 1
        assert v[0]["name"] == "Seven Dwarves"
        assert v[0]["quantity"] == 8
        assert v[0]["limit"] == 7
        assert v[0]["reason"] == "exceeds_named_card_cap"

    def test_nazgul_nine(self):
        nazgul = card(
            "Nazgûl",
            type_line="Creature — Wraith",
            color_identity=["B"],
            oracle_text="A deck can have up to nine cards named Nazgûl.",
        )
        d = deck(cards=[("Nazgûl", 9)])
        assert check_copy_limits(d, self._hyd_index([nazgul]), _SINGLETON_CONFIG) == []

    def test_constructed_4_of_allowed(self):
        hydrated = [card("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 4)])
        d["format"] = "pioneer"
        assert (
            check_copy_limits(d, self._hyd_index(hydrated), _CONSTRUCTED_CONFIG) == []
        )

    def test_constructed_5_of_violation(self):
        hydrated = [card("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 5)])
        d["format"] = "pioneer"
        v = check_copy_limits(d, self._hyd_index(hydrated), _CONSTRUCTED_CONFIG)
        assert len(v) == 1
        assert v[0]["limit"] == 4

    def test_constructed_main_plus_sideboard_combined(self):
        hydrated = [card("Lightning Bolt")]
        d = {
            "format": "pioneer",
            "cards": [{"name": "Lightning Bolt", "quantity": 3}],
            "sideboard": [{"name": "Lightning Bolt", "quantity": 2}],
        }
        v = check_copy_limits(d, self._hyd_index(hydrated), _CONSTRUCTED_CONFIG)
        assert len(v) == 1
        assert v[0]["quantity"] == 5
        assert v[0]["limit"] == 4

    def test_vintage_restricted_capped_at_1(self):
        restricted_card = card("Ancestral Recall")
        restricted_card["legalities"]["vintage"] = "restricted"
        hydrated = [restricted_card]
        d = {
            "format": "vintage",
            "cards": [{"name": "Ancestral Recall", "quantity": 2}],
        }
        v = check_copy_limits(
            d,
            self._hyd_index(hydrated),
            {"max_copies": 4, "legality_key": "vintage"},
        )
        assert len(v) == 1
        assert v[0]["limit"] == 1
        assert v[0]["reason"] == "restricted"


# ---------- Top-level audit ----------


class TestLegalityAudit:
    def test_clean_deck_passes(self):
        hydrated = [
            jinnie(),
            card("Swords to Plowshares", color_identity=["W"]),
            basic("Forest", "G"),
        ]
        d = deck(cards=[("Swords to Plowshares", 1), ("Forest", 30)])
        result = legality_audit(d, hydrated)
        assert result["overall_status"] == "PASS"
        assert result["format"] == "historic_brawl"
        assert result["counts"]["format_legality"] == 0
        assert result["counts"]["color_identity"] == 0
        assert result["counts"]["copy_limits"] == 0

    def test_multi_violation_deck_fails(self):
        hydrated = [
            jinnie(),
            card("Sol Ring", brawl="not_legal"),  # banned
            card("Counterspell", color_identity=["U"]),  # off-identity
            card("Lightning Bolt", color_identity=["R"]),
        ]
        d = deck(
            cards=[
                ("Sol Ring", 1),
                ("Counterspell", 1),
                ("Lightning Bolt", 2),  # singleton violation
            ],
        )
        result = legality_audit(d, hydrated)
        assert result["overall_status"] == "FAIL"
        assert result["counts"]["format_legality"] == 1
        assert result["counts"]["color_identity"] == 1
        assert result["counts"]["copy_limits"] == 1

    def test_unknown_format_raises(self):
        hydrated = [jinnie()]
        d = deck(format="made_up_format")
        import pytest

        with pytest.raises(ValueError, match="Unknown format"):
            legality_audit(d, hydrated)


# ---------- CLI smoke tests ----------


class TestCLI:
    def _write(
        self, tmp_path: Path, deck_data: dict, hydrated_data: list[dict]
    ) -> tuple[Path, Path]:
        deck_path = tmp_path / "deck.json"
        hydrated_path = tmp_path / "hydrated.json"
        deck_path.write_text(json.dumps(deck_data))
        hydrated_path.write_text(json.dumps(hydrated_data))
        return deck_path, hydrated_path

    def test_cli_pass(self, tmp_path: Path):
        hydrated = [jinnie(), card("Swords to Plowshares", color_identity=["W"])]
        d = deck(cards=[("Swords to Plowshares", 1)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0
        assert "PASS" in result.output
        data = json_from_cli_output(result)
        assert data["overall_status"] == "PASS"

    def test_cli_fail(self, tmp_path: Path):
        hydrated = [jinnie(), card("Sol Ring", brawl="not_legal")]
        d = deck(cards=[("Sol Ring", 1)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0  # data producer convention
        assert "FAIL" in result.output
        assert "Sol Ring" in result.output
        data = json_from_cli_output(result)
        assert data["overall_status"] == "FAIL"
        assert data["counts"]["format_legality"] == 1

    def test_cli_output_override(self, tmp_path: Path):
        hydrated = [jinnie()]
        d = deck()
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)
        custom_output = tmp_path / "custom.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(deck_path), str(hydrated_path), "--output", str(custom_output)],
        )
        assert result.exit_code == 0
        assert custom_output.exists()
        data = json.loads(custom_output.read_text())
        assert data["overall_status"] == "PASS"


class TestCiteRules:
    """``--cite-rules`` attaches CR citations keyed on violation reason."""

    _CR_FIXTURE = (
        "Magic: The Gathering Comprehensive Rules\n\n"
        "These rules are effective as of February 2, 2024\n\n"
        "Contents\n\n"
        "1. Game Concepts\n"
        "100. General\n"
        "9. Casual Variants\n"
        "903. Commander\n"
        "Glossary\n"
        "Credits\n\n"
        "1. Game Concepts\n\n"
        "100. General\n\n"
        "100.2. In constructed play, each deck has a minimum deck size of 60 cards.\n\n"
        "100.2a Constructed copy limit.\n\n"
        "9. Casual Variants\n\n"
        "903. Commander\n\n"
        "903.4. Commander color identity is defined here.\n\n"
        "903.5b Commander singleton rule.\n\n"
        "Glossary\n\n"
        "Credits\n"
    )

    def _write(self, tmp_path, deck_data, hydrated_data):
        deck_path = tmp_path / "deck.json"
        hydrated_path = tmp_path / "hydrated.json"
        deck_path.write_text(json.dumps(deck_data))
        hydrated_path.write_text(json.dumps(hydrated_data))
        return deck_path, hydrated_path

    def _write_rules(self, tmp_path):
        p = tmp_path / "comprehensive-rules-20240202.txt"
        p.write_text(self._CR_FIXTURE, encoding="utf-8")
        return p

    def test_copy_limit_violation_cited(self, tmp_path: Path):
        # Historic Brawl singleton — two copies of Sol Ring triggers a
        # copy_limit violation whose reason should cite 100.2a / 903.5b.
        rules_path = self._write_rules(tmp_path)
        hydrated = [jinnie(), card("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                str(hydrated_path),
                "--cite-rules",
                "--rules-file",
                str(rules_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        citations = data.get("rule_citations") or {}
        copy_citations = citations.get("copy_limits") or []
        cited_rules = {c["rule"] for c in copy_citations}
        assert {"100.2a", "903.5b"} & cited_rules

    def test_missing_rules_file_is_soft_error(self, tmp_path: Path):
        hydrated = [jinnie()]
        d = deck()
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)
        missing = tmp_path / "nope.txt"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                str(hydrated_path),
                "--cite-rules",
                "--rules-file",
                str(missing),
            ],
        )
        # Still exits 0 — CLI contract preserved.
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        assert "rule_citations_error" in data

    def test_cite_rules_default_on_finds_cr_next_to_deck(self, tmp_path: Path):
        """Regression pin for session 0a340f10: default --cite-rules
        must auto-find the CR in the directory containing the deck
        JSON, without --rules-file. Previously, ``uv run --directory
        <skill>`` rebased cwd and the default search missed the CR."""
        rules_path = self._write_rules(tmp_path)
        assert rules_path.parent == tmp_path
        hydrated = [jinnie(), card("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        # No --cite-rules (default-on), no --rules-file (input-dir search).
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        citations = data.get("rule_citations") or {}
        assert citations, "default-on should attach citations"
        assert "rule_citations_error" not in data

    def test_no_cite_rules_opts_out(self, tmp_path: Path):
        """--no-cite-rules skips citation attachment even with a
        reachable CR."""
        self._write_rules(tmp_path)
        hydrated = [jinnie(), card("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), str(hydrated_path), "--no-cite-rules"]
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        assert "rule_citations" not in data
        assert "rule_citations_error" not in data

    def test_warn_on_missing_cr_surfaces_in_stdout(self, tmp_path: Path):
        """Default-on citation lookup with no reachable CR must print a
        WARN line to stdout (not only to the JSON sidecar)."""
        hydrated = [jinnie()]
        d = deck()
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(hydrated_path)])
        assert result.exit_code == 0, result.output
        assert "WARN: rule_citations not attached" in result.output
