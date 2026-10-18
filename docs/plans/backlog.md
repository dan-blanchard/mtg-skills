# Backlog: open follow-ups and settled verdicts

Things found but not done, and things already judged, gathered from architecture
reviews, phase bumps and studies. Check here before proposing a refactor or re-running
a review. Delete an entry when it ships; the commit or ADR records it from then on.

## Open

**From the Jace, Multiverse Architect precon tune (2026-10-17)**

- **`scryfall-lookup --batch` without `--bulk-data` dies on one Scryfall 503.** A
  name the local pool can't resolve (or every name, when no `--bulk-data` is
  passed) goes to `fetch_card`, and one `HTTPError` aborts the whole batch with a
  traceback instead of landing in the envelope's `missing`. Catch the per-name
  network failure in `lookup_single`'s batch loop and report it as missing; keep
  the hard exit for a bulk that can't be read at all.
- **What the polymorph tune still gets wrong** (after 2026-10-18's tuner pass:
  carers never count lands or the cards the commander's lane serves as payoffs;
  a main theme needs builders (`focus_main_carers`); a commander's sibling reads
  of one ability collapse into its deepest held lane; fed-only engine cards
  re-bucket as filler; the cut ranking protects the lane's own emitters; the
  commander is never a misfit while its lane is viable; `cheat_into_play`
  carries the cheated card type as its subject and `wants_fodder` names the
  polymorph shape — see `deck-forge/CONTEXT.md` "Focus"). The Multiverse
  Reforged precon now reads FOCUSED: Cheat into play (main, 7 carers),
  Polymorph fodder and Token generators (subs), with Combat, Artifacts and
  Spellslinger fed. Left: (a) "Polymorph fodder" and "Token generators" are one
  theme read twice (the same seven polymorphs care about both; the broad serve
  adds Elspeth / Overlord / Shark Typhoon the fodder serve rightly leaves out) —
  a collapse by shared carers, not shared members, would fold them; (b) the
  only quality read on a payoff the lane serves (a bomb Jace flips into) is
  play-rate, so a weak flip with a null rank still reads as a low-value upgrade
  target while a strong new one does too — a flip-quality read (power, ETB
  value, evasion) over the cheat subject's payoff arm is the next step; (c)
  `artifacts_matter` is emitted for artifact-TOKEN makers (Skrelv's Hive, White
  Sun's Twilight, Currency Converter) — a doer read under a `_matters` key, the
  one ADR-0034 split the artifact / enchantment lanes never got, so three token
  makers read as three cards caring about artifacts; (d) the phantom
  "Activated-ability engine" emerging theme is down to Niv-Mizzet and Staff of
  the Storyteller once mana abilities are out (CR 605.1a), and "Lifegain
  (makers)" surfaces as emerging on two carers — the emerging floor of one carer
  may be too low for a 100-card deck; (e) `power_threshold_x_cheat_commander`
  and `etb_payoff_x_flood_commander` now anchor on a Creature-typed or untyped
  cheat only — the Planeswalker / Artifact / Enchantment cheat subjects have no
  pair rows yet (Zur's enchantment tutor, Stoneforge's equipment); (f)
  `_card_ir/card_subtypes.py` (and `creature_types.py`) are generated from the
  repo's tracked `mtg-utils/comprehensive-rules-20260807.txt`; the 2026-09-25
  CR adds Heartwood to the artifact types, so both regenerate when that
  tracked file is bumped (`rules-lookup --card-subtypes` / `--creature-types`).

- **What the 25-precon audit still finds wrong** (2026-10-18: every Commander
  precon list from MTGJSON's deck files, one per archetype family, tuned at
  `--budget 100 --max-swaps 10` and compared with 2-3 published upgrade guides
  each — `docs/plans/precon-audit-2026-10-18.md` has the method, the before /
  after table and the per-precon reads). Fixed in that pass: the add page is
  paged by play-rate, a premium card is never a band trim, a near-miss outranks
  dead weight only when it ends the game, the verdict counts directions, a main
  needs carers in proportion to its feeders, the primary lane is the held lane
  most cards care about. Left, by weight:
  (a) **No quality read inside a lane.** 141 of the 170 cards the guides cut
  are cards the tuner protects as carers of the main or doers of the
  commander's lane — the weak Slivers, Dinosaurs and Vampires a guide swaps for
  better ones. Blood Rites proposes nothing at all (43 of 45 Vampire-lane cards
  are carers, so there is no cut pool) while short on ramp, draw and wipes and
  with Vito / Sanguine Bond the consensus adds. The lane exemption from the
  low-value read was made for Jace's six-card polymorph lane; a lane of twenty
  or more doers should let its least-played members be upgrade targets, cut
  only for an add serving the same label. This is the flip-quality item above,
  generalized.
  (b) **Lane misreads the guides expose.** Gonti, Canny Acquisitor's first line
  ("spells you cast but don't own cost {1} less") reads as Cost reduction, not
  `wants_theft`, so Grand Larceny's theft lane (17 deep) has three carers and
  six on-theme cards (The Mimeoplasm, Siphon Insight) read as filler; Zurgo
  Stormrender's "whenever a creature token you control leaves the battlefield"
  is a tokens-matter carer the lane does not emit (Mardu Surge: Token
  generators 27 deep, one carer); Bello, Bard of the Brambles animates
  noncreature artifacts and enchantments of mana value 4+, a lane that does
  not exist, so his rocks read as "ramp over by 14"; Yuma, Proud Protector's
  Desert trigger has no lane (Desert Bloom: Lands matter 17 deep, no carer);
  Ellivere's Role tokens (Gylwain, Casting Director) are enchantment tokens
  the `enchantment_makers` read misses, so Gylwain reads as filler under an
  enchantments commander; a token doubler (Adrix and Nev, Esix) does not care
  about `token_maker`, so Deep Clue Sea cuts both; pillowfort cards
  (Comeuppance, Gideon's Sacrifice, Promise of Loyalty) read as "Superfriends"
  under Nelly Borca; "Opponents' graveyards" carries every "Your graveyard"
  carer (43 under Teval) — its cares-keys fold into `graveyard_matters`.
  (c) **Symmetric damage reads as interaction.** Endless Punishment's 35
  "interaction" (Blasphemous Act and the punisher suite) trips "interaction
  over by 20" and trims Enchanter's Bane; a damage-to-each-opponent spell under
  a punisher commander is the lane, not the template's removal row.
  (d) **A closer search that finds Bruce Banner.** `wincon_short` sources from
  `WINCON_SEARCH` with no avenue, so Sliver Swarm's closer is Bruce Banner //
  The Incredible Hulk and Living Energy's is Clown Car; the guides add The
  First Sliver, Craterhoof, Aurelia — a closer that serves the main lane. The
  remedy should be the main avenue's spec intersected with the closer read.
  (e) **Template bands versus a commander whose lane IS the band.** "Ramp over
  by 9" under Gimbal (artifacts) and "card draw over by 7" under Morska (Clues)
  trim the lane; a band whose members are mostly lane doers should relax or go
  advisory.
- **Competitive Brawl's "banned as a commander" reads as `restricted`.** The
  2026-10-12 B&R update introduced the category (mtg.wiki "Competitive Brawl"
  §Banned as a commander; Draftsim 2026-10-12): Oko, Thief of Crowns, Ragavan,
  Nimble Pilferer, Nadu, Winged Wisdom and Wrenn and Six are legal in the 99 but
  can't lead a deck; Yuriko, the Tiger's Shadow, Spider-Man 2099 and Light-Paws,
  Emperor's Voice joined them; Lutri is the only outright ban. The 2026-10-17
  AllPrintings encodes the category as `competitivebrawl: "restricted"` (the
  2026-10-14 bulk said `banned`). `Format.legality` therefore reads these as
  playable — right for the 99, wrong for `commander_eligibility` — and six tests
  that pin the old outright bans (`test_formats`, `test_legality_audit`,
  `test_price_check`) fail on a regenerated snapshot. Teach `formats.py`'s
  Competitive Brawl read that `restricted` means legal in the 99 and ineligible
  as commander (a new eligibility reason), re-pin the tests on Lutri for the
  outright ban and Oko for the commander ban, then regen the snapshot. The
  deck-wizard SKILL.md's "bans ten cards, as commander and in the 99" is stale
  the same way. Until then a bare `build-card-snapshot` run drags the drift in —
  the 2026-10-17 regen spliced only its two new cards.

- **Lane gaps behind the held serve specs** (the serve-ident pass, 2026-10-18;
  the full table is in `docs/plans/serve-idents-and-avenue-support.md` §2
  "Measured"). 41 specs keep their regex because the lane misses what the regex
  catches: +1/+1 counters placed by keyword actions (bolster, adapt, renown,
  monstrosity, connive, explore, endure, awaken — blocks plus_one, amass,
  incubate, modified); surveil as graveyard filling; granted / replacement
  Treasure and Food makers, forage; energy payers; random-discard outlets and
  granted connive; foretell granters and cost reducers; "all damage that would
  be dealt to you is dealt to X instead"; Bribery-style theft from an
  opponent's library (blocks `gain_control`); amass / endure / populate token
  makers read only off reminder text (blocks the `token_maker|you|*` wildcard
  conversions: token_maker, creature_etb, creatures_matter, edict_makers,
  damage_for_each, token_doubling). Report upstream where phase is the gap.
  The lifegain pair converted anyway and lost its 96 Food makers:
  `lifegain_makers` doesn't read the gain inside a Food token (Bake into a Pie,
  Bill the Pony).
  Lane false positives found the same way: Impending Flux on `suspend_matters`; The
  Book of Exalted Deeds on `exalted`; Investigator's Journal on
  `suspect_makers`; Astarion's "Friends —" mode on `partner_background`.

**From the Omnath Competitive Brawl build (2026-10-04)**

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
  mayhem are dropped, so the `self-recurring` preset and the "Self-recurring
  fodder" serve read them by keyword (`theme_presets.SELF_RECURRING_KEYWORD_GAPS`,
  `test_self_recurring_keyword_gap_canary`); Nether Shadow's graveyard return is an
  `unparsed_condition` residue since v0.104.0 (ledger row
  `nether_shadow_graveyard_return_parked`); Bumi's Feast
  Lecture's earthbend return binds to the Food token (`LastCreated`) instead of the
  land (`test_earthbend_last_created_binding_canary`).
