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
from mtg_utils._deck_forge._sweep_detectors import (
    KEYWORD_COUNTER_REGEX,
    SPELL_KEYWORD_GRANT_REGEX,
    SWEEP_DETECTORS,
    TARGET_PLAYER_DRAWS_REGEX,
)
from mtg_utils.card_classify import card_pt_int, get_oracle_text, is_creature
from mtg_utils.card_ir import Card, Condition, Effect, Filter, Quantity
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
# ADR-0027 keyword_soup: phase's grant_keyword counter_kind is spaceless
# ("firststrike"/"doublestrike"), so normalize the evergreen word set the same way
# for the per-ability distinct-keyword count.
_EVERGREEN_CK: frozenset[str] = frozenset(
    kw.replace(" ", "") for kw in _EVERGREEN_KW_WORDS
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
    # ADR-0027 t2b4-C: type_change ("protection from <subtype>" — Gor Muldrak) migrated
    # to the Card IR (kept_detector). phase DROPS the protection ARGUMENT (the subtype),
    # and Gor Muldrak's own static is dropped entirely, so there is no structural form.
    # extract_signals_ir mirrors the _type_hoser_clause subtype-gated word detector over
    # the joined oracle (clause-safe). This _DETECTORS row is deleted; the clause helper
    # stays (the IR path reuses it); the serve stays hand-registered.
    ("spellcast_matters", lambda c: _IS_BUILDAROUND_RE.search(c) is not None, "you"),
    # ADR-0027 t2b4a-B: xspell_matters ({X}-spells payoff) migrated to the Card IR —
    # the `HasXInManaCost` predicate on a `cast_spell` trigger subject (Zaxara, Nev,
    # Zimone …) + a kept effect-raw word mirror (_XSPELL_HOOK_RE minus _XSPELL_VETO_RE)
    # for the predicate-dropped tail (Unbound Flourishing, Rosheen Meanderer). This
    # _DETECTORS row is deleted; the serve spec stays hand-registered. CR 202.1/107.3.
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
    # creatures_matter (the go-wide scaling lane) MIGRATED to the Card IR (ADR-0027):
    # its over-broad "creatures you control"/"for each creature you control" substring
    # producer is DELETED. The lane now fires from the structural IR — count/aggregate
    # operands over your generic creature board, team anthems (pump/grant/base-P/T),
    # mass keyword/evasion grants, mass untaps, and the token-maker cross-open — served
    # via extract_signals_hybrid (MIGRATED_KEYS). The substring producer over-fired on
    # subtype/color lords, single targets, attack/combat triggers, and cost taps; the
    # IR over-fire boundary (generic-set, no subtype) keeps those out. serve spec stays
    # in signal_specs.
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
    # ADR-0027: land_creatures_matter migrated to the Card IR — fired from the shared
    # land-animator predicate (animate/base_pt_set/type_set over a Land subject) +
    # Land+Creature dual-type anthem/maker subjects (Sylvan Advocate, Timber Protector,
    # Jyoti) + a kept oracle mirror (signals._IR_KEPT_DETECTORS) for the self-animate
    # manlands phase drops. This _DETECTORS producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
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
    # ADR-0027: vanilla_matters migrated to the Card IR — the HasNoAbilities
    # subject-Filter predicate (read in _predicate_build_around_lanes). The predicate
    # is its own discriminator (a card merely BEING vanilla never carries it), so the
    # IR drops the regex's lone incidental-mention over-fire (Rise from the Wreck — a
    # multi-target Mount/Vehicle recursion spell that enumerates "creature card with
    # no abilities" as one of four targets, not a vanilla build-around) and ADDS the
    # "Creatures you control with no abilities" anthem the contiguous regex missed
    # (Jasmine Boreal). This _DETECTORS producer is deleted; the serve spec
    # (serve_vanilla=True) stays hand-registered in signal_specs.
    # Force-attack incentive (Kratos): "creatures that didn't attack this turn" punishes
    # not attacking — a goad/aggro commander that wants everyone swinging.
    ("forced_attack", _re(r"didn't attack this turn|that attacked this turn"), "you"),
    # ADR-0027: goad_matters migrated to the Card IR — detected structurally from the
    # Scryfall `goad` keyword + phase's `goad_all` effect + a `_GOAD_REWARD_REF` face
    # marker (the "attacks one of your opponents" / "a player other than you" /
    # "whenever a player attacks" / defending-player reward conditions phase flattens
    # to raw, project._dropped_static_markers) + the goad-style single-target political
    # force ("target creature … attacks … if able" — phase's force_attack effect
    # lifted to goad via _GOAD_STYLE_FORCE). The two _DETECTORS / _HAND_FLOOR producers
    # are deleted; the hand-written serve spec (signal_specs.py) is independent.
    # ADR-0027: outlaw_matters migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: \boutlaws?\b; outlaw is a
    # creature-type GROUP phase doesn't model as one tag). Its broad _DETECTORS
    # producer is deleted; the hand-written serve spec (signal_specs.py) is
    # independent of this regex and survives.
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
    # ADR-0027: snow_matters migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: \bsnow\b; snow is a
    # supertype CR 205.4 phase doesn't surface as a payoff tag). Its _DETECTORS
    # producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_types=("snow",)) is independent of this regex and survives.
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
    # ADR-0027: the reanimator PAYOFF regex ("enters/cast FROM a graveyard") is deleted
    # with the reanimator migration. It CONFLATED the reanimator archetype (active
    # creature reanimation — a `reanimate` effect, the migrated IR bind) with the
    # escape/disturb/flashback "cast from a graveyard" engine, which is a SEPARATE
    # graveyard-recursion axis (CR 702.34 casting ≠ reanimation putting onto the
    # battlefield — rules-lawyer-verified). The structural IR correctly excludes the
    # cast-from-graveyard cards; the regex's 36 "enters/cast from a graveyard" payoff
    # cards (Prized Amalgam, River Kelpie, Flayer of the Hatebound — self-recursion /
    # escape, not the archetype) are the over-fire the migration drops.
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
    # ADR-0027: sacrifice_matters migrated to the Card IR — a you-sacrifice EFFECT
    # (scope not opp/each, a non-land subject, not a forced-opponent edict raw) + a
    # "sacrificed" trigger payoff + the Casualty keyword + the additional-cost /
    # granted / pitch / morph / pay-or-die / bullet sac markers (project.py). The
    # broad oracle regex over-fired on land-sac, edicts, "controller may sacrifice",
    # Ward—Sacrifice, and reanimation engines with no sacrifice. NOT in
    # _IR_FLOOR_LANES; this _DETECTORS producer is deleted; the serve spec stays
    # hand-registered. (CR 701.16.)
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
    # ADR-0027: counters_matter migrated to the Card IR — it fires on ANY +1/+1
    # counter PLACEMENT regardless of recipient (self / on-others / on-attacking /
    # distribute-among — all are sources, CR 122.1 / 122.6) and on a "has/with a
    # +1/+1 counter" PAYOFF reference. Sources: phase's place_counter(p1p1) +
    # counter_move(p1p1) + proliferate + the counter_added trigger + the count-form
    # payoff (amount.subject / e.subject with the Counters predicate) + the
    # counters_have_ref marker (project._narrow_counter_refs / _counter_face_marker
    # for the placement/payoff phase folds into a coin_flip / roll_die / vote / pay-
    # cost / distribute / trimmed-grant carrier or drops entirely) + the +1/+1
    # keyword block (mentor/training/modular/bolster/evolve/outlast/renown/adapt/
    # graft/riot/bloodthirst/fabricate/sunburst/tribute/unleash/ravenous/reinforce/
    # scavenge/undying/dethrone/devour — all structurally produce a place_counter or
    # carry the keyword). NOT in _IR_FLOOR_LANES (floor-mirror-dep == 0; floor-ON ==
    # floor-OFF). This _DETECTORS producer is deleted; the serve spec stays.
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
    # ADR-0027: lifeloss_matters migrated to the Card IR — a structured `lose_life`
    # Effect (scope you→you else opponents; the drain / self-loss split), a
    # `life_payment` marker + a paylife ACTIVATION COST buying a non-ramp engine (the
    # self life-as-resource half), a `life_lost` trigger payoff, and the project
    # _lifeloss_markers (pay-life additional cost / pitch / keyworded-cost /
    # cumulative-upkeep / tax / Defiler / granted / modal / dice / choose self-loss +
    # the modal / granted / lost-life-this-turn / dice drain). The broad regex
    # over-fired on pay-life MANA sources (painlands etc.), Ward—Pay life (the opponent
    # pays), and lifeGAIN-context. NOT in _IR_FLOOR_LANES; both _DETECTORS producers
    # are deleted; the serve specs stay hand-registered. (CR 119.3 / 118.)
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
    # ADR-0027: goad_matters migrated to the Card IR — this second goad producer (the
    # force-OTHER-creatures-to-attack form + the "whenever a player attacks" / Kazuul
    # defending-player reward) is deleted. The IR recovers all three structurally: the
    # single-target political force via _GOAD_STYLE_FORCE over phase's force_attack
    # effect; the reward conditions via the _GOAD_REWARD_REF face marker
    # (project._dropped_static_markers). Floor-mirror-dep == 0 (goad_matters is NOT in
    # _IR_FLOOR_LANES). The hand-written serve spec (signal_specs.py) survives.
    # A commander that rewards a creature whose "power [is] greater than its base power"
    # (Kutzil, Baird) is a pump / +1/+1-counters payoff — the only way a creature's
    # power exceeds its BASE power is a counter or a pump (CR 613.4c puts BOTH in
    # layer 7c). modified_matters fires for the pump/Aura/Equipment side; the
    # counters_matter twin is migrated to the Card IR (the "power greater than its
    # base power" anchor in project._P1P1_HAVE_FACE / signals._P1P1_HAVE_REF →
    # counters_have_ref, ADR-0027). That counters_matter _HAND_FLOOR producer is
    # deleted; modified_matters stays hand-floored.
    (
        "modified_matters",
        re.compile(r"power greater than its base power", re.IGNORECASE),
        "you",
    ),
    # ADR-0027: low_power_matters migrated to the Card IR — a non-dynamic
    # PtComparison:Power:LE/LT predicate on a you-controller Creature Filter, read by
    # _predicate_build_around_lanes (the recursion cards — Alesha, Reveillark — carry it
    # natively; phase DROPS it on the buff/etb subject shapes, recovered by a
    # `_LOW_POWER_REF` marker that rebuilds the Power:LE subject from "creatures you
    # control with power N or less" — Subira, Underfoot Underdogs). Removed from
    # _IR_FLOOR_LANES; serve stays hand-registered.
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
    # ADR-0027: celebration_matters migrated to the Card IR — detected from the
    # kept word-detector mirror (signals._IR_KEPT_DETECTORS: \bcelebration\b, the
    # WOE ability word CR 207.2c phase doesn't structure). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py) is
    # independent of this regex and survives.
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
    # ADR-0027: tapped_matters migrated to the Card IR — the Tapped(controller='you')
    # Filter predicate read in three slots: the effect subject (Saryth's grant), the
    # amount.subject COUNT (Throne of the God-Pharaoh / Dragonscale General), and the
    # threshold-gate condition.subject (Vaultguard Trooper, Sami Ship's Engineer), plus
    # a `_TAPPED_GRANT` dropped-static face marker for the subject phase strips (Masako
    # "tapped creatures you control can block") and the count predicate phase drops
    # (Harvest Season). Removed from _IR_FLOOR_LANES; serve stays hand-registered in
    # signal_specs.
    # Legends-matter: a commander that TUTORS legends (Captain Sisay "search your
    # library for a legendary card"), BUFFS them (Dihada "target legendary creature
    # gains"), counts/cost-reduces them, or triggers off them (Yomiji "whenever a
    # legendary permanent ... is put into a graveyard"). All want legendary bombs.
    # ADR-0027: legends_matter migrated to the Card IR — served from the
    # HasSupertype:Legendary subject-Filter predicate + a kept word mirror
    # (_IR_KEPT_DETECTORS) merging both _HAND_FLOOR rows for the cost-reduction /
    # target-legendary / cast-legendary / library-search refs phase leaves textual.
    # Moved floor->kept (floor-mirror-dep -> 0); both _HAND_FLOOR producers deleted.
    # ADR-0027: the "sac-and-return-this-turn engine" floor (Garna, Gerrard, Moira)
    # is DELETED with the sacrifice_matters migration — it over-fired on reanimation
    # engines that name no sacrifice at all (the IR path correctly drops them).
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
    # ADR-0027 tranche2-C: free_creature_payoff migrated to the Card IR — an ETB
    # trigger whose condition tree carries a manaspentcondition (Satoru the
    # Infiltrator), read structurally in extract_signals_ir. The deleted "no mana …
    # spent to cast" regex 100% over-fired on anti-free-spell PUNISHERS (Nix, Roiling
    # Vortex, Vexing Bauble, Lavinia, Boromir — counter/tax opponents' free spells) and
    # self-punish/self-bonus forms (Primeval Spawn, Freestrider Commando); the
    # etb-trigger gate correctly excludes all of them. The serve spec stays in
    # signal_specs (all_of(creature, mana_cost ^{0}$), independent of this regex).
    # ADR-0027: mass_death_payoff migrated to the Card IR — a `_MASS_DEATH_REF`
    # ("for each|number of … creature … died this turn") count-operand marker
    # (project._dropped_static_markers), keyed on the AGGREGATE board-wipe shape and
    # EXCLUDING the single-death conditional ("if a creature died this turn", morbid —
    # plain death_matters). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027 (t2b5-B): per_target_payoff migrated to the Card IR (kept_detector).
    # Hinata's YOUR-arm ("Spells you cast cost {1} less to cast for each target") has no
    # IR shape — the IR has no mana_cost / cost-reduction model and no per-spell target-
    # count operand, so the arm is DROPPED from the parse entirely. The IR path detects
    # it from a byte-identical _IR_KEPT_DETECTORS word mirror; this _HAND_FLOOR producer
    # is deleted; the hand-written serve spec (signal_specs.py, X-/multi-target spells)
    # is independent of this regex and survives.
    # Arcane tribal (The Unspeakable, the Kirins, Kodama — Kamigawa Spiritcraft): a
    # commander that cares about ARCANE spells ("cast a Spirit or Arcane spell", "return
    # target Arcane card") wants Arcane-subtype spells (CR 205.3k) + splice-onto-Arcane.
    ("arcane_matters", re.compile(r"\barcane\b", re.IGNORECASE), "you"),
    # ADR-0027: enlist_matters migrated to the Card IR — detected from the Scryfall
    # `enlist` keyword (signals._IR_KEYWORD_MAP, a structured-field lookup). This
    # _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_keywords=("enlist",)) is independent of this regex and survives.
    # ADR-0027: power_tap_engine migrated to the Card IR — an ACTIVATED ability whose
    # cost contains 'tap' plus a power-scaling effect raw (the structural arm in
    # extract_signals_ir's ability loop), plus an _IR_KEPT_DETECTORS mirror (byte-
    # identical to this deleted regex) for the conferred/quoted "{T}: … equal to its
    # power" grant phase folds into a grant carrier. This _HAND_FLOOR producer is
    # deleted; the hand-written serve spec (signal_specs.py, untap effects) survives.
    # ADR-0027: recast_etb migrated to the Card IR. DETECTOR (the bounce-replay
    # engine): the Scryfall `Sneak` keyword (_IR_KEYWORD_MAP, 28 cards — the TMNT/
    # Marvel ninjutsu-on-a-spell variant) drops the four `\bsneak\b`-regex over-fires
    # (Cheatyface "you may sneak", Lightfoot Rogue "Sneak Attack" ability word,
    # Fraternal Exaltation, empty-keyword Ninja Teen). Ninjutsu proper / "return an
    # unblocked attacker" is ALREADY ninjutsu_matters, so recast_etb keys on Sneak
    # specifically. SERVE (the aggressive-ETB payoff): an etb Trigger plus a
    # discard/lose_life/sacrifice effect whose raw names "each opponent" (the
    # aggressive enter-bleed the recast repeats — Liliana's Specter, Skirmish Rhino),
    # wired in the trigger loop of extract_signals_ir. This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: exert_matters migrated to the Card IR. The team-VIGILANCE enabler
    # (Heliod, Always Watching, Brave the Sands — team vigilance neutralizes exert's
    # only downside, "won't untap next turn") is served STRUCTURALLY from a
    # grant_keyword effect with counter_kind=='vigilance' over a generic-creature-you-
    # control subject (the exert arm in the grant_keyword block of extract_signals_ir;
    # _is_generic_creature_filter admits Heliod's `Another` / Always Watching's
    # `NonToken` predicate but excludes the subtype-scoped Golem/Sliver/Warrior grants
    # and the single-target Kytheon's Tactics). The Johan namesake — "attacking
    # doesn't cause creatures you control to tap" — projects to a restriction whose
    # clause survives only in raw, so it is served by a kept word mirror
    # (_IR_KEPT_DETECTORS). This _HAND_FLOOR producer is deleted; the serve spec
    # (signal_specs.py, serve_keywords=("exert",)) stays hand-registered.
    # ADR-0027 t2b4-C: tap_down_blockers ("Can't be blocked unless ALL block" —
    # Tromokratis) migrated to the Card IR (kept_detector). phase DROPS the conditional-
    # evasion clause entirely (only the hexproof grant survives), so there is no
    # structural shape to read — the literal phrase is the only signal. It fires from an
    # _IR_KEPT_DETECTORS word mirror (the exact regex). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
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
    # ADR-0027: land_protection migrated to the Card IR — fired from the shared
    # land-animator predicate (animate/base_pt_set/type_set over a you/any Land subject)
    # + a kept oracle mirror (signals._IR_KEPT_DETECTORS) for the self-animate manlands
    # phase drops. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: lose_unless_hand migrated to the Card IR — an ETB trigger scoped to YOU
    # whose consequence is a lose_game effect (Phage the Untouchable; the etb +
    # scope=you + lose_game shape is structurally unique, in extract_signals_ir's
    # trigger loop). This _HAND_FLOOR producer is deleted; the hand-written serve spec
    # (signal_specs.py, drawback negation) survives.
    # ADR-0027: land_denial migrated to the Card IR — fired structurally from a
    # `phasing` Effect on a Land subject with controller=='you' (Taniwha). This
    # _HAND_FLOOR producer is deleted; the serve spec (the LD-punisher serve) stays
    # hand-registered in signal_specs.py and is unaffected.
    # ADR-0027: aoe_ping migrated to the Card IR — a REPEATABLE "damage to each
    # creature" board ping (Tibor, Pestilence, Pyrohemia) is structurally an Effect
    # (category=='damage', counter_kind=='all', Creature subject) carried by a
    # REPEATABLE-FRAME ability: an activated ability whose cost has 'tap'/'mana' but
    # NOT 'sacself'/'sacrifice' (the {T}: gate the cost field now supplies), OR a
    # triggered ability on upkeep/end_step/cast_spell (extract_signals_ir, per-ability
    # loop). A one-shot ETB sweep (Chaos Maw, event='etb') or sac-self pinger
    # (Bloodfire Colossus, cost='mana,sacself') can't be suited up before it fires, so
    # both are excluded. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py (deathtouch on the source so each ping kills).
    # ADR-0027: nonhuman_attackers migrated to the Card IR — detected structurally
    # from an attacks-trigger whose subject Filter carries NotSubtype:Human and a
    # "you"-controller (the dedicated branch in extract_signals_ir). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py, fliers that
    # connect) is independent of this regex and survives.
    # ADR-0027 (t2b2-A): control_exchange migrated to the Card IR — an `exile` Effect
    # whose subject carries the `Owned` predicate ("creature/permanent you OWN"), PAIRED
    # with a to:battlefield return in the same ability (Meneldor, The Neutrinos,
    # Aminatou). The inverse of the exile_removal Owned-exclusion. This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py, "Control
    # swaps") is independent of this regex and survives.
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
    # ADR-0027 t2b5-A: free_plot migrated to the Card IR — Fblthp makes the top card's
    # plot cost = its mana cost (the cEDH artifact-combo / storm engine), but no IR
    # structure exists for the Plot alt-cost rewrite (phase routes the clause to a
    # subjectless topdeck_select). The lane fires from a signals._IR_KEPT_DETECTORS word
    # mirror (the exact "plot cost is equal to its mana cost" phrase — literally unique
    # to one card, zero over-fire). This _HAND_FLOOR producer is deleted; the serve spec
    # (the 0-cost-cards serve) stays hand-registered in signal_specs.py.
    # ADR-0027: multicolor_matters migrated to the Card IR — served from the
    # multicolor ColorCount subject-Filter predicate (the "multicolored <permanent> you
    # control" / "multicolored card" build-arounds — Niv-Mizzet Reborn, Rienne) + a
    # _IR_KEPT_DETECTORS word mirror for the "cast a multicolored spell" trigger / "for
    # each color pair" refs that aren't a structured subject. This _HAND_FLOOR producer
    # is deleted; the serve spec stays hand-registered.
    # ADR-0027 (t2b5-B): target_own_payoff migrated to the Card IR (kept_detector).
    # Monk Gyatso's becomes-target may-reaction on YOUR creatures: phase parses the
    # becomes-target trigger as event='other' (no becomestarget trigger mode), so the
    # may-clause + own-creature restriction survive only in raw. The IR path detects it
    # from a byte-identical _IR_KEPT_DETECTORS word mirror; this _HAND_FLOOR producer is
    # deleted; the hand-written serve spec (signal_specs.py, en-Kor / {0}-equip
    # enablers) is independent of this regex and survives.
    # ADR-0027: life_payment_insurance migrated to the Card IR — a repeatable "Pay N
    # life:" ACTIVATION COST ("paylife" in Ability.cost; Selenia, Beledros, the
    # fetchlands — genuine recall the narrow regex missed) + a `life_payment` marker for
    # the misparsed cost (Arco-Flagellant, Hibernation Sliver) and the conferred quoted
    # "…Pay 1 life: Draw" ability phase drops (Underworld Connections, the volvers).
    # NOT in _IR_FLOOR_LANES; serve stays hand-registered. (CR 118.)
    # ADR-0027: land_exchange migrated to the Card IR — phase's `gain_control` effect
    # over a Land subject, plus a raw fallback (_LAND_EXCHANGE_RAW) for the "exchange
    # control of target X and target Y" shape phase parses with subject=None (Political
    # Trickery, Vedalken Plotter, Gauntlets of Chaos). NOT in _IR_FLOOR_LANES; the
    # serve spec stays hand-registered in signal_specs. The deleted regex's other
    # alternation ("activated abilities of lands … opponents control") only over-fired
    # on Sharkey (copies/taxes land abilities, never exchanges control — it emits NO
    # gain_control effect, so the structural IR correctly drops it).
    # ADR-0027: scavenge_fuel migrated to the Card IR — the Scryfall `scavenge`
    # keyword (_IR_KEYWORD_MAP, the intrinsic scavengers) plus a `scavenge`
    # dropped-static face marker for the graveyard-wide GRANTERS phase drops ("Each
    # creature card in your graveyard has scavenge" — Varolz, Young Deathclaws, The
    # Cave of Skulls, project._dropped_static_markers, read via _DOER_EFFECT_KEYS).
    # The "\bscavenge\b" floor over-fired on the "Scavenge the Dead" ability WORD
    # (CR 207.2c — Malanthrope), which the structural IR correctly excludes. This
    # _HAND_FLOOR producer is deleted; the serve spec stays in signal_specs.
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
    # ADR-0027 (t2b5-B): target_redirect migrated to the Card IR (kept_detector).
    # Rayne's becomes-target-of-opponent → draw payoff: phase flattens the becomes-
    # target trigger to event='other' (no becomestarget mode), so DETECTION (which
    # commanders open the lane) survives only in raw. The IR path detects it from a
    # byte-identical _IR_KEPT_DETECTORS word mirror; this _HAND_FLOOR producer is
    # deleted. The hand-written serve spec (signal_specs.py, redirect spells) is
    # independent of this regex and survives — the redirect SERVE pool is itself
    # structural via category=='redirect' should anyone tighten it later.
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
    # ADR-0027: treasure_matters migrated to the Card IR — detected structurally like
    # blood_matters: a Treasure-subtype make_token maker (incl. the die-roll/vote/choice
    # branch + Aftermath-DFC recovery), a "Sacrifice a Treasure" SAC PAYOFF, and a
    # `token_subtype_ref` "Treasures you control" / "was a Treasure" cares-about marker
    # (project._narrow_token_subtype_makers + _dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; floor-mirror-dep == 0. The structural IR is broader-and-correct
    # recall (the make_token-SUBJECT Treasure makers the "create … treasure token" regex
    # missed — Old Gnawbone, Prismari Command, Wanted Scoundrels). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec survives.
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
    # ADR-0027: lands_matter migrated to the Card IR — served from the
    # amount.subject=Land count operand (the structured scalers) + a kept word mirror
    # (_IR_KEPT_DETECTORS) for the "P/T equal to the number of lands you control" and
    # "for each land you control" forms phase emits as characteristic_pt/pump_target
    # but DROPS the count operand. Moved floor->kept (floor-mirror-dep -> 0); this
    # _HAND_FLOOR producer is deleted.
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
    # ADR-0027: scry_surveil_matters migrated to the Card IR — the scried/surveiled
    # trigger events (_PAYOFF_TRIGGER_KEYS) + phase's `scry_surveil` effect category
    # (the event='other' "whenever you scry/surveil" payoff trigger,
    # _narrow_trigger_other_refs) plus a `scry_surveil` dropped-static face marker
    # for the "if you would scry a number of cards … instead" REPLACEMENT phase drops
    # entirely (Kenessos, Eligeth — project._dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; this _HAND_FLOOR producer is deleted; the serve spec stays.
    # ── Named-mechanic long tail (precise named anchors → novel build-arounds) ───
    # ADR-0027: monarch_matters migrated to the Card IR — served structurally from
    # phase's `monarch` effect category (_DOER_EFFECT_KEYS, "you become the monarch"
    # grants narrowed in project._narrow_mechanic_refs) AND the Condition(ismonarch)
    # gate lifted in extract_signals_ir. Its oracle-regex floor detector is deleted;
    # the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: initiative_matters migrated to the Card IR — served from a
    # "\bthe initiative\b" _IR_KEPT_DETECTORS word mirror (phase v0.1.19 doesn't
    # structure the CR 720 initiative designation). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: ring_matters migrated to the Card IR — served structurally from
    # phase's `ring_tempt` effect category (_DOER_EFFECT_KEYS). A "Whenever the Ring
    # tempts you" trigger (CR 701.54) phase flattened to event='other', and a
    # "Ring-bearer" reference buried in any effect raw (Sauron — no tempt trigger),
    # are appended as `ring_tempt` marker effects by
    # project._narrow_trigger_other_refs. Its oracle-regex floor detector is deleted
    # and it is removed from _IR_FLOOR_LANES; the serve spec stays hand-registered.
    # ADR-0027: venture_matters migrated to the Card IR — phase's venture/take-the-
    # initiative effect category (_DOER_EFFECT_KEYS) + a condition-kind read
    # (completedadungeon / isinitiative — Gloom Stalker, Imoen, Safana) + a
    # trigger_doubling-over-dungeons read (Hama Pashar, Dungeon Delver) + a
    # `_VENTURE_REF` dropped-clause marker (You Find a Cursed Idol, Fly, Dungeon
    # Crawler). Removed from _IR_FLOOR_LANES; serve stays hand-registered. (CR 701.46.)
    # ADR-0027: energy_matters migrated to the Card IR — phase's `energy` effect
    # category (_DOER_EFFECT_KEYS, the gainenergy producers) + an `_ENERGY_REF` ({e})
    # marker for the SINKS / "whenever you get {E}" payoffs / doublers phase loses.
    # Removed from _IR_FLOOR_LANES; serve stays hand-registered. (CR 122.1.)
    # ADR-0027: devotion_matters migrated to the Card IR — served from the
    # amount.op=="devotion" count operand (the scaling payoffs) + a "devotion to
    # <color>" _IR_KEPT_DETECTORS word mirror for the cost-reduction / counterspell-tax
    # / mana forms phase doesn't make a count operand. This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
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
    # ADR-0027: historic_matters migrated to the Card IR — served from the "Historic"
    # subject-Filter predicate + a "\bhistoric\b" _IR_KEPT_DETECTORS word mirror for the
    # cost-reduction / "play a historic" / type-group refs phase leaves textual
    # (artifacts, legendaries, and Sagas are historic). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: legends_matter migrated to the Card IR (see the merged
    # _IR_KEPT_DETECTORS mirror). This second _HAND_FLOOR producer is deleted too.
    (
        "big_hand_matters",
        re.compile(
            r"no maximum hand size|maximum hand size"
            r"|(?:five|six|seven|eight) or more cards in your hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027: party_matters migrated to the Card IR — served from the
    # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
    # "full party" CONDITION + "creatures in your party" non-count refs. This
    # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered.
    (
        "exile_matters",
        re.compile(
            r"cards? (?:you own )?(?:that are )?in exile"
            r"|for each card (?:you own )?(?:in )?exile",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027: experience_matters migrated to the Card IR — the GivePlayerCounter
    # ->experience_counter gainers (_DOER_EFFECT_KEYS) plus the experience SCALER
    # operand (op="experience" from a Ref->PlayerCounter{Experience}, project
    # ._quantity) for Atreus/Azula. This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec stays in signal_specs.
    # ADR-0027: poison_matters migrated to the Card IR — served from the
    # infect/toxic/poisonous Scryfall keywords (the bearers, _IR_KEYWORD_MAP) + a kept
    # word mirror (_IR_KEPT_DETECTORS) for the GRANTERS ("gains infect", "has
    # poisonous 1") and "poison counter" / "has toxic" references phase folds into a
    # grant carrier's raw. Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
    ("modified_matters", re.compile(r"\bmodified\b", re.IGNORECASE), "you"),
    # ADR-0027: mutate_matters migrated to the Card IR — the Scryfall `mutate`
    # keyword (_IR_KEYWORD_MAP, the 34 mutate creatures) plus a `mutate` payoff
    # marker for the keyword-less cast-payoff ("if it has mutate" —
    # project._narrow_payoff_condition_refs, read via _DOER_EFFECT_KEYS; Pollywog
    # Symbiote). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: food_matters migrated to the Card IR — detected structurally like
    # blood_matters: a Food-subtype make_token maker (incl. the die-roll/vote/choice
    # branch + Aftermath-DFC recovery), a "Sacrifice a Food" SAC PAYOFF, and a
    # `token_subtype_ref` "Foods you control" / "is a Food" cares-about marker
    # (project._narrow_token_subtype_makers + _dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; floor-mirror-dep == 0. This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec survives.
    ("clue_matters", re.compile(r"\bclue\b|\binvestigate\b", re.IGNORECASE), "you"),
    # ADR-0027: blood_matters migrated to the Card IR — detected structurally from a
    # Blood-subtype maker (make_token subject), a Blood SACRIFICE PAYOFF (a sacrifice
    # Effect/Trigger whose subject Filter carries the Blood subtype — Wedding
    # Security, Blood Hypnotist), and the choose-list / granted-ability maker
    # recovery (Transmutation Font, Ceremonial Knife — project._narrow_token_subtype_
    # makers). It is removed from _IR_FLOOR_LANES (no floor mirror; floor-mirror-
    # dependency == 0). This _HAND_FLOOR producer is deleted; the hand-written serve
    # spec (signal_specs.py) survives. clue/food/treasure keep their floor for now.
    (
        "daynight_matters",
        re.compile(
            r"\bdaybound\b|\bnightbound\b|it becomes night"
            r"|day becomes night|night becomes day|as long as it's (?:day|night)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027: voting_matters migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: a broader vote regex that
    # also catches the plural + "each player votes"; voting CR 701.38 is a real
    # mechanic phase only partially structures). This _HAND_FLOOR producer is
    # deleted; the hand-written serve spec (signal_specs.py) survives.
    # ADR-0027: token_doubling migrated to the Card IR — detected structurally from
    # the token-doubling replacement effect (the `cat == "token_doubling"` branch in
    # extract_signals_ir). This _HAND_FLOOR producer is deleted; the hand-written
    # serve spec (signal_specs.py) survives. Token- and counter-doubling stay
    # separate lanes (a token doubler wants token makers; a counter doubler wants
    # counter sources) — counter_doubling keeps its own regex below.
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
    # ADR-0027: opponent_cast_matters migrated to the Card IR — the structural
    # cast_spell-trigger scope=opp arm (Lavinia, Nekusar) plus an _IR_KEPT_DETECTORS
    # mirror that DROPS this regex's over-broad bare "whenever a player casts a spell"
    # arm (the IR is more precise — symmetric-benefit / self-drawback over-fires are
    # excluded) and keeps only the explicit-opponent + symmetric-PUNISH ("that player"
    # anchor) branches. This _HAND_FLOOR producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: opponent_draw_matters migrated to the Card IR — detected
    # structurally from a "drawn" trigger event whose subject scope is an opponent
    # (the `ev == "drawn"` + `trig.scope == "opp"` branch in extract_signals_ir).
    # This _HAND_FLOOR producer is deleted; the hand-written serve spec
    # (signal_specs.py) is independent of this regex and survives.
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
    # ADR-0027: specialize_matters migrated to the Card IR (served structurally
    # from the Scryfall `specialize` keyword — _IR_KEYWORD_MAP['specialize']
    # below); both its oracle-regex sources (this _HAND_FLOOR detector and the
    # SWEEP_DETECTORS row) are deleted. The keyword survivor is the IR backing.
    # Villainous choice (AFR/WHO/Marvel): a commander built around making opponents face
    # villainous choices (The Valeyard doubles them; Davros/Missy/Dr. Eggman present
    # them) wants the villainous-choice card pool. A named mechanic, so a self-contained
    # open==serve lane like venture / specialize.
    ("villainous_choice", re.compile(r"villainous choice", re.IGNORECASE), "you"),
    # ADR-0027 t2b4a-B: curse_matters (Aura — Curse cares-about) migrated to the Card
    # IR — a trigger/effect subject Filter with subtypes=='Curse' (Lynde, Bitterheart
    # Witch, Witchbane Orb) + a kept word mirror (_IR_KEPT_DETECTORS, byte-identical to
    # this deleted regex) for the under-parsed "search for a Curse card …" tail (Curse
    # of Misfortunes). The membership half (a card that IS a Curse) stays REGEX-ONLY at
    # A4 like TYPE_MATTERS membership. This _HAND_FLOOR producer is deleted; the serve
    # spec stays hand-registered. CR 205.3 / 702.39.
    # ADR-0027: dice_matters migrated to the Card IR — phase's native `roll_die` effect
    # + a `roll_die` marker (project._narrow_trigger_other_refs for the "whenever you
    # roll" payoff trigger + _dropped_static_markers for the "Roll two d6 and choose"
    # spell / "Roll a d8:" cost / "reroll" forms phase keeps only in raw). The
    # structural IR is broader-and-correct recall ("rolls a d20", "Roll X dice", "Roll
    # the planar die", "20-sided die" — Chaos Dragon, Clown Car, Fractured Powerstone,
    # "Name Sticker" Goblin), not over-fire. This _HAND_FLOOR producer is deleted (the
    # SWEEP_DETECTORS row too); the serve spec stays. (CR 706.)
    # ADR-0027: crimes_matter migrated to the Card IR — phase's commit_crime trigger
    # event (_PAYOFF_TRIGGER_KEYS, the "Whenever you commit a crime" trigger form) + a
    # `_CRIME_REF`/`crime` marker for the condition-form payoff phase has no condition
    # kind for ("(if|as long as) you've committed a crime this turn" — Oko, Nimble
    # Brigand, Slickshot Vault-Buster, the Outlaws cost-reducers). Removed from
    # _IR_FLOOR_LANES; serve stays hand-registered. (CR 701.49.)
    # ADR-0027: connive_matters migrated to the Card IR — phase's `connive` effect
    # category (self-conniving cards, _DOER_EFFECT_KEYS) + the `_CONNIVE_REF`
    # applied/granted marker, plus the Scryfall `connive` keyword (_IR_KEYWORD_MAP)
    # which lifts the keyword-less GRANTER phase swallows into an Enchant parse
    # (Security Bypass). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: spell_copy_matters migrated to the Card IR — phase's `spell_copy`
    # effect (CopySpell + CastCopyOfCard) + the storm/replicate/conspire/casualty
    # Scryfall keywords (the HAVERS, _IR_KEYWORD_MAP) + a `_COPY_SPELL_REF` marker for
    # the granted/quoted/conditional copy phase folds into a modal / coin-flip / storm-
    # reminder carrier and the keyword-less GRANTERS ("…spell you cast has replicate/
    # casualty/storm/demonstrate"). The IR EXCLUDES the deleted regex's `\bstorm\b`
    # card-NAME over-fire (Comet Storm, Arrow Storm — burn, not the keyword). Both
    # regex producers (this _HAND_FLOOR + the SWEEP row) are deleted; the serve spec
    # stays hand-registered.
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
    # ADR-0027: removal_matters migrated to the Card IR — phase's `destroy` / `damage`
    # effect categories with a single-target permanent SUBJECT (CR 115.1), plus the
    # quoted-grant-ability recursion (an Aura/Equipment granting "{T}: Destroy/deal
    # damage to target …" — Manriki-Gusari, Lavamancer's Skill) and the
    # removal-target-subject recovery (Combo Attack, Broken Visage). The mass form
    # ("destroy/deal damage to EACH/ALL …" — DamageAll/DestroyAll, counter_kind=="all")
    # is a BOARD WIPE (CR 115.10), correctly EXCLUDED here and served by mass_removal;
    # the regex over-fired by folding board wipes / land destruction into removal. NOT
    # in _IR_FLOOR_LANES (floor-mirror-dep == 0); this _HAND_FLOOR producer is deleted
    # and the SWEEP_DETECTORS removal_matters row with it; serve stays hand-registered.
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
    # ADR-0027: counter_control migrated to the Card IR — phase's `counter_spell`
    # effect category plus a `counter_spell` dropped-static face marker for the
    # "counter target … spell/ability" phase loses in a modal mode body (Fangkeeper's
    # Familiar, Ertai Resurrected), a granted/quoted Aura ability (Equinox, Sunken
    # Field), or a non-grant carrier (Goblin Artisans). NOT in _IR_FLOOR_LANES; the
    # serve spec stays hand-registered in signal_specs (FP-free at this breadth).
    # ADR-0027: team_buff migrated to the Card IR — phase's `grant_keyword` Effect (one
    # per granted keyword, the keyword in counter_kind) on a GENERIC "creatures you
    # control" subject (_is_team_buff_grant + _TEAM_BUFF_GRANT_KW). The structural IR
    # drops the regex's tribal / color / attacking / single-target over-fires (it
    # matched the "creatures you control have <kw>" mass_grant roll-up text even when
    # the real grant was tribal/color-scoped); 0 genuine generic anthems lost. NOT in
    # _IR_FLOOR_LANES; this _HAND_FLOOR producer + the SWEEP_DETECTORS team_buff row
    # are deleted; the serve spec stays hand-registered.
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
    # ADR-0027: permanent_etb migrated to the Card IR — an `etb` Trigger whose subject
    # Filter carries the 'Permanent' card_type and controller=='you' (Amareth, the
    # canonical card). The structural IR is BROADER-and-correct: it catches the
    # "a/another permanent you control enters" variants the narrow word-order regex
    # missed (Cloudstone Curio, Kodama, Yoshimaru, Builder's Talent). NOT in
    # _IR_FLOOR_LANES; this _HAND_FLOOR producer is deleted; the serve spec stays.
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
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR — a first-class `bounce`
    # Effect with no graveyard zone tag and a subject not controlled by you (excludes
    # GY-recursion and self-bounce blink). This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec (signal_specs.py, "Bounce / tempo") is independent of this
    # regex and survives.
    # ADR-0027: cascade_matters migrated to the Card IR — the Scryfall `cascade`
    # keyword (_IR_KEYWORD_MAP, the intrinsic cascaders) + a `_CASCADE_GRANT` marker for
    # the keyword-less granters/references ("spells you cast have cascade", "as you
    # cascade", "spell with cascade"). Removed from _IR_FLOOR_LANES; serve hand-spec'd.
    # ADR-0027: regenerate_matters migrated to the Card IR — phase's `regenerate` effect
    # (_DOER_EFFECT_KEYS) + a `_REGENERATE_REF` marker for the granted/quoted/replace
    # regenerate phase drops (Tribal Golem, Mossbridge Troll). Removed from
    # _IR_FLOOR_LANES; serve hand-spec'd.
    # ── Keyword-coverage audit (CR 702/701) keyword[]-anchored avenues ──────────
    # Each fires on a commander/card that bears or cares about the keyword; the matching
    # SPECS entry serves the keyword[] bearers (authoritative) plus the payoff phrasing.
    # Madness (CR 702.35): discard to cast — discard_matters covers only 1/61.
    # ADR-0027: madness_matters migrated to the Card IR — the Scryfall `madness`
    # keyword (_IR_KEYWORD_MAP) + the `_MADNESS_GRANT` "has madness" conferral
    # marker, plus a `madness` payoff marker for the "if it has madness" condition
    # (project._narrow_payoff_condition_refs; Anje Falkenrath's untap loop). Removed
    # from _IR_FLOOR_LANES. The "\bmadness\b" floor over-fired on the "Crown of
    # Madness" ability WORD (CR 207.2c — Bloodboil Sorcerer), which the structural IR
    # correctly excludes. This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: speed_matters migrated to the Card IR — phase's `speed` doer +
    # a "start your engines|max speed|your speed" _IR_KEPT_DETECTORS word mirror (phase
    # v0.1.19 doesn't structure the CR 702.178/702.179 Speed designation; Aetherdrift).
    # Moved floor->kept (floor-mirror-dep -> 0); this _HAND_FLOOR producer is deleted;
    # the serve spec stays hand-registered.
    # ADR-0027: discover_matters migrated to the Card IR — served structurally from
    # the Scryfall `discover` keyword (_IR_KEYWORD_MAP, the discover SOURCES) plus a
    # `discover` effect category for the keyword-less re-trigger payoff (Curator of
    # Sun's Creation: "Whenever you discover, discover again" — a trigger phase
    # flattened to event='other', appended by project._narrow_trigger_other_refs and
    # read via _DOER_EFFECT_KEYS). Its oracle-regex floor detector is deleted; the
    # serve spec stays hand-registered in signal_specs.py.
    # Foretell (CR 702.143): the foretold-card payoff/engine axis (Alrund, Ranar).
    # ADR-0027: foretell_matters migrated to the Card IR — the Scryfall `foretell`
    # keyword (_IR_KEYWORD_MAP) + the `_FORETELL_REF` "has foretell"/"you foretell"
    # marker, plus the Foretold-predicate payoff bind (Niko Defies Destiny — a
    # counted subject Filter carrying the Foretold predicate) and a `foretell`
    # marker for the "to foretell" mana ENABLER (Karfell Harbinger,
    # project._narrow_payoff_condition_refs). Removed from _IR_FLOOR_LANES. This
    # _HAND_FLOOR producer is deleted; the serve spec stays in signal_specs.
    # ADR-0027: undying_persist_matters migrated to the Card IR — the Scryfall
    # `undying`/`persist` keywords (_IR_KEYWORD_MAP, the intrinsic bearers) + a
    # `_UNDYING_PERSIST_GRANT` marker for the keyword-less GRANTERS ("creatures you
    # control have undying" — Mikaeus, "gains persist until end of turn" — the persist-
    # granters). Removed from _IR_FLOOR_LANES; the "\bundying\b" floor over-fired on the
    # "Undying Flames" card NAME (Epic damage, no undying mechanic), which the
    # structural IR correctly drops. This _HAND_FLOOR producer is deleted; the serve
    # hand-spec stays. (dies_recursion still includes the undying/persist keywords.)
    # ADR-0027: minus_counters_matter migrated to the Card IR — phase's place_counter
    # (counter_kind='m1m1') is the maker (via _COUNTER_KIND_KEYS); the "-1/-1 counter"
    # references (remove / cost / ward / "with a -1/-1 counter on it" / prevention) are
    # the cares-about payoffs phase leaves textual, served from a "-1/-1 counter"
    # _IR_KEPT_DETECTORS word mirror (CR 122 / 702.80 Wither / 702.90 Infect). This
    # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered.
    # ADR-0027: the any-counter HAVE form of counters_matter ("permanents/creatures
    # you control with a counter on it" — Xolatoyac, Hidden Hideout, Michelangelo —
    # and "for each <permanent/creature> you control with a counter") migrated to the
    # Card IR: the counters_have_ref marker (project._narrow_counter_refs /
    # _counter_face_marker, "with a counter(s) on it/them" + "+1/+1 counter on
    # creatures you control" anchors) and the count-form payoff (amount.subject with
    # the Counters predicate). This _HAND_FLOOR producer is deleted; the serve spec
    # stays hand-registered.
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
    # ADR-0027: cycling_matters migrated to the Card IR — phase's `cycled` trigger +
    # a `cycling_payoff` marker (project._narrow_trigger_other_refs for the "cycle or
    # discard" payoff phase flattens to event='other', + _dropped_static_markers for
    # the cards phase truncates the trigger phrase off entirely). The `cycling_payoff`
    # category is DISTINCT from phase's native `cycling` landcycling doer, so the lane
    # stays payoff-only. This _HAND_FLOOR producer is deleted; the serve spec stays.
    # Kicker (CR 702.33): "cast a kicked spell" payoffs; spellcast_matters serves 0/10.
    (
        "kicked_spell_matters",
        re.compile(
            r"whenever you cast a kicked spell|if (?:that|it) (?:spell )?was kicked",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027: colorless_matters migrated to the Card IR — served from the
    # ColorCount:EQ:0 subject-Filter predicate (the "colorless <permanent> you
    # control" / "colorless card" build-arounds — Ancient Stirrings, Vile Aggregate) + a
    # "colorless (creature|spell|permanent)" _IR_KEPT_DETECTORS word mirror for the
    # cost-reduction / cast-restriction refs that aren't a structured subject (CR
    # 702.114). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: exalted_lone_attacker migrated to the Card IR — the Scryfall `exalted`
    # keyword (_IR_KEYWORD_MAP, the bearers) + an "attacks alone|\bexalted\b"
    # _IR_KEPT_DETECTORS word mirror for the attacks-alone payoff triggers + "X have
    # exalted" grants phase leaves textual (CR 702.83). Moved floor->kept (floor-mirror-
    # dep -> 0); this _HAND_FLOOR producer is deleted; the serve spec stays.
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
    # ADR-0027: team_evasion_grant migrated to the Card IR — phase's grant_keyword on a
    # generic creatures-you-control subject (the structural team grant) + a kept word
    # mirror for the subtype/color-scoped grants ("Sliver creatures you control have
    # flying", "Blue creatures you control can't be blocked") the narrow generic gate
    # excludes (CR 702.13/702.14/509). This _HAND_FLOOR producer is deleted; the serve
    # spec stays hand-registered.
    # ADR-0027: lessons_matter migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: \blessons?\b; Lesson is a
    # subtype CR 702.x phase doesn't surface as a payoff tag). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_types=("lesson",)) is independent of this regex and survives.
    # ADR-0027: suspend_matters migrated to the Card IR — served from the Scryfall
    # `suspend` keyword (the bearers, _IR_KEYWORD_MAP) + a kept word mirror
    # (_IR_KEPT_DETECTORS) folding in the SWEEP \bsuspend\b and widening to the whole
    # time-counter superstructure (CR 701.56 time travel, 702.63 Vanishing, Impending,
    # and the cross-pool enablers/payoffs As Foretold, Jhoira, Dust of Moments that
    # manipulate time counters without bearing Suspend). Moved floor->kept (floor-
    # mirror-dep -> 0); this _HAND_FLOOR producer + the SWEEP \bsuspend\b row deleted.
    # ADR-0027: the Casualty (CR 702.153) sacrifice_matters regex is DELETED with the
    # migration — the printed Casualty keyword now routes via _IR_KEYWORD_MAP and the
    # keyword-LESS granter (Anhelo "has casualty N") via a project grant marker.
    # ADR-0027: saddle_matters migrated to the Card IR — served structurally from
    # phase's `saddle` effect category (_DOER_EFFECT_KEYS; a "becomes saddled" /
    # "you saddle" grant phase folds into an animate/restriction/target_only carrier
    # is appended as a `saddle` marker in project._narrow_mechanic_refs) and the
    # Scryfall `saddle` keyword (_DIRECT_KEYWORD_SIGNALS, a structured field that
    # survives). Its oracle-regex floor detector is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027: suspect_matters migrated to the Card IR — phase's `suspect` effect
    # category (_DOER_EFFECT_KEYS, the leading-imperative suspect verb) + a
    # `_SUSPECT_REF` marker for the verb buried mid-clause / in a granted ability and
    # the "suspected" adjective form phase loses (the marker's "(?! counter)" excludes
    # Investigator's Journal's "suspect counter" — a same-named COUNTER type, not the
    # designation, CR 701.60b). Removed from _IR_FLOOR_LANES; serve hand-registered.
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
    # ADR-0027: the +1/+1-counter keyword block (mentor/training/modular/bolster/
    # evolve/outlast/renown/adapt — and dethrone/undying/graft/riot/bloodthirst/
    # fabricate/sunburst/tribute/unleash/ravenous/reinforce/scavenge below) removed
    # from the regex keyword path with the counters_matter migration — every one of
    # their keyword cards already fires counters_matter STRUCTURALLY from the IR (each
    # keyword projects a place_counter via phase's effect mapping), verified 0-miss
    # over the commander-legal corpus. The regex `extract_signals` must no longer emit
    # the migrated key.
    "battle cry": ("attack_matters", "you"),
    "battalion": ("attack_matters", "you"),
    "melee": ("attack_matters", "you"),
    "exalted": ("voltron_matters", "you"),
    # ADR-0027: extort / afflict / spectacle (→ lifeloss_matters) removed from the
    # regex keyword path with the lifeloss_matters migration — all their keyword cards
    # already fire lifeloss_matters STRUCTURALLY from the IR (extort's lose_life
    # effect, afflict's "player loses life", spectacle's "opponent lost life"), so the
    # regex `extract_signals` must no longer emit the migrated key.
    "amass": ("tokens_matter", "you"),
    "mobilize": ("tokens_matter", "you"),
    # Station (702.184) accrues charge counters → route to the proliferate avenue (which
    # already serves charge-counter cards); station commanders fire no +1/+1 counter
    # signal otherwise.
    "station": ("proliferate_matters", "you"),
    # ADR-0027: the `saddle` keyword (CR 702.171) moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because saddle_matters is migrated — keeping it here
    # would let the regex `extract_signals` path keep emitting a migrated key.
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
    # afflict / spectacle (→ lifeloss_matters) removed for the ADR-0027 migration —
    # see the note at the top of this map; the IR covers their keyword cards. The
    # +1/+1-counter keyword block (dethrone/undying/graft/riot/bloodthirst/fabricate/
    # sunburst/tribute/unleash/ravenous/reinforce/scavenge) is likewise removed for
    # the counters_matter migration — the IR fires counters_matter on all of them
    # structurally (see the note at the top of this map).
    # Persist returns with a -1/-1 counter (CR 702.79a), so it wants the -1/-1 serve
    # set, not the +1/+1-centric counters_matter — it stays (minus_counters_matter is
    # NOT migrated via this keyword path).
    "persist": ("minus_counters_matter", "you"),
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
# ADR-0027 tranche2-A: a GO-WIDE-GATE mirror for the migrated anthem_static key. Its
# regex producer is deleted, so it no longer rides the ``out`` set the CLASS_TRIBES
# go_wide gate reads (an anthem lord is a go-wide commander, so its own class type
# becomes a build-around — CR 205.3). Mirror the deleted anthem regex so the regex-path
# go_wide gate still recognizes a static team-buff; it only feeds the gate (it emits no
# signal — anthem_static itself is served from the IR). The IR path's go_wide gate sees
# the real anthem_static signal, so this keeps the two paths' type_matters in parity.
_ANTHEM_GO_WIDE_MIRROR = re.compile(
    r"(?:other [a-z]+ creatures|creatures you control|[a-z]+ creatures you control"
    r"|nonblack creatures|other creatures) get \+\d/\+\d",
    re.IGNORECASE,
)
# ADR-0027 tranche2-A: a HAS-OTHER-PLAN mirror for the migrated aoe_ping key — a
# "deals N damage to each creature" body (one-shot or repeatable) is a board-ping plan,
# NOT a vanilla voltron beater, so it silenced the commander-damage voltron tell.
# Mirrors the deleted aoe_ping _HAND_FLOOR regex exactly; feeds only the gate.
_AOE_PING_PLAN_MIRROR = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*deals? \d+ damage to each (?:other )?creature"
    r"|at the beginning of[^.]*deals? \d+ damage to each (?:other )?creature"
    r"|whenever you cast[^.]*deals? \d+ damage to each (?:other )?creature",
    re.IGNORECASE,
)
# ADR-0027 tranche2-A: a HAS-OTHER-PLAN mirror for the migrated mass_removal key — a
# board wipe (on a body or a spell) is a control plan, NOT a vanilla voltron beater, so
# it silenced the commander-damage voltron tell on a sweep-creature (Chaos Maw, Child
# of Alara). Mirrors the deleted mass_removal SWEEP_DETECTORS regex EXACTLY (only the
# old regex's matches, not the broader IR re-supply); feeds only the gate.
_MASS_REMOVAL_PLAN_MIRROR = re.compile(
    r"destroy all (?:other )?(?:nonland )?(?:permanents|creatures|artifacts"
    r"|enchantments|other creatures)|deals? \d+ damage to each (?:creature"
    r"|nonlegendary creature|other creature)|exile all (?:creatures|permanents)"
    r"|exile all (?:black|white|blue|red|green) creatures|all creatures get -\d"
    r"|destroy all [^.]*creatures except|destroy all other creatures",
    re.IGNORECASE,
)
# ADR-0027 tranche2-B: a HAS-OTHER-PLAN mirror for the migrated team_buff key — a
# "creatures you control have <evergreen keyword>" team-keyword grant is a go-wide
# plan, NOT a vanilla voltron beater, so it silenced the commander-damage voltron tell
# (Brave the Sands, Maze Behemoth, the DFC Topaz Dragon grant face; "other outlaws you
# control have vigilance" — Vihaan; "creatures you control that entered this turn have
# double strike" — Deathleaper). team_buff had TWO regex producers (a _HAND_FLOOR row
# and a SWEEP row), both deleted by the migration, so this mirror is their UNION — byte-
# identical to the pre-migration silencing (incl. the over-fire tail the narrower IR
# drops). It feeds only the gate, NOT the silencing-set IR re-supply (which would miss
# those over-fires AND, like mass_removal, over-silence). Needed once tranche2-A also
# deletes anthem_static's regex that previously masked this loss.
_TEAM_BUFF_PLAN_MIRROR = re.compile(
    r"(?:creatures?|permanents?) you control (?:gain|gains|have|has) "
    r"(?:flying|trample|menace|hexproof|indestructible|protection|deathtouch"
    r"|lifelink|double strike|first strike|vigilance|haste|ward|reach)"
    r"|(?:you and )?other \w+ you control have (?:hexproof|flying|trample"
    r"|indestructible|protection|ward|deathtouch|lifelink|menace|vigilance|haste"
    r"|first strike|double strike|reach)"
    r"|(?:each |all )?creatures? you control(?: that[^.]*?)? (?:gain|gains|have|has) "
    r"(?:indestructible|protection|hexproof|flying|trample|menace|deathtouch|lifelink"
    r"|double strike|first strike|vigilance|haste|ward|reach)",
    re.IGNORECASE,
)
# ADR-0027: a HAS-OTHER-PLAN mirror for the migrated sacrifice_matters key (its regex
# producer is deleted, so it no longer rides the ``out`` signal set the voltron gate
# reads). A you-sacrifice plan still silences the commander-damage voltron fallback —
# this matches the old broad detector + casualty regex exactly, but only feeds the
# gate (it emits no signal; the real lane is served from the IR). See ADR-0027.
_SACRIFICE_PLAN_MIRROR = re.compile(
    r"sacrifice (?:a|an|another|two|three|x|\d)|\bcasualty\b", re.IGNORECASE
)
# ADR-0027: the same HAS-OTHER-PLAN mirror for the migrated lifeloss_matters key — a
# drain / self-life-loss plan still silences the commander-damage voltron fallback.
# Mirrors the two deleted lifeloss _DETECTORS regexes exactly; feeds only the gate.
_LIFELOSS_PLAN_MIRROR = re.compile(
    r"\b(?:each opponent|each player|target opponent|target player|that player"
    r"|an opponent|each of your opponents|opponents?)"
    r"(?:\s+who\b[^.]{0,40}?)? loses? (?:\d+|x) life\b"
    r"|\bwhenever you (?:gain or )?lose life\b"
    r"|\bwhenever (?:an opponent|a player|one or more (?:players|opponents))"
    r" loses? life\b"
    r"|\blife [^.]*?lost this turn\b"
    r"|opponents? (?:who|that) lost life this turn"
    r"|opponent lost \d+ or more life this turn"
    r"|pay \d+ life|you lose \d+ life|you lose (?:x|that much) life"
    r"|you lose life equal to|you may pay (?:\d+|x) life",
    re.IGNORECASE,
)
# ADR-0027 (tranche2-C): the same HAS-OTHER-PLAN mirror for the five migrated
# tranche2-C keys (self_pump / tapper_engine / count_anthem / exert_matters /
# recast_etb). Each fired HIGH-confidence in the deleted _HAND_FLOOR / SWEEP path and
# so counted toward `has_other_plan`, silencing the spurious commander-damage voltron
# tell on a firebreathing sink / tapper / count-anthem / vigilance-enabler / sneak-
# recast body. Their regex producers are deleted, so this mirror (the OR of the exact
# deleted patterns) feeds the gate directly in extract_signals — reproducing the
# pre-migration `has_other_plan` for ALL cards (IR or not) so voltron_matters is
# unchanged. It emits no signal; the real lanes are served from the IR. NO-FLOOD.
_TRANCHE2C_PLAN_MIRROR = re.compile(
    r"\{[^}]*\}(?:, \{t\})?: [^.]* gets \+[0-9x]/\+[0-9x] until end of turn"
    r"|\{[wubrgc]\}: [^.:]*gets \+\d+/\+\d+ until end of turn"
    r"|\{[^}]*\}(?:, \{t\})?: put a \+1/\+1 counter on (?:it|this creature|[A-Z][a-z]+)"
    r"|:\s*tap (?:target|up to (?:one|two|\d+) target|all|each|two target|x target)"
    r"|(?:at the beginning of|whenever)[^.:]*,[^.]*\btap "
    r"(?:up to (?:one|two|\d+) target|target)"
    r"|\btap up to (?:one|two|\d+) target (?:creature|permanent)\b"
    r"|when [^.]* enters, tap (?:up to )?(?:one|two|\d+|target)"
    r"|(?:doesn't|don't|does not) untap during (?:its|their|the)"
    r"|(?:creatures you control get|each creature you control gets) "
    r"[+]\d+/[+]\d+ for each"
    r"|attacking doesn'?t cause (?:creatures|them)[^.]*to tap"
    r"|(?:other )?creatures you control have vigilance"
    r"|\bsneak\b|return an unblocked attacker",
    re.IGNORECASE,
)
# ADR-0027 (tranche2-B): the same HAS-OTHER-PLAN mirror for the four migrated
# tranche2-B keys (counter_manipulation / counter_place_trigger /
# counter_replace_bonus / exile_until_leaves). Each fired HIGH-confidence in the
# deleted SWEEP path (non-generic, non-voltron-compat) and so counted toward
# `has_other_plan`, silencing the spurious commander-damage voltron tell on a counter
# / O-Ring engine that is NOT a vanilla beater (Corpsejack Menace, Aragorn Company
# Leader, Dusk Legion Duelist, Kitesail Freebooter — 14 cards verified to leak the
# tell post-deletion). The IR re-supply is BROADER than the deleted regex
# (counter_manipulation +24 Graft moves, exile_until_leaves +33 linked-return O-Rings,
# counter_replace_bonus +9), so adding these keys to _VOLTRON_SILENCING_PLAN_KEYS
# would OVER-silence the IR-only bodies the regex never caught. Instead this mirror
# (the OR of the EXACT deleted patterns, read against the joined-face `_oracle` so it
# catches DFC back faces) feeds the gate directly in extract_signals, reproducing the
# pre-migration `has_other_plan` for ALL cards. It emits no signal; the real lanes are
# served from the IR. NO-FLOOD (voltron byte-identical to pre-migration).
_TRANCHE2B_PLAN_MIRROR = re.compile(
    # counter_manipulation
    r"(?:remove|move) (?:a|one|any number of|x|\d+) (?:\+1/\+1|-1/-1) counters?"
    r"|(?:remove|move) (?:a|one|any number of|x|\d+) [^.]{0,20}?"
    r"(?:\+1/\+1|-1/-1) counters?"
    # counter_place_trigger
    r"|whenever (?:you put|.*put) (?:one or more )?\+1/\+1 counters? on"
    r"|whenever one or more \+1/\+1 counters? (?:are|is) put on"
    r"|whenever you put (?:a|one or more|two|\d+) [^.]*counters? on"
    r"|whenever (?:a|one or more) [^.]*counters? (?:is|are) put on"
    # counter_replace_bonus
    r"|that many plus (?:one|two|\d+) [^.]*counters? are put|put that many plus"
    r"|if (?:one or more )?\+1/\+1 counters? would be put on"
    r"|one or more counters? would be (?:put|placed)"
    r"[^.]*(?:that many plus|twice that many)"
    # exile_until_leaves
    r"|exile [^.]*until [^.]*leaves the battlefield",
    re.IGNORECASE,
)
# ADR-0027 tranche2 batch-2 voltron reconciliation — bounce_tempo (t2b2-A) and
# keyword_counter (t2b2-C) each had a high-confidence regex producer that fed
# has_other_plan, silencing the spurious commander-damage voltron tell on a bounce-
# tempo creature (Man-o'-War, Reflector Mage, Brazen Borrower) or a keyword-counter
# creature (Wingfold Pteron, Void Beckoner). Those producers are deleted and the IR
# re-supply doesn't reach the regex-path has_other_plan, so this mirror (the deleted
# bounce_tempo SWEEP regex — broad enough to subsume its narrow _DETECTORS twin — OR
# the shared keyword_counter KEYWORD_COUNTER_REGEX) reproduces the silence on the
# joined-face oracle. The IR is BROADER than these regexes, so a mirror (not the
# _VOLTRON_SILENCING_PLAN_KEYS set) is the byte-identical gate. NB: the per-branch solo
# no-flood missed this (it toggled MIGRATED_KEYS with the regex already deleted, so both
# sides leaked equally and the delta read 0); the post-merge global re-validation caught
# the +40. CR 115.10 (bounce) / 122.1b (keyword counter).
_TRANCHE2B2_PLAN_MIRROR = re.compile(
    r"return (?:x )?target (?:creatures?|permanents?|nonland permanents?)[^.]*"
    r"to (?:its|their) owner.?s.? hands?"
    r"|return target (?:spell or permanent|permanent or spell)"
    r"|return [^.]*to (?:its|their) owners?.? hands?"
    r"|return up to (?:one|two|\w+) target (?:nonland )?(?:creature|permanent)[^.]*"
    r"to (?:its|their) owner.?s.? hands?"
    "|" + KEYWORD_COUNTER_REGEX,
    re.IGNORECASE,
)
# ADR-0027 tranche2-B-3: the migrated spell_keyword_grant / target_player_draws keys
# each had a high-confidence (non-generic, non-voltron-compat) SWEEP_DETECTORS producer
# that fed has_other_plan, silencing the spurious commander-damage voltron tell on a
# spell-keyword-granting / give-draw creature body (Silverquill Lecturer, Fallaji
# Wayfarer, Flamekin Herald, Sphinx of Enlightenment, Limestone Golem — 5 cards verified
# to leak the tell post-deletion). The IR re-supply is BROADER than the deleted regex
# (spell_keyword_grant +51 — the "as though they had flash" enablers; target_player_
# draws +232 — N-card / "that player" / "its controller" draws), so the IR-supply
# reconciliation (_VOLTRON_SILENCING_PLAN_KEYS) would OVER-silence the IR-only bodies
# the regex never caught. Instead this mirror — the OR of the two EXACT deleted regexes,
# read against the joined-face `_oracle` so it catches DFC back faces — feeds the gate
# directly, reproducing the pre-migration has_other_plan for ALL cards. It emits no
# signal; the real lanes are served from the IR. NO-FLOOD (voltron byte-identical to
# pre-migration). CR 601.3e (cast with keyword) / 120.2 (draw).
_TRANCHE2B3_PLAN_MIRROR = re.compile(
    SPELL_KEYWORD_GRANT_REGEX + "|" + TARGET_PLAYER_DRAWS_REGEX,
    re.IGNORECASE,
)
# ADR-0027 tranche2-B (t2b3-B): mirror the FULL deleted opponent_cast_matters regex —
# INCLUDING its over-broad bare "whenever a player casts a spell" arm. The migrated IR
# is MORE precise than that bare arm (it drops the symmetric-benefit / self-drawback
# over-fires), so the IR re-supply does NOT cover those cards — but in the regex path
# they fired high-confidence and counted toward has_other_plan, silencing the spurious
# commander-damage voltron tell on a cast-trigger creature (Ivy, Kraum, Scytheclaw
# Raptor, Glademuse, Ogre Recluse, Perplexing Chimera, Chancellor of the Annex). Mirror
# (not _VOLTRON_SILENCING_PLAN_KEYS — the IR is broader, so re-supply would under-cover
# the bare-arm cards) reproduces the silence byte-identically on the joined-face oracle.
# CR 603.2.
_OPP_CAST_PLAN_MIRROR = re.compile(
    r"whenever an opponent casts|whenever (?:a|another) player casts a spell"
    r"|whenever an opponent cast"
    r"|whenever (?:a|another) player casts[^.]*(?:(?:they|that player) "
    r"(?:loses?|discards?|sacrifices?)|deals? \d+ damage to that player)",
    re.IGNORECASE,
)
# ADR-0027 tranche2 batch-3 voltron reconciliation — keyword_soup (t2b3-A) and
# land_creatures_matter (t2b3-A) each had a high-confidence regex producer that fed
# has_other_plan, silencing the spurious commander-damage voltron tell on a keyword-
# soup body (Soulflayer "the same is true for first strike, double strike") or a
# land-creatures body (Earth Rumble Wrestlers "as long as you control a land
# creature"). Those producers are deleted and the IR re-supply (broader than the regex,
# so a mirror — not the silencing-keys set) doesn't reach the regex-path gate. This
# mirror (the OR of the two EXACT deleted regexes, read against the joined-face
# `_oracle`) reproduces the silence. The agents self-reconciled their other keys, but
# the cross-branch composition exposed these 2; the post-merge global diff caught them.
# CR 702 (keyword soup) / 305 (land creatures).
_TRANCHE2B3A_PLAN_MIRROR = re.compile(
    r"if it has flying[^.]*first strike"
    r"|the same is true for first strike, double strike"
    r"|has flying[^.]*\+1/\+1"
    r"|\bland creatures?\b|lands? you control (?:are|become)\b"
    r"|all lands[^.]*become[^.]*creature"
    r"|target land[^.]*becomes? a[^.]*creature"
    r"|(?:it's|becomes?) a forest land",
    re.IGNORECASE,
)
# ADR-0027 tranche2-batch-4 (t2b4a-A) voltron reconciliation — the deleted
# tribal_etb_multi / typed_enters_punish / vanilla_matters regex producers each fired
# high-confidence (scope='you') and so counted toward has_other_plan, silencing the
# spurious commander-damage voltron tell on a creature body (Goblin Assassin — "this or
# another Goblin enters → each player flips a coin, sacrifices" — silenced by the
# tribal_etb_multi regex). The producers are deleted and the broader IR re-supply
# doesn't reach the regex-path gate, so this mirror (the OR of the THREE EXACT deleted
# regexes, read against the joined-face `_oracle`) reproduces the silence byte-
# identically. (A mirror — not _VOLTRON_SILENCING_PLAN_KEYS — because the IR is broader
# than the narrow deleted regexes and would over-silence legit engine bodies via the
# silencing-keys path.) CR 603 (ETB triggers) / 113.3 (vanilla).
_TRANCHE2B4A_PLAN_MIRROR = re.compile(
    r"whenever [^.]*or another [A-Z][a-z]+(?:, [A-Z][a-z]+)*,? "
    r"(?:or [A-Z][a-z]+ )?enters"
    r"|whenever another (?:outlaw|ally|\w+) you control enters, "
    r"[^.]*deals \d+ damage to (?:target opponent|each opponent|any target)"
    r"|creatures? (?:card )?with no abilities",
    re.IGNORECASE,
)
# ADR-0027 tranche2-batch-4a (t2b4a-B) voltron reconciliation — FOUR of the five
# deleted regex producers (win_lose_game / xspell_matters / alt_cost_keyword /
# curse_matters) each fired HIGH-confidence in the regex path and counted toward
# has_other_plan, silencing the spurious commander-damage voltron tell on a body whose
# only "plan" was one of these (a win-the-game wincon — Azor's Elocutors, Lab Maniac,
# Biovisionary; an alt-cost creature — the Mayhem / Web-slinging beaters; an {X}-spell
# payoff; a Curse referencer). Their IR re-supply rides the hybrid path, not the
# regex-path gate, so a mirror (the UNION of the three boolean-OR deleted regexes, read
# against the joined-face `_oracle`) re-supplies the silence byte-identically. NB:
# partner_background is DELIBERATELY EXCLUDED — it is a _VOLTRON_COMPAT_KEY (a partner
# commander can ALSO be a voltron beater — Wilson, Eligeth, Peri Brown), so its old
# producer never counted toward has_other_plan and must not silence here. The {X}-spell
# arm carries its own VETO (Gaddock Teeg's "spells with {X} … can't be cast" fired NO
# producer, so it must NOT silence) — handled by the _XSPELL_HOOK/_XSPELL_VETO check
# OR'd in separately at the has_other_plan site. CR 104.2 / 118.9 / 202.1.
_T2B4A_PLAN_MIRROR = re.compile(
    # win_lose_game
    r"you win the game|(?:that player|each opponent"
    r"|target (?:player|opponent)) loses the game"
    # alt_cost_keyword
    r"|\bweb-slinging\b|\bsneak\b|\bmayhem\b"
    # curse_matters (cares-about)
    r"|curse spells?|curses? you (?:cast|control|own)"
    r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
    re.IGNORECASE,
)
# ADR-0027 tranche2-batch-5 (t2b5-B) voltron reconciliation — the deleted
# per_target_payoff / sacrifice_protection / secret_writedown / target_own_payoff /
# target_redirect regex producers each fired HIGH-confidence (scope='you') in the regex
# path and counted toward has_other_plan, silencing the spurious commander-damage
# voltron tell on a creature whose only "plan" was one of these (a wishboard ETB body —
# Legion Angel, North Wind Avatar "from outside the game"; a secret-choose body —
# Emissary of Grudges "secretly choose an opponent"; a sac-protection body — Tajuru
# Preserver "can't cause you to sacrifice permanents"). Their IR re-supply rides the
# hybrid path, NOT the regex-path gate, so this mirror (the UNION of the five EXACT
# deleted regexes) re-supplies the silence byte-identically — voltron 0 leaked AND 0
# lost vs the FILE-SWAP base. (A mirror — not _VOLTRON_SILENCING_PLAN_KEYS — because the
# IR is broader, so re-supply via the silencing-keys path would over-silence.) The gate
# is matched against the reminder-STRIPPED `text` (NOT `_oracle`), because the deleted
# producers were floor Detectors over reminder-stripped clauses — a "from outside the
# game" inside a Learn keyword's reminder (Professor of Symbology, Gnarled Professor,
# Eyetwitch, Dream Strix) never fired them, so the gate must not silence those bodies.
# The secret_writedown arm KEEPS the companion "your sideboard" clause (it was in the
# pre-migration regex run over `text`, so it silenced companions then and must now). CR
# 408.1 / 701.16 / 603 / 118.
_T2B5_PLAN_MIRROR = re.compile(
    # per_target_payoff
    r"less (?:to cast )?for each (?:of those )?target"
    # sacrifice_protection
    r"|can't cause you to sacrifice|can't be sacrificed"
    # secret_writedown (gate keeps the companion arm the detector mirror drops)
    r"|secretly (?:write|choose|name)"
    r"|before the game begins[^.]*(?:write|name|choose)"
    r"|from outside the game|your sideboard"
    # target_own_payoff
    r"|creature you control becomes the target[^.]*you may"
    # target_redirect
    r"|becomes? the target of a spell or ability an opponent controls[^.]*draw",
    re.IGNORECASE,
)
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


# Aura/Equipment subtypes + the attachment-STATE predicates phase emits ("for each
# Aura attached to it" → AttachedToRecipient; "enchanted or equipped" creatures →
# HasAnyAttachmentOf). A subject carrying either is the voltron build-around's
# structural anchor (CR 301.5 Equipment, 303.4 Aura, 702.6 enchant).
_EQUIP_AURA_SUBTYPES = frozenset({"aura", "equipment"})
_ATTACHMENT_PREDICATES = frozenset({"AttachedToRecipient", "HasAnyAttachmentOf"})
# An attach effect that moves ANOTHER object (a typed Equipment/Aura/Role) onto a
# creature — the build-around (Kor Outfitter "attach target Equipment", Balan
# "attach all Equipment", Hammer of Nazahn). Phase emits the same `attach` category
# for a card SELF-attaching (gear's own Equip cost / ETB "attach it" / living
# weapon / a removal Aura's enchant), which is NOT a voltron payoff — the regex
# floor deliberately stays off the singular Equipment/Aura payload, so the
# projection reads the effect raw to keep only the attach-OTHER form.
_ATTACH_OTHER_RE = re.compile(
    r"attach (?:target |all |any number of |up to (?:one|two|\w+) target |an |a )?"
    r"(?:equipment|aura|role)",
    re.IGNORECASE,
)
_SELF_ATTACH_RE = re.compile(
    r"^attach (?:it|this|that|~)\b|^equip[\s{]|^reconfigure|^fortify",
    re.IGNORECASE,
)


def _is_attach_other(e: Effect) -> bool:
    """True if a beneficial (non-opponent) attach effect moves ANOTHER typed
    Equipment/Aura/Role onto a creature — the voltron build-around — rather than the
    card self-attaching (its own Equip cost / "attach it" / living weapon / a removal
    Aura's enchant), which phase emits identically but the regex floor excludes."""
    if e.category not in ("attach", "unattach") or e.scope == "opp":
        return False
    raw = (e.raw or "").strip()
    return bool(_ATTACH_OTHER_RE.search(raw)) and not _SELF_ATTACH_RE.match(raw)


def _detect_voltron_payoff_ir(ir: Card) -> bool:
    """True if the Card IR carries a structural Aura/Equipment PAYOFF (the voltron
    build-around, NOT the gear/aura payload or the commander-damage membership
    fallback). Four unambiguous structural tells:

    * a cast-an-Aura/Equipment-spell trigger (Sram, Kor Spiritdancer);
    * a tutor for an Aura/Equipment CARD (Godo, Three Dreams, Stoneforge Mystic);
    * an attachment-STATE predicate (``AttachedToRecipient`` "for each Aura attached
      to it"; ``HasAnyAttachmentOf`` "enchanted or equipped creatures" — Koll, Reyav)
      on any effect/condition subject;
    * an attach effect moving ANOTHER typed Equipment/Aura onto a creature
      (``_is_attach_other`` — Kor Outfitter, Balan, Hammer of Nazahn).

    Deliberately NOT projected: the bare Aura/Equipment SUBTYPE on an effect subject
    (also covers Aura HATE — "destroy target Aura"), the ``EquippedBy`` payload-pump
    ("equipped creature gets +X/+X"), and self-attach (the gear itself) — all of
    which the regex floor stays off. Projects the lane from phase's structure
    instead of the oracle-regex floor/sweep rows (ADR-0027)."""
    for ab in ir.all_abilities():
        trg = ab.trigger
        if (
            trg is not None
            and trg.event == "cast_spell"
            and isinstance(trg.subject, Filter)
            and {s.lower() for s in trg.subject.subtypes} & _EQUIP_AURA_SUBTYPES
        ):
            return True
        for e in ab.effects:
            if _is_attach_other(e):
                return True
            # tutor for an Aura/Equipment CARD — the subtype on the searched filter.
            if (
                e.category == "tutor"
                and isinstance(e.subject, Filter)
                and ({s.lower() for s in e.subject.subtypes} & _EQUIP_AURA_SUBTYPES)
            ):
                return True
            for f in (e.subject, e.amount.subject if e.amount is not None else None):
                if isinstance(f, Filter) and (
                    set(f.predicates) & _ATTACHMENT_PREDICATES
                ):
                    return True
        cond = ab.condition
        if (
            cond is not None
            and isinstance(cond.subject, Filter)
            and set(cond.subject.predicates) & _ATTACHMENT_PREDICATES
        ):
            return True
    return False


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


# ADR-0027 tranche2-batch-4 (t2b4-C) — self_blink kept-detector mirror. phase parses a
# self-exile+return as two Effect(category='exile', subject=None) whose `~`-substituted
# raw can't tell "exile this creature (self-blink)" from "exile ~ as a cost" / other-
# target exiles (a raw 'exile ~'+to:battlefield over-fires to ~176 cards). So self_blink
# has NO clean structural IR form. The regex path produced it from TWO disjoint sources
# (zero overlap over the commander-legal corpus): the name-aware cross-sentence
# _detect_self_blink_fulltext (Norin-style, 34 cards) AND this single-target SWEEP regex
# run PER-CLAUSE (Ephemerate / Soulherder, 35 cards). The IR path mirrors BOTH to stay
# byte-identical (union 69; A-B==0). NB the SWEEP regex's `[^.]*\.?\s*` arms span a
# sentence over the WHOLE oracle (+24 over-fire), so it MUST be run per-clause via
# _clauses (matching the regex path), not as a flat _IR_KEPT_DETECTORS full-text row.
# This is the EXACT deleted SWEEP_DETECTORS["self_blink"] regex (byte-identical mirror).
_SELF_BLINK_SWEEP_RE = re.compile(
    r"exile (?:up to one |another |a |target )?(?:other )?target "
    r"(?:creature|permanent)[^.]*\.?\s*return (?:that|those|it|the[^.]*)"
    r"[^.]*to the battlefield"
    r"|exile (?:any number of|all|each)[^.]*creatures[^.]*return"
    r"|exile [A-Z][a-z']+\.\s*return (?:it|that card|them)[^.]*to the battlefield",
    re.IGNORECASE,
)


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
        # anthem_static's regex producer is deleted (ADR-0027 tranche2-A migration), so
        # it never rides ``keys_now`` here — the oracle mirror keeps the go_wide gate
        # aware of a static team-buff so an anthem lord's own class type still opens
        # (the IR path's go_wide sees the real anthem_static signal; preserves parity).
        _gate = {"creatures_matter", "attack_matters", "anthem_static"}
        go_wide = bool(keys_now & _gate) or bool(
            _ANTHEM_GO_WIDE_MIRROR.search(card.get("oracle_text") or "")
        )
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
    # ADR-0027 t2b4-C: self_blink migrated to the Card IR (kept_detector). The regex
    # path's emission (the name-aware fulltext detector + the SWEEP per-clause regex) is
    # deleted here; extract_signals_ir reproduces BOTH byte-identically. The
    # _detect_self_blink_fulltext / _SELF_BLINK_SWEEP_RE definitions stay — the IR path
    # reuses them.
    self_death_clause = _detect_self_death_payoff(text, name)
    if self_death_clause is not None:
        add("self_death_payoff", "you", "", self_death_clause)
    # Run against the RAW oracle (not the reminder-stripped `text`): a meld BACK piece
    # (Bruna) carries its meld info only in the "(Melds with …)" reminder, which the
    # per-clause path strips. subject = this card's name; the partner names it.
    _meld_raw = get_oracle_text(card)
    if name and _MELD_FULLTEXT_RE.search(_meld_raw):
        add("meld_pair", "you", name, _meld_raw[:160])
    # ADR-0027: counters_matter migrated to the Card IR — the self-counter-payoff and
    # counter-HAVE-payoff add() producers are deleted (the +1/+1 placement / "has a
    # +1/+1 counter" reference fires from place_counter(p1p1) + the counters_have_ref
    # marker via the IR path). Their orphaned regex helpers were removed with this
    # cleanup.
    if _detect_polymorph_cheat(text):
        add("cheat_into_play", "you", "", text[:160])
    # ADR-0027: reanimator migrated to the Card IR — a creature whose `reanimate`
    # effect returns CREATURE cards from a graveyard to the battlefield (the archetype),
    # via _reanimates_creature (incl. its raw fallback for the subject phase drops). The
    # legacy regex conflated this with "cast a spell FROM a graveyard" (flashback /
    # escape / disturb — CR 702.34 casting ≠ reanimation), which the structural IR
    # correctly drops. The legacy active-reanimation oracle-regex producer is deleted.
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
    # ADR-0027: sacrifice_matters migrated to the IR, so its regex producer no longer
    # appears in ``out`` here — but a card with a sacrifice plan is still NOT a vanilla
    # voltron beater. Mirror just the gate (not an emission) so the commander-damage
    # membership fallback below stays silenced on aristocrats commanders, matching the
    # pre-migration behavior. The serve/IR side emits the real signal.
    # The mirrors run against the JOINED-face oracle (get_oracle_text) — NOT raw
    # ``card.get("oracle_text")``, which is empty on a transform DFC, so a mirror keyed
    # on it goes blind on a back-face plan body (Archangel Avacyn's "deals 3 damage to
    # each other creature", Topaz Dragon's grant face). Joining both faces makes the
    # mirrors see the DFC back face the pre-migration path silenced on. Reminder text is
    # intentionally KEPT here (unlike ``text``, the detector input) so the mirrors stay
    # byte-identical to their own pre-migration behavior on non-DFC cards.
    _oracle = get_oracle_text(card) or ""
    has_other_plan = (
        any(
            s.confidence == "high"
            and s.key not in _GENERIC_KEYS
            and s.key not in _VOLTRON_COMPAT_KEYS
            for s in out
        )
        or _SACRIFICE_PLAN_MIRROR.search(_oracle)
        or _LIFELOSS_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-A: the migrated anthem_static / aoe_ping regex producers are
        # deleted, so they no longer ride ``out`` here. Their OLD oracle matches still
        # signal a NON-vanilla plan (a go-wide team-buff or a repeatable board-ping
        # body), which silenced the commander-damage voltron membership tell. Mirror the
        # two deleted regexes (gate-only — the real lanes are served from the IR) so the
        # silencing is identical to pre-migration, including the EOT-pump / one-shot
        # bodies the broad regexes incidentally covered.
        or _ANTHEM_GO_WIDE_MIRROR.search(_oracle)
        or _AOE_PING_PLAN_MIRROR.search(_oracle)
        or _MASS_REMOVAL_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-B: mirror the deleted team_buff regex (a go-wide team-
        # keyword grant). Byte-identical to the old _HAND_FLOOR regex; required once
        # tranche2-A also deletes the anthem_static regex that previously masked it.
        or _TEAM_BUFF_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-C: mirror the OR of the five deleted self_pump / tapper /
        # count_anthem / exert / recast regexes (their high-confidence regex producers
        # silenced voltron). Byte-identical to pre-migration; the IR re-supply is
        # broader and would over-silence legit engine bodies (Aetherling,
        # Angel's Trumpet).
        or _TRANCHE2C_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-B: mirror the OR of the four deleted counter / O-Ring
        # regexes (counter_manipulation / counter_place_trigger / counter_replace_bonus
        # / exile_until_leaves). Byte-identical to pre-migration; the IR re-supply is
        # broader (Graft moves, linked-return O-Rings) and would over-silence via
        # _VOLTRON_SILENCING_PLAN_KEYS.
        or _TRANCHE2B_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2 batch-2: re-silence bounce_tempo / keyword_counter (their
        # deleted regex producers fed this gate; IR re-supply doesn't reach it).
        or _TRANCHE2B2_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-B-3: re-silence spell_keyword_grant / target_player_draws
        # (deleted SWEEP producers fed this gate; the broader IR re-supply doesn't reach
        # it). Byte-identical to pre-migration on the 5 leaked creature bodies.
        or _TRANCHE2B3_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-B (t2b3-B): re-silence the deleted opponent_cast_matters
        # regex (its high-confidence producer fed this gate; the more-precise IR drops
        # the bare-arm cards, so a mirror — not the silencing-keys set — is required).
        or _OPP_CAST_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2 batch-3: re-silence keyword_soup / land_creatures_matter
        # (deleted regex producers fed this gate; cross-branch composition exposed 2).
        or _TRANCHE2B3A_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-batch-4 (t2b4a-A): re-silence tribal_etb_multi /
        # typed_enters_punish / vanilla_matters (deleted regex producers fed this gate;
        # the broader IR re-supply doesn't reach it). Goblin Assassin leaked without it.
        or _TRANCHE2B4A_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2 batch-4a: re-silence win_lose_game / alt_cost_keyword /
        # curse_matters (UNION mirror) + xspell_matters (its own hook-minus-veto,
        # matching the deleted _DETECTORS predicate exactly). partner_background is
        # excluded (a _VOLTRON_COMPAT_KEY). Deleted regex producers fed this gate; the
        # broader IR re-supply rides the hybrid path.
        or _T2B4A_PLAN_MIRROR.search(_oracle)
        # ADR-0027 tranche2-batch-5: re-silence the five deleted regex producers
        # (per_target_payoff / sacrifice_protection / secret_writedown /
        # target_own_payoff / target_redirect). Their high-confidence producers fed this
        # gate; the IR re-supply rides the hybrid path, so a mirror — not the silencing-
        # keys set — restores the byte-identical silence (voltron 0 leaked). Matched
        # against ``text`` (reminder-STRIPPED), NOT ``_oracle``: the deleted producers
        # were floor Detectors over reminder-stripped clauses, so a "from outside the
        # game" buried in a Learn keyword's reminder (Professor of Symbology, Eyetwitch)
        # never fired them — keeping reminders here would over-silence those bodies.
        or _T2B5_PLAN_MIRROR.search(text)
        or (
            bool(_XSPELL_HOOK_RE.search(_oracle))
            and not _XSPELL_VETO_RE.search(_oracle)
        )
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
    # ADR-0027: untap is NOT a blanket doer — every "untap it/that/this" incidental
    # untap (Act of Treason's threaten, Abduction's enchant, Amulet of Vigor) and the
    # "doesn't untap" INVERSION (Basalt Monolith) fired untap_engine through the doer
    # loop. The lane wants a deliberate untap ENGINE (untap target/all/each — Seedborn
    # Muse, Kiora), so it now fires from a GATED arm (cat=="untap" + _UNTAP_ENGINE_RAW
    # or a mass untap) instead of this entry. See extract_signals_ir.
    "proliferate": ("proliferate_matters", "you"),
    "topdeck_select": ("topdeck_selection", "you"),
    # ADR-0027: gain_control is NOT a blanket doer — the blanket fire mislabeled DONATE
    # (you give your own permanent away — Donate, Bazaar Trader) and RETURN-CONTROL
    # resets (Brooding Saurian) as theft. gain_control now fires from a GATED arm
    # (cat=="gain_control", excluding donate + Owned-subject return) in
    # extract_signals_ir.
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
    # Face-down 2/2 mechanics (CR 701.40 manifest / 701.58 cloak / 708) and the
    # turn-face-up payoff all feed the existing facedown_matters lane — manifest is
    # NOT a token_maker (CR 122.1), so it no longer pollutes that lane.
    "manifest": ("facedown_matters", "you"),
    "cloak": ("facedown_matters", "you"),
    "turn_face_up": ("facedown_matters", "you"),
    "ring_tempt": ("ring_matters", "you"),
    # Explore (CR 701.44) → its dedicated lane (was topdeck_select, but explore is a
    # reveal-top + land/counter mechanic, not a Brainstorm-style stacker).
    "explore": ("explore_matters", "you"),
    "energy": ("energy_matters", "you"),
    # Player-counter givers (GivePlayerCounter, split by kind in project.py — CR
    # 122.1). poison/rad land on opponents (a kill clock / penalty); experience is
    # a personal resource. ticket/unknown player counters stay lane-less (niche).
    "poison": ("poison_matters", "opponents"),
    "experience_counter": ("experience_matters", "you"),
    "rad_counter": ("rad_counter_matters", "opponents"),
    "phasing": ("phasing_matters", "you"),
    # ADR-0027 restriction-narrow markers (project._narrow_mechanic_refs): a
    # "becomes saddled"/"you saddle" grant (CR 702.171) and a "paired with a
    # creature with soulbond" reference (CR 702.95) phase folds into a generic
    # carrier are appended as precise saddle/soulbond marker effects → their lanes.
    "saddle": ("saddle_matters", "you"),
    "soulbond": ("soulbond_matters", "you"),
    # ADR-0027 trigger-other raw-markers (project._narrow_trigger_other_refs): a
    # named-mechanic PAYOFF trigger phase flattened to event='other', surviving only
    # in the effect raw, is appended as a precise marker effect → its lane. coin_flip
    # / ring_tempt / explore are already mapped above (their effect categories were
    # already read); these are the remaining payoff anchors. discover/ninjutsu reach
    # A-B==0 and migrate; boast/exhaust/scry_surveil close their event='other' tail
    # but a static-grant / delayed-trigger / scry-replacement remainder keeps them on
    # regex (see ADR-0027). CR 701.57 discover, 702.49 ninjutsu, 702.142 boast,
    # 702.177 exhaust, 701.22/701.25 scry/surveil.
    "discover": ("discover_matters", "you"),
    "ninjutsu": ("ninjutsu_matters", "you"),
    "boast": ("boast_matters", "you"),
    "exhaust": ("exhaust_matters", "you"),
    "scry_surveil": ("scry_surveil_matters", "you"),
    # ADR-0027 conferred-keyword re-parse markers (project._narrow_conferred_keyword
    # _refs): a keyword GRANTED to a class of objects (affinity for X / has madness /
    # has foretell), surviving only in a grant carrier's raw, is appended as a precise
    # marker effect → its lane. The card's OWN printed keyword still rides the Scryfall
    # keyword array (_IR_KEYWORD_MAP); these markers add the keyword-LESS conferred
    # granters. CR 702.41 affinity, 702.35 madness, 702.143 foretell. (devour / connive
    # / counter_spell / evasion_denial / damage_reflect markers are read elsewhere —
    # devour's multi-lane fan-out, connive above, counter_spell/evasion_denial/
    # damage_reflect their own per-effect reads.)
    "affinity": ("affinity_type", "you"),
    "madness": ("madness_matters", "you"),
    "foretell": ("foretell_matters", "you"),
    # ADR-0027 keyword-conditioned payoff markers (project._narrow_payoff_condition
    # _refs) + dropped-static face markers (project._dropped_static_markers): a
    # mutate cast-payoff / scavenge graveyard-grant phase left only in a non-grant
    # carrier raw or dropped entirely (surviving on the face oracle text) is appended
    # as a precise marker effect → its lane. The keyword-bearing makers ride the
    # Scryfall keyword array (_IR_KEYWORD_MAP); these add the keyword-LESS payoff /
    # granter residual. CR 702.139 mutate, 702.97 scavenge.
    "mutate": ("mutate_matters", "you"),
    "scavenge": ("scavenge_fuel", "you"),
    # ADR-0027 condition-form crime marker (project._dropped_static_markers): a
    # "(if|as long as) you've committed a crime this turn" payoff phase has no
    # condition kind for. The TRIGGER form ("Whenever you commit a crime") rides
    # phase's commit_crime trigger event (_PAYOFF_TRIGGER_KEYS); this is the
    # keyword-less condition-form payoff half (CR 701.49).
    "crime": ("crimes_matter", "you"),
    # ADR-0027 repeatable-pay-life marker (project._dropped_static_markers): a
    # "Pay N life:" activated-ability cost phase misparses (Arco-Flagellant,
    # Hibernation Sliver) or drops inside a conferred quoted ability (Underworld
    # Connections, the volvers). The structural paylife COST rides "paylife" in
    # cost_parts below; this is the misparse/conferred-ability residual (CR 118).
    "life_payment": ("life_payment_insurance", "you"),
    "roll_die": ("dice_matters", "you"),
    "dig_until": ("dig_until", "you"),
    # ADR-0027 sweep markers (project._dropped_static_markers / _narrow_trigger_other
    # _refs): a payoff/reference phase left only on the face oracle text or in an
    # event='other' carrier raw is appended as a precise marker effect → its lane.
    # starting_life ← "starting life total" compare (CR 103.4); mass_death ←
    # "creatures that died this turn" count operand (CR 700.4); cycling ← a
    # "cycle or discard" payoff trigger (CR 702.29). roll_die above already maps the
    # dice marker (same category as phase's native roll_die effect).
    "starting_life": ("starting_life_matters", "you"),
    "mass_death": ("mass_death_payoff", "you"),
    "cycling_payoff": ("cycling_matters", "you"),
    # ADR-0027 sweep batch 2 conferred/dropped-static markers — the keyword-less
    # granter / anthem / reference phase folds into a carrier raw or drops onto the
    # face oracle. The card's OWN printed cascade/undying/persist/changeling rides the
    # Scryfall keyword array (_IR_KEYWORD_MAP); these add the keyword-LESS form.
    "cascade": ("cascade_matters", "you"),
    "undying_persist": ("undying_persist_matters", "you"),
    "changeling": ("changeling_matters", "you"),
    # creature_cast ← the face-only-drop creature-cast reference (Blink's quoted token
    # ability, Glimpse of Nature's delayed trigger); scope "any" mirrors the regex.
    "creature_cast": ("creature_cast_trigger", "any"),
    # saga ← a lore-counter manipulation/payoff face reference (the chapter-advancement
    # build-around; a vanilla Saga's own reminder-only lore mention doesn't fire).
    "saga": ("saga_matters", "you"),
    # Batch 14 — extra-phase / type-change / mass-goad effect categories.
    "extra_combat": ("extra_combats", "you"),
    "extra_upkeep": ("extra_upkeep", "you"),
    "extra_draw": ("extra_draw_step", "you"),
    "extra_end": ("extra_end_step", "you"),
    "goad_all": ("goad_matters", "opponents"),
    "counter_move": ("counter_move", "you"),  # Batch 7 — MoveCounters effect
    # DEFERRED: type_change — SetCardTypes is kept as accurate IR but the lane
    # fires 0 in commander-legal (the regex's 25 are mostly static "is also a..."
    # which phase models differently); the lane waits for that shape.
    # clone_matters + per-type copy lanes are wired in extract_signals_ir from the
    # BecomeCopy "clone" category's COPIED type (creature-only for clone_matters;
    # the broad regex's token/spell-copy belong to their own lanes).
    # topdeck_stack is wired in extract_signals_ir (not here): _library_position_
    # effect now carries the WHERE (top/bottom/nth) in counter_kind, and the lane
    # fires only on a top-ish position with YOUR moved cards (excludes Bottom puts +
    # bounce-to-top removal). Resolves the deferred +421 flood.
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
    # Casualty (CR 702.153) sacrifices a creature as a cost to copy the spell — the
    # printed KEYWORD is the structural anchor for the sac cost phase folds into the
    # Casualty parse (no sacrifice Effect / cost token survives). Mirrors the regex
    # `\bcasualty\b` → sacrifice_matters. It ALSO copies the spell, so it opens
    # spell_copy_matters too (ADR-0027). The GRANTER (Anhelo — "has casualty 2") is
    # keyword-less and is recovered by a cast_with_keyword raw marker below.
    "casualty": (("sacrifice_matters", "you"), ("spell_copy_matters", "you")),
    "changeling": (("changeling_matters", "you"),),
    "companion": (("companion_keyword", "you"),),
    # Connive (CR 701.50) as the printed KEYWORD — covers the keyword-LESS GRANTER
    # (Security Bypass's Aura grants the enchanted creature "it connives", which
    # phase swallows into the Enchant parse so no connive effect is emitted). The
    # native connive EFFECT already covers self-conniving cards via _DOER_EFFECT_KEYS;
    # Scryfall tags the granter with the keyword too, so this lifts it cleanly.
    "connive": (("connive_matters", "you"),),
    "convoke": (("convoke_matters", "you"),),
    # Devour (CR 702.82) enters with +1/+1 counters per sacrificed creature — a
    # definitional +1/+1 source, so the printed keyword opens counters_matter too
    # (mirrors the `devour` EFFECT-category fan-out; covers Preyseizer Dragon, whose
    # devour rides the keyword + a board_count, not a `devour` effect). CR 122.1.
    "devour": (("devour_matters", "you"), ("counters_matter", "any")),
    "discover": (("discover_matters", "you"),),
    # Explore (CR 701.44) as the printed KEYWORD — the Scryfall-authoritative path
    # covers explore cards whose explore lives in a granted ability / replacement
    # clause / Map-token grant (Topography Tracker, Glowcap Lantern, Get Lost, …)
    # and so emit NO explore EFFECT node. The explore EFFECT category (doers + the
    # event='other' payoff trigger) opens it via _DOER_EFFECT_KEYS; this opens it
    # from the keyword the card actually carries (53 ⊇ the 44 regex hits).
    "explore": (("explore_matters", "you"),),
    "foretell": (("foretell_matters", "you"),),
    "madness": (("madness_matters", "you"),),
    # ADR-0027 counters_matter migration: the +1/+1-counter keyword block MOVED here
    # from _DIRECT_KEYWORD_SIGNALS (the shared regex/IR keyword path). counters_matter
    # is migrated, so it must leave the regex-readable _DIRECT_KEYWORD_SIGNALS; but the
    # IR path STILL needs the keyword for cards whose place_counter phase emits with a
    # blank counter_kind + a reminder-stripped raw (no "+1/+1" in the structural text —
    # Anafenza Kin-Tree's bolster, Goblin Glory Chaser's renown, Pteramander's adapt),
    # which the structural place_counter→counters_matter edge misses. _IR_KEYWORD_MAP
    # is IR-only (extract_signals doesn't read it), so this is the saddle-style move.
    # Each is definitionally a +1/+1-counter mechanic (CR 702.x). devour is mapped
    # above (it also sacs).
    # (scavenge and undying are mapped lower in this dict — counters_matter is merged
    # into their existing entries there to avoid a duplicate key.)
    "mentor": (("counters_matter", "any"),),
    "training": (("counters_matter", "any"),),
    "modular": (("counters_matter", "any"),),
    "bolster": (("counters_matter", "any"),),
    "evolve": (("counters_matter", "any"),),
    "outlast": (("counters_matter", "any"),),
    "renown": (("counters_matter", "any"),),
    "adapt": (("counters_matter", "any"),),
    "dethrone": (("counters_matter", "any"),),
    "graft": (("counters_matter", "any"),),
    "riot": (("counters_matter", "any"),),
    "bloodthirst": (("counters_matter", "any"),),
    "fabricate": (("counters_matter", "any"),),
    "sunburst": (("counters_matter", "any"),),
    "tribute": (("counters_matter", "any"),),
    "unleash": (("counters_matter", "any"),),
    "ravenous": (("counters_matter", "any"),),
    "reinforce": (("counters_matter", "any"),),
    # Phasing (CR 702.26) as the printed KEYWORD — Teferi's Imp, Ertai's Familiar,
    # and reminder-only phasers (Sandbar Crocodile) whose only "phases out" sits in
    # the stripped reminder text the regex floor misses. The phasing EFFECT category
    # (phase-out/in actions, project._narrow_mechanic_refs) opens the lane via
    # _DOER_EFFECT_KEYS; this opens it from the keyword the card actually carries.
    "phasing": (("phasing_matters", "you"),),
    # Graveyard-cast + graveyard-payoff keyword family — a card with any of these
    # uses ITS OWN / your graveyard as a resource (cast-from-GY: flashback/escape/
    # disturb/embalm/eternalize/encore/aftermath/retrace/jump-start/recover/unearth;
    # GY-payoff: dredge/delve/scavenge), so it cares about graveyards (scope you).
    # NOT graveyard HATE (exile from an opponent's GY) — that's a different lane.
    "flashback": (("graveyard_matters", "you"),),
    "escape": (("graveyard_matters", "you"),),
    "disturb": (("graveyard_matters", "you"),),
    "embalm": (("graveyard_matters", "you"),),
    "eternalize": (("graveyard_matters", "you"),),
    "encore": (("graveyard_matters", "you"),),
    "aftermath": (("graveyard_matters", "you"),),
    "retrace": (("graveyard_matters", "you"),),
    "jump-start": (("graveyard_matters", "you"),),
    "recover": (("graveyard_matters", "you"),),
    "unearth": (("graveyard_matters", "you"),),
    "dredge": (("graveyard_matters", "you"),),
    "delve": (("graveyard_matters", "you"),),
    "mutate": (("mutate_matters", "you"),),
    "myriad": (("myriad_grant", "you"),),
    "ninjutsu": (("ninjutsu_matters", "you"),),
    "commander ninjutsu": (("ninjutsu_matters", "you"),),
    # Sneak (the TMNT/Marvel ninjutsu-on-a-spell variant — Karai's Technique, Elektra,
    # New Generation's Technique) — the bounce-replay engine that recasts a cheap
    # creature to re-fire its ETB. ADR-0027: the Scryfall `sneak` keyword (28 cards)
    # is the structured detector for recast_etb, dropping the four `\bsneak\b`-regex
    # over-fires (Cheatyface, Lightfoot Rogue, etc.). Ninjutsu proper is the distinct
    # ninjutsu_matters lane above, so recast_etb keys on Sneak specifically.
    # ADR-0027 t2b4a-B: Sneak ALSO anchors the alt_cost_keyword lane (it pays an
    # alternative cost), alongside web-slinging and mayhem below — all three are
    # Scryfall keyword abilities that carry the alternative-cost ability, so the
    # keyword-array membership is exact (no over-fire vs the old `\bsneak\b`-style
    # regex, which risked reminder/flavor false positives). CR 118.9.
    "sneak": (("recast_etb", "you"), ("alt_cost_keyword", "you")),
    # web-slinging (Marvel) / mayhem (alt-cast-from-graveyard) — the other two
    # alternative-cost Scryfall keywords. Spellings match the lowercased Scryfall
    # array ("Web-slinging", "Mayhem"). ADR-0027 t2b4a-B.
    "web-slinging": (("alt_cost_keyword", "you"),),
    "mayhem": (("alt_cost_keyword", "you"),),
    # Partner family (CR 702.124 partner / partner with, 702.123 background,
    # Doctor's companion, Friends forever) — a commander built around a SECOND
    # commander wants the partner-card pool (drives the color-widening avenue,
    # ADR-0019). ADR-0027 t2b4a-B: the Scryfall keyword array carries the whole
    # family cleanly and is MORE precise than the old regex, which over-fired on
    # card-name self-references with a comma ("Lava, Axe", "Gather, the Townsfolk")
    # via its `\bpartner\b`/"friend" arms. Scryfall truncates "Friends forever" to
    # the keyword "Friends". `companion` is the SEPARATE companion_keyword lane (a
    # deckbuild constraint, not partner) — deliberately NOT mapped here.
    "partner": (("partner_background", "you"),),
    "partner with": (("partner_background", "you"),),
    "choose a background": (("partner_background", "you"),),
    "doctor's companion": (("partner_background", "you"),),
    "friends": (("partner_background", "you"),),
    "infect": (("poison_matters", "opponents"),),
    "toxic": (("poison_matters", "opponents"),),
    "poisonous": (("poison_matters", "opponents"),),
    # Saddle (CR 702.171) — moved here from _DIRECT_KEYWORD_SIGNALS for the ADR-0027
    # migration so the keyword detection lives on the IR-only path (the regex
    # `extract_signals` must no longer emit a migrated key); the `saddle` effect
    # marker (project._narrow_mechanic_refs → _DOER_EFFECT_KEYS) covers the
    # keyword-less "becomes saddled" granters.
    "saddle": (("saddle_matters", "you"),),
    # scavenge (CR 702.91) exiles a card from your GY to put that many +1/+1 counters
    # — a +1/+1 source, so it ALSO opens counters_matter (ADR-0027 migration merge).
    "scavenge": (
        ("scavenge_fuel", "you"),
        ("graveyard_matters", "you"),
        ("counters_matter", "any"),
    ),
    # Spectacle (CR 702.111) — "cast cheaper if an opponent lost life this turn" is a
    # life-loss PAYOFF (it cares about opponents having lost life), but the condition
    # lives entirely in reminder text that the structural projection strips, so the IR
    # fires no lose_life. Moved here from _DIRECT_KEYWORD_SIGNALS for the ADR-0027
    # lifeloss_matters migration so the keyword route stays on the IR path (extort /
    # afflict already fire lifeloss STRUCTURALLY and need no keyword entry).
    "spectacle": (("lifeloss_matters", "opponents"),),
    "soulbond": (("soulbond_matters", "you"),),
    "specialize": (("specialize_matters", "you"),),
    "suspend": (("suspend_matters", "you"),),
    # undying (CR 702.92) returns with a +1/+1 counter — a +1/+1 source, so it ALSO
    # opens counters_matter (ADR-0027 migration merge). persist returns with a -1/-1
    # counter (its own minus lane), so it is NOT given counters_matter.
    "undying": (
        ("undying_persist_matters", "you"),
        ("dies_recursion", "you"),
        ("counters_matter", "any"),
    ),
    "persist": (("undying_persist_matters", "you"), ("dies_recursion", "you")),
    "affinity": (("affinity_type", "you"),),
    # Investigate (CR 701.27) IS "create a Clue token" — a colorless ARTIFACT (CR
    # 205.3g). phase tags the keyword but drops the Clue subtype off the make_token
    # subject (the keyword-action's reminder text isn't structured — Deduce, Bygone
    # Bishop, Angelic Sleuth all carry make_token subject=None), so the keyword is the
    # structural anchor that the Clues feed an artifacts deck (affinity / metalcraft /
    # Academy Manufactor). The dedicated clue_matters lane reads investigate off its own
    # regex floor; this opens artifacts_matter, which has no other tell for these.
    "investigate": (("artifacts_matter", "you"),),
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
    # Spell-copy keywords (CR 702.40 storm, 702.108 replicate, 702.78 conspire) —
    # each COPIES the spell, the printed-keyword path for spell_copy_matters that the
    # structural CopySpell effect misses (the copy rides the keyword, not a CopySpell
    # node). Distinct from the deleted regex's `\bstorm\b`, which over-fired on every
    # card NAMED "… Storm" (Comet Storm, Arrow Storm — burn, not the keyword); the
    # Scryfall keyword array carries Storm-the-mechanic only. Casualty is mapped above
    # (it sacs AND copies). CR 702.153.
    "storm": (("spell_copy_matters", "you"),),
    "replicate": (("spell_copy_matters", "you"),),
    "conspire": (("spell_copy_matters", "you"),),
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
    # Batch 16 — recent-set mechanics phase v0.1.60 doesn't structure
    # (rules-lawyer-verified): celebration + coven (ability words, CR 207.2c),
    # outlaw (a creature-type group), plot (CR 702.170), miracle (CR 702.94),
    # lessons (a subtype), kicked (CR 702.33). Narrow word detectors, kept for A4.
    ("celebration_matters", re.compile(r"\bcelebration\b", re.IGNORECASE), "you"),
    ("coven_matters", re.compile(r"\bcoven\b", re.IGNORECASE), "you"),
    ("outlaw_matters", re.compile(r"\boutlaws?\b", re.IGNORECASE), "you"),
    ("lessons_matter", re.compile(r"\blessons?\b", re.IGNORECASE), "you"),
    # snow is a real supertype (CR 205.4), NOT a skip — the analysis workflow
    # wrongly listed it. A snow-matters payoff cares about snow permanents/mana.
    ("snow_matters", re.compile(r"\bsnow\b", re.IGNORECASE), "you"),
    # facedown_matters is a CARES-ABOUT lane: it must fire for face-down PAYOFFS
    # (Ixidor "face-down creatures get +1/+1", Secret Plans, Trail of Mystery), not
    # just the makers (morph/manifest/cloak/disguise). Those payoffs have no
    # structural IR form, so mirror the full same-named sweep regex here for parity
    # (the makers' IR categories + keywords also feed the lane; add() dedups).
    (
        "facedown_matters",
        re.compile(
            r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
            r"|face-?down creatures?|as a 2/2 face-?down"
            r"|turn (?:it|that creature|this creature|them|a permanent you control) "
            r"face up|turn target [^.]*?face up|turned face up this turn",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 — cares-about lanes phase v0.1.19 doesn't structure as a payoff
    # (rules-lawyer-verified: no card-property reference shape in the parse), moved
    # here from _IR_FLOOR_LANES so the lane fires from a dedicated IR-path word mirror
    # instead of the reused production floor Detector (floor-mirror-dep -> 0). Each
    # retains its EXISTING structural bind in extract_signals_ir too (add() dedups):
    #   • devotion_matters  ← amount.op=="devotion" count operand (the scaling payoffs);
    #     this mirror adds the cost-reduction / counterspell-tax / mana forms
    #     ("devotion to <color>") phase doesn't make a count operand. CR 700.5.
    #   • party_matters     ← amount.op=="party" count operand; this mirror adds the
    #     "full party" CONDITION + "creatures in your party" non-count refs. CR 700.6.
    #   • historic_matters  ← the "Historic" subject-Filter predicate; this mirror adds
    #     the cost-reduction / "play a historic" / type-group refs phase leaves textual
    #     (artifacts, legendaries, and Sagas are historic — CR 702.18-style group).
    #   • multicolor / colorless ← the ColorCount subject-Filter predicates (the
    #     "multicolored/colorless <permanent> you control" build-arounds); this mirror
    #     adds the "cast a multicolored spell" TRIGGER + "colorless spell/creature"
    #     cost-reduction / cast-restriction refs that aren't a structured subject.
    #   • initiative_matters / attractions_matter ← recent named designations (CR
    #     720 / 717) phase doesn't structure at all — the word IS the build-around tell.
    ("devotion_matters", re.compile(r"devotion to \w", re.IGNORECASE), "you"),
    (
        "party_matters",
        re.compile(
            r"\byour party\b|members? of your party|full party"
            r"|assemble[^.]*party|creatures? in your party",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("historic_matters", re.compile(r"\bhistoric\b", re.IGNORECASE), "you"),
    (
        "multicolor_matters",
        re.compile(
            r"for each color pair|exactly those colors|cast a multicolored"
            r"|multicolored (?:creature|permanent|spell)s? you",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "colorless_matters",
        re.compile(r"colorless (?:creature|spell|permanent)", re.IGNORECASE),
        "you",
    ),
    ("initiative_matters", re.compile(r"\bthe initiative\b", re.IGNORECASE), "you"),
    (
        "attractions_matter",
        re.compile(r"\battraction\b|open an attraction", re.IGNORECASE),
        "you",
    ),
    # ADR-0027 batch — cares-about / payoff lanes phase v0.1.19 scatters across
    # categories it doesn't unify (a count operand it drops, a trigger flattened to
    # event='other', a grant whose subject it folds), so each fires from a dedicated
    # IR-path word mirror (the deleted regex producer) alongside its EXISTING structural
    # bind (add() dedups). Each mirror reproduces the deleted regex exactly (regex-only
    # residual == 0). rules-lawyer-verified boundaries:
    #   • minus_counters_matter ← place_counter(m1m1) is the maker; the "-1/-1 counter"
    #     references (remove / cost / ward / "with a -1/-1 counter on it" / prevention)
    #     are the cares-about payoffs phase leaves textual (CR 122 / 702.80 Wither).
    #   • exalted_lone_attacker ← the `exalted` keyword is the bearer; "attacks alone"
    #     payoff triggers + "X have exalted" grants are textual (CR 702.83).
    #   • speed_matters ← phase's `speed` doer is the changer; "Start your engines!" /
    #     "max speed" / "your speed" payoffs are unstructured (CR 702.178/702.179).
    #   • tap_untap_matters ← phase's `taps` (tap-for-mana) trigger is structured; the
    #     "becomes tapped/untapped" trigger (Inspired) flattens to event='other'.
    #   • domain_matters ← amount.op=='domain' is the scaler; cost-reduction /
    #     conditions / the "Domain —" ability word are textual (CR 700.3).
    #   • commander_matters ← the IsCommander subject-Filter predicate is structured;
    #     Background grants ("Commander creatures you own have …") + "commander damage"
    #     / "your commander costs less" are textual (CR 903).
    #   • hand_disruption ← the opp-reveal trigger is structured; "look at … hand" /
    #     "play with hands revealed" / modal reveal-and-discard are textual.
    #   • team_evasion_grant ← phase structures the generic creatures-you-control
    #     keyword grant; the subtype/color-scoped grants ("Sliver creatures you control
    #     have flying", "Blue creatures you control can't be blocked") are the broader
    #     team-evasion forms (CR 702.13/702.14/509).
    #   • opponent_exile_matters ← GRAVEYARD HATE (CR 406), scattered across exile/
    #     cheat_play/pump categories phase doesn't unify; the lane is the kept mirror
    #     alone (the old permanent-exile arm mis-fired on Path-to-Exile removal).
    (
        "minus_counters_matter",
        re.compile(r"-1/-1 counter", re.IGNORECASE),
        "you",
    ),
    (
        "exalted_lone_attacker",
        re.compile(r"attacks alone|\bexalted\b", re.IGNORECASE),
        "you",
    ),
    (
        "speed_matters",
        re.compile(r"start your engines|max speed|your speed", re.IGNORECASE),
        "you",
    ),
    (
        "tap_untap_matters",
        re.compile(
            r"whenever [^.]*becomes? (?:tapped|untapped)|becomes? untapped, put",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "domain_matters",
        re.compile(
            r"\bdomain\b|number of basic land types? (?:among|you)"
            r"|basic land types? among",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "commander_matters",
        re.compile(
            r"commanders? you (?:control|own) (?:have|has|get|gets|gain|gains)"
            r"|commander creatures? you (?:own|control)|whenever your commander\b"
            r"|whenever a commander\b"
            r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
            r"|is your commander|it'?s your commander|while [^.]*your commander"
            r"|it's a copy of your other commander|copy of any of your commanders"
            r"|each commander you (?:control|own)|for each commander|commander damage",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "hand_disruption",
        re.compile(
            r"look at (?:target player|that player|an opponent|each opponent"
            r"|target opponent)'?s?'? hands?"
            r"|plays? with (?:their|his or her) hands? revealed"
            r"|reveals? (?:their|his or her) hands?"
            r"|reveals? (?:\w+ )?cards? (?:at random )?from "
            r"(?:their|his or her|that player's) hand"
            r"|reveals?[^.]*until you say stop",
            re.IGNORECASE,
        ),
        "opponents",
    ),
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
    (
        "opponent_exile_matters",
        re.compile(
            r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
            r"|for each card your opponents own in exile|opponents own in exile"
            r"|exile (?:target player's|target opponent's|each opponent's"
            r"|that player's) graveyard"
            r"|if a card would be put into an opponent's graveyard",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # ADR-0027 SWEEP batch — Group B cares-about lanes that phase v0.1.19 leaves
    # TEXTUAL (rules-lawyer + oracle verified): each had a load-bearing floor mirror
    # (floor-mirror-dep > 0 in the commander-legal corpus), so it MOVES from
    # _IR_FLOOR_LANES (a reused production floor Detector) to a dedicated IR-path word
    # mirror here — the sanctioned home (bending / voting / facedown). Each KEEPS its
    # existing structural / keyword IR bind too (add() dedups); the mirror reproduces
    # the deleted _HAND_FLOOR regex exactly (regex-only residual == 0):
    #   • legends_matter ← the HasSupertype:Legendary subject-Filter predicate (the
    #     "whenever a legendary … you control" / count subjects); the mirror adds the
    #     cost-reduction "for each legendary creature you control", "target legendary",
    #     "cast legendary spells", and library-search refs phase leaves textual (CR
    #     205.4a). Two _HAND_FLOOR rows merged.
    #   • lands_matter ← the amount.subject=Land count operand (the structured
    #     scalers); the mirror adds the "P/T equal to the number of lands you control"
    #     (Dakkon / Molimo — phase emits characteristic_pt/pump_target but DROPS the
    #     count operand) and "for each land you control" pumps phase flattens to a bare
    #     effect (CR 305).
    #   • poison_matters ← the infect/toxic/poisonous Scryfall keywords (the bearers);
    #     the mirror adds the GRANTERS ("Enchanted creature has infect", "gains infect",
    #     "All Sliver creatures have poisonous 1") + "poison counter" / "has toxic"
    #     references phase folds into a grant carrier's raw (CR 122 / 702.90 Infect).
    #   • suspend_matters ← the Scryfall `suspend` keyword (the bearers); the mirror
    #     adds the keyword-LESS suspend grants ("It gains suspend", As Foretold) + the
    #     whole time-counter superstructure (time travel CR 701.56, Vanishing 702.63,
    #     Impending) phase doesn't structure as suspend. SWEEP \bsuspend\b folded in.
    (
        "legends_matter",
        re.compile(
            r"search your library for a legendary"
            r"|target legendary (?:creature|permanent)"
            r"|legendary (?:creatures?|permanents?|spells?) you (?:control|cast)"
            r"|(?:number of|other) legendary"
            r"|whenever (?:a|another|one or more) legendary "
            r"(?:permanents?|creatures?)"
            r"[^.]*(?:enters|dies|put into a graveyard|leaves the battlefield"
            r"|you control)"
            r"|whenever you cast a legendary|for each legendary "
            r"(?:creature|permanent)"
            r"|cast legendary|legendary spells?",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "lands_matter",
        re.compile(
            r"(?:the number of|for each) (?:basic )?lands? you control",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "poison_matters",
        re.compile(
            r"poison counters?|\bpoisonous\b|\btoxic\b|\binfect\b", re.IGNORECASE
        ),
        "opponents",
    ),
    (
        "suspend_matters",
        re.compile(
            r"\bsuspend\b|time counter|time travel|\bvanishing\b|\bimpending\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 — exert_matters (the Johan namesake): "attacking doesn't cause
    # creatures you control to tap" neutralizes exert's "won't untap" downside, but
    # phase projects it to a restriction whose clause survives only in raw (no mode
    # token on the Effect), so a kept word mirror covers this single card. The TEAM-
    # vigilance enablers (Heliod, Brave the Sands, Always Watching) are served
    # STRUCTURALLY by the grant_keyword/vigilance arm in extract_signals_ir.
    (
        "exert_matters",
        re.compile(
            r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap", re.IGNORECASE
        ),
        "you",
    ),
    # ADR-0027 counter_manipulation cost tail — the IR recovers the +1/+1/-1/-1
    # MOVE (counter_move) and remove-as-EFFECT (remove_counter) halves structurally,
    # but the remove-as-COST form ("Remove a +1/+1 counter from ~:" — Walking
    # Ballista, Fertilid, Quillspike, Devoted Druid) is an Ability.cost phase leaves
    # in raw, unreachable from the structured IR. This mirror is byte-identical to
    # the deleted SWEEP_DETECTORS row so the hybrid reproduces its firings exactly
    # (A-B==0; the IR additionally catches Graft's counter MOVE). CR 122.1 / 122.6.
    (
        "counter_manipulation",
        re.compile(
            r"(?:remove|move) (?:a|one|any number of|x|\d+) (?:\+1/\+1|-1/-1) "
            r"counters?|(?:remove|move) (?:a|one|any number of|x|\d+) "
            r"[^.]{0,20}?(?:\+1/\+1|-1/-1) counters?",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-C — extra_land_drop tail. The structural arms (cheat_play /
    # topdeck_select with a Land subject) cover the bulk; this YOUR-anchored mirror
    # recovers the cards phase leaves textual: an empty-raw modal Confluence
    # (Riveteers), a cascade-from-exile put (Averna), a library/exile dig phase
    # mis-zoned to to:hand (Aminatou's Augury, Planar Genesis, Journey to the Lost
    # City), and a hand-put phase dropped entirely (Contaminant Grafter). The
    # "from your hand|among them|among those/the exiled cards" source clause EXCLUDES
    # the graveyard-source put (Wreck and Rebuild, Soul of Windgrace), which phase
    # correctly routes to reanimate (a graveyard-lands engine, a different shape) —
    # the deleted regex's broad arm over-matched into that graveyard source. CR 305.9.
    (
        "extra_land_drop",
        re.compile(
            r"you may put (?:a |up to \w+ )?lands? cards? "
            r"from (?:your hand|among them|among those cards"
            r"|among the exiled cards)[^.]*onto the battlefield",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 exile_until_leaves Saga tail — _is_exile_until_leaves recovers the
    # one-ability inline form (raw phrase) and the two-ability O-Ring form
    # structurally, but a SAGA CHAPTER exile collapses its per-effect raw to a
    # "Chapter N" stub (Trial of a Time Lord, Summon: Ixion), losing the inline
    # "until ~ leaves" phrase. The joined-face oracle text still carries it, so this
    # mirror (byte-identical to the deleted SWEEP_DETECTORS row) recovers the tail
    # (A-B==0; the IR additionally catches the linked-return O-Rings — Oblivion Ring,
    # Detention Sphere — the inline regex missed). CR 714.2.
    (
        "exile_until_leaves",
        re.compile(r"exile [^.]*until [^.]*leaves the battlefield", re.IGNORECASE),
        "you",
    ),
    # ADR-0027 tranche2-C — keyword_counter tail. The structural arm (place_counter /
    # remove_counter with a CR-122.1b keyword counter_kind) covers the bulk; this kept
    # mirror reuses the shared KEYWORD_COUNTER_REGEX to recover the choice/multi/quoted-
    # grant cards phase drops counter_kind on ("your choice of a flying OR a hexproof
    # counter" — Wingfold Pteron, T-45 Power Armor, Vivien). scope 'any' (these counter
    # sources appear on either side). CR 122.1b.
    ("keyword_counter", re.compile(KEYWORD_COUNTER_REGEX, re.IGNORECASE), "any"),
    # ADR-0027 keyword_soup tail. The structural arm (>=5 distinct evergreen
    # grant_keyword counter_kinds in one ability) catches the genuine granters
    # (Odric, Akroma's Memorial, Cairn Wanderer). phase parses the "the same is true
    # for X, Y, …" keyword-absorb idiom INCONSISTENTLY — it expands some cards
    # (Cairn Wanderer -> 9 grants) but collapses others to a single flying grant
    # (Indominus Rex, Urborg Scavengers), so this mirror (byte-identical to the
    # deleted SWEEP row) recovers that under-parse tail. A-B==0. CR 702.
    (
        "keyword_soup",
        re.compile(
            r"if it has flying[^.]*first strike"
            r"|the same is true for first strike, double strike"
            r"|has flying[^.]*\+1/\+1",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 land_creatures_matter tail. The structural arms (Land+Creature
    # subject anthems/makers + the animate/base_pt_set/type_set animator) catch the
    # bulk (174 cards, +127 manlands the regex missed), but phase drops some
    # self-animate manland clauses ({cost}: this land becomes a creature) entirely
    # and routes a few animators through non-animate categories (Druid Class's
    # characteristic_pt, Sage of the Maze's restriction). This mirror (byte-identical
    # to the deleted _HAND_FLOOR row) recovers that tail. A-B==0. CR 305 + CR 110.1.
    (
        "land_creatures_matter",
        re.compile(
            r"\bland creatures?\b|lands? you control (?:are|become)\b"
            r"|all lands[^.]*become[^.]*creature"
            r"|target land[^.]*becomes? a[^.]*creature"
            r"|(?:it's|becomes?) a forest land",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 land_protection tail. The structural animator arm catches the
    # mass land-animation commanders, but phase drops the self-animate clause on most
    # manlands (Creeping Tar Pit / Raging Ravine / the Restless lands), so this mirror
    # (byte-identical to the deleted _HAND_FLOOR row) recovers those 17 manlands the
    # structural read misses. A-B==0. CR 305 + CR 110.1.
    (
        "land_protection",
        re.compile(
            r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
            r"|that land becomes",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-B (t2b3-B) — power_tap_engine tail. The structural arm (an
    # ACTIVATED ability cost~'tap' + a power-scaling effect raw) covers the card's OWN
    # engine (Marwyn, Selvala, Staff of Domination). This kept mirror — byte-identical
    # to the deleted _HAND_FLOOR regex — recovers the CONFERRED form, where the
    # power-scaling "{T}: … equal to its power" engine is GRANTED to a creature via a
    # quoted Aura / equipment / one-turn grant (Predatory Urge, Burning Anger, Dragon
    # Throne of Tarkir, Gruesome Slaughter) or rides a DFC back face (Arlinn, Hadana's
    # Climb) — phase folds the granted ability into a grant carrier, losing the
    # Ability.cost='tap' anchor, so it survives only in the joined-face oracle. CR 602.
    (
        "power_tap_engine",
        re.compile(
            r"\{t\}:[^.]*(?:equal to|where x is|x is)[^.]*\bpower\b", re.IGNORECASE
        ),
        "you",
    ),
    # ADR-0027 tranche2-B (t2b3-B) — opponent_cast_matters symmetric-punish tail. The
    # structural arm (a cast_spell trigger scope='opp') covers the explicit "whenever an
    # opponent casts" half (Lavinia, Nekusar). This kept mirror — the deleted
    # _HAND_FLOOR regex with its OVER-BROAD bare "whenever a player casts a spell" arm
    # DROPPED (the IR is more precise than the regex here) — recovers the SYMMETRIC-
    # PUNISHER half, where phase collapses "whenever a player casts" to scope='any'
    # indistinguishable from a self-cast spellslinger payoff. The "that player" / "they
    # lose/discard/sacrifice" punish anchor (the spell's caster punished as a third
    # party — Ruric Thar "6 damage to that player", Mai, Eidolon of the Great Revel,
    # Ash Zealot) is the discriminator that excludes the spellslinger over-fire (Kessig
    # Flamebreather "damage to each opponent", Extort) the bare arm caused. The
    # explicit-opponent arm is kept too for joined-face DFC robustness (add() dedups vs
    # the structural scope='opp' arm). CR 603.2.
    (
        "opponent_cast_matters",
        re.compile(
            r"whenever an opponent casts|whenever an opponent cast"
            r"|whenever (?:a|another) player casts[^.]*(?:(?:they|that player) "
            r"(?:loses?|discards?|sacrifices?)|deals? \d+ damage to that player)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # ADR-0027 tranche2-batch-4 (t2b4-C) — three kept_detector lanes phase v0.1.60
    # CANNOT structure (rules-lawyer / spec verified: the discriminant is DROPPED in
    # the parse), so each fires from a dedicated IR-path word mirror reproducing the
    # deleted SWEEP / _HAND_FLOOR regex EXACTLY (full-text == per-clause over the
    # commander-legal corpus — each regex is clause-safe, A-B==0). floor-mirror-dep == 0
    # by construction (the kept mirror is not a floor detector).
    #   • damage_to_you_punish ← phase captures the deals_damage event but DROPS both
    #     discriminants: the source filter (subject=None, not 'opp') and the player-
    #     recipient ("to you" has no IR field) — event='deals_damage'/scope='any' can't
    #     be told from any "whenever ~ deals damage" trigger. The literal "deals
    #     (combat) damage to you" from an opponent-controlled source is the only tell.
    #   • excess_damage ← the 4 clean "is dealt excess damage" payoffs bind structurally
    #     (a Trigger event=='excess_damage'), but 29/33 references ride an intervening
    #     "if ~ was dealt excess damage" clause on a regular trigger or live in spell
    #     text — phase inlines that into Effect.raw, NOT a structured Condition. This
    #     residual word mirror recovers them. Serve stays serve_keywords=("trample",)
    #     (CR 702.19 enablers).
    #   • tap_down_blockers ← the "can't be blocked unless all creatures defending
    #     player controls block it" clause is 100% DROPPED by phase (Tromokratis's IR
    #     carries only the hexproof grant). No structural shape; the phrase is the tell.
    (
        "damage_to_you_punish",
        re.compile(
            r"whenever a source an opponent controls deals damage to you"
            r"|whenever (?:a|an) (?:opponent|source[^.]*opponent)[^.]*deals "
            r"(?:combat )?damage to you",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    ("excess_damage", re.compile(r"\bexcess damage\b", re.IGNORECASE), "you"),
    (
        "tap_down_blockers",
        re.compile(r"can'?t be blocked unless all", re.IGNORECASE),
        "you",
    ),
    # win_lose_game (ADR-0027 t2b4a-B) — the IR arm reads Effect.category in
    # {win_game, lose_game} (the broad terminal-outcome pool — 54+43 cards, far past
    # the narrow deleted regex). phase loses the outcome on a GRANTED / quoted ability
    # ("create tokens with 'that player loses the game'" — Vraska the Unseen / Vraska,
    # Golgari Queen; Frodo's granted "loses the game if the Ring tempted you"), folding
    # the quote into the grant carrier so no own-card win_game/lose_game Effect
    # survives. This mirror reproduces the deleted SWEEP regex EXACTLY (scope 'any', the
    # row's behavior-neutral choice — it matched both self-wins and player-losses)
    # so those conferred-ability cards keep firing. CR 104.2.
    (
        "win_lose_game",
        re.compile(
            r"you win the game|(?:that player|each opponent"
            r"|target (?:player|opponent)) loses the game",
            re.IGNORECASE,
        ),
        "any",
    ),
    # curse_matters cares-about (ADR-0027 t2b4a-B) — the IR arm reads Filter.subtypes
    # =='Curse' on a trigger/effect subject (Lynde, Bitterheart Witch, Witchbane Orb),
    # but phase under-parses a "search your library for a Curse card that doesn't have
    # the same name as …" subject (Curse of Misfortunes) so no Curse Filter survives.
    # This mirror reproduces the deleted cares-about regex EXACTLY (anchored on Curse-
    # as-a-mechanic — "a/target/each/another/your Curse", "Curse spells/cards",
    # "Curses you cast/control/own" — so a bare card NAME "Connors's Curse" never
    # qualifies; CR 205.3 / 702.39 Aura — Curse). The membership half (a card that IS
    # a Curse) stays REGEX-ONLY at A4 like TYPE_MATTERS membership — the regex never
    # fired it, so the type_line subtype read is deferred to avoid a 42-card flood.
    (
        "curse_matters",
        re.compile(
            r"curse spells?|curses? you (?:cast|control|own)"
            r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector lanes phase v0.1.60 CANNOT
    # structure (rules-lawyer / spec verified: the discriminant is un-CR digital
    # vocabulary, a per-mode target-legality constraint, an inconsistently-parsed
    # Kamigawa flip, a cost-rewrite phase doesn't model, or a grant-direction phase
    # folds into a carrier). Each fires from a dedicated IR-path WORD MIRROR
    # reproducing the deleted SWEEP / _HAND_FLOOR regex EXACTLY (the mirror reads the
    # joined-face oracle, so it is byte-identical — A-B==0). floor-mirror-dep == 0 by
    # construction (none is a floor detector).
    #   • draft_spellbook ← Arena/Alchemy digital mechanics (draft-a-card / spellbook)
    #     NOT in the CR with NO phase effect category (phase leaves them
    #     category='other'). The literal phrasing is the only signal; all matching
    #     cards are games:['arena'], so the lane is correctly inert in paper formats.
    #   • each_mode_player ← phase captures the modal head (Effect.category=='choose')
    #     but has NO field for the spread-the-modes CONSTRAINT; a bare 'choose' marker
    #     over-fires 1364:8 (every modal card). The literal phrase is the discriminator.
    #   • flip_self ← phase parses the Kamigawa flip (CR 710) INCONSISTENTLY (transform
    #     / reanimate / buried in raw), so no single structured category is reliable;
    #     "flip this creature" is a coined term on exactly the 7 flip creatures.
    #   • free_plot ← no IR structure for the Plot alt-cost rewrite (phase routes
    #     Fblthp's plot-cost clause to a subjectless topdeck_select). The phrase is
    #     literally unique to one card (Fblthp, Lost on the Range) — zero over-fire.
    #     (NB: the broad "\bplot\b" the old DEFERRED note warned against is NOT this
    #     producer — the _HAND_FLOOR regex was already the tight unique-phrase form.)
    #   • miracle_grant ← a card that GRANTS miracle to OTHER cards in hand; phase folds
    #     the grant into a carrier (category grant_keyword/other). The "cards/spells in
    #     your hand have/has miracle" phrasing is the granting DIRECTION (an intrinsic
    #     miracle card carries a "Miracle {cost}" keyword line, so the mirror excludes
    #     it). CR 702.94.
    (
        "draft_spellbook",
        re.compile(r"\bdraft a card\b|spellbook", re.IGNORECASE),
        "you",
    ),
    (
        "each_mode_player",
        re.compile(r"each mode must target a different player", re.IGNORECASE),
        "each",
    ),
    ("flip_self", re.compile(r"\bflip this creature\b", re.IGNORECASE), "you"),
    (
        "free_plot",
        re.compile(r"plot cost is equal to its mana cost", re.IGNORECASE),
        "you",
    ),
    (
        "miracle_grant",
        re.compile(
            r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B) — five kept_detector lanes phase v0.1.60
    # CANNOT structure (spec / rules-lawyer verified: the discriminant is DROPPED in
    # the parse — a cost-reduction-per-target operand, a protective-vs-stax restriction
    # split, the out-of-game zone, or a becomes-target trigger flattened to
    # event='other'). Each fires from a dedicated IR-path word mirror reproducing the
    # deleted _HAND_FLOOR / SWEEP regex (the secret_writedown mirror INTENTIONALLY
    # drops the deleted regex's "|your sideboard" arm — companion reminder text owned
    # by companion_keyword, not a wishboard build-around — so it is a NARROWER, correct
    # A-B, not a regression). floor-mirror-dep == 0 by construction (none is a floor
    # detector). All scope 'you'.
    #   • per_target_payoff   ← Hinata's YOUR-arm cost reduction scaling with target
    #     count; the IR has no mana_cost / cost-reduction model and no per-spell
    #     target-count operand, so the arm is dropped entirely (CR 601 / 118).
    #   • sacrifice_protection ← phase parses only ~21/39 as a generic restriction
    #     (indistinguishable from a STAX restriction — Ghostly Prison) and drops ~18/39
    #     buried in a quoted/granted ability; the two literal protective phrases are
    #     the only full-coverage tell (CR 701.16).
    #   • secret_writedown    ← the out-of-game zone (CR 408.1 Wish) + pre-game secret
    #     name/choose; phase's in-game battlefield IR models neither.
    #   • target_own_payoff   ← Monk Gyatso's becomes-target may-reaction on YOUR
    #     creatures; the becomes-target event flattens to event='other' (no
    #     becomestarget trigger mode), so the may-clause survives only in raw.
    #   • target_redirect     ← Rayne's becomes-target-of-opponent → draw payoff;
    #     same event='other' flattening (the redirect SERVE pool is structural via
    #     category=='redirect' but the DETECTION payoff is not). CR 603.
    (
        "per_target_payoff",
        re.compile(r"less (?:to cast )?for each (?:of those )?target", re.IGNORECASE),
        "you",
    ),
    (
        "sacrifice_protection",
        re.compile(r"can't cause you to sacrifice|can't be sacrificed", re.IGNORECASE),
        "you",
    ),
    (
        "secret_writedown",
        re.compile(
            r"secretly (?:write|choose|name)"
            r"|before the game begins[^.]*(?:write|name|choose)"
            r"|from outside the game",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "target_own_payoff",
        re.compile(
            r"creature you control becomes the target[^.]*you may", re.IGNORECASE
        ),
        "you",
    ),
    (
        "target_redirect",
        re.compile(
            r"becomes? the target of a spell or ability an opponent controls[^.]*draw",
            re.IGNORECASE,
        ),
        "you",
    ),
    # DEFERRED: kicked_spell_matters (\bkicked\b matches every "if kicked" card,
    # +171 — the lane is the PAYOFF "whenever you cast a kicked spell", not having
    # kicker). Needs a narrower payoff/keyword source.
    # DEFERRED: legend_rule_off — phase's `legend_exempt` Effect is a strict SUBSET
    # of the regex (2 of 8: only the unbounded "the legend rule doesn't apply" —
    # Mirror Gallery, Brothers Yamazaki). The bounded-scope variant ("doesn't apply
    # to permanents/tokens/Slivers/Spiders you control" — Mirror Box, Cadric, Sliver
    # Gravemother, Spider-Verse, The Master, Sakashima) is DROPPED by phase, so 6 of 8
    # cards' recall lives only in the regex. Needs a supplement.py extension anchoring
    # the "doesn't apply to … you control" form before this can migrate. CR 704.5j.
)

# Cares-about floor lanes the IR path also runs. A `<mechanic>_matters` lane means
# "this card cares about / combos with X", so it must fire for PAYOFFS, not just the
# doers — and those payoffs are textual references with no structural IR form (Ixidor
# "face-down creatures get +1/+1", a Clue payoff, "creatures you control with a
# counter"). So reuse the production floor Detector objects for this CURATED subset
# (the facedown_matters fix, generalized — see feedback memory). DELIBERATELY EXCLUDES
# the broad foundational / doer lanes (graveyard/counters/removal/pump/ramp/draw/…):
# their regex-only is genuine IR-STRUCTURING work the signal_diff harness must keep
# surfacing, not textual cares-about gaps. add() dedups overlap with IR categories.
_IR_FLOOR_LANES: frozenset[str] = frozenset(
    {
        # token-type synergy
        "clue_matters",
        # food_matters / treasure_matters removed — ADR-0027 migrated them to the Card
        # IR (the generalized blood_matters widening: Food/Treasure-subtype make_token
        # makers incl. the die-roll/vote/choice branch + Aftermath-DFC recovery, a
        # "Sacrifice a Food/Treasure" SAC PAYOFF, and a `token_subtype_ref` "Foods/
        # Treasures you control" cares-about marker). Removed from _IR_FLOOR_LANES;
        # floor-mirror-dep == 0. Their _HAND_FLOOR detectors are deleted; serve specs
        # survive. clue_matters keeps its floor (its "investigate" arm has no structural
        # IR form yet).
        # blood_matters removed — ADR-0027 migrated it to the Card IR (Blood-subtype
        # makers + the sacrifice-Effect/Trigger subject widening + the choose-list /
        # granted-ability maker recovery), so it fires from the STRUCTURAL IR alone
        # and no longer needs the floor mirror. Its _HAND_FLOOR detector is deleted.
        # counter-type synergy (distinct from the +1/+1 counters_matter doer lane)
        # poison_matters removed — ADR-0027 migrated it to the Card IR (the
        # infect/toxic/poisonous Scryfall keywords + a kept word mirror for the
        # GRANTERS / "poison counter" / "has toxic" refs phase folds into a grant
        # carrier's raw). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
        # oil_counter_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # place_counter(counter_kind='oil') placer + an `_OIL_REF` payoff marker for the
        # count-operand/condition phase drops). Its SWEEP_DETECTORS row is deleted.
        "shield_counter_matters",
        # rad_counter_matters removed — ADR-0027 migrated it to the Card IR (the
        # `rad_counter` effect / rad place_counter + a "rad counter(s)" face marker).
        # resource / devotion
        # energy_matters removed — ADR-0027 migrated it to the Card IR (phase's `energy`
        # effect + a {e} face marker for the sinks/payoffs/doublers phase loses).
        # devotion_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="devotion" count operand + a "devotion to <color>" kept word
        # mirror for the cost-reduction / counterspell-tax forms phase doesn't make a
        # count operand). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR gone.
        # type / tribe / permanent-shape synergy
        "vehicles_matter",
        "island_matters",
        # legends_matter removed — ADR-0027 migrated it to the Card IR (the
        # HasSupertype:Legendary subject-Filter predicate + a kept word mirror merging
        # both _HAND_FLOOR rows for the cost-reduction / target-legendary / cast-
        # legendary / search refs phase leaves textual). Moved floor->kept (floor-
        # mirror-dep -> 0); both _HAND_FLOOR producers deleted.
        # changeling_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # changeling keyword + a "changeling" / "is every creature type" marker). Its
        # SWEEP_DETECTORS row is deleted.
        # colorless_matters / multicolor_matters removed — ADR-0027 migrated them to the
        # Card IR (the ColorCount subject-Filter predicate build-arounds +
        # _IR_KEPT_DETECTORS word mirrors for the "cast a multicolored spell" trigger /
        # "colorless spell/creature" cost-reduction refs that aren't a structured
        # subject). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR rows deleted.
        # lands_matter removed — ADR-0027 migrated it to the Card IR (the
        # amount.subject=Land count operand + a kept word mirror for the "P/T equal to
        # the number of lands you control" / "for each land you control" forms phase
        # emits as characteristic_pt/pump_target but DROPS the count operand). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        "superfriends_matters",
        "modified_matters",
        # low_power_matters removed — ADR-0027 migrated it to the Card IR (the
        # Power:LE/LT predicate read + a `_LOW_POWER_REF` marker rebuilding the dropped
        # subject from "creatures you control with power N or less").
        "power_matters",
        # historic_matters removed — ADR-0027 migrated it to the Card IR (the
        # "Historic" subject-Filter predicate + a "\bhistoric\b" kept word mirror for
        # the cost-reduction / "play a historic" / type-group refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # domain_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="domain" count operand + a "\bdomain\b|basic land types" kept word
        # mirror for the cost-reduction / condition / ability-word refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # party_matters removed — ADR-0027 migrated it to the Card IR (the
        # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
        # "full party" CONDITION + "creatures in your party" non-count refs). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # commander_matters removed — ADR-0027 migrated it to the Card IR (the
        # IsCommander subject-Filter predicate + a kept word mirror for the Background
        # grants / "commander damage" / "your commander costs less" refs phase leaves
        # textual). Moved floor->kept (floor-mirror-dep -> 0); SWEEP row deleted.
        # mechanic / keyword synergy
        "arcane_matters",
        "daynight_matters",
        # saga_matters removed — ADR-0027 migrated it to the Card IR (a `_SAGA_REF`
        # "lore counter" / "Saga you control" dropped-static face marker; the reminder-
        # stripped anchor excludes a vanilla Saga's intrinsic advancement, mirroring the
        # deleted SWEEP regex). Its SWEEP_DETECTORS row is deleted.
        # initiative_matters removed — ADR-0027 migrated it to the Card IR (a
        # "\bthe initiative\b" _IR_KEPT_DETECTORS word mirror; phase v0.1.19 doesn't
        # structure the CR 720 initiative designation). Moved floor->kept
        # (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        # cycling_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `cycled` trigger + a `cycling_payoff` marker for the "cycle or discard" payoff
        # phase flattens to event='other' or truncates the trigger off entirely). Its
        # _HAND_FLOOR detector is deleted.
        "station_matters",
        "void_warp_matters",
        # speed_matters removed — ADR-0027 migrated it to the Card IR (phase's `speed`
        # doer + a "start your engines|max speed|your speed" kept word mirror; phase
        # v0.1.19 doesn't structure the CR 702.178/702.179 Speed designation). Moved
        # floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR row deleted.
        "stickers_matter",
        # attractions_matter removed — ADR-0027 migrated it to the Card IR (a
        # "\battraction\b|open an attraction" kept word mirror; phase v0.1.19 doesn't
        # structure the CR 717 Attraction designation). Moved floor->kept
        # (floor-mirror-dep -> 0); its SWEEP_DETECTORS row is deleted (serve stays).
        # suspect_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `suspect` effect + a verb/"suspected" face marker; the marker's "(?! counter)"
        # excludes Investigator's Journal's "suspect counter" same-named counter type).
        # venture_matters removed — ADR-0027 migrated it to the Card IR (the venture/
        # take-initiative effect + a completedadungeon/isinitiative condition read +
        # a trigger_doubling-over-dungeons read + a venture/complete-a-dungeon marker).
        # foretell_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # foretell keyword + the "has foretell"/"you foretell" marker, plus the
        # Foretold-predicate payoff bind (Niko) and the "to foretell" enabler marker
        # (Karfell)), so it no longer needs the regex floor (its _HAND_FLOOR detector
        # is deleted).
        # phasing_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # phasing keyword + the phase-out/in DOER markers, plus the event='other'
        # "permanents phase out" payoff-trigger marker (The War Doctor)), so it no
        # longer needs the regex floor (its SWEEP_DETECTORS row is deleted).
        # ring_matters removed — ADR-0027 migrated it to the Card IR (structural
        # ring_tempt effect, including the event='other' tempt trigger + the
        # Ring-bearer raw-scan), so it no longer needs the regex floor (its
        # _HAND_FLOOR detector is deleted).
        # convoke_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # convoke keyword + cast_with_keyword counter_kind='convoke' granters +
        # grant_spell_ability/cast-trigger convoke-raw markers), so it no longer needs
        # the regex floor (its SWEEP_DETECTORS row is deleted).
        # affinity_type removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # affinity keyword + an `affinity` marker effect for the conferred "spells you
        # cast have affinity for X" granters), so it no longer needs the regex floor
        # (its SWEEP_DETECTORS row is deleted).
        # cascade_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # cascade keyword + a `_CASCADE_GRANT` conferral/reference marker). Its
        # _HAND_FLOOR detector is deleted.
        # undying_persist_matters removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall undying/persist keywords + a `_UNDYING_PERSIST_GRANT` grant marker);
        # the "\bundying\b" floor over-fired on the "Undying Flames" card NAME, which
        # the structural IR correctly drops. Its _HAND_FLOOR detector is deleted.
        # myriad_grant removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # myriad keyword + grant_keyword counter_kind='myriad' granters + a copy-
        # exception conferred marker), so it no longer needs the regex floor (its
        # SWEEP_DETECTORS row is deleted; the "\bmyriad\b" floor over-fired on the
        # "The Myriad Pools" card NAME, which the IR correctly drops).
        # suspend_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # `suspend` keyword + a kept word mirror folding in the SWEEP \bsuspend\b and
        # widening to the time-counter superstructure — time travel / Vanishing /
        # Impending — phase doesn't structure). Moved floor->kept (floor-mirror-dep
        # -> 0); _HAND_FLOOR row + SWEEP_DETECTORS \bsuspend\b row deleted.
        # monarch_matters removed — ADR-0027 migrated it to the Card IR (structural
        # monarch effect + ismonarch condition), so it no longer needs the regex
        # floor (its _HAND_FLOOR detector is deleted).
        # madness_matters removed — ADR-0027 migrated it to the Card IR (the Scryfall
        # madness keyword + the "has madness" grant marker + the "if it has madness"
        # payoff marker (Anje)); the "\bmadness\b" floor over-fired on the "Crown of
        # Madness" ability word (CR 207.2c — Bloodboil Sorcerer), which the structural
        # IR correctly excludes. Its _HAND_FLOOR detector is deleted.
        # dice_matters removed — ADR-0027 migrated it to the Card IR (phase's native
        # roll_die effect + a `roll_die` marker for the "whenever you roll" payoff
        # trigger / "Roll two d6 and choose" spell / "Roll a d8:" cost / "reroll" phase
        # keeps only in raw). Its _HAND_FLOOR + SWEEP_DETECTORS rows are deleted.
        # exalted_lone_attacker removed — ADR-0027 migrated it to the Card IR (the
        # Scryfall `exalted` keyword + an "attacks alone|\bexalted\b" kept word mirror
        # for the attacks-alone payoff triggers + "X have exalted" grants phase leaves
        # textual; CR 702.83). Moved floor->kept (floor-mirror-dep -> 0); _HAND_FLOOR
        # row deleted.
        # crimes_matter removed — ADR-0027 migrated it to the Card IR (phase's
        # commit_crime trigger event + a `crime` condition-form marker for the
        # "(if|as long as) you've committed a crime" payoff phase has no kind for).
        # scry_surveil_matters removed — ADR-0027 migrated it to the Card IR (the
        # scried/surveiled trigger events + the event='other' scry/surveil payoff
        # marker, plus the "if you would scry a number of cards" replacement marker
        # (Kenessos, Eligeth)), so it no longer needs the regex floor (its _HAND_FLOOR
        # detector is deleted).
        # regenerate_matters removed — ADR-0027 migrated it to the Card IR (phase's
        # `regenerate` effect + a `_REGENERATE_REF` granted/quoted/replacement marker).
        # Its _HAND_FLOOR detector is deleted.
        # spell-pattern / count payoffs
        "second_spell_matters",
        "kicked_spell_matters",
        "big_hand_matters",
        "cast_from_exile",
        "exile_matters",
        # starting_life_matters removed — ADR-0027 migrated it to the Card IR (a
        # `_STARTING_LIFE_REF` "starting life total" compare marker, CR 103.4). The
        # broad regex over-fired on unrelated life thresholds (Elderscale Wurm,
        # Sigarda's Splendor), which the tight IR marker drops. Its SWEEP row is gone.
        "theft_matters",
        # mass_death_payoff removed — ADR-0027 migrated it to the Card IR (a
        # `_MASS_DEATH_REF` "creatures that died this turn" count-operand marker). Its
        # _HAND_FLOOR detector is deleted.
        "noncombat_damage_payoff",
        "land_sacrifice_matters",
    }
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
            "commander_matters",  # Batch 15
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
            # Batch 16 — recent-set kept-detectors (rules-lawyer-verified):
            "celebration_matters",
            "coven_matters",
            "outlaw_matters",
            "lessons_matter",
            "snow_matters",  # Batch 18 — real (CR 205.4), not a skip
            # Batch 8 — named scaling-operand lanes:
            "devotion_matters",
            "party_matters",
            "domain_matters",
            # Batch 11 — opponent-draw punisher (player-event scope):
            "opponent_draw_matters",
            # Batch 6 — grant_keyword team-anthem lanes (gated; flash_grant deferred):
            "team_evasion_grant",
            "protection_grant",
            "all_creatures_kw_grant",
            # Batch 2 (per-lane) — discard OUTLET cost (self-discard split out):
            "discard_outlet",
            # Batch 2 (per-lane) — top-of-library stacking (position-gated):
            "topdeck_stack",
            # Batch 5 — predicate-enriched color/power build-around lanes:
            "multicolor_matters",
            "colorless_matters",
            "power_matters",
            "low_power_matters",
            "color_hoser",
            # Batch 12 — negation/disjunction composite-filter lanes
            # (noncreature_cast_punish DEFERRED — phase scope can't split it from
            # prowess; see the cast_spell arm):
            "nonhuman_attackers",
            "typed_anthem_multi",
            # Batch 13 — combat-forcing statics (split out of stax):
            "forced_attack",
            "cant_block_grant",
            "lure_matters",
            # Batch 17 — DoubleTriggers static (Yarok / Panharmonicon):
            "trigger_doubling",
            # Batch 6 (unblocked) — flash_grant via CastWithKeyword{Flash}:
            "flash_grant",
            # Batch 5 (unblocked) — named-permanent via deck_copy_limit:
            "named_permanent",
            # Deferred-sweep: evasion-denial (IgnoreLandwalk); clone_matters still
            # deferred (regex 1611 vs IR 70 — needs the 1541 audited first):
            "evasion_denial",
            "base_pt_set",
            # Co-occurrence lanes (trigger + effect in one ability):
            "combat_buff_engine",
            "damage_reflect",
            # Clone hierarchy: creature-copy (clone_matters) + per-permanent-type
            # copy lanes (a Permanent copy fans out to all of these + copy_permanent):
            "clone_matters",
            "copy_artifact",
            "copy_enchantment",
            "copy_land",
            "copy_planeswalker",
            "copy_permanent",
            # Spell-copy (Twincast/Fork) — separate from clone:
            "spell_copy_matters",
            # ADR-0027 tranche2-C — structural IR-arm lanes (recast_etb also rides
            # the Scryfall `sneak` keyword via _IR_KEYWORD_KEYS):
            #   exert_matters   ← grant_keyword/vigilance over a generic creature board
            #                     (the team-vigilance enabler) + the Johan kept mirror.
            #   self_pump       ← an ACTIVATED pump_target / place_counter(p1p1) on the
            #                     self (firebreathing / Walking Ballista mana sink).
            #   tapper_engine   ← a tap Effect with a target subject + a "doesn't
            #                     untap" restriction raw (the repeatable tapper).
            #   count_anthem    ← a team +N/+N anthem scaling with a board count
            #                     (Hold the Gates / Commander's Insignia).
            "exert_matters",
            "self_pump",
            "tapper_engine",
            "count_anthem",
            # ADR-0027 tranche2 (t2b2-A) — structural grant/bounce/exile IR arms:
            #   aura_equip_kw_grant   ← grant_keyword of an evergreen kw over a YOUR
            #                           Aura/Equipment subgroup subject (Rashel).
            #   counter_grants_kw     ← grant_keyword over a YOUR-creature subject with
            #                           the `Counters` predicate (Bramblewood Paragon).
            #   conditional_self_protection ← a STATIC ability with a condition
            #                           granting a protective kw to ITSELF (Ojutai,
            #                           Zurgo, Kaito).
            #   control_exchange      ← exile a YOU-OWN subject paired with a
            #                           to:battlefield return (Meneldor, Neutrinos,
            #                           Aminatou) — inverse of the exile_removal Owned
            #                           exclusion.
            #   bounce_tempo          ← a `bounce` Effect, no graveyard zone, subject
            #                           not controller='you' (Boomerang…Cyclonic Rift).
            "aura_equip_kw_grant",
            "counter_grants_kw",
            "conditional_self_protection",
            "control_exchange",
            "bounce_tempo",
            # ADR-0027 tranche2-B (counters / O-Ring lanes):
            #   counter_manipulation ← counter_move/remove_counter effect (p1p1/m1m1)
            #                          + a kept cost-clause word mirror.
            #   counter_place_trigger ← a counter_added TRIGGER (scope!=opp, non-Saga).
            #   counter_replace_bonus ← the counter_doubling replacement category
            #                           (+ the place_counter(plus) temporary tail).
            #   exile_until_leaves   ← _is_exile_until_leaves (inline phrase OR the
            #                          two-ability linked-return shape) + Saga mirror.
            "counter_manipulation",
            "counter_place_trigger",
            "counter_replace_bonus",
            "exile_until_leaves",
            # ADR-0027 tranche2-C (batch C) — structural IR-arm lanes:
            #   extra_land_drop      ← cheat_play / topdeck_select with a Land subject
            #                          + a YOUR-anchored kept word mirror.
            #   free_creature_payoff ← an ETB trigger whose condition tree carries a
            #                          manaspentcondition (Satoru the Infiltrator).
            #   keyword_counter      ← a place/remove of a CR-122.1b keyword counter
            #                          + a kept word mirror for the choice/multi tail.
            "extra_land_drop",
            "free_creature_payoff",
            "keyword_counter",
            # ADR-0027 tranche2-batch-3-A — land-animation + keyword-soup lanes:
            #   land_denial          ← phasing Effect, Land/you subject (Taniwha).
            #   keyword_soup         ← >=5 distinct evergreen grant_keyword cks/ability
            #                          + a kept oracle mirror for the under-parse tail.
            #   land_creatures_matter / land_protection ← the shared land-animator
            #                          predicate + Land+Creature anthem/maker subjects
            #                          + a kept oracle mirror for the dropped manlands.
            "land_denial",
            "keyword_soup",
            "land_creatures_matter",
            "land_protection",
            # ADR-0027 tranche2-B-3 (batch C) — structural IR-arm lanes:
            #   spell_keyword_grant  ← the whole cast_with_keyword category (umbrella
            #                          over flash_grant / convoke_matters).
            #   target_player_draws  ← a draw effect with scope=='any' (directed/forced
            #                          draw, not a self-cantrip).
            # (self_counter_grow / timing_control / token_copy_matters were DEFERRED —
            # each has a genuine floor-disabled IR-vs-regex recall gap, not 100%
            # over-fire: self_counter_grow drops 14 subjNone p1p1 placements whose raw
            # lacks the self-anchor (Saga chapters, adapt/monstrosity); timing_control
            # drops the 2 Teferi cast-timing statics phase doesn't parse; token_copy_
            # matters drops 54 populate/copy cards phase rewrites without "copy of".)
            "spell_keyword_grant",
            "target_player_draws",
            # ADR-0027 tranche2-B (t2b3-B) — structural IR-arm lanes:
            #   lose_unless_hand       ← an etb trigger scope=you + a lose_game effect
            #                            (Phage the Untouchable).
            #   opponent_cast_matters  ← a cast_spell trigger scope=opp OR a symmetric
            #                            scope=any/each cast trigger with a punish
            #                            co-effect (Ruric Thar, Mai, Lavinia).
            #   opponent_counter_grant ← a place_counter(bounty/stun) on an opponent's
            #                            permanent — direct opp subject or a co-tap
            #                            effect carrying the opp filter (Mathas, Freeze
            #                            in Place).
            #   power_tap_engine       ← an ACTIVATED ability cost~'tap' + a power-
            #                            scaling effect raw (Marwyn, Selvala, Staff of
            #                            Domination).
            # pump_matters is DEFERRED (needs-projection — the IR pump/pump_target
            # categories flood with -1/-1 debuffs, self-firebreathing, and conditional
            # self-buffs the narrow positive-single-target regex never caught).
            "lose_unless_hand",
            "opponent_cast_matters",
            "opponent_counter_grant",
            "power_tap_engine",
            # ADR-0027 tranche2-batch-4 (t2b4-C) — kept_detector lanes phase v0.1.60
            # cannot structure, each fired from a dedicated IR-path word mirror (the
            # exact deleted regex):
            #   damage_to_you_punish / excess_damage / tap_down_blockers ← flat
            #     _IR_KEPT_DETECTORS rows (clause-safe full-text mirrors).
            #   self_blink ← name-aware _detect_self_blink_fulltext + the
            #     _SELF_BLINK_SWEEP_RE single-target regex run per-clause (both
            #     reproduced byte-identically; no clean structural IR form).
            #   type_change ← the _type_hoser_clause subtype-gated word detector over
            #     the joined oracle (phase drops the protection subtype argument).
            "damage_to_you_punish",
            "excess_damage",
            "self_blink",
            "tap_down_blockers",
            "type_change",
            # ADR-0027 tranche2-batch-4 (t2b4a-A) — structural ETB / predicate arms:
            #   tribal_etb_multi ← an etb trigger with a creature-subtype subject.
            #   typed_enters_punish ← an etb trigger whose consequence burns opponents.
            #   vanilla_matters ← the HasNoAbilities subject-Filter predicate.
            "tribal_etb_multi",
            "typed_enters_punish",
            "vanilla_matters",
            # ADR-0027 tranche2-batch-4a (t2b4a-B) — two structural keys
            # (alt_cost_keyword + partner_background ride _IR_KEYWORD_KEYS below):
            #   win_lose_game  ← win_game/lose_game Effect categories + a kept regex
            #     mirror (scope 'any') for the conferred/quoted-ability tail.
            #   xspell_matters ← HasXInManaCost predicate on a cast_spell trigger
            #     subject + a kept effect-raw hook mirror for the dropped-predicate
            #     tail.
            #   curse_matters  ← a trigger/effect subject Filter subtypes=='Curse' +
            #     a kept regex mirror for the "search for a Curse card" under-parse.
            "win_lose_game",
            "xspell_matters",
            "curse_matters",
            # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector lanes phase v0.1.60
            # cannot structure, each fired from a dedicated IR-path word mirror (the
            # exact deleted SWEEP / _HAND_FLOOR regex; the mirror reads the joined-face
            # oracle, so it is byte-identical — A-B==0):
            #   draft_spellbook ← un-CR digital mechanics (draft-a-card / spellbook).
            #   each_mode_player ← the spread-the-modes target-legality constraint phase
            #     drops (a bare 'choose' marker over-fires 1364:8).
            #   flip_self ← the Kamigawa flip phase parses inconsistently.
            #   free_plot ← the Plot alt-cost rewrite (phrase unique to Fblthp).
            #   miracle_grant ← a card that GRANTS miracle to other cards in hand.
            "draft_spellbook",
            "each_mode_player",
            "flip_self",
            "free_plot",
            "miracle_grant",
            # ADR-0027 tranche2-batch-5 (t2b5-B) — kept_detector lanes phase v0.1.60
            # cannot structure; each fires from a dedicated _IR_KEPT_DETECTORS word
            # mirror (the exact deleted regex; secret_writedown drops the companion
            # "your sideboard" arm):
            #   per_target_payoff / sacrifice_protection / secret_writedown /
            #   target_own_payoff / target_redirect.
            "per_target_payoff",
            "sacrifice_protection",
            "secret_writedown",
            "target_own_payoff",
            "target_redirect",
        }
    )
    # Batch 2a (keyword-array signals — same source as regex, full parity):
    | _IR_KEYWORD_KEYS
    # Cares-about floor lanes the IR path now mirrors from production (synergy
    # payoffs with no structural form) — track their convergence in the harness:
    | _IR_FLOOR_LANES
    # Batch 2b/2c (effect-doer + trigger-payoff lanes):
    | frozenset(key for key, _scope in _DOER_EFFECT_KEYS.values())
    | frozenset(key for key, _scope in _PAYOFF_TRIGGER_KEYS.values())
)

# IR scope vocab ("opp") → Signal scope vocab ("opponents").
_IR_TO_SIGNAL_SCOPE = {"you": "you", "opp": "opponents", "each": "each", "any": "any"}


def _ir_scope(scope: str) -> str:
    return _IR_TO_SIGNAL_SCOPE.get(scope, "any")


# "Your graveyard" / "this card from … graveyard" (self-recursion) is a self-graveyard
# engine (you); "an opponent's / their / each player's graveyard" is interaction/hate
# (opponents); a bare "a/the graveyard" carries no controller (auto = the structural
# scope). phase scopes a recursion-TARGET effect 'any' (the affected object carries no
# controller) even when the raw says "your graveyard", so the structural scope alone
# under-attributes self-graveyard cards to the 'any' avenue. Mirror the regex producer
# (signals.py "your graveyard"→you, opponent-library-mill→opponents) by reading the
# effect raw FIRST, falling back to the structural scope (ADR-0027 graveyard scope
# fidelity). CR 400.7 — a graveyard is a player's zone.
_GY_YOUR = re.compile(r"\byour graveyard\b", re.IGNORECASE)
_GY_OPP = re.compile(
    r"\b(?:opponent'?s?|their|each (?:player|opponent)'?s?|that player'?s?"
    r"|target (?:player|opponent)'?s?) graveyard\b",
    re.IGNORECASE,
)


def _gy_scope(e: Effect) -> str:
    """Resolve which player's graveyard an effect cares about (graveyard scope
    fidelity, ADR-0027). 'you' for a "your graveyard" reference (or an already-you
    structural scope); 'opponents' for an opponent's / their / each player's graveyard
    (or a structural opp scope); else the structural scope. A "your graveyard" tell
    wins over a co-mentioned opponent (Araumi's encore tokens "attack that opponent" is
    still a self-graveyard engine), matching the regex's self-first rule."""
    raw = e.raw or ""
    if e.scope == "you" or _GY_YOUR.search(raw):
        return "you"
    if e.scope == "opp" or _GY_OPP.search(raw):
        return "opponents"
    return _ir_scope(e.scope)


def _is_generic_creature_filter(f: object) -> bool:
    """A GENERIC 'creatures you control' filter (no tribe) — the creatures_matter
    anthem/scaling shape. A tribal filter (subtypes set) is type_matters, not this."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and not f.subtypes
        and f.controller == "you"
    )


# ADR-0027 land-animation lanes (land_creatures_matter / land_protection): one
# shared predicate. A Land+Creature dual-type subject is the anthem/maker side
# (Sylvan Advocate's pump, Timber Protector's grant, Jyoti's land-creature token);
# a Land subject under an animate/base_pt_set/type_set effect is the animator side
# (Living Plane, Life and Limb, manlands). phase frequently drops the animate
# subject to None and splits "target land becomes a 0/0 creature" across effects, so
# the subject=None case checks the WHOLE ability's joined raw for a land reference
# (Noyan Dar, Llanowar Loamspeaker) while this effect's raw must say creature/becomes
# (CR 305 land + CR 110.1 creature). Phase outright drops many self-animate manland
# clauses ({cost}: this land becomes a creature) — those ride the kept oracle mirror.
def _has_land_creature_types(f: object) -> bool:
    """A Land+Creature dual-type own-board subject (the anthem/maker shape)."""
    return (
        isinstance(f, Filter) and "Land" in f.card_types and "Creature" in f.card_types
    )


def _is_land_subject(f: object, controllers: tuple[str, ...]) -> bool:
    """A Land subject controlled by one of ``controllers`` (the animator shape)."""
    return (
        isinstance(f, Filter) and "Land" in f.card_types and f.controller in controllers
    )


def _none_animate_land(ab: object, e: object) -> bool:
    """A subject=None animate whose own raw says creature/becomes AND whose ABILITY-
    level raw mentions a land (phase splits the land subject off the animate clause)."""
    if getattr(e, "subject", "") is not None:
        return False
    er = (getattr(e, "raw", "") or "").lower()
    if "becomes" not in er and "creature" not in er:
        return False
    ab_raw = " ".join((x.raw or "") for x in getattr(ab, "effects", ())).lower()
    return bool(re.search(r"\bland", ab_raw))


def _is_land_animator(ab: object, e: object, controllers: tuple[str, ...]) -> bool:
    """An animate/base_pt_set/type_set effect that turns a land into a creature —
    either a Land subject (controllers-gated) or the subject=None raw fallback."""
    return getattr(e, "category", "") in ("animate", "base_pt_set", "type_set") and (
        _is_land_subject(getattr(e, "subject", None), controllers)
        or _none_animate_land(ab, e)
    )


# Permanent-type "matters" lanes whose go-wide DOER is a COUNT operand over your
# permanents of that type ("for each artifact you control", affinity per CR 702.41)
# or a TYPE trigger (cast / enters that type). The count operand is the strongest
# care signal — CR 604.3: the value is determined by that type's population (Nim
# Lasher's power IS the artifact count). Creature is handled separately (it has the
# anthem + token-maker + over-fire boundary the others lack). Scope-gated to YOU —
# a count over an opponent's permanents is not your build-around.
_TYPE_MATTERS_LANE: dict[str, str] = {
    "Artifact": "artifacts_matter",
    "Enchantment": "enchantments_matter",
}


def _generic_board_subject(f: object) -> object:
    """``f`` itself when it is a GENERIC own-board filter (controller you, NO subtypes)
    that includes Artifact or Enchantment — the mass-anthem/grant shape over the whole
    artifact/enchantment board. Else None. The no-subtype gate excludes a subtyped buff
    ("Equipment you control", an Aura-subtype grant) which is a narrower tribal care,
    and a single-target buff (controller 'any'/SelfRef). 'Artifact creatures you
    control have flying' (Workshop Elders) carries ('Creature','Artifact') with no
    subtype, so it passes and fires artifacts_matter (the artifact population is
    buffed); a bare 'creatures you control' buff has no Artifact/Enchantment type, so
    it never leaks into these lanes (it stays creatures_matter)."""
    if (
        isinstance(f, Filter)
        and f.controller == "you"
        and not f.subtypes
        and ("Artifact" in f.card_types or "Enchantment" in f.card_types)
    ):
        return f
    return None


def _typed_matters_lanes(f: object) -> list[str]:
    """The artifacts/enchantments lane(s) for a YOUR-permanents filter, in order. A
    COMPOSITE subject — a count/grant/trigger over the (Artifact AND/OR Enchantment)
    board (Nettlecyst's "for each artifact and/or enchantment you control", Open the
    Vaults, Fountain Watch) — carries BOTH card types, so it fires BOTH lanes (each
    permanent type's population is a care). Excludes Creature (its own go-wide rules)
    and opponent-controlled sets."""
    if not isinstance(f, Filter) or f.controller == "opp":
        return []
    return [
        lane
        for card_type, lane in _TYPE_MATTERS_LANE.items()
        if card_type in f.card_types
    ]


# Predefined ARTIFACT token subtypes (CR 111.10 / 205.3g): Treasure / Clue / Food /
# Powerstone / Gold / Map / Junk / Incubator / Blood / Lander / Mutagen are all
# artifact tokens, so a maker / sac-payoff over one feeds artifacts_matter (affinity,
# metalcraft, Academy Manufactor) even when phase carries only the subtype and drops
# the Artifact card-type (Emissary Green, Giant Opportunity). NOT a bare token go-wide
# subtype (Servo/Thopter artifact CREATURE tokens are a tokens deck — those carry the
# Artifact card-type explicitly, read off card_types, not this subtype set).
_ARTIFACT_TOKEN_SUBTYPES: frozenset[str] = frozenset(
    {
        "treasure",
        "clue",
        "food",
        "powerstone",
        "gold",
        "map",
        "junk",
        "incubator",
        "blood",
        "lander",
        "mutagen",
    }
)


def _is_artifact_subject(f: object) -> bool:
    """True when ``f`` is an Artifact subject — the Artifact card-type, OR an
    artifact-token subtype (Treasure/Clue/Food/…) phase carries with an empty
    card_types tuple. The artifact-token branch fires the artifacts lane off a
    resource-token maker / sac-payoff (CR 205.3g)."""
    if not isinstance(f, Filter):
        return False
    return "Artifact" in f.card_types or bool(
        _fsubs_lower(f) & _ARTIFACT_TOKEN_SUBTYPES
    )


# ── Generalized type-payoff shapes (ADR-0027) ─────────────────────────────────
# A FAMILY of effect-shape detectors that, given an effect over a card-type-filtered
# subject, return the matters-lane(s) the effect is a PAYOFF for. They read only the
# subject's card_types (via _typed_matters_lanes) plus the effect's category/marker,
# so they are type-parameterized — the same shapes transfer to a future
# graveyard/counters/spellcast matters lane by extending _TYPE_MATTERS_LANE. Each
# encodes one settled rules discriminator (see ADR-0027).


def _type_tutor_lanes(e: object) -> list[str]:
    """A TUTOR / DIG of a card-type (CR 701.23) → that type's matters-lane(s).

    A search/dig whose target FILTER is the card type ("search your library for an
    enchantment/artifact card" — Idyllic Tutor, Fabricate; "look at the top N, you may
    put an artifact into your hand" — Glint-Nest Crane) is a build-around enabler for
    that permanent type, so it fires the lane. A COMPOSITE filter ("an artifact OR
    enchantment card" — Enlightened Tutor) fires BOTH lanes.

    GATE (the over-fire boundary): the target filter's ``subtypes == ()``. A SUBTYPE
    tutor ("search for an Aura/Equipment card" — Three Dreams, Steelshaper's Gift,
    Stoneforge Mystic) carries ``subtypes=('Aura'/'Equipment',)`` — that is a NARROWER
    voltron/aura care, not the broad type lane, so it is excluded. A CMC-restricted
    any-of-type tutor (Trophy/Treasure/Tribute Mage — ``subtypes=()`` with a Cmc
    predicate) is STILL an any-artifact tutor, so it fires (correctly — it fetches the
    deck's artifacts). A generic-permanent tutor (Wargate — card_types ('Permanent',))
    carries neither Artifact nor Enchantment, so _typed_matters_lanes returns []."""
    if not isinstance(e, Effect) or e.category not in ("tutor", "topdeck_select"):
        return []
    sub = e.subject
    if not isinstance(sub, Filter) or sub.subtypes:
        return []
    return _typed_matters_lanes(Filter(card_types=sub.card_types, controller="you"))


def _type_recursion_lanes(e: object) -> list[str]:
    """A TYPE-RESTRICTED graveyard recursion of a card-type → that type's lane(s).

    SETTLED RULE (CR 115.1 single-target / 115.10 mass): the discriminator is the
    target FILTER's card-TYPE, NOT mass-vs-single. A reanimate / graveyard-recursion /
    graveyard→hand bounce / graveyard→library recursion whose target is FILTERED to a
    card type fires that type's lane whether it returns ONE ("return target enchantment
    card" — Auramancer, Monk Idealist, Skull of Orm; "return target artifact card" —
    Refurbish, Argivian Archaeologist) or ALL ("return all enchantment cards" — Crystal
    Chimes, Replenish; "return all artifact and enchantment cards" — Open the Vaults,
    Dance of the Manse). Type-gating = only useful in a deck full of that type. A
    COMPOSITE ("artifact OR enchantment card" — Argivian Find, Open the Vaults) fires
    BOTH lanes.

    GATE (the over-fire boundary): the target must be TYPE-restricted. A GENERIC-target
    recursion ("return target card" / "return target permanent card" — Regrowth,
    Eternal Witness, Pull from Eternity) is NOT type-gated, so it fires nothing here. An
    Aura-SUBTYPE recursion ("return target Aura" — Dowsing Shaman) is the narrower
    voltron/aura care, routed to a LOOSE enchantments_matter member (no dedicated Aura
    lane exists). Removal/reset (destroy/exile/counter) is a different category and
    never reaches here."""
    if not isinstance(e, Effect):
        return []
    if e.category not in (
        "reanimate",
        "graveyard_recursion",
        "bounce",
        "cast_from_zone",
        "topdeck_stack",
    ):
        return []
    sub = e.subject
    if not isinstance(sub, Filter) or sub.controller == "opp":
        return []
    # graveyard-sourced only: a battlefield mass bounce (BounceAll board wipe) or a
    # hand/library move is not graveyard recursion of the type as a resource.
    if "from:graveyard" not in e.zones and "in:graveyard" not in e.zones:
        return []
    lanes = _typed_matters_lanes(Filter(card_types=sub.card_types, controller="you"))
    # Aura-SUBTYPE recursion → a loose enchantments_matter member (CR 205.3 — Auras are
    # enchantments), only when no broader card-type lane already fired for it.
    if not lanes and "aura" in _fsubs_lower(sub):
        return ["enchantments_matter"]
    return lanes


# Batch 6 — grant_keyword lanes. The granted keyword rides in Effect.counter_kind.
# Evasion abilities per CR (702.9a flying / 702.13a intimidate / 702.28a shadow /
# 702.31a horsemanship / 702.36a fear / 702.111a menace / 702.118a skulk; landwalk
# is parameterized, not a bare granted keyword). Protective keywords: hexproof
# (702.11) / shroud (702.18) / indestructible (702.12) / ward (702.21) / protection
# (702.16). flash_grant is DEFERRED: flash-granting is CastWithKeyword (a cast-time
# permission), not a battlefield AddKeyword — see deferrals.md.
_EVASION_GRANT_KW: frozenset[str] = frozenset(
    {"flying", "intimidate", "shadow", "horsemanship", "fear", "menace", "skulk"}
)
_PROTECTION_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "shroud", "indestructible", "ward", "protection"}
)


def _is_team_creature_grant(f: object) -> bool:
    """The team-anthem grant shape: GENERIC creatures YOU control, no subtypes AND
    no predicates. The no-predicates gate is what _is_generic_creature_filter lacks
    (it ignores predicates), and it excludes equipment/aura (EquippedBy), conditional
    self-grants (SelfRef), and single targets — the source of the naive +2197 flood."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "you"
        and not f.subtypes
        and not f.predicates
    )


def _is_all_creatures_grant(f: object) -> bool:
    """The SYMMETRIC 'all creatures have X' shape (Concordant Crossroads) — a
    generic creature filter controlled by ANY player (not just yours), no subtypes,
    no predicates. Scope 'any' (the lane's convention) — it is an unscoped global
    grant that buffs opponents' creatures too, not a your-team anthem."""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "any"
        and not f.subtypes
        and not f.predicates
    )


# ADR-0027 team_buff — the full evergreen team-keyword anthem set. team_buff is the
# BROAD union of keyword anthems ("creatures you control have/gain <keyword>"); it
# intentionally overlaps team_evasion_grant (the evasion subset) + protection_grant
# (the protective subset) — the seen-set dedups within a lane. (CR: evergreen
# keyword abilities granted to your whole creature board.)
_TEAM_BUFF_GRANT_KW: frozenset[str] = frozenset(
    {
        "flying",
        "trample",
        "menace",
        "hexproof",
        "indestructible",
        "protection",
        "deathtouch",
        "lifelink",
        "doublestrike",
        "firststrike",
        "vigilance",
        "haste",
        "ward",
        "reach",
    }
)
# Predicates an anthem subject may carry while still being a GENERIC your-team
# anthem (not a tribal / single-target narrowing): Always Watching's "Nontoken
# creatures you control have vigilance" and Tam-style "Each OTHER creature you
# control …" stay in. A subtype (tribal), a HasColor / Attacking / EquippedBy /
# Cmc narrowing, or an opp/single controller fails the gate. (ADR-0027.)
_TEAM_BUFF_OK_PREDS: frozenset[str] = frozenset({"NonToken", "Another", "Other"})


def _is_team_buff_grant(f: object) -> bool:
    """The team_buff anthem shape: GENERIC creatures YOU control (no subtypes) whose
    only predicates are in ``_TEAM_BUFF_OK_PREDS`` (NonToken/Another/Other). Broader
    than ``_is_team_creature_grant`` (which tolerates NO predicates) so the genuine
    Always Watching / "each other creature you control" anthems land — kept SEPARATE
    so relaxing it never perturbs team_evasion_grant / protection_grant. (ADR-0027.)"""
    return (
        isinstance(f, Filter)
        and "Creature" in f.card_types
        and f.controller == "you"
        and not f.subtypes
        and set(f.predicates) <= _TEAM_BUFF_OK_PREDS
    )


# ADR-0027 aura_equip_kw_grant — the evergreen keyword set the deleted regex
# enumerated, normalized to phase's spaceless counter_kind spelling (firststrike /
# doublestrike). The allowlist is the over-fire boundary: it excludes "equip {0}" /
# "crew 1" grants (Syr Gwyn, Puresteel Paladin, Astor), which phase emits as a
# different cost/effect, never grant_keyword of an evergreen keyword. (See ADR-0027.)
_AURA_EQUIP_GRANT_KW: frozenset[str] = frozenset(
    {
        "exalted",
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "vigilance",
        "haste",
        "firststrike",
        "doublestrike",
        "hexproof",
        "ward",
        "menace",
        "reach",
        "indestructible",
    }
)


def _is_aura_equip_grant(f: object) -> bool:
    """The aura/equipment anthem shape: a grant subject that is YOUR Aura or
    Equipment subgroup ("Auras you control have flying", "Equipment you control have
    deathtouch" — Rashel). The subtype tells it apart from a generic team grant
    (_is_team_creature_grant requires NO subtypes, so there's no double-fire), and
    controller=='you' keeps it the player's own subgroup, not a symmetric grant."""
    return (
        isinstance(f, Filter)
        and f.controller == "you"
        and any(st.lower() in ("aura", "equipment") for st in f.subtypes)
    )


# ADR-0027 conditional_self_protection — the PROTECTIVE keyword subset a conditional
# self-grant confers ("during your turn ~ has indestructible", "has hexproof unless
# tapped"). This subset is the over-fire boundary vs an ordinary conditional self
# anthem (a "during your turn ~ has flying/trample" combat buff is NOT protection).
_SELF_PROTECTION_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "indestructible", "protection", "shroud", "ward"}
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
    # NB: lore counters do NOT map here — saga_matters fires from a `saga` marker
    # (project._dropped_static_markers, the "lore counter" / "Saga you control" face
    # reference), NOT every lore placement (a vanilla Saga's intrinsic chapter
    # advancement is not a build-around tell — the reminder is stripped, matching the
    # regex).
}

# keyword_counter (ADR-0027 tranche2-C) — the CLOSED CR-122.1b keyword-counter set:
# a counter that grants a keyword ability via layer 6 (CR 613.1f). phase tags the
# granted keyword KIND directly in Effect.counter_kind on a place_counter /
# remove_counter (verified across the corpus). Distinct from the p1p1/m1m1/charge/oil/
# shield/rad/ki standard counters (those are stat/resource counters, not ability
# grants). DELIBERATELY excludes stun (CR 122.1d) and shield (122.1c) — they create
# REPLACEMENT effects and grant NO keyword — and aegis (not a CR counter). The
# no-space form is phase's emission ('firststrike', 'doublestrike').
_KEYWORD_COUNTER_KINDS: frozenset[str] = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "reach",
        "haste",
        "deathtouch",
        "hexproof",
        "indestructible",
        "lifelink",
        "vigilance",
        "firststrike",
        "doublestrike",
    }
)

# opponent_counter_grant (ADR-0027): counter kinds that BENEFIT the recipient, so a
# placement on an opponent's permanent is the WRONG direction for the detrimental-mark
# punish lane — exclude them. p1p1 (a +1/+1 buff — Hunter of Eyeblights places one to
# enable its own counter-removal, not to punish), shield (a damage-soak), and every
# keyword counter (flying/indestructible/… — CR 122.1b grants an ability) all help the
# opponent. Everything else placed on an opponent (bounty/stun/m1m1/slime/bribery/
# rejection/…) is a detrimental mark. CR 122.1d.
_OPP_COUNTER_BENEFICIAL: frozenset[str] = (
    frozenset({"p1p1", "shield"}) | _KEYWORD_COUNTER_KINDS
)

_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)

# removal_matters subtype-only destroy gate (ADR-0027): "destroy target Wall"
# destroys a CREATURE; phase parses it as destroy(subject card_types=(),
# subtypes=('Wall',)) so the _PERMANENT_TYPES card-type gate misses it. Fire on a
# non-empty SUBTYPE subject UNLESS every subtype is a LAND subtype — "destroy target
# Island / nonbasic land" is land_destruction, NOT removal (the lane's discriminator,
# CR 305.6). Basics + the common nonbasic land-type words that appear as subtypes.
_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "desert",
        "gate",
        "lair",
        "locus",
        "urza's",
        "mine",
        "power-plant",
        "tower",
        "cave",
        "sphere",
    }
)

# land_exchange (ADR-0027): phase parses "exchange control of target X and target Y"
# as a gain_control effect with subject=None (it never binds the land-typed object
# onto the effect's Filter), so the "Land" in ftypes gate misses. Fall back to the
# effect raw for the exchange-with-land phrase — the lane's own serve regex, so the
# detector and serve stay consistent. Covers Gauntlets' "artifact, creature, or land"
# (raw has "…or land…") and excludes Sharkey (no gain_control effect at all).
_LAND_EXCHANGE_RAW = re.compile(r"exchange control of[^.]*\bland\b", re.IGNORECASE)

# extra_land_drop controller='any' recovery (ADR-0027 tranche2-C): a "from your hand
# OR graveyard" put-into-play (Bonny Pall, Riveteers Confluence, Dread Tiller) makes
# phase drop the source to controller='any' (the disjunction defeats the YOUR pin),
# so the structural controller=='you' gate misses it. Mirror the deleted regex's
# YOUR-anchor on the effect raw — "you may put a land … onto the battlefield" — and
# EXCLUDE the symmetric group-hug forms (Show and Tell / Braids / Kynaios /
# Hypergenesis / Tempting Wurm: "each player / that player / each opponent may put"),
# which the YOUR-anchored deleted regex never matched (they are group ramp, not your
# extra land drop). CR 305.9.
_EXTRA_LAND_DROP_YOU_RAW = re.compile(
    r"you may put (?:a |any number of )?lands? card", re.IGNORECASE
)
_EXTRA_LAND_DROP_GROUP_RAW = re.compile(
    r"each player|that player|each opponent|their hands?", re.IGNORECASE
)

# mass_removal (ADR-0027): a BOARD WIPE — the counter_kind=='all' "each/all"
# discriminator on a destroy/exile/damage of a battlefield permanent type, or a
# negative all-creatures pump (Languish/Toxic Deluge). The battlefield-type gate
# (NOT Land-only, NOT a graveyard Card/None subject) separates a real sweep from
# land destruction (Armageddon → land_destruction) and graveyard exile (delve /
# GY-hate). CR 115.10. The pump arm needs the negative-pump raw because phase drops
# the -X/-X amount (amount=None), so the "all creatures get -" raw is the only
# discriminator vs the 1000+ positive all-creatures anthems (Glorious Anthem).
_MASS_REMOVAL_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker"}
)
_MASS_DEBUFF_RAW = re.compile(r"all .*creatures? .*get -", re.IGNORECASE)

# donate_matters (ADR-0027): a control CHANGE that gives a permanent YOU control to
# ANOTHER player (CR 701.12 — Donate, Harmless Offering, Zedruu). phase parses these
# as gain_control with scope='any' (the RECIPIENT — an opponent/other player — is
# dropped from the typed shape), so read the effect raw for the giving-away phrasing.
# The recipient discriminator ("<target/another/that player|opponent|its owner> gains
# control") is what separates donate (you give away) from theft (you take). Mirrors
# the lane's own (deleted) serve regex; reproduces it exactly (residual 0). "gains"
# (not "gain") keeps the subjunctive "have an opponent GAIN control" outside the same
# clause but matches the indicative donate clause the regex caught.
_DONATE_RAW = re.compile(
    r"(?:target opponent|another player|target player|that player|each opponent"
    r"|each other player|the player with|its owner) gains control of",
    re.IGNORECASE,
)
# GIVE-control-AWAY drawback (ADR-0027 gain_control exclusion): a card whose control-
# change effect GIVES a permanent to an OPPONENT / redistributes to EACH player — a
# drawback (Akroan Horse, Rainbow Vale, Crag Saurian) or chaos (Scrambleverse), NOT
# theft. phase maps these GiveControl effects to the gain_control category, so the
# theft lane must exclude the give-away direction. Broader than _DONATE_RAW (adds
# "an opponent" / "each player" / "that creature's controller / source's controller")
# and gain_control-only (NOT wired to donate_matters, a separate migrated lane).
_GIVE_CONTROL_AWAY = re.compile(
    r"(?:an opponent|each player|that (?:creature's|permanent's|source's) controller"
    r"|target opponent|another player|that player|each opponent|its owner"
    r"|the (?:attacking|defending) player|the player with(?: the)?)"
    r" (?:[a-z ]*? )?gains control of",
    re.IGNORECASE,
)

# reanimate subject-recovery (ADR-0027): phase emits cat='reanimate' but DROPS the
# creature subject (subject=None) on the pay-{X}/"when you do" nesting (Isareth) and
# many "return target creature card from a graveyard to the battlefield" shapes
# (Beacon of Unrest, Liliana Death's Majesty, Coffin Queen). Recover the creature-card
# reanimation from the effect raw so _reanimates_creature stays true to its docstring
# (creature reanimation = the archetype). Gated to cat='reanimate' so it can never
# reach flashback / escape / unearth (distinct categories — CR 702.34 casting ≠
# reanimation putting onto the battlefield).
_REANIMATE_CREATURE_RAW = re.compile(
    r"(?:return|put)[^.]*\bcreature cards?\b[^.]*\bgraveyard\b[^.]*\bbattlefield\b",
    re.IGNORECASE,
)

# sacrifice_matters edict exclusion (ADR-0027): a FORCED sacrifice phase mis-scoped
# to "any" (it dropped the opponent/each-player controller — Malfegor, Barter in
# Blood, Plaguecrafter), so the structural opp/each edict split missed it. The raw
# still names the sacrificing party ("<each opponent / each player / target player /
# defending player / an opponent> ... sacrifices"), the 3rd-person forced form that
# distinguishes an edict from a you-sacrifice ("you ... sacrifice"). Kept out of the
# you-sac sacrifice_matters lane (it stays an edict_matters / removal effect).
_SAC_EDICT_RAW = re.compile(
    r"\b(?:each opponent|each player|each of your opponents|target opponent"
    r"|target player|that player|an opponent|defending player|enchanted player"
    r"|opponents?)\b[^.]{0,70}?\bsacrifices?\b",
    re.IGNORECASE,
)

# sacrifice_matters subject-less / modal fallback (ADR-0027): a YOU-sacrifice of a
# NON-land permanent surviving only in a sacrifice/choose effect raw phase left
# subjectless ("sacrifice any number of creatures" — Dracoplasm, Shimatsu; "sacrifice
# … unless you sacrifice a creature" pay-or-die — Phyrexian Dreadnought, Contamination;
# a "you may sacrifice an artifact or discard" modal collapsed to `choose` — Chandra,
# Gearbane). The lazy gap admits a count + adjective; the type list excludes a bare
# "sacrifice a land" and a self-sac ("sacrifice it/this/~/<Name>") carries no type, so
# it never matches. The edict guard (_SAC_EDICT_RAW) runs alongside this at the call.
_SAC_OUTLET_RAW = re.compile(
    r"\bsacrifice (?:a|an|another|two|three|any number of|x|\d+)\b[^.]*?\b"
    r"(?:creature|artifact|permanent|enchantment|nonland|nontoken|token"
    r"|food|treasure|clue|blood|planeswalker)s?\b",
    re.IGNORECASE,
)

# convoke_matters (ADR-0027): the keyword-LESS convoke GRANTERS + PAYOFFS phase keeps
# only in a carrier raw — Wand of the Worldsoul's grant_spell_ability ("the next spell
# you cast this turn has convoke", counter_kind dropped) and the "spell that has
# convoke" payoff trigger (Saint Traft, Joyful Stormsculptor). The structured static
# granters ("<type> spells you cast have convoke") carry counter_kind='convoke' and
# need no raw scan. The card's OWN printed convoke rides the keyword array.
_CONVOKE_RAW = re.compile(r"\bconvoke\b", re.IGNORECASE)

# power_tap_engine (ADR-0027): a {T}-activated ability whose output SCALES with a
# creature's power (Marwyn "{T}: Add {G} equal to ~'s power"; Selvala "where X is the
# greatest power"; Staff of Domination). The discriminator is the CONJUNCTION of the
# structured tap activation cost (Ability.cost ~ 'tap') and this power-scaling output
# phrase in an effect raw — a bare "equal to its power" damage/draw with NO tap cost
# (Soul's Majesty, Berserk) is one-off power-scaling, not a repeatable {T} engine. The
# power numeric need not be a Quantity; the word-mirror on the activated ability's
# effect raw is the precise tell. Byte-identical to the deleted _HAND_FLOOR regex's
# "(?:equal to|where x is|x is)[^.]*power" clause. CR 602.
_POWER_SCALING_RAW = re.compile(
    r"(?:equal to|where x is|x is)[^.]*\bpower\b|greatest power", re.IGNORECASE
)

# creature_cast_trigger (ADR-0027): phase parses "Whenever you cast a creature spell"
# into a cast_spell trigger but DROPS the spell-type subject (subject=None), OR keeps
# only a `place_counter`/`emblem`/granted-token effect whose raw carries the trigger
# (Wildgrowth Archaic's enters-with replacement, Garruk's emblem, Volo's Journal /
# Blink granted token, Glimpse of Nature's delayed trigger). The "creature spell"
# cast reference survives only in some effect's raw, so a face-level scan over EVERY
# effect raw catches them. Mirrors the regex (scope "any" — a creatures-being-cast
# lane regardless of who casts). The qualifier is unambiguous (a real creature-cast
# payoff), and the typed-subject trigger path still binds what phase DID structure.
_CREATURE_SPELL_RAW = re.compile(
    r"\bwhen(?:ever)? (?:you|a player|an opponent|each opponent|another player)"
    r" casts? (?:a|an|another)\b[^.]*?\bcreature spell\b"
    r"|\bwhen(?:ever)? (?:a|another) creature spell is cast\b",
    re.IGNORECASE,
)

# fight_matters (ADR-0027): a face-level fallback for an Aftermath DFC whose "Fight"
# back face phase never projects into the IR (Prepare // Fight) — the fight survives
# only on the combined face oracle. Mirrors the project `_FIGHT_REF` / fight_matters
# regex shapes (the fight VERB with a target/creature/each-other object).
_FIGHT_RAW = re.compile(
    r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
    r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature"
    r"|\bfight each other\b|\bfights? it\b|\bfights? (?:another|each)\b",
    re.IGNORECASE,
)

# token-subtype (ADR-0027): a face-level fallback for an Aftermath DFC whose
# "create … <Subtype> token" back face phase never projects into the IR (Indulge //
# Excess) — the maker survives only on the combined face oracle. Anchored on a creation
# verb + "<Subtype> token" so a "discard a Blood token" outlet doesn't false-fire.
_TOKEN_SUBTYPE_RAW = re.compile(
    r"\bcreates?\b[^.]*?\b(blood|clue|food|treasure) tokens?\b", re.IGNORECASE
)

# group_mana (ADR-0027): symmetric/shared mana added to players OTHER than just the
# controller. The Effect dataclass has no recipient field — phase flattens every
# mana-recipient phrasing ("each player … adds {G}", "that player adds {B}{R}{G}",
# "the active player adds {C}") into ramp/any, identical to controller-only "you add"
# ramp. The non-controller recipient survives only in e.raw, so this discriminator
# (a non-you player adding mana) separates group ramp (Magus of the Vineyard, Yurlok,
# Valleymaker, Tangleroot) from your-own ramp (Sol Ring, Llanowar).
_GROUP_MANA_RAW = re.compile(
    r"(?:each|that|the active|chosen) player[^.]*adds \{", re.IGNORECASE
)

# venture_matters (ADR-0027): a dungeon-DOUBLING payoff phase keeps as a
# trigger_doubling effect whose raw names rooms/dungeons ("Room abilities of dungeons
# you own trigger an additional time" — Hama Pashar, Dungeon Delver). The dungeon
# qualifier survives only in raw, so anchor on it rather than firing on every
# trigger_doubling (Panharmonicon is NOT a venture card).
_DUNGEON_RAW = re.compile(r"\broom abilit|\bdungeon", re.IGNORECASE)

# Goad-style political force (CR 701.38): a SINGLE-TARGET "target creature … attacks
# … if able" (Boiling Blood, Incite, Basandra, Alluring Siren) is the goad mechanic's
# doer — it forces ONE creature (usually an opponent's) to attack, the political
# redirect engine that wants goad payoffs. phase types these as a `force_attack`
# effect (the same category as the self/team "attacks each combat" compulsion), so the
# IR routes the force_attack effect to forced_attack by default; this raw anchor lifts
# the TARGETED form to goad_matters too. The self/team "each combat if able" static
# (the forced_attack lane proper) never says "target creature", so it stays
# forced_attack-only.
_GOAD_STYLE_FORCE = re.compile(
    r"target creature[^.]*attacks?[^.]*\bif able\b", re.IGNORECASE
)

# Scaling-count discriminator (ADR-0027 count-operand cluster): draw_for_each /
# scaling_pump want a value that SCALES with a board count ("for each creature you
# control", "equal to the number of …"), NOT a bare X-spell ("draw X cards", "pump
# +X/+X") whose X is the cast/activation cost. phase emits op='count' for BOTH (X is a
# count too), so the count op alone over-fires the lanes onto Braingeyser / Champion
# of Wits. A genuine scaling-count carries a counted SUBJECT (Shamanic Revelation's
# creature set) OR names the count in raw ("for each" / "equal to the number of"); a
# bare X-spell has neither. CR 107.3.
_FOR_EACH_RAW = re.compile(r"\bfor each\b|\bequal to the number of\b", re.IGNORECASE)


# The named count ops that are ALWAYS a "for each <X>" scale (CR 700.3 domain, CR
# 107.x devotion/party, CR 122 counters/experience) — distinct from the generic
# `count` op, which also covers bare X-spells. A pump/draw scaling on any of these is
# genuine (Kalemne's +1/+1 per experience, Atreus's draw-per-experience). experience
# also routes to experience_matters (a correct co-fire), not stolen from it.
_NAMED_SCALE_OPS = frozenset({"counters", "domain", "devotion", "party", "experience"})


# untap_engine discriminator (ADR-0027): the lane wants a DELIBERATE untap engine —
# "untap target/another target/all/each/two/up to <permanent>" (Seedborn Muse,
# Kiora, Murkfiend Liege) — NOT an incidental "untap it/this/that" rider (Act of
# Treason's threaten, Abduction, Amulet of Vigor) nor the "doesn't untap" INVERSION
# (Basalt Monolith). Mirrors the deleted regex's anchor; a mass untap (counter_kind
# =='all', the structured "untap all") also opens it even when the raw is empty.
_UNTAP_ENGINE_RAW = re.compile(
    r"\buntap (?:target|another target|all|each|two|up to)", re.IGNORECASE
)


# typed_enters_punish opponent-recipient discriminator (ADR-0027): phase scopes
# Purphoros / Witty Roastmaster's damage effect 'any' (the "each opponent" recipient
# survives only in raw), so the lane reads the raw for an opponent recipient when the
# structural scope / subject controller doesn't already mark it.
_TYPED_ENTERS_OPP_RAW = re.compile(
    r"each opponent|target opponent|your opponents|any target", re.IGNORECASE
)


# ADR-0027 power_double — the word-mirror discriminator. phase does NOT set
# Quantity(op='multiply') for P/T DOUBLING (Unleash Fury / Mr. Orfeo / Unnatural
# Growth all have amount=None on the pump), so a x2 power-double is category-
# indistinguishable from a flat +X pump by structure alone — the raw "double …
# power" / "power … doubled" phrasing IS the discriminator. (Keying off the Scryfall
# `Double` keyword would over-fire: most Double cards double DAMAGE / counters /
# tokens, not power.)
_POWER_DOUBLE_RAW = re.compile(r"double[^.]*power|power[^.]*doubled", re.IGNORECASE)


def _is_scaling_count(amount: Quantity | None, raw: str) -> bool:
    """True when an operand is a genuine BOARD-COUNT scaler ("for each <X>"), not a
    bare X-spell whose X is the cast cost. A NAMED count op (counters / domain /
    devotion / party) is always a scale; the generic `count`/`multiply` op is a scale
    only with a counted SUBJECT or a "for each" / "number of" raw (a bare X-spell —
    Braingeyser — has neither). Gates draw_for_each / scaling_pump off X-spells."""
    if amount is None:
        return False
    if amount.op in _NAMED_SCALE_OPS:
        return True
    if amount.op not in ("count", "multiply"):
        return False
    return amount.subject is not None or bool(_FOR_EACH_RAW.search(raw or ""))


# typed_anthem_multi (ADR-0027): phase drops the typed subject entirely on some pump
# anthems (subject=None), so neither the AnyOf nor the 2+-subtypes structural guard
# can see the disjunction. Recover from the pump effect's raw: "that's a X[, a Y]…,?
# or a Z" — 2+ comma/"or"-separated subtype tokens (single-type stays type_matters).
# Requires the leading "that's a/an" so a single-target pump can't match.
_TYPED_ANTHEM_MULTI_RAW = re.compile(
    r"that's (?:an? )?[A-Z][a-z]+(?:,? (?:an? )?[A-Z][a-z]+)*,? or (?:an? )?[A-Z][a-z]+"
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


def _is_permanent_subtype_destroy(f: object) -> bool:
    """True when ``f`` is a destroy/damage subject naming a permanent by SUBTYPE only
    (card_types empty) and that subtype is NOT a land — "destroy target Wall /
    Equipment / Aura" is removal (ADR-0027 removal_matters shape 2), while "destroy
    target Island" is land_destruction. Any non-land subtype qualifies (creature
    subtypes, Equipment/Aura/Vehicle/Room permanent subtypes); a subject that is ALL
    land subtypes returns False."""
    if not isinstance(f, Filter) or not f.subtypes:
        return False
    return any(s.lower() not in _LAND_SUBTYPES for s in f.subtypes)


# ADR-0027 destroy_legendary — phase stamps this exact predicate on a destroy
# subject only for an explicitly legendary-restricted target (Bounty Agent, Tsabo
# Tavoc). NB: match the EXACT string, NOT a "legendary" substring — `NotSupertype:
# Legendary` ("destroy target NONlegendary creature" — Cast Down, One Ring) is the
# OPPOSITE and must NOT fire. (CR 205.4a.)
_LEGENDARY_DESTROY_PRED = "HasSupertype:Legendary"

# ADR-0027 mass_bounce — the predicates a board-wide bounce subject may carry while
# still being a full board sweep (vs a single-target rider): "all OTHER permanents",
# "all NONLAND permanents". A graveyard-recursion subject ("return all creature
# cards from graveyards" — Garna, Empty the Catacombs) carries InZone/Owned and is
# EXCLUDED — that is recursion, not a board bounce.
_MASS_BOUNCE_ZONE_PREDS = frozenset({"InZone", "Owned"})


def _is_mass_bounce_subject(f: object) -> bool:
    """The board-wide bounce subject (ADR-0027 mass_bounce): a generic Creature /
    Permanent card-type sweep, EXCLUDING graveyard/library recursion (an InZone /
    Owned predicate, which marks "all <type> cards from graveyards" — recursion, not
    a board bounce). Color / CMC / token / power-threshold predicates are KEPT — a
    "return all green permanents" / "all attacking creatures" sweep is still mass
    bounce. The mass discriminator (counter_kind=='all') is applied by the caller."""
    if not isinstance(f, Filter):
        return False
    if _MASS_BOUNCE_ZONE_PREDS & set(f.predicates):
        return False
    return "Creature" in f.card_types or "Permanent" in f.card_types


def _filter_controller(f: object) -> str:
    return f.controller if isinstance(f, Filter) else "any"


def _fsubs_lower(f: object) -> frozenset[str]:
    return (
        frozenset(s.lower() for s in f.subtypes)
        if isinstance(f, Filter)
        else frozenset()
    )


def _has_predicate(f: object, pred: str) -> bool:
    return isinstance(f, Filter) and pred in f.predicates


def _hoses_a_color(f: object) -> bool:
    """A filter selecting a SPECIFIC color to remove (HasColor:Red) — "destroy target
    blue creature" / "destroy all black creatures" actively hoses that color (Blue
    Elemental Blast, Cleanse). NotColor ("destroy NONblack creature") is restricted
    removal sparing your own color, NOT a hoser — excluded, exactly as the regex omits
    it (its contiguous "{color} creature" can't match "nonblack creature"). The
    NotColor-anthem hoser (Evincar's "nonblack creatures get -1/-1") is a separate
    pump-debuff form the regex still covers; not captured here. NOT 'any color
    mention' — the lane also requires a removal effect context."""
    return isinstance(f, Filter) and any(
        p.startswith("HasColor:") for p in f.predicates
    )


# Copy/clone lanes by the COPIED permanent type. clone_matters = a CREATURE copy
# (Clone, Spark Double); the rest are per-permanent-type copy lanes. A copy of a
# generic "Permanent" (Crystalline Resonance) counts toward EVERY type lane AND the
# generic copy_permanent — the hierarchy Dan asked for (anything that can target
# permanents shows up for permanents AND each permanent type). Spell-copy (instant/
# sorcery) is a SEPARATE concern (spell_copy_matters), not a clone.
_COPY_TYPE_LANES: dict[str, str] = {
    "Creature": "clone_matters",
    "Artifact": "copy_artifact",
    "Enchantment": "copy_enchantment",
    "Land": "copy_land",
    "Planeswalker": "copy_planeswalker",
}


def _clone_copy_lanes(f: object, vocab: frozenset[str]) -> tuple[str, ...]:
    """The copy lanes a clone effect feeds, from the COPIED filter's types. A generic
    Permanent copy fans out to copy_permanent + every per-type lane; a creature SUBTYPE
    (Dinosaur, Ally) with no card type is still a creature copy → clone_matters."""
    if not isinstance(f, Filter):
        return ()
    types = set(f.card_types)
    lanes: set[str] = set()
    if "Permanent" in types:
        lanes.add("copy_permanent")
        lanes.update(_COPY_TYPE_LANES.values())
    for t in types:
        if t in _COPY_TYPE_LANES:
            lanes.add(_COPY_TYPE_LANES[t])
    if any(_resolve_subject(s, vocab) for s in f.subtypes):
        lanes.add("clone_matters")  # a creature subtype (Dinosaur, Ally) → creature
    return tuple(sorted(lanes))


def _is_multicolor_pred(p: str) -> bool:
    """A ColorCount predicate selecting MULTICOLORED objects (CR: 2+ colors) — GE>=2
    or EQ>=2/3. (ColorCount GE:1 = 'is colored', EQ:0 = colorless, EQ:1 = mono.)"""
    parts = p.split(":")
    if len(parts) != 3 or parts[0] != "ColorCount" or not parts[2].isdigit():
        return False
    n = int(parts[2])
    return (parts[1] == "GE" and n >= 2) or (parts[1] == "EQ" and n >= 2)


def _predicate_build_around_lanes(f: object) -> list[str]:
    """Batch 5 — color / power BUILD-AROUND lane keys from a subject filter's enriched
    predicates. Gated on controller='you' (a removal TARGET — "destroy target creature
    with power 4 or greater" — is controller 'any', and the regex lanes avoid those
    the same way via a "you control" anchor), except colorless, which the regex reads
    unscoped too (Ancient Stirrings reveals a colorless card). A dynamic power
    comparison (":*", e.g. "power less than this creature's") is a fight-style relative
    check, not a fixed theme threshold, so it never fires."""
    if not isinstance(f, Filter):
        return []
    you = f.controller == "you"
    out: list[str] = []
    for p in f.predicates:
        if p == "ColorCount:EQ:0" and f.controller in ("you", "any"):
            out.append("colorless_matters")
        elif you and _is_multicolor_pred(p):
            out.append("multicolor_matters")
        elif (
            you
            and not p.endswith(":*")
            and p.startswith(("PtComparison:Power:GE:", "PtComparison:Power:GT:"))
        ):
            out.append("power_matters")
        elif (
            you
            and not p.endswith(":*")
            and p.startswith(("PtComparison:Power:LE:", "PtComparison:Power:LT:"))
        ):
            out.append("low_power_matters")
        # vanilla_matters (ADR-0027): the HasNoAbilities subject-Filter predicate —
        # a payoff that pumps / triggers off creatures with no abilities (Ruxa,
        # Muraganda Petroglyphs). The predicate is its own discriminator (a card
        # merely BEING vanilla never carries it — it's a property of OTHER cards'
        # Filters), so only true vanilla payoffs fire. Gate to controller in
        # {'you','any'} (a shared-board static like Muraganda is 'any'); an
        # opponent-side "destroy a creature with no abilities" stays out. CR 113.3.
        elif p == "HasNoAbilities" and f.controller in ("you", "any"):
            out.append("vanilla_matters")
    return out


def _reanimates_creature(e: object) -> bool:
    """A reanimate effect that returns CREATURE cards (matches the regex detector,
    which requires 'creature cards' — a Permanent-card return like Sun Titan is a
    separate recursion engine, not the reanimator archetype).

    ADR-0027: phase drops the creature subject (subject=None) on the pay-{X}/"when
    you do" nesting (Isareth) and many "return target creature card from a graveyard
    to the battlefield" shapes (Beacon of Unrest, Liliana Death's Majesty). Fall back
    to the effect raw so the creature-card reanimation is still recognized."""
    f = getattr(e, "subject", None)
    if isinstance(f, Filter) and "Creature" in f.card_types:
        return True
    if f is not None:
        return False
    return bool(_REANIMATE_CREATURE_RAW.search(getattr(e, "raw", "") or ""))


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


# exile_until_leaves (ADR-0027) — the "exile until ~ leaves the battlefield"
# bounce-removal idiom (Oblivion Ring, Fiend Hunter, Banisher Priest, Glorious
# Protector). A plain exile-removal (Path to Exile, Swords to Plowshares) has no
# linked return and no "until ~ leaves" phrase, so it does not fire — that phrase
# / the linked return IS the discriminator vs permanent exile.
_EXILE_UNTIL_LEAVES_RAW = re.compile(
    r"until [^.]*leaves the battlefield", re.IGNORECASE
)


def _is_exile_until_leaves(ir: Card) -> bool:
    """True for either O-Ring shape: (A) a TWO-ABILITY card — an `exile` effect
    sending to:exile co-occurring with a SECOND ability whose trigger is dies/leaves
    and whose effect is a `reanimate` to:battlefield (the linked return); or (B) a
    ONE-ABILITY INLINE card — an `exile`/`blink` effect whose raw carries the
    "until ~ leaves the battlefield" phrase (the return is textual, not structured).
    phase coerces O-Ring's "leaves" trigger to event=='dies', so both events count."""
    has_exile_to_exile = False
    has_linked_return = False
    for ab in ir.all_abilities():
        trig = ab.trigger
        for e in ab.effects:
            # Branch B — inline "exile/blink … until ~ leaves the battlefield".
            if e.category in ("exile", "blink") and _EXILE_UNTIL_LEAVES_RAW.search(
                e.raw or ""
            ):
                return True
            # Branch A — collect the two halves across abilities.
            if e.category == "exile" and "to:exile" in e.zones:
                has_exile_to_exile = True
            if (
                trig is not None
                and trig.event in ("dies", "leaves")
                and e.category == "reanimate"
                and "to:battlefield" in e.zones
            ):
                has_linked_return = True
    return has_exile_to_exile and has_linked_return


def _condition_has_kind(cond: object, kind: str) -> bool:
    """True if ``cond`` (or any node in its nested And/Or/Not tree) has ``kind``.
    phase nests a manaspentcondition under wrapper kinds (Satoru the Infiltrator's
    'or' wraps it alongside a 'not'>'wascast'), so the recursion is required. (ADR-0027
    tranche2-C free_creature_payoff.)"""
    if not isinstance(cond, Condition):
        return False
    if cond.kind == kind:
        return True
    return any(_condition_has_kind(n, kind) for n in cond.nested)


def extract_signals_ir(
    card: dict,
    ir: Card | None,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
) -> list[Signal]:
    """Derive the A2 slice of Signals from the structured Card IR (5 keys).

    Same Signal contract as ``extract_signals``, restricted to ``IR_SLICE_KEYS`` so
    the two paths can be diffed key-for-key. Returns ``[]`` when the card has no IR
    (not yet projected / brand-new set) so a dispatcher can fall back to regexes.

    ``include_membership`` mirrors ``extract_signals``: it gates the signals derived
    from what the card *is* (own card-type / own subtype tribal membership), so the
    deck-aggregate path (``include_membership=False`` for the 99) doesn't flood the
    avenues with every creature's race and type — only the commander's. Threaded so
    ``extract_signals_hybrid`` can reproduce a membership-bearing key IDENTICALLY to
    ``extract_signals`` for a given ``include_membership`` (ADR-0027)."""
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

    # lifeloss_matters paylife VETO (ADR-0027): a card whose ONLY pay-life ability is
    # mana fixing is a painland/fetchland/shockland, not a life-as-resource engine —
    # phase types those COST[paylife,tap]→ramp identically. Mirror the regex's land
    # VETO so a paylife mana-source never opens the lane.
    card_is_land = "land" in (card.get("type_line") or "").lower()
    # A Saga / lore-counter card: phase types its chapter trigger as the same
    # counter_added event a +1/+1-counter payoff carries (ADR-0027 — see
    # counter_place_trigger below). CR 714.2.
    _is_lore_counter_card = (
        "saga" in (card.get("type_line") or "").lower()
        or "lore counter" in (card.get("oracle_text") or "").lower()
    )

    # exile_until_leaves (ADR-0027) — a card-level shape (the two-ability O-Ring
    # form spans abilities), so it is decided once over the whole IR.
    if _is_exile_until_leaves(ir):
        add("exile_until_leaves", "you", "", "")

    for ab in ir.all_abilities():
        # curse_matters cares-about half (ADR-0027 t2b4a-B) — a card that REFERENCES
        # the Curse subtype: a trigger narrowed to Curses (Lynde, Cheerful Tormentor:
        # Trigger(event='dies', subject=Filter(subtypes=('Curse',)))) or an effect
        # acting on a Curse subject (a "return target Curse" recursion). The literal
        # 'Curse' subtype string is the precise anchor — inherently name-immune (a card
        # NAMED "...Curse" that is not an Aura — Curse and references no Curse subtype
        # carries no 'Curse' in any Filter.subtypes), strictly cleaner than the regex.
        # Curse is an Aura subtype that enchants a player (CR 205.3 / 702.39), NOT a
        # creature subtype, so the CREATURE_SUBTYPES vocab gate does NOT apply. Scope:
        # controller you/any (Lynde's is 'you'; a "target Curse" removal is 'any').
        if (
            ab.trigger is not None
            and ab.trigger.subject is not None
            and "Curse" in ab.trigger.subject.subtypes
        ):
            add("curse_matters", "you", "", "")
        for e in ab.effects:
            if e.subject is not None and "Curse" in getattr(e.subject, "subtypes", ()):
                add("curse_matters", "you", "", e.raw or "")
        # xspell_matters (ADR-0027 t2b4a-B) — the {X}-spells payoff lane. PRIMARY:
        # phase encodes printed-{X}-in-cost (CR 202.1) as the `HasXInManaCost`
        # predicate on a `cast_spell` trigger's subject Filter (Zaxara, Nev, Zimone,
        # Anina, …, 9 clean payoffs). A precise structured predicate — no over-fire.
        # KEPT MIRROR: phase DROPS the predicate on a couple forms (Unbound
        # Flourishing's permanent-spell cast trigger; Rosheen Meanderer's "costs that
        # contain {X}" mana-enabler folded to a bare ramp effect), so scan the effect
        # raw with the same hook the deleted _DETECTORS row used, MINUS the hoser veto
        # ("can't be cast" — Gaddock Teeg, naturally already excluded from the
        # predicate arm since a ban is a restriction effect, not a payoff trigger).
        if (
            ab.trigger is not None
            and ab.trigger.event == "cast_spell"
            and (
                ab.trigger.subject is not None
                and "HasXInManaCost" in ab.trigger.subject.predicates
            )
        ):
            add("xspell_matters", "you", "", "")
        for e in ab.effects:
            r = e.raw or ""
            if _XSPELL_HOOK_RE.search(r) and not _XSPELL_VETO_RE.search(r):
                add("xspell_matters", "you", "", r)
        # keyword_soup (ADR-0027): a keyword-stacking granter — Odric / Akroma's
        # Memorial / Rayami emit one grant_keyword Effect PER keyword from a single
        # ability (the counter_kind carries each). >=5 DISTINCT evergreen keywords in
        # ONE ability isolates the genuine team-share/absorb soup (Odric, Concerted
        # Effort, Cairn Wanderer) from a single-creature 3-4-keyword bundle (Sword of
        # Vengeance). Per-ability (not per-card) so two separate 3-keyword grants don't
        # falsely sum to 6. The "the same is true for X, Y, …" idiom phase under-parses
        # to a single grant on a few cards (Indominus Rex, Urborg Scavengers) rides the
        # kept oracle mirror below. CR 702 evergreen keywords.
        _soup_cks = {
            (e.counter_kind or "").replace(" ", "").lower()
            for e in ab.effects
            if e.category == "grant_keyword"
        }
        if len(_soup_cks & _EVERGREEN_CK) >= 5:
            add("keyword_soup", "you", "", "")
        # power_tap_engine (ADR-0027) — ability-level: an ACTIVATED ability whose cost
        # contains 'tap' AND some effect's raw scales with a creature's power. The
        # repeatable {T} power-scaling engine (Marwyn, Selvala, Staff of Domination).
        if (
            ab.kind == "activated"
            and "tap" in (ab.cost or "")
            and any(_POWER_SCALING_RAW.search(e.raw or "") for e in ab.effects)
        ):
            add("power_tap_engine", "you", "", "")
        # opponent_counter_grant (ADR-0027) — ability-level: a DETRIMENTAL counter
        # (CR 122.1d) placed on an OPPONENT's permanent (the tap-down / detrimental-mark
        # punish lane). Two recipient shapes: (A) a place_counter whose own
        # subject.controller=='opp' — bounty (Mathas, Chevill), stun (Referee Squad),
        # plus the custom detrimental marks (bribery — Gwafa Hazid, slime — Toxrill,
        # rejection — Tolarian Contempt, m1m1 — Ifnir Deadlands); (B) the "tap target
        # ... and put a stun counter on IT" shape (Freeze in Place), where phase loses
        # the place_counter subject to the "it" pronoun — recovered by a co-occurring
        # tap Effect in the SAME ability whose subject.controller=='opp'. The
        # counter_kind must be DETRIMENTAL: exclude beneficial +1/+1 grants (p1p1 —
        # Hunter of Eyeblights places one to enable its own counter-removal, the wrong
        # direction) and beneficial keyword/shield counters, which would help the
        # opponent. Self-stun drawbacks (Pugnacious Hammerskull "stun counter on it" =
        # on itself) have no opp recipient and no co-tap, so they never fire. Breadth
        # over the bounty/stun regex is legitimate gain (CR 122.1d — these are all real
        # opponent-detrimental-counter cards), not over-fire.
        _opp_tap_here = any(
            e.category == "tap" and _filter_controller(e.subject) == "opp"
            for e in ab.effects
        )
        for e in ab.effects:
            if e.category != "place_counter":
                continue
            if e.counter_kind in _OPP_COUNTER_BENEFICIAL:
                continue
            recip_opp = _filter_controller(e.subject) == "opp"
            stun_via_tap = e.counter_kind == "stun" and _opp_tap_here
            if recip_opp or stun_via_tap:
                add("opponent_counter_grant", "opponents", "", "")
        # win_lose_game (ADR-0027 t2b4a-B) — the terminal-outcome lane: a win_game or
        # lose_game Effect category (Thassa's Oracle / Laboratory Maniac win_game,
        # Door to Nothingness / Triskaidekaphobia lose_game, Felidar Sovereign's
        # upkeep-conditional win). These are precise alt-win/loss categories with no
        # over-fire surface (CR 104.2). Scope 'any' to match the deleted SWEEP row,
        # which matched BOTH self-wins ("you win the game", e.scope=='you') and
        # opponent-losses ("that player loses the game") under one forced scope — the
        # behavior-neutral choice. "Don't lose for having 0 life" (Phyrexian Unlife)
        # is correctly cat=='lose_game' too (a lose-prevention combo enabler IN the
        # lane). The per-effect e.scope is available if a future split is wanted.
        for e in ab.effects:
            if e.category in ("win_game", "lose_game"):
                add("win_lose_game", "any", "", e.raw or "")
        for e in ab.effects:
            # creatures_matter = a go-wide/scaling lane: a count operand over your
            # creatures (any effect), OR an anthem buffing them (a pump's affected
            # set). NOT a single reanimate/destroy TARGET that happens to be a
            # creature you control — gate the affected-set case on the pump shape.
            amount_subject = e.amount.subject if e.amount is not None else None
            # Batch 8 — an effect scaling with a named deck-wide count.
            if e.amount is not None:
                if e.amount.op == "devotion":
                    add("devotion_matters", "you", "", e.raw)
                elif e.amount.op == "party":
                    add("party_matters", "you", "", e.raw)
                elif e.amount.op == "domain":
                    add("domain_matters", "you", "", e.raw)
                # Batch 3 — "for each +1/+1 counter on ~" → counters payoff. (The
                # Power operand is intentionally NOT a lane: "equal to its power" is
                # ubiquitous one-off scaling, not a power build-around.)
                elif e.amount.op == "counters":
                    add("counters_matter", "you", "", e.raw)
                # ADR-0027 — "for each experience counter you have" → experience
                # payoff SCALER (Atreus's draw-X, Azula's pump-X). The experience
                # GAINERS ride the GivePlayerCounter -> experience_counter category
                # (_DOER_EFFECT_KEYS); this is the count-operand scaler side phase
                # collapsed to a bare op (CR 122.1).
                elif e.amount.op == "experience":
                    add("experience_matters", "you", "", e.raw)
            # creatures_matter go-wide DOERs (over-fire-gated per rules-lawyer /
            # CR 604.3): a COUNT operand over your creatures (any effect — the value
            # scales with the population), OR a TEAM ANTHEM buffing them — a pump
            # (+N/+N) or a keyword grant ("creatures you control have/gain <kw>") over
            # the GENERIC creature set. A SUBTYPE filter (Sliver/Goblin) is tribal
            # (type_matters per CR 205.3), excluded by _is_generic_creature_filter's
            # no-subtype gate. A single reanimate/destroy/bounce TARGET that happens to
            # be "a creature you control" is NOT an anthem/count → it never reaches
            # these arms (its effect is reanimate/exile/bounce, not pump/grant_keyword,
            # and its subject is the affected object, not a value operand).
            if (
                _is_generic_creature_filter(amount_subject)
                or (
                    # A team ANTHEM over the GENERIC creature set: a +N/+N pump, a
                    # keyword grant ("creatures you control have/gain <kw>"), or a mass
                    # base-P/T SET ("creatures you control have base power and toughness
                    # X/X" — Biomass Mutation: the whole board's stat line is rewritten,
                    # a go-wide reset/anthem). A single-target base-P/T set ("target
                    # creature becomes 0/1") has controller 'any', failing the generic
                    # gate, so it never reaches here.
                    e.category in ("pump", "grant_keyword", "base_pt_set")
                    and _is_generic_creature_filter(e.subject)
                )
                # MASS UNTAP ("untap ALL creatures you control" — Aggravated Assault,
                # Reveille Squad): a go-wide untap engine (multiple-attacker / pseudo-
                # vigilance / extra-combat payoff). counter_kind=="all" gates out a
                # single-target untap (scope Single) which is a one-off untapper, not
                # a board-wide care.
                or (
                    e.category == "untap"
                    and e.counter_kind == "all"
                    and _is_generic_creature_filter(e.subject)
                )
            ):
                add("creatures_matter", "you", "", e.raw)
            # land_creatures_matter (ADR-0027): a land-creatures build wants its lands
            # turned into / counted as creatures. The PAYOFF/anthem side is a pump /
            # keyword-grant / base-P/T over a Land+Creature dual-type subject (Sylvan
            # Advocate, Timber Protector, Jyoti); the MAKER side is a make_token of a
            # land-creature (Jyoti's Forest Dryad); the ANIMATOR side turns your lands
            # into creatures (Living Plane, Noyan Dar). The kept oracle mirror below
            # recovers the self-animate manlands phase drops. land_protection rides the
            # SAME animator (you/any lands becoming creatures need keeping alive vs
            # removal); add() dedups the co-fire. CR 305 + CR 110.1.
            if (
                e.category in ("pump", "grant_keyword", "base_pt_set")
                and _has_land_creature_types(e.subject)
            ) or (e.category == "make_token" and _has_land_creature_types(e.subject)):
                add("land_creatures_matter", "you", "", e.raw)
            if _is_land_animator(ab, e, ("you",)):
                add("land_creatures_matter", "you", "", e.raw)
            # land_protection (ADR-0027): a commander that animates MANY of your lands
            # (you- OR any-controlled) wants them kept alive — indestructible / hexproof
            # lands / land recursion. Shares the animator predicate with
            # land_creatures_matter (full regex parity = fire on any land-animate); the
            # kept oracle mirror recovers the self-animate manlands phase drops.
            if _is_land_animator(ab, e, ("you", "any")):
                add("land_protection", "you", "", e.raw)
            # land_denial (ADR-0027): a self-land-phasing commander (Taniwha: "all lands
            # you control phase out") wants asymmetric land-bounce/sac stax punishers —
            # its own lands phase back while opponents' stay gone. phase v0.1.19 emits a
            # dedicated `phasing` Effect; the controller=='you' Land subject is the
            # narrow tell (Reality Ripple's one-shot any-controller phase-out is
            # excluded). CR 702.26.
            if e.category == "phasing" and _is_land_subject(e.subject, ("you",)):
                add("land_denial", "you", "", e.raw)
            # artifacts_matter / enchantments_matter go-wide DOER: a COUNT operand
            # over YOUR artifacts/enchantments (affinity CR 702.41, "for each artifact
            # you control" — Nim Lasher, Storm-Kiln, Tuvasa). The value scales with
            # that permanent type's population (CR 604.3), so the deck cares about it.
            # A COMPOSITE count ("for each artifact and/or enchantment you control" —
            # Nettlecyst, Shambling Suit) fires BOTH lanes (each population is a care).
            for typed_lane in _typed_matters_lanes(amount_subject):
                add(typed_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter TUTOR/DIG DOER (CR 701.23): a
            # search/dig whose target filter IS the card type — "search your library for
            # an enchantment/artifact card" (Idyllic Tutor, Fabricate), "look at the top
            # N, you may put an artifact into your hand" (Glint-Nest Crane), composite
            # "an artifact OR enchantment card" (Enlightened Tutor → both). A SUBTYPE
            # tutor (Aura/Equipment — Steelshaper's Gift) is gated out (narrower care);
            # a generic-permanent tutor (Wargate) carries neither type. See
            # _type_tutor_lanes for the settled discriminator.
            for tutor_lane in _type_tutor_lanes(e):
                add(tutor_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter STATIC anthem/grant DOER: a mass
            # buff or keyword/type/ability grant over the GENERIC own-board artifact or
            # enchantment set ("Artifacts you control have hexproof" — Padeem; "Artifact
            # creatures you control have flying" — Workshop Elders; "Enchantment
            # creatures you control have deathtouch…" — Zur Eternal Schemer; "Artifacts
            # and enchantments you control have shroud" — Fountain Watch, composite).
            # The granted permission/buff ranges over the whole board of that type
            # (CR 604.3 / continuous static), so the deck cares about the population.
            # Gated to YOUR generic set (no subtype, controller you) — a single-target
            # buff/removal has a different subject shape and never reaches here. A
            # composite (Artifact AND Enchantment) subject fires BOTH lanes.
            if e.category in ("grant_keyword", "pump", "base_pt_set", "board_grant"):
                gsub = _generic_board_subject(e.subject)
                for grant_lane in _typed_matters_lanes(gsub):
                    add(grant_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter BECOMES-TYPE DOER: a "becomes a/an
            # artifact|enchantment (creature)" type-grant (Sydri, Karn's Touch animate
            # your artifacts; Argent Mutation, Titania's Song grant the artifact type
            # for affinity/combo). phase drops the granted type to a subject=None
            # carrier; project._becomes_type_markers recovers it as a `becomes_type`
            # marker whose subject carries the granted card-type.
            if e.category == "becomes_type":
                for bt_lane in _typed_matters_lanes(e.subject):
                    add(bt_lane, "you", "", e.raw)
            # artifacts_matter / enchantments_matter token + sac-payoff DOER. A
            # make_token of an Artifact subject — incl. a Treasure/Clue/Food/Powerstone
            # resource-token maker phase carries by SUBTYPE with an empty card_types
            # (CR 205.3g; Beza, Atsushi, Emissary Green) — feeds affinity/metalcraft, so
            # it fires artifacts_matter; an Enchantment-token maker ("create a Role/Aura
            # enchantment token" — Gylwain, Ellivere; Enchantment-creature tokens) fires
            # enchantments_matter. The SAC PAYOFF is symmetric: a `sacrifice` of an
            # artifact/enchantment (Atog-style outlet, "sacrifice two Foods" — Giant
            # Opportunity) values having that type's permanents as fodder (CR 701.16),
            # so it opens the lane too — the same maker+sac-payoff pairing the
            # token-subtype lanes (clue/food/treasure) read. Scoped to YOU (a
            # make_token scope you/any; a sacrifice over a non-opp subject/scope).
            esub = e.subject
            if e.category == "make_token" and e.scope in ("you", "any"):
                if _is_artifact_subject(esub):
                    add("artifacts_matter", "you", "", e.raw)
                if isinstance(esub, Filter) and "Enchantment" in esub.card_types:
                    add("enchantments_matter", "you", "", e.raw)
            if (
                e.category == "sacrifice"
                and isinstance(esub, Filter)
                and esub.controller != "opp"
                and e.scope != "opp"
            ):
                if _is_artifact_subject(esub):
                    add("artifacts_matter", "you", "", e.raw)
                if "Enchantment" in esub.card_types:
                    add("enchantments_matter", "you", "", e.raw)
            # artifacts_matter / enchantments_matter TYPE-RECURSION DOER: a graveyard
            # recursion (reanimate / graveyard→hand bounce / graveyard→library) whose
            # target is FILTERED to the card type — SINGLE-target ("return target
            # enchantment card" — Auramancer, Monk Idealist; "return target artifact
            # card" — Refurbish, Argivian Archaeologist) OR MASS ("return all
            # enchantment cards" — Crystal Chimes, Open the Vaults). The discriminator
            # is the TYPE, not mass-vs-single (CR 115.1/115.10) — type-gating = useful
            # in that type's deck. Composite fires both; generic-target ("return target
            # card" — Regrowth) fires nothing; Aura-subtype → loose enchantments member.
            for rec_lane in _type_recursion_lanes(e):
                add(rec_lane, "you", "", e.raw)
            if e.category == "gain_life" and e.scope in ("you", "any"):
                add("lifegain_matters", "you", "", e.raw)
            # graveyard_recursion (soulshift, GY→hand per CR 702.46) is a graveyard
            # payoff but NOT reanimation — it feeds graveyard_matters without the
            # reanimator / creature_recursion lanes (those are GY→battlefield).
            if e.category in ("reanimate", "mill", "graveyard_recursion"):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY-recursion at the TARGET's scope (ADR-0027 scope-gate fix): a bounce /
            # cast-from-zone / reanimate / blink whose target is restricted IN the
            # graveyard ('in:graveyard') is graveyard recursion — Raise Dead / Monk
            # Idealist / World Breaker / Grim Captain's Call return a card FROM a
            # graveyard. phase assigns these scope='any' (the affected OBJECT is the
            # recursion target, which carries no controller), so the old "==you" gate
            # below dropped them. Fire at _ir_scope(e.scope): 'your graveyard' stays
            # you, 'from a graveyard' / an opponent's GY (Spurnmage, scope='opp')
            # becomes the GY-hate/any avenue the scope-split already serves. A
            # battlefield→graveyard 'dies' is from:battlefield (excluded) and isn't a
            # recursion category, so it never reaches here (CR 700.4).
            if (
                e.category in ("bounce", "cast_from_zone", "reanimate", "blink")
                and "in:graveyard" in e.zones
                and "from:battlefield" not in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY→battlefield cheat (ADR-0027 scope-gate fix, extended): a cheat_play /
            # reanimate whose ORIGIN includes a graveyard ('from:graveyard') puts a
            # card onto the battlefield from a graveyard — reanimation. Dakkon's "from
            # your hand or graveyard onto the battlefield" carries from:graveyard after
            # the per-effect zone recovery; the disjunction's graveyard source is a
            # genuine GY payoff (the hand source is incidental).
            if (
                e.category in ("cheat_play", "reanimate")
                and "from:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Graveyard-cast payoff (ADR-0027): an effect that LETS YOU cast cards from
            # a graveyard (Finale of Promise's CastFromZone, Laelia, Jaya's emblem
            # marker) — the recovered 'from:graveyard' zone or a bare cast_from_zone
            # category. The keyworded self-cast (flashback/escape) rides castable_zones
            # above; this is the effect that grants the casting.
            if e.category == "cast_from_zone" and (
                not e.zones or "from:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # GY-recursion / GY-search at the 'from:graveyard' ORIGIN (ADR-0027 pass 2):
            # a bounce that returns a card FROM a graveyard to hand ("Return all instant
            # and sorcery cards from your graveyard to your hand" — Metallurgic
            # Summonings; the GY→hand recursion phase tags from:graveyard, not
            # in:graveyard) or a multi-zone TUTOR whose search reaches a graveyard
            # (Boonweaver scope you, Dispossess scope opp — the from:graveyard the
            # tutor zone-recovery restored). reanimate / cheat_play / cast_from_zone /
            # exile / blink from:graveyard fire above; shuffle/draw from:graveyard is
            # the "shuffle your graveyard INTO your library" branch (empties the GY,
            # anti-synergy), deliberately NOT in this set.
            if e.category in ("bounce", "tutor") and "from:graveyard" in e.zones:
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Self-mill / fill-the-yard (ADR-0027): an effect that DEPOSITS cards into a
            # graveyard ('to:graveyard') — Mulch puts the non-lands in, Atris/Marchesa
            # bin a separated pile — fuels GY payoffs. Mirrors the trigger-dimension
            # policy below: the battlefield→graveyard 'dies' movement (from:battlefield)
            # is death, not self-mill, so it's excluded. Your/any scope only (an
            # opponent-only bin is mill against them, a different lane).
            if (
                "to:graveyard" in e.zones
                and "from:battlefield" not in e.zones
                and _ir_scope(e.scope) in ("you", "any")
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Graveyard-HATE (ADR-0027): an exile EFFECT whose ORIGIN/TARGET is a
            # graveyard — 'from:graveyard' (Farewell's exile-all-graveyards mode,
            # Consecrate / Jack-o'-Lantern / Heated Argument's exile-as-cost) or
            # 'in:graveyard' (a card targeted IN a graveyard then exiled — Boneyard
            # Parley "exile … creature cards from graveyards", Disposal Mummy /
            # Deadly Cover-Up exile a card from an opponent's graveyard). The lane's
            # intent includes GY hate; _gy_scope discriminates (an opponent's GY =
            # hate, your own = escape/delve self-exile fuel; a bare "graveyards" = any).
            # Gated to a graveyard zone tag, so a to:exile-only removal (Farewell's
            # battlefield modes, Eradicate's creature exile) stays out.
            if e.category in ("exile", "blink") and (
                "from:graveyard" in e.zones or "in:graveyard" in e.zones
            ):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # Zone-aware graveyard_matters (structural projection): an effect that
            # targets/counts/copies cards IN a graveyard (delve, "creature card in
            # your graveyard", a count-operand over cards-in-GY — Enigma Drake /
            # Pteramander markers, a copy-of-a-card-in-GY recursion — Feldon, a
            # return-the-target-in-GY — Brilliance Unleashed) cares about graveyards.
            # Fired at _ir_scope(e.scope) (ADR-0027 scope-gate): a 'your graveyard'
            # reference stays you; a 'a graveyard' reference (no controller) becomes
            # any, which the scope-split serves as its own avenue. exile/blink already
            # fire above via the GY-hate hook (origin=graveyard→exile). The count
            # marker carries scope you, so the count-operand path stays you-scoped.
            if "in:graveyard" in e.zones and e.category not in ("exile", "blink"):
                add("graveyard_matters", _gy_scope(e), "", e.raw)
            # An effect that scales with YOUR hand size (ZoneCardCount(Hand) — "draw
            # cards equal to the number of cards in your hand") cares about a big hand.
            if "in:hand" in e.zones and _ir_scope(e.scope) == "you":
                add("big_hand_matters", "you", "", e.raw)
            # token_maker only when the token goes to YOU — "destroy target
            # creature, its controller makes a Beast" (scope opp) is removal.
            if e.category == "make_token" and e.scope in ("you", "any"):
                subject = _token_kindred_subject(e.subject, vocab)
                if subject is not None:
                    add(signal_keys.TOKEN_MAKER, "you", subject, e.raw)
            # ADR-0027 tranche2-B-3: token_copy_matters DEFERRED — the make_token +
            # (populate|copy-of) raw guard has a genuine floor-disabled recall gap of 54
            # cards: phase rewrites the make_token raw without "copy of" (modal/choice
            # "Command" cards, Saga chapters, "create X tokens that are copies of …"
            # where the raw is truncated). Not migrated; the _DETECTORS row stays.
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
            # Filter-PREDICATE lanes — an effect restricted to tapped / attacking
            # creatures, or permanents WITH a counter, is a payoff for that state
            # ("tapped creatures you control get…", "attacking creatures get +1/+0",
            # "creatures you control with a +1/+1 counter have trample"). _predicate
            # captures ~all phase filter properties as Filter.predicates; lanes read
            # color/PT/AnyOf/InZone + (here) Tapped/Attacking/Counters. Still unread:
            # EnchantedBy/EquippedBy (aura/equipment/voltron), WithKeyword
            # (keyword-tribal), Cmc (mana-value threshold).
            esub = e.subject
            if esub is not None:
                # Tapped / Attacking gate to YOUR permanents — "your tapped/attacking
                # creatures get …" is the payoff; "destroy target ATTACKING creature"
                # (controller any) is removal, not an aggro lane.
                if esub.controller == "you":
                    # Gate tapped to a creature (or untyped generic) subject — "return
                    # a tapped LAND you control" (Living Twister) is a mana-bounce, not
                    # a tapped-creatures aggro payoff.
                    if "Tapped" in esub.predicates and (
                        "Creature" in esub.card_types or not esub.card_types
                    ):
                        add("tapped_matters", "you", "", e.raw)
                    if "Attacking" in esub.predicates:
                        add("attack_matters", "you", "", e.raw)
                # "a creature with a +1/+1 counter" payoff isn't controller-bound.
                if esub.controller != "opp" and "Counters" in esub.predicates:
                    add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027) — the COUNT-FORM counter-HAVE payoff: an
            # effect whose VALUE counts "creatures you control WITH a +1/+1 counter"
            # ("draw a card for each creature you control with a +1/+1 counter on it" —
            # Inspiring Call, Armorcraft Judge, Hamza's cost reduction). The Counters
            # predicate rides amount.subject (the counted set), not e.subject, so the
            # e.subject read above misses it — a counters PAYOFF the lane wants.
            if (
                amount_subject is not None
                and amount_subject.controller != "opp"
                and "Counters" in amount_subject.predicates
            ):
                add("counters_matter", "you", "", e.raw)
            # ADR-0027 — the COUNT-FORM tapped payoff: an effect whose VALUE counts
            # your tapped creatures ("each opponent loses life equal to the number of
            # tapped creatures you control" — Throne of the God-Pharaoh; Crash the
            # Party / Dragonscale General / Harvest Season). The Tapped filter rides
            # amount.subject, not e.subject, so the predicate read above misses it.
            if (
                amount_subject is not None
                and amount_subject.controller == "you"
                and "Tapped" in amount_subject.predicates
            ):
                add("tapped_matters", "you", "", e.raw)
            # ADR-0027 — a FORETOLD-card reference: an effect (or its count operand)
            # acting on / scaling with foretold cards you own is a foretell PAYOFF
            # (Niko Defies Destiny — "2 life for each foretold card you own in
            # exile"). The Foretold predicate is the structural discriminator phase
            # keeps on the counted subject Filter; the foretell makers ride the
            # keyword, the granters ride the foretell marker (CR 702.143).
            for fsub in (e.subject, amount_subject):
                if fsub is not None and "Foretold" in fsub.predicates:
                    add("foretell_matters", "you", "", e.raw)
            # ── Batch E — effect-category lanes ──
            cat = e.category
            ftypes = _ftypes(e.subject)
            # variable_pt is DEFERRED (ADR-0027 t2b4a-A, needs-projection): the
            # candidate IR shapes (a `characteristic_pt` effect + a `board_count`
            # effect anchored on "power and toughness … equal to") cover only ~83 of
            # the lane; phase DROPS the "power and toughness equal to …" CDA clause
            # entirely on ~154 genuine */* bodies (Nightmare, Pack Rat, Consuming
            # Aberration, Serra Avatar, Cultivator Colossus), a deep supplement
            # parse-gap. So the lane stays on its SWEEP_DETECTORS regex; no IR arm is
            # wired here. CR 604.3.
            # ADR-0027 — self_pump: a firebreathing mana-sink — an ACTIVATED pump or
            # +1/+1-counter placement on the SELF ("{R}: ~ gets +1/+0" — Shivan Dragon;
            # "{4}: Put a +1/+1 counter on ~" — Walking Ballista, Crystalline Crawler).
            # phase maps single-target pump to category 'pump_target' and leaves
            # subject=None when the pump targets the source; the activated-counter
            # branch (place_counter/p1p1/subjNone) is the same self shape. The ab.kind==
            # 'activated' gate is the regex's anchor (the activation prefix that
            # separates a mana-sink from a static anthem or a one-shot spell pump), and
            # it excludes manlands (animate/ramp categories) whose {cost}: prefix the
            # regex matched. subject is None (self) — a granter ("target creature
            # gets…", Pia Nalaar / Kjeldoran Elite Guard) carries a subject and is
            # counter_distribute / keyword_grant_target, NOT self_pump. Serve pairs
            # self_pump with _POWER_FLING_EXTRA (firebreathing → fling), hand-spec'd.
            if (
                ab.kind == "activated"
                and e.subject is None
                and (
                    cat == "pump_target"
                    or (cat == "place_counter" and e.counter_kind == "p1p1")
                )
            ):
                add("self_pump", "you", "", e.raw)
            # ADR-0027: pump_matters DEFERRED (needs-projection). The IR's pump_target /
            # pump categories do NOT cleanly map to this lane's "positive single-target
            # combat-trick BUFF of another creature" shape: pump_target fires on every
            # -1/-1 DEBUFF (Afflict, Festering Goblin, Flanking), every activated SELF
            # firebreathing (Granite Gargoyle, Drifting Shade — already self_pump), and
            # every conditional self-buff (Chandra's Spitfire), flooding 1600+ residual
            # past the regex's narrow positive "target creature gets +N/+N".
            # Distinguishing buff-direction (+ vs -) and target-vs-self needs projection
            # (a typed pump-direction / a stable single-OTHER-target subject), so the
            # lane stays on its SWEEP_DETECTORS regex pending that. See ADR-0027.
            if cat == "place_counter" and e.counter_kind in _COUNTER_KIND_KEYS:
                ck_key, ck_scope = _COUNTER_KIND_KEYS[e.counter_kind]
                add(ck_key, ck_scope, "", e.raw)
            # keyword_counter (ADR-0027 tranche2-C) — a place/remove of a CR-122.1b
            # keyword counter (a counter that grants a keyword ability via CR 613.1f).
            # phase tags the granted keyword in counter_kind on a place_counter /
            # remove_counter; membership in the closed _KEYWORD_COUNTER_KINDS set is the
            # discriminator vs the p1p1/m1m1/oil/shield/rad/ki stat-and-resource
            # counters. scope 'any' (these counter sources appear on either side),
            # matching the sweep. The choice/multi/quoted-grant tail (Wingfold Pteron's
            # "a flying OR a hexproof counter", Oozeavite's concatenated kinds,
            # Klement's quoted enter-with grant) — where phase drops counter_kind to
            # '' — is caught by the kept word mirror (signal_specs reuses the regex).
            if (
                cat in ("place_counter", "remove_counter")
                and e.counter_kind in _KEYWORD_COUNTER_KINDS
            ):
                add("keyword_counter", "any", "", e.raw)
            # counters_matter (ADR-0027 shape 1+2a) — a +1/+1 counter PLACEMENT is the
            # lane's core engine (Forgotten Ancient, Hardened Scales, every etb /
            # upkeep / combat / activated / spell +1/+1 source). place_counter with
            # counter_kind=='p1p1' is the discriminator phase already isolates from
            # loyalty / oil / shield / rad placements (those route to their own lanes
            # via _COUNTER_KIND_KEYS); the enters-with self-counter rides the projected
            # Moved→Battlefield replacement (kind p1p1) and the count-scaled placement
            # (amount.op in count/counters) lands here too. A counter_kind=='' blank
            # placement whose raw names "+1/+1 counter" is the enters-with / modal-
            # kicker form phase stripped the kind from (Endless One, Orzhov Advokist) —
            # gated on the raw so a NON-+1/+1 blank placement (a named-counter card)
            # stays out. CR 122.1 / 614.12.
            if cat == "place_counter" and (
                e.counter_kind == "p1p1"
                or (not e.counter_kind and "+1/+1 counter" in (e.raw or ""))
            ):
                add("counters_matter", "you", "", e.raw)
            # ADR-0027 tranche2-B-3: self_counter_grow DEFERRED — the structural arm
            # (place_counter(p1p1, subject=None) + a self-anchor raw) has a genuine
            # floor-disabled recall gap (14 subjNone p1p1 placements whose raw lacks the
            # self-anchor: Saga chapter placements, adapt/monstrosity, empty-raw modal),
            # plus an "on it" over-fire on counter-replacement doublers (Hardened
            # Scales). Not migrated; both regex producers stay (the self-power-scaling
            # _DETECTORS add + the SWEEP_DETECTORS row).
            # counters_matter (ADR-0027 pass 2) — a "has/with a +1/+1 counter"
            # PAYOFF reference phase dropped to a restriction / draw / damage /
            # cost_reduction carrier, recovered as a counters_have_ref marker
            # (project._narrow_counter_refs): "creatures you control with a +1/+1
            # counter can't be blocked" (Herald), "if that creature has a +1/+1
            # counter" (Bring Low), "for each +1/+1 counter on creatures you
            # control" (Deepwood Denizen), "power greater than its base power"
            # (Kutzil/Baird, the counters-on-it idiom). The marker is the structural
            # boundary phase kept only in raw; a deck running these cares about the
            # counter (the "_matters = cares-about" rule). CR 122.1 / 122.6.
            if cat == "counters_have_ref":
                add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027 shape 4) — proliferate is definitionally a
            # counters mechanic (CR 701.27: add another counter of each kind already
            # there). A direct category→lane edge, zero discriminator needed.
            if cat == "proliferate":
                add("counters_matter", "you", "", e.raw)
            # counters_matter (ADR-0027) — a +1/+1 counter MOVE ("move +1/+1 counters
            # from … onto …" — Bioshift, Aetherborn Marauder, Nesting Grounds): the
            # counter_move category already opens the dedicated counter_move lane; a
            # p1p1 move is also a +1/+1 counters payoff (it relocates the engine's
            # counters), so it opens counters_matter too. The kind gate keeps a
            # non-+1/+1 move out (CR 122.1; minus_counters stays its own lane).
            if cat == "counter_move" and e.counter_kind == "p1p1":
                add("counters_matter", "you", "", e.raw)
            # counter_manipulation (ADR-0027) — +1/+1 or -1/-1 counter MOVE or
            # remove-as-EFFECT (The Ozolith, Power Conduit, Nesting Grounds move;
            # Carnifex Demon, Retribution of the Ancients, Festercreep remove). The
            # counter_kind gate ({p1p1,m1m1}) is the +1/+1-vs-charge/oil/loyalty
            # discriminator. The remove-as-COST tail ("Remove a +1/+1 counter from
            # ~:" — Walking Ballista, Fertilid, Quillspike, Devoted Druid) is an
            # Ability.cost the IR does not structure, so it stays on a kept word
            # mirror (_IR_KEPT_DETECTORS). CR 122.1 / 122.6.
            if (cat == "counter_move" and e.counter_kind in ("p1p1", "m1m1")) or (
                cat == "remove_counter" and e.counter_kind in ("p1p1", "m1m1")
            ):
                add("counter_manipulation", "you", "", e.raw)
            if cat == "counter_spell":
                add("counter_control", "you", "", e.raw)
            if cat == "fight":
                add("fight_matters", "you", "", e.raw)
            if cat == "ramp":
                add("ramp_matters", "you", "", e.raw)
                # ADR-0027 — group_mana: a non-controller mana RECIPIENT in the ramp
                # raw (phase emits scope='each' for ZERO ramp effects; the recipient
                # survives only in raw — _GROUP_MANA_RAW is the discriminator).
                if e.scope == "each" or _GROUP_MANA_RAW.search(e.raw or ""):
                    add("group_mana", "each", "", e.raw)
            if cat == "blink":
                add("blink_flicker", "you", "", e.raw)
            # clone_matters (creatures) + per-permanent-type copy lanes. The copied
            # type (from BecomeCopy's target, incl. an Or-composite like Spark Double's
            # Creature-or-Planeswalker) drives the hierarchy: a generic Permanent copy
            # feeds copy_permanent + every type lane. Spell-copy is a separate lane.
            if cat == "clone":
                for key in _clone_copy_lanes(e.subject, vocab):
                    add(key, "you", "", e.raw)
            # spell-copy (Twincast, Fork — "copy target spell") is a SEPARATE lane
            # from clone (which is creatures-on-the-battlefield only), per Dan.
            if cat == "spell_copy":
                add("spell_copy_matters", "you", "", e.raw)
            # evasion_denial: IgnoreLandwalkForBlocking (Great Wall) — block through
            # an opponent's landwalk evasion. Also fires off the ADR-0027 conferred
            # marker for the generic-landwalk umbrella (Staff of the Ages), which phase
            # routes to grant_keyword (project._narrow_conferred_keyword_refs).
            if cat == "evasion_denial":
                add("evasion_denial", "opponents", "", e.raw)
            # damage_reflect: the ADR-0027 conferred marker for a quoted/granted
            # reflection ability (Spiteful Sliver — 'Slivers you control have "when ~
            # is dealt damage, ~ deals that much damage to ..."'), which phase swallows
            # into grant_keyword. The on-card reflectors fire via the trigger-based
            # co-occurrence below (damage_received event + a damage effect).
            if cat == "damage_reflect":
                add("damage_reflect", "you", "", e.raw)
            # base_pt_set: a static that SETS base P/T (Lignify, Ovinize, Kenrith's
            # Transformation, animate-to-X/X). scope "any" (matches the regex —
            # spans neutralize-removal, self/land animate, switch).
            if cat == "base_pt_set":
                add("base_pt_set", "any", "", e.raw)
            # Batch 6 — grant_keyword lanes (the AddKeyword category, +3.8% parse).
            # Gated to avoid the naive +2197 flood: team lanes fire ONLY on a generic
            # creatures-you-control grant (no subtypes, no predicates — excludes
            # equipment/aura/self/single-target); the symmetric "all creatures have X"
            # grant is its own each-scope lane (it buffs opponents too).
            if cat == "grant_keyword":
                if _is_team_creature_grant(e.subject):
                    if e.counter_kind in _EVASION_GRANT_KW:
                        add("team_evasion_grant", "you", "", e.raw)
                    if e.counter_kind in _PROTECTION_GRANT_KW:
                        add("protection_grant", "you", "", e.raw)
                elif _is_all_creatures_grant(e.subject):
                    add("all_creatures_kw_grant", "any", "", e.raw)
                # team_buff (ADR-0027): the BROAD union anthem — a generic
                # "creatures you control have/gain <evergreen keyword>" grant
                # (Akroma's Memorial, Brave the Sands, Always Watching). phase emits
                # one grant_keyword Effect per keyword with the granted keyword in
                # counter_kind; the summary ck=='mass_grant' roll-up is IGNORED (a
                # duplicate). The over-fire boundary is _is_team_buff_grant: a tribal
                # ("Sliver creatures you control", subtypes), color ("Red creatures",
                # HasColor), attacking ("Attacking creatures", Attacking), or single-
                # target ("target creature you control gains", controller 'any')
                # grant fails the gate and stays out. It intentionally co-fires with
                # team_evasion_grant / protection_grant (the subsets) — the seen-set
                # dedups within a lane. (Kira's quoted-ability grant is a grant_keyword
                # carrier of a quoted ABILITY, ck not a bare keyword, correctly out.)
                if e.counter_kind in _TEAM_BUFF_GRANT_KW and _is_team_buff_grant(
                    e.subject
                ):
                    add("team_buff", "you", "", e.raw)
                # ADR-0027 — myriad_grant: a card that GRANTS myriad (CR 702.115) to a
                # creature/team (Blade of Selves, Legion Loyalty, Duke Ulder, Corporeal
                # Projection) or confers it via a copy-exception (Muddle's project.py
                # marker). phase stamps counter_kind='myriad' on the grant_keyword
                # effect — the discriminator that separates a GRANTER (no `myriad` in
                # the keyword array) from a card that prints myriad itself
                # (_IR_KEYWORD_MAP['myriad'], the makers).
                if e.counter_kind == "myriad":
                    add("myriad_grant", "you", "", e.raw)
                # ADR-0027 — exert_matters: a TEAM-VIGILANCE enabler grants vigilance
                # to your generic creature board (Heliod, Always Watching, Brave the
                # Sands). Team vigilance neutralizes exert's only downside ("won't
                # untap next turn"), so the deck wants exert creatures. counter_kind==
                # 'vigilance' is the structured discriminator; _is_generic_creature_
                # filter (controller you, no subtypes — but predicate-tolerant, so
                # Heliod's `Another` / Always Watching's `NonToken` board still counts)
                # excludes the subtype-scoped Golem/Sliver/Warrior grants (which carry
                # the subtype on this vigilance effect) and the single-target self-
                # grant. Two grant_keyword effects appear per card (one real
                # 'vigilance', one duplicate 'mass_grant'); this reads the 'vigilance'
                # one. The serve pool is the Scryfall `exert` keyword (hand-spec).
                if e.counter_kind == "vigilance" and _is_generic_creature_filter(
                    e.subject
                ):
                    add("exert_matters", "you", "", e.raw)
                # ADR-0027 — aura_equip_kw_grant: an evergreen keyword granted to YOUR
                # Aura/Equipment subgroup ("Auras you control have flying", "Equipment
                # you control have deathtouch" — Rashel). The subtyped subject Filter
                # (Aura/Equipment, controller you) is the discriminator vs a generic
                # team grant; the _AURA_EQUIP_GRANT_KW allowlist excludes equip{0}/crew
                # cost grants (phase emits those as a different effect, not an evergreen
                # grant_keyword). Broader-and-correct over the 1-card literal regex.
                if e.counter_kind in _AURA_EQUIP_GRANT_KW and _is_aura_equip_grant(
                    e.subject
                ):
                    add("aura_equip_kw_grant", "you", "", e.raw)
                # ADR-0027 — counter_grants_kw: a keyword granted to YOUR creatures that
                # HAVE A COUNTER ("creatures you control with a +1/+1 counter have
                # trample" — Bramblewood Paragon). The `Counters` predicate on the grant
                # subject (phase collapses counters={type:P1P1} to bare 'Counters'; in
                # practice every counter-conditioned keyword grant is the +1/+1 case) is
                # the discriminator vs an ordinary team keyword grant; controller=='you'
                # excludes opponent-creature grants. Broader than the closed-kw regex.
                if (
                    isinstance(e.subject, Filter)
                    and "Counters" in e.subject.predicates
                    and e.subject.controller == "you"
                ):
                    add("counter_grants_kw", "you", "", e.raw)
                # ADR-0027 — conditional_self_protection: a STATIC ability with a
                # condition (during your turn / unless tapped / as-long-as) granting a
                # PROTECTIVE keyword to ITSELF (subj None = SelfRef) — Dragonlord Ojutai
                # (not tapped → hexproof), Zurgo (during your turn → indestructible),
                # Kaito (during your turn + loyalty → hexproof). TWO discriminators: (1)
                # ab.condition is not None (the conditional gate vs an unconditional
                # anthem); (2) subj None (SelfRef) excludes team/aura/equipment grants.
                # The protective subset keeps a conditional combat buff (flying/trample)
                # out. Intrinsic hexproof rides the keyword array, never grant_keyword.
                if (
                    ab.kind == "static"
                    and ab.condition is not None
                    and e.subject is None
                    and e.counter_kind in _SELF_PROTECTION_GRANT_KW
                ):
                    add("conditional_self_protection", "you", "", e.raw)
            # ADR-0027 tranche2-C — keyword_grant_target DEFERRED (needs-projection):
            # the lane's bulk is the single-target SPELL grant ("target creature gains
            # menace" — Accelerate, Adamant Will, Madcap Skills, ~531 cards). phase
            # collapses that to grant_keyword(subject=None) with the raw TRUNCATED to
            # just "gain menace", erasing the "target creature" anchor the deleted regex
            # keyed on — making it INDISTINGUISHABLE from a self-grant ("~ gains haste")
            # and a subject-dropped go-wide grant (Otepec Huntmaster "Dinosaurs you
            # control have haste", also subject=None). The Aura/Equipment grants
            # (EnchantedBy/EquippedBy) parse cleanly (~458), but firing on subject=None
            # floods +2236 self/go-wide grants. No structural discriminator survives, so
            # this stays on the regex pending a phase projection that keeps the
            # single-target subject/raw. See the keyword_grant_target SWEEP row.
            # Batch 9 — cheat a CREATURE into play (a land into play is ramp).
            if cat == "cheat_play" and "Creature" in ftypes:
                add("cheat_into_play", "you", "", e.raw)
            # extra_land_drop (ADR-0027 tranche2-C) — "put a land card from your hand
            # onto the battlefield" (Burgeoning, Gretchen Titchwillow, Exploration-
            # adjacent put-into-play). phase emits cat=='cheat_play' with a Land-typed
            # YOUR subject (the InZone predicate confirms a hand/library origin, not a
            # generic permanent drop). The Land subject discriminates from a generic
            # cheat-into-play (Sneak Attack / reanimator put a creature) — those carry
            # 'Creature' and fire cheat_into_play above. A land TUTOR to hand
            # (cat=='tutor', to:hand) is a different shape and never reaches here. The
            # extra-land STATIC (Azusa/Exploration "play N additional lands") is a
            # separate cat=='extra_land' mechanic the deleted regex did NOT target, so
            # it's intentionally out of this faithful put-onto-battlefield migration.
            if (
                cat == "cheat_play"
                and isinstance(e.subject, Filter)
                and "Land" in e.subject.card_types
                and (
                    e.subject.controller == "you"
                    # controller='any' recovery: the "from hand OR graveyard"
                    # disjunction defeats phase's YOUR pin — recover via the deleted
                    # regex's YOUR-anchored raw, excluding the symmetric group forms.
                    or (
                        e.subject.controller == "any"
                        and _EXTRA_LAND_DROP_YOU_RAW.search(e.raw or "")
                        and not _EXTRA_LAND_DROP_GROUP_RAW.search(e.raw or "")
                    )
                )
            ):
                add("extra_land_drop", "you", "", e.raw)
            # extra_land_drop (ADR-0027 tranche2-C, dig-into-play) — "look at the top N,
            # put a land card onto the battlefield" (Elvish Rejuvenator, Cavalier of
            # Thorns, Animist's Awakening, Cartographer's Survey). phase types these
            # cat=='topdeck_select' with a Land subject and a to:battlefield zone — the
            # land lands in play, not in hand. The to:battlefield gate excludes the
            # dig-to-HAND form (Planar Genesis: zones=('to:hand',)), which is card
            # selection, not a land drop. This is the dig variant of the same put-into-
            # play engine the deleted regex's "you may put a land … onto the
            # battlefield" arm captured. CR 305.9.
            if (
                cat == "topdeck_select"
                and isinstance(e.subject, Filter)
                and "Land" in e.subject.card_types
                and "to:battlefield" in (e.zones or ())
            ):
                add("extra_land_drop", "you", "", e.raw)
            # Batch 2 (per-lane) — topdeck_stack: stack the TOP of YOUR library to
            # control draws (Brainstorm; graveyard-/hand-to-top recursion). Gate out
            # Bottom puts (cleanup) AND bounce-to-top removal (a targeted permanent,
            # controller "any") by requiring a top-ish position + YOUR moved cards.
            if (
                cat == "topdeck_stack"
                and e.counter_kind != "bottom"
                and _filter_controller(e.subject) == "you"
            ):
                add("topdeck_stack", "you", "", e.raw)
            if cat == "draw":
                # draw_for_each = a draw that SCALES with a board count, NOT a bare
                # "draw X cards" X-spell (Braingeyser). The scaling-count gate keeps
                # the X-spells (op='count', no subject, no "for each") out.
                if _is_scaling_count(e.amount, e.raw or ""):
                    add("draw_for_each", "you", "", e.raw)
                if e.scope == "each":
                    add("group_hug_draw", "each", "", e.raw)
                # target_player_draws (ADR-0027 tranche2-B-3) — a DIRECTED / forced
                # draw ("target player draws", "target opponent draws", "that player
                # draws") parses scope=='any' (the affected player carries no
                # controller); a self-cantrip and the symmetric "each player draws"
                # both parse scope=='you'/'each' (group_hug_draw takes 'each'). So
                # scope=='any' cleanly isolates the player-directed draw from the
                # self-cantrip — Ancestral Recall, Dimir Guildmage, Bloodgift Demon,
                # Howling Mine, Font of Mythos, Sphinx of Enlightenment (the latter's
                # 'target opponent' subset also carries subject controller='opp', still
                # scope='any'). CR 120.2 (draw is a player action).
                if e.scope == "any":
                    add("target_player_draws", "any", "", e.raw)
            if cat == "damage" and e.scope == "each":
                add("symmetric_damage_each", "each", "", e.raw)
            if cat == "discard" and e.scope == "opp":
                add("opponent_discard", "opponents", "", e.raw)
            # ADR-0027 lifeloss_matters — a structured life-LOSS effect. phase emits a
            # `lose_life` category distinct from gain_life / set_life, so the lane reads
            # it directly. scope splits the half: a drain ("each opponent / target
            # player / that player loses N life") is scope opp/any → opponents; a self
            # life-loss cost/payoff ("you lose N/X life") is scope you → you. lifeGAIN
            # and combat damage are sibling categories that never reach here. CR 119.3.
            if cat == "lose_life":
                add(
                    "lifeloss_matters",
                    "you" if e.scope == "you" else "opponents",
                    "",
                    e.raw,
                )
            # A `life_payment` marker (project._dropped_static_markers: a "Pay N life:"
            # cost phase misparsed — Arco-Flagellant — or dropped inside a conferred
            # quoted ability — Hibernation Sliver, Underworld Connections) is a self
            # life-as-resource engine, so it opens lifeloss_matters too. (It already
            # opens life_payment_insurance via _DOER_EFFECT_KEYS.) Not a Land card.
            if cat == "life_payment" and not card_is_land:
                add("lifeloss_matters", "you", "", e.raw)
            # An edict forces OPPONENTS / each player to sacrifice — gate on an
            # explicit opp/each scope (an unscoped sacrifice effect is ambiguous,
            # often a self-sac inside a larger effect, so don't call it an edict).
            # A sac OUTLET is a COST (handled per-ability below).
            if cat == "sacrifice" and e.scope in ("opp", "each"):
                add("edict_matters", _ir_scope(e.scope), "", e.raw)
            # ADR-0027 sacrifice_matters — a YOU-sacrifice effect (the dominant gap):
            # "you may sacrifice a creature/artifact", "sacrifice another creature",
            # the additional-cost-to-cast sac marker (Altar's Reap, Fling). phase
            # emits scope "any" even for a clearly-you sacrifice, so fire on scope NOT
            # opp/each (the edict split above takes those). Three discriminators keep
            # the over-fire out: (1) a real subject Filter that is NOT land-ONLY — a
            # subjectless SelfRef "sacrifice THIS" is a downside payoff, not a
            # sac-theme outlet, and a land-ONLY subject is the land_sacrifice lane
            # (Excavating Anurid, Serendib Djinn); a mixed "creature or land" subject
            # (Reprocess, Harvester Troll) stays — it IS a creature/artifact sac
            # outlet. (2) the raw must not name a FORCED opponent/each-player sacrifice
            # phase mis-scoped to "any" (Malfegor, Barter in Blood — phase dropped the
            # opponent controller; the raw still reads "<player> sacrifices"). CR
            # 701.16.
            # A sacrifice whose SUBJECT Filter is controller "you" is a you-sac even
            # when the effect scope leaked opp from a downstream target-player clause
            # (Cabal Therapist's "you may sacrifice a creature … then target player
            # reveals" — the supplement's possessive scope pass stamps the ability
            # opp). The subject controller is the truth for who sacrifices.
            _sac_subject_you = (
                isinstance(e.subject, Filter) and e.subject.controller == "you"
            )
            if (
                cat == "sacrifice"
                and (e.scope not in ("opp", "each") or _sac_subject_you)
                and e.subject is not None
                and e.subject.card_types != ("Land",)
                and not _SAC_EDICT_RAW.search(e.raw or "")
            ):
                add("sacrifice_matters", "you", "", e.raw)
            # Subject-less / modal fallback: phase parsed a sacrifice or a `choose`
            # whose typed subject it dropped ("sacrifice any number of creatures" —
            # Dracoplasm; "sacrifice it unless you sacrifice a creature" pay-or-die;
            # "you may sacrifice an artifact or discard a card" → choose). The raw
            # naming a non-land non-self sac IS the discriminator (a bare "sacrifice
            # it/this/~" carries no type and never matches); the edict guard keeps a
            # forced opponent sac out.
            if (
                cat in ("sacrifice", "choose")
                and _SAC_OUTLET_RAW.search(e.raw or "")
                and not _SAC_EDICT_RAW.search(e.raw or "")
            ):
                add("sacrifice_matters", "you", "", e.raw)
            if cat == "gain_control":
                # donate_matters (ADR-0027): you GIVE a permanent you control to
                # another player. phase drops the recipient (scope='any'), so read
                # the raw for the recipient-is-another-player phrasing.
                is_donate = bool(_DONATE_RAW.search(e.raw or ""))
                if is_donate:
                    add("donate_matters", "you", "", e.raw)
                if "Land" in ftypes or (
                    e.subject is None and _LAND_EXCHANGE_RAW.search(e.raw or "")
                ):
                    add("land_exchange", "you", "", e.raw)
                # gain_control = THEFT (you take an opponent's/any permanent). EXCLUDE
                # (ADR-0027): a DONATE (you GIVE your own permanent away — Donate,
                # Bazaar Trader, Conjured Currency); and a RETURN-CONTROL reset ("each
                # player gains control of permanents they own" — Brooding Saurian),
                # which the Owned-subject tell marks. The old blanket _DOER_EFFECT_KEYS
                # entry fired gain_control on those give-away/reset directions; this
                # gated arm replaces it.
                returns_own = (
                    isinstance(e.subject, Filter) and "Owned" in e.subject.predicates
                )
                gives_away = bool(_GIVE_CONTROL_AWAY.search(e.raw or ""))
                if not is_donate and not returns_own and not gives_away:
                    add("gain_control", "you", "", e.raw)
            if cat == "destroy":
                if "Land" in ftypes:
                    add("land_destruction", "you", "", e.raw)
                if "Creature" in ftypes and ab.kind in ("activated", "triggered"):
                    add("kill_engine", "you", "", e.raw)
                # removal_matters: a SINGLE-TARGET destroy whose subject is a
                # permanent TYPE, or (ADR-0027) a subtype-ONLY subject that names a
                # permanent — "destroy target Wall/Equipment/Aura" (card_types=(),
                # subtypes set) is removal of a creature / artifact / enchantment.
                # Land-subtype-only destroys ("destroy target Island") route to
                # land_destruction above and are excluded here (CR 305.6 — the lane's
                # discriminator). The MASS form ("destroy ALL creatures" — DestroyAll,
                # counter_kind=="all") is a BOARD WIPE, not single-target removal (CR
                # 115.10 vs 115.1) — it is a distinct build axis and the regex lane
                # (anchored on "destroy target …") excludes it, so the IR must too.
                if e.counter_kind != "all" and (
                    (ftypes & _PERMANENT_TYPES)
                    or _is_permanent_subtype_destroy(e.subject)
                ):
                    add("removal_matters", "you", "", e.raw)
                # destroy_legendary (ADR-0027): a destroy whose subject is restricted
                # to legendary permanents (Bounty Agent, Tsabo Tavoc, Hero's Demise;
                # the mass form "destroy each legendary creature" — Invasion of Fiora —
                # rides counter_kind=="all" but carries the same predicate). The exact
                # HasSupertype:Legendary predicate IS the discriminator — a generic
                # "destroy target creature" (Hero's Downfall, predicates=()) lacks it,
                # and "destroy target NONlegendary creature" (Cast Down, One Ring)
                # carries NotSupertype:Legendary, the OPPOSITE, so neither fires. Scope
                # 'any' (the regex forces it). is_widen_of removal_matters is preserved
                # — it stays a destroy effect, which opened removal_matters above where
                # it qualifies. (CR 205.4a.) See ADR-0027.
                if (
                    isinstance(e.subject, Filter)
                    and _LEGENDARY_DESTROY_PRED in e.subject.predicates
                ):
                    add("destroy_legendary", "any", "", e.raw)
            # mass_bounce (ADR-0027): a BOARD-WIDE bounce — counter_kind=="all" (the
            # mass discriminator, the same convention as the mass-untap arm above) on
            # a generic Creature/Permanent subject (Evacuation, River's Rebuke,
            # Devastation Tide). counter_kind=="" is a single-target bounce (Cyclonic
            # Rift's base mode, "return target creature") — correctly excluded. A
            # graveyard-recursion subject ("return all creature cards from graveyards"
            # — Garna, Empty the Catacombs, Wrenn and Seven) carries an InZone/Owned
            # predicate and is excluded by _is_mass_bounce_subject (that is recursion,
            # CR 404, not a board bounce). Scope 'any' (the sweep convention — symmetric
            # vs one-sided follows the subject; Evacuation is symmetric). KEPT RESIDUAL:
            # Cyclonic Rift's OVERLOAD 'each' mode is a phase modal-alt-cost parse drop;
            # artifact/enchantment-only sweeps (Rebuild, Reduce to Dreams) are scoped
            # out (the lane's subject is Creature/Permanent, CR 115.10). See ADR-0027.
            if (
                cat == "bounce"
                and e.counter_kind == "all"
                and _is_mass_bounce_subject(e.subject)
                and not any("graveyard" in z or "library" in z for z in e.zones)
            ):
                add("mass_bounce", "any", "", e.raw)
            # bounce_tempo (ADR-0027): a battlefield→hand bounce as tempo (Boomerang,
            # Unsummon, Man-o'-War, Cyclonic Rift). TWO discriminators turn the raw
            # bounce category into the tempo lane: (1) EXCLUDE bounces touching a
            # graveyard zone — those are GY→hand recursion already routed to
            # graveyard_matters above (CR 404); (2) EXCLUDE subject.controller=='you'
            # (self-bounce for value/blink — Aviary Mechanic, karoo lands — is NOT
            # tempo). The breadth over the narrow regex (mass + flexible bounce) is
            # legitimate bounce signal, not over-fire. A mass bounce can co-fire its own
            # each-scope mass_bounce lane above — both are real bounce signals.
            if (
                cat == "bounce"
                and not any("graveyard" in z for z in e.zones)
                and not (
                    isinstance(e.subject, Filter) and e.subject.controller == "you"
                )
            ):
                add("bounce_tempo", "you", "", e.raw)
            # removal_matters (ADR-0027): a SINGLE-TARGET DAMAGE effect to a creature /
            # permanent (cat=='damage', subject a creature or other permanent type, or
            # a permanent subtype) is removal — Flame Slash, Crossbow Infantry, Nin
            # (op=count), Surgehacker (op=multiply), Hobbit's Sting (X). The regex
            # routed this only to direct_damage; the lane was never wired to damage.
            # Discriminators vs over-fire: (1) the damage SUBJECT must be a creature /
            # permanent (its card_types intersect _PERMANENT_TYPES OR it has a
            # permanent subtype) — a player/PW-only burn ("deal 3 to any target",
            # subject=None or {Player}/{Planeswalker}) stays direct_damage; (2) the MASS
            # form ("deals N damage to EACH creature" — DamageAll, counter_kind=="all")
            # is a board wipe, NOT the single-target burn the lane wants (CR 115.10 vs
            # 115.1), and the regex lane (anchored on "to target creature/permanent")
            # excludes it, so the IR must too.
            if (
                cat == "damage"
                and e.counter_kind != "all"
                and (
                    (ftypes & _PERMANENT_TYPES)
                    or _is_permanent_subtype_destroy(e.subject)
                )
            ):
                add("removal_matters", "you", "", e.raw)
            # control_exchange (ADR-0027): exile a permanent/creature YOU OWN, then
            # return it to the battlefield (under your control) — Meneldor, The
            # Neutrinos, Aminatou's -1. This is the INVERSE of the exile_removal Owned-
            # exclusion below: the `Owned` predicate ("you own", not "you control") is
            # the control-exchange tell (donate a dud, keep their bomb, reclaim your
            # own — Puca's Mischief loop). Requiring the to:battlefield return in the
            # SAME ability keeps a bare exile-you-own from leaking. Distinct from a
            # plain blink (which says "you control" → no Owned predicate) and from
            # gain_control theft (a sibling lane).
            if (
                cat == "exile"
                and isinstance(e.subject, Filter)
                and "Owned" in e.subject.predicates
                and any("to:battlefield" in z for sib in ab.effects for z in sib.zones)
            ):
                add("control_exchange", "you", "", e.raw)
            # exile_removal = genuine targeted EXILE of a permanent (CR 406). EXCLUDE
            # (ADR-0027): (1) BLINK — exiling YOUR OWN permanent to flicker it ("Exile
            # another target creature you own. Return it" — Charming Prince, Aminatou,
            # Angel of Condemnation's first mode); the `Owned` predicate / controller-
            # you subject is the tell, and the return makes it ETB-value, not removal.
            # (2) GY-HATE — exiling a card FROM a graveyard (zones in:/from: graveyard),
            # which is opponent_exile_matters, not permanent removal. Keep the genuine
            # opponent/any-target permanent exile.
            if (
                cat == "exile"
                and ftypes & _PERMANENT_TYPES
                and not (
                    isinstance(e.subject, Filter)
                    and (
                        "Owned" in e.subject.predicates or e.subject.controller == "you"
                    )
                )
                and not any("graveyard" in z for z in e.zones)
            ):
                add("exile_removal", "you", "", e.raw)
            # mass_removal (ADR-0027): a BOARD WIPE (CR 115.10) — three arms, all
            # keyed on the counter_kind=='all' "each/all" mass discriminator phase
            # isolates from single-target removal. (1) DESTROY/EXILE sweep over a
            # battlefield permanent type (Wrath, Day of Judgment, Merciless Eviction's
            # per-mode exile/all, Bane of Progress, In Garruk's Wake, Plague Wind) —
            # gated to _MASS_REMOVAL_TYPES so "destroy all LANDS" (Armageddon →
            # land_destruction) and an exile-all over a graveyard Card/None subject
            # (delve / GY-hate) stay out. (2) DAMAGE sweep over a Creature/Permanent
            # subject (Pyroclasm, Blasphemous Act) — a player-subject "deal N to each
            # opponent" group burn carries no creature subject and is excluded. (3)
            # the -X/-X DEBUFF sweep is the pump arm below (amount dropped to None).
            if (
                cat in ("destroy", "exile")
                and e.counter_kind == "all"
                and (ftypes & _MASS_REMOVAL_TYPES)
                # GY-hate / mass reanimation exclusion (mirrors exile_removal): an
                # "exile all <type> cards from graveyards" (Living Death, Living End,
                # Gerrard, Scrap Mastery) touches a graveyard zone — that is GY
                # recursion / hate, NOT a battlefield board wipe (CR 406), excluded.
                and not any("graveyard" in z for z in e.zones)
            ):
                add("mass_removal", "you", "", e.raw)
            if (
                cat == "damage"
                and e.counter_kind == "all"
                and (ftypes & {"Creature", "Permanent"})
            ):
                add("mass_removal", "you", "", e.raw)
            # mass_removal -X/-X DEBUFF sweep (Languish, Toxic Deluge): phase emits a
            # pump over a Creature subject but DROPS the negative amount (amount=None),
            # so the "all creatures get -" raw is the discriminator vs the positive
            # all-creatures ANTHEM (anthem_static, 1000+ cards). Gate on a creature
            # subject + the negative-pump raw.
            if (
                cat == "pump"
                and "Creature" in ftypes
                and _MASS_DEBUFF_RAW.search(e.raw or "")
            ):
                add("mass_removal", "you", "", e.raw)
            # opponent_exile_matters (ADR-0027): GRAVEYARD HATE, not permanent removal —
            # fires from the _IR_KEPT_DETECTORS word mirror (the deleted sweep regex)
            # because phase scatters its forms across categories phase doesn't unify
            # (graveyard-zone exile → cat='exile' subject=None; Leyline's replacement →
            # cat='cheat_play'; Umbris's "cards opponents own in exile" → cat='pump').
            # The old permanent-exile arm here mis-fired the lane on Path-to-Exile-style
            # removal (scope='opp', permanent subject) and is removed.
            # Batch 5 — color_hoser: destroy/exile/counter keyed on a SPECIFIC color
            # ("destroy target blue permanent", "counter target red spell") — the
            # Painter toolbox's payoff. Gate on a removal EFFECT context (not any color
            # mention), so a color-tribal anthem ("red creatures get +1/+0") stays out.
            # bounce is excluded: it also covers graveyard→hand recursion of YOUR own
            # colored cards (Revive, Xiahou Dun), which is not hosing.
            if cat in ("destroy", "exile", "counter_spell") and _hoses_a_color(
                e.subject
            ):
                add("color_hoser", "you", "", e.raw)
            if cat == "tap" and e.scope == "opp":
                add("tap_down", "opponents", "", e.raw)
            # ADR-0027 — tapper_engine: a repeatable TAPPER (Icy Manipulator,
            # Opposition, Master Decoy) — a tap Effect with a real TARGET/all/each
            # subject (a Filter). Every tap effect carrying a subject is a target tap;
            # tap-AS-COST lives in Ability.cost=='tap' and emits no tap Effect, so
            # `e.subject is not None` excludes pure-cost taps and self-untaps without
            # leaking. Scope 'any' (the lane wants the broad any-controller target tap
            # — do NOT reuse the tap_down opp-gate, which would massively under-fire
            # here). tap_down can co-fire on the same card (different lane/scope) — OK.
            if cat == "tap" and e.subject is not None:
                add("tapper_engine", "any", "", e.raw)
            # ADR-0027 — tapper_engine "doesn't untap" branch: a Frost-Titan / Kismet-
            # style can't-untap static projects to a restriction whose untap text
            # survives only in raw (no mode token on the Effect), so a raw /untap/
            # substring on a restriction opens the lane. Raw-gated so a generic stax
            # restriction (can't attack / can't cast) stays out.
            if cat == "restriction" and re.search(r"untap", e.raw or "", re.IGNORECASE):
                add("tapper_engine", "any", "", e.raw)
            # untap_engine (ADR-0027): a DELIBERATE untap engine — a mass untap
            # (counter_kind=='all', the structured "untap all creatures/permanents"),
            # a raw "untap target/all/each/two/up to <permanent>", OR a modal-split
            # untap whose subject is a real TARGET permanent (Dream's Grip's "• Untap
            # target permanent" — phase structures the effect but drops the bullet
            # raw). Gated off the incidental "untap it/this/that" rider and the
            # "doesn't untap" inversion (no target subject, no engine raw).
            if cat == "untap" and (
                e.counter_kind == "all"
                or _UNTAP_ENGINE_RAW.search(e.raw or "")
                or (
                    isinstance(e.subject, Filter)
                    and bool(e.subject.card_types)
                    and e.subject.controller != "opp"
                )
            ):
                add("untap_engine", "you", "", e.raw)
            # anthem_static (ADR-0027): a STATIC +N/+N over a creature GROUP — the
            # team buff you build go-wide to ride (CR 611, continuous). Two structural
            # discriminators vs over-fire: (1) ab.kind=='static' excludes the one-shot
            # / until-end-of-turn pump (Charge, Overcome — k='spell'); a temporary pump
            # is never a static ability. (2) factor>=0 AND scope!='opp' excludes the
            # DEBUFF half of a split anthem (Elesh Norn's "creatures opponents control
            # get -2/-2" projects as a SEPARATE pump, factor=-2 scope='opp'). factor>=0
            # (NOT >0) KEEPS the toughness-only anthems +0/+N (Veteran Armorer, Castle)
            # whose Quantity.factor encodes the POWER bonus (0) only. The subject must
            # be a creature GROUP: 'Creature' card_type AND (controller=='you' OR
            # 'Another' OR a subtype) — a single-target pump (controller 'any', no
            # Another/subtype) fails the group test and stays out. (widen of team_buff.)
            if (
                ab.kind == "static"
                and e.category == "pump"
                and e.amount is not None
                and e.amount.factor >= 0
                and e.scope != "opp"
                and isinstance(e.subject, Filter)
                and "Creature" in e.subject.card_types
                and (
                    e.subject.controller == "you"
                    or "Another" in e.subject.predicates
                    or bool(e.subject.subtypes)
                )
            ):
                add("anthem_static", "you", "", e.raw)
            if cat == "pump" and e.amount is not None:
                # scaling_pump = a +X/+X that SCALES with a board count ("for each
                # creature", "for each +1/+1 counter", domain/devotion/party), NOT a
                # bare "gets +X/+X" X-pump (firebreathing X). _is_scaling_count keeps
                # the bare-X pumps out and admits the NAMED scale ops (counters/domain/
                # devotion/party) phase routes off the generic `count`.
                if _is_scaling_count(e.amount, e.raw or ""):
                    add("scaling_pump", "you", "", e.raw)
                # counters_matter (ADR-0027 shape 6) — the counter-COUNT payoff reaches
                # the IR as a PUMP whose value counts counters on a permanent ("Humans
                # you control get +1/+1 for each counter on ~" — Kyler; High Sentinels).
                # Gated to the count-bearing ops + a "counter" raw (op alone is too
                # broad — a count counts anything; a fixed pump mentioning "counter" in
                # an unrelated clause must not leak).
                if (
                    e.amount.op in ("count", "multiply", "counters")
                    and "counter" in (e.raw or "").lower()
                ):
                    add("counters_matter", "you", "", e.raw)
                # ADR-0027 — count_anthem: a TEAM anthem whose +N/+N SCALES with a
                # board count ("Creatures you control get +0/+1 for each Gate you
                # control" — Hold the Gates; Commander's Insignia; Boon of the Spirit
                # Realm). The team-subject discriminator (a generic creature Filter you
                # control) separates this from single-target firebreathing scaling_pump
                # (subject single/None) and from Coat-of-Arms-style "EACH creature
                # gets" (subject controller='any', a symmetric global). _is_scaling_
                # count keeps bare "gets +X/+X" X-pumps out — only a real board-count
                # scale qualifies. count_anthem is the team-subject subset of the
                # scaling_pump superset; a card may legitimately open both (add()
                # dedups). The serve pool is hand-registered in signal_specs.py.
                if (
                    e.amount.op in ("count", "multiply", "counters")
                    and _is_scaling_count(e.amount, e.raw or "")
                    and _is_generic_creature_filter(e.subject)
                ):
                    add("count_anthem", "you", "", e.raw)
            # power_double (ADR-0027): a P/T-DOUBLING effect. phase does NOT set a
            # multiply quantity for power doubling (Unleash Fury / Mr. Orfeo /
            # Unnatural Growth all carry amount=None), so the raw word-mirror "double
            # … power" / "power … doubled" IS the discriminator — keyed off the
            # pump/pump_target category, NOT the over-firing Scryfall `Double` keyword
            # (which mostly doubles DAMAGE / counters / tokens). Single-target doublers
            # (Unleash Fury) land in pump_target; mass doublers (Unnatural Growth,
            # Zopandrel) land in pump with a you-controller subject. NB: outside the
            # `e.amount is not None` block above — power-doublers have no amount.
            # Scope 'you' (the doubling payoff is your own beater). See ADR-0027.
            if cat in ("pump", "pump_target") and _POWER_DOUBLE_RAW.search(e.raw or ""):
                add("power_double", "you", "", e.raw)
            # Batch 12 — typed_anthem_multi: a pump over creatures of MULTIPLE named
            # types ("each creature that's an Assassin, Mercenary, or Pirate gets ...")
            # — an AnyOf-of-subtypes on a creature filter (single-type is type_matters).
            # ADR-0027: phase parses some disjunctions as a FLAT subtypes tuple instead
            # of an AnyOf node (Brenard Food/Golem, Howlpack Resurgence Wolf/Werewolf,
            # Auriok Steelshaper Soldier/Knight), so also fire when the Filter names 2+
            # subtypes — a structurally clean discriminator (single-subtype anthem stays
            # type_matters at len==1). The pump-only gate excludes Paladin Danse (a
            # one-shot keyword GRANT via grant_keyword, not a +X/+X anthem).
            if (
                cat == "pump"
                and "Creature" in ftypes
                and isinstance(e.subject, Filter)
                and (
                    any(p.startswith("AnyOf:") for p in e.subject.predicates)
                    or len(e.subject.subtypes) >= 2
                )
            ):
                add("typed_anthem_multi", "you", "", e.raw)
            # CAUSE 1 (ADR-0027): phase dropped the typed subject (subject=None) — the
            # multi-type disjunction survives only in the pump raw (Kaheera, Immerwolf,
            # Lovisa, Sporecrown). Recover from "that's a X … or a Y" (2+ subtypes).
            if (
                cat == "pump"
                and e.subject is None
                and _TYPED_ANTHEM_MULTI_RAW.search(e.raw or "")
            ):
                add("typed_anthem_multi", "you", "", e.raw)
            if amount_subject is not None and "Land" in _ftypes(amount_subject):
                add("lands_matter", "you", "", e.raw)
            # Token-subtype synergy (clue/food/treasure/blood). The maker opens the
            # lane via a make_token subject carrying the token subtype; the SACRIFICE
            # PAYOFF (Wedding Security "sacrifice a Blood token", artifact-token
            # sac-fuel) opens it via a `sacrifice` Effect whose subject Filter carries
            # the same subtype — both are the lane's stated intent ("makers plus
            # sacrifice payoffs"). One general scan over both maker + sacrifice
            # subjects (the trigger-side "whenever you sacrifice a <Subtype> token"
            # payoff is read in the trigger loop below).
            if cat in ("make_token", "sacrifice"):
                for st in _fsubs_lower(e.subject):
                    if st in _TOKEN_SUBTYPE_KEYS:
                        tk, ts = _TOKEN_SUBTYPE_KEYS[st]
                        add(tk, ts, "", e.raw)
            # ADR-0027 token_subtype_ref marker (project._dropped_static_markers): a
            # cares-about reference to a named token subtype ("Foods you control", "was
            # a Treasure") — the subtype rides counter_kind → its food/treasure/clue/
            # blood lane (the "_matters = cares-about" payoff side).
            if cat == "token_subtype_ref" and e.counter_kind in _TOKEN_SUBTYPE_KEYS:
                tk, ts = _TOKEN_SUBTYPE_KEYS[e.counter_kind]
                add(tk, ts, "", e.raw)
            # An artifact-token-subtype cares-about ref ("Treasures you control", "Clues
            # you control") also feeds artifacts_matter (CR 205.3g — those tokens are
            # artifacts; Confront the Unknown, Academy Manufactor payoffs).
            if (
                cat == "token_subtype_ref"
                and e.counter_kind in _ARTIFACT_TOKEN_SUBTYPES
            ):
                add("artifacts_matter", "you", "", e.raw)
            # Modal keyword mechanics — own CR-accurate category fanning to EVERY mode
            # it touches, instead of being flattened into a single facet. The keyword
            # maps already fire the primary lane (amass→tokens_matter,
            # fabricate→counters_matter, devour→sacrifice_matters); these add the IR
            # side (→ BOTH) plus the previously-dropped mode.
            if cat == "amass":  # CR 701.47 — grow an Army (+1/+1) or make an Army token
                add("tokens_matter", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
            if cat == "fabricate":  # CR 702.123 — Servo tokens OR +1/+1 counters
                add("tokens_matter", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
            if cat == "devour":  # CR 702.82 — sacrifice creatures, enter with counters
                add("devour_matters", "you", "", e.raw)
                add("sacrifice_matters", "you", "", e.raw)
                add("counters_matter", "any", "", e.raw)
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
                # ADR-0027 tranche2-B-3: timing_control DEFERRED — phase drops the
                # Teferi-style "cast spells only any time they could cast a sorcery"
                # cast-timing static entirely (it keeps only the flash-grant), a genuine
                # 2-card recall gap, not 100% over-fire. Not migrated; the
                # SWEEP_DETECTORS row stays as the producer.
            # Batch 13 — combat-forcing statics (split out of stax): force the table
            # to attack (Fumiko), force a path by denying blocks, or lure blockers (a
            # creature that must be blocked). All scope "you" (you wield the engine).
            # A force/can't-block static that hobbles OPPONENTS is ALSO a pillowfort
            # tax, so it still feeds stax (the split must not regress stax coverage).
            # forced_attack is scope "any" to match the sweep detector that catches
            # the same "attacks each combat if able" compulsion (a symmetric/table
            # force, not a you-only payoff).
            if cat == "force_attack":
                add("forced_attack", "any", "", e.raw)
                # Goad-style single-target political force (CR 701.38): "target
                # creature … attacks … if able" wants goad payoffs, so it also opens
                # the goad lane. The self/team "each combat" force never names a
                # target, so it stays forced_attack-only.
                if _GOAD_STYLE_FORCE.search(e.raw or ""):
                    add("goad_matters", "opponents", "", e.raw)
            if cat == "cant_block":
                add("cant_block_grant", "you", "", e.raw)
            if cat == "lure":
                add("lure_matters", "you", "", e.raw)
            if cat in ("force_attack", "cant_block"):
                if e.scope == "opp":
                    add("stax_taxes", "opponents", "", e.raw)
                elif e.scope == "each":
                    add("symmetric_stax", "each", "", e.raw)
            # Batch 17 — DoubleTriggers static (Yarok, Panharmonicon): the
            # trigger-doubling engine ("a triggered ability triggers an extra time").
            if cat == "trigger_doubling":
                add("trigger_doubling", "you", "", e.raw)
                # ADR-0027 — venture_matters DUNGEON-DOUBLING payoff: the trigger
                # doubler is scoped to room/dungeon abilities (Hama Pashar, Dungeon
                # Delver), so it's also a dungeon-completion payoff.
                if _DUNGEON_RAW.search(e.raw or ""):
                    add("venture_matters", "you", "", e.raw)
            # Batch 6 (flash_grant) — CastWithKeyword{Flash}: a flash ENABLER (cast
            # spells as though they had flash — Teferi, Yeva, Alchemist's Refuge).
            if cat == "cast_with_keyword" and e.counter_kind == "flash":
                add("flash_grant", "you", "", e.raw)
            # ADR-0027 — convoke_matters GRANTER: "<type> spells you cast have convoke"
            # (CR 702.51, Fallaji Wayfarer, Chief Engineer) carries counter_kind=
            # 'convoke' on the cast_with_keyword effect — a pure structured read. The
            # activated "next spell … has convoke" granter (Wand of the Worldsoul)
            # lands in grant_spell_ability with the keyword only in raw.
            if cat == "cast_with_keyword" and e.counter_kind == "convoke":
                add("convoke_matters", "you", "", e.raw)
            if cat == "grant_spell_ability" and _CONVOKE_RAW.search(e.raw or ""):
                add("convoke_matters", "you", "", e.raw)
            # spell_keyword_grant (ADR-0027 tranche2-B-3) — the UMBRELLA lane: a card
            # that grants ANY keyword to the spells you cast ("spells you cast have
            # convoke/cascade/improvise/delve/demonstrate/flash", a casualty granter
            # with a BLANK counter_kind — Anhelo). The cast_with_keyword category is a
            # precise structured read (no over-fire), so fire for the WHOLE category
            # regardless of counter_kind — it co-fires with flash_grant /
            # convoke_matters on those subsets (Chief Engineer is both). Ordered AFTER
            # the flash/convoke special-cases so all the lanes fire. Cost-reduction
            # granters (Goblin Electromancer → cost_reduction) and spell-COPY (Galvanic
            # Iteration → spell_copy) are different categories and correctly excluded.
            # CR 702 (keyword abilities) / 601.3e (cast with an added keyword).
            if cat == "cast_with_keyword":
                add("spell_keyword_grant", "you", "", e.raw)
            # Doubling replacements (v0.1.60's `replacements`), split by event —
            # a token doubler and a counter doubler are different archetypes.
            if cat == "token_doubling":
                add("token_doubling", "you", "", e.raw)
            if cat == "counter_doubling":
                add("counter_doubling", "you", "", e.raw)
                # counter_replace_bonus (ADR-0027) — is_widen_of counter_doubling,
                # FULLY SUBSUMED by it: a counter-placement REPLACEMENT that
                # INCREASES the count (Hardened Scales "that many plus one",
                # Branching Evolution "twice that many", Conclave / Winding
                # Constrictor "plus one") is exactly phase's counter_doubling
                # category (project: event=='addcounter' + qmod in _INCREASE_MODS).
                # A counter-REDUCING replacement is excluded by the increase gate,
                # so neither lane over-fires. Co-fires (a doubler is both lanes).
                add("counter_replace_bonus", "you", "", e.raw)
            # counter_replace_bonus tail (ADR-0027) — a TEMPORARY activated
            # replacement ("until end of turn, if you would put … put that many plus
            # one instead" — Prairie Dog) phase types as place_counter(kind='plus')
            # rather than a static counter_doubling, since it is not a permanent
            # replacement. The 'plus' kind is exact (1 card corpus-wide), so it
            # recovers the tail with zero over-fire. CR 614 (replacement effects).
            if cat == "place_counter" and e.counter_kind == "plus":
                add("counter_replace_bonus", "you", "", e.raw)
            if cat == "damage_doubling":  # Batch 10 — DamageDone replacement doubler
                add("damage_doubling", "you", "", e.raw)
            # hand_disruption only when an OPPONENT reveals (a self-reveal — "reveal
            # cards in your hand" — is scope "any" and not disruption).
            if cat == "reveal_hand" and e.scope == "opp":
                add("hand_disruption", "opponents", "", e.raw)
        # ── Condition-gated lanes (the conditions projection) ──
        cond = ab.condition
        if cond is not None:
            # free_creature_payoff (ADR-0027 tranche2-C) — an ETB-triggered ability
            # conditioned on "no mana was spent to cast it/them" rewards creatures that
            # enter for free, so the deck wants 0-cost creatures (Ornithopter, Memnite).
            # phase exposes the condition as a manaspentcondition nested in the
            # condition tree (Satoru the Infiltrator nests it under an 'or' alongside a
            # 'not'>'wascast'); recurse to find it. The Trigger.event=='etb' gate is the
            # discriminator that excludes the 4 cast_spell-triggered manaspentcondition
            # cards — Lavinia / Boromir / Roiling Vortex / Vexing Bauble — which COUNTER
            # or TAX opponents' free spells (an anti-free-spell punisher, the opposite
            # lane). 'wascast' alone is NOT the tell (a 0-cost creature IS cast for no
            # mana — the mana-spent half is the discriminator). CR 712 / 601.2h.
            if (
                ab.trigger is not None
                and ab.trigger.event == "etb"
                and _condition_has_kind(cond, "manaspentcondition")
            ):
                add("free_creature_payoff", "you", "", "")
            # Graveyard gate — "if a creature card is in your graveyard"
            # (threshold/delirium), "if ~ is in your graveyard", a graveyard count.
            if "graveyard" in cond.zones:
                add("graveyard_matters", "you", "", "")
            # Gate on a TYPE you control/count (ControlsType / "control three or more
            # artifacts" = metalcraft/affinity / a tribal gate) → that type matters.
            # Skip the generic Creature/Permanent gates (≈ every creature deck) and
            # any opponent-controlled gate (a removal condition, not your synergy).
            csub = cond.subject
            if (
                csub is not None
                and cond.kind
                in ("controlstype", "quantitycomparison", "quantitycheck", "ispresent")
                and csub.controller != "opp"
            ):
                cft = _ftypes(csub)
                if "Artifact" in cft:
                    add("artifacts_matter", "you", "", "")
                if "Enchantment" in cft:
                    add("enchantments_matter", "you", "", "")
                if "Planeswalker" in cft:
                    add("superfriends_matters", "you", "", "")
                for st in _kindred_subjects(csub, vocab):
                    add(signal_keys.TYPE_MATTERS, "you", st, "")
                # ADR-0027 — the THRESHOLD-GATE tapped payoff: "if you control two or
                # more tapped creatures, …" (Vaultguard Trooper, Sami Ship's Engineer).
                # The Tapped filter rides the condition subject, read here off the same
                # in-hand csub the type gates use. Gated to a Creature subject — a
                # "no tapped LANDS" negative gate (Nantuko Shaman, Martyr's Soul) is a
                # mana check, not a tapped-creatures aggro payoff.
                if "Tapped" in csub.predicates and "Creature" in cft:
                    add("tapped_matters", "you", "", "")
            # Gate on a COUNTER kind ("if ~ has a +1/+1 counter", oil/ki/m1m1/…) →
            # the counter lane (mirrors the place_counter counter_kind dispatch).
            if cond.kind == "hascounters":
                if cond.counter_kind == "p1p1":
                    add("counters_matter", "you", "", "")
                elif cond.counter_kind in _COUNTER_KIND_KEYS:
                    ck_key, ck_scope = _COUNTER_KIND_KEYS[cond.counter_kind]
                    add(ck_key, ck_scope, "", "")
            # ADR-0027 — a triggered/static ability GATED on being the monarch
            # ("if you're the monarch …", CR 725): Throne Warden, Garrulous
            # Sycophant. The monarch reference lives in the condition, not an
            # effect category, so the doer projection (_DOER_EFFECT_KEYS['monarch'])
            # misses it; this lifts the ismonarch gate into the monarch lane.
            if cond.kind == "ismonarch":
                add("monarch_matters", "you", "", "")
            # ADR-0027 — venture_matters condition-kind PAYOFFS: a dungeon-completion
            # ("as long as you've completed a dungeon" — Gloom Stalker) or initiative
            # ("if you have the initiative" — Imoen, Safana) gate. phase has a stable
            # enum kind for these; the venture verb lives in no effect category, so the
            # condition gate is the structural anchor (CR 701.46 / 720).
            if cond.kind in ("completedadungeon", "isinitiative"):
                add("venture_matters", "you", "", "")
        # Trigger-gated graveyard_matters (the trigger-dimension projection): a
        # trigger on cards ENTERING the graveyard from a non-battlefield zone
        # (mill / "put into your graveyard from anywhere" — Syr Konrad) or LEAVING
        # the graveyard cares about graveyards. The battlefield→graveyard case is
        # `dies` (death_matters, not graveyard synergy), so it's gated out — exactly
        # the Effect.zones policy, now on the trigger's zone movement.
        trg = ab.trigger
        if trg is not None and (
            "from:graveyard" in trg.zones
            or ("to:graveyard" in trg.zones and "from:battlefield" not in trg.zones)
        ):
            add("graveyard_matters", "you", "", "")
        # Cost-based lanes (Ability.cost — a sacrifice OUTLET vs a sac effect).
        if ab.cost:
            cost_parts = set(ab.cost.split(","))
            if "sacrifice" in cost_parts:
                add("sacrifice_matters", "you", "", "")
            # activated_draw (ADR-0027): a TAP-to-DRAW activated engine — the
            # repeatable card-advantage source you want to untap (Arch of Orazca,
            # Bonders' Enclave, Arcane Encyclopedia, Niv-Mizzet). The {T} gate is the
            # cost field carrying 'tap'; the draw is an Effect category=='draw'. Use
            # the LOOSER 'tap' in cost (catches the {N}{T}: draw rocks/lands the literal
            # regex {T}-only anchor missed) — a tap-to-draw engine with an extra mana
            # cost is still the same engine. A sacself/discardself-cost draw (Forgotten
            # Cave cycling, cost='discardself,mana') lacks 'tap' → correctly excluded;
            # a paylife-draw (Erebos, cost='mana,paylife') likewise lacks 'tap'.
            if (
                ab.kind == "activated"
                and "tap" in cost_parts
                and any(e.category == "draw" for e in ab.effects)
            ):
                add("activated_draw", "you", "", "")
            # Batch 2 — a repeatable pay-life COST wants lifegain insurance.
            if "paylife" in cost_parts:
                add("life_payment_insurance", "you", "", "")
                # ADR-0027 lifeloss_matters — a pay-life ACTIVATION COST that buys a
                # real engine effect (Beledros paylife→untap-all-lands, Cauldron
                # paylife→reanimate, Sentry paylife→regenerate) is a life-as-resource
                # payoff. Gate hard against the lane's land trap: a paylife ability
                # whose ONLY effects are mana fixing (`ramp`) is a painland/fetch/
                # shockland (Horizon Canopy, Boseiju), excluded by the non-ramp gate;
                # a Land card is excluded defensively (Eumidian Hatchery rides a
                # place_counter past the ramp gate but is still mana fixing). CR 118.
                if not card_is_land and any(e.category != "ramp" for e in ab.effects):
                    add("lifeloss_matters", "you", "", "")
            # A discard OUTLET ("Discard a card: ...") pitches fodder for value —
            # madness/reanimator fuel. The cost projection splits self-discard
            # (Cycling's "discardself") out, so this no longer floods on alt-costs.
            if "discard" in cost_parts:
                add("discard_outlet", "you", "", "")
            # A graveyard-FUEL cost ("Exile this card from your graveyard" — Renew /
            # escape, Boneyard Mycodrax; "Exile the top card of your graveyard" —
            # Alms): the ability is powered by spending graveyard cards, a self-GY
            # payoff (CR 702.55a / Renew). The cost projection tags this `exilegrave`
            # (a battlefield/hand exile cost stays generic `exile`), so it never fires
            # on a non-graveyard exile cost.
            if "exilegrave" in cost_parts:
                add("graveyard_matters", "you", "", "")
            # counters_matter (ADR-0027 shape 5) — a recurring ability whose COST
            # spends counters ("Remove a +1/+1 counter from ~: …" — Triskelion pings,
            # Crystalline Crawler, Ulasht) is a +1/+1 counter sink/outlet, the engine
            # the lane wants. The cost field is a generic 'removecounter' with NO kind,
            # so gate on the card's oracle naming "+1/+1 counter": the 258 non-+1/+1
            # removecounter cards (ki / depletion / quest / spore / charge / page /
            # wish / loyalty sinks) route to their own lanes and must stay out (CR
            # 122.1). minus_counters_matter (m1m1) stays separate via its kind path.
            if "removecounter" in cost_parts and "+1/+1 counter" in (
                card.get("oracle_text") or ""
            ):
                add("counters_matter", "you", "", "")
        # aoe_ping (ADR-0027): a REPEATABLE "damage to each creature" board ping — with
        # deathtouch on the source every ping is lethal (CR 702.2b), a recurring
        # one-sided wipe (Pestilence, Pyrohemia, Tibor and Lumia). The damage half is
        # the counter_kind=='all' damage over a Creature subject; the REPEATABLE-FRAME
        # gate is the precision discriminator. Repeatable = (a) an activated ability
        # whose cost has 'tap' or 'mana' but NOT 'sacself'/'sacrifice' (a one-shot
        # sac-self pinger — Bloodfire Colossus cost='mana,sacself' — can't be suited up
        # before it fires, excluded), OR (b) a triggered ability on upkeep / end_step /
        # cast_spell. A one-shot ETB sweep (Chaos Maw, event='etb') is NOT repeatable
        # and stays out — the lane's whole point is gearing up the source first.
        _ap_cost = set(ab.cost.split(",")) if ab.cost else set()
        _ap_repeatable = (
            ab.kind == "activated"
            and not ({"sacself", "sacrifice"} & _ap_cost)
            and bool({"tap", "mana"} & _ap_cost)
        ) or (
            ab.kind == "triggered"
            and ab.trigger is not None
            and ab.trigger.event in ("upkeep", "end_step", "cast_spell")
        )
        if _ap_repeatable:
            for e in ab.effects:
                if (
                    e.category == "damage"
                    and e.counter_kind == "all"
                    and isinstance(e.subject, Filter)
                    and "Creature" in e.subject.card_types
                ):
                    add("aoe_ping", "you", "", e.raw)
        trig = ab.trigger
        if trig is not None:
            # counters_matter (ADR-0027) — a counter-HAVE TRIGGER: "whenever a creature
            # you control WITH a +1/+1 counter on it dies / deals combat damage …"
            # (Laid to Rest, Bred for the Hunt, Meltstrider Eulogist). The Counters
            # predicate rides the trigger's subject Filter (the effect-subject read
            # above only sees effect subjects, not the trigger condition's subject).
            tsub = trig.subject
            if (
                isinstance(tsub, Filter)
                and tsub.controller != "opp"
                and "Counters" in tsub.predicates
            ):
                add("counters_matter", "you", "", "")
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
            # ADR-0027 lifeloss_matters — the pure life-loss PAYOFF: a trigger that
            # fires when a player loses life ("whenever an opponent loses life" →
            # Exquisite Blood, Mindcrank, Bloodthirsty Conqueror; "whenever you lose
            # life" → Vilis). phase parses it as Trigger(event='life_lost') — a
            # cares-about payoff that combos with the drain, so it opens the lane. An
            # opp-scoped trigger is the drain payoff (opponents); else you/any.
            if trig.event == "life_lost":
                add(
                    "lifeloss_matters",
                    "opponents" if trig.scope == "opp" else "you",
                    "",
                    "",
                )
            # ADR-0027 lose_unless_hand — the cast-from-hand-or-lose drawback (Phage
            # the Untouchable): an ETB trigger scoped to YOU whose consequence is a
            # lose_game effect ("when ~ enters, if you didn't cast it from your hand,
            # you lose the game"). The etb + scope=you + lose_game shape is unique to
            # Phage out of 41 lose_game cards — it cleanly excludes the extra-turn
            # self-lose drawbacks (Final Fortune, Glorious End — lose_game on an
            # end-step / delayed trigger), the opponent-lose payoffs (Door to Nothing —
            # scope any/opp), and the static lose-prevention engines (Lich, Lab Maniac).
            # phase emits a dedicated lose_game category, so the cast-zone CONDITION
            # need not be separately structured. CR 104.3a.
            if (
                trig.event == "etb"
                and trig.scope == "you"
                and any(e.category == "lose_game" for e in ab.effects)
            ):
                add("lose_unless_hand", "you", "", "")
            # ADR-0027 sacrifice_matters — the pure SAC PAYOFF: a trigger that fires
            # on the act of sacrificing ("whenever you sacrifice a creature/artifact"
            # → reward; Gleaming Geardrake's "sacrificed" trigger → +1/+1 counter).
            # phase parses this as Trigger(event='sacrificed') — unambiguously a sac
            # payoff, so no discriminator is needed. CR 701.16.
            if trig.event == "sacrificed":
                add("sacrifice_matters", "you", "", "")
            # Batch 2c — trigger-event "payoff" lanes.
            payoff = _PAYOFF_TRIGGER_KEYS.get(trig.event)
            if payoff is not None:
                key, fixed_scope = payoff
                add(key, fixed_scope or _ir_scope(trig.scope), "", "")
            # counter_place_trigger (ADR-0027) — is_widen_of counters_matter, but a
            # DISTINCT lane: a "whenever one or more counters are put on …" TRIGGER
            # (Shalai and Hallar, Generous Pup, Scurry Oak, Flourishing Defenses,
            # Nest of Scarabs). phase types these as event=='counter_added'. The
            # _PAYOFF_TRIGGER_KEYS row above co-opens counters_matter; this opens the
            # place-trigger lane too (both correct). Gate scope!='opp' so an opponent-
            # side punisher ("counters on a creature you DON'T control" — Kros,
            # Generous Patron, scope='opp') does not open a YOUR-counters build-around.
            # EXCLUDE Sagas / lore-counter cards: phase types a Saga CHAPTER trigger
            # ("add a lore counter", CR 714.2) as the SAME counter_added(scope='you',
            # subj=None) event a legit +1/+1 payoff (Scurry Oak, Generous Pup) carries
            # — 202 Sagas would over-fire otherwise. The Saga supertype / lore-counter
            # reminder is the only discriminator (the trigger carries no kind). NOTE:
            # the TRIGGER form — distinct from the place_counter EFFECT doers
            # (counter_distribute / self_counter_grow); Cathars' Crusade / Experiment
            # Twelve (an effect that PLACES counters) must NOT fire here.
            if (
                trig.event == "counter_added"
                and trig.scope != "opp"
                and not _is_lore_counter_card
            ):
                add("counter_place_trigger", "you", "", "")
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
            # combat_buff_engine: a begin-combat trigger that PUMPS (Additive
            # Evolution — "at the beginning of combat on your turn, put a +1/+1
            # counter ..."). A co-occurrence: the trigger event + a pump/counter
            # effect in the SAME ability (the flat per-effect pass can't see this).
            if ev == "begin_combat" and any(
                e.category in ("pump", "place_counter") for e in ab.effects
            ):
                add("combat_buff_engine", "you", "", "")
            # damage_reflect: a "when this is dealt damage" trigger that DEALS damage
            # back (Boros Reckoner, Brash Taunter, Coalhauler Swine). Co-occurrence:
            # DamageReceived event + a damage effect (excludes the fight/lifeloss/
            # counter "when dealt damage" cards, which aren't reflectors).
            if ev == "damage_received" and any(
                e.category == "damage" for e in ab.effects
            ):
                add("damage_reflect", "you", "", "")
            if ev == "taps":
                add("tap_untap_matters", "you", "", "")
            if ev == "discarded":
                add("discard_matters", "you", "", "")
            # Token-subtype sacrifice PAYOFF (trigger side): "whenever you sacrifice
            # one or more <Subtype> tokens, ..." (Blood Hypnotist). The token subtype
            # rides the trigger subject Filter — the same token-subtype synergy
            # pattern the effect loop scans for makers + sacrifice-effect payoffs.
            if ev == "sacrificed":
                for st in tsub_kinds:
                    if st in _TOKEN_SUBTYPE_KEYS:
                        tk, ts = _TOKEN_SUBTYPE_KEYS[st]
                        add(tk, ts, "", "")
            if ev == "drawn":
                add("draw_matters", "you", "", "")
                # Batch 11 — "whenever an OPPONENT draws" (Nekusar / Notion Thief).
                if trig.scope == "opp":
                    add("opponent_draw_matters", "opponents", "", "")
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
            # tribal_etb_multi (ADR-0027): a tribal ETB-chain payoff — an `etb`
            # trigger whose subject Filter names a CREATURE SUBTYPE ("whenever this or
            # another Zombie you control enters" — Noxious Ghoul, Goblin Assassin,
            # Fludge). The vocab-gated subtype is the discriminator vs a generic
            # creature/permanent ETB (Serum Tank's Artifact subject, River Kelpie's
            # "permanent from a graveyard" carry no creature subtype → excluded). The
            # broad read (any tribal-ETB trigger) is the lane's intent — it surfaces
            # every tribal-ETB chain, overlapping creature_etb + type_matters (which
            # the trigger-subject _kindred_subjects pass already opens). CR 603.
            if ev == "etb" and _kindred_subjects(trig.subject, vocab):
                add("tribal_etb_multi", "you", "", "")
            # typed_enters_punish (ADR-0027): a per-ability co-occurrence — an `etb`
            # trigger on a YOUR-controlled creature/typed-thing ("another <X> you
            # control enters") whose consequence BURNS the opponents (Purphoros, Witty
            # Roastmaster, Vial Smasher). The discriminator vs plain creature_etb
            # (ETB-value) is the damage-to-OPPONENT payoff: a damage Effect whose
            # recipient is an opponent — subject Filter controller=='opp' (Vial
            # Smasher), scope in ('opp','each'), OR raw naming "each/target/your
            # opponent(s)" / "any target" (Purphoros / Witty — phase scopes the effect
            # 'any' but the raw says "each opponent"). NOT subtype-gated — the lane is
            # "another creature/typed-thing enters → burn", the damage payoff IS the
            # tell. CR 603.
            if (
                ev == "etb"
                and _filter_controller(trig.subject) == "you"
                and any(
                    e.category == "damage"
                    and (
                        _filter_controller(e.subject) == "opp"
                        or e.scope in ("opp", "each")
                        or _TYPED_ENTERS_OPP_RAW.search(e.raw or "")
                    )
                    for e in ab.effects
                )
            ):
                add("typed_enters_punish", "you", "", "")
            # permanent_etb (ADR-0027): the GENERIC permanent-ETB value engine —
            # "whenever a/another permanent you control enters" (Amareth, Cloudstone
            # Curio, Kodama of the East Tree, Yoshimaru, Builder's Talent). The
            # discriminator vs creature_etb is the subject card_type: 'Permanent' (NOT
            # 'Creature' — that is creature_etb) and the controller-you gate (an
            # opponent-scoped permanent-ETB punisher is excluded; a self-ETB
            # SelfRef→None never has card_types=='Permanent', so it can't false-fire).
            # The IR is BROADER-and-correct vs the narrow word-order regex (it catches
            # "a/another permanent you control enters" variants the regex missed; +12
            # genuine recall, all generic-permanent-ETB engines). (CR 603.)
            if (
                ev == "etb"
                and "Permanent" in tsubs
                and _filter_controller(trig.subject) == "you"
            ):
                add("permanent_etb", "you", "", "")
            # ADR-0027 — recast_etb SERVE (the aggressive-ETB payoff a Sneak engine
            # recasts): an etb trigger whose consequence BLEEDS each opponent — a
            # discard / lose_life / sacrifice effect whose raw names "each opponent"
            # (Liliana's Specter "each opponent discards", Skirmish Rhino "each
            # opponent loses 2 life"). phase tags the controller scope, not the
            # recipient, so "each opponent" is recovered from raw. The raw-mirror
            # inside an etb-bleed effect distinguishes the recast payoff from any
            # random etb creature (the lane's whole point — not goodstuff).
            if ev == "etb" and any(
                e.category in ("discard", "lose_life", "sacrifice")
                and "each opponent" in (e.raw or "").lower()
                for e in ab.effects
            ):
                add("recast_etb", "you", "", "")
            # Batch 14 — landfall: a land ENTERING (etb trigger w/ Land subject) is
            # the bulk of landfall; the LandPlayed "play a land" trigger (_PAYOFF)
            # catches the rest.
            if ev == "etb" and "Land" in tsubs:
                add("landfall", "you", "", "")
            # artifacts_matter / enchantments_matter type-ETB DOER: "whenever an
            # artifact/enchantment (you control) enters" (constellation — Tuvasa /
            # Eidolon of Blossoms; artifact-ETB engines — Leonin Elder, Disciple of the
            # Vault). The any/you-controller symmetric form ("whenever an artifact
            # enters" — phase controller=null→'any') is the common own-payoff in a
            # type-flood deck, so it fires; an opponent-only set (controller opp — a
            # punisher, "whenever an artifact an opponent controls enters") is excluded
            # by _typed_matters_lanes' opp gate. A "Creature" co-type (artifact
            # creature) still counts (the artifact entering is what triggers it).
            if ev == "etb":
                for etb_lane in _typed_matters_lanes(trig.subject):
                    add(etb_lane, "you", "", "")
            # artifacts_matter / enchantments_matter "leaves the battlefield" DOER:
            # "whenever a(n) (nontoken) artifact/enchantment you control is put into a
            # graveyard from the battlefield" (Farid — artifact-attrition engine;
            # Starfield Mystic, Ashiok's Reaper — the enchantment-sac payoff). phase
            # parses this as a `dies` trigger over an Artifact/Enchantment-you-control
            # subject. A repeatable engine keyed on YOUR permanents of that type cycling
            # through the graveyard cares about having many of them (CR 603). A
            # composite subject fires both lanes; an opponent-scoped dies trigger
            # (removal punish) is excluded by the controller-you gate.
            if ev == "dies" and _filter_controller(trig.subject) == "you":
                for dies_lane in _typed_matters_lanes(trig.subject):
                    add(dies_lane, "you", "", "")
            # artifacts_matter / enchantments_matter ABILITY-PAYOFF DOER: "whenever you
            # activate an ability of an artifact, … copy it" (Kurkesh, Artificer Class).
            # phase tags the ability-activation trigger as event='other' but keeps the
            # ACTIVATED-OBJECT type on the trigger subject Filter. A deck rewarding its
            # own artifact activations cares about running many (CR 602/113). Gated on a
            # type-filtered subject scoped !=opp — an OPPONENT-activates punisher (Harsh
            # Mentor, Immolation Shaman, "ability of an artifact, creature, or land")
            # collapses to subject=None and never fires.
            if ev == "other" and trig.scope != "opp":
                for abil_lane in _typed_matters_lanes(trig.subject):
                    add(abil_lane, "you", "", "")
            if ev in ("combat_damage", "deals_damage"):
                add("combat_damage_matters", "opponents", "", "")
                if trig.scope == "opp":
                    add("damage_to_opp_matters", "opponents", "", "")
                if tsub_kinds:
                    add("tribe_damage_trigger", "you", "", "")
            if ev == "cast_spell":
                # ADR-0027 opponent_cast_matters — the explicit scope=opp half
                # ("whenever an opponent casts a spell" — Lavinia, Nekusar). The
                # SYMMETRIC-PUNISH half (Ruric Thar, Mai, Eidolon of the Great Revel)
                # is NOT structurally separable here: phase reports BOTH "whenever a
                # player casts" (a punisher) AND "whenever YOU cast" (a self-cast
                # spellslinger payoff — Kessig Flamebreather, Thief of Hope, Extort) as
                # scope='any', so an effect-category punish gate would over-fire every
                # spellslinger that drains/burns each opponent. The symmetric-punisher's
                # discriminator survives only in raw ("…deals N damage to THAT PLAYER" /
                # "THAT PLAYER loses/discards/sacrifices" — the caster punished as a
                # third party), so it is recovered by an _IR_KEPT_DETECTORS word mirror
                # over the joined face, NOT a scope='any' structural arm. CR 603.2.
                if trig.scope == "opp":
                    add("opponent_cast_matters", "opponents", "", "")
                if "Creature" in tsubs:
                    add("creature_cast_trigger", "any", "", "")
                # ADR-0027 — convoke_matters PAYOFF: "Whenever you cast a spell that
                # has convoke, …" (Saint Traft, Joyful Stormsculptor). The "that has
                # convoke" qualifier survives only in the consequence effect raw (phase
                # tags a bare cast_spell trigger), so anchor on it rather than firing on
                # every spellcast trigger.
                if any(_CONVOKE_RAW.search(e.raw or "") for e in ab.effects):
                    add("convoke_matters", "you", "", "")
                # DEFERRED: noncreature_cast_punish. The NotType:Creature projection is
                # accurate, but phase tags BOTH a prowess self-cast ("whenever you cast
                # a noncreature spell") AND a symmetric/opponent punisher ("whenever a
                # player casts a noncreature spell") as scope "any", so the lane can't
                # be separated from spellcast_matters — firing it conflated 103 prowess
                # cards (Kykar, Esper Sentinel). See deferrals.md.
                for sub in _kindred_subjects(trig.subject, vocab):
                    add(signal_keys.TYPED_SPELLCAST, "you", sub, "")
                # artifacts_matter / enchantments_matter cast-trigger DOER:
                # "whenever you cast an artifact/enchantment spell" (Mishra, Sythis,
                # Saheeli's "Artificer or artifact spell"). Gated on scope != "opp":
                # phase reports "you cast"/"a player casts" as scope "any" but an
                # OPPONENT-cast PUNISHER ("whenever an opponent casts an artifact
                # spell" — Citanul Druid, Infested Roothold) as scope "opp", which is
                # NOT a type deck. The subject co-typing with Creature (artifact
                # creature spell) still counts.
                if trig.scope != "opp":
                    for cast_lane in _typed_matters_lanes(trig.subject):
                        add(cast_lane, "you", "", "")
            # Batch 12 — nonhuman_attackers (Winota): an attack trigger whose
            # attacking subject is a non-Human creature you control.
            if (
                ev == "attacks"
                and _has_predicate(trig.subject, "NotSubtype:Human")
                and _filter_controller(trig.subject) == "you"
            ):
                add("nonhuman_attackers", "you", "", "")

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
                # Batch 5 — color/power build-around lanes (controller-gated).
                for key in _predicate_build_around_lanes(f):
                    add(key, "you", "", "")
    if "HasSupertype:Legendary" in ir_predicates:
        add("legends_matter", "you", "", "")
    if "Historic" in ir_predicates:
        add("historic_matters", "you", "", "")
    if "IsCommander" in ir_predicates:  # Batch 15 — cares about your commander
        add("commander_matters", "you", "", "")
    # named_permanent: the CR 100.2a copy-limit exception (a deck runs many copies of
    # one name — Relentless Rats, Hare Apparent, Seven Dwarves). The authoritative
    # signal is the deck_copy_limit field, NOT an oracle regex or a fuzzy named-count
    # heuristic (which would wrongly catch a 4-of graveyard-spell-count like
    # Accumulated Knowledge). These cards want every other copy of their name.
    if ir.many_copies:
        add("named_permanent", "you", "", "")

    # Voltron PAYOFF (ADR-0027) — the structural Aura/Equipment build-around, read
    # from phase's IR (attach action / cast-an-Aura trigger / Aura-Equipment tutor /
    # attachment-state subject) instead of the oracle-regex floor+sweep rows. This is
    # the *payoff* half only — the commander-damage MEMBERSHIP fallback stays on the
    # regex path (it's gated on `not has_other_plan` over the full signal set, which
    # the IR slice can't reproduce; see ADR-0027 deferral). Not membership-gated,
    # matching the regex producer (the payoff fires from a card's text, not its type).
    if _detect_voltron_payoff_ir(ir):
        add("voltron_matters", "you", "", "", "low")

    # creatures_matter mass-token-maker DOER (cross-open): a token_maker that makes
    # CREATURE tokens (a captured creature subject — Darien makes Soldiers, Jinnie
    # Fay Cats) is a go-wide creatures deck; it wants anthems / per-creature-ETB
    # payoffs / Cathars' Crusade the bare token_maker lane never serves. Mirrors the
    # regex SWEEP cross-open (`token_maker and s.subject`) — non-creature token
    # makers (Treasure/Clue) never set a token_maker subject, so they stay out. Low
    # confidence. (Done here, after the per-effect loop has collected token_maker.)
    if not any(s.key == "creatures_matter" for s in out) and any(
        s.key == signal_keys.TOKEN_MAKER and s.subject for s in out
    ):
        add("creatures_matter", "you", "", "", "low")

    # ADR-0027 creature_cast_trigger (face-level): a "casts a creature spell" reference
    # phase keeps only in some effect raw — a cast_spell trigger whose spell-type
    # subject was dropped (subject=None), an enters-with replacement place_counter, an
    # emblem / granted-token quoted ability. The lane is a creatures-being-cast payoff
    # (scope "any"), so one scan over every effect raw recovers them (the typed-subject
    # trigger path above already binds what phase structured).
    if not any(s.key == "creature_cast_trigger" for s in out) and any(
        _CREATURE_SPELL_RAW.search(e.raw or "")
        for ab in ir.all_abilities()
        for e in ab.effects
    ):
        add("creature_cast_trigger", "any", "", "")

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
    # ADR-0027 t2b4-C — self_blink kept detector. No clean structural IR form (the
    # `~`-substituted exile raw can't be told from cost-exile / other-target exile), so
    # reproduce BOTH regex-path producers byte-identically: the name-aware cross-
    # sentence fulltext detector + the single-target SWEEP regex run per-clause (its
    # `[^.]*\.?\s*` arms span sentences over the whole oracle, so it must scan _clauses,
    # not flat text).
    if _detect_self_blink_fulltext(kept_oracle, name) is not None or any(
        _SELF_BLINK_SWEEP_RE.search(cl) for cl in _clauses(kept_oracle)
    ):
        add("self_blink", "you", "", "")
    # ADR-0027 t2b4-C — type_change kept detector. phase DROPS the protection ARGUMENT
    # (the subtype): "protection from Salamanders" survives only as a bare keyword with
    # no argument, and Gor Muldrak's own static is dropped entirely. So mirror the
    # _type_hoser_clause word detector (re `protection from (\w+)` gated against the
    # lowercase CREATURE_SUBTYPES vocab) over the joined oracle — clause-safe (full-text
    # == per-clause). LOWERCASED to match the regex path, which feeds it clause.lower().
    if _type_hoser_clause(kept_oracle.lower()):
        add("type_change", "you", "", "")
    # Cares-about floor lanes (synergy payoffs with no structural IR form) — reuse
    # the production floor Detector objects for the curated cares-about subset.
    for det in _FLOOR_DETECTORS:
        if det.key in _IR_FLOOR_LANES and det.pattern.search(kept_oracle):
            add(det.key, det.scope, "", "")

    # ADR-0027 fight_matters (face-level fallback): an Aftermath DFC whose "Fight" back
    # face phase never projects into the IR (Prepare // Fight) keeps the fight only on
    # the combined face oracle. Gated to faces with no structural fight effect/marker —
    # the project `_FIGHT_REF` dropped-static marker covers the single-face drops; this
    # is the back-face-not-projected residual. Reminder already stripped (kept_oracle).
    if not any(s.key == "fight_matters" for s in out) and _FIGHT_RAW.search(
        kept_oracle
    ):
        add("fight_matters", "you", "", "")

    # ADR-0027 token-subtype (face-level fallback): an Aftermath DFC whose "<Subtype>
    # token" back face phase never projects into the IR (Indulge // Excess) keeps the
    # maker only on the combined face oracle. One scan over kept_oracle per migrated
    # subtype, gated to subtypes not already opened by a structural maker/sac/ref.
    for tm in _TOKEN_SUBTYPE_RAW.finditer(kept_oracle):
        st = tm.group(1).lower()
        if st in _TOKEN_SUBTYPE_KEYS:
            tk, ts = _TOKEN_SUBTYPE_KEYS[st]
            if not any(s.key == tk for s in out):
                add(tk, ts, "", "")

    # Batch K — additional keyword-array lanes + type_line membership (clean
    # structured-field lookups; membership is low-confidence, as in the regex path).
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    for kw, pairs in _IR_KEYWORD_MAP.items():
        if kw in card_kws:
            for key, scope in pairs:
                add(key, scope, "", "")
    type_line = (card.get("type_line") or "").lower()
    # Membership signals (what the card IS): own card-type and own-subtype tribal.
    # Gated on include_membership, mirroring extract_signals — the deck-aggregate
    # path passes False for the 99 so every creature's race/type doesn't flood the
    # avenues (only the commander's membership opens a lane).
    if include_membership:
        if "artifact" in type_line:
            add("artifacts_matter", "you", "", "", "low")
        if "enchantment" in type_line:
            add("enchantments_matter", "you", "", "", "low")
        # Own-subtype tribal membership (a creature's own race) + named-token
        # tribes — a clean type_line / all_parts field-lookup. Class tribes
        # (Soldier/Cleric) open only behind a go-wide signal; race tribes open
        # unconditionally (CR 205.3).
        keys_now = {s.key for s in out}
        go_wide = bool(
            keys_now & {"creatures_matter", "attack_matters", "anthem_static"}
        )
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


# ── Hybrid dispatch seam (ADR-0027 strangler) ─────────────────────────────────
MIGRATED_KEYS: frozenset[str] = frozenset(
    {
        # Batch 1 — keys whose IR production is genuinely STRUCTURAL (not a
        # re-run of the deleted oracle regex), so deleting the regex cannot
        # regress the IR path. seek (phase `seek` effect category),
        # specialize (Scryfall `specialize` keyword), ki (phase counter-kind
        # projection). See ADR-0027.
        "seek_matters",
        "specialize_matters",
        "ki_counter_matters",
        # Group "bending" — the four bending lanes (airbend CR 701.65, earthbend
        # CR 701.66, waterbend CR 701.67, firebending CR 702.189). phase v0.1.19
        # doesn't structure these recent named mechanics, so the IR path detects
        # them from the kept word-detector mirror (_IR_KEPT_DETECTORS), NOT a
        # re-run of the deleted SWEEP_DETECTORS rows. A-B==0 (commander-legal,
        # floor lanes disabled). See ADR-0027.
        "airbend_matters",
        "earthbend_matters",
        "waterbend_matters",
        "firebending_matters",
        # Group "set-mechanics" — recent-set named mechanics. celebration (WOE
        # ability word), coven (MID ability word), outlaw (creature-type group),
        # snow (supertype), lessons (subtype) detect from the kept word-detector
        # mirror (_IR_KEPT_DETECTORS); enlist + companion detect from the Scryfall
        # keyword array (_IR_KEYWORD_MAP). All NON-floor IR sources; A-B==0
        # (commander-legal, floor lanes disabled). See ADR-0027.
        "celebration_matters",
        "coven_matters",
        "outlaw_matters",
        "snow_matters",
        "lessons_matter",
        "enlist_matters",
        "companion_keyword",
        # Group "structural" — keys backed by a STRUCTURED IR shape (not a re-run
        # of the deleted oracle regex). all_creatures_kw_grant ← GrantKeyword effect
        # on an "all creatures" subject; counter_move ← MoveCounters effect
        # (_DOER_EFFECT_KEYS); facedown_matters ← manifest/cloak/turn_face_up effect
        # categories + kept word mirror; nonhuman_attackers ← attacks trigger w/
        # NotSubtype:Human subject; opponent_draw_matters ← "drawn" trigger scoped
        # opp; token_doubling ← token-doubling replacement effect; voting_matters ←
        # kept word mirror. All NON-floor IR sources; A-B==0 (commander-legal, floor
        # lanes disabled). See ADR-0027.
        "all_creatures_kw_grant",
        "counter_move",
        "facedown_matters",
        "nonhuman_attackers",
        "opponent_draw_matters",
        "token_doubling",
        "voting_matters",
        # Group "restriction-narrow" (ADR-0027 projection deepening) — keys whose
        # tail cards phase folds into a generic carrier (a static restriction, an
        # Animate, a TargetOnly/Choose wrapper, an ismonarch condition) so the
        # mechanic survives only in raw. project._narrow_mechanic_refs appends a
        # precise `monarch`/`saddle`/`soulbond` marker effect (read via
        # _DOER_EFFECT_KEYS), and the ismonarch condition is lifted in
        # extract_signals_ir, so the lane fires from a NON-floor structural IR
        # source — A-B==0 (commander-legal, floor lanes disabled). soulbond also
        # reuses the Scryfall keyword; saddle also reuses the saddle keyword. Their
        # oracle-regex producers are deleted. See ADR-0027.
        "monarch_matters",
        "saddle_matters",
        "soulbond_matters",
        # Group "trigger-other raw-marker" (ADR-0027 projection deepening) — keys
        # whose tail cards are PAYOFF triggers phase flattened to event='other' (the
        # consequence is a typed effect; the trigger condition survives only in the
        # effect raw). project._narrow_trigger_other_refs appends a precise marker
        # effect (coin_flip / ring_tempt / discover / ninjutsu) read via
        # _DOER_EFFECT_KEYS, so the lane fires from a NON-floor structural IR source —
        # A-B==0 (commander-legal, floor lanes disabled). discover/ninjutsu also reuse
        # the Scryfall keyword; ring also raw-scans "Ring-bearer" (Sauron, no tempt
        # trigger). Their oracle-regex producers are deleted. boast/exhaust/explore/
        # scry_surveil got the same markers but a static-grant / delayed-trigger /
        # replacement-drop remainder keeps them on regex (not migrated). See ADR-0027.
        "coin_flip",
        "discover_matters",
        "ninjutsu_matters",
        "ring_matters",
        # Group "conferred-keyword re-parse" (ADR-0027 projection deepening) — keys
        # whose tail cards GRANT a keyword/ability to a CLASS of objects, which phase
        # folds into a grant carrier (cast_with_keyword / grant_spell_ability /
        # grant_keyword) so the granted keyword survives only in raw.
        # project._narrow_conferred_keyword_refs appends a precise marker effect, so
        # the lane fires from a NON-floor structural IR source — A-B==0 (commander-
        # legal, floor lanes disabled). affinity_type ← the Scryfall affinity keyword
        # + an `affinity` marker for "spells you cast have affinity for X" (Tezzeret,
        # …); damage_reflect ← the on-card damage_received+damage co-occurrence + a
        # `damage_reflect` marker for the quoted reflection grant (Spiteful Sliver);
        # evasion_denial ← phase's named-walk evasion_denial effect + an
        # `evasion_denial` marker for the generic-landwalk umbrella (Staff of the
        # Ages). Their oracle-regex SWEEP_DETECTORS rows are deleted (affinity also
        # left _IR_FLOOR_LANES). madness/foretell/devour/connive/counter_control got
        # the same markers (recall improved) but a condition-drop (Anje), a Foretold-
        # predicate (Niko), a token-profile residual, and modal/Aura-host parse-drops
        # keep them on regex pending a later capability. See ADR-0027.
        "affinity_type",
        "damage_reflect",
        "evasion_denial",
        # Group "go-wide count-over-own-board" (ADR-0027 projection deepening) — the
        # headline scaling lane. creatures_matter fires from STRUCTURAL IR alone (it is
        # NOT in _IR_FLOOR_LANES — its broad oracle floor was never floor-mirrored into
        # the IR path): a COUNT/AGGREGATE operand over your generic creature board (a
        # SetDynamicPower / ModifyCost-Reduce / Aggregate-Sum / replacement-counter
        # count, plus phase's named formidable condition and the for-each / X-is-count
        # oracle markers), a TEAM ANTHEM (pump / keyword grant / base-P/T set over the
        # generic set), a MASS keyword/evasion grant (CantBeBlockedBy static + the
        # narrow oracle mass-grant marker), a MASS untap (SetTapState scope=All + the
        # "untap all creatures you control" marker), and the token-maker cross-open.
        # All 14 adjudicated gaps fire structurally; the floor-disabled A-B residual is
        # 100% over-fire (subtype/color lords = type_matters CR 205.3, single-target,
        # attack/combat triggers, cost taps). Its over-broad oracle-regex _DETECTORS
        # producer ("creatures you control"/"for each creature you control" substring)
        # is deleted; the serve spec stays in signal_specs. See ADR-0027.
        "creatures_matter",
        # devour_matters (CR 702.82) — the sacrifice-creatures-for-+1/+1-counters
        # keyword lane. Fires from STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES): the
        # Scryfall `devour` keyword via _IR_KEYWORD_MAP plus phase's `devour` effect
        # category (the `devour N` make-token marker + the supplement keyword value),
        # fanned by the cat=="devour" arm in extract_signals_ir. Floor-mirror-dep==0
        # (commander-legal, floor lanes disabled): the IR set is identical with the
        # floor on or off. Its over-broad "\bdevour\b" SWEEP_DETECTORS regex producer
        # is deleted — it 100% over-fired on the "Devour Intellect" FLAVOR WORD
        # (CR 207.2d, no rules meaning) and the "Devour in Flames" CARD NAME, neither
        # being the Devour keyword; the structural IR correctly excludes both. The
        # serve spec stays in signal_specs. See ADR-0027.
        "devour_matters",
        # blood_matters (CR 111.10g — the Blood token subtype, a discard-a-card-draw
        # artifact-token rummage engine) — the token-subtype synergy lane. REMOVED
        # from _IR_FLOOR_LANES and now fires from the STRUCTURAL IR alone: a
        # Blood-subtype make_token subject (the maker), a Blood SACRIFICE PAYOFF (a
        # `sacrifice` Effect OR a `sacrificed` Trigger whose subject Filter carries
        # the Blood subtype — Wedding Security, Blood Hypnotist; the token-subtype
        # synergy widening reads sacrifice subjects, not just maker subjects), and the
        # CHOOSE-LIST / GRANTED-ABILITY maker recovery (Transmutation Font's "create
        # your choice of a Blood token", Ceremonial Knife's quoted "create a Blood
        # token" grant — project._narrow_token_subtype_makers appends make_token
        # markers for the dropped subtypes). Floor-mirror-dependency == 0 (commander-
        # legal, floor lanes disabled): all 41 cards fire structurally with the floor
        # on or off (the 4 former floor-only gap cards now bind structurally). Its
        # "blood tokens?" _HAND_FLOOR producer is deleted; the serve spec stays in
        # signal_specs. The widening generalizes to clue/food/treasure (genuine
        # recall: +18/+10/+8 structural firings, all real makers/sac-payoffs), which
        # keep their floor for now. See ADR-0027.
        "blood_matters",
        # Group "tail-supplement" (ADR-0027 projection deepening) — the 1-2-card
        # synthesis tail: keys whose last residual is a named-mechanic reference phase
        # DROPS (a static grant, a payoff condition, a replacement clause, a delayed
        # trigger, a count operand), recovered by a NARROW supplement marker so the
        # lane fires from a NON-floor structural IR source. Floor-mirror-dep==0
        # (commander-legal, floor lanes disabled) for each; the boundary over-fires
        # (Bloodboil's "Crown of Madness" / Malanthrope's "Scavenge the Dead" ability
        # words, CR 207.2c, rules-lawyer-verified) are the cards the structural IR
        # correctly drops. Each key's oracle-regex producer is deleted; serve specs
        # stay in signal_specs. See ADR-0027.
        #   boast      ← `boast` keyword + event='other' payoff + "can boast" face
        #                amplifier marker (Birgi).
        #   connive    ← phase's connive effect + the applied/granted marker + the
        #                Scryfall connive keyword granter-lift (Security Bypass).
        #   end_the_turn ← phase's end_the_turn effect (supplement category reconciled
        #                — Obeka).
        #   exhaust    ← `exhaust` keyword + the exhaust payoff marker, now firing on
        #                the delayed-trigger-inside-activated shape (Pit Automaton).
        #   extra_end_step ← phase's extra_end effect + the "additional end step" face
        #                marker (Y'shtola; left _IR_FLOOR_LANES — it was never floored).
        #   madness    ← `madness` keyword + grant marker + "if it has madness" payoff
        #                marker (Anje); left _IR_FLOOR_LANES.
        #   mutate     ← `mutate` keyword + "if it has mutate" keyword-less payoff
        #                marker (Pollywog).
        #   phasing    ← `phasing` keyword + phase-out DOER markers + event='other'
        #                payoff marker (War Doctor); left _IR_FLOOR_LANES.
        #   trigger_doubling ← phase's trigger_doubling effect + the granted/quoted
        #                "triggers an additional time" face marker (The Masamune).
        #   experience ← GivePlayerCounter gainers + the op="experience" scaler
        #                operand (Atreus, Azula).
        #   explore    ← `explore` keyword (authoritative, 53 ⊇ 44 regex) + the
        #                event='other' explore payoff (Topography Tracker, Glowcap).
        #   foretell   ← `foretell` keyword + grant marker + Foretold-predicate payoff
        #                (Niko) + "to foretell" enabler marker (Karfell); left
        #                _IR_FLOOR_LANES.
        #   scavenge_fuel ← `scavenge` keyword + the "has scavenge" graveyard-grant
        #                face marker (Varolz, Young Deathclaws, Cave of Skulls).
        #   scry_surveil ← scried/surveiled triggers + event='other' payoff + the
        #                "if you would scry a number of cards" replacement face marker
        #                (Kenessos, Eligeth); left _IR_FLOOR_LANES.
        "boast_matters",
        "connive_matters",
        "end_the_turn",
        "exhaust_matters",
        "extra_end_step",
        "madness_matters",
        "mutate_matters",
        "phasing_matters",
        "trigger_doubling",
        "experience_matters",
        "explore_matters",
        "foretell_matters",
        "scavenge_fuel",
        "scry_surveil_matters",
        # Group "tail-supplement 2" (ADR-0027 projection deepening) — the next batch
        # of synthesis-tail keys whose residual cards phase DROPS, recovered by NARROW
        # supplement markers so the lane fires from a NON-floor structural IR source.
        # Floor-mirror-dep==0 (none is in _IR_FLOOR_LANES). NO-FLOOD held (only the
        # target keys grew, each by its gap count; no non-target key moved). Each key's
        # oracle-regex producer is deleted; serve specs stay hand-registered. See
        # ADR-0027.
        #   extra_draw_step / extra_upkeep ← phase's extra_draw/extra_upkeep effect
        #                categories + an `_EXTRA_BEGINNING_PHASE_GRANT` face marker
        #                emitting BOTH for "additional beginning phase" (CR 501.1 — a
        #                beginning phase contains untap/upkeep/draw), which phase
        #                mis-routes to extra_combats (Second Sun cycle) or drops
        #                (Cyclonus). extra_draw fired 0 in the IR before this marker.
        #   counter_control ← phase's `counter_spell` effect + a `counter_spell` face
        #                marker for "counter target … spell/ability" phase loses in a
        #                modal body (Fangkeeper, Ertai), an Aura quoted grant (Equinox,
        #                Sunken Field), or a coin_flip carrier (Goblin Artisans).
        #   cant_block_grant ← phase's `cant_block` effect + a `cant_block` face marker
        #                for the modal mode body (Breeches, Retreat to Valakut) and the
        #                granted quoted ability (Hostile Realm, Malicious Intent) phase
        #                drops (CR 509). The structural IR is broader-and-correct recall
        #                (176 vs the regex's 65 — "creatures can't block" etc.), not
        #                over-fire.
        #   land_exchange ← phase's `gain_control` over a Land subject + a raw fallback
        #                for the subject=None "exchange control of … land" shape
        #                (Political Trickery, Vedalken Plotter, Gauntlets). The IR
        #                correctly drops Sharkey (copies/taxes land abilities, never
        #                exchanges control — the regex's lone false positive).
        "extra_draw_step",
        "extra_upkeep",
        "counter_control",
        "cant_block_grant",
        "land_exchange",
        # Group "tail-supplement 3" (ADR-0027 projection deepening) — five more
        # synthesis-tail keys. Three (myriad_grant, convoke_matters, tapped_matters)
        # were REMOVED from _IR_FLOOR_LANES and now fire from the STRUCTURAL IR alone;
        # floor-mirror-dependency == 0 for each (the floor-dependent gap cards now bind
        # structurally). The other two (typed_anthem_multi, life_total_set) were never
        # floored. NO-FLOOD held (only the target keys grew; no non-target key moved —
        # the Masako tapped-grant marker uses category="tap" so it never trips the
        # creatures_matter team-anthem read). Each key's oracle-regex producer is
        # deleted; serve specs stay hand-registered. See ADR-0027.
        #   myriad_grant ← `myriad` keyword (makers) + grant_keyword counter_kind=
        #                'myriad' (granters) + a copy-exception conferred marker
        #                (Muddle). The "\bmyriad\b" floor over-fired on the "The Myriad
        #                Pools" card NAME — the IR correctly drops it.
        #   convoke_matters ← `convoke` keyword (makers) + cast_with_keyword counter_
        #                kind='convoke' granters + grant_spell_ability/cast-trigger
        #                convoke-raw payoff markers.
        #   tapped_matters ← a Tapped(controller='you') Filter predicate read in the
        #                effect subject / amount.subject COUNT / condition.subject
        #                threshold slots, plus a `_TAPPED_GRANT` marker (Masako's
        #                dropped subject + Harvest Season's dropped count predicate).
        #   typed_anthem_multi ← a pump over a creature Filter naming 2+ subtypes (AnyOf
        #                node OR flat subtypes tuple) + a "that's a X … or a Y" raw
        #                fallback. The pump-only gate drops Paladin Danse (a keyword
        #                grant, not a +X/+X anthem), the regex's over-fire.
        #   life_total_set ← phase's set_life effect + the exchange/redistribute
        #                _NAMED_MECHANICS recategorizations + a `_LIFE_TOTAL_SET` marker
        #                for "life total becomes <X>" + "double … life total". The IR
        #                drops Heartless Hidetsugu (a damage effect), the over-fire.
        "myriad_grant",
        "convoke_matters",
        "tapped_matters",
        "typed_anthem_multi",
        "life_total_set",
        # Group "tail-supplement 4" (ADR-0027 projection deepening) — five floored
        # synthesis-tail keys, all REMOVED from _IR_FLOOR_LANES; floor-mirror-dep == 0
        # for each (the floor-dependent gap cards now bind structurally). NO-FLOOD held
        # (only the target keys grew; no non-target key moved). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. See ADR-0027.
        #   energy_matters ← phase's `energy` effect (gainenergy producers) + an
        #                `_ENERGY_REF` ({e}) marker for the sinks / "whenever you get
        #                {E}" payoffs / doublers phase loses. {e} is unambiguous (real
        #                energy cards only).
        #   rad_counter_matters ← phase's `rad_counter` effect / rad place_counter + a
        #                `_RAD_REF` ("rad counter(s)") marker for the clauses phase
        #                mangles (rad kind dropped to '', counter_doubling, dropped).
        #   suspect_matters ← phase's `suspect` effect (leading-verb) + a `_SUSPECT_REF`
        #                marker for the verb mid-clause/granted + the "suspected" state.
        #                The "(?! counter)" drops Investigator's Journal's "suspect
        #                counter" (a same-named counter type, CR 701.60b).
        #   venture_matters ← phase's venture/take-initiative effect + a
        #                completedadungeon/isinitiative condition read + a
        #                trigger_doubling-over-dungeons read + a `_VENTURE_REF`
        #                dropped-clause marker (gated out of a restriction effect so
        #                Keen-Eared Sentry's opponent anti-venture hate stays out).
        #   crimes_matter ← phase's commit_crime trigger event (the trigger form) + a
        #                `crime` condition-form marker ("(if|as long as) you've
        #                committed a crime") for the payoff phase has no kind for.
        "energy_matters",
        "rad_counter_matters",
        "suspect_matters",
        "venture_matters",
        "crimes_matter",
        # group_mana ← phase emits scope='each' for ZERO ramp effects (the recipient
        # field doesn't exist), so the dead each-scope arm is replaced by a
        # non-controller-recipient discriminator (_GROUP_MANA_RAW) on the ramp effect
        # raw — "each/that/the active/chosen player … adds {" — separating symmetric
        # group ramp (Magus of the Vineyard, Yurlok, Valleymaker, Tangleroot) from
        # your-own ramp. NOT in _IR_FLOOR_LANES; its SWEEP row is deleted, serve
        # hand-registered. gap=0, over=0 (all 8 cards bind structurally). See ADR-0027.
        "group_mana",
        # low_power_matters ← a non-dynamic PtComparison:Power:LE/LT predicate on a
        # you-controller Creature Filter (read by _predicate_build_around_lanes). The
        # recursion cards (Alesha, Reveillark, Vesperlark, Shirei — "return a creature
        # with power N or less") carry the predicate natively; phase DROPS it on the
        # buff/etb subject shapes, recovered by a `_LOW_POWER_REF` marker that rebuilds
        # the Power:LE subject (category="tap" so it stays out of the creatures_matter
        # team-anthem read). REMOVED from _IR_FLOOR_LANES; floor-mirror-dep == 0
        # (with_floor 33 == without_floor 33). NO-FLOOD held. See ADR-0027.
        "low_power_matters",
        # life_payment_insurance ← a repeatable "Pay N life:" ACTIVATION COST
        # ("paylife" in Ability.cost — Selenia, Beledros, the fetchlands; genuine recall
        # the narrow "pay N life:" regex missed) + a `life_payment` marker for the
        # misparsed cost (Arco-Flagellant, Hibernation Sliver) and the conferred quoted
        # "…Pay 1 life: Draw" ability phase drops (Underworld Connections, the volvers).
        # NOT in _IR_FLOOR_LANES; gap=0, over=36 (all genuine paylife-cost recall).
        # NO-FLOOD held (only this key grew, +7). See ADR-0027.
        "life_payment_insurance",
        # sacrifice_matters ← a you-sacrifice EFFECT (scope not opp/each OR a "you"
        # subject controller; a non-land subject; not a forced-opponent edict raw),
        # a "sacrificed" trigger payoff, the Casualty keyword, a subject-less / modal
        # raw fallback, and the project markers (additional-cost incl. Choice/Kicker,
        # granted/quoted outlet, casualty grant, free-spell pitch, keyworded-cost sac,
        # pay-or-die, discard+sac, bullet, cumulative-upkeep). NOT in _IR_FLOOR_LANES;
        # floor-mirror-dep == 0 (floor-ON 1279 == floor-OFF 1279). The deleted broad
        # regex over-fired on land-sac, edicts, "controller may sacrifice",
        # Ward—Sacrifice, and reanimation engines with NO sacrifice; the floor-disabled
        # residual re-adjudicates to all over-fire bar one card (Phyrexian Soulgorger,
        # a cumulative-upkeep cost phase parses as a SelfRef "sacrifice it"). NO-FLOOD
        # held (only sacrifice_matters / edict_matters grew; edict_matters +107 is the
        # recovered-from-mis-scope recall, plus 3 typed-sac-subject recall gains on
        # food/legends/type_matters — all correct). See ADR-0027.
        "sacrifice_matters",
        # lifeloss_matters ← a structured `lose_life` Effect (scope you→you else
        # opponents — the drain / self-loss split), a `life_payment` marker + a paylife
        # ACTIVATION COST buying a non-ramp engine (the self life-as-resource half), a
        # `life_lost` trigger payoff, and the project _lifeloss_markers (pay-life
        # additional cost / pitch / keyworded-cost / cumulative-upkeep / tax / Defiler
        # / granted / modal / dice / choose self-loss + the modal / granted /
        # lost-life-this-turn / dice drain). extort / afflict / spectacle are removed
        # from the regex keyword path (the IR covers them structurally). NOT in
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON 1262 == floor-OFF 1262). The
        # deleted broad regex over-fired on pay-life MANA sources (painlands etc.),
        # Ward—Pay life (the opponent pays), and lifeGAIN-context. The floor-disabled
        # residual re-adjudicates to ~all over-fire bar ~3 deep edge cards (a
        # value-paylife with no "if you do" anchor, a replacement-effect life loss).
        # NO-FLOOD held (only lifeloss_matters grew). See ADR-0027.
        "lifeloss_matters",
        # removal_matters ← phase's `destroy` / `damage` effect with a SINGLE-TARGET
        # permanent SUBJECT (card_types ∩ permanent types OR a permanent subtype, CR
        # 115.1), the quoted-grant-ability recursion (an Aura/Equipment granting "{T}:
        # Destroy/deal damage to target …" — Manriki-Gusari, Lavamancer's Skill), the
        # subtype-only destroy ("destroy target Wall"), the modal destroy/damage bullet
        # (subject recovered via the modal-split recursion), and the
        # removal-target-subject recovery (Combo Attack, Broken Visage). The MASS form
        # ("destroy/deal damage to EACH/ALL …" — DamageAll/DestroyAll, counter_kind ==
        # "all") is a BOARD WIPE (CR 115.10), EXCLUDED here and served by the
        # mass_removal lane; land destruction routes to land_destruction. NOT in
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON 2533 == floor-OFF 2533, the
        # IR removal arm reads no floor detector). The deleted broad regex (the
        # _HAND_FLOOR row + the SWEEP_DETECTORS row) over-fired by folding board wipes
        # ("destroy all/each", "damage divided") and land destruction into removal —
        # the A-B (regex-only) residual re-adjudicates to ~259/275 over-fire (mass /
        # land / divided), the ~16 remaining genuine single-target gaps being niche
        # sub-shapes (coin-flip-wrapped destroy, clone-exception grant, conditional
        # edicts). NO-FLOOD held: the migration DROPS the 470 board-wipe/land over-fires
        # and ADDS ~218 genuine single-target recall the narrow regex missed ("destroy
        # X/two/any-number-of target", fight-style "deals damage equal to its power to
        # target creature", granted Aura/Equipment removal). See ADR-0027.
        "removal_matters",
        # Group "sweep" (ADR-0027 small-residual close) — five low-residual keys closed
        # by the sweep markers (prior commit). Four left _IR_FLOOR_LANES and
        # now fire from the STRUCTURAL IR alone; floor-mirror-dep == 0 for each
        # (extract_signals_ir reproduces production with the floor lanes disabled).
        # NO-FLOOD held (only the target keys grew; no non-target key moved). Each key's
        # oracle-regex producer is deleted; serve specs stay hand-registered. ADR-0027.
        #   oil_counter_matters ← phase's place_counter(counter_kind='oil') placer +
        #                an `_OIL_REF` ("oil counter(s)") payoff marker (Urabrask's
        #                Anointer, Kuldotha Cackler — the count-operand/condition phase
        #                drops). The 'oil' kind never leaks into counters_matter (p1p1).
        #   mass_death_payoff ← a `_MASS_DEATH_REF` ("creatures that died this turn")
        #                count-operand marker (Khabál Ghoul, Gadrak, Spymaster's Vault).
        #   starting_life_matters ← a `_STARTING_LIFE_REF` ("starting life total")
        #                compare marker. The broad regex's "life total is greater/less"
        #                arm over-fired on unrelated thresholds (Elderscale Wurm's
        #                "less than 7", Sigarda's Splendor's "last noted life total"),
        #                which the tight IR marker correctly drops (CR 103.4).
        #   cycling_matters ← phase's `cycled` trigger + a `cycling` marker (the
        #                _narrow_trigger_other_refs arm for the "cycle or discard"
        #                payoff trigger phase flattens to event='other', plus the
        #                _dropped_static_markers arm for the cards phase truncates the
        #                trigger phrase off entirely — Pitiless Vizier, Zenith Seeker).
        #   dice_matters ← phase's native roll_die effect + a `roll_die` marker (the
        #                trigger-other "whenever you roll" payoff + the dropped-static
        #                "Roll two d6 and choose" SPELL / "Roll a d8:" COST / "reroll").
        "oil_counter_matters",
        "mass_death_payoff",
        "starting_life_matters",
        "cycling_matters",
        "dice_matters",
        # Group "sweep 2" (ADR-0027 small-residual close) — five more low-residual keys
        # closed by the conferred/dropped-static markers (prior commit). Four left
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 for cascade/changeling/regenerate
        # (floor-ON == floor-OFF), and undying_persist's +1 floor-dependency is the
        # "Undying Flames" NAME over-fire the structural IR correctly drops (parallel to
        # the madness "Crown of Madness" / devour "Devour Intellect" name/word over-fire
        # precedents). creature_cast_trigger was never floored. NO-FLOOD held (only the
        # target keys grew; no non-target key moved). The migrations are broader-and-
        # correct RECALL, not over-fire: creature_cast_trigger +28 (qualified-subject
        # triggers — "green/Vampire/Eldrazi creature spell", "nonlegendary creature
        # spell with flying" — the bare "casts a creature spell" regex missed). Each
        # key's oracle-regex producer is deleted; serve specs stay hand-spec'd.
        #   cascade_matters ← Scryfall `cascade` keyword + a `_CASCADE_GRANT` marker for
        #                the keyword-less granters/references (Maelstrom Nexus, Yidris,
        #                Averna, The First Doctor's "spell with cascade" payoff).
        #   changeling_matters ← Scryfall `changeling` keyword + a `_CHANGELING_REF`
        #                ("changeling" / "is every creature type") marker (Maskwood
        #                Nexus, Mistform Ultimus, Arachnoform, Omo's everything ctr).
        #   regenerate_matters ← phase's `regenerate` effect + a `_REGENERATE_REF`
        #                marker for the granted/quoted/replacement regenerate (Tribal
        #                Golem, Mossbridge Troll, the Holy Nimbus pair).
        #   undying_persist_matters ← Scryfall undying/persist keywords + a
        #                `_UNDYING_PERSIST_GRANT` marker for the keyword-less granters
        #                (Mikaeus, Cauldron of Souls, the Scarecrows). Drops "Undying
        #                Flames" (the name over-fire).
        #   creature_cast_trigger ← a cast_spell trigger with a Creature subject + an
        #                effect-raw / face-oracle "whenever/when [player] casts a …
        #                creature spell" scan (Wildgrowth Archaic's enters-with
        #                replacement, Glimpse of Nature's delayed trigger, Blink's
        #                token, Garruk's emblem). Anchored past mana-restrictions /
        #                different-trigger may-cast actions (Cavern of Souls, Dragon-
        #                Kami's Egg).
        "cascade_matters",
        "changeling_matters",
        "regenerate_matters",
        "undying_persist_matters",
        "creature_cast_trigger",
        # fight_matters ← phase's `fight` effect + a `_FIGHT_REF` dropped-static marker
        # (granted "it fights" / quoted-token / modal "Fight!" / emblem / symmetric
        # "fight each other") + a `_FIGHT_RAW` face-level fallback (the Aftermath DFC
        # phase doesn't project — Prepare // Fight). NOT in _IR_FLOOR_LANES;
        # floor-mirror-dep == 0 (132 == 132). NO-FLOOD held. The migration is broader-
        # and-correct recall (+5: Grothama, Ezuri's Predation, Time to Feed, Kraul
        # Harpooner, Skophos Maze-Warden — granted/token fights the narrow regex
        # missed). Its SWEEP_DETECTORS row is deleted; serve hand-spec'd. CR 701.12.
        "fight_matters",
        # food_matters / treasure_matters ← the generalized blood_matters token-subtype
        # widening: a Food/Treasure-subtype make_token MAKER (the die-roll/vote/choice
        # branch + the Aftermath-DFC face fallback), a "Sacrifice a Food/Treasure" SAC
        # PAYOFF, and a `token_subtype_ref` "Foods/Treasures you control" / "was a
        # Treasure" / "is a Food" CARES-ABOUT marker (project._narrow_token_subtype_
        # makers + _dropped_static_markers, read via _TOKEN_SUBTYPE_KEYS). REMOVED from
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (floor-ON == floor-OFF: 157/324).
        # NO-FLOOD held (token_maker/tokens_matter/creatures_matter unchanged — the
        # markers route ONLY through _TOKEN_SUBTYPE_KEYS to the 4 subtype lanes). The
        # migration is broader-and-correct recall (+4 food sac-payoffs / +27 treasure
        # make_token-SUBJECT makers the narrow "create … <Subtype> token" regex missed —
        # Old Gnawbone, Prismari Command, Wanted Scoundrels). CR 111.10 / 701.16.
        "food_matters",
        "treasure_matters",
        # saga_matters ← a `_SAGA_REF` ("lore counter" / "Saga you control") dropped-
        # static face marker (lore-counter manipulation — Keldon Warcaller, Satsuki,
        # Garnet; chapter-scaling payoff Sagas; the Saga-payoff commander Tom Bombadil;
        # non-Saga lore engines — Myth Realized, Mind Unbound). REMOVED from
        # _IR_FLOOR_LANES; floor-mirror-dep == 0 (17 == 17). NO-FLOOD held: mapping
        # counter_kind='lore' → saga_matters would have flooded the lane with all 186
        # Sagas (phase synthesizes a lore placement for every Saga's chapter
        # advancement); the reminder-stripped face anchor fires ONLY on the build-around
        # tell (a vanilla Saga's reminder-only lore mention is excluded), exactly
        # mirroring the regex (residual 0, ir_only 0). Its SWEEP_DETECTORS row is
        # deleted; serve hand-spec'd. CR 714.
        "saga_matters",
        # Group "cares-about kept-detector" (ADR-0027) — 7 cares-about lanes phase
        # v0.1.19 doesn't structure as a card-property payoff (rules-lawyer-verified: no
        # reference shape in the parse). MOVED from _IR_FLOOR_LANES (a reused production
        # floor Detector) to _IR_KEPT_DETECTORS (a dedicated IR-path word mirror), which
        # zeroes floor-mirror-dep by construction — the lane no longer toggles with
        # _IR_FLOOR_LANES. Each retains its EXISTING structural bind too (add() dedups):
        # devotion/party ← the amount.op=="devotion"/"party" count operand (the scaling
        # payoffs); multicolor/colorless ← the ColorCount subject-Filter predicates (the
        # "<multicolored|colorless> permanent/card you control" build-arounds — the kept
        # mirror is broader-and-correct: it adds Ancient Stirrings / Obscura Charm /
        # Dragon Arch "card" refs the narrow regex missed); historic ← the "Historic"
        # subject-Filter predicate. initiative (CR 720) / attractions (CR 717) have no
        # structural form — the word IS the build-around tell. Floor-mirror-dep == 0 for
        # all 7; regex-path parity exact (regex_only_resid == 0); NO-FLOOD (0 keys'
        # firing counts changed by the floor->kept move). Their _HAND_FLOOR rows
        # (devotion/historic/party/initiative/multicolor/colorless) + the attractions
        # SWEEP_DETECTORS row are deleted; serve specs survive. CR 700.5/700.6/702.114.
        "devotion_matters",
        "party_matters",
        "historic_matters",
        "multicolor_matters",
        "colorless_matters",
        "initiative_matters",
        "attractions_matter",
        # Group "SWEEP batch" (ADR-0027) — 11 keys whose forms phase scatters across
        # categories it doesn't unify (a count operand it drops, a trigger flattened to
        # event='other', a grant whose subject it folds, a zone-exile with subject=None,
        # a recipient it drops). Each fires from its EXISTING structural bind PLUS a
        # dedicated _IR_KEPT_DETECTORS word mirror (or a raw discriminator), reproducing
        # the deleted regex exactly (regex_only_resid == 0). rules-lawyer-verified.
        #   donate_matters ← a gain_control effect whose raw names an another-player
        #                RECIPIENT (_DONATE_RAW; phase drops the recipient to
        #                scope='any'). Replaces the dead scope=='opp' arm. CR 701.12.
        #   minus_counters_matter ← place_counter(m1m1) maker + a "-1/-1 counter" kept
        #                mirror for the remove/cost/ward/"with a counter" payoffs.
        #   team_evasion_grant ← the generic creatures-you-control grant_keyword +
        #                a kept mirror for subtype/color-scoped grants (Slivers have
        #                flying). +15 pump+grant recall the narrow regex missed.
        #   hand_disruption ← the opp-reveal trigger + a kept mirror for "look at
        #                hand" / "play with hands revealed" / modal reveal-discard.
        #                +6 recall.
        #   commander_matters ← the IsCommander predicate + a kept mirror for Background
        #                grants / "commander damage". Moved floor->kept. +13 recall.
        #   domain_matters ← amount.op=='domain' + a "\bdomain\b|basic land types" kept
        #                mirror. Moved floor->kept (floor-mirror-dep -> 0). CR 700.3.
        #   opponent_exile_matters ← GRAVEYARD HATE alone (CR 406) from a kept mirror;
        #                the old permanent-exile arm mis-fired on Path-to-Exile
        #                removal and is removed (so the 19 ir_only removal cards
        #                correctly leave the lane). phase scatters the forms across
        #                exile / cheat_play / pump.
        #   exalted_lone_attacker ← the `exalted` keyword + an "attacks alone|exalted"
        #                kept mirror. Moved floor->kept. CR 702.83.
        #   speed_matters ← phase's `speed` doer + a "start your engines|max speed|your
        #                speed" kept mirror. Moved floor->kept. CR 702.178/702.179.
        #   tap_untap_matters ← the `taps` (tap-for-mana) trigger + a "becomes tapped/
        #                untapped" kept mirror (Inspired flattens to event='other').
        #                +65 tap-for-mana recall the regex missed.
        #   reanimator ← a creature whose `reanimate` returns CREATURE cards from a
        #                graveyard (incl. a raw fallback for the subject phase drops —
        #                Isareth, Beacon of Unrest). The regex conflated this with
        #                "cast a spell FROM a graveyard" (flashback/escape — CR 702.34
        #                casting ≠ reanimation), which the structural IR correctly
        #                drops; the 38 regex-only residual re-adjudicates to all
        #                over-fire (flashback/escape/unearth/self-recursion). +25
        #                genuine creature-reanimation recall (the raw fallback). CR 603.
        # Floor-mirror-dep == 0 for all 11 (regex-path parity exact). NO-FLOOD: an
        # in-process before/after over the commander-legal corpus changed ZERO
        # non-target key firing counts (the removed opponent_exile permanent-exile arm
        # only dropped
        # that lane's mis-fires; exile_removal — the sibling on the same arm — is
        # unchanged). color_hoser was the 12th batch key — SKIPPED: 18 genuine gaps
        # (colored counterspells with subject=None, NotColor anthems on cat='pump',
        # destroy-target-color with dropped predicates, mass-bounce/restriction
        # categories the bind doesn't cover) need a deeper IR-bind widening, not a clean
        # over-fire migration. See ADR-0027.
        "donate_matters",
        "minus_counters_matter",
        "team_evasion_grant",
        "hand_disruption",
        "commander_matters",
        "domain_matters",
        "opponent_exile_matters",
        "exalted_lone_attacker",
        "speed_matters",
        "tap_untap_matters",
        "reanimator",
        # Group "SWEEP-floor->kept" (ADR-0027 sweep batch) — cares-about lanes phase
        # v0.1.19 leaves TEXTUAL, each with a load-bearing floor mirror so it MOVES
        # from _IR_FLOOR_LANES to a dedicated _IR_KEPT_DETECTORS word mirror while
        # KEEPING its existing structural / keyword IR bind (add() dedups). The move
        # zeroes floor-mirror-dep by construction (floor_ON == floor_OFF for all 4).
        # legends_matter ← HasSupertype:Legendary predicate; lands_matter ←
        # amount.subject=Land operand; poison_matters ← infect/toxic/poisonous
        # keywords; suspend_matters ← `suspend` keyword. Each mirror reproduces the
        # deleted regex exactly (regex_only_resid == 0). NO-FLOOD: floor->kept changed
        # one voltron tell (-1: The Balrog correctly silenced via legends IR recall).
        # See ADR-0027.
        "legends_matter",
        "lands_matter",
        "poison_matters",
        "suspend_matters",
        # Group "damage cluster" (ADR-0027 projection deepening) — the damage-doubling
        # half of the direct_damage <-> damage_doubling decoupling. damage_doubling
        # fires from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-
        # dep == 0): phase's `damage_doubling` DamageDone-replacement category, now
        # deepened to cover Triple (Fiery Emancipation, City on Fire) and the nested
        # AddTargetReplacement / CreateDamageReplacement amplifiers (Goblin Goliath,
        # Isengard Unleashed, Desperate Gambit), plus a `damage_doubling` face marker
        # for the modification phase dropped entirely (Neriv's entered-this-turn
        # condition, Jeska's Unimplemented loyalty mode, Borborygmos/Surtland's "deals
        # twice that much" riders). The IR is strictly broader-and-correct ("double all
        # damage … would deal" — Collective Inferno, Raphael, Wolverine — regex
        # missed) and EXCLUDES the regex's "prevent half that damage" HALVING over-fire
        # (Dark Sphere, CR 615 prevention — the opposite of a doubler, the lone regex-
        # only residual the structural IR correctly drops). The projection fix ALSO
        # nets out the coupling's other direction: the doublers (Furnace of Rath,
        # Gratuitous Violence, Neriv, Goblin Goliath) no longer carry the spurious
        # direct_damage the deleted synthesized `damage` effect over-fired in the IR.
        # direct_damage ITSELF stays on regex — its 52 burn gaps (Keranos, Koth,
        # Tibalt — damage buried in a reveal/loyalty/Unimplemented body) need a deeper
        # damage-recovery pass, not a clean over-fire migration. Its SWEEP_DETECTORS
        # row is deleted; the serve spec is hand-registered. See ADR-0027.
        "damage_doubling",
        # Group "combat-forcing" (ADR-0027 projection deepening) — the goad half of
        # the goad_matters <-> forced_attack disentanglement (CR 701.38 goad redirect-
        # payoff vs CR 508.1g self-force). goad_matters fires from the STRUCTURAL IR
        # alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0): the Scryfall `goad`
        # keyword + phase's `goad_all` effect + a `_GOAD_REWARD_REF` face marker (the
        # redirect-reward conditions phase flattens to raw — "attacks one of your
        # opponents", "a player other than you", "whenever a player attacks", Kazuul's
        # defending-player payoff) + the goad-style single-target political force
        # (`_GOAD_STYLE_FORCE` lifting phase's force_attack effect on "target creature
        # … attacks … if able" — Boiling Blood, Incite, Basandra, Alluring Siren). The
        # disentanglement is structural: the self/team "attacks each combat if able"
        # static stays on forced_attack (its own lane); the single-target / redirect-
        # reward forms open goad. regex-only residual 45 -> 2 (Boros Battleshaper's
        # attack-OR-block manipulation → cant_block, Tower Above's "blocks if able" →
        # force_block/lure — both correct IR exclusions). forced_attack ITSELF stays on
        # regex — its 23 "didn't attack this turn" PUNISHER-incentive gaps (Erg
        # Raiders, Kratos, Angel's Trumpet) are a distinct sub-concept the IR doesn't
        # bind, not a clean over-fire migration; the coupling's over-fire direction
        # (regex goad over-firing on self-force / blocks) is resolved structurally. The
        # two goad _DETECTORS / _HAND_FLOOR producers are deleted; the serve spec is
        # registered. See ADR-0027.
        "goad_matters",
        # Group "spell-copy" (ADR-0027 projection deepening) — spell_copy_matters fires
        # from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0):
        # phase's `spell_copy` effect (CopySpell + CastCopyOfCard) + the storm/replicate
        # /conspire/casualty Scryfall keywords (the HAVERS, _IR_KEYWORD_MAP) + a
        # `_COPY_SPELL_REF` face marker (project._dropped_static_markers) for the
        # granted/quoted/conditional copy phase folds into a modal / coin-flip / storm-
        # reminder carrier (God-Eternal Kefnet, Twinferno, Krark, Pyromancer's Goggles)
        # AND the keyword-less GRANTERS ("…spell you cast has replicate/casualty/storm/
        # demonstrate" — Anhelo, Djinn Illuminatus, Wort, Threefold Signal, The Twelfth
        # Doctor). The structural IR EXCLUDES the deleted regex's `\bstorm\b` card-NAME
        # over-fire — 20 of the 21 regex-only residual are cards merely NAMED "… Storm"
        # (Comet Storm, Arrow Storm, Tropical Storm — burn/effects, not the keyword),
        # which the IR correctly drops; the 21st (Refuse // Cooperate) is an irreducible
        # phase gap (phase has no record for the Aftermath back face that carries "Copy
        # target instant or sorcery spell"). The IR_ONLY (121) are 100% genuine copy
        # cards (all mention copy / a copy-keyword) the narrow regex missed. Both regex
        # producers (the _HAND_FLOOR + the SWEEP row) are deleted; the serve spec is
        # hand-registered. See ADR-0027.
        "spell_copy_matters",
        # Group "counters" (ADR-0027 counters_matter pass 2) — counters_matter fires
        # from the STRUCTURAL IR alone (NOT in _IR_FLOOR_LANES; floor-mirror-dep == 0,
        # floor-ON == floor-OFF). It fires on ANY +1/+1 counter PLACEMENT regardless
        # of recipient (self / on-others / on-attacking / distribute-among — all are
        # sources, CR 122.1 / 122.6) and on a "has/with a +1/+1 counter" PAYOFF
        # reference. Sources: phase's place_counter(p1p1) + counter_move(p1p1) +
        # proliferate + the counter_added trigger + the count-form payoff (the Counters
        # predicate on amount.subject / e.subject) + the amass/fabricate/devour modal
        # fan-out + the counters_have_ref marker (project._narrow_counter_refs /
        # _counter_face_marker — the placement/payoff phase folds into a coin_flip /
        # roll_die / vote / pay-cost / distribute / trimmed-grant / reanimate-rider
        # carrier or drops entirely) + the +1/+1 keyword block (mentor/training/
        # modular/bolster/evolve/outlast/renown/adapt/graft/riot/bloodthirst/
        # fabricate/sunburst/tribute/unleash/ravenous/reinforce/scavenge/undying/
        # dethrone/devour — every one verified to project a place_counter / carry its
        # keyword, 0-miss). LOSE == 0 in production config (floor lanes ON): the IR
        # fires counters_matter on ALL 1895 cards the regex did, plus 1243 the narrow
        # regex missed (genuine recall; IR 3138 vs regex 1895). All regex producers
        # (the count/board-wide _DETECTORS row, the two _HAND_FLOOR rows — "power
        # greater than its base power" twin + the any-counter HAVE form — the +1/+1
        # keyword block in _DIRECT_KEYWORD_SIGNALS, and the two self-/have-counter
        # add() calls) are deleted; the serve spec stays hand-registered. The
        # counter_place_trigger / counter_distribute / self_counter_grow SWEEP rows
        # (their own widen lanes) are independent and stay regex. See ADR-0027.
        "counters_matter",
        # Group "tranche2-B" (ADR-0027) — 5 keys phase v0.1.19 NOW structures, each
        # fires from the STRUCTURAL IR alone (NONE in _IR_FLOOR_LANES; floor-mirror-dep
        # == 0 by construction — no key reads a floor detector). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. NO-FLOOD held (only the
        # target keys' firing counts changed; no non-target key moved). See ADR-0027.
        #   mass_bounce ← a `bounce` Effect with counter_kind=='all' (the mass
        #                discriminator, same convention as the mass-untap arm) on a
        #                generic Creature/Permanent subject (_is_mass_bounce_subject),
        #                excluding graveyard recursion (InZone/Owned predicate or a
        #                graveyard/library zone — Garna, Wrenn, Empty the Catacombs).
        #                Single-target bounce (Cyclonic Rift base, counter_kind=='')
        #                stays out. Kept residual: Cyclonic Rift's overload 'each' mode
        #                (a phase modal-alt-cost parse drop) + artifact/enchantment-only
        #                sweeps (Rebuild, Reduce to Dreams — out of the Creature/
        #                Permanent subject scope). CR 115.10.
        #   permanent_etb ← an `etb` Trigger whose subject Filter carries 'Permanent'
        #                and controller=='you' (Amareth). BROADER-and-correct vs the
        #                narrow word-order regex (+12 generic-permanent-ETB engines:
        #                Cloudstone Curio, Kodama, Yoshimaru). creature_etb (Creature
        #                subject) and an opp-scoped punisher stay out. CR 603.
        #   team_buff ← the `grant_keyword` Effect (one per keyword, keyword in
        #                counter_kind) on a GENERIC "creatures you control" subject
        #                (_is_team_buff_grant tolerates NonToken/Another/Other;
        #                _TEAM_BUFF_GRANT_KW is the evergreen team-keyword set).
        #                Co-fires with team_evasion_grant / protection_grant (subsets;
        #                seen-set dedups). The structural IR drops the regex's tribal /
        #                color / attacking / single-target over-fires (it matched the
        #                "creatures you control have <kw>" mass_grant roll-up text even
        #                when the real grant was narrowed) — 0 genuine generic anthems
        #                lost. The summary ck=='mass_grant' roll-up Effect is ignored.
        #   destroy_legendary ← a `destroy` Effect whose subject Filter carries the
        #                exact HasSupertype:Legendary predicate (Bounty Agent, Tsabo
        #                Tavoc; the mass "destroy each legendary" form — Invasion of
        #                Fiora — rides counter_kind=='all' with the same predicate). The
        #                exact string is the discriminator: a generic "destroy target
        #                creature" lacks it; NotSupertype:Legendary ("nonlegendary" —
        #                Cast Down, One Ring) is the OPPOSITE and stays out. ~0
        #                residual. CR 205.4a. is_widen_of removal_matters preserved.
        #   power_double ← a `pump`/`pump_target` Effect whose raw carries the
        #                "double … power" / "power … doubled" word-mirror
        #                (_POWER_DOUBLE_RAW). phase sets no multiply quantity for P/T
        #                doubling (amount=None), so the category + raw is the
        #                discriminator (NOT the over-firing Scryfall `Double` keyword,
        #                which mostly doubles damage/counters/tokens). Single-target
        #                doublers (Unleash Fury) land in pump_target; mass doublers
        #                (Unnatural Growth) in pump. Kept residual: a Saga chapter
        #                (Roar of Endless Song, phase structures as saga steps).
        "mass_bounce",
        "permanent_etb",
        "team_buff",
        "destroy_legendary",
        "power_double",
        # Group "tranche2-A structural sweeps" (ADR-0027) — four removal/buff lanes
        # phase v0.1.60 now structures cleanly, each migrated from a STRUCTURAL /
        # cost-bearing IR source (NONE are in _IR_FLOOR_LANES; floor-disabled IR ==
        # floor-on IR for all four). The IR is strictly broader-and-cleaner than the
        # deleted regex — it drops the regex's over-fires and adds the typed/predicate
        # cases the narrow regex missed.
        #  • activated_draw ← Ability(kind=='activated') with 'tap' in cost + a draw
        #    Effect (the {T}: gate the cost field now supplies; the loose 'tap' catches
        #    the {N}{T}: draw rocks the literal `{t}: draw a card` regex missed). The
        #    5 regex-only are GRANTED {T}:Draw abilities phase folds into the granter.
        #  • anthem_static ← Ability(kind=='static') pump over a creature GROUP,
        #    factor>=0 (keeps +0/+N toughness anthems), scope!='opp' (drops the debuff
        #    half of a split anthem). kind=='static' drops the 303 EOT/one-shot pump
        #    over-fires the regex caught (Charge, planeswalker minus abilities); a
        #    ~15-card emblem/phase-parse-gap residual is the accepted tail.
        #  • aoe_ping ← a counter_kind=='all' damage Effect over a Creature subject on
        #    a REPEATABLE-FRAME ability (activated tap/mana cost without sacself, or an
        #    upkeep/end_step/cast_spell trigger). Drops the regex's sacself one-shot
        #    pingers (Bloodfire Colossus) and one-shot ETB sweeps (Chaos Maw).
        #  • mass_removal ← a counter_kind=='all' destroy/exile/damage of a battlefield
        #    permanent type, or a negative all-creatures pump (Languish/Toxic Deluge).
        #    Battlefield-type + graveyard-zone gates exclude land destruction
        #    (Armageddon) and mass reanimation/GY-hate (Living Death, Gerrard).
        "activated_draw",
        "anthem_static",
        "aoe_ping",
        "mass_removal",
        # Group "tranche2-C" (ADR-0027) — five combat/engine lanes, each fires from a
        # STRUCTURAL IR arm (none is in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them).
        # NO-FLOOD held (only the target keys' counts moved). Each key's oracle-regex
        # producer is deleted; serve specs stay hand-registered. See ADR-0027.
        #   exert_matters ← a grant_keyword effect with counter_kind=='vigilance' over
        #                a generic-creature-you-control subject (the team-vigilance
        #                enabler that neutralizes exert's "won't untap" downside —
        #                Heliod, Always Watching, Brave the Sands; _is_generic_creature_
        #                filter is predicate-tolerant so Heliod's `Another` / Always
        #                Watching's `NonToken` board counts, but the subtype-scoped
        #                Golem/Sliver/Warrior grants and Kytheon's single-target are
        #                excluded) + a Johan "attacking doesn't cause … to tap" kept
        #                word mirror. Its _HAND_FLOOR producer is deleted.
        #   self_pump ← an ACTIVATED pump_target / place_counter(p1p1) effect on the
        #                SELF (subject=None) — the firebreathing mana-sink (Shivan
        #                Dragon) and the activated +1/+1-counter body (Walking Ballista,
        #                Crystalline Crawler). The ab.kind=='activated' gate excludes
        #                manlands (animate/ramp) and one-shot spell pumps; subject=None
        #                excludes granters ("target creature gets…"). Its SWEEP row is
        #                deleted; its existing serve spec is repointed via regex=.
        #   tapper_engine ← a `tap` Effect with a target subject Filter (the repeatable
        #                tapper — Icy Manipulator, Opposition, Master Decoy; tap-as-cost
        #                lives in Ability.cost and emits no tap Effect, so subject!=None
        #                never leaks cost taps) + a "doesn't untap" restriction-raw
        #                branch (Frost Titan). Scope 'any' (broad target tap; tap_down
        #                may co-fire, OK). Its SWEEP row is deleted; serve hand-spec'd.
        #   recast_etb ← DETECTOR: the Scryfall `sneak` keyword (_IR_KEYWORD_MAP, the
        #                bounce-replay engine; drops the `\bsneak\b`-regex over-fires).
        #                SERVE: an etb Trigger + a discard/lose_life/sacrifice effect
        #                whose raw names "each opponent" (the aggressive enter-bleed the
        #                recast repeats — Liliana's Specter, Skirmish Rhino). Its
        #                _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   count_anthem ← a team +N/+N pump whose amount SCALES with a board count
        #                (_is_scaling_count) over a generic creature Filter you control
        #                (Hold the Gates, Commander's Insignia, Boon of the Spirit
        #                Realm). The team-subject discriminator separates it from
        #                single-target firebreathing scaling_pump and the symmetric
        #                Coat-of-Arms global; it is the team-subject subset of
        #                scaling_pump (both may open — add() dedups). Its SWEEP row is
        #                deleted; serve hand-spec'd.
        "exert_matters",
        "self_pump",
        "tapper_engine",
        "recast_etb",
        "count_anthem",
        # Group "tranche2 (t2b2-A)" — structural grant / bounce / exile IR arms whose
        # original `needs_projection` mappings were STALE (grant_keyword now carries the
        # granted keyword in counter_kind; Ability.condition carries the gate; the
        # `Owned` subject predicate captures "you own"; bounce is a first-class
        # category). All NON-floor (floor-mirror-dep == 0 — none is in _IR_FLOOR_LANES);
        # the floor-disabled IR-vs-regex residual is empty or 100% over-fire (the IR is
        # broader-and-correct). See ADR-0027.
        #   aura_equip_kw_grant ← grant_keyword of an _AURA_EQUIP_GRANT_KW evergreen kw
        #                over a YOUR Aura/Equipment subgroup subject (Rashel + 2 the
        #                literal regex alternation missed). Its SWEEP row is deleted;
        #                serve repointed via regex=.
        #   counter_grants_kw ← grant_keyword over a YOUR-creature subject carrying the
        #                `Counters` predicate (Bramblewood Paragon, Abzan Falconer,
        #                Tuskguard Captain). Broader than the closed-keyword regex
        #                (which named only haste/flying/trample/menace/vigilance/
        #                lifelink). Its SWEEP row is deleted; serve via regex=.
        #   conditional_self_protection ← a STATIC ability with a condition granting
        #                a _SELF_PROTECTION_GRANT_KW keyword to ITSELF (subject None =
        #                SelfRef) — Dragonlord Ojutai, Zurgo, Kaito. Broader-and-correct
        #                (catches every "during your turn has indestructible" the narrow
        #                regex missed). voltron-relevant (_VOLTRON_COMPAT_KEYS). Its
        #                SWEEP row is deleted; serve repointed via regex=.
        #   control_exchange ← an `exile` Effect whose subject carries the `Owned`
        #                predicate, PAIRED with a to:battlefield return in the same
        #                ability (Meneldor, The Neutrinos, Aminatou). The inverse of the
        #                exile_removal Owned-exclusion. Its SWEEP + _HAND_FLOOR
        #                producers are deleted; serve repointed via regex=.
        #   bounce_tempo ← a `bounce` Effect (first-class category) with no graveyard
        #                zone tag and subject not controller='you' (excludes self-bounce
        #                blink/karoo) — Boomerang, Unsummon, Man-o'-War, Cyclonic Rift.
        #                Broader than the narrow regex (mass + flexible bounce);
        #                breadth, not over-fire. Its SWEEP + _DETECTORS producers are
        #                deleted; serve repointed via regex=.
        "aura_equip_kw_grant",
        "counter_grants_kw",
        "conditional_self_protection",
        "control_exchange",
        "bounce_tempo",
        # Group "tranche2-B (counters / O-Ring)" (ADR-0027) — four lanes, each fires
        # from a STRUCTURAL IR arm (NONE in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them).
        # Floor-disabled IR-vs-regex residual on the commander-legal corpus:
        # counter_manipulation / counter_replace_bonus / exile_until_leaves A-B==0;
        # counter_place_trigger A-B==6, all 100% adjudicated (opp-side scope, a
        # CONFERRED trigger phase can't attribute — Danny Pink, Cursed Wombat — a
        # turn-face-up place_counter EFFECT not a counter_added trigger — Experiment
        # Twelve — and a lore-counter manipulation — Sigurd). Each key's oracle-regex
        # SWEEP_DETECTORS producer is deleted; serve specs stay hand-registered.
        # damage_to_opp_matters is DEFERRED (needs_projection — phase types the
        # "deals damage to a player" trigger as scope='any' indistinguishable from a
        # generic combat-damage connect trigger; widening to scope='any' floods 771
        # over-fires, a genuine recall gap). See ADR-0027.
        #   counter_manipulation ← (counter_move|remove_counter) Effect with
        #                counter_kind in {p1p1,m1m1} (the +1/+1-vs-charge/oil
        #                discriminator) + a kept word mirror for the remove-as-COST
        #                tail (Walking Ballista, Quillspike — an Ability.cost phase
        #                leaves in raw). The IR also catches Graft's counter MOVE the
        #                narrow regex missed.
        #   counter_place_trigger ← a counter_added TRIGGER (scope!='opp', non-Saga).
        #                EXCLUDES Saga CHAPTERS (phase types the lore-counter chapter
        #                trigger as the SAME counter_added(scope='you',subj=None) a
        #                +1/+1 payoff carries — 202 Sagas would flood otherwise; the
        #                Saga supertype / lore-counter reminder is the only
        #                discriminator). is_widen_of counters_matter (co-fires).
        #   counter_replace_bonus ← the counter_doubling replacement category (same
        #                population as counter_doubling, is_widen_of it) + a
        #                place_counter(kind='plus') tail for the temporary activated
        #                form (Prairie Dog, 1 card, zero over-fire).
        #   exile_until_leaves ← _is_exile_until_leaves: the inline "exile/blink …
        #                until ~ leaves" raw phrase OR the two-ability linked-return
        #                O-Ring shape (exile to:exile + a dies/leaves trigger whose
        #                reanimate returns to:battlefield — Oblivion Ring, Fiend
        #                Hunter the inline regex missed) + a Saga-chapter mirror
        #                (Trial of a Time Lord collapses its per-effect raw to a
        #                "Chapter N" stub, losing the phrase).
        "counter_manipulation",
        "counter_place_trigger",
        "counter_replace_bonus",
        "exile_until_leaves",
        # ADR-0027 tranche2-C (batch C) — three structural migrations:
        #   extra_land_drop ← cheat_play / topdeck_select with a Land subject (put a
        #     land from hand/library onto the battlefield) + a YOUR-anchored kept word
        #     mirror for the empty-raw modal / cascade / phase-mis-zoned tail. The
        #     deleted regex's broad arm over-matched into graveyard sources (Wreck and
        #     Rebuild / Soul of Windgrace), which phase correctly routes to reanimate
        #     (a graveyard-lands engine, a different shape) — residual 2, both o/fire.
        #     Floor-mirror-dep == 0; IR is a recall-gaining superset (+19). SWEEP row
        #     deleted; serve hand-spec'd.
        #   free_creature_payoff ← an ETB trigger whose condition tree carries a
        #     manaspentcondition (Satoru the Infiltrator). The etb-trigger gate excludes
        #     the 4 cast_spell-triggered manaspentcondition anti-free-spell punishers
        #     (Lavinia / Boromir / Roiling Vortex / Vexing Bauble); the deleted regex
        #     100% over-fired on those + self-punish/self-bonus forms (Primeval Spawn,
        #     Freestrider Commando). Floor-mirror-dep == 0; residual 7, all over-fire.
        #     Its _DETECTORS regex producer is deleted; the serve spec stays.
        #   keyword_counter ← a place_counter / remove_counter whose counter_kind is in
        #     the closed CR-122.1b keyword set (_KEYWORD_COUNTER_KINDS) + a kept word
        #     mirror (KEYWORD_COUNTER_REGEX) for the choice/multi/quoted-grant tail
        #     phase drops counter_kind on ("your choice of a flying OR hexproof").
        #     Floor-mirror-dep == 0; IR is a strict superset of the regex (regex_only 0,
        #     +6 recall). SWEEP row deleted; serve reuses the shared regex constant.
        # NOT migrated (deferred, needs-projection): gain_control (a low-confidence
        # include_membership theft-archetype cross-open fires on 13 "you control but
        # don't own" commanders — Gonti, Tasha, Vaan, … — with no structural IR form;
        # migrating would silently drop them) and keyword_grant_target (phase collapses
        # the single-target "target creature gains menace" spell grant to subject=None
        # with a TRUNCATED raw, erasing the anchor — indistinguishable from self/go-wide
        # grants; firing on subject=None floods +2236). See the deferral comments at the
        # respective arms / producers.
        "extra_land_drop",
        "free_creature_payoff",
        "keyword_counter",
        # ADR-0027 tranche2-batch-3-A — land-animation + keyword-soup lanes.
        #   land_denial          ← phasing Effect, Land subject, controller=='you'
        #     (Taniwha). Pure-structural; regex==IR==1, residual 0; floor-mirror-dep 0.
        #   keyword_soup         ← >=5 distinct evergreen grant_keyword counter_kinds in
        #     one ability (Odric class) + a kept oracle mirror for the "same is true
        #     for …" idiom phase under-parses (Indominus Rex). Combined residual 0;
        #     +8 genuine keyword-stackers the regex missed. Floor-mirror-dep 0.
        #   land_creatures_matter / land_protection ← the SHARED land-animator predicate
        #     (animate/base_pt_set/type_set over a Land subject, you- vs you/any-gated)
        #     + Land+Creature anthem/maker subjects + a kept oracle mirror for the
        #     self-animate manlands phase drops. Combined residual 0; +127 / +97
        #     manlands the regex missed. Floor-mirror-dep 0; the co-fire on one
        #     land-animator is correct (the deck wants both lanes).
        # legend_rule_off is DEFERRED — phase's legend_exempt is a strict SUBSET of the
        # regex (2 of 8; the bounded-scope variant is dropped). Needs a supplement
        # projection; left on the regex path. See the _IR_KEPT_DETECTORS tail note.
        "land_denial",
        "keyword_soup",
        "land_creatures_matter",
        "land_protection",
        # Group "tranche2-B-3" (ADR-0027) — 2 of 5 batch keys migrated; the other 3
        # (self_counter_grow / timing_control / token_copy_matters) DEFERRED for a
        # genuine floor-disabled IR-vs-regex recall gap (NOT 100% over-fire), see the
        # deferral comments at their arms / producers.
        #   spell_keyword_grant ← the WHOLE `cast_with_keyword` effect category (the
        #     umbrella over flash_grant / convoke_matters — it co-fires with them on
        #     those subsets, e.g. Chief Engineer). Floor-mirror-dep == 0. The floor-
        #     disabled regex-only residual is 1 card (Wicker Picker, a "sticker kicker"
        #     non-keyword grant phase routes to grant_keyword) — 100% over-fire of the
        #     deleted regex's bare "creature spells you cast have" arm. The IR adds 52
        #     genuine granters the narrow keyword-list regex missed ("cast spells as
        #     though they had flash" enablers — Vedalken Orrery, Leyline, Yeva; ripple/
        #     cascade granters). Its SWEEP_DETECTORS row is deleted; serve reuses the
        #     shared SPELL_KEYWORD_GRANT_REGEX. CR 702 / 601.3e.
        #   target_player_draws ← a `draw` effect with scope=='any' (the directed /
        #     forced draw; a self-cantrip parses scope=='you', "each player draws"
        #     scope=='each' → group_hug_draw, so the gate isolates the directed draw).
        #     Floor-mirror-dep == 0. The floor-disabled regex-only residual is 1 card
        #     (Arcane Artisan, whose "Target player draws … then exiles" draw phase
        #     scopes 'opp' for the downstream forced discard — the card stays covered by
        #     activated_draw + token_copy_matters, no coverage loss). The IR adds 233
        #     genuine directed/forced draws the narrow "draws a card|target opponent
        #     draws" regex missed ("Target player draws seven cards", "that player
        #     draws", Edric's "its controller may draw"). Its SWEEP_DETECTORS row is
        #     deleted; serve reuses the shared TARGET_PLAYER_DRAWS_REGEX. CR 120.2.
        "spell_keyword_grant",
        "target_player_draws",
        # ADR-0027 tranche2-B (t2b3-B) — four structural migrations. NONE is in
        # _IR_FLOOR_LANES (floor-mirror-dep == 0 — each fires from a NON-floor
        # structural IR source with the floor disabled). Floor-disabled IR-vs-regex
        # residual on the commander-legal corpus, all adjudicated:
        #   lose_unless_hand       ← an etb trigger scope=you + a lose_game effect
        #     (Phage the Untouchable). A-B==0 — single-card archetype, structurally
        #     unique. Its _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   opponent_cast_matters  ← the structural cast_spell scope=opp arm + an
        #     _IR_KEPT_DETECTORS mirror (the deleted regex MINUS its bare "whenever a
        #     player casts" arm — the symmetric-punisher's "that player" anchor excludes
        #     the scope='any' spellslinger over-fire phase can't separate). regex_only
        #     is 100% over-fire (symmetric-benefit / self-drawback
        #     cards the bare arm wrongly opened — Forgotten Ancient, Chalice, Ebon
        #     Drake — plus emblem-buried Jace / odd-parse); the IR is MORE precise. Its
        #     _HAND_FLOOR producer is deleted; serve hand-spec'd.
        #   opponent_counter_grant ← a place_counter of a DETRIMENTAL counter (CR
        #     122.1d) on an opponent's permanent — direct opp subject (bounty/stun/m1m1/
        #     slime/bribery/rejection) or a co-tap-opp recovery for the "tap … and stun
        #     it" pronoun shape; beneficial p1p1/shield/keyword counters excluded.
        #     regex_only==0 (the bribery recall gap — Gwafa Hazid — is closed); ir_only
        #     is legitimate breadth (all real opponent-detrimental-counter cards). Its
        #     SWEEP_DETECTORS row is deleted; serve hand-spec'd.
        #   power_tap_engine       ← an ACTIVATED ability cost~'tap' + a power-scaling
        #     effect raw (Marwyn, Selvala, Staff of Domination) + an _IR_KEPT_DETECTORS
        #     mirror for the granted/quoted "{T}: … equal to its power" form phase folds
        #     into a grant carrier (Predatory Urge,
        #     Dragon Throne, Arlinn back face). regex_only==0; ir_only is breadth (the
        #     structured ab.cost catches "{T}, Sacrifice …" engines the contiguous
        #     "{t}:" regex missed — Brion Stoutarm, Ghitu Fire-Eater). Its _HAND_FLOOR
        #     producer is deleted; serve hand-spec'd.
        # pump_matters is DEFERRED (needs-projection): the IR pump/pump_target
        # categories flood ~1600 floor-disabled residual with -1/-1 DEBUFFS, activated
        # SELF firebreathing, and conditional self-buffs the narrow positive-single-
        # target regex never caught — not adjudicable as clean over-fire. It stays on
        # its SWEEP_DETECTORS regex. See ADR-0027.
        "lose_unless_hand",
        "opponent_cast_matters",
        "opponent_counter_grant",
        "power_tap_engine",
        # ADR-0027 tranche2-batch-4 (t2b4-C) — 5 kept_detector keys phase v0.1.60
        # CANNOT structure (the discriminant is DROPPED in the parse), so each fires
        # from a dedicated IR-path WORD MIRROR (the EXACT deleted regex) in
        # extract_signals_ir — the sanctioned home for mechanics with no structural IR
        # form. Each mirror reads the joined-face oracle, so it is byte-identical to the
        # deleted regex (NO-FLOOD via file-swap baseline: each key's count UNCHANGED,
        # A-B==0). floor-mirror-dep == 0 by construction (none is a floor detector).
        # Voltron: each fired high-confidence in the regex path, so all 5 are added to
        # _VOLTRON_SILENCING_PLAN_KEYS to preserve the commander-damage tell silencing
        # the IR re-supply now carries (0 voltron leaked). See ADR-0027.
        #   damage_to_you_punish ← phase keeps deals_damage but drops the opp-source
        #     filter AND the "to you" recipient. SWEEP row deleted; serve hand-spec'd.
        #   excess_damage ← clean payoffs bind structurally (Trigger event), but the
        #     intervening-condition / spell-text refs ride Effect.raw — recovered by a
        #     `\bexcess damage\b` mirror. SWEEP row deleted; serve hand-spec'd.
        #   self_blink ← no clean IR form (the `~`-substituted exile raw is ambiguous);
        #     reproduce BOTH regex producers byte-identically (the name-aware fulltext
        #     detector + the per-clause _SELF_BLINK_SWEEP_RE). SWEEP row + the regex-
        #     path emission deleted; serve hand-spec'd.
        #   tap_down_blockers ← the "can't be blocked unless all … block it" clause is
        #     100% dropped by phase. _HAND_FLOOR row deleted; serve hand-spec'd.
        #   type_change ← phase drops the protection subtype argument; mirror the
        #     _type_hoser_clause subtype-gated detector. _DETECTORS row deleted; serve
        #     hand-spec'd.
        "damage_to_you_punish",
        "excess_damage",
        "self_blink",
        "tap_down_blockers",
        "type_change",
        # ADR-0027 tranche2-batch-4 (t2b4a-A) — 3 of 5 keys migrated; each fires from a
        # STRUCTURAL IR arm (NONE in _IR_FLOOR_LANES; floor-mirror-dep == 0 by
        # construction — extract_signals_ir reads no floor detector for any of them, and
        # the floor-ON firing set is byte-identical to the floor-OFF one). NO-FLOOD held
        # via the file-swap baseline (only the target keys' counts moved; voltron
        # membership unchanged — none of the 3 fed has_other_plan). Each migrated key's
        # oracle-regex producer is deleted; serve specs stay hand-registered.
        #   tribal_etb_multi ← an `etb` Trigger whose subject Filter names a creature
        #     SUBTYPE (vocab-gated _kindred_subjects — "this or another <Tribe> you
        #     control enters"). The broad structural read is the lane's intent (every
        #     tribal-ETB chain — Miirym, Lathliss, Righteous Valkyrie, Hada Freeblade),
        #     far wider than the artificially-narrow multi-tribe self-inclusion regex.
        #     The vocab gate drops the deleted regex's non-tribal over-fires (Serum
        #     Tank's Artifact ETB, River Kelpie / Flayer's graveyard-permanent ETB — no
        #     creature subtype). regex-only residual 3, 100% over-fire. CR 603.
        #   typed_enters_punish ← an `etb` Trigger on a YOUR-controlled creature/typed-
        #     thing whose consequence is a `damage` Effect with an OPPONENT recipient
        #     (subject controller=='opp', scope in opp/each, OR an "each/target
        #     opponent" / "any target" raw — _TYPED_ENTERS_OPP_RAW recovers Purphoros
        #     / Witty Roastmaster, whose damage phase scopes 'any'). The damage-to-
        #     opponent payoff is the discriminator vs plain creature_etb value.
        #     regex-only residual 0; ir_only is broader-and-correct recall (Dread
        #     Presence, Terror of the Peaks, Impact Tremors, landfall burn). CR 603.
        #   vanilla_matters ← the HasNoAbilities subject-Filter predicate (read in
        #     _predicate_build_around_lanes, gate controller in {'you','any'}). The
        #     predicate is its own discriminator (a card merely BEING vanilla never
        #     carries it). The IR drops the regex's lone over-fire (Rise from the Wreck,
        #     a multi-target Mount/Vehicle recursion spell enumerating "creature card
        #     with no abilities" — incidental mention, not a vanilla build-around) and
        #     ADDS the "Creatures you control with no abilities" anthem the contiguous
        #     regex missed (Jasmine Boreal). regex-only residual 1, over-fire. CR 113.3.
        # DEFERRED (needs-projection — genuine recall gap, NOT clean over-fire):
        #   untap_engine ← the IR arm (already wired) misses 11 genuine untap engines
        #     the regex catches (modal "tap or untap target" — Captain of the Mists,
        #     Tideforce Elemental; "tap-all OR untap-all" choose — Turnabout, Faces of
        #     the Past; mass-untap-of-own-board — All-Out Assault, Ohabi Caleria; the
        #     creatures-are-lands synergy — Ashaya). phase routes their untap text into
        #     `choose` / `bounce` / cost / SelfRef shapes, not a `cat=='untap'` effect.
        #     Its two _HAND_FLOOR producers stay on the regex path.
        #   variable_pt ← the IR arm misses ~154 genuine */* CDAs (Nightmare, Pack Rat,
        #     Consuming Aberration, Serra Avatar, Cultivator Colossus): phase DROPS the
        #     "power and toughness equal to …" clause entirely on most CDA bodies (the
        #     IR carries only the keyword/other abilities). A deep supplement parse-gap,
        #     not an over-fire migration. Its SWEEP_DETECTORS row stays on regex.
        "tribal_etb_multi",
        "typed_enters_punish",
        "vanilla_matters",
        # ADR-0027 tranche2-batch-4a (t2b4a-B) — two structural IR keys + three
        # field-lookup keyword-array keys:
        #   win_lose_game  ← Effect.category in {win_game, lose_game} (the broad
        #     terminal-outcome pool) + a kept regex mirror (scope 'any') for the
        #     conferred/quoted-ability tail (Vraska tokens, Frodo). SWEEP row deleted.
        #   xspell_matters ← the HasXInManaCost predicate on a cast_spell trigger
        #     subject (Zaxara …) + a kept effect-raw hook mirror (minus the hoser veto)
        #     for the predicate-dropped tail (Unbound Flourishing, Rosheen). _DETECTORS
        #     row deleted.
        #   alt_cost_keyword ← Scryfall web-slinging / sneak / mayhem keyword array
        #     (_IR_KEYWORD_MAP). SWEEP row deleted; drops the regex's flavor/grant
        #     over-fires.
        #   curse_matters ← a trigger/effect subject Filter subtypes=='Curse' +
        #     a kept regex mirror (the deleted cares-about regex) for the under-parsed
        #     "search for a Curse card …" tail. _HAND_FLOOR row deleted. Membership
        #     stays REGEX-ONLY at A4.
        #   partner_background ← Scryfall partner-family keyword array (_IR_KEYWORD_MAP;
        #     partner / partner with / choose a background / doctor's companion /
        #     friends). SWEEP row deleted; drops the regex's name-comma over-fires,
        #     recovers Friends-forever partners. Feeds the ADR-0019 color-widening
        #     avenue (production cards carry the keyword). companion NOT mapped.
        "win_lose_game",
        "xspell_matters",
        "alt_cost_keyword",
        "curse_matters",
        "partner_background",
        # ADR-0027 tranche2-batch-5 (t2b5-A) — 5 kept_detector keys phase v0.1.60
        # CANNOT structure, each fires from a dedicated IR-path WORD MIRROR (the EXACT
        # deleted regex) in extract_signals_ir, the sanctioned home for mechanics with
        # no structural IR form. Each mirror reads the joined-face oracle, so it is
        # byte-identical to the deleted regex (NO-FLOOD via file-swap baseline: each
        # key's count UNCHANGED, A-B==0). floor-mirror-dep == 0 by construction (none
        # is a floor detector). Voltron: each fired high-confidence in the regex path,
        # so all 5 are added to _VOLTRON_SILENCING_PLAN_KEYS to preserve the commander-
        # damage tell silencing the IR re-supply now carries (0 voltron leaked — the
        # kept mirror is byte-identical, so the IR re-supply is the same set). ADR-0027.
        #   draft_spellbook ← Arena/Alchemy digital mechanics (draft-a-card / spellbook)
        #     not in the CR, no phase effect category. SWEEP row deleted; serve hand-
        #     spec'd.
        #   each_mode_player ← phase captures the modal head but has no field for the
        #     spread-the-modes constraint. SWEEP row deleted; serve hand-spec'd.
        #   flip_self ← phase parses the Kamigawa flip inconsistently; "flip this
        #     creature" is the tell. SWEEP row deleted; serve hand-spec'd.
        #   free_plot ← no IR structure for the Plot alt-cost rewrite; the phrase is
        #     unique to Fblthp. _HAND_FLOOR row deleted; serve stays hand-spec'd.
        #   miracle_grant ← phase folds the grant into a carrier; the granting-direction
        #     phrase is the tell. SWEEP row deleted; serve hand-spec'd.
        "draft_spellbook",
        "each_mode_player",
        "flip_self",
        "free_plot",
        "miracle_grant",
        # ADR-0027 tranche2-batch-5 (t2b5-B) — five kept_detector lanes phase v0.1.60
        # CANNOT structure (the discriminant is DROPPED in the parse), each firing from
        # a dedicated IR-path word mirror (_IR_KEPT_DETECTORS) reproducing the deleted
        # _HAND_FLOOR / SWEEP regex. All NON-floor IR sources; floor-mirror-dep == 0;
        # A-B == 0 by construction (the secret_writedown mirror is INTENTIONALLY
        # narrower — it drops the deleted regex's companion-reminder "your sideboard"
        # arm, owned by companion_keyword). Their oracle-regex producers are deleted;
        # the serve specs stay hand-registered in signal_specs.py. See ADR-0027.
        #   per_target_payoff    ← Hinata's per-target cost-reduction arm (no IR
        #     mana-cost / target-count operand; CR 601 / 118).
        #   sacrifice_protection ← protective-vs-stax restriction split + the
        #     quoted/granted forms phase drops (CR 701.16).
        #   secret_writedown     ← out-of-game zone + pre-game secret name (CR 408.1).
        #   target_own_payoff    ← Monk Gyatso's becomes-target may-reaction (the
        #     trigger flattens to event='other'; CR 603).
        #   target_redirect      ← Rayne's becomes-target-of-opponent → draw (same
        #     event='other' flattening; CR 603).
        "per_target_payoff",
        "sacrifice_protection",
        "secret_writedown",
        "target_own_payoff",
        "target_redirect",
    }
)
"""Signal keys served from the IR path in production; grows as the ADR-0027
regex→IR strangler deletes each key's regex detector. Empty = pure regex
(today)."""


def extract_signals_hybrid(
    record: dict,
    ir: Card | None,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
    resolve_object: Callable[[str], dict | None] | None = None,
) -> list[Signal]:
    """Dispatch each signal key to the IR or the regex path per ``MIGRATED_KEYS``.

    Keys in ``MIGRATED_KEYS`` come from ``extract_signals_ir`` (the Card IR path);
    every other key comes from ``extract_signals`` (the legacy regex path). The two
    sets are merged and deduped by ``(key, scope, subject)``. With ``MIGRATED_KEYS``
    empty (today) the IR contributes nothing, so the result is byte-identical to a
    pure ``extract_signals`` call regardless of ``ir`` (including ``ir is None``).

    Graceful degradation: when ``ir is None`` (the sidecar is absent / a brand-new
    set), return the pure regex path — the IR sidecar is a new core dependency but
    must never hard-crash production if missing. The ``extract_signals`` keyword args
    (``vocab`` / ``include_membership`` / ``resolve_object``) are forwarded through."""
    regex_signals = extract_signals(
        record,
        vocab=vocab,
        include_membership=include_membership,
        resolve_object=resolve_object,
    )
    if ir is None or not MIGRATED_KEYS:
        return regex_signals
    out: list[Signal] = [s for s in regex_signals if s.key not in MIGRATED_KEYS]
    seen = {(s.key, s.scope, s.subject) for s in out}
    for sig in extract_signals_ir(
        record, ir, vocab=vocab, include_membership=include_membership
    ):
        if sig.key not in MIGRATED_KEYS:
            continue
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(sig)
    # ADR-0027 spell-copy cross-open reconciliation: the regex path cross-opens
    # spellcast_matters from a spell_copy_matters commander (a spell-copier is a
    # spellslinger wanting a dense I/S base), gated on the regex set carrying
    # spell_copy_matters. Now that spell_copy_matters migrated, the regex set lacks it,
    # so the cross-open stops firing — re-supply it here when the IR provides spell_copy
    # and the regex set didn't already cross-open spellcast (matching pre-migration
    # behavior; low confidence, you-scope).
    out_keys = {s.key for s in out}
    if (
        "spell_copy_matters" in out_keys
        and "spell_copy_matters" not in {s.key for s in regex_signals}
        and "spellcast_matters" not in out_keys
    ):
        out.append(
            Signal("spellcast_matters", "you", "", "", record.get("name", ""), "low")
        )
    # ADR-0027 voltron reconciliation: the regex path computes the commander-damage
    # voltron MEMBERSHIP fallback against its OWN signal set (gated on
    # ``not has_other_plan``), which no longer carries a migrated PLAN key — when a key
    # migrates, its regex producer is deleted, so the regex set stops silencing the
    # membership tell on a card whose plan now lives only in the IR (a reanimator /
    # tap-untap / hand-disruption / aristocrats engine is NOT a vanilla beater). The
    # sacrifice/lifeloss *_PLAN_MIRROR re-silences those two on the oracle, but it goes
    # blind on a DFC's empty top-level oracle_text and doesn't cover the SWEEP-batch
    # plan keys. So drop the spurious low-confidence commander-damage membership tell
    # when the IR supplies one of the plan keys whose regex producer this batch deleted
    # and the regex set now LACKS — exactly the keys that used to count toward
    # `has_other_plan` (matching pre-migration behavior; a non-plan migrated key like a
    # color/type predicate is excluded, so voltron firings the OLD path kept survive).
    if include_membership:
        regex_keys = {s.key for s in regex_signals}
        ir_plan = any(
            s.key in _VOLTRON_SILENCING_PLAN_KEYS and s.key not in regex_keys
            for s in out
        )
        if ir_plan:
            out = [
                s
                for s in out
                if not (
                    s.key == "voltron_matters"
                    and s.confidence == "low"
                    and s.text == "commander damage (CR 903.10a)"
                )
            ]
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
    ir_for: Callable[[dict], Card | None] | None = None,
) -> list[Signal]:
    """Deck signals deduped by (key, scope, subject) and ranked by relevance.

    Membership signals (own-subtype tribal, voltron fallback) are taken from the
    COMMANDER only — otherwise every creature's race/stat-line floods the deck. A
    signal's *support* (how many cards feed it) drives the ranking. Kept ForgeState-free
    so both the deck-forge engine (``engine.ranked_deck_signals``) and the deterministic
    tuner share one ranking (ADR-0023).

    ``ir_for`` (ADR-0027): a per-record Card-IR resolver. When supplied, each card
    runs through ``extract_signals_hybrid`` so migrated keys (served only from the IR)
    surface in the deck's ranked signals / avenues — the engine wires its index here.
    When ``None`` (the deterministic tuner's no-sidecar path), falls back to the pure
    regex ``extract_signals`` (a migrated key whose regex producer is deleted simply
    won't surface — graceful degradation, matching the hybrid's ``ir is None`` arm)."""
    support: dict[tuple[str, str, str], int] = {}
    from_commander: set[tuple[str, str, str]] = set()
    first: dict[tuple[str, str, str], Signal] = {}
    for card in records:
        if not card:
            continue
        is_cmd = card.get("name") in commander_names
        # Folded objects (a ventured dungeon — ADR-0025) belong to the COMMANDER's plan,
        # so only fold for the commander, never the 99.
        if ir_for is not None:
            sigs = extract_signals_hybrid(
                card,
                ir_for(card),
                include_membership=is_cmd,
                resolve_object=resolve_object if is_cmd else None,
            )
        else:
            sigs = extract_signals(
                card,
                include_membership=is_cmd,
                resolve_object=resolve_object if is_cmd else None,
            )
        for sig in sigs:
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

# ADR-0027 voltron reconciliation set: migrated plan keys whose (now-deleted) regex
# producer used to count toward `has_other_plan` and so silenced the commander-damage
# voltron membership tell. When the IR re-supplies one of these the regex set lacks,
# the hybrid re-silences voltron — preserving pre-migration behavior. Only the keys
# that actually fire as a high-confidence non-generic non-voltron-compat plan in the
# regex path belong here (sacrifice/lifeloss were the first two; the SWEEP batch adds
# the engine plans whose deletion would otherwise leak a vanilla-beater voltron tell).
_VOLTRON_SILENCING_PLAN_KEYS = frozenset(
    {
        "sacrifice_matters",
        "lifeloss_matters",
        "reanimator",
        "tap_untap_matters",
        "minus_counters_matter",
        "donate_matters",
        "hand_disruption",
        "team_evasion_grant",
        "commander_matters",
        "opponent_exile_matters",
        "domain_matters",
        "speed_matters",
        # ADR-0027 SWEEP batch: each fired high-confidence (forced scope) in the regex
        # path and so counted toward `has_other_plan`, silencing the spurious commander-
        # damage voltron tell. Their regex producers are now deleted, so the hybrid must
        # re-silence from the IR re-supply to preserve pre-migration behavior (without
        # this, an infect/suspend vanilla beater — Skithiryx, Errant Ephemeron — leaks a
        # spurious voltron membership tell). NO-FLOOD requires these four here.
        "legends_matter",
        "lands_matter",
        "poison_matters",
        "suspend_matters",
        # ADR-0027 counters_matter pass 2: the +1/+1-counter regex producers (detector
        # / floor / keyword block / self-counter adds) fired high-confidence non-
        # generic, counting toward has_other_plan. Now migrated, so the hybrid must re-
        # silence the spurious voltron tell from the IR re-supply (a +1/+1-counter
        # engine — Hardened Scales, Forgotten Ancient — is not a vanilla beater).
        "counters_matter",
        # ADR-0027 tranche2-B: mass_bounce / permanent_etb / power_double each fired
        # high-confidence in the regex path and counted toward has_other_plan, silencing
        # the spurious commander-damage voltron tell on a non-vanilla-beater (a
        # bounce/tempo engine — Scourge of Fleets; a permanent-ETB value engine —
        # Amareth; a power-doubler — Okaun). Their regex producers are deleted, so the
        # hybrid re-silences from the IR re-supply. None of the affected cards is a DFC,
        # so the structural IR-signal gate suffices (no oracle mirror needed). team_buff
        # is NOT here — it carries a regex over-fire tail the narrower IR drops AND DFC
        # grant faces (Topaz Dragon), so it uses the byte-identical
        # _TEAM_BUFF_PLAN_MIRROR gate instead.
        "mass_bounce",
        "permanent_etb",
        "power_double",
        # ADR-0027 tranche2-batch-3-A: land_denial fired high-confidence in the regex
        # path (the _HAND_FLOOR producer, now deleted) and counted toward
        # has_other_plan, silencing the spurious commander-damage voltron tell on
        # Taniwha (a Trample Serpent that is a land-phasing stax commander, not a
        # vanilla beater). The IR re-supplies land_denial on the SAME single card
        # (IR==regex==1: phasing+Land+you isolates Taniwha exactly), so this is
        # byte-identical re-silencing — not a broadening, so no over-silence. The other
        # three migrated keys (keyword_soup / land_creatures_matter / land_protection)
        # leaked NO voltron on the file-swap (their cards already carry another plan),
        # so they are NOT added here.
        "land_denial",
        # ADR-0027 tranche2-A: the migrated anthem_static / aoe_ping / mass_removal keys
        # silenced the spurious commander-damage voltron membership tell when their
        # (now-deleted) regex producers fired. The silencing is done on the regex side
        # via the has_other_plan oracle mirrors (_ANTHEM_GO_WIDE_MIRROR /
        # _AOE_PING_PLAN_MIRROR / _MASS_REMOVAL_PLAN_MIRROR), each matching ONLY the old
        # regex's matches — NOT the broader IR re-supply, which would over-silence the
        # IR-only sweep/anthem bodies the old regex never caught (Sunblast Angel, Reiver
        # Demon). The mirrors now run against the joined-face ``text`` (see _oracle), so
        # they catch DFC back-face bodies (Archangel Avacyn, Fang Dragon) byte-
        # identically — no silencing-set entry needed. activated_draw is a draw engine
        # that never rode the per-card voltron membership gate at all.
        # NB (ADR-0027 tranche2-C): the five tranche2-C keys (self_pump / tapper_engine
        # / count_anthem / exert_matters / recast_etb) are NOT added here. They also
        # silenced voltron pre-migration (high-conf plans), but their IR recall is
        # BROADER than the deleted regex (self_pump 567->725, tapper 474->784 on the
        # commander-legal IR corpus), so the IR-supply reconciliation here would
        # OVER-silence (-117 on Aetherling / Angel's Trumpet / vigilance-granter
        # bodies the narrow regex missed). Instead they re-silence via the regex-path
        # _TRANCHE2C_PLAN_MIRROR fed into `has_other_plan`, which reproduces the exact
        # pre-migration silence set (the deleted regex patterns) for ALL cards — so
        # voltron_matters is byte-identical to pre-migration. NO-FLOOD.
        # ADR-0027 tranche2-batch-4 (t2b4-C): the 5 kept_detector keys each fired
        # high-confidence (forced/default scope) in the regex path and so counted
        # toward has_other_plan, silencing the spurious commander-damage voltron tell.
        # Their regex producers are deleted, so the hybrid re-silences from the IR
        # re-supply. Unlike tranche2-C, these are kept WORD MIRRORS — the IR re-supply
        # reads the SAME joined oracle as the deleted regex, so it is BYTE-IDENTICAL (no
        # broadening, no over-silence). File-swap: 0 voltron leaked, A-B==0.
        "damage_to_you_punish",
        "excess_damage",
        "self_blink",
        "tap_down_blockers",
        "type_change",
        # ADR-0027 tranche2-batch-5 (t2b5-A): the 5 kept_detector keys each fired
        # high-confidence (forced/default scope) in the regex path and so counted toward
        # has_other_plan, silencing the spurious commander-damage voltron tell. Their
        # regex producers are deleted, so the hybrid re-silences from the IR re-supply.
        # These are kept WORD MIRRORS — the IR re-supply reads the SAME joined oracle as
        # the deleted regex, so it is BYTE-IDENTICAL (no broadening, no over-silence).
        # File-swap: 0 voltron leaked, A-B==0.
        "draft_spellbook",
        "each_mode_player",
        "flip_self",
        "free_plot",
        "miracle_grant",
    }
)

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
    # ADR-0027 strangler: a migrated key's regex production is deleted, but it is
    # still produced (from the IR path) and still needs a resolving spec — so it
    # stays guarded by the key-agreement gate (signal_specs ADR-0014). The
    # producer tables above no longer mention it, so union it back in explicitly.
    keys.update(MIGRATED_KEYS)
    return keys - signal_keys.SUBJECT_KEYS
