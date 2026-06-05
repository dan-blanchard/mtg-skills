// MTG color metadata for pips, curve tinting, and color-source readouts.

export const COLOR_ORDER = ["W", "U", "B", "R", "G", "C"];

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
