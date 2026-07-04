"""ADR-0035 Stage-3b bucket (b)-COMPLETION — reuse-on-compat field corrections.

The (b) FRAMEWORK is :mod:`overlay_corrections` (a TREE-level ``ConceptNode``
overlay that decorates ``scope`` / ``subject`` / ``zones`` / ``returns_to`` and
feeds BOTH the Signal lanes and the compat Card). This module is the (b)-
COMPLETION seam — the exact mirror of bucket (c)'s :mod:`dropped_clauses`: it
REUSES the supplement's ``_recover_*`` FIELD-correction arms DIRECTLY on the
already-built compat :class:`Card`, so the flag-ON compat Card gains the SAME
field corrections the flag-OFF ``project.py`` path carries. Reuse-on-compat is
SIMPLER than a tree reimplementation and is the pattern ADR-0035 Stage-3b (c)
established; the supplement arms themselves stay in ``project.py`` /
``supplement.py`` untouched (the flag-OFF path still calls them; Stage 4 retires
that path).

**Where it runs — the compat-Card seam (Seam B), COMPAT-ONLY.** Reached solely
through :func:`compat_card`, strictly DOWNSTREAM of the (c) synthesis stage. It
never receives, reads, or writes a tree / mirror node, so the substrate-purity
invariant holds *a fortiori* (``compat_card`` already snapshots the L1 identity
around the whole build and asserts it unchanged). Because it runs on the compat
Card and NOT on the tree the Signal lanes read (``extract_crosswalk_signals``
does not call this stage), the Signal seam is UNCHANGED by construction — the
``exit_master`` signal diff is byte-identical before/after (the "reuse-on-compat
leaves signals unchanged" property the ADR-0035 Stage-3b (b) gate requires).

**Which (b) arms are ported HERE vs DEFERRED — the lossy-compat boundary.** The
compat Card under-derives fields the OLD per-ability projection carried:
``compat._effect`` sets ``raw=cnode.raw``, which the substrate populates on only
~16% of nodes; ``compat._trigger`` drops a trigger's ``recipient`` / ``source``;
``compat._effect`` derives ``counter_kind`` only as ``"all"`` / ``""`` (never the
``"top"`` / ``"topbottom"`` / ``"p1p1"`` the old projection carried). A (b) arm
whose GUARD reads one of those under-derived fields cannot fire faithfully on
this seam — reusing it would either NO-OP (a false-convergence reading, the
bucket-(c) ``_DEFERRED_RAW_ARMS`` lesson) or misfire. So only the STRUCTURE-
reading (b) arms — whose guards read fields the compat Card DOES derive
(``category`` / ``subject`` / structural siblings), grounding on the whole-card
oracle when a per-node ``raw`` is absent — are reused here:

* ``cheat_into_play_source`` — appends one canonical ``cheat_play`` marker off
  STRUCTURED sibling tutor/reveal/dig/reanimate categories (raw only refines the
  subject). Fires structurally on the seam.
* ``clone_subjects`` — refills a ``clone`` effect's dropped copied-type
  ``subject`` from a sibling effect's / the trigger's structured subject.
* ``tap_down`` — resolves the opponent anaphora on a ``tap`` / ``skip_step``
  effect (a card-level ``(card, oracle)`` arm that falls back to the WHOLE oracle
  when the per-effect ``raw`` is empty — the same whole-oracle grounding the (c)
  card-level arms use, gated on the structural ``category``).

Every ported arm is proven to move 0 cards agree→disagree in ANY of the five
dataclass consumers (ranking / budgets / cut_check / metrics / bracket) at phase
v0.15.0 — a strict per-card SUPERSET (the consumer diff HOLDS: budgets 98.08%,
cut_check 97.43%, ranking 66.35%, metrics 99.95%, bracket 99.99%, all unchanged).
The ported arms are append-only / structurally idempotent, so no convergence gate
is needed (unlike bucket (c)'s two cost/controller-discriminated arms).

The remaining LIVE (b) arms are DEFERRED off this seam (:data:`_DEFERRED_RAW_ARMS`
+ :data:`_DEFERRED_UNDERDERIVED_ARMS`) with their blocker named — they belong to
the flag-OFF path until the compat Card carries the field their guard reads (a
Stage-4 follow-on: per-node ``raw`` population + richer ``trigger`` /
``counter_kind`` derivation). Their SIGNAL-facing purpose (scaling_pump,
dig_until, play_from_top, recursion, edict, removal, …) is already reproduced by
the crosswalk's STRUCTURAL Signal lanes; only their compat-Card FIELD awaits the
richer compat derivation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from mtg_utils._card_ir.project import (
    _recover_cheat_into_play_source,
    _recover_clone_subjects,
)
from mtg_utils._card_ir.supplement import _recover_tap_down

if TYPE_CHECKING:
    from mtg_utils.card_ir import Ability, Card

# An ability-level (b) arm: ``_recover_X(ability) -> ability`` (mapped over every
# face's abilities). A card-level arm: ``_recover_X(card, oracle) -> card``.
_AbilityArm = Callable[["Ability"], "Ability"]
_CardArm = Callable[["Card", str], "Card"]


# The ability-level (b) FIELD-correction arms reused on the compat Card, in
# ``project.py``'s projection order (clone during clone-build, then cheat). Each
# fires STRUCTURALLY (reads the built abilities' categories / subjects), so a
# firing on the seam faithfully reproduces the old projection's field correction.
APPLIED_ABILITY_ARMS: tuple[tuple[str, _AbilityArm], ...] = (
    ("clone_subjects", _recover_clone_subjects),
    ("cheat_into_play_source", _recover_cheat_into_play_source),
)

# The card-level (b) FIELD-correction arms reused on the compat Card. ``tap_down``
# reads each effect's own clause ``raw`` but FALLS BACK to the whole-card oracle
# when that raw is empty (which it is on the compat seam), gated on the structural
# ``tap`` / ``skip_step`` category — the same whole-oracle grounding the bucket-(c)
# card-level arms use.
APPLIED_CARD_ARMS: tuple[tuple[str, _CardArm], ...] = (("tap_down", _recover_tap_down),)

ARM_NAMES: tuple[str, ...] = tuple(
    name for name, _ in (*APPLIED_ABILITY_ARMS, *APPLIED_CARD_ARMS)
)


# ── deferred (b) arms (off the compat seam) — blocker named ────────────────────
#
# RAW-READERS: the arm's GUARD keys on a per-effect ``e.raw`` / ``out.raw`` the
# compat Card leaves empty on ~84% of nodes (``compat._effect`` carries only the
# sparse substrate ``description``). Reusing them here would fire unreliably on
# the incidental ~16% and give a FALSE convergence reading (the bucket-(c)
# ``_DEFERRED_RAW_ARMS`` finding). They await per-node ``raw`` population (Stage 4).
_DEFERRED_RAW_ARMS: tuple[str, ...] = (
    "count_operand",  # _FOR_EACH_COUNT over the effect raw (amount->count)
    "top_of_library_owner",  # top:you/top:opp owner tag from the effect raw
    "library_zones",  # from:library from the cast-from-library raw
    "graveyard_origin",  # GY exile-origin / play-from-GY from the effect raw
    "group_hug_draw_scope",  # "each player draws" from the draw effect raw
    "destroy_subject",  # "destroy target creature" from the destroy raw
    "hybrid_exile_zone",  # battlefield-OR-graveyard exile alt from out.raw
    "opponent_exile_subject",  # per-opponent exile clause from out.raw
)

# FIELD-UNDER-DERIVED: the arm's GUARD keys on a discriminator the LOSSY compat
# Card never derives — a trigger's ``recipient`` / ``source`` (``compat._trigger``
# drops both) or an effect's fine ``counter_kind`` (``compat._effect`` derives
# only ``"all"`` / ``""``, never ``"top"`` / ``"topbottom"`` / ``"p1p1"``). The
# arm can never fire on the seam regardless of ``raw``; it awaits richer compat
# derivation (Stage 4).
_DEFERRED_UNDERDERIVED_ARMS: tuple[str, ...] = (
    "tribe_damage_source",  # needs trigger.recipient=='player' (compat drops it)
    "topdeck_stack_self",  # needs counter_kind in {top, topbottom}
    "self_counter_grow",  # needs counter_kind=='p1p1'
)


def _map_abilities(card: Card, arm: _AbilityArm) -> Card:
    """Apply one ability-level (b) arm across every face's abilities."""
    return replace(
        card,
        faces=tuple(
            replace(face, abilities=tuple(arm(ab) for ab in face.abilities))
            for face in card.faces
        ),
    )


