"""Counters and tokens bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    counter_kind,
    counter_kind_any,
    distribute_counter_kind,
    filter_controller,
    tag_of,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge._sweep_detectors import KEYWORD_COUNTER_REGEX
from mtg_utils._deck_forge.signal_base import (
    _resolve_subject,
    clauses,
)
from mtg_utils._deck_forge.text_reads import (
    _KEYWORD_COUNTER_KINDS,
    _PROLIFERATE_REMOVE_COST_RE,
    _detect_token_maker,
    self_power_scale_match,
)

# ── token_maker_type_subject structural read + bucket-B (ADR-0036/0037 ───────
# T10-finalize2 fold). The type_matters MEMBERSHIP token-profile union (LOW
# confidence, a granularity-c reconciliation in extract_crosswalk_signals,
# distinct from the HIGH-confidence Arm-B/synth pair above): a token-MAKER's
# creature type is a kindred-tribal tell (Krenko makes Goblins -> wants Goblin
# lords), read from the make_token effect's own ``types`` field, "Human"
# excluded (a vanilla Human token is not a typed-tribal signal — matches
# live's all_parts arm). Phase's Token-effect projection is incomplete for
# two idioms: a MODAL "choose one" ability where only one bullet's token node
# survives the ``effect_concepts`` walk (Ghalta and Mavren's Dinosaur bullet
# sits alongside the structurally-read Vampire bullet) and a token whose
# creation isn't tagged ``make_token`` at all (Circuits Act's die-roll token,
# Chalk Outline's investigate-adjacent token). The deleted lane-time
# ``clauses(_kept(tree))`` + ``_detect_token_maker`` per-clause scan is
# relocated here, per-subject gap-gated against the structural set
# (SYNTH-EXCLUSION-PARITY — 82/31621 commander-legal corpus cards genuinely
# gap; the other 2121 both-fire cards are already structural, ~34 cards'
# regex-only "Human" addition is the deliberate exclusion, not a gap). CR
# 205.3i (subtypes).


def structural_token_maker_type_subjects(tree: ConceptTree) -> set[str]:
    """Creature-token subtypes of every ``make_token`` effect's own typed
    ``types`` field (the Arm-B source SHARED by the lane reconciliation AND
    this stage's per-subject gap gate — one source, no drift).
    """
    out: set[str] = set()
    for c in tree.effect_concepts("make_token"):
        types = [t for t in getattr(c.node, "types", None) or [] if isinstance(t, str)]
        if "Creature" not in types:
            continue
        for t in types:
            sub = _resolve_subject(t, CREATURE_SUBTYPES)
            if sub and sub.lower() != "human":
                out.add(sub)
    return out


def _mirror_token_maker_type_subjects(oracle: str) -> set[str]:
    """Every creature-token subtype the deleted ``_detect_token_maker``
    per-clause mirror captured (reminder-stripped, clause-split — the SAME
    text the flag-OFF lane mirror scanned), "Human" excluded.
    """
    subs: set[str] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        for _key, sub in _detect_token_maker(cl, CREATURE_SUBTYPES):
            if sub and sub.lower() != "human":
                subs.add(sub)
    return subs


def _arm_token_maker_type_subject(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying ``token_maker_type_subject`` node for the
    bucket-B token-profile gap: a TUPLE of ONLY the creature-token subtypes
    the mirror finds that :func:`structural_token_maker_type_subjects` MISSES.
    Returns None when phase already structuralizes every captured subtype.
    """
    new = _mirror_token_maker_type_subjects(
        tree.oracle or ""
    ) - structural_token_maker_type_subjects(tree)
    if not new:
        return None
    return _synthetic_concept(
        arm_id="token_maker_type_subject",
        concept="synth_token_maker_type_subject",
        scope="you",
        subject=tuple(sorted(new)),
        desc="bucket-B token-maker type subject (phase's Token effect "
        "projection drops the creature subtype)",
    )


# ── arm: keyword_counter bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ───
# CR 122.1b: a counter that grants a keyword via layer 6 (CR 613.1f). Shared
# structural gate with the ``_keyword_counter`` lane — one source, no drift: a
# ``place_counter``/``remove_counter`` effect whose kind is in the CLOSED
# ``_KEYWORD_COUNTER_KINDS`` set. The genuine residue: phase nests the actual
# counter-kind CHOICE outside the effect chain for a ``ChooseOneOf`` branch
# (Boot Nipper's "your choice of a deathtouch counter or a lifelink counter",
# Owen Grady's activated "choice of a menace, trample, reach, or haste
# counter") and a counter RIDER attached to a sibling effect (Luminous
# Broodmoth's "return it... with a flying counter on it" riding a ChangeZone) —
# probed: 25/107 corpus fires are this class, structurally un-reachable this
# batch. Relocates the deleted ``KEYWORD_COUNTER_REGEX`` mirror verbatim.
def has_structural_keyword_counter(tree: ConceptTree) -> bool:
    """A CR 122.1b keyword-counter placement/removal phase types directly."""
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        if c.concept not in ("place_counter", "remove_counter"):
            continue
        kind = (counter_kind(c.node) or counter_kind_any(c.node)).lower()
        kind = kind.replace(" ", "")
        if kind in _KEYWORD_COUNTER_KINDS:
            return True
    return False


_KEYWORD_COUNTER_SYNTH_RX = re.compile(KEYWORD_COUNTER_REGEX, re.IGNORECASE)


def _matches_keyword_counter_idiom(oracle: str) -> bool:
    return bool(_KEYWORD_COUNTER_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_keyword_counter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``keyword_counter`` node for the choice/grant tail phase
    nests outside the effect chain (the deleted ``_KEYWORD_COUNTER_RX``
    relocated verbatim)."""
    if has_structural_keyword_counter(tree):
        return None
    if not _matches_keyword_counter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="keyword_counter",
        concept="synth_keyword_counter",
        scope="any",
        subject=(),
        desc="bucket-B keyword-counter choice/grant tail (CR 122.1b)",
    )


# ── arm: counter_distribute bucket-B (ADR-0036/0037 Stage 5, batch T2-counters)─
# CR 115.7f + 601.2d, the board-wide +1/+1 spread. Shared structural gate with
# the ``_counter_distribute`` lane — one source: a ``PutCounterAll`` of kind
# P1P1, OR a typed ``distribute``-marked P1P1 ``PutCounter`` controlled by You.
# ADR-0027 #24 re-confirmed (re-probed this batch: 220 structural / 163
# mirror-only residue) that the DISTRIBUTE-AMONG / "each of" / support-N /
# enters-with-additional forms carry the IDENTICAL single-target
# ``place_counter(P1P1, Creature/you)`` shape as an unrelated single-target
# pump (Verdurous Gearhulk vs Snakeskin Veil) — genuinely un-structurable this
# batch. Relocates the deleted NARROWED ``_COUNTER_DISTRIBUTE_MIRROR`` verbatim
# (per-clause — the plain self-enters arm stays excluded, self_counter_grow's
# turf).
def has_structural_counter_distribute(tree: ConceptTree) -> bool:
    """A CR 115.7f board-wide +1/+1 spread phase types directly."""
    for c in tree.effect_concepts("place_counter"):
        kind = counter_kind(c.node).upper()
        if tag_of(c.node) == "PutCounterAll" and kind == "P1P1":
            return True
        if distribute_counter_kind(c.node) == "P1P1":
            tgt = getattr(c.node, "target", None)
            if filter_controller(tgt) == "You":
                return True
    return False


_COUNTER_DISTRIBUTE_SYNTH_RX = re.compile(
    r"put (?:a|one|two|\d+|x) \+1/\+1 counters? on each (?:other )?creature you control"
    r"|distribute [^.]{0,30}?\+1/\+1 counters"
    r"|put (?:a |one or more |the same number[^.]*?)\+1/\+1 counters? on each of"
    r"|(?:enters? with|enter with) (?:a|an|one|two|three|x|\d+) additional "
    r"\+1/\+1 counters? on"
    r"|enters with that many additional"
    r"|\bsupport (?:x|\d+)\b",
    re.IGNORECASE,
)


def _matches_counter_distribute_idiom(oracle: str) -> bool:
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _COUNTER_DISTRIBUTE_SYNTH_RX.search(cl):
            return True
    return False


def _arm_counter_distribute(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``counter_distribute`` node for the distribute-among /
    support-N / enters-with-additional residue (the deleted
    ``_COUNTER_DISTRIBUTE_MIRROR`` relocated verbatim)."""
    if has_structural_counter_distribute(tree):
        return None
    if not _matches_counter_distribute_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="counter_distribute",
        concept="synth_counter_distribute",
        scope="you",
        subject=(),
        desc=(
            "bucket-B distribute/support/enters-with-additional +1/+1 "
            "residue (CR 122.1/122.6/614.12/702.105)"
        ),
    )


# ── arm: proliferate_matters bucket-B (ADR-0036/0037 Stage 5, T2-counters) ─────
# CR 701.34/701.34a proliferate + CR 702.184 station + 721.1: the Myojin
# divinity/indestructible enters-with-counter cycle and the charge/experience
# resource-counter makers (Ezuri, Mizzix, Aether Vial). NEW this batch: probed
# phase DOES type these as a typed counter kind — a ``place_counter`` /
# ``remove_counter`` effect's kind (Arwen's indestructible enters-with, Aether
# Vial's charge PutCounter), OR a ``give_player_counter`` effect's OWN
# ``counter_kind`` field (a DIFFERENT phase field name than the permanent-side
# ``counter_type`` — Ezuri's "you get an experience counter" GivePlayerCounter
# node carries ``counter_kind='Experience'``, which the shared ``counter_kind``/
# ``counter_kind_any`` helpers do not read, since those key off
# ``counter_type``). Re-probed: 158/167 corpus fires now structural (up from
# 144 with the added GivePlayerCounter read), 9 residue — a "Station" counter-
# scaling reference (Inspirit, Flagship Vessel; The Eternity Elevator), a
# choice-branch charge-counter increment (Immard's "put a charge counter on it
# or remove one"), and a pure reference/cost tail (Ion Storm's activation cost,
# Atreus's "for each experience counter", Dismantle's "that many... charge
# counters") phase does not carry as a typed node this batch. Relocates the two
# deleted mirrors verbatim, gated against the new structural read.
_PROLIFERATE_STRUCT_KINDS: frozenset[str] = frozenset(
    {"divinity", "indestructible", "charge", "experience"}
)


def has_structural_proliferate(tree: ConceptTree) -> bool:
    """A Myojin-cycle enters-with counter or a charge/experience resource
    counter phase types directly (permanent-side OR player-side kind field)."""
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        if c.concept in ("place_counter", "remove_counter"):
            kind = (counter_kind(c.node) or counter_kind_any(c.node) or "").lower()
            if kind in _PROLIFERATE_STRUCT_KINDS:
                return True
        elif c.concept == "give_player_counter":
            kind = (getattr(c.node, "counter_kind", None) or "").lower()
            if kind in _PROLIFERATE_STRUCT_KINDS:
                return True
    return False


_PROLIF_ENTERS_COUNTER_SYNTH_RX = re.compile(
    r"enters with a(?:n)? (?:divinity|indestructible) counter", re.IGNORECASE
)
_PROLIF_RESOURCE_COUNTER_SYNTH_RX = re.compile(
    r"\bcharge counter|\bexperience counter", re.IGNORECASE
)


def _matches_proliferate_idiom(oracle: str) -> bool:
    kept = _REMINDER.sub(" ", oracle or "")
    return bool(
        _PROLIF_ENTERS_COUNTER_SYNTH_RX.search(kept)
        or _PROLIF_RESOURCE_COUNTER_SYNTH_RX.search(kept)
    )


def _arm_proliferate_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``proliferate_matters`` node for the Station-reference /
    choice-branch / pure-reference residue (the deleted
    ``_PROLIF_ENTERS_COUNTER_MIRROR`` / ``_PROLIF_RESOURCE_COUNTER_MIRROR``
    relocated verbatim)."""
    if has_structural_proliferate(tree):
        return None
    if not _matches_proliferate_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="proliferate_matters",
        concept="synth_proliferate_matters",
        scope="you",
        subject=(),
        desc="bucket-B counter-resource reference/enters-with residue (CR 121/701.34)",
    )


# ── arm: proliferate_matters LOW residual (ADR-0036/0037 Stage 5, T9-finalize) ─
# CR 121/701.34: the LOW-confidence "remove a counter as an ACTIVATION COST"
# tell (the deleted ``_PROLIFERATE_REMOVE_COST_RE`` mirror relocated
# verbatim — spending a counter as a cost signals the deck wants MORE of it,
# i.e. proliferate fuel: Migloz, Rasputin, Tayam / Fain / O'aka / Duchess).
# Deliberately NOT gap-gated against has_structural_proliferate: the live
# lane emits this as a SEPARATE LOW signal alongside (never instead of) the
# HIGH structural/synth firing, so this arm fires independent of it.
def _arm_proliferate_remove_cost(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a LOW-confidence ``proliferate_matters`` node for the
    remove-counter-as-activation-cost residue (the deleted
    ``_PROLIFERATE_REMOVE_COST_RE`` mirror relocated verbatim)."""
    if not _PROLIFERATE_REMOVE_COST_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="proliferate_remove_cost",
        concept="synth_proliferate_remove_cost",
        scope="you",
        subject=(),
        desc="bucket-B remove-counter activation-cost residue (CR 121/701.34)",
    )


