"""Whether a candidate upgrades a cut: the mana-value bands, the job reads'
downgrade gates (``_reads_worse_at_the_job``) and ``_upgrades`` itself
(split out of ``swaps``)."""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence

from mtg_utils._analysis.card_quality import quality
from mtg_utils._analysis.card_reads import has_trees
from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils._analysis.job_quality import JobRead, read_for
from mtg_utils._analysis.roles import DeckMana, role_of
from mtg_utils._analysis.signals import grant_payloads_for
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._tuner.ability_quality import grant_grade, outgrades
from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.issues import (
    is_flip,
    upgrade_job,
)
from mtg_utils.card_classify import (
    color_sources,
)
from mtg_utils.card_search import edhrec_popularity
from mtg_utils.deck import split_type_line

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


#: The colours a deck's identity holds before fixing is a ramp card's job.
_FIXING_COLORS = 3


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


def _stops_land_plays(card: Mapping) -> bool:
    """Whether a static of the card stops you playing lands (Aggressive
    Mining's "You can't play lands", a ``CantPlayLand`` mode)."""
    return any(
        unit.origin == "static"
        and "CantPlayLand" in str(getattr(unit.node, "mode", ""))
        for tree in trees_for(dict(card))
        for unit in tree.units
    )


#: Colorless sources a deck holds per {C} pip of an add's cost: eight cast
#: Kozilek's Command's and Warping Wail's two in Peace Offering and Mardu
#: Surge (batch 15's verdict); twelve for Echoes of Eternity's three.
_C_SOURCES_PER_PIP = 4


def _pays_a_sacrifice_more(read: JobRead, candidate: dict, cut: Mapping) -> bool:
    """Whether the job's read charges ``candidate`` a sacrifice cost
    (``activated_sac``) it does not charge ``cut``."""
    fc, fu = read.features(candidate) or {}, read.features(dict(cut)) or {}
    return fc.get("activated_sac", 0) > fu.get("activated_sac", 0)


#: The share of the cut's read a cheaper card in its band must keep to be a
#: tempo upgrade (:func:`_reads_worse_at_the_job`): Duplicant keeps 0.49 of
#: Meteor Golem (the kept precedent), Key to the City 0.38 of Smuggler's
#: Share.
_TEMPO_FLOOR = 0.4


