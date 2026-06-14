"""Deterministic signal extraction — the discovery-engine keystone.

A ``Signal`` is a precisely-scoped fact pulled from a card's oracle text: what it
cares about / triggers on, *whose* resource it concerns (scope), and — when the
clause names one — the *subject* it cares about (a creature subtype). Scope and
subject are part of the signal's identity, which is how we avoid overgeneralization:
a card that benefits from an opponent's graveyard yields ``graveyard_matters`` scoped
``opponents`` (never a generic one that would justify self-mill), and a Goblin lord
yields ``type_matters`` with ``subject="Goblin"`` (never collapsed into a generic
"creatures matter").

Three tiers, all keyless and precision-gated:

  1. **Baseline detectors** — the original substring/regex bag (creature_etb,
     graveyard_matters, …). Subject-free.
  2. **Parametric subject detectors** — ``type_matters`` / ``token_maker`` /
     ``typed_spellcast`` capture the subtype noun, singularize it, and validate it
     against the harvested creature-subtype vocabulary (``_subtypes``). An
     unresolvable capture emits nothing (silent drop = the safe failure mode), so
     clones / "Plant creature" / card-type words never become junk subjects.
  3. **Structural-anchor floor detectors + theme_presets reuse** — whole archetypes
     the baseline was blind to (treasure / artifacts / enchantments / tokens / stax),
     each requiring a ``X you control`` / ``for each X`` / ``whenever … enters`` /
     ``opponents can't`` anchor; plus a curated subset of ``theme_presets`` (blink /
     mill / goad / proliferate / magecraft / extra-combats / extra-turns).

One narrow structural scope rule (combat-damage-to-a-player + "that player's <zone>"
→ opponents) deterministically fixes the Tinybones bug without the broad
possessive→opponents rule that would misfire on self-blink/self-bounce cards.

``coverage_gate`` reports the extractor's own blind spots (zero-signal / only-generic
/ scope-uncertain) so the session-agent (M3, ADR-0009) can scope the residual tail
with mandatory oracle-clause quotes — blind spots are queued, never silently dropped.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import (
    CARD_TYPE_SUBJECTS,
    CREATURE_SUBTYPES,
    IRREGULAR_SINGULAR,
    NON_SUBJECT_WORDS,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.theme_presets import get_preset


@dataclass(frozen=True)
class Signal:
    """A scoped fact extracted from one card's oracle text."""

    key: str  # canonical signal id, e.g. "creature_etb"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: str  # subtype qualifier (e.g. "Goblin"); "" if none
    text: str  # the matched oracle clause (the quote, for grounding/scoping)
    source: str  # the card name the signal came from
    confidence: str = (
        "high"  # "high" | "low" — low = a scope guess the agent should confirm
    )


# ── Tier 1: baseline detectors ────────────────────────────────────────────────
# Each detector: (key, clause-matcher, forced_scope|None). When forced_scope is
# None the clause's own scope is used (critical for creature_etb / graveyard_matters).
def _has(*needles: str) -> Callable[[str], bool]:
    return lambda c: all(n in c for n in needles)


def _re(pattern: str) -> Callable[[str], bool]:
    rx = re.compile(pattern)
    return lambda c: rx.search(c) is not None


# creature_etb scope tracks who controls the ENTERING creature, never the payoff
# target: "another creature you control enters … deal 2 to each opponent" is YOUR
# go-wide engine (Purphoros), not an opponents-scoped punisher. Only an
# opponent-controlled entering creature is the punisher.
_ETB_OPP_RE = re.compile(
    r"creature an opponent controls enters"
    r"|creatures? your opponents? control enter"
    r"|creature[s]?[^.]*enters?[^.]*under (?:an |your )?opponent",
    re.IGNORECASE,
)
_ETB_ANY_RE = re.compile(
    r"\b(?:a|another|one or more|each)\b[^.]*\bcreature[s]?\b[^.]*\benter",
    re.IGNORECASE,
)
# ETB-trigger doublers (Panharmonicon / Yarok) are ETB-value commanders: they want
# ETB creatures, flicker, and more doublers, so route them to the creature_etb lane.
_ETB_DOUBLER_RE = re.compile(r"entering[^.]*triggers an additional time", re.IGNORECASE)


