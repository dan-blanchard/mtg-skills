# One Scryfall name-index core: NFKD-folded lookups, consistent DFC handling

The "Scryfall name → record index" was hand-copied ~5 times — `scryfall_lookup._load_bulk_index`,
`build_rarity_index`, `card_classify.build_card_lookup`, `find_commanders._load_bulk_index`,
`deck.load_bulk_indexes`, plus `card_search`'s dedup and `mark_owned`'s alias lookup — each
re-deriving the canonical-name → DFC-face → Arena-alias keying with *subtly inconsistent* rules.
`find_commanders`' own docstring said *"Unlike scryfall_lookup's index…"*. The inconsistencies
were the bug, not policy: three builders folded with bare `str.lower()` (so an ASCII-typed
`Lim-Dul's Vault` silently MISSED the diacritic `Lim-Dûl's Vault`), DFC faces were handled four
different ways (front-only `' // '` split vs every-face `card_faces[]` walk; front-face as a
deduped canonical key vs an arbitrary-printing alias), and "cheapest" had two `None`-price
behaviors. Dual-faced and diacritic lookups had surfaced repeated silent misses across the skills.

## Decision

One keying core in `mtg_utils/_name_index.py`; the genuinely per-caller policy stays as knobs.

- **`alias_keys(card)`** — the folded `(key, tier)` pairs a card claims: canonical name, **every
  face** (`card_faces[]`, or `' // '` split fallback), en-gated Arena `printed_name` /
  `flavor_name`. Tiers order precedence: a real standalone card wins its name over another card's
  face over an Arena alias.
- **`NameIndex`** — a `Mapping` whose keys AND lookups are NFKD-folded (`normalize_card_name`), so
  an ASCII query matches the real diacritic card and vice-versa, while the stored record keeps its
  real diacritic name for display. **Folding is the type, not a knob** — call sites never fold by
  hand.
- **`build_name_index(cards, *, reduce, value, prefilter)`** — one consistent pass:
  standalone-wins + reduce-within-tier, so a face key points at (e.g.) the *cheapest* printing of
  its multi-face card, consistent with that card's canonical key. `keep_cheaper` unifies the
  acquisition cost ("a priced printing beats a price-less one; cheapest among priced").

**The folding principle (the headline fix).** Always NFKD-fold for lookups and matching — people
rarely type non-ASCII, but a diacritic query still works (both fold to one key); displayed names
keep their real diacritics, since that is the card's actual name.

## What is a knob (legitimate policy), what collapsed (accidental drift)

- **Knobs:** the `reduce` cost-mode (paper `keep_cheaper` USD vs Arena `_keep_lowest_rarity`
  wildcards — the *same* "what it costs to acquire", switched by medium; plus `deck`'s
  prefer-has-oracle tiebreak and first-seen), the `value` payload shape (full record vs
  `{rarity, exempt_from_4cap}`), and the `prefilter` (layout / legality / set-type / draft-set).
- **Collapsed (behavior-changing, on purpose):** the 3-pass alias mechanic, **every-face DFC
  handling** (front-face is now a deduped tier key everywhere), universal **NFKD folding**, the
  en-gate, and the `None`-price handling (priced beats price-less, deterministic among
  price-less). `find_commanders` **gains Arena aliases** (it reads collections, which use Arena
  names — the absence was a bug).

## Migrated

`card_classify.build_card_lookup` (so `HydratedDeck.by_name` folds and indexes all DFC faces —
the deck-domain join, committed first), then `scryfall_lookup._load_bulk_index` /
`build_rarity_index`, `find_commanders._load_bulk_index`, `deck.load_bulk_indexes` (`by_name`;
`by_id` stays a plain token-inclusive dict), and `card_search`'s dedup. Every bulk-data record
lookup index now flows through the core. Consumers were transparent — they query `.get(name)` or
`.get(name.lower())`, both of which the `NameIndex` folds — so only return-type annotations
changed (`dict[str, dict]` → `NameIndex`).

## Follow-up (completed)

Both items first deferred here were addressed in a follow-up commit.

- **`mark_owned`** now consumes `alias_keys` for its DFC face derivation, keeping its own value
  shape (the bidirectional alias→canonical string map + sum/max quantity table — it does NOT use
  `build_name_index`, which is a record index). It was filed as pure DRY, but it turned out
  `mark_owned` *did* carry a smaller form of the DFC bug: it indexed the FRONT face only, so a
  deck/collection listing the BACK face of a split / MDFC / "prepare" card (e.g.
  `"Reflection of Kiki-Jiki"` of `"Emeritus of Woe // Demonic Tutor"`) silently missed.
  Consolidating onto `alias_keys` (every face, both directions) fixed it; pinned by a regression
  test.
- **deck-forge `production.build_by_name`** now folds — `build_name_index(reduce=keep_cheaper)` →
  a `NameIndex`. Its proper-case keying dissolved (folding makes search's proper-case output match
  any spelling), so `ForgeState.by_name` is now typed `Mapping[str, dict]`. One consumer needed a
  fix: `engine._signal_freq` iterated `by_name.values()`, which under a folding index yields the
  same record under several keys — it now dedups by card name so the commander-pool sweep counts
  each card once.

## What this stops re-suggesting

- Don't re-add a per-builder name-folding/DFC/alias pass — the keying is `alias_keys`; differences
  are `reduce` / `value` / `prefilter` knobs.
- Don't make folding a knob or revert any builder to `str.lower` — folding is universal
  (`NameIndex`); the diacritic miss is the bug it fixes.
- Don't "fix" `find_commanders` back to alias-less, or split-card front-only DFC indexing — those
  were the bugs.
- Don't fold `mark_owned` into `build_name_index` (different value shape); consolidate its *keying*
  onto `alias_keys` as a separate change if/when it earns its keep.
