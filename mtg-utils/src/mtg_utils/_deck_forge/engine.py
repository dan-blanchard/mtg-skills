"""The deck-forge engine: deck analysis over a ``ForgeState``, behind its own seam.

These were private functions inside ``app.py``, reachable only through the HTTP routes
(``TestClient(build_app(state)).get("/api/snapshot")``). Pulled out as free functions
over ``ForgeState``, they become the direct test surface — the interface IS the test
surface — and let ``app.py`` shrink to a transport adapter.

Free functions, deliberately NOT a ``DeckEngine`` class: ``ForgeState.session`` is
mutable and every mutation route edits it in place, so a class that cached a
``HydratedDeck`` at construction would desync on the next add/remove. A free function
reads ``state`` at call time and can never go stale.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from mtg_utils import mark_owned, price_check, theme_presets
from mtg_utils._deck_forge import collection, staples, views
from mtg_utils._deck_forge._ir_lookup import ir_for
from mtg_utils._deck_forge.budgets import role_of, slot_budgets
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import (
    Serve,
    payoff_search,
    payoff_serve,
    source_label,
    source_split,
    spec_for,
)
from mtg_utils._deck_forge.signals import (
    Signal,
    extract_signals_hybrid,
    rank_deck_signals,
)
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils._name_index import NameIndex
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import is_basic_land, is_commander, valid_partner_search
from mtg_utils.deck_stats import deck_stats, detect_bracket
from mtg_utils.format_config import FORMAT_CONFIGS
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.legality_audit import legality_audit
from mtg_utils.mana_audit import mana_audit
from mtg_utils.scryfall_lookup import build_rarity_index

_DECK_SIZE = {"commander": 100, "historic_brawl": 100, "brawl": 60}
SUPPORTED_FORMATS = frozenset(_DECK_SIZE)
_PAPER_FORMATS = {"commander"}
# deck_minimum is intentionally excluded: a deck-in-progress is always below the size
# minimum, so it's the normal building state, not a warning.
_AUDIT_CATEGORIES = (
    "format_legality",
    "commander_zone",
    "color_identity",
    "copy_limits",
    "sideboard_size",
)
# Low-land defensibility heuristic (D8): a low avg CMC backed by cheap card advantage.
_DEFENSIBLE_AVG_CMC = 2.3
_DEFENSIBLE_CHEAP_CA = 8
# Engine avenues are capped so the panel reads as "what the deck cares about" (its
# dominant themes), not an exhaustive every-card dump.
_AVENUE_CAP = 12
# Only these card_search kwargs may come from an avenue's stored search spec.
_EXPLORE_KEYS = (
    "oracle",
    "card_type",
    "name",
    "cmc_min",
    "cmc_max",
    "price_min",
    "price_max",
)
# The ranked-candidate pool the Find surface ranks over; the route windows the caller's
# page size into it, so this bounds how deep "Show more" can page on one request.
_FIND_POOL = 96


def _signals(record: dict, *, include_membership: bool = True) -> list[Signal]:
    """Hybrid signal extraction with the card's IR wired by oracle_id (ADR-0027)."""
    return extract_signals_hybrid(
        record, ir_for(record), include_membership=include_membership
    )


def avenue_with_serve(avenue: dict, serve: Serve | None) -> dict:
    """Attach an avenue's structured ``serve`` classifier (type/keyword/oracle) so
    ranking credits candidates by the SAME precise predicate the spec serves on —
    but ONLY when it carries a structured dimension (types/keywords) the bare
    ``search`` fragment can't express (e.g. Spellslinger's Instant/Sorcery type gate).
    Oracle-only serves are left to the legacy search-AND classification, so no
    oracle-only avenue's behavior shifts."""
    if serve is not None and serve.is_structured():
        avenue["serve"] = serve.as_dict()
    return avenue


def hydrate(state: ForgeState) -> HydratedDeck:
    """One HydratedDeck per request, joining the live session against the bulk index.
    Build it once at a handler's entry and thread it — every deck analysis reads it."""
    return HydratedDeck.from_session(state.session, state.by_name)


def deck_size(fmt: str) -> int:
    return _DECK_SIZE.get(fmt, 100)


def paper_only(fmt: str | None) -> bool:
    return fmt in _PAPER_FORMATS


def deck_color_identity(state: ForgeState) -> str:
    """Union of the commanders' color identities (the deck's color identity)."""
    colors: set[str] = set()
    for entry in state.session.to_deck_dict()["commanders"]:
        record = state.by_name.get(entry["name"])
        if record:
            colors.update(record.get("color_identity", []))
    return "".join(sorted(colors))


def is_paper(state: ForgeState) -> bool:
    """Whether this build is paper (vs digital/Arena). Drives the Collection slot and
    the cost mode (USD vs wildcards). Commander is always paper; Brawl / Historic Brawl
    follow the chosen medium (ADR-0018, amended: medium not format decides the slot)."""
    return state.session.medium == "paper"


def active_slot(state: ForgeState) -> str:
    """The Collection slot read for this build: ``paper`` for a paper build, ``arena``
    for a digital one. Keyed off medium, not format — so a paper Historic Brawl reads
    the paper slot. Reads are strictly single-slot."""
    return "paper" if is_paper(state) else "arena"


def _is_basic(record: dict | None) -> bool:
    return record is not None and is_basic_land(record)


