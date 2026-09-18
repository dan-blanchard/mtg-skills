"""deck-forge session state: the canonical in-progress deck and its mutations.

A ``DeckSession`` owns the deck as ordered name→quantity maps per zone and emits the
canonical parsed-deck dict (``{format, commanders, cards, sideboard, companion,
pool}``) that the rest of ``mtg_utils`` already speaks. For a pool-bounded format
(sealed / draft) the sideboard is DERIVED — the pool less the main deck — so "the
sideboard is the unused pool" holds by construction and containment collapses to
"the deck is drawn from the pool". To analyse a session, join it to the
bulk index with ``HydratedDeck.from_session(session, by_name)`` (see
``mtg_utils.hydrated_deck``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from mtg_utils._deck_forge.agent_bridge import AgentBridge
from mtg_utils._deck_forge.collection import CollectionStore
from mtg_utils._deck_forge.discovery import DiscoveryCache
from mtg_utils._deck_forge.events import EventHub
from mtg_utils._deck_forge.persistence import BuildStore
from mtg_utils._name_index import NameIndex
from mtg_utils.formats import FORMATS, Format
from mtg_utils.hydrated_deck import ZONES


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
        self._zones: dict[str, dict[str, int]] = {z: {} for z in ZONES}
        # Chosen printing per (zone, card name) → Scryfall printing id. Sparse: a card
        # with no entry uses the default (cheapest) printing, so existing builds and the
        # no-bulk path are unaffected. All copies of a card share one printing.
        self._printings: dict[str, dict[str, str]] = {z: {} for z in ZONES}
        # Chosen finish ("foil" | "etched") per (zone, card name). Rides the pinned
        # printing: only a pinned card can carry a finish, and re-pinning without one
        # clears it (the plain nonfoil default).
        self._finishes: dict[str, dict[str, str]] = {z: {} for z in ZONES}

    @property
    def medium(self) -> str:
        """Effective medium — the Format resolves the raw override (commander is always
        paper, Competitive Brawl always digital, Brawl / Historic Brawl honour the
        override and default to digital). Drives the active Collection slot and the
        cost mode (wildcards vs USD)."""
        return FORMATS[self.format].resolve_medium(self._medium_override)

    @property
    def deck_size(self) -> int:
        """Effective deck size — the Format resolves the raw override under the
        effective medium (only paper Historic Brawl may choose 60 or 100; elsewhere the
        override lies dormant)."""
        return FORMATS[self.format].resolve_deck_size(
            self._deck_size_override, self.medium
        )

    @property
    def pool_bounded(self) -> bool:
        """A limited build: the sideboard is the pool less the main deck."""
        return FORMATS[self.format].pool_bounded

    def set_medium(self, medium: str) -> None:
        self._medium_override = medium

    def set_deck_size(self, deck_size: int) -> None:
        self._deck_size_override = deck_size

    @classmethod
    def from_deck_dict(cls, deck: dict) -> DeckSession:
        """Rebuild a session from a canonical parsed-deck dict (for resume/load). A
        pool-bounded deck's sideboard is derived, so its stored list is not loaded;
        a pool-bounded dict with no pool (a list parsed before the zone existed)
        pools its cards and sideboard."""
        session = cls(
            Format.for_deck(deck).name,
            medium=deck.get("medium"),
            deck_size=deck.get("deck_size"),
        )
        zones: tuple[str, ...] = ZONES
        if session.pool_bounded and deck.get("pool"):
            zones = tuple(z for z in ZONES if z != "sideboard")
        for zone in zones:
            for entry in deck.get(zone) or []:
                session.add(entry["name"], int(entry.get("quantity", 1)), zone=zone)
                if entry.get("printing_id"):
                    session.set_printing(
                        entry["name"],
                        entry["printing_id"],
                        zone=zone,
                        finish=entry.get("finish"),
                    )
        if session.pool_bounded and not deck.get("pool"):
            session.pool_everything()  # a dict from before the pool zone existed
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
            self._printings[zone].pop(name, None)  # last copy gone → drop its printing
            self._finishes[zone].pop(name, None)  # …and its finish rides along
            return 0
        bucket[name] = remaining
        return remaining

    def set_printing(
        self,
        name: str,
        printing_id: str | None,
        *,
        zone: str = "cards",
        finish: str | None = None,
    ) -> None:
        """Pin (or clear, with ``None``) the Scryfall printing for a card in a zone.
        Clearing reverts the card to the default (cheapest) printing. ``finish``
        ("foil" / "etched") rides the pin: pinning without one clears any stored
        finish (nonfoil default), and clearing the pin clears the finish too."""
        prints = self._printings.setdefault(zone, {})
        finishes = self._finishes.setdefault(zone, {})
        if printing_id:
            prints[name] = printing_id
            if finish:
                finishes[name] = finish
            else:
                finishes.pop(name, None)
        else:
            prints.pop(name, None)
            finishes.pop(name, None)

    def printing_of(self, name: str, *, zone: str = "cards") -> str | None:
        return self._printings.get(zone, {}).get(name)

    def finish_of(self, name: str, *, zone: str = "cards") -> str | None:
        return self._finishes.get(zone, {}).get(name)

    def pool_everything(self) -> None:
        """Make the build's cards its pool: every copy the main deck runs is in the
        pool (at least), the stored sideboard joins the pool and is cleared (it is
        derived from here on). What a build does entering a pool-bounded format,
        and what a pre-pool dict does on load."""
        pool = self._zones["pool"]
        for name, qty in self._zones["cards"].items():
            pool[name] = max(pool.get(name, 0), qty)
        for name, qty in self._zones["sideboard"].items():
            pool[name] = pool.get(name, 0) + qty
        self.replace_zone("sideboard", {})

    def derived_sideboard(self) -> dict[str, int]:
        """A pool-bounded build's sideboard: the pool less the main deck, in pool
        order (empty for any other format, whose sideboard is stored)."""
        if not self.pool_bounded:
            return {}
        cards = self._zones["cards"]
        return {
            n: q - cards.get(n, 0)
            for n, q in self._zones["pool"].items()
            if q - cards.get(n, 0) > 0
        }

    def _entries(self, quantities: Mapping[str, int], pins: str) -> list:
        """Entries for ``quantities`` with the printing / finish pinned under
        ``pins`` (the zone whose pins apply — the pool's, for the derived sideboard)."""
        prints = self._printings.get(pins, {})
        finishes = self._finishes.get(pins, {})
        return [
            {
                "name": n,
                "quantity": q,
                **({"printing_id": prints[n]} if n in prints else {}),
                **({"finish": finishes[n]} if n in finishes else {}),
            }
            for n, q in quantities.items()
        ]

    def to_deck_dict(self) -> dict:
        """Emit the canonical parsed-deck dict consumed across ``mtg_utils``. ``medium``
        and ``deck_size`` are the effective values (medium drives slot/cost; deck_size
        flows into mana_audit's land math and the footer target). A pool-bounded
        build's sideboard is derived (the pool less the main deck)."""
        zones = {zone: self._entries(self._zones[zone], zone) for zone in ZONES}
        if self.pool_bounded:
            zones["sideboard"] = self._entries(self.derived_sideboard(), "pool")
        return {
            "format": self.format,
            "medium": self.medium,
            "deck_size": self.deck_size,
            **zones,
        }

    def replace_zone(self, zone: str, quantities: Mapping[str, int]) -> None:
        """Set a zone's contents wholesale (a seeded build, a format switch),
        dropping the pins of any name that leaves it."""
        bucket = self._bucket(zone)
        bucket.clear()
        bucket.update({n: int(q) for n, q in quantities.items() if int(q) > 0})
        for pinned in (self._printings[zone], self._finishes[zone]):
            for name in list(pinned):
                if name not in bucket:
                    pinned.pop(name, None)

    def quantity_of(self, name: str, *, zone: str = "cards") -> int:
        """How many copies of ``name`` a zone holds (0 when absent) — the derived
        sideboard included, for a pool-bounded build."""
        if zone == "sideboard" and self.pool_bounded:
            return self.derived_sideboard().get(name, 0)
        return self._zones.get(zone, {}).get(name, 0)

    def zone_quantities(self, zone: str) -> dict[str, int]:
        """A zone's name → copies (a copy of the stored bucket)."""
        return dict(self._bucket(zone))

    def quantity_sum(self, zone: str) -> int:
        """The copies a zone holds in total."""
        return sum(self._bucket(zone).values())

    def card_names(self) -> list[str]:
        """Every distinct card name across all zones (for hydration lookups)."""
        seen: dict[str, None] = {}
        for zone in ZONES:
            for name in self._zones[zone]:
                seen.setdefault(name, None)
        return list(seen)

    def _bucket(self, zone: str) -> dict[str, int]:
        if zone not in self._zones:
            msg = f"unknown zone {zone!r}; expected one of {ZONES}"
            raise ValueError(msg)
        return self._zones[zone]


@dataclass
class ForgeState:
    """Everything one running backend hub owns, injectable for tests.

    ``by_name`` maps card name → full Scryfall record (hydration + add-time
    validation + display enrichment). ``search_fn`` is the deterministic search
    seam (production wraps ``card_search.search_cards``; tests inject a fake).
    ``bulk_available`` is False when no Scryfall bulk data is on disk, so the
    search endpoint can fail loudly with a "run download-mtgjson" message instead of
    silently returning nothing.
    """

    by_name: Mapping[str, dict]
    search_fn: Callable[..., list[dict]]
    session: DeckSession
    hub: EventHub = field(default_factory=EventHub)
    bulk_available: bool = True
    # oracle_ids of spoiled-but-unreleased cards (card_search.unreleased_oracle_ids).
    # Derived from the bulk at startup, never persisted. Two readers: the Find surface
    # opts into them via SearchPayload.include_unreleased, and the views layer badges
    # them as pre-release. Empty without bulk, which correctly disables both.
    unreleased_ids: frozenset[str] = frozenset()
    combos_fn: Callable[[dict], dict] | None = None
    bridge: AgentBridge = field(default_factory=AgentBridge)
    store: BuildStore | None = None
    build_id: str = "default"
    build_name: str = "Untitled"
    agent_avenues: list[dict] = field(default_factory=list)
    # Monotonic id counter for agent avenues. Never reset, never derived from
    # len(agent_avenues): a length-based id reuses a live id after a delete
    # (add 1,2,3 -> delete 2 -> add yields 3 again), which silently makes
    # remove/focus hit the wrong lane.
    agent_avenue_seq: int = 0
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
    # Per-slot printing-level ownership detail (``collection.printing_index``):
    # slot → normalized name key → {(set, collector_number): (nonfoil, foil)}.
    # Sparse by design — a name absent from its slot's index has NAME-ONLY ownership
    # (old collection.json files / plain pastes), which the wire surfaces as the
    # tri-state ``owned_printing`` being absent. Rebuilt alongside collection_index.
    collection_printings: dict[
        str, dict[str, dict[tuple[str, str], tuple[int, int]]]
    ] = field(default_factory=dict)
    # normalized-alias → canonical map (Arena printed_name / flavor_name), built from
    # bulk once at launch. Threaded into every ``mark_owned.owned_lookup`` so the Arena
    # slot's ownership matches flavor/printed names — the ADR-0018 Arena-alias promise.
    name_aliases: dict[str, str] = field(default_factory=dict)
    # Arena wildcard costing for digital builds: the bulk path + a lazily-built, cached
    # Arena rarity index per FORMAT (``CardPool.rarity_index`` walks all of bulk, so
    # it's computed once per format and reused; keyed by format, not legality key, as
    # competitive_brawl shares historic_brawl's key with a different ban policy).
    bulk_path: Path | None = None
    rarity_index: dict[str, NameIndex] = field(default_factory=dict)
    # Commander discovery's memoized sweeps (lane density, per-collection served-name
    # sets, the Novelty signal-rarity table) — shared across the threadpool and the
    # post-import background warm, so it owns its own lock. See ``discovery``.
    discovery: DiscoveryCache = field(default_factory=DiscoveryCache)
    # Printing selection (picking a set/art for a card). ``printings_by_oracle`` maps a
    # card's oracle_id → every legal printing's record (for the picker list);
    # ``printing_by_id`` maps a Scryfall printing id → its record (to resolve a chosen
    # printing's image/price/set on the deck view + export). Both empty without bulk.
    printings_by_oracle: dict[str, list[dict]] = field(default_factory=dict)
    printing_by_id: dict[str, dict] = field(default_factory=dict)
    # ``set-scan`` readouts memoized per set code (a whole-bulk walk each).
    set_scans: dict[str, dict] = field(default_factory=dict)
    # Resolves a folded object's name → its card (ADR-0025): a commander's ventured
    # dungeon, whose oracle is appended to the commander's before signal extraction.
    # Dungeons are excluded from `by_name` (unaddable), so this is a separate raw-bulk
    # lookup, built once at launch. None when no bulk → no folding (graceful).
    object_resolver: Callable[[str], dict | None] | None = None

    @property
    def active_slot(self) -> str:
        """The Collection slot read for this build: ``paper`` for a paper build,
        ``arena`` for a digital one. Keyed off medium, not format — so a paper Historic
        Brawl reads the paper slot. Reads are strictly single-slot."""
        return "paper" if self.session.medium == "paper" else "arena"
