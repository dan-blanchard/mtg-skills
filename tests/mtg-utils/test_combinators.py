"""Unit tests for the nom-mirror parser-combinator core."""

import re

from mtg_utils._card_ir._combinators import (
    alt,
    bounded_scan,
    keyword,
    keyword_bounded,
    many,
    opt,
    phrase,
    preceded,
    regex_word,
    satisfy,
    scan,
    seq,
    seq2,
    seq3,
    signed_word,
    succeed,
    tag,
    take_until,
    take_until_clause,
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


class TestKeywordBounded:
    def test_matches_ability_word_fused_by_em_dash(self):
        # norm_word glues "Morph—Discard" → "morphdiscard"; keyword misses, this hits.
        assert keyword({"morph"}).parse("Morph—Discard a card") is None
        assert keyword_bounded({"morph"}).parse("Morph—Discard a card")[0] == "morph"

    def test_plain_spaced_word_still_matches(self):
        assert keyword_bounded({"morph"}).parse("Morph {3}")[0] == "morph"

    def test_no_internal_boundary_is_not_a_hit(self):
        # "\bmorph\b" does not match inside "geomorph" (no boundary) — neither do we.
        assert keyword_bounded({"morph"}).parse("geomorph rules") is None


class TestSeq:
    def test_seq_variadic_collects_values(self):
        p = seq(keyword({"you"}), keyword({"may"}), keyword({"play"}))
        vals, rest = p.parse("you may play it")
        assert vals == ["you", "may", "play"]
        assert rest.strip() == "it"

    def test_seq_fails_on_any_slot(self):
        p = seq(keyword({"you"}), keyword({"may"}), keyword({"draw"}))
        assert p.parse("you may play it") is None

    def test_seq_mixes_parser_kinds(self):
        p = seq(keyword({"when"}), bounded_scan(keyword({"dies"})), keyword({"return"}))
        assert p.parse("when this creature dies return it") is not None


class TestBoundedScan:
    def test_bounded_scan_finds_target_within_clause(self):
        # "when ~ dies, return it" — the gap "this creature" carries no delimiter.
        p = seq2(keyword({"when"}), bounded_scan(phrase({"dies"})))
        assert p.parse("when this creature dies, return it") is not None

    def test_bounded_scan_stops_at_period(self):
        # the target sits in the NEXT sentence — the gap must not cross the period.
        p = seq2(keyword({"when"}), bounded_scan(phrase({"dies"})))
        assert p.parse("when you attack do this. a creature dies") is None

    def test_bounded_scan_stops_at_semicolon_and_quote(self):
        p = bounded_scan(phrase({"target"}))
        assert p.parse("does a thing; then target a creature") is None
        assert p.parse('gains "first strike" then target creature') is None

    def test_bounded_scan_matches_clause_final_word(self):
        # the delimiter rides the target word itself — still a hit (delim check is on
        # the SKIPPED gap words, not on where the parser matches).
        p = seq2(keyword({"return"}), bounded_scan(phrase({"battlefield"})))
        assert p.parse("return it to the battlefield.") is not None

    def test_bounded_scan_default_delims_allow_commas(self):
        # a comma is NOT a clause delimiter (regex [^.]* allows it).
        p = seq2(keyword({"when"}), bounded_scan(phrase({"dies"})))
        assert p.parse("when this, that, the other dies") is not None


class TestTakeUntilClause:
    def test_take_until_clause_captures_the_gap(self):
        gap, rest = take_until_clause().parse("this creature dies. next")
        assert gap.strip() == "this creature dies"
        assert rest.startswith(".")

    def test_take_until_clause_empty_gap(self):
        gap, rest = take_until_clause().parse(". rest")
        assert gap == ""
        assert rest.startswith(".")


class TestSignedWord:
    def test_signed_word_preserves_plus_vs_minus(self):
        # norm_word folds both to "1/1"; signed_word keeps them distinct.
        assert keyword({"1/1"}).parse("+1/+1 counter")[0] == "1/1"
        assert signed_word({"+1/+1"}).parse("+1/+1 counter")[0] == "+1/+1"
        assert signed_word({"+1/+1"}).parse("-1/-1 counter") is None
        assert signed_word({"-1/-1"}).parse("-1/-1 counter")[0] == "-1/-1"

    def test_signed_word_strips_trailing_punctuation(self):
        assert signed_word({"+1/+1"}).parse("+1/+1, then") is not None
        assert signed_word({"-1/-1"}).parse("-1/-1.")[0] == "-1/-1"

    def test_signed_word_in_a_scan(self):
        # "remove a +1/+1 counter" — verb anchor then the signed kind.
        p = seq3(keyword({"remove"}), keyword({"a"}), signed_word({"+1/+1", "-1/-1"}))
        assert p.parse("remove a +1/+1 counter")[0][2] == "+1/+1"
