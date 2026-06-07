"""HydratedDeck — the value that owns the deck-name -> Scryfall-record join (ADR-0012).

A parsed deck is just ``{format, commanders, cards, sideboard}`` of ``{name, quantity}``
entries; computing curve, lands, colors, legality, or signals needs each name joined to
its full Scryfall record. That join used to be a second positional argument
(``hydrated``) every caller had to keep in sync with the deck — an unenforced invariant
guarded at runtime by ``check_hydration``. ``HydratedDeck`` makes a desynced pair
unconstructable: it carries the deck and its resolved records behind one interface, so
the analysis functions take a single ``HydratedDeck``.

Construction funnels through three adapters into one private ``__init__``:
  - ``from_session(session, by_name)`` — deck-forge, in-process; build one per request.
  - ``from_paths(deck_path, hydrated_path)`` — CLI; the one untrusted-JSON boundary.
  - ``from_parsed(deck, by_name=..., *, records=...)`` — the shared low-level seam.

Conventions (ADR-0012):
  - DROP: an un-hydratable name is absent from ``.records`` / ``.expanded()`` (never
    ``None``); the lone ``None`` is ``.by_name.get(name)`` on a miss.
  - Degraded mode is the typed ``.has_records`` flag, never ``bool(self)``.
  - The desync RAISE fires only where untrusted ``records`` enter (from_paths /
    ``from_parsed(records=...)``).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Protocol

from mtg_utils.card_classify import build_card_lookup


class _DeckSource(Protocol):
    """Anything exposing ``to_deck_dict()`` (e.g. a deck-forge DeckSession)."""

    def to_deck_dict(self) -> dict: ...


_ZONES = ("commanders", "cards", "sideboard")


def _distinct_names(deck: Mapping) -> list[str]:
    """Distinct card names across all zones, in commanders->cards->sideboard order."""
    seen: dict[str, None] = {}
    for zone in _ZONES:
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

    __slots__ = ("_by_name", "_deck", "_records")

    def __init__(self, deck: dict, records: list[dict]) -> None:
        """Internal. Use ``from_session`` / ``from_paths`` / ``from_parsed``.

        ``records`` must already be the resolved, distinct, no-None projection.
        """
        self._deck = deck
        self._records = records
        self._by_name = build_card_lookup(records)

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
    def from_session(
        cls, session: _DeckSource, by_name: Mapping[str, dict]
    ) -> HydratedDeck:
        """Build from a deck-forge session (anything exposing ``to_deck_dict()``) and a
        name->record index, joining once. Subsumes ``DeckSession.hydrated`` /
        ``hydrated_expanded`` and the per-request re-derivations in the backend hub."""
        return cls.from_parsed(session.to_deck_dict(), by_name)

    @classmethod
    def from_paths(
        cls,
        deck_path: str | os.PathLike,
        hydrated_path: str | os.PathLike | None,
    ) -> HydratedDeck:
        """Build from on-disk JSON — the CLI adapter, and the one boundary that reads
        untrusted input. ``hydrated_path=None`` is the optional-hydration case (e.g.
        combo_search) and yields the degraded state. A hydrated file containing deck
        stubs raises ``ValueError`` here."""
        deck = json.loads(Path(deck_path).read_text(encoding="utf-8"))
        if hydrated_path is None:
            return cls.from_parsed(deck)
        records = json.loads(Path(hydrated_path).read_text(encoding="utf-8"))
        return cls.from_parsed(deck, records=records)

    # --- projections -----------------------------------------------------------

    @property
    def deck(self) -> dict:
        """The untouched canonical {format, commanders, cards, sideboard} dict — the
        serializable shape autosave/export consume. HydratedDeck augments it, never
        replaces it."""
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

    def expanded(self, zones: tuple[str, ...] = ("cards", "sideboard")) -> list[dict]:
        """Records repeated by quantity for copy-aware counting (slot budgets). Walks
        ``zones`` in order, drops missing names; the command zone is excluded by
        default."""
        for zone in zones:
            if zone not in _ZONES:
                msg = f"unknown zone {zone!r}; expected one of {_ZONES}"
                raise ValueError(msg)
        out: list[dict] = []
        for zone in zones:
            for entry in self._deck.get(zone) or []:
                record = self._by_name.get(entry["name"])
                if record is not None:
                    out.extend([record] * int(entry.get("quantity", 1)))
        return out

    def entries(
        self, *, zones: tuple[str, ...] = ("commanders", "cards")
    ) -> list[tuple[dict, dict | None]]:
        """``(entry, record)`` pairs in zone+deck order, where ``record`` is the joined
        Scryfall dict or ``None`` for a miss. Pairs the deck-side quantity with its
        (possibly absent) record in one walk, so the two halves cannot drift apart."""
        for zone in zones:
            if zone not in _ZONES:
                msg = f"unknown zone {zone!r}; expected one of {_ZONES}"
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
        card_count = sum(len(self._deck.get(z) or []) for z in _ZONES)
        return card_count == 0

    # --- zone pass-throughs ----------------------------------------------------

    @property
    def format(self) -> str:
        return self._deck.get("format", "commander")

    @property
    def commanders(self) -> list[dict]:
        return self._deck.get("commanders") or []

    @property
    def cards(self) -> list[dict]:
        return self._deck.get("cards") or []

    @property
    def sideboard(self) -> list[dict]:
        return self._deck.get("sideboard") or []

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
