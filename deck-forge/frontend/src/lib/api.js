// Thin client over the deck-forge backend hub.

async function post(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  return { ok: resp.ok, status: resp.status, data };
}

async function get(path) {
  const resp = await fetch(path);
  const data = await resp.json().catch(() => ({}));
  return { ok: resp.ok, status: resp.status, data };
}

async function del(path) {
  const resp = await fetch(path, { method: "DELETE" });
  const data = await resp.json().catch(() => ({}));
  return { ok: resp.ok, status: resp.status, data };
}

export const api = {
  snapshot: () => fetch("/api/snapshot").then((r) => r.json()),
  search: (filters) => post("/api/search", filters),
  add: (name, zone = "cards", qty = 1) => post("/api/deck/add", { name, zone, qty }),
  remove: (name, zone = "cards", qty = 1) =>
    post("/api/deck/remove", { name, zone, qty }),
  balanceLands: () => post("/api/deck/balance-lands", {}),
  setFormat: (format) => post("/api/deck/format", { format }),
  packages: () => get("/api/packages"),
  presets: () => get("/api/presets"),
  combos: () => get("/api/combos"),
  agentStatus: () => get("/api/agent/status"),
  explore: (label, search, offset = 0) =>
    post("/api/explore", { label, search, offset }),
  removeAvenue: (id) => del(`/api/avenues/${id}`),
  finalize: (override) => post("/api/finalize", { override }),
  builds: () => get("/api/builds"),
  buildsNew: (format = "commander", name = "Untitled") =>
    post("/api/builds/new", { format, name }),
  buildsLoad: (id) => post("/api/builds/load", { id }),
  renameBuild: (id, name) => post("/api/builds/rename", { id, name }),
  deleteBuild: (id) => del(`/api/builds/${id}`),
  exportDeck: (fmt) => get(`/api/export?fmt=${fmt}`),

  // Raise a reasoning request and long-poll for the session-agent's answer.
  // Resolves to {result} | {offline: true} | {slow: true} | {error}.
  //
  // Grounded answers (card-search + per-card oracle verification, sometimes a
  // rules-lawyer hop) routinely take ~1 minute, so a fixed short budget would
  // mislabel a working agent as absent. We poll patiently and, past the quick
  // budget, consult the authoritative /api/agent/status to tell a genuinely
  // detached session (`offline`) apart from one that's simply still reasoning
  // (keep waiting; reassure the UI via `onThinking`). Only a confirmed-detached
  // status yields `offline`; exceeding the hard cap while attached yields
  // `slow` (still working), never a false "not attached".
  async agentAsk(kind, payload = {}, { onThinking } = {}) {
    const req = await post("/api/agent/request", { kind, payload });
    if (!req.ok) return { error: req.data.error || "request failed" };
    const id = req.data.request_id;
    const QUICK = 3; // ~60s of quiet waiting before we reassure / re-check attach
    const MAX = 15; // ~5 min hard cap (each poll is a ~20s server long-poll)
    for (let i = 0; i < MAX; i++) {
      const res = await get(`/api/agent/result/${id}?timeout=20`);
      if (res.status === 200) return { result: res.data.result };
      if (!res.ok && res.status !== 204) return { error: res.data.error || "failed" };
      if (i + 1 >= QUICK) {
        const st = await get("/api/agent/status");
        if (st.ok && st.data && st.data.attached === false) return { offline: true };
        if (onThinking) onThinking();
      }
    }
    return { slow: true };
  },
};

// Subscribe to the live snapshot stream. Returns the EventSource so callers can close it.
export function connectEvents({ onSnapshot, onOpen, onError }) {
  const es = new EventSource("/api/events");
  es.onmessage = (e) => onSnapshot(JSON.parse(e.data));
  if (onOpen) es.onopen = onOpen;
  if (onError) es.onerror = onError;
  return es;
}
