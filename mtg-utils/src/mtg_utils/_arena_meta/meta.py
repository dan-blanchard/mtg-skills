"""The meta model: one Arena queue's meta period, as Untapped.gg reports it, and
the four reads over it (ADR-0059). Pure — fetching is ``untapped``'s job.

A **snapshot** holds the period's meta archetypes (Untapped's grouping: a commander
on a Brawl ladder, a named deck type on a 60-card one) and the decklists it
publishes for them, each with a per-rank-bucket record. Every read sums the rank
buckets asked for (Platinum and up by default); an unranked queue has one bucket,
``all``, which every read uses whatever ranks were asked for.

- :func:`ranking` — meta archetypes ranked by the Wilson lower bound on their win
  rate, with a Mythic-only column beside it;
- :func:`field_shares` — what you'll face: each meta archetype's share of the matches;
- :func:`card_shares` / :func:`core` — how often a meta archetype's lists run each
  card, weighted by matches, with the average copies;
- :func:`buildable` — the decklists you can build, cheapest first;
- :func:`resolve` — which meta archetype a deck is (or the one named);
- :func:`tunable` / :func:`deck_context` — whether the tuner may read that archetype
  (its published lists clear the ranking's floor at the tuner's ranks), and what it
  reads from it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import NamedTuple, cast

from mtg_utils.names import normalize_card_name

LADDER_RANKS = ("bronze", "silver", "gold", "platinum", "diamond", "mythic")
DEFAULT_RANKS = ("platinum", "diamond", "mythic")
UNRANKED = "all"
#: A deck row's rank-bucket codes (``rs``); the archetype rows spell them out.
RANK_CODES = {
    "b": "bronze",
    "s": "silver",
    "g": "gold",
    "p": "platinum",
    "d": "diamond",
    "m": "mythic",
    "a": UNRANKED,
}
#: Defaults agreed for the reads (ADR-0059).
MIN_MATCHES = 250
# The Mythic column's sub-sample floor: a Mythic rate over fewer games is shown
# dimmed. At 100 games the 95% Wilson interval is about ±10 points (±14 at 50, ±6
# at 250, the ranking's floor, which most archetypes' Mythic games never reach).
MYTHIC_MIN_MATCHES = 100
CORE_SHARE = 0.40
FIELD_SHARE = 0.01
CUT_SHARE = 0.05  # under it, a card is rarely in the archetype's lists
MATCH_OVERLAP = 0.40
_COLORS = "WUBRG"
_COLOR_TAG = 7  # an Untapped tag of type 7 names the colours ("Izzet")


def parse_ranks(spec: str) -> tuple[str, ...]:
    """``"platinum+"`` (that rank and up), ``"gold,platinum"``, or ``"all"``."""
    spec = spec.strip().lower()
    if spec in ("all", "any"):
        return LADDER_RANKS
    if spec.endswith("+"):
        start = spec[:-1]
        if start not in LADDER_RANKS:
            raise ValueError(f"unknown rank {start!r}")
        return LADDER_RANKS[LADDER_RANKS.index(start) :]
    ranks = tuple(r.strip() for r in spec.split(",") if r.strip())
    unknown = [r for r in ranks if r not in LADDER_RANKS]
    if unknown or not ranks:
        raise ValueError(f"unknown rank(s) {unknown or spec!r}")
    return ranks


def wilson_lower(wins: int, matches: int, z: float = 1.96) -> float:
    """The lower bound of the Wilson score interval (95% by default)."""
    if matches <= 0:
        return 0.0
    p = wins / matches
    denom = 1 + z * z / matches
    centre = p + z * z / (2 * matches)
    spread = z * math.sqrt(p * (1 - p) / matches + z * z / (4 * matches * matches))
    return (centre - spread) / denom


@dataclass(frozen=True, slots=True)
class Record:
    matches: int = 0
    wins: int = 0

    def __add__(self, other: Record) -> Record:
        return Record(self.matches + other.matches, self.wins + other.wins)

    @property
    def winrate(self) -> float | None:
        return self.wins / self.matches if self.matches else None

    def to_json(self) -> dict:
        return {
            "matches": self.matches,
            "wins": self.wins,
            "winrate": round(self.winrate, 4) if self.winrate is not None else None,
            "wilson_lower": round(wilson_lower(self.wins, self.matches), 4),
        }


def _total(stats: Mapping[str, Record], ranks: Sequence[str]) -> Record:
    if UNRANKED in stats:
        return stats[UNRANKED]
    out = Record()
    for rank in ranks:
        out += stats.get(rank, Record())
    return out


@dataclass(frozen=True, slots=True)
class MetaArchetype:
    id: int
    name: str
    colors: str
    stats: Mapping[str, Record]


@dataclass(frozen=True, slots=True)
class MetaDeck:
    archetype: int
    commanders: tuple[str, ...]
    main: tuple[tuple[str, int], ...]
    sideboard: tuple[tuple[str, int], ...]
    stats: Mapping[str, Record]
    #: The folded names (``normalize_card_name``) matching reads compare, once.
    commander_keys: frozenset[str] = field(init=False, repr=False, compare=False)
    main_keys: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "commander_keys", _keys(self.commanders))
        object.__setattr__(self, "main_keys", _keys(n for n, _ in self.main))


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One queue's meta period: its archetypes and published decklists."""

    event: str
    period: Mapping
    fetched_at: str
    archetypes: Mapping[int, MetaArchetype]
    decks: tuple[MetaDeck, ...]
    #: Land names among the cards, so a read can set lands aside.
    lands: frozenset[str] = field(default_factory=frozenset)

    @property
    def ranked(self) -> bool:
        return not any(UNRANKED in a.stats for a in self.archetypes.values())

    def to_json(self) -> dict:
        return {
            "event": self.event,
            "period": dict(self.period),
            "fetched_at": self.fetched_at,
            "archetypes": [
                {**asdict(a), "stats": {k: asdict(v) for k, v in a.stats.items()}}
                for a in self.archetypes.values()
            ],
            "decks": [
                {
                    "archetype": d.archetype,
                    "commanders": list(d.commanders),
                    "main": [list(c) for c in d.main],
                    "sideboard": [list(c) for c in d.sideboard],
                    "stats": {k: asdict(v) for k, v in d.stats.items()},
                }
                for d in self.decks
            ],
            "lands": sorted(self.lands),
        }

    @classmethod
    def from_json(cls, data: Mapping) -> Snapshot:
        def stats(raw: Mapping) -> dict[str, Record]:
            return {k: Record(**v) for k, v in raw.items()}

        archetypes = {
            int(a["id"]): MetaArchetype(
                id=int(a["id"]),
                name=a["name"],
                colors=a.get("colors", ""),
                stats=stats(a["stats"]),
            )
            for a in data["archetypes"]
        }
        decks = tuple(
            MetaDeck(
                archetype=int(d["archetype"]),
                commanders=tuple(d.get("commanders", ())),
                main=tuple((n, int(q)) for n, q in d["main"]),
                sideboard=tuple((n, int(q)) for n, q in d.get("sideboard", ())),
                stats=stats(d["stats"]),
            )
            for d in data["decks"]
        )
        return cls(
            event=data["event"],
            period=data.get("period", {}),
            fetched_at=data.get("fetched_at", ""),
            archetypes=archetypes,
            decks=decks,
            lands=frozenset(data.get("lands", ())),
        )


