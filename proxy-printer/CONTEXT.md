# proxy-printer Context

The bounded context for rendering printable PDF proxies of MTG cards
and tokens, with ASCII art chosen per card subtype and optional
attributed art that carries an artist credit through to the printed
proxy.

## Language

### Art catalogs

**Local catalog**:
The hand-curated ASCII art that ships in the repo at
`mtg-utils/src/mtg_utils/data/card_art/*.txt` — one file per card
subtype plus card-type fallbacks and a `_generic.txt` ultimate
fallback. ASCII-only, no attribution header, no artist credit
rendered.
_Avoid_: "default catalog" (implies an out-of-the-box vs custom
distinction the renderer doesn't make — both tiers participate in
every lookup), "built-in art".

**Attributed catalog**:
The user-populated ASCII art at `$MTG_SKILLS_CACHE_DIR/attributed-art/`
(default `~/.cache/mtg-skills/attributed-art/`). Each `.txt` carries a
three-line header (title, source URL, attribution-license note)
followed by the art body. When the lookup hits this tier the proxy
renders `art by <Name>` in the footer slot. Ships **empty**; populated
by the `fetch-art` CLI.
_Avoid_: "external catalog" (it's local on disk, just user-populated),
"asciiart.eu catalog" (the tier is source-agnostic; `fetch-art` mines
multiple **Source**s and stamps each file's header with the right
per-source attribution).

**Source**:
A single upstream provider of ASCII art that `fetch-art` mines. Each
source has its own URL builders, HTML parser, and attribution-header
format. Today's sources: asciiart.eu (curated category list + optional
search fallback) and asciiart.website (Christopher Johnson's
collection — ~1148 **tags** auto-discovered from
`browse.php?show=tags`, per-piece JSON-LD metadata). Tags are used
rather than categories because tag names map directly to MTG concepts
("Lion" vs "Lion King", "Panther" vs "Pink Panther"). Cards in the
candidate pool carry an internal `_source` tag that selects the
correct header in `write_art`. The two sources' license stances differ
(asciiart.eu grants FAQ-attribution reuse; asciiart.website does not),
so `write_art` writes different third-header lines accordingly.
_Avoid_: "site" (ambiguous; the attributed catalog itself isn't on the
internet), "provider" (overloaded with payment / oauth).

**Fetcher**:
The seam between art-fetching logic and HTTP. A `Fetcher` is anything
satisfying `fetch(url, cache_key, *, throttle, max_retries) -> bytes`.
Production code uses `HttpFetcher`, which wraps a private
`requests.Session` and owns freshness, retry, throttle, and disk-write.
Tests use `FakeFetcher`, a dict-backed in-memory adapter that maps URL
substrings to canned bytes. Callers (pool builders, tag-page
walkers, search fallback) accept a Fetcher rather than a Session, so
their tests don't have to fake HTTP at all.
_Avoid_: "transport" (overloaded with TLS / SMTP), "session" alone
(refers to `requests.Session`, which is now a Fetcher implementation
detail).

### Lookup

**Slug**:
The filesystem key derived from a subtype or card-type name —
lowercase, apostrophes dropped, every non-alphanumeric run collapsed
to a single `-` (`Urza's` → `urzas`, `Eldrazi Spawn` → `eldrazi-spawn`).
Both catalogs index by slug.
_Avoid_: "filename" (the slug is the *base* of the filename, without
extension or directory), "key" alone (ambiguous with oracle_id keys).

**Lookup chain**:
The ordered sequence of `(tier, slug)` attempts executed by
`lookup_art(type_line)`. Each subtype slug is tried as
`attributed/<sub>` then `local/<sub>` before moving to the next subtype.
After all subtypes miss, each card-type slug runs the same pair.
Final fallback is `local/_generic`. First hit wins.
_Avoid_: "tier order" (suggests a global tier-1-then-tier-2 sweep,
which is *not* how this works — the interleave is per-slug, not
across slugs).

**Lookup tier**:
The class of the slug that produced the hit, returned by `lookup_art`
as one of `"subtype"`, `"card-type"`, or `"generic"`. Independent of
which catalog (attributed vs local) the file came from.
_Avoid_: "level", "rank" (both suggest priority within a single
catalog, but the tier is about which *kind of slug* matched).

**Skip-subtype**:
A subtype the `fetch-art` CLI deliberately never writes a file for —
MTG-only mechanics (Saga, Treasure, Role, Class, …), plane / setting
names (Innistrad, Ravnica, …), and stop-words ("and", "of", "the").
These render via the card-type or generic fallback. Distinct from
the renderer's `_ART_SKIP_WORDS`, which filters meta-keywords
(Token / Legendary / Snow / Tribal / Basic) when *parsing* a type
line — the two lists protect different stages.
_Avoid_: "blacklist", "excluded subtype".

### Rendering

**Signature**:
The artist's initials or mark embedded **inside** the ASCII art body,
preserved verbatim during fetch. Per asciiart.eu's FAQ, a preserved
signature alone satisfies the attribution requirement; the explicit
artist-credit footer is courtesy on top of that.
_Avoid_: "watermark" (implies a separate overlay; the signature is
part of the art itself), "byline".

**Artist credit**:
The "art by <Name>" string rendered in the proxy's lower-left footer
when the lookup chain hit the attributed catalog. Extracted from the
catalog file's first header line (`# Title (by Artist Name (sig))`).
Renders on the same row as the P/T box, where real MTG cards place
the artist credit.
_Avoid_: "attribution" alone (the in-art signature is *also*
attribution; this term refers specifically to the rendered footer
string).

**Footer slot**:
The lower-left rectangle on the rendered card, between the inner-left
edge and the P/T box. Shared between two pieces of text and **never**
holds both: token source ("from: <card>" or "from: N cards") for
token proxies, and artist credit for cards whose art came from the
attributed catalog. When both apply, the token source wins because
the in-art signature already carries attribution.
_Avoid_: "footer" (ambiguous with the whole bottom row including the
P/T box).

## Relationships

- The **Lookup chain** queries both the **Attributed catalog** and the
  **Local catalog** per **Slug**, interleaved.
- A **Lookup tier** is independent of which catalog hit — `("subtype",
  attributed)` and `("subtype", local)` are both `subtype` tier.
- An **Artist credit** is rendered only when the **Lookup chain** hit
  the **Attributed catalog**.
- The **Signature** lives inside the art body regardless of catalog
  tier — but `fetch-art` only guarantees its presence in attributed
  files (the local catalog's hand-curated art may or may not carry one).
- The **Footer slot** is mutually exclusive: token source displaces
  **Artist credit** when both apply.
- **Skip-subtype** affects only `fetch-art`'s write-side; the renderer
  doesn't consult it (a skip-subtype like `treasure` simply has no
  attributed file, so the chain falls through).

## Flagged ambiguities

- **"attribution"** could mean the in-art **Signature** (legally
  load-bearing per asciiart.eu's FAQ) or the rendered **Artist credit**
  footer (courtesy). Both satisfy attribution; only the signature is
  required. The footer can be displaced (e.g. by a token source) without
  breaking the license.
- **"catalog"** alone is ambiguous between the **Local catalog** and
  the **Attributed catalog**. Use the qualified term in code, comments,
  and docs — the unqualified word almost always conceals a real
  ambiguity about which tier you mean.
