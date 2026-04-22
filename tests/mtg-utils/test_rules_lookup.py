"""Tests for Comprehensive Rules parser and lookup CLI."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.rules_lookup import (
    find_citations_for_terms,
    grep_rules,
    load_rules,
    lookup_rule,
    lookup_term,
    main,
    parse_rules,
    resolve_rules_path,
)

# A minimal but structurally-complete CR fixture covering every shape the
# parser needs to handle: sections, categories, top-level rules,
# subrules, examples, glossary entries (single- and multi-line), CR
# formatting quirks (missing period / missing space after rule number;
# trailing period after a subrule letter), bare numerics in prose (to
# exercise the see_rules false-positive filter), and the terminal
# Credits block we must ignore.
_FIXTURE = textwrap.dedent(
    """\
    Magic: The Gathering Comprehensive Rules

    These rules are effective as of February 2, 2024

    Introduction

    Blurb.

    Contents

    1. Game Concepts
    100. General

    2. Spells
    600. Spells

    9. Casual Variants
    900. Quirks

    Glossary
    Credits

    1. Game Concepts

    100. General

    100.1. This is the first top-level rule.

    100.1a This is the first subrule.
    Example: This is an example for 100.1a.

    100.1b Second subrule. See rule 600.1.

    100.2. Second rule. A creature deals 3 damage to each of 200 players.
    Example: First example.
    Example: Second example.

    2. Spells

    600. Spells

    600.1. Casting a spell is defined here.

    600.2 Missing-period rule text (CR sometimes drops the period).

    600.3.No-space rule text (CR sometimes drops the trailing space).

    9. Casual Variants

    900. Quirks

    900.1a. Trailing-period subrule (CR sometimes keeps the period after the letter).

    Glossary

    Ability
    1. Text on an object.
    2. An activated or triggered ability on the stack.
    See rule 600, "Spells."

    Trample
    A keyword ability. See rule 100.1a.

    Credits

    Magic: The Gathering Original Game Design: Richard Garfield
    """
)


@pytest.fixture
def rules_text() -> str:
    return _FIXTURE


@pytest.fixture
def rules_file(tmp_path: Path, rules_text: str) -> Path:
    path = tmp_path / "comprehensive-rules-20240202.txt"
    path.write_text(rules_text, encoding="utf-8")
    return path


class TestParseRules:
    def test_extracts_effective_date(self, rules_text):
        parsed = parse_rules(rules_text)
        assert parsed["effective_date"] == "February 2, 2024"

    def test_all_sections_present(self, rules_text):
        parsed = parse_rules(rules_text)
        assert set(parsed["sections"]) == {"1", "2", "9"}
        assert parsed["sections"]["1"]["title"] == "Game Concepts"
        assert parsed["sections"]["2"]["title"] == "Spells"
        assert parsed["sections"]["9"]["title"] == "Casual Variants"

    def test_categories_attached_to_sections(self, rules_text):
        parsed = parse_rules(rules_text)
        assert parsed["sections"]["1"]["categories"] == ["100"]
        assert parsed["sections"]["2"]["categories"] == ["600"]
        assert parsed["sections"]["9"]["categories"] == ["900"]

    def test_top_level_rule_text(self, rules_text):
        parsed = parse_rules(rules_text)
        rule = parsed["rules"]["100.1"]
        assert rule["kind"] == "rule"
        assert rule["text"].startswith("This is the first top-level rule")
        assert rule["section"] == "1"
        assert rule["category"] == "100"

    def test_subrule_has_parent(self, rules_text):
        parsed = parse_rules(rules_text)
        rule = parsed["rules"]["100.1a"]
        assert rule["kind"] == "subrule"
        assert rule["parent"] == "100.1"

    def test_examples_attached_to_nearest_rule(self, rules_text):
        parsed = parse_rules(rules_text)
        assert parsed["rules"]["100.1a"]["examples"] == [
            "This is an example for 100.1a.",
        ]
        assert parsed["rules"]["100.2"]["examples"] == [
            "First example.",
            "Second example.",
        ]

    def test_cross_references_extracted(self, rules_text):
        parsed = parse_rules(rules_text)
        # 100.1b says "See rule 600.1" — should be in see_rules.
        assert "600.1" in parsed["rules"]["100.1b"]["see_rules"]

    def test_glossary_parsed(self, rules_text):
        parsed = parse_rules(rules_text)
        assert "trample" in parsed["glossary"]
        entry = parsed["glossary"]["trample"]
        assert entry["term"] == "Trample"
        assert "100.1a" in entry["see_rules"]

    def test_multiline_glossary_entry(self, rules_text):
        parsed = parse_rules(rules_text)
        entry = parsed["glossary"]["ability"]
        assert "activated or triggered" in entry["definition"]
        assert "600" in entry["see_rules"]

    def test_credits_not_mistaken_for_glossary(self, rules_text):
        parsed = parse_rules(rules_text)
        # "Magic: The Gathering Original Game Design" must NOT appear as
        # a glossary term — the parser stops at "Credits".
        for term in parsed["glossary"]:
            assert "richard garfield" not in term.lower()

    def test_raises_on_malformed_input(self):
        with pytest.raises(ValueError, match="Could not find body start"):
            parse_rules("no rules body here")

    def test_rule_with_missing_period(self, rules_text):
        """CR occasionally formats top-level rules without a period
        after the number ("600.5 If the total cost..."). The parser
        must still index them."""
        parsed = parse_rules(rules_text)
        r = parsed["rules"].get("600.2")
        assert r is not None
        assert r["kind"] == "rule"
        assert "Missing-period rule text" in r["text"]

    def test_rule_with_missing_space(self, rules_text):
        """CR occasionally formats top-level rules without a space
        after the period ("901.4.All plane and phenomenon..."). The
        parser must still index them and strip the run-on text
        correctly."""
        parsed = parse_rules(rules_text)
        r = parsed["rules"].get("600.3")
        assert r is not None
        assert r["text"].startswith("No-space rule text")

    def test_subrule_with_trailing_period(self, rules_text):
        """CR occasionally formats subrules with a period after the
        letter ("119.1d. In a two-player Brawl game..."). The parser
        must match these as subrules, not as top-level rules with the
        letter as part of the text."""
        parsed = parse_rules(rules_text)
        r = parsed["rules"].get("900.1a")
        assert r is not None
        assert r["kind"] == "subrule"
        assert r["text"].startswith("Trailing-period subrule")
        # Critical: the letter-stripped parent must not accidentally
        # pick up the trailing period.
        assert r["parent"] == "900.1"

    def test_bare_numbers_in_prose_filtered_from_see_rules(self, rules_text):
        """Rule text containing bare 3-digit numbers that happen to
        look like rule numbers ("200 players", "300 damage") must NOT
        pollute see_rules with references to nonexistent rules."""
        parsed = parse_rules(rules_text)
        r = parsed["rules"]["100.2"]
        # Fixture has "200 players" in 100.2's text; 200 is not a real
        # rule in the fixture, so it must be filtered out.
        assert "200" not in r["see_rules"]
        assert "3" not in r["see_rules"]  # damage value


class TestLoadRulesCache:
    def test_cache_roundtrip(self, rules_file):
        # First call parses from source.
        parsed1 = load_rules(rules_file)
        sidecar = rules_file.with_name(rules_file.name + ".parsed.pkl")
        assert sidecar.exists()
        # Second call hits the cache and returns equivalent content.
        parsed2 = load_rules(rules_file)
        assert parsed1.keys() == parsed2.keys()
        assert parsed1["rules"].keys() == parsed2["rules"].keys()

    def test_cache_invalidated_on_source_change(self, rules_file, rules_text):
        load_rules(rules_file)
        sidecar = rules_file.with_name(rules_file.name + ".parsed.pkl")
        first_mtime = sidecar.stat().st_mtime
        # Rewrite the source with newer content; file mtime must now be
        # newer than the sidecar's, invalidating the cache.
        import os
        import time

        new_text = rules_text + "\n\n"
        rules_file.write_text(new_text, encoding="utf-8")
        future = time.time() + 5
        os.utime(rules_file, (future, future))

        load_rules(rules_file)
        # Sidecar has been rewritten.
        assert sidecar.stat().st_mtime >= first_mtime


class TestQueries:
    def test_lookup_rule_hit(self, rules_file):
        parsed = load_rules(rules_file)
        r = lookup_rule(parsed, "100.1a")
        assert r is not None
        assert r["kind"] == "subrule"

    def test_lookup_rule_miss_returns_none(self, rules_file):
        parsed = load_rules(rules_file)
        assert lookup_rule(parsed, "999.99z") is None

    def test_lookup_term_case_insensitive(self, rules_file):
        parsed = load_rules(rules_file)
        assert lookup_term(parsed, "TRAMPLE")["term"] == "Trample"
        assert lookup_term(parsed, "trample")["term"] == "Trample"

    def test_lookup_term_miss_returns_none(self, rules_file):
        parsed = load_rules(rules_file)
        assert lookup_term(parsed, "nonexistent keyword") is None

    def test_grep_limit_respected(self, rules_file):
        parsed = load_rules(rules_file)
        matches = grep_rules(parsed, "rule", limit=1)
        assert len(matches) == 1

    def test_grep_invalid_regex_raises(self, rules_file):
        parsed = load_rules(rules_file)
        with pytest.raises(ValueError, match="Invalid regex"):
            grep_rules(parsed, "(")

    def test_find_citations_for_terms(self, rules_file):
        parsed = load_rules(rules_file)
        citations = find_citations_for_terms(parsed, ["trample", "unknown_keyword"])
        assert any(c["term"] == "Trample" for c in citations)
        assert all(c["rule"] == "100.1a" for c in citations if c["term"] == "Trample")


class TestResolveRulesPath:
    def test_explicit_path_used(self, tmp_path):
        p = tmp_path / "comprehensive-rules-20240101.txt"
        p.write_text("stub", encoding="utf-8")
        assert resolve_rules_path(p) == p

    def test_explicit_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_rules_path(tmp_path / "nope.txt")

    def test_glob_finds_newest(self, tmp_path):
        old = tmp_path / "comprehensive-rules-20230101.txt"
        new = tmp_path / "comprehensive-rules-20240101.txt"
        old.write_text("old", encoding="utf-8")
        new.write_text("new", encoding="utf-8")
        assert resolve_rules_path(None, cwd=tmp_path) == new

    def test_no_glob_match_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No comprehensive-rules"):
            resolve_rules_path(None, cwd=tmp_path)

    def test_input_path_dir_checked_before_cwd(self, tmp_path):
        """Regression pin: under ``uv run --directory <skill>``, ``cwd``
        is rebased away from the user's working dir. The CR the agent
        just downloaded (next to the deck/hydrated JSON) must still be
        found. Search order: input-file dir first, cwd second."""
        working = tmp_path / "working"
        skill_cwd = tmp_path / "skill"
        working.mkdir()
        skill_cwd.mkdir()
        cr = working / "comprehensive-rules-20260227.txt"
        cr.write_text("stub", encoding="utf-8")
        # No CR in skill_cwd — mimics the uv run --directory scenario.
        hydrated = working / "hydrated.json"
        hydrated.write_text("{}")
        assert resolve_rules_path(None, cwd=skill_cwd, input_path=hydrated) == cr

    def test_input_path_accepts_dir(self, tmp_path):
        """Callers can pass a directory directly instead of a file."""
        cr = tmp_path / "comprehensive-rules-20260227.txt"
        cr.write_text("stub", encoding="utf-8")
        assert resolve_rules_path(None, input_path=tmp_path) == cr

    def test_error_message_lists_searched_paths(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        hydrated = a / "hydrated.json"
        hydrated.write_text("{}")
        with pytest.raises(FileNotFoundError) as exc:
            resolve_rules_path(None, cwd=b, input_path=hydrated)
        assert str(a) in str(exc.value)
        assert str(b) in str(exc.value)


class TestCLI:
    def test_cli_rule_lookup(self, rules_file):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--rule", "100.1a", "--rules-file", str(rules_file)],
        )
        assert result.exit_code == 0, result.output
        assert "100.1a" in result.output
        assert "Full JSON:" in result.output

    def test_cli_term_lookup(self, rules_file):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--term", "trample", "--rules-file", str(rules_file)],
        )
        assert result.exit_code == 0, result.output
        assert "Trample" in result.output

    def test_cli_grep(self, rules_file):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--grep", "spell", "--rules-file", str(rules_file), "--limit", "5"],
        )
        assert result.exit_code == 0, result.output
        assert "600" in result.output

    def test_cli_requires_exactly_one_mode(self, rules_file):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--rule",
                "100.1a",
                "--term",
                "trample",
                "--rules-file",
                str(rules_file),
            ],
        )
        assert result.exit_code != 0
        assert "exactly one" in result.output.lower()

    def test_cli_rule_miss_still_exits_zero(self, rules_file):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--rule", "999.99", "--rules-file", str(rules_file)],
        )
        # Data producers exit 0; callers inspect JSON for match=None.
        assert result.exit_code == 0, result.output
        assert "no rule" in result.output.lower()

    def test_cli_writes_json_sidecar(self, rules_file):
        from conftest import json_from_cli_output

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["--rule", "100.1a", "--rules-file", str(rules_file)],
        )
        assert result.exit_code == 0, result.output
        data = json_from_cli_output(result)
        assert data["match"]["number"] == "100.1a"
        assert data["effective_date"] == "February 2, 2024"


class TestRealCR:
    """Real-CR tests: parse the actual 2024 Comprehensive Rules text
    (fetched by the ``real_cr_path`` session fixture) and assert
    invariants that must hold against the real document, not just our
    miniaturized hand-rolled fixture.

    Catches parser drift against formatting changes in the real CR —
    the synthetic fixture can't surface unknown-unknowns like the
    ``119.1d.`` trailing-period bug fixed after the initial review.
    """

    def test_structural_invariants(self, real_cr_path):
        """Tier 1: parser sanity. Exact counts are fragile across CR
        updates, so we assert lower bounds that would only break if the
        parser itself regressed (not if Wizards added a new section)."""
        parsed = load_rules(real_cr_path)

        # 9 top-level sections — this is stable across CR versions
        # going back decades.
        assert set(parsed["sections"]) == {str(i) for i in range(1, 10)}
        assert parsed["sections"]["1"]["title"] == "Game Concepts"
        assert parsed["sections"]["7"]["title"] == "Additional Rules"

        # The CR has ~3000 rules; anything under 2000 indicates a
        # parser regression that ate whole categories.
        assert len(parsed["rules"]) >= 2000, f"only {len(parsed['rules'])} rules parsed"

        # The glossary has ~670 entries; under 500 means a parser bug.
        assert len(parsed["glossary"]) >= 500

        # Effective-date line must have been extracted.
        assert parsed["effective_date"]

    def test_known_rules_indexed(self, real_cr_path):
        """Tier 1: specific well-known rule numbers and glossary terms
        must be present. Regressing any of these means the parser
        dropped them silently."""
        parsed = load_rules(real_cr_path)

        # Keyword ability subrules
        assert parsed["rules"].get("702.19a") is not None, "trample missing"
        assert parsed["rules"].get("702.4a") is not None, "double strike missing"
        assert parsed["rules"].get("702.2a") is not None, "deathtouch missing"

        # Top-level rules
        assert parsed["rules"].get("603.2") is not None, "triggered abilities"

        # Category headers (no subrule suffix)
        assert parsed["rules"].get("903") is not None, "commander category"

        # Real CR formatting quirks the relaxed regexes now catch
        # (see commit message of the parser-robustness fix).
        assert parsed["rules"].get("119.1d") is not None, (
            "trailing-period subrule regressed"
        )
        assert parsed["rules"].get("606.5") is not None, "missing-period rule regressed"
        assert parsed["rules"].get("901.4") is not None, "missing-space rule regressed"

        # Glossary terms — case-insensitive keys.
        for term in ("trample", "double strike", "deathtouch", "menace", "hexproof"):
            assert term in parsed["glossary"], f"glossary missing {term!r}"

    def test_zero_unresolved_cross_references(self, real_cr_path):
        """Tier 2: regression pin for I-2's post-filter. Every
        ``see_rules`` entry — in rules and glossary alike — must
        resolve to a real indexed rule. A non-zero count means the
        filter broke and bare numerics from prose are polluting
        citations again."""
        parsed = load_rules(real_cr_path)
        rule_keys = set(parsed["rules"])

        unresolved_from_rules = [
            (num, ref)
            for num, entry in parsed["rules"].items()
            for ref in entry.get("see_rules", [])
            if ref not in rule_keys
        ]
        assert unresolved_from_rules == [], (
            f"rules have unresolved see_rules: {unresolved_from_rules[:5]}"
        )

        unresolved_from_glossary = [
            (term, ref)
            for term, entry in parsed["glossary"].items()
            for ref in entry["see_rules"]
            if ref not in rule_keys
        ]
        assert unresolved_from_glossary == [], (
            f"glossary has unresolved see_rules: {unresolved_from_glossary[:5]}"
        )

    def test_trample_glossary_points_at_real_rule(self, real_cr_path):
        """Tier 2 spot-check: follow a glossary → rule cross-reference
        end-to-end against the real document."""
        parsed = load_rules(real_cr_path)
        trample = parsed["glossary"]["trample"]
        assert "702.19" in trample["see_rules"]
        # The referenced category must exist.
        assert parsed["rules"].get("702.19") is not None

    def test_cite_rules_end_to_end(self, real_cr_path, trigger_test_cards, tmp_path):
        """Tier 3: run ``cut-check --cite-rules`` against real hydrated
        cards and the real CR. Asserts the whole cite-rules pipeline —
        downloader-agnostic parse → keyword-interaction detection →
        glossary lookup → citation attachment — produces a coherent
        result against the actual published rules, not just our
        fixture."""
        from click.testing import CliRunner

        from mtg_utils.cut_check import main as cut_check_main

        hydrated_path = tmp_path / "hydrated.json"
        hydrated_path.write_text(json.dumps(trigger_test_cards))
        cuts_path = tmp_path / "cuts.json"
        # Blocking Restrictor (trample + can't-be-blocked-by-more-than-one)
        # against Obeka (menace commander) produces two keyword
        # interactions, each citing a real CR rule.
        cuts_path.write_text(json.dumps(["Blocking Restrictor", "Double Striker"]))
        output_path = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            cut_check_main,
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
                str(real_cr_path),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(output_path.read_text(encoding="utf-8"))

        # Collect all citations across all analysed cards.
        all_citations = [c for entry in data for c in entry.get("rule_citations", [])]
        assert all_citations, "no citations attached — wiring is broken"

        # Every citation must reference a real CR rule (format like
        # "702.19", "702.4") with a non-empty snippet.
        for c in all_citations:
            assert c["rule"], c
            assert c["snippet"], c
            # Rule numbers in the real CR are always digit.digit or
            # digit.digit-letter; the stub fixture uses 702.19-style
            # numbers, so a regex digit-dot-digit check is sufficient
            # to catch malformed citations.
            assert c["rule"].split(".")[0].isdigit()

        cited_terms = {c["term"].lower() for c in all_citations}
        # At least one of the expected keyword glossary hits must land.
        assert cited_terms & {
            "trample",
            "menace",
            "double strike",
            "deathtouch",
        }, f"no expected keyword cited: {cited_terms}"
