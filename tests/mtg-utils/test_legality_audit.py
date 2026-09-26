"""Tests for legality_audit: format legality, color identity, singleton rule."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from click.testing import CliRunner
from conftest import json_from_cli_output

from mtg_utils.formats import FORMATS
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.legality_audit import (
    check_color_identity,
    check_copy_limits,
    check_format_legality,
    legality_audit,
    main,
)
from mtg_utils.testkit import test_card


def _hd(deck, hydrated):
    return HydratedDeck.from_parsed(deck, records=hydrated)


# ---------- Card fixtures ----------


def _real(name: str, **per_printing) -> dict:
    """The real card *name* from the testkit snapshot (ADR-0056) — its real
    type line, color identity, oracle text and legalities — with only
    per-printing facts overlaid."""
    return {**test_card(name), **per_printing}


def card(name: str, *, brawl: str = "legal") -> dict:
    """A fictional machinery record: only a name and a ``brawl`` legality."""
    return {
        "name": name,
        "type_line": "Instant",
        "color_identity": [],
        "oracle_text": "",
        "legalities": {"brawl": brawl, "commander": "legal", "standardbrawl": "legal"},
    }


def deck(
    format: str = "historic_brawl",  # noqa: A002
    commanders: list[str] | None = None,
    cards: list[tuple[str, int]] | None = None,
    deck_size: int | None = None,
) -> dict:
    commanders = commanders or ["Jinnie Fay, Jetmir's Second"]
    cards = list(cards or [])
    total = len(commanders) + sum(q for _, q in cards)
    # An honest deck: pad to the format's size with Wastes, which stay UN-hydrated —
    # every check walks hydrated records (or skips a name it can't resolve) and the
    # colorless-basic rule ignores Wastes, so the padding is invisible to the checks
    # while ``Format.for_deck`` (which rejects a Commander-family deck declaring an
    # impossible size) sees a real 100-card deck.
    fmt = FORMATS.get(format)
    if deck_size is None:
        deck_size = fmt.deck_size if fmt is not None else total
    if deck_size > total:
        cards.append(("Wastes", deck_size - total))
        total = deck_size
    return {
        "format": format,
        "deck_size": deck_size,
        "commanders": [{"name": n, "quantity": 1} for n in commanders],
        "cards": [{"name": n, "quantity": q} for n, q in cards],
        "total_cards": total,
    }


def jinnie() -> dict:
    return _real("Jinnie Fay, Jetmir's Second")


def bulk_for_cli(records: list[dict]) -> list[dict]:
    """*records* as a CLI test's ``--bulk-data`` file, plus the Wastes that
    :func:`deck` pads with: the in-memory checks skip the un-hydrated padding, but a
    CLI acquires every name the deck lists, and a name the file lacks would fall
    back to Scryfall's API (tests make no network calls)."""
    if any(r.get("name") == "Wastes" for r in records):
        return records
    return [*records, _real("Wastes")]


# ---------- Format legality checks ----------


class TestFormatLegality:
    def test_all_legal(self):
        hydrated = [jinnie(), _real("Swords to Plowshares")]
        violations = check_format_legality(hydrated, FORMATS["historic_brawl"])
        assert violations == []

    def test_banned_card(self):
        hydrated = [jinnie(), _real("Sol Ring")]  # not on Arena: brawl not_legal
        violations = check_format_legality(hydrated, FORMATS["historic_brawl"])
        assert len(violations) == 1
        assert violations[0]["name"] == "Sol Ring"
        assert violations[0]["legality"] == "not_legal"

    def test_banned_commander(self):
        # A commander banned in-format should be reported like any other card.
        bad_cmd = _real("Iona, Shield of Emeria")  # banned under the brawl key
        violations = check_format_legality([bad_cmd], FORMATS["historic_brawl"])
        assert len(violations) == 1
        assert violations[0]["name"] == "Iona, Shield of Emeria"
        assert violations[0]["legality"] == "banned"

    def test_restricted_counts_as_legal(self):
        # Codebase convention: "restricted" passes the legality filter.
        hydrated = [card("Some Card", brawl="restricted")]
        violations = check_format_legality(hydrated, FORMATS["historic_brawl"])
        assert violations == []

    def test_commander_format_uses_commander_key(self):
        # Sol Ring is legal in Commander, not legal in Brawl.
        hydrated = [_real("Sol Ring")]
        assert check_format_legality(hydrated, FORMATS["commander"]) == []
        assert len(check_format_legality(hydrated, FORMATS["historic_brawl"])) == 1


