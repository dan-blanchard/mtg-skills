# A commander's signal extraction folds in the referenced objects its plan brings into play

`signals.py` derives a commander's avenues from its own oracle text. But some of a
commander's strongest, most-included cards are explained by an object the commander
**deterministically brings into play**, whose effects live on a *separate* card. *Acererak
the Archlich*'s decks run *Demon's Horn* (gain life when a black spell is cast) — and from
Acererak's own text that looks like a generic mono-black "color staple," which is exactly
what it was first dismissed as. It isn't: Acererak ventures into **Tomb of Annihilation**,
whose rooms read "Each player loses 1 life", "…loses 2 life unless they sacrifice…" — a
repeated self-bleed, so the deck wants lifegain sustain. The synergy is fully mechanical;
it's just invisible from Acererak's card. A future reader (and the first analysis) will be
tempted to file every such card under "deck context, not oracle-derivable, out of scope."

**Decision.** A commander's signal extraction reads, in addition to its own card, the
rules text of its **folded objects** — persistent game-objects its own abilities reliably
bring into its core strategy:

- **Card-backed objects** (dungeons; later, anything else Scryfall links) are discovered
  through `all_parts` — the same structured link that finds a card's tokens
  (`deck.discover_tokens`) — then **joined and re-extracted**: the object's oracle is run
  back through the normal extractor so the existing scope rules and cross-opens decide the
  synergies, rather than importing the object's raw signals.
- **In-oracle objects** (a planeswalker's emblem — its effect is quoted inside the
  ultimate, e.g. Elspeth's "creatures you control get +2/+2 and have flying") are *already*
  read; the extractor needs no change for them. They are documented as the same concept so
  no one re-builds machinery for a case that already works.

Gated three ways: the object must be (1) brought in by the commander's **own** text as its
**plan** (not a one-off reference), (2) carry its **own rules text**, and (3) be folded by
**append-and-re-extract**. Which dungeon to fold is **disambiguated by the commander's
oracle**: Acererak names *Tomb of Annihilation* (its ETB only stops bouncing him once ToA
is *completed*), and the Initiative is rule-fixed to *Undercity*. A generic "venture into
the dungeon" names nothing, so **no specific dungeon is folded** — broad `venture` support
covers it.

**Why this is the right call.** The goal is to alleviate the need to consult EDHREC for
synergies that are *mechanically the commander's plan* — and these are exactly that, merely
printed on a second card. `all_parts` is the right discovery surface because it's
structured (reuses the token walk) and robust where prose-scraping "venture into <name>"
is brittle. **Re-extraction, not raw-signal import,** is load-bearing: Tomb of Annihilation
loses *each player* life, so a naive import would conclude "Acererak wants opponents to
lose life"; running the text through the extractor lets the self-bleed→lifegain cross-open
reach the correct conclusion — sustain, not a drain payoff. And the **oracle
disambiguation** keeps us inside the gate that separates this tool from "EDHREC with extra
steps": `all_parts` lists *all three* D&D dungeons for every venture card (Acererak,
Nadaar, and Sefris are identical there), so choosing one for a *generic* venturer would
require popularity data — the one signal we refuse. Picking only the oracle-named /
rule-fixed dungeon keeps every folded avenue derivable from the card in hand.

**What this stops re-suggesting.** Before filing an off-card, high-synergy card as
"non-mechanical / deck-context / out of scope," rule out all three of: a **detector
phrasing miss**, a **folded object** (this ADR), and a **multi-step chain** — the
truly-non-mechanical residue (genuine popularity-only color staples) is small, and a card
may not be put there without that trace. Don't prose-scrape the dungeon name (use
`all_parts` to discover, oracle to disambiguate). Don't fold *all* of a venturer's
`all_parts` dungeons — that over-fires; it lists the rules-legal set, not the deterministic
one. Don't "fix" generic venturers by folding a popular dungeon — generic venture having no
specific folded dungeon is deliberate, not a gap. Don't rebuild folding for emblems — their
text is already in-oracle and read. If a new object class appears (the Ring's levels are
the obvious next instance; it is neither a card nor in `all_parts`, so it needs a small
hardcoded definition), add it against the three gates rather than widening to "fold any
card a commander references."
