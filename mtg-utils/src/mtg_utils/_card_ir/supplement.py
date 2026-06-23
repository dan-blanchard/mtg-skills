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
from mtg_utils.card_ir import Ability, Card, Effect, Filter, Quantity

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


# phase tags a line its OWN parser choked on with a diagnostic prefix
# ("Static pattern matched but line failed static parser: <LINE>"); strip it so the
# supplement re-parses the real clause underneath.
_FAILED_PREFIX = re.compile(r"^[^:]*\bline failed\b[^:]*:\s*", re.IGNORECASE)

# ── effect-clause grammar (a composed combinator parser, mirroring phase's
# oracle_dispatch → effect-chain → alt(verb-parsers); NOT a startswith chain). The
# parser consumes any leading trigger/timing/chapter/permission PREFIX, then matches
# the imperative verb at the cursor and yields its category. Built once at import. ──

# A leading clause that PRECEDES the imperative effect — consumed so dispatch lands on
# the verb (phase strips the trigger before parsing the effect the same way). A Saga
# "Chapter N —", a "When/Whenever/At/As … ," trigger/timing clause, "If … ," or a bare
# "you may"/"then" connective. ``opt(many(...))`` peels stacked prefixes.
_CHAPTER_PREFIX = comb.value(
    None, comb.seq3(comb.tag("chapter"), comb.take_until("—"), comb.tag("—"))
)
# An ABILITY WORD ("Ferocious — You gain 4 life", "Adamant — …", "Coven — …") is an
# italic flavour LABEL with no rules meaning (CR 207.2c) — consume it (+ the em-dash)
# so dispatch lands on the effect. Enumerated (a finite, closed set) so it can't eat a
# real clause that happens to contain "—". Any-condition word-words like "if"/"as
# long as" after the dash are peeled by the trigger/duration prefixes in turn.
_ABILITY_WORDS = {
    "adamant",
    "addendum",
    "alliance",
    "battalion",
    "bloodrush",
    "boast",
    # also em-dash-delimited KEYWORD labels (Kicker—Return …, Entwine—Sacrifice …,
    # Exhaust — {4}: …) — same "<label> — <effect/cost>" shape, strip the label.
    "kicker",
    "entwine",
    "exhaust",
    "morph",
    "blitz",
    "celebration",
    "channel",
    "chroma",
    "cohort",
    "constellation",
    "converge",
    "corrupted",
    "coven",
    "delirium",
    "descend",
    "domain",
    "eminence",
    "enrage",
    "fateful",
    "ferocious",
    "flurry",
    "formidable",
    "grandeur",
    "hellbent",
    "heroic",
    "imprint",
    "inspired",
    "join",
    "kinship",
    "landfall",
    "lieutenant",
    "magecraft",
    "metalcraft",
    "morbid",
    "pack",
    "parley",
    "radiance",
    "raid",
    "rally",
    "revolt",
    "secret",
    "spell",
    "strive",
    "sweep",
    "tempting",
    "threshold",
    "undergrowth",
    "valiant",
    "void",
    "will",
}
_ABILITY_WORD_PREFIX = comb.value(
    None,
    comb.seq3(comb.keyword(_ABILITY_WORDS), comb.take_until("—"), comb.tag("—")),
)
_TRIGGER_PREFIX = comb.value(
    None,
    comb.seq3(
        comb.keyword({"when", "whenever", "at", "as", "if"}),
        comb.take_until(","),
        comb.tag(","),
    ),
)
# A replacement-timing wrapper ("The next time … would …, <effect>", "The first time
# …, <effect>") — consume up to the comma so dispatch lands on the replacing effect
# (often "prevent …" / "it deals …"). phase strips the same wrapper before the effect.
_REPLACEMENT_PREFIX = comb.value(
    None,
    comb.seq3(
        comb.alt(
            comb.tag("the next time"),
            comb.tag("the first time"),
            comb.tag("the second time"),
        ),
        comb.take_until(","),
        comb.tag(","),
    ),
)
_CONNECTIVE_PREFIX = comb.value(
    None,
    comb.alt(
        comb.tag("you may "),
        comb.tag("may "),  # after a player prefix: "target player may draw"
        comb.tag("then "),
        comb.tag("also "),  # "… , also regenerate ~"
        comb.tag("instead "),
        comb.tag("secretly "),  # "… each secretly choose" -> choose
        comb.tag("simultaneously "),
    ),
)
# An activation cost "{…}…: " (activated abilities) — consume the leading "{" symbol
# run up to the cost/effect "': '" so dispatch lands on the effect, not the "{".
_COST_PREFIX = comb.value(
    None, comb.seq3(comb.tag("{"), comb.take_until(": "), comb.tag(": "))
)
# A planeswalker loyalty cost "[+1]: " / "[-3]: " / "[0]: " — consume the bracketed
# cost so dispatch lands on the loyalty ability's effect.
_LOYALTY_PREFIX = comb.value(
    None, comb.seq3(comb.tag("["), comb.take_until("]: "), comb.tag("]: "))
)
# A leading player subject ("Target player reveals …", "Each opponent …") — consume
# it so dispatch sees the verb the player performs. Includes the SELF subject "~"
# (the IR's self-name placeholder: "~ deals 2 damage …") and "it"/"its" (a back-ref
# to the just-named permanent) so the verb that follows dispatches.
_PLAYER_PREFIX = comb.value(
    None,
    comb.alt(
        comb.tag("each player "),
        comb.tag("each opponent "),
        comb.tag("they "),
        comb.tag("players "),
        comb.tag("each of them "),
        comb.tag("you and that player each "),
        comb.tag("you and target player each "),
        comb.tag("you and target opponent each "),
        comb.tag("that source's controller "),
        comb.tag("target player "),
        comb.tag("target opponent "),
        comb.tag("target creature "),
        comb.tag("target permanent "),
        comb.tag("another target creature "),
        comb.tag("each other creature you control "),
        comb.tag("nontoken creatures you control "),
        comb.tag("creatures you control "),
        comb.tag("creatures your opponents control "),
        comb.tag("up to one other target creature "),
        comb.tag("up to one target creature "),
        comb.tag("up to one "),
        comb.tag("each creature "),
        comb.tag("all creatures "),
        comb.tag("that player "),
        comb.tag("this creature "),
        comb.tag("this permanent "),
        comb.tag("that creature "),
        comb.tag("~'s "),
        comb.tag("~ "),
        comb.tag("its "),
        comb.tag("it "),
    ),
)
# A leading duration / distribution clause ("Until end of turn, …", "This turn, …",
# "For each player, …") — consumed so dispatch lands on the effect verb. phase strips
# the same timing wrapper before parsing the effect.
_DURATION_PREFIX = comb.value(
    None,
    comb.alt(
        comb.tag("until end of turn, "),
        comb.tag("this turn, "),
        comb.tag("during your turn, "),
        comb.tag("once each turn, "),
        comb.tag("once during each of your turns, "),
        comb.value(
            "", comb.seq3(comb.tag("during "), comb.take_until(", "), comb.tag(", "))
        ),
        # coerced to str so `alt`'s members are homogeneous Parser[str].
        comb.value(
            "", comb.seq3(comb.tag("for each "), comb.take_until(", "), comb.tag(", "))
        ),
    ),
)
_PREFIX = comb.preceded(
    comb.ws(),
    comb.alt(
        _CHAPTER_PREFIX,
        _ABILITY_WORD_PREFIX,
        _COST_PREFIX,
        _LOYALTY_PREFIX,
        _REPLACEMENT_PREFIX,
        _TRIGGER_PREFIX,
        _DURATION_PREFIX,
        _PLAYER_PREFIX,
        _CONNECTIVE_PREFIX,
    ),
)

