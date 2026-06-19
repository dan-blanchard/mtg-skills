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
        comb.tag("you and that player each "),
        comb.tag("you and target player each "),
        comb.tag("target player "),
        comb.tag("target opponent "),
        comb.tag("target creature "),
        comb.tag("target permanent "),
        comb.tag("another target creature "),
        comb.tag("each other creature you control "),
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
_ADD_MANA = comb.value("ramp", comb.seq2(comb.tag("add"), comb.take_until("mana")))
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
    comb.value("topdeck_select", comb.keyword({"look"})),  # "look at the top N …"
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
    comb.value("counter_spell", comb.tag("counter target")),
    comb.value("counter_spell", comb.tag("counter that")),
    # "search your library/hand/graveyard …", "search target player's library" — a
    # search is a tutor (CR 701.23) regardless of the zone searched.
    comb.value("tutor", comb.tag("search your")),
    comb.value("tutor", comb.tag("search target")),
    comb.value("pay_cost", comb.tag("pay any amount")),  # "pay any amount of {R}"
    # ETB-with-counters ("enters with X +1/+1 counters") → a counter placement.
    comb.value(
        "place_counter",
        comb.seq2(comb.tag("enters with"), comb.take_until("counter")),
    ),
    # "attacks each combat if able" — a forced-attack restriction (CR 508 must-attack).
    comb.value("force_attack", comb.tag("attacks each combat")),
    # "play with the top card of your library revealed" — play-from-top engine.
    comb.value("cast_from_zone", comb.tag("play with the top")),
    # extra land drops ("play an additional land this turn") — its own category.
    comb.value("extra_land", comb.tag("play an additional land")),
    # "play lands/cards from the top of your library" etc. — playing from a non-hand
    # zone (the "from" gate keeps "play an additional land" out). cast_from_zone.
    comb.value("cast_from_zone", comb.seq2(comb.tag("play"), comb.take_until("from"))),
    # "remove a/the … counter (from …)" — counter manipulation → place_counter
    # (counters_matter); the take_until("counter") gate keeps "remove from combat" out.
    comb.value(
        "place_counter", comb.seq2(comb.tag("remove"), comb.take_until("counter"))
    ),
    # "flip it" — turn the permanent over (flip card / face-down → up): transform.
    comb.value("transform", comb.tag("flip it")),
    # "turn target … face down/up" — morph/cloak/manifest flip: transform.
    comb.value("transform", comb.seq2(comb.tag("turn"), comb.take_until("face"))),
    # "enters prepared" (CR keyword) — its own category like becomeprepared->prepared.
    comb.value("prepared", comb.tag("enters prepared")),
    # "enters tapped" / "enters the battlefield tapped" — an ETB-tapped state (a real
    # mechanic; not IR-sliced, so this only completes the parse).
    comb.value("enters_tapped", comb.tag("enters tapped")),
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
_GETS_PT = re.compile(r"\bgets? [+-][\dxyz*]+/[+-][\dxyz*]+", re.IGNORECASE)
# A type/characteristic STATE conditional ("isn't a creature unless …", "isn't
# legendary if …") — a static layer effect, its own non-sliced category.
_STATE = re.compile(r"\bisn'?t (?:a |an |legendary)", re.IGNORECASE)
_CANT = re.compile(r"\bcan'?t\b", re.IGNORECASE)
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
# A player keyword grant — "You have hexproof/shroud/protection/…": grant_keyword,
# gated to real protective keywords so "you have no maximum hand size" stays out.
_PLAYER_KW_GRANT = re.compile(
    r"\byou have (?:hexproof|shroud|protection|indestructible|ward)", re.IGNORECASE
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
_BECOMES = re.compile(r"\bbecomes?\b", re.IGNORECASE)
# A cost alteration (CR 118.9): "… costs {N} less to cast", "… cost {2} more".
# The altered SET precedes "cost", so a discriminant scan (like the anthem above).
_COST_ALTER = re.compile(r"\bcosts?\s+(?:\{[^}]*\}\s+)?(?:less|more)\b", re.IGNORECASE)
# Disambiguate the "gain(s)" family: a life gain ("gains 5 life", "gain that much
# life") vs control ("gains control of") vs an ABILITY/keyword grant (everything
# else: "gains flashback", "has hexproof"). \blife\b is word-bounded so "lifelink"
# (a keyword grant) does NOT read as life. Control is checked before the bare grant.
_GAIN_LIFE = re.compile(r"\bgains?\b[^.]*\blife\b", re.IGNORECASE)
_GAIN_CONTROL = re.compile(r"\bgains?\s+control\b", re.IGNORECASE)
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
        return replace(e, category="restriction")
    if _CAN_COMBAT.search(s):
        return replace(e, category="grant_keyword")  # combat permission grant
    if _TUCK.search(s):
        return replace(e, category="shuffle")
    if _CDA_PT.search(s):
        return replace(e, category="characteristic_pt")
    if _STATE.search(s):
        return replace(e, category="state")
    if _FLASH_GRANT.search(s) or _PLAYER_KW_GRANT.search(s):
        return replace(e, category="grant_keyword")
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
        if any(w in low for w in _GRANTABLE_SUBJECT):
            return replace(e, category="grant_keyword")  # coarse — no keyword yet
    # "<subject> becomes a copy of …" → clone; "<subject> becomes a 4/4 …" → animate
    # (the subject precedes the verb, so this is a discriminant scan, not a parse).
    if _BECOMES.search(s):
        return replace(e, category="clone" if "copy of" in low else "animate")
    return None


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
    ClauseRule("by_verb", _recover_by_verb),
    ClauseRule("static_pattern", _recover_static_pattern),
)


# A bare Saga "Chapter N" (optionally "Chapter N, M") that leaked in as its own
# `other` effect — a chapter-timing LABEL, not a mechanical effect (the chapter's
# real effect is a sibling effect/trigger). Dropping it un-masks that sibling so the
# ability isn't held `partial` by a label; a chapter whose effect phase genuinely
# lost keeps an empty ability and stays partial (honest).
_CHAPTER_LABEL = re.compile(r"^chapter [\divxlc, ]+$", re.IGNORECASE)


def _is_noneffect_label(e: Effect) -> bool:
    return e.category == "other" and bool(_CHAPTER_LABEL.match((e.raw or "").strip()))


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
    """Return *card* with each effect's category/scope recovered from its raw, and the
    non-effect `other`s dropped (chapter labels; redundant textless nodes). See
    :func:`_clean_ability`."""
    faces = tuple(
        replace(face, abilities=tuple(_clean_ability(ab) for ab in face.abilities))
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

    return out
