"""A tiny parser-combinator core for the oracle-text mini-parser.

Mirrors the `nom` API phase's ``parser/oracle_effect/token.rs`` is built on
(``tag`` / ``alt`` / ``opt`` / ``take_until`` / ``value`` / ``map`` plus
sequencing), so a clause grammar reads the same on both sides and a rule can be
ported between phase (Rust/nom) and the supplement (Python) near-mechanically.
Zero dependencies — the combinators are ~plain closures over the remaining input.

A :class:`Parser` ``run`` consumes a prefix of the input string and returns
``(value, rest)`` on success or ``None`` on failure — nom's
``IResult<&str, T>`` in miniature. Primitives split into char-level (``tag``,
``take_until``, ``ws``) and word-level (``word``, ``keyword``, ``satisfy``)
because oracle clauses are word-oriented ("create a 1/1 white Soldier …").
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")
U = TypeVar("U")

# Success: (value, remaining-input). Failure: None.
Result = "tuple[T, str] | None"


@dataclass(frozen=True)
class Parser[T]:
    """A parser: ``run(input) -> (value, rest) | None`` (nom's ``IResult``)."""

    run: Callable[[str], tuple[T, str] | None]

    def parse(self, s: str) -> tuple[T, str] | None:
        return self.run(s)

    def map(self, f: Callable[[T], U]) -> Parser[U]:
        def go(s: str) -> tuple[U, str] | None:
            r = self.run(s)
            return None if r is None else (f(r[0]), r[1])

        return Parser(go)

    def __or__(self, other: Parser[T]) -> Parser[T]:
        """``p | q`` — first of ``p``, ``q`` to succeed (nom ``alt``)."""
        return alt(self, other)


# ── char-level primitives ─────────────────────────────────────────────────────


def tag(literal: str, *, ci: bool = True) -> Parser[str]:
    """Match a literal prefix (case-insensitive by default; nom ``tag``)."""
    n = len(literal)
    needle = literal.lower() if ci else literal

    def go(s: str) -> tuple[str, str] | None:
        head = s[:n]
        if (head.lower() if ci else head) == needle:
            return (head, s[n:])
        return None

    return Parser(go)


def take_until(literal: str, *, ci: bool = True) -> Parser[str]:
    """Consume up to (not including) ``literal``; fail if absent (``take_until``)."""

    def go(s: str) -> tuple[str, str] | None:
        idx = s.lower().find(literal.lower()) if ci else s.find(literal)
        return None if idx < 0 else (s[:idx], s[idx:])

    return Parser(go)


def ws() -> Parser[None]:
    """Consume leading whitespace (always succeeds)."""

    def go(s: str) -> tuple[None, str]:
        return (None, s.lstrip())

    return Parser(go)


# ── word-level primitives (oracle clauses are word-oriented) ───────────────────

_WORD = re.compile(r"\S+")


def norm_word(w: str) -> str:
    """A word's identity for matching: lowercase, punctuation stripped."""
    return re.sub(r"[^a-z0-9*/]", "", w.lower())


def word() -> Parser[str]:
    """The next whitespace-delimited word (leading whitespace skipped)."""

    def go(s: str) -> tuple[str, str] | None:
        s2 = s.lstrip()
        m = _WORD.match(s2)
        if not m:
            return None
        return (m.group(0), s2[m.end() :])

    return Parser(go)


def satisfy(pred: Callable[[str], bool]) -> Parser[str]:
    """The next word if its normalized form satisfies ``pred`` (else fail)."""

    def go(s: str) -> tuple[str, str] | None:
        r = word().run(s)
        if r is None or not pred(norm_word(r[0])):
            return None
        return r

    return Parser(go)


def keyword(words: Iterable[str]) -> Parser[str]:
    """The next word if its normalized form is in ``words`` (returns the normalized
    form so callers don't re-normalize)."""
    bag = frozenset(words)
    return satisfy(lambda w: w in bag).map(norm_word)


def regex_word(pattern: re.Pattern[str]) -> Parser[str]:
    """The next word if its normalized form fully matches ``pattern`` (e.g. a P/T)."""
    return satisfy(lambda w: bool(pattern.fullmatch(w)))


_ALNUM_RUN = re.compile(r"[a-z0-9]+")


def keyword_bounded(words: Iterable[str]) -> Parser[str]:
    """The next word if ANY of its ``\\b``-delimited alphanumeric segments is in
    ``words`` — the boundary-aware analogue of ``keyword``. ``norm_word`` glues a word
    across an em-dash/hyphen ("Morph—Discard" → "morphdiscard"), so a plain
    ``keyword({"morph"})`` misses an ability word fused to its cost; this splits on the
    punctuation ``norm_word`` strips, matching a regex ``\\bmorph\\b`` (a segment
    is naturally word-boundary-delimited, so "geomorph" — no internal boundary — is not
    a hit). Returns the matched segment."""
    bag = frozenset(words)

    def go(s: str) -> tuple[str, str] | None:
        r = word().run(s)
        if r is None:
            return None
        for seg in _ALNUM_RUN.findall(r[0].lower()):
            if seg in bag:
                return (seg, r[1])
        return None

    return Parser(go)


# ── combinators (nom-shaped) ───────────────────────────────────────────────────


def alt(*parsers: Parser[Any]) -> Parser[Any]:
    """First parser to succeed (nom ``alt``). Heterogeneous: arms may yield different
    value types (a ``phrase`` list, a ``seq`` list, a ``keyword`` str), so the element
    type is ``Any`` — the value of an ``alt`` used as a detector (run-is-not-None) or
    mapped to a constant is rarely consumed positionally."""

    def go(s: str) -> tuple[Any, str] | None:
        for p in parsers:
            r = p.run(s)
            if r is not None:
                return r
        return None

    return Parser(go)


def opt[T](p: Parser[T]) -> Parser[T | None]:
    """``p`` or nothing — never fails (nom ``opt``)."""

    def go(s: str) -> tuple[T | None, str]:
        r = p.run(s)
        return r if r is not None else (None, s)

    return Parser(go)


def many[T](p: Parser[T]) -> Parser[list[T]]:
    """Zero or more ``p`` (nom ``many0``). A no-progress result stops the loop."""

    def go(s: str) -> tuple[list[T], str]:
        out: list[T] = []
        rest = s
        while True:
            r = p.run(rest)
            if r is None or r[1] == rest:
                return (out, rest)
            out.append(r[0])
            rest = r[1]

    return Parser(go)


def value[U, T](constant: U, p: Parser[T]) -> Parser[U]:
    """Run ``p``, discard its output, yield ``constant`` (nom ``value``)."""
    return p.map(lambda _v: constant)


def preceded[P, T](pre: Parser[P], p: Parser[T]) -> Parser[T]:
    """Run ``pre``, discard its output, then ``p`` (nom ``preceded``)."""

    def go(s: str) -> tuple[T, str] | None:
        r = pre.run(s)
        return None if r is None else p.run(r[1])

    return Parser(go)


def succeed[T](x: T) -> Parser[T]:
    """Always succeed with ``x``, consuming nothing (nom ``success``)."""
    return Parser(lambda s: (x, s))


def find_word(words: Iterable[str]) -> Parser[str]:
    """Scan word-by-word for the first whole word whose normalized form is in
    ``words`` (word-boundary-safe, unlike a substring test that would match
    "vote" inside "devoted"). Returns the normalized word + the rest. A single
    O(n) pass — detection that runs on every clause must stay linear."""
    bag = frozenset(words)

    def go(s: str) -> tuple[str, str] | None:
        for m in _WORD.finditer(s):
            w = norm_word(m.group(0))
            if w in bag:
                return (w, s[m.end() :])
        return None

    return Parser(go)


A = TypeVar("A")
B = TypeVar("B")
C_ = TypeVar("C_")


def seq2[A, B](pa: Parser[A], pb: Parser[B]) -> Parser[tuple[A, B]]:
    """Run two parsers in sequence, collecting their outputs (nom tuple)."""

    def go(s: str) -> tuple[tuple[A, B], str] | None:
        ra = pa.run(s)
        if ra is None:
            return None
        rb = pb.run(ra[1])
        if rb is None:
            return None
        return ((ra[0], rb[0]), rb[1])

    return Parser(go)


def seq3[A, B, C_](
    pa: Parser[A], pb: Parser[B], pc: Parser[C_]
) -> Parser[tuple[A, B, C_]]:
    """Run three parsers in sequence, collecting their outputs (nom tuple)."""

    def go(s: str) -> tuple[tuple[A, B, C_], str] | None:
        ra = pa.run(s)
        if ra is None:
            return None
        rb = pb.run(ra[1])
        if rb is None:
            return None
        rc = pc.run(rb[1])
        if rc is None:
            return None
        return ((ra[0], rb[0], rc[0]), rc[1])

    return Parser(go)


def seq(*parsers: Parser[Any]) -> Parser[list[Any]]:
    """Run parsers in sequence, collecting their values into a list (variadic ``seq2``/
    ``seq3``). Fails if any parser fails. The arbitrary-arity glue for a multi-slot
    clause whose slots are heterogeneous parsers (a ``keyword`` then a ``bounded_scan``
    then a ``phrase`` …) — where ``phrase`` (all-keyword slots) is too rigid."""

    def go(s: str) -> tuple[list[Any], str] | None:
        out: list[Any] = []
        rest = s
        for p in parsers:
            r = p.run(rest)
            if r is None:
                return None
            out.append(r[0])
            rest = r[1]
        return (out, rest)

    return Parser(go)


def phrase(*bags: Iterable[str]) -> Parser[list[str]]:
    """Match consecutive words, each whose normalized form is in the corresponding
    ``bag`` — a fixed-shape word sequence with per-slot alternation (nom's
    tuple-of-tags, but word-oriented). ``phrase({"creature", "creatures"}, {"you"},
    {"control", "own"})`` matches "creatures you control" or "creature you own".
    Returns the matched normalized words. Fails if any slot's word is absent."""
    slots = [keyword(b) for b in bags]

    def go(s: str) -> tuple[list[str], str] | None:
        out: list[str] = []
        rest = s
        for p in slots:
            r = p.run(rest)
            if r is None:
                return None
            out.append(r[0])
            rest = r[1]
        return (out, rest)

    return Parser(go)


def scan[T](p: Parser[T]) -> Parser[T]:
    """Try ``p`` at each successive word boundary; the first success wins — the
    word-anchored analogue of a regex ``.search`` (vs. the combinators above, which
    anchor at the input's head). Linear in the word count times ``p``'s own cost, so
    detection that runs per clause stays linear. Returns ``p``'s value + the input
    after ``p``'s match (NOT after the scanned prefix), mirroring how ``find_word``
    hands back the tail past its hit."""

    def go(s: str) -> tuple[T, str] | None:
        rest = s
        while True:
            r = p.run(rest)
            if r is not None:
                return r
            w = word().run(rest)
            if w is None:
                return None
            rest = w[1]

    return Parser(go)


# Default clause delimiters: a period ends a sentence, a semicolon ends a sub-clause,
# and a straight/typographic quote ends a granted-ability body. A regex ``[^.]*?`` gap
# stops only at a period; ``bounded_scan`` adds ``;`` and the quotes so a multi-slot
# phrase never bridges two clauses — the word-anchored analogue of phase's per-clause
# ``take_until`` (oracle_effect splits on the same delimiters before parsing).
_CLAUSE_DELIMS = '.;"“”'


def _carries_delim(raw_word: str, delims: str) -> bool:
    """A raw (un-normalized) word carries a clause delimiter — so the gap that
    skipped it has crossed into the next clause and must stop. Checks the raw token
    because ``norm_word`` strips punctuation away."""
    return any(d in raw_word for d in delims)


def bounded_scan[T](p: Parser[T], *, delims: str = _CLAUSE_DELIMS) -> Parser[T]:
    """``scan`` bounded to the current clause: try ``p`` at each word boundary, but
    FAIL once a word carrying a clause delimiter (``delims``) has been crossed — the
    word-anchored analogue of a regex ``[^.]*?`` bounded gap inside one sentence.
    Lets ``seq2(anchor, bounded_scan(target))`` parse "anchor … target" structurally
    without bridging a period/semicolon/quote. The delimiter check is on the SKIPPED
    gap words, never on where ``p`` matches, so a target sitting on the clause-final
    word still parses. Linear, like ``scan``; mirrors phase's per-clause take_until."""

    def go(s: str) -> tuple[T, str] | None:
        rest = s
        while True:
            r = p.run(rest)
            if r is not None:
                return r
            w = word().run(rest)
            if w is None:
                return None
            if _carries_delim(w[0], delims):
                return None
            rest = w[1]

    return Parser(go)


def take_until_clause(*, delims: str = _CLAUSE_DELIMS) -> Parser[str]:
    """Consume characters up to (not including) the first clause-delimiter character,
    returning the skipped text. Always succeeds (an empty gap is valid). The capturing
    companion to ``bounded_scan`` — use when the gap's *content* is wanted (e.g. a
    recovered ``raw`` span), not merely skipped. Char-granular so it stops mid-word at
    the delimiter exactly like a regex ``[^.]*``; mirrors phase ``take_until`` but with
    a clause-delimiter set instead of a single literal."""
    delim_set = frozenset(delims)

    def go(s: str) -> tuple[str, str]:
        for i, ch in enumerate(s):
            if ch in delim_set:
                return (s[:i], s[i:])
        return (s, "")

    return Parser(go)


def _sign_form(w: str) -> str:
    """A counter token's sign-preserving identity: keep ``+ - 0-9 /`` only, so
    ``+1/+1`` and ``-1/-1`` stay DISTINCT (``norm_word`` folds both to ``1/1``)."""
    return re.sub(r"[^+\-0-9/]", "", w.lower())


def signed_word(words: Iterable[str]) -> Parser[str]:
    """The next word if its SIGN-PRESERVING form (``_sign_form``) is in ``words`` —
    the sign-sensitive analogue of ``keyword``. ``keyword({"+1/+1"})`` can never work
    (``norm_word`` strips the sign), so a parser that must read the counter KIND
    (``+1/+1`` vs ``-1/-1``) reaches for this. Returns the sign-preserving form, so a
    caller maps ``+1/+1 → p1p1`` / ``-1/-1 → m1m1`` directly off the value."""
    bag = frozenset(words)

    def go(s: str) -> tuple[str, str] | None:
        r = word().run(s)
        if r is None:
            return None
        form = _sign_form(r[0])
        if form not in bag:
            return None
        return (form, r[1])

    return Parser(go)
