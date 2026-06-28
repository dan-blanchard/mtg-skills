"""Legacy regex-bag signal detection + shared parsing primitives.

The ADR-0027 strangler's *base* module: ``extract_signals`` plus the parsing
primitives both paths share (``Signal``, ``_clauses``/``_scope``/
``_resolve_subject``, the voltron detectors, the ``*_PLAN_MIRROR`` regexes,
``_GENERIC_KEYS``). The IR path (:mod:`_signals_ir`) imports the shared
primitives from here; this module never imports the IR path (acyclic). Split
out of ``signals.py`` (behavior-neutral, 2026-06-21) to cut per-edit token cost.
``signals`` re-exports the public names.

ADR-0027 A4 (cutover, 2026-06-26): the regex path is **no longer "destined for
deletion"** — it is now the legitimate, non-dead residue. The incremental
migration already removed every deletable producer (``_DETECTORS`` and
``_PRESET_REGEX_SIGNALS`` are empty; the producer-table residues that remain
feed BOTH paths), so there is nothing left to delete here behavior-neutrally.
What stays is load-bearing:

  * ``extract_signals`` still produces ``voltron_matters`` — a *composite*
    gate-metric (commander-damage membership silenced by ``has_other_plan``)
    whose plan inputs are themselves already IR-served. ``extract_signals_hybrid``
    strips every ``MIGRATED_KEYS`` emission from the regex output and re-supplies
    it from the IR, so the surviving migrated-key emissions are harmless residue.
  * The ~57 helpers/constants :mod:`_signals_ir` imports from here are re-run as
    BYTE-IDENTICAL kept-mirrors of the IR re-supply (deleting them = gate drift).
  * The ``*_PLAN_MIRROR`` regexes + ``has_other_plan`` helpers feed the regex-side
    voltron silencing that the hybrid reconciliation depends on.

This module is retired only when ``voltron_matters`` itself migrates off the
regex path — tracked as the deferred voltron-migration work item (task #18),
held behind the structural-audit backlog. Until then: do not delete from here.
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
    NON_CREATURE_TOKEN,
    NON_SUBJECT_WORDS,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import (
    ATTACK_MATTERS_REGEX,
    BLOCKED_MATTERS_REGEX,
    COMBAT_BUFF_ENGINE_SWEEP_REGEX,
    DIG_UNTIL_REGEX,
    DISCARD_OUTLET_REGEX,
    DRAW_FOR_EACH_REGEX,
    EXILE_REMOVAL_REGEX,
    LANDFALL_REGEX,
    LURE_MATTERS_REGEX,
    NAMED_PERMANENT_REGEX,
    PROTECTION_GRANT_REGEX,
    SWEEP_DETECTORS,
    TOPDECK_SELECTION_REGEX,
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
# keyword_soup_makers team-grant context (ADR-0027 — pinned for the byte-identical
# _signals_ir kept mirror): a commander that GRANTS/SHARES keywords across the team
# ("creatures you control gain/have …", Odric's "each other creature you control",
# Akroma Vision's "+1/+1 if it has <keyword>" enumeration). The >=5-distinct-evergreen
# gate (counted with _EVERGREEN_KW_RE over the same reminder-stripped text) isolates the
# soup-sharer from a single-keyword anthem.
_KEYWORD_SOUP_CONTEXT_RE = re.compile(
    r"creatures you control (?:gain|have)|each other creature you control"
    r"|if it has",
    re.IGNORECASE,
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


# ADR-0027 β: creature_etb migrated to the Card IR via a BYTE-IDENTICAL kept mirror.
# This per-clause helper is the EXACT logic of the two deleted _DETECTORS rows below
# (the "you" ETB-value / doubler / delayed-payoff row and the "opponents" punisher
# row), pinned as the SINGLE source the _signals_ir mirror (_creature_etb_clauses)
# and the _CREATURE_ETB_PLAN_MIRROR voltron gate both reuse. A structural IR arm was
# REJECTED: phase models the doublers (Panharmonicon/Yarok — "entering … triggers an
# additional time") as static replacement effects and Ephara's delayed payoff as an
# upkeep trigger, neither an `etb` event, so the structural arm (etb-trigger w/
# Creature subject) MISSES 62 genuine creature-ETB cards (8 doublers, 4 had-payoffs,
# 3 opp-punishers, plus the broad ETB-value/over-fire tail) while GAINING only 39
# Graft/Soulbond bodies — a non-byte-identical mix, not a clean structural win. So
# the lane rides this exact regex (per-clause, reminder-stripped) instead — a true
# behavior-neutral re-home (commander-legal corpus: regex == mirror, 0 lost /
# 0 over-fire). CR 603.6.
def _creature_etb_clause(cl: str) -> str | None:
    """Scope ("you"|"opponents") the deleted creature_etb _DETECTORS rows would emit
    for one lowercased, reminder-stripped clause, or ``None``. The "you" row vetoes
    on an opponent-controlled entering creature; the "opponents" row is the punisher.
    """
    has_when = "whenever" in cl or "when " in cl
    opp = _ETB_OPP_RE.search(cl) is not None
    if opp and has_when:
        return "opponents"
    if (
        (_ETB_ANY_RE.search(cl) is not None and has_when)
        or _ETB_DOUBLER_RE.search(cl) is not None
        or _ETB_HAD_RE.search(cl) is not None
    ) and not opp:
        return "you"
    return None


def _creature_etb_clauses(text: str) -> set[tuple[str, str]]:
    """All (``"creature_etb"``, scope) pairs the deleted producer would emit over the
    reminder-stripped joined oracle, applied PER-CLAUSE (the deleted _DETECTORS ran
    per-clause, and the component regexes' ``[^.]`` spans never cross a sentence)."""
    out: set[tuple[str, str]] = set()
    for clause in _clauses(text):
        scope = _creature_etb_clause(clause.lower())
        if scope is not None:
            out.add(("creature_etb", scope))
    return out


# ADR-0027 graveyard scope/origin/zone (SIDECAR v29): the THREE deleted
# graveyard_matters _DETECTORS producers, pinned for the byte-identical per-clause kept
# mirror. The lane migrated to the Card IR (structural zone arms + _gy_scope
# self-graveyard default); this mirror recovers the broad "graveyard"-mention recall
# phase has no structural form for. (1) "your graveyard" → forced scope 'you'. (2) a
# bare "graveyard" mention (NOT "your graveyard") → the CLAUSE-RESOLVED scope (the
# None-forced-scope producer). (3) an exile-mill of an opponent's library ("exile the
# top … of target player's library" — Circu) → forced 'opponents'. The deleted producers
# ran PER-CLAUSE inside extract_signals's detector loop, applying the narrow Tinybones
# rescope (high) over the forced/resolved scope; this mirror reproduces that exactly. CR
# 400.7 / 701.17a.
_GY_YOUR_RE = re.compile(r"your graveyard")
_GY_EXILE_MILL_OPP_RE = re.compile(
    r"exile (?:the top|\w+ cards?|cards?)[^.]*"
    r"(?:target player'?s?|an opponent'?s?|each (?:player|opponent)'?s?"
    r"|that player'?s?) librar"
)


def _graveyard_matters_clauses(text: str, name: str) -> set[tuple[str, str]]:
    """All (``"graveyard_matters"``, scope) pairs the THREE deleted producers would emit
    over the reminder-stripped joined oracle, applied PER-CLAUSE with the exact scope
    logic of extract_signals's detector loop (Tinybones rescope wins; else the
    producer's forced scope; else the clause-resolved scope). Byte-identical to the
    deleted regex path so regex_only == 0."""
    out: set[tuple[str, str]] = set()
    for clause in _clauses(text):
        cl = clause.lower()
        rescope = _tinybones_scope(clause)
        clause_scope = _scope(cl)
        resolved_scope, _ = _resolve_scope(clause, cl, clause_scope, name)
        # (1) "your graveyard" — forced 'you' (rescope wins).
        if _GY_YOUR_RE.search(cl):
            out.add(("graveyard_matters", rescope or "you"))
        # (2) a bare "graveyard" mention (not "your graveyard") — clause-resolved scope.
        if "graveyard" in cl and "your graveyard" not in cl:
            out.add(("graveyard_matters", rescope or resolved_scope))
        # (3) exile-mill of an opponent's library — forced 'opponents'.
        if _GY_EXILE_MILL_OPP_RE.search(cl):
            out.add(("graveyard_matters", rescope or "opponents"))
    return out


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
    # ADR-0027: color_hoser (a color-HATE card — destroy/exile/counter/restrict/bounce
    # keyed on a NAMED color, or a "non<color> creatures get -X/-X" anthem-debuff)
    # migrated to the Card IR. The structural arm (destroy/exile/counter_spell + a
    # HasColor subject) carries the +1 ir_only recall (Reign of Chaos — non-contiguous
    # "destroy … target white creature"); the byte-identical _COLOR_HOSER_RE kept mirror
    # over kept_oracle in extract_signals_ir covers the predicate-DROPPED / scattered-
    # category tail phase can't structure (color-less counterspell subjects, NotColor
    # pump-debuffs typed cat='pump', the bounce/restriction forms). This _DETECTORS row
    # is deleted; the regex is BROADER than the byte-mirror (+1 ir_only), so the
    # has_other_plan voltron silence is re-supplied by a byte-identical
    # _COLOR_HOSER_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS, which would over-
    # silence Reign of Chaos). The serve spec stays hand-registered. CR 105.2 / 613.1e.
    # ADR-0027 t2b4-C: type_change ("protection from <subtype>" — Gor Muldrak) migrated
    # to the Card IR (kept_detector). phase DROPS the protection ARGUMENT (the subtype),
    # and Gor Muldrak's own static is dropped entirely, so there is no structural form.
    # extract_signals_ir mirrors the _type_hoser_clause subtype-gated word detector over
    # the joined oracle (clause-safe). This _DETECTORS row is deleted; the clause helper
    # stays (the IR path reuses it); the serve stays hand-registered.
    # ADR-0027 spellcast_matters (signals-only, SIDECAR 50): this _IS_BUILDAROUND_RE
    # producer (the instant/sorcery BUILD-AROUND with no cast trigger — Lier, Kess,
    # Dralnu) is deleted with the migration. It rides the byte-identical kept mirror
    # _detect_spellcast_matters (re-run PER-CLAUSE over the reminder-stripped
    # kept_oracle in extract_signals_ir) — flat == per-clause (the `[^.]{0,50}` arm
    # never crosses a sentence), so its firing set is byte-identical. The deleted
    # producer fired HIGH (forced scope 'you') and fed has_other_plan, so the
    # byte-identical _spellcast_has_plan (below) re-supplies the voltron silence for
    # BOTH the hybrid and the pure-regex (ir is None) paths. Serve stays
    # hand-registered. CR 601.2.
    # ADR-0027 t2b4a-B: xspell_matters ({X}-spells payoff) migrated to the Card IR —
    # the `HasXInManaCost` predicate on a `cast_spell` trigger subject (Zaxara, Nev,
    # Zimone …) + a kept effect-raw word mirror (_XSPELL_HOOK_RE minus _XSPELL_VETO_RE)
    # for the predicate-dropped tail (Unbound Flourishing, Rosheen Meanderer). This
    # _DETECTORS row is deleted; the serve spec stays hand-registered. CR 202.1/107.3.
    # ADR-0027 β: creature_etb (the ETB-VALUE / ETB-doubler / delayed-ETB-payoff lane,
    # both the "you" value scope and the "opponents" punisher scope) migrated to the
    # Card IR via a BYTE-IDENTICAL kept mirror. Both _DETECTORS rows are deleted; the
    # lane now fires from _creature_etb_clauses (the EXACT per-clause logic, pinned
    # above) via _CREATURE_ETB_MIRROR in _signals_ir over the reminder-stripped
    # kept_oracle — a structural etb-trigger arm MISSES the static-replacement doublers
    # (Panharmonicon/Yarok) and Ephara's upkeep-gated delayed payoff. Both rows fired
    # HIGH-confidence and fed has_other_plan, so the _CREATURE_ETB_PLAN_MIRROR below
    # re-supplies the commander-damage voltron silence. The serve specs (both scopes)
    # stay hand-registered in signal_specs.py. CR 603.6.
    # creatures_matter (the go-wide scaling lane) MIGRATED to the Card IR (ADR-0027):
    # its over-broad "creatures you control"/"for each creature you control" substring
    # producer is DELETED. The lane now fires from the structural IR — count/aggregate
    # operands over your generic creature board, team anthems (pump/grant/base-P/T),
    # mass keyword/evasion grants, mass untaps, and the token-maker cross-open — served
    # via extract_signals_hybrid (MIGRATED_KEYS). The substring producer over-fired on
    # subtype/color lords, single targets, attack/combat triggers, and cost taps; the
    # IR over-fire boundary (generic-set, no subtype) keeps those out. serve spec stays
    # in signal_specs.
    # ADR-0027: creature_recursion (the "loop a single creature" build-around — return
    # a CREATURE card from a graveyard, to HAND or BATTLEFIELD: Raise Dead, Gravedigger,
    # Reanimate, Hua Tuo, Meren) migrated to the Card IR. This _DETECTORS producer (the
    # "(?:return|put|choose) … creature card … (in|from) your graveyard" detector,
    # forced scope 'you' HIGH) is DELETED; its pattern is pinned as
    # CREATURE_RECURSION_REGEX in _sweep_detectors. The lane now fires from a STRUCTURAL
    # `reanimate`+Creature arm (recall GAIN, +160 GY->battlefield reanimators the
    # brittle "your graveyard" regex missed) PLUS the byte-identical
    # _CREATURE_RECURSION_MIRROR in _signals_ir over the reminder-stripped kept_oracle
    # (the 132 GY->hand / GY->library cards phase doesn't structure as `reanimate`).
    # DISTINCT from reanimator (GY->BATTLEFIELD only) and graveyard_matters (any self-GY
    # care). The producer fired HIGH-confidence scope 'you' and fed has_other_plan, so
    # the _CREATURE_RECURSION_PLAN_MIRROR below re-supplies the commander-damage voltron
    # silence (the IR path is BROADER, so NOT _VOLTRON_SILENCING_PLAN_KEYS). The serve
    # spec stays hand-registered in signal_specs.py. CR 700.4 / 903.10a.
    # ADR-0027: land_creatures_matter migrated to the Card IR — fired from the shared
    # land-animator predicate (animate/base_pt_set/type_set over a Land subject) +
    # Land+Creature dual-type anthem/maker subjects (Sylvan Advocate, Timber Protector,
    # Jyoti) + a kept oracle mirror (signals._IR_KEPT_DETECTORS) for the self-animate
    # manlands phase drops. This _DETECTORS producer is deleted; the serve spec stays
    # hand-registered in signal_specs.py.
    # ADR-0027 β: lifegain_matters migrated to the Card IR. This _DETECTORS producer
    # (the lifegain payoff / source detector — "whenever you gain life", "you gain N
    # life", "gained life this turn", "gain life equal to", "if you would gain life",
    # pinned now as ARM (A) of LIFEGAIN_MATTERS_REGEX in _sweep_detectors) AND the
    # inline self-bleed-wants-sustain block in extract_signals (ARM (B); deleted below)
    # are deleted. The lane fires from a RECALL-GAINING structural arm in
    # extract_signals_ir (a `gain_life` Effect scope you/any + a `life_gained` trigger +
    # the shared lifelink keyword map — +77 commander-legal cards the bare "you gain"
    # regex MISSED: directed "target player gains N life" / "each opponent gains 1
    # life") PLUS the byte-identical _LIFEGAIN_MATTERS_MIRROR (the EXACT deleted
    # producers over reminder-stripped kept_oracle — 247 regex-only cards restored, 0
    # new over-fire). This _DETECTORS row fired HIGH-confidence (forced scope 'you') and
    # counted toward has_other_plan, so the _LIFEGAIN_MATTERS_PLAN_MIRROR (below) re-
    # supplies the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, matching the
    # token_copy_makers / conjure_makers byte-identical-mirror pattern. The serve spec
    # (signal_specs) survives — it was always hand-registered and independent of this
    # regex. CR 119 / 118 / 903.10a.
    # ADR-0027 graveyard scope/origin/zone (SIDECAR v29): graveyard_matters migrated to
    # the Card IR. The THREE _DETECTORS producers (the "your graveyard"→'you' row, the
    # bare-"graveyard" clause-resolved row, the exile-mill-of-opponents→'opponents' row)
    # are DELETED here; their patterns are pinned as _GY_YOUR_RE / _GY_EXILE_MILL_OPP_RE
    # and the byte-identical PER-CLAUSE mirror _graveyard_matters_clauses (above). The
    # lane now fires from the rich structural zone arms in extract_signals_ir (mill /
    # reanimate / graveyard_recursion / cast_from_zone / exile-from-GY / play-from-GY /
    # in:graveyard count / the trigger-zone arm — each scoped by _gy_scope, which maps
    # a structurally-'any' GY effect to the SELF-graveyard default 'you', so no
    # forbidden ('graveyard_matters','any') avenue opens) UNION the byte-identical
    # mirror over the reminder-stripped kept_oracle (the broad "graveyard"-mention
    # recall phase has no structural form for). The deleted producers fired
    # HIGH-confidence and fed has_other_plan, so _graveyard_matters_has_plan re-supplies
    # the voltron silence (the IR re-supply is BROADER, so NOT
    # _VOLTRON_SILENCING_PLAN_KEYS). The serve specs
    # (signal_specs, ('graveyard_matters',{'you','opponents'})) are hand-registered and
    # independent of these regexes — they survive. CR 400.7 / 701.17a / 903.10a.
    # ADR-0027: vanilla_matters migrated to the Card IR — the HasNoAbilities
    # subject-Filter predicate (read in _predicate_build_around_lanes). The predicate
    # is its own discriminator (a card merely BEING vanilla never carries it), so the
    # IR drops the regex's lone incidental-mention over-fire (Rise from the Wreck — a
    # multi-target Mount/Vehicle recursion spell that enumerates "creature card with
    # no abilities" as one of four targets, not a vanilla build-around) and ADDS the
    # "Creatures you control with no abilities" anthem the contiguous regex missed
    # (Jasmine Boreal). This _DETECTORS producer is deleted; the serve spec
    # (serve_vanilla=True) stays hand-registered in signal_specs.
    # ADR-0027: forced_attack migrated to the Card IR — the real CR 508.1d
    # "attacks if able" compulsion rides phase's `force_attack` Effect STRUCTURAL arm
    # (extract_signals_ir), and this _DETECTORS "didn't attack this turn|that attacked
    # this turn" PUNISHER-incentive producer (scope "you", Erg Raiders / Kratos /
    # Angel's Trumpet — phase has no structural form for the penalty subject) is DELETED
    # and re-supplied byte-identically by the forced_attack row in
    # _signals_ir._IR_KEPT_DETECTORS. The has_other_plan voltron silence is re-supplied
    # by _FORCED_ATTACK_PLAN_MIRROR below (the IR re-supply is broader, so a byte-
    # identical regex mirror — not _VOLTRON_SILENCING_PLAN_KEYS). CR 508.1d / 903.10a.
    # ADR-0027: goad_makers migrated to the Card IR — detected structurally from the
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
    # ADR-0027: stax_taxes migrated regex→Card IR. This _DETECTORS pacify producer
    # (Gwafa Hazid: neutralizing OTHER creatures so they "can't attack" — a
    # pillowfort/control identity) is DELETED. Its firing is folded into the
    # byte-identical _STAX_TAXES_MIRROR (_signals_ir) over the reminder-stripped
    # kept_oracle, sourced from STAX_TAXES_REGEX (_sweep_detectors) — the union of this
    # row + the deleted _HAND_FLOOR row + the kept SWEEP row. The lane fires from the
    # structural `restriction` scope=='opp' arm (extract_signals_ir) UNION that mirror;
    # the broader arm adds +10 genuine opponent restrictions the regex missed. The
    # deleted producer fired HIGH (forced scope 'opponents') and fed has_other_plan, so
    # a byte-identical _STAX_TAXES_PLAN_MIRROR (below) re-supplies the voltron silence
    # (the IR is BROADER, so NOT _VOLTRON_SILENCING_PLAN_KEYS). The serve spec stays
    # hand-registered in signal_specs. CR 604.1 / 903.10a.
    # ADR-0027 C14: toughness_combat is now a fully STRUCTURAL lane (the byte-identical
    # mirror is retired). This inline _DETECTORS producer (the toughness-as-VALUE payoff
    # half) and the SWEEP combat-redirect row are both gone: project recovers the
    # AssignDamageFromToughness static modification (combat_damage_mod / from_toughness)
    # and the Ref/Aggregate Toughness operand (Quantity op=='toughness'), and the
    # extract_signals_ir arm reads those markers (+129 multi-ability faces phase's
    # static-drop missed; AssignNoCombatDamage / "equal to its power" over-fires
    # excluded). has_other_plan silence is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS
    # (signals.py). CR 510.1 / 119.3 / 604.3.
    # ADR-0027: snow_matters migrated to the Card IR — detected from the kept
    # word-detector mirror (signals._IR_KEPT_DETECTORS: \bsnow\b; snow is a
    # supertype CR 205.4 phase doesn't surface as a payoff tag). Its _DETECTORS
    # producer is deleted; the hand-written serve spec (signal_specs.py,
    # serve_types=("snow",)) is independent of this regex and survives.
    # ADR-0027 β — activated_ability migrated regex→Card IR. The lane is a card whose
    # ENGINE is a MEANINGFUL activated ability (the {T}:/{Q}: or generic-mana-cost
    # ability a tap-engine commander deck supports with cost reducers — Training
    # Grounds, untappers + haste-for-abilities — Thousand-Year Elixir, and ability
    # copiers — Rings of Brighthearth). This bare cost-shape _DETECTORS regex FLOODED
    # on every land/rock
    # /dork's "{T}: Add {mana}" mana ability (Forest, Sol Ring, Llanowar Elves all
    # matched `{t}:`). The migrated structural arm (extract_signals_ir) gates on phase's
    # is_mana_ability (the Mana effect projects to category 'ramp' — dropped) + the
    # SIDECAR-v15 'genericmana' cost token (the regex's generic branch excluded colored-
    # only firebreathing {R}: — fires the mana branch only on a generic-numeral / {0} /
    # {X} cost), so the flood is structurally impossible. The exact deleted regex is
    # pinned as ACTIVATED_ABILITY_REGEX (_sweep_detectors); it fired high-confidence
    # scope 'you' feeding has_other_plan, so a byte-identical _ACTIVATED_ABILITY_PLAN_
    # MIRROR re-supplies the voltron silence. The serve spec stays its OWN hand-
    # registered curated search pool (signal_specs), independent of this regex. The IR
    # arm is BROADER (+recall: generic-mana engines past the 18-char window — the
    # Moonfolk land-bounce cycle, Eldrazi processors, tap-untapped-creatures value —
    # Sigil Tracer, Volrath's Gardens), so the plan mirror — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — restores the silence set. CR 602.1a / 903.10a.
    # ADR-0027: the reanimator PAYOFF regex ("enters/cast FROM a graveyard") is deleted
    # with the reanimator migration. It CONFLATED the reanimator archetype (active
    # creature reanimation — a `reanimate` effect, the migrated IR bind) with the
    # escape/disturb/flashback "cast from a graveyard" engine, which is a SEPARATE
    # graveyard-recursion axis (CR 702.34 casting ≠ reanimation putting onto the
    # battlefield — rules-lawyer-verified). The structural IR correctly excludes the
    # cast-from-graveyard cards; the regex's 36 "enters/cast from a graveyard" payoff
    # cards (Prized Amalgam, River Kelpie, Flayer of the Hatebound — self-recursion /
    # escape, not the archetype) are the over-fire the migration drops.
    # ADR-0027 spellcast_matters (signals-only, SIDECAR 50): the MAIN spellslinger cast
    # detector ("whenever you cast a spell" payoff — NOT enchantment/artifact-cast,
    # which route to their own type lanes — plus the past-tense spell-COUNT payoff
    # "spells you've cast this turn", the instant/sorcery COST reducers, cast-from-zone,
    # and next-cast-copy glue) is deleted with the migration. The IR re-reads the
    # structural `cast_spell` trigger for the TYPED you-cast payoff (scope='any' + a
    # typed-noncreature subject + the card oracle's "you cast", verified 0 over-fire —
    # Talrand, Guttersnipe, Young Pyromancer) PLUS the byte-identical kept mirror
    # _detect_spellcast_matters (re-run PER-CLAUSE over the reminder-stripped
    # kept_oracle), which recovers the when/whenever-conflated + non-trigger glue phase
    # doesn't structure. The deleted producer fired HIGH (forced scope 'you') and fed
    # has_other_plan, so _spellcast_has_plan (below) re-supplies the voltron silence.
    # Serve stays hand-registered. CR 601.2 / 608 / 207.2c.
    # ADR-0027: death_matters migrated to the Card IR — the aristocrats payoff (OTHER
    # creatures dying, CR 700.4: "dies" = battlefield→graveyard, disjoint from the
    # broader `leaves` event ltb_matters reads). The lane fires from the STRUCTURAL
    # `dies`-trigger arm in extract_signals_ir (+90 ir_only recall — the verbose "is put
    # into a graveyard from the battlefield" payoffs the literal-"dies" regex missed)
    # PLUS the byte-identical _DEATH_MATTERS_MIRROR (the deleted producers' EXACT union,
    # pinned as DEATH_MATTERS_REGEX) run per-clause for the morbid "if a creature died
    # this turn" CONDITION family + the conferred/quoted dies triggers + the "dying"+
    # "trigger" death-doublers no single structural shape covers. Both this clause-
    # scoped _DETECTORS producer and the "died this turn" _HAND_FLOOR producer are
    # deleted; the serve spec stays hand-registered. The _DEATH_MATTERS_PLAN_MIRROR
    # re-supplies the has_other_plan voltron silence. (CR 700.4 / 603.6e.)
    # ADR-0027: sacrifice_outlets migrated to the Card IR — a you-sacrifice EFFECT
    # (scope not opp/each, a non-land subject, not a forced-opponent edict raw) + a
    # "sacrificed" trigger payoff + the Casualty keyword + the additional-cost /
    # granted / pitch / morph / pay-or-die / bullet sac markers (project.py). The
    # broad oracle regex over-fired on land-sac, edicts, "controller may sacrifice",
    # Ward—Sacrifice, and reanimation engines with no sacrifice. NOT in
    # _IR_FLOOR_LANES; this _DETECTORS producer is deleted; the serve spec stays
    # hand-registered. (CR 701.16.)
    # ADR-0027: attack_matters migrated to the Card IR — the COMBAT-trigger / attacked-
    # this-turn payoff axis. The lane fires from the STRUCTURAL `attacks`-trigger arm
    # (_PAYOFF_TRIGGER_KEYS) + the `Attacking` filter-predicate arm in the IR path (+135
    # ir_only recall — the reminder-only Training/Mentor/Exalted/Mobilize attack
    # triggers + the "Attacking creatures you control get …" anthems the bare substring
    # missed) PLUS a byte-identical _ATTACK_MATTERS_MIRROR (the two regex-expressible
    # substring branches pinned as ATTACK_MATTERS_REGEX — "attacking causes" / "attacked
    # this turn" — plus the inline "whenever"&"attack" substring-AND the deleted lambda
    # ran) run per-clause, recovering the disjunctive "enters or attacks" / "attacks or
    # blocks" triggers + the Raid condition family phase has no structural shape for.
    # This _DETECTORS producer is deleted; the 10 combat KEYWORDS move to the IR-only
    # _IR_KEYWORD_MAP; the serve spec stays hand-registered. The deleted producer fed
    # has_other_plan when it fired HIGH, so a faithful reproduction restores the voltron
    # silence below. (CR 508 / 702.10.)
    # ADR-0027 β: draw_matters migrated to the Card IR — a scope-gated `drawn`-trigger
    # structural arm (scope != "opp", excluding the opponent_draw_matters punisher lane)
    # PLUS a byte-identical draw_matters row in signals._IR_KEPT_DETECTORS for the
    # past-tense draw-COUNT payoff ("for each card you've drawn this turn" — Proft's
    # Eidetic Memory, Kydele, Thundering Djinn) that has no `drawn` trigger. This
    # _DETECTORS producer is deleted; the serve spec stays hand-registered in
    # signal_specs.py. The deleted producer fed has_other_plan (HIGH-confidence, scope
    # 'you'), so its voltron silence is restored by _DRAW_MATTERS_PLAN_MIRROR below.
    # CR 120.1 / 903.10a.
    # ADR-0027: landfall migrated to the Card IR — the LAND-ETB payoff axis (the
    # "Landfall —" ability word, the keyword-LESS "whenever a land you control
    # enters" trigger, the extra-land STATIC "play N additional lands", and land
    # RECURSION from the graveyard). The lane fires from the STRUCTURAL `etb`-trigger
    # arm (a Trigger whose subject is a Land) in the IR path (+5 ir_only recall — the
    # disjunctive / qualified "this land or another land enters" / "land … enters
    # from exile" / "nonbasic land an opponent controls enters" forms the bare
    # substring missed) PLUS a byte-identical _LANDFALL_MIRROR (the three
    # regex-expressible branches pinned as LANDFALL_REGEX — the "landfall" ability
    # word, "play N additional lands", and the two land-recursion forms — plus the
    # inline "whenever a land" & "enter" substring-AND the deleted lambda ran) run
    # per-clause, recovering the ability-word CONDITION + extra-land + recursion
    # families phase has no structural shape for. This _DETECTORS producer is deleted;
    # the serve spec stays hand-registered. The deleted producer fired HIGH (forced
    # scope 'you' → always HIGH), so it fed has_other_plan, and a byte-identical
    # _LANDFALL_PLAN_MIRROR restores the voltron silence below. (CR 207.2c / 305.)
    # ADR-0027: plus_one_matters migrated to the Card IR — it fires on ANY +1/+1
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
    # ADR-0027: combat_damage_matters (the BASE CR-510 combat-damage payoff: "whenever
    # ~ deals combat damage to a player/an opponent/each opponent" + the passive "player
    # who was dealt combat damage by ~" — Edric, Dragonlord Ojutai, Wrexial, Hope of
    # Ghirapur) migrated to the Card IR. This _DETECTORS producer is DELETED; the lane
    # rides a byte-identical _IR_KEPT_DETECTORS mirror of THIS regex (the structural
    # combat_damage/deals_damage arm over-fired the recipient — see the IR mirror's
    # rationale). The serve spec stays hand-registered. The deleted producer fired HIGH
    # (forced scope 'opponents') and fed has_other_plan, so combat_damage_matters is
    # added to signals._VOLTRON_SILENCING_PLAN_KEYS (byte-identical IR re-supply).
    # CR 510 / 903.10a.
    # ADR-0027: discard_matters migrated to the Card IR — this _DETECTORS producer (the
    # "whenever you discard" payoff OR the same-clause loot outlet "draw a card, then
    # discard") is DELETED. Both halves are reproduced from the IR: the "whenever you
    # discard" payoff (Hashaton, "whenever a player discards") fires from the scope-
    # gated `discarded`-trigger structural arm (scope != "opp", excluding the
    # opponent_discard punisher lane), and the loot outlet from the byte-identical
    # _LOOT_FULLTEXT_RE kept-mirror in signals._IR_KEPT_DETECTORS (whose broader pattern
    # is a strict superset of this entry's "draw N cards, then discard" arm). The serve
    # spec stays hand-registered in signal_specs.py; the deleted producer fed
    # has_other_plan (HIGH-confidence, scope 'you'), so its voltron silence is restored
    # by _DISCARD_MATTERS_PLAN_MIRROR (== _LOOT_FULLTEXT_RE) below. CR 702.35 / 120.1 /
    # 903.10a.
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
# ADR-0027: card_draw_engine is MIGRATED to the Card IR — extract_signals no longer
# invokes _detect_card_draw, but _signals_ir.extract_signals_ir imports it for a
# byte-identical KEPT MIRROR (per-clause re-run over the reminder-stripped kept_oracle).
# So _CARD_DRAW_RE + _detect_card_draw STAY PINNED here. Do not inline/delete them.
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


# ── ADR-0027 spellcast_matters kept-mirror helpers (signals-only, SIDECAR 50) ──
# The THREE deleted spellcast_matters producers, pinned so the IR path
# (extract_signals_ir) re-runs them PER-CLAUSE over the reminder-stripped kept_oracle
# for a byte-identical kept mirror, and so extract_signals's has_other_plan re-supplies
# the voltron silence the deleted HIGH-confidence producers used to feed.
_SPELLCAST_RECASTER_RE = re.compile(
    r"(?:you may cast|cast target|copy target)[^.]*"
    r"(?:instant or sorcery|instant and sorcery)"
    r"|instant and sorcery (?:spells? )?you (?:may )?cast",
    re.IGNORECASE,
)


def _spellcast_main_clause(c: str) -> bool:
    """The deleted MAIN spellcast detector (lowercased reminder-stripped clause)."""
    return (
        (
            "whenever you cast" in c
            and "spell" in c
            and not _re(r"whenever you cast an (?:enchantment|artifact) spell")(c)
        )
        or _re(r"spells? you've cast this turn")(c)
        or _re(r"instant and sorcery spells? you cast cost")(c)
        or _re(r"cast an instant or sorcery spell from")(c)
        or _re(r"when you (?:next )?cast an instant or sorcery spell this turn")(c)
    )


def _detect_spellcast_matters(clause: str) -> bool:
    """UNION of the three deleted spellcast_matters producers for one clause.

    The two _DETECTORS lambdas ran on the lowercased clause; the _HAND_FLOOR recaster
    ran IGNORECASE on the raw clause — identical on a lowercased input. Forced scope
    'you'. The IR path imports this for the byte-identical kept mirror.
    """
    cl = clause.lower()
    return (
        _IS_BUILDAROUND_RE.search(cl) is not None
        or _spellcast_main_clause(cl)
        or _SPELLCAST_RECASTER_RE.search(cl) is not None
    )


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
    # NON_CREATURE_TOKEN denylist (CR 111.10 / 205.3g): Treasure / Clue / Food / … are
    # ARTIFACT-token subtypes, not creature kindred — a few leak into CREATURE_SUBTYPES
    # from the bulk harvest. Deny BEFORE the vocab so "Treasures you control" / "each
    # Clue" never mints a false-positive tribal subject (they feed the dedicated
    # clue/food/treasure + artifacts_matter lanes instead).
    if w in NON_CREATURE_TOKEN:
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
# bodies + lords/equipment/ETB payoffs surface alongside the existing has_ninjutsu.
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


# ADR-0027 (voltron migration): the Equipment/Aura PAYOFF regex — the broad
# "attach an Equipment/Aura / for each Aura / cast an Aura / equipped creatures /
# unattach / search for an Equipment card …" build-around tell (CR 301.5 Equipment /
# 303.4 Aura / 702.6 enchant). The deleted _HAND_FLOOR producer fired HIGH scope
# 'you' per-clause, UNGATED (a voltron tool — Plate Armor, Magnetic Theft — and a
# payoff commander — Sram, Koll — both qualify, regardless of being a creature). Pinned
# here so the IR path can run the SAME regex per-clause (byte-identically; the `[^.]`
# spans never cross a sentence) UNIONed with the structural _detect_voltron_payoff_ir
# recall gain. The _HAND_FLOOR row below references it for the no-sidecar regex path.
VOLTRON_PAYOFF_REGEX = (
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
    r"|(?:legendary )?equipment attached to it"
)
_VOLTRON_PAYOFF_RE = re.compile(VOLTRON_PAYOFF_REGEX, re.IGNORECASE)

# Each floor detector requires a structural anchor, never a bare substring, so
# incidental one-shot makers (Beledros, Faramir) and self-restrictions (Kefnet)
# don't misfire. Hand-written source stays as (key, compiled-pattern, scope) tuples;
# the assembly below adapts both these and the mined sweep into Detector records.
_HAND_FLOOR: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # ADR-0027: goad_makers migrated to the Card IR — this second goad producer (the
    # force-OTHER-creatures-to-attack form + the "whenever a player attacks" / Kazuul
    # defending-player reward) is deleted. The IR recovers all three structurally: the
    # single-target political force via _GOAD_STYLE_FORCE over phase's force_attack
    # effect; the reward conditions via the _GOAD_REWARD_REF face marker
    # (project._dropped_static_markers). Floor-mirror-dep == 0 (goad_makers is NOT in
    # _IR_FLOOR_LANES). The hand-written serve spec (signal_specs.py) survives.
    # ADR-0027: modified_matters migrated to the Card IR — this FIRST of the two
    # _HAND_FLOOR producers (the indirect "power greater than its base power" anchor:
    # Kutzil, Baird — the only way a creature's power exceeds its BASE power is a
    # counter or a pump, CR 613.4c layer 7c, the modified-via-counter/Aura/Equip side)
    # is deleted. phase v0.1.19 doesn't structure "modified" (CR 700.9 — a derived
    # counter/Equipment/Aura union, not a parsed predicate), so the IR recovers it via
    # the UNION kept WORD MIRROR (`\bmodified\b` OR "power greater than its base power")
    # in _signals_ir._IR_KEPT_DETECTORS, run flat over the reminder-stripped joined-face
    # kept_oracle (byte-identical: both==47, regex_only==0, ir_only==0; scope 'you',
    # HIGH). The deleted producers fired HIGH-confidence scope 'you' and fed
    # has_other_plan; since the IR re-supply is the SAME breadth (residual 0),
    # modified_matters is added to _VOLTRON_SILENCING_PLAN_KEYS (signals.py) to
    # re-supply the pre-migration commander-damage voltron silence (file-swap voltron
    # delta 0). The SECOND producer (the `\bmodified\b` word) is deleted below. The
    # hand-written serve spec (signal_specs.py) survives. CR 700.9 / 301.5 / 303.4.
    # (plus_one_matters — formerly the "power greater than its base power" twin of this
    # producer — is independently migrated to the Card IR via project._P1P1_HAVE_FACE /
    # signals._P1P1_HAVE_REF → counters_have_ref; that producer is deleted too.)
    # ADR-0027: low_power_matters migrated to the Card IR — a non-dynamic
    # PtComparison:Power:LE/LT predicate on a you-controller Creature Filter, read by
    # _predicate_build_around_lanes (the recursion cards — Alesha, Reveillark — carry it
    # natively; phase DROPS it on the buff/etb subject shapes, recovered by a
    # `_LOW_POWER_REF` marker that rebuilds the Power:LE subject from "creatures you
    # control with power N or less" — Subira, Underfoot Underdogs). Removed from
    # _IR_FLOOR_LANES; serve stays hand-registered.
    # ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror. Both deleted
    # _HAND_FLOOR producers (this GO-WIDE count-scaler — "gets +N/+N for each creature
    # you control" / "power … equal to the number of creatures you control": Leonardo,
    # Adeline, Suki, Bravado — and the broad token PAYOFF producer below) are unioned
    # into TOKENS_MATTER_REGEX (_sweep_detectors) and re-fired byte-identically by
    # _TOKENS_MATTER_MIRROR in _signals_ir. Both fired HIGH-confidence (forced scope
    # 'you') and fed has_other_plan (a go-wide token engine is a real plan, not a
    # vanilla beater), so the voltron silence is re-supplied via
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py). The serve spec stays hand-registered in
    # signal_specs.py (its curated search regex was always independent of these
    # producers). CR 111.1 / 701.47.
    # ADR-0027 spellcast_matters (signals-only, SIDECAR 50): this recaster/copier
    # _HAND_FLOOR producer (Mavinda recasts from the yard, Velomachus casts off the
    # top, Naru Meha copies — enabler/copier forms with no "whenever you cast" trigger)
    # is deleted with the migration. Its pattern is pinned as _SPELLCAST_RECASTER_RE and
    # rides the byte-identical kept mirror _detect_spellcast_matters (re-run PER-CLAUSE
    # over the reminder-stripped kept_oracle in extract_signals_ir) — the `[^.]*` arm
    # never crosses a sentence, so flat == per-clause. CR 601.2.
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
    # ADR-0027: land_sacrifice_matters (Gitrog, Titania, Slogurk, Zuran Orb, Sylvan
    # Safekeeper — a card paying an ongoing land-sac cost, drawing/growing when lands
    # hit the graveyard, or offering a repeatable "Sacrifice a land:" outlet) migrated
    # to the Card IR. phase carries NO structural form (the structural sacrifice arm
    # emits this lane on 0 commander-legal cards — a land-ONLY sac subject is routed
    # AWAY from sacrifice_outlets but never re-homed), so this _HAND_FLOOR producer is
    # deleted and survives BYTE-IDENTICALLY as the LAND_SACRIFICE_REGEX row in
    # _IR_KEPT_DETECTORS (scope 'you', HIGH conf — the EXACT pattern run flat over the
    # reminder-stripped kept_oracle; commander-legal: flat==per-clause==66, 0
    # gain/loss).
    # A distinct archetype from sacrifice_outlets (which EXCLUDES "sacrifice a land" —
    # the fetchland guard), land_destruction (DESTROY a land), land_exchange (swap land
    # CONTROL).
    # The hand-written serve spec (signal_specs.py) is independent and survives. The
    # deleted producer fed has_other_plan (HIGH, scope 'you', not generic/voltron-
    # compat); the hybrid re-silences voltron via _VOLTRON_SILENCING_PLAN_KEYS — the IR
    # re-supply IS this byte-identical mirror (IR==regex==66), so no over-silence and NO
    # _LAND_SACRIFICE_PLAN_MIRROR. CR 701.16 / 903.10a.
    # ADR-0027: proliferate_matters migrated to the Card IR. This divinity /
    # indestructible-counter _HAND_FLOOR producer (Myojin cycle, Arwen — enter
    # with one beneficial counter that proliferate multiplies) is DELETED; it
    # survives byte-identically as a HIGH-confidence _IR_KEPT_DETECTORS mirror in
    # _signals_ir (phase carries no structural form — the enters-replacement
    # place_counter projects with a blank kind the structural edge routes to
    # plus_one_matters, not proliferate_matters). The keyword/charge/remove-cost
    # producers are likewise re-homed; the serve spec stays hand-registered.
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
    # is DELETED with the sacrifice_outlets migration — it over-fired on reanimation
    # engines that name no sacrifice at all (the IR path correctly drops them).
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR. The warp-GRANTING
    # membership cross-open (Tannuk: "cards in your hand have warp" — warp casts a hand
    # card for its warp cost and exiles it at end of turn, a temporary cheat-into-play;
    # a
    # commander handing out warp is a cheat deck wanting fat creatures + cheat enablers)
    # is DELETED; it survives BYTE-IDENTICALLY in the narrow _CHEAT_INTO_PLAY_RESIDUE_RE
    # mirror (the `have warp`/`gains warp` alt) in _signals_ir — phase emits no
    # structural
    # shape for a hand-wide warp grant. CR 702.184a.
    # ADR-0027: death_matters migrated to the Card IR. This "creature DIED this turn"
    # _HAND_FLOOR producer (scope "any", high-confidence — it fed has_other_plan) is
    # deleted along with the clause-scoped _DETECTORS producer above; both survive
    # byte-identically as the _DEATH_MATTERS_MIRROR in _signals_ir (the union pinned as
    # DEATH_MATTERS_REGEX), and the morbid-condition family feeds the regex-path
    # has_other_plan via _DEATH_MATTERS_PLAN_MIRROR below. The serve spec stays hand-
    # registered in signal_specs.py. CR 700.4.
    # ADR-0027 β: debuff_makers migrated to the Card IR. This Maha opponent-SHRINK
    # _DETECTORS row (scope "you") is deleted; it survives byte-identically as the
    # _DEBUFF_MAHA_REGEX _IR_KEPT_DETECTORS mirror, and feeds the regex-path
    # has_other_plan gate via _DEBUFF_MATTERS_PLAN_MIRROR below (it fired high-
    # confidence forced scope, silencing the spurious commander-damage voltron tell).
    # ADR-0027: direct_damage migrated to the Card IR. BOTH _HAND_FLOOR producers (this
    # player-BURN source — Syr Konrad, Mogis, Anathemancer, Fanatic of Mogis — and the
    # any-target/tap-ping/doubler/source-deals-damage producer below) are deleted. The
    # lane fires from the v22 damage Effect SCOPE arm in _signals_ir (scope 'opp'/'each'
    # always reaches a player; scope 'any' fires ONLY when the recipient is NOT
    # creature/permanent-restricted AND the raw names a player — so creature-only bite
    # stays removal) PLUS the byte-identical _DIRECT_DAMAGE_MIRROR (the OR of
    # these two deleted producers) for the under-structured player-reaching tail
    # (doublers, damage-matters payoffs, controller-riders, DFC/coin-flip burst). The
    # serve spec stays hand-registered in signal_specs.py. The deleted producers fired
    # HIGH-confidence scope 'you' and fed has_other_plan; the migrated IR is BROADER
    # (+139 ir_only), so the byte-identical _DIRECT_DAMAGE_PLAN_MIRROR below — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — re-supplies the exact pre-migration voltron silence
    # set. CR 120.1 / 115.4 / 903.10a.
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
    # ADR-0027: arcane_matters migrated to the Card IR via a BYTE-IDENTICAL kept WORD
    # MIRROR (the `\barcane\b` row in _signals_ir._IR_KEPT_DETECTORS, scope 'you'). The
    # Kamigawa Arcane / Splice-onto-Arcane / Spiritcraft archetype — "cast a Spirit or
    # Arcane spell" (Tallowisp), "Splice onto Arcane" (the Kamigawa I/S spells); CR
    # 205.3k spell type, CR 702.47 Splice. phase v0.1.19 doesn't structure Arcane (a
    # SPELL TYPE on Instants/Sorceries, not a creature subtype or keyword), so the IR
    # rides the EXACT deleted pattern over the reminder-stripped kept_oracle (no `[^.]*`
    # span → flat == per-clause → byte-identical, both==92, regex_only==0, ir_only==0).
    # This _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py
    # — splice-onto-arcane + serve_types ('arcane',)) is independent and survives. The
    # deleted producer fed has_other_plan (HIGH, scope 'you'), but is NOT added to
    # _VOLTRON_SILENCING_PLAN_KEYS — the file-swap leaked 0 voltron (all 92 Arcane
    # bodies already carry another plan), so an entry would be dead over-silencing.
    # ADR-0027: has_enlist migrated to the Card IR — detected from the Scryfall
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
    # unblocked attacker" is ALREADY has_ninjutsu, so recast_etb keys on Sneak
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
    # ADR-0027: island_matters migrated to the Card IR (the islandwalk / island-
    # attack-restriction lane: islandwalk bearers Thada Adel / Wrexial; GRANTERS /
    # token-makers / references Lord of Atlantis / Fishliver Oil / Chasm Skulker /
    # Mystic Decree; the Zhou Yu "can't attack unless defending player controls an
    # Island" restriction). The lane fires from a BYTE-IDENTICAL kept WORD MIRROR
    # (_ISLAND_MATTERS_MIRROR in _signals_ir, pinned as ISLAND_MATTERS_REGEX) — NOT the
    # Scryfall keyword array, which misses every GRANTER (the conferred-keyword gap).
    # This _HAND_FLOOR producer is deleted; the serve spec (signal_specs.py, "lands
    # become Islands") survives. The deleted producer fired HIGH-confidence (forced
    # scope 'you') and fed has_other_plan (24 island creatures — Sea Serpent, Marjhan,
    # Zhou Yu — carry island_matters as their SOLE plan), so island_matters is added to
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py) for the byte-identical re-supply
    # (79 == 79, voltron 3010 -> 3010).
    # ADR-0027 β: entered_attacker (the freshly-entered-attacker payoff — Samut
    # "if that creature entered this turn, draw a card" on combat damage;
    # Redoubled Stormsinger forks tokens that entered this turn on attack; Hixus
    # rewards itself having entered this turn) migrated to the Card IR via a
    # BYTE-IDENTICAL kept mirror. The "entered (the battlefield) this turn"
    # predicate is NOT projected (it survives only in raw), so there is no
    # structural IR shape to read — for ~3 commander-legal cards the clean
    # SIGNALS-ONLY path is a byte-identical _ENTERED_ATTACKER_MIRROR of the exact
    # deleted regex (pinned as ENTERED_ATTACKER_REGEX in _sweep_detectors), run
    # per-clause over the reminder-stripped oracle in _signals_ir, byte-identical
    # to this deleted floor Detector. NO voltron PLAN mirror is needed: each of
    # the 3 cards keeps has_other_plan via OTHER high-confidence non-generic
    # signals (combat_damage_matters / creature_etb / attack_matters /
    # tokens_matter), so deleting this producer leaks no voltron tell (voltron
    # delta 0, verified). The serve spec (signal_specs.py, "Haste + ETB pump") is
    # independent of this regex and survives. This _HAND_FLOOR producer is deleted.
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
    # ADR-0027 (t2b5-B → SIDECAR v40): target_own_payoff migrated to the Card IR via a
    # STRUCTURAL trigger read. phase HAS a `BecomesTarget` mode (CR 702.21a), so the
    # lane reads event=='becomes_target' + scope in (you,any) + NOT the project
    # `src:opp` zone tag (the you-can-self-target half — Heartfire Hero / Nadu / Brine
    # Comber / Monk Gyatso). The narrow "creature you control … you may" regex caught
    # only 2 cards; the structural event reaches all the own-target payoffs. This
    # _HAND_FLOOR producer is deleted; the hand-written serve spec (signal_specs.py,
    # en-Kor / {0}-equip enablers) is independent of this regex and survives.
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
    # ADR-0027 β: free_spell_storm migrated to the Card IR. A per-spell SCALING
    # self-discount whose cost drops for each spell cast THIS TURN (Thrasta "for each
    # other spell cast this turn"; Demilich / A-Demilich "for each instant and
    # sorcery spell you've cast this turn") — the deck wants FREE (0-cost) spells to
    # chain and keep cutting it (Ornithopter, Memnite, Lotus Petal, Mishra's Bauble).
    # phase models the discount as a SelfRef ModifyCost{Reduce} static (DROPPED by
    # project._project_static_mods — a self-discount is rules-excluded from the
    # build-around cost_reduction lane, CR 601.2f); project._free_spell_storm_marker
    # re-surfaces it as a dedicated `free_spell_storm` STATIC Effect (the migrated
    # lane reads it in _signals_ir), gated to the cast-this-turn dynamic_count shape
    # so an opponent-spell tax (Delightful Discovery) never fires. FULLY STRUCTURAL —
    # no _PLAN_MIRROR needed (the deleted regex matched only 2 cards; the marker
    # drops its lone over-fire and adds recall). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py. NOT in
    # _IR_FLOOR_LANES (floor-mirror-dep == 0).
    # ADR-0027 (t2b5-B → SIDECAR v40): target_redirect migrated to the Card IR via a
    # STRUCTURAL trigger read. phase HAS a `BecomesTarget` mode (CR 702.21a), and
    # `_project_trigger` surfaces the targeting spell's controller as the `src:opp` zone
    # tag, so the lane reads event=='becomes_target' + scope in (you,any) + src:opp (the
    # opponent-targets-your-stuff punisher — Rayne / Shapers' Sanctuary / Diffusion
    # Sliver / Tectonic Giant). The narrow "an opponent controls … draw" regex caught
    # only 11 cards and double-fired Shapers' Sanctuary into target_own_payoff too; the
    # structural src:opp split is clean. This _HAND_FLOOR producer is deleted. The
    # hand-written serve spec (signal_specs.py, redirect spells) is independent of this
    # regex and survives — the redirect SERVE pool is itself structural via
    # category=='redirect' should anyone tighten it later.
    # ADR-0027: ramp migrated to the Card IR. Its TWO _HAND_FLOOR producers are
    # deleted — this dork-support arm (Raggadragga: "Each creature you control with a
    # mana ability gets +2/+2 … untap it when it attacks") and the main mana-production
    # arm below. The dork-support arm has no structural form (phase drops the "with a
    # mana ability" subject), so it rides _MANA_DORK_SUPPORT_MIRROR in
    # _signals_ir (already present for the mana_amplifier dork arm — same regex); the
    # main arm rides _RAMP_MATTERS_REGEX + the structural `not card_is_land` ramp arm.
    # The has_other_plan voltron silence is re-supplied by _RAMP_MATTERS_PLAN_MIRROR
    # (the migrated IR arm is BROADER, so _VOLTRON_SILENCING_PLAN_KEYS would over-
    # silence). The serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: proliferate_matters migrated to the Card IR. This beneficial-
    # resource-counter _HAND_FLOOR producer (charge — Immard; experience — Ezuri,
    # Mizzix, Meren — counters that accumulate for upside, so the commander wants
    # PROLIFERATE) is DELETED; it survives byte-identically as a HIGH-confidence
    # _IR_KEPT_DETECTORS mirror in _signals_ir (phase carries no structural form
    # for a charge/experience-counter reference). The serve spec stays hand-
    # registered in signal_specs.py.
    # ADR-0027: treasure_matters migrated to the Card IR — detected structurally like
    # blood_matters: a Treasure-subtype make_token maker (incl. the die-roll/vote/choice
    # branch + Aftermath-DFC recovery), a "Sacrifice a Treasure" SAC PAYOFF, and a
    # `token_subtype_ref` "Treasures you control" / "was a Treasure" cares-about marker
    # (project._narrow_token_subtype_makers + _dropped_static_markers). Removed from
    # _IR_FLOOR_LANES; floor-mirror-dep == 0. The structural IR is broader-and-correct
    # recall (the make_token-SUBJECT Treasure makers the "create … treasure token" regex
    # missed — Old Gnawbone, Prismari Command, Wanted Scoundrels). This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec survives.
    # ADR-0027: artifacts_matter migrated to the Card IR — the ARTIFACTS go-wide /
    # matters axis (artifact-population anthems / counts, affinity / metalcraft /
    # improvise, artifact ETB / cast triggers, tutors / recursion / sac-outlets / token-
    # makers). The lane fires from the STRUCTURAL arms in extract_signals_ir (the
    # `_TYPE_MATTERS_LANE` count/grant/trigger DOERs, the `_ARTIFACT_TOKEN_SUBTYPES`
    # maker/sac arm, the type-gate condition arm, and the type_line membership arm —
    # +325 ir_only recall the brittle oracle regex missed: Food/Clue/Treasure subtype
    # sac payoffs + DFC back-face recursion) PLUS the NARROWED _ARTIFACTS_MATTER_MIRROR
    # (the deleted _HAND_FLOOR producer UNIONed with the kept "if you control an
    # artifact" SWEEP row) run per-clause for the oracle-idiom family no structural
    # shape covers.
    # NARROWED: the bare `\baffinity\b` branch became `affinity for artifacts`,
    # dropping the 22 affinity-for-non-artifact over-fires (Icebreaker Kraken's snow
    # affinity, Argivian Phalanx's creature affinity — none an artifacts deck). BOTH
    # this clause-
    # scoped _HAND_FLOOR producer AND the line-4349 type_line membership producer are
    # deleted (the IR membership arm reproduces the latter byte-identically); the kept
    # SWEEP row stays (len(SWEEP_DETECTORS) >=36). The serve spec stays hand-registered;
    # _ARTIFACTS_MATTER_PLAN_MIRROR re-supplies the has_other_plan voltron silence.
    # (CR 702.41 / 207.2c / 205.3g.)
    # ADR-0027: enchantments_matter migrated to the Card IR — the ENCHANTMENTS go-wide
    # / matters axis (enchantment-population anthems / counts, constellation,
    # enchantress cast triggers, enchantment tutors / recursion / sac-outlets /
    # token-makers, Role-token makers — Roles ARE Aura enchantments per CR 303.7 /
    # 111.10j). The lane fires from the STRUCTURAL arms in extract_signals_ir (the
    # `_TYPE_MATTERS_LANE` Enchantment count/grant/trigger DOERs, the Enchantment
    # make_token / Bargain-gated sac-payoff DOER, the type-gate condition arm, the
    # becomes-Enchantment / type-recursion / type-tutor arms, the Aura-subtype "loose
    # enchantments member" arm, and the type_line membership arm — shared with
    # artifacts_matter; +95 ir_only recall the brittle oracle regex missed: Licids that
    # become Auras, Aura / Glimmer / enchantment-creature token makers, Aura recursion,
    # single-type sac-an-enchantment outlets, "if you control an enchantment"
    # conditions) PLUS the BYTE-IDENTICAL _ENCHANTMENTS_MATTER_MIRROR (the deleted
    # _HAND_FLOOR producer ALONE — there is NO dedicated enchantment SWEEP row, unlike
    # artifacts' "if you control an artifact" row, so SWEEP_DETECTORS stays 36) run
    # per-clause for the oracle-idiom family no structural shape covers (enchantment
    # tutors / recursion-from-graveyard /
    # "enchantment card in your hand" miracle-grant / Role-token makers). BOTH this
    # clause-scoped _HAND_FLOOR producer AND the type_line membership producer below are
    # deleted (the IR membership arm reproduces the latter byte-identically). The serve
    # spec stays hand-registered; _ENCHANTMENTS_MATTER_PLAN_MIRROR re-supplies the
    # has_other_plan voltron silence. (CR 205.2 / 303 / 303.7.)
    # ADR-0027: tokens_matter migrated to the Card IR via a kept-mirror — this broad
    # token PAYOFF producer ("tokens you control" anthems/refs — Intangible Virtue,
    # Mirror Box, Brudiclad; a "whenever a/one or more/another … token … enters" trigger
    # — Woodland Champion, Junk Winder; and the token DOUBLER replacement "tokens would
    # be created/put" / "create twice that many … token" / "twice that many … tokens" —
    # Doubling Season, Parallel Lives, Mondrak, Divine Visitation) is deleted, unioned
    # with the GO-WIDE count-scaler above into TOKENS_MATTER_REGEX and re-fired by
    # _TOKENS_MATTER_MIRROR in _signals_ir. Voltron silence re-supplied via
    # _VOLTRON_SILENCING_PLAN_KEYS (signals.py). CR 111.1 / 701.47.
    # ADR-0027: stax_taxes migrated regex→Card IR. This _HAND_FLOOR producer
    # (`opponents can't` / `spells your opponents cast cost` / `creatures your opponents
    # control`) is DELETED with the _DETECTORS pacify row above. Its broad `creatures
    # your opponents control` branch over-fired on every -X/-X debuff anthem (Elesh
    # Norn, Massacre Wurm, Cower in Fear — NOT restriction/tax statics), which the
    # structural `restriction` IR arm correctly drops. The genuine firings are
    # reproduced byte-identically by _STAX_TAXES_MIRROR (_signals_ir) from
    # STAX_TAXES_REGEX (the union of this row + the deleted _DETECTORS row + the kept
    # SWEEP row). The deleted producer fired HIGH (forced scope 'opponents') and fed
    # has_other_plan, so the byte-identical _STAX_TAXES_PLAN_MIRROR (below) re-supplies
    # the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS (the IR is broader). The
    # serve spec stays hand-registered. CR 604.1 / 903.10a.
    # ADR-0027 β: cost_reduction migrated to the Card IR — this _HAND_FLOOR producer
    # (and the SWEEP_DETECTORS row) are deleted. The lane fires from the IR arm +
    # _COST_REDUCER_MIRROR in _signals_ir; the deleted regex's voltron silence is
    # restored by _COST_REDUCTION_PLAN_MIRROR above (its high-confidence producer fed
    # has_other_plan). The serve survives via the pinned COST_REDUCTION_REGEX constant.
    # ADR-0027: cast_from_exile migrated to the Card IR — this _HAND_FLOOR producer
    # (the CAST/PLAY-FROM-EXILE build-around: payoffs/enablers that cast or play cards
    # FROM EXILE — plot, the "from exile" / "from anywhere other than your hand" Paradox
    # triggers, self-cast-from-exile creatures, exile-and-cast engines, the Adventure-
    # style exile-from-hand cycle) is DELETED. phase carries NO usable structural form
    # (it drops the "from exile" zone off the cast_spell trigger AND the self-cast
    # cast_from_zone Effect; the only exile cast-zone it projects — castable_zones=
    # ('exile',) — is the 51-card foretell-spell SERVE pool, DISJOINT from these 77
    # detector firings), so the lane fires SOLELY from the byte-identical kept word
    # mirror — CAST_FROM_EXILE_REGEX (pinned in _sweep_detectors) run FLAT over the
    # reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS loop
    # (commander-legal: flat==per-clause==77, 0 gain/loss). Distinct from impulse_top_
    # play (exile the TOP of YOUR library then temporary-play — its own avenue) and
    # play_from_top below (the ONGOING permission to play off the top of the LIBRARY — a
    # different zone, not exile). The deleted producer fired HIGH (scope 'you') and fed
    # has_other_plan, so the hybrid re-silences the spurious commander-damage voltron
    # tell via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) — byte-identical re-supply, no
    # over-silence. The serve survives via the standalone _spec in signal_specs.py
    # (never reads this regex). cast_from_exile was NEVER a SWEEP key, so no SWEEP row /
    # floor count moves (len stays 33). CR 207.2c / 601.3b / 903.10a.
    # ADR-0027 β: play_from_top migrated to the Card IR — this _HAND_FLOOR producer
    # (and the SWEEP_DETECTORS row) are deleted. The lane fires from the IR structural
    # arm (a STATIC cast_from_zone+from:library Effect over phase's
    # TopOfLibraryCastPermission mode) + the per-clause _PLAY_FROM_TOP_MIRROR /
    # _PLAY_FROM_TOP_FLOOR_MIRROR (the EXACT deleted SWEEP + this FLOOR regex). The
    # deleted regex's voltron silence is restored by _PLAY_FROM_TOP_PLAN_MIRROR below
    # (its high-confidence producer fed has_other_plan). The serve survives via the
    # pinned PLAY_FROM_TOP_REGEX constant in signal_specs.py. CR 116 / 601.3b.
    # ADR-0027: lands_matter migrated to the Card IR — served from the
    # amount.subject=Land count operand (the structured scalers) + a kept word mirror
    # (_IR_KEPT_DETECTORS) for the "P/T equal to the number of lands you control" and
    # "for each land you control" forms phase emits as characteristic_pt/pump_target
    # but DROPS the count operand. Moved floor->kept (floor-mirror-dep -> 0); this
    # _HAND_FLOOR producer is deleted.
    # ADR-0027: direct_damage migrated to the Card IR — this second _HAND_FLOOR producer
    # (any-target burn / {T}-ping / damage doubler / "source you control deals damage"
    # payoff) is deleted along with the player-burn producer above. It survives byte-
    # identically inside the _DIRECT_DAMAGE_MIRROR (_signals_ir), whose tail-arms ARE
    # these exact branches; the doublers + damage-matters payoffs phase emits as
    # replacement / trigger effects (not a `damage` Effect), so they ride the mirror
    # while the structural scope arm handles the player-reaching `damage` Effects. See
    # the migration note on the deleted player-burn producer above.
    # ADR-0027 β: mana_amplifier (the DOUBLER arm) migrated to the Card IR — this
    # _HAND_FLOOR producer is deleted. The lane fires from the IR structural arm (the
    # supplement-split `mana_amplifier` category + a _MANA_AMPLIFY_RAW discriminator
    # over the triggered `ramp` / `double` doublers, read additively) + the per-card
    # dork-support _MANA_DORK_SUPPORT_MIRROR, all in _signals_ir. The deleted regex's
    # voltron silence is restored by _MANA_AMPLIFIER_PLAN_MIRROR below (its high-
    # confidence producer fed has_other_plan — a mana-doubler engine IS a plan). The
    # serve survives via the standalone _spec in signal_specs.py (never read this
    # regex). CR 106.4 / 605.
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    # ADR-0027 (voltron migration — the LAST key): the Equipment/Aura PAYOFF producer
    # is DELETED from the regex path. Its regex lives on as VOLTRON_PAYOFF_REGEX above;
    # the IR path (extract_signals_ir) runs the SAME regex per-clause UNIONed with the
    # structural _detect_voltron_payoff_ir. extract_signals no longer emits voltron.
    # ADR-0027: vehicles_matter migrated to the Card IR. This broad _HAND_FLOOR
    # producer (the "Vehicles you control" anthem / crew payoff / Vehicle GRANTER form)
    # is deleted; its EXACT regex is pinned as VEHICLES_MATTER_REGEX in _sweep_detectors
    # and rides the byte-identical VEHICLES_MATTER_MIRROR kept WORD MIRROR in
    # _signals_ir._IR_KEPT_DETECTORS (scope 'you', flat over the reminder-stripped
    # kept_oracle == this floor Detector's per-clause scan, both==41). The SEPARATE
    # typed-graveyard-recursion Vehicle arm (_detect_typed_gy_recursion's "vehicle" row
    # — Greasefang: "return target Vehicle card from your graveyard to the battlefield",
    # which this floor regex never anchored) is re-supplied PER-CLAUSE in the IR path
    # too. After both, IR == the deleted regex producers EXACTLY (both==42, ir_only==0,
    # regex_only==0). FLOOR→KEPT: removed from _IR_FLOOR_LANES (floor-mirror-dep -> 0).
    # The deleted producer fired HIGH-confidence scope 'you' and fed has_other_plan, and
    # the IR re-supply is the SAME breadth (residual 0), so vehicles_matter is added to
    # signals._VOLTRON_SILENCING_PLAN_KEYS (byte-identical re-silence). The hand-written
    # serve spec in signal_specs.py is independent of this regex and survives. CR 301.7
    # (Vehicle artifact subtype) / 702.122 (Crew) / 305.7.
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
    # ADR-0027: superfriends_matters migrated to the Card IR — served from the EXISTING
    # structural arm (a Condition gated on a Planeswalker subject you control: "as long
    # as you control a <Name> planeswalker, …", +26 commander-legal ir_only the regex
    # missed) PLUS a byte-identical SUPERFRIENDS_MATTERS_REGEX _IR_KEPT_DETECTORS word
    # mirror for the "planeswalkers you control" anthem / "loyalty counter" payoffs /
    # "activate a loyalty ability" engines / "abilities of a planeswalker" copiers phase
    # leaves textual. This _HAND_FLOOR producer is deleted and superfriends_matters is
    # removed from _IR_FLOOR_LANES; the serve spec stays hand-registered in
    # signal_specs.py. The BROADER IR re-supply means the has_other_plan voltron silence
    # is restored by the byte-identical _SUPERFRIENDS_MATTERS_PLAN_MIRROR below (NOT
    # _VOLTRON_SILENCING_PLAN_KEYS, which would over-silence the 26 structural bodies).
    # ADR-0027: historic_matters migrated to the Card IR — served from the "Historic"
    # subject-Filter predicate + a "\bhistoric\b" _IR_KEPT_DETECTORS word mirror for the
    # cost-reduction / "play a historic" / type-group refs phase leaves textual
    # (artifacts, legendaries, and Sagas are historic). This _HAND_FLOOR producer is
    # deleted; the serve spec stays hand-registered in signal_specs.py.
    # ADR-0027: legends_matter migrated to the Card IR (see the merged
    # _IR_KEPT_DETECTORS mirror). This second _HAND_FLOOR producer is deleted too.
    # ADR-0027: big_hand_matters migrated to the Card IR — served from the v23
    # `no_max_handsize` Effect structural arm + the byte-identical
    # _BIG_HAND_MATTERS_MIRROR _IR_KEPT_DETECTORS word mirror for the "X = cards in your
    # hand" P/T-scaling payoffs (Maro, Psychosis Crawler — a `characteristic_pt` Effect
    # with NO in:hand zone) and the "N or more cards in hand" conditions. BOTH its
    # oracle-regex producers (this _HAND_FLOOR row + the SWEEP row) are deleted; the
    # _BIG_HAND_MATTERS_PLAN_MIRROR re-supplies the has_other_plan voltron silence (the
    # producers fired HIGH-confidence scope 'you'). The hand-written serve spec
    # (signal_specs.py) is independent of these regexes and survives. CR 402.2.
    # ADR-0027: party_matters migrated to the Card IR — served from the
    # amount.op=="party" count operand + a _IR_KEPT_DETECTORS word mirror for the
    # "full party" CONDITION + "creatures in your party" non-count refs. This
    # _HAND_FLOOR producer is deleted; the serve spec stays hand-registered.
    # ADR-0027: exile_matters migrated to the Card IR — the EXILE-ZONE-AS-RESOURCE
    # cares-about lane (cards STANDING in exile — "cards you own in exile" / "card in
    # exile with <kind> counter" payoffs + "exiled with <this>" persistent-pile
    # scalers + the "for each card exiled this way" one-shot scalers the prefix branch
    # also reaches). phase carries NO usable structural form (it scatters the
    # exile-zone reference across a `zones=('in:exile',)` count operand, a
    # `Condition(zones= ('exile',))`, and a `characteristic_pt` Effect whose count
    # operand drops the zone), so the lane fires from a BYTE-IDENTICAL kept WORD
    # MIRROR — EXILE_MATTERS_REGEX (pinned in _sweep_detectors) run FLAT over the
    # reminder-stripped kept_oracle in extract_signals_ir's _IR_KEPT_DETECTORS loop
    # (commander-legal: flat==per- clause==63, 0 gain/loss — neither branch carries a
    # `[^.]*` cross-clause span). This was a regex FLOOR lane (in _IR_FLOOR_LANES);
    # FLOOR→KEPT, floor-mirror-dep -> 0. Distinct from exile_removal (EXILE a
    # permanent as REMOVAL), cast_from_exile (CAST/PLAY a card FROM exile), and
    # opponent_exile_matters (GRAVEYARD HATE). The deleted producer fired HIGH (scope
    # 'you') and fed has_other_plan, so the hybrid re-silences the spurious
    # commander-damage voltron tell via _VOLTRON_SILENCING_PLAN_KEYS (signals.py) —
    # byte-identical re-supply, no over- silence. The serve survives via the
    # standalone _spec in signal_specs.py (never reads this regex). exile_matters was
    # NEVER a SWEEP key, so no SWEEP row / floor count moves (len stays 32). CR 406.
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
    # ADR-0027: modified_matters migrated to the Card IR — this SECOND _HAND_FLOOR
    # producer (the direct `\bmodified\b` word: the Kamigawa Neon Dynasty "modified"
    # archetype, CR 700.9) is deleted. The IR recovers it (and the indirect "power
    # greater than its base power" anchor deleted above) via the UNION kept WORD MIRROR
    # in _signals_ir._IR_KEPT_DETECTORS (byte-identical, residual 0). The voltron
    # silence is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS. See the FIRST producer.
    # ADR-0027: has_mutate migrated to the Card IR — the Scryfall `mutate`
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
    # ADR-0027: clue_matters migrated to the Card IR — STRUCTURAL ARM (the artifact-
    # token-subtype maker / sac payoff / token_subtype_ref marker shared with food/
    # treasure/blood) UNIONed with a byte-identical kept WORD MIRROR
    # (_CLUE_MATTERS_MIRROR in _signals_ir._IR_KEPT_DETECTORS, the EXACT deleted
    # `\bclue\b|\binvestigate\b` pinned as CLUE_MATTERS_REGEX). The mirror is REQUIRED:
    # the structural arm fires only 52 of the 163 commander-legal lane cards (phase tags
    # the Investigate keyword -> artifacts_matter but DROPS the Clue subtype off the
    # make_token subject — Deduce, Bygone Bishop, Thraben Inspector parse with
    # subject=None), so the 112 pure-investigate / Clue-payoff cards survive only
    # textually (regex_only == 0 after the mirror). The structural arm is BROADER (+1
    # ir_only: Tangletrove Kelp, whose "other Clues you control" the singular-only
    # `\bclue\b` missed — a genuine recall gain), so voltron is re-silenced by the byte-
    # identical _CLUE_MATTERS_PLAN_MIRROR (NOT _VOLTRON_SILENCING_PLAN_KEYS, which would
    # over-silence Tangletrove Kelp). Removed from _IR_FLOOR_LANES. This _HAND_FLOOR
    # producer is deleted; the hand-written serve spec survives. CR 701.16 / 111.10f.
    # ADR-0027: blood_matters migrated to the Card IR — detected structurally from a
    # Blood-subtype maker (make_token subject), a Blood SACRIFICE PAYOFF (a sacrifice
    # Effect/Trigger whose subject Filter carries the Blood subtype — Wedding
    # Security, Blood Hypnotist), and the choose-list / granted-ability maker
    # recovery (Transmutation Font, Ceremonial Knife — project._narrow_token_subtype_
    # makers). It is removed from _IR_FLOOR_LANES (no floor mirror; floor-mirror-
    # dependency == 0). This _HAND_FLOOR producer is deleted; the hand-written serve
    # spec (signal_specs.py) survives. (clue/food/treasure all now migrated too.)
    # ADR-0027: daynight_matters migrated to the Card IR — detected from TWO
    # structural arms (NO mirror needed; CR 726 Day/Night): the daybound/nightbound
    # Scryfall KEYWORD via signals._IR_KEYWORD_MAP (the 35 transforming creatures —
    # Tovolar, the werewolf cycles, Arlinn) plus the `day_night` EFFECT-category doer
    # via _DOER_EFFECT_KEYS (the 12 keyword-LESS "it becomes day/night" / "as long as
    # it's day/night" transition payoffs — Brimstone Vandal, The Celestus, Vadrik — and
    # Tovolar's both-arm upkeep flip). phase v0.1.19 structures the transition cleanly,
    # so the two arms reproduce
    # this deleted _HAND_FLOOR producer BYTE-IDENTICALLY (commander-legal: both==47,
    # ir_only==0, regex_only==0). This producer (formerly an _IR_FLOOR_LANE; moved
    # floor->kept, floor-mirror-dep -> 0) is deleted; the hand-written serve spec
    # (signal_specs.py) survives. The producer fired high-confidence scope 'you' and fed
    # has_other_plan, so daynight_matters is added to _VOLTRON_SILENCING_PLAN_KEYS (the
    # IR re-supply is byte-identical, IR == regex == 47, so the silencing-keys path
    # re-silences exactly without over-silence).
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
    # counter sources).
    # ADR-0027: counter_doubling migrated to the Card IR — a structural
    # `cat == "counter_doubling"` replacement-effect arm (recovering the 6 canonical
    # replacement doublers this regex MISSED — Doubling Season, Branching Evolution,
    # Primal Vigor, Corpsejack Menace, The Earth Crystal, Struggle for Project Purity)
    # + a byte-identical COUNTER_DOUBLING_REGEX kept word mirror in _signals_ir (the 46
    # one-shot/activated/triggered "double the number of … counters" doublers phase
    # v0.1.19 mangles to a generic `double` effect or a plain
    # `place_counter`/`counter_distribute`). This _HAND_FLOOR producer (the UNION'd into
    # COUNTER_DOUBLING_REGEX) is deleted; the hand-written serve spec (signal_specs.py)
    # survives. The producer fired HIGH-confidence scope 'you' and fed has_other_plan,
    # so a byte-identical _COUNTER_DOUBLING_PLAN_MIRROR (below) re-supplies the
    # commander-damage voltron silence (the IR re-supply is BROADER — +6 — so NOT
    # _VOLTRON_SILENCING_PLAN_KEYS). CR 122 / 614 / 903.10a.
    # ADR-0027: second_spell_matters migrated to the Card IR — detected from a
    # byte-identical _SECOND_SPELL_MIRROR in signals._IR_KEPT_DETECTORS (the "second
    # spell each turn" / Dualcast-discount / Erayo-count payoff phase
    # under-structures: a bare `cast_spell` trigger drops the "second spell"
    # qualifier, identical to plain magecraft — so no structural arm can tell the
    # narrow second-spell payoff from the broad spellcast_matters lane). This
    # _HAND_FLOOR producer (formerly an _IR_FLOOR_LANE; moved floor->kept,
    # floor-mirror-dep -> 0) is deleted; the hand-written serve spec
    # (signal_specs.py) survives. The producer fired high-confidence scope 'you' and
    # fed has_other_plan, so second_spell_matters is added to
    # _VOLTRON_SILENCING_PLAN_KEYS (the IR re-supply is byte-identical, IR == regex
    # == 92, so the silencing-keys path re-silences exactly without over-silence).
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
    # ADR-0027 β: opponent_search_matters migrated to the Card IR — an opp-scoped
    # `lib_search` trigger (project._trigger_event re-types phase's SearchedLibrary /
    # Shuffled / scry-surveil-search PlayerPerformedAction modes off the generic
    # `other`; the scope=='opp' gate in extract_signals_ir is the discriminator vs the
    # YOU-scoped scry/surveil payoffs). This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec (signal_specs.py) is independent of this regex and
    # survives. NO voltron _PLAN_MIRROR is needed: although the producer fired
    # high-confidence (scope 'opponents') and fed has_other_plan, the FILE-SWAP shows
    # voltron delta 0 even with the lane absent — the two power<2 punishers (Wan Shi
    # Tong, Cosi's Trickster) never reach the voltron gate (power>=2 / voltron-keyword),
    # and every power>=2 punisher (River Song, Ob Nixilis, Archivist of Oghma) carries
    # ANOTHER high-confidence plan (direct_damage / death_matters / lifegain_matters)
    # that keeps has_other_plan True. So no body leaks the commander-damage tell.
    # ── Mechanics recovered from the "rejected" families (still-zero commanders) ──
    # ADR-0027 β: token_copy_makers migrated to the Card IR via a kept-mirror — the
    # lane fires from _TOKEN_COPY_MATTERS_MIRROR in _signals_ir (the EXACT deleted
    # regex, pinned as TOKEN_COPY_MATTERS_REGEX, over the reminder-stripped oracle),
    # NOT a structural CopyTokenOf/Populate arm (phase structures those but the 80-card
    # struct-only delta is 100% reminder-text SELF-copies — Embalm/Eternalize/Offspring/
    # Double-team — the regex excludes). This _HAND_FLOOR producer fired HIGH-confidence
    # (scope 'you') and fed has_other_plan, so a byte-identical
    # _TOKEN_COPY_MATTERS_PLAN_MIRROR below re-supplies the commander-damage voltron
    # silence. The serve spec stays hand-registered in signal_specs.py reusing
    # TOKEN_COPY_MATTERS_REGEX. CR 702.95 / 707.
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
    # ADR-0027: connive_makers migrated to the Card IR — phase's `connive` effect
    # category (self-conniving cards, _DOER_EFFECT_KEYS) + the `_CONNIVE_REF`
    # applied/granted marker, plus the Scryfall `connive` keyword (_IR_KEYWORD_MAP)
    # which lifts the keyword-less GRANTER phase swallows into an Enchant parse
    # (Security Bypass). This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: spell_copy_makers migrated to the Card IR — phase's `spell_copy`
    # effect (CopySpell + CastCopyOfCard) + the storm/replicate/conspire/casualty
    # Scryfall keywords (the HAVERS, _IR_KEYWORD_MAP) + a `_COPY_SPELL_REF` marker for
    # the granted/quoted/conditional copy phase folds into a modal / coin-flip / storm-
    # reminder carrier and the keyword-less GRANTERS ("…spell you cast has replicate/
    # casualty/storm/demonstrate"). The IR EXCLUDES the deleted regex's `\bstorm\b`
    # card-NAME over-fire (Comet Storm, Arrow Storm — burn, not the keyword). Both
    # regex producers (this _HAND_FLOOR + the SWEEP row) are deleted; the serve spec
    # stays hand-registered.
    # ── Effect-axis detectors: every ability is a direction to build around ──────
    # ADR-0027: ramp main mana-production arm migrated to the Card IR. The
    # deleted regex ("{T}: add {" / "add N mana" / "add {WUBRGC}") is now the
    # byte-identical _RAMP_MATTERS_REGEX kept mirror in _signals_ir, paired with a
    # structural `ramp`-category arm gated `not card_is_land` (the recall-GAINING half:
    # +96 nonland ramp doers the brittle anchor missed). See the dork-support note above
    # and _migrated_keys.py for the full residual.
    # ADR-0027: removal migrated to the Card IR — phase's `destroy` / `damage`
    # effect categories with a single-target permanent SUBJECT (CR 115.1), plus the
    # quoted-grant-ability recursion (an Aura/Equipment granting "{T}: Destroy/deal
    # damage to target …" — Manriki-Gusari, Lavamancer's Skill) and the
    # removal-target-subject recovery (Combo Attack, Broken Visage). The mass form
    # ("destroy/deal damage to EACH/ALL …" — DamageAll/DestroyAll, counter_kind=="all")
    # is a BOARD WIPE (CR 115.10), correctly EXCLUDED here and served by mass_removal;
    # the regex over-fired by folding board wipes / land destruction into removal. NOT
    # in _IR_FLOOR_LANES (floor-mirror-dep == 0); this _HAND_FLOOR producer is deleted
    # and the SWEEP_DETECTORS removal row with it; serve stays hand-registered.
    # ADR-0027 exile_removal (SIDECAR v30) migrated to the Card IR — phase's `exile`
    # effect category with a single-target permanent SUBJECT (CR 406.1 one-way exile /
    # 115.1 target), the v30 supplement RETAINING cat=exile + a permanent subject on the
    # rider-swallow / dropped-subject cases (Soul Partition, "Exile", Unexplained
    # Absence). This _HAND_FLOOR producer is deleted (its `exile target … nonland` arm
    # over-fired on GY-hate / recursion — "exile target nonland CARD from a graveyard",
    # Moratorium Stone / Secret Salvage / Shiko — which is NOT battlefield removal; the
    # structural arm excludes a graveyard zone, correctly dropping them). The SWEEP
    # row's broader regex survives as EXILE_REMOVAL_REGEX (the byte-identical kept
    # mirror); the serve spec stays hand-registered. CR 406.1 / 115.1.
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
    # ADR-0027 reveal/dig-v2: tutor migrated to the Card IR via a BYTE-IDENTICAL
    # kept mirror (_TUTOR_MATTERS_MIRROR in _signals_ir._IR_KEPT_DETECTORS == the
    # deleted
    # TUTOR_MATTERS_REGEX, over reminder-stripped kept_oracle). This _HAND_FLOOR
    # producer
    # is DELETED; the pattern survives as TUTOR_MATTERS_REGEX (below) for the mirror +
    # the
    # has_other_plan voltron silence reuse. The producer fired HIGH-confidence scope
    # 'you' and fed has_other_plan (a tutor engine is a card-advantage plan), so
    # tutor joins _VOLTRON_SILENCING_PLAN_KEYS (the IR re-supply is
    # byte-identical
    # — same 773 cards — so the strict-subset facade is valid). CR 701.23 / 401.
    # ADR-0027 β: untap_engine migrated to the Card IR — this _HAND_FLOOR producer (the
    # "untap target/all/each/two/up to" engine anchor) and the creatures-are-lands
    # producer below are deleted. The lane fires from a refined structural arm in
    # extract_signals_ir (mass untap counter_kind=='all' + raw "untap target/.." + a
    # multi/X-target untap of a permanent type you can control, all gated against the
    # opponent-untap / provoke / single-attach over-fires) PLUS a NARROWED
    # _IR_KEPT_DETECTORS-style mirror for the ~11 engines phase routes into a choose /
    # target_only / cost / type_set carrier. The two producers fired HIGH-confidence
    # (forced scope 'you') and counted toward has_other_plan, so an
    # _UNTAP_ENGINE_PLAN_MIRROR (the byte-identical OR of both deleted regexes over the
    # reminder-stripped joined-face `text`) re-supplies that voltron silence — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is BROADER (+12 ir_only) and would
    # over-silence those recall-gain bodies. The serve spec (signal_specs.py, a
    # standalone _spec on untap effects) survives. CR 701.16 / 903.10a. ADR-0027 β:
    # gain_control migrated to the Card IR — this _DETECTORS producer (the bare `gain
    # control of` literal, pinned now as GAIN_CONTROL_REGEX in _sweep_detectors) is
    # deleted. The lane fires from a GATED structural arm in extract_signals_ir
    # (cat=='gain_control' excl donate / Owned-return / give-away — a +85 recall-gaining
    # superset that catches the "you control enchanted creature" / "control target
    # player" / "exchange control" theft the bare regex MISSED and drops the
    # you-own-reset / can't-gain-protection / own-recovery over-fires it caught) PLUS a
    # NARROWED _GAIN_CONTROL_MIRROR (the 9 genuine theft phase emits no category for,
    # vetoed per-clause). The deleted producer fired HIGH-confidence (scope 'you') and
    # counted toward has_other_plan, so a _GAIN_CONTROL_PLAN_MIRROR (below) re- supplies
    # the voltron silence — NOT _VOLTRON_SILENCING_PLAN_KEYS, since the IR arm is
    # BROADER (+85) and the silencing-keys path would over-silence those recall-gain
    # bodies. The LOW-conf `dont_own` cross-open below + the theft_matters sibling are
    # reconciled in signals.py against the MERGED key set. The serve spec (signal_specs)
    # survives. CR 800.4a / 720.1 / 903.10a. ADR-0027: opponent_discard migrated to the
    # Card IR — this _HAND_FLOOR producer (the "(each|target|that) player/opponent
    # discards" hand-attack forcer OR the "opponent discarded a card this turn" /
    # "whenever an opponent discards" payoff) is DELETED. It fires from a structural arm
    # (a `discard` EFFECT scope == "opp", +7 genuine recall) PLUS a byte-identical
    # _OPPONENT_DISCARD_MIRROR kept-mirror in signals._IR_KEPT_DETECTORS (the EXACT
    # deleted regex) for the directed/symmetric forcers phase scopes 'any'/'you' and the
    # "whenever an opponent discards" payoffs phase emits a `discarded` TRIGGER for. The
    # serve spec stays hand-registered in signal_specs.py; the deleted producer fed
    # has_other_plan (HIGH-confidence, scope 'opponents'), so its voltron silence is
    # restored by _OPPONENT_DISCARD_PLAN_MIRROR below. DISJOINT from discard_matters
    # (the SELF-discard `discarded`-TRIGGER scope != 'opp' lane). CR 701.8a / 903.10a.
    # ADR-0027 β: damage_to_opp_matters migrated to the Card IR. This HAND_FLOOR
    # producer (a "whenever ~ deals (noncombat) damage to a PLAYER / opponent"
    # connect-payoff — ANY damage, not the literal "combat damage" the combat_* keys
    # require) is deleted. The lane now fires from a STRUCTURAL IR arm reading project's
    # DamageToPlayer recipient marker (SIDECAR v13 — the player recipient phase keeps on
    # the DamageDone trigger's valid_target but the projected Trigger drops) PLUS a
    # byte-identical kept mirror (_signals_ir) for the granted-ability / ETB-burst /
    # "another player" textual tail phase can't structure as a DamageDone trigger. The
    # IR path is BROADER (+recall: "deals 6 or more damage to an opponent", plural "deal
    # damage to a player", "deals damage to another player" the word-order regex
    # missed), so a byte-identical _DAMAGE_TO_OPP_MATTERS_PLAN_MIRROR below re-supplies
    # the deleted high-confidence producer's voltron silence — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS (that would over-silence the ir_only recall-gain
    # bodies). The exact regex is pinned as DAMAGE_TO_OPP_MATTERS_REGEX
    # (_sweep_detectors), shared by the mirror, the plan-mirror, and the hand-registered
    # serve. Distinct from combat_damage_to_opp (already migrated 42f6d81 — the literal
    # "combat damage to a player" recipient). CR 119.3. ADR-0027: permanent_etb migrated
    # to the Card IR — an `etb` Trigger whose subject Filter carries the 'Permanent'
    # card_type and controller=='you' (Amareth, the canonical card). The structural IR
    # is BROADER-and-correct: it catches the "a/another permanent you control enters"
    # variants the narrow word-order regex missed (Cloudstone Curio, Kodama, Yoshimaru,
    # Builder's Talent). NOT in _IR_FLOOR_LANES; this _HAND_FLOOR producer is deleted;
    # the serve spec stays. ADR-0027: evasion_self migrated to the Card IR. Evasion is a
    # blocking RESTRICTION (CR 509.1b); landwalk (CR 702.14) is conditional
    # unblockable-by-that-land-type evasion, and the keyword-only evasion words
    # (horsemanship 702.31, menace 702.111, fear 702.36, intimidate 702.13, skulk
    # 702.118) carry their "can't be blocked …" only in reminder text (stripped here),
    # so the bare keyword survived (Guan Yu's horsemanship). phase v0.1.19 structures
    # "This creature can't be blocked" only as a GENERIC `restriction` Effect (Slither
    # Blade — shared with stax/"can't block"/tax, too broad to key the lane off), and a
    # true mass CantBeBlockedBy grant becomes a `grant_keyword`(counter_kind
    # "unblockable") — neither is a clean SELF-evasion arm. So the lane rides a
    # BYTE-IDENTICAL kept WORD MIRROR of this EXACT deleted producer
    # (_EVASION_SELF_REGEX, pinned below) run FLAT over the reminder-stripped
    # kept_oracle in _signals_ir._IR_KEPT_DETECTORS — no `[^.]*` arm, so flat ==
    # per-clause. The IR re-supply is BROADER (+36): _IR_KEYWORD_MAP['shadow'] (CR
    # 702.28) credits the Shadow tribes (Dauthi/Soltari/Thalakos) via the precise
    # Scryfall keyword[] array, which the regex deliberately EXCLUDED (shadow collides
    # with card-name self-refs: "Whenever Shadow the Hedgehog…"). Shadow is genuine hard
    # evasion — recall, not over-fire. Commander-legal, floor-disabled, by oracle_id:
    # both==1426, ir_only==36 (all genuine Shadow keyword carriers), regex_only==0.
    # Because the deleted producer fired HIGH-confidence scope 'you' and fed
    # has_other_plan, and the IR re-supply is BROADER, a byte-identical
    # _EVASION_SELF_PLAN_MIRROR (the EXACT deleted regex) restores the voltron silence —
    # NOT _VOLTRON_SILENCING_PLAN_KEYS, which would over-silence the 36 Shadow bodies.
    # The hand-written serve spec (signal_specs.py) survives. CR 509.1b / 702.14 /
    # 702.28. ADR-0027 clone copied-type subject (SIDECAR v30): clone_makers migrated
    # to the Card IR. The supplement now populates the copied-type subject
    # (_copied_type_from_ text on the _CLONE_STATIC / _BECOMES re-tag), so a
    # cat=='clone' STRUCTURAL arm in extract_signals_ir fires clone_makers for the
    # broad "becomes a copy of target creature" family (triggered/activated/sorcery
    # clones — Cytoshape, Oko, Lazav, Sunfrill Imitator's Dinosaur) the narrow ETB-only
    # patterns missed, UNION a byte- identical _CLONE_MATTERS_MIRROR (the COMBINED
    # deleted regex — this _DETECTORS entry plus the SWEEP widen, pinned as
    # CLONE_MATTERS_REGEX) over the reminder-stripped kept_oracle for the 54 cards phase
    # under-structures (Spark Double / Stunt Double / Mockingbird — no clone effect) or
    # that copy a non-creature (Copy Artifact — the regex fired clone_makers regardless
    # of copied type). A token-copy clone ("create a token that's a copy" — Mirror
    # Match) is vetoed in the structural arm (the separate token_copy_makers lane). The
    # two membership cross-opens (the legendary recurring- value engine + the high-CMC
    # ETB/dies clone-TARGET tells) are reproduced in extract_signals_ir's
    # include_membership block (LOW conf, byte-identical). This _DETECTORS entry is
    # deleted; the deleted producer fired HIGH-confidence scope 'you' and fed
    # has_other_plan, so a byte-identical _CLONE_MATTERS_PLAN_MIRROR (below) — NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — restores the voltron silence (the IR re-supply is
    # BROADER: +1 Metamorphic Alteration the regex's "card"/"becomes" arms missed). CR
    # 707.1 / 707.2.
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR. This _DETECTORS
    # producer ("put … creature card … onto the battlefield" / "put … onto the
    # battlefield from your hand/library") is DELETED — it OVER-fired on graveyard
    # reanimation ("put target creature card from a graveyard onto the battlefield" —
    # Reanimate, Beacon of Unrest: the source zone the structural arm routes OUT) and
    # MISSED the reveal-until-creature Polymorph family the IR arm recovers. The lane
    # now
    # fires from the STRUCTURAL cat=='cheat_play'+to:battlefield+non-gy-source arm
    # (reading the project._recover_cheat_into_play_source marker, SIDECAR v37) UNION
    # the
    # narrow _CHEAT_INTO_PLAY_RESIDUE_RE mirror in _signals_ir. CR 110.2a / 400.7.
    # ADR-0027 (t2b2-A): bounce_tempo migrated to the Card IR — a first-class `bounce`
    # Effect with no graveyard zone tag and a subject not controlled by you (excludes
    # GY-recursion and self-bounce blink). This _HAND_FLOOR producer is deleted; the
    # hand-written serve spec (signal_specs.py, "Bounce / tempo") is independent of this
    # regex and survives.
    # ADR-0027: cascade_matters migrated to the Card IR — the Scryfall `cascade`
    # keyword (_IR_KEYWORD_MAP, the intrinsic cascaders) + a `_CASCADE_GRANT` marker for
    # the keyword-less granters/references ("spells you cast have cascade", "as you
    # cascade", "spell with cascade"). Removed from _IR_FLOOR_LANES; serve hand-spec'd.
    # ADR-0027: regenerate_makers migrated to the Card IR — phase's `regenerate` effect
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
    # ADR-0027: discover_makers migrated to the Card IR — served structurally from
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
    # ADR-0027: has_undying_persist migrated to the Card IR — the Scryfall
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
    # ADR-0027: the any-counter HAVE form of plus_one_matters ("permanents/creatures
    # you control with a counter on it" — Xolatoyac, Hidden Hideout, Michelangelo —
    # and "for each <permanent/creature> you control with a counter") migrated to the
    # Card IR: the counters_have_ref marker (project._narrow_counter_refs /
    # _counter_face_marker, "with a counter(s) on it/them" + "+1/+1 counter on
    # creatures you control" anchors) and the count-form payoff (amount.subject with
    # the Counters predicate). This _HAND_FLOOR producer is deleted; the serve spec
    # stays hand-registered.
    # ADR-0027 β: the untap_engine creatures-are-lands producer (Ashaya — "nontoken
    # creatures you control are Forest lands", whose creature-lands untap for mana via a
    # Seedborn/Quirion Ranger engine) is deleted alongside the engine-anchor producer
    # above. It survives byte-identically as _UNTAP_ENGINE_MIRROR_LANDS in the IR kept
    # mirror and in the _UNTAP_ENGINE_PLAN_MIRROR voltron re-supply below. CR 701.16.
    # ADR-0027: cycling_matters migrated to the Card IR — phase's `cycled` trigger +
    # a `cycling_payoff` marker (project._narrow_trigger_other_refs for the "cycle or
    # discard" payoff phase flattens to event='other', + _dropped_static_markers for
    # the cards phase truncates the trigger phrase off entirely). The `cycling_payoff`
    # category is DISTINCT from phase's native `cycling` landcycling doer, so the lane
    # stays payoff-only. This _HAND_FLOOR producer is deleted; the serve spec stays.
    # ADR-0027: kicked_spell_matters migrated to the Card IR — detected from a
    # byte-identical _KICKED_SPELL_MIRROR in signals._IR_KEPT_DETECTORS (the narrow
    # "whenever you cast a kicked spell" payoff / "if (that|it) (spell) was kicked"
    # condition, CR 702.33 Kicker). NOT the bare `\bkicked\b` keyword route — that
    # over-fires +171 on every "if kicked" card; the lane is the PAYOFF/CONDITION, not
    # Kicker presence. This _HAND_FLOOR producer (formerly an _IR_FLOOR_LANE; moved
    # floor->kept, floor-mirror-dep -> 0) is deleted; the hand-written serve spec
    # (signal_specs.py) survives. The producer fired high-confidence scope 'you' and fed
    # has_other_plan, so kicked_spell_matters is added to _VOLTRON_SILENCING_PLAN_KEYS
    # (the IR re-supply is byte-identical, IR == regex == 85, so the silencing-keys path
    # re-silences exactly without over-silence).
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
    # ADR-0027: the Casualty (CR 702.153) sacrifice_outlets regex is DELETED with the
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
    # greater" payoff (Colossal Majesty, Crater's Claws).
    # ADR-0027: power_matters migrated to the Card IR — served from the structural
    # PtComparison:Power:GE/GT predicate read off the board_count / trigger / Condition
    # / amount subject (_predicate_build_around_lanes + _condition_power_matters; the
    # v23 projection fills the operand) PLUS the byte-identical _POWER_MATTERS_MIRROR
    # (the exact deleted regex) over the reminder-stripped kept_oracle for the aggregate
    # "total/greatest power of creatures you control" tail phase folds into an empty-
    # predicate board_count. REMOVED from _IR_FLOOR_LANES; serve stays hand-registered
    # in signal_specs. The deleted producer fed has_other_plan (HIGH, scope 'you'), so
    # the byte-identical _POWER_MATTERS_PLAN_MIRROR (below) re-supplies the voltron
    # silence — the migrated IR is BROADER (+34), so _VOLTRON_SILENCING_PLAN_KEYS would
    # over-silence.
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
# Scryfall's authoritative `keywords` array, the low-false-positive path.
_PRESET_KEYWORD_SIGNALS = {
    # ADR-0027: the `mill` preset keyword moved to _IR_KEYWORD_MAP (the IR-only
    # keyword path) because mill_makers is migrated — keeping it here would let the
    # regex `extract_signals` path keep emitting a migrated key. The IR path reads the
    # same Scryfall `Mill` keyword array (byte-identical), and the has_other_plan
    # voltron silence is re-supplied by a `"mill" in card.keywords` gate term below
    # (the preset fired HIGH and fed has_other_plan — a mill engine is a real plan).
    # ADR-0027: the `goad` preset keyword moved to _IR_KEYWORD_MAP (the IR-only keyword
    # path) because goad_makers is migrated — keeping it here would let the regex
    # `extract_signals` path keep emitting a migrated key. This shared preset is read by
    # BOTH paths (extract_signals via _detect_keyword_presets AND extract_signals_ir at
    # line ~10318), so the IR path STILL needs the Scryfall `Goad` keyword array:
    # phase's `goad_all` effect + the _GOAD_STYLE_FORCE single-target political force
    # cover 57 of the 122 commander-legal goad cards structurally, but 65 fire SOLELY
    # from the keyword (a vanilla "Goad" body — a granter / cost-rider whose goad lives
    # in reminder text phase folds away). The IR keyword route (_IR_KEYWORD_MAP['goad'],
    # byte-identical Scryfall `Goad` array) re-supplies those exactly — verified the
    # hybrid goad set is unchanged (122) and voltron unchanged (2396) after the move.
    # The hand-written serve spec (signal_specs.py) is independent and survives.
    # CR 701.38.
    # ADR-0027: the `proliferate` preset keyword moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because proliferate_matters is migrated — keeping it
    # here would let the regex `extract_signals` path keep emitting a migrated
    # key. The IR path reads the same Scryfall keyword array.
    # ADR-0027: the `magecraft` preset keyword likewise moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because magecraft_matters is migrated — keeping it here
    # would let the regex `extract_signals` path keep emitting a migrated key. The IR
    # path reads the SAME Scryfall `Magecraft` keyword array (byte-identical), and the
    # has_other_plan voltron silence is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS
    # (verified inert — every magecraft creature already carries another high-confidence
    # plan, notably co-firing spellcast_matters, so 0 voltron tells leak). CR 207.2c.
    # ADR-0027: the `prowess` preset keyword likewise moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because spellcast_matters is migrated — keeping it here
    # would let the regex `extract_signals` path keep emitting a migrated key. The IR
    # path reads the SAME Scryfall `Prowess` keyword array (byte-identical), and the
    # has_other_plan voltron silence is re-supplied via _spellcast_has_plan (the
    # prowess-keyword arm). CR 702.108a.
    # Storm/Casualty/Replicate/etc. are spell-copy keywords.
    "spell-copy": ("spell_copy_makers", "you"),
}
# REGEX presets reused clause-scoped via the preset's own compiled patterns — these
# close documented pure-reuse gaps (blink/Brago) where the tested theme exists but the
# extractor never called it.
# ADR-0027: the `extra-combats` preset entry is DELETED — extra_combats migrated to
# the Card IR. phase carries an accurate STRUCTURAL form (the `extra_combat` effect
# category → extra_combats via _DOER_EFFECT_KEYS, 42 of 43 commander-legal cards, ZERO
# over-fire) and the ONE under-structured gap (Illusionist's Gambit — phase folds it
# into a lone `restriction` effect) rides the byte-identical EXTRA_COMBATS_REGEX word
# mirror in _IR_KEPT_DETECTORS (the EXACT deleted preset pattern, `additional combat
# phase`, run flat over the reminder-stripped kept_oracle — flat==per-clause; the
# structural arm union the mirror == 43 == this deleted producer EXACTLY). The
# `extra-combats` PRESET itself survives in theme_presets (deck-wizard / cube-wizard
# archetype detection still use it); only this _PRESET_REGEX_SIGNALS producer entry is
# removed. The deleted producer fed has_other_plan (HIGH, scope 'you', not
# generic/voltron-compat); the hybrid re-silences voltron via
# _VOLTRON_SILENCING_PLAN_KEYS — the IR re-supply IS this byte-identical union
# (IR==regex==43), so no over-silence and NO _EXTRA_COMBATS_PLAN_MIRROR.
# The hand-registered serve spec (signal_specs) is independent and survives. CR
# 505.1a / 903.10a.
_PRESET_REGEX_SIGNALS = {
    # ADR-0027 returns_to dimension (SIDECAR v34): the `blink` preset entry is DELETED —
    # blink_flicker migrated to the Card IR. phase folds a single-target "exile target
    # X, return it" into an exile half + a sibling return half; the v34 projection
    # (`Effect.returns_to`) stamps `returns_to="battlefield"` on the exile half iff the
    # SAME ability returns the object to the battlefield. The lane fires from the
    # STRUCTURAL `(cat in blink/exile) and returns_to=="battlefield"` arm in
    # extract_signals_ir (broader than the preset — it RECOVERS the genuine blinks phase
    # types `cat='exile'` because the exiled object isn't "you"-controlled: Flickerwisp,
    # Mistmeadow Witch, Roon, Eldrazi Displacer, +58 commander-legal ir_only, all with a
    # blink hook) UNION a BYTE-IDENTICAL kept mirror (BLINK_FLICKER_REGEX = the EXACT
    # deleted `blink` preset pattern + `_detect_blink_fulltext`, flat over the reminder-
    # stripped kept_oracle) that re-supplies the 41 regex_only DFC-flip / cross-sentence
    # / GY-recursion-with-return bodies the structural arm misses. It DROPS the
    # exile-as-resource over-fires the old preset never reached anyway (Chrome Mox /
    # Bottled Cloister / Helvault — exile with NO same-ability battlefield return). The
    # `blink`
    # PRESET itself survives in theme_presets (deck-wizard / cube-wizard archetype
    # detection); only this _PRESET_REGEX_SIGNALS producer entry is removed. The deleted
    # producer fed has_other_plan (HIGH, scope 'you', not generic/voltron-compat); the
    # voltron silence is re-supplied by the byte-identical `_blink_flicker_has_plan`
    # mirror OR'd into has_other_plan in signals.py (NOT _VOLTRON_SILENCING_PLAN_KEYS —
    # the IR structural re-supply is BROADER than the deleted regex, which would
    # over-silence the +58 ir_only recall-gain bodies). The hand-registered serve spec
    # (signal_specs) is independent and survives. CR 603.6e / 400.7.
    # ADR-0027: the `extra-turns` AND `extra-combats` presets are both DELETED — both
    # migrated to the Card IR (the STRUCTURAL `extra_turn` / `extra_combat` effect-
    # category arms in extract_signals_ir, scope 'you', HIGH, broader than the presets;
    # the under-structured tails ride the byte-identical EXTRA_TURNS_REGEX /
    # EXTRA_COMBATS_REGEX _IR_KEPT_DETECTORS mirrors). Keeping them here would let the
    # regex `extract_signals` path keep emitting a migrated key. Each fed has_other_plan
    # (HIGH, scope 'you', not generic/voltron-compat); extra_turns' voltron silence is
    # restored by the byte-identical _EXTRA_TURNS_PLAN_MIRROR below (NOT
    # _VOLTRON_SILENCING_PLAN_KEYS — its IR arm is broader, which would over-silence the
    # recall-gain bodies), and extra_combats' via _VOLTRON_SILENCING_PLAN_KEYS (its IR
    # re-supply is byte-identical). CR 500.7 / 505.1a / 903.10a.
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
# ADR-0027: _LAND_DESTRUCTION_RE deleted — the land_destruction creature-commander
# cross-open migrated to the Card IR. Its pattern is pinned as LAND_DESTRUCTION_REGEX
# in _sweep_detectors and reused byte-identically by the _LAND_DESTRUCTION_MIRROR arm
# in extract_signals_ir (creature + include_membership gated, LOW confidence). CR 305.6.
# A commander that reveals the top card of a library and CHEATS a permanent onto the
# battlefield (Vaevictis, Hans Eriksson, Thrasios) curates its top: it wants to stack a
# bomb there (graveyard-to-top). BOTH tells are required so a plain reanimation spell
# ("put ... onto the battlefield" with no reveal) isn't mistaken for a top-cheater.
# ADR-0027: the cheat_from_top producer migrated to the Card IR — these two regexes are
# KEPT (the producer's add() is deleted in extract_signals) and reused byte-identically
# by the _CHEAT_FROM_TOP_MIRROR arm in _signals_ir (the v24 from:top zone projection is
# too coarse to carry this lane's narrow scope; see _migrated_keys). CR 401 / 701.20a.
_CHEAT_TOP_REVEAL_RE = re.compile(r"reveals? the top card", re.IGNORECASE)
_CHEAT_TOP_ONTO_RE = re.compile(
    r"puts? (?:it|that card|them) onto the battlefield", re.IGNORECASE
)
# A commander that repeatedly DESTROYS creatures (an activated {T}/cost ability or a
# recurring trigger) is a reliable death-engine: every kill fires on-death payoffs
# (Blood Artist, Vicious Shadows). The repeatable frame is the precision gate -- a
# one-shot removal spell (Murder: "Destroy target creature.") never registers.
# ADR-0027: the kill_engine producer migrated to the Card IR (SIGNALS-ONLY — phase
# already structures ab.kind / ab.cost / Trigger.event, so the repeatable frame is
# READ, not projected). This regex is KEPT (the producer's add() is deleted in
# extract_signals) and reused byte-identically by the _REPEATABLE_KILL_MIRROR arm in
# _signals_ir for Evil Twin — the one card phase can't structure (its destroy lives
# inside a QUOTED granted ability ["{U}{B}, {T}: Destroy …"], folded into a `clone`
# Effect with no destroy ability of its own). CR 305.6 / 707.2.
_REPEATABLE_KILL_RE = re.compile(
    r"\{[^}]*\}[^.]*:[^.]*destroy target creature"
    r"|(?:whenever|at the beginning of)[^.]*destroy target creature",
    re.IGNORECASE,
)
# ADR-0027: the _BIG_MANA_RE producer migrated to the Card IR. The deleted regex
# (add 2+ symbols at once | add-for-each | "add an additional") survives
# byte-identically as the _BIG_MANA_REGEX kept mirror in _signals_ir (paired with the
# v23 structural `ramp`-amount arm). See the deleted producer below in extract_signals.


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
# Mentor/Training/Evolve/… put +1/+1 counters; Battle cry/Battalion/Melee reward
# attacking as a team; Exalted rewards attacking ALONE (suit up one); Extort drains each
# opponent (702.101a); Amass/Mobilize make tokens. The keyword is authoritative, so
# these are high confidence.
_DIRECT_KEYWORD_SIGNALS = {
    # ADR-0027: the `dash` keyword (CR 702.109a — cast for the dash cost, gains haste,
    # returns to hand at the next end step) moved to _IR_KEYWORD_MAP (the IR-only
    # keyword path) with the has_dash migration. Dash's "return to hand" lives in
    # stripped reminder text (Zurgo Bellstriker, Ragavan), so the Scryfall keyword array
    # is the only structured anchor; keeping it here would let the regex
    # `extract_signals` keep emitting a migrated key. has_dash was the SOLE
    # producer (no other regex emitter), so the IR re-supply is byte-identical
    # (commander-legal: both==22, ir_only==0, regex_only==0). Re-silenced via
    # _VOLTRON_SILENCING_PLAN_KEYS.
    # ADR-0027: the +1/+1-counter keyword block (mentor/training/modular/bolster/
    # evolve/outlast/renown/adapt — and dethrone/undying/graft/riot/bloodthirst/
    # fabricate/sunburst/tribute/unleash/ravenous/reinforce/scavenge below) removed
    # from the regex keyword path with the plus_one_matters migration — every one of
    # their keyword cards already fires plus_one_matters STRUCTURALLY from the IR (each
    # keyword projects a place_counter via phase's effect mapping), verified 0-miss
    # over the commander-legal corpus. The regex `extract_signals` must no longer emit
    # the migrated key.
    # ADR-0027: the combat-keyword block (battle cry / battalion / melee here, and boast
    # / exert / myriad / bushido / annihilator / flanking / frenzy below) moved to the
    # IR-only _IR_KEYWORD_MAP with the attack_matters migration — their attack condition
    # lives in stripped reminder text, so neither the byte-mirror nor the structural arm
    # fires for a vanilla-keyword body; the IR keyword route opens the migrated lane for
    # them (saddle/lifelink-style). The regex `extract_signals` must no longer emit it.
    # ADR-0027 (voltron migration — the LAST key): the `exalted` → voltron_matters row
    # is REMOVED from the regex keyword path. exalted opens voltron from the IR keyword
    # route (_IR_KEYWORD_MAP['exalted'] → exalted_lone_attacker + voltron_matters), so
    # the regex `extract_signals` must no longer emit it. CR 702.83 / 903.10a.
    # ADR-0027: extort / afflict / spectacle (→ lifeloss_matters) removed from the
    # regex keyword path with the lifeloss_matters migration — all their keyword cards
    # already fire lifeloss_matters STRUCTURALLY from the IR (extort's lose_life
    # effect, afflict's "player loses life", spectacle's "opponent lost life"), so the
    # regex `extract_signals` must no longer emit the migrated key.
    # ADR-0027: amass (CR 701.47) / mobilize / station (CR 702.184) ALL moved to
    # _IR_KEYWORD_MAP (the IR-only keyword path) with the tokens_matter +
    # proliferate_matters migrations — keeping any here would let the regex
    # `extract_signals` path keep emitting a now-migrated key. amass/mobilize →
    # tokens_matter (Army/Warrior token-making lives in stripped reminder text; amass
    # also fires from the structural amass effect-category arm in extract_signals_ir);
    # station (charge counters) → proliferate_matters (the proliferate avenue).
    # ADR-0027: the `saddle` keyword (CR 702.171) moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because saddle_matters is migrated — keeping it here
    # would let the regex `extract_signals` path keep emitting a migrated key.
    # ADR-0027: the `banding` keyword (CR 702.22) moved to _IR_KEYWORD_MAP (the
    # IR-only keyword path) because has_banding is migrated — keeping it here
    # would let the regex `extract_signals` path keep emitting a migrated key. The
    # IR keyword route reads the SAME Scryfall `Banding` keyword array (byte-
    # identical: commander-legal both==24, ir_only==0, regex_only==0 — every banding
    # card carries the keyword, 0 keyword-less). The has_other_plan voltron silence
    # is re-supplied via _VOLTRON_SILENCING_PLAN_KEYS (byte-identical re-supply, the
    # mill / magecraft / lifelink keyword-array precedent).
    # ADR-0027: boast (CR 702.135) / exert (702.107) / myriad (702.116) / bushido /
    # annihilator / flanking / frenzy → attack_matters MOVED to _IR_KEYWORD_MAP (each
    # carries its attack condition in stripped reminder text, so the keyword array is
    # the only structured anchor). Keeping them here would let the regex path keep
    # emitting the migrated key.
    # Archetype-defining keyword abilities (CR §702): the mechanic is reminder text
    # (stripped), so a commander WITH the keyword reads as that archetype via keyword.
    # ADR-0027: prowess (CR 702.108a — "whenever you cast a noncreature spell, +1/+1")
    # MOVED to _IR_KEYWORD_MAP with the spellcast_matters migration. The Scryfall
    # `Prowess` keyword array is the structured anchor (the keyword lives in stripped
    # reminder so no structural cast Effect fires for a vanilla body). Keeping it here
    # would let the regex `extract_signals` path emit a migrated key.
    # ADR-0027 Cluster D: the `rampage` keyword (CR 702.23 — "whenever this becomes
    # BLOCKED, +X/+X per extra blocker") moved to the IR-only path with the
    # blocked_matters migration. phase parses rampage's reminder trigger as a
    # `BecomesBlocked` mode (projected to event=='becomes_blocked'), so the structural
    # becomes_blocked arm (_PAYOFF_TRIGGER_KEYS in extract_signals_ir) opens
    # blocked_matters for every rampage face (verified 14/14 carry the mode). Keeping
    # this entry here would let the regex `extract_signals` path keep emitting a now-
    # migrated key. (The deleted producer fired HIGH scope 'you'; the IR re-supply is
    # the SAME scope/confidence, and its voltron silence rides _BLOCKED_MATTERS_PLAN_
    # MIRROR — the rampage card's "becomes blocked" trigger IS a real plan.)
    # ADR-0027 β: lifelink (→ lifegain_matters) MOVED to _IR_KEYWORD_MAP (the IR-only
    # keyword path) for the lifegain_matters migration — keeping it here would let the
    # regex `extract_signals` keep emitting a migrated key. A vanilla-lifelink creature
    # now opens lifegain_matters from the IR keyword route (saddle/spectacle-style).
    "exploit": ("sacrifice_outlets", "you"),  # enters → sacrifice a creature
    "devour": ("sacrifice_outlets", "you"),  # enters → sacrifice creatures for counters
    # afflict / spectacle (→ lifeloss_matters) removed for the ADR-0027 migration —
    # see the note at the top of this map; the IR covers their keyword cards. The
    # +1/+1-counter keyword block (dethrone/undying/graft/riot/bloodthirst/fabricate/
    # sunburst/tribute/unleash/ravenous/reinforce/scavenge) is likewise removed for
    # the plus_one_matters migration — the IR fires plus_one_matters on all of them
    # structurally (see the note at the top of this map).
    # Persist returns with a -1/-1 counter (CR 702.79a), so it wants the -1/-1 serve
    # set, not the +1/+1-centric plus_one_matters — it stays (minus_counters_matter is
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
    # ADR-0027: keyword_tribe is migrated to the Card IR. extract_signals no longer
    # calls this (the regex path must not emit the migrated key); it is now imported
    # by _signals_ir and run PER-CLAUSE over the reminder-stripped kept_oracle as a
    # byte-identical KEPT MIRROR. The mirror preserves the keyword subject (Flying,
    # Deathtouch, …) the per-subject serve spec interpolates — phase's WithKeyword
    # predicate covers ~70 of the 87 but a structural arm loses ~19 tail cards phase
    # folds keyword-less (tutors, P/T-scaling, granted-fly), so the byte-mirror (not
    # a structural arm) is the clean shape: commander-legal residual both==87,
    # ir_only==0, regex_only==0; flat-over-kept_oracle == per-clause (0 divergences).
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
# ADR-0027: a go-wide GATE reproduction for the migrated attack_matters key — the
# deleted producers' form (the _DETECTORS lambda over the reminder-stripped JOINED-face
# oracle: the "whenever"&"attack" substring-AND + the two pinned branches "attacking
# causes"/"attacked this turn"; PLUS the 10 combat keywords the _DIRECT_KEYWORD_SIGNALS
# rows read off the keyword array), so an aggro lord's own CLASS tribe (Soldier/Cleric)
# still opens on the pure-regex path now that the regex no longer emits attack_matters
# into ``keys_now``. In base the go-wide gate read attack_matters at ANY confidence (it
# reads ``keys_now``, not has_other_plan), so this is unconditioned by scope. Per-clause
# (the substring-AND must hold WITHIN one clause) and over joined faces (a DFC back-face
# attack payoff — Kefka, Tamiyo — must still open). The IR go_wide gate sees the real
# signal; this preserves parity for the regex path.
_ATTACK_MATTERS_GATE_RE = re.compile(ATTACK_MATTERS_REGEX, re.IGNORECASE)
_ATTACK_GO_WIDE_KEYWORDS = frozenset(
    {
        "battle cry",
        "battalion",
        "melee",
        "boast",
        "exert",
        "myriad",
        "bushido",
        "annihilator",
        "flanking",
        "frenzy",
    }
)


def _attack_go_wide(card: dict) -> bool:
    """The deleted attack_matters producers' form, for the class-tribe go-wide gate."""
    text = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")
    for clause in _clauses(text):
        cl = clause.lower()
        if ("whenever" in cl and "attack" in cl) or _ATTACK_MATTERS_GATE_RE.search(cl):
            return True
    return bool(
        {k.lower() for k in (card.get("keywords") or [])} & _ATTACK_GO_WIDE_KEYWORDS
    )


# ADR-0027: the HAS-OTHER-PLAN mirror for the migrated lure_makers key. Its deleted
# SWEEP producer fired HIGH-confidence scope 'you' and counted toward `has_other_plan`
# (lure_makers is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious
# commander-damage voltron tell on a lure body that is NOT a vanilla beater — a lure /
# must-be-blocked engine (Lure, Nemesis Mask, Bramblecrush-style) is the card's whole
# plan (CR 509.1c). The migrated IR re-supply is BROADER (+3 ir_only: Marble Priest,
# Talruum Piper, You Look Upon the Tarrasque — typed/restricted blockers the SWEEP arm-1
# adjacency missed), so re-supplying via _VOLTRON_SILENCING_PLAN_KEYS would OVER-silence
# those 3 bodies' voltron tells. This BYTE-IDENTICAL mirror (== LURE_MATTERS_REGEX)
# reproduces the OLD regex's exact silence set, so the file-swap shows voltron delta 0.
# It feeds ONLY the gate (emits no signal — the lane is served from the IR), matched
# against the reminder-STRIPPED `text` (the deleted producer was a SWEEP detector over
# reminder-stripped clauses; flat over `text` == per-clause: 69==69 on the commander-
# legal corpus). CR 509.1c / 903.10a.
_LURE_MATTERS_PLAN_MIRROR = re.compile(LURE_MATTERS_REGEX, re.IGNORECASE)
# ADR-0027: tokens_matter's voltron silence is re-supplied via
# _VOLTRON_SILENCING_PLAN_KEYS (signals.py), NOT a byte-identical PLAN mirror here. A
# pure oracle mirror would go BLIND on the 3 vanilla mobilize-KEYWORD bodies (Dragonback
# Lancer, Dalkovan Packbeasts, Nightblade Brigade): their tokens_matter plan rode the
# deleted regex KEYWORD map (now _IR_KEYWORD_MAP['mobilize']), whose token-making lives
# in stripped reminder text, so no oracle mirror over `text` can see it. Because the IR
# re-supply is byte-identical to the deleted regex firing (commander-legal: regex ==
# hybrid == 230, 0 broadening), _VOLTRON_SILENCING_PLAN_KEYS re-silences the spurious
# commander-damage tell for ALL 230 — oracle-payoff AND keyword-only — without
# over-silencing, matching the keyword-bearing plus_one_matters / suspend_matters /
# poison_matters precedent. CR 903.10a / 111.1.


_PROTECTION_GRANT_SWEEP_RE = re.compile(PROTECTION_GRANT_REGEX, re.IGNORECASE)


_BLOCKED_MATTERS_SWEEP_RE = re.compile(BLOCKED_MATTERS_REGEX, re.IGNORECASE)


# ADR-0027: the HAS-OTHER-PLAN reproduction for the migrated attack_matters key. The
# deleted _DETECTORS producer counted toward `has_other_plan` ONLY when it fired HIGH-
# confidence (an attack-trigger engine that wants the go-wide combat package, not a
# vanilla equip-up beater — Hellrider, Isshin, Accorder Paladin), but it fired LOW on a
# opponents-scoped "whenever ~ attacks, defending player <does X to their library/hand>"
# body (Goblin Guide, Robber of the Rich), which is itself a VOLTRON beater and so must
# NOT be silenced. A flat regex mirror cannot tell HIGH from LOW (both share the
# "whenever ~ attacks" shape), so a byte-faithful re-silence re-runs the deleted
# producer's EXACT per-clause logic (the lambda match AND the scope/confidence
# resolution) and silences only on a HIGH non-generic firing (_attack_matters_is_plan).
# The 10 combat keywords that fired HIGH scope 'you' are re-silenced from the keyword
# array (the shared _ATTACK_GO_WIDE_KEYWORDS set / _ATTACK_MATTERS_GATE_RE compile
# above). NOT _VOLTRON_SILENCING_PLAN_KEYS (a faithful reproduction). CR 903.10a.
def _attack_matters_is_plan(text: str, name: str) -> bool:
    """True iff the deleted attack_matters producer would have fired HIGH (non-generic),
    feeding has_other_plan. Re-runs its per-clause loop: the lambda match + the same
    _resolve_scope HIGH gate (forced_scope was None, so confidence == resolved_conf; the
    narrow Tinybones rescope also forces HIGH). Reproduces the pre-migration silence set
    byte-faithfully — the LOW opponents-scoped "defending player" attacker body (Goblin
    Guide) is NOT silenced. Matched over the reminder-STRIPPED joined text."""
    for clause in _clauses(text):
        cl = clause.lower()
        if not (
            ("whenever" in cl and "attack" in cl) or _ATTACK_MATTERS_GATE_RE.search(cl)
        ):
            continue
        if _tinybones_scope(clause):  # narrow Tinybones rule — HIGH
            return True
        _, conf = _resolve_scope(clause, cl, _scope(cl), name)
        if conf == "high":
            return True
    return False


# ADR-0027: the HAS-OTHER-PLAN reproduction for the migrated landfall key. The deleted
# _DETECTORS producer FORCED scope 'you' (so every firing was HIGH-confidence), counting
# toward `has_other_plan` — a landfall ENGINE (a ramp / extra-land / land-recursion
# build-around — Lotus Cobra, Tatyova, Crucible of Worlds, Azusa) IS a plan, not a
# vanilla equip-up beater, so it silenced the spurious commander-damage voltron tell.
# Because the producer was unconditionally HIGH, a flat byte-identical mirror of the
# producer's lambda (NOT a scope/confidence re-resolution as attack_matters needed)
# reproduces the silence set EXACTLY. The migrated IR arm is BROADER (+5 ir_only), so
# this byte-identical mirror — NOT _VOLTRON_SILENCING_PLAN_KEYS — restores the deleted
# regex's exact silence set WITHOUT over-silencing the 5 recall-gain bodies (Field of
# the Dead, Faldorn, Twists and Turns, Spectrum Sentinel, Deep Gnome Terramancer).
# Matched per-clause over the reminder-STRIPPED joined `text` (the deleted producer ran
# per-clause over stripped clauses): the three regex-expressible branches via
# _LANDFALL_PLAN_MIRROR (LANDFALL_REGEX), plus the one SUBSTRING-AND branch the deleted
# lambda ran ("whenever a land" & "enter" on the lower-cased clause — no single regex
# expresses a substring-AND). CR 207.2c / 305 / 903.10a.
_LANDFALL_PLAN_MIRROR = re.compile(LANDFALL_REGEX, re.IGNORECASE)


def _landfall_is_plan(text: str) -> bool:
    """True iff the deleted landfall producer would have fired (it forced scope 'you',
    so every firing was HIGH, feeding has_other_plan). Re-runs its per-clause lambda:
    the LANDFALL_REGEX match OR the "whenever a land" & "enter" substring-AND, over the
    reminder-STRIPPED joined text. Byte-faithful to the pre-migration silence set."""
    for clause in _clauses(text):
        cl = clause.lower()
        if _LANDFALL_PLAN_MIRROR.search(clause) or (
            "whenever a land" in cl and "enter" in cl
        ):
            return True
    return False


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


# ADR-0027 returns_to dimension (SIDECAR v34) — the EXACT deleted blink_flicker preset
# pattern, pinned for the byte-identical kept mirror. The `blink` theme preset
# (theme_presets.PRESETS["blink"].patterns) IS this single pattern; it is pinned here so
# the IR mirror is byte-stable independent of the preset registry. The deleted
# _PRESET_REGEX_SIGNALS producer ran it PER-CLAUSE over the reminder-stripped oracle.
BLINK_FLICKER_REGEX = r"exile[^.]*?return[^.]*?battlefield"
_BLINK_FLICKER_KEPT_RE = re.compile(BLINK_FLICKER_REGEX, re.IGNORECASE)


def _detect_blink_flicker_kept(kept_oracle: str) -> bool:
    """Byte-identical mirror of the two deleted blink_flicker HIGH-conf producers — the
    `blink` preset (per-clause `exile…return…battlefield`) and the cross-sentence
    `_detect_blink_fulltext` — over the reminder-stripped ``kept_oracle``. Recovers the
    DFC-flip / cross-sentence / GY-recursion-with-return bodies the structural
    returns_to arm misses (the residual regex_only). Mirrors the deleted producers' own
    per-clause / full-text scan exactly. CR 603.6e / 400.7."""
    if any(_BLINK_FLICKER_KEPT_RE.search(cl) for cl in _clauses(kept_oracle)):
        return True
    return _detect_blink_fulltext(kept_oracle) is not None


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

# discard_outlet (ADR-0027 discard-discarder scope, SIDECAR v26) — the EXACT deleted
# SWEEP_DETECTORS["discard_outlet"] regex (DISCARD_OUTLET_REGEX, byte-identical), kept
# as a PER-CLAUSE mirror in _signals_ir. The structural IR arm (a `discard` Effect scope
# in ('you','each')) + the cost arm ("discard" in cost_parts) catch the self-loot
# triggers and discard-as-cost outlets the literal regex missed (Murder of Crows,
# Burning-Tree Vandal — legitimate breadth), but phase under-parses a tail (granted
# "Discard a card:" abilities on enchanted/affected permanents, grandeur discard-a-copy
# costs, additional-cast-cost discards, cross-clause loot) the regex caught textually —
# this mirror recovers it. Its `draw [^.]*cards?[^.]*\.?\s*then discard` arm spans WHOLE
# oracle (over-fires flat), so — like self_blink / impulse_top_play — it MUST run
# PER-CLAUSE via _clauses (matching the deleted SWEEP path), NOT as a flat
# _IR_KEPT_DETECTORS full-text row. CR 701.8a.
_DISCARD_OUTLET_SWEEP_RE = re.compile(DISCARD_OUTLET_REGEX, re.IGNORECASE)

# Task #19 SPLIT — the named_synergy mirror regex (the named-card SYNERGY half of the
# old named_permanent lane), kept for the kept-mirror (_IR_KEPT_DETECTORS in
# _signals_ir, scope 'you', run FLAT over the reminder-stripped joined-face
# kept_oracle). The named-card synergy lane: a card referencing a specific OTHER card by
# name. phase drops the referenced name (only a bare `Named` flag survives, never the
# string), so the lane is signals-only — no projection, no sidecar bump (the meld_pair
# precedent). The two arms never cross a clause boundary (`[A-Z]`-anchored /
# `[^.]*`-bounded), so flat-over-kept_oracle == the deleted per-clause SWEEP firing
# (commander-legal: 26 cards). It fired HIGH scope 'you' and fed has_other_plan, so
# named_synergy joins signals._VOLTRON_SILENCING_PLAN_KEYS. The SIBLING copy_limit lane
# (CR 100.2a) is structural (IR `many_copies`), not this regex. CR 201.4 / 201.5 /
# 903.10a.
_NAMED_PERMANENT_SWEEP_RE = re.compile(NAMED_PERMANENT_REGEX, re.IGNORECASE)

# ADR-0027 dig library-owner scope (SIDECAR v27) — the EXACT deleted dig_until SWEEP
# regex, kept for the byte-identical mirror. The structural `dig_until` EFFECT
# scope=='you' arm covers the 49 own-library digs phase models as a dig effect; this
# mirror recovers the 44 your-library digs phase re-categorizes to
# cheat_play/reveal/topdeck_stack (Apex Devastator, Mass Polymorph, Madcap Experiment,
# the cascade/discover bodies). The deleted SWEEP Detector ran PER-CLAUSE over the
# reminder-STRIPPED oracle, so the mirror MUST too (cascade/discover restate the dig in
# PARENTHETICAL reminder text — stripped — so they never matched and still don't: union
# == 93 == the deleted producer, 0 over-fire). CR 701.23 / 401.
_DIG_UNTIL_SWEEP_RE = re.compile(DIG_UNTIL_REGEX, re.IGNORECASE)

# ADR-0027 topdeck library-owner scope (SIDECAR v28) — the EXACT deleted
# topdeck_selection SWEEP regex, kept for the byte-identical mirror. The
# structural `topdeck_select` EFFECT scope=='you' arm covers the scry/surveil
# doers + the supplement-promoted your-library look/reveal; this mirror
# recovers the 148 your-library reveals phase re-categorizes to `reveal` /
# cast_play (Fact or Fiction + the "an opponent separates these into two piles"
# cards, the cascade/dig reveal bodies — Ajani Unyielding, Atraxa Grand
# Unifier). The deleted SWEEP Detector ran PER-CLAUSE over the
# reminder-STRIPPED oracle, so the mirror MUST too. The regex is
# YOUR-library-anchored, so it never matched the opponent-library /
# opponent-hand peeks the structural arm also excludes. CR 116 / 701.18 /
# 701.42.
_TOPDECK_SELECTION_SWEEP_RE = re.compile(TOPDECK_SELECTION_REGEX, re.IGNORECASE)

# ADR-0027 exile_removal (SIDECAR v30) — the EXACT deleted exile_removal SWEEP regex,
# kept for the byte-identical mirror. The structural `cat=="exile"` single-target arm
# binds the genuine permanent removal (the v30 supplement retains cat=exile + a
# permanent subject on the rider-swallow / dropped-subject cases — Soul Partition,
# "Exile", Unexplained Absence); this mirror reproduces the blink/GY-hate over-fires
# the regex matched (Cloudshift, Ephemerate, Angel of Serenity — the v29 behavior the
# structural arm correctly EXCLUDES) PLUS the Drach'Nyen ETB-exile-dropped tail (phase
# carries no structural form for it). The deleted SWEEP Detector ran PER-CLAUSE over the
# reminder-STRIPPED oracle, so the mirror MUST too. CR 406.1 / 115.1.
_EXILE_REMOVAL_SWEEP_RE = re.compile(EXILE_REMOVAL_REGEX, re.IGNORECASE)

# ADR-0027 per-clause draw raw (SIDECAR v32) — the EXACT deleted draw_for_each SWEEP
# regex, kept for the byte-identical mirror. The structural `draw` Effect scaling-count
# arm (gated by the draw's PER-CLAUSE clause_raw — the projection's draw-local sub-
# clause) binds the genuine scaling draws phase structures; this mirror recovers the 12
# commander-legal cards phase RE-CATEGORIZES off the draw effect or leaves textual
# (Borrowed Knowledge, Curse of Surveillance, Sea Gate Restoration, Truth or
# Consequences, …). Its arms ("draw … for each" / "draw cards equal to the number of")
# never cross a clause boundary, so a per-clause scan over the reminder-STRIPPED oracle
# == the deleted SWEEP path byte-identically. CR 107.3.
_DRAW_FOR_EACH_SWEEP_RE = re.compile(DRAW_FOR_EACH_REGEX, re.IGNORECASE)

# play_from_top (ADR-0027 β) — the EXACT deleted SWEEP + _HAND_FLOOR regexes for the
# ongoing top-of-library play permission, kept as a byte-identical PER-CLAUSE mirror.
# The structural IR arm (a STATIC cast_from_zone+from:library Effect — project.
# _top_play_permission_marker over phase's TopOfLibraryCastPermission static mode)
# catches the 45-card clean spine (Future Sight, Bolas's Citadel, Mystic Forge, Vizier,
# Garruk's Horde, Oracle of Mul Daya, Courser of Kruphix — minus 2 granted-impulse
# statics excluded by the `"exile" not in raw` gate). But phase does NOT model as a
# cast-permission static the REVEAL-only forms ("Play with the top card revealed" —
# Goblin Spy, Crown of Convergence, Mul Daya Channelers, Skill Borrower, Vampire
# Nocturnus; "look at the top card any time" — Sphinx of Jwar Isle, Vesuvan Drifter,
# Glowcap Lantern), the ONCE-EACH-TURN restricted casts (Johann, Cemetery Illuminator,
# Assemble the Players, The Fourth Doctor), nor the TRIGGERED/temporary permissions
# (Gwenom, The Belligerent, The Lunar Whale, Xanathar, Ziatora's Envoy, Temporal
# Aperture, Fblthp, Radha). Those 25 ride this mirror — the EXACT deleted producers, so
# net recall == regex (no-flood). Both producers ran PER-CLAUSE over reminder-stripped
# clauses (split on .;\n), so the mirror runs the same way over kept_oracle's _clauses
# (un-lowered clauses + IGNORECASE == clause.lower(), so A-B == 0). The dig-until
# over-fire the FLOOR's broad `(?:play|cast)…from the top` arm catches (Amped Raptor,
# Codie, Jodah, Old Stickfingers — "exile/reveal cards from the top … until you exile/
# reveal", an impulse/dig engine NOT continuous top-play) is PRE-EXISTING production
# behavior reproduced byte-identically here, not a new over-fire. CR 116 / 601.3b.
_PLAY_FROM_TOP_MIRROR = re.compile(
    r"(?:may )?play (?:the )?top card of (?:your|their) library"
    r"|you may look at the top card of your library (?:any time|at any time)"
    r"|play with the top card of your library revealed"
    r"|(?:play|cast) (?:lands?|spells?|creature spells?)[^.]*from the top of your "
    r"library",
    re.IGNORECASE,
)
_PLAY_FROM_TOP_FLOOR_MIRROR = re.compile(
    r"(?:play|cast)\b[^.]*?\bfrom the top of your library",
    re.IGNORECASE,
)

# evasion_self (ADR-0027) — the EXACT deleted _HAND_FLOOR producer, pinned once and
# shared by the _signals_ir kept WORD MIRROR (the IR re-supply) and the voltron plan
# mirror below. No `[^.]*` arm, so a flat search over reminder-stripped text == the
# per-clause floor-Detector firing byte-identically. CR 509.1b / 702.14.
_EVASION_SELF_REGEX = re.compile(
    r"can't be blocked|\bunblockable\b"
    r"|\b(?:forest|island|mountain|plains|swamp)walk\b"
    r"|\b(?:horsemanship|menace|fear|intimidate|skulk)\b",
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
# ADR-0027 Cluster D — combat_buff_engine migrated to the Card IR (SIGNALS-ONLY,
# no projection: phase already structures the lane via Trigger.event in
# {attacks, blocks, begin_combat} + a pump/pump_target/place_counter effect). The
# deleted SWEEP_DETECTORS regex is pinned as COMBAT_BUFF_ENGINE_SWEEP_REGEX in
# _sweep_detectors (imported above); the _signals_ir kept mirror reuses it, and the
# helper below restores the voltron silence the two deleted producers fed.
_COMBAT_BUFF_ENGINE_SWEEP_RE = re.compile(COMBAT_BUFF_ENGINE_SWEEP_REGEX, re.IGNORECASE)


# Loot/rummage across a sentence boundary (Alpharael): "draw N cards. Then discard".
# Require the discard to be the ADJACENT clause (one period/comma + optional "then")
# so an unrelated later sentence ("draw two cards. You gain 3 life.") never matches.
# ADR-0027: the discard_matters _DETECTORS producer that read this is DELETED (the lane
# is migrated to the Card IR — a byte-identical _LOOT_FULLTEXT_RE kept-mirror in
# signals._IR_KEPT_DETECTORS + a scope-gated `discarded`-trigger structural arm). This
# regex SURVIVES (referenced by the voltron mirror below).
_LOOT_FULLTEXT_RE = re.compile(
    r"\bdraw (?:a|an|two|three|four|five|x|\d+) cards?[.,]?\s*"
    r"(?:then )?(?:you )?(?:may )?discard",
    re.IGNORECASE,
)
# Meld (CR 701.42): a meld piece either melds the pair into a result ("meld them into",
# front) or carries the reminder "(Melds with <front>.)" (back). Either side wants its
# ONE specific partner, so meld_pair is subject-bearing (subject = this card's name);
# the partner names this card, so signal_specs serves exactly it.
# ADR-0027 Cluster D: meld_pair migrated to the Card IR (a subject-bearing kept word
# mirror in _signals_ir). phase v0.1.60 structures a `Meld` Effect (source/partner/
# result) for ONLY 2 of the 14 commander-legal faces — the trigger-based FRONT pieces
# (Gisela, Graf Rats) — and DROPS the meld entirely for the other 12: the activated /
# complex-trigger front pieces (Urza Lord Protector, Hanweir Battlements, Mishra,
# Titania, Vanille — folded to a bare ChangeZone/exile or a conditional clause) AND the
# `(Melds with X.)` reminder-only BACK pieces (Bruna, Midnight Scavengers, Mightstone,
# Argoth, Hanweir Garrison, Phyrexian Dragon Engine, Fang — the reminder text is not
# parsed into ANY field). So a structural `Meld`-effect arm would recover only 2/14
# (both already caught), and project.py CANNOT recover the 12 (phase carries no meld
# data for them). The lane therefore rides a BYTE-IDENTICAL kept mirror of this exact
# regex over the RAW (un-stripped) joined oracle — the back-piece meld info lives in
# reminder text, which the reminder-stripped kept_oracle would lose. This producer is
# deleted; _MELD_FULLTEXT_RE survives as the mirror's pattern + the has_other_plan
# voltron re-supply (via _VOLTRON_SILENCING_PLAN_KEYS — the IR re-supply is the SAME 14
# cards, so the strict-subset facade is valid). SIDECAR UNCHANGED (signals-only, v36).
_MELD_FULLTEXT_RE = re.compile(r"\bmeld them into\b|\bmelds with\b", re.IGNORECASE)
# ADR-0027: ability_strip_payoff migrated to the Card IR (structural arm). These three
# patterns no longer drive a signal producer — they survive ONLY as the building blocks
# of the byte-identical _ability_strip_payoff_plan has_other_plan mirror (below), which
# re-supplies the voltron silence the deleted HIGH-confidence producer fed (the IR re-
# supply is narrower — Abigale only — so a _VOLTRON_SILENCING_PLAN_KEYS entry would leak
# the Retched Wretch self-recursion the regex also silenced). The strip ("loses all
# abilities") and the buff ("counter on that creature") are different clauses, so the
# mirror is a full-text check over the reminder-STRIPPED text (matching the deleted
# producer exactly).
_ABILITY_STRIP_RE = re.compile(r"loses all abilities", re.IGNORECASE)
_STRIP_COUNTER_RE = re.compile(r"counter on (?:that creature|it)\b", re.IGNORECASE)
_BASE_PT_SET_RE = re.compile(r"base power and toughness", re.IGNORECASE)


def _ability_strip_payoff_plan(text: str) -> bool:
    """The EXACT deleted ability_strip_payoff producer condition, for has_other_plan.

    Matched against the reminder-STRIPPED ``text`` (the deleted producer ran over the
    reminder-stripped joined-face oracle): the strip + the keyword-counter buff + NOT a
    base-P/T set. Re-supplies the voltron silence on BOTH cards the regex silenced
    (Abigale + Retched Wretch); the IR arm re-supplies only Abigale, so this byte-
    identical mirror keeps voltron_matters identical to pre-migration."""
    return bool(
        _ABILITY_STRIP_RE.search(text)
        and _STRIP_COUNTER_RE.search(text)
        and not _BASE_PT_SET_RE.search(text)
    )


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


def self_power_scale_match(text: str, name: str) -> bool:
    """True for the self-power-scaling cross-open tell ADR-0027 β re-homed from the
    deleted self_counter_grow _DETECTORS add: an effect whose value scales with the
    SOURCE's OWN power ("X is ~'s power", "equal to this creature's power" — Mona Lisa,
    Esper Sentinel, Velomachus Lorehold). Such a commander wants +1/+1 counter sources
    to pump its own power, so it opens self_counter_grow as a low-confidence cross-open.
    Name-aware (the card's own name + "this creature", NOT "its") so a fling's "target
    creature's power" stays out. Reused by the narrowed _SELF_COUNTER_GROW_MIRROR in
    _signals_ir so the migration keeps this cross-open out of extract_signals. CR
    122.1."""
    _self = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    return bool(
        re.search(
            rf"(?:equal to|x is|x equals?|where x is) [^.]*?(?:{_self})[^.]*?\bpower\b",
            text,
            re.IGNORECASE,
        )
    )


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


# ADR-0027 reveal/dig-v2 — the HAS-OTHER-PLAN voltron mirror for migrated cheat_into_
# play. The deleted producers (the _DETECTORS clause regex + the SWEEP widen + the
# polymorph full-text detector + the `have warp` membership row) all fired HIGH-
# confidence scope 'you' and fed has_other_plan (a cheat-into-play ENGINE — Sneak
# Attack, Show and Tell, a Polymorph commander — is a plan, not a vanilla beater). The
# migrated lane rides a BROADER structural arm (+215 ir_only — the reveal-until-creature
# + search-into-play recall the narrow regex literal missed), so re-supplying via
# _VOLTRON_SILENCING_PLAN_KEYS would OVER-silence those gains. So this byte-faithful
# gate
# reproduces ONLY the deleted producers' ORIGINAL silence set, per-clause over the
# reminder-STRIPPED `text` (the _DETECTORS / SWEEP arms are clause-local), plus the
# polymorph full-text detector and the warp membership row (both full-text). CR 903.10a.
_CHEAT_INTO_PLAY_DETECTORS_RE = re.compile(
    r"put [^.]*creature card[^.]*onto the battlefield"
    r"|put (?:a|that|those) [^.]*onto the battlefield from your (?:hand|library)",
    re.IGNORECASE,
)
_CHEAT_INTO_PLAY_SWEEP_RE = re.compile(
    r"put (?:a|that|those|up to (?:two|one|\d+))[^.]*"
    r"(?:permanent|creature|land|nonland)[^.]*cards?[^.]*onto the battlefield"
    r"|put a permanent card[^.]*onto the battlefield"
    r"|put [^.]*land cards?[^.]*onto the battlefield"
    r"|put (?:an? )?artifact,? (?:creature,? )?(?:or land |and/or land )?"
    r"card[^.]*from (?:your|their) hand onto the battlefield"
    r"|put an? [^.]*card[^.]*(?:from your (?:hand|library)|from among them) "
    r"onto the battlefield",
    re.IGNORECASE,
)
_CHEAT_INTO_PLAY_WARP_RE = re.compile(r"\bhave warp\b|gains? warp\b", re.IGNORECASE)


# ADR-0027 reveal/dig-v2 — tutor BYTE-IDENTICAL kept-mirror pattern (== the
# deleted _HAND_FLOOR producer). A "search your library for (a|an|up to|...)" over the
# REMINDER-STRIPPED kept_oracle: the "your" word drops opponent-library searches, the
# immediate "for" drops composite "search your library AND graveyard for", and reminder-
# stripping drops landcycling/transmute/partner-with parentheticals. Reused by the IR
# mirror (_signals_ir._IR_KEPT_DETECTORS) and the has_other_plan voltron silence.
TUTOR_MATTERS_REGEX = re.compile(
    r"search your library for (?:a|an|up to|one|two|three|x|that)", re.IGNORECASE
)
# ADR-0027 reveal/dig-v2 — cheat_into_play NARROW residue mirror for the two cards the
# structural arm (cat=='cheat_play' + to:battlefield + non-gy source, SIDECAR v37) can't
# reach: (1) the imprint-from-library cheat that spans TWO abilities (Clone Shell —
# "Imprint … look at the top four … exile one face down" in the ETB, "put it onto the
# battlefield" in the dies trigger; Summoner's Egg, already structurally covered, rides
# here harmlessly), and (2) Tannuk's "cards in your hand have warp" cheat-enabler (a
# membership cross-open phase emits no structural shape for — warp casts a hand card for
# its warp cost, a temporary cheat-into-play). Graveyard-guarded so it never re-fires an
# imprint that puts FROM a graveyard (none in the corpus, but kept honest). Commander-
# legal hit set: exactly {Clone Shell, Summoner's Egg, Tannuk} — 0 reanimation / land
# over-fire. CR 702.41 (imprint) / 702.184a (warp).
_CHEAT_INTO_PLAY_RESIDUE_RE = re.compile(
    r"\bhave warp\b|gains? warp\b"
    r"|imprint\b[\s\S]*?put it onto the battlefield"
    r"|imprint\b[\s\S]*?creature card[^.]*onto the battlefield",
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
        # ADR-0027: type_matters migrated to the Card IR. Its producers
        # (_detect_type_matters, _detect_multi_tribe_anthem, the type_matters row of
        # _detect_typed_gy_recursion, _detect_keyword_implied_tribe) are no longer
        # invoked here — the regex path must not emit the migrated key. The producers +
        # their patterns stay pinned (the IR path imports them for a byte-identical KEPT
        # MIRROR re-run PER-CLAUSE over the reminder-stripped kept_oracle, keeping the
        # creature-subtype subject the per-subject tribal serve spec interpolates +
        # the forced 'you' scope). The token_maker-driven type_matters cross-open below
        # likewise dropped in the hybrid (re-supplied by the IR make_token kindred);
        # the own-subtype + named-token membership type_matters arms are reproduced in
        # extract_signals_ir. Mirrors the keyword_tribe / typed_spellcast / token_maker
        # SUBJECT-CARRYING precedent. CR 205.3 / 109.3.
        # ADR-0027: keyword_tribe migrated to the Card IR. Its producer
        # (_detect_keyword_tribe) is no longer invoked here — the regex path must
        # not emit the migrated key. The producer + its constants stay pinned (the
        # IR path imports _detect_keyword_tribe for a byte-identical KEPT MIRROR run
        # per-clause over the reminder-stripped kept_oracle, preserving the keyword
        # subject the per-subject serve spec interpolates).
        # ADR-0027: typed_spellcast migrated to the Card IR. Its producer
        # (_detect_typed_spellcast) is no longer invoked here — the regex path must
        # not emit the migrated key. The producer + its _TYPED_SPELLCAST_PATTERN stay
        # pinned (the IR path imports _detect_typed_spellcast for a byte-identical KEPT
        # MIRROR run per-clause over the reminder-stripped kept_oracle, preserving the
        # creature-subtype subject the per-subject serve spec interpolates). Mirrors the
        # keyword_tribe SUBJECT-CARRYING migration precedent above.
        # ADR-0027: token_maker migrated to the Card IR. Its producer
        # (_detect_token_maker) is no longer invoked here — the regex path must not emit
        # the migrated key. The producer + its _TOKEN_MAKER_PATTERN stay pinned (the IR
        # path imports _detect_token_maker for a byte-identical KEPT MIRROR re-run
        # PER-CLAUSE over the reminder-stripped kept_oracle, preserving the creature-
        # subtype subject the per-subject serve spec interpolates and the forced 'you'
        # scope). The two token_maker-driven regex cross-opens below (creatures_matter,
        # type_matters) re-key off the byte-identical _TOKEN_MAKER_PATTERN mirror so the
        # sibling membership stays byte-identical to base. Mirrors the keyword_tribe /
        # typed_spellcast SUBJECT-CARRYING precedent. CR 111.2.
        # ADR-0027: _detect_typed_gy_recursion is no longer invoked here — BOTH its
        # rows are migrated to the Card IR (vehicles_matter earlier; type_matters this
        # batch), so the regex path must not emit either. The producer stays pinned;
        # extract_signals_ir re-runs it PER-CLAUSE (vehicles_matter via the dedicated
        # mirror, type_matters via the type_matters kept mirror). CR 305.7 / 205.3.
        # ADR-0027: _detect_keyword_implied_tribe (ninjutsu → Ninja) is no longer
        # invoked here — its only row is type_matters, now migrated. The producer stays
        # pinned; extract_signals_ir re-runs it in the type_matters kept mirror.
        # ADR-0027: card_draw_engine migrated to the Card IR. Its producer
        # (_detect_card_draw) is no longer invoked here — the regex path must not emit
        # the migrated key. The producer + its _CARD_DRAW_RE stay pinned (the IR path
        # imports _detect_card_draw for a byte-identical KEPT MIRROR re-run PER-CLAUSE
        # over the reminder-stripped kept_oracle, preserving the engine-vs-cantrip gate
        # and the 'you'/'each' scope the deleted producer emitted). The deleted producer
        # fired HIGH-confidence and fed has_other_plan, so its voltron silence is
        # restored by adding card_draw_engine to signals._VOLTRON_SILENCING_PLAN_KEYS
        # (the IR re-supply is the SAME breadth — residual 0/0/0). Mirrors the
        # keyword_tribe / typed_spellcast subjectless per-clause precedent. CR 120.2.
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
        # rearrange/put-on-top effects). ADR-0027 β: play_from_top is migrated to the
        # IR,
        # so it no longer rides this regex path's keys_now; key the cross-open off the
        # byte-identical _PLAY_FROM_TOP_MIRROR / _PLAY_FROM_TOP_FLOOR_MIRROR (the EXACT
        # deleted producers, run per-clause) so the sibling membership stays byte-
        # identical to base (topdeck_selection / topdeck_stack drift 0). CR 116.
        if "play_from_top" in keys_now or any(
            _PLAY_FROM_TOP_MIRROR.search(cl) or _PLAY_FROM_TOP_FLOOR_MIRROR.search(cl)
            for cl in _clauses(text)
        ):
            add("topdeck_selection", "you", "", text[:160], "low")
            add("topdeck_stack", "you", "", text[:160], "low")
        # ADR-0027: token_maker migrated, so the deleted producer no longer populates
        # `out` — re-derive the captured creature subtypes from the byte-identical
        # _detect_token_maker (kept pinned) PER-CLAUSE over the same reminder-stripped
        # `text` so both token_maker-driven cross-opens (creatures_matter, type_matters)
        # stay byte-identical to base.
        _token_maker_subjects = {
            subj
            for clause in _clauses(text)
            for _, subj in _detect_token_maker(clause, vocab)
            if subj
        }
        # A token_maker that makes CREATURE tokens (a captured subject: Darien makes
        # Soldiers, Jinnie Fay Cats/Dogs) is a go-wide creatures deck, so cross-open
        # creatures_matter: it wants anthems, per-creature-ETB payoffs (Soul Warden,
        # Impact Tremors), and Cathars' Crusade, none of which the bare token_maker lane
        # serves. Low confidence. Non-creature token makers (Treasure / Clue) never set
        # a token_maker subject, so they stay out. Scoped to token MAKERS (not the
        # broader tokens_matter payoff) so discovery's lane-weighted sort stays clean.
        # (creatures_matter is migrated — this regex cross-open is dropped in the hybrid
        # and the IR side re-supplies it; kept here for the pure-regex `extract_signals`
        # path, ir is None.)
        if "creatures_matter" not in keys_now and _token_maker_subjects:
            add("creatures_matter", "you", "", text[:160], "low")
        # A spell-copy commander (Veyran, Zevlor, Rassilon) copies the instants/
        # sorceries you cast, so it's a spellslinger wanting a dense spell base: cross-
        # open spellcast_matters (its serve covers every I/S). Low confidence.
        if "spell_copy_makers" in keys_now and "spellcast_matters" not in keys_now:
            add("spellcast_matters", "you", "", text[:160], "low")
        # A discard-OUTLET commander (loot / rummage / discard-to-pay) fills the
        # graveyard, so the discarded cards become GY fuel: it wants reanimation /
        # flashback / GY recursion. Cross-open graveyard_matters (Niambi reanimates,
        # Mishra recurs artifacts, Malfegor recurs the discarded hand). Low confidence.
        # ADR-0027 discard-discarder scope (SIDECAR v26): discard_outlet is migrated to
        # the IR, so it no longer rides this regex path's keys_now; key the cross-open
        # off the byte-identical _DISCARD_OUTLET_SWEEP_RE (the EXACT deleted SWEEP
        # producer, run PER-CLAUSE) so the graveyard_matters cross-open stays byte-
        # identical to base. CR 701.8a.
        # ADR-0027 graveyard scope/origin/zone (SIDECAR v29): graveyard_matters is NOW
        # migrated, so the hybrid DROPS this regex LOW cross-open along with every other
        # regex graveyard_matters. The hybrid re-runs the EXACT condition against the
        # MERGED key set and re-adds the LOW graveyard_matters when the merged set lacks
        # it (signals._reconcile_graveyard_matters_crossopen) — this producer stays for
        # the pure-regex (ir is None) degradation path.
        if "graveyard_matters" not in keys_now and any(
            _DISCARD_OUTLET_SWEEP_RE.search(cl) for cl in _clauses(text)
        ):
            add("graveyard_matters", "you", "", text[:160], "low")
        # A commander that MAKES tribe-X creature tokens (token_maker captured subtype)
        # wants tribe-X lords/support: its token board IS that kindred. Cross-open
        # type_matters=X. Most tribe-MEMBER token-makers already open it via membership;
        # this catches non-members (Grist, a Planeswalker that makes Insects). Low conf.
        # ADR-0027: type_matters is NOT migrated, so this regex cross-open SURVIVES the
        # hybrid — re-key it off the re-derived _token_maker_subjects (the byte-
        # identical _detect_token_maker re-run above) so type_matters drifts 0.
        for _sub in _token_maker_subjects:
            add(signal_keys.TYPE_MATTERS, "you", _sub, text[:160], "low")
        # Lure (force blocks) and blocked_matters (punish the blocker) are one
        # archetype: a commander that lures / must-be-blocked (Madame Vastra, Gorm)
        # wants the punish-when-blocked payoffs (Engulfing Slagwurm, Tolarian
        # Entrancer). One-directional — a bare "when blocked" trigger creature isn't a
        # lure deck, so blocked_matters does NOT cross-open lure.
        # ADR-0027: lure_makers is migrated to the IR, so it no longer rides this regex
        # path's keys_now; key the cross-open off the byte-identical
        # _LURE_MATTERS_PLAN_MIRROR (the EXACT deleted SWEEP regex over the reminder-
        # stripped `text`) so the sibling membership stays byte-identical to base
        # (blocked_matters drifts 0). The mirror matches the 69 commander-legal cards
        # the deleted producer fired on — NOT the 3 ir_only cards the IR broadened to,
        # so no NEW blocked_matters firing leaks. CR 509.1c.
        if (
            "lure_makers" in keys_now or _LURE_MATTERS_PLAN_MIRROR.search(text)
        ) and "blocked_matters" not in keys_now:
            add("blocked_matters", "you", "", text[:160], "low")
        # ADR-0027 β: the lifegain_matters self-bleed-wants-sustain block (ARM (B) — a
        # SIGNIFICANT repeated self-life-LOSS engine that wants lifegain to stay alive:
        # upkeep lose >=2 / cumulative upkeep / "lose life equal to" / Necropotence
        # draw-and-bleed / symmetric "each player loses [2-9]") migrated to the Card IR.
        # This inline producer (fired LOW confidence, so it never fed has_other_plan) is
        # deleted; it survives byte-identically as ARM (B) of LIFEGAIN_MATTERS_REGEX
        # (_sweep_detectors), run by the _LIFEGAIN_MATTERS_MIRROR in extract_signals_ir
        # over the same reminder-stripped oracle. CR 119 / 118.
        # ADR-0027 β — combat_damage_to_opp migrated to the Card IR. Its narrow
        # double-strike-grant producer (Raphael, Blade Historian, Berserkers' Onslaught:
        # "attacking creatures you control have double strike" → attackers connect with
        # players TWICE) is deleted here; the key is now served by the byte-identical
        # _IR_KEPT_DETECTORS mirror of COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX (same low
        # confidence). It fired LOW confidence, so it never fed has_other_plan — no
        # voltron PLAN mirror is needed for it.
        # ADR-0027: proliferate_matters migrated to the Card IR. This inline
        # "remove a counter as an ACTIVATION COST" producer (the colon = the cost;
        # Migloz/oil, Tayam/Fain/Duchess counter-spend engines want MORE counters,
        # i.e. proliferate fuel) is DELETED; it survives byte-identically as the
        # LOW-confidence _PROLIFERATE_REMOVE_COST_RE mirror arm in
        # extract_signals_ir. It fired LOW confidence, so it never fed
        # has_other_plan — no voltron PLAN mirror term is needed for it (the 55
        # countdown-resource cards with no other plan keep their voltron tell).
        # ADR-0027: keyword_soup_makers migrated to the Card IR. The keyword-soup
        # commander (Odric Lunarch Marshal, Akroma Vision, Akroma's Memorial/Will,
        # Concerted Effort, Bleeding Effect) grants/shares MANY evergreen keywords
        # across the team, so it wants creatures STACKED with keywords. This inline
        # producer (a team-grant context AND >=5 distinct evergreen keyword WORDS over
        # the reminder-stripped whole-text — no per-clause `[^.]` span) is DELETED; it
        # survives BYTE-IDENTICALLY as the include_membership-gated, LOW-confidence
        # _KEYWORD_SOUP_CONTEXT_RE + _EVERGREEN_KW_RE mirror in extract_signals_ir, run
        # flat over the same reminder-stripped kept_oracle (commander-legal: regex ==
        # mirror, 6 -> 6, 0 miss / 0 extra). A STRUCTURAL grant_keyword-counter_kind
        # arm was REJECTED — it LOSES Akroma's Will (its modal grants split across
        # abilities, so neither ability alone hits >=5 cks) and over-fires onto the
        # sibling `keyword_soup` lane's 11 single-creature keyword-ABSORBERS (Cairn
        # Wanderer, Rayami, Soulflayer, …), a different archetype. It fired LOW
        # confidence, so it never fed has_other_plan — no voltron PLAN mirror is needed.
        # CR 702 evergreen keywords.

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
        # anthem_static's regex producer is deleted (ADR-0027 tranche2-A migration) and
        # attack_matters's is deleted too (this migration), so neither rides keys_now
        # — the oracle mirrors keep the go_wide gate aware of a static team-buff /
        # attack-trigger payoff so an anthem / aggro lord's own class type still opens
        # (the IR go_wide sees the real signal; the mirrors preserve parity on the pure-
        # regex path). _attack_go_wide is the deleted producers' form (the per-clause
        # substring-AND + the two pinned branches + the combat-keyword array).
        _gate = {"creatures_matter", "attack_matters", "anthem_static"}
        go_wide = (
            bool(keys_now & _gate)
            or bool(_ANTHEM_GO_WIDE_MIRROR.search(card.get("oracle_text") or ""))
            or _attack_go_wide(card)
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
    # ADR-0027: BOTH the artifacts_matter AND enchantments_matter membership producers
    # are deleted — each survives byte-identically as the type_line membership arm in
    # extract_signals_ir ("if 'artifact' in type_line: add artifacts_matter you low" /
    # "if 'enchantment' in type_line: add enchantments_matter you low").
    # ADR-0027: the land_destruction creature-commander cross-open is migrated to the
    # Card IR — a creature whose own ability destroys lands (Numot) is an LD ENGINE
    # that opens the LD support lane, scope 'you', LOW confidence, membership + creature
    # gated so a one-shot LD SPELL among the 99 (Stone Rain) isn't mistaken for the
    # deck's plan. This producer is deleted; it survives BYTE-IDENTICALLY as the
    # membership-gated _LAND_DESTRUCTION_MIRROR arm in extract_signals_ir (creature +
    # include_membership + LAND_DESTRUCTION_REGEX over kept_oracle, low conf —
    # commander-legal: regex==mirror, 23→23, 0 miss/extra), NOT the broad `destroy`/Land
    # structural arm (which would flood +143 one-shot LD spells / utility lands HIGH).
    # The serve spec stays hand-registered. NO has_other_plan mirror: this producer
    # fired LOW confidence and never fed the voltron silence (which requires
    # confidence=='high'), so its deletion leaks no commander-damage tell. CR 305.6.
    # ADR-0027: cheat_from_top migrated to the Card IR. A commander that REVEALS its top
    # card and cheats the SAME revealed card onto the battlefield (Vaevictis, Hans
    # Eriksson, Lurking Predators) wants to STACK its top with a bomb. This membership-
    # gated producer is DELETED; it survives BYTE-IDENTICALLY as the _CHEAT_FROM_TOP_
    # MIRROR arm in extract_signals_ir (include_membership-gated — the OR-AND of the
    # EXACT deleted _CHEAT_TOP_REVEAL_RE + _CHEAT_TOP_ONTO_RE over the reminder-stripped
    # kept_oracle == this path's `text`; commander-legal: regex==mirror, 24→24, 0 miss/
    # extra). The v24 from:top/to:battlefield zone projection is too COARSE for a
    # structural arm (it over-fires +156 across the cheat_into_play / topdeck_selection
    # lane boundaries and still MISSES Vaevictis, whose reveal folds into a scope-'opp'
    # `choose` with no from:top). scope 'you', LOW confidence — it never fed
    # has_other_plan (the silence gate is confidence=='high'), so deleting it leaks no
    # voltron tell; NO _PLAN_MIRROR needed (the land_destruction / big_mana precedent).
    # The serve spec stays hand-registered in signal_specs.py. CR 401 / 701.20a.
    # ADR-0027: the kill_engine producer migrated to the Card IR (SIGNALS-ONLY). A
    # creature commander that repeatedly destroys creatures (Diaochan, Visara, Royal
    # Assassin, Western Paladin) is a death-engine: each kill fires on-death payoffs.
    # This membership cross-open is DELETED; it survives in extract_signals_ir as a
    # STRUCTURAL repeatable-frame arm (an activated destroy-creature ability, or a
    # RECURRING-trigger one — excluding one-shot ETB / morph-flip / monstrosity /
    # transform triggers per CR 701.37 / 707 / 701.27) UNION a byte-identical
    # _REPEATABLE_KILL_MIRROR for Evil Twin (its destroy is a quoted granted ability
    # phase folds into a `clone` Effect). The structural arm RECOVERS the +48 qualified-
    # creature kills the narrow regex missed ("destroy target TAPPED/WHITE/non-Demon
    # creature" — Royal Assassin, Western Paladin, Reaper from the Abyss). scope 'you',
    # LOW confidence — it never fed has_other_plan (the silence gate is
    # confidence=='high'), so deleting it leaks no voltron tell; NO _PLAN_MIRROR needed
    # (the land_destruction / cheat_from_top precedent). The serve spec stays hand-
    # registered in signal_specs.py. CR 305.6.
    # ADR-0027: big_mana migrated to the Card IR. A commander that generates big mana
    # wants X-spell sinks (Neheb, Sunastian). The include_membership cross-open is
    # deleted; it survives in extract_signals_ir as the membership-gated STRUCTURAL arm
    # (_is_big_mana_ir — a `ramp` Effect whose v23 amount is amount.factor>1 OR
    # op=="variable") UNION a byte-identical _BIG_MANA_REGEX kept mirror over
    # kept_oracle for the under-structured "add … for each" tail (Neheb → amount==None).
    # scope 'you', LOW conf — it fired LOW and never fed has_other_plan, so NO voltron
    # silencing entry is needed (the silence gate is confidence=='high'), matching the
    # land_destruction precedent. The serve spec stays hand-registered in
    # signal_specs.py. CR 106.4. ADR-0027 clone copied-type subject (SIDECAR v30):
    # clone_makers migrated to the Card IR. The legendary-recurring-value-engine
    # clone-TARGET cross-open (a LEGENDARY creature whose value is a REPEATABLE engine —
    # a per-turn triggered ability or a non-mana tap-activated ability — is itself a
    # clone target: copying it forks the engine and the copy dodges the legend rule;
    # "Clone your engine" for Obeka / Koma / Linessa, Dan's call) is RE-HOMED to
    # extract_signals_ir's include_membership block, reusing the SAME
    # _PER_TURN_ENGINE_RE / _TAP_ABILITY_RE / _MANA_TAP_RE helpers byte-identically (LOW
    # conf, scope 'you'). This regex emission is deleted so the regex path no longer
    # produces the migrated key. The helpers STAY (imported by the IR path). CR 707.1.

    # ADR-0027 returns_to dimension (SIDECAR v34): blink_flicker migrated to the Card
    # IR. The cross-sentence `_detect_blink_fulltext` add() (Roon, Norin, Aurelia,
    # Alpharael — trigger→payoff spanning a sentence boundary) is DELETED here; the IR
    # path reproduces it byte-identically as part of the BLINK_FLICKER_REGEX kept mirror
    # over kept_oracle. `_detect_blink_fulltext` STAYS (reused by the IR mirror).
    # ADR-0027 t2b4-C: self_blink migrated to the Card IR (kept_detector). The regex
    # path's emission (the name-aware fulltext detector + the SWEEP per-clause regex) is
    # deleted here; extract_signals_ir reproduces BOTH byte-identically. The
    # _detect_self_blink_fulltext / _SELF_BLINK_SWEEP_RE definitions stay — the IR path
    # reuses them.
    # ADR-0027: self_death_payoff migrated to the Card IR — the SELF-death Aristocrats
    # piece (the card rewards ITS OWN death — Kokusho, Solemn, Wurmcoil; SelfRef → scope
    # "you", DISTINCT from death_matters' OTHER-creature-dying real-subject trigger).
    # The lane fires from the STRUCTURAL `dies`-trigger SELF arm in extract_signals_ir
    # (+591 ir_only recall — the verbose "is put into a graveyard from the battlefield"
    # self forms + the keyword-expanded self-deaths Modular/Persist/Undying/Afterlife
    # the literal-"dies" regex missed) PLUS a name-aware kept mirror that reuses
    # _detect_self_death_payoff(kept_oracle, name) byte-identically to recover the 22
    # CONFERRED "When this creature dies" grants phase leaves as a quoted ability on the
    # target. This emission is deleted; _detect_self_death_payoff STAYS (reused by the
    # IR mirror AND the has_other_plan voltron silence below). CR 700.4 / 603.6e.
    # ADR-0027 Cluster D: meld_pair migrated to the Card IR. Its producer (a RAW-oracle
    # _MELD_FULLTEXT_RE scan that emitted scope 'you', subject = this card's name) is
    # deleted here; the IR path re-emits it as a byte-identical subject-bearing kept
    # mirror over the same RAW joined oracle (the back-piece "(Melds with X.)" lives in
    # reminder text). CR 701.42.
    # ADR-0027: plus_one_matters migrated to the Card IR — the self-counter-payoff and
    # counter-HAVE-payoff add() producers are deleted (the +1/+1 placement / "has a
    # +1/+1 counter" reference fires from place_counter(p1p1) + the counters_have_ref
    # marker via the IR path). Their orphaned regex helpers were removed with this
    # cleanup.
    # ADR-0027 reveal/dig-v2: cheat_into_play migrated to the Card IR. This polymorph-
    # cheat full-text detector add() (the reveal-until-creature "put it onto the
    # battlefield" Polymorph family — Jalira, Atla Palani, See the Unwritten) is
    # DELETED;
    # the STRUCTURAL cat=='cheat_play'+to:battlefield+from:top arm (the dig-into-play
    # retag + the SIDECAR-v37 source recovery) reproduces it and RECOVERS the +215
    # genuine library/hand cheats the narrow regex literal missed.
    # _detect_polymorph_cheat
    # STAYS — the has_other_plan voltron silence (_CHEAT_INTO_PLAY_PLAN_MIRROR below)
    # reuses it byte-identically. CR 110.2a / 400.7 / 701.23.
    # ADR-0027: reanimator migrated to the Card IR — a creature whose `reanimate`
    # effect returns CREATURE cards from a graveyard to the battlefield (the archetype),
    # via _reanimates_creature (incl. its raw fallback for the subject phase drops). The
    # legacy regex conflated this with "cast a spell FROM a graveyard" (flashback /
    # escape / disturb — CR 702.34 casting ≠ reanimation), which the structural IR
    # correctly drops. The legacy active-reanimation oracle-regex producer is deleted.
    # ADR-0027 Cluster D: combat_buff_engine migrated to the Card IR (SIGNALS-ONLY).
    # This full-text begin-combat single-target pump producer (Aurelia — the trigger
    # and the "gets +" payoff span a sentence boundary) is deleted; extract_signals_ir
    # fires the lane from a STRUCTURAL arm (a triggered ability with Trigger.event in
    # {attacks, blocks, begin_combat} + a pump/pump_target/place_counter effect, +588
    # recall the literal "gets +" regex missed — keyword combat-pumps Battle cry /
    # Mentor / Exalted / Bushido / Rampage / Melee, and "attacks → put a +1/+1 counter"
    # engines) UNION a byte-identical mirror of THIS producer + the deleted SWEEP regex
    # over kept_oracle. _COMBAT_BUFF_TRIGGER_RE / _COMBAT_BUFF_PUMP_RE STAY (the IR
    # mirror + the _combat_buff_engine_has_plan voltron re-supply reuse them). The
    # deleted producer fired HIGH and fed has_other_plan, so its voltron silence is
    # restored by _combat_buff_engine_has_plan() below. CR 508.
    # ADR-0027: discard_matters migrated to the Card IR — a scope-gated `discarded`-
    # trigger structural arm (scope != "opp", excluding the opponent_discard punisher
    # lane) PLUS a byte-identical _LOOT_FULLTEXT_RE kept-mirror in
    # signals._IR_KEPT_DETECTORS for the loot/rummage OUTLET ("draw N cards, then
    # discard" — Careful Study, Merfolk Looter) that has no `discarded` trigger. This
    # _LOOT_FULLTEXT_RE producer is deleted; the serve spec stays hand-registered in
    # signal_specs.py. The deleted producer fed has_other_plan (HIGH-confidence, scope
    # 'you'), so its voltron silence is restored by _DISCARD_MATTERS_PLAN_MIRROR below.
    # CR 702.35 / 120.1 / 903.10a.
    # ADR-0027: ability_strip_payoff migrated to the Card IR — the strip-and-buff payoff
    # (Abigale: ETB strips a target's abilities AND keeps it as a beater via keyword
    # counters) fires from a STRUCTURAL arm in extract_signals_ir (one ability has a
    # 'loses all abilities' effect-raw AND a place_counter effect, no base_pt_set
    # shrinker). The IR arm is strictly cleaner: the deleted regex over-fired on a self-
    # recursion creature whose "-1/-1 counter on it" CONDITION its `counter on
    # (that creature|it)` pattern matched (Retched Wretch — the IR reads that counter as
    # a Condition, never a place_counter buff, so the arm drops it). This regex producer
    # is deleted. The deleted producer fired HIGH (scope 'you', NOT generic/voltron-
    # compat) and fed has_other_plan, so a byte-identical _ABILITY_STRIP_PAYOFF_PLAN_
    # MIRROR (below) re-supplies the voltron silence on BOTH cards (the IR re-supply is
    # narrower — Abigale only — so _VOLTRON_SILENCING_PLAN_KEYS would leak Retched
    # Wretch). CR 613.1f / 122.1b: ability-removal and keyword counters resolve in
    # layer 6.
    # ADR-0027 (voltron migration — the LAST key): voltron_matters now fires
    # ENTIRELY from the Card IR (extract_signals_ir). The regex membership adds
    # (self-damage-prevention / hexproof beater / likely-voltron self-tells /
    # commander-damage fallback) and the ~930-line has_other_plan mirror chain that
    # re-supplied the regex-side silence are DELETED — that whole block existed only
    # to feed voltron's has_other_plan, which now reads the IR signal lanes directly.
    # The no-sidecar (ir is None) path no longer emits voltron, matching every other
    # migrated key's graceful degradation. CR 903.10a.
    return out


# creature commander) and discriminates no archetype. The other keys each pin a
# real sub-archetype, so they are NOT generic.
_GENERIC_KEYS = frozenset({"creatures_matter"})
