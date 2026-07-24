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
    # Iteration-2 extension: the all-of conjunction on the CANDIDATE side
    # (mirror of anchor_all) — every listed pattern must match some ident
    # of the candidate. A count payoff must be tribal-subject-matched AND
    # carry a variable-P/T count read; a yard stocker must tutor AND touch
    # the graveyard. One matching half alone is a lane, not the pair.
    candidate_all: tuple[str, ...] = ()


@dataclass(frozen=True)
class PairContext:
    """The deck side, built once per ranking: the commander's idents, the
    commander's own creature subtypes (lowercased — the scoped_subject_gate
    compares engine scopes against them), and the deck's ident density (how
    many cards emit each ident)."""

    commander_idents: frozenset[str] = frozenset()
    commander_subtypes: frozenset[str] = frozenset()
    density: Counter = field(default_factory=Counter)
    # S2 (2.6): the commander records the context was built from — the
    # limiter discounts' anchor-yield read needs the actual records.
    commander_records: tuple = ()


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
        # ── Iteration 2 (ADR-0043 amended protocol, 2026-07-18): 7 rows
        # from the v2-panel mining sweep (20 per-commander miners over the
        # adjudication-kill + crowd-miss surfaces, one synthesis; triage in
        # the session's BUILD-PLAN). New mechanism: candidate_all. ─────────
        PairRead(
            pair_id="self_death_value_x_death_commander",
            candidate=("sacrifice_outlets|you|*", "edict_makers|*"),
            anchor_kind="commander",
            anchor=("death_matters|*",),
            weight=3.0,
            label="Own-death value x death-payoff commander",
            rationale=(
                "The COST side of the death engine: an effect that kills "
                "your own creatures by your choice (CR 701.21a — sacrifice "
                "moves it from the battlefield straight to the graveyard) "
                "is a two-for-one under a commander converting each "
                "own-creature death into value (CR 603.6c dies triggers: "
                "Meren's experience, Wilhelt's token, Teysa's doubling) — "
                "the stated effect PLUS the per-death payoff, every "
                "activation. The death_payoff row prices the observer "
                "side; this prices the actuator."
            ),
            pins=("Birthing Pod", "Fleshbag Marauder"),
        ),
        PairRead(
            pair_id="power_threshold_x_cheat_commander",
            candidate=("power_matters|you|*",),
            anchor_kind="commander",
            anchor=("cheat_into_play|you|*",),
            weight=3.0,
            label="Power-threshold payoff x body-cheating commander",
            rationale=(
                "A payoff gated on or scaled by high power (ferocious, "
                "'greatest power among creatures you control', power-N+ "
                "ETB draws) is a coin-flip in a generic deck; a commander "
                "that repeatedly CHEATS oversized bodies onto the "
                "battlefield (Gishath, The Ur-Dragon) holds the "
                "conditional mode reliably on — the check reads live game "
                "state on application (CR 608.2h)."
            ),
            pins=("Elemental Bond",),
        ),
        PairRead(
            pair_id="extra_combat_x_attack_trigger_commander",
            candidate=("extra_combats|you|*",),
            anchor_kind="commander",
            anchor=("attack_matters|*",),
            weight=3.0,
            label="Extra combat x attack-trigger commander",
            rationale=(
                "An additional combat phase (CR 505.1a) is a full second "
                "firing of the commander's per-combat attack trigger "
                "(CR 603.2c — each combat's attack event is a separate "
                "trigger instance): Isshin and The Ur-Dragon convert every "
                "extra combat into a second helping of their signature "
                "payoff on top of the raw damage."
            ),
            pins=("Hellkite Charger", "Godo, Bandit Warlord"),
        ),
        PairRead(
            pair_id="counter_amplifier_x_counter_commander",
            candidate=(
                "counter_doubling|you|*",
                "counter_replace_bonus|you|*",
                "counter_distribute|you|*",
            ),
            anchor_kind="commander",
            anchor=(
                "plus_one_makers|you|*",
                "any_counter_makers|you|*",
                "proliferate_makers|you|*",
                "experience_makers|you|*",
            ),
            weight=3.0,
            label="Counter amplifier x counter-stream commander",
            rationale=(
                "A counters-'instead' replacement (CR 614.1a — the "
                "Hardened Scales class) or redistributor multiplies EVERY "
                "counter event (CR 122.1) the commander's own engine "
                "produces: Zaxara's X-counter Hydras, Atraxa's "
                "proliferate, Meren's experience. Flat lane weight prices "
                "it once; the pair is per-event, all game."
            ),
            pins=("Hardened Scales", "Ozolith, the Shattered Spire"),
        ),
        PairRead(
            pair_id="count_payoff_x_tribal_count_commander",
            candidate=("type_matters|you|*",),
            candidate_all=("variable_pt|*",),
            anchor_kind="commander",
            anchor=("token_maker|*",),
            weight=3.0,
            label="Count payoff x tribal count-engine commander",
            rationale=(
                "A characteristic-defining P/T that IS the live tribe "
                "count (CR 604.3 CDA — Battle Squadron, Reckless One) is "
                "pegged 1:1 to the census the commander inflates every "
                "activation (Krenko doubling Goblins). Subject-matched "
                "like the tribal-fodder row, plus candidate_all "
                "(variable_pt): tribal membership alone is a lane, not "
                "this pair."
            ),
            match_subject=True,
            pins=("Battle Squadron", "Reckless One"),
        ),
        PairRead(
            pair_id="yard_stocker_x_graveyard_commander",
            candidate=("tutor|you|*",),
            candidate_all=("graveyard_matters|you|*",),
            anchor_kind="commander",
            anchor=("graveyard_matters|you|*",),
            weight=3.0,
            label="Yard stocker x graveyard commander",
            rationale=(
                "A tutor whose destination or byproduct is the graveyard "
                "(Buried Alive, Unmarked Grave, Fauna Shaman) is card "
                "selection into the zone a graveyard commander casts from "
                "— under Muldrotha or Meren the yard is a second hand, so "
                "stocking it is tutoring to a castable zone. "
                "candidate_all requires the graveyard half: a plain "
                "to-hand tutor stays generic."
            ),
            pins=("Buried Alive", "Fauna Shaman"),
        ),
        PairRead(
            pair_id="xcost_spell_x_xspell_commander",
            candidate=("xcost_spell|you|*",),
            anchor_kind="commander",
            anchor=("xspell_matters|*",),
            weight=3.0,
            label="X-cost spell x X-payoff commander",
            rationale=(
                "X is announced once at casting (CR 601.2b) and read by "
                "BOTH the spell's own effect and the commander's X-trigger "
                "(Zaxara: an X-counter Hydra per X-spell) — every X-spell "
                "is two X-sized value streams for one cost. The candidate "
                "ident is record-derived from the mana cost ({X} "
                "present), the ledger's one cost-shape read."
            ),
            pins=("Stroke of Genius",),
        ),
        # ── Iteration 3 (lane-gap batch, 2026-07-18): the recast loop —
        # the mining sweep's biggest un-priced miss cluster (Muldrotha's
        # 13 cards, Meren's re-arm trio, Chulane's bounce package), built
        # on two new lanes: self_etb_payload (candidate) and
        # permanent_recast (anchor). ────────────────────────────────────
        PairRead(
            pair_id="etb_value_x_recast_commander",
            candidate=("self_etb_payload|you|*",),
            candidate_not=("token_maker|*",),
            anchor_kind="commander",
            anchor=("permanent_recast|you|*",),
            weight=3.0,
            label="ETB value x recast-engine commander",
            rationale=(
                "Enters triggers fire on EVERY entry (CR 603.6a) — a "
                "one-shot ETB value clause (Shriekmaw's destroy, "
                "Mulldrifter's draw, Fleshbag Marauder's edict) is priced "
                "as single-use by the lanes, but under a commander that "
                "repeatably re-delivers the permanent (Muldrotha's "
                "graveyard-cast permission, Meren's end-step reanimate, "
                "Chulane's bounce-and-replay) its true value is the clause "
                "x recasts-per-game. Token MAKERS are vetoed "
                "(candidate_not): the fodder rows already price them."
            ),
            pins=("Shriekmaw", "Mulldrifter"),
        ),
        # ── Iteration 4 (2026-07-18): Feather's entire miss file sat at
        # pair 0.0 — no ident marked "this spell targets your own
        # permanent" until the own_target_spell lane. ───────────────────
        PairRead(
            pair_id="own_target_spell_x_rebate_commander",
            candidate=("own_target_spell|you|*",),
            anchor_kind="commander",
            anchor=("targeting_matters|*",),
            weight=3.0,
            label="Own-target spell x targeting-rebate commander",
            rationale=(
                "A spell that targets your own permanent by its printed "
                "filter (Ephemerate, Feat of Resistance) is a one-shot in "
                "a generic deck; a commander whose trigger keys on spells "
                "targeting your permanents (Feather returns them to hand "
                "at end step; Zada copies them per creature) turns each "
                "into a PER-TURN engine — the same CR 603.2c per-cast "
                "trigger instance read as the cast rows. Strict candidate "
                "class: controller==You printed filters only (an "
                "any-target pump is Feather-compatible by choice, not by "
                "text — a documented recall gap, not imprecision)."
            ),
            pins=("Ephemerate", "Feat of Resistance"),
        ),
    )
}


