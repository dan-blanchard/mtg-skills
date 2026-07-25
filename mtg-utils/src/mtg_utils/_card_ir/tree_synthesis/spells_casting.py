"""Spellcasting bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    counter_kind,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_predicates,
    filter_subtypes,
    is_creature_cast_trigger_def,
    is_opponent_cast_trigger_def,
    iter_mod_sites,
    iter_nested_trigger_defs,
    iter_typed_nodes,
    mod_keyword_name,
    modify_cost_mode,
    static_mode_field,
    static_mode_tag,
    tag_of,
    trigger_caster_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _BECOMES_TARGET_SRC_OPP,
    _EXHAUST_TRIG,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._card_ir.tree_synthesis.value_engines import _subtree_has_graveyard_zone
from mtg_utils._deck_forge.signal_base import clauses
from mtg_utils._deck_forge.text_reads import (
    _CONVOKE_RAW,
    _EVERGREEN_CK,
    _SAME_TRUE_KW_RE,
)

# ── spellcast_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_spellcast_matters`` lane fires ``spellcast_matters`` on these typed
# reads; this stage's gap gate (:func:`has_structural_spellcast`) reads the SAME
# predicate so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift). CR
# 601.2 (casting) / 603.2 (triggered abilities).

# The compound "cast OR COPY" magecraft event (Archmage Emeritus, Storm-Kiln
# Artist, Veyran) phase derives as a DISTINCT mode from a bare cast — read
# structurally off ``trigger_event``, never text, exactly like
# ``ATTACK_TRIGGER_EVENTS``.
CAST_TRIGGER_EVENTS: frozenset[str] = frozenset({"cast_spell", "spellcastorcopy"})
# A predicate on the watched spell that narrows it to spells TARGETING the
# source (Heroic — CR 702.107a) — a self-target voltron/tribal-adjacent
# mechanic, not a Spellslinger density payoff. Vetoed at both the structural
# gate and the bucket-B text idiom.
_SPELLCAST_TARGET_VETO_PREDS: frozenset[str] = frozenset(
    {"Targets", "TargetsOnly", "HasSingleTarget"}
)


def has_structural_spellcast(tree: ConceptTree) -> bool:
    """A phase-typed you-cast trigger this lane reads as ``spellcast_matters``.

    Two families, both requiring ``trigger_caster_scope(unit.node) == "you"``
    (CR 603.2 — a symmetric "a player casts" hoser carries no you-scope and
    never fires either lane):

    * TYPED — the watched spell is Instant/Sorcery (core type) or explicitly
      NON-creature (``Non: Creature`` — the Prowess idiom). An
      enchantment/artifact-ONLY watched spell is carved out to the type lane
      (Alela) instead.
    * UNTYPED (Aetherflux Reservoir, Extort/Increment keyword triggers) — the
      watched spell carries NO restrictive core type (empty, or the ``Card``
      wildcard used for a CMC/zone/color-agnostic gate) AND no SUBTYPE
      restriction (Aang's "Lesson spell", tribal cast triggers — a different,
      narrower archetype signal) AND no SUPERTYPE restriction (Shanid's "a
      legendary spell" — that rewards legendary permanents broadly
      (legends_matter), not I/S Spellslinger density) AND no self-target
      restriction (:data:`_SPELLCAST_TARGET_VETO_PREDS` — Heroic).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event not in (CAST_TRIGGER_EVENTS):
            continue
        if trigger_caster_scope(unit.node) != "you":
            continue
        vc = getattr(unit.node, "valid_card", None)
        cores = set(filter_core_types(vc))
        typed = bool(cores & {"Instant", "Sorcery"}) or (
            "Creature" in filter_non_types(vc)
        )
        if typed:
            if cores and cores <= {"Enchantment", "Artifact"}:
                continue
            return True
        preds = set(filter_predicates(vc))
        if (
            cores <= {"Card"}
            and not filter_subtypes(vc)
            and "HasSupertype" not in preds
            and not (preds & _SPELLCAST_TARGET_VETO_PREDS)
        ):
            return True
    return False


# ── arm: spellcast_matters bucket-B (ADR-0036 fold) ───────────────────────────
# The you-cast Spellslinger payoff / build-around (CR 601.2/603.2) has a
# bucket-B tail phase emits NO typed cast node for:
#
#   * a "whenever you cast [or copy] a[n] [noncreature|instant or sorcery|
#     instant and sorcery] spell" trigger left DESCRIPTION-only — inside a
#     granted/quoted ability (Prowess-granting Equipment/tokens — Black
#     Mage's Rod, Circle of Power's Wizard token), an EMBLEM (Chandra, Torch
#     of Defiance; Venser, the Sojourner), or a SAGA chapter (Showdown of the
#     Skalds, Origin of Thor). The narrow insertion-word set structurally
#     excludes a subtype/color-restricted trigger ("an Elf spell", "a black
#     spell", "a Human creature spell") the SAME way the Tier-1 gate's
#     subtype check does — no insertion word for those forms, so the idiom
#     never matches — and a targeted trigger ("spell that targets/shares …"
#     — Heroic, Folk Hero) is vetoed explicitly, matching the structural gate.
#   * a static COST REDUCER ("instant and sorcery spells you cast cost {1}
#     less" — Baral, Goblin Electromancer) and BUILD-AROUND / recursion
#     granter (Lier, Kess, flashback grants, "you may cast … from your
#     graveyard").
#   * a RECASTER/COPIER ("you may cast / copy target instant or sorcery" —
#     Brain in a Jar, Chancellor of the Spires).
#   * a past-tense spell COUNT ("spells you've cast this turn" — Aetherflux
#     Conduit's storm-count, Narset's draw-count) and the delayed "when you
#     next cast an instant or sorcery spell this turn" copy rider (Doublecast,
#     Chandra the Firebrand).
#
# Every family fires ONLY when NO structural spellcast node is present
# (:func:`has_structural_spellcast`), so it never double-counts a card the
# Tier-1 arm already reads. Read PER-CLAUSE (reminder-stripped) so a match is
# confined to ONE clause.
# The optional color/type-adjective word is permitted ONLY when it precedes the
# "instant or sorcery"/"instant and sorcery" anchor — a "red instant or sorcery
# spell" (Jaya, Fiery Negotiator's -8 emblem) is still an I/S Spellslinger
# payoff, merely color-restricted (CR 601.2/603.2). It is deliberately NOT
# permitted before the bare ``spell`` — a color-only "a black spell" (Mountain
# Titan, the Defiler cycle's "black permanent spell") carries no I/S type anchor
# and stays excluded, matching the structural gate's subtype/supertype carve-out.
_SPELLCAST_TRIGGER_RX = re.compile(
    r"whenever you cast(?: or copy)? an? "
    r"(?:noncreature |"
    r"(?:(?:mono|multi)?colou?red |colorless |white |blue |black |red |green )?"
    r"(?:instant or sorcery |instant and sorcery ))?"
    r"spell\b"
    r"(?!\s*(?:that (?:targets|shares)))",
    re.IGNORECASE,
)
_SPELLCAST_BUILDAROUND_RX = re.compile(
    r"instants? (?:and|or) sorcer(?:y|ies)[^.]{0,50}"
    r"(?:flashback|from (?:your |a )?graveyard|cost (?:\{|\d|less)|you may cast)",
    re.IGNORECASE,
)
_SPELLCAST_RECASTER_RX = re.compile(
    r"(?:you may cast|cast target|copy target)[^.]*"
    r"(?:instant or sorcery|instant and sorcery)"
    r"|instant and sorcery (?:spells? )?you (?:may )?cast",
    re.IGNORECASE,
)
_SPELLCAST_COUNT_RX = re.compile(r"spells? you've cast this turn", re.IGNORECASE)
_SPELLCAST_COST_RX = re.compile(
    r"instant and sorcery spells? you cast cost", re.IGNORECASE
)
_SPELLCAST_FROMZONE_RX = re.compile(
    r"cast an instant or sorcery spell from", re.IGNORECASE
)
_SPELLCAST_RIDER_RX = re.compile(
    r"when you (?:next )?cast an instant or sorcery spell this turn",
    re.IGNORECASE,
)


