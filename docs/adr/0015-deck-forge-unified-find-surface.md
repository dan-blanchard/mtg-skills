# deck-forge merges Search and Synergies into one Avenue-driven Find surface

The browser SPA shipped two card-finding tabs that were projections of the same
underlying scoped Signals. The **Synergies tab** (`Packages.svelte`) rendered each
signal as a package — a named header plus a candidate grid — via `api.packages()`
("Discover all") or a single explored package via `api.explore(label, search)`. The
**Search tab** (`SearchPanel.svelte`) ran a free-form `api.search(filters)`. The
**Avenues panel** already listed every lane as a chip and, on click, drove the
Synergies tab. So "a lane," "a package," and "an avenue" were three names for nearly
one thing, and a Candidate's `synergy_fit` (the ✦ on each tile) counted *every*
auto-extracted lane — including ones that merely happened to occur in a card already
in the deck — which read as noise.

**Decision.** One **Find surface** replaces both tabs.

- **Focused avenues drive the search.** A pin/focus toggle on each Avenue chip marks
  the lanes the human is actually building toward. Focusing one or more avenues
  OR-combines their `serve` specs into the search (oracle/type unioned, color identity
  unioned), runs **one** search, and returns a single flat ✦-ranked list. There is no
  per-package grouped presentation.
- **Synergy fit is scoped to the focused set.** When ≥1 avenue is focused,
  `synergy_fit` counts only focused avenues, so the ✦ reads "serves N of your M focused
  lanes." The empty focus set is the default and means *everything counts* (today's
  behavior) — focusing is purely opt-in narrowing.
- **One search path.** `explore` folds into `search`: focused-avenue serve-specs become
  an extra OR'd oracle/type constraint, user filters AND on top, and paging is unified.
- **Instant client-side facets.** On top of the returned list, chip facets for **type,
  CMC, and price** narrow results without a round-trip. (Role facets were considered and
  dropped — three facets cover the real refinements; more is clutter.)

**Why dissolve the package grouping rather than keep it.** Grouped packages keep two
scoring stories alive at once — package membership *and* synergy_fit — which is most of
the confusion the change exists to kill. A single flat list makes the filter state and
the ✦ number tell one consistent story: these lanes are focused → these cards rank →
here they are.

**What we give up, and how it's recovered.** The flat list loses today's "Discover all"
serendipity (scanning many named packages you didn't ask for). That is recovered by the
**Avenues panel itself** — it already names every lane; "focus all" + sort-by-✦
reproduces the same discovery inside the unified list.

**What this stops re-suggesting.** Don't reintroduce a separate Synergies/Packages tab
for "grouped" browsing, and don't keep `explore` as a parallel endpoint to `search`
(the split is exactly the two-path complexity this removes). Weighting (boost focused
lanes while still counting the rest) was rejected in favor of filtering (focused set is
the whole basis) — a boost keeps the noisy long tail in the number.
