"""Card-type and tribal (keyword/creature-type) bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    color_count_preds,
    count_operand_filter,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_keywords,
    filter_subtypes,
    has_filter_property,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_static_defs,
    iter_typed_nodes,
    mana_restricted_to_multicolored,
    modify_cost_spell_filter,
    protection_cardtype,
    ref_count_filter,
    tag_of,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge._sweep_detectors import (
    ANIMATE_ARTIFACT_REGEX,
    COLOR_CHANGE_REGEX,
    ISLAND_MATTERS_REGEX,
    VEHICLES_MATTER_REGEX,
)
from mtg_utils._deck_forge.signal_base import (
    _resolve_subject,
    clauses,
)
from mtg_utils._deck_forge.text_reads import (
    _ABILITY_KEYWORDS,
    _TYPED_ANTHEM_MULTI_RAW,
    _detect_keyword_implied_tribe,
    _detect_keyword_tribe,
    _detect_multi_tribe_anthem,
    _detect_type_matters,
    _detect_typed_gy_recursion,
    _type_hoser_clause,
)

# ── type_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_type_matters_lane`` reads TWO structural sources: the creature
# subtype of every non-opponent Typed filter phase carries at an effect subject /
# count-operand / trigger valid_card / static affected / condition site (Arm B —
# :func:`structural_type_subjects`), and the SUBJECT-carrying bucket-B synth node
# (:func:`_arm_type_matters`). type_matters is the FIRST subject-carrying synth arm:
# the synth node holds a TUPLE of resolved creature subtypes (Lovisa → Barbarian /
# Warrior / Berserker), and the lane emits one Signal per element. The gap gate is
# per-SUBJECT (the gap-gate-alignment invariant applied to subjects): the synth adds
# only the subtypes phase's Typed filters MISS, reading the SAME Arm-B set the lane
# fires on — one source, no drift, never double-counting a subtype phase types.


def structural_type_subjects(tree: ConceptTree) -> set[str]:
    """Creature subtypes of every non-opponent Typed filter phase carries at a read
    site the ``_type_matters_lane`` fires on (CR 205.3 kindred — Arm B).

    The Arm-B source SHARED by the lane AND this stage's per-subject gap gate
    (:func:`_arm_type_matters`) — one source, no drift. A Typed filter controlled by
    an Opponent is not a your-tribe payoff (CR 109.3) and is skipped; each subtype is
    vocab-resolved through ``_resolve_subject`` (the ``NON_CREATURE_TOKEN`` /
    ``CARD_TYPE_SUBJECTS`` denylist — CR 111.10 / 205.3g), so a Treasure / Clue token
    subtype or a bare "creature" / "permanent" never mints a kindred subject.

    ADR-0038 W4: the static-def read is :func:`iter_static_defs`, not a bare
    ``unit.origin == "static"`` gate — a temporary "until end of turn" anthem
    a TRIGGER's effect confers (``GenericEffect.static_abilities`` — "When you
    cycle this card, Wizard creatures gain flying until end of turn.") nests
    its ``affected`` Typed filter on the INNER static-ability def, not on the
    trigger unit's own node, and the decorated concept's anchor is the leaf
    modification (``AddKeyword``/``AddPower``), which carries no filter field
    at all. ``iter_static_defs`` walks to the real def (cycle-safe, yields the
    unit node itself when IT is a def, so a top-level static ability is still
    covered — a strict superset of the old gate, never a narrowing).

    ADR-0038 W5 tails: also reads ``unit.costs`` (role=cost) the SAME way as
    ``unit.effects`` — an "as an additional cost to cast this spell,
    sacrifice a Goblin" (Goblin Grenade, Goblin Barrage, Fodder Launch) or
    "you may sacrifice any number of Spirits" (Devouring Greed/Rage) additional
    cost carries its subtype on the ``Sacrifice`` cost node's own ``target``
    filter (``effect_filter`` reads ``target`` — CR 601.2h "locked in" costs /
    701.21 sacrifice), which the old effects-only scan never reached (a
    cost-shaped node, not an effect). Mirrors legacy's ``_kindred_subjects(
    e.subject, vocab)`` read, which never distinguished cost- from
    effect-shaped Effects in the old IR's flat ``ab.effects`` walk.

    Also scans each static-def's own ``modifications`` list for a nested
    COUNT-OPERAND filter (``count_operand_filter`` — the SAME "value" field
    name the modification tag uses, e.g. ``AddDynamicPower.value``): "gets
    +1/+1 for each Dwarf, Equipment, and/or Vehicle you control" (Bearded
    Axe) carries its ``Or``-of-subtypes filter (``filter_subtypes`` already
    recurses ``Or``/``And``) on the leaf modification's OWN value, not the
    static-def's ``affected`` field (which stays the GENERIC "equipped
    creature" — CR 301.5c).

    Two more nested-descent sites (ADR-0038 W5 tails), both reusing shared
    helpers rather than re-implementing them:
    a **GrantAbility**'s own ``.definition.effect`` (:func:`effect_filter`
    over each ``iter_typed_nodes``-reached ``GrantAbility`` node, the SAME
    idiom :func:`has_structural_power_tap_engine` uses) — "Equipped
    creature has '{T}: ~ deals 1 damage to any target' and '{T}: ~ deals 3
    damage to target Werewolf creature.'" (Wolfhunter's Quiver) carries its
    tribal subject on the SECOND granted ability's own target, not on the
    static's ``affected`` (the generic "equipped creature" anchor, CR
    301.5c) or its top-level ``modifications`` (the grant tag itself
    carries no filter field);
    a **ModifyCost** static mode's ``spell_filter``
    (:func:`modify_cost_spell_filter` — the SAME shared reader
    ``_typed_spellcast``'s static arm already uses for a single-tribe cost
    reducer): "Cleric, Rogue, Warrior, and Wizard spells you cast cost {1}
    less to cast." (The Destined Warrior) carries its FOUR-tribe ``Or``
    list here, not on ``affected`` (a bare Card-type filter with no
    subtype at all — CR 601.2f).

    Safe by construction: ``add_filter`` only ever adds a SUBTYPED filter
    (empty-subtype hits produce nothing), so none of these three additions
    can open the generic go-wide membership floor's false-positive class
    (CR 205.3/613.4c).

    The effects/costs count-operand read also tries :func:`ref_count_filter`
    (a STRICT superset of :func:`count_operand_filter` — it additionally
    unwraps a ``Multiply``-scaled ``amount``/``count``/``value``): "This
    creature enters with two +1/+1 counters on it for each other nontoken
    Human you control." (Hamlet Vanguard) carries its Human subtype on a
    ``PutCounter`` whose ``count`` is ``Multiply(factor=2, inner=Ref(
    ObjectCount(filter=Typed(Subtype:Human))))`` — the bare ``Ref`` tag
    check in :func:`count_operand_filter` never unwraps the "twice that
    many" scalar, so this doubled-count kindred subject was missed.
    """
    out: set[str] = set()

    def add_filter(filt: object) -> None:
        if filt is None or filter_controller(filt) == "Opponent":
            return
        for s in filter_subtypes(filt):
            r = _resolve_subject(s, CREATURE_SUBTYPES)
            if r:
                out.add(r)

    def add_ref_count_filter(node: TypedMirrorNode) -> None:
        for fname in ("amount", "count", "value"):
            add_filter(ref_count_filter(node, fname))

    for unit in tree.units:
        for c in unit.effects:
            add_filter(count_operand_filter(c.node))
            add_ref_count_filter(c.node)
            if c.concept != "make_token":
                add_filter(effect_filter(c.node))
        for c in unit.costs:
            add_filter(count_operand_filter(c.node))
            add_ref_count_filter(c.node)
            add_filter(effect_filter(c.node))
        if unit.origin == "trigger":
            add_filter(getattr(unit.node, "valid_card", None))
        for static_def in iter_static_defs(unit.node):
            add_filter(getattr(static_def, "affected", None))
            add_filter(modify_cost_spell_filter(static_def))
            for mod in getattr(static_def, "modifications", None) or ():
                add_filter(count_operand_filter(mod))
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            eff = getattr(d, "effect", None) if d is not None else None
            if isinstance(eff, TypedMirrorNode):
                add_filter(effect_filter(eff))
        for cond in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(cond):
                if tag_of(q) == "Typed":
                    add_filter(q)
    return out


# ── arm: type_matters bucket-B (ADR-0036 fold — SUBJECT-carrying) ─────────────
# The kindred payoff (CR 205.3) has a bucket-B tail phase leaves SUBJECT-less: a
# TYPE-GRANT ("it's a Zombie in addition to its other creature types" — phase emits a
# type-change effect, NOT a subject-bearing Typed filter), a KEYWORD-implied tribe
# (ninjutsu → Ninja, CR 702.49), a MULTI-TRIBE anthem/list where phase collapses the
# list or emits no per-subtype filter (Lovisa's "each creature that's a Barbarian, a
# Warrior, or a Berserker"; the Spider-Ham menagerie run), two-tribe heads / creature-
# spell / tutor + comma card-lists where phase drops the subtype, and description-only
# tribal triggers / cost-site / count / cost-reducer / tribal-tutor forms. The four
# kept-oracle producers (imported from ``text_reads.py`` — the surviving mirror
# defs, SHARED never re-implemented) capture each subtype through the SAME
# ``_resolve_subject`` vocab gate; Vehicle routes to ``vehicles_matter`` (a different
# lane), so the TYPE_MATTERS-key filter drops it here.


_COPY_EXCEPTION_RX = re.compile(r"\bas a copy of\b[^.]*\bexcept\b", re.IGNORECASE)


def _mirror_type_subjects(oracle: str) -> set[str]:
    """Every creature subtype the four kept-oracle tribal producers capture, per
    reminder-stripped clause (the bucket-B tribal idioms — CR 205.3).

    Reads ``oracle`` reminder-stripped and clause-split (the SAME text the flag-OFF
    lane mirror scanned via ``_kept`` — ``_REMINDER`` matches ``crosswalk_signals``'s
    ``_REMINDER_RX``), so this reproduces the deleted lane mirror exactly. Only the
    ``TYPE_MATTERS`` rows of ``_detect_typed_gy_recursion`` are taken (Vehicle →
    ``vehicles_matter`` is a different lane).
    """
    subs: set[str] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        # A copy-exception rider ("enter as a copy of ... except it's a Bird
        # in addition to its other types") is SELF-directed — CR 707.9d: the
        # exception modifies the COPY's own characteristics. That is
        # membership (the type line already carries it), never a kindred
        # payoff; captured here it fed the emerging-tribal payoff gate a
        # phantom Bird payoff (Mockingbird, the Sliver benchmark).
        if _COPY_EXCEPTION_RX.search(cl):
            continue
        for _k, s in _detect_type_matters(cl, CREATURE_SUBTYPES):
            subs.add(s)
        for _k, s in _detect_multi_tribe_anthem(cl, CREATURE_SUBTYPES):
            subs.add(s)
        for _k, s in _detect_keyword_implied_tribe(cl):
            subs.add(s)
        for key, _sc, s in _detect_typed_gy_recursion(cl, CREATURE_SUBTYPES):
            if key == signal_keys.TYPE_MATTERS:
                subs.add(s)
    return subs


def _arm_type_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a SUBJECT-carrying ``type_matters`` node for bucket-B tribal gaps.

    CR 205.3: the four kept-oracle producers (:func:`_mirror_type_subjects`) capture
    a kindred subtype phase leaves subject-less; the node carries a TUPLE of ONLY the
    subtypes phase's Typed filters MISS — per-SUBJECT gap-gated against
    :func:`structural_type_subjects` (the SAME Arm-B set the lane fires on, so gate
    and lane never disagree). The lane emits one ``type_matters`` Signal per element
    of ``node.subject``. Returns None when phase already structuralizes every captured
    subtype (nothing new to add).
    """
    new = _mirror_type_subjects(tree.oracle or "") - structural_type_subjects(tree)
    if not new:
        return None
    return _synthetic_concept(
        arm_id="type_matters",
        concept="synth_type_matters",
        scope="you",
        subject=tuple(sorted(new)),
        desc="bucket-B tribal payoff (phase emits no subject-bearing Typed filter)",
    )


