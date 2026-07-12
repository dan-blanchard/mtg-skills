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

from mtg_utils._card_ir.crosswalk import iter_typed_nodes, tag_of
from mtg_utils._card_ir.project import _KEYWORD_COST_SAC, _PITCH_SAC

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


# ── Degavolver / Anavolver (the APC "Volver" cycle) → lifeloss_makers ────────
# "If this creature was kicked with its {1}{B} kicker, it enters with two
# +1/+1 counters on it and with 'Pay 3 life: Regenerate this creature.'" —
# phase parses the +1/+1-counter half of the replacement (a typed
# ``PutCounter`` node) but drops the quoted granted-ability half entirely:
# ZERO trace anywhere in the tree, not even an ``Unimplemented`` residue (CR
# 119.4/CR 601.2f — kicker is an announced additional cost the grant itself
# never becomes a node for). The gap check is an ABSENCE proof (no PayLife /
# GrantAbility node reachable anywhere) rather than a residue-presence read,
# since phase leaves no residue to point at.
_DEGAVOLVER_RX = re.compile(
    r"kicked with its[^.]*kicker,? it enters with[^.]*and with\s*\""
    r"[^\"]*\bpay\s+\d+\s+life\b",
    re.IGNORECASE,
)


def _degavolver_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in ("PayLife", "GrantAbility"):
                return False
    return True


def _degavolver_match(tree: ConceptTree) -> bool:
    return bool(_DEGAVOLVER_RX.search(tree.oracle))


# ── Withercrown → lifeloss_makers ────────────────────────────────────────────
# "Enchanted creature has base power 0 and has 'At the beginning of your
# upkeep, you lose 1 life unless you sacrifice this creature.'" — phase's
# trigger parser recognizes the GRANTED trigger shape but fails the "unless"
# clause it wraps, parking the WHOLE granted-trigger body as
# ``Unimplemented(name='Unsupported unless clause')`` nested under the
# GrantTrigger modification's own ``trigger.execute.effect`` — OUTSIDE
# ``apply_unimplemented_recovery``'s ``unit.effects``-only scan (CR
# 119.3/119.4). Corpus-verified narrow: 8 of 65 "Unsupported unless clause"
# residues corpus-wide mention life loss at all, and of those the OTHER 3
# distinct cards (Archfiend of Spite, Court of Ambition, Remorseless
# Punishment) are third-person OPPONENT-directed punishers ("target opponent
# loses N life unless ...") — a DIFFERENT scope shape this bridge's
# self-scoped anchor ("^you lose") deliberately excludes (legacy parity; see
# the module docstring's "beyond-legacy breadth" note — NOT fired here, left
# for the grammar sprint).
_WITHERCROWN_RX = re.compile(r"^you lose \d+ life unless\b", re.IGNORECASE)


def _unless_clause_failure_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) == "Unimplemented"
                and getattr(n, "name", None) == "Unsupported unless clause"
            ):
                yield getattr(n, "description", "") or ""


def _withercrown_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _unless_clause_failure_descs(tree))


def _withercrown_match(tree: ConceptTree) -> bool:
    return any(_WITHERCROWN_RX.search(d) for d in _unless_clause_failure_descs(tree))


# ── Night Shift of the Living Dead → lifeloss_makers ─────────────────────────
# "After you roll a die, you may pay 1 life. If you do, increase or decrease
# the result by 1." — phase's clause grammar recognizes the die-roll trigger
# shape but fails the optional "you may pay 1 life. If you do, ..." rider,
# parking the WHOLE top-level ability effect as
# ``Unimplemented(name='unknown')`` (role=effect — WITHIN
# ``apply_unimplemented_recovery``'s scan scope, but the grammar's token
# table has no entry for this specific idiom yet; ADR-0039 forbids adding
# one this session). Anchored to the die-roll framing specifically so this
# bridge does NOT also fire for Yavimaya Bloomsage // Channel's structurally
# similar but CR-118.8-excluded "any time you could activate a mana ability,
# you may pay 1 life" mana-ability rider (a genuine painland shape, already
# excluded via the ramp effect sitting alongside it in the same unit).
_NIGHT_SHIFT_RX = re.compile(
    r"after you roll a die[^.]*\bpay\s+\d+\s+life\b", re.IGNORECASE
)


