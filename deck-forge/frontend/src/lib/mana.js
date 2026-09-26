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

// Copies of a card still to acquire: the hub's served `copies_short` (deck rows, Find
// results and combo pieces all carry it; the ownership rule is applied there and never
// re-derived here). null when a row wasn't served one — the cost is unknown.
export function copiesShort(card) {
  return card?.copies_short ?? null;
}

// Per-card Arena cost for a digital build → { text, cls, title } for display, read
// from the served `copies_short` / `covered_by` (free basic, owned, or each copy short
// costs one wildcard of its rarity).
// `cls` is a .wc-* class suffix (owned | free | mythic | rare | uncommon | common).
export function wildcardLabel(card) {
  const short = copiesShort(card);
  if (short === null)
    return { text: "—", cls: "unknown", title: "Cost unknown" };
  if (card.covered_by === "free")
    return {
      text: "free",
      cls: "free",
      title: "Basic land — no wildcard needed",
    };
  if (short === 0)
    return {
      text: "owned",
      cls: "owned",
      title: "Your collection covers every copy",
    };
  const letter = WC_LETTER[card?.rarity];
  if (!letter) return { text: "—", cls: "unknown", title: "Rarity unknown" };
  const word = WC_WORD[card.rarity];
  return {
    text: short > 1 ? `${letter}×${short}` : letter,
    cls: card.rarity,
    title: `${short} ${word} wildcard${short > 1 ? "s" : ""}`,
  };
}

// Wildcards needed across a list of deck cards, by tier: the sum of each card's served
// shortfall — the same numbers the footer's $wildcards total is built from, per group.
export function wildcardTotals(cards) {
  const out = { mythic: 0, rare: 0, uncommon: 0, common: 0 };
  for (const c of cards || []) {
    if (c.rarity in out) out[c.rarity] += copiesShort(c) ?? 0;
  }
  return out;
}

// The land-health readout shared by the footer pill and the Mana Gate modal — a
// pass-through of the backend's ONE `land_band` (ADR-0041): floor (the gate), top
// (the target), flood (top + 2, the soft FLOOD line — never gates finalize, because an
// all-lands combo deck is a legitimate build) and status PASS | WARN | FAIL | FLOOD.
// Nothing about the band is derived here. See deck-forge CONTEXT.md › "Land band".
export function landState(mana) {
  const band = mana?.land_band;
  if (!band) return null;
  return {
    count: band.count,
    recommended: band.top,
    floor: band.floor,
    ceiling: band.flood,
    status: band.status,
    over: band.count - band.top, // how many to trim back to the top (FLOOD only)
    short: Math.max(0, band.floor - band.count), // how many to add (FAIL)
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
