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
export const avenues = writable([]);
export const warnings = writable([]);
export const connected = writable(false);
export const agentBusy = writable(false);
export const agentReply = writable(null);
export const buildId = writable(null);
export const buildName = writable("Untitled");

// Cross-component navigation: which left tab is active, and which avenue (if any)
// the user clicked to explore in the Synergies tab.
export const activeTab = writable("search");
export const exploreAvenue = writable(null);

// Card hover preview: { card, x, y } | null — follows the cursor over any card.
export const hovered = writable(null);

// Apply a snapshot (from /api/snapshot, SSE, or a mutation response).
export function applySnapshot(snap) {
  if (!snap) return;
  if (snap.deck) deck.set(snap.deck);
  if (snap.stats) stats.set(snap.stats);
  if (snap.mana) mana.set(snap.mana);
  if (snap.budgets) budgets.set(snap.budgets);
  if (snap.signals) signals.set(snap.signals);
  if (snap.avenues) avenues.set(snap.avenues);
  if (snap.warnings) warnings.set(snap.warnings);
  if (snap.build_id !== undefined) buildId.set(snap.build_id);
  if (snap.build_name !== undefined) buildName.set(snap.build_name);
}
