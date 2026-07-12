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
    filter_inzone_zones,
    filter_subtypes,
    iter_static_defs,
    iter_typed_nodes,
    recipient_tag,
    static_mode_field,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MISSING
from mtg_utils._deck_forge._sweep_detectors import NAMED_PERMANENT_REGEX

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
# Two bridges close the "NO typed Sacrifice node ANYWHERE in the tree"
# residual bucket (a card-level gap — the crosswalk's own
# ``iter_typed_nodes`` walk, corpus-verified against the SAME shape legacy's
# ``project.py._sacrifice_grant_markers`` gates its own regex fallback on:
# "no structural sacrifice effect anywhere" — so a card with a Sacrifice
# node ELSEWHERE on the SAME card, even for an unrelated edict clause,
# correctly stands every one of these bridges down, matching legacy's own
# gating exactly). CR 701.21a throughout. (ADR-0039 task #82 grammar
# sprint: ``sac_alt_cost_pitch`` / ``sac_keyword_cost`` /
# ``sac_etb_self_sac_unimplemented`` graduated OFF this ledger onto typed
# ``tree_synthesis`` marker-node reads — see ``crosswalk_signals.
# _sacrifice_outlets``'s docstring; ``sac_devour_unimplemented`` graduated
# onto the Scryfall-keyword sweep instead. RETIRED, not deleted from
# history — see git log for the removed rows' full text.)
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
#
# (1) formerly a swallowed THIRD-PERSON leading-subject clause bridge
# (``cheat_player_prefix_battlefield_put``) — RETIRED (ADR-0039 task #82
# grammar sprint): ``tree_synthesis._arm_cheat_player_prefix_battlefield_put``
# ports this bridge's own verbatim leading-phrase regex + tree-wide "onto the
# battlefield" gate onto a synthesized ``synth_cheat_reveal_or_put_
# battlefield`` marker node, which :func:`crosswalk_signals._cheat_into_play`
# now reads structurally (``tree.has_effect(...)``) instead of falling
# through to this ledger. Same membership (Divergent Transformations, Círdan
# the Shipwright, Vaevictis Asmadi the Dire, Collision of Realms, Guild Feud,
# Liberated Livestock); Soul of Emancipation's shared leading shape still
# excludes on the SAME "onto the battlefield" tree-wide gate.
#
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


# (4) formerly a swallowed "choose a [type] card from among them" bridge
# (``cheat_choose_from_among_graveyard_origin``) — RETIRED (ADR-0039 task
# #82 grammar sprint): ``tree_synthesis._arm_cheat_choose_from_among_
# graveyard_origin`` ports this bridge's own gap/match pair (the same
# Unimplemented "choose"+"from among them" text test, paired with the SAME
# sibling Battlefield+Graveyard-origin ChangeZone scan) onto the shared
# ``synth_cheat_reveal_or_put_battlefield`` marker node, which
# :func:`crosswalk_signals._cheat_into_play` now reads structurally instead
# of falling through to this ledger. Same membership (Animal Magnetism,
# Selective Adaptation); Guided Passage / Manifold Insights / Kaya's
# Spirits' Justice / Capricious Hellraiser / Green Sun's Twilight still
# exclude on the SAME no-Battlefield-node-in-the-unit gate.
#
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


# (6) formerly Synthetic Destiny's delayed-trigger reveal-until node bridge
# (``cheat_synthetic_destiny_delayed_reveal``) — RETIRED (ADR-0039 task #82
# grammar sprint): ``tree_synthesis._arm_cheat_synthetic_destiny_delayed_
# reveal`` ports this bridge's own verbatim idiom regex onto the shared
# ``synth_cheat_reveal_or_put_battlefield`` marker node, which
# :func:`crosswalk_signals._cheat_into_play` now reads structurally instead
# of falling through to this ledger. Same membership (Synthetic Destiny,
# corpus-verified sole hit).
#
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
# Seven bridges originally closed the final base_pt_set stragglers left
# after this session's three structural closers (a ``LastCreated``
# resolved-tag accept, an empty-nested-description unit-level fallback, and
# a modal ``mode_abilities`` threaded-target walk — see
# :func:`~mtg_utils._deck_forge.crosswalk_signals._base_pt_set` and
# :func:`~mtg_utils._deck_forge.crosswalk_signals.
# _iter_base_pt_modal_threaded_statics`). Each census below is corpus-bound
# to EXACTLY its enumerated pins (re-verified 2026-07-11, phase v0.20.0,
# 31,622 commander-legal cards) — no blast-radius slop. Three of the seven
# (the whole-clause "have ... become" / conditional "is a(n) ... with base
# power and toughness N/N" / mass "have base power and toughness X/X"
# idioms) RETIRED this session (ADR-0039 task #82) into ``tree_synthesis.py``
# arms; the remaining four stay ledgered here.
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


# (1)-(3) formerly here: the "have ... base power ... become" scalar/copy
# re-assignment, the conditional "is a(n) ... with base power and
# toughness N/N" type-change, and the mass "have base power and toughness
# X/X, where X is ..." idioms — all RETIRED this session (ADR-0039 task
# #82 grammar sprint) into ``tree_synthesis.py`` arms
# (``_arm_base_pt_have_become``, ``_arm_base_pt_is_a_type_with``,
# ``_arm_base_pt_mass_where_x``): the regex reads moved from this lane-
# embedded bridge into a gap-gated tree-build-time synthesis stage, and
# ``_base_pt_set`` now reads the synthesized concept node structurally.

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


# ── Duskana / Bess → base_power_matters: RETIRED (ADR-0039 task #82) ─────────
# The conjunctive "base power AND toughness N/N" reference bridge graduated
# into ``tree_synthesis._arm_base_power_ref_conjunctive`` this session — the
# ``_BASE_POWER_REF`` combinator scan moved there verbatim, and
# ``_base_power_matters`` now reads the synthesized concept node
# structurally instead of calling this module.

# ── Katilda / Old-Growth Troll / Tazri → ramp ─────────────────────────────────
# A ``GrantAbility`` whose OWN quoted text mentions "add mana" but whose
# ``definition.effect`` itself parks as ``Unimplemented`` (the granted
# ability's body never structures at all): Katilda's "{T}: Add one mana of
# any of ~'s colors" (a self-referential dynamic-color derivation the
# clause grammar can't structure), Tazri's identical shape, and Old-Growth
# Troll's compound "Enchanted Forest has '{T}: Add {G}{G}' and '{1}, {T},
# Sacrifice ~: Create...'" (TWO quoted granted abilities joined by "and"
# the grant parser doesn't split).
_RAMP_GRANT_UNIMPL_RX = re.compile(
    r"\badd\b[^.]*(\{[A-Za-z0-9]{1,3}\}|\bmana\b)", re.IGNORECASE
)


def _ramp_grant_unimplemented_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            d = getattr(n, "definition", None)
            if d is None:
                continue
            if tag_of(getattr(d, "effect", None)) != "Unimplemented":
                continue
            desc = getattr(d, "description", "") or ""
            if _RAMP_GRANT_UNIMPL_RX.search(desc):
                return True
    return False


def _ramp_grant_unimplemented_match(tree: ConceptTree) -> bool:
    return _ramp_grant_unimplemented_gap(tree)


# ── The scaling/restricted/note-type "Add mana" residue class → ramp ────────
# A card-name-keyed enumeration (CONTEXT.md's third residue class) rather
# than a generic substring: every card here is CR-verified this session as
# a genuine legacy ``ramp`` member via TWO independent legacy mechanisms —
# ``old_ir_for``'s own category=='ramp' structural classification (a
# from-scratch grammar phase's parser doesn't share, 17 of 24), or the
# byte-identical KEPT MIRROR pair legacy explicitly maintains as
# authoritative for this exact residue (``_RAMP_MATTERS_REGEX`` /
# ``_MANA_DORK_SUPPORT_MIRROR`` in _signals_ir.py, 7 of 24) — phase parks
# EVERY one of these as an ``Unimplemented`` residue somewhere in the tree
# (a dynamic/scaling count — Neheb's "for each 1 life...", Fangorn's "twice
# that much"; a restricted-spend/note-type rider — Adarkar Unicorn, Ice
# Cauldron, Jeweled Amulet, Kyren Toy; a die-roll/sticker table —
# "Name Sticker" Goblin, Unglued Pea-Brained Dinosaur, ________ Goblin; a
# player-choice recipient — Victory Chimes; a reveal-from-hand conditional
# wrapper — Chancellor of the Tangle). A whole-card text regex would
# over-fire (verified this session: a naive "add ... mana" pattern matches
# reminder text describing a CREATED TOKEN's own ability — Deadly
# Derision's Treasure token, T'Challa's Vibranium token — cards legacy does
# NOT serve), so the name enumeration is the bounded anchor instead.
_RAMP_DROPPED_NAMES: frozenset[str] = frozenset(
    {
        "Neheb, the Eternal",
        "Benthic Explorers",
        "Victory Chimes",
        "Megatron, Tyrant",
        "Su-Chi Cave Guard",
        "Raggadragga, Goreguts Boss",
        "Braid of Fire",
        "Plasm Capture",
        "Elemental Resonance",
        "Rasputin, the Oneiromancer",
        "Conduit of Emrakul",
        "Adarkar Unicorn",
        "Spoils of Evil",
        "Ice Cauldron",
        "Jeweled Amulet",
        "Tundra Fumarole",
        "Fangorn, Tree Shepherd",
        "Kyren Toy",
        "Chancellor of the Tangle",
        "Charmed Pendant",
        "Squandered Resources",
        "Unglued Pea-Brained Dinosaur",
        "________ Goblin",
        '"Name Sticker" Goblin',
    }
)


def _ramp_dropped_clause_gap(tree: ConceptTree) -> bool:
    return not tree.is_type("Land") and not tree.effect_concepts("ramp")


def _ramp_dropped_clause_match(tree: ConceptTree) -> bool:
    return tree.name in _RAMP_DROPPED_NAMES


