import { api } from "./api.js";
import { agentBusy, agentReply } from "./store.js";

const OFFLINE_MSG =
  "No forge-friend attached. Run /deck-forge in an interactive Claude Code session to enable reasoning, novel-synergy discovery, and rules answers.";

// Ask the session-agent a question; routes the answer into the shared reply store.
export async function askForge(kind, payload = {}) {
  agentBusy.set(true);
  agentReply.set(null);
  const res = await api.agentAsk(kind, payload);
  agentBusy.set(false);
  if (res.timeout) {
    agentReply.set({ kind, payload, text: OFFLINE_MSG, offline: true });
  } else if (res.error) {
    agentReply.set({ kind, payload, text: res.error, offline: false });
  } else {
    agentReply.set({ kind, payload, ...res.result });
  }
}
