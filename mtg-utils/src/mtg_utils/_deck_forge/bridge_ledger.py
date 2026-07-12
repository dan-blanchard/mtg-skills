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

from mtg_utils._card_ir.crosswalk import (
    effect_filter,
    effect_reaches_player,
    filter_core_types,
    filter_subtypes,
    iter_typed_nodes,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MISSING
from mtg_utils._card_ir.project import _KEYWORD_COST_SAC, _PITCH_SAC

if TYPE_CHECKING:  # pragma: no cover
    from mtg_utils._card_ir.crosswalk import ConceptTree

# Land subtypes (CR 205.3i), duplicated (not imported) from crosswalk_signals.
# _LAND_SUBTYPES: crosswalk_signals.py imports ``bridge_fires`` FROM this
# module, so importing the other way would be circular.
_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "gate",
        "desert",
        "lair",
        "locus",
        "mine",
        "power-plant",
        "tower",
        "urza's",
        "cave",
        "sphere",
        "town",
    }
)

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


# ── cheat_into_play residual class (ADR-0039 W7 endgame) ────────────────────
# Six bridges close the LAST 20 of the key's residual live_only set (40 at
# session start; 3 closed structurally — Dr. Eggman/Impromptu Raid's scan-
# scope descent, Telemin Performance's reveal_until-sibling origin trust,
# all in crosswalk_signals.py; 17 adjudicated as sheds — legacy over-fires
# a land-only-restricted put [CR 305.1: playing a land is a special action,
# never a cast — the SAME carve-out already excludes Boreas Charger et al.]
# or a name-match-only / bare-'Card' filter that carries ZERO type
# restriction [CR 201.1 names a card's name as its own characteristic,
# distinct from CR 205.1's type line — never guess a Land could be
# excluded by trusting a filter that can't tell]). CR 601.2 (casting
# defined) / CR 110.4a (permanent card) throughout for the "put onto the
# battlefield WITHOUT casting" idiom itself.
def _cheat_unimplemented_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented":
                yield getattr(n, "description", "") or ""


# (1) A swallowed THIRD-PERSON leading-subject clause ("For each of those
# creatures, its controller reveals..."; "who received no votes may put...";
# "You do the same with the top three cards..."). Phase's clause grammar
# has no token for a leading referent/relative-clause before the actual
# imperative (the post-deletion grammar sprint's ``_PLAYER_PREFIX`` token,
# task #82) so it parks the WHOLE clause as an opaque ``Unimplemented``,
# under ``unit.effects`` (role=effect — within the recovery stage's scan
# scope, but the grammar token itself doesn't exist yet). Anchored to each
# card's own verbatim leading phrase (never a bare first-word check — the
# Unimplemented decorator's ``name`` field is just the clause's own first
# word, "for"/"who"/"you"/"those"/"secretly", far too common to gate on
# alone) PLUS a tree-wide "onto the battlefield" requirement (Soul of
# Emancipation's "For each of those permanents, its controller creates a
# 3/3 Angel..." shares the SAME leading-subject shape but is a token maker,
# not a cheat — excluded since it never mentions "onto the battlefield" at
# all).
_CHEAT_PLAYER_PREFIX_RX = re.compile(
    r"^(?:"
    r"for each of those \w+, (?:its controller|you may put)|"
    r"who (?:received no votes may put|"
    r"sacrificed a permanent this way reveals|"
    r"shuffled a nontoken creature into their library this way reveals)|"
    r"you do the same with the top three cards of your library"
    r")",
    re.IGNORECASE,
)


def _cheat_player_prefix_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _cheat_unimplemented_descs(tree))


def _cheat_player_prefix_match(tree: ConceptTree) -> bool:
    if "onto the battlefield" not in (tree.oracle or "").lower():
        return False
    return any(
        _CHEAT_PLAYER_PREFIX_RX.search(d) for d in _cheat_unimplemented_descs(tree)
    )


# (2) A DROPPED clause with the type/count evidence specifically degraded —
# CONTEXT.md's third residue class: the tree HAS nodes, just degraded (an
# emptied ``SearchLibrary``/``Dig``/``RevealUntil`` filter — Curse of
# Misfortunes' "for a Curse card" self-reference drops to ``type_filters:
# []``, Empty the Laboratory's "equal to the number of Zombies sacrificed"
# dynamic count drops to a bare ``Fixed(1)``/``Any()`` filter; a swallowed
# CONDITION with zero residue at all — Matter Reshaper's "if it's a
# permanent card with mana value 3 or less" and Eladamri's "if you reveal a
# creature card this way" both vanish with no Unimplemented node, no
# condition field, nothing; or the reveal/selection MECHANISM itself never
# becomes a node — Turntimber Symbiosis's "look at the top seven cards...
# put a creature card...onto the battlefield" survives only as the
# CONSEQUENCE replacement [+1/+1 counters if mv<=3], Game Preserve's
# symmetric "if all cards revealed are creature cards, put them onto the
# battlefield" has NO node past the bare ``RevealTop``, Wakanda Forever!'s
# ``Dig`` collapses the "onto the battlefield WITH a counter" OR "into your
# hand" modal choice to a single ``destination: Hand``, and Green Sun's
# Twilight's X-gated modal destination swallows into an Unimplemented
# 'choose' with the ACTUAL destination logic nowhere reachable). Gap is an
# ABSENCE proof over the SAME core/subtype helpers the structural arms use
# — self-retiring the moment any of these nodes' filter/count/destination
# lands real evidence (the structural arm fires on its own, no edit here).
def _cheat_no_battlefield_type_evidence(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            tg = tag_of(n)
            if tg in ("ChangeZone", "ChangeZoneAll"):
                if getattr(n, "destination", None) != "Battlefield":
                    continue
                filt = effect_filter(n)
                cores = set(filter_core_types(filt))
                if cores and not cores <= {"Land"}:
                    return False
                if not cores:
                    subs = {s.lower() for s in filter_subtypes(filt)}
                    if subs and not subs & _LAND_SUBTYPES:
                        return False
            elif tg == "RevealUntil":
                if getattr(n, "kept_destination", None) != "Battlefield":
                    continue
                filt = effect_filter(n)
                cores = set(filter_core_types(filt))
                if cores and not cores <= {"Land"}:
                    return False
                if not cores:
                    subs = {s.lower() for s in filter_subtypes(filt)}
                    if subs and not subs & _LAND_SUBTYPES:
                        return False
    return True


_CHEAT_DROPPED_CLAUSE_RX = re.compile(
    r"(?:"
    r"you may put that card onto the battlefield if it's a permanent card "
    r"with mana value \d+ or less|"
    r"if you reveal a creature card this way, put it onto the battlefield|"
    r"that doesn't have the same name as a \S+ attached to enchanted "
    r"player, put it onto the battlefield|"
    r"put those cards onto the battlefield and the rest on the bottom of "
    r"your library|"
    r"put a creature card from among them onto the battlefield\. if that "
    r"card has mana value|"
    r"put a permanent card from among them onto the battlefield with an "
    r"indestructible counter|"
    r"if all cards revealed this way are creature cards, put those cards "
    r"onto the battlefield|"
    r"if x is 5 or more, instead put the chosen cards onto the battlefield"
    r")",
    re.IGNORECASE,
)


def _cheat_dropped_clause_match(tree: ConceptTree) -> bool:
    return bool(tree.oracle and _CHEAT_DROPPED_CLAUSE_RX.search(tree.oracle))


# (3) A ``RevealUntil`` whose ``kept_destination`` reads 'Hand' even though
# the card text puts the revealed card onto the BATTLEFIELD — an upstream
# mis-parse (the revealer and the putter are DIFFERENT actors: "its
# controller reveals... puts that card onto the battlefield" — Chaos
# Mutation, Chaotic Transformation). No typed Battlefield destination
# survives anywhere for this clause; :func:`_cheat_no_battlefield_type_
# evidence` is the shared gap.
_CHEAT_KEPT_DEST_MISPARSE_RX = re.compile(
    r"(?:"
    r"its controller reveals cards from the top of their library until "
    r"they reveal a creature card, puts that card onto the battlefield|"
    r"its controller reveals cards from the top of their library until "
    r"they reveal a card that shares a card type with it, puts that card "
    r"onto the battlefield"
    r")",
    re.IGNORECASE,
)


def _cheat_kept_dest_misparse_match(tree: ConceptTree) -> bool:
    return bool(tree.oracle and _CHEAT_KEPT_DEST_MISPARSE_RX.search(tree.oracle))


# (4) A swallowed "choose a [type] card from among them" (Unimplemented,
# name='choose', description containing "from among them") whose sibling
# Battlefield put carries ``origin: 'Graveyard'`` — a phase-side origin
# MIS-TAG (the source is the just-revealed LIBRARY pile, not a graveyard;
# CR 400.7 zones don't reorder themselves), which the main arm's reanimation
# carve-out (never trusts Graveyard origin) correctly-but-wrongly excludes.
# Corpus-verified narrow (2026-07, every commander-legal Unimplemented
# 'choose'+'from among them' residue paired with a Battlefield-destined
# put in the SAME unit): Animal Magnetism, Selective Adaptation are the
# ONLY two carrying that Graveyard-origin sibling (Guided Passage, Manifold
# Insights, Kaya's Spirits' Justice, Capricious Hellraiser, Green Sun's
# Twilight all share the "choose... from among them" shape but carry NO
# Battlefield-destined node in the unit at all — a different, ungated
# residue class; Green Sun's Twilight is bridge (2) above instead).
def _cheat_choose_among_gap(tree: ConceptTree) -> bool:
    return any("from among them" in d.lower() for d in _cheat_unimplemented_descs(tree))


def _cheat_choose_among_match(tree: ConceptTree) -> bool:
    if not any(
        "choose" in d.lower() and "from among them" in d.lower()
        for d in _cheat_unimplemented_descs(tree)
    ):
        return False
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) in ("ChangeZone", "ChangeZoneAll")
                and getattr(n, "destination", None) == "Battlefield"
                and getattr(n, "origin", None) == "Graveyard"
            ):
                return True
    return False


