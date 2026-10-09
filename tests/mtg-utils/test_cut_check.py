"""Tests for cut_check.py — mechanical pre-grill analysis, read off phase's trees.

Every card is real (ADR-0056); each expectation follows the card's oracle text, its
rulings and the CR rule cited beside it.
"""

from __future__ import annotations

import json

import pytest

from mtg_utils._card_ir.crosswalk.reads import TRIGGER_KINDS, activated_ability_units
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.cut_check import (
    commander_profile,
    detect_commander_multiplication,
    detect_keyword_interactions,
    detect_self_recurring,
    detect_triggers,
    detect_zone_granted_abilities,
    main,
    render_text_report,
    run_cut_check,
)
from mtg_utils.testkit import test_card

_ALL_TYPES = list(TRIGGER_KINDS)


def _obeka_deck(tmp_path, cards):
    """A deck JSON commanded by Obeka over every other fixture card, so the CLI reads
    the commander from the deck and hydrates the rest through --bulk-data."""
    commander = "Obeka, Splitter of Seconds"
    deck = {
        "format": "commander",
        "commanders": [{"name": commander, "quantity": 1}],
        "cards": [
            {"name": c["name"], "quantity": 1} for c in cards if c["name"] != commander
        ],
        "sideboard": [],
    }
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(deck), encoding="utf-8")
    return deck_path


def _triggers(name, trigger_types=_ALL_TYPES, opponents=3):
    return detect_triggers(
        test_card(name), trigger_types=list(trigger_types), opponents=opponents
    )


class TestDetectTriggers:
    def test_upkeep_trigger_with_a_fixed_value(self):
        (t,) = _triggers("Phyrexian Arena", ["upkeep"])
        assert t["matched_type"] == "upkeep"
        assert t["parseable"] is True
        assert t["base_value"] == "1"  # draws a card

    def test_type_filter(self):
        (t,) = _triggers("Phyrexian Arena", ["attack"])
        assert t["matches_trigger_type"] is False
        assert t["matched_type"] is None
        assert t["types"] == ["upkeep"]

    def test_attack_trigger_token_count(self):
        """Hero of Bladehold's own attack trigger makes two tokens; its battle cry
        is a second attack trigger (CR 702.91a) with no number to multiply."""
        triggers = _triggers("Hero of Bladehold", ["attack"])
        assert [t["matched_type"] for t in triggers] == ["attack", "attack"]
        assert sorted(t["base_value"] for t in triggers if t["parseable"]) == ["2"]

    def test_a_scaling_amount_is_not_parseable(self):
        """Dark Confidant's life loss is "equal to its mana value"."""
        (t,) = _triggers("Dark Confidant", ["upkeep"])
        assert t["matches_trigger_type"] is True
        assert t["parseable"] is False
        assert t["base_value"] == t["text"]

    @pytest.mark.parametrize(
        ("name", "value"),
        [("Purphoros, God of the Forge", "6"), ("Impact Tremors", "3")],
    )
    def test_damage_to_each_opponent_counts_per_opponent(self, name, value):
        (t,) = _triggers(name, ["etb"])
        assert t["base_value"] == value
        assert name.split(",")[0] in t["text"]  # phase's "~" reads as the name

    def test_when_it_dies_is_a_death_trigger(self):
        """Kokusho's "When ~ dies" (CR 700.4): "each opponent loses 5 life" is 5 per
        opponent."""
        (t,) = _triggers("Kokusho, the Evening Star", ["death"])
        assert t["matched_type"] == "death"
        assert t["base_value"] == "15"

    def test_enters_or_attacks_is_both(self):
        (t,) = _triggers("Sun Titan")
        assert t["types"] == ["etb", "attack"]

    def test_landfall_is_an_enters_trigger(self):
        """An ability word has no rules meaning (CR 207.2c): landfall is "whenever a
        land you control enters" (CR 603.6a)."""
        (t,) = _triggers("Rampaging Baloths", ["etb"])
        assert t["matched_type"] == "etb"
        assert t["base_value"] == "1"

    def test_the_end_step(self):
        (t,) = _triggers("Pestilence", ["endstep"])
        assert t["matched_type"] == "endstep"

    def test_combat_damage_trigger(self):
        (t,) = _triggers("Obeka, Splitter of Seconds", ["combat-damage"])
        assert t["matched_type"] == "combat-damage"

    def test_no_trees_no_triggers(self):
        """A card phase has no trees for gets no triggers — never a text guess."""
        card = {
            "name": "Unknown Card",
            "oracle_text": "At the beginning of your upkeep",
        }
        assert detect_triggers(card, trigger_types=_ALL_TYPES, opponents=3) == []


