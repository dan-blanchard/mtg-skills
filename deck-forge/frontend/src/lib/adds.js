// The one "add a card" call every panel shares: apply the snapshot on success, or
// return the hub's reason (the engine's own rule text — a copy limit, a zone the
// format lacks, a card the pool does not hold) for the caller to render beside the
// control it came from. Empty string = added.
import { api } from "./api.js";
import { applySnapshot } from "./store.js";

export async function tryAdd(name, zone = "cards") {
  const r = await api.add(name, zone, 1);
  if (r.ok) {
    applySnapshot(r.data);
    return "";
  }
  return r.data.error || `couldn't add ${name}`;
}
