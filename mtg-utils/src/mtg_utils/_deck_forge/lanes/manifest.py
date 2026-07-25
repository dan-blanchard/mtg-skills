"""``SERVED_SIGNAL_KEYS`` — the hand-maintained served-key manifest (split from
crosswalk_signals.py; input to the ADR-0014 key-agreement gate)."""

from __future__ import annotations

from mtg_utils._deck_forge import signal_keys

# The Signal keys the crosswalk PORTS from the typed substrate — THE served-keys
# constant (ADR-0039 task #80 step 6): every migrated key eventually promoted out
# of the (now-deleted) ADR-0035 Stage-4 residual-tracking machinery, so this is a
# single flat set with no staging/residual distinction left. History: the
# original Stage-2 batch was sliced by the shadow harness against the live hybrid
# path; the Stage-4 default-ON flip temporarily routed a batch of keys the
# crosswalk didn't yet reproduce (vs the legacy ``old_ir_for``) back onto the
# legacy ``extract_signals_ir`` path via a ``_STAGE4_RESIDUAL`` subtraction —
# every one of those keys was subsequently promoted (see the per-key adjudication
# notes below, preserved from the old residual-tracking block) and the legacy
# fallback itself is gone (ADR-0039 task #80 step 6), so the subtraction is now
# always a no-op and has been collapsed away.
SERVED_SIGNAL_KEYS: frozenset[str] = frozenset(
    {
        # Batch 1 (already landed):
        "win_lose_game",
        "discard_makers",
        "spell_copy_makers",
        "spellcast_matters",
        signal_keys.TOKEN_MAKER,
        "draw_matters",
        "land_creatures_matter",
        # Batch 2 (ADR-0035 Stage 2, this increment):
        "death_matters",
        "extra_turns",
        "lifegain_makers",
        "reanimator",
        "plus_one_makers",
        # task #87: pacify_makers — the dedicated structural concept
        # budgets.py's `_INTERACTION_PRESETS` comment named as the recovery
        # path for the Pacifism/Arrest `interaction`-role credit task #86's
        # removal-preset flip cost (see `_pacify_makers`'s own docstring).
        "pacify_makers",
        # task #np_roles: single_target_neutralize — the Darksteel Mutation
        # base-P/T-overwrite neutralize class (CR 613.4b layer 7b), the
        # pacify-adjacent answer shape no removal-family key reads (CR
        # 611.2 — the permanent stays). See `_single_target_neutralize`'s
        # own docstring for the fold-vs-new-key adjudication.
        "single_target_neutralize",
        # task #96 (ADR-0040): mass creature-type changers, zone reach as
        # sibling keys (battlefield / beyond-battlefield / graveyard) — see
        # `_type_changers`'s docstring for the CR grounding and the two
        # ledgered text bridges.
        "type_changers",
        "type_changers_all_zones",
        "type_changers_graveyard",
        # task B-1 (2026-07-16 study): wildcard tribal payoffs — cards that
        # choose a creature type as they enter (CR 614.12) and pay off the
        # chosen type (Door of Destinies, Herald's Horn). Keys on the payoff
        # sites that REFERENCE the choice, never the Choose itself — see
        # `_chosen_type_matters`'s docstring for the serve-vs-punish gates.
        "chosen_type_matters",
        "direct_damage",
        # task B-2 (2026-07-16 study): board-count damage — DealDamage whose
        # amount is an ObjectCount over YOUR creatures/tribe (Mob Justice,
        # Goblin War Strike). The go-wide reach/finisher read; see
        # `_damage_for_each`'s docstring for the amount-site and controller
        # gates that keep X-spells and symmetric counts out.
        "damage_for_each",
        # task B-3 (2026-07-16 study): choose-N-keep-the-rest board resets
        # (Single Combat, Cataclysm) — disjoint from edict_makers (a
        # TrackedSet back-reference is never the CR 701.21a fresh sacrifice
        # choice an edict forces); see `_keep_n_wrath`'s docstring.
        "keep_n_wrath",
        "landfall",
        "sacrifice_outlets",
        "lifegain_matters",
        "blink_flicker",
        "tokens_matter",
        "ramp",
        # Batch 3 (ADR-0035 Stage 2, big over-fire lanes + doer cluster):
        "creatures_matter",
        "artifacts_matter",
        "enchantments_matter",
        "attack_matters",
        "tapped_matters",
        "any_counter_makers",
        "any_counter_matters",
        # task #93: counter_hate — an opponent-directed counter-placement
        # denial (Blightbeetle, Suncleanser), distinct from the above
        # payoff lane. See `_counter_hate`'s own module note.
        "counter_hate",
        # np_boons task #5: adapt_matters — a card that supports/enables OTHER
        # creatures' Adapt (CR 701.46) without itself adapting (Biomancer's
        # Familiar). Distinct from `self_counter_grow`, the adapt DOER
        # population (a creature's own typed Adapt effect).
        "adapt_matters",
        "plus_one_matters",
        "minus_counters_matter",
        "gain_control",
        "treasure_makers",
        "food_makers",
        "clue_makers",
        "blood_makers",
        "mill_makers",
        "proliferate_makers",
        "energy_makers",
        "voltron_makers",
        "voltron_matters",
        # Batch 4 (ADR-0035 Stage 2, this increment):
        "graveyard_makers",
        "graveyard_matters",
        "fight_makers",
        "goad_makers",
        # task B-5 (2026-07-16 study): combat puppeteers — you make
        # opponents' attack/block declarations (CR 508.1a / 509.1a);
        # bridge-only (phase has no typed choose-combat node) — see
        # `_combat_choice_makers`'s docstring.
        "combat_choice_makers",
        "regenerate_makers",
        "lifeloss_makers",
        "lifeloss_matters",
        "edict_makers",
        "land_sacrifice_makers",
        "debuff_makers",
        "lure_makers",
        "copy_permanent",
        "clone_makers",
        "token_copy_makers",
        "connive_makers",
        "explore_makers",
        "suspect_makers",
        "combat_damage_to_opp",
        # Batch 5 (ADR-0035 Stage 2, the named-mechanic long tail):
        "monarch_makers",
        "monarch_matters",
        "discover_makers",
        "venture_makers",
        "venture_matters",
        "daynight_makers",
        "daynight_matters",
        "phasing_makers",
        "voting_makers",
        "ring_tempters",
        "ring_matters",
        "amass_makers",
        "incubate_makers",
        "facedown_makers",
        "dice_makers",
        "cast_from_exile",
        "foretell_makers",
        "cascade_makers",
        "suspend_makers",
        "poison_makers",
        # Batch 6 (ADR-0035 Stage 2): the counter-KIND / count-operand / property
        # build-around cluster.
        "oil_counter_makers",
        "oil_counter_matters",
        "ki_counter_makers",
        "rad_counter_makers",
        "shield_counter_makers",
        "experience_makers",
        "experience_matters",
        "devotion_matters",
        "party_matters",
        "domain_matters",
        "modified_matters",
        "multicolor_matters",
        "colorless_matters",
        "power_matters",
        "low_power_matters",
        "coin_flip",
        "opponent_discard",
        "vanilla_matters",
        # Batch 7 (ADR-0035 Stage 2): the phase / control / terminal-effect cluster
        # + four Scryfall-keyword maker survivors.
        "extra_combats",
        "cost_reduction",
        "donate_makers",
        "conjure_makers",
        "blocked_matters",
        "initiative_makers",
        "initiative_matters",
        "end_the_turn",
        "opponent_exile_makers",
        "boast_makers",
        "exhaust_makers",
        "convoke_makers",
        "magecraft_matters",
        # Batch 8 (ADR-0035 Stage 2): the mana / card-flow / removal-sub-lane /
        # pump-sub-lane / library-top cluster.
        "mana_amplifier",
        "extra_land_drop",
        "group_mana",
        "draw_for_each",
        "discard_outlet",
        "mass_removal",
        "mass_bounce",
        "exile_removal",
        "lands_matter",
        "treasure_matters",
        "blood_matters",
        "anthem_static",
        "count_anthem",
        "scaling_pump",
        "self_pump",
        "team_buff",
        "cheat_into_play",
        "impulse_top_play",
        "play_from_top",
        "counter_manipulation",
        # Batch 9 (ADR-0035 Stage 2): the discard/draw payoff, death-loop,
        # card-advantage-engine, library-top, combat-pump, and grant cluster.
        "discard_matters",
        "opponent_draw_matters",
        "self_death_payoff",
        "dies_recursion",
        "creature_recursion",
        "card_draw_engine",
        "group_hug_draw",
        "target_player_draws",
        "activated_draw",
        "topdeck_selection",
        "topdeck_stack",
        "combat_buff_engine",
        "land_sacrifice_matters",
        "exile_matters",
        "energy_matters",
        "counter_move",
        "explore_matters",
        "dice_matters",
        "extra_upkeep",
        "extra_end_step",
        "facedown_matters",
        "spell_keyword_grant",
        "flash_grant",
        "flash_makers",
        "hand_disruption",
        # Batch 10 (ADR-0035 Stage 2): the trigger-event cluster, effect-tag
        # cluster, keyword-grant/mod-site cluster, P/T-characteristic cluster,
        # static-mode cluster, and three probed bonus ports.
        "creature_etb",
        "permanent_etb",
        "ltb_matters",
        "creature_cast_trigger",
        "opponent_cast_matters",
        "combat_damage_matters",
        "damage_to_opp_matters",
        "second_spell_matters",
        "xspell_matters",
        "counter_control",
        "bounce_tempo",
        "power_double",
        "keyword_grant_target",
        "protection_grant",
        "all_creatures_kw_grant",
        "team_evasion_grant",
        "aura_equip_kw_grant",
        "base_pt_set",
        "variable_pt",
        "trigger_doubling",
        "forced_attack",
        "damage_prevention",
        "damage_equal_power",
        # Batch 11 (ADR-0035 Stage 2): the replacement-doubler cluster, the
        # damage-trigger cluster, the counter/ETB/cast trigger-event cluster,
        # the tap cluster, the library/zone cluster, and four probed bonus
        # ports (§F).
        "token_doubling",
        "counter_doubling",
        "counter_replace_bonus",
        "damage_doubling",
        "damage_reflect",
        "damage_to_you_punish",
        "combat_damage_to_creature",
        "tribe_damage_trigger",
        "symmetric_damage_each",
        "aoe_ping",
        "creature_ping",
        "counter_place_trigger",
        "tribal_etb_multi",
        "typed_enters_punish",
        "noncreature_cast_punish",
        "tap_down",
        "tapper_engine",
        "tap_untap_matters",
        "dig_until",
        "exile_until_leaves",
        signal_keys.TYPED_SPELLCAST,
        "legends_matter",
        "historic_matters",
        "self_blink",
        # Batch 12 (ADR-0035 Stage 2): the trigger-event payoff cluster, the
        # effect-node lanes, the control/land cluster, the mirror-parity
        # lanes, the statics/taxes/counters cluster, and the reference/
        # condition lanes (+ 2 batch-11 adjudicated follow-ups riding the
        # already-ported typed_spellcast / tap_down lanes).
        "scry_surveil_matters",
        "cycling_matters",
        "exert_matters",
        "entered_attacker",
        "saga_matters",
        "life_total_set",
        "unspent_mana",
        "opp_top_exile",
        "kill_engine",
        "control_exchange",
        "land_exchange",
        "land_denial",
        "land_protection",
        "evasion_denial",
        "animate_artifact",
        "color_change",
        "type_change",
        "stax_taxes",
        "symmetric_stax",
        "keyword_counter",
        "counter_grants_kw",
        "counter_distribute",
        "superfriends_matters",
        "commander_matters",
        "big_hand_matters",
        "big_hand_makers",
        "vehicles_matter",
        # Batch 13 (ADR-0035 Stage 2): the field-lookup wholesale batch — 7
        # pure Scryfall-keyword rows, 11 keyword+top-up membership lanes, 5
        # structural payoff arms, 4 kept-mirror ports (keyword_tribe is
        # SUBJECT-carrying).
        "companion_keyword",
        "has_banding",
        "has_dash",
        "has_enlist",
        "specialize_matters",
        "alt_cost_keyword",
        "partner_background",
        "madness_matters",
        "affinity_type",
        "scavenge_fuel",
        "has_soulbond",
        "has_mutate",
        "has_ninjutsu",
        "has_undying_persist",
        "has_devour",
        "has_changeling",
        "myriad_grant",
        "boast_matters",
        "cascade_matters",
        "convoke_matters",
        "curse_matters",
        "foretell_matters",
        "keyword_soup",
        "island_matters",
        "poison_matters",
        "suspend_matters",
        signal_keys.KEYWORD_TRIBE,
        # Batch 14 (ADR-0035 Stage 2): the first structural-remainder batch —
        # the big dynamic-subject lane (type_matters), two never-listed core
        # lanes (removal / tutor), the counter/untap/pump engine cluster, the
        # membership benefit lanes (wants_cloning / wants_theft), the
        # food/clue token-subtype payoffs, the cost-census activated_ability
        # lane, and the kept-mirror survivors re-confirmed against v0.9.0
        # (tutor / flash_matters / coven / outlaw / theft_makers /
        # opponent_exile_matters — mirror-primary, structural reads
        # LOGGED-adds-only where the spec marks them).
        signal_keys.TYPE_MATTERS,
        "removal",
        "tutor",
        "proliferate_matters",
        "untap_engine",
        "theft_makers",
        "own_target_spell",
        "permanent_recast",
        "self_etb_payload",
        "wants_theft",
        "wants_cloning",
        "food_matters",
        "clue_matters",
        "pump_makers",
        "self_counter_grow",
        "flash_matters",
        "activated_ability",
        "mass_death_payoff",
        "destroy_legendary",
        "opponent_exile_matters",
        "opponent_search_matters",
        "color_hoser",
        "coven_matters",
        "crimes_matter",
        "outlaw_matters",
        # Batch 15 (ADR-0035 Stage 2): the second structural-remainder batch —
        # the 7-key TLA bending cluster (per-bend lanes, never conflated — the
        # rules-lawyer-verified CR 701.65/701.66/701.67/702.189 partition), the
        # 2 station split keys, the 7-key grant cluster, and 6 by-value
        # recent-set named mechanics completing ported maker/matters pairs
        # (exhaust_makers b13, suspect_makers b4 — both sibling lanes pinned
        # zero-change).
        "airbend_makers",
        "earthbend_makers",
        "earthbend_matters",
        "firebending_makers",
        "firebending_matters",
        "waterbend_makers",
        "waterbend_matters",
        "station_makers",
        "station_matters",
        "evasion_self",
        "cant_block_grant",
        "global_ability_grant",
        "opponent_counter_grant",
        "conditional_self_protection",
        "sacrifice_protection",
        "life_payment_insurance",
        "speed_makers",
        "speed_matters",
        "exhaust_matters",
        "saddle_matters",
        "suspect_matters",
        "void_warp_makers",
        # Batch 16 (ADR-0035 Stage 2): THE FINAL structural batch — closes the
        # porting phase at 318 keys (314 literal + 4 constants; meld_pair is a
        # literal key ported via the signal_keys.MELD_PAIR constant import, the
        # b12 TYPE_MATTERS precedent). Nine flat kept mirrors, the one
        # raw-oracle SUBJECT mirror (meld_pair — reminder text load-bearing),
        # seven structural arms, two LOW membership lanes (one_punch /
        # keyword_soup_makers), and the exalted keyword row emitting BOTH its
        # own lane and the already-ported voltron_matters (the live tuple).
        "ability_copy",
        "ability_strip_payoff",
        "arcane_matters",
        "celebration_matters",
        "cmdzone_ability",
        "exalted_lone_attacker",
        "flip_self",
        "free_creature_payoff",
        "free_spell_storm",
        "island_makers",
        "keyword_soup_makers",
        signal_keys.MELD_PAIR,
        "named_counter_misc",
        "noncombat_damage_payoff",
        "nonhuman_attackers",
        "one_punch",
        "per_target_payoff",
        "power_tap_engine",
        "starting_life_matters",
        "toughness_combat",
        "typed_anthem_multi",
        # Stage-2 closeout sweep (ADR-0035): the 23 skip-lane dispositions —
        # 14 PORT (structural content lands) + 9 FORMAL KEPT-MIRROR (the
        # b12-sanctioned byte-identical mirror port). Every "digital-only /
        # not commander-buildable" skip rationale was falsified by measured
        # bulk legalities (min: seek_matters cl=0 but bl=98 — deck-forge
        # serves historic_brawl), so nothing stays invisible: all 23 join
        # SERVED_SIGNAL_KEYS (318 → 341) and the mapping file's skip klass dies.
        "attractions_matter",
        "draft_spellbook",
        "each_mode_player",
        "free_plot",
        "legend_rule_off",
        "lessons_matter",
        "lose_unless_hand",
        "miracle_grant",
        "powerup_matters",
        "recast_etb",
        "secret_writedown",
        "seek_matters",
        "snow_matters",
        "stickers_matter",
        "tap_down_blockers",
        "target_own_payoff",
        "target_redirect",
        # task B-4 (2026-07-16 study): the ChangeTargets(Spell) DOER —
        # redirect-the-original instruments (Wild Ricochet, Deflecting Swat,
        # Bolt Bend), split from the target_redirect payoff key; see
        # `_spell_redirect`'s docstring for the CR 115.7 / 707.10c boundary.
        "spell_redirect",
        "targeting_matters",
        "theft_protection",
        "timing_control",
        "villainous_choice",
        "void_warp_matters",
        "voting_matters",
        # ADR-0039 W8 (KEPT-twelve wave) — the 4 Stage-2 KEPT keys PROMOTED
        # this session (0 live-only diff on a fresh commander-legal
        # re-measure, phase v0.20.0, 2026-07-12):
        #   • cheat_from_top — ALREADY byte-identical: the include_membership
        #     floor's ``_apply_membership_floor`` is single-source with
        #     legacy (single-source via ``membership_floor``), so promoting is a
        #     pure key-slice change — the crosswalk was already computing it
        #     identically and throwing it away.
        #   • copy_limit — NEW structural arm (:func:`_copy_limit`) reading
        #     the typed ``deck_copy_limit`` field (a new
        #     :attr:`~mtg_utils._card_ir.crosswalk.ConceptTree.many_copies`
        #     deepening — the b16 precedent).
        #   • base_power_matters — GRADUATED off the old IR's regex recovery
        #     (:func:`_base_power_matters`): phase v0.20.0's typed
        #     ``PtComparison`` node now carries a ``scope`` field
        #     (``'Base'`` vs ``'Current'``) the old lossy projection threw
        #     away, so the lane reads it directly (the graduation rule).
        #   • damage_redirect — a settled KEPT (spec §G: `redirect_target`
        #     exists on only 8 corpus replacements, Pariah itself parses with
        #     NO redirect_target), re-verified this wave and ported as the
        #     b12 SANCTIONED byte-identical mirror (:func:`_damage_redirect`)
        #     — both legacy arms (self-shield + redirect-clause) reused
        #     verbatim, single-source from ``text_reads``.
        "cheat_from_top",
        "copy_limit",
        "base_power_matters",
        "damage_redirect",
        # NB: land_destruction's batch-8 KEPT verdict (the membership-gated
        # structural arm reproduced the live 23-card set 23/23 but added 2
        # non-byte-identical extras — Goblin Grenadiers, Orcish Settlers)
        # predates the ADR-0035 Stage-3a floor extraction; see the
        # land_destruction key entry below (landed by the parallel W8
        # FINISHERS commit) for the fresh re-measure that superseded it.
        #
        # ADR-0039 W8 FINISHERS (KEPT-key promotions, 2026-07-12): four
        # Stage-2 KEPT keys — deliberately never staged (the legacy word
        # mirror served them; each carries an inline KEPT rationale where it
        # lived in the deleted ``_signals_ir.py``) — re-measured and closed this wave.
        # ``extra_draw_step`` PROMOTED via a typed-node extension (mechanism
        # (a)/(b)): :func:`_extra_upkeep_end` already decomposed an
        # additional-BEGINNING-phase's "untap" kind into ``extra_upkeep``
        # (CR 501.1's beginning phase = untap+upkeep+draw); this wave adds
        # the draw-step decomposition alongside it (both == 3 == the deleted
        # regex's Cyclonus/Sphinx/Shadow-of-the-Second-Sun set, 0 lost, 0
        # over-fire). ``excess_damage`` / ``kicked_spell_matters`` /
        # ``free_cast`` PROMOTED via byte-identical KEPT-MIRROR text scans
        # (:func:`_excess_damage` / :func:`_kicked_spell_matters` /
        # :func:`_free_cast`, the same tier as ``_MINUS_COUNTER_KEPT_RX`` /
        # ``_COST_*_KEPT_RX`` above) — each already proven byte-identical
        # (both==N, 0/0) in the legacy IR docstrings phase v0.20 changes
        # nothing structural about, re-verified this wave (excess_damage
        # both=28, kicked_spell_matters both=85, free_cast both=328, all
        # 0 regex_only / 0 ir_only). CR 501.1 / 702.19 / 120.4a / 702.33 /
        # 601.2b / 118.9.
        "excess_damage",
        "extra_draw_step",
        "free_cast",
        "kicked_spell_matters",
        # NB: damage_redirect was ALSO promoted this wave (see the
        # damage_redirect module comment and key entry above, landed by the
        # parallel KEPT-twelve-wave commit) — `redirect_target` exists on
        # only 8 corpus replacements and Pariah itself parses with NO
        # redirect_target (shield Prevention only — structurally identical to
        # a pure prevention shield), but the b12 byte-identical mirror ports
        # cleanly, so it graduated alongside these four.
        # W8 FINISHERS (ADR-0039, KEPT-twelve wave): 4 of the 12 KEPT keys
        # PROMOTED by re-measure under the current landfall rule (adjudicated
        # cw_only gains no longer block promotion — the old byte-match bar
        # this batch-8 land_destruction verdict predates is superseded).
        # land_destruction: the shared `_apply_membership_floor` (imported
        # above) now reproduces the legacy 23-card set 23/23, 0 live_only, 0
        # cw_only on a fresh corpus re-measure — the floor extraction (ADR-
        # 0035 Stage-3a, "one source, zero drift") that landed after the
        # batch-8 verdict already closed the 2-extra byte-mismatch it flagged
        # (Goblin Grenadiers / Orcish Settlers no longer diverge). CR 305.6.
        "land_destruction",
        # big_mana: also entirely `_apply_membership_floor`-served — 542/542 both, 0/0
        # live_only/cw_only at promotion time (the deleted `extract_signals_ir` and
        # `extract_crosswalk_signals` both called the same shared floor function).
        # ADR-0039 task #80 step 3 (deletion phase) REWIRED the
        # floor's structural big_mana arm off the OLD projected `Card`
        # (`_is_big_mana_ir`) onto the concept tree directly
        # (`_is_big_mana_tree`, reading the SAME `ramp` effect-concept set the
        # `ramp` key lane above already uses) — `extract_crosswalk_signals`
        # no longer takes an `ir` parameter at all. CR 106.4.
        "big_mana",
        # ki_counter_matters: the `ki` HasCounters TRIGGER-condition self-
        # check (the Kamigawa flip cycle's "if there are two or more ki
        # counters on ~, you may flip it") needed a deep-walk sibling of the
        # oil arm (`ki_counter_kind_refs`, ADR-0039 W8) — the flat
        # concept-node walk only reaches the trigger's own effect
        # (Unimplemented('flip')), never the trigger's `condition` field one
        # level up. 5/5 live cards closed, 0 cw_only. CR 122.1.
        "ki_counter_matters",
        # named_synergy: entirely bridge-served (`named_synergy_
        # overloaded_named_node`) — the raw typed `Named` node this key's
        # idiom carries is corpus-verified too overloaded (partner pairs /
        # copy-limit swarms / named-card tutoring / planeswalker-uncoupled
        # callbacks — 245 Named-node hits vs 27 legacy) to read directly
        # yet; see the bridge's module comment in bridge_ledger.py. CR
        # 201.4 / 201.5.
        "named_synergy",
        # task #83 (theme-preset structural views, lane-gap fix #5): "cantrip"
        # — the deleted preset's NO_LANE gap (rec 0.10 vs card_draw_engine,
        # which deliberately excludes one-shot rider draw). A new, BOUNDED
        # single-draw-plus-rider lane (:func:`_cantrip`), never emitted
        # before this batch — corpus-scanned to 433 commander-legal hits
        # (vs the old preset's unbounded 3174-card substring match).
        "cantrip",
    }
)

