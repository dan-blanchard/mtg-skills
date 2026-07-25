"""The stage: the ``_ARMS`` registry and ``apply_tree_synthesis`` entry point.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from mtg_utils._card_ir._substrate_purity import (
    SynthesizedNode,
    assert_substrate_pure,
    l1_identity,
)
from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._card_ir.tree_synthesis.combat import (
    _arm_attack_matters,
    _arm_base_power_ref_conjunctive,
    _arm_base_pt_have_become,
    _arm_base_pt_is_a_type_with,
    _arm_base_pt_mass_where_x,
    _arm_evasion_self,
    _arm_exalted_lone_attacker,
    _arm_exert_matters,
    _arm_firebending_matters,
    _arm_power_matters,
    _arm_pump_makers,
    _arm_station_matters,
    _arm_tap_untap_becomes,
    _arm_toughness_combat,
)
from mtg_utils._card_ir.tree_synthesis.control_stax import (
    _arm_cant_block_grant,
    _arm_color_hoser,
    _arm_damage_prevention,
    _arm_dont_own,
    _arm_legend_rule_off,
    _arm_opponent_counter_grant,
    _arm_opponent_exile_matters,
    _arm_sacrifice_protection,
    _arm_stax_taxes,
    _arm_superfriends_matters,
    _arm_symmetric_stax,
    _arm_targeting_matters,
    _arm_void_warp_makers,
)
from mtg_utils._card_ir.tree_synthesis.counters_tokens import (
    _arm_boon_plus_one_makers,
    _arm_convert_adapt_self_grow,
    _arm_counter_distribute,
    _arm_dropped_counter_move,
    _arm_keyword_counter,
    _arm_plus_one_makers,
    _arm_poison_matters,
    _arm_proliferate_matters,
    _arm_proliferate_remove_cost,
    _arm_self_counter_grow,
    _arm_self_power_scale,
    _arm_token_maker_type_subject,
)
from mtg_utils._card_ir.tree_synthesis.death_life import (
    _arm_death_matters,
    _arm_life_payment_insurance,
    _arm_lifegain_matters,
    _arm_mass_death_payoff,
    _arm_starting_life_matters,
)
from mtg_utils._card_ir.tree_synthesis.mana_ramp_lands import (
    _arm_bounce_tempo,
    _arm_dig_until,
    _arm_extra_land_drop,
    _arm_historic_matters,
    _arm_known_token_explore,
    _arm_known_token_ramp,
    _arm_land_fetch_ramp,
    _arm_ramp_dropped_add_mana_clause,
    _arm_ramp_grant_unimplemented_body,
    _arm_tutor,
    _arm_tutor_directed,
    _arm_unspent_mana,
    _arm_untap_engine,
)
from mtg_utils._card_ir.tree_synthesis.mechanics_misc import (
    _arm_celebration_matters,
    _arm_clue_matters,
    _arm_coven_matters,
    _arm_crimes_matter,
    _arm_curse_matters,
    _arm_known_token_counter_spell,
    _arm_known_token_impulse_top_play,
    _arm_known_token_lifeloss_contract,
    _arm_known_token_lifeloss_opponents,
    _arm_known_token_single_target_neutralize,
    _arm_known_token_topdeck_scry,
    _arm_known_token_ward_grant,
    _arm_outlaw_matters,
    _arm_suspect_makers,
    _arm_suspect_matters,
    _arm_suspend_matters,
    _arm_token_subtype_own_ref,
)
from mtg_utils._card_ir.tree_synthesis.spells_casting import (
    _arm_ability_copy,
    _arm_arcane_matters,
    _arm_becomes_target_src_opp,
    _arm_bending_cross,
    _arm_boon_creature_cast_trigger,
    _arm_cheat_choose_from_among_graveyard_origin,
    _arm_cheat_player_prefix_battlefield_put,
    _arm_cheat_synthetic_destiny_delayed_reveal,
    _arm_convoke_matters,
    _arm_cost_reduction,
    _arm_creature_cast_trigger,
    _arm_exhaust_matters,
    _arm_flash_matters,
    _arm_keyword_soup_same_true,
    _arm_lessons_matter,
    _arm_miracle_grant,
    _arm_noncombat_damage_payoff,
    _arm_opponent_cast_matters,
    _arm_per_target_payoff,
    _arm_recast_etb_bleed,
    _arm_spellcast_matters,
)
from mtg_utils._card_ir.tree_synthesis.types_tribal import (
    _arm_animate_artifact,
    _arm_color_change,
    _arm_colorless_matters,
    _arm_island_matters,
    _arm_keyword_tribe,
    _arm_keyword_tribe_any,
    _arm_land_creatures_dynamic_animate,
    _arm_manland,
    _arm_multicolor_matters,
    _arm_snow_matters,
    _arm_type_change,
    _arm_type_matters,
    _arm_typed_anthem_multi,
    _arm_vehicles_matter,
)
from mtg_utils._card_ir.tree_synthesis.value_engines import (
    _arm_b13_node_anchor,
    _arm_b13_raw_anchor,
    _arm_big_hand_makers,
    _arm_big_hand_matters,
    _arm_coin_flip_payoff,
    _arm_connive_makers,
    _arm_devil_token_quoted_grant,
    _arm_dice_makers,
    _arm_discover_makers,
    _arm_extra_turns,
    _arm_fight_makers,
    _arm_group_hug_draw,
    _arm_keranos_effect_structure,
    _arm_kill_engine,
    _arm_meld_pair,
    _arm_power_tap_engine,
    _arm_sac_alt_cost_pitch,
    _arm_sac_etb_self_sac,
    _arm_sac_keyword_cost,
    _arm_theft_makers,
    _arm_wants_cloning,
)
from mtg_utils._deck_forge._sweep_detectors import (
    STICKERS_MATTER_REGEX,
    VOID_WARP_MATTERS_REGEX,
)

# ── creatures_matter grammar-sprint stragglers (ADR-0039 task #82, post-
# deletion grammar sprint) ─────────────────────────────────────────────────
# Three ledgered ADR-0039 W8-finisher bridges (bridge_ledger.py) close via
# the SAME sole-source sweep-row shape the T8-misc-sweep rows below use --
# each is a whole-clause phase drop (a role=effect ``Unimplemented`` node
# with ZERO typed substructure beneath it, not even a nested count/target
# field) for a genuinely distinct creatures_matter idiom, corpus-bound to
# exactly its one pinned card (re-verified 2026-07-12, phase v0.20.0,
# 105,561 commander-legal Unimplemented nodes scanned):
#
#   * excess_count -- Superior Numbers' "deals damage ... equal to the
#     number of creatures you control in excess of the number of creatures
#     target opponent controls" (CR 107.3 computed value). The nearest
#     typed phase concept is a ``count.Difference{left, right}`` comparator
#     (22 corpus occurrences elsewhere) over two ``Ref``/``ObjectCount``
#     creature-count operands, the LEFT one a generic creatures-you-control
#     population -- the same shape every other "for each creature you
#     control" scaler feeds :func:`count_operand_filter`.
#   * diff_counters -- Sovereign Okinec Ahau's attack-triggered "for each
#     creature you control with power greater than that creature's base
#     power, put a number of +1/+1 counters on that creature equal to the
#     difference" (CR 122.1 counters, 613.4b base power reference). The
#     nearest typed phase concept is a per-object ``PutCounter`` distributed
#     over a generic creatures-you-control filter -- the ``PutCounterAll``
#     sibling shape :data:`_CREATURES_MATTER_MOD_TAGS` already reads for a
#     FIXED per-creature amount; here the amount is a per-object computed
#     difference instead.
#   * faceup_grant -- Whisperwood Elemental's activated "Sacrifice ~: Until
#     end of turn, face-up nontoken creatures you control gain '...'" (CR
#     113.10 ability grant, 702.164 manifest). The nearest typed phase
#     concept is a ``GrantAbility`` static def over a face-up/nontoken-
#     filtered team -- the SAME team-anthem shape the buried/Or-wrapped
#     ``_iter_creatures_matter_static_defs`` descent already reads for every
#     OTHER granted-ability team anthem.
#
# All three are gap-gated for free by the sweep-row's own sole-source
# philosophy (celebration_matters precedent): the SAME regex that corpus-
# verified census=1 in bridge_ledger.py anchors each row here too, so
# widening past its pin would be an explicit, auditable regex change, not
# silent drift.
_CREATURES_MATTER_EXCESS_COUNT_SYNTH_RX = re.compile(
    r"deals? damage to target creature equal to the number of creatures "
    r"you control in excess of the number of creatures target opponent "
    r"controls",
    re.IGNORECASE,
)
_CREATURES_MATTER_DIFF_COUNTERS_SYNTH_RX = re.compile(
    r"for each creature you control with power greater than that "
    r"creature's base power, put a number of \+1/\+1 counters",
    re.IGNORECASE,
)
_CREATURES_MATTER_FACEUP_GRANT_SYNTH_RX = re.compile(
    r"face-up nontoken creatures you control gain", re.IGNORECASE
)


# ── T8-misc-sweep bucket-B: the 9 Stage-2 closeout sweep rows ──────────────────
# Re-probed at v0.9.0 (double tag/mode census + substring scan, ADR-0036): NONE
# of the 9 formal kept-mirror rows has a competing structural read — each is
# the SOLE source for its key (the celebration_matters/coven_matters
# precedent: a plain regex relocation, no gap gate). Per-row grounding:
#
#   * attractions_matter — CR 717/701.51/701.52. Structural != live in BOTH
#     directions (26 phase-only Attraction permanents' own visit nodes vs 4
#     live-only word references) — the mirror is the producer.
#   * draft_spellbook — DD5 (Spellbook) + CR 905.1c/905.2b (Conspiracy
#     draft). NO Draft/Spellbook node in the census; digital vocabulary.
#   * free_plot — CR 702.170. Single-card lane (Fblthp); phase drops the
#     plot clause entirely.
#   * secret_writedown — CR 702.106a/b + 400.11b/108.3.
#   * stickers_matter — CR 123/122.1. The {TK}-cost/reference tail is
#     mirror-only; the typed ``PutSticker`` corroboration lives separately
#     in :func:`_stickers_structural` (a strict-subset ADD, unaffected).
#   * tap_down_blockers — CR 509.1c. Tromokratis's clause survives ONLY as
#     ``Unrecognized`` condition TEXT on a 1-holder ``CantBeBlocked``
#     static (probed live) — a typed read is still a raw-text match at
#     pop=1, no fidelity gain.
#   * timing_control — CR 117.1a + 307.5. Phase drops the cast-timing
#     statics (flash-permission auras, suspend timing checks).
#   * villainous_choice — CR 701.55a-d. The choice action is unstructured.
#   * void_warp_matters — CR 702.185 + 207.2c (void is an ability word, no
#     rules meaning). The payoff side has no node.
_ATTRACTIONS_SYNTH_RX = re.compile(r"\battraction\b|open an attraction", re.IGNORECASE)
_DRAFT_SPELLBOOK_SYNTH_RX = re.compile(r"\bdraft a card\b|spellbook", re.IGNORECASE)
_FREE_PLOT_SYNTH_RX = re.compile(r"plot cost is equal to its mana cost", re.IGNORECASE)
_SECRET_WRITEDOWN_SYNTH_RX = re.compile(
    r"secretly (?:write|choose|name)"
    r"|before the game begins[^.]*(?:write|name|choose)"
    r"|from outside the game",
    re.IGNORECASE,
)
_STICKERS_SYNTH_RX = re.compile(STICKERS_MATTER_REGEX, re.IGNORECASE)
_TAP_DOWN_BLOCKERS_SYNTH_RX = re.compile(r"can'?t be blocked unless all", re.IGNORECASE)
_TIMING_CONTROL_SYNTH_RX = re.compile(
    r"cast spells (?:and activate abilities )?only during their own"
    r"|spells? only any time they could cast a sorcery"
    r"|can cast spells only",
    re.IGNORECASE,
)
_VILLAINOUS_SYNTH_RX = re.compile(r"villainous choice", re.IGNORECASE)
_VOID_WARP_MATTERS_SYNTH_RX = re.compile(VOID_WARP_MATTERS_REGEX, re.IGNORECASE)

# (regex, arm_id, concept, scope, CR desc) — one factory builds all 9 arms so
# the shared "sole-source, no gate" shape (celebration_matters precedent)
# isn't hand-repeated 9 times; each still gets its own registered arm_id.
_SWEEP_SYNTH_ROWS: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (_ATTRACTIONS_SYNTH_RX, "attractions_matter", "you", "CR 717"),
    (_DRAFT_SPELLBOOK_SYNTH_RX, "draft_spellbook", "you", "DD5/CR 905"),
    (_FREE_PLOT_SYNTH_RX, "free_plot", "you", "CR 702.170"),
    (_SECRET_WRITEDOWN_SYNTH_RX, "secret_writedown", "you", "CR 702.106"),
    (_STICKERS_SYNTH_RX, "stickers_matter", "you", "CR 123"),
    (_TAP_DOWN_BLOCKERS_SYNTH_RX, "tap_down_blockers", "you", "CR 509.1c"),
    (_TIMING_CONTROL_SYNTH_RX, "timing_control", "any", "CR 117.1a"),
    (_VILLAINOUS_SYNTH_RX, "villainous_choice", "you", "CR 701.55"),
    (_VOID_WARP_MATTERS_SYNTH_RX, "void_warp_matters", "you", "CR 702.185"),
    (
        _CREATURES_MATTER_EXCESS_COUNT_SYNTH_RX,
        "creatures_matter_excess_count",
        "you",
        "CR 107.3",
    ),
    (
        _CREATURES_MATTER_DIFF_COUNTERS_SYNTH_RX,
        "creatures_matter_diff_counters",
        "you",
        "CR 122.1/613.4b",
    ),
    (
        _CREATURES_MATTER_FACEUP_GRANT_SYNTH_RX,
        "creatures_matter_faceup_grant",
        "you",
        "CR 113.10/702.164",
    ),
)


def _make_sweep_arm(rx: re.Pattern[str], arm_id: str, scope: str, cr: str) -> _Arm:
    def _arm(tree: ConceptTree) -> ConceptNode | None:
        oracle = _REMINDER.sub(" ", tree.oracle or "")
        if not rx.search(oracle):
            return None
        return _synthetic_concept(
            arm_id=arm_id,
            concept=f"synth_{arm_id}",
            scope=scope,
            subject=(),
            desc=f"bucket-B {arm_id} sweep row ({cr})",
        )

    return _arm


# ── the stage ─────────────────────────────────────────────────────────────────

# Each arm: ``tree -> ConceptNode | None``. Keyed by id for an input-side
# convergence check — an arm retires when phase begins parsing its
# clause (the synth would then duplicate a typed node the Tier-1 read already sees,
# so its ``_has_structural_death``-style gap gate drops its firing to 0).
_Arm = Callable[[ConceptTree], "ConceptNode | None"]
_ARMS: tuple[tuple[str, _Arm], ...] = (
    ("recast_etb_bleed", _arm_recast_etb_bleed),
    ("cost_reduction", _arm_cost_reduction),
    ("damage_prevention", _arm_damage_prevention),
    ("dig_until", _arm_dig_until),
    ("bending_cross", _arm_bending_cross),
    ("bounce_tempo", _arm_bounce_tempo),
    ("cheat_player_prefix_battlefield_put", _arm_cheat_player_prefix_battlefield_put),
    (
        "cheat_choose_from_among_graveyard_origin",
        _arm_cheat_choose_from_among_graveyard_origin,
    ),
    (
        "cheat_synthetic_destiny_delayed_reveal",
        _arm_cheat_synthetic_destiny_delayed_reveal,
    ),
    ("token_maker_type_subject", _arm_token_maker_type_subject),
    ("death_matters", _arm_death_matters),
    ("attack_matters", _arm_attack_matters),
    ("lifegain_matters", _arm_lifegain_matters),
    ("spellcast_matters", _arm_spellcast_matters),
    ("type_matters", _arm_type_matters),
    ("keyword_tribe", _arm_keyword_tribe),
    ("keyword_tribe_any", _arm_keyword_tribe_any),
    ("wants_cloning", _arm_wants_cloning),
    ("mass_death_payoff", _arm_mass_death_payoff),
    ("untap_engine", _arm_untap_engine),
    ("tutor_directed", _arm_tutor_directed),
    ("tutor", _arm_tutor),
    ("land_fetch_ramp", _arm_land_fetch_ramp),
    ("discover_makers", _arm_discover_makers),
    ("suspect_makers", _arm_suspect_makers),
    ("group_hug_draw", _arm_group_hug_draw),
    ("dice_makers", _arm_dice_makers),
    ("coin_flip_payoff", _arm_coin_flip_payoff),
    ("extra_land_drop", _arm_extra_land_drop),
    ("historic_matters", _arm_historic_matters),
    ("multicolor_matters", _arm_multicolor_matters),
    ("colorless_matters", _arm_colorless_matters),
    ("stax_taxes", _arm_stax_taxes),
    ("symmetric_stax", _arm_symmetric_stax),
    ("superfriends_matters", _arm_superfriends_matters),
    ("evasion_self", _arm_evasion_self),
    ("theft_makers", _arm_theft_makers),
    ("coven_matters", _arm_coven_matters),
    ("celebration_matters", _arm_celebration_matters),
    ("outlaw_matters", _arm_outlaw_matters),
    ("arcane_matters", _arm_arcane_matters),
    ("exalted_lone_attacker", _arm_exalted_lone_attacker),
    ("power_matters", _arm_power_matters),
    ("keyword_counter", _arm_keyword_counter),
    ("counter_distribute", _arm_counter_distribute),
    ("proliferate_matters", _arm_proliferate_matters),
    ("proliferate_remove_cost", _arm_proliferate_remove_cost),
    ("self_counter_grow", _arm_self_counter_grow),
    ("self_power_scale", _arm_self_power_scale),
    ("convert_adapt_self_counter_grow", _arm_convert_adapt_self_grow),
    ("dropped_counter_move", _arm_dropped_counter_move),
    ("plus_one_makers", _arm_plus_one_makers),
    ("boon_plus_one_makers", _arm_boon_plus_one_makers),
    ("poison_matters", _arm_poison_matters),
    ("island_matters", _arm_island_matters),
    ("animate_artifact", _arm_animate_artifact),
    ("color_change", _arm_color_change),
    ("vehicles_matter", _arm_vehicles_matter),
    ("manland", _arm_manland),
    ("land_creatures_dynamic_animate", _arm_land_creatures_dynamic_animate),
    ("curse_matters", _arm_curse_matters),
    ("clue_matters", _arm_clue_matters),
    ("token_subtype_own_ref", _arm_token_subtype_own_ref),
    ("suspend_matters", _arm_suspend_matters),
    ("flash_matters", _arm_flash_matters),
    ("crimes_matter", _arm_crimes_matter),
    ("suspect_matters", _arm_suspect_matters),
    ("pump_makers", _arm_pump_makers),
    ("opponent_exile_matters", _arm_opponent_exile_matters),
    ("color_hoser", _arm_color_hoser),
    ("type_change", _arm_type_change),
    ("b13_raw_anchor", _arm_b13_raw_anchor),
    ("b13_node_anchor", _arm_b13_node_anchor),
    ("opponent_counter_grant", _arm_opponent_counter_grant),
    ("cant_block_grant", _arm_cant_block_grant),
    ("void_warp_makers", _arm_void_warp_makers),
    ("sacrifice_protection", _arm_sacrifice_protection),
    ("sac_alt_cost_pitch", _arm_sac_alt_cost_pitch),
    ("sac_keyword_cost", _arm_sac_keyword_cost),
    ("sac_etb_self_sac_unimplemented", _arm_sac_etb_self_sac),
    ("devil_token_quoted_grant_dominant_verb_create", _arm_devil_token_quoted_grant),
    ("keranos_effect_structure_parse_failure", _arm_keranos_effect_structure),
    ("life_payment_insurance", _arm_life_payment_insurance),
    ("ability_copy", _arm_ability_copy),
    ("noncombat_damage_payoff", _arm_noncombat_damage_payoff),
    ("per_target_payoff", _arm_per_target_payoff),
    ("unspent_mana", _arm_unspent_mana),
    ("kill_engine", _arm_kill_engine),
    ("big_hand_makers", _arm_big_hand_makers),
    ("big_hand_matters", _arm_big_hand_matters),
    ("power_tap_engine", _arm_power_tap_engine),
    ("starting_life_matters", _arm_starting_life_matters),
    ("meld_pair", _arm_meld_pair),
    ("toughness_combat", _arm_toughness_combat),
    ("exert_matters", _arm_exert_matters),
    ("firebending_matters", _arm_firebending_matters),
    ("station_matters", _arm_station_matters),
    ("legend_rule_off", _arm_legend_rule_off),
    ("lessons_matter", _arm_lessons_matter),
    ("miracle_grant", _arm_miracle_grant),
    ("snow_matters", _arm_snow_matters),
    ("targeting_matters", _arm_targeting_matters),
    ("convoke_matters", _arm_convoke_matters),
    ("keyword_soup_same_true", _arm_keyword_soup_same_true),
    ("exhaust_matters", _arm_exhaust_matters),
    ("becomes_target_src_opp", _arm_becomes_target_src_opp),
    ("dont_own", _arm_dont_own),
    ("typed_anthem_multi", _arm_typed_anthem_multi),
    ("connive_makers", _arm_connive_makers),
    ("opponent_cast_matters", _arm_opponent_cast_matters),
    ("creature_cast_trigger", _arm_creature_cast_trigger),
    ("boon_creature_cast_trigger", _arm_boon_creature_cast_trigger),
    ("fight_makers", _arm_fight_makers),
    ("extra_turns", _arm_extra_turns),
    ("base_pt_have_become", _arm_base_pt_have_become),
    ("base_pt_is_a_type_with", _arm_base_pt_is_a_type_with),
    ("base_pt_mass_where_x", _arm_base_pt_mass_where_x),
    ("base_power_ref_conjunctive", _arm_base_power_ref_conjunctive),
    ("tap_untap_becomes", _arm_tap_untap_becomes),
    ("ramp_grant_unimplemented_body", _arm_ramp_grant_unimplemented_body),
    ("ramp_dropped_add_mana_clause", _arm_ramp_dropped_add_mana_clause),
    ("known_token_ramp", _arm_known_token_ramp),
    ("known_token_explore", _arm_known_token_explore),
    ("known_token_impulse_top_play", _arm_known_token_impulse_top_play),
    ("known_token_lifeloss_opponents", _arm_known_token_lifeloss_opponents),
    (
        "known_token_single_target_neutralize",
        _arm_known_token_single_target_neutralize,
    ),
    ("known_token_ward_grant", _arm_known_token_ward_grant),
    ("known_token_topdeck_scry", _arm_known_token_topdeck_scry),
    ("known_token_counter_spell", _arm_known_token_counter_spell),
    ("known_token_lifeloss_contract", _arm_known_token_lifeloss_contract),
    *(
        (arm_id, _make_sweep_arm(rx, arm_id, scope, cr))
        for rx, arm_id, scope, cr in _SWEEP_SYNTH_ROWS
    ),
)

SYNTHESIS_ARM_IDS: tuple[str, ...] = tuple(arm_id for arm_id, _ in _ARMS)


def synthesize_nodes(tree: ConceptTree) -> tuple[tuple[str, ConceptNode], ...]:
    """``(arm_id, node)`` for every arm that synthesizes a node on this tree.

    The convergence primitive: an arm that yields a node "fired" (found +
    filled a genuine gap). An arm firing on NO corpus card has CONVERGED —
    phase now parses the clause, so the arm's gap gate trips everywhere and
    it is retire-ready (ADR-0035 shrinking bridge).
    """
    fired: list[tuple[str, ConceptNode]] = []
    for arm_id, arm in _ARMS:
        node = arm(tree)
        if node is not None:
            fired.append((arm_id, node))
    return tuple(fired)


def apply_tree_synthesis(tree: ConceptTree) -> ConceptTree:
    """Add synthetic concept-nodes for genuine phase-parse (bucket-B) gaps.

    A Layer-2 stage on the signal path only (never ``compat_card``). Runs each
    registered arm once over the tree; every synthetic :class:`ConceptNode` it
    emits is collected into ONE
    new synthetic :class:`AbilityUnit` appended to the tree, so the phase units are
    left by identity. The synthetic unit's own ``node`` and its effect nodes are
    :class:`SynthesizedNode` markers, which :func:`_substrate_purity.l1_nodes`
    filters — so the phase L1 fingerprint is preserved (asserted here). A tree
    needing no synthesis is returned unchanged (identity).
    """
    fingerprint = l1_identity(tree)
    synthetic = [node for _arm_id, node in synthesize_nodes(tree)]
    if not synthetic:
        return tree
    synth_unit = AbilityUnit(
        origin="synth",
        index=len(tree.units),
        node=SynthesizedNode(arm_id="_unit", description="tree-synthesis unit"),
        kind=None,
        trigger_event=None,
        effects=tuple(synthetic),
        costs=(),
        statics=(),
    )
    result = replace(tree, units=(*tree.units, synth_unit))
    assert_substrate_pure(fingerprint, result)
    return result