# ── keyword_tribe structural reads (ADR-0036 fold — shared lane/gate source) ──
# The KEYWORD analog of type_matters (CR 109.3 / 702): a payoff/reference that CARES
# about creatures WITH an ability keyword (Favorable Winds' "creatures you control with
# flying get +1/+1"; Winged Portent's "for each creature you control with flying"; Odric
# sharing keywords across your board). The SUBJECT is the capitalized ability keyword.
# The Tier-1 ``_keyword_tribe`` lane reads TWO structural sources: the keyword of every
# controller-``You`` ``WithKeyword`` filter phase carries at an effect subject /
# count-operand / trigger valid_card / static affected / condition site (Arm B —
# :func:`structural_keyword_subjects`, scope "you"), and the SUBJECT-carrying bucket-B
# synth nodes (:func:`_arm_keyword_tribe` / :func:`_arm_keyword_tribe_any`). Like
# type_matters the synth node holds a TUPLE of resolved keywords and the lane emits one
# Signal per element, per-KEYWORD gap-gated against the SAME Arm-B set — one source, no
# drift, never double-counting a keyword phase structuralizes.


def structural_keyword_subjects(tree: ConceptTree) -> set[str]:
    """Ability keywords of every controller-``You`` ``WithKeyword`` filter phase
    carries at a read site the ``_keyword_tribe`` lane fires on (CR 109.3 — Arm B).

    The Arm-B source SHARED by the lane AND this stage's per-keyword gap gate
    (:func:`_arm_keyword_tribe`) — one source, no drift. Only a controller-``You``
    filter is a your-tribe payoff (a bare / opponent-controlled ``WithKeyword`` is a
    keyword hoser or removal target — "destroy target creature with flying" — not a
    tribe payoff, CR 702; the mirror required a "you control" / anthem context, so we
    require ``controller == "You"``). The ``sacrifice`` effect concept is skipped:
    phase tags an EDICT ("each opponent sacrifices a creature with flying" — Clip
    Wings, Pick Your Poison) with a spurious controller-``You`` target, but the
    sacrificed creature is the opponent's — anti-flyer removal, not a your-tribe
    payoff (the ``make_token`` carve-out precedent). Each keyword is vocab-gated
    through ``_ABILITY_KEYWORDS`` (the precision gate — a non-keyword word yields no
    subject) and returned capitalized.
    """
    out: set[str] = set()

    def add_filter(filt: object) -> None:
        if filt is None or filter_controller(filt) != "You":
            return
        for k in filter_keywords(filt):
            if k.lower() in _ABILITY_KEYWORDS:
                out.add(k.lower().capitalize())

    for unit in tree.units:
        for c in unit.effects:
            add_filter(count_operand_filter(c.node))
            if c.concept not in ("make_token", "sacrifice"):
                add_filter(effect_filter(c.node))
        if unit.origin == "trigger":
            add_filter(getattr(unit.node, "valid_card", None))
        if unit.origin == "static":
            add_filter(getattr(unit.node, "affected", None))
        for cond in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(cond):
                if tag_of(q) == "Typed":
                    add_filter(q)
    return out


