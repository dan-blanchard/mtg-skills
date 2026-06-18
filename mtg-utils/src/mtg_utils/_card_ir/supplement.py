"""Structured clause mini-parser — the gap-filler for phase's Unimplemented tail.

phase parses *what a card does* into a mechanics-shaped IR, but it only adds a
grammar rule for a mechanic once it implements the *engine* for it, so its parse
coverage is structurally bounded by its engine roadmap and trails the live card
pool. A **synergy** parser only ever needs to PARSE, never to play — so this
module is decoupled from that roadmap: it walks the English clauses phase
collapsed into ``category="other"`` (a ``GenericEffect`` / ``Unimplemented``) and
emits real :mod:`mtg_utils.card_ir` nodes (Effect category + scope + subject +
amount), so the synergy lanes derive from structure rather than a card-level
oracle regex.

The recovery is a registry of :class:`ClauseRule`s, each a function from an
``other`` effect to a structured Effect (or None). Following phase's own shape
(``imperative.rs`` dispatches on a cheap ``tag`` check, then hands off to a
structured parser), detection here is an O(n) keyword DISPATCH — these run on
every Unimplemented effect, so a search-the-whole-string scan would be too slow —
while the part with real structure, the created token's descriptor (type / subtype
/ count), is *parsed* by an anchored combinator grammar mirroring ``token.rs``.
Two scope holes phase leaves (it carries structured scope on only a sliver of
abilities) are closed by a final pass: the narrow Tinybones rule (combat-damage-
to-a-player + that-player's-zone → opponents) and the third-party-possessive guess.

The Tinybones regexes are inlined (not imported from ``_deck_forge.signals``) on
purpose: ``signals`` imports the IR, so a back-edge would be a cycle.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from mtg_utils._card_ir import _combinators as comb
from mtg_utils.card_ir import Card, Effect, Filter, Quantity

# ── scope recovery (phase structures scope on only a sliver of abilities) ──────
# Narrow Tinybones rule: combat-damage-to-a-player + that-player's-zone → opp.
# Kept narrow on purpose (a broad "its owner's hand → opp" misfires on
# self-blink/self-bounce). Ported verbatim from signals._tinybones_scope.
_COMBAT_DMG_TO_PLAYER = re.compile(r"deals combat damage to a player", re.IGNORECASE)
_THAT_PLAYERS_ZONE = re.compile(
    r"that player's (?:graveyard|hand|library)", re.IGNORECASE
)
# Broader third-party possessive (an opponents guess), deliberately excluding
# "its owner's" so it never flips self-blink/self-bounce.
_BROAD_THIRD_PARTY = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)

# ── clause detectors. Detection is a cheap keyword DISPATCH (what phase's
# imperative.rs does: a tag check decides which parser to run); only the token
# descriptor — the part with real structure (type/subtype/count) — is parsed, by
# the anchored combinator grammar further down. No search-the-string scan/regex:
# these run on every Unimplemented effect, so they must be O(n) substring tests. ─

# find_word is a single word-boundary-safe pass (vs a substring "vote" that would
# fire on "devoted"); shared module-level so it's built once, not per call.
_VOTE_WORD = comb.find_word({"vote", "votes"})
_DOUBLE_NOUN = comb.find_word({"token", "tokens", "counter", "counters"})


def _recover_graveyard_cast(e: Effect) -> Effect | None:
    """Cast-from-graveyard (Tinybones / graveyard-cast payoffs): "cast … from …
    graveyard" in order → a reanimation shape (the structural parse lost the zone)."""
    low = e.raw.lower()
    c = low.find("cast")
    if c < 0:
        return None
    f = low.find("from", c)
    if f < 0 or low.find("graveyard", f) < 0:
        return None
    return replace(e, category="reanimate")


def _recover_vote(e: Effect) -> Effect | None:
    """Voting (CR 701.38): phase leaves the vote itself Unimplemented even when it
    structures the consequence, so re-category the clause to a ``vote`` node (scope
    each — every player votes); signals derives voting_matters from it."""
    low = e.raw.lower()
    if "will of the council" in low or "council's dilemma" in low:
        return replace(e, category="vote", scope="each")
    if _VOTE_WORD.parse(e.raw) is not None:
        return replace(e, category="vote", scope="each")
    return None


# The doubling frame requires the MULTIPLIER, not a bare "that many" (which also
# appears on token-type *replacers* — Divine Visitation's "instead that many Angel
# tokens" — that keep the count). "times that many" generalizes over N (three/four/
# ten times…); "twice that many" is the 2x word; "that many plus" the adders;
# "double the number" the Doubling-Season phrasing phase sometimes leaves unparsed.
_DOUBLING_FRAMES = (
    "twice that many",
    "times that many",
    "that many plus",
    "double the number",
)


