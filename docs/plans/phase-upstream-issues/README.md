# phase-rs upstream issues (verified against v0.131.0)

Ready-to-post issue bodies generated from `docs/plans/phase-upstream-reports.md`, drafted against phase v0.118.0 and re-verified card by card against phase v0.131.0's own card-data (`card-data-v0.131.0.json`) after the pin bump of 2026-11-24. Nothing here has been posted. Each file: title as the `#` heading, the phase tag, the cards with oracle text from the local MTGJSON bulk, the trimmed face-record fragment phase emits (null/false/empty fields and the noise keys `kind`, `trigger_zones`, `damage_kind`, `sub_link`, `target_choice_timing` dropped; `…` marks an elided sub-tree), the expected structure, and why it matters. Where v0.131.0 added `metadata.confirmed_misparse` to a record, the file says so.

Numbering: `NN` is the report section; issues found after the report (25 on: the Arena game-log comparison, the graveyard-mirror follow-up, and 27 to 36 from the v0.131.0 pin bump) take the next number, and the table's last column names their source. Sections 12, 15, 16 and 24 hold several unrelated shapes, so they are split into letter-suffixed files (12a-d, 15a-i, 16a-b, 24a-j). Files are never renumbered: a number whose issue phase fixed is retired, not reused. Cards the report names only as "also" / "ledger" / "backlog, not re-checked" are mentioned in an issue's text as "the same shape appears on these cards, not re-quoted here"; Appendix A (ledger rows) and the "Not drafted" list are out of scope here.

## Posting order

