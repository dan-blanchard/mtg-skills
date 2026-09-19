"""Cut selection + add sourcing → budgeted (cut, add) swap pairs.

Cuts: filler → over-band Spine excess → stranded Engine singletons, gated by hard
floors (never the commander, a Spine role at/below floor, lands, or a dual-purpose
card). Adds: issue-driven calls to the injected ``search_fn`` (Spine/protection fills
efficiency-first, avenue-deepening synergy-first), budget-bounded (owned = free,
no-listing never free). No new search code — the tuner is a new *caller* of the
existing search + ranking (ADR-0023).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._analysis.budgets import COMMANDER_TEMPLATE, Template
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._analysis.roles import role_of
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.issues import (
    CUT_FILLER,
    CUT_GENERIC,
    Issue,
    Sourcing,
    cut_over,
    over_role,
)
from mtg_utils.card_classify import (
    extract_price,
    get_oracle_text,
    is_basic_land,
    is_land,
)
from mtg_utils.deck import split_type_line

# Worst-possible play-rate sentinel (an unranked card sorts last on the quality axis).
_UNPLAYED = 10**9


def _popularity(card: dict) -> int:
    """edhrec_rank as a quality key (lower = more played); absent → unplayed."""
    rank = card.get("edhrec_rank")
    return rank if rank is not None else _UNPLAYED


def _quality(card: dict, *, playrate: bool) -> int:
    """The quality tiebreak between candidates of equal synergy / cost: play-rate
    where it means something (``playrate`` — edhrec_rank is a paper-EDH population,
    the Commander family's one popularity lean, by user direction), else neutral,
    so price alone breaks the tie for a 60-card or limited deck."""
    return _popularity(card) if playrate else 0


def _fills_short_role(card: CardClass, budgets: dict) -> bool:
    """True if the card fills a role already at/below its floor — cutting it would drop
    that role below the template minimum, so it is never a safe trim (e.g. don't cut the
    lone board wipe to fix interaction overflow)."""
    return any(
        budgets.get(r, {}).get("current", 0) <= budgets.get(r, {}).get("min", 0)
        for r in card.roles
    )


# Basic-land FETCH is color fixing even though the spell produces no battlefield mana
# itself (produced_mana is empty on a sorcery): a generic "basic land" search lets you
# fetch the color you need, and a multi-type land-name search (Farseek) grabs 2+ types.
# Single-type fetches ("a Forest card") are mono-color ramp, not fixing — excluded.
_LAND_FETCH_FIXING_RE = re.compile(
    r"search your library for[^.]*\bbasic land"
    r"|search your library for[^.]*"
    r"(?:plains|island|swamp|mountain|forest)[^.]*"
    r"(?:plains|island|swamp|mountain|forest)",
    re.IGNORECASE,
)


def _is_fixing(card: CardClass) -> bool:
    """A ramp source that fixes COLORS — a premium dork/rock/land-fetch the deck's mana
    base leans on (Birds of Paradise, Arcane Signet, Kodama's Reach). It reads as ramp,
    but trimming it for ramp-overflow strands the color base, so the over-band ramp cut
    sorts these LAST (cut redundant single-purpose ramp first).

    Fixing = produces ≥2 colors of battlefield mana, OR is a basic-land fetch (which
    produces no mana itself but retrieves the color the deck needs — produced_mana would
    miss it, so the worse 2-color rock was being protected while the any-basic fetcher,
    which fixes ALL the deck's colors, was cut first)."""
    produced = card.record.get("produced_mana") or []
    if len({c for c in produced if c in "WUBRG"}) >= 2:
        return True
    return bool(_LAND_FETCH_FIXING_RE.search(get_oracle_text(card.record).lower()))


def cut_candidates(
    classes: Sequence[CardClass],
    *,
    budgets: dict,
    focus_verdict: str,
    stranded: set[str],
    protected: Collection[str] = (),
    medium: str = "paper",
    template: Template = COMMANDER_TEMPLATE,
    playrate: bool = True,
) -> list[tuple[str, CardClass]]:
    """Ordered (reason, card) cut candidates, most-cuttable first. Hard floors apply.

    ``protected`` names cards the proposer must never cut (e.g. combo pieces, ADR-0029);
    they are skipped even when they would otherwise be the top filler cut. A card is
    listed once per COPY it holds (a 4-of filler may be cut four times); an over-band
    row's members are read through the ``template``'s own membership, and an
    ``advisory`` row is never a cut pool.
    """
    out: list[tuple[str, CardClass]] = []
    seen: set[str] = set()

    def push(reason: str, card: CardClass) -> None:
        if card.name not in seen and card.name not in protected:
            seen.add(card.name)
            out.extend([(reason, card)] * max(1, card.quantity))

    # 1. Filler — do-nothing high-CMC before do-nothing cheap (efficiency-aware).
    for c in sorted(
        (c for c in classes if c.bucket == "filler"),
        key=lambda c: c.cmc,
        reverse=True,
    ):
        push("filler", c)

    # 1b. Low-value Engine cards (``CardClass.low_value``) — upgrade targets, worst
    #     play-rate (incl. unranked) first.
    for c in sorted(
        (c for c in classes if c.low_value(medium=medium, playrate=playrate)),
        key=lambda c: -(c.edhrec_rank if c.edhrec_rank is not None else 10**9),
    ):
        push("low_value", c)

    # 2. Over-band Spine excess, weakest (low synergy, high CMC) first. Never a card
    #    also filling a floor role. Dual-purpose cards are eligible (the role is over),
    #    sorted last so the least-synergistic excess goes first. Membership is the
    #    template's own read (a constructed interaction row counts a sweeper too).
    for role, b in budgets.items():
        if role == "lands" or b["deviation"] <= 0 or b.get("advisory"):
            continue
        members = [
            c
            for c in classes
            if c.bucket == "spine"
            and template.fills(role, c.record, roles=set(c.roles))
            and not _fills_short_role(c, budgets)
        ]
        # Color-fixing ramp sorts LAST (cut redundant single-purpose ramp before a
        # dork the manabase needs); then trim the LEAST-PLAYED excess first (a premium
        # staple like Sol Ring must not be cut to satisfy a band — it serves no
        # thematic avenue but is the best card in the role); then fewest avenues
        # served, then highest CMC.
        members.sort(
            key=lambda c: (
                _is_fixing(c),
                -(c.edhrec_rank if c.edhrec_rank is not None else 10**9),
                len(c.served),
                -c.cmc,
            )
        )
        # Exactly the excess in COPIES: a 4-of over by two lists two cut entries,
        # not eight.
        excess = b["deviation"]
        for c in members:
            if excess <= 0:
                break
            if c.name in seen or c.name in protected:
                continue
            copies = min(excess, max(1, c.quantity))
            seen.add(c.name)
            out.extend([(cut_over(role), c)] * copies)
            excess -= copies

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


def size_cuts(
    classes: Sequence[CardClass],
    *,
    overflow: int,
    budgets: dict,
    focus_verdict: str,
    stranded: set[str],
    message: str,
    protected: Collection[str] = (),
    medium: str = "paper",
    eligible: Collection[str] | None = None,
) -> list[dict]:
    """Legality-driven cuts for an OVER-sized deck: up to ``overflow`` proposals.

    A Commander deck's minimum and maximum deck size are both 100 (CR 903.5a;
    Brawl is exactly 60 per CR 903.12d), so a deck past ``deck_size`` is never
    legal — these cuts are proposed on every Tune run, even a ``max_swaps=0``
    scorecard pass. Proposals draw from the SAME ``cut_candidates`` ranking the
    swap machinery uses (lowest-value first), so its hard floors hold for free:
    never a commander or a land (their buckets are never candidates, so the
    land floor can't be breached), never a ``protected`` card, and never a card
    filling a Spine role at/below its floor. When the safe pool runs dry the
    list comes up short of ``overflow`` rather than proposing an unsafe cut.

    ``eligible`` restricts proposals to those names (the maindeck — cutting a
    sideboard card wouldn't shrink the counted commanders+cards total).
    """
    out: list[dict] = []
    for reason, card in cut_candidates(
        classes,
        budgets=budgets,
        focus_verdict=focus_verdict,
        stranded=stranded,
        protected=protected,
        medium=medium,
    ):
        if len(out) >= overflow:
            break
        if eligible is not None and card.name not in eligible:
            continue
        out.append(
            {
                "name": card.name,
                "why": _cut_why(reason, card),
                "reason": "over:deck_size",
                "message": message,
            }
        )
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


class _GameChangerRoom:
    """How many more Game Changers the target bracket allows (ADR-0030: the proposer
    never adds one past the ceiling). ``room=None`` is no ceiling — no target bracket,
    a one-on-one game, brackets 4-5; a NEGATIVE room is a deck already over, which
    must cut its way back under before any Game Changer add. The third ledger beside
    the two purses: probed read-only, charged on commit."""

    def __init__(self, room: int | None) -> None:
        self.room = room

    def allows(self, record: dict) -> bool:
        return self.room is None or self.room > 0 or not record.get("game_changer")

    def charge(self, add: dict, cut: CardClass | None) -> None:
        """A Game Changer added spends a slot; one cut frees a slot."""
        if self.room is None:
            return
        self.room -= bool(add.get("game_changer"))
        self.room += bool(cut is not None and cut.record.get("game_changer"))


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


@dataclass(frozen=True)
class SwapContext:
    """Everything ``propose_swaps`` needs beyond the classes and the issues — the deck
    facts the scorecard already derived and the purse it may spend (ADR-0050: one
    context instead of 18 keyword arguments).

    Deck facts: ``budgets`` (the slot bands), ``focus_result``, ``deck_signals``,
    ``identity`` (the color identity the search is bounded to), ``fmt``, ``medium``,
    ``top_heavy`` (the efficiency verdict), ``protected`` (cards the proposer must
    never cut — combo pieces, at-floor closers), ``fill_slots`` (open slots an
    under-sized deck may fill with pure adds). Purse: ``owned`` (free cards),
    ``budget`` (USD; ignored when ``wildcard_budget`` is set), ``wildcard_budget``
    (digital: one wildcard of the card's rarity per add, gated per tier),
    ``max_swaps``, ``paper_only`` (restrict the search to paper-legal cards),
    ``game_changer_room`` (how many more Game Changers the target bracket allows —
    ADR-0030; ``None`` = no ceiling).
    ``search_fn`` is the injected candidate search."""

    budgets: dict
    focus_result: dict
    deck_signals: list
    search_fn: Callable[..., list[dict]]
    identity: str
    fmt: str
    paper_only: bool
    owned: Mapping[str, int]
    budget: float | None
    max_swaps: int
    top_heavy: bool
    fill_slots: int = 0
    wildcard_budget: Mapping[str, int] | None = None
    protected: Collection[str] = ()
    medium: str = "paper"
    game_changer_room: int | None = None
    # The family's template (membership for over-band cuts, the fill order) and the
    # copy model: ``max_copies`` (None = unbounded), ``available`` (a limited pool's
    # quantities — None = the whole card database), and whether play-rate is a
    # meaningful quality read here (the Commander family's paper-EDH population).
    template: Template = COMMANDER_TEMPLATE
    max_copies: int | None = 1
    available: Mapping[str, int] | None = None
    #: Whether edhrec play-rate is a meaningful quality read for this deck (the
    #: family's ``Calibration.playrate_meaningful``).
    playrate: bool = True
    #: Adds the builder rejected — never sourced, on any path (the issue loop, the
    #: dead-weight drain, the fill pass all pick through ``addable``).
    exclude: Collection[str] = ()

    def copy_ceiling(self, record: dict) -> int | None:
        """How many copies of this card the build may run: the copy limit, bounded
        by what the pool holds; ``None`` = unbounded (a basic land)."""
        if is_basic_land(record):
            return None
        ceiling = self.max_copies
        if self.available is not None:
            have = self.available.get(record.get("name", ""), 0)
            ceiling = have if ceiling is None else min(ceiling, have)
        return ceiling

    def under_ceiling(self, record: dict, copies: int) -> bool:
        """Whether ``copies`` of this card leave room for one more."""
        ceiling = self.copy_ceiling(record)
        return ceiling is None or copies < ceiling


def propose_swaps(
    classes: Sequence[CardClass],
    issues: Sequence[Issue],
    ctx: SwapContext,
) -> dict:
    """Walk the ranked issues, sourcing a (cut, add) pair per issue that carries a
    :class:`~mtg_utils._tuner.issues.Remedy`, up to ``ctx.max_swaps``. When
    ``ctx.fill_slots`` > 0 (an under-sized deck) a fill pass then adds pure adds (no
    cut) into the open slots. Returns the swaps + a note.
    See :class:`SwapContext` for the deck facts and the purse.

    Copies: a candidate stays addable while the deck's copies plus the copies this
    run already added are under its ``copy_ceiling`` — "go to four" is a swap like
    any other, and the add carries ``copy`` (the copy number it becomes). A cut
    removes ONE copy; a name may be cut as many times as it holds copies."""
    in_deck: dict[str, int] = {c.name: c.quantity for c in classes}
    # The rejected adds the LAST find_add passed over — so an issue that then found
    # nothing can say the rejection is why, instead of silently yielding its slot.
    rejected_hits: list[str] = []
    blocked_notes: list[str] = []

    def addable(card: dict) -> bool:
        name = card.get("name", "")
        if name in ctx.exclude:
            rejected_hits.append(name)
            return False  # rejected by the builder: the next-ranked candidate instead
        return ctx.under_ceiling(card, in_deck.get(name, 0) + used_adds[name])

    sourcing = Sourcing(ctx.focus_result, ctx.deck_signals, ctx.budgets)
    stranded = set(ctx.focus_result["stranded_avenues"])
    # The deck's own avenue prominence, so the candidate ranker scores DEPTH in
    # the deck's real themes (a death payoff) over BREADTH across incidental lanes
    # (a token equipment that grazes ten). Without this the count rewards splashy
    # box-tickers — the bug that surfaced Elven Bow / Hired Claw over real payoffs.
    focus_sets = {
        "viable": {a["label"] for a in ctx.focus_result["viable_avenues"]},
        "emerging": {a["label"] for a in ctx.focus_result.get("emerging", [])},
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
        budgets=ctx.budgets,
        focus_verdict=ctx.focus_result["verdict"],
        stranded=stranded,
        protected=ctx.protected,
        medium=ctx.medium,
        template=ctx.template,
        playrate=ctx.playrate,
    )
    # Route cuts into the pools a Remedy names: an over-band trim cuts from THAT over
    # role (``over:<role>``); everything else is the generic pool (filler, low-value,
    # then stranded), so a trim isn't derailed onto filler.
    pools: dict[str, list[tuple[str, CardClass]]] = {CUT_GENERIC: [], CUT_FILLER: []}
    for reason, card in cuts:
        pool = reason if over_role(reason) is not None else CUT_GENERIC
        pools.setdefault(pool, []).append((reason, card))
        # The dead-weight drain cuts filler ONLY (a separate view of the same cards);
        # the shared used_cuts guard stops it and the generic pool cutting a card twice.
        if reason in ("filler", "low_value"):
            pools[CUT_FILLER].append((reason, card))
    cut_iters = {name: iter(items) for name, items in pools.items()}
    # Copies cut so far per name: a name may be cut up to the copies it holds (each
    # pool lists it once per copy), and never more across pools.
    used_cuts: Counter[str] = Counter()

    def take_cut(pool: str) -> tuple[str, CardClass] | None:
        for reason, card in cut_iters.get(pool, iter(())):
            if used_cuts[card.name] < card.quantity:
                return reason, card
        return None

    used_adds: Counter[str] = Counter()
    game_changers = _GameChangerRoom(ctx.game_changer_room)
    swaps: list[dict] = []
    ledger: _UsdLedger | _WildcardLedger = (
        _WildcardLedger(ctx.wildcard_budget)
        if ctx.wildcard_budget is not None
        else _UsdLedger(ctx.budget)
    )
    cmc_cap = 4.0 if ctx.top_heavy else None

    # Roles already at/above their template ceiling — an add filling one would push the
    # deck OFF-template, so fixing one issue must not regress the template.
    full_roles = {r for r, b in ctx.budgets.items() if b["current"] >= b["max"]}

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
            ctx.search_fn,
            spec,
            identity=ctx.identity,
            fmt=ctx.fmt,
            paper_only=ctx.paper_only,
            cmc_cap=cmc_cap,
            limit=limit,
        )
        # A card the deck already runs stays in the pool while it may hold another
        # copy (used_adds is applied at pick time, so the memoized order holds).
        pool = [
            c for c in found if ctx.under_ceiling(c, in_deck.get(c.get("name", ""), 0))
        ]
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
                active_signals=ctx.deck_signals,
                focus_sets=focus_sets,
                deck_tribes=deck_tribes,
            )
            ranked = [
                r["card"]
                for r in sorted(
                    scored,
                    key=lambda r: (
                        -r["score"]["synergy_score"],
                        _quality(r["card"], playrate=ctx.playrate),
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
                    _quality(c, playrate=ctx.playrate),
                    extract_price(c) or 1e9,
                ),
            )
        _pool_memo[key] = ranked
        return ranked

    def _viable_served_names(cards: Sequence[dict]) -> set[str]:
        """Names among ``cards`` that serve ≥1 of the deck's VIABLE avenues —
        reuses ``rank_candidates``' own ``served`` computation (the ADR-0040
        role-fix guard below), never a second serving definition."""
        viable = focus_sets["viable"]
        if not viable or not cards:
            return set()
        scored = rank_candidates(
            list(cards),
            active_signals=ctx.deck_signals,
            focus_sets=focus_sets,
            deck_tribes=deck_tribes,
        )
        return {
            r["card"].get("name", "")
            for r in scored
            if set(r["score"]["served"]) & viable
        }

    def find_add(
        spec: dict,
        *,
        synergy_first: bool,
        nonland_only: bool = False,
        limit: int = 60,
        role_fix: bool = False,
    ) -> tuple[dict, float, bool] | None:
        """The best affordable, not-yet-used add for this spec — does NOT commit spend
        (the caller commits once a cut is secured, so an unpaired add can't inflate the
        total). Returns ``(card, cost, off_avenue_fallback)``; the third value is only
        ever True under the ``role_fix`` guard below.

        Prefers an add that does NOT overshoot an already-full Spine role (so a curve
        fix can't break the template); only falls back to an overshooting add when
        nothing cleaner is affordable. ``nonland_only`` drops lands — Spine roles count
        only nonland producers, and the fill pass reserves land slots for the land tool,
        so the ramp oracle (which matches mana-producing lands) must not pull them in.
        ``limit`` widens the candidate pool — the fill pass adds many cards per spec, so
        a 60-card page runs dry after dedup; it requests a deeper page.

        ``role_fix`` marks a Spine-band add (ADR-0040 companion): at FOCUSED verdict,
        among the non-overshooting affordable candidates, one that serves ≥1 of the
        deck's viable avenues is picked over one that serves none, whenever such a
        candidate exists — the zero-avenue pick still ships as a last resort, and the
        caller labels it via the returned flag. SPREAD-THIN / SPINE-LED and non-role-fix
        calls are untouched: the first eligible candidate in ranked order wins, exactly
        as before this guard.
        """
        ranked = _ranked_pool(
            spec, synergy_first=synergy_first, nonland_only=nonland_only, limit=limit
        )
        rejected_hits.clear()
        guard = role_fix and ctx.focus_result["verdict"] == "FOCUSED"
        fallback: tuple[dict, float] | None = None
        eligible: list[tuple[dict, float]] = []
        for card in ranked:
            if not addable(card):  # every allowed copy taken — the next best
                continue
            if not game_changers.allows(card):
                continue  # ADR-0030: never propose an add past the bracket's ceiling
            cost = ledger.acquire_cost(card, ctx.owned)
            if cost is None:
                continue
            if role_of(card) & full_roles:
                fallback = fallback or (card, cost)  # keep the best overshooting option
                continue
            if not guard:
                return card, cost, False
            eligible.append((card, cost))

        if not guard or not eligible:
            return (*fallback, False) if fallback else None
        on_avenue = _viable_served_names([c for c, _ in eligible])
        for card, cost in eligible:
            if card.get("name") in on_avenue:
                return card, cost, False
        card, cost = eligible[0]  # nothing on-avenue — labeled last resort
        return card, cost, True

    def commit(
        kind: str,
        message: str,
        reason: str,
        cut: CardClass | None,
        add_card: dict,
        cost: float,
        *,
        off_avenue: bool = False,
    ) -> None:
        # Charge only now that the swap is finalized (find_add probed read-only, so an
        # unpaired add never consumed budget — USD dollars or a wildcard, by mode).
        ledger.charge(add_card, ctx.owned, cost)
        game_changers.charge(add_card, cut)
        if cut is not None:
            used_cuts[cut.name] += 1
        add_name = add_card.get("name", "")
        used_adds[add_name] += 1
        copy_no = in_deck.get(add_name, 0) + used_adds[add_name]
        if off_avenue:
            # ADR-0040 companion: the find_add role_fix guard found no in-budget
            # candidate serving a viable avenue, so this is the labeled fallback.
            message += " (off-avenue fallback)"
        swaps.append(
            {
                "issue": kind,
                "reason": message,
                # cut is None for a fill (a pure add into an open slot, not a trade).
                "cut": (
                    {"name": cut.name, "why": _cut_why(reason, cut), "quantity": 1}
                    if cut
                    else None
                ),
                "add": {
                    "name": add_name,
                    "cmc": add_card.get("cmc", 0.0),
                    # Which copy this add becomes (1 for a card the deck lacks; a
                    # "go to four" reads as copy 4).
                    "copy": copy_no,
                    "cost": cost,
                    "owned": ctx.owned.get(add_card.get("name", ""), 0) >= 1,
                    # Rarity rides along so a digital build can show the add's wildcard
                    # cost (one wildcard of its rarity) without a second card lookup.
                    "rarity": add_card.get("rarity", ""),
                },
            }
        )

    allow_buys = (
        "set a wildcard budget to allow crafting"
        if ctx.wildcard_budget is not None
        else "set a Budget to allow buys"
    )
    for issue in issues:
        if len(swaps) >= ctx.max_swaps:
            break
        remedy = issue.remedy
        if remedy is None:
            continue  # nothing to source — the issue is the builder's to read
        # Every cut is a NONLAND (cut_candidates never trims lands), so the add must be
        # nonland too — else a theme swap silently adds a value land (e.g. Fountainport
        # on the Aristocrats lane), shifting the land count a swap is meant to
        # preserve. The mana base is the land tooling's job, not Tune's.
        swaps_for_issue = 0
        while len(swaps) < ctx.max_swaps:
            picked = find_add(
                remedy.spec,
                synergy_first=not remedy.spine,
                nonland_only=True,
                # A Spine fill ranks efficiency-first with no synergy input at all —
                # role_fix is the ADR-0040 guard that stops that path handing a
                # FOCUSED deck a staple over an in-budget on-avenue candidate.
                role_fix=remedy.spine,
            )
            if picked is None:
                if rejected_hits and not swaps_for_issue:
                    names = ", ".join(dict.fromkeys(rejected_hits))
                    blocked_notes.append(
                        f'No alternative to {names} for "{issue.message}" — '
                        f"{allow_buys}, or allow it again."
                    )
                break
            cut_entry = take_cut(remedy.cut_from)
            if cut_entry is None:
                break  # no appropriate cut for this issue — don't grab a wrong one
            reason, cut = cut_entry
            add_card, cost, off_avenue = picked
            commit(
                issue.kind,
                issue.message,
                reason,
                cut,
                add_card,
                cost,
                off_avenue=off_avenue,
            )
            swaps_for_issue += 1
            # One issue → one swap, except the dead-weight DRAIN: a deck can carry
            # several do-nothing cards, and it ranks first so the genuinely dead cards
            # go before any role trim churns a functional card.
            if not remedy.drain:
                break

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
        while (
            added < quota and fills_done < ctx.fill_slots and len(swaps) < ctx.max_swaps
        ):
            # Fill is nonland-only (land slots reserved) and pulls a DEEP page: an
            # identity-only good-stuff search is cmc-asc, so its first few hundred hits
            # are mostly CMC-0 lands — we need to page well past them to find enough
            # distinct nonland cards.
            picked = find_add(
                spec, synergy_first=synergy_first, nonland_only=True, limit=1000
            )
            if picked is None:
                break
            # Fills are pure adds (no cut), never "role-fix swaps" — role_fix
            # defaults False above, so this flag is always False here.
            add_card, cost, _off_avenue = picked
            commit(kind, msg, "", None, add_card, cost)
            added += 1
            fills_done += 1

    if ctx.fill_slots > 0:
        # Short rows in template order; a row nothing sources (lands, an advisory
        # fact, a Grant-covered role) reads None from the same Sourcing the issue
        # loop uses.
        for role, b in ctx.budgets.items():
            if b["current"] < b["min"] and sourcing.role_spec(role) is not None:
                take_fills(
                    # None for a Grant-covered role: the fill pass reads the same
                    # answer the issue loop does (ADR-0040 §1).
                    sourcing.role_spec(role),
                    b["min"] - b["current"],
                    synergy_first=False,
                    kind="fill_role",
                    msg=f"fill {role.replace('_', ' ')} toward the floor",
                )
        for e in ctx.focus_result.get("emerging", []):
            take_fills(
                sourcing.avenue(e["label"]),
                ctx.fill_slots,
                synergy_first=True,
                kind="fill_theme",
                msg=f"deepen {e['label']}",
            )
        take_fills(
            sourcing.main_avenue(),
            ctx.fill_slots,
            synergy_first=True,
            kind="fill_theme",
            msg="deepen the deck's main theme",
        )
        take_fills(
            {},
            ctx.fill_slots,
            synergy_first=True,
            kind="fill",
            msg="fill open slots with in-identity cards",
        )

    digital = ctx.wildcard_budget is not None
    raise_budget = "raise your wildcard budget" if digital else "raise the budget"
    note = None
    if ctx.fill_slots and fills_done < ctx.fill_slots:
        why = (
            "hit the max-swaps limit — raise it"
            if len(swaps) >= ctx.max_swaps
            else f"out of distinct affordable in-identity adds — {raise_budget}"
        )
        note = f"Filled {fills_done} of {ctx.fill_slots} open nonland slots ({why})."
    elif not ctx.fill_slots and len(swaps) < ctx.max_swaps:
        note = (
            f"Proposed {len(swaps)} of {ctx.max_swaps} — no further actionable issues, "
            f"or out of safe cuts / affordable adds ({allow_buys})."
        )
    if blocked_notes:
        note = " ".join(([note] if note else []) + blocked_notes)
    return {
        "swaps": swaps,
        # `spent` is always a USD float (0.0 in digital); per-tier wildcards go in
        # `wildcards_spent` (None for paper), so neither field is a union type.
        "spent": ledger.usd_spent,
        "wildcards_spent": ledger.wildcards_spent,
        "note": note,
    }


def _cut_why(reason: str, card: CardClass | None = None) -> str:
    if reason == "filler":
        return "serves no avenue here (filler)"
    if reason == "low_value":
        # ADR-0040 §2 (Fix 6): a Granter condemned by GRADE (playrate-
        # independent) must say so — "barely played" is factually wrong for
        # a well-ranked weak Granter (the cut_candidates low_value queue
        # already reads grant_grade over playrate whenever it's set).
        if card is not None and card.grant_grade == "weak":
            return "weak ability grant for its cost — upgrade target"
        return "barely played for this theme — upgrade target"
    role = over_role(reason)
    if role is not None:
        return f"{role.replace('_', ' ')} over template band"
    if reason == "stranded":
        return "stranded on a near-empty avenue"
    return reason
