# Ownership is a medium rule with one owner

Every cost and "can I build this" read asks how many copies of a card a collection
covers. Before this, only `price-check` answered with any care. The tuner's two purses
treated an add as free whenever one copy was owned, whatever copy number it was, and
the swap said "owned". deck-forge's browser summed wildcards and the unowned USD total
itself, and its owned tick, "N of M owned" count and Owned-only facet read "owned at
all" as "covered". `lgs-search` subtracted collections with its own arithmetic.

**Decision.** `Format.coverage(medium, name, needed, owned, *, requested_owned)` owns
the rule, beside `Format.cost_mode`, because what ownership means depends on the medium
(ADR-0052's medium facts). It returns a `Coverage`: the copies still to acquire, and
why a covered entry is covered (`"free"` or `"owned"`). `Format.copies_short` is its
`short`.

- **Basic lands are free, in any quantity** (`card_classify.BASIC_LAND_NAMES`, the six
  basic land types). On Arena there is no exception: its basic styles are cosmetic,
  and an import falls back to the default. In paper the one exception is a deck entry
  asking for a SPECIAL printing, decided by `is_special_basic_request(name, request,
  printing)` from the requested printing's own record: a foil or etched finish,
  full-art, borderless, a showcase / extended-art (or other special) frame, a promo, or
  a visual promo type (`boosterfun` and the named foil treatments; distribution tags
  such as `universesbeyond`, `bundle` and `startercollection` ride on ordinary basics
  and don't count). A special request is covered only by that exact printing — the
  pinned set and collector number, and foil copies when a foil finish is asked for — so
  a collection that lists basics by name only, or not at all, holds none of it. A
  plain set and collector pin ("Forest (M21) 274" from an export) stays free.
  Snow-Covered basics are different cards, not printings of a basic land type, so they
  are collected like any card.
- **On Arena, owning four copies of a card covers any quantity** (`ARENA_PLAYSET`). It
  only changes anything for a card a deck may run more than four of: four Hare Apparent
  ("any number") fill seventeen slots, four Seven Dwarves ("up to seven") fill seven.
  This is a rule of the MTG Arena client, not the Comprehensive Rules; Dan confirmed it
  in play.
- **Otherwise you have what you own.**

Printing-level ownership lives in the neutral `mtg_utils.ownership` (the CLIs and the
hub both import it; nothing imports the hub, ADR-0050): a collection's per-printing
detail (`printing_index`, and `printing_rows`, which `mark-owned` writes onto
`owned_cards` rows and `price-check` reads back), a deck entry's printing request
(`printing_request`), and `requested_printing_owned`, which asks the predicate and
consults the detail only for a special request. The MTGJSON adapter carries each
printing's style (`full_art`, `border_color`, `frame_effects`, `promo`, `promo_types`;
bulk sidecar v4, announced on stderr as a one-time rebuild).

Every reader goes through the owner:

- `price-check`: the medium is the Format's (`resolve_medium`, then `cost_mode` picks
  wildcards or USD); a paper deck line's set / collector pin resolves to its printing
  through `CardPool.printing_at`.
- the tuner: `propose_swaps` decides coverage once per added copy; the purse prices
  only uncovered copies, and the swap's `owned` is that same decision.
- deck-forge: `engine.coverage` serves each deck row's `copies_short`, `covered_by` and
  `owned` flag (a paper row's pinned printing and finish are its request);
  `engine.candidate_coverage` serves Find results and combo pieces (one copy to add);
  the footer's wildcard total and the "N of M owned" count are sums of the rows; the
  browser only reads what it is served.
- `lgs-search`: collection subtraction is paper `copies_short`.

`mtga-import` no longer writes basic lands into `collection.json` at quantity 99, and
the Arena rarity index no longer carries a `free` flag: the owner is the one encoding
of a free basic.

**Consequences.** A new reader of a collection calls `Format.coverage`; nothing
compares `owned` to `needed` or `4` itself. Paper `price-check` stops charging for
basic lands the collection doesn't list, unless the deck asks for a special printing
of one. The agent-facing skills (deck-wizard, deck-forge, lgs-search) state the rule
for reasoning done by hand.
