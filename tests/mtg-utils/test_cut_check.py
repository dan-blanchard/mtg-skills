"""Tests for cut_check.py — mechanical pre-grill analysis."""

from __future__ import annotations

import json

from mtg_utils.card_ir import Ability, Card, Effect, Face, Quantity, Trigger
from mtg_utils.cut_check import (
    _activated_ability_lines,
    _extract_activated_abilities,
    detect_commander_multiplication,
    detect_keyword_interactions,
    detect_self_recurring,
    detect_triggers,
    detect_zone_granted_abilities,
    main,
    render_text_report,
    run_cut_check,
)


def _ir_triggered(event, *, category, factor, op="fixed", effect_scope="any"):
    """A hand-built single-trigger Card IR (the _SYNTHETIC_CASES pattern — no
    snapshot/bulk needed) with one triggered ability whose effect carries a value."""
    return Card(
        oracle_id="test",
        name="IR Card",
        faces=(
            Face(
                name="IR Card",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event=event, scope="you"),
                        effects=(
                            Effect(
                                category=category,
                                amount=Quantity(op=op, factor=factor),
                                scope=effect_scope,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


class TestDetectTriggersFromIR:
    """ADR-0029: trigger detection reads the Card IR structurally when present
    (bucket-A), falling back to the regex path when absent (bucket-B)."""

    _CARD = {"name": "x", "oracle_text": ""}

    def test_ir_attack_trigger_to_each_opponent_multiplies(self):
        # "Whenever you attack, deal 2 damage to each opponent" — IR-native.
        ir = _ir_triggered("attacks", category="damage", factor=2, effect_scope="opp")
        triggers = detect_triggers(
            self._CARD, trigger_types=["attack"], opponents=3, ir=ir
        )
        matched = [t for t in triggers if t["matches_trigger_type"]]
        assert len(matched) == 1
        assert matched[0]["matched_type"] == "attack"
        assert matched[0]["parseable"] is True
        assert matched[0]["base_value"] == "6"  # 2 damage x 3 opponents

    def test_ir_event_respects_trigger_type_filter(self):
        ir = _ir_triggered("etb", category="draw", factor=1)
        triggers = detect_triggers(
            self._CARD, trigger_types=["upkeep"], opponents=3, ir=ir
        )
        assert [t for t in triggers if t["matches_trigger_type"]] == []

    def test_ir_variable_amount_is_not_parseable(self):
        # op="count" (scales with the board) is not a fixed multipliable value.
        ir = _ir_triggered("upkeep", category="make_token", factor=1, op="count")
        triggers = detect_triggers(
            self._CARD, trigger_types=["upkeep"], opponents=3, ir=ir
        )
        matched = [t for t in triggers if t["matches_trigger_type"]]
        assert len(matched) == 1
        assert matched[0]["parseable"] is False

    def test_run_cut_check_reads_ir_when_resolvable(self, monkeypatch):
        # Wiring: run_cut_check resolves ir_for per card and feeds it to detect_triggers.
        import mtg_utils.cut_check as cc

        ir = _ir_triggered("attacks", category="damage", factor=2, effect_scope="opp")
        monkeypatch.setattr(
            cc, "ir_for", lambda card: ir if card.get("name") == "Atk" else None
        )
        hydrated = [{"name": "Atk", "oracle_text": "", "keywords": []}]
        results = run_cut_check(
            hydrated=hydrated,
            commander_name="Atk",
            cut_names=["Atk"],
            trigger_types=["attack"],
            multiplier_low=1,
            multiplier_high=1,
            opponents=3,
        )
        matched = [t for t in results[0]["triggers"] if t["matches_trigger_type"]]
        assert matched
        assert matched[0]["base_value"] == "6"  # the IR each-opponent value


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


class TestFlexibleInput:
    """cut-check should accept the same cuts.json format as build-deck.

    Regression: cut-check used ``json.loads`` directly and treated the result
    as a list of name strings. When the user passed ``[{"name": "X",
    "quantity": 1}]`` (the format build-deck accepts), cut-check crashed with
    ``TypeError: cannot use 'dict' as a dict key (unhashable type: 'dict')``
    deep inside ``run_cut_check`` when it called ``lookup.get(name, ...)`` on
    a dict. Sharing a single cuts.json across both tools is the expected
    workflow during a tune session, so cut-check must normalize like
    build-deck does.
    """

    def test_cli_accepts_dict_cuts(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps([{"name": "Upkeep Drainer", "quantity": 1}]))
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
        assert "Upkeep Drainer" in result.output

    def test_cli_rejects_malformed_entry(self, trigger_test_cards, tmp_path):
        """Symmetric with build_deck's contract: malformed cuts entries
        (no ``name`` key, wrong type) raise instead of warn-and-continue.

        Sharing a single ``cuts.json`` across cut-check and build-deck was
        the design goal of dict-format acceptance. Asymmetric error policy
        ("cut-check warns, build-deck raises") would let the user get a
        false sense of security from cut-check's partial analysis and
        then hit a hard error at build-deck on the same file. Both tools
        fail-fast on the same input.
        """
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps([{"quantity": 1}]))  # missing name
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
        assert result.exit_code != 0
        # Output file must not be written on error.
        assert not output_path.exists()

    def test_cli_accepts_mixed_string_and_dict_cuts(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(
            json.dumps(
                [
                    "Upkeep Drainer",
                    {"name": "Blocking Restrictor", "quantity": 1},
                ]
            )
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
        assert "Upkeep Drainer" in result.output
        assert "Blocking Restrictor" in result.output


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

    def test_warn_on_missing_cr_surfaces_in_stdout(
        self, trigger_test_cards, tmp_path, monkeypatch
    ):
        """Default-on citation lookup with no reachable CR must surface
        a WARN line in stdout, not only in the JSON sidecar. Agents skim
        stdout; silent JSON-only errors got missed in session 0a340f10.

        cwd is pinned to tmp_path because ``resolve_rules_path`` falls back to
        ``Path.cwd()``: a gitignored ``comprehensive-rules-*.txt`` left in the
        package dir by any earlier ``download-rules`` run made the CR reachable
        and silently defeated this assertion.
        """
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Blocking Restrictor"]))
        output_path = tmp_path / "out.json"
        monkeypatch.chdir(tmp_path)

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


# ---------------------------------------------------------------------------
# Zone-granted activated abilities
# ---------------------------------------------------------------------------

# Real oracle text / type lines (verified against MTGJSON), not templated
# stand-ins — a zone grant keys on the exact cost syntax, so a trimmed body
# would test the fixture rather than the detector.
_THRANDUIL = {
    "name": "Thranduil, the Elvenking",
    "type_line": "Legendary Creature — Elf Noble",
    "oracle_text": (
        "Thranduil has all activated abilities of all Elf cards in your "
        "graveyard.\nWhenever another legendary Elf you control enters, draw "
        "two cards, then discard a card."
    ),
}
_OBEKA = {
    "name": "Obeka, Splitter of Seconds",
    "type_line": "Legendary Creature — Ogre Wizard",
    "oracle_text": (
        "Menace\nWhenever Obeka, Splitter of Seconds deals combat damage to a "
        "player, you get that many additional upkeep steps after this phase."
    ),
}
_PRIEST_OF_TITANIA = {
    "name": "Priest of Titania",
    "type_line": "Creature — Elf Druid",
    "oracle_text": "{T}: Add {G} for each Elf on the battlefield.",
}
_IRON_SHIELD_ELF = {
    "name": "Iron-Shield Elf",
    "type_line": "Creature — Elf Warrior",
    "oracle_text": (
        "Discard a card: This creature gains indestructible until end of turn. "
        'Tap it. (Damage and effects that say "destroy" don\'t destroy it. If '
        "its toughness is 0 or less, it still dies.)"
    ),
}
_LATHRIL = {
    "name": "Lathril, Blade of the Elves",
    "type_line": "Legendary Creature — Elf Noble",
    "oracle_text": (
        "Menace (This creature can't be blocked except by two or more "
        "creatures.)\nWhenever Lathril deals combat damage to a player, create "
        "that many 1/1 green Elf Warrior creature tokens.\n{T}, Tap ten "
        "untapped Elves you control: Each opponent loses 10 life and you gain "
        "10 life."
    ),
}
_BLOODLINE_PRETENDER = {
    "name": "Bloodline Pretender",
    "type_line": "Artifact Creature — Shapeshifter",
    "oracle_text": (
        "Changeling (This card is every creature type.)\nAs this creature "
        "enters, choose a creature type.\nWhenever another creature you "
        "control of the chosen type enters, put a +1/+1 counter on this "
        "creature."
    ),
}
_DOOR_OF_DESTINIES = {
    "name": "Door of Destinies",
    "type_line": "Artifact",
    "oracle_text": (
        "As this artifact enters, choose a creature type.\nWhenever you cast a "
        "spell of the chosen type, put a charge counter on this artifact.\n"
        "Creatures you control of the chosen type get +1/+1 for each charge "
        "counter on this artifact."
    ),
}


class TestDetectZoneGrantedAbilities:
    def test_no_grant_on_ordinary_commander(self):
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _OBEKA)
        assert result == {"grants": False}

    def test_parses_granted_type_and_zone(self):
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _THRANDUIL)
        assert result["grants"] is True
        assert result["granted_type"] == "Elf"
        assert result["zone"] == "graveyard"

    def test_mana_ability_is_reported(self):
        """A mana ability is what a zone-granting commander mostly borrows, so
        include_mana must default on for this caller."""
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _THRANDUIL)
        assert result["abilities"] == ["{T}: Add {G} for each Elf on the battlefield."]

    def test_non_mana_symbol_cost_is_reported(self):
        """ "Discard a card:" has no mana symbol but is still an activated ability."""
        result = detect_zone_granted_abilities(_IRON_SHIELD_ELF, _THRANDUIL)
        assert len(result["abilities"]) == 1
        assert result["abilities"][0].startswith("Discard a card:")

    def test_reminder_text_is_not_an_ability(self):
        """Lathril has one activated ability; menace reminder text has no colon
        and the combat-damage line is triggered, not activated."""
        result = detect_zone_granted_abilities(_LATHRIL, _THRANDUIL)
        assert len(result["abilities"]) == 1
        assert result["abilities"][0].startswith("{T}, Tap ten untapped Elves")

    def test_changeling_counts_as_the_granted_type(self):
        result = detect_zone_granted_abilities(_BLOODLINE_PRETENDER, _THRANDUIL)
        assert result["card_matches_type"] is True

    def test_off_type_card_reports_no_abilities(self):
        result = detect_zone_granted_abilities(_DOOR_OF_DESTINIES, _THRANDUIL)
        assert result["grants"] is True
        assert result["card_matches_type"] is False
        assert result["abilities"] == []

    def test_run_cut_check_surfaces_the_flag(self):
        hydrated = [_THRANDUIL, _PRIEST_OF_TITANIA, _DOOR_OF_DESTINIES]
        results = run_cut_check(
            hydrated=hydrated,
            commander_name="Thranduil, the Elvenking",
            cut_names=["Priest of Titania", "Door of Destinies"],
            trigger_types=[],
            multiplier_low=1,
            multiplier_high=2,
            opponents=1,
        )
        by_name = {r["name"]: r for r in results}
        assert by_name["Priest of Titania"]["zone_granted_abilities"]["abilities"]
        assert not by_name["Door of Destinies"]["zone_granted_abilities"]["abilities"]

    def test_report_names_the_grant(self):
        hydrated = [_THRANDUIL, _PRIEST_OF_TITANIA]
        results = run_cut_check(
            hydrated=hydrated,
            commander_name="Thranduil, the Elvenking",
            cut_names=["Priest of Titania"],
            trigger_types=[],
            multiplier_low=1,
            multiplier_high=2,
            opponents=1,
        )
        report = render_text_report(
            results,
            commander_name="Thranduil, the Elvenking",
            multiplier_low=1,
            multiplier_high=2,
            opponents=1,
        )
        assert "ZONE_GRANTED" in report
        assert "1 zone-granted" in report
        assert "removes a tool from the commander" in report


class TestExtractActivatedAbilities:
    """The non-mana extractor and the zone-grant extractor share one
    implementation; only the mana-ability filter differs between them."""

    def test_non_mana_cost_is_still_an_activated_ability(self):
        """Regression: a rule keyed on "{...}" in the cost dropped these."""
        assert _extract_activated_abilities(_IRON_SHIELD_ELF["oracle_text"]) == [
            _activated_ability_lines(_IRON_SHIELD_ELF["oracle_text"])[0]
        ]

    def test_mana_abilities_excluded_here_and_included_there(self):
        text = _PRIEST_OF_TITANIA["oracle_text"]
        assert _extract_activated_abilities(text) == []
        assert _activated_ability_lines(text) == [
            "{T}: Add {G} for each Elf on the battlefield."
        ]

    def test_triggered_abilities_are_not_activated_abilities(self):
        assert _extract_activated_abilities(_THRANDUIL["oracle_text"]) == []

    def test_loyalty_abilities_are_not_activated_abilities(self):
        oracle = "[+1]: Draw a card.\n[−3]: Destroy target creature."
        assert _activated_ability_lines(oracle) == []