# --- Building a snapshot from Untapped's payloads --------------------------------


def drop_nulls[T](value: T) -> T:
    """Untapped's JSON with every ``null`` field dropped (recursively), so each read
    of it falls back to its default — the one place its nulls are handled."""
    if isinstance(value, dict):
        return cast(T, {k: drop_nulls(v) for k, v in value.items() if v is not None})
    if isinstance(value, list):
        return cast(T, [drop_nulls(v) for v in value])
    return value


def _count(row: Sequence, at: int) -> int:
    """A ``rs`` row's ``at``-th count (``[matches, wins, avg_seconds]``), 0 when
    missing or null."""
    return int(row[at] or 0) if len(row) > at else 0


def _colors(color_byte: int | None) -> str:
    return "".join(c for i, c in enumerate(_COLORS) if (color_byte or 0) >> i & 1)


def _archetype_name(tag_ids: Sequence[int], tags: Mapping[int, Mapping]) -> str:
    named = [tags[t] for t in tag_ids if t in tags]
    named.sort(key=lambda t: (t.get("metadata") or {}).get("type") != _COLOR_TAG)
    return " / ".join(str(t.get("name", "")) for t in named) or "Unknown"


def build_snapshot(
    raw: Mapping,
    names: Mapping[int, str],
    *,
    lands: Collection[str] = (),
) -> Snapshot:
    """A :class:`Snapshot` from the raw bundle ``untapped.fetch_raw`` writes —
    ``{event, period, fetched_at, tags, archetypes, decks}`` — with ``names``
    resolving each titleId (a card it can't name is kept as ``titleId N``).
    A deckstring this decoder can't read is skipped."""
    from mtg_utils._arena_meta.deckstring import DeckstringError, decode

    raw = drop_nulls(raw)
    tags = {int(t["id"]): t for t in raw.get("tags", ())}

    def name(title: int) -> str:
        return names.get(title) or f"titleId {title}"

    archetypes: dict[int, MetaArchetype] = {}
    for row in raw.get("archetypes", ()):
        stats = {
            rank: Record(
                int(s.get("total_matches", 0)),
                round(
                    int(s.get("total_matches", 0)) * float(s.get("winrate", 0)) / 100
                ),
            )
            for rank, s in row.get("stats", {}).items()
        }
        aid = int(row["primary_tag_group_id"])
        archetypes[aid] = MetaArchetype(
            id=aid,
            name=_archetype_name(row.get("primary_tags", ()), tags),
            colors=_colors(row.get("color_byte")),
            stats=stats,
        )
    decks: list[MetaDeck] = []
    for row in raw.get("decks", ()):
        try:
            deck = decode(row["ds"])
        except (DeckstringError, KeyError):
            continue
        decks.append(
            MetaDeck(
                archetype=int(row.get("ptg", 0)),
                commanders=tuple(name(t) for t in deck.commanders),
                main=tuple((name(t), q) for t, q in deck.main),
                sideboard=tuple((name(t), q) for t, q in deck.sideboard),
                stats={
                    RANK_CODES[code]: Record(_count(v, 0), _count(v, 1))
                    for code, v in row.get("rs", {}).items()
                    if code in RANK_CODES
                },
            )
        )
    return Snapshot(
        event=str(raw.get("event", "")),
        period=dict(raw.get("period", {})),
        fetched_at=str(raw.get("fetched_at", "")),
        archetypes=archetypes,
        decks=tuple(decks),
        lands=frozenset(lands),
    )


