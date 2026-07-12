"""ADR-0035 Stage-3b bucket (c) — the named dropped-clause synthesis L2 stage.

The supplement's ``_recover_*`` arms are three operations (ADR-0035 Decision).
Bucket **(c)** — *dropped-clause synthesis* — is the set of card-level
``_recover_X(card, oracle) -> Card`` arms that SYNTHESIZE structure phase dropped
ENTIRELY (a genuine parse gap: the clause survives only in the oracle text, so the
recovery re-derives the old-IR Effect / Ability it should have carried). This
module is bucket (c)'s named home.

**Where it runs (the compat-Card seam, not the tree).** A dropped clause has NO
Layer-1 mirror node to decorate — phase never emitted one — so unlike the bucket
(b) ``overlay_corrections`` stage (which re-derives fields on a *correctly-parsed*
concept node), (c) synthesis produces old-IR ``Effect`` / ``Ability`` structure
that lands on the compat :class:`Card`. It therefore runs at the ``compat_card``
seam, strictly DOWNSTREAM of the Layer-1 substrate: it never receives, reads, or
writes a tree / mirror node, so the substrate-purity invariant holds *a fortiori*
(``compat_card`` still snapshots the tree's L1 identity around the whole build and
asserts it unchanged — the shared :func:`assert_substrate_pure` guard — proving the
overlay+synthesis path left the mirror untouched).

**Faithful reuse, not reimplementation.** ADR-0035 sanctions oracle-grounding for
a GENUINE drop ("oracle-grounded ONLY for a genuine drop"), which is exactly what
these arms are. Rather than re-derive 29 bespoke oracle recoveries structurally
(there is no structure to read — phase dropped it), the stage OWNS the
application of the proven supplement arms, in the deleted ``project_card``'s
post-supplement order, so the compat card gains the SAME dropped-clause
structure the legacy ``project.py`` path carried. The supplement arms
themselves stay in ``supplement.py`` (this stage and ``field_corrections`` are
their surviving consumers; the legacy path died in ADR-0039 step 7).

**Compat-seam only.** Reached solely through ``compat_card`` (the five
dataclass-API consumers ``ranking`` / ``budgets`` / ``cut_check`` / ``metrics``
/ ``bracket``). The Signal lanes read the tree, not the compat Card, so a
dropped clause that maps to old-IR Card structure does not feed them — the signal
path is unchanged by this stage (signal-diff holds by construction); tree-node
synthesis for the few (c) clauses a Signal lane could read is a follow-on.

**The convergence contract.** Each arm is keyed by name so the input-side
convergence check (:mod:`mtg_utils._card_ir.card_ir_convergence`) can, at each pin
bump, ask whether phase NOW parses the clause — grounded on the strict mirror: an
arm that no longer FIRES on any corpus card (its structural idempotence guard
trips because the mirror already carries the structure) has CONVERGED and is
retire-ready. Every arm in :data:`SYNTHESIS_ARMS` fires on >=1 commander-legal
card at phase v0.15.0 (the gated convergence test asserts it); the six other (c)
arms are deferred off this seam (:data:`_DEFERRED_TRIGGER_ARMS` +
:data:`_DEFERRED_RAW_ARMS`).

**Per-card convergence GATES (the SUPERSET guarantee).** A handful of arm guards
read a discriminator phase parsed onto the record — a trigger subject's
``controller``, a sacrifice COST's typed target — that survives on the strict L1
mirror but is UNDER-derived by the lossy compat Card (``compat._trigger`` drops
the controller; ``compat._ability`` drops costs). Reading only the compat Card,
such a guard misfires and the arm OVER-fires on the seam, moving a card
agree→disagree in a consumer (a per-card regression, which "correctness over
card-count" forbids even under a net gain). :func:`convergence_gated_arms` reads
the SAME strict mirror the compat Card was built from and returns the arms to SKIP
because the mirror ALREADY carries the discriminator — a per-card convergence that
makes the whole stage a strict SUPERSET (no consumer moves agree→disagree). Two
arms are gated at v0.15.0: ``land_sacrifice`` (a you-side land-to-graveyard payoff
trigger the old IR suppresses on) and ``gy_recursion`` (an activated self-recursion
whose sacrifice cost the old IR promotes to a real-answer veto). Both still fire on
every non-converged corpus card, so both stay LIVE.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mtg_utils._card_ir.crosswalk import (
    ARTIFACT_TOKEN_SUBTYPES,
    trigger_subject_scope,
)
from mtg_utils._card_ir.supplement import (
    _is_gy_recursion_ability,
    _recover_base_power_ref,
    _recover_base_pt_set,
    _recover_cast_from_exile_zone,
    _recover_clone_creature,
    _recover_colorless_subject,
    _recover_cost_reduction,
    _recover_counter_removal,
    _recover_damage_reflect,
    _recover_devotion_operand,
    _recover_dies_return,
    _recover_dropped_gain_life,
    _recover_dynamic_base_pt_set,
    _recover_exile_zone_ref,
    _recover_extra_land_drop,
    _recover_facedown,
    _recover_gy_recursion,
    _recover_hand_disruption,
    _recover_historic_subject,
    _recover_keyword_grant_target,
    _recover_land_sacrifice,
    _recover_opponent_cast_lock,
    _recover_opponent_discard,
    _recover_scaling_pump,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
    from mtg_utils.card_ir import Card

# Each arm's uniform (card, oracle) -> Card shape (every applied arm reads the
# whole face oracle — the drop's only surviving evidence).
_CardArm = Callable[["Card", str], "Card"]


# The (c) synthesis arms APPLIED on the compat-Card seam, in ``project_card``'s
# post-supplement application order (project.py:858-1202). Name-keyed for the
# convergence check. Every applied arm is a WHOLE-ORACLE reader, so a 0-firing at a
# pin is a TRUE convergence signal (phase now parses the clause) — not a seam
# artifact. Two families of (c) arm are DEFERRED off this seam:
#
# * ``_DEFERRED_TRIGGER_ARMS`` — the trigger-SYNTHESIZING arms
#   combat_damage_recipients / damage_to_opp / opponent_cast_scope depend on
#   ``project.py``-only PRE-passes that structure the combat-damage / opponent-cast
#   triggers NATIVELY before the arm self-deactivates (``_attach_nested_combat_
#   damage``, the supplement's trigger re-typing). The compat base carries no such
#   native trigger, so the arm OVER-fires here and synthesizes a trigger that
#   diverges from the flag-OFF card — a measured cut_check regression (623+52+75
#   single-arm regressions vs 95+16+4 improvements at v0.15.0). Excluding them
#   holds cut_check and keeps the budgets improvement.
# * ``_DEFERRED_RAW_ARMS`` — becomes_tap_untap / modal_mass_exile / discard_unless
#   read a per-EFFECT ``raw`` the compat card leaves empty (the substrate carries
#   ``description`` on only a few nodes), so they can never fire on this seam (0 /
#   0 / 1 firings) and would give a FALSE convergence reading. They stay dormant
#   until the compat effects carry per-node raws.
#
# Both families need a structural reimplementation that reads the tree directly
# (the Stage-3b follow-on) rather than a naive card-level reuse.
SYNTHESIS_ARMS: tuple[tuple[str, _CardArm], ...] = (
    ("base_pt_set", _recover_base_pt_set),
    ("dynamic_base_pt_set", _recover_dynamic_base_pt_set),
    ("dropped_gain_life", _recover_dropped_gain_life),
    ("damage_reflect", _recover_damage_reflect),
    ("opponent_cast_lock", _recover_opponent_cast_lock),
    ("dies_return", _recover_dies_return),
    ("counter_removal", _recover_counter_removal),
    ("devotion_operand", _recover_devotion_operand),
    ("cast_from_exile_zone", _recover_cast_from_exile_zone),
    ("exile_zone_ref", _recover_exile_zone_ref),
    ("land_sacrifice", _recover_land_sacrifice),
    ("cost_reduction", _recover_cost_reduction),
    ("clone_creature", _recover_clone_creature),
    ("opponent_discard", _recover_opponent_discard),
    ("colorless_subject", _recover_colorless_subject),
    ("historic_subject", _recover_historic_subject),
    ("base_power_ref", _recover_base_power_ref),
    ("scaling_pump", _recover_scaling_pump),
    ("gy_recursion", _recover_gy_recursion),
    ("facedown", _recover_facedown),
    ("hand_disruption", _recover_hand_disruption),
    ("keyword_grant_target", _recover_keyword_grant_target),
    ("extra_land_drop", _recover_extra_land_drop),
)

# The trigger-synthesizing (c) arms deferred off the compat seam (see the note on
# ``SYNTHESIS_ARMS``): LIVE at v0.15.0 but need a structural reimplementation to
# port safely. Their legacy ``project.py`` home died in ADR-0039 step 7, so they
# are dormant until that structural tree read lands.
_DEFERRED_TRIGGER_ARMS: tuple[str, ...] = (
    "combat_damage_recipients",
    "damage_to_opp",
    "opponent_cast_scope",
)

# The per-effect-raw-dependent (c) arms deferred off the compat seam: the compat
# card leaves effect ``raw`` empty, so they cannot fire here.
_DEFERRED_RAW_ARMS: tuple[str, ...] = (
    "becomes_tap_untap",
    "modal_mass_exile",
    "discard_unless",
)

ARM_NAMES: tuple[str, ...] = tuple(name for name, _ in SYNTHESIS_ARMS)


# ── per-card convergence gates (ADR-0035 Stage-3b c) ──────────────────────────
#
# An arm's supplement guard decided IDEMPOTENCE for the legacy ``project.py``
# card by reading discriminators phase parsed onto the RECORD. A few of those
# discriminators — a trigger subject's controller, a sacrifice COST's typed
# target — survive on the strict Layer-1 MIRROR but are UNDER-derived by the
# lossy Layer-2 compat Card (``compat._trigger`` drops the controller;
# ``compat._ability`` drops costs entirely). Reading only the compat Card, the
# arm's guard misfires and the arm OVER-fires on the seam, moving a card
# agree→disagree in a consumer (a per-card regression, which "correctness over
# card-count" forbids even under a net gain).
#
# :func:`convergence_gated_arms` is the input-side convergence check the ADR
# names, applied per card: grounded on the SAME strict mirror the compat Card was
# built from, it returns the arms to SKIP because the mirror ALREADY carries the
# discriminator that makes the arm's synthesis a double-count / mis-categorization
# (phase converged on the clause). A gated card is a no-op for that arm ONLY; the
# arm still fires on every non-converged corpus card, so its firing count stays
# >0 (still LIVE — the convergence corpus test holds). Both regressions are
# mirror-grounded, so the gate reads the tree, not a fresh oracle regex.


def _land_sacrifice_converged(tree: ConceptTree, card: Card) -> bool:
    """CONVERGENCE gate for ``land_sacrifice``: the mirror already carries a
    you-side land-to-graveyard PAYOFF trigger.

    ``project._recover_land_sacrifice`` self-suppresses when a ``leaves``/``dies``
    Land-subject trigger is present with ``controller=="you"`` — the structured
    payoff phase parses from "one or more land cards are put into YOUR graveyard"
    (Turntimber Sower). ``compat._trigger`` doesn't derive the subject controller
    (always ``"any"``), so the arm's own guard can't tell that you-side payoff from
    an each/any one (Centaur Vinecrasher — "into A graveyard", ``controller=null``,
    where the old IR KEEPS the synth). We read the controller from the MIRROR
    (``trigger_subject_scope`` over the L1 node) to reproduce the old projection's
    suppression exactly: skip only the ``"you"`` case.
    """
    abilities = card.faces[0].abilities if card.faces else ()
    for unit, ab in zip(tree.units, abilities, strict=False):
        if (
            ab.trigger is not None
            and ab.trigger.event in ("leaves", "dies")
            and ab.trigger.subject is not None
            and "Land" in ab.trigger.subject.card_types
            and trigger_subject_scope(unit.node) == "you"
        ):
            return True
    return False


# The sacrifice-COST target types the old projection PROMOTES to a real-answer
# ``sacrifice`` Effect: a core Land (``_land_sacrifice_cost_markers``), a core
# Artifact/Enchantment (``_typed_sacrifice_cost_markers``), or a predefined
# ARTIFACT-token subtype (native token-sacrifice projection — Unshakable Tail's
# Clue). A core Creature (Gollum), a creature subtype, and — critically — a LAND
# SUBTYPE (Jarad's "Sacrifice a Swamp and a Forest": ``type_filters`` carry
# ``Swamp``/``Forest``, NOT the core ``Land``) are NOT promoted: the old IR
# carries no veto sibling for them, so their gy-recursion stamp is a genuine
# improvement and must stay OUT of the gate.
_PROMOTED_CORE_SAC_TYPES = frozenset({"Land", "Artifact", "Enchantment"})


def _sac_cost_target_is_promoted(cost: object) -> bool:
    """True iff a Sacrifice COST anywhere under ``cost`` (a mirror cost node's
    ``to_dict``) sacrifices an object the old projection PROMOTES to a real-answer
    ``sacrifice`` Effect — a core Land / Artifact / Enchantment, or a predefined
    ARTIFACT-token subtype (Clue / Treasure / …). Reproduces the old IR's
    ``_land_sacrifice_cost_markers`` / ``_typed_sacrifice_cost_markers`` / native
    token-sacrifice promotion so the gy_recursion gate matches ``old_real_answer``
    exactly; a creature or a LAND-SUBTYPE sacrifice (which the old IR does NOT
    promote) returns False.
    """
    if isinstance(cost, list):
        return any(_sac_cost_target_is_promoted(x) for x in cost)
    if not isinstance(cost, dict):
        return False
    if str(cost.get("type", "")).lower() == "sacrifice":
        target = cost.get("target")
        filters = target.get("type_filters") if isinstance(target, dict) else None
        for tf in filters if isinstance(filters, list) else ():
            if isinstance(tf, str) and tf in _PROMOTED_CORE_SAC_TYPES:
                return True
            if (
                isinstance(tf, dict)
                and isinstance((sub := tf.get("Subtype")), str)
                and sub.lower() in ARTIFACT_TOKEN_SUBTYPES
            ):
                return True
    return any(_sac_cost_target_is_promoted(v) for v in cost.values())


def _unit_has_promoted_sac_cost(unit: AbilityUnit) -> bool:
    """A unit's activation COST sacrifices a promoted (non-creature) object."""
    return any(_sac_cost_target_is_promoted(c.node.to_dict()) for c in unit.costs)


