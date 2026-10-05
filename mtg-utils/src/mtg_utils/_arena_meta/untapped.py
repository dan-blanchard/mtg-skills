"""Untapped.gg's Premium meta API: sign-in, fetch, and the on-disk cache (ADR-0059).

Verified live (2026-10-05): the Premium endpoints authorize by session cookies alone,
and only after a real page load has refreshed the session (a bare API call with the
cookies gets a 403). So the client opens a persistent Playwright profile, loads one
Untapped page, and calls the API through that browser context:

- ``meta-periods/active`` — one period per Arena event name (``Brawl_Ladder``,
  ``Traditional_Ladder``…), each with its predecessor. The event's newest period is
  the current meta; ``--previous`` reads its predecessor.
- ``analytics/query/{archetypes,decks}_by_event_scope_and_rank_v2/premium`` with
  ``MetaPeriodId`` and ``RankingClassScopeFilter`` — ``BRONZE_TO_MYTHIC`` on a ranked
  ladder, ``ALL`` on an unranked queue (``Play_Brawl_Historic``).
- ``tags`` — names for each archetype's ``primary_tags``.

A 403 means the session has expired: :class:`SignInRequiredError` tells the user to run
``arena-meta --login``. Playwright is imported only here, only when fetching, so a
skill that never fetches never needs a browser.

Snapshots are cached under ``<cache root>/untapped/meta/`` for 24 hours (a closed
previous period, for good); the tuner and the hub read only this cache.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

from mtg_utils._arena_meta.meta import Snapshot, build_snapshot
from mtg_utils._http import cache_root, is_fresh
from mtg_utils._sidecar import atomic_write_json

if TYPE_CHECKING:
    from playwright.sync_api import PlaywrightContextManager

    from mtg_utils._arena_meta.meta import MetaContext
    from mtg_utils.card_pool import CardPool
    from mtg_utils.hydrated_deck import HydratedDeck

SITE = "https://mtga.untapped.gg/"
API = "https://api.mtga.untapped.gg/api/v1/"
#: Any real page refreshes the session before the API calls (a 404 page doesn't).
WARM_PAGE = SITE + "constructed/standard/decks"
_ARCHETYPES = "analytics/query/archetypes_by_event_scope_and_rank_v2/premium"
_DECKS = "analytics/query/decks_by_event_scope_and_rank_v2/premium"
_CACHE_HOURS = 24
_TIMEOUT_MS = 60_000


class MetaError(Exception):
    """Untapped meta data can't be had right now; the message says what to do."""


class SignInRequiredError(MetaError):
    def __init__(self) -> None:
        super().__init__(
            "Untapped's Premium meta data needs a signed-in session: run "
            "`arena-meta --login` and sign in to your Untapped account."
        )


class BrowserMissingError(MetaError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"arena-meta needs Playwright's Chromium ({detail}): run "
            "`uv run playwright install chromium` in this skill's directory."
        )


def meta_dir() -> Path:
    return cache_root() / "untapped" / "meta"


def profile_dir() -> Path:
    return cache_root() / "untapped" / "profile"


def _playwright() -> PlaywrightContextManager:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserMissingError("playwright isn't installed") from exc
    return sync_playwright()


def login() -> None:
    """Open a visible browser on Untapped with the persistent profile; the user
    signs in and closes the window. Blocks until it is closed."""
    profile = profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    with _playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(str(profile), headless=False)
        except Exception as exc:  # playwright's launch error: no browser binary
            raise BrowserMissingError(str(exc).splitlines()[0]) from exc
        ctx.new_page().goto(SITE)
        ctx.wait_for_event("close", timeout=0)


def is_ranked_event(event: str) -> bool:
    """A ranked ladder reports rank buckets; Arena's ``Play_*`` queues don't."""
    return "Ladder" in event


def pick_period(
    periods: Iterable[Mapping],
    event: str,
    *,
    previous: bool = False,
    period_id: int | None = None,
) -> dict:
    """The meta period to read: ``period_id`` when given, else ``event``'s newest
    (or, with ``previous``, the one before it)."""
    rows = [dict(p) for p in periods]
    if period_id is not None:
        for row in rows:
            if row.get("id") == period_id:
                return row
        return {"id": period_id, "event_name": event}
    mine = [p for p in rows if p.get("event_name") == event]
    if not mine:
        raise MetaError(f"Untapped lists no active meta period for {event}")
    newest = max(mine, key=lambda p: str(p.get("start_ts", "")))
    if not previous:
        return newest
    before = newest.get("predecessor_id")
    if before is None:
        raise MetaError(f"{event}'s current period has no predecessor")
    for row in rows:
        if row.get("id") == before:
            return row
    return {"id": before, "event_name": event}


def _period_summary(period: Mapping) -> dict:
    return {
        "id": period.get("id"),
        "predecessor_id": period.get("predecessor_id"),
        "description": period.get("description"),
        "start": str(period.get("start_ts") or "")[:10] or None,
        "end": str(period.get("end_ts") or "")[:10] or None,
    }


