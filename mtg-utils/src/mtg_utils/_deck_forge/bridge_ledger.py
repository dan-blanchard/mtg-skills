"""Ledgered bridges (ADR-0039) — the sanctioned straggler-serving mechanism.

A **ledgered bridge** is a gap-gated, corpus-bounded, self-retiring text read
that serves a signal lane where the typed substrate genuinely cannot yet: a
grammar straggler, a dropped clause, a missing face, or an upstream parse
failure. Bridges exist so the legacy-IR deletion (ADR-0039 / task #80) never
drops a legacy-served member — each bridge keeps its laggard cards served
until the post-deletion grammar sprint (task #82) or a phase bump lands the
real structure.

Every bridge is REGISTERED here, never written inline in a lane. A row
carries:

* ``gap`` — the machine-checkable evidence the typed substrate still lacks
  the structure. This is what makes a bridge SELF-RETIRING: when a grammar
  verb / phase bump lands the structure, ``gap`` goes False, the bridge stops
  firing, and the convergence test flags the row for deletion.
* ``match`` — the bounded text/idiom read. ``census`` records the authored
  blast radius (how many corpus cards the pattern hits, at which phase tag),
  so a reviewer can see the bridge is a scalpel, not a regex lane.
* ``todo`` — the NAMED grammar TODO or upstream report that retires it. A
  bridge with no retirement path is a regex detector wearing a costume; the
  ledger forbids it by construction.

A bridge FIRES only when ``gap AND match`` — the gate guarantees a bridge
can never shadow (or fight) a real structural read of the same card.

**The convergence hook** is ``tests/mtg-utils/test_bridge_ledger.py``: for
every row and every pinned fixture card it asserts ``gap`` still holds (a
False ``gap`` fails RETIRE-READY: delete the row + its lane call, rewrite the
mechanism pin structural, keep the membership pin — the graduation rule) and
``match`` still hits (pattern rot fails loudly). Laggards stay visible at
every fixture regen; nothing retires silently.

Bridges mirror LEGACY's serving only — beyond-legacy breadth is the typed
substrate's job. A bridge that "could also" open a sibling lane records that
as a note for the grammar sprint instead of widening its own read.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._card_ir.crosswalk import tag_of

if TYPE_CHECKING:  # pragma: no cover
    from mtg_utils._card_ir.crosswalk import ConceptTree

# The four residue classes a bridge may serve (mtg-utils/CONTEXT.md):
# a grammar straggler (our clause grammar's frontier), a dropped clause
# (phase emits nothing), a missing face (W2c text-only tree), an upstream
# parse failure (phase tried and failed — diagnostic residue preserved).
BRIDGE_KINDS = frozenset(
    {
        "grammar_straggler",
        "dropped_clause",
        "missing_face",
        "upstream_parse_failure",
    }
)


@dataclass(frozen=True)
class Bridge:
    """One ledger row. See the module docstring for the field contracts."""

    bridge_id: str
    key: str  # the signal key served (legacy parity, one key per row)
    kind: str  # one of BRIDGE_KINDS
    todo: str  # the named grammar TODO / upstream report that retires this
    census: str  # authored blast radius: hits + corpus + phase tag + date
    pins: tuple[str, ...]  # representative fixture card names
    gap: Callable[[ConceptTree], bool]  # substrate still lacks the structure
    match: Callable[[ConceptTree], bool]  # the bounded text/idiom read

    def fires(self, tree: ConceptTree) -> bool:
        """Gap-gated firing — a landed structural read stands the bridge down."""
        return self.gap(tree) and self.match(tree)


def _static_parse_failure_descs(tree: ConceptTree) -> Iterator[str]:
    """Descriptions of phase's ``static_structure`` parse-failure residues.

    Phase's static parser, on a line it recognizes but cannot structure,
    parks the WHOLE line as ``Unimplemented(name='static_structure')`` with a
    "Static pattern matched but line failed static parser: <line>" diagnostic
    (116 nodes corpus-wide at v0.20.0). The line text survives only there, so
    an upstream_parse_failure bridge both gap-checks and reads that node.
    """
    for unit in tree.units:
        for cn in unit.iter_concepts():
            node = cn.node
            if (
                tag_of(node) == "Unimplemented"
                and getattr(node, "name", None) == "static_structure"
            ):
                yield getattr(node, "description", "") or ""


# ── Bello, Bard of the Brambles → artifacts_matter ───────────────────────────
# "During your turn, each non-Equipment artifact and non-Aura enchantment you
# control with mana value 4 or greater is a 4/4 Elemental creature ..." — an
# artifact-animation payoff (CR 301; the legacy IR fires artifacts_matter).
# Phase v0.20.0's static parser fails the whole line (upstream candidate);
# no typed node exists anywhere to read. NOTE for the grammar sprint: the
# same line also names enchantment animation — legacy does NOT fire
# enchantments_matter here, so this bridge stays legacy-parity and leaves
# that breadth to the eventual structural read.
_BELLO_ANIMATE_RX = re.compile(
    r"each [^.]*artifact[^.]*you control[^.]*\bis an? \d+/\d+[^.]*\bcreature\b",
    re.IGNORECASE,
)


def _bello_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _static_parse_failure_descs(tree))


def _bello_match(tree: ConceptTree) -> bool:
    return any(_BELLO_ANIMATE_RX.search(d) for d in _static_parse_failure_descs(tree))


BRIDGES: dict[str, Bridge] = {
    b.bridge_id: b
    for b in (
        Bridge(
            bridge_id="bello_static_animate_artifacts",
            key="artifacts_matter",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): static "
                "parser fails 'During your turn, each non-Equipment artifact "
                "and non-Aura enchantment you control ... is a 4/4 Elemental "
                "creature' — retires on a phase bump that parses the line"
            ),
            census=(
                "1 hit / 31,622 commander-legal (116 static_structure "
                "failures scanned), phase v0.20.0, 2026-07-11"
            ),
            pins=("Bello, Bard of the Brambles",),
            gap=_bello_gap,
            match=_bello_match,
        ),
    )
}


def bridge_fires(bridge_id: str, tree: ConceptTree) -> bool:
    """Whether the registered bridge fires for this tree (gap AND match)."""
    return BRIDGES[bridge_id].fires(tree)
