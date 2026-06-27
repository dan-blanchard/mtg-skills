"""Unit tests for the nom-mirror parser-combinator core."""

import re

from mtg_utils._card_ir._combinators import (
    alt,
    keyword,
    many,
    opt,
    phrase,
    preceded,
    regex_word,
    satisfy,
    scan,
    succeed,
    tag,
    take_until,
    value,
    word,
    ws,
)


class TestPrimitives:
    def test_tag_case_insensitive_by_default(self):
        assert tag("create ").parse("Create a token") == ("Create ", "a token")
        assert tag("create ").parse("nope") is None

    def test_tag_case_sensitive(self):
        assert tag("X", ci=False).parse("X/X") == ("X", "/X")
        assert tag("x", ci=False).parse("X/X") is None

    def test_take_until(self):
        assert take_until(" token").parse("a 1/1 Bird token here") == (
            "a 1/1 Bird",
            " token here",
        )
        assert take_until(" token").parse("no match") is None

    def test_ws_always_succeeds(self):
        assert ws().parse("   hi") == (None, "hi")
        assert ws().parse("hi") == (None, "hi")

    def test_word_skips_leading_ws(self):
        assert word().parse("  Goblin rest") == ("Goblin", " rest")
        assert word().parse("   ") is None

    def test_keyword_normalizes_and_filters(self):
        p = keyword({"white", "blue"})
        assert p.parse("white Soldier") == ("white", " Soldier")
        # punctuation stripped before matching; normalized form returned
        assert p.parse("White, ") == ("white", " ")
        assert p.parse("Goblin") is None

    def test_satisfy(self):
        digit = satisfy(str.isdigit)
        assert digit.parse("3 tokens") == ("3", " tokens")
        assert digit.parse("three") is None

    def test_regex_word(self):
        pt = regex_word(re.compile(r"[\dx*]+/[\dx*]+", re.IGNORECASE))
        assert pt.parse("1/1 white") == ("1/1", " white")
        assert pt.parse("X/X red") == ("X/X", " red")
        assert pt.parse("white") is None


class TestCombinators:
    def test_alt_first_success(self):
        p = alt(tag("ab"), tag("cd"))
        assert p.parse("cdef") == ("cd", "ef")
        assert p.parse("xy") is None

    def test_or_operator_is_alt(self):
        p = tag("ab") | tag("cd")
        assert p.parse("cdef") == ("cd", "ef")

    def test_opt_never_fails(self):
        assert opt(tag("ab")).parse("xy") == (None, "xy")
        assert opt(tag("ab")).parse("abxy") == ("ab", "xy")

    def test_many_collects_until_no_progress(self):
        p = many(keyword({"and", "white", "blue"}))
        vals, rest = p.parse("white and blue Bird")
        assert vals == ["white", "and", "blue"]
        assert rest.strip() == "Bird"

    def test_many_zero(self):
        assert many(tag("z")).parse("abc") == ([], "abc")

    def test_value_replaces_output(self):
        assert value(7, tag("x")).parse("xyz") == (7, "yz")

    def test_preceded_discards_prefix(self):
        p = preceded(tag("create "), word())
        assert p.parse("create Goblin x") == ("Goblin", " x")
        assert p.parse("nope") is None

    def test_map(self):
        assert word().map(str.upper).parse("hi there") == ("HI", " there")

    def test_succeed_consumes_nothing(self):
        assert succeed(42).parse("abc") == (42, "abc")


class TestPhrase:
    def test_phrase_matches_consecutive_word_bags(self):
        p = phrase({"creature", "creatures"}, {"you"}, {"control", "own"})
        vals, rest = p.parse("creatures you control with base power")
        assert vals == ["creatures", "you", "control"]
        assert rest.strip().startswith("with")

    def test_phrase_per_slot_alternation(self):
        p = phrase({"creature", "creatures"}, {"you"}, {"control", "own"})
        assert p.parse("creature you own a thing")[0] == ["creature", "you", "own"]

    def test_phrase_fails_on_missing_slot(self):
        p = phrase({"opponent", "opponents"}, {"cant"}, {"cast"})
        # normalization folds the apostrophe: "can't" -> "cant"
        assert p.parse("opponents can't cast spells") is not None
        assert p.parse("opponents may cast spells") is None

    def test_phrase_anchors_at_head_not_mid(self):
        # phrase does NOT search — it anchors at the input head (scan adds search).
        p = phrase({"base"}, {"power"})
        assert p.parse("with base power") is None
        assert p.parse("base power 2") is not None


class TestScan:
    def test_scan_finds_phrase_mid_clause(self):
        p = scan(phrase({"base"}, {"power"}))
        assert p.parse("creatures you control with base power 2") is not None

    def test_scan_retries_past_a_false_lead(self):
        # the first "becomes" is not followed by "untapped"; a later one is — scan
        # must advance past the false lead (a plain find-then-check would miss it).
        p = scan(phrase({"become", "becomes"}, {"untapped"}))
        assert p.parse("becomes the target. it becomes untapped") is not None

    def test_scan_returns_tail_after_the_match(self):
        p = scan(phrase({"devotion"}, {"to"}))
        vals, rest = p.parse("your devotion to black is high")
        assert vals == ["devotion", "to"]
        assert rest.strip().startswith("black")

    def test_scan_fails_when_absent(self):
        assert scan(phrase({"historic"})).parse("a history lesson") is None
