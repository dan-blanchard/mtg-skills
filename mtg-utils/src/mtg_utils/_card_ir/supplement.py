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
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

from mtg_utils._card_ir import _combinators as comb
from mtg_utils._card_ir.clause_grammar import (
    _EFFECT_CLAUSE,
    _FAILED_PREFIX,
    parse_clause,
    scan_clause,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger

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

# ── ADR-0027 topdeck library-owner scope (SIDECAR v28) ────────────────────────
# A `topdeck_select` clause (the "look at / reveal the top N …" + scry/surveil
# selection family) is split by WHOSE LIBRARY (or hand) is examined, so a
# downstream topdeck_selection lane keeps the controller's OWN-library card
# selection (scry/surveil/look-at-your-top) apart from an opponent-library /
# opponent-hand PEEK and the Morph face-down REVEAL — which are not the
# controller's own top-of-deck curation. Mirrors the dig library-owner scope split
# (project._dig_player_scope) one zone up: the supplement-recovered topdeck_select
# (the "look"/"looks" combinator + the _LIBRARY_POS arm) carries no structured
# `player`, so the owner is read from the RAW. CR 701.18 (scry) / 701.42 (surveil)
# / 116 (top of library). The structured scry/surveil DOERS (project._EFFECT_CATEGORY
# scry/surveil → topdeck_select) already carry scope 'you' and never reach the
# supplement, so they keep their own-selection scope.
# YOUR library: "the top N cards of your library", "from the top of your library",
# "top of your library" — the controller's own deck.
_TOPDECK_YOUR_LIBRARY = re.compile(
    r"\bof your library\b|\bfrom the top of your library\b|\btop of your library\b",
    re.IGNORECASE,
)
# An OPPONENT-library / target-player-library PEEK or an opponent-HAND peek — a
# look at a DIFFERENT player's hidden zone, not the controller's own selection.
# "target player's library" is INCLUDED here (the _BROAD_THIRD_PARTY guess omits
# it — it names only opponent/their/each-opponent), so an Orcish-Spy / Mishra's-
# Bauble "look at the top N of target player's library" routes to 'opp' too.
_TOPDECK_OTHER_ZONE = re.compile(
    r"(?:target opponent'?s?|that player'?s?|defending player'?s?"
    r"|target player'?s?|an opponent'?s?|each opponent'?s?|their) (?:library|hand)"
    r"|(?:look at|reveal)[^.]*opponent'?s? hand",
    re.IGNORECASE,
)
# The Morph / face-down REVEAL ("look at target face-down creature" — Aven
# Soulgazer, Smoke Teller; "look at face-down creatures you don't control" — Keeper
# of the Lens) is a hidden-information peek at a BATTLEFIELD object, NOT a
# top-of-library selection — gated to NO "library" so a your-library dig that
# exiles a card face down (Clone Shell, Curator of Destinies, Hideaway) is NOT
# dropped. CR 702.37.
_TOPDECK_MORPH = re.compile(r"\bface[- ]down\b", re.IGNORECASE)
_TOPDECK_LIBRARY = re.compile(r"\blibrar", re.IGNORECASE)


# ── ADR-0027 exile_removal category+subject retention (SIDECAR v30, Cluster B) ──
# phase swallows a genuine single-target exile REMOVAL into a sibling RIDER clause
# (a restriction/tax static — Soul Partition; a lifegain rider — Swords to
# Plowshares, "Exile") or leaves the exile structured but DROPS the permanent-type
# subject (Unexplained Absence — an Unimplemented "for each player" wrapper). The
# exile-removal lane then can't read it. This recovery RE-TAGS the swallow effect to
# category="exile" + a permanent-type subject, and FILLS the dropped subject on a
# bare cat=="exile" effect, READING the discriminator off the raw (the structured
# subject is the thing that's missing). It mirrors the deleted exile_removal SWEEP
# regex's permanent-target core, so the recovered effect is exactly what that regex
# matched. CR 406.1 (exile is a holding area — one-way exile is removal), 115.1
# (single TARGET, vs the 115.10 mass board wipe which carries no "target").
#
# Verb "exile" OR "~": phase replaces the swallowed exile verb with its Unimplemented
# name marker "~" ("Exile" the card → "~ target nonwhite attacking creature"), so the
# literal verb is gone from that effect's raw — match both. The captured HEAD noun
# (creature/permanent/artifact/enchantment/planeswalker) becomes the card_types
# subject the structural arm gates on.
_EXILE_REMOVAL_RAW = re.compile(
    r"(exile|~) (?:up to (?:one|two|three|\w+|x) )?(?:other |another )?"
    r"target (?:[a-z]+ )*(creature|permanent|artifact|enchantment|planeswalker)",
    re.IGNORECASE,
)
# Exclusions read from raw, mirroring the structural arm's predicate/zone/sibling
# gates (which can't fire when the subject/zone is the thing phase dropped):
#  - RETURN → blink/flicker (CR 603.6e / 400.7 — the object returns as a NEW object,
#    not permanent removal — Eldrazi Displacer "exile … then return it");
#  - TIME COUNTER / SUSPEND → impulse/suspend temporary exile (CR 702.62), returns;
#  - from GRAVEYARD / HAND → GY-hate / hand-exile setup, not battlefield removal;
#  - "you own"/"you control" on the TARGET → self-exile / blink-of-own (value, not
#    removal — Cloudshift, Kaya's -2).
_EXILE_REMOVAL_RETURN = re.compile(
    r"\breturn (?:it|that card|those cards|them|the exiled|each)", re.IGNORECASE
)
_EXILE_REMOVAL_SUSPEND = re.compile(r"time counter|\bsuspend\b", re.IGNORECASE)
_EXILE_REMOVAL_FROM_ZONE = re.compile(
    r"from (?:a|your|their|its owner's|each|all)?\s*(?:graveyard|hand)", re.IGNORECASE
)
_EXILE_REMOVAL_SELF_TARGET = re.compile(
    r"target (?:[a-z]+ )*(?:creature|permanent|artifact|enchantment|planeswalker)"
    r" you (?:own|control)",
    re.IGNORECASE,
)
# The swallow categories phase mis-routed a target exile into (the literal "exile"
# verb survives in the static's description; the lifegain rider's effect carries the
# whole clause). A bare cat=="exile" with NO subject is the dropped-subject case.
_EXILE_SWALLOW_CATEGORIES = frozenset({"restriction", "gain_life"})
_EXILE_HEAD_TO_TYPE = {
    "creature": "Creature",
    "permanent": "Permanent",
    "artifact": "Artifact",
    "enchantment": "Enchantment",
    "planeswalker": "Planeswalker",
}


def _recover_exile_removal(out: Effect) -> Effect:
    """Retain cat="exile" + a permanent-type subject on a genuine single-target exile
    REMOVAL phase swallowed into a rider clause or left subjectless.

    Fires only when (a) the effect is a swallow category (restriction/gain_life) OR a
    bare cat=="exile" with no subject, AND (b) the raw matches the single-target
    permanent-exile core, AND (c) none of the blink/suspend/zone-shuffle/self-exile
    exclusions hit. Re-tags category to "exile" and sets the captured head-noun
    subject; leaves scope/zones/amount untouched (the structural arm reads the
    category + subject, and the recovered subject carries no controller predicate, so
    the existing Owned/you gates still hold for cards that already had a subject)."""
    cat = out.category
    bare_exile = cat == "exile" and out.subject is None
    if cat not in _EXILE_SWALLOW_CATEGORIES and not bare_exile:
        return out
    # The MASS half of a "exile target X and all <other> X" effect (counter_kind=="all",
    # the board-wipe sibling phase splits out — Declaration in Stone, Soul Nova) is
    # mass_removal's domain (CR 115.10), not the single-target lane; never fill its
    # dropped subject (it would flip mass_removal on, breaking pre-wire neutrality).
    if out.counter_kind == "all":
        return out
    raw = out.raw or ""
    m = _EXILE_REMOVAL_RAW.search(raw)
    if m is None:
        return out
    if (
        _EXILE_REMOVAL_RETURN.search(raw)
        or _EXILE_REMOVAL_SUSPEND.search(raw)
        or _EXILE_REMOVAL_FROM_ZONE.search(raw)
        or _EXILE_REMOVAL_SELF_TARGET.search(raw)
    ):
        return out
    # A gain_life effect whose exile verb survived as the LITERAL "Exile" means phase
    # ALSO emitted a separate, properly-subjected exile effect (the lifegain is a true
    # rider payoff — Swords to Plowshares "Exile target creature. Its controller gains
    # life …" — 23 such cards). Retagging it would be redundant for recall AND would
    # silence the migrated lifegain_matters reading of that rider. Only the GENUINE
    # lifegain-SWALLOW — where phase replaced the exile verb with its Unimplemented "~"
    # marker because the exile is the only carrier ("Exile" the card → "~ target
    # nonwhite attacking creature. You gain life …") — has no sibling exile, so the
    # gain_life recovery is gated to the "~" verb (lifegain_matters stays neutral).
    verb = m.group(1)
    if out.category == "gain_life" and verb != "~":
        return out
    subject = Filter(card_types=(_EXILE_HEAD_TO_TYPE[m.group(2).lower()],))
    return replace(out, category="exile", subject=subject)


# ── ADR-0027 exile_removal PROJECTION TAIL (SIDECAR v46, Cluster C13) ──────────
# Two phase MIS-PARSES each drop a genuine SINGLE-TARGET battlefield exile that the
# C13 structural arm would otherwise admit. The supplement is our parser: we add the
# structure phase missed (both upstreamable to phase-rs). Append-only / idempotent —
# a correctly-parsed exile is untouched; only the mis-parsed shapes are repaired.
#
# (1) BATTLEFIELD-OR-GRAVEYARD HYBRID phase mis-zoned graveyard-only. Savior of
#     Ollenbock — "exile up to one other target creature FROM THE BATTLEFIELD or
#     creature card from a graveyard" — is partial battlefield removal, but phase
#     emits zones=(from:graveyard, to:exile): the in:battlefield alternative is NOT
#     emitted, so C13's pure-GY exclusion (graveyard zone present AND no
#     in:battlefield) drops it. When the raw names a battlefield-exile alternative
#     ("creature from the battlefield or … card from a graveyard" / "creature you
#     don't control or creature card from a graveyard"), ADD in:battlefield so the
#     effect becomes the HYBRID board+GY shape the structural arm already admits
#     (matching Angel of Serenity / Aurelia's Vindicator, which phase parses with
#     zones=(in:battlefield, in:graveyard, to:exile)). CR 406.1 — one-way exile of
#     the on-board portion is removal; CR 406.2 — the battlefield half moves from the
#     battlefield to exile.
_EXILE_BATTLEFIELD_ALT = re.compile(
    r"creature (?:from the battlefield|you don't control)\b[^.]*\bor\b[^.]*"
    r"creature card from (?:a |an |their |each )?graveyard",
    re.IGNORECASE,
)


def _recover_hybrid_exile_zone(out: Effect) -> Effect:
    """ADD in:battlefield to a cat="exile" effect phase mis-zoned graveyard-only when
    the raw names a battlefield-exile alternative (Savior of Ollenbock).

    Idempotent: fires only when a graveyard zone is present, in:battlefield is ABSENT,
    and the raw matches the battlefield-OR-graveyard alternative — so a pure-GY exile
    (no battlefield clause) and an already-hybrid exile are both untouched. The
    structural exile_removal arm's pure-GY exclusion then no longer drops the effect
    (graveyard zone present AND in:battlefield present ⇒ admitted)."""
    if out.category != "exile":
        return out
    zones = out.zones
    if not any("graveyard" in z for z in zones):
        return out
    if any("in:battlefield" in z for z in zones):
        return out
    if not _EXILE_BATTLEFIELD_ALT.search(out.raw or ""):
        return out
    return replace(out, zones=(*zones, "in:battlefield"))


# (2) OPPONENT-EXILE half phase split into a bare subjectless exile. Kaya, Spirits'
#     Justice -2 — "Exile target creature you control. For each other player, exile
#     up to one target creature that player controls" — is split by phase into a
#     cat="blink"(subject=self, controller=you) self-exile half + a bare
#     cat="exile"(subject=None) opponent half. The SECOND sentence is unconditional
#     permanent exile of opponents' creatures = genuine removal. _recover_exile_removal
#     can't refill it: its single-target core matches the EARLIER "creature you
#     control" in the SAME raw and the self-target guard fires. Give the bare exile an
#     OPPONENT-controlled creature subject (read from the per-opponent "exile … target
#     creature that player controls" clause) so the structural arm admits the opponent
#     half. Scoped to the opponent clause so the self-target collision is sidestepped.
#     CR 406.1 (one-way exile = removal), CR 406.2 (to-exile moves from the
#     battlefield).
_EXILE_OPPONENT_CLAUSE = re.compile(
    r"(?:for each other player|each opponent)\b[^.]*\bexile\b[^.]*"
    r"creature (?:that player controls|you don't control)",
    re.IGNORECASE,
)


def _recover_opponent_exile_subject(out: Effect) -> Effect:
    """Fill an OPPONENT-controlled creature subject on a bare cat="exile"(subject=None)
    that phase split off from a self+opponent dual-exile (Kaya, Spirits' Justice -2),
    so the structural exile_removal arm admits the opponent-removal half.

    Idempotent: fires only on a subjectless, non-mass, non-graveyard/hand exile whose
    raw names the per-opponent "exile … creature that player controls" clause — so a
    bare exile that is the controller's own (blink) half, a GY-source exile, or a mass
    exile is untouched. The opponent-controlled subject clears the structural arm's
    permanent-type + not-you-controlled gates."""
    if out.category != "exile" or out.subject is not None:
        return out
    if out.counter_kind == "all":
        return out
    if any("graveyard" in z or "hand" in z for z in out.zones):
        return out
    if not _EXILE_OPPONENT_CLAUSE.search(out.raw or ""):
        return out
    return replace(out, subject=Filter(card_types=("Creature",), controller="opp"))


def _topdeck_select_owner_scope(out: Effect) -> Effect:
    """Re-scope (or re-categorize) a supplement-recovered ``topdeck_select`` Effect by
    WHOSE library/hand it examines (read from ``raw`` — the recovery carries no
    structured player).

    - A pure Morph REVEAL ("look at target face-down creature", no "library") is NOT
      top-of-library selection → re-categorized to ``reveal`` (a non-topdeck category
      the topdeck_selection doer/structural arm both drop). The face-down dig that
      EXILES from YOUR library (Clone Shell, Curator) keeps "library" in its raw, so
      it stays ``topdeck_select``.
    - An OPPONENT-library / target-player-library / opponent-hand PEEK (Orcish Spy,
      Mishra's Bauble, Cruel Fate, Anointed Peacekeeper) → scope 'opp' (route OUT of
      the controller's own-selection lane), UNLESS the clause ALSO names your library
      (a dual "look at the top of YOUR library, opponent separates" — Atris, Fortune's
      Favor — is still YOUR selection).
    - An OWN-library look/reveal ("the top N cards of your library") → scope 'you' (the
      controller's own card selection, joining the structured scry/surveil 'you').

    A clause that names neither zone (a "put X on top of their owners' libraries" tuck
    the _LIBRARY_POS arm also catches — Plow Under, Hallowed Burial) keeps its current
    scope; it is topdeck_STACK/removal, not selection, and the scope!='you' keeps it
    out of the migrated topdeck_selection structural arm. CR 116 / 401.4."""
    raw = out.raw or ""
    has_library = bool(_TOPDECK_LIBRARY.search(raw))
    if _TOPDECK_MORPH.search(raw) and not has_library:
        return replace(out, category="reveal")
    your = bool(_TOPDECK_YOUR_LIBRARY.search(raw))
    if _TOPDECK_OTHER_ZONE.search(raw) and not your:
        return replace(out, scope="opp")
    if your:
        return replace(out, scope="you")
    return out


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
    # "Double all damage …/the next … damage … would deal" → damage doubling.
    if ("double all damage" in low or "double the damage" in low) or (
        "double" in low and "damage" in low and "would deal" in low
    ):
        return replace(e, category="damage_doubling", scope="you")
    end = next(
        (low.find(f) + len(f) for f in _DOUBLING_FRAMES if f in low),
        -1,
    )
    if end < 0:
        return None
    noun = _DOUBLE_NOUN.parse(e.raw[end:]) or _DOUBLE_NOUN.parse(e.raw[:end])
    if noun is None:
        # a multiplier frame with no token/counter object — doubling another resource
        # (energy/mana/life: "you get twice that many {E}"). Generic `double`.
        return replace(e, category="double", scope="you")
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


def _recover_by_verb(e: Effect) -> Effect | None:
    """Re-categorize via the shared clause grammar (now in clause_grammar)."""
    cat = parse_clause(e.raw)
    return replace(e, category=cat) if cat is not None else None


def _recover_verb_scan(e: Effect) -> Effect | None:
    cat = scan_clause(e.raw)
    return replace(e, category=cat) if cat is not None else None


# Static-line discriminants: an anthem ("… gets +N/+N"), a restriction ("… can't …"),
# or an ability/keyword grant ("creatures … have/gain …"). Unlike the imperative verbs
# (parsed left-to-right by the combinator grammar above), a static names the AFFECTED
# set BEFORE its verb, so detection is a discriminant PATTERN, not a cursor-anchored
# parse — and the anthem's "+N/+N" token is punctuated, which the word-level
# combinators normalize away (norm_word strips "+"), so a char-level regex is the right
# tool here (as for the Tinybones scope rules above).
# An anthem/pump "gets +N/+N" — N may be a digit OR a variable (+X/+Y, dynamic pumps
# like "gets +X/+X where X is …") OR * (gets */*). The token is punctuated, which the
# word-combinators normalize away, so a char-level regex is right here.
# N may be a digit / variable (X,Y,Z) / * / ~ (phase's P/T placeholder, "gets ~/~").
# Allow words between "gets" and the P/T token ("gets an additional +2/-2").
_GETS_PT = re.compile(
    r"\bgets?\b[^./]{0,18}[+-~][\dxyz*~]*/[+-~][\dxyz*~]*", re.IGNORECASE
)
# A type/characteristic STATE conditional ("isn't a creature unless …", "isn't
# legendary if …") — a static layer effect, its own non-sliced category.
_STATE = re.compile(
    r"\bisn'?t (?:a |an |legendary)|\bis the chosen (?:color|type)\b"
    r"|\b(?:is|are) no longer\b",  # "is no longer snow", "are no longer suspected"
    re.IGNORECASE,
)
_CANT = re.compile(r"\bcan'?t\b", re.IGNORECASE)
# ADR-0027 scope='each' symmetric pass — an OPPONENT-tax restriction phase folds into
# a generic synthesized "other" clause (its structured CantCastFrom / cantgainlife
# carrier never reached _restriction_scope, so the clause survives only in raw at
# scope 'any'): "your opponents can't …" (Drannith Magistrate, Stranglehold, Silence),
# "each opponent can't …" (Lavinia, Azorius Renegade). Promote the recovered
# restriction's scope to 'opp' so the stax_taxes lane reads it. DORMANT until that
# lane is wired (no migrated key reads restriction scope). CR 115.4 / 720.
_OPP_RESTRICTION = re.compile(
    r"\b(?:your opponents|each opponent|opponents) can'?t\b", re.IGNORECASE
)
# A combat cap ("No more than N creatures can attack/block …") is a RESTRICTION, not
# a permission — checked before the can-attack/block grant below so it wins.
_COMBAT_CAP = re.compile(r"\bno more than\b", re.IGNORECASE)
# A combat PERMISSION grant ("can attack as though it had haste", "can block an
# additional creature") — an ability grant, distinct from the "can't" restriction.
_CAN_COMBAT = re.compile(r"\bcan (?:attack|block)\b", re.IGNORECASE)
# A tuck ("the owner of … shuffles it into their library") — the shuffle verb is
# preceded by the owner subject, so a discriminant scan recovers it as a shuffle.
_TUCK = re.compile(r"\bshuffles?\b.{0,60}\blibrary\b", re.IGNORECASE)
# A timing grant — "cast spells … as though they had flash" -> grant_keyword (flash).
_FLASH_GRANT = re.compile(r"as though (?:it|they) (?:had|have) flash", re.IGNORECASE)
# More niche-mechanic discriminants (subject/structure precedes the keyword, so a
# scan, not a cursor parse). All map to NON-sliced categories — pure parse completion.
_DAMAGE_REPLACE = re.compile(  # damage replacement/prevention: "all damage … as
    # though …", "the next N damage that would be dealt …", "damage that would reduce …"
    r"\bdamage\b[^.]*\bas though\b|\bdamage that would\b",
    re.IGNORECASE,
)
# An alternative cost ("you may pay {0} rather than pay the mana cost", "rather than
# its mana cost") — a cost-replacement permission. Non-sliced category.
_ALT_COST = re.compile(
    r"\brather than\b[^.]*\bmana cost\b|\bwithout paying (?:its|their) mana costs?\b"
    r"|\brather than pay\b",  # "Rather than pay {2} for each previous time …"
    re.IGNORECASE,
)
# An ETB/continuous clone ("enters as a copy of …", "is a copy of the chosen creature")
# distinct from the imperative "create a copy" — a clone synergy. Static discriminant.
_CLONE_STATIC = re.compile(
    r"\b(?:is|are|enters?|enter) (?:as )?(?:a )?copy of\b|\bas a copy of\b",
    re.IGNORECASE,
)
# Copied-type words, in priority order (Permanent last so a specific type wins).
_COPY_TYPE_WORDS: tuple[tuple[str, str], ...] = (
    ("creature", "Creature"),
    ("artifact", "Artifact"),
    ("enchantment", "Enchantment"),
    ("planeswalker", "Planeswalker"),
    ("land", "Land"),
    ("permanent", "Permanent"),
)


def _copied_type_from_text(raw: str) -> Filter | None:
    """The copied permanent type from a clone clause — the word right after "copy of"
    ("becomes a copy of target CREATURE" → Creature; "of any creature or planeswalker"
    → both). None when "copy of" is followed by a typeless referent ("copy of that
    card") — those fall back to the ability's sibling/trigger target."""
    low = raw.lower()
    i = low.find("copy of")
    if i < 0:
        return None
    seg = low[i : i + 60]
    types = tuple(title for word, title in _COPY_TYPE_WORDS if word in seg)
    return Filter(card_types=types) if types else None


# Forced combat: "… attacks … if able", "all creatures … attack if able". And a forced
# block: "all … able to block ~ do so" (a lure).
_FORCE_ATTACK = re.compile(r"\battacks?\b[^.]*\bif able\b", re.IGNORECASE)
_FORCE_BLOCK = re.compile(r"\bable to block\b[^.]*\bdo so\b", re.IGNORECASE)
_TEXT_CHANGE = re.compile(
    r"\bchange the text\b|\bchange ~'s\b|\bchange\b[^.]{0,15}\bbase power\b",
    re.IGNORECASE,
)
# A characteristic/animation set: "~ is a 2/3 Gargoyle", "~ is a 5/5 Golem artifact
# creature" — a continuous become-a-creature (CR animate), N/N word-bounded.
# "~ is a 2/3 Gargoyle", "is a Bear with base power and toughness 4/2", "is an
# artifact creature" — the P/T or "creature" head appears within the phrase.
_ANIMATE = re.compile(
    r"\bis an? [\w '-]{0,45}?(?:[\dx*]+/[\dx*]+|creature)\b"
    # a Job-select bullet mode "• <Name> — {cost} — N/N" (becomes that creature).
    r"|^•[^.]*—[^.]*[\dx*]+/[\dx*]+",
    re.IGNORECASE,
)
_MANA_RESTRICTION = re.compile(
    r"\bspend (?:only|this mana only)\b|\bspend this mana only\b", re.IGNORECASE
)
# A keyword ability that survived as bare text: any "<type>cycling" (CR 702.29) and
# any basic-land-type "…walk" landwalk (CR 702.14 evasion).
_CYCLING = re.compile(r"\b\w*cycling\b", re.IGNORECASE)
_LANDWALK = re.compile(
    r"\b(?:desert|forest|island|mountain|swamp|plains)walk\b", re.IGNORECASE
)
# "Activate only as a sorcery / during your turn" — an activation-timing restriction.
_ACTIVATE_ONLY = re.compile(r"\bactivate only\b", re.IGNORECASE)
_BID = re.compile(r"\bbid life\b|\bstart the bidding\b", re.IGNORECASE)
_DRAFT = re.compile(r"\bdraft (?:this|each|up to|an|a |\d|that)", re.IGNORECASE)
# Redirect / re-target effects: "reselect which … target", "that damage is dealt to
# … instead", "change the target" (already handled separately).
_REDIRECT = re.compile(
    r"\breselect\b|\bthat damage is dealt to\b|\bredirect\b"
    r"|\bchange (?:any|the|all|its)\b[^.]{0,20}\btargets?\b",  # "change any targets of"
    re.IGNORECASE,
)
# Misc named one-offs caught as statics: an emblem grant, monarch-control aura.
_EMBLEM = re.compile(r"\b(?:gets?|with|creates?) an emblem\b", re.IGNORECASE)
_MONARCH_CONTROL = re.compile(r"\bmonarch controls\b", re.IGNORECASE)
# An attack restriction: "may attack only the nearest opponent", "attack only the".
_ATTACK_ONLY = re.compile(r"\b(?:may |can )?attack only\b", re.IGNORECASE)
# Named one-off mechanics — each names a real mechanic (accurate IR), mapped to its
# own honest category. `(pattern, category)` pairs, scanned in order, after the broad
# rules above so a more general match wins first.
_NAMED_MECHANICS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\breverse the .*turn order\b", re.IGNORECASE), "reverse_turn"),
    (re.compile(r"\bredistribute\b.*\blife totals?\b", re.IGNORECASE), "set_life"),
    (re.compile(r"\bno maximum hand size\b", re.IGNORECASE), "no_max_handsize"),
    (re.compile(r"\bplay with .*hands? revealed\b", re.IGNORECASE), "reveal_hands"),
    (re.compile(r"\blegend rule\b", re.IGNORECASE), "legend_exempt"),
    (re.compile(r"\bskips? (?:your|their|his|her) next\b", re.IGNORECASE), "skip_turn"),
    (re.compile(r"\bunattach\b", re.IGNORECASE), "unattach"),
    (re.compile(r"\bharness\b", re.IGNORECASE), "harness"),
    (re.compile(r"\bnote (?:your|their) life total\b", re.IGNORECASE), "note"),
    (
        re.compile(r"\b(?:triggers?|trigger) .*\ban additional time\b", re.IGNORECASE),
        "trigger_doubling",
    ),
    (re.compile(r"\ban additional time\b", re.IGNORECASE), "trigger_doubling"),
    (
        re.compile(r"\btriggers? only once\b|\bonly you may activate\b", re.IGNORECASE),
        "restriction",
    ),
    (re.compile(r"\bdo all of the above\b", re.IGNORECASE), "modal"),
    (
        re.compile(r"\beach player separates\b|\binto two piles\b", re.IGNORECASE),
        "fact_or_fiction",
    ),
    (re.compile(r"\bunlock\b[^.]*\bdoor\b", re.IGNORECASE), "unlock"),
    (re.compile(r"\bactivate exhaust\b|\bexhaust abilit", re.IGNORECASE), "exhaust"),
    (re.compile(r"\b(?:is|are) sacrificed\b", re.IGNORECASE), "sacrifice"),
    (re.compile(r"\byou control your opponents\b", re.IGNORECASE), "gain_control"),
    (re.compile(r"\bexchange life\b", re.IGNORECASE), "set_life"),
    (re.compile(r"\bdouble the value of\b", re.IGNORECASE), "double"),
    (re.compile(r"\bdevotion to each color\b", re.IGNORECASE), "devotion"),
    # ADR-0027: emit "end_the_turn" (matching phase's native endtheturn->end_the_turn
    # map in project._EFFECT_CATEGORY and the _DOER_EFFECT_KEYS key) so the
    # failed-parse recovery binds the end_the_turn lane (Obeka). The old "end_turn"
    # string matched no signal binding and was silently dropped.
    (re.compile(r"\b(?:may )?end the turn\b", re.IGNORECASE), "end_the_turn"),
    (re.compile(r"\bcast this spell only if\b", re.IGNORECASE), "restriction"),
    (re.compile(r"\beffects from spells named\b", re.IGNORECASE), "name_matters"),
    (re.compile(r"\bdon'?t cause abilities\b", re.IGNORECASE), "trigger_suppression"),
    (
        re.compile(
            r"\bexchange (?:his|its|their) text\b|\bcolor words\b[^.]*\bchanged\b",
            re.IGNORECASE,
        ),
        "text_change",
    ),
    (
        re.compile(r"\bexchange your hand and graveyard\b", re.IGNORECASE),
        "exchange_zones",
    ),
    (
        re.compile(r"\bcircle (?:one|two|three) of the colors\b", re.IGNORECASE),
        "deckbuild",
    ),
    (re.compile(r"\byou win the game\b", re.IGNORECASE), "win_game"),  # win-con payoff
    (re.compile(r"\byou lose the game\b", re.IGNORECASE), "lose_game"),
    (re.compile(r"\bget [\dx]+ \{e\}", re.IGNORECASE), "place_counter"),  # energy
    (re.compile(r"^companion\b", re.IGNORECASE), "companion"),  # deckbuild constraint
    (re.compile(r"^blitz\b", re.IGNORECASE), "alt_cost"),  # an alternative cost
    (
        re.compile(r"\blethal damage\b[^.]*\bdetermined by\b", re.IGNORECASE),
        "damage_assignment",  # Zilortha — power as toughness for lethal damage
    ),
)
# A generic REPLACEMENT effect: "If [a thing] would [happen] …, [instead] …" — the
# recurring token/counter/mana/draw replacement shape phase leaves Unimplemented.
# Checked LAST among statics (after the specific damage/doubling replacements), so it
# only catches the residual; its own non-sliced `replacement` category.
_REPLACEMENT = re.compile(
    r"\bif\b[^.]*\bwould\b[^.]*\binstead\b|\bwould .* instead\b", re.IGNORECASE
)
# A casting-timing restriction: "(Players) can cast spells (and activate abilities)
# only during their own turns".
_CAST_RESTRICT = re.compile(
    r"\bcan cast spells (?:and activate abilities )?only\b|\bcast spells only\b",
    re.IGNORECASE,
)
# A mana-production modification ("if you tap … for mana, it produces twice as much",
# "produces {C} instead of …", "produces three times") — a mana doubler/filter.
_MANA_PRODUCE = re.compile(
    r"\bfor mana, it produces\b|\bproduces (?:twice|three times)\b"
    r"|\bproduces .{0,20}\binstead of\b|\bproduces colorless\b",
    re.IGNORECASE,
)
# ADR-0027 β — the mana-AMPLIFY subset of _MANA_PRODUCE: a tap-for-mana doubler that
# multiplies the AMOUNT produced ("it produces twice/three times as much" — Mana
# Reflection, Virtue of Strength/Garenbrig Growth). Checked BEFORE _MANA_PRODUCE so it
# splits the amount-MULTIPLIER doublers OUT of the generic mana_filter passthrough; the
# color-CHANGE forms ("produces {C} instead", "produces colorless" — Damping Sphere,
# Pale Moon, Pulse of Llanowar, Deep Water, Harvest Mage, Quarum Trench Gnomes, Mirri)
# and the any-color SPEND permission (_MANA_FILTER — Celestial Dawn, Vizier of the
# Menagerie) are NOT amplifiers and correctly stay mana_filter. This is the doubler arm
# of the mana_amplifier lane; the triggered "tap a land … add an additional" doublers
# (Crypt Ghast, Mirari's Wake) phase types as a triggered `ramp` Mana effect, read
# discriminator-gated in extract_signals_ir (additive — they keep firing ramp).
# CR 106.4 / 605.
_MANA_AMPLIFY = re.compile(
    r"\bproduces (?:twice|three times)\b"
    r"|\bfor mana, it produces (?:twice|three times)\b",
    re.IGNORECASE,
)
# An activation-PERMISSION ("you may activate loyalty/equip abilities … any time/twice
# each turn", "activate the loyalty abilities of …").
_ACTIVATION_PERM = re.compile(
    r"\bactivate (?:the )?(?:loyalty|equip) abilities\b"
    r"|\bactivate .{0,30}\babilities\b[^.]{0,30}\b(?:any time|twice each turn)\b",
    re.IGNORECASE,
)
# Crew (CR 702.122), Phasing (702.26), Haunt (702.55) keyword abilities as text.
_CREW = re.compile(r"\bcrews? vehicles?\b", re.IGNORECASE)
_PHASING = re.compile(r"\bphases? (?:in|out)\b|\bphased[- ]out\b", re.IGNORECASE)
_HAUNT = re.compile(r"\bhaunts?\b", re.IGNORECASE)
_CONTROL_COMBAT = re.compile(  # "you choose which creatures attack/block"
    r"\bchoose which creatures? (?:attack|block)", re.IGNORECASE
)
_ASSIGN_DAMAGE = re.compile(r"\bassigns? (?:no |the )?combat damage\b", re.IGNORECASE)
# Mana filtering / "any color" spend permission ("spend white mana as though it were
# any color", "Mana of any type can be spent to …", "spend mana of any type").
_MANA_FILTER = re.compile(
    r"\bspend (?:[a-z]+ )?mana as though\b|\bmana of any (?:type|color) can be spent\b"
    r"|\bspend mana of any (?:type|color)\b|\bspend mana as though\b",
    re.IGNORECASE,
)
# A type-defining static ("Creatures you control are the chosen type", "Lands you
# control are every basic land type", "Nontoken creatures … are Forest lands") — a
# continuous type set/grant. Its own non-sliced category.
_TYPE_SET = re.compile(
    r"\bare (?:the (?:first |second )?chosen|every basic land type|all basic land types"
    r"|[a-z]+ lands?\b|white|blue|black|red|green|colorless|legendary|all colors"
    r"|(?:plains|islands?|swamps?|mountains?|forests?)\b)"
    r"|\b(?:is|are) all colors\b|\b(?:is|are) (?:snow|basic)\b"
    r"|\b(?:is|are) every (?:nonbasic )?(?:land|creature) type\b"
    r"|\bis a (?:flagbearer|demon spirit)\b|\benters? untapped\b"
    r"|\bis an? (?:plains|island|swamp|mountain|forest)\b"
    # the "in addition to (its/their) other …" frame is the type-ADDING tell
    # ("Each land is a Swamp in addition to its other land types").
    r"|\bin addition to (?:its|their|your) other\b",
    re.IGNORECASE,
)
# "there is an additional combat phase" / "an additional combat phase after this" —
# an extra-combat granter (phase's additionalphase category).
_EXTRA_COMBAT = re.compile(
    r"\badditional (?:combat|beginning|main|end|precombat|postcombat) phase\b",
    re.IGNORECASE,
)
# Flagbearer (CR 720-era "while an opponent is choosing targets … must choose this")
# and flashback-cost / cost-reduction-qualifier statics.
_FLAGBEARER = re.compile(r"\bwhile an opponent is choosing targets\b", re.IGNORECASE)
_FLASHBACK = re.compile(r"\bflashback cost is equal\b", re.IGNORECASE)
_COST_RED_QUAL = re.compile(r"\bthis effect reduces only\b", re.IGNORECASE)
_DAMAGE_PERSIST = re.compile(r"\bdamage isn'?t removed\b", re.IGNORECASE)
# "(on the) top/bottom of … library" — a library-position placement ("on top of their
# library", "the top or bottom of its owner's library"). The "on" is optional.
_LIBRARY_POS = re.compile(
    r"\b(?:top|bottom)\b[^.]{0,40}\b(?:library|libraries)\b", re.IGNORECASE
)
# A player keyword grant — "You have hexproof/shroud/protection/…": grant_keyword,
# gated to real protective keywords so "you have no maximum hand size" stays out.
_PLAYER_KW_GRANT = re.compile(
    r"\byou have (?:hexproof|shroud|protection|indestructible|ward)", re.IGNORECASE
)
# An evergreen keyword printed bare on the permanent ("Hexproof from artifacts …",
# "Protection from red") — a self keyword grant.
_BARE_KEYWORD = re.compile(
    r"^(?:hexproof|protection|ward|shroud) (?:from|—|\{)", re.IGNORECASE
)
# A characteristic-defining P/T ("[its] power and toughness are each equal to …",
# "power is equal to …") — a DYNAMIC characteristic, distinct from base_pt_set's
# FIXED "base power and toughness N/N" (conflating them floods that lane), so its own
# category (not IR-sliced — completes the parse only). The P/T characteristic is the
# subject, so a discriminant scan; the imperative "deals damage equal to its power"
# is caught by the verb grammar first, so this only sees true CDAs.
_CDA_PT = re.compile(
    r"\b(?:power|toughness)\b[^.]{0,40}\b(?:is|are)\b[^.]{0,20}\bequal to\b",
    re.IGNORECASE,
)
_HAVE_GAIN = re.compile(r"\b(?:have|has|gains?)\b", re.IGNORECASE)
# ADR-0027 (SIDECAR v32, Cluster C): a FIXED base-P/T set static phase's static parser
# FAILED on (Curse of Conformity "Nonlegendary creatures … have base power and toughness
# 3/3", Overwhelming Splendor "… have base power and toughness 1/1"). Without this it
# falls to the _HAVE_GAIN grant fallback below (→ grant_keyword), dropping the base-P/T
# set. Requires a LITERAL fixed value ("base power and toughness N" / "base power N" /
# "base toughness N"); the dynamic "base power … equal to X" form (CDA) is NOT a fixed
# set and is excluded so variable_pt keeps it. CR 613.4b vs 613.4a.
_HAS_BASE_PT = re.compile(
    r"\bbase power(?: and toughness)? \d|\bbase toughness \d", re.IGNORECASE
)
# A keyword grant whose subject is a TRIBE/type we don't anchor ("Warriors your team
# control have haste", "Knights … have flying") — anchored on the GRANTED keyword
# instead (a closed CR keyword-ability set), so it fires without a noun anchor.
_KEYWORD_GRANT = re.compile(
    r"\b(?:have|has|gains?)\b[^.]{0,30}\b(?:each of the chosen abilities"
    r"|all (?:activated|triggered) abilities|flying|trample|haste|vigilance|deathtouch"
    r"|lifelink|menace|reach|hexproof|indestructible|first strike|double strike|flash"
    r"|defender|protection|ward|shroud|fear|intimidate|horsemanship|shadow|skulk"
    r"|infect|wither|persist|undying|forestwalk|islandwalk|swampwalk|mountainwalk"
    r"|plainswalk|landwalk|unblockable)\b",
    re.IGNORECASE,
)
# "If you would flip a coin, instead flip two coins …", "flip one or more coins".
_COIN = re.compile(r"\bflips?\b[^.]{0,18}\bcoins?\b", re.IGNORECASE)
_BECOMES = re.compile(r"\bbecomes?\b", re.IGNORECASE)
# A cost alteration (CR 118.9): "… costs {N} less to cast", "… cost {2} more".
# The altered SET precedes "cost", so a discriminant scan (like the anthem above).
# Allow a multi-symbol reduction ("cost {B}{R} less") — one or more brace groups, or
# none ("costs less").
_COST_ALTER = re.compile(
    r"\bcosts?\s+(?:\{[^}]*\}\s*)*(?:less|more)\b|\bcosts?\s+an additional\b",
    re.IGNORECASE,
)
# Disambiguate the "gain(s)" family: a life gain ("gains 5 life", "gain that much
# life") vs control ("gains control of") vs an ABILITY/keyword grant (everything
# else: "gains flashback", "has hexproof"). \blife\b is word-bounded so "lifelink"
# (a keyword grant) does NOT read as life. Control is checked before the bare grant.
_GAIN_LIFE = re.compile(r"\bgains?\b[^.]*\blife\b", re.IGNORECASE)
_GAIN_CONTROL = re.compile(r"\bgains?\s+control\b", re.IGNORECASE)
# A grant whose subject was stripped as a prefix ("It gains deathtouch", "They gain
# flying", "~ gains islandwalk") — the clause LEADS with a self/back-reference + a
# gain/has verb, so it's a keyword grant even without a grantable noun left in it.
_LEAD_GRANT = re.compile(
    r"^(?:it|they|this \w+|that \w+|target \w+|~)\s+(?:gains?|has|have)\s",
    re.IGNORECASE,
)
# Grantable-set anchors: a keyword grant names what GETS the ability (creatures,
# slivers, lands, the self ~, a card type, enchanted/equipped). Requiring one keeps
# the grant fallback off bare conditionals ("if you have …", "has been …").
_GRANTABLE_SUBJECT = (
    "creature",
    "permanent",
    "sliver",
    "land",
    "instant",
    "sorcery",
    "spell",
    "artifact",
    "enchantment",
    "planeswalker",
    "vehicle",
    "enchanted ",
    "equipped ",
    "~",
)