class _Session:
    """A headless browser context on the persistent profile, warmed by one page
    load, whose request API carries the session cookies."""

    def __enter__(self) -> Self:
        profile = profile_dir()
        if not profile.exists():
            raise SignInRequiredError
        self._pw = _playwright().start()
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(
                str(profile), headless=True
            )
        except Exception as exc:
            self._pw.stop()
            raise BrowserMissingError(str(exc).splitlines()[0]) from exc
        self._ctx.new_page().goto(
            WARM_PAGE, wait_until="domcontentloaded", timeout=_TIMEOUT_MS
        )
        return self

    def get(self, path: str, **params: str | float) -> list | dict | None:
        resp = self._ctx.request.get(API + path, params=params, timeout=_TIMEOUT_MS)
        if resp.status in (401, 403):
            raise SignInRequiredError
        if resp.status >= 400:
            raise MetaError(f"Untapped answered {resp.status} for {path}")
        body = resp.body()
        return json.loads(body) if body.strip() else None

    def __exit__(self, *_exc: object) -> None:
        self._ctx.close()
        self._pw.stop()


def fetch_raw(
    event: str, *, previous: bool = False, period_id: int | None = None
) -> dict:
    """One meta period's raw bundle — ``{event, period, fetched_at, tags,
    archetypes, decks}`` — straight from Untapped."""
    with _Session() as session:
        periods = session.get("meta-periods/active") or []
        period = pick_period(periods, event, previous=previous, period_id=period_id)
        scope = "BRONZE_TO_MYTHIC" if is_ranked_event(event) else "ALL"
        query = {"MetaPeriodId": period["id"], "RankingClassScopeFilter": scope}
        archetypes = session.get(_ARCHETYPES, **query) or []
        decks = session.get(_DECKS, **query) or []
        tags = session.get("tags") or []
    used = {t for a in archetypes for t in a.get("primary_tags", ())}
    return {
        "event": event,
        "period": _period_summary(period),
        "fetched_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "tags": [t for t in tags if t.get("id") in used],
        "archetypes": archetypes,
        "decks": decks,
    }


# --- Naming the cards ---------------------------------------------------------------


def resolve_titles(
    title_ids: Collection[int],
    cards: Iterable[Mapping],
    loc: Iterable[Mapping],
    by_arena_id: Mapping[int, list[dict]] | None = None,
) -> tuple[dict[int, str], set[str]]:
    """titleId -> card name, and which of those names are lands.

    A titleId names a card across its printings (``cards.json`` maps each grpid
    to one). The name is the card-data record's for the first grpid the pool knows
    (``CardPool.by_arena_id`` — the name every deck tool keys on), else Arena's own
    English title (``loc_en.json``)."""
    from mtg_utils.arena_card_db import arena_title
    from mtg_utils.card_classify import BASIC_LAND_NAMES, is_land

    wanted = set(title_ids)
    grpids: dict[int, list[int]] = defaultdict(list)
    for rec in cards:
        title = rec.get("titleId")
        if title in wanted and not rec.get("isToken"):
            grpids[title].append(int(rec["grpid"]))
    text = {int(e["id"]): str(e.get("text", "")) for e in loc if e.get("id") in wanted}
    names: dict[int, str] = {}
    lands: set[str] = set()
    for title in wanted:
        record = next(
            (
                by_arena_id[g][0]
                for g in grpids.get(title, ())
                if by_arena_id and by_arena_id.get(g)
            ),
            None,
        )
        name = record["name"] if record else arena_title(None, text.get(title))
        if not name:
            continue
        names[title] = name
        if (record and is_land(record)) or name in BASIC_LAND_NAMES:
            lands.add(name)
    return names, lands


def _title_ids(raw: Mapping) -> set[int]:
    from mtg_utils._arena_meta.deckstring import DeckstringError, decode

    out: set[int] = set()
    for row in raw.get("decks", ()):
        try:
            deck = decode(row["ds"])
        except (DeckstringError, KeyError):
            continue
        out.update(deck.commanders, deck.companions)
        out.update(t for t, _ in (*deck.main, *deck.sideboard))
    return out


def snapshot_from_raw(raw: Mapping, *, pool: CardPool | None = None) -> Snapshot:
    """A :class:`Snapshot` from a raw bundle. A bundle carrying its own ``names``
    (``{titleId: name}``) and ``lands`` is self-contained (tests, offline
    ``--from-json``); otherwise names come from Untapped's public card files and the
    card pool (``pool``, a ``CardPool``, optional)."""
    if "names" in raw:
        names = {int(k): v for k, v in raw["names"].items()}
        return build_snapshot(raw, names, lands=raw.get("lands", ()))
    from mtg_utils.limited_stats import mtgajson_files

    cards, loc = mtgajson_files()
    names, lands = resolve_titles(
        _title_ids(raw), cards, loc, pool.by_arena_id if pool is not None else None
    )
    return build_snapshot(raw, names, lands=lands)