- **Phase misparses behind the "Self-recurring fodder" serve** (found 2026-10-09,
  phase v0.104.0; report upstream, Dan posts). The serve reads the card's graveyard
  return routes (`card_advantage.comes_back_from_graveyard`); three legal creatures
  the old regex served stay out because
  phase loses "this card": Sproutback Trudge's and Syrix, Carrier of the Flame's "you
  may cast this card from your graveyard" is a `CastFromZone` with target `Any` in a
  battlefield-zone trigger; Worldheart Phoenix's (and Raffine's Guidance's)
  graveyard alternative cost is a `CastWithAlternativeCost` static whose `affected`
  is your typed permanents, active on the battlefield. Read with a canary: "you may
  cast it from your graveyard" (Skyclave Shade, Hildibrand Manderville, Mosswood
  Dreadknight, Ichor Aberration) is a `PlayFromExile` permission on an empty
  `TrackedSet` (`test_unbound_graveyard_cast_misparse_canary`); Forgeborn Phoenix's
  granted "return this card from your graveyard to battlefield" parses as a
  `Bounce` to hand (`test_perpetual_bounce_misparse_canary`).

**From the twohg-guide skill (2026-09-27)**

- **Phase drops the player behind edicts** (found 2026-10-09, phase v0.104.0;
  report upstream, Dan posts). Each is read with a workaround that retires itself:
  a chained "…, then sacrifices" loses its subject (Undercity Plague, Priest of
  Forgotten Gods, Din of the Fireherd's land half, Nicol Bolas, Planeswalker's −9),
  and Davriel, Soul Broker's +1 hangs "they sacrifice an attacking creature" beside
  its delayed trigger, not in it (`test_chained_sacrifice_actor_dropped_canary`);
  "each opponent [who …] sacrifices" parses with no player at all (Papalymo
  Totolymo, Variable Solutions — ledger row `opponent_sacrifice_actor_dropped`).
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

