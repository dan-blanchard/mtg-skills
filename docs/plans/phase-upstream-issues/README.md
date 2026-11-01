# phase-rs upstream issues (drafted against v0.118.0)

Ready-to-post issue bodies generated from `docs/plans/phase-upstream-reports.md` and re-verified against phase v0.118.0's own card-data (`card-data-v0.118.0.json`). Nothing here has been posted. Each file: title as the `#` heading, the phase tag, the cards with oracle text from the local MTGJSON bulk, the trimmed face-record fragment phase emits (null/false/empty fields and the noise keys `kind`, `trigger_zones`, `damage_kind`, `sub_link`, `target_choice_timing` dropped; `…` marks an elided sub-tree), the expected structure, and why it matters.

Numbering: `NN` is the report section. Sections 12, 15, 16 and 24 hold several unrelated shapes, so they are split into letter-suffixed files (12a-d, 15a-i, 16a-b, 24a-h). Cards the report names only as "also" / "ledger" / "backlog, not re-checked" are mentioned in an issue's text as "the same shape appears on these cards, not re-quoted here"; Appendix A (ledger rows) and the "Not drafted" list are out of scope here.

## Issues

| File | Title | Cards | Report section |
|---|---|---|---|
| 01-disa-graveyard-arrival-unknown-mode.md | Graveyard arrival "from anywhere other than the battlefield" is an `Unknown` trigger mode | Disa the Restless (control: Countryside Crusher) | 1 |
| 02-unknown-trigger-modes.md | Trigger events phase can't type are parked as `mode.Unknown` | Eye of Singularity, Ranar (fragments); Nicanzil, Dream Devourer, Sacred Ground, Thrasher Brute, The Fourth Doctor, Hero of Bretagard (listed) | 2 |
| 03-tracked-set-unbound.md | Tracked set lost or unbound | Cleansing Meditation, Skyclave Shade, Ichor Aberration | 3 |
| 04-unless-pays.md | "Unless [player] pays" on a placeholder or parked | Rhystic Tutor, Rune Snag (control: Geistlight Snare) | 4 |
| 05-reveal-only-search.md | Reveal-only search typed as a move to hand | Grim Reminder, Chaos Mutation | 5 |
| 06-quoted-granted-abilities.md | Quoted/granted abilities dropped, parked or mistyped | Frodo Sauron's Bane, Nicol Bolas Dragon-God, Forgeborn Phoenix | 6 |
| 07-graveyard-returns-parked.md | Returns from the graveyard parked or lost | Custodi Soulcaller, Venerable Warsinger, All Hallow's Eve, Necromancy, Can't Stay Away | 7 |
| 08-where-x-binding.md | `where X is ...` residue swallows the effect | Mask of the Schemer, Officious Interrogation, Thromok | 8 |
| 09-unparsed-quantity.md | "equal to ..." clauses parked as `unparsed_quantity` | Within Range, Soulblast, Overclocked Electromancer, Tar Fiend, Notorious Throng | 9 |
| 10-activate-only-if-residue.md | "Activate only if" parked as a residue sub-ability | Boxing Ring | 10 |
| 11-damage-prevention-redirection.md | Prevention/redirection parked (regression since v0.94.0) | Treacherous Link, Prairie Dog, Light of Sanction (fragments); Well-Laid Plans, Ironscale Hydra, Camel, Forcefield (listed) | 11 |
| 12a-that-player-controls-stamped-you.md | "that player controls" stamped `controller: You` | Delirium, Mana Web, Devastating Mastery, Teferi Temporal Pilgrim | 12a |
| 12b-edict-actor-dropped.md | Chained edict's actor dropped | Undercity Plague, Priest of Forgotten Gods, Variable Solutions | 12b |
| 12c-payer-chooser-stamped-controller.md | Payer/chooser stamped `Controller` | Fraying Line, Worms of the Earth | 12c |
| 12d-graveyard-exile-no-owner.md | Graveyard exile with no owner | Rooting Moloch, Grime Gorger, Skullsnatcher | 12d |
| 13-static-affected-selfref.md | `affected` stamped `SelfRef`/`TriggeringSource` for another object | Canopy Cover, Hidden Guerrillas, Warmonger's Chariot (fragments); Mesmerizing Benthid, Tsabo's Web, Alacrian Armory, Animate Artifact (listed) | 13 |
| 14-anaphora-misbound.md | Anaphora bound to the wrong object | Bestial Fury, Blood Lust, Stunning Shot (fragments); Six-Sided Die, Ojutai Exemplars, Fatespinner (listed) | 14 |
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
| 24b-damage-to-each-creature-blocking-it.md | "each creature blocking it" typed as every creature | Battle-Scarred Goblin, Fire Juggler | 24 |
| 24c-orcish-captain-flip-outcome-it.md | Flip outcome "it" stamped `SelfRef` | Orcish Captain | 24 |
| 24d-split-coin-flip.md | One flip typed as two | Desperate Gambit, Goblin Kites, Fickle Efreet | 24 |
| 24e-prevention-residues.md | Prevention clauses parked | Dark Sphere, Torrent of Lava, Blinding Powder | 24 |
| 24f-craft-with-two-that-share-a-card-type.md | Craft with a shared-type material parked | Eye of Ojer Taq | 24 |
| 24g-loses-defender-trigger.md | "loses defender and gains trample" parked | Guardian of the Ages | 24 |
| 24h-vibranium-token-no-mana-ability.md | Vibranium token has no mana ability | Shuri's Fabricator (and four other makers) | 24 |

