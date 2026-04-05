"""Tests for cut_check.py — mechanical pre-grill analysis."""

from __future__ import annotations

import json

from commander_utils.cut_check import (
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
    def test_outputs_valid_json(self, trigger_test_cards, tmp_path):
        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Upkeep Drainer"]))
        from click.testing import CliRunner

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
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "Upkeep Drainer"
