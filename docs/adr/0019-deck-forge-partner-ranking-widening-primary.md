# deck-forge partner ranking is widening-primary and strict-tiered (colors before synergy)

The Partner / Background avenue surfaces cards legally eligible to be the deck's second
commander (CR 702.124, color-agnostic via `valid_partner_search`) and ranked them through
the generic `rank_candidates` tuple `(synergy_fit, price, cmc)`. The user observed that
the dominant reason to add a partner is usually to **widen the color identity** so more of
the *original* commander's strategy becomes accessible — and that pure-synergy ranking
buries exactly those color-opening partners.

**Decision.** For the partner avenue only — a second commander is the *only* card that can
change a deck's color identity, so this axis exists nowhere else — the sort key becomes:

> **(additional colors unlocked, desc) → (synergy_fit, desc) → (price asc → cmc asc)**

**Color widening** is the raw count of NEW colors the candidate adds to the deck's current
identity (`partner.color_identity − deck identity`), **unbounded** (a five-color opener
tops a two-color one), and **strictly dominant**: a high-widen / low-synergy partner
outranks a low-widen / high-synergy one. Synergy only orders partners *within* a widening
tier.

**Considered and rejected.**

- **Synergy-primary (the previous behavior)** — buries the color-openers, which are the
  whole point of most partner picks.
- **"Synergy-unlocked" widening** — measure the *cards* in the newly-added colors that
  would serve the deck's lanes, instead of counting colors. Sound in principle, heavier in
  compute, and ultimately not the ask: the user wants to rank by *how many colors* open,
  then sort by synergy within that. Dropped.
- **Dominant weighted blend** (`W·colors + synergy_fit`) — introduces an indefensible
  magic weight. Strict tiers are transparent and drop straight into `ranking.py`'s
  existing tuple-sort idiom (a one-element extension of the sort key).

**What this stops re-suggesting.** Don't "fix" the partner sort back to synergy-primary
because a no-synergy five-color partner topping a high-synergy two-color one *looks*
wrong — that ordering is deliberate. Don't reintroduce synergy-unlocked widening; it was
weighed and dropped. See the **Color widening** glossary term in `deck-forge/CONTEXT.md`.
