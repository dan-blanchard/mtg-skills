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
    candidate: tuple[str, ...]
    anchor_kind: str  # "commander" | "density"
    anchor: tuple[str, ...]
    weight: float
    label: str
    rationale: str  # the CR-grounded mechanical hook
    pins: tuple[str, ...]  # snapshot-resident candidate-pattern emitters
    threshold: int = 1  # density only: >= N deck emitters
    # Iteration-1 extensions (2026-07-17): candidate/anchor are any-of glob
    # tuples; candidate_not vetoes the row when the card ALSO emits a
    # matching ident (the ETB payoff row must not double-credit token
    # MAKERS the fodder rows already price); anchor_all is an all-of
    # conjunction on top of the any-of anchor (an attack rider needs a
    # commander with attack triggers AND trigger doubling — Teysa's death
    # doubling must not mispair).
    candidate_not: tuple[str, ...] = ()
    anchor_all: tuple[str, ...] = ()
    # When True, the candidate ident's SUBJECT segment (the third |-part)
    # must equal a matching anchor ident's subject, both non-empty — the
    # tribal-fodder shape: Goblin fodder feeds Krenko's Goblin count,
    # Soldier fodder does not.
    match_subject: bool = False
    # Iteration-1 panel fix: when True, a candidate ident carrying a
    # NON-EMPTY subject (a subtype-SCOPED engine — Myr Galvanizer's
    # ``untap_engine|you|Myr``) only counts if that subject matches the
    # commander's own subtypes or a matching anchor ident's subject;
    # unscoped candidates ("" subject — Thousand-Year Elixir) pass
    # untouched. Unlike match_subject this never REQUIRES a subject; it
    # vetoes a scope the deck's commander can't reach. Commander-anchored
    # rows only.
    scoped_subject_gate: bool = False


@dataclass(frozen=True)
class PairContext:
    """The deck side, built once per ranking: the commander's idents, the
    commander's own creature subtypes (lowercased — the scoped_subject_gate
    compares engine scopes against them), and the deck's ident density (how
    many cards emit each ident)."""

    commander_idents: frozenset[str] = frozenset()
    commander_subtypes: frozenset[str] = frozenset()
    density: Counter = field(default_factory=Counter)