def _gy_recursion_converged(tree: ConceptTree, card: Card) -> bool:
    """Compat-seam over-fire gate for ``gy_recursion``: the recursion is an
    ACTIVATED self-recursion whose sacrifice COST the old IR promotes to a veto.

    ``_recover_gy_recursion`` re-stamps ``in:graveyard`` onto the CONTENTLESS
    bounce a collapsed GY-recursion TRIGGER left, discriminated in the flag-OFF
    card by the bounce's EMPTY ``raw``. Every compat effect's ``raw`` is empty, so
    that discriminator is vacuous and the arm also fires on an ACTIVATED-ability
    self-recursion ("Sacrifice X: Return this card from your graveyard" —
    Unshakable Tail's Clue, Whiteout's snow land). For those, the old IR carries
    the ability's sacrifice COST as a sibling ``sacrifice`` Effect (a real answer)
    that vetoes ``_ir_recursion_only``; ``compat._ability`` drops costs, so the
    bare stamp mis-flips the card to recursion-only — a per-card budgets
    regression. We read the dropped COST from the MIRROR: skip when the recursion
    ability's sacrifice cost is a promoted (non-creature) type, matching the old
    IR. A creature-cost self-recursion (Gollum, Jarad) carries NO old-IR veto, so
    the stamp is a genuine improvement there and is NOT gated.
    """
    abilities = card.faces[0].abilities if card.faces else ()
    for unit, ab in zip(tree.units, abilities, strict=False):
        if (
            ab.kind == "activated"
            and _is_gy_recursion_ability(ab)
            and _unit_has_promoted_sac_cost(unit)
        ):
            return True
    return False


