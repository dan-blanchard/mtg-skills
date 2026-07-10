"""Shared clause grammar (ADR-0038): the pure text->category-token parsing
core both IR paths consume.

The old-IR supplement (:mod:`mtg_utils._card_ir.supplement`) re-tags
``Effect.category`` with it; the crosswalk recovery stage re-decorates
``ConceptNode``s with it. Extracted verbatim from ``supplement.py`` so
the two paths cannot drift.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir import _combinators as comb

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
        # CR 724 (end the turn) — Obeka's activated-ability grant reads "The
        # player whose turn it is may end the turn." Peeling this subject
        # lands dispatch on "may end the turn", which the connective prefix
        # then strips to "end the turn" for the verb table.
        comb.tag("the player whose turn it is "),
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
    # counters. Own category fans to sacrifice_outlets (the fodder) AND
    # plus_one_matters (the payoff) + the dedicated has_devour lane.
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
    # (plus_one_matters); the take_until("counter") gate keeps "remove from combat" out.
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
    # "end the turn" (CR 724) — the expedite-the-turn ACTION (Obeka's grant,
    # after the player-subject + "may " prefixes peel). "until end of turn, "
    # / "at the end of the turn" are a DURATION prefix (different text, a
    # trailing comma, peeled long before dispatch reaches the verb table) so
    # neither shadows nor is shadowed by this arm.
    comb.value("end_the_turn", comb.tag("end the turn")),
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


def parse_clause(text: str) -> str | None:
    """Parse a clause's imperative effect with the combinator grammar (after
    stripping phase's diagnostic prefix). Returns the matched category, or
    None when the clause has no recognizable imperative."""
    r = _EFFECT_CLAUSE.parse(_FAILED_PREFIX.sub("", text).strip())
    return r[0] if r is not None else None


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
    r"|regenerates?|converts?|ends?)\b",
    re.IGNORECASE,
)


def scan_clause(text: str) -> str | None:
    """Last-resort word-by-word scan for the clause's primary verb, for a
    clause whose subject hides the verb a few words in. Returns the matched
    category, or None when no known verb is present."""
    s = _FAILED_PREFIX.sub("", text).strip()
    peeled = _PREFIX_PEEL.parse(s)
    body = peeled[1].strip() if peeled is not None else s
    if not _VERB_PRESENT.search(body):
        return None
    words = body.split()
    for i in range(1, min(len(words), 22)):
        r = _VERB.parse(" ".join(words[i:]))
        if r is not None:
            return r[0]
    return None


# ── static-line grammar (the STATIC-clause analog of parse_clause) ────────────
# A static names the AFFECTED set BEFORE its verb (an anthem, a restriction, an
# ability grant), so — unlike the imperative verb grammar above, which is a
# cursor-anchored parse — static-line recovery is a DISCRIMINANT: does the
# clause (after stripping phase's diagnostic prefix) contain a recognized
# static idiom ANYWHERE. ``STATIC_TOKENS`` is an ordered table of (compiled
# pattern, token) rows, first match wins; ``static_token`` is its pure lookup
# fn, the static-line sibling of ``parse_clause``/``scan_clause``. Today wired
# crosswalk-side only (:mod:`recovery`'s ``_recover`` tries it as the third
# fallback); the supplement's ``_recover_static_pattern`` arms migrate INTO
# this shared table per-key later, same strangler discipline as the effect-
# verb grammar (no legacy behavior change from adding a row here alone).
STATIC_TOKENS: tuple[tuple[re.Pattern[str], str], ...] = (
    # evasion-denial idiom (CR 509.1b/702.14): "can be blocked as though
    # it/they didn't have [landwalk/those abilities]" — an anti-evasion
    # static (Staff of the Ages) whose grant phase leaves an Unimplemented
    # parse-failure residue the typed IgnoreLandwalkForBlocking static read
    # never reaches. "can't be blocked" (an evasion GRANT) never matches —
    # the idiom is "CAN be blocked as though".
    (
        re.compile(
            r"\bcan be blocked as though (?:it|they) did(?:n'?t| not) have\b",
            re.IGNORECASE,
        ),
        "evasion_denial",
    ),
    # coin-flip idiom (CR 705.1/705.3): "flip a coin", "flip one or more
    # coins", "those coins come up heads" (a flip-FIXING static — Edgar,
    # King of Figaro's "Two-Headed Coin", Molten Sentry's modal ETB flip).
    # Both land in an Unimplemented node the imperative verb grammar's
    # SIMPLE_VERB table has no "flip" arm for (a flip-fixing static never
    # itself instructs a plain flip the way "draw"/"destroy" do — CR
    # 705.3 lets the static OVERRIDE the actual coin-flip result). Mirrors
    # the OLD-IR ``_COIN`` static-pattern regex byte-for-byte (verbatim
    # extraction discipline, ADR-0038) so the two paths draw the same line.
    (
        re.compile(r"\bflips?\b[^.]{0,18}\bcoins?\b", re.IGNORECASE),
        "coin_flip",
    ),
    # opponent cast-lock idiom (CR 601.3/604.1): "each opponent can't cast
    # ..." (Lavinia, Azorius Renegade) -- a dynamic-threshold restriction
    # ("... with mana value greater than the number of lands that player
    # controls") phase's own static parser can't build, leaving an
    # Unimplemented parse-failure residue the typed AddRestriction read
    # never reaches. Mirrors the OLD-IR supplement._CANT + third-party
    # scope-repair idiom for this exact "opponent can't cast" phrasing.
    (
        re.compile(r"\bopponents? can'?t cast\b", re.IGNORECASE),
        "stax_cast_lock",
    ),
)


def static_token(text: str) -> str | None:
    """Match a STATIC clause (after stripping phase's diagnostic prefix)
    against :data:`STATIC_TOKENS`, first row wins. Returns the matched
    token, or None when no known static idiom is present."""
    s = _FAILED_PREFIX.sub("", text).strip()
    for pattern, token in STATIC_TOKENS:
        if pattern.search(s):
            return token
    return None
