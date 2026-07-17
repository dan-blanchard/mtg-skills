"""Pair reads — scored two-card mechanic interactions (ADR-0042).

Per-lane additive synergy cannot price MULTIPLICATIVE interactions: after
the B-6 serve fix, Mana Reflection correctly serves Zaxara's X-spells lane
and still ranks ~13.6k of 17k — one lane of credit — when the crowd plays it
precisely because amplifier x X-commander multiplies. A Pair read prices
that interaction deterministically: a candidate ident-pattern x a deck
ANCHOR, with a flat curated weight on the payoff scale and a CR-grounded
rationale.

Two anchor kinds (both v1, per the grilled design):

* ``commander`` — fires when the COMMANDER's own idents match the anchor
  pattern. The commander is reliably in play (CR 903.8: it recasts from the
  command zone), so the interaction reliably assembles — the mechanical
  justification for anchoring pairs to it.
* ``density`` — fires when at least ``threshold`` deck cards emit the anchor
  pattern (the free-sac-outlet x token-flood shape: no single card is the
  anchor, the MASS is).

Matched rows SUM without decay — curation bounds stacking (a few dozen
audited rows, unlike open-ended clusters) — into a separate additive
``pair_score`` readout: never injected into the synergy clusters (no
coupling with prominence/decay/gate machinery) and never Rate-multiplied
(the row already priced the interaction). The ledger follows the
bridge-ledger discipline: pins (snapshot-resident emitters of the candidate
pattern) and a hygiene test.

Ident patterns are ``fnmatch`` globs over the task-#90 ``"key|scope|subject"``
vocabulary. Candidate idents come from the same memoized per-oracle_id read
the serve ``signal_idents`` arm uses.
"""

from __future__ import annotations

import fnmatch
from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PairRead:
    """One ledger row. ``candidate``/``anchor`` are ident-pattern globs."""

    pair_id: str
    candidate: str
    anchor_kind: str  # "commander" | "density"
    anchor: str
    weight: float
    label: str
    rationale: str  # the CR-grounded mechanical hook
    pins: tuple[str, ...]  # snapshot-resident candidate-pattern emitters
    threshold: int = 1  # density only: >= N deck emitters
    # When True, the candidate ident's SUBJECT segment (the third |-part)
    # must equal a matching anchor ident's subject, both non-empty — the
    # tribal-fodder shape: Goblin fodder feeds Krenko's Goblin count,
    # Soldier fodder does not.
    match_subject: bool = False


@dataclass(frozen=True)
class PairContext:
    """The deck side, built once per ranking: the commander's idents and the
    deck's ident density (how many cards emit each ident)."""

    commander_idents: frozenset[str] = frozenset()
    density: Counter = field(default_factory=Counter)


