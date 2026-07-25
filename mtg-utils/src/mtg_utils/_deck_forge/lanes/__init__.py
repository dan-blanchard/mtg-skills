"""Layer-3 ``Signal`` lanes derived from the Layer-2 concept overlay (ADR-0035).

THE production serving path (ADR-0039 task #80 step 6):
``signals.extract_signals`` runs ``extract_crosswalk_signals`` over each
of a card's per-face concept trees (``_card_ir.crosswalk.ConceptTree``) and
unions the results — no regex or projected-Card path backs it up anymore. Each
lane emits the frozen ``Signal(key, scope, subject)`` contract from typed reads
wherever the substrate carries the datum; the remaining oracle-text reads are
enumerated and gap-gated (the ledgered bridges of ``bridge_ledger`` plus a small
kept-mirror tier), awaiting the post-deletion grammar sprint.

``SERVED_SIGNAL_KEYS`` (``manifest.py``) is the served-key set. The per-key comments
throughout this package are the migration's adjudication record — shed/gain verdicts and
corpus measurements taken against the now-deleted legacy paths
(``old_ir_for`` / ``extract_signals_ir`` / the regex bag). They are history,
kept verbatim.
"""

from __future__ import annotations

from collections.abc import (
    Callable,
    Sequence,
)

from mtg_utils._card_ir.crosswalk import (
    ConceptTree,
    recipient_tag,
)
from mtg_utils._card_ir.tree_synthesis import (
    _has_repeatable_kill_unit,
    structural_token_maker_type_subjects,
)
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import (
    CLASS_TRIBES,
    CREATURE_SUBTYPES,
    TRIBAL_SUBTYPES,
)
from mtg_utils._deck_forge.lanes._shared import (
    _ATTACHMENT_PREDS,
    _CAST_FROM_EXILE_PERMS,
    _DEBUFF_SINGLE_AURA_PREDS,
    _DYNAMIC_PT_MODS,
    _EDICT_ACTORS,
    _FIXING_PRODUCED_TYPES,
    _FORCE_BLOCK_SHAPE_RX,
    _GRANT_ABILITY_MOD_TAGS,
    _GY_CAST_KEYWORDS,
    _GY_MATTERS_KEYWORDS,
    _LAND_SUBTYPE_WORDS,
    _LAND_SUBTYPES,
    _MASS_EFFECT_TAGS,
    _OPP_DISCARD_ACTORS,
    _OPP_TOP_OWNERS,
    _PERMANENT_TYPES,
    _PT_COUNTER_KINDS,
    _REMINDER_RX,
    _RETURN_TARGET_TAGS,
    _REVEAL_WHO_OPP,
    _RING_CONDITIONS,
    _SELF_BLINK_RETURN_TAGS,
    _SELF_PAYLOAD_SUBTYPE,
    _SPELL_GRANT_KEYWORDS,
    _TAP_EVENTS,
    _TARGET_OWNER_BACKREF_TAGS,
    _TOKEN_WORD_RX,
    _TUCK_SELECTION_SIBLINGS,
    _TYPE_MATTERS_LANE,
    _UNKNOWN_MODE_COMBAT_DAMAGE_TO_PLAYER,
    _VOLTRON_SUBTYPES,
    _YOU_EACH,
    _attack_compulsion_hit,
    _condition_leaves,
    _discard_watch_is_opponent,
    _is_generic_creature_filter,
    _kept,
    _negative_pt_field,
    _root_target_filter,
    _sac_is_edict,
    _sentence_span,
    _site_raw,
    _target_owner_beneficiary_scope,
    _tuck_preceded_by_selection,
    _unknown_mode_combat_damage_to_player,
    _voltron_collective_preds,
    _whole_card_maker,
)
from mtg_utils._deck_forge.lanes.board_and_ramp import (
    _CAST_ADD_SAC_LAND_ONLY_WORDS,
    _CAST_ADD_SAC_RX,
    _CM_STATIC_DEF_CHILD_FIELDS,
    _CREATURES_MATTER_EVASION_MODES,
    _CREATURES_MATTER_MOD_TAGS,
    _FLOOR_TOKEN_MAKER_RAW,
    _RECOVERED_ARTIFACT_TOKEN_RE,
    _RECOVERED_ENCHANT_TOKEN_RE,
    _SAC_DEPENDENT_CLAUSE_RX,
    _SAC_OTHER_ACTOR_HEAD_RX,
    _SAC_PTC_OTHER_ACTOR_CONTROLLERS,
    _SAC_PTC_UNIMPL_OTHER_ACTOR_RX,
    _TYPE_MATTERS_GOWIDE_KEYWORDS,
    _TYPE_MATTERS_GOWIDE_MOD_TAGS,
    _aggregate_creature_filter,
    _artifacts_enchantments_matter,
    _attack_tapped_matters,
    _blink_flicker,
    _cast_add_sac_clause_is_land_only,
    _creature_count_operand_filter,
    _creatures_matter,
    _creatures_matter_cmc_property_count_filter,
    _creatures_matter_condition_filter,
    _creatures_matter_flip_coin_win_filter,
    _creatures_matter_formidable_condition,
    _creatures_matter_scaled_target_filter,
    _creatures_matter_wrapped_count_filter,
    _floor_token_maker_subjects,
    _generic_board_lanes,
    _granted_mana_defs,
    _has_animate_treasure_grant,
    _has_created_token_devour,
    _is_artifact_token_types,
    _is_big_mana_tree,
    _is_you_sac_subject,
    _iter_creatures_matter_static_defs,
    _iter_returnasaura_mana_defs,
    _lifegain_matters,
    _mana_accel,
    _mana_fixing,
    _mass_untap_creature_filter,
    _or_wrapped_generic_creature_filter,
    _pump_scaling_creature_filter,
    _ramp,
    _sac_effect_names_other_actor,
    _sac_leaf_is_you_outlet,
    _sac_outlet_granted_cost,
    _sac_ptc_you_eligible,
    _sac_subject_present,
    _sacrifice_outlets,
    _spellcast_matters,
    _tokens_matter,
    _type_matters_go_wide,
    _type_recursion_lanes,
    _typed_matters_lanes,
    blink_flicker_is_maker,
    blink_flicker_maker_present,
)
from mtg_utils._deck_forge.lanes.board_and_ramp import (
    LANES as _BOARD_AND_RAMP_LANES,
)
from mtg_utils._deck_forge.lanes.card_advantage import (
    _COMBAT_BUFF_EVENTS,
    _DIES_RECURSION_GRANT_KEYWORDS,
    _EXILE_OWNS_COND_TEXT_RX,
    _FACEDOWN_MAKER_IDIOM_RX,
    _FACEDOWN_REF_HOOK_RX,
    _LAND_SAC_EVENTS,
    _RECOVERED_DRAW_DIRECTED_RE,
    _RECOVERED_DRAW_REPLACEMENT_RE,
    _SELF_DRAW_RECIPIENT_TAGS,
    _TARGET_PLAYER_DRAW_PHRASE_RE,
    _TARGETED_DRAW_TAGS,
    _TARGETED_DRAW_WIDENED_TAGS,
    _TOPDECK_EACH_PLAYER_ZONE,
    _TOPDECK_SELECTION_TARGET_TAGS,
    _TOPDECK_SELECTION_TOP_RX,
    _TOPDECK_SELECTION_VERB_RX,
    _TOPDECK_STACK_SWEEP_RE,
    _activated_draw,
    _cantrip,
    _card_draw_engine,
    _combat_buff_engine,
    _counter_manipulation,
    _counter_move,
    _creature_recursion,
    _dice_matters,
    _dies_recursion,
    _discard_matters,
    _draw_engine_scope,
    _energy_matters,
    _exile_ability_chain_effects,
    _exile_matters,
    _exile_matters_time_counter_reuse,
    _exile_then_tracked_set_size,
    _explore_matters,
    _extra_upkeep_end,
    _facedown_has_marker,
    _facedown_matters,
    _facedown_node_descriptions,
    _group_hug_draw,
    _has_exile_then_return_replacement,
    _has_suspend_keyword_property,
    _impulse_top_play,
    _land_sacrifice_matters,
    _opponent_draw_matters,
    _pce_has_paired_draw,
    _play_from_top,
    _self_death_payoff,
    _target_player_draws,
    _topdeck_owner_ok,
    _topdeck_selection,
    _topdeck_stack,
    _unit_has_originalcontroller_draw,
    _widened_tag_phrase_match,
    etb_bulk_draw,
)
from mtg_utils._deck_forge.lanes.card_advantage import (
    LANES as _CARD_ADVANTAGE_LANES,
)
from mtg_utils._deck_forge.lanes.core_makers import (
    _CHOSEN_STATIC_MODES,
    _CHOSEN_TYPE_PREDS,
    _DFE_MISPARSE_RX,
    _DFE_RECOVERED_RX,
    _EACH_PLAYER_TOKEN_MAKER_RE,
    _GRANT_ANTHEM_TAGS,
    _GRANT_HOSTILE_PREDS,
    _GRANT_KW_CAMEL,
    _LANDFALL_CLAUSE_RX,
    _LANDFALL_ETB_WORD_RX,
    _LANDFALL_GY_PERMISSION_MODES,
    _LANDFALL_GY_RETURN_WORD_RX,
    _LANDFALL_STATIC_LAND_DROP_MODES,
    _LIFEGAIN_MATTERS_TRIGGER_RX,
    _LIFEGAIN_TEXT_RX,
    _PACIFY_ALWAYS_COMPENSATING_TAGS,
    _PACIFY_ATTACH_PREDS,
    _PACIFY_AURA_MODES,
    _PACIFY_PT_MOD_TAGS,
    _RECOVERED_DAMAGE_REACH,
    GrantPayload,
    _chosen_type_matters,
    _chosen_type_serve_statics,
    _combat_choice_makers,
    _damage_for_each,
    _death_matters,
    _direct_damage,
    _discard_makers,
    _draw_matters,
    _extra_turns,
    _has_land_and_creature,
    _is_creature_animator,
    _keep_n_wrath,
    _land_creatures_matter,
    _landfall,
    _landfall_clauses,
    _lifegain_makers,
    _lifegain_text_idiom,
    _neutralize_aura_compensates,
    _pacify_aura_compensates,
    _pacify_makers,
    _plus_one_makers,
    _reanimator,
    _single_target_neutralize,
    _spell_copy_makers,
    _spell_redirect,
    _token_maker,
    _type_changer_static_reads,
    _type_changer_zone,
    _type_changers,
    _win_lose_game,
    extract_grant_payloads,
)
from mtg_utils._deck_forge.lanes.core_makers import (
    LANES as _CORE_MAKERS_LANES,
)
from mtg_utils._deck_forge.lanes.counters_voltron import (
    _ADAPT_KEYWORD_INVOCATION_RE,
    _ADAPT_MATTERS_RE,
    _ANY_COUNTER_SCALE_TEXT_RX,
    _COUNTER_HATE_OPPONENT_RE,
    _EXCESS_DAMAGE_KEPT_RX,
    _FREE_CAST_KEPT_RX,
    _HAD_P1P1_COND_RX,
    _HAD_P1P1_REMOVAL_TAGS,
    _KICKED_SPELL_KEPT_RX,
    _MINUS_COUNTER_KEPT_RX,
    _P1P1_COND_TEXT_RX,
    _PT_PUMP_TAGS,
    _UNATTACH_RX,
    _UNIMPLEMENTED_ATTACH_GEAR_RX,
    _UNKNOWN_MODE_VOLTRON_ATTACHMENT_RE,
    _VOLTRON_BECOMES_ATTACHED_RX,
    _VOLTRON_REANIMATE_ATTACH_RX,
    _adapt_matters,
    _any_counter_makers,
    _any_counter_matters,
    _chooses_opponent,
    _counter_hate,
    _energy_makers,
    _excess_damage,
    _free_cast,
    _gain_control,
    _gives_control_to_other,
    _has_structural_adapt,
    _kicked_spell_matters,
    _mana_restriction_equip_tell,
    _mill_makers,
    _minus_counters_matter,
    _plus_one_matters,
    _proliferate_makers,
    _resource_token_makers,
    _unknown_mode_voltron_attachment,
    _voltron_count_filters,
    _voltron_equip_style_keyword,
    _voltron_maker_unit_gear_attach,
    _voltron_makers,
    _voltron_matters,
    _voltron_modal_aggregate_tell,
)
from mtg_utils._deck_forge.lanes.counters_voltron import (
    LANES as _COUNTERS_VOLTRON_LANES,
)
from mtg_utils._deck_forge.lanes.graveyard_lifeloss import (
    _ATTACK_REQ_LAND_SAC_RE,
    _CANT_REGENERATE_RX,
    _CLONE_BECOME_COPY_RX,
    _CLONE_LAND_EXCLUDE_RX,
    _CLONE_TOKEN_EXCLUDE_RX,
    _CLONE_TYPE_WORD_RE,
    _DIG_REST_GRAVEYARD_RE,
    _GY_COUNT_PHRASE_RE,
    _GY_OPP_RE,
    _GY_RECOVERED_BOUNCE_RE,
    _LIFELOSS_CLAUSE_RX,
    _LIFELOSS_OPPONENT_TEXT_RX,
    _LIFELOSS_SELF_TEXT_RX,
    _MONARCH_CONDITIONS,
    _OPP_SAC_ACTORS,
    _REGENERATE_WORD_RX,
    _VENTURE_CONDITIONS,
    _attack_requirement_land_sac,
    _clone_copied_words,
    _clone_text_idiom,
    _clone_words_from_raw,
    _combat_damage_to_opp,
    _combat_damage_to_opp_fires,
    _connive_makers,
    _copy_clone,
    _debuff_makers,
    _edict_makers,
    _edict_scope,
    _explore_makers,
    _fight_makers,
    _goad_makers,
    _granted_ability_paylife,
    _granted_land_sac_unless_pay,
    _graveyard_makers,
    _graveyard_matters,
    _gy_count_ref_scope,
    _gy_filter_scope,
    _gy_player_scope,
    _gy_scope,
    _gy_unwrap_scalar,
    _has_defiler_cost_reduction,
    _has_paylife_as_colored_mana,
    _in_condition_instead_branch,
    _land_sacrifice_makers,
    _lifeloss_makers,
    _lifeloss_matters,
    _lifeloss_scope,
    _lifeloss_self_paid_cost,
    _lifeloss_text_scope,
    _lure_makers,
    _monarch,
    _regenerate_makers,
    _sac_actor_scope,
    _sac_targets_opponent,
    _scoped_player_scope,
    _suspect_makers,
    _token_attach_opponent_bleed_ids,
    _unit_has_non_ramp_effect,
    _venture,
    graveyard_return_direction,
    self_mill_fill,
)
from mtg_utils._deck_forge.lanes.graveyard_lifeloss import (
    LANES as _GRAVEYARD_LIFELOSS_LANES,
)
from mtg_utils._deck_forge.lanes.keyword_mechanics import (
    _BOAST_KEYWORDS,
    _CASCADE_KEYWORDS,
    _COMBAT_PHASES,
    _CONTROL_REVENGE_RE,
    _CONVOKE_KEYWORDS,
    _COST_FREE_CAST_KEPT_RX,
    _COST_INCREASE_KEPT_RX,
    _COST_LESS_KEPT_RX,
    _COST_SELF_DISCOUNT_KEPT_RX,
    _COUNTER_PRED_LANES,
    _DAYNIGHT_KEYWORDS,
    _EXHAUST_KEYWORDS,
    _FACEDOWN_KEYWORDS,
    _FORETELL_KEYWORDS,
    _GIVE_AWAY_SCOPES,
    _MAGECRAFT_KEYWORDS,
    _OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX,
    _OPP_DISCARD_SCALING_PREFIX_RX,
    _OPP_PLAYER_TAGS,
    _PHASING_TEXT_RE,
    _PLACE_COUNTER_MAKER_KINDS,
    _PLAYER_COUNTER_MAKER,
    _POISON_KEYWORDS,
    _POISON_WORD_MIRROR,
    _RAD_REF,
    _REPLACEMENT_VALID_PLAYER_SCOPE,
    _RING_BEARER_REF,
    _SUSPEND_KEYWORDS,
    _SYMMETRIC_DISCARD_WATCH_RX,
    _TARGETED_PLAYER_TAGS,
    _TEXT_ONLY_EACH_DISCARD_RX,
    _TEXT_ONLY_OPP_DISCARD_RX,
    _amass_incubate_keyword_fallback,
    _amass_makers,
    _blocked_matters,
    _cast_from_exile,
    _cast_from_exile_unit_evidence,
    _cast_from_exile_zone_evidence,
    _choose_opponent_bound_discard,
    _coin_flip,
    _conjure_makers,
    _cost_reduction,
    _count_operand_lanes,
    _counter_kind_lanes,
    _daynight_makers,
    _dice_makers,
    _discover_makers,
    _donate_makers,
    _end_the_turn,
    _extra_combats,
    _facedown_makers,
    _has_native_rad_counter,
    _incubate_makers,
    _initiative,
    _is_target_player_loot,
    _keyword_field_signals,
    _keyword_field_signals_b5,
    _keyword_field_signals_b7,
    _modified_matters,
    _nested_owner_player_scope,
    _opponent_discard,
    _opponent_exile_makers,
    _phasing_makers,
    _player_counter_makers,
    _predicate_build_around,
    _ring,
    _sibling_reveal_direction,
    _unit_has_nested_reveal_hand,
    _voting_makers,
)
from mtg_utils._deck_forge.lanes.keyword_mechanics import (
    LANES as _KEYWORD_MECHANICS_LANES,
)
from mtg_utils._deck_forge.lanes.mana_and_wipes import (
    _BARE_X_QTY_TAGS,
    _CHEAT_REVEAL_PRODUCERS,
    _DIRECTED_SEARCHERS,
    _DISCARD_OUTLET_SKIP_FIELDS,
    _DISCARD_OUTLET_SWEEP_RE,
    _DRAW_FOR_EACH_PHRASE_RE,
    _DRAW_FOR_EACH_TRACKED_TAGS,
    _GROUP_MANA_RECIPIENTS,
    _MANA_DORK_SUPPORT_RX,
    _MASS_REMOVAL_TYPES,
    _OPP_COUNT_CONTROLLERS,
    _RECOVERED_OPP_DISCARD_RE,
    _SAC_TOKEN_MATTERS,
    _SCALING_QTY_TAGS,
    _TEAM_BUFF_GRANT_KW,
    _TEAM_BUFF_OK_PREDS,
    _anthem_static,
    _change_zone_all_cores,
    _cheat_choose_one_of_battlefield_put,
    _cheat_into_play,
    _cheat_negated_reveal_else_put,
    _cheat_reveal_until_you_enters_put,
    _directed_search_sibling,
    _discard_outlet,
    _draw_for_each,
    _exile_removal,
    _extra_land_drop,
    _field_qty,
    _filter_all_named,
    _group_mana,
    _is_anthem_group_filter,
    _is_scaling_count,
    _is_team_buff_filter,
    _iter_discard_cost_nodes,
    _lands_matter,
    _mana_amplifier,
    _mass_bounce,
    _mass_removal,
    _nested_emblem_tutor_put,
    _nested_grant_reveal_or_hand_put,
    _pump_scaling_lanes,
    _resource_token_matters,
    _reveal_producer_cores,
    _reveal_producer_subtypes,
    _self_pump,
    _sibling_exile_producer_cores,
    _sibling_named_tutor_no_core,
    _sibling_selector_cores,
    _sibling_selector_subtypes,
    _sum_expr_qty,
    _team_buff,
    _tracked_target_exile_caused,
    _unit_targets_player,
)
from mtg_utils._deck_forge.lanes.mana_and_wipes import (
    LANES as _MANA_AND_WIPES_LANES,
)
from mtg_utils._deck_forge.lanes.manifest import SERVED_SIGNAL_KEYS
from mtg_utils._deck_forge.lanes.protection_and_sweep import (
    _B15_KEYWORD_LANES,
    _B16_PLACE_COUNTER_TAGS,
    _B16_STATIC_KEPT_MODS,
    _SPEED_DOER_TAGS,
    _STATION_SUBTYPES,
    _SWEEP_KEYWORD_LANES,
    _SWEEP_SYNTH_KEYS,
    _VOTING_MATTERS_RX,
    _WB_PT_SET_MODS,
    _ability_copy,
    _ability_strip_payoff,
    _arcane_matters,
    _becomes_target_lanes,
    _bending_lanes,
    _cant_block_grant,
    _celebration_matters,
    _cmdzone_ability,
    _conditional_self_protection,
    _each_mode_player,
    _evasion_self,
    _exalted_textual,
    _exhaust_matters,
    _flip_self,
    _free_creature_payoff,
    _free_spell_storm,
    _global_ability_grant,
    _is_island_landwalk_kw,
    _island_makers,
    _keyword_field_signals_b15,
    _keyword_field_signals_b16,
    _keyword_field_signals_sweep,
    _keyword_field_signals_w4g,
    _keyword_soup_makers,
    _legend_rule_off,
    _lessons_matter,
    _life_payment_insurance,
    _lose_unless_hand,
    _meld_pair,
    _miracle_grant,
    _named_counter_misc,
    _named_synergy,
    _noncombat_damage_payoff,
    _nonhuman_attackers,
    _one_punch,
    _opponent_counter_grant,
    _per_target_payoff,
    _power_tap_engine,
    _recast_etb_bleed,
    _sacrifice_protection,
    _saddle_matters_lane,
    _seek_matters,
    _snow_matters,
    _speed_doer,
    _starting_life_matters,
    _station_lanes,
    _stickers_structural,
    _suspect_matters_lane,
    _sweep_kept_mirrors,
    _sweep_source_is_opp,
    _sweep_watched_owner_scope,
    _theft_protection,
    _toughness_combat,
    _typed_anthem_multi,
    _void_warp_makers,
    _voting_matters,
    _wb_dropped_other,
)
from mtg_utils._deck_forge.lanes.protection_and_sweep import (
    LANES as _PROTECTION_AND_SWEEP_LANES,
)
from mtg_utils._deck_forge.lanes.protection_and_sweep import (
    LANES_TAIL as _PROTECTION_AND_SWEEP_LANES_TAIL,
)
from mtg_utils._deck_forge.lanes.removal_tutors import (
    _AA_EXTRA_COST_TAGS,
    _AA_TAP_COST_TAGS,
    _B13_KEYWORD_LANES,
    _B13_MOD_GRANT_LANES,
    _B14_KEYWORD_LANES,
    _COUNTER_TUCK_CHOICE_RE,
    _OPP_SEARCH_MODES,
    _QUALIFIED_DESTROY_TYPE_RE,
    _activated_ability,
    _b13_conferred_grant_lanes,
    _boast_matters,
    _clue_matters_lane,
    _color_hoser,
    _convoke_matters,
    _coven_matters_lane,
    _crimes_matter,
    _curse_matters,
    _destroy_legendary,
    _edict_answer_types,
    _flash_matters_lane,
    _food_matters_lane,
    _foretell_matters,
    _island_matters,
    _keyword_field_signals_b13,
    _keyword_field_signals_b14,
    _keyword_soup,
    _keyword_tribe,
    _mass_death_payoff,
    _opponent_exile_matters_lane,
    _opponent_search_matters,
    _outlaw_matters_lane,
    _own_target_spell,
    _perm_answer_types,
    _permanent_recast,
    _poison_matters,
    _proliferate_matters_lane,
    _pump_makers_lane,
    _qualified_destroy_target_type,
    _removal,
    _removal_answer_types,
    _removal_edict_types_for,
    _self_counter_grow,
    _self_etb_payload,
    _suspend_matters,
    _theft_makers_lane,
    _token_subtype_payoff,
    _trigger_mode_tag,
    _tutor_lane,
    _type_matters_lane,
    _unit_sacrifice_nodes,
    _untap_engine,
    _wants_cloning,
    removal_edict_targets_type,
    self_counter_grow_narrow,
)
from mtg_utils._deck_forge.lanes.removal_tutors import (
    LANES as _REMOVAL_TUTORS_LANES,
)
from mtg_utils._deck_forge.lanes.stax_and_tempo import (
    _ALT_COST_SPELLCAST_RX,
    _ENTERED_ATTACKER_TRIGGER_EVENTS,
    _FOR_EACH_OPPONENT_TAP_RE,
    _OPPONENT_CONTROLS_TAP_RE,
    _OPPONENTS_TURN_RE,
    _REPLICATE_GRANT_RX,
    _TAP_EACH_OPPONENT_CREATURE_RE,
    _TAP_WORD_RE,
    _animate_artifact,
    _big_hand_lanes,
    _color_change,
    _commander_matters,
    _control_exchange,
    _counter_distribute,
    _counter_grants_kw,
    _counter_place_trigger,
    _cycling_matters,
    _dig_until,
    _entered_attacker,
    _evasion_denial,
    _exert_matters,
    _exile_until_leaves,
    _is_protection_animator,
    _keyword_counter,
    _kill_engine,
    _land_denial,
    _land_exchange,
    _land_protection,
    _legends_historic_matters,
    _life_total_set,
    _noncreature_cast_punish,
    _opp_top_exile,
    _saga_matters,
    _scry_surveil_matters,
    _self_blink_lane,
    _stax_lanes,
    _superfriends_matters,
    _tap_lanes,
    _tap_owner_text,
    _tap_sentence,
    _tap_untap_matters,
    _tribal_etb_multi,
    _type_change,
    _typed_enters_punish,
    _typed_spellcast_lane,
    _unspent_mana,
    _vehicles_matter,
)
from mtg_utils._deck_forge.lanes.stax_and_tempo import (
    LANES as _STAX_AND_TEMPO_LANES,
)
from mtg_utils._deck_forge.lanes.triggers_damage import (
    _AURA_EQUIP_KW,
    _DAMAGE_AMP_MODS,
    _DAMAGE_TO_OPP_MATTERS_MIRROR,
    _DEP_PLAYER_TAGS,
    _FORCED_ATTACK_PUNISH_RX,
    _INCREASE_QTY_MODS,
    _KEYWORD_GRANT_TARGET_KEPT_RX,
    _POWER_DOUBLE_MODES,
    _POWER_ITS_OWN_DOER,
    _POWER_MULT_DOER,
    _POWER_RECIP_CREATURE_TEXT,
    _POWER_SELF_RECIP,
    _PROTECTIVE_GRANT_KW,
    _REVEAL_PLAYER_TAGS,
    _REVEAL_SCOPE_WRAPPER_TAGS,
    _REVEALS_HAND_TEXT_RE,
    _SECOND_SPELL_NODE_TEXT,
    _SUIT_UP_PREDS,
    _TEAM_EVASION_GRANT_RX,
    _TEAM_EVASION_KW,
    _TRIGGER_DOUBLING_GRANT_RE,
    _animate_refs_other_object_stats,
    _base_power_matters,
    _base_pt_set,
    _bounce_tempo,
    _combat_damage_lanes,
    _copy_limit,
    _counter_control,
    _creature_cast_trigger,
    _creature_ping_fires,
    _damage_equal_power,
    _damage_prevention,
    _damage_redirect,
    _damage_trigger_lanes,
    _delayed_had_enter_creature_etb,
    _dep_or_and_reaches_player,
    _etb_trigger_lanes,
    _forced_attack,
    _hand_disruption,
    _is_tribe_damage_source,
    _iter_base_pt_modal_threaded_statics,
    _keyword_grant_lanes,
    _ltb_matters,
    _mass_damage_lanes,
    _norm_kw,
    _opponent_cast_matters,
    _power_double,
    _replacement_doubler_lanes,
    _reveal_names_other_player,
    _second_spell_matters,
    _second_spell_node_text,
    _spell_keyword_grant,
    _trigger_doubling,
    _unimplemented_ability_creature_etb,
    _unit_is_repeatable,
    _unknown_mode_creature_etb,
    _variable_pt,
    _xspell_matters,
)
from mtg_utils._deck_forge.lanes.triggers_damage import (
    LANES as _TRIGGERS_DAMAGE_LANES,
)
from mtg_utils._deck_forge.lanes.triggers_damage import (
    LANES_W8 as _TRIGGERS_DAMAGE_LANES_W8,
)
from mtg_utils._deck_forge.membership_floor import (
    _FLOOR_DETECTORS,
    _IR_FLOOR_LANES,
    _apply_membership_floor,
)
from mtg_utils._deck_forge.signal_base import Signal
from mtg_utils.card_classify import get_oracle_text

