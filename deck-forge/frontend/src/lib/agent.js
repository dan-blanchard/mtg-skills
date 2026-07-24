import { get } from "svelte/store";
import { api } from "./api.js";
import {
  agentAttached,
  agentBusy,
  agentReply,
  agentThinking,
} from "./store.js";

const OFFLINE_MSG =
  "No forge-friend attached. Run /deck-forge in an interactive Claude Code session to enable reasoning, novel-synergy discovery, and rules answers.";
const SLOW_MSG =
  "The forge-friend is attached and still reasoning — this one is taking unusually long. Give it a moment, or ask again.";

// Ask the session-agent a question; routes the answer into the shared reply store.
// Defensive no-op when no session is attached — the UI already disables every caller
// (CardTile / Commanders / ForgeFriend) on `!$agentAttached`, but this keeps the guard
// in one place regardless of caller.
export async function askForge(kind, payload = {}) {
  if (!get(agentAttached)) return;
  agentBusy.set(true);
  agentThinking.set(false);
  agentReply.set(null);
  const res = await api.agentAsk(kind, payload, {
    onThinking: () => agentThinking.set(true),
  });
  agentBusy.set(false);
  agentThinking.set(false);
  if (res.offline) {
    agentReply.set({ kind, payload, text: OFFLINE_MSG, offline: true });
  } else if (res.slow) {
    agentReply.set({ kind, payload, text: SLOW_MSG, slow: true });
  } else if (res.error) {
    agentReply.set({ kind, payload, text: res.error, offline: false });
  } else {
    agentReply.set({ kind, payload, ...res.result });
  }
}
