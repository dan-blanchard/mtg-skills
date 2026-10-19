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
- **What the polymorph tune and the 25-precon audit still get wrong** (third
  pass, 2026-10-18 — `docs/plans/precon-audit-2026-10-18.md` has the method,
  the three before / after tables and the per-precon reads; the first two
  passes' fixes are listed there). Fixed in the third pass: a quality read
  inside a lane is "a feeder nobody plays" (measured, below); Spine fills
  rank by play-rate within a mana-value band; player-only damage is not
  `interaction`; Bello's Animation and Yuma's Deserts have lanes
  (`animate_makers|you|<Type>`, `land_type_matters|you|<Type>`); pillowfort
  and fogs are not `superfriends_matters`; a typed token replacement or
  sacrifice trigger carries its token kind (Xorn is `treasure_matters`,
  Academy Manufactor three kinds, Fisher's Talent `tokens_matter|you|Fish`);
  an artifact-TOKEN maker is a maker, never `artifacts_matter`; carers respect
  scope where the specs split it ("Opponents' graveyards" 43 → 4 under
  Teval); two avenues with one carer set are one theme (Polymorph fodder
  absorbs Token generators); an emerging theme needs two carers in
  proportion; the primary lane is a held lane deep enough to show; three pair
  rows for the Enchantment / Artifact / Planeswalker cheat subjects; the CR
  2026-09-25 subtype lists (Heartwood); Syr Konrad's folded zone-change
  trigger reads as `dies` for a dies doubler; a card that merely has an
  activated ability is a payoff target of "Activated-ability engine", not a
  builder (its untap engines are — Abzan Armor read that lane as its main
  over a 42-deep toughness lane; the Jace phantom of the polymorph entry's
  (d) is gone with it). Fixed in the seventh pass (2026-10-19): the upgrade
  slots — an off-lane card past rank 3000 and the deep lane's least-played
  half (never a Granter), traded by a last-ranked `upgrade` issue for a
  better-played card at no higher mana-value band doing the same job (223
  swaps, 104 cuts and 29 adds matching a guide, from 85 / 44 / 8); every theme
  add is the most-played candidate that fits; an Equipment's, Aura's or
  target's shrink and damage to each player are not board wipes; the main
  theme no longer changes with the string-hash seed. Left:
  (a) **Inside a lane, the cut read is "a feeder nobody plays" — don't
  re-suggest a function read.** Measured 2026-10-18 on the 25 precons' main
  lanes (906 lane cards, 222 guide cuts, base rate 0.245): no function
  feature moved the rate — one-shot vs repeatable 0.19, body for its cost
  0.27-0.32, in-deck synergy depth (`rank_candidates` over the deck's own
  cards) flat 0.22-0.25 across quartiles, lanes touched 0.14-0.28. Play-rate
  does (least-played quarter 0.35), and "a member that does not itself care
  about the lane" more so (0.32 vs carers 0.20; rank-bottom-quarter feeders
  0.46; a feeder with no template role past rank 8000: 0.67, n=24). The
  `lane_upgrade` tier now orders feeders before carers, then least played
  (top-five precision 0.48; costlier-first within the half was 0.30). The
  guides' stated reasons (one-shot, delirium type, curve) are not what their
  cuts share, and the same holds for the flip-quality read the polymorph tune
  wanted. Script: `docs/plans/precon-audit/lane_quality.py` (rerun recipe in
  `docs/plans/precon-audit-2026-10-18.md`).
  (b) **Lane leftovers.** (Bello's floor is carried since the fourth pass:
  `animate_makers|you|Artifact>=4`, `Serve.types_cmc_min`; the `animate_artifact`
  regex lane is retired for `animate_makers` — 24 cards lost the old key with
  no replacement, by design: 19 Vehicles and 2 artifacts that animate only
  themselves, 2 copy effects (Saheeli, Sublime Artificer; True Polymorph).)
  (Alacrian Armory, Hidden Guerrillas and Animate Artifact are bridged by field
  corrections since 2026-10-19 — see the phase-gap list below.)
  (`clue_matters` on bare investigate doers and the enchantment-token makers'
  `enchantments_matter` are fixed in the fourth pass: a `<x>_matters` is a
  payoff shape — a count, a grant, a watched subject, a sacrifice you pay —
  never a maker; `clue_matters` 165 → 31, `food_matters` 53 → 69. Three Clue
  cards now carry no Clue key at all, maker-lane gaps in `counters_voltron.py`:
  Officious Interrogation (phase parks "investigate X times" in an
  Unimplemented where-X residue), Curious Inquiry (an Aura granting an
  investigate trigger — `_resource_token_makers` does not walk granted
  bodies), In Too Deep.) The superfriends synth arm still fires on protective "creature
  or planeswalker you control" cards (Angelic Intervention, Kaya's Ghostform,
  Fey Steed); a general veto would drop Spark Double and Lae'zel. (The eight
  protective cards phase types no deterrent for are bridged since 2026-10-19 —
  the phase-gap list below.) The
  Animation subject types are spelled twice (`signal_specs/core._ANIMATED_TYPES`
  and the lane's `_ANIMATE_SUBJECT_TYPES`): the spec layer and the lane layer
  do not import each other. A
  Clue/Treasure-maker commander (Sophina, Goldspan Dragon) no longer opens an
  Artifacts avenue from its own text — it opens its typed lane, and the
  Artifacts serve still counts its tokens as depth. An enchantment-token
  maker (a Role maker) still emits `enchantments_matter`, the same
  doer-under-payoff shape the artifact side just lost.
  (c) **Gaps behind the interaction role** (the phase ones: report upstream,
  Dan posts). With `direct_damage` out of the `removal` preset and the
  `removal` lane firing on burn that can reach a permanent (+810 cards; the
  role lost 592 player-only punishers and gained 26 real removals), what the
  role now misses: mass planeswalker damage — "each opponent and each
  planeswalker they control" (Cavalier of Flame, Kumano Faces Kakkazan,
  Omnath, Locus of Creation) — a `mass_removal` lane gap; sweeps nested in a
  coin flip, a granted ability or a dies trigger (Winter Sky, Noxious Field,
  Volatile Rig), the same lane; real removal whose creature half phase drops
  — Mob Verdict, Chandra's Flame Wave, Path of Mettle ("each creature"),
  Cragganwick Cremator ("player or planeswalker"), Unstable Footing (its
  target), Ian the Reckless ("you and any target" recovered only as a
  residue); Flames of the Blood Hand, Insult // Injury, Kaboom!, Tetsuo parse
  no damage at all (their `direct_damage` is a ledgered bridge). One false
  positive: Monsoon's "tap all Islands" filter reads as a permanent target.
  (d) **Text-mirror leftovers behind the payoff lanes.** The three `_matters`
  text mirrors (artifacts / enchantments / the cast arm) run over oracle
  clauses minus a string match against an animating static's description
  (`board_and_ramp._non_animation_clauses`) because nothing aligns a clause
  with the unit phase typed it as; the deeper shape is to run the mirrors over
  each non-claimed unit's description plus the residue text. Rise and Shine
  still fires `artifacts_matter|you|` through another arm ("put four +1/+1
  counters on each artifact that became a creature this way"). (The pair
  rows read candidates without membership idents since the fourth pass, so a
  card with both a cast and an enters payoff — Tuvasa the Sunlit, Sai — fires
  the typed-cheat rows and Sol Ring / Pacifism no longer score as payoffs.)
  (e) **The most-played card of a job recurs** (seventh pass): Skullclamp is
  an add in 12 of 25 precons (a guide add in 3), Swiftfoot Boots in 9, Frantic
  Search in 5 — and looting counts as card draw (connive is written in as card
  advantage), so Faithless Looting and Frantic Search upgrade a draw spell.
  Nine precons get no guide-matching add at all. A "main theme" upgrade can
  land on a generic card the main avenue's page holds (Swiftfoot Boots in
  Mardu Surge, Lightning Greaves in Tinker Time).
  (f) A targeted static toughness shrink (Nameless Inversion's "+3/-3") is no
  `removal` key, so it fills no interaction slot.
  (g) The guide cuts the tuner protects are still 124 — lane carers and doers
  the guides trim, which the upgrade issue reaches only through the deep
  lane's least-played half.
  (h) The board-wipe role reads two substrates — the compat projection's mass
  marker (`_ir_board_wipe`, whose destroy / damage / bounce arm duplicates
  `mass_removal`) and a roles-local typed walk for static population shrinks
  (`_static_board_shrink`, beside `debuff_makers`' static arm) — where it
  should come off the signal path: `mass_removal` plus a population-shrink
  arm, retiring `_ir_board_wipe`. The role and the `board-wipe` preset the
  tuner sources by disagree on one-sided shrinks (the role counts Elesh Norn's
  -2/-2; the preset excludes Massacre Wurm by adjudication), and no test pins
  their agreement as `test_the_preset_and_the_role_agree_on_every_covered_card`
  does for ramp. `mass_removal`'s attachment veto (`_DEBUFF_SINGLE_AURA_PREDS`)
  has no `EquippedBy`; check with /rules-lawyer whether `AttachedToRecipient` /
  `HasAnyAttachmentOf` name one object before folding it into
  `crosswalk.ATTACHED_OBJECT_PREDICATES`.
  (i) `cut_candidates` / `size_cuts` take four focus-result fields one by one
  (`viable`, `commander_cards`, `upgrade_cards`, `lane_upgrade_cards`) — one
  focus slice would do.

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

- **Every held serve spec is converted (2026-10-19); what the lanes still
  miss** (the per-spec censuses are in `docs/plans/serve-idents-and-avenue-support.md`
  §2; the 41 holds of the serve-ident pass and the six of the fourth pass are
  all `serve_idents` now, each with its remainder classified). Phase gaps,
  each bridged 2026-10-19 by the supplemental parser with a `retirement_canary`
  or a self-retiring ledger row (tests/mtg-utils/test_phase_gaps_*.py; report
  upstream all the same, Dan posts): where-X keyword heads (Mask of the
  Schemer's connive X, Thromok's devour X, Fall of Cair Andros's amass X,
  Officious Interrogation's investigate X — the `_where_x_head` recovery,
  scoped to connive / amass / investigate; opening it to every allowlisted verb
  would recover ~40 more where-X clauses across many lanes, a separate
  measured promotion); energy residues (`gain_energy` / `energy_payment`
  tokens: Overclocked Electromancer, Robobrain War Mind, The Motherlode,
  Reiterating Bolt, Salvation Colossus, Izzet Generatorium's condition);
  foretell residues (Ethereal Valkyrie, Karfell Harbinger, Ranar); Osteomancer
  Adept's forage cost (a ledger row); Jetmir's Fixer (a lane arm over the
  recovered counter); the nine "all damage dealt to X is dealt to Y instead"
  replacements (`damage_redirect` token, Treacherous Link and Megatron kept
  out as opponent-side); Prairie Dog and Zabaz (`counter_bonus` token);
  Death's Approach and kin (`debuff` static token — the Sewer Plague ledger row
  retired by it); Attempted Murder; Ian the Reckless and Volcano Hellion ("to
  you and …" burn); Stunning Shot and three more fresh tap targets; ledger rows
  for Cragganwick Cremator / Flames of the Blood Hand / Kaboom! / Unstable
  Footing (a dropped planeswalker target), Insult // Injury, Tetsuo, Mob
  Verdict / Chandra's Flame Wave / Path of Mettle (the creature half), Decimator
  Beetle / Zealous Persecution / Foul Renewal (a dropped shrink), Heir of the
  Ancient Fang / Lethal Exploit / Lethal Throwdown / Lion Umbra (modified),
  Elspeth Resplendent / Undercover Operative (shield counters), Nicanzil,
  Dream Devourer, The Fourth Doctor, You Find a Cursed Idol (Unknown or
  dropped trigger modes); field corrections for the `SelfRef` untap locks
  (Mesmerizing Benthid, Scion of Stygia, Wall of Stolen Identity, Tsabo's Web,
  Code of Constraint), the anaphoric "it gets -N/-0" pumps (the two Jaces,
  Tamiyo, Blood Lust, Six-Sided Die), "that player controls" taps (Delirium,
  Yosei, Mana Web — and 22 self-tap cards such as Jaddi Lifestrider left
  `tapper_engine`), the Hidden / Opal / Veiled / Lurking self-animation cycle,
  Alacrian Armory and Animate Artifact, Athreos's exile, the graveyard owner
  (Skullsnatcher, Zombie Cannibal, Grime Gorger — opponents; Savior of
  Ollenbock — any), `CounterPlayerAddedAll`'s energy kind, Venser's Diffusion;
  the eight protective superfriends cards (a parked-recipient check); and the
  repo-side reads: granted afterlife / mobilize token makers, Worldwalker
  Helm's replacement Map, Dodecapod's enters-with counters, Hamza / Starport
  Security's countered-creature cost reductions, Brimaz's Phyrexian death,
  `walk_effect_chain` descending a coin flip's WIN branch only (+23 idents;
  the lose branch — Volatile Rig's sweep — is deliberately not walked, since
  both branches would serve drawbacks: Scoria Wurm's self-bounce). Still open,
  nothing to read: Commence the Endgame (the amass is folded into the Draw
  node's description with no residue; the keyword-array fallback serves it),
  Izzet Generatorium's energy replacement (a payoff on makers, left), Aether
  Refinery's doubler typed as a CreateToken replacement (no consumer reads it
  wrong), Rain of Riches (already served), the aftermath faces Rags // Riches,
  Reduce // Rubble, Indulge // Excess (phase emits no record for the second
  face — a canary waits on it), Pradesh Gypsies (no record at all), Tomik's
  "affinity for planeswalkers" (the keyword's parameter is not exposed), the
  Attraction Unknown modes (already served by the sweep row); Orcish Captain's
  "it gets -0/-2" (an anaphoric "it" inside an ACTIVATED ability's coin-flip
  branch, stamped `SelfRef`; the `anaphoric_pump` arm covers delayed triggers
  and a spell's own chain, not activated abilities, since a Dragonrage-type
  grant really does mean the card) fires `self_pump|you|`; Desperate Gambit's "choose a source you control" loses
  "you control" (the chooser is `TargetOnly{target: Any}`), so its losing
  branch's prevention reads as `damage_prevention` — a dropped-controller
  misstamp, and once a field correction restores it `is_own_drawback` needs a
  `PreventDamage`-on-your-source arm.
  Lane gaps still open: `creature_recursion` has no destination subject (62
  reanimation spells sit outside damage_for_each; creature_etb carries a
  reanimation extra instead); `cost_reduction` has no spell-type subject (21
  creature-spell reducers); the edict lane misses Incriminate, Malik,
  Gluttonous Hellkite, Killing Wave, Tragic Arrogance and granted edicts;
  keyword token-copy makers
  (embalm, eternalize, myriad, squad, encore) are not read; granted flanking;
  back-reference counter targets scoped you (Retribution, Obelisk Spider);
  partial prevention, granted absorb, Blinding Powder, Torrent of Lava
  (`damage_prevention`); `discard_outlet`
  misses "cast from your graveyard by discarding" (Alien Symbiosis, Demonic
  Embrace, Rona); the lifegain pair lost its 96 Food makers — `lifegain_makers`
  does not read the gain inside a Food token (Bake into a Pie, Bill the Pony);
  "whenever you proliferate" payoffs and granted / X proliferate have no ident
  (Scheming Aspirant, Venser, Tam, Ichormoon Gauntlet); the own-graveyard
  remainder (collect-evidence and forage costs, descend payoffs, the Empower
  Jace token's surveil, granted delve / soulshift X, a craft cost). Lane false
  positives still open: a token another player
  creates serves as a `token_maker|you|*` (Varchild, Goblin Spymaster,
  Skyclave Apparition, Genesis Chamber, March of Souls …); "tap creatures you
  control" cards serve `tapper_engine` (Jaddi Lifestrider — inseparable from
  the `controller: You` misstamp above); ~9 "when an opponent causes you to
  discard this" cards fire `discard_matters` and Balance / Restore Balance
  `discard_outlet`; Oft-Nabbed Goat and Sentinel of Lost Lore fire
  `gain_control`; An Offer You Can't Refuse fires `treasure_makers|you`;
  Investigator's Journal still fires `proliferate_matters` and
  The Book of Exalted Deeds `stax_taxes|opponents`.
  Ranking: `ranking._synergy_score` gives clause clusters only to regex-matched
  hits, so every regex → ident conversion thins clause breadth (Empty the
  Warrens' token clause 8 → 6 lanes); attributing an ident hit to the clause
  its signal came from belongs in the ranking module.

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