class TestDetectKeywordInteractions:
    _OBEKA = "Obeka, Splitter of Seconds"

    def test_menace_and_blocked_by_at_most_one(self):
        """Menace needs two or more blockers (CR 702.111b); the restrictions are
        cumulative (CR 509.1b), so no block is legal."""
        out = detect_keyword_interactions(
            test_card("Charging Rhino"), commander_profile(test_card(self._OBEKA))
        )
        assert [i["keywords"][0] for i in out] == ["menace"]

    def test_a_granted_blocking_limit_counts(self):
        out = detect_keyword_interactions(
            test_card("Full Steam Ahead"), commander_profile(test_card(self._OBEKA))
        )
        assert [i["keywords"][0] for i in out] == ["menace"]

    def test_double_strike_and_a_combat_damage_trigger(self):
        """A double striker deals combat damage in both steps (CR 702.4b)."""
        out = detect_keyword_interactions(
            test_card("Boros Swiftblade"), commander_profile(test_card(self._OBEKA))
        )
        assert [i["keywords"] for i in out] == [
            ["double strike", "combat damage trigger"]
        ]

    def test_trample_and_deathtouch(self):
        out = detect_keyword_interactions(
            test_card("Baleful Strix"),
            commander_profile(test_card("Ghalta, Primal Hunger")),
        )
        assert [i["keywords"] for i in out] == [["trample", "deathtouch"]]

    def test_no_interaction(self):
        assert (
            detect_keyword_interactions(
                test_card("Phyrexian Arena"), commander_profile(test_card(self._OBEKA))
            )
            == []
        )


class TestDetectSelfRecurring:
    @pytest.mark.parametrize(
        "name",
        [
            "Bloodghast",  # landfall: returns from the graveyard
            "Vengevine",
            "Prized Amalgam",
            "Gravecrawler",  # cast from the graveyard
            "Endless Cockroaches",  # dies: returns to hand
            "Arc Blade",  # its ruling: it suspends itself again
            "Arcanis the Omnipotent",  # returns itself to hand (the lane's decision)
            "Batterskull",
            "Greenbelt Rampager",
            "Grinning Ignus",  # a self-bounce cost
            "Whispers of the Muse",  # buyback, CR 702.27a
            "Kitchen Finks",  # persist, CR 702.79a
            "Pyre Zombie",  # "return it to your hand" from the graveyard
            "Epochrasite",  # dies: exiled with time counters, gains suspend
            "Staggershock",  # rebound, CR 702.88a
            "Anointer Priest",  # embalm, CR 702.128a
            "Dusk // Dawn",  # aftermath, CR 702.127a (the preset's keyword arm)
            "Sinister Concierge",  # dies: exiled with time counters, suspended
            "Trusty Boomerang",  # its granted ability returns it to hand
            "Escape Velocity",  # escape phase leaves as a residue, recovered
            "Nether Shadow",  # upkeep: from your graveyard onto the battlefield
            # Dash returns it to hand at the next end step (CR 702.109a).
            "Ragavan, Nimble Pilferer",
            "Warbringer",
            "Zurgo Bellstriker",
            "Mardu Scout",
        ],
    )
    def test_recurs(self, name):
        assert detect_self_recurring(test_card(name)) is True

    @pytest.mark.parametrize(
        "name",
        [
            "Unsummon",  # bounces something else
            "Man-o'-War",
            "Eternal Witness",  # returns another card
            "Gravedigger",
            "Aetherling",  # blinks itself: protection, not another use
            "Ancestral Vision",  # suspend is one delayed cast, CR 702.62a
            "Phyrexian Arena",
            "Sphinx of Uthuun",  # "put one pile into your hand": revealed cards
            "Memory Crystal",  # changes buyback costs; no buyback of its own
        ],
    )
    def test_does_not_recur(self, name):
        assert detect_self_recurring(test_card(name)) is False


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    "name",
    ["Dusk // Dawn", "Garza's Assassin", "Salvation Colossus", "Oscorp Industries"],
)
def test_self_recurring_keyword_gap_canary(name):
    """Retirement canary for the ``self-recurring`` preset's ``keywords`` arm
    (Aftermath, Recover, Unearth, Mayhem). Phase v0.94.0 drops Dawn's aftermath
    half, Garza's Assassin's recover, Salvation Colossus's unearth and Oscorp
    Industries' mayhem, so
    ``recurs_itself`` can't see them. Once it can, drop that keyword from the arm."""
    from mtg_utils._analysis.lanes import recurs_itself

    trees = trees_for(test_card(name))
    assert not any(recurs_itself(t) for t in trees), (
        f"self-recurring preset: RETIRE-READY for {name} — phase now parses its "
        "recursion; drop its keyword from the preset's keywords arm and this case."
    )