def owned_quantities(state: ForgeState) -> dict[str, int]:
    """Owned-copy map (deck card name → count) against the ACTIVE Collection slot only —
    empty when that slot holds no imported Collection. Basic lands are excluded: owning
    basics is assumed, so they never read as an un-owned 'miss' nor clutter the
    readout. DERIVED fresh each call from the cached per-slot lookup; never stored."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return {}
    entries, lookup = idx
    out: dict[str, int] = {}
    for name in state.session.card_names():
        if _is_basic(state.by_name.get(name)):
            continue
        qty = mark_owned.owned_quantity(name, entries, lookup)
        if qty is not None:
            out[name] = qty
    return out


def owned_collection(state: ForgeState) -> dict[str, int]:
    """EVERY owned card in the active Collection slot (name -> copies), basics excluded.

    Distinct from :func:`owned_quantities`, which is deck-scoped (the "X of Y owned"
    readout). The tuner judges *candidate* adds — cards NOT yet in the deck — so a
    deck-scoped map makes every candidate read as un-owned: at a zero wildcard budget
    nothing would be affordable (no owned-card fills), and owned-but-not-in-deck cards
    would wrongly burn budget. This whole-slot map lets the tuner treat any owned
    candidate as free. Keyed by the collection's own names (canonical for Untapped/Arena
    and Moxfield exports), which match the canonical names ``card_search`` returns."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return {}
    entries, _lookup = idx
    return {
        name: qty
        for name, qty in entries.values()
        if qty >= 1 and not _is_basic(state.by_name.get(name))
    }


def owned_of(state: ForgeState, name: str) -> int | None:
    """Owned copies of an arbitrary card name in the active Collection slot, or None.
    Unlike :func:`owned_quantities` (deck-scoped) this answers for any card — so Find
    can flag whether a *candidate* is already on your shelf (the 'Owned only' facet)."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return None
    entries, lookup = idx
    return mark_owned.owned_quantity(name, entries, lookup)


def set_collection(state: ForgeState, slot: str, pile: dict) -> None:
    """Load a parsed Collection ``pile`` into ``slot``: cache its precomputed ownership
    lookup (so snapshots stay O(deck size)) and persist. The single mutation point for a
    Collection slot."""
    pile = collection.owned_only(pile)  # drop quantity-0 (un-owned/wishlist) rows
    state.collections[slot] = pile
    state.collection_index[slot] = mark_owned.owned_lookup(
        pile, name_aliases=state.name_aliases or None
    )
    state.lane_collection_serves.pop(slot, None)  # stale: the slot's cards changed
    if state.collection_store is not None:
        state.collection_store.save(state.collections)


def clear_collection(state: ForgeState, slot: str) -> None:
    """Drop a Collection slot (and its cached lookup), then persist."""
    state.collections.pop(slot, None)
    state.collection_index.pop(slot, None)
    state.lane_collection_serves.pop(slot, None)  # stale: the slot's cards are gone
    if state.collection_store is not None:
        state.collection_store.save(state.collections)


def collection_summary(state: ForgeState, owned: dict[str, int]) -> dict:
    """The Collection readout the SPA renders: which slot is active, each slot's size,
    and the deck's owned count vs its non-basic distinct total (the 'N of M owned')."""
    deck_total = sum(
        1 for n in state.session.card_names() if not _is_basic(state.by_name.get(n))
    )
    return {
        "active_slot": active_slot(state),
        "slots": collection.slot_sizes(state.collections),
        "owned": len(owned),
        "deck_total": deck_total,
    }


def _rarity_index(state: ForgeState) -> NameIndex | None:
    """The Arena rarity index for the current format's legality key, built once from
    bulk and cached on the state (``build_rarity_index`` walks all of bulk)."""
    if state.bulk_path is None:
        return None
    key = _legality_key(state.session.format)
    cached = state.rarity_index.get(key)
    if cached is None:
        cached = build_rarity_index(state.bulk_path, key, arena_only=True)
        state.rarity_index[key] = cached
    return cached


def wildcard_cost(state: ForgeState) -> dict | None:
    """Arena wildcard cost for a DIGITAL build — ``{mythic, rare, uncommon, common}``
    needed for cards NOT already owned in the active (arena) Collection slot, reusing
    ``price_check``'s Arena costing (4-cap-exemption aware). ``None`` for paper builds
    (USD cost) or with no bulk. Basic lands are stripped — Arena never charges wildcards
    for them."""
    if is_paper(state) or state.bulk_path is None:
        return None
    rarity_index = _rarity_index(state)
    if not rarity_index:
        return None
    deck = state.session.to_deck_dict()
    no_basics = dict(deck)
    for zone in ("commanders", "cards", "sideboard"):
        if zone in deck:
            no_basics[zone] = [
                e
                for e in (deck.get(zone) or [])
                if not _is_basic(state.by_name.get(e["name"]))
            ]
    owned = owned_quantities(state)  # deck cards owned in the active slot (basics-free)
    owned_cards = [{"name": n, "quantity": q} for n, q in owned.items()]
    result = price_check.arena_wildcard_cost(
        no_basics, rarity_index, owned_cards=owned_cards
    )
    return result["wildcard_cost"]


# Commander discovery (ADR-0018). "Best" is intent-driven, never EDHREC popularity:
# Support depth (how much of a commander's strategy your collection already fills) or
# Novelty (signal rarity), each over the active Collection slot.
_DISCOVER_SORTS = ("support", "novelty")
_SUPPORT_FLOOR = 5  # owned in-identity cards a lane needs to count as supported


def _resolve_record(state: ForgeState, name: str) -> dict | None:
    """A collection card name → its bulk record via the case- and diacritic-folding
    name index (``NameIndex.get``; an empty dict in the no-bulk path)."""
    return state.by_name.get(name)


def _resolved_collection(state: ForgeState, slot: str | None = None) -> list[dict]:
    """Every collection card in ``slot`` (default: the active slot) resolved to a bulk
    record (un-resolvable names dropped — no data, no reasoning). The explicit ``slot``
    lets background warming target a just-imported slot that isn't the active one."""
    pile = state.collections.get(slot or active_slot(state)) or {}
    out: dict[str, dict] = {}
    for section in ("commanders", "cards", "sideboard"):
        for entry in pile.get(section) or []:
            name = entry.get("name")
            if not name:
                continue
            rec = _resolve_record(state, name)
            if rec is not None and rec["name"] not in out:
                out[rec["name"]] = rec
    return list(out.values())


