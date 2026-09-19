"""deck-forge FastAPI app factory — the transport adapter.

``build_app(state)`` wires the HTTP endpoints, the SSE stream, and (when a built SPA is
present) static file serving. Each route is a thin adapter: parse the payload, call the
``engine`` (deck analysis over ``ForgeState``) and ``views`` (wire serialization), apply
side effects (mutation / autosave / SSE publish), and return. Everything the app needs
is injected via ``ForgeState`` so the endpoints are testable without bulk data on disk;
the deck logic itself is tested directly through ``engine`` / ``views``.
"""

from __future__ import annotations

import functools
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mtg_utils._deck_forge import collection, discovery, engine, views
from mtg_utils._deck_forge.engine import DeckRuleError
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils._tuner.tune import tune as run_tune
from mtg_utils.deck_stats import deck_stats
from mtg_utils.export_deck import export_as
from mtg_utils.mana_audit import mana_audit
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


class MovePayload(BaseModel):
    name: str
    from_zone: str
    to_zone: str
    qty: int = 1


class FormatPayload(BaseModel):
    format: str


class MediumPayload(BaseModel):
    medium: str  # "paper" | "digital"


class DeckSizePayload(BaseModel):
    deck_size: int  # a Commander-family choice (60 | 100) or a constructed floor


class SetPrintingPayload(BaseModel):
    name: str
    printing_id: str | None = None  # None → revert to default (cheapest) printing
    zone: str = "cards"
    # Optional finish for the pinned printing: "foil" | "etched". Validated against
    # the chosen printing's own `finishes` list; omitting it on a (re)pin clears any
    # stored finish (nonfoil default).
    finish: str | None = None


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
    # Sealed / draft: the whole list is the opened pool (no deck built yet).
    pool_only: bool = False


class SeedPayload(BaseModel):
    colors: str  # one or more of WUBRG, e.g. "WG"


class ImportCollectionPayload(BaseModel):
    text: str
    slot: str = "paper"


class ClearCollectionPayload(BaseModel):
    slot: str = "paper"


class DiscoverCommandersPayload(BaseModel):
    sort: str = "support"  # "support" (owned-support depth) | "novelty" (signal rarity)
    colors: str | None = None  # color-identity subset filter (e.g. "BG")
    themes: list[str] = []  # theme_presets lanes a commander must ALL match (as Find)
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
    include_unreleased: bool = False
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
    # Adds the builder rejected (Tune's Reject button): never proposed; the slot a
    # rejected card held goes to the next-ranked candidate on the re-run.
    exclude: list[str] = []


def _autosave(state: ForgeState) -> None:
    if state.store is not None:
        state.store.save(state.build_id, state.build_name, state.session.to_deck_dict())


def _commit(
    state: ForgeState, *, persist: bool = True, readout: dict | None = None
) -> dict:
    """The tail of every state-changing route, written once: persist the build (a
    DECK change — ``persist=False`` for runtime-only state like lanes and
    Collections, and for a load, which must not rewrite the file it just read), take
    the snapshot, broadcast it to every open browser, return it. ``readout`` is a
    land-plan result that rides on the broadcast snapshot (``balanced`` /
    ``trimmed``)."""
    if persist:
        _autosave(state)
    snap = {**engine.snapshot(state), **(readout or {})}
    state.hub.publish(json.dumps(snap))
    return snap


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
        include_unreleased=payload.include_unreleased,
        sort=payload.sort,
        limit=payload.limit,
        offset=payload.offset,
    )


def _clamp_timeout(timeout: float) -> float:
    return max(0.0, min(timeout, 30.0))


def _no_bulk() -> JSONResponse:
    return JSONResponse(
        {"error": "Scryfall bulk data not found — run `download-mtgjson` first."},
        status_code=503,
    )


