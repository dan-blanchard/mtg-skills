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
(there is no structure to read — phase dropped it), the stage OWNS the flag-ON
application of the proven supplement arms, in ``project_card``'s post-supplement
order, so the flag-ON compat card gains the SAME dropped-clause structure the
flag-OFF ``project.py`` path carries. The supplement arms themselves stay in
``supplement.py`` (the flag-OFF path still calls them); Stage 4 retires that path.

**Flag-ON only.** Reached solely through ``compat_card`` (the five dataclass-API
consumers ``ranking`` / ``budgets`` / ``cut_check`` / ``metrics`` / ``bracket``);
the flag-OFF ``project.py`` projection builds the same structure natively and
never reaches here. The Signal lanes read the tree, not the compat Card, so a
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
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mtg_utils._card_ir.supplement import (
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
#   0 / 1 firings) and would give a FALSE convergence reading. They belong to the
#   flag-OFF path until the compat effects carry per-node raws.
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
# port safely, so the flag-OFF ``project.py`` path remains their only home.
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


def apply_dropped_clause_synthesis(card: Card, oracle: str) -> Card:
    """Synthesize every dropped (c) clause onto the compat ``card`` (flag-ON only).

    Runs the bucket-(c) arms over ``card`` in ``project_card``'s order, threading
    the card through so a later arm sees an earlier arm's synthesis (mirroring the
    flag-OFF chain). ``oracle`` is the card's whole face oracle text (the drop's
    only surviving evidence). Idempotent per arm (each guards on the structure it
    would add) and pure. A card needing no synthesis is returned by identity.
    """
    for _name, arm in SYNTHESIS_ARMS:
        card = arm(card, oracle)
    return card


def synthesize_with_trace(card: Card, oracle: str) -> tuple[Card, frozenset[str]]:
    """Like :func:`apply_dropped_clause_synthesis`, but also return WHICH arms fired.

    An arm "fired" when it changed the card (a dropped clause it found + synthesized
    — the mirror-grounded gap signal the convergence check reads: an arm that fires
    on NO corpus card has converged, because phase now parses the clause and the
    arm's structural guard trips). The firing test is dataclass content-inequality,
    matching the Stage-3b measure phase's detector.
    """
    fired: set[str] = set()
    for name, arm in SYNTHESIS_ARMS:
        nxt = arm(card, oracle)
        if nxt is not card and nxt != card:
            fired.add(name)
        card = nxt
    return card, frozenset(fired)