def owned_commander_records(state: ForgeState) -> list[dict]:
    """Bulk records for the commander-eligible cards in the active Collection slot."""
    fmt = state.session.format
    return [r for r in _resolved_collection(state) if is_commander(r, fmt)["eligible"]]


def _commander_lanes(record: dict) -> list[tuple[str, Serve, str]]:
    """The commander's text-opened lanes as ``(label, serve, key)`` triples, deduped by
    label. The generic Staples lane is NOT a signal spec, so it's naturally excluded —
    owning good-stuff isn't commander-specific support (Q9).

    ``include_membership=False`` (Q9 amended): a lane the commander opens only from what
    it *is* (a vanilla artifact legend → "artifacts matter"; a Goblin that says nothing
    about Goblins → "Goblin tribal") is NOT stated support — it's the broad "lists every
    artifact" lane the user flagged. We count only lanes the commander's TEXT opens, so
    a real artifacts-matter / tribal commander keeps its lane while a coincidental
    member doesn't inflate its support."""
    out: list[tuple[str, Serve, str]] = []
    seen: set[str] = set()
    for sig in _signals(record, include_membership=False):
        spec = spec_for(sig)
        if spec is None or spec.label in seen:
            continue
        seen.add(spec.label)
        out.append((spec.label, spec.serve, f"{sig.key}:{sig.subject}"))
    return out


def _density_pool(state: ForgeState) -> list[dict]:
    """The deduped bulk-record pool used as the lane-density denominator, cached on the
    state (``by_name`` folds every face/alias, so dedup by canonical name)."""
    if not state.density_pool:
        seen: set[str] = set()
        pool: list[dict] = []
        for rec in state.by_name.values():
            name = rec.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            pool.append(rec)
        state.density_pool = pool
    return state.density_pool


def _lane_density(state: ForgeState, key: str, serve: Serve) -> float:
    """Fraction of the whole legal pool that serves a lane, cached per lane-key. A broad
    lane (artifacts ~0.1) yields a low ``-log(p)`` weight; a distinctive one (a niche
    tribe ~0.002) a high one — so collection DEPTH in a rare lane outweighs raw breadth.
    Floored at one hit so a lane that exists always carries some weight."""
    cached = state.lane_density.get(key)
    if cached is not None:
        return cached
    pool = _density_pool(state)
    total = len(pool) or 1
    hits = sum(1 for c in pool if serve.matches(c))
    p = max(hits, 1) / total
    state.lane_density[key] = p
    return p


_DENSITY_SIDECAR_PREFIX = "deck-forge-lane-density"


def _density_sidecar_path(state: ForgeState) -> Path | None:
    """On-disk path for the lane-density cache, keyed by the BULK file's fingerprint
    (mtime+size via ``sha_keyed_path``). A ``download-bulk`` refresh changes the key, so
    a stale sidecar is transparently ignored, not served. ``None`` without bulk."""
    if state.bulk_path is None:
        return None
    return sha_keyed_path(_DENSITY_SIDECAR_PREFIX, state.bulk_path)


def _load_lane_density(state: ForgeState) -> None:
    """Seed ``lane_density`` from its sidecar, ONCE per state. The ~55s first-discovery
    density sweep (every lane scanned over the 34k-card pool) is thus paid once per bulk
    version, not once per server start. A missing/unreadable/changed-bulk sidecar is a
    silent no-op (the sweep just recomputes and re-saves)."""
    if state.density_sidecar_loaded:
        return
    state.density_sidecar_loaded = True
    path = _density_sidecar_path(state)
    if path is None or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (int, float)):
                state.lane_density.setdefault(k, float(v))


def _save_lane_density(state: ForgeState) -> None:
    """Persist the accumulated lane-density cache to its bulk-keyed sidecar (atomic
    write, so concurrent discovery threads never see a half-written file)."""
    path = _density_sidecar_path(state)
    if path is not None:
        atomic_write_json(path, dict(state.lane_density))


_SERVED_SIDECAR_PREFIX = "deck-forge-served"


def _served_sidecar_path(state: ForgeState, coll: list[dict]) -> Path | None:
    """Sidecar path for a collection's per-lane served-name sets, content-addressed by
    the bulk fingerprint AND the collection's exact owned-name set. Each distinct
    collection thus gets its own cache (so multiple collections each stay warm), and a
    changed collection or bulk starts fresh (different key). ``None`` without bulk."""
    if state.bulk_path is None:
        return None
    names = sorted(c.get("name", "") for c in coll)
    return sha_keyed_path(_SERVED_SIDECAR_PREFIX, state.bulk_path, names)


def _load_collection_serves(state: ForgeState, slot: str, coll: list[dict]) -> None:
    """Seed ``slot``'s per-lane served-name cache from its content-addressed sidecar,
    ONCE per (process, slot) — saving the ~10s collection scan on restart / switch.
    In-memory presence is the 'loaded' flag; set/clear_collection clears it so a changed
    collection re-seeds from ITS sidecar."""
    if slot in state.lane_collection_serves:
        return
    cache: dict[str, frozenset[str]] = {}
    state.lane_collection_serves[slot] = cache
    path = _served_sidecar_path(state, coll)
    if path is None or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, dict):
        for k, names in data.items():
            if isinstance(names, list):
                cache[str(k)] = frozenset(str(n) for n in names)


def _save_collection_serves(state: ForgeState, slot: str, coll: list[dict]) -> None:
    """Persist ``slot``'s served-name sets to its content-addressed sidecar."""
    path = _served_sidecar_path(state, coll)
    if path is None:
        return
    cache = state.lane_collection_serves.get(slot) or {}
    atomic_write_json(path, {k: sorted(v) for k, v in cache.items()})


