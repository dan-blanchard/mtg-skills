import { writable } from "svelte/store";

export const deck = writable({
  format: "commander",
  commanders: [],
  cards: [],
  sideboard: [],
});
export const stats = writable(null);
export const mana = writable(null);
export const budgets = writable(null);
export const signals = writable([]);
export const warnings = writable([]);
export const connected = writable(false);
export const agentBusy = writable(false);
export const agentReply = writable(null);

// Apply a snapshot (from /api/snapshot, SSE, or a mutation response).
export function applySnapshot(snap) {
  if (!snap) return;
  if (snap.deck) deck.set(snap.deck);
  if (snap.stats) stats.set(snap.stats);
  if (snap.mana) mana.set(snap.mana);
  if (snap.budgets) budgets.set(snap.budgets);
  if (snap.signals) signals.set(snap.signals);
  if (snap.warnings) warnings.set(snap.warnings);
}