def _recover_doubling(e: Effect) -> Effect | None:
    """Doubling/tripling replacements phase leaves Unimplemented (Ojer Taq's token
    tripling). The multiplier frame + the multiplied NOUN pick the lane — a token
    doubler and a counter doubler are different archetypes, never one "doubling".
    The noun is the multiplier's OBJECT (just after the frame: "double the number
    of counters") — searched after the frame first so an incidental noun elsewhere
    (a "Sacrifice a token" cost) can't steal it; only "counters would be put …
    twice that many" puts the noun before, so fall back to the preceding text."""
    low = e.raw.lower()
    end = next(
        (low.find(f) + len(f) for f in _DOUBLING_FRAMES if f in low),
        -1,
    )
    if end < 0:
        return None
    noun = _DOUBLE_NOUN.parse(e.raw[end:]) or _DOUBLE_NOUN.parse(e.raw[:end])
    if noun is None:
        return None
    cat = "token_doubling" if noun[0].startswith("token") else "counter_doubling"
    return replace(e, category=cat, scope="you")


@dataclass(frozen=True)
class ClauseRule:
    """One recovery: a function from an ``other`` effect to a structured Effect (or
    None if the rule doesn't apply). Detection is combinator-PARSED, not
    regex-matched, so a rule reads like phase's nom grammar."""

    name: str
    recover: Callable[[Effect], Effect | None]


# ── token-clause parser (mirrors phase's parser/oracle_effect/token.rs grammar) ─
# "create [count] [tapped] [supertypes] [P/T] [colors] <descriptor> token …".
# phase drops a token to Unimplemented when the clause has no count it recognizes,
# a creature with no P/T, or a bare-subtype descriptor not in its catalog; we
# recover those here into a real make_token Effect with a typed subject.

# The 4 card-type words phase's token grammar recognizes; everything else in the
# descriptor is a subtype (token.rs parse_token_identity's allowlist).
_TOKEN_CARD_TYPES = {"artifact", "creature", "enchantment", "land"}
# Predefined artifact subtypes: a bare "Treasure"/"Food"/… token is an Artifact
# with that subtype (token.rs known_named_token_identity).
_PREDEF_ARTIFACT_SUB = {
    "treasure",
    "food",
    "clue",
    "blood",
    "map",
    "powerstone",
    "junk",
    "shard",
    "gold",
    "lander",
    "mutagen",
    "incubator",
}
_TOKEN_COUNT_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
# The modifier words consumed (in any order) between the count and the
# type/subtype head: enters-flags, P/T (one whole word), colors, supertypes.
_TOKEN_FLAGS = {"tapped", "untapped", "attacking"}
_TOKEN_COLORS = {
    "white",
    "blue",
    "black",
    "red",
    "green",
    "colorless",
    "monocolored",
    "multicolored",
}
_TOKEN_SUPERTYPES = {"legendary", "snow", "basic"}
_PT_WORD = re.compile(r"[\dx*]+/[\dx*]+", re.IGNORECASE)  # a whole word, e.g. 1/1
# Words that end the type/subtype run (an abilities/naming/attach clause follows).
_TOKEN_TAIL = {"with", "named", "that", "attached", "for", "in", "and"}


# Whose token is it (default: the controller's). An each-opponent / target-player
# giveaway is scope opp/each — a punisher, not your token engine.
def _token_scope(low: str) -> str:
    if "each opponent creates" in low:
        return "opp"
    if "each player creates" in low:
        return "each"
    if (
        "target opponent creates" in low
        or "target player creates" in low
        or "that player creates" in low
    ):
        return "opp"
    return "you"


# ── the token grammar, as combinators (mirrors token.rs's field order) ──────────
# count token (kept homogeneous Parser[str] — the Quantity conversion happens once
# in _count_value): an article/number word, a digit, X (dynamic), "that many"
# (dynamic), or "up to N". Captured as a raw string so the dynamic and numeric
# forms compose in one ``alt`` without a heterogeneous Parser[Quantity | None].
_single_count = comb.keyword(_TOKEN_COUNT_WORDS) | comb.satisfy(str.isdigit)
_count_token = comb.alt(
    comb.tag("that many"),
    comb.preceded(comb.tag("up to "), _single_count),
    _single_count,
    comb.keyword({"x"}),
)
# modifiers between the count and the head: P/T, colors, supertypes, enters-flags,
# and the "and" colour connector — consumed and discarded.
_modifier_p = comb.alt(
    comb.regex_word(_PT_WORD),
    comb.keyword(_TOKEN_COLORS),
    comb.keyword(_TOKEN_SUPERTYPES),
    comb.keyword(_TOKEN_FLAGS),
    comb.keyword({"and"}),
)
# the type+subtype head: words until a tail word (returns raw words to split).
_head_word = comb.satisfy(lambda w: bool(w) and w not in _TOKEN_TAIL)
_token_grammar = comb.seq3(
    comb.opt(_count_token), comb.many(_modifier_p), comb.many(_head_word)
)


