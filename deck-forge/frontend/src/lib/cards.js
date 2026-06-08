// Card-display helpers shared across the SPA.

// Render a card name the way players say it. Scryfall joins the faces of a split /
// transform / MDFC / adventure card with " // " (e.g. "Odds // Ends"), but at the
// table everyone says "Odds / Ends" — a single slash. DISPLAY-ONLY: never feed the
// result back to the add/remove/search APIs, which match the canonical " // " name.
export function displayName(name) {
  return (name || "").replace(/ \/\/ /g, " / ");
}
