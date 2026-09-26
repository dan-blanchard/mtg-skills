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

import functools
import time
import uuid
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from mtg_utils import card_search, mark_owned, ownership
from mtg_utils._analysis import staples
from mtg_utils._analysis.budgets import banded_slot_budgets, template_for
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._analysis.roles import role_of
from mtg_utils._analysis.signal_specs import (
    Serve,
    payoff_search,
    payoff_serve,
    source_label,
    source_split,
    spec_for,
)
from mtg_utils._analysis.signals import (
    Signal,
    extract_signals,
    rank_deck_signals,
)
from mtg_utils._deck_forge import collection, views
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils._gauntlet_build import build_gauntlet_deck
from mtg_utils._name_index import NameIndex
from mtg_utils._tuner.tune import TuneParams
from mtg_utils.card_classify import (
    classifying_type_line,
    get_colors,
    is_basic_land,
    is_land,
    valid_partner_search,
)
from mtg_utils.card_pool import CardPool, printing_of
from mtg_utils.companion import is_companion
from mtg_utils.deck import deck_entries
from mtg_utils.deck_stats import deck_stats, detect_bracket
from mtg_utils.formats import (
    FOIL_FINISHES,
    FORMATS,
    Coverage,
    Format,
    family_size_choices,
    format_options,
)
from mtg_utils.hydrated_deck import ZONES, HydratedDeck
from mtg_utils.legality_audit import card_copy_limit, legality_audit
from mtg_utils.mana_audit import (
    limited_land_target,
    mana_audit,
    reconcile_basic_lands,
)
from mtg_utils.parse_deck import parse_deck_text
from mtg_utils.set_scan import pool_color_pairs, set_scan