# ── arm: keyword_tribe bucket-B (ADR-0036 fold — SUBJECT-carrying, per-scope) ──
# The keyword-tribe payoff (CR 109.3 / 702) has a bucket-B tail phase leaves keyword-
# less: a keyword TUTOR (Isperia — "search your library for a creature card with
# flying"; phase emits no WithKeyword-bearing search filter), a play-from-top engine
# gated on a keyword (Errant and Giada), a symmetric anthem ("creatures with flying
# get +1/+1" — controller-less, so Arm B misses it), and granted-fly riders. The
# pinned kept-oracle producer (:func:`_detect_keyword_tribe`, imported from
# ``text_reads.py`` — the surviving mirror, SHARED never re-implemented)
# captures each keyword through the SAME ``_ABILITY_KEYWORDS`` vocab gate and carries
# the mirror's per-clause scope
# ("you" for your-tribe references / tutors; "any" for symmetric anthems). Two arms keep
# the two scopes distinct (the diff keys on scope) — the "you" arm is per-keyword
# gap-gated against :func:`structural_keyword_subjects` (Arm B, scope "you"); the "any"
# arm has no Arm-B counterpart (Arm B only reads controller-``You``), so it fires
# ungated. Both emit the ``synth_keyword_tribe`` concept; the lane reads ``node.scope``.


def _keyword_tribe_pairs(oracle: str) -> set[tuple[str, str]]:
    """Every ``(scope, keyword)`` the kept-oracle keyword-tribe producer captures, per
    reminder-stripped clause (CR 109.3 / 702).

    Reads ``oracle`` reminder-stripped and clause-split (the SAME text the flag-OFF lane
    mirror scanned via ``_kept`` — ``_REMINDER`` matches ``crosswalk_signals``'s
    ``_REMINDER_RX``), so this reproduces the deleted lane mirror exactly.
    """
    out: set[tuple[str, str]] = set()
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        for _k, scope, kw in _detect_keyword_tribe(cl):
            out.add((scope, kw))
    return out


def _keyword_tribe_scoped(tree: ConceptTree) -> tuple[set[str], set[str]]:
    """``(you_keywords, any_keywords)`` for the keyword-tribe synth, gap-gated.

    The "you"-scope keywords are per-keyword gap-gated against
    :func:`structural_keyword_subjects` (the SAME Arm-B set the lane fires on, so gate
    and lane never disagree); the "any"-scope keywords (symmetric anthems) have no Arm-B
    counterpart and pass through ungated.
    """
    struct = structural_keyword_subjects(tree)
    you: set[str] = set()
    anyk: set[str] = set()
    for scope, kw in _keyword_tribe_pairs(tree.oracle or ""):
        if scope == "you":
            if kw not in struct:
                you.add(kw)
        else:
            anyk.add(kw)
    return you, anyk


