# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

**From the twohg-guide skill (2026-09-27)**

- **The edict presets match sacrifices you make yourself.** `removal_tutors.
  _edict_answer_types` applies no actor gate, so `creature-edict` /
  `planeswalker-edict` fire on Winter, Tormented Loner and Mycoloth ("you may
  sacrifice…"). `edict_makers` already has the right actor read; gate the removal walk
  on the same predicate (twohg_scan now calls it) and re-check the preset real-card tests.
- **`role_of` has no removal fallback for a set phase hasn't parsed.** The removal
  preset reads signal keys only, so on a set newer than `PHASE_TAG` `set-scan` reports
  no removal while `twohg-scan`'s text path finds it. Move a removal text degrade into
  `roles` beside `ramp_by_text` so both readouts share it.
- **About eight copies of the cache-root lookup** (`$MTG_SKILLS_CACHE_DIR` else
  `~/.cache/mtg-skills`: bulk_loader, _phase, proxy_print, download_mtgjson,
  _deck_forge/production, _stores/_common, …). `_http.cache_root()` now exists; migrate
  the rest to it.
- **phase tags "each other player" as `Opponent`.** Grave Pact and Syphon Mind carry
  `player_scope: Opponent`, which only differs from "each opponent" in team formats
  (it includes your teammate). phase doesn't support team formats yet, so this isn't
  reported upstream for now. `twohg_scan` vetoes it with an oracle-text check guarded by
  a `retirement_canary` test; delete the veto when the canary fails.
- **`twohg-scan --shadow`.** Listing IR-vs-text disagreements (information only, never
  merged) would calibrate the text fallback and surface phase misparses. Deferred until
  a set arrives that phase hasn't parsed. Baseline from FRA with the IR stripped: the
  text path misses Tomik, Izzet Sparkmage (a damage *replacement*, not an "each
  opponent" clause), reads Cruel Calculations as target-player (phase drops its player
  target), and differs on removal reach for about 18 cards.

**From the phase v0.94.0 bump (2026-09-26)**

- **d20 roll tables.** Phase now parses them into `results[]` rows, which the shared
  effect walker never reads (only the ramp lane reads them, locally). Farideh's
  Fireball (`symmetric_damage_each`) and Overwhelming Encounter (`pump_makers`) lost
  their old flattened fires. Walking `results[]` adds about 50 fires across 117 cards,
  so those need a review first. (Druid of the Emerald Grove's lost `tutor` was
  accepted: a basic-land fetch is ramp, which it keeps.)
- **Walking `else_ability` everywhere.** "Otherwise" branches are opt-in per read
  (`walk_effects_with_else`). Walking them globally would change 176 cards: mostly
  plausible gains, but the Champion cards' `self_etb_payload` looks doubtful and 3
  fires are lost (`suspect_matters` ×2, `exile_removal`).
- **`named_synergy_overloaded_named_node`'s gap is the constant `True`**, so that
  bridge row can never retire itself.
- **`_phase.run_commander` loses finished games on timeout**, the flaw `run_duel`
  had (limited plan P3): a timeout on game N discards games 1..N-1. Nothing calls it
  today; give it `run_duel`'s chunked budget before anything does.
- **Roster counts are still hand-bumped.** Every pin bump edits the hard-coded counts
  in `tests/mtg-utils/test_card_ir_mirror.py` (Effect roster length,
  `distinct_variants_observed`, tagged + struct mirror classes) by hand;
  `bump-phase-pin` could derive and rewrite them like the rosters themselves.
- **Raw walks left in bridge-ledger matches.** The purity rule covers gaps only; the
  Ceremonial Knife `GrantTrigger` walk and `_blood_sacrificed_trigger_match` still
  walk nodes directly.

**From the 2026-09-17 architecture review (worth exploring, not started)**

- **One Storefront browser session.** `open_handoff` / `open_login` are repeated,
  near-identical, across the four Storefront adapters (TGP, Atomic Empire,
  TCGPlayer, Mana Pool): eight methods.
- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Known lane recall gaps (surfaced by ADR-0051; a lane fix repairs every consumer)**

- Tireless Provisioner ("Food or Treasure") fires only `food_makers`.
- Surveyor's Scope (fetch X basics) reads as `tutor`.
- Firebending token makers aren't ramp (Firebender Ascension, Fire Nation Attacks,
  Cruel Administrator, Fire Nation Occupation). Vibranium-mana token makers are
  suspected too, but no card was found to test.

**Discovery ranking:** see ADR-0043's terminal-state amendment for the unclaimed
headroom and parked items.

## Settled: don't re-suggest

- **Two-arm lanes** (a structural arm OR a `synth_<key>` reference-arm concept, 91 of
  279 lanes): stable by design, not debt (ADR-0038 amendment). Don't tabulate or
  rename them.
- **Judged in good shape by the 2026-09-17 review:** `theme_presets` (a registry over
  signals; removal isn't duplicated), `cut_check`, proxy-printer's layout and Fetcher
  seam, `phase_bump`, `testkit`, `agent_bridge` / `events`, and the tuner's classify,
  shape and bracket modules.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
