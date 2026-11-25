# phase-rs upstream drafts ranked by the workaround code each would retire

Counted 2026-11-25 at commit `ad9a499f`, phase pin v0.131.0. The posting order drawn from it is in `README.md`. 53 drafts in `docs/plans/phase-upstream-issues/`; 201 rows in `bridge_ledger.BRIDGES`; 87 `retirement_canary` test functions (several parametrized).

Since the count: `mutate_count_team_pump_dropped` (draft 08) and `perpetual_combat_self_pump_parked` (Appendix A1) were retired on 2026-11-25 by `misparsed_shapes`' parked-pump rows, which carry their own canaries. The totals below are from before that.

## How it was counted

- **Ledger rows**: every row id and its pins were dumped from `BRIDGES` itself; each row went to at most one draft. **Canary tests**: all 87 marked test functions were pulled out by AST (name, docstring, parametrize cases) and read; each went to at most one draft (its primary one). **Correction rows**: `misparsed_shapes` rows, `branches.BRANCH_MISREADS` rows, `overlay_corrections` field arms, `dropped_keywords` arms, recovery `ALLOWLIST` tokens with their `clause_grammar` STATIC/REPLACEMENT rows (counted once per token), and named recovery helpers that exist only for one shape. Lane-side constants a canary guards (`NARROWED_PERMANENT_SWEEPS`, `UNBOUND_CAST_TARGET`, ...) are counted through their canary, not twice.
- Not counted anywhere: the 7 `shape_compat` rows (the module says they are renames, not misparses), the generic legacy arms of `field_corrections` (3) and `dropped_clauses` (24), the generic `overlay_corrections` arms (dig_into_play, exile_removal, edict_scope, removal_target_subject, graveyard_zones, blink_returns_to) and the ~38 generic verb tokens of the recovery ALLOWLIST (they shrink with draft 21's census, class by class).
- Flags: **s** = strict (a pinned card / test case is named in the draft, or the row exists only for the draft's named shape); **p** = partial (the row/test also serves cards outside the draft, so it retires only when those are fixed too); **j** = judgement (shape match: the card is not in the draft; mostly from the report's 'Also (ledger)' lists, which the drafts left out by design). 'Total' counts s + p + j; 'Strict' counts s only.
- Card count = cards the draft names, quoted or listed as 'the same shape appears on' (controls excluded). confirmed_misparse = whether the draft says the v0.131.0 record carries `metadata.confirmed_misparse`.

## A. All 53 drafts, sorted by workarounds retired

| # | Draft | Shape | Ledger | Canary | Correction | Total | Strict | Cards | confirmed_misparse |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 16a-keyworded-self-recursion-dropped.md | Recover/unearth/mayhem/aftermath not typed | 9 | 3 | 1 | 13 | 2 | 4 | no |
| 2 | 14-anaphora-misbound.md | Anaphora bound to the wrong object | 5 | 5 | 2 | 12 | 5 | 5 | yes (Stunning Shot) |
| 3 | 08-where-x-binding.md | where X binding swallows the effect | 3 | 4 | 4 | 11 | 4 | 3 | no |
| 4 | 15h-grant-swallowed-beside-typed-effect.md | Clause swallowed beside a typed effect | 11 | 0 | 0 | 11 | 4 | 3 | no |
| 5 | 15e-grant-or-token-parked-as-unimplemented.md | Grant / keyword counter / token parked as Unimplemented | 9 | 1 | 1 | 11 | 0 | 3 | no |
| 6 | 13-static-affected-selfref.md | Static affected stamped SelfRef/TriggeringSource | 4 | 3 | 3 | 10 | 7 | 6 | yes (4 of 6: Benthid, Tsabo's Web, Alacrian Armory, Animate Artifact) |
| 7 | 09-unparsed-quantity.md | unparsed_quantity: 'equal to ...' parked | 6 | 2 | 2 | 10 | 1 | 5 | no |
| 8 | 02-unknown-trigger-modes.md | Trigger events parked as mode.Unknown | 7 | 1 | 1 | 9 | 6 | 8 | no |
| 9 | 11-damage-prevention-redirection.md | Damage prevention / redirection parked | 4 | 3 | 2 | 9 | 6 | 5 | no |
| 10 | 19-condition-or-qualifier-dropped.md | Condition or same-name qualifier dropped | 5 | 3 | 0 | 8 | 1 | 3 | no |
| 11 | 07-graveyard-returns-parked.md | Graveyard returns parked or lost | 5 | 0 | 0 | 5 | 3 | 5 | no |
| 12 | 15i-keyword-lost-from-token-or-zone-owner-dropped.md | Token keyword, suspect, zone owner dropped | 5 | 0 | 0 | 5 | 3 | 3 | no |
| 13 | 06-quoted-granted-abilities.md | Quoted/granted abilities dropped or mistyped | 4 | 1 | 0 | 5 | 1 | 3 | no |
| 14 | 15c-copy-exception-keyword-dropped.md | Copy exception keyword dropped / read as subtype | 0 | 2 | 2 | 4 | 4 | 2 | no |
| 15 | 15f-role-token-ability-missing.md | Role token has no ability | 2 | 1 | 1 | 4 | 4 | 1 | no |
| 16 | 25-countered-spell-exiled-instead-typed-from-graveyard.md | Countered spell 'exile it instead' typed from graveyard | 0 | 2 | 1 | 3 | 3 | 23 | no |
| 17 | 35-this-way-set-reference-parked.md | '... this way' set reference parked | 2 | 1 | 0 | 3 | 3 | 17 | yes (Raiding Party) |
| 18 | 24d-split-coin-flip.md | One coin flip typed as two | 0 | 2 | 1 | 3 | 3 | 3 | no |
| 19 | 18-second-sentences-and-reflexive-effects.md | Second sentences, restrictions, reflexive effects parked | 0 | 1 | 2 | 3 | 1 | 6 | no |
| 20 | 24j-mirrormind-crown-token-copy-replacement-parked.md | Mirrormind Crown token-copy replacement parked | 3 | 0 | 0 | 3 | 1 | 1 | no |
| 21 | 04-unless-pays.md | Unless any player pays on a placeholder | 1 | 1 | 1 | 3 | 0 | 1 | no |
| 22 | 31-qualified-cant-be-targeted-parked-as-other.md | Qualified can't-be-targeted parked as Other | 2 | 0 | 0 | 2 | 2 | 22 | yes (Fiendslayer Paladin, Dense Foliage; Autumn's Veil, Display of Dominance) |
| 23 | 12a-that-player-controls-stamped-you.md | 'that player controls' stamped You | 0 | 1 | 1 | 2 | 2 | 4 | yes (Teferi, Temporal Pilgrim) |
| 24 | 12d-graveyard-exile-no-owner.md | Graveyard exile with no owner | 0 | 1 | 1 | 2 | 2 | 3 | no |
| 25 | 12c-payer-chooser-stamped-controller.md | Payer/chooser stamped Controller | 0 | 1 | 1 | 2 | 2 | 2 | no |
| 26 | 17-blocking-restriction-and-spell-target-constraint.md | Typeless blocker filter; 'with one or more targets' dropped | 0 | 2 | 0 | 2 | 2 | 2 | no |
| 27 | 15d-pump-grant-dropped.md | Pump's keyword grant dropped | 0 | 1 | 1 | 2 | 2 | 1 | no |
| 28 | 26-mana-spend-rider-exile-instead-parked.md | Mana rider 'exile instead' parked | 0 | 1 | 1 | 2 | 2 | 1 | no |
| 29 | 36-revealed-hand-discard-parked.md | Revealed-hand discard parked | 0 | 0 | 2 | 2 | 1 | 15 | no |
| 30 | 03-tracked-set-unbound.md | Tracked set lost or unbound | 1 | 1 | 0 | 2 | 1 | 3 | yes (Cleansing Meditation) |
| 31 | 22-mana-spending-restrictions-and-foretell.md | Spend-only restrictions and foretell parked | 1 | 0 | 1 | 2 | 1 | 2 | no |
| 32 | 28-emergent-sequence-counter-on-selfref.md | Emergent Sequence counter on SelfRef | 0 | 2 | 0 | 2 | 1 | 1 | yes |
| 33 | 15a-grant-dropped-from-static-modifications.md | Keyword grant left out of static modifications | 0 | 1 | 1 | 2 | 0 | 2 | no |
| 34 | 32-per-count-cost-reduction-parked.md | Per-count cost reduction parked | 1 | 0 | 0 | 1 | 1 | 10 | yes (Battlefield Thaumaturge, Thrasta) |
| 35 | 24e-prevention-residues.md | Prevention residues | 1 | 0 | 0 | 1 | 1 | 3 | no |
| 36 | 33-damage-to-creatures-and-players-parked.md | Damage to a player and their creatures parked | 0 | 0 | 1 | 1 | 1 | 3 | no |
| 37 | 05-reveal-only-search.md | Reveal-only search typed as a move to hand | 1 | 0 | 0 | 1 | 1 | 2 | yes (Chaos Mutation) |
| 38 | 12b-edict-actor-dropped.md | Edict actor dropped | 1 | 0 | 0 | 1 | 1 | 1 | no |
| 39 | 24a-malik-secret-choice-edict.md | Malik secret-choice edict | 1 | 0 | 0 | 1 | 1 | 1 | no |
| 40 | 24c-orcish-captain-flip-outcome-it.md | Orcish Captain flip 'it' SelfRef | 0 | 1 | 0 | 1 | 1 | 1 | no |
| 41 | 24g-loses-defender-trigger.md | Loses-defender trigger parked | 1 | 0 | 0 | 1 | 1 | 1 | no |
| 42 | 21-unimplemented-residue-census.md | Census of Unimplemented classes | 0 | 0 | 0 | 0 | 0 | 14 | n/a |
| 43 | 24h-vibranium-token-no-mana-ability.md | Vibranium token has no mana ability | 0 | 0 | 0 | 0 | 0 | 5 | no |
| 44 | 16b-this-card-from-graveyard-typed-as-any-card.md | 'this card' from graveyard typed as any card | 0 | 0 | 0 | 0 | 0 | 4 | no |
| 45 | 23-as-though-flash-permission-typed-as-cast.md | 'As though it had flash' typed as a cast | 0 | 0 | 0 | 0 | 0 | 2 | no |
| 46 | 15b-unrecognized-condition-swallows-grants.md | Unrecognized condition swallows grants (Tek) | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 47 | 20-seek-has-no-player.md | Seek has no player | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 48 | 24f-craft-with-two-that-share-a-card-type.md | Craft with two that share a card type | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 49 | 24i-kaust-face-up-combat-damage-unknown-mode.md | Kaust face-up combat-damage Unknown mode | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 50 | 27-danse-macabre-non-targeting-return-multi-target.md | Danse Macabre multi_target / parked returns | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 51 | 29-veiling-oddity-cant-be-blocked-broadcast-parked.md | Veiling Oddity broadcast parked | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 52 | 30-tenuous-truce-attack-trigger-unknown-modes.md | Tenuous Truce split into two Unknown modes | 0 | 0 | 0 | 0 | 0 | 1 | no |
| 53 | 34-thought-dissector-compound-reveal-until.md | Thought Dissector compound reveal-until | 0 | 0 | 0 | 0 | 0 | 1 | yes |

Ranking by Strict alone puts 13 (7), 02 (6), 11 (6), 14 (5) first, then 08, 15h, 15c, 15f (4 each).

## Per-draft attribution

### 16a — Recover/unearth/mayhem/aftermath not typed (16a-keyworded-self-recursion-dropped.md)

Cards: 4. confirmed_misparse: no.

- Ledger rows: `energy_unearth_parked` (s), `insult_injury_aftermath_face_unparsed` (j), `insult_injury_aftermath_face_removal` (j), `opp_discard_driven_despair_missing_face` (j), `team_keyword_grant_aftermath_face` (j), `aftermath_face_double_strike` (j), `aftermath_face_bulk_draw` (j), `aftermath_face_each_player_draw` (j), `keyword_dropped_paylife` (j)
- Canary tests: `test_self_recurring_keyword_gap_canary` (s), `test_missing_aftermath_face_canary` (j), `test_dropped_keyword_costs_canary` (j)
- Correction rows / tokens: energy_payment token (STATIC_TOKENS row + ALLOWLIST; Salvation Colossus; Reiterating Bolt, Izzet Generatorium, Razorfield Ripper undrafted) (p)
- Note: Two upstream fixes in one draft: (a) keywords with a non-mana cost parked (Recover, Unearth, and by the same parse, warp/madness/escape with life: keyword_dropped_paylife + test_dropped_keyword_costs_canary); (b) no face record for an aftermath half (Dawn; 7 missing_face ledger rows + test_missing_aftermath_face_canary). Splitting (b) out would make it the single biggest retirement on our side.

### 14 — Anaphora bound to the wrong object (14-anaphora-misbound.md)

Cards: 5. confirmed_misparse: yes (Stunning Shot).

- Ledger rows: `akiri_unattach_selfref_grant` (j), `dauntless_bodyguard_chosen_creature` (j), `orphan_double_strike_grant` (j), `aura_untap_back_reference_unbound` (j), `fumble_plural_attachment_anaphor` (j)
- Canary tests: `test_anaphoric_pump_canary` (s), `test_fresh_tap_target_is_still_a_back_reference_canary` (s), `test_fatespinner_skip_is_still_parked_canary` (s), `test_ogre_battledriver_it_is_still_an_unresolved_parent_target_canary` (j), `test_earthbend_last_created_binding_canary` (j)
- Correction rows / tokens: `overlay_corrections._arm_anaphoric_pump` (s), `overlay_corrections._arm_fresh_tap_target` (s)
- Note: 24c (Orcish Captain's flip 'it') and 28 (a spell's SelfRef) are the same binding defect.

### 08 — where X binding swallows the effect (08-where-x-binding.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `where_x_player_burn_dropped` (j), `mutate_count_team_pump_dropped` (j), `amass_zombies_dropped` (j)
- Canary tests: `test_resource_clause_still_parked_canary` (p), `test_unbound_x_reach_canary` (j), `test_parked_search_put_canary` (j), `test_commence_the_endgame_amass_dropped_canary` (j)
- Correction rows / tokens: ALLOWLIST connive (s), ALLOWLIST amass (s), ALLOWLIST investigate (s), ALLOWLIST devour (s)
- Note: The resource canary is parametrized over 14 cards: 4 are 08's (Mask, Fall of Cair Andros, Officious Interrogation, Thromok), 3 are 22's foretell, 1 is 09's, 1 is 16a's, 5 have no draft (Robobrain War Mind, The Motherlode, Reiterating Bolt, Izzet Generatorium, Jetmir's Fixer).

### 15h — Clause swallowed beside a typed effect (15h-grant-swallowed-beside-typed-effect.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `ice_counter_defender_swallowed` (s), `dig_onto_battlefield_indestructible_counter_dropped` (s), `cloak_dropped_from_dig` (s), `cloak_dropped` (s), `cheat_dropped_clause_zero_residue` (p), `cloak_parked` (j), `untapped_artifacts_indestructible_swallowed` (j), `enters_and_gains_protection_dropped` (j), `put_attacking_gains_indestructible_swallowed` (j), `cast_this_way_gains_haste_dropped` (j), `stolen_creature_gains_haste_dropped` (j)
- Canary tests: none
- Correction rows / tokens: none
- Note: cheat_dropped_clause_zero_residue has 6 pins; Wakanda Forever! is the only one here.

### 15e — Grant / keyword counter / token parked as Unimplemented (15e-grant-or-token-parked-as-unimplemented.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `encore_grant_parked` (j), `cast_this_way_gains_haste_parked` (j), `own_card_suspend_grant_parked` (j), `landwalk_choice_grant_parked` (j), `keyword_swap_parked` (j), `chosen_keyword_moved_flying` (j), `chosen_keyword_moved_first_strike` (j), `chosen_keyword_moved_trample` (j), `chosen_keyword_moved_shadow` (j)
- Canary tests: `test_residue_keyword_canary` (p)
- Correction rows / tokens: `recovery.residue_body_keywords` (p)
- Note: test_residue_keyword_canary: 4 of 9 cases are named here (Notorious Throng via 09); Mardu Thunderkite, Rushblade Commander, Blitzwing, Wall of Caltrops, Better Offer have no draft. All nine ledger rows are judgement (report section 15 single cards); five are Phyrexian Splicer alone.

### 13 — Static affected stamped SelfRef/TriggeringSource (13-static-affected-selfref.md)

Cards: 6. confirmed_misparse: yes (4 of 6: Benthid, Tsabo's Web, Alacrian Armory, Animate Artifact).

- Ledger rows: `equipped_defender_attack_misread` (s), `moku_haste_grant_misscoped_selfref` (j), `team_keyword_grant_misscoped_selfref` (j), `team_indestructible_misbound` (j)
- Canary tests: `test_cant_untap_object_canary` (s), `test_self_animation_canary` (s), `test_animated_object_canary` (s)
- Correction rows / tokens: `overlay_corrections._arm_cant_untap_object` (s), `overlay_corrections._arm_self_animation` (s), `overlay_corrections._arm_animated_object` (s)
- Note: The three overlay arms each have their canary in test_phase_gaps_fields.py.

### 09 — unparsed_quantity: 'equal to ...' parked (09-unparsed-quantity.md)

Cards: 5. confirmed_misparse: no.

- Ledger rows: `mass_token_clause_parked` (p), `each_player_equal_damage_parse_failure` (j), `exile_cast_discount_parse_failure` (j), `second_verb_reveal_hand_parked` (j), `wizard_count_parked` (j), `goblins_devoured_parked` (j)
- Canary tests: `test_peeled_subject_canary` (s), `test_attempted_murder_counters_are_still_a_residue_canary` (j)
- Correction rows / tokens: recovery._peeled_subject (shared with 36) (p), ALLOWLIST gain_energy (Overclocked Electromancer; Robobrain, Motherlode undrafted) (p)
- Note: mass_token_clause_parked has 8 pins; only Notorious Throng is in the draft. _peeled_subject also serves Amnesia (36). gain_energy also serves Robobrain War Mind and The Motherlode (no draft).

### 02 — Trigger events parked as mode.Unknown (02-unknown-trigger-modes.md)

Cards: 8. confirmed_misparse: no.

- Ledger rows: `exile_from_hand_trigger_unknown_mode` (s), `explore_payoff_trigger_unknown_mode` (s), `foretell_payoff_trigger_unknown_mode` (s), `reflexive_food_trigger_dropped` (s), `land_return_trigger_unknown_mode` (s), `team_enters_watcher_parse_failure` (s), `chosen_players_drain_trigger_parked` (j)
- Canary tests: `test_equipped_attack_canary` (j)
- Correction rows / tokens: misparsed_shapes: equipped-attack row (+ clause_grammar.attached_attackers_kind) (j)
- Note: Eye of Singularity's own workaround (the same-name veto) is 19's. Tenuous Truce (30) asks for the same joined-event form as Ranar.

### 11 — Damage prevention / redirection parked (11-damage-prevention-redirection.md)

Cards: 5. confirmed_misparse: no.

- Ledger rows: `prevention_shield_parse_failure` (s), `gated_prevention_parked` (s), `damage_prevention_replacement_parse_failure` (j), `plus_one_rock_hydra_static_parse_failure` (j)
- Canary tests: `test_redirect_is_still_a_residue_canary` (s), `test_counter_bonus_is_still_a_residue_canary` (s), `test_parked_prevention_residues_canary` (p)
- Correction rows / tokens: damage_redirect token (REPLACEMENT_TOKENS row + ALLOWLIST) (s), counter_bonus token (REPLACEMENT_TOKENS row + ALLOWLIST) (s)
- Note: test_parked_prevention_residues_canary covers 6 residue classes; the draft names prevention_source_scope (Well-Laid Plans) and the prevent_damage_recipient_target_role count; Safeguard, Dovin, Bloatfly Swarm, Sekki are not in it. 24e is the same family.

### 19 — Condition or same-name qualifier dropped (19-condition-or-qualifier-dropped.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `warchanter_skald_condition_dropped` (j), `modified_reference_dropped` (j), `xspell_card_filter_dropped` (j), `enchanted_vigilance_payoff_dropped` (j), `trampler_excess_damage_payoff_dropped` (j)
- Canary tests: `test_narrowed_permanent_sweeps_canary` (s), `test_winnow_condition_dropped_canary` (j), `test_typeless_mass_filter_canary` (j)
- Correction rows / tokens: none
- Note: Every ledger row here is judgement: the draft names none of them; the report's section 19 lists Warchanter Skald and the 'modified' row as the same family.

### 07 — Graveyard returns parked or lost (07-graveyard-returns-parked.md)

Cards: 5. confirmed_misparse: no.

- Ledger rows: `creature_reanimation_misparse` (s), `mass_reanimation_parse_failure` (s), `aura_reanimation_etb_parse_failure` (s), `madness_paid_etb_return_parse_failure` (j), `reanimation_card_type_dropped` (j)
- Canary tests: none
- Correction rows / tokens: none
- Note: Custodi Soulcaller / Venerable Warsinger are where_x_binding residues: draft 08's shape too.

### 15i — Token keyword, suspect, zone owner dropped (15i-keyword-lost-from-token-or-zone-owner-dropped.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `furygale_flocking_token_flying` (s), `skeleton_token_suspected_dropped` (s), `graveyard_card_suspended_owner_dropped` (s), `welcome_the_darkness_token_flying` (j), `devil_tokens_gain_haste_dropped` (j)
- Canary tests: none
- Correction rows / tokens: none

### 06 — Quoted/granted abilities dropped or mistyped (06-quoted-granted-abilities.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `exile_grant_all_activated_abilities` (j), `sokrates_granted_prevention_misparse` (j), `quoted_grant_read_as_token_replacement` (j), `kaya_emblem_cast_from_exile_drop` (j)
- Canary tests: `test_perpetual_bounce_misparse_canary` (s)
- Correction rows / tokens: none
- Note: Frodo and Nicol Bolas, Dragon-God have no workaround for this shape (the Bolas LoseTheGame canary is a different ability, and phase types that player now: see D). The four ledger rows are the report's section 6 'Also' list.

### 15c — Copy exception keyword dropped / read as subtype (15c-copy-exception-keyword-dropped.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_copy_grant_dropped_canary` (s), `test_stray_grant_subtype_canary` (s)
- Correction rows / tokens: dropped_keywords copy arm (s), dropped_keywords misread-subtype arm (_misread_subtype_lists/_keywords_for_subtypes) (s)

### 15f — Role token has no ability (15f-role-token-ability-missing.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `role_attach_parked` (s), `monster_role_trample_parked` (s)
- Canary tests: `test_role_token_ability_dropped_canary` (s)
- Correction rows / tokens: `dropped_keywords._role_grants` (s)
- Note: Become Brutes is named in the draft's 'same applies to 11 Role-making cards' line.

### 25 — Countered spell 'exile it instead' typed from graveyard (25-countered-spell-exiled-instead-typed-from-graveyard.md)

Cards: 23. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_countered_exile_instead_canary` (s), `test_cast_trigger_exile_instead_canary` (s)
- Correction rows / tokens: misparsed_shapes: exile-instead row (counterspell + cast-trigger forms) (s)
- Note: crosswalk.diverts_from_graveyard reads the corrected shape and would need re-checking, not deleting. 26 is the same 'exile instead' fact on a mana rider.

### 35 — '... this way' set reference parked (35-this-way-set-reference-parked.md)

Cards: 17. confirmed_misparse: yes (Raiding Party).

- Ledger rows: `those_cards_reanimation_parked_permanent_recast` (s), `those_cards_reanimation_parked_creature_recursion` (s)
- Canary tests: `test_harsh_mercy_chosen_type_dropped_canary` (s)
- Correction rows / tokens: none
- Note: The generic recovery reads of parked 'this way' sweeps (reads.recovered_each_permanent / recovered_land_sweep) would go quiet but are general machinery, not counted. 03 and 27 carry the same residue.

### 24d — One coin flip typed as two (24d-split-coin-flip.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_split_coin_flip_canary` (s), `test_split_delayed_coin_flip_canary` (s)
- Correction rows / tokens: misparsed_shapes: split coin flip row (s)

### 18 — Second sentences, restrictions, reflexive effects parked (18-second-sentences-and-reflexive-effects.md)

Cards: 6. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_self_discount_continuation_parked_canary` (s)
- Correction rows / tokens: self_discount token (STATIC_TOKENS row + ALLOWLIST; shared with 32) (p), clause_grammar reveal_hand row for Blackmail's "reveals three cards from their hand" (j)
- Note: The self_discount token also serves 32's Thrasta / Korvold / The Balrog; it retires only with both.

### 24j — Mirrormind Crown token-copy replacement parked (24j-mirrormind-crown-token-copy-replacement-parked.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `token_creation_replacement_parked` (s), `tokens_as_copies_parse_failure` (p), `permanent_entry_parse_failure` (p)
- Canary tests: none
- Correction rows / tokens: none
- Note: Two of the three rows have other pins (Thunderbond Vanguard; Araumi, Become Anonymous, Krovikan Vampire, Ruthless Radrat, Write into Being).

### 04 — Unless any player pays on a placeholder (04-unless-pays.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `withercrown_unless_lose_life` (j)
- Canary tests: `test_unless_note_is_still_phases_annotation_canary` (j)
- Correction rows / tokens: `recovery._UNLESS_NOTE_RX` (j)
- Note: Nothing reads Rhystic Tutor itself (job_quality/tutor.py only documents the gap). Both attributions are to the 'Unsupported unless clause' class the draft mentions as related.

### 31 — Qualified can't-be-targeted parked as Other (31-qualified-cant-be-targeted-parked-as-other.md)

Cards: 22. confirmed_misparse: yes (Fiendslayer Paladin, Dense Foliage; Autumn's Veil, Display of Dominance).

- Ledger rows: `yours_untargetable_parked` (s), `land_shield_misscoped_selfref` (s)
- Canary tests: none
- Correction rows / tokens: none
- Note: ConceptTree.other_static_modes() exists only for Tomik's row.

### 12a — 'that player controls' stamped You (12a-that-player-controls-stamped-you.md)

Cards: 4. confirmed_misparse: yes (Teferi, Temporal Pilgrim).

- Ledger rows: none
- Canary tests: `test_tap_other_player_canary` (s)
- Correction rows / tokens: `overlay_corrections._arm_tap_other_player` (s)
- Note: field_corrections' legacy tap_down arm also resolves a tap's opponent anaphora but is a generic compat arm, not counted.

### 12d — Graveyard exile with no owner (12d-graveyard-exile-no-owner.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_graveyard_owner_canary` (s)
- Correction rows / tokens: `overlay_corrections._arm_graveyard_owner` (s)

### 12c — Payer/chooser stamped Controller (12c-payer-chooser-stamped-controller.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_other_player_branch_misreads_canary` (s)
- Correction rows / tokens: branches.BRANCH_MISREADS Fraying Line row (s)

### 17 — Typeless blocker filter; 'with one or more targets' dropped (17-blocking-restriction-and-spell-target-constraint.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_glorfindel_blocking_limit_misparse_canary` (s), `test_wylls_reversal_target_constraint_canary` (s)
- Correction rows / tokens: none

### 15d — Pump's keyword grant dropped (15d-pump-grant-dropped.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_partly_read_grant_canary` (s)
- Correction rows / tokens: `recovery._partly_read_grant` (s)

### 26 — Mana rider 'exile instead' parked (26-mana-spend-rider-exile-instead-parked.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_mana_spent_exile_is_still_a_residue_canary` (s)
- Correction rows / tokens: exile_instead token (REPLACEMENT_TOKENS row + ALLOWLIST) (s)

### 36 — Revealed-hand discard parked (36-revealed-hand-discard-parked.md)

Cards: 15. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: `recovery._after_anothers_revealed_hand` (s), recovery._peeled_subject (Amnesia; shared with 09) (p)
- Note: _peeled_subject is shared with 09 (Tar Fiend's canary).

### 03 — Tracked set lost or unbound (03-tracked-set-unbound.md)

Cards: 3. confirmed_misparse: yes (Cleansing Meditation).

- Ledger rows: `global_ruin_tracked_set_sacrifice` (j)
- Canary tests: `test_unbound_graveyard_cast_misparse_canary` (s)
- Correction rows / tokens: none
- Note: Global Ruin is report section 3's 'Also', not in the draft.

### 22 — Spend-only restrictions and foretell parked (22-mana-spending-restrictions-and-foretell.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: `artifact_ability_mana_type_dropped` (j)
- Canary tests: none
- Correction rows / tokens: ALLOWLIST foretell (Karfell Harbinger, Ethereal Valkyrie, Ranar) (s)
- Note: The foretell token serves exactly Karfell Harbinger, Ethereal Valkyrie and Ranar (all 22's shape).

### 28 — Emergent Sequence counter on SelfRef (28-emergent-sequence-counter-on-selfref.md)

Cards: 1. confirmed_misparse: yes.

- Ledger rows: none
- Canary tests: `test_spell_self_counter_misbinding_canary` (s), `test_spell_selfref_misbinding_canary` (j)
- Correction rows / tokens: none
- Note: test_spell_selfref_misbinding_canary (Blizzard Brawl, Savage Order, Promise of Loyalty) is attributed because backlog.md says draft 28 reports that shape; its fix needs three different rebinds.

### 15a — Keyword grant left out of static modifications (15a-grant-dropped-from-static-modifications.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_static_grant_dropped_canary` (p)
- Correction rows / tokens: dropped_keywords._grants Continuous-def arm (shared with 15b) (p)
- Note: test_static_grant_dropped_canary: 6 of its 9 cases are 15a's family, 3 (Tek x2, Tribal Golem) are 15b's; the _grants arm restores both.

### 32 — Per-count cost reduction parked (32-per-count-cost-reduction-parked.md)

Cards: 10. confirmed_misparse: yes (Battlefield Thaumaturge, Thrasta).

- Ledger rows: `per_spell_self_discount_parked` (s)
- Canary tests: none
- Correction rows / tokens: none
- Note: Shares the self_discount token with 18.

### 24e — Prevention residues (24e-prevention-residues.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: `granted_unattach_prevention_parse_failure` (s)
- Canary tests: none
- Correction rows / tokens: none

### 33 — Damage to a player and their creatures parked (33-damage-to-creatures-and-players-parked.md)

Cards: 3. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: recovery._PLAYERS_BOARD_TOO_RX (Mob Verdict / Chandra's Flame Wave swept-board mark) (s)
- Note: _PLAYERS_BOARD_TOO_RX is not canary-guarded.

### 05 — Reveal-only search typed as a move to hand (05-reveal-only-search.md)

Cards: 2. confirmed_misparse: yes (Chaos Mutation).

- Ledger rows: `cheat_kept_destination_hand_misparse` (s)
- Canary tests: none
- Correction rows / tokens: none
- Note: Grim Reminder has no workaround (tutor.py documents it).

### 12b — Edict actor dropped (12b-edict-actor-dropped.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `opponent_sacrifice_actor_dropped` (s)
- Canary tests: none
- Correction rows / tokens: none
- Note: overlay_corrections' legacy edict_scope arm is generic, not counted. Variable Solutions is also 20's card (a different clause).

### 24a — Malik secret-choice edict (24a-malik-secret-choice-edict.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `secret_choice_edict_parse_failure` (s)
- Canary tests: none
- Correction rows / tokens: none

### 24c — Orcish Captain flip 'it' SelfRef (24c-orcish-captain-flip-outcome-it.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: `test_flip_outcome_anaphor_stamped_selfref_canary` (s)
- Correction rows / tokens: none

### 24g — Loses-defender trigger parked (24g-loses-defender-trigger.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: `loses_defender_trigger_parked` (s)
- Canary tests: none
- Correction rows / tokens: none

### 21 — Census of Unimplemented classes (21-unimplemented-residue-census.md)

Cards: 14. confirmed_misparse: n/a.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none
- Note: A census by residue class: no workaround keys on it, but the generic recovery ALLOWLIST and the 26 Appendix A1 fail-closed rows shrink as classes get typed.

### 24h — Vibranium token has no mana ability (24h-vibranium-token-no-mana-ability.md)

Cards: 5. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 16b — 'this card' from graveyard typed as any card (16b-this-card-from-graveyard-typed-as-any-card.md)

Cards: 4. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none
- Note: The report and backlog name a ledger row nether_shadow_graveyard_return_parked that no longer exists; Nether Shadow is now read by the generic recovery (card_advantage._recovered_returns_self).

### 23 — 'As though it had flash' typed as a cast (23-as-though-flash-permission-typed-as-cast.md)

Cards: 2. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 15b — Unrecognized condition swallows grants (Tek) (15b-unrecognized-condition-swallows-grants.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none
- Note: Retires nothing alone: its cases sit in 15a's canary and arm. Post with 15a.

### 20 — Seek has no player (20-seek-has-no-player.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 24f — Craft with two that share a card type (24f-craft-with-two-that-share-a-card-type.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 24i — Kaust face-up combat-damage Unknown mode (24i-kaust-face-up-combat-damage-unknown-mode.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 27 — Danse Macabre multi_target / parked returns (27-danse-macabre-non-targeting-return-multi-target.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 29 — Veiling Oddity broadcast parked (29-veiling-oddity-cant-be-blocked-broadcast-parked.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 30 — Tenuous Truce split into two Unknown modes (30-tenuous-truce-attack-trigger-unknown-modes.md)

Cards: 1. confirmed_misparse: no.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

### 34 — Thought Dissector compound reveal-until (34-thought-dissector-compound-reveal-until.md)

Cards: 1. confirmed_misparse: yes.

- Ledger rows: none
- Canary tests: none
- Correction rows / tokens: none

## B. Recommended first batch (post these first)

Ordered by strict retirements, with the "prefer an unflagged draft when close" rule applied (11 and 02 ahead of 13; 08 and 15h ahead of 14). Companions in parentheses are the same upstream fix: post them together.

1. **11 (+ 24e)** damage prevention / redirection. Total 9, strict 6, unflagged. Deletes the `damage_redirect` and `counter_bonus` tokens (their `REPLACEMENT_TOKENS` rows and `ALLOWLIST` entries) with `test_redirect_is_still_a_residue_canary` and `test_counter_bonus_is_still_a_residue_canary`, the ledger rows `prevention_shield_parse_failure` and `gated_prevention_parked` (j: `damage_prevention_replacement_parse_failure`, `plus_one_rock_hydra_static_parse_failure`), part of `reads.PARKED_PREVENTION_RESIDUES` and its canary, and 24e's `granted_unattach_prevention_parse_failure`.
2. **02 (+ 30, 24i)** trigger events parked as `mode.Unknown`. Total 9, strict 6, unflagged. Deletes six ledger rows (`exile_from_hand_trigger_unknown_mode`, `explore_payoff_trigger_unknown_mode`, `foretell_payoff_trigger_unknown_mode`, `reflexive_food_trigger_dropped`, `land_return_trigger_unknown_mode`, `team_enters_watcher_parse_failure`), and if phase types Unknown modes generally (j) `chosen_players_drain_trigger_parked` and the `misparsed_shapes` Akiri row with `clause_grammar.attached_attackers_kind` and `test_equipped_attack_canary`. 30 and 24i retire nothing on their own; 30 asks for the same joined-event form.
3. **13** `affected` stamped `SelfRef` / `TriggeringSource`. Total 10, strict 7 (the most strict), but phase already flags 4 of its 6 records (lead with Hidden Guerrillas and Warmonger's Chariot, which aren't flagged). Deletes `overlay_corrections._arm_cant_untap_object`, `_arm_self_animation`, `_arm_animated_object` and their three canaries, and the ledger row `equipped_defender_attack_misread` (j: the two Moku rows, `team_indestructible_misbound`).
4. **08 (+ 07)** `where X` binding and the graveyard returns it swallows. 08: total 11, strict 4; 07: total 5, strict 3; both unflagged. Deletes the `connive`, `amass`, `investigate`, `devour` recovery tokens and 4 of the 14 cases of `test_resource_clause_still_parked_canary`; (j) `reads.unbound_x_reach`, `reads.parked_search_puts_onto_battlefield` and their canaries, the Commence the Endgame canary, `amass_zombies_dropped`, `where_x_player_burn_dropped`, `mutate_count_team_pump_dropped`; 07 deletes `creature_reanimation_misparse`, `mass_reanimation_parse_failure`, `aura_reanimation_etb_parse_failure` (Custodi Soulcaller and Venerable Warsinger are where_x residues, so 07 and 08 overlap).
5. **15h** a clause swallowed beside a typed effect. Total 11, strict 4, unflagged. Deletes `ice_counter_defender_swallowed`, `dig_onto_battlefield_indestructible_counter_dropped`, `cloak_dropped_from_dig`, `cloak_dropped` (part of `cheat_dropped_clause_zero_residue`), and (j) six more `keyword_bodies` rows (Become Anonymous, Guardian Beast, Nick Fury x2, Thundermane Dragon, Yasova Dragonclaw).
6. **14 (+ 24c, 28)** anaphora and `SelfRef` bound to the wrong object. 14: total 12, strict 5 (only Stunning Shot flagged); 24c 1; 28 2 (flagged). Deletes `_arm_anaphoric_pump`, `_arm_fresh_tap_target` and their canaries, `control_stax._fatespinner_parked_skip` and its canary; 24c's `SelfRef` arm of `reads._FLIP_ANAPHOR_TAGS`; 28's `has_structural_self_counter_grow` guard (and, j, `protection._filter_recipient`'s spell `SelfRef` arm and `attack_deterrent`'s exception); (j) five ledger rows (Akiri, Dauntless Bodyguard, Violent Urge, Howl of the Hunt, Fumble) and the Ogre Battledriver and Bumi canaries.
7. **16a, split in two before posting** keyword self-recursion and aftermath halves. Total 13 (the most), strict 2, unflagged. The keyword half deletes `theme_presets.SELF_RECURRING_KEYWORD_GAPS`'s arm and its canary, `energy_unearth_parked`, part of the `energy_payment` token, and (j) `crosswalk.core._dropped_keyword_costs` with its canary and `keyword_dropped_paylife`. The aftermath half ("Dawn has no face record") deletes, if phase emits aftermath face records, 7 `missing_face` ledger rows and `test_missing_aftermath_face_canary`. That is a different upstream fix, and it is worth its own issue.
8. **15c (+ 15a, 15b, 15d)** a keyword dropped from a typed body. Strict 4 + 2 + shared 2, unflagged. Together they empty `dropped_keywords` except the Role arm: the copy arm, the misread-subtype arm, the `_grants` Continuous-def arm, plus `recovery._partly_read_grant`, `test_copy_grant_dropped_canary`, `test_stray_grant_subtype_canary` (and `reads._SUBTYPE_WORDS`' gate), `test_static_grant_dropped_canary`, `test_partly_read_grant_canary`. 15b retires nothing without 15a.
9. **15f** Role token has no ability. Total 4, strict 4, unflagged. Deletes `dropped_keywords._role_grants`, `test_role_token_ability_dropped_canary`, `role_attach_parked`, `monster_role_trample_parked`.
10. **25 (+ 26)** "exile it instead" of the graveyard. 25: strict 3, 23 cards; 26: strict 2; unflagged. Deletes the `misparsed_shapes` exile-instead row with `test_countered_exile_instead_canary` and `test_cast_trigger_exile_instead_canary`, and 26's `exile_instead` token with `test_mana_spent_exile_is_still_a_residue_canary` (`crosswalk.diverts_from_graveyard` then needs a re-check against the new form).

Next tier: 09 + 36 (they share `recovery._peeled_subject`; 09 is total 10 but strict 1), 15e (total 11, all judgement, five rows are Phyrexian Splicer), 19 (total 8, strict 1), 18 + 32 (they share the `self_discount` token), 03 + 35 + 27 (the "this way" tracked set), and the small strict ones 12a, 12c, 12d, 17 (2 each).

Other pairs that are really one fix: 12b + 20 (both Variable Solutions, different clauses: the edict's actor and seek's player).

## C. Drafts that retire nothing on our side (pure reports)

- 16b (Sproutback Trudge, Syrix, Worldheart Phoenix, Nether Shadow; the generic recovery reads Nether Shadow)
- 20 (Variable Solutions' seek)
- 21 (the census; it retires nothing specific)
- 23 (Rootwater Shaman, Aluren)
- 24f (Eye of Ojer Taq)
- 24h (Vibranium tokens; our fix of 2026-11-01 was a projection gap of ours)
- 24i (Kaust)
- 27 (Danse Macabre)
- 29 (Veiling Oddity)
- 30 (Tenuous Truce; it is only one of seven cases in `test_parked_attack_recipient_canary`)
- 34 (Thought Dissector)
- 15b (Tek): nothing alone; its cases sit in 15a's canary and arm

## D. Reporting gaps and stale text

### D1. Ledger rows that record a phase bug but fit no draft (106 of 201; 102 once the four below are set aside)

The README says Appendix A was left out of the drafts on purpose, so most of these are a known gap; they are listed so the next drafting pass can pick them up. Pins in parentheses.

Not phase bugs, or already filed: `ramp_dropped_add_mana_clause` (grammar_straggler: our own clause grammar); `each_other_player_dragon_flying` (kind grammar_straggler: our own grammar); `self_suspend_haste_dropped` (kind grammar_straggler: our own grammar); `donate_superlative_player_unbound_subject` (already filed upstream as phase-rs/phase#8170).

Rows in no report or draft at all (added after the report): `energy_gain_replacement_parked` (Izzet Generatorium), `wither_grant_unparsed` (Everlasting Torment).

**Appendix A1, fail-closed parks (census classes of draft 21 only) (25)**: `additional_combat_phase_parked` (Lightning Runner, Zariel, Archduke of Avernus); `artifact_or_human_graveyard_cast_parked` (Arcade Gannon); `bring_low_counter_condition_parked` (Bring Low); `conditional_alt_win_parked` (Ramses, Assassin Lord); `conditional_combat_pump_parked` (Sickle Dancer); `conditional_threaten_haste_parked` (Might Makes Right); `copy_spell_condition_parked` (Ashnod the Uncaring, Ink-Treader Nephilim, Spellweaver Helix, Uldaros Theorix); `darigaaz_egg_counter_removal_parked` (Darigaaz Reincarnated); `dies_payload_condition_parked` (Fyndhorn Druid); `dunedain_rangers_ring_tempt_parked` (Dúnedain Rangers); `face_up_creature_pump_parked` (Trail of Mystery); `freerunning_return_parse_failure` (Escape Detection); `granted_cast_group_burn_parse_failure` (Construction Arsonist); `hadanas_climb_counter_threshold_parked` (Hadana's Climb // Winged Temple of Orazca); `johan_combat_self_grant_parked` (Johan); `ochre_jelly_counter_condition_parked` (Ochre Jelly); `perpetual_combat_self_pump_parked` (By Elspeth's Command, Hurkyl's Prodigy); `perpetual_spacecraft_pump_parked` (Network Marauder); `perpetual_x_pump_parked` (Gyox, Brutal Carnivora, Mycoid Resurrection); `plains_upkeep_lifegain_parked` (Spiritual Sanctuary); `pump_condition_parked` (Alex Wilder, Runaway, Sickle Dancer); `sigurd_lore_counter_saga_parked` (Sigurd, Jarl of Ravensthorpe); `tetsuo_equipped_condition_damage_parked` (Tetsuo, Imperial Champion); `tetsuo_equipped_condition_parked` (Tetsuo, Imperial Champion); `tetsuo_equipped_condition_removal_parked` (Tetsuo, Imperial Champion)

**Appendix A2, parse failures (40)**: `all_creatures_attack_parse_failure` (Public Enemy, War's Toll); `artifact_cast_permission_empty_effect` (Anrakyr the Traveller); `artifact_graveyard_condition_unrecognized` (Windwright Mage); `attack_you_parse_failure` (Teferi's Moat, Sivitri, Dragon Master, Chronomantic Escape, Mirri, Weatherlight Duelist, Varchild, Betrayer of Kjeldor, Immortal Obligation, Illusionist's Gambit); `base_pt_tk_sticker_parse_failure` (Cool Fluffy Loxodon); `burning_of_xinye_opponent_destroys_lands` (Burning of Xinye); `candlekeep_inspiration_exile_gy_pt_setter` (Candlekeep Inspiration); `cheat_modal_mode_unsupported_qualifier` (Ao, the Dawn Sky); `chosen_creatures_double_strike_parked` (Sigarda's Vanguard); `combat_choice_unimplemented_choose` (Master Warcraft, Brutal Hordechief, Odric, Master Tactician, Melee, Berserker's Frenzy); `hellbent_damage_doubling_hollow` (Anthem of Rakdos); `hollow_graveyard_cast_permission_recast` (Glimpse the Cosmos); `hollow_graveyard_cast_permission_self_recurring` (Glimpse the Cosmos); `human_enters_counter_misparse` (Dearly Departed); `human_token_modes_parked` (Outlaws' Merriment); `illusionists_gambit_additional_combat_swallowed` (Illusionist's Gambit); `is_a_human_unrecognized` (Bonds of Faith); `land_creatures_condition_reference_dropped` (Earth Rumble Wrestlers); `mill_until_creature_steal_parked` (Helm of Obedience); `most_wizards_parked` (Thoughtbound Primoc); `named_synergy_parked_reference` (Sheltered Valley, Ominous Traveler); `night_shift_optional_paylife_dieroll` (Night Shift of the Living Dead); `perpetual_dragon_grant_parked` (Heir to Dragonfire); `perpetual_dragon_parked` (Sarkhan, Wanderer to Shiv); `protection_grant_parked` (Guardian Archon, Jade Orb of Dragonkind, Maze's Mantle, Outmuscle); `protective_grant_parse_failure` (Darksteel Garrison, Guardian Beast, Outmuscle, Sheltering Prayers, Guardian Archon, Jade Orb of Dragonkind, Maze's Mantle); `sac_emblem_activated_cost` (Ob Nixilis of the Black Oath); `shares_a_type_parked` (Invasion of New Capenna // Holy Frazzle-Cannon); `spell_or_ability_redirect_parse_failure` (Emissary of Grudges); `spell_redirect_parse_failure` (Emissary of Grudges, Meddle, Quicksilver Dragon); `target_double_strike_parked` (Urdnan, Dromoka Warrior); `team_base_pt_quantity_parse_failure` (Candlekeep Inspiration); `team_double_strike_parked` (Aradesh, the Founder, Sylvia Brightspear); `team_power_bite_parked` (Combo Attack); `treasure_empty_effect` (Bank Job); `voltron_attach_count_scaling_dropped` (Sage's Reverie); `your_artifacts_reference_parse_failure` (Assassin's Ink, Guardian Beast, Karn, Living Legacy, Phylactery Lich, Robobrain War Mind); `your_enchantments_reference_parse_failure` (Balduvian Shaman, Floodtide Serpent); `zombie_grant_parked` (Afterlife from the Loam, Ghouls' Night Out, Grimoire of the Dead); `zombie_reference_parked` (Wand of Orcus)

**Appendix A3, clauses dropped with no node (34)**: `army_power_bite_dropped` (Widespread Brutality); `base_pt_becomecopy_no_pt_override` (Mindlink Mech); `blocked_by_zombie_dropped` (Time to Reflect); `burn_planeswalker_target_dropped` (Cragganwick Cremator, Flames of the Blood Hand, Kaboom!, Unstable Footing); `captain_rex_nebula_crash_land_final_step_drop` (Captain Rex Nebula); `chosen_type_majority_dropped` (Peer Pressure); `close_encounter_warped_exile_additional_cost` (Close Encounter); `creature_return_cost_dropped` (Veil of Secrecy); `creature_sweep_branch_dropped` (Catastrophe); `curse_shaken_faith_enchant_player_them` (Curse of Shaken Faith); `elf_card_to_hand_dropped` (Bounty of Skemfar); `ellie_vengeful_hunter_damage_half_dropped` (Ellie, Vengeful Hunter); `enchantment_copy_entry_dropped` (Estrid's Invocation); `enchantment_copy_entry_dropped_copy` (Estrid's Invocation); `equipped_cant_attack_you_dropped` (Assault Suit); `exiled_land_put_dropped` (Venture Forth); `flames_blood_hand_headline_clause_drop` (Flames of the Blood Hand); `forage_cast_permission_cost_dropped` (Osteomancer Adept); `kaboom_trailing_clause_drop` (Kaboom!); `keep_n_wrath_unimplemented_choose` (Duneblast, Stick Together, Mount Doom); `kicker_ptplayer_modal_new_target` (Goblin Barrage, Unstable Footing); `lightning_runner_untap_all_dropped` (Lightning Runner); `lone_attacker_double_strike_dropped` (Jin Sakai, Ghost of Tsushima); `modal_venture_dropped` (You Find a Cursed Idol); `one_sided_sweep_creature_half_dropped` (Path of Mettle // Metzali, Tower of Triumph); `opp_discard_fungal_shambler_dropped_conjunct` (Fungal Shambler); `sac_casualty_granted_onto_other_spell` (Anhelo, the Painter, Silverquill, the Disputant); `shares_a_type_dropped` (Cryptic Gateway); `shield_counter_dropped` (Elspeth Resplendent, Undercover Operative); `shrink_clause_dropped` (Decimator Beetle, Zealous Persecution); `vexing_arcanix_reveal_misread_damage_drop` (Vexing Arcanix); `wizard_entering_dropped` (Naban, Dean of Iteration); `zombie_grant_dropped` (Nim Deathmantle); `zuko_modal_unconditional_paylife` (Zuko, Conflicted)

**Appendix A4, missing faces (1)**: `folded_object_text_only_each_player_loses` (Tomb of Annihilation)

**Not in Appendix A (2)**: `energy_gain_replacement_parked` (Izzet Generatorium); `wither_grant_unparsed` (Everlasting Torment)

### D2. Canary tests with no draft (39 of 87 at the ranking; 38 since the dead canary went)

- **Guard a phase bug no draft names (29):** `test_self_damage_sweep_canary` (Solar Blaze), `test_chosen_card_type_sweep_canary` (Season of Gathering), `test_its_controller_manifests_canary` (Unwanted Remake), `test_umbra_armor_grant_canary` (Umbra Mystic), `test_relative_power_return_canary` (Mirko) — five of the eight `misparsed_shapes` rows; `test_counter_added_zone_change_canary` (Athreos), `test_player_counter_kind_canary` (Territorial Gorger), `test_suspended_card_target_canary` (Venser's Diffusion) — three `overlay_corrections` arms; `test_shrink_is_still_a_residue_canary` (Death's Approach and kin: the `debuff` token), `test_draw_and_blight_is_still_a_residue_canary` (Sinister Gnarlbark: the `blight` token; on the report's "Not drafted" list), `test_you_and_target_burn_is_still_a_residue_canary` (Ian the Reckless, Volcano Hellion: the `damage` token's "to you and" override), `test_graveyard_land_play_is_still_a_residue_canary` (Serra Paragon), `test_misread_keyword_canary` (Detritivore's suspend X, Warbringer, Memory Crystal), `test_untyped_discard_cast_keywords_canary` (jump-start, retrace), `test_survivors_partner_is_still_generic_canary`, `test_cryptic_spires_mana_is_still_a_residue_canary`, `test_verdant_mastery_piles_are_still_lost_canary`, `test_overload_sweep_is_read_from_the_base_mode` (Damn, Cyclonic Rift), `test_clause_dropped_canary` (Extinction, Do or Die; nearest draft 19), `test_assault_suit_superfriends_leftover_canary`, `test_parked_attack_recipient_canary` (7 cards; Tenuous Truce is 30's and Vengeful Pharaoh is an Unknown mode, but the shape, "you or a planeswalker you control" parked, has no draft), `test_auriok_steelshaper_equip_reducer_misparse_canary`, `test_cloudsteel_kirin_cant_lose_still_unscoped_canary`, `test_chosen_token_type_canary` (Sarpadian Empires), `test_splice_cost_in_quality_canary` (Veil of Secrecy), `test_visions_of_phyrexia_powerstone_still_recovered_canary`, `test_phase_drops_printed_firebending` (on "Not drafted"), `test_council_vote_is_still_a_residue_canary` (on "Not drafted"), `test_optional_wheel_draw_scope_canary` (Snort; on "Not drafted"), `test_target_opponent_may_canary` (Tell Me What You See; backlog.md says "not yet reported upstream").
- **Deliberately not reported:** `test_each_other_player_still_reads_opponent_canary` (phase has no team formats; backlog.md's own verdict).
- **Renames, not misparses (the `shape_compat` module's own account):** `test_graveyard_owner_controller_canary`, `test_targeted_and_attached_canary`, `test_zero_floor_canary`, `test_spelled_out_hexproof_canary`, `test_owner_shuffles_target_canary`, `test_single_clause_arrival_canary`, `test_self_owned_by_you_canary`.
- **A canary that could no longer fail (done 2026-11-25):** `test_lose_the_game_player_dropped_canary` (Angel of Destiny, Nicol Bolas, Dragon-God) asserted only that the `LoseTheGame` node has no `target`, which stays true now that phase types both losers on the ability's `player_scope` (`OpponentAttacked`, `ControlsCount` over the opponents). `crosswalk.ends_the_game` (and the self-loss reads `_harms_you` / `_loses_you_the_game`) now read `player_scope`, and the canary is deleted. No upstream report to file.

### D3. Correction-layer rows and tokens with no draft

- `misparsed_shapes`: 5 of 8 rows (self-damage sweep; chosen card type read as a creature type; "Its controller manifests dread"; umbra armor grant to a subtype; Mirko's relative-power return). Only the split coin flip (24d), the exile-instead row (25) and (j) the Akiri equipped-attack row (02) map to a draft.
- `overlay_corrections`: `_arm_player_counter_kind`, `_arm_suspended_card_target`, `_arm_counter_added_zone_change`.
- Recovery tokens: `debuff`, `blight`; the `damage` token's "to you and" object-verb override; the undrafted cases of `gain_energy` (Robobrain War Mind, The Motherlode) and `energy_payment` (Reiterating Bolt, Izzet Generatorium, Razorfield Ripper); the Jetmir's Fixer `place_counter` case.
- Crosswalk constants guarded by the canaries above: `core._misread_keyword`, `core.PARTNER_GROUPS_PHASE_COLLAPSES`, `reads.CIRCLED_COLORS_RESIDUE`, `reads.lost_pile_count`, `crosswalk.targets_one_opponent`.
- `shape_compat`'s 7 rows are renames and need no upstream report.

### D4. Stale text

- **No draft names a workaround of ours** (each file was grepped for ledger ids, canary names, correction modules and "our read/side"; the only hit is 27's "our analysis reads it as a variable-target spell", which is still true). So no draft is stale in that sense.
- **Stale in the source documents the drafts were built from:**
  - `phase-upstream-reports.md` §16 and `backlog.md` ("Phase misparses behind cut-check reads") name the ledger row `nether_shadow_graveyard_return_parked`. It is gone from `BRIDGES`; the generic recovery now reads Nether Shadow (`card_advantage._recovered_returns_self`).
  - Report §8 and `backlog.md` ("Every held serve spec is converted") name a `_where_x_head` recovery. It no longer exists; the mechanism is now `TokenRule.from_binding_sentence` + `recovery._recover_binding_sentence`.
  - (Corrected 2026-11-25.) Report §1, §10, §12b and §24 named the retired canaries `test_graveyard_arrival_unknown_mode_canary`, `test_boxing_ring_gate_is_still_a_residue_canary`, `test_chained_sacrifice_actor_dropped_canary` and `test_combat_scope_damage_parses_as_board_sweep` as current; each now says what retired it.
  - (Corrected 2026-11-25.) Report Appendix A's intro said 202 rows. It now gives the measured count: of the ledger's 199 rows it names 186, 10 were added since (named in the intro) and 3 are left out on purpose; the 3 rows retired since are marked.
  - (Corrected 2026-11-25.) The report's "all 166 retirement_canary tests" counted parametrized cases at v0.118.0; it now says so and gives today's 100 functions (253 cases).

## Verification

- **Opened and read in the code:** all 201 ledger rows (ids, kinds and pins dumped from `BRIDGES`; todo text read for about 25 of them, including every row behind the top-ranked drafts' attributions); all 87 canary functions (docstrings, parametrize cases and the module-level card tables in `test_phase_gaps_*.py`); `misparsed_shapes` and `shape_compat` docstrings (every row); `overlay_corrections`' arm tables; `dropped_keywords`' four arms; `branches.BRANCH_MISREADS`; the recovery `ALLOWLIST` (49 tokens) and the `clause_grammar` STATIC/REPLACEMENT token tables; and the recovery helpers `_peeled_subject`, `_after_anothers_revealed_hand`, `_PLAYERS_BOARD_TOO_RX`, `_UNLESS_NOTE_RX`, `residue_body_keywords` and `_partly_read_grant`. Residue names for about 45 ambiguous cards come from the committed snapshot's v0.131.0 phase records. That covers every strict (s) and partial (p) attribution in the top fifteen drafts.
- **Taken from the docs (all the j flags):** shape attributions that rest on the report's "Also (ledger)" lists or on backlog wording. These are 13's Moku x2 and Resistance Reunited; 14's Akiri, Dauntless Bodyguard, Violent Urge, Howl of the Hunt and Fumble; 06's Mairsil/Rex, Sokrates x2 and Kaya; 07's Grave Scrabbler and Agadeem; 19's Warchanter, "modified", X-spell, Solid Footing and Ram Through; 15e's nine; 15h's six; 15i's two; 16a's aftermath rows (draft 16a does ask for the aftermath face record); 28's spell-SelfRef canary (backlog says draft 28 reports it); 04's two; 03's Global Ruin; 08's where-X canaries and rows; and 09's unparsed_quantity rows.
