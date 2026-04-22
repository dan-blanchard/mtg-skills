"""Tests for cut_check.py — mechanical pre-grill analysis."""

from __future__ import annotations

import json

from mtg_utils.cut_check import (
    detect_commander_multiplication,
    detect_keyword_interactions,
    detect_self_recurring,
    detect_triggers,
    main,
    run_cut_check,
)


class TestDetectTriggers:
    def test_upkeep_trigger_fixed_damage(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Upkeep Drainer")
        triggers = detect_triggers(card, trigger_types=["upkeep"], opponents=3)
        assert len(triggers) == 1
        assert triggers[0]["matches_trigger_type"] is True
        assert triggers[0]["parseable"] is True

    def test_upkeep_trigger_not_matched_as_attack(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Upkeep Drainer")
        triggers = detect_triggers(card, trigger_types=["attack"], opponents=3)
        matched = [t for t in triggers if t["matches_trigger_type"]]
        assert len(matched) == 0

    def test_attack_trigger(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Attack Trigger Guy")
        triggers = detect_triggers(card, trigger_types=["attack"], opponents=3)
        matched = [t for t in triggers if t["matches_trigger_type"]]
        assert len(matched) == 1

    def test_variable_trigger_not_parseable(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Variable Trigger")
        triggers = detect_triggers(card, trigger_types=["upkeep"], opponents=3)
        assert len(triggers) == 1
        assert triggers[0]["matches_trigger_type"] is True
        assert triggers[0]["parseable"] is False

    def test_multiple_trigger_types(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Upkeep Drainer")
        triggers = detect_triggers(
            card, trigger_types=["upkeep", "attack"], opponents=3
        )
        matched = [t for t in triggers if t["matches_trigger_type"]]
        assert len(matched) == 1  # matches upkeep only


class TestDetectKeywordInteractions:
    def test_menace_plus_blocking_restriction(self, trigger_test_cards):
        commander = next(
            c for c in trigger_test_cards if c["name"] == "Obeka, Splitter of Seconds"
        )
        card = next(c for c in trigger_test_cards if c["name"] == "Blocking Restrictor")
        interactions = detect_keyword_interactions(card, commander)
        assert len(interactions) > 0
        assert any("unblockable" in i["interaction"].lower() for i in interactions)

    def test_double_strike_plus_combat_damage(self, trigger_test_cards):
        commander = next(
            c for c in trigger_test_cards if c["name"] == "Obeka, Splitter of Seconds"
        )
        card = next(c for c in trigger_test_cards if c["name"] == "Double Striker")
        interactions = detect_keyword_interactions(card, commander)
        assert any("double" in i["interaction"].lower() for i in interactions)

    def test_no_interaction(self, trigger_test_cards):
        commander = next(
            c for c in trigger_test_cards if c["name"] == "Obeka, Splitter of Seconds"
        )
        card = next(c for c in trigger_test_cards if c["name"] == "Upkeep Drainer")
        interactions = detect_keyword_interactions(card, commander)
        assert len(interactions) == 0


class TestDetectSelfRecurring:
    def test_suspend_card(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Suspend Bouncer")
        assert detect_self_recurring(card) is True

    def test_buyback_card(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Buyback Spell")
        assert detect_self_recurring(card) is True

    def test_non_recurring_card(self, trigger_test_cards):
        card = next(c for c in trigger_test_cards if c["name"] == "Upkeep Drainer")
        assert detect_self_recurring(card) is False


class TestDetectCommanderMultiplication:
    def _get_card(self, cards, name):
        return next(c for c in cards if c["name"] == name)

    def test_helm_of_the_host_commander_copy(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Helm of the Host")
        result = detect_commander_multiplication(card, commander)
        assert len(result["commander_copy"]) > 0
        assert result["legend_bypass"] is True

    def test_spark_double_commander_copy(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Spark Double")
        result = detect_commander_multiplication(card, commander)
        assert len(result["commander_copy"]) > 0
        assert result["legend_bypass"] is True

    def test_strionic_resonator_ability_copy(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Strionic Resonator")
        result = detect_commander_multiplication(card, commander)
        assert len(result["ability_copy"]) > 0
        assert len(result["commander_copy"]) == 0

    def test_panharmonicon_trigger_doubler(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Panharmonicon")
        result = detect_commander_multiplication(card, commander)
        assert len(result["ability_copy"]) > 0
        assert any(e["type"] == "trigger_doubler" for e in result["ability_copy"])

    def test_rings_of_brighthearth_activated_copy(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Rings of Brighthearth")
        result = detect_commander_multiplication(card, commander)
        assert len(result["ability_copy"]) > 0
        assert any(
            e["type"] == "copy_activated_ability" for e in result["ability_copy"]
        )

    def test_commander_triggers_affected(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Strionic Resonator")
        result = detect_commander_multiplication(card, commander)
        assert "combat-damage" in result["commander_triggers_affected"]

    def test_commander_activated_abilities(self, trigger_test_cards, hydrated_cards):
        # Thrasios has "{4}: Scry 1, then reveal..."
        thrasios = next(
            c for c in hydrated_cards if c["name"] == "Thrasios, Triton Hero"
        )
        card = self._get_card(trigger_test_cards, "Rings of Brighthearth")
        result = detect_commander_multiplication(card, thrasios)
        assert len(result["commander_activated_abilities"]) > 0

    def test_no_false_positive_counterspell(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Counterspell")
        result = detect_commander_multiplication(card, commander)
        assert len(result["commander_copy"]) == 0
        assert len(result["ability_copy"]) == 0
        assert result["legend_bypass"] is False

    def test_no_false_positive_upkeep_drainer(self, trigger_test_cards):
        commander = self._get_card(trigger_test_cards, "Obeka, Splitter of Seconds")
        card = self._get_card(trigger_test_cards, "Upkeep Drainer")
        result = detect_commander_multiplication(card, commander)
        assert len(result["commander_copy"]) == 0
        assert len(result["ability_copy"]) == 0

    def test_run_cut_check_includes_multiplication(self, trigger_test_cards):
        results = run_cut_check(
            hydrated=trigger_test_cards,
            commander_name="Obeka, Splitter of Seconds",
            cut_names=["Helm of the Host", "Strionic Resonator"],
            trigger_types=["upkeep"],
            multiplier_low=3,
            multiplier_high=7,
            opponents=3,
        )
        helm = next(r for r in results if r["name"] == "Helm of the Host")
        assert "commander_multiplication" in helm
        assert len(helm["commander_multiplication"]["commander_copy"]) > 0
        resonator = next(r for r in results if r["name"] == "Strionic Resonator")
        assert len(resonator["commander_multiplication"]["ability_copy"]) > 0


class TestRunCutCheck:
    def test_full_analysis(self, trigger_test_cards):
        results = run_cut_check(
            hydrated=trigger_test_cards,
            commander_name="Obeka, Splitter of Seconds",
            cut_names=["Upkeep Drainer", "Blocking Restrictor", "Suspend Bouncer"],
            trigger_types=["upkeep"],
            multiplier_low=3,
            multiplier_high=7,
            opponents=3,
        )
        assert len(results) == 3
        drainer = next(r for r in results if r["name"] == "Upkeep Drainer")
        assert len(drainer["triggers"]) == 1
        assert drainer["triggers"][0]["parseable"] is True
        restrictor = next(r for r in results if r["name"] == "Blocking Restrictor")
        assert len(restrictor["keyword_interactions"]) > 0
        bouncer = next(r for r in results if r["name"] == "Suspend Bouncer")
        assert bouncer["self_recurring"] is True


class TestCLI:
    def test_text_report_and_json_file(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Upkeep Drainer"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--trigger-type",
                "upkeep",
                "--multiplier-low",
                "3",
                "--multiplier-high",
                "7",
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output

        # Loose text-report assertions
        assert "cut-check:" in result.output
        assert "Upkeep Drainer" in result.output
        assert "Full JSON:" in result.output
        assert "Obeka, Splitter of Seconds" in result.output

        # Strict structural correctness via the JSON file
        data = json_from_cli_output(result)
        assert len(data) == 1
        assert data[0]["name"] == "Upkeep Drainer"
        assert output_path.exists()

    def test_flags_commander_multiplication_in_text_report(
        self, trigger_test_cards, tmp_path
    ):
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(
            json.dumps(["Helm of the Host", "Strionic Resonator", "Upkeep Drainer"])
        )
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "COMMANDER_MULTIPLICATION" in result.output
        assert "Helm of the Host" in result.output
        assert "Strionic Resonator" in result.output

    def test_default_output_path_is_deterministic(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Upkeep Drainer"]))

        runner = CliRunner()
        args = [
            str(hydrated_path),
            "Obeka, Splitter of Seconds",
            "--cuts",
            str(cuts_path),
            "--multiplier-low",
            "3",
            "--multiplier-high",
            "7",
        ]
        r1 = runner.invoke(main, args)
        r2 = runner.invoke(main, args)
        assert r1.exit_code == 0
        assert r2.exit_code == 0

        def _path(output):
            for line in output.splitlines():
                if line.startswith("Full JSON:"):
                    return line.split(":", 1)[1].strip()
            return None

        assert _path(r1.output) == _path(r2.output)


class TestCiteRules:
    """``--cite-rules`` enriches keyword_interactions with CR citations."""

    _CR_FIXTURE = (
        "Magic: The Gathering Comprehensive Rules\n\n"
        "These rules are effective as of February 2, 2024\n\n"
        "Contents\n\n"
        "1. Game Concepts\n"
        "100. General\n"
        "Glossary\n"
        "Credits\n\n"
        "1. Game Concepts\n\n"
        "100. General\n\n"
        "100.1. Stub rule.\n\n"
        "Glossary\n\n"
        "Trample\n"
        "A keyword ability. See rule 100.1.\n\n"
        "Menace\n"
        "A keyword ability. See rule 100.1.\n\n"
        "Credits\n"
    )

    def _write_rules(self, tmp_path):
        p = tmp_path / "comprehensive-rules-20240202.txt"
        p.write_text(self._CR_FIXTURE, encoding="utf-8")
        return p

    def test_cite_rules_attaches_citations(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        rules_path = self._write_rules(tmp_path)
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
                "--cite-rules",
                "--rules-file",
                str(rules_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        # Obeka + Blocking Restrictor have the menace + can't-be-blocked
        # interaction, plus trample (from the Restrictor's oracle text).
        citations = data[0].get("rule_citations") or []
        cited_terms = {c["term"] for c in citations}
        assert {"Menace", "Trample"} & cited_terms

    def test_cite_rules_missing_file_is_soft_error(self, trigger_test_cards, tmp_path):
        """Missing CR file should record an error field, not crash."""
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"
        missing_rules = tmp_path / "nope.txt"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
                "--cite-rules",
                "--rules-file",
                str(missing_rules),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        for entry in data:
            assert entry["rule_citations"] == []
            assert "rule_citations_error" in entry

    def test_cite_rules_default_on_finds_cr_next_to_hydrated(
        self, trigger_test_cards, tmp_path
    ):
        """Regression pin: default --cite-rules behavior should auto-find
        a CR file in the directory containing the hydrated JSON, without
        needing an explicit --rules-file flag. Covers the path the
        0a340f10 live session agent missed when ``uv run --directory
        <skill>`` rebased cwd away from the working dir."""
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        rules_path = self._write_rules(tmp_path)
        assert rules_path.parent == tmp_path
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        # No --cite-rules flag (relies on default-on) and no
        # --rules-file (relies on input-dir search).
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        citations = [c for e in data for c in e.get("rule_citations", [])]
        assert citations, "default-on should attach citations"
        assert "rule_citations_error" not in data[0]

    def test_no_cite_rules_opts_out(self, trigger_test_cards, tmp_path):
        """--no-cite-rules skips citation attachment entirely even when
        a CR file would otherwise be reachable."""
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        self._write_rules(tmp_path)
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
                "--no-cite-rules",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        for entry in data:
            assert "rule_citations" not in entry
            assert "rule_citations_error" not in entry

    def test_warn_on_missing_cr_surfaces_in_stdout(self, trigger_test_cards, tmp_path):
        """Default-on citation lookup with no reachable CR must surface
        a WARN line in stdout, not only in the JSON sidecar. Agents skim
        stdout; silent JSON-only errors got missed in session 0a340f10."""
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(hydrated_path),
                "Obeka, Splitter of Seconds",
                "--cuts",
                str(cuts_path),
                "--multiplier-low",
                "1",
                "--multiplier-high",
                "1",
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "WARN: rule_citations not attached" in result.output