def _recover_static_pattern(e: Effect) -> Effect | None:
    s = _FAILED_PREFIX.sub("", e.raw).strip()
    if _GETS_PT.search(s):
        return replace(e, category="pump")
    if _COST_ALTER.search(s):
        return replace(e, category="cost_reduction")
    if _CANT.search(s) or _COMBAT_CAP.search(s):
        scope = "opp" if _OPP_RESTRICTION.search(s) else e.scope
        return replace(e, category="restriction", scope=scope)
    if _CAN_COMBAT.search(s):
        return replace(e, category="grant_keyword")  # combat permission grant
    if _TUCK.search(s):
        return replace(e, category="shuffle")
    if _CDA_PT.search(s):
        return replace(e, category="characteristic_pt")
    # ADR-0027 (SIDECAR v32): a fixed base-P/T set the static parser failed (Curse of
    # Conformity / Overwhelming Splendor) → base_pt_set, BEFORE the _HAVE_GAIN grant
    # fallback claims it as grant_keyword. After _CDA_PT so a dynamic */* keeps its
    # lane. v45: carry the discriminated scope + Creature subject + toughness amount
    # (the same fields the card-level recovery synthesizes) so debuff_makers reads a
    # mass opp/symmetric shrink structurally. CR 613.4b.
    if _HAS_BASE_PT.search(s):
        sc, subj, amt = _base_pt_set_fields(s)
        return replace(e, category="base_pt_set", scope=sc, subject=subj, amount=amt)
    if _STATE.search(s):
        return replace(e, category="state")
    if _FLASH_GRANT.search(s) or _PLAYER_KW_GRANT.search(s) or _BARE_KEYWORD.match(s):
        return replace(e, category="grant_keyword")
    if _TEXT_CHANGE.search(s):
        return replace(e, category="text_change")
    if _MANA_RESTRICTION.search(s):
        return replace(e, category="mana_restriction")
    if _ACTIVATE_ONLY.search(s):
        return replace(e, category="restriction")
    if _CYCLING.search(s):
        return replace(e, category="cycling")
    if _LANDWALK.search(s):
        return replace(e, category="evasion")
    if _MANA_FILTER.search(s):
        return replace(e, category="mana_filter")
    if _KEYWORD_GRANT.search(s):
        return replace(e, category="grant_keyword")
    if _COIN.search(s):
        return replace(e, category="coin_flip")
    if _ATTACK_ONLY.search(s) or _CAST_RESTRICT.search(s):
        return replace(e, category="restriction")
    # ADR-0027 β — the amount-MULTIPLIER doublers split OUT of mana_filter (checked
    # first so a "produces twice/three times" amplifier never falls through to the
    # color-change mana_filter below). CR 106.4.
    if _MANA_AMPLIFY.search(s):
        return replace(e, category="mana_amplifier")
    if _MANA_PRODUCE.search(s):
        return replace(e, category="mana_filter")
    if _ACTIVATION_PERM.search(s):
        return replace(e, category="activation_permission")
    if _CREW.search(s):
        return replace(e, category="crew")
    if _PHASING.search(s):
        return replace(e, category="phasing")
    if _HAUNT.search(s):
        return replace(e, category="haunt")
    if _REDIRECT.search(s):
        return replace(e, category="redirect")
    if _EMBLEM.search(s):
        return replace(e, category="emblem")
    if _MONARCH_CONTROL.search(s):
        return replace(e, category="gain_control")
    for pat, cat in _NAMED_MECHANICS:
        if pat.search(s):
            # ADR-0027 C11_loot (SIDECAR v51) — "your opponents play with their hands
            # revealed" (Telepathy) is inherently an opponent-directed reveal, so stamp
            # scope='opp' here (phase emits no scope on the re-categorized form). The
            # hand_disruption signal arm reads `reveal_hands` regardless of scope, but
            # the 'opp' is carried for honesty and any downstream scope reader.
            if cat == "reveal_hands":
                return replace(e, category=cat, scope="opp")
            return replace(e, category=cat)
    if _CLONE_STATIC.search(s):
        return replace(e, category="clone")
    if _FORCE_ATTACK.search(s):
        return replace(e, category="force_attack")
    if _FORCE_BLOCK.search(s):
        return replace(e, category="lure")
    if _BID.search(s):
        return replace(e, category="bid")
    if _DRAFT.search(s):
        return replace(e, category="draft")
    if _CONTROL_COMBAT.search(s):
        return replace(e, category="control_combat")
    if _ASSIGN_DAMAGE.search(s):
        # ADR-0027 C14 — stamp the `from_toughness` marker (consistent with the project
        # AssignDamageFromToughness arm) when the clause is "assigns combat damage equal
        # to its TOUGHNESS rather than its power" (Doran's abilityless single-static
        # face, recovered here). "assigns NO combat damage" (Master of Cruelties — a
        # suppression, CR 510.1b/c) is the same regex but NOT a toughness care, so it
        # gets no marker and the toughness_combat lane excludes it structurally.
        ck = "from_toughness" if "toughness" in s.lower() else ""
        return replace(e, category="combat_damage_mod", counter_kind=ck)
    if _TYPE_SET.search(s):
        return replace(e, category="type_set")
    if _EXTRA_COMBAT.search(s):
        return replace(e, category="extra_combats")
    if _FLAGBEARER.search(s):
        return replace(e, category="flagbearer")
    if _FLASHBACK.search(s):
        return replace(e, category="grant_keyword")
    if _COST_RED_QUAL.search(s):
        return replace(e, category="cost_reduction")
    if _DAMAGE_PERSIST.search(s):
        return replace(e, category="damage_persist")
    if _LIBRARY_POS.search(s):
        return replace(e, category="topdeck_select")
    if _ALT_COST.search(s):
        return replace(e, category="alt_cost")
    if _DAMAGE_REPLACE.search(s):
        return replace(e, category="damage_replace")
    low = s.lower()
    # The gain/have family: a life gain or control gain (any subject), else a
    # "<grantable set> gains/has <ability>" keyword grant. The grant fallback keeps a
    # subject anchor (a grantable noun in the clause) so a bare conditional "if you
    # have no cards" doesn't read as a grant; life/control need no anchor.
    if _HAVE_GAIN.search(s):
        if _GAIN_CONTROL.search(s):
            return replace(e, category="gain_control")
        if _GAIN_LIFE.search(s):
            return replace(e, category="gain_life")
        if _LEAD_GRANT.match(s) or any(w in low for w in _GRANTABLE_SUBJECT):
            return replace(e, category="grant_keyword")  # coarse — no keyword yet
    # "<subject> becomes a copy of …" → clone; "<subject> becomes a 4/4 …" → animate
    # (the subject precedes the verb, so this is a discriminant scan, not a parse).
    if _BECOMES.search(s):
        return replace(e, category="clone" if "copy of" in low else "animate")
    if _ANIMATE.search(s):
        return replace(e, category="animate")
    # LAST: a generic "if … would …, instead …" replacement effect (the residual
    # token/counter/mana/draw replacements the specific rules above didn't claim).
    if _REPLACEMENT.search(s):
        return replace(e, category="replacement")
    return None


# A NAMED ability — a card-specific flavour name before an em-dash ("Venom Blast —
# Artifacts … enter tapped", "Allure of Slaanesh — Each opponent …"), the generic form
# of the enumerated _ABILITY_WORDS. Strip the name and dispatch the effect after it.
# Gated so it can't eat a modal "Choose one — • …" (bullet after) or a Saga "Chapter
# N —" or a numbered/level head, and the head must be short (a name, not a sentence).
_EM_DASH = re.compile(r"\s*—\s*")


def _recover_named_ability(e: Effect) -> Effect | None:
    s = _FAILED_PREFIX.sub("", e.raw).strip()
    m = _EM_DASH.search(s)
    if m is None:
        return None
    head, tail = s[: m.start()].strip(), s[m.end() :].strip()
    if not head or not tail or len(head) > 40 or "•" in head or tail.startswith("•"):
        return None
    if head.lower().startswith(("choose", "chapter")) or head[:1].isdigit():
        return None
    # dispatch the effect after the name (verb clause -> static -> scan; no recursion).
    tail_eff = replace(e, raw=tail)
    r = _EFFECT_CLAUSE.parse(tail)
    if r is not None:
        return replace(e, category=r[0])
    return _recover_static_pattern(tail_eff) or _recover_verb_scan(tail_eff)


# The recovery registry. Order matters: the first matching rule wins, so put the
# most specific clauses first. Doubling is tried before create_token (a "twice that
# many … tokens" clause is a doubler, not a plain token maker). The two broad
# dispatchers (leading-verb, then static-pattern) run LAST — the catch-all gap-filler
# after the specific structured recoveries. Grow this as the fan-out owns more tail.
_RECOVERY_RULES: tuple[ClauseRule, ...] = (
    ClauseRule("graveyard_cast", _recover_graveyard_cast),
    ClauseRule("vote", _recover_vote),
    ClauseRule("doubling", _recover_doubling),
    ClauseRule("create_token", _recover_create_token),
    ClauseRule("named_ability", _recover_named_ability),
    ClauseRule("by_verb", _recover_by_verb),
    ClauseRule("static_pattern", _recover_static_pattern),
    ClauseRule("verb_scan", _recover_verb_scan),
)


# A bare Saga "Chapter N" (optionally "Chapter N, M") that leaked in as its own
# `other` effect — a chapter-timing LABEL, not a mechanical effect (the chapter's
# real effect is a sibling effect/trigger). Dropping it un-masks that sibling so the
# ability isn't held `partial` by a label; a chapter whose effect phase genuinely
# lost keeps an empty ability and stays partial (honest).
_CHAPTER_LABEL = re.compile(r"^chapter [\divxlc, ]+$", re.IGNORECASE)
# Continuation / glue fragments that are NOT a standalone effect — they qualify or
# extend a SIBLING clause: "The same is true for …" (extends a prior set), "X is the
# number of …" / "where X is …" (defines a prior operand), a bare self-ref "~." (a
# split artifact). Like a chapter label, these aren't mechanical effects.
_GLUE_FRAGMENT = re.compile(
    r"^(?:the same is true\b|x is (?:the|equal)\b|where x is\b|~\.?$"
    r"|if you do\b|rounded (?:up|down)\b)",
    re.IGNORECASE,
)


def _is_noneffect_label(e: Effect) -> bool:
    if e.category != "other":
        return False
    raw = (e.raw or "").strip()
    return bool(_CHAPTER_LABEL.match(raw)) or bool(_GLUE_FRAGMENT.match(raw))


def _is_empty_other(e: Effect) -> bool:
    return e.category == "other" and not (e.raw or "").strip()


def _clean_ability(ab: Ability) -> Ability:
    """Supplement each effect, then drop two kinds of non-effect `other`: a bare Saga
    chapter LABEL (timing marker), and a TEXTLESS `other` when the ability also has a
    structured (recovered) effect — phase emitted a contentless node alongside the real
    effect (e.g. a tutor's reveal sub-step), so it's a redundant artifact carrying no
    information. A textless `other` that is an ability's SOLE content is KEPT: that
    ability was wholly lost, and the card should stay honestly partial."""
    supplemented = [_supplement_effect(e) for e in ab.effects]
    has_structured = any(e.category != "other" for e in supplemented)
    kept = [
        e
        for e in supplemented
        if not _is_noneffect_label(e) and not (has_structured and _is_empty_other(e))
    ]
    return replace(ab, effects=tuple(kept))


def supplement_card(card: Card) -> Card:
    """Return *card* with each effect's category/scope recovered from its raw, the
    non-effect `other`s dropped (chapter labels; redundant textless nodes), and any
    NON-static ability left with no effects after cleaning dropped entirely — such an
    ability held only a glue continuation ("The same is true …") that phase
    mis-attributed to its own ability; the real effect lives on a sibling (e.g. the
    static), so the empty shell is spurious, not a parse gap (genuinely-lost abilities
    were already oracle-filled upstream by _fill_sole_empty). See _clean_ability."""
    faces = tuple(
        replace(
            face,
            abilities=tuple(
                ab
                for raw_ab in face.abilities
                if (ab := _clean_ability(raw_ab)).effects or ab.kind == "static"
            ),
        )
        for face in card.faces
    )
    return replace(card, faces=faces)


def recover_effect_from_text(raw: str) -> Effect:
    """Run the full clause recovery on a bare oracle sentence → a structured Effect
    (category="other" if nothing matched). The seam projection uses to fill a
    sole-empty ability from its card's oracle (an effect phase structured but left
    textless), reusing the exact same grammar the in-IR `other`s go through."""
    return _supplement_effect(Effect(category="other", scope="any", raw=raw))


# ── #24e P1 parser-substrate: anchor-then-parse dispatch ──────────────────────
# The bucket-B card-level recoveries below detect with a `_combinators` word-parser
# instead of a regex. A word-combinator costs more per call than a compiled regex
# (it walks the clause word by word), so running it on every card's whole oracle
# would bloat the build. phase avoids this by ANCHORING via a cheap dispatch and
# parsing only the structured part; we mirror that: a fast lowercase-substring gate
# (a NECESSARY lead substring of the parser's match — never a false negative) keeps
# the combinator off the ~99% of cards that cannot match. The combinator stays the
# DETECTOR (whole-word, slot-by-slot); the substring is only the dispatch key.


def _anchored[T](text: str, anchor: str, parser: comb.Parser[T]) -> bool:
    """``anchor in text.lower()`` (cheap dispatch) AND ``parser`` matches (the real
    word-combinator detection). ``anchor`` must be a necessary lead substring of any
    string the parser accepts, so gating never drops a real match."""
    return anchor in text.lower() and parser.run(text) is not None


