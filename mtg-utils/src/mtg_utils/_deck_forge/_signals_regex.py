"""Legacy regex-bag signal detection + shared parsing primitives.

The ADR-0027 strangler's *base* module: ``extract_signals`` (the oracle-text
regex path destined for deletion at A4) plus the parsing primitives both paths
share (``Signal``, ``_clauses``/``_scope``/``_resolve_subject``, the voltron
detectors, the ``*_PLAN_MIRROR`` regexes, ``_GENERIC_KEYS``). The IR path
(:mod:`_signals_ir`) imports the shared primitives from here; this module never
imports the IR path (acyclic). Split out of ``signals.py`` (behavior-neutral,
2026-06-21) to cut per-edit token cost. ``signals`` re-exports the public names.
"""

from __future__ import annotations

import re
from collections.abc import Callable
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
    NONCREATURE_CAST_PUNISH_REGEX,
    SPELL_KEYWORD_GRANT_REGEX,
    SWEEP_DETECTORS,
    TARGET_PLAYER_DRAWS_REGEX,
)
from mtg_utils.card_classify import card_pt_int, get_oracle_text
from mtg_utils.card_ir import Card, Effect, Filter
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
    # ADR-0027 t2b5-C: theft_protection migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact "for the first
    # time each turn, counter" regex). phase parses Kira's granted shield as a grant
    # carrier + a counter_spell effect but does NOT structure the once-per-turn becomes-
    # target gate, so the phrasing survives only on the oracle. This _HAND_FLOOR
    # producer is deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027 q2-D2: opp_top_exile migrated to the Card IR — a name-lock /
    # impulse-cast engine that exiles from an opponent's zone AND lets a card be
    # PLAYED from there (Circu, Ragavan, Gonti, Villainous Wealth). Fires from the
    # structural extract_signals_ir arm (exile scope=='opp' + cast_from_zone
    # scope=='opp', OR exile scope=='opp' carrying 'in:library') — which adds 50
    # steal-and-cast cards this regex never reached — plus an _IR_KEPT_DETECTORS word
    # mirror reproducing this exact regex for the name-lock / peek subset phase
    # under-parses (Circu's exile scope=='any'; Scrib Nibblers; granted "exile the top
    # card" on Predators' Hour). This _HAND_FLOOR producer is deleted; the serve spec
    # stays hand-registered in signal_specs.py.
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
    # ADR-0027 t2b5-C: villainous_choice migrated to the Card IR — detected from the
    # kept word-detector mirror in signals._IR_KEPT_DETECTORS (the exact "villainous
    # choice" literal). phase routes the keyword action to a GENERIC 'choose' Effect
    # (too broad to key on), so the literal phrase is the only clean discriminator. The
    # Valeyard doubles them; Davros/Missy/Dr. Eggman present them. This _HAND_FLOOR
    # producer is deleted; the serve spec stays hand-registered in signal_specs.py.
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
    # ADR-0027 (q2-D3): flash_matters migrated to the Card IR — the GRANT half binds
    # structurally (extract_signals_ir: an Effect category=='cast_with_keyword' with
    # counter_kind=='flash' — the same node flash_grant reads; Leyline of Anticipation,
    # Vivien Champion of the Wilds, Teferi Mage of Zhalfir). phase folds the ACTIVATED
    # flash-grant (Winding Canyons {2}{T}, Teferi Time Raveler +1) into grant_keyword
    # with an EMPTY counter_kind, and leaves the opponent-turn cast payoff ("whenever
    # you cast a spell during an opponent's turn") textual — so the FULL deleted regex
    # is kept byte-identically as the _IR_KEPT_DETECTORS mirror to recover both forms.
    # The structural arm is broader-and-correct (adds Teferi Mage of Zhalfir, whose
    # "have flash" grant the regex's phrasing missed). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered. CR 702.8.
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
# ADR-0027 (q2-D3) voltron reconciliation — the deleted noncreature_cast_punish SWEEP
# regex producer fired high-confidence (scope='any') in the regex path and counted
# toward has_other_plan, silencing the spurious commander-damage voltron tell on a
# symmetric-cast creature body (Ink-Treader Nephilim, Heartwood Storyteller,
# Mirrorwing Dragon — 3 cards verified to leak the tell post-deletion). The migrated IR
# opp-arm is MORE precise (it covers only scope=='opp' opponent punishers, NOT these
# symmetric "a player casts" bodies), so the IR re-supply does NOT reach the regex-path
# gate — this mirror (the EXACT deleted SWEEP regex, read against the joined-face
# `_oracle`) reproduces the silence byte-identically. (A mirror — not
# _VOLTRON_SILENCING_PLAN_KEYS — because the IR is more precise and would under-cover
# the symmetric cards via the silencing-keys path.) CR 603.2.
_NONCREATURE_CAST_PUNISH_PLAN_MIRROR = re.compile(
    NONCREATURE_CAST_PUNISH_REGEX, re.IGNORECASE
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

# impulse_top_play (ADR-0027 β) — the impulse exile-then-play SWEEP regex, kept as a
# byte-identical PER-CLAUSE mirror. The structural IR arm (a NON-static cast_from_zone
# Effect carrying a recovered 'from:library' zone) catches the temporary exile-and-play
# engine broadly (Light Up the Stage, Ragavan, Etali, Narset, Collected Conjuring — 105
# real impulse cards the narrow regex never reached, all verified to exile-top-then-
# cast: legitimate breadth, not over-fire). phase under-parses a tail (the "you may play
# that card this turn" follow-through it folds into a generic effect with no from-zone
# category, the modal "from among" clause) so this mirror recovers it. Its `[^.]*\.?\s*`
# arms span a sentence over the WHOLE oracle (+39 over-fire flat), so — like self_blink
# — it MUST run PER-CLAUSE via _clauses (matching the deleted SWEEP path), NOT as a flat
# _IR_KEPT_DETECTORS full-text row. This is the EXACT deleted SWEEP_DETECTORS row
# (byte-identical). The static play-from-library permission (Future Sight, Bolas's
# Citadel) is the SIBLING play_from_top lane, NOT this — it stays on regex (DEFERRED:
# phase's supplement creates that cast_from_zone effect AFTER the from:library recovery
# pass runs, so the zone never lands on the static shape). CR 116 / 601.3b.
_IMPULSE_TOP_PLAY_SWEEP_RE = re.compile(
    r"exile the top [^.]*card[^.]*(?:you may play|may play (?:it|that card|them))"
    r"|until (?:your next end step|end of turn|the end of your next turn)"
    r"[^.]*you may play"
    r"|exile the top [^.]*card[^.]*your library[^.]*\.?\s*you may (?:play|cast)"
    r"|you may play (?:that|the exiled|those|that card) cards?"
    r"|you may (?:cast|play) (?:the|those|that) (?:exiled )?cards? this turn"
    r"|top [^.]*card[^.]*of your library\.?[^.]*you may (?:cast|play) "
    r"(?:it|them|that card)[^.]*this turn"
    r"|you may play (?:that card|those cards?|them) (?:this turn|until)"
    r"|cast (?:up to two |a )?spells? from among"
    r"|top card of your library is[^.]*you may[^.]*(?:cast|play)"
    r"|play (?:lands? )?(?:and |or )?cast [^.]*from among cards you exiled"
    r"|you may look at (?:it )?and (?:play|cast)",
    re.IGNORECASE,
)

# edict_matters (ADR-0027 β) voltron plan mirror — the EXACT deleted SWEEP regex. The
# regex producer fired high-confidence (forced scope 'each'), counting toward
# has_other_plan: an edict commander (Plaguecrafter, Butcher of Malakir, Dictate of
# Erebos) is a sacrifice-removal engine, NOT a vanilla commander-damage beater, so its
# regex producer silenced the spurious voltron membership tell. The migrated IR arm is
# BROADER (+28 — Annihilator beaters, modal "those players sacrifice"), so re-supplying
# via _VOLTRON_SILENCING_PLAN_KEYS would OVER-silence (an Annihilator voltron threat —
# Kozilek, Ulamog — is exactly the vanilla-beater tell voltron should keep). This
# byte-identical mirror restores ONLY the deleted regex's silence set. Its arms never
# cross a sentence (`[^.]`-only), so full-text == per-clause (verified diff=0); read
# against the joined-face _oracle (reminder text adds no edict match — verified).
_EDICT_PLAN_MIRROR = re.compile(
    r"each opponent sacrifices|whenever an opponent sacrifices"
    r"|target opponent sacrifices|each player sacrifices"
    r"|(?:each player|that player|each opponent|target player"
    r"|target opponent) sacrifices? (?:a|an|two|\d+|half)"
    r"|that player sacrifices|controller sacrifices",
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
        # ADR-0027 (q2-D3): re-silence the deleted noncreature_cast_punish SWEEP regex —
        # its high-confidence producer fed this gate on symmetric "a player casts a
        # noncreature spell" bodies (Ink-Treader Nephilim, Heartwood Storyteller,
        # Mirrorwing Dragon). The migrated IR opp-arm is more precise and doesn't reach
        # these, so the byte-identical mirror restores the silence. CR 603.2.
        or _NONCREATURE_CAST_PUNISH_PLAN_MIRROR.search(_oracle)
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
        # ADR-0027 β: re-silence the deleted impulse_top_play SWEEP producer. It fired
        # high-confidence (forced scope 'you') and counted toward has_other_plan,
        # silencing the spurious commander-damage voltron tell on an impulse engine that
        # is NOT a vanilla beater (Opposition Agent, Laughing Jasper Flint, Eruth — 11
        # leaked on the file-swap without this). The migrated IR arm is BROADER than the
        # deleted regex (+105 cards), so the _VOLTRON_SILENCING_PLAN_KEYS IR-re-supply
        # path would OVER-silence; instead this byte-identical mirror (the EXACT deleted
        # SWEEP regex) restores only the old regex's silence set. Run PER-CLAUSE over
        # ``text`` (reminder-STRIPPED, like _T2B5): the deleted producer was a floor
        # Detector over reminder-stripped clauses, and the regex's `[^.]*\.?\s*` arms
        # span a sentence over the whole oracle (+39 over-silence flat), so per-clause
        # is the byte-identical reproduction (voltron back to base; A-B==0).
        or any(_IMPULSE_TOP_PLAY_SWEEP_RE.search(cl) for cl in _clauses(text))
        # ADR-0027 β: re-silence the deleted edict_matters SWEEP producer (forced scope
        # 'each', high-confidence — it counted toward has_other_plan). The migrated IR
        # arm is BROADER (+28), so _VOLTRON_SILENCING_PLAN_KEYS would over-silence an
        # Annihilator voltron beater; this byte-identical mirror restores only the old
        # regex's silence set. Full-text over _oracle == per-clause (arms never cross a
        # sentence; reminder text adds no edict match — both verified diff=0).
        or _EDICT_PLAN_MIRROR.search(_oracle)
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


# creature commander) and discriminates no archetype. The other keys each pin a
# real sub-archetype, so they are NOT generic.
_GENERIC_KEYS = frozenset({"creatures_matter"})
