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

The recovery is a registry of :class:`ClauseRule`s. A *simple* rule re-categorizes
an ``other`` effect whose English is unambiguous (e.g. "cast … from … graveyard"
→ a graveyard-cast). A *rich* rule (``build``) parses a real subject/amount out of
the clause (e.g. a created token's type and count). Two scope holes phase leaves
(it carries structured scope on only a sliver of abilities) are closed by a final
pass: the narrow Tinybones rule (combat-damage-to-a-player + that-player's-zone →
opponents) and the broader third-party-possessive guess.

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

# ── clause patterns for the recovery rules ────────────────────────────────────
# Cast-from-graveyard (Tinybones / graveyard-cast payoffs): "cast … from …
# graveyard". The structural parse loses the zone, so recover the reanimation
# shape from the clause.
_GRAVEYARD_CAST = re.compile(r"\bcast\b[^.]*\bfrom\b[^.]*\bgraveyard\b", re.IGNORECASE)

# Voting (CR 701.38) — phase leaves the vote itself Unimplemented even when it
# structures the consequence ("each player votes …, exile/sacrifice …"). The vote
# clause carries no operand worth binding, so a simple re-category to "vote"
# (scope each: every player votes) is the right structured node; signals derives
# voting_matters from it instead of a card-level oracle regex.
_VOTE = re.compile(
    r"will of the council|council's dilemma|each player votes?|\bvotes?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClauseRule:
    """One recovery: a clause pattern → a structured Effect.

    A *simple* rule sets ``category`` (and optionally overrides ``scope``) on the
    matched ``other`` effect. A *rich* rule supplies ``build(match, effect)`` to
    parse a real subject/amount out of the clause and return a new Effect.
    """

    name: str
    pattern: re.Pattern[str]
    category: str = ""
    scope: str | None = None
    build: Callable[[re.Match[str], Effect], Effect] | None = None

    def apply(self, m: re.Match[str], e: Effect) -> Effect:
        if self.build is not None:
            return self.build(m, e)
        return replace(e, category=self.category, scope=self.scope or e.scope)


# ── token-clause parser (mirrors phase's parser/oracle_effect/token.rs grammar) ─
# "create [count] [tapped] [supertypes] [P/T] [colors] <descriptor> token …".
# phase drops a token to Unimplemented when the clause has no count it recognizes,
# a creature with no P/T, or a bare-subtype descriptor not in its catalog; we
# recover those here into a real make_token Effect with a typed subject.
_CREATE_TOKEN = re.compile(r"\bcreates?\b.*?\btokens?\b", re.IGNORECASE)

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
_TOKEN_SCOPE = (
    (re.compile(r"each opponent\s+creates", re.IGNORECASE), "opp"),
    (re.compile(r"each player\s+creates", re.IGNORECASE), "each"),
    (
        re.compile(
            r"(?:target (?:opponent|player)|that player)\s+creates", re.IGNORECASE
        ),
        "opp",
    ),
)

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


def _build_token_effect(m: re.Match[str], e: Effect) -> Effect:
    """Parse a "create … token" clause into a structured make_token Effect."""
    clause = m.group(0)
    inner = re.search(r"\bcreates?\s+(.*?)\s+tokens?\b", clause, re.IGNORECASE)
    descriptor = inner.group(1) if inner else ""
    scope = "you"
    for pat, sc in _TOKEN_SCOPE:
        if pat.search(e.raw):
            scope = sc
            break
    count, subject = _parse_token_descriptor(descriptor)
    return replace(e, category="make_token", scope=scope, subject=subject, amount=count)


# The recovery registry. Order matters: the first matching rule wins, so put the
# most specific clauses first. Grow this as the fan-out owns more of the tail —
# each rule is a structured node, not a card-level boolean.
_RECOVERY_RULES: tuple[ClauseRule, ...] = (
    ClauseRule("graveyard_cast", _GRAVEYARD_CAST, category="reanimate"),
    ClauseRule("vote", _VOTE, category="vote", scope="each"),
    ClauseRule("create_token", _CREATE_TOKEN, build=_build_token_effect),
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
            m = rule.pattern.search(e.raw)
            if m:
                out = rule.apply(m, e)
                break

    # 2. scope recovery → opp. The narrow Tinybones rule overrides any prior
    # scope; the broad third-party guess only fills an unscoped ("any") effect.
    tinybones = _COMBAT_DMG_TO_PLAYER.search(out.raw) and _THAT_PLAYERS_ZONE.search(
        out.raw
    )
    if tinybones or (out.scope == "any" and _BROAD_THIRD_PARTY.search(out.raw)):
        out = replace(out, scope="opp")

    return out
