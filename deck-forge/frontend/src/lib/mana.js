// MTG color metadata for pips, curve tinting, and color-source readouts.

export const COLOR_ORDER = ["W", "U", "B", "R", "G", "C"];

// Order for DISPLAYING symbols: colorless first, then WUBRG.
export const SYMBOL_ORDER = ["C", "W", "U", "B", "R", "G"];

export const COLOR_LABEL = {
  W: "White",
  U: "Blue",
  B: "Black",
  R: "Red",
  G: "Green",
  C: "Colorless",
};

// CMC buckets for the curve chart (7 collects everything 7+).
export const CURVE_BUCKETS = [0, 1, 2, 3, 4, 5, 6, 7];

// Deck-size target per Commander-family format (the footer reads "current/target").
export const FORMAT_TARGET = {
  commander: 100,
  brawl: 60,
  historic_brawl: 100,
};

// Cheapest USD listing for a card, or null (no-listing ≠ free — never shown as $0).
// Mirrors DeckList.priceOf so the footer's deck total agrees with the list subtotals.
export function priceOf(card) {
  const p =
    card?.prices?.usd ?? card?.prices?.usd_foil ?? card?.prices?.usd_etched;
  const n = p == null ? null : Number(p);
  return n == null || Number.isNaN(n) ? null : n;
}

// ─── Arena wildcards ────────────────────────────────────────────────────────
// In a digital (Arena) build a card costs nothing in dollars — it costs one wildcard
// of its rarity (and owned cards / basic lands cost nothing). These helpers are the
// medium-aware counterpart to priceOf, shared by every cost read-out.

// Tiers high→low, with the chip letter and the rarity key (= the .wc-<key> color class).
export const WC_TIERS = [
  ["mythic", "M", "mythic"],
  ["rare", "R", "rare"],
  ["uncommon", "U", "uncommon"],
  ["common", "C", "common"],
];

// Rarity ordering for the "max wildcard rarity" facet ceiling (≤C / ≤U / ≤R).
export const RARITY_RANK = { common: 0, uncommon: 1, rare: 2, mythic: 3 };

const WC_LETTER = { mythic: "M", rare: "R", uncommon: "U", common: "C" };
const WC_WORD = {
  mythic: "mythic",
  rare: "rare",
  uncommon: "uncommon",
  common: "common",
};

export function isBasicLand(card) {
  return /\bBasic Land\b/.test(card?.type_line || "");
}

// Per-card Arena cost for a digital build → { text, cls, title } for display.
// Owned cards and basics are free; everything else is one wildcard of its rarity.
// `cls` is a .wc-* class suffix (owned | free | mythic | rare | uncommon | common).
export function wildcardLabel(card) {
  if (card?.owned)
    return {
      text: "owned",
      cls: "owned",
      title: "Already in your Arena collection",
    };
  if (isBasicLand(card))
    return {
      text: "free",
      cls: "free",
      title: "Basic land — no wildcard needed",
    };
  const letter = WC_LETTER[card?.rarity];
  if (!letter) return { text: "—", cls: "unknown", title: "Rarity unknown" };
  return {
    text: letter,
    cls: card.rarity,
    title: `1 ${WC_WORD[card.rarity]} wildcard`,
  };
}

// Wildcards needed across a list of deck cards, by tier — owned cards and basics are
// free, so they don't count. Singleton Commander-family formats are one copy each, so a
// card contributes exactly one wildcard of its rarity. Mirrors the backend wildcard_cost
// definition the footer's $wildcards aggregate uses, but per-group (Command Zone / Deck).
export function wildcardTotals(cards) {
  const out = { mythic: 0, rare: 0, uncommon: 0, common: 0 };
  for (const c of cards || []) {
    if (c.owned || isBasicLand(c)) continue;
    if (c.rarity in out) out[c.rarity] += c.quantity || 1;
  }
  return out;
}

// The land-health readout shared by the footer pill and the Mana Gate modal.
// Adds the soft FLOOD band (recommended + 2) on top of the backend's PASS/WARN/FAIL:
// above the flood line the deck is over-landed (offer to trim) — but FLOOD never gates
// finalize, because an all-lands two/three-card combo deck is a legitimate build.
// See deck-forge CONTEXT.md › "Flood line".
export function landState(mana) {
  if (!mana) return null;
  const count = mana.land_count ?? 0;
  const recommended = mana.recommended_land_count ?? 0;
  const ceiling = recommended + 2;
  const status = count > ceiling ? "FLOOD" : mana.land_count_status;
  return {
    count,
    recommended,
    floor: mana.land_count_floor ?? 0,
    ceiling,
    status, // PASS | WARN | FAIL | FLOOD
    over: count - recommended, // how many to trim back to recommended (FLOOD only)
    short: Math.max(0, (mana.land_count_floor ?? 0) - count), // how many to add (FAIL)
  };
}

export function bucketCurve(curve) {
  const out = Object.fromEntries(CURVE_BUCKETS.map((b) => [b, 0]));
  for (const [cmc, n] of Object.entries(curve || {})) {
    const k = Math.min(7, parseInt(cmc, 10) || 0);
    out[k] += n;
  }
  return out;
}

// Split a mana-cost string ("{1}{R}{W/U}") into bare symbol codes for <Mana>
// (which strips braces itself). Hybrid/Phyrexian like "W/U" stay intact; the
// <Mana> SVG-URL builder normalizes the slash.
export function parseManaCost(cost) {
  if (!cost) return [];
  return (String(cost).match(/\{[^}]+\}/g) || []).map((t) => t.slice(1, -1));
}

// Tokenize a forge-friend reply into ordered runs for rich rendering:
//   {t:'text', v}  — plain prose
//   {t:'card', v}  — a card reference written by the agent as [[Card Name]]
//   {t:'mana', v}  — a mana/symbol token written as {W}, {1}, {T}, …
// Everything outside [[…]] / {…} stays plain text, so reasoning is preserved.
export function tokenizeReply(text) {
  const out = [];
  if (!text) return out;
  const re = /\[\[([^\]]+)\]\]|\{([^}]+)\}/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    if (m[1] != null) out.push({ t: "card", v: m[1].trim() });
    else out.push({ t: "mana", v: m[2] });
    last = re.lastIndex;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}