def _reads_worse_at_the_job(
    candidate: dict,
    cut: dict,
    job: str,
    deck: Sequence[dict] | None,
    commanders: Sequence[Mapping] = (),
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
    if job == "ramp":
        # Cheaper is no excuse for half the mana a turn or less: Exploration
        # Broodship's extra land drop waits on station 3 (a quarter a turn)
        # and replaced Careful Cultivation's {G}{G} creature (Virtue and
        # Valor, 2026-11-02).
        fc, fu = read.features(candidate) or {}, read.features(cut) or {}
        if fc.get("per_turn", 0) < 0.5 * fu.get("per_turn", 0):
            return True
        # Nor is a one-colour source an upgrade to one that fixes in a deck of
        # three colours or more: Ignoble Hierarch's {B}, {R} or {G} went to
        # Llanowar Elves' {G} in Jund Graveyard Overdrive (2026-11-02) — the
        # read's fitted weight on fixing is small, the deck's need is not.
        identity = {c for cmd in commanders for c in cmd.get("color_identity") or ()}
        if (
            len(identity) >= _FIXING_COLORS
            and fu.get("fixes", 0) > 0
            and fc.get("fixes", 0) < fu.get("fixes", 0)
        ):
            return True
    if job == "board_wipe" and _sweeps_fewer_kinds(read, candidate, cut):
        return True
    if job == "board_wipe" and _bounces_for_a_kill(candidate, cut, deck):
        return True
    if job == "card_draw":
        from mtg_utils._analysis.job_quality import card_draw

        if card_draw.narrower_engine(candidate, cut):
            return True
    if job == "interaction":
        from mtg_utils._analysis.job_quality import removal

        # Removal that answers creatures is no upgrade to removal that can't:
        # Lethal Scheme went to Return to Nature (Sultai Arisen, 2026-11-02).
        if (
            removal.answers_creatures(cut)
            and removal.answers_creatures(candidate) is False
        ):
            return True
    records = deck or ()
    if (
        job == "board_wipe"
        and records
        and _spares_less_of_the_deck(candidate, cut, records, commanders)
    ):
        return True
    if _one_shot_for_an_engine(read, candidate, cut, records):
        return True
    cand_cost, cut_cost = _job_cost(read, candidate), _job_cost(read, cut)
    sc, su = read.score(candidate, records), read.score(cut, records)
    if (
        cand_cost < cut_cost
        and _cost_band(cand_cost) == _cost_band(cut_cost)
        # A cheaper card is a tempo upgrade only while it keeps enough of the job:
        # Key to the City's discard-to-untap draw (0.22) replaced Smuggler's
        # Share (0.57) in Blame Game (2026-11-02).
        and (sc is None or su is None or sc >= _TEMPO_FLOOR * su)
        # Nor is a card cheaper that pays a creature the cut doesn't: Fling's
        # "sacrifice a creature" for Fiend Hunter (Riders of Rohan,
        # 2026-11-02).
        and not _pays_a_sacrifice_more(read, candidate, cut)
        # Nor is ramp cheaper whose mana comes late: Ordeal of Nylea's lands
        # wait on three attacks (``early`` 0) and took Careful Cultivation's
        # slot (Virtue and Valor, 2026-11-02).
        and not (
            read.job == "ramp" and (read.features(candidate) or {}).get("early") == 0
        )
    ):
        return False
    return sc is not None and su is not None and sc < su - 1e-9


def _one_shot_for_an_engine(
    read: JobRead, candidate: dict, cut: Mapping, deck: Sequence[dict]
) -> bool:
    """Whether ``candidate`` is an instant or sorcery the job's read sees
    nothing of, replacing a permanent the read scores at the job: Vanquisher's
    Banner's draw on every Knight cast went to And They Shall Know No Fear's
    one turn of +1/+0 (Cavalry Charge, 2026-11-02). Only a one-shot spell: the
    broader "nothing at the job is worse" also caught creatures the read
    can't see (Dark Confidant) and was reverted."""
    words = {w.lower() for w in split_type_line(candidate.get("type_line") or "")[0]}
    if not words & {"instant", "sorcery"}:
        return False
    cut_words = {w.lower() for w in split_type_line(cut.get("type_line") or "")[0]}
    if cut_words & {"instant", "sorcery"}:
        return False
    if not has_trees(candidate):
        return False
    return (
        read.score(candidate, deck) is None and read.score(dict(cut), deck) is not None
    )


def _spares_less_of_the_deck(
    candidate: dict,
    cut: Mapping,
    deck: Sequence[dict],
    commanders: Sequence[Mapping] = (),
) -> bool:
    """Whether a wipe candidate is symmetric in ``deck`` where the cut spares
    the deck's own board (``board_wipe.features``' deck-read ``one_sided``):
    Winds of Rath under twenty Auras, Dusk under face-down 2/2s, Slaughter the
    Strong under 0-power walls all went to Wrath of God or Damn, the read's
    weight on sparing too small to hold them (2026-11-02). A power line that
    kills a commander spares nothing that matters: Dusk spares most of
    Virtue and Valor's creatures by printed power, but not Ellivere of the
    Wild Court, a 4-power commander — Winds of Rath went to it (2026-11-02).
    Nor a type left out the commander is not: Extinguish All Hope spares
    Enduring Enchantments' enchantment creatures, Anikthea among them, and
    went to The One Ring to Rule Them All, whose "nonlegendary" spares six of
    them (2026-11-02)."""
    from mtg_utils._analysis.job_quality import board_wipe

    def one_sided(card: dict) -> bool | None:
        f = board_wipe.features(card, deck)
        if not f:
            return None
        sided = f.get("one_sided", 0) > 0 or board_wipe.toughness_spares(card, deck)
        return sided and not any(
            board_wipe.power_bound_hits(card, c) or board_wipe.type_bound_hits(card, c)
            for c in commanders
        )

    a, b = one_sided(candidate), one_sided(dict(cut))
    if a is None or b is None:
        return False
    if b and not a:
        return True
    # Nor a wipe the commander survives for one that kills it: The Day of the
    # Doctor keeps up to three chosen Doctors, the Tenth Doctor among them,
    # and went to The Battle of Bywater, which kills him (Timey Wimey,
    # 2026-11-02).
    return any(
        board_wipe.keeps_commander(dict(cut), c)
        and board_wipe.kills_commander(candidate, c)
        for c in commanders
    )


def _bounces_for_a_kill(
    candidate: dict, cut: Mapping, deck: Sequence[dict] | None
) -> bool:
    """Whether ``candidate`` returns creatures to hand where ``cut`` destroys
    or exiles them, and spares the deck's own board no more: they come back
    next turn. Slinn Voda's kicked "return all creatures to their owners'
    hands" went in for Oversimplify's "Exile all creatures" (Quandrix
    Unlimited, 2026-11-02) — the read's fitted weight on bounce is
    Cyclonic Rift's, a one-sided one."""
    from mtg_utils._analysis.job_quality import board_wipe

    records = deck or None
    fc = board_wipe.features(candidate, records)
    fu = board_wipe.features(dict(cut), records)
    if not fc or not fu:
        return False
    # A bounce leaving a class standing the cut doesn't (Raise the Palisade's
    # chosen type for Dusk // Dawn under Zombies) spares the deck's board.
    return (
        fc.get("bounce", 0) > 0
        and fu.get("lethal", 0) >= 1
        and fc.get("one_sided", 0) <= fu.get("one_sided", 0)
        and fc.get("spares", 0) <= fu.get("spares", 0)
    )


def _one_shot_mana(card: dict) -> bool:
    """Whether the ramp read sees a one-shot mana source: no mana a turn, no
    land, no conditional engine (a ritual, Lotus Petal, a spirit guide)."""
    read = read_for("ramp")
    if read is None or not has_trees(card):
        return False
    f = read.features(card)
    return bool(f) and all(
        f.get(k, 0) == 0 for k in ("per_turn", "land", "cond_engine")
    )


def _sweeps_no_creatures(card: dict) -> bool:
    """Whether the wipe read sees the card sweep no creatures (Vandalblast)."""
    read = read_for("board_wipe")
    if read is None or not has_trees(card):
        return False
    features = read.features(card)
    return bool(features) and features.get("creatures", 0) == 0


def _sweeps_fewer_kinds(read: JobRead, candidate: dict, cut: Mapping) -> bool:
    """Whether a wipe candidate sweeps no creatures where the cut does, or only
    a narrow slice where the cut sweeps the board: the wipe read scores
    Vandalblast's one-sided artifact sweep above Winds of Rath, but the
    board-wipe row is there for creature boards — Blame Game, Desert Bloom,
    Endless Punishment and Timey-Wimey traded creature sweepers for it
    (2026-11-02)."""
    a, b = read.features(candidate), read.features(dict(cut))
    if not a or not b:
        return False
    if a.get("creatures", 0) == 0 and b.get("creatures", 0) > 0:
        return True
    # A sweep that kills only small creatures never replaces one that kills
    # the board: Contagion Engine's one -1/-1 counter for Starstorm's X damage
    # (Animated Army, 2026-11-02), let through as the "cheaper" card.
    if a.get("small", 0) > 0 and b.get("lethal", 0) >= 1:
        return True
    # A sweep of a narrow slice (the attacking creatures, a power bound)
    # never replaces one of the whole board: Aetherize's "return all
    # attacking creatures" took Fumigate's slot as the cheaper card though
    # the read scores it below (Counter Intelligence, 2026-11-02).
    return a.get("narrow", 0) > 0 and b.get("narrow", 0) == 0


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
    if read is None or not has_trees(candidate) or not has_trees(dict(cut)):
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
    if read.job == "interaction":
        from mtg_utils._analysis.job_quality import removal

        cost = removal.deploy_cost(card)
        if cost is not None:
            return max(cost, effective_mana_value(card))
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
    needs_kept: Callable[[Mapping], int] | None = None,
    commanders: Sequence[Mapping] = (),
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
        candidate, cut.record, read_job, deck, commanders
    ):
        return False
    if read_job is not None and _lateral_at_the_job(candidate, cut.record, read_job):
        return False
    if needs is not None and needs(candidate) < needs(cut.record):
        return False
    # The needs an upgrade keeps (``needs_kept``, the broad ones included):
    # a cut supplying the commander's enchantment need goes to an enchantment.
    if needs_kept is not None and needs_kept(candidate) < needs_kept(cut.record):
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
