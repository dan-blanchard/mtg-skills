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
"""

from __future__ import annotations

import math
import statistics
import sys
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis.budgets import COMMANDER_TEMPLATE, Template
from mtg_utils._analysis.card_quality import quality
from mtg_utils._analysis.card_reads import has_trees
from mtg_utils._analysis.commander_need import (
    Need,
    grants_all_creature_types,
    is_broad,
    need_serve,
    satisfies,
    typal_payoff_for,
)
from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils._analysis.job_quality import JobRead, read_for
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._analysis.roles import DeckMana, protects, role_of
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._analysis.signal_specs import (
    pages_by_serve,
    serve_page_search,
    theme_page,
)
from mtg_utils._analysis.signals import grant_payloads_for
from mtg_utils._card_ir.creature_types import CREATURE_TYPES
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    iter_cost_leaves,
    iter_typed_nodes,
    tag_of,
    trigger_def_event,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._tuner import mana_base
from mtg_utils._tuner.ability_quality import grant_grade, outgrades
from mtg_utils._tuner.classify import CardClass, is_premium
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
    cut_over,
    is_flip,
    over_role,
    polymorph_flip_types,
    upgrade_job,
)
from mtg_utils._tuner.mana_base import LandPlan
from mtg_utils._tuner.metrics import NEUTRAL_KEYS, NO_FEEDER_READ, payoff_feeders
from mtg_utils.card_classify import (
    color_sources,
    extract_price,
    is_basic_land,
    is_land,
    land_search_fixes,
)
from mtg_utils.card_search import edhrec_popularity
from mtg_utils.deck import split_type_line
from mtg_utils.formats import Coverage, Format
from mtg_utils.theme_presets import _signal_idents_for


# Worst-possible play-rate sentinel (an unranked card sorts last on the quality axis).
def _quality(card: dict, *, playrate: bool) -> int:
    """The quality tiebreak between candidates of equal synergy / cost: play-rate
    where it means something (``playrate`` — edhrec_rank is a paper-EDH population,
    the Commander family's one popularity lean, by user direction), else neutral,
    so price alone breaks the tie for a 60-card or limited deck."""
    return edhrec_popularity(card) if playrate else 0


#: The mana-value bands a Spine fill ranks within when play-rate means something:
#: cheap (0-3: the one-mana removal, the two-mana rocks, the three-mana wipes and
#: draw engines), mid (4-5: the four-mana wraths) and top (6+).
_MV_BANDS: tuple[float, ...] = (3.0, 5.0)


#: The share of a card's job its deck must fuel for the card to count as doing
#: the job there (``JobRead.deck_fit``; card draw's engines). On the 25 precons
#: (2026-10-19) Skullclamp's fit split at 0.39 (Abzan Armor) and below versus
#: 0.58 (Quick Draw) and above, where every guide that adds it sits, so any floor
#: in that gap reads the same; 0.5 is its middle, not a tuned value.
_DECK_FIT_FLOOR = 0.5
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

#: How close two cards' job-read scores (log10 play-rate units) must be for theme
#: fit to decide between them (``JobRead.theme_ties``): about a quarter of the
#: spread between a niche draw engine and a staple one (Garruk's Uprising 0.63,
#: Guardian Project 0.58, Esper Sentinel 0.98). Dan's call (2026-10-23): when a
#: staple and an on-theme card do a job about equally well, the on-theme card
#: wins. Measured on the 25 precons (2026-10-24): for card draw, guide-matching
#: adds 39 to 42, Garruk's Uprising out of 3 decks; for ramp, 39 to 41; for
#: removal 38, wipes 39 (one wipe match lost), protection unchanged — so those
#: three keep their order.
_THEME_TIE = 0.1
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

#: How close a later candidate's play-rate (log10 EDHREC rank, the job reads'
#: unit) must be to the first pick's for the cheaper of them to be the add
#: (``find_add``, :func:`_near_tie`): within a factor of two in rank. A near
#: tie spent at the lower price leaves budget for the issues after it — 47
#: guide adds a page held were lost to what was left of the budget, and Timey
#: Wimey stopped at 12 swaps on expensive payoffs. Measured on the 25 precons
#: (2026-10-24, against 479 swaps / 179 guide-matching cuts / 56 guide-matching
#: adds): 0.1 took 512 / 186 / 56, 0.2 538 / 192 / 59, 0.3 546 / 195 / 60, and
#: 0.5 569 / 199 / 61 — wider keeps gaining, but a threefold rank gap is no tie.
#: The near tie weighs only a first pick past an even share of what is left
#: (``_Purse.share``), and before it the first card in the window that fits the
#: share: a precon tune bound by its budget spent half of it on one card-draw
#: or protection staple (Esper Sentinel $55, Rhystic Study $68, Deflecting Swat
#: $71; $637 for two guide adds), and an unbound one gave up Victimize for a
#: cheaper near tie it never needed. Measured on the 25 precons (2026-10-25,
#: against 543 / 195 / 59): 560 / 197 / 66.
_CHEAPER_TIE = 0.3
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


#: What an X in a mana cost is worth for banding: an X spell is cast for value at
#: X ≥ 3 (Martial Coup wants five, Comet Storm three) — a printed mana value of 2
#: would otherwise band Martial Coup with Swords to Plowshares. The lane's own call.
_X_COST_VALUE = 3.0


#: How many mana-value bands above its cut a JOB upgrade may cost: one. A
#: four- or five-mana wipe may be upgraded to a top-band one (Blame Game trades
#: Winds of Rath for Blasphemous Act, a guide add), a cheap one only to the
#: middle band. Measured on the 25 precons (2026-10-24): one band higher
#: for job upgrades took the guide-matching adds from 39 to 43 and cuts from 158 to
#: 161; for theme upgrades as well, 41 and 161, so a theme upgrade of a card already
#: on the main theme keeps its band. One serving no main theme gets the room too
#: (``off_theme``, :func:`_upgrades`): three guide adds more and one guide cut
#: (2026-10-25).
_JOB_BAND_ROOM = 1


def flip_floor_band(
    deck_records: Sequence[Mapping], flip_types: frozenset[str]
) -> int | None:
    """The mana-value band (:func:`_mv_band`) a polymorph deck's creature or
    planeswalker ADD must reach — one band under the deck's median flip — or
    ``None`` with no polymorph commander or no flips in the deck. Every such
    card in the library is what the polymorph reveals (Jace's -3 has no
    mana-value gate), so a cheap one added for any other reason is a whiff
    beside the deck's bombs: the Jace precon's flips run 6 to 10 mana, median
    7, so a 4-mana add passes and a 3-mana one does not. A fodder card is read
    by the fodder page, not this floor (``find_add``)."""
    bands = [_mv_band(r) for r in deck_records if is_flip(r, flip_types)]
    if not bands:
        return None
    return max(0, int(statistics.median(bands)) - 1)


def over_band(
    candidate: Mapping, cut: Mapping, job: str | None, *, off_theme: bool = False
) -> bool:
    """Whether ``candidate`` costs more than an upgrade of ``cut`` for ``job``
    may: a higher mana-value band (:func:`_mv_band`) than the cut's, by more than
    ``_JOB_BAND_ROOM`` for a job upgrade or one moving an ``off_theme`` card's
    slot onto the main theme."""
    room = _JOB_BAND_ROOM if job is not None or off_theme else 0
    return _mv_band(candidate) > _mv_band(cut) + room


def _mv_band(card: Mapping) -> int:
    """The index of the band the card's cost falls in (``_MV_BANDS``), so a Spine
    fill is ranked by play-rate among its peers in cost rather than by exact mana
    value, where a {0} cost reads as the cheapest card that does the job. An X in
    the cost counts ``_X_COST_VALUE`` (CR 202.3e: X is treated as 0 while the
    object is not on the stack, so a printed mana value never shows what the
    spell is cast for)."""
    cmc = float(card.get("cmc") or 0.0)
    if "{X}" in (card.get("mana_cost") or ""):
        cmc += _X_COST_VALUE
    return sum(1 for top in _MV_BANDS if cmc > top)


def _blended_percentiles(
    cards: Sequence[dict], job: str | None, deck: Sequence[dict] | None = None
) -> dict[str, float]:
    """For the cards ``job``'s read scores: the read's percentile among them plus
    their play-rate percentile — the order an ordering job's candidates take
    (``JobRead.orders``). A percentile is the share of the cards strictly below,
    so cards that tie share one, whatever order ``cards`` came in. Given
    ``deck`` (its cards' records), the read is the one in that deck
    (``JobRead.score``'s deck fit)."""
    read = read_for(job)
    if read is None:
        return {}
    scored = [(c, s) for c in cards if (s := read.score(c, deck)) is not None]
    if not scored:
        return {}
    n = len(scored)
    reads = sorted(s for _c, s in scored)
    plays = sorted(-edhrec_popularity(c) for c, _s in scored)
    # J2 (2026-10-31): the card's quality read (``card_quality``, by its type) as
    # a third percentile beside the job read's and play-rate's; a card no read
    # sees sits at the middle.
    from mtg_utils._analysis.card_quality import quality

    quals = sorted(q for c, _s in scored if (q := quality(c)) is not None)

    def quality_pos(c: dict) -> float:
        q = quality(c)
        return bisect_left(quals, q) if q is not None else n / 2

    return {
        c.get("name", ""): (
            bisect_left(reads, s)
            + bisect_left(plays, -edhrec_popularity(c))
            + quality_pos(c)
        )
        / n
        for c, s in scored
    }


def _near_tie(a: dict, b: dict, read: JobRead | None, deck: Sequence[dict]) -> bool:
    """Whether ``b`` does about as well as ``a``: their play-rates within
    ``_CHEAPER_TIE`` (log10 EDHREC rank) and, for a job whose read orders its
    candidates (``read``), their read scores within ``_THEME_TIE``."""
    gap = math.log10(edhrec_popularity(a)) - math.log10(edhrec_popularity(b))
    if abs(gap) > _CHEAPER_TIE:
        return False
    if read is None:
        return True
    sa, sb = read.score(a, deck), read.score(b, deck)
    return sa is not None and sb is not None and abs(sa - sb) <= _THEME_TIE


def _does_the_job(
    card: dict, job: str | None, deck: Sequence[dict], cut: dict | None = None
) -> bool:
    """Whether ``card`` does ``job`` by its card read (``job_quality``), in a deck
    that fuels at least ``_DECK_FIT_FLOOR`` of it — true for a job with no read,
    for a card the read can't see at all (no concept trees: a set newer than the
    phase pin), which its template role already vouched for, and for a read of
    part of the job (removal, of interaction) unless it reads the ``cut``."""
    read = read_for(job)
    if read is None or not has_trees(card):
        return True
    if not read.whole_job and (cut is None or read.score(cut) is None):
        return True
    return read.score(card) is not None and read.deck_fit(card, deck) >= _DECK_FIT_FLOOR


def _reads_worse_at_the_job(
    candidate: dict, cut: dict, job: str, deck: Sequence[dict] | None
) -> bool:
    """Whether the job's card read (``job_quality``) scores ``candidate`` below
    ``cut`` in ``deck`` at no lower mana value. The read decides membership
    and play-rate orders (ADR-0060), but a job upgrade costing as much that
    does the job less well than the card it replaces is a swap for its own
    sake: Golgari Signet went to Fellwar Stone, whose colors are an
    opponent's lands' (Death Toll, 2026-11-02). A cheaper card is a tempo
    upgrade whatever the read says of its reach (Duplicant for Meteor Golem);
    a card either read can't see (no trees) is not held to it."""
    read = read_for(job)
    if read is None or not has_trees(candidate) or not has_trees(cut):
        return False
    if job == "ramp" and _one_shot_for_repeatable(read, candidate, cut):
        return True
    cand_cost, cut_cost = _job_cost(read, candidate), _job_cost(read, cut)
    if cand_cost < cut_cost and _cost_band(cand_cost) == _cost_band(cut_cost):
        return False
    records = deck or ()
    sc, su = read.score(candidate, records), read.score(cut, records)
    return sc is not None and su is not None and sc < su - 1e-9


def _one_shot_for_repeatable(read: JobRead, candidate: dict, cut: Mapping) -> bool:
    """Whether ``candidate`` is a one-shot mana source (a ritual, Lotus Petal:
    the ramp read's ``per_turn`` zero and no land) replacing a repeatable one —
    a downgrade whatever it costs: Wild Growth went to Lotus Petal (Deadly
    Disguise), Azorius Signet to Dark Ritual (Multiverse Reforged), Millikin to
    Simian Spirit Guide (Lorehold Spirit; 2026-11-02)."""
    a, b = read.features(candidate), read.features(dict(cut))
    if not a or a.get("per_turn", 0) > 0 or a.get("land", 0) > 0:
        return False
    # A cut the read can't itemise (Millikin's mill-cost mana, a ramp role all
    # the same) is repeatable for all a one-shot knows; so is a conditional
    # engine (Relic Retriever's Treasures).
    return b is None or any(
        b.get(k, 0) > 0 for k in ("per_turn", "land", "cond_engine")
    )


def _lateral_at_the_job(candidate: dict, cut: Mapping, job: str) -> bool:
    """Whether ``candidate`` is the cut in another coat: the same job read, the
    same deploy cost and as many colors — Talisman of Creativity for Talisman
    of Curiosity in a Temur deck (Living Energy), Pongify for Rapid
    Hybridization (Explorers of the Deep; 2026-11-02). Arcane Signet's
    any-color mana is more colors than a Signet's two, so it stays an
    upgrade; a read that differs at all is play-rate's to order."""
    read = read_for(job)
    if read is None or not has_trees(candidate) or not has_trees(cut):
        return False
    sc, su = read.score(candidate), read.score(dict(cut))
    if sc is None or su is None or abs(sc - su) > 1e-9:
        return False
    if _job_cost(read, candidate) != _job_cost(read, dict(cut)):
        return False
    return _color_count(candidate) == _color_count(cut)


def _color_count(card: Mapping) -> int:
    """How many colors the card's mana reaches (five for "any"), else how many
    colors it is."""
    sources = color_sources(dict(card))
    if sources:
        return 5 if "any" in sources else len(sources - {"C"})
    return len(card.get("color_identity") or [])


def _cost_band(cost: float) -> int:
    """The mana-value band (``_MV_BANDS``) a deploy cost falls in: the cheaper
    exemption of :func:`_reads_worse_at_the_job` holds within one band only —
    Duplicant's six for Meteor Golem's seven, Toxic Deluge's three for Damn's
    overloaded four — never across two: Thrill of Possibility's two for
    Niv-Mizzet, Parun's six drew a card-draw engine down to a cantrip (Quick
    Draw, 2026-11-02)."""
    return sum(1 for top in _MV_BANDS if cost > top)


def _job_cost(read: JobRead, card: dict) -> float:
    """What deploying ``card`` for its job costs: the read's own ``cost``
    feature where it has one (the ramp read counts Wayfarer's Bauble's
    activation — three, not its printed one, so a Signet is no card it
    undercuts), else the mana value on the curve."""
    features = read.features(card)
    if features and "cost" in features:
        return float(features["cost"])
    return effective_mana_value(card)


def _upgrades(
    candidate: dict,
    cut: CardClass,
    job: str | None,
    *,
    deck_mana: DeckMana | None = None,
    deck: Sequence[dict] | None = None,
    off_theme: bool = False,
    draw_engine: bool = False,
    needs: Callable[[Mapping], int] | None = None,
) -> bool:
    """Whether ``candidate`` is an upgrade of ``cut``: it costs no higher
    mana-value band, or for a job one band higher at most (:func:`over_band` — a
    two-mana removal spell is not upgraded to a six-mana one, nor a one-drop to
    a seven-drop on the main theme), for a job
    (``upgrade_job``) it does that same job — card draw is not upgraded to a
    counterspell that draws — and, where the job has a card read
    (``job_quality.read_for``), does it by that read (a looter is no card-draw
    upgrade) — in ``deck`` (its cards' records), a read with a deck fit also needs
    the deck to fuel at least ``_DECK_FIT_FLOOR`` of the job (Skullclamp in a deck
    with few bodies to lose is no draw engine); and more decks play it than the
    cut. The read decides membership, not "better": against the precon guides'
    cuts it found the weaker card less often than play-rate did, for every job,
    and "scores better than the cut" in play-rate's place matched no more guide
    adds for any job (ADR-0060).

    ``off_theme`` is a cut serving none of the deck's main avenues. With no job,
    its add comes off the main theme, and moving the slot onto the main theme is
    the upgrade: the add need not be more played than the cut (an Energy card is
    played less than Whirler Rogue, which an Energy deck's sub-theme ran), and it
    may cost one band higher, as a job upgrade may.

    A Granter is judged by its grant (ADR-0040 §4): with no job, its slot may go
    to a card whose grant grades higher (:func:`ability_quality.outgrades`;
    ``draw_engine``: the commander is a repeatable draw engine, as the deck's
    Granters were graded) at no higher band, however few decks play it (Sliver
    Swarm's Megantic Sliver, an anthem, for Pulmonic Sliver's flying); play-rate
    decides between grants of one grade. Measured on the 25 precons (2026-10-26):
    two guide cuts more, adds flat.

    ``needs`` counts the commander's specific needs a card supplies
    (``commander_need``, ADR-0061): with no job, a candidate supplying more of
    them than the cut is an upgrade however few decks play it — Felothar's
    walls (Stalwart Shield-Bearers, Wall of Souls) over the big-butt staples a
    toughness page is otherwise ranked by (Gray Merchant of Asphodel), which
    the guides add and play-rate gated out (Abzan Armor, 2026-11-01). The
    commander's own text outranks the population's habits on its theme pages.
    And whatever the job, an upgrade keeps what the cut gives the commander: a
    candidate supplying fewer of the needs is none — Living Death (cards leave
    Teval's graveyard) is no interaction slot for Assassin's Trophy, Squirrel
    Nest (Hazel's Squirrel tokens) none for Fanatic of Rhonas (2026-11-01)."""
    if over_band(candidate, cut.record, job, off_theme=off_theme):
        return False
    if job is not None and (
        upgrade_job(role_of(candidate, deck_mana=deck_mana), candidate) != job
    ):
        return False
    if not _does_the_job(candidate, job, deck or (), cut.record):
        return False
    # The job the read holds the swap to: the page's, or on a theme page the
    # cut's own (Niv-Mizzet, Parun draws; a theme card that draws nothing is
    # not held to it, a candidate that does none of the job moves the slot
    # onto the theme as the docstring allows, and an off-theme slot leaves
    # its role by design).
    read_job = (
        job if job is not None or off_theme else upgrade_job(cut.roles, cut.record)
    )
    if read_job is not None and _reads_worse_at_the_job(
        candidate, cut.record, read_job, deck
    ):
        return False
    if read_job is not None and _lateral_at_the_job(candidate, cut.record, read_job):
        return False
    if needs is not None and needs(candidate) < needs(cut.record):
        return False
    # A jobless cut (a theme card, a body) is never traded down: the two
    # admissions below that ignore play-rate — moving an off-theme slot onto
    # the theme, and more of what the commander asks — both stop at a
    # candidate the card-quality read rates below it. Zetalpa, Primal Dawn
    # (toughness 8, off Felothar's defender lane, his toughness need too broad
    # to page) went to Shield-Wall Sentinel by each in turn (2026-11-02);
    # Jaddi Offshoot's Stalwart Shield-Bearers reads no weaker and still
    # moves. A job card's quality (``upgrade_job``: a template role or
    # protection) is read against its job, so a full job's slot moving onto
    # the theme is not held to it.
    trades_down = (
        job is None
        and upgrade_job(cut.roles, cut.record) is None
        and _weaker_on_its_text(candidate, cut.record)
    )
    if job is None and off_theme and not trades_down:
        return True
    if (
        job is None
        and needs is not None
        and needs(candidate) > needs(cut.record)
        and not trades_down
    ):
        return True
    if (
        job is None
        and cut.grant_grade is not None
        and outgrades(
            _grant_grade_of(candidate, draw_engine=draw_engine), cut.grant_grade
        )
    ):
        return True
    if (
        job is None
        and not off_theme
        and _mv_band(cut.record) - _mv_band(candidate) > _JOB_BAND_ROOM
    ):
        # A theme slot upgraded on play-rate alone stays within a band of its
        # cost downward too: Garruk, Cursed Huntsman's six went to Chatter of
        # the Squirrel's one as the more-played Squirrel card (Squirreled
        # Away, 2026-11-02) — a top-end payoff's slot is not a cantrip's. A
        # job page and an off-theme move keep their own band rules.
        return False
    rank = candidate.get("edhrec_rank")
    return rank is not None and (cut.edhrec_rank is None or rank < cut.edhrec_rank)


def _weaker_on_its_text(candidate: dict, cut: Mapping) -> bool:
    """Whether the card-quality read (ADR-0063) rates ``candidate`` below
    ``cut``; False when either has no read."""
    a, b = quality(candidate), quality(dict(cut))
    return a is not None and b is not None and a < b


#: A candidate's Granter grade per (oracle id, draw-engine commander): a pure
#: function of the card, asked of the same theme pages by every Granter cut.
_GRANT_GRADES: dict[tuple[str, bool], str | None] = {}


def _grant_grade_of(card: dict, *, draw_engine: bool) -> str | None:
    """``card``'s Granter grade (``None``: no grant), as ``classify`` grades the
    deck's own."""
    key = (card.get("oracle_id") or card.get("name", ""), draw_engine)
    if key not in _GRANT_GRADES:
        _GRANT_GRADES[key] = grant_grade(
            grant_payloads_for(card), draw_engine_commander=draw_engine
        )
    return _GRANT_GRADES[key]


def _fills_short_role(card: CardClass, budgets: dict) -> bool:
    """True if the card fills a role already at/below its floor — cutting it would drop
    that role below the template minimum, so it is never a safe trim (e.g. don't cut the
    lone board wipe to fix interaction overflow)."""
    return any(
        budgets.get(r, {}).get("current", 0) <= budgets.get(r, {}).get("min", 0)
        for r in card.roles
    )


#: The deck cards that do what a payoff cares about for the payoff to be alive
#: there; a tribe needs twice as many creatures sharing the type for a
#: choose-a-type payoff (Door of Destinies). The ``_NEED_BUILT_FLOOR`` line.
_FEEDER_FLOOR = 5
#: The CR's creature types (CR 205.3m), lower-cased — not the bulk-harvested
#: ``CREATURE_SUBTYPES``, which picks up Food and Equipment off artifact
#: creature faces.
_CREATURE_SUBTYPE_WORDS = frozenset(s.lower() for s in CREATURE_TYPES)
#: The doers a multiplier needs in the deck to be alive there: twice the floor
#: (:func:`dead_payoff`).
_MULTIPLIER_FEEDER_FLOOR = 2 * _FEEDER_FLOOR
#: The payoffs that multiply what the deck already does, and so never feed
#: themselves (:func:`dead_payoff`).
_MULTIPLIER_KEYS = frozenset(
    {"counter_doubling", "counter_replace_bonus", "token_doubling"}
)
#: The card types (and the one supertype) a payoff's unit is gated on beside a
#: creature type: a spellslinger's instants and sorceries (Talrand), an
#: artifact or enchantment cast (Sai, Master Thopterist; Starfield Mystic),
#: legends (Rising of the Day). Fed by :data:`_TYPE_GATE_FLOOR` cards of the
#: type — a quarter of the nonlands; twelve artifacts make no artifact deck
#: (Riders of Rohan's Sai, 2026-11-02) — where a creature type or a gear type
#: (Equipment, Aura) is fed by :data:`_FEEDER_FLOOR` (:func:`_unit_gates`).
_GATE_TYPE_WORDS = frozenset(
    {"instant", "sorcery", "artifact", "enchantment", "planeswalker", "legendary"}
)
_TYPE_GATE_FLOOR = 15
#: A land type gates nothing (Farseek's Plains, Knight of the White Orchid's).
_LAND_TYPE_WORDS = frozenset(s.lower() for s in LAND_SUBTYPES)
#: The type words every deck has: no gate (Asceticism's creatures).
_GENERIC_TYPE_WORDS = frozenset(
    {"creature", "permanent", "card", "spell", "land", "token", "kindred", "tribal"}
)
#: A gate on your permanents with +1/+1 counters (Inspiring Call's draw), fed
#: by the deck's counter makers; and one on your creature tokens (Intangible
#: Virtue's anthem), fed by the deck's creature-token makers — Clues and
#: Treasures are no creatures (Deep Clue Sea, 2026-11-02).
_COUNTERS_GATE = "+1/+1 counters"
_CREATURE_TOKENS_GATE = "creature tokens"
#: A gate on a color of your spells (Oketra's Monument's white creature
#: spells — a colorless card, dead in Golgari), fed by :data:`_TYPE_GATE_FLOOR`
#: cards of the color; the word is ``color:<letter>``.
_COLOR_LETTERS = {"white": "w", "blue": "u", "black": "b", "red": "r", "green": "g"}
_COUNTER_GATE_FEEDERS = frozenset({"plus_one_makers", "any_counter_makers"})
#: A gate on an opponent's discard (Waste Not's three triggers), fed by the
#: deck's discard makers; the event is the gate where the discarded card's
#: type is generic (2026-11-02).
_OPP_DISCARD_GATE = "opponents discard"
_OPP_DISCARD_FEEDERS = frozenset({"opponent_discard", "discard_makers"})
#: The library effects whose filter is over YOUR cards though it carries no
#: controller: Heroes' Podium's legendary creature from the top, Open the
#: Armory's Aura or Equipment.
_LIBRARY_EFFECTS = frozenset({"Dig", "SearchLibrary"})


def deck_profile(classes: Sequence[CardClass]) -> tuple[Counter, Counter, Counter]:
    """What the deck does, for :func:`dead_payoff`: its signal keys by the
    cards carrying them, its creatures' subtypes by count, and its cards'
    other type words by count — card types and supertypes (``instant``,
    ``artifact``, ``legendary``) and non-creature subtypes (``equipment``,
    ``aura``, ``food``), the gates :func:`_unit_gates` reads."""
    keys: Counter = Counter()
    tribes: Counter = Counter()
    types: Counter = Counter()
    for c in classes:
        for ident in _signal_idents_for(c.record, include_membership=False):
            keys[ident.split("|", 1)[0]] += 1
        words, subs = split_type_line(c.record.get("type_line") or "")
        lowered = {w.lower() for w in words}
        if "creature" in lowered:
            for sub in subs:
                tribes[sub.lower()] += 1
        for word in lowered | {
            s.lower() for s in subs if s.lower() not in _CREATURE_SUBTYPE_WORDS
        }:
            types[word] += 1
        if any(
            i.startswith(f"{TOKEN_MAKER}|")
            and i.split("|", 2)[2].lower() in _CREATURE_SUBTYPE_WORDS
            for i in _signal_idents_for(c.record, include_membership=False)
        ):
            types[_CREATURE_TOKENS_GATE] += 1
        for color in c.record.get("colors") or ():
            types[f"color:{str(color).lower()}"] += 1
    # A commander that makes permanents every creature type (Omo, Queen of
    # Vesuva's everything counters) fields every tribe: a lord, a tribal
    # trigger or a choose-a-type card is fed whatever the type line says, as
    # the guides' Roaming Throne and Coat of Arms for Tricky Terrain are
    # (2026-11-02).
    if any(
        c.bucket == "commander" and grants_all_creature_types(c.record) for c in classes
    ):
        for word in _CREATURE_SUBTYPE_WORDS:
            tribes[word] = max(tribes[word], 2 * _FEEDER_FLOOR)
    return keys, tribes, types


def dead_payoff(
    card: Mapping, deck_keys: Counter, deck_tribes: Counter, deck_types: Counter
) -> bool:
    """Whether ``card`` is a payoff for what the deck doesn't do: every
    mechanic it cares about has fewer than :data:`_FEEDER_FLOOR` doers in the
    deck (``metrics.payoff_feeders``), the card feeds none of them itself, and
    it does nothing else on its own (no doer key beyond the structural ones,
    :data:`metrics.NEUTRAL_KEYS`, and the feeders of its own multipliers —
    Hardened Scales' extra counter is tagged a counter maker). A
    choose-a-creature-type payoff with no tribe of ten in the deck (Banner of
    Kinship, Door of Destinies, Coat of Arms under Bello), a counter doubler
    where nothing places counters. Not Etali (its poison payoff fed by its own
    poison, and a doer besides), Myr Battlesphere (its Myr are its own
    tokens), Birgi (boast unfed, but a mana doer), Farseek (a Plains is no
    tribe); a card caring about nothing the read names is never dead
    (2026-11-02).

    A unit gated on a type the deck lacks is as dead as one gated on a tribe
    (:func:`_unit_gates`): Docent of Perfection's Wizards wait on instants and
    sorceries an Eldrazi deck casts thirteen of, Puresteel Paladin's draw on
    Equipment a Humans deck holds two of, Death Baron's anthem on Zombies a
    Party deck has none of (2026-11-02)."""
    idents = _signal_idents_for(dict(card), include_membership=False)
    own_keys = {i.split("|", 1)[0] for i in idents}
    makes_tokens = any(i.startswith(f"{TOKEN_MAKER}|") for i in idents)
    own_subtypes = {w.lower() for w in split_type_line(card.get("type_line") or "")[1]}
    feeders = payoff_feeders()
    verdicts: list[bool] = []
    cares: set[str] = set()
    gated = _unit_gates(card)
    for ident in idents:
        key, scope, subject = ident.split("|", 2)
        chooses_a_type = key == "chosen_type_matters" or (
            key == "subtype_ref" and subject == "shared"
        )
        if chooses_a_type:
            cares.add(key)
            biggest_tribe = max(deck_tribes.values(), default=0)
            verdicts.append(biggest_tribe >= 2 * _FEEDER_FLOOR)
        elif key == "subtype_ref":
            # A creature type the card names among YOUR permanents (Dragon
            # Tempest's Dragons); a land type (Farseek's Plains), a gear type
            # (Sram's Auras) or another player's is no tribe the deck fields.
            # Where the trees show the gates, they are the read: Docent of
            # Perfection's Wizard tokens arrive only on the spells its gated
            # trigger waits for, so they feed no Wizard reference of its own.
            sub = subject.lower()
            if scope != "you" or sub not in _CREATURE_SUBTYPE_WORDS or gated.gates:
                continue
            cares.add(key)
            verdicts.append(
                makes_tokens
                or sub in own_subtypes
                or deck_tribes.get(sub, 0) >= _FEEDER_FLOOR
            )
        elif (fed_by := feeders.get(key)) is not None:
            cares.add(key)
            multiplier = key in _MULTIPLIER_KEYS
            self_fed = not multiplier and bool(fed_by & own_keys)
            # A doubler is for what the deck does a lot: twice the floor.
            # Anikthea's five incidental counter cards kept Hardened Scales and
            # Branching Evolution alive on her page; Hazel's eighteen token
            # makers keep Doubling Season (2026-11-02).
            floor = _MULTIPLIER_FEEDER_FLOOR if multiplier else _FEEDER_FLOOR
            verdicts.append(
                self_fed or sum(deck_keys.get(f, 0) for f in fed_by) >= floor
            )
    # A unit gated on a creature type (Dragon Tempest's "whenever a Dragon
    # you control enters"), a card type or a gear type: the gate lives in the
    # IR, not in a key. Fed by the deck's cards of the type, the card's own
    # type, or its own tokens.
    for gate in gated.gates:
        cares.add("unit_gate")
        verdicts.append(gated.fed(gate, deck_tribes, deck_types, deck_keys))
    if not verdicts or any(verdicts):
        return False
    if gated_without_feed(card, deck_tribes, deck_types, deck_keys):
        return True
    multiplier_feeders = frozenset().union(
        *(feeders.get(k, frozenset()) for k in cares & _MULTIPLIER_KEYS)
    )
    # The umbrella payoffs (Door of Destinies' "whenever you cast a spell of
    # the chosen type" is ``spellcast_matters``) are no doing of their own.
    doers = own_keys - cares - NEUTRAL_KEYS - NO_FEEDER_READ - multiplier_feeders
    return not doers


@dataclass(frozen=True)
class _Gate:
    """One gated unit's words (a creature type, a card type, a gear type, a
    counters or creature-tokens gate; any word fed feeds the gate) and whether
    the unit is a static."""

    words: frozenset[str]
    static: bool


@dataclass(frozen=True)
class _UnitGates:
    """What :func:`_unit_gates` read off one card: its ``gates``; ``units`` —
    its triggers, statics and abilities; whether it has an ``activated``
    ability no gate holds; and what feeds its own gates — the types its
    statics grant (Ygra's Food) feed any gate; the token kinds it makes feed a
    trigger's or an ability's (Myr Battlesphere's Myr are its own; Krenko's
    Goblins) but not a static's (Docent of Perfection's Wizard anthem waits on
    the Wizards its spell trigger never makes). Its own type feeds nothing: a
    Zombie lord's anthem for other Zombies is for nobody (Death Baron), and
    Scourge of Valkas's one Dragon is itself (Endless Punishment,
    2026-11-02)."""

    gates: tuple[_Gate, ...]
    units: int
    activated: bool
    granted_words: frozenset[str]
    token_words: frozenset[str]
    makes_tokens: bool

    def fed(
        self,
        gate: _Gate,
        deck_tribes: Counter,
        deck_types: Counter,
        deck_keys: Counter | None = None,
    ) -> bool:
        """Whether the deck feeds ``gate``: a creature type by
        :data:`_FEEDER_FLOOR` creatures of it or, for a trigger's or ability's
        gate, the card's own tokens; a card type by :data:`_TYPE_GATE_FLOOR`
        cards of it — an instant-or-sorcery gate by their sum; a counters gate
        by :data:`_FEEDER_FLOOR` counter makers (``deck_keys``); a gear or
        other subtype, or the creature-tokens gate, by :data:`_FEEDER_FLOOR`
        cards or the kind the card grants."""
        words = gate.words
        if words & self.granted_words or (not gate.static and words & self.token_words):
            return True
        card_types = words & _GATE_TYPE_WORDS
        if (
            card_types
            and sum(deck_types.get(w, 0) for w in card_types) >= _TYPE_GATE_FLOOR
        ):
            return True
        for word in words - _GATE_TYPE_WORDS:
            if word.startswith("color:"):
                if deck_types.get(word, 0) >= _TYPE_GATE_FLOOR:
                    return True
            elif word == _OPP_DISCARD_GATE:
                keys = deck_keys or Counter()
                if sum(keys.get(k, 0) for k in _OPP_DISCARD_FEEDERS) >= _FEEDER_FLOOR:
                    return True
            elif word == _COUNTERS_GATE:
                keys = deck_keys or Counter()
                if sum(keys.get(k, 0) for k in _COUNTER_GATE_FEEDERS) >= _FEEDER_FLOOR:
                    return True
            elif word in _CREATURE_SUBTYPE_WORDS:
                if (not gate.static and self.makes_tokens) or deck_tribes.get(
                    word, 0
                ) >= _FEEDER_FLOOR:
                    return True
            elif deck_types.get(word, 0) >= _FEEDER_FLOOR:
                return True
        return False


def _gate_words(filt: object) -> frozenset[str]:
    """The gate words of a unit's filter: its subtypes (a creature type, a
    gear type), its card types in :data:`_GATE_TYPE_WORDS`, and a legendary
    supertype — never a land type or a word every deck has."""
    words = {w.lower() for w in filter_subtypes(filt)}
    cores = {w.lower() for w in filter_core_types(filt)}
    words |= cores & _GATE_TYPE_WORDS
    if any(
        tag_of(n) == "HasSupertype" and getattr(n, "value", None) == "Legendary"
        for n in iter_typed_nodes(filt)
    ):
        words.add("legendary")
    preds = filter_predicates(filt)
    for n in iter_typed_nodes(filt):
        if tag_of(n) == "HasColor":
            letter = _COLOR_LETTERS.get(str(getattr(n, "color", "")).lower())
            if letter:
                words.add(f"color:{letter}")
    if "Counters" in preds:
        words.add(_COUNTERS_GATE)
    if "Token" in preds and "creature" in cores:
        words.add(_CREATURE_TOKENS_GATE)
    return frozenset(words - _LAND_TYPE_WORDS - _GENERIC_TYPE_WORDS)


def _ability_gate_words(node: object, effects: Sequence) -> frozenset[str]:
    """The gate words of an activated ability or a spell: a sacrifice in its
    cost names what it feeds on (Skirk Prospector's Goblin, Grinding Station's
    artifact, Sai, Master Thopterist's two artifacts), and an effect over
    permanents of YOURS does (Brass Squire's Equipment you control, Inspiring
    Call's creatures with +1/+1 counters, Krenko's Goblins) — never a target
    among anyone's (Vandalblast's artifacts, Asceticism's creature)."""
    words: set[str] = set()
    for leaf in iter_cost_leaves(getattr(node, "cost", None)):
        if tag_of(leaf) == "Sacrifice":
            target = getattr(leaf, "target", None)
            if _present(target):
                words |= _gate_words(target)
    for c in effects:
        # Every typed filter the effect reaches — its target, an attachment
        # (Brass Squire's Equipment), a count (Inspiring Call's counters); a
        # library effect's filter is yours with no controller on it.
        library = tag_of(c.node) in _LIBRARY_EFFECTS
        for n in iter_typed_nodes(c.node):
            if tag_of(n) == "Typed" and (library or filter_controller(n) == "You"):
                words |= _gate_words(n)
    return frozenset(words)


def _unit_gates(card: Mapping) -> _UnitGates:
    """The gates on the card's triggers and statics, read off phase's trees
    (the field ``ranking._ir_gate_subtypes`` reads on the compat Card, which
    CI has no sidecar for): the words of a trigger's ``valid_card`` (Dragon
    Tempest's Dragons, Talrand's instants and sorceries, Puresteel Paladin's
    Equipment) or a static's ``affected`` (Death Baron's Skeletons and
    Zombies; a self-only static has none). Empty for a card phase has no
    trees for."""
    gates: list[_Gate] = []
    units = 0
    activated = False
    tokens: set[str] = set()
    made: set[str] = set()
    idents = _signal_idents_for(dict(card), include_membership=False)
    makes_tokens = False
    for ident in idents:
        key, _scope, subject = ident.split("|", 2)
        if key == TOKEN_MAKER:
            makes_tokens = True
            if subject:
                tokens.add(subject.lower())
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            if unit.origin == "ability":
                # An activated ability or a spell, gated by its cost or its
                # effects over your permanents (:func:`_ability_gate_words`);
                # one no gate holds is something to activate whatever the deck.
                units += 1
                words = _ability_gate_words(unit.node, unit.effects)
                if words:
                    gates.append(_Gate(words, static=False))
                elif unit.kind == "Activated" and not all(
                    tag_of(getattr(c.node, "target", None)) == "SelfRef"
                    for c in unit.effects
                ):
                    # A self-only ability (Scourge of Valkas's firebreathing)
                    # is not why the card is played: nothing to activate.
                    activated = True
                continue
            if unit.origin == "trigger":
                filt = getattr(unit.node, "valid_card", None)
                if (
                    isinstance(unit.node, TypedMirrorNode)
                    and trigger_def_event(unit.node) == "discarded"
                    and trigger_scope(unit.node) in ("opponents", "each")
                ):
                    units += 1
                    gates.append(
                        _Gate(
                            (_gate_words(filt) if _present(filt) else frozenset())
                            | {_OPP_DISCARD_GATE},
                            static=False,
                        )
                    )
                    continue
            elif unit.origin == "static":
                filt = getattr(unit.node, "affected", None)
                if tag_of(filt) == "SelfRef":
                    filt = None
                # A cost reduction's spell filter is its gate (Oketra's
                # Monument's white creature spells), beside the affected.
                mode_words: set[str] = set()
                for n in iter_typed_nodes(getattr(unit.node, "mode", None)):
                    if tag_of(n) == "Typed":
                        mode_words |= _gate_words(n)
                # A type the static grants feeds a gate on it: Ygra, Eater of
                # All makes other creatures Food.
                for mod in getattr(unit.node, "modifications", None) or ():
                    if tag_of(mod) == "AddSubtype":
                        made.add(str(getattr(mod, "subtype", "")).lower())
                    elif tag_of(mod) == "AddType":
                        made.add(str(getattr(mod, "core_type", "")).lower())
            else:
                continue
            units += 1
            words = _gate_words(filt) if _present(filt) else frozenset()
            if unit.origin == "static":
                words |= mode_words
            if words:
                gates.append(_Gate(words, static=unit.origin == "static"))
    return _UnitGates(
        tuple(gates), units, activated, frozenset(made), frozenset(tokens), makes_tokens
    )


def gated_without_feed(
    card: Mapping,
    deck_tribes: Counter,
    deck_types: Counter,
    deck_keys: Counter | None = None,
) -> bool:
    """A card gated on what the deck lacks, dead whatever page asks: a
    choose-a-creature-type card (:func:`chooses_a_type_without_tribe`), or a
    card whose triggers and statics are mostly gated on a creature type, card
    type or gear type the deck lacks and that has nothing to activate
    (:func:`_unit_gates`) — whatever they do (Dragon Tempest's damage, a doer
    key) waits on Dragons that never come; its haste for flyers is not why it
    is played (2026-11-02). An activated ability no gate holds keeps a card
    (Asceticism's regeneration); Sai, Master Thopterist's draw costs two
    artifacts, so in a Humans deck it holds nothing."""
    if chooses_a_type_without_tribe(card, deck_tribes):
        return True
    gated = _unit_gates(card)
    if not gated.gates or 2 * len(gated.gates) < gated.units or gated.activated:
        return False
    return not any(
        gated.fed(gate, deck_tribes, deck_types, deck_keys) for gate in gated.gates
    )


def chooses_a_type_without_tribe(card: Mapping, deck_tribes: Counter) -> bool:
    """A choose-a-creature-type card (``chosen_type_matters``: Vanquisher's
    Banner, Kindred Discovery, Herald's Horn) in a deck with no tribe of
    ``2 * _FEEDER_FLOOR`` creatures: every ability it has hangs on the choice,
    its draw and its anthem alike, so it is dead whatever page asks for it —
    Vanquisher's Banner drew nothing for Bello's deck as a card-draw upgrade
    (2026-11-02)."""
    idents = _signal_idents_for(dict(card), include_membership=False)
    if not any(i.startswith("chosen_type_matters|") for i in idents):
        return False
    return max(deck_tribes.values(), default=0) < 2 * _FEEDER_FLOOR


#: A mana doubler's keys: a replacement that adds mana (Mana Reflection) or a
#: trigger on tapping for mana that adds more (Forsaken Monument).
_MANA_DOUBLER_KEYS = frozenset({"mana_amplifier", "tap_untap_matters"})


def _amplifies_mana(card: CardClass) -> bool:
    """Whether the card is a mana doubler (:data:`_MANA_DOUBLER_KEYS`)."""
    return any(
        i.split("|", 1)[0] in _MANA_DOUBLER_KEYS
        for i in _signal_idents_for(card.record, include_membership=False)
    )


def _is_fixing(card: CardClass) -> bool:
    """A ramp source that fixes COLORS — a premium dork/rock/land-fetch the deck's mana
    base leans on (Birds of Paradise, Arcane Signet, Kodama's Reach). It reads as ramp,
    but trimming it for ramp-overflow strands the color base, so the over-band ramp cut
    sorts these LAST (cut redundant single-purpose ramp first).

    Fixing = produces ≥2 colors of battlefield mana, OR is a basic-land fetch (which
    produces no mana itself but retrieves the color the deck needs — produced_mana would
    miss it, so the worse 2-color rock was being protected while the any-basic fetcher,
    which fixes ALL the deck's colors, was cut first).

    A land search fixes by ``card_classify.land_search_fixes`` (the one rule
    ``is_fixing_land`` reads too)."""
    produced = card.record.get("produced_mana") or []
    if len({c for c in produced if c in "WUBRG"}) >= 2:
        return True
    return land_search_fixes(card.record)


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
    for c in sorted(
        (c for c in classes if c.bucket == "filler"),
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


_WC_TIERS: tuple[str, ...] = ("mythic", "rare", "uncommon", "common")


class _Purse(Protocol):
    """An acquisition budget, probed read-only then charged on commit. It prices only
    copies the collection does NOT cover — the caller decides coverage once, by
    ``Format.copies_short`` — and each purse reads what it needs from the record."""

    def acquire_cost(self, record: dict) -> float | None:
        """The cost of one uncovered copy, or None when unaffordable."""

    def charge(self, record: dict, cost: float) -> None: ...

    def share(self, adds: int) -> float:
        """An even share of what is left over ``adds`` more adds: an add priced
        within it leaves every later add the same, so the budget binds only
        past it (``find_add``'s near tie)."""

    @property
    def usd_spent(self) -> float: ...

    @property
    def wildcards_spent(self) -> dict[str, int] | None: ...


class _UsdLedger:
    """Paper acquisition budget: a single USD pool. A no-listing card is never free
    (treated as scarce); ``budget is None`` is the owned-only pass."""

    def __init__(self, budget: float | None) -> None:
        self.budget = budget
        self.spent = 0.0

    def acquire_cost(self, record: dict) -> float | None:
        price = extract_price(record)
        if price is None:  # no-listing: never $0
            return None
        if self.budget is None:  # owned-only pass
            return None
        return price if self.spent + price <= self.budget else None

    def charge(self, record: dict, cost: float) -> None:
        self.spent += cost

    def share(self, adds: int) -> float:
        if self.budget is None:  # owned-only: every add it can make is free
            return math.inf
        return (self.budget - self.spent) / max(1, adds)

    @property
    def usd_spent(self) -> float:
        return round(self.spent, 2)

    @property
    def wildcards_spent(self) -> dict[str, int] | None:
        return None


class _WildcardLedger:
    """Digital (Arena) acquisition budget: four per-rarity wildcard pools. An uncovered
    copy costs ONE wildcard of its rarity. Wildcards are NOT interchangeable, so each
    tier is gated independently — an all-zero budget is the owned-only pass. The
    swap's USD ``cost`` is 0.0 (the UI costs by rarity); ``total`` is the per-tier
    wildcards spent."""

    def __init__(self, budget: Mapping[str, int]) -> None:
        self.remaining = {t: int(budget.get(t, 0)) for t in _WC_TIERS}
        self.spent = dict.fromkeys(_WC_TIERS, 0)

    def acquire_cost(self, record: dict) -> float | None:
        rarity = record.get("rarity")
        if rarity not in self.remaining or self.remaining[rarity] <= 0:
            return None
        return 0.0

    def charge(self, record: dict, cost: float) -> None:
        rarity = record.get("rarity")
        if rarity in self.remaining:
            self.remaining[rarity] -= 1
            self.spent[rarity] += 1

    def share(self, adds: int) -> float:
        return math.inf  # one wildcard of its rarity, whatever the card

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

    def addable(card: dict) -> bool:
        name = card.get("name", "")
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
        if "creature" in (c.record.get("type_line") or "").lower()
        for st in split_type_line(c.record.get("type_line", ""))[1]
    )
    # What the deck does, for the dead-payoff read (:func:`dead_payoff`): a
    # theme add that cares about a mechanic the deck lacks is no add — Banner
    # of Kinship and Coat of Arms on Bello's artifact page, Hardened Scales
    # on Anikthea's enchantments (2026-11-02). Read once per card.
    deck_keys, deck_tribe_counts, deck_type_counts = deck_profile(classes)
    dead_memo: dict[str, bool] = {}

    def dead_here(card: Mapping) -> bool:
        key = card.get("oracle_id") or card.get("name", "")
        verdict = dead_memo.get(key)
        if verdict is None:
            verdict = dead_payoff(card, deck_keys, deck_tribe_counts, deck_type_counts)
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
        tribe_member=lambda record: (
            sourcing.tribe_spec(record) is not None
            or typal_payoff_for(record, sourcing.tribe_kinds)
        ),
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

    def take_cut(pool: str, keep: Collection[str] = ()) -> tuple[str, CardClass] | None:
        for reason, card in cut_iters.get(pool, iter(())):
            if card.name in relied_on or card.name in keep:
                continue  # an add the proposal makes needs it
            if used_cuts[card.name] < card.quantity:
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
            ):
                continue
            if upgrade_of is None and not _does_the_job(card, job, deck_records):
                continue
            if trim_of is not None and over_band(
                card, trim_of.record, None, off_theme=off_theme
            ):
                continue  # a trim's add keeps its cut's band
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
            cut_entry = take_cut(remedy.cut_from, issue.relies_on)
            if cut_entry is None and remedy.lane_ok:
                cut_entry = take_cut(CUT_UPGRADE_JOBLESS, issue.relies_on)
            if cut_entry is None and remedy.lane_ok:
                cut_entry = take_cut(CUT_LANE, issue.relies_on)
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