def _unimplemented_effect_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for cn in unit.effects:
            if tag_of(cn.node) == "Unimplemented":
                yield getattr(cn.node, "description", "") or ""


def _night_shift_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _unimplemented_effect_descs(tree))


def _night_shift_match(tree: ConceptTree) -> bool:
    return any(_NIGHT_SHIFT_RX.search(d) for d in _unimplemented_effect_descs(tree))


# ── Zuko, Conflicted → lifeloss_makers ───────────────────────────────────────
# "At the beginning of your first main phase, choose one that hasn't been
# chosen and you lose 2 life — [4 modes]." The life loss is UNCONDITIONAL
# across every mode (CR 700.2 — a modal ability's shared cost/effect
# outside the mode list), but phase's modal parser drops it WHOLESALE: the
# trigger's own ``execute.effect`` is a bare ``GenericEffect`` placeholder
# (no LoseLife, no PayLife — not even an Unimplemented residue) and NONE of
# the 4 ``mode_abilities`` carry it either. ZERO trace, same absence-proof
# gap shape as the Degavolver/Anavolver and Warp/Blitz/Morph bridges above.
_ZUKO_RX = re.compile(r"choose one[^.]*\band you lose \d+ life\b", re.IGNORECASE)


def _zuko_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in ("PayLife", "LoseLife"):
                return False
    return True


def _zuko_match(tree: ConceptTree) -> bool:
    return bool(_ZUKO_RX.search(tree.oracle))


# ── Warp / Blitz / Morph life-cost cycle → lifeloss_makers ──────────────────
# "Warp—{B}, Pay 2 life." (Timeline Culler), "Blitz—{2}{B}{B}, Pay 2 life."
# (Tenacious Underdog), "Morph—Pay 5 life." (Zombie Cutthroat). Unlike
# Flashback (a full ``Composite``/``PayLife`` structure rides
# ``root.keywords``, see :func:`_keyword_cost_paylife_concepts`), phase
# v0.20.0 drops these three newer alternative-casting keywords WHOLESALE —
# ``root.keywords`` doesn't even carry a bare variant entry for them, let
# alone a cost payload (CR 702.1/601.2f: an alternative way to cast the
# card, phase's keyword grammar frontier). ZERO trace anywhere in the tree.
_KEYWORD_DROPPED_RX = re.compile(
    r"\b(?:Warp|Blitz|Morph|Ninjutsu)—[^.]*\bpay\s+\d+\s+life\b",
    re.IGNORECASE,
)


def _keyword_dropped_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in ("PayLife", "GrantAbility"):
                return False
    return True


def _keyword_dropped_match(tree: ConceptTree) -> bool:
    return bool(_KEYWORD_DROPPED_RX.search(tree.oracle))


# ── sacrifice_outlets residual class (ADR-0039 W7) ────────────────────────
# Six bridges close the "NO typed Sacrifice node ANYWHERE in the tree"
# residual bucket (a card-level gap — the crosswalk's own
# ``iter_typed_nodes`` walk, corpus-verified against the SAME shape legacy's
# ``project.py._sacrifice_grant_markers`` gates its own regex fallback on:
# "no structural sacrifice effect anywhere" — so a card with a Sacrifice
# node ELSEWHERE on the SAME card, even for an unrelated edict clause,
# correctly stands every one of these bridges down, matching legacy's own
# gating exactly). CR 701.21a throughout.
_REMINDER_RX = re.compile(r"\([^)]*\)")