# tree-grounded convergence gates, keyed by the arm they gate. Each reads the L1
# mirror for the discriminator the compat Card under-derives.
_CONVERGENCE_GATES: dict[str, Callable[[ConceptTree, Card], bool]] = {
    "land_sacrifice": _land_sacrifice_converged,
    "gy_recursion": _gy_recursion_converged,
}


def convergence_gated_arms(tree: ConceptTree, card: Card) -> frozenset[str]:
    """The (c) arms to SKIP for this card because the mirror has already converged.

    For each gated arm, the strict Layer-1 mirror carries the discriminator that
    would make the arm's synthesis a double-count / mis-categorization, but the
    lossy compat ``card`` under-derives it — so the arm's own guard misfires.
    Passing the result to :func:`apply_dropped_clause_synthesis` /
    :func:`synthesize_with_trace` makes the stage a strict per-card SUPERSET (no
    consumer moves agree→disagree). ``card`` is the pre-synthesis compat base
    (``compat.compat_card_base``); its abilities run parallel to ``tree.units``.
    """
    return frozenset(
        name for name, gate in _CONVERGENCE_GATES.items() if gate(tree, card)
    )


def apply_dropped_clause_synthesis(
    card: Card, oracle: str, *, skip: frozenset[str] = frozenset()
) -> Card:
    """Synthesize every dropped (c) clause onto the compat ``card``.

    Runs the bucket-(c) arms over ``card`` in ``project_card``'s order, threading
    the card through so a later arm sees an earlier arm's synthesis (mirroring the
    legacy chain). ``oracle`` is the card's whole face oracle text (the drop's
    only surviving evidence). ``skip`` names the arms a mirror-grounded convergence
    gate found already-satisfied on this card (:func:`convergence_gated_arms`), so
    the synthesis is a strict per-card SUPERSET (it may move a consumer
    agree→agree or disagree→agree, never agree→disagree). Idempotent per arm and
    pure. A card needing no synthesis is returned by identity.
    """
    for name, arm in SYNTHESIS_ARMS:
        if name in skip:
            continue
        card = arm(card, oracle)
    return card


def synthesize_with_trace(
    card: Card, oracle: str, *, skip: frozenset[str] = frozenset()
) -> tuple[Card, frozenset[str]]:
    """Like :func:`apply_dropped_clause_synthesis`, but also return WHICH arms fired.

    An arm "fired" when it changed the card (a dropped clause it found + synthesized
    — the mirror-grounded gap signal the convergence check reads: an arm that fires
    on NO corpus card has converged, because phase now parses the clause and the
    arm's structural guard trips). A ``skip``-listed (convergence-gated) arm is a
    no-op and never counts as a firing, so a per-card convergence reads the same as
    a corpus-wide one. The firing test is dataclass content-inequality, matching
    the Stage-3b measure phase's detector.
    """
    fired: set[str] = set()
    for name, arm in SYNTHESIS_ARMS:
        if name in skip:
            continue
        nxt = arm(card, oracle)
        if nxt is not card and nxt != card:
            fired.add(name)
        card = nxt
    return card, frozenset(fired)
