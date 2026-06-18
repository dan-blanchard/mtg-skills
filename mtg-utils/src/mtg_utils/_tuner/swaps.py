"""Cut selection + add sourcing → budgeted (cut, add) swap pairs.

Cuts: filler → over-band Spine excess → stranded Engine singletons, gated by hard
floors (never the commander, a Spine role at/below floor, lands, or a dual-purpose
card). Adds: issue-driven calls to the injected ``search_fn`` (Spine/protection fills
efficiency-first, avenue-deepening synergy-first), budget-bounded (owned = free,
no-listing never free). No new search code — the tuner is a new *caller* of the
existing search + ranking (ADR-0023).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence

from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._tuner.classify import CardClass, is_fringe
from mtg_utils.card_classify import (
    extract_price,
    get_oracle_text,
    is_basic_land,
    is_land,
    is_ramp,
)
from mtg_utils.deck import split_type_line

# Worst-possible play-rate sentinel (an unranked card sorts last on the quality axis).
_UNPLAYED = 10**9


def _popularity(card: dict) -> int:
    """edhrec_rank as a quality key (lower = more played); absent → unplayed."""
    rank = card.get("edhrec_rank")
    return rank if rank is not None else _UNPLAYED


# The mana ability of these rocks is gated on board state a deck may not have (Mox Opal
# wants metalcraft, Mox Jasper a Dragon: "Activate only if you control …") — so they
# read as ramp but do nothing here. Match the gate phrase itself (not the "Activate[
# this ability]" prefix) so re-templating can't sneak one back in. Mox Amber has no such
# gate ("…among legendary creatures … you control"), so it's correctly still sourced.
_RAMP_CONDITIONAL = "only if you control"


def _reliable_ramp(card: dict) -> bool:
    """Ramp the tuner will SOURCE: a genuine producer (is_ramp — which already rejects
    mana an opponent receives, like An Offer You Can't Refuse's Treasures) whose ability
    isn't conditionally gated. The deck's existing conditional rocks still COUNT as ramp
    (is_ramp), but the tuner won't suggest one the deck can't reliably turn on."""
    return is_ramp(card) and _RAMP_CONDITIONAL not in get_oracle_text(card).lower()


_ROLE_SEARCH: dict[str, dict] = {
    # Ramp has NO theme_preset (it's detected by card_classify.is_ramp, not a matcher),
    # so it must be sourced by oracle text — mirroring is_ramp's own patterns (mana
    # production or land-fetch). Using a nonexistent "ramp" preset here previously made
    # card_search raise and 500'd /api/tune for any ramp-short deck. The "_filter" is a
    # tuner-side precision pass (applied in _ranked_pool) the coarse regex can't do — it
    # drops opponent-mana and conditionally-gated rocks the regex would let through.
    "ramp": {
        "oracle": r"add (?:\{|one mana|mana of|an amount of mana)|"
        r"search your library for [^.]*\bland",
        "_filter": _reliable_ramp,
    },
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
    """True if the card fills a role already at/below its floor — cutting it would drop
    that role below the template minimum, so it is never a safe trim (e.g. don't cut the
    lone board wipe to fix interaction overflow)."""
    return any(
        budgets.get(r, {}).get("current", 0) <= budgets.get(r, {}).get("min", 0)
        for r in card.roles
    )


def _is_fixing(card: CardClass) -> bool:
    """A ramp source that fixes COLORS (produces ≥2 colors of mana) — a premium
    dork/rock the deck's mana base leans on (Birds of Paradise, Arcane Signet). It
    reads as ramp, but trimming it for ramp-overflow strands the color base, so the
    over-band ramp cut sorts these LAST (cut redundant single-purpose ramp first)."""
    produced = card.record.get("produced_mana") or []
    return len({c for c in produced if c in "WUBRG"}) >= 2


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

    # 1b. Low-value Engine cards — feed a theme but are barely played (fringe
    #     edhrec_rank), e.g. a vanilla beater that "counts" as creature support. Upgrade
    #     targets, worst play-rate (incl. unranked) first.
    for c in sorted(
        (c for c in classes if c.bucket == "engine" and is_fringe(c.edhrec_rank)),
        key=lambda c: -(c.edhrec_rank if c.edhrec_rank is not None else 10**9),
    ):
        push("low_value", c)

    # 2. Over-band Spine excess, weakest (low synergy, high CMC) first. Never a card
    #    also filling a floor role. Dual-purpose cards are eligible (the role is over),
    #    sorted last so the least-synergistic excess goes first.
    for role, b in budgets.items():
        if role == "lands" or b["deviation"] <= 0:
            continue
        members = [
            c
            for c in classes
            if c.bucket == "spine"
            and role in c.roles
            and not _fills_short_role(c, budgets)
        ]
        # Color-fixing ramp sorts LAST (cut redundant single-purpose ramp before a
        # dork the manabase needs); then fewest avenues served, then highest CMC.
        members.sort(key=lambda c: (_is_fixing(c), len(c.served), -c.cmc))
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


_WC_TIERS: tuple[str, ...] = ("mythic", "rare", "uncommon", "common")


class _UsdLedger:
    """Paper acquisition budget: a single USD pool. Owned = free; a no-listing card is
    never free (treated as scarce); ``budget is None`` is the owned-only pass."""

    def __init__(self, budget: float | None) -> None:
        self.budget = budget
        self.spent = 0.0

    def acquire_cost(self, record: dict, owned: Mapping[str, int]) -> float | None:
        """The card's USD cost, or None when unaffordable. Read-only (the caller charges
        on commit) so probing many candidates can't inflate the running total."""
        if owned.get(record.get("name", ""), 0) >= 1:
            return 0.0
        price = extract_price(record)
        if price is None:  # no-listing: never $0
            return None
        if self.budget is None:  # owned-only pass
            return None
        return price if self.spent + price <= self.budget else None

    def charge(self, record: dict, owned: Mapping[str, int], cost: float) -> None:
        self.spent += cost

    @property
    def usd_spent(self) -> float:
        return round(self.spent, 2)

    @property
    def wildcards_spent(self) -> dict[str, int] | None:
        return None