class TestActivatedAbilities:
    """The activated abilities that work on the battlefield (CR 602.1, 113.6b)."""

    @staticmethod
    def _count(name, *, include_mana=True):
        return sum(
            1
            for tree in trees_for(test_card(name))
            for _ in activated_ability_units(tree, include_mana=include_mana)
        )

    def test_hand_and_graveyard_abilities_are_out(self):
        """Cycling (CR 702.29a), ninjutsu (702.49a), suspend's special action
        (116.2f) and a graveyard ability work from another zone."""
        assert self._count("Ash Barrens") == 1  # its {T}: Add {C}
        assert self._count("Ninja of the Deep Hours") == 0
        assert self._count("Ancestral Vision") == 0
        assert self._count("Reassembling Skeleton") == 0

    def test_loyalty_and_equip_are_activated_abilities(self):
        """CR 606.1 (loyalty abilities are activated abilities), 702.6a (equip)."""
        assert self._count("Liliana of the Veil") == 3
        assert self._count("Batterskull") == 2

    def test_mana_abilities_on_request(self):
        assert self._count("Priest of Titania") == 1
        assert self._count("Priest of Titania", include_mana=False) == 0


class TestDetectCommanderMultiplication:
    _OBEKA = commander_profile(test_card("Obeka, Splitter of Seconds"))
    _KRENKO = commander_profile(test_card("Krenko, Mob Boss"))

    def test_helm_of_the_host_copies_the_commander(self):
        result = detect_commander_multiplication(
            test_card("Helm of the Host"), self._OBEKA
        )
        assert [c["type"] for c in result["commander_copy"]] == ["create_token_copy"]
        assert "isn't legendary" in result["commander_copy"][0]["clause"]
        assert result["legend_bypass"] is True  # CR 707.9b, 704.5j
        assert result["commander_triggers_affected"] == ["combat-damage"]

    def test_spark_double_becomes_a_copy(self):
        result = detect_commander_multiplication(test_card("Spark Double"), self._OBEKA)
        assert [c["type"] for c in result["commander_copy"]] == ["becomes_copy"]
        assert result["legend_bypass"] is True

    def test_strionic_resonator_copies_a_triggered_ability(self):
        result = detect_commander_multiplication(
            test_card("Strionic Resonator"), self._OBEKA
        )
        assert [c["type"] for c in result["ability_copy"]] == ["copy_triggered_ability"]
        assert result["commander_copy"] == []

    def test_panharmonicon_needs_an_enters_trigger(self):
        """Obeka has no enters trigger; Urza's own enters trigger is doubled (the
        Panharmonicon ruling)."""
        pan = test_card("Panharmonicon")
        assert detect_commander_multiplication(pan, self._OBEKA)["ability_copy"] == []
        result = detect_commander_multiplication(
            pan, commander_profile(test_card("Urza, Lord High Artificer"))
        )
        assert [c["type"] for c in result["ability_copy"]] == ["trigger_doubler"]

    def test_rings_needs_an_activated_ability(self):
        rings = test_card("Rings of Brighthearth")
        assert detect_commander_multiplication(rings, self._OBEKA)["ability_copy"] == []
        result = detect_commander_multiplication(rings, self._KRENKO)
        assert [c["type"] for c in result["ability_copy"]] == ["copy_activated_ability"]
        assert result["commander_activated_abilities"] == [
            (
                "{T}: Create X 1/1 red Goblin creature tokens, where X is the "
                "number of Goblins you control."
            )
        ]

    def test_kiki_jiki_cannot_copy_a_legendary_commander(self):
        result = detect_commander_multiplication(
            test_card("Kiki-Jiki, Mirror Breaker"), self._KRENKO
        )
        assert result["commander_copy"] == []

    def test_a_legend_rule_static_is_a_bypass(self):
        result = detect_commander_multiplication(
            test_card("Mirror Gallery"), self._KRENKO
        )
        assert result["legend_bypass"] is True

    def test_no_false_positive(self):
        result = detect_commander_multiplication(test_card("Counterspell"), self._OBEKA)
        assert result["commander_copy"] == []
        assert result["ability_copy"] == []
        assert result["legend_bypass"] is False


