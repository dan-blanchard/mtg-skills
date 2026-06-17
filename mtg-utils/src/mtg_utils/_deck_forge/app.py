"""deck-forge FastAPI app factory — the transport adapter.

``build_app(state)`` wires the HTTP endpoints, the SSE stream, and (when a built SPA is
present) static file serving. Each route is a thin adapter: parse the payload, call the
``engine`` (deck analysis over ``ForgeState``) and ``views`` (wire serialization), apply
side effects (mutation / autosave / SSE publish), and return. Everything the app needs
is injected via ``ForgeState`` so the endpoints are testable without bulk data on disk;
the deck logic itself is tested directly through ``engine`` / ``views``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mtg_utils._deck_forge import collection, engine, views
from mtg_utils._deck_forge.budgets import slot_budgets
from mtg_utils._deck_forge.exporters import export_as
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils._tuner.tune import TuneParams
from mtg_utils._tuner.tune import tune as run_tune
from mtg_utils.deck_stats import deck_stats
from mtg_utils.mana_audit import mana_audit, reconcile_basic_lands
from mtg_utils.parse_deck import parse_deck_text
from mtg_utils.theme_presets import list_presets

VERSION = "0.1.0"

_PLACEHOLDER_INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>deck-forge</title></head>
<body style="font-family: system-ui; margin: 3rem; max-width: 40rem">
  <h1>deck-forge</h1>
  <p>Backend hub is running, but the built UI was not found.</p>
  <p>Build it with <code>cd deck-forge/frontend && npm install && npm run build</code>,
     or use the JSON API directly (<code>GET /api/snapshot</code>).</p>
</body>
</html>
"""


class AddPayload(BaseModel):
    name: str
    qty: int = 1
    zone: str = "cards"


class RemovePayload(BaseModel):
    name: str
    qty: int = 1
    zone: str = "cards"


class FormatPayload(BaseModel):
    format: str


class MediumPayload(BaseModel):
    medium: str  # "paper" | "digital"


class DeckSizePayload(BaseModel):
    deck_size: int  # 60 | 100 (paper Historic Brawl)


class AgentRequestPayload(BaseModel):
    kind: str
    payload: dict = {}


class AgentResultPayload(BaseModel):
    request_id: str
    result: dict


class FinalizePayload(BaseModel):
    override: bool = False


class AvenuePayload(BaseModel):
    label: str
    description: str = ""
    search: dict = {}


class NewBuildPayload(BaseModel):
    format: str = "commander"
    name: str = "Untitled"


class ImportDeckPayload(BaseModel):
    text: str
    format: str = "commander"
    name: str | None = None


class ImportCollectionPayload(BaseModel):
    text: str
    slot: str = "paper"


class ClearCollectionPayload(BaseModel):
    slot: str = "paper"


class DiscoverCommandersPayload(BaseModel):
    sort: str = "support"  # "support" (owned-support depth) | "novelty" (signal rarity)
    colors: str | None = None  # color-identity subset filter (e.g. "BG")
    theme: str | None = None  # a theme_presets lane to require
    limit: int = 24


class LoadBuildPayload(BaseModel):
    id: str


class RenameBuildPayload(BaseModel):
    id: str
    name: str


class SearchPayload(BaseModel):
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
    presets: list[str] = []
    is_commander: bool = False
    sort: str = "cmc-asc"
    limit: int = 25
    offset: int = 0


class TunePayload(BaseModel):
    budget: float | None = None  # None = owned-only zero-spend pass (paper / USD)
    # Digital builds budget in Arena wildcards, not dollars: a per-rarity allowance
    # {mythic, rare, uncommon, common}. When set (medium=digital) it replaces `budget`.
    wildcard_budget: dict[str, int] | None = None
    max_swaps: int = 0  # 0 = diagnose only
    shape_override: str | None = None
    suggest_commander: bool = False


def _autosave(state: ForgeState) -> None:
    if state.store is not None:
        state.store.save(state.build_id, state.build_name, state.session.to_deck_dict())