def _iter_spans(text: str, parser: comb.Parser[Any]) -> Iterator[tuple[str, Any]]:
    """Yield ``(matched_span, value)`` for every NON-overlapping place ``parser``
    matches, left to right — the structural analogue of ``re.finditer`` (advances past
    each match's end, like ``finditer``). ``parser`` anchors at its own lead word."""
    rest = text
    while True:
        r = parser.run(rest)
        if r is not None:
            span = rest[: len(rest) - len(r[1])].strip()
            yield (span, r[0])
            rest = r[1]
            continue
        w = comb.word().run(rest)
        if w is None:
            return
        rest = w[1]


def _scan_span(text: str, parser: comb.Parser[Any]) -> str | None:
    """The first clause-span in ``text`` where ``parser`` matches at a word boundary,
    returned as the matched substring (start-of-anchor → end-of-parser) — the
    structural analogue of ``re.search(...).group(0)`` for recovering a synthetic
    Effect's ``raw``. ``None`` if the parser never matches. ``parser`` should anchor at
    its OWN lead word (it is tried at each successive boundary, like ``scan``)."""
    rest = text
    while True:
        r = parser.run(rest)
        if r is not None:
            return rest[: len(rest) - len(r[1])].strip()
        w = comb.word().run(rest)
        if w is None:
            return None
        rest = w[1]


# ── ADR-0027 combat-damage RECIPIENT residue (SIDECAR v41) ────────────────────
# project.py stamps a structured `recipient` on every NATIVE combat_damage trigger
# (the DamageDone / DamageDoneOnceByController modes), but phase leaves combat-damage
# payoffs UNSTRUCTURED when the trigger is QUOTED inside a granted ability that lives
# in an ACTIVATED ability or a one-shot spell/Saga/emblem grant, or is a "would deal
# combat damage" REPLACEMENT — phase keeps no DamageDone trigger and sometimes drops
# the clause from the effect raw entirely. For those, the recipient discriminator
# survives only in the card's RAW oracle, so we synthesize a combat_damage trigger
# (with the recipient) from the raw — the sanctioned residue path (NOT a retained
# regex MIRROR in signals; the lanes still read `trig.recipient` STRUCTURALLY).
# Patterns are the EXACT recipient phrasings the three deleted SWEEP/HAND_FLOOR
# regexes anchored on, so the recovered set is byte-identical to the deleted mirrors.
# CR 510.1b (player / planeswalker) / 510.1c (creature) / 120.3.
# A PLAYER / planeswalker recipient survives in the raw three ways the deleted regexes
# matched: a "whenever ~ deals combat damage to a player/opponent" trigger, a "would
# deal combat damage to a player/opponent" REPLACEMENT (CR 615 — Charging Tuskodon,
# Szadek, Undead Alchemist), and the passive "player who was dealt combat damage by ~"
# reference (CR 510.2 — Steel Hellkite, Hope of Ghirapur, Admiral Beckett Brass). All
# three are combat-damage-to-a-player payoffs (the structural recipient is a player), so
# all three fire BOTH the base matters lane and to_opp — a player recipient is a player
# recipient regardless of the verb. CR 510.1b / 615.
# #24e P3 parser-substrate: the combat-damage RECIPIENT detector reads STRUCTURE.
# PLAYER arm A — (when|whenever|would) <bounded gap> "deals combat damage to" <player
# recipient bag>: the "a player or planeswalker / or battle" variants are subsumed by
# the bare "a player" slot (it matches the lead two words), exactly as the regex's
# leftmost-alternation did. PLAYER arm B — the passive "was/were dealt combat damage
# by" reference. CREATURE — "deals combat damage to (a|another|one or more) creature(s)"
# (the regex's "whenever <gap> deals combat damage to a creature" arm is fully subsumed
# by this, which anchors on "deals" anywhere). Ports to phase-rs as nom tuples.
_CDMG_DEALS_TO = comb.phrase({"deal", "deals"}, {"combat"}, {"damage"}, {"to"})
_CDMG_PLAYER_RECIPIENT = comb.alt(
    comb.phrase({"a"}, {"player"}),
    comb.phrase({"an"}, {"opponent"}),
    comb.phrase({"one"}, {"of"}, {"your"}, {"opponents"}),
    comb.phrase({"each"}, {"opponent"}),
    comb.phrase({"that"}, {"player"}),
)
_CDMG_RECIPIENT_PLAYER = comb.alt(
    comb.scan(
        comb.seq2(
            comb.keyword({"when", "whenever", "would"}),
            comb.bounded_scan(comb.seq2(_CDMG_DEALS_TO, _CDMG_PLAYER_RECIPIENT)),
        )
    ),
    comb.scan(comb.phrase({"was", "were"}, {"dealt"}, {"combat"}, {"damage"}, {"by"})),
)
_CDMG_RECIPIENT_CREATURE = comb.scan(
    comb.seq3(
        comb.phrase({"deals"}, {"combat"}, {"damage"}, {"to"}),
        comb.alt(
            comb.phrase({"one"}, {"or"}, {"more"}), comb.keyword({"a", "another"})
        ),
        comb.keyword({"creature", "creatures"}),
    )
)


def combat_damage_recipients_from_text(text: str) -> frozenset[str]:
    """The combat-damage RECIPIENT type(s) a raw oracle names — {player, creature}
    (planeswalker folds into the player-or-planeswalker phrasing). The reminder-strip
    happens here, so callers pass raw oracle. Public because the deck-forge hybrid path
    reuses it to recover the recipient of a runtime-FOLDED object (the Ring-bearer's
    "deals combat damage to a player" level) whose text is not in the commander's
    pre-built sidecar IR. CR 510.1b / 510.1c / 510.2 / 615."""
    stripped = re.sub(r"\([^)]*\)", " ", text or "")
    low = stripped.lower()
    out: set[str] = set()
    # cheap dispatch: every player arm carries "combat damage" (arm A) or "dealt
    # combat damage by" (arm B); the creature detector likewise needs "combat damage".
    if "combat damage" in low and _CDMG_RECIPIENT_PLAYER.run(stripped) is not None:
        out.add("player")
    if "combat damage to" in low and _CDMG_RECIPIENT_CREATURE.run(stripped) is not None:
        out.add("creature")
    return frozenset(out)


def _recover_combat_damage_recipients(card: Card, oracle: str) -> Card:
    """Append synthetic ``combat_damage`` Trigger abilities for recipient types that
    phase left wholly unstructured but the raw *oracle* still names (granted-in-an-
    activated-ability / one-shot grants / "would deal combat damage" replacements).
    Append-only and recipient-deduped: a recipient already carried by a NATIVE
    combat_damage trigger is not re-synthesized, so a fully-structured card is
    untouched. The synthetic ability lands on the first face (the IR rollup is
    face-agnostic for these lanes)."""
    wanted = set(combat_damage_recipients_from_text(oracle))
    if not wanted or not card.faces:
        return card
    native = {
        r
        for ab in card.all_abilities()
        if ab.trigger is not None and ab.trigger.event == "combat_damage"
        for r in ab.trigger.recipient
    }
    missing = tuple(sorted(wanted - native))
    if not missing:
        return card
    raw = re.sub(r"\([^)]*\)", " ", oracle).strip()
    synth = Ability(
        kind="triggered",
        trigger=Trigger(event="combat_damage", recipient=missing),
        effects=(Effect(category="other", raw=raw),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 base-P/T SET static residue (SIDECAR v45) ────────────────────────
# phase v0.1.60 has a TOTAL blind spot for the layer-7b "set base power and/or
# toughness to a specific value" static (CR 613.4b): ALL 222 commander-legal cards
# whose oracle carries "base power and toughness N/M" / "base power N" / "base
# toughness N" parse to ZERO abilities — Maha, Lignify, Humility, Curse of
# Conformity, Biomass Mutation, Godhead of Awe, Flatline. base_pt_set already fires
# for them off the carved kept word mirror (it scans the raw oracle), but the
# MIGRATED debuff_makers lane reads IR and saw nothing for an opponent / symmetric
# MASS shrink — Maha "Creatures your opponents control have base toughness 1" is a
# -1/-1 enabler (7b sets toughness 1, a 7c -1/-1 then drops it to 0 → dies, CR
# 613.4c / 704.5g). This card-level recovery (the _recover_combat_damage_recipients
# precedent — phase dropped the WHOLE ability, so synthesize from the raw oracle)
# emits the base_pt_set static so the lane reads STRUCTURE, not a regex mirror.
#
# Fires ONLY on a FIXED LITERAL value: the dynamic "change base power to <the
# greatest power among …>" / "base power and toughness X/X" forms (Halfdane, Brine
# Hag, Candlekeep Inspiration) carry no digit after the phrase, so the value regex
# skips them — matching the carved word mirror's fixed-only firing set, so
# base_pt_set stays drift-0. CR 613.4b layer 7b.
# #24e P3 parser-substrate: the base-P/T-SET reads are STRUCTURAL. The VALUE parser
# returns the toughness it sets (int) — or None for a power-only set (amount variable,
# no toughness shrink) — so it doubles as the detector (run is not None) and the
# amount.factor source. Forms, in regex-alternation order: "base power and toughness
# N/M" (toughness = M), "base toughness N" (= N), "base power N" (power-only → None).
_BASE_PT_PAIR_RE = re.compile(r"\d+/\d+")
_BASE_PT_VALUE_P = comb.scan(
    comb.alt(
        comb.seq2(
            comb.phrase({"base"}, {"power"}, {"and"}, {"toughness"}),
            comb.regex_word(_BASE_PT_PAIR_RE),
        ).map(lambda v: int(comb.norm_word(v[1]).split("/")[1])),
        comb.seq2(
            comb.phrase({"base"}, {"toughness"}),
            comb.satisfy(lambda w: w.isdigit()),
        ).map(lambda v: int(comb.norm_word(v[1]))),
        comb.value(
            None,
            comb.seq2(
                comb.phrase({"base"}, {"power"}),
                comb.satisfy(lambda w: w.isdigit()),
            ),
        ),
    )
)
# The SET-EFFECT signature: the value is set by a "have/has/are/is base power…"
# verb. This is the precision gate that keeps a REFERENCE / FILTER out — "creatures
# you control WITH base power and toughness 1/1" (Bess, Zinnia — a tribal count
# condition), "different from ITS base power" (Jason Bright), "with base power OR
# toughness 1" (Sword of the Squeak) all use "with"/"its base", NOT a setting verb,
# so they are not a layer-7b set and must not synthesize one. CR 613.4b vs a mere
# characteristic reference.
_BASE_PT_SET_VERB_P = comb.scan(
    comb.phrase({"have", "has", "are", "is"}, {"base"}, {"power", "toughness"})
)
# The MASS-anthem affected set is a plural "creatures" the clause sets P/T on with
# a "have/has base" verb. A SINGLE-target / aura / equipment / self set ("target
# creature", "enchanted/equipped creature", "this creature") is a neutralize —
# removal, NOT a -1/-1 anthem — so it must NOT be scoped opp/each (the lane
# discriminator wants MASS+low). A "<perms> become … creatures with base …"
# animation (The Antiquities War, Tezzeret — artifacts becoming creatures) is its
# OWN type-animator theme, not a creature anthem, so the "become" verb is excluded
# from the mass arm too.
# The regex anchored `\btarget creature` (no trailing boundary), so "target creatures"
# (a small targeted set — "up to two target creatures each have base …", Will Kenrith,
# Phantasmal Form) read as single/targeted, NOT a go-wide anthem. Mirror that by
# accepting the plural in the noun slot (a true mass anthem says "Creatures you control
# have base …", with no "target"/"enchanted"/"equipped"/"this" qualifier).
_BASE_PT_SINGLE_P = comb.scan(
    comb.alt(
        comb.phrase({"target"}, {"creature", "creatures"}),
        comb.phrase({"enchanted"}, {"creature", "creatures"}),
        comb.phrase({"equipped"}, {"creature", "creatures"}),
        comb.phrase({"this"}, {"creature", "creatures"}),
        comb.phrase({"target"}, {"artifact", "artifacts"}),
        comb.phrase({"enchanted"}, {"artifact", "artifacts"}),
    )
)
_BASE_PT_BECOME_P = comb.scan(
    comb.seq2(
        comb.keyword({"become", "becomes"}),
        comb.bounded_scan(comb.phrase({"base"}, {"power", "toughness"})),
    )
)
# Whose creatures the set affects (read from the value-bearing clause): a PLAIN
# go-wide "creatures you control/own" (controller you — the creatures_matter anthem
# shape the legacy path already fires) vs an opponent set ("your opponents control"
# / an enchanted-player curse / "that player controls" → opp) vs a symmetric
# "all/other/each/non-X creatures" or "creatures target player controls" → each.
# The PLAIN you tell is anchored at the clause START ("[Other/All] creatures you
# control/own …") so a QUALIFIED you set ("Commander creatures you own" — Raised by
# Giants, a narrow commander buff, NOT a go-wide anthem) does NOT read as a generic
# controller-you creatures_matter subject (it falls to the symmetric controller-any
# arm, which fires no lane for a >2 toughness). Head-anchored (not scanned) — the
# regex's `^`.
_BASE_PT_YOU_PLAIN_P = comb.seq2(
    comb.opt(comb.keyword({"other", "all"})),
    comb.phrase({"creatures"}, {"you"}, {"control", "own"}),
)
_BASE_PT_OPP_P = comb.scan(
    comb.alt(
        comb.phrase({"opponent", "opponents"}, {"control"}),
        comb.phrase({"enchanted"}, {"player"}, {"control", "controls"}),
        comb.phrase({"that"}, {"player"}, {"controls"}),
    )
)


def _base_pt_set_fields(clause: str) -> tuple[str, Filter | None, Quantity]:
    """The (scope, subject, amount) of a layer-7b base-P/T set from its raw clause.
    A MASS "creatures … have base …" anthem → a Creature subject (controller you/opp/
    any) + a discriminated scope, so the debuff_makers arm reads the shrink SCOPE
    and the land-animator arms — which key on a LAND subject — stay out; a single-
    target / self / "become" set → subject None + scope "any" (a neutralize is
    removal, not a -1/-1 anthem). The toughness is carried in ``amount.factor`` (the
    death-relevant stat); a power-only set → amount op="variable" (no toughness
    shrink). CR 613.4b. Shared by the per-clause supplement (``_recover_static_
    pattern``) and the card-level empty-IR recovery (``_recover_base_pt_set``)."""
    r = _BASE_PT_VALUE_P.run(clause)
    tough = r[0] if r is not None else None  # int (toughness) or None (power-only)
    amount = (
        Quantity(op="fixed", factor=tough)
        if tough is not None
        else Quantity(op="variable")  # power-only / dynamic — no toughness shrink
    )
    cl = clause.strip()
    is_mass = (
        comb.find_word({"creatures"}).run(cl) is not None
        and _BASE_PT_SINGLE_P.run(cl) is None
        and _BASE_PT_BECOME_P.run(cl) is None
    )
    if not is_mass:
        return "any", None, amount
    if _BASE_PT_OPP_P.run(cl) is not None:
        scope, ctrl = "opp", "opp"
    elif _BASE_PT_YOU_PLAIN_P.run(cl) is not None:
        scope, ctrl = "you", "you"
    else:
        scope, ctrl = "each", "any"
    return scope, Filter(card_types=("Creature",), controller=ctrl), amount


def _recover_base_pt_set(card: Card, oracle: str) -> Card:
    """Append a synthetic ``base_pt_set`` static Effect for the layer-7b set-P/T
    statics phase left wholly unstructured (it drops the whole ability — empty IR).
    Append-only: a face already carrying a base_pt_set Effect is left alone (the
    per-clause supplement or native projection already structured it). One Effect per
    value-bearing clause, fields from ``_base_pt_set_fields``. CR 613.4b."""
    if not card.faces:
        return card
    if any(
        e.category == "base_pt_set" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch — the value + verb both need "base power"/"base toughness".
    if "base power" not in low and "base toughness" not in low:
        return card
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if (
            _BASE_PT_VALUE_P.run(clause) is None
            or _BASE_PT_SET_VERB_P.run(clause) is None
        ):
            continue
        scope, subject, amount = _base_pt_set_fields(clause)
        synth.append(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="base_pt_set",
                        scope=scope,
                        subject=subject,
                        amount=amount,
                        raw=clause.strip(),
                    ),
                ),
            )
        )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 #24m F1 — DYNAMIC / QUOTED base-P/T SET residue (SIDECAR v61) ─────
# The `_recover_base_pt_set` pass above is the DEBUFF path: it fires only on a FIXED
# LITERAL "creatures … have/has/are/is base power N" mass shrink (Maha, Humility) and
# scopes opp/each so debuff_makers reads the SHRINK. It deliberately ignores the
# DYNAMIC / quoted / type-conferral SETTERS — phase routes those to animate / clone /
# reanimate / pump / place_counter / emblem / type_set WITHOUT a base_pt_set Effect, so
# the base_pt_set LANE (CR 613.4b layer 7b) leaned wholly on the carved kept word
# mirror for them. This pass re-synthesizes a base_pt_set Effect for the SETTER residue
# the lane needs (scope "any", subject None, amount variable — a build-around set, NOT a
# mass debuff anthem, so it never feeds debuff_makers):
#   • "<perm> becomes a N/N <Type> creature in addition to its other types" the dynamic
#     forms where phase emitted no base_pt_set Effect (Cool Fluffy Loxodon → type_set,
#     Displaced Dinosaurs → type_set, Mindlink Mech → a clone P/T override "it's 4/3 …
#     in addition to its other types"). CR 205.1b + 613.4b.
#   • "has/have base power [and toughness] …" dynamic or quoted (Trench Gorger "base
#     power and base toughness each equal to the lands exiled", Gigantoplasm '"{X}: This
#     creature has base power and toughness X/X"').
#   • "becomes/is a <Type> with base power and toughness N" (Fractalize "with base power
#     and toughness each equal to X plus 1", Goddric "is a Dragon with base power and
#     toughness 4/4", The Master "a green Mutant with base power and toughness 3/3",
#     Tezzeret the Schemer's emblem "becomes an artifact creature with base power and
#     toughness 5/5").
#   • "base power and toughness of each <perms> become …" (Sita Varma).
# It EXCLUDES the base-power REFERENCE grammar "creatures you control WITH base power N"
# (Bess Soul Nourisher, Zinnia, Duskana, Primo, Rapid Augmenter): those merely REFER to
# base P/T (CR 613.4b sentence 2), set nothing, and await a separate base_power_matters
# decision — they stay on the narrowed base_pt_set kept mirror, NOT synthesized here.
# Append-only and gated to bps==0 so the DEBUFF pass (which runs first) owns the mass
# shrinks. The symmetric MASS-animators (Living Plane "All lands are 1/1 creatures",
# March of the Machines "… with power and toughness equal to its mana value", Mycosynth
# Lattice) say neither "base power" nor "N/N … in addition to its other types", so they
# are not matched. Upstream-to-phase candidate (phase should keep the dropped set as a
# base_pt_set node).
# #24e P3 parser-substrate: the 6 DYNAMIC-setter arms read STRUCTURE. A digit-leading
# word (`_DIGIT_LEAD`: "3", "1/1", "4/4,") stands in for the regex `\d`; `_PT_PAIR_W`
# is the `\b\d+/\d+\b` word. `[^.]*` gaps become `bounded_scan` (clause-bounded). Arm 6
# keys on bare "become" (not "becomes"); arms 4/5 on "become(s) a/an". Ports to phase-rs
# as a nom alt of tuples.
_DIGIT_LEAD = comb.satisfy(lambda w: bool(w) and w[0].isdigit())
_PT_PAIR_W = comb.regex_word(_BASE_PT_PAIR_RE)
_DYN_BASE_PT_SET_P = comb.alt(
    comb.scan(comb.phrase({"has", "have"}, {"base"}, {"power", "toughness"})),
    comb.scan(
        comb.seq3(
            comb.phrase({"base"}, {"power"}),
            comb.opt(comb.phrase({"and"}, {"toughness"})),
            _DIGIT_LEAD,
        )
    ),
    comb.scan(comb.seq2(comb.phrase({"base"}, {"toughness"}), _DIGIT_LEAD)),
    comb.scan(
        comb.seq3(
            comb.keyword({"become", "becomes"}),
            comb.keyword({"a", "an"}),
            comb.bounded_scan(comb.phrase({"with"}, {"base"}, {"power", "toughness"})),
        )
    ),
    comb.scan(
        comb.seq2(
            comb.seq2(comb.keyword({"become", "becomes"}), comb.keyword({"a", "an"})),
            comb.seq2(
                comb.bounded_scan(_PT_PAIR_W),
                comb.bounded_scan(
                    comb.phrase(
                        {"in"}, {"addition"}, {"to"}, {"its"}, {"other"}, {"types"}
                    )
                ),
            ),
        )
    ),
    comb.scan(
        comb.seq2(
            comb.phrase({"base"}, {"power", "toughness"}),
            comb.bounded_scan(comb.keyword({"become"})),
        )
    ),
)
# The REFERENCE grammar: "creature(s) you control WITH base power N" — a noun qualifier,
# not a set. Excluded so the references stay on the narrowed mirror (await
# base_power_matters), not synthesized into the SETTER lane.
_REF_BASE_PT_P = comb.scan(
    comb.phrase(
        {"creature", "creatures"},
        {"you"},
        {"control", "own"},
        {"with"},
        {"base"},
        {"power", "toughness"},
    )
)


def _recover_dynamic_base_pt_set(card: Card, oracle: str) -> Card:
    """Append a synthetic ``base_pt_set`` static Effect for the DYNAMIC / quoted /
    type-conferral base-P/T SETTERS phase folded into a sibling category (animate /
    clone / reanimate / pump / place_counter / emblem / type_set) without a base_pt_set
    node. Append-only and gated to bps==0 (the DEBUFF ``_recover_base_pt_set`` pass owns
    the mass shrinks and runs first). One Effect per non-reference SETTER clause; scope
    "any", subject None, amount variable so it feeds the base_pt_set LANE but never the
    debuff_makers mass-shrink read. CR 613.4b layer 7b."""
    if not card.faces:
        return card
    if any(
        e.category == "base_pt_set" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch — every arm needs "base power"/"base toughness" or the
    # type-conferral tail "in addition to its other types".
    if not (
        "base power" in low
        or "base toughness" in low
        or "in addition to its other types" in low
    ):
        return card
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if _DYN_BASE_PT_SET_P.run(clause) is None:
            continue
        if _REF_BASE_PT_P.run(clause) is not None:
            continue
        synth.append(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="base_pt_set",
                        scope="any",
                        subject=None,
                        amount=Quantity(op="variable"),
                        raw=clause.strip(),
                    ),
                ),
            )
        )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 C10 — DROPPED gain_life residue (SIDECAR v50) ────────────────────
# phase sometimes emits NO gain_life Effect though the raw oracle plainly says YOU
# gain life: a multi-clause / symmetric fold (Game of Chaos "you gain 1 life and
# target opponent loses 1 life" → only coin_flip + lose_life(opp), the gain is
# dropped) or a dynamic "gain life equal to X" the engine didn't model. The gainer
# survives only in the raw, so this card-level pass — the _recover_base_pt_set /
# _recover_combat_damage_recipients precedent (phase dropped the structure, so
# synthesize it from the joined oracle) — emits a gain_life Effect (scope you) so
# the EXISTING gain_life signals arm fires lifegain_matters STRUCTURALLY, retiring
# the deleted regex's gain-act arm from the kept mirror. CR 119.3. Upstream-to-phase
# candidate (phase should keep the dropped gain clause).
#
# Append-only and gated to a YOU gainer: a card already carrying ANY gain_life
# Effect (phase structured at least one gain clause) is untouched — the lane needs
# only one, so a second dropped clause is moot. The patterns are the YOU-anchored
# gain phrasings the deleted ARM-A regex matched ("you gain N/X life", "gain life
# equal to", "you gain that much life"); an opponent/each gainer ("target opponent
# gains 3 life") is NOT synthesized here (that gain_life rides phase's own scope-any
# node + the existing arm, not a forced scope-you marker).
# #24e P2 parser-substrate: DETECTION is a per-clause `_combinators` scan over three
# arms (the deleted YOU-anchored regex):
#   A: you gain <N|X> life   (value slot = satisfy(isdigit-or-x); folds multi-digit)
#   B: gain life equal to
#   C: you gain that much life
# WHOLE-WORD ("life" never matches inside "lifelink"). Ports to phase-rs as
# `alt((tuple((tag("you"), tag("gain"), digit, tag("life"))), ...))`. CR 119.3.
_GAIN_LIFE_VALUE = comb.satisfy(lambda w: w.isdigit() or w == "x")
_GAIN_LIFE_DROPPED = comb.scan(
    comb.alt(
        comb.value(
            None,
            comb.seq3(
                comb.keyword({"you"}),
                comb.keyword({"gain"}),
                comb.seq2(_GAIN_LIFE_VALUE, comb.keyword({"life"})),
            ),
        ),
        comb.value(None, comb.phrase({"gain"}, {"life"}, {"equal"}, {"to"})),
        comb.value(None, comb.phrase({"you"}, {"gain"}, {"that"}, {"much"}, {"life"})),
    )
)


def _recover_dropped_gain_life(card: Card, oracle: str) -> Card:
    """Append a synthetic ``gain_life`` Effect (scope you) for the gain-life clauses
    phase dropped (no gain_life node though the raw says you gain life). Append-only:
    a card already carrying a gain_life Effect is left alone. One Effect per
    value-bearing clause. CR 119.3."""
    if not card.faces:
        return card
    # Skip only when a gain_life the signals arm WOULD read (scope you/any) already
    # exists — NOT a gain_life phase mis-scoped to 'opp'. phase's third-party
    # possessive heuristic flips "You gain life equal to the cards in target
    # opponent's hand" (Gerrard Capashen, Search Warrant, Daxos, Froghemoth) to
    # scope='opp' because the COUNT references an opponent, though the GAINER is you.
    # Those never fire the you/any arm, so the synth must still run. CR 119.3.
    if any(
        e.category == "gain_life" and e.scope in ("you", "any")
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    synth: list[Ability] = []
    for clause in re.split(r"[.\n]", text):
        if _anchored(clause, "gain", _GAIN_LIFE_DROPPED):
            synth.append(
                Ability(
                    kind="static",
                    effects=(
                        Effect(
                            category="gain_life",
                            scope="you",
                            raw=clause.strip(),
                        ),
                    ),
                )
            )
    if not synth:
        return card
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, *synth)), *rest),
    )