def _arm_keyword_tribe(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a scope-``you`` ``keyword_tribe`` node for bucket-B keyword gaps.

    Carries a TUPLE of ONLY the your-tribe keywords phase's ``WithKeyword`` filters
    MISS — per-keyword gap-gated against :func:`structural_keyword_subjects` (the SAME
    Arm-B set the lane fires on). Returns None when phase already structuralizes every
    captured keyword.
    """
    you, _anyk = _keyword_tribe_scoped(tree)
    if not you:
        return None
    return _synthetic_concept(
        arm_id="keyword_tribe",
        concept="synth_keyword_tribe",
        scope="you",
        subject=tuple(sorted(you)),
        desc="bucket-B keyword-tribe payoff (phase emits no WithKeyword filter)",
    )


def _arm_keyword_tribe_any(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a scope-``any`` ``keyword_tribe`` node for symmetric keyword anthems
    ("creatures with flying get +1/+1" — controller-less, so Arm B never sees it; CR
    702). No structural counterpart exists at scope "any", so it fires ungated."""
    _you, anyk = _keyword_tribe_scoped(tree)
    if not anyk:
        return None
    return _synthetic_concept(
        arm_id="keyword_tribe_any",
        concept="synth_keyword_tribe",
        scope="any",
        subject=tuple(sorted(anyk)),
        desc="bucket-B symmetric keyword anthem (controller-less WithKeyword)",
    )


def _has_multicolor_count_pred(filt: object) -> bool:
    """Whether ``filt`` carries a ``ColorCount`` ``GE``/``EQ`` >= 2
    predicate, controller You (CR 105.2) — the shared discriminant both
    :func:`has_structural_multicolor_matters` and the
    ``_predicate_build_around`` lane's multicolor arm apply."""
    if filter_controller(filt) != "You":
        return False
    return any(
        (cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)
        for cmp_, cnt in color_count_preds(filt)
    )


def has_structural_multicolor_matters(tree: ConceptTree) -> bool:
    """The multicolor_matters TYPED gate (CR 105.2): a ``ColorCount``
    GE/EQ >= 2 predicate on an effect / count-operand / static-affected /
    trigger-subject filter (Knight of New Alara), OR a ``Mana`` effect's
    ``SpellType: Multicolored`` spend restriction (Obsidian Obelisk).
    Mirrors the checks ``crosswalk_signals._predicate_build_around``'s
    multicolor arm runs, so the color-pair-reference synthesis arm below
    never fires on a card the typed read already covers."""
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        if mana_restricted_to_multicolored(c.node):
            return True
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is not None and _has_multicolor_count_pred(filt):
                return True
    for unit in tree.units:
        if unit.statics:
            aff = getattr(unit.node, "affected", None)
            if aff is not None and _has_multicolor_count_pred(aff):
                return True
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) is None:
            continue
        ctrl = filter_controller(vc)
        you = ctrl == "You" or (ctrl is None and trigger_scope(unit.node) == "you")
        if you and any(
            (cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)
            for cmp_, cnt in color_count_preds(vc)
        ):
            return True
    return False


# multicolor cares-about REFERENCE idiom phase drops the "multicolored"
# qualifier from entirely (Fallaji Wayfarer's granted-keyword affected filter
# carries no ColorCount predicate at all — the word survives only in the
# static's description) or parks on an Unimplemented node whose PARSEABLE
# verb ("choose") discards the "for each color pair" prefix that carries the
# actual cares-about content (Niv-Mizzet Reborn). Mirrors the deleted
# _signals_ir word-mirror's "for each color pair" / "exactly those colors" /
# "multicolored (creature/permanent/spell)s? you" alternatives verbatim (the
# "cast a multicolored" alternative is intentionally OMITTED — that idiom is
# now covered STRUCTURALLY by has_structural_multicolor_matters's Mana-
# restriction arm, so the synthesis fallback never needs it). CR 105.2.
_MULTICOLOR_REFERENCE_RE = re.compile(
    r"for each color pair|exactly those colors"
    r"|multicolored (?:creature|permanent|spell)s? you",
    re.IGNORECASE,
)


