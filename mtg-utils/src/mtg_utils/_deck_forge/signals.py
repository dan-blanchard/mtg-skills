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
    CLASS_TRIBES,
    CREATURE_SUBTYPES,
    IRREGULAR_SINGULAR,
    NON_SUBJECT_WORDS,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS
from mtg_utils.card_classify import card_pt_int, get_oracle_text, is_creature
from mtg_utils.card_ir import Card, Filter
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
def _re(pattern: str) -> Callable[[str], bool]:
    rx = re.compile(pattern)
    return lambda c: rx.search(c) is not None


# Evergreen keywords a keyword-soup commander (Odric Lunarch Marshal, Akroma Vision)
# shares across the team — counting >=5 of them in a team-grant context isolates the
# soup-sharers from single-keyword anthems.
_EVERGREEN_KW_WORDS = (
    "flying",
    "first strike",
    "double strike",
    "deathtouch",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
    "ward",
    "protection",
)
_EVERGREEN_KW_RE = tuple(
    re.compile(r"\b" + kw + r"\b", re.IGNORECASE) for kw in _EVERGREEN_KW_WORDS
)


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
# Delayed ETB-payoff (Ephara): "at the beginning of upkeep, if you HAD a creature enter
# the battlefield under your control last turn, …" — rewards creatures entering, but the
# trigger word is the upkeep, not "when a creature enters", so the trigger-word gate
# below misses it. It's an ETB-payoff commander all the same.
_ETB_HAD_RE = re.compile(
    r"you had (?:a|an|another|one or more|\d+)[^.]*creatures? "
    r"enter the battlefield under your control",
    re.IGNORECASE,
)


# color_hoser: a commander whose payoff is keyed on a specific COLOR it punishes,
# restricts, or bounces (Llawan "opponents can't cast blue creature spells" / "return
# all blue creatures", Dromar "choose a color, then return all of it", Jaya "destroy
# target blue permanent", Ascendant Evincar "nonblack creatures get -1/-1"). Such a
# commander wants the color-changing "Painter" toolbox to force its color payoff onto
# every permanent (color is a layer-5 characteristic the hoser then checks: CR 105.2 /
# 613.1e). Deliberately omits bare "protection from <color>" (ubiquitous keyword) and
# the plain "<color> creatures get +" mono-color anthem (Bad Moon), neither of which is
# a hoser. Scopes to removal/restriction/bounce on a NAMED color.
_COLOR = r"(?:white|blue|black|red|green)"
_COLOR_HOSER_RE = re.compile(
    rf"(?:destroy|exile|return|counter) (?:target |all )?(?:\w+ )?{_COLOR} "
    rf"(?:creature|permanent|spell)"
    rf"|can'?t (?:cast|be cast|block|attack)[^.]{{0,30}}{_COLOR}"
    rf"|non{_COLOR} creatures? [^.]*get -"
    rf"|{_COLOR} creatures? (?:your |that your )?opponents control"
    rf"|choose a color, then (?:return|destroy|exile)",
    re.IGNORECASE,
)


# type_change: the TYPE analog of color_hoser/color_change. A commander whose payoff is
# keyed on a creature SUBTYPE it punishes — "protection from Salamanders" (Gor Muldrak),
# "protection from <subtype>" — wants the creature-TYPE-CHANGING toolbox (Unnatural
# Selection, Standardize) to force every opponent's creature into that type, so the
# hoser blanks them (creature type is a continuously-checked characteristic, CR 205.3 /
# 702.16 protection). The captured word is validated against the subtype vocab, so
# "protection from white" (a color) and "protection from everything" never match.
_TYPE_HOSER_RE = re.compile(r"protection from (\w+)")


def _type_hoser_clause(cl: str) -> bool:
    return any(
        w in CREATURE_SUBTYPES or w.rstrip("s") in CREATURE_SUBTYPES
        for w in _TYPE_HOSER_RE.findall(cl)
    )


# Instant/sorcery BUILD-AROUND with no "whenever you cast" trigger: a commander that
# grants flashback to / recasts from the graveyard / reduces the cost of instants and
# sorceries (Lier "each instant and sorcery card in your graveyard has flashback", Kess,
# Dralnu) is a spellslinger deck and wants a high instant/sorcery density. The cast-
# trigger spellcast_matters detector keys on "whenever you cast", so it misses these.
# Requires a build-around verb after the type pair, so a bare counterspell ("counter
# target instant or sorcery spell") never matches.
_IS_BUILDAROUND_RE = re.compile(
    r"instants? (?:and|or) sorcer(?:y|ies)[^.]{0,50}"
    r"(?:flashback|from (?:your |a )?graveyard|cost (?:\{|\d|less)|you may cast)",
    re.IGNORECASE,
)

# xspell_matters: a commander that REWARDS or ENABLES casting spells whose printed mana
# cost contains {X} (Zaxara makes a Hydra per X-spell, Rosheen ramps for {X} costs, Nev
# grows on your first {X} spell). "{X} in its/their mana cost" / "costs that contain
# {X}" / "spells you cast with {X}" is the tight hook; CR 107.3 (X is a placeholder) and
# 702.156a ("creature cards with {X} in their mana cost") confirm "{X} in the mana cost"
# is a fixed printed characteristic (CR 202.1). The clause-scoped VETO drops an X-spell
# HOSER (Gaddock Teeg "spells with {X} in their mana costs can't be cast") — it bans
# X-spells, it doesn't want them. Matched per-clause so the veto is local to the clause.
_XSPELL_HOOK_RE = re.compile(
    r"\{x\} in (?:its|their) (?:mana )?cost"
    r"|costs? that contains? \{x\}"
    r"|spells? you cast with \{x\}",
    re.IGNORECASE,
)
_XSPELL_VETO_RE = re.compile(r"can'?t be cast|can'?t cast", re.IGNORECASE)