# ---------- Color identity checks ----------


class TestColorIdentity:
    def test_all_in_identity(self):
        hydrated = [
            jinnie(),
            _real("Lightning Bolt"),
            _real("Swords to Plowshares"),
            _real("Llanowar Elves"),
        ]
        d = deck(
            cards=[
                ("Lightning Bolt", 1),
                ("Swords to Plowshares", 1),
                ("Llanowar Elves", 1),
            ]
        )
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert violations == []

    def test_off_identity_card(self):
        hydrated = [
            jinnie(),
            _real("Counterspell"),
        ]
        d = deck(cards=[("Counterspell", 1)])
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert len(violations) == 1
        assert violations[0]["name"] == "Counterspell"
        assert violations[0]["card_identity"] == ["U"]
        assert sorted(violations[0]["commander_identity"]) == ["G", "R", "W"]

    def test_multi_color_off_identity_reports_full_identity(self):
        hydrated = [
            jinnie(),
            _real("Thornwood Falls"),
        ]
        d = deck(cards=[("Thornwood Falls", 1)])
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert len(violations) == 1
        assert sorted(violations[0]["card_identity"]) == ["G", "U"]

    def test_partner_commanders_combined_identity(self):
        cmd1 = _real("Akiri, Line-Slinger")
        cmd2 = _real("Silas Renn, Seeker Adept")
        hydrated = [cmd1, cmd2, _real("Dimir Charm")]
        d = deck(
            commanders=["Akiri, Line-Slinger", "Silas Renn, Seeker Adept"],
            cards=[("Dimir Charm", 1)],
        )
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert violations == []

    def test_wastes_in_colorless_commander(self):
        cmd = _real("Kozilek, the Great Distortion")
        wastes = _real("Wastes")
        hydrated = [cmd, wastes]
        d = deck(
            format="commander",
            commanders=["Kozilek, the Great Distortion"],
            cards=[("Wastes", 5)],
        )
        # Commander format: colorless_any_basic=False. Wastes has empty CI so no exemption needed.
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert violations == []

    def test_colorless_brawl_one_basic_type_allowed(self):
        cmd = _real("Karn, Living Legacy")
        hydrated = [cmd, _real("Plains")]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 30)],
        )
        violations = check_color_identity(d, hydrated, FORMATS["historic_brawl"])
        assert violations == []

    def test_colorless_brawl_mixed_basics_all_flagged(self):
        cmd = _real("Karn, Living Legacy")
        hydrated = [cmd, _real("Plains"), _real("Forest")]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 15), ("Forest", 15)],
        )
        violations = check_color_identity(d, hydrated, FORMATS["historic_brawl"])
        assert len(violations) == 2
        reasons = {v["reason"] for v in violations}
        assert reasons == {"colorless_deck_must_pick_one_basic_type"}
        names = sorted(v["name"] for v in violations)
        assert names == ["Forest", "Plains"]

    def test_colorless_commander_rejects_plains(self):
        cmd = _real("Kozilek, the Great Distortion")
        hydrated = [cmd, _real("Plains")]
        d = deck(
            format="commander",
            commanders=["Kozilek, the Great Distortion"],
            cards=[("Plains", 5)],
        )
        violations = check_color_identity(d, hydrated, FORMATS["commander"])
        assert len(violations) == 1
        assert violations[0]["name"] == "Plains"

    def test_colorless_brawl_single_basic_plus_wastes(self):
        # Wastes (empty CI) is always allowed alongside the chosen exempt basic.
        cmd = _real("Karn, Living Legacy")
        hydrated = [
            cmd,
            _real("Plains"),
            _real("Wastes"),
        ]
        d = deck(
            format="historic_brawl",
            commanders=["Karn, Living Legacy"],
            cards=[("Plains", 20), ("Wastes", 10)],
        )
        violations = check_color_identity(d, hydrated, FORMATS["historic_brawl"])
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
            _real("Lightning Bolt"),
            _real("Swords to Plowshares"),
            _real("Sol Ring"),
        ]

        result = legality_audit(_hd(deck, hydrated))
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
            _real("Krenko, Mob Boss"),
            _real("Lightning Bolt"),
        ]

        result = legality_audit(_hd(deck, hydrated))
        assert result["counts"]["commander_zone"] == 0

    def test_non_commander_format_skips_zone_check(self):
        """60-card constructed has no commander zone — check is a no-op."""
        deck = {
            "format": "modern",
            "deck_size": 60,
            "commanders": [],
            "cards": [{"name": "Lightning Bolt", "quantity": 4}],
        }
        hydrated = [_real("Lightning Bolt")]
        result = legality_audit(_hd(deck, hydrated))
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
            _real("Lightning Bolt"),
            _real("Sol Ring"),
        ]

        result = legality_audit(_hd(deck, hydrated))
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
            _real("Thrasios, Triton Hero"),
            _real("Lightning Bolt"),
        ]

        result = legality_audit(_hd(deck, hydrated))
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
            _real("Kozilek, Butcher of Truth"),
            _real("Sol Ring"),
        ]
        result = legality_audit(_hd(deck, hydrated))
        assert result["counts"]["commander_zone"] == 0