## Not reproduced at v0.118.0

- **15g (Crashing Tide, Graveyard Shift, Mutual Destruction, Take for a Ride).** Phase types the conditional own-spell flash as a record-level `casting_options: [{"kind": "AsThoughHadFlash", "condition": {...}}]` (Crashing Tide: Merfolk you control `>= 1`; Graveyard Shift: distinct mana values in your graveyard `>= 5`; Mutual Destruction: a permanent with Flash `>= 1`; Take for a Ride: crimes committed `>= 1`). Supernatural Rescue's line is a `Continuous` static `AddKeyword Flash`. Not a phase defect. *Corrects report section 15, bullet "A spell's conditional flash dropped" (delete it; the "Also" list there is wrong too).*
- **Necromancy's flash.** The record has `casting_options: [{"kind": "AsThoughHadFlash"}]`, and the ETB sacrifice trigger carries a `CastTimingPermission AsThoughHadFlash` condition. The flash permission is typed; the main ability is still parked (issue 07). *Corrects report section 23, first sentence ("leaves no flash permission") and the Necromancy half of its Expected; section 7's Necromancy text stands.*
- **Liliana's Talent.** Typed: a `Continuous` static on `Typed[Planeswalker] + EnchantedBy` with a `GrantAbility` whose cost is `Loyalty -8` and effect `ChangeZoneAll` Graveyard->Battlefield for creatures (`enters_under: You`). *Corrects report section 6 (first example) and the "Also" mention of it in section 7.*
- **Torpid Moloch.** Typed as `GenericEffect` / `RemoveKeyword Defender` until end of turn (Guardian of the Ages is still parked: issue 24g). *Corrects report section 24, the Guardian of the Ages / Torpid Moloch bullet.*
- **Skyclave Apparition.** The `Token` has `owner: Controller` but also `player_scope: {"type": "OwnersOfCardsExiledBySource"}`, which types the exiled card's owner as the maker. The gap is in our read. *Corrects report section 24, the Skyclave Apparition bullet (move it to "Not a phase defect").*

## Findings beyond the report

- Disa the Restless's second trigger ("create a Tarmogoyf token") is itself `Unimplemented unparsed_verb_arguments` (noted in issue 01).
- Section 11's regression claim is now verified: Light of Sanction is a `DamageDone` replacement with `shield_kind: {Prevention: {amount: All}}` at v0.86.0 and a `replacement_structure` residue at v0.94.0.
- Report section 16 says Dusk's "Aftermath keyword is absent"; more precisely, `Aftermath` has no keyword in the card-data and Dawn has no face record. Dusk // Dawn has a phase record for the `Dusk` face only; none for `Dawn` (issue 16a).
- Counts in issue 21 are over the whole card-data file (3,116 records with any `Unimplemented`; 298 with an `Unknown` trigger mode), not the report's commander-legal subset (1,971 / 172).
