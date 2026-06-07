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