# ---------- Copy limit checks ----------

_SINGLETON_CONFIG = FORMATS["commander"]
_CONSTRUCTED_CONFIG = FORMATS["pioneer"]


class TestCopyLimits:
    def _hyd_index(self, hydrated: list[dict]) -> dict:
        return {c["name"]: c for c in hydrated}

    def test_normal_singleton_violation(self):
        hydrated = [_real("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 2)])
        v = check_copy_limits(d, self._hyd_index(hydrated), _SINGLETON_CONFIG)
        assert len(v) == 1
        assert v[0]["name"] == "Lightning Bolt"
        assert v[0]["quantity"] == 2
        assert v[0]["limit"] == 1
        assert v[0]["reason"] == "copy_limit"

    def test_basic_land_allowed(self):
        hydrated = [_real("Forest")]
        d = deck(cards=[("Forest", 40)])
        assert check_copy_limits(d, self._hyd_index(hydrated), _SINGLETON_CONFIG) == []

    def test_any_number_exemption(self):
        hare = _real("Hare Apparent")
        d = deck(cards=[("Hare Apparent", 40)])
        assert check_copy_limits(d, self._hyd_index([hare]), _SINGLETON_CONFIG) == []

    def test_up_to_n_at_cap(self):
        dwarves = _real("Seven Dwarves")
        d = deck(cards=[("Seven Dwarves", 7)])
        assert check_copy_limits(d, self._hyd_index([dwarves]), _SINGLETON_CONFIG) == []

    def test_up_to_n_over_cap(self):
        dwarves = _real("Seven Dwarves")
        d = deck(cards=[("Seven Dwarves", 8)])
        v = check_copy_limits(d, self._hyd_index([dwarves]), _SINGLETON_CONFIG)
        assert len(v) == 1
        assert v[0]["name"] == "Seven Dwarves"
        assert v[0]["quantity"] == 8
        assert v[0]["limit"] == 7
        assert v[0]["reason"] == "exceeds_named_card_cap"

    def test_nazgul_nine(self):
        nazgul = _real("Nazgûl")
        d = deck(cards=[("Nazgûl", 9)])
        assert check_copy_limits(d, self._hyd_index([nazgul]), _SINGLETON_CONFIG) == []

    def test_card_copy_limit_is_the_one_ladder(self):
        from mtg_utils.legality_audit import card_copy_limit

        plains = _real("Plains")
        rats = _real("Relentless Rats")
        bolt = _real("Lightning Bolt")
        lotus = _real("Black Lotus")  # vintage: restricted
        assert card_copy_limit(plains, FORMATS["modern"]) is None
        assert card_copy_limit(rats, FORMATS["modern"]) is None
        assert card_copy_limit(bolt, FORMATS["modern"]) == 4
        assert card_copy_limit(bolt, FORMATS["commander"]) == 1
        assert card_copy_limit(lotus, FORMATS["vintage"]) == 1

    def test_constructed_4_of_allowed(self):
        hydrated = [_real("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 4)])
        d["format"] = "pioneer"
        assert (
            check_copy_limits(d, self._hyd_index(hydrated), _CONSTRUCTED_CONFIG) == []
        )

    def test_constructed_5_of_violation(self):
        hydrated = [_real("Lightning Bolt")]
        d = deck(cards=[("Lightning Bolt", 5)])
        d["format"] = "pioneer"
        v = check_copy_limits(d, self._hyd_index(hydrated), _CONSTRUCTED_CONFIG)
        assert len(v) == 1
        assert v[0]["limit"] == 4

    def test_constructed_main_plus_sideboard_combined(self):
        hydrated = [_real("Lightning Bolt")]
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
        hydrated = [_real("Ancestral Recall")]  # vintage: restricted
        d = {
            "format": "vintage",
            "cards": [{"name": "Ancestral Recall", "quantity": 2}],
        }
        v = check_copy_limits(
            d,
            self._hyd_index(hydrated),
            FORMATS["vintage"],
        )
        assert len(v) == 1
        assert v[0]["limit"] == 1
        assert v[0]["reason"] == "restricted"


# ---------- Top-level audit ----------


class TestLegalityAudit:
    def test_clean_deck_passes(self):
        hydrated = [
            jinnie(),
            _real("Swords to Plowshares"),
            _real("Forest"),
        ]
        d = deck(cards=[("Swords to Plowshares", 1), ("Forest", 30)])
        result = legality_audit(_hd(d, hydrated))
        assert result["overall_status"] == "PASS"
        assert result["format"] == "historic_brawl"
        assert result["counts"]["format_legality"] == 0
        assert result["counts"]["color_identity"] == 0
        assert result["counts"]["copy_limits"] == 0

    def test_multi_violation_deck_fails(self):
        hydrated = [
            jinnie(),
            _real("Sol Ring"),  # not_legal (not on Arena)
            _real("Counterspell"),  # off-identity
            _real("Lightning Bolt"),
        ]
        d = deck(
            cards=[
                ("Sol Ring", 1),
                ("Counterspell", 1),
                ("Lightning Bolt", 2),  # singleton violation
            ],
        )
        result = legality_audit(_hd(d, hydrated))
        assert result["overall_status"] == "FAIL"
        assert result["counts"]["format_legality"] == 1
        assert result["counts"]["color_identity"] == 1
        assert result["counts"]["copy_limits"] == 1

    def test_unknown_format_raises(self):
        hydrated = [jinnie()]
        d = deck(format="made_up_format")
        import pytest

        with pytest.raises(ValueError, match="Unknown format"):
            legality_audit(_hd(d, hydrated))


# ---------- CLI smoke tests ----------


class TestCLI:
    def _write(
        self, tmp_path: Path, deck_data: dict, hydrated_data: list[dict]
    ) -> tuple[Path, Path]:
        deck_path = tmp_path / "deck.json"
        hydrated_path = tmp_path / "hydrated.json"
        deck_path.write_text(json.dumps(deck_data))
        hydrated_path.write_text(json.dumps(bulk_for_cli(hydrated_data)))
        return deck_path, hydrated_path

    def test_cli_pass(self, tmp_path: Path):
        hydrated = [jinnie(), _real("Swords to Plowshares")]
        d = deck(cards=[("Swords to Plowshares", 1)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), "--bulk-data", str(hydrated_path)]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output
        data = json_from_cli_output(result)
        assert data["overall_status"] == "PASS"

    def test_cli_fail(self, tmp_path: Path):
        hydrated = [jinnie(), _real("Sol Ring")]
        d = deck(cards=[("Sol Ring", 1)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), "--bulk-data", str(hydrated_path)]
        )
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
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--output",
                str(custom_output),
            ],
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
        hydrated_path.write_text(json.dumps(bulk_for_cli(hydrated_data)))
        return deck_path, hydrated_path

    def _write_rules(self, tmp_path):
        p = tmp_path / "comprehensive-rules-20240202.txt"
        p.write_text(self._CR_FIXTURE, encoding="utf-8")
        return p

    def test_copy_limit_violation_cited(self, tmp_path: Path):
        # Historic Brawl singleton — two copies of Sol Ring triggers a
        # copy_limit violation whose reason should cite 100.2a / 903.5b.
        rules_path = self._write_rules(tmp_path)
        hydrated = [jinnie(), _real("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
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
                "--bulk-data",
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
        hydrated = [jinnie(), _real("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        # No --cite-rules (default-on), no --rules-file (input-dir search).
        result = runner.invoke(
            main, [str(deck_path), "--bulk-data", str(hydrated_path)]
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        citations = data.get("rule_citations") or {}
        assert citations, "default-on should attach citations"
        assert "rule_citations_error" not in data

    def test_no_cite_rules_opts_out(self, tmp_path: Path):
        """--no-cite-rules skips citation attachment even with a
        reachable CR."""
        self._write_rules(tmp_path)
        hydrated = [jinnie(), _real("Sol Ring")]
        d = deck(cards=[("Sol Ring", 2)])
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), "--bulk-data", str(hydrated_path), "--no-cite-rules"]
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        assert "rule_citations" not in data
        assert "rule_citations_error" not in data

    def test_warn_on_missing_cr_surfaces_in_stdout(self, tmp_path: Path, monkeypatch):
        """Default-on citation lookup with no reachable CR must print a
        WARN line to stdout (not only to the JSON sidecar).

        ``resolve_rules_path`` searches the input file's directory and then
        ``Path.cwd()``. The cwd leg made this test depend on ambient state: a
        developer who has ever run ``download-rules`` from the package dir has a
        gitignored ``comprehensive-rules-*.txt`` sitting there forever, so the CR
        *was* reachable and no WARN was emitted. Pin cwd to the empty tmp_path so
        both search legs are genuinely clean.
        """
        hydrated = [jinnie()]
        d = deck()
        deck_path, hydrated_path = self._write(tmp_path, d, hydrated)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main, [str(deck_path), "--bulk-data", str(hydrated_path)]
        )
        assert result.exit_code == 0, result.output
        assert "WARN: rule_citations not attached" in result.output


# ---------- Companion checks ----------


def _companion_card(name: str) -> dict:
    """A real Ikoria companion from the testkit snapshot."""
    return test_card(name)


class TestCompanion:
    """The ``companion`` zone is outside the deck and sideboard (CR 702.139a-b):
    validated on its own (max one, must have the ability, condition satisfied)
    and never counted by the deck-minimum / sideboard-size checks."""

    def test_no_companion_zone_yields_no_violations(self):
        result = legality_audit(_hd(deck(), [jinnie()]))
        assert result["counts"]["companion"] == 0
        assert result["violations"]["companion"] == []

    def test_condition_violation_keruga_with_a_two_drop(self):
        # Keruga: every nonland card must be mana value 3+; Sol Ring is a 1-drop.
        keruga = _companion_card("Keruga, the Macrosage")
        commander = jinnie()  # MV 3: satisfies Keruga
        sol_ring = _real("Sol Ring")
        d = deck(cards=[("Sol Ring", 1)])
        d["companion"] = [{"name": "Keruga, the Macrosage", "quantity": 1}]
        result = legality_audit(_hd(d, [commander, sol_ring, keruga]))
        v = result["violations"]["companion"]
        assert [x["reason"] for x in v] == ["companion_condition"]
        assert v[0]["rule"] == "702.139b"
        assert v[0]["name"] == "Keruga, the Macrosage"
        assert v[0]["card"] == "Sol Ring"
        assert result["overall_status"] == "FAIL"

    def test_satisfied_condition_passes(self):
        keruga = _companion_card("Keruga, the Macrosage")
        commander = jinnie()  # MV 3: satisfies Keruga
        giant = _real("Hill Giant")
        d = deck(cards=[("Hill Giant", 1)])
        d["companion"] = [{"name": "Keruga, the Macrosage", "quantity": 1}]
        result = legality_audit(_hd(d, [commander, giant, keruga]))
        assert result["violations"]["companion"] == []

    def test_non_companion_card_in_the_zone(self):
        sol_ring = _real("Sol Ring")
        d = deck()
        d["companion"] = [{"name": "Sol Ring", "quantity": 1}]
        result = legality_audit(_hd(d, [jinnie(), sol_ring]))
        v = result["violations"]["companion"]
        assert [x["reason"] for x in v] == ["companion_not_companion"]

    def test_multiple_companions_flagged(self):
        keruga = _companion_card("Keruga, the Macrosage")
        yorion = _companion_card("Yorion, Sky Nomad")
        commander = jinnie()  # MV 3: satisfies Keruga
        d = deck()
        d["companion"] = [
            {"name": "Keruga, the Macrosage", "quantity": 1},
            {"name": "Yorion, Sky Nomad", "quantity": 1},
        ]
        result = legality_audit(_hd(d, [commander, keruga, yorion]))
        reasons = {x["reason"] for x in result["violations"]["companion"]}
        assert "companion_multiple" in reasons

    def test_unhydratable_companion_skipped_gracefully(self):
        d = deck()
        d["companion"] = [{"name": "Totally Unknown Cat", "quantity": 1}]
        result = legality_audit(_hd(d, [jinnie()]))
        assert result["violations"]["companion"] == []

    def _std_deck(self, n_cards: int) -> dict:
        plains = _real("Plains")
        yorion = _companion_card("Yorion, Sky Nomad")
        d = {
            "format": "pioneer",  # Yorion is Pioneer-legal (rotated out of Standard)
            "commanders": [],
            "cards": [{"name": "Plains", "quantity": n_cards}],
            "sideboard": [],
            "companion": [{"name": "Yorion, Sky Nomad", "quantity": 1}],
        }
        return legality_audit(_hd(d, [plains, yorion]))

    def test_yorion_uses_the_60_card_minimum_in_constructed(self):
        # Non-singleton 60-card format → deck_minimum 60 → Yorion needs 80.
        result = self._std_deck(60)
        v = result["violations"]["companion"]
        assert [x["reason"] for x in v] == ["companion_condition"]
        assert "80" in v[0]["detail"]

    def test_yorion_satisfied_at_80_in_constructed(self):
        assert self._std_deck(80)["violations"]["companion"] == []

    def test_a_builds_own_size_never_raises_the_floor(self):
        # A Pioneer build targeting 80 (Yorion) is audited against the 60-card CR
        # floor: 80 cards satisfy Yorion (60 + 20), and 60 cards are not below
        # the minimum.
        plains = _real("Plains")
        yorion = _companion_card("Yorion, Sky Nomad")
        d = {
            "format": "pioneer",
            "deck_size": 80,
            "commanders": [],
            "cards": [{"name": "Plains", "quantity": 80}],
            "sideboard": [],
            "companion": [{"name": "Yorion, Sky Nomad", "quantity": 1}],
        }
        result = legality_audit(_hd(d, [plains, yorion]))
        assert result["violations"]["companion"] == []
        d["cards"] = [{"name": "Plains", "quantity": 60}]
        d["companion"] = []
        assert legality_audit(_hd(d, [plains, yorion]))["violations"][
            "deck_minimum"
        ] == ([])

    def test_companion_never_pads_the_deck_minimum(self):
        # 100 counted cards vs a 101 minimum: the companion is outside the deck
        # (CR 702.139a-b), so it must NOT bring the total to 101.
        from mtg_utils.legality_audit import check_deck_minimum

        d = {
            "commanders": [{"name": "Jinnie Fay, Jetmir's Second", "quantity": 1}],
            "cards": [{"name": "Forest", "quantity": 99}],
            "companion": [{"name": "Yorion, Sky Nomad", "quantity": 1}],
        }
        violations = check_deck_minimum(d, replace(FORMATS["commander"], deck_size=101))
        assert violations
        assert violations[0]["total_cards"] == 100

    def test_companion_never_counts_toward_sideboard_size(self):
        from mtg_utils.legality_audit import check_sideboard_size

        d = {
            "sideboard": [{"name": "Duress", "quantity": 15}],
            "companion": [{"name": "Yorion, Sky Nomad", "quantity": 1}],
        }
        assert check_sideboard_size(d, FORMATS["standard"]) == []


class TestCompanionCiteRules:
    """--cite-rules maps the three companion reasons onto their CR rules."""

    _CR_FIXTURE = (
        "Magic: The Gathering Comprehensive Rules\n\n"
        "These rules are effective as of February 2, 2024\n\n"
        "Contents\n\n"
        "1. Game Concepts\n"
        "100. General\n"
        "103. Starting the Game\n"
        "7. Additional Rules\n"
        "702. Keyword Abilities\n"
        "9. Casual Variants\n"
        "903. Commander\n"
        "Glossary\n"
        "Credits\n\n"
        "1. Game Concepts\n\n"
        "100. General\n\n"
        "100.2a Constructed copy limit.\n\n"
        "103. Starting the Game\n\n"
        "103.2b A player who wishes to reveal a companion may do so; each player "
        "may reveal no more than one companion.\n\n"
        "7. Additional Rules\n\n"
        "702. Keyword Abilities\n\n"
        "702.139a Companion is a keyword ability that functions outside the "
        "game.\n\n"
        "702.139b If a companion ability refers to your starting deck, it refers "
        "to your deck after you've set aside any sideboard cards.\n\n"
        "9. Casual Variants\n\n"
        "903. Commander\n\n"
        "903.5b Commander singleton rule.\n\n"
        "Glossary\n\n"
        "Credits\n"
    )

    def test_companion_reasons_are_cited(self, tmp_path: Path):
        rules_path = tmp_path / "comprehensive-rules-20240202.txt"
        rules_path.write_text(self._CR_FIXTURE, encoding="utf-8")
        keruga = _companion_card("Keruga, the Macrosage")
        commander = jinnie()  # MV 3: satisfies Keruga
        sol_ring = _real("Sol Ring")
        # One deck triggering all three reasons: two occupants (103.2b), one of
        # them not a companion (702.139a), and Keruga's condition broken by the
        # 1-drop (702.139b).
        d = deck(cards=[("Sol Ring", 1)])
        d["companion"] = [
            {"name": "Keruga, the Macrosage", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ]
        deck_path = tmp_path / "deck.json"
        hydrated_path = tmp_path / "hydrated.json"
        deck_path.write_text(json.dumps(d))
        hydrated_path.write_text(
            json.dumps(bulk_for_cli([commander, sol_ring, keruga]))
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
                "--cite-rules",
                "--rules-file",
                str(rules_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        citations = data.get("rule_citations") or {}
        cited = {c["rule"] for c in citations.get("companion") or []}
        assert {"103.2b", "702.139a", "702.139b"} <= cited


# ---------- Competitive Brawl (Arena) ----------


class TestCompetitiveBrawl:
    """Competitive Brawl shares the `brawl` legality key but not its ban list:
    it legalizes everything that key marks `banned` and enforces its own ten
    cards by name. `not_legal` still fails — that means absent from Arena."""

    def test_key_banned_card_is_legal(self):
        # Mana Drain is banned in ordinary Historic Brawl, legal here.
        hydrated = [_real("Mana Drain")]
        violations = check_format_legality(hydrated, FORMATS["competitive_brawl"])
        assert violations == []

    def test_not_legal_card_still_fails(self):
        # not_legal means the card isn't on Arena at all — still a violation.
        hydrated = [_real("Sol Ring")]
        violations = check_format_legality(hydrated, FORMATS["competitive_brawl"])
        assert len(violations) == 1
        assert violations[0]["legality"] == "not_legal"

    def test_format_ban_list_is_enforced_by_name(self):
        # Oko is `banned` under the brawl key too, which Competitive Brawl ignores;
        # it is banned here by name, on the format's own list.
        hydrated = [_real("Oko, Thief of Crowns")]
        violations = check_format_legality(hydrated, FORMATS["competitive_brawl"])
        assert len(violations) == 1
        assert violations[0]["name"] == "Oko, Thief of Crowns"
        assert violations[0]["legality"] == "banned"

    def test_end_to_end_audit_passes_with_a_key_banned_card(self):
        cmd = _real("Thranduil, the Elvenking")
        drain = _real("Mana Drain")
        deck = {
            "format": "competitive_brawl",
            "commanders": [{"name": "Thranduil, the Elvenking", "quantity": 1}],
            "cards": [{"name": "Mana Drain", "quantity": 1}],
            "total_cards": 2,
        }
        result = legality_audit(_hd(deck, [cmd, drain]))
        assert result["violations"]["format_legality"] == []


# ---------- Pool containment (limited) ----------


class TestPoolContainment:
    """A sealed / draft deck is drawn from its opened pool (CR 100.2b): every copy in
    the main deck and sideboard must be in the pool, basics excepted; there is no
    copy limit and no sideboard cap."""

    COMMON = test_card("Stone by Sunlight")
    RARE = test_card("The One Ring")
    PLAINS = test_card("Plains")

    def _audit(self, *, cards, sideboard=(), pool=()):
        d = {
            "format": "sealed",
            "commanders": [],
            "cards": [{"name": n, "quantity": q} for n, q in cards],
            "sideboard": [{"name": n, "quantity": q} for n, q in sideboard],
            "pool": [{"name": n, "quantity": q} for n, q in pool],
        }
        return legality_audit(_hd(d, [self.COMMON, self.RARE, self.PLAINS]))

    def test_off_pool_card_is_a_violation(self):
        result = self._audit(
            cards=[("The One Ring", 1), ("Plains", 39)],
            pool=[("Stone by Sunlight", 3)],
        )
        v = result["violations"]["pool_containment"]
        assert v == [
            {
                "name": "The One Ring",
                "quantity": 1,
                "in_pool": 0,
                "reason": "not_in_pool",
            }
        ]
        assert result["overall_status"] == "FAIL"

    def test_duplicates_the_product_included_are_legal(self):
        result = self._audit(
            cards=[("Stone by Sunlight", 3), ("Plains", 37)],
            pool=[("Stone by Sunlight", 3)],
        )
        assert result["violations"]["pool_containment"] == []
        assert result["violations"]["copy_limits"] == []  # no copy limit

    def test_a_fourth_copy_the_pool_lacks_is_a_violation(self):
        result = self._audit(
            cards=[("Stone by Sunlight", 4), ("Plains", 36)],
            pool=[("Stone by Sunlight", 3)],
        )
        assert result["violations"]["pool_containment"][0]["in_pool"] == 3

    def test_basics_are_unlimited_and_outside_the_pool(self):
        result = self._audit(cards=[("Plains", 40)], pool=[("The One Ring", 1)])
        assert result["violations"]["pool_containment"] == []

    def test_a_basic_with_no_record_is_still_exempt_by_name(self):
        from mtg_utils.legality_audit import check_pool_containment

        d = {"cards": [{"name": "Snow-Covered Forest", "quantity": 17}], "pool": []}
        assert check_pool_containment(d, {}, FORMATS["sealed"]) == []
        d = {"cards": [{"name": "Not A Basic", "quantity": 1}], "pool": []}
        assert check_pool_containment(d, {}, FORMATS["sealed"])[0]["name"] == (
            "Not A Basic"
        )

    def test_the_sideboard_is_the_unused_pool_with_no_cap(self):
        result = self._audit(
            cards=[("Plains", 40)],
            sideboard=[("Stone by Sunlight", 43)],
            pool=[("Stone by Sunlight", 43)],
        )
        assert result["violations"]["sideboard_size"] == []
        assert result["violations"]["pool_containment"] == []

    def test_below_the_40_card_minimum_cites_100_2b(self):
        result = self._audit(cards=[("Plains", 39)], pool=[])
        assert result["violations"]["deck_minimum"][0]["minimum"] == 40
        from mtg_utils.legality_audit import _REASON_TO_CR_RULES

        assert "100.2b" in _REASON_TO_CR_RULES["below_minimum"]
        assert _REASON_TO_CR_RULES["not_in_pool"] == ("100.2b",)

    def test_a_constructed_deck_has_no_containment_check(self):
        d = {
            "format": "modern",
            "commanders": [],
            "cards": [{"name": "Plains", "quantity": 60}],
            "sideboard": [],
        }
        assert (
            legality_audit(_hd(d, [self.PLAINS]))["violations"]["pool_containment"]
            == []
        )