# ── Historical per-key promotion record ───────────────────────────────────
# ADR-0039 task #80 step 6: this used to be the ``_STAGE4_RESIDUAL`` frozenset
# (permanently empty by the time of this step — every key it ever held had
# already been promoted out, one at a time, in the sessions documented below)
# subtracted from the ported set to route a handful of keys back onto the
# legacy ``extract_signals_ir`` fallback. That fallback is gone (the flag died
# with it), so the subtraction collapsed to a no-op and was deleted along with
# it; the per-key promotion adjudications are preserved here as history — each
# documents WHY a specific key's crosswalk recall was verified complete enough
# to serve it live, with corpus counts and CR citations.
# ADR-0035 Stage-4 (default-ON flip): EXACTLY the keys that OWN a flag-ON
# deck-forge test failure — the crosswalk lane MISSES what the legacy
# ``old_ir_for`` serves on a TEST-COVERED card (tests pin the legacy firing;
# design bucket (iii) confirmed overfire=0, so a failure is a genuine crosswalk
# LOSS, never a gain). Derived by running the deck-forge suite with every
# Stage-3 key ported and collecting the ``(key, scope[, subject])`` tuples the
# failing assertions name (80 keys), plus three keys whose loss surfaces only
# once the direct owners are already residual — ``scaling_pump`` (masked in a
# multi-assert test by an earlier-failing key), ``token_maker`` (its crosswalk
# ranking pushes a land-creatures avenue past the engine's avenue cap), and
# ``type_matters`` (the class-tribe membership floor is go_wide-gated on the
# residual ``creatures_matter``, so the floor lane must ride the same
# ``old_ir_for`` arm). Routing ONLY these to residual (they stayed in the now-deleted
# migrated set, so dropping them from ``SERVED_SIGNAL_KEYS`` re-supplied them from
# the
# deleted ``extract_signals_ir(old)`` path — byte-identical to flag-OFF) restored the
# legacy firing without retreating from any key the crosswalk serves correctly.
#
# ADR-0038 W3 batch 3 (combat-coercion cluster): ``forced_attack``,
# ``goad_makers``, and ``lure_makers`` PROMOTED (0 genuine members lost
# vs a live corpus re-measure; the ForceBlock/created-token/self-combo
# false-positive classes excluded, the beyond-legacy gains CR-grounded +
# pinned). ``lure_makers``'s last apparent gap — Destined // Lead's
# Aftermath back face ("Lead"), which phase never emits — is closed by
# the W2c text-only face tree ``trees_for`` synthesizes off the bulk
# face (task #76): the ``_LURE_ABLE`` idiom reads the synthesized
# tree's oracle text, so production parity is exact (the wave's own
# measurement harness predated ``trees_for`` and couldn't see it).
#
# ADR-0038 W3 batch 4 (combat-damage cluster): ``poison_makers``
# PROMOTED (146 both / 0 live_only vs a live corpus re-measure — up
# from a 63-card gap). Two structural gaps closed: (1) a direct
# ``GivePlayerCounter(poison)`` DOER with no infect/toxic/poisonous
# keyword at all (Pit Scorpion, Marsh Viper — joined
# ``_PLAYER_COUNTER_MAKER``); (2) a poison GivePlayerCounter buried
# inside a CreateToken/CreateEmblem's OWN granted-ability definition
# (Serpent Generator, Ajani Sleeper Agent — a deep ``iter_typed_nodes``
# walk). Plus a SANCTIONED whole-card word-mirror
# (``_POISON_WORD_MIRROR``) for the keyword GRANTERS a bearer-only
# keyword-array read misses (Corrupted Conscience "has infect", Snake
# Cult Initiation "has poisonous 3"). One adjudicated GAIN: Ajani's
# emblem giver (legacy's OLD IR projects the whole "You get an emblem
# with ..." clause as one opaque, undecomposed effect — verified via
# ``old_ir_for``, no nested GivePlayerCounter survives — so legacy can
# never see into it; CR 114.1/122.1). ``combat_damage_matters``,
# ``combat_damage_to_opp``, and ``creature_ping`` gained substantial
# structural recovery this batch too (nested/delayed trigger descent,
# an Unknown-mode description fallback, a planeswalker-only exclusion,
# and a doer-based creature_ping widening) but still carry a diverse
# residual tail (TK-templated placeholder cards, bare quoted-static
# grants with no CreateDelayedTrigger/GrantTrigger node at all, DFC
# blank-oracle records) — NOT promoted this batch; see the W3 batch 4
# session notes.
#
# ADR-0038 W3 batch 4 (pt-counters-grants cluster): ``cost_reduction``,
# ``minus_counters_matter``, and ``keyword_grant_target`` PROMOTED (0
# genuine members lost vs a live corpus re-measure). ``cost_reduction``
# widened ``_arm_cost_reduction`` to also read ``ReduceAbilityCost{Reduce}``
# (a v0.20.0 typed mode distinct from ``ModifyCost`` — CR 601.2f/118.7
# covers activated-ability costs too), a nested ``GrantStaticAbility.
# definition`` reducer, and ANY node's own description as an Unimplemented-
# residue fallback, plus a final whole-tree kept-mirror for the zero-node
# residuals (Henzie "Toolbox" Torre, Catalyst Stone); the self-discount
# veto is now card-level (a multi-sentence rider's "It also costs ...
# less" continuation inherits it) and a free-cast/impulse-discount
# exclusion added. ``minus_counters_matter`` added a cost-embedded
# ``PutCounter`` walk (Devoted Druid), an ``enter_with_counters`` M1M1
# read (the Persist family's v0.20.0 substrate shape), and the legacy's
# own "-1/-1 counter" kept-mirror for the cares-about residue (Vizier of
# Remedies, Soul-Scar Mage, Necroskitter). ``keyword_grant_target``
# extended the threaded-target walk to trigger-origin units (Conquering
# Manticore's "gain control ... It gains haste" idiom) and added a
# kept-mirror fallback (the deleted SWEEP regex) for phase-parse-loss
# residues and the split/aftermath back-half (Onward // Victory).
# ``base_pt_set`` — see its own PROMOTED comment further down this
# frozenset (ADR-0039 W7 endgame) for the final arm history; the
# interim W3 batch 4/6 notes that used to sit here (21 corpus gaps,
# Belligerent Yearling closing 1 of them) are superseded.
#
# ADR-0038 W3 batch 4: ``scaling_pump`` PROMOTED — the single-target
# ``Pump`` tag is now admitted alongside ``PumpAll`` in
# ``_pump_scaling_lanes`` (CR 107.3 / 613.4c; see that function's
# docstring), plus two widened ``_SCALING_QTY_TAGS`` entries
# (``ZoneCardCount``, ``ObjectTypelineComponentCount``). 0 genuine
# members lost vs a live corpus re-measure (Embiggen, Gold Rush, Gran
# Pulse Ochu, Ral's Staticaster, Sunbathing Rootwalla all recovered);
# the beyond-legacy gains (~182-card corpus diff, every sub-shape by
# target tag corpus-verified) are CR-grounded + pinned.
#
# ADR-0038 W3 batch 4 (draw-etb-tokens cluster, worker w3b4e):
# ``topdeck_stack`` PROMOTED (0 genuine members lost vs a live corpus
# re-measure card-by-card against ``old_ir_for``): a nested-grant
# descent (``GrantAbility``/``GrantTrigger``/``GrantStaticAbility``
# ``.definition``, mirroring ``_self_pump``'s sibling scan — Scion of
# Halaster), a ``ParentTarget``/``TrackedSet``/``ExiledBySource``
# back-reference widening gated by the legacy
# ``supplement._topdeck_stack_self`` self-anchor scan (reused verbatim
# — the SAME disambiguation legacy needs, since phase's Dig /
# PutAtLibraryPosition carry no library-OWNER field, so a self
# top-stack and an opponent-library tuck are structurally
# byte-identical), and the legacy ``_sweep_detectors.
# TOPDECK_STACK_SWEEP_REGEX`` kept mirror run card-level (reused
# verbatim, unchanged) for the two idioms with NO topdeck_stack node at
# all (Leashling/Penance/Hidden Retreat's activation-cost put; Munda,
# Ambush Leader's/Diabolic Vision's modal reveal-then-place ``Dig``).
# A REPLACEMENT-origin unit is excluded (Library of Leng — legacy's
# project.py never walks ``card.replacements`` for this concept,
# verified via ``old_ir_for``) and the nested-grant descent is
# deliberately scoped to the three grant tags, never a blanket
# ``iter_typed_nodes`` walk (Loathsome Troll's modal ``RollDie`` result
# put — corpus-verified over-fire when tried, reverted). CR 401.4.
#
# ADR-0038 W3 batch 5 follow-up: ``landfall`` PROMOTED by the
# orchestrating session's verification pass — the W3 batch 4 lands
# agent left it residual at live_only=1, but that 1 is its OWN
# adjudicated, negative-pinned shed (Tameshi, Reality Architect: the
# land moves battlefield→hand as a cost and the graveyard return
# targets only artifact/enchantment, never a land entering — CR 305.1,
# re-verified via rules-lookup at promotion). live_only = exactly the
# shed set IS the 0-genuine-lost gate; re-measured at HEAD before the
# flip. The 12 cw_only gains (Wandering Troubadour, Restore, Hazezon,
# Soul of Windgrace, ...) were batch-4-adjudicated and pinned.
#
# ADR-0038 W3 batch 6 (draw-etb-tokens cluster): ``creature_etb``
# PROMOTED — corpus re-measure 338 both / 0 genuine live_only (37 raw
# live_only, all adjudicated sheds; see ``_etb_trigger_lanes``'s
# docstring for the full per-class breakdown) / 46 cw_only (Soulbond/
# Graft granted-ability bodies CR 702.95a/702.58a + the pre-existing
# EnteredThisTurn Arm 3 gains, all CR-grounded). Eight arms total: the
# three pre-existing (top-level trigger + DoubleTriggers +
# EnteredThisTurn) plus five new this batch — a nested
# ``GrantTrigger``/``CreateEmblem`` descent and a
# ``CreateDelayedTrigger`` descent (both riding the EXISTING shared
# iterators ``creature_cast_trigger``/``opponent_cast_matters`` already
# use), a compound ``entersorattacks`` event widening, an Unknown-mode
# per-trigger description fallback, an Unimplemented-whole-ability
# per-unit description fallback for the Stickers family, and a
# mode-agnostic ``_ETB_HAD_RE`` per-trigger description fallback for
# Ephara's condition-less delayed payoff (no ``etb`` event exists in
# phase's model for a structural arm to ever reach). CR 603.6a.
#
# ADR-0038 W3 batch 6 (facedown-and-basept cluster): ``facedown_matters``
# PROMOTED. The batch-5 zones agent proved the legacy population is
# SCOPE-MISMATCHED — a plain morph/manifest/cloak MAKER with no genuine
# payoff fires the legacy ``_matters`` lane purely because the OLD IR's
# per-face keyword tuple drops the keyword for a non-mana morph cost
# (Gathan Raiders "Morph—Discard a card" keywords=() vs Krosan Colossus
# "Morph {4}{U}" keywords=('Morph',)) — an artifact of that projection
# quirk, not a principled cares-about boundary (CR 702.37a: Morph is
# the cast-as-2/2 ability; a plain maker never references an EXISTING
# face-down object). Re-measured at HEAD: 61 live_only, 3 cw_only. 33
# of the 61 are this maker-idiom shed (Gathan Raiders/Whisperwood
# Elemental/Gift of Doom's own "as ~ is turned face up" morph rider/
# Cloak and Dagger, Entwined's pure regex name-collision — negative-
# pinned) and 28 are genuine structural gaps now closed: a FaceDown-
# typed marker deep scan (Nosy Goblin's ``Destroy`` target, Etrata's
# granted-ability ``affected``, Kadena's face-down-ETB draw, Ixidron,
# Veiled Ascension, Tunnel Tipster, Cryptic Pursuit, Dream Chisel,
# Obscuring Aether, Primordial Mist, Found Footage, Keeper of the Lens,
# Panoptic Projektor, Lumbering Laundry), a ``manifestdread`` trigger
# event (Paranormal Analyst — CR 701.62, reactive to the ACTION, not
# the making of it), typed ``EnchantedIsFaceDown`` condition (Unable to
# Scream) and static ``mode == "CantBeTurnedFaceUp"`` (Karlov Watchdog),
# and a ``look``/``turn``-named ``Unimplemented`` residue read (Smoke
# Teller/Aven Soulgazer, Showstopping Surprise/Backslide, Exiled
# Doomsayer's morph-cost tax), plus a unit-scoped last-resort text hook
# (Qarsi Deceiver, Revealing Wind, Lens of Clarity, Spy Network,
# Illusionary Mask) gated by a maker-idiom exclusion regex (reminder-
# completion / "exile ... face-down pile" gambit / self ETB-parity
# rider / a bare "is turned face up" duplicate-decomposition fragment)
# — corpus-verified at the FULL commander-legal corpus (not just the
# 61) to guard against the batch-5 naive-port explosion (3→126
# cw_only); this port's corpus cw_only is 11 (3 pre-existing baseline
# anomalies — Fear of Impostors/Unwanted Remake/Unidentified Hovership,
# the ManifestDread-on-OPPONENT arm, unrelated to this batch — plus 8
# genuine beyond-legacy gains: Primal Whisperer's face-down-creature
# count, Cyber Conversion/Illithid Harvester's "turn X face down"
# removal the legacy regex allowlist never covered, Creeping Peeper/
# Overgrown Zealot/Tin Street Gossip's mana restrictions, Oblivious
# Bookworm's broad condition). live_only == exactly the 33-card shed
# set IS the 0-genuine-lost gate.
#
# ADR-0038 W3 batch 6 (combat-trio): ``combat_damage_matters`` and
# ``combat_damage_to_opp`` PROMOTED (0 genuine members lost vs a live
# corpus re-measure — 28/27 live_only -> 0/0). A whole-face text
# fallback (:func:`~mtg_utils._card_ir.supplement.
# combat_damage_recipients_from_text`, reused verbatim, single-source
# from the OLD projection's own synthetic ``combat_damage`` trigger
# recovery) closes the bare-quoted-grant / replacement / passive-
# reference tail (Predators' Hour, Sokrates, Steel Hellkite, the
# Unfinity Sticker Sheet TK-templates, the Optimus Prime DFC face) for
# BOTH lanes; ``combat_damage_to_opp`` additionally gains a LOW-
# confidence double-strike-grant mirror (Raphael, Blade Historian,
# Berserkers' Onslaught — CR 510.1b/510.1c/510.2/615.
# ``creature_ping`` PROMOTED (0 genuine members lost — 36 -> 0
# live_only): the anchor widened from ``DealDamage``-only to also read
# ``DamageAll``/``DamageEachPlayer`` (both already decorate as the
# ``deal_damage`` concept, only the lane's own per-node tag filter
# excluded them — Waltz of Rage, Heartfire Hero), a deep
# ``iter_typed_nodes`` walk reaches a granted ability's OWN buried
# DealDamage/DamageAll (Burning Anger, Brawl), a strict "power to
# target creature" recipient-text confirm recovers a ParentTarget
# back-reference recipient when the doer's power comes from a
# DIFFERENT object (Lie in Wait, Dead Reckoning), and the Multiply
# anchor admits an ``EventContextAmount`` inner qty (Cut Propulsion's
# anaphoric "twice that much"), all CR 120.3. Three adjudicated GAINS
# (Osseous Sticktwister, Storm Queen of Wakanda, Lukka's ultimate
# emblem) join the already-ported Delirium precedent — legacy's own
# oracle-fallback regex is narrower than the structural read in each
# case (a pronoun, an "any target" tail, a qualifying relative clause),
# not a principled exclusion.
#
# ADR-0038 W4 giant-key batch: ``creatures_matter`` STAYS residual —
# substantial recall gain (a live corpus re-measure: both 603 -> 1193,
# live_only 3184 -> 2594, no new cw_only over-fires beyond the existing
# pre-batch predicate-blind-filter anomaly class), but the gate is NOT
# met — the tail doesn't decompose into a small adjudicated set. The
# ``_creatures_matter`` arm widened from 2 shapes to 5, all sharing the
# SAME ``_is_generic_creature_filter`` gate: (1) a ``Multiply``-scaled or
# ``Mana``-nested count operand (Peach Garden Oath, Circle of Dreams
# Druid/Battle Hymn — CR 107.3), (2) a scaling ``Pump``/``PumpAll``'s
# ``power``/``toughness`` Ref site (Might of the Masses, CR 107.3), (3)
# a whole-unit ``iter_static_defs`` descent so a ONE-SHOT
# ``GenericEffect``-nested or ``CreateEmblem``-nested static def fires
# the team-anthem arm same as a static-origin unit (Overrun, Capitoline
# Triad, Call for Unity's scaling ``AddDynamicPower``/
# ``AddDynamicToughness`` — CR 611.2c/613.4c), (4)
# ``GrantAbility``/``GrantTrigger`` mod tags joining ``AddKeyword`` in
# the same arm (Lightning Volley, Kira, Phenax — CR 113.10), (5) a plain
# top-level ``PumpAll`` role=effect with no nested static def at all
# (Warrior's Honor, Fortify — CR 611.2c/613.4c). ~590 corpus cards
# recovered this batch (all 5 arms pinned in ``test_crosswalk.py`` —
# ``test_creatures_matter_w4_giant_batch``). The GIANT remaining tail
# (~2594 live_only) decomposes into: (a) ~2160 the pre-existing
# docstring already names and this batch corpus-reconfirmed — legacy's
# LOW regex floor fires on ANY creature-token maker (Siege-Gang
# Commander, Mobilization) purely because the oracle text mentions
# "creature token", not a structural cares-about read (negative-pinned:
# Siege-Gang Commander) — deliberately NOT ported; (b) a genuinely
# diverse ~430-card tail spanning MANY small, structurally UNRELATED
# shapes that would each need its own arm + corpus verification: Devour
# ETB counters (Bloodspore Thrinax, ~20), Rampage/"blocked by" combat
# counts (Craw Giant, ~24 — different SUBJECT, "creatures blocking it"
# not "creatures you control", negative-pinned), symmetric "on the
# battlefield" any-controller counts (Blasphemous Act, Coat of Arms,
# ~10 — fails the "You" gate by design, negative-pinned), named-card
# self-counts (Relentless Rats, ~15), "greatest power among creatures
# you control" Aggregate/Max reads (Rishkar's Expertise, ~21 —
# structurally a MAX function, not an ObjectCount, needs its own
# operand-extraction arm), attacking-creature counts (Klauth, ~35 —
# different subject again), conditional gates ("if you control a
# creature with power 5+", Chronicler of Heroes, ~24 — a boolean
# Condition node, not a count/anthem shape at all), and a genuinely
# heterogeneous ~284-card residue (subtype/face-down/color-restricted
# anthems correctly excluded by the no-subtype-or-predicate gate,
# single-target aura token-granters, generic "untap all creatures you
# control" one-shot effects with no P/T/keyword modification at all,
# …). No single mechanism closes (b) — banking the recall gain per
# ADR-0038 step 5 rather than force-fitting a promotion.
#
# ADR-0039 W7 BRIDGES wave (2026-07-11): ``creatures_matter`` STAYS
# residual — a live corpus re-measure gives the FIRST exact,
# mechanistically-derived bucket accounting of the whole live_only
# set (a per-card classifier walking the SAME node fields the arms
# read, not approximate counts): both 1262 -> 1390 (+128 genuine
# recall), live_only 2532 -> 2404, cw_only 30 -> 154 (every new hit
# spot-verified genuine — the predicate-agnostic condition-gate
# philosophy already established for the artifacts_matter/
# enchantments_matter siblings, e.g. Colossal Majesty's "draw a card
# if you control a creature with power 4+", CR 603.4). Four new
# closing mechanisms, all CR-grounded and pinned
# (``test_creatures_matter_w7_bridges_batch``):
#
# (1) a CONDITION-gate arbitrary-payoff arm
# (:func:`_creatures_matter_condition_filter`) — an existence/
# threshold Condition wrapping an UNRELATED effect over the generic
# population (Chronicler of Heroes, the Ferocious ability word, Epic
# Struggle's "20 or more creatures, you win" — CR 603.4/608.2b),
# EXCLUDING a cost-reduction's own condition (``static_mode_tag ==
# "ModifyCost"`` — Avatar of Might/Synchronized Eviction/Arwen's
# Gift/Orysa's "costs {N} less" gate, CR 601.2f — the W6 boundary
# worry this arm resolves) and a Soulbond ``Unpaired`` predicate
# (Nearheath Pilgrim's ETB pairing check, CR 702.95b — keyword-
# mechanic bookkeeping for ONE partner, not a population care).
# (2) a deep static-def descent
# (:func:`_iter_creatures_matter_static_defs`, a lane-local STRICT
# SUPERSET of :func:`iter_static_defs` additionally following
# ``modifications``/``definition``/``trigger`` — a team anthem buried
# inside a modification's OWN granted trigger/ability body, Centaur
# Chieftain / Teroh's Vanguard / Angelic Skirmisher / Garruk Savage
# Herald / Dragon Throne of Tarkir / Tenth District Hero) plus two
# widened mod tags (``AddChosenKeyword``, ``GrantStaticAbility`` — CR
# 113.10) and four more (``AddType``/``AddSubtype``/
# ``AddAllCreatureTypes``/``AssignDamageFromToughness`` — CR 613.4d /
# 510.1c, each verified as the card's OWN static, never granted into
# an opponent-controlled token where "You" resolves to the WRONG
# controller — Goblin Spymaster / Pursued Whale's MustAttack mode is
# exactly that trap and is deliberately NOT added).
# (3) a team EVASION/UNTAP-PERMISSION static MODE
# (:data:`_CREATURES_MATTER_EVASION_MODES` — CantBeBlocked family +
# UntapsDuringEachOtherPlayersUntapStep, CR 113.12/502/611.1 — Keeper
# of Keys, Drumbellower, Dread Charge).
# (4) :func:`_pump_scaling_creature_filter` widened to accept an
# ``Aggregate`` qty alongside ``ObjectCount`` — a created TOKEN's
# scaling power/toughness site (Miming Slime's "X/X token, X = the
# greatest power among creatures you control" — CR 208.1), the sole
# caller so the widening needs no sibling corpus check.
#
# TWO CORRECTNESS FIXES to the shared :func:`_is_generic_creature_filter`
# gate itself (affecting every caller — type_matters go-wide included,
# a pure improvement, never a widening): an explicit non-Battlefield
# ``InZone`` predicate now fails the gate (Wire Surgeons' "each
# artifact creature card in your GRAVEYARD has encore" was a false
# positive the deep descent's wider reach first surfaced — CR 400.2;
# an explicit ``InZone: Battlefield`` — Chronicler of Heroes' own
# counter-predicate filter states it explicitly — still passes), and a
# ``SharesQuality`` predicate now fails the gate (Haunted One's
# granted "other creatures you control that SHARE A CREATURE TYPE
# with it" is a TRIBAL restriction phase encodes as a predicate, not
# a ``Subtype`` type_filters entry — CR 205.3, type_matters
# territory).
#
# The exact live_only=2404 decomposition (a per-card mechanistic
# classifier, not estimates): 2131 the PRE-EXISTING token-maker LOW
# regex floor (Siege-Gang Commander, already negative-pinned); 162 a
# genuinely heterogeneous residue of many small, structurally
# UNRELATED shapes (subtype anthems correctly excluded by the
# no-subtype gate — Karrthus; single-target aura/equip grants;
# generic "untap all" with no P/T/keyword mod; Rampage/board-count
# shapes the pre-existing shed classes already cover under different
# node paths than this session's diagnostic script checked); 32 a
# "creatures BLOCKING it"/"creatures attacking you" count (Rampage,
# Craw Giant, already negative-pinned, CR 509.1h); 22 Devour's
# sacrifice count (Bloodspore Thrinax, already negative-pinned, CR
# 702.82a); 20 a symmetric any-controller "on the battlefield" count
# (Blasphemous Act, already negative-pinned); 6 the legendary-
# creature-count-SCALED cost reduction shape at a non-Condition site
# (Boseiju/Eiganjo/Otawara/Sokenzan/Takenuma/Mirror of Galadriel —
# the SAME CR 601.2f exclusion as arm (1)'s cost-reduction guard, just
# reached via a ``S_cost_reduction`` count field rather than a
# Condition site, deliberately NOT closed by a blind count-operand
# deep scan — that would reopen the SAME cost-reduction contamination
# risk arm (1) was built to avoid); 2 a self-referential named-copy
# CDA (Relentless Rats — CR 613.4b, the Towering Gibbon precedent); 1
# a tribal SharesQuality grant (Haunted One, now correctly excluded
# by the gate fix above); 2 an opponent-token-scope MustAttack grant
# (Goblin Spymaster/Pursued Whale); 1 a graveyard-zone care (Kathril,
# Aspect Warper, now correctly excluded); ~26 more single-card shapes
# in the ``other_filter`` tail needing their own dedicated arm
# (Mana Echoes, Crypt of Agadeem, Carrion Grub, Audience with
# Trostani, We Ride at Dawn, …). No single further mechanism closes
# the residue — banking this session's substantial recall gain and
# two shared-gate correctness fixes rather than force-fitting a
# promotion past a still-genuine, still-diverse tail.
#
# ADR-0038 W4 giant-key batch: ``plus_one_matters`` STAYS residual —
# substantial recall gain (a live corpus re-measure: both 118 -> 296,
# live_only 485 -> 307, cw_only 2 -> 23, all 23 corpus-verified genuine
# beyond-legacy gains — Battlefront Krushok / Thoughtbound Phantasm /
# a DFC front-face RemoveCounter cost / Skyclave Sentinel's second-clause
# payoff / the Unleash CantBlock idiom, each a real legacy structured-
# parse gap, not a crosswalk over-fire), but the gate is NOT met — the
# tail doesn't decompose into a small adjudicated set. Five new arms
# mirror ``_any_counter_matters``'s whole-unit descents gated to P1P1
# instead of Any (:func:`_plus_one_matters`'s own docstring — CR 122.1):
# a mass STATIC ``affected`` filter (Outlast tribal anthems), a
# counter-HAVE TRIGGER's ``valid_card`` filter (Marchesa the Black Rose),
# a nested ``iter_static_defs`` conferred-grant descent, a ``HasCounters``
# whole-unit static CONDITION (Lightwalker's self-referencing "as long as
# it has a +1/+1 counter" idiom, CR 604.2), and a P1P1-kind
# ``RemoveCounter`` activation COST (Triskelion/Walking Ballista's
# counter-sink outlet, CR 118.7). :func:`trigger_counter_filter`
# (``_card_ir/crosswalk.py``) is ALSO widened to read a THRESHOLD-less
# ``counter_filter``'s ``MirrorVariant`` collapse (Fathom Mage / Enduring
# Scalelord / Knighted Myr — a mirror-runtime loading artifact, not a
# new grammar arm). Two DISTINCT legacy over-fire mechanisms are
# deliberately NOT reproduced (both corpus-verified noise, not a
# genuine +1/+1-specific cares-about read — see the docstring's "NOT
# ported" section): (1) legacy's ``_PAYOFF_TRIGGER_KEYS["counter_added"]``
# row fires UNCONDITIONALLY on every ``counter_added`` trigger with no
# kind gate (~249 raw live_only — 171 Saga lore-counter chapters + 74
# M1M1/kindless kind-agnostic triggers + 4 more via (2)); (2) legacy's
# per-ability ``project._narrow_counter_refs`` regex carries a
# kind-agnostic "with/has a counter on it" alternative that double-tags
# cards the esub arm already correctly routes to any_counter_matters
# (The Swarmlord, Cleopatra Exiled Pharaoh, Puca's Covenant, Metropolis
# Angel). The remaining ~58-card tail is genuinely diverse (an
# ``Unknown``-tagged ``sub_ability`` idiom for "if X has a counter, do Y
# instead" — Bring Low; a condition phase drops entirely inside a
# ``GenericEffect`` wrapper — Dual-Sun Technique; a deeply-nested
# ``ModifyCost``/``spell_filter``/``Targets`` cost-reduction shape —
# Titanic Brawl; CDA "power greater than its base power" text idioms
# with no counter node at all — Baird, Kutzil, Ms. Marvel) — each would
# need its own arm + corpus verification. Banking the recall gain per
# ADR-0038 step 5 rather than force-fitting a promotion.
#
# ADR-0038 W4 giant session (enchantments_matter): a large residual gap
# (40 live_only vs 3840 both) collapsed to 6 (both 3874) via four
# structural fixes, all corpus-verified: (1) an Aura-SUBTYPE recursion
# fallback on the three graveyard-recursion arms (:func:`
# _type_recursion_lanes`, CR 205.3/303.4 — "return target Aura card"
# carries no Enchantment core type); (2) an And/Or condition-leaf
# descent (:func:`_condition_leaves`, CR 603.4 — "if you control an
# artifact AND an enchantment" types as one compound condition wrapping
# two leaf checks); (3) the ``_ENCHANTMENTS_MATTER_MIRROR`` byte-mirror
# port (the enchantment sibling of the already-ported
# ``_ARTIFACTS_MATTER_MIRROR``, never previously wired in); (4) an
# AFFINITY-FOR-ENCHANTMENTS keyword-line check (the enchantment sibling
# of the existing AFFINITY-FOR-EQUIPMENT arm). The remaining 6:
# 4 "each player/opponent sacrifices an enchantment of their choice"
# EDICTS (Gaius van Baelsar, Pick Your Poison, Simplify, Catch //
# Release — CR 701.21a, the same shape ``_sac_is_edict`` already
# rejects) and 1 symmetric library-position reset (Harmonic
# Convergence's "put all enchantments on top of their owners'
# libraries" — CR 205.2, no ``controller: You`` gate) are ADJUDICATED
# SHEDS (mandatory negative pins added), not genuine recall. The 6th —
# Smoke Spirits' Aid's "For each of up to X target creatures, create a
# red Aura enchantment token …" — is a GENUINE gap phase parses as a
# residue ``Unimplemented`` node (the "for each … create" wrapper);
# recovering it needs either ``clause_grammar.py`` growth (forbidden
# this session) or a ``make_token`` recovery-ALLOWLIST entry, which is
# a corpus-wide shared-helper widening (affects every lane reading the
# ``make_token`` concept, not just this one) too broad to verify safely
# for a single card this session. Banking the recall gain per ADR-0038
# step 5 rather than force-fitting a promotion.
#
# ADR-0038 post-giants main-session batch: ``enchantments_matter``
# PROMOTED — the orchestrating session added exactly that
# ``make_token`` ALLOWLIST row with the full-corpus verification the
# giant agent asked for (blast radius: 38 recovered nodes, 2 changed
# cards corpus-wide before the lane branch — Tobias/Soul of
# Emancipation, both adjudicated genuine — plus the recovered-node
# raw-read branch in _artifacts_enchantments_matter, CR 701.7/111.2/
# 205.3g rules-lookup-verified). Smoke Spirits' Aid recovered + pinned;
# final live_only == exactly the five adjudicated, negative-pinned
# sheds (Gaius/Pick Your Poison/Simplify/Catch // Release edicts +
# Harmonic Convergence symmetric reset) — the landfall gate rule.
# artifacts_matter also gained (Circuits Act, Yawgmoth Merfolk Soul —
# its tail is now 8) but keeps its genuinely diverse residual.
#
# ADR-0038 post-giants main-session batch: ``discard_outlet`` PROMOTED
# — the giants agent's ONLY remaining class (the period-split "Then
# discard a card unless <cond>" tail, 5 cards) is recovered by the
# "discard" ALLOWLIST row; the lane's recovered-node DIRECTION gate
# (``_RECOVERED_OPP_DISCARD_RE``, a raw reject-list) keeps the
# opponent-directed / protection residues out (Nebuchadnezzar's
# subject-truncated imperative, Bladecoil's "each opponent", Tamiyo's
# "can't cause you to"), negative-pinned. Final live_only=0; the
# recovered path's four genuine additions (Breakthrough, Circling
# Vultures, Noxious Vapors' symmetric wheel, Azra's team loot) ride
# the already-adjudicated cw_only gain classes. Free rider:
# opponent_discard's gap fell 77→33 (recovered opponent-directed
# discards now reach its own arm) — banked, key stays residual.
#
# ADR-0038 W5 tails (2026-07-11): ``artifacts_matter`` NOT YET
# PROMOTED — corpus re-measure 5006 both / 4 live_only (down from 8).
# Four structural/local-read fixes: a BATTLEFIELD-sourced library-
# bounce (Rebuking Ceremony, CR 401.4, distinct from the existing GY-
# recursion arm's CR 400.7); ``SearchOutsideGame`` (the Wish idiom, CR
# 108.3) read LOCALLY by its own typed tag (never routed through the
# shared ``tutor`` CONCEPT_MAP — that would incorrectly open the
# dedicated tutor lane for every Wish card too); a ``ChooseOneOf``-
# wrapped sac (Nimble Hobbit's "sacrifice a Food or pay {2}{W}" —
# ``_walk_effect_chain`` collapses the whole modal branch to one
# opaque concept, so a deep scan finds the Sacrifice inside directly);
# a ``become_copy`` type-restricted target read (Spirit of
# Resilience's "become a copy of an artifact or creature card", CR
# 707 — an ordinary Clone's bare Creature-only target stays silent by
# construction). Two cards ADJUDICATED AS SHEDS this batch (negative-
# pinned): Catch // Release's "Release" half and Braids, Cabal
# Minion's upkeep trigger are SYMMETRIC EDICTS (CR 701.21a — every
# player sacrifices their OWN choice, not a fodder outlet), the exact
# same class the enchantments_matter sibling already sheds for the
# first of these two cards. The remaining 2 live_only are GENUINE
# unclosed gaps, not sheds: Bello, Bard of the Brambles is a
# confirmed phase STATIC-PARSER FAILURE (its whole ability parks as
# an ``Unimplemented`` node named "static_structure" with a "Static
# pattern matched but line failed static parser" diagnostic — no
# residue to recover from, needs upstream phase work); Dargo, the
# Shipwrecker's "As an additional cost to cast this spell, you may
# sacrifice any number of artifacts and/or creatures" is a genuine
# ``build_concept_tree`` root-cause bug — ``_spell_additional_cost_
# concepts`` computes the Sacrifice cost concept correctly but the
# merge loop only attaches it to an EXISTING Spell-kind ``S_abilities``
# entry, and Dargo has NONE (its only ability is a Static cost-
# reduction rider) — so the additional_cost is silently dropped for
# any card with this exact shape. 241-card corpus census (every
# commander-legal card with a root additional_cost and no Spell-kind
# ability) confirms this is NOT Dargo-specific, but fixing it means
# synthesizing a carrier AbilityUnit for build_concept_tree itself — a
# foundational, corpus-wide crosswalk.py change needing the SAME full
# ALL-KEY diff rigor as a recovery ALLOWLIST row, which this batch's
# time budget didn't cover. Landfall rule not met (2 genuine gaps
# remain, not sheds) — key stays residual.
#
# ADR-0038 W5 tails (2026-07-11): ``base_pt_set`` NOT YET PROMOTED —
# 218 both / 13 live_only (down from 20) via a deep GenericEffect/
# CreateEmblem descent, a ``TriggeringSource`` accept-list addition,
# and a matched-quantity narrowing of the copy-stats exclusion; see
# :func:`_base_pt_set`'s own docstring for the full mechanism list and
# the still-residual 13-card tail.
#
# ADR-0038 W5 tails (2026-07-11): ``draw_for_each`` NOT YET PROMOTED —
# 210 both / 3 live_only (down from 16) via a reversed-order phrase
# alternative (object-gated to exclude a back-reference false match)
# plus a ``CreateDelayedTrigger``/``Vote`` per-choice descent; see
# :func:`_draw_for_each`'s own docstring for the full mechanism list
# and the still-residual 3-card tail (all genuine gaps, no sheds).
#
# ADR-0038 W5 tails (2026-07-11): opponent_discard NOT YET PROMOTED —
# re-measured at 77 live_only (the 33 estimate in the prior note was
# the giants agent's own-arm PREDICTION, not a re-measurement; this
# session's actual number at fresh HEAD was 77). ONE structural gap
# closed: a discard buried under a ``GrantAbility.definition``
# (Mindlash Sliver) or a ``Vote`` ``per_choice_effect`` branch
# (Capital Punishment, Sail into the West) is not on the unit's own
# direct effect chain, so ``effect_concepts`` never reached it —
# :func:`iter_typed_nodes`'s deep walk now finds the buried node, and
# its DIRECT wrapper's own ``player_scope`` resolves via the new
# lane-local :func:`_nested_owner_player_scope` (CR 613.1f/701.38 —
# kept lane-local rather than widening the shared
# ``effect_owner_player_scope``, which backs discard_outlet/
# group_hug_draw/opponent_cast_matters too). A dual "each"+"opponents"
# emission for a symmetric wheel was TRIED and REVERTED: it broke the
# pre-existing adjudicated ``test_opponent_discard_wheel_wrapper_
# is_each`` pin, which already decided the legacy kept-mirror's
# redundant "opponents" duplicate for an "each"-scoped wheel is a
# MIRROR OVER-FIRE, not a second genuine signal (``spec_for``'s
# (key)-only fallback already resolves an ``each``-scoped signal to
# the ``("opponent_discard","opponents")`` spec, so the "invisible to
# every consumer" premise for dual-emitting was false) — see the
# GRADUATION RULE, never suppress an existing correct pin.
#
# live_only fell 77→68 with the GrantAbility/Vote descent fix alone.
# Of the 68, ~44 are THIS SAME already-adjudicated wheel-mirror-
# duplicate shed (Wheel of Fortune, Dark Deal, Mindslicer, Windfall,
# Magus of the Wheel, Memory Jar, Magus of the Jar, Reforge the Soul,
# Liliana of the Veil, Rankle, … — every "each player discards"
# wheel legacy's kept mirror ALSO tags "opponents" for). FIVE more
# are the Cephalid-Looter loot shape (:func:`_is_target_player_loot`)
# — Compulsive Research (already pinned pre-session) / Laquatus's
# Creativity / Steal the Show / Collective Defiance / Lumengrid Augur
# all have a discard AND a sibling draw naming the SAME single
# targeted player; legacy's inclusion of 4 of the 5 (never Cephalid
# Looter/Broker themselves, which the SAME veto correctly excludes in
# legacy too) is driven by incidental "that player discards"
# REGEX-MIRROR phrasing adjacency, not a principled distinction — CR
# 701.9/701.8a, negative-pinned (Laquatus's Creativity this session).
# The remaining ~19 are GENUINELY diverse, un-closed structural gaps:
# damage-CONNECT specters with no Discard node at all (Fungal
# Shambler, Bladecoil Serpent); a delayed-trigger wheel whose
# CreateDelayedTrigger wrapper carries no player_scope of its own
# (Memory Jar / Magus of the Jar's OWN discard, distinct from their
# both-matching "each player exiles..." ChangeZoneAll arm); a
# REPLACEMENT effect chain (Words of Waste, Breathstealer's Crypt); a
# reveal-then-discard back-reference (Nebuchadnezzar, Dementia
# Sliver); a past-tense "discarded this turn" punisher condition
# (Tinybones); a ``Choose(choice_type='Opponent')`` value pick
# disconnected from the later Discard's mis-tagged ``Controller``
# target (Fervent Mastery); two empty-text Aftermath DFC records
# (Consign // Oblivion, Driven // Despair); plus Jagged Poppet/Hint
# of Insanity/Tainted Specter/Yawgmoth Merfolk Soul/Remorseless
# Punishment/Mindculling/Azula, each its own shape — banked, not
# force-fit this session. Key stays residual.
# ADR-0039 bridge phase (2026-07-11): ``artifacts_matter`` PROMOTED —
# the two W5-tails genuine gaps closed by the two pattern-setting
# mechanisms of the bridge phase: (1) Dargo, the Shipwrecker via the
# ``build_concept_tree`` additional-cost CARRIER fix (a root
# ``additional_cost`` with no Spell-kind ability entry was silently
# dropped; the synthesized carrier unit fixed 17 cards corpus-wide,
# all pure gains — CR 601.2b); (2) Bello, Bard of the Brambles via
# the FIRST ledgered bridge (``bridge_ledger.BRIDGES[
# "bello_static_animate_artifacts"]`` — phase's static parser fails
# the whole animation line, upstream report candidate). Final
# live_only == exactly the two adjudicated, negative-pinned
# symmetric-edict sheds (Braids, Cabal Minion; Catch // Release —
# CR 701.21a): the landfall rule. both=5008 / cw_only=18 unchanged.
# base_pt_set PROMOTED (ADR-0039 W7 endgame, 2026-07-11) — landfall
# rule met: both 218 -> 231, live_only 13 -> 0, cw_only=13 unchanged
# (the pre-existing switch_pt beyond-legacy gains — CR 613.4d,
# documented in :func:`_base_pt_set`'s own docstring, unaffected).
# Three structural closers (crosswalk_signals.py): (1) a
# ``LastCreated`` resolved-tag accept (Ultron, Artificial
# Malevolence's created-token back-reference, CR 701.7a/608.2h);
# (2) an empty-nested-description fallback to the enclosing unit's
# own description (Displaced Dinosaurs' REPLACEMENT-origin static,
# CR 614.12); (3) :func:`_iter_base_pt_modal_threaded_statics`, a
# per-key modal ``mode_abilities`` threaded-target walk mirroring
# ``_iter_untap_targets``'s established pattern (Sauron, Dino
# Devotee's doubly-nested ``ParentTarget`` inside a modal mode's
# own sub-ability chain, CR 700.2). Seven ADR-0039 ledgered bridges
# (bridge_ledger.py) close the residual whole-clause-grammar and
# dropped-clause tail: ``base_pt_have_become_residue`` (Ambassador
# Blorpityblorpboop, Tanazir Quandrix, Unruly Krasis),
# ``base_pt_is_a_type_with_residue`` (Circle of the Moon Druid),
# ``base_pt_mass_where_x_residue`` (Candlekeep Inspiration),
# ``base_pt_tk_sticker_parse_failure`` (Cool Fluffy Loxodon),
# ``base_pt_each_equal_to_dropped`` (Captain Rex Nebula,
# Fractalize), ``base_pt_addpt_misattributed_typechange`` (Goddric,
# Cloaked Reveler — RETIRED at the v0.35.2 phase bump, structure
# landed upstream), ``base_pt_becomecopy_no_pt_override`` (Mindlink
# Mech — the standard "except it's 0/0 and has this ability"
# clone-shell idiom, Mimeoplasm, Revered One, is corpus-verified
# NOT a legacy member and stays excluded via a negative lookahead).
# CR 613.4b throughout. See :func:`_base_pt_set`'s own docstring
# for the full arm history.
# ADR-0039 task #82 grammar sprint (2026-07-12): three of those seven
# bridges — ``base_pt_have_become_residue``, ``base_pt_is_a_type_with_
# residue``, ``base_pt_mass_where_x_residue`` (plus the sibling
# ``candlekeep_inspiration_mass_where_x_creatures_matter`` and
# ``duskana_bess_base_pt_and_toughness_ref`` rows) — RETIRED into
# ``tree_synthesis.py`` arms (``_arm_base_pt_have_become``, ``_arm_
# base_pt_is_a_type_with``, ``_arm_base_pt_mass_where_x``, ``_arm_
# base_power_ref_conjunctive``); the regex reads moved from lane-embedded
# bridges into gap-gated tree-build-time synthesis, and ``_base_pt_set``/
# ``_base_power_matters``/``_creatures_matter`` now read the synthesized
# concept nodes structurally. Membership unchanged (same pins, same keys).
# cheat_into_play PROMOTED (ADR-0039 W7, 2026-07-12) — landfall
# rule met: live_only 40 -> 0 accounted for, every remaining
# live_only card is a TESTED, CR-grounded adjudicated shed (a
# land-only carve-out — CR 305.1, ramp not a cheat, joining Boreas
# Charger et al.; a name-match-only/bare-'Card' filter with ZERO
# type restriction — CR 201.1/205.1, never guess). Three
# structural closers in :func:`_cheat_into_play` (a ChooseOneOf
# branch descent for Dr. Eggman, a Condition else_ability descent
# for Impromptu Raid — both fields crosswalk.py's
# ``_EFFECT_CHILD_FIELDS`` never walks — and a reveal_until-sibling
# origin trust gated on ``enters_under: You`` for Telemin
# Performance) plus six ADR-0039 ledgered bridges
# (bridge_ledger.py: ``cheat_player_prefix_battlefield_put``,
# ``cheat_dropped_clause_zero_residue``,
# ``cheat_kept_destination_hand_misparse``,
# ``cheat_choose_from_among_graveyard_origin``,
# ``cheat_modal_mode_unsupported_qualifier``,
# ``cheat_synthetic_destiny_delayed_reveal`` — 20 cards, each
# anchored to its own verbatim clause/diagnostic-name residue, CR
# 601.2/110.4a for the "put onto the battlefield without casting"
# idiom itself). See :func:`_cheat_into_play`'s own docstring for
# the full W3-W7 arm history.
# creatures_matter PROMOTED (ADR-0039 W8 finisher, 2026-07-12) —
# landfall rule met: a live corpus re-measure gives both 1421 ->
# 1440, live_only 2373 -> 2354, cw_only=281 unchanged. A per-card
# node-path classifier bucketed the 2373 pre-session live_only
# set into six ADJUDICATED SHED classes (2320: TOKEN_MAKER_CROSS_
# OPEN 2120, SYMMETRIC_ANY_CONTROLLER 67, BLOCKING_OR_ATTACKING
# 61, SUBTYPE_TRIBAL_YOU 39, DEVOUR 17, TRIBAL_SHARESQUALITY 10,
# OPPONENT_SCOPE 4, NAMED_SELF 2 — all pre-adjudicated W4-W7, CR
# 111.1/111.2 token-maker floor / CR 509.1h blocking-attacking /
# CR 702.82a Devour / CR 205.3 tribal) plus a 53-card true-gap
# tail this session fully adjudicated per-card:
#
# SHED (39 of the 53, reinforcing pins added, no code change) —
# cost-reduction's OWN dynamic/scaled condition (CR 601.2f, the
# Avatar of Might boundary, 13 members: Arwen's Gift / Boseiju /
# Mirror of Galadriel / Orysa / Takenuma already pinned via the
# W7 condition-filter arm's ModifyCost guard; Ghalta / Khalni
# Hydra / Spectral Denial / Temur Battlecrier / The Pride of
# Hull Clade / Walking Skyscraper / Towashi Guide-Bot / Mobilized
# District newly corpus-confirmed the same shape, two pinned);
# self-CDA / self-only scaling (CR 604.3/613.4a-c, the Towering
# Gibbon precedent, 3 members: Ancient Ooze, Carrion Grub, Moon-
# Vigil Adherents — role=="static" ``affected: SelfRef``, never
# the generic team, one pinned); graveyard-zone population (CR
# 400.2, the Wire Surgeons/Kathril precedent: Crypt of Agadeem,
# pinned); chosen-type-restricted population (CR 205.3 tribal
# philosophy, contrast Rukarumel where the chosen type is
# GRANTED to a generic population rather than restricting what's
# COUNTED: Kindred Charge, pinned); already-adjudicated re-
# affirms (Divine Resilience / Fettergeist / Kathril, W7/W8
# pins, unaffected); TOKEN-MAKER CROSS-OPEN with a DROPPED/
# Unimplemented token node (18 members — legacy's floor fires on
# ITS OWN token-maker cross-open regardless of what our tree
# contains, CR 111.1/111.2, three pinned: Maestros Diabolist,
# Tobias Doomed Conqueror, Broken Visage).
#
# CLOSED (14 of the 53, all pinned) — a Formidable activation-
# restriction condition (CR 602.5 "can't begin to activate a
# prohibited ability"; CR 207.2c "Formidable" is an ability word
# with no independent rules meaning) via phase's OWN bespoke
# ``CreaturesYouControlTotalPowerAtLeast`` condition tag
# (:func:`_creatures_matter_formidable_condition`, 4 members:
# Atarka Beastbreaker, Circle of Elders, Dragon-Scarred Bear,
# Glade Watcher); two tiny typed container-descent reads — a
# FlipCoin win-branch DealDamage count operand
# (:func:`_creatures_matter_flip_coin_win_filter`, Goblin Lyre)
# and a reanimation target filter's nested Cmc-property count
# operand (:func:`_creatures_matter_cmc_property_count_filter`,
# Unforgiving One, CR 107.3 — genuinely typed data the crosswalk
# simply wasn't reading one field deeper, not a bridge); eight
# ADR-0039 ledgered bridges (bridge_ledger.py, creatures_matter
# section) for the residual grammar-straggler/dropped-clause/
# mis-scoped-grant idioms — Lightning Runner's absence-proof
# "untap all creatures you control" (CR 701.26), Superior
# Numbers' excess-count comparator, Sovereign Okinec Ahau's
# per-creature counter distribution, Whisperwood Elemental's
# face-up team-grant residue, Duskana's dropped per-base-2/2
# draw count (a separate row from the already-landed
# base_power_matters reference bridge — different key), Moku's
# mis-scoped SelfRef haste grant, Siege Behemoth's empty-
# modifications static, and Candlekeep Inspiration's mass base-
# P/T-setter residue (sharing its gap/match with the base_pt_set
# sibling row, CR 613.4b). See :func:`_creatures_matter`'s own
# docstring for the full W4-W8 arm history and
# ``test_creatures_matter_w8_finisher_batch`` for every pin.
# direct_damage PROMOTED (ADR-0039 W7 endgame, 2026-07-11) — the
# final 129 live_only closed: one real structural gain (Sin
# Prodder, the ``optional_for`` widening), one card reclassified
# into the PRE-EXISTING creature-only shed (Cruel Sadist — a
# legacy ``_DIRECT_DAMAGE_MIRROR`` regex over-fire, not a genuine
# gap), and fourteen ledgered bridges closing the rest (a compound
# "creature + that creature's controller" dropped-clause template
# plus eleven further singleton dropped-clause/upstream-parse-
# failure shapes plus a Devil-token quoted-grant pair plus a
# kicker-mode ParentTarget-reuse pair). See :func:`_direct_damage`'s
# own docstring for the full accounting and ``bridge_ledger.py``
# for each row's corpus census. CR 120.1/102.1/303.4c/702.33d
# verified this session.
# draw_for_each PROMOTED (ADR-0038 W6 endgame) — the final 2
# live_only closed this session: a card-level ``_kept(tree)``
# last-resort read for Vivien's Stampede's raw-text-free delayed
# trigger, and a RemoveCounter->Draw ``PreviousEffectAmount``
# positive gate for Nexus Mentality. See :func:`_draw_for_each`'s
# own docstring for the corpus history.
# exile_matters PROMOTED (ADR-0039 W7 endgame, 2026-07-12) —
# landfall met: both 73->81, live_only 10->2, and both remaining
# live_only cards (Rose Tyler, Amy Pond) are the adjudicated CR
# 702.62a Suspend-mechanic-reuse shed (the full 2-card population,
# not a sample). Two structural mechanism fixes: the RemoveCounter-
# from-an-exiled-card arm's Suspend-reuse gate is now the
# STRUCTURAL ``HasKeywordKind='Suspend'`` tell instead of the
# ``counter_type=='time'`` NAME proxy (Alaundo the Seer, a
# home-brewed "time counter" mechanic with no Suspend keyword
# property — a real gain, corpus-verified against every genuine
# Suspend RemoveCounter shape); an order-sensitive bare-
# ``TrackedSetSize``-after-exile-ChangeZone arm (Rysorian Badger,
# discriminated from Revival Experiment's reversed-order
# self-exile housekeeping by execution-chain position). Five
# ADR-0039 ledgered bridges close the rest
# (bridge_ledger.BRIDGES: exile_grant_all_activated_abilities
# [Mairsil, the Pretender; Rex, Cyber-Hound — the SAME "has all
# activated abilities of cards in exile with counters" idiom, a
# static_structure parse failure], grolnok_cast_from_exile_
# counter_pile, candlekeep_inspiration_exile_gy_pt_setter,
# close_encounter_warped_exile_additional_cost [zero-residue
# absence proof], kaya_emblem_cast_from_exile_drop). CR
# 406.1/113.10/601.2f/601.3/107.3/702.62a verified this session.
# graveyard_matters PROMOTED (ADR-0038 W6 endgame) — 31 live_only
# -> 0: a genuine ``ChooseFromZone`` GAIN (Dawnbreak Reclaimer)
# plus a single unified LEGACY OVER-FIRE shed thesis covering the
# rest (CR 404.1): legacy's ``_gy_scope`` resolves graveyard
# ownership from either the carrying effect's own recipient/actor
# SCOPE or a crude "opponent's/target player's graveyard" text
# regex applied over the WHOLE ability's raw — both imprecise
# proxies that over-fire whenever a SIBLING effect with no
# graveyard interaction of its own inherits the tag via
# raw-sharing (15 cards — Necromancer's Covenant, Klaw, Cathartic
# Parting, …), an effect's own recipient direction differs from
# the graveyard it actually references (Cavalier of Flame,
# Urborg Justice), or a bare/compound no-owner filter hits
# legacy's unconditional "else -> you" catchall the crosswalk's
# ``_gy_filter_scope`` correctly declines to guess (Keeper of the
# Cadence, matching the pre-existing Pulse of Murasa precedent) —
# plus the pre-existing 15-card MDFC Disturb-back-face scope
# quirk (documented functionally inert since 29d095dc). See
# :func:`_graveyard_matters`'s own docstring for the arm history.
# land_creatures_matter PROMOTED (ADR-0039 W7, 2026-07-12): both
# 104 -> 110, live_only 86 -> 0. Two structural closers (a mass
# animate static's ``affected`` controller admits TargetPlayer
# alongside You — Jolrael, Empress of Beasts, corpus-verified
# narrow; a self-recursion ChangeZone whose face-down profile
# carries the Land core type — Yedora, Grave Gardener's land-MAKING
# recursion, corpus-verified singleton) plus three ledgered bridges
# (bridge_ledger.BRIDGES: land_creatures_subtype_animate_dropped —
# Ambush Commander's subtype mass-animate, CR 305.3/305.7;
# land_creatures_dynamic_animate_dropped — Primal Adversary / Sage
# of the Maze's dynamic-count animate; land_creatures_condition_
# reference_dropped — Earth Rumble Wrestlers's condition-reference,
# CR 305/110.1) close 6 genuine gaps (ADR-0039 task #82 later retired
# the first two into typed ``tree_synthesis`` sweep arms — see this
# function's own docstring above for the current split). The
# remaining 80 corpus-
# decompose EXACTLY into eight adjudicated CR-grounded shed
# classes, all negative-pinned (verified via a full-corpus
# bucket-assignment script this session — every live_only card
# maps to precisely one class): manland self-animate + its
# Aura-granted Genju sibling (35 + 4 — land_protection-only, a
# utility land-into-creature isn't a build-around theme); a land
# TYPE/subtype change with no Creature type added (35 — CR 305.7);
# the STATIC reverse animator creatures→lands (1 — Ashaya; distinct
# from Yedora's one-shot land-MAKING recursion above, which fires);
# a SYMMETRIC/any-controller mass animate (1 — Natural Affinity, CR
# 613.1d); a REMOVAL spell merely NAMING a land creature (2); a
# disjunctive Land-or-Creature copy-target filter (1 — Relm's
# Sketching); an unrelated landfall-keyed self-type toggle that
# never itself has the Land type (1 — Hidden Stag).
# land_sacrifice_makers PROMOTED (ADR-0039 W7, 2026-07-12): both
# 118 -> 121, live_only 8 -> 5. Two pre-W6-flagged accessor fixes
# (:func:`_attack_requirement_land_sac` — Exalted Dragon's attack-
# requirement cost, CR 508.1d; :func:`_granted_land_sac_unless_pay`
# — Custody Battle's granted-trigger unless_pay, CR 601.2h) plus
# the Epicenter per-clause :func:`_in_condition_instead_branch`
# fix (CR 614.1 — a ConditionInstead replacement must not inherit
# a superseded sibling's opponent direction) close 3 live_only.
# The remaining 5 are ALL the SAME legacy-synthesis over-fire class
# (``supplement._recover_land_sacrifice``'s regex fires on a
# "sacrifice a land" substring regardless of true trigger-vs-cost
# position or true subject — CR 701.21/400.7): a land-DYING watcher
# with no "you control" restriction (Dingus Egg, Akki Raider,
# Centaur Vinecrasher), the PAYOFF-wording "whenever you sacrifice
# a land" (Scouring Swarm), and a MIXED "sacrifice a land or
# Lander" subject that's genuinely ``sacrifice_outlets`` territory
# (Larval Scoutlander).
# lifeloss_makers PROMOTED (ADR-0039 W7, 2026-07-11): both=1188,
# live_only == exactly four adjudicated CR-grounded shed classes
# (scope_mismatch ~51 — CR 119.3/603.2, legacy's own regex
# mis-scopes a no-recipient self-loss to /opponents, Agent Venom
# precedent; condition_reference ~46 — CR 603.4/603.2, "if X lost
# life this turn" is a triggering CONDITION scaling a DIFFERENT
# effect, Savage Gorger precedent, includes the Scriv Contract-
# token SequentialSibling raw-bleed singleton; LifeChanged watcher
# 2 — CR 603.2, a gain-OR-lose watcher trigger, never the card's
# own action; ramp_exclusion 2 — CR 118.8 painland shape,
# Lithoform Blight + Yavimaya Bloomsage // Channel). Closed via
# three new root-level cost-surface readers
# (_spell_additional_cost_concepts's PayLife carve-out,
# _spell_alt_cost_paylife_concepts for casting_options
# AlternativeCost, _keyword_cost_paylife_concepts for a keyword's
# own cost payload — all crosswalk.py), two narrow static
# accessors (_has_paylife_as_colored_mana, K'rrik;
# _has_defiler_cost_reduction, the Defiler cycle), a Spell-kind
# non-ramp-gate exemption (Phyrexian Scuta's cost-only carrier), a
# Ward-keyword exclusion (CR 702.21a — the TARGETING player pays,
# not the controller), a token-attach-opponent bleed guard (Scriv,
# the SequentialSibling raw-bleed family), and five ledgered
# bridges (bridge_ledger.BRIDGES: degavolver_kicker_paylife_regen,
# withercrown_unless_lose_life, keyword_dropped_paylife
# [Warp/Blitz/Morph], night_shift_optional_paylife_dieroll,
# zuko_modal_unconditional_paylife).
# opponent_discard PROMOTED (ADR-0039 W7, 2026-07-12) — landfall
# rule met: 471 both / 63 live_only == exactly the 3 pre-existing
# adjudicated shed classes (wheel-mirror-duplicate, Cephalid-
# Looter loot, past-tense-watcher/self-discard) plus 8 cards now
# closed via ledgered bridges (bridge_ledger.py:
# opp_discard_unless_clause, opp_discard_for_scaling_dominant_
# token, opp_discard_tk_sticker_parse_failure, opp_discard_words_
# of_waste_replacement_the_residue, opp_discard_fungal_shambler_
# dropped_conjunct, opp_discard_mindculling_dropped_conjunct,
# opp_discard_driven_despair_missing_face,
# opp_discard_jagged_poppet_combat_scaling). See
# :func:`_opponent_discard`'s own docstring for the full arm
# history.
# plus_one_matters PROMOTED (ADR-0039 W8, 2026-07-12): both 307 /
# live_only 296 unchanged from the W6 endgame re-measure (the key's
# own arms are untouched this wave) — the gate is met by closing
# the 6-card genuinely-unclosed tail instead: 5 ledgered bridges
# (bridge_ledger.py: plus_one_rock_hydra_static_parse_failure,
# plus_one_rumbling_ruin_count_unimplemented,
# plus_one_deepwood_denizen_cost_reduction_unimplemented,
# plus_one_hierophant_previouseffectamount_dropped_kind,
# plus_one_tetravus_removecounter_token_pair) plus one
# re-adjudication (Winged Hive Tyrant folds into the existing
# kind-mismatch shed class — its static-parse-failure residue text
# is kind-agnostic, no "+1/+1" anywhere on the card). Grammar sprint
# task #82 (2026-07-12) GRADUATED 3 of the 5: Rumbling Ruin /
# Deepwood Denizen off recovered-node arms (``clause_grammar``'s
# ``count_operand`` / ``counter_cost_reduction`` tokens +
# ``recovery.ALLOWLIST``) and Tetravus off a fully-typed
# RemoveCounter/Token pairing arm — all inline in
# :func:`_plus_one_matters` now, no bridge lookup. Rock Hydra and
# Hierophant Bio-Titan stay bridges (both need an upstream phase
# bump). See :func:`_plus_one_matters`'s own docstring for the full
# history.
# ramp PROMOTED (ADR-0039 W7, 2026-07-12): both 1636 -> 1668,
# live_only 32 -> 0, cw_only=3 unchanged (pre-existing "additional
# cost: sacrifice a land" cast-cost gains). Four structural closers
# (:func:`_ramp`'s own docstring): the granted-mana descent now
# reads a ``GrantTrigger`` body too and relaxes the
# ``is_mana_ability`` gate (Mark of Sakiko, Bigger on the Inside);
# :func:`_iter_returnasaura_mana_defs` reaches a ``ReturnAsAura``
# grant (Harold and Bob); :func:`_has_animate_treasure_grant` reads
# a Treasure-conversion static (Minimus Containment, CR
# 111.4/205.3g); a granted LAND-recipient Sacrifice-cost mana
# ability is acceleration regardless of produced shape (Rain of
# Filth). Two ledgered bridges close the residual "Add mana"
# clause-grammar tail (bridge_ledger.BRIDGES:
# ramp_grant_unimplemented_body — Katilda/Old-Growth Troll/Tazri's
# granted-ability-body Unimplemented; ramp_dropped_add_mana_clause
# — a 24-card name-keyed enumeration, each CR-verified this session
# against legacy's own independent classification).
# sacrifice_outlets PROMOTED (ADR-0039 W7, 2026-07-11) — landfall
# rule met: live_only 191 -> 166, and every remaining live_only
# card is a TESTED adjudicated shed (land_sacrifice_makers
# territory, the Grave-Pact edict-mislabel class, bare-self/
# subject-dropped, TargetPlayer/ScopedPlayer edicts, "any player"
# ambiguity — a corpus-wide predicate scan over ALL 166 confirmed
# zero unaccounted-for exclusions). Three closers: (1) the
# ``ParentTargetController`` you-outlet split
# (:func:`_sac_ptc_you_eligible` — 6 cards: Funeral March, Tainted
# Aether, Phyrexian Obliterator, Fade Away, Maarika Brutal
# Gladiator, Vengeful Strangler // Strangling Grasp; corpus-
# verified against all 16 commander-legal ParentTargetController
# Sacrifice-effect hits, the prior W6 deferral resolved rather
# than re-litigated blind); (2) two real structural reads — the
# Exploit keyword joining the Casualty/Bargain
# :data:`_SWEEP_KEYWORD_LANES` row (Silumgar Scavenger) and a
# created-token Devour read (:func:`_has_created_token_devour` —
# Dragon Broodmother's typed ``MirrorVariant(key='Devour')`` on
# the Token effect's own keywords list); (3) two ADR-0039 ledgered
# bridges for the residual NO-typed-Sacrifice-node bucket
# (bridge_ledger.py: ``sac_casualty_granted_onto_other_spell``,
# ``sac_emblem_activated_cost``). ADR-0039 task #82 grammar sprint
# graduated the other three OFF the ledger onto typed
# ``tree_synthesis`` marker-node reads (``sac_alt_cost_pitch`` /
# ``sac_keyword_cost`` / ``sac_etb_self_sac_unimplemented``), and
# Devour on the card's own body joined the Scryfall-keyword sweep
# alongside Casualty/Bargain/Exploit (formerly
# ``sac_devour_unimplemented``). See :func:`_sacrifice_outlets`'s
# own docstring for the full arm history.
# target_player_draws PROMOTED (ADR-0039 W7, 2026-07-12) —
# landfall rule met: 183 both / 70 live_only -> 0 genuine gaps.
# One real structural gain, a buried-grant Draw descent (Thief of
# Existence, mirrors opponent_discard's own iter_typed_nodes
# precedent). Two ADR-0039 ledgered bridges opened for the rest
# (Fatal Lore/Season of the Burrow/Ertai Resurrected/Balor,
# The Wedding of River Song); BOTH graduated off the ledger in the
# grammar sprint (task #82, 2026-07-12) onto structural/recovered-
# node reads. See :func:`_target_player_draws`'s own docstring for
# the full arm history.
# token_maker PROMOTED (ADR-0038 W6 endgame) — the 86-card
# live_only set is EXACTLY two adjudicated shed classes: the
# 85-card copy/Populate boundary (CR 707.1/111.2 — that's
# ``token_copy_makers``, a separate, already-promoted concept)
# plus Soul of Emancipation's multi-target "for each of those
# permanents, its controller creates ..." legacy scope-resolution
# bug (the SAME "unset-controller defaults to you" pattern
# already adjudicated elsewhere this wave — Pongify / Beast
# Within / Generous Gift's SINGLE-target case resolves the
# directed scope correctly in old_ir_for, confirmed via direct
# inspection; only the multi-target for-each idiom loses the
# per-permanent controller reference). See :func:`_token_maker`'s
# own docstring for the arm history.
# type_matters PROMOTED (ADR-0038 W5 tails) — see the crosswalk lane's
# own docstring for the corpus history + the fully-adjudicated shed
# class (the legacy _board_count_markers artifact).
# voltron_matters PROMOTED (ADR-0039 W7 endgame, 2026-07-12) —
# landfall met: both 2276->2281, live_only 81->76, and every
# remaining live_only card is one of three adjudicated shed
# classes: 64 commander-damage MEMBERSHIP-fallback (mandatory: Big
# Winner / Croakid Amphibonaut / Grabby Tabby / Scared Stiff + W6
# representatives, pinned) + 10 attach-action/housekeeping (Hammer
# of Nazahn, Battlefield Improvisation, Nahiri the Lithomancer,
# Unexpected Request, Armed and Armored, Super-Soldier Serum,
# Goldwardens' Gambit, Inventory Management, Resolute Strike,
# Benevolent Blessing) + 2 removal/theft-target (Soul Nova,
# Shackles of Treachery — CR 301.5c). The prior W6 5-card
# (7-in-comment) dropped-clause residual closes via three ADR-0039
# ledgered bridges (bridge_ledger.BRIDGES):
# ``voltron_attach_count_scaling_dropped`` (Judgment Bolt / Animal
# Friend / Sage's Reverie — the SAME "for each Aura/Equipment ...
# attached" / "where X is the number of Equipment you control"
# idiom, tightly anchored — NOT the legacy VOLTRON_PAYOFF_REGEX's
# bare "equipment you control" branch, which over-fires on
# Affinity-for-Equipment reminder text and attach-ACTION clauses),
# ``warchanter_skald_condition_dropped`` (a Taps-trigger's
# condition=None, the clause surviving only in ``description``),
# ``forge_anew_equip_cost_paycost_unlinked`` (an unlinked
# PayCost({0}); Bruenor Battlehammer's identical clause is served
# through its OWN structural ObjectCount arm before the bridge is
# ever reached). CR 301.5/303.4/107.3/601.2f/702.6c verified this
# session.