# Verb arms that need a look-ahead discriminant (a sub-parse), built from combinators:
# "deal [N] damage" (amount between verb and noun); create-a-copy vs token; return-to-
# battlefield (reanimate) vs to-hand/owner/top (bounce); "add … mana"; "put … counter".
_DEAL_DAMAGE = comb.value(
    "damage", comb.seq2(comb.tag("deal"), comb.take_until("damage"))
)
_CREATE = comb.alt(
    comb.value("clone", comb.seq2(comb.tag("create"), comb.take_until("copy of"))),
    comb.value("make_token", comb.tag("create")),
)
_RETURN = comb.preceded(
    comb.tag("return"),
    comb.alt(
        comb.value("reanimate", comb.take_until("to the battlefield")),
        comb.value("bounce", comb.take_until("to its owner")),
        comb.value("bounce", comb.take_until("to their owner")),
        comb.value("bounce", comb.take_until("to their hand")),
        comb.value("bounce", comb.take_until("to your hand")),
        comb.value("bounce", comb.take_until("to the top")),
    ),
)
_ADD_MANA = comb.alt(
    comb.value("ramp", comb.seq2(comb.tag("add"), comb.take_until("mana"))),
    # "add {C}{C}", "add {R}" — mana symbols, no literal "mana" word.
    comb.value("ramp", comb.seq2(comb.tag("add"), comb.take_until("{"))),
)
# "lose(s) …": a life loss ("loses 4 life") vs an ABILITY/type loss ("loses all
# abilities", "loses flying", "loses all creature types"). take_until("life") picks
# the life sense; otherwise it's an ability_loss (debuff / type-strip).
_LOSE = comb.preceded(
    comb.keyword({"lose", "loses"}),
    comb.alt(
        comb.value("lose_life", comb.take_until("life")),
        comb.value("ability_loss", comb.succeed(None)),
    ),
)
# "put …" branches by what's put where: "put a +1/+1 counter" (place_counter), "put X
# onto the battlefield" (reanimate — recur a card into play from a non-cast zone),
# "put X into … hand" (bounce). Most specific (counter) first; the zone arms read the
# destination phrase the way _RETURN reads return-destinations.
_PUT = comb.preceded(
    comb.tag("put"),
    comb.alt(
        comb.value("place_counter", comb.take_until("counter")),
        comb.value("reanimate", comb.take_until("onto the battlefield")),
        comb.value("bounce", comb.take_until("into its owner")),
        comb.value("bounce", comb.take_until("into their owner")),
        comb.value("bounce", comb.take_until("into your hand")),
    ),
)

