"""deck-forge session state: the canonical in-progress deck and its mutations.

A ``DeckSession`` owns the deck as ordered name→quantity maps per zone and emits the
canonical parsed-deck dict (``{format, commanders, cards, sideboard}``) that the
rest of ``mtg_utils`` already speaks. To analyse a session, join it to the bulk index
with ``HydratedDeck.from_session(session, by_name)`` (see ``mtg_utils.hydrated_deck``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mtg_utils._deck_forge.agent_bridge import AgentBridge
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils.format_config import FORMAT_CONFIGS

_ZONES = ("commanders", "cards", "sideboard")
# Brawl/Historic Brawl can be played digital (Arena) or paper; commander is paper-only.
# Medium drives the active Collection slot and the cost mode (wildcards vs USD).
_ARENA_FORMATS = ("brawl", "historic_brawl")


def _default_medium(fmt: str) -> str:
    return "digital" if fmt in _ARENA_FORMATS else "paper"


def _size_choosable(fmt: str, medium: str) -> bool:
    """Only paper Historic Brawl (a.k.a. paper "Brawl") may be 60 OR 100 cards; every
    other (format, medium) has a fixed size."""
    return fmt == "historic_brawl" and medium == "paper"


class DeckSession:
    """The in-progress deck for one build session."""

    def __init__(
        self, fmt: str, *, medium: str | None = None, deck_size: int | None = None
    ) -> None:
        self.format = fmt
        # Overrides, applied through guarded properties: commander forces paper, and a
        # deck-size override only takes effect for paper Historic Brawl. Kept as raw
        # overrides (not reset on format change) so a preference survives toggling away
        # and back; the properties re-derive the effective value live.
        self._medium_override = medium
        self._deck_size_override = deck_size
        self._zones: dict[str, dict[str, int]] = {z: {} for z in _ZONES}

    @property
    def medium(self) -> str:
        """Effective medium: commander is always paper; Brawl/Historic Brawl honor the
        override, defaulting to digital (Arena is the common case for those)."""
        if self.format not in _ARENA_FORMATS:
            return "paper"
        return self._medium_override or _default_medium(self.format)

    @property
    def deck_size(self) -> int:
        """Effective deck size: the format default, except paper Historic Brawl may
        override to 60 or 100 (both are legal for paper "Brawl")."""
        default = FORMAT_CONFIGS.get(self.format, {}).get("deck_size", 100)
        if _size_choosable(self.format, self.medium) and self._deck_size_override in (
            60,
            100,
        ):
            return self._deck_size_override
        return default

    def set_medium(self, medium: str) -> None:
        self._medium_override = medium

    def set_deck_size(self, deck_size: int) -> None:
        self._deck_size_override = deck_size

    @classmethod
    def from_deck_dict(cls, deck: dict) -> DeckSession:
        """Rebuild a session from a canonical parsed-deck dict (for resume/load)."""
        session = cls(
            deck.get("format", "commander"),
            medium=deck.get("medium"),
            deck_size=deck.get("deck_size"),
        )
        for zone in _ZONES:
            for entry in deck.get(zone) or []:
                session.add(entry["name"], int(entry.get("quantity", 1)), zone=zone)
        return session

    def add(self, name: str, qty: int = 1, *, zone: str = "cards") -> int:
        """Add ``qty`` copies of ``name`` to a zone; merges with any existing copies.

        Returns the new quantity for that card in the zone.
        """
        bucket = self._bucket(zone)
        bucket[name] = bucket.get(name, 0) + qty
        return bucket[name]

    def remove(self, name: str, qty: int = 1, *, zone: str = "cards") -> int:
        """Remove ``qty`` copies; drops the entry at zero. No-op for unknown cards.

        Returns the remaining quantity (0 if absent or fully removed).
        """
        bucket = self._bucket(zone)
        if name not in bucket:
            return 0
        remaining = bucket[name] - qty
        if remaining <= 0:
            del bucket[name]
            return 0
        bucket[name] = remaining
        return remaining

    def to_deck_dict(self) -> dict:
        """Emit the canonical parsed-deck dict consumed across ``mtg_utils``. ``medium``
        and ``deck_size`` are the effective values (medium drives slot/cost; deck_size
        flows into mana_audit's land math and the footer target)."""
        return {
            "format": self.format,
            "medium": self.medium,
            "deck_size": self.deck_size,
            **{
                zone: [{"name": n, "quantity": q} for n, q in self._zones[zone].items()]
                for zone in _ZONES
            },
        }

    def card_names(self) -> list[str]:
        """Every distinct card name across all zones (for hydration lookups)."""
        seen: dict[str, None] = {}
        for zone in _ZONES:
            for name in self._zones[zone]:
                seen.setdefault(name, None)
        return list(seen)

    def _bucket(self, zone: str) -> dict[str, int]:
        if zone not in self._zones:
            msg = f"unknown zone {zone!r}; expected one of {_ZONES}"
            raise ValueError(msg)
        return self._zones[zone]


@dataclass
class ForgeState:
    """Everything one running backend hub owns, injectable for tests.

    ``by_name`` maps card name → full Scryfall record (hydration + add-time
    validation + display enrichment). ``search_fn`` is the deterministic search
    seam (production wraps ``card_search.search_cards``; tests inject a fake).
    ``bulk_available`` is False when no Scryfall bulk data is on disk, so the
    search endpoint can fail loudly with a "run download-bulk" message instead of
    silently returning nothing.
    """

    by_name: dict[str, dict]
    search_fn: Callable[..., list[dict]]
    session: DeckSession
    hub: EventHub = field(default_factory=EventHub)
    bulk_available: bool = True
    combos_fn: Callable[[dict], dict] | None = None
    bridge: AgentBridge = field(default_factory=AgentBridge)
    store: BuildStore | None = None
    build_id: str = "default"
    build_name: str = "Untitled"
    agent_avenues: list[dict] = field(default_factory=list)
    # Avenue ids the human has pinned as lanes they're actually building toward (#2).
    # When non-empty, the candidate synergy score counts only these focused lanes
    # (see engine.scoring_basis). Runtime state, like agent_avenues — not persisted yet.
    focused_avenue_ids: set[str] = field(default_factory=set)
    # The global Collection (ADR-0018): owned cards in two format-keyed slots
    # ("paper" / "arena"), shared across builds and persisted on its own.
    # ``collections`` holds the raw piles (for counts + persistence);
    # ``collection_index`` caches each slot's precomputed (entries, alias_lookup) from
    # ``mark_owned.owned_lookup`` so a per-snapshot ownership check is O(deck size).
    # Ownership is DERIVED, never stored.
    collection_store: CollectionStore | None = None
    collections: dict[str, dict] = field(default_factory=dict)
    collection_index: dict[str, tuple] = field(default_factory=dict)
    # normalized-alias → canonical map (Arena printed_name / flavor_name), built from
    # bulk once at launch. Threaded into every ``mark_owned.owned_lookup`` so the Arena
    # slot's ownership matches flavor/printed names — the ADR-0018 Arena-alias promise.
    name_aliases: dict[str, str] = field(default_factory=dict)
    # Arena wildcard costing for digital builds: the bulk path + a lazily-built, cached
    # Arena rarity index per legality_key (``build_rarity_index`` walks all of bulk, so
    # it's computed once per format and reused).
    bulk_path: Path | None = None
    rarity_index: dict[str, dict] = field(default_factory=dict)
    # Lazily-built novelty support: per-format signal-rarity table over the whole legal
    # commander pool (fmt -> (freq, total)). Cached because the sweep over every
    # commander-eligible bulk card is the one expensive part of Commander discovery.
    commander_signal_freq: dict = field(default_factory=dict)
