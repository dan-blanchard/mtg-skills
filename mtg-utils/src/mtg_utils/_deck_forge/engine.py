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

import math
from dataclasses import dataclass
from pathlib import Path

from mtg_utils import mark_owned, price_check, theme_presets
from mtg_utils._deck_forge import collection, staples, views
from mtg_utils._deck_forge.budgets import role_of, slot_budgets
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import Serve, spec_for
from mtg_utils._deck_forge.signals import Signal, extract_signals
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils._name_index import NameIndex
from mtg_utils.card_classify import is_commander, valid_partner_search
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
    return bool(record) and "Basic Land" in (record.get("type_line") or "")


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
    if state.collection_store is not None:
        state.collection_store.save(state.collections)


def clear_collection(state: ForgeState, slot: str) -> None:
    """Drop a Collection slot (and its cached lookup), then persist."""
    state.collections.pop(slot, None)
    state.collection_index.pop(slot, None)
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
    """A collection card name → its bulk record (exact, then case-insensitive)."""
    rec = state.by_name.get(name)
    if rec is not None:
        return rec
    low = name.lower()
    return next((r for n, r in state.by_name.items() if n.lower() == low), None)


def _resolved_collection(state: ForgeState) -> list[dict]:
    """Every active-slot collection card resolved to a bulk record (un-resolvable names
    dropped — we can't reason about cards we have no data for)."""
    pile = state.collections.get(active_slot(state)) or {}
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


def _commander_lanes(record: dict) -> list[tuple[str, Serve]]:
    """The commander's actionable signal-derived lanes as ``(label, serve)`` pairs,
    deduped by label. The generic Staples lane is NOT a signal spec, so it's naturally
    excluded — owning good-stuff isn't commander-specific support (Q9)."""
    out: list[tuple[str, Serve]] = []
    seen: set[str] = set()
    for sig in extract_signals(record, include_membership=True):
        spec = spec_for(sig)
        if spec is None or spec.label in seen:
            continue
        seen.add(spec.label)
        out.append((spec.label, spec.serve))
    return out


def _support_depth(
    record: dict, owned_in_identity: list[dict]
) -> tuple[float, list, int]:
    """Breadth-down-weighted owned support (ADR-0018 / Q10): sum over lanes of
    ``own(L) * log(N / own(L))`` where ``own(L)`` = in-identity owned cards serving lane
    L and ``N`` = total in-identity owned. A near-universal lane (own close to N)
    contributes ~0 (IDF), so breadth isn't mistaken for quality. Returns
    ``(score, per-lane breakdown, # supported lanes)``."""
    n = len(owned_in_identity)
    if n == 0:
        return 0.0, [], 0
    score = 0.0
    breakdown: list[dict] = []
    supported = 0
    for label, serve in _commander_lanes(record):
        k = sum(1 for c in owned_in_identity if serve.matches(c))
        if k == 0:
            continue
        score += k * math.log(n / k) if k < n else 0.0
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
    for rec in state.by_name.values():
        if not is_commander(rec, fmt)["eligible"]:
            continue
        total += 1
        for key in {(s.key, s.subject) for s in extract_signals(rec)}:
            freq[key] = freq.get(key, 0) + 1
    state.commander_signal_freq[fmt] = (freq, total)
    return freq, total


def _novelty(record: dict, freq: dict, total: int) -> float:
    """Signal rarity: summed inverse-frequency of the commander's signals over the pool,
    so an off-beat hook outranks tokens / counters / ramp. Blind by design to commanders
    whose ability fires no detector (they score 0) — the accepted limit of signal-based
    novelty."""
    keys = {
        (s.key, s.subject) for s in extract_signals(record, include_membership=True)
    }
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
    fmt = state.session.format
    freq, total = _signal_freq(state) if sort == "novelty" else ({}, 0)

    results: list[dict] = []
    for rec in records:
        identity = set(rec.get("color_identity") or [])
        # Support is OTHER owned cards that feed the commander's lanes — the commander
        # itself is the build's centerpiece, not its own support, so exclude it (and it
        # keeps the breadth denominator honest: a lane can't read as 100%-of-pool just
        # because the commander matches its own lane).
        in_identity = [
            c
            for c in coll
            if c["name"] != rec["name"]
            and set(c.get("color_identity") or []) <= identity
        ]
        depth, lanes, supported = _support_depth(rec, in_identity)
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


def legality_warnings(hd: HydratedDeck) -> list[dict]:
    audit = legality_audit(hd)
    violations = audit.get("violations") or {}
    return [
        _violation_message(cat, v)
        for cat in _AUDIT_CATEGORIES
        for v in (violations.get(cat) or [])
    ]


def finalize_state(state: ForgeState) -> dict:
    """The finalize REPORT (not the gating decision — the route owns the override)."""
    hd = hydrate(state)
    mana = mana_audit(hd)
    avg_cmc = deck_stats(hd).get("avg_cmc", 0.0)
    cheap_ca = sum(
        1 for r in hd.expanded() if "card_draw" in role_of(r) and r.get("cmc", 0) <= 2
    )
    defensible = avg_cmc <= _DEFENSIBLE_AVG_CMC and cheap_ca >= _DEFENSIBLE_CHEAP_CA
    warnings = legality_warnings(hd)
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

    Membership signals (own-subtype tribal, voltron fallback) are taken from the
    COMMANDER only — otherwise every creature's race/stat-line floods the deck. A
    theme's ``support`` (how many cards feed it) drives the ranking."""
    commander_names = {e["name"] for e in state.session.to_deck_dict()["commanders"]}
    support: dict[tuple[str, str, str], int] = {}
    from_commander: set[tuple[str, str, str]] = set()
    first: dict[tuple[str, str, str], object] = {}
    for card in hydrated:
        is_cmd = card.get("name") in commander_names
        for sig in extract_signals(card, include_membership=is_cmd):
            ident = (sig.key, sig.scope, sig.subject)
            support[ident] = support.get(ident, 0) + 1
            if is_cmd:
                from_commander.add(ident)
            first.setdefault(ident, sig)
    return sorted(
        first.values(),
        key=lambda s: (
            (s.key, s.scope, s.subject) in from_commander,
            support[(s.key, s.scope, s.subject)],
            s.confidence == "high",
        ),
        reverse=True,
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
                spec.serve,
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
        ranked = rank_candidates(
            cands, active_signals=active, avenues=avs, widening_base=widening_base
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
        "warnings": legality_warnings(hd),
        "collection": collection_summary(state, owned),
        "wildcards": wildcard_cost(state),
    }