# Single-word imperative verbs (word-boundary-safe via `keyword`, so "draw" doesn't
# fire on "drawback"); plural/3rd-person forms included for triggered phrasings.
_SIMPLE_VERB = comb.alt(
    comb.value("draw", comb.keyword({"draw", "draws"})),
    comb.value("make_token", comb.keyword({"conjure", "conjures"})),
    comb.value("choose", comb.keyword({"choose", "chooses"})),
    comb.value("sacrifice", comb.keyword({"sacrifice", "sacrifices"})),
    comb.value("mill", comb.keyword({"mill", "mills"})),
    comb.value("discard", comb.keyword({"discard", "discards"})),
    comb.value("untap", comb.keyword({"untap", "untaps"})),
    comb.value("tap", comb.keyword({"tap", "taps"})),
    comb.value("shuffle", comb.keyword({"shuffle", "shuffles"})),
    comb.value("destroy", comb.keyword({"destroy", "destroys"})),
    comb.value("exile", comb.keyword({"exile", "exiles"})),
    comb.value("proliferate", comb.keyword({"proliferate", "proliferates"})),
    comb.value("goad", comb.keyword({"goad", "goads"})),
    comb.value("scry", comb.keyword({"scry", "scries"})),
    comb.value("surveil", comb.keyword({"surveil", "surveils"})),
    comb.value("reveal", comb.keyword({"reveal", "reveals"})),
    comb.value("roll_die", comb.keyword({"roll", "rolls"})),  # "roll a d20", dice
    comb.value("pay_cost", comb.keyword({"pay"})),  # "Pay 3 life", "pay {2}{R}" (cost)
    comb.value("fight", comb.keyword({"fight", "fights"})),  # "fights target creature"
    # Manifest = card face down as a 2/2 (CR 701.40), not a token — own category.
    comb.value("manifest", comb.keyword({"manifest", "manifests"})),
    comb.value("clash", comb.keyword({"clash"})),  # "clash with defending player"
    comb.value("discover", comb.keyword({"discover", "discovers"})),
    comb.value("make_token", comb.keyword({"investigate", "investigates"})),  # Clue
    # Craft (CR 702.166) — exile this + materials, return it transformed: a transform.
    comb.value("transform", comb.keyword({"craft"})),
    comb.value("suspect", comb.keyword({"suspect", "suspects"})),  # CR 701.61
    comb.value("place_counter", comb.keyword({"adapt", "adapts"})),  # CR 701.43
    comb.value("regenerate", comb.keyword({"regenerate", "regenerates"})),  # CR 701.19
    comb.value("convert", comb.keyword({"convert", "converts"})),  # FF convert
    comb.value("station", comb.keyword({"station", "stations"})),  # spacecraft Station
    # Ninjutsu (CR 702.49) — return an unblocked attacker, put this onto the
    # battlefield from hand: a put-into-play cheat. The effect is in the reminder
    # (stripped), so map the keyword name itself.
    comb.value("cheat_play", comb.keyword({"ninjutsu"})),
    # Keyword abilities that survived as leading text — a closed CR vocabulary mapped
    # to the mechanic each one IS (generalizes to any card with the keyword).
    # Devour (CR 702.82): sacrifice creatures as it enters, ENTER WITH +1/+1
    # counters. Own category fans to sacrifice_matters (the fodder) AND
    # counters_matter (the payoff) + the dedicated devour_matters lane.
    comb.value("devour", comb.keyword({"devour", "devours"})),
    comb.value("vanishing", comb.keyword({"vanishing"})),  # CR 702.62 time counters
    # Soulshift returns a card from GY to HAND (CR 702.46) — graveyard recursion,
    # NOT reanimation (which is GY→battlefield). Mislabeling it "reanimate" wrongly
    # marked Spirit-tribal commanders as reanimators.
    comb.value("graveyard_recursion", comb.keyword({"soulshift"})),  # CR 702.46
    comb.value("cost_reduction", comb.keyword({"multikicker"})),  # CR 702.33
    comb.value("cast_from_zone", comb.keyword({"foretell", "foretells"})),  # 702.143
    comb.value("topdeck_select", comb.keyword({"look", "looks"})),  # "look at top N"
    comb.value("damage_prevention", comb.keyword({"prevent", "prevents"})),
    # The four bending keyword-actions (CR 701.65-67, 702.189) — distinct mechanics,
    # one shared `bending` effect category (the per-element synergy lanes are not
    # IR-sliced, so this only completes the parse).
    comb.value(
        "bending",
        comb.keyword(
            {
                "earthbend",
                "earthbends",
                "firebend",
                "firebends",
                "waterbend",
                "waterbends",
                "airbend",
                "airbends",
            }
        ),
    ),
)
# Multi-word verb phrases (order: most specific first).
_VERB = comb.alt(
    _DEAL_DAMAGE,
    comb.value("gain_life", comb.tag("gain life")),
    comb.value("lose_life", comb.tag("lose life")),
    comb.value("gain_control", comb.tag("exchange control")),
    comb.value("gain_control", comb.tag("gain control")),
    comb.value("win_game", comb.tag("win the game")),
    comb.value("lose_game", comb.tag("lose the game")),
    comb.value("attach", comb.tag("attach")),  # "attach it to …"
    # "exchange its power and the power of …" — switch P/T (CR switchpt).
    comb.value("switch_pt", comb.seq2(comb.tag("exchange"), comb.take_until("power"))),
    # "switch its power and toughness" (CR switchpt).
    comb.value("switch_pt", comb.seq2(comb.tag("switch"), comb.take_until("power"))),
    comb.value("skip_step", comb.keyword({"skip", "skips"})),  # "skips … combat phase"
    comb.value("counter_spell", comb.tag("counter target")),
    comb.value("counter_spell", comb.tag("counter that")),
    comb.value("counter_spell", comb.tag("counter it")),  # "…, counter it unless …"
    comb.value("spell_copy", comb.tag("copy that spell")),
    comb.value("spell_copy", comb.tag("copy target spell")),
    comb.value("tutor", comb.tag("search the graveyard")),  # Delirium search-the-GY
    # "distribute N +1/+1 counters among …" — a counter placement.
    comb.value(
        "place_counter", comb.seq2(comb.tag("distribute"), comb.take_until("counter"))
    ),
    # "search your library/hand/graveyard …", "search target player's library" — a
    # search is a tutor (CR 701.23) regardless of the zone searched.
    comb.value("tutor", comb.tag("search your")),
    comb.value("tutor", comb.tag("search target")),
    comb.value("tutor", comb.tag("search their")),  # "search their library …"
    comb.value("tutor", comb.tag("searches their")),  # "<player> searches their …"
    comb.value("tutor", comb.tag("searches your")),
    comb.value("tutor", comb.tag("search that player's")),
    comb.value("tutor", comb.tag("searches that player's")),
    comb.value("redirect", comb.tag("change the target")),  # changetargets -> redirect
    comb.value("pay_cost", comb.tag("pay any amount")),  # "pay any amount of {R}"
    # ETB-with-counters ("enters with X +1/+1 counters", plural "enter with …") → a
    # counter placement.
    comb.value(
        "place_counter",
        comb.seq2(comb.tag("enters with"), comb.take_until("counter")),
    ),
    comb.value(
        "place_counter",
        comb.seq2(comb.tag("enter with"), comb.take_until("counter")),
    ),
    # "get(s) … counter(s)" — a player/permanent gains counters (poison/energy/+1+1);
    # the take_until("counter") gate keeps a bare "get" out.
    comb.value(
        "place_counter",
        comb.seq2(comb.keyword({"get", "gets"}), comb.take_until("counter")),
    ),
    # "attacks each combat if able" — a forced-attack restriction (CR 508 must-attack).
    comb.value("force_attack", comb.tag("attacks each combat")),
    # "play with the top card of your library revealed" — play-from-top engine.
    comb.value("cast_from_zone", comb.tag("play with the top")),
    # "you may play that card / those cards / it (this turn)" — impulse/exile play.
    comb.value("cast_from_zone", comb.tag("play that card")),
    comb.value("cast_from_zone", comb.tag("play those cards")),
    comb.value("cast_from_zone", comb.tag("play cards exiled")),
    comb.value("gain_control", comb.tag("you control target")),  # mind-control
    comb.value("gain_control", comb.tag("you control enchanted")),  # Control Magic aura
    comb.value("attach", comb.tag("aura swap")),  # CR 702.65 — swap an Aura in/out
    # an Aura's "Enchant <X>" — defines what it attaches to (voltron/attach lane).
    comb.value("attach", comb.tag("enchant ")),
    # "Move one or more counters from … onto …" (CR movecounters) -> counter_move.
    comb.value("counter_move", comb.seq2(comb.tag("move"), comb.take_until("counter"))),
    # extra land drops ("play an additional land", "play two additional lands") — its
    # own category; the count word between "play" and "additional land" is consumed.
    comb.value(
        "extra_land",
        comb.seq2(comb.tag("play"), comb.take_until("additional land")),
    ),
    # "play lands/cards from the top of your library" etc. — playing from a non-hand
    # zone (the "from" gate keeps "play an additional land" out). cast_from_zone.
    comb.value("cast_from_zone", comb.seq2(comb.tag("play"), comb.take_until("from"))),
    # "cast … from the top/graveyard/exile" — casting from a non-hand zone (the "from"
    # gate keeps "cast a copy" out). cast_from_zone.
    comb.value("cast_from_zone", comb.seq2(comb.tag("cast"), comb.take_until("from"))),
    # "remove a/the … counter (from …)" — counter manipulation → place_counter
    # (counters_matter); the take_until("counter") gate keeps "remove from combat" out.
    comb.value(
        "place_counter", comb.seq2(comb.tag("remove"), comb.take_until("counter"))
    ),
    # "flip it" / "flip ~" — turn the permanent over (flip card / face-down): transform.
    comb.value("transform", comb.tag("flip it")),
    comb.value("transform", comb.tag("flip ~")),
    # "turn target … face down/up" — morph/cloak/manifest flip: transform.
    comb.value("transform", comb.seq2(comb.tag("turn"), comb.take_until("face"))),
    # "enters prepared" (CR keyword) — its own category like becomeprepared->prepared.
    comb.value("prepared", comb.tag("enters prepared")),
    # "enters tapped" / "enters the battlefield tapped" — an ETB-tapped state (a real
    # mechanic; not IR-sliced, so this only completes the parse).
    comb.value("enters_tapped", comb.tag("enters tapped")),
    comb.value("enters_tapped", comb.tag("enter tapped")),
    comb.value("enters_tapped", comb.tag("enters the battlefield tapped")),
    _ADD_MANA,
    _PUT,
    _CREATE,
    _RETURN,
    _LOSE,
    _SIMPLE_VERB,
)
# An effect clause: zero or more leading prefixes, whitespace, then the verb.
_EFFECT_CLAUSE = comb.preceded(
    comb.opt(comb.many(_PREFIX)), comb.preceded(comb.ws(), _VERB)
)