# --- Reads ------------------------------------------------------------------------


def _field_total(snap: Snapshot, ranks: Sequence[str]) -> int:
    return sum(_total(a.stats, ranks).matches for a in snap.archetypes.values())


def _row(snap: Snapshot, arch: MetaArchetype, ranks: Sequence[str], total: int) -> dict:
    rec = _total(arch.stats, ranks)
    row = {
        "id": arch.id,
        "name": arch.name,
        "colors": arch.colors,
        **rec.to_json(),
        "share": round(rec.matches / total, 4) if total else 0.0,
    }
    if snap.ranked:
        row["mythic"] = arch.stats.get("mythic", Record()).to_json()
    return row


def ranking(
    snap: Snapshot,
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    min_matches: int = MIN_MATCHES,
) -> list[dict]:
    """Meta archetypes with at least ``min_matches`` matches in ``ranks``, best
    Wilson lower bound first."""
    total = _field_total(snap, ranks)
    rows = [
        _row(snap, a, ranks, total)
        for a in snap.archetypes.values()
        if _total(a.stats, ranks).matches >= min_matches
    ]
    return sorted(rows, key=lambda r: (-r["wilson_lower"], -r["matches"]))


def field_shares(
    snap: Snapshot,
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    min_share: float = FIELD_SHARE,
) -> list[dict]:
    """Meta archetypes holding at least ``min_share`` of the matches, most played
    first: the opponents a deck will meet."""
    total = _field_total(snap, ranks)
    rows = [_row(snap, a, ranks, total) for a in snap.archetypes.values()]
    return sorted(
        (r for r in rows if r["share"] >= min_share), key=lambda r: -r["matches"]
    )