def _reset_runtime_lanes(state: ForgeState) -> None:
    """Clear per-build runtime lane state on a build switch.

    ``agent_avenues`` (lanes the session-agent posted) and ``focused_avenue_ids``
    (the human's focus pins) are scoped to one deck. Carrying them across a
    new/import/load would surface the prior commander's lanes and scope candidate
    scoring (``engine.scoring_basis``) to focus pins from another build.
    """
    state.agent_avenues.clear()
    state.focused_avenue_ids.clear()


def _find_params(payload: SearchPayload) -> engine.FindParams:
    """Adapt the transport ``SearchPayload`` to the engine's ``FindParams`` struct. The
    field mapping is the transport adapter's job, kept here so the engine's Find
    pipeline stays free of the FastAPI/pydantic payload type (ADR-0013 / ADR-0021)."""
    return engine.FindParams(
        color_identity=payload.color_identity,
        exact_colors=payload.exact_colors,
        oracle=payload.oracle,
        type=payload.type,
        name=payload.name,
        cmc_min=payload.cmc_min,
        cmc_max=payload.cmc_max,
        price_min=payload.price_min,
        price_max=payload.price_max,
        format=payload.format,
        presets=tuple(payload.presets),
        is_commander=payload.is_commander,
        sort=payload.sort,
        limit=payload.limit,
        offset=payload.offset,
    )


def _clamp_timeout(timeout: float) -> float:
    return max(0.0, min(timeout, 30.0))


def _zone_error(zone: str) -> JSONResponse | None:
    if zone not in views.VALID_ZONES:
        return JSONResponse({"error": f"unknown zone {zone!r}"}, status_code=400)
    return None


def _no_bulk() -> JSONResponse:
    return JSONResponse(
        {"error": "Scryfall bulk data not found — run `download-bulk` first."},
        status_code=503,
    )