class _WildcardLedger:
    """Digital (Arena) acquisition budget: four per-rarity wildcard pools. A card costs
    ONE wildcard of its rarity; owned cards and basic lands are free. Wildcards are NOT
    interchangeable, so each tier is gated independently — an all-zero budget is the
    owned-only pass. The swap's USD ``cost`` is 0.0 (the UI costs by rarity); ``total``
    is the per-tier wildcards spent."""

    def __init__(self, budget: Mapping[str, int]) -> None:
        self.remaining = {t: int(budget.get(t, 0)) for t in _WC_TIERS}
        self.spent = dict.fromkeys(_WC_TIERS, 0)

    def acquire_cost(self, record: dict, owned: Mapping[str, int]) -> float | None:
        """0.0 when the card is craftable within the remaining wildcard budget for its
        rarity (or free: owned / basic), else None. Read-only — commit charges."""
        if owned.get(record.get("name", ""), 0) >= 1 or is_basic_land(record):
            return 0.0
        rarity = record.get("rarity")
        if rarity not in self.remaining or self.remaining[rarity] <= 0:
            return None
        return 0.0

    def charge(self, record: dict, owned: Mapping[str, int], cost: float) -> None:
        if owned.get(record.get("name", ""), 0) >= 1 or is_basic_land(record):
            return
        rarity = record.get("rarity")
        if rarity in self.remaining:
            self.remaining[rarity] -= 1
            self.spent[rarity] += 1

    @property
    def usd_spent(self) -> float:
        return 0.0  # Arena spends wildcards, not dollars — see wildcards_spent.

    @property
    def wildcards_spent(self) -> dict[str, int]:
        return dict(self.spent)


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
    fill_slots: int = 0,
    wildcard_budget: Mapping[str, int] | None = None,
) -> dict:
    """Walk the ranked issues, sourcing a (cut, add) pair per actionable issue up to
    ``max_swaps``. When ``fill_slots`` > 0 (an under-sized deck) a fill pass then adds
    pure adds (no cut) into the open slots. Returns the swaps + a note.

    ``wildcard_budget`` (digital builds) switches costing from a single USD pool to four
    per-rarity Arena wildcard pools — a card costs one wildcard of its rarity, so an add
    is only sourced while that tier's budget holds. ``budget`` is ignored when set."""
    in_deck = {c.name for c in classes}
    stranded = set(focus_result["stranded_avenues"])
    # The deck's own avenue prominence, so the candidate ranker scores DEPTH in
    # the deck's real themes (a death payoff) over BREADTH across incidental lanes
    # (a token equipment that grazes ten). Without this the count rewards splashy
    # box-tickers — the bug that surfaced Elven Bow / Hired Claw over real payoffs.
    focus_sets = {
        "viable": {a["label"] for a in focus_result["viable_avenues"]},
        "emerging": {a["label"] for a in focus_result.get("emerging", [])},
        "stranded": stranded,
    }
    # The creature subtypes the deck actually fields, so the ranker can discount a
    # payoff gated on a tribe the deck lacks (Hired Claw's "attack with Lizards" in
    # a Lizard-less deck) without penalizing it in a deck that DOES field them.
    deck_tribes = frozenset(
        st.lower()
        for c in classes
        if "creature" in (c.record.get("type_line") or "").lower()
        for st in split_type_line(c.record.get("type_line", ""))[1]
    )
    cuts = cut_candidates(
        classes,
        budgets=budgets,
        focus_verdict=focus_result["verdict"],
        stranded=stranded,
    )
    # Route cuts: a role_over trim cuts from THAT over role; other issues draw from the
    # generic pool (filler then stranded), so a trim isn't derailed onto filler.
    over_cuts: dict[str, list[tuple[str, CardClass]]] = {}
    generic_cuts: list[tuple[str, CardClass]] = []
    for reason, card in cuts:
        if reason.startswith("over:"):
            over_cuts.setdefault(reason.split(":", 1)[1], []).append((reason, card))
        else:
            generic_cuts.append((reason, card))
    gen_iter = iter(generic_cuts)
    over_iters = {role: iter(items) for role, items in over_cuts.items()}
    # The dead-weight pass cuts filler ONLY (a separate view of the same cards); a
    # shared used_cuts guard stops it and the generic pass cutting the same card twice.
    filler_iter = iter([(r, c) for r, c in cuts if r in ("filler", "low_value")])
    used_cuts: set[str] = set()

    def _pull(it: Iterator[tuple[str, CardClass]]) -> tuple[str, CardClass] | None:
        for reason, card in it:
            if card.name not in used_cuts:
                return reason, card
        return None

    def take_cut(issue: dict) -> tuple[str, CardClass] | None:
        if issue["kind"] == "role_over":
            return _pull(over_iters.get(issue["role"], iter(())))
        return _pull(gen_iter)

    used_adds: set[str] = set()
    swaps: list[dict] = []
    ledger: _UsdLedger | _WildcardLedger = (
        _WildcardLedger(wildcard_budget)
        if wildcard_budget is not None
        else _UsdLedger(budget)
    )
    cmc_cap = 4.0 if top_heavy else None

    # Roles already at/above their template ceiling — an add filling one would push the
    # deck OFF-template, so fixing one issue must not regress the template.
    full_roles = {r for r, b in budgets.items() if b["current"] >= b["max"]}

    # Search + rank a spec ONCE per propose_swaps call, memoized. The ranked ORDER
    # depends only on in_deck (fixed), not on which cards have been used — so the fill
    # pass, which asks for the same spec repeatedly to fill many slots, reuses the pool
    # instead of re-searching + re-ranking ~1000 cards per card added (the dominant
    # redundant cost). used_adds is applied at pick time in find_add, not here.
    _pool_memo: dict[tuple, list[dict]] = {}

    def _ranked_pool(
        spec: dict, *, synergy_first: bool, nonland_only: bool, limit: int
    ) -> list[dict]:
        key = (tuple(sorted(spec.items())), synergy_first, nonland_only, limit)
        cached = _pool_memo.get(key)
        if cached is not None:
            return cached
        found = _run_search(
            search_fn,
            spec,
            identity=identity,
            fmt=fmt,
            paper_only=paper_only,
            cmc_cap=cmc_cap,
            limit=limit,
        )
        pool = [c for c in found if c.get("name") not in in_deck]
        if nonland_only:
            pool = [c for c in pool if not is_land(c)]
        spec_filter = spec.get("_filter")
        if spec_filter is not None:  # tuner-side precision pass (e.g. reliable-ramp)
            pool = [c for c in pool if spec_filter(c)]
        if synergy_first:
            # Synergy DEPTH first (synergy_score, deck-relative — a real payoff for
            # the deck's themes beats a box-ticker grazing many incidental lanes),
            # then play-rate so a staple beats the cheapest chaff that nominally
            # serves the same lane, then price. The play-rate tiebreak is the one
            # EDHREC-popularity lean (user-directed).
            scored = rank_candidates(
                pool,
                active_signals=deck_signals,
                focus_sets=focus_sets,
                deck_tribes=deck_tribes,
            )
            ranked = [
                r["card"]
                for r in sorted(
                    scored,
                    key=lambda r: (
                        -r["score"]["synergy_score"],
                        _popularity(r["card"]),
                        extract_price(r["card"]) or 1e9,
                    ),
                )
            ]
        else:
            # Spine fills: cheapest-MV does-the-job first (efficiency), then play-rate
            # so a played staple beats a fringe same-cost role-filler, then price.
            ranked = sorted(
                pool,
                key=lambda c: (
                    c.get("cmc", 0.0),
                    _popularity(c),
                    extract_price(c) or 1e9,
                ),
            )
        _pool_memo[key] = ranked
        return ranked

    def find_add(
        spec: dict, *, synergy_first: bool, nonland_only: bool = False, limit: int = 60
    ) -> tuple[dict, float] | None:
        """The best affordable, not-yet-used add for this spec — does NOT commit spend
        (the caller commits once a cut is secured, so an unpaired add can't inflate the
        total).

        Prefers an add that does NOT overshoot an already-full Spine role (so a curve
        fix can't break the template); only falls back to an overshooting add when
        nothing cleaner is affordable. ``nonland_only`` drops lands — Spine roles count
        only nonland producers, and the fill pass reserves land slots for the land tool,
        so the ramp oracle (which matches mana-producing lands) must not pull them in.
        ``limit`` widens the candidate pool — the fill pass adds many cards per spec, so
        a 60-card page runs dry after dedup; it requests a deeper page.
        """
        ranked = _ranked_pool(
            spec, synergy_first=synergy_first, nonland_only=nonland_only, limit=limit
        )
        fallback: tuple[dict, float] | None = None
        for card in ranked:
            if card.get("name") in used_adds:  # already taken — skip to the next best
                continue
            cost = ledger.acquire_cost(card, owned)
            if cost is None:
                continue
            if role_of(card) & full_roles:
                fallback = fallback or (card, cost)  # keep the best overshooting option
                continue
            return card, cost
        return fallback

    def commit(
        issue: dict, reason: str, cut: CardClass | None, add_card: dict, cost: float
    ) -> None:
        # Charge only now that the swap is finalized (find_add probed read-only, so an
        # unpaired add never consumed budget — USD dollars or a wildcard, by mode).
        ledger.charge(add_card, owned, cost)
        if cut is not None:
            used_cuts.add(cut.name)
        used_adds.add(add_card.get("name", ""))
        swaps.append(
            {
                "issue": issue["kind"],
                "reason": issue["message"],
                # cut is None for a fill (a pure add into an open slot, not a trade).
                "cut": ({"name": cut.name, "why": _cut_why(reason)} if cut else None),
                "add": {
                    "name": add_card.get("name", ""),
                    "cmc": add_card.get("cmc", 0.0),
                    "cost": cost,
                    "owned": owned.get(add_card.get("name", ""), 0) >= 1,
                    # Rarity rides along so a digital build can show the add's wildcard
                    # cost (one wildcard of its rarity) without a second card lookup.
                    "rarity": add_card.get("rarity", ""),
                },
            }
        )

    for issue in issues:
        if len(swaps) >= max_swaps:
            break
        # Dead weight: drain filler, replacing each with the best on-theme / role card.
        # One issue → many swaps (a deck can carry several do-nothing cards), so this is
        # the only multi-swap branch — and it runs first (top severity) so the genuinely
        # dead cards go before any role trim churns a functional card.
        if issue["kind"] == "dead_weight":
            spec = _dead_weight_spec(focus_result, deck_signals, budgets)
            if spec is None:
                continue
            while len(swaps) < max_swaps:
                cut_entry = _pull(filler_iter)
                if cut_entry is None:
                    break
                picked = find_add(spec, synergy_first=True, nonland_only=True)
                if picked is None:
                    break
                reason, cut = cut_entry
                add_card, cost = picked
                commit(issue, reason, cut, add_card, cost)
            continue

        spec = _spec_for_issue(issue, focus_result, deck_signals)
        if spec is None:
            continue  # advisory-only issue (e.g. commander_misfit, efficiency)
        synergy_first = issue["kind"] not in _SPINE_KINDS
        # Every cut here is a NONLAND (cut_candidates never trims lands), so the add
        # must be nonland too — else a theme swap silently adds a value land (e.g.
        # Fountainport on the Aristocrats lane), shifting the land count a swap is
        # meant to preserve. The mana base is the land tooling's job, not Tune's.
        picked = find_add(spec, synergy_first=synergy_first, nonland_only=True)
        if picked is None:
            continue
        cut_entry = take_cut(issue)
        if cut_entry is None:
            continue  # no appropriate cut for this issue — skip, don't grab a wrong one
        reason, cut = cut_entry
        add_card, cost = picked
        commit(issue, reason, cut, add_card, cost)

    # Fill pass — grow an under-sized deck toward target with PURE ADDS (no cut). The
    # swap loop above is cut-bound (every move trades a card), so a partially-built deck
    # with open slots never grows. Here we add into the open slots, prioritised by the
    # same needs: short Spine roles to floor → emerging/main themes → in-identity good
    # stuff. Lands are out of scope (the mana base is the land tooling's job).
    fills_done = 0

    def take_fills(
        spec: dict | None, quota: int, *, synergy_first: bool, kind: str, msg: str
    ) -> None:
        nonlocal fills_done
        if spec is None:
            return
        added = 0
        while added < quota and fills_done < fill_slots and len(swaps) < max_swaps:
            # Fill is nonland-only (land slots reserved) and pulls a DEEP page: an
            # identity-only good-stuff search is cmc-asc, so its first few hundred hits
            # are mostly CMC-0 lands — we need to page well past them to find enough
            # distinct nonland cards.
            picked = find_add(
                spec, synergy_first=synergy_first, nonland_only=True, limit=1000
            )
            if picked is None:
                break
            add_card, cost = picked
            commit({"kind": kind, "message": msg}, "", None, add_card, cost)
            added += 1
            fills_done += 1

    if fill_slots > 0:
        for role in ("ramp", "card_draw", "interaction", "board_wipe"):
            b = budgets.get(role)
            if b and b["current"] < b["min"]:
                take_fills(
                    _ROLE_SEARCH[role],
                    b["min"] - b["current"],
                    synergy_first=False,
                    kind="fill_role",
                    msg=f"fill {role.replace('_', ' ')} toward the floor",
                )
        for e in focus_result.get("emerging", []):
            take_fills(
                _avenue_search_for(e["label"], deck_signals),
                fill_slots,
                synergy_first=True,
                kind="fill_theme",
                msg=f"deepen {e['label']}",
            )
        take_fills(
            _main_avenue_search(focus_result, deck_signals),
            fill_slots,
            synergy_first=True,
            kind="fill_theme",
            msg="deepen the deck's main theme",
        )
        take_fills(
            {},
            fill_slots,
            synergy_first=True,
            kind="fill",
            msg="fill open slots with in-identity cards",
        )

    digital = wildcard_budget is not None
    raise_budget = "raise your wildcard budget" if digital else "raise the budget"
    allow_buys = (
        "set a wildcard budget to allow crafting"
        if digital
        else "set a Budget to allow buys"
    )
    note = None
    if fill_slots and fills_done < fill_slots:
        why = (
            "hit the max-swaps limit — raise it"
            if len(swaps) >= max_swaps
            else f"out of distinct affordable in-identity adds — {raise_budget}"
        )
        note = f"Filled {fills_done} of {fill_slots} open nonland slots ({why})."
    elif not fill_slots and len(swaps) < max_swaps:
        note = (
            f"Proposed {len(swaps)} of {max_swaps} — no further actionable issues, or "
            f"out of safe cuts / affordable adds ({allow_buys})."
        )
    return {
        "swaps": swaps,
        # `spent` is always a USD float (0.0 in digital); per-tier wildcards go in
        # `wildcards_spent` (None for paper), so neither field is a union type.
        "spent": ledger.usd_spent,
        "wildcards_spent": ledger.wildcards_spent,
        "note": note,
    }


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