# Below this point: per-key promotion / recall-widening history for the keys
# ABOVE (the ``SERVED_SIGNAL_KEYS`` literal at the top of this region), continuing the
# historical record started by the "Historical per-key promotion record" block.
# ADR-0035 Stage-A (2026-07-09): the own-lifelink keyword row below recovers +325 of
# lifegain_makers' residual gap (corpus live_only 420 → 95), banked toward eventually
# promoting the key. lifegain_makers stays residual for now: the remaining ~95 are
# granted/nested gain-life sources (Ajani's loyalty ability, Animal Boneyard /
# Darkheart Sliver granted abilities) needing the granted-ability walk, plus a few
# opponent-lifegain over-fires.
# ADR-0035/0038 task #74 (2026-07-10): airbend_makers / earthbend_matters /
# waterbend_matters PROMOTED. They were corpus live_only=0 all along but blocked by a
# DFC face-drop bug, not a lane gap: ``_ir_lookup`` indexed only ONE phase record per
# oracle_id (first-record-wins), and Avatar Aang's cross-bend payoff (the
# ``RegisterBending`` / ``ElementalBend`` nodes these three lanes read) lives on the
# FRONT face ("Avatar Aang"), while phase's dict-key ordering ("aang, master of
# elements" < "avatar aang") put the back face first — silently dropping the front
# face's tree, and with it the only node these lanes had to read. ``trees_for`` now
# reads every face record per oracle_id and the hybrid unions their signals, so the
# front face's tree is read regardless of ordering. Fixing the READ (not a lane
# change) closes the gap; see ``_ir_lookup.trees_for`` for the mechanism.
# ADR-0038 W3 batch 4 (2026-07-10): clone_makers PROMOTED. The 7 remaining
# live_only members were ALL phase static-parser failures emitting no
# ``BecomeCopy`` node (Blade of Shared Souls / Essence of the Wild /
# Metamorphic Alteration / The Fourteenth Doctor / Vesuvan Shapeshifter —
# ``Unimplemented`` "static_structure"/"unknown" clauses; Ludevic,
# Necrogenius's transform back face has no BecomeCopy node anywhere). A
# bucket-B per-clause text-idiom bridge (CR 707.2/707.5, ``_clone_text_idiom``
# in :func:`_copy_clone`) reads the become-a-copy-of clause straight off the
# reminder-stripped face oracle when no structural node fired, gated against
# the token_copy_makers and land-copy false-positive classes. Corpus
# re-measure (2026-07): live_only 0/130, one adjudicated beyond-legacy gain
# (Dinosaur Headdress — a genuine CR 707.2 clone effect legacy's regex mirror
# never covered either).
# ADR-0038 W3 batch 4 (2026-07-10): any_counter_matters PROMOTED. The 8
# live_only members split into two structural gaps: (1) a counter-HAVE
# TRIGGER whose Counters predicate rides the trigger's own ``valid_card``
# filter, never an effect/static filter (The Swarmlord, Cleopatra, Puca's
# Covenant, Skyboon Evangelist, Metropolis Angel); (2) a PLAYER-counter scale
# (``PlayerCounter`` qty node, distinct from the permanent-scoped
# ``CountersOn``/``CountersOnObjects``) for Poison specifically (Mycosynth
# Fiend, Vishgraz) — gated to exclude Experience, which owns its own
# dedicated lane (experience_matters, ADR-0034); and a granted-token static
# def whose "for each <kind> counter" scale phase drops to a fixed P/T value
# two levels deep (Moira Brown, Guide Author), recovered via a bucket-B text
# idiom gated on ``count_operand_qty`` finding nothing (CR 122.1). Root-caused
# the 5 unrooted cw_only members this session: Cathedral Acolyte / Innkeeper's
# Talent / Iroh / Matt Murdock / Michelangelo's "each creature you control
# with a counter on it has/gains <keyword>" shape is a GrantStaticAbility the
# old IR's marker-synthesis simplifies to a bare ``Creature`` filter (dropping
# the Counters predicate) — legacy's regex fallback also never matches
# (requires the bare PLURAL "creatures you control gain/have" phrase with no
# intervening modifier clause). Adjudicated beyond-legacy gains, pinned.
# ADR-0038 W3 batch 4 (2026-07-10): second_spell_matters PROMOTED. The 34
# live_only members are ALL ADJUDICATED SHEDS — legacy's regex mirror
# (_SECOND_SPELL_MIRROR) carries a bare, unscoped "cast two or more spells"
# alternative that over-fires on the ~32-card Innistrad werewolf transform
# family ("if a player cast two or more spells LAST turn, transform this
# creature", CR 603.4 intervening-if + CR 712) plus Call of the Full Moon
# (same condition, already adjudicated batch 3) and Ertai's Scorn (opponent-
# scoped discount, already adjudicated batch 3) — none is a genuine spell-
# velocity build-around. The crosswalk excludes the werewolf class on TWO
# independent structural grounds (spell_velocity_static_two's qty-type gate
# requires SpellsCastThisTurn, not the werewolves' SpellsCastLastTurn; the
# node-text bridge requires "you cast" or an ordinal word, neither present in
# the werewolves' own description). Also widened the node-text bridge with a
# THIRD phrasing (CR 601) for a kind-agnostic, ANY-PLAYER ordinal count
# ("Whenever the fourth spell of a turn is cast" — Erayo, Soratami
# Ascendant) phase parses as a bare Unknown-mode trigger with no count
# qualifier — the SAME class the legacy IR's own byte-mirror fires for
# (pinned in test_signals_effect_axes.py::test_spell_count_storm_widen).
# ADR-0038 W3 batch 4 (2026-07-10): lifegain_makers PROMOTED (corpus
# live_only 95 → 0, ADR-0035 Stage-A's banked +325 recall now fully closed
# out). Two new structural arms plus one text-idiom bridge: (a) a GainLife
# effect buried ANYWHERE under a unit — a GrantTrigger/GrantAbility's own
# quoted definition, or the SAME grant a level deeper inside a created
# token's own static_abilities (the Pest-token family) — via one
# iter_typed_nodes deep walk (the has_nested_roll_die/has_nested_flip_coin/
# has_nested_fight precedent), gated on the found node's OWN player field
# (an explicit Opponent controller or "Another" property excluded); (b) a
# per-clause "you gain ... life" text-idiom bridge for cards phase's static
# parser drops entirely (Drain Life's capped formula, Soul Burn/Predator's
# Rapport/Discerning Taste's "life equal to ~" scalers, Necravolver's
# kicker-branched grant), itself gated against the ubiquitous "Whenever you
# gain life, <payoff>" lifegain_MATTERS trigger condition (a card that
# CARES about gaining life, never a source — Ajani's Pridemate, Sanguine
# Bond, ~65 more). The 8 remaining live_only members are ADJUDICATED SHEDS:
# legacy's OLD IR mis-projects every "target opponent gains N life" /
# "each OTHER player gains N life" effect's scope as "any" (a genuine
# scope-derivation bug in the retired project.py pipeline, verified this
# session), so its own scope-gate incorrectly admits an opponent-benefit
# drawback as a lifegain SOURCE; the crosswalk reads phase's ACTUAL
# structured player field and correctly excludes all of them. Two
# adjudicated beyond-legacy gains (Restorative Technique, Explore the
# Vastlands — genuinely "you"/symmetric-team benefits legacy's same scope
# bug drops). CR 119.3 verified via rules-lookup this session.
# ADR-0038 W4 giants (2026-07-11): type_matters banked a MAJOR gap reduction
# (corpus live_only 550 -> 176, both 18777 -> 19151) but stays residual — a
# genuinely diverse tail remains (Rampage self-buffs, mass-untap, MAX-operand
# scalers, sacrifice-a-<tribe> additional-cost filters, Formidable condition
# checks, nested GrantAbility.definition targets), each needing its own
# arm/adjudication pass this session's budget didn't cover. Two structural
# fixes, both reused by :func:`structural_type_subjects` (Arm B) AND the new
# :func:`_type_matters_go_wide` gate:
# (1) ``structural_type_subjects`` now reads :func:`iter_static_defs`
# instead of a bare ``unit.origin == "static"`` gate — a TRIGGER-conferred
# temporary anthem ("When you cycle this card, Wizard creatures gain flying
# until end of turn." — Gempalm Sorcerer) nests its Typed ``affected``
# filter on a static-ability DEF buried inside the trigger's own
# ``GenericEffect.static_abilities``, not on the trigger's own node; the
# decorated concept's anchor is the leaf modification (``AddKeyword``),
# which carries no filter field at all. A strict superset of the old gate
# (never a narrowing) — recovers Gempalm Sorcerer / Captain America,
# Unbowed / Kaito's Pursuit -class nested subtype references. CR 205.3.
# (2) the class-tribe MEMBERSHIP floor's go-wide gate is now
# :func:`_type_matters_go_wide`, not a bare ``out_keys`` intersection — the
# crosswalk's OWN ``creatures_matter``/``attack_matters``/``anthem_static``
# lanes are narrower than the deleted ``_signals_ir``'s go-wide breadth
# (``creatures_matter`` stays Stage-4 RESIDUAL, so its signals never reach
# ``out_keys`` at all — ``add()`` filters them by ``keys`` before they
# land). Three widened arms: a creature-type TOKEN MAKER cross-open
# (mirrors legacy's line ~11394 LOW arm — Krenko/Bear's Companion/Doomed
# Traveler-class, CR 111.2), a count-operand generic-filter scan (mirrors
# ``_creatures_matter``'s own first arm, unfiltered by ``keys``), and a
# pump/grant_keyword/set_pt static-DEF scan via ``iter_static_defs``
# (origin-agnostic, unlike ``_creatures_matter``'s ``unit.statics``-only
# scan — Balmor, Battlemage Captain/Selesnya Guildmage-class triggered/
# activated team anthems). Never changes what ``creatures_matter`` itself
# SERVES (still re-supplied from ``old_ir_for`` while residual) — a pure
# internal widening of the type_matters reconciliation's own go-wide test.
# CR 205.3/613.4. 0 regressions: full mtg-utils + deck-forge (all three
# MTG_SKILLS_CROSSWALK_SIGNALS states) suites green; +9 cw_only gains
# spot-verified as genuine CR 205.3 tribal reads (Sedris's own-type-line
# floor riding the graveyard-wide unearth grant, Grey Knight Paragon's
# conditional-exile Demon reference), no over-fire pattern found.
# ADR-0038 W5 tails (2026-07-11): type_matters PROMOTED. Corpus re-measure
# (176 -> 78 -> 0 genuine-gap live_only across this session's arms): five
# structural additions to :func:`structural_type_subjects` (Arm B) —
# ``unit.costs`` scanned the SAME way as ``unit.effects`` (a sacrifice-a-
# <tribe> ADDITIONAL COST — Goblin Grenade, Goblin Barrage, Fodder Launch,
# Devouring Greed/Rage, CR 601.2h/701.21), each static-def's own
# ``modifications`` list re-scanned for a nested COUNT-OPERAND filter
# (Bearded Axe's "for each Dwarf, Equipment, and/or Vehicle you control" —
# an ``Or``-of-subtypes on the leaf modification's ``value``, not the
# static's generic ``affected``), a ``ModifyCost`` static's own
# ``spell_filter`` (:func:`modify_cost_spell_filter`, reused verbatim from
# the ``typed_spellcast`` arm — The Destined Warrior's four-tribe cost
# reducer), and a ``GrantAbility.definition.effect`` descent (the SAME
# ``iter_typed_nodes`` idiom :func:`has_structural_power_tap_engine`
# already uses — Wolfhunter's Quiver's second granted ability's OWN
# target). Plus one new :func:`_type_matters_go_wide` arm: a combat
# KEYWORD tell (:data:`_TYPE_MATTERS_GOWIDE_KEYWORDS` — battle cry /
# battalion / melee / exert / bushido / annihilator / flanking / frenzy,
# each verified via rules-lookup this session) mirroring legacy's
# ``_IR_KEYWORD_MAP`` combat block, which routes the SAME keyword set to
# ``attack_matters`` — a vanilla-keyword body (Ahn-Crop Crasher, Glory-
# Bound Initiate, Sokenzan Spellblade) carries its attack condition in
# reminder text with no board-state Typed filter for any structural arm
# to read. A FIRST ATTEMPT at a sixth go-wide arm (a bare ``iter_typed_
# nodes`` scan for ANY generic creature-you filter anywhere in a unit)
# was REVERTED — corpus-verified to jump cw_only 267 -> 853 by matching
# ordinary SINGLE-TARGET filters ("target creature you control gains
# lifelink" — Alabaster Mage) that satisfy ``_is_generic_creature_filter``
# exactly as well as a genuine population count, since that gate checks
# only core-type/subtype/controller, never target-vs-population shape.
# The remaining 78 live_only members (post-fix) are ALL ADJUDICATED
# SHEDS, one homogeneous class, root-caused to source: legacy's old-IR
# ``_board_count_markers``/``_is_generic_board_filter`` (project.py)
# fabricates a synthetic "board_count" ability with a bare ``Filter
# (Creature, controller="you")`` for ANY own-board ``ObjectCount``/
# ``Aggregate`` operand phase's raw parse carries, and that helper's OWN
# docstring admits the imprecision: "controller you/unspecified passes"
# — so a REAL "creatures BLOCKING it" population (Rampage — CR 702.23;
# phase's actual structural filter carries ``BlockingSource`` with
# ``controller=None``, verified this session) or a REAL "creatures
# sacrificed to Devour" cost count (CR 702.82) gets mis-attributed as a
# "creatures you control" care regardless. This is the IDENTICAL "bare
# 'creature' mention count, not a structural cares-about read" floor
# :func:`_creatures_matter`'s own docstring already adjudicates as
# live_only / not-ported for the SAME reason — Formidable-style total-
# power conditions (Owlbear Shepherd, Surrak, Atarka Beastbreaker) and
# tapped-creature-count conditions (Frontline War-Rager, Sunstar
# Chaplain) verified this session to ride the IDENTICAL fabricated
# ability (their REAL structural ``ability.condition`` never reaches a
# bare-Creature-typed lane at all, per the deleted ``_signals_ir``'s line ~10476's own
# "skip the generic Creature/Permanent gates" comment). Negative-pinned
# (Elvish Berserker: Elf race tribe fires, Berserker class tribe does
# not). 0 regressions: full mtg-utils + deck-forge (all three
# MTG_SKILLS_CROSSWALK_SIGNALS states) suites green.
# ADR-0038 W4 giant (2026-07-11): topdeck_selection PROMOTED. Corpus
# re-measure: live_only 440 -> 4 (both 1136 -> 1572), all four ADJUDICATED
# SHEDS — genuine legacy ``old_ir_for`` false positives (Arjun, the
# Shifting Flame / Mindmoil's bottom-of-library wheel effect
# mis-classified by the retired pipeline's raw-regex category map; Winter,
# Cynical Opportunist's plain mill trigger caught only by the deleted SWEEP
# mirror's context-blind "put ... onto the battlefield" alternative
# matching its UNRELATED Delirium clause; Ecological Appreciation's
# tutor-and-reveal effect getting a stray zone tag with no "top" wording at
# all) — see :func:`_topdeck_selection`'s docstring for the full per-class
# breakdown and CR citations (verified via rules-lookup this session:
# 701.22a scry, 701.25a surveil, 701.20a reveal, 701.13a exile, 701.17
# mill, 701.40 manifest, 401.1 library-zone ownership, 401.5 look-at-top
# statics). Five widened/new arms beyond the pre-existing Scry/Surveil/
# Dig/RevealTop quartet: ``ExileTop`` (impulse-draw exile), ``RevealUntil``/
# ``ExileFromTopUntil`` (dig-until, via the existing
# :func:`reveal_until_player`), a ``MayLookAtTopOfLibrary`` static-mode arm
# (Bolas's Citadel, Elsha of the Infinite — a whole class legacy's regex
# never covered, since it requires "top card" with NO count word, a shape
# the deleted SWEEP pattern's grammar can't express), a structural
# mill-then-cheat-to-battlefield arm (Mill + TrackedSet/TrackedSetFiltered
# to Battlefield — gated STRICTLY on Battlefield, since the sibling
# "mill N, put a card from among them into your HAND" cantrip family,
# ~50 corpus cards, is corpus-verified to never fire in legacy at all), and
# a two-condition bucket-B text idiom (a selection verb + a top-of-library
# phrase, both anywhere in the same unit — never a single adjacency regex,
# mirroring legacy's own whole-ability raw-bleed C8 mechanism) that closes
# a whole "manifest the top card of your library" family and an
# "exile the top card(s) of your library: <effect>" activated-cost family
# phase's static parser drops into bare ``Unimplemented`` nodes. A new
# owner-boundary gate (:func:`_topdeck_owner_ok`, reusing
# ``supplement._TOPDECK_YOUR_LIBRARY``/``_TOPDECK_OTHER_ZONE`` verbatim,
# plus a local ``_TOPDECK_EACH_PLAYER_ZONE`` supplement for the
# "each player's library" symmetric-reveal shape those two constants'
# existing callers never needed) keeps the structural Dig/RevealTop/
# ExileTop arm from firing on an opponent-library dig whose ``player``
# field is structurally indistinguishable from a self dig (Gonti, Lord of
# Luxury; Selvala, Explorer Returned; Etali, Primal Storm). cw_only rose
# 52 -> 120, but this is overwhelmingly BEYOND-LEGACY RECALL, not
# over-fire: spot-verified via a per-card arm-attribution script, the vast
# majority are the same three new mechanism classes (MayLookAtTopOfLibrary,
# ExileTop/RevealTop activated-cost engines, the Manifest family) firing on
# genuine build-around staples the deleted SWEEP regex's narrower grammar
# never matched.