# --- The cache ------------------------------------------------------------------------


def _snapshot_path(event: str, *, previous: bool, period_id: int | None) -> Path:
    which = (
        str(period_id)
        if period_id is not None
        else ("previous" if previous else "current")
    )
    return meta_dir() / f"{event}.{which}.json"


_MEMO: dict[Path, tuple[int, Snapshot]] = {}


def cached_snapshot(
    event: str, *, previous: bool = False, period_id: int | None = None
) -> Snapshot | None:
    """The cached snapshot for ``event``, whatever its age, or ``None``. Never
    fetches: the tuner and the hub read only this. Memoized per file version, so a
    Tune re-run doesn't re-parse it (a refresh rewrites the file)."""
    path = _snapshot_path(event, previous=previous, period_id=period_id)
    try:
        version = path.stat().st_mtime_ns
        memo = _MEMO.get(path)
        if memo is None or memo[0] != version:
            snap = Snapshot.from_json(json.loads(path.read_text(encoding="utf-8")))
            _MEMO[path] = memo = (version, snap)
    except (OSError, ValueError, KeyError):
        return None
    return memo[1]


def snapshot_age_hours(snap: Snapshot) -> float | None:
    try:
        fetched = datetime.fromisoformat(snap.fetched_at)
    except ValueError:
        return None
    return (datetime.now(tz=UTC) - fetched).total_seconds() / 3600


def snapshot_is_stale(snap: Snapshot) -> bool:
    """Older than the cache's 24 hours (a closed period never matters)."""
    age = snapshot_age_hours(snap)
    return age is not None and age >= _CACHE_HOURS


def deck_queues(hd: HydratedDeck) -> tuple[tuple[str, bool], ...]:
    """The Arena queues a deck reads, best first (``Format.arena_queues``): the
    first is the one a fetch fills; the rest are read-only fallbacks."""
    return hd.format.arena_queues(sideboard=bool(hd.deck.get("sideboard")))


def deck_queue(hd: HydratedDeck) -> tuple[str, bool, Snapshot | None] | None:
    """The Arena queue a deck reads now — ``(event, bo3, cached snapshot)``: the
    first of :func:`deck_queues` with a cache, else the preferred one with
    ``None``. ``None`` for a format with no queue."""
    queues = deck_queues(hd)
    for event, bo3 in queues:
        snap = cached_snapshot(event)
        if snap is not None:
            return event, bo3, snap
    return (*queues[0], None) if queues else None


def load_snapshot(
    event: str,
    *,
    previous: bool = False,
    period_id: int | None = None,
    refresh: bool = False,
    pool: CardPool | None = None,
) -> Snapshot:
    """The snapshot for ``event``: the cache while fresh (24 hours — a period
    pinned by id never changes), else a fetch that rewrites it. ``--previous``
    expires like the current period: after a set release, "previous" is a new
    period."""
    path = _snapshot_path(event, previous=previous, period_id=period_id)
    fresh = period_id is not None or is_fresh(path, max_age_hours=_CACHE_HOURS)
    if not refresh and path.exists() and fresh:
        cached = cached_snapshot(event, previous=previous, period_id=period_id)
        if cached is not None:
            return cached
    raw = fetch_raw(event, previous=previous, period_id=period_id)
    snap = snapshot_from_raw(raw, pool=pool)
    atomic_write_json(path, snap.to_json())
    return snap


def deck_lands(hd: HydratedDeck) -> list[str]:
    """The deck's lands by their hydrated types (``match_deck``'s ``lands``)."""
    from mtg_utils.card_classify import is_land

    return [r["name"] for r in hd.deck_records() if is_land(r)]


def cached_deck_context(
    hd: HydratedDeck, medium: str, *, archetype: str | None = None
) -> tuple[MetaContext | None, str | None]:
    """The tuner's meta context for ``hd`` from the CACHE alone (:func:`deck_queue`),
    and a note saying what was read or why nothing was — ``None`` where no meta
    applies (a paper build, a format with no Arena queue)."""
    from mtg_utils._arena_meta.meta import deck_context
    from mtg_utils.formats import medium_is_digital

    fmt = hd.format
    if not medium_is_digital(medium):
        return None, None
    queue = deck_queue(hd)
    if queue is None:
        return None, None
    snap = queue[2]
    if snap is None:
        return None, f"meta: none cached — run `arena-meta --format {fmt.name}`"
    ctx = deck_context(snap, hd.deck, archetype=archetype, lands=deck_lands(hd))
    if ctx is None:
        return None, f"meta: the deck matches no {snap.event} meta archetype"
    stale = ", stale" if snapshot_is_stale(snap) else ""
    return ctx, (
        f"meta: {ctx.archetype['name']} ({snap.event} period "
        f"{snap.period.get('id')}{stale})"
    )