__all__ = [
    "SERVED_SIGNAL_KEYS",
    "_AA_EXTRA_COST_TAGS",
    "_AA_TAP_COST_TAGS",
    "_ADAPT_KEYWORD_INVOCATION_RE",
    "_ADAPT_MATTERS_RE",
    "_ALT_COST_SPELLCAST_RX",
    "_ANY_COUNTER_SCALE_TEXT_RX",
    "_ATTACHMENT_PREDS",
    "_ATTACK_REQ_LAND_SAC_RE",
    "_AURA_EQUIP_KW",
    "_B13_KEYWORD_LANES",
    "_B13_MOD_GRANT_LANES",
    "_B14_KEYWORD_LANES",
    "_B15_KEYWORD_LANES",
    "_B16_PLACE_COUNTER_TAGS",
    "_B16_STATIC_KEPT_MODS",
    "_BARE_X_QTY_TAGS",
    "_BOAST_KEYWORDS",
    "_CANT_REGENERATE_RX",
    "_CASCADE_KEYWORDS",
    "_CAST_ADD_SAC_LAND_ONLY_WORDS",
    "_CAST_ADD_SAC_RX",
    "_CAST_FROM_EXILE_PERMS",
    "_CHEAT_REVEAL_PRODUCERS",
    "_CHOSEN_STATIC_MODES",
    "_CHOSEN_TYPE_PREDS",
    "_CLONE_BECOME_COPY_RX",
    "_CLONE_LAND_EXCLUDE_RX",
    "_CLONE_TOKEN_EXCLUDE_RX",
    "_CLONE_TYPE_WORD_RE",
    "_CM_STATIC_DEF_CHILD_FIELDS",
    "_COMBAT_BUFF_EVENTS",
    "_COMBAT_PHASES",
    "_CONTROL_REVENGE_RE",
    "_CONVOKE_KEYWORDS",
    "_COST_FREE_CAST_KEPT_RX",
    "_COST_INCREASE_KEPT_RX",
    "_COST_LESS_KEPT_RX",
    "_COST_SELF_DISCOUNT_KEPT_RX",
    "_COUNTER_HATE_OPPONENT_RE",
    "_COUNTER_PRED_LANES",
    "_COUNTER_TUCK_CHOICE_RE",
    "_CREATURES_MATTER_EVASION_MODES",
    "_CREATURES_MATTER_MOD_TAGS",
    "_DAMAGE_AMP_MODS",
    "_DAMAGE_TO_OPP_MATTERS_MIRROR",
    "_DAYNIGHT_KEYWORDS",
    "_DEBUFF_SINGLE_AURA_PREDS",
    "_DEP_PLAYER_TAGS",
    "_DFE_MISPARSE_RX",
    "_DFE_RECOVERED_RX",
    "_DIES_RECURSION_GRANT_KEYWORDS",
    "_DIG_REST_GRAVEYARD_RE",
    "_DIRECTED_SEARCHERS",
    "_DISCARD_OUTLET_SKIP_FIELDS",
    "_DISCARD_OUTLET_SWEEP_RE",
    "_DRAW_FOR_EACH_PHRASE_RE",
    "_DRAW_FOR_EACH_TRACKED_TAGS",
    "_DYNAMIC_PT_MODS",
    "_EACH_PLAYER_TOKEN_MAKER_RE",
    "_EDICT_ACTORS",
    "_ENTERED_ATTACKER_TRIGGER_EVENTS",
    "_EXCESS_DAMAGE_KEPT_RX",
    "_EXHAUST_KEYWORDS",
    "_EXILE_OWNS_COND_TEXT_RX",
    "_FACEDOWN_KEYWORDS",
    "_FACEDOWN_MAKER_IDIOM_RX",
    "_FACEDOWN_REF_HOOK_RX",
    "_FIXING_PRODUCED_TYPES",
    "_FLOOR_TOKEN_MAKER_RAW",
    "_FORCED_ATTACK_PUNISH_RX",
    "_FORCE_BLOCK_SHAPE_RX",
    "_FORETELL_KEYWORDS",
    "_FOR_EACH_OPPONENT_TAP_RE",
    "_FREE_CAST_KEPT_RX",
    "_GIVE_AWAY_SCOPES",
    "_GRANT_ABILITY_MOD_TAGS",
    "_GRANT_ANTHEM_TAGS",
    "_GRANT_HOSTILE_PREDS",
    "_GRANT_KW_CAMEL",
    "_GROUP_MANA_RECIPIENTS",
    "_GY_CAST_KEYWORDS",
    "_GY_COUNT_PHRASE_RE",
    "_GY_MATTERS_KEYWORDS",
    "_GY_OPP_RE",
    "_GY_RECOVERED_BOUNCE_RE",
    "_HAD_P1P1_COND_RX",
    "_HAD_P1P1_REMOVAL_TAGS",
    "_INCREASE_QTY_MODS",
    "_KEYWORD_GRANT_TARGET_KEPT_RX",
    "_KICKED_SPELL_KEPT_RX",
    "_LANDFALL_CLAUSE_RX",
    "_LANDFALL_ETB_WORD_RX",
    "_LANDFALL_GY_PERMISSION_MODES",
    "_LANDFALL_GY_RETURN_WORD_RX",
    "_LANDFALL_STATIC_LAND_DROP_MODES",
    "_LAND_SAC_EVENTS",
    "_LAND_SUBTYPES",
    "_LAND_SUBTYPE_WORDS",
    "_LANES",
    "_LIFEGAIN_MATTERS_TRIGGER_RX",
    "_LIFEGAIN_TEXT_RX",
    "_LIFELOSS_CLAUSE_RX",
    "_LIFELOSS_OPPONENT_TEXT_RX",
    "_LIFELOSS_SELF_TEXT_RX",
    "_MAGECRAFT_KEYWORDS",
    "_MANA_DORK_SUPPORT_RX",
    "_MASS_EFFECT_TAGS",
    "_MASS_REMOVAL_TYPES",
    "_MINUS_COUNTER_KEPT_RX",
    "_MONARCH_CONDITIONS",
    "_OPPONENTS_TURN_RE",
    "_OPPONENT_CONTROLS_TAP_RE",
    "_OPP_COUNT_CONTROLLERS",
    "_OPP_DISCARD_ACTORS",
    "_OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX",
    "_OPP_DISCARD_SCALING_PREFIX_RX",
    "_OPP_PLAYER_TAGS",
    "_OPP_SAC_ACTORS",
    "_OPP_SEARCH_MODES",
    "_OPP_TOP_OWNERS",
    "_P1P1_COND_TEXT_RX",
    "_PACIFY_ALWAYS_COMPENSATING_TAGS",
    "_PACIFY_ATTACH_PREDS",
    "_PACIFY_AURA_MODES",
    "_PACIFY_PT_MOD_TAGS",
    "_PERMANENT_TYPES",
    "_PHASING_TEXT_RE",
    "_PLACE_COUNTER_MAKER_KINDS",
    "_PLAYER_COUNTER_MAKER",
    "_POISON_KEYWORDS",
    "_POISON_WORD_MIRROR",
    "_POWER_DOUBLE_MODES",
    "_POWER_ITS_OWN_DOER",
    "_POWER_MULT_DOER",
    "_POWER_RECIP_CREATURE_TEXT",
    "_POWER_SELF_RECIP",
    "_PROTECTIVE_GRANT_KW",
    "_PT_COUNTER_KINDS",
    "_PT_PUMP_TAGS",
    "_QUALIFIED_DESTROY_TYPE_RE",
    "_RAD_REF",
    "_RECOVERED_ARTIFACT_TOKEN_RE",
    "_RECOVERED_DAMAGE_REACH",
    "_RECOVERED_DRAW_DIRECTED_RE",
    "_RECOVERED_DRAW_REPLACEMENT_RE",
    "_RECOVERED_ENCHANT_TOKEN_RE",
    "_RECOVERED_OPP_DISCARD_RE",
    "_REGENERATE_WORD_RX",
    "_REMINDER_RX",
    "_REPLACEMENT_VALID_PLAYER_SCOPE",
    "_REPLICATE_GRANT_RX",
    "_RETURN_TARGET_TAGS",
    "_REVEALS_HAND_TEXT_RE",
    "_REVEAL_PLAYER_TAGS",
    "_REVEAL_SCOPE_WRAPPER_TAGS",
    "_REVEAL_WHO_OPP",
    "_RING_BEARER_REF",
    "_RING_CONDITIONS",
    "_SAC_DEPENDENT_CLAUSE_RX",
    "_SAC_OTHER_ACTOR_HEAD_RX",
    "_SAC_PTC_OTHER_ACTOR_CONTROLLERS",
    "_SAC_PTC_UNIMPL_OTHER_ACTOR_RX",
    "_SAC_TOKEN_MATTERS",
    "_SCALING_QTY_TAGS",
    "_SECOND_SPELL_NODE_TEXT",
    "_SELF_BLINK_RETURN_TAGS",
    "_SELF_DRAW_RECIPIENT_TAGS",
    "_SELF_PAYLOAD_SUBTYPE",
    "_SPEED_DOER_TAGS",
    "_SPELL_GRANT_KEYWORDS",
    "_STATION_SUBTYPES",
    "_SUIT_UP_PREDS",
    "_SUSPEND_KEYWORDS",
    "_SWEEP_KEYWORD_LANES",
    "_SWEEP_SYNTH_KEYS",
    "_SYMMETRIC_DISCARD_WATCH_RX",
    "_TAP_EACH_OPPONENT_CREATURE_RE",
    "_TAP_EVENTS",
    "_TAP_WORD_RE",
    "_TARGETED_DRAW_TAGS",
    "_TARGETED_DRAW_WIDENED_TAGS",
    "_TARGETED_PLAYER_TAGS",
    "_TARGET_OWNER_BACKREF_TAGS",
    "_TARGET_PLAYER_DRAW_PHRASE_RE",
    "_TEAM_BUFF_GRANT_KW",
    "_TEAM_BUFF_OK_PREDS",
    "_TEAM_EVASION_GRANT_RX",
    "_TEAM_EVASION_KW",
    "_TEXT_ONLY_EACH_DISCARD_RX",
    "_TEXT_ONLY_OPP_DISCARD_RX",
    "_TOKEN_WORD_RX",
    "_TOPDECK_EACH_PLAYER_ZONE",
    "_TOPDECK_SELECTION_TARGET_TAGS",
    "_TOPDECK_SELECTION_TOP_RX",
    "_TOPDECK_SELECTION_VERB_RX",
    "_TOPDECK_STACK_SWEEP_RE",
    "_TRIGGER_DOUBLING_GRANT_RE",
    "_TUCK_SELECTION_SIBLINGS",
    "_TYPE_MATTERS_GOWIDE_KEYWORDS",
    "_TYPE_MATTERS_GOWIDE_MOD_TAGS",
    "_TYPE_MATTERS_LANE",
    "_UNATTACH_RX",
    "_UNIMPLEMENTED_ATTACH_GEAR_RX",
    "_UNKNOWN_MODE_COMBAT_DAMAGE_TO_PLAYER",
    "_UNKNOWN_MODE_VOLTRON_ATTACHMENT_RE",
    "_VENTURE_CONDITIONS",
    "_VOLTRON_BECOMES_ATTACHED_RX",
    "_VOLTRON_REANIMATE_ATTACH_RX",
    "_VOLTRON_SUBTYPES",
    "_VOTING_MATTERS_RX",
    "_WB_PT_SET_MODS",
    "_YOU_EACH",
    "GrantPayload",
    "_ability_copy",
    "_ability_strip_payoff",
    "_activated_ability",
    "_activated_draw",
    "_adapt_matters",
    "_aggregate_creature_filter",
    "_amass_incubate_keyword_fallback",
    "_amass_makers",
    "_animate_artifact",
    "_animate_refs_other_object_stats",
    "_anthem_static",
    "_any_counter_makers",
    "_any_counter_matters",
    "_arcane_matters",
    "_artifacts_enchantments_matter",
    "_attack_compulsion_hit",
    "_attack_requirement_land_sac",
    "_attack_tapped_matters",
    "_b13_conferred_grant_lanes",
    "_base_power_matters",
    "_base_pt_set",
    "_becomes_target_lanes",
    "_bending_lanes",
    "_big_hand_lanes",
    "_blink_flicker",
    "_blocked_matters",
    "_boast_matters",
    "_bounce_tempo",
    "_cant_block_grant",
    "_cantrip",
    "_card_draw_engine",
    "_cast_add_sac_clause_is_land_only",
    "_cast_from_exile",
    "_cast_from_exile_unit_evidence",
    "_cast_from_exile_zone_evidence",
    "_celebration_matters",
    "_change_zone_all_cores",
    "_cheat_choose_one_of_battlefield_put",
    "_cheat_into_play",
    "_cheat_negated_reveal_else_put",
    "_cheat_reveal_until_you_enters_put",
    "_choose_opponent_bound_discard",
    "_chooses_opponent",
    "_chosen_type_matters",
    "_chosen_type_serve_statics",
    "_clone_copied_words",
    "_clone_text_idiom",
    "_clone_words_from_raw",
    "_clue_matters_lane",
    "_cmdzone_ability",
    "_coin_flip",
    "_color_change",
    "_color_hoser",
    "_combat_buff_engine",
    "_combat_choice_makers",
    "_combat_damage_lanes",
    "_combat_damage_to_opp",
    "_combat_damage_to_opp_fires",
    "_commander_matters",
    "_condition_leaves",
    "_conditional_self_protection",
    "_conjure_makers",
    "_connive_makers",
    "_control_exchange",
    "_convoke_matters",
    "_copy_clone",
    "_copy_limit",
    "_cost_reduction",
    "_count_operand_lanes",
    "_counter_control",
    "_counter_distribute",
    "_counter_grants_kw",
    "_counter_hate",
    "_counter_kind_lanes",
    "_counter_manipulation",
    "_counter_move",
    "_counter_place_trigger",
    "_coven_matters_lane",
    "_creature_cast_trigger",
    "_creature_count_operand_filter",
    "_creature_ping_fires",
    "_creature_recursion",
    "_creatures_matter",
    "_creatures_matter_cmc_property_count_filter",
    "_creatures_matter_condition_filter",
    "_creatures_matter_flip_coin_win_filter",
    "_creatures_matter_formidable_condition",
    "_creatures_matter_scaled_target_filter",
    "_creatures_matter_wrapped_count_filter",
    "_crimes_matter",
    "_curse_matters",
    "_cycling_matters",
    "_damage_equal_power",
    "_damage_for_each",
    "_damage_prevention",
    "_damage_redirect",
    "_damage_trigger_lanes",
    "_daynight_makers",
    "_death_matters",
    "_debuff_makers",
    "_delayed_had_enter_creature_etb",
    "_dep_or_and_reaches_player",
    "_destroy_legendary",
    "_dice_makers",
    "_dice_matters",
    "_dies_recursion",
    "_dig_until",
    "_direct_damage",
    "_directed_search_sibling",
    "_discard_makers",
    "_discard_matters",
    "_discard_outlet",
    "_discard_watch_is_opponent",
    "_discover_makers",
    "_donate_makers",
    "_draw_engine_scope",
    "_draw_for_each",
    "_draw_matters",
    "_each_mode_player",
    "_edict_answer_types",
    "_edict_makers",
    "_edict_scope",
    "_end_the_turn",
    "_energy_makers",
    "_energy_matters",
    "_entered_attacker",
    "_etb_trigger_lanes",
    "_evasion_denial",
    "_evasion_self",
    "_exalted_textual",
    "_excess_damage",
    "_exert_matters",
    "_exhaust_matters",
    "_exile_ability_chain_effects",
    "_exile_matters",
    "_exile_matters_time_counter_reuse",
    "_exile_removal",
    "_exile_then_tracked_set_size",
    "_exile_until_leaves",
    "_explore_makers",
    "_explore_matters",
    "_extra_combats",
    "_extra_land_drop",
    "_extra_turns",
    "_extra_upkeep_end",
    "_facedown_has_marker",
    "_facedown_makers",
    "_facedown_matters",
    "_facedown_node_descriptions",
    "_field_qty",
    "_fight_makers",
    "_filter_all_named",
    "_flash_matters_lane",
    "_flip_self",
    "_floor_token_maker_subjects",
    "_food_matters_lane",
    "_forced_attack",
    "_foretell_matters",
    "_free_cast",
    "_free_creature_payoff",
    "_free_spell_storm",
    "_gain_control",
    "_generic_board_lanes",
    "_gives_control_to_other",
    "_global_ability_grant",
    "_goad_makers",
    "_granted_ability_paylife",
    "_granted_land_sac_unless_pay",
    "_granted_mana_defs",
    "_graveyard_makers",
    "_graveyard_matters",
    "_group_hug_draw",
    "_group_mana",
    "_gy_count_ref_scope",
    "_gy_filter_scope",
    "_gy_player_scope",
    "_gy_scope",
    "_gy_unwrap_scalar",
    "_hand_disruption",
    "_has_animate_treasure_grant",
    "_has_created_token_devour",
    "_has_defiler_cost_reduction",
    "_has_exile_then_return_replacement",
    "_has_land_and_creature",
    "_has_native_rad_counter",
    "_has_paylife_as_colored_mana",
    "_has_structural_adapt",
    "_has_suspend_keyword_property",
    "_impulse_top_play",
    "_in_condition_instead_branch",
    "_incubate_makers",
    "_initiative",
    "_is_anthem_group_filter",
    "_is_artifact_token_types",
    "_is_big_mana_tree",
    "_is_creature_animator",
    "_is_generic_creature_filter",
    "_is_island_landwalk_kw",
    "_is_protection_animator",
    "_is_scaling_count",
    "_is_target_player_loot",
    "_is_team_buff_filter",
    "_is_tribe_damage_source",
    "_is_you_sac_subject",
    "_island_makers",
    "_island_matters",
    "_iter_base_pt_modal_threaded_statics",
    "_iter_creatures_matter_static_defs",
    "_iter_discard_cost_nodes",
    "_iter_returnasaura_mana_defs",
    "_keep_n_wrath",
    "_kept",
    "_keyword_counter",
    "_keyword_field_signals",
    "_keyword_field_signals_b5",
    "_keyword_field_signals_b7",
    "_keyword_field_signals_b13",
    "_keyword_field_signals_b14",
    "_keyword_field_signals_b15",
    "_keyword_field_signals_b16",
    "_keyword_field_signals_sweep",
    "_keyword_field_signals_w4g",
    "_keyword_grant_lanes",
    "_keyword_soup",
    "_keyword_soup_makers",
    "_keyword_tribe",
    "_kicked_spell_matters",
    "_kill_engine",
    "_land_creatures_matter",
    "_land_denial",
    "_land_exchange",
    "_land_protection",
    "_land_sacrifice_makers",
    "_land_sacrifice_matters",
    "_landfall",
    "_landfall_clauses",
    "_lands_matter",
    "_legend_rule_off",
    "_legends_historic_matters",
    "_lessons_matter",
    "_life_payment_insurance",
    "_life_total_set",
    "_lifegain_makers",
    "_lifegain_matters",
    "_lifegain_text_idiom",
    "_lifeloss_makers",
    "_lifeloss_matters",
    "_lifeloss_scope",
    "_lifeloss_self_paid_cost",
    "_lifeloss_text_scope",
    "_lose_unless_hand",
    "_ltb_matters",
    "_lure_makers",
    "_mana_accel",
    "_mana_amplifier",
    "_mana_fixing",
    "_mana_restriction_equip_tell",
    "_mass_bounce",
    "_mass_damage_lanes",
    "_mass_death_payoff",
    "_mass_removal",
    "_mass_untap_creature_filter",
    "_meld_pair",
    "_mill_makers",
    "_minus_counters_matter",
    "_miracle_grant",
    "_modified_matters",
    "_monarch",
    "_named_counter_misc",
    "_named_synergy",
    "_negative_pt_field",
    "_nested_emblem_tutor_put",
    "_nested_grant_reveal_or_hand_put",
    "_nested_owner_player_scope",
    "_neutralize_aura_compensates",
    "_noncombat_damage_payoff",
    "_noncreature_cast_punish",
    "_nonhuman_attackers",
    "_norm_kw",
    "_one_punch",
    "_opp_top_exile",
    "_opponent_cast_matters",
    "_opponent_counter_grant",
    "_opponent_discard",
    "_opponent_draw_matters",
    "_opponent_exile_makers",
    "_opponent_exile_matters_lane",
    "_opponent_search_matters",
    "_or_wrapped_generic_creature_filter",
    "_outlaw_matters_lane",
    "_own_target_spell",
    "_pacify_aura_compensates",
    "_pacify_makers",
    "_pce_has_paired_draw",
    "_per_target_payoff",
    "_perm_answer_types",
    "_permanent_recast",
    "_phasing_makers",
    "_play_from_top",
    "_player_counter_makers",
    "_plus_one_makers",
    "_plus_one_matters",
    "_poison_matters",
    "_power_double",
    "_power_tap_engine",
    "_predicate_build_around",
    "_proliferate_makers",
    "_proliferate_matters_lane",
    "_pump_makers_lane",
    "_pump_scaling_creature_filter",
    "_pump_scaling_lanes",
    "_qualified_destroy_target_type",
    "_ramp",
    "_reanimator",
    "_recast_etb_bleed",
    "_regenerate_makers",
    "_removal",
    "_removal_answer_types",
    "_removal_edict_types_for",
    "_replacement_doubler_lanes",
    "_resource_token_makers",
    "_resource_token_matters",
    "_reveal_names_other_player",
    "_reveal_producer_cores",
    "_reveal_producer_subtypes",
    "_ring",
    "_root_target_filter",
    "_sac_actor_scope",
    "_sac_effect_names_other_actor",
    "_sac_is_edict",
    "_sac_leaf_is_you_outlet",
    "_sac_outlet_granted_cost",
    "_sac_ptc_you_eligible",
    "_sac_subject_present",
    "_sac_targets_opponent",
    "_sacrifice_outlets",
    "_sacrifice_protection",
    "_saddle_matters_lane",
    "_saga_matters",
    "_scoped_player_scope",
    "_scry_surveil_matters",
    "_second_spell_matters",
    "_second_spell_node_text",
    "_seek_matters",
    "_self_blink_lane",
    "_self_counter_grow",
    "_self_death_payoff",
    "_self_etb_payload",
    "_self_pump",
    "_sentence_span",
    "_sibling_exile_producer_cores",
    "_sibling_named_tutor_no_core",
    "_sibling_reveal_direction",
    "_sibling_selector_cores",
    "_sibling_selector_subtypes",
    "_single_target_neutralize",
    "_site_raw",
    "_snow_matters",
    "_speed_doer",
    "_spell_copy_makers",
    "_spell_keyword_grant",
    "_spell_redirect",
    "_spellcast_matters",
    "_starting_life_matters",
    "_station_lanes",
    "_stax_lanes",
    "_stickers_structural",
    "_sum_expr_qty",
    "_superfriends_matters",
    "_suspect_makers",
    "_suspect_matters_lane",
    "_suspend_matters",
    "_sweep_kept_mirrors",
    "_sweep_source_is_opp",
    "_sweep_watched_owner_scope",
    "_tap_lanes",
    "_tap_owner_text",
    "_tap_sentence",
    "_tap_untap_matters",
    "_target_owner_beneficiary_scope",
    "_target_player_draws",
    "_team_buff",
    "_theft_makers_lane",
    "_theft_protection",
    "_token_attach_opponent_bleed_ids",
    "_token_maker",
    "_token_subtype_payoff",
    "_tokens_matter",
    "_topdeck_owner_ok",
    "_topdeck_selection",
    "_topdeck_stack",
    "_toughness_combat",
    "_tracked_target_exile_caused",
    "_tribal_etb_multi",
    "_trigger_doubling",
    "_trigger_mode_tag",
    "_tuck_preceded_by_selection",
    "_tutor_lane",
    "_type_change",
    "_type_changer_static_reads",
    "_type_changer_zone",
    "_type_changers",
    "_type_matters_go_wide",
    "_type_matters_lane",
    "_type_recursion_lanes",
    "_typed_anthem_multi",
    "_typed_enters_punish",
    "_typed_matters_lanes",
    "_typed_spellcast_lane",
    "_unimplemented_ability_creature_etb",
    "_unit_has_nested_reveal_hand",
    "_unit_has_non_ramp_effect",
    "_unit_has_originalcontroller_draw",
    "_unit_is_repeatable",
    "_unit_sacrifice_nodes",
    "_unit_targets_player",
    "_unknown_mode_combat_damage_to_player",
    "_unknown_mode_creature_etb",
    "_unknown_mode_voltron_attachment",
    "_unspent_mana",
    "_untap_engine",
    "_variable_pt",
    "_vehicles_matter",
    "_venture",
    "_void_warp_makers",
    "_voltron_collective_preds",
    "_voltron_count_filters",
    "_voltron_equip_style_keyword",
    "_voltron_maker_unit_gear_attach",
    "_voltron_makers",
    "_voltron_matters",
    "_voltron_modal_aggregate_tell",
    "_voting_makers",
    "_voting_matters",
    "_wants_cloning",
    "_wb_dropped_other",
    "_whole_card_maker",
    "_widened_tag_phrase_match",
    "_win_lose_game",
    "_xspell_matters",
    "apply_membership_floor",
    "blink_flicker_is_maker",
    "blink_flicker_maker_present",
    "etb_bulk_draw",
    "extract_crosswalk_signals",
    "extract_grant_payloads",
    "graveyard_return_direction",
    "removal_edict_targets_type",
    "self_counter_grow_narrow",
    "self_mill_fill",
]

