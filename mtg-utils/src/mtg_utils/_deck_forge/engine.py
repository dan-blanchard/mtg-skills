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

from mtg_utils._deck_forge import views
from mtg_utils._deck_forge.budgets import role_of, slot_budgets
from mtg_utils._deck_forge.signal_specs import spec_for
from mtg_utils._deck_forge.signals import extract_signals
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils.card_classify import valid_partner_search
from mtg_utils.deck_stats import deck_stats, detect_bracket
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.legality_audit import legality_audit
from mtg_utils.mana_audit import mana_audit

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


def signal_dict(signal) -> dict:
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
        # The Partner / Background avenue is commander-specific: replace its generic
        # "any partner card" search with one scoped to cards that can LEGALLY be this
        # commander's second commander (CR 702.124). Skip it when there's no open slot.
        if sig.key == "partner_background":
            psearch = partner_search(state)
            if psearch is None:
                continue
            main_search = psearch
        seen_labels.add(spec.label)
        # Include subject so distinct tribes (Goblin vs Dwarf) get distinct avenues.
        suffix = f":{sig.subject}" if sig.subject else ""
        avenue_id = f"engine:{sig.key}:{sig.scope}{suffix}"
        out.append(
            {
                "id": avenue_id,
                "label": spec.label,
                "description": spec.avenue,
                "scope": sig.scope,
                "source": "engine",
                "search": main_search,
            }
        )
        # A signal can fan out into several precise sub-avenues (e.g. the land-creatures
        # theme: creature-lands / payoffs / animators).
        for i, extra in enumerate(spec.extras):
            if extra.label in seen_labels:
                continue
            seen_labels.add(extra.label)
            out.append(
                {
                    "id": f"{avenue_id}:{i}",
                    "label": extra.label,
                    "description": extra.avenue,
                    "scope": sig.scope,
                    "source": "engine",
                    "search": dict(extra.search),
                }
            )
    out.extend(state.agent_avenues)
    return out


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


def snapshot(state: ForgeState) -> dict:
    """The full canonical snapshot the SPA renders — the engine's composition root.
    Builds ONE HydratedDeck and threads it to every sub-analysis, so a request hits the
    bulk index once. Pure read of state; never mutates, publishes, or autosaves."""
    hd = hydrate(state)
    stats = deck_stats(hd)
    return {
        "build_id": state.build_id,
        "build_name": state.build_name,
        "deck": views.deck_view(state),
        "stats": stats,
        "bracket": detect_bracket(hd.records, stats.get("avg_cmc", 0.0)),
        "mana": mana_audit(hd),
        "budgets": slot_budgets(hd.expanded(), deck_size=deck_size(hd.format)),
        "signals": [signal_dict(s) for s in ranked_deck_signals(state, hd.records)],
        "avenues": avenues(state, hd.records),
        "warnings": legality_warnings(hd),
    }
