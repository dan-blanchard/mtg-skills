# ADR-0056 sweep: which tests still hand-build card data

Read-only survey (no test files edited). Scope: every file under `tests/` that
hand-builds a dict/kwargs carrying `oracle_text`, `type_line`, `keywords`,
`mana_cost`, `power`/`toughness`, `legalities`, or runs a `_card(...)`-style
factory that assembles one. Found via `grep` across all of `tests/` (105 files
on the narrow pattern set, +3 more on a broader second pass for
`color_identity`/`produced_mana`/`rarity`/`card_faces`/`cmc`/`edhrec_rank`/
`game_changer`), then classified file-by-file by seven parallel read-only
agents plus direct review of both `conftest.py` files.

`lgs-search` (19 files), `rules-lawyer`, `deck-strat`, `deck-wizard` (1 smoke
test each) have **zero** hits on any pattern — out of scope entirely.
`tests/lgs-search/test_scryfall_usd_lookup.py` uses real names (Sol Ring,
Counterspell, Beast Within) purely as price-lookup keys with fabricated USD
prices — the ADR's own "price tie-break" machinery example, so left out of
the table below.

Legend: **CONVERT** = real card, assertion depends on it, should become
`test_card`/`test_card_ir`/`test_signals`. **RENAME** = machinery test using a
real name with wrong/incomplete data for that card. **SYNTHETIC-OK** =
fictional name, tests a shape not a card, or a legitimate per-printing
overlay on an already-converted real record. **SPECIAL** = judgment call
(counted separately, not folded into the other three columns). Counts with
`~` are approximate (agents sampled or estimated on very large files).
"Not in snapshot" means `build-card-snapshot` must run before that name can
be used — never run by any survey agent.

## Per-file table

### Shared fixtures

