"""Death/dying and lifegain bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    cost_has_paylife,
    explicit_recipient_scope,
    iter_condition_sites,
    iter_typed_nodes,
    replacement_event_tag,
    tag_of,
    trigger_subject,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _MASS_DEATH_REF,
    _PAY_LIFE_REF,
    _STARTING_LIFE_REF,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.signal_base import (
    _resolve_subject,
    clauses,
)


def _is_creature_death_subject(subject: tuple[str, ...]) -> bool:
    """Whether a ``dies`` trigger's watched OBJECT is a CREATURE (CR 700.4).

    "Dies" is defined only for creatures (a creature put into a graveyard from the
    battlefield); a watcher of a non-creature graveyard-arrival (Scrapheap —
    artifact/enchantment) is a different lane, not a death payoff. True when the
    watched subject names ``Creature`` OR resolves to a real creature subtype
    (Kithkin Mourncaller); a pure ``Artifact`` / ``Enchantment`` subject — or a
    token-only subtype absent from the card-face vocab (Tentacle — The Watcher) —
    is rejected. The subtype check routes through ``_resolve_subject`` so it shares
    the vocab's case-folding + the card-type / non-creature-token (Treasure / Clue)
    denylists rather than a raw membership test against the lowercased vocab.

    Shared by the ``_death_matters`` lane (which imports this) and this stage's gap
    gate (:func:`_has_structural_death`) so the two agree on which dies-triggers
    phase structuralizes — one source, no drift. A non-vocab subtype dies-trigger
    (Tentacle) is thereby NOT counted structural, so it reaches the SUBTYPE synth
    arm instead of dropping through the crack.
    """
    return "Creature" in subject or any(
        _resolve_subject(w, CREATURE_SUBTYPES) for w in subject
    )


# ── shared death/dies VALUE-effect predicates (ADR-0036 — the neutral home) ───
# Moved here from ``crosswalk_signals`` so the ``_death_matters`` /
# ``_self_death_payoff`` lanes AND the ``wants_cloning`` fold read ONE source (no
# drift), and so :func:`is_clone_value_effect` can reuse them without the
# ``crosswalk_signals`` <-> ``tree_synthesis`` import cycle. ``crosswalk_signals``
# imports them back.
_DEATH_PAYOFF_EFFECTS: frozenset[str] = frozenset(
    {
        "draw",
        "dig",
        "reveal_until",
        "deal_damage",
        "lose_life",
        "gain_life",
        "mill",
        "make_token",
        "place_counter",
        "discard",
        "surveil",
        "cast_from_zone",
    }
)


def _is_death_payoff_effect(e: ConceptNode) -> bool:
    """Whether an AttachedTo dies-trigger effect EXTRACTS VALUE (payoff, KEEP), not
    resilience (SHED). CR 700.4.

    A named payoff kind (:data:`_DEATH_PAYOFF_EFFECTS`), OR a DEPLOY ``change_zone``
    — a ``Creature`` put onto the battlefield from hand/graveyard (Deathrender
    deploys a NEW creature from hand on the equipped creature's death). The deploy
    form is distinguished from the return-THE-SOURCE resilience ``change_zone``
    (Resurrection Orb / Oathkeeper / Gift of Immortality — "return that card to the
    battlefield", which phase emits with an EMPTY subject and origin unset) by a
    named ``Creature`` subject moving Hand/Graveyard → Battlefield, so widening the
    gate here recovers Deathrender without re-admitting the resilience auras.
    """
    if e.concept in _DEATH_PAYOFF_EFFECTS:
        return True
    if e.concept == "change_zone":
        origin, dest = change_zone_dirs(e.node)
        return (
            dest == "Battlefield"
            and origin in ("Hand", "Graveyard")
            and "Creature" in e.subject
        )
    return False


# A ``ChangeZone`` back to the battlefield targeting the trigger's own source (the
# undying/persist return — Kitchen Finks) OR a shuffle-into-library protection
# rider (Kozilek). Both are SELF-preservation, never a fork-worthy VALUE payoff, so
# ``is_clone_value_effect`` and ``_self_death_payoff`` both shed them.
_SELF_RETURN_TAGS: frozenset[str] = frozenset({"SelfRef", "TriggeringSource"})


def _is_self_return_effect(c: ConceptNode) -> bool:
    """A ``ChangeZone`` back to the battlefield targeting the trigger's own
    source — the dies_recursion return arm (Kitchen Finks' persist), NOT a
    death VALUE payoff."""
    return (
        tag_of(c.node) == "ChangeZone"
        and getattr(c.node, "destination", None) == "Battlefield"
        and tag_of(getattr(c.node, "target", None)) in _SELF_RETURN_TAGS
    )


def _is_shuffle_back_effect(c: ConceptNode) -> bool:
    """A zone move whose destination is the LIBRARY — the "shuffle it / your
    graveyard into its owner's library" self-protection rider (Kozilek,
    Serra Avatar — CR 701.19b), not a death VALUE payoff."""
    return (
        tag_of(c.node) in ("ChangeZone", "ChangeZoneAll")
        and getattr(c.node, "destination", None) == "Library"
    )


# ── arm: death_matters bucket-B (ADR-0036 fold) ───────────────────────────────
# The aristocrats death payoff (OTHER creatures dying, CR 700.4) has a bucket-B
# tail phase emits NO typed death node for: the clause lives only in a trigger's
# raw DESCRIPTION or an untyped condition. Three genuine idiom families the
# structural Tier-1 arms miss, each read PER-CLAUSE (reminder-stripped, split on
# ``.;\n``) so a match is confined to ONE clause — the cross-clause false-positive
# class the mirror carried is thereby eliminated:
#
#   * MORBID condition — "if a creature died this turn" / "for each creature that
#     died this turn" (Feast, Inga Rune-Eyes, the Zubera-count payoffs) that phase
#     folds into an effect operand rather than a typed ZoneChangeCount. No
#     "whenever" gate: "died this turn" is an unambiguous death-count idiom.
#   * COMBAT-DAMAGE death — "whenever a creature dealt damage … this turn dies"
#     (Scythe of the Wretched, Unscythe, Vampiric Sliver): the damaged creature's
#     death, OTHER-creature death per CR 700.4.
#   * OTHER-creature death — "whenever another/a … creature|permanent … dies"
#     (Syr Konrad, Massacre Girl, Baeloth) and the subtype-tribal form ("whenever
#     another nontoken Human you control dies" — Jerren; Tentacle — The Watcher).
#
# The COMBAT / OTHER / SUBTYPE families are "whenever"-gated (a persistent death
# TRIGGER, not a one-shot "if it dies this way" rider — Cinder Cloud). Every family
# fires ONLY when NO structural death node is present (so it never double-counts a
# card a Tier-1 arm already reads) and ONLY for OTHER-creature death (a bare
# self-death "when ~ dies" — no "whenever", subject "this" — matches no family, so
# it is shed to ``self_death_payoff`` without an explicit veto). ~40 commander-legal
# corpus cards fire this arm across the three families (the pilot's single
# "another creature dies" idiom covered ~23).
_DEATH_MORBID_RX = re.compile(
    r"creatures?[^.]*\bdied\b[^.]*this turn|no creatures? died this turn",
    re.IGNORECASE,
)
_DEATH_COMBAT_RX = re.compile(
    r"creature[^.]*dealt damage[^.]*this turn[^.]*\bdies\b"
    r"|creature[^.]*dealt damage[^.]*\bdies\b[^.]*this turn",
    re.IGNORECASE,
)
_DEATH_OTHER_RX = re.compile(
    r"\b(?:another|an?|one or more) (?:\w+ ){0,4}?(?:creature|permanent)s? "
    r"(?:you (?:control|own) |an opponent controls )?dies?\b",
    re.IGNORECASE,
)
# subtype-tribal death ("another nontoken Human you control dies"); the capitalized
# subtype anchor keeps it distinct from a card NAME (which is not lowercased here).
_DEATH_SUBTYPE_RX = re.compile(
    r"\b(?:another|an?) (?:nontoken |token )?[A-Z][a-z]+ "
    r"(?:you (?:control|own) )?dies\b",
)
_DEATH_CLAUSE_SPLIT = re.compile(r"[.;\n]")


def _matches_death_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B death idiom (per-clause).

    MORBID fires ungated ("died this turn"); the COMBAT / OTHER / SUBTYPE trigger
    families require "whenever" in the same clause (a persistent death trigger, not
    a one-shot removal rider). CR 700.4.
    """
    clauses = _DEATH_CLAUSE_SPLIT.split(_REMINDER.sub(" ", oracle or ""))
    for cl in clauses:
        if _DEATH_MORBID_RX.search(cl):
            return True
    for cl in clauses:
        if "whenever" not in cl.lower():
            continue
        if (
            _DEATH_COMBAT_RX.search(cl)
            or _DEATH_OTHER_RX.search(cl)
            or _DEATH_SUBTYPE_RX.search(cl)
        ):
            return True
    return False


def _iter_all_typed(tree: ConceptTree) -> Iterator[TypedMirrorNode]:
    """Every typed mirror node under every phase unit (the whole-card deep walk)."""
    for unit in tree.units:
        yield from iter_typed_nodes(unit.node)


def _has_tag(tree: ConceptTree, tag: str) -> bool:
    """Whether any typed node anywhere on the card carries discriminator ``tag``."""
    return any(tag_of(n) == tag for n in _iter_all_typed(tree))


def _double_triggers_creature_dying(tree: ConceptTree) -> bool:
    """A ``DoubleTriggers`` static caused by ``CreatureDying`` (Teysa / Drivnod).

    The ``DoubleTriggers`` mode is a modification-less MODE static, so it never
    surfaces through ``iter_static_defs`` (no modifications to pair with);
    :func:`double_triggers_cause_core_types` also returns ``None`` for the non-ETB
    ``CreatureDying`` cause. We scan the raw nodes and read the cause off the mode
    variant's ``to_dict`` (its inner is itself a wrapper). CR 603.2.
    """
    for n in _iter_all_typed(tree):
        mode = getattr(n, "mode", MISSING)
        if not (isinstance(mode, MirrorVariant) and mode.key == "DoubleTriggers"):
            continue
        inner = mode.to_dict().get("DoubleTriggers")
        cause = inner.get("cause") if isinstance(inner, dict) else inner
        if cause == "CreatureDying":
            return True
    return False


def _has_creature_morbid(tree: ConceptTree) -> bool:
    """A morbid battlefield→graveyard creature-death state check (Bone Picker)."""
    for unit in tree.units:
        for frm, to, filt in zone_change_count_reads(unit.node):
            if (
                to == "Graveyard"
                and frm in ("Battlefield", None)
                and _filter_is_creature_death(filt)
            ):
                return True
    return False


def _filter_is_creature_death(filt: object) -> bool:
    """Whether a zone-change filter names a CREATURE (CR 700.4) — a death, not a
    land/permanent-only graveyard-arrival."""
    d = filt.to_dict() if isinstance(filt, TypedMirrorNode) else {}
    tfs = d.get("type_filters") if isinstance(d, dict) else None
    if not isinstance(tfs, list):
        return False
    # ``type_filters`` mixes plain strings ("Creature") and dicts ({"Subtype":
    # "Dalek"}); a dict is unhashable, so membership must not hash the element.
    return any(isinstance(tf, str) and tf in ("Creature", "Permanent") for tf in tfs)


def creature_death_condition(tree: ConceptTree) -> bool:
    """A morbid creature-death STATE check the ``_death_matters`` lane reads Tier-1.

    The "if a creature died this turn" / "for each creature that died this turn"
    family (Bone Picker, Mahadi, the Zubera-count payoffs): a
    ``CreatureDiedThisTurn`` flag, a creature battlefield→graveyard
    ``ZoneChangeCountThisTurn``, or a ``ZoneChangeAggregateThisTurn`` creature count
    (CR 700.4). Shared by the lane (as a structural arm) and this stage's gap gate
    so the two agree on which cards phase structuralizes — one source, no drift.
    """
    if _has_tag(tree, "CreatureDiedThisTurn") or _has_creature_morbid(tree):
        return True
    for n in _iter_all_typed(tree):
        if tag_of(n) == "ZoneChangeAggregateThisTurn" and (
            _filter_is_creature_death(getattr(n, "filter", None))
        ):
            return True
    return False


def _has_structural_death(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 death reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural death
    evidence the lane reads exists: a battlefield ``dies`` trigger watching a real
    CREATURE object (:func:`_is_creature_death_subject` — the SAME predicate the
    lane fires on, so the gate and the lane never disagree). A bare self-death
    ``SelfRef`` yields no subject (not structural — its morbid EFFECT clause still
    reaches the synth), and a non-vocab subtype watcher (Tentacle — The Watcher) is
    NOT a recognized creature, so it is also not counted structural and the SUBTYPE
    synth arm recovers it. Also structural: a morbid creature-death state check
    (:func:`creature_death_condition`) or a ``CreatureDying`` trigger-doubler.
    """
    for unit in tree.units:
        if (
            unit.trigger_event == "dies"
            and getattr(unit.node, "origin", None) == "Battlefield"
            and _is_creature_death_subject(trigger_subject(unit.node))
        ):
            return True
    if creature_death_condition(tree):
        return True
    return _double_triggers_creature_dying(tree)


def _arm_death_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``death_matters`` node for a description-only death payoff.

    CR 700.4 self/other split: the synth idioms (:func:`_matches_death_idiom`)
    require a MORBID "creature died this turn" state, a combat-damage-dies clause,
    or a "whenever another/a creature … dies" trigger — all OTHER-creature death
    (the aristocrats lane). A bare self-death "when <this> dies" matches NONE
    ("when" ≠ "whenever"; "this" ∉ another/an/a; no "died this turn"), so it is shed
    to ``self_death_payoff`` without an explicit veto.
    """
    if _has_structural_death(tree):
        return None
    if not _matches_death_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="death_matters",
        concept="synth_death_matters",
        scope="any",
        subject=("Creature",),
        desc="bucket-B death payoff (phase emits no typed death node)",
    )


# ── mass_death_payoff structural read (ADR-0036 fold — shared lane/gate source) ─
# CR 700.4 amount-vs-condition boundary. mass_death_payoff is the AGGREGATE
# board-wipe payoff — a value/effect that SCALES with the NUMBER of creatures that
# died this turn ("a Treasure for each nontoken creature that died this turn" —
# Gadrak / Mahadi; "draw a card for each creature that died under your control this
# turn" — Body Count; "connive X, where X is the number of creatures that died" —
# Spymaster's Vault). phase emits that count as a ``ZoneChangeCountThisTurn`` (from
# Battlefield, to Graveyard, creature/permanent filter) wrapped in a ``Ref`` held
# in an effect AMOUNT field (``Token.count`` / ``Draw.count`` / ``PutCounter.count``
# / ``GainLife.amount`` / ``Connive.count`` / ``Quantity.value`` / ``Multiply.inner``
# / ``repeat_for`` — the SCALING position).
#
# The MORBID single-death conditional ("if a creature died this turn" — Bone Picker,
# Tragic Slip, the Zubera / Festerhide threshold payoffs) emits the SAME count node
# but in a COMPARISON operand (the ``lhs`` of ``QuantityComparison`` /
# ``QuantityCheck`` / ``OnlyIfQuantity``) — that is death_matters (the morbid CONDITION,
# read there via :func:`creature_death_condition`), NOT this lane. Discriminating on
# the HOLDING FIELD partitions the ~94 corpus carriers cleanly: 34 amount (aggregate
# payoff), ~60 comparison (morbid) — a naive tag-only read over-fires on the morbid.
# Shared by the ``_mass_death_payoff`` lane (its Tier-1 arm) and this stage's synth
# gap gate — one source, no drift (the gap-gate-alignment invariant).

# A creatures-died count in a COMPARISON operand is the morbid CONDITION, not an
# amount; every other field the Ref sits in is a SCALING amount.
_DIED_COUNT_COMPARISON_FIELDS = frozenset({"lhs", "rhs"})


def _is_creature_died_count(n: object) -> bool:
    """A ``ZoneChangeCountThisTurn`` counting creatures that died this turn.

    from Battlefield, to Graveyard, filter naming Creature / Permanent (CR 700.4 —
    only creatures die; a permanent-scoped Gravestorm count rides the same node).
    """
    return (
        tag_of(n) == "ZoneChangeCountThisTurn"
        and getattr(n, "from_", None) == "Battlefield"
        and getattr(n, "to", None) == "Graveyard"
        and _filter_is_creature_death(getattr(n, "filter", None))
    )


def _amount_died_count_under(root: object) -> bool:
    """Whether a creatures-died count sits in an effect AMOUNT position under root.

    A ``Ref`` whose ``qty`` is a creatures-died count (:func:`_is_creature_died_count`)
    held in a field that is NOT a comparison operand
    (:data:`_DIED_COUNT_COMPARISON_FIELDS`) — the SCALING position that makes the
    lane an aggregate payoff rather than a morbid condition.
    """

    def walk(v: object) -> bool:
        if isinstance(v, TypedMirrorNode):
            for f in dataclasses.fields(v):
                fv = getattr(v, f.name, MISSING)
                if (
                    isinstance(fv, TypedMirrorNode)
                    and tag_of(fv) == "Ref"
                    and f.name not in _DIED_COUNT_COMPARISON_FIELDS
                    and _is_creature_died_count(getattr(fv, "qty", None))
                ):
                    return True
                if walk(fv):
                    return True
            return False
        if isinstance(v, MirrorVariant):
            return walk(v.inner)
        if isinstance(v, (list, tuple)):
            return any(walk(x) for x in v)
        if isinstance(v, dict):
            return any(walk(x) for x in v.values())
        return False

    return walk(root)


def mass_death_amount(tree: ConceptTree) -> bool:
    """Whether phase carries the creatures-died count in an effect AMOUNT position.

    The aggregate board-wipe payoff (CR 700.4). Shared by the ``_mass_death_payoff``
    lane (as its structural Tier-1 arm) and this stage's synth gap gate so the two
    agree on which cards phase structuralizes — one source, no drift.
    """
    return any(_amount_died_count_under(unit.node) for unit in tree.units)


def _arm_mass_death_payoff(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``mass_death_payoff`` node for the bucket-B aggregate tail.

    phase drops the ``died this turn`` count OPERAND for the cost-reduction form
    ("this spell costs {N} less to cast for each creature that died this turn" —
    Blood for the Blood God!, Death-Rattle Oni, Diregraf Rebirth) and the
    Unimplemented tail (Tobias). This arm relocates the AGGREGATE regex to
    projection-time, gated on :func:`mass_death_amount` (the SAME predicate the lane
    fires on — SYNTH-EXCLUSION-PARITY: the tight ``for each`` / ``number of`` anchor
    already excludes the morbid conditional, and the gate suppresses the synth wherever
    phase already emits the amount, so it fires ONLY on genuine-gap cards). CR 700.4.
    """
    if mass_death_amount(tree):
        return None
    if not _MASS_DEATH_REF.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="mass_death_payoff",
        concept="synth_mass_death_payoff",
        scope="you",
        subject=(),
        desc="bucket-B aggregate death payoff (phase drops the died-count operand)",
    )


# ── lifegain_matters structural reads (ADR-0036 fold — shared lane/gate source) ──
# The Tier-1 ``_lifegain_matters`` lane fires ``lifegain_matters`` on these five
# typed reads; this stage's gap gate (:func:`_has_structural_lifegain`) reads the
# SAME predicates so the lane and the synth never disagree on which cards phase
# structuralizes (the gap-gate-alignment invariant — one source, no drift). The
# lane is a YOUR-lifegain PAYOFF / significant self-life-loss engine (CR 119.3): a
# pure lifegain SOURCE ("whenever ~ dies, you gain 1 life" — Blood Artist) is
# ``lifegain_makers``, not this lane, and a bare lose-life / pay-life clause and an
# opponent-lifegain hoser are shed (a different lane).

_LIFE_GAINED_THIS_TURN_TAGS: frozenset[str] = frozenset(
    {"LifeGainedThisTurn", "YouGainedLifeThisTurn"}
)


def has_life_gained_trigger(tree: ConceptTree) -> bool:
    """A native ``life_gained`` trigger — "whenever you gain life" (CR 603.2).

    Archangel of Thune, Ajani's Pridemate, Well of Lost Dreams. The direct
    structural payoff; a conferred/granted one (inside a static-granted ability,
    phase drops the inner trigger — Sunbond) reaches the bucket-B synth instead.
    """
    return any(u.trigger_event == "life_gained" for u in tree.units)


def has_trigger_draw_bleed(tree: ConceptTree) -> bool:
    """A triggered draw-and-self-bleed engine (the Phyrexian Arena / Necropotence
    idiom — CR 119.3).

    ANY triggered ability whose SAME ability carries BOTH a ``draw`` AND an explicit-
    self ``lose_life``: the card pays life to draw, so it wants lifegain to sustain
    the bleed. The trigger EVENT is not restricted — an upkeep bleed (Phyrexian
    Arena), an attack bleed (Audacious Thief), a creature-death bleed (Taborax), and
    a general permanent-to-graveyard bleed whose event phase types ``other``
    (Kothophed) or ``leaves`` (Nikara) are the SAME repeated card-flow engine, so all
    fire. Gating on a *trigger* (not a one-shot spell/activated effect) keeps it to a
    recurring engine; the ``draw`` gate keeps it to card-flow (a bare "you lose 2
    life" rider is not a draw-bleed). Broadened from the original dies-only gate to
    recover the event-``other`` / non-dies engines the death-only read missed
    (ADR-0036 recall-completion).
    """
    for unit in tree.units:
        if not unit.trigger_event or not unit.has_effect("draw"):
            continue
        for c in unit.effect_concepts("lose_life"):
            if explicit_recipient_scope(c.node) == "you":
                return True
    return False


def has_selfloss_engine(tree: ConceptTree) -> bool:
    """A significant recurring self-life-LOSS engine (CR 119.3 — wants lifegain).

    An explicit-self ``lose_life`` that SCALES (dynamic amount — Dark Confidant) OR
    a beginning-of-upkeep bleed with factor >= 2 (Xathrid Demon). A one-shot fixed
    "you lose 2 life" rider is NOT an engine (excluded — the mirror's broader loose
    lose-life / pay-life / symmetric-drain matches are shed as over-fires).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("lose_life"):
            if explicit_recipient_scope(c.node) != "you":
                continue
            up = getattr(getattr(unit, "node", None), "phase", None) == "Upkeep"
            if amount_is_scaling(c.node) or (up and amount_factor(c.node) >= 2):
                return True
    return False


def has_life_gained_this_turn(tree: ConceptTree) -> bool:
    """A "life gained this turn" typed operand / gate (bucket-A — CR 119).

    The ``LifeGainedThisTurn`` dynamic-amount / condition node (Accomplished
    Alchemist's mana scaler, Angelic Accord's "if you gained 4 or more life this
    turn" gate, Crested Sunmare) — a payoff that references HOW MUCH life you gained
    this turn, analogous to death's morbid ``ZoneChangeCountThisTurn``. A genuine
    your-lifegain payoff the ``life_gained`` trigger arm does not see.
    """
    return any(
        tag_of(n) in _LIFE_GAINED_THIS_TURN_TAGS
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _replacement_exec_type(node: object) -> str | None:
    """The type of a replacement unit's executed effect (``execute.effect.type``)."""
    d = node.to_dict() if isinstance(node, TypedMirrorNode) else {}
    ex = d.get("execute") if isinstance(d, dict) else None
    eff = ex.get("effect") if isinstance(ex, dict) else None
    return eff.get("type") if isinstance(eff, dict) else None


def has_gain_life_amplifier(tree: ConceptTree) -> bool:
    """A CR-614 gain-life REPLACEMENT amplifier (bucket-A — "if you would gain life").

    An ``origin == "replacement"`` unit whose replaced event is ``GainLife`` and
    whose executed effect re-emits a gain (``GainLife`` — the "twice that much" /
    "that much plus 1" amplifiers: Alhammarret's Archive, Boon Reflection, Angel of
    Vitality, Rhox Faithmender) or converts it (``Draw`` — Lich, "draw that many
    cards instead"). A ``LoseLife`` execute (Tainted Remedy / Rain of Gore — "if an
    OPPONENT would gain life, they lose that much") is an anti-lifegain hoser on a
    DIFFERENT lane, and a ``None`` / unimplemented execute (Sulfuric Vortex "can't
    gain life", Flames of the Blood Hand "gain no life") is a hoser too — both
    excluded by the execute gate.
    """
    for unit in tree.units:
        if (
            unit.origin == "replacement"
            and replacement_event_tag(unit.node) == "GainLife"
            and _replacement_exec_type(unit.node) in ("GainLife", "Draw")
        ):
            return True
    return False


_HIGH_LIFE_COMPARATORS: frozenset[str] = frozenset({"GE", "GT"})
# A FIXED life threshold must clear this floor to count as a "high life" payoff.
# The corpus splits cleanly: the lone low outlier is Elderscale Wurm's "7 or more
# life" damage-prevention FLOOR (a survival shield — gaining life past 7 does
# nothing, so it is NOT a lifegain payoff), while every genuine payoff sits at 25+
# (Divinity of Pride 25 … Bilbo 111). 15 is the wide-margin gap between them.
# Relative gates (RHS is a Ref, e.g. "≥ your starting life" — Path of Bravery,
# Glorious Enforcer) are a deliberate-high condition regardless of number and are
# kept unconditionally.
_MIN_HIGH_LIFE_THRESHOLD = 15


def has_high_life_total_payoff(tree: ConceptTree) -> bool:
    """A HIGH-life-total win-condition / static payoff (CR 104.2 + 119.3):
    life as a resource, not just a one-time gain.

    A ``QuantityComparison`` condition (:func:`iter_condition_sites`, the
    big_hand_matters precedent) whose LHS reads YOUR ``LifeTotal`` (CR
    119.1) with a GE/GT comparator (:data:`_HIGH_LIFE_COMPARATORS`) — "as
    long as you have 25 or more life" static payoffs (Divinity of Pride,
    Serra Ascendant, Blood Baron of Vizkopa, Caduceus Staff of Hermes), a
    win-the-game upkeep threshold (Felidar Sovereign, Test of Endurance —
    CR 104.2), a relative "more life than an opponent" comparison whose LHS
    is still YOUR life (Glorious Enforcer), and the vs-starting-life gate
    (Path of Bravery). A FIXED threshold BELOW :data:`_MIN_HIGH_LIFE_
    THRESHOLD` is excluded as a survival FLOOR, not a high-life payoff —
    Elderscale Wurm ("7 or more life" gating damage prevention) reads as a
    genuine ``QuantityComparison`` GE 7 but gaining life past 7 does nothing
    for it, so it is not a lifegain payoff; a near-death "if you have 5 or
    less life" payoff is a DIFFERENT, opposite-polarity signal (LE/LT), not
    read here. Any RHS/OTHER-player LifeTotal comparand alone (Marchesa's
    Emissary-style "player with the most life" family — the LHS gate is
    load-bearing) is excluded.
    """
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(site):
                if tag_of(q) != "QuantityComparison":
                    continue
                if getattr(q, "comparator", None) not in _HIGH_LIFE_COMPARATORS:
                    continue
                lhs = getattr(q, "lhs", None)
                qty = getattr(lhs, "qty", None) if lhs is not None else None
                if tag_of(qty) != "LifeTotal":
                    continue
                player = getattr(qty, "player", None)
                if tag_of(player) != "Controller":
                    continue
                # A fixed threshold must clear the "high" floor; a relative
                # (Ref) gate is a deliberate-high condition, kept as-is.
                rhs = getattr(q, "rhs", None)
                if tag_of(rhs) == "Fixed":
                    val = getattr(rhs, "value", None)
                    if isinstance(val, int) and val < _MIN_HIGH_LIFE_THRESHOLD:
                        continue
                return True
    return False


def _has_structural_lifegain(tree: ConceptTree) -> bool:
    """Whether phase ALREADY carries a typed node the Tier-1 lifegain reads see.

    The synth arm fills only a genuine gap, so it no-ops when any structural
    lifegain evidence the lane fires on exists — the SAME six predicates the
    lane reads (:func:`has_life_gained_trigger` / :func:`has_trigger_draw_bleed`
    / :func:`has_selfloss_engine` / :func:`has_life_gained_this_turn` /
    :func:`has_gain_life_amplifier` / :func:`has_high_life_total_payoff` —
    ADR-0036/0037 Stage 5 #60), so the gate and the lane never disagree.
    """
    return (
        has_life_gained_trigger(tree)
        or has_trigger_draw_bleed(tree)
        or has_selfloss_engine(tree)
        or has_life_gained_this_turn(tree)
        or has_gain_life_amplifier(tree)
        or has_high_life_total_payoff(tree)
    )


# ── arm: lifegain_matters bucket-B (ADR-0036 fold) ────────────────────────────
# The your-lifegain payoff (CR 119) has a bucket-B tail phase emits NO typed
# lifegain node for: a "whenever you gain life" trigger left description-only or
# inside a granted/quoted ability ("Enchanted creature has 'whenever you gain
# life, …'" — Sunbond, Light of Promise; emblem payoffs — Ajani, Strength of the
# Pride) — including the "gain OR lose life" combined trigger (Moonstone Harbinger,
# Wax-Wane Witness) — and the "gained life this turn" gate / "life you gained"
# scaler phase folds into untyped text without a ``LifeGainedThisTurn`` node (Regna,
# Licia, Shanna, Case of the Uneaten Feast). Read PER-CLAUSE (reminder-stripped) so
# a match is confined to ONE clause — the cross-clause false-positive class the
# mirror carried. The "you gain / you've gained" anchoring keeps it YOUR lifegain:
# "whenever a PLAYER gains life" (False Cure hoser) and "whenever an OPPONENT gains
# life" (Punishing Fire) never match.
_LIFEGAIN_WHENEVER_RX = re.compile(
    r"whenever you gain(?: or lose)? life", re.IGNORECASE
)
_LIFEGAIN_GAINED_RX = re.compile(
    r"(?:you|your team)(?:'ve| have)? gained[^.]*life|life you gained",
    re.IGNORECASE,
)


def _matches_lifegain_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B lifegain payoff idiom.

    Per-clause: a your-side "whenever you gain (or lose) life" trigger, or a "you('ve)
    gained … life" / "life you gained" this-turn gate/scaler. CR 119.
    """
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _LIFEGAIN_WHENEVER_RX.search(cl) or _LIFEGAIN_GAINED_RX.search(cl):
            return True
    return False


def _arm_lifegain_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``lifegain_matters`` node for a description-only lifegain payoff.

    CR 119: fires only when phase carries no typed lifegain node
    (:func:`_has_structural_lifegain`) and the oracle carries a genuine your-side
    lifegain idiom (:func:`_matches_lifegain_idiom`). Scope "you" (the lane's forced
    scope for this your-lifegain payoff).
    """
    if _has_structural_lifegain(tree):
        return None
    if not _matches_lifegain_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="lifegain_matters",
        concept="synth_lifegain_matters",
        scope="you",
        subject=(),
        desc="bucket-B lifegain payoff (phase emits no typed lifegain node)",
    )


# ── batch T5-niche-a: life_payment_insurance (bucket-B tail) ───────────────
# CR 119.4 (a pay-life cost subtracts from the total only if life >= amount —
# a repeatable pay-life COST wants lifegain insurance): the live structural
# cost census (any Activated unit's flattened cost carrying a ``PayLife``
# leaf) already binds the card's OWN activated ability. The residual: a
# GRANT form — a static's granted-ability STRING ("Other Caves you control
# have '{T}, Pay 1 life: …'" — Forgotten Monument; "Enchanted land has
# '{T}, Pay 1 life: …'" — Underworld Connections) phase never structures (an
# ``AddAbility``-style text payload, not a typed Activated/PayLife leaf on
# THIS card) — a genuine gap, not a dropped read. Relocates the deleted
# ``_PAY_LIFE_REF`` marker re-derivation, gap-gated against the structural
# cost census (the project.py :8527-8530 face gate this shares — the SAME
# marker feeds an independent the compat-Card resolver path there, untouched). Measured
# byte-identical over the commander-legal corpus (155/155 union, 0 drops).
def has_structural_life_payment_insurance(tree: ConceptTree) -> bool:
    """Whether ANY Activated unit's flattened cost carries a ``PayLife``
    leaf (a deep walk, not just the top-level ``Composite`` costs list —
    the pay-HALF-life forms nest it under ``EffectCost.effect/PayCost.cost``,
    Lurking Evil / Murderous Betrayal)."""
    for unit in tree.units:
        if unit.kind != "Activated":
            continue
        cost = getattr(unit.node, "cost", None)
        if cost_has_paylife(cost) or any(
            tag_of(q) == "PayLife" for q in iter_typed_nodes(cost)
        ):
            return True
    return False


def _matches_life_payment_insurance_idiom(oracle: str) -> bool:
    return bool(_PAY_LIFE_REF.search(_REMINDER.sub(" ", oracle or "")))


def _arm_life_payment_insurance(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``life_payment_insurance`` node for the granted-ability
    ("Other Caves have '…Pay N life:…'") residue (the deleted
    ``_PAY_LIFE_REF`` marker relocated, gap-gated against
    :func:`has_structural_life_payment_insurance`)."""
    if has_structural_life_payment_insurance(tree):
        return None
    if not _matches_life_payment_insurance_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="life_payment_insurance",
        concept="synth_life_payment_insurance",
        scope="you",
        subject=(),
        desc="bucket-B granted pay-life-cost-ability residue (CR 119.4)",
    )


# ── batch T7-niche-c: starting_life_matters (bucket-B, sole source) ────────
# CR 103.4 ("Each player begins the game with a starting life total of 20")
# + 103.4c (Commander: 40): phase carries no StartingLife structure — a
# genuine, long-logged representation gap (probed) — so this is the lane's
# SOLE source, no structural competitor. Relocates the deleted
# ``_STARTING_LIFE_REF`` mirror verbatim. Measured byte-identical over the
# commander-legal corpus (24/24, 0 drops, 0 adds).
def _arm_starting_life_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``starting_life_matters`` node for the "starting life
    total" phrase (the deleted ``_STARTING_LIFE_REF`` mirror relocated — no
    competing Tier-1 predicate exists, so this is the lane's SOLE
    source)."""
    if _STARTING_LIFE_REF.search(_REMINDER.sub(" ", tree.oracle or "")) is None:
        return None
    return _synthetic_concept(
        arm_id="starting_life_matters",
        concept="synth_starting_life_matters",
        scope="you",
        subject=(),
        desc="bucket-B starting-life-total residue (CR 103.4)",
    )