# ── arm: self_counter_grow bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ─
# CR 122.1 + adapt/monstrosity/renown (CR 701.46/701.37/702.104): the
# grow-ITSELF lane. Shared structural gate with the ``_self_counter_grow``
# lane — one source: an effect-role ``PutCounter{P1P1, SelfRef}`` (a
# replacement-origin unit additionally requiring the replacement's own SelfRef
# valid_card, so board grants like Master Biomancer stay out; a Devour chain
# vetoed by a sibling ``sacrifice`` effect, Mycoloth), OR an Adapt/Monstrosity/
# Renown effect tag. The genuine residue: the narrowed self-anchored text
# idiom ("on him/her/itself/this creature") phase leaves un-typed — re-probed
# this batch at 1458 structural / 21 mirror-clause residue (the loose "on it"
# arm stays EXCLUDED — it 100%-over-fired onto other-creature placements per
# ``test_counter_distribute_is_board_wide_only``'s sibling gate, so relocating
# it verbatim carries zero NEW over-fire risk). The separate
# ``self_power_scale_match`` cross-open (a self-power-SCALING tell, NOT a
# counter placement — Esper Sentinel, Dreadhorde Arcanist) is OUT OF SCOPE for
# this fold: it is not the named mirror, stays a direct text read in the lane,
# unchanged.
_SELF_GROW_ACTION_TAGS: frozenset[str] = frozenset({"Adapt", "Monstrosity", "Renown"})