# ── ADR-0027 #24 — GRANTED damage-reflection residue (SIDECAR v52) ─────────────
# phase has no first-class node for a damage-REFLECTION ability granted to (or
# quoted onto) a CLASS of creatures: 'Sliver creatures you control have "Whenever
# this creature is dealt damage, it deals that much damage to target player or
# planeswalker."' (Spiteful Sliver) parses to a `board_grant` carrying the whole
# quoted reflection in its raw, plus a split-off `damage` static — NOT a
# damage_reflect Effect. The damage_reflect signals arm reads a `damage_reflect`
# CATEGORY marker (the conferred-keyword read) and an on-card damage_received
# trigger; neither fires for the GRANTED form (board_grant is not a grant carrier
# and there is no card-level trigger), so the lane saw nothing — the previously
# dead `cat=='damage_reflect'` IR read becomes load-bearing here. This card-level
# pass — the _recover_base_pt_set / _recover_combat_damage_recipients precedent
# (phase dropped the structure, so synthesize it from the joined oracle) — emits a
# damage_reflect Effect so the lane reads STRUCTURE. CR 120.3 / 119.3.
#
# Anchored TIGHTLY on the reflection signature (the same two anchors the project-
# side _narrow_conferred_keyword_refs grant-carrier marker uses): a "whenever ~ is
# dealt damage" TRIGGER + a "deals that much damage" CONSEQUENCE (the reflection
# mirrors the received amount — not "deals N damage to it", a source dealing its
# own damage). Both required so a mere "if dealt damage this way" side-effect
# (Marauding Raptor) never fires.
#
# Append-only and gated to the GRANTED form: skip a card already carrying a
# damage_reflect Effect, and skip an ON-CARD reflector (a damage_received trigger
# with a damage effect — Boros Reckoner, Stuffy Doll), which the signals arm reads
# off the trigger. The granted/quoted reflectors phase leaves wholly unstructured
# (Spiteful Sliver's tribal grant, Arcbond's targeted grant, Donna Noble's
# paired-subject trigger phase couldn't model) carry neither, so they recover here.
# #24e P2 parser-substrate: both required anchors are `_combinators`:
#   TRIG: "whenever … is dealt damage" — the bounded `[^.""]*?` gap is honored by
#         splitting the text on period / quote chars and running, per segment,
#         `preceded(find_word({"whenever"}), scan(phrase("is","dealt","damage")))`
#         (whenever BEFORE is-dealt-damage, within one no-period-no-quote run).
#   DEALS: `scan(phrase("deals","that","much","damage"))` over the whole text.
# WHOLE-WORD throughout. Ports to phase-rs as a nom `tuple` inside a sentence-bounded
# `take_until('.')`. CR 120.3.
_DAMAGE_REFLECT_TRIG = comb.preceded(
    comb.find_word({"whenever"}),
    comb.scan(comb.phrase({"is"}, {"dealt"}, {"damage"})),
)
_DAMAGE_REFLECT_DEALS = comb.scan(
    comb.phrase({"deals"}, {"that"}, {"much"}, {"damage"})
)


def _has_damage_reflect_grant(text: str) -> bool:
    """The GRANTED damage-reflection tell: a "whenever … is dealt damage" trigger (in a
    no-period-no-quote run) AND a "deals that much damage" consequence somewhere in the
    text. Mirrors the two deleted regexes; the trigger's sentence/quote bound is the
    per-segment split."""
    if "dealt damage" not in text.lower() or "that much damage" not in text.lower():
        return False
    segments = re.split(r"[.\"“”]", text)
    if not any(_DAMAGE_REFLECT_TRIG.run(seg) is not None for seg in segments):
        return False
    return _DAMAGE_REFLECT_DEALS.run(text) is not None


def _recover_damage_reflect(card: Card, oracle: str) -> Card:
    """Append a synthetic ``damage_reflect`` static Effect for the GRANTED/quoted
    damage-reflection abilities phase leaves wholly unstructured (a `board_grant`
    raw, a targeted grant, or a compound-subject trigger phase couldn't model).
    Append-only: a card already carrying a damage_reflect Effect, or an on-card
    reflector (a damage_received trigger + a damage effect the signals arm reads
    directly), is left alone. CR 120.3."""
    if not card.faces:
        return card
    if any(
        e.category == "damage_reflect"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    if any(
        ab.trigger is not None
        and ab.trigger.event == "damage_received"
        and any(e.category == "damage" for e in ab.effects)
        for ab in card.all_abilities()
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if not _has_damage_reflect_grant(text):
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="damage_reflect", scope="you", raw=text.strip()),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24 — OPPONENT cast-lock restriction residue (SIDECAR v52) ────────
# phase drops the "your opponents can't cast spells [during your turn/combat]"
# player-restriction static WHOLLY for a body that has no other modelled ability
# (Dragonlord Dromoka parses to ZERO abilities; Tidal Barracuda, Voice of Victory,
# Kutzil, Marisi, Myrel, Conqueror's Flail, Narset Transcendent's emblem all drop
# it too). The migrated stax arm reads a `restriction` Effect scope='opp' →
# stax_taxes (CR 601.3: an effect prohibits opponents from casting — a hard lock,
# CR 604.1 static). With no Effect the arm saw nothing, so the lane fired only off
# the broad `\bopponents? can't\b` residue byte-mirror. This card-level pass — the
# _recover_base_pt_set precedent (phase dropped the WHOLE ability, so synthesize it
# from the joined oracle) — emits the restriction Effect so the stax arm reads
# STRUCTURE, and the residue mirror's opponent-cast branch is narrowed to defer to
# it (see _STAX_TAXES_RESIDUE_RE's `(?! cast)` guard). CR 601.3 / 604.1.
#
# Scope is unambiguously 'opp' (the OPPONENTS form only — "your/each opponent(s)
# can't cast"). The SYMMETRIC "players can't cast" locks (Grafdigger's Cage,
# Basandra) and the messier "that/defending player can't cast" forms are left to
# the residue mirror: their scope is 'each' (symmetric_stax) or situational, and
# folding them here would risk the symmetric/opp split. Append-only and gated to a
# body phase left WITHOUT any restriction Effect (the 21 cleanly-structured
# opponent cast-locks — Grand Abolisher, Drannith Magistrate, Azor — already fire
# the structural arm and are untouched).
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan
# (``scan(phrase({"opponent","opponents"}, {"cant"}, {"cast"}))``) — the three
# consecutive words "opponent(s) can't cast" ("can't" normalizes to "cant"). Behavior-
# neutral with the deleted `\bopponents? can't cast\b` mirror; ports to phase-rs as a
# nom `tuple((alt((tag("opponents"), tag("opponent"))), tag("can't"), tag("cast")))`.
_OPP_CAST_LOCK = comb.scan(comb.phrase({"opponent", "opponents"}, {"cant"}, {"cast"}))


def _recover_opponent_cast_lock(card: Card, oracle: str) -> Card:
    """Append a synthetic ``restriction`` static Effect (scope opp) for the
    "your opponents can't cast spells" player-lock phase drops wholly. Append-only
    and gated: a card already carrying ANY restriction Effect (phase structured the
    lock, or a sibling restriction) is left alone. One Effect for the card. CR
    601.3 / 604.1."""
    if not card.faces:
        return card
    if any(
        e.category == "restriction" for ab in card.all_abilities() for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    clause = next(
        (
            cl.strip()
            for cl in re.split(r"[.\n]", text)
            if _anchored(cl, "can't cast", _OPP_CAST_LOCK)
        ),
        None,
    )
    if clause is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="restriction", scope="opp", raw=clause),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24c — becomes-(un)tapped trigger residue (SIDECAR v53) ───────────
# phase emits a structured `Untaps` mode for the becomes-untapped (Inspired) trigger
# — project._trigger_event NOW maps it to event=='untaps' — but it also leaves a
# fistful of becomes-(un)tapped triggers on an UNKNOWN mode (the subject phase
# couldn't parse: Darksteel Garrison's "fortified land becomes tapped", Grand Marshal
# Macie's "becomes untapped", Roots of Life's "a land … an opponent controls becomes
# tapped"), and those project to event=='other'. The tap_untap_matters lane fires on
# trig.event in {taps, untaps}; this card-level pass recovers the dropped event for
# the Unknown-mode tail by reading the trigger clause's OWN raw — "becomes untapped" →
# `untaps`, "becomes tapped" → `taps` (folding into the same `taps` event the Taps
# mode already uses). Idempotent: only event=='other' triggers are touched, so the
# `Untaps`/`Taps`-mode cards project._trigger_event already typed are untouched. The
# trigger SUBJECT is None on this tail (phase's Unknown), so no typed-subject lane
# (line ~10112 `_typed_matters_lanes`) is disturbed. CR 701.20a / 702.108.
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan over the
# trigger effect raw — ``scan(phrase({"become","becomes"}, {"untapped"}))`` /
# ``... {"tapped"}``. "becomes untapped" never matches the "tapped" phrase ("untapped"
# is a distinct normalized word), so the untapped-first ordering is preserved exactly.
# Behavior-neutral with the deleted `becomes? (un)tapped` mirrors; ports to phase-rs as
# a nom `tuple((alt((tag("becomes"), tag("become"))), tag("untapped")))`.
_BECOMES_UNTAPPED = comb.scan(comb.phrase({"become", "becomes"}, {"untapped"}))
_BECOMES_TAPPED = comb.scan(comb.phrase({"become", "becomes"}, {"tapped"}))


def _recover_becomes_tap_untap(card: Card) -> Card:
    """Re-type an event=='other' triggered ability whose effect raw is a
    "becomes (un)tapped" trigger clause to the structured `untaps` / `taps` event,
    so tap_untap_matters reads STRUCTURE for the Unknown-mode tap/untap tail phase
    couldn't mode-classify. Append-free (rewrites the trigger event in place)."""
    if not card.faces:
        return card
    new_faces = []
    changed = False
    for face in card.faces:
        new_abs = []
        for ab in face.abilities:
            tr = ab.trigger
            new_ab = ab
            if tr is not None and tr.event == "other":
                raw = " ".join(e.raw or "" for e in ab.effects)
                clean = re.sub(r"\([^)]*\)", " ", raw)
                # "tapped" is a necessary substring of both phrases ("untapped"
                # contains it), so it is the cheap dispatch gate for the scans.
                if "tapped" not in clean.lower():
                    new_abs.append(new_ab)
                    continue
                if _BECOMES_UNTAPPED.run(clean) is not None:
                    new_ab = replace(ab, trigger=replace(tr, event="untaps"))
                    changed = True
                elif _BECOMES_TAPPED.run(clean) is not None:
                    new_ab = replace(ab, trigger=replace(tr, event="taps"))
                    changed = True
            new_abs.append(new_ab)
        new_faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(new_faces)) if changed else card


# ── ADR-0027 #24c — SELF dies-return residue (SIDECAR v53) ─────────────────────
# The aristocrats/reanimator CORE mechanic "When this dies, return it to the
# battlefield" — phase flattens the granted/quoted form to a place_counter / pump
# effect (Feign Death → place_counter(p1p1); Abnormal Endurance → pump) and DROPS the
# reanimate, and the body-borne form (Bronzehide Lion, Ashcloud Phoenix) parses as a
# dies-trigger + reanimate that would over-broaden if read directly (a dies-triggered
# reanimate of OTHERS is NOT self-recursion). The undying/persist keyword BEARERS ride
# _IR_KEYWORD_MAP and the keyword-LESS GRANTERS ride the `undying_persist` marker; this
# pass covers the third class — the literal self dies-return clause — by synthesizing a
# dedicated `self_recursion` marker Effect ONLY dies_recursion reads (zero collateral
# into death_matters / graveyard_matters / reanimate lanes). The patterns mirror the
# deleted DIES_RECURSION_REGEX's two non-keyword arms EXACTLY (self-return + the
# would-die-instead-exile-with-counters delayed return — Darigaaz Reincarnated), run
# over the joined oracle, so the recovered set is byte-identical sans the keyword arm
# (now structural). CR 700.4 (dies = battlefield→graveyard) / 603.6c.
# #24e P3 parser-substrate: the two non-keyword DIES_RECURSION arms read STRUCTURE.
# Arm A — "when ~ dies, return it to the battlefield": `when` anchor, a bounded-gap
# scan over the creature description (no period crossed), then the fixed return phrase
# (the pronoun bag covers it/her/him/them). `keyword({when})` matches ONLY "when", not
# "whenever" (norm keeps them distinct), mirroring the regex's `when ` space-anchor.
# Arm B — "if ~ would die, instead exile it with N counters" (Darigaaz Reincarnated's
# delayed return): `if` anchor, bounded-gap to the fixed "would die instead exile it
# with" phrase, then a second bounded gap to the `counter(s)` word. Both `[^.]*` gaps
# become `bounded_scan` (clause-bounded). Ports to phase-rs as two nom tuples.
_DIES_RETURN_ARM_A = comb.seq2(
    comb.keyword({"when"}),
    comb.bounded_scan(
        comb.phrase(
            {"dies"},
            {"return"},
            {"it", "her", "him", "them"},
            {"to"},
            {"the"},
            {"battlefield"},
        )
    ),
)
_DIES_RETURN_ARM_B = comb.seq2(
    comb.keyword({"if"}),
    comb.bounded_scan(
        comb.seq2(
            comb.phrase({"would"}, {"die"}, {"instead"}, {"exile"}, {"it"}, {"with"}),
            comb.bounded_scan(comb.keyword({"counter", "counters"})),
        )
    ),
)


# ── v0.8.0 bump regression-recovery ROOT A (SIDECAR 66, no bump) ──────────────
# phase v0.8.0 collapses a "Whenever <event>, ... (return|exile) THIS card from your
# graveyard ..." TRIGGERED graveyard-recursion ability (the Recover template, CR
# 702.59a) into a CONTENTLESS spell-kind ability — it strips BOTH the trigger AND the
# in:graveyard zone, emitting a bare `bounce` Effect (raw="", zones=()). Two losses:
# (1) the lane that EXCLUDES graveyard-recursion bounces (bounce_tempo guards on
# `not any("graveyard" in z)`) now LEAKS these as if they were battlefield→hand tempo
# bounces — A Good Day to Pie, Punishing Fire, Unlawful Entry, Spit Flame, Sosuke's
# Summons, Killian's Confidence, Vivi's Persistence, Reach of Branches, Unconventional
# Tactics are all "return this card from YOUR GRAVEYARD" (CR 400.7 graveyard→hand zone
# change), NOT a tempo bounce of an opponent's permanent; (2) the tribal-ETB recursion
# trigger ("Whenever a <subtype> you control enters" — Snake/Dragon/Zombie) and the
# scry-recursion trigger ("Whenever you scry" — Council's Deliberation) vanish, so
# tribal_etb_multi / scry_surveil_matters drop a real member. This card-level pass
# re-bridges the structure v0.8.0 drops — the proven #24 supplement precedent
# (_recover_dies_return / _recover_combat_damage_recipients): it stamps in:graveyard
# back onto the contentless recursion bounce (re-arming the bounce_tempo graveyard
# guard → the 9 over-fires drop) and, when the recursion's "Whenever" condition is a
# creature-subtype ETB or a scry, rebuilds that Trigger onto the ability so the tribal/
# scry payoff lanes read STRUCTURE again. Decoy Gambit ("return that creature to its
# owner's hand", a battlefield→hand opponent-creature tempo bounce) carries a NON-empty
# bounce raw and NO graveyard mention, so it is untouched and correctly stays in
# bounce_tempo. CR 702.59a / 400.7 / 603.
_GY_RECUR_MARK = re.compile(
    r"\b(?:return|exile) this card from your graveyard\b", re.IGNORECASE
)
_GY_RECUR_WHENEVER = re.compile(r"\bwhenever\b", re.IGNORECASE)
# "a [nontoken] <Subtype> you control enters [the battlefield]" — the tribal-ETB head.
_GY_RECUR_TRIBAL_ETB = re.compile(
    r"\b(?:a|an|another) (?:nontoken )?([A-Za-z]+) you control enters\b",
    re.IGNORECASE,
)
_GY_RECUR_SCRY = re.compile(r"\byou scry\b", re.IGNORECASE)


def _gy_recursion_trigger(oracle: str) -> Trigger | None:
    """Reconstruct the Trigger v0.8.0 dropped from a graveyard-recursion ability, or
    None when the "Whenever" condition is neither a creature-subtype ETB nor a scry
    (a sticker / opp-lifegain / commander-ETB / combat-damage condition needs no
    rebuilt trigger — the in:graveyard zone stamp alone excludes its bounce)."""
    mark = _GY_RECUR_MARK.search(oracle)
    if mark is None:
        return None
    head = oracle[: mark.start()]
    whenevers = list(_GY_RECUR_WHENEVER.finditer(head))
    if not whenevers:
        return None
    cond = oracle[whenevers[-1].end() : mark.start()].split(",", 1)[0]
    etb = _GY_RECUR_TRIBAL_ETB.search(cond)
    if etb is not None:
        sub = etb.group(1).capitalize()
        return Trigger(
            event="etb",
            subject=Filter(subtypes=(sub,), controller="you"),
            scope="you",
        )
    if _GY_RECUR_SCRY.search(cond):
        return Trigger(event="scried", scope="you")
    return None


def _is_gy_recursion_bounce(e: Effect) -> bool:
    """A CONTENTLESS bounce v0.8.0 left from a collapsed GY-recursion trigger — empty
    raw / zones / counter_kind / subject. The empty raw is the discriminator vs a real
    tempo bounce (which carries its clause), so a card with BOTH a real bounce and a
    Recover clause keeps the real bounce in bounce_tempo."""
    return (
        e.category == "bounce"
        and not e.raw
        and not e.zones
        and not e.counter_kind
        and e.subject is None
    )


def _is_gy_recursion_exile(e: Effect) -> bool:
    """The exile-from-graveyard form of a collapsed GY-recursion trigger (Council's
    Deliberation "exile this card from your graveyard. If you do, draw a card"). phase
    keeps the from:graveyard zone but DROPS the trigger; the empty raw marks it as the
    collapsed-trigger half (vs a real exile-removal clause, which carries its raw)."""
    return e.category == "exile" and not e.raw and "from:graveyard" in e.zones


def _is_gy_recursion_ability(ab: Ability) -> bool:
    """An ability holding a collapsed GY-recursion effect — either the contentless
    bounce or the exile-from-graveyard form. NOT gated on kind/trigger: the
    createdelayedtrigger trigger-lift (project._lift_delayed_trigger) now projects the
    etb/lifegain recursion ability as kind='triggered', but the contentless SelfRef
    Bounce still carries no origin zone (node-absent), so this pass must still stamp
    in:graveyard onto it regardless of whether the trigger was lifted natively. The
    card-level _GY_RECUR_MARK oracle gate in _recover_gy_recursion already restricts
    this to genuine 'return/exile this card from your graveyard' cards."""
    return any(
        _is_gy_recursion_bounce(e) or _is_gy_recursion_exile(e) for e in ab.effects
    )


def _recover_gy_recursion(card: Card, oracle: str) -> Card:
    """Re-bridge the v0.8.0 GY-recursion regression (ROOT A): stamp in:graveyard onto
    the contentless recursion bounce (so bounce_tempo's graveyard guard excludes it)
    and rebuild the dropped creature-subtype-ETB / scry Trigger so tribal_etb_multi /
    scry_surveil_matters fire. Gated to cards whose oracle carries the literal
    "(return|exile) this card from your graveyard"; idempotent (a contentless recursion
    bounce already carrying a graveyard zone is left alone). CR 702.59a / 400.7."""
    if not card.faces or not _GY_RECUR_MARK.search(oracle):
        return card
    trig = _gy_recursion_trigger(oracle)
    changed = False
    attached = False
    new_faces: list[Face] = []
    for face in card.faces:
        new_abilities: list[Ability] = []
        for ab in face.abilities:
            if not _is_gy_recursion_ability(ab):
                new_abilities.append(ab)
                continue
            changed = True
            effects = tuple(
                replace(e, zones=("in:graveyard",)) if _is_gy_recursion_bounce(e) else e
                for e in ab.effects
            )
            # rebuild the dropped trigger onto the FIRST recursion ability only
            # (each target card has exactly one recursion clause). Skip when the
            # ability already carries a trigger — project._lift_delayed_trigger now
            # projects the etb/lifegain recursion trigger natively, so the recovery
            # only backstops the still-node-absent in:graveyard zone stamp (else
            # branch) and the regex-only scry trigger (mode:Unknown, ab.trigger None).
            if trig is not None and not attached and ab.trigger is None:
                new_abilities.append(
                    replace(ab, kind="triggered", trigger=trig, effects=effects)
                )
                attached = True
            else:
                new_abilities.append(replace(ab, effects=effects))
        new_faces.append(replace(face, abilities=tuple(new_abilities)))
    if not changed:
        return card
    return replace(card, faces=tuple(new_faces))


def _recover_dies_return(card: Card, oracle: str) -> Card:
    """Append a synthetic `self_recursion` static marker Effect when the joined
    oracle carries the literal self dies-return (or would-die-instead-exile-with-
    counters) clause, so dies_recursion reads STRUCTURE. Append-only and idempotent
    (skip a card already carrying the marker)."""
    if not card.faces:
        return card
    if any(
        e.category == "self_recursion"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    span: str | None = None
    # cheap necessary-substring dispatch per arm (the combinator stays the detector).
    if "battlefield" in low:
        span = _scan_span(text, _DIES_RETURN_ARM_A)
    if span is None and "exile it with" in low:
        span = _scan_span(text, _DIES_RETURN_ARM_B)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="self_recursion", scope="you", raw=span),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24c — +1/+1 / -1/-1 counter REMOVAL-as-cost residue (SIDECAR v53) ─
# counter_manipulation reads a counter_move / remove_counter Effect of kind p1p1/m1m1
# (the structured MOVE + remove-as-effect halves). The remaining mirror tail is the
# counter REMOVAL phase leaves OUTSIDE an effect: as an activation COST (phase emits
# the `removecounter` cost token but DROPS the counter kind — Triskelion, Walking
# Ballista, Quillspike, Spike Weaver) and as a damage-prevention REPLACEMENT (Phantom
# Centaur / Flock / Nantuko, Oathsworn Knight — "prevent that damage … remove a +1/+1
# counter"). phase keeps neither as a remove_counter Effect, so the kind survives only
# in raw. This pass recovers the dropped KIND (the audit's named upstream gap) by
# synthesizing a remove_counter Effect with counter_kind=p1p1/m1m1 from the raw
# removal clause — the existing counter_manipulation arm then reads STRUCTURE. Gated to
# skip a card already carrying a p1p1/m1m1 counter_move/remove_counter (the structured
# MOVE/effect cards are untouched); the kind gate keeps a charge/oil/loyalty cost-side
# removal (Coretapper, Surge Node) OUT. CR 122.1 / 122.6.
# #24e P3 parser-substrate: the +1/+1-vs--1/-1 counter-removal detector reads STRUCTURE
# with the new SIGN-PRESERVING `signed_word` (`norm_word` folds both to "1/1", losing
# the kind the lane needs). Shape mirrors `(?:remove|move) <qty> [gap] (+1/+1|-1/-1)
# counter(s)`: verb anchor + a quantity (a|one|x|N|"any number of") + a bounded gap to
# the signed token + the `counter(s)` word. The value threaded out is the signed form,
# mapped p1p1/m1m1 by the caller. Ports to phase-rs as a nom tuple with a sign-tag.
_COUNTER_REMOVE_QTY = comb.alt(
    comb.phrase({"any"}, {"number"}, {"of"}),
    comb.satisfy(lambda w: w in {"a", "one", "x"} or w.isdigit()),
)
# The gap is bounded by ``:`` too (not just sentence delims): a ``Remove a charge
# counter from ~: Put a -1/-1 counter`` activation removes a charge/quest counter as a
# COST and puts the signed counter in the EFFECT — the signed token after the colon is
# a different clause and must not be read as the removed kind (Trigon of Corruption,
# Quest for the Gemblades, The Duke). The regex's 20-char cap blocked these by accident;
# the colon is the STRUCTURAL boundary (cost ``:`` effect, CR 602.1).
_COUNTER_REMOVE_P = comb.seq2(
    comb.seq2(comb.keyword({"remove", "move"}), _COUNTER_REMOVE_QTY),
    comb.bounded_scan(
        comb.seq2(
            comb.signed_word({"+1/+1", "-1/-1"}),
            comb.keyword({"counter", "counters"}),
        ),
        delims='.;:"“”',
    ),
).map(lambda v: v[1][0])