_DETECTORS: tuple[tuple[str, Callable[..., bool], str | None], ...] = (
    (
        "creature_etb",
        lambda c: (
            (
                (
                    _ETB_ANY_RE.search(c) is not None
                    and ("whenever" in c or "when " in c)
                )
                or _ETB_DOUBLER_RE.search(c) is not None
            )
            and _ETB_OPP_RE.search(c) is None
        ),
        "you",
    ),
    (
        "creature_etb",
        lambda c: (
            _ETB_OPP_RE.search(c) is not None and ("whenever" in c or "when " in c)
        ),
        "opponents",
    ),
    ("creatures_matter", _has("creatures you control"), "you"),
    # Type-matters: "land creature(s)" as a phrase. \b before "land" so "nonland
    # creature" / "Plant creature" / "island creature" do NOT register — only a
    # genuine land-creature reference (the Jyoti / Sylvan Advocate theme).
    (
        "land_creatures_matter",
        _re(
            r"\bland creatures?\b|lands? you control (?:are|become)\b"
            r"|all lands[^.]*become[^.]*creature"
            r"|target land[^.]*becomes? a[^.]*creature"
        ),
        None,
    ),
    (
        # Lifegain payoff ("whenever you gain life") OR the act of gaining life OR a
        # payoff that gates on HAVING gained life this turn ("if you gained life this
        # turn", "the amount of life you gained" — Aerith / Celestine / Lathiel).
        "lifegain_matters",
        _re(
            r"whenever[^.]*gain[^.]*life|you gain \d+ life|gain \d+ life"
            r"|you gained[^.]*life|life you gained"
            # Variable lifegain: "gain X life" (Atalya), "gain life equal to …" (Ayli).
            r"|gains? x life|gains? life equal to"
            # Lifegain amplifiers: "if you would gain life, you gain … instead"
            # (Bilbo, Boon Reflection, Rhox Faithmender, Alhammarret's Archive).
            r"|if you would gain life"
        ),
        "you",
    ),
    ("graveyard_matters", _has("graveyard"), None),
    # Exile-mill of OPPONENTS (Circu): "exile the top card of target player's library"
    # is a mill variant the graveyard ("graveyard"-keyed) detector misses. Scoped
    # opponents — exiling YOUR OWN library (impulse draw) never matches.
    (
        "graveyard_matters",
        _re(
            r"exile (?:the top|\w+ cards?|cards?)[^.]*"
            r"(?:target player'?s?|an opponent'?s?|each (?:player|opponent)'?s?"
            r"|that player'?s?) librar"
        ),
        "opponents",
    ),
    # Vanilla matters (Ruxa, Muraganda Petroglyphs): a commander rewarding "creatures
    # with no abilities" wants vanilla beaters.
    ("vanilla_matters", _re(r"creatures? (?:card )?with no abilities"), "you"),
    # Force-attack incentive (Kratos): "creatures that didn't attack this turn" punishes
    # not attacking — a goad/aggro commander that wants everyone swinging.
    ("forced_attack", _re(r"didn't attack this turn|that attacked this turn"), "you"),
    # Rewards-for-attacking-opponents (Gahiji, Frontier Warmonger): a creature that
    # attacks "one of your opponents" earns a buff. Goad forces opponents' creatures to
    # attack a player other than their controller — one of your OTHER opponents — which
    # fires the reward (CR 701.39). So such a commander wants goad effects.
    (
        "goad_matters",
        _re(r"attacks? one of your opponents|attacks? a player other than you"),
        "opponents",
    ),
    # Outlaw tribal (Outlaws of Thunder Junction): Assassins/Mercenaries/Pirates/Rogues/
    # Warlocks are collectively "outlaws" (Vial Smasher, Kellan).
    (
        "outlaw_matters",
        _re(r"\boutlaws?\b you control|another outlaw|outlaws? enter"),
        "you",
    ),
    # Pacify/control commander (Gwafa Hazid): neutralizing OTHER creatures so they
    # "can't attack or block" is a pillowfort/control identity wanting Propaganda.
    # Scoped to others (with/you-don't-control) so a Wall's self-restriction
    # ("this creature can't attack") doesn't qualify.
    (
        "stax_taxes",
        _re(
            r"creatures? (?:with|you don't control|an opponent controls)"
            r"[^.]*can't attack|can't attack you\b"
        ),
        "opponents",
    ),
    # Toughness-as-value payoffs beyond Doran's "assigns combat damage equal to
    # toughness" (already mined): a token/damage/value keyed on a creature's TOUGHNESS
    # (Geralf: "X is the sacrificed creature's toughness"). The "(?! are each)" guard
    # keeps set-base-P/T ("power and toughness are each equal to …") off the lane.
    (
        "toughness_combat",
        _re(
            r"\bx (?:is|equals?) [^.]{0,40}\btoughness\b"
            r"|equal to [^.]{0,40}\btoughness\b(?! are each)"
        ),
        "you",
    ),
    # Snow matters (Isu the Abominable, Yeti tribal): a commander referencing snow
    # permanents / lands / spells / mana opens the snow archetype.
    (
        "snow_matters",
        _re(
            r"\bsnow (?:permanent|land|spell|creature|mana)|for each snow"
            r"|affinity for snow"
        ),
        "you",
    ),
    # Activated-ability engine: a commander whose engine is a {T}: (or {Q}:) activated
    # ability (Arcum, Captain Sisay, Ertai, Kaho, Sanctum Weaver) wants the support
    # package — cost reducers (Training Grounds), untappers + haste-for-abilities
    # (Thousand-Year Elixir), and ability copiers (Rings of Brighthearth). The tap
    # symbol followed by a cost separator (":" or ",") is the activated-ability anchor.
    # {T}:/{Q}: tap abilities, plus mana-cost activated abilities with a generic-numeral
    # cost ("{2}{U}{B}: …" — The Scarab God, Kenrith). The generic numeral excludes
    # cheap colored-only firebreathing ("{R}: +1/+0"), which has its own pump lane.
    (
        "activated_ability",
        _re(r"\{t\}\s*[,:]|\{q\}\s*[,:]|\{(?:\d+|x)\}[^.\n]{0,18}:"),
        "you",
    ),
    # Reanimator PAYOFF: a trigger that rewards a creature ENTERING from a graveyard
    # (reanimation) or being CAST from a graveyard (escape/disturb) — Celes, Prized
    # Amalgam, Flayer of the Hatebound, River Kelpie. Distinct from graveyard_matters
    # above, which is the FUEL (fill your own yard / self-mill); this is the PAYOFF, and
    # it opens a reanimation-effects avenue, not a self-mill one. Forced "you": the deck
    # always reanimates / recasts from its OWN graveyard. The phrasing ("enters/cast
    # FROM a graveyard") never matches a plain reanimation spell ("…to the battlefield")
    # or a regrowth ("…to your hand"), so those stay enablers the avenue FINDS, not
    # payoff signals. Verified against bulk: 36 cards, all genuine.
    (
        "reanimator",
        _re(
            r"enter(?:s|ed)?(?: the battlefield)? from "
            r"(?:a|your|their|an? \w+'?s?) graveyard"
            r"|\bcast from (?:a|your|their) graveyard"
        ),
        "you",
    ),
    # Spellslinger cast trigger — but NOT when the only cast trigger is an *enchantment*
    # or *artifact* spell: those are enchantress / artifact-cast archetypes (Sythis,
    # Sai), routed to their own type lanes below, not to cheap instants/sorceries.
    (
        "spellcast_matters",
        lambda c: (
            (
                "whenever you cast" in c
                and "spell" in c
                and not _re(r"whenever you cast an (?:enchantment|artifact) spell")(c)
            )
            # Past-tense spell-COUNT payoff ("for each spell you've cast this turn" —
            # Gnostro, Rionya, Narset) the present-tense "whenever you cast" missed.
            or _re(r"spells? you've cast this turn")(c)
        ),
        "you",
    ),
    # Aristocrats: a "whenever … dies" trigger (CR 700.4: "dies" = put into a graveyard
    # from the battlefield), OR a death-trigger DOUBLER ("if a creature dying causes a
    # triggered ability … that ability triggers an additional time" — Teysa, Drivnod),
    # an aristocrats commander even without a literal "whenever … dies". Verified vs
    # bulk: the "dying"+"trigger" branch adds only ~5 cards, all death-doublers.
    (
        "death_matters",
        lambda c: (
            ("whenever" in c and "dies" in c)
            # Plural "creatures die" (Morbid Opportunist, Grave Pact-style) — the CR
            # term is "dies", but cards phrase mass death as "one or more creatures
            # die". Scoped to creature/permanent/token to avoid "roll a die" dice cards.
            # The "control" alternative handles the conjugation where "you control" sits
            # between the noun and the verb ("creatures you control die" — Vraan, Éomer,
            # G'raha Tia); the dice noun "die" follows an article ("a die", "sided
            # die"), never "control", so this stays off the dice cards.
            or _re(
                r"whenever [^.]*(?:creatures?|permanents?|tokens?|they|control) die\b"
            )(c)
            # Past-tense death COUNT payoff ("create a Treasure for each creature that
            # died this turn" / "if a creature died this turn") — a morbid/aristocrats
            # commander (Mahadi, Gadrak, Shessra) the present-tense "dies" branch lost.
            or _re(r"creatures? (?:that )?died this turn")(c)
            or ("dying" in c and "trigger" in c)
        ),
        None,
    ),
    ("sacrifice_matters", _re(r"sacrifice (?:a|an|another|two|three|x|\d)"), "you"),
    (
        "attack_matters",
        # Past-tense "attacked this turn" is a combat-count payoff (Relentless Assault,
        # Alesha) the present-tense "whenever … attack" trigger missed.
        lambda c: (
            ("whenever" in c and "attack" in c)
            or "attacking causes" in c
            or "attacked this turn" in c
        ),
        None,
    ),
    # Present "whenever you draw" OR the past-tense draw-COUNT payoff ("for each card
    # you've drawn this turn" — Proft's Eidetic Memory, Kydele, Thundering Djinn).
    (
        "draw_matters",
        lambda c: (
            "whenever you draw" in c
            or _re(r"(?:you've|you have) drawn (?:this turn|your|\d|two|three)")(c)
        ),
        "you",
    ),
    (
        # Landfall / lands-matter: the ability word, a land-enter trigger, extra land
        # drops, OR land RECURSION from the graveyard (Lord Windgrace, Crucible) — a
        # lands-matter commander even with no "landfall". Verified vs bulk: the
        # recursion branch opens the lane for ~31 cards, all genuine lands-matter.
        "landfall",
        lambda c: (
            "landfall" in c
            or ("whenever a land" in c and "enter" in c)
            or _re(r"play (?:an|one|two|three|\d+) additional lands?")(c)
            or _re(
                r"play lands? from your graveyard"
                r"|return [^.]*\blands?\b[^.]*from your graveyard to the battlefield"
            )(c)
        ),
        "you",
    ),
    (
        # Counter payoffs: "for each"/"number of" count-matters PLUS distributor
        # anchors (Mikaeus, Shalai and Hallar) that spread/reward counters without
        # the count phrasing — but NOT bare "put a +1/+1 counter on it" self-growth.
        "counters_matter",
        lambda c: (
            "+1/+1 counter" in c
            and (
                "for each" in c
                or "number of" in c
                or "on each creature you control" in c
                or "creatures you control with +1/+1 counter" in c
                # A VARIABLE count ("put X +1/+1 counters …") is a scaling counter
                # engine, not bare self-growth (Halana and Alena, Champion of Lambholt).
                or "x +1/+1 counter" in c
                # MULTI-counter placement ("put three +1/+1 counters on …" — plural)
                # is a counter engine; bare single self-growth ("put a +1/+1 counter on
                # it") stays out (Minsc & Boo, Hardened Scales decks).
                or "+1/+1 counters on" in c
                # Recurring placement on ANOTHER creature (Anafenza: "+1/+1 counter on
                # another target …") is an engine, not self-growth.
                or "+1/+1 counter on another" in c
            )
        ),
        None,
    ),
    # Combat-damage triggers (distinct from attack_matters, which keys on "attack").
    # Forced opponents — the damaged party is a player/opponent. The single biggest
    # zero-signal recovery (Edric, Dragonlord Ojutai, Wrexial, …).
    (
        "combat_damage_matters",
        _re(
            # "deals?" — singular subject ("a creature … deals") AND plural ("one or
            # more creatures you control deal combat damage", 200+ cards: Yarus, Gonti
            # Canny Acquisitor, Neheb the Eternal).
            r"\bwhen(?:ever)?\b[^.]*?\bdeals? combat damage to "
            r"(?:a player|an opponent|one of your opponents|each opponent"
            r"|a player or planeswalker|a player or battle)\b"
            # Passive form: a commander that cares about HAVING dealt combat damage
            # (Hope of Ghirapur: "player who was dealt combat damage by Hope") wants to
            # connect — it's a voltron/combat deck.
            r"|(?:was|were) dealt combat damage by"
        ),
        "opponents",
    ),
    # "whenever you discard" payoff OR a loot outlet ("draw a card, then discard").
    (
        "discard_matters",
        _re(r"whenever you discard|draw (?:a|two|three|x|\d+) cards?, then discard"),
        "you",
    ),
    # Life-loss / drain. Scope varies (opponents drain vs your own life-loss), so
    # forced_scope is None — the clause scope resolves it.
    (
        "lifeloss_matters",
        _re(
            r"\b(?:each opponent|each player|target opponent|target player|that player"
            r"|an opponent|each of your opponents|opponents?)"
            r"(?:\s+who\b[^.]{0,40}?)? loses? (?:\d+|x) life\b"
            r"|\bwhenever you (?:gain or )?lose life\b"
            r"|\bwhenever (?:an opponent|a player|one or more (?:players|opponents))"
            r" loses? life\b"
            # Past-tense life-loss COUNT payoff ("for each 1 life your opponents have
            # lost this turn" — Neheb, Rakdos Lord of Riots, Wound Reflection).
            r"|\blife [^.]*?lost this turn\b"
        ),
        None,
    ),
    # Pay-life / self life-loss as a resource (forced you — it's your life).
    ("lifeloss_matters", _re(r"pay \d+ life|you lose \d+ life"), "you"),
)


# card_draw_engine: a recurring/bulk card-advantage engine, NOT a cantrip. The bare
# "draw a card" must never fire — the single-card branch is gated behind a recurring
# "at the beginning of" anchor, and a one-shot ETB draw is skipped.
_CARD_DRAW_RE = re.compile(
    r"at the beginning of [^.]*\bdraws? "
    r"(?:a|an|two|three|four|five|six|seven|eight|nine|ten|x|\d+)\b[^.]*\bcard"
    r"|\bdraws? (?:two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?\b"
    r"|\bdraw cards equal to\b"
    r"|\bdraws? an additional card\b"
    r"|if you would draw a card, (?:instead )?draw "
    r"(?:two|three|four|five|six|seven|eight|nine|ten|x|\d+)",
    re.IGNORECASE,
)


def _detect_card_draw(clause: str) -> tuple[str, str] | None:
    if not _CARD_DRAW_RE.search(clause):
        return None
    cl = clause.lower()
    # Skip a one-shot ETB draw (not an engine) unless it's a recurring trigger too.
    if "when" in cl and "enters" in cl and "at the beginning of" not in cl:
        return None
    return ("card_draw_engine", "each" if "each player" in cl else "you")


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"(?<=[.;\n])\s+", text) if c.strip()]


def _scope(clause_lower: str) -> str:
    if "opponent" in clause_lower:
        return "opponents"
    if "each player" in clause_lower:
        return "each"
    if (
        "you control" in clause_lower
        or "your " in clause_lower
        or re.search(r"\byou\b", clause_lower)
    ):
        return "you"
    return "any"


# ── Tier 2: parametric subject detectors ──────────────────────────────────────


def _singularize(raw: str) -> str:
    """Lowercase + best-effort singularize a captured noun. The (\\w+?)s? capture
    can emit a partial plural ("Elve", "Dwarve"), so we map those explicitly."""
    w = raw.lower().strip(",.")
    if w in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    if w.endswith("ve") and len(w) > 3 and w not in ("cave", "wave", "brave"):
        return w[:-2] + "f"
    # Never strip the trailing "s" of an "-us" word: Fungus / Octopus / Pegasus /
    # Homunculus are SINGULAR subtypes (their plurals are "Fungi" etc., mapped above).
    if w.endswith("s") and len(w) > 1 and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def _resolve_subject(raw: str, vocab: frozenset[str]) -> str:
    """Resolve a raw capture to a canonical kindred subject, or "" (silent drop).

    Card-type words ("creature"/"permanent") and card-type subjects
    ("artifact"/"land", handled by the floor detectors) never become a kindred
    subject — they fall through to the generic / floor keys. This is the precision
    gate: an unparseable or non-kindred noun produces zero false positives.
    """
    w = _singularize(raw)
    if w in NON_SUBJECT_WORDS or w in CARD_TYPE_SUBJECTS:
        return ""
    if w in vocab:
        return w.capitalize()
    return ""