# deck_minimum is intentionally excluded: a deck-in-progress is always below the size
# minimum, so it's the normal building state, not a warning.
_AUDIT_CATEGORIES = (
    "format_legality",
    "commander_zone",
    "color_identity",
    "copy_limits",
    "sideboard_size",
    "pool_containment",
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
    return extract_signals(record, include_membership=include_membership)


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


def hydrate_session(state: ForgeState) -> HydratedDeck:
    """One HydratedDeck per request, joining the live session against the bulk index.
    Build it once at a handler's entry and thread it — every deck analysis reads it."""
    return HydratedDeck.from_session(state.session, state.by_name)


def deck_color_identity(state: ForgeState) -> str:
    """Union of the commanders' color identities (the deck's color identity)."""
    colors: set[str] = set()
    for entry in state.session.to_deck_dict()["commanders"]:
        record = state.by_name.get(entry["name"])
        if record:
            colors.update(record.get("color_identity", []))
    return "".join(sorted(colors))


def deck_colors(state: ForgeState) -> str:
    """The colors a candidate search is scoped to, by family: the commanders' color
    identity where there is a command zone (CR 903.4 — the rule), else the castable
    colors of the nonland cards the build already runs (a description, so the Find
    pips stay unlocked — a splash is the builder's call, not a rule)."""
    if state.session.fmt.has_commander:
        return deck_color_identity(state)
    colors: set[str] = set()
    deck = state.session.to_deck_dict()
    for zone in built_zones(state):
        for entry in deck.get(zone) or []:
            record = state.by_name.get(entry["name"])
            if record and _casts(record):
                colors.update(get_colors(record))
    return "".join(sorted(colors))


def built_zones(state: ForgeState) -> tuple[str, ...]:
    """The zones a build's own cards live in — the main deck plus a STORED sideboard.
    A pool-bounded build's sideboard is the unused pool, which is not something the
    builder chose to run, so there it is the main deck alone. The one answer for
    every read of "the cards this deck runs" that is not the counted deck
    (``HydratedDeck.deck_records``): colours, ownership, combos, finalize evidence."""
    return ("cards",) if state.session.pool_bounded else ("cards", "sideboard")


def deck_names(state: ForgeState) -> set[str]:
    """Every distinct name the build runs: commanders, the built zones, the companion
    — never an opened pool."""
    names: set[str] = set()
    for zone in ("commanders", *built_zones(state), "companion"):
        names.update(state.session.quantities(zone))
    return names


def _casts(record: dict) -> bool:
    """Whether a card is something the deck CASTS (its colours are the deck's): any
    nonland, and a modal DFC with a spell face (a Sorcery // Land is cast for its
    front; a Land // Land is not). A transform card is judged by its front."""
    if not is_land(record):
        return True
    faces = record.get("card_faces") or []
    if record.get("layout") == "modal_dfc" and faces:
        return any("Land" not in (f.get("type_line") or "") for f in faces)
    return "Land" not in classifying_type_line(record)


def check_commander_family(state: ForgeState) -> None:
    """The family rule for a Commander-only surface (commander discovery): the
    build's format has a command zone."""
    fmt = state.session.fmt
    if not fmt.has_commander:
        raise DeckRuleError(f"{fmt.label} has no command zone")


def is_paper(state: ForgeState) -> bool:
    """Whether this build is paper (vs digital/Arena). Drives the Collection slot and
    the cost mode (USD vs wildcards). Commander is always paper; Brawl / Historic Brawl
    follow the chosen medium (ADR-0018, amended: medium not format decides the slot)."""
    return state.session.medium == "paper"


def active_slot(state: ForgeState) -> str:
    """The Collection slot read for this build (``ForgeState.active_slot``)."""
    return state.active_slot


def _is_basic(record: dict | None) -> bool:
    return record is not None and is_basic_land(record)


def owned_quantities(state: ForgeState) -> dict[str, int]:
    """Owned-copy map (deck card name → count) against the ACTIVE Collection slot only —
    empty when that slot holds no imported Collection. The names are the deck's
    (:func:`deck_names`: never an opened pool, whose cards are owned by definition).
    Every card is read, basic lands included: whether a basic counts as owned is
    ``Format.coverage``'s call (the six basic land types are free; Snow-Covered basics
    are collected like any card). DERIVED fresh each call from the cached per-slot
    lookup; never stored."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return {}
    entries, lookup = idx
    out: dict[str, int] = {}
    for name in sorted(deck_names(state)):
        qty = mark_owned.owned_quantity(name, entries, lookup)
        if qty is not None:
            out[name] = qty
    return out


def owned_collection(state: ForgeState) -> dict[str, int]:
    """EVERY owned card in the active Collection slot (name -> copies).

    Distinct from :func:`owned_quantities`, which is deck-scoped (the "X of Y owned"
    readout). The tuner judges *candidate* adds — cards NOT yet in the deck — so a
    deck-scoped map makes every candidate read as un-owned: at a zero wildcard budget
    nothing would be affordable (no owned-card fills), and owned-but-not-in-deck cards
    would wrongly burn budget. This whole-slot map lets the tuner treat any owned
    candidate as free (``Format.coverage`` decides basics). Keyed by the collection's
    own names (canonical for Untapped/Arena and Moxfield exports), which match the
    canonical names ``card_search`` returns."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return {}
    entries, _lookup = idx
    return {name: qty for name, qty in entries.values() if qty >= 1}


def owned_of(state: ForgeState, name: str) -> int | None:
    """Owned copies of an arbitrary card name in the active Collection slot, or None.
    Unlike :func:`owned_quantities` (deck-scoped) this answers for any card — so Find
    can flag whether a *candidate* is already on your shelf (the 'Owned only' facet)."""
    idx = state.collection_index.get(active_slot(state))
    if not idx:
        return None
    entries, lookup = idx
    return mark_owned.owned_quantity(name, entries, lookup)


def coverage(state: ForgeState, owned: Mapping[str, int], entry: Mapping) -> Coverage:
    """How far the active Collection slot covers a deck entry (``{name, quantity}``,
    plus its ``printing_id`` / ``finish`` pins), given ``owned`` (name → owned copies,
    :func:`owned_quantities`): ``Format.coverage`` for the build's medium, served per
    row so every readout — the footer total, the per-group subtotals, each row's label,
    the owned tick, the "N of M owned" count, the Owned-only facet — reads it and the
    browser derives nothing. In paper a pinned printing or finish is the entry's
    printing request (only a special basic printing counts,
    ``ownership.requested_printing_owned``). An opened pool is owned outright."""
    if state.session.pool_bounded:
        return Coverage(0, "owned")
    name = entry["name"]
    requested = None
    printing_id = entry.get("printing_id")
    if is_paper(state) and (printing_id or entry.get("finish")):
        record = state.printing_by_id.get(printing_id) if printing_id else None
        requested = ownership.requested_printing_owned(
            name, entry, record, owned_printing_detail(state, name)
        )
    return Format.coverage(
        state.session.medium,
        name,
        entry["quantity"],
        owned.get(name, 0),
        requested_owned=requested,
    )


def candidate_coverage(state: ForgeState, name: str) -> Coverage:
    """How far the active Collection slot covers adding one copy of ``name`` — for a
    card shown outside the deck (a Find result, a combo piece) — by :func:`coverage`."""
    return coverage(
        state, {name: owned_of(state, name) or 0}, {"name": name, "quantity": 1}
    )


def set_collection(state: ForgeState, slot: str, pile: dict) -> None:
    """Load a parsed Collection ``pile`` into ``slot``: cache its precomputed ownership
    lookup (so snapshots stay O(deck size)) and persist. The single mutation point for a
    Collection slot."""
    pile = collection.owned_only(pile)  # drop quantity-0 (un-owned/wishlist) rows
    state.collections[slot] = pile
    state.collection_index[slot] = mark_owned.owned_lookup(
        pile, name_aliases=state.name_aliases or None
    )
    # Per-printing detail (set/collector/foil), for entries that carry it — sparse,
    # so a plain name-only pile yields an empty index (tri-state: printing unknown).
    state.collection_printings[slot] = ownership.printing_index(pile)
    if state.collection_store is not None:
        state.collection_store.save(state.collections)


def clear_collection(state: ForgeState, slot: str) -> None:
    """Drop a Collection slot (and its cached lookup), then persist."""
    state.collections.pop(slot, None)
    state.collection_index.pop(slot, None)
    state.collection_printings.pop(slot, None)
    if state.collection_store is not None:
        state.collection_store.save(state.collections)


def owned_printing_detail(
    state: ForgeState, name: str
) -> dict[tuple[str, str], tuple[int, int]] | None:
    """Per-printing owned copies of ``name`` in the ACTIVE Collection slot:
    ``{(set, collector_number): (nonfoil_qty, foil_qty)}`` — or ``None`` when the
    collection has NO printing detail for the name (name-only ownership, or no
    collection at all). Resolution shares ``mark_owned``'s DFC / Arena-alias keys
    with the name-level reads, so both levels agree on which entry a name is."""
    slot = active_slot(state)
    idx = state.collection_index.get(slot)
    printings = state.collection_printings.get(slot)
    if not idx or not printings:
        return None
    _entries, lookup = idx
    primary = mark_owned.collection_key(name, lookup)
    if primary is None:
        return None
    return printings.get(primary)


def printing_owned(
    state: ForgeState, name: str, printing_id: str | None = None
) -> bool | None:
    """Tri-state printing-level ownership for a card's effectively-chosen printing:
    the pinned ``printing_id`` when given, else the default (cheapest) record the
    deck displays. ``True`` = that exact (set, collector) is owned in the active
    slot; ``False`` = the collection HAS printing detail for this name but not this
    printing; ``None`` = no printing detail (name-only ownership — the existing
    ``owned`` bool remains the only signal)."""
    detail = owned_printing_detail(state, name)
    if detail is None:
        return None
    record = state.printing_by_id.get(printing_id) if printing_id else None
    if record is None:
        record = state.by_name.get(name)
    if record is None:
        return None
    key = ((record.get("set") or "").lower(), str(record.get("collector_number") or ""))
    nonfoil, foil = detail.get(key, (0, 0))
    return (nonfoil + foil) > 0


def pin_imported_printings(
    state: ForgeState, session: DeckSession, parsed: dict
) -> None:
    """Auto-pin printings for a just-imported deck (ADR-0017 + printing picker):
    an entry carrying ``set`` + ``collector_number`` (the keys ``parse_deck`` reads
    off Moxfield/Arena/CSV lines) resolves against ``printings_by_oracle`` — set code
    case-insensitively, collector number as an exact string — and pins that printing
    on the session card. A ``finish`` ("foil"/"etched") is stored with the pin when
    the resolved printing actually offers it. Unresolvable pairs stay unpinned (the
    cheapest default) and invalid finishes are dropped — an import never errors on
    printing detail."""
    for zone in ZONES:
        for entry in parsed.get(zone) or []:
            name = entry.get("name")
            set_code = (entry.get("set") or "").lower()
            collector = str(entry.get("collector_number") or "")
            if not (name and set_code and collector):
                continue
            match = printing_of(
                state.by_name, state.printings_by_oracle, name, set_code, collector
            )
            if match is None:
                continue
            finish = entry.get("finish")
            if finish not in FOIL_FINISHES or finish not in (
                match.get("finishes") or []
            ):
                finish = None
            session.set_printing(name, match.get("id"), zone=zone, finish=finish)


def collection_summary(state: ForgeState, owned: Mapping[str, int]) -> dict:
    """The Collection readout the SPA renders: which slot is active, each slot's size,
    and the 'N of M owned' count — of the deck's distinct cards that aren't free (a
    basic land), how many the collection covers (:func:`coverage`). Seventeen Hare
    Apparent with one owned is not owned."""
    by_name = {e["name"]: coverage(state, owned, e) for e in _deck_rows(state)}
    covered, total = ownership.covered_count(by_name.values())
    return {
        "active_slot": active_slot(state),
        "slots": collection.slot_sizes(state.collections),
        "owned": covered,
        "deck_total": total,
    }


def _deck_rows(state: ForgeState) -> list[dict]:
    """The build's deck entries — commanders, the built zones and the companion, never
    an opened pool (:func:`deck_names`' zones) — with their printing pins."""
    zones = ("commanders", *built_zones(state), "companion")
    return deck_entries(state.session.to_deck_dict(), zones)


def _rarity_index(state: ForgeState) -> NameIndex | None:
    """The Arena rarity index for the current format, built once from bulk and
    cached on the state per FORMAT (the pool's own memo shares it across states).
    Keyed by format rather than legality key because Competitive Brawl shares
    Historic Brawl's ``brawl`` key but admits the cards that key marks banned."""
    if state.bulk_path is None:
        return None
    fmt = state.session.format
    cached = state.rarity_index.get(fmt)
    if cached is None:
        pool = CardPool.load(state.bulk_path)
        cached = pool.rarity_index(FORMATS[fmt], arena_only=True)
        state.rarity_index[fmt] = cached
    return cached


def wildcard_cost(state: ForgeState) -> dict | None:
    """Arena wildcard cost for a DIGITAL build — ``{mythic, rare, uncommon, common}``:
    each deck row's served shortfall (:func:`coverage`), summed by its Arena rarity,
    so the footer total is exactly the sum of the rows. ``None`` for paper builds
    (USD cost), an opened pool (owned outright) or with no bulk."""
    if is_paper(state) or state.bulk_path is None:
        return None
    if state.session.pool_bounded:
        return None  # an opened pool is owned; nothing is crafted
    rarity_index = _rarity_index(state)
    if not rarity_index:
        return None
    owned = owned_quantities(state)
    totals = {"mythic": 0, "rare": 0, "uncommon": 0, "common": 0}
    # Every row costs, the companion included: on Arena it is a sideboard card you
    # must own (a Historic / Timeless build's Yorion is crafted like any other). A card
    # absent from the Arena rarity index (not on Arena) costs nothing we can price.
    for entry in _deck_rows(state):
        listed = rarity_index.get(entry["name"].lower())
        if listed is not None:
            rarity = listed["rarity"]
            short = coverage(state, owned, entry).short
            totals[rarity] = totals.get(rarity, 0) + short
    return totals


# Commander discovery (ADR-0018). "Best" is intent-driven, never EDHREC popularity:
# Support depth (how much of a commander's strategy your collection already fills) or
# Novelty (signal rarity), each over the active Collection slot.
# --- builds and lanes -----------------------------------------------------------


def switch_build(
    state: ForgeState, session: DeckSession, *, name: str, build_id: str | None = None
) -> None:
    """Make ``session`` the live build — a new one, an import, a load, or the fresh
    build that replaces a deleted one. ``build_id=None`` mints an id.

    The ONE place the hub becomes a different build, because the four things that
    change together must: the session, its id, its name, and the per-build runtime
    lanes. ``agent_avenues`` (lanes the session-agent posted) and
    ``focused_avenue_ids`` (the human's focus pins) are scoped to one deck — carried
    across a switch they surface the prior commander's lanes and scope candidate
    scoring (``scoring_basis``) to another build's pins."""
    state.session = session
    state.build_id = build_id or uuid.uuid4().hex[:8]
    state.build_name = name
    state.agent_avenues.clear()
    state.focused_avenue_ids.clear()
    state.seed_undo = None


def add_agent_avenue(
    state: ForgeState, *, label: str, description: str, search: dict
) -> dict:
    """Post a session-agent lane onto the live build; returns the new avenue."""
    state.agent_avenue_seq += 1
    avenue = {
        "id": f"agent:{state.agent_avenue_seq}",
        "label": label,
        "description": description,
        "scope": "",
        "source": "agent",
        "search": search,
    }
    state.agent_avenues.append(avenue)
    return avenue


def remove_avenue(state: ForgeState, avenue_id: str) -> None:
    """Drop an agent lane — and its focus pin: a removed lane can't stay focused."""
    state.agent_avenues[:] = [a for a in state.agent_avenues if a["id"] != avenue_id]
    state.focused_avenue_ids.discard(avenue_id)


def toggle_avenue_focus(state: ForgeState, avenue_id: str) -> None:
    """Flip a lane's 'focused' pin (#2): the candidate ✦ score then counts only the
    focused lanes. A toggle, so the pin button can flip it either way."""
    if avenue_id in state.focused_avenue_ids:
        state.focused_avenue_ids.discard(avenue_id)
    else:
        state.focused_avenue_ids.add(avenue_id)


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


def staple_pool(state: ForgeState) -> list[dict]:
    """The curated 'good stuff' staples offered to this deck — the hardcoded staple
    list (see ``staples``) filtered to the deck's color identity AND format legality,
    resolved from the bulk index. Empty without bulk, and empty outside the Commander
    family — the list is curated for Commander (``staples``), and offered to a
    Legacy deck it would name Sol Ring. This is the candidate source for the
    always-present Staples avenue (a name list, not a search pattern)."""
    if not state.by_name or not state.session.fmt.has_commander:
        return []
    return staples.staples_for(
        deck_color_identity(state),
        state.by_name,
        fmt=state.session.fmt,
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


def _overflow_warnings(hd: HydratedDeck) -> list[dict]:
    """Two failure modes the shared ``legality_audit`` deliberately doesn't own, because
    they're build-surface concerns: a deck that has grown PAST its size cap (the mirror
    of the excluded ``deck_minimum`` — under is normal building, over is never legal;
    only an exact-size family HAS a cap, a constructed size is a floor — CR 100.2a),
    and card names that resolved to no Scryfall record (a typo or a failed paste-import,
    which ADR-0012 otherwise DROPs silently from the hydrated records)."""
    out: list[dict] = []
    max_cards = hd.format.size_cap
    if max_cards is not None:
        # Commanders + maindeck only: the companion is revealed from outside the
        # game and is not part of the deck or sideboard (CR 702.139a-b), so it
        # never counts toward the exact Commander-family size (CR 903.5a).
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
        for zone in ZONES
        for e in hd.deck.get(zone) or []
        if e.get("name") and e["name"] not in hd.by_name
    ]
    out.extend(
        {"category": "unimported", "message": f"did not import: {name}"}
        for name in unimported
    )
    return out


def _companion_message(v: dict) -> str:
    """One human-readable warning line for a ``check_companion`` violation dict —
    companion name, reason, and the governing CR cite, so the browser warning is
    self-explanatory without the structured audit payload."""
    reason = v.get("reason")
    if reason == "companion_multiple":
        names = ", ".join(v.get("names") or [])
        return (
            f"companion: more than one companion ({names}) — a player may "
            f"reveal at most one (CR 103.2b)"
        )
    if reason == "companion_not_companion":
        return f"companion: {v.get('name')} has no companion ability (CR 702.139a)"
    offender = f" [{v['card']}]" if v.get("card") else ""
    return (
        f"companion: {v.get('name')} condition not met{offender} — "
        f"{v.get('detail')} (CR {v.get('rule', '702.139b')})"
    )


def legality_warnings(hd: HydratedDeck, *, audit: dict | None = None) -> list[dict]:
    """The live warning list: every audited category, the size cap where the family
    has one, and the companion checks. ``hd.format`` carries the build's effective
    size, so the cap is derived here — no caller passes one. ``audit`` is a
    ``legality_audit`` result the caller already has (finalize reads it twice)."""
    audit = legality_audit(hd) if audit is None else audit
    violations = audit.get("violations") or {}
    return (
        [
            _violation_message(cat, v)
            for cat in _AUDIT_CATEGORIES
            for v in (violations.get(cat) or [])
        ]
        + _overflow_warnings(hd)
        # Companion violations (the shared ``check_companion``: max one, must
        # have the ability, condition met over commanders + maindeck — with
        # deck_minimum=None for the exact-size Commander family, CR 903.5a /
        # 903.12d, and the format's minimum for constructed) surface as warnings
        # like deck_maximum: through /api/audit and the finalize gate
        # (legality_status FAIL), never a hard error.
        + [
            {"category": "companion", "message": _companion_message(v)}
            for v in (violations.get("companion") or [])
        ]
    )


class DeckRuleError(ValueError):
    """A deck rule rejected the request (a printing that isn't the card's, a second
    companion, an unsupported import format). The transport adapter maps it to one
    400 in one place; engine tests assert on it directly (ADR-0013)."""


# --- land plans -----------------------------------------------------------------


def _apply_land_plan(state: ForgeState, plan: dict) -> dict[str, dict[str, int]]:
    """Apply a ``reconcile_basic_lands`` plan to the session: removals first, then
    adds — only basics the loaded index can hydrate. Returns what was applied."""
    applied: dict[str, dict[str, int]] = {"add": {}, "remove": {}}
    for name, qty in plan["remove"].items():
        state.session.remove(name, qty, zone="cards")
        applied["remove"][name] = qty
    for name, qty in plan["add"].items():
        if name in state.by_name:
            state.session.add(name, qty, zone="cards")
            applied["add"][name] = qty
    return applied


def balance_lands(state: ForgeState) -> dict[str, dict[str, int]]:
    """Fix the mana base: add basics up to the land band's floor and rebalance the
    basics to color demand (swapping over- for under-produced colors at the current
    count when already at/above the floor). Mutates the session; returns the
    applied ``{add, remove}``."""
    return _apply_land_plan(state, reconcile_basic_lands(hydrate_session(state)))


def trim_lands(state: ForgeState) -> dict[str, dict[str, int]]:
    """The FLOOD remedy: trim basics back down to the land band's top, over-produced
    colors first. A no-op (empty plan) at or under the top — soft, never a gate,
    because an all-lands combo deck is a legitimate build (CONTEXT: Flood line)."""
    hd = hydrate_session(state)
    audit = mana_audit(hd)
    top = audit["land_band"]["top"]
    if audit["land_count"] <= top:
        return {"add": {}, "remove": {}}
    return _apply_land_plan(state, reconcile_basic_lands(hd, target_total=top))


# --- format / medium / size / zone rules -----------------------------------------


def check_format(fmt: str) -> None:
    """The format rule: a build is one of the formats the table declares (ADR-0045);
    every family the Format module knows is served."""
    if fmt not in FORMATS:
        raise DeckRuleError(f"unknown format: {fmt!r}")


def set_format(state: ForgeState, fmt: str) -> None:
    """Change the build's format (:func:`check_format`). The deck's cards are kept;
    everything format-dependent re-derives on the next snapshot. Crossing the
    pool boundary keeps the cards playable: entering a pool-bounded format with no
    pool yet pools everything the build holds (its sideboard becomes derived);
    leaving one stores the derived sideboard as a real one."""
    check_format(fmt)
    session = state.session
    was_pool = session.pool_bounded
    now_pool = FORMATS[fmt].pool_bounded
    if was_pool and not now_pool:
        # The unused pool becomes a stored sideboard; the pool is emptied (a
        # database-pooled format carries none — re-entering re-pools), and a seed's
        # undo goes with it (it held a deck drawn from that pool).
        session.replace_zone("sideboard", session.derived_sideboard())
        session.replace_zone("pool", {})
        state.seed_undo = None
    session.format = fmt
    if now_pool and not was_pool:
        session.pool_everything()


def set_medium(state: ForgeState, medium: str) -> None:
    """The medium rule: paper vs digital, only where the format is played that way
    (``Format.media``, ADR-0045). The medium drives the active Collection slot and
    the cost mode — digital → Arena slot + wildcards; paper → paper slot + USD
    (ADR-0018, amended)."""
    fmt = state.session.fmt
    if medium not in fmt.media:
        raise DeckRuleError(
            f"{fmt.name} is not played in {medium!r} (media: {', '.join(fmt.media)})"
        )
    state.session.set_medium(medium)


def set_deck_size(state: ForgeState, deck_size: int) -> None:
    """The deck-size rule, by family (ADR-0045): a constructed build takes any size
    its Format calls valid (a floor — an 80-card Yorion deck); a Commander-family
    build takes any size some format of the family may choose — only paper Historic
    Brawl honors a choice (60 or 100 are both legal paper "Brawl"), every other
    (format, medium) keeps its fixed size, so the override lies dormant until it
    applies. The guard is derived from the format table, never a hand-list."""
    fmt = state.session.fmt
    if fmt.size_is_minimum:
        if not fmt.is_valid_deck_size(deck_size):
            raise DeckRuleError(f"{deck_size} is not a valid {fmt.label} deck size")
    else:
        choices = family_size_choices(fmt.family)
        if deck_size not in choices:
            raise DeckRuleError(f"deck size must be one of {list(choices)}")
    state.session.set_deck_size(deck_size)


def check_zone(zone: str) -> None:
    """The zone rule: a request names one of the deck's zones (``ZONES``)."""
    if zone not in ZONES:
        raise DeckRuleError(f"unknown zone {zone!r}")


def check_zone_open(state: ForgeState, zone: str) -> None:
    """The family's zone rule: only a format with a command zone has commanders;
    only a pool-bounded format has a pool, and there the sideboard is DERIVED (the
    pool less the deck) — nothing is added to it, a card is cut from the deck or
    added to the pool. A sideboard the family caps at zero is NOT refused here —
    the size audit warns (``sideboard_size``), so a build in progress may park
    cards while swapping."""
    check_zone(zone)
    fmt = state.session.fmt
    if zone == "commanders" and not fmt.has_commander:
        raise DeckRuleError(f"{fmt.label} has no command zone")
    if zone == "pool" and not fmt.pool_bounded:
        raise DeckRuleError(f"{fmt.label} has no pool — only sealed / draft do")
    if zone == "sideboard" and fmt.pool_bounded:
        raise DeckRuleError(
            "the sideboard is the unused pool — cut a card from the deck to "
            "sideboard it, or add it to the pool"
        )


def check_pool_remove(state: ForgeState, name: str, qty: int, zone: str) -> None:
    """The pool-bounded remove rule: a pool copy the deck still runs cannot leave
    the pool (cut it from the deck first), and the derived sideboard is never
    removed from directly."""
    if not state.session.pool_bounded:
        return
    if zone == "sideboard":
        raise DeckRuleError(
            "the sideboard is the unused pool — remove the card from the pool instead"
        )
    if zone == "pool":
        left = state.session.quantity_of(name, zone="pool") - qty
        used = state.session.quantity_of(name, zone="cards")
        if left < used:
            raise DeckRuleError(
                f"{name}: the deck runs {used}; cut it from the deck before "
                "removing it from the pool"
            )


# --- copy limits -----------------------------------------------------------------


def copy_limit(state: ForgeState, record: dict) -> int | None:
    """How many copies of one card the build may run (``None`` = unlimited) — the
    audit's own ``card_copy_limit`` under the build's Format, so the hub and
    ``legality_audit.check_copy_limits`` cannot drift. In a pool-bounded build the
    limit IS what the pool holds (CR 100.2b: as many duplicates as the product
    included; basics unlimited) — so the one add rule is also pool containment."""
    fmt = state.session.fmt
    if fmt.pool_bounded:
        if is_basic_land(record):
            return None
        return state.session.quantity_of(record.get("name", ""), zone="pool")
    return card_copy_limit(record, fmt)


def copies_of(state: ForgeState, name: str) -> int:
    """The copies of ``name`` the build holds across EVERY zone: the copy limit spans
    the deck and the sideboard (CR 100.4a), the command zone (CR 903.5a: a Commander
    deck's singleton rule includes its commander), and the companion (a sideboard
    card on Arena). Wider than the audit's cards + sideboard count — the hub is the
    stricter of the two by design. In a pool-bounded build the copies are the main
    deck's (the pool is the limit, the derived sideboard the remainder)."""
    if state.session.pool_bounded:
        zones: tuple[str, ...] = ("cards", "companion")
    else:
        zones = ZONES
    return sum(state.session.quantity_of(name, zone=z) for z in zones)


def at_copy_limit(state: ForgeState, record: dict) -> bool:
    """Whether the build already runs every copy of this card it may — the one rule
    Find strips by, so a 2-of in a 4-of format stays findable."""
    limit = copy_limit(state, record)
    return limit is not None and copies_of(state, record.get("name", "")) >= limit


def check_copy_add(
    state: ForgeState, name: str, qty: int, *, zone: str = "cards"
) -> None:
    """The copy-limit rule for an add, raising ``DeckRuleError`` when ``qty`` more
    copies would exceed :func:`copy_limit`. Mirrors ``check_companion_add``: the hub
    never over-adds, so the SPA's stepper can't run past the format. An add to the
    pool itself is never limited — the pool IS the limit."""
    if zone == "pool":
        return
    record = state.by_name.get(name)
    if record is None:
        return  # the route 404s an unknown name before any rule
    limit = copy_limit(state, record)
    if limit is None:
        return
    have = copies_of(state, name)
    if have + qty > limit:
        fmt = state.session.fmt
        if fmt.pool_bounded:
            raise DeckRuleError(
                f"{name}: not in the pool (CR 100.2b)"
                if limit == 0
                else f"{name}: the pool holds {limit} and the deck runs {have}"
            )
        raise DeckRuleError(
            f"{name}: {have + qty} copies would exceed the {fmt.label} limit of "
            f"{limit} (you have {have})"
        )


def add_card(state: ForgeState, name: str, qty: int, *, zone: str) -> None:
    """Add copies to a zone under every rule: the zone is one the family has, the
    companion zone's own rules, the copy limit (which is pool containment in a
    pool-bounded build). Raises ``DeckRuleError``; an unknown name is the route's
    404 (a lookup miss, not a rule)."""
    check_zone_open(state, zone)
    if zone == "companion":
        check_companion_add(state, name, qty)
    else:
        check_copy_add(state, name, qty, zone=zone)
    state.session.add(name, qty, zone=zone)


def remove_card(state: ForgeState, name: str, qty: int, *, zone: str) -> None:
    """Remove copies from a zone under the pool-bounded rules (a pool copy the deck
    runs stays; the derived sideboard is never removed from directly)."""
    check_zone(zone)
    check_pool_remove(state, name, qty, zone)
    state.session.remove(name, qty, zone=zone)


def move_card(
    state: ForgeState, name: str, *, from_zone: str, to_zone: str, qty: int = 1
) -> None:
    """Move ``qty`` copies of ``name`` between two zones in one step (main deck ⇄
    sideboard, promote to commander, reveal as companion), carrying a pinned
    printing along. Every rule runs BEFORE the session changes, so a refused move
    leaves the build untouched. The copy limit is not consulted: a move keeps the
    build's total."""
    check_zone(from_zone)
    if from_zone == to_zone:
        raise DeckRuleError(f"{name} is already in {to_zone}")
    have = state.session.quantity_of(name, zone=from_zone)
    if have < qty:
        raise DeckRuleError(f"{name}: only {have} in {from_zone}, cannot move {qty}")
    if state.session.pool_bounded:
        # The pool and its derived sideboard are one thing to move against: a card
        # leaves the deck into it (a remove) or enters the deck from it (an add the
        # pool bounds); the pool itself never changes by a move.
        unused = ("sideboard", "pool")
        if from_zone == "cards" and to_zone in unused:
            state.session.remove(name, qty, zone="cards")
            return
        if from_zone in unused and to_zone == "cards":
            check_copy_add(state, name, qty)
            state.session.add(name, qty, zone="cards")
            return
        if from_zone in unused and to_zone in unused:
            raise DeckRuleError(f"{name} is already in the pool")
    check_zone_open(state, to_zone)
    if to_zone == "companion":
        check_companion_add(state, name, qty)
    printing = state.session.printing_of(name, zone=from_zone)
    finish = state.session.finish_of(name, zone=from_zone)
    state.session.remove(name, qty, zone=from_zone)
    state.session.add(name, qty, zone=to_zone)
    if printing and state.session.printing_of(name, zone=to_zone) is None:
        state.session.set_printing(name, printing, zone=to_zone, finish=finish)


# --- the companion zone ---------------------------------------------------------


def check_companion_add(state: ForgeState, name: str, qty: int) -> None:
    """The zone rules for adding to the companion zone, raising ``DeckRuleError``:
    (a) at most ONE card may occupy it (CR 103.2b) — an occupied zone is refused;
    the user removes the old occupant first, it is never silently replaced; (b) the
    card must carry the companion ability (CR 702.139a), read off its record."""
    occupied = state.session.to_deck_dict().get("companion") or []
    if occupied:
        raise DeckRuleError(
            f"companion zone already holds {occupied[0]['name']}; a player may "
            "reveal at most one companion (CR 103.2b) — remove it first"
        )
    if qty != 1:
        raise DeckRuleError(
            "the companion zone holds exactly one card (CR 103.2b: at most one "
            "companion)"
        )
    record = state.by_name.get(name)
    if record is None or not is_companion(record):
        raise DeckRuleError(f"{name} has no companion ability (CR 702.139a)")


def settle_companion_zone(parsed: dict, by_name: Mapping[str, dict]) -> list[str]:
    """Route an imported list's companion zone in place: the FIRST plausible
    companion keeps the zone (an unknown name stays — it surfaces as ``unknown``
    like any other zone); overflow entries (CR 103.2b: at most one companion), extra
    copies, and cards the index PROVES have no companion ability (CR 702.139a) are
    demoted to ``cards`` with a warning, never dropped. Returns the warnings."""
    warnings: list[str] = []
    kept: list[dict] = []
    demoted: list[dict] = []
    for entry in parsed.get("companion") or []:
        record = by_name.get(entry.get("name", ""))
        if record is not None and not is_companion(record):
            demoted.append(entry)
            warnings.append(
                f"{entry['name']} has no companion ability (CR 702.139a); "
                "moved to the deck"
            )
        elif kept:
            demoted.append(entry)
            warnings.append(
                f"more than one companion listed; {entry['name']} moved to the "
                "deck (CR 103.2b: at most one companion)"
            )
        else:
            qty = int(entry.get("quantity", 1))
            if qty > 1:
                demoted.append({**entry, "quantity": qty - 1})
                warnings.append(
                    f"{entry['name']}: {qty} copies listed as companion; kept 1, "
                    f"moved {qty - 1} to the deck (CR 103.2b)"
                )
            kept.append({**entry, "quantity": 1})
    parsed["companion"] = kept
    if demoted:
        parsed["cards"] = list(parsed.get("cards") or []) + demoted
    return warnings


@dataclass(frozen=True)
class ImportedDeck:
    """What ``import_deck`` derived from a pasted list: the parsed dict (companion
    zone settled), a fresh session over it (printings pinned), the names the index
    cannot hydrate, and the companion warnings."""

    parsed: dict
    session: DeckSession
    unknown: list[str]
    warnings: list[str]


def import_deck(
    state: ForgeState, text: str, *, fmt: str, pool_only: bool = False
) -> ImportedDeck:
    """Parse a pasted / uploaded list IN-PROCESS (ADR-0017 — pure compute, no LLM)
    into a NEW session: companion zone settled (``settle_companion_zone``), printing
    suffixes pinned, unknown names collected. Never guesses a commander — an unmarked
    list lands in ``cards`` for the user to promote from. Does not touch
    ``state.session``; the transport adapter switches builds. Raises
    ``DeckRuleError`` for an unsupported format, an unparseable paste, or an empty
    list. For a pool-bounded format the list's cards become the opened pool
    (``pool_only``: the whole list, no deck yet — see ``parse_deck_text``)."""
    check_format(fmt)
    try:
        parsed = parse_deck_text(text, format=fmt, pool_only=pool_only)
    except Exception as exc:
        raise DeckRuleError(f"could not parse deck list: {exc}") from exc
    warnings = settle_companion_zone(parsed, state.by_name)
    session = DeckSession.from_deck_dict(parsed)
    if not session.card_names():
        raise DeckRuleError("no cards found in the imported list")
    # Entries that carried a "(SET) 123" suffix (and optional *F*/*E* finish
    # marker) auto-pin the matching printing; unresolvable pairs stay unpinned.
    pin_imported_printings(state, session, parsed)
    unknown = sorted(n for n in session.card_names() if n not in state.by_name)
    return ImportedDeck(
        parsed=parsed, session=session, unknown=unknown, warnings=warnings
    )


# --- printings ------------------------------------------------------------------


def printings_for(state: ForgeState, name: str) -> list[tuple[dict, int, int]]:
    """Every legal printing of *name* for the picker, each with its owned nonfoil /
    foil counts in the ACTIVE Collection slot (0 when unknown). Owned printings
    sort first (total owned desc, ties newest-first), then the rest newest-first.
    Empty for an unknown name."""
    record = state.by_name.get(name)
    oracle_id = record.get("oracle_id") if record else None
    prints = state.printings_by_oracle.get(oracle_id, []) if oracle_id else []
    detail = owned_printing_detail(state, name) or {}
    rows: list[tuple[dict, int, int]] = []
    for p in prints:
        key = ((p.get("set") or "").lower(), str(p.get("collector_number") or ""))
        nonfoil, foil = detail.get(key, (0, 0))
        rows.append((p, nonfoil, foil))
    # Stable sort over the newest-first base order: the owned block first (by total
    # owned desc, ties stay newest-first), then unowned newest-first unchanged.
    rows.sort(key=lambda r: (0 if r[1] + r[2] > 0 else 1, -(r[1] + r[2])))
    return rows


def choose_printing(
    state: ForgeState,
    name: str,
    printing_id: str | None,
    *,
    zone: str,
    finish: str | None,
) -> None:
    """Pin (or clear, with a null id) the printing for *name* in *zone*. The chosen
    printing drives the card's image / price / export set, never its gameplay text.
    Validated against the card's own printings so a stray id can't pin a wrong
    card's art, and a finish only rides a pinned printing that was produced in it
    (its ``finishes`` list). Raises ``DeckRuleError``; mutates the session."""
    chosen: dict | None = None
    if printing_id is not None:
        record = state.by_name.get(name)
        oracle_id = record.get("oracle_id") if record else None
        chosen = next(
            (
                p
                for p in state.printings_by_oracle.get(oracle_id or "", [])
                if p.get("id") == printing_id
            ),
            None,
        )
        if chosen is None:
            raise DeckRuleError(f"not a printing of {name!r}")
    if finish is not None:
        if chosen is None:
            raise DeckRuleError("finish requires a chosen printing")
        if finish not in FOIL_FINISHES or finish not in (chosen.get("finishes") or []):
            raise DeckRuleError(f"printing {printing_id!r} has no {finish!r} finish")
    state.session.set_printing(name, printing_id, zone=zone, finish=finish)


def export_deck_dict(state: ForgeState) -> dict:
    """The session as a parsed-deck dict with each chosen printing resolved to its
    ``set`` / ``collector_number`` (the exporters' ``(SET) <collector#>`` suffix and
    the JSON export's printing identity). A no-op for default printings."""
    deck = state.session.to_deck_dict()
    for zone in ZONES:
        for entry in deck.get(zone) or []:
            record = state.printing_by_id.get(entry.get("printing_id") or "")
            if record is not None:
                entry["set"] = record.get("set")
                entry["collector_number"] = record.get("collector_number")
    return deck


# --- tune -----------------------------------------------------------------------


def pool_records(hd: HydratedDeck) -> list[dict]:
    """The distinct records of a build's opened pool."""
    return hd.deck_records(zones=("pool",))


def pool_owned(state: ForgeState) -> dict[str, int] | None:
    """A pool-bounded build's pool as name → copies (what the tuner may add and owns
    outright), or None for any other family."""
    if not state.session.pool_bounded:
        return None
    return dict(state.session.quantities("pool"))


def search_for(state: ForgeState, hd: HydratedDeck) -> Callable[..., list[dict]]:
    """The candidate search for THIS build: the bulk-backed ``state.search_fn`` for
    a format whose card pool is the database, or — for a pool-bounded build — the
    same filter implementation (``card_search.filter_records``) over the opened
    pool's records, so Find and the tuner search the pool with the search's own
    semantics and never name a card the builder did not open."""
    if not state.session.pool_bounded:
        return state.search_fn
    return card_search.pool_search_fn(pool_records(hd), state.session.fmt)


def pool_readout(state: ForgeState, hd: HydratedDeck) -> dict | None:
    """The snapshot's pool panel for a pool-bounded build: its size, how much is
    unused, and every colour pair it supports on equal footing
    (``set_scan.pool_color_pairs``); None for any other family."""
    if not state.session.pool_bounded:
        return None
    unused = state.session.derived_sideboard()
    return {
        "size": state.session.quantity_sum("pool"),
        "unused": sum(unused.values()),
        "color_pairs": pool_color_pairs(hd.deck_quantities(zones=("pool",))),
        # Whether the last seed can be undone (its replaced deck is still held).
        "seed_undo": state.seed_undo is not None,
    }


def set_scan_for(state: ForgeState, code: str) -> dict | None:
    """What set ``code`` holds (``set_scan.set_scan`` over the pool's set index),
    memoized per code; None for a code the bulk has no cards for. Requires bulk."""
    key = code.lower()
    if key not in state.set_scans:
        assert state.bulk_path is not None  # the route checks bulk first
        records = CardPool.load(state.bulk_path).set_records(key)
        state.set_scans[key] = set_scan(records, code=key) if records else {}
    return state.set_scans[key] or None


# The curve a seeded 40 aims for (nonland slots by mana value) — the limited norm
# a first draft starts from; the builder tunes from there.
_SEED_CURVE = {1: 3, 2: 7, 3: 6, 4: 4, 5: 2, 6: 1}


def seed_build(state: ForgeState, colors: str) -> dict:
    """One click from a pool to a first 40 in ``colors`` (``_gauntlet_build``'s
    deterministic greedy fill over the pool's own cards plus basics) — a starting
    point the builder then tunes, never a finished deck, and never a card the pool
    does not hold. Replaces the main deck, keeping what it replaced for ONE
    ``undo_seed``. Raises ``DeckRuleError`` outside a
    pool-bounded build, for bad colours, or when the pool cannot fill the colours."""
    if not state.session.pool_bounded:
        raise DeckRuleError("only a sealed / draft build seeds a deck from a pool")
    wanted = [c for c in colors.upper() if c in "WUBRG"]
    if not wanted or len(wanted) != len(set(wanted)):
        raise DeckRuleError(
            f"colors must be one or more distinct of WUBRG, got {colors!r}"
        )
    hd = hydrate_session(state)
    # One record PER COPY (distinct objects: the builder's fallback fill dedups by
    # identity), so a 3-of in the pool may be picked three times and never four.
    records: list[dict] = []
    for entry, rec in hd.entries(zones=("pool",)):
        if rec is not None:
            records.extend(dict(rec) for _ in range(int(entry.get("quantity", 1))))
    deck_size = state.session.deck_size
    lands = limited_land_target(ramp_count=0, avg_cmc=0.0, deck_size=deck_size)
    outcome = build_gauntlet_deck(
        records,
        {
            "name": "".join(wanted),
            "colors": wanted,
            "shape": "midrange",
            "curve_target": _SEED_CURVE,
        },
        deck_size=deck_size,
        lands=lands,
    )
    if outcome.status != "ok":
        raise DeckRuleError(outcome.reason or "the pool cannot fill those colors")
    main: dict[str, int] = {}
    for entry in outcome.deck.get("main") or []:
        qty = int(entry["count"])  # the gauntlet builder's contract
        main[entry["name"]] = main.get(entry["name"], 0) + qty
    replaced = state.session.quantities("cards")
    state.seed_undo = replaced
    state.session.replace_zone("cards", main)
    return {
        "colors": "".join(wanted),
        "cards": sum(main.values()),
        "lands": lands,
        "replaced": sum(replaced.values()),
    }


def undo_seed(state: ForgeState) -> None:
    """Put back the main deck the last seed replaced — one level, quantities only
    (a printing pinned on a replaced card is not restored), and whatever was
    edited since the seed goes with it. The pool is untouched, so the restored deck
    is still drawn from it. Raises ``DeckRuleError`` outside a pool-bounded build
    or when there is nothing to undo."""
    if not state.session.pool_bounded:
        raise DeckRuleError("only a sealed / draft build has a seed to undo")
    if state.seed_undo is None:
        raise DeckRuleError("nothing to undo — no seed has replaced this deck")
    state.session.replace_zone("cards", state.seed_undo)
    state.seed_undo = None


SIGNALS_INDEX_JOB = "signals-index"
SIGNALS_INDEX_LABEL = "Building the card-signal index"


def record_busy(
    state: ForgeState, job: str, label: str, done: int, total: int
) -> dict | None:
    """The state transition behind the busy meter: fold one progress report from a
    long hub job (the one-time signals-index build; a cold commander-discovery
    sweep) into ``state.busy`` — done, total, and a time-left estimate from the
    pace so far — and return it (None once the job has finished, which also
    clears it). ONE meter, first job wins: while a job is in flight a report from
    a different ``job`` id is ignored (``state.busy`` unchanged, returned as is),
    so two concurrent passes (a launch warm and a foreground discover) can never
    fight over the bar or clear each other's. Pure state; the transport adapter
    owns the broadcast."""
    now = time.monotonic()
    prior = state.busy
    if prior and prior.get("job") != job:
        return prior  # another job holds the meter until it finishes
    started = prior["started"] if prior and prior.get("started") else now
    finished = bool(total) and done >= total
    if finished:
        state.busy = None
        return None
    elapsed = now - started
    eta = (elapsed / done) * (total - done) if done and total else None
    state.busy = {
        "job": job,
        "label": label,
        "done": done,
        "total": total,
        "eta_s": None if eta is None else round(eta),
        "started": started,
    }
    return state.busy


def tune_params(
    state: ForgeState,
    *,
    budget: float | None,
    wildcard_budget: dict[str, int] | None,
    max_swaps: int,
    shape_override: str | None,
    suggest_commander: bool,
    exclude: Collection[str] = (),
) -> TuneParams:
    """The tuner's parameters for THIS build — transport only: the medium and both
    purses go through as-is, and ``tune`` asks the Format which currency and which
    candidate pool the medium means (ADR-0045). ``max_swaps`` is capped high enough
    to FILL a near-empty deck (an under-sized build can need ~40+ adds to reach 100).
    ``exclude`` is the adds the builder rejected this session — the browser holds
    the list per build and sends it with every run, so a rejected card's slot is
    re-sourced from the next candidate.
    """
    return TuneParams(
        budget=budget,
        wildcard_budget=wildcard_budget,
        max_swaps=max(0, min(max_swaps, 99)),
        shape_override=shape_override,
        suggest_commander=suggest_commander,
        medium=state.session.medium,
        exclude=frozenset(exclude),
    )


def finalize_state(state: ForgeState) -> dict:
    """The finalize REPORT (not the gating decision — the route owns the override).
    ``below_minimum`` is the one hard fact a size-minimum family adds: a deck under
    its CR floor is illegal, not a judgment call, so the route never lets an
    override lift it (the land gate stays overridable)."""
    hd = hydrate_session(state)
    mana = mana_audit(hd)
    avg_cmc = deck_stats(hd).get("avg_cmc", 0.0)
    cheap_ca = sum(
        1
        for r in hd.expanded(zones=built_zones(state))
        if "card_draw" in role_of(r) and r.get("cmc", 0) <= 2
    )
    defensible = avg_cmc <= _DEFENSIBLE_AVG_CMC and cheap_ca >= _DEFENSIBLE_CHEAP_CA
    audit = legality_audit(hd)
    warnings = legality_warnings(hd, audit=audit)
    deck_minimum = None
    if hd.format.size_is_minimum:
        short = audit["violations"].get("deck_minimum") or []
        if short:
            deck_minimum = {
                "total": short[0]["total_cards"],
                "minimum": short[0]["minimum"],
            }
    return {
        "below_minimum": deck_minimum is not None,
        "deck_minimum": deck_minimum,
        "land_status": mana["land_band"]["status"],
        "land_count": mana["land_count"],
        "land_band": mana["land_band"],
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
        hydrated, commander_names, resolve_object=state.object_resolver
    )


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
    # Admit spoiled-but-unreleased cards (pre-release brewing). WIDENS the pool rather
    # than narrowing it, so it is deliberately not part of has_user_filters: ticking it
    # alone must not turn an idle Find into a whole-vault dump.
    include_unreleased: bool = False
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
    candidate-pipeline extraction ADR-0013 parked. Lane searches are scoped to
    ``deck_colors`` (the identity under a commander, the castable colors otherwise).
    Three branches on focus state:

    * FOCUSED avenues → OR-merge each lane's pool (a Staples lane resolves the curated
      name pool via ``staple_pool``; others ``search_fn`` the lane's ``explore_filters``
      base, AND-refined by the user's filters), score against the focused lanes, rank
      (with color-widening when a focused avenue carries it, ADR-0019).
    * no focus but user FILTERS → a manual ``search_fn`` scored against everything.
    * neither → an empty page (an idle prompt, not the whole vault).

    Strips cards the deck already runs every allowed copy of (``at_copy_limit``: a
    singleton's one, a 4-of's four, a basic's never), then returns the requested
    window of ranked rows. The route serializes the rows and annotates ownership;
    this stops at ranked records.
    """
    fmt = state.session.format
    ci = deck_colors(state)
    hd = hydrate_session(state)
    deck_records = hd.deck_records()
    sigs = ranked_deck_signals(state, deck_records)
    all_avenues = avenues(state, deck_records)
    focused = [a for a in all_avenues if a.get("focused")]
    search = search_for(state, hd)

    if focused:
        pool: dict[str, dict] = {}
        for av in focused:
            if (av.get("search") or {}).get("staples"):
                found = staple_pool(state)
            else:
                base = explore_filters(av["search"], color_identity=ci, fmt=fmt)
                found = search(
                    limit=_FIND_POOL,
                    paper_only=FORMATS[fmt].paper_only(state.session.medium),
                    include_unreleased=params.include_unreleased,
                    **refine_filters(base, params),
                )
            for card in found:
                cname = card.get("name")
                if cname:
                    pool.setdefault(cname, card)
        cands = [c for c in pool.values() if not at_copy_limit(state, c)]
        active, avs = scoring_basis(state, deck_records, sigs, focused)
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
        records = search(
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
            # The pool follows the BUILD (its format under its medium), not the
            # filter's format: a paper table filtering by another format still buys
            # paper printings. No format filter → no pool restriction, as before.
            paper_only=params.format is not None
            and state.session.fmt.paper_only(state.session.medium),
            include_unreleased=params.include_unreleased,
            preset_names=tuple(params.presets),
            is_commander_filter=params.is_commander,
            sort=params.sort,
            limit=_FIND_POOL,
            offset=0,
        )
        cands = [c for c in records if not at_copy_limit(state, c)]
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

    hd = hydrate_session(state)
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


def budgets(state: ForgeState) -> dict:
    """The deck rule behind ``GET /api/budgets``: the family's template rows over
    the main deck (a sideboard fills no slot), lands from the mana audit's band."""
    hd = hydrate_session(state)
    return banded_slot_budgets(
        hd.expanded(zones=("cards",)),
        mana_audit(hd)["land_band"],
        deck_size=state.session.deck_size,
        template=template_for(hd.format.family),
    )


def snapshot(state: ForgeState) -> dict:
    """The full canonical snapshot the SPA renders — the engine's composition root.
    Builds ONE HydratedDeck and threads it to every sub-analysis, so a request hits the
    bulk index once. Pure read of state; never mutates, publishes, or autosaves."""
    hd = hydrate_session(state)
    stats = deck_stats(hd)
    owned = owned_quantities(state)
    mana = mana_audit(hd)
    fmt = hd.format
    return {
        "build_id": state.build_id,
        "build_name": state.build_name,
        # The long hub job in flight (the first-launch signals-index build), so a
        # tab that opens mid-build shows the meter; None when idle.
        "busy": state.busy,
        # The format table the SPA's pickers read (labels, media, size choices) — the
        # Format is the one authority; the SPA never mirrors it (ADR-0045).
        "format_options": format_options(),
        "deck": views.deck_view(
            state,
            owned,
            functools.partial(printing_owned, state),
            functools.partial(copy_limit, state),
            functools.partial(coverage, state, owned),
        ),
        "stats": stats,
        # Commander brackets are WotC's multiplayer-Commander system: a constructed
        # build has none, and the SPA drops the pill on null.
        "bracket": (
            detect_bracket(hd.deck_records(), stats.get("avg_cmc", 0.0))
            if fmt.has_commander
            else None
        ),
        # The colors Find scopes lane searches to (identity or castable, by family).
        "deck_colors": deck_colors(state),
        "mana": mana,
        "budgets": banded_slot_budgets(
            hd.expanded(zones=("cards",)),
            mana["land_band"],
            deck_size=state.session.deck_size,
            template=template_for(fmt.family),
        ),
        # The counted deck (commanders + main deck): a sideboard or an opened pool
        # never shapes the avenues.
        "signals": [
            views.signal_view(s) for s in ranked_deck_signals(state, hd.deck_records())
        ],
        "avenues": avenues(state, hd.deck_records()),
        "warnings": legality_warnings(hd),
        "collection": collection_summary(state, owned),
        "wildcards": wildcard_cost(state),
        # The pool panel for a sealed / draft build (None otherwise).
        "pool": pool_readout(state, hd),
        # True when a second commander could still be added (CR 702.124 partner /
        # Background): the Find color pips stay unlocked so an off-identity partner is
        # findable; otherwise they lock to the commander's identity (A5).
        "partner_open": partner_search(state) is not None,
    }
