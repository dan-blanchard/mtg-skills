"""Untapped.gg's per-card results on a Commander-family ladder, per commander.

Verified live (2026-11-28): the "Card Data" page of a Commander-family queue reads
``analytics/query/card_stats_commander_by_archetype_and_scope_v2/premium/<partition>``
with ``MetaPeriodId`` and ``MetaPeriodScopeFilter=EXACTLY_LAST_3_MONTHS``. The
partition is ``ALL`` or a meta archetype's id (a commander: the ids
``archetypes_by_event_scope_and_rank_v2`` lists). ``data`` is keyed by Arena titleId,
then ``ALL``, then a rank code (``RANK_CODES``, plus ``n`` for unranked games), each a
list of three count rows named by ``metadata.fields``:

- ``games, wins, in_main_games`` — games with the card in the deck;
- ``available_games, available_wins, played_games, played_wins,
  not_available_games, not_available_wins`` — the card reached the hand, was
  played, never reached the hand;
- ``in_opening_hands, in_opening_hand_wins``.

Untapped drops a row's trailing zeros, so every index read defaults to 0.

These are results of games people played, not a reading of the cards. They are a
readout (``arena-meta``) and a yardstick for the tuner's proposals; **the tuner never
reads them** (Dan's decision, 2026-11-28: it picks cards by reading cards).

Raw bundles are cached under ``<cache root>/untapped/card-stats/`` for 24 hours.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mtg_utils._arena_meta.meta import DEFAULT_RANKS, RANK_CODES, UNRANKED, Record
from mtg_utils._http import cache_root, is_fresh
from mtg_utils._sidecar import atomic_write_json

if TYPE_CHECKING:
    from mtg_utils.card_pool import CardPool

_CARD_STATS = (
    "analytics/query/card_stats_commander_by_archetype_and_scope_v2/premium/{partition}"
)
SCOPE = "EXACTLY_LAST_3_MONTHS"
#: The partition holding every commander's games.
EVERY_COMMANDER = "ALL"
_CACHE_HOURS = 24
#: Where each count sits: (row, index of games, index of wins).
_AT = {
    "deck": (0, 0, 1),
    "in_hand": (1, 0, 1),
    "played": (1, 2, 3),
    "not_in_hand": (1, 4, 5),
    "opening": (2, 0, 1),
}


_NO_GAMES = Record()


def card_stats_dir() -> Path:
    return cache_root() / "untapped" / "card-stats"


@dataclass(frozen=True, slots=True)
class CardResult:
    """One card's measured results under one commander (or every commander), over
    the ranks asked for. ``deck``: games with the card in the deck. ``in_hand``: it
    reached the hand. ``played``: it was played. ``not_in_hand``: it was in the deck
    and never reached the hand. ``opening``: it was in the opening hand."""

    name: str
    deck: Record = _NO_GAMES
    in_hand: Record = _NO_GAMES
    played: Record = _NO_GAMES
    not_in_hand: Record = _NO_GAMES
    opening: Record = _NO_GAMES

    @property
    def lift(self) -> float | None:
        """Win rate with the card in hand minus win rate with it in the deck and
        never in hand: the same decks and players on both sides, so the deck's
        and the player's strength cancel. Untapped's "In hand WR Δ"."""
        seen, unseen = self.in_hand.winrate, self.not_in_hand.winrate
        return None if seen is None or unseen is None else seen - unseen

    @property
    def lift_se(self) -> float | None:
        """The binomial standard error of :attr:`lift`."""
        if self.lift is None:
            return None
        return math.sqrt(
            sum(
                (r.wins / r.matches) * (1 - r.wins / r.matches) / r.matches
                for r in (self.in_hand, self.not_in_hand)
            )
        )

    def to_json(self) -> dict:
        def rate(record: Record) -> float | None:
            return None if record.winrate is None else round(record.winrate, 4)

        return {
            "name": self.name,
            "games": self.deck.matches,
            "deck_winrate": rate(self.deck),
            "in_hand_games": self.in_hand.matches,
            "in_hand_winrate": rate(self.in_hand),
            "played_winrate": rate(self.played),
            "not_in_hand_winrate": rate(self.not_in_hand),
            "lift": None if self.lift is None else round(self.lift, 4),
            "lift_se": None if self.lift_se is None else round(self.lift_se, 4),
        }


def _at(rows: Sequence, row: int, index: int) -> int:
    try:
        return int(rows[row][index] or 0)
    except (IndexError, TypeError):
        return 0


def _record(buckets: Mapping, kind: str, ranks: Sequence[str]) -> Record:
    row, games, wins = _AT[kind]
    out = Record()
    for code, rows in buckets.items():
        rank = RANK_CODES.get(code)
        if rank is not None and (rank in ranks or rank == UNRANKED):
            out += Record(_at(rows, row, games), _at(rows, row, wins))
    return out


def card_results(
    raw: Mapping, ranks: Sequence[str] = DEFAULT_RANKS
) -> dict[str, CardResult]:
    """Card name -> its results over ``ranks``, from a raw bundle (``names`` maps
    each titleId to a card name; a titleId with no name is dropped)."""
    names = raw.get("names", {})
    out: dict[str, CardResult] = {}
    for title, parts in raw.get("data", {}).items():
        name = names.get(str(title))
        buckets = next(iter(parts.values()), None) if parts else None
        if not name or not buckets:
            continue
        out[name] = CardResult(name, *(_record(buckets, kind, ranks) for kind in _AT))
    return out


def partition_games(raw: Mapping, ranks: Sequence[str] = DEFAULT_RANKS) -> int:
    """The games behind a bundle over ``ranks`` (``metadata.games``)."""
    games = raw.get("games", {})
    return sum(
        int(next(iter(count.values()), 0) or 0)
        for rank, count in games.items()
        if rank in ranks or rank == UNRANKED
    )


#: Under this many games with the card in hand, a row is marked thin.
THIN_IN_HAND = 200


def deck_card_results(
    raw: Mapping,
    names: Iterable[str],
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    skip: Iterable[str] = (),
) -> dict:
    """The ``arena-meta`` section: each of ``names`` (a deck's cards, ``skip``
    left out — its lands) with its results in ``raw``, best lift first, and the
    names ``raw`` has no results for.

    Each row's ``relative`` is its lift minus ``average_lift``, the bundle's
    average card's (weighted by games in hand). A game that runs long shows its
    player more cards, so under a commander that wins early every card's lift
    sits below zero, and above it under one that wins late; the difference from
    the average card is what compares two cards of one commander."""
    results = card_results(raw, ranks)
    seen = [(r.in_hand.matches, r.lift) for r in results.values() if r.lift is not None]
    weight = sum(n for n, _ in seen)
    average = sum(n * lift for n, lift in seen) / weight if weight else 0.0
    left_out = set(skip)
    rows: list[dict] = []
    missing: list[str] = []
    for name in dict.fromkeys(names):
        if name in left_out:
            continue
        result = results.get(name) or results.get(name.split(" // ")[0])
        if result is None or result.lift is None:
            missing.append(name)
            continue
        rows.append(
            {
                **result.to_json(),
                "relative": round(result.lift - average, 4),
                "thin": result.in_hand.matches < THIN_IN_HAND,
            }
        )
    rows.sort(key=lambda r: -r["lift"])
    return {
        "games": partition_games(raw, ranks),
        "average_lift": round(average, 4),
        "scope": raw.get("scope"),
        "period": raw.get("period"),
        "cards": rows,
        "missing": missing,
    }


def _path(event: str, period: int, partition: int | str) -> Path:
    return card_stats_dir() / f"{event}.{period}.{partition}.json"


def _names(data: Mapping, pool: CardPool | None) -> dict[str, str]:
    from mtg_utils._arena_meta.untapped import resolve_titles
    from mtg_utils.limited_stats import mtgajson_files

    cards, loc = mtgajson_files()
    names, _lands = resolve_titles(
        {int(t) for t in data},
        cards,
        loc,
        pool.by_arena_id if pool is not None else None,
    )
    return {str(title): name for title, name in names.items()}


def load_card_stats(
    event: str,
    partitions: Iterable[int | str] = (EVERY_COMMANDER,),
    *,
    period_id: int | None = None,
    refresh: bool = False,
    pool: CardPool | None = None,
) -> dict[int | str, dict]:
    """The raw bundle of each partition (a meta archetype id, or ``"ALL"``) for
    ``event``'s current period: the cache while fresh, else one signed-in session
    that fetches every stale one. Raises what :mod:`untapped` raises (a
    ``SignInRequiredError`` says to run ``arena-meta --login``)."""
    from mtg_utils._arena_meta.untapped import MetaError, _Session, pick_period

    wanted = list(dict.fromkeys(partitions))
    out: dict[int | str, dict] = {}
    if period_id is not None and not refresh:
        for partition in wanted:
            path = _path(event, period_id, partition)
            if is_fresh(path, max_age_hours=_CACHE_HOURS):
                out[partition] = json.loads(path.read_text(encoding="utf-8"))
    if len(out) == len(wanted):
        return out
    with _Session() as session:
        if period_id is None:
            periods = session.get("meta-periods/active") or []
            period_id = int(pick_period(periods, event)["id"])
        for partition in wanted:
            if partition in out:
                continue
            path = _path(event, period_id, partition)
            if not refresh and is_fresh(path, max_age_hours=_CACHE_HOURS):
                out[partition] = json.loads(path.read_text(encoding="utf-8"))
                continue
            body = session.get(
                _CARD_STATS.format(partition=partition),
                MetaPeriodId=period_id,
                MetaPeriodScopeFilter=SCOPE,
            )
            if not isinstance(body, dict) or "data" not in body:
                raise MetaError(
                    f"Untapped sent no card results for {event} / {partition}"
                )
            meta = body.get("metadata") or {}
            bundle = {
                "event": event,
                "period": period_id,
                "partition": partition,
                "scope": SCOPE,
                "fetched_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "fields": meta.get("fields"),
                "games": meta.get("games") or {},
                "names": _names(body["data"], pool),
                "data": body["data"],
            }
            if partition == EVERY_COMMANDER:
                bundle["games_by_partition"] = (
                    meta.get("games_by_partition_and_rank") or {}
                )
            atomic_write_json(path, bundle)
            out[partition] = bundle
    return out