def _arm_multicolor_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a multicolor_matters REFERENCE node for the cares-about
    idiom phase leaves unstructured (Fallaji Wayfarer's dropped-predicate
    grant, Niv-Mizzet Reborn's discarded "for each color pair" prefix).
    Gap-gated on :func:`has_structural_multicolor_matters` so a card the
    typed read already covers never doubles. Emits the REAL
    "multicolor_matters" concept directly (ADR-0038 retired the ``synth_*``
    marker namespace) — this key has no dedicated verb (it's a reference,
    not an effect), so the lane reads the synthesized node by its concept
    NAME rather than through a typed ``effect_concepts()`` walk."""
    if has_structural_multicolor_matters(tree):
        return None
    if not _MULTICOLOR_REFERENCE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="multicolor_matters",
        concept="multicolor_matters",
        scope="you",
        subject=(),
        desc="multicolor cares-about reference phase leaves unstructured",
    )


# ADR-0038 deferral sweep unit 6: colorless_matters — phase DROPS the
# "colorless" qualifier off a cast-restriction / cost-reduction / counter-
# target the SAME way it drops "multicolored" (Ghostfire Blade's "if it
# targets a colorless creature" cost_reduction subject=None, Ugin the
# Ineffable's "Colorless spells you cast cost {2} less" cost_reduction
# subject=None, Consign to Memory's "Counter target colorless spell" whose
# counter_spell subject is a bare Card Filter with no color predicate) —
# the OLD-IR's own ``supplement._recover_colorless_subject`` (SIDECAR #24e)
# already carries this exact idiom; ported here VERBATIM as a bucket-B
# reference-idiom synthesis arm, mirroring _arm_multicolor_matters's shape.
def _has_colorless_count_pred(filt: object) -> bool:
    """Whether ``filt`` carries a ``ColorCount`` ``EQ 0`` predicate,
    controller You OR unscoped (CR 105.2) — mirrors
    ``crosswalk_signals._predicate_build_around``'s "shared" colorless gate
    (a colorless reference is commonly unscoped -- Ancient Stirrings'
    "reveal cards until you reveal a colorless card")."""
    if filter_controller(filt) not in ("You", "Any", None):
        return False
    return any(cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(filt))


def has_structural_colorless_matters(tree: ConceptTree) -> bool:
    """The colorless_matters TYPED gate (CR 105.2): a ``ColorCount`` EQ 0
    predicate on an effect / count-operand / static-affected / trigger-
    subject filter, OR a condition-site ColorCount EQ 0 (Dominator Drone).
    Mirrors every check ``crosswalk_signals._predicate_build_around``'s
    colorless arm runs (including the condition-site + cost-role reads),
    so the reference-idiom synthesis arm below never doubles on a card the
    typed read already covers."""
    for c in tree.iter_concepts():
        if c.role == "cost":
            for leaf in iter_cost_leaves(c.node):
                filt = effect_filter(leaf)
                if filt is not None and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(filt)
                ):
                    return True
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is not None and _has_colorless_count_pred(filt):
                return True
    for unit in tree.units:
        if unit.statics:
            aff = getattr(unit.node, "affected", None)
            if aff is not None and _has_colorless_count_pred(aff):
                return True
        for site in iter_condition_sites(unit.node):
            for n in iter_typed_nodes(site):
                ctrl = filter_controller(n)
                if ctrl in ("You", "ScopedPlayer") and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(n)
                ):
                    return True
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) is None:
            continue
        # unlike multicolor (you-scoped only), colorless reads "shared"
        # (You/Any/None) — an unscoped colorless-cast trigger still counts
        # (mirrors the crosswalk lane's own "shared" gate).
        if filter_controller(vc) in ("You", "Any", None) and any(
            cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(vc)
        ):
            return True
    return False


# colorless cares-about REFERENCE idiom — the whole-word two-slot scan
# behind the OLD-IR's ``supplement._COLORLESS_REF`` (SIDECAR #24e), ported
# verbatim as a char-regex (this stage's arms are all char-regex over
# ``tree.oracle``, unlike the word-combinator OLD-IR path): "colorless
# creature(s)/spell(s)/permanent(s)" — stricter than a bare substring match
# ("colorless spellbomb" must NOT fire) via the `\b` word boundaries. CR
# 105.2c.
_COLORLESS_REFERENCE_RE = re.compile(
    r"\bcolorless (?:creature|creatures|spell|spells|permanent|permanents)\b",
    re.IGNORECASE,
)


def _arm_colorless_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a colorless_matters REFERENCE node for the cares-about
    idiom phase leaves unstructured (Ghostfire Blade / Ugin the Ineffable's
    dropped-predicate cost_reduction, Consign to Memory's colorless-blind
    counter_spell subject). Gap-gated on
    :func:`has_structural_colorless_matters` so a card the typed read
    already covers never doubles. Emits the REAL "colorless_matters"
    concept directly (ADR-0038 retired the ``synth_*`` marker namespace)
    — this key has no dedicated verb (it's a reference, not an effect), so
    the lane reads the synthesized node by its concept NAME rather than
    through a typed ``effect_concepts()`` walk."""
    if has_structural_colorless_matters(tree):
        return None
    if not _COLORLESS_REFERENCE_RE.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="colorless_matters",
        concept="colorless_matters",
        scope="you",
        subject=(),
        desc="colorless cares-about reference phase leaves unstructured",
    )


# ── batch T3-makers-type (ADR-0036/0037 Stage 5): island_matters bucket-B ─────
# CR 702.14c: the "can't attack unless defending player controls an Island"
# attack-restriction payoff (Dandân, Zhou Yu). phase parses this as an
# inconsistent mix of a raw-only condition and a dropped restriction clause —
# no typed node the lane can read — so it has no competing Tier-1 predicate
# (the celebration/coven/poison_matters precedent): relocates the deleted
# ``_ISLAND_MATTERS_RX`` (the pinned ``ISLAND_MATTERS_REGEX``) verbatim.
_ISLAND_MATTERS_SYNTH_RX = re.compile(ISLAND_MATTERS_REGEX, re.IGNORECASE)


def _matches_island_matters_idiom(oracle: str) -> bool:
    return bool(_ISLAND_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_island_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``island_matters`` node for the bucket-B attack-
    restriction payoff (the deleted ``_ISLAND_MATTERS_RX`` relocated
    verbatim)."""
    if not _matches_island_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="island_matters",
        concept="synth_island_matters",
        scope="you",
        subject=(),
        desc="bucket-B Island-control attack-restriction payoff (CR 702.14c)",
    )


# ── batch T3-makers-type: animate_artifact bucket-B (verbatim relocation) ────
# CR 613.1d + 702.122b: "artifacts become creatures" (Karn Silver Golem, March
# of the Machines, Vehicle-crew animation). phase parses this THREE
# inconsistent ways (batch-12 adjudication, ``_sweep_detectors.
# ANIMATE_ARTIFACT_REGEX`` module docstring) — no clean structural
# separation from generic become/type-conferral exists (a raw ``animate``
# arm fires on ZERO commander-legal cards; a base_pt_set/AddType-over-
# Artifact arm either 90%-over-fires or loses 48 core animators) — so this
# has no competing Tier-1 predicate and relocates the deleted
# ``_ANIMATE_ARTIFACT_RX`` verbatim.
_ANIMATE_ARTIFACT_SYNTH_RX = re.compile(ANIMATE_ARTIFACT_REGEX, re.IGNORECASE)


def _matches_animate_artifact_idiom(oracle: str) -> bool:
    return bool(_ANIMATE_ARTIFACT_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_animate_artifact(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``animate_artifact`` node (the deleted
    ``_ANIMATE_ARTIFACT_RX`` relocated verbatim)."""
    if not _matches_animate_artifact_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="animate_artifact",
        concept="synth_animate_artifact",
        scope="you",
        subject=(),
        desc="bucket-B artifact-becomes-creature (CR 613.1d/702.122b)",
    )


