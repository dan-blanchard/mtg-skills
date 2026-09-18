"""HydratedDeck — the value that owns the deck-name -> Scryfall-record join (ADR-0012).

A parsed deck is just ``{format, commanders, cards, sideboard}`` of ``{name, quantity}``
entries; computing curve, lands, colors, legality, or signals needs each name joined to
its full Scryfall record. That join used to be a second positional argument
(``hydrated``) every caller had to keep in sync with the deck — an unenforced invariant
guarded at runtime by ``check_hydration``. ``HydratedDeck`` makes a desynced pair
unconstructable: it carries the deck and its resolved records behind one interface, so
the analysis functions take a single ``HydratedDeck``.

Construction funnels through three adapters into one private ``__init__``:
  - ``acquire(deck_path, ...)`` — the deck-acquisition seam (ADR-0046): a deck JSON on
    disk becomes a HydratedDeck, joined against the ``CardPool`` and memoized in a
    sidecar beside the deck (``deck.json`` -> ``deck.hydrated.json``). Every deck CLI
    enters here.
  - ``from_session(session, by_name)`` — deck-forge, in-process; build one per request.
  - ``from_parsed(deck, by_name=..., *, records=...)`` — the shared low-level seam.

Conventions (ADR-0012):
  - DROP: an un-hydratable name is absent from ``.records`` / ``.expanded()`` (never
    ``None``); the lone ``None`` is ``.by_name.get(name)`` on a miss, and ``.missing``
    lists them.
  - Degraded mode is the typed ``.has_records`` flag, never ``bool(self)``.
  - The desync RAISE fires only where untrusted ``records`` enter
    (``from_parsed(records=...)``, which the sidecar read goes through).
  - One record shape (ADR-0046): a record is the bulk's own adapter record, keys absent
    when the card has no such field — never a None-filled projection.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Protocol

from mtg_utils._sidecar import atomic_write_json
from mtg_utils.card_classify import build_card_lookup
from mtg_utils.card_pool import CardPool, NoBulkError
from mtg_utils.formats import Format

# Bump when the sidecar payload shape (or the record shape it stores) changes, so an
# old sidecar is rebuilt instead of read. v1: full adapter records, all four zones.
# v2: five zones — the limited ``pool`` joins beside the sideboard.
HYDRATED_VERSION = 2
HYDRATED_SUFFIX = ".hydrated.json"


def sidecar_path(deck_path: str | os.PathLike) -> Path:
    """Where ``acquire`` memoizes a deck's join: ``<dir>/<stem>.hydrated.json`` beside
    the deck (``deck.json`` -> ``deck.hydrated.json``). Visible on purpose — an agent
    can Grep it for an oracle pattern."""
    path = Path(deck_path)
    return path.with_name(path.stem + HYDRATED_SUFFIX)


def _deck_digest(deck_content: str) -> str:
    """The deck-content half of the sidecar key, stored on its own so a no-bulk
    reader (which cannot compute the bulk half) can still tell "this deck" apart."""
    return hashlib.sha256(deck_content.encode()).hexdigest()[:16]


def _hydration_key(deck_content: str, pool_identity: str) -> str:
    """The sidecar's validity key: the deck's exact content, the bulk's identity and
    the payload version. Any of the three changing invalidates the sidecar, so a
    stale join is unreadable by construction (no "switch to the new cache_path")."""
    hasher = hashlib.sha256()
    hasher.update(deck_content.encode())
    hasher.update(f"|bulk:{pool_identity}|v{HYDRATED_VERSION}".encode())
    return hasher.hexdigest()[:16]


def records_from_file(path: str | os.PathLike) -> list[dict]:
    """The card records in a JSON file that is EITHER a bare records list (a
    ``scryfall-lookup --batch`` cache of candidates) OR a hydrated sidecar payload
    (``<deck>.hydrated.json``) — for a CLI that reads a record list rather than a
    deck (``archetype-audit``, ``card-summary`` on a list), so the sidecar is usable
    wherever a records file is. Raises ``ValueError`` on any other shape."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    msg = f"{path}: expected a JSON list of card records or a hydrated sidecar"
    raise ValueError(msg)


