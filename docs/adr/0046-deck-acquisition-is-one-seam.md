# Deck acquisition is one seam: a deck JSON becomes a HydratedDeck through the CardPool

The 2026-09-12 architecture review found the deck CLIs re-plumbing the same preamble
twelve times under five argument conventions: `parse-deck` wrote `deck.json`,
`scryfall-lookup --batch` wrote a SHA-keyed `hydrated-<key>.json` somewhere else, and
every analysis CLI took both paths. Four of the twelve re-read both files with
`json.loads` instead of `HydratedDeck.from_paths`. The hydrated file was a 23-field
None-filled projection (`CARD_FIELDS`) while deck-forge's hub joined the bulk's full
adapter records, so the two paths saw different record shapes — the P/T gates and the
`edhrec_rank` fringe logic were both dead in production for a field the projection had
omitted while passing unit tests built by hand. Five call sites loaded the bulk and
built a name index with four different policies (cheapest printing / first-seen /
prefer-oracle-text / cheapest-plus-token-skip); the rarity index, unreleased set,
printing indexes, object resolver, and Arena alias map each walked the bulk from their
own module. The batch hydrator walked three zones, so the CLI path never hydrated the
companion zone and `check_companion` could not fire from a CLI. deck-wizard's Step 1
was six invocations, and both SKILL.md files carried a "re-hydrate and switch to the new
`cache_path` after every edit" rule to keep the file in sync.

**Decision.** Two modules own acquisition; everything else reads through them.

- **`card_pool.CardPool`** is the one owner of the bulk and every index over it:
  `CardPool.load(bulk_path)` (`None` auto-discovers the MTGJSON bulk per ADR-0033; no
  bulk raises `NoBulkError` naming `download-mtgjson`) and lazily-built, memoized
  `by_name` / `by_id` / `rarity_index(fmt)` / `unreleased_ids` / `name_aliases` /
  `printings_by_oracle` / `printing_by_id` / `resolve_object`. The name index has ONE
  policy: the cheapest priced game-layout printing, a text-bearing printing beating a
  text-less placeholder, tokens and memorabilia never (they stay reachable by id). The
  four policies it replaces differed on two names in the whole bulk.
- **`HydratedDeck.acquire(deck_path, *, pool, bulk_path, require_records, fetch)`** is
  the deck-acquisition seam. It reads the deck, joins all four zones (companion
  included) against the pool, tries Scryfall's per-card endpoint once per pool miss
  (ADR-0005's cache-miss carve-out, unchanged), and memoizes the join in a sidecar
  beside the deck: `deck.json` → `deck.hydrated.json`, keyed inside the file by the
  deck's content hash, the bulk's identity, and the payload version. A stale sidecar is
  unreadable by construction; there is no cache path to thread. The one carve-out:
  with no bulk on disk, a names-only CLI (`require_records=False`) reads a sidecar
  of the same deck content whatever bulk wrote it — a join of this deck beats none. `from_paths` is
  retired; `from_parsed` and `from_session` stay.
- **One record shape.** A record is the bulk's own adapter record — keys absent when the
  card has no such field — on every path. `CARD_FIELDS` and the None-filled projection
  are deleted; the single-card CLI and `card-search --json` keep a terminal-sized
  `display_fields` projection for output only.
- **One CLI convention.** Every deck CLI takes `DECK_JSON` and the shared `--bulk-data`
  option (`deck_cli.bulk_data_option`, default auto-discovered) and calls
  `deck_cli.acquire_for_cli`, which turns `NoBulkError` into a `ClickException` and
  warns once on stderr about names the join dropped. `combo-search` passes
  `require_records=False` (it works on names alone); `export-deck` needs no card
  records at all, so it reads the deck JSON directly and takes no `--bulk-data`;
  `price-check` prices name lists and cube JSON as well as decks, so it takes the
  shared option (auto-discovered) but prices names itself, warning once when there
  is no bulk and every name goes to Scryfall. `deck-hydrate <deck.json>`
  is the explicit warm step: it builds the sidecar and prints the envelope (sidecar
  path, card count, missing names, type/curve digest) that `scryfall-lookup --batch`
  used to print. `scryfall-lookup --batch` serves name lists (and cube JSON — the cube bounded
  context below) only.
- **The hub** builds `ForgeState` from one `CardPool` in `production.py`; the state's
  fields stay (populated from the pool) so `app.py` / `engine.py` do not churn.

**Scope (the explicit no).** `mtga-import`'s `arena_id` index and lgs-search's lookup
stay where they are: different keys, one consumer each — a hypothetical seam until a
second consumer appears. Cube-wizard's flat pool is a different bounded context
(ADR-0012's scope note stands).

**Considered and rejected.** Loading the bulk in every CLI with no sidecar (warm load is
sub-second, but the sidecar is what lets an agent Grep the deck's oracle text and what
keeps `card-summary`'s table instant); a global hash-keyed cache directory (invisible
to the agent, and needs a `--cache-dir` option on every CLI again); keeping an explicit
`--hydrated PATH` override (a permanent second shape on every CLI); a projection with
absent-key semantics (a third omission bug stays possible); collapsing `ForgeState`'s
index fields onto `state.pool` now (a large hub diff while the CLI side is also moving).

**Amends.** ADR-0012's construction adapters are now `acquire` / `from_session` /
`from_parsed` (`from_paths` retired). ADR-0005's `scryfall_lookup` carve-out is now the
`fetch_card` seam `acquire` calls; nothing else changes.