# ── Ambush Commander → land_creatures_matter ─────────────────────────────────
# "Forests you control are 1/1 green Elf creatures that are still lands." —
# the subtype (not core-type) land-animate mass-static idiom
# (crosswalk_signals._is_creature_animator / the mass-static-def arm both
# gate on the CORE type "Land" in the affected filter; a SUBTYPE-only
# affected filter like "Forests" needs its own clause-grammar verb, CR
# 305.3/305.7). Phase's static parser drops the WHOLE line as
# ``Unimplemented(name='unknown')`` — no typed AddType/affected-filter node
# survives anywhere for it.
def _land_creatures_subtype_animate_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        eff = getattr(unit.node, "effect", None)
        if tag_of(eff) == "Unimplemented":
            desc = getattr(eff, "description", "") or ""
            if re.search(
                r"you control are [^.]*creatures?[^.]*\bstill lands?\b",
                desc,
                re.IGNORECASE,
            ):
                return True
    return False


def _land_creatures_subtype_animate_match(tree: ConceptTree) -> bool:
    return _land_creatures_subtype_animate_gap(tree)


# ── Primal Adversary / Sage of the Maze → land_creatures_matter ──────────────
# A land-animate clause whose CREATURE COUNT is dynamic/deferred (a "pay
# this cost N times, then up to that many target lands become creatures"
# repeat-count chain — Primal Adversary; a P/T formula "twice the number of
# Gates you control" embedded in a single-target animate — Sage of the
# Maze) blocks the clause grammar's animate-effect parse entirely; the
# WHOLE clause parks as ``Unimplemented`` with no typed Animate/AddType
# node anywhere. Distinct grammar gap from the Ambush Commander subtype-mass
# idiom above (a per-target/per-count deferred value, not a bare subtype
# filter) but the SAME root cause (a dynamic value inside an "X becomes a
# creature" clause) — grouped as one idiom-class per the ledger's
# per-idiom-class row rule.
def _land_creatures_dynamic_animate_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        desc = getattr(unit.node, "description", "") or ""
        if not re.search(
            r"\blands?\b[^.]*\bbecomes?\b[^.]*\bcreatures?\b", desc, re.IGNORECASE
        ):
            continue
        if any(tag_of(n) == "Unimplemented" for n in iter_typed_nodes(unit.node)):
            return True
    return False


def _land_creatures_dynamic_animate_match(tree: ConceptTree) -> bool:
    return _land_creatures_dynamic_animate_gap(tree)


# ── Earth Rumble Wrestlers → land_creatures_matter ───────────────────────────
# "~ gets +1/+0 and has trample as long as you control a land creature or a
# land entered the battlefield under your control this turn." — a
# ``_matters``-style CONDITION-REFERENCE payoff (CR 305/110.1's "land
# creature" concept combined via an Or with a landfall self-state check);
# phase's condition parser fails the compound Or, parking the WHOLE
# condition as ``T_condition__Unrecognized`` — the "land creature" reference
# survives only in that node's own ``text`` field (a typed field, not a
# whole-card regex).
def _land_creatures_condition_ref_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unrecognized":
                text = getattr(n, "text", "") or ""
                if "land creature" in text.lower():
                    return True
    return False


def _land_creatures_condition_ref_match(tree: ConceptTree) -> bool:
    return _land_creatures_condition_ref_gap(tree)


# ── exile_matters bridges (ADR-0039 W7, 2026-07-12) ──────────────────────────


# (1) Mairsil, the Pretender / Rex, Cyber-Hound — "~ has all activated
# abilities of all cards [you own] in exile with [a] <kind> counter[s] on
# them" (CR 113.10 — an effect that ADDS an ability). Phase's static parser
# recognizes the line but fails to structure it (the SAME failure family as
# Bello's animate line): ``Unimplemented(name='static_structure')`` with no
# ``GrantAbility``/``GrantStaticAbility`` node anywhere for the granted-
# ability-suite idiom. Grouped as ONE idiom class (same diagnostic name,
# same clause shape — "has all activated abilities" is the load-bearing
# anchor, not the counter-kind word).
_MAIRSIL_REX_RX = re.compile(
    r"has all (?:the )?activated abilities of all cards (?:you own )?in"
    r" exile with [^.]* counters? on (?:it|them)",
    re.IGNORECASE,
)


def _mairsil_rex_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _static_parse_failure_descs(tree))


def _mairsil_rex_match(tree: ConceptTree) -> bool:
    return any(_MAIRSIL_REX_RX.search(d) for d in _static_parse_failure_descs(tree))


# (2) Grolnok, the Omnivore — "You may play lands and cast spells from among
# cards you own in exile with croak counters on them" (CR 305.1 land-play
# permission / CR 601.3 cast permission). A DIFFERENT phase diagnostic name
# than (1) — ``Unimplemented(name='effect_structure')`` ("Effect sentence
# candidate but line failed effect parser") — so a separate gap/match pair,
# even though the surface idiom (a counter-gated persistent exile pile as a
# play/cast resource) is a sibling of (1)'s ability-grant idiom.
def _effect_structure_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) == "Unimplemented"
                and getattr(n, "name", None) == "effect_structure"
            ):
                yield getattr(n, "description", "") or ""


_GROLNOK_RX = re.compile(
    r"play lands and cast spells from among cards you own in exile with"
    r" [^.]* counters? on (?:it|them)",
    re.IGNORECASE,
)


def _grolnok_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _effect_structure_descs(tree))


def _grolnok_match(tree: ConceptTree) -> bool:
    return any(_GROLNOK_RX.search(d) for d in _effect_structure_descs(tree))


# (3) Candlekeep Inspiration — "Until end of turn, creatures you control
# have base power and toughness X/X, where X is the number of cards you own
# in exile and in your graveyard that are instant cards, are sorcery cards,
# and/or have an Adventure" (CR 107.3 X-as-placeholder / 613.4c
# characteristic-defining). A THIRD diagnostic name —
# ``Unimplemented(name='creatures')`` — the whole dynamic P/T-setter clause
# dropped wholesale with no ``SetDynamicPower``/``SetDynamicToughness`` pair
# anywhere in the tree.
def _creatures_unimpl_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == (
                "creatures"
            ):
                yield getattr(n, "description", "") or ""


_CANDLEKEEP_RX = re.compile(
    r"where x is the number of cards you own in exile", re.IGNORECASE
)


def _candlekeep_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _creatures_unimpl_descs(tree))


def _candlekeep_match(tree: ConceptTree) -> bool:
    return any(_CANDLEKEEP_RX.search(d) for d in _creatures_unimpl_descs(tree))


# (4) Close Encounter — "As an additional cost to cast this spell, choose a
# creature you control or a warped creature card you own in exile" (CR
# 601.2f additional cost). ZERO residue anywhere: ``unit.costs`` is empty
# and no ``Unimplemented`` node carries the clause text either (confirmed
# via direct tree dump) — an ABSENCE proof, the Degavolver precedent, since
# there is no residue node to read.
_CLOSE_ENCOUNTER_RX = re.compile(
    r"warped creature card you own in exile", re.IGNORECASE
)


def _close_encounter_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        if unit.costs:
            return False
        for n in iter_typed_nodes(unit.node):
            if "Exile" in filter_inzone_zones(getattr(n, "filter", None)):
                return False
            if "Exile" in filter_inzone_zones(getattr(n, "target", None)):
                return False
    return True


def _close_encounter_match(tree: ConceptTree) -> bool:
    return bool(_CLOSE_ENCOUNTER_RX.search(tree.oracle or ""))


# (5) Kaya the Inexorable — the -7 emblem's granted trigger's OWN
# description names "from your hand, from your graveyard, or from among
# cards you own in exile" (CR 601.3 cast permission), but the granted
# ``CastFromZone`` effect's target filter carries ONLY the hand-zone
# branch — the graveyard/exile alternate-source clause is dropped from the
# target filter entirely. Anchored to the OWNING trigger's own description
# (not a whole-card scan), mirroring the module's ``_unknown_mode_*``
# per-node last-resort family.
def _kaya_emblem_cast_from_exile_drop(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "CreateEmblem":
                continue
            for trig in getattr(n, "triggers", None) or []:
                desc = (getattr(trig, "description", "") or "").lower()
                if "in exile" not in desc:
                    continue
                execute = getattr(trig, "execute", None)
                eff = getattr(execute, "effect", None) if execute else None
                if tag_of(eff) != "CastFromZone":
                    continue
                target = getattr(eff, "target", None)
                if "Exile" not in filter_inzone_zones(target):
                    return True
    return False


# ── voltron_matters bridges (ADR-0039 W7, 2026-07-12) ─────────────────────────

# Duplicated (not imported) from crosswalk_signals — same rationale as
# _LAND_SUBTYPES (crosswalk_signals imports bridge_fires FROM this module).
_VOLTRON_SUBTYPES: frozenset[str] = frozenset({"aura", "equipment", "role"})

# (1) Judgment Bolt / Animal Friend / Sage's Reverie — the SAME idiom class:
# an Aura/Equipment ATTACHMENT-COUNT scaling clause ("for each Aura/
# Equipment ... attached", "where X is the number of Equipment you
# control") that phase drops entirely — the corresponding count/value node
# is a bare ``Fixed`` (Animal Friend's PutCounter count=Fixed(1), Sage's
# Reverie's Draw count=Fixed(1) and AddPower/AddToughness value=1, Judgment
# Bolt's DealDamage carries no second recipient/scaling node at all) with
# NO ``ObjectCount``/``Aggregate`` scoped to Equipment/Aura anywhere in the
# tree to descend into (CR 301.5/303.4/107.3). Tightly anchored (not the
# legacy ``VOLTRON_PAYOFF_REGEX`` bare "equipment you control" branch,
# which over-fires on Affinity-for-Equipment reminder text and imperative
# attach-ACTION clauses — see the census note below): requires "for each
# Aura/Equipment ... attached" IN THE SAME CLAUSE, or the "where X is the
# number of Equipment you control" scaling frame specifically.
_VOLTRON_SCALING_RX = re.compile(
    r"\bfor each (?:aura|equipment)\b[^.]*\battached\b"
    r"|\bwhere x is the number of equipment you control\b",
    re.IGNORECASE,
)


def _voltron_scaling_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) not in ("ObjectCount", "Aggregate"):
                continue
            filt = getattr(n, "filter", None)
            if filt is not None and (
                {s.lower() for s in filter_subtypes(filt)} & _VOLTRON_SUBTYPES
            ):
                return False
    return True