def _weights(decks: Sequence[MetaDeck], ranks: Sequence[str]) -> list[int]:
    """Each list's matches in ``ranks``; every list's all-rank matches when none
    has any (so a thin queue still has a profile)."""
    weights = [_total(d.stats, ranks).matches for d in decks]
    if not any(weights):
        weights = [_total(d.stats, LADDER_RANKS).matches or 1 for d in decks]
    return weights


def card_shares(
    snap: Snapshot, archetype: int, ranks: Sequence[str] = DEFAULT_RANKS
) -> dict[str, dict]:
    """Main-deck card -> ``{share, avg_copies}`` across a meta archetype's lists:
    the match-weighted fraction of lists running it, and the copies those lists
    run on average. Commanders are left out (every list runs them)."""
    decks = [d for d in snap.decks if d.archetype == archetype]
    weights = _weights(decks, ranks)
    total = sum(weights)
    if not total:
        return {}
    in_lists: dict[str, float] = defaultdict(float)
    copies: dict[str, float] = defaultdict(float)
    for deck, weight in zip(decks, weights, strict=True):
        if not weight:
            continue  # a list unplayed in these ranks says nothing about them
        for name, qty in deck.main:
            in_lists[name] += weight
            copies[name] += weight * qty
    return {
        name: {
            "share": round(in_lists[name] / total, 4),
            "avg_copies": round(copies[name] / in_lists[name], 2),
        }
        for name in in_lists
    }


def core(
    snap: Snapshot,
    archetype: int,
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    min_share: float = CORE_SHARE,
    shares: Mapping[str, Mapping] | None = None,
) -> list[dict]:
    """The cards at least ``min_share`` of a meta archetype's lists run, most
    shared first (``shares``: :func:`card_shares`' answer, when already in hand)."""
    if shares is None:
        shares = card_shares(snap, archetype, ranks)
    rows = [
        {"name": name, **v, "land": name in snap.lands}
        for name, v in shares.items()
        if v["share"] >= min_share
    ]
    return sorted(rows, key=lambda r: (-r["share"], r["name"]))


def buildable(
    snap: Snapshot,
    cost: Callable[[MetaDeck], Mapping[str, int]],
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    wildcards: Mapping[str, int] | None = None,
    archetype: int | None = None,
) -> list[dict]:
    """Every published list played in ``ranks`` (only ``archetype``'s, when given)
    with its wildcard cost (``cost``: rarity -> wildcards still needed), the ones
    within ``wildcards`` first, then cheapest, then best Wilson lower bound."""
    rows = []
    for deck in snap.decks:
        if archetype is not None and deck.archetype != archetype:
            continue
        rec = _total(deck.stats, ranks)
        if not rec.matches:
            continue
        need = {r: int(n) for r, n in cost(deck).items() if n}
        fits = wildcards is not None and all(
            n <= wildcards.get(r, 0) for r, n in need.items()
        )
        arch = snap.archetypes.get(deck.archetype)
        rows.append(
            {
                "archetype": arch.name if arch else f"group {deck.archetype}",
                "commanders": list(deck.commanders),
                **rec.to_json(),
                "wildcards_needed": need,
                "fits": fits,
                "deck": deck,
            }
        )
    return sorted(
        rows,
        key=lambda r: (
            not r["fits"],
            sum(r["wildcards_needed"].values()),
            -r["wilson_lower"],
        ),
    )