def has_structural_self_counter_grow(tree: ConceptTree) -> bool:
    """A CR 122.1 self-anchored +1/+1 grow, or an Adapt/Monstrosity/Renown
    keyword action, phase types directly."""
    for unit in tree.units:
        for c in unit.effect_concepts("place_counter"):
            if tag_of(c.node) != "PutCounter":
                continue
            if counter_kind(c.node) != "P1P1":
                continue
            if tag_of(getattr(c.node, "target", None)) != "SelfRef":
                continue
            if unit.origin == "replacement":
                if tag_of(getattr(unit.node, "valid_card", None)) != "SelfRef":
                    continue
                if any(s.concept == "sacrifice" for s in unit.effects):
                    continue
            return True
        for c in unit.effects:
            if tag_of(c.node) in _SELF_GROW_ACTION_TAGS:
                return True
    return False


_SELF_COUNTER_GROW_SYNTH_RX = re.compile(
    r"enters with (?:x|\d+|a|an|one|two|three) \+1/\+1 counters? on "
    r"(?:him|her|itself|this)"
    r"|put (?:a|one|two|three|x|\d+) \+1/\+1 counters? on "
    r"(?:him|her|itself|this creature)\b"
    r"|put that many \+1/\+1 counters? on (?:him|her|itself|this creature)",
    re.IGNORECASE,
)