**From the 2026-09-17 architecture review (worth exploring, not started)**

- Speculative: `playtest.py`'s mode functions; copies of the Scryfall client policy.

**Known lane recall gaps (surfaced by ADR-0051; a lane fix repairs every consumer)**

- Vibranium-mana token makers are suspected not to count as ramp, but no card was
  found to test.

**Discovery ranking:** see ADR-0043's terminal-state amendment for the unclaimed
headroom and parked items.

## Settled: don't re-suggest

- **A spell's casting-cost discard is a discard outlet** (Dan, 2026-10-10). The
  optional keyword costs count: escalate (Collective Brutality, CR 702.120a),
  buyback (Forbid, Demonic Collusion, CR 702.27a), flashback (Conflagrate, Twinned
  Vision, CR 702.34a), as Sabin's blitz does (CR 702.152a). Jump-start (CR
  702.133a) and retrace (CR 702.81a) count too; phase leaves their discard
  untyped, so `discard_outlet` reads them by keyword name behind a
  `retirement_canary`. A mandatory additional-cost discard counts as well
  (Tormenting Voice, Thrill of Possibility, CR 601.2f): you choose the card and
  when to cast. So does a discard that is one choice of an either/or cost (Bitter
  Triumph, Bone Shards, Lightning Axe: "discard a card or pay …"), since you may
  always choose it. `discard_outlet` reads each off the spell's merged `unit.costs`.
- **A random discard isn't a discard outlet, but it still makes discards** (Dan,
  2026-10-10). It can't be aimed (CR 701.9b; Flowstone Flood's buyback, Goblin
  Lore, Amok), so `discard_outlet` skips it in every arm, the kept text mirror
  included (`crosswalk.discard_is_random`). `discard_makers` (loot and rummage)
  keeps it, because a "whenever you discard" payoff (Drake Haven) fires whichever
  card goes (Burning Inquiry). A chosen opponent's discard is not yours either
  (Fervent Mastery, `lanes._shared._choose_opponent_bound_discard`).
- **Upkeep-payment discards aren't discard outlets** (Dan, 2026-10-09): echo's and
  cumulative upkeep's discard (Deepcavern Imp, Rakdos Headliner, Vexing Sphinx) is
  a forced payment to keep the permanent, not a discard you make on demand (CR
  702.30a, 702.24a); `core._UPKEEP_PAYMENT_KEYWORDS` reads only their life costs.

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