def _recover_counter_removal(card: Card, oracle: str) -> Card:
    """Append a synthetic remove_counter Effect (counter_kind p1p1/m1m1) for a
    +1/+1 or -1/-1 counter removal phase left as an activation cost / damage-
    prevention replacement (kind dropped). Append-only; skip a card already carrying
    a p1p1/m1m1 counter_move/remove_counter (structured) Effect. CR 122.1."""
    if not card.faces:
        return card
    if any(
        e.category in ("counter_move", "remove_counter")
        and e.counter_kind in ("p1p1", "m1m1")
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    low = text.lower()
    # cheap dispatch: a removal verb AND a signed counter token must both be present.
    if ("remove" not in low and "move" not in low) or (
        "+1/+1" not in text and "-1/-1" not in text
    ):
        return card
    rest = text
    sign: str | None = None
    span = ""
    while True:
        r = _COUNTER_REMOVE_P.run(rest)
        if r is not None:
            sign = r[0]
            span = rest[: len(rest) - len(r[1])].strip()
            break
        w = comb.word().run(rest)
        if w is None:
            break
        rest = w[1]
    if sign is None:
        return card
    kind = "p1p1" if sign == "+1/+1" else "m1m1"
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="remove_counter",
                scope="you",
                counter_kind=kind,
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


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

    # 3. ADR-0027 topdeck library-owner scope (SIDECAR v28): split a recovered
    # topdeck_select by whose library/hand it examines (own-selection 'you',
    # opponent peek 'opp', Morph face-down reveal → re-categorized out). Runs AFTER
    # the broad-third-party guess so the owner rule has the final word for this
    # category (it adds the "target player's library" peeks _BROAD_THIRD_PARTY omits).
    if out.category == "topdeck_select":
        out = _topdeck_select_owner_scope(out)

    # 4. ADR-0027 clone copied-type subject (SIDECAR v30): the _CLONE_STATIC / _BECOMES
    # re-tags above turn an `other` "enter/is a copy of <type>" clause into category
    # "clone" but leave subject=None — the project-side _recover_clone_subjects already
    # ran (pre-supplement) and never saw this newly-recovered clone effect, so
    # _clone_copy_lanes(None) drops the copied type (~49 creature-copies — Clone, Body
    # Double, Phyrexian Metamorph). Re-derive the copied permanent type from the clone
    # clause's own "copy of <type>" text (the same _COPY_TYPE_WORDS read the
    # project-side recovery uses). Append-only — a clone effect that already carries a
    # structured subject (a phase-parsed BecomeCopy that reached
    # _recover_clone_subjects) is untouched. None stays None for a typeless referent
    # ("copy of that card / ~", Essence of the Wild, Valki) — those have no in-clause
    # type and no sibling here. CR 707.2 (a copy takes the copiable values, incl. card
    # type).
    if out.category == "clone" and out.subject is None:
        out = replace(out, subject=_copied_type_from_text(out.raw))

    # 5. ADR-0027 exile_removal retention (SIDECAR v31): retain cat="exile" + a
    # permanent-type subject on a genuine single-target exile REMOVAL phase swallowed
    # into a rider clause (restriction/lifegain) or left subjectless, so the migrated
    # exile_removal structural arm can read it. Runs after the scope passes so a
    # recovered exile keeps any opp/each scope it already had (Unexplained Absence).
    out = _recover_exile_removal(out)

    # 6. ADR-0027 exile_removal PROJECTION TAIL (SIDECAR v46, C13): repair two phase
    # mis-parses the C13 structural arm would otherwise admit — Savior of Ollenbock's
    # graveyard-only mis-zoning (ADD in:battlefield from the battlefield-exile
    # alternative) and Kaya, Spirits' Justice's split-off bare opponent-exile (FILL an
    # opponent-controlled subject). Both run after _recover_exile_removal so they see
    # the post-retention shape; both are append-only / idempotent.
    out = _recover_hybrid_exile_zone(out)
    return _recover_opponent_exile_subject(out)


# ── ADR-0027 #24b SUPPLEMENT_RECOVER batch B1 (SIDECAR v54) ───────────────────
# Five lanes phase PARSES but whose zone / count / devotion operand it DROPS, today
# carried by a signals-side regex mirror. Each recovery below RECOVERS the dropped
# structure from the joined oracle (the recovery seam) onto the IR — the
# ``_recover_base_pt_set`` / ``_recover_combat_damage_recipients`` precedent (phase
# dropped the structure, synthesize it) — so the migrated lane reads STRUCTURE and
# the mirror is deleted. Where phase DID leave usable partial structure (a
# leaves/dies Land-subject trigger, an ``in:exile`` count operand, a
# ``cast_from_zone`` Effect), the signals arm reads it directly and the supplement
# only fills the residue; where phase scattered the operand across many effect
# categories (lands_matter's land count, devotion's collapsed ``op``) the
# supplement appends ONE inert marker carrying the recovered operand rather than
# mutating the overloaded ``amount`` of each (which cascades into pump_makers /
# ramp that read ``amount.op``). All append-only / idempotent.

# lands_matter — DEFERRED (mirror kept): phase's card-data.json omits the AFTERMATH
# back face entirely (Road // Ruin projects only "Road"; "Ruin deals damage … equal
# to the number of lands you control" is absent from the IR), so a supplement that
# reads the records oracle cannot recover that real member — deleting the mirror
# would silently drop it. The count operand also scatters across 12+ effect
# categories (characteristic_pt P/T scalers, pump_target, make_token, tutor,
# place_counter, cost_reduction) and a few cost/restriction bodies with no effect
# raw, so a clean structural read awaits a phase aftermath-face fix. CR 305.

# devotion_matters — phase preserves Quantity.op=='devotion' on SOME effects (Gray
# Merchant, the Theros gods) but COLLAPSES it to op=='variable' on a devotion-scaled
# ramp (Nyx Lotus, Karametra's Acolyte, Nykthos) and DROPS it on a devotion pump /
# characteristic_pt (Aspect of Hydra, Daxos). Re-stamping the op in place would
# cascade (ramp reads op=='variable' for its accel split, pump_makers reads
# op=='fixed'); instead append ONE inert devotion marker so the devotion_matters arm
# reads op=='devotion' without disturbing those neighbors. Gated to a card not
# already carrying a devotion operand. CR 700 (devotion).
#
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan
# (``scan(seq3(keyword({"devotion"}), keyword({"to"}), word()))``) — "devotion to
# <color>" read as three consecutive words, the trailing ``word()`` enforcing the
# `\w`-after-"to" the regex required. Behavior-neutral with the deleted `devotion to
# \w` mirror; ports to phase-rs as a nom `tuple((tag("devotion"), tag("to"), word))`.
_DEVOTION_TO_COLOR = comb.scan(
    comb.seq3(comb.keyword({"devotion"}), comb.keyword({"to"}), comb.word())
)


def _recover_devotion_operand(card: Card, oracle: str) -> Card:
    """Append a synthetic devotion marker (op='devotion') for the devotion operand
    phase collapses to op='variable' (ramp) or drops (pump / characteristic_pt), so
    the devotion_matters arm reads it structurally without re-stamping the overloaded
    ``amount.op`` of the real ramp/pump effect (which ramp / pump_makers
    read). Append-only; skipped when an op=='devotion' operand already exists."""
    if not card.faces:
        return card
    if any(
        e.amount is not None and e.amount.op == "devotion"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    m = _DEVOTION_TO_COLOR.run(text) if "devotion to" in text.lower() else None
    if m is None:
        return card
    raw = " ".join(m[0])  # the matched "devotion to <color>" words (inert marker raw)
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", amount=Quantity(op="devotion"), raw=raw),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# cast_from_exile — phase HAS the structure but DROPS the exile zone: a self-cast
# permanent projects ``cast_from_zone`` zones=() (Eternal Scourge, Misthollow), a
# cast-from-exile payoff projects an effect on a ``cast_spell`` Trigger zones=()
# (Vega's "from anywhere other than your hand"), and Squee keeps from:graveyard but
# drops the "or from exile". Stamp ``from:exile`` onto the real ``cast_from_zone``
# Effect and the ``cast_spell`` Trigger so the lane reads the zone STRUCTURALLY;
# synthesize a marker only for the exile-and-cast / impulse engines phase leaves with
# neither carrier. CR 601.3b / 702.143.
# #24e P3 parser-substrate: the cast-from-exile detector reads STRUCTURE — six arms,
# `[^.]*?` gaps → `bounded_scan`, anchored phrases. The "play a land or cast a spell"
# regex option is subsumed by "play a land". Detection-only (boolean).
_CFE_FROM_EXILE = comb.phrase({"from"}, {"exile"})
_CFE_CAST_PLAY = comb.alt(
    comb.phrase({"cast"}, {"a"}, {"spell"}),
    comb.phrase({"play"}, {"a"}, {"card", "land"}),
)
_CAST_FROM_EXILE_P = comb.scan(
    comb.alt(
        comb.phrase(
            {"top"}, {"card"}, {"of"}, {"your"}, {"library"}, {"has"}, {"plot"}
        ),
        comb.seq(
            comb.alt(comb.keyword({"whenever"}), comb.phrase({"each"}, {"time"})),
            comb.keyword({"you"}),
            _CFE_CAST_PLAY,
            comb.bounded_scan(_CFE_FROM_EXILE),
        ),
        comb.phrase({"spell", "spells"}, {"you"}, {"cast"}, {"from"}, {"exile"}),
        comb.seq(
            comb.phrase({"you"}, {"may"}, {"play", "cast"}),
            comb.alt(
                comb.keyword({"it", "them"}),
                comb.phrase({"that"}, {"card"}),
                comb.phrase({"this"}, {"card"}),
                comb.phrase({"those"}, {"card", "cards"}),
            ),
            comb.bounded_scan(
                comb.alt(
                    comb.phrase(
                        {"for"},
                        {"as"},
                        {"long"},
                        {"as"},
                        {"it"},
                        {"remains"},
                        {"exiled"},
                    ),
                    _CFE_FROM_EXILE,
                )
            ),
        ),
        comb.seq(
            comb.phrase({"you"}, {"may"}, {"play"}),
            comb.opt(comb.keyword({"a", "that"})),
            # the regex `card` had no trailing boundary — "play cards … from exile"
            # (Tinybones, Bauble Burglar) matched via the plural prefix.
            comb.keyword({"card", "cards"}),
            comb.bounded_scan(_CFE_FROM_EXILE),
        ),
        comb.seq(
            comb.alt(
                comb.phrase({"cast"}, {"a"}, {"spell"}),
                comb.phrase({"play"}, {"a"}, {"land"}),
                comb.phrase({"play"}, {"a"}, {"card"}),
            ),
            comb.bounded_scan(
                comb.phrase(
                    {"from"}, {"anywhere"}, {"other"}, {"than"}, {"your"}, {"hand"}
                )
            ),
        ),
    )
)


def _recover_cast_from_exile_zone(card: Card, oracle: str) -> Card:
    """Stamp ``from:exile`` onto the ``cast_from_zone`` Effect and ``cast_spell``
    Trigger phase leaves zones=() (Eternal Scourge, Misthollow, Squee, Vega), and
    synthesize a from:exile marker for the exile-and-cast engines phase leaves with
    neither, so the cast_from_exile lane reads the cast-from zone structurally.
    Idempotent; gated to the cast-from-exile oracle. CR 601.3b."""
    if not card.faces:
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    low = stripped.lower()
    # cheap dispatch: every arm needs one of these substrings (combinator detects).
    if not ("exile" in low or "plot" in low or "anywhere other than your hand" in low):
        return card
    if _CAST_FROM_EXILE_P.run(stripped) is None:
        return card
    stamped = False
    new_faces = []
    for face in card.faces:
        new_abs = []
        for ab in face.abilities:
            trig = ab.trigger
            if (
                trig is not None
                and trig.event == "cast_spell"
                and "from:exile" not in trig.zones
            ):
                trig = replace(trig, zones=(*trig.zones, "from:exile"))
                stamped = True
            effs = []
            for e in ab.effects:
                new_e = e
                if e.category == "cast_from_zone" and "from:exile" not in e.zones:
                    new_e = replace(e, zones=(*e.zones, "from:exile"))
                    stamped = True
                effs.append(new_e)
            new_abs.append(replace(ab, trigger=trig, effects=tuple(effs)))
        new_faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(new_faces))
    if stamped:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", zones=("from:exile",), raw=""),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# exile_matters — the EXILE-ZONE-AS-RESOURCE lane. phase SCATTERS the reference: it
# tags ``in:exile`` on a count operand (Ulamog place_counter) and ``exile`` on a
# Condition (Ketramose) — those the signals arm reads directly — but DROPS the zone
# off a ``characteristic_pt`` P/T scaler ("cards you own in exile" — Cosmogoyf,
# Crackling Drake) and an "exiled with ~" persistent-pile payoff (Gorex). Stamp
# ``in:exile`` onto the standing-in-exile effects phase left zoneless; synthesize a
# marker for the oracle-only residue. Distinct from exile_removal (``to:exile``).
# CR 406.
# #24e P2 parser-substrate: the CARD-LEVEL standing-in-exile gate is a `_combinators`
# scan over two opt()-bearing arms (the deleted regex's two alternations) — a showcase
# of opt() for the "(you own )?(that are )?"/"(you own )?(in )?" optional slots:
#   A: cards [you own]? [that are]? in exile*
#   B: for each card [you own]? [in]? exile*
# The terminal slot matches the WHOLE word with the "exile" PREFIX (exile/exiled/exiles)
# because the deleted regex's bare "exile" matched the "card exiled this way" / "cards
# exiled" PAYOFFS by substring (the prefix of "exiled") — those are real exile_matters
# members (Gorex, Lumbering Battlement, Crypt Incursion, the March cost-reducers), so
# the gate must keep them; the per-effect ``_EXILE_STANDING_CLAUSE_RE`` (`card(s)
# exiled` / `exiled with`) is the structural stamp the gate guards. Set-equal to the
# deleted regex. Ports to phase-rs as nom `alt((..., ...))` with `opt`. CR 406.
_EXILE_WORD = comb.satisfy(lambda w: w.startswith("exile"))
_EXILE_STANDING = comb.scan(
    comb.alt(
        comb.value(
            None,
            comb.preceded(
                comb.keyword({"card", "cards"}),
                comb.preceded(
                    comb.opt(comb.seq2(comb.keyword({"you"}), comb.keyword({"own"}))),
                    comb.preceded(
                        comb.opt(
                            comb.seq2(comb.keyword({"that"}), comb.keyword({"are"}))
                        ),
                        comb.seq2(comb.keyword({"in"}), _EXILE_WORD),
                    ),
                ),
            ),
        ),
        comb.value(
            None,
            comb.preceded(
                comb.seq3(
                    comb.keyword({"for"}),
                    comb.keyword({"each"}),
                    comb.keyword({"card"}),
                ),
                comb.preceded(
                    comb.opt(comb.seq2(comb.keyword({"you"}), comb.keyword({"own"}))),
                    comb.preceded(comb.opt(comb.keyword({"in"})), _EXILE_WORD),
                ),
            ),
        ),
    )
)
# Per-effect anchor (the clause references cards STANDING in exile, not exiling TO
# exile) — used to pick which zoneless effect carries the in:exile tag.
_EXILE_STANDING_CLAUSE_RE = re.compile(
    r"\bin exile\b|exiled with\b|\bcard exiled\b|\bcards exiled\b", re.IGNORECASE
)


def _recover_exile_zone_ref(card: Card, oracle: str) -> Card:
    """Stamp ``in:exile`` onto the standing-in-exile effects phase leaves zoneless (a
    ``characteristic_pt`` P/T scaler — Cosmogoyf; an "exiled with ~" pile payoff —
    Gorex), and synthesize an in:exile marker for the oracle-only residue, so the
    exile_matters arm reads the zone structurally (additive to the ``in:exile`` count
    operand / ``exile`` Condition phase already structures). Idempotent; gated to the
    standing-in-exile oracle. CR 406."""
    if not card.faces:
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "exile", _EXILE_STANDING):
        return card
    has_zone = any(
        "in:exile" in e.zones for ab in card.all_abilities() for e in ab.effects
    )
    stamped = False
    new_faces = []
    for face in card.faces:
        new_abs = []
        for ab in face.abilities:
            effs = []
            for e in ab.effects:
                new_e = e
                if (
                    "in:exile" not in e.zones
                    and "to:exile" not in e.zones
                    and _EXILE_STANDING_CLAUSE_RE.search(e.raw or "")
                ):
                    new_e = replace(e, zones=(*e.zones, "in:exile"))
                    stamped = True
                effs.append(new_e)
            new_abs.append(replace(ab, effects=tuple(effs)))
        new_faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(new_faces))
    if stamped or has_zone:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="other", zones=("in:exile",), raw=""),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# land_sacrifice_matters — phase emits real structure for most of the lane: the
# land-to-graveyard PAYOFF is a leaves/dies Trigger whose subject is a Land you
# control (Slogurk leaves subj=Land; Titania dies subj=Land) — the signals arm reads
# it directly. The sac OUTLET (Zuran Orb "Sacrifice a land:") is an activated
# Ability whose cost projects to a bare 'sacrifice' token, DROPPING the sacrificed
# Land type into the raw. Synthesize a ``sacrifice`` Effect with a Land-you subject
# for the cost-sac (and any "whenever you sacrifice a land" / "unless you sacrifice a
# land" body phase leaves unstructured) so the lane reads the sacrificed-permanent
# type structurally. A Land-ONLY sacrifice subject is already excluded from
# sacrifice_outlets (CR 701.16), so it stays this lane's own signal.
# #24e P3 parser-substrate: the land-sacrifice detector reads STRUCTURE. Arm 1 keys on
# the cost separator `:` glued to "land"/"land card" (`_word_with_colon`, since norm
# strips the colon). `[^.]*` gaps → `bounded_scan`. Quantity bag (a|one or more|another)
# is shared by arms 2-3. Detection-only.
_LAND_SAC_QTY = comb.alt(
    comb.phrase({"one"}, {"or"}, {"more"}), comb.keyword({"a", "another"})
)


def _word_with_colon(bag: set[str]) -> comb.Parser[str]:
    """Match a word whose normalized form is in ``bag`` AND whose RAW form carries a
    cost-separator ``:`` (which ``norm_word`` strips) — "Sacrifice a land:" / "land
    card:". The colon distinguishes a sacrifice COST from a mere "sacrifice a land"
    body verb, so it must not be folded away. CR 602.1 / 118.3."""

    def go(s: str) -> tuple[str, str] | None:
        r = comb.word().run(s)
        if r is None or comb.norm_word(r[0]) not in bag or ":" not in r[0]:
            return None
        return (comb.norm_word(r[0]), r[1])

    return comb.Parser(go)


_LAND_SACRIFICE_P = comb.alt(
    comb.seq(
        comb.phrase({"sacrifice"}, {"a"}),
        comb.alt(
            _word_with_colon({"land"}),
            comb.seq(comb.keyword({"land"}), _word_with_colon({"card"})),
        ),
    ),
    comb.seq(
        comb.keyword({"whenever"}),
        _LAND_SAC_QTY,
        comb.keyword({"land", "lands"}),
        comb.opt(comb.keyword({"card", "cards"})),
        comb.bounded_scan(comb.phrase({"put"}, {"into"})),
        comb.bounded_scan(comb.keyword({"graveyard"})),
    ),
    comb.seq(
        comb.keyword({"whenever"}),
        comb.keyword({"you"}),
        comb.keyword({"sacrifice"}),
        _LAND_SAC_QTY,
        comb.keyword({"land", "lands"}),
    ),
    comb.phrase({"unless"}, {"you"}, {"sacrifice"}, {"a"}, {"land"}),
)


def _land_sac_trigger_present(card: Card) -> bool:
    """A leaves/dies Trigger whose subject is a Land you control — the structured
    land-to-graveyard payoff the signals arm reads directly (Slogurk, Titania)."""
    return any(
        ab.trigger is not None
        and ab.trigger.event in ("leaves", "dies")
        and ab.trigger.subject is not None
        and "Land" in ab.trigger.subject.card_types
        and ab.trigger.subject.controller == "you"
        for ab in card.all_abilities()
    )


def _land_sac_effect_present(card: Card) -> bool:
    """A YOUR-side land-sacrifice Effect the signals arm already reads (scope not
    each/opp — a symmetric "each player sacrifices a land" does NOT count, so a card
    whose only structured land-sac is symmetric still gets the you-side cost synth —
    Mana Vortex's "counter it unless you sacrifice a land")."""
    return any(
        e.category == "sacrifice"
        and e.subject is not None
        and e.subject.card_types == ("Land",)
        and e.scope not in ("each", "opp")
        for ab in card.all_abilities()
        for e in ab.effects
    )


def _recover_land_sacrifice(card: Card, oracle: str) -> Card:
    """Append a synthetic ``sacrifice`` Effect (subject Land you control) for the
    land sac-OUTLET cost / "whenever you sacrifice a land" / "unless you sacrifice a
    land" bodies phase leaves with the sacrificed Land type only in raw, so the
    land_sacrifice_matters arm reads the sacrificed-permanent type structurally. The
    leaves/dies Land-subject payoff trigger is already structured — no synth for it.
    Append-only; skipped when a land-sac trigger or effect already exists. CR
    701.16."""
    if not card.faces:
        return card
    if _land_sac_trigger_present(card) or _land_sac_effect_present(card):
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "land" not in stripped.lower():  # cheap dispatch — every arm names a land.
        return card
    span = _scan_span(stripped, _LAND_SACRIFICE_P)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="sacrifice",
                scope="you",
                subject=Filter(card_types=("Land",), controller="you"),
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# ── ADR-0027 #24d — cost-REDUCTION residue (SIDECAR v55) ──────────────────────
# phase emits NO cat=="cost_reduction" Effect for a large class of genuine build-
# around reducers — it carries only the static ModifyCost{Reduce} (a spell-class
# discount) and the named `reducenextspellcost` effect, and DROPS WHOLLY:
#   • ability-cost reducers ("Activated abilities of creatures you control cost {2}
#     less to activate" — Agatha, Biomancer's Familiar, Power Artifact; Boast/Equip
#     ability-cost reducers — Dragonkin Berserker, Fervent Champion),
#   • conditional spell reducers ("Those spells cost {G} less to cast" — the Defiler
#     cycle),
#   • donor reducers ("spells that player casts cost {2} less" — Will Kenrith),
#   • named special-cost reducers ("Blitz/Flashback costs you pay cost {N} less" —
#     Henzie, Catalyst Stone), and
#   • granted/quoted reducers ("Spells you cast cost {1} less" on a created token —
#     Tamiyo, Compleated Sage's Notebook).
# These are all CR 601.2f cost reductions (an effect that reduces the total cost to
# cast a spell / activate an ability) the cost_reduction signals arm needs. This
# card-level pass — the _recover_base_pt_set / _recover_opponent_cast_lock precedent
# (phase dropped the WHOLE clause, so synthesize the Effect from the raw oracle) —
# emits one cost_reduction static Effect (subject None, the matched reducer clause as
# raw) so the EXISTING arm reads STRUCTURE and the kept _COST_REDUCER_MIRROR retires.
# CR 601.2f / 118.7.
#
# The arms are the SIX the (already-narrowed, not byte-identical) signals mirror
# carried — each requires a "cost(s) … less" reduction of OTHER spells/abilities and
# structurally excludes "this spell costs" (self-discount) and "… more"/"an
# additional" (increase), so the synthesized raw passes the arm's subject-None screen
# (_COST_SELF_DISCOUNT / _COST_LESS_REDUCER / _COST_INCREASE) and the recovered set is
# exactly the mirror's. Append-only and gated to a body phase left WITHOUT any
# cost_reduction Effect (the 211 cleanly-structured reducers already fire the arm).
# #24e P3 parser-substrate: the six cost-reducer arms read STRUCTURE. A mana token is
# a word whose RAW carries `{…}` (`_MANA_BRACED`, where braces are required) or whose
# NORM is a bare mana run (`_MANA_AMOUNT`, optional braces — norm strips them). `[^.]`
# char-gaps → `bounded_scan` (clause-bounded; the recover runs per period-split clause,
# so the char caps and the clause are near-coextensive). Arm C's `(?<!this )` lookbehind
# is a custom scan that skips a "spell" preceded by "this".
_MANA_BRACE_RE = re.compile(r"\{[wubrgcx0-9]+\}", re.IGNORECASE)
_MANA_RUN_RE = re.compile(r"[wubrgcx0-9]+", re.IGNORECASE)
_MANA_BRACED = comb.Parser(
    lambda s: (
        r
        if (r := comb.word().run(s)) is not None and _MANA_BRACE_RE.match(r[0])
        else None
    )
)
_MANA_AMOUNT = comb.satisfy(lambda w: bool(_MANA_RUN_RE.fullmatch(w)))
_CR_LESS_TO_CAST = comb.phrase({"less"}, {"to"}, {"cast"})


def _cr_arm_c() -> comb.Parser[object]:
    """Arm C: a spell CLASS you cast made cheaper — the regex's `(?<!this )` lookbehind
    becomes a scan that skips a "spell(s)" preceded by "this" (a self-discount), then
    parses "… you cast … cost <amount> … less to cast"."""
    # The "cost <amount>" is one bounded_scan UNIT so it backtracks past a false "cost"
    # lead (Zimone: "… with {X} in its mana cost each turn costs {1} less …" — the first
    # "cost" carries no mana amount; the regex backtracked to "costs {1}", so must we).
    rest = comb.seq(
        comb.bounded_scan(comb.phrase({"you"}, {"cast"})),
        comb.bounded_scan(comb.seq2(comb.keyword({"cost", "costs"}), _MANA_AMOUNT)),
        comb.bounded_scan(_CR_LESS_TO_CAST),
    )

    def go(s: str) -> tuple[object, str] | None:
        prev = None
        cur = s
        while True:
            w = comb.word().run(cur)
            if w is None:
                return None
            nw = comb.norm_word(w[0])
            if nw in {"spell", "spells"} and prev != "this":
                r = rest.run(w[1])
                if r is not None:
                    return r
            prev = nw
            cur = w[1]

    return comb.Parser(go)