def apply_field_corrections(card: Card, oracle: str) -> Card:
    """Reuse the (b) FIELD-correction arms on the compat ``card`` (flag-ON only).

    Runs the ported ability-level arms (mapped over every face's abilities) then
    the card-level arms, threading the card through so a later arm sees an earlier
    arm's correction — mirroring the flag-OFF ``project.py`` chain. ``oracle`` is
    the card's whole face oracle text (the card-level arms' grounding when a
    per-effect ``raw`` is absent). Each arm is append-only / structurally
    idempotent and pure; a card needing no correction is returned by identity.
    """
    for _name, arm in APPLIED_ABILITY_ARMS:
        card = _map_abilities(card, arm)
    for _name, arm in APPLIED_CARD_ARMS:
        card = arm(card, oracle)
    return card


def correct_with_trace(card: Card, oracle: str) -> tuple[Card, frozenset[str]]:
    """Like :func:`apply_field_corrections`, but also return WHICH arms fired.

    An arm "fired" when it changed the card (a dropped field it refilled) — the
    same dataclass content-inequality firing test the Stage-3b measure phase and
    bucket (c) use. Used by the gated corpus test to assert every ported arm is
    still LIVE at the pin (finds a field gap on >=1 corpus card).
    """
    fired: set[str] = set()
    for name, arm in APPLIED_ABILITY_ARMS:
        nxt = _map_abilities(card, arm)
        if nxt != card:
            fired.add(name)
        card = nxt
    for name, arm in APPLIED_CARD_ARMS:
        nxt = arm(card, oracle)
        if nxt is not card and nxt != card:
            fired.add(name)
        card = nxt
    return card, frozenset(fired)
