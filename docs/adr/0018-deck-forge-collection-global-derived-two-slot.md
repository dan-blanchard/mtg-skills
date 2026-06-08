# deck-forge collections are global, two format-keyed slots, with derived (not stored) ownership

Bringing ownership into deck-forge is genuinely new state — `ForgeState` / `DeckSession`
knew only deck zones. The `mtg_utils` CLIs model ownership as a stored `owned_cards`
field that `mark_owned` writes into a deck JSON: a frozen snapshot of one deck × one
collection intersection. That model doesn't survive contact with a live, multi-build,
multi-format hub, so three forks had to be decided.

**Decision.**

- **Global, not per-build.** A **Collection** is the user's *library* — it doesn't change
  when you switch which deck you're forging — so it lives on `ForgeState`, persisted in
  one `collection.json` (a sibling of `BuildStore`), auto-loaded on launch.
- **Two slots, medium-keyed.** `paper` and `arena`, because the two real libraries are
  distinct. The active slot is auto-picked by the build's **medium** (digital → arena,
  paper → paper). Reads are **strictly single-slot** — a paper deck never consults the
  Arena slot — and an empty active slot prompts an import, never a silent "owns nothing."

  > **Amendment.** This was first keyed off *format* via `engine.paper_only` (commander →
  > paper; brawl/historic_brawl → arena). When Brawl/Historic Brawl gained a paper/digital
  > **medium** toggle (a paper Historic Brawl is the legal paper "Brawl"), the slot — and
  > the cost mode (digital → wildcards, paper → USD) — moved to keying off medium, not
  > format, so a *paper* Historic Brawl correctly reads the paper slot. See the **Medium**
  > glossary term.
- **Derived, not stored ownership.** A deck card's **Owned** flag is computed fresh on
  every snapshot (live deck × active slot, reusing `mark_owned`'s DFC / Arena-alias
  matching) and surfaced in `deck_view` — never persisted onto the build. The collection's
  normalized lookup is precomputed once at import and cached on `ForgeState`, so each
  snapshot stays O(deck-size).

**Why not per-build, or the stored `owned_cards` field.** The CLI's stored field goes
stale the instant the deck mutates — and here the deck mutates constantly — so it would
silently misreport ownership. Per-build ownership would duplicate the same library across
every build and desync. Deriving keeps it always-correct for one cheap O(deck) pass.

**Why not a single collection.** One slot would force a re-import every time you switch
between a paper Commander build and an Arena Historic Brawl build, and would cross-
contaminate ownership across pools that are genuinely different. Format already cleanly
partitions paper vs. Arena (`paper_only`), so the slot auto-picks with zero extra choice
at read time.

**Consequences.** **Commander discovery** and the "Owned only" Find facet both read this
same active-slot derivation. Discovery ranking is intent-driven (**Support depth** /
**Novelty**), never EDHREC popularity — an application of ADR-0009, not a new decision.
See the **Collection**, **Owned**, **Commander discovery**, **Support depth**, and
**Novelty** glossary terms in `deck-forge/CONTEXT.md`.