_COST_REDUCTION_RECOVER_P = comb.alt(
    # A. ability-cost reducers: "<class of> abilities … cost {N} less to activate".
    comb.scan(
        comb.seq(
            comb.keyword({"abilities"}),
            comb.bounded_scan(comb.keyword({"cost"})),
            comb.bounded_scan(comb.keyword({"less"})),
            comb.bounded_scan(comb.phrase({"to"}, {"activate"})),
        )
    ),
    # B. conditional spell reducer: "those spells cost {C} less" (the Defiler cycle).
    comb.scan(
        comb.seq(
            comb.phrase({"those"}, {"spells"}, {"cost"}),
            _MANA_BRACED,
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
    # C. a spell CLASS (NOT "this spell") you cast made cheaper.
    _cr_arm_c(),
    # D. a donor reducer: "spells <a player> casts cost {N} less" (Will Kenrith).
    comb.scan(
        comb.seq(
            comb.keyword({"spells"}),
            comb.alt(
                comb.phrase({"that"}, {"player"}),
                comb.phrase({"those"}, {"players"}),
                comb.phrase({"that"}, {"opponent"}),
                comb.phrase({"each"}, {"player"}),
            ),
            comb.bounded_scan(
                comb.seq(
                    comb.keyword({"cast", "casts"}),
                    comb.keyword({"cost"}),
                    _MANA_BRACED,
                )
            ),
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
    # E. a named special cost: "Blitz/Flashback costs you pay cost {N} less".
    comb.scan(
        comb.seq(
            comb.keyword(
                {"blitz", "cycling", "kicker", "flashback", "escape", "ninjutsu"}
            ),
            comb.keyword({"costs"}),
            comb.bounded_scan(comb.seq2(comb.keyword({"cost"}), _MANA_BRACED)),
            comb.bounded_scan(comb.keyword({"less"})),
        )
    ),
    # F. a granted/property-filtered spell class made cheaper, no "you cast".
    comb.scan(
        comb.seq(
            comb.phrase({"spells"}, {"with"}),
            comb.bounded_scan(comb.seq2(comb.keyword({"cost"}), _MANA_AMOUNT)),
            comb.bounded_scan(_CR_LESS_TO_CAST),
        )
    ),
)
# The arm's subject-None screen (mirrored here so the gate skips only a card that
# already FIRES the cost_reduction arm, not one phase left a cost_reduction Effect on
# that the screen rejects — Invasion of the Giants' chapter-III reducer collapses to a
# raw "Chapter 3" Effect that fails the screen, so it must still recover). CR 601.2f.
# The `[^."]` gaps mirror onto bounded_scan with delims='."' (period + double-quote
# only — commas/semicolons are allowed inside the regex char class).
_COST_RED_SELF_P = comb.scan(
    comb.alt(
        comb.phrase({"this"}, {"spell"}, {"costs"}),
        comb.phrase({"this"}, {"ability"}, {"costs"}),
        comb.phrase({"this"}, {"costs"}),
    )
)
_COST_RED_LESS_P = comb.scan(
    comb.seq2(
        comb.keyword({"cost", "costs"}),
        comb.bounded_scan(comb.keyword({"less"}), delims='."'),
    )
)
_COST_RED_MORE_P = comb.alt(
    comb.scan(
        comb.seq2(
            comb.keyword({"cost", "costs"}),
            comb.bounded_scan(
                comb.alt(comb.keyword({"more"}), comb.phrase({"an"}, {"additional"})),
                delims='."',
            ),
        )
    ),
    comb.scan(comb.phrase({"would"}, {"cost"}, {"less"}, {"than"})),
)


def _cost_reduction_fires(e: Effect) -> bool:
    """True iff this cost_reduction Effect would fire the signals arm (a non-None
    subject is trusted; a subject-None effect must carry a genuine "cost(s) … less"
    reduction that is neither a self-discount nor a cost-increase). CR 601.2f."""
    if e.category != "cost_reduction":
        return False
    if e.subject is not None:
        return True
    raw = e.raw or ""
    return (
        _COST_RED_LESS_P.run(raw) is not None
        and _COST_RED_SELF_P.run(raw) is None
        and _COST_RED_MORE_P.run(raw) is None
    )


def _recover_cost_reduction(card: Card, oracle: str) -> Card:
    """Append a synthetic ``cost_reduction`` static Effect (subject None, scope you)
    for the build-around cost reducers phase drops wholly (ability-cost reducers, the
    Defiler conditional, donor / named-special / granted reducers). Append-only and
    gated: a card already carrying a cost_reduction Effect that FIRES the arm (see
    _cost_reduction_fires) is left alone — but a Saga-chapter collapse ("Chapter 3"
    raw) that does not is still recovered. One Effect per card, raw = the first
    matching reducer clause (so the arm's subject-None screen sees a genuine reducer,
    not the whole oracle). CR 601.2f / 118.7."""
    if not card.faces:
        return card
    if any(_cost_reduction_fires(e) for ab in card.all_abilities() for e in ab.effects):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "less" not in text.lower():  # cheap dispatch — every reducer arm needs "less".
        return card
    clause = next(
        (
            cl.strip()
            for cl in re.split(r"[.\n]", text)
            if _COST_REDUCTION_RECOVER_P.run(cl) is not None
        ),
        None,
    )
    if clause is None:
        return card
    synth = Ability(
        kind="static",
        effects=(Effect(category="cost_reduction", scope="you", raw=clause),),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24d — CREATURE-copy clone residue (SIDECAR v55) ──────────────────
# phase folds the optional ETB-copy replacement "you may have this creature enter as
# a copy of any creature" (and "becomes a copy of that/target creature") into a
# `choose` / empty node — emitting NO cat=="clone" Effect — for a class of genuine
# CREATURE copies (Spark Double, Stunt Double, Mockingbird, Chameleon Master of
# Disguise, Vesuvan Shapeshifter, Progenitor Mimic, The Mimeoplasm, Essence of the
# Wild, Permeating Mass, Moritte of the Frost). The clone_makers arm reads the COPIED
# type off a `clone` Effect's subject (creature copy → clone_makers; CR 707.2 — the
# copy acquires the original's card type), so a dropped clone Effect = a silent miss.
# This card-level pass — the _recover_base_pt_set precedent (phase dropped the WHOLE
# Effect, so synthesize it from the raw oracle) — emits a `clone` Effect with a
# Creature (or Permanent, for a "copy of a permanent" changeling) subject so the arm
# reads STRUCTURE and the kept CLONE_MATTERS_REGEX mirror retires. CR 707.1 / 707.2.
#
# Append-only and gated to a body phase left WITHOUT any clone Effect: a card phase
# DID structure a copy on (Copy Artifact / Copy Land / Mycosynth Gardens / Thespian's
# Stage — a clone Effect with an Artifact/Land/Enchantment subject) is left alone, so
# the NON-creature copies correctly fire their per-type copy lane (copy_artifact /
# copy_land / copy_enchantment) and drop clone_makers — the over-broad mirror's
# creature-blind firing is the over-fire being shed (CR 707.2: a copy of an artifact
# is an artifact copy, not a creature copy). The veto on a TOKEN-copy ("create a token
# that's a copy" — Mirror Match) rides the existing arm, not here.
# #24e P3 parser-substrate: the creature-copy detector reads STRUCTURE. `[^.\"“”]` gaps
# → bounded_scan with delims='.\"“”' (period + quotes only — the regex allows commas /
# semicolons). `\bcreature` (no trailing boundary) → {creature, creatures}. Arm 5's
# `(?!…\b)` negative lookahead → `_clone_not_next` (a zero-width assert that the next
# word is not an explicit non-creature card type). The copy-of-a-permanent arm doubles
# as the Permanent-subject discriminator. CR 707.1 / 707.2.
_CLONE_DELIMS = '."“”'
_CLONE_CREATURE_W = comb.keyword({"creature", "creatures"})


def _clone_not_next(bag: set[str]) -> comb.Parser[None]:
    """Zero-width negative lookahead (nom ``not``): succeed (consuming nothing) iff the
    NEXT word's normalized form is not in ``bag`` — the regex `(?!(?:…)\\b)`."""

    def go(s: str) -> tuple[None, str] | None:
        w = comb.word().run(s)
        if w is not None and comb.norm_word(w[0]) in bag:
            return None
        return (None, s)

    return comb.Parser(go)


_CLONE_COPY_PERMANENT_P = comb.scan(
    comb.seq(
        comb.phrase({"copy"}, {"of"}),
        comb.opt(comb.keyword({"a", "an", "any", "another", "target", "that"})),
        comb.keyword({"permanent"}),
    )
)
_CLONE_CREATURE_COPY_P = comb.scan(
    comb.alt(
        # "as a copy of … creature".
        comb.seq(
            comb.phrase({"as"}, {"a"}, {"copy"}, {"of"}),
            comb.bounded_scan(_CLONE_CREATURE_W, delims=_CLONE_DELIMS),
        ),
        # "copy of <det> … creature".
        comb.seq(
            comb.phrase({"copy"}, {"of"}),
            comb.keyword({"a", "an", "any", "another", "target", "that", "this"}),
            comb.bounded_scan(_CLONE_CREATURE_W, delims=_CLONE_DELIMS),
        ),
        # "copy of <det?> permanent".
        comb.seq(
            comb.phrase({"copy"}, {"of"}),
            comb.opt(comb.keyword({"a", "an", "any", "another", "target", "that"})),
            comb.keyword({"permanent"}),
        ),
        # "creatures you control enter as a copy".
        comb.phrase(
            {"creatures"}, {"you"}, {"control"}, {"enter"}, {"as"}, {"a"}, {"copy"}
        ),
        # "enter(s) [the battlefield] as | become(s)" a copy of <det?> … card(s).
        comb.seq(
            comb.alt(
                comb.seq(
                    comb.keyword({"enter", "enters"}),
                    comb.opt(comb.phrase({"the"}, {"battlefield"})),
                    comb.keyword({"as"}),
                ),
                comb.keyword({"become", "becomes"}),
            ),
            comb.phrase({"a"}, {"copy"}, {"of"}),
            comb.opt(
                comb.alt(
                    comb.phrase({"one"}, {"of"}, {"those"}),
                    comb.keyword({"a", "an", "the", "that", "any"}),
                )
            ),
            _clone_not_next(
                {
                    "artifact",
                    "land",
                    "enchantment",
                    "instant",
                    "sorcery",
                    "planeswalker",
                }
            ),
            comb.bounded_scan(comb.keyword({"card", "cards"}), delims=_CLONE_DELIMS),
        ),
    )
)


def _recover_clone_creature(card: Card, oracle: str) -> Card:
    """Append a synthetic ``clone`` Effect (Creature subject, or Permanent for a
    "copy of a permanent" changeling) for the creature-copy replacements phase folds
    to a non-clone node. Append-only and gated: a card already carrying ANY clone
    Effect (phase structured the copy — including the non-creature Copy Artifact / Copy
    Land family) is left alone, so only the genuinely-dropped creature copies recover
    and the non-creature copies keep their per-type lane. CR 707.1 / 707.2."""
    if not card.faces:
        return card
    # Skip only when phase ALREADY structured a CREATURE/PERMANENT copy (the
    # clone_makers arm fires off Creature/Permanent in the copied subject). A clone
    # Effect typed to a non-creature permanent (the Copy Artifact / Copy Land family —
    # Artifact/Land/Enchantment subject) does NOT fire clone_makers, so it must still
    # run the creature-copy check: Dermotaxi copies a CREATURE card but phase types its
    # subject "Artifact" (from the "Vehicle artifact" rider), so the gate would skip a
    # creature copy. The creature-copy regex then no-ops on a true non-creature copy
    # ("copy of any artifact") and recovers Dermotaxi's "copy of the exiled [creature]
    # card". An EMPTY-subject clone (Essence of the Wild, Permeating Mass) also runs.
    if any(
        e.category == "clone"
        and e.subject is not None
        and bool({"Creature", "Permanent"} & set(e.subject.card_types))
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "copy" not in text.lower():  # cheap dispatch — every arm needs "copy".
        return card
    if _CLONE_CREATURE_COPY_P.run(text) is None:
        return card
    copied = (
        Filter(card_types=("Permanent",))
        if _CLONE_COPY_PERMANENT_P.run(text) is not None
        else Filter(card_types=("Creature",))
    )
    synth = Ability(
        kind="static",
        effects=(
            Effect(category="clone", scope="any", subject=copied, raw=text.strip()),
        ),
    )
    head, *rest = card.faces
    return replace(
        card,
        faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
    )


# ── ADR-0027 #24d — OPPONENT-directed discard residue (SIDECAR v55) ────────────
# phase structures a forced discard as a `discard` Effect but DROPS the discardER
# scope to 'any' whenever the discarding player is ANAPHORIC — "that player discards"
# referring to a structurally-identified opponent it can't resolve. The disconnected
# pieces survive in the IR:
#   A. a damage-CONNECT specter: a combat_damage / deals_damage trigger whose
#      recipient is a PLAYER (recipient=('player',) or a DamageToPlayer subject
#      predicate) + a `discard` Effect on the SAME ability ("whenever ~ deals combat
#      damage to a player, that player discards" — Abyssal/Hypnotic Specter, Chilling
#      Apparition, Cabal Slaver, Larceny, Sword of Feast and Famine). The damaged
#      player is the discardER → an opponent. CR 510.1c.
#   B. a ParentTarget bounce/counter-then-discard: a `bounce` or `counter_spell`
#      Effect preceding the discard in the same ability ("Return target permanent …,
#      then that player discards" — Recoil, Dinrova Horror; "Counter target spell …
#      that player discards" — Frightful Delusion, Compelling Deterrence). The
#      target's controller is the discardER → an opponent. CR 701.9.
#   C. a reveal-hand-then-discard: a `reveal_hand` / `reveal` Effect scoped to an
#      opponent preceding the discard ("Look at target opponent's hand … that player
#      discards" — Mind Warp, Extortion, Collective Brutality, Thrull Surgeon). CR
#      701.9 / 701.18.
#   D. an each/target-OPPONENT discard the raw names but phase scoped 'any' ("each
#      opponent discards" — Words of Waste, Bite of the Black Rose, Bladecoil Serpent).
# For each, append a sibling `discard` Effect scope='opp' so the EXISTING opponent_
# discard arm (which reads a `discard` Effect scope opp/each or subject.controller==
# opp) fires STRUCTURALLY. Append-only and gated to a body phase left WITHOUT an
# opp/each-directed discard (the cleanly-structured forced-opponent discards — Mind
# Rot, Stupor, Dark Deal — already fire the arm). The genuinely-unstructurable tail
# phase leaves no anchor for — "whenever a player discards" PAYOFFS (Confessor, Spirit
# Cairn), the "discarded a card this turn" past-tense payoff (Tinybones), would-draw
# REPLACEMENTS (Chains of Mephistopheles), and granted/quoted grants (Wand of Ith,
# Dementia Sliver) — keeps the NARROWED residue mirror (the spec's upstream-phase gap).
# CR 701.9 / 510.1c / 102.2.
# #24e P2 parser-substrate: the each/target/an-opponent discardER raw tell is a
# `_combinators` scan — `scan(phrase({each/target/an}, {opponent}, {discards}))` —
# WHOLE-WORD ("discards" only, mirroring the deleted regex's no-`?`). Ports to phase-rs
# as nom `tuple((alt(det tags), tag("opponent"), tag("discards")))`. CR 701.9.
_OPP_DISCARD_RAW = comb.scan(
    comb.phrase({"each", "target", "an"}, {"opponent"}, {"discards"})
)


def _opp_discard_raw(text: str) -> bool:
    """``each/target/an opponent discards`` anywhere in ``text`` (whole-word)."""
    return "discards" in text.lower() and _OPP_DISCARD_RAW.run(text) is not None


# The OPPONENT-directed discardER tell — the disconnected discard piece's own text
# names the discarding player as an anaphoric opponent ("that player/opponent
# discards", "its controller discards", "each/target opponent discards"). This is the
# discriminator that keeps the damage-CONNECT specter ("that player discards") IN and
# the combat-damage SELF-LOOT ("you may draw a card, then discard a card" — Looter
# il-Kor, Academy Raider, Wharf Infiltrator) OUT: a self-loot's discard names YOU, not
# "that player", so it never fires the anchor. CR 701.9 vs the loot outlet (CR 701.8a).
# #24e P2 parser-substrate: the OPPONENT-directed discardER tell is a `_combinators`
# scan over four arms (the deleted regex's four alternations) — WHOLE-WORD, so a
# past-tense "that player discarded" (the regex matched "that player discard" as a
# substring of "discarded") is NOT a discard tell here (Tinybones-style past-tense
# payoffs stay on the narrowed residue mirror, per this module's design). `discards?`
# → {discard, discards}. CR 701.9.
_DISCARD_OPP_DIRECTED = comb.scan(
    comb.alt(
        comb.phrase({"that"}, {"player", "opponent"}, {"discard", "discards"}),
        comb.phrase({"its"}, {"controller"}, {"discard", "discards"}),
        comb.phrase({"each", "target", "an"}, {"opponent"}, {"discard", "discards"}),
        comb.phrase({"each"}, {"player"}, {"discard", "discards"}),
    )
)


def _directed_discard(text: str) -> bool:
    """An opponent-directed discardER tell anywhere in ``text`` (whole-word)."""
    return "discard" in text.lower() and _DISCARD_OPP_DIRECTED.run(text) is not None


def _opp_discard_anchor(ab: Ability, card_text: str) -> bool:
    """True iff this ability carries an OPPONENT-directed discard (its own text names
    an anaphoric opponent discardER — NOT a self-loot) whose discarding player is a
    structurally-identified opponent: a damage-to-player trigger, a prior bounce/
    counter target, a prior reveal-opponent-hand, or an each/target-opponent raw. CR
    701.9."""
    tr = ab.trigger
    dmg_to_player = (
        tr is not None
        and tr.event in ("deals_damage", "combat_damage")
        and (
            "player" in tr.recipient
            or (
                tr.subject is not None
                and any(p.startswith("DamageToPlayer") for p in tr.subject.predicates)
            )
        )
    )
    for i, e in enumerate(ab.effects):
        if e.category != "discard":
            continue
        # The discard must be OPPONENT-directed (anaphoric "that player discards"),
        # read from its own raw or — for a modal/empty-raw discard — the card text.
        directed = e.raw or ""
        if not _directed_discard(directed) and not (
            not directed.strip() and _directed_discard(card_text)
        ):
            continue
        prior = ab.effects[:i]
        if dmg_to_player:
            return True
        if any(x.category in ("bounce", "counter_spell") for x in prior):
            return True
        if any(
            x.category in ("reveal_hand", "reveal")
            and (
                x.scope == "opp"
                or (x.subject is not None and x.subject.controller == "opp")
            )
            for x in prior
        ):
            return True
        if _opp_discard_raw(card_text):
            return True
    return False


def _recover_opponent_discard(card: Card, oracle: str) -> Card:
    """Append a sibling ``discard`` Effect scope='opp' to each ability whose discard is
    directed at a structurally-identified opponent (see _opp_discard_anchor), so the
    opponent_discard arm reads STRUCTURE for the damage-connect / bounce-counter /
    reveal-hand / each-opponent buckets phase scoped 'any'. Append-only and gated to a
    body phase left WITHOUT an opp/each-directed discard. CR 701.9 / 510.1c."""
    if not card.faces:
        return card
    if any(
        e.category == "discard"
        and (
            e.scope in ("opp", "each")
            or (e.subject is not None and e.subject.controller == "opp")
        )
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    appended = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            if _opp_discard_anchor(ab, text):
                new_abs.append(
                    replace(
                        ab,
                        effects=(
                            *ab.effects,
                            Effect(
                                category="discard",
                                scope="opp",
                                raw="opponent-directed discard (recovered)",
                            ),
                        ),
                    )
                )
                appended = True
            else:
                new_abs.append(ab)
        faces.append(replace(face, abilities=tuple(new_abs)))
    if not appended:
        return card
    return replace(card, faces=tuple(faces))


def _append_marker(card: Card, effect: Effect) -> Card:
    """Append a synthetic static ability carrying one marker ``effect`` to the head
    face — the shared shape the subject-Filter recoveries below use to surface a
    dropped predicate the lane reads off any ability's subject (mirrors
    _recover_devotion_operand). The marker is category="other", so it opens no
    category-gated lane; only the predicate-reading arms see its subject Filter."""
    synth = Ability(kind="static", effects=(effect,))
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# colorless_matters — phase DROPS the "colorless" qualifier off a cast-restriction /
# cost-reduction / counter-target, leaving a subject-less effect (Ghostfire Blade's
# "if it targets a colorless creature" cost_reduction subj=None, Ugin the Ineffable's
# "Colorless spells you cast cost {2} less" cost_reduction subj=None, Consign to
# Memory's "Counter … colorless spell" whose counter_spell subject is a bare Card
# Filter with no color predicate). The discriminator survives only in the raw, so we
# synth a ColorCount:EQ:0 subject Filter the colorless_matters arm
# (_predicate_build_around_lanes) reads structurally. CR 105.2c (a colorless object
# has no color) / 202.2.
# #24e P2 parser-substrate: DETECTION is a `_combinators` word scan —
# ``scan(seq2(keyword({"colorless"}), keyword({creature/spell/permanent + plurals})))``
# — a WHOLE-WORD two-slot read, stricter than the deleted substring regex
# `colorless (?:creature|spell|permanent)` which fired inside larger words ("colorless
# spellbomb" → the regex's "colorless spell" substring). The plural forms are folded in
# (the regex matched "colorless creatures"/"permanents" via its singular substring) so
# the real set holds. Ports to phase-rs as a nom `tuple((tag("colorless"), alt(type
# tags)))`. CR 105.2c.
_COLORLESS_REF = comb.scan(
    comb.seq2(
        comb.keyword({"colorless"}),
        comb.keyword(
            {
                "creature",
                "creatures",
                "spell",
                "spells",
                "permanent",
                "permanents",
            }
        ),
    )
)


def _recover_colorless_subject(card: Card, oracle: str) -> Card:
    """Synth a ColorCount:EQ:0 subject Filter (controller='you') for a card that
    references a colorless creature/spell/permanent but whose effects phase left
    color-blind, so the colorless_matters arm reads the predicate STRUCTURALLY.
    Idempotent (skipped when a real ColorCount:EQ:0 predicate already exists).
    CR 105.2c."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "ColorCount:EQ:0" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "colorless", _COLORLESS_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("ColorCount:EQ:0",)),
            raw="colorless reference (recovered)",
        ),
    )


# historic_matters — phase DROPS the "historic" qualifier off a cast-restriction /
# cost-reduction / discard-cost, leaving a subject-less effect (Raff Capashen's "cast
# historic spells as though they had flash" cast_with_keyword subj=None; Sanctum
# Spirit's "Discard a historic card" activation cost phase collapses to cost='discard'
# with no Historic carrier). The discriminator survives only in the raw, so we synth a
# Historic subject Filter the historic_matters arm (``"Historic" in ir_predicates``)
# reads structurally. An object is historic if it is legendary, an artifact, or a Saga
# (CR 700.6). Set-equal to the deleted "\bhistoric\b" word mirror (same anchor over
# the reminder-stripped joined oracle).
# #24e P1 parser-substrate: the DETECTION is a `_combinators` word scan
# (``find_word({"historic"})``), not a regex — it reads the oracle as a word stream
# and matches the whole word "historic" (word-boundary-safe by the tokenizer, not a
# `\b` assertion). Behavior-neutral with the deleted `\bhistoric\b` mirror (find_word's
# normalized whole-word match == the corpus). Ports to phase-rs as a nom `tag` in a
# word context. CR 700.6.
_HISTORIC_REF = comb.find_word({"historic"})


def _recover_historic_subject(card: Card, oracle: str) -> Card:
    """Synth a Historic subject Filter (controller='you') for a card that references a
    historic object but whose effects/cost phase left without the Historic predicate,
    so the historic_matters arm reads it STRUCTURALLY. Idempotent (skipped when a real
    Historic predicate already exists). CR 700.6."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "Historic" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "historic", _HISTORIC_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("Historic",)),
            raw="historic reference (recovered)",
        ),
    )


# base_power_matters — a base-power/toughness REFERENCE payoff (CR 613.4b sentence 2:
# "effects that REFER to the base power/toughness of a creature apply in layer 7b") —
# is distinct from a base_pt_set SETTER (sentence 1, "effects that SET power/tough").
# A reference says "creatures you control WITH base power N" (Bess Soul Nourisher's ETB
# count, Zinnia's go-wide scale, Duskana's draw-per, Primo's combat trigger, Rapid
# Augmenter's haste grant, Sword of the Squeak's equip scale) — it SELECTS creatures by
# their base P/T and rewards them; it sets nothing. phase preserves SOME of these as a
# `PtComparison:Power:EQ:N` subject predicate but that predicate is base-BLIND (323 of
# 330 cards carrying it reference CURRENT power — "creatures you control with power 4 or
# greater"), so the lane can't read PtComparison directly without massively over-firing
# to the current-power references. We therefore synth a base-SPECIFIC `BasePtRef` marker
# Filter (controller='you'), anchored on the same base-reference grammar the deleted
# base_pt_set kept word mirror used, so the base_power_matters arm reads the base-only
# predicate STRUCTURALLY. Set-equal to that deleted mirror (`creatures? you control/own
# with base power|toughness` over the reminder-stripped oracle) — the references LEAVE
# base_pt_set (they were an over-fire: set no base P/T) and ENTER base_power_matters.
# The setter verb ("have/has/are/is/becomes base power") is NOT matched, so a genuine
# base_pt_set setter never enters this lane (CR 613.4b set vs refer).
# #24e P1 parser-substrate: DETECTION is a `_combinators` clause scan over the
# six-slot phrase "creature(s) you control/own with base power/toughness" — each slot
# a per-position alternation bag, read as consecutive words. Behavior-neutral with the
# deleted `creatures? you (control|own) with base (power|toughness)` mirror; ports to
# phase-rs as a nom `tuple` of six tags. CR 613.4b (refer, not set).
_BASE_POWER_REF = comb.scan(
    comb.phrase(
        {"creature", "creatures"},
        {"you"},
        {"control", "own"},
        {"with"},
        {"base"},
        {"power", "toughness"},
    )
)


def _recover_base_power_ref(card: Card, oracle: str) -> Card:
    """Synth a base-specific `BasePtRef` subject Filter (controller='you') for a card
    that REFERS to a creature's base power/toughness ("creatures you control with base
    power N") but whose base qualifier phase either drops (Bess, Duskana — left an
    `ev:other` trigger / bare-Creature subject) or preserves only as a base-blind
    PtComparison (Zinnia, Primo, Rapid Augmenter, Sword of the Squeak), so the
    base_power_matters arm reads the base-only predicate STRUCTURALLY. Idempotent
    (skipped when a `BasePtRef` marker already exists). CR 613.4b (refer, not set)."""
    if not card.faces:
        return card
    if any(
        isinstance(f, Filter) and "BasePtRef" in f.predicates
        for ab in card.all_abilities()
        for f in _ability_subjects(ab)
    ):
        return card
    if not _anchored(re.sub(r"\([^)]*\)", " ", oracle), "with base", _BASE_POWER_REF):
        return card
    return _append_marker(
        card,
        Effect(
            category="other",
            subject=Filter(controller="you", predicates=("BasePtRef",)),
            raw="base power/toughness reference (recovered)",
        ),
    )


def _ability_subjects(ab: Ability) -> list[Filter]:
    """Every subject Filter an ability exposes (effect subjects, amount subjects,
    trigger subject) — the surface the predicate-reading lane arms scan."""
    subs: list[object] = [e.subject for e in ab.effects]
    subs += [e.amount.subject for e in ab.effects if e.amount is not None]
    if ab.trigger is not None:
        subs.append(ab.trigger.subject)
    return [f for f in subs if isinstance(f, Filter)]


# scaling_pump — a "~ gets +N/+N for each <X>" board-count scaler phase routes through
# a NON-`pump` carrier so the structural scaling_pump arm (cat=='pump' + scaling
# count) misses it: the token-borne grant lands on a `board_count` Effect (Karn Scion
# of Urza / Urza Lord High Artificer's "Construct … gets +1/+1 for each artifact you
# control"), a make_token raw (Vren's "Rat … gets +1/+1 for each other Rat you
# control"), or a single-target `pump_target` Effect with amount=None (Gold Rush's
# "creature gets +2/+2 for each Treasure you control"). We synth a `pump` Effect
# carrying the recovered op='count' operand (the for-each scaling reference the gate
# reads), so the arm fires STRUCTURALLY. The synth subject is left None on purpose: the
# count's go-wide reference lives in the raw (`_is_scaling_count` reads the "for each"
# raw for a subjectless count), and a typed subject would over-couple this pump-only
# recovery to the typed-matters lanes (artifacts_matter / etc. cross-read amount
# subjects). CR 613 (P/T-setting/modifying layer) / 107.3.
# #24e P2 parser-substrate: DETECTION is a `_combinators` scan — `scan(seq2(preceded(
# keyword({"gets"}), <PT word>), phrase({"for"}, {"each","every"})))` — where the P/T
# word is read as a STRUCTURED token (`+N/+N`, signed both sides) by a raw fullmatch,
# and the per-each magnitude N is taken from the normalized form (split on '/'). The
# whole-word read drops a substring over-fire and, because the magnitude class is
# `[0-9x]+` (not the deleted regex's single `[0-9x]`), CORRECTLY captures a multi-digit
# scaler ("gets +10/+10 for each …") the regex missed. The synth raw reconstructs the
# matched fragment (incl. trailing) so `_is_scaling_count`'s "for each" read is
# preserved. Ports to phase-rs as a nom `tuple((tag("gets"), pt_token, tag("for"),
# alt((tag("each"), tag("every")))))`. CR 613.
_PT_GETS_RE = re.compile(r"[+\-][0-9x]+/[+\-][0-9x]+", re.IGNORECASE)


def _pt_after_gets() -> comb.Parser[str]:
    """The signed P/T modification token (`+N/+N`) as one word — the structured operand
    a "gets" pump applies (raw fullmatch keeps the sign the normalizer folds)."""

    def go(s: str) -> tuple[str, str] | None:
        r = comb.word().run(s)
        if r is None or not _PT_GETS_RE.fullmatch(r[0]):
            return None
        return r

    return comb.Parser(go)


_SCALING_PUMP = comb.scan(
    comb.seq2(
        comb.preceded(comb.keyword({"gets"}), _pt_after_gets()),
        comb.phrase({"for"}, {"each", "every"}),
    )
)
_SCALING_FOR_EACH_RAW = re.compile(
    r"\bfor each\b|\bequal to the number of\b", re.IGNORECASE
)
_SCALING_NAMED_OPS = frozenset(
    {"counters", "domain", "devotion", "party", "experience"}
)


def _has_structural_scaling_pump(card: Card) -> bool:
    """True when a real `pump` Effect already carries a scaling count (a named scale
    op, or a count/multiply/toughness op with a subject or a for-each raw) — i.e. the
    structural scaling_pump arm already fires, so no synth is needed (the byte-mirror's
    206-card overlap). Mirrors _deck_forge._signals_ir._is_scaling_count."""
    for ab in card.all_abilities():
        for e in ab.effects:
            if e.category != "pump" or e.amount is None:
                continue
            op = e.amount.op
            if op in _SCALING_NAMED_OPS:
                return True
            if op in ("count", "multiply", "toughness") and (
                e.amount.subject is not None
                or _SCALING_FOR_EACH_RAW.search(e.raw or "")
            ):
                return True
    return False


def _recover_scaling_pump(card: Card, oracle: str) -> Card:
    """Synth a `pump` Effect with the recovered op='count' scaling operand for a card
    whose "gets +N/+N for each <X>" pump phase routed through a board_count / make_token
    / amount=None pump_target carrier, so the scaling_pump arm reads it STRUCTURALLY.
    Skipped when a real scaling pump already exists (the structural arm already fires).
    CR 613."""
    if not card.faces:
        return card
    if _has_structural_scaling_pump(card):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "gets" not in text.lower():
        return card
    res = _SCALING_PUMP.run(text)
    if res is None:
        return card
    (ptword, conn), rest = res
    # Per-each magnitude N from the normalized P/T token ("+10/+10" -> "10/10" -> "10").
    mag = comb.norm_word(ptword).split("/")[0]
    factor = 1 if mag in ("x", "") else int(mag)
    # Reconstruct the matched fragment (incl. the no-period/quote trailing) so the synth
    # raw carries "for each <X>" exactly as the deleted regex's m.group(0) did — the
    # `_is_scaling_count` "for each" read depends on it.
    cut = len(rest)
    for i, ch in enumerate(rest):
        if ch in '.\n"':
            cut = i
            break
    raw = f"gets {ptword} for {conn[1]}{rest[:cut]}"
    return _append_marker(
        card,
        Effect(
            category="pump",
            scope="you",
            amount=Quantity(op="count", factor=factor),
            raw=raw,
        ),
    )


# ── ADR-0027 #24h SUPPLEMENT_RECOVER C2 (subject / anaphora / quoted-trigger) ──
# Three reclassified MED-residue lanes whose kept regex mirror was the SOLE source of
# a real tail phase parses but DROPS the discriminating subject / scope / trigger.
# Each recovery reconstructs the dropped STRUCTURE onto the IR (a face-down subject, a
# resolved opponent controller, a synthesized deals_damage trigger) so the lane's IR
# arm reads structure and the regex mirror retires. Append-only / idempotent; same
# joined-oracle seam as the recoveries above.

# (1) facedown_matters — phase emits a face-down REVEAL / LOOK / TURN-face-up payoff as
#     a generic reveal / topdeck_select / transform / cost_reduction with the FACE-DOWN
#     qualifier DROPPED from the subject (Smoke Teller "look at target face-down
#     creature", Break Open "turn target face-down creature … face up", Panoptic
#     Projektor's "next face-down creature spell … costs less"). Stamp the EXACT marker
#     phase emits for NATIVE face-down subjects (the subtype token "Face-down" — see
#     _signals_ir._is_facedown_subject) onto every effect whose own clause references a
#     face-down permanent / spell or a morph-family mechanic, so the existing
#     facedown_matters effect-subject arm fires. The marker is inert outside the lane
#     ("Face-down" is not a creature subtype, so it can't cross into tribal lanes). CR
#     707.2 / 708.2 / 702.36-37.
# Mirror of the deleted FACEDOWN_MATTERS regex (NARROW — a face-down CREATURE/permanent
# reference, a 2/2-face-down, a TURN-face-up phrasing, or a morph-family keyword). It is
# deliberately NOT a bare "face down": a card EXILED face down (impulse-exile / hideaway
# — Bottled Cloister, Scroll Rack, Gonti) is a hidden-card mechanic, not the morph /
# manifest face-down-PERMANENT lane (CR 708 vs 702.36).
# #24e P3 parser-substrate: the face-down reference detector reads STRUCTURE. The
# `face[- ]?down` hyphen variants fold under norm ("face-down"/"facedown" → "facedown")
# OR split into two words ("face down"); `_FACEDOWN_WORD` covers both. `[^.]*?` gap →
# bounded_scan. Detection-only (the synth subject is fixed). CR 707.2 / 708.2.
_FACEDOWN_WORD = comb.alt(comb.keyword({"facedown"}), comb.phrase({"face"}, {"down"}))
_FACEDOWN_NOUN = comb.keyword({"creature", "creatures", "permanent", "permanents"})
_FACEDOWN_REF_P = comb.scan(
    comb.alt(
        # keyword_bounded so an ability word fused to its cost by an em-dash
        # ("Morph—Discard a card") still matches, like the regex `\bmorph\b`.
        comb.keyword_bounded({"morph", "megamorph", "manifest", "disguise", "cloak"}),
        comb.seq2(_FACEDOWN_WORD, _FACEDOWN_NOUN),
        comb.seq(
            comb.phrase({"as"}, {"a"}),
            comb.regex_word(re.compile(r"2/2")),
            _FACEDOWN_WORD,
        ),
        comb.seq(
            comb.keyword({"turn"}),
            comb.alt(
                comb.keyword({"it", "them"}),
                comb.phrase({"that"}, {"creature"}),
                comb.phrase({"this"}, {"creature"}),
                comb.phrase({"a"}, {"permanent"}, {"you"}, {"control"}),
            ),
            comb.phrase({"face"}, {"up"}),
        ),
        comb.seq(
            comb.phrase({"turn"}, {"target"}),
            comb.bounded_scan(comb.phrase({"face"}, {"up"})),
        ),
        comb.phrase({"turned"}, {"face"}, {"up"}),
    )
)
# A card that already fires facedown_matters STRUCTURALLY (a morph-family MAKER) needs
# no carrier: it bears the keyword, a native "Face-down" subject, or a turn_face_up.
_FACEDOWN_KEYWORDS = frozenset(
    {"morph", "megamorph", "manifest", "disguise", "cloak", "manifest dread"}
)


def _has_native_facedown(card: Card) -> bool:
    for face in card.faces:
        if any(k.lower() in _FACEDOWN_KEYWORDS for k in face.keywords):
            return True
    for ab in card.all_abilities():
        if ab.trigger is not None and (
            ab.trigger.event == "turn_face_up"
            or (
                ab.trigger.subject is not None
                and "Face-down" in ab.trigger.subject.subtypes
            )
        ):
            return True
        for e in ab.effects:
            if e.category == "turn_face_up" or (
                e.subject is not None and "Face-down" in e.subject.subtypes
            ):
                return True
    return False


def _recover_facedown(card: Card, oracle: str) -> Card:
    """Append a synthetic ``facedown_ref`` carrier Effect (subject = the exact
    "Face-down" marker phase emits for native face-down subjects) when the oracle
    references a face-down permanent / spell or a morph-family mechanic, so the existing
    facedown_matters effect-subject arm (``_is_facedown_subject``) reads STRUCTURE. The
    card name is stripped first, so a card merely NAMED "… of Disguise" / "… Made
    Manifest" / "Burning Cloak" — not a face-down payoff — is not swept in by its own
    name (a precision gain over the name-blind regex). A dedicated carrier category +
    subject is used (not a mutation of an existing effect's subject) so no other lane's
    subject-presence assumption is disturbed (e.g. the cost_reduction arm trusts a
    non-None subject — a stamped marker would mis-trust a "morph costs cost more" tax).
    Deduped against the morph-family MAKERS already firing structurally. CR 707.2 /
    708.2."""
    if not card.faces:
        return card
    name = card.name or ""
    text = oracle.replace(name, " ") if name else oracle
    text = re.sub(r"\([^)]*\)", " ", text)
    low = text.lower()
    # cheap dispatch: every arm needs a morph-family word or "face".
    if not any(k in low for k in ("face", "morph", "manifest", "disguise", "cloak")):
        return card
    if _FACEDOWN_REF_P.run(text) is None:
        return card
    if _has_native_facedown(card):
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="facedown_ref",
                scope="you",
                subject=Filter(subtypes=("Face-down",)),
                raw="face-down reference (recovered)",
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# (2) tap_down — phase leaves an OPPONENT-tap's controller UNRESOLVED: an anaphoric
#     "tap target <perm> that player controls" / "an opponent controls" projects with
#     subject.controller you/any (Citadel Siege, Karazikar, Sentinel, Somnophore,
#     Delirium) or a DROPPED subject (Snaremaster Sprite, Mind Spiral), so the
#     opponent-tapping lane can't read scope. Resolve the anaphor to controller=='opp'
#     on the tap subject (synthesizing the dropped subject from the tapped noun). The
#     "skips their next untap step" tempo-skip with NO tap effect at all (Brine
#     Elemental, Shisato — keeping the opponent's board tapped) is resolved to
#     scope=='opp' on the skip_step effect. A symmetric "each player's … that player
#     controls" tap (Monsoon, Angel's Trumpet) and a SELF untap-skip (Avizoa, Savor the
#     Moment) are both excluded. CR 701.20 / 702.36.
# #24e P3 parser-substrate: the tap-down anaphora reads STRUCTURE. `keyword({"tap"})`
# matches only the standalone word "tap" (norm keeps "untap"/"taps"/"tapped" distinct),
# so the regex `(?<!un)tap\b` lookbehind is satisfied for free. `[^.]*?` gap →
# bounded_scan. `_TAP_NOUN_P` maps the tapped noun to its capitalized singular subject.
_TAP_OPP_NOUN = comb.alt(
    comb.phrase({"an"}, {"opponent"}),
    comb.phrase({"that"}, {"player"}),
    comb.phrase({"that"}, {"opponent"}),
    comb.phrase({"target"}, {"opponent"}),
    comb.phrase({"defending"}, {"player"}),
    comb.phrase({"your"}, {"opponents"}),
    comb.keyword({"opponents"}),
)
_TAP_OPP_CONTROL_P = comb.scan(
    comb.seq2(
        comb.keyword({"tap"}),
        comb.bounded_scan(
            comb.seq2(_TAP_OPP_NOUN, comb.keyword({"control", "controls"}))
        ),
    )
)
# Substring regexes ("each player", "untap step") matched the possessive/plural
# ("each player's", "untap steps"), so accept those in the trailing slot.
_EACH_PLAYER_P = comb.scan(comb.phrase({"each"}, {"player", "players"}))
_SKIP_UNTAP_P = comb.scan(comb.phrase({"untap"}, {"step", "steps"}))
_SKIP_OPP_P = comb.scan(
    comb.seq2(
        comb.alt(
            comb.phrase({"each"}, {"opponent"}),
            comb.phrase({"that"}, {"player"}),
            comb.phrase({"target"}, {"player"}),
            comb.phrase({"target"}, {"opponent"}),
            comb.phrase({"an"}, {"opponent"}),
            comb.phrase({"that"}, {"opponent"}),
            comb.keyword({"opponent", "opponents"}),
        ),
        comb.keyword({"skip", "skips"}),
    )
)
_SKIP_SELF_P = comb.alt(
    comb.scan(comb.phrase({"you"}, {"skip"})),
    comb.scan(
        comb.seq(
            comb.keyword({"your"}),
            comb.opt(comb.keyword({"next"})),
            comb.phrase({"untap"}, {"step"}),
        )
    ),
)
_TAP_NOUN_MAP = {
    "land": "Land",
    "lands": "Land",
    "permanent": "Permanent",
    "permanents": "Permanent",
    "artifact": "Artifact",
    "artifacts": "Artifact",
    "creature": "Creature",
    "creatures": "Creature",
}
_TAP_NOUN_P = comb.scan(comb.satisfy(lambda w: w in _TAP_NOUN_MAP)).map(
    lambda w: _TAP_NOUN_MAP[comb.norm_word(w)]
)


def _tap_subject_opp(subject: Filter | None, clause: str) -> Filter:
    """Set the tap target's controller to 'opp', synthesizing the type subject phase
    dropped (read from the tapped noun — "tap target LAND that player controls")."""
    if subject is None:
        r = _TAP_NOUN_P.run(clause)
        ct = r[0] if r is not None else "Creature"
        return Filter(card_types=(ct,), controller="opp")
    return replace(subject, controller="opp")


def _recover_tap_down(card: Card, oracle: str) -> Card:
    """Resolve the opponent anaphora on tap / skip-untap-step effects so tap_down reads
    STRUCTURE (a tap subject controller=='opp', a skip_step scope=='opp'). Each effect
    reads its OWN clause raw (the full oracle only when phase dropped that raw —
    Delirium, Mind Spiral). Idempotent (a tap already controller=='opp' / a skip already
    scope=='opp' is untouched). CR 701.20."""
    if not card.faces:
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                clause = re.sub(r"\([^)]*\)", " ", e.raw) if e.raw else text
                if (
                    e.category == "tap"
                    and not (e.subject is not None and e.subject.controller == "opp")
                    and _TAP_OPP_CONTROL_P.run(clause) is not None
                    and _EACH_PLAYER_P.run(clause) is None
                ):
                    new_effs.append(
                        replace(e, subject=_tap_subject_opp(e.subject, clause))
                    )
                    changed = True
                elif (
                    e.category == "skip_step"
                    and e.scope != "opp"
                    and _SKIP_UNTAP_P.run(clause) is not None
                    and _SKIP_OPP_P.run(clause) is not None
                    and _SKIP_SELF_P.run(clause) is None
                ):
                    new_effs.append(replace(e, scope="opp"))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    if not changed:
        return card
    return replace(card, faces=tuple(faces))


# (3) damage_to_opp_matters — a "deals (noncombat) damage to a player / opponent" payoff
#     phase leaves UNSTRUCTURED: a trigger QUOTED inside a granted ability or a token's
#     text (Serpent Generator, Snake Umbra, Helm of the Ghastlord, Arm with Aether,
#     Talon of Pain), or a one-shot ETB / set-in-motion BURST to each opponent (Fanatic
#     of Mogis, Meria's Outrider, Stormbreath Dragon). phase emits no DamageDone trigger
#     for these, so the player recipient survives only in the raw. Synthesize a
#     ``deals_damage`` trigger carrying the DamageToPlayer marker (the same marker
#     project stamps on a NATIVE deals_damage player trigger), so the existing
#     damage_to_opp_matters arm reads STRUCTURE. The detect
#     pattern is the deleted DAMAGE_TO_OPP_MATTERS_REGEX byte-for-byte, so the recovered
#     set == the deleted mirror's; it EXCLUDES "combat damage" (the already-migrated
#     combat_damage_to_opp recipient). CR 119.3 / 120.
# #24e P3 parser-substrate: the noncombat damage-to-a-player payoff reads STRUCTURE.
# when/whenever anchor + bounded gap + "deals [noncombat] damage to <player recipient>".
# "a player" subsumes "a player or planeswalker" (leftmost-alternation). CR 119.3 / 120.
_DAMAGE_TO_OPP_PAYOFF_P = comb.scan(
    comb.seq(
        comb.keyword({"when", "whenever"}),
        comb.bounded_scan(
            comb.seq(
                comb.keyword({"deals"}),
                comb.opt(comb.keyword({"noncombat"})),
                comb.phrase({"damage"}, {"to"}),
                comb.alt(
                    comb.phrase({"a"}, {"player"}),
                    comb.phrase({"an"}, {"opponent"}),
                    comb.phrase({"one"}, {"of"}, {"your"}, {"opponents"}),
                    comb.phrase({"each"}, {"opponent"}),
                    comb.phrase({"target"}, {"opponent"}),
                    comb.phrase({"that"}, {"player"}),
                ),
            )
        ),
    )
)
_DAMAGE_TO_PLAYER_MARKER = Filter(predicates=("DamageToPlayer",))


def _recover_damage_to_opp(card: Card, oracle: str) -> Card:
    """Append a synthetic ``deals_damage`` (DamageToPlayer) Trigger ability when the raw
    oracle names a non-combat "deals damage to a player/opponent" payoff that phase left
    wholly unstructured, so damage_to_opp_matters reads STRUCTURE. Deduped against a
    NATIVE deals_damage / combat_damage player trigger (a fully-structured card is
    untouched). CR 119.3."""
    if not card.faces:
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "damage to" not in stripped.lower():  # cheap dispatch.
        return card
    if _DAMAGE_TO_OPP_PAYOFF_P.run(stripped) is None:
        return card
    if any(
        ab.trigger is not None
        and ab.trigger.event in ("deals_damage", "combat_damage")
        and ab.trigger.subject is not None
        and "DamageToPlayer" in ab.trigger.subject.predicates
        for ab in card.all_abilities()
    ):
        return card
    synth = Ability(
        kind="triggered",
        trigger=Trigger(event="deals_damage", subject=_DAMAGE_TO_PLAYER_MARKER),
        effects=(Effect(category="other", raw=stripped.strip()),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# ── ADR-0027 #24i (SIDECAR v58) — SUPPLEMENT_RECOVER D1 ───────────────────────
# (1) hand_disruption — an opponent reveals / you look at an opponent's hand, the
#     hand-disruption build-around tell. phase emits the structure THREE ways the
#     existing scope-gated reveal_hand arm misses, plus drops/folds it on a tail:
#       • a MODAL reveal-opponent-hand ("Choose one — Target opponent reveals their
#         hand", Mardu Charm, Collective Brutality, Auntie's Sentence, Doomfall,
#         Cerebral Confiscation, Shatter Assumptions) — phase keeps a `reveal_hand`
#         Effect whose SUBJECT Filter is controller='opp' but the mode loses the
#         scope, so it lands scope='any' and the arm (which needs scope=='opp')
#         skips it. Recover scope='opp' off the subject controller (bucket A).
#       • a `reveal` (NOT reveal_hand) scope='opp' whose raw says "<player> reveals
#         their hand" (Alhammarret, Psychotic Episode) — phase typed the hand reveal
#         as a generic reveal. Re-categorize to reveal_hand (bucket A).
#       • a `topdeck_select` scope='opp' mis-categorized look-at-an-opponent's-hand
#         peek ("look at an opponent's hand, then choose a card name", Anointed
#         Peacekeeper, Sorcerous Spyglass) — re-categorize to reveal_hand (bucket A).
#     A folded/dropped tail (Thoughtcutter Agent's reveal folded into the lose_life
#     effect, Sen Triplets' / Wandering Eye's "plays with their hand(s) revealed"
#     restriction, Arachne's dropped look-at-hand, The Raven's Warning's Saga-chapter
#     combat-damage hand peek) survives only in the raw oracle: synth a reveal_hand
#     scope='opp' from it (bucket B), guarded so a card already carrying an opp-
#     directed reveal_hand / reveal_hands is untouched. The detect pattern is the
#     deleted hand_disruption mirror byte-for-byte, so the recovered set == the
#     mirror's. CR 402.3 / 701.x.
# #24e P3 parser-substrate: the hand-disruption tells read STRUCTURE. The possessive
# `…'?s?'?` folds under norm ("opponent's" → "opponents"), so the noun slots accept the
# possessive/plural form. `[^.]*` gaps → bounded_scan. `(\w+ )?cards?` → an alt that
# tries "card" directly, else one filler word then "card" (regex backtracking). The
# "their|his or her" possessive-pronoun bag recurs. CR 402.3 / 701.x.
_HD_HIS_THEIR = comb.alt(comb.keyword({"their"}), comb.phrase({"his"}, {"or"}, {"her"}))
_HD_REVEAL_HAND_TEXT_P = comb.scan(
    comb.seq(
        comb.keyword({"reveal", "reveals"}),
        _HD_HIS_THEIR,
        comb.keyword({"hand", "hands"}),
    )
)
_HD_LOOK_HAND_TEXT_P = comb.scan(
    comb.seq2(
        comb.phrase({"look"}, {"at"}),
        comb.bounded_scan(comb.keyword({"hand", "hands"})),
    )
)
# The opponent-directed hand-disruption oracle tell (the deleted mirror, verbatim).
_HD_OPP_HAND_P = comb.scan(
    comb.alt(
        comb.seq(
            comb.phrase({"look"}, {"at"}),
            comb.alt(
                comb.phrase({"target"}, {"player", "players"}),
                comb.phrase({"that"}, {"player", "players"}),
                comb.phrase({"an"}, {"opponent", "opponents"}),
                comb.phrase({"each"}, {"opponent", "opponents"}),
                comb.phrase({"target"}, {"opponent", "opponents"}),
            ),
            comb.keyword({"hand", "hands"}),
        ),
        comb.seq(
            comb.keyword({"play", "plays"}),
            comb.keyword({"with"}),
            _HD_HIS_THEIR,
            comb.keyword({"hand", "hands"}),
            comb.keyword({"revealed"}),
        ),
        comb.seq(
            comb.keyword({"reveal", "reveals"}),
            _HD_HIS_THEIR,
            comb.keyword({"hand", "hands"}),
        ),
        comb.seq(
            comb.keyword({"reveal", "reveals"}),
            comb.alt(
                comb.keyword({"card", "cards"}),
                comb.seq2(comb.word(), comb.keyword({"card", "cards"})),
            ),
            comb.opt(comb.phrase({"at"}, {"random"})),
            comb.keyword({"from"}),
            comb.alt(
                comb.keyword({"their"}),
                comb.phrase({"his"}, {"or"}, {"her"}),
                comb.phrase({"that"}, {"players"}),
            ),
            comb.keyword({"hand"}),
        ),
        comb.seq2(
            comb.keyword({"reveal", "reveals"}),
            comb.bounded_scan(comb.phrase({"until"}, {"you"}, {"say"}, {"stop"})),
        ),
    )
)


def _recover_hand_disruption(card: Card, oracle: str) -> Card:
    """Recover the opponent-hand-reveal structure so the scope-gated reveal_hand arm
    fires: scope='opp' off a modal reveal_hand's opp subject, a generic `reveal` /
    `topdeck_select` opp hand-peek re-categorized to reveal_hand (bucket A), and a
    synth reveal_hand scope='opp' for the folded/dropped tail (bucket B, guarded
    against an existing opp-directed reveal_hand / reveal_hands). CR 402.3 / 701.x."""
    if not card.faces:
        return card

    def has_opp_reveal(c: Card) -> bool:
        return any(
            (e.category == "reveal_hand" and e.scope == "opp")
            or e.category == "reveal_hands"
            for ab in c.all_abilities()
            for e in ab.effects
        )

    changed = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                raw = e.raw or ""
                if (
                    e.category == "reveal_hand"
                    and e.scope != "opp"
                    and isinstance(e.subject, Filter)
                    and e.subject.controller == "opp"
                ):
                    new_effs.append(replace(e, scope="opp"))
                    changed = True
                elif e.scope == "opp" and (
                    (
                        e.category == "reveal"
                        and _HD_REVEAL_HAND_TEXT_P.run(raw) is not None
                    )
                    or (
                        e.category == "topdeck_select"
                        and _HD_LOOK_HAND_TEXT_P.run(raw) is not None
                    )
                ):
                    new_effs.append(replace(e, category="reveal_hand"))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    card = replace(card, faces=tuple(faces)) if changed else card

    # bucket B — synth from the raw oracle the folded/dropped tail phase emits no
    # opp-directed reveal node for (append-only; an existing opp reveal short-circuits).
    if not has_opp_reveal(card):
        stripped = re.sub(r"\([^)]*\)", " ", oracle)
        low = stripped.lower()
        if ("reveal" in low or "look at" in low) and _HD_OPP_HAND_P.run(
            stripped
        ) is not None:
            synth = Ability(
                kind="static",
                effects=(
                    Effect(category="reveal_hand", scope="opp", raw=stripped.strip()),
                ),
            )
            head, *rest = card.faces
            card = replace(
                card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
            )
    return card


# (2) keyword_grant_target — a spell/ability grants a keyword to a SINGLE TARGET
#     creature ("target creature gains menace until end of turn"). The structural
#     single_target_grant arm reads phase's clean ParentTarget AddKeyword markers;
#     phase drops the target on a tail it folds into a bare `grant_keyword`
#     (subject=None): a MODAL grant (Adaptive Sporesinger, Appa, Balloon Stand,
#     Ferocification, Retreat to Hagra), a grant QUOTED on an Aura / land / planes-
#     walker ("Enchanted land has '{T}: Target creature gains haste'", Racecourse
#     Fury, Skygames, Footfall Crater, Rowan's Talent), a compound quoted grant
#     (Infuse with Vitality), a Saga-chapter grant (Rediscover the Way), and Chariot
#     of the Sun (routed to base_pt_set). For those the "target creature gains <kw>"
#     survives only in the raw oracle, so synth a single_target_grant Effect (the
#     resolved Creature subject + the SingleTarget predicate, faithful controller +
#     granted keyword in counter_kind) so the arm reads STRUCTURE. The detect pattern
#     is the deleted KEYWORD_GRANT_TARGET mirror byte-for-byte. The split/aftermath
#     BACK-HALF grants (Claim//Fame's "Fame", Onward//Victory's "Victory") are a
#     GENUINE UPSTREAM phase gap — phase emits NO record for a split back face, so the
#     phase-records oracle this recovery reads never carries them; a narrow layout-
#     gated residue in signals keeps those two. CR 700.2 / 702.x.
# #24e P3 parser-substrate: the single-target keyword grant reads STRUCTURE. The value
# threads out (controller-flag, keyword) — controller "you" iff "you control" rode the
# target, keyword folded to its no-space form ("double strike" → "doublestrike"). The
# `gets ±N/±M and gains` arm reads the sign-bearing P/T delta off the raw word (norm
# folds the sign, so `_KGT_PT_DELTA` checks the raw). Iterated via `_iter_spans`
# (the regex finditer). CR 700.2 / 702.x.
_KGT_PT_DELTA_RE = re.compile(r"[+\-][0-9x]/[+\-][0-9x]", re.IGNORECASE)
_KGT_PT_DELTA = comb.Parser(
    lambda s: (
        r
        if (r := comb.word().run(s)) is not None and _KGT_PT_DELTA_RE.match(r[0])
        else None
    )
)
_KGT_VERB = comb.alt(
    comb.keyword({"gain", "gains"}),
    comb.seq(
        comb.keyword({"gets"}),
        _KGT_PT_DELTA,
        comb.keyword({"and"}),
        comb.keyword({"gain", "gains"}),
    ),
)
_KGT_KW = comb.alt(
    comb.value("doublestrike", comb.phrase({"double"}, {"strike"})),
    comb.value("firststrike", comb.phrase({"first"}, {"strike"})),
    comb.keyword(
        {
            "deathtouch",
            "trample",
            "flying",
            "menace",
            "vigilance",
            "lifelink",
            "haste",
            "hexproof",
            "indestructible",
            "protection",
            "reach",
            "ward",
            "shroud",
        }
    ),
)
_KGT_GRANT_P = comb.seq(
    comb.phrase({"target"}, {"creature"}),
    comb.opt(comb.phrase({"you"}, {"control"})),
    _KGT_VERB,
    _KGT_KW,
)
_KGT_SINGLE_TARGET_PRED = "SingleTarget"


def _recover_keyword_grant_target(card: Card, oracle: str) -> Card:
    """Append synthetic ``single_target_grant`` Effects for the single-target keyword
    grants phase folded to a bare grant_keyword (modal / quoted-on-Aura-or-land /
    Saga-chapter) so the keyword_grant_target arm reads STRUCTURE. Append-only: a card
    already carrying a single_target_grant (phase's clean ParentTarget marker) is left
    alone. The split/aftermath back-half grants are out of reach here (no phase record
    for the back face — upstream gap); a signals layout residue keeps them. CR 700.2."""
    if not card.faces:
        return card
    if any(
        e.category == "single_target_grant"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    if "target creature" not in text.lower():  # cheap dispatch — every match needs it.
        return card
    synth_effs: list[Effect] = []
    seen: set[str] = set()
    for clause, value in _iter_spans(text, _KGT_GRANT_P):
        if clause.lower() in seen:
            continue
        seen.add(clause.lower())
        controller = "you" if value[1] is not None else "any"
        kw = value[3]
        synth_effs.append(
            Effect(
                category="single_target_grant",
                scope=controller,
                subject=Filter(
                    card_types=("Creature",),
                    controller=controller,
                    predicates=(_KGT_SINGLE_TARGET_PRED,),
                ),
                raw=clause.strip(),
                counter_kind=kw,
            )
        )
    if not synth_effs:
        return card
    synth = Ability(kind="static", effects=tuple(synth_effs))
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# ── ADR-0027 #24k (SIDECAR v59) — SUPPLEMENT_RECOVER D2 ───────────────────────
# (1) opponent_cast_matters — the genuinely OPPONENT-scoped "whenever an opponent
#     casts a spell" punisher/tax. phase scopes a DIRECT "whenever an opponent
#     casts" trigger correctly (scope='opp' — Lavinia, Nekusar), but when the
#     trigger is QUOTED inside a granted/emblem/Saga-token ability it FOLDS the
#     clause into a non-trigger Effect (a `creature_cast` static, a `cheat_play`,
#     an `emblem`, a `place_counter`) and emits NO cast_spell trigger at all —
#     Hunting Grounds (threshold-granted), Jace, Unraveler of Secrets (emblem),
#     Thundering Mightmare (soulbond-granted), Blink (Saga token). The opponent
#     scope survives only in the raw, so synthesize a cast_spell trigger scope='opp'
#     (the _recover_damage_to_opp precedent). The detect pattern is the OPPONENT-only
#     phrase "whenever an opponent casts" — it must NOT match the SYMMETRIC "whenever
#     a player casts" (CR 102.1 "a player" includes its controller — Eidolon of the
#     Great Revel, Pyrostatic Pillar, Ruric Thar punish EVERYONE, not opponents
#     only; CR 102.2/102.3 "an opponent" excludes you). The deleted regex mirror
#     over-swept the symmetric "a player casts … punish that player" half; deleting
#     it drops those 17 symmetric punishers (genuine non-members of an opponent-
#     scoped lane), and this recovery keeps the 4 genuinely-opponent quoted grants
#     firing STRUCTURALLY. CR 601 / 603.2 / 102.2.
# #24e P2 parser-substrate: DETECTION is a `_combinators` scan —
# `scan(phrase({"whenever"}, {"an"}, {"opponent"}, {"cast","casts"}))` — a WHOLE-WORD
# four-slot read. The "an opponent" slot is the clean bag discriminator that keeps the
# SYMMETRIC "whenever a player casts" (CR 102.1) OUT (no "an opponent"). Ports to
# phase-rs as nom `tuple((tag("whenever"), tag("an"), tag("opponent"), alt((tag("cast"),
# tag("casts")))))`. CR 603.2 / 102.2.
_OPP_CAST_TRIGGER = comb.scan(
    comb.phrase({"whenever"}, {"an"}, {"opponent"}, {"cast", "casts"})
)


def _recover_opponent_cast_scope(card: Card, oracle: str) -> Card:
    """Append a synthetic ``cast_spell`` Trigger scope='opp' when the raw oracle names
    a "whenever an opponent casts" trigger phase folded into a non-trigger Effect (a
    quoted/granted/emblem/Saga-token ability), so opponent_cast_matters reads STRUCTURE.
    Deduped against a NATIVE opponent-scoped cast_spell trigger (a card phase already
    scoped scope='opp' — Lavinia — is untouched). The SYMMETRIC "a player casts" is NOT
    matched (CR 102.1 — symmetric, not opponent-only). CR 603.2 / 102.2."""
    if not card.faces:
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if not _anchored(stripped, "opponent cast", _OPP_CAST_TRIGGER):
        return card
    if any(
        ab.trigger is not None
        and ab.trigger.event == "cast_spell"
        and ab.trigger.scope == "opp"
        for ab in card.all_abilities()
    ):
        return card
    synth = Ability(
        kind="triggered",
        trigger=Trigger(event="cast_spell", scope="opp"),
        effects=(Effect(category="other", raw=stripped.strip()),),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# (2) tribe_damage_trigger — a go-wide "[creatures/a tribe] you control deal combat
#     damage to a player → reward" payoff. project stamps the DamageDone trigger's
#     valid_source (project → trig.source), but phase DROPS the source when the trigger
#     is QUOTED inside a loyalty / emblem / delayed ability — Vraska, Golgari Queen
#     (emblem), Dovin, Jace Cunning Castaway, Kaito Shizuki, Mistway Spy, Popular
#     Entertainer, Surge to Victory, The Girl in the Fireplace, Flitterwing Nuisance —
#     so the combat_damage trigger lands source=None and the tribe_damage_trigger arm
#     (which requires a Creature/subtype YOUR source) skips it. Recover source=Filter(
#     Creature, controller=you) onto a source-None combat_damage trigger with a PLAYER
#     recipient when the raw names "creatures you control deal combat damage to a
#     player". (The AnyOf-subtype OUTLAW source — Olivia — and the deals_damage tribal
#     source — Francisco — are CAPTURED by phase; the signals arm broadens to read those
#     shapes, no supplement needed.) CR 603.2 / 510.1b.
# #24e P3 parser-substrate: the YOUR-creatures combat-damage-to-a-player tell reads
# STRUCTURE — a fixed seven-slot read with a quantity bag and a player-recipient bag.
# CR 603.2 / 510.1b.
_TRIBE_CDMG_SRC_P = comb.scan(
    comb.seq(
        comb.keyword({"whenever"}),
        comb.alt(comb.keyword({"a"}), comb.phrase({"one"}, {"or"}, {"more"})),
        comb.keyword({"creature", "creatures"}),
        comb.phrase({"you"}, {"control"}),
        comb.keyword({"deal", "deals"}),
        comb.phrase({"combat"}, {"damage"}, {"to"}),
        comb.alt(
            comb.phrase({"a"}, {"player"}),
            comb.phrase({"an"}, {"opponent"}),
            comb.phrase({"one"}, {"of"}, {"your"}, {"opponents"}),
            comb.phrase({"each"}, {"opponent"}),
        ),
    )
)


def _recover_tribe_damage_source(card: Card, oracle: str) -> Card:
    """Stamp source=Filter(Creature, controller=you) on a combat_damage trigger phase
    left source=None (quoted in a loyalty / emblem / delayed ability) when the raw names
    a "creatures you control deal combat damage to a player" payoff, so
    tribe_damage_trigger reads STRUCTURE. Gated to a PLAYER recipient (the lane needs a
    reward-on-connect-to-a-player shape). Idempotent (a trigger already with a source
    is untouched). CR 603.2 / 510.1b."""
    if not card.faces:
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "combat damage to" not in stripped.lower():  # cheap dispatch.
        return card
    if _TRIBE_CDMG_SRC_P.run(stripped) is None:
        return card
    src = Filter(card_types=("Creature",), controller="you")
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            t = ab.trigger
            if (
                t is not None
                and t.event == "combat_damage"
                and t.source is None
                and "player" in t.recipient
            ):
                new_abs.append(replace(ab, trigger=replace(t, source=src)))
                changed = True
            else:
                new_abs.append(ab)
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card


# (3) topdeck_stack — self-library-top curation (look-then-stack / graveyard→top /
#     hand→top recursion). phase structures the put-on-top as a `topdeck_stack` Effect
#     (counter_kind 'top'/'topbottom') but DROPS the controller, landing subject=None —
#     so the structural arm's controller==you gate skips it (Ancestral Knowledge, Orcish
#     Librarian, Scroll Rack, Doomsday, Rowan's Grim Search, plus the broader self-top-
#     stack set the narrow mirror missed — Mortuary, Cream of the Crop, Thassa's Oracle,
#     …). Recover the SELF controller: stamp subject=Filter(Card, controller=you) (the
#     shape phase's CLEANLY-parsed self top-stacks already carry — Brainstorm) on a
#     subject-None top-stack whose OWN clause names "on top of your library" (the self
#     anchor — an opponent tuck "on top of their owner's library" is excluded). PARTIAL:
#     a self-curation phase FOLDED to topdeck_select-to-hand with NO topdeck_stack
#     Effect (Diabolic Vision), a "put a card from your hand on top" ACTIVATION COST
#     (Hidden Retreat, Leashling, Penance), or a dropped-clause look-then-stack (Munda)
#     is not structurally recoverable → the kept mirror stays for those. CR 401.
# #24e P2 parser-substrate: the SELF top-stack tell is a `_combinators` scan over the
# deleted regex's two alternations — `scan(alt(phrase("on","top","of","your","library"),
# phrase("top","of","your","library","in","any","order")))` — WHOLE-WORD ("library"
# never matches inside "libraries"). Ports to phase-rs as nom `alt`. CR 401.
_TOPDECK_STACK_SELF = comb.scan(
    comb.alt(
        comb.phrase({"on"}, {"top"}, {"of"}, {"your"}, {"library"}),
        comb.phrase({"top"}, {"of"}, {"your"}, {"library"}, {"in"}, {"any"}, {"order"}),
    )
)


def _topdeck_stack_self(clause: str) -> bool:
    """A SELF top-stack tell ("on top of your library" / "top of your library in any
    order") anywhere in ``clause`` (whole-word)."""
    return (
        "top of your library" in clause.lower()
        and _TOPDECK_STACK_SELF.run(clause) is not None
    )


def _recover_topdeck_stack_self(card: Card, oracle: str) -> Card:
    """Stamp subject=Filter(Card, controller=you) on a subject-None ``topdeck_stack``
    Effect (counter_kind 'top'/'topbottom') whose clause names a SELF top-stack ("on top
    of your library"), so the topdeck_stack arm reads STRUCTURE. Per-effect (each reads
    its OWN clause raw; falls back to the oracle only when phase dropped that raw).
    Idempotent (a top-stack already controller==you is untouched). CR 401."""
    if not card.faces:
        return card
    text = re.sub(r"\([^)]*\)", " ", oracle)
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                clause = re.sub(r"\([^)]*\)", " ", e.raw) if e.raw else text
                if (
                    e.category == "topdeck_stack"
                    and e.counter_kind in ("top", "topbottom")
                    and (e.subject is None or e.subject.controller != "you")
                    and _topdeck_stack_self(clause)
                ):
                    new_effs.append(
                        replace(
                            e,
                            subject=Filter(card_types=("Card",), controller="you"),
                        )
                    )
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card


# ── ADR-0027 #24l (SIDECAR v60) — SUPPLEMENT_RECOVER E1 (low-residue tail) ─────
# (1) extra_land_drop — the YOUR "put a land card from your hand / among the dug-or-
#     cascaded cards onto the battlefield" put phase FOLDS off cat=='cheat_play':
#     phase emits cat=='reanimate' for the cascade-from-exile put (Averna), buries the
#     dig put inside the cat=='exile' / cat=='topdeck_select' effect raw (Aminatou's
#     Augury, Planar Genesis — mis-zoned to:hand), folds it into a draw's raw
#     (Contaminant Grafter), drops the d20-branch put (Journey to the Lost City), or
#     leaves the modal Confluence cheat_play Land controller='any' + EMPTY raw
#     (Riveteers Confluence — the "or graveyard" disjunction defeats phase's YOUR pin).
#     The dropped structure (a YOUR land-into-play put) survives in the joined oracle,
#     so synthesize a canonical cheat_play Effect (Land subject, controller='you') the
#     extra_land_drop arm already reads — the _recover_combat_damage_recipients
#     precedent. The detect pattern is the EXACT deleted signals mirror regex (the
#     source-restricted "you may put … land card from your hand|among them|among those
#     cards|among the exiled cards … onto the battlefield"), so the recovered set is
#     byte-identical to the deleted mirror and the symmetric "each player may put …
#     from their hand" group ramp (Kynaios, Hypergenesis, Tempting Wurm) never matches
#     (it lacks the YOUR "you may put"). The whole mirror retires. CR 305.9 / 720.
# #24e P3 parser-substrate: the YOUR land-into-play put reads STRUCTURE. The optional
# quantity is "a" or "up to <word>"; the source is one of four fixed phrases; the gap
# gap to "onto the battlefield" → bounded_scan. CR 305.9 / 720.
_EXTRA_LAND_DROP_PUT_P = comb.seq(
    comb.phrase({"you"}, {"may"}, {"put"}),
    comb.opt(
        comb.alt(
            comb.keyword({"a"}),
            comb.seq2(comb.phrase({"up"}, {"to"}), comb.word()),
        )
    ),
    comb.keyword({"land", "lands"}),
    comb.keyword({"card", "cards"}),
    comb.keyword({"from"}),
    comb.alt(
        comb.phrase({"your"}, {"hand"}),
        comb.phrase({"among"}, {"them"}),
        comb.phrase({"among"}, {"those"}, {"cards"}),
        comb.phrase({"among"}, {"the"}, {"exiled"}, {"cards"}),
    ),
    comb.bounded_scan(comb.phrase({"onto"}, {"the"}, {"battlefield"})),
)


def _recover_extra_land_drop(card: Card, oracle: str) -> Card:
    """Append a synthetic ``cheat_play`` Effect (Land subject, controller='you') for the
    YOUR land-into-play put phase folds off cat=='cheat_play' — a cascade-from-exile
    reanimate (Averna), a dig-into-play buried in an exile/topdeck_select raw
    (Aminatou's Augury, Planar Genesis), a draw-raw fold (Contaminant Grafter), a
    dropped d20 branch (Journey to the Lost City), or a modal Confluence cheat_play Land
    controller='any' with empty raw (Riveteers). Append-only; skipped when the card
    already carries a cheat_play Land controller='you' put (the shape the arm reads).
    The synthetic Effect carries only zones=('to:battlefield',) so it fires
    extra_land_drop alone (other cheat_play readers gate on from:graveyard/top:you)."""
    if not card.faces:
        return card
    if any(
        e.category == "cheat_play"
        and isinstance(e.subject, Filter)
        and "Land" in e.subject.card_types
        and e.subject.controller == "you"
        for ab in card.all_abilities()
        for e in ab.effects
    ):
        return card
    stripped = re.sub(r"\([^)]*\)", " ", oracle)
    if "you may put" not in stripped.lower():  # cheap dispatch — the lead phrase.
        return card
    span = _scan_span(stripped, _EXTRA_LAND_DROP_PUT_P)
    if span is None:
        return card
    synth = Ability(
        kind="static",
        effects=(
            Effect(
                category="cheat_play",
                scope="you",
                subject=Filter(card_types=("Land",), controller="you"),
                zones=("to:battlefield",),
                raw=span,
            ),
        ),
    )
    head, *rest = card.faces
    return replace(
        card, faces=(replace(head, abilities=(*head.abilities, synth)), *rest)
    )


# (2) group_hug_draw — the symmetric "each player draws" card-advantage scope phase
#     FOLDS to scope=='any' when the draw amount is variable (Grothama, All-Devouring's
#     "each player draws cards equal to the amount of damage …") or lives in a d20
#     branch (Mathise, Surge Channeler's "1—9 | Each player draws a card."). phase's
#     accurately-scoped each-draw (Howling Mine, Prosperity) already fires the lane
#     STRUCTURALLY; this re-stamps scope='each' on the folded ones — reading the draw's
#     OWN clause raw, so only an "each player draws" draw is retagged (a sibling "you
#     draw a card" branch keeps its scope). The retag pulls Grothama/Mathise OUT of
#     target_player_draws (a directed-draw lane scope=='any' feeds): an "each player
#     draws" is a symmetric group-hug, never a player-DIRECTED draw, so the move is a
#     correct reclassification, not a loss. The coin-flip branch that emits NO draw
#     Effect (Winter Sky) and the Saga-chapter collapse to a 'Chapter N' raw (Vault 11)
#     leave no draw raw to read — those stay on the narrowed signals residue mirror
#     (UPSTREAM phase folds). CR 121 / 120.2.
# #24e P2 parser-substrate: the symmetric each-player-draws tell is a `_combinators`
# scan over the deleted regex's two alternations (the optional "may" is a separate arm,
# `draws?` → {draw, draws}) — WHOLE-WORD ("draws" never matches inside "drawstep").
# Ports to phase-rs as nom `alt`. CR 121.
_GROUP_HUG_DRAW = comb.scan(
    comb.alt(
        comb.phrase({"each"}, {"player"}, {"draw", "draws"}),
        comb.phrase({"each"}, {"player"}, {"may"}, {"draw", "draws"}),
        comb.phrase({"each"}, {"player"}, {"who"}, {"drew"}),
        # v0.8.0 ROOT F — the symmetric wheel "each player who does draws seven
        # cards" (Step Between Worlds, Turtles in Time). phase scopes the draw
        # 'opp' (the "each player who does" relative clause loses its 'each'
        # scope), so _recover_group_hug_draw_scope re-stamps scope='each' off
        # this tell. "who does draw(s)" is the present-tense companion of the
        # "who drew" past-tense arm above. CR 121.
        comb.phrase({"each"}, {"player"}, {"who"}, {"does"}, {"draw", "draws"}),
    )
)


def _group_hug_draw(raw: str) -> bool:
    """A symmetric "each player [may] draw(s)" / "each player who drew" tell anywhere in
    ``raw`` (whole-word)."""
    return "each player" in raw.lower() and _GROUP_HUG_DRAW.run(raw) is not None


def _recover_group_hug_draw_scope(card: Card) -> Card:
    """Re-stamp scope='each' on a ``draw`` Effect whose OWN raw names a symmetric "each
    player draws" but which phase folded to scope!='each' (a variable amount — Grothama
    — or a d20 branch — Mathise). Reads the effect raw (not oracle), so a Saga-chapter
    'Chapter N' raw / a coin-flip with no draw Effect is left for the residue mirror.
    Idempotent (a draw already scope=='each' is untouched). CR 121."""
    if not card.faces:
        return card
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                if (
                    e.category == "draw"
                    and e.scope != "each"
                    and e.raw
                    and _group_hug_draw(e.raw)
                ):
                    new_effs.append(replace(e, scope="each"))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card


# ── ROOT C residual — modal mass-EXILE phase leaves Unimplemented ──────────────
# The Vote.per_choice_effect descend (project.py, SIDECAR v69) reads every VOTE card's
# outcomes natively, retiring the 5-arm _recover_vote_outcome. The one residual it
# can't reach is the CHOOSE-carrier modal "Each player chooses a color. Then exile each
# permanent unless …" (Selective Obliteration): phase emits the mass-exile as an
# Unimplemented unless-clause (CR 614 gap) under a `choose` carrier — there is no
# per_choice_effect to descend. Re-synthesize the mass `exile` Effect from the carrier
# raw so mass_removal reads it (the lone surviving arm of the deleted regex; the
# _VOTE_EXILE_EACH pattern + Effect shape preserved verbatim). Append-only: skip a card
# already carrying an exile (incl. one the descend produced). CR 701.38a.
_MODAL_MASS_EXILE = re.compile(
    r"exile (?:each|all) (?:nonland )?permanents?\b", re.IGNORECASE
)


def _recover_modal_mass_exile(card: Card) -> Card:
    if not card.faces:
        return card
    if any(e.category == "exile" for ab in card.all_abilities() for e in ab.effects):
        return card
    for face in card.faces:
        for ab in face.abilities:
            for e in ab.effects:
                if e.category not in ("vote", "choose") or not e.raw:
                    continue
                m = _MODAL_MASS_EXILE.search(e.raw)
                if m is None:
                    continue
                synth = Ability(
                    kind="spell",
                    effects=(
                        Effect(
                            category="exile",
                            scope="you",
                            counter_kind="all",
                            subject=Filter(card_types=("Permanent",)),
                            zones=("to:exile",),
                            raw=e.raw[m.start() :],
                        ),
                    ),
                )
                head, *rest = card.faces
                return replace(
                    card,
                    faces=(replace(head, abilities=(*head.abilities, synth)), *rest),
                )
    return card


# ── v0.8.0 bump ROOT D — "discard a card unless <alt>" residue ─────────────────
# phase v0.8.0 reparses a "Draw N cards. Then discard a card unless <non-discard
# alternative>" loot/rummage clause into TWO `draw` Effects — the real one (carrying
# the amount + clause_raw) and a DEGENERATE empty draw fragment (no amount, no
# clause_raw) whose raw still holds the whole sentence: the discard branch (CR 701.9:
# discard = hand → graveyard) is dropped to a phantom draw. The self-discard fuel
# (discard_outlet) and the draw+discard loot co-occurrence (discard_matters) both
# vanish. This pass converts that degenerate sibling draw back into the `discard`
# Effect it misparses (scope you — a self-loot), so discard_outlet reads the discard
# structurally and the loot arm (draw + discard in one ability) re-opens
# discard_matters. Gated to the misparse shape: an ability with a REAL draw (amount /
# clause_raw) AND a degenerate amount-less draw whose raw matches "discard <n> card(s)
# unless", and no `discard` Effect already present. CR 701.9 / 701.50.
_DISCARD_UNLESS = re.compile(
    r"discard (?:a|an|one|two|three|four|five|x|\d+) cards? unless", re.IGNORECASE
)


def _recover_discard_unless(card: Card) -> Card:
    """Convert the degenerate empty-draw fragment of a "draw N, then discard a card
    unless …" clause back into the `discard` Effect (scope you) phase dropped, so the
    discard_outlet / discard_matters loot lanes read STRUCTURE. Gated to the v0.8.0
    misparse shape (real draw + amount-less duplicate draw whose raw is a "discard …
    unless"); a card already carrying a `discard` Effect in that ability is left alone.
    CR 701.9."""
    if not card.faces:
        return card
    faces: list[Face] = []
    changed = False
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            cats = {e.category for e in ab.effects}
            draws = [e for e in ab.effects if e.category == "draw"]
            has_real = any(e.amount is not None or e.clause_raw for e in draws)
            degen = next(
                (
                    e
                    for e in draws
                    if e.amount is None
                    and not e.clause_raw
                    and _DISCARD_UNLESS.search(e.raw or "")
                ),
                None,
            )
            if "discard" in cats or not has_real or degen is None:
                new_abs.append(ab)
                continue
            m = _DISCARD_UNLESS.search(degen.raw or "")
            assert m is not None
            new_effs = tuple(
                Effect(
                    category="discard",
                    scope="you",
                    subject=Filter(controller="you"),
                    raw=(degen.raw or "")[m.start() :],
                )
                if e is degen
                else e
                for e in ab.effects
            )
            new_abs.append(replace(ab, effects=new_effs))
            changed = True
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card


# ── v0.8.0 ROOT G — self_counter_grow self-anchor / anthem discriminator ──────
# phase v0.8.0 regressed the +1/+1 enters-with replacement on two axes: (1) it NULLS
# the SelfRef self-anchor on a genuine "~ enters with X +1/+1 counters on it" body
# (Naya Soulbeast, Pyretic Hunter, Lurking Automaton, Cogwork Grinder) — the
# self-grow creature the lane wants; (2) it WRONGLY stamps the SelfRef marker on an
# ANTHEM static "creatures you control enter with … counters on them" (Bard Class,
# Curator Beastie) whose entering set is OTHER creatures, not the source. project's
# valid_card clearing (CR 614.13) used to split these. This pass restores the split
# off the effect raw: stamp the marker on the self body, clear it on the anthem, so
# the self_counter_grow arm (which keys on the marker) reads the right membership.
# CR 614.13c (the object enters with the counters) / 122.1.
_SELF_GROW_ENTERS = re.compile(
    r"~ enters with [^.]*\+1/\+1 counters? on it\b", re.IGNORECASE
)
_ANTHEM_ENTERS = re.compile(
    r"creatures you control enter with [^.]*\+1/\+1 counters? on them\b",
    re.IGNORECASE,
)


def _recover_self_counter_grow(card: Card) -> Card:
    """Re-anchor the +1/+1 enters-with replacement: stamp the SelfRef self-anchor on
    a genuine "~ enters with … on it" body and clear it on a "creatures you control
    enter with … on them" anthem. Reads the place_counter effect's OWN raw; gated to
    the p1p1 kind. Idempotent (a body already marked / an anthem already clear is
    untouched)."""
    if not card.faces:
        return card
    marker = Filter(predicates=("SelfRef",))
    changed = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                if e.category == "place_counter" and e.counter_kind == "p1p1":
                    raw = e.raw or ""
                    if e.subject is None and _SELF_GROW_ENTERS.search(raw):
                        new_effs.append(replace(e, subject=marker))
                        changed = True
                        continue
                    if e.subject == marker and _ANTHEM_ENTERS.search(raw):
                        new_effs.append(replace(e, subject=None))
                        changed = True
                        continue
                new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card


# ── v0.8.0 ROOT H — destroy subject re-typed Creature ─────────────────────────
# phase v0.8.0 NULLS the subject on both destroy nodes of "Destroy two target
# nonblack creatures unless …" (Dead Ringers) — the "two target … unless" conditional
# defeats the subject parse — so removal (which needs a permanent-type
# subject) drops it. This pass re-types a subjectless single/multi-target destroy as
# Creature when its OWN raw says "destroy … creature(s)", so removal reads
# STRUCTURE. Gated to subject is None + counter_kind != "all" (a board wipe is
# mass_removal, never single-target removal) + a literal "target … creature(s)" in
# the clause — the TARGETED-removal discriminator that keeps the anaphoric combat
# forms phase also nulls ("destroy that creature" / "destroy it" deathtouch-likes —
# Cockatrice, the Basilisks) OUT (those are not single-target removal spells, and
# the v0.8.0 arm correctly never fired them). A non-battlefield zone on the node
# (from:library/to:graveyard) means phase mis-tagged a search-and-mill as `destroy`
# (Life's Finale's "search target opponent's library … creature cards") — gated out
# by ``not e.zones``. A self-destroying form ("Destroy ~ and target creature it's
# blocking" — Wall of Vipers) is excluded too: it sacrifices the source per use, so
# it is not the repeatable creature-removal the lane (and the downstream kill_engine
# membership cross-open) wants — keep it a non-member, matching v0.8.0. CR 701.8
# (destroy) / 115.1.
_DESTROY_CREATURE = re.compile(
    r"\bdestroy\b[^.]*\btarget\b[^.]*\bcreatures?\b", re.IGNORECASE
)
_DESTROY_SELF = re.compile(r"\bdestroy ~(?!\w)", re.IGNORECASE)


def _recover_destroy_subject(card: Card) -> Card:
    """Re-type a subjectless TARGETED destroy as Creature when its raw names a
    target creature, so removal reads STRUCTURE. Gated to subject None +
    non-mass + a literal "target … creature(s)" clause; idempotent."""
    if not card.faces:
        return card
    creature = Filter(card_types=("Creature",))
    changed = False
    faces: list[Face] = []
    for face in card.faces:
        new_abs: list[Ability] = []
        for ab in face.abilities:
            new_effs: list[Effect] = []
            for e in ab.effects:
                if (
                    e.category == "destroy"
                    and e.subject is None
                    and e.counter_kind != "all"
                    and not e.zones
                    and _DESTROY_CREATURE.search(e.raw or "")
                    and not _DESTROY_SELF.search(e.raw or "")
                ):
                    new_effs.append(replace(e, subject=creature))
                    changed = True
                else:
                    new_effs.append(e)
            new_abs.append(replace(ab, effects=tuple(new_effs)))
        faces.append(replace(face, abilities=tuple(new_abs)))
    return replace(card, faces=tuple(faces)) if changed else card