def warm_discovery_caches(state: ForgeState, slot: str) -> None:
    """Compute + persist BOTH discovery caches (bulk-keyed lane density, and ``slot``'s
    content-addressed served-name sets) WITHOUT ranking, so the next discover is fast.
    Run in the background right after a collection import (see app.py), so the ~65s cold
    cost is never paid at discover time. Heavy CPU — call off the event loop. A pure
    read of state besides the caches it fills (idempotent)."""
    coll = _resolved_collection(state, slot)
    if not coll:
        return
    fmt = state.session.format
    _load_lane_density(state)
    _load_collection_serves(state, slot, coll)
    density_before = len(state.lane_density)
    served_before = len(state.lane_collection_serves.get(slot) or {})
    for rec in coll:
        if not is_commander(rec, fmt)["eligible"]:
            continue
        for _label, serve, key in _commander_lanes(rec):
            _lane_density(state, key, serve)
            _slot_lane_serves(state, slot, key, serve, coll)
    if len(state.lane_density) > density_before:
        _save_lane_density(state)
    if len(state.lane_collection_serves.get(slot) or {}) > served_before:
        _save_collection_serves(state, slot, coll)


def _slot_lane_serves(
    state: ForgeState, slot: str, key: str, serve: Serve, coll: list[dict]
) -> frozenset[str]:
    """Owned card NAMES (in ``slot``'s collection) that serve a lane, cached per
    (slot, key). Scanned ONCE per distinct lane, so support is a set intersection,
    not a per-commander regex scan (the ~30s discovery hot path). Invalidated when
    the slot's collection changes (``set_collection`` / ``clear_collection``)."""
    cache = state.lane_collection_serves.setdefault(slot, {})
    hit = cache.get(key)
    if hit is not None:
        return hit
    names = frozenset(c["name"] for c in coll if serve.matches(c))
    cache[key] = names
    return names


def _support_depth(
    state: ForgeState,
    record: dict,
    in_names: set[str],
    slot: str,
    coll: list[dict],
) -> tuple[float, list, int]:
    """Format-relative owned support (ADR-0018 / Q9 amended): sum over the
    commander's text-opened lanes of ``own(L) * -log(p_L)``, where ``own(L)`` =
    in-identity owned cards serving lane L and ``p_L`` = that lane's serve density in
    the legal pool. The old within-collection IDF peaked at mid-breadth, so a
    merely-broad lane (artifacts) always won; the pool-relative weight instead makes a
    distinctive lane you own deeply outrank a broad one (reflects the collection, not
    lane width).

    ``own(L)`` counts the lane's served-names also in ``in_names`` (a set intersection
    over the cached served-name set), so no regex runs per commander: the scan is once
    per distinct lane. Returns ``(score, breakdown, # supported)``."""
    if not in_names:
        return 0.0, [], 0
    score = 0.0
    breakdown: list[dict] = []
    supported = 0
    for label, serve, key in _commander_lanes(record):
        k = len(_slot_lane_serves(state, slot, key, serve, coll) & in_names)
        if k == 0:
            continue
        score += k * -math.log(_lane_density(state, key, serve))
        breakdown.append({"label": label, "owned": k})
        if k >= _SUPPORT_FLOOR:
            supported += 1
    breakdown.sort(key=lambda b: -b["owned"])
    return score, breakdown, supported


def _signal_freq(state: ForgeState) -> tuple[dict, int]:
    """Per-format signal-rarity table over the whole legal commander pool, cached on the
    state (the one expensive sweep in discovery). Maps ``(key, subject)`` → occurrences,
    plus the commander count, for the Novelty IDF."""
    fmt = state.session.format
    cached = state.commander_signal_freq.get(fmt)
    if cached is not None:
        return cached
    freq: dict[tuple[str, str], int] = {}
    total = 0
    # by_name folds and indexes every face/alias, so the same record appears under
    # several keys — dedup by canonical name so each commander is counted once.
    seen: set[str] = set()
    for rec in state.by_name.values():
        name = rec.get("name", "")
        if name in seen:
            continue
        seen.add(name)
        if not is_commander(rec, fmt)["eligible"]:
            continue
        total += 1
        for key in {(s.key, s.subject) for s in _signals(rec)}:
            freq[key] = freq.get(key, 0) + 1
    state.commander_signal_freq[fmt] = (freq, total)
    return freq, total


def _novelty(record: dict, freq: dict, total: int) -> float:
    """Signal rarity: summed inverse-frequency of the commander's signals over the pool,
    so an off-beat hook outranks tokens / counters / ramp. Blind by design to commanders
    whose ability fires no detector (they score 0) — the accepted limit of signal-based
    novelty."""
    keys = {(s.key, s.subject) for s in _signals(record, include_membership=True)}
    return sum(math.log((total + 1) / freq.get(key, 1)) for key in keys)