# --- Matching a deck --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Match:
    archetype: MetaArchetype
    #: ``"commander"`` (a Brawl ladder), ``"overlap"`` (a 60-card ladder) or
    #: ``"named"`` (the caller named the archetype).
    by: str
    #: The match-weighted share of the deck's nonland cards the archetype's lists
    #: run (1.0 for a commander or named match).
    overlap: float

    def to_json(self) -> dict:
        return {
            "archetype": self.archetype.name,
            "by": self.by,
            "overlap": self.overlap,
        }


def _keys(names: Iterable[str]) -> frozenset[str]:
    return frozenset(normalize_card_name(n) for n in names)


def _deck_names(deck: Mapping, zone: str) -> list[str]:
    return [e["name"] for e in deck.get(zone) or []]


def match_deck(
    snap: Snapshot,
    deck: Mapping,
    ranks: Sequence[str] = DEFAULT_RANKS,
    *,
    lands: Collection[str] = (),
    min_overlap: float = MATCH_OVERLAP,
) -> Match | None:
    """The meta archetype a parsed ``deck`` is. With commanders: the archetype
    whose lists lead with the same commander(s), the most played when several do.
    Without: the one whose lists share most of the deck's nonland cards — the
    match-weighted mean of each list's share of them — or ``None`` below
    ``min_overlap``. ``lands`` names the deck's own lands (its hydrated types), so a
    land no list runs doesn't count against the overlap."""
    by_arch: dict[int, list[MetaDeck]] = defaultdict(list)
    for d in snap.decks:
        if d.archetype in snap.archetypes:
            by_arch[d.archetype].append(d)
    played = {aid: _total(a.stats, ranks).matches for aid, a in snap.archetypes.items()}
    commanders = _deck_names(deck, "commanders")
    if commanders:
        want = _keys(commanders)
        hits = [
            aid
            for aid, decks in by_arch.items()
            if any(d.commander_keys == want for d in decks)
        ] or [  # a partner pair Untapped groups under one of the two
            aid
            for aid, decks in by_arch.items()
            if any(d.commander_keys & want for d in decks)
        ]
        if not hits:
            return None
        best = max(hits, key=lambda aid: played.get(aid, 0))
        return Match(snap.archetypes[best], "commander", 1.0)
    mine = _keys(_deck_names(deck, "cards")) - _keys(snap.lands) - _keys(lands)
    if not mine:
        return None
    best_aid, best_overlap = None, 0.0
    for aid, decks in by_arch.items():
        weights = _weights(decks, ranks)
        total = sum(weights)
        if not total:
            continue
        overlap = (
            sum(
                w * len(mine & d.main_keys) / len(mine)
                for d, w in zip(decks, weights, strict=True)
            )
            / total
        )
        if overlap > best_overlap:
            best_aid, best_overlap = aid, overlap
    if best_aid is None or best_overlap < min_overlap:
        return None
    return Match(snap.archetypes[best_aid], "overlap", round(best_overlap, 4))


def find_archetype(snap: Snapshot, name: str) -> MetaArchetype | None:
    """A meta archetype by name: exact (case-folded), else the one whose name
    contains ``name``, the most-played when several do."""
    want = name.strip().casefold()
    exact = [a for a in snap.archetypes.values() if a.name.casefold() == want]
    if exact:
        return exact[0]
    part = [a for a in snap.archetypes.values() if want in a.name.casefold()]
    if not part:
        return None
    return max(part, key=lambda a: _total(a.stats, LADDER_RANKS).matches)