def _recover_by_verb(e: Effect) -> Effect | None:
    """Parse an unrecovered clause's imperative effect with the combinator grammar
    (after stripping phase's diagnostic prefix). Returns the effect re-categorized, or
    None when the clause has no recognizable imperative (it stays 'other')."""
    r = _EFFECT_CLAUSE.parse(_FAILED_PREFIX.sub("", e.raw).strip())
    return replace(e, category=r[0]) if r is not None else None


# The anchored grammar matches the verb at the cursor (after prefixes); but a clause
# whose SUBJECT is a noun phrase we don't peel ("Up to two target creatures you control
# each deal damage", "searches their library …") hides the primary verb a few words in.
# This LAST-RESORT scan advances word-by-word and takes the FIRST known verb — the
# clause's primary action. A cheap keyword guard skips the positional scan unless a
# candidate verb token is even present, so it runs only on the genuine tail.
_PREFIX_PEEL = comb.opt(comb.many(_PREFIX))
_VERB_PRESENT = re.compile(
    r"\b(?:draws?|creates?|destroys?|exiles?|gains?|deals?|mills?|sacrifices?"
    r"|discards?|taps?|untaps?|puts?|searches?|counter|scry|scries|surveils?"
    r"|shuffles?|loses?|reveals?|proliferates?|returns?|conjures?|chooses?"
    r"|goads?|rolls?|prevents?|enters?|enter|moves?|plays?|casts?|removes?"
    r"|fights?|switch|switches|adds?|foretells?|adapts?|crews?|stations?|soulshift"
    r"|regenerates?|converts?)\b",
    re.IGNORECASE,
)


def _recover_verb_scan(e: Effect) -> Effect | None:
    s = _FAILED_PREFIX.sub("", e.raw).strip()
    peeled = _PREFIX_PEEL.parse(s)
    body = peeled[1].strip() if peeled is not None else s
    if not _VERB_PRESENT.search(body):
        return None
    words = body.split()
    for i in range(1, min(len(words), 22)):
        r = _VERB.parse(" ".join(words[i:]))
        if r is not None:
            return replace(e, category=r[0])
    return None


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
# discriminator-gated in extract_signals_ir (additive — they keep firing ramp_matters).
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
        return replace(e, category="combat_damage_mod")
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
    return _recover_exile_removal(out)