def discover_commanders(
    state: ForgeState,
    *,
    sort: str = "support",
    colors: str | None = None,
    theme: str | None = None,
    limit: int = 24,
) -> list[dict]:
    """Intent-ranked owned commanders from the active Collection slot (ADR-0018).

    ``support`` (default) ranks by breadth-down-weighted owned support; ``novelty``
    ranks by signal rarity, HARD-GATED to commanders you own some support for.
    ``colors`` (a color-identity subset) and ``theme`` (a ``theme_presets`` lane) narrow
    the pool. Never uses EDHREC popularity.
    """
    if sort not in _DISCOVER_SORTS:
        sort = "support"
    records = owned_commander_records(state)
    if colors:
        allowed = set(colors.upper())
        records = [r for r in records if set(r.get("color_identity") or []) <= allowed]
    if theme:
        records = [r for r in records if theme_presets.matches(theme, r)]

    coll = _resolved_collection(state)
    slot = active_slot(state)
    fmt = state.session.format
    freq, total = _signal_freq(state) if sort == "novelty" else ({}, 0)
    # Seed both discovery caches from their sidecars so this skips the ~55s pool sweep
    # (density) and the ~10s collection scan (served sets). New lanes still compute
    # lazily and persist at the end. (Imports warm these in the background already.)
    _load_lane_density(state)
    _load_collection_serves(state, slot, coll)
    density_before = len(state.lane_density)
    served_before = len(state.lane_collection_serves.get(slot) or {})

    results: list[dict] = []
    for rec in records:
        identity = set(rec.get("color_identity") or [])
        # Support is OTHER owned cards that feed the commander's lanes — the commander
        # itself is the build's centerpiece, not its own support, so exclude it (and it
        # keeps the breadth denominator honest: a lane can't read as 100%-of-pool just
        # because the commander matches its own lane). Names (not records): support is a
        # set intersection against the per-lane served-name cache.
        in_names = {
            c["name"]
            for c in coll
            if c["name"] != rec["name"]
            and set(c.get("color_identity") or []) <= identity
        }
        depth, lanes, supported = _support_depth(state, rec, in_names, slot, coll)
        item = {
            "name": rec["name"],
            **views.project(rec, fmt),
            "support_depth": round(depth, 2),
            "lanes": lanes,
            "supported_lanes": supported,
        }
        if sort == "novelty":
            item["novelty"] = round(_novelty(rec, freq, total), 2)
        results.append(item)

    if sort == "novelty":
        # Hard support gate: only the buildable weird ones (own SOME support), then sort
        # by strangeness, with support depth as the tiebreak. Gate on a non-empty lane
        # breakdown (own ≥ 1 supporting card) rather than support_depth > 0 — the IDF
        # weight is 0 for a single lane every owned card serves (k == N), and such a
        # commander is still buildable, so it must not be silently dropped.
        results = [r for r in results if r["lanes"]]
        results.sort(key=lambda r: (-r["novelty"], -r["support_depth"], r["name"]))
    else:
        results.sort(
            key=lambda r: (-r["support_depth"], -r["supported_lanes"], r["name"])
        )
    if len(state.lane_density) > density_before:
        _save_lane_density(state)  # new densities computed this call — persist them
    if len(state.lane_collection_serves.get(slot) or {}) > served_before:
        _save_collection_serves(state, slot, coll)  # new served sets — persist them
    return results[:limit]


def partner_search(state: ForgeState) -> dict | None:
    """The ``card_search`` filter for cards legally eligible to be the deck's second
    commander (CR 702.124), or ``None`` when there's no open partner slot — i.e. the
    deck doesn't have exactly one commander, or that commander has no partner ability.
    Used to make the Partner / Background avenue surface only valid partners."""
    commanders = state.session.to_deck_dict()["commanders"]
    if len(commanders) != 1:
        return None  # 0 commanders (unknown) or 2 (slot already filled)
    record = state.by_name.get(commanders[0]["name"])
    if record is None:
        return None
    return valid_partner_search(record)


def _legality_key(fmt: str) -> str:
    cfg = FORMAT_CONFIGS.get(fmt)
    return cfg["legality_key"] if cfg else "commander"


def staple_pool(state: ForgeState) -> list[dict]:
    """The curated 'good stuff' staples offered to this deck — the hardcoded staple
    list (see ``staples``) filtered to the deck's color identity AND format legality,
    resolved from the bulk index. Empty without bulk. This is the candidate source for
    the always-present Staples avenue (a name list, not a search pattern)."""
    if not state.by_name:
        return []
    return staples.staples_for(
        deck_color_identity(state),
        state.by_name,
        legality_key=_legality_key(state.session.format),
    )


def staples_serve() -> dict:
    """The name serve shared by the Staples avenue and its explore call, so ranking
    credits every curated staple as on-theme for that avenue."""
    return {"names": sorted(staples.staple_names())}


def staples_avenue(state: ForgeState) -> dict | None:
    """The always-present 'Staples / good stuff' avenue, or ``None`` when no staple is
    in-identity and format-legal (so an empty avenue never renders). Its candidates are
    resolved at explore time via ``staple_pool``; the name serve lets ranking credit
    every staple as on-theme for this avenue."""
    if not staple_pool(state):
        return None
    return {
        "id": "engine:staples",
        "label": "Staples / good stuff",
        "description": (
            "cards that are good in most commander decks — ramp, fixing, removal, "
            "card draw, interaction, protection — filtered to your colors and format"
        ),
        "scope": "you",
        "source": "engine",
        "search": {"staples": True},
        "serve": staples_serve(),
    }


def _violation_message(category: str, violation: dict) -> dict:
    name = violation.get("name") or violation.get("card") or ""
    detail = (
        violation.get("legality")
        or violation.get("reason")
        or violation.get("message")
        or ""
    )
    label = category.replace("_", " ")
    body = name if not detail else (f"{name} ({detail})" if name else str(detail))
    return {"category": category, "message": f"{label}: {body}".strip(": ")}


def _overflow_warnings(hd: HydratedDeck, max_cards: int | None) -> list[dict]:
    """Two failure modes the shared ``legality_audit`` deliberately doesn't own, because
    they're build-surface concerns: a deck that has grown PAST its size cap (the mirror
    of the excluded ``deck_minimum`` — under is normal building, over is never legal),
    and card names that resolved to no Scryfall record (a typo or a failed paste-import,
    which ADR-0012 otherwise DROPs silently from the hydrated records)."""
    out: list[dict] = []
    if max_cards is not None:
        total = sum(
            int(e.get("quantity", 1))
            for zone in ("commanders", "cards")
            for e in hd.deck.get(zone) or []
        )
        if total > max_cards:
            out.append(
                {
                    "category": "deck_maximum",
                    "message": f"deck maximum: {total} cards (max {max_cards})",
                }
            )
    unimported = [
        e["name"]
        for zone in ("commanders", "cards", "sideboard")
        for e in hd.deck.get(zone) or []
        if e.get("name") and e["name"] not in hd.by_name
    ]
    out.extend(
        {"category": "unimported", "message": f"did not import: {name}"}
        for name in unimported
    )
    return out