def build_app(state: ForgeState, *, frontend_dist: Path | None = None) -> FastAPI:
    """Build the FastAPI app from an injected ``ForgeState``."""
    app = FastAPI(title="deck-forge", version=VERSION)

    @app.exception_handler(DeckRuleError)
    async def _deck_rule_error(_request: Request, exc: DeckRuleError) -> JSONResponse:
        # Every engine rule breach (ADR-0013) is one 400 with the rule's message.
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION, "bulk": str(state.bulk_available)}

    @app.get("/api/deck")
    async def deck() -> dict:
        return {
            "deck": views.deck_view(
                state,
                engine.owned_quantities(state),
                functools.partial(engine.printing_owned, state),
                functools.partial(engine.copy_limit, state),
            )
        }

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return engine.snapshot(state)

    @app.get("/api/stats")
    async def stats() -> dict:
        return deck_stats(engine.hydrate_session(state))

    @app.get("/api/mana-audit")
    async def mana() -> dict:
        return mana_audit(engine.hydrate_session(state))

    @app.post("/api/deck/add", response_model=None)
    async def add(payload: AddPayload) -> dict | JSONResponse:
        if payload.name not in state.by_name:
            return JSONResponse(
                {"error": f"card not found: {payload.name!r}"}, status_code=404
            )
        engine.add_card(state, payload.name, payload.qty, zone=payload.zone)
        return _commit(state)

    @app.post("/api/deck/move")
    async def move(payload: MovePayload) -> dict:
        """Move copies between zones in one step (``engine.move_card`` is the rule);
        returns the new snapshot."""
        engine.move_card(
            state,
            payload.name,
            from_zone=payload.from_zone,
            to_zone=payload.to_zone,
            qty=payload.qty,
        )
        return _commit(state)

    @app.post("/api/deck/remove")
    async def remove(payload: RemovePayload) -> dict:
        engine.remove_card(state, payload.name, payload.qty, zone=payload.zone)
        return _commit(state)

    @app.post("/api/deck/seed")
    async def seed(payload: SeedPayload) -> dict:
        """Seed a first 40 from a sealed / draft pool in the chosen colours
        (``engine.seed_build`` is the rule); returns the new snapshot."""
        seeded = engine.seed_build(state, payload.colors)
        return {"seeded": seeded, **_commit(state)}

    @app.post("/api/deck/seed/undo")
    async def seed_undo() -> dict:
        """Put back the main deck the last seed replaced (``engine.undo_seed`` is
        the rule); returns the new snapshot."""
        engine.undo_seed(state)
        return _commit(state)

    @app.get("/api/set-scan", response_model=None)
    async def set_scan(code: str) -> dict | JSONResponse:
        """What a set holds — removal by rarity, sweepers, evasion, the biggest
        bodies (``set_scan.set_scan`` over the pool's set index). Pure compute."""
        if not state.bulk_available or state.bulk_path is None:
            return _no_bulk()
        scan = await run_in_threadpool(engine.set_scan_for, state, code)
        if scan is None:
            return JSONResponse(
                {"error": f"no cards found for set {code!r}"}, status_code=404
            )
        return scan

    @app.post("/api/deck/format")
    async def set_format(payload: FormatPayload) -> dict:
        """Change the build's format (``engine.set_format`` is the rule); returns the
        new snapshot."""
        engine.set_format(state, payload.format)
        return _commit(state)

    @app.post("/api/deck/medium")
    async def set_medium(payload: MediumPayload) -> dict:
        """Set paper vs digital for the build (``engine.set_medium`` is the rule);
        returns the new snapshot."""
        engine.set_medium(state, payload.medium)
        return _commit(state)

    @app.post("/api/deck/deck-size")
    async def set_deck_size(payload: DeckSizePayload) -> dict:
        """Choose the deck size (``engine.set_deck_size`` is the rule); returns the
        new snapshot."""
        engine.set_deck_size(state, payload.deck_size)
        return _commit(state)

    @app.post("/api/deck/balance-lands")
    async def balance_lands() -> dict:
        """Fix the mana base: add basics to reach the FAIL floor and rebalance the
        basics to match color demand (swapping over- for under-produced colors at the
        current count when already at/above the floor)."""
        return _commit(state, readout={"balanced": engine.balance_lands(state)})

    @app.post("/api/deck/trim-lands")
    async def trim_lands() -> dict:
        """FLOOD remedy (#13): trim basics back down to the recommended land count
        (max of Burgess/Karsten), removing over-produced colors first. No-op when the
        deck is already at/under recommended. Soft — never blocks finalize, because an
        all-lands combo deck is a legitimate build (see CONTEXT Flood line)."""
        applied = engine.trim_lands(state)
        changed = bool(applied["add"] or applied["remove"])
        return _commit(state, persist=changed, readout={"trimmed": applied})

    @app.post("/api/handoff/goldfish", response_model=None)
    async def handoff_goldfish() -> dict | JSONResponse:
        """Run-here handoff (#6): goldfish the deck in-process and return the report
        inline — pure local compute (no LLM, no API key), so it works with no session
        attached. See ADR-0016."""
        if not state.bulk_available:
            return _no_bulk()
        hd = engine.hydrate_session(state)
        if len(hd.expanded(zones=("commanders", "cards"))) < 7:
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
        return {
            "card": views.result_view(
                rec,
                state.session.fmt,
                unreleased=rec.get("oracle_id") in state.unreleased_ids,
                copy_limit=engine.copy_limit(state, rec),
            )
        }

    @app.get("/api/printings", response_model=None)
    async def printings(name: str) -> dict | JSONResponse:
        """Every legal printing of a card for the picker (C): identity + set/collector
        + cost + art, annotated with printing-level ownership in the ACTIVE Collection
        slot (``owned_qty`` nonfoil / ``owned_foil_qty`` — 0 when unknown). Owned
        printings sort first (total owned desc, ties newest-first), then the rest
        newest-first. The envelope carries the name-level ``card_owned`` /
        ``card_owned_qty``. Empty for an unknown name / no bulk."""
        if not state.bulk_available:
            return _no_bulk()
        rows = [
            {**views.printing_view(p), "owned_qty": nonfoil, "owned_foil_qty": foil}
            for p, nonfoil, foil in engine.printings_for(state, name)
        ]
        owned_total = engine.owned_of(state, name)
        return {
            "name": name,
            "card_owned": owned_total is not None,
            "card_owned_qty": owned_total or 0,
            "printings": rows,
        }

    @app.post("/api/deck/printing")
    async def set_printing(payload: SetPrintingPayload) -> dict:
        """Pin (or clear, with a null id) the printing for a card in the deck (C). The
        chosen printing drives the card's image / price / export set, never its gameplay
        text. Validated against the card's own printings so a stray id can't pin a wrong
        card's art."""
        engine.check_zone(payload.zone)
        engine.choose_printing(
            state,
            payload.name,
            payload.printing_id,
            zone=payload.zone,
            finish=payload.finish,
        )
        return _commit(state)

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
        sigs = engine.ranked_deck_signals(
            state, engine.hydrate_session(state).deck_records()
        )
        return {"signals": [views.signal_view(s) for s in sigs]}

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
        return {"budgets": engine.budgets(state)}

    @app.get("/api/builds")
    async def builds() -> dict:
        return {
            "current": state.build_id,
            "builds": state.store.list() if state.store else [],
        }

    @app.post("/api/builds/new")
    async def builds_new(payload: NewBuildPayload) -> dict:
        engine.check_format(payload.format)
        engine.switch_build(
            state, DeckSession(payload.format), name=payload.name or "Untitled"
        )
        return {"build_id": state.build_id, **_commit(state)}

    @app.post("/api/builds/import")
    async def builds_import(payload: ImportDeckPayload) -> dict:
        """Import an existing list as a NEW build (ADR-0017). Parse the raw pasted /
        uploaded text IN-PROCESS (pure compute — `parse_deck_text`, no LLM, no API key),
        seed a fresh session, switch to it. Never overwrites the live build; never
        guesses a commander — an unmarked list lands as a pile in ``cards`` that the
        user promotes from (the DeckList ★)."""
        imported = engine.import_deck(
            state, payload.text, fmt=payload.format, pool_only=payload.pool_only
        )
        engine.switch_build(
            state, imported.session, name=payload.name or "Imported deck"
        )
        snap = _commit(state)
        parsed = imported.parsed
        return {
            "build_id": state.build_id,
            "imported": {
                "commanders": len(parsed.get("commanders") or []),
                "cards": sum(
                    int(e.get("quantity", 1)) for e in (parsed.get("cards") or [])
                ),
                "companion": len(parsed.get("companion") or []),
                "sideboard": sum(
                    int(e.get("quantity", 1)) for e in (parsed.get("sideboard") or [])
                ),
                "pool": sum(
                    int(e.get("quantity", 1)) for e in (parsed.get("pool") or [])
                ),
                # Names the index can't hydrate (typos, un-owned tokens, Arena-only
                # cards when no bulk) surface as `unknown` cards for the UI to warn.
                "unknown": imported.unknown,
                "warnings": imported.warnings,
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
        engine.switch_build(
            state,
            DeckSession.from_deck_dict(record.get("deck") or {}),
            name=record.get("name", "Untitled"),
            build_id=payload.id,
        )
        return {"build_id": state.build_id, **_commit(state, persist=False)}

    @app.post("/api/builds/rename")
    async def builds_rename(payload: RenameBuildPayload) -> dict:
        live = payload.id == state.build_id
        if live:
            # Rename the live deck and persist it under the new name immediately
            # (even if it had no file yet), so the name isn't lost without a mutation.
            state.build_name = payload.name
        elif state.store is not None:
            record = state.store.load(payload.id)
            if record is not None:
                state.store.save(payload.id, payload.name, record.get("deck") or {})
        return _commit(state, persist=live)

    @app.delete("/api/builds/{build_id}")
    async def delete_build(build_id: str) -> dict:
        deleted = state.store.delete(build_id) if state.store is not None else False
        if deleted and build_id == state.build_id:
            # The live build's file was just deleted. Reset to a fresh build so the
            # next mutation's _autosave doesn't silently re-create the deleted id.
            engine.switch_build(
                state, DeckSession(state.session.format), name="Untitled"
            )
            _commit(state)
        return {
            "deleted": deleted,
            "current": state.build_id,
            "builds": state.store.list() if state.store else [],
        }

    @app.post("/api/collection/import", response_model=None)
    async def collection_import(
        payload: ImportCollectionPayload,
        background: BackgroundTasks,
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
        snap = _commit(state, persist=False)  # a Collection is not the build
        # Warm the discovery caches for the just-imported slot in the background:
        # Starlette runs sync background tasks in the threadpool, so the ~65s cold cost
        # is paid there (off the event loop), not by the user's first discover. The
        # format is captured NOW — by execution time the live session format may have
        # changed, which would warm eligibility for the wrong format.
        if state.bulk_available:
            background.add_task(
                discovery.warm,
                state,
                payload.slot,
                fmt=state.session.format,
            )
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
        return _commit(state, persist=False)

    @app.post("/api/commanders/discover", response_model=None)
    async def commanders_discover(
        payload: DiscoverCommandersPayload,
    ) -> dict | JSONResponse:
        """Intent-ranked owned commanders from the active Collection slot (ADR-0018) —
        support-depth or novelty, theme/color filters, never EDHREC. Pure compute."""
        engine.check_commander_family(state)
        if not state.bulk_available:
            return _no_bulk()
        # Validate the themes like the sibling slot/format guards (a clean 400, not a
        # 500): theme_presets.matches raises KeyError on an unknown preset name.
        unknown = [t for t in payload.themes if t not in list_presets()]
        if unknown:
            return JSONResponse(
                {"error": f"unknown theme preset: {unknown[0]!r}"}, status_code=400
            )
        slot = engine.active_slot(state)
        # discover_commanders is heavy CPU (scores every owned commander).
        # Offload it to a worker thread so it never blocks the event loop;
        # a blocking call here froze the whole hub for the run (~30s on a big
        # collection). Same pattern as tune/goldfish. It fills discovery's caches
        # from this worker thread; ``DiscoveryCache`` carries the lock.
        results = await run_in_threadpool(
            discovery.discover_commanders,
            state,
            sort=payload.sort,
            colors=payload.colors,
            themes=tuple(payload.themes),
            limit=max(1, payload.limit),
        )
        fmt = state.session.fmt
        return {
            "results": [views.commander_view(row, fmt) for row in results],
            "sort": payload.sort,
            "active_slot": slot,
            "slot_size": collection.slot_sizes(state.collections).get(slot, 0),
        }

    @app.get("/api/export", response_model=None)
    async def export(fmt: str = "json") -> dict | JSONResponse:
        deck = engine.export_deck_dict(state)
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
        avenue = engine.add_agent_avenue(
            state,
            label=payload.label,
            description=payload.description,
            search=payload.search,
        )
        return {"avenue": avenue, **_commit(state, persist=False)}

    @app.delete("/api/avenues/{avenue_id}")
    async def remove_avenue(avenue_id: str) -> dict:
        engine.remove_avenue(state, avenue_id)
        return _commit(state, persist=False)

    @app.post("/api/avenues/{avenue_id}/focus")
    async def focus_avenue(avenue_id: str) -> dict:
        """Toggle a lane as 'focused' (#2): the candidate ✦ score then counts only the
        focused lanes. Idempotent toggle so the pin button can flip it either way."""
        engine.toggle_avenue_focus(state, avenue_id)
        return _commit(state, persist=False)

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
        # find_candidates scans/scores the bulk pool: modest (~0.3s) but enough
        # to stutter the loop under rapid typing, so offload it too (same pattern).
        page = await run_in_threadpool(
            engine.find_candidates, state, _find_params(payload)
        )
        fmt = state.session.fmt
        results = [
            views.candidate_view(
                row,
                fmt,
                owned_qty=engine.owned_of(state, row["card"].get("name", "")),
                unreleased=row["card"].get("oracle_id") in state.unreleased_ids,
                copy_limit=engine.copy_limit(state, row["card"]),
            )
            for row in page.rows
        ]
        return {"results": results, "offset": page.offset, "has_more": page.has_more}

    @app.get("/api/audit")
    async def audit() -> dict:
        return {"warnings": engine.legality_warnings(engine.hydrate_session(state))}

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
        params = engine.tune_params(
            state,
            budget=payload.budget,
            wildcard_budget=payload.wildcard_budget,
            max_swaps=payload.max_swaps,
            shape_override=payload.shape_override,
            suggest_commander=payload.suggest_commander,
            exclude=payload.exclude,
        )
        # run_tune does blocking work (a Commander Spellbook combos call + heavy bulk
        # searches); offload it to a worker thread so a slow combo lookup can't stall
        # the event loop and wedge the whole hub. Pure read of state, so thread-safe.
        hd = engine.hydrate_session(state)
        return await run_in_threadpool(
            run_tune,
            hd,
            # A pool-bounded build searches its opened pool (and owns all of it).
            search_fn=engine.search_for(state, hd),
            params=params,
            # The WHOLE active Collection slot, not the deck-scoped owned map: the tuner
            # costs CANDIDATE adds (not in the deck yet), so it must see every card you
            # own as free — otherwise a zero wildcard budget fills nothing and owned
            # cards wrongly consume budget.
            owned=engine.owned_collection(state),
            combos_fn=state.combos_fn,
            # ADR-0025: the tune scorecard must rank the SAME commander lanes
            # the avenues panel shows — folded-object signals included.
            resolve_object=state.object_resolver,
            pool=engine.pool_owned(state),
        )

    @app.post("/api/finalize")
    async def finalize(payload: FinalizePayload) -> dict:
        fs = engine.finalize_state(state)
        land_fail = fs["land_status"] == "FAIL"
        # Below the CR minimum is illegal, never overridable; the land gate is.
        gated = fs["below_minimum"] or (land_fail and not payload.override)
        return {
            "finalized": not gated,
            "gated": gated,
            # An override that could not lift the gate overrode nothing.
            "overridden": land_fail and payload.override and not gated,
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
        return views.enrich_combos(
            result,
            state.by_name,
            in_deck=engine.deck_names(state),
            fmt=state.session.fmt,
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
