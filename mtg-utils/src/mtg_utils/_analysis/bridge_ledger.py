"""Ledgered bridges (ADR-0039) — the sanctioned straggler-serving mechanism.

A **ledgered bridge** is a gap-gated, corpus-bounded, self-retiring text read
that serves a signal lane where the typed substrate genuinely cannot yet: a
grammar straggler, a dropped clause, a missing face, or an upstream parse
failure. Bridges exist so the legacy-IR deletion (ADR-0039 / task #80) never
drops a legacy-served member — each bridge keeps its laggard cards served
until the post-deletion grammar sprint (task #82) or a phase bump lands the
real structure.

Every bridge is REGISTERED here, never written inline in a lane — and since
ADR-0048 the row also OWNS its emission (``key`` + ``scope``): the one
``bridge_signals`` lane fires every row, so no lane names a bridge id and
retiring a bridge is deleting its row (``tests/mtg-utils/test_bridge_ledger.py``
forbids a bridge id literal anywhere under ``lanes/``). A row carries:

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

Bridges restore prior serving only — the serving the legacy IR gave (the
ADR-0039 deletion's laggards) or the serving an upstream phase regression
took away (a bump's parse failure, bridged until the next bump restores it).
Beyond-prior breadth is the typed substrate's job. A bridge that "could also"
open a sibling lane records that as a note for the grammar sprint instead of
widening its own read.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis._sweep_detectors import NAMED_PERMANENT_REGEX
from mtg_utils._analysis.signal_base import Signal
from mtg_utils._card_ir.crosswalk import (
    ARTIFACT_TOKEN_SUBTYPES,
    DAMAGE_EFFECT_TAGS,
    _filter_type_words,
    aggregate_filter,
    damage_recipient,
    effect_filter,
    effect_owner_player_scope,
    effect_reaches_player,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    iter_cost_leaves,
    iter_typed_nodes,
    static_mode_field,
    tag_of,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.mirror.runtime import MISSING

if TYPE_CHECKING:  # pragma: no cover
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree


# The four residue classes a bridge may serve (mtg-utils/CONTEXT.md):
# a grammar straggler (our clause grammar's frontier), a dropped clause
# (phase emits nothing for the clause), a missing face (W2c text-only tree),
# an upstream parse failure (phase tried and failed — the line preserved in an
# ``Unimplemented`` residue or in a hollow static def's ``description``, or
# emitted as a WRONG typed node: a misparse). ``test_bridge_ledger`` checks
# each row's kind against its pins' evidence where the kind is checkable.
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
    # The emission the row serves (ADR-0048): the ledger — not a lane — emits
    # ``Signal(key, scope, "", text, card, "high")`` when the bridge fires, so a
    # bridge is ONE row and retiring it is deleting that row.
    scope: str = "you"  # "you" | "opponents" | "each" | "any"
    quote_oracle: bool = False  # carry the card's oracle text as Signal.text

    def fires(self, tree: ConceptTree) -> bool:
        """Gap-gated firing — a landed structural read stands the bridge down."""
        return self.gap(tree) and self.match(tree)

    def signal(self, tree: ConceptTree) -> Signal:
        """The signal this row serves for ``tree`` (call only when it fires)."""
        text = (tree.oracle or "") if self.quote_oracle else ""
        return Signal(self.key, self.scope, "", text, tree.name, "high")


def _static_parse_failure_descs(tree: ConceptTree) -> Iterator[str]:
    """Descriptions of phase's ``static_structure`` parse-failure residues.

    Phase's static parser, on a line it recognizes but cannot structure,
    parks the WHOLE line as ``Unimplemented(name='static_structure')`` with a
    "Static pattern matched but line failed static parser: <line>" diagnostic
    (116 nodes corpus-wide at v0.20.0). The line text survives only there, so
    an upstream_parse_failure bridge both gap-checks and reads that node.
    """
    return tree.residues("static_structure")


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


def _says(rx: re.Pattern[str], texts: Iterable[str]) -> bool:
    """Whether any of ``texts`` — the residue / hollow-static descriptions a
    presence read returned — says ``rx``. The shape every text bridge's gap and
    match share: the gap asks it of the residue carrying the row's own clause,
    the match of the text that residue preserves."""
    return any(rx.search(t) for t in texts)


def _degavolver_gap(tree: ConceptTree) -> bool:
    return all(tag_of(n) not in ("PayLife", "GrantAbility") for n in tree.iter_typed())


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
    return tree.residues("Unsupported unless clause")


def _withercrown_gap(tree: ConceptTree) -> bool:
    # Keyed on the residue carrying THIS clause (CONTEXT.md "Gap predicate"), so a
    # phase fix to it reads RETIRE-READY even if another unless-clause stays parked.
    return _says(_WITHERCROWN_RX, _unless_clause_failure_descs(tree))


def _withercrown_match(tree: ConceptTree) -> bool:
    return _says(_WITHERCROWN_RX, _unless_clause_failure_descs(tree))


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


def _night_shift_gap(tree: ConceptTree) -> bool:
    # The residue carrying THIS clause, over the ``residues`` presence read.
    return _says(_NIGHT_SHIFT_RX, tree.residues())


def _night_shift_match(tree: ConceptTree) -> bool:
    return _says(_NIGHT_SHIFT_RX, tree.effect_residues())


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
    return all(tag_of(n) not in ("PayLife", "LoseLife") for n in tree.iter_typed())


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
    return all(tag_of(n) not in ("PayLife", "GrantAbility") for n in tree.iter_typed())


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
# gating exactly). CR 701.21a throughout.
_REMINDER_RX = re.compile(r"\([^)]*\)")


def _no_typed_sacrifice_node(tree: ConceptTree) -> bool:
    """The shared gap for every ``sacrifice_outlets`` bridge below: no
    ``Sacrifice``-tagged node reachable anywhere in the tree. Self-retiring
    by construction — the day phase decomposes any of these idioms into a
    typed Sacrifice cost/effect node, every bridge below stands down on
    that card without any further edit."""
    return not any(tag_of(n) == "Sacrifice" for n in tree.iter_typed())


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
# read (:data:`~mtg_utils._analysis.lanes._SWEEP_KEYWORD_LANES`)
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
# is "you", mirroring :func:`~mtg_utils._analysis.lanes.
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
# Three bridges close the LAST 20 of the key's residual live_only set (40 at
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
    for n in tree.iter_typed():
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
                if subs and not subs & LAND_SUBTYPES:
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
                if subs and not subs & LAND_SUBTYPES:
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


# (5) Ao, the Dawn Sky's own MODAL parser diagnostic, named exactly
# ``modal_mode_unsupported_qualifier`` (phase's modal grammar can't
# structure a "total mana value N or less" qualifier on a "put any number
# of nonland permanent cards... onto the battlefield" mode) — anchored to
# that literal diagnostic name, corpus-verified sole hit.
def _cheat_modal_unsupported_gap(tree: ConceptTree) -> bool:
    return any(
        True
        for n in tree.iter_typed()
        if tag_of(n) == "Unimplemented"
        and getattr(n, "name", None) == "modal_mode_unsupported_qualifier"
    )


def _cheat_modal_unsupported_match(tree: ConceptTree) -> bool:
    for n in tree.iter_typed():
        if tag_of(n) != "Unimplemented":
            continue
        if getattr(n, "name", None) != "modal_mode_unsupported_qualifier":
            continue
        desc = (getattr(n, "description", "") or "").lower()
        if "onto the battlefield" in desc:
            return True
    return False


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
    for unit in tree.iter_units():
        for n in unit.iter_typed():
            if tag_of(n) in DAMAGE_EFFECT_TAGS and effect_reaches_player(n, unit.node):
                return False
    return True


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
# Four bridges close the final base_pt_set stragglers left after three
# structural closers (a ``LastCreated`` resolved-tag accept, an
# empty-nested-description unit-level fallback, and a modal
# ``mode_abilities`` threaded-target walk — see
# :func:`~mtg_utils._analysis.lanes._base_pt_set` and
# :func:`~mtg_utils._analysis.lanes.
# _iter_base_pt_modal_threaded_statics`). Each census below is corpus-bound
# to EXACTLY its enumerated pins (re-verified 2026-07-11, phase v0.20.0,
# 31,622 commander-legal cards) — no blast-radius slop.
def _unimplemented_descs_anywhere(tree: ConceptTree) -> Iterator[str]:
    """Every ``Unimplemented`` node's description reachable ANYWHERE in the
    tree (unlike :meth:`ConceptTree.effect_residues`, this is NOT scoped to
    ``unit.effects`` — a base_pt_set residue can be nested under a STATIC
    unit or a granted-ability chain, outside ``apply_unimplemented_
    recovery``'s scan scope, per the mtg-utils/CONTEXT.md landmine)."""
    for n in tree.iter_typed():
        if tag_of(n) == "Unimplemented":
            yield getattr(n, "description", "") or ""


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
    return _says(_BASE_PT_TK_ANIMATE_RX, _unimplemented_descs_anywhere(tree))


# (5) RETIRED at the v0.86.0 pin bump: the DYNAMIC "base power and toughness each
# equal to <mana value | X>" scalar (CR 613.4b) now decomposes into the typed
# ``SetPowerDynamic``/``SetToughnessDynamic`` pair (Fractalize is served by the main
# lane's dynamic-pair arm). Captain Rex Nebula regressed differently: v0.86.0 parks
# its WHOLE "Crash Land — Whenever ~ deals damage …" trigger as an
# ``unrecognized_clause_head`` residue whose description is truncated to the
# trigger head — the hook text is not on the tree at all, so no residue-backed
# bridge can serve it. Logged as a lost card, not bridged
# (``base_pt_each_equal_to_dropped``, 2026-07-11 → 2026-09-17).


# (7) A ``BecomeCopy`` "except it's N/N" fixed P/T override with NO
# ``additional_modifications`` field AT ALL (Mindlink Mech's "becomes a
# copy of target nonlegendary creature ..., except it's 4/3, ..." — CR
# 707.2/707.9) — ZERO trace anywhere in the tree for the override, same
# absence-proof shape as the Degavolver/Zuko/keyword-dropped bridges above.
# The standard clone-SHELL idiom ("becomes a copy of X, except it's 0/0
# and has this ability" — Mimeoplasm, Revered One) shares the identical
# missing-additional_modifications gap but is corpus-verified NOT a legacy
# base_pt_set member (the deleted legacy IR engine returned False for it) — the
# ``(?!0/0\b)`` negative lookahead excludes that shell idiom by construction
# rather than re-deriving legacy's own clone-shell carve-out. Census:
# 2/31,622 commander-legal pattern-matched before the 0/0 exclusion, 1 after
# (exactly the 1 pin).
_BASE_PT_BECOMECOPY_PT_RX = re.compile(
    r"becomes a copy of[^.]*except it'?s (?!0/0\b)\d+/\d+", re.IGNORECASE
)


def _base_pt_becomecopy_no_mods_gap(tree: ConceptTree) -> bool:
    for n in tree.iter_typed():
        if tag_of(n) != "BecomeCopy":
            continue
        addl = getattr(n, "additional_modifications", MISSING)
        if addl is MISSING or addl in (None, []):
            return True
    return False


def _base_pt_becomecopy_no_mods_match(tree: ConceptTree) -> bool:
    return bool(_BASE_PT_BECOMECOPY_PT_RX.search(tree.oracle))


# ── phase v0.66.0 pin bump: the fail-closed ``unbound_subject`` residue ─────
# phase v0.46.0 (#7003, "stop failing open on an unparseable subject") parks
# any clause whose SUBJECT it can't bind as ``Unimplemented(name=
# "unbound_subject")`` with the clause as its description — 183 corpus
# residues at v0.66.0, zero at v0.45.0. Two deck-relevant sub-idioms lost
# their typed node in the flip and are bridged here; the third ("you and X
# each draw") rides card_advantage's recovered-residue read instead.
def _unbound_subject_descs(tree: ConceptTree) -> Iterator[str]:
    """Every ``unbound_subject`` residue's description, ANYWHERE under a
    unit (a planeswalker emblem's granted trigger nests its residue under
    ``CreateEmblem.triggers``, outside the flat ``unit.effects`` walk)."""
    for n in tree.iter_typed():
        if tag_of(n) == "Unimplemented" and (
            getattr(n, "name", None) == "unbound_subject"
        ):
            yield getattr(n, "description", "") or ""


# (a) "the player who/with <superlative> gains control of ~" → donate_makers.
# Ghazbán Ogre / Wild Dogs ("the player with the most life"), Loxodon
# Peacekeeper ("the lowest life total"), Sokenzan Renegade ("the most cards
# in hand"), Thoughtbound Primoc ("controls the most Wizards"), Wild Mammoth
# ("controls the most creatures") — a ``GiveControl{target: SelfRef,
# recipient: Any}`` through v0.45.0, now the residue. The card hands
# ITSELF to whichever player wins the comparison (CR 110.2 — a permanent's
# controller changes only by an effect; the give-away direction is the
# whole point of the card), the same give-away ``_donate_makers`` reads off
# a typed ``GiveControl`` recipient. Anchored to the residue's OWN clause:
# a leading "the player who/with …" superlative subject AND a trailing
# "gains control of ~" self-object — the "'s controller gains control"
# REVENGE idiom the lane excludes never has this subject shape.
_DONATE_SUPERLATIVE_RX = re.compile(
    r"^the player (?:who|with|that) [^.]*\bgains control of ~$", re.IGNORECASE
)
_CONTROL_CHANGE_TAGS = frozenset(
    {"GiveControl", "GainControl", "GainControlAll", "ExchangeControl"}
)


def _no_control_change_node(tree: ConceptTree) -> bool:
    return not any(tag_of(n) in _CONTROL_CHANGE_TAGS for n in tree.iter_typed())


def _donate_superlative_match(tree: ConceptTree) -> bool:
    return _says(_DONATE_SUPERLATIVE_RX, _unbound_subject_descs(tree))


# RETIRED at the v0.86.0 pin bump: phase binds "this emblem" as the damage source
# inside a ``CreateEmblem`` granted trigger again (phase-rs/phase#8169), so the
# ``unbound_subject`` residue is gone and the direct_damage lane serves Chandra,
# Spark Hunter / Koth / Narset structurally (``emblem_self_reference_damage_
# unbound_subject``, 2026-08-29 → 2026-09-17). Chandra, Awakened Inferno's
# opponent-owned "this emblem deals 1 damage to you" emblem is the one member the
# lane does not read (the recipient is the emblem's own controller — the opponent
# — which the player-reaching read files as self-damage); logged, not bridged.


# ── phase v0.66.0 pin bump: the "each <source> … deals damage equal to its
# power" rider ───────────────────────────────────────────────────────────────
# v0.53.0 (#7322, "resolve per-source power in each-X-deals-damage clauses")
# fails the per-source rider CLOSED as ``Unimplemented(name="each_source_
# unrepresentable_rider")``: Master of the Wild Hunt's "Each Wolf tapped this
# way deals damage equal to its power to target creature" was a typed
# ``DealDamage{amount: Ref(Power, Anaphoric), target: Typed(Creature)}`` at
# v0.45.0 (the one commander-legal member; Season's Beatings is not legal).
# The clause is single-target creature burn scaled on each source's own
# power (CR 120.3 — damage dealt to a creature by a creature source; the
# ``creature_ping`` doer shape) — served for both keys off the residue's own
# text, gated on there being NO typed creature-reaching damage node left.
_EACH_SOURCE_RIDER_RX = re.compile(
    r"\bdeals damage equal to its power to (?:target|another target|each) creature\b",
    re.IGNORECASE,
)


def _each_source_rider_descs(tree: ConceptTree) -> Iterator[str]:
    for n in tree.iter_typed():
        if tag_of(n) == "Unimplemented" and (
            getattr(n, "name", None) == "each_source_unrepresentable_rider"
        ):
            yield getattr(n, "description", "") or ""


def _no_creature_reaching_damage_node(tree: ConceptTree) -> bool:
    for n in tree.iter_typed():
        if tag_of(n) in DAMAGE_EFFECT_TAGS and "Creature" in (
            filter_core_types(damage_recipient(n))
        ):
            return False
    return True


def _each_source_rider_match(tree: ConceptTree) -> bool:
    return _says(_EACH_SOURCE_RIDER_RX, _each_source_rider_descs(tree))


# ── The scaling/restricted/note-type "Add mana" residue class → ramp ────────
# NARROWED (ADR-0039 task #82): 22 of the former 24-name enumeration
# graduated into ``tree_synthesis._arm_ramp_dropped_add_mana_clause`` — a
# per-NODE regex over each ``Unimplemented`` node's OWN ``description``
# (never the whole-card oracle), which structurally cannot hit a created
# TOKEN's reminder-text ability (a ``Token`` effect node carries no
# oracle-echoing ``description`` field at all — Deadly Derision / T'Challa's
# Treasure/Vibranium tokens corpus-verified this session to never produce a
# matching node), closing the over-fire the old whole-card-regex plan
# would have hit WITHOUT needing the name enumeration as the safety rail.
#
# NARROWED again (task #87): Braid of Fire GRADUATED off this row.
# ``crosswalk.build_concept_tree`` now carries a dedicated ``"keyword"``
# ``AbilityUnit`` origin (:func:`mtg_utils._card_ir.crosswalk.
# _keyword_effect_units`) that walks ``root.keywords`` for an
# ``EffectCost``-tagged variant (Cumulative Upkeep's own effect payload) and
# decorates its ``effect`` field the same way any other origin's effect
# chain is decorated — Braid of Fire's "Add {R}" is now a real
# ``effect_concepts("ramp")`` hit, read by this lane's FIRST branch
# (``crosswalk_signals._ramp``) with no bridge involved. Corpus-swept: the
# v0.23.0 EffectCost-keyword census is exactly 9 commander-legal cards (all
# ``CumulativeUpkeep``) — Aboroth, Braid of Fire, Herald of Leshrac,
# Infernal Darkness, Jötun Grunt, Karplusan Minotaur, Psychic Vortex,
# Sheltering Ancient, Varchild's War-Riders; only Braid of Fire's own
# ``Mana`` effect tag maps to a ported concept (``ramp``) — the rest
# surface as ``other`` and open no membership by construction (a silent,
# correct no-op, not a suppressed match), except two SECONDARY genuine
# gains the new origin's general per-unit reads independently produce
# (adjudicated, not this row's concern): Jötun Grunt's
# ``PutAtLibraryPosition`` target (an unowned "single graveyard" filter)
# now reaches ``_graveyard_matters``'s per-effect InZone-Graveyard arm,
# correctly defaulting to scope "you" (CR 400.7 — the SAME no-owner-field
# default the lane already applies to every other effect shape); Varchild's
# War-Riders' ``Token`` effect (a genuine creature-token maker) now reaches
# ``_type_matters_go_wide``'s token-maker arm (ii), opening its own
# ``Warrior`` CLASS_TRIBE at low confidence — the same reconciliation
# Kalitas/Daxos already get, working for the first time on a card the
# substrate gap previously hid entirely.
#
# The 1 name left is genuinely un-synthesizable by ANY current arm:
# Raggadragga, Goreguts Boss is a mana-ability-HAVER support card (creatures
# WITH a mana ability get +2/+2 and untap on attack) — legacy's own
# ``_MANA_DORK_SUPPORT_MIRROR`` classification, not an add-mana clause at
# all; phase parks BOTH its abilities as a structure-parser failure with no
# "add ... mana" text anywhere (its filter predicate "with a mana ability"
# is the real, deeper grammar gap — a matters-lane idiom bundled into this
# row's enumeration, not this row's own residue class, and not a
# keywords-field idiom either — its ``keywords`` list is empty). Stays a
# name-keyed bridge until its OWN grammar gap closes.
_RAMP_DROPPED_NAMES: frozenset[str] = frozenset(
    {
        "Raggadragga, Goreguts Boss",
    }
)


def _ramp_dropped_clause_gap(tree: ConceptTree) -> bool:
    return not tree.is_type("Land") and not tree.effect_concepts("ramp")


def _ramp_dropped_clause_match(tree: ConceptTree) -> bool:
    return tree.name in _RAMP_DROPPED_NAMES


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
    for n in tree.iter_typed():
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
    # The static_structure residue carrying THIS clause, not any static failure.
    return _says(_MAIRSIL_REX_RX, _static_parse_failure_descs(tree))


def _mairsil_rex_match(tree: ConceptTree) -> bool:
    return _says(_MAIRSIL_REX_RX, _static_parse_failure_descs(tree))


# (2) Grolnok, the Omnivore — "You may play lands and cast spells from among
# cards you own in exile with croak counters on them" (CR 305.1 land-play
# permission / CR 601.3 cast permission). A DIFFERENT phase diagnostic name
# than (1) — ``Unimplemented(name='effect_structure')`` ("Effect sentence
# candidate but line failed effect parser") — so a separate gap/match pair,
# even though the surface idiom (a counter-gated persistent exile pile as a
# play/cast resource) is a sibling of (1)'s ability-grant idiom.
def _effect_structure_descs(tree: ConceptTree) -> Iterator[str]:
    return tree.residues("effect_structure")


_GROLNOK_RX = re.compile(
    r"play lands and cast spells from among cards you own in exile with"
    r" [^.]* counters? on (?:it|them)",
    re.IGNORECASE,
)


def _grolnok_gap(tree: ConceptTree) -> bool:
    # The effect_structure residue carrying THIS clause, not any effect failure.
    return _says(_GROLNOK_RX, _effect_structure_descs(tree))


def _grolnok_match(tree: ConceptTree) -> bool:
    return _says(_GROLNOK_RX, _effect_structure_descs(tree))


# (3) Candlekeep Inspiration — "Until end of turn, creatures you control
# have base power and toughness X/X, where X is the number of cards you own
# in exile and in your graveyard that are instant cards, are sorcery cards,
# and/or have an Adventure" (CR 107.3 X-as-placeholder / 613.4c
# characteristic-defining). A THIRD diagnostic name —
# ``Unimplemented(name='creatures')`` — the whole dynamic P/T-setter clause
# dropped wholesale with no ``SetDynamicPower``/``SetDynamicToughness`` pair
# anywhere in the tree.
def _creatures_unimpl_descs(tree: ConceptTree) -> Iterator[str]:
    return tree.residues("creatures")


_CANDLEKEEP_RX = re.compile(
    r"where x is the number of cards you own in exile", re.IGNORECASE
)


def _candlekeep_gap(tree: ConceptTree) -> bool:
    return tree.has_residue("creatures")


def _candlekeep_match(tree: ConceptTree) -> bool:
    return _says(_CANDLEKEEP_RX, _creatures_unimpl_descs(tree))


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
    if any(c.role == "cost" for c in tree.iter_concepts()):
        return False
    return not any(
        "Exile" in filter_inzone_zones(getattr(n, "filter", None))
        or "Exile" in filter_inzone_zones(getattr(n, "target", None))
        for n in tree.iter_typed()
    )


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
    for n in tree.iter_typed():
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

# The attachment subtypes the voltron bridges gate on (CR 205.3g).
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
    for n in tree.iter_typed():
        if tag_of(n) == "ObjectCount":
            filt = getattr(n, "filter", None)
        else:
            filt = aggregate_filter(n)
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
    for unit in tree.iter_units("trigger"):
        if getattr(unit.node, "mode", None) != "Taps":
            continue
        if getattr(unit.node, "condition", None) is None:
            return True
    return False


def _warchanter_condition_match(tree: ConceptTree) -> bool:
    for unit in tree.iter_units("trigger"):
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
    ``ReduceAbilityCost`` tag appears anywhere on the card — the alternative-
    payment clause is structurally unlinked from the equip ability it
    modifies. Self-retires once phase ties the two together (a whole-card
    presence read over ``iter_typed``, never a per-unit walk)."""
    has_paycost_zero = has_equip_link = False
    for n in tree.iter_typed():
        if tag_of(n) == "PayCost":
            mana_cost = getattr(getattr(n, "cost", None), "cost", None)
            if getattr(mana_cost, "generic", None) == 0 and not getattr(
                mana_cost, "shards", None
            ):
                has_paycost_zero = True
        if (
            tag_of(n) == "ReduceAbilityCost"
            and str(getattr(n, "keyword", "")).lower() == "equip"
        ):
            has_equip_link = True
    return has_paycost_zero and not has_equip_link


def _forge_anew_match(tree: ConceptTree) -> bool:
    return bool(_FORGE_ANEW_RX.search(tree.oracle or ""))


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
# v0.66.0 pin bump: the "target opponent loses N life unless that player
# discards" alternative retired with Remorseless Punishment's graduation
# (phase now emits the unless_pay cost structurally — see
# ``keyword_mechanics._unless_pay_opponent_discard``).
_OPP_DISCARD_UNLESS_RX = re.compile(
    r"target player discards? a card unless",
    re.IGNORECASE,
)


def _opp_discard_unless_match(tree: ConceptTree) -> bool:
    return _says(_OPP_DISCARD_UNLESS_RX, _unless_clause_failure_descs(tree))


def _opp_discard_unless_gap(tree: ConceptTree) -> bool:
    # The unless-clause residue carrying THIS discard clause, not any unless-clause.
    return _says(_OPP_DISCARD_UNLESS_RX, _unless_clause_failure_descs(tree))


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
    for n in tree.iter_typed():
        if tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "unknown":
            yield getattr(n, "description", "") or ""


def _yawgmoth_tk_discard_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _yawgmoth_tk_discard_descs(tree))


def _yawgmoth_tk_discard_match(tree: ConceptTree) -> bool:
    return _says(_YAWGMOTH_TK_DISCARD_RX, _yawgmoth_tk_discard_descs(tree))


# ``_no_typed_discard_node`` — the shared gap for the two dropped-clause
# bridges below: no ``Discard``/``DiscardCard``-tagged node reachable
# ANYWHERE in the tree, mirroring ``sacrifice_outlets``'
# ``_no_typed_sacrifice_node`` precedent exactly (a broad, self-retiring
# absence proof; the narrow per-card ``match`` below is what keeps each
# bridge a scalpel, not a lane).
def _no_typed_discard_node(tree: ConceptTree) -> bool:
    return not any(tag_of(n) in ("Discard", "DiscardCard") for n in tree.iter_typed())


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
# :data:`~mtg_utils._analysis.lanes._TEXT_ONLY_OPP_DISCARD_
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
    return tree.is_text_only


def _driven_despair_match(tree: ConceptTree) -> bool:
    return bool(_DRIVEN_DESPAIR_RX.search(tree.oracle or ""))


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
    # The static_structure residue carrying THIS clause, not any static failure.
    return _says(_ROCK_HYDRA_RX, _static_parse_failure_descs(tree))


def _rock_hydra_match(tree: ConceptTree) -> bool:
    return _says(_ROCK_HYDRA_RX, _static_parse_failure_descs(tree))


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
    for unit in tree.iter_units("static"):
        dyn = static_mode_field(unit.node, "dynamic_count")
        if tag_of(dyn) == "PreviousEffectAmount":
            yield getattr(unit.node, "description", "") or ""


def _hierophant_gap(tree: ConceptTree) -> bool:
    return any(True for _ in _hierophant_modifycost_descs(tree))


def _hierophant_match(tree: ConceptTree) -> bool:
    return _says(_HIEROPHANT_RX, _hierophant_modifycost_descs(tree))


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
#
# Grammar-sprint attempt (task #82, 2026-07-12): tried the narrowest bounded
# structural sub-shape available — a STATIC ability whose affected Typed
# filter co-occurs ``Named`` + ``Another`` properties (the literal "each
# other creature/permanent named X gets..." self-buff shape Brothers
# Yamazaki's third line carries). It survives on exactly 1 of this lane's
# 29-card current-corpus population (Brothers Yamazaki) plus 1 near-miss the
# legacy regex itself undercounts (Syr Joshua and Syr Saxon — "creature you
# control named Syr Joshua and Syr Saxon has battle cry" doesn't match
# NAMED_PERMANENT_REGEX's word order but is the same idiom). The other two
# pins never reach a typed ``Named`` node at all — Mishra, Claimed by Gix's
# meld-partner clause and Sheltered Valley's land-legend-swap replacement
# both fail their static/replacement parsers and land as ``Unimplemented``
# residue, so "named X" survives only as raw text there, not structure. A
# full context-shape census (every ``(unit_origin, Named node type)`` pair
# corpus-wide) confirms no shape cleanly separates this lane's population
# from the rest: ``static/T_properties__Named`` is the best available
# signal and it is STILL a mix of 4 in-population against 12 out (3x
# over-fire for 14% recall); every other shape (``ability/T_properties__
# Named`` 5-in/81-out, ``trigger/T_properties__Named`` 10-in/64-out,
# ``trigger/T_filter__Named`` 0-in/53-out, ``ability/T_subject__Named``
# 0-in/18-out, ``trigger/T_subject__Named`` 0-in/10-out) is worse. There is
# no bounded structural discriminator to synthesize here — the disambiguation
# genuinely needs semantic classification of what the Named reference is
# FOR (self-buff vs tutoring vs partner-pair vs copy-limit vs planeswalker
# callback), which is exactly the dedicated classifier project the todo
# already names, not something a corpus-bounded tree_synthesis arm can
# close. Scan script + full result dump:
# /Users/danblanchard/.claude/jobs/097c2256/tmp/gs_named/.
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
# Four bridges close the last of the key's 53-card true-gap tail (the
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
# by :func:`~mtg_utils._analysis.lanes.
# _mass_untap_creature_filter`'s own SetTapState walk, so the shared gap
# below stands every one of them down on its own).
_LIGHTNING_RUNNER_UNTAP_RX = re.compile(
    r"pay eight \{E\}\. if you pay, untap all creatures you control, and "
    r"after this phase, there is an additional combat phase",
    re.IGNORECASE,
)


def _lightning_runner_gap(tree: ConceptTree) -> bool:
    return not any(tag_of(n) == "SetTapState" for n in tree.iter_typed())


def _lightning_runner_match(tree: ConceptTree) -> bool:
    return bool(_LIGHTNING_RUNNER_UNTAP_RX.search(tree.oracle or ""))


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
        for n in tree.iter_typed()
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
# :func:`~mtg_utils._analysis.lanes.
# _iter_creatures_matter_static_defs`'s ``affected``-filter check to find
# it as a team anthem).
_MOKU_HASTE_GRANT_RX = re.compile(
    r"gets? \+\d+/\+\d+ and creatures you control gain haste", re.IGNORECASE
)


def _moku_haste_grant_gap(tree: ConceptTree) -> bool:
    for unit in tree.iter_units():
        for sdef in unit.static_defs():
            if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
                continue
            if _MOKU_HASTE_GRANT_RX.search(getattr(sdef, "description", "") or ""):
                return True
    return False


def _moku_haste_grant_match(tree: ConceptTree) -> bool:
    return _moku_haste_grant_gap(tree)


def _hollow_static_says(tree: ConceptTree, rx: re.Pattern[str]) -> bool:
    """The gap every hollow-static bridge shares: one of phase's hollow static
    defs (:meth:`ConceptTree.hollow_statics` — ``affected: SelfRef``, an EMPTY
    ``modifications`` list) carries the clause in its ``description``. Keyed on
    the clause itself, so the gap goes False — RETIRE-READY, not pattern rot —
    the moment phase structures THAT line, whatever else stays hollow."""
    return _says(rx, tree.hollow_statics())


def _oracle_says(tree: ConceptTree, rx: re.Pattern[str]) -> bool:
    return bool(rx.search(tree.oracle or ""))


# (7) Siege Behemoth's "As long as this creature is attacking, FOR EACH
# CREATURE YOU CONTROL, you may have that creature assign its combat
# damage as though it weren't blocked" (CR 509.1h-adjacent unblocked-
# damage-assignment permission) — a hollow static def: ``affected`` is
# ``SelfRef`` and ``modifications`` is an EMPTY list; the whole per-creature
# grant lives only in the def's own ``description`` and an ``Unrecognized``
# condition text, never a typed mode or modification.
_SIEGE_BEHEMOTH_RX = re.compile(
    r"for each creature you control, you may have that creature assign "
    r"its combat damage as though it weren't blocked",
    re.IGNORECASE,
)


def _siege_behemoth_gap(tree: ConceptTree) -> bool:
    return _hollow_static_says(tree, _SIEGE_BEHEMOTH_RX)


def _siege_behemoth_match(tree: ConceptTree) -> bool:
    return _oracle_says(tree, _SIEGE_BEHEMOTH_RX)


# (8) Illusionist's Gambit → extra_combats. "Remove all attacking creatures
# from combat and untap them. After this phase, there is an additional
# combat phase. Each of those creatures attacks that combat if able. They
# can't attack you or planeswalkers you control that combat." — the
# ``Condition_If`` clause grammar swallows the WHOLE sentence (a phase
# ``SwallowedClause`` parse warning fires on it, unchanged since phase
# v0.20.0 through v0.23.0), leaving the card's one static ability def with
# ``affected: SelfRef`` and an EMPTY ``modifications`` list — the same
# residue shape as (7) Siege Behemoth above, no ``AdditionalPhase`` node of
# any kind reachable anywhere on the tree.
_ILLUSIONISTS_GAMBIT_RX = re.compile(
    r"after this phase, there is an additional combat phase", re.IGNORECASE
)


def _illusionists_gambit_gap(tree: ConceptTree) -> bool:
    return _hollow_static_says(tree, _ILLUSIONISTS_GAMBIT_RX)


def _illusionists_gambit_match(tree: ConceptTree) -> bool:
    return _oracle_says(tree, _ILLUSIONISTS_GAMBIT_RX)


# ── task B-3: keep_n_wrath — the Shape-B walk + Unimplemented-choose bridge ──
# Single home for the keep-N text/structure reads (verified-review F1/F9/F10):
# the lane imports the Shape-B walk + regexes from here, and the bridge's gap
# is "the lane's OWN accepted read finds nothing" — so a landed-but-rejected
# chain keeps bridge eligibility, and a landed-and-accepted one stands it down.
KNW_REST_RX = re.compile(r"(?:then )?(?:sacrifices?|destroys?) the rest", re.IGNORECASE)
_KNW_RANDOM_RX = re.compile(r"at random", re.IGNORECASE)
# A LANDS choose feeding the rest-clause (Limited Resources; Balance's lands
# arm) — mass land denial, the class KEEP_N_CHOOSE_TYPES exists to exclude.
# Balance's creature arm rides "the same way", which no bounded text read can
# honestly attribute — adjudicated excluded, conservatively (F1).
_KNW_LAND_CHOOSE_RX = re.compile(
    r"chooses? [^.\n]*\blands?\b[^.\n]*(?:then )?sacrifices? the rest",
    re.IGNORECASE,
)
# Core-type gate (mirrors _MASS_REMOVAL_TYPES' shape): Land deliberately
# absent — a land reset is denial, not a board reset.
KEEP_N_CHOOSE_TYPES = frozenset(
    {"Creature", "Permanent", "Planeswalker", "Artifact", "Enchantment"}
)


def _knw_one_sided(unit: AbilityUnit, effect_node: object) -> bool:
    """The keep-N reaches only opponents: the owning wrapper's ``player_scope``
    is Opponent ("each opponent chooses …"), or the trigger fires only during
    an opponent's turn ("that player chooses …" — Archfiend of Depravity)."""
    return effect_owner_player_scope(unit.node, effect_node) == "Opponent" or (
        unit.origin == "trigger"
        and trigger_turn_constraint(unit.node) == "OnlyDuringOpponentsTurn"
    )


def keep_n_casr_reads(tree: ConceptTree) -> list[tuple[str, str]]:
    """(scope, raw) per first-class ``ChooseAndSacrificeRest`` node whose
    ``sacrifice_filter`` core is in ``KEEP_N_CHOOSE_TYPES`` (Cataclysm class).
    Both chooser_scope values fire (Tragic Arrogance's you-pick-for-all resets
    every board too). Scope "opponents" when the owning wrapper is scoped to
    opponents — phase v0.94.0 moved No One Will Hear Your Cries onto this node
    with ``player_scope: Opponent`` (Liliana, Dreadhorde General's -9 and
    Ajani, Nacatl Avenger's -4 carried it all along); "each" otherwise."""
    out: list[tuple[str, str]] = []
    for unit in tree.iter_units():
        for c in unit.effects:
            if tag_of(c.node) != "ChooseAndSacrificeRest":
                continue
            # Type WORDS, not bare core types: Single Combat's filter is
            # {AnyOf: [Creature, Planeswalker]}, which filter_core_types skips.
            sac_filter = getattr(c.node, "sacrifice_filter", None)
            if not set(_filter_type_words(sac_filter)) & KEEP_N_CHOOSE_TYPES:
                continue
            scope = "opponents" if _knw_one_sided(unit, c.node) else "each"
            out.append((scope, c.raw or ""))
    return out


def keep_n_shape_b_reads(tree: ConceptTree) -> list[tuple[str, str]]:
    """(scope, raw) per ACCEPTED Shape-B keep-N chain: a gated ``TargetOnly``
    choose followed by a ``Sacrifice``/``Destroy`` whose target is the
    ``TrackedSet`` back-reference. The one walk both the lane (its Shape-B
    arm) and the bridge's gap consume — acceptance means core types in
    ``KEEP_N_CHOOSE_TYPES`` AND a resolvable scope (symmetric ScopedPlayer/
    All → "each"; You under an Opponent player_scope or an
    OnlyDuringOpponentsTurn trigger → "opponents")."""
    out: list[tuple[str, str]] = []
    for unit in tree.iter_units():
        pending: str | None = None
        for c in unit.effects:
            t = tag_of(c.node)
            if t == "TargetOnly":
                pending = None
                target = getattr(c.node, "target", None)
                if target is None or not (
                    set(filter_core_types(target)) & KEEP_N_CHOOSE_TYPES
                ):
                    continue
                ctrl = filter_controller(target)
                owner = effect_owner_player_scope(unit.node, c.node)
                if ctrl == "ScopedPlayer" and owner == "All":
                    pending = "each"
                elif ctrl == "You" and _knw_one_sided(unit, c.node):
                    pending = "opponents"
                continue
            if (
                pending
                and t in ("Sacrifice", "Destroy")
                and tag_of(getattr(c.node, "target", None)) == "TrackedSet"
            ):
                out.append((pending, c.raw or ""))
                pending = None
    return out


def _knw_gap(tree: ConceptTree) -> bool:
    return not (keep_n_casr_reads(tree) or keep_n_shape_b_reads(tree))


def _knw_match(tree: ConceptTree) -> bool:
    oracle = tree.oracle or ""
    return (
        bool(KNW_REST_RX.search(oracle))
        and not _KNW_RANDOM_RX.search(oracle)
        and not _KNW_LAND_CHOOSE_RX.search(oracle)
    )


# ── task B-5: combat_choice_makers — no typed choose-attackers/blockers node ─
_COMBAT_CHOICE_RX = re.compile(
    r"\bchoose (?:which creatures? (?:attack|block)|how those creatures? block)\b",
    re.IGNORECASE,
)


def _combat_choice_gap(tree: ConceptTree) -> bool:
    """The choose-attackers/blockers clause itself is still parked as an
    effect-position residue — goes False when a phase bump lands a typed
    choose-attackers/choose-blockers effect node for THAT clause, even if an
    unrelated "choose" line stays parked (Berserker's Frenzy parks two)."""
    return _says(_COMBAT_CHOICE_RX, tree.effect_residues())


def _combat_choice_match(tree: ConceptTree) -> bool:
    return _oracle_says(tree, _COMBAT_CHOICE_RX)


# ── artifacts_matter — the reflexive-payment regression (v0.35.2 bump) ───────
# "you may sacrifice a Food or pay {2}{W}. When you do, ..." (Nimble Hobbit —
# CR 603.12 reflexive trigger; Food is an artifact subtype, CR 205.3g). At
# v0.23.0 phase decomposed the payment as a ChooseOneOf carrying a typed Food
# Sacrifice branch; the v0.26.0+ reflexive-payment rework parks the WHOLE body
# as ``Unimplemented(name='reflexive optional payment')`` instead. Gap is the
# shared tree-wide ``_no_typed_sacrifice_node`` absence proof.
def _paycost_artifact_sacrifice_undecorated(tree: ConceptTree) -> bool:
    """phase v0.86.0 structures the reflexive payment (the ``Unimplemented('reflexive
    optional payment')`` residue of v0.26.0-v0.66.0 is gone): "you may sacrifice a
    Food or pay {2}{W}. When you do, …" is now an effect-role ``PayCost`` whose
    ``OneOf`` cost carries a typed ``Sacrifice(Food)`` leaf, with the reflexive body
    on a ``WhenYouDo`` sub-ability (CR 603.12). The gap is OURS now: the overlay
    decorates activation costs and top-level effects, so a sacrifice inside an
    effect's own cost never becomes a ``sacrifice`` concept the artifacts_matter
    read sees. True when such a leaf names an artifact (core type or a predefined
    artifact-token subtype) and no sacrifice concept was decorated anywhere."""
    if any(c.concept == "sacrifice" for c in tree.iter_concepts()):
        return False
    for n in tree.iter_typed():
        if tag_of(n) != "PayCost":
            continue
        for leaf in iter_cost_leaves(getattr(n, "cost", None)):
            if tag_of(leaf) != "Sacrifice":
                continue
            filt = getattr(leaf, "target", None)
            if "Artifact" in filter_core_types(filt) or (
                {x.lower() for x in filter_subtypes(filt)} & ARTIFACT_TOKEN_SUBTYPES
            ):
                return True
    return False


# ── predefined-token maker/payoff bridges (Blood-token gap sweep, 2026-07-25) ─
# Four measured gaps around the Blood/Clue/Food predefined-token lanes. The
# first three shapes are OUR overlay's frontier, not phase's: the typed
# substrate is complete (a fully-typed ``Token`` node exists) but the concept
# decoration only walks the top-level effect chain — a ``ChooseOneOf``
# BRANCH's Token (Transmutation Font) and a ``GrantTrigger``-granted
# trigger's Token (Ceremonial Knife) never surface as ``make_token``
# concepts, so ``_resource_token_makers``'s concept read finds nothing.
# Odric, Blood-Cursed rides the choice-list blood row via a second match arm
# (upstream_parse_failure class, the keep_n_wrath/Promise-of-Loyalty
# precedent): phase parks "create X Blood tokens, where X is the number of
# abilities ..." WHOLE as ``Unimplemented(name='create')``; the recovery
# stage decorates it as a ``make_token`` concept but with an EMPTY subject —
# no ``Blood`` for the lane's subtype read. CR 111.10 (predefined tokens)
# throughout.


def _make_token_concept_missing(tree: ConceptTree, subtype: str) -> bool:
    """The shared maker-row gap: no ``make_token`` concept ANYWHERE in the
    tree carries ``subtype`` in its subject — the exact read
    ``_resource_token_makers`` serves from. Self-retiring: the moment the
    overlay decorates the branch/granted Token (or phase's create-X grammar
    lands and recovery fills the subject), the concept appears with the
    subtype and the bridge stands down."""
    return not any(
        c.concept == "make_token" and subtype in c.subject for c in tree.iter_concepts()
    )


def _choice_branch_makes_token(tree: ConceptTree, subtype: str) -> bool:
    """A ``ChooseOneOf`` branch whose own effect is a typed ``Token`` node
    carrying ``subtype`` in its ``types`` — the choice-list maker idiom
    ("Create your choice of a Blood token, a Clue token, or a Food token"),
    read structurally off the branch nodes the decoration skips."""
    for n in tree.iter_typed():
        if tag_of(n) != "ChooseOneOf":
            continue
        for br in getattr(n, "branches", None) or []:
            eff = getattr(br, "effect", None)
            if tag_of(eff) == "Token" and subtype in (
                getattr(eff, "types", None) or ()
            ):
                return True
    return False


_CREATE_X_BLOOD_RX = re.compile(r"\bcreate x blood tokens\b", re.IGNORECASE)


def _blood_maker_concept_gap(tree: ConceptTree) -> bool:
    return _make_token_concept_missing(tree, "Blood")


def _choice_list_blood_match(tree: ConceptTree) -> bool:
    # Arm 1: the Font choice-list branch Token; arm 2: Odric's phase
    # Unimplemented('create') residue (see the section comment above).
    if _choice_branch_makes_token(tree, "Blood"):
        return True
    return _says(_CREATE_X_BLOOD_RX, _unimplemented_descs_anywhere(tree))


def _choice_list_clue_gap(tree: ConceptTree) -> bool:
    # clue_makers has TWO structural reads in _resource_token_makers: the
    # make_token subtype AND a first-class Investigate effect — both must
    # miss before the bridge may serve.
    if tree.has_effect("investigate"):
        return False
    return _make_token_concept_missing(tree, "Clue")


def _choice_list_clue_match(tree: ConceptTree) -> bool:
    return _choice_branch_makes_token(tree, "Clue")


def _choice_list_food_gap(tree: ConceptTree) -> bool:
    return _make_token_concept_missing(tree, "Food")


def _choice_list_food_match(tree: ConceptTree) -> bool:
    return _choice_branch_makes_token(tree, "Food")


# NOTE (grammar sprint, NOT fired here): The Third Doctor's choice list
# ("...create your choice of a Clue, a Food, or a Treasure token") could
# also serve treasure_makers via the identical branch read — beyond this
# sweep's named Blood/Clue/Food shapes, so it stays a comment; gold_makers
# is not a served key at all (verified absent from SERVED_SIGNAL_KEYS).


def _granted_trigger_blood_token_match(tree: ConceptTree) -> bool:
    """A ``GrantTrigger`` static modification whose granted trigger's own
    effect chain carries a typed Blood ``Token`` node ('Equipped creature
    ... has "Whenever this creature deals combat damage, create a Blood
    token."' — Ceremonial Knife, CR 301.5/613.1f)."""
    for n in tree.iter_typed():
        if tag_of(n) != "GrantTrigger":
            continue
        trig = getattr(n, "trigger", None)
        if trig is None:
            continue
        for t in iter_typed_nodes(trig):
            if tag_of(t) == "Token" and "Blood" in (getattr(t, "types", None) or ()):
                return True
    return False


def _blood_matters_structural_gap(tree: ConceptTree) -> bool:
    """The payoff-row gap: none of ``_resource_token_matters``'s three
    structural reads (a Blood-subtyped sacrifice EFFECT, a Blood-subtyped
    ``Sacrifice`` cost leaf, a ``synth_token_subtype_own_ref`` Blood marker)
    finds anything on this tree."""
    for c in tree.effect_concepts("sacrifice"):
        if "blood" in {s.lower() for s in filter_subtypes(effect_filter(c.node))}:
            return False
    for n in tree.iter_typed():  # every Sacrifice leaf, activation costs included
        if tag_of(n) == "Sacrifice" and "blood" in {
            s.lower() for s in filter_subtypes(getattr(n, "target", None))
        }:
            return False
    for c in tree.iter_concepts():
        if c.concept == "synth_token_subtype_own_ref" and any(
            s.lower() == "blood" for s in c.subject
        ):
            return False
    return True


def _blood_sacrificed_trigger_match(tree: ConceptTree) -> bool:
    """A ``Sacrificed``-mode trigger whose ``valid_card`` filter carries the
    Blood subtype and a You/unstated controller ("Whenever you sacrifice one
    or more Blood tokens, ..." — Blood Hypnotist; CR 701.21, the
    sacrifice-PAYOFF half). An Opponent-controller watcher is a punisher,
    not your payoff — excluded."""
    for unit in tree.units:
        if unit.trigger_event != "sacrificed":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or filter_controller(vc) not in (None, "You"):
            continue
        if any(s.lower() == "blood" for s in filter_subtypes(vc)):
            return True
    return False


# ── folded-object text-only lifeloss (ADR-0025, 2026-07-25) ──────────────────
# A wholly phase-uncovered folded object (the dungeon Tomb of Annihilation)
# gets ONLY a zero-unit text-only ConceptTree (ADR-0038 W2c generalized —
# ``_ir_lookup._text_only_tree``, ``units=()``): no LoseLife node exists for
# the lifeloss lane's typed reads, so the room text "Each player loses 1
# life" serves nothing. The bounded symmetric-bleed idiom rides a
# missing_face bridge instead — this is what carries Acererak's fold to the
# ADR-0025 flagship conclusion (self-bleed → the deck wants lifegain
# sustain). CR 309 (dungeons) / CR 119.3 throughout.
_EACH_PLAYER_LOSES_RX = re.compile(r"\beach player loses \d+ life\b", re.IGNORECASE)


def _text_only_tree_gap(tree: ConceptTree) -> bool:
    """No PHASE-BUILT unit == the W2c/ADR-0025 text-only shape
    (``_text_only_tree`` builds ``units=()``; the production pipeline's
    ``apply_tree_synthesis`` may then append ``origin="synth"`` bucket-B
    units — Tomb's Atropal line synthesizes a token-maker marker — which
    carry no typed ``LoseLife`` either, so they don't count as coverage).
    Goes False the moment phase covers the object (its tree then carries a
    real-origin unit, and the typed LoseLife reads own it)."""
    return tree.is_text_only


def _each_player_loses_match(tree: ConceptTree) -> bool:
    return bool(_EACH_PLAYER_LOSES_RX.search(tree.oracle or ""))


# ── phase v0.94.0 regressions (2026-09-26) ──────────────────────────────────────
# (1) damage_prevention — through v0.86.0 phase structured a static CR 615.1
# prevention line ("Prevent all damage that would be dealt to …", "… prevent
# that damage", "… prevent all but 1 of that damage") as a ``DamageDone``
# REPLACEMENT with ``shield_kind {Prevention}``, which the bucket-B
# ``synth_damage_prevention`` arm reads. v0.94.0's replacement parser
# recognizes the line and then fails it: the replacement is gone and the WHOLE
# line survives only as an ``Unimplemented`` residue — ``replacement_structure``
# ("Replacement pattern matched but line failed replacement parser: <line>";
# Light of Sanction, Well-Laid Plans, Ironscale Hydra, Hyperion) or, inside a
# "Choose target creature." chain, ``unparsed_replacement`` (Silhouette). The
# match is the CR 615.1a "prevent" verb over those residues' text. A
# prevent-and-reflect card ("When damage is prevented this way, …" — Phyrexian
# Vindicator, Stuffy Doll Avatar) carries the same residues but was never a
# member (Vindicator is damage_redirect's), so it stays out: a bridge restores
# the serving the regression took, never more. The gap keys on a residue that
# carries the prevention clause itself, so an unrelated residue of the same
# name left behind never masks a phase fix (RETIRE-READY, not pattern rot).
_PREVENTION_RESIDUE_NAMES = ("replacement_structure", "unparsed_replacement")
_PREVENTION_SHIELD_RX = re.compile(
    r"\bprevent (?:all (?:but \d+ of )?(?:that )?damage|that damage)\b",
    re.IGNORECASE,
)
_PREVENTED_THIS_WAY_RX = re.compile(r"\bprevented this way\b", re.IGNORECASE)


def _prevention_residue_descs(tree: ConceptTree) -> Iterator[str]:
    for name in _PREVENTION_RESIDUE_NAMES:
        yield from tree.residues(name)


def _prevention_parse_failure_gap(tree: ConceptTree) -> bool:
    return _says(_PREVENTION_SHIELD_RX, _prevention_residue_descs(tree))


def _prevention_parse_failure_match(tree: ConceptTree) -> bool:
    return _oracle_says(tree, _PREVENTION_SHIELD_RX) and not _oracle_says(
        tree, _PREVENTED_THIS_WAY_RX
    )


# (2) Camel → damage_prevention. "As long as this creature is attacking,
# prevent all damage Deserts would deal to this creature and to creatures
# banded with this creature" (CR 615.1a) — v0.86.0 parsed it as a Prevention
# replacement; v0.94.0 leaves a hollow static def (``affected: SelfRef``, a
# ``SourceIsAttacking`` condition and an EMPTY ``modifications`` list), the
# prevention living only in the def's own ``description`` (the Siege Behemoth
# / Illusionist's Gambit shape above — no residue node to key on).
def _prevention_empty_static_gap(tree: ConceptTree) -> bool:
    return _hollow_static_says(tree, _PREVENTION_SHIELD_RX)


def _prevention_empty_static_match(tree: ConceptTree) -> bool:
    return _oracle_says(tree, _PREVENTION_SHIELD_RX)


# (3) Fumble → voltron_makers. "Gain control of all Auras and Equipment that
# were attached to it, then attach them to another creature" (CR 701.3a) —
# v0.86.0 parsed the tail as an ``Attach`` (attachment ParentTarget, target
# another creature) the lane's sibling-gear arm read; v0.94.0 parks it as
# ``Unimplemented(name='plural_attachment_anaphor')`` "attach them to another
# creature". The residue names no gear, so the match takes the gear from the
# sibling ``GainControlAll``'s own Aura/Equipment filter (structural). Helm of
# Kaldra carries the same residue ("Attach those Equipment to it") but no
# GainControlAll — the lane's Unimplemented-attach-gear arm already serves it.
_ATTACH_ANAPHOR_RX = re.compile(r"\battach them to another creature\b", re.IGNORECASE)


def _plural_attach_anaphor_gap(tree: ConceptTree) -> bool:
    # The anaphor residue carrying THIS "attach them" clause (CONTEXT.md "Gap
    # predicate"), so a phase fix to it reads RETIRE-READY on its own.
    return _says(_ATTACH_ANAPHOR_RX, tree.residues("plural_attachment_anaphor"))


def _plural_attach_anaphor_match(tree: ConceptTree) -> bool:
    if not _plural_attach_anaphor_gap(tree):
        return False
    return any(
        tag_of(n) == "GainControlAll"
        and {s.lower() for s in filter_subtypes(getattr(n, "target", None))}
        & _VOLTRON_SUBTYPES
        for n in tree.iter_typed()
    )


BRIDGES: dict[str, Bridge] = {
    b.bridge_id: b
    for b in (
        Bridge(
            bridge_id="combat_choice_unimplemented_choose",
            key="combat_choice_makers",
            # Scope "opponents" uniformly (the goad_makers precedent): CR 508.1a and
            # 509.1a give attack and block declarations to the active and defending
            # players; these cards hand the choice to you, exercised over opponents'
            # combat decisions.
            scope="opponents",
            quote_oracle=True,
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the effect "
                "grammar has no choose-attackers/choose-blockers verb — 'you "
                "choose which creatures attack/block' and 'choose how those "
                "creatures block' park as Unimplemented(name='choose'/"
                "'creatures'/'15—20') — retires on a phase bump that "
                "structures the combat-choice effect (CR 508.1a / 509.1a: "
                "the declaration choices the card transfers to you)"
            ),
            census=(
                "5 hits / 35,397 phase records, all commander-legal (Master "
                "Warcraft, Melee, Odric Master Tactician, Brutal Hordechief, "
                "Berserker's Frenzy 15—20 arm; War's Toll's residue-shaped "
                "'attack if able' deliberately excluded by the choose "
                "anchor; Berserker's 1—14 ForceBlock arm fails the "
                "which/how idiom), phase v0.23.0, 2026-07-16"
            ),
            pins=(
                "Master Warcraft",
                "Brutal Hordechief",
                "Odric, Master Tactician",
                "Melee",
                "Berserker's Frenzy",
            ),
            gap=_combat_choice_gap,
            match=_combat_choice_match,
        ),
        Bridge(
            bridge_id="keep_n_wrath_unimplemented_choose",
            key="keep_n_wrath",
            scope="each",
            quote_oracle=True,
            kind="dropped_clause",
            todo=(
                "upstream phase-rs grammar candidate (Dan posts): the "
                "'choose …, then sacrifice/destroy the rest' choose step "
                "parses as Unimplemented(name='choose'/'for') instead of the "
                "TargetOnly node the Single Combat class gets — retires on a "
                "phase bump that promotes the choose to TargetOnly, at which "
                "point _keep_n_wrath's Shape-B chain reads it structurally "
                "(the gap stands this row down per-card the moment the "
                "chain lands). Promise of Loyalty's vow-counter variant "
                "graduated at phase v0.94.0 (a first-class "
                "ChooseAndSacrificeRest node, read by keep_n_casr_reads)."
            ),
            census=(
                "4 fire / whole pool (Duneblast 'Choose creature', Stick "
                "Together 'choose a party from among creatures they "
                "control', Mount Doom 'Choose creatures', Promise of "
                "Loyalty — no residue at all), 3 vetoed (Last One Standing "
                "'Choose a creature at random' — a random keep protects "
                "nothing; Balance + Limited Resources — lands-choose rest "
                "clauses, mass land denial per the KEEP_N_CHOOSE_TYPES "
                "gate, verified-review F1), phase v0.23.0, 2026-07-16; "
                "4 fire at phase v0.94.0 (Duneblast, Stick Together, Mount "
                "Doom, Balancing Act — 'chooses a number of permanents … "
                "then sacrifices the rest' is a Sacrifice with no choose "
                "node); Promise of Loyalty and Single Combat read "
                "structurally via keep_n_casr_reads, Limited Resources is a "
                "Land-gated ChooseAndSacrificeRest, 2026-09-26"
            ),
            pins=(
                "Duneblast",
                "Stick Together",
                "Mount Doom",
            ),
            gap=_knw_gap,
            match=_knw_match,
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
            # Filed dropped_clause at v0.20.0, when the keyword left no node at all;
            # by v0.94.0 phase parks the whole keyword line ("Warp—{B}, Pay 2
            # life.") as an Unimplemented(name='unknown') residue — phase tried and
            # failed, so the kind follows the evidence (test_bridge_ledger's
            # kind↔evidence check). The id keeps its history.
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "Warp / Blitz / Morph keyword grammar fails a life-cost "
                "variant (v0.20.0: no keyword entry at all; v0.94.0: the "
                "line parked as an Unimplemented residue — unlike "
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
            scope="any",
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
            bridge_id="base_pt_becomecopy_no_pt_override",
            key="base_pt_set",
            scope="any",
            # The override drops with ZERO trace (no field, no residue): a dropped
            # clause, not a parse failure (CONTEXT.md; the kind↔evidence check).
            kind="dropped_clause",
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
                "base_pt_set member via the deleted legacy IR engine "
                "directly) — exactly the 1 remaining pin"
            ),
            pins=("Mindlink Mech",),
            gap=_base_pt_becomecopy_no_mods_gap,
            match=_base_pt_becomecopy_no_mods_match,
        ),
        Bridge(
            bridge_id="donate_superlative_player_unbound_subject",
            key="donate_makers",
            kind="upstream_parse_failure",
            todo=(
                "FILED upstream as phase-rs/phase#8170 (2026-08-29): the v0.46.0 "
                "fail-closed subject binder (#7003) parks 'the player "
                "who/with <superlative> gains control of ~' as an "
                "Unimplemented('unbound_subject') residue — a typed "
                "GiveControl{SelfRef -> Any} through v0.45.0. Retires on a "
                "phase bump that binds a superlative-comparison player "
                "subject (the same class as Timesifter's 'takes an extra "
                "turn' and Celestial Convergence's 'wins the game', not "
                "bridged — one card each)"
            ),
            census=(
                "6 hits / 35,798 corpus records, all commander-legal "
                "(Ghazbán Ogre, Loxodon Peacekeeper, Sokenzan Renegade, "
                "Thoughtbound Primoc, Wild Dogs, Wild Mammoth), phase "
                "v0.66.0, 2026-08-29"
            ),
            pins=("Thoughtbound Primoc",),
            gap=_no_control_change_node,
            match=_donate_superlative_match,
        ),
        Bridge(
            bridge_id="removal_each_source_power_rider",
            key="removal",
            kind="upstream_parse_failure",
            todo=(
                "FILED upstream as phase-rs/phase#8171 (2026-08-29): phase "
                "v0.53.0 (#7322) "
                "fails the per-source 'each <X> … deals damage equal to its "
                "power to target creature' rider CLOSED as "
                "Unimplemented('each_source_unrepresentable_rider') — a "
                "typed DealDamage{Ref(Power, Anaphoric) -> Typed(Creature)} "
                "through v0.45.0. Retires on a phase bump that represents a "
                "per-source damage amount"
            ),
            census=(
                "2 hits / 35,798 corpus records, 1 commander-legal (Master "
                "of the Wild Hunt; Season's Beatings is not legal), phase "
                "v0.66.0, 2026-08-29"
            ),
            pins=("Master of the Wild Hunt",),
            gap=_no_creature_reaching_damage_node,
            match=_each_source_rider_match,
        ),
        Bridge(
            bridge_id="creature_ping_each_source_power_rider",
            key="creature_ping",
            kind="upstream_parse_failure",
            todo=(
                "same residue as removal_each_source_power_rider "
                "(phase-rs/phase#8171) — the "
                "creature_ping doer shape (a creature dealing damage equal "
                "to ITS OWN power to a creature, CR 120.3); retires with it"
            ),
            census=(
                "2 hits / 35,798 corpus records, 1 commander-legal (Master "
                "of the Wild Hunt), phase v0.66.0, 2026-08-29"
            ),
            pins=("Master of the Wild Hunt",),
            gap=_no_creature_reaching_damage_node,
            match=_each_source_rider_match,
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
            bridge_id="ramp_dropped_add_mana_clause",
            key="ramp",
            kind="grammar_straggler",
            todo=(
                "post-deletion grammar sprint (task #82): NARROWED — 22 of "
                "the former 24 names graduated into tree_synthesis._arm_"
                "ramp_dropped_add_mana_clause (a per-Unimplemented-node "
                "'add {mana-expression}' read, never a whole-card regex). "
                "NARROWED AGAIN (task #87): Braid of Fire graduated a "
                "SECOND time when build_concept_tree grew a dedicated "
                "'keyword' AbilityUnit origin for a keyword's own effect "
                "payload (crosswalk._keyword_effect_units) — its Mana "
                "effect is now a real effect_concepts('ramp') hit, no "
                "bridge needed. The 1 left is genuinely un-synthesizable "
                "by any current arm: Raggadragga, Goreguts Boss needs a "
                "'creature WITH a mana ability' filter-predicate grammar "
                "verb (a matters-lane idiom, not an add-mana clause — it "
                "never emits one, and its keywords list is empty so the "
                "new origin doesn't touch it either). Retires when its "
                "own gap closes."
            ),
            census=(
                "1 hit / 31,622 commander-legal (narrowed from 2, "
                "ADR-0039 task #87), phase v0.23.0, 2026-07-13"
            ),
            pins=("Raggadragga, Goreguts Boss",),
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
                "v0.20.0, 2026-07-12. At the v0.35.2 bump Judgment Bolt's "
                "'where X is the number of Equipment you control' scaling "
                "structured upstream (its pin graduated — served by the "
                "lane's dynamic-count read); Animal Friend and Sage's "
                "Reverie's 'for each ... attached' scaling still drops. "
                "NOTE: the legacy VOLTRON_PAYOFF_REGEX's bare 'equipment "
                "you control' branch is deliberately NOT reused here — it "
                "over-fires on Affinity-for-Equipment reminder text and "
                "imperative attach-ACTION clauses (Armed and Armored, "
                "Goldwardens' Gambit, Oxidda Finisher, Rebel Salvo, and 5 "
                "more of the existing attach-housekeeping shed class), "
                "all correctly excluded by this tighter anchor"
            ),
            pins=("Animal Friend", "Sage's Reverie"),
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
            bridge_id="opp_discard_unless_clause",
            key="opponent_discard",
            scope="opponents",
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
                "shaped unless-cost). HALF-RETIRED at the v0.66.0 pin "
                "bump: phase v0.65.0 (#7830) structures the third-person "
                "'target opponent loses N life unless that player "
                "discards' shape as the unit's own unless_pay cost "
                "(Remorseless Punishment graduated to keyword_mechanics' "
                "_unless_pay_opponent_discard); the second-person "
                "'target player discards a card unless they put a card "
                "... on top of their library' shape (Tainted Specter) is "
                "still parked as the residue — retires with it"
            ),
            census=(
                "1 hit / 35,798 corpus records, phase v0.66.0, 2026-08-29 "
                "(2 hits / 31,622 commander-legal at phase v0.20.0, "
                "2026-07-12); Wand of Ith carries the SAME residue class "
                "but is served INDEPENDENTLY via its own typed "
                "DiscardCard(ParentTarget) elsewhere in the tree — never "
                "reaches this bridge's gap"
            ),
            pins=("Tainted Specter",),
            gap=_opp_discard_unless_gap,
            match=_opp_discard_unless_match,
        ),
        Bridge(
            bridge_id="opp_discard_tk_sticker_parse_failure",
            key="opponent_discard",
            scope="opponents",
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
            bridge_id="opp_discard_fungal_shambler_dropped_conjunct",
            key="opponent_discard",
            scope="opponents",
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
            scope="opponents",
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
            scope="opponents",
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
            # Our Named-context classifier's frontier, not phase's (the todo: "NOT a
            # phase grammar gap") — a straggler, whatever residue some pins carry.
            kind="grammar_straggler",
            todo=(
                "dedicated Named-context classifier (confirmed NOT a "
                "grammar-sprint task #82 arm — task #82 tried the "
                "narrowest bounded structural sub-shape available "
                "[static Named+Another self-buff] and it recovers only "
                "1 of 29 current-corpus population cards with no clean "
                "context-shape split available corpus-wide; see the "
                "module comment's 'Grammar-sprint attempt' paragraph — "
                "this is a crosswalk-side disambiguation project, not a "
                "phase grammar gap): narrow the typed Named-node deep "
                "walk to exclude partner-pair references (CR 716.3), "
                "planeswalker-uncoupled 'Path of the X' callbacks, "
                "copy-limit swarms (CR 100.2a — the copy_limit sibling's "
                "own territory), and named-card library tutoring, "
                "keeping only the permanent-synergy self/other-name "
                "reference this lane serves — retires (for the cards it "
                "then covers) once that classifier lands and the lane "
                "switches to reading it structurally"
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
            # A misparse — the grant survives on a mis-scoped def ("not dropped
            # outright"), so phase tried and failed; never a dropped clause.
            kind="upstream_parse_failure",
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
            kind="upstream_parse_failure",
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
        Bridge(
            bridge_id="illusionists_gambit_additional_combat_swallowed",
            key="extra_combats",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs report candidate (Dan posts): the "
                "Condition_If clause grammar's SwallowedClause warning "
                "on Illusionist's Gambit's 'after this phase, there is "
                "an additional combat phase' sentence leaves the card's "
                "one static def (affected=SelfRef) with an EMPTY "
                "modifications list — no AdditionalPhase node anywhere "
                "on the tree — retires on a phase bump that structures "
                "the additional-combat-phase clause"
            ),
            census=(
                "1 hit / 31,622 commander-legal (Illusionist's Gambit; "
                "still SwallowedClause at v0.23.0, unchanged from "
                "v0.20.0), phase v0.23.0, 2026-07-12"
            ),
            pins=("Illusionist's Gambit",),
            gap=_illusionists_gambit_gap,
            match=_illusionists_gambit_match,
        ),
        Bridge(
            bridge_id="artifact_sac_reflexive_payment_undecorated",
            key="artifacts_matter",
            kind="grammar_straggler",
            todo=(
                "grammar sprint: decorate the cost leaves of an EFFECT-role "
                "``PayCost`` (phase v0.86.0's reflexive-payment shape — "
                "``PayCost{cost: OneOf[Sacrifice(Food), Mana]}`` + a "
                "``WhenYouDo`` sub-ability, CR 603.12) as cost concepts the way "
                "an activation cost's leaves are, so a 'sacrifice a Food' "
                "payment reads as a sacrifice concept and the artifacts_matter "
                "read serves it with no bridge. Through v0.66.0 the same body "
                "was an Unimplemented('reflexive optional payment') residue "
                "(an upstream gap, closed at v0.86.0)"
            ),
            census=(
                "1 commander-legal card lost artifacts_matter at the v0.86.0 "
                "bump (Nimble Hobbit — the pin; Bullseye, Death Dealer's SIBLING "
                "activated ability carries a fully-typed Sacrifice(Artifact) "
                "cost, so it is served structurally either way), 2026-09-17"
            ),
            pins=("Nimble Hobbit",),
            gap=_paycost_artifact_sacrifice_undecorated,
            match=_paycost_artifact_sacrifice_undecorated,
        ),
        Bridge(
            bridge_id="choice_list_token_maker_blood",
            key="blood_makers",
            kind="grammar_straggler",
            todo=(
                "grammar sprint (task #82): decorate ChooseOneOf BRANCH "
                "effects with concepts (the branch's typed Token -> a "
                "make_token concept whose subject carries the token "
                "subtypes) — the moment the overlay descends branches, "
                "the shared gap goes False and this row + its "
                "_resource_token_makers call delete. The Odric arm is an "
                "upstream phase-rs report candidate (Dan posts) riding "
                "this row via the match's second branch (the "
                "keep_n_wrath/Promise-of-Loyalty precedent): 'create X "
                "Blood tokens, where X is the number of abilities ...' "
                "parks WHOLE as Unimplemented(name='create'); recovery "
                "decorates it make_token but with an EMPTY subject — "
                "retires on a phase bump that structures the create-X-"
                "where-X count (the subject then carries Blood and the "
                "same gap stands the arm down)"
            ),
            census=(
                "2 hits / 38,261 distinct oracle_ids (31,552 commander-"
                "legal), structural sweep over every choice-list / "
                "create-X candidate: Transmutation Font (choice-list "
                "branch Token) + Odric, Blood-Cursed (Unimplemented "
                "'create' residue), MTGJSON 2026-07-25 @ phase v0.35.2"
            ),
            pins=("Transmutation Font", "Odric, Blood-Cursed"),
            gap=_blood_maker_concept_gap,
            match=_choice_list_blood_match,
        ),
        Bridge(
            bridge_id="choice_list_token_maker_clue",
            key="clue_makers",
            kind="grammar_straggler",
            todo=(
                "grammar sprint (task #82): the SAME ChooseOneOf-branch "
                "decoration gap as choice_list_token_maker_blood (one key "
                "per row splits the serving) — retires with it; the gap "
                "additionally stands down on a first-class Investigate "
                "effect (the lane's second clue read)"
            ),
            census=(
                "2 hits / 38,261 distinct oracle_ids (31,552 commander-"
                "legal): Transmutation Font + The Third Doctor (its "
                "Clue/Food/Treasure choice list shares the branch shape), "
                "MTGJSON 2026-07-25 @ phase v0.35.2"
            ),
            pins=("Transmutation Font",),
            gap=_choice_list_clue_gap,
            match=_choice_list_clue_match,
        ),
        Bridge(
            bridge_id="choice_list_token_maker_food",
            key="food_makers",
            kind="grammar_straggler",
            todo=(
                "grammar sprint (task #82): the SAME ChooseOneOf-branch "
                "decoration gap as choice_list_token_maker_blood (one key "
                "per row splits the serving) — retires with it"
            ),
            census=(
                "2 hits / 38,261 distinct oracle_ids (31,552 commander-"
                "legal): Transmutation Font + The Third Doctor, MTGJSON "
                "2026-07-25 @ phase v0.35.2 (The Third Doctor's Treasure "
                "branch could also serve treasure_makers — beyond this "
                "sweep's named shapes, ledgered as the section comment's "
                "grammar-sprint note instead)"
            ),
            pins=("Transmutation Font",),
            gap=_choice_list_food_gap,
            match=_choice_list_food_match,
        ),
        Bridge(
            bridge_id="granted_trigger_blood_token_maker",
            key="blood_makers",
            kind="grammar_straggler",
            todo=(
                "grammar sprint (task #82): decorate GrantTrigger-granted "
                "trigger bodies with concepts (the granted trigger's typed "
                "Token -> make_token, the same descent the granted-paylife "
                "/ sac-outlet granted-cost arms already hand-roll) — the "
                "moment the overlay walks the grant, the shared "
                "_make_token_concept_missing gap goes False and this row "
                "+ its _resource_token_makers call delete"
            ),
            census=(
                "1 hit / 38,261 distinct oracle_ids (31,552 commander-"
                "legal), structural sweep over every Blood-mentioning "
                "card's GrantTrigger nodes: Ceremonial Knife alone, "
                "MTGJSON 2026-07-25 @ phase v0.35.2"
            ),
            pins=("Ceremonial Knife",),
            gap=_blood_maker_concept_gap,
            match=_granted_trigger_blood_token_match,
        ),
        Bridge(
            bridge_id="blood_sacrificed_trigger_payoff",
            key="blood_matters",
            kind="grammar_straggler",
            todo=(
                "grammar sprint (task #82): grow a Sacrificed-trigger "
                "subject arm on _resource_token_matters (read the "
                "trigger's own valid_card subtypes structurally — the "
                "typed substrate is COMPLETE here, mode='Sacrificed' + "
                "Typed(Blood) valid_card; only the lane read is missing) "
                "— delete this row + its lane call when the arm lands"
            ),
            census=(
                "4 hits / 38,261 distinct oracle_ids (3 commander-legal: "
                "Blood Hypnotist, Gluttonous Guest, Sanguine Statuette; "
                "+ Sanguine Brushstroke, not commander-legal), MTGJSON "
                "2026-07-25 @ phase v0.35.2"
            ),
            pins=("Blood Hypnotist",),
            gap=_blood_matters_structural_gap,
            match=_blood_sacrificed_trigger_match,
        ),
        Bridge(
            bridge_id="folded_object_text_only_each_player_loses",
            key="lifeloss_makers",
            scope="each",
            kind="missing_face",
            todo=(
                "retires on a phase bump that emits card-data records for "
                "non-traditional folded objects (a Dungeon's rooms as "
                "typed LoseLife triggers — the gap's zero-units check "
                "goes False the moment ANY record lands) or on the "
                "ADR-0025 grammar sprint giving folded objects typed "
                "trees; until then the W2c text-only tree is the ONLY "
                "carrier of the room text"
            ),
            census=(
                "1 hit / 38,261 distinct oracle_ids, swept over every "
                "text-only-tree-eligible object whose oracle carries the "
                "bounded 'each player loses N life' idiom: Tomb of "
                "Annihilation alone (a Dungeon — not itself commander-"
                "legal; it serves via the ADR-0025 fold on its venturing "
                "commander, e.g. Acererak the Archlich), MTGJSON "
                "2026-07-25 @ phase v0.35.2"
            ),
            pins=("Tomb of Annihilation",),
            gap=_text_only_tree_gap,
            match=_each_player_loses_match,
        ),
        Bridge(
            bridge_id="damage_prevention_replacement_parse_failure",
            key="damage_prevention",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs regression (v0.86.0 → v0.94.0, report "
                "candidate — Dan posts): the replacement parser fails static "
                "'prevent all / that / all but N of that damage' lines it "
                "structured through v0.86.0 as DamageDone replacements with "
                "shield_kind Prevention — retires on the phase bump that "
                "restores them (the synth_damage_prevention arm reads the "
                "replacement again and the residue goes away)"
            ),
            census=(
                "5 hits / 7 Unimplemented residues of the two names whose "
                "text says 'prevent', corpus-wide (Light of Sanction, "
                "Well-Laid Plans, Ironscale Hydra, Hyperion, Supreme Hero, "
                "Silhouette — exactly the v0.86.0 members lost; Phyrexian "
                "Vindicator + Stuffy Doll Avatar vetoed as prevent-and-"
                "reflect), MTGJSON 2026-09-22 @ phase v0.94.0, 2026-09-26"
            ),
            pins=(
                "Light of Sanction",
                "Well-Laid Plans",
                "Ironscale Hydra",
                "Hyperion, Supreme Hero",
                "Silhouette",
            ),
            gap=_prevention_parse_failure_gap,
            match=_prevention_parse_failure_match,
        ),
        Bridge(
            bridge_id="camel_attacking_prevention_empty_static",
            key="damage_prevention",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs regression (v0.86.0 → v0.94.0, report "
                "candidate — Dan posts): Camel's 'as long as this creature "
                "is attacking, prevent all damage Deserts would deal to …' "
                "line became a SelfRef static def with an empty "
                "modifications list (a Prevention replacement through "
                "v0.86.0) — retires on the phase bump that structures it "
                "again (the def gains a modification or leaves the tree)"
            ),
            census=(
                "1 hit / every static def corpus-wide with empty "
                "modifications and 'prevent' text (Camel alone), MTGJSON "
                "2026-09-22 @ phase v0.94.0, 2026-09-26"
            ),
            pins=("Camel",),
            gap=_prevention_empty_static_gap,
            match=_prevention_empty_static_match,
        ),
        Bridge(
            bridge_id="fumble_plural_attachment_anaphor",
            key="voltron_makers",
            kind="upstream_parse_failure",
            todo=(
                "upstream phase-rs regression (v0.86.0 → v0.94.0, report "
                "candidate — Dan posts): 'then attach them to another "
                "creature' became Unimplemented(plural_attachment_anaphor) "
                "where v0.86.0 emitted an Attach (attachment ParentTarget) — "
                "retires on the phase bump that resolves the plural anaphor "
                "to a typed Attach/AttachAll the lane's gear-attach arms read"
            ),
            census=(
                "1 hit / 2 plural_attachment_anaphor residues corpus-wide "
                "(Fumble; Helm of Kaldra has no GainControlAll and is served "
                "by the lane), MTGJSON 2026-09-22 @ phase v0.94.0, 2026-09-26"
            ),
            pins=("Fumble",),
            gap=_plural_attach_anaphor_gap,
            match=_plural_attach_anaphor_match,
        ),
    )
}


def bridge_fires(bridge_id: str, tree: ConceptTree) -> bool:
    """Whether the registered bridge fires for this tree (gap AND match)."""
    return BRIDGES[bridge_id].fires(tree)


def bridges_for(key: str) -> tuple[Bridge, ...]:
    """Every ledgered bridge serving signal ``key`` — the question the ledger
    exists to answer (ADR-0048), so retirement and review read one place."""
    return tuple(b for b in BRIDGES.values() if b.key == key)


def bridge_signals(tree: ConceptTree) -> list[Signal]:
    """The one lane every ledgered bridge fires through (ADR-0048): each row that
    fires for ``tree`` emits its own ``Signal`` (key + scope from the row). No lane
    names a bridge id; the crosswalk's per-lane dedupe by (key, scope, subject)
    folds a bridge's signal into a structural read of the same ident."""
    return [b.signal(tree) for b in BRIDGES.values() if b.fires(tree)]