def legality_warnings(hd: HydratedDeck, *, max_cards: int | None = None) -> list[dict]:
    audit = legality_audit(hd)
    violations = audit.get("violations") or {}
    return [
        _violation_message(cat, v)
        for cat in _AUDIT_CATEGORIES
        for v in (violations.get(cat) or [])
    ] + _overflow_warnings(hd, max_cards)


def finalize_state(state: ForgeState) -> dict:
    """The finalize REPORT (not the gating decision — the route owns the override)."""
    hd = hydrate(state)
    mana = mana_audit(hd)
    avg_cmc = deck_stats(hd).get("avg_cmc", 0.0)
    cheap_ca = sum(
        1 for r in hd.expanded() if "card_draw" in role_of(r) and r.get("cmc", 0) <= 2
    )
    defensible = avg_cmc <= _DEFENSIBLE_AVG_CMC and cheap_ca >= _DEFENSIBLE_CHEAP_CA
    warnings = legality_warnings(hd, max_cards=state.session.deck_size)
    return {
        "land_status": mana["land_count_status"],
        "land_count": mana["land_count"],
        "recommended_land_count": mana["recommended_land_count"],
        "evidence": {
            "avg_cmc": avg_cmc,
            "cheap_card_advantage": cheap_ca,
            "defensible": defensible,
        },
        "legality_status": "FAIL" if warnings else "PASS",
        "warnings": warnings,
    }


def ranked_deck_signals(state: ForgeState, hydrated: list[dict]) -> list:
    """Deck signals deduped by (key, scope, subject) and ranked by relevance.

    Thin ForgeState wrapper over the shared ``signals.rank_deck_signals`` core that the
    deterministic tuner also calls (ADR-0023). Wires the Card-IR index (ADR-0027) so
    migrated keys — served only from the IR — surface in the deck's avenues."""
    commander_names = {e["name"] for e in state.session.to_deck_dict()["commanders"]}
    return rank_deck_signals(
        hydrated,
        commander_names,
        resolve_object=state.object_resolver,
        ir_for=ir_for,
    )


def signal_dict(signal: Signal) -> dict:
    spec = spec_for(signal)
    return {
        "key": signal.key,
        "scope": signal.scope,
        "subject": signal.subject,
        "source": signal.source,
        "confidence": signal.confidence,
        "label": spec.label if spec else signal.key,
        "avenue": spec.avenue if spec else "",
        "actionable": spec is not None,
    }


def avenues(state: ForgeState, hydrated: list[dict]) -> list[dict]:
    """All explorable avenues: engine-derived (from scoped signals with specs) plus any
    the session-agent has discovered and posted. Each carries the search spec needed to
    surface its candidates."""
    out: list[dict] = []
    # Dedupe by label: a signal that fires at two scopes (you + any) can resolve to the
    # same scope-agnostic spec, which would otherwise render twice.
    seen_labels: set[str] = set()
    for sig in ranked_deck_signals(state, hydrated):
        if len(seen_labels) >= _AVENUE_CAP:
            break
        spec = spec_for(sig)
        if spec is None or spec.label in seen_labels:
            continue
        main_search = dict(spec.search)
        widening = False
        # The Partner / Background avenue is commander-specific: replace its generic
        # "any partner card" search with one scoped to cards that can LEGALLY be this
        # commander's second commander (CR 702.124). Skip it when there's no open slot.
        if sig.key == "partner_background":
            psearch = partner_search(state)
            if psearch is None:
                continue
            main_search = psearch
            # Flag the partner avenue so the Find ranker sorts its candidates by color
            # widening first, then synergy (ADR-0019). A second commander is the only
            # card that can change the deck's color identity, so this flag lives here.
            widening = True
        seen_labels.add(spec.label)
        # Include subject so distinct tribes (Goblin vs Dwarf) get distinct avenues.
        suffix = f":{sig.subject}" if sig.subject else ""
        avenue_id = f"engine:{sig.key}:{sig.scope}{suffix}"
        # ADR-0026: split a fused payoff/source serve into a payoff avenue (oracle) +
        # a Source avenue (the pieces — auras/equipment, artifacts, instants…). Never
        # split the partner avenue (its search is commander-legality, not a serve).
        split = None if widening else source_split(spec)
        main_serve = spec.serve
        if split is not None:
            source_serve, source_search = split
            main_search = payoff_search(main_search, spec.serve)
            main_serve = payoff_serve(spec)
        out.append(
            avenue_with_serve(
                {
                    "id": avenue_id,
                    "label": spec.label,
                    "description": spec.avenue,
                    "scope": sig.scope,
                    "source": "engine",
                    "search": main_search,
                    "widening": widening,
                },
                main_serve,
            )
        )
        if split is not None:
            source_serve, source_search = split
            src_label = source_label(source_serve.types)
            if src_label not in seen_labels:
                seen_labels.add(src_label)
                out.append(
                    avenue_with_serve(
                        {
                            "id": f"{avenue_id}:src",
                            "label": src_label,
                            "description": (
                                f"the {src_label.lower()} in your colors — the pieces "
                                f"that feed your {spec.label.lower()} payoffs"
                            ),
                            "scope": sig.scope,
                            "source": "engine",
                            "search": source_search,
                        },
                        source_serve,
                    )
                )
        # A signal can fan out into several precise sub-avenues (e.g. the land-creatures
        # theme: creature-lands / payoffs / animators).
        for i, extra in enumerate(spec.extras):
            if extra.label in seen_labels:
                continue
            seen_labels.add(extra.label)
            out.append(
                avenue_with_serve(
                    {
                        "id": f"{avenue_id}:{i}",
                        "label": extra.label,
                        "description": extra.avenue,
                        "scope": sig.scope,
                        "source": "engine",
                        "search": dict(extra.search),
                    },
                    extra.serve,
                )
            )
    # Always-present "good stuff" avenue — independent of the deck's signals, so even a
    # signal-less commander gets a curated staples shortlist (scoped to colors/format).
    sa = staples_avenue(state)
    if sa is not None:
        out.append(sa)
    out.extend(state.agent_avenues)
    for avenue in out:  # mark which lanes the human has pinned (#2)
        avenue["focused"] = avenue["id"] in state.focused_avenue_ids
    return out


