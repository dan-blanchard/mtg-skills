import { writable } from "svelte/store";

export const deck = writable({
  format: "commander",
  commanders: [],
  cards: [],
  sideboard: [],
});
export const stats = writable(null);
export const bracket = writable(null);
export const mana = writable(null);
export const budgets = writable(null);
export const signals = writable([]);
export const avenues = writable([]);
export const warnings = writable([]);
export const connected = writable(false);
export const agentBusy = writable(false);
// True once a slow request has crossed the quick budget while the agent is
// confirmed attached — lets the UI reassure ("still reasoning") instead of
// implying the request stalled.
export const agentThinking = writable(false);
export const agentReply = writable(null);
export const buildId = writable(null);
export const buildName = writable("Untitled");

// Which left tab is active. Search + Synergies are merged into the unified "find"
// surface (ADR-0015); focusing avenues drives it via server-side focus state.
export const activeTab = writable("find");

// Card hover preview: { card, x, y } | null — follows the cursor over any card.
export const hovered = writable(null);

// Whether an interactive Claude session is bridged to the hub (the "● Session" dot
// and Forge-Friend's status read this one source; App.svelte owns the poll). Distinct
// from `connected`, which is the browser↔hub SSE link (the "● Hub" dot).
export const agentAttached = writable(false);

// The Mana Gate detail modal — opened by clicking the land-health pill in the footer.
export const manaModalOpen = writable(false);

// Apply a snapshot (from /api/snapshot, SSE, or a mutation response).
export function applySnapshot(snap) {
  if (!snap) return;
  if (snap.deck) deck.set(snap.deck);
  if (snap.stats) stats.set(snap.stats);
  if (snap.bracket) bracket.set(snap.bracket);
  if (snap.mana) mana.set(snap.mana);
  if (snap.budgets) budgets.set(snap.budgets);
  if (snap.signals) signals.set(snap.signals);
  if (snap.avenues) avenues.set(snap.avenues);
  if (snap.warnings) warnings.set(snap.warnings);
  if (snap.build_id !== undefined) buildId.set(snap.build_id);
  if (snap.build_name !== undefined) buildName.set(snap.build_name);
}
