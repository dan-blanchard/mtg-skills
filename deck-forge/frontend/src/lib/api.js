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

export const api = {
  snapshot: () => fetch("/api/snapshot").then((r) => r.json()),
  search: (filters) => post("/api/search", filters),
  add: (name, zone = "cards", qty = 1) => post("/api/deck/add", { name, zone, qty }),
  remove: (name, zone = "cards", qty = 1) =>
    post("/api/deck/remove", { name, zone, qty }),
  packages: () => get("/api/packages"),
  combos: () => get("/api/combos"),
  finalize: (override) => post("/api/finalize", { override }),
  builds: () => get("/api/builds"),
  buildsNew: (format = "commander", name = "Untitled") =>
    post("/api/builds/new", { format, name }),
  buildsLoad: (id) => post("/api/builds/load", { id }),
  exportDeck: (fmt) => get(`/api/export?fmt=${fmt}`),

  // Raise a reasoning request and long-poll for the session-agent's answer.
  // Resolves to {result} | {timeout: true} | {error}. A timeout means no
  // interactive Claude Code session is attached to answer.
  async agentAsk(kind, payload = {}) {
    const req = await post("/api/agent/request", { kind, payload });
    if (!req.ok) return { error: req.data.error || "request failed" };
    const id = req.data.request_id;
    for (let i = 0; i < 3; i++) {
      const res = await get(`/api/agent/result/${id}?timeout=20`);
      if (res.status === 200) return { result: res.data.result };
      if (!res.ok && res.status !== 204) return { error: res.data.error || "failed" };
    }
    return { timeout: true };
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