# ORDERING CONTRACT: the concatenation below MUST reproduce the original
# crosswalk_signals._LANES tuple ELEMENT-FOR-ELEMENT, IN ORDER — lane emission
# order feeds the first-wins ident dedupe in extract_crosswalk_signals (and
# downstream consumers), so reordering segments changes which lane's Signal
# survives a (key, scope, subject) collision. Do not reorder or merge segments.
_LANES = (
    _CORE_MAKERS_LANES
    + _BOARD_AND_RAMP_LANES
    + _COUNTERS_VOLTRON_LANES
    + _GRAVEYARD_LIFELOSS_LANES
    + _KEYWORD_MECHANICS_LANES
    + _MANA_AND_WIPES_LANES
    + _CARD_ADVANTAGE_LANES
    + _TRIGGERS_DAMAGE_LANES
    + _STAX_AND_TEMPO_LANES
    + _REMOVAL_TUTORS_LANES
    + _PROTECTION_AND_SWEEP_LANES
    + _TRIGGERS_DAMAGE_LANES_W8
    + _PROTECTION_AND_SWEEP_LANES_TAIL
)


def extract_crosswalk_signals(
    tree: ConceptTree,
    *,
    keywords: frozenset[str] = frozenset(),
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    all_trees: Sequence[ConceptTree] = (),
) -> list[Signal]:
    """Run the structural signal lanes over one concept tree; dedupe by ident.

    Emits exactly what the lanes produce — there is no key filter (ADR-0014:
    the old ``keys=`` slice was strangler-era scaffolding measured to drop
    nothing; the served-key manifest ``SERVED_SIGNAL_KEYS`` now feeds only the
    key-agreement gate, and a corpus test asserts every emitted key is in it).
    The whole-card ``spell_copy_makers`` → ``spellcast_matters`` reconciliation
    is applied (a spell-copier wants a dense instant/sorcery base, so a
    ``spellcast_matters`` LOW is cross-opened when absent).

    ``keywords`` is the card's Scryfall keyword array (the bulk record's
    ``keywords``), the field-lookup source ``mill_makers`` gates on — it is NOT in
    the phase typed substrate (phase carries no ``Mill`` keyword), so the caller
    supplies it (the shadow diff from the bulk record, the tests from the fixture).

    ``vocab`` is the creature-subtype vocab the token-kindred cross-open validates
    against (threaded through like the hybrid).

    ``all_trees`` (ADR-0039 task #80 step 6): the card's FULL per-face tree tuple
    (every face, ``tree`` included), for the type_matters class-tribe go-wide gate
    ONLY — a two-face card whose token-maker ability lives on a NON-creature face
    (Flaxen Intruder // Welcome Home, Huatli Poet of Unity // Roar of the Fifth
    People, Kianne Dean of Substance // Imbraham Dean of Theory, Jadzi Steward of
    Fate // Oracle's Gift, Eccentric Pestfinder // Turn Stones) needs a sibling
    face's tree to prove "this card goes wide" before its OWN creature face opens
    a CLASS tribe (CR 205.3; see :func:`_type_matters_go_wide`). Defaults to
    ``()`` (single-tree callers / tests — falls back to just ``tree``), so every
    existing direct caller is unaffected. The card-type / cares-about MEMBERSHIP
    floor itself no longer runs here at all — see :func:`apply_membership_floor`,
    called ONCE per card at the merge level (``signals.extract_signals``)
    where every face's tree is visible together (closes the Sheoldred // The True
    Scriptures kill_engine gap the same way).
    """
    # ADR-0035 Stage-3b (b): run the named overlay-correction stage FIRST, so the
    # lanes read the corrected concept overlay (a dig-into-play flipped to
    # cheat_play, an edict re-scoped). Preserves the L1 mirror by identity
    # (substrate-purity invariant).
    from mtg_utils._card_ir.overlay_corrections import apply_overlay_corrections
    from mtg_utils._card_ir.tree_synthesis import apply_tree_synthesis

    tree = apply_overlay_corrections(tree)
    # ADR-0037: ADD synthetic concept-nodes for genuine phase-parse (bucket-B) gaps
    # the lanes read structurally (death_matters' Syr Konrad-family tail). Signal
    # path ONLY — never in compat_card, so the the compat-Card consumers are invariant.
    # Preserves the phase L1 fingerprint (substrate-purity, relaxed).
    tree = apply_tree_synthesis(tree)
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(sig: Signal) -> None:
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(sig)

    for lane in _LANES:
        for sig in lane(tree):
            add(sig)
    for sig in _mill_makers(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b5(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b7(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b13(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b14(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b15(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b16(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_w4g(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_sweep(frozenset(keywords), tree.name):
        add(sig)
    for sig in _amass_incubate_keyword_fallback(frozenset(keywords), tree.name):
        add(sig)
    # b15 keyword-DISCRIMINATED lanes (the bending node arm's earthbend gate
    # and the firebending / station mirror splits read the Scryfall array,
    # so they take ``keywords`` like the field-lookup rows above).
    for sig in _bending_lanes(tree, frozenset(keywords)):
        add(sig)
    for sig in _station_lanes(tree, frozenset(keywords)):
        add(sig)

    # Whole-card reconciliation (granularity c): cross-open spellcast_matters LOW
    # from a spell-copier that has no native spellcast signal in this batch.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        add(Signal("spellcast_matters", "you", "", "", tree.name, "low"))

    # b14 §7 — the wants_theft hybrid-FACADE reconciliation (CR 800.4a; the
    # spell_copy precedent above): a battlefield-steal (gain_control in the
    # MERGED out keys) or a "don't own" payoff tell opens the LOW
    # wants_theft benefit lane; a dont_own tell with NO structural
    # gain_control also restores the facade's LOW gain_control half.
    # include_membership flag asymmetry noted at _wants_cloning — live gates
    # this behind include_membership, the crosswalk runs it unconditionally
    # (live pops measured with the flag True; the b12 kill_engine precedent).
    # Tier-1 (ADR-0036/0037 T10-finalize2 fold): the deleted lane-time
    # ``_DONT_OWN_RX`` whole-oracle scan is relocated verbatim to the
    # bucket-B ``synth_dont_own`` node (:func:`_arm_dont_own`), read here.
    out_keys = {s.key for s in out}
    gc_now = "gain_control" in out_keys
    dont_own = any(c.concept == "synth_dont_own" for c in tree.iter_concepts())
    if (gc_now or dont_own) and "wants_theft" not in out_keys:
        add(Signal("wants_theft", "opponents", "", "", tree.name, "low"))
    if dont_own and not gc_now:
        add(Signal("gain_control", "you", "", "", tree.name, "low"))

    # b14 §1 arm C — the type_matters MEMBERSHIP reconciliation (LOW; runs
    # AFTER the lane loop so a HIGH lane firing wins the ident dedupe — the
    # class-tribe go_wide gate itself calls its constituent lanes directly,
    # ADR-0038 W5, not the (dead-in-production) accumulated out-key set):
    # (i) own type_line subtype — race tribes (TRIBAL_SUBTYPES) fire
    # unconditionally, class tribes (CLASS_TRIBES) only behind a go-wide
    # signal (CR 205.3);
    # (ii) token-profile subtypes — the Token effect nodes' creature-token
    # ``types`` (the b13 has_devour token-profile precedent; ``human``
    # excluded, matching live's all_parts arm), via the SHARED
    # :func:`structural_token_maker_type_subjects` (the lane/gate source),
    # UNION the ``synth_token_maker_type_subject`` bucket-B node (ADR-0036/
    # 0037 T10-finalize2 fold — the deleted lane-time ``clauses(_kept(tree))``
    # + ``_detect_token_maker`` per-clause scan is relocated verbatim to
    # :func:`_arm_token_maker_type_subject`, gap-gated against the same
    # structural set: Krenko makes Goblins → wants Goblin lords; Ghalta and
    # Mavren's MODAL Dinosaur bullet phase's ``effect_concepts`` walk drops).
    # Live's all_parts membership can fire tokens the PHASE record doesn't
    # name (bulk-side data) → a small live_only membership tail is a
    # documented join artifact (the b13 island_matters precedent), NOT
    # chased with bulk reads.
    go_wide = any(
        _type_matters_go_wide(t, keywords, vocab) for t in (all_trees or (tree,))
    )
    if tree.is_type("Creature"):
        for st in tree.card_subtypes:
            sl = st.lower()
            if sl in TRIBAL_SUBTYPES or (sl in CLASS_TRIBES and go_wide):
                add(
                    Signal(
                        signal_keys.TYPE_MATTERS,
                        "you",
                        sl.capitalize(),
                        "",
                        tree.name,
                        "low",
                    )
                )
    token_subjects: set[str] = set(structural_token_maker_type_subjects(tree))
    for c in tree.iter_concepts():
        if c.concept == "synth_token_maker_type_subject":
            token_subjects.update(c.subject)
    for sub in token_subjects:
        add(Signal(signal_keys.TYPE_MATTERS, "you", sub, "", tree.name, "low"))

    return out


def apply_membership_floor(
    trees: Sequence[ConceptTree],
    record: dict,
    out: list[Signal],
    add: Callable[[Signal], None],
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
) -> None:
    """The card-type / cares-about MEMBERSHIP floor — the broad LOW-conf
    "commander cares about X" lanes that are membership-agnostic in the
    structural crosswalk (a vanilla enchantment opens ``enchantments_matter``,
    an Equipment opens ``voltron_matters``, an artifact opens
    ``artifacts_matter``). Called ONCE per card, at the merge level
    (``signals.extract_signals``), over EVERY face's tree together —
    never per-face (ADR-0039 task #80 step 6: closes a step-3 regression).

    Per-face isolation previously lost the floor's own class-tribe / kill_engine
    cross-opens on a two-face card whose qualifying ability lives on a DIFFERENT
    face than its creature type: Flaxen Intruder // Welcome Home, Huatli Poet of
    Unity // Roar of the Fifth People, Kianne Dean of Substance // Imbraham Dean
    of Theory, Jadzi Steward of Fate // Oracle's Gift, and Eccentric Pestfinder //
    Turn Stones (a token-maker ability on the non-creature face never widened the
    creature face's own class-tribe go-wide — see
    :func:`extract_crosswalk_signals`'s ``all_trees`` param, the sibling fix for
    the UNGATED type_matters lane cross-open); Sheoldred // The True Scriptures
    (the repeatable destroy lives on the Enchantment — Saga face, never the
    Creature face — see :func:`_has_repeatable_kill_unit`). Each structural fact
    below is now unioned/OR'd across every face instead of read off one:
      * the ``_FLOOR_DETECTORS`` cares-about loop (gated by ``_IR_FLOOR_LANES``)
        runs over EVERY face's ``_kept(tree)``, not just one;
      * ``is_big_mana`` / ``is_kill_engine`` are True if ANY face structurally
        qualifies (``is_kill_engine`` additionally requires that SOME face is a
        Creature — the whole-card fact ``_apply_membership_floor`` itself already
        re-derives from ``record["type_line"]`` — while the repeatable-destroy
        unit can live on any OTHER face; see :func:`_has_repeatable_kill_unit`);
      * ``token_maker_subjects`` is the UNION of every face's structural
        token-maker subjects.
    ``record`` is the WHOLE-CARD bulk record (already multi-face-joined for
    ``type_line`` / ``oracle_text`` / ``all_parts`` — no per-face read needed
    there). A no-op when ``trees`` is empty (nothing to derive the floor from)."""
    if not trees:
        return
    name = record.get("name", "")

    def _add_floor(
        key: str, scope: str, subject: str, raw: str, conf: str = "high"
    ) -> None:
        # task #91 — cheat_from_top's LOW-conf byte-mirror (below) fires off
        # a bare "reveals the top card...onto the battlefield" oracle-regex
        # pair with no per-card structural check at all, so it can't tell
        # Vaevictis/Hans Eriksson/Lurking Predators's OWN-library reveal
        # (the mirror's intended target: a commander recursion engine, scope
        # "you") from Chaos Warp's "The owner of target permanent...reveals
        # the top card of THEIR library...they put it onto the battlefield"
        # (the SAME ParentTargetOwner beneficiary shape
        # :func:`_cheat_into_play`'s structural arm reads for it — the
        # target's owner benefits, not the caster, CR 108.3). Corpus-
        # verified: Chaos Warp is the ONLY commander-legal card whose tree
        # carries a ParentTargetOwner recipient AND fires this LOW-conf
        # mirror.
        if key == "cheat_from_top" and scope == "you":
            for tree in trees:
                for unit in tree.units:
                    if not any(
                        recipient_tag(c.node) == "ParentTargetOwner"
                        for c in unit.effects
                    ):
                        continue
                    override = _target_owner_beneficiary_scope(unit)
                    if override is not None:
                        scope = override
                        break
                else:
                    continue
                break
        add(Signal(key, scope, subject, raw, name, conf))

    for tree in trees:
        kept = _kept(tree)
        for det in _FLOOR_DETECTORS:
            if det.key in _IR_FLOOR_LANES and det.pattern.search(kept):
                _add_floor(det.key, det.scope, "", "")
    kept_oracle = _REMINDER_RX.sub(" ", get_oracle_text(record) or "")
    is_big_mana = any(_is_big_mana_tree(t) for t in trees)
    is_kill_engine = any(t.is_type("Creature") for t in trees) and any(
        _has_repeatable_kill_unit(t) for t in trees
    )
    token_maker_subjects: frozenset[str] = frozenset().union(
        *(_floor_token_maker_subjects(t, vocab) for t in trees)
    )
    _apply_membership_floor(
        record,
        name,
        vocab,
        kept_oracle,
        out,
        _add_floor,
        is_big_mana=is_big_mana,
        is_kill_engine=is_kill_engine,
        token_maker_subjects=token_maker_subjects,
    )
