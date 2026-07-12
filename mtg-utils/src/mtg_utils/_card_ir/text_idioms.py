"""Text-idiom regexes/combinator-scans shared by the legacy Card IR builder
(``project.py`` / ``supplement.py``) and the Layer-3 crosswalk (ADR-0035).

ADR-0039 step 2 rehomes these symbol DEFINITIONS out of the old builder modules
so the crosswalk's sanctioned text reads (``crosswalk_signals.py``,
``tree_synthesis.py``, and the ``_deck_forge._signals_ir`` mirror that
``combat_damage_recipients_from_text`` also serves) survive the old builder's
eventual deletion (ADR-0039 steps 6-7). ``project.py`` and ``supplement.py``
import their own symbols BACK from here, so the legacy sidecar-build path keeps
running byte-identically in the meantime — one definition, no duplication, zero
behavior change. Every symbol below moved verbatim (same regex / combinator
patterns, same bodies) from its original module; only the import direction
changed.

``_counter_kind_token`` is the one exception to "no other module dependency":
it needs ``project.py``'s ``_norm`` helper (158 other internal uses there, so
it stays put), imported lazily INSIDE the function body to avoid a
``project.py`` <-> ``text_idioms.py`` import cycle (``project.py`` imports this
module at its own top level to get the symbol back).
"""

from __future__ import annotations

import re

from mtg_utils._card_ir import _combinators as comb
from mtg_utils.card_ir import Filter

# ── Group A: from project.py ──────────────────────────────────────────────

# A CARES-ABOUT reference to a named token subtype WITHOUT making/sacrificing it —
# "<Subtype>s you control" (a count operand / anthem subject — Hobbit's Sting,
# Vihaan, Rent Is Due, Honored Dreyleader), "(was|were) (a|an) <Subtype>" (a sac
# condition — Evereth), "is a <Subtype>" / "that's a <Subtype>" (a Food-creature
# anthem — Brenard, Shelob). The lane (food/treasure/clue/blood_matters) is a
# cares-about payoff (the "_matters = cares-about" rule), so a deck running these
# wants the subtype. Anchored on the explicit own-control / state phrasing.
_TOKEN_SUBTYPE_OWN_REF = re.compile(
    r"\b(blood|clue|food|treasure)s? you control\b"
    r"|\b(?:was|were) (?:a |an )?(blood|clue|food|treasure)s?\b"
    r"|(?:\bis|\bare|that's|that are|it's|except it's) (?:a |an )?"
    r"(blood|clue|food|treasure)\b",
    re.IGNORECASE,
)

# ADR-0027 β — predicates that narrow a grant to a SINGLE permanent (an Aura's
# enchanted creature / an Equipment's equipped creature), NOT a board. A grant carrying
# one of these is "Enchanted/Equipped creature has '<quoted>'" — single-target, NOT a
# global ability grant — so it never fires the lane (the regex never matched a single
# Aura/Equipment grant either). CR 303 / 301.
_SINGLE_PERMANENT_GRANT_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})

# Lure / force-a-block (CR 509.1c/h) phase swallows into a pump/grant_keyword compound
# clause (Indrik Umbra, Revenge of the Hunted), drops in a conditional static (Seton's
# Desire, Stone-Tongue Basilisk), folds the equip rider as "must be blocked by <type>
# if able" (Ace's Baseball Bat, Slayer's Cleaver), or buries it in a modal bullet
# (Glorfindel). Two phrasings: "able to block <X> do so" (force ALL able blockers) and
# "must be blocked [by <type>] if able" (force a block on the attacker). Both force a
# block — the lane explicitly wants force-a-block — so a by-<type> restriction is a
# refinement, not a disqualifier. The block-LIMIT tax ("can't be blocked by more than
# one") never says "do so" or "must be blocked … if able", so it can't match.
_LURE_ABLE = re.compile(r"\bable to block\b[^.]*\bdo so\b", re.IGNORECASE)
_LURE_MUST = re.compile(r"\bmust be blocked\b[^.]*?\bif able\b", re.IGNORECASE)

# Combat-forcing disentanglement (CR 508.1g / 701.38). Two structurally distinct
# compulsions phase DROPS to raw (the self/team static carries no abilities; the
# reward-payoff trigger flattens to event=None with the redirect condition in raw):
#
#   • FORCED ATTACK (self-force) — "~ attacks each/every combat if able", "attacks
#     that player this combat if able", a granted "creatures you control attack each
#     combat if able" (Dauthi Slayer, Battle-Mad Ronin, Goblin Spymaster's token
#     grant). A COMPULSION to swing — the forced_attack lane (an aggro/symmetric-force
#     theme), NOT goad. phase emits a `MustAttack` mode only for the ACTIVATED single-
#     target form (Basandra); the static self/team force is dropped.
#   • GOAD REWARD (redirect-payoff) — "attacks one of your opponents", "attacks a
#     player other than you", "whenever a(nother) player attacks (one of your
#     opponents)", the defending-player payoff (Gahiji, Breena, Frontier Warmonger,
#     Kazuul). The card REWARDS opponents' creatures being redirected at another player
#     — the goad mechanic's payoff (CR 701.38b: a goaded creature attacks a player
#     other than its controller), so it wants goad effects. NOT a self-force.
#
# The two patterns are mutually exclusive by construction: "each combat if able" is
# the self-compulsion; "one of your opponents" / "a player other than you" / "a player
# attacks" is the redirect-reward. A single-target "target creature attacks … if able"
# (Basandra) keeps phase's force_attack effect and is NOT matched here (no "each/every
# combat", no opponent-redirect) — it stays forced_attack-adjacent without leaking goad.
_FORCE_ATTACK_REF = re.compile(
    r"attacks? (?:each|every) combat if able"
    r"|attacks? that player this combat if able"
    r"|may attack only the nearest opponent",
    re.IGNORECASE,
)
_GOAD_REWARD_REF = re.compile(
    r"attacks? one of your opponents"
    r"|attacks? a player other than (?:you|its controller)"
    r"|whenever a(?:nother)? player attacks"
    r"|creature an opponent controls attacks[^.]*"
    r"(?:you're|you are) the defending player",
    re.IGNORECASE,
)

