"""``proposal-check``: every mechanical gate a deck-wizard proposal must pass.

deck-wizard's Step 7 (pre-grill verification) and Step 10 (impact verification) were
six separate commands an agent ran and read by hand: build the preview deck, audit its
legality, compare its mana, price the adds, diff the combos, and cut-check the cuts.
This applies the cuts and adds once and runs all of them, so the review debate argues
strategy over facts that are already checked. It reuses each tool's own function; no
check is re-derived here.

Gates (each ``PASS`` / ``WARN`` / ``FAIL``; any ``FAIL`` fails the proposal):

- ``cuts`` — every cut names a card in the deck.
- ``size`` — the main deck meets the format's size (exact for the Commander family).
- ``legality`` — ``legality-audit`` passes on the new deck.
- ``lands`` — ``mana-audit``'s land band isn't ``FAIL`` (below the floor).
- ``budget`` — the adds fit ``--budget`` (paper USD) or ``--wildcards`` (Arena), when
  one is given.
- ``combos`` — no game-winning combo is lost (``FAIL`` unless ``--allow-combo-loss``);
  a near-miss a cut closes is a ``WARN``, and so is a combo search that's unavailable.
- ``multipliers`` — a cut that copies or multiplies the commander
  (``_analysis.multipliers``, the tuner's own cut protection) is a ``WARN``: it
  needs the justification the cut checklist asks for. ``cut-check``'s full readout
  for every commander rides beside it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click

from mtg_utils._analysis.multipliers import commander_multipliers
from mtg_utils._sidecar import atomic_write_json
from mtg_utils.build_deck import build_deck, lookup_missing_adds, normalize_entry
from mtg_utils.card_pool import CardPool
from mtg_utils.combo_search import combo_search, combos_or_none, is_game_winning
from mtg_utils.cut_check import run_cut_check
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option, resolve_bulk_path
from mtg_utils.deck_diff import deck_diff
from mtg_utils.formats import CostMode
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.legality_audit import legality_audit
from mtg_utils.mana_audit import mana_audit
from mtg_utils.mark_owned import load_collection, mark_owned
from mtg_utils.names import build_name_alias_map
from mtg_utils.price_check import check_prices

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
# mana-audit's land-band status → this gate: below the floor fails, over the flood
# line warns.
_LAND_GATE = {"FAIL": FAIL, "FLOOD": WARN}


def _gate(status: str, detail: str, **extra: object) -> dict:
    return {"status": status, "detail": detail, **extra}


def _combo_key(combo: Mapping) -> tuple[str, ...]:
    return tuple(sorted(combo.get("cards") or []))


def _combo_gate(
    before: Mapping | None, after: Mapping | None, cut_names: set[str], *, allow: bool
) -> dict:
    """Lost / gained combos and the near-misses a cut closes."""
    if before is None or after is None:
        return _gate(WARN, "combo search unavailable (Commander Spellbook unreachable)")
    after_keys = {_combo_key(c) for c in after.get("combos") or []}
    before_keys = {_combo_key(c) for c in before.get("combos") or []}
    lost = [c for c in before.get("combos") or [] if _combo_key(c) not in after_keys]
    gained = [c for c in after.get("combos") or [] if _combo_key(c) not in before_keys]
    closed = [
        n
        for n in before.get("near_misses") or []
        if cut_names & set(n.get("cards") or [])
    ]
    lost_winning = [c for c in lost if is_game_winning(c)]
    if lost_winning and not allow:
        status = FAIL
        detail = f"{len(lost_winning)} game-winning combo(s) lost: " + "; ".join(
            " + ".join(c["cards"]) for c in lost_winning
        )
    elif lost or closed:
        status = WARN
        detail = (
            f"{len(lost)} combo(s) lost, {len(closed)} near-miss(es) closed by a cut"
        )
    else:
        status = PASS
        detail = "no combo lost"
    return _gate(status, detail, lost=lost, gained=gained, near_misses_closed=closed)


def _multiplier_gate(hd: HydratedDeck, cut_names: set[str]) -> dict:
    """A cut that copies or multiplies the commander (the tuner's cut protection)."""
    cuts = [r for r in hd.records if r.get("name") in cut_names]
    hits = commander_multipliers(cuts, hd.expanded(zones=("commanders",)))
    if not hits:
        return _gate(PASS, "no cut multiplies the commander")
    detail = "cuts a commander multiplier: " + "; ".join(
        f"{name} ({why})" for name, why in sorted(hits.items())
    )
    return _gate(WARN, detail, cards=hits)


def _size_gate(new_hd: HydratedDeck) -> dict:
    """The size the Format allows: legality-audit checks only the minimum, so the
    Commander family's exact size (its ``size_cap``) is checked here."""
    fmt = new_hd.format
    total = new_hd.deck.get("total_cards", 0)
    cap = fmt.size_cap
    ok = fmt.min_deck_size <= total and (cap is None or total <= cap)
    want = f"at least {fmt.min_deck_size}" if cap is None else f"exactly {cap}"
    return _gate(PASS if ok else FAIL, f"{total} cards ({want})", total=total)


def _budget_gate(
    price: dict,
    cost_mode: CostMode,
    *,
    budget: float | None,
    wildcards: Mapping[str, int] | None,
) -> dict:
    cost = price.get("wildcard_cost")
    digital = cost_mode == "wildcards"
    if (budget is not None and digital) or (wildcards is not None and not digital):
        flag, mode = ("--budget", "digital") if digital else ("--wildcards", "paper")
        return _gate(
            WARN,
            f"{flag} doesn't apply to a {mode} build — not checked",
            wildcard_cost=cost,
            total_cost=price.get("total_cost"),
        )
    if wildcards is not None:
        cost = cost or {}
        over = {
            r: n - wildcards.get(r, 0)
            for r, n in cost.items()
            if n > wildcards.get(r, 0)
        }
        status = FAIL if over else PASS
        detail = (
            "over by " + ", ".join(f"{n} {r}" for r, n in over.items())
            if over
            else f"wildcards {dict(cost)} within {dict(wildcards)}"
        )
        return _gate(status, detail, wildcard_cost=cost)
    if budget is not None:
        spend = float(price.get("total_cost") or 0.0)
        status = FAIL if spend > budget else PASS
        return _gate(status, f"${spend:.2f} of ${budget:.2f}", total_cost=spend)
    return _gate(
        PASS, "no budget given", wildcard_cost=cost, total_cost=price.get("total_cost")
    )


def proposal_check(
    hd: HydratedDeck,
    cuts: Sequence[dict | str],
    adds: Sequence[dict | str],
    *,
    sideboard_cuts: Sequence[dict | str] | None = None,
    sideboard_adds: Sequence[dict | str] | None = None,
    extra_hydrated: list[dict] | None = None,
    bulk_path: Path | None = None,
    budget: float | None = None,
    wildcards: Mapping[str, int] | None = None,
    medium: str | None = None,
    collection: Mapping | None = None,
    name_aliases: dict[str, str] | None = None,
    allow_combo_loss: bool = False,
    combos_fn: Callable[[HydratedDeck], dict] = combo_search,
    multiplier_low: int = 1,
    multiplier_high: int = 1,
    opponents: int | None = None,
) -> tuple[HydratedDeck, dict]:
    """Apply the proposal to ``hd`` and run every gate. Returns the new deck and the
    report (``pass``, ``gates``, and each tool's full output). ``collection`` (a
    parsed collection) marks the adds you own as free."""
    cut_entries = [normalize_entry(c) for c in cuts]
    add_entries = [normalize_entry(a) for a in adds]
    sb_cut_entries = [normalize_entry(c) for c in sideboard_cuts or []]
    sb_add_entries = [normalize_entry(a) for a in sideboard_adds or []]
    new_hd, unmatched = build_deck(
        hd.deck,
        list(hd.records),
        cut_entries,
        add_entries,
        sideboard_cuts=sb_cut_entries or None,
        sideboard_adds=sb_add_entries or None,
        extra_hydrated=extra_hydrated,
    )
    fmt = new_hd.format
    # --medium, else the deck's own, else the format's default (ADR-0052).
    medium = fmt.resolve_medium(medium or hd.deck.get("medium"))
    cut_names = {c["name"] for c in cut_entries}

    legality = legality_audit(new_hd)
    mana_before, mana_after = mana_audit(hd), mana_audit(new_hd)
    land_status = mana_after["land_band"]["status"]
    priced = add_entries + sb_add_entries
    owned = list(hd.deck.get("owned_cards") or [])
    if collection is not None:
        # The deck's owned_cards only covers cards already in it, so the adds are
        # checked against the whole collection.
        owned += mark_owned(
            {"cards": priced}, dict(collection), name_aliases=name_aliases
        )["owned_cards"]
    price = check_prices(
        {
            "format": fmt.name,
            "cards": priced,
            "owned_cards": owned,
        },
        bulk_path=bulk_path,
        format=fmt.name,
        medium=medium,
    )
    # Two independent Commander Spellbook round-trips: run them side by side; an
    # outage degrades the combos gate, never the whole check.
    with ThreadPoolExecutor(max_workers=2) as pool:
        before_job, after_job = (
            pool.submit(combos_or_none, combos_fn, hd),
            pool.submit(combos_or_none, combos_fn, new_hd),
        )
        combos = {"before": before_job.result(), "after": after_job.result()}

    gates = {
        "cuts": _gate(
            FAIL if unmatched else PASS,
            f"not in the deck: {', '.join(unmatched)}" if unmatched else "all found",
            unmatched=unmatched,
        ),
        "size": _size_gate(new_hd),
        "legality": _gate(
            PASS if legality["overall_status"] == "PASS" else FAIL,
            legality["overall_status"],
        ),
        "lands": _gate(
            _LAND_GATE.get(land_status, PASS),
            f"{mana_after['land_band']['count']} lands, band "
            f"{mana_after['land_band']['floor']}-{mana_after['land_band']['top']} "
            f"({land_status})",
        ),
        "budget": _budget_gate(
            price, fmt.cost_mode(medium), budget=budget, wildcards=wildcards
        ),
        "combos": _combo_gate(
            combos["before"], combos["after"], cut_names, allow=allow_combo_loss
        ),
        "multipliers": _multiplier_gate(hd, cut_names),
    }
    report = {
        "pass": all(g["status"] != FAIL for g in gates.values()),
        "gates": gates,
        "diff": deck_diff(hd, new_hd),
        "legality": legality,
        "mana": {
            "before": mana_before["land_band"],
            "after": mana_after["land_band"],
            "ramp_before": mana_before["ramp_count"],
            "ramp_after": mana_after["ramp_count"],
        },
        "price": price,
        "combos": combos,
    }
    if fmt.has_commander and hd.commanders and cut_names:
        report["cut_check"] = {
            commander["name"]: run_cut_check(
                hydrated=list(hd.records),
                commander_name=commander["name"],
                cut_names=sorted(cut_names),
                trigger_types=[],
                multiplier_low=multiplier_low,
                multiplier_high=multiplier_high,
                opponents=opponents
                if opponents is not None
                else (3 if fmt.game(medium).multiplayer else 1),
            )
            for commander in hd.commanders
        }
    return new_hd, report


def render_text_report(report: dict) -> str:
    lines = [f"proposal-check: {'PASS' if report['pass'] else 'FAIL'}"]
    for name, gate in report["gates"].items():
        lines.append(f"  {gate['status']:4}  {name:9} {gate['detail']}")
    diff = report["diff"]
    lines.append(
        f"  cards {diff['count_before']}→{diff['count_after']}, "
        f"lands {diff['land_count_before']}→{diff['land_count_after']}, "
        f"ramp {diff['ramp_count_before']}→{diff['ramp_count_after']}, "
        f"avg MV {diff['avg_cmc_before']}→{diff['avg_cmc_after']}"
    )
    return "\n".join(lines) + "\n"


def _read_list(path: Path | None) -> list:
    return json.loads(path.read_text(encoding="utf-8")) if path else []


def _parse_wildcards(text: str | None) -> dict[str, int] | None:
    if not text:
        return None
    out: dict[str, int] = {}
    for part in text.split(","):
        rarity, _, n = part.partition("=")
        out[rarity.strip().lower()] = int(n)
    return out


@click.command()
@click.argument("deck_json", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option("--cuts", "cuts_json", type=click.Path(exists=True, path_type=Path))
@click.option("--adds", "adds_json", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--sideboard-cuts", "sb_cuts_json", type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--sideboard-adds", "sb_adds_json", type=click.Path(exists=True, path_type=Path)
)
@click.option("--budget", type=float, default=None, help="Paper budget in USD.")
@click.option(
    "--wildcards",
    default=None,
    help="Arena wildcard budget, e.g. mythic=1,rare=0,uncommon=48,common=33.",
)
@click.option("--medium", type=click.Choice(["paper", "digital"]), default=None)
@click.option(
    "--collection",
    "collection_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Collection (parsed JSON or Untapped/Moxfield CSV); adds you own are free.",
)
@click.option(
    "--allow-combo-loss",
    is_flag=True,
    help="Let a lost game-winning combo pass (a justified cut).",
)
@click.option("--multiplier-low", type=int, default=1)
@click.option("--multiplier-high", type=int, default=1)
@click.option("--opponents", type=int, default=None)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where new-deck.json and proposal-check.json go (default: beside DECK_JSON).",
)
def main(
    deck_json: Path,
    bulk_data: Path | None,
    cuts_json: Path | None,
    adds_json: Path | None,
    sb_cuts_json: Path | None,
    sb_adds_json: Path | None,
    budget: float | None,
    wildcards: str | None,
    medium: str | None,
    collection_path: Path | None,
    allow_combo_loss: bool,  # noqa: FBT001 — a click flag
    multiplier_low: int,
    multiplier_high: int,
    opponents: int | None,
    output_dir: Path | None,
) -> None:
    """Apply a proposal's cuts and adds to DECK_JSON and run every mechanical gate:
    legality, size, lands, budget, combos, and cut-check on the cuts."""
    output_dir = (output_dir or deck_json.parent).resolve()
    hd = acquire_for_cli(deck_json, bulk_data)
    bulk_path = resolve_bulk_path(bulk_data)
    adds = _read_list(adds_json)
    sb_adds = _read_list(sb_adds_json)
    extra = lookup_missing_adds(
        [normalize_entry(e) for e in [*adds, *sb_adds]], list(hd.records), bulk_path
    )
    new_hd, report = proposal_check(
        hd,
        _read_list(cuts_json),
        adds,
        sideboard_cuts=_read_list(sb_cuts_json),
        sideboard_adds=sb_adds,
        extra_hydrated=extra,
        bulk_path=bulk_path,
        budget=budget,
        wildcards=_parse_wildcards(wildcards),
        medium=medium,
        collection=load_collection(collection_path) if collection_path else None,
        name_aliases=build_name_alias_map(bulk_path)
        if collection_path and bulk_path
        else None,
        allow_combo_loss=allow_combo_loss,
        multiplier_low=multiplier_low,
        multiplier_high=multiplier_high,
        opponents=opponents,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    deck_path = output_dir / "new-deck.json"
    atomic_write_json(deck_path, new_hd.deck)
    # The in-process join beside the new deck, as build-deck writes it, so the next
    # tool reads it instead of re-joining.
    new_hd.write_sidecar(deck_path, CardPool.load(bulk_path))
    report_path = output_dir / "proposal-check.json"
    atomic_write_json(report_path, report)
    click.echo(render_text_report(report), nl=False)
    click.echo(f"New deck: {deck_path}\nFull JSON: {report_path}")
    if not report["pass"]:
        raise SystemExit(1)
