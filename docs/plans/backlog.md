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
- **Phase gaps behind the closer, alternative-cost and mass-land-denial reads**
  (found moving `_tuner/` and `deck_stats` onto the trees, phase v0.94.0; report
  upstream, Dan posts). Each is a card the old regexes read and the trees don't:
  - Reach: `unparsed_quantity` residues park "loses life / deals damage equal to …"
    (Within Range, Soulblast, Final Punishment, Mjölnir; ~28 such residues name
    damage or life loss). Underbridge Warlock's boon reads as a self loss. (The
    `where_x_binding` X effects — Insatiable Hemophage, Zenith Flare — are read by
    `reads.unbound_x_reach`, canary `test_unbound_x_reach_canary`.)
  - Game wins: Frodo, Sauron's Bane's Rogue clause is dropped (its second ability
    parses as the Ring tempting you); Celestial Convergence's win is an
    `unbound_subject` residue.
  - Alternative costs, each corrected where the tree is built with a canary: keyword
    lines with a non-mana cost parked as residues (morph "Reveal a blue card", warp
    / madness with life, Escape Velocity's escape; blitz parses since v0.104.0 —
    `core._dropped_keyword_costs`, `test_dropped_keyword_costs_canary`); suspend X
    read as count 0 and Warbringer's / Catalyst Stone's cost changers read as empty
    keywords (`core._misread_keyword`, `test_misread_keyword_canary`).
  - Mass land denial, each with a canary or a ledger row: Eye of Singularity and
    Herald of Vengeance lose their narrowing clause and read as "all permanents"
    (vetoed by `reads.NARROWED_PERMANENT_SWEEPS`; End Hostilities is an
    `attached_to_qualifier` residue since v0.104.0); Exhaustion's and
    Mana Vapors' one-untap-step effect parses as a lasting static
    (`_lasting_static_defs`); Burning of Xinye's "destroys four lands" is a residue
    and Global Ruin's sacrifice a tracked set (both ledger bridges).
- **Phase gap behind the tuner's ramp sourcing** (found 2026-10-08, phase v0.94.0;
  report upstream, Dan posts). Boxing Ring's "Activate only if you control a
  creature that fought this turn" is an `unparsed_condition` residue, not an
  activation restriction — the only legal card whose mana or Treasure ability is
  gated that way (`reads.UNPARSED_ACTIVATION_GATE`,
  `test_boxing_ring_gate_is_still_a_residue_canary`).
- **Commander-multiplier gap.** Syr Konrad's trigger reads as `ChangesZone` with no
  zones of its own: phase v0.104.0 folds its three moves into `zone_change_clauses`,
  which `reads.trigger_zone_changes` now reads (graveyard_matters does). Teach
  `_analysis/multipliers` the same read so a dies doubler matches it.
- **Phase misparses behind cut-check reads** (found 2026-10-08; report upstream,
  Dan posts). Each has a canary: Glorfindel, Dauntless Rescuer's "can't be blocked
  by more than one creature each combat" parses as `CantBeBlockedBy` a typeless
  filter (`test_glorfindel_blocking_limit_misparse_canary`); Wyll's Reversal loses
  "with one or more targets", so it reads as a commander-spell copy
  (`test_wylls_reversal_target_constraint_canary`); aftermath halves (Dusk // Dawn),
  Garza's Assassin's recover, Salvation Colossus's unearth and Oscorp Industries'
  mayhem are dropped, so the `self-recurring` preset reads them by keyword
  (`test_self_recurring_keyword_gap_canary`); Nether Shadow's graveyard return is an
  `unparsed_condition` residue since v0.104.0 (ledger row
  `nether_shadow_graveyard_return_parked`); Bumi's Feast
  Lecture's earthbend return binds to the Food token (`LastCreated`) instead of the
  land (`test_earthbend_last_created_binding_canary`).
- **`serve_self_recur` is still an oracle regex** (`signal_specs._shared._self_recurs`,
  the reanimator avenue's and aristocrats' "Self-recurring fodder" creatures). The
  `self_recurring` key's idents, filtered to creatures, don't line up (2026-10-08, legal
  corpus): 294 kept, 302 gained, 28 lost. The key is wider by design — any per-game
  reuse: self-bounce (Arcanis, Blinking Spirit), dash (Kolaghan Forerunners), returns
  to hand, persist (Kitchen Finks), re-suspend (Epochrasite) — where the serve wants a
  creature coming back from the graveyard to play. Of the 28 lost, some are the
  regex's misfires (Emptiness and Kami of Mourning return another card or grant a
  perpetual ability), some key misses phase hides: cast-from-graveyard permissions on
  a trigger or keyword (Tenacious Underdog's blitz, Skyclave Shade, Sproutback
  Trudge). Switching needs a zone-discriminating subject on the key's ident
  (graveyard → battlefield / stack) and those misses read first.

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