def _voltron_scaling_match(tree: ConceptTree) -> bool:
    return bool(_VOLTRON_SCALING_RX.search(tree.oracle or ""))


# (2) Warchanter Skald — "Whenever ~ becomes tapped, if it's enchanted or
# equipped, create a 2/1 red Dwarf Berserker creature token" (CR 301.5c /
# 303.4c). The trigger's OWN ``condition`` field is ``None`` — "if it's
# enchanted or equipped" survives ONLY inside the trigger's whole-clause
# ``description`` string, indistinguishable from a genuinely-absent
# condition on any other trigger. Anchored to the SPECIFIC trigger node
# (mode='Taps', condition is None) rather than a whole-card scan.
def _warchanter_condition_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if getattr(unit.node, "mode", None) != "Taps":
            continue
        if getattr(unit.node, "condition", None) is None:
            return True
    return False


def _warchanter_condition_match(tree: ConceptTree) -> bool:
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if getattr(unit.node, "mode", None) != "Taps":
            continue
        desc = (getattr(unit.node, "description", "") or "").lower()
        if "enchanted or equipped" in desc or "equipped or enchanted" in desc:
            return True
    return False


# (3) Forge Anew — "You may pay {0} rather than pay the equip cost of the
# first equip ability you activate during each of your turns" (CR 601.2f /
# 702.6c). The {0}-alternative-payment half parses as a bare unlinked
# ``PayCost`` node with no reachable Equipment/equip-keyword tag tying it
# to the granted timing permission — Bruenor Battlehammer's structurally
# IDENTICAL clause is excluded because Bruenor ALSO carries a genuine
# ObjectCount/Aggregate Equipment-count scalar elsewhere on the SAME card
# ("+2/+0 for each Equipment attached to it"), so its ``voltron_matters``
# is already served through that other arm before this bridge is ever
# reached (the ``bridge_fires`` gate call site in crosswalk_signals.py sits
# at the END of the lane, after every structural arm has already tried).
_FORGE_ANEW_RX = re.compile(r"pay \{0\} rather than pay the equip cost", re.IGNORECASE)


def _forge_anew_paycost_unlinked_gap(tree: ConceptTree) -> bool:
    """A ``PayCost({0})`` node exists but no equip-keyword
    ``ReduceAbilityCost`` tag reaches the same unit — the alternative-
    payment clause is structurally unlinked from the equip ability it
    modifies. Self-retires once phase ties the two together."""
    for unit in tree.units:
        has_paycost_zero = False
        has_equip_link = False
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "PayCost":
                cost = getattr(n, "cost", None)
                mana_cost = getattr(cost, "cost", None)
                if getattr(mana_cost, "generic", None) == 0 and not getattr(
                    mana_cost, "shards", None
                ):
                    has_paycost_zero = True
            if (
                tag_of(n) == "ReduceAbilityCost"
                and str(getattr(n, "keyword", "")).lower() == "equip"
            ):
                has_equip_link = True
        if has_paycost_zero and not has_equip_link:
            return True
    return False


def _forge_anew_match(tree: ConceptTree) -> bool:
    return bool(_FORGE_ANEW_RX.search(tree.oracle or ""))


# ── target_player_draws residual class (ADR-0039 W7 BRIDGES wave) ──────────
# ``_TARGETED_DRAW_WIDENED_TAGS``, duplicated (not imported) from
# crosswalk_signals — the SAME layering reason ``_LAND_SUBTYPES`` is
# duplicated at the top of this module (crosswalk_signals imports
# ``bridge_fires`` FROM here, so the reverse import would be circular).
_TPD_WIDENED_TAGS: frozenset[str] = frozenset(
    {
        "Typed",
        "ParentTargetController",
        "TriggeringPlayer",
        "ParentTargetOwner",
        "TriggeringSourceController",
    }
)


# Fatal Lore / Season of the Burrow / Ertai Resurrected / Balor each carry a
# typed ``Draw`` node with a recipient tag already in
# ``_TPD_WIDENED_TAGS`` — the SAME shape the live arm's phrase gate
# ordinarily confirms — but the owning unit's OWN ``description`` is either
# ``None`` (Fatal Lore's second mode, Season of the Burrow's exile mode) or
# a synthetic trigger-condition label ("When ~ enters", "Whenever ~
# attacks"/"Whenever ~ dies" — Ertai Resurrected, Balor), never the modal
# bullet's/attack-or-dies mode's own English (CR 121.1/608.2h — the
# grammar's own frontier for attributing modal/multi-triggered-event text
# down to its unit). The gap is a per-unit residue-presence check (does
# this Draw node's own recipient tag exist without ANY reachable "draw"-
# mentioning text) so it self-retires the day phase/our own unit-synthesis
# attributes real English there — the pre-existing phrase gate then fires
# through the LIVE arm with zero further edits, same as every other
# bridge's self-retirement. Corpus-verified 2026-07-12, phase v0.20.0,
# 31,622 commander-legal: this shared gap hits 9 cards total (Balor, Ertai
# Resurrected, Fall of the First Civilization, Fatal Lore, Love Song of
# Night and Day, Season of the Burrow, The Legend of Yangchen // Avatar
# Yangchen, Vault 11: Voter's Dilemma, Your Temple Is Under Attack) — the
# other 5 are EITHER already closed by the pre-existing self-paired
# ``_unit_has_originalcontroller_draw``/``Vote``-branch admissions (Fall of
# the First Civilization, Love Song of Night and Day, The Legend of
# Yangchen, Your Temple Is Under Attack — see
# ``_target_player_draws``'s own W6-endgame docstring) or a genuine
# ADJUDICATED SHED (Vault 11: Voter's Dilemma — a GROUP ``All``-scoped
# outcome, not a directed gift; see
# ``test_target_player_draws_excludes_vote_council_self_payoff``) — so this
# bridge's own narrowly-anchored match (below) is the only thing that lets
# it fire, and it hits exactly the 4 pins.
def _tpd_widened_tag_no_draw_text(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Draw":
                continue
            if recipient_tag(n) not in _TPD_WIDENED_TAGS:
                continue
            desc = (getattr(unit.node, "description", None) or "").lower()
            if "draw" not in desc:
                return True
    return False


_TPD_SYNTHETIC_DESC_RX = re.compile(
    r"that player draws up to three cards|"
    r"exile target nonland permanent\. its controller draws a card|"
    r"counter target spell, activated ability, or triggered ability\. "
    r"its controller draws a card|"
    r"destroy another target creature or planeswalker\. "
    r"its controller draws a card|"
    r"target opponent draws three cards, then discards three cards at "
    r"random",
    re.IGNORECASE,
)


def _tpd_widened_tag_synthetic_desc_match(tree: ConceptTree) -> bool:
    return bool(_TPD_SYNTHETIC_DESC_RX.search(tree.oracle or ""))


# The Wedding of River Song's "Draw two cards, then you may exile a
# nonland card ... Then target opponent does the same." — the ellipsis
# repeat-for-another-player construct is a NAMED grammar token our own
# clause_grammar.py already recognizes (the Unimplemented decorator's own
# ``name`` field is literally ``target_opponent_does_the_same``) but has no
# concept mapping in recovery.py's ALLOWLIST yet (ADR-0039 forbids adding
# one this session — grammar-blocked, task #82's territory). Gap and match
# are the SAME residue-presence check (the ``sac_devour_unimplemented``
# precedent): the named token's mere existence both proves the substrate
# still lacks the mapping AND identifies the idiom precisely enough to
# serve it — no separate text anchor needed. Corpus-verified sole hit,
# 2026-07-12, phase v0.20.0, 31,622 commander-legal.
def _tpd_wedding_ellipsis_repeat_gap(tree: ConceptTree) -> bool:
    return any(
        True
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
        if tag_of(n) == "Unimplemented"
        and getattr(n, "name", None) == "target_opponent_does_the_same"
    )


def _tpd_wedding_ellipsis_repeat_match(tree: ConceptTree) -> bool:
    return _tpd_wedding_ellipsis_repeat_gap(tree)


# ── opponent_discard residual class (ADR-0039 W7 BRIDGES wave) ─────────────
# Shared with ``lifeloss_makers``' ``withercrown_unless_lose_life`` bridge:
# a discard-payoff "unless" clause phase's trigger/ability parser fails
# wholesale, parking the WHOLE clause as an ``Unimplemented('Unsupported
# unless clause')`` residue (CR 119.4 — an unless-cost payment). Reuses
# :func:`_unless_clause_failure_descs` (defined above, module-shared, NOT
# re-derived) — the SAME residue-scan function, a different direction
# anchor. Tainted Specter's "Target player discards a card unless they put
# a card from their hand on top of their library" and Remorseless
# Punishment's "Target opponent loses 5 life unless that player discards
# two cards or sacrifices ..." both name the discard as the UNLESS-avoided
# consequence. Wand of Ith carries the SAME residue class (its second
# branch, "the player discards it unless they pay life equal to its mana
# value") but is served INDEPENDENTLY — its FIRST branch already resolves
# through a genuine typed ``DiscardCard{target: ParentTarget}`` node
# elsewhere in the same tree, so it never reaches this bridge's gap at all
# (verified via direct tree dump: Wand of Ith already fires structurally,
# not via this bridge). Corpus-verified 2026-07-12, phase v0.20.0,
# 31,622 commander-legal: exactly 2 hits.
_OPP_DISCARD_UNLESS_RX = re.compile(
    r"target player discards? a card unless|"
    r"target opponent loses \d+ life unless that player discards",
    re.IGNORECASE,
)


def _opp_discard_unless_match(tree: ConceptTree) -> bool:
    return any(
        _OPP_DISCARD_UNLESS_RX.search(d) for d in _unless_clause_failure_descs(tree)
    )


def _opp_discard_unless_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _unless_clause_failure_descs(tree))