def _matches_spellcast_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B spellcast idiom.

    Per-clause: a genuine (non-subtype, non-targeted) you-cast trigger left
    description-only, a build-around/cost-reducer, a recaster/copier, a
    past-tense spell count, or the delayed next-cast copy rider. CR 601.2.
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if (
            _SPELLCAST_TRIGGER_RX.search(cl)
            or _SPELLCAST_BUILDAROUND_RX.search(cl)
            or _SPELLCAST_RECASTER_RX.search(cl)
            or _SPELLCAST_COUNT_RX.search(cl)
            or _SPELLCAST_COST_RX.search(cl)
            or _SPELLCAST_FROMZONE_RX.search(cl)
            or _SPELLCAST_RIDER_RX.search(cl)
        ):
            return True
    return False


def _arm_spellcast_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``spellcast_matters`` node for a description-only build-around.

    CR 601.2/603.2: fires only when phase carries no typed cast node
    (:func:`has_structural_spellcast`) and the oracle carries a genuine
    bucket-B spellcast idiom (:func:`_matches_spellcast_idiom`). Scope "you"
    (the lane's forced scope for this you-cast payoff).
    """
    if has_structural_spellcast(tree):
        return None
    if not _matches_spellcast_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="spellcast_matters",
        concept="synth_spellcast_matters",
        scope="you",
        subject=(),
        desc="bucket-B spellcast build-around (phase emits no typed cast node)",
    )


def has_permanent_recast(tree: ConceptTree) -> bool:
    """A REPEATABLE engine that re-delivers your own permanents to a
    castable/battlefield zone — the recast-loop pair row's ANCHOR class
    (iteration-3). Three structural arms, probed 2026-07-18:

    * the graveyard-cast permission static (``static_mode_tag`` ==
      ``GraveyardCastPermission`` — Muldrotha's per-type play-from-yard);
    * a trigger whose ``ChangeZone`` puts a graveyard card onto the
      battlefield (destination ``Battlefield`` + an ``InZone(Graveyard)``
      target filter in the unit subtree — Meren's end-step reanimate,
      Sun Titan);
    * an activated ability that bounces your own creatures (``Bounce``
      with a ``controller == You`` target — Chulane's stapled replay).
    """
    for unit in tree.units:
        if unit.origin == "static" and (
            static_mode_tag(unit.node) == "GraveyardCastPermission"
        ):
            return True
        if unit.origin == "trigger":
            for c in unit.effects:
                if (
                    c.concept == "change_zone"
                    and getattr(c.node, "destination", None) == "Battlefield"
                    and _subtree_has_graveyard_zone(unit.node)
                ):
                    return True
        if unit.origin == "ability":
            for c in unit.effects:
                if c.concept == "bounce" and (
                    filter_controller(getattr(c.node, "target", None)) == "You"
                ):
                    return True
    return False


# "Whenever an opponent casts a[n ...] spell" idiom (CR 102.2/102.3 +
# 603.2) — the no-residue class Thundering Mightmare's soulbond-paired
# grant falls into (its ``SourceIsPaired`` static's ``modifications`` is
# a genuinely EMPTY list; phase drops the granted trigger text with no
# node at all, not even an Unimplemented one).
_OPPONENT_CAST_PAYOFF_RE = re.compile(r"\bwhenever an opponent casts\b", re.IGNORECASE)


def has_structural_opponent_cast_matters(tree: ConceptTree) -> bool:
    """The opponent_cast_matters TYPED gate: :func:`is_opponent_cast_trigger_def`
    applied at a top-level trigger unit's own node OR a nested trigger def
    :func:`iter_nested_trigger_defs` reaches inside a GRANTED-ability
    construct (Hunting Grounds's Threshold static grant, Jace, Unraveler
    of Secrets's -8 emblem, Blink's Alien Angel token grant). Shared
    verbatim with the ``_opponent_cast_matters`` lane and this arm's gap
    gate below."""
    for unit in tree.units:
        if unit.origin == "trigger" and is_opponent_cast_trigger_def(unit.node):
            return True
        if any(
            is_opponent_cast_trigger_def(t) for t in iter_nested_trigger_defs(unit.node)
        ):
            return True
    return False


def _arm_opponent_cast_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_cast`` marker for Thundering Mightmare's
    soulbond-paired "Whenever an opponent casts a spell, put a +1/+1
    counter on this creature" — phase's ``SourceIsPaired`` static drops
    the granted trigger text ENTIRELY (``modifications = []``, no node of
    any kind), a no-residue class 2 gap (ADR-0038 amendment). Gap-gated
    on :func:`has_structural_opponent_cast_matters` so a typed/nested
    card never doubles. This key's underlying read is TRIGGER-unit-based
    (not ``effect_concepts``-based like connive/coin_flip/dice), so there
    is no natural "real" phase concept name for a bare trigger shape —
    ``opponent_cast`` is this arm's dedicated marker, read by the lane's
    explicit ``isinstance(c.node, SynthesizedNode)`` check (the
    group_hug_draw precedent for a synthesis-only marker name). CR
    102.2/102.3."""
    if has_structural_opponent_cast_matters(tree):
        return None
    if not _OPPONENT_CAST_PAYOFF_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="opponent_cast_matters",
        concept="opponent_cast",
        scope="opponents",
        subject=(),
        desc="soulbond-granted opponent-cast trigger phase drops entirely",
    )


# "Whenever you cast a[n ...] creature spell" idiom (CR 701.5a / 603.2) —
# the no-residue class most creature_cast_trigger gap cards fall into:
# phase re-templates "whenever you cast a creature spell, that creature
# enters with X counters" as a REPLACEMENT effect on the entering creature
# (a ``valid_card``-filtered ``Moved``/``ChangeZone`` replacement, several
# with a ``SwallowedClause`` parse warning dropping the "cast" qualifier
# down to a bare self-only shape) rather than a genuine ``SpellCast``
# trigger unit or a ``CreateDelayedTrigger`` condition (Glimpse of
# Nature's "this turn" one-shot) — neither shape the flat trigger-unit
# walk nor the granted-trigger descent reaches. The word boundary directly
# before "creature" keeps a NONcreature-spell mention ("cast a noncreature
# spell") from matching (no ``\b`` exists inside "noncreature").
_CREATURE_CAST_RE = re.compile(
    r"\bwhenever you cast (?:a|an)\b.{0,40}?\bcreature spell\b", re.IGNORECASE
)


def has_structural_creature_cast_trigger(tree: ConceptTree) -> bool:
    """The creature_cast_trigger TYPED gate: :func:`is_creature_cast_trigger_def`
    applied at a top-level trigger unit's own node OR a nested trigger def
    :func:`iter_nested_trigger_defs` reaches inside a GRANTED-ability
    construct (Garruk, Caller of Beasts's -7 emblem, Blink's Alien Angel
    token grant). Shared verbatim with the ``_creature_cast_trigger`` lane
    and this arm's gap gate below."""
    for unit in tree.units:
        if unit.origin == "trigger" and is_creature_cast_trigger_def(unit.node):
            return True
        if any(
            is_creature_cast_trigger_def(t) for t in iter_nested_trigger_defs(unit.node)
        ):
            return True
    return False


def _arm_creature_cast_trigger(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``creature_cast`` marker for the "whenever you cast a
    creature spell" idiom phase re-templates as a replacement effect / a
    delayed-trigger condition rather than a readable trigger definition
    (Boreal Outrider, Communal Brewing, Kozilek's Return, Runadi, Behemoth
    Caller, Volo, Itinerant Scholar, Wildgrowth Archaic, Glimpse of
    Nature) — a no-residue class 2 gap (ADR-0038 amendment). Gap-gated on
    :func:`has_structural_creature_cast_trigger` so a typed/nested card
    never doubles. This key's underlying read is TRIGGER-unit-based, not
    ``effect_concepts``-based, matching opponent_cast_matters's mechanism
    — ``creature_cast`` is this arm's dedicated synthesis-only marker,
    read by the lane's explicit ``isinstance(c.node, SynthesizedNode)``
    check. CR 701.5a / 603.2."""
    if has_structural_creature_cast_trigger(tree):
        return None
    if not _CREATURE_CAST_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="creature_cast_trigger",
        concept="creature_cast",
        scope="any",
        subject=(),
        desc="creature-spell-cast trigger phase re-templates unreadably",
    )


# The "one-time boon" mechanic (np_boons task #2, a recent set idiom, no
# dedicated CR number yet — Scryfall rulings gloss it as "a single-use
# triggered ability with no source"): "You get a one-time boon with '<quoted
# delayed trigger>'" (Arcane Archery, Champions of Tyr, March Toward
# Perfection, Tenacious Pup, and ~16 further corpus carriers). phase parses
# the WRAPPER two different ways, neither reachable by the existing
# creature_cast_trigger read: (a) a plain Unimplemented "other" residue
# whose raw is the bare "get a one-time boon with '...'" text (Champions of
# Tyr, Tenacious Pup) — genuinely node-LESS for this purpose (the recovery
# grammar's ALLOWLIST only re-decorates a residue INTO one of its existing
# real concepts; there is no such concept for "grants a delayed one-time
# trigger", so route (i) cannot anchor); (b) a garbled ``S_replacements``
# node (event ``Moved``) whose nested ``execute`` is a bogus ``PutCounter``
# with a GARBAGE ``counter_type`` (a fragment of the quoted text itself,
# not a real counter kind — Arcane Archery, March Toward Perfection,
# Patchplate Resolute, Benalish Knight-Counselor) — a MISPARSE, not a
# correctable field on an otherwise-real placement, so overlay_corrections'
# field-only discipline (no concept rewrites, see that module's own
# docstring) can't serve it either; route (ii) can't anchor. Both shapes are
# genuinely gapped for THIS signal, so route (iv): one shared whole-oracle
# idiom pair, anchored on the literal "one-time boon with \"...\"" wrapper
# (never a blind scan — the match is confined to inside the quoted
# sub-string, so it can't bleed onto an unrelated sibling clause the way a
# raw multi-sentence blob can). Reuses the SAME "creature_cast" marker
# :func:`_arm_creature_cast_trigger` emits (CR 701.5a / 603.2 — a boon that
# watches a creature-spell cast IS that same payoff, just single-use), so
# the existing ``_creature_cast_trigger`` lane serves it with no lane
# change. The `\bcreature spell\b` word boundary (leading AND trailing)
# excludes a "noncreature spell" boon (Valiant Batrider, Illuminating Lash
# — a different watched event entirely) the same way the sibling regex's
# own comment above excludes it.
_BOON_CREATURE_CAST_RE = re.compile(
    r"\bone-time boon with \"[^\"]*?\bwhen you cast (?:a|an)\b"
    r"[^\"]{0,40}?\bcreature spell\b",
    re.IGNORECASE,
)


def _arm_boon_creature_cast_trigger(tree: ConceptTree) -> ConceptNode | None:
    """See :data:`_BOON_CREATURE_CAST_RE`'s module comment. CR 701.5a / 603.2."""
    if has_structural_creature_cast_trigger(tree):
        return None
    if not _BOON_CREATURE_CAST_RE.search(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="boon_creature_cast_trigger",
        concept="creature_cast",
        scope="any",
        subject=(),
        desc="one-time-boon creature-spell-cast trigger, no anchorable node",
    )


# ── arcane_matters direct/bucket-B (ADR-0036/0037 Stage 5) ─────────────────────
# CR 205.3k (Arcane is a spell type) + 702.47a (Splice onto Arcane). A payoff
# naming Arcane spells in a cast-trigger/target filter (Tallowisp, Sideswipe)
# structures as a ``Typed`` filter with subtype "Arcane" — read directly,
# zero regex. Being Arcane-TYPED is NOT itself membership (probed: 66 of 95
# corpus Arcane-typed cards carry no arcane-caring text at all — a plain
# Arcane spell is not a payoff). The genuine bucket-B tail is "Splice onto
# Arcane" itself: phase drops the whole static ability (zero units for
# Glacial Ray) — the ``S_Splice`` mirror type exists but is a dead map row
# (0 corpus nodes, the ``IncreaseSpeed`` precedent) carried anyway for when
# phase starts emitting it.
def has_structural_arcane(tree: ConceptTree) -> bool:
    """Whether phase carries a typed filter naming the Arcane spell subtype
    (a cast-trigger / target payoff — Tallowisp, Sideswipe) or a structured
    ``Splice`` static naming Arcane (dead row today, kept for convergence)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Typed" and "Arcane" in filter_subtypes(n):
                return True
            if tag_of(n) == "Splice" and getattr(n, "subtype", None) == "Arcane":
                return True
    return False


_ARCANE_SYNTH_RX = re.compile(r"\barcane\b", re.IGNORECASE)


def _matches_arcane_idiom(oracle: str) -> bool:
    return bool(_ARCANE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_arcane_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``arcane_matters`` node for the bucket-B "Splice onto
    Arcane" tail phase drops entirely (Glacial Ray, Torrent of Stone, …)."""
    if has_structural_arcane(tree):
        return None
    if not _matches_arcane_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="arcane_matters",
        concept="synth_arcane_matters",
        scope="you",
        subject=(),
        desc="bucket-B Splice onto Arcane (CR 702.47a) phase drops",
    )


# ── batch T4-mechanic-kw: flash_matters bucket-B (full relocation) ──────────
# CR 702.8/702.8a, ADR-0034 branch B: ONLY the opponent-turn cast PAYOFF
# (the bearer/grant makers live in flash_makers/flash_grant, untouched).
# Structural is a TRAP (probed over the commander-legal corpus): phase
# carries ``SpellCast + OnlyDuringOpponentsTurn`` for the plain form
# (Faerie Tauntings) but drops the qualifier entirely on the "first spell"
# form (Alela, Wavebreak Hippocamp — a bare ``NthSpellThisTurn{n:1}``,
# indistinguishable from second_spell_matters) AND over-fires on unrelated
# opponent-turn triggers (Gandalf of the Secret Fire, Breath of the
# Sleepless) — 2 over-fires + 8 misses vs. the mirror's 18-card pop, so no
# competing Tier-1 predicate exists. Relocates the deleted
# ``_FLASH_MATTERS_MIRROR`` verbatim — SOLE source (the poison_matters/
# island_matters no-competing-predicate precedent). Measured byte-identical
# (18/18 union, 0 drops, 0 adds).
_FLASH_MATTERS_SYNTH_RX = re.compile(
    r"whenever you cast (?:a |your first )?spells? "
    r"during (?:an|each|any) opponent",
    re.IGNORECASE,
)


def _matches_flash_matters_idiom(oracle: str) -> bool:
    return bool(_FLASH_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_flash_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``flash_matters`` node (the deleted
    ``_FLASH_MATTERS_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_flash_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="flash_matters",
        concept="synth_flash_matters",
        scope="you",
        subject=(),
        desc="bucket-B opponent-turn cast payoff (CR 702.8/702.8a)",
    )


# ── batch T6-niche-b: ability_copy (full relocation, no gate) ──────────────
# CR 707.10 ("To copy a spell, activated ability, or triggered ability means
# to put a copy of it onto the stack …") + 113.2b: the ability-COPIERS
# (Strionic Resonator, Lithoform Engine, Rings of Brighthearth), the "you may
# copy it" self-copiers (Chancellor of Tales), and the whole-suite importers
# ("has all/the activated abilities of" — Necrotic Ooze, Experiment Kraj).
# LOGGED, not taken: v0.9.0's ``CopySpell`` Effect flattens EVERY copy target
# (ability vs spell) into one undifferentiated category — a
# ``category == "spell_copy"`` arm 90%-OVER-FIRES onto the spell-copy half
# NOT in this lane (Twincast, Fork, Reiterate) while STILL MISSING the
# ability-granters (phase parses "has all activated abilities of" as a
# board-grant, never spell_copy) — no competing Tier-1 predicate exists.
# Relocates the deleted ``_ABILITY_COPY_MIRROR`` verbatim — SOLE source (the
# flash_matters/opponent_exile_matters no-competing-predicate precedent).
# Measured byte-identical over the commander-legal corpus (56/56, 0 drops,
# 0 adds).
_ABILITY_COPY_SYNTH_RX = re.compile(
    r"copy (?:that|this|the|target) "
    r"(?:activated |triggered |activated or triggered )?ability"
    r"|you may copy (?:it|that ability)"
    r"|has all activated abilities of|has the activated abilities of",
    re.IGNORECASE,
)


def _matches_ability_copy_idiom(oracle: str) -> bool:
    return bool(_ABILITY_COPY_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_ability_copy(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``ability_copy`` node (the deleted
    ``_ABILITY_COPY_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_ability_copy_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="ability_copy",
        concept="synth_ability_copy",
        scope="you",
        subject=(),
        desc="bucket-B ability-copy/grant residue (CR 707.10)",
    )


# ── batch T6-niche-b: noncombat_damage_payoff (full relocation, no gate) ───
# CR 510.1a/510.2 (the combat/noncombat damage boundary) + 702.19a (trample
# "… is dealing noncombat damage" — the CR's literal term witness): the
# doublers (Solphim), reflectors (Boros Reckoner, Backfire), and the "deals
# exactly N damage" family. No competing Tier-1 predicate: the ``Double``
# effect's ``target_kind`` enum never carries a ``"Damage"`` member (checked
# against the corpus — only ``Counters``/``LifeTotal``/``ManaPool``/``None``
# occur), and phase leaves the "deals exactly N damage" event-other family an
# Unknown-mode blob (Ghyrson Starn). Relocates the deleted
# ``NONCOMBAT_DAMAGE_PAYOFF_REGEX`` mirror verbatim — SOLE source. Measured
# byte-identical over the commander-legal corpus (97/97, 0 drops, 0 adds).
_NONCOMBAT_DAMAGE_SYNTH_RX = re.compile(
    r"noncombat damage"
    r"|deals that much damage to (?:each opponent|any target|that creature)"
    r"|deals exactly \d+ damage"
    r"|whenever (?:a|another) source you control deals [^.]*damage"
    r"|deals damage equal to (?:that spell's|the exiled card's|that card's"
    r"|that creature's) mana value",
    re.IGNORECASE,
)


def _matches_noncombat_damage_idiom(oracle: str) -> bool:
    return bool(_NONCOMBAT_DAMAGE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_noncombat_damage_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``noncombat_damage_payoff`` node (the deleted
    ``NONCOMBAT_DAMAGE_PAYOFF_REGEX`` mirror relocated verbatim — no
    competing Tier-1 predicate exists, so this is the lane's SOLE
    source)."""
    if not _matches_noncombat_damage_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="noncombat_damage_payoff",
        concept="synth_noncombat_damage_payoff",
        scope="you",
        subject=(),
        desc="bucket-B noncombat-damage doubler/payoff residue (CR 510.2)",
    )


# ── batch T6-niche-b: per_target_payoff (full relocation, no gate) ─────────
# CR 601.2c (targets announced/locked as part of casting) + 601.2f (the
# locked-in total cost): Hinata's YOUR-side per-target cost reduction — corpus
# population exactly 1. [P49] phase parses the ``ModifyCost`` reduction but
# degrades the "for each TARGET" discriminator to an ``ObjectCount`` over an
# EMPTY filter (verified against the committed Hinata fixture: both statics'
# ``dynamic_count.filter`` carry ``type_filters=[]`` — only the node
# ``description`` string retains "for each target", and a node-scoped
# description regex is the Tier-2 waypoint ADR-0036 rejects) — a genuine gap,
# no competing Tier-1 predicate. Relocates the deleted ``_PER_TARGET_RX``
# mirror verbatim — SOLE source. Measured byte-identical (1/1, 0 drops, 0
# adds).
_PER_TARGET_SYNTH_RX = re.compile(
    r"less (?:to cast )?for each (?:of those )?target", re.IGNORECASE
)


def _matches_per_target_idiom(oracle: str) -> bool:
    return bool(_PER_TARGET_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_per_target_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``per_target_payoff`` node (the deleted ``_PER_TARGET_RX``
    mirror relocated verbatim — no competing Tier-1 predicate exists, so
    this is the lane's SOLE source)."""
    if not _matches_per_target_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="per_target_payoff",
        concept="synth_per_target_payoff",
        scope="you",
        subject=(),
        desc="bucket-B per-target cost-reduction residue (CR 601.2c)",
    )


_LESSONS_SYNTH_RX = re.compile(r"\blessons?\b", re.IGNORECASE)
_MIRACLE_GRANT_SYNTH_RX = re.compile(
    r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle", re.IGNORECASE
)


def has_structural_lessons_matter(tree: ConceptTree) -> bool:
    """CR 701.48: a ``{"Subtype": "Lesson"}`` filter anywhere on the card
    (Uncle Iroh's ModifyCost spell_filter, Aang's state-check)."""
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            if any(s.lower() == "lesson" for s in filter_subtypes(node)):
                return True
    return False


def _arm_lessons_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``lessons_matter`` node for the 7-card bare "lesson(s)"
    word residue (Twenty Lessons, …) — the deleted ``_LESSONS_RX`` mirror
    relocated verbatim, gap-gated against
    :func:`has_structural_lessons_matter`."""
    if has_structural_lessons_matter(tree):
        return None
    if not _LESSONS_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="lessons_matter",
        concept="synth_lessons_matter",
        scope="you",
        subject=(),
        desc="bucket-B bare lesson(s) word residue (CR 701.48)",
    )


def has_structural_miracle_grant(tree: ConceptTree) -> bool:
    """CR 702.94: an ``AddKeyword{Miracle}`` modification walk (Lorehold,
    the Historian; Molecule Man)."""
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "AddKeyword" and mod_keyword_name(mod) == "Miracle":
                return True
    return False


def _arm_miracle_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``miracle_grant`` node for the folded-grant residue
    (Aminatou, Veil Piercer; Topdeck the Halls) — the deleted
    ``_MIRACLE_GRANT_RX`` mirror relocated verbatim, gap-gated against
    :func:`has_structural_miracle_grant`."""
    if has_structural_miracle_grant(tree):
        return None
    if not _MIRACLE_GRANT_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="miracle_grant",
        concept="synth_miracle_grant",
        scope="you",
        subject=(),
        desc="bucket-B folded-Miracle-grant residue (CR 702.94)",
    )


# ── T10-finalize2 bucket-B: 8 small tail lanes (ADR-0036/0037 Stage 5) ────────


def _arm_convoke_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``convoke_matters`` node for the cast-spell trigger
    whose convoke qualifier survives only in the trigger's OWN description
    (phase tags a bare cast trigger with no convoke marker) — the deleted
    lane-time ``_CONVOKE_RAW`` scan relocated verbatim. CR 702.51. No
    competing Tier-1 predicate exists (the curse_matters/poison_matters
    no-competing-structural-read precedent), so this is the lane's SOLE
    source, gated only on the unit being a cast_spell trigger — matching
    the deleted lane's own gate exactly (pop == 3: Joyful Stormsculptor,
    Kasla, Saint Traft and Rem Karolus)."""
    for unit in tree.units:
        if unit.trigger_event != "cast_spell":
            continue
        desc = getattr(unit.node, "description", None)
        if isinstance(desc, str) and _CONVOKE_RAW.search(desc):
            return _synthetic_concept(
                arm_id="convoke_matters",
                concept="synth_convoke_matters",
                scope="you",
                subject=(),
                desc="bucket-B convoke_matters cast-trigger qualifier (CR 702.51)",
            )
    return None


def _keyword_soup_unit_text(unit: AbilityUnit) -> str:
    """The granting UNIT's own text (description + effect raws) the
    keyword_soup ``same_true`` absorb arm reads — the deleted lane-time
    join relocated verbatim (reimplemented here, not imported, to avoid a
    crosswalk_signals<->tree_synthesis cycle, the ``_retained_node_texts_
    synth`` precedent)."""
    return " ".join(
        [getattr(unit.node, "description", None) or ""]
        + [c.raw for c in unit.iter_concepts() if c.raw]
    )


def _arm_keyword_soup_same_true(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``keyword_soup`` node for the "same is true" absorb arm
    (CR 702, 205.1b/205.3m vs 702.111a): an evergreen ``AddKeyword`` grant
    or a beneficial evergreen ``place_counter`` site, PLUS the live
    ``_SAME_TRUE_KW_RE`` anchor over the SAME granting unit's own text
    (description + effect raws — never the whole kept oracle) — the
    deleted lane-time join relocated verbatim (Urborg Scavengers, Escaped
    Shapeshifter; Roshan's same-true is scoped to its OWN unit so it never
    absorbs through a different unit's menace grant)."""
    for unit in tree.units:
        unit_text = _keyword_soup_unit_text(unit)
        if not _SAME_TRUE_KW_RE.search(unit_text):
            continue
        kinds: set[str] = set()
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "AddKeyword":
                kw = (mod_keyword_name(mod) or "").replace(" ", "").lower()
                if kw:
                    kinds.add(kw)
        if kinds & _EVERGREEN_CK:
            return _synthetic_concept(
                arm_id="keyword_soup_same_true",
                concept="synth_keyword_soup",
                scope="you",
                subject=(),
                desc="bucket-B keyword_soup same-true absorb, keyword grant (CR 702)",
            )
        if any(
            c.concept == "place_counter"
            and (counter_kind(c.node) or "").replace(" ", "").lower() in _EVERGREEN_CK
            for c in unit.effects
        ):
            return _synthetic_concept(
                arm_id="keyword_soup_same_true",
                concept="synth_keyword_soup",
                scope="you",
                subject=(),
                desc="bucket-B keyword_soup same-true absorb, counter site (CR 702)",
            )
    return None


def _arm_exhaust_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``exhaust_matters`` node for the project raw-anchor
    arm (CR 702.177a/b): the live ``_EXHAUST_TRIG`` marker over a unit's
    own description/effect raws, firing REGARDLESS of trigger event (Pit
    Automaton's delayed-trigger-inside-activated payoff; Elvish Refueler's
    permission static) — the deleted lane-time scan relocated verbatim.
    Gap-gated against the pure-typed ``KeywordAbilityActivated{Exhaust}``
    trigger read the lane keeps Tier-1 (so this arm never duplicates
    Sala)."""
    for unit in tree.units:
        mode = getattr(unit.node, "mode", None)
        if (
            isinstance(mode, MirrorVariant)
            and mode.key == "KeywordAbilityActivated"
            and tag_of(mode.inner) == "Exhaust"
        ):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        for raw in raws:
            if _EXHAUST_TRIG.search(raw):
                return _synthetic_concept(
                    arm_id="exhaust_matters",
                    concept="synth_exhaust_matters",
                    scope="you",
                    subject=(),
                    desc="bucket-B exhaust_matters raw-anchor payoff (CR 702.177)",
                )
    return None


def _becomes_target_src_opp_ctrls(trig: TypedMirrorNode) -> set[str]:
    """The typed controller-string set under a ``BecomesTarget`` trigger's
    ``valid_source`` — the structural half of the src-is-opp derivation,
    extracted so the lane's structural gate and this arm's text-fallback
    gap gate read the SAME set (no drift)."""
    ctrls: set[str] = set()
    vs = getattr(trig, "valid_source", None)
    if isinstance(vs, TypedMirrorNode):
        for node in iter_typed_nodes(vs):
            c = getattr(node, "controller", None)
            if isinstance(c, str) and c:
                ctrls.add(re.sub(r"[^a-z0-9]", "", c.lower()))
    return ctrls


def _arm_becomes_target_src_opp(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``becomes_target_src_opp`` node for the bare
    no-controller ``BecomesTarget`` source whose opponent-restriction
    survives only in the trigger's OWN description (Reality Smasher /
    Swarm Shambler / Tectonic Giant parse gap) — the live
    ``_BECOMES_TARGET_SRC_OPP`` anchor relocated verbatim. Gap-gated:
    skips any trigger whose ``valid_source`` already carries a typed
    controller (the structural case the lane reads directly), so this arm
    covers only the genuine text-only residue. CR 702.21a/108.3."""
    for unit in tree.units:
        if unit.trigger_event != "becomes_target":
            continue
        if _becomes_target_src_opp_ctrls(unit.node):
            continue
        desc = getattr(unit.node, "description", None)
        if isinstance(desc, str) and _BECOMES_TARGET_SRC_OPP.search(desc):
            return _synthetic_concept(
                arm_id="becomes_target_src_opp",
                concept="synth_becomes_target_src_opp",
                scope="you",
                subject=(),
                desc="bucket-B becomes-target opponent-source residue (CR 702.21a)",
            )
    return None


# The etb-bleed sibling concepts recast_etb's serve arm joins on (the live
# categories {discard, lose_life, sacrifice} — crosswalk concept names) —
# moved here from crosswalk_signals (the neutral-home precedent).
_RECAST_BLEED_CONCEPTS: frozenset[str] = frozenset(
    {"discard", "lose_life", "sacrifice"}
)
# The verb-anchored bleed clause for the two shapes phase carries the text
# AWAY from a first-class bleed effect node: a for-each clause dropped to
# ``Unimplemented`` (Bladecoil Serpent — read off that node's own raw), and a
# GRANT-flattened bleed (Lurking Spinecrawler, The Bus Runner) — read off
# the unit's own description with a deep bleed-TAG node as the structural
# anchor (the granted execute's Sacrifice/Discard/LoseLife).
_RECAST_UNIMPL_BLEED_RX = re.compile(
    r"each opponent (?:discards?|loses|sacrifices?)", re.IGNORECASE
)
_RECAST_BLEED_TAGS: frozenset[str] = frozenset({"Discard", "LoseLife", "Sacrifice"})


def _arm_recast_etb_bleed(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``recast_etb`` node for the SERVE arm (CR 702.190/
    118.9): an enters-trigger unit whose text (description + modal
    ``mode_descriptions``) names "each opponent" AND whose sibling effects
    resolve the bleed one of three ways — a native bleed concept
    (discard/lose_life/sacrifice), an ``Unimplemented`` node whose OWN raw
    carries the verb-anchored ``_RECAST_UNIMPL_BLEED_RX`` phrase, or a
    GRANT-flattened bleed (the same phrase on the unit's own text PLUS a
    deep bleed-TAG node under the same unit) — the deleted lane-time join
    relocated verbatim (Burglar Rat, Skirmish Rhino, Baleful Beholder,
    Skemfar Shadowsage, Bladecoil Serpent, Lurking Spinecrawler, The Bus
    Runner). Phase tags only the trigger's CONTROLLER scope, never the
    effect's recipient, so the "each opponent" recipient tell has no
    structural substitute — a genuine bucket-B gap, no competing Tier-1
    predicate. The unit join (etb + bleed in the SAME ability) stays the
    anti-goodstuff point (Wood Elves never fires)."""
    for unit in tree.units:
        if unit.trigger_event != "enters":
            continue
        parts = [getattr(unit.node, "description", None)]
        for node in iter_typed_nodes(unit.node):
            mds = getattr(node, "mode_descriptions", None)
            if isinstance(mds, list):
                parts.extend(m for m in mds if isinstance(m, str))
        text = " ".join(p for p in parts if isinstance(p, str))
        if "each opponent" not in text.lower():
            continue
        native = any(c.concept in _RECAST_BLEED_CONCEPTS for c in unit.effects)
        unimpl = any(
            tag_of(c.node) == "Unimplemented"
            and _RECAST_UNIMPL_BLEED_RX.search(c.raw or "")
            for c in unit.effects
        )
        granted = _RECAST_UNIMPL_BLEED_RX.search(text) and any(
            tag_of(n) in _RECAST_BLEED_TAGS for n in iter_typed_nodes(unit.node)
        )
        if native or unimpl or granted:
            return _synthetic_concept(
                arm_id="recast_etb_bleed",
                concept="synth_recast_etb",
                scope="you",
                subject=(),
                desc="bucket-B recast_etb each-opponent bleed serve (CR 702.190/118.9)",
            )
    return None


# ── cost_reduction bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2;
# ADR-0038 W3 batch 4 widened the walk — see below) ──────────────────────────
# cost_reduction (CR 601.2f/118.7): a static ``ModifyCost{Reduce}`` build-around.
# A ``SelfRef`` ``affected`` filter is the canonical self-discount shape (220/226
# of the "this spell costs" statics, Tier-1 structural — the lane excludes it
# directly, no text). Six residual self-discounts instead parse as a bare
# ``Typed[Card]`` (``spell_filter`` null) — structurally BYTE-IDENTICAL to a
# genuine symmetric reducer (Helm of Awakening), disambiguated ONLY by the
# static's own description ([P8], refined 2026-07-02: Discontinuity,
# Hierophant Bio-Titan). Whole decision relocated here (both branches read
# ONLY the node's own typed fields + its own description, never a
# cross-node/whole-oracle read) so the lane becomes a pure synth-concept read.
#
# ADR-0038 W3 batch 4 (cost_reduction gap close, corpus live_only 62 -> 0):
# widened from a top-level-unit-only scan to a full ``iter_typed_nodes`` deep
# walk over EACH unit, three additions, each still a node-own-field read:
#
#   1. ``ReduceAbilityCost{Reduce}`` (a DISTINCT static mode from
#      ``ModifyCost`` — v0.20.0 gave ACTIVATED-ABILITY cost reducers their own
#      typed mode; Training Grounds/Heartstone's team creature-ability
#      discount, Boom Scholar's "other permanents", Fervent Champion/Cloud's
#      "Equip abilities that target ~", Silver-Fur Master's Ninjutsu,
#      Fluctuator's Cycling). Same direction + SelfRef + description gates as
#      ``ModifyCost``. CR 601.2f/118.7 covers ability-activation costs too
#      (118.7's "cost of a spell, activated ability, or other effect").
#   2. The deep walk ALSO reaches a ``ModifyCost``/``ReduceAbilityCost`` node
#      nested inside a ``GrantStaticAbility.definition`` (Ballad of the Black
#      Flag's Saga chapter IV grants ITSELF a temporary reducer static; Urza,
#      Planeswalker's [+2] does the same) — the granted static's OWN
#      ``affected``/``description`` are read exactly like a top-level one, no
#      new logic, just reachability.
#   3. An ``Unimplemented`` node (phase gave up parsing the clause outright —
#      Will Kenrith's donor "spells that player casts cost {2} less", Cheering
#      Fanatic's chosen-name reducer, Ghostfire Blade/Cosmos Charger/Professor
#      Hojo/Tezzeret's "Static pattern matched but line failed static parser"
#      residue, the "next spell/instant/sorcery you cast" idiom on Elminster/
#      Kaza/Maelstrom Muse/Commander Liara Portyr/Urianger Augurelt) whose OWN
#      ``description`` carries a genuine "cost(s) ... less" reduction and
#      neither a self-discount nor a cost-increase tell — the SAME three
#      textual gates the deleted ``_COST_REDUCER_MIRROR`` used, relocated to a
#      single node's own field (never cross-node/whole-oracle). CR 601.2f/118.7.
_COST_LESS_REDUCER_RE = re.compile(r'\bcosts?\b[^."]{0,40}?\bless\b', re.IGNORECASE)
# The self-discount tell — extended (ADR-0038 W3 batch 4) with "that/the copy
# costs" (God-Eternal Kefnet: "copy that card ... That copy costs {2} less to
# cast" — a ONE-SHOT discount on a single already-created object, the same
# non-build-around shape as "this spell costs", not a persistent CLASS
# reducer; pop-verified False against legacy). CR 601.2f (a genuine
# cost_reduction build-around discounts a CLASS of spells/abilities, not one
# anaphoric single-use copy).
_COST_SELF_DISCOUNT_RE = re.compile(
    r"\bthis spell costs\b|\bthis ability costs\b|\bthis costs\b"
    r"|\b(?:that|the) copy costs\b",
    re.IGNORECASE,
)
_COST_INCREASE_RE = re.compile(
    r"\bcost(?:s)?[^.\"]{0,30}?\b(?:more|an additional)\b|would cost less than",
    re.IGNORECASE,
)
# The impulse/free-cast comparator idiom ("cast the exiled card WITHOUT
# PAYING its mana cost if that spell's mana value is 8 OR LESS" — Breaching
# Dragonstorm, Solstice Revelations, Ryan Sinclair, Rashmi and Ragavan, Pin
# Collection's "ticket cost X or less ... without paying that sticker's
# ticket cost", Bre of Clan Stoutarm): the "cost"/"less" tokens both appear,
# but "less" is a THRESHOLD on the exiled card's mana VALUE, never a
# reduction of what you pay — pop-verified False against legacy (8-card
# corpus over-fire, ADR-0038 W3 batch 4). "It costs ... this way" (Uvilda,
# Dean of Perfection's "It costs {4} less to cast this way" granted
# ability — SINGULAR "it", the SAME one-shot-object-discount family as
# "that copy costs" above, a delayed/impulse cast of ONE already-exiled
# card) is excluded too, but NARROWLY: the pronoun must be "it", not a
# CLASS noun — "Spells you cast this way cost {2} less to cast" (Urianger
# Augurelt's Play Arcanum, a genuine persistent build-around over every
# card exiled with it) does NOT match and correctly still fires.
_COST_FREE_CAST_RE = re.compile(
    r"without paying|\bit costs?\b[^.\"]*?\bthis way\b",
    re.IGNORECASE,
)


def _cost_reducer_node_ok(desc: str) -> bool:
    """Whether a node's OWN description is a genuine "costs ... less"
    reduction (not a self-discount, not a cost-increase, not a free-cast
    mana-value comparator). The gates the deleted ``_COST_REDUCER_MIRROR``
    applied, node-scoped, plus the ADR-0038 W3 batch 4 free-cast exclusion."""
    return bool(
        desc
        and _COST_LESS_REDUCER_RE.search(desc)
        and not _COST_SELF_DISCOUNT_RE.search(desc)
        and not _COST_INCREASE_RE.search(desc)
        and not _COST_FREE_CAST_RE.search(desc)
    )


def _arm_cost_reduction(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``cost_reduction`` node (CR 601.2f/118.7): a
    ``ModifyCost{Reduce}`` OR ``ReduceAbilityCost{Reduce}`` static ANYWHERE
    under a unit (including nested inside a ``GrantStaticAbility.definition``)
    whose ``affected`` is not ``SelfRef`` and whose OWN description does not
    carry the self-discount tell ("this spell/ability costs" — Discontinuity,
    Hierophant Bio-Titan's symmetric residual shape); falling back to ANY
    node (typically ``Unimplemented`` — phase gave up parsing the clause —
    but also a malformed ``CreateEmblem``/``GrantStaticAbility`` static whose
    OWN description embeds the raw clause, Saheeli Filigree Master's -4
    emblem) whose OWN description is a genuine "costs ... less" reducer.
    Node-own-field/description reads only, no cross-node text.
    """
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            mt = static_mode_tag(node)
            if mt == "ModifyCost":
                inner_mode = modify_cost_mode(node)
            elif mt == "ReduceAbilityCost":
                inner_mode = static_mode_field(node, "mode")
            else:
                continue
            if inner_mode != "Reduce":
                continue
            if tag_of(getattr(node, "affected", None)) == "SelfRef":
                continue
            desc = (getattr(node, "description", None) or "").lower()
            if "this spell costs" in desc or "this ability costs" in desc:
                continue
            return _synthetic_concept(
                arm_id="cost_reduction",
                concept="synth_cost_reduction",
                scope="you",
                subject=(),
                desc="bucket-B static spell/ability-cost reducer (CR 601.2f/118.7)",
            )
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            desc = getattr(node, "description", None)
            if not isinstance(desc, str):
                continue
            if _cost_reducer_node_ok(desc):
                return _synthetic_concept(
                    arm_id="cost_reduction",
                    concept="synth_cost_reduction",
                    scope="you",
                    subject=(),
                    desc="bucket-B Unimplemented cost-reducer residue "
                    "(CR 601.2f/118.7)",
                )
    return None


# ── bending_cross bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ────
# CR 701.65a airbend / 701.66a earthbend / 701.67a waterbend: the
# ``RegisterBending`` node's own typed ``kind`` field ("Air"/"Earth") and the
# Waterbend cost-leaf TAG are both fully structural (no text needed — the
# lane reads them directly). The sole residual is the ``ElementalBend``
# TRIGGER mode (Avatar Aang's cross-bend payoff), which carries NO
# per-element typed payload — a genuine bucket-B gap, disambiguated only by
# which bend word(s) the trigger's own description names.
def _bend_trigger_mode_tag(unit: AbilityUnit) -> str | None:
    """A trigger unit's RAW phase mode tag (plain string or variant key)."""
    mode = getattr(unit.node, "mode", None)
    return mode if isinstance(mode, str) else tag_of(mode)


def _arm_bending_cross(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``bending_cross`` node for the ``ElementalBend`` trigger
    residual: a TUPLE of the bend word(s) ("airbend"/"earthbend"/
    "waterbend") the trigger's OWN description names, structurally gated on
    the ``ElementalBend`` mode tag itself (the mechanic must genuinely be
    present) — the deleted lane-time per-unit text route relocated here.
    """
    for unit in tree.units:
        if unit.origin != "trigger" or _bend_trigger_mode_tag(unit) != "ElementalBend":
            continue
        desc = (getattr(unit.node, "description", None) or "").lower()
        found = tuple(
            sorted({w for w in ("airbend", "earthbend", "waterbend") if w in desc})
        )
        if found:
            return _synthetic_concept(
                arm_id="bending_cross",
                concept="synth_bending_cross",
                scope="you",
                subject=found,
                desc="bucket-B ElementalBend cross-bend payoff residual "
                "(CR 701.65a/701.66a/701.67a)",
            )
    return None


# ── cheat_into_play grammar-sprint closers (ADR-0039 task #82) ─────────────────
# Three residual bridge_ledger.py rows (cheat_into_play's LAST grammar
# stragglers) each swallow a "put ... onto the battlefield" chain into an
# Unimplemented residue phase's clause grammar can't yet structure: a leading
# player-referent clause ahead of the real imperative, a "choose ... from
# among them" selection step paired with a phase-mistagged Graveyard origin
# on its sibling put, and a delayed-trigger reveal-until node recovered to
# concept ``reveal_until`` but missing a typed ``kept_destination``. All three
# are corpus-verified narrow (bridge_ledger.py's own census, phase v0.20.0,
# 2026-07-11); each arm below PORTS the exact verbatim regex the retired
# bridge used (not a new, wider pattern) so membership is provably unchanged
# — a synthesis arm, not a widened one. One shared marker concept
# (``synth_cheat_reveal_or_put_battlefield``) since all three feed the SAME
# terminal ``cheat_into_play`` read (CR 110.2/400.7) and no other lane needs
# to distinguish them.
_CHEAT_PLAYER_PREFIX_SYNTH_RX = re.compile(
    r"^(?:"
    r"for each of those \w+, (?:its controller|you may put)|"
    r"who (?:received no votes may put|"
    r"sacrificed a permanent this way reveals|"
    r"shuffled a nontoken creature into their library this way reveals)|"
    r"you do the same with the top three cards of your library"
    r")",
    re.IGNORECASE,
)


def _arm_cheat_player_prefix_battlefield_put(tree: ConceptTree) -> ConceptNode | None:
    """A leading referent/relative-clause ahead of the real imperative
    ("its controller reveals...", "who received no votes may put...", "you
    do the same with...") defeats phase's clause grammar, parking the WHOLE
    clause as an ``Unimplemented`` residue (Divergent Transformations,
    Círdan the Shipwright, Vaevictis Asmadi the Dire, Collision of Realms,
    Guild Feud, Liberated Livestock). Tree-wide "onto the battlefield" gate
    excludes Soul of Emancipation's same leading shape (a token maker, no
    battlefield put at all — CR 110.2/400.7). bridge_ledger.py's retired
    ``cheat_player_prefix_battlefield_put`` row."""
    if "onto the battlefield" not in (tree.oracle or "").lower():
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Unimplemented":
                continue
            desc = getattr(n, "description", "") or ""
            if _CHEAT_PLAYER_PREFIX_SYNTH_RX.search(desc):
                return _synthetic_concept(
                    arm_id="cheat_player_prefix_battlefield_put",
                    concept="synth_cheat_reveal_or_put_battlefield",
                    scope="you",
                    subject=(),
                    desc="leading player-referent clause swallows a "
                    "battlefield put (CR 110.2/400.7)",
                )
    return None


def _arm_cheat_choose_from_among_graveyard_origin(
    tree: ConceptTree,
) -> ConceptNode | None:
    """A swallowed "choose a [type] card from among them" selection step
    (Unimplemented, description containing "from among them") whose sibling
    Battlefield put carries ``origin: 'Graveyard'`` — a phase-side origin
    MIS-TAG (the real source is the just-revealed LIBRARY pile, CR 400.7
    zones don't reorder themselves), which the typed ``cheat_into_play``
    reanimation carve-out correctly-but-wrongly excludes (Animal Magnetism,
    Selective Adaptation). bridge_ledger.py's retired
    ``cheat_choose_from_among_graveyard_origin`` row (its own census: the
    ONLY two commander-legal cards pairing this Unimplemented shape with a
    Graveyard-origin Battlefield ChangeZone in the same tree — Guided
    Passage / Manifold Insights / Kaya's Spirit's Justice / Capricious
    Hellraiser / Green Sun's Twilight share the "choose... from among them"
    shape but carry no Battlefield-destined node at all)."""
    has_choose = any(
        "choose" in desc.lower() and "from among them" in desc.lower()
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
        if tag_of(n) == "Unimplemented"
        for desc in (getattr(n, "description", "") or "",)
    )
    if not has_choose:
        return None
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) in ("ChangeZone", "ChangeZoneAll")
                and getattr(n, "destination", None) == "Battlefield"
                and getattr(n, "origin", None) == "Graveyard"
            ):
                return _synthetic_concept(
                    arm_id="cheat_choose_from_among_graveyard_origin",
                    concept="synth_cheat_reveal_or_put_battlefield",
                    scope="you",
                    subject=(),
                    desc="choose-from-among-them selection paired with a "
                    "phase-mistagged Graveyard-origin battlefield put "
                    "(CR 400.7)",
                )
    return None


_CHEAT_SYNTHETIC_DESTINY_SYNTH_RX = re.compile(
    r"reveal cards from the top of your library until you reveal that "
    r"many creature cards, put all creature cards revealed this way onto "
    r"the battlefield",
    re.IGNORECASE,
)


def _arm_cheat_synthetic_destiny_delayed_reveal(
    tree: ConceptTree,
) -> ConceptNode | None:
    """Synthetic Destiny's delayed-trigger reveal-until node: the recovery
    stage already re-decorates this ``Unimplemented`` node with concept
    ``reveal_until`` (its raw text names the idiom), but the raw ``.node``
    itself carries no typed ``kept_destination`` field, so the typed
    ``cheat_into_play`` RevealUntil arm can never read a destination off
    it. Anchored to the card's own verbatim idiom (corpus-verified sole
    hit). bridge_ledger.py's retired
    ``cheat_synthetic_destiny_delayed_reveal`` row."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Unimplemented" or getattr(n, "name", None) != "reveal":
                continue
            desc = getattr(n, "description", "") or ""
            if _CHEAT_SYNTHETIC_DESTINY_SYNTH_RX.search(desc):
                return _synthetic_concept(
                    arm_id="cheat_synthetic_destiny_delayed_reveal",
                    concept="synth_cheat_reveal_or_put_battlefield",
                    scope="you",
                    subject=(),
                    desc="delayed-trigger reveal-until node has no typed "
                    "kept_destination field (CR 701.20a)",
                )
    return None
