"""deck-forge session state: the canonical in-progress deck and its mutations.

A ``DeckSession`` owns the deck as ordered name→quantity maps per zone and emits the
canonical parsed-deck dict (``{format, commanders, cards, sideboard}``) that the
rest of ``mtg_utils`` already speaks. To analyse a session, join it to the bulk index
with ``HydratedDeck.from_session(session, by_name)`` (see ``mtg_utils.hydrated_deck``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from mtg_utils._deck_forge.agent_bridge import AgentBridge
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.persistence import BuildStore

_ZONES = ("commanders", "cards", "sideboard")


class DeckSession:
    """The in-progress deck for one build session."""

    def __init__(self, fmt: str) -> None:
        self.format = fmt
        self._zones: dict[str, dict[str, int]] = {z: {} for z in _ZONES}

    @classmethod
    def from_deck_dict(cls, deck: dict) -> DeckSession:
        """Rebuild a session from a canonical parsed-deck dict (for resume/load)."""
        session = cls(deck.get("format", "commander"))
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
        """Emit the canonical parsed-deck dict consumed across ``mtg_utils``."""
        return {
            "format": self.format,
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