def _dead_weight_spec(
    focus_result: dict, deck_signals: list, budgets: dict
) -> dict | None:
    """Where to redeploy a dead-weight card: deepen the deck's main theme if it has one,
    else fill the worst-short Spine role. None when neither exists (nothing better to
    add than the filler being replaced, so don't churn)."""
    main = _main_avenue_search(focus_result, deck_signals)
    if main:
        return main
    short = sorted(
        (
            (r, b)
            for r, b in budgets.items()
            if b.get("deviation", 0) < 0 and r in _ROLE_SEARCH
        ),
        key=lambda kv: kv[1]["deviation"],
    )
    return _ROLE_SEARCH[short[0][0]] if short else None


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
    if kind == "under_supported_theme":
        # "Commit" to the emerging theme: add more cards that feed it.
        return _avenue_search_for(issue["label"], deck_signals)
    if kind == "role_over":
        # Trim the excess: the cut comes from the over role (routed in propose_swaps).
        # The add deepens an under-supported emerging theme if any (commit while
        # trimming), else the main theme. find_add's full-role filter keeps it from
        # re-filling the role being trimmed.
        emerging = focus_result.get("emerging", [])
        if emerging:
            spec = _avenue_search_for(emerging[0]["label"], deck_signals)
            if spec is not None:
                return spec
        return _main_avenue_search(focus_result, deck_signals)
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
    if reason == "low_value":
        return "barely played for this theme — upgrade target"
    if reason.startswith("over:"):
        return f"{reason.split(':', 1)[1].replace('_', ' ')} over template band"
    if reason == "stranded":
        return "stranded on a near-empty avenue"
    return reason