# (5) Ao, the Dawn Sky's own MODAL parser diagnostic, named exactly
# ``modal_mode_unsupported_qualifier`` (phase's modal grammar can't
# structure a "total mana value N or less" qualifier on a "put any number
# of nonland permanent cards... onto the battlefield" mode) — anchored to
# that literal diagnostic name, corpus-verified sole hit.
def _cheat_modal_unsupported_gap(tree: ConceptTree) -> bool:
    return any(
        True
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
        if tag_of(n) == "Unimplemented"
        and getattr(n, "name", None) == "modal_mode_unsupported_qualifier"
    )


def _cheat_modal_unsupported_match(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Unimplemented":
                continue
            if getattr(n, "name", None) != "modal_mode_unsupported_qualifier":
                continue
            desc = (getattr(n, "description", "") or "").lower()
            if "onto the battlefield" in desc:
                return True
    return False


# (6) Synthetic Destiny's delayed-trigger reveal-until node: the recovery
# stage already re-decorates this ``Unimplemented`` with concept
# ``reveal_until`` (the node's raw text names the idiom), but the raw node
# itself carries no typed ``kept_destination`` field — a raw-text
# destination read would be a NEW heuristic pattern invented for this one
# card, so it stays a bridge anchored to the recovered node's own raw
# rather than extending the recovered-raw-read precedent to a field this
# tag doesn't have. Corpus-verified sole hit.
def _cheat_synthetic_destiny_gap(tree: ConceptTree) -> bool:
    return any(
        True
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
        if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "reveal"
    )


_CHEAT_SYNTHETIC_DESTINY_RX = re.compile(
    r"reveal cards from the top of your library until you reveal that "
    r"many creature cards, put all creature cards revealed this way onto "
    r"the battlefield",
    re.IGNORECASE,
)


def _cheat_synthetic_destiny_match(tree: ConceptTree) -> bool:
    return any(
        _CHEAT_SYNTHETIC_DESTINY_RX.search(d) for d in _cheat_unimplemented_descs(tree)
    )


# ── direct_damage — shared gap for the whole dropped-clause/upstream-parse-
# failure residual (ADR-0039 W7 endgame) ─────────────────────────────────────
# No ``DealDamage``/``DamageAll``/``DamageEachPlayer`` node ANYWHERE in the
# tree structurally reaches a player (the lane's own ``effect_reaches_player``
# / ``has_nested_damage_reaching_player`` checks both already missed, or the
# tree carries no such node at all — including a phase-missing face with ZERO
# units, Insult // Injury's Aftermath back half). Self-retiring PER CARD: the
# day phase decomposes any one idiom below into a typed damage node whose
# recipient resolves, this shared gap goes False for THAT card specifically
# (``effect_reaches_player`` finds it and returns early) while staying True
# for every other card still missing its own structure — the
# ``_no_typed_sacrifice_node`` precedent, same shared-broad-gap /
# narrow-per-bridge-match shape.
def _no_player_reaching_damage_node(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) in (
                "DealDamage",
                "DamageAll",
                "DamageEachPlayer",
            ) and effect_reaches_player(n, unit.node):
                return False
    return True


# (1) "deals N damage to target creature and X damage to that creature's/
# permanent's controller" (Judgment Bolt, Liquid Fire, Synchronized
# Spellcraft; CR 102.1 — a controller is a player) — phase structures ONLY
# the first (creature) clause; the second (controller-damage) clause carries
# NO node anywhere, typed or ``Unimplemented``. Reuses the exact wording
# legacy's OWN ``_DIRECT_DAMAGE_MIRROR`` alternative anchors on.
_DMG_CREATURE_CONTROLLER_RX = re.compile(
    r"(?:\d+|x) damage to (?:that creature's|that permanent's) controller",
    re.IGNORECASE,
)


def _dmg_creature_controller_match(tree: ConceptTree) -> bool:
    return bool(_DMG_CREATURE_CONTROLLER_RX.search(tree.oracle or ""))


# (2) Vexing Arcanix's "... they put it into their graveyard and ~ deals 2
# damage to them" — the trailing damage clause is dropped after an
# ``Unimplemented(name='otherwise')`` residue; a SEPARATE upstream bug also
# misreads the earlier ``RevealTop.player`` as ``Controller()`` instead of
# the activated ability's OWN targeted player (out of THIS bridge's scope —
# the damage recipient text alone is what direct_damage needs).
_VEXING_ARCANIX_RX = re.compile(
    r"put(?:s)? it into their graveyard and [^.]*deals? \d+ damage to them",
    re.IGNORECASE,
)


def _vexing_arcanix_match(tree: ConceptTree) -> bool:
    return bool(_VEXING_ARCANIX_RX.search(tree.oracle or ""))


# (3) Curse of Shaken Faith's "Enchant player" + "... this Aura deals 2
# damage to them" (CR 303.4c) — the Aura's OWN enchant-target TYPE (player,
# vs. creature/permanent) lives nowhere in the tree: ``AttachedTo`` is a bare
# zero-field marker tag shared by every enchant-restriction, so the sibling
# ``ParentTarget`` damage recipient can never structurally resolve. Corpus-
# verified: of 42 commander-legal "Enchant player" Auras, only this one both
# matches the idiom AND still lacks a typed reach (Curse of the Pierced
# Heart's structurally-identical-looking "that player" is ALREADY a typed
# ``Or[TriggeringPlayer, Typed[Planeswalker]]`` target, not a bare
# ``ParentTarget`` — genuinely different phase output, no bridge needed).
_CURSE_SHAKEN_FAITH_RX = re.compile(
    r"^enchant player\b.*\bdeals? \d+ damage to (?:them|that player)\b",
    re.IGNORECASE | re.DOTALL,
)


def _curse_shaken_faith_match(tree: ConceptTree) -> bool:
    return bool(_CURSE_SHAKEN_FAITH_RX.search(tree.oracle or ""))


# (4) Flames of the Blood Hand's HEADLINE sentence — "~ deals 4 damage to
# target player or planeswalker." — is dropped WHOLESALE; the only surviving
# unit is the THIRD sentence's "gains no life instead" replacement effect
# (an ``Unimplemented`` under an ``S_replacements`` wrapper). Unlike the
# trailing-clause idioms below, the missing clause here is the FIRST
# sentence, not a tail.
_FLAMES_BLOOD_HAND_RX = re.compile(
    r"deals \d+ damage to target player or planeswalker\. the damage "
    r"can't be prevented",
    re.IGNORECASE,
)


def _flames_blood_hand_match(tree: ConceptTree) -> bool:
    return bool(_FLAMES_BLOOD_HAND_RX.search(tree.oracle or ""))


# (5) Valakut Exploration's "... put them into their owner's graveyard, then
# this enchantment deals that much damage to each opponent" — the trailing
# damage clause after the ``ChangeZone`` (graveyard) effect in the SAME
# sentence is dropped; the wrapping unit's OWN ``description`` field still
# carries the full English sentence (verified via tree dump), but
# ``execute.effect`` decomposes only the graveyard half.
_VALAKUT_EXPLORATION_RX = re.compile(
    r"put them into their owner's graveyard, then [^.]*deals? that much "
    r"damage to each opponent",
    re.IGNORECASE,
)


def _valakut_exploration_match(tree: ConceptTree) -> bool:
    return bool(_VALAKUT_EXPLORATION_RX.search(tree.oracle or ""))


# (6) Avatar Aang // Aang, Master of Elements's transform trigger is a FIVE-
# effect conjunction (gain life, draw, put counters, deal damage) chained via
# ``SequentialSibling``; phase's chain terminates after the FOURTH effect
# (``PutCounter``, ``sub_ability=None``) — the fifth conjunct, "he deals 4
# damage to each opponent," carries no node at all.
_AVATAR_AANG_RX = re.compile(
    r"put four \+1/\+1 counters on \w+, and \w+ deals \d+ damage to "
    r"each opponent",
    re.IGNORECASE,
)


def _avatar_aang_match(tree: ConceptTree) -> bool:
    return bool(_AVATAR_AANG_RX.search(tree.oracle or ""))


# (7) Insult // Injury's Aftermath back face ("Injury deals 2 damage to
# target creature and 2 damage to target player or planeswalker") gets ZERO
# units in its ``ConceptTree`` — neither phase's own parse nor the W2c
# text-only fallback structures this face at all (the shared gap trivially
# holds: an empty ``tree.units`` loop never finds a reaching node).
_INSULT_INJURY_RX = re.compile(
    r"injury deals \d+ damage to target creature and \d+ damage to "
    r"target player or planeswalker",
    re.IGNORECASE,
)


def _insult_injury_match(tree: ConceptTree) -> bool:
    return bool(_INSULT_INJURY_RX.search(tree.oracle or ""))


# (8) Karn, Living Legacy's [-7] emblem — "You get an emblem with 'Tap an
# untapped artifact you control: This emblem deals 1 damage to any
# target.'" — parks the WHOLE granted activated ability as an opaque
# ``CreateEmblem.statics[].description`` string (the ``sac_emblem_
# activated_cost`` precedent, a Sacrifice-costed sibling of this same
# opaque-emblem-body shape).
_KARN_LIVING_LEGACY_RX = re.compile(
    r'emblem with\s*"[^".]*:[^".]*deals? \d+ damage to any target',
    re.IGNORECASE,
)


def _karn_living_legacy_match(tree: ConceptTree) -> bool:
    return bool(_KARN_LIVING_LEGACY_RX.search(tree.oracle or ""))


# (9) Captain Rex Nebula's granted "Crash Land" trigger — "Whenever ~ deals
# damage, roll a six-sided die. If the result is equal to ~'s mana value,
# sacrifice ~, then it deals that much damage to any target." — decomposes
# into a REAL typed chain (``Unimplemented('crash')`` -> ``RollDie`` ->
# ``Sacrifice``) but the chain's OWN ``sub_ability`` terminates at
# ``Sacrifice`` (``sub_ability=None``); the FINAL "it deals that much damage"
# step carries no node.
_CAPTAIN_REX_NEBULA_RX = re.compile(
    r"roll a six-sided die\. if the result is equal to [^.]*mana value, "
    r"sacrifice [^,.]*, then it deals that much damage to any target",
    re.IGNORECASE,
)


def _captain_rex_nebula_match(tree: ConceptTree) -> bool:
    return bool(_CAPTAIN_REX_NEBULA_RX.search(tree.oracle or ""))


# (10) Maestros Diabolist / Pugnacious Pugilist's "create a tapped and
# attacking 1/1 red Devil creature token with 'When this token dies, it
# deals 1 damage to any target.'" — the WHOLE clause is one
# ``Unimplemented(name='create', ...)`` residue whose DOMINANT verb token is
# "create," so the make_token recovery ALLOWLIST never descends into the
# quoted granted-ability text to find the nested damage clause (contrast
# Dance with Devils's simpler, un-triggered phrasing, which IS structured).
_DEVIL_TOKEN_QUOTED_GRANT_RX = re.compile(
    r"create a tapped and attacking 1/1 red devil creature token with "
    r'"when [^"]*dies, it deals \d+ damage to any target',
    re.IGNORECASE,
)


def _devil_token_quoted_grant_match(tree: ConceptTree) -> bool:
    return bool(_DEVIL_TOKEN_QUOTED_GRANT_RX.search(tree.oracle or ""))


# (11) Ellie, Vengeful Hunter's "Pay 2 life, Sacrifice another creature: ~
# deals 2 damage to target player and gains indestructible until end of
# turn." — the WHOLE ability collapses into a single ``GenericEffect``
# wrapping only the keyword-grant half (``AddKeyword(Indestructible)``) as a
# typed static-ability modification; the damage half is dropped entirely,
# not even as an ``Unimplemented`` residue.
_ELLIE_VENGEFUL_HUNTER_RX = re.compile(
    r"deals \d+ damage to target player and gains indestructible",
    re.IGNORECASE,
)


def _ellie_vengeful_hunter_match(tree: ConceptTree) -> bool:
    return bool(_ELLIE_VENGEFUL_HUNTER_RX.search(tree.oracle or ""))


# (12) Keranos, God of Storms's three-sentence reveal-and-punish ability
# fails OUR effect-sentence parser wholesale: "Effect sentence candidate but
# line failed effect parser: Reveal the first card you draw ... Keranos
# deals 3 damage to any target." — an ``Unimplemented(name='effect_
# structure')`` diagnostic residue (our own clause grammar's frontier, not
# phase's — task #82 names the eventual multi-trigger-sentence verb).
_KERANOS_RX = re.compile(
    r"whenever you reveal a nonland card this way, [^.]*deals \d+ "
    r"damage to any target",
    re.IGNORECASE,
)


def _keranos_match(tree: ConceptTree) -> bool:
    return bool(_KERANOS_RX.search(tree.oracle or ""))


# (13) Kaboom!'s "For each of them, reveal cards ... until you reveal a
# nonland card, ~ deals damage equal to that card's mana value to that
# player or planeswalker, then you put the revealed cards on the bottom..."
# — the top-level ``TargetOnly(target=Player())`` DOES structurally choose
# the "target players or planeswalkers," but the trailing damage clause
# after the ``RevealUntil`` sub-ability chain (``sub_ability=None``) is
# dropped entirely — no node ties the computed mana-value amount back to
# that established target.
_KABOOM_RX = re.compile(
    r"deals damage equal to that card's mana value to that player or "
    r"planeswalker",
    re.IGNORECASE,
)


def _kaboom_match(tree: ConceptTree) -> bool:
    return bool(_KABOOM_RX.search(tree.oracle or ""))


# (14) Goblin Barrage / Unstable Footing's KICKER-MODE bonus target — "If
# this spell was kicked, it (also) deals N damage to target player or
# planeswalker" (CR 702.33d — "if a player chooses to pay a kicker cost...
# that spell has been kicked") — is a BRAND NEW target choice the kicked
# mode introduces, not a genuine back-reference; phase tags it ``ParentTarget``
# anyway (the SAME bare marker Aggressive Sabotage's genuine back-reference
# uses), and with no sibling player-reaching field in the SAME unit (Goblin
# Barrage's base mode targets ``Typed(Creature)`` only; Unstable Footing's
# base effect has no target at all), ``_unit_has_player_target`` correctly
# can't resolve it — this module's own documented Fiery-Impulse-collision
# caution (a "deals N instead" modal amendment quoting an EARLIER creature
# target carries the identical tag) forbids loosening that resolution
# generically. Corpus-verified: exactly these 2 cards match the idiom
# corpus-wide.
_KICKER_PTPLANESWALKER_RX = re.compile(
    r"kicked,? it (?:also )?deals \d+ damage to target player or "
    r"planeswalker",
    re.IGNORECASE,
)


def _kicker_ptplayer_match(tree: ConceptTree) -> bool:
    return bool(_KICKER_PTPLANESWALKER_RX.search(tree.oracle or ""))


# ── base_pt_set residual class (ADR-0039 W7 endgame) ─────────────────────
# Six bridges close the final base_pt_set stragglers left after this
# session's three structural closers (a ``LastCreated`` resolved-tag
# accept, an empty-nested-description unit-level fallback, and a modal
# ``mode_abilities`` threaded-target walk — see
# :func:`~mtg_utils._deck_forge.crosswalk_signals._base_pt_set` and
# :func:`~mtg_utils._deck_forge.crosswalk_signals.
# _iter_base_pt_modal_threaded_statics`). Each census below is corpus-bound
# to EXACTLY its enumerated pins (re-verified 2026-07-11, phase v0.20.0,
# 31,622 commander-legal cards) — no blast-radius slop.
def _unimplemented_descs_anywhere(tree: ConceptTree) -> Iterator[str]:
    """Every ``Unimplemented`` node's description reachable ANYWHERE in the
    tree (unlike :func:`_unimplemented_effect_descs`, this is NOT scoped to
    ``unit.effects`` — a base_pt_set residue can be nested under a STATIC
    unit or a granted-ability chain, outside ``apply_unimplemented_
    recovery``'s scan scope, per the mtg-utils/CONTEXT.md landmine)."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented":
                yield getattr(n, "description", "") or ""


# (1) A "have <subject>'s base power [and toughness] ... become <value>"
# idiom — a scalar/copy re-assignment phase's clause grammar can't
# structure at all (Ambassador Blorpityblorpboop's sticker-power scalar,
# Tanazir Quandrix/Unruly Krasis's "become equal to ~'s power" copy —
# CR 613.4b), parking the WHOLE clause as an ``Unimplemented`` residue that
# survives WITH the hook text intact. Census: 3/31,622 commander-legal
# (exactly the 3 pins; Arni Brokenbrow's "change ~'s base power to 1 plus
# ..." and Curie, Emergent Intelligence's "draw cards equal to its base
# power" — both matched by the whole-oracle raw-hook substring but neither
# by this "have ... become" verb anchor, and neither is a legacy
# base_pt_set member — verified via ``extract_signals_ir`` directly).
_BASE_PT_HAVE_BECOME_RX = re.compile(
    r"\bhave\b.*?\bbase power\b.*?\bbecome\b", re.IGNORECASE
)


def _base_pt_have_become_match(tree: ConceptTree) -> bool:
    return any(
        _BASE_PT_HAVE_BECOME_RX.search(d) for d in _unimplemented_descs_anywhere(tree)
    )


# (2) An "is a(n) <Type> with base power and toughness N/N" fixed-value
# type-change idiom (Circle of the Moon Druid's "Bear Form — During your
# turn, ~ is a Bear with base power and toughness 4/2" — CR 613.4b), parked
# as a whole-clause ``Unimplemented`` residue (the conditional "During your
# turn" framing is the grammar frontier this bridge's TODO names). Census:
# 1/31,622 commander-legal (exactly the 1 pin; Halfdane's "change ~'s base
# power and toughness to the power and toughness of ..." and Brine Hag's
# "change the base power and toughness of all creatures ... to 0/2" both
# fail the "is a(n) ... with base power and toughness N/N" anchor).
_BASE_PT_IS_A_TYPE_WITH_RX = re.compile(
    r"\bis an? [^.]*\bwith base power and toughness \d+/\d+\b", re.IGNORECASE
)


def _base_pt_is_a_type_with_match(tree: ConceptTree) -> bool:
    return any(
        _BASE_PT_IS_A_TYPE_WITH_RX.search(d)
        for d in _unimplemented_descs_anywhere(tree)
    )


# (3) A mass "creatures you control have base power and toughness X/X,
# where X is ..." scalar (Candlekeep Inspiration — CR 613.4b), parked as a
# whole-clause ``Unimplemented`` residue (the "where X is the number of
# cards you own in exile and in your graveyard that are instant cards, are
# sorcery cards, and/or have an Adventure" scalar definition is the grammar
# frontier). Census: 1/31,622 commander-legal (exactly the 1 pin).
_BASE_PT_MASS_WHERE_X_RX = re.compile(
    r"\bhave base power and toughness [A-Za-z]/[A-Za-z]\b", re.IGNORECASE
)


def _base_pt_mass_where_x_match(tree: ConceptTree) -> bool:
    return any(
        _BASE_PT_MASS_WHERE_X_RX.search(d) for d in _unimplemented_descs_anywhere(tree)
    )


# (4) A Stickers-templated ability whose cost is an un-parseable ``{TK}``
# placeholder (Cool Fluffy Loxodon's "{TK}{TK}{TK}{TK}{TK} — Whenever a
# creature enters under your control, ~ becomes a 13/13 Eldrazi creature in
# addition to its other types until end of turn" — Unfinity's sticker-sheet
# templating, CR 713) — phase's cost grammar has no ``{TK}`` token at all,
# parking the WHOLE ability (cost AND effect) as an opaque ``Unimplemented``
# residue, unlike the other three bridges above where only the base-P/T
# CLAUSE fails. Census: 1/31,622 commander-legal (exactly the 1 pin — the
# ONLY {TK}-costed ability corpus-wide whose residue ALSO names the animate
# hook; other Stickers cards' {TK} abilities don't touch base P/T at all).
_BASE_PT_TK_ANIMATE_RX = re.compile(
    r"\{TK\}[^.]*\d+/\d+[^.]*\bin addition to its other types\b", re.IGNORECASE
)


def _base_pt_tk_animate_match(tree: ConceptTree) -> bool:
    return any(
        _BASE_PT_TK_ANIMATE_RX.search(d) for d in _unimplemented_descs_anywhere(tree)
    )


# (5) A DYNAMIC "base power and toughness each equal to <mana value | X>"
# scalar-set clause phase drops ENTIRELY from the site's own modifications
# (Captain Rex Nebula's mana-value CDA-like scalar, Fractalize's "X plus 1"
# scalar — CR 613.4b) — the site's own ``description`` DOES carry the hook
# text (unlike bridges 1-4's whole-clause drop), and the target resolves
# fine, but no ``SetPowerDynamic``/``SetToughnessDynamic`` modification
# node exists anywhere on that site for phase to have dropped a residue
# for. Self-retiring PER SITE: the day phase decomposes the "each equal to"
# scalar into a typed SetDynamic pair at that exact site, this predicate
# goes False on that card AND the main lane's existing dynamic-pair arm
# picks it up structurally with zero further edits. Census: 2/31,622
# commander-legal (exactly the 2 pins).
_BASE_PT_EACH_EQUAL_TO_RX = re.compile(
    r"base power and toughness each equal to\b", re.IGNORECASE
)


def _base_pt_each_equal_to_dropped(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for ge in iter_typed_nodes(unit.node):
            if tag_of(ge) != "GenericEffect":
                continue
            for st in getattr(ge, "static_abilities", None) or []:
                desc = getattr(st, "description", "") or ""
                if not _BASE_PT_EACH_EQUAL_TO_RX.search(desc):
                    continue
                mods = {tag_of(m) for m in (getattr(st, "modifications", None) or [])}
                if not (
                    mods
                    & {
                        "SetPower",
                        "SetToughness",
                        "SetPowerDynamic",
                        "SetToughnessDynamic",
                    }
                ):
                    return True
    return False


# (6) A fixed-value "is a <Type> with base power and toughness N/N, <extra
# granted keyword/ability>" type-change site phase MIS-decomposes as an
# ``AddPower``/``AddToughness`` PAIR (Goddric, Cloaked Reveler's Celebration
# static — phase apparently attributes the SIBLING granted "{R}: Dragons
# you control get +1/+0" activated ability's OWN pump amounts onto this
# static's modifications instead of a ``SetPower``/``SetToughness`` pair
# for the "is a Dragon with base power and toughness 4/4" clause itself —
# CR 613.4b/CR 613.1f). The site's own ``description`` DOES carry the hook
# text and the correct SelfRef subject; only the modification TAGS are
# wrong. Gap is a tree-wide absence proof (mirrors :func:`_no_typed_
# sacrifice_node`): Burden of Proof ALSO carries an AddPower/AddToughness-
# only site whose description happens to span BOTH its conditional
# branches' text, but its "Otherwise, it has base power and toughness 1/1"
# branch DOES have a genuine SetPower/SetToughness pair elsewhere in the
# SAME tree, so the tree-wide gap correctly stands this bridge down there
# (verified: ``extract_signals_ir`` fires True for Burden of Proof via that
# EXISTING structural pair, no bridge needed). Census: 2/31,622
# commander-legal pattern-matched, 1 after the tree-wide gap exclusion
# (exactly the 1 pin).
def _base_pt_no_typed_set_anywhere(tree: ConceptTree) -> bool:
    return not any(
        tag_of(n)
        in ("SetPower", "SetToughness", "SetPowerDynamic", "SetToughnessDynamic")
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


_BASE_PT_ADDPT_RAW_HOOK_RX = re.compile(r"base power|base toughness", re.IGNORECASE)
_BASE_PT_ADDPT_ANIMATE_HOOK_RX = re.compile(
    r"\d+/\d+[^.]*\bin addition to its other types\b", re.IGNORECASE
)


def _base_pt_addpt_misattributed_match(tree: ConceptTree) -> bool:
    sts: list[object] = []
    for unit in tree.units:
        if unit.origin == "static":
            sts.append(unit.node)
        for ge in iter_typed_nodes(unit.node):
            if tag_of(ge) == "GenericEffect":
                sts.extend(getattr(ge, "static_abilities", None) or [])
    for st in sts:
        mods = {tag_of(m) for m in (getattr(st, "modifications", None) or [])}
        if mods != {"AddPower", "AddToughness"}:
            continue
        desc = getattr(st, "description", "") or ""
        if _BASE_PT_ADDPT_RAW_HOOK_RX.search(
            desc
        ) or _BASE_PT_ADDPT_ANIMATE_HOOK_RX.search(desc):
            return True
    return False


# (7) A ``BecomeCopy`` "except it's N/N" fixed P/T override with NO
# ``additional_modifications`` field AT ALL (Mindlink Mech's "becomes a
# copy of target nonlegendary creature ..., except it's 4/3, ..." — CR
# 707.2/707.9) — ZERO trace anywhere in the tree for the override, same
# absence-proof shape as the Degavolver/Zuko/keyword-dropped bridges above.
# The standard clone-SHELL idiom ("becomes a copy of X, except it's 0/0
# and has this ability" — Mimeoplasm, Revered One) shares the identical
# missing-additional_modifications gap but is corpus-verified NOT a legacy
# base_pt_set member (``extract_signals_ir`` returns False for it) — the
# ``(?!0/0\b)`` negative lookahead excludes that shell idiom by construction
# rather than re-deriving legacy's own clone-shell carve-out. Census:
# 2/31,622 commander-legal pattern-matched before the 0/0 exclusion, 1 after
# (exactly the 1 pin).
_BASE_PT_BECOMECOPY_PT_RX = re.compile(
    r"becomes a copy of[^.]*except it'?s (?!0/0\b)\d+/\d+", re.IGNORECASE
)


def _base_pt_becomecopy_no_mods_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "BecomeCopy":
                continue
            addl = getattr(n, "additional_modifications", MISSING)
            if addl is MISSING or addl in (None, []):
                return True
    return False


def _base_pt_becomecopy_no_mods_match(tree: ConceptTree) -> bool:
    return bool(_BASE_PT_BECOMECOPY_PT_RX.search(tree.oracle))


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
        Bridge(
            bridge_id="cheat_player_prefix_battlefield_put",
            key="cheat_into_play",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a new "
                "_PLAYER_PREFIX clause-grammar token for a leading "
                "referent/relative-clause before the actual imperative "
                "('its controller reveals...', 'who received no votes "
                "may put...', 'you do the same with...') — retires when "
                "the swallowed clause decomposes into its own typed "
                "reveal/put chain the existing ChangeZone/RevealUntil "
                "arms already read"
            ),
            census=(
                "6 hits / 31,622 commander-legal Unimplemented residues "
                "matching the enumerated leading-subject phrasings AND "
                "mentioning 'onto the battlefield' tree-wide, phase "
                "v0.20.0, 2026-07-11 (Soul of Emancipation shares the "
                "SAME 'For each of those permanents, its controller...' "
                "leading shape but is a token maker with no battlefield-"
                "put mention at all — excluded by the tree-wide gate)"
            ),
            pins=(
                "Divergent Transformations",
                "Círdan the Shipwright",
                "Vaevictis Asmadi, the Dire",
                "Collision of Realms",
                "Guild Feud",
                "Liberated Livestock",
            ),
            gap=_cheat_player_prefix_gap,
            match=_cheat_player_prefix_match,
        ),
        Bridge(
            bridge_id="cheat_dropped_clause_zero_residue",
            key="cheat_into_play",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a family "
                "of type/count/destination degradations on reveal-then-put "
                "chains — an emptied SearchLibrary/Dig/RevealUntil filter "
                "(Curse of Misfortunes' self-referential 'Curse card' "
                "subtype, Empty the Laboratory's 'equal to the number "
                "sacrificed' dynamic count), a swallowed condition with "
                "ZERO residue (Matter Reshaper's 'mana value 3 or less', "
                "Eladamri's 'if you reveal a creature card'), or the "
                "reveal/put mechanism itself never becoming a node "
                "(Turntimber Symbiosis, Game Preserve, Wakanda Forever!'s "
                "modal-to-Hand collapse, Green Sun's Twilight's X-gated "
                "destination) — retires PER-NODE as each filter/count/"
                "destination lands real evidence (the existing structural "
                "arms fire on their own, no edit needed here)"
            ),
            census=(
                "8 hits / 31,622 commander-legal, matched against each "
                "card's own verbatim dropped-clause phrasing (a card-name-"
                "keyed enumeration, not a generic substring — CONTEXT.md's "
                "third residue class), phase v0.20.0, 2026-07-11"
            ),
            pins=(
                "Matter Reshaper",
                "Eladamri, Korvecdal",
                "Curse of Misfortunes",
                "Empty the Laboratory",
                "Turntimber Symbiosis // Turntimber, Serpentine Wood",
                "Wakanda Forever!",
                "Game Preserve",
                "Green Sun's Twilight",
            ),
            gap=_cheat_no_battlefield_type_evidence,
            match=_cheat_dropped_clause_match,
        ),
        Bridge(
            bridge_id="cheat_kept_destination_hand_misparse",
            key="cheat_into_play",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "RevealUntil whose revealer and putter are DIFFERENT "
                "actors ('its controller reveals... puts that card onto "
                "the battlefield') mis-parses kept_destination as 'Hand' "
                "instead of 'Battlefield' — retires on a phase bump that "
                "reads the actual destination clause instead of "
                "defaulting when the actors diverge"
            ),
            census=(
                "2 hits / 31,622 commander-legal, matched against each "
                "card's own verbatim reveal-until-then-put sentence, "
                "phase v0.20.0, 2026-07-11 (Telemin Performance shares "
                "the divergent-actor shape but structures its put as a "
                "SEPARATE, correctly-typed ChangeZone node — closed "
                "structurally this session via "
                "_cheat_reveal_until_you_enters_put in "
                "crosswalk_signals.py, not this bridge)"
            ),
            pins=("Chaos Mutation", "Chaotic Transformation"),
            gap=_cheat_no_battlefield_type_evidence,
            match=_cheat_kept_dest_misparse_match,
        ),
        Bridge(
            bridge_id="cheat_choose_from_among_graveyard_origin",
            key="cheat_into_play",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a new grammar "
                "verb for 'choose a [type] card from among them' (the "
                "reveal-then-select idiom's selection step) that ALSO "
                "corrects the sibling ChangeZone's origin tag — phase "
                "mis-tags it 'Graveyard' when the actual source is the "
                "just-revealed LIBRARY-top pile — retires when the choose "
                "clause decomposes with a correct origin"
            ),
            census=(
                "2 hits / 31,622 commander-legal Unimplemented 'choose'+"
                "'from among them' residues paired with a Graveyard-origin "
                "sibling Battlefield put in the SAME unit, phase v0.20.0, "
                "2026-07-11 (5 siblings — Guided Passage, Manifold "
                "Insights, Kaya's Spirits' Justice, Capricious Hellraiser, "
                "Green Sun's Twilight — share the 'choose... from among "
                "them' shape but carry NO Battlefield-destined node at "
                "all in the unit; Green Sun's Twilight is the dropped-"
                "clause bridge above instead)"
            ),
            pins=("Animal Magnetism", "Selective Adaptation"),
            gap=_cheat_choose_among_gap,
            match=_cheat_choose_among_match,
        ),
        Bridge(
            bridge_id="cheat_modal_mode_unsupported_qualifier",
            key="cheat_into_play",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "modal parser can't structure a 'total mana value N or "
                "less' qualifier on a mode's 'put any number of nonland "
                "permanent cards... onto the battlefield' effect, parking "
                "the WHOLE mode as Unimplemented(name="
                "'modal_mode_unsupported_qualifier') — retires on a phase "
                "bump that structures the qualifier"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented nodes named "
                "'modal_mode_unsupported_qualifier' mentioning 'onto the "
                "battlefield', phase v0.20.0, 2026-07-11 (Ao, the Dawn "
                "Sky is the SOLE hit — the diagnostic name itself is rare "
                "corpus-wide)"
            ),
            pins=("Ao, the Dawn Sky",),
            gap=_cheat_modal_unsupported_gap,
            match=_cheat_modal_unsupported_match,
        ),
        Bridge(
            bridge_id="cheat_synthetic_destiny_delayed_reveal",
            key="cheat_into_play",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): the Unimplemented"
                "-recovery stage already re-decorates this node with "
                "concept 'reveal_until' (its raw text names the idiom) but "
                "the raw node carries no typed kept_destination field — "
                "needs a dig_until/reveal_until recovery verb that "
                "synthesizes the missing field from the raw text (recovery"
                ".py's ALLOWLIST is the likely landing spot, not a NEW "
                "bridge), retiring when the node decomposes structurally"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented nodes named "
                "'reveal' nested inside a CreateDelayedTrigger, phase "
                "v0.20.0, 2026-07-11 — Synthetic Destiny is the SOLE hit"
            ),
            pins=("Synthetic Destiny",),
            gap=_cheat_synthetic_destiny_gap,
            match=_cheat_synthetic_destiny_match,
        ),
        Bridge(
            bridge_id="dmg_creature_and_controller_dropped",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a burn "
                "spell's compound 'deals N damage to target creature AND X "
                "damage to that creature's/permanent's controller' clause "
                "(CR 102.1) structures only the first (creature) half — the "
                "controller-damage half carries no node anywhere, typed or "
                "Unimplemented. Retires on a phase bump that decomposes the "
                "second conjunct (task #82's compound-damage-clause verb)"
            ),
            census=(
                "3 hits / 31,622 commander-legal, no-player-reaching-damage-"
                "node subset scanned via legacy's OWN _DIRECT_DAMAGE_MIRROR "
                "controller-damage alternative wording (45 corpus siblings "
                "matching the same wording — Unlicensed Disintegration, "
                "Lash Out, etc. — are ALREADY served via a real typed "
                "Or[Typed(Creature), ParentTargetController] target, no "
                "bridge needed), phase v0.20.0, 2026-07-11"
            ),
            pins=("Judgment Bolt", "Liquid Fire", "Synchronized Spellcraft"),
            gap=_no_player_reaching_damage_node,
            match=_dmg_creature_controller_match,
        ),
        Bridge(
            bridge_id="vexing_arcanix_reveal_misread_damage_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): Vexing "
                "Arcanix's 'Otherwise, they put it into their graveyard "
                "and ~ deals 2 damage to them' trailing damage clause is "
                "dropped after an Unimplemented('otherwise') residue (a "
                "SEPARATE upstream bug also misreads the earlier RevealTop's "
                "player as Controller() instead of the activated ability's "
                "own targeted player — out of THIS bridge's scope). Retires "
                "on a phase bump that structures the 'otherwise' branch's "
                "own damage clause"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Vexing Arcanix, a "
                "singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Vexing Arcanix",),
            gap=_no_player_reaching_damage_node,
            match=_vexing_arcanix_match,
        ),
        Bridge(
            bridge_id="curse_shaken_faith_enchant_player_them",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the Aura "
                "target-restriction line (CR 303.4c — 'Enchant player' vs. "
                "'Enchant creature/permanent') is not preserved on the "
                "AttachedTo marker node — a bare zero-field tag with no "
                "type field — so a sibling bare ParentTarget damage "
                "recipient can't structurally resolve back to a player. "
                "Retires on a phase bump that adds an enchant-type field to "
                "AttachedTo (or splits it into typed variants, matching "
                "Curse of the Pierced Heart's already-structural "
                "Or[TriggeringPlayer, Typed(Planeswalker)] shape)"
            ),
            census=(
                "1 hit / 31,622 commander-legal ('enchant player' cards "
                "scanned: 42 total; only Curse of Shaken Faith both matches "
                "the damage-clause idiom AND still lacks a typed reach — "
                "Curse of the Pierced Heart's structurally-identical-"
                "looking clause is ALREADY typed, the other 40 'enchant "
                "player' Curses have non-damage payoffs), phase v0.20.0, "
                "2026-07-11"
            ),
            pins=("Curse of Shaken Faith",),
            gap=_no_player_reaching_damage_node,
            match=_curse_shaken_faith_match,
        ),
        Bridge(
            bridge_id="flames_blood_hand_headline_clause_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): Flames of "
                "the Blood Hand's HEADLINE sentence ('~ deals 4 damage to "
                "target player or planeswalker.') is dropped wholesale — "
                "only the third sentence's 'gains no life instead' "
                "replacement survives as a unit. Retires on a phase bump "
                "that structures the first sentence alongside the "
                "replacement it currently emits alone"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Flames of the Blood Hand, "
                "a singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Flames of the Blood Hand",),
            gap=_no_player_reaching_damage_node,
            match=_flames_blood_hand_match,
        ),
        Bridge(
            bridge_id="valakut_exploration_trailing_clause_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "trailing 'then ~ deals that much damage to each opponent' "
                "clause after a ChangeZone(Graveyard) effect in the SAME "
                "sentence is dropped from execute.effect even though the "
                "wrapping unit's own description field still carries the "
                "full sentence text. Retires on a phase bump that "
                "decomposes a second SequentialSibling-chained effect "
                "sharing one sentence (task #82)"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Valakut Exploration, a "
                "singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Valakut Exploration",),
            gap=_no_player_reaching_damage_node,
            match=_valakut_exploration_match,
        ),
        Bridge(
            bridge_id="avatar_aang_conjunction_tail_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a FIVE-"
                "effect SequentialSibling conjunction (gain life, draw, put "
                "counters, deal damage) terminates after the FOURTH effect "
                "(PutCounter, sub_ability=None) — the fifth conjunct 'he "
                "deals 4 damage to each opponent' carries no node. Retires "
                "on a phase bump that extends the chain depth for this "
                "shape"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Avatar Aang // Aang, "
                "Master of Elements, a singleton idiom), phase v0.20.0, "
                "2026-07-11"
            ),
            pins=("Aang, Master of Elements",),
            gap=_no_player_reaching_damage_node,
            match=_avatar_aang_match,
        ),
        Bridge(
            bridge_id="insult_injury_aftermath_face_unparsed",
            key="direct_damage",
            kind="missing_face",
            todo=(
                "upstream phase-rs / W2c report candidate (Dan posts): "
                "Insult // Injury's Aftermath back face ('Injury deals 2 "
                "damage to target creature and 2 damage to target player or "
                "planeswalker') gets ZERO units in its ConceptTree — "
                "neither phase's own parse nor the W2c text-only fallback "
                "structures this face at all. Retires when either path "
                "produces at least one unit for this face's text"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Insult // Injury, a "
                "singleton idiom — the only zero-unit Aftermath back face "
                "carrying a direct-damage clause), phase v0.20.0, "
                "2026-07-11"
            ),
            pins=("Insult // Injury",),
            gap=_no_player_reaching_damage_node,
            match=_insult_injury_match,
        ),
        Bridge(
            bridge_id="karn_living_legacy_emblem_tap_cost_damage",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): "
                "CreateEmblem's granted-ability text parks entirely as an "
                "opaque S_statics.description string — no typed activated-"
                "ability-with-cost structure survives for the emblem's OWN "
                "granted tap-cost damage outlet (the sac_emblem_activated_"
                "cost bridge's Sacrifice-costed sibling shape). Retires on "
                "a phase bump that decomposes an emblem's granted ability "
                "the way a GrantAbility's granted ability already is"
            ),
            census=(
                "1 hit / 31,622 commander-legal, no-player-reaching-damage-"
                "node subset scanned for a comma/colon-cost-prefixed "
                "'deals N damage to any target' inside an emblem's quoted "
                "granted text (Koth of the Hammer's structurally-identical-"
                "looking emblem is ALREADY served — its Mountain-static "
                "grant resolves via a different, already-structural path), "
                "phase v0.20.0, 2026-07-11"
            ),
            pins=("Karn, Living Legacy",),
            gap=_no_player_reaching_damage_node,
            match=_karn_living_legacy_match,
        ),
        Bridge(
            bridge_id="captain_rex_nebula_crash_land_final_step_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "granted 'Crash Land' trigger decomposes into a REAL typed "
                "chain (Unimplemented('crash') -> RollDie -> Sacrifice) but "
                "the chain's own sub_ability terminates at Sacrifice "
                "(sub_ability=None) — the FINAL 'it deals that much damage "
                "to any target' step carries no node. Retires on a phase "
                "bump that extends this chain one more link"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Captain Rex Nebula, a "
                "singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Captain Rex Nebula",),
            gap=_no_player_reaching_damage_node,
            match=_captain_rex_nebula_match,
        ),
        Bridge(
            bridge_id="devil_token_quoted_grant_dominant_verb_create",
            key="direct_damage",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): an Unimplemented-"
                "residue recovery verb for a token-creation clause whose "
                "quoted granted-ability text carries a NESTED damage clause "
                "(create a tapped and attacking 1/1 red Devil creature "
                "token whose quoted death trigger deals 1 damage to any "
                "target) — the whole clause's dominant verb token is "
                "create, so the make_token recovery ALLOWLIST never "
                "descends into the quoted text. Retires when the node "
                "decomposes into a typed CreateToken + nested granted-"
                "ability DealDamage read (Dance with Devils's simpler, "
                "un-triggered phrasing already works structurally)"
            ),
            census=(
                "2 hits / 31,622 commander-legal, no-player-reaching-"
                "damage-node subset scanned for the exact Devil-token "
                "quoted-grant idiom (Maestros Diabolist, Pugnacious "
                "Pugilist), phase v0.20.0, 2026-07-11"
            ),
            pins=("Maestros Diabolist", "Pugnacious Pugilist"),
            gap=_no_player_reaching_damage_node,
            match=_devil_token_quoted_grant_match,
        ),
        Bridge(
            bridge_id="ellie_vengeful_hunter_damage_half_dropped",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): 'Pay 2 "
                "life, Sacrifice another creature: ~ deals 2 damage to "
                "target player and gains indestructible until end of turn.' "
                "collapses into a single GenericEffect carrying ONLY the "
                "keyword-grant half (AddKeyword(Indestructible)) as a typed "
                "static-ability modification; the damage half is dropped "
                "entirely, not even as an Unimplemented residue. Retires on "
                "a phase bump that structures both halves of this compound "
                "activated-ability effect"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Ellie, Vengeful Hunter, a "
                "singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Ellie, Vengeful Hunter",),
            gap=_no_player_reaching_damage_node,
            match=_ellie_vengeful_hunter_match,
        ),
        Bridge(
            bridge_id="keranos_effect_structure_parse_failure",
            key="direct_damage",
            kind="upstream_parse_failure",
            todo=(
                "post-deletion grammar sprint (task #82): Keranos, God of "
                "Storms's three-sentence reveal-and-punish ability fails "
                "OUR OWN effect-sentence parser wholesale — an "
                "Unimplemented(name='effect_structure', description="
                "'Effect sentence candidate but line failed effect parser: "
                "...') diagnostic residue (our own clause grammar's "
                "frontier, not phase's). Retires when the multi-trigger-"
                "sentence verb this diagnostic names gets built"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Keranos, God of Storms, a "
                "singleton idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Keranos, God of Storms",),
            gap=_no_player_reaching_damage_node,
            match=_keranos_match,
        ),
        Bridge(
            bridge_id="kaboom_trailing_clause_drop",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the top-"
                "level TargetOnly(target=Player()) DOES structurally choose "
                "'target players or planeswalkers,' but the trailing "
                "'~ deals damage equal to that card's mana value to that "
                "player or planeswalker' clause after the RevealUntil sub-"
                "ability chain (sub_ability=None) is dropped entirely — no "
                "node ties the computed mana-value amount back to the "
                "established target. Retires on a phase bump that extends "
                "the chain past RevealUntil"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Kaboom!, a singleton "
                "idiom), phase v0.20.0, 2026-07-11"
            ),
            pins=("Kaboom!",),
            gap=_no_player_reaching_damage_node,
            match=_kaboom_match,
        ),
        Bridge(
            bridge_id="kicker_ptplayer_modal_new_target",
            key="direct_damage",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a kicker-"
                "mode's own NEW 'target player or planeswalker' choice (CR "
                "702.33d — not a back-reference) is tagged ParentTarget, the "
                "same bare marker used for a genuine back-reference "
                "(Aggressive Sabotage) — with no typed Or[Player, "
                "Planeswalker] discriminator preserved; phase's "
                "SequentialSibling kicker-mode grammar collapses both "
                "shapes into the identical tag. Retires on a phase bump "
                "that gives the kicked-mode's own target its own typed "
                "shape (matching Curse of the Pierced Heart's already-"
                "structural Or[TriggeringPlayer, Typed(Planeswalker)])"
            ),
            census=(
                "2 hits / 31,622 commander-legal ('kicked, it (also) deals "
                "N damage to target player or planeswalker' idiom scanned "
                "corpus-wide: Goblin Barrage, Unstable Footing — both a "
                "FRESH kicker-mode target, CR 702.33d, not the Aggressive "
                "Sabotage back-reference shape this module's ParentTarget "
                "resolution already serves correctly), phase v0.20.0, "
                "2026-07-11"
            ),
            pins=("Goblin Barrage", "Unstable Footing"),
            gap=_no_player_reaching_damage_node,
            match=_kicker_ptplayer_match,
        ),
        Bridge(
            bridge_id="base_pt_have_become_residue",
            key="base_pt_set",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a clause-grammar "
                "verb for the 'have <subject>'s base power [and toughness] "
                "... become <value>' scalar/copy re-assignment idiom — "
                "retires when the node decomposes into a typed SetPower/"
                "SetPowerDynamic (and toughness sibling) pair the way the "
                "matched-quantity copy-stats arm already reads structurally"
            ),
            census=(
                "3 hits / 31,622 commander-legal Unimplemented residues "
                "matching the 'have ... base power ... become' verb anchor, "
                "phase v0.20.0, 2026-07-11 (exactly the 3 pins; Arni "
                "Brokenbrow's 'change ~'s base power to 1 plus ...' and "
                "Curie, Emergent Intelligence's 'draw cards equal to its "
                "base power' both carry the bare raw-hook substring but "
                "neither the 'have ... become' verb shape, and neither "
                "fires under legacy's own extract_signals_ir — verified "
                "directly)"
            ),
            pins=(
                "Ambassador Blorpityblorpboop",
                "Tanazir Quandrix",
                "Unruly Krasis",
            ),
            gap=_base_pt_have_become_match,
            match=_base_pt_have_become_match,
        ),
        Bridge(
            bridge_id="base_pt_is_a_type_with_residue",
            key="base_pt_set",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a clause-grammar "
                "verb for a conditionally-gated 'is a(n) <Type> with base "
                "power and toughness N/N' fixed type-change idiom (the "
                "'During your turn' framing is the frontier — an "
                "unconditional sibling shape already decomposes into "
                "typed SetPower/SetToughness/AddType nodes, see Displaced "
                "Dinosaurs/Sauron/Ultron this same session) — retires when "
                "the conditional wrapper decomposes too"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented residues "
                "matching the 'is a(n) ... with base power and toughness "
                "N/N' anchor, phase v0.20.0, 2026-07-11 (exactly the 1 pin; "
                "Halfdane's 'change ~'s base power and toughness to the "
                "power and toughness of ...' and Brine Hag's 'change the "
                "base power and toughness of all creatures ... to 0/2' "
                "both fail the anchor)"
            ),
            pins=("Circle of the Moon Druid",),
            gap=_base_pt_is_a_type_with_match,
            match=_base_pt_is_a_type_with_match,
        ),
        Bridge(
            bridge_id="base_pt_mass_where_x_residue",
            key="base_pt_set",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a clause-grammar "
                "verb for a mass 'creatures you control have base power "
                "and toughness X/X, where X is <scalar definition>' idiom "
                "— retires when the node decomposes into a typed "
                "SetPowerDynamic/SetToughnessDynamic pair over a "
                "board-wide affected filter"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented residues "
                "matching 'have base power and toughness X/X', phase "
                "v0.20.0, 2026-07-11 (exactly the 1 pin)"
            ),
            pins=("Candlekeep Inspiration",),
            gap=_base_pt_mass_where_x_match,
            match=_base_pt_mass_where_x_match,
        ),
        Bridge(
            bridge_id="base_pt_tk_sticker_parse_failure",
            key="base_pt_set",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the cost "
                "grammar has no token for Unfinity's Stickers '{TK}' "
                "placeholder cost, so the WHOLE ability (cost AND effect) "
                "parks as an opaque Unimplemented residue — retires on a "
                "phase bump that parses (or explicitly stubs) the {TK} "
                "cost token"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented residues "
                "whose description contains both a '{TK}' cost token and "
                "the animate hook, phase v0.20.0, 2026-07-11 (exactly the "
                "1 pin — the only {TK}-costed ability corpus-wide whose "
                "text also names a base-P/T animate hook)"
            ),
            pins=("Cool Fluffy Loxodon",),
            gap=_base_pt_tk_animate_match,
            match=_base_pt_tk_animate_match,
        ),
        Bridge(
            bridge_id="base_pt_each_equal_to_dropped",
            key="base_pt_set",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a DYNAMIC "
                "'base power and toughness each equal to <mana value | X>' "
                "scalar-set clause is dropped from the site's own "
                "modifications entirely (the site's own description DOES "
                "carry the hook text and the target resolves fine — only "
                "the SetPowerDynamic/SetToughnessDynamic pair itself is "
                "missing) — retires on a phase bump that decomposes the "
                "'each equal to' scalar the way a 'become equal to your "
                "life total' scalar already does (Aettir and Priwen)"
            ),
            census=(
                "2 hits / 31,622 commander-legal GenericEffect static "
                "sites whose OWN description matches 'base power and "
                "toughness each equal to' with no SetPower*/SetToughness* "
                "modification present, phase v0.20.0, 2026-07-11 (exactly "
                "the 2 pins)"
            ),
            pins=("Captain Rex Nebula", "Fractalize"),
            gap=_base_pt_each_equal_to_dropped,
            match=_base_pt_each_equal_to_dropped,
        ),
        Bridge(
            bridge_id="base_pt_addpt_misattributed_typechange",
            key="base_pt_set",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a fixed "
                "'is a <Type> with base power and toughness N/N, <granted "
                "activated ability>' static mis-decomposes as an "
                "AddPower/AddToughness pair carrying the SIBLING granted "
                "ability's OWN pump amounts instead of a SetPower/"
                "SetToughness pair for the type-change clause itself — "
                "retires on a phase bump that emits the correct Set pair "
                "at this site"
            ),
            census=(
                "2 hits / 31,622 commander-legal AddPower+AddToughness-"
                "only static sites whose description names the raw/animate "
                "hook, phase v0.20.0, 2026-07-11; 1 after the tree-wide "
                "no-typed-Set-anywhere gap (Burden of Proof's OTHER "
                "conditional branch DOES carry a genuine SetPower/"
                "SetToughness pair elsewhere in the same tree, correctly "
                "excluded — verified against legacy's own True fire there "
                "via the EXISTING structural pair, no bridge needed) — "
                "exactly the 1 remaining pin"
            ),
            pins=("Goddric, Cloaked Reveler",),
            gap=_base_pt_no_typed_set_anywhere,
            match=_base_pt_addpt_misattributed_match,
        ),
        Bridge(
            bridge_id="base_pt_becomecopy_no_pt_override",
            key="base_pt_set",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "BecomeCopy 'except it's N/N' fixed P/T override drops "
                "with ZERO trace (no additional_modifications field at "
                "all, confirmed via direct tree dump) — retires on a phase "
                "bump that structures the 'except it's N/N' override "
                "clause into BecomeCopy.additional_modifications"
            ),
            census=(
                "2 hits / 31,622 commander-legal BecomeCopy nodes with no "
                "additional_modifications whose oracle text matches "
                "'becomes a copy of ... except it's N/N', phase v0.20.0, "
                "2026-07-11; 1 after excluding the standard clone-SHELL "
                "idiom ('... except it's 0/0 and has this ability' — "
                "Mimeoplasm, Revered One — corpus-verified NOT a legacy "
                "base_pt_set member via extract_signals_ir directly) — "
                "exactly the 1 remaining pin"
            ),
            pins=("Mindlink Mech",),
            gap=_base_pt_becomecopy_no_mods_gap,
            match=_base_pt_becomecopy_no_mods_match,
        ),
    )
}


def bridge_fires(bridge_id: str, tree: ConceptTree) -> bool:
    """Whether the registered bridge fires for this tree (gap AND match)."""
    return BRIDGES[bridge_id].fires(tree)
