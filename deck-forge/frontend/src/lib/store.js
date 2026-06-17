import { writable, derived } from "svelte/store";

export const deck = writable({
  format: "commander",
  commanders: [],
  cards: [],
  sideboard: [],
});
// True for an Arena/digital build (Brawl / Historic Brawl with the medium toggle set to
// digital). Drives every cost read-out: digital shows Arena wildcards by rarity, paper
// shows USD. Derived so components subscribe to one flag instead of repeating the test.
export const isDigital = derived(deck, ($d) => $d.medium === "digital");
export const stats = writable(null);
export const bracket = writable(null);
export const mana = writable(null);
export const budgets = writable(null);
export const signals = writable([]);
export const avenues = writable([]);
export const warnings = writable([]);
// The global Collection summary (#2, ADR-0018): { active_slot, slots:{paper,arena},
// owned, deck_total } — drives the owned readout and the discovery panel's empty-prompt.
export const collection = writable(null);
// Arena wildcard cost for a digital build: { mythic, rare, uncommon, common } needed,
// or null for a paper build (USD cost). Drives the footer cost readout.
export const wildcards = writable(null);
export const connected = writable(false);
export const agentBusy = writable(false);
// True once a slow request has crossed the quick budget while the agent is
// confirmed attached — lets the UI reassure ("still reasoning") instead of
// implying the request stalled.
export const agentThinking = writable(false);
export const agentReply = writable(null);
export const buildId = writable(null);
export const buildName = writable("Untitled");
// True when a second commander could still join (CR 702.124 partner / Background): the
// Find color pips stay unlocked so an off-identity partner is findable (A5).
export const partnerOpen = writable(false);

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

// Import-a-deck dialog (#1, ADR-0017) — opened from the BuildMenu and the cold-forge
// empty state; rendered once at App level.
export const importOpen = writable(false);

// Import-a-collection dialog (#2, ADR-0018) — distinct from the deck import (it targets a
// Collection slot, not a build). Opened from the BuildMenu and the Commanders panel.
export const collectionOpen = writable(false);

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
  if (snap.collection) collection.set(snap.collection);
  // wildcards is null for paper builds — set unconditionally (don't keep a stale value).
  if ("wildcards" in snap) wildcards.set(snap.wildcards);
  if (snap.build_id !== undefined) buildId.set(snap.build_id);
  if (snap.build_name !== undefined) buildName.set(snap.build_name);
  if ("partner_open" in snap) partnerOpen.set(snap.partner_open);
}