class TestRunCutCheck:
    def test_full_analysis(self, trigger_test_cards):
        results = run_cut_check(
            hydrated=trigger_test_cards,
            commander_name="Obeka, Splitter of Seconds",
            cut_names=[
                "Phyrexian Arena",
                "Charging Rhino",
                "Arc Blade",
                "Helm of the Host",
                "Strionic Resonator",
            ],
            trigger_types=["upkeep"],
            multiplier_low=3,
            multiplier_high=7,
            opponents=3,
        )
        by_name = {r["name"]: r for r in results}
        (arena,) = by_name["Phyrexian Arena"]["triggers"]
        assert (arena["multiplied_low"], arena["multiplied_high"]) == ("3", "7")
        assert by_name["Charging Rhino"]["keyword_interactions"]
        assert by_name["Arc Blade"]["self_recurring"] is True
        helm = by_name["Helm of the Host"]["commander_multiplication"]
        assert helm["commander_copy"]
        resonator = by_name["Strionic Resonator"]["commander_multiplication"]
        assert resonator["ability_copy"]


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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps([{"name": "Phyrexian Arena", "quantity": 1}]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        assert "Phyrexian Arena" in result.output

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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps([{"quantity": 1}]))  # missing name
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(
            json.dumps(
                [
                    "Phyrexian Arena",
                    {"name": "Charging Rhino", "quantity": 1},
                ]
            )
        )
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        assert "Phyrexian Arena" in result.output
        assert "Charging Rhino" in result.output


