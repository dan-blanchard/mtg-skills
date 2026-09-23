"""CardPool — the one owner of the card-data bulk and every index over it (ADR-0046).

Before this module, five call sites each loaded the bulk and built their own
name -> record index with a subtly different policy (cheapest printing / first-seen /
prefer-oracle-text / cheapest-plus-token-skip), the per-format Arena rarity index and
the unreleased-oracle set lived in ``scryfall_lookup`` and ``card_search``, the hub
built its printing indexes and object resolver in ``production.py``, and ``mark_owned``
walked the bulk again for its Arena alias map. Every one of them read the same
``load_bulk_cards`` list.

``CardPool`` is that list plus every index the deck domain asks of it, behind one
value: ``CardPool.load(bulk_path)`` (``None`` auto-discovers the MTGJSON bulk per
ADR-0033/ADR-0005) and the lazily-built, memoized projections below. Indexes are built
on first use, so a caller that only needs ``by_name`` never pays for the printings
walk, and a process that loads the same bulk twice shares one pool.

Index policy (ONE, replacing four): a name resolves to the cheapest priced printing
among game layouts (no token / art-series / memorabilia records), a printing with
oracle text beating a text-less placeholder — so a deck hydrates with a real price, a
proxy never renders blank, and a token can never shadow a card name. Tokens stay
reachable by printing id (``by_id``), which proxies need for ``all_parts``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mtg_utils._name_index import NameIndex, build_name_index, keep_cheaper
from mtg_utils.arena_card_db import find_card_db, primary_rarities
from mtg_utils.bulk_loader import bulk_mtime, default_bulk_path, load_bulk_cards
from mtg_utils.card_classify import BASIC_LAND_NAMES, SKIP_LAYOUTS
from mtg_utils.formats import Format
from mtg_utils.names import normalize_card_name

__all__ = ["CardPool", "NoBulkError", "is_game_card"]


class NoBulkError(FileNotFoundError):
    """No card-data bulk on disk (and none passed). The message names the fix."""

    def __init__(self, bulk_path: Path | None = None) -> None:
        where = f" at {bulk_path}" if bulk_path is not None else ""
        super().__init__(
            f"card-data bulk not found{where} — run `download-mtgjson` first "
            "(or pass --bulk-data)."
        )


_NON_GAME_SET_TYPES = frozenset({"token", "memorabilia"})


def is_game_card(card: dict) -> bool:
    """The pool's prefilter: a record you could actually put in a deck — game layouts
    only (no token / art-series / emblem layouts) and no token / memorabilia sets."""
    return (
        card.get("layout") not in SKIP_LAYOUTS
        and card.get("set_type") not in _NON_GAME_SET_TYPES
    )


def _keep_best_printing(existing: dict, new: dict) -> dict:
    """The name-index reducer: a printing WITH oracle text beats a text-less
    placeholder (a blank proxy is worse than an expensive one); otherwise the cheaper
    priced printing wins (``keep_cheaper``)."""
    if not existing.get("oracle_text") and new.get("oracle_text"):
        return new
    if existing.get("oracle_text") and not new.get("oracle_text"):
        return existing
    return keep_cheaper(existing, new)


RARITY_ORDER = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "mythic": 3,
    "special": 2,
    "bonus": 2,
}


def _keep_lowest_rarity(existing: dict, new: dict) -> dict:
    """Arena acquisition-cost reducer: a card's wildcard cost is the LOWEST rarity among
    its legal printings, so the lower ``RARITY_ORDER`` rank wins."""
    existing_rank = RARITY_ORDER.get(existing.get("rarity", "rare"), 2)
    new_rank = RARITY_ORDER.get(new.get("rarity", "rare"), 2)
    return new if new_rank < existing_rank else existing


def _collector_key(card: dict) -> tuple[int, int, str]:
    """A sortable collector number: a digit-bearing number sorts by its digits ("12a"
    by 12, "A-123" by 123), ties by the raw string; a number with no digit at all
    sorts after every one that has."""
    raw = str(card.get("collector_number") or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    return (0, int(digits), raw) if digits else (1, 0, raw)


def _rarity_value(card: dict, arena: dict[str, str]) -> dict:
    """``{rarity, free}`` for *card*: Arena's own rarity when its card database lists
    the card (by full name or front face), else this printing's."""
    name = card.get("name", "")
    rarity = arena.get(normalize_card_name(name)) or arena.get(
        normalize_card_name(name.split(" // ")[0])
    )
    if rarity is None:
        rarity = card.get("rarity", "rare")
    return {
        "rarity": "rare" if rarity in ("special", "bonus") else rarity,
        "free": card.get("name") in BASIC_LAND_NAMES,
    }


# One pool per (bulk path, sidecar mtime) per process: the record list is already
# memoized by ``load_bulk_cards``; this memoizes the INDEXES over it, so a CLI that
# hydrates a deck and then searches shares one name index.
_POOLS: dict[tuple[str, float], CardPool] = {}


