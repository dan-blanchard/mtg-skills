# Attributed art is mined from multiple sources with per-source license stance

The attributed catalog (see ADR 0006) was originally populated by a single
source: asciiart.eu, whose FAQ explicitly grants reuse with artist
attribution. A single source kept `art_fetcher.py` simple and made the
license note trivially correct — every `.txt` could cite the same FAQ
URL. Coverage stalled at 71 subtypes.

Adding Christopher Johnson's collection at asciiart.website roughly
doubled the candidate pool (1721 → 3001 cards) and pushed coverage to
124 subtypes (+75%). But asciiart.website's "FAQ" is an archived 1994
usenet document, not a site license — it explicitly says "ask permission
before using". The site does not grant blanket reuse with attribution
the way asciiart.eu does. Treating it the same in our license header
would be misrepresenting the permission status.

**Decision 1 — Maintain two sources side-by-side.** `art_fetcher.py`
carries two HTML parsers (`_parse_cards`, `_parse_cards_website`), two
URL builders, and a filter for the auto-discovered asciiart.website
tags. `build_pool` mines both and returns a unified pool of dicts
tagged with a `_source` discriminator. Selection (size scoring + title
match) is source-agnostic — whichever piece scores best wins regardless
of where it came from.

**Decision 1a — Mine asciiart.website by tag, not by category.** The
site exposes both `cat.php?category_id=N` (~635 categories, broad media
groupings) and `tag.php?tag_id=N` (~1148 tags, per-concept). Category
names conflate concepts with franchise universes — the "Lions"
category and "Lion King" category are sibling entries on the same
browse view, and you can't tell them apart until you scrape and look
at the cards inside. Tags, by contrast, are per-concept: a clean
"Lion" tag is distinct from "Lion King", "Panther" from "Pink
Panther", "Dragon" (89 pieces) from "Dragon Ball" (6 pieces). Same
page structure (CollectionPage JSON-LD + inline `<pre>` bodies), so
`_parse_cards_website` works unchanged.

**Decision 2 — Per-source license headers, not a unified template.**
`write_art` branches on `_source` and writes different third-header
lines:

- asciiart.eu: `# Used with attribution per https://www.asciiart.eu/faq`
- asciiart.website: `# Personal-use proxy; artist credited (no explicit
  license grant from source).`

Both formats end with a blank line so `proxy_print._try_read_attributed`
parses them identically — it strips `#`-prefixed header lines until a
blank, then reads the body, and pulls the artist name from the first
header line's `(by <name>)`.

**Why these together:** Single-source would have kept the license note
correct by construction (one license to cite), but at the cost of
permanent coverage gaps. Multi-source unlocks coverage but only if each
source carries an honest license stance. Pretending asciiart.website
granted a license it didn't would have been a quiet integrity bug — the
.txt files would assert a permission grant that doesn't exist. The
honest per-source header keeps the catalog defensible for personal-use
printing while not overstating the legal posture.

**What we considered:**

- **Single source (status quo before this change).** Rejected — the
  coverage gain (71 → ~130 attributed subtypes) was load-bearing for
  the user's actual proxy-printing use case.
- **Treat asciiart.website the same as asciiart.eu.** Rejected — the
  third header line would assert a license that doesn't exist. Quiet
  integrity bugs in licensing claims are the kind of thing that becomes
  a real problem later.
- **Email Christopher Johnson for blanket attribution permission, then
  ship asciiart.website with the same header as asciiart.eu.** Out of
  scope for this PR; revisit if/when usage grows.
- **Mine asciiart.website by category instead of tag.** Initial design.
  Rejected after observing systemic franchise pollution — "Lion King"
  passes any keyword filter that admits "Lion", "Pink Panther" passes
  one that admits "Panther", etc. Required a fragile denylist that
  fought the data model. Tags side-step the problem because they're
  per-concept by construction.
- **Use asciiart.website's search endpoint per subtype.** Considered as
  an alternative to bulk-fetching. Rejected because the search page is
  JS-driven (no useful HTML in the initial response); the tag taxonomy
  achieves the same per-concept slicing without needing a JS runtime.
- **Adapter Protocol abstraction (like `_stores/StoreSession`).**
  Deferred per ADR 0004 — exactly one branch in the codebase keys on
  `_source` today (`write_art`). Refactor when a third source forces the
  question; until then, the conditional is cheaper than a Protocol.

**What this stops re-suggesting:**

- "Let's pick one source and rip out the other for simplicity." See
  Decision 1 — the coverage delta is large and the parsers are both
  small. Single-source costs ~50 attributions and many of the
  highest-quality artist-credited pieces (Shanaka Dias's dragon,
  H.P. Barmario's wizard, Colin J. Randall's knight).
- "Why doesn't asciiart.website's header cite the FAQ like asciiart.eu's
  does?" The FAQ page on asciiart.website is an archived usenet doc, not
  a site license. Citing it would misrepresent the permission status.
- "Why aren't the parsers Protocol-based?" One branch in one function
  isn't a pattern; it's a switch. Revisit when a third source lands.
