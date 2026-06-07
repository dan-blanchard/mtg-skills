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
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mtg_utils._deck_forge import engine, views
from mtg_utils._deck_forge.budgets import slot_budgets
from mtg_utils._deck_forge.exporters import export_as
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import search_filters, spec_for
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.deck_stats import deck_stats
from mtg_utils.mana_audit import mana_audit, reconcile_basic_lands
from mtg_utils.theme_presets import list_presets

VERSION = "0.1.0"
_PACKAGE_LIMIT = 12
# Ranked-candidate pool an avenue ranks over; the explore endpoint pages _PACKAGE_LIMIT
# at a time through it, so this bounds how deep "Show more" can go on one avenue.
_EXPLORE_POOL = 96

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


class ExplorePayload(BaseModel):
    label: str = "Exploration"
    search: dict = {}
    offset: int = 0


class NewBuildPayload(BaseModel):
    format: str = "commander"
    name: str = "Untitled"


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


def _autosave(state: ForgeState) -> None:
    if state.store is not None:
        state.store.save(state.build_id, state.build_name, state.session.to_deck_dict())


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
        return {"deck": views.deck_view(state)}

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return engine.snapshot(state)

    @app.get("/api/stats")
    async def stats() -> dict:
        return deck_stats(engine.hydrate(state))

    @app.get("/api/mana-audit")
    async def mana() -> dict:
        return mana_audit(engine.hydrate(state))

    @app.post("/api/deck/add")
    async def add(payload: AddPayload):
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

    @app.post("/api/deck/remove")
    async def remove(payload: RemovePayload):
        bad_zone = _zone_error(payload.zone)
        if bad_zone is not None:
            return bad_zone
        state.session.remove(payload.name, payload.qty, zone=payload.zone)
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/format")
    async def set_format(payload: FormatPayload):
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

    @app.post("/api/search")
    async def search(payload: SearchPayload):
        if not state.bulk_available:
            return _no_bulk()
        page = max(1, payload.limit)
        records = state.search_fn(
            color_identity=payload.color_identity,
            exact_colors=payload.exact_colors,
            oracle=payload.oracle,
            card_type=payload.type,
            name=payload.name,
            cmc_min=payload.cmc_min,
            cmc_max=payload.cmc_max,
            price_min=payload.price_min,
            price_max=payload.price_max,
            format=payload.format,
            paper_only=engine.paper_only(payload.format),
            preset_names=tuple(payload.presets),
            is_commander_filter=payload.is_commander,
            sort=payload.sort,
            limit=page + 1,  # over-fetch one to detect a next page
            offset=max(0, payload.offset),
        )
        has_more = len(records) > page
        fmt = state.session.format
        return {
            "results": [views.result_view(r, fmt) for r in records[:page]],
            "offset": payload.offset,
            "has_more": has_more,
        }

    @app.get("/api/card")
    async def card_by_name(name: str):
        """Resolve one card by exact name to a hydrated view (images / mana_cost /
        oracle / layout) so the UI can render a forge-friend card reference inline
        with art + the standard hover preview. Exact match first, then a
        case-insensitive fallback. Returns {"card": None} on a miss."""
        if not state.bulk_available:
            return _no_bulk()
        rec = state.by_name.get(name)
        if rec is None:
            low = name.lower()
            rec = next((r for n, r in state.by_name.items() if n.lower() == low), None)
        if rec is None:
            return {"card": None}
        return {"card": views.result_view(rec, state.session.format)}

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def gen():
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
        return {
            "budgets": slot_budgets(
                records, deck_size=engine.deck_size(state.session.format)
            )
        }

    @app.get("/api/packages")
    async def packages() -> dict:
        if not state.bulk_available:
            return _no_bulk()
        hd = engine.hydrate(state)
        sigs = engine.ranked_deck_signals(state, hd.records)
        ci = engine.deck_color_identity(state)
        fmt = state.session.format
        in_deck = set(state.session.card_names())
        out = []
        for sig in sigs:
            spec = spec_for(sig)
            if spec is None:
                continue
            if sig.key == "partner_background":
                psearch = engine.partner_search(state)
                if psearch is None:
                    continue  # no open partner slot → no partner package
                filters = {**psearch, "format": fmt}
            else:
                filters = search_filters(sig, color_identity=ci, fmt=fmt)
            found = state.search_fn(
                limit=40, paper_only=engine.paper_only(fmt), **filters
            )
            fresh = [c for c in found if c.get("name") not in in_deck]
            # Credit candidates for this signal's own avenue (its main search), not
            # just any agent-added avenues. Carry the structured serve classifier so a
            # cantrip is credited by TYPE, not a value permanent by "draw a card".
            self_avenue = engine.avenue_with_serve(
                {"label": spec.label, "search": dict(spec.search)}, spec.serve
            )
            active, avs = engine.scoring_basis(
                state, hd.records, sigs, [self_avenue, *state.agent_avenues]
            )
            ranked = rank_candidates(fresh, active_signals=active, avenues=avs)[
                :_PACKAGE_LIMIT
            ]
            out.append(
                {
                    "signal": engine.signal_dict(sig),
                    "candidates": [views.candidate_view(r, fmt) for r in ranked],
                }
            )
        return {"packages": out}

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
        _autosave(state)
        snap = engine.snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {"build_id": state.build_id, **snap}

    @app.post("/api/builds/load")
    async def builds_load(payload: LoadBuildPayload):
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

    @app.get("/api/export")
    async def export(fmt: str = "json"):
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
        avenue = {
            "id": f"agent:{len(state.agent_avenues) + 1}",
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

    @app.post("/api/explore")
    async def explore(payload: ExplorePayload) -> dict:
        if not state.bulk_available:
            return _no_bulk()
        fmt = state.session.format
        # The Staples avenue is a curated NAME list, not a search pattern: resolve it
        # directly from the bulk index (color-identity- and format-filtered) instead of
        # routing through search_fn, and credit it via its name serve so the staples
        # don't read as zero-fit irrelevant hits.
        if payload.search.get("staples"):
            found = engine.staple_pool(state)
            explored = {
                "label": payload.label,
                "search": payload.search,
                "serve": engine.staples_serve(),
            }
        else:
            filters = engine.explore_filters(
                payload.search,
                color_identity=engine.deck_color_identity(state),
                fmt=fmt,
            )
            found = state.search_fn(
                limit=_EXPLORE_POOL, paper_only=engine.paper_only(fmt), **filters
            )
            # Credit candidates for the avenue actually being explored, so a card the
            # avenue surfaced doesn't read as a zero-fit (irrelevant) hit.
            explored = {"label": payload.label, "search": payload.search}
        in_deck = set(state.session.card_names())
        fresh = [c for c in found if c.get("name") not in in_deck]
        hd = engine.hydrate(state)
        sigs = engine.ranked_deck_signals(state, hd.records)
        active, avs = engine.scoring_basis(
            state, hd.records, sigs, [explored, *state.agent_avenues]
        )
        ranked = rank_candidates(fresh, active_signals=active, avenues=avs)
        # Page _PACKAGE_LIMIT at a time through the ranked pool (stable order, so "Show
        # more" appends the next slice).
        offset = max(0, payload.offset)
        page = ranked[offset : offset + _PACKAGE_LIMIT]
        has_more = len(ranked) > offset + _PACKAGE_LIMIT
        return {
            "package": {
                "label": payload.label,
                "candidates": [views.candidate_view(r, fmt) for r in page],
                "offset": payload.offset,
                "has_more": has_more,
            }
        }

    @app.get("/api/audit")
    async def audit() -> dict:
        return {"warnings": engine.legality_warnings(engine.hydrate(state))}

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

    @app.get("/api/agent/next")
    async def agent_next(timeout: float = 25.0):  # noqa: ASYNC109
        req = await state.bridge.next_request(timeout=_clamp_timeout(timeout))
        if req is None:
            return Response(status_code=204)
        return {"request_id": req.id, "kind": req.kind, "payload": req.payload}

    @app.post("/api/agent/result")
    async def agent_result(payload: AgentResultPayload) -> dict:
        ok = state.bridge.complete(payload.request_id, payload.result)
        return {"ok": ok}

    @app.get("/api/agent/result/{request_id}")
    async def agent_result_wait(request_id: str, timeout: float = 25.0):  # noqa: ASYNC109
        result = await state.bridge.wait_result(
            request_id, timeout=_clamp_timeout(timeout)
        )
        if result is None:
            return Response(status_code=204)
        return {"result": result}

    @app.get("/api/combos")
    async def combos() -> dict:
        if state.combos_fn is None:
            return {
                "combos": [],
                "near_misses": [],
                "error": "combo lookup unavailable",
            }
        try:
            result = state.combos_fn(state.session.to_deck_dict())
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
