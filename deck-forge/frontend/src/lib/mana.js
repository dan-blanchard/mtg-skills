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
  const p = card?.prices?.usd ?? card?.prices?.usd_foil ?? card?.prices?.usd_etched;
  const n = p == null ? null : Number(p);
  return n == null || Number.isNaN(n) ? null : n;
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