PAIR_READS: dict[str, PairRead] = {
    row.pair_id: row
    for row in (
        PairRead(
            pair_id="amplifier_x_commander",
            candidate="mana_amplifier|you|",
            anchor_kind="commander",
            anchor="xspell_matters|*",
            weight=4.5,
            label="Mana amplifier x X-commander",
            rationale=(
                "X is chosen at announcement (CR 601.2b) and paid from what "
                "you can produce — doubling production (Mana Reflection, "
                "CR 614.1 replacement) raises the castable X ceiling every "
                "single turn the commander is out. The ADR-0042 flagship: "
                "one lane of additive credit, but the pair is the whole "
                "reason the crowd plays it."
            ),
            pins=("Mana Reflection", "Zendikar Resurgent"),
        ),
        PairRead(
            pair_id="token_fodder_x_death_commander",
            candidate="token_maker|*",
            anchor_kind="commander",
            anchor="death_matters|*",
            weight=3.0,
            label="Token fodder x death-payoff commander",
            rationale=(
                "Every body a token spell adds is a death trigger the "
                "commander converts (CR 603.6c leaves-the-battlefield "
                "triggers; CR 701.21a sacrifice feeds them on demand) — "
                "fodder count multiplies the commander's per-death payoff."
            ),
            pins=("Empty the Warrens", "Hordeling Outburst"),
        ),
        PairRead(
            pair_id="sac_outlet_x_token_commander",
            candidate="sacrifice_outlets|you|",
            anchor_kind="commander",
            anchor="token_maker|*",
            weight=3.0,
            label="Sac outlet x token commander",
            rationale=(
                "A token-engine commander refills the board every turn; a "
                "free outlet (CR 701.21a — sacrificing is the controller's "
                "own action, no timing window an opponent can break) turns "
                "each refill into mana/damage/value. The classic Krenko x "
                "Ashnod's Altar shape."
            ),
            pins=("Ashnod's Altar",),
        ),
        PairRead(
            pair_id="keep_n_x_voltron_commander",
            candidate="keep_n_wrath|*",
            anchor_kind="commander",
            anchor="voltron_matters|*",
            weight=3.0,
            label="Keep-N wrath x voltron commander",
            rationale=(
                "A choose-N reset keeps exactly the one big threat (the "
                "keep_n_wrath adjudication: the keep is the controller's "
                "choice, inverting the CR 701.21a edict direction) while "
                "clearing the blockers and dodging targeted removal — the "
                "voltron deck's asymmetric sweeper."
            ),
            pins=("Single Combat",),
        ),
        PairRead(
            pair_id="tribal_fodder_x_token_commander",
            candidate="token_maker|*",
            anchor_kind="commander",
            anchor="token_maker|*",
            weight=3.0,
            label="Tribal fodder x tribal token commander",
            rationale=(
                "A tribal token engine's activation SCALES with the tribe "
                "count (Krenko's X = the number of Goblins — game "
                "information counted on application, CR 608.2h), so every "
                "same-tribe body a fodder spell adds multiplies the next "
                "activation. Subject-matched: only the commander's OWN "
                "tribe feeds the count."
            ),
            pins=("Empty the Warrens", "Hordeling Outburst"),
            match_subject=True,
        ),
        PairRead(
            pair_id="combat_puppeteer_x_goad_density",
            candidate="combat_choice_makers|opponents|",
            anchor_kind="density",
            anchor="goad_makers|*",
            threshold=3,
            weight=3.0,
            label="Combat puppeteer x goad package",
            rationale=(
                "Goad forces the attack but its controller still declares "
                "(CR 701.15 / 508.1a); a puppeteer (Master Warcraft) takes "
                "the declarations themselves (CR 508.1a / 509.1a "
                "transferred), turning a table full of forced attacks into "
                "aimed ones. Density-anchored: one goad card is a trick, "
                "three are a plan."
            ),
            pins=("Master Warcraft",),
        ),
    )
}


def _card_idents(card: dict) -> frozenset[str]:
    from mtg_utils.theme_presets import _signal_idents_for

    return frozenset(_signal_idents_for(card))


def build_pair_context(
    commander_records: list[dict], deck_records: list[dict]
) -> PairContext:
    """The deck side of every pair row, computed once per ranking."""
    commander_idents: set[str] = set()
    for rec in commander_records:
        commander_idents |= _card_idents(rec)
    density: Counter = Counter()
    for rec in deck_records:
        for ident in _card_idents(rec):
            density[ident] += 1
    return PairContext(frozenset(commander_idents), density)


def _subject_of(ident: str) -> str:
    parts = ident.split("|")
    return parts[2] if len(parts) > 2 else ""


def _anchor_met(
    row: PairRead, ctx: PairContext, candidate_idents: frozenset[str]
) -> bool:
    if row.anchor_kind == "commander":
        anchors = [
            i for i in ctx.commander_idents if fnmatch.fnmatchcase(i, row.anchor)
        ]
        if not anchors:
            return False
        if not row.match_subject:
            return True
        subjects = {
            _subject_of(i)
            for i in candidate_idents
            if fnmatch.fnmatchcase(i, row.candidate) and _subject_of(i)
        }
        return any(_subject_of(a) in subjects for a in anchors if _subject_of(a))
    hits = sum(n for i, n in ctx.density.items() if fnmatch.fnmatchcase(i, row.anchor))
    return hits >= row.threshold


def pair_score(card: dict, ctx: PairContext | None) -> tuple[float, list[dict]]:
    """(summed weight, matched-row readout) for one candidate. Rows sum
    without decay; no context (or no idents) scores 0.0 — inert."""
    if ctx is None:
        return 0.0, []
    idents = _card_idents(card)
    if not idents:
        return 0.0, []
    total = 0.0
    readout: list[dict] = []
    for row in PAIR_READS.values():
        if not any(fnmatch.fnmatchcase(i, row.candidate) for i in idents):
            continue
        if not _anchor_met(row, ctx, idents):
            continue
        total += row.weight
        readout.append({"pair": row.pair_id, "label": row.label, "weight": row.weight})
    return round(total, 3), readout