def scoring_basis(
    state: ForgeState, hydrated: list[dict], sigs: list, context_avenues: list[dict]
) -> tuple[list, list[dict]]:
    """Pick the ``(active_signals, avenues)`` a candidate is scored against.

    Default (nothing focused): today's behavior — the deck's scoped signals AND the
    avenue(s) in context (the one being explored, or a package's own avenue, plus agent
    avenues). With one or more focused avenues the synergy score is scoped to ONLY the
    focused lanes: the broad signal counting is dropped (that diffuse "every lane the
    deck happens to touch" tally is the noise focus exists to remove), so the score
    reads "serves N of your M focused lanes." See deck-forge CONTEXT.md, Focused avenue.
    """
    if not state.focused_avenue_ids:
        return sigs, context_avenues
    focused = [
        a for a in avenues(state, hydrated) if a["id"] in state.focused_avenue_ids
    ]
    return [], focused


def explore_filters(search: dict, *, color_identity: str, fmt: str) -> dict:
    filters = {k: search[k] for k in _EXPLORE_KEYS if search.get(k) is not None}
    presets = search.get("preset_names") or search.get("presets")
    if presets:
        filters["preset_names"] = tuple(presets)
    # An avenue may carry its own color_identity (e.g. partner avenues pass "WUBRG" to
    # stay color-agnostic — partner legality has no color restriction); otherwise scope
    # to the deck's identity.
    filters["color_identity"] = search.get("color_identity") or color_identity
    filters["format"] = fmt
    return filters


@dataclass(frozen=True)
class FindParams:
    """A Find request as the engine's own struct — the transport-agnostic mirror of the
    route's ``SearchPayload``. Keeping engine free of FastAPI/pydantic types (ADR-0013:
    engine takes a ForgeState, not a Request) lets ``find_candidates`` be driven
    directly in tests; the route adapts its ``SearchPayload`` into this struct."""

    color_identity: str | None = None
    exact_colors: bool = False
    oracle: str | None = None
    type: str | None = None
    name: str | None = None
    cmc_min: float | None = None
    cmc_max: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    format: str | None = None
    presets: tuple[str, ...] = ()
    is_commander: bool = False
    sort: str = "cmc-asc"
    limit: int = 25
    offset: int = 0


@dataclass(frozen=True)
class CandidatePage:
    """A window of ranked candidate rows plus paging metadata. ``rows`` are
    ``rank_candidates`` rows (``{"card", "score"}``) — RANKED RECORDS, not serialized
    wire dicts. The route projects them via ``views.candidate_view`` (ADR-0013 keeps
    the views seam separate), so ``find_candidates`` is tested on selection and
    ordering, not the wire shape. ``total`` is the pre-window ranked count."""

    rows: list[dict]
    offset: int
    has_more: bool
    total: int


def has_user_filters(params: FindParams) -> bool:
    """Whether a Find request carries any narrowing filter — so a no-focus, no-filter
    request returns an idle empty page instead of dumping the whole vault."""
    return bool(
        params.name
        or params.oracle
        or params.type
        or params.color_identity
        or params.presets
        or params.is_commander
        or params.cmc_min is not None
        or params.cmc_max is not None
        or params.price_min is not None
        or params.price_max is not None
    )


def refine_filters(base: dict, params: FindParams) -> dict:
    """Merge the user's narrowing filters onto a focused avenue's card_search kwargs.
    The avenue owns the oracle (its lane definition), so user ``oracle`` is deliberately
    not merged — name/type/color/cmc/price AND on top to refine the lane's pool."""
    out = dict(base)
    if params.name:
        out["name"] = params.name
    if params.type:
        out["card_type"] = params.type
    if params.color_identity:
        out["color_identity"] = params.color_identity
    if params.cmc_min is not None:
        out["cmc_min"] = params.cmc_min
    if params.cmc_max is not None:
        out["cmc_max"] = params.cmc_max
    if params.price_min is not None:
        out["price_min"] = params.price_min
    if params.price_max is not None:
        out["price_max"] = params.price_max
    return out


