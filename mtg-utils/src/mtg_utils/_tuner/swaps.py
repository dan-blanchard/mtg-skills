"""Cut selection + add sourcing → budgeted (cut, add) swap pairs.

Cuts: filler → over-band Spine excess → stranded Engine singletons, gated by hard
floors (never the commander, a Spine role at/below floor, lands, or a dual-purpose
card). Adds: issue-driven calls to the injected ``search_fn`` (Spine/protection fills
efficiency-first, avenue-deepening synergy-first), budget-bounded (owned = free,
no-listing never free). No new search code — the tuner is a new *caller* of the
existing search + ranking (ADR-0023).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._tuner.classify import CardClass
from mtg_utils.card_classify import extract_price

_ROLE_SEARCH: dict[str, dict] = {
    "ramp": {"preset_names": ("ramp",)},
    "card_draw": {"preset_names": ("card-draw",)},
    "interaction": {
        "preset_names": ("removal", "creature-removal", "counterspell", "bounce")
    },
    "board_wipe": {"preset_names": ("board-wipe",)},
}
_PROTECTION_SEARCH = {
    "preset_names": ("hexproof", "indestructible", "protection", "ward", "counterspell")
}
_WINCON_SEARCH = {"oracle": r"wins the game|an additional combat phase|deals damage"}
# Roles whose fills should be ranked efficiency-first (cheapest does-the-job) per ADR.
_SPINE_KINDS = {"role_short", "protection_short"}


def _fills_short_role(card: CardClass, budgets: dict) -> bool:
    return any(budgets.get(r, {}).get("deviation", 0) < 0 for r in card.roles)


def cut_candidates(
    classes: Sequence[CardClass],
    *,
    budgets: dict,
    focus_verdict: str,
    stranded: set[str],
) -> list[tuple[str, CardClass]]:
    """Ordered (reason, card) cut candidates, most-cuttable first. Hard floors apply."""
    out: list[tuple[str, CardClass]] = []
    seen: set[str] = set()

    def push(reason: str, card: CardClass) -> None:
        if card.name not in seen:
            seen.add(card.name)
            out.append((reason, card))

    # 1. Filler — do-nothing high-CMC before do-nothing cheap (efficiency-aware).
    for c in sorted(
        (c for c in classes if c.bucket == "filler"),
        key=lambda c: c.cmc,
        reverse=True,
    ):
        push("filler", c)

    # 2. Over-band Spine excess — weakest (low synergy, high CMC) first, never a card
    #    that also fills a short role, never a dual-purpose card.
    for role, b in budgets.items():
        if role == "lands" or b["deviation"] <= 0:
            continue
        members = [
            c
            for c in classes
            if c.bucket == "spine"
            and role in c.roles
            and not c.dual_purpose
            and not _fills_short_role(c, budgets)
        ]
        members.sort(key=lambda c: (len(c.served), -c.cmc))
        for c in members[: b["deviation"]]:
            push(f"over:{role}", c)

    # 3. Stranded Engine singletons — only when refocusing a spread-thin deck.
    if focus_verdict == "SPREAD-THIN":
        for c in sorted(
            (
                c
                for c in classes
                if c.bucket == "engine"
                and len(c.served) <= 1
                and set(c.served) & stranded
            ),
            key=lambda c: c.cmc,
            reverse=True,
        ):
            push("stranded", c)

    return out


def _acquire_cost(
    record: dict, owned: Mapping[str, int], budget: float | None, spent: float
) -> float | None:
    """Cost to acquire this add, or None when not affordable. Owned = free; a no-listing
    card is never free (treated as scarce); budget None = owned-only."""
    name = record.get("name", "")
    if owned.get(name, 0) >= 1:
        return 0.0
    price = extract_price(record)
    if price is None:  # no-listing: never $0
        return None
    if budget is None:  # owned-only pass
        return None
    return price if spent + price <= budget else None


def _run_search(
    search_fn: Callable[..., list[dict]],
    spec: dict,
    *,
    identity: str,
    fmt: str,
    paper_only: bool,
    cmc_cap: float | None,
    limit: int = 60,
) -> list[dict]:
    # A spec may carry its own cmc band (a thin-top-end fix wants cmc_min 6); combine
    # its ceiling with the top-heavy cap so both hold.
    spec_max = spec.get("cmc_max")
    if cmc_cap is None:
        cmc_max = spec_max
    elif spec_max is None:
        cmc_max = cmc_cap
    else:
        cmc_max = min(spec_max, cmc_cap)
    return search_fn(
        color_identity=spec.get("color_identity") or identity,
        exact_colors=False,
        oracle=spec.get("oracle"),
        card_type=spec.get("card_type"),
        name=None,
        cmc_min=spec.get("cmc_min"),
        cmc_max=cmc_max,
        price_min=None,
        price_max=None,
        format=fmt,
        paper_only=paper_only,
        preset_names=tuple(spec.get("preset_names") or ()),
        is_commander_filter=False,
        sort="cmc-asc",
        limit=limit,
        offset=0,
    )


def _avenue_search_for(label: str, deck_signals: list) -> dict | None:
    for sig in deck_signals:
        spec = spec_for(sig)
        if spec is not None and spec.label == label:
            return dict(spec.search)
    return None


def propose_swaps(
    classes: Sequence[CardClass],
    issues: Sequence[dict],
    *,
    budgets: dict,
    focus_result: dict,
    deck_signals: list,
    search_fn: Callable[..., list[dict]],
    identity: str,
    fmt: str,
    paper_only: bool,
    owned: Mapping[str, int],
    budget: float | None,
    max_swaps: int,
    top_heavy: bool,
) -> dict:
    """Walk the ranked issues, sourcing a (cut, add) pair per actionable issue up to
    ``max_swaps``. Returns the swaps + a note when fewer than asked were found."""
    in_deck = {c.name for c in classes}
    stranded = set(focus_result["stranded_avenues"])
    cuts = cut_candidates(
        classes,
        budgets=budgets,
        focus_verdict=focus_result["verdict"],
        stranded=stranded,
    )
    cut_iter = iter(cuts)
    used_adds: set[str] = set()
    swaps: list[dict] = []
    spent = 0.0
    cmc_cap = 4.0 if top_heavy else None

    def find_add(spec: dict, *, synergy_first: bool) -> tuple[dict, float] | None:
        """The best affordable add for this spec — does NOT commit spend (the caller
        commits once a cut is secured, so an unpaired add can't inflate the total)."""
        found = _run_search(
            search_fn,
            spec,
            identity=identity,
            fmt=fmt,
            paper_only=paper_only,
            cmc_cap=cmc_cap,
        )
        pool = [c for c in found if c.get("name") not in in_deck | used_adds]
        if synergy_first:
            ranked = [
                r["card"] for r in rank_candidates(pool, active_signals=deck_signals)
            ]
        else:
            ranked = sorted(
                pool, key=lambda c: (c.get("cmc", 0.0), extract_price(c) or 1e9)
            )
        for card in ranked:
            cost = _acquire_cost(card, owned, budget, spent)
            if cost is not None:
                return card, cost
        return None

    for issue in issues:
        if len(swaps) >= max_swaps:
            break
        spec = _spec_for_issue(issue, focus_result, deck_signals)
        if spec is None:
            continue  # advisory-only issue (e.g. commander_misfit, efficiency)
        synergy_first = issue["kind"] not in _SPINE_KINDS
        picked = find_add(spec, synergy_first=synergy_first)
        if picked is None:
            continue
        try:
            reason, cut = next(cut_iter)
        except StopIteration:
            break
        add_card, cost = picked
        spent += cost  # commit the spend only now that the swap is finalized
        used_adds.add(add_card.get("name", ""))
        swaps.append(
            {
                "issue": issue["kind"],
                "reason": issue["message"],
                "cut": {"name": cut.name, "why": _cut_why(reason)},
                "add": {
                    "name": add_card.get("name", ""),
                    "cmc": add_card.get("cmc", 0.0),
                    "cost": cost,
                    "owned": owned.get(add_card.get("name", ""), 0) >= 1,
                },
            }
        )

    note = None
    if len(swaps) < max_swaps:
        note = (
            f"Proposed {len(swaps)} of {max_swaps} — no further actionable issues, or "
            "out of safe cuts / affordable adds (set a Budget to allow buys)."
        )
    return {"swaps": swaps, "spent": round(spent, 2), "note": note}


# Efficiency curve issues → a CMC band to add into, scoped to the deck's main theme.
_EFFICIENCY_BANDS: dict[str, dict] = {
    "thin top-end": {"cmc_min": 6},
    "thin early game": {"cmc_max": 2},
    "top-heavy": {"cmc_max": 3},
}


def _main_avenue_search(focus_result: dict, deck_signals: list) -> dict:
    """The deck's main-theme serve spec, or an empty (identity-only) spec when none."""
    viable = focus_result["viable_avenues"]
    if viable:
        return _avenue_search_for(viable[0]["label"], deck_signals) or {}
    return {}


def _spec_for_issue(issue: dict, focus_result: dict, deck_signals: list) -> dict | None:
    kind = issue["kind"]
    if kind == "role_short":
        return _ROLE_SEARCH.get(issue["role"])
    if kind == "protection_short":
        return _PROTECTION_SEARCH
    if kind == "wincon_short":
        return _WINCON_SEARCH
    if kind == "spread_thin":
        viable = focus_result["viable_avenues"]
        if viable:
            return _avenue_search_for(viable[0]["label"], deck_signals)
        return None
    if kind == "efficiency":
        # A curve problem is fixed by adding a synergistic card at the missing CMC band
        # (a thin top-end wants a 6+ MV finisher on the deck's main theme, etc.).
        band = _EFFICIENCY_BANDS.get(issue.get("subkind", ""))
        if band is None:
            return None
        return {**_main_avenue_search(focus_result, deck_signals), **band}
    return None


def _cut_why(reason: str) -> str:
    if reason == "filler":
        return "serves no avenue here (filler)"
    if reason.startswith("over:"):
        return f"{reason.split(':', 1)[1].replace('_', ' ')} over template band"
    if reason == "stranded":
        return "stranded on a near-empty avenue"
    return reason