class TestCLI:
    def test_text_report_and_json_file(self, trigger_test_cards, tmp_path):
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Phyrexian Arena"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        assert "Phyrexian Arena" in result.output
        assert "Full JSON:" in result.output
        assert "Obeka, Splitter of Seconds" in result.output

        # Strict structural correctness via the JSON file
        data = json_from_cli_output(result)
        assert len(data) == 1
        assert data[0]["name"] == "Phyrexian Arena"
        assert output_path.exists()

    def test_flags_commander_multiplication_in_text_report(
        self, trigger_test_cards, tmp_path
    ):
        from click.testing import CliRunner

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(
            json.dumps(["Helm of the Host", "Strionic Resonator", "Phyrexian Arena"])
        )
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Phyrexian Arena"]))

        runner = CliRunner()
        args = [
            str(deck_path),
            "--bulk-data",
            str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Charging Rhino"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        # Obeka's menace + Charging Rhino's "can't be blocked by more than one
        # creature" cite menace.
        citations = data[0].get("rule_citations") or []
        cited_terms = {c["term"] for c in citations}
        assert "Menace" in cited_terms

    def test_cite_rules_missing_file_is_soft_error(self, trigger_test_cards, tmp_path):
        """Missing CR file should record an error field, not crash."""
        from click.testing import CliRunner
        from conftest import json_from_cli_output

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Charging Rhino"]))
        output_path = tmp_path / "out.json"
        missing_rules = tmp_path / "nope.txt"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Charging Rhino"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        # No --cite-rules flag (relies on default-on) and no
        # --rules-file (relies on input-dir search).
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Charging Rhino"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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
        deck_path = _obeka_deck(tmp_path, trigger_test_cards)
        cuts_path = tmp_path / "cuts.json"
        cuts_path.write_text(json.dumps(["Charging Rhino"]))
        output_path = tmp_path / "out.json"
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(deck_path),
                "--bulk-data",
                str(hydrated_path),
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

_THRANDUIL = test_card("Thranduil, the Elvenking")
_THRANDUIL_CMD = commander_profile(_THRANDUIL)
_OBEKA_CMD = commander_profile(test_card("Obeka, Splitter of Seconds"))
_PRIEST_OF_TITANIA = test_card("Priest of Titania")
_IRON_SHIELD_ELF = test_card("Iron-Shield Elf")
_LATHRIL = test_card("Lathril, Blade of the Elves")
_BLOODLINE_PRETENDER = test_card("Bloodline Pretender")
_DOOR_OF_DESTINIES = test_card("Door of Destinies")


class TestDetectZoneGrantedAbilities:
    def test_no_grant_on_ordinary_commander(self):
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _OBEKA_CMD)
        assert result == {"grants": False}

    def test_parses_granted_type_and_zone(self):
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _THRANDUIL_CMD)
        assert result["grants"] is True
        assert result["granted_type"] == "Elf"
        assert result["zone"] == "graveyard"

    def test_mana_ability_is_reported(self):
        """A mana ability is what a zone-granting commander mostly borrows."""
        result = detect_zone_granted_abilities(_PRIEST_OF_TITANIA, _THRANDUIL_CMD)
        assert result["abilities"] == ["{T}: Add {G} for each Elf on the battlefield."]

    def test_non_mana_symbol_cost_is_reported(self):
        """ "Discard a card:" has no mana symbol but is still an activated ability
        (CR 602.1)."""
        result = detect_zone_granted_abilities(_IRON_SHIELD_ELF, _THRANDUIL_CMD)
        assert len(result["abilities"]) == 1
        assert result["abilities"][0].startswith("Discard a card:")

    def test_triggered_abilities_are_not_activated(self):
        """Lathril has one activated ability; its combat-damage line is triggered."""
        result = detect_zone_granted_abilities(_LATHRIL, _THRANDUIL_CMD)
        assert len(result["abilities"]) == 1
        assert result["abilities"][0].startswith("{T}, Tap ten untapped Elves")

    @pytest.mark.parametrize(
        "name", ["Bloodline Pretender", "Mirror Entity", "Chameleon Colossus"]
    )
    def test_changeling_counts_as_the_granted_type(self, name):
        """Changeling is every creature type and works in every zone (CR 702.73a,
        604.3) — Mirror Entity in the graveyard is an Elf card."""
        result = detect_zone_granted_abilities(test_card(name), _THRANDUIL_CMD)
        assert result["card_matches_type"] is True

    def test_hand_only_abilities_are_not_borrowed(self):
        """Forestcycling works only from its card's hand (CR 702.29a), so Thranduil
        can't activate it on the battlefield; the mana ability it can."""
        result = detect_zone_granted_abilities(
            test_card("Elvish Aberration"), _THRANDUIL_CMD
        )
        assert result["abilities"] == ["{T}: Add {G}{G}{G}."]

    def test_off_type_card_reports_no_abilities(self):
        result = detect_zone_granted_abilities(_DOOR_OF_DESTINIES, _THRANDUIL_CMD)
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