PAIR_READS: dict[str, PairRead] = {
    row.pair_id: row
    for row in (
        PairRead(
            pair_id="amplifier_x_commander",
            candidate=("mana_amplifier|you|",),
            anchor_kind="commander",
            anchor=("xspell_matters|*",),
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
            candidate=("token_maker|*",),
            anchor_kind="commander",
            anchor=("death_matters|*",),
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
            candidate=("sacrifice_outlets|you|",),
            anchor_kind="commander",
            anchor=("token_maker|*",),
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
            candidate=("keep_n_wrath|*",),
            anchor_kind="commander",
            anchor=("voltron_matters|*",),
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
            candidate=("token_maker|*",),
            anchor_kind="commander",
            anchor=("token_maker|*",),
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
        # ── Iteration 1 (ADR-0043 mining, 2026-07-17): 8 rows mined from
        # the study's 692 misses (19 adjudicators + synthesis), mapped to
        # verified ident emissions. ─────────────────────────────────────────
        PairRead(
            pair_id="anthem_x_swarm_commander",
            candidate=("anthem_static|you|*", "scaling_pump|you|*"),
            anchor_kind="commander",
            anchor=("token_maker|*", "tokens_matter|you|*"),
            weight=3.0,
            label="Anthem x swarm commander",
            rationale=(
                "A continuous per-body grant applies in layer 7 to each of N "
                "bodies simultaneously (CR 613.1g / 613.4c), so anthem value "
                "is proportional to the commander's token output — Heraldic "
                "Banner under Krenko buffs every Goblin the next activation "
                "mints. The commander's text never says 'anthem'; the "
                "multiplication exists only at the pair level. Subtype-"
                "scoped anthems (Goblin King) gate on reaching the "
                "commander's swarm (iteration-1 panel: Merrow Reejerey's "
                "Merfolk anthem died under Urza — scoped_subject_gate)."
            ),
            pins=("Heraldic Banner", "Crucible of Fire"),
            scoped_subject_gate=True,
        ),
        PairRead(
            pair_id="etb_payoff_x_flood_commander",
            candidate=("creature_etb|you|*",),
            candidate_not=("token_maker|*",),
            anchor_kind="commander",
            anchor=("token_maker|*", "cheat_into_play|you|*"),
            weight=3.0,
            label="ETB payoff x flood commander",
            rationale=(
                "Each entering body is a separate trigger instance (CR "
                "603.2c: one event with multiple occurrences triggers once "
                "per occurrence) — X tokens per Krenko activation queue X "
                "copies of Impact Tremors' payoff at once. Token MAKERS are "
                "vetoed (candidate_not): the fodder rows already price them."
            ),
            pins=("Impact Tremors", "Kindred Discovery"),
        ),
        PairRead(
            pair_id="trigger_doubler_x_trigger_commander",
            candidate=(
                "trigger_doubling|you|*",
                "ability_copy|you|*",
                "token_copy_makers|you|*",
                "clone_makers|you|*",
            ),
            anchor_kind="commander",
            anchor=(
                "attack_matters|*",
                "death_matters|*",
                "creature_etb|*",
                "spellcast_matters|*",
                "combat_damage_matters|*",
                "combat_damage_to_opp|*",
                "cheat_into_play|*",
            ),
            weight=4.5,
            label="Trigger doubler x trigger-engine commander",
            rationale=(
                "A doubler or copy engine is a pure multiplier on the "
                "commander's signature triggered ability (CR 603.2c — a "
                "second instance is a full second resolution): Roaming "
                "Throne naming the commander's type fires the trigger twice, "
                "a Strionic copy is a second free cheat/drain per event, a "
                "commander clone is an independent second engine. Marquee "
                "multiplicative class (4.5). An activated-engine commander "
                "(Krenko) offers nothing to double — the anchor set is "
                "trigger keys only."
            ),
            pins=("Roaming Throne", "Strionic Resonator"),
        ),
        PairRead(
            pair_id="death_payoff_x_death_commander",
            candidate=("death_matters|*", "self_death_payoff|you|*"),
            anchor_kind="commander",
            anchor=("death_matters|*", "sacrifice_outlets|you|*"),
            weight=3.0,
            label="Death payoff x death-engine commander",
            rationale=(
                "A death-trigger observer's worth is deaths-per-turn x "
                "triggers-per-death (CR 603.6c leaves-the-battlefield "
                "triggers): a commander that manufactures or doubles death "
                "events (Wilhelt's per-death token stream, Teysa's doubling) "
                "sets the rate the payoff's flat lane weight never expresses."
            ),
            pins=("Dictate of Erebos", "Field of Souls"),
        ),
        PairRead(
            pair_id="cast_payoff_x_cast_commander",
            candidate=("spellcast_matters|you|*",),
            anchor_kind="commander",
            anchor=("spellcast_matters|*", "draw_matters|you|*"),
            weight=3.0,
            label="Cast payoff x cast-rate commander",
            rationale=(
                "Each cast is a separate trigger instance (CR 603.2c); a "
                "commander that rewards casting (Talrand's per-spell Drake) "
                "shapes the deck into a high-cast-rate engine, so every "
                "per-cast payoff (Guttersnipe, Aetherflux Reservoir) fires "
                "at the deck's cast rate, not the pool average the flat "
                "lane weight assumes."
            ),
            pins=("Guttersnipe", "Aetherflux Reservoir"),
        ),
        PairRead(
            pair_id="untap_x_activated_commander",
            candidate=("untap_engine|you|*",),
            anchor_kind="commander",
            anchor=("activated_ability|you|*",),
            weight=4.5,
            label="Untap engine x activated commander",
            rationale=(
                "An untapper is a pure activation multiplier: a second "
                "untap-and-activate per turn literally doubles the "
                "commander's output (CR 602.1 activation, no per-turn limit "
                "without one printed) — Thousand-Year Elixir under Krenko is "
                "the marquee case (4.5), the same multiplicative class as "
                "amplifier x X-commander. Subtype-scoped untappers gate on "
                "reaching the commander (iteration-1 panel: Myr Galvanizer "
                "'untaps each OTHER Myr' died unanimously under Krenko and "
                "Urza — scoped_subject_gate)."
            ),
            pins=("Thousand-Year Elixir", "Seedborn Muse"),
            scoped_subject_gate=True,
        ),
        PairRead(
            pair_id="attack_rider_x_attack_doubler_commander",
            candidate=("attack_matters|you|*",),
            anchor_kind="commander",
            anchor=("attack_matters|you|*",),
            anchor_all=("trigger_doubling|you|*",),
            weight=3.0,
            label="Attack rider x attack-doubling commander",
            rationale=(
                "An attack trigger under a doubling commander fires twice "
                "per combat (CR 603.2c — Isshin's second instance is a full "
                "second resolution). anchor_all requires attack triggers AND "
                "doubling on the commander: Teysa doubles DEATH triggers, "
                "and an attack rider gains nothing from her."
            ),
            pins=("Hellrider", "Leonin Warleader"),
        ),
        PairRead(
            pair_id="recursion_fodder_x_graveyard_commander",
            candidate=(
                "dies_recursion|you|*",
                "has_undying_persist|you|*",
                "self_death_payoff|you|*",
            ),
            anchor_kind="commander",
            anchor=("graveyard_matters|you|*",),
            weight=3.0,
            label="Self-recycling fodder x graveyard commander",
            rationale=(
                "A body that returns itself (undying/persist, CR 702.93/"
                "702.79; dies-recursion riders) is repeatable fodder under a "
                "graveyard commander whose engine recasts or rebuys from the "
                "yard (Muldrotha, Meren) — the same card dies for value "
                "every turn cycle, which no single-use lane weight prices."
            ),
            pins=("Putrid Goblin",),
        ),
        PairRead(
            pair_id="combat_puppeteer_x_goad_density",
            candidate=("combat_choice_makers|opponents|",),
            anchor_kind="density",
            anchor=("goad_makers|*",),
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


def _commander_subtypes(commander_records: list[dict]) -> frozenset[str]:
    """Lowercased creature subtypes across the commanders' FRONT faces (the
    gameplay identity a scoped engine must reach — Krenko: {goblin})."""
    subs: set[str] = set()
    for rec in commander_records:
        front_type = (rec.get("type_line") or "").split(" // ")[0]
        _, _, tail = front_type.partition("—")
        subs |= {w.lower() for w in tail.split()}
    return frozenset(subs)


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
    return PairContext(
        frozenset(commander_idents),
        _commander_subtypes(commander_records),
        density,
    )


def _subject_of(ident: str) -> str:
    parts = ident.split("|")
    return parts[2] if len(parts) > 2 else ""


def _matches_any(ident: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(ident, pat) for pat in patterns)


def _anchor_met(
    row: PairRead, ctx: PairContext, candidate_idents: frozenset[str]
) -> bool:
    if row.anchor_kind == "commander":
        anchors = [i for i in ctx.commander_idents if _matches_any(i, row.anchor)]
        if not anchors:
            return False
        # anchor_all: every listed pattern must ALSO match some commander
        # ident (the attack-rider conjunction).
        for pat in row.anchor_all:
            if not any(fnmatch.fnmatchcase(i, pat) for i in ctx.commander_idents):
                return False
        if not row.match_subject:
            return True
        subjects = {
            _subject_of(i)
            for i in candidate_idents
            if _matches_any(i, row.candidate) and _subject_of(i)
        }
        return any(_subject_of(a) in subjects for a in anchors if _subject_of(a))
    hits = sum(n for i, n in ctx.density.items() if _matches_any(i, row.anchor))
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
        matched = [i for i in idents if _matches_any(i, row.candidate)]
        if row.scoped_subject_gate:
            matched = [
                i for i in matched if _scope_reaches_commander(i, row, ctx)
            ]
        if not matched:
            continue
        if row.candidate_not and any(
            _matches_any(i, row.candidate_not) for i in idents
        ):
            continue
        if not _anchor_met(row, ctx, idents):
            continue
        total += row.weight
        readout.append({"pair": row.pair_id, "label": row.label, "weight": row.weight})
    return round(total, 3), readout


def _scope_reaches_commander(ident: str, row: PairRead, ctx: PairContext) -> bool:
    """scoped_subject_gate: an UNSCOPED candidate ident ("" subject) always
    passes; a subtype-scoped one (``untap_engine|you|Myr``) passes only when
    the scope reaches the deck's commander — the subject is one of the
    commander's own subtypes (a Myr untapper under a Myr commander) or a
    matching anchor ident's subject (a Goblin anthem over Krenko's Goblin
    token stream). The iteration-1 panel's unanimous kills (Myr Galvanizer
    under Krenko/Urza, Merrow Reejerey under Urza) are exactly the scoped-
    and-unreachable class."""
    subject = _subject_of(ident).lower()
    if not subject:
        return True
    if subject in ctx.commander_subtypes:
        return True
    return any(
        _subject_of(a).lower() == subject
        for a in ctx.commander_idents
        if _matches_any(a, row.anchor)
    )
