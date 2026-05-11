# Attributed art catalog ships empty and interleaves with the local catalog per-slug

The proxy renderer reads ASCII art from two tiers: a hand-curated
**local catalog** committed to the repo at
`mtg-utils/src/mtg_utils/data/card_art/*.txt`, and an **attributed
catalog** at `$MTG_SKILLS_CACHE_DIR/attributed-art/` whose files carry a
3-line license header and propagate an artist credit to the rendered
proxy. Two architectural choices about the attributed catalog are
load-bearing enough to record here, and they only make sense together.

**Decision 1 — Attributed catalog ships empty.** The repo commits
nothing under `attributed-art/`. Users populate it themselves by
running `fetch-art`, which scrapes asciiart.eu under that site's
FAQ-granted reuse-with-attribution license. The renderer degrades
gracefully when the catalog is empty — every lookup falls through to
the local catalog or `_generic.txt`.

**Decision 2 — Lookup interleaves per-slug, not per-tier.** For each
subtype slug in the type line, the chain tries `attributed/<sub>`
then `local/<sub>` before moving to the next subtype. After all
subtypes miss, each card-type slug runs the same `(attributed, local)`
pair. Final fallback is `local/_generic.txt`. This is *not* an
attributed-tier-then-local-tier global sweep.

**Why these two together:** Decision 2 only makes sense in a world
where the attributed catalog is sparse — a hand-curated `local/vampire`
beats a generic `attributed/creature` because the local subtype hit is
more specific than an attributed card-type hit. And Decision 1 only
works because Decision 2 gracefully degrades: an empty
`attributed/vampire` doesn't punch through to `_generic`; it falls to
the next slug attempt and almost always finds `local/vampire`. Split
them and the design collapses:

- Ship empty + tier-first lookup: every render would skip straight from
  empty-attributed to local — fine, but the per-slug interleave buys
  nothing.
- Ship populated + per-slug interleave: the repo now has hundreds of
  scraped files in git, doubling its size and forcing us to re-vet
  licensing every time `fetch-art` improves its scoring.
- Ship populated + tier-first lookup: a single attributed-art entry for
  a generic card-type (e.g. `attributed/creature`) would beat *every*
  hand-curated local subtype — almost certainly the wrong call.

**What we considered:**

- **Single-tier**: drop the attributed catalog, hand-curate everything,
  no artist credit. Rejected — the local catalog took weeks to reach
  98.5% blind-test pass rate, and the user wanted real artist
  attribution on the printed PDF.
- **Global tier order** (attributed-first across all slugs): rejected
  per the worked-example above.
- **Ship a starter populated catalog**: rejected because (a) it puts
  licensed third-party art in git, (b) `fetch-art` is cheap to re-run
  with its 7-day HTTP cache, and (c) the attributed catalog is morally
  a cache, not a source artifact.

**What this stops re-suggesting:**

- "Let's commit the attributed catalog so the repo works out of the
  box." No — see Decision 1; the renderer already works out of the
  box via the local catalog. `fetch-art` is the population path.
- "Why doesn't `lookup_art` just check all attributed files first?"
  See Decision 2 and the worked example — global tier order would let
  a generic attributed entry override a specific hand-curated local
  entry.
- "Can we extend this to other art sources?" Yes, in principle —
  anything that emits the 3-line license header and lands under
  `$MTG_SKILLS_CACHE_DIR/attributed-art/` participates. The lookup
  chain is source-agnostic; only `fetch-art` knows about asciiart.eu.