**From walking phase's branch shapes (2026-10-09)**

- **Phase misparses behind the branch-misread registry** (`_card_ir.branches.
  BRANCH_MISREADS`, each row with its `retirement_canary`; report upstream, Dan
  posts). Fraying Line's "that player may pay {2}" is a `PayCost` with `payer:
  Controller`, so its "Otherwise" branch reads as yours (pruned from the certain
  records: LOW); Osseous Sticktwister's "each opponent who didn't sacrifice … or
  discard a card this way" parses as a second choice with a discard branch; Spitting
  Slug's "each creature blocking or blocked by this creature" loses its narrowing
  (both dropped from every tree). Also unreported, no workaround: Worms of the
  Earth's "any player may" choice is `chooser: Controller` (read off the wrapper's
  `optional_for`), and Ensnared by the Mara's villainous branch carries
  `player_scope: All`, so its (LOW) impulse_top_play scopes "each".

**From the phase v0.104.0 bump (2026-10-09)**

- **Phase now fails closed on what it can't represent** (#9392 and kin), parking the
  whole effect as a residue named for its shape (`unparsed_condition` 63 → 216 at
  v0.104.0, `put_counter_tail`, `attached_to_qualifier`, `static_structure`,
  `unparsed_verb_arguments`, `perpetual_modify_pt`, `granter_reference_unreached`).
  Recovery reads the parked verbs (`recovery.ALLOWLIST`), each instruction of a
  compound clause and a granted body's residue (nine rows retired that way,
  2026-10-09); the remaining v0.104.0 ledger rows are parked conditions and verbs the
  grammar doesn't tag. Report upstream by residue class, not per card.
- **Lane-side reads of recovered clause text remain** beside the seam's marks:
  `damage_for_each`'s `_DFE_RECOVERED_RX`, `named_counter_misc`'s
  `_RECOVERED_POWER_TAP_RE`, `_recovered_power_damage`, `creatures_matter`'s
  `_RECOVERED_TEAM_COUNTER_RE` and `target_player_draws`'
  `_RECOVERED_DRAW_REPLACEMENT_RE` (a replacement diagnostic the seam could refuse).
  Move each onto a `read_clause` mark the same way draw, discard, damage reach and
  make_token's kinds moved (2026-10-09), population unchanged.
- **Upkeep-payment discards are undecided** (Dan's call). Keyword-cost `Discard`
  leaves are decorated since 2026-10-09 (Sabin, Master Monk's blitz reads as a
  discard outlet again), except Echo and Cumulative upkeep
  (`core._UPKEEP_PAYMENT_KEYWORDS`): Deepcavern Imp, Rakdos Headliner ("Echo—Discard
  a card") and Vexing Sphinx ("Cumulative upkeep—Discard a card") would fire
  `discard_outlet`. A keyword discard merged into a spell's own costs (Collective
  Brutality's escalate, Forbid's buyback, Conflagrate's flashback) still fires
  nothing: `discard_outlet`'s cost walk reads the unit's node, not merged costs.

**From the 2026-09-17 architecture review (worth exploring, not started)**

- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Known lane recall gaps (surfaced by ADR-0051; a lane fix repairs every consumer)**

- Vibranium-mana token makers are suspected not to count as ramp, but no card was
  found to test.

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
- **Firebending isn't ramp** (Dan, 2026-10-09): not a creature with firebending
  (Uncle Iroh; `firebending_makers` is out of the ramp preset's keys), a maker of
  firebending tokens (Fire Nation Attacks, Firebender Ascension, Cruel
  Administrator, Fire Nation Occupation) nor a grant (Sozin's Comet, Fire Nation
  Turret, Fire Nation Cadets). The mana comes only as the creature attacks and lasts
  until end of combat (CR 702.189a), so it doesn't speed up the curve.
- **Symmetric shields aren't protection** (Dan, 2026-10-08): `roles.protects` is
  protecting YOUR board, so a permanent's shield over every player's objects alike
  (Crumbling Sanctuary, Plated Pegasus, Well-Laid Plans' residue) stays out; a fog
  you cast and an optional shield you aim stay in.
- **Every strong candidate from the 2026-09-12 review shipped** (ADR-0045 to 0050,
  plus ADR-0041 and ADR-0013 finished).