| File | CONVERT | RENAME | SYNTHETIC-OK | Effort | Notes |
|---|---|---|---|---|---|
| tests/mtg-utils/conftest.py | 38 | 0 | ~9 (+SPECIAL 1) | L | `sample_bulk_data` (16 real cards: Korvold, Viscera Seer, Blood Artist, Sol Ring, Command Tower, Sakura-Tribe Elder, Deadly Rollick, Cultivate, Ashnod's Altar, Dictate of Erebos, Overgrown Tomb, Thrasios, Tymna, Fire // Ice, Malakir Rebirth // Mire, Rhystic Study), `cube_bulk_data` (8: Lightning Bolt, Swords to Plowshares, Counterspell, Dark Ritual, Llanowar Elves, Atraxa, Tuvasa, Wildfire), `alt_cost_cards` (7: Star Whale, Ancestral Vision, Fury, Goldvein Hydra, Sol Ring, Command Tower, Murderous Cut), `trigger_test_cards` (7 real of 14: Obeka, Helm of the Host, Spark Double, Strionic Resonator, Panharmonicon, Rings of Brighthearth, Counterspell — other 7 are fictional machinery, fine). `cube_hydrated_real_removal` already does the correct overlay pattern (reference example). `sample_cube_json`/`sample_commander_cube_json`/`sample_edhrec_response`/`sample_combo_response(_empty)` are name-only or API-shape fixtures — out of scope, no card facts asserted. **Not in snapshot:** Korvold Fae-Cursed King, Overgrown Tomb, Thrasios Triton Hero, Malakir Rebirth // Malakir Mire. **SPECIAL:** `Ancient Wyrm` in `sample_bulk_data` — fictional name, comment explains it was chosen deliberately (7/7 flier) "rather than patching power onto a small card"; legitimately SYNTHETIC-OK per the ADR, but a real big flier (e.g. a real 6+ power flying creature) would serve the same test and is more in the ADR's spirit. Highest blast-radius file in the repo — see Batch 0 below for dependents. |
| tests/deck-forge/conftest.py | 0 | 0 | 0 | — | Only a network-blocking autouse fixture. No card data. |

### tests/mtg-utils

| File | CONVERT | RENAME | SYNTHETIC-OK | Effort | Notes |
|---|---|---|---|---|---|
| test_archetype_audit.py | 7 | 0 | 8 | M | Hydrated records serialized to tmp JSON: Llanowar Elves ×3, Lightning Bolt ×2, Reanimate ×1 — all in snapshot. |
| test_archetype_resolver.py | 2 | 0 | 2 | S | Llanowar Elves negative-control dict, hand-typed twice; in snapshot. |
| test_build_deck.py | 0 | 1 | ~25 | M | "Korvold" used 33× as commander placeholder with fake `{cmc:5, type_line:"Creature"}`; real Korvold is MV4 and not in snapshot — rename to an obviously fictional commander. Rest is cut/add bookkeeping, fine. |
| test_bulk_loader.py | 0 | 0 | 2 | S | Sol Ring/Lightning Bolt/Counterspell/Opt as `{name, type_line}` cache-invalidation probes — accurate, no drift risk. |
| test_card_classify.py | ~55 | 0 | ~35 (SPECIAL 2) | L | Biggest mtg-utils target. `TestRampByText`/`TestColorSources`/`TestClassifyCubeCategory`/`TestPartnerAbility` hand-type real cards' oracle text and depend on it. Azusa's text already drifted (drops "up to"). An unnamed Metalcraft rock is Mox Opal's text; an unnamed fetch-land is Seething Landscape's. DFC/alias tests use Hengegate Pathway, Shatterskull Smashing, Masked Meower/Skittering Kitten. **Not in snapshot (partial list):** Mox Opal, Moonsilver Key, Seething Landscape, Arcane Signet, Bloom Tender, Nature's Lore, Three Visits, Farseek, Overgrown Tomb, Polluted Delta, Prismatic Vista, Verdant Catacombs, Flooded Strand, Fabled Passage, Evolving Wilds, Chromatic Lantern, plus several commander names — re-verify exact punctuation before a snapshot rebuild. |
| test_card_pool.py | 0 | 0 | ~25 | — | `_card()` covers only structural fields (id/rarity/legalities/prices/set) — CardPool's own job never touches oracle text. `_mtgjson_printing()` is the reference "overlay on `test_card(...)`" pattern. Already compliant. |
| test_card_search.py | 0 | 0 | ~60 | — | Filter/sort/pagination/legality-date machinery; real names used as flavor only. Type-line-token tests already route through `testkit`. Already compliant. |
| test_card_summary.py | 0 | 0 | 3 (SPECIAL 1) | S | "Test Card" ×2 and "Smash" are fine fictional shorthand. **SPECIAL:** Sol Ring ×2 — real, accurate, but the assertion (zone filtering) never depends on what Sol Ring does; a free but unnecessary swap. |
| test_combo_search.py | 5 | 0 | 2 | M | Murderous Redcap, Grizzly Bears, Ashnod's Altar, Rhythm of the Wild, Moritte of the Frost — real, accurate. Not in snapshot: Murderous Redcap, Rhythm of the Wild, Moritte of the Frost. |
| test_commander_cost.py | 0 | 0 | ~15 | — | `_creature()`/ISLAND/LORD are fictional machinery for the hypergeometric math. `TestIRRead` (the only real-card-dependent class) already runs through `testkit`. Already compliant. |
| test_companion.py | ~35 | 2 | ~3 (SPECIAL 1) | L | Nearly every `_card()` call names a real companion or real deck card with faithful mana_cost/cmc/type_line. **RENAME:** `_companion(name)` hardcodes type_line "Legendary Creature — Beast" for all ten companions (wrong for most); `test_negative` attaches made-up text to "Grizzly Bears". Several companions not in snapshot (Jegantha, Kaheera, Keruga, Obosh, Umori, Yorion, Zirda) plus Sliver Overlord, Burning-Tree Emissary. **SPECIAL:** module docstring claims "all records are synthetic," but the content is mostly accurate real cards the companion-condition assertions depend on — docstring is stale, side with the content. |
| test_crosswalk.py | 0 | 0 | 0 | L (17.5k lines) | Almost everything already loads real cards by name from its own `tests/fixtures/crosswalk_fixture_cards.json`, not testkit — a second real-cards-by-name mechanism the ADR doesn't explicitly address. Only 7 hand-typed literals (Oblivion, Despair, Feed, Injury, "Lead", Mulldrifter, Chaos Warp), all real/accurate; Mulldrifter and Chaos Warp are in the snapshot and could convert, the other 5 feed a testkit-unserved shape (`_text_only_tree`, no phase record). **SPECIAL** (7): whether the whole `crosswalk_fixture_cards.json` mechanism should fold into testkit is an architecture question, not a per-file fix. |
| test_cube_balance.py | 0 | 0 | 2 | — | Fictional type-line-exclusion negatives (structural, not identity-dependent); the real-card class already runs through `testkit`. Already compliant. |
| test_cube_legality_audit.py | 2 | 0 | 1 | S | Black Lotus, Mana Drain (both in snapshot) — overlay `rarity` by hand. "Mystery Card" fine. |
| test_custom_format_classifier.py | 12 | 0 | ~5 | M | `TestClassifyLibraryEffect`'s ten `_card()` calls (Opt, Sensei's Divining Top, Consider, Discovery, Dragon's Rage Channeler, Stitcher's Supplier, Demonic Tutor, Goblin Guide, Counterspell, Mountain) plus 2 in `TestPrecomputeMetadata` are real cards the classifier's assertion depends on. Not in snapshot: Consider, Discovery, Dragon's Rage Channeler. `TestParsePipCounts`/`TestCanCastWithPips` are machinery, fine. |
| test_custom_format_shared_library.py | 0 | 0 | all | S | Only procedurally generated `f"{color}{i}"` cards. |
| test_cut_check.py | 7 | 0 | 2 | M | Module-level dicts explicitly commented "Real oracle text ... verified against MTGJSON": Thranduil, Obeka, Priest of Titania, Iron-Shield Elf, Lathril Blade of the Elves, Bloodline Pretender, Door of Destinies. Not in snapshot: Priest of Titania, Iron-Shield Elf, Lathril, Bloodline Pretender. Also depends on conftest's `trigger_test_cards`, already covered above. |
| test_deck_diff.py | 0 | 0 | 3 | S | Only "Bolt"/"Smash" shorthand. |
| test_deck_forge_clis.py | 3 | 0 | 0 | M | Krenko, Mountain, Goblin Chieftain — real oracle_id pasted in by hand but oracle_text is a paraphrase (drift risk). All three in snapshot; overlay `prices` (not in minimal record). |
| test_deck_stats.py | 1 | 1 | 9 (SPECIAL 1) | S | **CONVERT:** `_mld("Armageddon")` — real text, detector depends on it. **RENAME:** `_gc("Smothering Tithe")` has type_line "X" and empty text; overlay `game_changer` (not served) once converted. **SPECIAL:** Lightning Bolt filler in `TestSideboardStats`, real/accurate but assertion doesn't depend on its text. Also depends on conftest's `alt_cost_cards`, already covered above. |
| test_deck_tune_cli.py | 0 | 1 | 0 (SPECIAL 1) | S | **RENAME:** KRENKO — oracle truncated ("...tokens." drops "where X is the number of Goblins you control"), nothing reads the text, `test_card("Krenko, Mob Boss")` fits and is in snapshot. **SPECIAL:** MOUNTAIN, real/accurate but unnecessary. |
| test_draft_ai.py | 0 | 0 | 6 | S | Only fictional Bomb/Chaff/BlueX names. |
| test_dropped_clauses.py | 0 | 0 | 3 | S | Card-IR dataclass machinery, fictional names. |
| test_field_corrections.py | 0 | 0 | 7 | S | Card-IR dataclass machinery, `name="T"`. |
| test_find_commanders.py | 8 | 4 | 4 | L | Full Scryfall-shaped `_card()` factory. **CONVERT:** Lightning Bolt, Sol Ring, Thrasios, Pir Imaginative Rascal, Bruna//Brisela ×2, Lim-Dûl's Vault. **RENAME:** Korvold (not in snapshot), Atraxa, Teferi Temporal Pilgrim (keep the factory's wrong defaults), "Faceless One" (real Baldur's Gate commander, hand text gives it a dies-trigger it doesn't have). Overlay gap: `edhrec_rank`, `game_changer`, `set_type` not served. |
| test_formats.py | 0 | 0 | ~4 | — | Model file for the ADR — every legality claim already runs through `testkit`. A handful of pure name-matching dicts left, fine. |
| test_gauntlet_build.py | 5 | 0 | ~42 | S | Goblin Guide, Akroma Angel of Wrath, Counterspell, Grizzly Bears, Mountain — real, accurate. Only Akroma not in snapshot. Rest loop-generated. |
| test_gauntlet_inference.py | 1 | 0 | ~20 | S | Mountain (in snapshot); rest loop-generated. |
| test_hydrated_deck.py | 5 | 0 | 1 | M | Module constants SOL_RING, LLANOWAR, FOREST, PATHWAY, COMMANDER (Marwyn) feed ~20 tests via `BY_NAME`. Not in snapshot: Branchloft Pathway // Boulderloft Pathway. Overlay `prices`. |
| test_hydrated_pt_gates.py | 0 | 0 | 0 (SPECIAL 1) | S | No literals (uses conftest's `sample_bulk_data`). **SPECIAL:** `ground` copies the real Ancient Wyrm record and strips its text/keywords to build a "big creature, no evasion" negative — a real name carrying invented data; a genuine real near-miss would be cleaner. |
| test_integration.py | 0 | 0 | 0 | S | Nothing hand-built; depends on conftest's `sample_bulk_data`/`sample_edhrec_response`. |
| test_legality_audit.py | 29 | 7 | 5 | L | ~40 fixtures across 15 classes via `card()`/`basic()`/`jinnie()`/`_companion_card()`. **Live drift bug:** line ~1158 gives Oko `color_identity=["G"]`; real/snapshot value is `["G","U"]`. RENAME: Krenko, Thrasios, Kozilek Butcher, TestCommanderZone filler, My Precious, Golos, Stone by Sunlight. Large "not in snapshot" list (Jinnie Fay, Golos, Kozilek the Great Distortion, Ancestral Recall, Keruga, Yorion, Hill Giant, basics, etc.) — see agent detail before a snapshot rebuild. |
| test_mana_audit.py | 13 | 1 | 5 (SPECIAL 2) | L | Lightning Helix, Command Tower, Mountain, Lightning Bolt convertible now. Not in snapshot: Malakir Rebirth // Malakir Mire, Bennie Bracks Zoologist, Korvold, Plains, Island. **SPECIAL:** `_benchmark_deck()`'s "Bennie Bracks" is deliberately mis-colored/mis-costed per its own docstring (to hit an ADR-0041 benchmark) — rename to an obviously fictional commander; `test_counts_colored_pips` has nameless dicts with `# Counterspell`/`# No Mercy` comments nothing reads — drop the comments or convert. Also depends on conftest's `hydrated_cards`. |
| test_mtga_import.py | 0 | 1 | 0 | S | `_fake_bulk_cards()`: Sheoldred/Sol Ring/Bolt with blanket legalities + fake arena_ids, used only as index machinery — rename or convert with `arena_id`/`games` overlay (not served by snapshot). |
| test_mtgjson_adapter.py | 0 | 2 | 14 | S | Inputs are MTGJSON-shaped; testkit can't supply them, nothing to convert. RENAME: Bruna given Brisela's type line and vice versa — swap in fictional names as the file already does elsewhere. |
| test_name_index.py | 0 | 0 | ~15 | S | *(found in broader sweep, not the narrow grep.)* Name-folding/index machinery; real names (Sol Ring, Lim-Dûl's Vault, Fire // Ice) used purely as opaque string keys, no behavior claimed. Already fine. |
| test_parse_cube.py | 2 | 0 | 0 | S | Only `test_category_prefixes_list_triggers_commander_detection` reads type_line: Atraxa, Lightning Bolt, both in snapshot. |
| test_phase_bump.py | 0 | 5 | 9 | S | All 5 RENAMEs are "Sol Ring" reused as a generic "old text"/"new text" label across `_rec()`/`_fake_repo()`. |
| test_phase_record_grouping.py | 0 | 0 | 1 (SPECIAL 1) | S | **SPECIAL:** a "Fast" impostor fixture hand-types real oracle text/ids of two colliding real cards to reproduce a documented upstream mis-join bug (task #78) — testkit serves clean records, not a deliberately-wrong join, so this probably has to stay hand-typed with a comment. |
| test_playtest_custom_format.py | 0 | 0 | 2 | S | Only `f"{color}{i}"` generator. |
| test_playtest_draft.py | 0 | 0 | 1 | S | Only `f"{color}{i}"` generator. |
| test_playtest_gauntlet.py | 5 | 0 | 1 | S | 5 hand-typed basics; not in snapshot: Plains, Island, Swamp. |
| test_playtest_goldfish.py | 25 | 1 | 16 | L | ~14 unique real cards. **RENAME:** "Hobbit Hole" is given text that contradicts the real card (sends the land to hand vs. real ETB-tapped fetch). Not in snapshot: Hobbit Hole, Wood Elves, Knight of the Reliquary, Fabled Passage, Ignoble Hierarch, Hill Giant, Pitiless Plunderer, Mirkwood, etc. No overlay needed (snapshot's `produced_mana` already matches). |
| test_price_check.py | 1 | 0 | ~22 | S | **The ADR's motivating "wrong Arena rule / hand-typed Hare Apparent" example is already fixed** — `_arena_printing()` now builds from `testkit.test_card(name)` and Hare Apparent is in the snapshot. **But an uncaught duplicate of the same pattern remains:** `test_arena_partial_ownership_under_4cap` hand-types Persistent Petitioners' Arena copy-limit oracle text instead of routing through `_arena_printing`; Persistent Petitioners is not in the snapshot. |
| test_rulings_lookup.py | 0 | 1 | 2 | S | `_FAKE_CARD` is "Sol Ring" with a fake id/oracle_id/invented rulings, reused in ~10 tests — rename. |
| test_scryfall_lookup.py | 5 | 0 | 2 | M | Sol Ring ×2, Fire // Ice, Steam Vents, Bind // Liberate (+ the deliberate "Bind" name-collision case, keep as a real near miss). Not in snapshot: Steam Vents, Bind // Liberate. Overlay `prices`/`rarity`. Also depends on conftest's `sample_bulk_data`. |
| test_set_scan.py | 0 | 0 | ~7 | — | FLYER/WALL/TROLL/BEAR/FOREST are fictional generic bodies; MURDER/WRATH (the only signal-dependent fixtures) already route through `testkit`. Already compliant. |
| test_theme_presets.py | 0 | 0 | 2 | — | The reference file for the whole ADR — every golden fixture resolves through `testkit` by design. Only "Fake Card" ×2 (sidecar-cache correctness, not preset accuracy) is hand-built. Already compliant. |
| test_tree_synthesis.py | 14 | 2 | 84 | L | Has its own real-card fixture (`crosswalk_fixture_cards.json` via `_fixture_tree(name)`, 278 sites) — mostly compliant already. CONVERT = hand-built `ConceptTree(...)` bypassing `_fixture_tree` for 14 real cards (Chancellor of Tales, Backfire, Brazen Collector, Evil Twin, Ancient Silver Dragon, Castle Locthwain, Baneslayer Angel, Esper Sentinel, etc.) — 12 of 14 not yet in that fixture either. |
| test_tuner_bracket.py | 5 | 2 | 4 | M | CONVERT: Winter Orb, Time Stretch, Armageddon (`_mld`, exact text), Time Warp, Temporal Manipulation. RENAME: Smothering Tithe, Mana Crypt (`_gc`, oracle_text=""). Not in snapshot: Winter Orb, Time Stretch, Time Warp, Mana Crypt. Overlay `game_changer`. |
| test_tuner_classify.py | 5 | 0 | 0 (SPECIAL 1) | M | Module-level KRENKO, RABBLEMASTER, RAMP_ROCK (Mind Stone), VANILLA (Hill Giant), MOUNTAIN — real, bucket assertions genuinely depend on real text. Not in snapshot: Mind Stone, Hill Giant. **SPECIAL:** HEROIC (Heroic Intervention) — text is accurate but the test feeds a hand-built `Signal` directly, bypassing the text entirely; converting adds no guarantee, comment already documents intent. |
| test_tuner_metrics.py | 10 | 4 | 6 | M | CONVERT: Pact of Negation, Platinum Angel, Mortal Combat, Yuriko, Blood Artist, Serra Angel, Lightning Bolt, Lava Axe, Aetherflux Reservoir, Exsanguinate. RENAME (fixture text wrong for the real card): Fiery Confluence, Kaervek's Torch, Fireball, Torment of Hailfire. Not in snapshot: Pact of Negation, Platinum Angel, Mortal Combat, Lava Axe, Exsanguinate. |
| test_tuner_shape.py | 0 | 0 | 1 | — | `_cc()` builds generic "C0/S0" records; real names only in comments. |
| test_tuner_swaps.py | 6 | 0 | ~55 (SPECIAL 1) | M | `_is_fixing` tests hand-type Kodama's Reach, Farseek, Rampant Growth, Golgari Signet, Sol Ring, Mind Stone specifically to prove real-text reading. Not in snapshot: Kodama's Reach, Farseek, Golgari Signet, Mind Stone. Remaining ~55 fixtures feed a fully mocked `search_fn` — legitimately synthetic even under a real name. **SPECIAL:** a "Swords to Plowshares" record drops the life-gain clause, but only reaches the mocked path, so it's inert. |
| test_tuner_tune.py | 8 | 0 | ~20 | L | KRENKO, RABBLE (Goblin Rabblemaster), WARCHIEF (Goblin Warchief), FILLER1 (Hill Giant), FILLER2 (Lumbering Battlement), MOUNTAIN, BOLT (Lightning Bolt), Laboratory Maniac — one shared fixture drives ~40 test functions (coordinated change, not independent swaps). Not in snapshot: Hill Giant, Lumbering Battlement, Laboratory Maniac. |

### tests/deck-forge

| File | CONVERT | RENAME | SYNTHETIC-OK | Effort | Notes |
|---|---|---|---|---|---|
| test_app.py | 3 | 0 | 1 (SPECIAL 1) | M | Llanowar Elves, Forest, Atraxa — in snapshot; `_FOREST_VIEW` expected-response must change alongside. **SPECIAL:** Ishai Ojutai Dragonspeaker test monkeypatches a hand-built Card IR/ConceptTree in place of the crosswalk index — more than a mechanical swap. |
| test_avenue_gaps.py | 27 | 0 | 0 | L | 13 module constants + 14 inline dicts, every one a hand-typed real card (Sram, Sun Titan also correctly pulled via `test_signals` elsewhere). Not in snapshot (11): Warstorm Surge, Corpse Knight, Solemn Simulacrum, Soul Warden, Doubling Season, Gratuitous Violence, Authority of the Consuls, Basilisk Collar, Swiftfoot Boots, Flux Channeler, Krosan Cloudscraper. |
| test_balance_lands.py | 6 | 0 | 2 | S | `_basic()` builds all six basics. Not in snapshot: Plains, Island, Swamp, Wastes. Fixture wrongly uses `color_identity: []` — check nothing depends on that being empty before converting. |
| test_budgets.py | 19 | 1 | ~5 | M | FOREST/LLANOWAR/FLESHBAG(+real oracle_id)/LUPINE/VISCERA plus 14 inline role/`protects()` dicts (Blighted Agent, Phyrexian Swarmlord, Carnage Tyrant, Boros Charm, Ghostly Prison, Misdirection, Deflecting Swat, Umbra Mystic, Twincast, Frenetic Efreet, Fog, etc.). **RENAME:** "Sejiri Refuge Save" reuses a real land's name for made-up text. **SPECIAL (S1, shared w/ test_ranking):** several real-card dicts deliberately drop `oracle_id` to exercise the text-fallback path — converting naively would move them onto the structural path, a different test; needs an explicit `{**test_card(n), "oracle_id": ""}` overlay, or a decision that the fallback path should now be proven on real records. Not in snapshot (12): Blighted Agent, Phyrexian Swarmlord, Darksteel Reactor, Carnage Tyrant, Swiftfoot Boots, Boros Charm, Ghostly Prison, Misdirection, Deflecting Swat, Umbra Mystic, Frenetic Efreet. |
| test_collection.py | 2 | 3 | 0 (SPECIAL 1) | M | CONVERT: Forest, Ghave Guru of Spores (must be commander-eligible). RENAME: Sol Ring, Cultivate, Llanowar Elves via `_rec()` with blank text and wrong cmc. Not in snapshot: Ghave, Masked Meower. **SPECIAL:** Masked Meower — real Arena-alias test ("Skittering Kitten"); the fixture's colour/type look wrong (white vs. real red), snapshot carries no Arena-name field so the alias still needs hand-authoring even after conversion. |
| test_commander_discovery.py | 0 | 0 | ~95 (6 factory groups) | — | Deliberately synthetic top to bottom (Lifelord, Tokenlord, Vanilla Vance, etc.) — a made-up card has no phase record by design. Nothing to change. |
| test_commit_point.py | 2 | 0 | 0 | S | Forest, Llanowar Elves — accurate, in snapshot; placeholder oracle_ids become real ones. |
| test_companion_zone.py | 6 | 0 | 0 | M | Keruga, Yorion, Atraxa, Sol Ring, Forest, Hill Giant — companion condition text/mana values drive the assertions directly. Not in snapshot: Keruga, Yorion, Hill Giant. This file's Atraxa text is truncated (missing proliferate line) vs. the full text used in test_app.py/test_engine.py — exactly the cross-file drift the ADR targets. |
| test_constructed.py | 7 | 0 | 0 (SPECIAL 1, 3 records) | M | Mountain, Lightning Bolt, Black Lotus, Keruga, Island, Counterspell, Ragavan (text cut to "Dash {1}{R}"). Not in snapshot: Island, Keruga. **SPECIAL:** a Delver/Agadeem's Awakening/Cragcrown Pathway DFC-face-reading test uses real names with deliberately wrong face colors (a comment even says "a made-up back") — renaming all three to fictional DFCs is probably cleaner than fixing the colors. |
| test_crosswalk_seam.py | 0 | 0 | 3 (SPECIAL 1) | S | Works one layer below testkit against its own `crosswalk_fixture_cards.json`; never types oracle text. **SPECIAL:** `_bulk()`/`_ported_case()` search the whole corpus at test time for whichever card fires a PORTED signal, then bolt on a hardcoded `type_line` — doesn't fit testkit's "name is a literal" rule and deliberately stays name-independent; leave as-is or pin a named card. |
| test_engine.py | 3 | 0 | 0 | S | Ishai, Atraxa, Forest — accurate, in snapshot. |
| test_engine_endpoints.py | 1 | 0 | 5 | S | Jyoti Moag Ancient — comment claiming the snapshot drops cmc/color_identity is stale (only `prices` is actually missing); in snapshot. Rest is fictional endpoint plumbing. |
| test_engine_rules.py | 4 (+1 overlay) | 0 | 1 | M | Lurrus of the Dream-Den, Sol Ring, plus a second `_basic()` (Plains, Island). `SOL_RING_PREMIUM = {**SOL_RING, ...}` is already the ADR's recommended overlay shape — only the base needs to become `test_card("Sol Ring")`. Not in snapshot: Plains, Island. `printings_by_oracle` keyed by a placeholder id, needs rekeying. |
| test_find.py | 1 | 0 | 2 (SPECIAL 1) | S | Llanowar Elves, in snapshot; overlay rarity/prices/image_uris. **SPECIAL:** `_PRE` "Belladonna Took" models an unreleased card (needs a `released_at` in the future) — the snapshot can never hold that by construction; a fictional "Unreleased Test Card" is more durable than a real card that will eventually release (and may already have). |
| test_find_candidates.py | 4 | 0 | 3 | M | Treetop Village, Sol Ring, Cultivate, Counterspell — all in snapshot. Overlay prices/rarity where read. |
| test_handoff_goldfish.py | 1 | 0 | 2 | S | Forest — the ADR's own worked example; snapshot's Forest already has `produced_mana`, no overlay needed. |
| test_handoff_proxies.py | 1 | 2 | 1 | S | CONVERT: Forest. RENAME: Grizzly Bears, Giant Growth get placeholder "`{name} does a thing.`" text — test only checks PDF bytes/status, so converting is simplest. |
| test_images.py | 0 | 0 | 5 | — | *(found in broader sweep.)* Image-URL extraction; real names (Llanowar Elves, Hengegate Pathway) used as opaque card-shape holders, no behavior claim. |
| test_import.py | 1 | 0 | 0 | S | SOL_RING dict, accurate — convert, overlay prices. |
| test_keyword_gaps.py | 2 | 0 | 0 (SPECIAL 3) | S | Two hand-typed "Grizzly Bears" dicts, in snapshot. **SPECIAL:** "Defensive Wall" (fictional should-not-serve negative — ADR wants a real near miss instead), "Test Saga Lord" (docstring argues no real card has this exact shape — defensible but still asserts on fictional text), "Self Lifeloss"/`ludevic` (fictional negative whose variable name suggests it was modeled on a real card). |
| test_known_tokens.py | 0 | 0 | 0 (SPECIAL 11) | L | 11 entries mirror phase's own `known-tokens.toml` (independently verified real data, re-checked at the 2026-07-24 pin bump) but in a `display_name`/`rules_text`/`core_types` shape testkit doesn't serve at all — a different real-data source than Scryfall. Recommend an explicit ADR-0056 carve-out rather than forcing these into testkit. Separately, the file's integration tests already load real cards from a different committed fixture (`crosswalk_fixture_cards.json`), out of scope here. |
| test_limited.py | 2 | 0 | 5 | M | Forest (in snapshot), Plains (real, not in snapshot) via `_rec()`. BEAR/EAGLE/TROLL/PONY/"Dragon" are correctly fictional pool/sealed filler. |
| test_medium_wildcards.py | 4 | 0 | 0 | M | Shock, Thoughtseize, Mountain (in snapshot), Keruga (real, not in snapshot, correct companion text). |
| test_partner_widening.py | 0 | 0 | 3 | S | PAIR_LORD/WIDE/MONO are obviously-fictional legendaries whose text is only the generic Partner reminder — legitimately synthetic; the widening math needs color-identity combos no single real commander cleanly provides. |
| test_persistence.py | 1 | 0 | 0 | S | Forest stub — convert; DECK's commanders/cards are name+quantity only, out of scope. |
| test_phase_crosscheck.py | 0 | 1 | ~11 | S | **RENAME:** "Elvish Mystic" (not in snapshot) is a phase-record-shaped dict for tag-projection only; the name plays no role in the assertion. Rest is loader/corpus machinery, or already real (Adeline, Krenko) via `test_card` on the Scryfall side. |
| test_printing_ownership.py | 3 | 1 | 0 | L | `_printing()` factory: CHEAP/PREMIUM/NEWEST are all "Sol Ring" (in snapshot), correct base data, needing a real per-printing overlay (set/collector_number/released_at/rarity/finishes/prices/image_uris/id). **RENAME:** CULTIVATE has empty oracle_text — wrong for the real card, but harmless here; convert via testkit since real text doesn't hurt. 417-line file, several cross-referenced printing dicts — nontrivial overlay design. |
| test_printings.py | 2 | 0 | 0 | S | `_printing()` CHEAP/PREMIUM, same Sol Ring pattern as test_printing_ownership.py but fewer fields. |
| test_production.py | 0 | 0 | 0 (SPECIAL 1) | S | **SPECIAL:** "Opt" (in snapshot) in a pure memoization/call-counting test — the assertion would pass with any two distinct names, so a testkit swap is free but arguably not meaningful. |
| test_ranking.py | 13 | 0 | ~10 | M | 11 module dicts explicitly commented "Real card props (full oracle text — fixtures must embed real cards)": Bastion, Blood Artist, Midnight Reaper, Elven Bow, Flayer Husk, Walking Ballista, Hired Claw, Siege-Gang Lt, Fires of Mount Doom, Empty the Warrens, Ashnod's Altar; plus inline Mishra's Factory, Silent Hallcreeper. Not in snapshot (6): Midnight Reaper, Flayer Husk, Walking Ballista, Hired Claw, Mishra's Factory, Silent Hallcreeper. Overlay `prices`; same deliberate-no-oracle_id issue as test_budgets.py (see S1 above). |
| test_rate.py | 0 | 0 | 1 | — | Only a neutral-rate `{"name": "X", "oracle_text": ""}` probe. Already clean. |
| test_roles.py | 0 | 0 | 3 | — | "Test Rock"/"Test Bear" must be cards the signal path doesn't cover, so fictional is correct; the Lightning Bolt overlay proves a covered card never falls back to text — legitimate machinery. |
| test_row_class_permutation.py | 0 | 0 | ~10 | — | *(found in broader sweep.)* Ranking-permutation machinery; real names (Grizzly Bears via "Bare Pump" etc. — actually fictional pun names) used only as sort keys, no behavior claim. |
| test_safety_rails.py | 2 | 0 | 2 | S | FOREST, "Opt" (verbatim real text) — in snapshot. CMD/BANNED are correctly fictional. |
| test_signal_specs.py | ~480 | 0 | ~30 | L | **Largest single conversion job in the repo.** 223 test functions, ~515 `"name":` occurrences, an estimated ~93-95% (≈470-490) are real, identifiable cards with word-for-word-or-near-verbatim snapshot text (Rhystic Study, Esper Sentinel, Sword of Fire and Ice, Wrath of God, Monastery Swiftspear, Kokusho, Junji, etc., plus heavily-reused "vanilla baseline" cards: Grizzly Bears ×20, Llanowar Elves ×10, Lightning Bolt ×8). Newest ~260 lines (tail of file) already comply via `test_card`/`test_card_ir`. Genuine synthetic minority (~25-35, ~5-7%) uses fictional or explicitly disclaimed "X-like" names — legitimately SYNTHETIC-OK, and the file had already independently converged on the ADR's own real-vs-fictional distinction before the ADR existed. **Caveat:** at least one sampled real-named entry (Kokusho) truncates real text (drops Flying + the life-gain clause) without changing the current assertion — conversion can't be a blind find/replace; each swap needs a check that real text still exercises the intended branch. Extrapolated snapshot growth: ~100-250 new real cards. See the recommended internal split in Batch 9 below. |
| test_signals_dash.py | 0 | 0 | 0 (SPECIAL 2) | S | **SPECIAL:** nameless oracle-only positive/negative probes for `serves()` (Equipment / Aura) — a real positive (Bonesplitter, in snapshot) and a real Aura negative (Rancor / Ethereal Armor, neither in snapshot) would satisfy the ADR's "real near miss" rule better than generic shape probes. |
| test_signals_floor.py | 0 | 0 | 4 | — | Overlays (P/T/keywords) on records rebuilt from `crosswalk_fixture_cards.json` — legitimate; a second real-card fixture mechanism (see test_signals_floor's SPECIAL S2 in the deck-forge partial-batch report: 10 of its names aren't in the testkit snapshot either — an architecture question, not a per-file fix). |
| test_signals_generalized.py | 60 | 0 | 9 (SPECIAL 12) | L | Mostly inline dicts for `spec_for(...).serve.matches`/`lane_covers`, plus 11 oracle-text snippets lifted from real cards (Dong Zhou, Banisher Priest, Krenko Tin Street Kingpin, Tinybones, Bria, Tromokratis, etc. — Tromokratis and Tinybones drop real reminder/rider text). 17 of 60 already in snapshot; 43 not. **SPECIAL (12):** 2 dead fixtures to delete (unused paraphrases), 6 fictional-named clause probes (5 defensible machinery, 1 — "Reanimator" — is word-for-word Zombify's text and should convert), 4 `serves()` negatives with fictional names that admit or imply a real card in a comment (Disfigure-like, Self Discounter/Ghalta, Generic Donate/Harmless Offering, Vanilla Double Striker) — each should swap to the named real near miss. |
| test_signals_membership_aggregation.py | 0 | 0 | 6 | — | Fictional theme probes; comment explains the deck cards are deliberately left without concept trees. Clean. |
| test_signals_rules_audit.py | 1 | 0 | 0 (SPECIAL 1) | S | CONVERT: Gisela, the Broken Blade partner dict (not in snapshot). **SPECIAL:** "Other Meld" fictional negative — a real meld half with a different partner (Hanweir Garrison, Graf Rats; neither in snapshot) would be the proper near miss. |
| test_source_avenue_split.py | 0 | 0 | 2 | — | Nameless `aura`/`equip` dicts for `_matches_filters` — pure machinery. |
| test_staples.py | 4 | 0 | 2 (SPECIAL 1) | L | Sol Ring, Cultivate, Counterspell, Command Tower — all in snapshot, clean convert, no overlay gaps. **SPECIAL:** file docstring says "synthetic records ... same constraint as the rest of the suite" (no network) — stale now that testkit serves these four with zero network dependency; convert and update/remove the docstring rationale. |
| test_trim_lands.py | 6 | 0 | 2 | M | `_basic()` for all 6 basics: Mountain/Forest in snapshot; Plains/Island/Swamp/Wastes not. |
| test_tune_endpoint.py | 5 | 0 | 1 | M | Goblin Rabblemaster, Hill Giant (not in snapshot), Mountain, Lightning Bolt, Shock — all verbatim-correct otherwise. |
| test_views.py | 3 | 0 | 0 (SPECIAL 2) | L | CONVERT: Atraxa, Forest, "Settle the Wreckage" (real, not in snapshot, faithful truncated paraphrase). **SPECIAL:** two names ("Rise of Sozin // Fire Lord Sozin", "Belladonna Took") turned out on external lookup to be real printed cards (Avatar/Hobbit sets) with substantially wrong hand-written text — since neither test's assertion depends on real behavior (DFC-face-folding shape, badge-flag plumbing), renaming both to obviously-fictional placeholders is cleaner than expanding the snapshot for text that isn't needed. |

### tests/proxy-printer and tests/cube-wizard (no action needed)

| File | CONVERT | RENAME | SYNTHETIC-OK | Notes |
|---|---|---|---|---|
| test_art_differentiation.py | 0 | 0 | ~15 | Real names used only as art-lookup slug keys; no behavior claim. |
| test_art_fetcher.py | 0 | 0 | ~40 | Mocked-HTTP scraping machinery; real deck-entry names used via type_line/all_parts shape only. |
| test_art_lookup.py | 0 | 0 | ~15 | Slug/catalog-tier lookup, some deliberately fictional type lines. |
| test_compute_layout.py | 0 | 0 | ~20 | Pure PDF geometry math; no rules-behavior assertion. |
| test_render_smoke.py | 0 | 0 | ~5 | End-to-end PDF text-extraction smoke test. |
| test_token_discovery.py | 0 | 0 | ~12 | Token-walk/dedup over `all_parts`; names are graph nodes only. |
| test_smoke.py (cube-wizard) | 0 | 0 | 6 | CLI-help + `classify_cube_category` unit tests, fully generic dicts. |

### Already fully compliant / out of scope (no table entry needed)

`test_bulk_loader.py`, `test_card_pool.py`, `test_card_search.py`,
`test_commander_cost.py`, `test_cube_balance.py`, `test_custom_format_shared_library.py`,
`test_deck_diff.py`, `test_draft_ai.py`, `test_dropped_clauses.py`,
`test_field_corrections.py`, `test_formats.py`, `test_hydrated_pt_gates.py`
(SPECIAL only), `test_integration.py`, `test_name_index.py`,
`test_playtest_custom_format.py`, `test_playtest_draft.py`, `test_set_scan.py`,
`test_theme_presets.py`, `test_tuner_shape.py`, `test_commander_discovery.py`,
`test_images.py`, `test_partner_widening.py`, `test_rate.py`, `test_roles.py`,
`test_row_class_permutation.py`, `test_signals_membership_aggregation.py`,
`test_source_avenue_split.py`, plus all of `tests/proxy-printer` and
`tests/cube-wizard` and all of `tests/lgs-search`/`tests/rules-lawyer`/
`tests/deck-strat`/`tests/deck-wizard`.

## Decisions (Dan, 2026-09-23)

1. `test_known_tokens.py`: carved out in ADR-0056 (phase-mirrored data). No conversion.
2. `crosswalk_fixture_cards.json`: merge into the snapshot. That is Batch 10, after the
   per-file batches.
3. Stripped `oracle_id` fixtures (`test_budgets.py`, `test_ranking.py`): convert to
   `test_card(name)`, then drop `oracle_id` explicitly with a why-comment.

Also: `test_price_check.py` still hand-types Persistent Petitioners (goes in Batch 1).

**Batch 10 — merge `tests/fixtures/crosswalk_fixture_cards.json` into the snapshot.**
Point `test_crosswalk.py` / `test_tree_synthesis.py` at `testkit`; delete the fixture file.

## Proposed batches (~10 files each, no file in two batches)

**Batch 0 — `tests/mtg-utils/conftest.py` (do first; highest blast radius).**
Depends on it: `test_deck_hydrate.py`, `test_integration.py`,
`test_hydrated_pt_gates.py`, `test_price_check.py`, `test_scryfall_lookup.py`
(`sample_bulk_data`); `test_card_summary.py`, `test_cut_check.py`,
`test_deck_stats.py`, `test_deck_diff.py`, `test_mana_audit.py`
(`hydrated_cards`); `test_archetype_audit.py`, `test_cube_balance.py`,
`test_cube_stats.py`, `test_cube_diff.py`, `test_cube_legality_audit.py`,
`test_pack_simulate.py`, `test_export_cube.py` (`cube_hydrated(_real_removal)`
/ `sample_cube_json` / `sample_commander_cube_json`); `test_deck_stats.py`
(`alt_cost_cards`); `test_cut_check.py`, `test_rules_lookup.py`
(`trigger_test_cards`); `test_combo_search.py` (`sample_combo_response(_empty)`);
`test_edhrec_lookup.py`, `test_integration.py` (`sample_edhrec_response`).
Since most of those consuming files only read names/quantities back out (not
the raw oracle text), converting conftest's fixtures should be low-risk for
them — but run the full suite after, not just the files in this batch.

**Batch 1 — mtg-utils, classification & legality core (9 files).**
`test_archetype_audit.py`, `test_archetype_resolver.py`, `test_card_classify.py`,
`test_companion.py`, `test_legality_audit.py`, `test_cube_legality_audit.py`,
`test_cut_check.py`, `test_build_deck.py`, `test_find_commanders.py`.

**Batch 2 — mtg-utils, tuner + tree suite (9 files).**
`test_tuner_bracket.py`, `test_tuner_classify.py`, `test_tuner_metrics.py`,
`test_tuner_swaps.py`, `test_tuner_tune.py`, `test_tree_synthesis.py`,
`test_deck_forge_clis.py`, `test_custom_format_classifier.py`,
`test_combo_search.py`.

**Batch 3 — mtg-utils, gauntlet/mana/hydrate (9 files).**
`test_mana_audit.py`, `test_gauntlet_build.py`, `test_gauntlet_inference.py`,
`test_hydrated_deck.py`, `test_deck_stats.py`, `test_deck_tune_cli.py`,
`test_price_check.py`, `test_parse_cube.py`, `test_hydrated_pt_gates.py`.

**Batch 4 — mtg-utils, import/lookup/adapters + playtest (10 files).**
`test_mtga_import.py`, `test_mtgjson_adapter.py`, `test_phase_bump.py`,
`test_rulings_lookup.py`, `test_scryfall_lookup.py`, `test_card_summary.py`,
`test_phase_record_grouping.py`, `test_crosswalk.py`, `test_playtest_gauntlet.py`,
`test_playtest_goldfish.py`.

**Batch 5 — deck-forge, collection/discovery/companion (9 files).**
`test_app.py`, `test_balance_lands.py`, `test_collection.py`,
`test_commit_point.py`, `test_companion_zone.py`, `test_constructed.py`,
`test_engine.py`, `test_engine_rules.py`, `test_find.py`.

**Batch 6 — deck-forge, find/handoff/printings (9 files).**
`test_find_candidates.py`, `test_handoff_goldfish.py`, `test_handoff_proxies.py`,
`test_import.py`, `test_limited.py`, `test_medium_wildcards.py`,
`test_persistence.py`, `test_printing_ownership.py`, `test_printings.py`.

**Batch 7 — deck-forge, safety/staples/tune/views + odds (9 files).**
`test_safety_rails.py`, `test_staples.py`, `test_trim_lands.py`,
`test_tune_endpoint.py`, `test_views.py`, `test_crosswalk_seam.py`,
`test_production.py`, `test_known_tokens.py`, `test_engine_endpoints.py`.

**Batch 8 — deck-forge, signals/avenue/budgets/ranking (8 files).**
`test_avenue_gaps.py`, `test_budgets.py`, `test_keyword_gaps.py`,
`test_phase_crosscheck.py`, `test_ranking.py`, `test_signals_generalized.py`,
`test_signals_rules_audit.py`, `test_signals_dash.py`.

**Batch 9 — `tests/deck-forge/test_signal_specs.py` alone.**
~480 real-card literals across 223 test functions — big enough to be its own
job. Recommend an internal multi-pass split by section rather than one
change: start with the 5 hoisted module-level constants (`SELF_MILL`,
`OPPONENT_MILL`, `TOKEN_MAKER`, `BURN`, `LIFEGAIN` — small blast radius),
then the ~200 scattered per-test literals grouped by `TestXServe` class,
leaving the already-compliant tail (~lines 7480-7742) untouched.

## Totals

- **Files with at least one hand-built card-data construct:** 108 (105 from
  the narrow grep + 3 from the broader second pass), plus both `conftest.py`
  files.
- **CONVERT instances:** ≈990 total, of which ≈480 are in
  `test_signal_specs.py` alone. Next-largest: `test_card_classify.py` (~55),
  `test_companion.py` (~35), `test_legality_audit.py` (29),
  `test_avenue_gaps.py` (27), `test_playtest_goldfish.py` (25),
  `test_signals_generalized.py` (60), `test_budgets.py` (19).
- **RENAME instances:** ≈43, spread thin (no file has more than 7).
- **SYNTHETIC-OK instances:** ≈880+, the bulk of the suite — legitimate
  machinery, no action needed.
- **SPECIAL judgment calls:** several dozen individual cases; the file-level
  concentrations are `test_crosswalk.py` (7 — a second real-cards-by-name
  mechanism via `crosswalk_fixture_cards.json`), `test_known_tokens.py`
  (11 — a non-Scryfall real-data source testkit doesn't serve),
  `test_signals_generalized.py` (12), and the recurring "deliberately
  dropped `oracle_id` to exercise the text-fallback path" pattern shared by
  `test_budgets.py` and `test_ranking.py`.
- **Files needing zero action:** ~35 (already fully compliant or pure
  machinery with fictional names throughout) — see the list above.
- **Real card names confirmed absent from the snapshot** (a `build-card-snapshot`
  run is required before any of these convert cleanly): Korvold Fae-Cursed
  King, Overgrown Tomb, Thrasios Triton Hero, Malakir Rebirth // Malakir Mire,
  Plains, Island, Swamp, Wastes, Mind Stone, Hill Giant, Lumbering Battlement,
  Laboratory Maniac, Kodama's Reach, Farseek, Golgari Signet, Consider,
  Discovery, Dragon's Rage Channeler, Persistent Petitioners, Ghave Guru of
  Spores, Masked Meower, Keruga the Macrosage, Yorion Sky Nomad, Winter Orb,
  Time Stretch, Time Warp, Mana Crypt, Pact of Negation, Platinum Angel,
  Mortal Combat, Lava Axe, Exsanguinate, Steam Vents, Bind // Liberate,
  Murderous Redcap, Rhythm of the Wild, Moritte of the Frost, Priest of
  Titania, Iron-Shield Elf, Lathril Blade of the Elves, Bloodline Pretender,
  Hobbit Hole, Wood Elves, Knight of the Reliquary, Fabled Passage, Ignoble
  Hierarch, Branchloft Pathway // Boulderloft Pathway, plus ~43 names in
  `test_signals_generalized.py` and ~11 in `test_avenue_gaps.py` (see those
  rows), and ~100-250 more inside `test_signal_specs.py` (estimate, not
  enumerated). One `build-card-snapshot` run covering the whole batch plan
  is more efficient than one per file.