# ── batch T3-makers-type: color_change bucket-B (verbatim relocation) ────────
# CR 105.3: "becomes the color of your choice" / "becomes all colors" (Alchor's
# Tomb, Distorting Lens). phase parses this inconsistently (20 cards as a
# nested AddChosenColor, 4 as a bare Unimplemented "become" — batch-12
# adjudication); the only structural anchor (cat=='animate') over-fires ~90%
# (man-lands / animate-land anthems, not color-changers). No competing Tier-1
# predicate — relocates the deleted ``_COLOR_CHANGE_RX`` verbatim.
_COLOR_CHANGE_SYNTH_RX = re.compile(COLOR_CHANGE_REGEX, re.IGNORECASE)


def _matches_color_change_idiom(oracle: str) -> bool:
    return bool(_COLOR_CHANGE_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_color_change(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``color_change`` node (the deleted ``_COLOR_CHANGE_RX``
    relocated verbatim)."""
    if not _matches_color_change_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="color_change",
        concept="synth_color_change",
        scope="you",
        subject=(),
        desc="bucket-B color-changing effect (CR 105.3)",
    )


# ── batch T3-makers-type: vehicles_matter bucket-B tail ──────────────────────
# CR 301.7 + 702.122: the residual crew/Vehicle idiom the lane's three
# structural arms (Crews trigger / Vehicle-subtype static / GY->battlefield
# Vehicle recursion — ``_vehicles_matter`` in crosswalk_signals.py) miss:
# "Vehicles you control", "mounts and vehicles", a Vehicle-artifact-token
# maker, "becomes a vehicle" (a Vehicle GRANTER — the animated object need
# not itself be a Vehicle already). Gap-gated against the SAME three arms
# (SYNTH-EXCLUSION-PARITY) so this bucket-B tail never double-covers a card
# the structural arms already see.
_VEHICLES_MATTER_SYNTH_RX = re.compile(VEHICLES_MATTER_REGEX, re.IGNORECASE)


def has_structural_vehicles_matter(tree: ConceptTree) -> bool:
    """Whether phase already carries a typed node the vehicles_matter lane's
    three structural arms see — the synth gap-gate (mirrors the lane's own
    arms a/b/c exactly, GAP-GATE-ALIGNMENT)."""
    if "Vehicle" in tree.card_subtypes:
        return False
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in (
            "crews",
            "saddlesorcrews",
        ):
            return True
        if unit.origin == "static":
            affected = getattr(unit.node, "affected", None)
            subs = {w for s in filter_subtypes(affected) for w in s.lower().split()}
            if "vehicle" in subs and filter_controller(affected) == "You":
                return True
        for c in unit.effect_concepts("change_zone"):
            origin, dest = change_zone_dirs(c.node)
            if origin != "Graveyard" or dest != "Battlefield":
                continue
            tsubs = {
                s.lower() for s in filter_subtypes(getattr(c.node, "target", None))
            }
            if "vehicle" in tsubs:
                return True
    return False


def _matches_vehicles_matter_idiom(oracle: str) -> bool:
    return bool(_VEHICLES_MATTER_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_vehicles_matter(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``vehicles_matter`` node for the bucket-B crew/Vehicle
    residue (the deleted ``_VEHICLES_MATTER_RX`` relocated, gap-gated
    against :func:`has_structural_vehicles_matter` — the SAME arms the lane
    itself already tries first)."""
    if has_structural_vehicles_matter(tree):
        return None
    if not _matches_vehicles_matter_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="vehicles_matter",
        concept="synth_vehicles_matter",
        scope="you",
        subject=(),
        desc="bucket-B Vehicle/crew residue (CR 301.7/702.122)",
    )


# ── batch T3-makers-type: manland (land_protection's self-animate tail) ──────
# CR 613.1d/305: a commander animating MANY lands wants them kept alive
# (``_land_protection`` in crosswalk_signals.py). Two structural
# improvements over the deleted ``_MANLAND_MIRROR``:
#
# * a SelfRef-affected nested static (an Activated ability's own GenericEffect
#   — the projection does NOT lift these, per the animate_artifact/
#   waterbend precedent) conferring ``AddType Creature`` on a card that IS
#   itself a Land (the "Restless" self-animate manland cycle — Restless
#   Anchorage, Crawling Barrens — the latter a genuine RECOVER the mirror
#   MISSED: no "land" word precedes "becomes a 0/0 Elemental creature").
# * a landish-AFFECTED (Land core type or land-subtype word, e.g. an
#   ``EnchantedBy`` Island filter) nested static conferring ``AddType
#   Creature`` — the Genju cycle (Aura animates the enchanted land) and the
#   mass "all lands become creatures" anthems (Natural Affinity, Rude
#   Awakening, Sylvan Awakening, Life and Limb, Jolrael, Thelonite Druid) a
#   plain top-level walk misses because the modification is nested inside a
#   spell's/activated-ability's own ``GenericEffect``.
#
# Both are read together (:func:`has_structural_manland`), gap-gating the
# bucket-B text tail below. The residual genuine members phase structures too
# loosely to read (a SearchLibrary-then-animate tracked chain — Emergent
# Sequence, Rampaging Growth; a mass land-to-copy effect — March from Velis
# Vel; a fully ``Unimplemented`` activated ability — Sage of the Maze) keep
# the mirror's text idiom, with ONE adjudicated veto: "land becomes a/an
# <basic land type>" is a land TYPE-CHANGE idiom (Gaea's Liege, Graceful
# Antelope, Tide Shaper — "target land becomes a Forest/Plains/Island"), not
# an animate — the accompanying "creature" word these three carry is always
# an UNRELATED self-reference ("until THIS CREATURE leaves the battlefield"),
# a genuine mirror over-fire class shed here (measured over the
# commander-legal corpus: 3 dropped, 11 recovered, 0 other regressions).
_MANLAND_SYNTH_RX = re.compile(
    r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
    r"|that land becomes",
    re.IGNORECASE,
)
_MANLAND_TYPE_CHANGE_VETO_RX = re.compile(
    r"becomes? an? (?:forest|island|swamp|mountain|plains)\b", re.IGNORECASE
)
_LAND_SUBTYPE_WORDS_SYNTH: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "desert",
        "gate",
        "lair",
        "locus",
        "cave",
        "mine",
        "power-plant",
        "sphere",
        "tower",
        "urza's",
    }
)


