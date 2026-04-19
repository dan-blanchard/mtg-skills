"""Tests for Comprehensive Rules parser and lookup CLI."""

from __future__ import annotations

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
# subrules, examples, glossary entries (single- and multi-line), and
# the terminal Credits block we must ignore.
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

    Glossary
    Credits

    1. Game Concepts

    100. General

    100.1. This is the first top-level rule.

    100.1a This is the first subrule.
    Example: This is an example for 100.1a.

    100.1b Second subrule. See rule 600.1.

    100.2. Second rule.
    Example: First example.
    Example: Second example.

    2. Spells

    600. Spells

    600.1. Casting a spell is defined here.

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
        assert set(parsed["sections"]) == {"1", "2"}
        assert parsed["sections"]["1"]["title"] == "Game Concepts"
        assert parsed["sections"]["2"]["title"] == "Spells"

    def test_categories_attached_to_sections(self, rules_text):
        parsed = parse_rules(rules_text)
        assert parsed["sections"]["1"]["categories"] == ["100"]
        assert parsed["sections"]["2"]["categories"] == ["600"]

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
