"""deck-forge FastAPI app factory.

``build_app(state)`` wires the deterministic endpoints, the SSE stream, and (when a
built SPA is present) static file serving. Everything the app needs is injected via
``ForgeState`` so the endpoints are testable without Scryfall bulk data on disk.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mtg_utils._deck_forge.budgets import role_of, slot_budgets
from mtg_utils._deck_forge.exporters import export_as
from mtg_utils._deck_forge.images import image_urls
from mtg_utils._deck_forge.ranking import rank_candidates
from mtg_utils._deck_forge.signal_specs import search_filters, spec_for
from mtg_utils._deck_forge.signals import aggregate_signals
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.deck_stats import deck_stats
from mtg_utils.legality_audit import legality_audit
from mtg_utils.mana_audit import mana_audit

VERSION = "0.1.0"
_VALID_ZONES = ("commanders", "cards", "sideboard")
_DECK_SIZE = {"commander": 100, "historic_brawl": 100, "brawl": 60}
_PAPER_FORMATS = {"commander"}
# deck_minimum is intentionally excluded: a deck-in-progress is always below the
# size minimum, so it's the normal building state, not a warning.
_AUDIT_CATEGORIES = (
    "format_legality",
    "commander_zone",
    "color_identity",
    "copy_limits",
    "sideboard_size",
)
_PACKAGE_LIMIT = 12
# Low-land defensibility heuristic (D8): a low avg CMC backed by cheap card advantage.
_DEFENSIBLE_AVG_CMC = 2.3
_DEFENSIBLE_CHEAP_CA = 8

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


class NewBuildPayload(BaseModel):
    format: str = "commander"
    name: str = "Untitled"


class LoadBuildPayload(BaseModel):
    id: str


class RenameBuildPayload(BaseModel):
    id: str
    name: str


def _autosave(state: ForgeState) -> None:
    if state.store is not None:
        state.store.save(state.build_id, state.build_name, state.session.to_deck_dict())


def _clamp_timeout(timeout: float) -> float:
    return max(0.0, min(timeout, 30.0))


class SearchPayload(BaseModel):
    color_identity: str | None = None
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


def _project(record: dict) -> dict:
    """Display fields for one real card record (no name/quantity)."""
    return {
        "type_line": record.get("type_line", ""),
        "mana_cost": record.get("mana_cost", ""),
        "cmc": record.get("cmc", 0.0),
        "color_identity": record.get("color_identity", []),
        "oracle_text": record.get("oracle_text", ""),
        "rarity": record.get("rarity", ""),
        "prices": record.get("prices", {}),
        "images": image_urls(record),
        "game_changer": record.get("game_changer"),
    }


def _card_view(name: str, qty: int, by_name: dict[str, dict]) -> dict:
    record = by_name.get(name)
    if record is None:
        return {"name": name, "quantity": qty, "unknown": True}
    return {"name": name, "quantity": qty, "unknown": False, **_project(record)}


def _deck_view(state: ForgeState) -> dict:
    deck = state.session.to_deck_dict()
    by_name = state.by_name
    return {
        "format": deck["format"],
        **{
            zone: [_card_view(e["name"], e["quantity"], by_name) for e in deck[zone]]
            for zone in _VALID_ZONES
        },
    }


def _zone_error(zone: str) -> JSONResponse | None:
    if zone not in _VALID_ZONES:
        return JSONResponse({"error": f"unknown zone {zone!r}"}, status_code=400)
    return None


def _snapshot(state: ForgeState) -> dict:
    deck = state.session.to_deck_dict()
    hydrated = state.session.hydrated(state.by_name)
    return {
        "build_id": state.build_id,
        "build_name": state.build_name,
        "deck": _deck_view(state),
        "stats": deck_stats(deck, hydrated),
        "mana": mana_audit(deck, hydrated),
        "budgets": slot_budgets(
            state.session.hydrated_expanded(state.by_name),
            deck_size=_deck_size(deck["format"]),
        ),
        "signals": [_signal_dict(s) for s in aggregate_signals(hydrated)],
        "avenues": _avenues(state, hydrated),
        "warnings": _legality_warnings(state),
    }


def _deck_size(fmt: str) -> int:
    return _DECK_SIZE.get(fmt, 100)


def _paper_only(fmt: str | None) -> bool:
    return fmt in _PAPER_FORMATS


def _color_identity(state: ForgeState) -> str:
    """Union of the commanders' color identities (the deck's color identity)."""
    colors: set[str] = set()
    for entry in state.session.to_deck_dict()["commanders"]:
        record = state.by_name.get(entry["name"])
        if record:
            colors.update(record.get("color_identity", []))
    return "".join(sorted(colors))


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


def _legality_warnings(state: ForgeState) -> list[dict]:
    audit = legality_audit(
        state.session.to_deck_dict(), state.session.hydrated(state.by_name)
    )
    violations = audit.get("violations") or {}
    return [
        _violation_message(cat, v)
        for cat in _AUDIT_CATEGORIES
        for v in (violations.get(cat) or [])
    ]


def _finalize_state(state: ForgeState) -> dict:
    deck = state.session.to_deck_dict()
    hydrated = state.session.hydrated(state.by_name)
    mana = mana_audit(deck, hydrated)
    avg_cmc = deck_stats(deck, hydrated).get("avg_cmc", 0.0)
    cheap_ca = sum(
        1
        for r in state.session.hydrated_expanded(state.by_name)
        if "card_draw" in role_of(r) and r.get("cmc", 0) <= 2
    )
    defensible = avg_cmc <= _DEFENSIBLE_AVG_CMC and cheap_ca >= _DEFENSIBLE_CHEAP_CA
    warnings = _legality_warnings(state)
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


def _signal_dict(signal) -> dict:
    spec = spec_for(signal)
    return {
        "key": signal.key,
        "scope": signal.scope,
        "subject": signal.subject,
        "source": signal.source,
        "label": spec.label if spec else signal.key,
        "avenue": spec.avenue if spec else "",
        "actionable": spec is not None,
    }


def _avenues(state: ForgeState, hydrated: list[dict]) -> list[dict]:
    """All explorable avenues: engine-derived (from scoped signals with specs)
    plus any the session-agent has discovered and posted. Each carries the search
    spec needed to surface its candidates."""
    out: list[dict] = []
    seen: set[str] = set()
    for sig in aggregate_signals(hydrated):
        spec = spec_for(sig)
        if spec is None:
            continue
        avenue_id = f"engine:{sig.key}:{sig.scope}"
        if avenue_id in seen:
            continue
        seen.add(avenue_id)
        out.append(
            {
                "id": avenue_id,
                "label": spec.label,
                "description": spec.avenue,
                "scope": sig.scope,
                "source": "engine",
                "search": dict(spec.search),
            }
        )
    out.extend(state.agent_avenues)
    return out


def _explore_filters(search: dict, *, color_identity: str, fmt: str) -> dict:
    filters = {k: search[k] for k in _EXPLORE_KEYS if search.get(k) is not None}
    presets = search.get("preset_names") or search.get("presets")
    if presets:
        filters["preset_names"] = tuple(presets)
    filters["color_identity"] = color_identity
    filters["format"] = fmt
    return filters


def build_app(state: ForgeState, *, frontend_dist: Path | None = None) -> FastAPI:
    """Build the FastAPI app from an injected ``ForgeState``."""
    app = FastAPI(title="deck-forge", version=VERSION)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION, "bulk": str(state.bulk_available)}

    @app.get("/api/deck")
    async def deck() -> dict:
        return {"deck": _deck_view(state)}

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return _snapshot(state)

    @app.get("/api/stats")
    async def stats() -> dict:
        s = state.session
        return deck_stats(s.to_deck_dict(), s.hydrated(state.by_name))

    @app.get("/api/mana-audit")
    async def mana() -> dict:
        s = state.session
        return mana_audit(s.to_deck_dict(), s.hydrated(state.by_name))

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
        snap = _snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/deck/remove")
    async def remove(payload: RemovePayload):
        bad_zone = _zone_error(payload.zone)
        if bad_zone is not None:
            return bad_zone
        state.session.remove(payload.name, payload.qty, zone=payload.zone)
        _autosave(state)
        snap = _snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/search")
    async def search(payload: SearchPayload):
        if not state.bulk_available:
            return JSONResponse(
                {"error": "Scryfall bulk data not found — run `download-bulk` first."},
                status_code=503,
            )
        records = state.search_fn(
            color_identity=payload.color_identity,
            oracle=payload.oracle,
            card_type=payload.type,
            name=payload.name,
            cmc_min=payload.cmc_min,
            cmc_max=payload.cmc_max,
            price_min=payload.price_min,
            price_max=payload.price_max,
            format=payload.format,
            paper_only=_paper_only(payload.format),
            preset_names=tuple(payload.presets),
            is_commander_filter=payload.is_commander,
            sort=payload.sort,
            limit=payload.limit,
        )
        return {
            "results": [{"name": r.get("name", ""), **_project(r)} for r in records]
        }

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        async def gen():
            # Send current state immediately so a (re)connecting browser re-syncs —
            # e.g. after a server restart — with no manual refresh, and never keeps a
            # stale snapshot (which is how a removed avenue lingered client-side).
            yield f"data: {json.dumps(_snapshot(state))}\n\n"
            async for message in state.hub.stream():
                yield message

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/signals")
    async def signals() -> dict:
        sigs = aggregate_signals(state.session.hydrated(state.by_name))
        return {"signals": [_signal_dict(s) for s in sigs]}

    @app.get("/api/budgets")
    async def budgets() -> dict:
        records = state.session.hydrated_expanded(state.by_name)
        return {
            "budgets": slot_budgets(records, deck_size=_deck_size(state.session.format))
        }

    @app.get("/api/packages")
    async def packages() -> dict:
        if not state.bulk_available:
            return JSONResponse(
                {"error": "Scryfall bulk data not found — run `download-bulk` first."},
                status_code=503,
            )
        sigs = aggregate_signals(state.session.hydrated(state.by_name))
        ci = _color_identity(state)
        fmt = state.session.format
        in_deck = set(state.session.card_names())
        out = []
        for sig in sigs:
            if spec_for(sig) is None:
                continue
            filters = search_filters(sig, color_identity=ci, fmt=fmt)
            found = state.search_fn(limit=40, paper_only=_paper_only(fmt), **filters)
            fresh = [c for c in found if c.get("name") not in in_deck]
            ranked = rank_candidates(
                fresh, active_signals=sigs, avenues=state.agent_avenues
            )[:_PACKAGE_LIMIT]
            out.append(
                {
                    "signal": _signal_dict(sig),
                    "candidates": [
                        {
                            "name": r["card"].get("name", ""),
                            **_project(r["card"]),
                            "score": r["score"],
                        }
                        for r in ranked
                    ],
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
        snap = _snapshot(state)
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
        snap = _snapshot(state)
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
        snap = _snapshot(state)
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
        snap = _snapshot(state)
        state.hub.publish(json.dumps(snap))
        return {"avenue": avenue, **snap}

    @app.delete("/api/avenues/{avenue_id}")
    async def remove_avenue(avenue_id: str) -> dict:
        state.agent_avenues[:] = [
            a for a in state.agent_avenues if a["id"] != avenue_id
        ]
        snap = _snapshot(state)
        state.hub.publish(json.dumps(snap))
        return snap

    @app.post("/api/explore")
    async def explore(payload: ExplorePayload) -> dict:
        if not state.bulk_available:
            return JSONResponse(
                {"error": "Scryfall bulk data not found — run `download-bulk` first."},
                status_code=503,
            )
        fmt = state.session.format
        filters = _explore_filters(
            payload.search, color_identity=_color_identity(state), fmt=fmt
        )
        found = state.search_fn(limit=40, paper_only=_paper_only(fmt), **filters)
        in_deck = set(state.session.card_names())
        fresh = [c for c in found if c.get("name") not in in_deck]
        sigs = aggregate_signals(state.session.hydrated(state.by_name))
        ranked = rank_candidates(
            fresh, active_signals=sigs, avenues=state.agent_avenues
        )[:_PACKAGE_LIMIT]
        return {
            "package": {
                "label": payload.label,
                "candidates": [
                    {
                        "name": r["card"].get("name", ""),
                        **_project(r["card"]),
                        "score": r["score"],
                    }
                    for r in ranked
                ],
            }
        }

    @app.get("/api/audit")
    async def audit() -> dict:
        return {"warnings": _legality_warnings(state)}

    @app.post("/api/finalize")
    async def finalize(payload: FinalizePayload) -> dict:
        fs = _finalize_state(state)
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
            return state.combos_fn(state.session.to_deck_dict())
        except Exception as exc:  # noqa: BLE001 — network/3rd-party; surface, don't crash
            return JSONResponse(
                {"error": f"combo lookup failed: {exc}"}, status_code=502
            )

    _register_frontend(app, frontend_dist)
    return app


def _register_frontend(app: FastAPI, frontend_dist: Path | None) -> None:
    if frontend_dist and (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="spa")
        return

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _PLACEHOLDER_INDEX