# Bladecoil Serpent's "When ~ enters, for each {B}{B} spent to cast it,
# each opponent discards a card." — a mana-spent SCALING prefix (CR
# 601.2f — mana spent to cast a spell) whose DOMINANT recovered grammar
# token is "for", not the inner clause's own verb ("discard") — the
# post-deletion grammar sprint's scaling-prefix-peel TODO, not this
# session's (ADR-0039 forbids a new clause_grammar.py verb). The residue
# node's OWN description preserves the full clause verbatim, so the match
# is a tight, self-anchored end-of-clause read (Hollow Marauder's
# superficially similar "For each of those opponents who didn't discard a
# card ..., draw a card" residue is a DIFFERENT payoff, a DRAW gated on
# non-discarders, correctly excluded — its clause doesn't END in "each
# opponent discards a card"). Corpus-verified sole hit, 2026-07-12, phase
# v0.20.0, 31,622 commander-legal.
_OPP_DISCARD_FOR_SCALING_RX = re.compile(
    r"each opponent discards a card\s*$", re.IGNORECASE
)


def _opp_discard_for_scaling_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "for":
                yield getattr(n, "description", "") or ""


def _opp_discard_for_scaling_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _opp_discard_for_scaling_descs(tree))


def _opp_discard_for_scaling_match(tree: ConceptTree) -> bool:
    return any(
        _OPP_DISCARD_FOR_SCALING_RX.search(d)
        for d in _opp_discard_for_scaling_descs(tree)
    )


# Yawgmoth Merfolk Soul's Unfinity Stickers "{TK}{TK} — When ~ leaves the
# battlefield, target player discards a card." — the SAME {TK}-placeholder
# cost-grammar frontier ``base_pt_tk_sticker_parse_failure`` (Cool Fluffy
# Loxodon) closes for base_pt_set, here on a DIFFERENT granted ability
# (CR 123.1 — Stickers). The residue node's own description preserves the
# full clause verbatim (unlike the base_pt case, no separate hook-text
# read needed — the "target player discards a card" payoff is right there
# in the SAME Unimplemented). Corpus-verified sole hit, 2026-07-12, phase
# v0.20.0, 31,622 commander-legal.
_YAWGMOTH_TK_DISCARD_RX = re.compile(
    r"\{TK\}.*?—.*?target player discards a card", re.IGNORECASE
)


def _yawgmoth_tk_discard_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "unknown":
                yield getattr(n, "description", "") or ""


def _yawgmoth_tk_discard_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _yawgmoth_tk_discard_descs(tree))


def _yawgmoth_tk_discard_match(tree: ConceptTree) -> bool:
    return any(
        _YAWGMOTH_TK_DISCARD_RX.search(d) for d in _yawgmoth_tk_discard_descs(tree)
    )


# Words of Waste's "{1}: The next time you would draw a card this turn,
# each opponent discards a card instead." — a REPLACEMENT-idiom "the next
# time ... instead" clause (CR 614.1) collapses WHOLESALE to a bare
# determiner-token residue, ``Unimplemented(name='the')`` — our own
# clause grammar's dominant-token detector picks the sentence's leading
# word ("The") rather than any verb at all, since the whole clause is one
# unbroken replacement rider with no imperative to peel. Gap and match
# are the SAME residue-presence check (mirrors ``tpd_wedding_ellipsis_
# repeat``'s precedent): the residue's own preserved text is specific
# enough to serve without a separate anchor. Corpus-verified sole hit,
# 2026-07-12, phase v0.20.0, 31,622 commander-legal.
_WORDS_OF_WASTE_RX = re.compile(
    r"next time you would draw a card this turn, each opponent discards "
    r"a card instead",
    re.IGNORECASE,
)


def _words_of_waste_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "the":
                yield getattr(n, "description", "") or ""


def _words_of_waste_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _words_of_waste_descs(tree))


def _words_of_waste_match(tree: ConceptTree) -> bool:
    return any(_WORDS_OF_WASTE_RX.search(d) for d in _words_of_waste_descs(tree))


# ``_no_typed_discard_node`` — the shared gap for the two dropped-clause
# bridges below: no ``Discard``/``DiscardCard``-tagged node reachable
# ANYWHERE in the tree, mirroring ``sacrifice_outlets``'
# ``_no_typed_sacrifice_node`` precedent exactly (a broad, self-retiring
# absence proof; the narrow per-card ``match`` below is what keeps each
# bridge a scalpel, not a lane).
def _no_typed_discard_node(tree: ConceptTree) -> bool:
    return not any(
        tag_of(n) in ("Discard", "DiscardCard")
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


# Fungal Shambler's "Whenever ~ deals damage to an opponent, you draw a
# card and that opponent discards a card." — phase structures the FIRST
# conjunct (a typed ``Draw{recipient: Controller}``) but the SECOND
# conjunct drops WHOLESALE: zero trace anywhere in the tree, not even an
# ``Unimplemented`` residue (CR 701.9). Corpus-verified sole hit, 2026-07-12,
# phase v0.20.0, 31,622 commander-legal.
_FUNGAL_SHAMBLER_RX = re.compile(
    r"deals damage to an opponent, you draw a card and that opponent "
    r"discards a card",
    re.IGNORECASE,
)


def _fungal_shambler_match(tree: ConceptTree) -> bool:
    return bool(_FUNGAL_SHAMBLER_RX.search(tree.oracle or ""))


# Mindculling's "You draw two cards and target opponent discards two
# cards." — the SAME shared no-typed-Discard-node absence proof; the first
# conjunct's ``Draw{recipient: Controller}`` is the only node the whole
# ability produces, the second conjunct drops with ZERO trace. Corpus-
# verified sole hit, 2026-07-12, phase v0.20.0, 31,622 commander-legal.
_MINDCULLING_RX = re.compile(
    r"you draw two cards and target opponent discards two cards",
    re.IGNORECASE,
)


def _mindculling_match(tree: ConceptTree) -> bool:
    return bool(_MINDCULLING_RX.search(tree.oracle or ""))


# Driven // Despair's "Despair" half never gets a phase record at all (the
# SAME Aftermath-back-half gap ``opponent_discard``'s own W2c text-only-
# tree arm closes for Consign // Oblivion) — this face's granted-ability
# quoted text ("Whenever this creature deals combat damage to a player,
# that player discards a card.") is a "that player" BACK-REFERENCE with no
# "target opponent"/"target player"/"each player" anchor
# :data:`~mtg_utils._deck_forge.crosswalk_signals._TEXT_ONLY_OPP_DISCARD_
# RX` requires — correctly NOT matched by the existing last-resort sweep
# (see that regex's own module comment). Gap is "no REAL (phase-parsed)
# unit anywhere" rather than a bare ``not tree.units`` — this exact face's
# text ALSO trips an UNRELATED ``apply_tree_synthesis`` arm (a whole-card
# scan matching the SAME "deals combat damage to a player" wording), which
# appends a synthetic ``origin="synth"`` wrapper unit onto the tree BEFORE
# this lane ever runs; ``all(u.origin == "synth" for u in tree.units)``
# generalizes the main lane's own zero-unit check (vacuously true for a
# genuinely empty tuple too) so the gap still holds. The narrow per-card
# match keeps this a scalpel (Consign // Oblivion's "Oblivion" face is
# ALSO a no-real-unit tree but its own "Target opponent discards two
# cards" text doesn't match this bridge's back-reference-shaped anchor —
# it's already served by the pre-existing sweep instead). Corpus-verified
# sole hit, 2026-07-12, phase v0.20.0, 31,622 commander-legal.
_DRIVEN_DESPAIR_RX = re.compile(
    r"deals combat damage to a player, that player discards a card",
    re.IGNORECASE,
)


def _driven_despair_gap(tree: ConceptTree) -> bool:
    return all(u.origin == "synth" for u in tree.units)


def _driven_despair_match(tree: ConceptTree) -> bool:
    return bool(_DRIVEN_DESPAIR_RX.search(tree.oracle or ""))


# Jagged Poppet's "Hellbent — Whenever ~ deals combat damage to a player,
# if you have no cards in hand, that player discards cards equal to the
# damage." — the "discard cards equal to the damage" clause DOES recover
# via the "discard" ALLOWLIST token (its own Unimplemented residue
# preserves that exact wording), but the DIRECTION ("that player" = the
# player dealt combat damage) has no typed recipient of its own to
# resolve, and the trigger's own valid_target reads a bare 'Player' (not
# an explicit Opponent-shaped actor _OPP_DISCARD_ACTORS admits) — the
# same bare-Player-vs-Opponent ambiguity a GENERAL widening would risk
# over-firing genuinely symmetric multiplayer group-hug triggers on. The
# gap is scoped to this idiom's OWN residue text (not the general "any
# recovered discard with unresolved direction" shape, which would be far
# too broad to serve as a self-retiring proof) — CR 510 (combat damage),
# 701.9. Corpus-verified sole hit, 2026-07-12, phase v0.20.0, 31,622
# commander-legal.
def _jagged_poppet_discard_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "discard":
                yield getattr(n, "description", "") or ""


def _jagged_poppet_gap(tree: ConceptTree) -> bool:
    return any(
        "equal to the damage" in d.lower() for d in _jagged_poppet_discard_descs(tree)
    )


def _jagged_poppet_match(tree: ConceptTree) -> bool:
    return _jagged_poppet_gap(tree)


# ── Rock Hydra → plus_one_matters ────────────────────────────────────────────
# "For each 1 damage that would be dealt to ~, if it has a +1/+1 counter on
# it, remove a +1/+1 counter from it and prevent that 1 damage." (CR 122.1,
# a P1P1 self-condition damage-prevention replacement) — phase's static
# parser fails the WHOLE line (the SAME ``static_structure`` residue shape
# Bello, Bard of the Brambles's bridge reads), so no typed HasCounters/
# QuantityCheck condition node exists anywhere for the existing condition-
# site arms to reach. ADR-0039 W8 (2026-07-12).
_ROCK_HYDRA_RX = re.compile(r"if it has a \+1/\+1 counter on it", re.IGNORECASE)


def _rock_hydra_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _static_parse_failure_descs(tree))


def _rock_hydra_match(tree: ConceptTree) -> bool:
    return any(_ROCK_HYDRA_RX.search(d) for d in _static_parse_failure_descs(tree))