def build_app(state: ForgeState, *, frontend_dist: Path | None = None) -> FastAPI:
    """Build the FastAPI app from an injected ``ForgeState``."""
    app = FastAPI(title="deck-forge", version=VERSION)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION, "bulk": str(state.bulk_available)}

    @app.get("/api/deck")
    async def deck() -> dict:
        return {"deck": views.deck_view(state, engine.owned_quantities(state))}

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return engine.snapshot(state)

    @app.get("/api/stats")
    async def stats() -> dict:
        return deck_stats(engine.hydrate(state))

    @app.get("/api/mana-audit")
    async def mana() -> dict:
        return mana_audit(engine.hydrate(state))

    @app.post("/api/deck/add", response_model=None)
    async def add(payload: AddPayload) -> dict | JSONResponse:
        bad_zone = _zone_error(payload.zone)
        if bad_zone is not None:
            return bad_zone
        if payload.name not in state.by_name:
            return JSONResponse(
                {"error": f"card not found: {payload.name!r}"}, status_code=404
            )
        state.session.add(payload.name, payload.qty, zone=payload.zone)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/remove", response_model=None)
    async def remove(payload: RemovePayload) -> dict | JSONResponse:
        bad_zone = _zone_error(payload.zone)
        if bad_zone is not None:
            return bad_zone
        state.session.remove(payload.name, payload.qty, zone=payload.zone)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/format", response_model=None)
    async def set_format(payload: FormatPayload) -> dict | JSONResponse:
        """Change the current build's format (commander / brawl / historic_brawl).
        The deck's cards are kept; everything format-dependent (deck size, land floor,
        legality, commander eligibility) re-derives on the next snapshot."""
        if payload.format not in engine.SUPPORTED_FORMATS:
            return JSONResponse(
                {"error": f"unsupported format: {payload.format!r}"}, status_code=400
            )
        state.session.format = payload.format
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/medium", response_model=None)
    async def set_medium(payload: MediumPayload) -> dict | JSONResponse:
        """Set paper vs digital for the build (Brawl / Historic Brawl). Drives the
        active Collection slot and the cost mode — digital → Arena slot + wildcards;
        paper → paper slot + USD (ADR-0018, amended)."""
        if payload.medium not in ("paper", "digital"):
            return JSONResponse(
                {"error": f"unknown medium: {payload.medium!r}"}, status_code=400
            )
        if payload.medium == "digital" and state.session.format == "commander":
            return JSONResponse({"error": "commander is paper-only"}, status_code=400)
        state.session.set_medium(payload.medium)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/deck-size", response_model=None)
    async def set_deck_size(payload: DeckSizePayload) -> dict | JSONResponse:
        """Choose 60 or 100 cards. Only paper Historic Brawl honors it (both are legal
        for paper "Brawl"); every other format/medium keeps its fixed size, so the
        override lies dormant until it applies."""
        if payload.deck_size not in (60, 100):
            return JSONResponse(
                {"error": "deck size must be 60 or 100"}, status_code=400
            )
        state.session.set_deck_size(payload.deck_size)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/balance-lands")
    async def balance_lands() -> dict:
        """Fix the mana base: add basics to reach the FAIL floor and rebalance the
        basics to match color demand (swapping over- for under-produced colors at the
        current count when already at/above the floor)."""
        plan = reconcile_basic_lands(engine.hydrate(state))
        applied: dict[str, dict[str, int]] = {"add": {}, "remove": {}}
        for name, qty in plan["remove"].items():
            state.session.remove(name, qty, zone="cards")
            applied["remove"][name] = qty
        for name, qty in plan["add"].items():
            if name in state.by_name:  # only add basics the loaded index can hydrate
                state.session.add(name, qty, zone="cards")
                applied["add"][name] = qty
        _autosave(state)
        snap = engine.snapshot(state)
        snap["balanced"] = applied
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/trim-lands")
    async def trim_lands() -> dict:
        """FLOOD remedy (#13): trim basics back down to the recommended land count
        (max of Burgess/Karsten), removing over-produced colors first. No-op when the
        deck is already at/under recommended. Soft — never blocks finalize, because an
        all-lands combo deck is a legitimate build (see CONTEXT Flood line)."""
        audit = mana_audit(engine.hydrate(state))
        recommended = audit["recommended_land_count"]
        applied: dict[str, dict[str, int]] = {"add": {}, "remove": {}}
        if audit["land_count"] > recommended:
            plan = reconcile_basic_lands(
                engine.hydrate(state), target_total=recommended
            )
            for name, qty in plan["remove"].items():
                state.session.remove(name, qty, zone="cards")
                applied["remove"][name] = qty
            for name, qty in plan["add"].items():
                if name in state.by_name:  # only basics the index can hydrate
                    state.session.add(name, qty, zone="cards")
                    applied["add"][name] = qty
            _autosave(state)
        snap = engine.snapshot(state)
        snap["trimmed"] = applied
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/handoff/goldfish", response_model=None)
    async def handoff_goldfish() -> dict | JSONResponse:
        """Run-here handoff (#6): goldfish the deck in-process and return the report
        inline — pure local compute (no LLM, no API key), so it works with no session
        attached. See ADR-0016."""
        if not state.bulk_available:
            return _no_bulk()
        if len(engine.hydrate(state).expanded(zones=("commanders", "cards"))) < 7:
            return JSONResponse(
                {"error": "Add more cards before goldfishing (need a full hand)."},
                status_code=400,
            )
        # The goldfish sim is heavy local compute (many simulated turns); offload it so
        # a long run keeps the loop responsive (same reason proxies is a sync route).
        return await run_in_threadpool(engine.goldfish_report, state)

    @app.post("/api/handoff/proxies", response_model=None)
    def handoff_proxies() -> Response:
        """Run-here handoff (#6): render a printable proxy PDF in-process (reportlab,
        no API key) and return it as a download. A SYNC route on purpose — FastAPI runs
        it in a threadpool, so the blocking PDF render + file I/O never stall the event
        loop. See ADR-0016."""
        if not state.bulk_available:
            return _no_bulk()
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            count = engine.render_proxies(state, tmp_path)
            if count == 0:
                return JSONResponse(
                    {"error": "No renderable cards — add some first."}, status_code=400
                )
            data = tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="proxies.pdf"'},
        )

    @app.get("/api/card", response_model=None)
    async def card_by_name(name: str) -> dict | JSONResponse:
        """Resolve one card by exact name to a hydrated view (images / mana_cost /
        oracle / layout) so the UI can render a forge-friend card reference inline
        with art + the standard hover preview. Looked up through the
        case- and diacritic-folding name index. Returns {"card": None} on a miss."""
        if not state.bulk_available:
            return _no_bulk()
        rec = state.by_name.get(name)
        if rec is None:
            return {"card": None}
        return {"card": views.result_view(rec, state.session.format)}

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            # Send current state immediately so a (re)connecting browser re-syncs —
            # e.g. after a server restart — with no manual refresh, and never keeps a
            # stale snapshot (which is how a removed avenue lingered client-side).
            yield f"data: {json.dumps(engine.snapshot(state))}\n\n"
            async for message in state.hub.stream():
                yield message

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/signals")
    async def signals() -> dict:
        sigs = engine.ranked_deck_signals(state, engine.hydrate(state).records)
        return {"signals": [engine.signal_dict(s) for s in sigs]}

    @app.get("/api/presets")
    async def presets() -> dict:
        # name → description, so the UI can offer a discoverable multiselect.
        return {
            "presets": [
                {"name": name, "description": desc}
                for name, desc in sorted(list_presets().items())
            ]
        }

    @app.get("/api/budgets")
    async def budgets() -> dict:
        records = engine.hydrate(state).expanded()
        return {"budgets": slot_budgets(records, deck_size=state.session.deck_size)}

    @app.get("/api/builds")
    async def builds() -> dict:
        return {
            "current": state.build_id,
            "builds": state.store.list() if state.store else [],
        }

    @app.post("/api/builds/new")
    async def builds_new(payload: NewBuildPayload) -> dict:
        state.session = DeckSession(payload.format)
        state.build_id = uuid.uuid4().hex[:8]
        state.build_name = payload.name or "Untitled"
        _reset_runtime_lanes(state)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {"build_id": state.build_id, **snap}

    @app.post("/api/builds/import", response_model=None)
    async def builds_import(payload: ImportDeckPayload) -> dict | JSONResponse:
        """Import an existing list as a NEW build (ADR-0017). Parse the raw pasted /
        uploaded text IN-PROCESS (pure compute — `parse_deck_text`, no LLM, no API key),
        seed a fresh session, switch to it. Never overwrites the live build; never
        guesses a commander — an unmarked list lands as a pile in ``cards`` that the
        user promotes from (the DeckList ★)."""
        if payload.format not in engine.SUPPORTED_FORMATS:
            return JSONResponse(
                {"error": f"unsupported format: {payload.format!r}"}, status_code=400
            )
        try:
            parsed = parse_deck_text(payload.text, format=payload.format)
        except Exception as exc:  # noqa: BLE001 — a bad paste is a 400, never a 500
            return JSONResponse(
                {"error": f"could not parse deck list: {exc}"}, status_code=400
            )
        session = DeckSession.from_deck_dict(parsed)
        if not session.card_names():
            return JSONResponse(
                {"error": "no cards found in the imported list"}, status_code=400
            )
        state.session = session
        state.build_id = uuid.uuid4().hex[:8]
        state.build_name = payload.name or "Imported deck"
        _reset_runtime_lanes(state)
        _autosave(state)
        # Names the bulk index can't hydrate (typos, un-owned tokens, Arena-only cards
        # when no bulk) surface as `unknown` cards; report them so the UI can warn.
        unknown = sorted(n for n in session.card_names() if n not in state.by_name)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {
            "build_id": state.build_id,
            "imported": {
                "commanders": len(parsed.get("commanders") or []),
                "cards": sum(
                    int(e.get("quantity", 1)) for e in (parsed.get("cards") or [])
                ),
                "unknown": unknown,
            },
            **snap,
        }

    @app.post("/api/builds/load", response_model=None)
    async def builds_load(payload: LoadBuildPayload) -> dict | JSONResponse:
        if state.store is None:
            return JSONResponse({"error": "no build store"}, status_code=400)
        record = state.store.load(payload.id)
        if record is None:
            return JSONResponse(
                {"error": f"build not found: {payload.id}"}, status_code=404
            )
        state.session = DeckSession.from_deck_dict(record.get("deck") or {})
        state.build_id = payload.id
        state.build_name = record.get("name", "Untitled")
        _reset_runtime_lanes(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {"build_id": state.build_id, **snap}

    @app.post("/api/builds/rename")
    async def builds_rename(payload: RenameBuildPayload) -> dict:
        if payload.id == state.build_id:
            # Rename the live deck and persist it under the new name immediately
            # (even if it had no file yet), so the name isn't lost without a mutation.
            state.build_name = payload.name
            _autosave(state)
        elif state.store is not None:
            record = state.store.load(payload.id)
            if record is not None:
                state.store.save(payload.id, payload.name, record.get("deck") or {})
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.delete("/api/builds/{build_id}")
    async def delete_build(build_id: str) -> dict:
        deleted = state.store.delete(build_id) if state.store is not None else False
        return {
            "deleted": deleted,
            "current": state.build_id,
            "builds": state.store.list() if state.store else [],
        }

    @app.post("/api/collection/import", response_model=None)
    async def collection_import(
        payload: ImportCollectionPayload,
    ) -> dict | JSONResponse:
        """Import a Collection into a slot (paper | arena), parsed IN-PROCESS (pure
        compute — `parse_deck_text`, no LLM/API key; ADR-0017). Ownership is then
        derived per snapshot from this slot, never stored on a build (ADR-0018)."""
        if payload.slot not in collection.SLOTS:
            return JSONResponse(
                {"error": f"unknown collection slot: {payload.slot!r}"}, status_code=400
            )
        try:
            pile = parse_deck_text(payload.text)
        except Exception as exc:  # noqa: BLE001 — a bad paste is a 400, never a 500
            return JSONResponse(
                {"error": f"could not parse collection: {exc}"}, status_code=400
            )
        engine.set_collection(state, payload.slot, pile)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {
            "slot": payload.slot,
            "size": collection.slot_sizes(state.collections).get(payload.slot, 0),
            **snap,
        }

    @app.post("/api/collection/clear", response_model=None)
    async def collection_clear(payload: ClearCollectionPayload) -> dict | JSONResponse:
        if payload.slot not in collection.SLOTS:
            return JSONResponse(
                {"error": f"unknown collection slot: {payload.slot!r}"}, status_code=400
            )
        engine.clear_collection(state, payload.slot)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/commanders/discover", response_model=None)
    async def commanders_discover(
        payload: DiscoverCommandersPayload,
    ) -> dict | JSONResponse:
        """Intent-ranked owned commanders from the active Collection slot (ADR-0018) —
        support-depth or novelty, theme/color filters, never EDHREC. Pure compute."""
        if not state.bulk_available:
            return _no_bulk()
        # Validate the theme like the sibling slot/format guards (a clean 400, not a
        # 500): theme_presets.matches raises KeyError on an unknown preset name.
        if payload.theme and payload.theme not in list_presets():
            return JSONResponse(
                {"error": f"unknown theme preset: {payload.theme!r}"}, status_code=400
            )
        slot = engine.active_slot(state)
        results = engine.discover_commanders(
            state,
            sort=payload.sort,
            colors=payload.colors,
            theme=payload.theme,
            limit=max(1, payload.limit),
        )
        return {
            "results": results,
            "sort": payload.sort,
            "active_slot": slot,
            "slot_size": collection.slot_sizes(state.collections).get(slot, 0),
        }

    @app.get("/api/export", response_model=None)
    async def export(fmt: str = "json") -> dict | JSONResponse:
        deck = state.session.to_deck_dict()
        if fmt == "json":
            return {"format": "json", "deck": deck}
        text = export_as(deck, fmt)
        if text is None:
            return JSONResponse(
                {"error": f"unknown export format: {fmt}"}, status_code=400
            )
        return {"format": fmt, "text": text}

    @app.post("/api/avenues")
    async def add_avenue(payload: AvenuePayload) -> dict:
        state.bridge.touch()
        state.agent_avenue_seq += 1
        avenue = {
            "id": f"agent:{state.agent_avenue_seq}",
            "label": payload.label,
            "description": payload.description,
            "scope": "",
            "source": "agent",
            "search": payload.search,
        }
        state.agent_avenues.append(avenue)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {"avenue": avenue, **snap}

    @app.delete("/api/avenues/{avenue_id}")
    async def remove_avenue(avenue_id: str) -> dict:
        state.agent_avenues[:] = [
            a for a in state.agent_avenues if a["id"] != avenue_id
        ]
        state.focused_avenue_ids.discard(avenue_id)  # a removed lane can't stay focused
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/avenues/{avenue_id}/focus")
    async def focus_avenue(avenue_id: str) -> dict:
        """Toggle a lane as 'focused' (#2): the candidate ✦ score then counts only the
        focused lanes. Idempotent toggle so the pin button can flip it either way."""
        if avenue_id in state.focused_avenue_ids:
            state.focused_avenue_ids.discard(avenue_id)
        else:
            state.focused_avenue_ids.add(avenue_id)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/find", response_model=None)
    async def find(payload: SearchPayload) -> dict | JSONResponse:
        """The unified Find surface (#5): one card-finding path that replaces separate
        search + explore (ADR-0015). The pipeline — focused-avenue OR-merge /
        filter-only manual search / idle, in-deck stripping, scoring, ranking, paging —
        lives in ``engine.find_candidates`` (the extraction ADR-0013 parked; ADR-0021).
        This route adapts the payload, projects the ranked rows via
        ``views.candidate_view``, and flags ownership (the active Collection slot,
        ADR-0018)."""
        if not state.bulk_available:
            return _no_bulk()
        page = engine.find_candidates(state, _find_params(payload))
        fmt = state.session.format
        results = [
            views.candidate_view(
                row, fmt, owned_qty=engine.owned_of(state, row["card"].get("name", ""))
            )
            for row in page.rows
        ]
        return {"results": results, "offset": page.offset, "has_more": page.has_more}

    @app.get("/api/audit")
    async def audit() -> dict:
        return {
            "warnings": engine.legality_warnings(
                engine.hydrate(state), max_cards=state.session.deck_size
            )
        }

    @app.post("/api/tune", response_model=None)
    async def tune(payload: TunePayload) -> dict | JSONResponse:
        """The deterministic Tune surface — a thin Transport adapter (ADR-0013) over the
        skill-agnostic tuner core (ADR-0023). ForgeState -> HydratedDeck -> tune(); no
        tuning logic here. Pure Deterministic core, so it runs hub-side with no agent
        attached. ``owned`` is the active Collection slot. Cost mode follows the medium:
        paper budgets in USD (``budget``); digital budgets in Arena wildcards
        (``wildcard_budget`` per rarity) — each unowned add costs one wildcard of its
        rarity, gated per tier (wildcards aren't interchangeable)."""
        if not state.bulk_available:
            return _no_bulk()
        fmt = state.session.format
        is_digital = state.session.medium == "digital"
        params = TuneParams(
            # Paper budgets in dollars; digital in per-rarity wildcards (a missing
            # wildcard_budget on a digital build → all-zero → owned-only pass).
            budget=None if is_digital else payload.budget,
            wildcard_budget=(payload.wildcard_budget or {}) if is_digital else None,
            # Cap high enough to FILL a near-empty deck (an under-sized build can need
            # ~40+ adds to reach 100); the old 25 cap silently clamped large requests
            # and starved the fill pass.
            max_swaps=max(0, min(payload.max_swaps, 99)),
            shape_override=payload.shape_override,
            suggest_commander=payload.suggest_commander,
            paper_only=engine.paper_only(fmt),
            medium=state.session.medium,
        )
        # run_tune does blocking work (a Commander Spellbook combos call + heavy bulk
        # searches); offload it to a worker thread so a slow combo lookup can't stall
        # the event loop and wedge the whole hub. Pure read of state, so thread-safe.
        return await run_in_threadpool(
            run_tune,
            engine.hydrate(state),
            search_fn=state.search_fn,
            params=params,
            # The WHOLE active Collection slot, not the deck-scoped owned map: the tuner
            # costs CANDIDATE adds (not in the deck yet), so it must see every card you
            # own as free — otherwise a zero wildcard budget fills nothing and owned
            # cards wrongly consume budget.
            owned=engine.owned_collection(state),
            combos_fn=state.combos_fn,
        )

    @app.post("/api/finalize")
    async def finalize(payload: FinalizePayload) -> dict:
        fs = engine.finalize_state(state)
        land_fail = fs["land_status"] == "FAIL"
        gated = land_fail and not payload.override
        return {
            "finalized": not gated,
            "gated": gated,
            "overridden": land_fail and payload.override,
            **fs,
        }

    @app.get("/api/agent/status")
    async def agent_status() -> dict:
        return {"attached": state.bridge.attached()}

    @app.post("/api/agent/heartbeat")
    async def agent_heartbeat() -> dict:
        state.bridge.touch()
        return {"ok": True}

    @app.post("/api/agent/request")
    async def agent_request(payload: AgentRequestPayload) -> dict:
        return {"request_id": state.bridge.submit(payload.kind, payload.payload)}

    @app.get("/api/agent/next", response_model=None)
    async def agent_next(timeout: float = 25.0) -> dict | Response:  # noqa: ASYNC109
        req = await state.bridge.next_request(timeout=_clamp_timeout(timeout))
        if req is None:
            return Response(status_code=204)
        return {"request_id": req.id, "kind": req.kind, "payload": req.payload}

    @app.post("/api/agent/result")
    async def agent_result(payload: AgentResultPayload) -> dict:
        ok = state.bridge.complete(payload.request_id, payload.result)
        return {"ok": ok}

    @app.get("/api/agent/result/{request_id}", response_model=None)
    async def agent_result_wait(
        request_id: str,
        timeout: float = 25.0,  # noqa: ASYNC109
    ) -> dict | Response:
        result = await state.bridge.wait_result(
            request_id, timeout=_clamp_timeout(timeout)
        )
        if result is None:
            return Response(status_code=204)
        return {"result": result}

    @app.get("/api/combos", response_model=None)
    async def combos() -> dict | JSONResponse:
        if state.combos_fn is None:
            return {
                "combos": [],
                "near_misses": [],
                "error": "combo lookup unavailable",
            }
        try:
            # Combos ride a network call (Spellbook); run it off the event loop so a
            # slow response can't stall the hub.
            result = await run_in_threadpool(
                state.combos_fn, state.session.to_deck_dict()
            )
        except Exception as exc:  # noqa: BLE001 — network/3rd-party; surface, don't crash
            return JSONResponse(
                {"error": f"combo lookup failed: {exc}"}, status_code=502
            )
        # Enrich each combo's cards with hydrated views (image/type/price) + an in-deck
        # flag, so the UI can render them as the same CardTiles as search/synergies.
        in_deck = set(state.session.card_names())
        fmt = state.session.format

        def _card_views(names: list[str]) -> list[dict]:
            return [
                views.combo_card_view(
                    name, state.by_name.get(name), in_deck=name in in_deck, fmt=fmt
                )
                for name in (names or [])
            ]

        for group in ("combos", "near_misses"):
            for combo in result.get(group) or []:
                combo["card_views"] = _card_views(combo.get("cards", []))
        return result

    _register_frontend(app, frontend_dist)
    return app


def _register_frontend(app: FastAPI, frontend_dist: Path | None) -> None:
    if frontend_dist and (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="spa")
        return

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _PLACEHOLDER_INDEX