_DETECTORS: tuple[tuple[str, Callable[..., bool], str | None], ...] = (
    ("color_hoser", lambda c: _COLOR_HOSER_RE.search(c) is not None, "you"),
    ("type_change", _type_hoser_clause, "you"),
    ("spellcast_matters", lambda c: _IS_BUILDAROUND_RE.search(c) is not None, "you"),
    (
        "xspell_matters",
        lambda c: bool(_XSPELL_HOOK_RE.search(c)) and not _XSPELL_VETO_RE.search(c),
        "you",
    ),
    (
        "creature_etb",
        lambda c: (
            (
                (
                    _ETB_ANY_RE.search(c) is not None
                    and ("whenever" in c or "when " in c)
                )
                or _ETB_DOUBLER_RE.search(c) is not None
                or _ETB_HAD_RE.search(c) is not None
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
    # Plural "creatures you control" OR the singular go-wide count "for each creature
    # you control" (Shanna: P/T scales with your creature count).
    (
        "creatures_matter",
        lambda c: "creatures you control" in c or "for each creature you control" in c,
        "you",
    ),
    # Creature RECURSION engine (Hua Tuo, Adun, Othelm): a repeatable "return/put/choose
    # a creature card (in|from) your graveyard" ability. Distinct from broad
    # graveyard_matters — it loops a single creature, so it wants SELF-SACRIFICING
    # creatures (the sac is the value AND refuels the graveyard — Spore Frog) plus
    # ETB-value bodies. Served accordingly.
    (
        "creature_recursion",
        _re(
            r"(?:return|put|choose) (?:target |a |another )?creature card"
            r"[^.]*?\b(?:in|from) your graveyard"
        ),
        "you",
    ),
    # Type-matters: "land creature(s)" as a phrase. \b before "land" so "nonland
    # creature" / "Plant creature" / "island creature" do NOT register — only a
    # genuine land-creature reference (the Jyoti / Sylvan Advocate theme). The
    # "it's/becomes a forest land" tail catches the maker side (Yedora turns dead
    # creatures into Forest lands that animate-your-lands payoffs then re-animate).
    (
        "land_creatures_matter",
        _re(
            r"\bland creatures?\b|lands? you control (?:are|become)\b"
            r"|all lands[^.]*become[^.]*creature"
            r"|target land[^.]*becomes? a[^.]*creature"
            r"|(?:it's|becomes?) a forest land"
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
            # "you gained" plus the contraction ("you've") and the partner "your team
            # gained life this turn" form (Regna / Krav).
            r"|(?:you|your team)(?:'ve| have)? gained[^.]*life|life you gained"
            # Variable lifegain: "gain X life" (Atalya), "gain life equal to …" (Ayli),
            # "you gain that much life" (Varina, Black Panther) — count-scaled self
            # lifegain. Self-scoped form only; "<opponent> gains that much life" stays
            # out (lifelink reminder text on granted auras already opens via lifelink).
            r"|gains? x life|gains? life equal to|you gain that much life"
            # Lifegain amplifiers: "if you would gain life, you gain … instead"
            # (Bilbo, Boon Reflection, Rhox Faithmender, Alhammarret's Archive).
            r"|if you would gain life"
        ),
        "you",
    ),
    # Whose graveyard a card cares about decides the scope. A self-graveyard engine
    # that merely MENTIONS opponents elsewhere (Araumi's encore tokens "attack that
    # opponent"; Tasigur, Toshiro, Syr Konrad, Glissa) was mis-scoped opponents by the
    # generic "opponent"-anywhere rule, so self-mill enablers (scoped you) never
    # served. Force "you" on any "your graveyard" reference; let the residual graveyard
    # mentions ("a graveyard", an opponent's) auto-scope, but exclude the self cards so
    # they don't ALSO raise a spurious opponents'-graveyard avenue.
    ("graveyard_matters", _re(r"your graveyard"), "you"),
    (
        "graveyard_matters",
        lambda c: "graveyard" in c and "your graveyard" not in c,
        None,
    ),
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
    # attack a player other than the goader (you) — i.e. one of your OTHER opponents —
    # which fires the reward (CR 701.15b). So such a commander wants goad effects.
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
            # Instant/sorcery COST reducers (Baral, Magnus, Vadrik) and cast-from-zone
            # / next-cast-copy payoffs (Johann, Zaffai, Najal) — core spellslinger glue
            # with no "whenever you cast" trigger.
            or _re(r"instant and sorcery spells? you cast cost")(c)
            or _re(r"cast an instant or sorcery spell from")(c)
            or _re(r"when you (?:next )?cast an instant or sorcery spell this turn")(c)
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
                # Board-wide placement: "put a +1/+1 counter on each <group>" — on
                # each attacking / other / legendary / artifact creature, on each
                # <tribe> you control, on each of up to N target creatures. All are
                # counter ENGINES (Drana, Edgar Markov, Steel Overseer, Iron Spider).
                or "+1/+1 counter on each" in c
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
                # Placement on a CHOSEN creature — "counter on target/up to one target/
                # that creature" — is a counters engine (Leinore's Coven, Shelinda),
                # distinct from bare self-growth "counter on it".
                or "+1/+1 counter on target" in c
                or "+1/+1 counter on up to one target" in c
                or "+1/+1 counter on that creature" in c
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
            # The natural "lost … life this turn" order (lost-before-life) the above
            # life-before-lost pattern misses — drain payoffs that reward an opponent
            # having lost life (Sygg: "an opponent lost 3 or more life this turn";
            # Belbe: "opponents who lost life this turn").
            r"|opponents? (?:who|that) lost life this turn"
            r"|opponent lost \d+ or more life this turn"
        ),
        None,
    ),
    # Pay-life / self life-loss as a resource (forced you — it's your life). Numeric
    # AND the variable self-anchored forms: "you lose X life" draw engines, "you lose
    # that much life", "you lose life equal to", "you may pay X life". Anchored on
    # "you" so a "Ward, pay life equal to" cost (the opponent pays, Raubahn) stays out.
    (
        "lifeloss_matters",
        _re(
            r"pay \d+ life|you lose \d+ life|you lose (?:x|that much) life"
            r"|you lose life equal to|you may pay (?:\d+|x) life"
        ),
        "you",
    ),
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


def clauses(text: str) -> list[str]:
    """Public alias for the sentence-scoped clause splitter the extractor uses.

    Ranking clusters served lanes by which clause matched them (one physical
    property = one synergy credit), so it must split on the SAME boundaries the
    detectors do — a shared splitter keeps spans aligned with detector scope.
    """
    return _clauses(text)


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
        r"(?:enters|entering|attacks?|dies|deals|blocks?|becomes?|leaves)\b",
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
    # "the number of tapped Assassins you control" — a state adjective sits between the
    # count anchor and the tribe, so the bare anchor above captures the adjective (which
    # the vocab gate drops) and the tribe is lost. The fixed adjective set + subtype
    # vocab gate keep it precise (a "tapped creature" count still drops). Lydia Frye.
    re.compile(
        r"\b(?:number of|for each) "
        r"(?:tapped|untapped|attacking|blocking|nontoken|enchanted) "
        r"([A-Za-z]+?)s? you control\b",
        re.IGNORECASE,
    ),
    # Keyword-grant lord: "have"/"has" (static) and "gain"/"gains" (granted) — "Spirits
    # you control gain flying", "Knights you control gain double strike". The subtype
    # vocab gate keeps the generic "Creatures you control gain …" out.
    re.compile(r"\b([A-Za-z]+?)s? you control (?:ha(?:ve|s)|gains?)\b", re.IGNORECASE),
    # Global lords with no "you control" / "other": "Bird creatures get +1/+1"
    # (Soraya) or the singular "Each Fungus creature gets +1/+1" (Thelon). The
    # subtype-vocab gate drops "all"/"other"/"creature" so only a real tribe sticks.
    re.compile(r"\b([A-Za-z]+?) creatures? gets? [+\-](?:\d|x)", re.IGNORECASE),
    # The canonical tribal lord "Goblin creatures you control get +1/+1" — "you control"
    # sits between the tribe and the verb, so the adjacency patterns above and the "Xs
    # you control get" pattern (which captures "creatures") both miss it. 351 cards.
    re.compile(
        r"\b([A-Za-z]+?) creatures? you control (?:gets?|have|has|gains?)\b",
        re.IGNORECASE,
    ),
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
    # Evasion-grant lord: "Boars you control can't be blocked …" (Rocksteady — a
    # Rhino Mutant buffing Boars, so type-line membership can't supply the tribe).
    # The vocab gate drops the generic "Creatures you control can't be blocked".
    re.compile(r"\b([A-Za-z]+?)s? you control can't be blocked\b", re.IGNORECASE),
    # Tribal SUPPORT that never says "Xs you control": a commander that BUFFS a TARGET
    # of a type (Owen Grady: "put a … counter on target Dinosaur"; Otepec: "target
    # Dinosaur gains haste"), TUTORS the tribe ("search … for a Dragon card" — Sivitri),
    # WRATHS around it ("destroy all non-Dragon creatures" — Sivitri, Liliana Death's
    # Majesty), or COST-REDUCES its spells ("Dragon spells you cast cost {1} less" —
    # Nogi) is that tribe's commander. The subtype-vocab gate (_resolve_subject) keeps
    # each precise; "destroy ALL non-X" excludes the non-X drawback/reward forms (Yukora
    # "sacrifice all non-Ogre", Anim Pakal "attack with non-Gnome").
    re.compile(r"counter on target ([A-Za-z]+?)\b", re.IGNORECASE),
    re.compile(r"\btarget ([A-Za-z]+?) (?:gains?|gets [+\-])", re.IGNORECASE),
    re.compile(
        r"\bsearch (?:your library )?for (?:a|an) ([A-Za-z]+?)"
        r"(?: (?:permanent|creature|nonland|artifact|enchantment))? card",
        re.IGNORECASE,
    ),
    re.compile(r"\bdestroy all non-([A-Za-z]+?) creatures?\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?) spells you cast cost\b", re.IGNORECASE),
    # Tribal-spell payoff phrased as "<Tribe> creature spell": a commander that casts /
    # cost-reduces / copies "Dragon creature spells" (Rivaz), "Zombie creature spells"
    # (Gisa and Geralf), or "Beast creature spells" (Tawnos) is that tribe. The bare
    # "X spells you cast cost" pattern captures "creature", not the tribe.
    re.compile(r"\b([A-Za-z]+?) creature spells?\b", re.IGNORECASE),
    # Tribal evasion-grant on a single target with no "you control" anchor: "target
    # Ninja can't be blocked" (Splinter, a Ninja-tribal payoff). The vocab gate drops
    # the bare "target creature can't be blocked".
    re.compile(r"\btarget ([A-Za-z]+?) can't be blocked", re.IGNORECASE),
    # "(a|an) <Tribe> [permanent/creature] card/spell": finditer captures EVERY tribe in
    # a multi-tribe reveal/cast/return list the single-capture patterns miss. Kaalia
    # ("an Angel card, a Demon card, and/or a Dragon card"), Disa ("a Lhurgoyf permanent
    # card"), Eivor ("a Saga card"). Vocab-gated: "a creature card" / "a land" drop out.
    re.compile(
        r"\b(?:a|an) ([A-Za-z]+?)(?: (?:permanent|creature|nonland))? (?:card|spell)\b",
        re.IGNORECASE,
    ),
)
# Two-tribe trigger: "a Goblin or Orc you control deals …" (Gorbag — an Orc, so
# membership supplies Orc but never Goblin). Emit BOTH captured subtypes; the
# single-subject "a X you control <verb>" pattern captures only the first side.
_TWO_TRIBE_TRIGGER_RE = re.compile(
    r"\b(?:a|an) ([A-Za-z]+?) or ([A-Za-z]+?) you control "
    r"(?:enters|attacks?|dies|deals|blocks?)\b",
    re.IGNORECASE,
)
# Type GRANT: a commander that CONVERTS its creatures to a tribe — "it's a Zombie in
# addition to its other creature types" (Lim-Dûl reanimates as Zombies), Chainer
# (Nightmare), Xu-Ifit (Skeleton), Shilgengar (Vampire). Its board becomes that tribe,
# so it wants that tribe's lords. The vocab gate (in _resolve_subject) keeps it to real
# subtypes.
_TYPE_GRANT_RE = re.compile(
    r"(?:is|are|becomes?|it's) (?:a |an )?([A-Za-z]+?)s? "
    r"in addition to (?:its|their) other(?: creature)? types",
    re.IGNORECASE,
)
# typed_spellcast: subject-bearing extension of spellcast_matters — catches tribal
# spell payoffs ("Sliver spells you cast") the literal spellcast_matters misses.
_TYPED_SPELLCAST_PATTERN = re.compile(
    r"\b([A-Za-z]+?)s? spells? you cast\b", re.IGNORECASE
)
# Multi-tribe comma list before card/spell: "a Kraken, Leviathan, Octopus, or Serpent
# spell" (Kiora), "a Construct, Robot, or Vehicle card" (Dr. Eggman). The single-subject
# "(a) X card/spell" pattern stops at the first comma; this captures the whole list so
# every member is emitted. Vocab gate drops "or" and non-subtypes.
_TRIBE_LIST_RE = re.compile(
    r"\b(?:a|an) ((?:[A-Za-z]+, )+(?:or )?[A-Za-z]+)(?: creature)? (?:card|spell)s?\b",
    re.IGNORECASE,
)
# Two-tribe creature spell: "a Beast or Bird creature spell" (Tawnos). Scoped to
# "creature spell" (not bare card/spell) so an opponent-cast hoser (Ishi-Ishi punishing
# "a Spirit or Arcane spell") doesn't wrongly open the punished tribe.
_TWO_TRIBE_SPELL_RE = re.compile(
    r"\b(?:a|an) ([A-Za-z]+) or ([A-Za-z]+) creature spells?\b", re.IGNORECASE
)
# Two-tribe tutor: "search ... for a Lesson or Noble card" (Lo and Li, a Noble-tribal
# tutor). Scoped to "search ... for" (your tutor), so opponent-cast hosers don't match.
_TWO_TRIBE_TUTOR_RE = re.compile(
    r"\bsearch (?:your library )?for (?:a|an) ([A-Za-z]+) or ([A-Za-z]+) card",
    re.IGNORECASE,
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
    # Two-tribe head ("a Goblin or Orc you control deals …"): emit for BOTH sides.
    for m in _TWO_TRIBE_TRIGGER_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Multi-tribe comma list ("a Kraken, Leviathan, Octopus, or Serpent spell"): emit
    # for EVERY listed type.
    for m in _TRIBE_LIST_RE.finditer(clause):
        for raw in re.findall(r"[A-Za-z]+", m.group(1)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Two-tribe creature spell ("a Beast or Bird creature spell"): emit for BOTH.
    for m in _TWO_TRIBE_SPELL_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Two-tribe tutor ("search for a Lesson or Noble card"): emit for BOTH.
    for m in _TWO_TRIBE_TUTOR_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Type GRANT ("it's a Zombie in addition to its other creature types"): the
    # commander converts its board to that tribe → wants that tribe's lords.
    for m in _TYPE_GRANT_RE.finditer(clause):
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
# Menagerie-anthem LIST form: "Other Spiders, Boars, …, and Wolves you control get
# +1/+1" (Spider-Ham) names many subtypes in one comma run before "you control
# get/have/gain". The head form above has no "that's a X" and the single-tribe pattern
# grabs only the last type. Require a comma (≥2 types) so single-tribe anthems don't
# double-fire here, and let the vocab gate drop connectives ("and"/"or") and the
# generic "creatures" head ("Other creatures you control get" → no subtype).
_MULTI_TRIBE_LIST_RE = re.compile(
    r"\bother ([A-Za-z]+(?:, (?:and |or )?[A-Za-z]+)+) you control "
    r"(?:gets?|have|has|gains?)\b",
    re.IGNORECASE,
)


def _detect_multi_tribe_anthem(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pattern in (_MULTI_TRIBE_HEAD_RE, _MULTI_TRIBE_LIST_RE):
        for m in pattern.finditer(clause):
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
    # Goad archetype (CR 701.15): two commander shapes that want goad cards (Disrupt
    # Decorum) but carry no goad KEYWORD, so the keyword preset misses them. (1) FORCING
    # OTHER creatures to attack — "target/another target/each other creature ... attacks
    # ... if able" (Basandra, Thantis) is the goad mechanic itself. (2) Rewarding ANY
    # player's attack — "whenever a(nother) player attacks" (Aurelia, Breena, Jolene) —
    # goad sends opponents' creatures into the payoff. EXCLUDES self forced-attack
    # ("Zurgo attacks each combat if able" — an aggressive beater, not goad) by
    # anchoring on target/other/each-other creatures, never "this creature" / the name.
    (
        "goad_matters",
        re.compile(
            r"(?:target creature|another target creature|each other creature)"
            r"[^.]*attacks?[^.]*\bif able\b"
            r"|whenever (?:a|another) player attacks"
            # (3) DEFENDING-player payoff (Kazuul): "whenever a creature an opponent
            # controls attacks ... you're the defending player, <reward>" rewards
            # opponents swinging at YOU, so it wants force-attack / goad to feed it.
            r"|creature an opponent controls attacks[^.]*"
            r"(?:you're|you are) the defending player",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # A commander that rewards a creature whose "power [is] greater than its base power"
    # (Kutzil, Baird) is a pump / +1/+1-counters payoff — the only way a creature's
    # power exceeds its BASE power is a counter or a pump (CR 613.4c puts BOTH in
    # layer 7c). Open counters_matter (so +1/+1 sources like Forgotten Ancient /
    # Hardened Scales surface) AND modified_matters (so pumps / Auras / Equipment that
    # also satisfy "power > base" surface). Niche: only two commander-legal cards carry
    # the phrase, so precision is near-total.
    (
        "counters_matter",
        re.compile(r"power greater than its base power", re.IGNORECASE),
        "you",
    ),
    (
        "modified_matters",
        re.compile(r"power greater than its base power", re.IGNORECASE),
        "you",
    ),
    # Small-creatures-matter (Subira, Delney, Arabella, Ezuri): a commander that rewards
    # or buffs "creature(s) YOU CONTROL with power N or less" runs a go-wide weenie deck
    # and wants the small-creature payoffs (Raid Bombardment, Reconnaissance Mission).
    # Anchored on "you control with power N or less" so removal ("destroy a target
    # with power N or less") and evasion-bypass ("can't be blocked by creatures with
    # power N or greater") — never "you control" — stay out. Oracle-only serve (no
    # power_max: that would credit every power<=2 vanilla as on-theme fodder).
    (
        "low_power_matters",
        re.compile(
            r"creatures? you control with power \d+ or (?:less|fewer)", re.IGNORECASE
        ),
        "you",
    ),
    # Creature-count-scaling = a GO-WIDE commander: its own power scales with "for each
    # (other) creature you control" / "equal to the number of creatures you control"
    # (Leonardo, Adeline, Suki). It wants to flood the board, so open tokens_matter —
    # whose creature-scoped go-wide package (mass creature-token makers + protection)
    # is exactly what a count-scaler runs. Kind-agnostic on purpose: it counts ANY
    # creature, so any creature-token maker pumps it (the serve already excludes
    # non-creature Treasure/Clue makers).
    (
        "tokens_matter",
        re.compile(
            r"(?:gets? \+\d+/\+\d+|power (?:and toughness )?(?:is|are) equal to)"
            r"[^.]*(?:for each (?:other )?creature you control"
            r"|number of creatures you control)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Spellslinger recaster/copier (Mavinda recasts from the yard, Velomachus casts off
    # the top, Naru Meha copies) — a commander that casts or copies instants/sorceries
    # wants prowess/magecraft payoffs. The base spellcast detector keys on the "whenever
    # you cast an instant/sorcery" PAYOFF form; these are enabler/copier forms.
    (
        "spellcast_matters",
        re.compile(
            r"(?:you may cast|cast target|copy target)[^.]*"
            r"(?:instant or sorcery|instant and sorcery)"
            r"|instant and sorcery (?:spells? )?you (?:may )?cast",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Enchantment-TOKEN maker (Scriv "create a white Aura enchantment token", The Rani,
    # Preston Garvey) — makes enchantments, so it's an enchantment deck wanting
    # enchantment payoffs (Eriette, Sphere of Safety).
    (
        "enchantments_matter",
        re.compile(r"create [^.]*\benchantment token", re.IGNORECASE),
        "you",
    ),
    # Celebration (WOE ability word, CR 702.x reminder): every Celebration card carries
    # the exact phrase "two or more nonland permanents entered the battlefield under
    # your control this turn". Only 11 cards share it, so the phrase is its own precise
    # archetype lane — a Celebration commander (Ash) wants the other Celebration
    # payoffs (Grand Ball Guest, Raging Battle Mouse), which the bare attack trigger
    # never surfaced. Same phrase opens (commander) and serves (card).
    (
        "celebration_matters",
        re.compile(
            r"two or more nonland permanents entered the battlefield "
            r"under your control this turn",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Land-sacrifice matters (Gitrog, Titania, Slogurk): a commander that draws/grows
    # when lands hit the graveyard ("whenever … land … put into … graveyard") or pays an
    # ongoing land-sac cost wants repeatable "Sacrifice a land:" OUTLETS (Sylvan
    # Safekeeper, Zuran Orb). A distinct archetype from sacrifice_matters, which
    # deliberately EXCLUDES "sacrifice a land" (the fetchland guard) — so it's its own
    # lane. Same regex opens (commander payoff/cost) and serves (the outlets).
    (
        "land_sacrifice_matters",
        re.compile(
            r"sacrifice a land(?: card)?:"
            r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
            r"put into[^.]*graveyard"
            r"|whenever you sacrifice (?:a|one or more|another) lands?"
            r"|unless you sacrifice a land",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Divinity / indestructible counter → proliferate (Myojin cycle, Arwen). These
    # permanents enter with exactly ONE beneficial counter that gates indestructibility
    # or fuels a "Remove a counter: [big effect]" ability — proliferate multiplies it
    # into more activations / longer protection. Keyed on the counter TYPE because that
    # is the discriminator: divinity/indestructible are always good to multiply, unlike
    # COUNTDOWN counters (slumber, egg) you race to remove, where proliferate is anti-
    # synergy. 11 cards carry the phrase (all Myojins + Arwen); zero false positives.
    (
        "proliferate_matters",
        re.compile(
            r"enters with a(?:n)? (?:divinity|indestructible) counter", re.IGNORECASE
        ),
        "you",
    ),
    # Tapped-creatures-matter (Masako lets tapped creatures block; Saryth grants them
    # deathtouch; Throne of the God-Pharaoh / Dragonscale General scale with the
    # "number of tapped creatures you control"). The deck taps its team freely and
    # cashes in the count. Distinct from tap_untap_matters (becomes-tapped triggers)
    # and from convoke, which taps UNtapped creatures as a cost — the \btapped word
    # boundary keeps "untapped creatures you control" out (no boundary inside the word).
    (
        "tapped_matters",
        re.compile(
            r"number of tapped creatures you control"
            r"|\btapped creatures you control (?:have|get|gain|are|can|with)"
            # Threshold gate ("if you control two or more tapped creatures, <payoff>" —
            # Sami and the EOE tap cluster) and the "for each tapped creature you
            # control" count form. "or more tapped" never matches "or more untapped".
            r"|or more tapped creatures|for each tapped creature you control",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Legends-matter: a commander that TUTORS legends (Captain Sisay "search your
    # library for a legendary card"), BUFFS them (Dihada "target legendary creature
    # gains"), counts/cost-reduces them, or triggers off them (Yomiji "whenever a
    # legendary permanent ... is put into a graveyard"). All want legendary bombs.
    (
        "legends_matter",
        re.compile(
            r"search your library for a legendary"
            r"|target legendary (?:creature|permanent)"
            r"|legendary (?:creatures?|permanents?|spells?) you (?:control|cast)"
            r"|(?:number of|other) legendary"
            r"|whenever (?:a|another|one or more) legendary (?:permanents?|creatures?)"
            r"[^.]*(?:enters|dies|put into a graveyard|leaves the battlefield"
            r"|you control)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Sac-and-return-this-turn engine (Garna, Gerrard, Moira): "return ... creature/
    # permanent cards ... that (died | were put into your graveyard) ... this turn." It
    # wants sac outlets to put creatures in the yard on demand, then brings them back —
    # an aristocrats/sacrifice deck.
    (
        "sacrifice_matters",
        re.compile(
            r"return[^.]*(?:creature|permanent) cards?[^.]*"
            r"(?:died|put there|put into (?:a|your|their) graveyard)[^.]*this turn",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Warp-GRANTING (Tannuk: "cards in your hand have warp") — warp casts a card from
    # hand for its warp cost and exiles it at end of turn, a temporary cheat-into-play.
    # A commander handing out warp is a cheat deck wanting fat creatures + cheat
    # enablers (Ilharg, Maelstrom Colossus), which cheat_into_play serves.
    (
        "cheat_into_play",
        re.compile(r"\bhave warp\b|gains? warp\b", re.IGNORECASE),
        "you",
    ),
    # "Creature DIED this turn" payoff (Faramir draws, Sméagol tempts, Tobias makes
    # Zombies, Ebondeath recasts) — an aristocrats payoff wanting sac fodder + outlets.
    # death-specific ("died ... this turn"), so the broader "put into a graveyard from
    # anywhere this turn" (mill/discard, → graveyard) stays out.
    (
        "death_matters",
        re.compile(
            r"creature[^.]*\bdied\b[^.]*this turn|creatures? that died this turn",
            re.IGNORECASE,
        ),
        "any",
    ),
    # Opponent-SHRINK (Maha: "Creatures your opponents control have base toughness 1") —
    # shrinking opponents' creatures combos with -1/-1 effects (toughness 1 + any -1/-1
    # = dead), so it's a debuff commander wanting -1/-1 anthems and wipes.
    (
        "debuff_matters",
        re.compile(
            r"creatures your opponents control (?:have base (?:power|toughness)|get -)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Player-BURN source (Syr Konrad, Mogis, Go-Shintai, Nekusar) — a commander that
    # deals N/X damage to a player/opponent is a burn deck wanting burn payoffs and
    # damage doublers (direct_damage serves them). Distinct from damage_to_opp_matters,
    # which keys on a "whenever ~ deals COMBAT damage" connect-TRIGGER. Anchored to a
    # PLAYER/opponent target, so creature-only pings (removal) stay out.
    (
        "direct_damage",
        re.compile(
            r"deals (?:\d+|x|that much) damage to "
            r"(?:target player|target opponent|each opponent|that player|any target"
            r"|target player or planeswalker)"
            r"|deals damage equal to [^.]*to "
            r"(?:each opponent|target player|that player|any target)"
            # Target-FIRST variable burn: "deals damage to <player> equal to N"
            # (Anathemancer, Fanatic of Mogis, Corrupt) — the amount-first branch above
            # missed this word order. Player-scoped, so creature bite stays out.
            r"|deals damage to (?:target player|target opponent|each opponent"
            r"|that player|any target|target player or planeswalker) equal to"
            # "<N> damage to that creature's controller" (Shocker, Gimli) — burns the
            # PLAYER even when the "deals" sits a clause away ("deals N to a creature
            # AND N to that creature's controller"). The controller is a player.
            r"|(?:\d+|x|that much) damage to (?:that creature's|that permanent's) "
            r"controller",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Free-creature payoff (Satoru): a commander that rewards creatures entering with
    # "no mana was spent to cast them" wants 0-cost creatures (Ornithopter, Memnite,
    # Phyrexian Walker). "wasn't cast" alone (Preston) is blink/reanimate — NOT this: a
    # 0-cost creature IS cast, just for no mana, so we key on "no mana spent" only.
    (
        "free_creature_payoff",
        re.compile(r"no mana (?:was|is) spent to cast", re.IGNORECASE),
        "you",
    ),
    # Mass-death payoff (Tobias, Nevinyrral, Gadrak, Mahadi): a commander whose reward
    # SCALES with the count of creatures that died this turn ("for each ... creature ...
    # died this turn" / "the number of creatures ... died this turn") wants to force a
    # big death turn and convert it — so it wants board wipes (the maximal death engine)
    # plus MASS-reanimation to refill the wiped board. Keyed on the AGGREGATE/count
    # shape ("for each" / "number of"), NOT a single-death conditional: "if a creature
    # died this turn, <reward>" (Old Flitterfang's one Food, Scorpion, Shessra) earns
    # the same payoff whether 1 or 10 died, so a wipe buys it nothing — that's plain
    # death_matters, not this. Excluding it keeps the lane precise (4 commanders).
    (
        "mass_death_payoff",
        re.compile(
            r"(?:for each|number of) (?:nontoken )?(?:creature|permanent)s?"
            r"[^.]*died this turn",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Per-target payoff (Hinata: "Spells you cast cost {1} less to cast for each
    # target"): a commander whose spells get CHEAPER per target wants spells whose
    # target COUNT scales — X-target / "any number of targets" — so the discount
    # compounds. A unique mechanic (only Hinata in the commander pool), so the lane is
    # exact. Keyed on "less ... for each target": flat cost reduction ("cost {1} less to
    # cast", Goblin Electromancer) is excluded, as is the opponent-tax "more ... per
    # target" half (we want the discount, scoped to YOU).
    (
        "per_target_payoff",
        re.compile(r"less (?:to cast )?for each (?:of those )?target", re.IGNORECASE),
        "you",
    ),
    # Arcane tribal (The Unspeakable, the Kirins, Kodama — Kamigawa Spiritcraft): a
    # commander that cares about ARCANE spells ("cast a Spirit or Arcane spell", "return
    # target Arcane card") wants Arcane-subtype spells (CR 205.3k) + splice-onto-Arcane.
    ("arcane_matters", re.compile(r"\barcane\b", re.IGNORECASE), "you"),
    # Enlist payoff (Aradesh): an enlist commander wants OTHER enlist creatures plus
    # high-power stay-back fodder to tap — enlist adds the tapped creature's POWER (CR
    # 702.150). Reminder text is stripped, so "Enlist" / "enlisted" survives outside it.
    ("enlist_matters", re.compile(r"\benlist(?:ed)?\b", re.IGNORECASE), "you"),
    # Power-scaling TAP engine (Mona Lisa "{T}: Add X = power"; Marwyn, Selvala, Alena):
    # a {T} ability whose output scales with a creature's power wants UNTAP effects (tap
    # the engine again for more) and power pumps (a bigger payoff each tap).
    (
        "power_tap_engine",
        re.compile(
            r"\{t\}:[^.]*(?:equal to|where x is|x is)[^.]*\bpower\b", re.IGNORECASE
        ),
        "you",
    ),
    # Bounce-replay / Sneak (Oroku Saki + the TMNT Sneak legends): "Sneak" / "return an
    # unblocked attacker" recasts a cheap creature, re-firing its ETB. So the commander
    # wants cheap creatures with an AGGRESSIVE enter-trigger ("each opponent discards /
    # loses life") — recast = repeat the bleed. Serving the aggressive ETBs (not every
    # ETB creature) keeps it the precise, color-filtered recast payoff, not goodstuff.
    (
        "recast_etb",
        re.compile(r"\bsneak\b|return an unblocked attacker", re.IGNORECASE),
        "you",
    ),
    # Exert payoff (Johan, Heliod God of the Sun): a commander that grants pseudo-
    # vigilance ("attacking doesn't cause creatures you control to tap" / "creatures you
    # control have vigilance") turns EXERT into a no-downside ability: exert's only cost
    # ("won't untap next turn") is moot when attacking never taps them. So it wants
    # exert creatures.
    (
        "exert_matters",
        re.compile(
            r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap"
            r"|(?:other )?creatures you control have vigilance",
            re.IGNORECASE,
        ),
        "you",
    ),
    # "Can't be blocked unless ALL block" (Tromokratis): the commander connects only if
    # the defender CAN'T field enough blockers, so it wants to TAP DOWN opponents'
    # creatures (Sleep, Blustersquall) before combat — fewer untapped blockers means
    # it's unblockable.
    (
        "tap_down_blockers",
        re.compile(r"can'?t be blocked unless all", re.IGNORECASE),
        "you",
    ),
    # Island matters (Zhou Yu "can't attack unless defending player controls an Island";
    # islandwalk commanders Thada Adel, Wrexial): wants effects that turn opponents'
    # lands into Islands (Quicksilver Fountain, Stormtide Leviathan) so the attack
    # restriction is met / islandwalk connects, plus more islandwalk and island-count.
    (
        "island_matters",
        re.compile(
            r"\bislandwalk\b|can'?t attack unless defending player controls an island",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Newly-entered attacker payoff (Samut: rewards a creature that entered this turn
    # dealing combat damage). It wants HASTE + ETB-pump anthems (Ogre Battledriver,
    # Primal Forcemage) that let a freshly-entered creature swing for value at once.
    (
        "entered_attacker",
        re.compile(
            r"(?:deals combat damage|attacks)[^.]*"
            r"entered (?:the battlefield )?this turn"
            r"|entered (?:the battlefield )?this turn"
            r"[^.]*(?:attacks|deals combat damage)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Land-animation (Noyan Dar, Kamahl, the Tophs): a commander that turns your lands
    # into creatures makes them vulnerable to creature removal AND land destruction, so
    # it wants land PROTECTION (Terra Eternal indestructible-lands, Tomik untargetable-
    # lands, Sacred Ground recursion) to keep the animated lands alive.
    (
        "land_protection",
        re.compile(
            r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
            r"|that land becomes",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Cast-from-hand-or-lose drawback (Phage): a commander that makes you LOSE unless
    # cast from hand wants to negate it — command-zone-to-hand tutors (Netherborn Altar,
    # Command Beacon) so it's cast normally, "you can't lose the game" backstops, and
    # Torpor Orb-style "ETBs don't trigger" to silence the lose-trigger when cheated.
    (
        "lose_unless_hand",
        re.compile(
            r"didn'?t cast (?:it|this) from your hand, you lose the game", re.IGNORECASE
        ),
        "you",
    ),
    # Phasing-lands (Taniwha "all lands you control phase out"): your lands phase back
    # each turn but symmetric land-denial stax hits opponents permanently, so it wants
    # the land-bounce/sac punishers (Mana Breach, Overburden) — asymmetric land denial.
    (
        "land_denial",
        re.compile(r"lands? you control phase", re.IGNORECASE),
        "you",
    ),
    # Repeatable "damage to each creature" board ping (Tibor, Pestilence, Pyrohemia,
    # Plague Spitter): with deathtouch on the source every ping is lethal (CR 702.2b),
    # so it's a recurring one-sided board wipe. The repeatable frame (activated cost,
    # upkeep/end-step trigger, or cast-trigger) is the precision gate -- a one-shot ETB
    # sweep (Chaos Maw) can't be suited up before it resolves, so it stays out.
    (
        "aoe_ping",
        re.compile(
            r"\{[^}]*\}[^.]*:[^.]*deals? \d+ damage to each (?:other )?creature"
            r"|at the beginning of[^.]*deals? \d+ damage to each (?:other )?creature"
            r"|whenever you cast[^.]*deals? \d+ damage to each (?:other )?creature",
            re.IGNORECASE,
        ),
        "you",
    ),
    # A non-Human-attack-trigger engine (Winota, A-Winota) wants evasive attackers that
    # reliably connect to FIRE it: fliers (a useful ~25%-of-pool narrowing, NOT "all
    # non-Humans" at 96%). Flying Humans served here are premium cheat-in targets.
    (
        "nonhuman_attackers",
        re.compile(r"non-?human creatures? you control attacks?", re.IGNORECASE),
        "you",
    ),
    # A commander that exiles a creature YOU OWN and returns it under your control
    # (Meneldor, The Neutrinos -- note "you own", not the usual blink "you control")
    # can reclaim a creature you own but don't control. So it wants control-EXCHANGE
    # (donate a dud via Puca's Mischief, keep their bomb, then reclaim your dud). The
    # "you own" + exile-return is the precision gate (a normal blink says "control").
    (
        "control_exchange",
        re.compile(r"exile [^.]*creature you own[^.]*return", re.IGNORECASE),
        "you",
    ),
    # Kira-style targeting shield: your creatures COUNTER the first spell/ability that
    # targets them ("for the first time each turn, counter"). That makes a CONTINGENT
    # steal (Sower: lost if the thief dies) un-removable and keeps a theft ENGINE alive,
    # the sticky-theft lock. The exact "first time each turn, counter" phrasing is the
    # gate: plain Ward ("counter unless ... pays") is a different per-creature shield.
    (
        "theft_protection",
        re.compile(r"for the first time each turn, counter", re.IGNORECASE),
        "you",
    ),
    # A commander that exiles/takes the top card of a TARGET player's library (Circu's
    # name-lock; Ragavan/Grenzo/Vaan impulse-cast) wants to SEE opponents' tops so it
    # exiles/steals the best card and targets the right player. Tell: "exile the top
    # card of (target player/an opponent/...)".
    (
        "opp_top_exile",
        re.compile(
            r"exile the top card of (?:target player|each opponent|that player"
            r"|an opponent|target opponent)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Fblthp makes the top card's plot cost = its mana cost, so 0-cost cards are free to
    # plot off the top -- the cEDH artifact-combo / storm engine (Hullbreaker + two
    # 0-cost permanents, Sai/Displacer chains). So he wants 0-cost cards. The "plot cost
    # is equal to its mana cost" phrasing is unique to him.
    (
        "free_plot",
        re.compile(r"plot cost is equal to its mana cost", re.IGNORECASE),
        "you",
    ),
    # Multicolor matters (Niv-Mizzet Reborn "for each color pair"; General Ferrous
    # Rokiric, Rienne): a gold-cards commander wants the multicolored PAYOFFS ("whenever
    # you cast a multicolored spell", converge, "multicolored creatures you control"),
    # not just any gold card (that's the whole deck).
    (
        "multicolor_matters",
        re.compile(
            r"for each color pair|exactly those colors|cast a multicolored"
            r"|multicolored (?:creature|permanent|spell)s? you",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Target-your-own payoff (Monk Gyatso): airbends a creature you control when it's
    # targeted, so it wants FREE ways to target your own creatures (the en-Kor "{0}:
    # target a creature you control" cycle, {0}-equip like Shuko).
    (
        "target_own_payoff",
        re.compile(
            r"creature you control becomes the target[^.]*you may", re.IGNORECASE
        ),
        "you",
    ),
    # Self-life-payment (Selenia "Pay 2 life:"; Beledros, Vilis, Chainer): a commander
    # with a repeatable "pay N life:" ability drives its own life low, so it wants
    # life-loss insurance (Phyrexian Unlife "don't lose at 0 life", Angel's Grace).
    (
        "life_payment_insurance",
        re.compile(r"pay \d+ life:", re.IGNORECASE),
        "you",
    ),
    # Land control / exchange (Sharkey taxes + copies opponents' land abilities): a
    # land-control commander wants land-EXCHANGE effects (Political Trickery, Vedalken
    # Plotter) to swap a weak land for an opponent's best while taxing the rest.
    (
        "land_exchange",
        re.compile(
            r"activated abilities of lands[^.]*opponents control"
            r"|exchange control of[^.]*\bland\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Scavenge fuel (Varolz: "each creature card in your graveyard has scavenge … +1/+1
    # counters equal to that card's power"): scavenge converts a creature's POWER into
    # counters, so a scavenge commander wants high-power creatures (Force of Savagery
    # 8/0, Yargle 18/6, Rotting Regisaur) as the biggest scavenge payloads.
    (
        "scavenge_fuel",
        re.compile(r"\bscavenge\b", re.IGNORECASE),
        "you",
    ),
    # Free-spell storm (Thrasta: "costs {3} less for each other spell cast this turn"):
    # a commander whose cost drops per spell cast wants FREE (0-cost) spells to chain,
    # each cutting its cost (Ornithopter, Memnite, Lotus Petal, Mishra's Bauble).
    (
        "free_spell_storm",
        re.compile(
            r"less to cast for each (?:other )?spell[^.]*cast this turn", re.IGNORECASE
        ),
        "you",
    ),
    # Draw-when-targeted (Rayne: "whenever you or a permanent you control becomes the
    # target of a spell or ability an opponent controls, draw"): wants target-REDIRECT
    # (Spellskite, Misdirection) to shunt an opponent's spell onto a cheap permanent,
    # still triggering the draw while protecting the real target.
    (
        "target_redirect",
        re.compile(
            r"becomes? the target of a spell or ability an opponent controls[^.]*draw",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Mana-dork payoff (Raggadragga: "Each creature you control with a mana ability gets
    # +2/+2 ... untap it when it attacks") — a mana-dork deck that wants mana-producing
    # creatures (ramp_matters) and dork support (mana_amplifier).
    (
        "ramp_matters",
        re.compile(r"creatures?[^.]*\bwith (?:a )?mana abilit", re.IGNORECASE),
        "you",
    ),
    (
        "mana_amplifier",
        re.compile(r"creatures?[^.]*\bwith (?:a )?mana abilit", re.IGNORECASE),
        "you",
    ),
    # Beneficial RESOURCE counters — charge (Immard) and experience (Ezuri, Mizzix,
    # Meren) — accumulate for upside, so the commander wants PROLIFERATE (more charge to
    # spend, more experience). Gated to charge/experience only: a PENALTY counter
    # (Arixmethes' slumber, stun, -1/-1 on your own) makes proliferate anti-synergy, so
    # those never open this lane.
    (
        "proliferate_matters",
        re.compile(r"\bcharge counter|\bexperience counter", re.IGNORECASE),
        "you",
    ),
    (
        "treasure_matters",
        re.compile(
            r"create (?:a|an|one|two|three|four|five|\d+|x)[^.]*?\btreasure token"
            r"|\btreasures? you control\b"
            # Treasure-CARE without making it: "if the sacrificed permanent was a
            # Treasure" (Evereth), "sacrifice a Treasure" (Kain) — a Treasure deck.
            r"|sacrifice a treasure|(?:was|were) (?:a |an )?treasures?\b",
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
            # Artifact TUTORS/theft (Arcum, Thada Adel): "search … for a(n)
            # [noncreature] artifact card …" — fetch/steal artifacts to play.
            r"|search [^.]*\bfor [^.]*artifact[^.]*card|noncreature artifact card"
            # Artifact DIG/cheat (Fifteenth Doctor, Jhoira, Muzzio): "put an artifact
            # card … into your hand / onto the battlefield" — and IMPROVISE, an
            # artifact-tap cost mechanic like affinity (reminder stripped → key it).
            r"|put (?:an?|that|up to \w+) artifact cards?[^.]*"
            r"(?:into your hand|onto the battlefield)"
            r"|\bimprovise\b"
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
            # Mutagen (TMNT) is a resource artifact token — sac for a +1/+1 counter,
            # like Food/Clue — so its makers (April O'Neil, Donatello, the Mutant
            # commanders) are artifact decks. NOT the bare parent word "artifact": a
            # "create a Servo/Thopter artifact CREATURE token" go-wide maker is a tokens
            # deck, not an artifacts deck, so only the resource-token subtypes belong.
            r"|junk|incubator|lander|mutagen)\b[^.]*token"
            # "Investigate" IS "create a Clue token" (a colorless artifact, the keyword
            # action) — so an investigate commander (Sophina, Lonis) is an artifact deck
            # whose Clues feed artifact-ETB / affinity payoffs.
            r"|\binvestigate\b"
            # Metalcraft (CR 207.2c ability word: "control three or more artifacts") is
            # an artifacts deck; the italic word prints in the oracle, so match it.
            r"|\bmetalcraft\b"
            # Artifact tutors / digs that reference artifact CARDS (Arcum: "search …
            # for a noncreature artifact card"; Casey/Ashe: "reveal an artifact card")
            # and an artifact-ETB CONDITION (Akal Pakal: "if an artifact entered the
            # battlefield under your control this turn"), plus artifact-spell cost
            # reducers (Urza, Lord Protector).
            r"|search (?:your library )?for an?[^.]*artifact card"
            r"|reveal an artifact card"
            r"|if an artifact entered the battlefield under your control"
            r"|artifact,? instant,? and sorcery spells",
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
            # Enchantress: "whenever you cast an enchantment spell" (Sythis) — also the
            # "your first enchantment spell each turn" wording (Psemilla). The bare
            # "cast an enchantment" missed the "first/second … enchantment spell" forms.
            r"|cast (?:an?|your (?:first|second)) enchantment"
            # Tutors / recursion / hand-matters that reference enchantment CARDS (Zur:
            # "search … for an enchantment card"; Estrid: "return … enchantment cards
            # from your graveyard"; Marina: "put all enchantment cards … into your
            # hand"; Aminatou: "enchantment card in your hand") — the lane keyed only on
            # "enchantments you control" / casting and missed card references.
            r"|search (?:your library )?for an?[^.]*enchantment card"
            r"|return [^.]*enchantment cards?[^.]*(?:graveyard|hand)"
            r"|enchantment cards? in your hand"
            r"|reveal[^.]*enchantment cards?[^.]*hand|put all enchantment cards"
            # Role tokens are Aura ENCHANTMENTS (CR), so a Role-token maker (Gylwain,
            # Ellivere, Syr Armont) is an enchantment commander — floods Auras and wants
            # enchantment-count payoffs (Sanctum Weaver) and Aura support.
            r"|create [^.]*\bRole token",
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
            r"|(?:return|put)[^.]*\baura\b[^.]*\battached\b"
            # "enchanted or equipped" payoffs (Koll), an Aura/Equipment BECOMING
            # attached (Siona), and Equipment-attached combat payoffs (Kassandra) —
            # the lane keyed on "attach"/"equipped creatures" and missed these.
            r"|enchanted or equipped|equipped or enchanted"
            r"|(?:aura|equipment) you control becomes attached"
            r"|(?:legendary )?equipment attached to it",
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
            r"|activate (?:a |one )?loyalty|one or more loyalty"
            # Cares about planeswalkers as a GROUP (Leori: "planeswalker type", copy
            # abilities "of a planeswalker"). The "of a planeswalker" anchor keeps a
            # lone planeswalker-commander's own-loyalty text out.
            r"|planeswalker type"
            r"|abilit(?:y|ies) of (?:a |target |another |each )?planeswalker",
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
    # Doubling is split by WHAT is doubled — token-doubling and counter-doubling are
    # inherently different deck archetypes (a token doubler wants token makers; a
    # counter doubler wants counter sources). There is deliberately NO generic
    # "doubling" lane: mana / life / card-draw / damage doublers are not a distinct
    # commander archetype (zero openers) and fold into ramp / burn / direct_damage.
    (
        "token_doubling",
        re.compile(
            r"create twice that many|double the number of [^.]*tokens?"
            r"|would create[^.]*\binstead\b[^.]*(?:twice|double)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "counter_doubling",
        re.compile(
            r"double the number of [^.]*counters?"
            r"|would put[^.]*counters?[^.]*\binstead\b"
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
            r"|whenever an opponent cast"
            # Symmetric cast-PUNISHER with an adjective the "casts a spell" branch
            # misses: "whenever a player casts a NONCREATURE spell, they lose 2 life"
            # (Mai) / "… deals 6 damage to that player" (Ruric Thar). Gated on a PUNISH
            # effect (they/that player loses/discards/sacrifices, or damage to that
            # player) so benefit-on-cast commanders (Niv-Mizzet draws, April makes a
            # token) stay out of the punish lane.
            r"|whenever (?:a|another) player casts[^.]*(?:(?:they|that player) "
            r"(?:loses?|discards?|sacrifices?)|deals? \d+ damage to that player)",
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
            r"|create a token that's a copy"
            # Populate (CR 702.95) IS "create a token that's a copy of a creature token
            # you control" — a token-copy commander (Ghired, Trostani). The serve
            # already credits \bpopulate\b; the detector missed the keyword.
            r"|\bpopulate\b"
            # A token DOUBLER (Adrix and Nev, Mondrak: "twice that many … tokens are
            # created") is a token-copy commander — it doubles token-copy spells (Rite
            # of Replication, Esix), so route it the copy effects it wants to fork.
            r"|twice that many[^.]*tokens?",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("specialize_matters", re.compile(r"\bspecialize\b", re.IGNORECASE), "you"),
    # Villainous choice (AFR/WHO/Marvel): a commander built around making opponents face
    # villainous choices (The Valeyard doubles them; Davros/Missy/Dr. Eggman present
    # them) wants the villainous-choice card pool. A named mechanic, so a self-contained
    # open==serve lane like venture / specialize.
    ("villainous_choice", re.compile(r"villainous choice", re.IGNORECASE), "you"),
    # Curses (Aura — Curse, enchant player): a commander built around recurring /
    # attaching / casting Curses (Lynde, Cheerful Tormentor) wants the Curse subtype.
    # Anchored on Curse-as-a-card mechanic ("a/target/your Curse", "Curse spells",
    # "Curse card") so the bare card NAME ("Connors's Curse") doesn't qualify.
    (
        "curse_matters",
        re.compile(
            r"curse spells?|curses? you (?:cast|control|own)"
            r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
            re.IGNORECASE,
        ),
        "you",
    ),
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
            r"|target player|that player|each player) discards"
            # Discard-MATTERS payoffs (not just forcers): a commander that triggers on
            # an opponent HAVING discarded — Tinybones "if an opponent discarded a card
            # this turn", or "whenever an opponent discards" — runs the forced-discard
            # package (Bottomless Pit, Oppression, Megrim, Liliana's Caress).
            r"|(?:opponent|player)[^.]{0,20}discarded a card this turn"
            r"|whenever (?:an opponent|a player|another player) discards",
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
    # Undying (CR 702.93a, +1/+1) / Persist (CR 702.79a, -1/-1): the counter-bearing
    # SUBSET of dies_recursion. Distinct lane because the COUNTER is the point for a
    # counters deck — undying feeds +1/+1 synergies, persist feeds -1/-1/aristocrats —
    # whereas the broad dies_recursion lane cares about the recursion itself. These
    # cards open BOTH lanes (dies_recursion includes the undying/persist keywords).
    (
        "undying_persist_matters",
        re.compile(r"\b(?:undying|persist)\b", re.IGNORECASE),
        "you",
    ),
    # -1/-1 counters (CR 122 / 702.80 Wither / 702.90 Infect): the symmetric counter
    # axis counters_matter (hard-pinned to +1/+1) leaves homeless — Hapatra aristocrats.
    ("minus_counters_matter", re.compile(r"-1/-1 counter", re.IGNORECASE), "you"),
    # Cares about its permanents HAVING counters (any kind) — Xolatoyac untaps "each
    # permanent you control with a counter on it", so it wants counter producers. The
    # +1/+1-specific counters_matter detector misses the any-counter form; the "you
    # control with a counter" anchor keeps a bare self-counter body ("enters with a
    # +1/+1 counter on it") out.
    (
        "counters_matter",
        re.compile(
            r"(?:permanents?|creatures?) you control with (?:a |one or more )?"
            r"counters? on (?:it|them)"
            r"|for each (?:permanent|creature) you control with "
            r"(?:a |one or more )?counter",
            re.IGNORECASE,
        ),
        "any",
    ),
    # Creatures-are-lands (Ashaya): "nontoken creatures you control are Forest lands" —
    # its creatures ARE lands, so untap-lands effects (Quirion Ranger, Argothian Elder,
    # Seedborn Muse) untap its creature-lands for mana and re-use -> the untap engine.
    (
        "untap_engine",
        re.compile(
            r"(?:nontoken )?creatures you control are[^.]*\blands\b", re.IGNORECASE
        ),
        "you",
    ),
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

# A recurring-value ENGINE on a legendary: a per-turn triggered ability (upkeep / end
# step / combat) or a repeatable "each turn" effect — the value you'd fork by cloning
# the commander. Reminder text is stripped before this runs.
_PER_TURN_ENGINE_RE = re.compile(
    r"at the beginning of (?:your|each)[^.]*"
    r"(?:upkeep|end step|draw step|combat|main phase)"
    r"|(?:once )?(?:each|every) turn"
    # Extra-turn / extra-phase generators (Obeka Splitter of Seconds: "additional upkeep
    # steps"; Najeela / Aurelia / Moraug: "additional combat phase"; "take an extra
    # turn") are PREMIUM recurring-value engines — cloning multiplies the extra phases.
    r"|(?:additional|extra|another) (?:upkeep|combat|main)[^.]{0,8}(?:step|phase)"
    r"|take (?:an? )?(?:extra|additional) turn|an additional turn",
    re.IGNORECASE,
)
# A tap-activated ability ("{T}: …") is repeatable engine value too — but a pure mana
# dork ("{T}: Add …" as its only ability) is not a clone-worthy VALUE engine.
_TAP_ABILITY_RE = re.compile(r"\{t\}[^:]*:", re.IGNORECASE)
_MANA_TAP_RE = re.compile(r"\{t\}: add\b", re.IGNORECASE)
# A commander whose OWN ability destroys lands (Numot) is a land-destruction engine:
# it wants the LD support package (own-land recursion to survive symmetric LD, plus
# land-loss punishers). "[up to N] target land(s)" is the destroy-lands tell; gated to
# the commander (membership) so a one-shot LD spell in the 99 isn't read as the plan.
_LAND_DESTRUCTION_RE = re.compile(
    r"destroy (?:up to (?:one|two|three|four|\w+) )?target lands?\b", re.IGNORECASE
)
# A commander that reveals the top card of a library and CHEATS a permanent onto the
# battlefield (Vaevictis, Hans Eriksson, Thrasios) curates its top: it wants to stack a
# bomb there (graveyard-to-top). BOTH tells are required so a plain reanimation spell
# ("put ... onto the battlefield" with no reveal) isn't mistaken for a top-cheater.
_CHEAT_TOP_REVEAL_RE = re.compile(r"reveals? the top card", re.IGNORECASE)
_CHEAT_TOP_ONTO_RE = re.compile(
    r"puts? (?:it|that card|them) onto the battlefield", re.IGNORECASE
)
# A commander that repeatedly DESTROYS creatures (an activated {T}/cost ability or a
# recurring trigger) is a reliable death-engine: every kill fires on-death payoffs
# (Blood Artist, Vicious Shadows). The repeatable frame is the precision gate -- a
# one-shot removal spell (Murder: "Destroy target creature.") never registers.
_REPEATABLE_KILL_RE = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*destroy target creature"
    r"|(?:whenever|at the beginning of)[^.]*destroy target creature",
    re.IGNORECASE,
)
# A commander that GENERATES big mana (Neheb "add {R} for each 1 life lost"; Sunastian
# "{T}: Add {C}{C}"; mana doublers) wants X-spell sinks to dump it into (Dan: big-mana-
# GENERATING cards -> X-spells, NOT "high-cmc cards -> X"). The tells: add 2+ symbols at
# once, add-for-each (scales), or "add an additional" (a doubler).
_BIG_MANA_RE = re.compile(
    r"add \{[^}]*\}\{[^}]*\}|add [^.]*for each|add an additional", re.IGNORECASE
)


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
    # Rampage (702.23): "whenever this becomes BLOCKED, +X/+X per extra blocker" — the
    # block trigger is reminder text, so a Rampage commander (Marhault) reads as
    # blocked-matters via the keyword (wants rampage payoffs / lure to force blocks).
    "rampage": ("blocked_matters", "you"),
    "lifelink": ("lifegain_matters", "you"),  # gains life in combat → lifegain payoffs
    "exploit": ("sacrifice_matters", "you"),  # enters → sacrifice a creature
    "devour": ("sacrifice_matters", "you"),  # enters → sacrifice creatures for counters
    "afflict": ("lifeloss_matters", "opponents"),  # becomes blocked → player loses life
    "spectacle": ("lifeloss_matters", "opponents"),  # alt cost if opponent lost life
    "dethrone": ("counters_matter", "any"),  # attacks the top life total → +1/+1
    # +1/+1-counter keyword abilities: a commander with one is a counters deck (Exava=
    # Unleash, Indoraptor=Bloodthirst, Cytoplast=Graft). Mirrors the counters SERVE set.
    "undying": ("counters_matter", "any"),
    # Persist returns with a -1/-1 counter (CR 702.79a), so it wants the -1/-1 serve
    # set, not the +1/+1-centric counters_matter. (Undying/graft are genuinely +1/+1.)
    "persist": ("minus_counters_matter", "you"),
    "graft": ("counters_matter", "any"),
    "riot": ("counters_matter", "any"),
    "bloodthirst": ("counters_matter", "any"),
    "fabricate": ("counters_matter", "any"),
    "sunburst": ("counters_matter", "any"),
    "tribute": ("counters_matter", "any"),
    "unleash": ("counters_matter", "any"),
    "ravenous": ("counters_matter", "any"),
    "reinforce": ("counters_matter", "any"),
    "scavenge": ("counters_matter", "any"),
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
    # "creatures you control with deathtouch …" PLUS the SINGULAR forms a fliers-matter
    # (or any keyword-tribe) commander uses: "creature you control with flying" /
    # "creature spell with flying" (Momo). The "you control"/"spell" qualifier is
    # REQUIRED so anti-tribe removal ("destroy all creatures with flying") stays out;
    # the _ABILITY_KEYWORDS gate validates the captured word.
    (
        re.compile(
            r"\bcreatures? (?:you control |spell )with ([A-Za-z]+)\b", re.IGNORECASE
        ),
        "you",
    ),
    # "all creatures with deathtouch …" (symmetric)
    (
        re.compile(
            r"\bcreatures with ([A-Za-z]+)\b[^.]{0,20}?"
            r"(?:gets? [+\-]|have \"|gains?\b)",
            re.IGNORECASE,
        ),
        "any",
    ),
    # "cast spells with flash or flying from the top …" (Errant and Giada) — a
    # play-from-top engine gated on a keyword rewards that keyword's tribe (here
    # fliers). Capture the second keyword; the _ABILITY_KEYWORDS gate validates it.
    (
        re.compile(
            r"cast spells with flash or ([A-Za-z]+) from the top", re.IGNORECASE
        ),
        "you",
    ),
    # Keyword-tribe TUTOR (Isperia: "search your library for a creature card with
    # flying"): fetching a keyworded creature card IS a keyword-tribe payoff — the
    # "card" form the "you control"/"spell" patterns above didn't cover. Anchored on a
    # FETCH verb (search / reveal) so a self-gain card that buffs off any graveyard ("as
    # long as a creature card with flying is in a graveyard" — Cairn Wanderer) stays
    # out. The _ABILITY_KEYWORDS gate still validates the captured word.
    (
        re.compile(
            r"(?:search(?:es)? (?:their|your) library for|reveal)"
            r"[^.]{0,40}creature cards? with ([A-Za-z]+)",
            re.IGNORECASE,
        ),
        "you",
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
# Signals that do NOT indicate a non-voltron PLAN, so they must not suppress the
# voltron fallback: a Background is archetype-agnostic (Wilson is a vanilla bear to
# suit up), and conditional self-protection is a resilient-beater tell (Thrun). A real
# engine (attack/graveyard/tokens/spellcast) still suppresses; voltron isn't its plan.
_VOLTRON_COMPAT_KEYS = frozenset({"partner_background", "conditional_self_protection"})
# LIKELY-VOLTRON override signals (open the equipment/aura avenue even when another
# signal already fired — the single-big-threat plan co-exists with combat/counter
# engines). Calibrated against EDHREC: base rate "wants the equipment package" = 21.6%.
# (C) Equip/aura PAYOFF in the commander's own oracle — 90% precision / 4.2x lift. The
# strongest, ungated signal: a commander that rewards equipped/enchanted creatures or
# casting Auras & Equipment IS the voltron payoff. The "aura … equipment" co-mention
# catches list forms ("cast an Aura, Equipment, or Vehicle spell" — Sram).
_VOLTRON_EQUIP_RE = re.compile(
    r"equipped creature|enchanted creature|\breconfigure\b|\bequip \{"
    r"|attach[^.]*(?:equipment|aura)|aura[^.]{0,30}equipment|equipment[^.]{0,30}aura"
    r"|cast an? (?:aura|equipment)|(?:equipment|aura)s? you control"
    r"|for each (?:equipment|aura)",
    re.IGNORECASE,
)


def _voltron_self_pump(text: str, name: str) -> bool:
    """True if the commander GROWS ITSELF on combat damage (Mirri: 'whenever Mirri deals
    combat damage …, put a +1/+1 counter on Mirri') — the canonical voltron growth loop.
    Self-scoped (this creature / itself / its name) so a counter placed on 'target' /
    'another' / 'each' creature (a go-wide counters payoff) does NOT qualify."""
    alts = "|".join(["this creature", "itself", *_self_name_alts(name)])
    pat = re.compile(
        rf"deals combat damage[^.]*put a \+1/\+1 counter on (?:{alts})\b", re.IGNORECASE
    )
    return pat.search(text) is not None


def _voltron_self_unblockable(text: str, name: str) -> bool:
    """True if the COMMANDER ITSELF can't be blocked (Tromokratis) — an unblockable fat
    body is a prime voltron threat. Self-scoped so a grant to 'target creature you
    control' / 'creatures you control' (go-wide evasion — Bria) does NOT qualify;
    parenthetical landwalk reminders are already stripped before this runs."""
    alts = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    pat = re.compile(rf"(?:{alts}) can'?t be blocked", re.IGNORECASE)
    return pat.search(text) is not None


def _voltron_self_heroic(text: str, name: str) -> bool:
    """True if the COMMANDER has a SELF-targeting heroic trigger ("whenever you cast a
    spell that targets [itself]", CR 702.86-style: Brigone, Feather, Anax and Cymede).
    Casting an Aura/pump spell on it fires heroic AND suits it up, so it's a single-big-
    threat voltron deck. Self-scoped (this creature / its name) so a trigger targeting
    'another' / 'target creature you control' (a go-wide granter) doesn't qualify."""
    alts = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    pat = re.compile(
        rf"whenever you cast (?:a |an |your )?(?:noncreature )?spell that targets "
        rf"(?:only )?(?:{alts})\b",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _voltron_land_scaler(text: str, name: str) -> bool:
    """True if the COMMANDER's OWN power equals a basic-land-type count (Sima Yi: "Sima
    Yi's power is equal to the number of Swamps you control") — a single mono-color
    scaling threat whose top synergy is the land-scaling equipment that suits it up
    (Nightmare Lash, Lashwrithe). Self-scoped (its name / this creature) so a team
    anthem setting OTHERS' power by a land count isn't read as a suit-up threat."""
    alts = "|".join(["this creature", *_self_name_alts(name)])
    pat = re.compile(
        rf"(?:{alts})'?s power (?:is )?equal to the number of "
        r"(?:plains|islands?|swamps?|mountains?|forests?) you control",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _voltron_self_recurs(text: str, name: str) -> bool:
    """True if the COMMANDER returns ITSELF from the graveyard to the battlefield —
    "return Akuta from your graveyard to the battlefield" (Akuta, Calim): a resilient,
    hard-to-keep-dead threat, hence a prime equipment carrier (voltron, like the
    hexproof tell). Self-scoped (its name / this creature) so a reanimation effect
    returning ANOTHER creature doesn't qualify."""
    alts = "|".join(["this creature", "itself", *_self_name_alts(name)])
    pat = re.compile(
        rf"return (?:{alts}) from (?:your|its owner's) graveyard to the battlefield",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


_VOLTRON_TOKEN_MAKE_RE = re.compile(r"create[^.]*token", re.IGNORECASE)


def _voltron_double_strike_beater(card: dict, text: str) -> bool:
    """True if the commander ITSELF has double strike (Scryfall keyword) and a real body
    (power >= 4) and is NOT a token go-wide engine — a single beater that doubles every
    equipment/aura bonus, so a prime voltron threat (Sabin, Leonardo). The power>=4 +
    no-"create token" gate excludes the double-strike go-wide token-makers (Oketra) that
    are the documented over-fire class for an ungated double-strike rule."""
    kws = {k.lower() for k in (card.get("keywords") or [])}
    if "double strike" not in kws:
        return False
    return card_pt_int(card) >= 4 and not _VOLTRON_TOKEN_MAKE_RE.search(text)


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
    r"\bexile (?:up to \w+ |any number of )?(?:another |one |other )?"
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
    alts = "|".join(["this creature", "~", *_self_name_alts(name)])
    exile_self = re.compile(rf"\bexile (?:{alts})\b", re.IGNORECASE)
    if not (exile_self.search(text) and _SELF_BLINK_RETURN_RE.search(text)):
        return None
    for clause in _clauses(text):
        if _SELF_BLINK_RETURN_RE.search(clause):
            return clause.strip()
    return text[:160]


# Self-death PAYOFF (Kokusho / Junji / Ryusei / Lord Xander): the commander's OWN
# "when ~ dies, <value>" trigger is the engine, so the deck wants to re-trigger that
# death — dies-recursion to bring it back after the trigger, sac outlets to kill it on
# demand, reanimation to recast. Distinct from aristocrats death_matters ("whenever A
# creature you control dies" — CR 700.4, any creature) because it keys on the
# commander ITSELF dying (its name or "this creature"). Value verbs only, so a bare
# "when this dies, return it" (pure dies_recursion / a vanilla death) doesn't register.
_SELF_DEATH_PAYOFF_RE = re.compile(
    r"(?:each opponent|target opponent|each player|target player|that player"
    r"|an opponent)[^.]*(?:loses?|discards?|sacrifices?)"
    r"|you (?:may )?(?:draw|create|return|put|search)"
    # Numeric AND variable damage (Orca: "deals damage equal to its power") — a value
    # death trigger worth re-firing, like the self-ETB damage payoff.
    r"|deals? (?:\d+|x) damage|deals? damage equal to",
    re.IGNORECASE,
)


def _detect_self_death_payoff(text: str, name: str) -> str | None:
    alts = "|".join(["this creature", "~", *_self_name_alts(name)])
    death = re.compile(rf"when (?:{alts})\b[^.]* dies", re.IGNORECASE)
    if not death.search(text):
        return None
    # A VALUE death trigger (Kokusho), OR a self-RECURSION death trigger that returns/
    # exiles-and-returns the commander ITSELF (Lucius, The Scorpion God, The Balrog) —
    # both want the same package (sac outlets to re-fire/loop the death, reanimation).
    # The recursion form is anchored to the dies clause + a self-reference so it isn't a
    # graveyard reanimation of ANOTHER creature.
    recursion = re.compile(
        rf"when (?:{alts})[^.]*? dies,[^.]*(?:return (?:it|this card)|exile it)",
        re.IGNORECASE,
    )
    if not (_SELF_DEATH_PAYOFF_RE.search(text) or recursion.search(text)):
        return None
    for clause in _clauses(text):
        if death.search(clause):
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
# Meld (CR 701.42): a meld piece either melds the pair into a result ("meld them into",
# front) or carries the reminder "(Melds with <front>.)" (back). Either side wants its
# ONE specific partner, so meld_pair is subject-bearing (subject = this card's name);
# the partner names this card, so signal_specs serves exactly it.
_MELD_FULLTEXT_RE = re.compile(r"\bmeld them into\b|\bmelds with\b", re.IGNORECASE)
# Ability-strip-and-buff (Abigale): the strip ("loses all abilities") and the buff
# ("counter on that creature") are different clauses, so this is a full-text check.
_ABILITY_STRIP_RE = re.compile(r"loses all abilities", re.IGNORECASE)
_STRIP_COUNTER_RE = re.compile(r"counter on (?:that creature|it)\b", re.IGNORECASE)
_BASE_PT_SET_RE = re.compile(r"base power and toughness", re.IGNORECASE)


# Self-ETB VALUE trigger (commander-only): a commander whose own "When ~ enters,
# <value>" ability is its engine wants blink/flicker to re-use it (CR 603.6). VALUE
# verbs only — NOT removal (exile/destroy target): O-Ring's "when ~ enters, exile target
# nonland permanent" is removal with a delayed return, not a flicker engine (the
# existing test_oring_removal_is_not_flicker guards this). Excludes mana-ritual/keyword
# ETBs too, so a bare beater doesn't open a Blink avenue.
_SELF_ETB_PAYOFF = (
    # The whole alternation is wrapped in ONE (?:...) group. Without it, the trailing
    # "|choose …" alternative floats to the TOP of the interpolated _self_etb_value
    # pattern and matches a bare "choose one" ANYWHERE — e.g. a DEATH modal ("When ~
    # dies, choose one") — instead of staying anchored under "when ~ enters". (Guarded
    # by test_self_etb_modal_choose_requires_enters_not_dies.)
    r"(?:\b(?:draws?|create|creates|search|searches|look at|reveal|returns?"
    r"|gains? control|put[^.]*counter|mills?|investigate|scry|draft|copy"
    # Damage ETBs are value (Flametongue Kavu — flicker re-fires the burn): numeric
    # "deals N damage" AND the variable forms "deals X damage" / "deals damage equal
    # to …" (Dong Zhou, Ureni, Themberchaud, Jet). Distinct from exile/destroy removal
    # (the O-Ring exclusion), which carries no "deals … damage".
    r"|deals? (?:\d+|x) damage|deals? damage equal to)\b"
    # Modal ETBs ("When ~ enters, choose one —") are value triggers; the value verbs
    # sit in the bullet modes (separate clauses), so credit the modal template itself
    # (CR 700.2). "choose one/two/three/up to" is the modal marker — narrower than bare
    # "choose". Catches Donnie & April, Charming Prince, Aether Channeler.
    r"|choose (?:one|two|three|up to)"
    r")"
)


def _detect_self_damage_prevention(text: str, name: str) -> bool:
    """True if the commander prevents/redirects ALL damage dealt to ITSELF (Cho-Manno,
    Anti-Venom) — the unkillable Pariah redirect target. Name-aware so a generic fog
    ('prevent all combat damage this turn') doesn't qualify."""
    alts = "|".join(["this creature", "~", *_self_name_alts(name)])
    pat = re.compile(
        r"(?:prevent all damage that would be dealt to"
        r"|if damage would be dealt to) "
        rf"(?:{alts})\b",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _self_name_alts(name: str) -> list[str]:
    """Regex-escaped ways a card's oracle refers to itself BY NAME: the short name
    (everything before the first comma — 'Spider-Byte', 'Donnie & April', 'Black Cat')
    and the first meaningful token (legacy nickname forms). Oracle self-references use
    the short name, which may be hyphenated / two-named / multi-word, so keying on the
    first token alone misses them ('Spider' is followed by '-Byte', not ' enters')."""
    alts: list[str] = []
    short = name.split(",", maxsplit=1)[0].strip()
    if short:
        alts.append(re.escape(short))
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            tok = re.escape(w)
            if tok not in alts:
                alts.append(tok)
            break
    return alts


def _self_etb_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self enters-the-battlefield VALUE trigger."""
    alts = "|".join(["this creature", "this permanent", "~", *_self_name_alts(name)])
    # when(?:ever)? + enters? — catch "WHENEVER ~ enters" (Roxanne) and the plural
    # "enter" of two-name commanders ("When Donnie & April enter").
    pat = re.compile(
        rf"\bwhen(?:ever)? (?:{alts}) enters?\b[^.]*?{_SELF_ETB_PAYOFF}", re.IGNORECASE
    )
    for clause in _clauses(text):
        if pat.search(clause):
            return clause.strip()
    return None


def _detect_self_counter_payoff(text: str, name: str) -> bool:
    """True if the commander puts +1/+1 counters on ITSELF and CARES about its counter
    count (Sab-Sunen, Qala, Kyler) — a +1/+1-counters commander. The two-condition gate
    (accumulate AND count-care) excludes incidental self-counter creatures that just get
    a counter on attack/sacrifice without caring about the total (Thraximundar)."""
    alts = "|".join(["this creature", "~", *_self_name_alts(name)])
    accumulate = re.compile(rf"put a \+1/\+1 counter on (?:{alts})\b", re.IGNORECASE)
    count_care = re.compile(
        rf"(?:number of|for each) (?:\+1/\+1 )?counters? on (?:it|itself|{alts})",
        re.IGNORECASE,
    )
    return accumulate.search(text) is not None and count_care.search(text) is not None


# +1/+1-counters PAYOFF that rewards creatures which HAVE counters ("each creature you
# control WITH A COUNTER ON IT …", "unless he HAS A +1/+1 COUNTER ON HIM"). Full-text,
# because the payoff clause and the +1/+1 reference are usually in separate sentences
# (Baxter: "with a counter on it" / "put a +1/+1 counter on Baxter") — the per-clause
# counters_matter detector sees neither clause as complete. Gated on the card mentioning
# "+1/+1 counter" SOMEWHERE, so -1/-1 / charge / named-counter commanders (Volrath,
# Immard) — which never say "+1/+1" — stay out.
_COUNTER_HAVE_PAYOFF = re.compile(
    r"with (?:a |an |one or more )?(?:\+1/\+1 )?counters? on (?:it|them|him|her)"
    r"|has (?:a |an )?\+1/\+1 counter on (?:it|him|her)",
    re.IGNORECASE,
)
_PLUS_ONE_COUNTER = re.compile(r"\+1/\+1 counter", re.IGNORECASE)
# "Double the damage of creatures you control WITH COUNTERS on them" (Raphael, Tidus) is
# a +1/+1-counters DAMAGE payoff — the damage-doubling context implies POSITIVE counters
# (you'd never double the damage of -1/-1 creatures), so no literal "+1/+1" is required;
# this avoids the gate that otherwise needs "+1/+1" and would miss Raphael ("counters").
_COUNTER_DAMAGE_PAYOFF = re.compile(
    r"double [^.]*damage [^.]*creatures? you control with counters?", re.IGNORECASE
)


def _detect_counter_have_payoff(text: str) -> bool:
    """True if a +1/+1-counters commander's payoff rewards creatures that HAVE counters
    (Rishkar, Baxter, Pipsqueak), or doubles counter-creatures' damage (Raphael)."""
    return bool(
        (_PLUS_ONE_COUNTER.search(text) and _COUNTER_HAVE_PAYOFF.search(text))
        or _COUNTER_DAMAGE_PAYOFF.search(text)
    )


# Polymorph/cheat commanders dig until a creature card and PUT IT ONTO THE BATTLEFIELD
# from library/hand (Jalira, Atla Palani, Eladamri) — a library/hand cheat (they want
# big fatties), not graveyard reanimation. Full-text (DOTALL) because the "reveal … a
# creature card." and "Put that card onto the battlefield" halves split across a period,
# and the put-clause says "that card" / "it", not "creature card".
_POLYMORPH_CHEAT_RE = re.compile(
    r"(?:reveal|look at)[\s\S]*?\bcreature card[\s\S]{0,80}?"
    r"put (?:that card|it|that creature card)[\s\S]{0,40}?onto the battlefield",
    re.IGNORECASE,
)


def _detect_polymorph_cheat(text: str) -> bool:
    """True for library/hand polymorph-cheat commanders (see _POLYMORPH_CHEAT_RE).
    Excludes graveyard reanimation (a distinct lane) by the graveyard guard."""
    low = text.lower()
    if "from your graveyard" in low or "from a graveyard" in low:
        return False
    return _POLYMORPH_CHEAT_RE.search(text) is not None


# ACTIVE reanimation in a COMMANDER's own oracle — "return/put a creature card from a
# graveyard onto/to the battlefield" (Alesha, Olivia, Sauron, Sheoldred, Reya). A
# commander that reanimates IS a reanimator deck. Creature-gated by the caller, so the
# reanimation SPELLS / Auras the avenue merely FINDS (Reanimate, Animate Dead —
# instants/sorceries/enchantments) stay enablers, not the archetype label itself.
_ACTIVE_REANIMATION_RE = re.compile(
    r"(?:return|put) (?:target |a |that |all |each )?creature cards?"
    r"[^.]*from (?:a|your|their|target player'?s?|an opponent'?s?|each"
    r"|that player'?s?) graveyard[^.]*(?:to|onto) the battlefield",
    re.IGNORECASE,
)


# Death-trigger payoffs worth re-firing via a clone (Kamigawa dragons: Keiga steals,
# Kokusho drains, Yosei taps down). Mirrors _SELF_ETB_PAYOFF with the death-specific
# verbs (gain control, opponents lose life, skip a step).
_SELF_DIES_PAYOFF = (
    r"\b(?:gains? control|loses? \d+ life|lose life|each opponent|each player"
    r"|draws?|returns?|create|creates|destroys?|exiles?"
    # Numeric AND variable damage (Orca: "deals damage equal to its power").
    r"|deals? (?:\d+|x) damage|deals? damage equal to"
    r"|put[^.]*counter|skips?)\b"
)


def _self_dies_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self DIES VALUE trigger — a clone/token copy
    re-fires it when the copy dies (Keiga, Kokusho). Name-aware (short name like
    Scryfall prints) so 'When Keiga dies' matches."""
    alts = "|".join(["this creature", "this permanent", "~", *_self_name_alts(name)])
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


def _object_oracle(obj: dict | None) -> str:
    """A folded object's full oracle, joining DFC faces. A dungeon's rooms are one face,
    but the Ring / Undercity are "// Card" DFCs with an empty oracle_text field."""
    return (get_oracle_text(obj) or "") if obj else ""


def _fold_referenced_objects(
    card: dict, resolve_object: Callable[[str], dict | None]
) -> dict:
    """Append the oracle of a commander's *folded objects* to its text (ADR-0025).

    A commander's plan can deterministically bring in a separate game-object whose
    effects are part of its strategy. The card-backed case is a **ventured dungeon**:
    the dungeon cards sit in Scryfall ``all_parts`` (which lists ALL of a venturer's
    rules-legal dungeons), so the specific one to fold is disambiguated by the
    commander's own oracle naming it (Acererak → Tomb of Annihilation). A generic
    venturer names no dungeon, so nothing is folded. ``resolve_object`` maps a dungeon
    name to its card (dungeons are excluded from the addable name-index, so this is a
    separate raw-bulk lookup). Returns ``card`` unchanged when nothing folds."""
    text = get_oracle_text(card) or ""
    low = text.lower()
    extra: list[str] = []
    # Chooseable dungeon: all_parts lists every rules-legal dungeon, so fold only the
    # one the commander's oracle NAMES (Acererak → Tomb of Annihilation) — the
    # deterministic one. A generic venturer names none, so nothing folds.
    for part in card.get("all_parts") or []:
        if "dungeon" not in (part.get("type_line") or "").lower():
            continue
        name = part.get("name") or ""
        if name and name.lower() in low:
            extra.append(_object_oracle(resolve_object(name)))
    # Meld result: the commander's plan is to meld into it (conditional on assembling
    # both halves, but it IS the deck's payoff). One result per meld card, named
    # structurally in all_parts, so no oracle disambiguation — fold it directly.
    for part in card.get("all_parts") or []:
        if part.get("component") == "meld_result":
            extra.append(_object_oracle(resolve_object(part.get("name") or "")))
    # Rules-fixed objects: a trigger phrase maps to ONE global object (no need to
    # disambiguate; there is only one Ring, one Initiative dungeon). Read via
    # get_oracle_text — these DFCs keep their text on card_faces, not oracle_text.
    for trigger, obj_name in (
        ("the ring tempts you", "The Ring"),
        ("take the initiative", "Undercity"),
    ):
        if trigger in low:
            extra.append(_object_oracle(resolve_object(obj_name)))
    extra = [e for e in extra if e]
    if not extra:
        return card
    folded = dict(card)
    folded.pop("card_faces", None)  # oracle_text below is now authoritative
    folded["oracle_text"] = text + "\n" + "\n".join(extra)
    return folded


def extract_signals(
    card: dict,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
    resolve_object: Callable[[str], dict | None] | None = None,
) -> list[Signal]:
    """Extract scoped, subject-bearing signals from a card (deterministic baseline).

    ``include_membership`` controls the two signals derived from what the card *is*
    (its characteristics) rather than what it *does*: own-subtype tribal and the
    voltron fallback. These are a commander-level suggestion; when aggregating over a
    whole deck, pass ``include_membership=False`` for the 99 so every creature's race
    and stat-line don't flood the deck's avenues (only the commander's do)."""
    # Fold in the commander's referenced objects (its ventured dungeon, etc. — ADR-0025)
    # before extraction, so the dungeon's effects flow through the normal detectors and
    # cross-opens (append-and-re-extract). No-op when no resolver or nothing to fold.
    if resolve_object is not None:
        card = _fold_referenced_objects(card, resolve_object)
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

    # Theft-archetype siblings (membership). Stealing battlefield permanents
    # (gain_control — Silumgar / Garland / Nihiloor) and borrowing-and-casting what you
    # don't own (theft_matters — Gonti, Hostage Taker, Thief of Sanity) are facets of
    # ONE stealing archetype; a steal commander runs the whole theft package. The card
    # classification stays split (battlefield control change vs play-what-you-don't-own
    # — these are distinct mechanics), so only the COMMANDER cross-opens the sibling
    # lane, at LOW confidence (an archetype suggestion, not a detected payoff). A theft
    # PAYOFF commander — one that rewards permanents "you control but DON'T OWN" (Don
    # Andres, Arvinox, Vaan) — is the same archetype and opens BOTH sibling lanes.
    if include_membership:
        keys_now = {s.key for s in out}
        # "you control/cast/own ... (but) don't own" — covers Don Andres ("creatures you
        # control but don't own"), Arvinox, and Gonti Canny ("spells you cast but don't
        # own"). The bounded gap allows the intervening verb ("cast"/"control").
        dont_own = re.search(
            r"you (?:cast|control|own)?[^.]{0,25}?(?:do not|don't) own",
            text,
            re.IGNORECASE,
        )
        if "gain_control" in keys_now or dont_own:
            add("theft_matters", "opponents", "", text[:160], "low")
        if dont_own and "gain_control" not in keys_now:
            add("gain_control", "you", "", text[:160], "low")
        # Play-from-top engine (Gwenom, Glarb, Reality Chip) curates its top — it wants
        # surveil/scry and top-stacking to set up what it plays. Cross-open the sibling
        # top-of-library lanes (topdeck_selection serves surveil/scry; topdeck_stack the
        # rearrange/put-on-top effects).
        if "play_from_top" in keys_now:
            add("topdeck_selection", "you", "", text[:160], "low")
            add("topdeck_stack", "you", "", text[:160], "low")
        # A token_maker that makes CREATURE tokens (a captured subject: Darien makes
        # Soldiers, Jinnie Fay Cats/Dogs) is a go-wide creatures deck, so cross-open
        # creatures_matter: it wants anthems, per-creature-ETB payoffs (Soul Warden,
        # Impact Tremors), and Cathars' Crusade, none of which the bare token_maker lane
        # serves. Low confidence. Non-creature token makers (Treasure / Clue) never set
        # a token_maker subject, so they stay out. Scoped to token MAKERS (not the
        # broader tokens_matter payoff) so discovery's lane-weighted sort stays clean.
        if "creatures_matter" not in keys_now and any(
            s.key == "token_maker" and s.subject for s in out
        ):
            add("creatures_matter", "you", "", text[:160], "low")
        # A spell-copy commander (Veyran, Zevlor, Rassilon) copies the instants/
        # sorceries you cast, so it's a spellslinger wanting a dense spell base: cross-
        # open spellcast_matters (its serve covers every I/S). Low confidence.
        if "spell_copy_matters" in keys_now and "spellcast_matters" not in keys_now:
            add("spellcast_matters", "you", "", text[:160], "low")
        # A discard-OUTLET commander (loot / rummage / discard-to-pay) fills the
        # graveyard, so the discarded cards become GY fuel: it wants reanimation /
        # flashback / GY recursion. Cross-open graveyard_matters (Niambi reanimates,
        # Mishra recurs artifacts, Malfegor recurs the discarded hand). Low confidence.
        if "discard_outlet" in keys_now and "graveyard_matters" not in keys_now:
            add("graveyard_matters", "you", "", text[:160], "low")
        # A commander that MAKES tribe-X creature tokens (token_maker captured subtype)
        # wants tribe-X lords/support: its token board IS that kindred. Cross-open
        # type_matters=X. Most tribe-MEMBER token-makers already open it via membership;
        # this catches non-members (Grist, a Planeswalker that makes Insects). Low conf.
        for _sub in {s.subject for s in out if s.key == "token_maker" and s.subject}:
            add(signal_keys.TYPE_MATTERS, "you", _sub, text[:160], "low")
        # Lure (force blocks) and blocked_matters (punish the blocker) are one
        # archetype: a commander that lures / must-be-blocked (Madame Vastra, Gorm)
        # wants the punish-when-blocked payoffs (Engulfing Slagwurm, Tolarian
        # Entrancer). One-directional — a bare "when blocked" trigger creature isn't a
        # lure deck, so blocked_matters does NOT cross-open lure.
        if "lure_matters" in keys_now and "blocked_matters" not in keys_now:
            add("blocked_matters", "you", "", text[:160], "low")
        # SIGNIFICANT, repeated, unavoidable self-life-loss bleeds you out without
        # sustain, so the engine wants lifegain to stay alive: (1) MEANINGFUL fixed/
        # scaling bleed — upkeep lose >=2 (Deadpool), cumulative upkeep (Gallowbraid/
        # Morinfen), "you lose life equal to" sac engines (Greven); (2) a PASSIVE death/
        # LTB-triggered draw-AND-bleed engine (Kothophed loses 1 per opponent permanent
        # dying — fast with wipes; Nikara, Tegwyll) — frequent and unavoidable, so the
        # per-event 1 life still decks you. The negligible "lose 1 life" rider on a
        # CONTROLLED attack/sac/value trigger stays out (the over-broad lifeloss trap).
        if re.search(
            r"at the beginning of (?:your|each)[^.]*upkeep[^.]*you lose (?:[2-9]|\d\d) "
            r"life|cumulative upkeep[^.]*life|you lose life equal to"
            # Variable siblings of "you lose life equal to": the Necropotence-style
            # "draw X / lose X" engines (Be'lakor, Imskir, Corpse Augur, Graveborn Muse)
            # and "you lose that much life" (Asmodeus draws its library). Forced, X-/
            # damage-scaled self-bleed — always significant, never a 1-life rider — so
            # it wants lifegain sustain. Optional "you may PAY X life" is NOT "lose" and
            # stays out (the controlled-payment half of the over-broad lifeloss trap).
            r"|you lose x life|you lose that much life"
            r"|whenever[^.]*(?:put into (?:a|their|your) graveyard|dies"
            r"|leaves the battlefield)[^.]*you draw[^.]*you lose \d+ life"
            # Symmetric significant drain — "each player loses [2-9] life" hits YOU too,
            # so a repeated source (a folded Tomb of Annihilation's rooms; a symmetric
            # bleed engine) decks the controller and wants lifegain sustain.
            r"|each player loses (?:[2-9]|\d\d) life",
            text,
            re.IGNORECASE,
        ):
            add("lifegain_matters", "you", "", text[:160], "low")
        # Double strike granted to your ATTACKING team (Raphael) makes attackers deal
        # combat damage to players TWICE — it wants the "whenever creatures you control
        # deal combat damage to a player" payoffs. Tight to "attacking creatures you
        # control have double strike" so go-wide/tribal/conditional double-strike
        # granters (Kwende, Jetmir, Raksha) — not combat-damage-payoff decks — stay out.
        if re.search(
            r"attacking creatures you control have[^.]*double strike",
            text,
            re.IGNORECASE,
        ):
            add("combat_damage_to_opp", "opponents", "", text[:160], "low")
        # SPENDING a counter as an activation cost ("remove a counter from <permanent>:
        # <effect>") means the deck wants MORE counters — i.e. proliferate (Migloz/oil,
        # Rasputin/dream, Tayam/Fain/O'aka/Duchess/The Duke counter-spend engines, plus
        # Myojin/Arwen already opened by the enters-with rule). Keyed on the MECHANIC
        # (the colon = activation cost), not a counter-name list, so it future-proofs
        # for new counter types. COUNTDOWN counters you race to remove (slumber, egg)
        # use "may remove" / upkeep-remove with NO colon-activation, so the colon anchor
        # (bounded by [^:.] so it can't cross a period into a later clause) drops them.
        if re.search(
            r"remove (?:a|an|one|two|three|x|\d+) (?:\w+ )?counters? from "
            r"[^:.\n]{0,40}:",
            text,
            re.IGNORECASE,
        ):
            add("proliferate_matters", "you", "", text[:160], "low")
        # Keyword-soup commander (Odric Lunarch Marshal, Akroma Vision): grants/shares
        # MANY evergreen keywords across the team ("creatures you control gain … if it
        # has …"; Akroma's "+1/+1 if it has <keyword>" enumeration), so it wants
        # creatures STACKED with keywords. >=5 distinct evergreen keywords in a team-
        # grant/"if it has" context isolates the soup-sharer from a single-keyword
        # anthem (Aang's lone vigilance). Reminder text is already stripped from `text`,
        # so a keyword's reminder can't inflate the count.
        if (
            re.search(
                r"creatures you control (?:gain|have)|each other creature you control"
                r"|if it has",
                text,
                re.IGNORECASE,
            )
            and sum(1 for rx in _EVERGREEN_KW_RE if rx.search(text)) >= 5
        ):
            add("keyword_soup_matters", "you", "", text[:160], "low")

    # Own-subtype tribal (membership): a creature's own creature type is a deterministic
    # characteristic (CR 109.3) that tribal cards key off (CR 205.3 / 702.38a), so a
    # Dragon is a viable Dragons build with no tribal oracle text. LOW confidence
    # (membership ≠ a payoff — an oracle "other Dragons you control" wins the dedup at
    # high confidence) and gated to supported race tribes (not generic class types).
    # Commander-only at the deck level — see include_membership.
    type_line = card.get("type_line") or ""
    if include_membership and "creature" in type_line.lower() and "—" in type_line:
        # A class type (Soldier/Cleric/Ninja/…) becomes a build-around only when the
        # commander ALSO rewards a board of creatures, so its own class is gated on a
        # go-wide signal; race tribes (Dragon/Kraken) open unconditionally. (CR 205.3.)
        keys_now = {s.key for s in out}
        _gate = {"creatures_matter", "attack_matters", "anthem_static"}
        go_wide = bool(keys_now & _gate)
        for tok in type_line.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in TRIBAL_SUBTYPES or (sub in CLASS_TRIBES and go_wide):
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), type_line, "low")
    # Named-token tribal (membership): a CREATURE token the commander creates carries
    # its tribe in all_parts even when the oracle uses the token's NAME ("Walker token"
    # = Token Creature Zombie, Enkira). The commander makes that tribe of bodies, so it
    # wants the tribe's kindred: the named-token form of the oracle token_maker -> tribe
    # cross-open. Low confidence; vocab-gated (human / non-subtypes drop out).
    if include_membership:
        for part in card.get("all_parts") or []:
            if part.get("component") != "token":
                continue
            tl = part.get("type_line") or ""
            if "creature" not in tl.lower() or "—" not in tl:
                continue
            for tok in tl.split("—", 1)[1].split():
                sub = tok.strip().lower()
                if sub in CREATURE_SUBTYPES and sub != "human":
                    add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), tl, "low")
    # A commander that IS an artifact / enchantment (the card type is in its type line)
    # is an artifact / enchantment deck — it wants that type's support (affinity & cost
    # reducers; constellation & cheap enchantments), just as a creature is a member of
    # its own tribe. Membership-only, low confidence.
    if include_membership and "artifact" in type_line.lower():
        add("artifacts_matter", "you", "", type_line, "low")
    if include_membership and "enchantment" in type_line.lower():
        add("enchantments_matter", "you", "", type_line, "low")
    # A creature commander whose own ability destroys lands (Numot) is a land-
    # destruction engine — open the LD support lane. Membership + creature gated so a
    # one-shot LD spell among the 99 (Stone Rain) isn't mistaken for the deck's plan.
    if (
        include_membership
        and "creature" in type_line.lower()
        and _LAND_DESTRUCTION_RE.search(text)
    ):
        add("land_destruction", "you", "", "repeatable land destruction", "low")
    # A commander that reveals its top card and cheats a permanent into play (Vaevictis,
    # Hans Eriksson) wants to STACK its top with a bomb. Membership-only: the lane opens
    # because the COMMANDER is the top-cheater, not because the 99 hold one.
    if (
        include_membership
        and _CHEAT_TOP_REVEAL_RE.search(text)
        and _CHEAT_TOP_ONTO_RE.search(text)
    ):
        add("cheat_from_top", "you", "", "reveal-top cheat into play", "low")
    # A creature commander that repeatedly destroys creatures (Diaochan, Visara) is a
    # death-engine WITHOUT a sac outlet: each kill fires on-death payoffs. Membership +
    # creature gated so a one-shot removal spell in the 99 isn't read as the plan.
    if (
        include_membership
        and "creature" in type_line.lower()
        and _REPEATABLE_KILL_RE.search(text)
    ):
        add("kill_engine", "you", "", "repeatable creature destruction", "low")
    # A commander that generates big mana wants X-spell sinks (Neheb, Sunastian).
    # Membership-only: a mana rock in the 99 (Sol Ring) opening this would over-suggest
    # X-spells to every deck — the COMMANDER being the big-mana engine is the signal.
    if include_membership and _BIG_MANA_RE.search(text):
        add("big_mana", "you", "", "big-mana generator", "low")
    # A LEGENDARY creature whose value is a REPEATABLE engine (a per-turn triggered
    # ability, or a non-mana tap-activated ability) is itself a clone target: copying it
    # forks the engine and the copy dodges the legend rule. "Clone your engine" is
    # standard for recurring-value legendaries (Obeka, Koma, Linessa) — Dan's call.
    # Membership-only, low confidence: a commander-level suggestion, never a property of
    # every creature in the 99 (so the deck-aggregate path with include_membership=False
    # doesn't flood every engine creature's clone avenue).
    # "legendary" + "creature" (not the contiguous "legendary creature") so a Legendary
    # ENCHANTMENT/ARTIFACT/SNOW Creature (Go-Shintai, Thassa, the gods) — still a
    # legendary creature, just with an intervening card type — is eligible too.
    _tl = type_line.lower()
    if include_membership and "legendary" in _tl and "creature" in _tl:
        is_engine = bool(_PER_TURN_ENGINE_RE.search(text)) or (
            bool(_TAP_ABILITY_RE.search(text))
            and not (_MANA_TAP_RE.search(text) and text.count("{T}") == 1)
        )
        if is_engine:
            add("clone_matters", "you", "", text[:160], "low")

    # Full-text detectors: trigger→payoff patterns that span a sentence boundary, so
    # the per-clause loop above can't see both halves (Roon, Norin, Aurelia, Alpharael).
    blink_clause = _detect_blink_fulltext(text)
    if blink_clause is not None:
        add("blink_flicker", "you", "", blink_clause)
    self_blink_clause = _detect_self_blink_fulltext(text, name)
    if self_blink_clause is not None:
        add("self_blink", "you", "", self_blink_clause)
    self_death_clause = _detect_self_death_payoff(text, name)
    if self_death_clause is not None:
        add("self_death_payoff", "you", "", self_death_clause)
    # Run against the RAW oracle (not the reminder-stripped `text`): a meld BACK piece
    # (Bruna) carries its meld info only in the "(Melds with …)" reminder, which the
    # per-clause path strips. subject = this card's name; the partner names it.
    _meld_raw = get_oracle_text(card)
    if name and _MELD_FULLTEXT_RE.search(_meld_raw):
        add("meld_pair", "you", name, _meld_raw[:160])
    if _detect_self_counter_payoff(text, name):
        add("counters_matter", "you", "", text[:160])
    if _detect_counter_have_payoff(text):
        add("counters_matter", "you", "", text[:160])
    if _detect_polymorph_cheat(text):
        add("cheat_into_play", "you", "", text[:160])
    # Active reanimation is the reanimator archetype only on a CREATURE (a commander);
    # reanimation spells/Auras stay enablers the avenue finds (_ACTIVE_REANIMATION_RE).
    if is_creature(card) and _ACTIVE_REANIMATION_RE.search(text):
        add("reanimator", "you", "", text[:160])
    if _COMBAT_BUFF_TRIGGER_RE.search(text) and _COMBAT_BUFF_PUMP_RE.search(text):
        add("combat_buff_engine", "you", "", text[:160])
    if _LOOT_FULLTEXT_RE.search(text):
        add("discard_matters", "you", "", text[:160])
    # Ability-strip payoff (Abigale): a commander that STRIPS a creature's abilities and
    # KEEPS it as a beater (keyword counters buff it) wants big cheap creatures whose
    # crippling DRAWBACK it neutralizes (Rotting Regisaur's upkeep-discard → keep the
    # 7/6). Gated on the counter BUFF + NOT a base-P/T set, which excludes the SHRINKERS
    # that turn the target into a small vanilla body (Lizard "becomes a 4/4", Chromium)
    # and pure removal that strips without a buff. CR 613.1f / 122.1b: ability-removal
    # and keyword counters both resolve in layer 6.
    if (
        _ABILITY_STRIP_RE.search(text)
        and _STRIP_COUNTER_RE.search(text)
        and not _BASE_PT_SET_RE.search(text)
    ):
        add("ability_strip_payoff", "you", "", text[:160])
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
    _self = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
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
    # A Background ("Choose a Background") is archetype-agnostic, and conditional self-
    # protection (Thrun, Palladia-Mors: indestructible-on-your-turn / situational
    # hexproof) is itself a voltron tell (a resilient beater; 60% want the equipment
    # package vs 21.6% base). Neither indicates a NON-voltron plan, so neither silences
    # the voltron fallback below; only a real engine does. Backgrounds-only commanders
    # (Wilson) and self-protecting beaters (Thrun) then read as the vanilla voltron
    # bodies they are, instead of being silenced by an orthogonal signal.
    has_other_plan = any(
        s.confidence == "high"
        and s.key not in _GENERIC_KEYS
        and s.key not in _VOLTRON_COMPAT_KEYS
        for s in out
    )
    power = card_pt_int(card)
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
    # Likely-voltron OVERRIDES: open the equipment/aura avenue even when a strong signal
    # already fired (voltron co-exists with combat/counter engines: Mirri is both). Each
    # criterion is the single-big-threat plan, calibrated to clear the mechanical bar
    # (see _VOLTRON_EQUIP_RE / _voltron_self_pump / _voltron_self_unblockable). Double
    # strike alone is NOT here: it over-fires on token go-wide engines (Oketra), so it
    # stays in the path-B fallback below.
    if (
        include_membership
        and "creature" in type_line.lower()
        and (
            _VOLTRON_EQUIP_RE.search(text)  # (C) equip/aura payoff: 90% precision
            or (power >= 2 and _voltron_self_pump(text, name))  # (D) Mirri self-growth
            or (
                power >= 4 and _voltron_self_unblockable(text, name)
            )  # (F) self-unblock
            or _voltron_self_heroic(text, name)  # (G) self-heroic suit-up (Brigone)
            or _voltron_land_scaler(text, name)  # (H) land-scaling threat (Sima Yi)
            or _voltron_self_recurs(text, name)  # (I) self-recurring threat (Akuta)
            or _voltron_double_strike_beater(card, text)  # (J) DS beater (Sabin)
        )
    ):
        add("voltron_matters", "you", "", "likely voltron commander", "low")
    if (
        include_membership
        and not has_other_plan
        and "creature" in type_line.lower()
        and (kws & _VOLTRON_KEYWORDS or power >= 2)
    ):
        add("voltron_matters", "you", "", "commander damage (CR 903.10a)", "low")
    # An extreme power-for-cost beater (power >= 8 AND power >= 2x its mana value: Lord
    # of Tresserhorn 10/4, Yargle 18/6, The Ancient One 8/8 for 2) wins by connecting
    # ONCE for lethal, so it wants damage amplification — grant infect (power -> poison)
    # or double strike (2x). The ratio gate excludes expensive fatties (Emrakul 15/15
    # for 15) that win by size, not amplification. Fires alongside any other plan: the
    # huge body is the threat regardless of incidental text (Lord's drawback ETB).
    cmc = card.get("cmc") or 0
    if (
        include_membership
        and "creature" in type_line.lower()
        and power >= 8
        and power >= 2 * cmc
    ):
        add("one_punch", "you", "", "extreme power-for-cost beater", "low")

    return out


# ── IR-backed signal extraction (Milestone A2 — 5-key vertical slice) ──────────
# extract_signals_ir derives the same Signal(key, scope, subject, …) from the
# structured Card IR instead of regexes, so the two paths can be diffed and the IR
# eventually replaces the regex bag (A4). The slice covers five keys spanning the
# hard axes: a scaling lane (creatures_matter), a payoff lane (lifegain_matters), a
# scoped lane (graveyard_matters), a subject-bearing lane (token_maker), and a
# trigger lane (death_matters). Fan-out to the full vocabulary follows.
# Batch 2b — effect.category → (signal key, fixed scope | None). The CROSSWALK
# "doer" set: a card that DOES X (makes the resource), keyed off the effect.
# None scope = derive from the effect's own scope.
_DOER_EFFECT_KEYS: dict[str, tuple[str, str | None]] = {
    "untap": ("untap_engine", "you"),
    "proliferate": ("proliferate_matters", "you"),
    "topdeck_select": ("topdeck_selection", "you"),
    "gain_control": ("gain_control", "you"),
    "mill": ("mill_matters", "any"),
    "tutor": ("tutor_matters", "you"),
    # Batch P — phase-native mechanic effects.
    "monarch": ("monarch_matters", "you"),
    "suspect": ("suspect_matters", "you"),
    "speed": ("speed_matters", "you"),
    "station": ("station_matters", "you"),
    "venture": ("venture_matters", "you"),
    "connive": ("connive_matters", "you"),
    "damage_prevention": ("damage_prevention", "you"),
    "detain": ("tap_down", "opponents"),
    "seek": ("seek_matters", "you"),  # Alchemy Seek (DD3) — phase parses it
    # Batch 0 — v0.1.60 effect types newly projected (see project.py _EFFECT_CATEGORY).
    "coin_flip": ("coin_flip", "you"),
    "end_the_turn": ("end_the_turn", "you"),
    "extra_turn": ("extra_turns", "you"),
    "set_life": ("life_total_set", "any"),  # scope-agnostic build-around marker
    # reveal_hand → hand_disruption is scope-GATED below (only an opponent-reveal is
    # disruption; "reveal cards in your hand" is a self-reveal, scope "any").
    "regenerate": ("regenerate_matters", "you"),
    "ring_tempt": ("ring_matters", "you"),
    "energy": ("energy_matters", "you"),
    "phasing": ("phasing_matters", "you"),
    "roll_die": ("dice_matters", "you"),
    "dig_until": ("dig_until", "you"),
    # Batch 14 — extra-phase / type-change / mass-goad effect categories.
    "extra_combat": ("extra_combats", "you"),
    "extra_upkeep": ("extra_upkeep", "you"),
    "extra_draw": ("extra_draw_step", "you"),
    "extra_end": ("extra_end_step", "you"),
    "goad_all": ("goad_matters", "opponents"),
    # DEFERRED: type_change — SetCardTypes is kept as accurate IR but the lane
    # fires 0 in commander-legal (the regex's 25 are mostly static "is also a..."
    # which phase models differently); the lane waits for that shape.
    # DEFERRED: clone_matters — the BecomeCopy effect (the "clone" category, kept as
    # accurate IR) is the precise 70 clones, but the regex lane is broad (~1611
    # copy-anything: spell copy, token copy); matching it would conflate distinct
    # copy archetypes, so the lane waits rather than under-cover by 1541.
    # DEFERRED: topdeck_stack — the PutAtLibraryPosition category is accurate IR but
    # includes BOTTOM puts (failed tutors, "rest on the bottom"); firing the
    # top-stacking lane on all 508 floods it (+421). Needs a top-vs-bottom position
    # gate in the projection before the lane can read it.
    # NB: place_counter -> counters_matter is deferred until the projection
    # captures counter KIND (+1/+1 vs loyalty/charge/oil) — firing on every
    # counter placement floods the lane (planeswalkers, one-off charge counters).
    # direct_damage is special-cased below (doer scope "you", offensive only).
}

# Batch 2c — trigger.event → (signal key, fixed scope | None). The CROSSWALK
# "payoff" set: a card that CARES when X happens, keyed off the trigger.
_PAYOFF_TRIGGER_KEYS: dict[str, tuple[str, str | None]] = {
    "cast_spell": ("spellcast_matters", "you"),
    "combat_damage": ("combat_damage_to_opp", "opponents"),
    "attacks": ("attack_matters", "you"),
    "counter_added": ("counters_matter", "you"),
    # Batch 1 — payoff trigger events newly projected in _trigger_event.
    "commit_crime": ("crimes_matter", "you"),
    "scried": ("scry_surveil_matters", "you"),
    "surveiled": ("scry_surveil_matters", "you"),
    # cycled → cycling_matters is scope-GATED below (a SelfRef "when you cycle THIS"
    # bonus is scope "you" and not a cycling-theme payoff). excess_damage DEFERRED:
    # the ExcessDamageAll trigger covers only 4 cards (the regex lane is ~28, mostly
    # trample-excess) — the event mapping stays for accurate IR, but no lane yet.
}

# Batch K — Scryfall keyword (lowercased) → the signal keys it fires. A clean
# structured-field lookup (card["keywords"]), NOT oracle regex, so it survives
# into the IR-native world. One keyword may open several lanes; several keywords
# may open one (poison ← infect/toxic/poisonous; evasion ← menace/fear/…).
_IR_KEYWORD_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "boast": (("boast_matters", "you"),),
    "cascade": (("cascade_matters", "you"),),
    "changeling": (("changeling_matters", "you"),),
    "companion": (("companion_keyword", "you"),),
    "convoke": (("convoke_matters", "you"),),
    "devour": (("devour_matters", "you"),),
    "discover": (("discover_matters", "you"),),
    "foretell": (("foretell_matters", "you"),),
    "madness": (("madness_matters", "you"),),
    "mutate": (("mutate_matters", "you"),),
    "myriad": (("myriad_grant", "you"),),
    "ninjutsu": (("ninjutsu_matters", "you"),),
    "commander ninjutsu": (("ninjutsu_matters", "you"),),
    "infect": (("poison_matters", "opponents"),),
    "toxic": (("poison_matters", "opponents"),),
    "poisonous": (("poison_matters", "opponents"),),
    "scavenge": (("scavenge_fuel", "you"),),
    "soulbond": (("soulbond_matters", "you"),),
    "specialize": (("specialize_matters", "you"),),
    "suspend": (("suspend_matters", "you"),),
    "undying": (("undying_persist_matters", "you"), ("dies_recursion", "you")),
    "persist": (("undying_persist_matters", "you"), ("dies_recursion", "you")),
    "affinity": (("affinity_type", "you"),),
    "islandwalk": (("island_matters", "you"),),
    "enlist": (("enlist_matters", "you"),),
    "exalted": (("exalted_lone_attacker", "you"),),
    "exhaust": (("exhaust_matters", "you"),),
    # NB: cycling/crew/curse are NOT here — having Cycling ≠ a cycling-MATTERS
    # payoff, having Crew ≠ a Vehicle-tribal payoff, being a Curse ≠ curses-matter.
    # Those derive from triggers / Filter subtypes in later batches.
    "menace": (("evasion_self", "you"),),
    "fear": (("evasion_self", "you"),),
    "intimidate": (("evasion_self", "you"),),
    "skulk": (("evasion_self", "you"),),
    "horsemanship": (("evasion_self", "you"),),
    "shadow": (("evasion_self", "you"),),
}

# Kept narrow mechanic-word detectors: REAL mechanics (rules-lawyer-verified —
# voting CR 701.38, firebending CR 702.189, …) that phase v0.1.19 doesn't yet
# STRUCTURE (too recent/niche → Unimplemented). These are narrow keyword-WORD
# regexes (not the brittle "for each Y" kind the IR replaces), so the IR path
# KEEPS them — they survive A4 like the keyword-array / type_line lookups. Grow
# this as more mis-skipped mechanics are rules-lawyer-verified.
_IR_KEPT_DETECTORS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # Voting (CR 701.38). The supplement structures the vote clause into an
    # accurate Effect(category="vote") node where phase emits one, but the LANE
    # stays a kept oracle-scan detector for full coverage: phase leaves some
    # voting cards entirely unparsed (Ballot Broker, The Valeyard) or carries the
    # vote only in a trigger condition (Grudge Keeper), which an IR-only pass
    # can't reach. `\bvotes?\b` (vs the old `\bvote\b`) also catches the plural —
    # e.g. "each player secretly votes" (Trap the Trespassers), which the regex
    # _DETECTORS path still misses.
    (
        "voting_matters",
        re.compile(
            r"will of the council|council's dilemma|each player[^.]*votes?|\bvotes?\b",
            re.IGNORECASE,
        ),
        "each",
    ),
    # The four bending keywords are SEPARATE mechanics (rules-lawyer-verified;
    # no unifying "bending ability" rule exists, no card references the set), so
    # each gets its own lane rather than one conflated bending_matters: airbend
    # (CR 701.65), earthbend (CR 701.66), waterbend (CR 701.67), firebending
    # (CR 702.189). These mirror the same-named _sweep_detectors regexes.
    ("airbend_matters", re.compile(r"\bairbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    ("earthbend_matters", re.compile(r"\bearthbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    ("waterbend_matters", re.compile(r"\bwaterbend(?:ing|s)?\b", re.IGNORECASE), "you"),
    (
        "firebending_matters",
        re.compile(r"\bfirebend(?:ing|s)?\b", re.IGNORECASE),
        "you",
    ),
)

# Keys the keyword-array detectors emit (reused verbatim by the IR path, same
# Scryfall source as the regex path → perfect parity).
_IR_KEYWORD_KEYS: frozenset[str] = (
    frozenset(key for key, _scope in _PRESET_KEYWORD_SIGNALS.values())
    | frozenset(key for key, _scope in _DIRECT_KEYWORD_SIGNALS.values())
    | frozenset(k for pairs in _IR_KEYWORD_MAP.values() for k, _s in pairs)
)

IR_SLICE_KEYS: frozenset[str] = (
    frozenset(
        {
            "creatures_matter",
            "lifegain_matters",
            "graveyard_matters",
            signal_keys.TOKEN_MAKER,
            "death_matters",
            # Batch 1 (aristocrats/recursion):
            "self_death_payoff",
            "reanimator",
            # Batch 2b (special-cased doer):
            "direct_damage",
            # Batch 3 (tribal — oracle-ability subjects; type_line membership is a
            # structured-field lookup reused at A4, so REGEX_ONLY here = membership):
            signal_keys.TYPE_MATTERS,
            # Batch K (type_line membership):
            "artifacts_matter",
            "enchantments_matter",
            # Batch E (effect-category lanes):
            "counters_matter",
            "minus_counters_matter",
            "oil_counter_matters",
            "shield_counter_matters",
            "rad_counter_matters",
            "ki_counter_matters",
            "counter_control",
            "fight_matters",
            "ramp_matters",
            "group_mana",
            "blink_flicker",
            "draw_for_each",
            "group_hug_draw",
            "symmetric_damage_each",
            "opponent_discard",
            "sacrifice_matters",
            "donate_matters",
            "land_exchange",
            "land_destruction",
            "kill_engine",
            "removal_matters",
            "exile_removal",
            "opponent_exile_matters",
            "tap_down",
            "scaling_pump",
            "lands_matter",
            "treasure_matters",
            "clue_matters",
            "food_matters",
            "blood_matters",
            "creature_recursion",
            # Batch T (trigger-event lanes):
            "tap_untap_matters",
            "discard_matters",
            "draw_matters",
            "creature_etb",
            "combat_damage_matters",
            "creature_cast_trigger",
            signal_keys.TYPED_SPELLCAST,
            # Batch P (phase-native mechanic effects):
            "monarch_matters",
            "suspect_matters",
            "venture_matters",
            "connive_matters",
            "damage_prevention",
            # Batch ST (static restriction → stax):
            "stax_taxes",
            "symmetric_stax",
            # Batch R (v0.1.60 replacement-effect doublers, split by event):
            "token_doubling",
            "counter_doubling",
            "damage_doubling",  # Batch 10
            # Batch 0 — scope-gated lane (not in the _DOER table):
            "hand_disruption",
            # Batch 1 — scope-gated cycling payoff (not in _PAYOFF_TRIGGER_KEYS):
            "cycling_matters",
            # Batch 14 — landfall (a land-ETB trigger; CR 207.2c ability word):
            "landfall",
            # Batch 9 — cheat a creature into play (library/hand → battlefield):
            "cheat_into_play",
            # Batch 2 — cost-based + Filter-predicate lanes:
            "life_payment_insurance",
            "legends_matter",
            "historic_matters",
            # Digital mechanic that was mis-skipped — phase parses Seek (Alchemy
            # DD3, now in rules-lawyer's digital supplement).
            "seek_matters",
            # Kept narrow detectors — real mechanics phase doesn't structure
            # (rules-lawyer-verified): voting (CR 701.38); the four distinct
            # bending keywords (airbend CR 701.65, earthbend 701.66, waterbend
            # 701.67, firebending 702.189) — each its own lane, never conflated.
            "voting_matters",
            "airbend_matters",
            "earthbend_matters",
            "waterbend_matters",
            "firebending_matters",
        }
    )
    # Batch 2a (keyword-array signals — same source as regex, full parity):
    | _IR_KEYWORD_KEYS
    # Batch 2b/2c (effect-doer + trigger-payoff lanes):
    | frozenset(key for key, _scope in _DOER_EFFECT_KEYS.values())
    | frozenset(key for key, _scope in _PAYOFF_TRIGGER_KEYS.values())
)

# IR scope vocab ("opp") → Signal scope vocab ("opponents").
_IR_TO_SIGNAL_SCOPE = {"you": "you", "opp": "opponents", "each": "each", "any": "any"}


def _ir_scope(scope: str) -> str:
    return _IR_TO_SIGNAL_SCOPE.get(scope, "any")


def _is_generic_creature_filter(f: object) -> bool:
    """A GENERIC 'creatures you control' filter (no tribe) — the creatures_matter
    anthem/scaling shape. A tribal filter (subtypes set) is type_matters, not this."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and not f.subtypes
        and f.controller == "you"
    )


# Batch E — counter KIND → (signal key, scope). NB: p1p1 is deliberately ABSENT
# — +1/+1 counters are ubiquitous, so place_counter→counters_matter floods the
# lane (1552 IR_ONLY); counters_matter derives from the counter_added trigger +
# the +1/+1-keyword set instead. The off-+1/+1 kinds are precise.
_COUNTER_KIND_KEYS: dict[str, tuple[str, str]] = {
    "m1m1": ("minus_counters_matter", "you"),
    "oil": ("oil_counter_matters", "you"),
    "shield": ("shield_counter_matters", "you"),
    "rad": ("rad_counter_matters", "opponents"),
    "ki": ("ki_counter_matters", "you"),
}

_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)

# Batch E — made artifact-token subtype → (signal key, scope).
_TOKEN_SUBTYPE_KEYS: dict[str, tuple[str, str]] = {
    "treasure": ("treasure_matters", "you"),
    "clue": ("clue_matters", "you"),
    "food": ("food_matters", "you"),
    "blood": ("blood_matters", "you"),
}


def _ftypes(f: object) -> frozenset[str]:
    return frozenset(f.card_types) if isinstance(f, Filter) else frozenset()


def _filter_controller(f: object) -> str:
    return f.controller if isinstance(f, Filter) else "any"


def _fsubs_lower(f: object) -> frozenset[str]:
    return (
        frozenset(s.lower() for s in f.subtypes)
        if isinstance(f, Filter)
        else frozenset()
    )


def _reanimates_creature(e: object) -> bool:
    """A reanimate effect that returns CREATURE cards (matches the regex detector,
    which requires 'creature cards' — a Permanent-card return like Sun Titan is a
    separate recursion engine, not the reanimator archetype)."""
    f = getattr(e, "subject", None)
    return isinstance(f, Filter) and "Creature" in f.card_types


def _kindred_subjects(f: object, vocab: frozenset[str]) -> list[str]:
    """Resolved creature-subtype subjects of a YOUR-controlled (or unscoped) Filter
    — the tribal payoff axis ("Goblins you control", "for each Goblin you control").
    An opponent-controlled tribe is not your tribal build-around, so it's dropped."""
    if not isinstance(f, Filter) or f.controller == "opp":
        return []
    return [s for s in (_resolve_subject(x, vocab) for x in f.subtypes) if s]


def _token_kindred_subject(f: object, vocab: frozenset[str]) -> str | None:
    """A creature-token filter → its resolved kindred subject ("" if none); None for
    a non-creature token (which token_maker does not cover). Matches the regex
    detector's 'last creature subtype' choice."""
    if not isinstance(f, Filter) or "Creature" not in f.card_types:
        return None
    for raw in reversed(f.subtypes):
        subject = _resolve_subject(raw, vocab)
        if subject:
            return subject
    return ""


def extract_signals_ir(
    card: dict, ir: Card | None, *, vocab: frozenset[str] = CREATURE_SUBTYPES
) -> list[Signal]:
    """Derive the A2 slice of Signals from the structured Card IR (5 keys).

    Same Signal contract as ``extract_signals``, restricted to ``IR_SLICE_KEYS`` so
    the two paths can be diffed key-for-key. Returns ``[]`` when the card has no IR
    (not yet projected / brand-new set) so a dispatcher can fall back to regexes."""
    if ir is None:
        return []
    name = card.get("name", "")
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(key: str, scope: str, subject: str, raw: str, conf: str = "high") -> None:
        ident = (key, scope, subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(Signal(key, scope, subject, raw, name, conf))

    # A self-cast-from-graveyard card (flashback / escape / disturb …) cares about
    # its own graveyard.
    if "graveyard" in ir.castable_zones:
        add("graveyard_matters", "you", "", "")

    for ab in ir.all_abilities():
        for e in ab.effects:
            # creatures_matter = a go-wide/scaling lane: a count operand over your
            # creatures (any effect), OR an anthem buffing them (a pump's affected
            # set). NOT a single reanimate/destroy TARGET that happens to be a
            # creature you control — gate the affected-set case on the pump shape.
            amount_subject = e.amount.subject if e.amount is not None else None
            if _is_generic_creature_filter(amount_subject) or (
                e.category == "pump" and _is_generic_creature_filter(e.subject)
            ):
                add("creatures_matter", "you", "", e.raw)
            if e.category == "gain_life" and e.scope in ("you", "any"):
                add("lifegain_matters", "you", "", e.raw)
            if e.category in ("reanimate", "mill"):
                add("graveyard_matters", _ir_scope(e.scope), "", e.raw)
            # token_maker only when the token goes to YOU — "destroy target
            # creature, its controller makes a Beast" (scope opp) is removal.
            if e.category == "make_token" and e.scope in ("you", "any"):
                subject = _token_kindred_subject(e.subject, vocab)
                if subject is not None:
                    add(signal_keys.TOKEN_MAKER, "you", subject, e.raw)
            # reanimator (the ARCHETYPE) is a creature that actively returns
            # creatures from a graveyard to the battlefield — a commander, not a
            # one-shot spell (those stay enablers the avenue finds).
            if (
                e.category == "reanimate"
                and is_creature(card)
                and _reanimates_creature(e)
            ):
                add("reanimator", "you", "", e.raw)
            # Batch 2b — effect-category "doer" lanes (the CROSSWALK doer set).
            doer = _DOER_EFFECT_KEYS.get(e.category)
            if doer is not None:
                key, fixed_scope = doer
                add(key, fixed_scope or _ir_scope(e.scope), "", e.raw)
            # direct_damage is a doer (scope "you" = you control the source);
            # gate out incidental SELF-damage (painlands, talismans target you).
            if e.category == "damage" and e.scope != "you":
                add("direct_damage", "you", "", e.raw)
            # Batch 3 — tribal type_matters: a subtype anthem/count over YOUR
            # creatures (Goblin lord, "for each Goblin you control"). The token
            # TYPE a token_maker makes is token_maker, not type_matters.
            for sub in _kindred_subjects(amount_subject, vocab):
                add(signal_keys.TYPE_MATTERS, "you", sub, e.raw)
            if e.category != "make_token":
                for sub in _kindred_subjects(e.subject, vocab):
                    add(signal_keys.TYPE_MATTERS, "you", sub, e.raw)
            # ── Batch E — effect-category lanes ──
            cat = e.category
            ftypes = _ftypes(e.subject)
            if cat == "place_counter" and e.counter_kind in _COUNTER_KIND_KEYS:
                ck_key, ck_scope = _COUNTER_KIND_KEYS[e.counter_kind]
                add(ck_key, ck_scope, "", e.raw)
            if cat == "counter_spell":
                add("counter_control", "you", "", e.raw)
            if cat == "fight":
                add("fight_matters", "you", "", e.raw)
            if cat == "ramp":
                add("ramp_matters", "you", "", e.raw)
                if e.scope == "each":
                    add("group_mana", "each", "", e.raw)
            if cat == "blink":
                add("blink_flicker", "you", "", e.raw)
            # Batch 9 — cheat a CREATURE into play (a land into play is ramp).
            if cat == "cheat_play" and "Creature" in ftypes:
                add("cheat_into_play", "you", "", e.raw)
            if cat == "draw":
                if e.amount is not None and e.amount.op in ("count", "multiply"):
                    add("draw_for_each", "you", "", e.raw)
                if e.scope == "each":
                    add("group_hug_draw", "each", "", e.raw)
            if cat == "damage" and e.scope == "each":
                add("symmetric_damage_each", "each", "", e.raw)
            if cat == "discard" and e.scope == "opp":
                add("opponent_discard", "opponents", "", e.raw)
            # An edict forces OPPONENTS / each player to sacrifice — gate on an
            # explicit opp/each scope (an unscoped sacrifice effect is ambiguous,
            # often a self-sac inside a larger effect, so don't call it an edict).
            # A sac OUTLET is a COST (handled per-ability below).
            if cat == "sacrifice" and e.scope in ("opp", "each"):
                add("edict_matters", _ir_scope(e.scope), "", e.raw)
            if cat == "gain_control":
                if e.scope == "opp":
                    add("donate_matters", "you", "", e.raw)
                if "Land" in ftypes:
                    add("land_exchange", "you", "", e.raw)
            if cat == "destroy":
                if "Land" in ftypes:
                    add("land_destruction", "you", "", e.raw)
                if "Creature" in ftypes and ab.kind in ("activated", "triggered"):
                    add("kill_engine", "you", "", e.raw)
                if ftypes & _PERMANENT_TYPES:
                    add("removal_matters", "you", "", e.raw)
            if cat == "exile" and ftypes & _PERMANENT_TYPES:
                add("exile_removal", "you", "", e.raw)
                if e.scope == "opp":
                    add("opponent_exile_matters", "opponents", "", e.raw)
            if cat == "tap" and e.scope == "opp":
                add("tap_down", "opponents", "", e.raw)
            if (
                cat == "pump"
                and e.amount is not None
                and e.amount.op in ("count", "multiply")
            ):
                add("scaling_pump", "you", "", e.raw)
            if amount_subject is not None and "Land" in _ftypes(amount_subject):
                add("lands_matter", "you", "", e.raw)
            if cat == "make_token":
                for st in _fsubs_lower(e.subject):
                    if st in _TOKEN_SUBTYPE_KEYS:
                        tk, ts = _TOKEN_SUBTYPE_KEYS[st]
                        add(tk, ts, "", e.raw)
            if cat == "reanimate" and "Creature" in ftypes:
                add("creature_recursion", "you", "", e.raw)
            if cat == "animate" and "Artifact" in ftypes:
                add("animate_artifact", "you", "", e.raw)
            # Stax: a static restriction hobbling OPPONENTS (stax_taxes) or
            # everyone symmetrically (symmetric_stax).
            if cat == "restriction":
                if e.scope == "opp":
                    add("stax_taxes", "opponents", "", e.raw)
                elif e.scope == "each":
                    add("symmetric_stax", "each", "", e.raw)
            # Doubling replacements (v0.1.60's `replacements`), split by event —
            # a token doubler and a counter doubler are different archetypes.
            if cat == "token_doubling":
                add("token_doubling", "you", "", e.raw)
            if cat == "counter_doubling":
                add("counter_doubling", "you", "", e.raw)
            if cat == "damage_doubling":  # Batch 10 — DamageDone replacement doubler
                add("damage_doubling", "you", "", e.raw)
            # hand_disruption only when an OPPONENT reveals (a self-reveal — "reveal
            # cards in your hand" — is scope "any" and not disruption).
            if cat == "reveal_hand" and e.scope == "opp":
                add("hand_disruption", "opponents", "", e.raw)
        # Cost-based lanes (Ability.cost — a sacrifice OUTLET vs a sac effect).
        if ab.cost:
            cost_parts = set(ab.cost.split(","))
            if "sacrifice" in cost_parts:
                add("sacrifice_matters", "you", "", "")
            # Batch 2 — a repeatable pay-life COST wants lifegain insurance.
            if "paylife" in cost_parts:
                add("life_payment_insurance", "you", "", "")
            # DEFERRED: discard_outlet — the "discard" cost includes Cycling
            # ("Discard this card"), a SELF-discard, so firing on every discard cost
            # floods the lane (+471). Needs a discard-self vs discard-other split in
            # the cost projection (like sacself vs sacrifice) before the lane fires.
        trig = ab.trigger
        if trig is not None:
            # death_matters is the ARISTOCRATS payoff — OTHER creatures dying. A
            # "when this dies" self-death trigger (SelfRef → no subject filter) is
            # self_death_payoff, a different lane, so gate on a real subject.
            if trig.event == "dies" and trig.subject is not None:
                add("death_matters", _ir_scope(trig.scope), "", "")
            # The complement: a true SELF-death trigger (SelfRef → scope "you")
            # that produces a recognized payoff (Kokusho, Solemn, Festering Goblin)
            # — wants sac outlets + recursion. Gating on SelfRef excludes
            # "equipped creature dies" (Skullclamp, AttachedTo → scope "any"); the
            # recognized-effect gate drops unparsed "other"-only death triggers.
            elif (
                trig.event == "dies"
                and trig.scope == "you"
                and any(e.category != "other" for e in ab.effects)
            ):
                add("self_death_payoff", "you", "", "")
            if trig.event == "life_gained":
                add("lifegain_matters", "you", "", "")
            # Batch 2c — trigger-event "payoff" lanes.
            payoff = _PAYOFF_TRIGGER_KEYS.get(trig.event)
            if payoff is not None:
                key, fixed_scope = payoff
                add(key, fixed_scope or _ir_scope(trig.scope), "", "")
            # Batch 1 — cycling_matters: a "whenever you cycle a card" payoff (valid
            # card null → scope "any"), NOT a SelfRef "when you cycle THIS" bonus
            # (scope "you" — having cycling ≠ a cycling-theme payoff).
            if trig.event == "cycled" and trig.scope != "you":
                add("cycling_matters", "you", "", "")
            # Batch 3 — tribal trigger ("whenever a Goblin you control enters").
            for sub in _kindred_subjects(trig.subject, vocab):
                add(signal_keys.TYPE_MATTERS, "you", sub, "")
            # ── Batch T — trigger-event lanes ──
            ev = trig.event
            tsubs = _ftypes(trig.subject)
            tsub_kinds = _fsubs_lower(trig.subject)
            if ev == "taps":
                add("tap_untap_matters", "you", "", "")
            if ev == "discarded":
                add("discard_matters", "you", "", "")
            if ev == "drawn":
                add("draw_matters", "you", "", "")
            # creature_etb (ETB-VALUE) — cares when OTHER creatures enter (a Typed
            # subject; a self-ETB SelfRef→None is a one-shot, not this lane). Scope
            # tracks WHOSE entering creature triggers it (yours = value, an
            # opponent's = punisher), as the regex forces.
            if ev == "etb" and "Creature" in tsubs:
                add(
                    "creature_etb",
                    "opponents" if _filter_controller(trig.subject) == "opp" else "you",
                    "",
                    "",
                )
            # Batch 14 — landfall: a land ENTERING (etb trigger w/ Land subject) is
            # the bulk of landfall; the LandPlayed "play a land" trigger (_PAYOFF)
            # catches the rest.
            if ev == "etb" and "Land" in tsubs:
                add("landfall", "you", "", "")
            if ev in ("combat_damage", "deals_damage"):
                add("combat_damage_matters", "opponents", "", "")
                if trig.scope == "opp":
                    add("damage_to_opp_matters", "opponents", "", "")
                if tsub_kinds:
                    add("tribe_damage_trigger", "you", "", "")
            if ev == "cast_spell":
                if trig.scope == "opp":
                    add("opponent_cast_matters", "opponents", "", "")
                if "Creature" in tsubs:
                    add("creature_cast_trigger", "any", "", "")
                for sub in _kindred_subjects(trig.subject, vocab):
                    add(signal_keys.TYPED_SPELLCAST, "you", sub, "")

    # Batch 2 — card-level Filter-predicate lanes: an effect/trigger that cares
    # about a Legendary / Historic object (the predicate is on its subject Filter).
    ir_predicates: set[str] = set()
    for ab in ir.all_abilities():
        subs: list[object] = [e.subject for e in ab.effects]
        subs += [e.amount.subject for e in ab.effects if e.amount is not None]
        if ab.trigger is not None:
            subs.append(ab.trigger.subject)
        for f in subs:
            if isinstance(f, Filter):
                ir_predicates.update(f.predicates)
    if "HasSupertype:Legendary" in ir_predicates:
        add("legends_matter", "you", "", "")
    if "Historic" in ir_predicates:
        add("historic_matters", "you", "", "")

    # Keyword-array signals (Batch 2a): authoritative Scryfall keyword lookups,
    # NOT oracle regex — they already survive into the IR-native world, so reuse
    # the existing detectors. Same source as the regex path → perfect parity.
    for key, scope in _detect_keyword_presets(card):
        add(key, scope, "", "")
    for key, scope in _detect_direct_keywords(card):
        add(key, scope, "", "")
    # Kept narrow mechanic-word detectors (real mechanics phase doesn't structure).
    kept_oracle = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")
    for key, pat, scope in _IR_KEPT_DETECTORS:
        if pat.search(kept_oracle):
            add(key, scope, "", "")

    # Batch K — additional keyword-array lanes + type_line membership (clean
    # structured-field lookups; membership is low-confidence, as in the regex path).
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    for kw, pairs in _IR_KEYWORD_MAP.items():
        if kw in card_kws:
            for key, scope in pairs:
                add(key, scope, "", "")
    type_line = (card.get("type_line") or "").lower()
    if "artifact" in type_line:
        add("artifacts_matter", "you", "", "", "low")
    if "enchantment" in type_line:
        add("enchantments_matter", "you", "", "", "low")
    # Own-subtype tribal membership (a creature's own race) + named-token tribes —
    # a clean type_line / all_parts field-lookup. Class tribes (Soldier/Cleric)
    # open only behind a go-wide signal; race tribes open unconditionally (CR 205.3).
    keys_now = {s.key for s in out}
    go_wide = bool(keys_now & {"creatures_matter", "attack_matters", "anthem_static"})
    if "creature" in type_line and "—" in type_line:
        for tok in type_line.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in TRIBAL_SUBTYPES or (sub in CLASS_TRIBES and go_wide):
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
    for part in card.get("all_parts") or []:
        if part.get("component") != "token":
            continue
        tl = (part.get("type_line") or "").lower()
        if "creature" not in tl or "—" not in tl:
            continue
        for tok in tl.split("—", 1)[1].split():
            sub = tok.strip().lower()
            if sub in CREATURE_SUBTYPES and sub != "human":
                add(signal_keys.TYPE_MATTERS, "you", sub.capitalize(), "", "low")
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
    records: Sequence[dict | None],
    commander_names: set[str],
    *,
    resolve_object: Callable[[str], dict | None] | None = None,
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
        # Folded objects (a ventured dungeon — ADR-0025) belong to the COMMANDER's plan,
        # so only fold for the commander, never the 99.
        for sig in extract_signals(
            card,
            include_membership=is_cmd,
            resolve_object=resolve_object if is_cmd else None,
        ):
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
    {
        "self_blink",
        "combat_buff_engine",
        "discard_matters",
        "card_draw_engine",
        "ability_strip_payoff",
        "land_destruction",
        "cheat_from_top",
        "kill_engine",
        "one_punch",
        "big_mana",
    }
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
