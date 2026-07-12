"""Text-idiom regexes/combinator-scans shared by the Layer-3 crosswalk (ADR-0035).

ADR-0039 step 2 rehomed these symbol DEFINITIONS out of the old builder modules
(``project.py`` / ``supplement.py``) so the crosswalk's sanctioned text reads
(``crosswalk_signals.py``, ``tree_synthesis.py``, and the
``_deck_forge._signals_ir`` mirror that ``combat_damage_recipients_from_text``
also serves) survive the old builder's deletion. Step 7 finished that deletion:
``project.py`` is gone, and the last shared symbols it still defined (``_norm``,
``_DICE_TRIG``, the tree-synthesis raw anchors of Group C, and the sac-cost
patterns ``bridge_ledger`` reads) moved here verbatim (same regex / combinator
patterns, same bodies); only the import direction changed.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir import _combinators as comb
from mtg_utils.card_ir import Filter


def _norm(token: object) -> str:
    """Lowercase + strip non-alphanumerics, so ``DealDamage``/``deal_damage`` match."""
    return re.sub(r"[^a-z0-9]", "", str(token).lower())


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


# ── Group C: from project.py (ADR-0039 step 7 — the builder deleted) ──────
# The raw anchors below were project.py's marker regexes; the crosswalk's
# tree_synthesis arms, the _signals_ir / recovery grammar reads, and the
# bridge_ledger sac-cost rows import them from here now that the legacy
# builder is gone. Each moved verbatim with its original comment block.

# "<determiner> creature […] can't block" — a clause FORCING a targeted/affected
# creature OTHER THAN THE SOURCE to be unable to block (path-clearing / pillowfort
# grant, CR 509). The leading determiner excludes the bare self drawback
# "~ can't block" / "this creature can't block" (a vanilla downside, not a grant).
_CANT_BLOCK_REF = re.compile(
    r"\b(?:target|each|that|the chosen|chosen|enchanted|another) "
    r"(?:[a-z]+ )*?creature[^.]*?can'?t block\b",
    re.IGNORECASE,
)
# …but not the combat TAX "can't block with N" / "can't block more than" (a
# block-limiting effect, a different lane than an absolute can't-block grant).
_CANT_BLOCK_TAX = re.compile(r"can'?t block (?:with|more than)\b", re.IGNORECASE)
# Soulbond (CR 702.95) reference in a non-keyword card ("paired with a creature with
# soulbond" — Flowering Lumberknot's restriction).
_SOULBOND_REF = re.compile(r"\bsoulbond\b", re.IGNORECASE)
# Exhaust (CR 702.177) PAYOFF trigger: "Whenever you activate an exhaust ability,
# …" (Rangers' Aetherhive, Adrenaline Jockey). Exhaust SOURCES carry an
# "Exhaust — {cost}:" ability; this is the keyword-less payoff.
_EXHAUST_TRIG = re.compile(
    r"\bactivate(?:s|d)? (?:a |an )?exhaust abilit", re.IGNORECASE
)
# Dice (CR 706, AFR/Unfinity) PAYOFF trigger: "Whenever you roll one or more dice/a
# die/a <N>/your <Nth> die, …" (Brazen Dwarf, Dee Kay, Feywild Trickster). phase
# parses the consequence (damage / make_token / place_counter / draw) but flattens the
# dice trigger to event='other', keeping the roll reference only in the raw. The
# roll-a-die DOERS already ride phase's roll_die effect; this is the keyword-less
# "cares when I roll" payoff. Anchored on the roll-trigger phrase.
_DICE_TRIG = re.compile(
    r"\bwhenever you roll\b|\broll(?:ed)? (?:one or more|your|a|\d+) (?:dice|die|\d)"
    r"|\brolled (?:one or more|\d+) (?:dice|die)\b",
    re.IGNORECASE,
)
# Cascade (CR 702.85) CONFERRED / referenced — phase rides the Scryfall `cascade`
# keyword for an INTRINSIC cascade spell, but the GRANTERS are keyword-less: "spells
# you cast have cascade" (Maelstrom Nexus, Yidris), "the next spell you cast … has
# cascade" (Maelstrom Nexus, the Doctor Who cascade-granters), "gain cascade" (Yidris),
# "with cascade" (Zhulodok's "Cascade, cascade"), and the cares-about "as you cascade"
# (Averna) / "cast a spell with cascade" (The First Doctor) payoff. Anchored on the
# conferring/reference phrase — "(have|has|gain[s]|with) cascade" / "as you cascade" /
# "spell with cascade" — NOT the bare keyword the card's own array already carries.
_CASCADE_GRANT = re.compile(
    r"\b(?:have|has|gains?|with) cascade\b|\bas you cascade\b"
    r"|\bspells? with cascade\b|\bcascade, cascade\b",
    re.IGNORECASE,
)
# Undying (CR 702.92) / Persist (CR 702.78) GRANTED to a class of creatures — phase
# rides the Scryfall keyword for an INTRINSIC undying/persist creature, but the
# GRANTERS are keyword-less: "creatures you control … have undying" (Mikaeus),
# "gains persist until end of turn" (Cauldron of Souls, Rhys, the persist-granters),
# "has persist as long as …" (the Scarecrows), a granted/quoted "gain undying"
# (Haunted One). Anchored on the GRANT VERB ("(gains?|have|has) undying/persist"),
# NOT the reminder text "(When a creature WITH undying dies …)" nor the bare keyword
# (the card's own array). The undying/persist counters mechanic stays its own lane.
_UNDYING_PERSIST_GRANT = re.compile(
    r"\b(?:gains?|have|has) (?:undying|persist)\b", re.IGNORECASE
)
# Suspect (CR 701.60) phase emits only on the leading imperative verb. The verb buried
# mid-clause / in a granted ability ("…and suspect it", "suspect up to one target") and
# the adjective/state form ("suspected creature") survive only in raw. Anchored on the
# verb (NOT followed by "counter" — Investigator's Journal's "suspect counter" is a
# same-named COUNTER type, not the Suspect designation, CR 701.60b) or "suspected".
_SUSPECT_REF = re.compile(r"\bsuspects?\b(?! counter)|\bsuspected\b", re.IGNORECASE)
# Crimes (CR 701.49, Outlaws) in CONDITION form — "(if|as long as) you've committed a
# crime this turn" / a cost reduction "if you've committed a crime" — the dominant
# crime-PAYOFF template phase has no condition kind for (it flattens the crime check
# into a quantitycomparison condition or drops it into raw). The TRIGGER form ("Whenever
# you commit a crime") already binds via phase's commit_crime trigger event; this is the
# keyword-less condition-form payoff. Anchored on the explicit "committed a crime".
_CRIME_REF = re.compile(
    r"(?:if|as long as|whenever) you'?ve committed a crime"
    r"|committed a crime this turn",
    re.IGNORECASE,
)
# Repeatable "Pay N life:" activated-ability cost phase loses: it misparses the cost
# (Arco-Flagellant's Endurant ability becomes a spell-with-pay_cost; Hibernation
# Sliver's self-usable granted ability) or drops the conferred quoted "…Pay 1 life:
# Draw" ability entirely (Underworld Connections, Degavolver, Anavolver, Lithoform
# Blight, Forgotten Monument). The colon-delimited "Pay N life:" is the precise cost
# anchor (not reminder text, not a one-shot cast-time additional cost). Gated to faces
# with no structural paylife cost so the 167 cards that parse it natively aren't
# double-tagged. CR 118.
_PAY_LIFE_REF = re.compile(r"[Pp]ay \d+ life:")
# Can't-block grant (CR 509) phase loses in a MODAL mode body ("• Target creature
# can't block this turn" — Breeches, Retreat to Valakut, phase keeps only the
# `choose` header) or a GRANTED QUOTED ability ("Enchanted land has '{T}: Target
# creature can't block…'" — Hostile Realm, Malicious Intent, phase emits
# abilities=()). We isolate the modal bullet / quoted-grant SEGMENT, then apply the
# same _CANT_BLOCK_REF (leading determiner + "creature … can't block") minus
# _CANT_BLOCK_TAX as the carrier-raw marker — segment isolation keeps the greedy
# determiner match from spanning an unrelated make_token "create … token with 'this
# token can't block'" clause (Anax, Totentanz), which the per-carrier marker already
# excludes via _CANT_BLOCK_CARRIERS dropping make_token.
_CANT_BLOCK_MODAL_BULLET = re.compile(r"•[^•\n]*?can'?t block", re.IGNORECASE)
_CANT_BLOCK_GRANT_QUOTE = re.compile(
    r'(?:has|have|enters with) "[^"]*?can\'?t block[^"]*"', re.IGNORECASE
)
# "Starting life total" (CR 103.4) payoff reference — a card that compares against /
# resets to the starting life total ("less than half their starting life total",
# "your life total becomes equal to your starting life total", "greater than your
# starting life total"). phase has no structure for this specific game value, so it
# survives only on the face oracle text. Anchored TIGHTLY on "starting life total"
# (the specific value) — NOT the broad regex's "life total is greater/less" second
# arm, which over-fires on unrelated life thresholds ("if your life total is less
# than 7" — Elderscale Wurm), which the structural IR correctly drops.
_STARTING_LIFE_REF = re.compile(r"\bstarting life total\b", re.IGNORECASE)
# Changeling (CR 702.73) / "is every creature type" — the all-tribes lane. phase
# rides the Scryfall `changeling` keyword for an INTRINSIC changeling, but DROPS the
# subtype on a "create a … Shapeshifter token WITH changeling" maker (the changeling
# lives in the token profile raw — Maskwood Nexus, Birthing Boughs), folds an
# "is/are every creature type" anthem/grant into a grant_keyword/pump carrier raw
# (Arachnoform, Amorphous Axe), or types the self-static as `type_set` / a place_
# counter (Mistform Ultimus, Omo's everything counter). Anchored on the literal
# "changeling" keyword OR the "(is|are|becomes) every creature type" phrase — both
# appear only on real all-tribes cards (no flavor/name collision).
_CHANGELING_REF = re.compile(
    r"\bchangeling\b|\b(?:is|are|becomes) every creature type\b", re.IGNORECASE
)
# Mass-death count operand (CR 700.4) payoff — a value/effect that SCALES with the
# number of creatures that died this turn ("a +1/+1 counter for each creature that
# died this turn", "a Treasure for each nontoken creature that died this turn",
# "connives X, where X is the number of creatures that died this turn"). phase
# parses the consequence (place_counter / make_token / connive / reanimate) but
# drops the "creatures that died this turn" operand. Anchored on the AGGREGATE
# ("for each" / "number of") shape — the board-wipe payoff the regex deliberately
# isolates — NOT the single-death conditional ("if a creature died this turn",
# morbid — Bone Picker, Tragic Slip), which is plain death_matters and would flood
# the lane. Mirrors the mass_death_payoff regex exactly (4 board-wipe commanders).
_MASS_DEATH_REF = re.compile(
    r"(?:for each|number of) (?:nontoken )?(?:creature|permanent)s?[^.]*died this turn",
    re.IGNORECASE,
)
# ADR-0027 (SIDECAR v40) — the whose-spell parse gap on a BecomesTarget trigger. phase
# usually carries the targeting source's controller on ``valid_source`` (an Or of
# StackSpell/StackAbility filters, each with a ``controller``), but for 3 cards (Reality
# Smasher, Swarm Shambler, Tectonic Giant) it emits a BARE StackSpell with no
# controller, dropping the "an opponent controls" restriction the text states. Recover
# it from the trigger's own description, anchored on the SOURCE phrase ("of a spell /
# ability … an opponent controls") so a SUBJECT-side "a creature an opponent controls
# becomes the target" (Shay Cormac / Willbreaker — those are read structurally from
# valid_card) is NOT swept. CR 702.21a.
_BECOMES_TARGET_SRC_OPP = re.compile(
    r"of (?:a |an )?(?:spell|ability)[^.]*?an opponent controls?", re.IGNORECASE
)

_SAC_COUNT = r"(?:a|an|another|two|three|any number of|x|\d+)"
_SAC_TYPE = r"(?:creature|artifact|permanent|enchantment|token|planeswalker)"
# A free-spell pitch ("you may sacrifice three black creatures rather than pay this
# spell's mana cost" — Flare of Denial, Salvage Titan, Delraich, Demon of Death's
# Gate, Dark Triumph). CR 118.9.
_PITCH_SAC = re.compile(
    rf"sacrifice {_SAC_COUNT}\b[^.]*?{_SAC_TYPE}[^.]*\brather than pay\b",
    re.IGNORECASE,
)
# A keyworded cost paid in a non-land sacrifice phase drops with the keyword cost:
# graveyard-cast ("Flashback—Sacrifice three creatures" — Dread Return; Cabal
# Therapy's flashback sac) and a morph turn-up ("Morph—Sacrifice another creature" —
# Gift of Doom). CR 702.34 / 702.37.
_KEYWORD_COST_SAC = re.compile(
    rf"(?:flashback|escape|buyback|morph|megamorph|disturb|embalm)\b[^.]*\bsacrifice "
    rf"{_SAC_COUNT}\b[^.]*?{_SAC_TYPE}",
    re.IGNORECASE,
)
