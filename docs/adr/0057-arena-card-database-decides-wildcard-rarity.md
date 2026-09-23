# The local Arena card database decides wildcard rarity; MTGJSON is the fallback

`price-check` and deck-forge cost an Arena deck in wildcards, and a card's wildcard cost
is the rarity Arena charges to craft it. We read that from MTGJSON (ADR-0033): the lowest
rarity among a card's Arena printings, with one heuristic on top. Reprints in the
digital-only draft sets (J21 / JMP / AJMP) deferred to the card's other Arena printing,
because Lightning Bolt's J21 common costs an uncommon.

On 2026-09-23 Unholy Heat priced as mythic. Arena ships its own card database with every
install (`MTGA_Data/Downloads/Raw/Raw_CardDatabase_<hash>.mtga`, SQLite), and it marks the
printings Arena sells with `IsPrimaryCard`. Checked against every card in it, our MTGJSON
answer was wrong for 45 cards (plus J21-only cards reported as "not on Arena"):

- The draft-set heuristic was backwards. 866 of Arena's 894 J21/JMP printings are
  primary; Bolt is one of the 28 that are not. Unholy Heat's J21 common is primary, so it
  costs a common, not its later Special Guests mythic.
- MTGJSON's data can't express the rest. It lists Special Guests printings at their sheet
  rarity (mythic) where Arena charges the card's own (Darkness common, Condemn uncommon).
  It misses Arena availability for the Final Fantasy Commander reprints. It marks some
  Alchemy bonus-sheet printings as on Arena at a rarity Arena doesn't sell.

**Decision.** When the local Arena card database is present, it decides wildcard rarity.
MTGJSON decides it otherwise, and still decides legality and availability either way.

- **`mtg_utils.arena_card_db`** finds the database: `$MTG_SKILLS_ARENA_CARD_DB` (a path,
  or `none`), then the download folder `Player.log` records, then the standard install
  locations. It reads `normalize_card_name(title) -> lowest rarity among primary
  printings`, skipping tokens, rebalanced "A-" printings and rows below common. A title
  comes from the plain localization row: the formatted row hides "A-" behind a sprite
  tag and wraps words in `<nobr>`. `player_log_path` is shared with `mtga-import`.
- **`CardPool.rarity_index(fmt, arena_only=True)`** projects each card's rarity through
  that map (full name, then front face), falling back to the MTGJSON rarity. The memo key
  carries the database identity.
- **The MTGJSON fallback counts draft-set reprints like any printing.** Measured against
  the database, that is 35 wrong instead of 45, trading three it now gets wrong (Lightning
  Bolt, Dark Ritual, Fog) for thirteen it gets right.
- **Tests never see an installed Arena.** `tests/conftest.py` sets
  `MTG_SKILLS_ARENA_CARD_DB=none` for every suite. A test that wants the database points
  the variable at a fixture built by `conftest.make_arena_card_db`.

**Consequences.** On a machine with Arena installed, which is every machine that needs
wildcard costs, the rarity matches what Arena charges: 0 mismatches over about 16,000
cards on the day this landed. Without Arena (CI, a paper player costing an Arena list),
the answer degrades to MTGJSON's, which is right for all but about 35 cards. The database
is read-only and only opened when an Arena-medium index is built. A new client version
writes a new `<hash>` file; discovery takes the newest.
