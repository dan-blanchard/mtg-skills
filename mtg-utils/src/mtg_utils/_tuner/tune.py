"""The tuner orchestrator: ``HydratedDeck`` + injected ``search_fn`` → scorecard/swaps.

Skill-agnostic (ADR-0023): no ``ForgeState``, no FastAPI types. deck-forge's
``/api/tune`` adapts a ``ForgeState`` into these arguments; deck-wizard can call it
the same way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._deck_forge._ir_lookup import ir_for
from mtg_utils._deck_forge.budgets import slot_budgets
from mtg_utils._deck_forge.signals import rank_deck_signals, tribal_payoff_subjects
from mtg_utils._tuner import commander_fit, metrics
from mtg_utils._tuner import swaps as swaps_mod
from mtg_utils._tuner.bracket import bracket_gate
from mtg_utils._tuner.classify import CardClass, classify_deck
from mtg_utils._tuner.shape import infer_shape
from mtg_utils.deck_stats import deck_stats
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.mana_audit import mana_audit


@dataclass(frozen=True)
class TuneParams:
    """A Tune request. ``budget=None`` is the owned-only zero-spend default; an explicit
    number opens the buy pool. ``paper_only``/``medium`` come from the deck's Medium.
    ``wildcard_budget`` (digital builds) is the per-rarity Arena wildcard allowance
    ``{mythic, rare, uncommon, common}`` — when set it replaces the USD ``budget``: each
    unowned add costs one wildcard of its rarity, gated per tier (they don't swap)."""

    budget: float | None = None
    max_swaps: int = 0
    shape_override: str | None = None
    suggest_commander: bool = False
    paper_only: bool = True
    medium: str = "paper"
    wildcard_budget: Mapping[str, int] | None = None
    # The bracket the builder is AIMING for (ADR-0030). When set, the scorecard carries
    # a bracket-constraint gate; when None, the bracket axis is skipped entirely.
    target_bracket: int | None = None


def _deck_identity(hd: HydratedDeck) -> str:
    """The deck's color identity — the commander's (the deck identity it enforces),
    or the union across all cards when there is no commander."""
    colors: set[str] = set()
    sources = hd.commanders or []
    records = [hd.by_name.get(e["name"]) for e in sources]
    records = [r for r in records if r] or hd.records
    for rec in records:
        colors.update(rec.get("color_identity") or [])
    return "".join(sorted(colors))


def _fill_gap(
    deck: dict, classes: Sequence[CardClass], deck_size: int, recommended_lands: int
) -> tuple[int, int]:
    """Open NONLAND slots in an under-sized deck: returns (fill_slots, land_gap).

    fill_slots is the nonland target (deck_size, less recommended lands and commanders)
    minus the current nonland count -- the nonland adds the fill pass makes. land_gap is
    the lands still owed to the recommended mana base, left to the land tooling."""
    land_names = {c.name for c in classes if c.bucket == "land"}

    def qty(zone: str) -> int:
        return sum(int(e.get("quantity", 1)) for e in deck.get(zone) or [])

    num_cmd = len(deck.get("commanders") or [])
    total = qty("commanders") + qty("cards")
    lands = sum(
        int(e.get("quantity", 1))
        for e in deck.get("cards") or []
        if e["name"] in land_names
    )
    nonland_target = deck_size - recommended_lands - num_cmd
    current_nonland = total - lands - num_cmd
    fill_slots = max(0, nonland_target - current_nonland)
    land_gap = max(0, recommended_lands - lands)
    return fill_slots, land_gap


def _bucket_counts(classes: Sequence[CardClass]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in classes:
        out[c.bucket] = out.get(c.bucket, 0) + 1
    return out


def _focus_public(focus_r: dict) -> dict:
    return {k: v for k, v in focus_r.items() if not k.startswith("_")}


def _safe_combos(combos_fn: Callable[[dict], dict] | None, deck: dict) -> dict | None:
    """Combos feed win-con detection but ride a network call (Commander Spellbook). On
    any failure, degrade to heuristic-only win-cons rather than failing the whole Tune —
    the deterministic diagnosis must never depend on an external service."""
    if combos_fn is None:
        return None
    try:
        return combos_fn(deck)
    except Exception:  # noqa: BLE001 — any combos failure degrades, never breaks Tune
        return None


def tune(
    hd: HydratedDeck,
    *,
    search_fn: Callable[..., list[dict]],
    params: TuneParams,
    owned: Mapping[str, int] | None = None,
    combos_fn: Callable[[dict], dict] | None = None,
) -> dict:
    """Diagnose the deck and (when ``max_swaps>0``) propose budgeted swaps."""
    owned = dict(owned or {})
    deck = hd.deck
    commander_names = {e["name"] for e in deck.get("commanders") or []}
    deck_size = int(deck.get("deck_size") or 100)
    fmt = hd.format
    identity = _deck_identity(hd)

    stats = deck_stats(hd)
    avg_cmc = stats.get("avg_cmc", 0.0)
    mana = mana_audit(hd)
    combos = _safe_combos(combos_fn, deck)
    combo_count = len((combos or {}).get("combos") or [])
    # Cards in a combo line are protected from the cut proposer (ADR-0029): the
    # deterministic core must not quietly cut a combo piece.
    combo_pieces = {
        name
        for combo in (combos or {}).get("combos") or []
        for name in combo.get("cards") or []
    }

    # ADR-0029: resolve signals through the Card IR (regex fallback when no sidecar).
    deck_signals = rank_deck_signals(hd.records, commander_names, ir_for=ir_for)
    # ADR-0040 companion (task #101): the emerging-tribal payoff gate.
    payoff_subjects = tribal_payoff_subjects(hd.records, commander_names, ir_for=ir_for)
    classes = classify_deck(hd, deck_signals, commander_names)

    shape_r = infer_shape(
        classes,
        avg_cmc=avg_cmc,
        combo_present=combo_count > 0,
        override=params.shape_override,
    )
    shape = shape_r.shape

    budgets = slot_budgets(hd.expanded(), deck_size=deck_size, shape=shape)
    eff = metrics.efficiency(classes, shape=shape, avg_cmc=avg_cmc, deck_size=deck_size)
    foc = metrics.focus(
        classes,
        deck_size=deck_size,
        deck_signals=deck_signals,
        medium=params.medium,
        tribal_payoff_subjects=payoff_subjects,
    )
    tmpl = metrics.template_deviation(budgets)
    wins = metrics.win_conditions(classes, shape=shape, combo_count=combo_count)
    prot = metrics.protection(classes, shape=shape, deck_size=deck_size)
    cfit = metrics.commander_fit(classes, foc)
    issues = metrics.top_issues(
        efficiency_r=eff,
        focus_r=foc,
        template_r=tmpl,
        wincons_r=wins,
        protection_r=prot,
        commander_r=cfit,
    )

    # ADR-0030: a target-bracket constraint gate, only when a target was chosen.
    bracket = (
        bracket_gate(hd.records, params.target_bracket, combos=combos)
        if params.target_bracket is not None
        else None
    )

    scorecard = {
        "shape": {
            "value": shape,
            "inferred": shape_r.inferred,
            "scores": {k: round(v, 2) for k, v in shape_r.scores.items()},
            "evidence": shape_r.evidence,
        },
        "efficiency": eff,
        "focus": _focus_public(foc),
        "template": tmpl,
        "wincons": wins,
        "protection": prot,
        "commander_fit": cfit,
        "top_issues": issues,
        "counts": _bucket_counts(classes),
        # ADR-0029 enrichment: surface the mechanical reads the spine no longer leaves
        # to the agent — full mana audit (not just the land count), the curve histogram,
        # and the combo list (not just a tally).
        "mana": mana,
        "curve": stats.get("curve") or {},
        "combos": combos or {"combos": []},
        "bracket": bracket,
    }

    # Win-con floor protection (ADR-0029, sibling to combo-piece protection): at/below
    # the heuristic win-con floor, don't let the proposer cut a card the SAME scorecard
    # counts as a finisher — that would drop it below the floor it just reported. Above
    # the floor, marginal finishers stay trimmable.
    wincon_protect = set(wins["cards"]) if wins["count"] <= wins["target"][0] else set()

    swaps_out: dict = {"swaps": [], "spent": 0.0, "wildcards_spent": None, "note": None}
    if params.max_swaps > 0 and hd.has_records:
        recommended_lands = int(mana.get("recommended_land_count") or 0)
        fill_slots, land_gap = _fill_gap(deck, classes, deck_size, recommended_lands)
        swaps_out = swaps_mod.propose_swaps(
            classes,
            issues,
            budgets=budgets,
            focus_result=foc,
            deck_signals=deck_signals,
            search_fn=search_fn,
            identity=identity,
            fmt=fmt,
            paper_only=params.paper_only,
            owned=owned,
            budget=params.budget,
            max_swaps=params.max_swaps,
            top_heavy=eff["verdict"] == "top-heavy",
            fill_slots=fill_slots,
            wildcard_budget=params.wildcard_budget,
            protected=combo_pieces | wincon_protect,
            medium=params.medium,
        )
        # The fill pass deliberately skips lands; flag any mana-base shortfall so the
        # user runs the land tooling (balance-lands), not Tune, to finish it.
        if land_gap > 0:
            land_note = (
                f"Also ~{land_gap} lands short — run Balance Lands to finish the "
                "mana base."
            )
            swaps_out["note"] = (
                f"{swaps_out['note']} {land_note}" if swaps_out["note"] else land_note
            )

    suggestions = None
    if params.suggest_commander:
        suggestions = commander_fit.suggest_commanders(
            classes,
            deck_signals,
            viable_labels=[a["label"] for a in foc["viable_avenues"]],
            identity=identity,
            fmt=fmt,
            paper_only=params.paper_only,
            search_fn=search_fn,
            owned=set(owned),
        )

    return {
        "scorecard": scorecard,
        "swaps": swaps_out["swaps"],
        "spent": swaps_out["spent"],
        "wildcards_spent": swaps_out["wildcards_spent"],
        "swaps_note": swaps_out["note"],
        "commander_suggestions": suggestions,
    }