# ── Hierophant Bio-Titan → plus_one_matters ──────────────────────────────────
# "Frenzied Metabolism — As an additional cost to cast this spell, you may
# remove any number of +1/+1 counters from among creatures you control.
# This spell costs {2} less to cast for each counter removed this way." (CR
# 601.2f) — phase structures the cost-reduction scaler as a ``ModifyCost``
# static whose ``dynamic_count`` is ``PreviousEffectAmount`` (the amount
# scales off the OTHER effect that already ran — the additional-cost
# removal), but that ``PreviousEffectAmount`` node carries NO counter-kind
# field at all: phase's own encoding of "however many of the PRECEDING
# effect" drops which counter kind the preceding effect removed. A dropped
# clause, not reachable by any accessor — the node shape itself has nowhere
# to put the kind. ADR-0039 W8 (2026-07-12).
_HIEROPHANT_RX = re.compile(r"\+1/\+1 counters?", re.IGNORECASE)


def _hierophant_modifycost_descs(tree: ConceptTree) -> Iterator[str]:
    for unit in tree.units:
        if unit.origin != "static":
            continue
        dyn = static_mode_field(unit.node, "dynamic_count")
        if tag_of(dyn) == "PreviousEffectAmount":
            yield getattr(unit.node, "description", "") or ""


def _hierophant_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _hierophant_modifycost_descs(tree))


def _hierophant_match(tree: ConceptTree) -> bool:
    return any(_HIEROPHANT_RX.search(d) for d in _hierophant_modifycost_descs(tree))


# ── named_synergy (ADR-0039 W8, the KEPT-twelve wave) ────────────────────────
# CR 201.4 (choosing a card name) / 201.5 (self-reference by name): a card
# whose ability references a specific permanent BY NAME — another copy of
# ITSELF (Brothers Yamazaki's legend-rule bypass, Alania Divergent Storm's
# "another Alania"), or a genuinely different card (Mishra, Claimed by Gix's
# meld partner, Rohgahh of Kher Keep's "Kobolds of Kher Keep"). phase v0.20.0
# DOES now preserve the literal name string on a typed ``Named`` filter
# property/predicate (``T_properties__Named`` / ``T_filter__Named`` both
# carry a real ``name: str`` field — this SUPERSEDES the stale ADR-0027 claim
# that "phase drops the referenced name"), but that SAME typed shape is
# massively overloaded: partner-pair references (CR 716.3 — Will Kenrith /
# Rowan Kenrith), planeswalker-uncoupled "Path of the X" callbacks, deck-
# construction copy-limit swarms (Relentless Rats — CR 100.2a, the SIBLING
# copy_limit lane's own territory), and named-card library TUTORING (Squadron
# Hawk — "search for a card named X") all route through the identical typed
# node. Corpus-verified 2026-07-12 (phase v0.20.0): 245 commander-legal cards
# carry a ``Named`` node ANYWHERE, vs this lane's 27-card legacy population —
# an ~9x blast radius, far past the ~2x tighten bar — so a blind "any Named
# node" deep walk is not a safe port. Discriminating the permanent-synergy
# idiom from the other four Named-node uses needs a dedicated Named-context
# classifier (the todo); until it lands, the bridge's idiom-bounded ``match``
# (byte-identical to the deleted NAMED_PERMANENT_REGEX SWEEP producer, flat
# over the reminder-stripped per-face oracle — the SAME input the legacy
# _IR_KEPT_DETECTORS mirror reads) is what keeps this lane scoped to exactly
# legacy's population, not the raw gap.
_NAMED_SYNERGY_RE = re.compile(NAMED_PERMANENT_REGEX, re.IGNORECASE)


def _named_synergy_kept(tree: ConceptTree) -> str:
    """Reminder-stripped per-face oracle text — mirrors legacy's OWN
    paren-strip so this bridge's blast radius matches legacy's byte-for-
    byte, not an independently-invented pattern."""
    return _REMINDER_RX.sub(" ", tree.oracle or "")


def _named_synergy_gap(_tree: ConceptTree) -> bool:
    return True


def _named_synergy_match(tree: ConceptTree) -> bool:
    return bool(_NAMED_SYNERGY_RE.search(_named_synergy_kept(tree)))


# ── creatures_matter residual class (ADR-0039 W8 finisher) ──────────────────
# Seven bridges close the last of the key's 53-card true-gap tail (the
# TOKEN_MAKER_CROSS_OPEN / SYMMETRIC / BLOCKING_OR_ATTACKING / SUBTYPE_
# TRIBAL_YOU / DEVOUR / TRIBAL_SHARESQUALITY / OPPONENT_SCOPE / NAMED_SELF
# classes plus a cost-reduction (CR 601.2f) / self-CDA (CR 604.3/613.4a) /
# graveyard-zone (CR 400.2) / chosen-type-population (CR 205.3) shed set
# stay adjudicated NOT ported — see :func:`~mtg_utils._deck_forge.
# crosswalk_signals._creatures_matter`'s own docstring for the full
# accounting). A Formidable activation-restriction arm (CR 602.5/207.2c)
# landed structurally this session (:func:`~mtg_utils._deck_forge.
# crosswalk_signals._creatures_matter_formidable_condition` — a bespoke
# typed condition tag, not a bridge) alongside two tiny structural
# container-descent reads (a FlipCoin win-branch count operand and a
# reanimation target filter's nested ``Cmc``-property count operand,
# both :mod:`crosswalk_signals` too) — genuinely typed data the crosswalk
# simply wasn't reading yet, not a phase gap a bridge exists to paper
# over.


# (1) Lightning Runner's "untap all creatures you control" (CR 701.26) —
# the pay-{E} sub-ability chain IS structured (GainEnergy -> PayEnergy ->
# AdditionalPhase all typed), but the "untap all creatures you control"
# clause between them carries NO node at all, not even an Unimplemented
# residue: the SAME absence-proof gap shape as the sacrifice_outlets /
# direct_damage "ZERO trace" bridges above. Anchored to the card's full
# surrounding sentence (not the bare "untap all creatures you control"
# substring, which alone hits 32 commander-legal cards — Vitalize,
# Aurelia, Drumbellower, … — every one of them ALREADY structurally read
# by :func:`~mtg_utils._deck_forge.crosswalk_signals.
# _mass_untap_creature_filter`'s own SetTapState walk, so the shared gap
# below stands every one of them down on its own).
_LIGHTNING_RUNNER_UNTAP_RX = re.compile(
    r"pay eight \{E\}\. if you pay, untap all creatures you control, and "
    r"after this phase, there is an additional combat phase",
    re.IGNORECASE,
)