def _manland_landish(affected: object) -> bool:
    return "Land" in filter_core_types(affected) or bool(
        {t.lower() for t in filter_subtypes(affected)} & _LAND_SUBTYPE_WORDS_SYNTH
    )


def has_structural_manland(tree: ConceptTree) -> bool:
    """Whether phase already carries a typed self-animate / landish-affected
    node the land_protection lane's manland arm sees — the synth gap-gate."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddType":
                continue
            if getattr(mod, "core_type", None) != "Creature":
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) == "SelfRef" and tree.is_type("Land"):
                return True
            if _manland_landish(affected):
                return True
    return False


def _matches_manland_idiom(oracle: str) -> bool:
    text = _REMINDER.sub(" ", oracle or "")
    if not _MANLAND_SYNTH_RX.search(text):
        return False
    return not _MANLAND_TYPE_CHANGE_VETO_RX.search(text)


def _arm_manland(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``manland`` node for land_protection's self-animate tail
    (the deleted ``_MANLAND_MIRROR`` relocated, land-type-change veto
    added, gap-gated against :func:`has_structural_manland`)."""
    if has_structural_manland(tree):
        return None
    if not _matches_manland_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="manland",
        concept="synth_manland",
        scope="you",
        subject=(),
        desc="bucket-B manland self-animate residue (CR 613.1d/305)",
    )


# ── land_creatures_matter grammar-sprint stragglers (ADR-0039 task #82,
# post-deletion grammar sprint) ──────────────────────────────────────────────
# Ledgered land_creatures_matter bridges (bridge_ledger.py) closed here —
# whole-clause phase drops (a role=effect ``Unimplemented`` node with ZERO
# typed substructure beneath it: no ``AddType``, no ``Animate``, no static
# def anywhere for the clause), the SAME shape the sibling
# ``manland``/``curse_matters``/etc. sweep arms above already close, gap-
# gated against a NEW shared helper so a card the lane's OWN structural
# reads already see (``_is_creature_animator`` / a first-class ``Animate``
# effect / a mass ``iter_static_defs`` AddType-Creature def) never doubles:
#
#   * subtype_animate -- RETIRED at the phase v0.23.0 bump (task #84).
#     Ambush Commander's "Forests you control are 1/1 green Elf creatures
#     that are still lands" (CR 305.6/305.7/613.1d layer 4) now parses as a
#     real Continuous static (SetPT + AddType over a Forest-subtyped
#     affected filter) that BOTH :func:`has_structural_land_creatures_
#     animate` and the lane's own set_pt static read see directly. The
#     v0.23.0 re-census of the arm's own bounding regex found ZERO
#     remaining gap members corpus-wide (the sole v0.20.0 hit was the pin
#     itself), so the arm was deleted rather than left as dead code.
#   * dynamic_animate -- Primal Adversary's deferred "pay this cost N
#     times, then up to that many target lands you control become 3/3 Wolf
#     creatures" repeat-count chain (CR 107.3 -- the paid-count value X --
#     /613.1d) and Sage of the Maze's "target land you control becomes an
#     X/X Citizen creature ... where X is twice the number of Gates you
#     control" formula-P/T animate (CR 107.3/613.4 sublayer 7c). Both drop
#     the WHOLE clause to ``Unimplemented`` because the value feeding the
#     animate is dynamic/deferred, not a literal count -- the grammar gap
#     is the SAME root cause (a computed value inside an "X becomes a
#     creature" clause), one arm covers both idioms per the ledger row's
#     per-idiom-class grouping. Corpus-verified (scan1.py, 2026-07-12): the
#     repeat-count regex is sole-source (Primal Adversary only); the
#     formula-X regex ALSO matches Elvish Branchbender's structurally
#     ALREADY-parsed "becomes an X/X ... creature ... in addition to its
#     other types, where X is the number of Elves you control" (phase
#     DOES emit a typed ``Animate`` node for it -- see the lane's own
#     "Land-SUBTYPE targets ... admitted" comment in crosswalk_signals.py)
#     -- the shared gap-gate below excludes it, leaving Sage of the Maze
#     as the arm's sole firing card for that half.
_LAND_CREATURES_DYNAMIC_REPEAT_SYNTH_RX = re.compile(
    r"up to that many target lands? you control become", re.IGNORECASE
)
_LAND_CREATURES_DYNAMIC_X_SYNTH_RX = re.compile(
    r"becomes? an? [^.]*creature[^.]*in addition to its other types,"
    r" where x is",
    re.IGNORECASE,
)


def has_structural_land_creatures_animate(tree: ConceptTree) -> bool:
    """Whether phase already carries a typed land->creature animate node
    the land_creatures_matter lane's own structural arms read (mirrors
    ``_is_creature_animator``'s static-def read, the first-class
    ``Animate`` effect read, and the mass ``iter_static_defs`` AddType-
    Creature descent, GAP-GATE-ALIGNMENT) -- the synth gap-gate for both
    arms below, so a card already covered structurally never doubles."""
    for unit in tree.units:
        for c in unit.iter_concepts():
            if c.role != "effect" or tag_of(c.node) != "Animate":
                continue
            tgt = getattr(c.node, "target", None)
            landish = "Land" in filter_core_types(tgt) or (
                {t.lower() for t in filter_subtypes(tgt)} & _LAND_SUBTYPE_WORDS_SYNTH
            )
            if landish and "Creature" in (getattr(c.node, "types", None) or ()):
                return True
        for sdef in iter_static_defs(unit.node):
            mods = getattr(sdef, "modifications", None)
            if any(
                tag_of(m) == "AddType" and getattr(m, "core_type", None) == "Creature"
                for m in (mods or [])
            ):
                return True
    return False