def _count_value(token: str) -> Quantity | None:
    """A captured count token → a bound Quantity, or None for a dynamic count
    ("x" / "that many", which were consumed only so the head isn't misread)."""
    w = comb.norm_word(token)
    if w in _TOKEN_COUNT_WORDS:
        return Quantity(op="fixed", factor=_TOKEN_COUNT_WORDS[w])
    if w.isdigit():
        return Quantity(op="fixed", factor=int(w))
    return None


def _split_head(words: list[str]) -> Filter | None:
    """Split the head words into (card_types, subtypes) by phase's 4-word allowlist;
    a predefined artifact subtype (Treasure/Food/…) also supplies the Artifact type."""
    card_types: list[str] = []
    subtypes: list[str] = []
    for raw in words:
        w = comb.norm_word(raw)
        if w in _TOKEN_CARD_TYPES:
            card_types.append(w.capitalize())
        elif w in _PREDEF_ARTIFACT_SUB:
            if "Artifact" not in card_types:
                card_types.append("Artifact")
            subtypes.append(w.capitalize())
        else:
            subtypes.append(w.capitalize())
    if not (card_types or subtypes):
        return None
    return Filter(card_types=tuple(card_types), subtypes=tuple(subtypes))


def _parse_token_descriptor(descriptor: str) -> tuple[Quantity | None, Filter | None]:
    """Run the token grammar over a descriptor → (count, typed subject)."""
    parsed = _token_grammar.parse(descriptor)
    if parsed is None:
        return None, None
    (count_token, _mods, heads), _rest = parsed
    count = _count_value(count_token) if count_token else None
    return count, _split_head(heads)


# Locate a "create … token" clause: scan to "create"/"creates", take the descriptor
# up to " token" (nom's take_until). A bare "created"/"creates" without a following
# " token" yields no descriptor, so the rule doesn't fire. ``_CREATE_DESC`` is the
# anchored grammar (built once): "create[s] " then the descriptor up to " token".
_CREATE_DESC = comb.preceded(
    comb.tag("creates ") | comb.tag("create "), comb.take_until(" token")
)


def _recover_create_token(e: Effect) -> Effect | None:
    """A "create … token" clause → a structured make_token Effect (typed subject +
    count + scope), for the tokens phase leaves Unimplemented. Cheap dispatch first
    (a `.find` for "create" + " token"), then the anchored grammar parses the
    descriptor — phase's imperative.rs dispatches the same way."""
    low = e.raw.lower()
    start = low.find("create")
    if start < 0 or " token" not in low[start:]:
        return None
    parsed = _CREATE_DESC.parse(e.raw[start:])
    if parsed is None:
        return None
    count, subject = _parse_token_descriptor(parsed[0])
    return replace(
        e,
        category="make_token",
        scope=_token_scope(low),
        subject=subject,
        amount=count,
    )


# The recovery registry. Order matters: the first matching rule wins, so put the
# most specific clauses first. Doubling is tried before create_token (a "twice that
# many … tokens" clause is a doubler, not a plain token maker). Grow this as the
# fan-out owns more of the tail — each rule is a structured node, not a boolean.
_RECOVERY_RULES: tuple[ClauseRule, ...] = (
    ClauseRule("graveyard_cast", _recover_graveyard_cast),
    ClauseRule("vote", _recover_vote),
    ClauseRule("doubling", _recover_doubling),
    ClauseRule("create_token", _recover_create_token),
)


def supplement_card(card: Card) -> Card:
    """Return *card* with each effect's category/scope recovered from its raw."""
    faces = tuple(
        replace(
            face,
            abilities=tuple(
                replace(ab, effects=tuple(_supplement_effect(e) for e in ab.effects))
                for ab in face.abilities
            ),
        )
        for face in card.faces
    )
    return replace(card, faces=faces)


def _supplement_effect(e: Effect) -> Effect:
    out = e
    # 1. recover a buried effect from its clause (the first matching rule wins).
    if e.category == "other":
        for rule in _RECOVERY_RULES:
            recovered = rule.recover(e)
            if recovered is not None:
                out = recovered
                break

    # 2. scope recovery → opp. The narrow Tinybones rule overrides any prior
    # scope; the broad third-party guess only fills an unscoped ("any") effect.
    tinybones = _COMBAT_DMG_TO_PLAYER.search(out.raw) and _THAT_PLAYERS_ZONE.search(
        out.raw
    )
    if tinybones or (out.scope == "any" and _BROAD_THIRD_PARTY.search(out.raw)):
        out = replace(out, scope="opp")

    return out