def _no_typed_sacrifice_node(tree: ConceptTree) -> bool:
    """The shared gap for every ``sacrifice_outlets`` bridge below: no
    ``Sacrifice``-tagged node reachable anywhere in the tree. Self-retiring
    by construction — the day phase decomposes any of these idioms into a
    typed Sacrifice cost/effect node, every bridge below stands down on
    that card without any further edit."""
    return not any(
        tag_of(n) == "Sacrifice"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _sac_kept(tree: ConceptTree) -> str:
    """Reminder-stripped oracle text — mirrors legacy's OWN paren-strip
    (``project.py._sacrifice_grant_markers``'s ``re.sub(r"\\([^)]*\\)", ...
    )``) so a bridge's blast radius matches legacy's byte-for-byte, not an
    independently-invented pattern."""
    return _REMINDER_RX.sub(" ", tree.oracle or "")


# (1) A free-spell / alternative-cost pitch ("You may sacrifice three
# artifacts rather than pay this spell's mana cost." — Salvage Titan; CR
# 118.9). Reuses legacy's OWN ``_PITCH_SAC`` regex verbatim (not a
# re-derived pattern) so the count-word limitation ("four" isn't in
# ``_SAC_COUNT``, so Hand of Emrakul's "sacrifice four Eldrazi Spawn"
# correctly stays UNMATCHED, matching legacy) and the land-type exclusion
# (``_SAC_TYPE`` never includes "land"/a land subtype, so Fireblast's
# "sacrifice two Mountains" stays land_sacrifice_makers territory) are
# legacy-parity BY CONSTRUCTION, not independently re-verified.
def _sac_pitch_match(tree: ConceptTree) -> bool:
    return bool(_PITCH_SAC.search(_sac_kept(tree)))


# (2) A keyworded-ability cost sacrifice ("Flashback—Sacrifice three
# creatures." — Dread Return; "Morph—Sacrifice another creature." — Gift of
# Doom; CR 702.34a / 702.37a / 702.27a). Reuses legacy's ``_KEYWORD_COST_SAC``
# verbatim — the SAME land-type exclusion applies (Walk the Aeons'
# "Buyback—Sacrifice three Islands" stays unmatched).
def _sac_keyword_cost_match(tree: ConceptTree) -> bool:
    return bool(_KEYWORD_COST_SAC.search(_sac_kept(tree)))


# (3) Casualty GRANTED onto ANOTHER spell, not the bearer's OWN printed
# keyword array ("The first instant or sorcery spell you cast each turn
# has casualty 2." — Anhelo, the Painter; "Each instant and sorcery spell
# you cast has casualty 1." — Silverquill, the Disputant; CR 702.153a). The
# bearer's OWN Casualty is a separate, ALREADY-STRUCTURAL Scryfall-keyword
# read (:data:`~mtg_utils._deck_forge.crosswalk_signals._SWEEP_KEYWORD_LANES`)
# — this bridge is scoped to the keyword-LESS granter only (the gap check
# excludes any card that already carries a Sacrifice node from elsewhere,
# but a granter with NO own Casualty keyword needs this text anchor
# regardless).
_SAC_CASUALTY_GRANT_RX = re.compile(r"\bhas casualty\b", re.IGNORECASE)


def _sac_casualty_grant_match(tree: ConceptTree) -> bool:
    return bool(_SAC_CASUALTY_GRANT_RX.search(_sac_kept(tree)))


# (4) Devour (CR 702.82a) parked as a bare ``Unimplemented`` residue on the
# creature's OWN body ("Devour X, where X is the number of creatures
# devoured this way" — Thromok the Insatiable) rather than a typed keyword
# entry (compare Dragon Broodmother's CREATED-TOKEN Devour, which IS
# reachable as a typed ``MirrorVariant(key='Devour')`` on the token's own
# ``keywords`` list — a genuine structural read landed this session, no
# bridge needed there).
_SAC_DEVOUR_UNIMPL_RX = re.compile(r"^devour\b", re.IGNORECASE)


def _sac_devour_unimpl_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and _SAC_DEVOUR_UNIMPL_RX.match(
                getattr(n, "description", "") or ""
            ):
                return True
    return False


def _sac_devour_unimpl_match(tree: ConceptTree) -> bool:
    return _sac_devour_unimpl_gap(tree)


# (5) A written-out (non-keyword) self-sac ETB parked as a bare
# ``Unimplemented`` residue ("As this creature enters, sacrifice any
# number of creatures. This creature's power becomes the total power of
# those creatures..." — Dracoplasm; CR 614.12 — a replacement effect that
# modifies how the permanent enters the battlefield, the same rule Devour
# itself is templated under; CR 701.21a for the sacrifice action).
_SAC_ETB_UNIMPL_RX = re.compile(
    r"as [^.]*enters[^.]*,\s*sacrifice any number of creatures", re.IGNORECASE
)


def _sac_etb_unimpl_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and _SAC_ETB_UNIMPL_RX.search(
                getattr(n, "description", "") or ""
            ):
                return True
    return False


def _sac_etb_unimpl_match(tree: ConceptTree) -> bool:
    return _sac_etb_unimpl_gap(tree)


# (6) An emblem's OWN granted activated ability whose COST is a Sacrifice
# leaf, parked entirely as opaque ``CreateEmblem.statics`` description text
# ("You get an emblem with '{1}{B}, Sacrifice a creature: You gain X life
# and draw X cards...'" — Ob Nixilis of the Black Oath; CR 602.1a — a cost
# is always paid by the activator, so an emblem's OWN granted-cost outlet
# is "you", mirroring :func:`~mtg_utils._deck_forge.crosswalk_signals.
# _sac_outlet_granted_cost`'s GrantAbility precedent). Anchored on a comma
# immediately before the IMPERATIVE "Sacrifice" (a cost position) followed
# by a colon (the cost/effect separator) — a third-person "sacrifices"
# EDICT effect inside an emblem (Sorin, Solemn Visitor's "that player
# sacrifices a creature of their choice") does NOT match: no comma-cost
# prefix, no colon, and the verb form fails the ``\bSacrifice\b`` word
# boundary against "sacrifices".
_SAC_EMBLEM_COST_RX = re.compile(
    r'emblem with\s*"[^".]*,\s*sacrifice\b[^:."]*:', re.IGNORECASE
)


def _sac_emblem_cost_match(tree: ConceptTree) -> bool:
    return bool(_SAC_EMBLEM_COST_RX.search(_sac_kept(tree)))


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
        Bridge(
            bridge_id="degavolver_kicker_paylife_regen",
            key="lifeloss_makers",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "kicker-conditional replacement 'it enters with ... and "
                'with "Pay N life: <ability>"\' drops the quoted '
                "granted-ability half with ZERO trace (no PayLife / "
                "GrantAbility node anywhere) — retires on a phase bump "
                "that structures the quoted grant"
            ),
            census=(
                "2 hits / 31,622 commander-legal (the APC 'Volver' kicker "
                "cycle: Degavolver, Anavolver), phase v0.20.0, 2026-07-11"
            ),
            pins=("Degavolver", "Anavolver"),
            gap=_degavolver_gap,
            match=_degavolver_match,
        ),
        Bridge(
            bridge_id="withercrown_unless_lose_life",
            key="lifeloss_makers",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "trigger parser's 'unless' clause handling fails a "
                "GRANTED 'you lose N life unless you sacrifice ~' body, "
                "parking it as an Unimplemented('Unsupported unless "
                "clause') residue — retires on a phase bump that "
                "structures the unless-clause payoff (a PayLife-shaped "
                "unless-cost, CR 119.4)"
            ),
            census=(
                "1 hit / 31,622 commander-legal (65 'Unsupported unless "
                "clause' residues scanned, 8 life-related across 4 "
                "distinct cards — the other 3 are third-person opponent-"
                "directed punishers this bridge's self-scoped anchor "
                "deliberately excludes; see the module comment above), "
                "phase v0.20.0, 2026-07-11"
            ),
            pins=("Withercrown",),
            gap=_withercrown_gap,
            match=_withercrown_match,
        ),
        Bridge(
            bridge_id="night_shift_optional_paylife_dieroll",
            key="lifeloss_makers",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "clause grammar's die-roll ability parser fails the "
                "optional 'you may pay 1 life. If you do, ...' rider, "
                "parking the whole ability effect as "
                "Unimplemented(name='unknown') — retires on a grammar "
                "verb / phase bump that structures the optional PayLife "
                "rider"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Night Shift of the "
                "Living Dead; Yavimaya Bloomsage // Channel's structurally "
                "similar mana-ability rider deliberately excluded by the "
                "die-roll anchor — see the module comment above), phase "
                "v0.20.0, 2026-07-11"
            ),
            pins=("Night Shift of the Living Dead",),
            gap=_night_shift_gap,
            match=_night_shift_match,
        ),
        Bridge(
            bridge_id="zuko_modal_unconditional_paylife",
            key="lifeloss_makers",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a modal "
                "ability's shared 'and you lose N life' cost/effect "
                "outside the mode list (CR 700.2) is dropped WHOLESALE — "
                "the trigger's execute.effect is a bare GenericEffect "
                "placeholder, none of the mode_abilities carry it either "
                "— retires on a phase bump that structures the shared "
                "modal rider"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Zuko, Conflicted), "
                "phase v0.20.0, 2026-07-11"
            ),
            pins=("Zuko, Conflicted",),
            gap=_zuko_gap,
            match=_zuko_match,
        ),
        Bridge(
            bridge_id="keyword_dropped_paylife",
            key="lifeloss_makers",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "Warp / Blitz / Morph keyword grammar drops a life-cost "
                "variant WHOLESALE (no keyword entry at all, unlike "
                "Flashback's Composite/PayLife structure) — retires on a "
                "phase bump that parses these keywords' own cost payload"
            ),
            census=(
                "3 hits / 31,622 commander-legal (Timeline Culler [Warp], "
                "Tenacious Underdog [Blitz], Zombie Cutthroat [Morph]), "
                "phase v0.20.0, 2026-07-11"
            ),
            pins=("Timeline Culler", "Tenacious Underdog", "Zombie Cutthroat"),
            gap=_keyword_dropped_gap,
            match=_keyword_dropped_match,
        ),
        Bridge(
            bridge_id="sac_alt_cost_pitch",
            key="sacrifice_outlets",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the Spell "
                "ability's own `cost` field is None for a CR 118.9 "
                "alternative-cost pitch ('you may sacrifice ... rather than "
                "pay this spell's mana cost') — no typed cost node survives "
                "anywhere for the mana cost OR its alternative. Retires on "
                "a phase bump that decomposes the alternative-cost clause "
                "(the grammar sprint's cast-cost-alternative verb, task #82)"
            ),
            census=(
                "9 hits / 31,622 commander-legal, no-typed-Sacrifice-node "
                "subset scanned via legacy's own _PITCH_SAC regex, phase "
                "v0.20.0, 2026-07-11 (7 siblings — Crash, Downhill Charge, "
                "Fireblast, Mine Collapse, Mogg Alarm, Pulverize, "
                "Thunderclap — are LAND-only 'sacrifice N Mountains' and "
                "stay land_sacrifice_makers territory, excluded by "
                "_PITCH_SAC's own _SAC_TYPE vocabulary; Flare of Malice "
                "and Hand of Emrakul are excluded too — the former already "
                "carries an edict Sacrifice node elsewhere on the card, the "
                "latter's 'four' count word isn't in _SAC_COUNT — both "
                "verified against legacy's own signals, neither fires there"
            ),
            pins=("Salvage Titan", "Flare of Fortitude", "Delraich"),
            gap=_no_typed_sacrifice_node,
            match=_sac_pitch_match,
        ),
        Bridge(
            bridge_id="sac_keyword_cost",
            key="sacrifice_outlets",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "Flashback/Morph/Escape/Buyback/etc. keyword's OWN "
                "alternative cost drops entirely when that cost is a "
                "Sacrifice leaf (CR 702.34/702.37) — no typed node survives "
                "for the keyword cost at all. Retires on a phase bump that "
                "decomposes a keyword-ability's alternative cost (the "
                "grammar sprint's keyword-cost verb, task #82)"
            ),
            census=(
                "3 hits / 31,622 commander-legal, no-typed-Sacrifice-node "
                "subset scanned via legacy's own _KEYWORD_COST_SAC regex, "
                "phase v0.20.0, 2026-07-11 (Worthy Cause also matches the "
                "regex but is already served by the EXISTING cast- "
                "additional-cost text idiom arm before this bridge is even "
                "reached; Walk the Aeons' 'Buyback—Sacrifice three Islands' "
                "is LAND-only, excluded by _SAC_TYPE)"
            ),
            pins=("Dread Return", "Cabal Therapy", "Gift of Doom"),
            gap=_no_typed_sacrifice_node,
            match=_sac_keyword_cost_match,
        ),
        Bridge(
            bridge_id="sac_casualty_granted_onto_other_spell",
            key="sacrifice_outlets",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a static "
                "GrantAbility whose granted text is 'has casualty N' onto "
                "spells the player casts drops the casualty grant entirely "
                "— no typed Casualty-cost node survives for the GRANT (the "
                "bearer's OWN printed Casualty keyword IS structurally "
                "reachable via the Scryfall keyword array; only the "
                "granter shape is a dropped clause). Retires on a phase "
                "bump that decomposes a granted-keyword's own cost (task "
                "#82)"
            ),
            census=(
                "3 hits / 31,622 commander-legal, no-typed-Sacrifice-node "
                "subset scanned via a `has casualty` text anchor (matching "
                "legacy's own _CASUALTY_GRANT regex), phase v0.20.0, "
                "2026-07-11 (Ashad, the Lone Cyberman also matches but is "
                "already served by its own 'sacrificed' payoff trigger — "
                "harmless redundant fire, membership dedupes)"
            ),
            pins=("Anhelo, the Painter", "Silverquill, the Disputant"),
            gap=_no_typed_sacrifice_node,
            match=_sac_casualty_grant_match,
        ),
        Bridge(
            bridge_id="sac_devour_unimplemented",
            key="sacrifice_outlets",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): an "
                "Unimplemented-residue recovery verb for 'Devour N, where "
                "N is...' text (recovery.py's Unimplemented-recovery-stage "
                "ALLOWLIST is the likely landing spot, not a NEW bridge) — "
                "retires when the node decomposes into a typed Devour/"
                "Sacrifice read the way the created-token Devour case "
                "already does structurally"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented nodes whose "
                "description starts with 'Devour', phase v0.20.0, "
                "2026-07-11 — the ONLY other Devour-keyword instance "
                "corpus-wide is Dragon Broodmother's CREATED-TOKEN Devour, "
                "which IS a typed MirrorVariant on the token's keywords "
                "list (a genuine structural read, not this bridge)"
            ),
            pins=("Thromok the Insatiable",),
            gap=_sac_devour_unimpl_gap,
            match=_sac_devour_unimpl_match,
        ),
        Bridge(
            bridge_id="sac_etb_self_sac_unimplemented",
            key="sacrifice_outlets",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): an "
                "Unimplemented-residue recovery verb for a written-out "
                "'as this creature enters, sacrifice any number of "
                "creatures, set P/T from the total' idiom (the Devour-"
                "keyword idiom's un-keyworded sibling) — retires when the "
                "node decomposes into a typed Sacrifice cost/effect"
            ),
            census=(
                "1 hit / 31,622 commander-legal, no-typed-Sacrifice-node "
                "subset scanned for the written-out ETB self-sac idiom, "
                "phase v0.20.0, 2026-07-11"
            ),
            pins=("Dracoplasm",),
            gap=_sac_etb_unimpl_gap,
            match=_sac_etb_unimpl_match,
        ),
        Bridge(
            bridge_id="sac_emblem_activated_cost",
            key="sacrifice_outlets",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): "
                "CreateEmblem's granted-ability text parks entirely as an "
                "opaque S_statics.description string — no typed activated- "
                "ability-with-cost structure survives for the emblem's OWN "
                "granted Sacrifice-cost outlet. Retires on a phase bump "
                "that decomposes an emblem's granted ability the way a "
                "GrantAbility's granted ability already is (task #82 / "
                "phase bump)"
            ),
            census=(
                "1 hit / 31,622 commander-legal, no-typed-Sacrifice-node "
                "subset scanned for a comma-cost-prefixed imperative "
                "'Sacrifice ...:' inside an emblem's quoted granted text, "
                "phase v0.20.0, 2026-07-11 (Sorin, Solemn Visitor's emblem "
                "ALSO grants a sacrifice-shaped ability but it's a "
                "third-person 'that player sacrifices' EDICT, not a cost — "
                "the comma+colon cost anchor correctly excludes it)"
            ),
            pins=("Ob Nixilis of the Black Oath",),
            gap=_no_typed_sacrifice_node,
            match=_sac_emblem_cost_match,
        ),
    )
}


def bridge_fires(bridge_id: str, tree: ConceptTree) -> bool:
    """Whether the registered bridge fires for this tree (gap AND match)."""
    return BRIDGES[bridge_id].fires(tree)