class CardPool:
    """The loaded bulk and every index over it. Construct via :meth:`load` (disk) or
    :meth:`from_cards` (in-memory; tests and the snapshot builder)."""

    __slots__ = (
        "_aliases",
        "_by_id",
        "_by_name",
        "_cards",
        "_object_resolver",
        "_path",
        "_printings",
        "_rarity",
        "_set_records",
        "_unreleased",
    )

    def __init__(self, cards: list[dict], *, path: Path | None) -> None:
        self._cards = cards
        self._path = path
        self._by_name: NameIndex | None = None
        self._by_id: dict[str, dict] | None = None
        self._rarity: dict[tuple[str, bool, str | None, int], NameIndex] = {}
        self._unreleased: frozenset[str] | None = None
        self._aliases: dict[str, str] | None = None
        self._printings: tuple[dict[str, list[dict]], dict[str, dict]] | None = None
        self._object_resolver: Callable[[str], dict | None] | None = None
        self._set_records: dict[str, list[dict]] = {}

    # --- constructors ----------------------------------------------------------

    @classmethod
    def resolve_path(cls, bulk_path: Path | None = None) -> Path:
        """The bulk file :meth:`load` would read: *bulk_path* itself, or (``None``)
        the auto-discovered MTGJSON bulk (``bulk_loader.default_bulk_path``). Raises
        :class:`NoBulkError` when there is neither — the one resolution rule, for a
        caller that needs the path without paying the load."""
        path = bulk_path if bulk_path is not None else default_bulk_path()
        if path is None or not Path(path).is_file():
            raise NoBulkError(bulk_path)
        return Path(path)

    @classmethod
    def load(cls, bulk_path: Path | None = None) -> CardPool:
        """The pool over *bulk_path* (:meth:`resolve_path`). Raises
        :class:`NoBulkError` when there is nothing to load. Memoized per process on
        (path, bulk version)."""
        path = cls.resolve_path(bulk_path)
        cards = load_bulk_cards(path)  # refreshes the sidecar first, so mtime is final
        key = (str(path), bulk_mtime(path))
        pool = _POOLS.get(key)
        if pool is None or pool.cards is not cards:
            pool = cls(cards, path=path)
            _POOLS[key] = pool
        return pool

    @classmethod
    def from_cards(cls, cards: list[dict], *, path: Path | None = None) -> CardPool:
        """A pool over an in-memory record list (no disk, no memo)."""
        return cls(cards, path=path)

    @staticmethod
    def clear_memo() -> None:
        """Drop the per-process pool memo (test hygiene)."""
        _POOLS.clear()

    # --- identity --------------------------------------------------------------

    @property
    def path(self) -> Path | None:
        """The bulk file this pool was loaded from (``None`` for an in-memory pool)."""
        return self._path

    @property
    def identity(self) -> str:
        """A cheap version token for derived caches: the bulk's ``mtime_ns:size``
        (``download-mtgjson`` rewrites the file on refresh, so it changes with the
        data) plus the translated sidecar's mtime (``bulk_loader.bulk_mtime`` — the
        records a pool serves come from the sidecar, which a ``SIDECAR_VERSION`` bump
        or a price-only refresh rebuilds with the source untouched), or ``memory`` for
        an in-memory pool."""
        if self._path is None:
            return "memory"
        try:
            stat = self._path.stat()
        except OSError:
            return "missing"
        return f"{stat.st_mtime_ns}:{stat.st_size}:{bulk_mtime(self._path)}"

    @property
    def cards(self) -> list[dict]:
        """Every bulk record, read-only and shared by reference."""
        return self._cards

    # --- indexes ---------------------------------------------------------------

    @property
    def by_name(self) -> NameIndex:
        """name -> the record a deck entry hydrates to (see the module docstring for
        the one policy). Alias-aware and NFKD-folded via ``NameIndex``."""
        if self._by_name is None:
            self._by_name = build_name_index(
                self._cards, reduce=_keep_best_printing, prefilter=is_game_card
            )
        return self._by_name

    @property
    def by_id(self) -> dict[str, dict]:
        """printing id -> record, EVERY printing including tokens (``all_parts``
        resolution for proxies needs the token records a name lookup must not see)."""
        if self._by_id is None:
            self._by_id = {c["id"]: c for c in self._cards if c.get("id")}
        return self._by_id

    def rarity_index(self, fmt: Format, *, arena_only: bool = False) -> NameIndex:
        """name -> ``{rarity, free}`` for Arena wildcard costing in *fmt*.

        A card's wildcard cost is its LOWEST rarity among printings legal in *fmt*
        (``Format.is_legal``, which carries Competitive Brawl's ban override, so an
        owned, legal staple is never reported as illegal). *arena_only* restricts to
        printings that exist on Arena, and lets the local Arena card database
        (``arena_card_db``) decide the rarity of every card it lists: the lowest
        rarity among the card's craftable (primary) printings, which MTGJSON cannot
        see. ``free`` marks the six basic lands Arena gives every player
        (Snow-Covered basics are collected, so they are not free). Memoized per
        (format, arena_only, card database).
        """
        db = find_card_db() if arena_only else None
        arena = primary_rarities(db) if db is not None else {}
        key = (fmt.name, arena_only, str(db) if db else None, len(arena))
        cached = self._rarity.get(key)
        if cached is not None:
            return cached

        def _legal(card: dict) -> bool:
            if card.get("layout") in SKIP_LAYOUTS or not fmt.is_legal(card):
                return False
            return not arena_only or "arena" in (card.get("games") or [])

        index = build_name_index(
            self._cards,
            reduce=_keep_lowest_rarity,
            value=lambda card: _rarity_value(card, arena),
            prefilter=_legal,
        )
        self._rarity[key] = index
        return index

    @property
    def unreleased_ids(self) -> frozenset[str]:
        """oracle_ids of spoiled-but-unreleased cards (``card_search.
        unreleased_oracle_ids``): the set ``Format.legality`` reads to report
        ``unreleased`` instead of ``not_legal``."""
        if self._unreleased is None:
            from mtg_utils.card_search import unreleased_ids_for, unreleased_oracle_ids

            self._unreleased = (
                unreleased_ids_for(self._path, self._cards)
                if self._path is not None
                else unreleased_oracle_ids(self._cards)
            )
        return self._unreleased

    @property
    def name_aliases(self) -> dict[str, str]:
        """normalized Arena alias (``printed_name`` / ``flavor_name``) -> normalized
        canonical name, for collection matching (``mark_owned``)."""
        if self._aliases is None:
            from mtg_utils.names import name_alias_map

            self._aliases = name_alias_map(self._cards)
        return self._aliases

    def set_records(self, code: str) -> list[dict]:
        """One record per distinct card in set ``code`` (game cards only, the lowest
        collector number per oracle) — what a set holds, for a limited scan of the
        threats and answers a pool's opponents draw from. Memoized per code."""
        key = code.lower()
        if key not in self._set_records:
            best: dict[str, dict] = {}
            for card in self._cards:
                if (card.get("set") or "").lower() != key or not is_game_card(card):
                    continue
                oracle_id = card.get("oracle_id") or card.get("name", "")
                if oracle_id not in best or _collector_key(card) < _collector_key(
                    best[oracle_id]
                ):
                    best[oracle_id] = card
            self._set_records[key] = sorted(
                best.values(), key=lambda c: (_collector_key(c), c.get("name", ""))
            )
        return self._set_records[key]

    @property
    def printings_by_oracle(self) -> dict[str, list[dict]]:
        """oracle_id -> every addable printing, newest set first (the printing
        picker)."""
        return self._printing_indexes()[0]

    @property
    def printing_by_id(self) -> dict[str, dict]:
        """printing id -> record, addable printings only (a chosen printing's
        image / price / set)."""
        return self._printing_indexes()[1]

    def _printing_indexes(self) -> tuple[dict[str, list[dict]], dict[str, dict]]:
        if self._printings is None:
            by_oracle: dict[str, list[dict]] = {}
            by_id: dict[str, dict] = {}
            for card in self._cards:
                if not is_game_card(card):
                    continue
                oracle_id, printing_id = card.get("oracle_id"), card.get("id")
                if not oracle_id or not printing_id:
                    continue
                by_oracle.setdefault(oracle_id, []).append(card)
                by_id[printing_id] = card
            for prints in by_oracle.values():
                prints.sort(key=lambda r: r.get("released_at") or "", reverse=True)
            self._printings = (by_oracle, by_id)
        return self._printings

    def resolve_object(self, name: str) -> dict | None:
        """A *folded object* (ADR-0025) by name: the Dungeon a commander ventures
        into, an Emblem-typed object it brings in (The Ring), or a meld result
        (Brisela). These are deliberately absent from ``by_name`` (you cannot add one
        to a deck); keyed by full name AND DFC front-face name."""
        if self._object_resolver is None:
            meld_results = {
                p.get("name")
                for c in self._cards
                for p in (c.get("all_parts") or [])
                if p.get("component") == "meld_result" and p.get("name")
            }
            objects: dict[str, dict] = {}
            for c in self._cards:
                tl = (c.get("type_line") or "").lower()
                name_ = c.get("name") or ""
                if not name_ or (
                    "dungeon" not in tl
                    and "emblem" not in tl
                    and name_ not in meld_results
                ):
                    continue
                objects.setdefault(name_, c)
                objects.setdefault(name_.split(" // ")[0], c)
            self._object_resolver = objects.get
        return self._object_resolver(name)