def _matches_self_counter_grow_idiom(oracle: str) -> bool:
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _SELF_COUNTER_GROW_SYNTH_RX.search(cl):
            return True
    return False


def _arm_self_counter_grow(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``self_counter_grow`` node for the self-anchored +1/+1
    residue (the deleted ``_SELF_COUNTER_GROW_MIRROR`` relocated verbatim)."""
    if has_structural_self_counter_grow(tree):
        return None
    if not _matches_self_counter_grow_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="self_counter_grow",
        concept="synth_self_counter_grow",
        scope="you",
        subject=(),
        desc="bucket-B self-anchored +1/+1 counter residue (CR 122.1/614.12)",
    )


# ── arm: self_counter_grow self-power-scale residual (ADR-0036/0037 Stage 5,
# T9-finalize) ──────────────────────────────────────────────────────────────
# CR 122.1: the separate self-power-SCALING cross-open (the deleted direct
# ``self_power_scale_match`` read relocated verbatim) — an effect whose
# value scales with the SOURCE's OWN power ("equal to this creature's
# power" — Esper Sentinel, Mona Lisa, Velomachus Lorehold). Such a commander
# wants +1/+1 counter sources to pump its own power, so it opens
# self_counter_grow as a low-confidence cross-open (fired here at HIGH,
# matching the live lane's own confidence for this arm). Gap-gated against
# BOTH upstream arms (SYNTH-EXCLUSION-PARITY): a card already covered by
# the structural PutCounter/keyword-action read or the narrowed +1/+1 text
# idiom never double-fires this one.
def _arm_self_power_scale(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``self_counter_grow`` node for the self-power-scaling
    cross-open (the deleted ``self_power_scale_match`` direct read
    relocated verbatim)."""
    if has_structural_self_counter_grow(tree):
        return None
    if _matches_self_counter_grow_idiom(tree.oracle or ""):
        return None
    oracle = tree.oracle or ""
    if not self_power_scale_match(_REMINDER.sub(" ", oracle), tree.name):
        return None
    return _synthetic_concept(
        arm_id="self_power_scale",
        concept="synth_self_power_scale",
        scope="you",
        subject=(),
        desc="bucket-B self-power-scaling cross-open (CR 122.1)",
    )


# ── arm: convert-then-adapt self_counter_grow (np_counters item 2) ────────────
# CR 701.46a ("Adapt N" = "If this permanent has no +1/+1 counters on it, put
# N +1/+1 counters on it") chained behind a Convert: Jetfire, Air Guardian's
# "{U}{U}{U}: Convert Jetfire, then adapt 3." parses as a bare ``Transform``
# effect and the ", then adapt 3" consequence is dropped WHOLLY — no node, no
# Unimplemented residue (node-dump verified at the v0.23.0 pin), so neither
# the recovery grammar (route i — nothing to re-decorate) nor an overlay
# correction (route ii — no under-read field on the Transform) can anchor.
# The card is a genuine Adapt DOER (its own 2022-10-14 rulings: convert works
# exactly like transform; the adapt happens as the ability resolves) missing
# from ``self_counter_grow``'s population — the adapt_matters lane note in
# ``crosswalk_signals`` already flags this exact card as "a bucket-B gap in
# self_counter_grow itself". Reuses the EXISTING ``synth_self_counter_grow``
# marker so no lane code changes; the corpus's other 24 "adapt N" carriers
# all parse a typed ``Adapt`` node, which the structural gate excludes here.
_CONVERT_ADAPT_RE = re.compile(
    r"\bconvert [^.;\n]{1,60}?, then adapt (?:\d+|x)\b", re.IGNORECASE
)


def _arm_convert_adapt_self_grow(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``self_counter_grow`` node for the "Convert ~, then
    adapt N" chained consequence phase drops whole. CR 701.46a."""
    if has_structural_self_counter_grow(tree):
        return None
    if not _CONVERT_ADAPT_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="convert_adapt_self_counter_grow",
        concept="synth_self_counter_grow",
        scope="you",
        subject=(),
        desc="convert-then-adapt-N consequence dropped whole (CR 701.46a)",
    )


# ── arm: dropped possessed-counters relocation (np_counters item 3) ───────────
# CR 122.1: the counter RELOCATION idiom — moving counters a permanent
# already possesses onto another object ("put its/those counters on X"),
# normally a typed ``MoveCounters`` node (19 of the corpus's 21 carriers:
# Essence Channeler, Iron Apprentice, The Ozolith, Reluctant Role Model, …)
# that ``counter_move`` + ``any_counter_makers`` read structurally. TWO
# corpus cards drop the clause WHOLE with no residue node to re-decorate
# (routes i/ii can't anchor):
#
# * Ambitious Augmenter — "…create a 0/0 … Fractal creature token, then put
#   this creature's counters on that token": only the ``Token`` sibling
#   survives; the move clause vanishes.
# * Heroic Sacrifice — the entire delayed dies-trigger ("When that creature
#   dies this turn, put its counters on up to one target creature you
#   control and draw a card") is dropped; the card parses as ONLY its
#   damage-redirect replacement.
#
# Gated on NO structural ``move_counters`` concept anywhere on the tree, so
# every typed carrier stays on its real node; a placement of NEW counters
# ("put a +1/+1 counter on") never matches the possessive form. The marker
# concept is read by ``counter_move`` and ``any_counter_makers`` (the same
# pair every typed classmate fires), and deliberately NOT by
# ``plus_one_matters``'s kind-gated ``move_counters`` read — a synthetic
# node carries no ``counter_type``, matching Iron Apprentice's own
# kind-agnostic membership.
_DROPPED_COUNTER_MOVE_RE = re.compile(
    r"\bput (?:its|those|this creature's|~'s) counters on\b", re.IGNORECASE
)


def _arm_dropped_counter_move(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``counter_move`` marker for the possessed-counters
    relocation clause phase drops whole. CR 122.1."""
    if tree.effect_concepts("move_counters"):
        return None
    if not _DROPPED_COUNTER_MOVE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="dropped_counter_move",
        concept="synth_counter_move",
        scope="you",
        subject=(),
        desc="possessed-counters relocation clause dropped whole (CR 122.1)",
    )


# ── arm: plus_one_makers bucket-B (task #85, plus-one-counters preset) ────────
# CR 122.1: a +1/+1 counter PLACEMENT phase drops entirely rather than typing
# as a ``place_counter`` concept, corpus-confirmed across four repeated
# TEMPLATE shapes a 415-card residual census (v0.23) split into:
#
# * an ETB REPLACEMENT effect phase's static parser can't reach at all
#   ("This creature enters with X +1/+1 counters on it, where X is …" —
#   Cogwork Grinder, Naya Soulbeast, Lupine Harbingers) — the whole clause
#   decorates as an ``Unimplemented`` EFFECT-role node whose raw literally
#   starts "Replacement pattern matched but line failed replacement
#   parser: ~ enters with X …", OR (Worldheart Phoenix, Undead Sprinter,
#   Tervigon's "Ravenous" reminder) leaves NO unit/effect trace at all.
# * a COMPUTED-amount ``PutCounter`` targeting something the unit ALSO
#   just made ("Create a 0/0 … Fractal token. Put X +1/+1 counters on
#   it." — Body of Research, Sequence Engine, the Kamigawa Fractal cycle;
#   "Put a +1/+1 counter on it for each invasion counter on this
#   enchantment" — Alien Invasion) — the preceding ``make_token``/
#   ``change_zone`` effect survives, but the FOLLOWING variable-amount
#   counter clause is dropped with no node at all (mirrors the
#   ``direct_damage`` "computed-amount … clause phase drops entirely"
#   precedent a few hundred lines up ``crosswalk_signals.py``).
# * a PLANESWALKER loyalty ability's own effect ("[-3]: … put a number of
#   +1/+1 counters on it equal to …" — Jared Carthalion, Elspeth
#   Resplendent) — phase types the whole clause ``Unimplemented`` with the
#   counter-placement instruction verbatim as the node's raw text.
# * the general "Put N +1/+1 counter(s) on <target>" imperative-effect
#   template anywhere else phase's grammar doesn't reach it (Furgul, Elder
#   Arthur Maxson's granted Training, Amzu, Emissary Green, …).
#
# All four collapse to ONE idiom read: an IMPERATIVE "put(s) … +1/+1
# counter(s)" clause (never the PASSIVE "is/are put" phrasing a matters-
# side payoff uses to describe an EXTERNAL placement — Hardened Scales-
# style triggers stay ``plus_one_matters``' territory) or the ETB-
# replacement "enters … with … +1/+1 counter(s) on it" template, read on
# the REMINDER-STRIPPED whole-card oracle. Reminder-stripping is what
# keeps this SHED (not double-served) from every keyword mechanic whose
# OWN +1/+1-counter rider is reminder text on a DIFFERENT keyword —
# Connive ("If you discarded a nonland card, put a +1/+1 counter on this
# creature."), Amass, Explore, Incubate, Megamorph, Awaken all template
# their counter clause inside parens; stripping them before matching
# means this arm never re-opens those already-distinct preset/signal
# lanes (Connive routes to ``connive_makers``/cantrip, Amass/Incubate to
# their own token-preset, Megamorph to ``facedown_makers`` — CR 702.153/
# 701.47/701.53/702.75). Reanimation-with-a-bonus-counter ("Return …
# creature card from your graveyard to the battlefield with an additional
# +1/+1 counter on it" — A-Graveyard Shift, Drana) uses neither "put" nor
# "enters", so it's excluded by construction, not by an explicit list —
# CR 122.1 doesn't treat that rider as the reanimation effect's own
# mechanic, but this preset's SCOPE decision (task #85) is that
# reanimation stays its own archetype. Gap-gated against the SAME
# structural ``place_counter``/P1P1 read ``_plus_one_makers`` runs first
# (never double-counts a card Tier-1 already reads).
_PLUS_ONE_ETB_RX = re.compile(
    r"enters (?:the battlefield )?with .{0,80}\+1/\+1 counters? on it",
    re.IGNORECASE,
)
_PLUS_ONE_PUT_RX = re.compile(
    r"(?<!is )(?<!are )(?<!re-)\bput(?:s)?\b(?:(?!\.|;).){0,150}?\+1/\+1 counters?\b",
    re.IGNORECASE,
)


def has_structural_plus_one_makers(tree: ConceptTree) -> bool:
    """A typed P1P1 ``PutCounter``/``place_counter`` concept anywhere on
    the tree — the SAME read ``crosswalk_signals._plus_one_makers`` runs,
    factored out here so this module's gap-gate never drifts from it."""
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "place_counter":
                continue
            ck = counter_kind(c.node).upper()
            if ck == "P1P1" or (not ck and "+1/+1 counter" in (c.raw or "")):
                return True
    return False


def _matches_plus_one_makers_idiom(oracle: str) -> bool:
    stripped = _REMINDER.sub(" ", oracle or "")
    if _PLUS_ONE_ETB_RX.search(stripped):
        return True
    for cl in re.split(r"[.\n]", stripped):
        low = cl.lower()
        if "put" not in low:
            continue
        # opponent-directed placements are their own archetype (task #85
        # scope) — "target opponent puts a +1/+1 counter on a creature
        # they control" reads as an OPPONENT choice, not this card's own
        # making. Only excludes when "opponent" precedes the verb in the
        # SAME clause (an opponent REFERENCED after the placement, e.g.
        # "put a +1/+1 counter on target creature an opponent controls",
        # still counts — you are the one placing it).
        put_idx = low.find("put")
        if "opponent" in low[:put_idx]:
            continue
        if _PLUS_ONE_PUT_RX.search(cl):
            return True
    return False


def _arm_plus_one_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``plus_one_makers`` node for the dropped-clause /
    Unimplemented-residue P1P1 placement residual (task #85) — see the
    block comment above for the four template shapes this idiom read
    unifies."""
    if has_structural_plus_one_makers(tree):
        return None
    if not _matches_plus_one_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="plus_one_makers",
        concept="synth_plus_one_makers",
        scope="you",
        subject=(),
        desc="bucket-B +1/+1 counter placement (dropped-clause residue)",
    )


# The "one-time boon" +1/+1-counter sibling (np_boons task #2 — see
# ``_BOON_CREATURE_CAST_RE``'s docstring for the two ungapped node shapes
# this idiom covers). The delayed trigger's OWN "+1/+1 counter" grant
# (Arcane Archery, Champions of Tyr, March Toward Perfection, Tenacious
# Pup, Patchplate Resolute, Benalish Knight-Counselor) is a genuine CR
# 122.1 P1P1 placement the card WILL perform (once, on its next qualifying
# creature cast) — the same population ``_matches_plus_one_makers_idiom``
# already recognizes for a live top-level "enters with ... +1/+1 counter"
# clause, just wrapped in the quoted boon body instead of sitting bare in
# the oracle (so the sibling regex's own "on it" tail requirement, tuned
# for a SINGLE counter grant, doesn't fit a boon's "+1/+1 counter, a flying
# counter, or a lifelink counter on it" multi-counter list — a dedicated,
# narrowly-anchored pattern instead of loosening the general idiom's own
# regex and risking its unrelated corpus population). Anchored the same
# way as ``_BOON_CREATURE_CAST_RE`` — confined inside the quoted
# sub-string, never a blind scan.
_BOON_PLUS_ONE_RE = re.compile(
    r"\bone-time boon with \"[^\"]*?\+1/\+1 counter\b", re.IGNORECASE
)


def _arm_boon_plus_one_makers(tree: ConceptTree) -> ConceptNode | None:
    """See :data:`_BOON_PLUS_ONE_RE`'s module comment. CR 122.1."""
    if has_structural_plus_one_makers(tree):
        return None
    if not _BOON_PLUS_ONE_RE.search(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="boon_plus_one_makers",
        concept="synth_plus_one_makers",
        scope="you",
        subject=(),
        desc="one-time-boon +1/+1 counter placement, no anchorable node",
    )


# ── arm: poison_matters bucket-B (ADR-0036/0037 Stage 5, batch T2-counters) ────
# CR 122 + 704.5c: the "poison counter" reference/giver mirror (the ADR-0034
# partition — infect/toxic/poisonous keyword BEARERS ride the separate
# poison_makers lane). No competing Tier-1 predicate was probed for this
# residual class: a poison-counter payoff reference (Corrupted's threshold
# check) and a poison-GIVER that spells out "poison counter" instead of
# bearing Infect (Fynn, Caress of Phyrexia) are indistinguishable from each
# other structurally without re-opening the ADR-0034 partition, so this arm is
# the lane's SOLE source (the evasion_self/celebration no-competing-predicate
# precedent). Relocates the deleted ``_POISON_MATTERS_MIRROR`` verbatim.
_POISON_MATTERS_SYNTH_RX = re.compile(r"poison counters?", re.IGNORECASE)


def _matches_poison_matters_idiom(oracle: str) -> bool:
    return bool(_POISON_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_poison_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``poison_matters`` node for the "poison counter" text
    reference/giver (the deleted ``_POISON_MATTERS_MIRROR`` relocated
    verbatim)."""
    if not _matches_poison_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="poison_matters",
        concept="synth_poison_matters",
        scope="opponents",
        subject=(),
        desc="bucket-B poison-counter reference/giver (CR 122/704.5c)",
    )
