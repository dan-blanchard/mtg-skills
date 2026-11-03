"""Which cards a proposal cuts: the cut queue (``cut_candidates``), size cuts,
the over-row members and the cut reasons' text (split out of ``swaps``)."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._analysis.budgets import COMMANDER_TEMPLATE, Template
from mtg_utils._tuner.card_gates import (
    _amplifies_mana,
    _is_fixing,
)
from mtg_utils._tuner.classify import CardClass, is_premium
from mtg_utils._tuner.issues import (
    cut_over,
    over_role,
)
from mtg_utils._tuner.upgrade_gates import (
    _fills_short_role,
)


def over_row_members(
    classes: Sequence[CardClass],
    role: str,
    budgets: dict,
    *,
    template: Template,
) -> list[CardClass]:
    """The Spine cards an over-band trim of ``role`` may draw from: the
    template's own membership read, never a card also filling a floor role.
    The one read ``tune``'s lane-row share and the trim itself both use, so
    the share is measured on the set that would be trimmed."""
    return [
        c
        for c in classes
        if c.bucket == "spine"
        and template.fills(role, c.record, roles=set(c.roles))
        and not _fills_short_role(c, budgets)
    ]


@dataclass(frozen=True)
class CutFocus:
    """The slice of the focus read the cut ranking needs.

    ``verdict`` is the focus verdict (``SPREAD-THIN`` trims differently);
    ``stranded`` / ``viable`` the avenue labels the deck cannot / can build, and
    ``mains`` the viable ones that are main themes; ``commander_cards`` the
    cards that do what the commander's lane does;
    ``upgrade_cards`` the off-lane cards few decks play; ``lane_upgrade_cards``
    the deep lane's least-played half, in the focus read's order (order matters).
    """

    verdict: str = "FOCUSED"
    stranded: frozenset[str] = frozenset()
    viable: frozenset[str] = frozenset()
    mains: frozenset[str] = frozenset()
    commander_cards: frozenset[str] = frozenset()
    upgrade_cards: frozenset[str] = frozenset()
    lane_upgrade_cards: tuple[str, ...] = ()
    popular_upgrade_cards: tuple[str, ...] = ()

    @classmethod
    def from_focus(cls, focus_result: dict) -> CutFocus:
        """Slice a ``focus`` result dict."""
        return cls(
            verdict=focus_result["verdict"],
            stranded=frozenset(focus_result["stranded_avenues"]),
            viable=frozenset(a["label"] for a in focus_result["viable_avenues"]),
            mains=frozenset(focus_result.get("mains") or ()),
            commander_cards=frozenset(focus_result.get("commander_lane_cards") or ()),
            upgrade_cards=frozenset(focus_result.get("upgrade_cards") or ()),
            lane_upgrade_cards=tuple(focus_result.get("lane_upgrade_cards") or ()),
            popular_upgrade_cards=tuple(
                focus_result.get("popular_upgrade_cards") or ()
            ),
        )


def cut_candidates(
    classes: Sequence[CardClass],
    *,
    budgets: dict,
    focus: CutFocus,
    protected: Collection[str] = (),
    medium: str = "paper",
    template: Template = COMMANDER_TEMPLATE,
    playrate: bool = True,
    playrate_meaningful: bool = True,
    needs: Callable[[Mapping], int] | None = None,
    tribe_member: Callable[[Mapping], bool] | None = None,
) -> list[tuple[str, CardClass]]:
    """Ordered (reason, card) cut candidates, most-cuttable first. Hard floors apply.

    ``needs`` counts the commander's needs a card supplies (``propose_swaps``'
    ``supplies_need``, every need the redundancy ones included): an over-band
    row trims a card supplying one after every member supplying none — Oracle
    of Mul Daya's extra land drops under a land-sacrificing Yuma are what the
    deck asks for, not surplus ramp (Desert Bloom, 2026-11-01). ``tribe_member``
    says the card is one of the commander's tribe (``Sourcing.tribe_spec``):
    it trims after the row's other members too — Cavalier of Thorns, an
    Elemental, went as surplus ramp under an Elemental commander whose guides
    add Cavaliers (Dance of the Elements, 2026-11-01).

    ``playrate`` is whether a fringe play-rate may CONDEMN a card
    (``Calibration.playrate_condemns`` — never in a one-on-one game);
    ``playrate_meaningful`` whether play-rate reads at all (the Commander
    family), which is what shields a premium card from a band trim: a shield
    is a quality read, not a condemnation, so it holds in a one-on-one game too.

    ``protected`` names cards the proposer must never cut (e.g. combo pieces, ADR-0029);
    they are skipped even when they would otherwise be the top filler cut. A card is
    listed once per COPY it holds (a 4-of filler may be cut four times); an over-band
    row's members are read through the ``template``'s own membership, and an
    ``advisory`` row is never a cut pool.

    ``focus.viable`` / ``focus.commander_cards`` are the focus read's built
    avenues and the cards that do what the commander's lane does
    (``commander_lane_cards``): such a card is never a low-value cut
    (play-rate says nothing about a polymorph
    piece under a polymorph commander) and trims last from an over-band row; a
    card feeding no viable avenue trims first. A payoff the lane merely serves
    (a bomb the commander flips into) is ordered like any other card.

    The last two tiers are the upgrade slots the focus read names: the
    off-lane cards few decks play (``focus.upgrade_cards``, least played first),
    drawn by the upgrade issue for a better-played card doing the same job (and,
    one that does no job, by a ``lane_ok`` remedy whose own pool is dry); then
    the deep lane's least-played half (``focus.lane_upgrade_cards``, in the focus
    read's order) — a tribal precon's forty-three Vampires are all carers, so
    with every other tier empty the deck proposed nothing while short on ramp,
    draw and wipes (Blood Rites, 2026-10-18). A lane slot is never dead weight:
    only a Spine fill, a closer, a game-ending piece or an upgrade may take it
    (``Remedy.lane_ok``; the first pass traded Dinosaurs for Human-tribal and
    Landfall "commit more" adds). Last, the popular cards serving none of the
    deck's main avenues (``focus.popular_upgrade_cards``), drawn by the
    upgrade issue only once both pools above are dry.
    """
    out: list[tuple[str, CardClass]] = []
    seen: set[str] = set()

    def premium(card: CardClass) -> bool:
        return playrate_meaningful and is_premium(card.edhrec_rank)

    def viable_served(card: CardClass) -> int:
        return len(focus.viable.intersection(card.served))

    def push(reason: str, card: CardClass) -> None:
        if card.name not in seen and card.name not in protected:
            seen.add(card.name)
            out.extend([(reason, card)] * max(1, card.quantity))

    # 1. Filler — do-nothing high-CMC before do-nothing cheap (efficiency-aware).
    # A card supplying one of the commander's needs is no do-nothing filler:
    # Evolution Sage's proliferate and Auntie Ool's -1/-1 counters went as
    # Blight Curse's dead weight (2026-11-02).
    for c in sorted(
        (
            c
            for c in classes
            if c.bucket == "filler" and not (needs is not None and needs(c.record) > 0)
        ),
        key=lambda c: c.cmc,
        reverse=True,
    ):
        push("filler", c)

    # 1b. Low-value Engine cards (``CardClass.low_value``) — upgrade targets, worst
    #     play-rate (incl. unranked) first.
    #     Never a card on the commander's own lane (the focus read exempts it too).
    for c in sorted(
        (
            c
            for c in classes
            if c.low_value(medium=medium, playrate=playrate)
            and c.name not in focus.commander_cards
            # A card supplying one of the commander's needs is no low-value
            # fodder for a fill, however few decks play it: Juniper Order
            # Ranger's counters under Bright-Palm went for a closer (Call for
            # Backup, 2026-11-02).
            and not (needs is not None and needs(c.record) > 0)
        ),
        key=lambda c: c.least_played_key,
    ):
        push("low_value", c)

    # 2. Over-band Spine excess, weakest (low synergy, high CMC) first. Never a card
    #    also filling a floor role. Dual-purpose cards are eligible (the role is over),
    #    sorted last so the least-synergistic excess goes first. Membership is the
    #    template's own read (a constructed interaction row counts a sweeper too).
    for role, b in budgets.items():
        if (
            role == "lands"
            or b["deviation"] <= 0
            or b.get("advisory")
            or b.get("lane_row")
        ):
            continue
        members = over_row_members(classes, role, budgets, template=template)
        # A premium card (``classify.PREMIUM_RANK``) is never a band trim: under
        # a tribal commander the lane holds forty cards and sorts last, which
        # left Sol Ring as the first non-lane ramp to trim for "ramp over by 3"
        # in the Veloci-Ramp-Tor precon (2026-10-18), a cut none of its upgrade
        # guides made. A row whose whole excess is premium trims nothing, and
        # that is the answer. Color-fixing ramp sorts LAST (cut redundant
        # single-purpose ramp before a dork the manabase needs), and so does a
        # card that does what the commander's lane does (a card-draw trim under
        # Jace must not pick a polymorph that also draws); then trim the
        # excess serving the FEWEST viable avenues first (a fed avenue is no
        # reason to keep a card; one on the deck's lands plan is — Desert
        # Bloom's Oracle of Mul Daya went as its least-played ramp while
        # Explore and Harrow serve nothing, 2026-11-01), then the least
        # played, then highest CMC. Before all of it, a card supplying one of
        # the commander's built needs trims last — ahead even of the fixing
        # shield, since the row is over its band and the deck keeps the rest
        # of its fixing (Oracle of Mul Daya's extra land drops under Yuma over
        # Harrow, a guide cut, 2026-11-01).
        members = [c for c in members if not premium(c)]
        members.sort(
            key=lambda c: (
                needs is not None and needs(c.record) > 0,
                tribe_member is not None and tribe_member(c.record),
                # A card filling several template roles is not the row's
                # surplus: Wrenn and Seven's ramp beside its draw and tokens
                # went as "ramp over" (Death Toll, 2026-11-02). Nor is a mana
                # doubler, which is what the ramp is for: Forsaken Monument
                # (Eldrazi Incursion) and Mana Reflection (Tricky Terrain) —
                # kept ahead of a fixing rock, which the deck has several of.
                len(c.roles) > 1 or _amplifies_mana(c),
                # A ramp piece serving a viable avenue (Awakening Zone's Spawn
                # under Ulalek) outranks a fixing rock that serves none.
                viable_served(c),
                _is_fixing(c),
                c.name in focus.commander_cards,
                c.least_played_key,
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
    if focus.verdict == "SPREAD-THIN":
        for c in sorted(
            (
                c
                for c in classes
                if c.bucket == "engine"
                and len(c.served) <= 1
                and set(c.served) & focus.stranded
            ),
            key=lambda c: c.cmc,
            reverse=True,
        ):
            push("stranded", c)

    # 4. The upgrade slots (``focus``'s ``upgrade_cards``): off every lane the
    # deck holds and played little — least played first. The upgrade issue
    # draws on them for a better-played card doing the same job; a ``lane_ok``
    # remedy takes one doing no job before a lane slot (``propose_swaps``).
    # A card supplying one of the commander's needs goes after the rest of
    # its tier: Icon of Ancestry (Sliver Swarm) and Juniper Order Ranger
    # (Call for Backup) left as a fill's cut while idle cards stayed
    # (2026-11-02).
    def supplies(c: CardClass) -> bool:
        return needs is not None and needs(c.record) > 0

    # Keeping the tribe's payoffs (Icon of Ancestry) out of these tiers
    # altogether was measured and reverted: Sliver Swarm's, Fae Dominion's
    # and Eternal Might's fringe choose-a-type cards are their upgrade pool
    # (the 25 734 / 337 → 722 / 332, held-out 572 / 261 → 562 / 257,
    # 2026-11-02).
    for c in sorted(
        (c for c in classes if c.name in focus.upgrade_cards),
        key=lambda c: (supplies(c), c.least_played_key),
    ):
        push("upgrade", c)

    # 5. The deep lane's upgrade slots (``focus``'s ``lane_upgrade_cards``:
    # its least-played half, plain feeders before carers) — the slot a Spine
    # fill, a closer, a game-ending piece or an upgrade may take.
    lane_order = {name: i for i, name in enumerate(focus.lane_upgrade_cards)}
    for c in sorted(
        (c for c in classes if c.name in lane_order),
        key=lambda c: (supplies(c), lane_order[c.name]),
    ):
        push("lane_upgrade", c)

    # 6. The last upgrade slots (``focus``'s ``popular_upgrade_cards``): cards
    # many decks play that serve none of the deck's main avenues, least
    # played first — drawn only by the upgrade issue once the slots above are
    # spent.
    popular = {name: i for i, name in enumerate(focus.popular_upgrade_cards)}
    for c in sorted(
        (c for c in classes if c.name in popular),
        key=lambda c: (supplies(c), popular[c.name]),
    ):
        push("popular_upgrade", c)

    return out


def size_cuts(
    classes: Sequence[CardClass],
    *,
    overflow: int,
    budgets: dict,
    focus: CutFocus,
    message: str,
    protected: Collection[str] = (),
    medium: str = "paper",
    eligible: Collection[str] | None = None,
    playrate_condemns: bool = True,
    playrate_meaningful: bool = True,
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
        focus=focus,
        protected=protected,
        medium=medium,
        playrate=playrate_condemns,
        playrate_meaningful=playrate_meaningful,
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


def _cut_why(reason: str, card: CardClass | None = None) -> str:
    if reason == "filler":
        if card is not None and card.served:
            # Re-bucketed by focus: it feeds avenues only, none the deck built toward.
            return "feeds only avenues nobody built toward (fed)"
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
    if reason == "lane_upgrade":
        return "a lane feeder few decks play — an upgrade's slot"
    if reason == "upgrade":
        return "off the deck's lanes and few decks play it — a staple does its job"
    if reason == "popular_upgrade":
        return "serves none of the deck's themes — a better-played card does its job"
    if reason == "mana_base":
        return (
            "a land the mana base does better without — an untapped land in its colours"
        )
    return reason