# "becomes a/an artifact|enchantment" — a TYPE-GRANT (animate / grant the type) whose
# granted card-type phase drops to a subject=None base_pt_set/animate/state. Anchored
# on "becomes" + the type so a token "create a token that's an artifact" (a maker, not
# a grant) and a clone "becomes a copy of" never match.
_BECOMES_TYPE_RE = re.compile(
    r"becomes? (?:a|an) (?:\w+ )*?(artifact|enchantment)\b", re.IGNORECASE
)

# ADR-0027 counter/modified taxonomy — strip a leaked comparator phrase off a
# phase counter-KIND string. phase's filter-property ``counters.data`` is usually a
# clean kind ("oil", "time", "bounty") but sometimes carries the comparator clause
# the parser failed to split off ("or more charge" → the kind is "charge"; "or more
# loyalty" → "loyalty"; "fewer than x +1/+1" → the +1/+1 signature). CR 122.1.
_COUNTER_KIND_LEAK = re.compile(
    r"^(?:x\s+)?(?:or\s+more|or\s+fewer|fewer\s+than(?:\s+x)?|more|fewer)\s+",
    re.IGNORECASE,
)


def _counter_kind_token(raw: object) -> str:
    """Normalize a phase filter-property ``counters.data`` into a kind token.

    ``+1/+1`` → ``P1P1`` and ``-1/-1`` → ``M1M1`` (the canonical signatures the
    plus_one_matters / minus_counters_matter lanes read), else the leaked-comparator-
    stripped ``_norm`` of the kind (oil / stun / time / bounty / divinity / …). An
    empty / pure-comparator residue becomes ``Generic`` (a counter with no nameable
    kind). CR 122.1 (counters are individuated by name)."""
    from mtg_utils._card_ir.project import _norm

    if not isinstance(raw, str):
        return "Generic"
    if "+1/+1" in raw:
        return "P1P1"
    if "-1/-1" in raw:
        return "M1M1"
    s = raw
    prev = None
    while prev != s:
        prev = s
        s = _COUNTER_KIND_LEAK.sub("", s).strip()
    if s.lower() in ("or more", "or fewer", "or", ""):
        return "Generic"
    norm = _norm(s)
    # Phase emits a clean "P1P1"/"M1M1" for the bulk of +1/+1 / -1/-1 references;
    # canonicalize them to the same signature token the leaked-text branch returns
    # (else a clean "P1P1" → _norm "p1p1" wouldn't match the lane's P1P1 read).
    if norm == "p1p1":
        return "P1P1"
    if norm == "m1m1":
        return "M1M1"
    return norm or "Generic"


# ADR-0027 β opponent_search_matters — the library-manipulation player actions phase
# lists on a `PlayerPerformedAction` trigger's `player_actions` (River Song's composite
# is ["Scry","Surveil","SearchedLibrary"]). The composite must NAME the library SEARCH
# (`SearchedLibrary`) and contain ONLY scry-surveil-search actions — the search is the
# discriminator that pins this to the opponent-search lane the deleted regex covered
# ("searches their/a library"). Two carve-outs the gate deliberately leaves on `other`:
#   • Proliferate composites (Ezuri, Scheming Aspirant) — not a library action.
#   • SCRY/SURVEIL-only composites (Matoya, Planetarium — both YOU-scoped, no opponent
#     punisher exists) — staying `other` keeps the `_narrow_trigger_other_refs`
#     scry_surveil marker (gated event=='other') firing scry_surveil_matters for them,
#     so the re-type is drift-free on that lane.
_LIB_SEARCH_PLAYER_ACTIONS = frozenset({"scry", "surveil", "searchedlibrary"})


# ── Group B: from supplement.py ───────────────────────────────────────────

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


# Forced combat: "… attacks … if able", "all creatures … attack if able" (the
# sibling forced-BLOCK regex — "all … able to block ~ do so" — stays in
# supplement.py; this is only the attack half). CR 508.1g.
_FORCE_ATTACK = re.compile(r"\battacks?\b[^.]*\bif able\b", re.IGNORECASE)

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
