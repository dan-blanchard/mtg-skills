// Card-display helpers shared across the SPA.

// Render a card name the way players say it. Scryfall joins the faces of a split /
// transform / MDFC / adventure card with " // " (e.g. "Odds // Ends"), but at the
// table everyone says "Odds / Ends" — a single slash. DISPLAY-ONLY: never feed the
// result back to the add/remove/search APIs, which match the canonical " // " name.
export function displayName(name) {
  return (name || "").replace(/ \/\/ /g, " / ");
}

// How many copies of a card the build may hold, mirroring the hub's copy rule
// (`engine.copy_limit`): a basic land or an "any number of cards named X" card
// (Relentless Rats, Shadowborn Apostle, Dragon's Approach…) is unlimited, every
// other card takes the served format's max_copies (1 singleton, 4 constructed).
// The hub stays the judge (a restricted card's 1, a named cap) — this only decides
// which affordances to show.
export function copyLimit(card, maxCopies) {
  if (/\bBasic Land\b/.test(card.type_line || "")) return Infinity;
  if (/a deck can have any number of cards named/i.test(card.oracle_text || ""))
    return Infinity;
  return maxCopies;
}
