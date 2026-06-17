// The live faceting shared by the Find results AND the deck view (A4): the same Type /
// CMC / Price-or-Rarity / Owned chips narrow a card list client-side (no round-trip).
// Extracted from Find.svelte so DeckList can reuse the exact widget + predicate.
import { RARITY_RANK } from "./mana.js";

export const TYPE_FACETS = [
  ["", "All"],
  ["creature", "Creatures"],
  ["instant|sorcery", "Inst/Sorc"],
  ["artifact", "Artifacts"],
  ["enchantment", "Enchant."],
  ["planeswalker", "PWs"],
  ["land", "Lands"],
];
export const CMC_FACETS = [
  ["", "Any"],
  ["0-2", "≤2"],
  ["3", "3"],
  ["4", "4"],
  ["5+", "5+"],
];
export const PRICE_FACETS = [
  ["", "Any"],
  ["1", "≤$1"],
  ["5", "≤$5"],
  ["20", "≤$20"],
];
// Digital builds cost wildcards, not dollars: "≤U" is the cheap, abundant pool
// (commons + uncommons), then the two scarce tiers R and M on their own.
export const RARITY_FACETS = [
  ["", "Any"],
  ["leU", "≤U"],
  ["rare", "R"],
  ["mythic", "M"],
];

export function emptyFacets() {
  return { type: "", cmc: "", price: "", rarity: "", owned: false };
}

// True if a card passes the active facets. ``f`` is {type, cmc, price, rarity, owned}.
// Callers that need Svelte reactivity must read the facet values into ``f`` at the call
// site (so Svelte tracks them as dependencies) — this function does not close over them.
export function facetOk(card, f, digital) {
  if (f.type && !new RegExp(f.type, "i").test(card.type_line || ""))
    return false;
  if (f.cmc) {
    const v = card.cmc ?? 0;
    if (f.cmc === "0-2" && v > 2) return false;
    if (f.cmc === "3" && v !== 3) return false;
    if (f.cmc === "4" && v !== 4) return false;
    if (f.cmc === "5+" && v < 5) return false;
  }
  if (digital) {
    // Wildcard cost filter. "leU" is a ceiling (commons + uncommons); "rare"/"mythic"
    // match that exact scarce tier. Unknown-rarity cards always pass.
    if (f.rarity && card.rarity) {
      if (f.rarity === "leU") {
        if (RARITY_RANK[card.rarity] > RARITY_RANK.uncommon) return false;
      } else if (card.rarity !== f.rarity) {
        return false;
      }
    }
  } else if (f.price) {
    const p = card.prices?.usd == null ? Infinity : Number(card.prices.usd);
    if (p > Number(f.price)) return false;
  }
  return !(f.owned && !card.owned);
}

// Client-side name substring (case-insensitive); empty query matches everything.
export function nameOk(card, query) {
  const q = (query || "").trim().toLowerCase();
  return !q || (card.name || "").toLowerCase().includes(q);
}