def _lightning_runner_gap(tree: ConceptTree) -> bool:
    return not any(
        tag_of(n) == "SetTapState"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _lightning_runner_match(tree: ConceptTree) -> bool:
    return bool(_LIGHTNING_RUNNER_UNTAP_RX.search(tree.oracle or ""))


# (2)-(4) Superior Numbers' excess-count comparator, Sovereign Okinec
# Ahau's per-creature counter distribution, and Whisperwood Elemental's
# face-up team-grant residue RETIRED (ADR-0039 task #82, post-deletion
# grammar sprint): each now decomposes into a typed
# ``tree_synthesis`` sweep-row node (the "creatures_matter grammar-sprint
# stragglers" section in ``tree_synthesis.py``) instead of a text-anchored
# bridge — same three pins, now firing structurally via
# ``synth_creatures_matter_excess_count`` /
# ``synth_creatures_matter_diff_counters`` /
# ``synth_creatures_matter_faceup_grant``.


# (5) Duskana, the Rage Mother's ETB "draw a card for each creature you
# control with base power and toughness 2/2" (CR 121.1 draw, 613.4b base
# P/T reference) — the ``Draw`` node IS typed, but its ``count`` field
# collapses to a bare ``Fixed(1)`` instead of a ``Ref(qty=ObjectCount(...
# base-power-2/2 filter))``; the dynamic count is dropped with no residue
# at all. Distinct from the ALREADY-LANDED ``duskana_bess_base_pt_and_
# toughness_ref`` bridge above (``base_power_matters`` key) — that bridge
# serves the SECOND ability's "creature ... with base power and toughness
# 2/2 attacks" REFERENCE; this one serves the FIRST ability's dropped
# COUNT, a different key, kept as a separate row/id per the ledger's
# one-key-per-row contract.
_DUSKANA_DRAW_COUNT_RX = re.compile(
    r"draw a card for each creature you control with base power and "
    r"toughness 2/2",
    re.IGNORECASE,
)


def _duskana_draw_count_gap(tree: ConceptTree) -> bool:
    return any(
        tag_of(n) == "Draw" and tag_of(getattr(n, "count", None)) != "Ref"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    )


def _duskana_draw_count_match(tree: ConceptTree) -> bool:
    return bool(_DUSKANA_DRAW_COUNT_RX.search(tree.oracle or ""))


# (6) Moku, Meandering Drummer's "Moku gets +2/+1 AND CREATURES YOU CONTROL
# GAIN HASTE until end of turn" (CR 113.10 ability grant) — phase folds
# BOTH clauses into ONE ``S_static_abilities`` def whose ``affected`` is
# ``SelfRef`` (Moku's own +2/+1) even though the SAME def's own
# ``modifications`` list also carries the team ``AddKeyword('Haste')`` —
# an upstream mis-scope (the def's OWN ``description`` still names "and
# creatures you control gain haste" verbatim, so the grant text survives,
# just attributed to the wrong ``affected`` population for
# :func:`~mtg_utils._deck_forge.crosswalk_signals.
# _iter_creatures_matter_static_defs`'s ``affected``-filter check to find
# it as a team anthem).
_MOKU_HASTE_GRANT_RX = re.compile(
    r"gets? \+\d+/\+\d+ and creatures you control gain haste", re.IGNORECASE
)


def _moku_haste_grant_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
                continue
            if _MOKU_HASTE_GRANT_RX.search(getattr(sdef, "description", "") or ""):
                return True
    return False


def _moku_haste_grant_match(tree: ConceptTree) -> bool:
    return _moku_haste_grant_gap(tree)


# (7) Siege Behemoth's "As long as this creature is attacking, FOR EACH
# CREATURE YOU CONTROL, you may have that creature assign its combat
# damage as though it weren't blocked" (CR 509.1h-adjacent unblocked-
# damage-assignment permission) — the static DEF exists (``affected``/
# ``modifications`` field pair present) but ``affected`` is ``SelfRef``
# and ``modifications`` is an EMPTY list; the whole per-creature grant
# lives only in the def's own ``description`` and an ``Unrecognized``
# condition text, never a typed mode or modification.
_SIEGE_BEHEMOTH_RX = re.compile(
    r"for each creature you control, you may have that creature assign "
    r"its combat damage as though it weren't blocked",
    re.IGNORECASE,
)


def _siege_behemoth_gap(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
                continue
            if getattr(sdef, "modifications", None):
                continue
            if _SIEGE_BEHEMOTH_RX.search(getattr(sdef, "description", "") or ""):
                return True
    return False


def _siege_behemoth_match(tree: ConceptTree) -> bool:
    return _siege_behemoth_gap(tree)


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
        Bridge(
            bridge_id="land_creatures_subtype_animate_dropped",
            key="land_creatures_matter",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a subtype-"
                "restricted (not core-type Land) mass land-animate "
                "grammar verb — 'Forests you control are 1/1 green Elf "
                "creatures that are still lands' parks wholesale as "
                "Unimplemented(name='unknown') — retires when the clause "
                "decomposes into a typed affected-filter (subtype Forest) "
                "+ AddType(Creature) static the existing mass-static-def "
                "arm already reads for CORE-type Land filters"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented top-level "
                "effects matching 'you control are ... creatures ... "
                "still lands', phase v0.20.0, 2026-07-12"
            ),
            pins=("Ambush Commander",),
            gap=_land_creatures_subtype_animate_gap,
            match=_land_creatures_subtype_animate_match,
        ),
        Bridge(
            bridge_id="land_creatures_dynamic_animate_dropped",
            key="land_creatures_matter",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a dynamic-value "
                "land-animate grammar verb (a deferred 'pay this cost N "
                "times, then up to that many lands become creatures' "
                "repeat-count chain, or an X/X formula embedded in a "
                "single-target animate) — both park wholesale as "
                "Unimplemented — retires when the clause decomposes into "
                "the existing typed Animate/AddType(Creature) reads"
            ),
            census=(
                "2 hits / 31,622 commander-legal, matched against each "
                "unit's own description ('land(s) ... become(s) ... "
                "creature(s)') paired with an Unimplemented residue "
                "anywhere in that same unit, phase v0.20.0, 2026-07-12"
            ),
            pins=("Primal Adversary", "Sage of the Maze"),
            gap=_land_creatures_dynamic_animate_gap,
            match=_land_creatures_dynamic_animate_match,
        ),
        Bridge(
            bridge_id="land_creatures_condition_reference_dropped",
            key="land_creatures_matter",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "condition parser fails a compound Or between a 'you "
                "control a land creature' state-check and a landfall "
                "self-state check, parking the WHOLE condition as "
                "Unrecognized — retires on a phase bump that structures "
                "the 'land creature' state-check half"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unrecognized condition "
                "nodes whose text mentions 'land creature', phase v0.20.0, "
                "2026-07-12"
            ),
            pins=("Earth Rumble Wrestlers",),
            gap=_land_creatures_condition_ref_gap,
            match=_land_creatures_condition_ref_match,
        ),
        Bridge(
            bridge_id="ramp_grant_unimplemented_body",
            key="ramp",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a granted-"
                "ability body parser verb for (1) the self-referential "
                "'any of ~'s colors' dynamic-color derivation (Katilda, "
                "Tazri) and (2) a compound TWO-quoted-granted-ability body "
                "joined by 'and' (Old-Growth Troll's 'Enchanted Forest has "
                '"..." and "..."\') — both park the WHOLE granted '
                "ability as Unimplemented; retires when the grant's "
                "definition.effect decomposes into a typed Mana node"
            ),
            census=(
                "3 hits / 31,622 commander-legal GrantAbility nodes whose "
                "definition.effect is Unimplemented and whose description "
                "mentions 'add ... mana/{X}', phase v0.20.0, 2026-07-12"
            ),
            pins=(
                "Katilda, Dawnhart Prime",
                "Old-Growth Troll",
                "Tazri, Stalwart Survivor",
            ),
            gap=_ramp_grant_unimplemented_gap,
            match=_ramp_grant_unimplemented_match,
        ),
        Bridge(
            bridge_id="ramp_dropped_add_mana_clause",
            key="ramp",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): THE headline "
                "grammar verb for this key — an 'add {mana-expression}' "
                "clause grammar that structures a dynamic/scaling count "
                "('add {R} for each...', 'add twice that much'), a "
                "restricted-spend or note-type rider ('spend this mana "
                "only to...', Ice Cauldron/Jeweled Amulet's 'note the type "
                "spent'), a die-roll/sticker value table, or a player-"
                "choice recipient into a typed Mana effect — retires "
                "PER-CARD as each idiom decomposes (the existing "
                "structural ramp arm already reads it once it does)"
            ),
            census=(
                "24 hits / 31,622 commander-legal, each name CR-verified "
                "this session as a genuine legacy ramp member via "
                "old_ir_for's independent category=='ramp' classification "
                "(17/24) or legacy's own kept-mirror pair "
                "(_RAMP_MATTERS_REGEX / _MANA_DORK_SUPPORT_MIRROR in "
                "_signals_ir.py, 7/24 — Megatron, Raggadragga, Braid of "
                "Fire, Plasm Capture, Tundra Fumarole, Chancellor of the "
                "Tangle, Squandered Resources); phase v0.20.0, 2026-07-12. "
                "A naive whole-card 'add ... mana' regex over-fires on "
                "reminder text describing a CREATED TOKEN's own ability "
                "(Deadly Derision / T'Challa's Treasure/Vibranium tokens — "
                "corpus-verified NOT legacy ramp members), so this row is "
                "a bounded name enumeration instead (CONTEXT.md's third "
                "residue class)."
            ),
            pins=(
                "Neheb, the Eternal",
                "Squandered Resources",
                "Rasputin, the Oneiromancer",
                '"Name Sticker" Goblin',
            ),
            gap=_ramp_dropped_clause_gap,
            match=_ramp_dropped_clause_match,
        ),
        Bridge(
            bridge_id="exile_grant_all_activated_abilities",
            key="exile_matters",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "static parser recognizes but fails to structure "
                "'~ has all activated abilities of all cards [you own] in "
                "exile with <kind> counters on them' — no GrantAbility/"
                "GrantStaticAbility node results — retires on a phase "
                "bump that parses this ability-suite-import idiom into a "
                "typed grant node"
            ),
            census=(
                "2 hits / 31,622 commander-legal static_structure "
                "Unimplemented residues matching the 'has all activated "
                "abilities ... in exile with ... counters' idiom, phase "
                "v0.20.0, 2026-07-12 (exactly the 2 pins — Mairsil, the "
                "Pretender and Rex, Cyber-Hound; Warden of the Beyond's "
                "superficially similar 'owns a card in exile' condition "
                "is a DIFFERENT idiom, already closed by the existing "
                "gap-marker text-fallback arm)"
            ),
            pins=("Mairsil, the Pretender", "Rex, Cyber-Hound"),
            gap=_mairsil_rex_gap,
            match=_mairsil_rex_match,
        ),
        Bridge(
            bridge_id="grolnok_cast_from_exile_counter_pile",
            key="exile_matters",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "effect parser recognizes but fails to structure 'You may "
                "play lands and cast spells from among cards you own in "
                "exile with <kind> counters on them' (no CastFromZone/"
                "MayPlayAdditionalLand permission node results) — retires "
                "on a phase bump that parses this dual land-play/cast "
                "permission into typed nodes"
            ),
            census=(
                "1 hit / 31,622 commander-legal effect_structure "
                "Unimplemented residues matching the 'play lands and cast "
                "spells from among cards you own in exile with ... "
                "counters' idiom, phase v0.20.0, 2026-07-12 (exactly the "
                "1 pin)"
            ),
            pins=("Grolnok, the Omnivore",),
            gap=_grolnok_gap,
            match=_grolnok_match,
        ),
        Bridge(
            bridge_id="candlekeep_inspiration_exile_gy_pt_setter",
            key="exile_matters",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "effect parser drops the WHOLE dynamic base-P/T-setter "
                "clause 'creatures you control have base power and "
                "toughness X/X, where X is the number of cards you own in "
                "exile and in your graveyard that are instant cards, are "
                "sorcery cards, and/or have an Adventure' as "
                "Unimplemented(name='creatures') — no SetDynamicPower/"
                "SetDynamicToughness pair anywhere — retires on a phase "
                "bump that structures this dual-zone dual-type-filter X "
                "count"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented(name="
                "'creatures') residues matching 'where x is the number of "
                "cards you own in exile', phase v0.20.0, 2026-07-12 "
                "(exactly the 1 pin)"
            ),
            pins=("Candlekeep Inspiration",),
            gap=_candlekeep_gap,
            match=_candlekeep_match,
        ),
        Bridge(
            bridge_id="close_encounter_warped_exile_additional_cost",
            key="exile_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "additional-cost clause 'choose a creature you control or "
                "a warped creature card you own in exile' is dropped with "
                "ZERO trace — unit.costs is empty and no Unimplemented "
                "residue carries the clause text either — retires on a "
                "phase bump that structures this additional-cost choice "
                "into unit.costs"
            ),
            census=(
                "1 hit / 31,622 commander-legal cards whose oracle text "
                "matches 'warped creature card you own in exile', phase "
                "v0.20.0, 2026-07-12 (exactly the 1 pin)"
            ),
            pins=("Close Encounter",),
            gap=_close_encounter_gap,
            match=_close_encounter_match,
        ),
        Bridge(
            bridge_id="kaya_emblem_cast_from_exile_drop",
            key="exile_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "granted trigger's own description names casting 'from "
                "your hand, from your graveyard, or from among cards you "
                "own in exile' but the granted CastFromZone's target "
                "filter carries ONLY the hand-zone branch — the "
                "graveyard/exile alternate-source clause is dropped from "
                "the target filter — retires on a phase bump that "
                "structures the full Or-zone target"
            ),
            census=(
                "1 hit / 31,622 commander-legal CreateEmblem triggers "
                "whose own description names 'in exile' paired with a "
                "CastFromZone target that doesn't reach the exile zone, "
                "phase v0.20.0, 2026-07-12 (exactly the 1 pin)"
            ),
            pins=("Kaya the Inexorable",),
            gap=_kaya_emblem_cast_from_exile_drop,
            match=_kaya_emblem_cast_from_exile_drop,
        ),
        Bridge(
            bridge_id="voltron_attach_count_scaling_dropped",
            key="voltron_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): an Aura/"
                "Equipment attachment-count scaling clause ('for each "
                "Aura/Equipment ... attached', 'where X is the number of "
                "Equipment you control') is dropped — the corresponding "
                "count/value node decomposes as a bare Fixed constant "
                "with no ObjectCount/Aggregate scoped to Equipment/Aura "
                "anywhere in the tree — retires on a phase bump that "
                "structures this scaling clause into a dynamic count "
                "operand"
            ),
            census=(
                "3 hits / 33 commander-legal cards matching the tight "
                "'for each Aura/Equipment ... attached' / 'where X is the "
                "number of Equipment you control' anchor AND unserved by "
                "every other voltron_matters arm (incl. the shared "
                "_apply_membership_floor creature-gated word tell), phase "
                "v0.20.0, 2026-07-12 — exactly the 3 pins (Judgment Bolt, "
                "Animal Friend, Sage's Reverie). NOTE: the legacy "
                "VOLTRON_PAYOFF_REGEX's bare 'equipment you control' "
                "branch is deliberately NOT reused here — it over-fires "
                "on Affinity-for-Equipment reminder text and imperative "
                "attach-ACTION clauses (Armed and Armored, Goldwardens' "
                "Gambit, Oxidda Finisher, Rebel Salvo, and 5 more of the "
                "existing attach-housekeeping shed class), all correctly "
                "excluded by this tighter anchor"
            ),
            pins=("Judgment Bolt", "Animal Friend", "Sage's Reverie"),
            gap=_voltron_scaling_gap,
            match=_voltron_scaling_match,
        ),
        Bridge(
            bridge_id="warchanter_skald_condition_dropped",
            key="voltron_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "Taps-mode trigger's 'if it's enchanted or equipped' "
                "condition clause is dropped — the trigger's own "
                "condition field decomposes as None, with the clause "
                "text surviving only in the trigger's whole-ability "
                "description — retires on a phase bump that structures "
                "this condition into a typed RequiresCondition/filter"
            ),
            census=(
                "1 hit / 31,622 commander-legal Taps-mode triggers with "
                "condition=None whose own description names 'enchanted "
                "or equipped', phase v0.20.0, 2026-07-12 (exactly the 1 "
                "pin)"
            ),
            pins=("Warchanter Skald",),
            gap=_warchanter_condition_gap,
            match=_warchanter_condition_match,
        ),
        Bridge(
            bridge_id="forge_anew_equip_cost_paycost_unlinked",
            key="voltron_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): 'pay {0} "
                "rather than pay the equip cost of the first equip "
                "ability you activate' parses as a bare unlinked PayCost "
                "node with no ReduceAbilityCost/equip-keyword tag tying "
                "it to the ability it modifies — retires on a phase bump "
                "that links the alternative payment to its equip-keyword "
                "target"
            ),
            census=(
                "2 hits / 31,622 commander-legal cards matching 'pay {0} "
                "rather than pay the equip cost' (Forge Anew, Bruenor "
                "Battlehammer), phase v0.20.0, 2026-07-12; Bruenor is "
                "already served through its OWN '+2/+0 for each "
                "Equipment attached to it' ObjectCount arm before this "
                "bridge is ever reached (the bridge_fires call sits at "
                "the end of the lane, after every structural arm) — "
                "exactly the 1 remaining pin"
            ),
            pins=("Forge Anew",),
            gap=_forge_anew_paycost_unlinked_gap,
            match=_forge_anew_match,
        ),
        Bridge(
            bridge_id="tpd_widened_tag_synthetic_desc",
            key="target_player_draws",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a modal-mode / "
                "attack-or-dies-triggered Draw's own unit never gets its "
                "mode's real English attributed to unit.node.description "
                "— only a synthetic trigger-condition label ('When ~ "
                "enters', 'Whenever ~ attacks') survives, so the EXISTING "
                "_TARGET_PLAYER_DRAW_PHRASE_RE gate can never see real "
                "text — retires when that attribution lands (the "
                "pre-existing arm then fires unmodified)"
            ),
            census=(
                "shared gap 9 hits / 31,622 commander-legal (Balor, Ertai "
                "Resurrected, Fall of the First Civilization, Fatal Lore, "
                "Love Song of Night and Day, Season of the Burrow, The "
                "Legend of Yangchen // Avatar Yangchen, Vault 11: Voter's "
                "Dilemma, Your Temple Is Under Attack), phase v0.20.0, "
                "2026-07-12; this bridge's own narrow match hits exactly "
                "the 4 pins (the other 5 gap hits are EITHER already "
                "closed by the pre-existing self-paired/Vote-branch "
                "admissions OR a genuine adjudicated shed — Vault 11: "
                "Voter's Dilemma, a GROUP All-scoped outcome — see "
                "_tpd_widened_tag_no_draw_text's own module comment)"
            ),
            pins=(
                "Fatal Lore",
                "Season of the Burrow",
                "Ertai Resurrected",
                "Balor",
            ),
            gap=_tpd_widened_tag_no_draw_text,
            match=_tpd_widened_tag_synthetic_desc_match,
        ),
        Bridge(
            bridge_id="tpd_wedding_ellipsis_repeat",
            key="target_player_draws",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): an ellipsis "
                "repeat-for-another-player construct ('Then target "
                "opponent does the same') — our OWN clause grammar "
                "already names the token "
                "(Unimplemented(name='target_opponent_does_the_same')) "
                "but recovery.py's ALLOWLIST has no concept mapping for "
                "it yet — retires when that mapping lands"
            ),
            census=("1 hit / 31,622 commander-legal, phase v0.20.0, 2026-07-12"),
            pins=("The Wedding of River Song",),
            gap=_tpd_wedding_ellipsis_repeat_gap,
            match=_tpd_wedding_ellipsis_repeat_match,
        ),
        Bridge(
            bridge_id="opp_discard_unless_clause",
            key="opponent_discard",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "trigger/ability parser's 'unless' clause handling fails "
                "a discard-payoff 'target player/opponent ... discards "
                "... unless ...' body, parking it as an "
                "Unimplemented('Unsupported unless clause') residue — "
                "SHARED with lifeloss_makers' withercrown_unless_lose_"
                "life bridge, the sprint's shared-row candidate for the "
                "unless-clause recovery ALLOWLIST row — retires on a "
                "phase bump or a recovery-stage unless-clause row that "
                "structures the discard/life-loss payoff (CR 119.4-"
                "shaped unless-cost)"
            ),
            census=(
                "2 hits / 31,622 commander-legal 'Unsupported unless "
                "clause' residues matching this discard-direction "
                "anchor, phase v0.20.0, 2026-07-12; Wand of Ith carries "
                "the SAME residue class but is served INDEPENDENTLY via "
                "its own typed DiscardCard(ParentTarget) elsewhere in "
                "the tree — never reaches this bridge's gap"
            ),
            pins=("Tainted Specter", "Remorseless Punishment"),
            gap=_opp_discard_unless_gap,
            match=_opp_discard_unless_match,
        ),
        Bridge(
            bridge_id="opp_discard_for_scaling_dominant_token",
            key="opponent_discard",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a 'for each "
                "<mana> spent to cast it, <effect>' scaling prefix (CR "
                "601.2f) is the DOMINANT recovered token ('for'), never "
                "the inner clause's own verb ('discard') — needs a "
                "scaling-prefix-peel so the wrapped clause's own verb "
                "decorates instead — retires when that peel lands"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented('for') "
                "residues ending in the exact discard payoff, phase "
                "v0.20.0, 2026-07-12 (Hollow Marauder's superficially "
                "similar 'for each ... discard' residue is a DIFFERENT, "
                "unrelated draw payoff — correctly excluded by the "
                "end-of-clause anchor)"
            ),
            pins=("Bladecoil Serpent",),
            gap=_opp_discard_for_scaling_gap,
            match=_opp_discard_for_scaling_match,
        ),
        Bridge(
            bridge_id="opp_discard_tk_sticker_parse_failure",
            key="opponent_discard",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a {TK} "
                "Unfinity Stickers placeholder-costed ability (CR 123.1) "
                "parks WHOLESALE as Unimplemented('unknown') — the SAME "
                "frontier base_pt_set's base_pt_tk_sticker_parse_failure "
                "bridge (Cool Fluffy Loxodon) closes — retires on a "
                "phase bump that parses {TK}-costed abilities"
            ),
            census=("1 hit / 31,622 commander-legal, phase v0.20.0, 2026-07-12"),
            pins=("Yawgmoth Merfolk Soul",),
            gap=_yawgmoth_tk_discard_gap,
            match=_yawgmoth_tk_discard_match,
        ),
        Bridge(
            bridge_id="opp_discard_words_of_waste_replacement_the_residue",
            key="opponent_discard",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a REPLACEMENT-"
                "idiom 'the next time ... instead' clause (CR 614.1) has "
                "no imperative verb to peel, so the dominant-token "
                "detector falls back to the sentence's leading determiner "
                "('the') instead of any concept-bearing token — needs a "
                "next-time-instead replacement-grammar rule that reads "
                "past the determiner into the replaced effect's own verb "
                "— retires when that rule lands"
            ),
            census=("1 hit / 31,622 commander-legal, phase v0.20.0, 2026-07-12"),
            pins=("Words of Waste",),
            gap=_words_of_waste_gap,
            match=_words_of_waste_match,
        ),
        Bridge(
            bridge_id="opp_discard_fungal_shambler_dropped_conjunct",
            key="opponent_discard",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "SECOND conjunct of a 'you draw a card and that opponent "
                "discards a card' compound trigger effect drops WHOLESALE "
                "with zero residue (not even an Unimplemented node) — "
                "retires on a phase bump that structures the second "
                "conjunct"
            ),
            census=(
                "1 hit / 31,622 commander-legal (the shared no-typed-"
                "Discard-node gap is broad; this bridge's own narrow "
                "match is the scalpel), phase v0.20.0, 2026-07-12"
            ),
            pins=("Fungal Shambler",),
            gap=_no_typed_discard_node,
            match=_fungal_shambler_match,
        ),
        Bridge(
            bridge_id="opp_discard_mindculling_dropped_conjunct",
            key="opponent_discard",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "SECOND conjunct of a 'you draw N cards and target "
                "opponent discards N cards' compound sorcery effect drops "
                "WHOLESALE with zero residue — retires on a phase bump "
                "that structures the second conjunct"
            ),
            census=(
                "1 hit / 31,622 commander-legal (SAME shared no-typed-"
                "Discard-node gap as the Fungal Shambler bridge above, a "
                "DIFFERENT card-class — sorcery vs. creature trigger), "
                "phase v0.20.0, 2026-07-12"
            ),
            pins=("Mindculling",),
            gap=_no_typed_discard_node,
            match=_mindculling_match,
        ),
        Bridge(
            bridge_id="opp_discard_driven_despair_missing_face",
            key="opponent_discard",
            kind="missing_face",
            todo=(
                "retires when phase (or a W2c text-only-tree successor) "
                "gains a real structural parse for an Aftermath back-"
                "half's GRANTED-ability quoted text — the existing W2c "
                "text-only tree already supplies the raw oracle for this "
                "bridge to read, but a genuine typed read of the "
                "granted trigger itself is the eventual retirement path"
            ),
            census=(
                "1 hit / 31,622 commander-legal zero-unit text-only "
                "trees matching this back-reference-shaped anchor, phase "
                "v0.20.0, 2026-07-12 (Consign // Oblivion's own zero-unit "
                "Oblivion face is already served by the pre-existing "
                "_TEXT_ONLY_OPP_DISCARD_RX sweep, disjoint from this "
                "anchor)"
            ),
            pins=("Driven // Despair",),
            gap=_driven_despair_gap,
            match=_driven_despair_match,
        ),
        Bridge(
            bridge_id="opp_discard_jagged_poppet_combat_scaling",
            key="opponent_discard",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): a "
                "combat-damage-to-a-player trigger's own bare 'Player' "
                "valid_target COULD directionally resolve an unresolved "
                "discard as opponent-directed (combat damage from your "
                "own creature reaches an opponent by the rules of the "
                "game, CR 510) — but a general Player-vs-Opponent "
                "owner-scope widening for opponent_discard's fallback "
                "chain risks over-firing genuinely symmetric multiplayer "
                "group-hug triggers; the sprint should scope that "
                "widening lane-locally to combat-damage triggers only — "
                "retires on that lane-local widening or a phase bump"
            ),
            census=(
                "1 hit / 31,622 commander-legal Unimplemented('discard') "
                "residues matching this exact damage-scaling idiom, "
                "phase v0.20.0, 2026-07-12"
            ),
            pins=("Jagged Poppet",),
            gap=_jagged_poppet_gap,
            match=_jagged_poppet_match,
        ),
        Bridge(
            bridge_id="plus_one_rock_hydra_static_parse_failure",
            key="plus_one_matters",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "static/replacement parser fails the whole "
                "'if it has a +1/+1 counter on it, remove a +1/+1 "
                "counter ... and prevent that damage' line — retires on "
                "a phase bump that structures this damage-prevention "
                "replacement's self-condition into a typed "
                "HasCounters/QuantityCheck node the existing condition-"
                "site arms already read"
            ),
            census=(
                "1 hit / 31,622 commander-legal static_structure "
                "residues matching 'if it has a +1/+1 counter on it', "
                "phase v0.20.0, 2026-07-12 (exactly the 1 pin)"
            ),
            pins=("Rock Hydra",),
            gap=_rock_hydra_gap,
            match=_rock_hydra_match,
        ),
        Bridge(
            bridge_id="plus_one_hierophant_previouseffectamount_dropped_kind",
            key="plus_one_matters",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "ModifyCost static's dynamic_count=PreviousEffectAmount "
                "scaler (a cost reduction keyed to however much a PRIOR "
                "effect did) carries no counter-kind field at all — "
                "phase's own encoding of 'the preceding effect's amount' "
                "has nowhere to put which counter kind that preceding "
                "effect removed — retires on a phase bump that threads "
                "the kind through PreviousEffectAmount"
            ),
            census=(
                "1 hit / 31,622 commander-legal static ModifyCost nodes "
                "with dynamic_count=PreviousEffectAmount corpus-wide "
                "(not just the +1/+1-mentioning subset — the shape "
                "itself is this rare), phase v0.20.0, 2026-07-12 "
                "(exactly the 1 pin)"
            ),
            pins=("Hierophant Bio-Titan",),
            gap=_hierophant_gap,
            match=_hierophant_match,
        ),
        Bridge(
            bridge_id="named_synergy_overloaded_named_node",
            key="named_synergy",
            kind="upstream_parse_failure",
            todo=(
                "dedicated Named-context classifier (not the post-"
                "deletion grammar sprint — this is a crosswalk-side "
                "disambiguation project, not a phase grammar gap): "
                "narrow the typed Named-node deep walk to exclude "
                "partner-pair references (CR 716.3), planeswalker-"
                "uncoupled 'Path of the X' callbacks, copy-limit swarms "
                "(CR 100.2a — the copy_limit sibling's own territory), "
                "and named-card library tutoring, keeping only the "
                "permanent-synergy self/other-name reference this lane "
                "serves — retires (for the cards it then covers) once "
                "that classifier lands and the lane switches to reading "
                "it structurally"
            ),
            census=(
                "27 hits / 31,622 commander-legal (byte-identical to the "
                "deleted NAMED_PERMANENT_REGEX SWEEP producer, flat over "
                "the reminder-stripped per-face oracle — unchanged from "
                "the legacy population); 245 commander-legal cards carry "
                "a Named node ANYWHERE (an ~9x blast radius past the ~2x "
                "tighten bar, corpus-verified), so the bridge stays "
                "idiom-bounded by regex rather than reading the raw node, "
                "phase v0.20.0, 2026-07-12"
            ),
            pins=("Brothers Yamazaki", "Mishra, Claimed by Gix", "Sheltered Valley"),
            gap=_named_synergy_gap,
            match=_named_synergy_match,
        ),
        Bridge(
            bridge_id="lightning_runner_untap_all_dropped",
            key="creatures_matter",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "pay-{E} sub-ability chain structures GainEnergy/"
                "PayEnergy/AdditionalPhase but drops the sandwiched "
                "'untap all creatures you control' clause with ZERO "
                "trace (no SetTapState node anywhere) — retires on a "
                "phase bump that structures the untap clause"
            ),
            census=(
                "1 hit / 105,561 commander-legal (Lightning Runner, "
                "anchored to its full surrounding sentence, not the bare "
                "'untap all creatures you control' substring — that "
                "alone hits 32 commander-legal cards, every other one "
                "already structurally read via "
                "_mass_untap_creature_filter's own SetTapState walk, so "
                "the shared no-SetTapState gap stands every one of them "
                "down on its own), phase v0.20.0, 2026-07-12"
            ),
            pins=("Lightning Runner",),
            gap=_lightning_runner_gap,
            match=_lightning_runner_match,
        ),
        Bridge(
            bridge_id="duskana_draw_per_base_pt_creature_dropped",
            key="creatures_matter",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the ETB "
                "Draw node's own count collapses to a bare Fixed(1) "
                "instead of a Ref(qty=ObjectCount(base-power-2/2 "
                "filter)) — the dynamic count is dropped with no residue "
                "at all — retires on a phase bump that structures the "
                "per-base-2/2-creature count. Distinct from the RETIRED "
                "duskana_bess_base_pt_and_toughness_ref bridge "
                "(base_power_matters key, graduated to a tree_synthesis.py "
                "arm this session) — that one served the SECOND ability's "
                "base-power-2/2 REFERENCE; this one serves the FIRST "
                "ability's dropped COUNT, kept as a separate row per the "
                "ledger's one-key-per-row contract"
            ),
            census=(
                "1 hit / 105,561 commander-legal (Duskana, the Rage "
                "Mother), phase v0.20.0, 2026-07-12"
            ),
            pins=("Duskana, the Rage Mother",),
            gap=_duskana_draw_count_gap,
            match=_duskana_draw_count_match,
        ),
        Bridge(
            bridge_id="moku_haste_grant_misscoped_selfref",
            key="creatures_matter",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): a "
                "static def folds 'Moku gets +2/+1 AND creatures you "
                "control gain haste' into ONE affected=SelfRef def whose "
                "OWN modifications list also carries the team "
                "AddKeyword('Haste') — the grant is mis-scoped to the "
                "wrong affected population, not dropped outright (the "
                "def's own description still names it) — retires on a "
                "phase bump that splits the conjunctive grant into its "
                "own team-scoped def"
            ),
            census=(
                "1 hit / 105,561 commander-legal (Moku, Meandering "
                "Drummer), phase v0.20.0, 2026-07-12"
            ),
            pins=("Moku, Meandering Drummer",),
            gap=_moku_haste_grant_gap,
            match=_moku_haste_grant_match,
        ),
        Bridge(
            bridge_id="siege_behemoth_unblocked_assign_empty_mods",
            key="creatures_matter",
            kind="dropped_clause",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "static def for 'for each creature you control, you may "
                "have that creature assign combat damage as though "
                "unblocked' parses with affected=SelfRef, an "
                "Unrecognized condition text, and an EMPTY modifications "
                "list — the whole per-creature grant survives only in "
                "the def's own description — retires on a phase bump "
                "that types the per-creature permission as a real mode "
                "or modification"
            ),
            census=(
                "1 hit / 105,561 commander-legal (Siege Behemoth), "
                "phase v0.20.0, 2026-07-12"
            ),
            pins=("Siege Behemoth",),
            gap=_siege_behemoth_gap,
            match=_siege_behemoth_match,
        ),
    )
}


def bridge_fires(bridge_id: str, tree: ConceptTree) -> bool:
    """Whether the registered bridge fires for this tree (gap AND match)."""
    return BRIDGES[bridge_id].fires(tree)
