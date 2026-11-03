"""Cut selection + add sourcing → budgeted (cut, add) swap pairs.

Cuts: filler → low-value → over-band Spine excess → stranded Engine singletons →
the upgrade slots (off-lane cards few decks play, then a deep lane's least-played
half, then popular cards on none of the deck's main avenues), gated by hard
floors (never the commander, a Spine role at/below floor, lands, or a
dual-purpose card). Adds: issue-driven calls to the injected
``search_fn`` (Spine/protection fills by play-rate within a mana-value band,
avenue-deepening and upgrades by fit then play-rate), budget-bounded (owned =
free, no-listing never free). No new search code — the tuner is a new *caller* of the
existing search + ranking (ADR-0023).

The swap loop (``propose_swaps``) and its page searches live here; its parts
are their own modules, re-exported here so every old import path holds:
``purse`` (the budget ledgers), ``card_gates`` (the deck profile and the
dead-add gates), ``upgrade_gates`` (``_upgrades`` and the job reads'
downgrade gates), ``cuts`` (the cut queue) and ``recheck`` (the proposal
read whole: unfuelled adds and their cuts' re-picks).
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass

from mtg_utils._analysis.budgets import COMMANDER_TEMPLATE, Template
from mtg_utils._analysis.commander_need import (
    Need,
    is_broad,
    need_serve,
    satisfies,
    typal_payoff_for,
)
from mtg_utils._analysis.job_quality import JobRead, read_for
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._analysis.roles import DeckMana, protects, role_of
from mtg_utils._analysis.signal_specs import (
    pages_by_serve,
    serve_page_search,
    theme_page,
)
from mtg_utils._tuner import mana_base
from mtg_utils._tuner.card_gates import (  # noqa: F401 — re-exported: the old import path
    _ATTRACTION_GATE,
    _COLOR_LETTERS,
    _COUNTER_GATE_FEEDERS,
    _COUNTERS_GATE,
    _CREATURE_SUBTYPE_WORDS,
    _CREATURE_TOKENS_GATE,
    _DEPENDENT_EFFECT_TAGS,
    _DEPENDENT_TARGET_TAGS,
    _FEEDER_FLOOR,
    _GATE_TYPE_WORDS,
    _GENERIC_TYPE_WORDS,
    _LAND_TYPE_WORDS,
    _LIBRARY_EFFECTS,
    _LIFE_GATE,
    _MANA_DOUBLER_KEYS,
    _MULTIPLIER_FEEDER_FLOOR,
    _MULTIPLIER_KEYS,
    _NON_PREFIX,
    _OPP_DISCARD_FEEDERS,
    _OPP_DISCARD_GATE,
    _SELF_MILL_SHARE,
    _TOKENS_GATE,
    _TOKENS_GATE_FEEDERS,
    _TYPE_GATE_FLOOR,
    _YOU_DISCARD_FEEDERS,
    _YOU_DISCARD_GATE,
    _ability_gate_words,
    _affects_creatures,
    _amplifies_mana,
    _biggest_choosable_tribe,
    _choosable_types,
    _chosen_type_on_battlefield,
    _commander_already_grants,
    _counted_gate_words,
    _Gate,
    _gate_words,
    _is_fixing,
    _kinship_words,
    _mills_only_opponents,
    _self_mill_deck,
    _Tribes,
    _trigger_effect_gate_words,
    _unit_gates,
    _UnitGates,
    chooses_a_type_without_tribe,
    dead_payoff,
    deck_profile,
    gated_without_feed,
    statics_of,
)
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.cuts import (  # noqa: F401 — re-exported: the old import path
    CutFocus,
    _cut_why,
    cut_candidates,
    over_row_members,
    size_cuts,
)
from mtg_utils._tuner.issues import (
    CUT_FILLER,
    CUT_GENERIC,
    CUT_LANE,
    CUT_UPGRADE,
    CUT_UPGRADE_JOBLESS,
    CUT_UPGRADE_POPULAR,
    FLIP_SLOT,
    UPGRADE_ROLE_ORDER,
    Issue,
    Sourcing,
    UpgradeSource,
    is_flip,
    over_role,
    polymorph_flip_types,
    upgrade_job,
)
from mtg_utils._tuner.mana_base import LandPlan
from mtg_utils._tuner.purse import (  # noqa: F401 — re-exported: the old import path
    _WC_TIERS,
    _GameChangerRoom,
    _Purse,
    _UsdLedger,
    _WildcardLedger,
)
from mtg_utils._tuner.recheck import (  # noqa: F401 — re-exported: the old import path
    _FUELED_JOBS,
    _REPICK_TRIES,
    _next_fueled_add,
    _unfueled_adds,
)
from mtg_utils._tuner.upgrade_gates import (  # noqa: F401 — re-exported: the old import path
    _C_SOURCES_PER_PIP,
    _CHEAPER_TIE,
    _DECK_FIT_FLOOR,
    _FIXING_COLORS,
    _GRANT_GRADES,
    _JOB_BAND_ROOM,
    _MV_BANDS,
    _TEMPO_FLOOR,
    _THEME_TIE,
    _X_COST_VALUE,
    _blended_percentiles,
    _bounces_for_a_kill,
    _color_count,
    _cost_band,
    _does_the_job,
    _fills_short_role,
    _grant_grade_of,
    _job_cost,
    _lateral_at_the_job,
    _mv_band,
    _near_tie,
    _one_shot_for_an_engine,
    _one_shot_for_repeatable,
    _one_shot_mana,
    _pays_a_sacrifice_more,
    _reads_worse_at_the_job,
    _spares_less_of_the_deck,
    _stops_land_plays,
    _sweeps_fewer_kinds,
    _sweeps_no_creatures,
    _upgrades,
    _weaker_on_its_text,
    flip_floor_band,
    over_band,
)
from mtg_utils.card_classify import (
    extract_price,
    is_basic_land,
    is_creature,
    is_land,
)
from mtg_utils.card_search import edhrec_popularity
from mtg_utils.deck import split_type_line
from mtg_utils.formats import Coverage, Format


# Worst-possible play-rate sentinel (an unranked card sorts last on the quality axis).
def _quality(card: dict, *, playrate: bool) -> int:
    """The quality tiebreak between candidates of equal synergy / cost: play-rate
    where it means something (``playrate`` — edhrec_rank is a paper-EDH population,
    the Commander family's one popularity lean, by user direction), else neutral,
    so price alone breaks the tie for a 60-card or limited deck."""
    return edhrec_popularity(card) if playrate else 0


#: The job a Spine issue fills when it is not its row's role.
_SPINE_JOBS = {"protection_short": "protection"}

#: An upgrade's search reads the role's whole match set when the job has a card
#: read (``job_quality``), not a play-rate page: a page let popularity pick the
#: candidates the read then gates and orders, five-colour removal outran the
#: 600-card page this replaced, and the blend's percentiles moved with the
#: page's depth. Deeper than any match set; the search slices its sorted matches.
_JOB_READ_PAGE = sys.maxsize
#: The search page an add is ranked from otherwise.
_PAGE = 150
#: The most of a type- or preset-searched theme's adds that may come from its
#: serve's broader page — support that is not of the type (a tribe's Urza's
#: Incubator, Goad's attack payoffs): one in five, never the first. The search
#: by type keeps the tribe's own members (``signal_specs.pages_by_serve``);
#: uncapped, the generic tribal support outplays them. Measured on the 25
#: precons (2026-10-24, alone against a913f172's 434 swaps / 168 guide-matching
#: cuts / 50 guide-matching adds): one in five 436 / 170 / 51 (Aurelia, the Law
#: Above under Goad); one in three 442 / 171 / 49 and one in two 441 / 171 / 47,
#: Herald's Horn and Roaming Throne taking Fae Dominion's and Sliver Swarm's
#: budget from their own members.
_SUPPORT_SHARE = 0.2

#: The head of an upgrade's order the theme tie reorders: the avenue read runs
#: on these cards only, and a pick rarely reaches past them.
_THEME_TIE_WINDOW = 300

#: The most of what is left of the budget one upgrade's add may take, past the
#: even share (``find_add``): Multiverse Reforged's $29 Solphim for Skrelv's Hive,
#: with $29.60 left and nine swaps open, ended its tune at 25 swaps. Measured on
#: the 25 precons (2026-10-30, against 720 swaps / 332 guide cuts / 117 guide adds,
#: held-out 290 / 139 / 37), alone: 732 / 334 / 119, held-out 297 / 139 / 37,
#: Multiverse Reforged 30 / 14 / 2 (it lost Nezahal, which its fodder trims win
#: back). With them: 0.5 736 / 336 / 123 but held-out adds 36 (Cavalry Charge's
#: Black Market Connections); 0.6 732 / 335 / 121, held-out 297 / 139 / 37; 0.75
#: 726 / 334 / 120, held-out 297 / 139 / 37. An Arena deck's even share is
#: unbounded, so no wildcard add is past it.
_PURSE_CAP = 0.6

#: The most of a polymorph deck's flips (:func:`is_flip`) that may sit under
#: its flip floor (:func:`flip_floor_band`) once a fodder creature is added
#: (``find_add``): one in four. A creature that makes a token every turn is
#: fodder (``signal_specs`` ``wants_fodder``, Dan's call 2026-11-01), and every
#: creature card in the library is also what the polymorph reveals, so without
#: a bound the fodder page's creature makers took thirteen of Dan's Jace tune's
#: twenty adds beside eleven bombs cut: two flips in three a two-drop. One in
#: four is this lane's own line, no rule's.
_WHIFF_SHARE = 0.25

#: The most adds completing a combo on the SAME deck card one tune proposes:
#: Blood Rites took five (Sanguine Bond, Vito, Enduring Tenacity, Marauding
#: Blight-Priest, Aetherflux Reservoir), every one a partner for Exquisite
#: Blood, where its guides add two. A second partner is redundancy; a third is
#: the same slot again (2026-11-01).
_COMBO_PIECE_ADDS = 2

#: How many deck cards must supply one of the commander's specific needs
#: (``commander_need``) for the need to order a theme page and gate an upgrade
#: (``propose_swaps``' ``built_needs``): the focus read's emerging floor, about
#: five per hundred. Below it the need is a mention, not the plan.
_NEED_BUILT_FLOOR = 5

#: How many candidates past the first pick the near tie looks at.
_CHEAPER_WINDOW = 10
#: On a theme page under a TIGHT purse — an even share under ``_TIGHT_SHARE``
#: a swap, below what a played staple costs — the window reaches further for
#: the cheaper near tie: Counter Intelligence's $40 (a $1.35 share) went on
#: Walking Ballista and Thought Vessel with Contagion Clasp and Core Prowler
#: past the tenth candidate, and the tune ran dry at 24 swaps. Widened for
#: every purse it traded Pantlaza's Etali for Tyrranax Rex on a $286 budget
#: and moved his ramp slots onto cheap Dinosaurs (2026-11-02).
_CHEAPER_WINDOW_THEME = 40
_TIGHT_SHARE = 2.0

#: Spine-fill jobs exempt from the ADR-0040 avenue guard (``find_add``'s
#: ``role_fix``): protection guards the deck's threats whatever avenue they are
#: on, so a protection card serving an avenue is no better a fill. Under the guard
#: Animated Army's "protection short" fill was the $36 Sword of Feast and Famine
#: (it serves Combat) over Swiftfoot Boots, the guides' add and the most-played
#: protection card (2026-10-23).
_GUARD_EXEMPT_JOBS = frozenset({"protection"})


def search_key(spec: Mapping[str, object]) -> tuple:
    """What :func:`_run_search` reads of ``spec`` — its public keys and its
    ``_serve`` — as a memo key: two specs that differ only in what the tuner does
    with the page after (a ``_filter``, the ``_avenue`` it is credited to) are one
    search."""
    return tuple(
        sorted(
            (k, v) for k, v in spec.items() if not k.startswith("_") or k == "_serve"
        )
    )


def _run_search(
    search_fn: Callable[..., list[dict]],
    spec: dict,
    *,
    identity: str,
    fmt: str,
    paper_only: bool,
    cmc_cap: float | None,
    limit: int,
    playrate: bool = False,
) -> list[dict]:
    # A spec may carry its own cmc band (a thin-top-end fix wants cmc_min 6); combine
    # its ceiling with the top-heavy cap so both hold.
    #
    # The page is the candidate POOL the ranking below sees, so what it is sorted
    # by decides what can be proposed at all. Paged cheapest-mana-value first, a
    # broad serve ("Enchantments", "Artifacts") filled its 60 slots with the
    # cheapest chaff that matched — Genju of the Fields, Clown Car, Bog Rats, the
    # Class enchantments — and across 25 precons (2026-10-18) three of 77 adds
    # matched any upgrade article. Where play-rate means something (the Commander
    # family: ``Calibration.playrate_meaningful``) the page is the most-played
    # matches instead; synergy still ranks within it.
    #
    # A theme searched by an oracle pattern (or by nothing of its own) pages the
    # cards its ``Serve`` admits instead — ``signal_specs.theme_page``, the page
    # deck-forge's Find reads too. A search by card type or preset alone stays.
    spec_max = spec.get("cmc_max")
    if cmc_cap is None:
        cmc_max = spec_max
    elif spec_max is None:
        cmc_max = cmc_cap
    else:
        cmc_max = min(spec_max, cmc_cap)
    page, serve = theme_page(spec, spec.get("_serve"))
    return search_fn(
        color_identity=spec.get("color_identity") or identity,
        exact_colors=False,
        oracle=page.get("oracle"),
        card_type=page.get("card_type"),
        name=spec.get("name"),
        cmc_min=spec.get("cmc_min"),
        cmc_max=cmc_max,
        price_min=None,
        price_max=None,
        format=fmt,
        paper_only=paper_only,
        preset_names=tuple(spec.get("preset_names") or ()),
        any_preset_names=tuple(spec.get("any_preset_names") or ()),
        is_commander_filter=False,
        sort="edhrec-asc" if playrate else "cmc-asc",
        limit=limit,
        offset=0,
        serve=serve,
    )


#: How many cards a commander need wants in the deck: the frameworks' redundancy
#: of the commander's key effect (about eight to twelve). A need page's depth is
#: what is still owed toward it, so a thin need asks before a well-stocked one.
_NEED_TARGET = 12
#: The most adds one need page takes from the SHARED theme adds in a tune. Zero:
#: a need page is reached through a cut that itself supplies the need
#: (``Sourcing.upgrade_spec``: a weak Aura's slot goes to a better Aura, a cut
#: surveil card's to a better surveil outlet), never by taking a main's slot.
#: Measured on the 2026-10-30 Phase A baseline (the 25: 732 swaps / 335 guide
#: cuts / 121 guide adds; held-out 20: 571 / 253 / 80): routing alone 731 / 335 /
#: 123 and 570 / 252 / 86, consensus adds +2 and +6, page recall@30 +20 and
#: +29; one shared add per need page 738 / 334 / 114 and 568 / 252 / 78; three
#: 739 / 331 / 109 and 573 / 253 / 76 — the shared adds displaced the mains'
#: guide hits.
_NEED_CAP = 0


def need_avenues(
    needs: Sequence[Need],
    deck_records: Sequence[dict],
    identity_pool: Sequence[dict],
) -> list[tuple[str, int, dict]]:
    """The commander's need pages (ADR-0061): for each need at most
    ``BROAD_SHARE`` of the identity's nonland pool supplies, an avenue — its
    label, its depth (what the deck still owes toward ``_NEED_TARGET``) and a
    spec carrying the page (``_page``: the pool's suppliers in the pool's own
    order, play-rate) and the need's serve. A broad need (every instant under a
    spellslinger) opens no page: the mains hold those."""
    # The pool's idents from the persisted signals index (a no-op without a
    # bulk: a small test pool reads them live).
    try:
        from mtg_utils.bulk_loader import default_bulk_path
        from mtg_utils.theme_presets import seed_signal_key_index

        seed_signal_key_index(default_bulk_path())
    except Exception:  # noqa: BLE001 - no bulk configured
        pass
    nonland_pool = [c for c in identity_pool if not is_land(c)]
    deck_nonland = [r for r in deck_records if not is_land(r)]
    # One pass over the pool, every need per card (the idents and type words
    # are read once per card inside ``satisfies``' memos).
    pages: list[list[dict]] = [[] for _ in needs]
    for card in nonland_pool:
        for i, need in enumerate(needs):
            if satisfies(card, need):
                pages[i].append(card)
    out: list[tuple[str, int, dict]] = []
    for need, page in zip(needs, pages, strict=True):
        if not page or is_broad(need, len(page) / max(1, len(nonland_pool))):
            continue
        have = sum(satisfies(r, need) for r in deck_nonland)
        label = f"{need.label} (commander need)"
        spec = {
            "_serve": need_serve(need),
            "_avenue": label,
            "_page": page,
            "_need": need,
            "_cap": _NEED_CAP,
        }
        # Deep as a main is deep (the deck's commitment to the need), and never
        # shallower than what the deck still owes toward the target: a thin
        # need asks early, a built one keeps asking.
        out.append((label, max(have, _NEED_TARGET - have, 1), spec))
    return out


def need_pages(
    needs: Sequence[Need],
    deck_records: Sequence[dict],
    *,
    search_fn: Callable[..., list[dict]],
    identity: str,
    fmt: str,
    paper_only: bool,
) -> list[tuple[str, int, dict]]:
    """The commander's need pages for a tune (:func:`need_avenues` over one
    identity-wide search in its play-rate order); empty with no needs."""
    if not needs:
        return []
    identity_pool = _run_search(
        search_fn,
        {},
        identity=identity,
        fmt=fmt,
        paper_only=paper_only,
        cmc_cap=None,
        limit=sys.maxsize,
        playrate=True,
    )
    return need_avenues(needs, deck_records, identity_pool)


def land_pool(
    *,
    search_fn: Callable[..., list[dict]],
    identity: str,
    fmt: str,
    paper_only: bool,
) -> list[dict]:
    """Every land in the deck's identity, in play-rate order (the mana-base
    pass's candidates, ``mana_base.land_candidates``)."""
    return _run_search(
        search_fn,
        {"card_type": "Land"},
        identity=identity,
        fmt=fmt,
        paper_only=paper_only,
        cmc_cap=None,
        limit=sys.maxsize,
        playrate=True,
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
    #: The Shape's protection target where it wants protection (ADR-0024), else
    #: 0 — the most protection the deck wants, as a template row's max is.
    protection_target: int = 0
    #: The protection the deck holds (the scorecard's count), against that target.
    protection_count: int = 0
    #: Whether the commander is a repeatable draw engine
    #: (``classify.commander_draws``): a candidate's grant is graded as the
    #: deck's own Granters are (ADR-0040 §2).
    draw_engine_commander: bool = False
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
    #: family's ``Calibration.playrate_meaningful``): the tiebreak between adds.
    playrate: bool = True
    #: Whether a fringe play-rate may mark a card a cut target
    #: (``Calibration.playrate_condemns`` — never in a one-on-one game).
    playrate_condemns: bool = True
    #: Adds the builder rejected — never sourced, on any path (the issue loop, the
    #: dead-weight drain, the fill pass all pick through ``addable``).
    exclude: Collection[str] = ()
    #: The deck context ramp is judged in (``hd.deck_mana``): a rock whose mana
    #: is dead under this commander is never sourced as ramp.
    deck_mana: DeckMana | None = None
    #: The commander's own idents and the deck cards emitting each ident
    #: (``read_deck_signals``): what :meth:`issues.Sourcing.multiplier_avenue`
    #: reads the commander's token output from.
    commander_idents: Collection[tuple[str, str, str]] = ()
    emitters: Mapping[tuple[str, str, str], Collection[str]] | None = None
    #: The commander's need pages (:func:`need_pages`, ADR-0061), built once by
    #: ``tune`` so the issue remedies and the swap engine read the same pages.
    need_avenues: Sequence[tuple[str, int, dict]] = ()
    #: Every need the commander's text reads (``commander_needs``), the broad
    #: ones the pages skip included: an upgrade keeps the needs its cut
    #: supplies (``_upgrades``). Empty: the pages' needs are every need.
    needs: Sequence[Need] = ()
    #: The commanders' records: a power-bound sweep that kills one is no
    #: one-sided sweep in its deck (:func:`_spares_less_of_the_deck`).
    commanders: Sequence[Mapping] = ()
    #: The mana-base plan (``mana_base.land_plan``, Phase C of the 2026-10-30
    #: plan) and the identity's lands in play-rate order: the land swaps made
    #: first, within their own purse. ``None``: no land swaps.
    land_plan: LandPlan | None = None
    land_pool: Sequence[dict] = ()

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
    removes ONE copy; a name may be cut as many times as it holds copies.

    A full job moves onto the theme: when the deck holds the most of an upgrade's
    job it wants (a template row at its max, or the Shape's protection target),
    the cut's slot goes to the theme's add instead, if that costs no more than
    the job's add (or, with none, fits the even share). The template's ceiling
    says another card of the role adds nothing, so the slot is better spent on
    the theme; the row stays in its band. Measured on the 25 precons
    (2026-10-26, a screen against 711 swaps / 264 guide-matching cuts / 81
    guide-matching adds): 710 / 265 / 86 for the template rows (Living Energy's
    Izzet Generatorium, Roil Cartographer, Motherlode and Blaster Hulk for its
    off-theme draw, Enduring Enchantments' Wild Growth and Utopia Sprawl for
    its ramp), 88 with protection (Blame Game). Any row still above its floor
    took 9 adds more but spent the budget's cuts (four fewer); the theme's add
    held to the even share instead of the job's cost, 4 adds and a cut fewer;
    with no cost bar, 13 cuts fewer.

    A Spine fill, a closer or a game-ending piece (``Remedy.lane_ok``) whose own
    pool is dry takes an off-lane upgrade slot that does no job before a lane
    slot: the upgrade issue would trade that card for a theme card anyway, and
    the off-lane slots are guide cuts more often than the lane's (0.39 against
    0.28). Measured on the 25 precons (2026-10-26): one guide add more (Multiverse
    Reforged's Swiftfoot Boots), cuts flat."""
    in_deck: dict[str, int] = {c.name: c.quantity for c in classes}
    # The deck's records, for a job read's deck fit (an engine's fuel).
    # The counted deck, one record per copy (a 60-card deck's four Lightning
    # Bolts are four of its spells), read by the job reads' deck fit.
    deck_records = tuple(c.record for c in classes for _ in range(max(1, c.quantity)))
    # The rejected adds the LAST find_add passed over — so an issue that then found
    # nothing can say the rejection is why, instead of silently yielding its slot.
    rejected_hits: list[str] = []
    blocked_notes: list[str] = []

    # Adds the whole-proposal recheck dropped (:func:`_unfueled_adds`): never
    # re-picked for the cut they leave.
    unfueled: set[str] = set()

    def addable(card: dict) -> bool:
        name = card.get("name", "")
        if name in unfueled:
            return False
        if name in ctx.exclude:
            rejected_hits.append(name)
            return False  # rejected by the builder: the next-ranked candidate instead
        return ctx.under_ceiling(card, in_deck.get(name, 0) + used_adds[name])

    sourcing = Sourcing(
        ctx.focus_result,
        ctx.deck_signals,
        ctx.budgets,
        commander_idents=ctx.commander_idents,
        emitters=ctx.emitters,
        need_avenues=ctx.need_avenues,
    )
    cut_focus = CutFocus.from_focus(ctx.focus_result)
    # What a polymorph commander's fodder is (``find_add``'s job upgrades), what
    # it flips into and the band a flip added must reach (``find_add``).
    fodder = sourcing.fodder_spec()
    fodder_serve = fodder["_serve"] if fodder else None
    flip_types = polymorph_flip_types(ctx.commander_idents)
    flip_floor = flip_floor_band(deck_records, flip_types)

    def below_floor(record: Mapping) -> bool:
        """A flip under the deck's flip floor: a whiff beside its bombs."""
        return (
            flip_floor is not None
            and is_flip(record, flip_types)
            and _mv_band(record) < flip_floor
        )

    # The deck's flips, and how many sit under the floor (``_WHIFF_SHARE``);
    # ``commit`` moves both with each swap.
    flip_count = sum(1 for r in deck_records if is_flip(r, flip_types))
    # The deck's colorless sources: an add asking {C} pips is cast off them
    # (:data:`_C_SOURCES_PER_PIP`).
    colorless_sources = sum(
        1 for r in deck_records if "C" in (r.get("produced_mana") or ())
    )
    low_flips = sum(1 for r in deck_records if below_floor(r))
    # The deck's own avenue prominence, so the candidate ranker scores DEPTH in
    # the deck's real themes (a death payoff) over BREADTH across incidental lanes
    # (a token equipment that grazes ten). Without this the count rewards splashy
    # box-tickers — the bug that surfaced Elven Bow / Hired Claw over real payoffs.
    focus_sets = {
        "viable": cut_focus.viable,
        "emerging": {a["label"] for a in ctx.focus_result.get("emerging", [])},
        "stranded": cut_focus.stranded,
    }
    # The creature subtypes the deck actually fields, so the ranker can discount a
    # payoff gated on a tribe the deck lacks (Hired Claw's "attack with Lizards" in
    # a Lizard-less deck) without penalizing it in a deck that DOES field them.
    deck_tribes = frozenset(
        st.lower()
        for c in classes
        if is_creature(c.record)
        for st in split_type_line(c.record.get("type_line", ""))[1]
    )
    # What the deck does, for the dead-payoff read (:func:`dead_payoff`): a
    # theme add that cares about a mechanic the deck lacks is no add — Banner
    # of Kinship and Coat of Arms on Bello's artifact page, Hardened Scales
    # on Anikthea's enchantments (2026-11-02). Read once per card.
    deck_keys, deck_tribe_counts, deck_type_counts = deck_profile(classes)
    # A deck that plays extra lands or pays off landfall takes no add that
    # stops it playing lands (:func:`_stops_land_plays`).
    plays_lands = (
        deck_keys.get("extra_land_drop", 0) + deck_keys.get("landfall", 0)
        >= _FEEDER_FLOOR
    )
    dead_memo: dict[str, bool] = {}
    self_mill = _self_mill_deck(classes)

    def dead_here(card: Mapping) -> bool:
        key = card.get("oracle_id") or card.get("name", "")
        verdict = dead_memo.get(key)
        if verdict is None:
            verdict = (
                dead_payoff(card, deck_keys, deck_tribe_counts, deck_type_counts)
                or _commander_already_grants(card, ctx.commanders)
                # A deck milling itself takes no card that only mills
                # opponents: Mindcrank and Altar of the Brood went onto Necron
                # Dynasties' Mill page (2026-11-02).
                or (self_mill and _mills_only_opponents(card))
            )
            dead_memo[key] = verdict
        return verdict

    # The commander's specific needs (``commander_need``, ADR-0061), for the
    # job pages' near ties (:func:`_need_ties`).
    needs_here = [
        spec["_need"] for _l, _d, spec in ctx.need_avenues if spec.get("_need")
    ]

    def supplies_need(card: Mapping) -> bool:
        return any(satisfies(card, need) for need in needs_here)

    # Of those, the needs the deck already builds toward (``_NEED_BUILT_FLOOR``
    # of its cards supply one): how many of them a card supplies is the theme
    # pages' first order (``_ranked_pool``) and an upgrade's gate (``_upgrades``).
    # A need the commander mentions in passing — Commodore Guff's one Wizard
    # token, two deck cards — must not rank a token-making planeswalker over
    # Ugin, the Spirit Dragon; nor does more of what the commander already does
    # every turn (a ``redundancy`` need: Ms. Bumbleflower makes opponents draw
    # on every spell, and Forget and Martyr's Cry led her page over the
    # payoffs for it) (2026-11-01). Read once per card.
    # A need read off the commander's own trigger or condition (``event`` /
    # ``condition``) is the plan whatever the deck holds yet — Valgavoth's
    # opponents'-turn drainers are what Endless Punishment is short of.
    # A ceiling on a built need ("met at twelve suppliers, leads no more")
    # was measured and reverted: it switched off Bello's big-artifact need and
    # Éowyn's Human need, which are the plan however many cards the deck
    # holds — the 25 lost ten guide adds (2026-11-02).
    built_needs = [
        need
        for need in needs_here
        if need.kind != "redundancy"
        and need.leads
        and (
            need.kind in ("event", "condition")
            or sum(1 for c in classes if satisfies(c.record, need)) >= _NEED_BUILT_FLOOR
        )
    ]
    needs_count_memo: dict[str, int] = {}

    def needs_supplied(card: Mapping) -> int:
        key = card.get("oracle_id") or card.get("name", "")
        n = needs_count_memo.get(key)
        if n is None:
            n = sum(1 for need in built_needs if satisfies(card, need))
            needs_count_memo[key] = n
        return n

    # The needs an upgrade keeps: the built ones and the card types the
    # commander's text pays off (a ``payoff`` need with ``types``) when too
    # broad to page (``need_avenues`` skips a need over ``BROAD_SHARE`` of the
    # pool — Anikthea's enchantments, Inspirit's artifacts). A broad need leads
    # no page and ranks no theme card, but a cut of the type still goes to a
    # card of the type: Cast Out, an enchantment Anikthea returns, went to
    # Assassin's Trophy on the interaction page (Enduring Enchantments,
    # 2026-11-02). Only the payload types: holding every broad need kept
    # Massacre Girl (menace, Olivia's evasion event) from Damn and Eshki's
    # Dragons from Impact Tremors — the held-out 20 lost three guide cuts.
    kept_needs = built_needs + [
        need
        for need in ctx.needs
        if need not in built_needs
        and need.leads
        and (
            # A resource the commander makes itself is consumed whatever the
            # deck holds of the consumers: Temmet loots on every attack, and
            # Archfiend of Ifnir is one of three discard payoffs Eternal Might
            # holds (2026-11-02). A condition on the commander's own text is
            # its plan however broad: Éowyn's "if another Human entered the
            # battlefield … this turn" (Increasing Devotion, Riders of Rohan).
            need.kind in ("resource", "condition")
            or (
                need.kind == "payoff"
                and need.types
                and sum(1 for c in classes if satisfies(c.record, need))
                >= _NEED_BUILT_FLOOR
            )
        )
    ]
    kept_count_memo: dict[str, int] = {}

    def needs_kept(card: Mapping) -> int:
        key = card.get("oracle_id") or card.get("name", "")
        n = kept_count_memo.get(key)
        if n is None:
            n = sum(1 for need in kept_needs if satisfies(card, need))
            kept_count_memo[key] = n
        return n

    # Every ranking below scores in this one context, so each candidate's
    # readout is computed once (``rank_candidates``' ``scores``) however many
    # pages, ties and theme ties hold it. Lives for this call only.
    readouts: dict[int, tuple[dict, dict]] = {}

    def rank(cards: list[dict]) -> list[dict]:
        return rank_candidates(
            cards,
            active_signals=ctx.deck_signals,
            focus_sets=focus_sets,
            deck_tribes=deck_tribes,
            deck_mana=ctx.deck_mana,
            scores=readouts,
        )

    def tribal_cut(record: Mapping) -> bool:
        """Whether a deck card is one of the commander's tribe or a payoff
        for it (``Sourcing.tribe_spec`` / ``typal_payoff_for``)."""
        return sourcing.tribe_spec(record) is not None or typal_payoff_for(
            record, sourcing.tribe_kinds
        )

    cuts = cut_candidates(
        classes,
        budgets=ctx.budgets,
        focus=cut_focus,
        protected=ctx.protected,
        medium=ctx.medium,
        template=ctx.template,
        playrate=ctx.playrate_condemns,
        playrate_meaningful=ctx.playrate,
        # The trim order spares EVERY need's suppliers, the redundancy needs'
        # too: a card doing what the commander does (Kwain making opponents
        # draw under Ms. Bumbleflower) is the plan, whatever the row's band —
        # Peace Offering trimmed nine draw cards from a group-hug deck whose
        # guides keep the hug-and-draw core (2026-11-01).
        needs=(lambda record: int(supplies_need(record))) if needs_here else None,
        tribe_member=tribal_cut,
    )
    # Route cuts into the pools a Remedy names: an over-band trim cuts from THAT over
    # role (``over:<role>``); everything else is the generic pool (filler, low-value,
    # then stranded), so a trim isn't derailed onto filler.
    pools: dict[str, list[tuple[str, CardClass]]] = {
        CUT_GENERIC: [],
        CUT_FILLER: [],
        CUT_LANE: [],
        CUT_UPGRADE: [],
    }
    for reason, card in cuts:
        if over_role(reason) is not None:
            pool = reason
        elif reason == "lane_upgrade":
            pool = CUT_LANE  # only a ``lane_ok`` remedy, once its own pool is dry
        elif reason == "upgrade":
            pool = CUT_UPGRADE  # only the upgrade issue, for a card doing its job
            if (
                upgrade_job(
                    card.roles,
                    card.record,
                    on_plan=bool(cut_focus.mains.intersection(card.served)),
                )
                is None
            ):
                # A second view of the jobless slots, for a lane_ok remedy.
                pools.setdefault(CUT_UPGRADE_JOBLESS, []).append((reason, card))
        elif reason == "popular_upgrade":
            pool = CUT_UPGRADE_POPULAR  # the upgrade issue, once the rest are spent
        else:
            pool = CUT_GENERIC
        pools.setdefault(pool, []).append((reason, card))
        # The dead-weight drain cuts filler ONLY (a separate view of the same cards);
        # the shared used_cuts guard stops it and the generic pool cutting a card twice.
        if reason in ("filler", "low_value"):
            pools[CUT_FILLER].append((reason, card))
    cut_iters = {name: iter(items) for name, items in pools.items()}
    # Copies cut so far per name: a name may be cut up to the copies it holds (each
    # pool lists it once per copy), and never more across pools.
    used_cuts: Counter[str] = Counter()
    # The deck cards the proposal's own adds need: a near-miss add completes a
    # combo with them (``Issue.relies_on``), so cutting one would leave the add
    # without its line. ``combo_pieces`` protects the combos the deck holds
    # before the tune; this protects the ones the tune completes.
    relied_on: set[str] = set()

    def take_cut(
        pool: str, keep: Collection[str] = (), filling: str | None = None
    ) -> tuple[str, CardClass] | None:
        skipped: list[tuple[str, CardClass]] = []
        found = None
        for reason, card in cut_iters.get(pool, iter(())):
            if card.name in relied_on or card.name in keep:
                continue  # an add the proposal makes needs it
            if filling is not None and any(
                r == filling or (ctx.budgets.get(r) or {}).get("deviation", 0) < 0
                for r in card.roles
            ):
                # A fill never cuts a card of a row the deck is short of, its
                # own or another: Gix, Yawgmoth Praetor's draw went for Black
                # Market Connections to fill ramp (Mardu Surge, 2026-11-02).
                # Kept for a later issue.
                skipped.append((reason, card))
                continue
            if used_cuts[card.name] < card.quantity:
                found = (reason, card)
                break
        if skipped:
            # The pool iterator is shared: put back what this fill passed over.
            rest = list(cut_iters.get(pool, iter(())))
            cut_iters[pool] = iter(skipped + rest)
        return found

    def take_lane_ok_cut(keep: Collection[str] = ()) -> tuple[str, CardClass] | None:
        """A ``lane_ok`` remedy's cut once its own pool is dry: the jobless
        upgrade slots, then the lane's least-played half — every card that is
        none of the commander's tribe or its payoffs across both before one
        that is. Pool by pool, Descendants' Path (a payoff for Pantlaza's
        Dinosaurs, last of the jobless slots) went as a card-draw fill's cut
        while Drover of the Mighty and four other guide cuts waited in the lane
        pool (Veloci-Ramp-Tor, 2026-11-02). Holding back every need supplier
        so was measured and narrowed: held-out 569 / 262 / 107 → 564 / 260 /
        104. Opening the jobless popular slots that supply no need ahead of a
        need supplier was measured and reverted too: it kept Blight Curse's
        Kulrath Knight (wither, under Auntie Ool) from a ramp fill but churned
        Counter Intelligence and cut Pentad Prism again — held-out 565 / 262 /
        106 → 565 / 265 / 101 (2026-11-02)."""
        for want in (False, True):
            for pool in (CUT_UPGRADE_JOBLESS, CUT_LANE):
                for reason, card in pools.get(pool, ()):
                    if card.name in relied_on or card.name in keep:
                        continue
                    if used_cuts[card.name] >= card.quantity:
                        continue
                    if tribal_cut(card.record) != want:
                        continue
                    if any(
                        (ctx.budgets.get(r) or {}).get("deviation", 0) < 0
                        for r in card.roles
                    ):
                        # Never a card filling a row the deck is short of:
                        # Titan of Littjara's draw went to Sundial of the
                        # Infinite while card draw was two short (Sliver
                        # Swarm, 2026-11-02).
                        continue
                    return reason, card
        return None

    used_adds: Counter[str] = Counter()

    def coverage(card: dict) -> Coverage:
        """How far the collection covers the copy an add of ``card`` would become —
        ``Format.coverage`` for this build's medium, decided here once so the purse
        prices only uncovered copies and the swap's ``owned`` agrees with it."""
        name = card.get("name", "")
        copy = in_deck.get(name, 0) + used_adds[name] + 1
        return Format.coverage(ctx.medium, name, copy, ctx.owned.get(name, 0))

    def acquire_cost(card: dict) -> float | None:
        return 0.0 if coverage(card).short == 0 else ledger.acquire_cost(card)

    game_changers = _GameChangerRoom(ctx.game_changer_room)
    swaps: list[dict] = []
    # Each swap's cut, add record, cost and whether it was charged, in step
    # with ``swaps`` (:func:`_unfueled_adds`).
    committed: list[tuple[CardClass | None, dict, float, bool]] = []
    # In step with ``committed``: the search that found each add (``find_add``'s
    # spec and options), so a dropped add's cut can take the next one; None for
    # an add no search found (the mana base's).
    searches: list[tuple[dict, dict] | None] = []
    last_find: list[tuple[dict, dict] | None] = [None]
    ledger: _Purse = (
        _WildcardLedger(ctx.wildcard_budget)
        if ctx.wildcard_budget is not None
        else _UsdLedger(ctx.budget)
    )
    cmc_cap = 4.0 if ctx.top_heavy else None

    # Roles already at/above their template ceiling — an add filling one would push the
    # deck OFF-template, so fixing one issue must not regress the template.
    full_roles = {r for r, b in ctx.budgets.items() if b["current"] >= b["max"]}
    # How far each upgrade job is from the most the deck wants of it, as the
    # swaps land: a template row's max, and the Shape's protection target where
    # it wants protection (ADR-0024). A job with no room left is full, and a
    # full job's upgrade moves onto the theme (the docstring).
    job_room = {
        job: b["max"] - b["current"]
        for job, b in ctx.budgets.items()
        if job in UPGRADE_ROLE_ORDER and not b.get("advisory")
    }
    if ctx.protection_target:
        job_room["protection"] = ctx.protection_target - ctx.protection_count

    def count_jobs(record: dict, roles: Collection[str], step: int) -> None:
        held = set(roles)
        if "protection" in job_room and protects(record):
            held.add("protection")
        for job in job_room.keys() & held:
            job_room[job] -= step

    # Search + rank a spec ONCE per propose_swaps call, memoized. The ranked ORDER
    # depends only on in_deck (fixed), not on which cards have been used — so the fill
    # pass, which asks for the same spec repeatedly to fill many slots, reuses the pool
    # instead of re-searching + re-ranking ~1000 cards per card added (the dominant
    # redundant cost). used_adds is applied at pick time in find_add, not here.
    _pool_memo: dict[tuple, list[dict]] = {}
    _search_memo: dict[tuple, tuple[int, list[dict]]] = {}

    # Per theme avenue (a spec's ``_avenue``): the adds taken from it, the
    # support cards its broader page offered (``_SUPPORT_SHARE``) and how many
    # of those were taken.
    support_names: dict[str, set[str]] = {}
    theme_taken: Counter[str] = Counter()
    support_taken: Counter[str] = Counter()

    def _search(spec: dict, limit: int, *, capped: bool) -> list[dict]:
        """The spec's search, its first ``limit`` cards. One search per spec at
        the deepest page asked so far: the search sorts before it pages, so a
        shorter page is the deeper one's head."""
        prebuilt = spec.get("_page")
        if prebuilt is not None:  # a need page: already the pool's suppliers, in order
            return list(prebuilt)[:limit]
        skey = (search_key(spec), capped)
        deep = _search_memo.get(skey)
        if deep is None or deep[0] < limit:
            deep = (
                limit,
                _run_search(
                    ctx.search_fn,
                    spec,
                    identity=ctx.identity,
                    fmt=ctx.fmt,
                    paper_only=ctx.paper_only,
                    cmc_cap=cmc_cap if capped else None,
                    limit=limit,
                    playrate=ctx.playrate,
                ),
            )
            _search_memo[skey] = deep
        return deep[1][:limit]

    def _ranked_pool(
        spec: dict,
        *,
        synergy_first: bool,
        nonland_only: bool,
        limit: int,
        job: str | None = None,
        capped: bool = True,
    ) -> list[dict]:
        # A need page rides in ``_page`` (a list, keyed by identity: one list per
        # need per call).
        key = (
            tuple(sorted((k, v) for k, v in spec.items() if k != "_page")),
            id(spec.get("_page")),
            synergy_first,
            nonland_only,
            limit,
            job,
            capped,
        )
        cached = _pool_memo.get(key)
        if cached is not None:
            return cached
        # A theme searched by card type or preset (a tribe, Artifacts, Goad)
        # pages its own members; its serve's broader page adds the support
        # that is not of the type (Urza's Incubator under Dinosaurs), which
        # ``find_add`` holds to ``_SUPPORT_SHARE`` of the theme's adds.
        avenue = spec.get("_avenue")
        # A page's own order, ahead of play-rate and synergy (the polymorph
        # fodder page's repeatable makers first, ``issues._fodder_lead``), then
        # on a theme page the commander's specific needs the card supplies
        # (most first): under Morska the Clue makers before a creature-token
        # anthem, under Ellivere the Auras before the Equipment, under Gimbal
        # the artifact token makers before the mana rocks (2026-11-01). The
        # job pages keep their reads' order (``_job_order``). Measured and held
        # back (2026-11-01): a candidate that also fills a role the deck is
        # short of leading the rest — meant for Asceticism over Panharmonicon
        # on Bello's page with no protection in the deck — put the cycling
        # Dinosaurs over Etali and Gishath on Pantlaza's page and protection
        # Equipment on Bello's (25 precons 121 → 109 guide adds).
        lead = spec.get("_lead")
        # The need leads a tribe page too: keeping "upgrade a Dinosaur" in
        # play-rate order was measured and reverted — Veloci-Ramp-Tor's
        # Bonehoard Dracosaur and Ghalta and Mavren did not come back, and
        # Dance of the Elements' and Party Time's need-led tribe pages lost
        # seven guide adds between them (held-out 105 → 100, 2026-11-02).
        by_needs = synergy_first and job is None and avenue is not None and built_needs
        # A page with an order of its own is sorted WHOLE and cut to ``limit``
        # after: the lead has to see the suppliers below the play-rate head.
        # Cut first, Hazel's Squirrel makers (two of her needs) sat past the
        # token makers' first 150 and Fanatic of Rhonas took Arasta's slot
        # (2026-11-01).
        page_limit = sys.maxsize if (lead is not None or by_needs) else limit
        support: set[str] = set()
        if (
            synergy_first
            and job is None
            and avenue is not None
            and spec.get("_serve") is not None
            and not pages_by_serve(spec)
        ):
            # Every member, which the support is told apart from: the page is
            # their head (one search, not a page and then every member).
            members_page = _search(spec, sys.maxsize, capped=capped)
            members = {c.get("name") for c in members_page}
            extra = [
                c
                for c in _search(serve_page_search(spec), page_limit, capped=capped)
                if c.get("name") not in members
            ]
            support = {c.get("name", "") for c in extra}
            support_names.setdefault(avenue, set()).update(support)
            found = [*members_page[:page_limit], *extra]
        else:
            found = _search(spec, page_limit, capped=capped)
        # A card the deck already runs stays in the pool while it may hold another
        # copy (used_adds is applied at pick time, so the memoized order holds).
        pool = [
            c for c in found if ctx.under_ceiling(c, in_deck.get(c.get("name", ""), 0))
        ]
        if nonland_only:
            pool = [c for c in pool if not is_land(c)]
        if spec.get("name"):  # a named-card remedy wants that card, not a substring hit
            pool = [c for c in pool if c.get("name") == spec["name"]]
        spec_filter = spec.get("_filter")
        if spec_filter is not None:  # tuner-side precision pass (e.g. reliable-ramp)
            pool = [c for c in pool if spec_filter(c, deck_mana=ctx.deck_mana)]

        # Measured and held back (2026-11-02): among the live cards of a type
        # page, one that also serves another of the deck's viable avenues
        # leading one that only has the type — meant for Asceticism and
        # Glorious Sunrise over Panharmonicon on Bello's page — cost the 25 six
        # guide adds (120 → 114: Felothar's walls, Anikthea's doublers) and the
        # held-out 20 eleven (104 → 93), Counter Intelligence back to 21
        # swaps; scoped to a commander whose plan is a mana-value floor it
        # traded Bello's popular idle artifacts for obscure artifact creatures
        # (Big Mother Mouser, Lux Artillery), no better by the guides.

        def led(c: dict) -> tuple:
            own = lead(c) if lead is not None else ()
            needs_term = (-needs_supplied(c),) if by_needs else ()
            return (*own, *needs_term)

        if synergy_first and job is not None and ctx.playrate:
            ranked = _job_order(pool, job)
        elif synergy_first and ctx.playrate:
            # A theme page where play-rate means something (the Commander
            # family; the one EDHREC-popularity lean, user-directed): the most
            # played first, then price. The page's search already holds only the
            # theme's cards, so no synergy floor on top. The floor this replaced
            # (a fifth of the page's best synergy score, then play-rate; 72 guide
            # adds in the pages' top ten against play-rate alone's 69, 2026-10-19)
            # lost the tune adds: measured on the phase v0.118.0 pin (2026-10-30)
            # against the floor's 722 swaps / 332 guide cuts / 115 guide adds
            # (held-out 297 / 139 / 36, Jace 29 / 14 / 3), play-rate alone
            # scored 718 / 333 / 118 (held-out 290 / 139 / 37, Jace unchanged).
            # Card reads leading the order (commander fit, deck depth, blends in
            # log play-rate) all scored below both (backlog (t)).
            ranked = sorted(
                pool,
                key=lambda c: (
                    led(c),
                    _quality(c, playrate=True),
                    extract_price(c) or 1e9,
                ),
            )
        elif synergy_first:
            # Elsewhere synergy alone orders the page, then price.
            ranked = [
                r["card"]
                for r in sorted(
                    rank(pool),
                    key=lambda r: (
                        led(r["card"]),
                        -r["score"]["synergy_score"],
                        extract_price(r["card"]) or 1e9,
                    ),
                )
            ]
        else:
            # Spine fills: the cheapest mana-value BAND that does the job first
            # (efficiency), then play-rate within it, then price. Exact mana value
            # first let an X or {0} cost win every fill — Welding Jar as the
            # protection add, Engineered Explosives as the board wipe, under a
            # Dinosaur commander (25-precon audit, 2026-10-18) — so where play-rate
            # means something (the Commander family) the band is the unit and the
            # most-played card in it is the fill. A 60-card or limited deck keeps
            # the exact mana value: its ``_quality`` is neutral, so price breaks the
            # tie and nothing else would.
            #
            # A job whose read orders its fill (``JobRead.fill_orders``: board
            # wipes) ranks by the read first, then the band: the read already
            # weighs the cost, and the band let Wail of War (read 0.07) fill
            # Death Toll's wipe slot over Find // Finality (0.28).
            fill_read = read_for(job) if ctx.playrate else None
            if fill_read is not None and not fill_read.fill_orders:
                fill_read = None

            def fill_lead(c: dict) -> tuple:
                if fill_read is None:
                    return ()
                sc = fill_read.score(c, deck_records)
                return (sc is None, -(sc or 0.0))

            ranked = sorted(
                pool,
                key=lambda c: (
                    fill_lead(c),
                    _mv_band(c) if ctx.playrate else c.get("cmc", 0.0),
                    _quality(c, playrate=ctx.playrate),
                    extract_price(c) or 1e9,
                ),
            )
        if page_limit != limit:
            # The deep page adds only what the play-rate head LACKS: a card the
            # lead ranks ahead of every addable card in the head (Hazel's
            # Squirrel makers, two needs to the head's one). Sorted whole and
            # cut to the lead's top, the page was a thousand obscure cards
            # supplying as much as the head's did, and the tune spent its budget
            # on them before its job upgrades (held-out Counter Intelligence 30
            # → 21 swaps; Enduring Enchantments took eight self-mill
            # enchantments, 2026-11-01).
            head = found[:limit]
            best = min(
                (led(c) for c in head if not in_deck.get(c.get("name", ""))),
                default=None,
            )
            # Strictly ahead of the head's best, never tied with it: deep ties
            # admitted while the head's best tier was thin (under ten) flooded
            # Bello's page with obscure artifacts (Gruul War Plow, Horn of
            # Deafening) and took Counter Intelligence back to 21 swaps
            # (2026-11-02, measured and held back).
            deep = [c for c in found[limit:] if best is None or led(c) < best]
            keep = {id(c) for c in head} | {id(c) for c in deep}
            ranked = [c for c in ranked if id(c) in keep]
        else:
            ranked = ranked[:limit]
        _pool_memo[key] = ranked
        return ranked

    def _job_order(pool: list[dict], job: str) -> list[dict]:
        """An upgrade's candidates in order. A job upgrade (removal, draw, ramp, a
        wipe, protection) trades a card for one doing the same job, not for one
        fitting the theme, so no fit floor: the most played first, or for a job
        whose card read orders (``JobRead.orders``) the best blend of how well
        each does the job (its read's percentile in the match set), how many
        decks play it (its play-rate percentile) and how strong a card it is on
        its own text (its quality read's percentile, ``card_quality``, ADR-0063:
        held-out plan-consistency +19 with the guide floor held) — the job read
        alone put the guides' adds lower at the top of the list than play-rate
        does. The fit floor
        kept Swords to Plowshares and Path to Exile — the most played, both guide
        adds — behind Dragon Tempest in a goad deck; without it 54 guide adds
        matched across the 25 precons, against 47 (thirty swaps, 2026-10-19).

        Synergy, then price, then the synergy ranking's own order
        (``rank_candidates``) breaks a tie. Synergy is scored only for the cards
        a tie leaves level: the match set runs to thousands of cards for a
        five-colour job, and synergy decides nothing else here."""
        read = read_for(job)
        blend = (
            _blended_percentiles(pool, job, deck_records)
            if read is not None and read.orders
            else {}
        )

        def lead(card: dict) -> float:
            mix = blend.get(card.get("name", ""))
            return -mix if mix is not None else _quality(card, playrate=True)

        leads = Counter(lead(c) for c in pool)
        tied = [c for c in pool if leads[lead(c)] > 1]
        synergy = {
            id(r["card"]): (-r["score"]["synergy_score"], i)
            for i, r in enumerate(rank(tied))
        }
        out = sorted(
            pool,
            key=lambda c: (
                lead(c),
                synergy.get(id(c), (0.0, 0))[0],
                extract_price(c) or 1e9,
                synergy.get(id(c), (0.0, 0))[1],
            ),
        )
        if read is not None and read.theme_ties:
            out = _theme_ties(out, read)
        if needs_here:
            out = _need_ties(out)
        return out

    def _need_ties(ranked: list[dict]) -> list[dict]:
        """``ranked`` with a job card that supplies one of the commander's
        specific needs (:func:`supplies_need`: Smothering Tithe under a Treasure
        commander) taking the place of one that doesn't when the two are a near
        tie in play-rate (within ``_CHEAPER_TIE``, a factor of two in rank). A
        near tie, never a hold: a clearly better-played staple keeps its place.
        Only the head of the order (``_THEME_TIE_WINDOW``) is walked. The wide
        tie (any need, not only one the deck's main lanes also serve): measured
        2026-10-30, it is what moves plan-consistency, the gate's primary line."""
        head = list(ranked[:_THEME_TIE_WINDOW])
        out: list[dict] = []
        while head:
            pick = head[0]
            if not supplies_need(pick):
                top = math.log10(edhrec_popularity(pick))
                for later in head[1:]:
                    if math.log10(
                        edhrec_popularity(later)
                    ) - top <= _CHEAPER_TIE and supplies_need(later):
                        pick = later
                        break
            out.append(pick)
            head.remove(pick)
        return out + ranked[_THEME_TIE_WINDOW:]

    def _theme_ties(ranked: list[dict], read: JobRead) -> list[dict]:
        """``ranked`` with an on-theme card taking the place of an off-theme one
        that does the job about as well: walking the order, where the next card
        serves none of the deck's viable avenues, the first later card that does,
        scoring within ``_THEME_TIE`` of it on the job read, goes first. Theme
        fit breaks a near tie above play-rate; it never holds an upgrade to the
        theme. Only the first ``_THEME_TIE_WINDOW`` cards are reordered."""
        head = ranked[:_THEME_TIE_WINDOW]
        on = _viable_served_names(head)
        scores = {c.get("name", ""): read.score(c, deck_records) for c in head}
        rest = list(head)
        out: list[dict] = []
        while rest:
            pick = rest[0]
            top = scores.get(pick.get("name", ""))
            if top is not None and pick.get("name", "") not in on:
                for later in rest[1:]:
                    sc = scores.get(later.get("name", ""))
                    if (
                        later.get("name", "") in on
                        and sc is not None
                        and abs(sc - top) <= _THEME_TIE
                    ):
                        pick = later
                        break
            out.append(pick)
            rest.remove(pick)
        return out + ranked[_THEME_TIE_WINDOW:]

    def _viable_served_names(cards: Sequence[dict]) -> set[str]:
        """Names among ``cards`` that serve ≥1 of the deck's VIABLE avenues —
        reuses ``rank_candidates``' own ``served`` computation (the ADR-0040
        role-fix guard below), never a second serving definition."""
        viable = focus_sets["viable"]
        if not viable or not cards:
            return set()
        scored = rank(list(cards))
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
        limit: int = _PAGE,
        role_fix: bool = False,
        upgrade_of: CardClass | None = None,
        job: str | None = None,
        trim_of: CardClass | None = None,
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
        the default 150-card page runs dry after dedup; it requests a deeper page.

        ``role_fix`` marks a Spine-band add (ADR-0040 companion): at FOCUSED verdict,
        among the non-overshooting affordable candidates, one that serves ≥1 of the
        deck's viable avenues is picked over one that serves none, whenever such a
        candidate exists — the zero-avenue pick still ships as a last resort, and the
        caller labels it via the returned flag. SPREAD-THIN / SPINE-LED and non-role-fix
        calls are untouched: the first eligible candidate in ranked order wins, exactly
        as before this guard.

        ``upgrade_of`` is the card an upgrade replaces and ``job`` the
        job it keeps: a candidate must be an upgrade (:func:`_upgrades`), and
        the roles the cut frees are no overshoot. ``trim_of`` is the card a trim
        cuts: a candidate keeps its mana-value band (:func:`over_band`, job-less).

        Where play-rate means something, the first eligible candidate is the add
        when it costs no more than an even share of what is left over the swaps
        still open (``_Purse.share``). Past that share the budget binds: the
        next ``_CHEAPER_WINDOW`` candidates are weighed, and the first that fits
        the share is the add, else the cheapest near tie (:func:`_near_tie`), so
        the budget reaches more issues. An upgrade's add past the share takes at
        most ``_PURSE_CAP`` of what is left.

        Under a polymorph commander a job upgrade of a card that makes fodder
        (``Sourcing.fodder_spec``'s serve) must make fodder too, or the card is
        not a slot: Occult Epiphany's Spirits are bodies for Jace's -3 to exile.
        Measured with the rest of the change (2026-10-30): Multiverse Reforged
        30 / 15 / 4 against 30 / 14 / 4 (one guide cut, Fact or Fiction; Occult
        Epiphany goes to Thopter Shop, Staff of the Storyteller to Dawn of Hope).
        A theme upgrade is untouched: the guides cut theme cards often (backlog
        (s), 3a).

        And a creature or planeswalker it adds is a flip (:func:`is_flip`): one
        below the deck's flip floor (:func:`flip_floor_band`) that the fodder
        page does not admit is a whiff in the library, not an add, whatever
        page asked for it — Zurgo Stormrender as a card-draw upgrade, Adeline
        as a theme one (Dan's Jace tune, 2026-11-01: ten such adds beside
        eleven bombs cut). A card asked for by name (a combo's missing piece)
        is the exception: the line is the reason.
        """
        last_find[0] = (
            spec,
            {
                "synergy_first": synergy_first,
                "nonland_only": nonland_only,
                "limit": limit,
                "role_fix": role_fix,
                "upgrade_of": upgrade_of,
                "job": job,
                "trim_of": trim_of,
            },
        )
        ranked = _ranked_pool(
            spec,
            synergy_first=synergy_first,
            nonland_only=nonland_only,
            limit=limit,
            job=job,
            # A top-heavy deck caps its adds at four mana so a fix can't make the
            # curve heavier; an upgrade can't anyway — it takes no higher
            # mana-value band than its cut (``_upgrades``).
            capped=upgrade_of is None,
        )
        rejected_hits.clear()
        # Protection is exempt (``_GUARD_EXEMPT_JOBS``).
        guard = (
            role_fix
            and ctx.focus_result["verdict"] == "FOCUSED"
            and job not in _GUARD_EXEMPT_JOBS
        )
        fallback: tuple[dict, float] | None = None
        eligible: list[tuple[dict, float]] = []
        avenue = spec.get("_avenue")
        # Where play-rate orders the page: the even share and the near tie
        # (the docstring).
        tie_read = read_for(job)
        if tie_read is not None and not tie_read.orders:
            tie_read = None
        share = ledger.share(ctx.max_swaps - len(swaps))
        # A cut serving none of the main avenues (``_upgrades``' ``off_theme``).
        band_cut = upgrade_of or trim_of
        off_theme = band_cut is not None and not cut_focus.mains.intersection(
            band_cut.served
        )
        first: tuple[dict, float] | None = None
        best: tuple[dict, float] | None = None
        looked = 0
        window = (
            _CHEAPER_WINDOW_THEME
            if job is None and ctx.playrate and share < _TIGHT_SHARE
            else _CHEAPER_WINDOW
        )
        for card in ranked:
            if first is not None:
                looked += 1
                if looked > window:
                    break
            if not addable(card):  # every allowed copy taken — the next best
                continue
            if spec.get("name") and float(card.get("cmc") or 0.0) > deck_top_mv:
                continue  # a named add above the deck's top end (``deck_top_mv``)
            if avenue is not None and not support_room(avenue, card):
                continue
            if not game_changers.allows(card):
                continue  # ADR-0030: never propose an add past the bracket's ceiling
            if plays_lands and _stops_land_plays(card):
                # "You can't play lands" in a deck that plays extra lands or
                # pays off landfall: Aggressive Mining under Hearthhull, the
                # Worldseed (World Shaper, 2026-11-02).
                continue
            pips = (card.get("mana_cost") or "").count("{C}")
            if pips and colorless_sources < _C_SOURCES_PER_PIP * pips:
                # Echoes of Eternity's {C}{C}{C} in Animated Army, a Gruul
                # deck of eight colorless sources (2026-11-02).
                continue
            if not spec.get("name") and below_floor(card):
                # The docstring: a cheap flip is a whiff in the library, unless
                # it is fodder, and fodder only while the flips stay mostly the
                # deck's bombs (``_WHIFF_SHARE``) — counted as the swap would
                # leave them, the cut's own flip gone where the cut is known.
                if not (fodder_serve is not None and fodder_serve.matches(card)):
                    continue
                cut_rec = band_cut.record if band_cut is not None else None
                flips_after = (
                    flip_count
                    + 1
                    - bool(cut_rec is not None and is_flip(cut_rec, flip_types))
                )
                low_after = (
                    low_flips + 1 - bool(cut_rec is not None and below_floor(cut_rec))
                )
                if low_after > _WHIFF_SHARE * flips_after:
                    continue
            if (
                job is not None
                and upgrade_of is not None
                and fodder_serve is not None
                and fodder_serve.matches(upgrade_of.record)
                and not fodder_serve.matches(card)
            ):
                continue  # the docstring: a maker's job upgrade makes fodder too
            if (
                job == "board_wipe"
                and not spec.get("name")
                and _sweeps_no_creatures(card)
            ):
                continue  # the board-wipe row is for creature boards
            if (
                job == "ramp"
                and upgrade_of is None
                and not spec.get("name")
                and _one_shot_mana(card)
            ):
                # A ritual fills no ramp slot: Dark Ritual (Fae Dominion),
                # Jeska's Will (Quick Draw), Cabal Ritual (Revenant Recon).
                continue
            if not spec.get("name") and (
                dead_here(card)
                if job is None
                else gated_without_feed(
                    card, deck_tribe_counts, deck_type_counts, deck_keys
                )
            ):
                # A payoff for something this deck doesn't do: the theme page's
                # whole read, a job page's gate rule alone (the whole read
                # misfired there — Farseek's Plains, Teferi's untap — and a job
                # card's job is its own; a banner's or Dragon Tempest's is not).
                # A named add is the line's (2026-11-02).
                continue
            if upgrade_of is not None and not _upgrades(
                card,
                upgrade_of,
                job,
                deck_mana=ctx.deck_mana,
                deck=deck_records,
                off_theme=off_theme,
                draw_engine=ctx.draw_engine_commander,
                needs=needs_supplied if built_needs else None,
                needs_kept=needs_kept if kept_needs else None,
                commanders=ctx.commanders,
            ):
                continue
            if upgrade_of is None and not _does_the_job(card, job, deck_records):
                continue
            if trim_of is not None and over_band(
                card, trim_of.record, None, off_theme=off_theme
            ):
                continue  # a trim's add keeps its cut's band
            if trim_of is not None and role_of(card, deck_mana=ctx.deck_mana) & {
                r
                for r in trim_of.roles
                if (ctx.budgets.get(r) or {}).get("deviation", 0) > 0
            }:
                # A trim's add is no member of the row it trims: Wizard Class
                # went to Deep Analysis for "card draw over by 9" (Peace
                # Offering, 2026-11-02). Holding a trim's add out of every
                # over row was measured and reverted: Peace Offering's plan is
                # draw, so its ramp trims found nothing to add and two guide
                # cuts went unmade (held-out 563 / 262 / 105 → 562 / 260 /
                # 105); held to every theme add, eight swaps and seven guide
                # cuts (→ 554 / 255 / 105).
                continue
            cost = acquire_cost(card)
            if cost is None:
                continue
            if (
                band_cut is not None
                and cost > share
                and cost > _PURSE_CAP * share * max(1, ctx.max_swaps - len(swaps))
            ):
                # An upgrade's or a trim's add past the share takes at most
                # ``_PURSE_CAP`` of what is left: Sheoldred, the Apocalypse took
                # half of Endless Punishment's $126 as a trim's add and the
                # tune ran dry at 20 swaps (2026-11-02).
                continue
            overshoot = role_of(card, deck_mana=ctx.deck_mana) & full_roles
            if upgrade_of is not None:
                overshoot -= set(upgrade_of.roles)
            if overshoot:
                fallback = fallback or (card, cost)  # keep the best overshooting option
                continue
            if not guard:
                if not ctx.playrate or cost <= share:
                    return card, cost, False
                if first is None:
                    first = best = (card, cost)
                elif (
                    best is not None
                    and cost < best[1]
                    and _near_tie(first[0], card, tie_read, deck_records)
                ):
                    best = (card, cost)
                continue
            eligible.append((card, cost))

        if best is not None:
            return (*best, False)
        if not guard or not eligible:
            return (*fallback, False) if fallback else None
        on_avenue = _viable_served_names([c for c, _ in eligible])
        for card, cost in eligible:
            if card.get("name") in on_avenue:
                return card, cost, False
        card, cost = eligible[0]  # nothing on-avenue — labeled last resort
        return card, cost, True

    def support_room(avenue: str, card: dict) -> bool:
        """Whether ``card`` may be ``avenue``'s next add: a member always, a
        support card while the support taken stays within ``_SUPPORT_SHARE``
        of the avenue's adds, this one counted."""
        if card.get("name") not in support_names.get(avenue, ()):
            return True
        return support_taken[avenue] + 1 <= _SUPPORT_SHARE * (theme_taken[avenue] + 1)

    def find_theme_add(
        spec: dict,
        *,
        synergy_first: bool,
        nonland_only: bool = False,
        limit: int = _PAGE,
        role_fix: bool = False,
        upgrade_of: CardClass | None = None,
        job: str | None = None,
        trim_of: CardClass | None = None,
    ) -> tuple[tuple[dict, float, bool] | None, str | None]:
        """``find_add``, and the theme avenue the add serves (``None`` off a
        theme). The deck's theme (a spec marked ``_share``, ``Sourcing.theme``)
        is shared by depth over its main avenues (``Sourcing.theme_avenues``):
        each pick asks the avenue with the most depth per add it already took,
        then the next, so a second main gets its own adds."""
        avenues = sourcing.theme_avenues() if spec.get("_share") else []
        if not avenues:
            avenues = [(spec.get("_avenue"), 1, spec)]
        order = sorted(
            range(len(avenues)),
            key=lambda i: (-avenues[i][1] / (theme_taken[avenues[i][0] or ""] + 1), i),
        )
        for i in order:
            label, _depth, aspec = avenues[i]
            # An avenue holding to a number of adds (the multiplier page's one).
            cap = aspec.get("_cap")
            if cap is not None and theme_taken[label or ""] >= cap:
                continue
            picked = find_add(
                aspec,
                synergy_first=synergy_first,
                nonland_only=nonland_only,
                limit=limit,
                role_fix=role_fix,
                upgrade_of=upgrade_of,
                job=job,
                trim_of=trim_of,
            )
            if picked is not None:
                return picked, label
        return None, None

    def commit(
        kind: str,
        message: str,
        reason: str,
        cut: CardClass | None,
        add_card: dict,
        cost: float,
        *,
        off_avenue: bool = False,
        avenue: str | None = None,
    ) -> None:
        nonlocal flip_count, low_flips
        # Charge only now that the swap is finalized (find_add probed read-only, so an
        # unpaired add never consumed budget — USD dollars or a wildcard, by mode).
        if cut is not None:
            count_jobs(cut.record, cut.roles, -1)
        count_jobs(add_card, role_of(add_card, deck_mana=ctx.deck_mana), 1)
        if flip_floor is not None:
            # The polymorph deck's flips, as the proposal leaves them.
            if cut is not None and is_flip(cut.record, flip_types):
                flip_count -= 1
                low_flips -= below_floor(cut.record)
            if is_flip(add_card, flip_types):
                flip_count += 1
                low_flips += below_floor(add_card)
        cover = coverage(add_card)
        if cover.covered_by is None:
            ledger.charge(add_card, cost)
        committed.append((cut, add_card, cost, cover.covered_by is None))
        searches.append(last_find[0])
        last_find[0] = None
        game_changers.charge(add_card, cut)
        if cut is not None:
            used_cuts[cut.name] += 1
        add_name = add_card.get("name", "")
        used_adds[add_name] += 1
        if avenue is not None:
            theme_taken[avenue] += 1
            support_taken[avenue] += add_name in support_names.get(avenue, ())
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
                    # The coverage decision the purse charged by, served so the UI
                    # derives nothing: copies this add leaves to acquire (0 or 1),
                    # and "free" (a basic land) / "owned" (the collection's copies).
                    "copies_short": 0 if cover.covered_by else 1,
                    "covered_by": cover.covered_by,
                    "owned": cover.covered_by == "owned",
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
    # The mana base first (Phase C): a tapped mana-only land, or a surplus basic,
    # for an untapped land in its colours, within the land purse
    # (``mana_base.LAND_BUDGET_SHARE`` of the budget in all, ``LAND_PRICE_SHARE``
    # of the even share per land). Fixing the mana is usually the biggest buff a
    # precon gets, so these take their swaps before the plan's issues do.
    if ctx.land_plan is not None and ctx.land_plan.cuts and ctx.land_pool:
        land_budget = (
            ctx.budget * mana_base.LAND_BUDGET_SHARE if ctx.budget is not None else None
        )
        price_cap = (
            mana_base.LAND_PRICE_SHARE * ctx.budget / max(1, ctx.max_swaps)
            if ctx.budget is not None
            else math.inf
        )
        land_spent = 0.0
        land_classes = {c.name: c for c in classes if c.bucket == "land"}
        candidates = mana_base.land_candidates(
            ctx.land_pool, needed=ctx.land_plan.needed, exclude=set(in_deck)
        )

        def land_cost(card: dict) -> float | None:
            cost = acquire_cost(card)
            if cost is None:
                return None
            if land_budget is not None and land_spent + cost > land_budget:
                return None
            return cost

        land_swaps_cap = max(1, int(mana_base.LAND_SWAP_SHARE * ctx.max_swaps))
        for record, must in ctx.land_plan.cuts:
            if len(swaps) >= min(ctx.max_swaps, land_swaps_cap):
                break
            cut = land_classes.get(record.get("name", ""))
            if cut is None or cut.name in ctx.protected or used_cuts[cut.name]:
                continue
            pick = mana_base.pick_add(
                candidates,
                must=must,
                used=set(used_adds) | set(in_deck),
                price_cap=price_cap,
                affordable=land_cost,
            )
            if pick is None:
                continue
            add_card, cost = pick
            land_spent += cost
            why = (
                "a basic beyond the colour demand"
                if is_basic_land(cut.record)
                else "enters tapped and only makes mana"
            )
            commit(
                "mana_base",
                f"mana base: {cut.name} {why} — {add_card.get('name', '')} enters "
                "untapped in the deck's colours",
                "mana_base",
                cut,
                add_card,
                cost,
            )

    theme = sourcing.theme()
    # Where a full job's slot moves (below): the theme, or for a polymorph
    # deck's flip the flips' page (``Sourcing.flip_spec``), so the slot stays a
    # flip — Niv-Mizzet, Ghost Counsel's draw slot under Jace with card draw
    # over its band.
    flip_page = sourcing.flip_spec()

    def moved_source(cut: CardClass) -> UpgradeSource | None:
        if flip_page and is_flip(cut.record, flip_types):
            return UpgradeSource(flip_page, None, FLIP_SLOT)
        return UpgradeSource(theme, None) if theme else None

    # The adds taken per deck card a combo line relies on (``_COMBO_PIECE_ADDS``).
    combo_adds: Counter[str] = Counter()
    # The deck's top nonland mana value: a card asked for by name (a combo's
    # missing piece) that costs more than anything the deck runs is not a slot
    # — Blightsteel Colossus for Blade of Selves in Mardu Surge, a token aggro
    # deck whose top is Myr Battlesphere (2026-11-01). Every other add keeps
    # its cut's band already (:func:`over_band`).
    deck_top_mv = max((c.cmc for c in classes if c.bucket != "land"), default=0.0)

    for issue in issues:
        if len(swaps) >= ctx.max_swaps:
            break
        remedy = issue.remedy
        if remedy is None:
            continue  # nothing to source — the issue is the builder's to read
        if any(used_cuts[name] for name in issue.relies_on):
            continue  # a piece the add needs is already cut
        if issue.kind == "near_miss_combo" and any(
            combo_adds[name] >= _COMBO_PIECE_ADDS for name in issue.relies_on
        ):
            continue  # the piece has its partners (``_COMBO_PIECE_ADDS``)
        # Every cut is a NONLAND (cut_candidates never trims lands), so the add must be
        # nonland too — else a theme swap silently adds a value land (e.g. Fountainport
        # on the Aristocrats lane), shifting the land count a swap is meant to
        # preserve. The mana base is the land tooling's job, not Tune's.
        trim = over_role(remedy.cut_from) is not None
        if remedy.spec_for_cut is not None or trim:
            # Cut first, then the add the cut allows. An upgrade's add is the
            # one the cut names (its own job), ranked as any theme add is — fit,
            # then play-rate, or for a job whose read orders, the read blended
            # with play-rate; a cut nothing does the job of better is passed
            # over. A trim's add deepens the remedy's avenue at no higher a
            # mana-value band than its cut's (``over_band``, as an upgrade's): a
            # one-mana card trimmed from an over row is no slot for a seven-drop.
            # A trim with no add stops there, as an add-first issue does.
            trims = 0
            while len(swaps) < ctx.max_swaps:
                cut_entry = take_cut(remedy.cut_from, issue.relies_on)
                if cut_entry is None and remedy.lane_ok:
                    cut_entry = take_cut(CUT_LANE, issue.relies_on)
                if cut_entry is None and remedy.cut_from == CUT_UPGRADE:
                    cut_entry = take_cut(CUT_UPGRADE_POPULAR, issue.relies_on)
                if cut_entry is None:
                    break
                reason, cut = cut_entry
                message = issue.message
                if remedy.spec_for_cut is None:
                    picked, avenue = find_theme_add(
                        remedy.spec, synergy_first=True, nonland_only=True, trim_of=cut
                    )
                else:
                    source = remedy.spec_for_cut(cut)
                    if source is None:
                        continue
                    job_read = read_for(source.job)
                    picked, avenue = find_theme_add(
                        source.spec,
                        synergy_first=True,
                        nonland_only=True,
                        upgrade_of=cut,
                        job=source.job,
                        # A job with a card read reads its whole match set, so
                        # the read's gate (and, for an ordering job, its blend)
                        # reaches past popularity.
                        limit=_JOB_READ_PAGE if job_read else _PAGE,
                    )
                    if (
                        picked is None
                        and source.job is None
                        and source.what not in (None, FLIP_SLOT)
                    ):
                        # A tribe slot stays the tribe's while the tribe's page
                        # holds a better card; past that the slot is routed as
                        # any theme cut's is — the main theme, then the pages
                        # of the needs the cut supplies (Explorers of the
                        # Deep's weak Merfolk feed Hakbal's counters, and the
                        # Merfolk page ran dry: four swaps went unmade,
                        # 2026-11-02). A flip's slot stays a flip's.
                        fallbacks = [sourcing.theme() or {}]
                        fallbacks += [
                            {k: v for k, v in nspec.items() if k != "_cap"}
                            for _l, _d, nspec in ctx.need_avenues
                            if nspec.get("_need") is not None
                            and satisfies(cut.record, nspec["_need"])
                        ]
                        for spec in fallbacks:
                            if not spec:
                                continue
                            picked, avenue = find_theme_add(
                                spec,
                                synergy_first=True,
                                nonland_only=True,
                                upgrade_of=cut,
                                job=None,
                            )
                            if picked is not None:
                                source = UpgradeSource(spec, None)
                                break
                    # A full job's slot moves onto the theme (the docstring) when
                    # the theme's add costs no more than the job's would — or,
                    # for a polymorph deck's flip, onto the flips' page.
                    target = (
                        moved_source(cut)
                        if source.job in job_room and job_room[source.job] <= 0
                        else None
                    )
                    if target is not None:
                        moved, moved_avenue = find_theme_add(
                            target.spec,
                            synergy_first=True,
                            nonland_only=True,
                            upgrade_of=cut,
                            job=None,
                        )
                        cap = (
                            picked[1]
                            if picked is not None
                            else ledger.share(ctx.max_swaps - len(swaps))
                        )
                        if moved is not None and moved[1] <= cap:
                            picked, avenue = moved, moved_avenue
                            source, job_read = target, None
                    if picked is not None:
                        why = (
                            "reads better at the job and more decks play it"
                            if job_read is not None and job_read.orders
                            else "more decks play it"
                        )
                        message = (
                            f"upgrade {source.label}: "
                            f"{picked[0].get('name', '')} — {why}"
                        )
                if picked is None and trim:
                    if rejected_hits and not trims:
                        names = ", ".join(dict.fromkeys(rejected_hits))
                        blocked_notes.append(
                            f'No alternative to {names} for "{issue.message}" — '
                            f"{allow_buys}, or allow it again."
                        )
                    break
                if picked is None:
                    continue
                add_card, cost, off_avenue = picked
                relied_on.update(issue.relies_on)
                if issue.kind == "near_miss_combo":
                    combo_adds.update(issue.relies_on)
                commit(
                    issue.kind,
                    message,
                    reason,
                    cut,
                    add_card,
                    cost,
                    off_avenue=off_avenue,
                    avenue=avenue,
                )
                trims += 1
            continue
        swaps_for_issue = 0
        while len(swaps) < ctx.max_swaps:
            picked, avenue = find_theme_add(
                remedy.spec,
                synergy_first=not remedy.spine,
                nonland_only=True,
                # A Spine fill ranks efficiency-first with no synergy input at all —
                # role_fix is the ADR-0040 guard that stops that path handing a
                # FOCUSED deck a staple over an in-budget on-avenue candidate.
                role_fix=remedy.spine,
                # A Spine fill's job, so its card read gates the add too (a
                # looter fills no card-draw slot; Skullclamp none in a deck
                # with few bodies to lose).
                job=_SPINE_JOBS.get(issue.kind, issue.role) if remedy.spine else None,
            )
            if picked is None:
                if rejected_hits and not swaps_for_issue:
                    names = ", ".join(dict.fromkeys(rejected_hits))
                    blocked_notes.append(
                        f'No alternative to {names} for "{issue.message}" — '
                        f"{allow_buys}, or allow it again."
                    )
                break
            cut_entry = take_cut(
                remedy.cut_from,
                issue.relies_on,
                filling=issue.role if issue.kind == "role_short" else None,
            )
            if cut_entry is None and remedy.lane_ok:
                cut_entry = take_lane_ok_cut(issue.relies_on)
            if cut_entry is None:
                break  # no appropriate cut for this issue — don't grab a wrong one
            reason, cut = cut_entry
            add_card, cost, off_avenue = picked
            relied_on.update(issue.relies_on)
            if issue.kind == "near_miss_combo":
                combo_adds.update(issue.relies_on)
            commit(
                issue.kind,
                issue.message,
                reason,
                cut,
                add_card,
                cost,
                off_avenue=off_avenue,
                avenue=avenue,
            )
            swaps_for_issue += 1
            # One issue → one swap, except a DRAIN: the dead-weight drain (a deck
            # can carry several do-nothing cards, and it ranks first so the
            # genuinely dead cards go before any role trim churns a functional
            # card) and an over-band trim, whose pool holds exactly the excess.
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
            # identity-only good-stuff search paged by mana value opens on a few
            # hundred CMC-0 lands, and one paged by play-rate on the lands every
            # deck runs — we need to page well past them to find enough distinct
            # nonland cards.
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

    # The proposal read whole: an add whose job runs on the deck (a draw
    # engine's fuel, a narrow team's protection) is read again against the
    # deck the proposal leaves, and dropped when the same proposal's cuts took
    # its fuel — Sephara, Sky's Blade's flyers went to six other swaps
    # (Silverquill Influence, 2026-11-02).
    for i in reversed(_unfueled_adds(committed, deck_records, ctx.commanders)):
        cut, add_card, cost, charged = committed.pop(i)
        dropped = swaps.pop(i)
        search = searches.pop(i)
        if charged:
            ledger.refund(add_card, cost)
        name = add_card.get("name", "")
        unfueled.add(name)
        used_adds[name] -= 1
        count_jobs(add_card, role_of(add_card, deck_mana=ctx.deck_mana), -1)
        if cut is None:
            continue
        used_cuts[cut.name] -= 1
        count_jobs(cut.record, cut.roles, 1)
        # The cut takes its next-best add from the same search, fuelled in the
        # deck the proposal leaves: four guide cuts fell with their unfuelled
        # adds before (Thought Monitor, Narci, Eureka Moment, Treasure Cruise,
        # 2026-11-02).
        repick = _next_fueled_add(
            search, cut, find_add, committed, deck_records, ctx.commanders, unfueled
        )
        if repick is None:
            continue
        new_card, new_cost, off_avenue = repick
        commit(
            dropped["issue"],
            dropped["reason"].replace(name, new_card.get("name", "")),
            (dropped["cut"] or {}).get("why", ""),
            cut,
            new_card,
            new_cost,
            off_avenue=off_avenue,
        )
        # ``commit`` appends; the swap goes back where the dropped one stood.
        swaps.insert(i, swaps.pop())
        committed.insert(i, committed.pop())
        searches.insert(i, searches.pop())

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
