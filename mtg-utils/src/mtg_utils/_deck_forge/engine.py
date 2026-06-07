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

from pathlib import Path

from mtg_utils._deck_forge import staples, views
from mtg_utils._deck_forge.budgets import role_of, slot_budgets
from mtg_utils._deck_forge.signal_specs import Serve, spec_for
from mtg_utils._deck_forge.signals import Signal, extract_signals
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils.card_classify import valid_partner_search
from mtg_utils.deck_stats import deck_stats, detect_bracket
from mtg_utils.format_config import FORMAT_CONFIGS
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
            avenue_with_serve(
                {
                    "id": avenue_id,
                    "label": spec.label,
                    "description": spec.avenue,
                    "scope": sig.scope,
                    "source": "engine",
                    "search": main_search,
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