def resolve(
    snap: Snapshot,
    *,
    deck: Mapping | None = None,
    archetype: str | None = None,
    ranks: Sequence[str] = DEFAULT_RANKS,
    lands: Collection[str] = (),
) -> Match | None:
    """The meta archetype to read: the one named, else the one ``deck`` matches
    (``lands``: :func:`match_deck`'s)."""
    if archetype:
        arch = find_archetype(snap, archetype)
        return Match(arch, "named", 1.0) if arch else None
    if deck is None:
        return None
    return match_deck(snap, deck, ranks, lands=lands)


def deck_card_names(deck: Mapping) -> list[str]:
    """Every card a parsed deck runs: commanders, main deck and sideboard."""
    return [
        n
        for zone in ("commanders", "cards", "sideboard")
        for n in _deck_names(deck, zone)
    ]


def mark_held(rows: Iterable[Mapping], names: Iterable[str]) -> list[dict]:
    """``rows`` (card rows with a ``name``) each with ``in_deck``: whether ``names``
    holds it, by the one name folding."""
    have = _keys(names)
    return [{**r, "in_deck": normalize_card_name(r["name"]) in have} for r in rows]


# --- The tuner's context ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MetaContext:
    """What the tuner reads from the deck's meta archetype (ADR-0059): how often
    its lists run each card (``inclusion``) and its core."""

    archetype: Mapping
    match: Match
    period: Mapping
    ranks: tuple[str, ...]
    #: ``normalize_card_name(card)`` -> the share of the lists running it.
    inclusion: Mapping[str, float]
    core: tuple[Mapping, ...]

    def share(self, name: str) -> float:
        """How many of the archetype's lists run ``name`` (0 when none do)."""
        return self.inclusion.get(normalize_card_name(name), 0.0)

    def missing_from(self, names: Iterable[str]) -> list[Mapping]:
        """The core cards ``names`` lacks, most shared first (lands included)."""
        have = _keys(names)
        return [c for c in self.core if normalize_card_name(c["name"]) not in have]

    def to_json(self) -> dict:
        return {
            "archetype": dict(self.archetype),
            "match": self.match.to_json(),
            "period": dict(self.period),
            "ranks": list(self.ranks),
            "core": [dict(c) for c in self.core],
            "cut_share": CUT_SHARE,
            "core_share": CORE_SHARE,
        }


class ListSample(NamedTuple):
    """How much an archetype's published lists say: how many, and their matches."""

    lists: int
    matches: int


def list_sample(
    snap: Snapshot, archetype: int, ranks: Sequence[str] = DEFAULT_RANKS
) -> ListSample:
    """The archetype's published lists and their matches in ``ranks``. Untapped
    publishes lists for a fraction of its archetypes (2026-10: 103 of 1104 on
    Brawl_Ladder), often one thin list, so every core read carries its sample."""
    decks = [d for d in snap.decks if d.archetype == archetype]
    return ListSample(len(decks), sum(_total(d.stats, ranks).matches for d in decks))


def tunable(snap: Snapshot, archetype: int) -> bool:
    """Whether the tuner may read the archetype: its published lists hold at least
    the ranking's ``MIN_MATCHES`` at the tuner's ranks (``DEFAULT_RANKS``), so one
    thin list never condemns every card it lacks. The one test — the report and
    the panel show its answer rather than judge it again."""
    return list_sample(snap, archetype).matches >= MIN_MATCHES


def deck_context(snap: Snapshot, match: Match) -> MetaContext | None:
    """The tuner's meta context for a ``match`` (:func:`resolve`): the archetype's
    card shares and core at ``DEFAULT_RANKS``. ``None`` unless :func:`tunable`."""
    aid = match.archetype.id
    if not tunable(snap, aid):
        return None
    ranks = DEFAULT_RANKS
    shares = card_shares(snap, aid, ranks)
    return MetaContext(
        archetype=_row(snap, match.archetype, ranks, _field_total(snap, ranks)),
        match=match,
        period=snap.period,
        ranks=tuple(ranks),
        inclusion={normalize_card_name(n): v["share"] for n, v in shares.items()},
        core=tuple(core(snap, aid, ranks, shares=shares)),
    )
