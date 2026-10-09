# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

**From the Omnath Competitive Brawl build (2026-10-04)**

- **Read MTGJSON's Competitive Brawl key once it exists.** Scryfall's API now carries
  `competitivebrawl`, and it agreed with `Format("competitive_brawl")` on every card
  spot-checked. MTGJSON (5.3.0+20261004) drops it: its `ScryfallLegalities` model
  (`mtgjson5/models/submodels.py` `Legalities`) is a fixed TypedDict, and pydantic drops
  the undeclared key. Fix proposed upstream in mtgjson/mtgjson#1742 (2026-10-04).
  When it ships, add the key to `_mtgjson/adapter._LEGALITY_FORMATS` and point
  the format at it. That would retire `ignores_legality_key_bans` and the hand-kept
  `COMPETITIVE_BRAWL_BANNED` snapshot, after diffing the two over the whole pool.
- **Move the remaining oracle-text regexes in the tuner and deck CLIs to phase's IR**
  (next after the 2026-10-04 tuner changes, at Dan's request). Card reads go through the
  corrected trees and the shared crosswalk reads; a clause phase can't parse belongs in
  the recovery stage or a ledgered bridge (ADR-0047/0048), never a free regex. The
  `_analysis/text_reads.py` patterns are the sanctioned bridge / membership-floor set and
  out of scope. Pre-existing targets:
  - `cut_check.py` (~30): trigger types and values, keyword interactions,
    self-recurring, `detect_commander_multiplication`'s copy patterns, the zone grant.
    The tuner's protection already moved to `_analysis/multipliers.py`; cut-check's own
    report should read the same trees.
  - `_tuner/issues.py`: `_RAMP_CONDITIONAL` ("only if you control" in the oracle text
    keeps a conditionally gated rock out of the tuner's ramp sourcing); read the
    mana ability's activation condition off the tree.
  - `find_commanders._is_partner` / `_partner_with_target`: read
    `card_classify.partner_abilities` instead of the oracle (the `Partner—[text]`
    groups and Doctor's companion are already there).
- **Phase gaps behind the closer, alternative-cost and mass-land-denial reads**
  (found moving `_tuner/` and `deck_stats` onto the trees, phase v0.94.0; report
  upstream, Dan posts). Each is a card the old regexes read and the trees don't:
  - Reach: `unparsed_quantity` residues park "loses life / deals damage equal to …"
    (Within Range, Soulblast, Final Punishment, Mjölnir; ~28 such residues name
    damage or life loss). Underbridge Warlock's boon reads as a self loss. (The
    `where_x_binding` X effects — Insatiable Hemophage, Zenith Flare — are read by
    `reads.unbound_x_reach`, canary `test_unbound_x_reach_canary`.)
  - Our own walk: `reads._find_owner_wrapper` doesn't descend `per_choice_effect` /
    `else_ability`, so a vote's or an else-branch's `player_scope` is lost (Tyrant's
    Choice, Sphinx Sovereign). Widening it moves `effect_player_reach` for every lane
    — do it with a corpus diff.
  - Game wins: Frodo, Sauron's Bane's Rogue clause is dropped (its second ability
    parses as the Ring tempting you); Celestial Convergence's win is an
    `unbound_subject` residue.
  - Alternative costs, each corrected where the tree is built with a canary: keyword
    lines with a non-mana cost parked as residues (morph "Reveal a blue card", blitz
    / warp / madness with life, Escape Velocity's escape —
    `core._dropped_keyword_costs`, `test_dropped_keyword_costs_canary`); suspend X
    read as count 0 and Warbringer's / Catalyst Stone's cost changers read as empty
    keywords (`core._misread_keyword`, `test_misread_keyword_canary`).
  - Mass land denial, each with a canary or a ledger row: End Hostilities, Eye of
    Singularity and Herald of Vengeance lose their narrowing clause and read as
    "all permanents" (vetoed by `reads.NARROWED_PERMANENT_SWEEPS`); Exhaustion's and
    Mana Vapors' one-untap-step effect parses as a lasting static
    (`_lasting_static_defs`); Burning of Xinye's "destroys four lands" is a residue
    and Global Ruin's sacrifice a tracked set (both ledger bridges).
- **Leftovers from moving `roles.protects` onto the signal path** (2026-10-08).
  - deck-forge's "Pillowfort" sub-avenue (`signal_specs._PILLOWFORT_EXTRA`) still
    serves by an oracle regex; the `pillowfort` key now carries the same fact.
  - `ranking._structural_floor` (`is_fixing` / `is_ramp` / `cmc_bomb`) is serialised
    into every candidate's score and read by nothing — the SPA, the tuner and the
    CLIs all ignore it (its `is_tutor` text read was deleted for that reason).
- **Two commander-multiplier gaps.** Syr Konrad's trigger reads as `ChangesZone` with
  no zones (a phase gap), so `_analysis/multipliers` can't match a dies doubler to it;
  report upstream rather than work around it. And `trees.object_facts` reads printed
  types only, so Grist, the Hunger Tide ("a 1/1 Insect creature" off the battlefield)
  isn't seen as a creature spell Double Major or Lithoform Engine can copy; read the
  off-battlefield type-adding static from the tree.

**From arena-meta (2026-10-05, ADR-0059)**

- **Rank Find's candidates by meta inclusion on an Arena build.** The tuner reads the
  meta archetype's card shares; deck-forge's Find still ranks by synergy, then price,
  then curve. Feeding `MetaContext.share` into `_analysis.ranking` as a tiebreak
  (never above synergy) was left for later, by agreement.

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
- **Symmetric shields aren't protection** (Dan, 2026-10-08): `roles.protects` is
  protecting YOUR board, so a permanent's shield over every player's objects alike
  (Crumbling Sanctuary, Plated Pegasus, Well-Laid Plans' residue) stays out; a fog
  you cast and an optional shield you aim stay in.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
