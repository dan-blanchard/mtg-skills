// Card-display helpers shared across the SPA.

// Render a card name the way players say it. Scryfall joins the faces of a split /
// transform / MDFC / adventure card with " // " (e.g. "Odds // Ends"), but at the
// table everyone says "Odds / Ends" — a single slash. DISPLAY-ONLY: never feed the
// result back to the add/remove/search APIs, which match the canonical " // " name.
export function displayName(name) {
  return (name || "").replace(/ \/\/ /g, " / ");
}

// A basic land, by its type line (CR 205.4c: the basic supertype is what makes the
// unlimited-copies and pool-containment exemptions apply).
export function isBasicLand(card) {
  return /\bBasic Land\b/.test(card.type_line || "");
}

// The copies of each name the build holds across every zone the copy limit spans —
// the same count the hub's rule reads, so the stepper and Find agree.
export function heldCopies(deck) {
  return [
    ...(deck.commanders || []),
    ...(deck.cards || []),
    ...(deck.sideboard || []),
    ...(deck.companion || []),
  ].reduce(
    (m, c) => m.set(c.name, (m.get(c.name) || 0) + (c.quantity || 1)),
    new Map(),
  );
}

// Whether the build may hold one more copy of a served card row. The hub serves
// `copy_limit` on every deck / Find / card row (`engine.copy_limit`: the format's
// cap, a restricted card's 1, a named cap, the pool's count for a sealed / draft
// build; null = unlimited) — the SPA never re-derives the exemptions.
export function canHoldAnother(card, held) {
  const limit = card.copy_limit;
  if (limit === null || limit === undefined) return true;
  return held < limit;
}

/** A 0–1 share as a one-decimal percent ("—" when unknown) — the Meta panel's and
 * the Tune scorecard's meta block's one formatter. */
export function pct1(x) {
  return x === null || x === undefined ? "—" : (100 * x).toFixed(1) + "%";
}

/** How a deck matched its Arena meta archetype (ADR-0059): "71.0% overlap", or
 * "by commander" / "by named". */
export function matchLabel(match) {
  if (!match) return "";
  return match.by === "overlap"
    ? `${pct1(match.overlap)} overlap`
    : `by ${match.by}`;
}