Ranked 2026-11-25 by the workaround code each draft retires on our side when phase fixes it: bridge-ledger rows, `retirement_canary` tests, and correction-layer rows or recovery tokens (`ranking.md` has every draft's count, what each attribution rests on, and which were verified in the code). "Strict" counts only a workaround whose card or exact shape the draft names. Where two drafts were close, the one phase does not already flag `confirmed_misparse` goes first. Drafts in parentheses are the same upstream fix: post them together.

| Order | Draft | Strict | What we delete when it is fixed |
|---|---|---|---|
| 1 | 11 (+ 24e) prevention and redirection parked | 6 | the `damage_redirect` and `counter_bonus` recovery tokens and their two canaries; ledger rows `prevention_shield_parse_failure`, `gated_prevention_parked`, `granted_unattach_prevention_parse_failure`; part of `reads.PARKED_PREVENTION_RESIDUES` |
| 2 | 02 (+ 30, 24i) trigger events parked as `mode.Unknown` | 6 | six ledger rows (Hero of Bretagard / Ranar, Nicanzil, Dream Devourer, The Fourth Doctor, Sacred Ground, Thrasher Brute); if phase types Unknown modes generally, also the `misparsed_shapes` Akiri row and its canary |
| 3 | 13 `affected` stamped `SelfRef` | 7 | `overlay_corrections`' can't-untap, self-animation and animated-object arms and their three canaries; ledger row `equipped_defender_attack_misread`. Lead with Hidden Guerrillas and Warmonger's Chariot: phase already flags the other four records |
| 4 | 08 (+ 07) `where X` bindings and the returns they swallow | 4 + 3 | the where-X recovery of connive / amass / investigate, the `devour` token, four cases of the resource canary; 07's three reanimation ledger rows |
| 5 | 15h a clause swallowed beside a typed effect | 4 | ledger rows for the ice-counter defender, Wakanda Forever!'s indestructible counter, and the two cloak rows |
| 6 | 14 (+ 24c, 28) anaphora bound to the wrong object | 5 | `overlay_corrections`' anaphoric-pump and fresh-tap-target arms, the Fatespinner skip, and their three canaries; 24c's flip `SelfRef` arm; 28's spell-`SelfRef` guards |
| 7 | 16a keyworded self-recursion, **split in two first** | 2 | the keyword half: `theme_presets.SELF_RECURRING_KEYWORD_GAPS` and its canary, `energy_unearth_parked`. The aftermath half ("Dawn has no face record") is a different fix worth its own issue: seven `missing_face` ledger rows and their canary |
| 8 | 15c (+ 15a, 15b, 15d) a keyword dropped from a typed body | 4 + 2 | everything in `dropped_keywords` but the Role arm, `recovery._partly_read_grant`, five canaries. 15b retires nothing without 15a |
| 9 | 15f a Role token has no ability | 4 | `dropped_keywords._role_grants` and its canary; ledger rows `role_attach_parked`, `monster_role_trample_parked` |
| 10 | 25 (+ 26) "exile it instead" of the graveyard | 3 + 2 | the `misparsed_shapes` exile-instead row and its two canaries (23 cards); 26's `exile_instead` token and its canary |

Next: 09 with 36 (they share `recovery._peeled_subject`), 15e, 19, 18 with 32 (the `self_discount` token), 03 with 35 and 27 (the "this way" tracked set), then 12a, 12c, 12d and 17 (two strict each), and 12b with 20 (both Variable Solutions).

Pure reports, which retire nothing on our side: 16b, 20, 21, 23, 24f, 24h, 24i, 27, 29, 30, 34 (and 15b alone).

## Issues

| File | Title | Cards | Report section |
|---|---|---|---|
| 02-unknown-trigger-modes.md | Trigger events phase can't type are parked as `mode.Unknown` | Eye of Singularity, Ranar (fragments); Nicanzil, Dream Devourer, Sacred Ground, Thrasher Brute, The Fourth Doctor, Hero of Bretagard (listed) | 2 |
| 03-tracked-set-unbound.md | Tracked set lost or unbound | Cleansing Meditation (now parked), Skyclave Shade, Ichor Aberration | 3 |
| 04-unless-pays.md | "Unless any player pays" on a placeholder | Rhystic Tutor (control: Geistlight Snare) | 4 |
| 05-reveal-only-search.md | Reveal-only search typed as a move to hand | Grim Reminder, Chaos Mutation | 5 |
| 06-quoted-granted-abilities.md | Quoted/granted abilities dropped, parked or mistyped | Frodo Sauron's Bane, Nicol Bolas Dragon-God, Forgeborn Phoenix | 6 |
| 07-graveyard-returns-parked.md | Returns from the graveyard parked or lost | Custodi Soulcaller, Venerable Warsinger, All Hallow's Eve, Necromancy, Can't Stay Away | 7 |
| 08-where-x-binding.md | `where X is ...` residue swallows the effect | Mask of the Schemer, Officious Interrogation, Thromok | 8 |
| 09-unparsed-quantity.md | "equal to ..." clauses parked as `unparsed_quantity` | Within Range, Soulblast, Overclocked Electromancer, Tar Fiend, Notorious Throng | 9 |
| 11-damage-prevention-redirection.md | Prevention/redirection parked | Treacherous Link, Prairie Dog (fragments); Well-Laid Plans, Camel, Forcefield (listed); control: Light of Sanction | 11 |
| 12a-that-player-controls-stamped-you.md | "that player controls" stamped `controller: You` | Delirium, Mana Web, Devastating Mastery; Teferi Temporal Pilgrim (now parked) | 12a |
| 12b-edict-actor-dropped.md | "Each opponent sacrifices" has no player | Variable Solutions | 12b |
| 12c-payer-chooser-stamped-controller.md | Payer/chooser stamped `Controller` | Fraying Line, Worms of the Earth | 12c |
| 12d-graveyard-exile-no-owner.md | Graveyard exile with no owner | Rooting Moloch, Grime Gorger, Skullsnatcher | 12d |
| 13-static-affected-selfref.md | `affected` stamped `SelfRef`/`TriggeringSource` for another object | Hidden Guerrillas, Warmonger's Chariot (fragments); Mesmerizing Benthid, Tsabo's Web, Alacrian Armory, Animate Artifact (listed) | 13 |
| 14-anaphora-misbound.md | Anaphora bound to the wrong object | Bestial Fury, Blood Lust, Stunning Shot (fragments); Six-Sided Die, Fatespinner (listed) | 14 |
| 15a-grant-dropped-from-static-modifications.md | Keyword grant left out of modifications | Chariot of the Sun, Valkyrie's Call | 15 |
| 15b-unrecognized-condition-swallows-grants.md | Clause chain collapses into an `Unrecognized` condition | Tek | 15 |
| 15c-copy-exception-keyword-dropped.md | Copy exception keyword dropped / read as subtype | Irenicus's Vile Duplication, Will of the Temur | 15 |
| 15d-pump-grant-dropped.md | Pump's keyword grant dropped | Tromp the Domains | 15 |
| 15e-grant-or-token-parked-as-unimplemented.md | Grant / keyword counter / token parked | Reaper of Night, Inventive Wingsmith, Genku Future Shaper | 15 |
| 15f-role-token-ability-missing.md | Role token has no ability | Monstrous Rage | 15 |
| 15h-grant-swallowed-beside-typed-effect.md | Clause swallowed beside a typed effect | Woolly Razorback, Wakanda Forever!, Hide in Plain Sight | 15 |
| 15i-keyword-lost-from-token-or-zone-owner-dropped.md | Token keyword, suspect, zone owner dropped | Furygale Flocking, Case of the Stashed Skeleton, Soovril | 15 |
| 16a-keyworded-self-recursion-dropped.md | Recover/unearth/mayhem/aftermath not typed | Garza's Assassin, Salvation Colossus, Oscorp Industries, Dusk // Dawn | 16 |
| 16b-this-card-from-graveyard-typed-as-any-card.md | "this card" from graveyard typed as any card / wrong zone | Sproutback Trudge, Syrix, Worldheart Phoenix, Nether Shadow | 16 |
| 17-blocking-restriction-and-spell-target-constraint.md | Typeless blocker filter; "with one or more targets" dropped | Glorfindel Dauntless Rescuer, Wyll's Reversal | 17 |
| 18-second-sentences-and-reflexive-effects.md | Second sentences, restrictions, reflexive effects parked | Geistlight Snare, Blackmail, Mana Clash, Even the Odds, Turtles Forever, Ludevic | 18 |
| 19-condition-or-qualifier-dropped.md | Condition/qualifier dropped | Phyrexian Unlife, Eye of Singularity, Herald of Vengeance | 19 |
| 20-seek-has-no-player.md | `Seek` has no player | Variable Solutions | 20 |
| 21-unimplemented-residue-census.md | Census of `Unimplemented` classes (by class) | exemplars per class | 21 |
| 22-mana-spending-restrictions-and-foretell.md | Spend-only restrictions and foretell clauses parked | Karfell Harbinger, Ethereal Valkyrie | 22 |
| 23-as-though-flash-permission-typed-as-cast.md | "as though it had flash" permission as one-shot cast / parked | Rootwater Shaman, Aluren | 23 |
| 24a-malik-secret-choice-edict.md | Secret simultaneous choice parked | Malik, Grim Manipulator | 24 |
| 24c-orcish-captain-flip-outcome-it.md | Flip outcome "it" stamped `SelfRef` | Orcish Captain | 24 |
| 24d-split-coin-flip.md | One flip typed as two | Desperate Gambit, Goblin Kites, Fickle Efreet | 24 |
| 24e-prevention-residues.md | Prevention clauses parked | Dark Sphere, Torrent of Lava, Blinding Powder | 24 |
| 24f-craft-with-two-that-share-a-card-type.md | Craft with a shared-type material parked | Eye of Ojer Taq | 24 |
| 24g-loses-defender-trigger.md | "loses defender and gains trample" parked | Guardian of the Ages | 24 |
| 24h-vibranium-token-no-mana-ability.md | Vibranium token has no mana ability | Shuri's Fabricator (and four other makers) | 24 |
| 24i-kaust-face-up-combat-damage-unknown-mode.md | Face-up-this-turn combat-damage trigger is an `Unknown` mode | Kaust, Eyes of the Glade | 24 (triage pass) |
| 24j-mirrormind-crown-token-copy-replacement-parked.md | Token-copy replacement parked as `as_long_as_gate` | Mirrormind Crown | 24 (triage pass) |
| 25-countered-spell-exiled-instead-typed-from-graveyard.md | "Exile it instead" of the graveyard typed as a move out of the graveyard | Dissipate (control: Memory Lapse); 20 more listed; the cast-trigger form: Goliath Daydreamer, Gandalf of the Secret Fire | Arena log comparison, 2026-11-09 |
| 26-mana-spend-rider-exile-instead-parked.md | A mana rider exiling the spell it pays for parked as `Unimplemented` | Forger's Foundry (control: Primal Wellspring) | the graveyard-mirror follow-up, 2026-11-09 |
| 27-danse-macabre-non-targeting-return-multi-target.md | Non-targeting "return up to two" carries a `multi_target`; the d20 returns parked | Danse Macabre | v0.131.0 pin bump |
| 28-emergent-sequence-counter-on-selfref.md | "Put a +1/+1 counter on it" bound to the sorcery | Emergent Sequence | v0.131.0 pin bump |
| 29-veiling-oddity-cant-be-blocked-broadcast-parked.md | "creatures can't be blocked this turn" parked as `broadcast_static_mode_live_set` | Veiling Oddity | v0.131.0 pin bump |
| 30-tenuous-truce-attack-trigger-unknown-modes.md | Compound attack trigger split into two `Unknown` modes | Tenuous Truce | v0.131.0 pin bump |
| 31-qualified-cant-be-targeted-parked-as-other.md | "can't be the target of [some] spells" parked as `mode: {Other: text}` | Fiendslayer Paladin, Dense Foliage, Tomik (fragments); 17 more listed; the spell form: Autumn's Veil, Display of Dominance | v0.131.0 pin bump |
| 32-per-count-cost-reduction-parked.md | A cost change "for each [count]" parked as `static_structure` | Battlefield Thaumaturge, Thrasta (fragments); 8 more listed | v0.131.0 pin bump |
| 33-damage-to-creatures-and-players-parked.md | Damage to a player and their creatures in one clause parked | Disorder, Incite Rebellion, Mob Verdict | v0.131.0 pin bump |
| 34-thought-dissector-compound-reveal-until.md | Reveal-until with two stop conditions parked as `compound_reveal_until` | Thought Dissector | v0.131.0 pin bump |
| 35-this-way-set-reference-parked.md | A clause over the cards chosen or moved "this way" parked | Revivify, Raiding Party (fragments); 15 more listed | v0.131.0 pin bump |
| 36-revealed-hand-discard-parked.md | "Reveals their hand and discards all … cards": the discard parked, its player cut | Amnesia, Persecute, Shatter Assumptions (fragments); 12 more listed | v0.131.0 pin bump |

## Fixed at v0.131.0

Deleted, every card fixed: 01 (Disa the Restless), 10 (Boxing Ring), 24b (Battle-Scarred Goblin, Fire Juggler). Trimmed, the fixed cards removed and named in the file: 04 (Rune Snag), 11 (Light of Sanction, Ironscale Hydra), 12b (Undercity Plague, Priest of Forgotten Gods), 13 (Canopy Cover), 14 (Ojutai Exemplars). See `../phase-upstream-reports.md`, "Fixed at v0.131.0".

## Not reproduced at v0.118.0

- **15g (Crashing Tide, Graveyard Shift, Mutual Destruction, Take for a Ride).** Phase types the conditional own-spell flash as a record-level `casting_options: [{"kind": "AsThoughHadFlash", "condition": {...}}]` (Crashing Tide: Merfolk you control `>= 1`; Graveyard Shift: distinct mana values in your graveyard `>= 5`; Mutual Destruction: a permanent with Flash `>= 1`; Take for a Ride: crimes committed `>= 1`). Supernatural Rescue's line is a `Continuous` static `AddKeyword Flash`. Not a phase defect. *Corrects report section 15, bullet "A spell's conditional flash dropped" (delete it; the "Also" list there is wrong too).*
- **Necromancy's flash.** The record has `casting_options: [{"kind": "AsThoughHadFlash"}]`, and the ETB sacrifice trigger carries a `CastTimingPermission AsThoughHadFlash` condition. The flash permission is typed; the main ability is still parked (issue 07). *Corrects report section 23, first sentence ("leaves no flash permission") and the Necromancy half of its Expected; section 7's Necromancy text stands.*
- **Liliana's Talent.** Typed: a `Continuous` static on `Typed[Planeswalker] + EnchantedBy` with a `GrantAbility` whose cost is `Loyalty -8` and effect `ChangeZoneAll` Graveyard->Battlefield for creatures (`enters_under: You`). *Corrects report section 6 (first example) and the "Also" mention of it in section 7.*
- **Torpid Moloch.** Typed as `GenericEffect` / `RemoveKeyword Defender` until end of turn (Guardian of the Ages is still parked: issue 24g). *Corrects report section 24, the Guardian of the Ages / Torpid Moloch bullet.*
- **Skyclave Apparition.** The `Token` has `owner: Controller` but also `player_scope: {"type": "OwnersOfCardsExiledBySource"}`, which types the exiled card's owner as the maker. The gap is in our read. *Corrects report section 24, the Skyclave Apparition bullet (move it to "Not a phase defect").*

## Findings beyond the report

- Disa the Restless's second trigger ("create a Tarmogoyf token") is still `Unimplemented unparsed_verb_arguments` at v0.131.0; issue 01, which noted it, is deleted because its subject (the first trigger) is fixed.
- Section 11's regression is over: Light of Sanction was a `DamageDone` replacement with `shield_kind: {Prevention: {amount: All}}` at v0.86.0, a `replacement_structure` residue at v0.94.0 through v0.118.0, and is typed again at v0.131.0 (issue 11 uses it as the control).
- Report section 16 says Dusk's "Aftermath keyword is absent"; more precisely, `Aftermath` has no keyword in the card-data and Dawn has no face record. Dusk // Dawn has a phase record for the `Dusk` face only; none for `Dawn` (issue 16a; unchanged at v0.131.0).
- Counts in issue 21 are over the whole card-data file (3,073 records with any `Unimplemented`; 299 with an `Unknown` trigger mode), and the commander-legal figures in the issues use each record's own `legalities` (1,742 / 167 at v0.131.0).
- Many v0.131.0 records carry `metadata.confirmed_misparse` (`wrong_player`, `wrong_object`, `dropped_qualifier`, `missing_effect`, …): phase now flags several of the drafted cards itself, and several clauses v0.118.0 typed with a qualifier dropped now fail closed (issues 31 to 35).
