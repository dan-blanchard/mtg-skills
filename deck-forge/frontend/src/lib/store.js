import { writable, derived, get } from "svelte/store";

export const deck = writable({
  format: "commander",
  commanders: [],
  cards: [],
  sideboard: [],
  // The outside-the-game companion zone (CR 702.139) — always an array in snapshots;
  // present here so pre-snapshot renders don't crash on $deck.companion reads.
  companion: [],
});
// True for an Arena/digital build (Brawl / Historic Brawl with the medium toggle set to
// digital). Drives every cost read-out: digital shows Arena wildcards by rarity, paper
// shows USD. Derived so components subscribe to one flag instead of repeating the test.
export const isDigital = derived(deck, ($d) => $d.medium === "digital");
// The format table the backend serves in every snapshot (ADR-0045): one row per
// format the hub serves, every family — { id, label, family, has_commander,
// max_copies, sideboard_size, size_is_minimum, media, default_medium, deck_size,
// size_choices: { <medium>: [sizes] } }. The pickers, zones, copy stepper and pills
// derive from it; nothing here mirrors the backend's format table.
export const formatOptions = writable([]);
// The served row for the live deck's format, and the family facts every component
// keys off (never a string compare on the format id). Defaults reproduce a
// Commander build for the pre-snapshot render.
export const currentFormat = derived(
  [formatOptions, deck],
  ([$opts, $d]) => $opts.find((f) => f.id === $d.format) ?? null,
);
export const hasCommander = derived(
  currentFormat,
  ($f) => $f?.has_commander ?? true,
);
// A null cap on the served row means NONE (a limited build: the whole unused pool
// as the sideboard) — Infinity here, so the comparisons read naturally; before the
// first snapshot the defaults are Commander's. (A card's copy limit is served per
// row as `copy_limit` — see lib/cards.js — never derived from the format here.)
export const sideboardSize = derived(currentFormat, ($f) =>
  $f ? ($f.sideboard_size ?? Infinity) : 0,
);
// A sealed / draft build: bounded by its opened pool, the sideboard derived.
export const poolBounded = derived(
  currentFormat,
  ($f) => $f?.pool_bounded ?? false,
);
export const sizeIsMinimum = derived(
  currentFormat,
  ($f) => $f?.size_is_minimum ?? false,
);
export const deckSizeDefault = derived(
  currentFormat,
  ($f) => $f?.deck_size ?? 100,
);
// The colors the hub scopes lane searches to: the commanders' identity under a
// command zone, else the castable colors of the cards the deck runs (a caption for
// a constructed build — the pips stay unlocked).
export const deckColors = writable("");
// The pool panel a sealed / draft snapshot serves ({ size, unused, color_pairs }),
// null for every other family.
export const pool = writable(null);
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
// The one long hub job in flight (the first-launch card-signal index build):
// { job, label, done, total, eta_s } while it runs, null when idle. Arrives in
// every snapshot and as its own SSE message as the build moves.
export const busy = writable(null);
// Adds the builder rejected in Tune (card names) — sent with every Tune run as
// `exclude`, so a rejected card's slot is re-sourced from the next candidate. Per
// build: cleared when the snapshot's build_id changes.
export const rejectedAdds = writable(new Set());
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
  if (snap.format_options) formatOptions.set(snap.format_options);
  if (snap.stats) stats.set(snap.stats);
  // bracket is null outside the Commander family — set unconditionally so a
  // format switch clears the stale pill.
  if ("bracket" in snap) bracket.set(snap.bracket);
  if ("deck_colors" in snap) deckColors.set(snap.deck_colors);
  if ("pool" in snap) pool.set(snap.pool);
  if (snap.mana) mana.set(snap.mana);
  if (snap.budgets) budgets.set(snap.budgets);
  if (snap.signals) signals.set(snap.signals);
  if (snap.avenues) avenues.set(snap.avenues);
  if (snap.warnings) warnings.set(snap.warnings);
  if (snap.collection) collection.set(snap.collection);
  // wildcards is null for paper builds — set unconditionally (don't keep a stale value).
  if ("wildcards" in snap) wildcards.set(snap.wildcards);
  if ("busy" in snap) busy.set(snap.busy);
  if (snap.build_id !== undefined) {
    if (get(buildId) !== snap.build_id) rejectedAdds.set(new Set());
    buildId.set(snap.build_id);
  }
  if (snap.build_name !== undefined) buildName.set(snap.build_name);
  if ("partner_open" in snap) partnerOpen.set(snap.partner_open);
}
