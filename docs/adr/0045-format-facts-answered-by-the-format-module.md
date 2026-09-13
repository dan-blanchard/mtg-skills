# Format facts are answered by the Format module, never re-derived from a table

Adding Arena's Competitive Brawl took three commits and 25 files (c0290e0a, fac7acd4,
ede6cb43): `format_config.FORMAT_CONFIGS` was a 13 × 17 table of flags with no behaviour,
so six modules re-derived "is this record legal here" (`legality_audit`,
`build_rarity_index`, `card_search`, `find_commanders`, `is_commander`, the deck-forge
staples pool), four re-derived the medium and deck-size rules (`state.py`, `app.py`,
`engine.py`, and `deck_tune` importing the hub's private `_default_medium`), the tuner
kept its own CR-citation table, `mtga_import` its own deck-size table, and the SPA
hand-listed the family three times. Two of the six legality predicates never learned the
Competitive Brawl override, so `card-search` and `find-commanders` hid cards
`legality-audit` accepted. The 2026-09-12 architecture review rated this the top
deepening candidate.

**Decision.** One module, `mtg_utils.formats`, owns every format question behind a frozen
`Format` value (`FORMATS[name]`, `get_format`, `Format.for_deck(deck_json)`):

- **Legality** — `Format.legality(record, *, unreleased=frozenset())` returns one status
  (`legal` / `restricted` / `banned` / `not_legal` / `unreleased`) with the Competitive
  Brawl override, the format's own ban list, and the Arena-pool gate folded in;
  `is_legal` is the strict bool. The pre-release widening stays a caller-side control
  (the Find surface's *include unreleased*), expressed as the caller passing the
  oracle-level set and reading `unreleased` back — never re-reading `legalities`.
- **Commander eligibility** — `Format.commander_eligibility(record, *, unreleased)`
  composes legality with a now format-free `card_classify.is_commander` (type line and
  text only; the planeswalker rule arrives as the format's flag). The `ignore_legality`
  escape hatch is gone with the gate that needed it.
- **Medium** — allowed media, default, `resolve_medium(override)`, and the medium →
  cost-mode rule. `DeckSession` keeps only the raw overrides; a deck JSON never carries
  a medium (it is a property of a build session, per deck-forge's CONTEXT).
- **Size** — fixed size, per-medium choices (paper Historic Brawl: 60 or 100), the CR
  citation for exact-size formats, and `for_deck` validation: a Commander-family deck
  declaring an impossible size raises; constructed formats accept any size (a 40-card
  limited deck borrows a constructed format's legality).
- **The SPA table** — `format_options()` is served in the snapshot; the Svelte
  hand-lists read it.

**The Arena gate moved, not its semantics.** The MTGJSON adapter used to rewrite
legalities to `not_legal` for Arena-defined keys when no printing existed on Arena. It
now emits the oracle-level fact (`arena_available`, any printing on Arena) and the
legalities verbatim; `Format.legality` gates on the field for the formats whose card pool
is Arena's (`arena_pool`: brawl, historic_brawl, competitive_brawl, alchemy, historic,
timeless — exactly the keys the adapter gated, since Standard and Pioneer are
paper-defined pools Arena mirrors). Medium-independent, as before. A record without the
field carries no evidence and is not gated. The adapter also emits `reprint` from
MTGJSON's `isReprint`, making the J21/JMP draft-rarity guard in `CardPool.rarity_index`
live (it had read a field the adapter never produced).

**Considered and rejected.** Free functions over the dict (callers still hold a string
and a bag of keys — a seventh interpreter); a per-record Arena gate on `games` (per
printing, so search's cheapest-printing dedup would mark Arena-available cards
`not_legal`); a `medium` field in the deck JSON (a second source of truth the session
would reconcile); a data file for the Competitive Brawl ban list (one adapter is a
hypothetical seam).

**What this stops re-suggesting.** Don't read `legalities[...]` or a format flag at a
call site to decide legality, medium, size, or family — ask the `Format`. Don't add a
format-name tuple or if-chain anywhere (`fmt == "historic_brawl"`): put the fact on the
table row and the behaviour on the value. Don't mirror the format table in the SPA; read
`format_options`. `combo_search._is_format_legal` reads Commander Spellbook's own
legalities record and is deliberately outside this module.