def _card_idents(card: dict) -> frozenset[str]:
    from mtg_utils.theme_presets import _signal_idents_for

    idents = set(_signal_idents_for(card))
    # The ledger's one RECORD-DERIVED cost-shape ident (not a signal lane):
    # {X} anywhere in the mana cost. X is announced once at casting
    # (CR 601.2b) and read by both the spell's effect and an
    # xspell_matters commander's trigger — the xcost row's candidate side.
    costs = [card.get("mana_cost") or ""] + [
        f.get("mana_cost") or "" for f in card.get("card_faces") or []
    ]
    if any("{X}" in c for c in costs):
        idents.add("xcost_spell|you|")
    return frozenset(idents)


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
        tuple(commander_records),
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


def pair_score(
    card: dict,
    ctx: PairContext | None,
    *,
    discount_fn=None,
) -> tuple[float, list[dict]]:
    """(summed weight, matched-row readout) for one candidate. Rows sum
    without decay; no context (or no idents) scores 0.0 — inert.

    ``discount_fn`` (S2, default None = OFF): a callable
    ``(card, row, matched_idents) -> multiplier`` applied to each matched
    row's weight — the limiter discounts
    (:mod:`mtg_utils._deck_forge.limiter_discounts`); flips on only if
    the S2 slice measurement accepts."""
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
            matched = [i for i in matched if _scope_reaches_commander(i, row, ctx)]
        if not matched:
            continue
        if row.candidate_all and not all(
            any(fnmatch.fnmatchcase(i, pat) for i in idents)
            for pat in row.candidate_all
        ):
            continue
        if row.candidate_not and any(
            _matches_any(i, row.candidate_not) for i in idents
        ):
            continue
        if not _anchor_met(row, ctx, idents):
            continue
        weight = row.weight
        if discount_fn is not None:
            weight = round(weight * discount_fn(card, row, matched), 4)
        total += weight
        readout.append({"pair": row.pair_id, "label": row.label, "weight": weight})
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