def _sidecar_records(
    path: Path, valid: Callable[[dict], bool]
) -> list[dict | None] | None:
    """The sidecar's records if it exists, parses, and *valid* accepts its payload
    (the caller's selector: the full validity key, or the deck digest + payload
    version for the no-bulk read); else None."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not valid(payload):
        return None
    records = payload.get("records")
    return records if isinstance(records, list) else None


def _write_sidecar(
    sidecar: Path, deck_content: str, pool: CardPool, hd: HydratedDeck
) -> None:
    """Memoize *hd*'s join: both selectors (the full key and the deck digest) are
    derived here from the one *deck_content*, so they can never disagree."""
    atomic_write_json(
        sidecar,
        {
            "version": HYDRATED_VERSION,
            "key": _hydration_key(deck_content, pool.identity),
            "deck": _deck_digest(deck_content),
            "bulk": str(pool.path) if pool.path is not None else None,
            "missing": hd.missing,
            "records": hd.records,
        },
    )


class _DeckSource(Protocol):
    """Anything exposing ``to_deck_dict()`` (e.g. a deck-forge DeckSession)."""

    def to_deck_dict(self) -> dict: ...


# "companion" hydrates like any zone (its record is needed for companion-condition
# audits) but is outside the game (CR 702.139a-b): deck-size / curve / budget math
# must request zones explicitly and exclude it.
#: The deck's zones. ``pool`` is the limited family's opened pool (CR 100.2b) —
#: hydrated like any zone, counted by none of the deck analyses (they walk the zones
#: they mean by name).
ZONES = ("commanders", "cards", "sideboard", "companion", "pool")


def _distinct_names(deck: Mapping) -> list[str]:
    """Distinct card names across all zones, in commanders->cards->sideboard->
    companion->pool order."""
    seen: dict[str, None] = {}
    for zone in ZONES:
        for entry in deck.get(zone) or []:
            seen.setdefault(entry["name"], None)
    return list(seen)


def _has_stub(records: list[dict | None]) -> bool:
    """True if any record is a deck-entry stub ({name, quantity}, no type_line) — the
    unambiguous 'passed the un-hydrated deck where records belong' misuse."""
    return any(
        r is not None and "quantity" in r and "type_line" not in r for r in records
    )


class HydratedDeck:
    """An immutable deck + its joined Scryfall records (see module docstring)."""

    __slots__ = ("_by_name", "_deck", "_format", "_records")

    def __init__(self, deck: dict, records: list[dict]) -> None:
        """Internal. Use ``acquire`` / ``from_session`` / ``from_parsed``.

        ``records`` must already be the resolved, distinct, no-None projection. The
        deck's format (and its explicit ``deck_size``) is resolved here, so an unknown
        format or an impossible size fails at the boundary, not deep in an audit.
        """
        self._deck = deck
        self._records = records
        self._by_name = build_card_lookup(records)
        self._format = Format.for_deck(deck)

    # --- constructors ----------------------------------------------------------

    @classmethod
    def from_parsed(
        cls,
        deck: dict,
        by_name: Mapping[str, dict] | None = None,
        *,
        records: list[dict | None] | None = None,
    ) -> HydratedDeck:
        """Build from an already-parsed deck dict. Exactly one join source:

        - ``by_name``: a name->record index (in-process; e.g. the bulk index). Trusted;
          no stub check — the value's shape makes the footgun unconstructable.
        - ``records``: a raw records list (untrusted, e.g. a hydrated JSON file). The
          desync RAISE fires here on deck-entry stubs.

        Passing both is a programmer error. Passing neither yields the degraded state.
        """
        if by_name is not None and records is not None:
            msg = "from_parsed: pass by_name OR records, not both"
            raise ValueError(msg)

        distinct = _distinct_names(deck)
        if records is not None:
            if _has_stub(records):
                msg = (
                    "HydratedDeck: the records list contains deck-entry stubs "
                    "({name, quantity} with no 'type_line') — pass hydrated Scryfall "
                    "records, not a deck. (Stale or wrong --hydrated file?)"
                )
                raise ValueError(msg)
            index = build_card_lookup(records)
            resolved = [index[n] for n in distinct if n in index]
        elif by_name is not None:
            resolved = [by_name[n] for n in distinct if n in by_name]
        else:
            resolved = []
        return cls(deck, resolved)

    @classmethod
    def acquire(
        cls,
        deck_path: str | os.PathLike,
        *,
        pool: CardPool | None = None,
        bulk_path: str | os.PathLike | None = None,
        require_records: bool = True,
        fetch: Callable[[str], dict | None] | None = None,
    ) -> HydratedDeck:
        """The deck-acquisition seam (ADR-0046): read the deck JSON at *deck_path* and
        join every zone (commanders / cards / sideboard / companion) against the
        card pool, memoized in the sidecar beside the deck (:func:`sidecar_path`).

        - A sidecar whose key matches (same deck content, same bulk, same payload
          version) is read instead of the bulk — no bulk load at all.
        - On a miss the pool is *pool*, else loaded from *bulk_path* (``None``:
          auto-discovered). A name the pool cannot resolve is tried once against
          *fetch* (default: Scryfall's per-card endpoint, the ADR-0005 cache-miss
          path; pass ``lambda _: None`` to stay offline), and the sidecar is written.
        - No bulk and no valid sidecar: :class:`NoBulkError`, unless
          ``require_records=False`` (a CLI that works on names alone, e.g.
          combo-search), which yields the degraded state.
        """
        path = Path(deck_path)
        content = path.read_text(encoding="utf-8")
        deck = json.loads(content)
        sidecar = sidecar_path(path)

        if pool is None:
            try:
                pool = CardPool.load(Path(bulk_path) if bulk_path else None)
            except NoBulkError:
                if require_records:
                    raise
                # No bulk: the key's bulk half can't be computed, but a sidecar of
                # THIS deck (any bulk) beats no records when they are optional.
                digest = _deck_digest(content)
                cached = _sidecar_records(
                    sidecar,
                    lambda p: (
                        p.get("deck") == digest and p.get("version") == HYDRATED_VERSION
                    ),
                )
                return cls.from_parsed(deck, records=cached)

        key = _hydration_key(content, pool.identity)
        cached = _sidecar_records(sidecar, lambda p: p.get("key") == key)
        if cached is not None:
            return cls.from_parsed(deck, records=cached)

        if fetch is None:
            from mtg_utils.scryfall_lookup import fetch_card

            fetch = fetch_card
        records: list[dict] = []
        for name in _distinct_names(deck):
            record = pool.by_name.get(name)
            if record is None:
                record = fetch(name)
            if record is not None:
                records.append(record)
        hd = cls(deck, records)
        _write_sidecar(sidecar, content, pool, hd)
        return hd

    def write_sidecar(self, deck_path: str | os.PathLike, pool: CardPool) -> Path:
        """Memoize THIS join beside *deck_path* (which must hold ``self.deck`` as
        written) — for a CLI that derives a new deck in-process (build-deck) so the
        next tool reads the sidecar instead of re-joining. Returns the sidecar path."""
        path = Path(deck_path)
        sidecar = sidecar_path(path)
        _write_sidecar(sidecar, path.read_text(encoding="utf-8"), pool, self)
        return sidecar

    @classmethod
    def from_session(
        cls, session: _DeckSource, by_name: Mapping[str, dict]
    ) -> HydratedDeck:
        """Build from a deck-forge session (anything exposing ``to_deck_dict()``) and a
        name->record index, joining once. Subsumes ``DeckSession.hydrated`` /
        ``hydrated_expanded`` and the per-request re-derivations in the backend hub."""
        return cls.from_parsed(session.to_deck_dict(), by_name)

    # --- projections -----------------------------------------------------------

    @property
    def deck(self) -> dict:
        """The untouched canonical {format, commanders, cards, sideboard, companion,
        pool} dict — the serializable shape autosave/export consume. HydratedDeck
        augments it, never replaces it."""
        return self._deck

    @property
    def records(self) -> list[dict]:
        """One record per distinct card name across all zones, in deck order, missing
        names DROPPED (never None)."""
        return self._records

    @property
    def by_name(self) -> Mapping[str, dict]:
        """Alias-aware name->record index (canonical / DFC front-face / printed_name /
        flavor_name), built once. ``.get(name)`` is None for a miss."""
        return self._by_name

    @property
    def missing(self) -> list[str]:
        """Distinct deck names (all zones, deck order) with no joined record — the
        DROP convention's ledger, so a CLI can warn about a typo or an unknown card
        instead of silently under-counting."""
        return [n for n in _distinct_names(self._deck) if n not in self._by_name]

    def expanded(self, zones: tuple[str, ...] = ("cards", "sideboard")) -> list[dict]:
        """Records repeated by quantity for copy-aware counting (slot budgets). Walks
        ``zones`` in order, drops missing names; the command zone is excluded by
        default."""
        for zone in zones:
            if zone not in ZONES:
                msg = f"unknown zone {zone!r}; expected one of {ZONES}"
                raise ValueError(msg)
        out: list[dict] = []
        for zone in zones:
            for entry in self._deck.get(zone) or []:
                record = self._by_name.get(entry["name"])
                if record is not None:
                    out.extend([record] * int(entry.get("quantity", 1)))
        return out

    def deck_quantities(
        self, *, zones: tuple[str, ...] = ("commanders", "cards")
    ) -> list[tuple[dict, int]]:
        """``(record, copies)`` per distinct card name in ``zones`` (the counted deck
        by default — commanders + main deck, never the sideboard), in zone + deck
        order, copies summed across the zones, missing names dropped — what a
        copy-aware analysis (the tuner's classes) counts."""
        seen: dict[str, int] = {}
        order: list[dict] = []
        for entry, record in self.entries(zones=zones):
            if record is None:
                continue
            name = record.get("name", "")
            if name not in seen:
                seen[name] = 0
                order.append(record)
            seen[name] += int(entry.get("quantity", 1))
        return [(r, seen[r.get("name", "")]) for r in order]

    def deck_records(
        self, *, zones: tuple[str, ...] = ("commanders", "cards")
    ) -> list[dict]:
        """One record per distinct card name in ``zones`` (the counted deck by
        default), in zone + deck order, missing names dropped. The all-zones
        ``records`` is for hydration bookkeeping; an analysis of the deck reads
        this."""
        return [r for r, _ in self.deck_quantities(zones=zones)]

    def entries(
        self, *, zones: tuple[str, ...] = ("commanders", "cards")
    ) -> list[tuple[dict, dict | None]]:
        """``(entry, record)`` pairs in zone+deck order, where ``record`` is the joined
        Scryfall dict or ``None`` for a miss. Pairs the deck-side quantity with its
        (possibly absent) record in one walk, so the two halves cannot drift apart."""
        for zone in zones:
            if zone not in ZONES:
                msg = f"unknown zone {zone!r}; expected one of {ZONES}"
                raise ValueError(msg)
        out: list[tuple[dict, dict | None]] = []
        for zone in zones:
            for entry in self._deck.get(zone) or []:
                out.append((entry, self._by_name.get(entry["name"])))
        return out

    # --- degraded-mode flag ----------------------------------------------------

    @property
    def has_records(self) -> bool:
        """False ONLY when the deck has cards but no records joined (no-bulk degraded
        mode); True for an empty deck or any records present. The queryable successor to
        check_hydration's WARN — distinct from an empty deck."""
        if self._records:
            return True
        card_count = sum(len(self._deck.get(z) or []) for z in ZONES)
        return card_count == 0

    # --- zone pass-throughs ----------------------------------------------------

    @property
    def format(self) -> Format:
        """The deck's ``Format`` with its own ``deck_size`` applied — every analysis
        reads legality / size / family from here, never from the raw dict."""
        return self._format

    @property
    def commanders(self) -> list[dict]:
        return self._deck.get("commanders") or []

    @property
    def cards(self) -> list[dict]:
        return self._deck.get("cards") or []

    @property
    def sideboard(self) -> list[dict]:
        return self._deck.get("sideboard") or []

    @property
    def companion(self) -> list[dict]:
        """The outside-the-game companion zone (CR 702.139a-b) — never part of
        deck-size, curve, or sideboard counts."""
        return self._deck.get("companion") or []

    @property
    def pool(self) -> list[dict]:
        """A limited build's opened pool (CR 100.2b): what the deck and sideboard
        must be drawn from. Never part of any count."""
        return self._deck.get("pool") or []

    # --- drop-in sugar over .records (deliberately NOT __bool__) ----------------

    def __iter__(self) -> Iterator[dict]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        # A HydratedDeck is always truthy: degraded mode is the explicit .has_records
        # flag, never `if hd:`. Defuses the __len__ fallback that would otherwise make
        # bool(hd) conflate an empty deck with no-bulk.
        return True