# type_matters: the subject NOUN is captured. Every pattern requires a structural
# "you control" / "for each" anchor — never a bare noun. IGNORECASE is load-bearing
# (sentence-initial "Other Dwarves" else drops Magda).
_TYPE_MATTERS_PATTERNS = (
    re.compile(r"\bother ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    # "another Elf you control" (singular) — tribal triggers the "other Xs" form misses.
    re.compile(r"\banother ([A-Za-z]+?) you control\b", re.IGNORECASE),
    # "a Spider you control enters/attacks/dies/deals …" — tribal trigger. A common
    # trigger verb follows (so a bare "a Goblin you control" can't over-capture); the
    # vocab gate drops "creature"/"permanent". Mary Jane Watson / Patron of the Nezumi
    # ("a Rat you control deals") / Sylvia ("a Dragon you control attack").
    re.compile(
        r"\b(?:a|an) ([A-Za-z]+?) you control "
        r"(?:enters|attacks?|dies|deals|blocks?|becomes?|leaves)\b",
        re.IGNORECASE,
    ),
    # "each attacking Samurai" / "attacking Goblins" — tribal combat trigger (Nagao).
    re.compile(r"\b(?:each )?attacking ([A-Za-z]+?)s?\b", re.IGNORECASE),
    # "you control an Army" — reverse word order the "X you control" anchors miss; the
    # subtype-vocab gate keeps it precise (creature/artifact/Mountain drop out). Grond.
    re.compile(r"\byou control (?:a|an) ([A-Za-z]+?)\b", re.IGNORECASE),
    # "becomes a Samurai in addition to its other creature types" — type-granting that
    # adds a kindred subject (the "in addition" anchor keeps it off clone/animate).
    re.compile(r"\bbecomes? an? ([A-Za-z]+?) in addition\b", re.IGNORECASE),
    # "Other Elf creatures have …" (lord with no "you control"); tribal in an
    # activated cost ("untapped Wizard you control:" / "<Sub> you control:").
    re.compile(r"\bother ([A-Za-z]+?) creatures?\b", re.IGNORECASE),
    re.compile(r"\buntapped ([A-Za-z]+?) you control\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?) you control\s*:", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?)s? you control gets? [+\-](?:\d|x)", re.IGNORECASE),
    re.compile(r"\b(?:number of|for each) ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    # Keyword-grant lord: "have"/"has" (static) and "gain"/"gains" (granted) — "Spirits
    # you control gain flying", "Knights you control gain double strike". The subtype
    # vocab gate keeps the generic "Creatures you control gain …" out.
    re.compile(r"\b([A-Za-z]+?)s? you control (?:ha(?:ve|s)|gains?)\b", re.IGNORECASE),
    # Global lords with no "you control" / "other": "Bird creatures get +1/+1"
    # (Soraya) or the singular "Each Fungus creature gets +1/+1" (Thelon). The
    # subtype-vocab gate drops "all"/"other"/"creature" so only a real tribe sticks.
    re.compile(r"\b([A-Za-z]+?) creatures? gets? [+\-](?:\d|x)", re.IGNORECASE),
    # Multiplayer "your team controls" (Sylvia: "Dragons your team controls have …").
    re.compile(
        r"\b([A-Za-z]+?)s? your team controls? (?:have|has|get|gain)\b", re.IGNORECASE
    ),
    # Offering mechanic (Patron cycle): "Rat offering" / "Dragon offering" sacrifices a
    # tribe member to cast — so the commander is that tribe.
    re.compile(r"\b([A-Za-z]+) offering\b", re.IGNORECASE),
    # "for each Rat on the battlefield" — a tribal count payoff with no "you control"
    # (Patron's discard channel counts Rats). Vocab gate keeps it to real tribes.
    re.compile(
        r"\bfor each ([A-Za-z]+?)s? (?:on the battlefield|you control)\b", re.IGNORECASE
    ),
)
# typed_spellcast: subject-bearing extension of spellcast_matters — catches tribal
# spell payoffs ("Sliver spells you cast") the literal spellcast_matters misses.
_TYPED_SPELLCAST_PATTERN = re.compile(
    r"\b([A-Za-z]+?)s? spells? you cast\b", re.IGNORECASE
)
# token_maker: capture the LAST creature subtype before "creature token(s)",
# preferring a real subtype over the card-type word "artifact"
# ("Thopter artifact creature token" → Thopter).
_TOKEN_MAKER_PATTERN = re.compile(r"create [^.]*?\bcreature tokens?\b", re.IGNORECASE)
_TOKEN_SUBJECT_WORDS = re.compile(r"\b([A-Z][a-z]+)\b")


def _detect_type_matters(clause: str, vocab: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pat in _TYPE_MATTERS_PATTERNS:
        for m in pat.finditer(clause):
            subject = _resolve_subject(m.group(1), vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    return out


# Multi-tribe anthem: "each creature that's a Barbarian, a Warrior, or a Berserker gets
# +2/+2" (Lovisa) — a multi-tribe lord. Emit type_matters for EVERY named type so each
# tribe's creatures surface; the single-type patterns above require "other"/"you
# control" and miss this "that's a X, a Y, or a Z" form. The vocab gate drops the
# connective words ("a"/"or"/"and"/"attacking"), keeping only real subtypes.
_MULTI_TRIBE_HEAD_RE = re.compile(
    r"creatures? (?:you control )?that(?:'s| is| are)\b(.{0,80}?)"
    r"\b(?:gets?|have|has|gains?)\b",
    re.IGNORECASE,
)


def _detect_multi_tribe_anthem(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _MULTI_TRIBE_HEAD_RE.finditer(clause):
        for word in re.findall(r"[A-Za-z]+", m.group(1)):
            subject = _resolve_subject(word, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    return out


def _detect_typed_spellcast(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _TYPED_SPELLCAST_PATTERN.finditer(clause):
        subject = _resolve_subject(m.group(1), vocab)
        if subject:
            out.append((signal_keys.TYPED_SPELLCAST, subject))
    return out


def _detect_token_maker(clause: str, vocab: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _TOKEN_MAKER_PATTERN.finditer(clause):
        head = re.split(r"creature tokens?", m.group(0), flags=re.IGNORECASE)[0]
        chosen = ""
        for w in reversed(_TOKEN_SUBJECT_WORDS.findall(head)):
            if w.lower() in vocab:
                chosen = w.capitalize()
                break
        out.append((signal_keys.TOKEN_MAKER, chosen))
    return out


# Typed graveyard recursion: "return target <Type> card from your graveyard to the
# battlefield" (Greasefang → Vehicle) is a dedicated deck for <Type>. Resolve the
# captured type to its matters signal — vehicles_matter for Vehicle, type_matters for a
# creature subtype — but NOT for the generic card-type words (creature/permanent/
# artifact), which are plain reanimation, not a typed-recursion theme.
_TYPED_GY_RECUR_PATTERN = re.compile(
    r"\breturn (?:target |all |each |up to \w+ target )?([A-Za-z]+) cards?\b"
    r"[^.]*from (?:your|a) graveyard[^.]*(?:to|onto) the battlefield",
    re.IGNORECASE,
)


def _detect_typed_gy_recursion(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for m in _TYPED_GY_RECUR_PATTERN.finditer(clause):
        raw = m.group(1).lower()
        if raw == "vehicle":
            out.append(("vehicles_matter", "you", ""))
            continue
        subject = _resolve_subject(m.group(1), vocab)
        if subject:
            out.append((signal_keys.TYPE_MATTERS, "you", subject))
    return out


# Keyword abilities whose presence implies a creature-subtype tribal theme the literal
# "<Subtype>s you control" patterns miss. Ninjutsu (CR 702.49) is ONLY granted to/by
# Ninjas, so a ninjutsu commander (Yuriko, Satoru, Higure — whose text never says
# "Ninjas you control") is a Ninja-tribal deck; emit type_matters:Ninja so the tribal
# bodies + lords/equipment/ETB payoffs surface alongside the existing ninjutsu_matters.
_KEYWORD_IMPLIES_TRIBE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bninjutsu\b"), "Ninja"),
)


def _detect_keyword_implied_tribe(clause: str) -> list[tuple[str, str]]:
    return [
        (signal_keys.TYPE_MATTERS, subj)
        for pat, subj in _KEYWORD_IMPLIES_TRIBE
        if pat.search(clause)
    ]


# ── Tier 3: structural-anchor floor detectors + theme_presets reuse ────────────


@dataclass(frozen=True)
class Detector:
    """A compiled floor/sweep detector: a regex over a clause → a scoped signal key.
    The single record type the extractor's Tier-3 loop consumes, whether the source
    is a curated hand-written rule or a row of the exhaustively-mined sweep table."""

    key: str
    scope: str  # forced scope ("you" | "opponents" | "each" | "any")
    pattern: re.Pattern[str]


# Each floor detector requires a structural anchor, never a bare substring, so
# incidental one-shot makers (Beledros, Faramir) and self-restrictions (Kefnet)
# don't misfire. Hand-written source stays as (key, compiled-pattern, scope) tuples;
# the assembly below adapts both these and the mined sweep into Detector records.
_HAND_FLOOR: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "treasure_matters",
        re.compile(
            r"create (?:a|an|one|two|three|four|five|\d+|x)[^.]*?\btreasure token"
            r"|\btreasures? you control\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "artifacts_matter",
        re.compile(
            r"\bartifacts? you control\b"
            r"|artifact creatures? you control"
            r"|for each artifact you control"
            r"|whenever an? artifact (?:you control )?enters"
            # Artifact-cast / affinity / artifact-recursion commanders are artifact
            # decks (Sai, Emry); affinity's reminder is stripped, so key on the keyword.
            r"|whenever you cast an artifact|\baffinity\b"
            r"|artifact (?:card|spell)[^.]*(?:from|in)[^.]*graveyard"
            # Sac outlets (Bosh), artifact-ability payoffs (Kurkesh), and type-granters
            # (Memnarch: "becomes an artifact") are artifact commanders too. The sac
            # lookahead drops the generic any-permanent list ("sacrifice an artifact,
            # creature, enchantment …" — Braids), which is an aristocrats outlet.
            r"|sacrifices? (?:an?|another|two|three|x|\d+) artifacts?\b"
            r"(?!,? (?:or )?(?:an? )?(?:creature|enchantment|land|permanent))"
            r"|abilit(?:y|ies) of (?:an? )?artifacts?\b"
            r"|becomes? an? artifact\b"
            # Artifact-TOKEN makers are artifact commanders: Treasure / Food / Clue /
            # Blood / Gold / etc. are artifact tokens (CR 205.3g), so a maker feeds
            # affinity / metalcraft / Academy Manufactor (Goldspan, Gyome, Korvold).
            r"|create[^.]*\b(?:treasure|food|clue|blood|gold|map|powerstone"
            r"|junk|incubator|lander)\b[^.]*token"
            # Metalcraft (CR 207.2c ability word: "control three or more artifacts") is
            # an artifacts deck; the italic word prints in the oracle, so match it.
            r"|\bmetalcraft\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "enchantments_matter",
        re.compile(
            r"\benchantments? you control\b"
            r"|for each enchantment you control"
            r"|whenever an? enchantment (?:you control )?enters"
            # Enchantress: "whenever you cast an enchantment spell" (Sythis, the
            # Enchantress cycle) — the core payoff, previously sent to spellslinger.
            r"|whenever you cast an enchantment",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "tokens_matter",
        re.compile(
            r"\btokens? you control\b"
            r"|whenever (?:a|one or more|another)[^.]*?\btokens?\b[^.]*?\benters?\b"
            # A token DOUBLER (Adrix, Parallel Lives) wants token-MAKERS to double, so
            # it is a tokens commander — open the lane that surfaces them.
            r"|tokens? would be (?:created|put)|create twice that many[^.]*token"
            r"|twice that many[^.]*tokens?",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "stax_taxes",
        re.compile(
            r"\bopponents? can't\b"
            r"|spells your opponents cast cost"
            r"|creatures your opponents control",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    (
        "cost_reduction",
        re.compile(
            r"\b(?:spells?|each spell) you cast\b[^.]{0,80}?"
            r"\bcosts?\b[^.]{0,40}?\bless\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Cast-from-exile MATTERS: payoffs and enablers that cast/play cards FROM EXILE
    # (plot, suspend, "whenever you cast a spell from exile", paradox). Two neighbours
    # are deliberately NOT here: impulse draw (exile-top + temporary play) is its own
    # avenue (the impulse_top_play sweep), and playing off the top of your LIBRARY
    # (Future Sight) is `play_from_top` below — a different zone, not exile.
    (
        "cast_from_exile",
        re.compile(
            r"top card of your library has plot"
            r"|(?:whenever|each time) you (?:cast a spell|play a (?:card|land)"
            r"|play a land or cast a spell)[^.]*?from exile"
            r"|spells? you cast from exile"
            r"|you may (?:play|cast) (?:it|that card|this card|those cards?|them)"
            r"[^.]*?(?:for as long as it remains exiled|from exile)"
            r"|you may play (?:a |that )?card[^.]*?from exile"
            # Paradox (CR 207.2c): zone-agnostic "from anywhere other than your hand"
            # payoffs (Vega, Iraxxa) — the literal-"from exile" branches miss 16/17.
            r"|(?:cast a spell|play a land|play a card)[^.]*?"
            r"from anywhere other than your hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Play from the TOP OF YOUR LIBRARY (Future Sight, Bolas's Citadel, Oracle of Mul
    # Daya). Casts from the LIBRARY zone — not exile — so it's neither impulse nor
    # cast-from-exile. Requires a play/cast verb so look/scry/surveil/mill ("look at ...
    # from the top of your library", Stargaze) don't match.
    (
        "play_from_top",
        re.compile(
            r"(?:play|cast)\b[^.]*?\bfrom the top of your library",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "lands_matter",
        re.compile(
            r"(?:the number of|for each) (?:basic )?lands? you control", re.IGNORECASE
        ),
        "you",
    ),
    (
        "direct_damage",
        re.compile(
            r"deals? (?:\d+|x) damage to any target"
            r"|\{t\}[^.]*?:[^.]*?deals? (?:\d+|x) damage"
            # Tap-ping with a non-literal amount ("{T}: deals damage … equal to half …"
            # — Heartless Hidetsugu): still a repeatable pinger.
            r"|\{t\}[^.]*?:[^.]*?deals? damage to (?:each|any|target|that)"
            r"|would deal damage[^.]*?(?:it deals double|it deals twice"
            r"|deals that much damage plus)"
            # Land/mana PUNISHER (Zo-Zu): "whenever a land enters / a player taps a land
            # … deals N damage" — the opponents-landfall-punish side (Ankh, Manabarbs).
            r"|whenever (?:a|each) (?:player taps a )?land(?: enters| for mana)?"
            r"[^.]*?deals? (?:\d+|x) damage"
            # Damage-matters commander: "whenever a (red) source you control deals
            # damage …" wants to deal lots of damage (The Red Terror, Toralf).
            r"|whenever a (?:\w+ )?source you control deals damage",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "mana_amplifier",
        re.compile(
            r"tap(?:ped)? (?:a |an |another |each |any )?[^.]*?for mana[^.]*?"
            r"(?:add (?:an additional|one mana of any|that much|twice)"
            r"|produces? (?:twice|an additional))",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    (
        "voltron_matters",
        re.compile(
            r"\bfor each (?:equipment|aura|role)\b[^.]*?\b(?:attached|you control)\b"
            r"|\battach (?:target |all |any number of |up to one target |an |a )?"
            r"(?:equipment|aura)"
            r"|attach (?:any number of |all )?"
            r"(?:auras? and equipment|equipment and auras?)"
            r"|search your library for an? (?:equipment|aura)"
            r"(?: or (?:equipment|aura|vehicle))? card"
            r"|(?:equipment|auras?) you control have equip"
            r"|equip (?:abilities|costs?)[^.]{0,40}?(?:cost|costs?)[^.]{0,20}?less"
            r"|spend this mana only to cast (?:an? )?(?:aura|equipment)"
            r"|whenever you attach (?:a |an )?(?:equipment|aura|role)"
            r"|whenever an? (?:equipment|aura) (?:you control )?enters"
            r"|as long as \w+ is equipped|\bequipment you control\b"
            r"|pay [^.]*equip cost"
            # A commander that rewards / cares about "equipped creatures" (PLURAL — the
            # Equipment payload "Equipped creature gets…" is singular, so this stays off
            # gear) or moves Equipment around (Akiri: "unattach an Equipment").
            r"|equipped creatures\b|\bunattach\b"
            # Sram / Galea / Danitha: a CAST-trigger or cast-from-top keyed on Aura/
            # Equipment spells (CR 601 cast) — the deck IS a voltron deck even though
            # the wording is "cast an Aura/Equipment", not "attach"/"equipped".
            r"|cast an? (?:aura|equipment)|cast aura and equipment"
            r"|whenever you cast an aura, equipment"
            # Aura/Equipment cost reducers (Danitha, Galea): "Aura and Equipment spells
            # you cast cost {1} less" is a voltron payoff, not generic cost reduction.
            r"|(?:aura|equipment)[^.]*spells? you cast cost"
            # Hakim: Aura RECURSION onto a creature ("return … Aura … attached") — aura
            # voltron even though the wording isn't "attach an Aura".
            r"|(?:return|put)[^.]*\baura\b[^.]*\battached\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "vehicles_matter",
        re.compile(
            r"\bvehicles you control\b|\bmounts? and vehicles?\b"
            r"|\bvehicle you control enters\b|\bcrews a vehicle\b"
            r"|\bwhenever[^.]*\bcrews?\b"
            r"|\b(?:mount|equipment) or vehicle (?:card|spell)\b"
            r"|\bvehicle or artifact (?:creature )?(?:card|spell)\b"
            r"|create [^.]*\bvehicle artifact (?:creature )?token\b"
            # Vehicle GRANTERS (Captain Rex Nebula: "becomes a Vehicle … gains crew")
            # care about Vehicles too, even without "Vehicles you control".
            r"|\bbecomes? a vehicle\b|\bgains? crew\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "scry_surveil_matters",
        re.compile(
            r"whenever you scry or surveil\b|whenever you (?:scry|surveil)\b"
            r"|if you would scry (?:a number of cards|\d)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Named-mechanic long tail (precise named anchors → novel build-arounds) ───
    ("monarch_matters", re.compile(r"\bthe monarch\b", re.IGNORECASE), "you"),
    ("initiative_matters", re.compile(r"\bthe initiative\b", re.IGNORECASE), "you"),
    (
        "ring_matters",
        re.compile(r"ring tempts you|your ring-bearer|the ring-bearer", re.IGNORECASE),
        "you",
    ),
    (
        "venture_matters",
        re.compile(
            r"venture into the dungeon|complete a dungeon|\bdungeon\b", re.IGNORECASE
        ),
        "you",
    ),
    ("energy_matters", re.compile(r"\{e\}|energy counters?", re.IGNORECASE), "you"),
    ("devotion_matters", re.compile(r"devotion to \w", re.IGNORECASE), "you"),
    (
        "superfriends_matters",
        re.compile(
            r"planeswalkers? you control|loyalty counters?"
            r"|activate (?:a |one )?loyalty|one or more loyalty",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("historic_matters", re.compile(r"\bhistoric\b", re.IGNORECASE), "you"),
    (
        "legends_matter",
        re.compile(
            r"legendary creatures? you control"
            r"|whenever (?:a|another) legendary (?:creature|permanent)[^.]*you control"
            r"|whenever you cast a legendary|for each legendary (?:creature|permanent)"
            r"|cast legendary|legendary (?:creature|permanent|spell)s? you cast"
            r"|legendary spells?",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "big_hand_matters",
        re.compile(
            r"no maximum hand size|maximum hand size"
            r"|(?:five|six|seven|eight) or more cards in your hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "party_matters",
        re.compile(
            r"\byour party\b|members? of your party|full party"
            r"|assemble[^.]*party|creatures? in your party",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "exile_matters",
        re.compile(
            r"cards? (?:you own )?(?:that are )?in exile"
            r"|for each card (?:you own )?(?:in )?exile",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("experience_matters", re.compile(r"experience counters?", re.IGNORECASE), "you"),
    (
        "poison_matters",
        re.compile(
            r"poison counters?|\bpoisonous\b|\btoxic\b|\binfect\b", re.IGNORECASE
        ),
        "opponents",
    ),
    ("modified_matters", re.compile(r"\bmodified\b", re.IGNORECASE), "you"),
    ("mutate_matters", re.compile(r"\bmutate\b", re.IGNORECASE), "you"),
    (
        # Anchor on the Food-token mechanic (CR 111.10), like its sibling token axes,
        # not the bare word.
        "food_matters",
        re.compile(
            r"\bfood token|create (?:a|an|one|two|three|x|\d+)[^.]*?\bfood\b"
            r"|sacrifice a food|foods? you control",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("clue_matters", re.compile(r"\bclue\b|\binvestigate\b", re.IGNORECASE), "you"),
    ("blood_matters", re.compile(r"blood tokens?", re.IGNORECASE), "you"),
    (
        "daynight_matters",
        re.compile(
            r"\bdaybound\b|\bnightbound\b|it becomes night"
            r"|day becomes night|night becomes day|as long as it's (?:day|night)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "voting_matters",
        re.compile(
            r"will of the council|council's dilemma|each player votes?|\bvote\b",
            re.IGNORECASE,
        ),
        "each",
    ),
    ("coven_matters", re.compile(r"\bcoven\b", re.IGNORECASE), "you"),
    (
        "doubling_matters",
        re.compile(
            r"double the (?:number|amount)|create twice that many"
            r"|would (?:create|put|draw|gain|deal)[^.]*\binstead\b"
            r"[^.]*(?:twice|double|that many plus)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "second_spell_matters",
        re.compile(
            r"second spell you cast (?:each|this) turn|cast your second spell"
            r"|(?:second|third|fourth|fifth) spell (?:you cast|of (?:a|each|that) turn)"
            r"|cast two or more spells",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "opponent_cast_matters",
        re.compile(
            r"whenever an opponent casts|whenever (?:a|another) player casts a spell"
            r"|whenever an opponent cast",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    (
        "opponent_draw_matters",
        re.compile(
            r"whenever an opponent draws|whenever each opponent draws"
            r"|whenever a player draws a card (?:except|other than)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # Punish opponents' library manipulation (River Song's Spoilers; Aven
    # Mindcensor / Opposition Agent / Leovold space) — distinct from your own
    # scry_surveil payoff, which is scoped "you".
    (
        "opponent_search_matters",
        re.compile(
            r"whenever (?:an opponent|a player|each opponent)[^.]*"
            r"(?:scries|surveils|searches (?:their|a) library"
            r"|shuffles (?:their|a) library)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # ── Mechanics recovered from the "rejected" families (still-zero commanders) ──
    (
        "token_copy_matters",
        re.compile(
            r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of"
            r"|create a token that's a copy",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("specialize_matters", re.compile(r"\bspecialize\b", re.IGNORECASE), "you"),
    (
        "dice_matters",
        re.compile(
            r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)"
            r"|result of (?:the|a|your) (?:roll|die)|whenever you roll",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "crimes_matter",
        re.compile(r"commit(?:s|ted)? a crime|whenever you commit", re.IGNORECASE),
        "you",
    ),
    ("connive_matters", re.compile(r"\bconnives?\b", re.IGNORECASE), "you"),
    (
        "spell_copy_matters",
        re.compile(
            r"copy target (?:instant or sorcery spell|spell)|\bcopy that spell\b"
            r"|you may copy (?:it|that spell)|whenever you copy (?:a|an|target|that)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Effect-axis detectors: every ability is a direction to build around ──────
    (
        "ramp_matters",
        re.compile(
            r"\{t\}[^.]*:\s*add \{|add (?:one|two|three|four|five|x|\d+) mana"
            r"|add \{[wubrgc]\}",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Destroy/damage removal — the slice that indestructible & regeneration blank
        # (CR 701.8/702.12/702.19). Exile is a separate axis (bypasses those).
        "removal_matters",
        re.compile(
            r"destroy target "
            r"(?:creature|permanent|artifact|enchantment|planeswalker|nonland)"
            r"|deals? (?:\d+|x) damage to target (?:creature|permanent)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Exile removal — bypasses indestructible/regeneration and stops death/LTB
        # recursion (CR 406, 701.10). Distinct build axis from destroy/damage.
        "exile_removal",
        re.compile(
            r"exile target (?:creature|permanent|artifact|enchantment|nonland)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Allow an adjective gap so "counter target CREATURE spell" / "noncreature
        # spell" fire (Essence Scatter, Negate were missed by the keyword-immediately-
        # after-"target" anchor). The serve is already FP-free at this breadth.
        "counter_control",
        re.compile(r"counter target (?:[a-z-]+ )*(?:spell|ability)", re.IGNORECASE),
        "you",
    ),
    (
        "team_buff",
        re.compile(
            r"(?:creatures?|permanents?) you control (?:gain|gains|have|has) "
            r"(?:flying|trample|menace|hexproof|indestructible|protection|deathtouch"
            r"|lifelink|double strike|first strike|vigilance|haste|ward|reach)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "tutor_matters",
        re.compile(
            r"search your library for (?:a|an|up to|one|two|three|x|that)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "untap_engine",
        re.compile(
            r"untap (?:target|another target|all|each|two|up to)", re.IGNORECASE
        ),
        "you",
    ),
    ("gain_control", re.compile(r"gain control of", re.IGNORECASE), "you"),
    (
        "opponent_discard",
        re.compile(
            r"(?:each opponent|target opponent|an opponent|that opponent"
            r"|target player|that player|each player) discards",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # "deals damage to an opponent" — ANY damage (not the literal "combat damage" the
    # combat_* keys require, per the rules-lawyer audit). The connect-trigger axis for
    # self-source pingers/evasion (Lu Xun, Zhang Liao) the tribe/combat keys miss.
    (
        "damage_to_opp_matters",
        re.compile(
            r"\bwhen(?:ever)?\b[^.]*?\bdeals (?:noncombat )?damage to "
            r"(?:a player|an opponent|one of your opponents|each opponent"
            r"|target opponent|that player|a player or planeswalker)\b",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # "another permanent you control enters" — the generic permanent-ETB value engine
    # (distinct from creature_etb, which needs the word "creature"). Amareth.
    (
        "permanent_etb",
        re.compile(
            r"\bwhen(?:ever)?\b[^.]*?\b(?:a|an|another|one or more|each) "
            r"(?:nonland |nontoken )?permanents? you control enters",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Evasion = a blocking RESTRICTION (CR 509.1b). "attacks if able" is a
        # forced-attack REQUIREMENT (CR 508.1d) — that belongs to forced_attack/goad.
        # Landwalk (CR 702.14) is conditional unblockable-by-that-land-type evasion.
        # The keyword-only evasion words (horsemanship 702.31, menace 702.111, fear
        # 702.36, intimidate 702.13, skulk 702.118) carry their "can't be blocked …"
        # only in reminder text, which is stripped above — so the bare keyword is all
        # that survives (Guan Yu's horsemanship). "shadow" (702.28) is deliberately
        # EXCLUDED here: it collides with card-name self-references in oracle text
        # ("Whenever Shadow the Hedgehog…", Rasaad Shadow Monk) — the serve still
        # credits real Shadow-keyword cards via the exact keyword[] match.
        "evasion_self",
        re.compile(
            r"can't be blocked|\bunblockable\b"
            r"|\b(?:forest|island|mountain|plains|swamp)walk\b"
            r"|\b(?:horsemanship|menace|fear|intimidate|skulk)\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Clone = a permanent that itself becomes/enters as a copy (CR 707). Drop the
        # bare "copy of target creature" branch — it bleeds into the token-copy phrase
        # "create a token that's a copy of target creature" (that's token_copy_matters).
        # "becomes?" catches the bare infinitive ("have Gogo become a copy of …").
        "clone_matters",
        re.compile(
            r"becomes? a copy of|enters [^.]*as a copy of",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "cheat_into_play",
        re.compile(
            r"put [^.]*creature card[^.]*onto the battlefield"
            r"|put (?:a|that|those) [^.]*onto the battlefield from your "
            r"(?:hand|library)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "bounce_tempo",
        re.compile(
            r"return target (?:creature|permanent|nonland)[^.]*"
            r"to (?:its|their) owner's hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("cascade_matters", re.compile(r"\bcascade\b", re.IGNORECASE), "you"),
    ("regenerate_matters", re.compile(r"\bregenerate\b", re.IGNORECASE), "you"),
    # ── Keyword-coverage audit (CR 702/701) keyword[]-anchored avenues ──────────
    # Each fires on a commander/card that bears or cares about the keyword; the matching
    # SPECS entry serves the keyword[] bearers (authoritative) plus the payoff phrasing.
    # Madness (CR 702.35): discard to cast — discard_matters covers only 1/61.
    ("madness_matters", re.compile(r"\bmadness\b", re.IGNORECASE), "you"),
    # Speed / Max speed (CR 702.179/702.178, Aetherdrift): max-speed payoffs unsurfaced.
    (
        "speed_matters",
        re.compile(r"start your engines|max speed|your speed", re.IGNORECASE),
        "you",
    ),
    # Discover (CR 701.57): cascade-like dig — surface discover sources + low-MV spells.
    (
        "discover_matters",
        re.compile(
            r"\bdiscover \d|\bdiscover x\b|whenever you discover", re.IGNORECASE
        ),
        "you",
    ),
    # Foretell (CR 702.143): the foretold-card payoff/engine axis (Alrund, Ranar).
    ("foretell_matters", re.compile(r"\bforetell\b|foretold", re.IGNORECASE), "you"),
    # Undying (702.93) / Persist (702.79): death-triggered self-return + their granters.
    (
        "undying_persist_matters",
        re.compile(r"\b(?:undying|persist)\b", re.IGNORECASE),
        "you",
    ),
    # -1/-1 counters (CR 122 / 702.80 Wither / 702.90 Infect): the symmetric counter
    # axis counters_matter (hard-pinned to +1/+1) leaves homeless — Hapatra aristocrats.
    ("minus_counters_matter", re.compile(r"-1/-1 counter", re.IGNORECASE), "you"),
    # Cycling (CR 702.29): payoffs use "cycle or discard"; discard_matters serves 0/32.
    (
        "cycling_matters",
        re.compile(
            r"whenever you cycle|cycles? or discard"
            r"|whenever (?:a player|another player) cycles",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Kicker (CR 702.33): "cast a kicked spell" payoffs; spellcast_matters serves 0/10.
    (
        "kicked_spell_matters",
        re.compile(
            r"whenever you cast a kicked spell|if (?:that|it) (?:spell )?was kicked",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Colorless / Devoid / Eldrazi (CR 702.114): colorless-payoff axis (anthems / cost
    # reduction / cast-triggers) keyed on "colorless creature|spell|permanent".
    (
        "colorless_matters",
        re.compile(r"colorless (?:creature|spell|permanent)", re.IGNORECASE),
        "you",
    ),
    # Exalted (CR 702.83): rewards attacking ALONE — the attacks-alone payoff/trigger.
    (
        "exalted_lone_attacker",
        re.compile(r"attacks alone|\bexalted\b", re.IGNORECASE),
        "you",
    ),
    # Flash (CR 702.8): flash-GRANTING enablers ("cast … spells … as though they had
    # flash" — class grant, NOT the one-shot "as though IT had flash") + opponent-turn
    # cast payoffs. spellslinger's serve is instant/sorcery + prowess/magecraft and
    # excludes creatures, so it never surfaces a flash wantlist (creatures/granters).
    (
        "flash_matters",
        re.compile(
            r"cast[^.]{0,60}spells?[^.]{0,30}as though they had flash"
            r"|whenever you cast (?:a |your first )?spells? "
            r"during (?:an|each|any) opponent",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Team evasion-keyword grants (CR 702.13/702.14/509): "creatures you control
    # gain/have <evasion keyword>". evasion_self covers single-attacker/landwalk/team
    # can't-be-blocked but misses the keyword grants (menace/fear/horsemanship/…).
    (
        "team_evasion_grant",
        re.compile(
            r"(?:other |attacking )?creatures you control (?:gain|have)\b"
            r"[^.]{0,40}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk"
            r"|flying|can't be blocked)\b"
            r"|(?:other |attacking )?creatures you control[^.]*can't be blocked",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Lessons (CR 701.48): typed_spellcast drops "Lesson" (its subject vocab is
    # creature-only), so a Lessons commander (Uncle Iroh, Aang) had no avenue.
    ("lessons_matter", re.compile(r"\blesson\b", re.IGNORECASE), "you"),
    # Widen the existing suspend_matters avenue (sweep fires only on "suspend") to the
    # whole time-counter superstructure: CR 701.56 time travel, 702.63 Vanishing,
    # Impending, and the cross-pool enablers/payoffs (As Foretold, Jhoira, Dust of
    # Moments) that manipulate time counters without bearing Suspend themselves.
    (
        "suspend_matters",
        re.compile(
            r"time counter|time travel|\bvanishing\b|\bimpending\b", re.IGNORECASE
        ),
        "you",
    ),
    # Casualty (CR 702.153) sacrifices a creature as a cost — a casualty granter
    # (Anhelo, Silverquill) wants the sac-fodder avenue. Route the grant to sacrifice.
    ("sacrifice_matters", re.compile(r"\bcasualty\b", re.IGNORECASE), "you"),
    # Saddle / Mount (CR 702.171): attacks-while-saddled payoffs (Calamity, Gitrog
    # Ravenous Ride) the crew-keyed vehicles_matter avenue (1/33) doesn't surface.
    (
        "saddle_matters",
        re.compile(r"\bsaddled\b|whenever you saddle", re.IGNORECASE),
        "you",
    ),
    # Suspect (CR 701.60): a designation granting menace + can't-block. Key on the
    # oracle term — the keyword[] field is incomplete here (misses Cases / instants).
    (
        "suspect_matters",
        re.compile(r"\bsuspects?\b|\bsuspected\b", re.IGNORECASE),
        "you",
    ),
    # Power matters (CR 208): a commander whose engine keys on creature POWER — cost
    # reduction by total/greatest power (Ghalta), a power-N-or-greater spell threshold
    # (Goreclaw), or a Ferocious-style "if you control a creature with power N or
    # greater" payoff (Colossal Majesty, Crater's Claws). Every branch is anchored on a
    # "you control" / "you cast" / "under your control" context so that removal and
    # combat tricks that merely reference a target "creature with power N or greater"
    # (Bring to Trial, Bolt Bend) — which are NOT a power-matters theme — never fire.
    (
        "power_matters",
        re.compile(
            r"(?:total|greatest|combined) power of creatures you control"
            r"|creature spells? you cast with power \d+ or (?:greater|more)"
            r"|if you control [^.]*?with power \d+ or (?:greater|more)"
            r"|creature with power \d+ or (?:greater|more) enters"
            r" the battlefield under your control"
            r"|(?:total|greatest) power among (?:other )?creatures you control"
            # Formidable (CR 207.2c ability word: "creatures you control have total
            # power 8 or greater") is a big-creatures/power deck; match the italic word.
            r"|\bformidable\b",
            re.IGNORECASE,
        ),
        "you",
    ),
)

# One registration path: the curated hand-written detectors plus the exhaustively-
# mined sweep (one ability-axis each, grounded in real oracle text), unified into a
# single Detector record type. Same-key sweep widens carry the complete merged regex,
# so the extractor's (key, scope, subject) dedup unions them with the hand originals.
_FLOOR_DETECTORS: tuple[Detector, ...] = tuple(
    Detector(key, scope, pattern) for key, pattern, scope in _HAND_FLOOR
) + tuple(
    Detector(d["key"], d["scope"], re.compile(d["regex"], re.IGNORECASE))
    for d in SWEEP_DETECTORS
)

# (preset_name → (signal_key, scope)). KEYWORD-ARRAY presets only — these read
# Scryfall's authoritative `keywords` array, the low-false-positive path. mill is
# scoped "any" (it can target self or opponents; Phase-B nested-scope refines it).
_PRESET_KEYWORD_SIGNALS = {
    "mill": ("mill_matters", "any"),
    "goad": ("goad_matters", "opponents"),
    "proliferate": ("proliferate_matters", "you"),
    "magecraft": ("magecraft_matters", "you"),
    # Prowess is a spellslinger payoff (cast noncreature spells) → same avenue.
    "prowess": ("spellcast_matters", "you"),
    # Storm/Casualty/Replicate/etc. are spell-copy keywords.
    "spell-copy": ("spell_copy_matters", "you"),
}
# REGEX presets reused clause-scoped via the preset's own compiled patterns — these
# close documented pure-reuse gaps (blink/Brago, extra-combats/Aurelia) where the
# tested theme exists but the extractor never called it.
_PRESET_REGEX_SIGNALS = {
    "blink": ("blink_flicker", "you"),
    "extra-combats": ("extra_combats", "you"),
    "extra-turns": ("extra_turns", "you"),
}


def _detect_keyword_presets(card: dict) -> list[tuple[str, str]]:
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    out: list[tuple[str, str]] = []
    for preset_name, (key, scope) in _PRESET_KEYWORD_SIGNALS.items():
        preset_kws = {k.lower() for k in get_preset(preset_name).keywords}
        if card_kws & preset_kws:
            out.append((key, scope))
    return out


# Direct card-keyword signals: keywords (not theme_presets) that anchor a build via the
# rules — each maps to an existing signal axis, grounded in its CR 702.x definition.
# Dash returns the creature to hand each end step (702.109a) so Equipment persists
# (301.5c) while Auras (704.5m)/counters are lost; Mentor/Training/Evolve/… put +1/+1
# counters; Battle cry/Battalion/Melee reward attacking as a team; Exalted rewards
# attacking ALONE (suit up one); Extort drains each opponent (702.101a); Amass/Mobilize
# make tokens. The keyword is authoritative, so these are high confidence.
_DIRECT_KEYWORD_SIGNALS = {
    "dash": ("dash_matters", "you"),
    "mentor": ("counters_matter", "any"),
    "training": ("counters_matter", "any"),
    "modular": ("counters_matter", "any"),
    "bolster": ("counters_matter", "any"),
    "evolve": ("counters_matter", "any"),
    "outlast": ("counters_matter", "any"),
    "renown": ("counters_matter", "any"),
    "adapt": ("counters_matter", "any"),
    "battle cry": ("attack_matters", "you"),
    "battalion": ("attack_matters", "you"),
    "melee": ("attack_matters", "you"),
    "exalted": ("voltron_matters", "you"),
    "extort": ("lifeloss_matters", "opponents"),
    "amass": ("tokens_matter", "you"),
    "mobilize": ("tokens_matter", "you"),
    # Station (702.184) accrues charge counters → route to the proliferate avenue (which
    # already serves charge-counter cards); station commanders fire no +1/+1 counter
    # signal otherwise. Saddle (702.171) bodies want the dedicated saddle/Mount avenue.
    "station": ("proliferate_matters", "you"),
    "saddle": ("saddle_matters", "you"),
    # Banding (CR 702.21): a commander with banding wants other banding creatures to
    # form attacking/blocking bands (Ayesha Tanaka, General Jarkeld's pile).
    "banding": ("banding_matters", "you"),
    # Boast (CR 702.135) activates "only if this creature attacked this turn"; Exert
    # (702.107) is "as it attacks"; Myriad (702.116) makes attacking copies — all three
    # carry their attack condition in reminder text (stripped before detection), so a
    # commander with the keyword reads as attack-matters via the keyword, not oracle.
    "boast": ("attack_matters", "you"),
    "exert": ("attack_matters", "you"),
    "myriad": ("attack_matters", "you"),
    # Archetype-defining keyword abilities (CR §702): the mechanic is reminder text
    # (stripped), so a commander WITH the keyword reads as that archetype via keyword.
    "prowess": ("spellcast_matters", "you"),  # cast a noncreature spell → +1/+1
    "bushido": ("attack_matters", "you"),  # combat pump on block/blocked
    "annihilator": ("attack_matters", "you"),  # attacks → defending player sacrifices
    "flanking": ("attack_matters", "you"),  # combat (blockers get -1/-1)
    "frenzy": ("attack_matters", "you"),  # attacks unblocked → +N/+0
    "exploit": ("sacrifice_matters", "you"),  # enters → sacrifice a creature
    "devour": ("sacrifice_matters", "you"),  # enters → sacrifice creatures for counters
    "afflict": ("lifeloss_matters", "opponents"),  # becomes blocked → player loses life
    "spectacle": ("lifeloss_matters", "opponents"),  # alt cost if opponent lost life
    "dethrone": ("counters_matter", "any"),  # attacks the top life total → +1/+1
}


def _detect_direct_keywords(card: dict) -> list[tuple[str, str]]:
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    return [
        (key, scope)
        for kw, (key, scope) in _DIRECT_KEYWORD_SIGNALS.items()
        if kw in card_kws
    ]


# Keyword-tribes: cards that group creatures by a KEYWORD characteristic (CR 109.3)
# rather than a subtype — "Flying creatures you control get +1/+1", "creatures with
# deathtouch …". The ability-keyword vocab is the precision gate (so a subtype like
# "Goblin creatures you control" routes to type_matters, never here).
_ABILITY_KEYWORDS = frozenset(
    {
        "flying",
        "deathtouch",
        "vigilance",
        "trample",
        "lifelink",
        "menace",
        "reach",
        "haste",
        "hexproof",
        "indestructible",
        "defender",
        "flash",
        "ward",
        "shroud",
        "fear",
        "intimidate",
        "horsemanship",
        "prowess",
        "skulk",
        "wither",
        "infect",
        "persist",
        "undying",
        "flanking",
        "banding",
        "shadow",
        "exalted",
    }
)
_KW_TRIBE_RE = re.compile(
    r"\b(?:other )?([A-Za-z]+) creatures you control\b", re.IGNORECASE
)
_KEYWORD_TRIBE_PATTERNS = (
    # "Flying creatures you control …" / "other Flying creatures …"
    (_KW_TRIBE_RE, "you"),
    (re.compile(r"\bother ([A-Za-z]+) creatures\b", re.IGNORECASE), "you"),
    # "creatures you control with deathtouch …"
    (re.compile(r"\bcreatures you control with ([A-Za-z]+)\b", re.IGNORECASE), "you"),
    # "all creatures with deathtouch …" (symmetric)
    (
        re.compile(
            r"\bcreatures with ([A-Za-z]+)\b[^.]{0,20}?"
            r"(?:gets? [+\-]|have \"|gains?\b)",
            re.IGNORECASE,
        ),
        "any",
    ),
)


def _detect_keyword_tribe(clause: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for pat, scope in _KEYWORD_TRIBE_PATTERNS:
        for m in pat.finditer(clause):
            kw = m.group(1).lower()
            if kw in _ABILITY_KEYWORDS:
                out.append((signal_keys.KEYWORD_TRIBE, scope, kw.capitalize()))
    return out


# Voltron fallback: a vanilla beater still has a deterministic plan — commander damage
# (CR 903.10a: 21 combat damage from one commander = loss). Fires ONLY when nothing else
# gave a strong direction, for a voltron-viable creature (evasion keyword or power >=4).
_VOLTRON_KEYWORDS = frozenset(
    {
        "flying",
        "menace",
        "fear",
        "intimidate",
        "shadow",
        "horsemanship",
        "skulk",
        "trample",
        "double strike",
        # Resilience / aggression keywords that make a themeless legend a real
        # commander-damage threat worth suiting up (Konda: indestructible+vigilance).
        "indestructible",
        "hexproof",
        "vigilance",
        "first strike",
        "lifelink",
        "deathtouch",
        "haste",
    }
)


def _detect_regex_presets(clause: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for preset_name, (key, scope) in _PRESET_REGEX_SIGNALS.items():
        if any(p.search(clause) for p in get_preset(preset_name).patterns):
            out.append((key, scope))
    return out


# Cross-sentence flicker: the blink preset's single-clause "exile…return…battlefield"
# regex can't span the period in "Exile target creature. Return that card to the
# battlefield" (Roon). Detect the exile + pronoun-return pair on the full text; the
# pronoun ("it"/"that card"/"them") gates out reanimation, which returns a *graveyard*
# card ("return target creature card … to the battlefield"), not the exiled object.
_BLINK_EXILE_RE = re.compile(
    # Targeted flicker (exile target creature/permanent … return),
    r"\bexile (?:up to \w+ |any number of )?(?:another |one )?"
    r"target (?:creature|permanent|nonland permanent|artifact)"
    # OR untargeted MASS self-flicker of YOUR OWN permanents (Yorion: "exile any number
    # of other nonland permanents you own and control"). The "you control" anchor keeps
    # it off O-Ring-style removal of an opponent's permanent.
    r"|\bexile (?:up to \w+ |any number of |all )?(?:other )?"
    r"(?:nonland )?(?:creatures?|permanents?) you (?:own and )?control",
    re.IGNORECASE,
)
# Pronoun-return only: "return the exiled card to the battlefield" is the O-ring
# signature (Journey to Nowhere / Fiend Hunter) — removal with a leaves-the-
# battlefield-delayed return, NOT a flicker engine. Real flicker pronominally
# references the exiled object (it / that card / those cards).
_BLINK_RETURN_RE = re.compile(
    r"\breturn (?:it|them|that card|those cards|that permanent) to the battlefield",
    re.IGNORECASE,
)


def _detect_blink_fulltext(text: str) -> str | None:
    """Grounding clause if the card is a cross-sentence flicker engine, else None."""
    if not (_BLINK_EXILE_RE.search(text) and _BLINK_RETURN_RE.search(text)):
        return None
    for clause in _clauses(text):
        if _BLINK_RETURN_RE.search(clause):
            return clause.strip()
    return text[:160]


# Self-blink (full text): a card that exiles ITSELF and returns it (Norin), split
# across sentences so the per-clause self_blink sweep can't see both halves. Name-
# aware — the exiled object must be "this creature", "~", or the card's own name —
# which keeps it off reanimation and removal of OTHER creatures.
_SELF_BLINK_RETURN_RE = re.compile(
    r"\breturn (?:it|them|that card|that permanent) to the battlefield", re.IGNORECASE
)


def _detect_self_blink_fulltext(text: str, name: str) -> str | None:
    first = ""
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            first = w
            break
    alts = r"this creature|~" + (("|" + re.escape(first)) if first else "")
    exile_self = re.compile(rf"\bexile (?:{alts})\b", re.IGNORECASE)
    if not (exile_self.search(text) and _SELF_BLINK_RETURN_RE.search(text)):
        return None
    for clause in _clauses(text):
        if _SELF_BLINK_RETURN_RE.search(clause):
            return clause.strip()
    return text[:160]


# Beginning-of-combat single-target pump engine (Aurelia): the combat trigger and the
# "gets +" payoff sit in different sentences, so the per-clause combat_buff_engine
# sweep can't span them. Two-condition full-text check, anchored to your own creatures.
_COMBAT_BUFF_TRIGGER_RE = re.compile(
    r"at the beginning of combat on your turn", re.IGNORECASE
)
_COMBAT_BUFF_PUMP_RE = re.compile(
    r"(?:that creature|target creature you control|creatures? you control)[^.]*gets \+",
    re.IGNORECASE,
)

# Loot/rummage across a sentence boundary (Alpharael): "draw N cards. Then discard".
# Require the discard to be the ADJACENT clause (one period/comma + optional "then")
# so an unrelated later sentence ("draw two cards. You gain 3 life.") never matches.
_LOOT_FULLTEXT_RE = re.compile(
    r"\bdraw (?:a|an|two|three|four|five|x|\d+) cards?[.,]?\s*"
    r"(?:then )?(?:you )?(?:may )?discard",
    re.IGNORECASE,
)


# Self-ETB VALUE trigger (commander-only): a commander whose own "When ~ enters,
# <value>" ability is its engine wants blink/flicker to re-use it (CR 603.6). VALUE
# verbs only — NOT removal (exile/destroy target): O-Ring's "when ~ enters, exile target
# nonland permanent" is removal with a delayed return, not a flicker engine (the
# existing test_oring_removal_is_not_flicker guards this). Excludes mana-ritual/keyword
# ETBs too, so a bare beater doesn't open a Blink avenue.
_SELF_ETB_PAYOFF = (
    r"\b(?:draws?|create|creates|search|searches|look at|reveal|returns?"
    r"|gains? control|put[^.]*counter|mills?|investigate|scry|draft|copy"
    r"|deals? \d+ damage)\b"
)


def _detect_self_damage_prevention(text: str, name: str) -> bool:
    """True if the commander prevents/redirects ALL damage dealt to ITSELF (Cho-Manno,
    Anti-Venom) — the unkillable Pariah redirect target. Name-aware so a generic fog
    ('prevent all combat damage this turn') doesn't qualify."""
    first = ""
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            first = w
            break
    alts = r"this creature|~" + (("|" + re.escape(first)) if first else "")
    pat = re.compile(
        r"(?:prevent all damage that would be dealt to"
        r"|if damage would be dealt to) "
        rf"(?:{alts})\b",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _self_etb_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self enters-the-battlefield VALUE trigger."""
    first = ""
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            first = w
            break
    alts = r"this creature|this permanent|~" + (
        ("|" + re.escape(first)) if first else ""
    )
    pat = re.compile(
        rf"\bwhen (?:{alts}) enters\b[^.]*?{_SELF_ETB_PAYOFF}", re.IGNORECASE
    )
    for clause in _clauses(text):
        if pat.search(clause):
            return clause.strip()
    return None


# Death-trigger payoffs worth re-firing via a clone (Kamigawa dragons: Keiga steals,
# Kokusho drains, Yosei taps down). Mirrors _SELF_ETB_PAYOFF with the death-specific
# verbs (gain control, opponents lose life, skip a step).
_SELF_DIES_PAYOFF = (
    r"\b(?:gains? control|loses? \d+ life|lose life|each opponent|each player"
    r"|draws?|returns?|create|creates|destroys?|exiles?|deals? \d+ damage"
    r"|put[^.]*counter|skips?)\b"
)


def _self_dies_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self DIES VALUE trigger — a clone/token copy
    re-fires it when the copy dies (Keiga, Kokusho). Name-aware (short name like
    Scryfall prints) so 'When Keiga dies' matches."""
    first = ""
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            first = w
            break
    alts = r"this creature|this permanent|~" + (
        ("|" + re.escape(first)) if first else ""
    )
    pat = re.compile(
        rf"\bwhen (?:{alts}) dies\b[^.]*?{_SELF_DIES_PAYOFF}", re.IGNORECASE
    )
    for clause in _clauses(text):
        if pat.search(clause):
            return clause.strip()
    return None


# ── Narrow Tinybones structural scope rule ────────────────────────────────────
_COMBAT_DAMAGE_TO_PLAYER = re.compile(r"deals combat damage to a player", re.IGNORECASE)
_THAT_PLAYERS_ZONE = re.compile(
    r"that player's (?:graveyard|hand|library)", re.IGNORECASE
)


def _tinybones_scope(clause: str) -> str | None:
    """combat-damage-to-a-player + that-player's-zone → opponents. Kept narrow: a
    broad "its owner's hand → opponents" rule misfires on self-blink/self-bounce."""
    if _COMBAT_DAMAGE_TO_PLAYER.search(clause) and _THAT_PLAYERS_ZONE.search(clause):
        return "opponents"
    return None


# ── Phase B: nested-scope / self-reference resolvers behind a confidence flag ──
# A granted ability ("creatures you control have \"…\"") has an OUTER scope (who has
# it) and an INNER scope (who it affects); the flat parser can't resolve the inner
# confidently, so signals pulled from it are marked low confidence.
_GRANTED_ABILITY = re.compile(r'(?:have|gains?) "', re.IGNORECASE)
# Third-party possessive zones — the broad scope rule (deliberately excludes "its
# owner's" so it never flips the ~123 self-blink/self-bounce cards).
_BROAD_THIRD_PARTY = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)
_SELF_REF_MARKER = re.compile(r"\bthis (?:creature|permanent|land|card)\b|~")
_ARTICLES = frozenset({"the", "a", "an", "and", "of"})


def _self_reference(clause_lower: str, name: str) -> bool:
    """True if the clause refers to the card itself (own name or "this <type>")."""
    words = [
        w for w in re.split(r"\W+", name) if len(w) > 2 and w.lower() not in _ARTICLES
    ]
    if words and words[0].lower() in clause_lower:
        return True
    return _SELF_REF_MARKER.search(clause_lower) is not None


def _resolve_scope(
    clause: str, clause_lower: str, base_scope: str, name: str
) -> tuple[str, str]:
    """Resolve a clause's (scope, confidence) for unforced baseline detectors.

    The narrow Tinybones rule (high confidence) is applied separately and takes
    precedence. Otherwise: a granted ability is low-confidence (nested scope); a
    third-party possessive zone is an opponents guess (low confidence — the broad
    rule, on behind the flag); a self-reference resolves an otherwise-unscoped clause
    to "you" (high confidence)."""
    if _GRANTED_ABILITY.search(clause):
        return base_scope, "low"
    if _BROAD_THIRD_PARTY.search(clause_lower):
        return "opponents", "low"
    if base_scope == "any" and _self_reference(clause_lower, name):
        return "you", "high"
    return base_scope, "high"


# ── The extractor ─────────────────────────────────────────────────────────────


def extract_signals(
    card: dict,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
) -> list[Signal]:
    """Extract scoped, subject-bearing signals from a card (deterministic baseline).

    ``include_membership`` controls the two signals derived from what the card *is*
    (its characteristics) rather than what it *does*: own-subtype tribal and the
    voltron fallback. These are a commander-level suggestion; when aggregating over a
    whole deck, pass ``include_membership=False`` for the 99 so every creature's race
    and stat-line don't flood the deck's avenues (only the commander's do)."""
    # Strip parenthetical reminder text first: it restates a keyword and is rules-
    # redundant, so it must never generate a signal (e.g. an Earthbend reminder's
    # "is exiled, return it to the battlefield" is not a blink engine).
    text = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")
    name = card.get("name", "")
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(
        key: str, scope: str, subject: str, clause: str, confidence: str = "high"
    ) -> None:
        ident = (key, scope, subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(
            Signal(
                key=key,
                scope=scope,
                subject=subject,
                text=clause,
                source=name,
                confidence=confidence,
            )
        )

    for clause in _clauses(text):
        stripped = clause.strip()
        cl = clause.lower()
        clause_scope = _scope(cl)
        rescope = _tinybones_scope(clause)
        # Phase B: (scope, confidence) for unforced baseline detectors.
        resolved_scope, resolved_conf = _resolve_scope(clause, cl, clause_scope, name)
        # Tier 1 — baseline (subject-free)
        for key, matches, forced_scope in _DETECTORS:
            if not matches(cl):
                continue
            if rescope:  # narrow Tinybones rule — confident
                scope, conf = rescope, "high"
            elif forced_scope:
                scope, conf = forced_scope, "high"
            else:
                scope, conf = resolved_scope, resolved_conf
            add(key, scope, "", stripped, conf)
        # Tier 2 — parametric subject detectors (forced scope=you: "you control")
        for key, subject in _detect_type_matters(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_multi_tribe_anthem(clause, vocab):
            add(key, "you", subject, stripped)
        for key, scope, subject in _detect_keyword_tribe(clause):
            add(key, scope, subject, stripped)
        for key, subject in _detect_typed_spellcast(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_token_maker(clause, vocab):
            add(key, "you", subject, stripped)
        for key, scope, subject in _detect_typed_gy_recursion(clause, vocab):
            add(key, scope, subject, stripped)
        for key, subject in _detect_keyword_implied_tribe(clause):
            add(key, "you", subject, stripped)
        draw = _detect_card_draw(clause)
        if draw is not None:
            add(draw[0], draw[1], "", stripped)
        # Tier 3 — structural floor detectors + regex-preset reuse
        for det in _FLOOR_DETECTORS:
            if det.pattern.search(clause):
                add(det.key, det.scope, "", stripped)
        for key, scope in _detect_regex_presets(clause):
            add(key, scope, "", stripped)

    # Tier 3 — keyword-array presets (card-level, authoritative)
    for key, scope in _detect_keyword_presets(card):
        add(key, scope, "", text[:120])
    for key, scope in _detect_direct_keywords(card):
        add(key, scope, "", text[:120])

    # Own-subtype tribal (membership): a creature's own creature type is a deterministic
    # characteristic (CR 109.3) that tribal cards key off (CR 205.3 / 702.38a), so a
    # Dragon is a viable Dragons build with no tribal oracle text. LOW confidence
    # (membership ≠ a payoff — an oracle "other Dragons you control" wins the dedup at
    # high confidence) and gated to supported race tribes (not generic class types).
    # Commander-only at the deck level — see include_membership.
    type_line = card.get("type_line") or ""
    if include_membership and "creature" in type_line.lower() and "—" in type_line:
        for tok in type_line.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in TRIBAL_SUBTYPES:
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), type_line, "low")
    # A commander that IS an artifact (the Artifact card type is in its type line) is an
    # artifact deck — it wants affinity / cost reducers / artifact synergy, just as a
    # creature is a member of its own tribe. Membership-only, low confidence.
    if include_membership and "artifact" in type_line.lower():
        add("artifacts_matter", "you", "", type_line, "low")

    # Full-text detectors: trigger→payoff patterns that span a sentence boundary, so
    # the per-clause loop above can't see both halves (Roon, Norin, Aurelia, Alpharael).
    blink_clause = _detect_blink_fulltext(text)
    if blink_clause is not None:
        add("blink_flicker", "you", "", blink_clause)
    self_blink_clause = _detect_self_blink_fulltext(text, name)
    if self_blink_clause is not None:
        add("self_blink", "you", "", self_blink_clause)
    if _COMBAT_BUFF_TRIGGER_RE.search(text) and _COMBAT_BUFF_PUMP_RE.search(text):
        add("combat_buff_engine", "you", "", text[:160])
    if _LOOT_FULLTEXT_RE.search(text):
        add("discard_matters", "you", "", text[:160])
    if _detect_self_damage_prevention(text, name):
        add("damage_redirect", "you", "", text[:160])
        # An unkillable body (prevents all damage to itself: Cho-Manno) is the ideal
        # Equipment/Aura carrier — it's a voltron commander too (membership-only, since
        # the commander-damage plan is a suggestion for the commander itself).
        if include_membership:
            add("voltron_matters", "you", "", text[:160], "low")
    # Self-power-scaling commander (Mona Lisa: "X is Mona Lisa's power") wants to pump
    # its OWN power with +1/+1 counters — open the self-counter-growth lane. Name-aware
    # (name + "this creature", not "its") so a fling's "target creature's power" is out.
    _first = ""
    for _w in re.split(r"\W+", name):
        if len(_w) > 2 and _w.lower() not in _ARTICLES:
            _first = _w
            break
    _self = r"this creature|this permanent"
    if _first:
        _self += "|" + re.escape(_first)
    if re.search(
        rf"(?:equal to|x is|x equals?|where x is) [^.]*?(?:{_self})[^.]*?\bpower\b",
        text,
        re.IGNORECASE,
    ):
        add("self_counter_grow", "you", "", text[:160], "low")

    # Self-ETB value commander → open the (existing, precise) blink/flicker avenue so
    # Ephemerate/Cloudshift/Conjurer's Closet get surfaced to re-use the commander's
    # own ETB (CR 603.6). Commander-only — a flicker package is a suggestion.
    if include_membership:
        etb_clause = _self_etb_value(text, name)
        if etb_clause is not None:
            add("blink_flicker", "you", "", etb_clause, "low")
        # A HIGH-CMC commander with a strong ETB or DEATH trigger is worth COPYING — a
        # clone/token copy re-fires the expensive ETB on a cheap body (Gyruda) or the
        # death trigger when the copy dies (Keiga, Kokusho — sac-loop staple). Gate on
        # mana value >= 5 (copying a cheap trigger isn't worth a clone). Reuse the
        # self-ETB/dies clauses so the SHORT name Scryfall prints matches.
        if (card.get("cmc") or 0) >= 5:
            clone_clause = etb_clause or _self_dies_value(text, name)
            if clone_clause is not None:
                add("clone_matters", "you", "", clone_clause, "low")

    # Voltron fallback (membership; commander damage, CR 903.10a): only when nothing
    # else gave a strong direction and the creature is a real commander-damage threat
    # (an evasion/resilience keyword, or power >=2 — Isamaru is a 2/2). Low confidence —
    # a generic plan, not a detected synergy. Commander-only at the deck level (see
    # include_membership); a 0/1 themeless wall is excluded by the power floor.
    type_line = card.get("type_line") or ""
    has_strong = any(s.confidence == "high" and s.key not in _GENERIC_KEYS for s in out)
    try:
        power = int(str(card.get("power", "0")))
    except ValueError:
        power = 0
    kws = {k.lower() for k in (card.get("keywords") or [])}
    # Hexproof / indestructible / shroud creatures are PRIME voltron targets — un-
    # removable beaters you safely suit up (Sigarda, Uril, Geist of Saint Traft) — so
    # open voltron even when another signal already fired (these decks are voltron
    # regardless of the commander's incidental text).
    if (
        include_membership
        and "creature" in type_line.lower()
        and power >= 2
        and kws & {"hexproof", "indestructible", "shroud"}
    ):
        add("voltron_matters", "you", "", "hexproof/indestructible beater", "low")
    if (
        include_membership
        and not has_strong
        and "creature" in type_line.lower()
        and (kws & _VOLTRON_KEYWORDS or power >= 2)
    ):
        add("voltron_matters", "you", "", "commander damage (CR 903.10a)", "low")

    return out


def aggregate_signals(records: list[dict | None]) -> list[Signal]:
    """Union of signals across many cards, deduped by (key, scope, subject)."""
    seen: dict[tuple[str, str, str], Signal] = {}
    for record in records:
        if not record:
            continue
        for sig in extract_signals(record):
            ident = (sig.key, sig.scope, sig.subject)
            seen.setdefault(ident, sig)
    return list(seen.values())


def rank_deck_signals(
    records: Sequence[dict | None], commander_names: set[str]
) -> list[Signal]:
    """Deck signals deduped by (key, scope, subject) and ranked by relevance.

    Membership signals (own-subtype tribal, voltron fallback) are taken from the
    COMMANDER only — otherwise every creature's race/stat-line floods the deck. A
    signal's *support* (how many cards feed it) drives the ranking. Kept ForgeState-free
    so both the deck-forge engine (``engine.ranked_deck_signals``) and the deterministic
    tuner share one ranking (ADR-0023)."""
    support: dict[tuple[str, str, str], int] = {}
    from_commander: set[tuple[str, str, str]] = set()
    first: dict[tuple[str, str, str], Signal] = {}
    for card in records:
        if not card:
            continue
        is_cmd = card.get("name") in commander_names
        for sig in extract_signals(card, include_membership=is_cmd):
            ident = (sig.key, sig.scope, sig.subject)
            support[ident] = support.get(ident, 0) + 1
            if is_cmd:
                from_commander.add(ident)
            first.setdefault(ident, sig)
    return sorted(
        first.values(),
        key=lambda s: (
            (s.key, s.scope, s.subject) in from_commander,
            support[(s.key, s.scope, s.subject)],
            s.confidence == "high",
        ),
        reverse=True,
    )


# ── Coverage gate — the agent-augmentation (M3) hook ──────────────────────────
# Generic = {creatures_matter}: it fires on "creatures you control" (nearly every
# creature commander) and discriminates no archetype. The other keys each pin a
# real sub-archetype, so they are NOT generic.
_GENERIC_KEYS = frozenset({"creatures_matter"})

_SELF_MARKER = re.compile(r"\byou\b|\byour\b", re.IGNORECASE)
_THIRD_PARTY_POSSESSIVE = re.compile(
    r"that player's|each opponent's|target opponent's|their (?:hand|graveyard|library)",
    re.IGNORECASE,
)


def _scope_uncertain(text: str) -> bool:
    """True if any clause mixes a self-marker AND a third-party possessive that the
    narrow Tinybones rule did NOT already resolve — the agent's territory."""
    for clause in _clauses(text):
        if (
            _SELF_MARKER.search(clause)
            and _THIRD_PARTY_POSSESSIVE.search(clause)
            and _tinybones_scope(clause) is None
        ):
            return True
    return False


def coverage_gate(card: dict, signals: list[Signal]) -> tuple[bool, str]:
    """Report a blind spot: (needs_agent, reason). reason ∈ {zero_signal,
    only_generic, low_confidence, scope_uncertain, ""}. Surfaces gaps for agent
    scoping instead of dropping them silently."""
    if not signals:
        return (True, "zero_signal")
    keys = {s.key for s in signals}
    if keys <= _GENERIC_KEYS and not any(s.subject for s in signals):
        return (True, "only_generic")
    # Every signal is a scope guess (Phase B) → the agent should confirm the scoping.
    if all(s.confidence == "low" for s in signals):
        return (True, "low_confidence")
    if _scope_uncertain(get_oracle_text(card) or ""):
        return (True, "scope_uncertain")
    return (False, "")


# Keys emitted by hand-written full-text / function detectors via a direct add(), i.e.
# NOT carried by a producer table — co-listed so the key-agreement gate guards them too.
# (Subject-bearing keys live in signal_keys.SUBJECT_KEYS and are excluded below; they
# resolve dynamically via signal_specs._subject_spec, not a static spec.)
_LITERAL_ADD_KEYS = frozenset(
    {"self_blink", "combat_buff_engine", "discard_matters", "card_draw_engine"}
)


def producible_static_keys() -> set[str]:
    """Every scope-bearing, subject-LESS signal key a detector can emit into
    ``Signal.key`` — DERIVED from the producer tables (so it can never lag the
    detectors) and fed to the key-agreement gate in signal_specs.py. Subject-bearing
    keys are excluded: they have no static spec (signal_specs._subject_spec builds one
    from the captured subject) and so must not be probed with an empty subject."""
    keys: set[str] = set()
    keys.update(key for key, _matcher, _scope in _DETECTORS)
    keys.update(key for key, _pattern, _scope in _HAND_FLOOR)
    keys.update(d["key"] for d in SWEEP_DETECTORS)
    for table in (
        _PRESET_KEYWORD_SIGNALS,
        _PRESET_REGEX_SIGNALS,
        _DIRECT_KEYWORD_SIGNALS,
    ):
        keys.update(key for key, _scope in table.values())
    keys.update(_LITERAL_ADD_KEYS)
    return keys - signal_keys.SUBJECT_KEYS