def find_candidates(state: ForgeState, params: FindParams) -> CandidatePage:
    """The unified Find pipeline (ADR-0015) as a free function over ForgeState — the
    candidate-pipeline extraction ADR-0013 parked. Three branches on focus state:

    * FOCUSED avenues → OR-merge each lane's pool (a Staples lane resolves the curated
      name pool via ``staple_pool``; others ``search_fn`` the lane's ``explore_filters``
      base, AND-refined by the user's filters), score against the focused lanes, rank
      (with color-widening when a focused avenue carries it, ADR-0019).
    * no focus but user FILTERS → a manual ``search_fn`` scored against everything.
    * neither → an empty page (an idle prompt, not the whole vault).

    Strips cards already in the deck, then returns the requested window of ranked rows.
    The route serializes the rows and annotates ownership; this stops at ranked records.
    """
    fmt = state.session.format
    ci = deck_color_identity(state)
    hd = hydrate(state)
    sigs = ranked_deck_signals(state, hd.records)
    all_avenues = avenues(state, hd.records)
    focused = [a for a in all_avenues if a.get("focused")]
    in_deck = set(state.session.card_names())

    if focused:
        pool: dict[str, dict] = {}
        for av in focused:
            if (av.get("search") or {}).get("staples"):
                found = staple_pool(state)
            else:
                base = explore_filters(av["search"], color_identity=ci, fmt=fmt)
                found = state.search_fn(
                    limit=_FIND_POOL,
                    paper_only=paper_only(fmt),
                    **refine_filters(base, params),
                )
            for card in found:
                cname = card.get("name")
                if cname:
                    pool.setdefault(cname, card)
        cands = [c for c in pool.values() if c.get("name") not in in_deck]
        active, avs = scoring_basis(state, hd.records, sigs, focused)
        # The partner avenue ranks by color widening first (ADR-0019): pass the deck's
        # current identity as the widening base when it is among the focused lanes, so
        # the broadest color-openers surface above synergy.
        widening_base = ci if any(a.get("widening") for a in focused) else None
        # Focused avenues are the user's hand-picked lanes: rank by how MANY of
        # them a card serves (fit count), not synergy depth — the depth clustering
        # would collapse two focused lanes the user deliberately chose as distinct.
        ranked = rank_candidates(
            cands,
            active_signals=active,
            avenues=avs,
            widening_base=widening_base,
            rank_by="fit",
        )
    elif has_user_filters(params):
        records = state.search_fn(
            color_identity=params.color_identity,
            exact_colors=params.exact_colors,
            oracle=params.oracle,
            card_type=params.type,
            name=params.name,
            cmc_min=params.cmc_min,
            cmc_max=params.cmc_max,
            price_min=params.price_min,
            price_max=params.price_max,
            format=params.format,
            paper_only=paper_only(params.format),
            preset_names=tuple(params.presets),
            is_commander_filter=params.is_commander,
            sort=params.sort,
            limit=_FIND_POOL,
            offset=0,
        )
        cands = [c for c in records if c.get("name") not in in_deck]
        ranked = rank_candidates(cands, active_signals=sigs, avenues=all_avenues)
    else:
        ranked = []

    page = max(1, params.limit)
    offset = max(0, params.offset)
    return CandidatePage(
        rows=ranked[offset : offset + page],
        offset=offset,
        has_more=len(ranked) > offset + page,
        total=len(ranked),
    )


def goldfish_report(
    state: ForgeState, *, games: int = 100, turns: int = 14, seed: int = 0
) -> dict:
    """Run-here handoff (#6, ADR-0016): goldfish the current deck IN-PROCESS — pure
    local compute, no API key, no subprocess — reusing the ``playtest-goldfish`` core
    the hub already ships in ``mtg_utils``. Returns the rendered markdown plus the raw
    schema-v1 envelope. Imports are local so the snapshot path never pays for the
    playtest module."""
    import time as _time

    from mtg_utils._playtest_common import envelope, render_goldfish_markdown
    from mtg_utils.playtest import GOLDFISH_VERSION, _run_goldfish

    hd = hydrate(state)
    deck = state.session.to_deck_dict()
    entries = (deck.get("commanders") or []) + (deck.get("cards") or [])
    records = hd.expanded(zones=("commanders", "cards"))
    requested = sum(int(e.get("quantity", 1)) for e in entries)
    missing = sorted({e["name"] for e in entries if e["name"] not in hd.by_name})

    start = _time.perf_counter()
    results = _run_goldfish(records, games=games, max_turns=turns, base_seed=seed)
    elapsed = _time.perf_counter() - start

    out = envelope(
        mode="goldfish",
        engine="goldfish",
        engine_version=GOLDFISH_VERSION,
        seed=seed,
        format_=deck.get("format"),
        card_coverage={
            "requested": requested,
            "supported": len(records),
            "missing": missing,
        },
        results=results,
        warnings=[f"{len(missing)} cards not in hydrated cache"] if missing else [],
        duration_s=elapsed,
    )
    return {"markdown": render_goldfish_markdown(out), "report": out}


def render_proxies(
    state: ForgeState, out_path: Path, *, page_size: str = "letter"
) -> int:
    """Run-here handoff (#6, ADR-0016): render printable card proxies to ``out_path`` as
    a PDF, IN-PROCESS via ``proxy_print.build_pdf`` (reportlab is its lazy backend). One
    proxy per copy of every commander + mainboard card, hydrated from the hub's bulk
    index. Returns the count rendered (0 = nothing renderable)."""
    from mtg_utils.deck import hydrate as hydrate_card
    from mtg_utils.deck import walk_cards
    from mtg_utils.proxy_print import build_pdf

    deck = state.session.to_deck_dict()
    items: list[tuple[dict, list[str] | None]] = []
    for name, qty in walk_cards(deck, include_sideboard=False, copies=1):
        src = state.by_name.get(name)
        if src is None:
            continue  # un-hydratable name → skip (DROP convention)
        items.extend([(hydrate_card(src), None)] * qty)
    if not items:
        return 0
    build_pdf(
        out_path,
        items,
        page_size=page_size,
        is_token=False,
        title=f"deck-forge proxies — {state.build_name}",
    )
    return len(items)


def snapshot(state: ForgeState) -> dict:
    """The full canonical snapshot the SPA renders — the engine's composition root.
    Builds ONE HydratedDeck and threads it to every sub-analysis, so a request hits the
    bulk index once. Pure read of state; never mutates, publishes, or autosaves."""
    hd = hydrate(state)
    stats = deck_stats(hd)
    owned = owned_quantities(state)
    return {
        "build_id": state.build_id,
        "build_name": state.build_name,
        "deck": views.deck_view(state, owned),
        "stats": stats,
        "bracket": detect_bracket(hd.records, stats.get("avg_cmc", 0.0)),
        "mana": mana_audit(hd),
        "budgets": slot_budgets(hd.expanded(), deck_size=state.session.deck_size),
        "signals": [signal_dict(s) for s in ranked_deck_signals(state, hd.records)],
        "avenues": avenues(state, hd.records),
        "warnings": legality_warnings(hd, max_cards=state.session.deck_size),
        "collection": collection_summary(state, owned),
        "wildcards": wildcard_cost(state),
        # True when a second commander could still be added (CR 702.124 partner /
        # Background): the Find color pips stay unlocked so an off-identity partner is
        # findable; otherwise they lock to the commander's identity (A5).
        "partner_open": partner_search(state) is not None,
    }