def _arm_land_creatures_dynamic_animate(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``land_creatures_dynamic_animate`` node for Primal
    Adversary's deferred repeat-count animate and Sage of the Maze's
    formula-X animate (the ``land_creatures_dynamic_animate_dropped``
    bridge, CR 107.3/613.1d/613.4), gap-gated against
    :func:`has_structural_land_creatures_animate` so Elvish Branchbender's
    already-structural formula-X animate never doubles."""
    if has_structural_land_creatures_animate(tree):
        return None
    text = _REMINDER.sub(" ", tree.oracle or "")
    if not (
        _LAND_CREATURES_DYNAMIC_REPEAT_SYNTH_RX.search(text)
        or _LAND_CREATURES_DYNAMIC_X_SYNTH_RX.search(text)
    ):
        return None
    return _synthetic_concept(
        arm_id="land_creatures_dynamic_animate",
        concept="synth_land_creatures_dynamic_animate",
        scope="you",
        subject=(),
        desc="bucket-B dynamic-value land-animate (CR 107.3/613.1d/613.4)",
    )


# ── arm: type_change bucket-B (ADR-0036/0037 Stage 5, T9-finalize) ────────────
# CR 702.16 + 613.1d: the type-HOSER read (the color_hoser analog, keyed on a
# creature SUBTYPE instead of a color) — a commander whose payoff punishes a
# named creature subtype ("protection from Salamanders") wants the creature-
# TYPE-CHANGING toolbox to force every opponent's creature into that subtype.
# The residual: the deleted ``_type_hoser_clause`` per-clause
# "protection from (\\w+)" vocab-gated scan for the cases phase's own
# AddKeyword{Protection{CardType}} argument read misses, relocated verbatim.
def has_structural_type_change(tree: ConceptTree) -> bool:
    """An ``AddKeyword`` whose keyword is ``Protection{CardType: <arg>}``
    with the argument vocab-validated against the creature-subtype list
    (Gor Muldrak's Salamanders); protection from a COLOR fails the gate."""
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            arg = protection_cardtype(mod)
            if arg is None:
                continue
            w = arg.lower()
            if w in CREATURE_SUBTYPES or w.rstrip("s") in CREATURE_SUBTYPES:
                return True
    return False


def _arm_type_change(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``type_change`` node for the "protection from <subtype>"
    residue (the deleted ``_type_hoser_clause`` mirror relocated verbatim),
    gap-gated against :func:`has_structural_type_change`."""
    if has_structural_type_change(tree):
        return None
    if not _type_hoser_clause(_REMINDER.sub(" ", tree.oracle or "").lower()):
        return None
    return _synthetic_concept(
        arm_id="type_change",
        concept="synth_type_change",
        scope="you",
        subject=(),
        desc="bucket-B protection-from-subtype residue (CR 702.16/613.1d)",
    )


_SNOW_SYNTH_RX = re.compile(r"\bsnow\b", re.IGNORECASE)


def has_structural_snow_matters(tree: ConceptTree) -> bool:
    """CR 205.4: a ``{HasSupertype: Snow}`` filter property, OR a
    ``YouControlSnowPermanentCountAtLeast`` condition."""
    for unit in tree.units:
        if has_filter_property(unit.node, "HasSupertype", "Snow"):
            return True
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) == "YouControlSnowPermanentCountAtLeast":
                return True
    return False


def _arm_snow_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``snow_matters`` node for the bare "snow" word residue
    (snow-mana payoffs / prose references phase leaves textual) — the
    deleted ``_SNOW_RX`` mirror relocated verbatim, gap-gated against
    :func:`has_structural_snow_matters`."""
    if has_structural_snow_matters(tree):
        return None
    if not _SNOW_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="snow_matters",
        concept="synth_snow_matters",
        scope="you",
        subject=(),
        desc="bucket-B bare snow-word residue (CR 205.4)",
    )


# Pump modification tags projecting to the live cat=='pump' (fixed AND dynamic
# spellings — Hancock's AddDynamicPower rides the same anthem, CR 613.4c) —
# moved here from crosswalk_signals (the neutral-home precedent).
_ANTHEM_PUMP_MODS: frozenset[str] = frozenset(
    {
        "AddPower",
        "AddToughness",
        "AddDynamicPower",
        "AddDynamicToughness",
        "AddPowerDynamic",
        "AddToughnessDynamic",
    }
)


def _typed_anthem_multi_hits(f: object) -> bool:
    """Whether a filter targets >=2 creature subtypes — the shared
    predicate the lane's structural read and this arm's gap gate both
    apply (one source, no drift; reimplemented here to avoid a
    crosswalk_signals<->tree_synthesis cycle)."""
    return (
        f is not None
        and "Creature" in filter_core_types(f)
        and len(set(filter_subtypes(f))) >= 2
    )


def _arm_typed_anthem_multi(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``typed_anthem_multi`` node for the RAW FALLBACK residue
    (CR 205.3m/613.4c): a pump modification or mass ``PumpAll`` effect whose
    typed subject filter is None (phase drops the multi-subtype list) but
    whose own site/effect text carries the CASE-SENSITIVE
    ``_TYPED_ANTHEM_MULTI_RAW`` anchor — the two deleted lane-time raw-
    fallback reads relocated verbatim. Gap-gated: only reached when the
    typed filter is absent (``_typed_anthem_multi_hits`` returns False for
    None), so this arm never duplicates the lane's own structural hit."""
    for unit in tree.units:
        for sd, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in _ANTHEM_PUMP_MODS:
                continue
            aff = getattr(sd, "affected", None)
            if aff is not None:
                continue
            if _TYPED_ANTHEM_MULTI_RAW.search(getattr(sd, "description", None) or ""):
                return _synthetic_concept(
                    arm_id="typed_anthem_multi",
                    concept="synth_typed_anthem_multi",
                    scope="you",
                    subject=(),
                    desc="bucket-B typed_anthem_multi mod-site raw fallback "
                    "(CR 205.3m/613.4c)",
                )
        for c in unit.effects:
            if tag_of(c.node) != "PumpAll":
                continue
            tgt = getattr(c.node, "target", None)
            if tgt is not None:
                continue
            if _TYPED_ANTHEM_MULTI_RAW.search(
                c.raw or getattr(unit.node, "description", None) or ""
            ):
                return _synthetic_concept(
                    arm_id="typed_anthem_multi",
                    concept="synth_typed_anthem_multi",
                    scope="you",
                    subject=(),
                    desc="bucket-B typed_anthem_multi PumpAll raw fallback "
                    "(CR 205.3m/613.4c)",
                )
    return None
