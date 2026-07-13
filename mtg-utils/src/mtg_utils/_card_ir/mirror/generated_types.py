"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).
One frozen typed dataclass per distinct mirror shape — complete coverage, no
generic fallback — plus a discriminated-union alias per tagged content_key and
the two dispatch tables the strict loader builds typed instances from.

Class naming: ``S_<ckey>`` for a struct shape, ``T_<ckey>__<tag>`` for a tagged
shape, ``U_<ckey>`` for the union of all tagged shapes at one content_key. The
``<root>`` card record is :class:`S_Root`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

__all__ = [
    "GENERATED_BY_CKEY",
    "GENERATED_BY_KEY",
    "JSON_TO_PY",
]


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_Root(TypedMirrorNode):
    abilities: list[S_abilities]
    card_type: S_card_type
    color_override: None | list[object]
    defense: None | str
    flavor_name: None
    keywords: list[MirrorVariant]
    legalities: S_legalities
    loyalty: None | str
    mana_cost: U_mana_cost
    name: str
    non_ability_text: None
    oracle_text: None | str
    power: None | U_power
    printings: list[object]
    replacements: list[S_replacements]
    scryfall_oracle_id: str
    static_abilities: list[S_static_abilities]
    toughness: None | U_toughness
    triggers: list[S_triggers]
    additional_cost: U_additional_cost = MISSING
    bracket_signals: S_bracket_signals = MISSING
    brawl_commander: bool = MISSING
    casting_options: list[S_casting_options | MirrorVariant] = MISSING
    casting_restrictions: list[U_casting_restrictions] = MISSING
    cleave_variant: S_cleave_variant = MISSING
    color_identity: list[object] = MISSING
    deck_copy_limit: U_deck_copy_limit = MISSING
    is_commander: bool = MISSING
    is_oathbreaker: bool = MISSING
    layout: str = MISSING
    metadata: S_metadata | MirrorVariant = MISSING
    modal: S_modal = MISSING
    parse_warnings: list[U_parse_warnings] = MISSING
    rarities: list[object] = MISSING
    rulings: list[S_rulings] = MISSING
    solve_condition: U_solve_condition = MISSING
    strive_cost: U_strive_cost = MISSING


@dataclass(frozen=True)
class S_AddKeywordUntilEndOfTurn(TypedMirrorNode):
    duration: str
    keyword: str
    restriction: MirrorVariant


@dataclass(frozen=True)
class S_Affinity(TypedMirrorNode):
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class S_AlternativeKeywordCost(TypedMirrorNode):
    cost: U_cost
    keyword: str
    frequency: str = MISSING


@dataclass(frozen=True)
class S_Awaken(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_BattlefieldTransition(TypedMirrorNode):
    enter: bool
    leave: bool
    qualifiers: list[MirrorVariant]


@dataclass(frozen=True)
class S_CantActivateDuring(TypedMirrorNode):
    exemption: str
    when: str
    who: str


@dataclass(frozen=True)
class S_CantBeActivated(TypedMirrorNode):
    exemption: str
    source_filter: U_source_filter
    who: str


@dataclass(frozen=True)
class S_CantCastDuring(TypedMirrorNode):
    when: str
    who: str


@dataclass(frozen=True)
class S_CantPayCost(TypedMirrorNode):
    cost: str | MirrorVariant
    who: str


@dataclass(frozen=True)
class S_CastFromHandFree(TypedMirrorNode):
    frequency: str
    origin: str


@dataclass(frozen=True)
class S_CastWithAlternativeCost(TypedMirrorNode):
    cost: U_cost
    timing_permission: str


@dataclass(frozen=True)
class S_CombatAlone(TypedMirrorNode):
    action: str
    requirement: str


@dataclass(frozen=True)
class S_Craft(TypedMirrorNode):
    cost: U_cost
    count: U_count
    materials: U_materials


@dataclass(frozen=True)
class S_Crew(TypedMirrorNode):
    once_per_turn: None | U_once_per_turn
    power: int


@dataclass(frozen=True)
class S_CrewContribution(TypedMirrorNode):
    actions: list[object]
    kind: str | MirrorVariant


@dataclass(frozen=True)
class S_DefilerCostReduction(TypedMirrorNode):
    color: str
    life_cost: int
    mana_reduction: U_mana_reduction


@dataclass(frozen=True)
class S_EntersWithAdditionalCounters(TypedMirrorNode):
    count: int
    counter_type: str


@dataclass(frozen=True)
class S_ExileCastPermission(TypedMirrorNode):
    cost: str
    frequency: str
    play_mode: str
    pool: str
    timing: str
    extra_cost: S_extra_cost = MISSING
    grants_flash: bool = MISSING
    mana_spend_permission: str = MISSING


@dataclass(frozen=True)
class S_GraveyardCastPermission(TypedMirrorNode):
    frequency: str
    play_mode: str
    extra_cost: S_extra_cost = MISSING
    graveyard_destination_replacement: str = MISSING


@dataclass(frozen=True)
class S_Impending(TypedMirrorNode):
    cost: U_cost
    counters: int


@dataclass(frozen=True)
class S_ImposeAdditionalCost(TypedMirrorNode):
    action: str
    cost: U_cost
    spell_filter: U_spell_filter


@dataclass(frozen=True)
class S_Keyword(TypedMirrorNode):
    count: int
    options: list[MirrorVariant]


@dataclass(frozen=True)
class S_ManaValue(TypedMirrorNode):
    comparator: str
    value: int


@dataclass(frozen=True)
class S_MaxAttackersEachCombat(TypedMirrorNode):
    defender: None | str
    max: int


@dataclass(frozen=True)
class S_MaxUntapPerType(TypedMirrorNode):
    filter: U_filter
    max: int


@dataclass(frozen=True)
class S_ModifyActivationLimit(TypedMirrorNode):
    keyword: str
    new_limit: int


@dataclass(frozen=True)
class S_ModifyCost(TypedMirrorNode):
    amount: U_amount
    mode: str
    spell_filter: None | U_spell_filter
    dynamic_count: U_dynamic_count = MISSING


@dataclass(frozen=True)
class S_MustBeBlockedByAll(TypedMirrorNode):
    pass


@dataclass(frozen=True)
class S_NumberRange(TypedMirrorNode):
    max: int
    min: int
    distinctness: str = MISSING


@dataclass(frozen=True)
class S_OnlyForSpellWithManaValue(TypedMirrorNode):
    comparator: str
    value: int


@dataclass(frozen=True)
class S_PerTurnCastLimit(TypedMirrorNode):
    max: int
    spell_filter: None | U_spell_filter
    who: str


@dataclass(frozen=True)
class S_PerTurnDrawLimit(TypedMirrorNode):
    max: int
    who: str


@dataclass(frozen=True)
class S_Prototype(TypedMirrorNode):
    cost: U_cost
    power: int
    toughness: int


@dataclass(frozen=True)
class S_ReduceAbilityCost(TypedMirrorNode):
    amount: int
    exemption: str
    keyword: str
    mode: str
    activator: U_activator = MISSING
    dynamic_count: U_dynamic_count = MISSING
    minimum_mana: int = MISSING


@dataclass(frozen=True)
class S_ReduceActionCost(TypedMirrorNode):
    action: str
    amount: int
    mode: str


@dataclass(frozen=True)
class S_Reinforce(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_RestrictLibrarySearchToTop(TypedMirrorNode):
    count: int
    who: str


@dataclass(frozen=True)
class S_SpellFromZone(TypedMirrorNode):
    polarity: str
    zone: str


@dataclass(frozen=True)
class S_SpellMatchingCostCriteria(TypedMirrorNode):
    criteria: list[MirrorVariant]
    spell_type: str


@dataclass(frozen=True)
class S_SpellTypeOrAbilityActivation(TypedMirrorNode):
    ability: str
    spell_type: str


@dataclass(frozen=True)
class S_SpellWithColorCount(TypedMirrorNode):
    comparator: str
    count: int


@dataclass(frozen=True)
class S_SpellWithKeywordKindFromZone(TypedMirrorNode):
    kind: str
    zone: str


@dataclass(frozen=True)
class S_SpellWithManaValue(TypedMirrorNode):
    comparator: str
    value: int


@dataclass(frozen=True)
class S_SpendManaAsAnyColor(TypedMirrorNode):
    pass


@dataclass(frozen=True)
class S_Splice(TypedMirrorNode):
    cost: U_cost
    subtype: str


@dataclass(frozen=True)
class S_StepEndUnspentMana(TypedMirrorNode):
    action: str | MirrorVariant
    filter: None | str


@dataclass(frozen=True)
class S_SuppressTriggers(TypedMirrorNode):
    events: list[object]
    source_filter: U_source_filter


@dataclass(frozen=True)
class S_Suspend(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_TopOfLibraryCastPermission(TypedMirrorNode):
    alt_cost: None | U_alt_cost
    frequency: str
    play_mode: str


@dataclass(frozen=True)
class S_TriggerOnSpend(TypedMirrorNode):
    ability: S_ability
    restriction: str | MirrorVariant


@dataclass(frozen=True)
class S_Typecycling(TypedMirrorNode):
    cost: U_cost
    subtype: str


@dataclass(frozen=True)
class S_UntilNextStepOf(TypedMirrorNode):
    player: U_player
    step: str


@dataclass(frozen=True)
class S_abilities(TypedMirrorNode):
    condition: None | U_condition
    cost: None | U_cost
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    ability_tag: U_ability_tag = MISSING
    activation_restrictions: list[U_activation_restrictions] = MISSING
    activation_zone: str = MISSING
    activator_filter: U_activator_filter = MISSING
    cant_be_copied: bool = MISSING
    consumes_source: bool = MISSING
    cost_reduction: S_cost_reduction = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    is_mana_ability: bool = MISSING
    min_x_value: int = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    repeat_until: U_repeat_until = MISSING
    starting_with: str = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_ability(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None


@dataclass(frozen=True)
class S_additional_token_spec(TypedMirrorNode):
    characteristics: S_characteristics
    controller: int
    enter_with_counters: list[U_enter_with_counters]
    enters_attacking: bool
    sacrifice_at: None
    script_name: str
    source_id: int
    static_abilities: list[S_static_abilities]
    tapped: bool


@dataclass(frozen=True)
class S_bracket_signals(TypedMirrorNode):
    efficient_tutor: bool
    extra_turn: bool
    game_changer: bool
    mass_land_denial: bool


@dataclass(frozen=True)
class S_branches(TypedMirrorNode):
    condition: None
    cost: None
    description: None | str
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    iteration_kind_binding: U_iteration_kind_binding = MISSING
    player_scope: U_player_scope = MISSING
    target_choice_timing: str = MISSING


@dataclass(frozen=True)
class S_card_type(TypedMirrorNode):
    core_types: list[object]
    subtypes: list[object]
    supertypes: list[object]


@dataclass(frozen=True)
class S_cards(TypedMirrorNode):
    count: U_count
    duplicate_of: U_duplicate_of = MISSING
    name: str = MISSING


@dataclass(frozen=True)
class S_casting_options(TypedMirrorNode):
    kind: str
    condition: U_condition = MISSING
    cost: U_cost = MISSING


@dataclass(frozen=True)
class S_characteristics(TypedMirrorNode):
    colors: list[U_colors]
    core_types: list[object]
    display_name: str
    keywords: list[MirrorVariant]
    power: None | int
    subtypes: list[object]
    supertypes: list[object]
    toughness: None | int


@dataclass(frozen=True)
class S_chosen_pile_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None
    player_scope: U_player_scope = MISSING


@dataclass(frozen=True)
class S_cleave_variant(TypedMirrorNode):
    abilities: list[S_abilities]
    replacements: list[S_replacements]
    static_abilities: list[S_static_abilities]
    triggers: list[S_triggers]


@dataclass(frozen=True)
class S_cost_reduction(TypedMirrorNode):
    amount_per: int
    count: U_count
    condition: U_condition = MISSING


@dataclass(frozen=True)
class S_counter_filter(TypedMirrorNode):
    counter_type: str
    threshold: int


@dataclass(frozen=True)
class S_data(TypedMirrorNode):
    candidate_filter: U_candidate_filter = MISSING
    comparator: str = MISSING
    condition: U_condition = MISSING
    cost: U_cost = MISSING
    costs: list[U_costs] = MISSING
    count: int = MISSING
    counters: U_counters = MISSING
    filter: U_filter = MISSING
    max_iterations: int = MISSING
    maximum: int = MISSING
    minimum: int = MISSING
    outcome_template: S_outcome_template = MISSING
    repeatable: bool = MISSING
    stop_on_duplicate_exiled_names: bool = MISSING
    stop_on_put_to_hand: bool = MISSING
    value: U_value = MISSING


@dataclass(frozen=True)
class S_decline(TypedMirrorNode):
    condition: None
    cost: None
    description: None | str
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None


@dataclass(frozen=True)
class S_definition(TypedMirrorNode):
    condition: None | U_condition
    description: None | str
    ability_tag: U_ability_tag = MISSING
    activation_restrictions: list[U_activation_restrictions] = MISSING
    active_zones: list[object] = MISSING
    affected: None | U_affected = MISSING
    affected_zone: None = MISSING
    characteristic_defining: bool = MISSING
    cost: None | U_cost = MISSING
    cost_reduction: S_cost_reduction = MISSING
    duration: None | str = MISSING
    effect: U_effect = MISSING
    effect_zone: None = MISSING
    forward_result: bool = MISSING
    is_mana_ability: bool = MISSING
    kind: str = MISSING
    mode: str | MirrorVariant = MISSING
    modifications: list[U_modifications] = MISSING
    multi_target: S_multi_target = MISSING
    optional: bool = MISSING
    optional_targeting: bool = MISSING
    player_scope: U_player_scope = MISSING
    sub_ability: None | S_sub_ability = MISSING
    target_choice_timing: str = MISSING
    target_prompt: None = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_effect(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    is_mana_ability: bool = MISSING
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_else_ability(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None | str
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING


@dataclass(frozen=True)
class S_ensure_token_specs(TypedMirrorNode):
    characteristics: S_characteristics
    controller: int
    enter_with_counters: list[U_enter_with_counters]
    enters_attacking: bool
    sacrifice_at: None
    script_name: str
    source_id: int
    static_abilities: list[S_static_abilities]
    tapped: bool


@dataclass(frozen=True)
class S_execute(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    ability_tag: U_ability_tag = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    is_mana_ability: bool = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    repeat_until: U_repeat_until = MISSING
    starting_with: str = MISSING
    target_choice_timing: str = MISSING
    target_chooser: U_target_chooser = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_extra_cost(TypedMirrorNode):
    cost: U_cost
    mode: str


@dataclass(frozen=True)
class S_face_down_profile(TypedMirrorNode):
    body: str = MISSING
    extra_core_types: list[object] = MISSING
    power: int = MISSING
    subtypes: list[object] = MISSING
    toughness: int = MISSING


@dataclass(frozen=True)
class S_filter(TypedMirrorNode):
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class S_legalities(TypedMirrorNode):
    brawl: str = MISSING
    commander: str = MISSING
    duel: str = MISSING
    historic: str = MISSING
    legacy: str = MISSING
    modern: str = MISSING
    oathbreaker: str = MISSING
    pauper: str = MISSING
    paupercommander: str = MISSING
    pioneer: str = MISSING
    premodern: str = MISSING
    standard: str = MISSING
    standardbrawl: str = MISSING
    timeless: str = MISSING
    vintage: str = MISSING


@dataclass(frozen=True)
class S_lose_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    player_scope: U_player_scope = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_metadata(TypedMirrorNode):
    related_token_ids: list[object]
    source_printing_ids: list[object]


@dataclass(frozen=True)
class S_modal(TypedMirrorNode):
    allow_repeat_modes: bool
    chooser: U_chooser
    max_choices: int
    min_choices: int
    mode_count: int
    mode_descriptions: list[object]
    constraints: list[U_constraints] = MISSING
    dynamic_max_choices: U_dynamic_max_choices = MISSING
    entwine_cost: U_entwine_cost = MISSING
    mode_costs: list[U_mode_costs] = MISSING
    mode_pawprints: list[object] = MISSING
    selection: U_selection = MISSING


@dataclass(frozen=True)
class S_mode_abilities(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    is_mana_ability: bool = MISSING
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    target_choice_timing: str = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_modification(TypedMirrorNode):
    kind: str
    amount: U_amount = MISSING
    creature_subtypes: list[object] = MISSING
    keywords: list[MirrorVariant] = MISSING
    mode: str = MISSING
    power: int = MISSING
    power_delta: int = MISSING
    toughness: int = MISSING
    toughness_delta: int = MISSING


@dataclass(frozen=True)
class S_multi_target(TypedMirrorNode):
    max: None | U_max
    min: int | U_min


@dataclass(frozen=True)
class S_on_decline(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None
    duration: None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None


@dataclass(frozen=True)
class S_or_trigger(TypedMirrorNode):
    batched: bool
    condition: None
    constraint: None
    damage_kind: str
    description: None
    destination: None
    execute: None
    mode: str
    optional: bool
    origin: None
    phase: None
    secondary: bool
    trigger_zones: list[object]
    valid_card: U_valid_card
    valid_source: None
    valid_target: None | U_valid_target


@dataclass(frozen=True)
class S_outcome_template(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None


@dataclass(frozen=True)
class S_per_choice_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    target_choice_timing: str = MISSING


@dataclass(frozen=True)
class S_profile(TypedMirrorNode):
    extra_core_types: list[object] = MISSING
    power: int = MISSING
    subtypes: list[object] = MISSING
    toughness: int = MISSING


@dataclass(frozen=True)
class S_replacement(TypedMirrorNode):
    condition: None | U_condition
    description: None | str
    event: str
    execute: None | S_execute
    mode: U_mode
    valid_card: None | U_valid_card
    combat_scope: str = MISSING
    consume_on_apply: bool = MISSING
    damage_modification: U_damage_modification = MISSING
    damage_source_filter: U_damage_source_filter = MISSING
    damage_target_filter: MirrorVariant = MISSING
    destination_zone: str = MISSING
    expiry: U_expiry = MISSING
    quantity_modification: U_quantity_modification = MISSING
    shield_kind: MirrorVariant = MISSING
    token_owner_redirect: str = MISSING
    token_owner_scope: str = MISSING


@dataclass(frozen=True)
class S_replacements(TypedMirrorNode):
    condition: None | U_condition
    description: None | str
    event: str
    execute: None | S_execute
    mode: U_mode
    valid_card: None | U_valid_card
    additional_token_spec: S_additional_token_spec = MISSING
    combat_scope: str = MISSING
    counter_match: U_counter_match = MISSING
    damage_modification: U_damage_modification = MISSING
    damage_source_filter: U_damage_source_filter = MISSING
    damage_target_filter: str | MirrorVariant = MISSING
    destination_zone: str = MISSING
    ensure_token_specs: list[S_ensure_token_specs] = MISSING
    enters_under: str = MISSING
    mana_modification: U_mana_modification = MISSING
    mana_replacement_scope: U_mana_replacement_scope = MISSING
    quantity_modification: U_quantity_modification = MISSING
    redirect_target: U_redirect_target = MISSING
    shield_kind: MirrorVariant = MISSING
    token_owner_scope: str = MISSING
    valid_player: str = MISSING


@dataclass(frozen=True)
class S_requirement(TypedMirrorNode):
    requirement: str
    comparator: str = MISSING
    count: int = MISSING
    stat: str = MISSING
    value: int = MISSING


@dataclass(frozen=True)
class S_results(TypedMirrorNode):
    effect: S_effect
    max: int
    min: int


@dataclass(frozen=True)
class S_rulings(TypedMirrorNode):
    date: str
    text: str


@dataclass(frozen=True)
class S_scale(TypedMirrorNode):
    counter_type: str
    scale_property: str


@dataclass(frozen=True)
class S_split(TypedMirrorNode):
    primary_count: int
    primary_destination: str
    rest_destination: str
    primary_enter_tapped: bool = MISSING


@dataclass(frozen=True)
class S_static_abilities(TypedMirrorNode):
    active_zones: list[object]
    affected: None | U_affected
    affected_zone: None | str
    characteristic_defining: bool
    condition: None | U_condition
    description: None | str
    effect_zone: None
    mode: str | MirrorVariant
    modifications: list[U_modifications]
    attack_defended: str = MISSING
    bypass_beneficiary: str = MISSING
    per_player_condition: U_per_player_condition = MISSING


@dataclass(frozen=True)
class S_static_def(TypedMirrorNode):
    active_zones: list[object]
    affected: None
    affected_zone: None
    characteristic_defining: bool
    condition: None
    description: None
    effect_zone: None
    mode: str
    modifications: list[U_modifications]


@dataclass(frozen=True)
class S_statics(TypedMirrorNode):
    active_zones: list[object]
    affected: None | U_affected
    affected_zone: None
    characteristic_defining: bool
    condition: None
    description: str
    effect_zone: None
    mode: str | MirrorVariant
    modifications: list[U_modifications]


@dataclass(frozen=True)
class S_sub_ability(TypedMirrorNode):
    condition: None | U_condition
    cost: None | U_cost
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    ability_tag: U_ability_tag = MISSING
    activation_restrictions: list[U_activation_restrictions] = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    is_mana_ability: bool = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    starting_with: str = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_trigger(TypedMirrorNode):
    batched: bool
    condition: None | U_condition
    constraint: None | U_constraint
    damage_kind: str
    description: None | str
    destination: None | str
    execute: None | S_execute
    mode: str | MirrorVariant
    optional: bool
    origin: None | str
    phase: None | str
    secondary: bool
    trigger_zones: list[object]
    valid_card: None | U_valid_card
    valid_source: None | U_valid_source
    valid_target: None | U_valid_target
    attack_target_filter: str = MISSING
    coin_flip_result: str = MISSING
    counter_filter: MirrorVariant = MISSING
    spell_cast_origin: U_spell_cast_origin = MISSING
    unless_pay: S_unless_pay = MISSING
    zone_change_clauses: list[S_zone_change_clauses] = MISSING


@dataclass(frozen=True)
class S_triggers(TypedMirrorNode):
    batched: bool
    condition: None | U_condition
    constraint: None | U_constraint
    damage_kind: str
    description: None | str
    destination: None | str
    execute: None | S_execute
    mode: str | MirrorVariant
    optional: bool
    origin: None | str
    phase: None | str
    secondary: bool
    trigger_zones: list[object]
    valid_card: None | U_valid_card
    valid_source: None | U_valid_source
    valid_target: None | U_valid_target
    attack_target_filter: str = MISSING
    clash_result: str = MISSING
    coin_flip_result: str = MISSING
    counter_filter: S_counter_filter | MirrorVariant = MISSING
    damage_amount: list[object] = MISSING
    destination_constraint: U_destination_constraint = MISSING
    die_result: MirrorVariant = MISSING
    expend_threshold: int = MISSING
    life_amount: list[object] = MISSING
    origin_zones: list[object] = MISSING
    player_actions: list[object] = MISSING
    spell_cast_origin: U_spell_cast_origin = MISSING
    taps_for_mana_produced: list[object] = MISSING
    unless_pay: S_unless_pay = MISSING
    valid_subject_player: U_valid_subject_player = MISSING
    zone_change_clauses: list[S_zone_change_clauses] = MISSING


@dataclass(frozen=True)
class S_unchosen_pile_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None


@dataclass(frozen=True)
class S_unless_pay(TypedMirrorNode):
    cost: U_cost
    payer: U_payer


@dataclass(frozen=True)
class S_win_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: None | str
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None
    target_prompt: None
    is_mana_ability: bool = MISSING
    sub_link: str = MISSING


@dataclass(frozen=True)
class S_zone_change_clauses(TypedMirrorNode):
    origin: U_origin
    valid_card: U_valid_card
    destination: str = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_ActivateTagged__Equip(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equip"


@dataclass(frozen=True)
class T_ActivateTagged__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_Bestow__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Bestow__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Blitz__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Blitz__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Bloodthirst__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    data: int


@dataclass(frozen=True)
class T_Bloodthirst__X(TypedMirrorNode):
    _tag: ClassVar[str | None] = "X"


@dataclass(frozen=True)
class T_Buyback__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Buyback__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Cleave__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_CommanderNinjutsu__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Companion__EvenManaValues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EvenManaValues"


@dataclass(frozen=True)
class T_Companion__MaxPermanentManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MaxPermanentManaValue"
    data: int


@dataclass(frozen=True)
class T_Companion__MinManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MinManaValue"
    data: int


@dataclass(frozen=True)
class T_Companion__NoRepeatedManaSymbols(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoRepeatedManaSymbols"


@dataclass(frozen=True)
class T_Companion__OddManaValues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OddManaValues"


@dataclass(frozen=True)
class T_Companion__PermanentsHaveActivatedAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PermanentsHaveActivatedAbilities"


@dataclass(frozen=True)
class T_Companion__SharedCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharedCardType"


@dataclass(frozen=True)
class T_CumulativeUpkeep__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_CumulativeUpkeep__EffectCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCost"
    effect: U_effect


@dataclass(frozen=True)
class T_CumulativeUpkeep__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None
    zone: str


@dataclass(frozen=True)
class T_CumulativeUpkeep__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_CumulativeUpkeep__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_CumulativeUpkeep__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_CumulativeUpkeep__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_Cycling__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Cycling__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Dash__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Disguise__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Disturb__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Echo__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Echo__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Embalm__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Emerge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Enchant__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_Enchant__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_Enchant__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_Enchant__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_Enchant__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Encore__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Encore__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Encore__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_Entwine__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_EqualTo__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_EqualTo__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_Equip__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Equip__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_Escalate__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_Escalate__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_Escalate__TapCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TapCreatures"
    filter: U_filter
    requirement: S_requirement


@dataclass(frozen=True)
class T_Escape__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Eternalize__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Eternalize__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Evoke__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Evoke__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Firebending__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_Firebending__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_Flashback__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Flashback__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Foretell__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Foretell__SelfManaCostReduced(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCostReduced"
    reduction: int


@dataclass(frozen=True)
class T_Fortify__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Freerunning__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Gift__Card(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Card"


@dataclass(frozen=True)
class T_Gift__Food(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Food"


@dataclass(frozen=True)
class T_Gift__TappedFish(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TappedFish"


@dataclass(frozen=True)
class T_Gift__Treasure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Treasure"


@dataclass(frozen=True)
class T_Harmonize__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Harmonize__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_HexproofFrom__CardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardType"
    data: str


@dataclass(frozen=True)
class T_HexproofFrom__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"


@dataclass(frozen=True)
class T_HexproofFrom__Color(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Color"
    data: str


@dataclass(frozen=True)
class T_HexproofFrom__Quality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Quality"
    data: str


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Boast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Boast"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Exhaust(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exhaust"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Outlast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Outlast"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_Kicker__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_LevelUp__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Madness__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Mayhem__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Mayhem__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Megamorph__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Miracle__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Miracle__SelfManaCostReduced(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCostReduced"
    reduction: int


@dataclass(frozen=True)
class T_Mobilize__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_Mobilize__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_MoreThanMeetsTheEye__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Morph__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Mutate__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Ninjutsu__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Offspring__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Outlast__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Overload__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Partner__CharacterSelect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CharacterSelect"


@dataclass(frozen=True)
class T_Partner__ChooseABackground(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseABackground"


@dataclass(frozen=True)
class T_Partner__DoctorsCompanion(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoctorsCompanion"


@dataclass(frozen=True)
class T_Partner__FriendsForever(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FriendsForever"


@dataclass(frozen=True)
class T_Partner__Generic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Generic"


@dataclass(frozen=True)
class T_Partner__With(TypedMirrorNode):
    _tag: ClassVar[str | None] = "With"
    data: str


@dataclass(frozen=True)
class T_Plot__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Prowl__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Quality__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_Quality__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_Quality__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Reconfigure__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Recover__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Replicate__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Replicate__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Scavenge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Scavenge__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Sneak__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Specialize__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Spectacle__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Squad__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Surge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Transfigure__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Transmute__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Unearth__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Ward__Compound(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Compound"
    data: list[U_data | S_data | MirrorVariant]


@dataclass(frozen=True)
class T_Ward__DiscardCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DiscardCard"


@dataclass(frozen=True)
class T_Ward__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Ward__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    data: int


@dataclass(frozen=True)
class T_Ward__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    data: S_data


@dataclass(frozen=True)
class T_Ward__Waterbend(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Waterbend"
    data: U_data


@dataclass(frozen=True)
class T_Warp__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_WebSlinging__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_ability_tag__Augment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Augment"


@dataclass(frozen=True)
class T_ability_tag__Backup(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Backup"


@dataclass(frozen=True)
class T_ability_tag__Boast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Boast"


@dataclass(frozen=True)
class T_ability_tag__Cycling(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cycling"


@dataclass(frozen=True)
class T_ability_tag__Equip(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equip"


@dataclass(frozen=True)
class T_ability_tag__Evolve(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Evolve"


@dataclass(frozen=True)
class T_ability_tag__Exhaust(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exhaust"


@dataclass(frozen=True)
class T_ability_tag__Outlast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Outlast"


@dataclass(frozen=True)
class T_ability_tag__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_action__exile_from_pool(TypedMirrorNode):
    _tag: ClassVar[str | None] = "exile_from_pool"
    up_to: bool
    zone: str


@dataclass(frozen=True)
class T_action__put_counter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "put_counter"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_activation_restrictions__AsInstant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AsInstant"


@dataclass(frozen=True)
class T_activation_restrictions__AsSorcery(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AsSorcery"


@dataclass(frozen=True)
class T_activation_restrictions__BeforeAttackersDeclared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeAttackersDeclared"


@dataclass(frozen=True)
class T_activation_restrictions__BeforeCombatDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeCombatDamage"


@dataclass(frozen=True)
class T_activation_restrictions__ClassLevelIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClassLevelIs"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__CounterThreshold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterThreshold"
    data: S_data


@dataclass(frozen=True)
class T_activation_restrictions__DuringCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringCombat"


@dataclass(frozen=True)
class T_activation_restrictions__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_activation_restrictions__DuringYourUpkeep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourUpkeep"


@dataclass(frozen=True)
class T_activation_restrictions__IsSolved(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsSolved"


@dataclass(frozen=True)
class T_activation_restrictions__LevelCounterRange(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LevelCounterRange"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__MatchesCardCastTiming(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesCardCastTiming"


@dataclass(frozen=True)
class T_activation_restrictions__MaxTimesEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MaxTimesEachTurn"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__OnlyOnce(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnce"


@dataclass(frozen=True)
class T_activation_restrictions__OnlyOnceEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnceEachTurn"


@dataclass(frozen=True)
class T_activation_restrictions__RequiresCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RequiresCondition"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_source_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_activator__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_activator_filter__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_activator_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_activity__ActivateAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ActivateAbilities"
    exemption: str
    only_tag: U_only_tag = MISSING


@dataclass(frozen=True)
class T_activity__Attack(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attack"
    defended: str


@dataclass(frozen=True)
class T_activity__CastOnlyFromZones(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastOnlyFromZones"
    allowed_zones: list[object]


@dataclass(frozen=True)
class T_activity__CastSpells(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastSpells"
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_activity__ProhibitPlayFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProhibitPlayFromZone"
    zone: str


@dataclass(frozen=True)
class T_additional_cost__Choice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Choice"
    data: list[U_data | S_data | MirrorVariant]


@dataclass(frozen=True)
class T_additional_cost__Kicker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Kicker"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_additional_cost__Optional(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Optional"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_additional_cost__Required(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Required"
    data: U_data


@dataclass(frozen=True)
class T_additional_filter__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_additional_filter__IsChosenCreatureType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCreatureType"


@dataclass(frozen=True)
class T_additional_filter__MatchesLastChosenCardPredicate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesLastChosenCardPredicate"


@dataclass(frozen=True)
class T_additional_modifications__AddColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddColor"
    color: str


@dataclass(frozen=True)
class T_additional_modifications__AddCounterOnEnter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddCounterOnEnter"
    count: U_count
    counter_type: str
    if_type: None | str


@dataclass(frozen=True)
class T_additional_modifications__AddKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_additional_modifications__AddStaticMode(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddStaticMode"
    mode: MirrorVariant


@dataclass(frozen=True)
class T_additional_modifications__AddSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddSubtype"
    subtype: str


@dataclass(frozen=True)
class T_additional_modifications__AddSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddSupertype"
    supertype: str


@dataclass(frozen=True)
class T_additional_modifications__AddType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddType"
    core_type: str


@dataclass(frozen=True)
class T_additional_modifications__GrantAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantAbility"
    definition: S_definition


@dataclass(frozen=True)
class T_additional_modifications__GrantStaticAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantStaticAbility"
    definition: S_definition


@dataclass(frozen=True)
class T_additional_modifications__GrantTrigger(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantTrigger"
    trigger: S_trigger


@dataclass(frozen=True)
class T_additional_modifications__RemoveAllSubtypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllSubtypes"
    set: str


@dataclass(frozen=True)
class T_additional_modifications__RemoveManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveManaCost"


@dataclass(frozen=True)
class T_additional_modifications__RemoveSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveSupertype"
    supertype: str


@dataclass(frozen=True)
class T_additional_modifications__RetainPrintedAbilityFromSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RetainPrintedAbilityFromSource"
    source_ability_index: int


@dataclass(frozen=True)
class T_additional_modifications__RetainPrintedTriggerFromSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RetainPrintedTriggerFromSource"
    source_trigger_index: int


@dataclass(frozen=True)
class T_additional_modifications__SetCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetCardTypes"
    core_types: list[object]


@dataclass(frozen=True)
class T_additional_modifications__SetColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetColor"
    colors: list[U_colors]


@dataclass(frozen=True)
class T_additional_modifications__SetName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetName"
    name: str


@dataclass(frozen=True)
class T_additional_modifications__SetPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetPower"
    value: int


@dataclass(frozen=True)
class T_additional_modifications__SetPowerDynamic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetPowerDynamic"
    value: U_value


@dataclass(frozen=True)
class T_additional_modifications__SetStartingLoyalty(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetStartingLoyalty"
    value: int


@dataclass(frozen=True)
class T_additional_modifications__SetToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetToughness"
    value: int


@dataclass(frozen=True)
class T_additional_modifications__SetToughnessDynamic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetToughnessDynamic"
    value: U_value


@dataclass(frozen=True)
class T_affected__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_affected__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_affected__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_affected__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_affected__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


@dataclass(frozen=True)
class T_affected__LastCreated(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastCreated"


@dataclass(frozen=True)
class T_affected__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_affected__OriginalSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OriginalSource"


@dataclass(frozen=True)
class T_affected__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_affected__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_affected__PlayerWhoChoseLabel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerWhoChoseLabel"
    label: str


@dataclass(frozen=True)
class T_affected__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_affected__SourceOrPaired(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceOrPaired"


@dataclass(frozen=True)
class T_affected__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_affected__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_affected__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_affected__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_affected_players__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_affected_players__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_affected_players__OpponentsOfSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentsOfSourceController"


@dataclass(frozen=True)
class T_affected_players__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_affected_players__ParentTargetedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetedPlayer"


@dataclass(frozen=True)
class T_affected_players__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_affected_players__TargetedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetedPlayer"


@dataclass(frozen=True)
class T_alt_ability_cost__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_alt_ability_cost__KeywordCostOfCastSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "KeywordCostOfCastSpell"
    keyword: str


@dataclass(frozen=True)
class T_alt_ability_cost__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_alt_cost__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_amount__ClampMin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClampMin"
    inner: U_inner
    minimum: int


@dataclass(frozen=True)
class T_amount__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_amount__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_amount__DivideRounded(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DivideRounded"
    divisor: int
    inner: U_inner
    rounding: str


@dataclass(frozen=True)
class T_amount__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_amount__Max(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Max"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_amount__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_amount__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_amount__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_amount__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_amount_dynamic__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_attach_to__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_attach_to__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_attachment__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_attachment__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_attachment__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_attachment__ParentTargetSlot(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetSlot"
    index: int


@dataclass(frozen=True)
class T_attachment__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_attachment__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_attachment__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_attacker_restriction__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_attacker_restriction__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_attr__BattlefieldEntriesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BattlefieldEntriesThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_attr__CardsDrawnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDrawnThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_attr__HandSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSize"
    player: U_player


@dataclass(frozen=True)
class T_attr__LifeLostThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeLostThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_attr__LifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeTotal"
    player: U_player


@dataclass(frozen=True)
class T_attr__PlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCounter"
    kind: str
    scope: str


@dataclass(frozen=True)
class T_base__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_base__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None
    zone: str


@dataclass(frozen=True)
class T_base__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_base__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_base__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_base__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_blockers__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_by__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_candidate_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_cap__OnlyOnceEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnceEachTurn"


@dataclass(frozen=True)
class T_card_filter__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_card_filter__None(TypedMirrorNode):
    _tag: ClassVar[str | None] = "None"


@dataclass(frozen=True)
class T_card_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_card_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_cast_cost_raise__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_casting_restrictions__AfterBlockersDeclared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AfterBlockersDeclared"


@dataclass(frozen=True)
class T_casting_restrictions__AfterCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AfterCombat"


@dataclass(frozen=True)
class T_casting_restrictions__BeforeAttackersDeclared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeAttackersDeclared"


@dataclass(frozen=True)
class T_casting_restrictions__BeforeBlockersDeclared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeBlockersDeclared"


@dataclass(frozen=True)
class T_casting_restrictions__BeforeCombatDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeCombatDamage"


@dataclass(frozen=True)
class T_casting_restrictions__DeclareAttackersStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclareAttackersStep"


@dataclass(frozen=True)
class T_casting_restrictions__DeclareBlockersStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclareBlockersStep"


@dataclass(frozen=True)
class T_casting_restrictions__DuringCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringCombat"


@dataclass(frozen=True)
class T_casting_restrictions__DuringOpponentsTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringOpponentsTurn"


@dataclass(frozen=True)
class T_casting_restrictions__DuringOpponentsUpkeep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringOpponentsUpkeep"


@dataclass(frozen=True)
class T_casting_restrictions__DuringYourEndStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourEndStep"


@dataclass(frozen=True)
class T_casting_restrictions__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_casting_restrictions__RequiresCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RequiresCondition"
    data: MirrorVariant


@dataclass(frozen=True)
class T_choose_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_chooser__ChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenPlayer"
    index: int


@dataclass(frozen=True)
class T_chooser__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_chooser__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_chooser__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_chooser__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_chooser__ParentObjectTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetOwner"


@dataclass(frozen=True)
class T_chooser__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_chooser__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_colors__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"


@dataclass(frozen=True)
class T_colors__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: list[U_value | MirrorVariant]


@dataclass(frozen=True)
class T_condition__ActivatedAbilityIsNonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ActivatedAbilityIsNonMana"


@dataclass(frozen=True)
class T_condition__AdditionalCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaid"
    min_count: int = MISSING
    origin: str = MISSING
    origin_ordinal: int = MISSING
    source: str = MISSING
    subject: U_subject = MISSING
    variant: str = MISSING


@dataclass(frozen=True)
class T_condition__AdditionalCostPaidInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaidInstead"


@dataclass(frozen=True)
class T_condition__AlternativeManaCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AlternativeManaCostPaid"


@dataclass(frozen=True)
class T_condition__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_condition__AtNextPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtNextPhase"
    phase: str


@dataclass(frozen=True)
class T_condition__AtNextPhaseForPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtNextPhaseForPlayer"
    phase: str
    player: int
    gate: str = MISSING


@dataclass(frozen=True)
class T_condition__AttackersDeclaredCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackersDeclaredCount"
    comparator: str
    count: int
    subject: U_subject


@dataclass(frozen=True)
class T_condition__BattlefieldEntriesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BattlefieldEntriesThisTurn"
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_condition__BeenAttackedThisStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeenAttackedThisStep"


@dataclass(frozen=True)
class T_condition__CastDuringPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastDuringPhase"
    phases: list[object]


@dataclass(frozen=True)
class T_condition__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    zone: str


@dataclass(frozen=True)
class T_condition__CastTimingPermission(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastTimingPermission"
    permission: str


@dataclass(frozen=True)
class T_condition__CastVariantPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaid"
    variant: str
    subject: U_subject = MISSING


@dataclass(frozen=True)
class T_condition__CastVariantPaidInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaidInstead"
    variant: str


@dataclass(frozen=True)
class T_condition__CastVariantPaidPersistent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaidPersistent"
    variant: str


@dataclass(frozen=True)
class T_condition__CastViaEscape(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastViaEscape"


@dataclass(frozen=True)
class T_condition__CastViaKicker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastViaKicker"
    variant: str = MISSING


@dataclass(frozen=True)
class T_condition__CastingAsVariant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastingAsVariant"
    variant: str


@dataclass(frozen=True)
class T_condition__ChosenLabelIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenLabelIs"
    label: str


@dataclass(frozen=True)
class T_condition__ClassLevelGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClassLevelGE"
    level: int


@dataclass(frozen=True)
class T_condition__CompletedADungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CompletedADungeon"


@dataclass(frozen=True)
class T_condition__CompletedDungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CompletedDungeon"
    specific: str = MISSING


@dataclass(frozen=True)
class T_condition__ConditionInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConditionInstead"
    inner: U_inner


@dataclass(frozen=True)
class T_condition__ControllerControlledMatchingAsCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlledMatchingAsCast"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControllerControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlsMatching"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControlsCommander(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCommander"
    ownership: str


@dataclass(frozen=True)
class T_condition__ControlsCreatureWithKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCreatureWithKeyword"
    controller: str
    keyword: str


@dataclass(frozen=True)
class T_condition__ControlsNone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsNone"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControlsType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsType"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__CostPaidObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObjectMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__CreatureDiedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreatureDiedThisTurn"


@dataclass(frozen=True)
class T_condition__CreaturesYouControlTotalPowerAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreaturesYouControlTotalPowerAtLeast"
    minimum: int


@dataclass(frozen=True)
class T_condition__DamagedPlayerIsEventSourceOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamagedPlayerIsEventSourceOwner"


@dataclass(frozen=True)
class T_condition__DayNightIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DayNightIs"
    state: str


@dataclass(frozen=True)
class T_condition__DayNightIsNeither(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DayNightIsNeither"


@dataclass(frozen=True)
class T_condition__DealtDamageBySourceThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealtDamageBySourceThisTurn"


@dataclass(frozen=True)
class T_condition__DealtDamageThisTurnBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealtDamageThisTurnBySource"
    source: U_source


@dataclass(frozen=True)
class T_condition__DefendingPlayerControls(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayerControls"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__DefendingPlayerControlsNone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayerControlsNone"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__DevotionGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DevotionGE"
    colors: list[U_colors]
    threshold: int


@dataclass(frozen=True)
class T_condition__DuringPlayersTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringPlayersTurn"
    player: U_player


@dataclass(frozen=True)
class T_condition__DuringUntapStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringUntapStep"


@dataclass(frozen=True)
class T_condition__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_condition__EchoDue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EchoDue"


@dataclass(frozen=True)
class T_condition__EffectCausedDiscard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCausedDiscard"


@dataclass(frozen=True)
class T_condition__EffectOutcome(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectOutcome"
    signal: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__EnchantedIsFaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnchantedIsFaceDown"


@dataclass(frozen=True)
class T_condition__EnteredFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredFromZone"
    cast_origin: str
    origin_constraint: U_origin_constraint


@dataclass(frozen=True)
class T_condition__EventDamageSourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventDamageSourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__EventObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventObjectMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__EventOutcomeWon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventOutcomeWon"


@dataclass(frozen=True)
class T_condition__EventSourceControlledBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventSourceControlledBy"
    controller: str


@dataclass(frozen=True)
class T_condition__ExceptFirstDrawInDrawStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExceptFirstDrawInDrawStep"


@dataclass(frozen=True)
class T_condition__FirstCombatPhaseOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstCombatPhaseOfTurn"


@dataclass(frozen=True)
class T_condition__FirstEndStepOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstEndStepOfTurn"


@dataclass(frozen=True)
class T_condition__FirstSpellThisGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstSpellThisGame"


@dataclass(frozen=True)
class T_condition__FirstTimeObjectTappedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstTimeObjectTappedThisTurn"


@dataclass(frozen=True)
class T_condition__FirstTokenCreationEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstTokenCreationEachTurn"
    player: str


@dataclass(frozen=True)
class T_condition__HadCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HadCounters"
    counter_type: None | str


@dataclass(frozen=True)
class T_condition__HandSizeExact(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSizeExact"
    count: int


@dataclass(frozen=True)
class T_condition__HandSizeOneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSizeOneOf"
    counts: list[object]


@dataclass(frozen=True)
class T_condition__HasCityBlessing(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCityBlessing"


@dataclass(frozen=True)
class T_condition__HasCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCounters"
    counters: U_counters
    minimum: int
    maximum: int = MISSING


@dataclass(frozen=True)
class T_condition__HasMaxSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasMaxSpeed"


@dataclass(frozen=True)
class T_condition__IfControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IfControlsMatching"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_condition__IsInitiative(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsInitiative"


@dataclass(frozen=True)
class T_condition__IsMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsMonarch"


@dataclass(frozen=True)
class T_condition__IsPresent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsPresent"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__IsRenowned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsRenowned"
    subject: str


@dataclass(frozen=True)
class T_condition__IsRingBearer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsRingBearer"


@dataclass(frozen=True)
class T_condition__IsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsTapped"
    scope: U_scope


@dataclass(frozen=True)
class T_condition__IsYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsYourTurn"


@dataclass(frozen=True)
class T_condition__ManaColorSpent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaColorSpent"
    color: str
    minimum: int


@dataclass(frozen=True)
class T_condition__ManaSpentCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSpentCondition"
    text: str


@dataclass(frozen=True)
class T_condition__MinCoAttackers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MinCoAttackers"
    minimum: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_condition__NoMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoMonarch"


@dataclass(frozen=True)
class T_condition__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    condition: U_condition


@dataclass(frozen=True)
class T_condition__NthResolutionThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthResolutionThisTurn"
    n: int


@dataclass(frozen=True)
class T_condition__ObjectsShareQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectsShareQuality"
    quality: str
    reference: U_reference
    subject: U_subject


@dataclass(frozen=True)
class T_condition__OnlyExtraTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyExtraTurn"


@dataclass(frozen=True)
class T_condition__OnlyIfQuantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyIfQuantity"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__OpponentDamagedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentDamagedThisTurn"


@dataclass(frozen=True)
class T_condition__OpponentPoisonAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentPoisonAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__OpponentSearchedLibraryThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentSearchedLibraryThisTurn"


@dataclass(frozen=True)
class T_condition__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_condition__PlacedByAbilitySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlacedByAbilitySource"


@dataclass(frozen=True)
class T_condition__PlayerCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCountAtLeast"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_condition__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"
    comparator: str
    rhs: U_rhs
    channel: str = MISSING


@dataclass(frozen=True)
class T_condition__QuantityCheck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityCheck"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__QuantityComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityComparison"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__QuantityVsEachOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityVsEachOpponent"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__RecipientAttackingOwnerTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientAttackingOwnerTarget"
    target: str


@dataclass(frozen=True)
class T_condition__RecipientHasCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientHasCounters"
    counters: U_counters
    minimum: int


@dataclass(frozen=True)
class T_condition__RecipientMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__RevealedHasCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealedHasCardType"
    card_types: list[MirrorVariant]
    additional_filter: U_additional_filter = MISSING
    subtype_filter: U_subtype_filter = MISSING


@dataclass(frozen=True)
class T_condition__SharesColorWithMostCommonColorAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesColorWithMostCommonColorAmongPermanents"


@dataclass(frozen=True)
class T_condition__SolveConditionMet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SolveConditionMet"


@dataclass(frozen=True)
class T_condition__SourceAttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttachedTo"
    required_type: str


@dataclass(frozen=True)
class T_condition__SourceAttachedToCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttachedToCreature"


@dataclass(frozen=True)
class T_condition__SourceAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttackedThisTurn"


@dataclass(frozen=True)
class T_condition__SourceAttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttackingAlone"


@dataclass(frozen=True)
class T_condition__SourceEnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceEnteredThisTurn"


@dataclass(frozen=True)
class T_condition__SourceHasCounterAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceHasCounterAtLeast"
    count: int
    counter_type: str


@dataclass(frozen=True)
class T_condition__SourceHasDealtDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceHasDealtDamage"


@dataclass(frozen=True)
class T_condition__SourceHasNoCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceHasNoCounter"
    counter_type: str


@dataclass(frozen=True)
class T_condition__SourceInZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceInZone"
    zone: str


@dataclass(frozen=True)
class T_condition__SourceIsAttacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsAttacking"


@dataclass(frozen=True)
class T_condition__SourceIsBlocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsBlocked"


@dataclass(frozen=True)
class T_condition__SourceIsColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsColor"
    color: str


@dataclass(frozen=True)
class T_condition__SourceIsCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsCreature"


@dataclass(frozen=True)
class T_condition__SourceIsEnchanted(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsEnchanted"


@dataclass(frozen=True)
class T_condition__SourceIsEquipped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsEquipped"


@dataclass(frozen=True)
class T_condition__SourceIsHarnessed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsHarnessed"


@dataclass(frozen=True)
class T_condition__SourceIsMonstrous(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsMonstrous"


@dataclass(frozen=True)
class T_condition__SourceIsPaired(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsPaired"


@dataclass(frozen=True)
class T_condition__SourceIsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsTapped"


@dataclass(frozen=True)
class T_condition__SourceLacksKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceLacksKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__SourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__SourcePowerAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourcePowerAtLeast"
    minimum: int


@dataclass(frozen=True)
class T_condition__SourceTappedState(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceTappedState"
    tapped: bool


@dataclass(frozen=True)
class T_condition__SourceUntappedAttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceUntappedAttachedTo"
    required_type: str


@dataclass(frozen=True)
class T_condition__SpeedGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpeedGE"
    threshold: int


@dataclass(frozen=True)
class T_condition__SpellTargetsFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellTargetsFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__Static(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Static"
    condition: U_condition


@dataclass(frozen=True)
class T_condition__TargetHasKeywordInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetHasKeywordInstead"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__TargetMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetMatchesFilter"
    filter: U_filter
    use_lki: bool
    subject_slot: int = MISSING


@dataclass(frozen=True)
class T_condition__TargetSharesNameWithOtherExiledThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetSharesNameWithOtherExiledThisWay"
    target: U_target


@dataclass(frozen=True)
class T_condition__TokenCoreTypeMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokenCoreTypeMatches"
    core_types: list[object]


@dataclass(frozen=True)
class T_condition__TokenSubtypeMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokenSubtypeMatches"
    subtypes: list[object]


@dataclass(frozen=True)
class T_condition__TributeNotPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TributeNotPaid"


@dataclass(frozen=True)
class T_condition__TriggeringSpellTargetsFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellTargetsFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsCountMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsCountMatching"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_condition__UnlessControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsMatching"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsOtherLeq(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsOtherLeq"
    count: int
    filter: S_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsSubtype"
    subtypes: list[object]


@dataclass(frozen=True)
class T_condition__UnlessMultipleOpponents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessMultipleOpponents"


@dataclass(frozen=True)
class T_condition__UnlessPay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessPay"
    cost: U_cost
    defended: str = MISSING
    scaling: U_scaling = MISSING


@dataclass(frozen=True)
class T_condition__UnlessPlayerLifeAtMost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessPlayerLifeAtMost"
    amount: int


@dataclass(frozen=True)
class T_condition__UnlessQuantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessQuantity"
    active_player_req: str
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__UnlessYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessYourTurn"


@dataclass(frozen=True)
class T_condition__Unrecognized(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unrecognized"
    text: str


@dataclass(frozen=True)
class T_condition__WasCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasCast"
    controller: str = MISSING
    owner: str = MISSING
    zone: str = MISSING


@dataclass(frozen=True)
class T_condition__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_condition__WasStartingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasStartingPlayer"
    controller: str


@dataclass(frozen=True)
class T_condition__WasType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasType"
    card_type: str


@dataclass(frozen=True)
class T_condition__WhenDies(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenDies"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenDiesOrExiled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenDiesOrExiled"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenEntersBattlefield(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenEntersBattlefield"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenLeavesPlayFiltered(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenLeavesPlayFiltered"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenNextEvent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenNextEvent"
    or_trigger: None | S_or_trigger
    trigger: S_trigger
    lifetime: str = MISSING


@dataclass(frozen=True)
class T_condition__WhenYouDo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenYouDo"


@dataclass(frozen=True)
class T_condition__WheneverEvent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WheneverEvent"
    trigger: S_trigger


@dataclass(frozen=True)
class T_condition__YouAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedThisTurn"


@dataclass(frozen=True)
class T_condition__YouAttackedWithAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedWithAtLeast"
    count: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_condition__YouCastSpellCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouCastSpellCountAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__YouCastSpellThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouCastSpellThisTurn"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__YouControlAnotherColorlessCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlAnotherColorlessCreature"


@dataclass(frozen=True)
class T_condition__YouControlColorPermanentCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlColorPermanentCountAtLeast"
    color: str
    count: int


@dataclass(frozen=True)
class T_condition__YouControlCoreTypeCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlCoreTypeCountAtLeast"
    core_type: str
    count: int


@dataclass(frozen=True)
class T_condition__YouControlCreatureWithPowerAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlCreatureWithPowerAtLeast"
    minimum: int


@dataclass(frozen=True)
class T_condition__YouControlCreatureWithPt(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlCreatureWithPt"
    power: int
    toughness: int


@dataclass(frozen=True)
class T_condition__YouControlDifferentPowerCreatureCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlDifferentPowerCreatureCountAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__YouControlLandSubtypeAny(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlLandSubtypeAny"
    subtypes: list[object]


@dataclass(frozen=True)
class T_condition__YouControlLandsWithSameNameAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlLandsWithSameNameAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__YouControlLegendaryCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlLegendaryCreature"


@dataclass(frozen=True)
class T_condition__YouControlNamedPlaneswalker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlNamedPlaneswalker"
    name: str


@dataclass(frozen=True)
class T_condition__YouControlNoCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlNoCreatures"


@dataclass(frozen=True)
class T_condition__YouControlSnowPermanentCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlSnowPermanentCountAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__YouControlSubtypeCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlSubtypeCountAtLeast"
    count: int
    subtype: str


@dataclass(frozen=True)
class T_condition__YouCreatedTokenThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouCreatedTokenThisTurn"


@dataclass(frozen=True)
class T_condition__YouDiscardedCardThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouDiscardedCardThisTurn"


@dataclass(frozen=True)
class T_condition__YouGainedLifeThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouGainedLifeThisTurn"


@dataclass(frozen=True)
class T_condition__YouHadArtifactEnterThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouHadArtifactEnterThisTurn"


@dataclass(frozen=True)
class T_condition__YouPlayedLandThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouPlayedLandThisTurn"


@dataclass(frozen=True)
class T_condition__YouSacrificedArtifactThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouSacrificedArtifactThisTurn"


@dataclass(frozen=True)
class T_condition__ZoneCardCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCountAtLeast"
    count: int
    zone: str


@dataclass(frozen=True)
class T_condition__ZoneCardTypeCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardTypeCountAtLeast"
    count: int
    zone: str


@dataclass(frozen=True)
class T_condition__ZoneChangeObjectIsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectIsTapped"


@dataclass(frozen=True)
class T_condition__ZoneChangeObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectMatchesFilter"
    destination: str
    filter: U_filter
    origin: str = MISSING


@dataclass(frozen=True)
class T_condition__ZoneChangedThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisWay"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ZoneCoreTypeCardCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCoreTypeCardCountAtLeast"
    core_type: str
    count: int
    zone: str


@dataclass(frozen=True)
class T_condition__ZoneSubtypeCardCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneSubtypeCardCountAtLeast"
    count: int
    subtype: str
    zone: str


@dataclass(frozen=True)
class T_conditional_enter_with_counters__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_conditional_enter_with_counters__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_conditions__AdditionalCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaid"


@dataclass(frozen=True)
class T_conditions__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_conditions__AttackersDeclaredCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackersDeclaredCount"
    comparator: str
    count: int
    subject: U_subject


@dataclass(frozen=True)
class T_conditions__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    zone: str


@dataclass(frozen=True)
class T_conditions__CastVariantPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaid"
    variant: str


@dataclass(frozen=True)
class T_conditions__CastVariantPaidPersistent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaidPersistent"
    variant: str


@dataclass(frozen=True)
class T_conditions__ChosenLabelIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenLabelIs"
    label: str


@dataclass(frozen=True)
class T_conditions__ClassLevelGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClassLevelGE"
    level: int


@dataclass(frozen=True)
class T_conditions__ControlCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlCount"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_conditions__ControllerControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlsMatching"
    filter: U_filter


@dataclass(frozen=True)
class T_conditions__ControlsType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsType"
    filter: U_filter


@dataclass(frozen=True)
class T_conditions__CurrentPhaseIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CurrentPhaseIs"
    phases: list[object]


@dataclass(frozen=True)
class T_conditions__DuringPlayersTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringPlayersTurn"
    player: U_player


@dataclass(frozen=True)
class T_conditions__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_conditions__EffectOutcome(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectOutcome"
    signal: str


@dataclass(frozen=True)
class T_conditions__FirstCombatPhaseOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstCombatPhaseOfTurn"


@dataclass(frozen=True)
class T_conditions__HasCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCounters"
    counters: U_counters
    minimum: int


@dataclass(frozen=True)
class T_conditions__HasObjectTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasObjectTarget"


@dataclass(frozen=True)
class T_conditions__IsPresent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsPresent"
    filter: None | U_filter


@dataclass(frozen=True)
class T_conditions__IsYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsYourTurn"


@dataclass(frozen=True)
class T_conditions__ManaColorSpent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaColorSpent"
    color: str
    minimum: int


@dataclass(frozen=True)
class T_conditions__ManaSpentCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSpentCondition"
    text: str


@dataclass(frozen=True)
class T_conditions__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    condition: U_condition


@dataclass(frozen=True)
class T_conditions__OpponentPoisonAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentPoisonAtLeast"
    count: int


@dataclass(frozen=True)
class T_conditions__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_conditions__QuantityCheck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityCheck"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_conditions__QuantityComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityComparison"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_conditions__ScopedPlayerMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayerMatches"
    filter: U_filter


@dataclass(frozen=True)
class T_conditions__SourceEnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceEnteredThisTurn"


@dataclass(frozen=True)
class T_conditions__SourceInZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceInZone"
    zone: str


@dataclass(frozen=True)
class T_conditions__SourceIsAttacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsAttacking"


@dataclass(frozen=True)
class T_conditions__SourceIsBlocking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsBlocking"


@dataclass(frozen=True)
class T_conditions__SourceIsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsTapped"


@dataclass(frozen=True)
class T_conditions__SourceLacksKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceLacksKeyword"
    keyword: str


@dataclass(frozen=True)
class T_conditions__SourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_conditions__SpellCastWithVariantThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellCastWithVariantThisTurn"
    variant: str


@dataclass(frozen=True)
class T_conditions__TargetHasKeywordInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetHasKeywordInstead"
    keyword: str


@dataclass(frozen=True)
class T_conditions__TargetMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetMatchesFilter"
    filter: U_filter
    use_lki: bool


@dataclass(frozen=True)
class T_conditions__TriggeringSpellMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_conditions__UnlessPay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessPay"
    cost: U_cost
    scaling: U_scaling
    defended: str = MISSING


@dataclass(frozen=True)
class T_conditions__Unrecognized(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unrecognized"
    text: str


@dataclass(frozen=True)
class T_conditions__WasCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasCast"
    controller: str = MISSING
    owner: str = MISSING
    zone: str = MISSING


@dataclass(frozen=True)
class T_conditions__YouControlSubtypeCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouControlSubtypeCountAtLeast"
    count: int
    subtype: str


@dataclass(frozen=True)
class T_conditions__ZoneChangeObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectMatchesFilter"
    destination: str
    filter: U_filter
    origin: str = MISSING


@dataclass(frozen=True)
class T_conditions__ZoneChangedThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisWay"
    filter: U_filter


@dataclass(frozen=True)
class T_constraint__AtClassLevel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtClassLevel"
    level: int


@dataclass(frozen=True)
class T_constraint__DistinctCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCardTypes"
    categories: list[object]


@dataclass(frozen=True)
class T_constraint__EventSourceControlledBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventSourceControlledBy"
    controller: str


@dataclass(frozen=True)
class T_constraint__ManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaValue"
    data: S_data


@dataclass(frozen=True)
class T_constraint__MaxTimesPerTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MaxTimesPerTurn"
    max: int


@dataclass(frozen=True)
class T_constraint__NthDrawThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthDrawThisTurn"
    n: int


@dataclass(frozen=True)
class T_constraint__NthSpellThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthSpellThisTurn"
    n: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_constraint__OncePerGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OncePerGame"


@dataclass(frozen=True)
class T_constraint__OncePerOpponentPerTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OncePerOpponentPerTurn"


@dataclass(frozen=True)
class T_constraint__OncePerTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OncePerTurn"


@dataclass(frozen=True)
class T_constraint__OnlyDuringOpponentsTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyDuringOpponentsTurn"


@dataclass(frozen=True)
class T_constraint__OnlyDuringYourMainPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyDuringYourMainPhase"


@dataclass(frozen=True)
class T_constraint__OnlyDuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyDuringYourTurn"


@dataclass(frozen=True)
class T_constraints__ConditionalMaxChoices(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConditionalMaxChoices"
    condition: U_condition
    max_choices: int
    otherwise_max_choices: int


@dataclass(frozen=True)
class T_constraints__DifferentTargetPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DifferentTargetPlayers"


@dataclass(frozen=True)
class T_constraints__NoRepeatThisGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoRepeatThisGame"


@dataclass(frozen=True)
class T_constraints__NoRepeatThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoRepeatThisTurn"


@dataclass(frozen=True)
class T_copy_modifications__RemoveSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveSupertype"
    supertype: str


@dataclass(frozen=True)
class T_cost__Behold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Behold"
    action: str
    count: int
    filter: U_filter
    type_choice: str = MISSING


@dataclass(frozen=True)
class T_cost__Blight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Blight"
    count: int


@dataclass(frozen=True)
class T_cost__CollectEvidence(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CollectEvidence"
    amount: int


@dataclass(frozen=True)
class T_cost__Composite(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Composite"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_cost__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None | U_filter
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_cost__EffectCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCost"
    effect: U_effect


@dataclass(frozen=True)
class T_cost__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None | U_filter
    zone: None | str


@dataclass(frozen=True)
class T_cost__ExileWithAggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileWithAggregate"
    comparator: str
    filter: U_filter
    function: str
    property: MirrorVariant
    value: int
    zone: str


@dataclass(frozen=True)
class T_cost__Loyalty(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Loyalty"
    amount: int


@dataclass(frozen=True)
class T_cost__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_cost__ManaDynamic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaDynamic"
    quantity: U_quantity


@dataclass(frozen=True)
class T_cost__Mill(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mill"
    count: int


@dataclass(frozen=True)
class T_cost__NinjutsuFamily(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NinjutsuFamily"
    mana_cost: U_mana_cost
    variant: str


@dataclass(frozen=True)
class T_cost__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_cost__PayEnergy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayEnergy"
    amount: U_amount


@dataclass(frozen=True)
class T_cost__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_cost__PaySpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PaySpeed"
    amount: U_amount


@dataclass(frozen=True)
class T_cost__PerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerCounter"
    base: U_base
    counter: str
    target: U_target


@dataclass(frozen=True)
class T_cost__RemoveCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveCounter"
    count: int
    counter_type: U_counter_type
    selection: str
    target: None | U_target


@dataclass(frozen=True)
class T_cost__ReturnToHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReturnToHand"
    count: int
    filter: U_filter
    from_zone: str = MISSING


@dataclass(frozen=True)
class T_cost__Reveal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Reveal"
    count: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_cost__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    target: U_target
    count: int = MISSING
    requirement: S_requirement = MISSING


@dataclass(frozen=True)
class T_cost__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_cost__Tap(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tap"


@dataclass(frozen=True)
class T_cost__TapCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TapCreatures"
    filter: U_filter
    requirement: S_requirement


@dataclass(frozen=True)
class T_cost__Unimplemented(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unimplemented"
    description: str


@dataclass(frozen=True)
class T_cost__Waterbend(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Waterbend"
    cost: U_cost


@dataclass(frozen=True)
class T_costs__Behold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Behold"
    action: str
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_costs__Blight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Blight"
    count: int


@dataclass(frozen=True)
class T_costs__CollectEvidence(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CollectEvidence"
    amount: int


@dataclass(frozen=True)
class T_costs__Composite(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Composite"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_costs__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_costs__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None | U_filter
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_costs__EffectCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCost"
    effect: U_effect


@dataclass(frozen=True)
class T_costs__Exert(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exert"


@dataclass(frozen=True)
class T_costs__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None | U_filter
    zone: None | str


@dataclass(frozen=True)
class T_costs__ExileMaterials(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileMaterials"
    count: U_count
    materials: U_materials


@dataclass(frozen=True)
class T_costs__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_costs__Mill(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mill"
    count: int


@dataclass(frozen=True)
class T_costs__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_costs__PayEnergy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayEnergy"
    amount: U_amount


@dataclass(frozen=True)
class T_costs__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_costs__RemoveCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveCounter"
    count: int
    counter_type: U_counter_type
    selection: str
    target: None | U_target


@dataclass(frozen=True)
class T_costs__ReturnToHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReturnToHand"
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_costs__Reveal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Reveal"
    count: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_costs__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_costs__Tap(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tap"


@dataclass(frozen=True)
class T_costs__TapCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TapCreatures"
    filter: U_filter
    requirement: S_requirement


@dataclass(frozen=True)
class T_costs__Unattach(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unattach"


@dataclass(frozen=True)
class T_costs__UnattachFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnattachFrom"
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_costs__Unimplemented(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unimplemented"
    description: str


@dataclass(frozen=True)
class T_costs__Untap(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Untap"


@dataclass(frozen=True)
class T_costs__Waterbend(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Waterbend"
    cost: U_cost


@dataclass(frozen=True)
class T_count__AtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtLeast"
    count: int


@dataclass(frozen=True)
class T_count__ClampMin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClampMin"
    inner: U_inner
    minimum: int


@dataclass(frozen=True)
class T_count__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_count__DivideRounded(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DivideRounded"
    divisor: int
    inner: U_inner
    rounding: str


@dataclass(frozen=True)
class T_count__Exactly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exactly"
    count: int


@dataclass(frozen=True)
class T_count__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_count__Max(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Max"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_count__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_count__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_count__Power(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Power"
    base: int
    exponent: U_exponent


@dataclass(frozen=True)
class T_count__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_count__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_count__UpTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UpTo"
    max: U_max


@dataclass(frozen=True)
class T_counter_match__OfType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OfType"
    data: str


@dataclass(frozen=True)
class T_counter_type__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_counter_type__OfType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OfType"
    data: str


@dataclass(frozen=True)
class T_countered_spell_zone__Hand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Hand"


@dataclass(frozen=True)
class T_countered_spell_zone__Library(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Library"
    position: U_position


@dataclass(frozen=True)
class T_counters__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_counters__OfType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OfType"
    data: str


@dataclass(frozen=True)
class T_damage_modification__Double(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Double"


@dataclass(frozen=True)
class T_damage_modification__LifeFloor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeFloor"
    minimum: int


@dataclass(frozen=True)
class T_damage_modification__Minus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Minus"
    value: int


@dataclass(frozen=True)
class T_damage_modification__Plus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Plus"
    value: U_value


@dataclass(frozen=True)
class T_damage_modification__SetToSourcePower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetToSourcePower"


@dataclass(frozen=True)
class T_damage_modification__Triple(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Triple"


@dataclass(frozen=True)
class T_damage_source_filter__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_damage_source_filter__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_damage_source_filter__ChosenDamageSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenDamageSource"
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_damage_source_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_damage_source_filter__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_damage_source_filter__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_damage_source_filter__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_damage_source_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_data__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_data__Behold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Behold"
    action: str
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_data__Blight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Blight"
    count: int


@dataclass(frozen=True)
class T_data__Composite(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Composite"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_data__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_data__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None | U_filter
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_data__DiscardCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DiscardCard"


@dataclass(frozen=True)
class T_data__EffectCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCost"
    effect: U_effect


@dataclass(frozen=True)
class T_data__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None | U_filter
    zone: None | str


@dataclass(frozen=True)
class T_data__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost = MISSING
    data: U_data = MISSING


@dataclass(frozen=True)
class T_data__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_data__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_data__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount = MISSING
    data: int = MISSING


@dataclass(frozen=True)
class T_data__ReturnToHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReturnToHand"
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_data__Reveal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Reveal"
    count: int
    filter: U_filter


@dataclass(frozen=True)
class T_data__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_data__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_data__TapCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TapCreatures"
    filter: U_filter
    requirement: S_requirement


@dataclass(frozen=True)
class T_data__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_data__Unimplemented(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unimplemented"
    description: str


@dataclass(frozen=True)
class T_data__Waterbend(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Waterbend"
    cost: U_cost


@dataclass(frozen=True)
class T_deck_copy_limit__Unlimited(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unlimited"


@dataclass(frozen=True)
class T_deck_copy_limit__UpTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UpTo"
    data: int


@dataclass(frozen=True)
class T_depth__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_destination_constraint__NotEquals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotEquals"
    data: str


@dataclass(frozen=True)
class T_direction__Decrease(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Decrease"


@dataclass(frozen=True)
class T_direction__Left(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Left"


@dataclass(frozen=True)
class T_direction__Right(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Right"


@dataclass(frozen=True)
class T_distribute__Counters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counters"
    data: str


@dataclass(frozen=True)
class T_distribute__Damage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Damage"


@dataclass(frozen=True)
class T_distribute__EvenSplitDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EvenSplitDamage"


@dataclass(frozen=True)
class T_duplicate_of__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_duplicate_of__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_duplicate_of__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_duplicate_of__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_dynamic_count__Aggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Aggregate"
    filter: U_filter
    function: str
    property: str


@dataclass(frozen=True)
class T_dynamic_count__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"
    scope: str


@dataclass(frozen=True)
class T_dynamic_count__BasicLandTypeCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BasicLandTypeCount"
    controller: str


@dataclass(frozen=True)
class T_dynamic_count__CardsDiscardedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDiscardedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__CardsDrawnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDrawnThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__CountersOn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOn"
    counter_type: str
    scope: U_scope


@dataclass(frozen=True)
class T_dynamic_count__DamageDealtThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageDealtThisTurn"
    damage_kind: str
    source: U_source
    target: U_target


@dataclass(frozen=True)
class T_dynamic_count__Devotion(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Devotion"
    colors: U_colors


@dataclass(frozen=True)
class T_dynamic_count__DistinctCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCardTypes"
    source: U_source


@dataclass(frozen=True)
class T_dynamic_count__DistinctColorsAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColorsAmongPermanents"
    filter: U_filter


@dataclass(frozen=True)
class T_dynamic_count__FilteredTrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FilteredTrackedSetSize"
    filter: U_filter
    caused_by: str = MISSING


@dataclass(frozen=True)
class T_dynamic_count__LifeGainedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeGainedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__LifeLostThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeLostThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_dynamic_count__ObjectCountDistinct(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCountDistinct"
    filter: U_filter
    qualities: list[object]


@dataclass(frozen=True)
class T_dynamic_count__PartySize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PartySize"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__PlayerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCount"
    filter: U_filter


@dataclass(frozen=True)
class T_dynamic_count__PlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCounter"
    kind: str
    scope: str


@dataclass(frozen=True)
class T_dynamic_count__Power(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Power"
    scope: U_scope


@dataclass(frozen=True)
class T_dynamic_count__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"


@dataclass(frozen=True)
class T_dynamic_count__Speed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Speed"
    player: U_player


@dataclass(frozen=True)
class T_dynamic_count__SpellsCastThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastThisTurn"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_dynamic_count__TrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetSize"


@dataclass(frozen=True)
class T_dynamic_count__ZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCount"
    card_types: list[MirrorVariant]
    scope: str
    zone: str


@dataclass(frozen=True)
class T_dynamic_count__ZoneChangeCountThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeCountThisTurn"
    filter: U_filter
    from_: str = field(metadata={"json": "from"})
    to: str


@dataclass(frozen=True)
class T_dynamic_max_choices__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_effect__Adapt(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Adapt"
    count: U_count


@dataclass(frozen=True)
class T_effect__AddPendingETBCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddPendingETBCounters"
    count: U_count
    counter_type: str


@dataclass(frozen=True)
class T_effect__AddPendingEntersModifications(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddPendingEntersModifications"
    modifications: list[U_modifications]


@dataclass(frozen=True)
class T_effect__AddRestriction(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddRestriction"
    restriction: U_restriction


@dataclass(frozen=True)
class T_effect__AddTargetReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddTargetReplacement"
    replacement: S_replacement
    target: U_target


@dataclass(frozen=True)
class T_effect__AdditionalPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalPhase"
    after: str
    attacker_restriction: None | U_attacker_restriction
    count: U_count
    followed_by: list[object]
    phase: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Amass(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Amass"
    count: U_count
    subtype: str


@dataclass(frozen=True)
class T_effect__Animate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Animate"
    power: None | U_power
    target: U_target
    toughness: None | U_toughness
    types: list[object]
    keywords: list[MirrorVariant] = MISSING
    remove_types: list[object] = MISSING


@dataclass(frozen=True)
class T_effect__ApplyPerpetual(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ApplyPerpetual"
    modification: S_modification
    target: U_target


@dataclass(frozen=True)
class T_effect__AssembleContraptions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AssembleContraptions"
    count: U_count


@dataclass(frozen=True)
class T_effect__Attach(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attach"
    target: U_target
    attachment: U_attachment = MISSING


@dataclass(frozen=True)
class T_effect__BecomeBlocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeBlocked"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeCopy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeCopy"
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    duration: str | MirrorVariant = MISSING
    mana_value_limit: str = MISSING
    recipient: U_recipient = MISSING


@dataclass(frozen=True)
class T_effect__BecomeMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeMonarch"


@dataclass(frozen=True)
class T_effect__BecomePrepared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomePrepared"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeSaddled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeSaddled"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeUnprepared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeUnprepared"
    target: U_target


@dataclass(frozen=True)
class T_effect__Behold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Behold"
    filter: U_filter


@dataclass(frozen=True)
class T_effect__BlightEffect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlightEffect"
    count: int
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__Bolster(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bolster"
    count: U_count


@dataclass(frozen=True)
class T_effect__Bounce(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bounce"
    destination: None
    target: U_target
    selection: str = MISSING


@dataclass(frozen=True)
class T_effect__BounceAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BounceAll"
    target: U_target
    count: U_count = MISSING


@dataclass(frozen=True)
class T_effect__CastCopyOfCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastCopyOfCard"
    cost: U_cost
    count: None | U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    mode: str
    target: U_target
    without_paying_mana_cost: bool
    alt_ability_cost: U_alt_ability_cost = MISSING
    cast_transformed: bool = MISSING
    constraint: U_constraint = MISSING
    driver: str = MISSING
    duration: str | MirrorVariant = MISSING
    mana_spend_permission: str = MISSING


@dataclass(frozen=True)
class T_effect__ChangeSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeSpeed"
    amount: U_amount
    direction: U_direction
    floor: int
    player_scope: U_player_scope


@dataclass(frozen=True)
class T_effect__ChangeTargets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeTargets"
    forced_to: None | U_forced_to
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__ChangeZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeZone"
    destination: str
    enter_tapped: bool
    enter_transformed: bool
    enters_attacking: bool
    origin: None | str
    owner_library: bool
    target: U_target
    conditional_enter_with_counters: list[U_conditional_enter_with_counters] = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    enters_modified_if: U_enters_modified_if = MISSING
    enters_under: str = MISSING
    face_down_profile: S_face_down_profile = MISSING
    up_to: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChangeZoneAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeZoneAll"
    destination: str
    origin: None | str
    target: U_target
    enter_tapped: bool = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    enters_under: str = MISSING
    face_down_profile: S_face_down_profile = MISSING
    library_position: U_library_position = MISSING
    random_order: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChaosEnsues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChaosEnsues"


@dataclass(frozen=True)
class T_effect__Choose(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Choose"
    choice_type: str | MirrorVariant
    persist: bool
    selection: U_selection = MISSING


@dataclass(frozen=True)
class T_effect__ChooseAndSacrificeRest(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseAndSacrificeRest"
    categories: list[object]
    choose_filter: U_choose_filter
    chooser_scope: str
    sacrifice_filter: U_sacrifice_filter
    total_power_cap: U_total_power_cap = MISSING


@dataclass(frozen=True)
class T_effect__ChooseAugmentAndCombineWithHost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseAugmentAndCombineWithHost"
    filter: U_filter
    host: U_host
    zones: list[object]


@dataclass(frozen=True)
class T_effect__ChooseCounterAdjustment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseCounterAdjustment"
    adjustment: str
    count: U_count


@dataclass(frozen=True)
class T_effect__ChooseCounterKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseCounterKind"
    target: U_target


@dataclass(frozen=True)
class T_effect__ChooseDrawnThisTurnPayOrTopdeck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseDrawnThisTurnPayOrTopdeck"
    count: U_count
    life_payment: U_life_payment
    player: U_player


@dataclass(frozen=True)
class T_effect__ChooseFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseFromZone"
    chooser: str
    count: int
    up_to: bool
    zone: str
    zone_owner: str
    additional_zones: list[object] = MISSING
    constraint: U_constraint = MISSING
    filter: U_filter = MISSING
    random: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChooseObjectsIntoTrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseObjectsIntoTrackedSet"
    chooser: U_chooser
    filter: U_filter
    max: None | int
    min: int


@dataclass(frozen=True)
class T_effect__ChooseOneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseOneOf"
    branches: list[S_branches]
    chooser: U_chooser


@dataclass(frozen=True)
class T_effect__Clash(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Clash"


@dataclass(frozen=True)
class T_effect__Cloak(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cloak"
    count: U_count
    target: U_target
    object_source: U_object_source = MISSING


@dataclass(frozen=True)
class T_effect__CollectEvidence(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CollectEvidence"
    amount: int


@dataclass(frozen=True)
class T_effect__CombineHost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CombineHost"
    host: U_host
    source: str


@dataclass(frozen=True)
class T_effect__Conjure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Conjure"
    cards: list[S_cards]
    destination: str
    tapped: bool


@dataclass(frozen=True)
class T_effect__Connive(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Connive"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__ControlNextTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlNextTurn"
    grant_extra_turn_after: bool
    target: U_target
    window: str


@dataclass(frozen=True)
class T_effect__CopySpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopySpell"
    retarget: U_retarget
    starting_loyalty_from_casualty_sacrifice: bool
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    copier: str = MISSING


@dataclass(frozen=True)
class T_effect__CopyTokenBlockingAttacker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopyTokenBlockingAttacker"
    owner: U_owner
    source_filter: U_source_filter


@dataclass(frozen=True)
class T_effect__CopyTokenOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopyTokenOf"
    count: U_count
    enters_attacking: bool
    owner: U_owner
    tapped: bool
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    extra_keywords: list[MirrorVariant] = MISSING
    source_filter: U_source_filter = MISSING


@dataclass(frozen=True)
class T_effect__Counter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counter"
    target: U_target
    countered_spell_zone: U_countered_spell_zone = MISSING
    source_rider: U_source_rider = MISSING


@dataclass(frozen=True)
class T_effect__CounterAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__CreateDamageReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDamageReplacement"
    combat_scope: str = MISSING
    modification: U_modification = MISSING
    recipient_object_filter: U_recipient_object_filter = MISSING
    redirect_amount: MirrorVariant = MISSING
    redirect_object_filter: U_redirect_object_filter = MISSING
    redirect_to: U_redirect_to = MISSING
    source_filter: U_source_filter = MISSING
    target_filter: MirrorVariant = MISSING


@dataclass(frozen=True)
class T_effect__CreateDelayedTrigger(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDelayedTrigger"
    condition: U_condition
    effect: S_effect
    uses_tracked_set: bool


@dataclass(frozen=True)
class T_effect__CreateDrawReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDrawReplacement"
    replacement_effect: U_replacement_effect


@dataclass(frozen=True)
class T_effect__CreateEmblem(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateEmblem"
    statics: list[S_statics]
    triggers: list[S_triggers]


@dataclass(frozen=True)
class T_effect__CreatePlaneswalkReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreatePlaneswalkReplacement"
    replacement_effect: U_replacement_effect


@dataclass(frozen=True)
class T_effect__DamageAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageAll"
    amount: U_amount
    target: U_target
    damage_source: str = MISSING
    player_filter: U_player_filter = MISSING


@dataclass(frozen=True)
class T_effect__DamageEachPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageEachPlayer"
    amount: U_amount
    player_filter: U_player_filter


@dataclass(frozen=True)
class T_effect__DealDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealDamage"
    amount: U_amount
    target: U_target
    damage_source: str = MISSING
    excess: U_excess = MISSING


@dataclass(frozen=True)
class T_effect__Destroy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Destroy"
    cant_regenerate: bool
    target: U_target


@dataclass(frozen=True)
class T_effect__DestroyAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DestroyAll"
    cant_regenerate: bool
    target: U_target


@dataclass(frozen=True)
class T_effect__Detain(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Detain"
    target: U_target


@dataclass(frozen=True)
class T_effect__Dig(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Dig"
    count: U_count
    destination: None | str
    enter_tapped: bool
    filter: U_filter
    keep_count: None | int
    player: U_player
    rest_destination: None | str
    reveal: bool
    up_to: bool
    keep_count_expr: U_keep_count_expr = MISSING
    source: str = MISSING


@dataclass(frozen=True)
class T_effect__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    target: U_target
    filter: U_filter = MISSING
    random: bool = MISSING
    unless_filter: U_unless_filter = MISSING


@dataclass(frozen=True)
class T_effect__DiscardCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DiscardCard"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_effect__Discover(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discover"
    mana_value_limit: U_mana_value_limit
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__Double(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Double"
    target: U_target
    target_kind: U_target_kind


@dataclass(frozen=True)
class T_effect__DoublePT(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoublePT"
    factor: int
    mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__DoublePTAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoublePTAll"
    factor: int
    mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__DraftFromSpellbook(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DraftFromSpellbook"
    destination: str
    random: bool
    tapped: bool


@dataclass(frozen=True)
class T_effect__Draw(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Draw"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__EachDealsDamageEqualToPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachDealsDamageEqualToPower"
    recipient: U_recipient
    sources: U_sources
    extra_source: U_extra_source = MISSING


@dataclass(frozen=True)
class T_effect__EachPlayerCopyChosen(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachPlayerCopyChosen"
    choose_filter: U_choose_filter
    copy_modifications: list[U_copy_modifications]
    max: int
    min: int
    scale: S_scale


@dataclass(frozen=True)
class T_effect__EachSourceDealsDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachSourceDealsDamage"
    amount: U_amount
    recipient: U_recipient
    sources: U_sources


@dataclass(frozen=True)
class T_effect__Encore(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Encore"


@dataclass(frozen=True)
class T_effect__EndCombatPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndCombatPhase"


@dataclass(frozen=True)
class T_effect__EndTheTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndTheTurn"


@dataclass(frozen=True)
class T_effect__Endure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Endure"
    amount: U_amount
    subject: U_subject


@dataclass(frozen=True)
class T_effect__ExchangeControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeControl"
    target_a: U_target_a
    target_b: U_target_b


@dataclass(frozen=True)
class T_effect__ExchangeLifeTotals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeLifeTotals"
    player_a: U_player_a
    player_b: U_player_b


@dataclass(frozen=True)
class T_effect__ExchangeLifeWithStat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeLifeWithStat"
    player: U_player
    stat: str


@dataclass(frozen=True)
class T_effect__ExileFromTopUntil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileFromTopUntil"
    player: U_player
    until: U_until


@dataclass(frozen=True)
class T_effect__ExileHaunting(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileHaunting"
    target: U_target


@dataclass(frozen=True)
class T_effect__ExileResolvingSpellInsteadOfGraveyard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileResolvingSpellInsteadOfGraveyard"


@dataclass(frozen=True)
class T_effect__ExileTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileTop"
    count: U_count
    player: U_player
    face_down: bool = MISSING


@dataclass(frozen=True)
class T_effect__Explore(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Explore"


@dataclass(frozen=True)
class T_effect__ExploreAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExploreAll"
    filter: U_filter


@dataclass(frozen=True)
class T_effect__ExtraTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExtraTurn"
    target: U_target


@dataclass(frozen=True)
class T_effect__Fight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fight"
    subject: U_subject
    target: U_target


@dataclass(frozen=True)
class T_effect__FlipCoin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoin"
    lose_effect: None | S_lose_effect
    win_effect: None | S_win_effect
    flipper: U_flipper = MISSING


@dataclass(frozen=True)
class T_effect__FlipCoinUntilLose(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoinUntilLose"
    win_effect: S_win_effect


@dataclass(frozen=True)
class T_effect__FlipCoins(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoins"
    count: U_count
    lose_effect: None
    win_effect: None | S_win_effect


@dataclass(frozen=True)
class T_effect__ForEachCategory(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForEachCategory"
    action: U_action
    category: str
    chooser: str


@dataclass(frozen=True)
class T_effect__Forage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Forage"


@dataclass(frozen=True)
class T_effect__ForceAttack(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForceAttack"
    duration: str
    required_player: U_required_player
    target: U_target


@dataclass(frozen=True)
class T_effect__ForceBlock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForceBlock"
    target: U_target


@dataclass(frozen=True)
class T_effect__FreeCastFromZones(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FreeCastFromZones"
    count: int
    exile_instead_of_graveyard: bool
    filter: U_filter
    max_total_mv: int
    zones: list[object]


@dataclass(frozen=True)
class T_effect__GainActivatedAbilitiesOfTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainActivatedAbilitiesOfTarget"
    duration: str
    recipient: U_recipient
    scope: str
    target: U_target


@dataclass(frozen=True)
class T_effect__GainControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainControl"
    target: U_target


@dataclass(frozen=True)
class T_effect__GainControlAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainControlAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__GainEnergy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainEnergy"
    amount: U_amount


@dataclass(frozen=True)
class T_effect__GainLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainLife"
    amount: U_amount
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__GenericEffect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GenericEffect"
    duration: None | str | MirrorVariant
    static_abilities: list[S_static_abilities]
    target: None | U_target


@dataclass(frozen=True)
class T_effect__GiftDelivery(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GiftDelivery"
    kind: U_kind


@dataclass(frozen=True)
class T_effect__GiveControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GiveControl"
    recipient: U_recipient
    target: U_target


@dataclass(frozen=True)
class T_effect__GivePlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GivePlayerCounter"
    count: U_count
    counter_kind: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Goad(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Goad"
    target: U_target


@dataclass(frozen=True)
class T_effect__GoadAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GoadAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__GrantCastingPermission(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantCastingPermission"
    permission: U_permission
    target: U_target
    grantee: U_grantee = MISSING


@dataclass(frozen=True)
class T_effect__GrantExtraLoyaltyActivations(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantExtraLoyaltyActivations"
    amount: U_amount
    target: U_target


@dataclass(frozen=True)
class T_effect__GrantNextSpellAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantNextSpellAbility"
    modifier: U_modifier
    player: U_player
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_effect__Harness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Harness"


@dataclass(frozen=True)
class T_effect__Heist(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Heist"
    look_count: int
    target: U_target


@dataclass(frozen=True)
class T_effect__HideawayConceal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HideawayConceal"
    target: U_target


@dataclass(frozen=True)
class T_effect__Incubate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Incubate"
    count: U_count


@dataclass(frozen=True)
class T_effect__Intensify(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Intensify"
    amount: U_amount
    scope: U_scope


@dataclass(frozen=True)
class T_effect__Investigate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Investigate"


@dataclass(frozen=True)
class T_effect__Learn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Learn"


@dataclass(frozen=True)
class T_effect__LoseAllPlayerCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseAllPlayerCounters"
    target: U_target


@dataclass(frozen=True)
class T_effect__LoseLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseLife"
    amount: U_amount
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__LoseTheGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseTheGame"
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__MadnessCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MadnessCast"
    cost: U_cost


@dataclass(frozen=True)
class T_effect__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    produced: U_produced
    expiry: str = MISSING
    grants: list[U_grants | MirrorVariant] = MISSING
    restrictions: list[MirrorVariant] = MISSING
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__Manifest(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Manifest"
    count: U_count
    target: U_target
    enters_under: str = MISSING
    profile: S_profile = MISSING


@dataclass(frozen=True)
class T_effect__ManifestDread(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManifestDread"


@dataclass(frozen=True)
class T_effect__Meld(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Meld"
    partner: str
    result: str
    source: str


@dataclass(frozen=True)
class T_effect__Mill(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mill"
    count: U_count
    destination: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Monstrosity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Monstrosity"
    count: U_count


@dataclass(frozen=True)
class T_effect__MoveCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MoveCounters"
    count: None | U_count
    counter_type: None | str
    mode: str
    selection: str
    source: U_source
    target: U_target


@dataclass(frozen=True)
class T_effect__MultiplyCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MultiplyCounter"
    counter_type: str
    multiplier: int
    target: U_target


@dataclass(frozen=True)
class T_effect__Myriad(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Myriad"


@dataclass(frozen=True)
class T_effect__NoOp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoOp"


@dataclass(frozen=True)
class T_effect__OpenAttractions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpenAttractions"
    count: int


@dataclass(frozen=True)
class T_effect__OpponentGuess(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentGuess"
    guesser: str | MirrorVariant
    subject: U_subject


@dataclass(frozen=True)
class T_effect__PairWith(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PairWith"
    target: U_target


@dataclass(frozen=True)
class T_effect__PayCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayCost"
    cost: U_cost
    payer: U_payer
    scale: U_scale = MISSING


@dataclass(frozen=True)
class T_effect__PhaseIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PhaseIn"
    target: U_target


@dataclass(frozen=True)
class T_effect__PhaseOut(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PhaseOut"
    target: U_target


@dataclass(frozen=True)
class T_effect__Planeswalk(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Planeswalk"


@dataclass(frozen=True)
class T_effect__Populate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Populate"


@dataclass(frozen=True)
class T_effect__PreventDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreventDamage"
    amount: str | MirrorVariant
    scope: str
    target: U_target
    amount_dynamic: U_amount_dynamic = MISSING
    damage_source_filter: U_damage_source_filter = MISSING
    prevention_duration: str = MISSING


@dataclass(frozen=True)
class T_effect__Proliferate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Proliferate"


@dataclass(frozen=True)
class T_effect__ProliferateTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProliferateTarget"
    target: U_target


@dataclass(frozen=True)
class T_effect__Pump(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Pump"
    power: U_power
    target: U_target
    toughness: U_toughness


@dataclass(frozen=True)
class T_effect__PumpAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PumpAll"
    power: U_power
    target: U_target
    toughness: U_toughness


@dataclass(frozen=True)
class T_effect__PutAtLibraryPosition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutAtLibraryPosition"
    count: U_count
    position: U_position
    target: U_target


@dataclass(frozen=True)
class T_effect__PutChosenCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutChosenCounter"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__PutCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutCounter"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_effect__PutCounterAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutCounterAll"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_effect__PutOnTopOrBottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutOnTopOrBottom"
    target: U_target


@dataclass(frozen=True)
class T_effect__PutSticker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutSticker"
    count: U_count
    target: U_target
    kind: str = MISSING
    max_ticket_cost: U_max_ticket_cost = MISSING
    ticket_cost_payment: str = MISSING


@dataclass(frozen=True)
class T_effect__ReassembleContraption(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReassembleContraption"
    control_mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__RedistributeLifeTotals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RedistributeLifeTotals"


@dataclass(frozen=True)
class T_effect__ReduceNextSpellCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReduceNextSpellCost"
    amount: int
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_effect__Regenerate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Regenerate"
    target: U_target


@dataclass(frozen=True)
class T_effect__RegisterBending(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RegisterBending"
    kind: str


@dataclass(frozen=True)
class T_effect__RememberCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RememberCard"
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveAllDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllDamage"
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveCounter"
    count: U_count
    counter_type: None | str
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveFromCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveFromCombat"
    target: U_target


@dataclass(frozen=True)
class T_effect__Renown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Renown"
    count: U_count


@dataclass(frozen=True)
class T_effect__ReturnAsAura(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReturnAsAura"
    enchant_filter: U_enchant_filter
    grants: list[U_grants | MirrorVariant]


@dataclass(frozen=True)
class T_effect__Reveal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Reveal"
    target: U_target


@dataclass(frozen=True)
class T_effect__RevealFromHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealFromHand"
    filter: U_filter
    on_decline: S_on_decline


@dataclass(frozen=True)
class T_effect__RevealHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealHand"
    card_filter: U_card_filter
    count: None | U_count
    reveal: bool
    target: U_target
    choice_optional: bool = MISSING
    random: bool = MISSING


@dataclass(frozen=True)
class T_effect__RevealTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealTop"
    count: int
    player: U_player


@dataclass(frozen=True)
class T_effect__RevealUntil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealUntil"
    count: U_count
    filter: U_filter
    kept_destination: str
    player: U_player
    rest_destination: str
    enter_tapped: bool = MISSING
    enters_attacking: bool = MISSING
    enters_under: str = MISSING
    kept_optional_to: str = MISSING
    matched_disposition: U_matched_disposition = MISSING


@dataclass(frozen=True)
class T_effect__ReverseTurnOrder(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReverseTurnOrder"


@dataclass(frozen=True)
class T_effect__RingTemptsYou(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RingTemptsYou"


@dataclass(frozen=True)
class T_effect__RollDie(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RollDie"
    count: U_count
    results: list[S_results]
    sides: int
    modifier: U_modifier = MISSING


@dataclass(frozen=True)
class T_effect__RollToVisitAttractions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RollToVisitAttractions"


@dataclass(frozen=True)
class T_effect__RuntimeHandled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RuntimeHandled"
    handler: str


@dataclass(frozen=True)
class T_effect__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: U_count
    target: U_target
    min_count: int = MISSING


@dataclass(frozen=True)
class T_effect__Scry(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Scry"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__SearchLibrary(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SearchLibrary"
    count: U_count
    filter: U_filter
    reveal: bool
    selection_constraint: U_selection_constraint = MISSING
    source_zones: list[object] = MISSING
    split: S_split = MISSING
    target_player: U_target_player = MISSING


@dataclass(frozen=True)
class T_effect__SearchOutsideGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SearchOutsideGame"
    count: U_count
    destination: str
    filter: U_filter
    reveal: bool
    source_pool: U_source_pool = MISSING


@dataclass(frozen=True)
class T_effect__Seek(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Seek"
    count: U_count
    destination: str
    enter_tapped: bool
    filter: U_filter
    from_top: int = MISSING


@dataclass(frozen=True)
class T_effect__SeparateIntoPiles(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SeparateIntoPiles"
    chooser: U_chooser
    chosen_pile_effect: S_chosen_pile_effect
    object_filter: U_object_filter
    partition_subject: U_partition_subject
    pile_source: U_pile_source
    unchosen_pile_effect: None | S_unchosen_pile_effect


@dataclass(frozen=True)
class T_effect__SetClassLevel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetClassLevel"
    level: int


@dataclass(frozen=True)
class T_effect__SetDayNight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetDayNight"
    to: str


@dataclass(frozen=True)
class T_effect__SetLifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetLifeTotal"
    amount: U_amount
    target: U_target


@dataclass(frozen=True)
class T_effect__SetRoomDoorLock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetRoomDoorLock"
    op: U_op
    target: U_target


@dataclass(frozen=True)
class T_effect__SetTapState(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetTapState"
    scope: U_scope
    state: U_state
    target: U_target


@dataclass(frozen=True)
class T_effect__Shuffle(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Shuffle"
    target: U_target


@dataclass(frozen=True)
class T_effect__SkipNextStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SkipNextStep"
    count: U_count
    scope: str
    step: U_step
    target: U_target


@dataclass(frozen=True)
class T_effect__SkipNextTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SkipNextTurn"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__SolveCase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SolveCase"


@dataclass(frozen=True)
class T_effect__Specialize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Specialize"


@dataclass(frozen=True)
class T_effect__StartYourEngines(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StartYourEngines"
    player_scope: U_player_scope


@dataclass(frozen=True)
class T_effect__Surveil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Surveil"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__Suspect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Suspect"
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__SwapChosenLabels(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwapChosenLabels"
    first: str
    second: str


@dataclass(frozen=True)
class T_effect__SwitchPT(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwitchPT"
    target: U_target


@dataclass(frozen=True)
class T_effect__TakeTheInitiative(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TakeTheInitiative"


@dataclass(frozen=True)
class T_effect__TargetOnly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetOnly"
    target: U_target


@dataclass(frozen=True)
class T_effect__TimeTravel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TimeTravel"


@dataclass(frozen=True)
class T_effect__Token(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Token"
    colors: list[U_colors]
    count: U_count
    enters_attacking: bool
    keywords: list[MirrorVariant]
    name: str
    owner: U_owner
    power: U_power
    tapped: bool
    toughness: U_toughness
    types: list[object]
    attach_to: U_attach_to = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    static_abilities: list[S_static_abilities] = MISSING
    supertypes: list[object] = MISSING


@dataclass(frozen=True)
class T_effect__Transform(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Transform"
    target: U_target


@dataclass(frozen=True)
class T_effect__Tribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tribute"
    count: int


@dataclass(frozen=True)
class T_effect__TurnFaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnFaceDown"
    profile: S_profile
    target: U_target


@dataclass(frozen=True)
class T_effect__TurnFaceUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnFaceUp"
    target: U_target


@dataclass(frozen=True)
class T_effect__UnattachAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnattachAll"
    attachment: U_attachment
    target: U_target


@dataclass(frozen=True)
class T_effect__Unimplemented(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unimplemented"
    description: None | str
    name: str


@dataclass(frozen=True)
class T_effect__Unsuspect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unsuspect"
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__VentureIntoDungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VentureIntoDungeon"


@dataclass(frozen=True)
class T_effect__Vote(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Vote"
    choices: list[object]
    per_choice_effect: list[S_per_choice_effect]
    starting_with: str
    subject: U_subject
    tally_mode: U_tally_mode
    visibility: U_visibility
    voter_scope: U_voter_scope


@dataclass(frozen=True)
class T_effect__WinTheGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WinTheGame"
    target: U_target = MISSING


@dataclass(frozen=True)
class T_enchant_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_enter_with_counters__ClampMin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClampMin"
    inner: U_inner
    minimum: int


@dataclass(frozen=True)
class T_enter_with_counters__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_enter_with_counters__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_enter_with_counters__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_enters_modified_if__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_entwine_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_excess__TargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetController"


@dataclass(frozen=True)
class T_exclude__CreatureTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreatureTypes"


@dataclass(frozen=True)
class T_exclude__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_exclude__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_expiry__EndOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndOfTurn"


@dataclass(frozen=True)
class T_exponent__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_exprs__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_exprs__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_exprs__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_extra_source__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_filter__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_filter__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filter__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_filter__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_filter__ControlsCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCount"
    comparator: str
    count: U_count
    filter: U_filter
    relation: U_relation


@dataclass(frozen=True)
class T_filter__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_filter__GrantingObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantingObject"


@dataclass(frozen=True)
class T_filter__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


@dataclass(frozen=True)
class T_filter__HasLostTheGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasLostTheGame"


@dataclass(frozen=True)
class T_filter__Named(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Named"
    name: str


@dataclass(frozen=True)
class T_filter__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    filter: U_filter


@dataclass(frozen=True)
class T_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_filter__OpponentAttacked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttacked"
    scope: str
    subject: str


@dataclass(frozen=True)
class T_filter__OpponentDealtDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentDealtDamage"
    kind: str
    source: U_source = MISSING


@dataclass(frozen=True)
class T_filter__OpponentGainedLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentGainedLife"


@dataclass(frozen=True)
class T_filter__OpponentLostLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentLostLife"


@dataclass(frozen=True)
class T_filter__OpponentOfTriggeringPlayerNotAttacked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOfTriggeringPlayerNotAttacked"


@dataclass(frozen=True)
class T_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filter__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_filter__PerformedActionThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerformedActionThisWay"
    action: str
    relation: U_relation


@dataclass(frozen=True)
class T_filter__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_filter__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_filter__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str | MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_filters__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filters__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_filters__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_filters__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_filters__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_filters__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


@dataclass(frozen=True)
class T_filters__LastCreated(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastCreated"


@dataclass(frozen=True)
class T_filters__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    filter: U_filter


@dataclass(frozen=True)
class T_filters__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filters__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_filters__ParentTargetSlot(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetSlot"
    index: int


@dataclass(frozen=True)
class T_filters__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_filters__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_filters__StackAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackAbility"
    controller: str = MISSING
    kind: str = MISSING


@dataclass(frozen=True)
class T_filters__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_filters__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_filters__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_filters__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_filters__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str | MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_flipper__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_flipper__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_forced_to__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_forced_to__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_grantee__ObjectOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectOwner"


@dataclass(frozen=True)
class T_grantee__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_grants__GrantAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantAbility"
    definition: S_definition


@dataclass(frozen=True)
class T_grants__RemoveAllAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllAbilities"


@dataclass(frozen=True)
class T_host__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_host__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_inner__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_inner__CastDuringPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastDuringPhase"
    phases: list[object]


@dataclass(frozen=True)
class T_inner__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    zone: str


@dataclass(frozen=True)
class T_inner__CastVariantPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaid"
    variant: str


@dataclass(frozen=True)
class T_inner__ClampMin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClampMin"
    inner: U_inner
    minimum: int


@dataclass(frozen=True)
class T_inner__ControllerControlledMatchingAsCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlledMatchingAsCast"
    filter: U_filter


@dataclass(frozen=True)
class T_inner__CostPaidObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObjectMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_inner__DayNightIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DayNightIs"
    state: str


@dataclass(frozen=True)
class T_inner__EventOutcomeWon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventOutcomeWon"


@dataclass(frozen=True)
class T_inner__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_inner__HasCityBlessing(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCityBlessing"


@dataclass(frozen=True)
class T_inner__IsMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsMonarch"


@dataclass(frozen=True)
class T_inner__ManaColorSpent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaColorSpent"
    color: str
    minimum: int


@dataclass(frozen=True)
class T_inner__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_inner__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    condition: U_condition


@dataclass(frozen=True)
class T_inner__NthResolutionThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthResolutionThisTurn"
    n: int


@dataclass(frozen=True)
class T_inner__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_inner__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_inner__QuantityCheck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityCheck"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_inner__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_inner__RevealedHasCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealedHasCardType"
    card_types: list[MirrorVariant]
    subtype_filter: U_subtype_filter


@dataclass(frozen=True)
class T_inner__SourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_inner__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_inner__TargetMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetMatchesFilter"
    filter: U_filter
    use_lki: bool


@dataclass(frozen=True)
class T_inner__ZoneChangeObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectMatchesFilter"
    destination: str
    filter: U_filter


@dataclass(frozen=True)
class T_inner__ZoneChangedThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisWay"
    filter: U_filter


@dataclass(frozen=True)
class T_invalidation__UntilNextGrantFromSameSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UntilNextGrantFromSameSource"


@dataclass(frozen=True)
class T_iteration_kind_binding__RebindToIteratedKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RebindToIteratedKind"


@dataclass(frozen=True)
class T_keep_count_expr__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_kind__Card(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Card"


@dataclass(frozen=True)
class T_kind__Food(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Food"


@dataclass(frozen=True)
class T_kind__TappedFish(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TappedFish"


@dataclass(frozen=True)
class T_kind__Treasure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Treasure"


@dataclass(frozen=True)
class T_land_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_left__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_lhs__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_lhs__HandSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSize"
    player: U_player


@dataclass(frozen=True)
class T_lhs__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_lhs__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_library_position__Bottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bottom"


@dataclass(frozen=True)
class T_library_position__Top(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Top"


@dataclass(frozen=True)
class T_life_payment__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_mana_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_mana_cost__NoCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoCost"


@dataclass(frozen=True)
class T_mana_modification__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int


@dataclass(frozen=True)
class T_mana_modification__ReplaceWith(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReplaceWith"
    mana_type: str


@dataclass(frozen=True)
class T_mana_reduction__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_mana_replacement_scope__TappedForMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TappedForMana"


@dataclass(frozen=True)
class T_mana_value_limit__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_mana_value_limit__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_matched_disposition__ChooseAnyNumber(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseAnyNumber"


@dataclass(frozen=True)
class T_matched_disposition__RevealOnly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealOnly"


@dataclass(frozen=True)
class T_materials__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_max__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_max__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_max__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_max_ticket_cost__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_metric__DistinctColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColors"


@dataclass(frozen=True)
class T_metric__FromSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FromSource"
    source_filter: U_source_filter


@dataclass(frozen=True)
class T_metric__Total(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Total"


@dataclass(frozen=True)
class T_min__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_mode__Mandatory(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mandatory"


@dataclass(frozen=True)
class T_mode__MayCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MayCost"
    cost: U_cost
    decline: None | S_decline


@dataclass(frozen=True)
class T_mode__Optional(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Optional"
    decline: None | S_decline


@dataclass(frozen=True)
class T_mode_costs__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_modification__Double(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Double"


@dataclass(frozen=True)
class T_modifications__AddAllBasicLandTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddAllBasicLandTypes"


@dataclass(frozen=True)
class T_modifications__AddAllCreatureTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddAllCreatureTypes"


@dataclass(frozen=True)
class T_modifications__AddAllLandTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddAllLandTypes"


@dataclass(frozen=True)
class T_modifications__AddChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddChosenColor"


@dataclass(frozen=True)
class T_modifications__AddChosenKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddChosenKeyword"


@dataclass(frozen=True)
class T_modifications__AddChosenSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddChosenSubtype"
    kind: str


@dataclass(frozen=True)
class T_modifications__AddColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddColor"
    color: str


@dataclass(frozen=True)
class T_modifications__AddDynamicKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddDynamicKeyword"
    kind: str
    value: U_value


@dataclass(frozen=True)
class T_modifications__AddDynamicPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddDynamicPower"
    value: U_value


@dataclass(frozen=True)
class T_modifications__AddDynamicToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddDynamicToughness"
    value: U_value


@dataclass(frozen=True)
class T_modifications__AddKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_modifications__AddPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddPower"
    value: int


@dataclass(frozen=True)
class T_modifications__AddStaticMode(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddStaticMode"
    mode: str | MirrorVariant


@dataclass(frozen=True)
class T_modifications__AddSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddSubtype"
    subtype: str


@dataclass(frozen=True)
class T_modifications__AddSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddSupertype"
    supertype: str


@dataclass(frozen=True)
class T_modifications__AddToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddToughness"
    value: int


@dataclass(frozen=True)
class T_modifications__AddType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddType"
    core_type: str


@dataclass(frozen=True)
class T_modifications__AssignDamageAsThoughUnblocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AssignDamageAsThoughUnblocked"


@dataclass(frozen=True)
class T_modifications__AssignDamageFromToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AssignDamageFromToughness"


@dataclass(frozen=True)
class T_modifications__AssignNoCombatDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AssignNoCombatDamage"


@dataclass(frozen=True)
class T_modifications__ChangeController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeController"


@dataclass(frozen=True)
class T_modifications__GrantAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantAbility"
    definition: S_definition


@dataclass(frozen=True)
class T_modifications__GrantAllActivatedAbilitiesOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantAllActivatedAbilitiesOf"
    source: U_source
    cap: U_cap = MISSING


@dataclass(frozen=True)
class T_modifications__GrantAllTriggeredAbilitiesOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantAllTriggeredAbilitiesOf"
    source: U_source


@dataclass(frozen=True)
class T_modifications__GrantStaticAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantStaticAbility"
    definition: S_definition


@dataclass(frozen=True)
class T_modifications__GrantTrigger(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantTrigger"
    trigger: S_trigger


@dataclass(frozen=True)
class T_modifications__RemoveAllAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllAbilities"


@dataclass(frozen=True)
class T_modifications__RemoveAllSubtypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllSubtypes"
    set: str


@dataclass(frozen=True)
class T_modifications__RemoveKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_modifications__RemoveSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveSupertype"
    supertype: str


@dataclass(frozen=True)
class T_modifications__RemoveType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveType"
    core_type: str


@dataclass(frozen=True)
class T_modifications__SetBasicLandType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetBasicLandType"
    land_type: str


@dataclass(frozen=True)
class T_modifications__SetCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetCardTypes"
    core_types: list[object]


@dataclass(frozen=True)
class T_modifications__SetChosenBasicLandType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetChosenBasicLandType"


@dataclass(frozen=True)
class T_modifications__SetChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetChosenName"


@dataclass(frozen=True)
class T_modifications__SetColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetColor"
    colors: list[U_colors]


@dataclass(frozen=True)
class T_modifications__SetDynamicPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetDynamicPower"
    value: U_value


@dataclass(frozen=True)
class T_modifications__SetDynamicToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetDynamicToughness"
    value: U_value


@dataclass(frozen=True)
class T_modifications__SetName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetName"
    name: str


@dataclass(frozen=True)
class T_modifications__SetPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetPower"
    value: int


@dataclass(frozen=True)
class T_modifications__SetPowerDynamic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetPowerDynamic"
    value: U_value


@dataclass(frozen=True)
class T_modifications__SetToughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetToughness"
    value: int


@dataclass(frozen=True)
class T_modifications__SetToughnessDynamic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetToughnessDynamic"
    value: U_value


@dataclass(frozen=True)
class T_modifier__Add(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Add"
    value: U_value


@dataclass(frozen=True)
class T_modifier__CantBeCountered(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CantBeCountered"


@dataclass(frozen=True)
class T_modifier__CastAsThoughFlash(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastAsThoughFlash"


@dataclass(frozen=True)
class T_modifier__HasKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_modifier__Subtract(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Subtract"
    value: U_value


@dataclass(frozen=True)
class T_modifier__WithoutPayingManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithoutPayingManaCost"


@dataclass(frozen=True)
class T_object_filter__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_object_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_object_source__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_object_source__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_once_per_turn__OnlyOnceEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnceEachTurn"


@dataclass(frozen=True)
class T_only_tag__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_op__LockOrUnlock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LockOrUnlock"


@dataclass(frozen=True)
class T_op__Unlock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unlock"


@dataclass(frozen=True)
class T_origin__Equals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equals"
    data: str


@dataclass(frozen=True)
class T_origin__NotEquals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotEquals"
    data: str


@dataclass(frozen=True)
class T_origin__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    data: list[U_data | S_data | MirrorVariant]


@dataclass(frozen=True)
class T_origin_constraint__Equals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equals"
    data: str


@dataclass(frozen=True)
class T_owner__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_owner__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_owner__OriginalController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OriginalController"


@dataclass(frozen=True)
class T_owner__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_owner__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_owner__ParentTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetOwner"


@dataclass(frozen=True)
class T_owner__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_owner__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_owner__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_owner__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_owner__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str | MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_parity__LastNamedChoice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastNamedChoice"


@dataclass(frozen=True)
class T_parse_warnings__IgnoredRemainder(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IgnoredRemainder"
    line_index: int
    parser: str
    text: str


@dataclass(frozen=True)
class T_parse_warnings__SwallowedClause(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwallowedClause"
    description: str
    detector: str
    line_index: int


@dataclass(frozen=True)
class T_parse_warnings__TargetFallback(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetFallback"
    context: str
    line_index: int
    text: str


@dataclass(frozen=True)
class T_partition_subject__AnOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnOpponent"


@dataclass(frozen=True)
class T_partition_subject__EachOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachOpponent"


@dataclass(frozen=True)
class T_payer__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_payer__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_payer__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_payer__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_payer__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_payer__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_payer__TriggeringSpellController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellController"


@dataclass(frozen=True)
class T_payer__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_per_player_condition__YouAttackedSourceControllerThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedSourceControllerThisTurn"


@dataclass(frozen=True)
class T_per_player_condition__YouAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedThisTurn"


@dataclass(frozen=True)
class T_per_player_condition__YouCastSpellThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouCastSpellThisTurn"


@dataclass(frozen=True)
class T_permission__ExileWithAltCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileWithAltCost"
    cost: U_cost


@dataclass(frozen=True)
class T_permission__ExileWithEnergyCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileWithEnergyCost"


@dataclass(frozen=True)
class T_permission__Foretold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Foretold"
    cost: U_cost
    turn_foretold: int


@dataclass(frozen=True)
class T_permission__PlayFromExile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayFromExile"
    duration: str | MirrorVariant
    granted_to: int
    card_filter: U_card_filter = MISSING
    cast_cost_raise: U_cast_cost_raise = MISSING
    frequency: str = MISSING
    invalidation: U_invalidation = MISSING
    land_enter_tapped: str = MISSING
    mana_spend_permission: str = MISSING
    single_use: bool = MISSING


@dataclass(frozen=True)
class T_permission__Plotted(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Plotted"
    turn_plotted: int


@dataclass(frozen=True)
class T_pile_source__Battlefield(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Battlefield"


@dataclass(frozen=True)
class T_pile_source__ExiledThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledThisWay"


@dataclass(frozen=True)
class T_pile_source__RevealedFromLibraryTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealedFromLibraryTop"
    data: MirrorVariant


@dataclass(frozen=True)
class T_player__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"
    aggregate: str
    exclude: U_exclude = MISSING


@dataclass(frozen=True)
class T_player__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_player__AnyTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyTurn"


@dataclass(frozen=True)
class T_player__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_player__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_player__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"
    aggregate: str = MISSING


@dataclass(frozen=True)
class T_player__OpponentDealtDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentDealtDamage"
    kind: str
    min_sources: int
    source: U_source


@dataclass(frozen=True)
class T_player__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_player__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_player__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_player__ParentTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetOwner"


@dataclass(frozen=True)
class T_player__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player__PostReplacementDamageTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageTarget"


@dataclass(frozen=True)
class T_player__RecipientController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientController"


@dataclass(frozen=True)
class T_player__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_player__SourceChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceChosenPlayer"


@dataclass(frozen=True)
class T_player__Target(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Target"


@dataclass(frozen=True)
class T_player__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_player__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_player_a__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_player_a__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player_b__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player_b__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_player_filter__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_player_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_player_filter__OpponentOtherThanTriggering(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOtherThanTriggering"


@dataclass(frozen=True)
class T_player_scope__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_player_scope__AllExcept(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllExcept"
    exclude: U_exclude


@dataclass(frozen=True)
class T_player_scope__ChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenPlayer"
    index: int


@dataclass(frozen=True)
class T_player_scope__ControlsCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCount"
    comparator: str
    count: U_count
    filter: U_filter
    relation: U_relation


@dataclass(frozen=True)
class T_player_scope__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_player_scope__HighestSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HighestSpeed"


@dataclass(frozen=True)
class T_player_scope__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_player_scope__OpponentAttacked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttacked"
    scope: str
    subject: str


@dataclass(frozen=True)
class T_player_scope__OpponentAttackingEnchantedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttackingEnchantedPlayer"


@dataclass(frozen=True)
class T_player_scope__OpponentOfTriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOfTriggeringPlayer"


@dataclass(frozen=True)
class T_player_scope__OwnersOfCardsExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OwnersOfCardsExiledBySource"


@dataclass(frozen=True)
class T_player_scope__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_player_scope__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_player_scope__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_player_scope__VotedFor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VotedFor"
    choice_index: int


@dataclass(frozen=True)
class T_position__BeneathTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeneathTop"
    depth: U_depth


@dataclass(frozen=True)
class T_position__Bottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bottom"


@dataclass(frozen=True)
class T_position__NthFromTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthFromTop"
    n: int


@dataclass(frozen=True)
class T_position__Top(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Top"


@dataclass(frozen=True)
class T_power__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_power__Quantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Quantity"
    value: U_value


@dataclass(frozen=True)
class T_power__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    value: str


@dataclass(frozen=True)
class T_produced__AnyCombination(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyCombination"
    color_options: list[object]
    count: U_count


@dataclass(frozen=True)
class T_produced__AnyCombinationOfObjectColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyCombinationOfObjectColors"
    count: U_count
    scope: U_scope


@dataclass(frozen=True)
class T_produced__AnyInCommandersColorIdentity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyInCommandersColorIdentity"
    count: U_count


@dataclass(frozen=True)
class T_produced__AnyOneColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOneColor"
    color_options: list[object]
    count: U_count
    contribution: str = MISSING


@dataclass(frozen=True)
class T_produced__AnyOneColorAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOneColorAmongPermanents"
    count: U_count
    filter: U_filter


@dataclass(frozen=True)
class T_produced__AnyTypeProduceableBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyTypeProduceableBy"
    count: U_count
    land_filter: U_land_filter


@dataclass(frozen=True)
class T_produced__ChoiceAmongCombinations(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChoiceAmongCombinations"
    options: list[MirrorVariant]


@dataclass(frozen=True)
class T_produced__ChoiceAmongExiledColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChoiceAmongExiledColors"
    source: U_source


@dataclass(frozen=True)
class T_produced__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"
    count: U_count
    contribution: str = MISSING
    fixed_alternative: str = MISSING


@dataclass(frozen=True)
class T_produced__Colorless(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Colorless"
    count: U_count


@dataclass(frozen=True)
class T_produced__DistinctColorsAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColorsAmongPermanents"
    filter: U_filter


@dataclass(frozen=True)
class T_produced__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    colors: list[U_colors]
    contribution: str = MISSING


@dataclass(frozen=True)
class T_produced__Mixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mixed"
    colorless_count: int
    colors: list[U_colors]


@dataclass(frozen=True)
class T_produced__OpponentLandColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentLandColors"
    count: U_count


@dataclass(frozen=True)
class T_produced__TriggerEventManaType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggerEventManaType"


@dataclass(frozen=True)
class T_prop__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"


@dataclass(frozen=True)
class T_prop__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"


@dataclass(frozen=True)
class T_prop__InTrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InTrackedSet"
    id: int


@dataclass(frozen=True)
class T_prop__SameName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameName"


@dataclass(frozen=True)
class T_prop__SharesQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesQuality"
    quality: str
    reference: U_reference


@dataclass(frozen=True)
class T_prop__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_properties__Another(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Another"


@dataclass(frozen=True)
class T_properties__AnyOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOf"
    props: list[U_props]


@dataclass(frozen=True)
class T_properties__AttachedToRecipient(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedToRecipient"


@dataclass(frozen=True)
class T_properties__AttachedToSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedToSource"


@dataclass(frozen=True)
class T_properties__AttackedOrBlockedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedOrBlockedThisTurn"


@dataclass(frozen=True)
class T_properties__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"
    defender: str = MISSING


@dataclass(frozen=True)
class T_properties__Attacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attacking"
    defender: str = MISSING


@dataclass(frozen=True)
class T_properties__AttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackingAlone"


@dataclass(frozen=True)
class T_properties__BlockedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockedThisTurn"


@dataclass(frozen=True)
class T_properties__Blocking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Blocking"


@dataclass(frozen=True)
class T_properties__BlockingSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockingSource"


@dataclass(frozen=True)
class T_properties__CanEnchant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CanEnchant"
    target: U_target


@dataclass(frozen=True)
class T_properties__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_properties__ColorCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ColorCount"
    comparator: str
    count: int


@dataclass(frozen=True)
class T_properties__CombatRelation(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CombatRelation"
    relation: str
    subject: str


@dataclass(frozen=True)
class T_properties__ControlledContinuouslySinceTurnBegan(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlledContinuouslySinceTurnBegan"


@dataclass(frozen=True)
class T_properties__ControllerChoseLabel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerChoseLabel"
    label: str


@dataclass(frozen=True)
class T_properties__ControllerMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerMatches"
    player: U_player


@dataclass(frozen=True)
class T_properties__ConvokedSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConvokedSource"


@dataclass(frozen=True)
class T_properties__CouldBeTargetedByTriggeringSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CouldBeTargetedByTriggeringSpell"


@dataclass(frozen=True)
class T_properties__Counters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counters"
    comparator: str
    count: U_count
    counters: U_counters


@dataclass(frozen=True)
class T_properties__CountersPutOnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersPutOnThisTurn"
    actor: str
    comparator: str
    count: int
    counters: U_counters


@dataclass(frozen=True)
class T_properties__DifferentNameFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DifferentNameFrom"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__DistinctFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctFrom"
    reference: U_reference


@dataclass(frozen=True)
class T_properties__EnchantedBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnchantedBy"


@dataclass(frozen=True)
class T_properties__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"


@dataclass(frozen=True)
class T_properties__EquippedBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EquippedBy"


@dataclass(frozen=True)
class T_properties__FaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FaceDown"


@dataclass(frozen=True)
class T_properties__Foretold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Foretold"


@dataclass(frozen=True)
class T_properties__HasAnyAttachmentOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAnyAttachmentOf"
    kinds: list[object]


@dataclass(frozen=True)
class T_properties__HasAttachment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAttachment"
    kind: str
    controller: str = MISSING
    exclude_source: bool = MISSING


@dataclass(frozen=True)
class T_properties__HasColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasColor"
    color: str


@dataclass(frozen=True)
class T_properties__HasKeywordKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasKeywordKind"
    value: str


@dataclass(frozen=True)
class T_properties__HasManaAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasManaAbility"


@dataclass(frozen=True)
class T_properties__HasNoAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasNoAbilities"


@dataclass(frozen=True)
class T_properties__HasSingleTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasSingleTarget"


@dataclass(frozen=True)
class T_properties__HasSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasSupertype"
    value: str


@dataclass(frozen=True)
class T_properties__HasXInActivationCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasXInActivationCost"


@dataclass(frozen=True)
class T_properties__HasXInManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasXInManaCost"


@dataclass(frozen=True)
class T_properties__Historic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Historic"


@dataclass(frozen=True)
class T_properties__InAnyZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InAnyZone"
    zones: list[object]


@dataclass(frozen=True)
class T_properties__InZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InZone"
    zone: str


@dataclass(frozen=True)
class T_properties__IsChosenCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCardType"


@dataclass(frozen=True)
class T_properties__IsChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenColor"


@dataclass(frozen=True)
class T_properties__IsChosenCreatureType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCreatureType"


@dataclass(frozen=True)
class T_properties__IsCommander(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsCommander"


@dataclass(frozen=True)
class T_properties__IsSaddled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsSaddled"


@dataclass(frozen=True)
class T_properties__ManaCostIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaCostIn"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_properties__ManaSymbolCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSymbolCount"
    color: str
    comparator: str
    value: int


@dataclass(frozen=True)
class T_properties__ManaValueParity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaValueParity"
    parity: U_parity


@dataclass(frozen=True)
class T_properties__MatchesLastChosenCardPredicate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesLastChosenCardPredicate"


@dataclass(frozen=True)
class T_properties__Modal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Modal"


@dataclass(frozen=True)
class T_properties__Modified(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Modified"


@dataclass(frozen=True)
class T_properties__MostPrevalentCreatureTypeIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MostPrevalentCreatureTypeIn"
    scope: str
    zone: str


@dataclass(frozen=True)
class T_properties__NameMatchesAnyPermanent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NameMatchesAnyPermanent"
    controller: None


@dataclass(frozen=True)
class T_properties__Named(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Named"
    name: str


@dataclass(frozen=True)
class T_properties__NonToken(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonToken"


@dataclass(frozen=True)
class T_properties__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    prop: U_prop


@dataclass(frozen=True)
class T_properties__NotColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotColor"
    color: str


@dataclass(frozen=True)
class T_properties__NotHistoric(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotHistoric"


@dataclass(frozen=True)
class T_properties__NotSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotSupertype"
    value: str


@dataclass(frozen=True)
class T_properties__OtherThanTriggerObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OtherThanTriggerObject"


@dataclass(frozen=True)
class T_properties__Owned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Owned"
    controller: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__PowerExceedsBase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerExceedsBase"


@dataclass(frozen=True)
class T_properties__PowerGTSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerGTSource"


@dataclass(frozen=True)
class T_properties__ProtectorMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProtectorMatches"
    controller: str


@dataclass(frozen=True)
class T_properties__PtComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PtComparison"
    comparator: str
    scope: str
    stat: str
    value: U_value


@dataclass(frozen=True)
class T_properties__Renowned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Renowned"


@dataclass(frozen=True)
class T_properties__SaddledSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SaddledSource"


@dataclass(frozen=True)
class T_properties__SameName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameName"


@dataclass(frozen=True)
class T_properties__SameNameAsParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameNameAsParentTarget"


@dataclass(frozen=True)
class T_properties__SharesQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesQuality"
    quality: str
    reference: U_reference = MISSING
    relation: str = MISSING


@dataclass(frozen=True)
class T_properties__Suspected(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Suspected"


@dataclass(frozen=True)
class T_properties__Tapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tapped"


@dataclass(frozen=True)
class T_properties__Targets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Targets"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__TargetsOnly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetsOnly"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__Token(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Token"


@dataclass(frozen=True)
class T_properties__ToughnessGTPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ToughnessGTPower"


@dataclass(frozen=True)
class T_properties__Transformed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Transformed"


@dataclass(frozen=True)
class T_properties__Unblocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unblocked"


@dataclass(frozen=True)
class T_properties__Unpaired(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unpaired"


@dataclass(frozen=True)
class T_properties__Untapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Untapped"


@dataclass(frozen=True)
class T_properties__WasDealtDamageThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasDealtDamageThisTurn"


@dataclass(frozen=True)
class T_properties__WasKicked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasKicked"


@dataclass(frozen=True)
class T_properties__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_properties__WithKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithKeyword"
    value: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__WithoutKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithoutKeyword"
    value: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__WithoutKeywordKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithoutKeywordKind"
    value: str


@dataclass(frozen=True)
class T_properties__ZoneChangedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisTurn"
    from_: str = field(metadata={"json": "from"})
    to: str


@dataclass(frozen=True)
class T_props__AttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackingAlone"


@dataclass(frozen=True)
class T_props__BlockingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockingAlone"


@dataclass(frozen=True)
class T_props__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_props__HasColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasColor"
    color: str


@dataclass(frozen=True)
class T_props__PtComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PtComparison"
    comparator: str
    scope: str
    stat: str
    value: U_value


@dataclass(frozen=True)
class T_qty__AdditionalCostPaymentCountFor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaymentCountFor"
    origin: str
    origin_ordinal: int


@dataclass(frozen=True)
class T_qty__Aggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Aggregate"
    filter: U_filter
    function: str
    property: str | MirrorVariant


@dataclass(frozen=True)
class T_qty__AttachmentsOnLeavingObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachmentsOnLeavingObject"
    controller: str
    kind: str


@dataclass(frozen=True)
class T_qty__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__BasicLandTypeCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BasicLandTypeCount"
    controller: str


@dataclass(frozen=True)
class T_qty__BattlefieldEntriesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BattlefieldEntriesThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__BendTypesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BendTypesThisTurn"


@dataclass(frozen=True)
class T_qty__CardsDiscardedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDiscardedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__CardsDrawnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDrawnThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__CardsExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsExiledBySource"


@dataclass(frozen=True)
class T_qty__ChosenNumber(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenNumber"


@dataclass(frozen=True)
class T_qty__ColorsInCommandersColorIdentity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ColorsInCommandersColorIdentity"


@dataclass(frozen=True)
class T_qty__CommanderCastFromCommandZoneCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CommanderCastFromCommandZoneCount"


@dataclass(frozen=True)
class T_qty__CommanderManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CommanderManaValue"
    owner: str


@dataclass(frozen=True)
class T_qty__ControlledByEachPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlledByEachPlayer"
    aggregate: str
    filter: U_filter


@dataclass(frozen=True)
class T_qty__ConvokedCreatureCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConvokedCreatureCount"


@dataclass(frozen=True)
class T_qty__CostXPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostXPaid"


@dataclass(frozen=True)
class T_qty__CounterAddedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterAddedThisTurn"
    actor: str
    counters: U_counters
    target: U_target


@dataclass(frozen=True)
class T_qty__CountersOn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOn"
    scope: U_scope
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_qty__CountersOnObjects(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOnObjects"
    filter: U_filter
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_qty__CrimesCommittedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CrimesCommittedThisTurn"


@dataclass(frozen=True)
class T_qty__DamageDealtThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageDealtThisTurn"
    source: U_source
    target: U_target
    aggregate: str = MISSING
    channel: str = MISSING
    damage_kind: str = MISSING
    group_by: str = MISSING


@dataclass(frozen=True)
class T_qty__DescendedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DescendedThisTurn"


@dataclass(frozen=True)
class T_qty__Devotion(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Devotion"
    colors: U_colors


@dataclass(frozen=True)
class T_qty__DistinctCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCardTypes"
    source: U_source


@dataclass(frozen=True)
class T_qty__DistinctColorsAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColorsAmongPermanents"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__DistinctCounterKindsAmong(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCounterKindsAmong"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__DistinctSubtypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctSubtypes"
    exclude: U_exclude
    source: U_source


@dataclass(frozen=True)
class T_qty__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__EventContextAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventContextAmount"


@dataclass(frozen=True)
class T_qty__ExiledCardPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledCardPower"
    index: int


@dataclass(frozen=True)
class T_qty__ExiledFromHandThisResolution(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledFromHandThisResolution"


@dataclass(frozen=True)
class T_qty__FilteredTrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FilteredTrackedSetSize"
    filter: U_filter
    caused_by: str = MISSING


@dataclass(frozen=True)
class T_qty__GraveyardSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GraveyardSize"
    player: U_player


@dataclass(frozen=True)
class T_qty__HandSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSize"
    player: U_player


@dataclass(frozen=True)
class T_qty__Intensity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Intensity"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__KickerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "KickerCount"


@dataclass(frozen=True)
class T_qty__LandsPlayedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LandsPlayedThisTurn"
    player: U_player
    from_zones: list[object] = MISSING


@dataclass(frozen=True)
class T_qty__LifeAboveStarting(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeAboveStarting"


@dataclass(frozen=True)
class T_qty__LifeGainedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeGainedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__LifeLostThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeLostThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__LifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeTotal"
    player: U_player


@dataclass(frozen=True)
class T_qty__LoyaltyAbilitiesActivatedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoyaltyAbilitiesActivatedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__ManaSpentToCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSpentToCast"
    metric: U_metric
    scope: str


@dataclass(frozen=True)
class T_qty__ManaSymbolsInManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSymbolsInManaCost"
    color: None | str
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectColorCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectColorCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__ObjectCountBySharedQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCountBySharedQuality"
    aggregate: str
    filter: U_filter
    quality: str


@dataclass(frozen=True)
class T_qty__ObjectCountDistinct(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCountDistinct"
    filter: U_filter
    qualities: list[object]


@dataclass(frozen=True)
class T_qty__ObjectManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectManaValue"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectNameWordCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectNameWordCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectTypelineComponentCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectTypelineComponentCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__PartySize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PartySize"
    player: U_player


@dataclass(frozen=True)
class T_qty__PlayerActionsThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerActionsThisTurn"
    action: str
    player: U_player


@dataclass(frozen=True)
class T_qty__PlayerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCount"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__PlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCounter"
    kind: str
    scope: str


@dataclass(frozen=True)
class T_qty__Power(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Power"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"


@dataclass(frozen=True)
class T_qty__SacrificedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SacrificedThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_qty__Speed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Speed"
    player: U_player


@dataclass(frozen=True)
class T_qty__SpellsCastLastTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastLastTurn"


@dataclass(frozen=True)
class T_qty__SpellsCastThisGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastThisGame"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__SpellsCastThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastThisTurn"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__StartingLifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StartingLifeTotal"


@dataclass(frozen=True)
class T_qty__TargetControllerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetControllerCounter"
    kind: str


@dataclass(frozen=True)
class T_qty__TargetObjectManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetObjectManaValue"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__TargetZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetZoneCardCount"
    zone: str


@dataclass(frozen=True)
class T_qty__TimesCostPaidThisResolution(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TimesCostPaidThisResolution"


@dataclass(frozen=True)
class T_qty__TokensCreatedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokensCreatedThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__Toughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Toughness"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__TrackedSetAggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetAggregate"
    function: str
    property: str
    source: str = MISSING


@dataclass(frozen=True)
class T_qty__TrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetSize"


@dataclass(frozen=True)
class T_qty__TriggeringDiscoverValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringDiscoverValue"


@dataclass(frozen=True)
class T_qty__TurnsTaken(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnsTaken"


@dataclass(frozen=True)
class T_qty__UnspentMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnspentMana"
    color: str


@dataclass(frozen=True)
class T_qty__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    name: str


@dataclass(frozen=True)
class T_qty__VoteCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VoteCount"
    choice_index: int


@dataclass(frozen=True)
class T_qty__ZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCount"
    card_types: list[MirrorVariant]
    scope: str
    zone: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__ZoneChangeAggregateThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeAggregateThisTurn"
    filter: U_filter
    from_: str = field(metadata={"json": "from"})
    function: str
    property: str
    to: str


@dataclass(frozen=True)
class T_qty__ZoneChangeCountThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeCountThisTurn"
    filter: U_filter
    from_: str = field(default=MISSING, metadata={"json": "from"})
    to: str = MISSING


@dataclass(frozen=True)
class T_quantity__BasicLandTypeCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BasicLandTypeCount"
    controller: str


@dataclass(frozen=True)
class T_quantity__CountersOn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOn"
    scope: U_scope
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_quantity__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_quantity__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_quantity__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_quantity__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_quantity__ZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCount"
    card_types: list[MirrorVariant]
    scope: str
    zone: str


@dataclass(frozen=True)
class T_quantity_modification__Half(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Half"


@dataclass(frozen=True)
class T_quantity_modification__Minus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Minus"
    value: int


@dataclass(frozen=True)
class T_quantity_modification__Plus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Plus"
    value: int


@dataclass(frozen=True)
class T_quantity_modification__Prevent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Prevent"


@dataclass(frozen=True)
class T_quantity_modification__Times(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Times"
    factor: int


@dataclass(frozen=True)
class T_recipient__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_recipient__EachController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachController"


@dataclass(frozen=True)
class T_recipient__Neighbor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Neighbor"
    direction: U_direction


@dataclass(frozen=True)
class T_recipient__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_recipient__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_recipient__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_recipient__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_recipient__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_recipient__Shared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Shared"
    data: U_data


@dataclass(frozen=True)
class T_recipient__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_recipient__TriggeringSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSourceController"


@dataclass(frozen=True)
class T_recipient__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_recipient_object_filter__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_recipient_object_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_redirect_object_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_redirect_target__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_redirect_to__ChosenObjectTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenObjectTarget"


@dataclass(frozen=True)
class T_redirect_to__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_redirect_to__SourceObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceObject"


@dataclass(frozen=True)
class T_reference__CostPaidObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObject"


@dataclass(frozen=True)
class T_reference__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_reference__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_reference__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_reference__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_reference__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_reference__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_reference__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_relation__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_relation__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_repeat_for__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_repeat_for__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_repeat_for__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_repeat_for__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_repeat_for__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_repeat_until__ControllerChoice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerChoice"


@dataclass(frozen=True)
class T_repeat_until__UntilStopConditions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UntilStopConditions"
    data: S_data


@dataclass(frozen=True)
class T_repeat_until__WhileCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhileCondition"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_replacement_effect__ChaosEnsues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChaosEnsues"


@dataclass(frozen=True)
class T_replacement_effect__DealDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealDamage"
    amount: U_amount
    target: U_target


@dataclass(frozen=True)
class T_replacement_effect__GainLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainLife"
    amount: U_amount


@dataclass(frozen=True)
class T_replacement_effect__Token(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Token"
    colors: list[U_colors]
    count: U_count
    enters_attacking: bool
    keywords: list[MirrorVariant]
    name: str
    owner: U_owner
    power: U_power
    tapped: bool
    toughness: U_toughness
    types: list[object]


@dataclass(frozen=True)
class T_required_player__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_required_player__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_restriction__CantEnterBattlefieldFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CantEnterBattlefieldFrom"
    expiry: U_expiry
    filter: U_filter
    source: int


@dataclass(frozen=True)
class T_restriction__DamagePreventionDisabled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamagePreventionDisabled"
    expiry: U_expiry
    source: int
    scope: U_scope = MISSING


@dataclass(frozen=True)
class T_restriction__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_restriction__ProhibitActivity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProhibitActivity"
    activity: U_activity
    affected_players: U_affected_players
    expiry: U_expiry
    source: int


@dataclass(frozen=True)
class T_retarget__KeepOriginalTargets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "KeepOriginalTargets"


@dataclass(frozen=True)
class T_retarget__MayChooseNewTargets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MayChooseNewTargets"


@dataclass(frozen=True)
class T_retarget__RetargetEachCopyToIterationMember(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RetargetEachCopyToIterationMember"


@dataclass(frozen=True)
class T_rhs__DivideRounded(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DivideRounded"
    divisor: int
    inner: U_inner
    rounding: str


@dataclass(frozen=True)
class T_rhs__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_rhs__HandSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSize"
    player: U_player


@dataclass(frozen=True)
class T_rhs__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_rhs__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_rhs__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_right__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_right__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_sacrifice_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_scale__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_scaling__PerAffectedAndQuantityRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerAffectedAndQuantityRef"
    data: MirrorVariant


@dataclass(frozen=True)
class T_scaling__PerAffectedCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerAffectedCreature"


@dataclass(frozen=True)
class T_scaling__PerAffectedWithRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerAffectedWithRef"
    data: MirrorVariant


@dataclass(frozen=True)
class T_scaling__PerQuantityRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerQuantityRef"
    data: MirrorVariant


@dataclass(frozen=True)
class T_scope__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_scope__AmassedArmy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AmassedArmy"


@dataclass(frozen=True)
class T_scope__Anaphoric(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Anaphoric"


@dataclass(frozen=True)
class T_scope__CostPaidObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObject"


@dataclass(frozen=True)
class T_scope__Demonstrative(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Demonstrative"


@dataclass(frozen=True)
class T_scope__EventSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventSource"


@dataclass(frozen=True)
class T_scope__EventTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventTarget"


@dataclass(frozen=True)
class T_scope__OtherRevealedCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OtherRevealedCard"


@dataclass(frozen=True)
class T_scope__OwnedSameName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OwnedSameName"


@dataclass(frozen=True)
class T_scope__OwnedSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OwnedSubtype"
    subtype: str


@dataclass(frozen=True)
class T_scope__Recipient(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Recipient"


@dataclass(frozen=True)
class T_scope__Single(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Single"


@dataclass(frozen=True)
class T_scope__Source(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Source"


@dataclass(frozen=True)
class T_scope__SourcesControlledBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourcesControlledBy"
    data: int


@dataclass(frozen=True)
class T_scope__Target(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Target"


@dataclass(frozen=True)
class T_selection__Random(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Random"


@dataclass(frozen=True)
class T_selection_constraint__DistinctQualities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctQualities"
    qualities: list[object]


@dataclass(frozen=True)
class T_selection_constraint__MatchEachFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchEachFilter"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_selection_constraint__TotalManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TotalManaValue"
    comparator: str
    value: int


@dataclass(frozen=True)
class T_solve_condition__Condition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Condition"
    condition: U_condition


@dataclass(frozen=True)
class T_solve_condition__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    comparator: str
    filter: U_filter
    threshold: int


@dataclass(frozen=True)
class T_solve_condition__Text(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Text"
    description: str


@dataclass(frozen=True)
class T_source__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_source__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_source__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_source__ChosenCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenCard"


@dataclass(frozen=True)
class T_source__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_source__Objects(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Objects"
    filter: U_filter


@dataclass(frozen=True)
class T_source__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_source__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_source__ThisObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ThisObject"


@dataclass(frozen=True)
class T_source__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    caused_by: str


@dataclass(frozen=True)
class T_source__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_source__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_source__Zone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Zone"
    scope: str
    zone: str


@dataclass(frozen=True)
class T_source_filter__ChosenDamageSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenDamageSource"


@dataclass(frozen=True)
class T_source_filter__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


@dataclass(frozen=True)
class T_source_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_source_filter__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_source_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_source_pool__SideboardAndFaceUpExile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SideboardAndFaceUpExile"


@dataclass(frozen=True)
class T_source_rider__Destroy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Destroy"


@dataclass(frozen=True)
class T_source_rider__LosesAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LosesAbilities"
    static_def: S_static_def


@dataclass(frozen=True)
class T_sources__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_spell_cast_origin__Equals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equals"
    data: str


@dataclass(frozen=True)
class T_spell_cast_origin__NotEquals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotEquals"
    data: str


@dataclass(frozen=True)
class T_spell_filter__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


@dataclass(frozen=True)
class T_spell_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_spell_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_state__Tap(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tap"


@dataclass(frozen=True)
class T_state__Untap(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Untap"


@dataclass(frozen=True)
class T_step__CombatPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CombatPhase"


@dataclass(frozen=True)
class T_step__Step(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Step"
    data: str


@dataclass(frozen=True)
class T_strive_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_subject__AttackTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackTarget"
    attacked: str
    controller: str


@dataclass(frozen=True)
class T_subject__CommittedChoice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CommittedChoice"
    choice_type: MirrorVariant


@dataclass(frozen=True)
class T_subject__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_subject__LastRevealed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastRevealed"


@dataclass(frozen=True)
class T_subject__Named(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Named"


@dataclass(frozen=True)
class T_subject__Objects(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Objects"
    data: S_data


@dataclass(frozen=True)
class T_subject__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_subject__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_subject__Proposition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Proposition"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_subject__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_subject__Target(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Target"


@dataclass(frozen=True)
class T_subject__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_subject__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_subtype_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_subtype_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_tag__Backup(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Backup"


@dataclass(frozen=True)
class T_tally_mode__PerVote(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerVote"


@dataclass(frozen=True)
class T_tally_mode__TopVotes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TopVotes"
    data: MirrorVariant


@dataclass(frozen=True)
class T_target__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_target__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_target__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_target__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_target__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_target__CostPaidObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObject"


@dataclass(frozen=True)
class T_target__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_target__EventTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventTarget"


@dataclass(frozen=True)
class T_target__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_target__ExiledCardByIndex(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledCardByIndex"
    index: int


@dataclass(frozen=True)
class T_target__GrantingObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantingObject"


@dataclass(frozen=True)
class T_target__LastCreated(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastCreated"


@dataclass(frozen=True)
class T_target__None(TypedMirrorNode):
    _tag: ClassVar[str | None] = "None"


@dataclass(frozen=True)
class T_target__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_target__OriginalController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OriginalController"


@dataclass(frozen=True)
class T_target__Owner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Owner"


@dataclass(frozen=True)
class T_target__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_target__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_target__ParentTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetOwner"


@dataclass(frozen=True)
class T_target__ParentTargetSlot(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetSlot"
    index: int


@dataclass(frozen=True)
class T_target__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_target__PostReplacementDamageTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageTarget"


@dataclass(frozen=True)
class T_target__PostReplacementDamageTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageTargetOwner"


@dataclass(frozen=True)
class T_target__PostReplacementSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementSourceController"


@dataclass(frozen=True)
class T_target__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_target__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_target__SourceChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceChosenPlayer"


@dataclass(frozen=True)
class T_target__StackAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackAbility"
    controller: str = MISSING
    kind: str = MISSING


@dataclass(frozen=True)
class T_target__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_target__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_target__TrackedSetFiltered(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetFiltered"
    filter: U_filter
    id: int
    caused_by: str = MISSING


@dataclass(frozen=True)
class T_target__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_target__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_target__TriggeringSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSourceController"


@dataclass(frozen=True)
class T_target__TriggeringSpellController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellController"


@dataclass(frozen=True)
class T_target__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str | MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_a__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_target_a__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_target_a__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_target_a__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_b__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_target_b__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_target_b__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_chooser__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_target_constraints__DifferentObjectControllers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DifferentObjectControllers"


@dataclass(frozen=True)
class T_target_constraints__SameZoneOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameZoneOwner"
    zone: str


@dataclass(frozen=True)
class T_target_constraints__TotalManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TotalManaValue"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_target_kind__Counters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counters"
    data: MirrorVariant


@dataclass(frozen=True)
class T_target_kind__LifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeTotal"


@dataclass(frozen=True)
class T_target_kind__ManaPool(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaPool"
    data: MirrorVariant


@dataclass(frozen=True)
class T_target_player__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_target_player__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_target_player__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_selection_mode__Random(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Random"


@dataclass(frozen=True)
class T_threshold__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_tie__AllTied(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllTied"


@dataclass(frozen=True)
class T_tie__Breaker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Breaker"
    data: int


@dataclass(frozen=True)
class T_total_power_cap__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_toughness__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_toughness__Quantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Quantity"
    value: U_value


@dataclass(frozen=True)
class T_toughness__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    value: str


@dataclass(frozen=True)
class T_unless_filter__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_unless_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_until__CumulativeThreshold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CumulativeThreshold"
    comparator: str
    property: str
    threshold: U_threshold


@dataclass(frozen=True)
class T_until__NextMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NextMatches"
    filter: U_filter


@dataclass(frozen=True)
class T_valid_card__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_valid_card__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_valid_card__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_valid_card__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_valid_card__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_valid_card__ParentTargetSlot(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetSlot"
    index: int


@dataclass(frozen=True)
class T_valid_card__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_valid_card__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_valid_source__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_valid_source__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_valid_source__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_valid_source__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_valid_source__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_valid_source__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_valid_source__StackAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackAbility"
    controller: str = MISSING
    tag: U_tag = MISSING


@dataclass(frozen=True)
class T_valid_source__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_valid_source__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_valid_subject_player__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_valid_subject_player__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_valid_target__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_valid_target__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_valid_target__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_valid_target__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_valid_target__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_valid_target__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_valid_target__SourceChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceChosenPlayer"


@dataclass(frozen=True)
class T_valid_target__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_valid_target__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_value__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_value__DivideRounded(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DivideRounded"
    divisor: int
    inner: U_inner
    rounding: str


@dataclass(frozen=True)
class T_value__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_value__Max(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Max"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_value__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_value__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_value__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_value__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_visibility__Open(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Open"


@dataclass(frozen=True)
class T_visibility__Secret(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Secret"


@dataclass(frozen=True)
class T_voter_scope__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_voter_scope__ControllerLabels(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerLabels"


@dataclass(frozen=True)
class T_voter_scope__EachOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachOpponent"


# --- discriminated-union aliases (one per tagged content_key) ---

type U_ActivateTagged = T_ActivateTagged__Equip | T_ActivateTagged__PowerUp
type U_Bestow = T_Bestow__Mana | T_Bestow__NonMana
type U_Blitz = T_Blitz__Cost | T_Blitz__SelfManaCost
type U_Bloodthirst = T_Bloodthirst__Fixed | T_Bloodthirst__X
type U_Buyback = T_Buyback__Mana | T_Buyback__NonMana
type U_Cleave = T_Cleave__Cost
type U_CommanderNinjutsu = T_CommanderNinjutsu__Cost
type U_Companion = (
    T_Companion__EvenManaValues
    | T_Companion__MaxPermanentManaValue
    | T_Companion__MinManaValue
    | T_Companion__NoRepeatedManaSymbols
    | T_Companion__OddManaValues
    | T_Companion__PermanentsHaveActivatedAbilities
    | T_Companion__SharedCardType
)
type U_CumulativeUpkeep = (
    T_CumulativeUpkeep__Discard
    | T_CumulativeUpkeep__EffectCost
    | T_CumulativeUpkeep__Exile
    | T_CumulativeUpkeep__Mana
    | T_CumulativeUpkeep__OneOf
    | T_CumulativeUpkeep__PayLife
    | T_CumulativeUpkeep__Sacrifice
)
type U_Cycling = T_Cycling__Mana | T_Cycling__NonMana
type U_Dash = T_Dash__Cost
type U_Disguise = T_Disguise__Cost
type U_Disturb = T_Disturb__Cost
type U_Echo = T_Echo__Mana | T_Echo__NonMana
type U_Embalm = T_Embalm__Mana
type U_Emerge = T_Emerge__Cost
type U_Enchant = (
    T_Enchant__Any
    | T_Enchant__Or
    | T_Enchant__ParentTarget
    | T_Enchant__Player
    | T_Enchant__Typed
)
type U_Encore = T_Encore__Cost | T_Encore__SelfManaCost | T_Encore__SelfManaValue
type U_Entwine = T_Entwine__Cost
type U_EqualTo = T_EqualTo__Fixed | T_EqualTo__Ref
type U_Equip = T_Equip__Cost | T_Equip__SelfManaValue
type U_Escalate = T_Escalate__Discard | T_Escalate__Mana | T_Escalate__TapCreatures
type U_Escape = T_Escape__NonMana
type U_Eternalize = T_Eternalize__Mana | T_Eternalize__NonMana
type U_Evoke = T_Evoke__Mana | T_Evoke__NonMana
type U_Filter = T_Filter__Typed
type U_Firebending = T_Firebending__Fixed | T_Firebending__Ref
type U_Flashback = T_Flashback__Mana | T_Flashback__NonMana
type U_Foretell = T_Foretell__Cost | T_Foretell__SelfManaCostReduced
type U_Fortify = T_Fortify__Cost
type U_Freerunning = T_Freerunning__Cost
type U_Gift = T_Gift__Card | T_Gift__Food | T_Gift__TappedFish | T_Gift__Treasure
type U_Harmonize = T_Harmonize__Cost | T_Harmonize__SelfManaCost
type U_HexproofFrom = (
    T_HexproofFrom__CardType
    | T_HexproofFrom__ChosenColor
    | T_HexproofFrom__Color
    | T_HexproofFrom__Quality
)
type U_KeywordAbilityActivated = (
    T_KeywordAbilityActivated__Boast
    | T_KeywordAbilityActivated__Exhaust
    | T_KeywordAbilityActivated__Outlast
    | T_KeywordAbilityActivated__PowerUp
)
type U_Kicker = T_Kicker__Cost
type U_LevelUp = T_LevelUp__Cost
type U_Madness = T_Madness__Cost
type U_Mayhem = T_Mayhem__Cost | T_Mayhem__SelfManaCost
type U_Megamorph = T_Megamorph__Cost
type U_Miracle = T_Miracle__Cost | T_Miracle__SelfManaCostReduced
type U_Mobilize = T_Mobilize__Fixed | T_Mobilize__Ref
type U_MoreThanMeetsTheEye = T_MoreThanMeetsTheEye__Cost
type U_Morph = T_Morph__Cost
type U_Mutate = T_Mutate__Cost
type U_Ninjutsu = T_Ninjutsu__Cost
type U_Offspring = T_Offspring__Cost
type U_Outlast = T_Outlast__Cost
type U_Overload = T_Overload__Cost
type U_Partner = (
    T_Partner__CharacterSelect
    | T_Partner__ChooseABackground
    | T_Partner__DoctorsCompanion
    | T_Partner__FriendsForever
    | T_Partner__Generic
    | T_Partner__With
)
type U_Plot = T_Plot__Cost
type U_Prowl = T_Prowl__Cost
type U_Quality = T_Quality__Any | T_Quality__Or | T_Quality__Typed
type U_Reconfigure = T_Reconfigure__Cost
type U_Recover = T_Recover__Cost
type U_Replicate = T_Replicate__Cost | T_Replicate__SelfManaCost
type U_Scavenge = T_Scavenge__Cost | T_Scavenge__SelfManaCost
type U_Sneak = T_Sneak__Cost
type U_Specialize = T_Specialize__Cost
type U_Spectacle = T_Spectacle__Cost
type U_Squad = T_Squad__Cost
type U_Surge = T_Surge__Cost
type U_Transfigure = T_Transfigure__Cost
type U_Transmute = T_Transmute__Cost
type U_Unearth = T_Unearth__Cost
type U_Ward = (
    T_Ward__Compound
    | T_Ward__DiscardCard
    | T_Ward__Mana
    | T_Ward__PayLife
    | T_Ward__Sacrifice
    | T_Ward__Waterbend
)
type U_Warp = T_Warp__Cost
type U_WebSlinging = T_WebSlinging__Cost
type U_ability_tag = (
    T_ability_tag__Augment
    | T_ability_tag__Backup
    | T_ability_tag__Boast
    | T_ability_tag__Cycling
    | T_ability_tag__Equip
    | T_ability_tag__Evolve
    | T_ability_tag__Exhaust
    | T_ability_tag__Outlast
    | T_ability_tag__PowerUp
)
type U_action = T_action__exile_from_pool | T_action__put_counter
type U_activation_restrictions = (
    T_activation_restrictions__AsInstant
    | T_activation_restrictions__AsSorcery
    | T_activation_restrictions__BeforeAttackersDeclared
    | T_activation_restrictions__BeforeCombatDamage
    | T_activation_restrictions__ClassLevelIs
    | T_activation_restrictions__CounterThreshold
    | T_activation_restrictions__DuringCombat
    | T_activation_restrictions__DuringYourTurn
    | T_activation_restrictions__DuringYourUpkeep
    | T_activation_restrictions__IsSolved
    | T_activation_restrictions__LevelCounterRange
    | T_activation_restrictions__MatchesCardCastTiming
    | T_activation_restrictions__MaxTimesEachTurn
    | T_activation_restrictions__OnlyOnce
    | T_activation_restrictions__OnlyOnceEachTurn
    | T_activation_restrictions__RequiresCondition
)
type U_activation_source_filter = T_activation_source_filter__Typed
type U_activator = T_activator__Controller
type U_activator_filter = T_activator_filter__All | T_activator_filter__Opponent
type U_activity = (
    T_activity__ActivateAbilities
    | T_activity__Attack
    | T_activity__CastOnlyFromZones
    | T_activity__CastSpells
    | T_activity__ProhibitPlayFromZone
)
type U_additional_cost = (
    T_additional_cost__Choice
    | T_additional_cost__Kicker
    | T_additional_cost__Optional
    | T_additional_cost__Required
)
type U_additional_filter = (
    T_additional_filter__Cmc
    | T_additional_filter__IsChosenCreatureType
    | T_additional_filter__MatchesLastChosenCardPredicate
)
type U_additional_modifications = (
    T_additional_modifications__AddColor
    | T_additional_modifications__AddCounterOnEnter
    | T_additional_modifications__AddKeyword
    | T_additional_modifications__AddStaticMode
    | T_additional_modifications__AddSubtype
    | T_additional_modifications__AddSupertype
    | T_additional_modifications__AddType
    | T_additional_modifications__GrantAbility
    | T_additional_modifications__GrantStaticAbility
    | T_additional_modifications__GrantTrigger
    | T_additional_modifications__RemoveAllSubtypes
    | T_additional_modifications__RemoveManaCost
    | T_additional_modifications__RemoveSupertype
    | T_additional_modifications__RetainPrintedAbilityFromSource
    | T_additional_modifications__RetainPrintedTriggerFromSource
    | T_additional_modifications__SetCardTypes
    | T_additional_modifications__SetColor
    | T_additional_modifications__SetName
    | T_additional_modifications__SetPower
    | T_additional_modifications__SetPowerDynamic
    | T_additional_modifications__SetStartingLoyalty
    | T_additional_modifications__SetToughness
    | T_additional_modifications__SetToughnessDynamic
)
type U_affected = (
    T_affected__And
    | T_affected__Any
    | T_affected__AttachedTo
    | T_affected__Controller
    | T_affected__HasChosenName
    | T_affected__LastCreated
    | T_affected__Or
    | T_affected__OriginalSource
    | T_affected__ParentTarget
    | T_affected__Player
    | T_affected__PlayerWhoChoseLabel
    | T_affected__SelfRef
    | T_affected__SourceOrPaired
    | T_affected__TrackedSet
    | T_affected__TriggeringPlayer
    | T_affected__TriggeringSource
    | T_affected__Typed
)
type U_affected_players = (
    T_affected_players__AllPlayers
    | T_affected_players__DefendingPlayer
    | T_affected_players__OpponentsOfSourceController
    | T_affected_players__ParentObjectTargetController
    | T_affected_players__ParentTargetedPlayer
    | T_affected_players__ScopedPlayer
    | T_affected_players__TargetedPlayer
)
type U_alt_ability_cost = (
    T_alt_ability_cost__Discard
    | T_alt_ability_cost__KeywordCostOfCastSpell
    | T_alt_ability_cost__PayLife
)
type U_alt_cost = T_alt_cost__PayLife
type U_amount = (
    T_amount__ClampMin
    | T_amount__Cost
    | T_amount__Difference
    | T_amount__DivideRounded
    | T_amount__Fixed
    | T_amount__Max
    | T_amount__Multiply
    | T_amount__Offset
    | T_amount__Ref
    | T_amount__Sum
)
type U_amount_dynamic = T_amount_dynamic__Ref
type U_attach_to = T_attach_to__ParentTarget | T_attach_to__Typed
type U_attachment = (
    T_attachment__Any
    | T_attachment__Or
    | T_attachment__ParentTarget
    | T_attachment__ParentTargetSlot
    | T_attachment__SelfRef
    | T_attachment__TriggeringSource
    | T_attachment__Typed
)
type U_attacker_restriction = (
    T_attacker_restriction__ParentTarget | T_attacker_restriction__Typed
)
type U_attr = (
    T_attr__BattlefieldEntriesThisTurn
    | T_attr__CardsDrawnThisTurn
    | T_attr__HandSize
    | T_attr__LifeLostThisTurn
    | T_attr__LifeTotal
    | T_attr__PlayerCounter
)
type U_base = (
    T_base__Discard
    | T_base__Exile
    | T_base__Mana
    | T_base__OneOf
    | T_base__PayLife
    | T_base__Sacrifice
)
type U_blockers = T_blockers__Typed
type U_by = T_by__Typed
type U_candidate_filter = T_candidate_filter__Typed
type U_cap = T_cap__OnlyOnceEachTurn
type U_card_filter = (
    T_card_filter__Any | T_card_filter__None | T_card_filter__Or | T_card_filter__Typed
)
type U_cast_cost_raise = T_cast_cost_raise__Cost
type U_casting_restrictions = (
    T_casting_restrictions__AfterBlockersDeclared
    | T_casting_restrictions__AfterCombat
    | T_casting_restrictions__BeforeAttackersDeclared
    | T_casting_restrictions__BeforeBlockersDeclared
    | T_casting_restrictions__BeforeCombatDamage
    | T_casting_restrictions__DeclareAttackersStep
    | T_casting_restrictions__DeclareBlockersStep
    | T_casting_restrictions__DuringCombat
    | T_casting_restrictions__DuringOpponentsTurn
    | T_casting_restrictions__DuringOpponentsUpkeep
    | T_casting_restrictions__DuringYourEndStep
    | T_casting_restrictions__DuringYourTurn
    | T_casting_restrictions__RequiresCondition
)
type U_choose_filter = T_choose_filter__Typed
type U_chooser = (
    T_chooser__ChosenPlayer
    | T_chooser__Controller
    | T_chooser__DefendingPlayer
    | T_chooser__Opponent
    | T_chooser__ParentObjectTargetController
    | T_chooser__ParentObjectTargetOwner
    | T_chooser__PlayerAttribute
    | T_chooser__TriggeringPlayer
)
type U_colors = T_colors__ChosenColor | T_colors__Fixed
type U_condition = (
    T_condition__ActivatedAbilityIsNonMana
    | T_condition__AdditionalCostPaid
    | T_condition__AdditionalCostPaidInstead
    | T_condition__AlternativeManaCostPaid
    | T_condition__And
    | T_condition__AtNextPhase
    | T_condition__AtNextPhaseForPlayer
    | T_condition__AttackersDeclaredCount
    | T_condition__BattlefieldEntriesThisTurn
    | T_condition__BeenAttackedThisStep
    | T_condition__CastDuringPhase
    | T_condition__CastFromZone
    | T_condition__CastTimingPermission
    | T_condition__CastVariantPaid
    | T_condition__CastVariantPaidInstead
    | T_condition__CastVariantPaidPersistent
    | T_condition__CastViaEscape
    | T_condition__CastViaKicker
    | T_condition__CastingAsVariant
    | T_condition__ChosenLabelIs
    | T_condition__ClassLevelGE
    | T_condition__CompletedADungeon
    | T_condition__CompletedDungeon
    | T_condition__ConditionInstead
    | T_condition__ControllerControlledMatchingAsCast
    | T_condition__ControllerControlsMatching
    | T_condition__ControlsCommander
    | T_condition__ControlsCreatureWithKeyword
    | T_condition__ControlsNone
    | T_condition__ControlsType
    | T_condition__CostPaidObjectMatchesFilter
    | T_condition__CreatureDiedThisTurn
    | T_condition__CreaturesYouControlTotalPowerAtLeast
    | T_condition__DamagedPlayerIsEventSourceOwner
    | T_condition__DayNightIs
    | T_condition__DayNightIsNeither
    | T_condition__DealtDamageBySourceThisTurn
    | T_condition__DealtDamageThisTurnBySource
    | T_condition__DefendingPlayerControls
    | T_condition__DefendingPlayerControlsNone
    | T_condition__DevotionGE
    | T_condition__DuringPlayersTurn
    | T_condition__DuringUntapStep
    | T_condition__DuringYourTurn
    | T_condition__EchoDue
    | T_condition__EffectCausedDiscard
    | T_condition__EffectOutcome
    | T_condition__EnchantedIsFaceDown
    | T_condition__EnteredFromZone
    | T_condition__EventDamageSourceMatchesFilter
    | T_condition__EventObjectMatchesFilter
    | T_condition__EventOutcomeWon
    | T_condition__EventSourceControlledBy
    | T_condition__ExceptFirstDrawInDrawStep
    | T_condition__FirstCombatPhaseOfTurn
    | T_condition__FirstEndStepOfTurn
    | T_condition__FirstSpellThisGame
    | T_condition__FirstTimeObjectTappedThisTurn
    | T_condition__FirstTokenCreationEachTurn
    | T_condition__HadCounters
    | T_condition__HandSizeExact
    | T_condition__HandSizeOneOf
    | T_condition__HasCityBlessing
    | T_condition__HasCounters
    | T_condition__HasMaxSpeed
    | T_condition__IfControlsMatching
    | T_condition__IsInitiative
    | T_condition__IsMonarch
    | T_condition__IsPresent
    | T_condition__IsRenowned
    | T_condition__IsRingBearer
    | T_condition__IsTapped
    | T_condition__IsYourTurn
    | T_condition__ManaColorSpent
    | T_condition__ManaSpentCondition
    | T_condition__MinCoAttackers
    | T_condition__NoMonarch
    | T_condition__Not
    | T_condition__NthResolutionThisTurn
    | T_condition__ObjectsShareQuality
    | T_condition__OnlyExtraTurn
    | T_condition__OnlyIfQuantity
    | T_condition__OpponentDamagedThisTurn
    | T_condition__OpponentPoisonAtLeast
    | T_condition__OpponentSearchedLibraryThisTurn
    | T_condition__Or
    | T_condition__PlacedByAbilitySource
    | T_condition__PlayerCountAtLeast
    | T_condition__PreviousEffectAmount
    | T_condition__QuantityCheck
    | T_condition__QuantityComparison
    | T_condition__QuantityVsEachOpponent
    | T_condition__RecipientAttackingOwnerTarget
    | T_condition__RecipientHasCounters
    | T_condition__RecipientMatchesFilter
    | T_condition__RevealedHasCardType
    | T_condition__SharesColorWithMostCommonColorAmongPermanents
    | T_condition__SolveConditionMet
    | T_condition__SourceAttachedTo
    | T_condition__SourceAttachedToCreature
    | T_condition__SourceAttackedThisTurn
    | T_condition__SourceAttackingAlone
    | T_condition__SourceEnteredThisTurn
    | T_condition__SourceHasCounterAtLeast
    | T_condition__SourceHasDealtDamage
    | T_condition__SourceHasNoCounter
    | T_condition__SourceInZone
    | T_condition__SourceIsAttacking
    | T_condition__SourceIsBlocked
    | T_condition__SourceIsColor
    | T_condition__SourceIsCreature
    | T_condition__SourceIsEnchanted
    | T_condition__SourceIsEquipped
    | T_condition__SourceIsHarnessed
    | T_condition__SourceIsMonstrous
    | T_condition__SourceIsPaired
    | T_condition__SourceIsTapped
    | T_condition__SourceLacksKeyword
    | T_condition__SourceMatchesFilter
    | T_condition__SourcePowerAtLeast
    | T_condition__SourceTappedState
    | T_condition__SourceUntappedAttachedTo
    | T_condition__SpeedGE
    | T_condition__SpellTargetsFilter
    | T_condition__Static
    | T_condition__TargetHasKeywordInstead
    | T_condition__TargetMatchesFilter
    | T_condition__TargetSharesNameWithOtherExiledThisWay
    | T_condition__TokenCoreTypeMatches
    | T_condition__TokenSubtypeMatches
    | T_condition__TributeNotPaid
    | T_condition__TriggeringSpellTargetsFilter
    | T_condition__UnlessControlsCountMatching
    | T_condition__UnlessControlsMatching
    | T_condition__UnlessControlsOtherLeq
    | T_condition__UnlessControlsSubtype
    | T_condition__UnlessMultipleOpponents
    | T_condition__UnlessPay
    | T_condition__UnlessPlayerLifeAtMost
    | T_condition__UnlessQuantity
    | T_condition__UnlessYourTurn
    | T_condition__Unrecognized
    | T_condition__WasCast
    | T_condition__WasPlayed
    | T_condition__WasStartingPlayer
    | T_condition__WasType
    | T_condition__WhenDies
    | T_condition__WhenDiesOrExiled
    | T_condition__WhenEntersBattlefield
    | T_condition__WhenLeavesPlayFiltered
    | T_condition__WhenNextEvent
    | T_condition__WhenYouDo
    | T_condition__WheneverEvent
    | T_condition__YouAttackedThisTurn
    | T_condition__YouAttackedWithAtLeast
    | T_condition__YouCastSpellCountAtLeast
    | T_condition__YouCastSpellThisTurn
    | T_condition__YouControlAnotherColorlessCreature
    | T_condition__YouControlColorPermanentCountAtLeast
    | T_condition__YouControlCoreTypeCountAtLeast
    | T_condition__YouControlCreatureWithPowerAtLeast
    | T_condition__YouControlCreatureWithPt
    | T_condition__YouControlDifferentPowerCreatureCountAtLeast
    | T_condition__YouControlLandSubtypeAny
    | T_condition__YouControlLandsWithSameNameAtLeast
    | T_condition__YouControlLegendaryCreature
    | T_condition__YouControlNamedPlaneswalker
    | T_condition__YouControlNoCreatures
    | T_condition__YouControlSnowPermanentCountAtLeast
    | T_condition__YouControlSubtypeCountAtLeast
    | T_condition__YouCreatedTokenThisTurn
    | T_condition__YouDiscardedCardThisTurn
    | T_condition__YouGainedLifeThisTurn
    | T_condition__YouHadArtifactEnterThisTurn
    | T_condition__YouPlayedLandThisTurn
    | T_condition__YouSacrificedArtifactThisTurn
    | T_condition__ZoneCardCountAtLeast
    | T_condition__ZoneCardTypeCountAtLeast
    | T_condition__ZoneChangeObjectIsTapped
    | T_condition__ZoneChangeObjectMatchesFilter
    | T_condition__ZoneChangedThisWay
    | T_condition__ZoneCoreTypeCardCountAtLeast
    | T_condition__ZoneSubtypeCardCountAtLeast
)
type U_conditional_enter_with_counters = (
    T_conditional_enter_with_counters__Fixed | T_conditional_enter_with_counters__Typed
)
type U_conditions = (
    T_conditions__AdditionalCostPaid
    | T_conditions__And
    | T_conditions__AttackersDeclaredCount
    | T_conditions__CastFromZone
    | T_conditions__CastVariantPaid
    | T_conditions__CastVariantPaidPersistent
    | T_conditions__ChosenLabelIs
    | T_conditions__ClassLevelGE
    | T_conditions__ControlCount
    | T_conditions__ControllerControlsMatching
    | T_conditions__ControlsType
    | T_conditions__CurrentPhaseIs
    | T_conditions__DuringPlayersTurn
    | T_conditions__DuringYourTurn
    | T_conditions__EffectOutcome
    | T_conditions__FirstCombatPhaseOfTurn
    | T_conditions__HasCounters
    | T_conditions__HasObjectTarget
    | T_conditions__IsPresent
    | T_conditions__IsYourTurn
    | T_conditions__ManaColorSpent
    | T_conditions__ManaSpentCondition
    | T_conditions__Not
    | T_conditions__OpponentPoisonAtLeast
    | T_conditions__Or
    | T_conditions__QuantityCheck
    | T_conditions__QuantityComparison
    | T_conditions__ScopedPlayerMatches
    | T_conditions__SourceEnteredThisTurn
    | T_conditions__SourceInZone
    | T_conditions__SourceIsAttacking
    | T_conditions__SourceIsBlocking
    | T_conditions__SourceIsTapped
    | T_conditions__SourceLacksKeyword
    | T_conditions__SourceMatchesFilter
    | T_conditions__SpellCastWithVariantThisTurn
    | T_conditions__TargetHasKeywordInstead
    | T_conditions__TargetMatchesFilter
    | T_conditions__TriggeringSpellMatchesFilter
    | T_conditions__UnlessPay
    | T_conditions__Unrecognized
    | T_conditions__WasCast
    | T_conditions__YouControlSubtypeCountAtLeast
    | T_conditions__ZoneChangeObjectMatchesFilter
    | T_conditions__ZoneChangedThisWay
)
type U_constraint = (
    T_constraint__AtClassLevel
    | T_constraint__DistinctCardTypes
    | T_constraint__EventSourceControlledBy
    | T_constraint__ManaValue
    | T_constraint__MaxTimesPerTurn
    | T_constraint__NthDrawThisTurn
    | T_constraint__NthSpellThisTurn
    | T_constraint__OncePerGame
    | T_constraint__OncePerOpponentPerTurn
    | T_constraint__OncePerTurn
    | T_constraint__OnlyDuringOpponentsTurn
    | T_constraint__OnlyDuringYourMainPhase
    | T_constraint__OnlyDuringYourTurn
)
type U_constraints = (
    T_constraints__ConditionalMaxChoices
    | T_constraints__DifferentTargetPlayers
    | T_constraints__NoRepeatThisGame
    | T_constraints__NoRepeatThisTurn
)
type U_copy_modifications = T_copy_modifications__RemoveSupertype
type U_cost = (
    T_cost__Behold
    | T_cost__Blight
    | T_cost__CollectEvidence
    | T_cost__Composite
    | T_cost__Cost
    | T_cost__Discard
    | T_cost__EffectCost
    | T_cost__Exile
    | T_cost__ExileWithAggregate
    | T_cost__Loyalty
    | T_cost__Mana
    | T_cost__ManaDynamic
    | T_cost__Mill
    | T_cost__NinjutsuFamily
    | T_cost__OneOf
    | T_cost__PayEnergy
    | T_cost__PayLife
    | T_cost__PaySpeed
    | T_cost__PerCounter
    | T_cost__RemoveCounter
    | T_cost__ReturnToHand
    | T_cost__Reveal
    | T_cost__Sacrifice
    | T_cost__SelfManaCost
    | T_cost__Tap
    | T_cost__TapCreatures
    | T_cost__Unimplemented
    | T_cost__Waterbend
)
type U_costs = (
    T_costs__Behold
    | T_costs__Blight
    | T_costs__CollectEvidence
    | T_costs__Composite
    | T_costs__Cost
    | T_costs__Discard
    | T_costs__EffectCost
    | T_costs__Exert
    | T_costs__Exile
    | T_costs__ExileMaterials
    | T_costs__Mana
    | T_costs__Mill
    | T_costs__OneOf
    | T_costs__PayEnergy
    | T_costs__PayLife
    | T_costs__RemoveCounter
    | T_costs__ReturnToHand
    | T_costs__Reveal
    | T_costs__Sacrifice
    | T_costs__Tap
    | T_costs__TapCreatures
    | T_costs__Unattach
    | T_costs__UnattachFrom
    | T_costs__Unimplemented
    | T_costs__Untap
    | T_costs__Waterbend
)
type U_count = (
    T_count__AtLeast
    | T_count__ClampMin
    | T_count__Difference
    | T_count__DivideRounded
    | T_count__Exactly
    | T_count__Fixed
    | T_count__Max
    | T_count__Multiply
    | T_count__Offset
    | T_count__Power
    | T_count__Ref
    | T_count__Sum
    | T_count__UpTo
)
type U_counter_match = T_counter_match__OfType
type U_counter_type = T_counter_type__Any | T_counter_type__OfType
type U_countered_spell_zone = (
    T_countered_spell_zone__Hand | T_countered_spell_zone__Library
)
type U_counters = T_counters__Any | T_counters__OfType
type U_damage_modification = (
    T_damage_modification__Double
    | T_damage_modification__LifeFloor
    | T_damage_modification__Minus
    | T_damage_modification__Plus
    | T_damage_modification__SetToSourcePower
    | T_damage_modification__Triple
)
type U_damage_source_filter = (
    T_damage_source_filter__And
    | T_damage_source_filter__AttachedTo
    | T_damage_source_filter__ChosenDamageSource
    | T_damage_source_filter__Or
    | T_damage_source_filter__ParentTarget
    | T_damage_source_filter__SelfRef
    | T_damage_source_filter__StackSpell
    | T_damage_source_filter__Typed
)
type U_data = (
    T_data__Any
    | T_data__Behold
    | T_data__Blight
    | T_data__Composite
    | T_data__Cost
    | T_data__Discard
    | T_data__DiscardCard
    | T_data__EffectCost
    | T_data__Exile
    | T_data__Mana
    | T_data__OneOf
    | T_data__ParentTarget
    | T_data__PayLife
    | T_data__ReturnToHand
    | T_data__Reveal
    | T_data__Sacrifice
    | T_data__SelfManaCost
    | T_data__TapCreatures
    | T_data__TriggeringSource
    | T_data__Unimplemented
    | T_data__Waterbend
)
type U_deck_copy_limit = T_deck_copy_limit__Unlimited | T_deck_copy_limit__UpTo
type U_depth = T_depth__Ref
type U_destination_constraint = T_destination_constraint__NotEquals
type U_direction = T_direction__Decrease | T_direction__Left | T_direction__Right
type U_distribute = (
    T_distribute__Counters | T_distribute__Damage | T_distribute__EvenSplitDamage
)
type U_duplicate_of = (
    T_duplicate_of__And
    | T_duplicate_of__ParentTarget
    | T_duplicate_of__StackSpell
    | T_duplicate_of__Typed
)
type U_dynamic_count = (
    T_dynamic_count__Aggregate
    | T_dynamic_count__AttackedThisTurn
    | T_dynamic_count__BasicLandTypeCount
    | T_dynamic_count__CardsDiscardedThisTurn
    | T_dynamic_count__CardsDrawnThisTurn
    | T_dynamic_count__CountersOn
    | T_dynamic_count__DamageDealtThisTurn
    | T_dynamic_count__Devotion
    | T_dynamic_count__DistinctCardTypes
    | T_dynamic_count__DistinctColorsAmongPermanents
    | T_dynamic_count__FilteredTrackedSetSize
    | T_dynamic_count__LifeGainedThisTurn
    | T_dynamic_count__LifeLostThisTurn
    | T_dynamic_count__ObjectCount
    | T_dynamic_count__ObjectCountDistinct
    | T_dynamic_count__PartySize
    | T_dynamic_count__PlayerCount
    | T_dynamic_count__PlayerCounter
    | T_dynamic_count__Power
    | T_dynamic_count__PreviousEffectAmount
    | T_dynamic_count__Speed
    | T_dynamic_count__SpellsCastThisTurn
    | T_dynamic_count__TrackedSetSize
    | T_dynamic_count__ZoneCardCount
    | T_dynamic_count__ZoneChangeCountThisTurn
)
type U_dynamic_max_choices = T_dynamic_max_choices__Ref
type U_effect = (
    T_effect__Adapt
    | T_effect__AddPendingETBCounters
    | T_effect__AddPendingEntersModifications
    | T_effect__AddRestriction
    | T_effect__AddTargetReplacement
    | T_effect__AdditionalPhase
    | T_effect__Amass
    | T_effect__Animate
    | T_effect__ApplyPerpetual
    | T_effect__AssembleContraptions
    | T_effect__Attach
    | T_effect__BecomeBlocked
    | T_effect__BecomeCopy
    | T_effect__BecomeMonarch
    | T_effect__BecomePrepared
    | T_effect__BecomeSaddled
    | T_effect__BecomeUnprepared
    | T_effect__Behold
    | T_effect__BlightEffect
    | T_effect__Bolster
    | T_effect__Bounce
    | T_effect__BounceAll
    | T_effect__CastCopyOfCard
    | T_effect__CastFromZone
    | T_effect__ChangeSpeed
    | T_effect__ChangeTargets
    | T_effect__ChangeZone
    | T_effect__ChangeZoneAll
    | T_effect__ChaosEnsues
    | T_effect__Choose
    | T_effect__ChooseAndSacrificeRest
    | T_effect__ChooseAugmentAndCombineWithHost
    | T_effect__ChooseCounterAdjustment
    | T_effect__ChooseCounterKind
    | T_effect__ChooseDrawnThisTurnPayOrTopdeck
    | T_effect__ChooseFromZone
    | T_effect__ChooseObjectsIntoTrackedSet
    | T_effect__ChooseOneOf
    | T_effect__Clash
    | T_effect__Cloak
    | T_effect__CollectEvidence
    | T_effect__CombineHost
    | T_effect__Conjure
    | T_effect__Connive
    | T_effect__ControlNextTurn
    | T_effect__CopySpell
    | T_effect__CopyTokenBlockingAttacker
    | T_effect__CopyTokenOf
    | T_effect__Counter
    | T_effect__CounterAll
    | T_effect__CreateDamageReplacement
    | T_effect__CreateDelayedTrigger
    | T_effect__CreateDrawReplacement
    | T_effect__CreateEmblem
    | T_effect__CreatePlaneswalkReplacement
    | T_effect__DamageAll
    | T_effect__DamageEachPlayer
    | T_effect__DealDamage
    | T_effect__Destroy
    | T_effect__DestroyAll
    | T_effect__Detain
    | T_effect__Dig
    | T_effect__Discard
    | T_effect__DiscardCard
    | T_effect__Discover
    | T_effect__Double
    | T_effect__DoublePT
    | T_effect__DoublePTAll
    | T_effect__DraftFromSpellbook
    | T_effect__Draw
    | T_effect__EachDealsDamageEqualToPower
    | T_effect__EachPlayerCopyChosen
    | T_effect__EachSourceDealsDamage
    | T_effect__Encore
    | T_effect__EndCombatPhase
    | T_effect__EndTheTurn
    | T_effect__Endure
    | T_effect__ExchangeControl
    | T_effect__ExchangeLifeTotals
    | T_effect__ExchangeLifeWithStat
    | T_effect__ExileFromTopUntil
    | T_effect__ExileHaunting
    | T_effect__ExileResolvingSpellInsteadOfGraveyard
    | T_effect__ExileTop
    | T_effect__Explore
    | T_effect__ExploreAll
    | T_effect__ExtraTurn
    | T_effect__Fight
    | T_effect__FlipCoin
    | T_effect__FlipCoinUntilLose
    | T_effect__FlipCoins
    | T_effect__ForEachCategory
    | T_effect__Forage
    | T_effect__ForceAttack
    | T_effect__ForceBlock
    | T_effect__FreeCastFromZones
    | T_effect__GainActivatedAbilitiesOfTarget
    | T_effect__GainControl
    | T_effect__GainControlAll
    | T_effect__GainEnergy
    | T_effect__GainLife
    | T_effect__GenericEffect
    | T_effect__GiftDelivery
    | T_effect__GiveControl
    | T_effect__GivePlayerCounter
    | T_effect__Goad
    | T_effect__GoadAll
    | T_effect__GrantCastingPermission
    | T_effect__GrantExtraLoyaltyActivations
    | T_effect__GrantNextSpellAbility
    | T_effect__Harness
    | T_effect__Heist
    | T_effect__HideawayConceal
    | T_effect__Incubate
    | T_effect__Intensify
    | T_effect__Investigate
    | T_effect__Learn
    | T_effect__LoseAllPlayerCounters
    | T_effect__LoseLife
    | T_effect__LoseTheGame
    | T_effect__MadnessCast
    | T_effect__Mana
    | T_effect__Manifest
    | T_effect__ManifestDread
    | T_effect__Meld
    | T_effect__Mill
    | T_effect__Monstrosity
    | T_effect__MoveCounters
    | T_effect__MultiplyCounter
    | T_effect__Myriad
    | T_effect__NoOp
    | T_effect__OpenAttractions
    | T_effect__OpponentGuess
    | T_effect__PairWith
    | T_effect__PayCost
    | T_effect__PhaseIn
    | T_effect__PhaseOut
    | T_effect__Planeswalk
    | T_effect__Populate
    | T_effect__PreventDamage
    | T_effect__Proliferate
    | T_effect__ProliferateTarget
    | T_effect__Pump
    | T_effect__PumpAll
    | T_effect__PutAtLibraryPosition
    | T_effect__PutChosenCounter
    | T_effect__PutCounter
    | T_effect__PutCounterAll
    | T_effect__PutOnTopOrBottom
    | T_effect__PutSticker
    | T_effect__ReassembleContraption
    | T_effect__RedistributeLifeTotals
    | T_effect__ReduceNextSpellCost
    | T_effect__Regenerate
    | T_effect__RegisterBending
    | T_effect__RememberCard
    | T_effect__RemoveAllDamage
    | T_effect__RemoveCounter
    | T_effect__RemoveFromCombat
    | T_effect__Renown
    | T_effect__ReturnAsAura
    | T_effect__Reveal
    | T_effect__RevealFromHand
    | T_effect__RevealHand
    | T_effect__RevealTop
    | T_effect__RevealUntil
    | T_effect__ReverseTurnOrder
    | T_effect__RingTemptsYou
    | T_effect__RollDie
    | T_effect__RollToVisitAttractions
    | T_effect__RuntimeHandled
    | T_effect__Sacrifice
    | T_effect__Scry
    | T_effect__SearchLibrary
    | T_effect__SearchOutsideGame
    | T_effect__Seek
    | T_effect__SeparateIntoPiles
    | T_effect__SetClassLevel
    | T_effect__SetDayNight
    | T_effect__SetLifeTotal
    | T_effect__SetRoomDoorLock
    | T_effect__SetTapState
    | T_effect__Shuffle
    | T_effect__SkipNextStep
    | T_effect__SkipNextTurn
    | T_effect__SolveCase
    | T_effect__Specialize
    | T_effect__StartYourEngines
    | T_effect__Surveil
    | T_effect__Suspect
    | T_effect__SwapChosenLabels
    | T_effect__SwitchPT
    | T_effect__TakeTheInitiative
    | T_effect__TargetOnly
    | T_effect__TimeTravel
    | T_effect__Token
    | T_effect__Transform
    | T_effect__Tribute
    | T_effect__TurnFaceDown
    | T_effect__TurnFaceUp
    | T_effect__UnattachAll
    | T_effect__Unimplemented
    | T_effect__Unsuspect
    | T_effect__VentureIntoDungeon
    | T_effect__Vote
    | T_effect__WinTheGame
)
type U_enchant_filter = T_enchant_filter__Typed
type U_enter_with_counters = (
    T_enter_with_counters__ClampMin
    | T_enter_with_counters__Fixed
    | T_enter_with_counters__Offset
    | T_enter_with_counters__Ref
)
type U_enters_modified_if = T_enters_modified_if__Typed
type U_entwine_cost = T_entwine_cost__Cost
type U_excess = T_excess__TargetController
type U_exclude = (
    T_exclude__CreatureTypes
    | T_exclude__ParentObjectTargetController
    | T_exclude__TriggeringPlayer
)
type U_expiry = T_expiry__EndOfTurn
type U_exponent = T_exponent__Ref
type U_exprs = T_exprs__Fixed | T_exprs__Multiply | T_exprs__Ref
type U_extra_source = T_extra_source__Typed
type U_filter = (
    T_filter__All
    | T_filter__And
    | T_filter__Any
    | T_filter__Controller
    | T_filter__ControlsCount
    | T_filter__ExiledBySource
    | T_filter__GrantingObject
    | T_filter__HasChosenName
    | T_filter__HasLostTheGame
    | T_filter__Named
    | T_filter__Not
    | T_filter__Opponent
    | T_filter__OpponentAttacked
    | T_filter__OpponentDealtDamage
    | T_filter__OpponentGainedLife
    | T_filter__OpponentLostLife
    | T_filter__OpponentOfTriggeringPlayerNotAttacked
    | T_filter__Or
    | T_filter__ParentTarget
    | T_filter__PerformedActionThisWay
    | T_filter__Player
    | T_filter__PlayerAttribute
    | T_filter__SelfRef
    | T_filter__Typed
)
type U_filters = (
    T_filters__And
    | T_filters__Any
    | T_filters__AttachedTo
    | T_filters__Controller
    | T_filters__ExiledBySource
    | T_filters__HasChosenName
    | T_filters__LastCreated
    | T_filters__Not
    | T_filters__Or
    | T_filters__ParentTarget
    | T_filters__ParentTargetSlot
    | T_filters__Player
    | T_filters__SelfRef
    | T_filters__StackAbility
    | T_filters__StackSpell
    | T_filters__TrackedSet
    | T_filters__TriggeringPlayer
    | T_filters__TriggeringSource
    | T_filters__Typed
)
type U_flipper = T_flipper__Any | T_flipper__TriggeringPlayer
type U_forced_to = T_forced_to__ParentTarget | T_forced_to__SelfRef
type U_grantee = T_grantee__ObjectOwner | T_grantee__ParentTargetController
type U_grants = T_grants__GrantAbility | T_grants__RemoveAllAbilities
type U_host = T_host__TriggeringSource | T_host__Typed
type U_inner = (
    T_inner__And
    | T_inner__CastDuringPhase
    | T_inner__CastFromZone
    | T_inner__CastVariantPaid
    | T_inner__ClampMin
    | T_inner__ControllerControlledMatchingAsCast
    | T_inner__CostPaidObjectMatchesFilter
    | T_inner__DayNightIs
    | T_inner__EventOutcomeWon
    | T_inner__Fixed
    | T_inner__HasCityBlessing
    | T_inner__IsMonarch
    | T_inner__ManaColorSpent
    | T_inner__Multiply
    | T_inner__Not
    | T_inner__NthResolutionThisTurn
    | T_inner__Offset
    | T_inner__Or
    | T_inner__QuantityCheck
    | T_inner__Ref
    | T_inner__RevealedHasCardType
    | T_inner__SourceMatchesFilter
    | T_inner__Sum
    | T_inner__TargetMatchesFilter
    | T_inner__ZoneChangeObjectMatchesFilter
    | T_inner__ZoneChangedThisWay
)
type U_invalidation = T_invalidation__UntilNextGrantFromSameSource
type U_iteration_kind_binding = T_iteration_kind_binding__RebindToIteratedKind
type U_keep_count_expr = T_keep_count_expr__Ref
type U_kind = T_kind__Card | T_kind__Food | T_kind__TappedFish | T_kind__Treasure
type U_land_filter = T_land_filter__Typed
type U_left = T_left__Ref
type U_lhs = T_lhs__Difference | T_lhs__HandSize | T_lhs__ObjectCount | T_lhs__Ref
type U_library_position = T_library_position__Bottom | T_library_position__Top
type U_life_payment = T_life_payment__Fixed
type U_mana_cost = T_mana_cost__Cost | T_mana_cost__NoCost
type U_mana_modification = (
    T_mana_modification__Multiply | T_mana_modification__ReplaceWith
)
type U_mana_reduction = T_mana_reduction__Cost
type U_mana_replacement_scope = T_mana_replacement_scope__TappedForMana
type U_mana_value_limit = T_mana_value_limit__Fixed | T_mana_value_limit__Ref
type U_matched_disposition = (
    T_matched_disposition__ChooseAnyNumber | T_matched_disposition__RevealOnly
)
type U_materials = T_materials__Or
type U_max = T_max__Fixed | T_max__Offset | T_max__Ref
type U_max_ticket_cost = T_max_ticket_cost__Ref
type U_metric = T_metric__DistinctColors | T_metric__FromSource | T_metric__Total
type U_min = T_min__Ref
type U_mode = T_mode__Mandatory | T_mode__MayCost | T_mode__Optional
type U_mode_costs = T_mode_costs__Cost
type U_modification = T_modification__Double
type U_modifications = (
    T_modifications__AddAllBasicLandTypes
    | T_modifications__AddAllCreatureTypes
    | T_modifications__AddAllLandTypes
    | T_modifications__AddChosenColor
    | T_modifications__AddChosenKeyword
    | T_modifications__AddChosenSubtype
    | T_modifications__AddColor
    | T_modifications__AddDynamicKeyword
    | T_modifications__AddDynamicPower
    | T_modifications__AddDynamicToughness
    | T_modifications__AddKeyword
    | T_modifications__AddPower
    | T_modifications__AddStaticMode
    | T_modifications__AddSubtype
    | T_modifications__AddSupertype
    | T_modifications__AddToughness
    | T_modifications__AddType
    | T_modifications__AssignDamageAsThoughUnblocked
    | T_modifications__AssignDamageFromToughness
    | T_modifications__AssignNoCombatDamage
    | T_modifications__ChangeController
    | T_modifications__GrantAbility
    | T_modifications__GrantAllActivatedAbilitiesOf
    | T_modifications__GrantAllTriggeredAbilitiesOf
    | T_modifications__GrantStaticAbility
    | T_modifications__GrantTrigger
    | T_modifications__RemoveAllAbilities
    | T_modifications__RemoveAllSubtypes
    | T_modifications__RemoveKeyword
    | T_modifications__RemoveSupertype
    | T_modifications__RemoveType
    | T_modifications__SetBasicLandType
    | T_modifications__SetCardTypes
    | T_modifications__SetChosenBasicLandType
    | T_modifications__SetChosenName
    | T_modifications__SetColor
    | T_modifications__SetDynamicPower
    | T_modifications__SetDynamicToughness
    | T_modifications__SetName
    | T_modifications__SetPower
    | T_modifications__SetPowerDynamic
    | T_modifications__SetToughness
    | T_modifications__SetToughnessDynamic
)
type U_modifier = (
    T_modifier__Add
    | T_modifier__CantBeCountered
    | T_modifier__CastAsThoughFlash
    | T_modifier__HasKeyword
    | T_modifier__Subtract
    | T_modifier__WithoutPayingManaCost
)
type U_object_filter = T_object_filter__Any | T_object_filter__Typed
type U_object_source = T_object_source__ParentTarget | T_object_source__TrackedSet
type U_once_per_turn = T_once_per_turn__OnlyOnceEachTurn
type U_only_tag = T_only_tag__PowerUp
type U_op = T_op__LockOrUnlock | T_op__Unlock
type U_origin = T_origin__Equals | T_origin__NotEquals | T_origin__OneOf
type U_origin_constraint = T_origin_constraint__Equals
type U_owner = (
    T_owner__Any
    | T_owner__Controller
    | T_owner__OriginalController
    | T_owner__ParentTarget
    | T_owner__ParentTargetController
    | T_owner__ParentTargetOwner
    | T_owner__Player
    | T_owner__ScopedPlayer
    | T_owner__TriggeringPlayer
    | T_owner__TriggeringSource
    | T_owner__Typed
)
type U_parity = T_parity__LastNamedChoice
type U_parse_warnings = (
    T_parse_warnings__IgnoredRemainder
    | T_parse_warnings__SwallowedClause
    | T_parse_warnings__TargetFallback
)
type U_partition_subject = (
    T_partition_subject__AnOpponent | T_partition_subject__EachOpponent
)
type U_payer = (
    T_payer__AllPlayers
    | T_payer__Controller
    | T_payer__ParentTargetController
    | T_payer__Player
    | T_payer__ScopedPlayer
    | T_payer__TriggeringPlayer
    | T_payer__TriggeringSpellController
    | T_payer__Typed
)
type U_per_player_condition = (
    T_per_player_condition__YouAttackedSourceControllerThisTurn
    | T_per_player_condition__YouAttackedThisTurn
    | T_per_player_condition__YouCastSpellThisTurn
)
type U_permission = (
    T_permission__ExileWithAltCost
    | T_permission__ExileWithEnergyCost
    | T_permission__Foretold
    | T_permission__PlayFromExile
    | T_permission__Plotted
)
type U_pile_source = (
    T_pile_source__Battlefield
    | T_pile_source__ExiledThisWay
    | T_pile_source__RevealedFromLibraryTop
)
type U_player = (
    T_player__AllPlayers
    | T_player__Any
    | T_player__AnyTurn
    | T_player__Controller
    | T_player__DefendingPlayer
    | T_player__Opponent
    | T_player__OpponentDealtDamage
    | T_player__ParentObjectTargetController
    | T_player__ParentTarget
    | T_player__ParentTargetController
    | T_player__ParentTargetOwner
    | T_player__Player
    | T_player__PostReplacementDamageTarget
    | T_player__RecipientController
    | T_player__ScopedPlayer
    | T_player__SourceChosenPlayer
    | T_player__Target
    | T_player__TriggeringPlayer
    | T_player__Typed
)
type U_player_a = T_player_a__Controller | T_player_a__Player
type U_player_b = T_player_b__Player | T_player_b__Typed
type U_player_filter = (
    T_player_filter__All
    | T_player_filter__Opponent
    | T_player_filter__OpponentOtherThanTriggering
)
type U_player_scope = (
    T_player_scope__All
    | T_player_scope__AllExcept
    | T_player_scope__ChosenPlayer
    | T_player_scope__ControlsCount
    | T_player_scope__DefendingPlayer
    | T_player_scope__HighestSpeed
    | T_player_scope__Opponent
    | T_player_scope__OpponentAttacked
    | T_player_scope__OpponentAttackingEnchantedPlayer
    | T_player_scope__OpponentOfTriggeringPlayer
    | T_player_scope__OwnersOfCardsExiledBySource
    | T_player_scope__ParentObjectTargetController
    | T_player_scope__PlayerAttribute
    | T_player_scope__TriggeringPlayer
    | T_player_scope__VotedFor
)
type U_position = (
    T_position__BeneathTop
    | T_position__Bottom
    | T_position__NthFromTop
    | T_position__Top
)
type U_power = T_power__Fixed | T_power__Quantity | T_power__Variable
type U_produced = (
    T_produced__AnyCombination
    | T_produced__AnyCombinationOfObjectColors
    | T_produced__AnyInCommandersColorIdentity
    | T_produced__AnyOneColor
    | T_produced__AnyOneColorAmongPermanents
    | T_produced__AnyTypeProduceableBy
    | T_produced__ChoiceAmongCombinations
    | T_produced__ChoiceAmongExiledColors
    | T_produced__ChosenColor
    | T_produced__Colorless
    | T_produced__DistinctColorsAmongPermanents
    | T_produced__Fixed
    | T_produced__Mixed
    | T_produced__OpponentLandColors
    | T_produced__TriggerEventManaType
)
type U_prop = (
    T_prop__AttackedThisTurn
    | T_prop__EnteredThisTurn
    | T_prop__InTrackedSet
    | T_prop__SameName
    | T_prop__SharesQuality
    | T_prop__WasPlayed
)
type U_properties = (
    T_properties__Another
    | T_properties__AnyOf
    | T_properties__AttachedToRecipient
    | T_properties__AttachedToSource
    | T_properties__AttackedOrBlockedThisTurn
    | T_properties__AttackedThisTurn
    | T_properties__Attacking
    | T_properties__AttackingAlone
    | T_properties__BlockedThisTurn
    | T_properties__Blocking
    | T_properties__BlockingSource
    | T_properties__CanEnchant
    | T_properties__Cmc
    | T_properties__ColorCount
    | T_properties__CombatRelation
    | T_properties__ControlledContinuouslySinceTurnBegan
    | T_properties__ControllerChoseLabel
    | T_properties__ControllerMatches
    | T_properties__ConvokedSource
    | T_properties__CouldBeTargetedByTriggeringSpell
    | T_properties__Counters
    | T_properties__CountersPutOnThisTurn
    | T_properties__DifferentNameFrom
    | T_properties__DistinctFrom
    | T_properties__EnchantedBy
    | T_properties__EnteredThisTurn
    | T_properties__EquippedBy
    | T_properties__FaceDown
    | T_properties__Foretold
    | T_properties__HasAnyAttachmentOf
    | T_properties__HasAttachment
    | T_properties__HasColor
    | T_properties__HasKeywordKind
    | T_properties__HasManaAbility
    | T_properties__HasNoAbilities
    | T_properties__HasSingleTarget
    | T_properties__HasSupertype
    | T_properties__HasXInActivationCost
    | T_properties__HasXInManaCost
    | T_properties__Historic
    | T_properties__InAnyZone
    | T_properties__InZone
    | T_properties__IsChosenCardType
    | T_properties__IsChosenColor
    | T_properties__IsChosenCreatureType
    | T_properties__IsCommander
    | T_properties__IsSaddled
    | T_properties__ManaCostIn
    | T_properties__ManaSymbolCount
    | T_properties__ManaValueParity
    | T_properties__MatchesLastChosenCardPredicate
    | T_properties__Modal
    | T_properties__Modified
    | T_properties__MostPrevalentCreatureTypeIn
    | T_properties__NameMatchesAnyPermanent
    | T_properties__Named
    | T_properties__NonToken
    | T_properties__Not
    | T_properties__NotColor
    | T_properties__NotHistoric
    | T_properties__NotSupertype
    | T_properties__OtherThanTriggerObject
    | T_properties__Owned
    | T_properties__PowerExceedsBase
    | T_properties__PowerGTSource
    | T_properties__ProtectorMatches
    | T_properties__PtComparison
    | T_properties__Renowned
    | T_properties__SaddledSource
    | T_properties__SameName
    | T_properties__SameNameAsParentTarget
    | T_properties__SharesQuality
    | T_properties__Suspected
    | T_properties__Tapped
    | T_properties__Targets
    | T_properties__TargetsOnly
    | T_properties__Token
    | T_properties__ToughnessGTPower
    | T_properties__Transformed
    | T_properties__Unblocked
    | T_properties__Unpaired
    | T_properties__Untapped
    | T_properties__WasDealtDamageThisTurn
    | T_properties__WasKicked
    | T_properties__WasPlayed
    | T_properties__WithKeyword
    | T_properties__WithoutKeyword
    | T_properties__WithoutKeywordKind
    | T_properties__ZoneChangedThisTurn
)
type U_props = (
    T_props__AttackingAlone
    | T_props__BlockingAlone
    | T_props__Cmc
    | T_props__HasColor
    | T_props__PtComparison
)
type U_qty = (
    T_qty__AdditionalCostPaymentCountFor
    | T_qty__Aggregate
    | T_qty__AttachmentsOnLeavingObject
    | T_qty__AttackedThisTurn
    | T_qty__BasicLandTypeCount
    | T_qty__BattlefieldEntriesThisTurn
    | T_qty__BendTypesThisTurn
    | T_qty__CardsDiscardedThisTurn
    | T_qty__CardsDrawnThisTurn
    | T_qty__CardsExiledBySource
    | T_qty__ChosenNumber
    | T_qty__ColorsInCommandersColorIdentity
    | T_qty__CommanderCastFromCommandZoneCount
    | T_qty__CommanderManaValue
    | T_qty__ControlledByEachPlayer
    | T_qty__ConvokedCreatureCount
    | T_qty__CostXPaid
    | T_qty__CounterAddedThisTurn
    | T_qty__CountersOn
    | T_qty__CountersOnObjects
    | T_qty__CrimesCommittedThisTurn
    | T_qty__DamageDealtThisTurn
    | T_qty__DescendedThisTurn
    | T_qty__Devotion
    | T_qty__DistinctCardTypes
    | T_qty__DistinctColorsAmongPermanents
    | T_qty__DistinctCounterKindsAmong
    | T_qty__DistinctSubtypes
    | T_qty__EnteredThisTurn
    | T_qty__EventContextAmount
    | T_qty__ExiledCardPower
    | T_qty__ExiledFromHandThisResolution
    | T_qty__FilteredTrackedSetSize
    | T_qty__GraveyardSize
    | T_qty__HandSize
    | T_qty__Intensity
    | T_qty__KickerCount
    | T_qty__LandsPlayedThisTurn
    | T_qty__LifeAboveStarting
    | T_qty__LifeGainedThisTurn
    | T_qty__LifeLostThisTurn
    | T_qty__LifeTotal
    | T_qty__LoyaltyAbilitiesActivatedThisTurn
    | T_qty__ManaSpentToCast
    | T_qty__ManaSymbolsInManaCost
    | T_qty__ObjectColorCount
    | T_qty__ObjectCount
    | T_qty__ObjectCountBySharedQuality
    | T_qty__ObjectCountDistinct
    | T_qty__ObjectManaValue
    | T_qty__ObjectNameWordCount
    | T_qty__ObjectTypelineComponentCount
    | T_qty__PartySize
    | T_qty__PlayerActionsThisTurn
    | T_qty__PlayerCount
    | T_qty__PlayerCounter
    | T_qty__Power
    | T_qty__PreviousEffectAmount
    | T_qty__SacrificedThisTurn
    | T_qty__SelfManaValue
    | T_qty__Speed
    | T_qty__SpellsCastLastTurn
    | T_qty__SpellsCastThisGame
    | T_qty__SpellsCastThisTurn
    | T_qty__StartingLifeTotal
    | T_qty__TargetControllerCounter
    | T_qty__TargetObjectManaValue
    | T_qty__TargetZoneCardCount
    | T_qty__TimesCostPaidThisResolution
    | T_qty__TokensCreatedThisTurn
    | T_qty__Toughness
    | T_qty__TrackedSetAggregate
    | T_qty__TrackedSetSize
    | T_qty__TriggeringDiscoverValue
    | T_qty__TurnsTaken
    | T_qty__UnspentMana
    | T_qty__Variable
    | T_qty__VoteCount
    | T_qty__ZoneCardCount
    | T_qty__ZoneChangeAggregateThisTurn
    | T_qty__ZoneChangeCountThisTurn
)
type U_quantity = (
    T_quantity__BasicLandTypeCount
    | T_quantity__CountersOn
    | T_quantity__Multiply
    | T_quantity__ObjectCount
    | T_quantity__Ref
    | T_quantity__Sum
    | T_quantity__ZoneCardCount
)
type U_quantity_modification = (
    T_quantity_modification__Half
    | T_quantity_modification__Minus
    | T_quantity_modification__Plus
    | T_quantity_modification__Prevent
    | T_quantity_modification__Times
)
type U_recipient = (
    T_recipient__Any
    | T_recipient__EachController
    | T_recipient__Neighbor
    | T_recipient__ParentTarget
    | T_recipient__ParentTargetController
    | T_recipient__Player
    | T_recipient__ScopedPlayer
    | T_recipient__SelfRef
    | T_recipient__Shared
    | T_recipient__TriggeringPlayer
    | T_recipient__TriggeringSourceController
    | T_recipient__Typed
)
type U_recipient_object_filter = (
    T_recipient_object_filter__SelfRef | T_recipient_object_filter__Typed
)
type U_redirect_object_filter = T_redirect_object_filter__Typed
type U_redirect_target = T_redirect_target__SelfRef
type U_redirect_to = (
    T_redirect_to__ChosenObjectTarget
    | T_redirect_to__Controller
    | T_redirect_to__SourceObject
)
type U_reference = (
    T_reference__CostPaidObject
    | T_reference__ExiledBySource
    | T_reference__Or
    | T_reference__ParentTarget
    | T_reference__SelfRef
    | T_reference__TrackedSet
    | T_reference__TriggeringSource
    | T_reference__Typed
)
type U_relation = T_relation__All | T_relation__Opponent
type U_repeat_for = (
    T_repeat_for__Difference
    | T_repeat_for__Fixed
    | T_repeat_for__Multiply
    | T_repeat_for__Offset
    | T_repeat_for__Ref
)
type U_repeat_until = (
    T_repeat_until__ControllerChoice
    | T_repeat_until__UntilStopConditions
    | T_repeat_until__WhileCondition
)
type U_replacement_effect = (
    T_replacement_effect__ChaosEnsues
    | T_replacement_effect__DealDamage
    | T_replacement_effect__GainLife
    | T_replacement_effect__Token
)
type U_required_player = T_required_player__Controller | T_required_player__Typed
type U_restriction = (
    T_restriction__CantEnterBattlefieldFrom
    | T_restriction__DamagePreventionDisabled
    | T_restriction__PlayerAttribute
    | T_restriction__ProhibitActivity
)
type U_retarget = (
    T_retarget__KeepOriginalTargets
    | T_retarget__MayChooseNewTargets
    | T_retarget__RetargetEachCopyToIterationMember
)
type U_rhs = (
    T_rhs__DivideRounded
    | T_rhs__Fixed
    | T_rhs__HandSize
    | T_rhs__ObjectCount
    | T_rhs__Offset
    | T_rhs__Ref
)
type U_right = T_right__Fixed | T_right__Ref
type U_sacrifice_filter = T_sacrifice_filter__Typed
type U_scale = T_scale__Ref
type U_scaling = (
    T_scaling__PerAffectedAndQuantityRef
    | T_scaling__PerAffectedCreature
    | T_scaling__PerAffectedWithRef
    | T_scaling__PerQuantityRef
)
type U_scope = (
    T_scope__All
    | T_scope__AmassedArmy
    | T_scope__Anaphoric
    | T_scope__CostPaidObject
    | T_scope__Demonstrative
    | T_scope__EventSource
    | T_scope__EventTarget
    | T_scope__OtherRevealedCard
    | T_scope__OwnedSameName
    | T_scope__OwnedSubtype
    | T_scope__Recipient
    | T_scope__Single
    | T_scope__Source
    | T_scope__SourcesControlledBy
    | T_scope__Target
)
type U_selection = T_selection__Random
type U_selection_constraint = (
    T_selection_constraint__DistinctQualities
    | T_selection_constraint__MatchEachFilter
    | T_selection_constraint__TotalManaValue
)
type U_solve_condition = (
    T_solve_condition__Condition
    | T_solve_condition__ObjectCount
    | T_solve_condition__Text
)
type U_source = (
    T_source__And
    | T_source__Any
    | T_source__AttachedTo
    | T_source__ChosenCard
    | T_source__ExiledBySource
    | T_source__Objects
    | T_source__Or
    | T_source__SelfRef
    | T_source__ThisObject
    | T_source__TrackedSet
    | T_source__TriggeringSource
    | T_source__Typed
    | T_source__Zone
)
type U_source_filter = (
    T_source_filter__ChosenDamageSource
    | T_source_filter__HasChosenName
    | T_source_filter__Or
    | T_source_filter__SelfRef
    | T_source_filter__Typed
)
type U_source_pool = T_source_pool__SideboardAndFaceUpExile
type U_source_rider = T_source_rider__Destroy | T_source_rider__LosesAbilities
type U_sources = T_sources__Typed
type U_spell_cast_origin = T_spell_cast_origin__Equals | T_spell_cast_origin__NotEquals
type U_spell_filter = (
    T_spell_filter__HasChosenName | T_spell_filter__Or | T_spell_filter__Typed
)
type U_state = T_state__Tap | T_state__Untap
type U_step = T_step__CombatPhase | T_step__Step
type U_strive_cost = T_strive_cost__Cost
type U_subject = (
    T_subject__AttackTarget
    | T_subject__CommittedChoice
    | T_subject__Controller
    | T_subject__LastRevealed
    | T_subject__Named
    | T_subject__Objects
    | T_subject__Or
    | T_subject__ParentTarget
    | T_subject__Proposition
    | T_subject__SelfRef
    | T_subject__Target
    | T_subject__TriggeringSource
    | T_subject__Typed
)
type U_subtype_filter = T_subtype_filter__Or | T_subtype_filter__Typed
type U_tag = T_tag__Backup
type U_tally_mode = T_tally_mode__PerVote | T_tally_mode__TopVotes
type U_target = (
    T_target__AllPlayers
    | T_target__And
    | T_target__Any
    | T_target__AttachedTo
    | T_target__Controller
    | T_target__CostPaidObject
    | T_target__DefendingPlayer
    | T_target__EventTarget
    | T_target__ExiledBySource
    | T_target__ExiledCardByIndex
    | T_target__GrantingObject
    | T_target__LastCreated
    | T_target__None
    | T_target__Or
    | T_target__OriginalController
    | T_target__Owner
    | T_target__ParentTarget
    | T_target__ParentTargetController
    | T_target__ParentTargetOwner
    | T_target__ParentTargetSlot
    | T_target__Player
    | T_target__PostReplacementDamageTarget
    | T_target__PostReplacementDamageTargetOwner
    | T_target__PostReplacementSourceController
    | T_target__ScopedPlayer
    | T_target__SelfRef
    | T_target__SourceChosenPlayer
    | T_target__StackAbility
    | T_target__StackSpell
    | T_target__TrackedSet
    | T_target__TrackedSetFiltered
    | T_target__TriggeringPlayer
    | T_target__TriggeringSource
    | T_target__TriggeringSourceController
    | T_target__TriggeringSpellController
    | T_target__Typed
)
type U_target_a = (
    T_target_a__And | T_target_a__Or | T_target_a__SelfRef | T_target_a__Typed
)
type U_target_b = T_target_b__Or | T_target_b__TriggeringSource | T_target_b__Typed
type U_target_chooser = T_target_chooser__ScopedPlayer
type U_target_constraints = (
    T_target_constraints__DifferentObjectControllers
    | T_target_constraints__SameZoneOwner
    | T_target_constraints__TotalManaValue
)
type U_target_kind = (
    T_target_kind__Counters | T_target_kind__LifeTotal | T_target_kind__ManaPool
)
type U_target_player = (
    T_target_player__ParentTargetController
    | T_target_player__Player
    | T_target_player__Typed
)
type U_target_selection_mode = T_target_selection_mode__Random
type U_threshold = T_threshold__Fixed
type U_tie = T_tie__AllTied | T_tie__Breaker
type U_total_power_cap = T_total_power_cap__Fixed
type U_toughness = T_toughness__Fixed | T_toughness__Quantity | T_toughness__Variable
type U_unless_filter = T_unless_filter__Or | T_unless_filter__Typed
type U_until = T_until__CumulativeThreshold | T_until__NextMatches
type U_valid_card = (
    T_valid_card__And
    | T_valid_card__Any
    | T_valid_card__AttachedTo
    | T_valid_card__Or
    | T_valid_card__ParentTarget
    | T_valid_card__ParentTargetSlot
    | T_valid_card__SelfRef
    | T_valid_card__Typed
)
type U_valid_source = (
    T_valid_source__And
    | T_valid_source__AttachedTo
    | T_valid_source__Or
    | T_valid_source__ParentTarget
    | T_valid_source__Player
    | T_valid_source__SelfRef
    | T_valid_source__StackAbility
    | T_valid_source__StackSpell
    | T_valid_source__Typed
)
type U_valid_subject_player = (
    T_valid_subject_player__Controller | T_valid_subject_player__Player
)
type U_valid_target = (
    T_valid_target__AttachedTo
    | T_valid_target__Controller
    | T_valid_target__Or
    | T_valid_target__ParentTargetController
    | T_valid_target__Player
    | T_valid_target__SelfRef
    | T_valid_target__SourceChosenPlayer
    | T_valid_target__TriggeringPlayer
    | T_valid_target__Typed
)
type U_value = (
    T_value__Difference
    | T_value__DivideRounded
    | T_value__Fixed
    | T_value__Max
    | T_value__Multiply
    | T_value__Offset
    | T_value__Ref
    | T_value__Sum
)
type U_visibility = T_visibility__Open | T_visibility__Secret
type U_voter_scope = (
    T_voter_scope__AllPlayers
    | T_voter_scope__ControllerLabels
    | T_voter_scope__EachOpponent
)


# --- dispatch tables (full schema coverage) ---

GENERATED_BY_KEY: dict[tuple[str, str], type[TypedMirrorNode]] = {
    ("ActivateTagged", "Equip"): T_ActivateTagged__Equip,
    ("ActivateTagged", "PowerUp"): T_ActivateTagged__PowerUp,
    ("Bestow", "Mana"): T_Bestow__Mana,
    ("Bestow", "NonMana"): T_Bestow__NonMana,
    ("Blitz", "Cost"): T_Blitz__Cost,
    ("Blitz", "SelfManaCost"): T_Blitz__SelfManaCost,
    ("Bloodthirst", "Fixed"): T_Bloodthirst__Fixed,
    ("Bloodthirst", "X"): T_Bloodthirst__X,
    ("Buyback", "Mana"): T_Buyback__Mana,
    ("Buyback", "NonMana"): T_Buyback__NonMana,
    ("Cleave", "Cost"): T_Cleave__Cost,
    ("CommanderNinjutsu", "Cost"): T_CommanderNinjutsu__Cost,
    ("Companion", "EvenManaValues"): T_Companion__EvenManaValues,
    ("Companion", "MaxPermanentManaValue"): T_Companion__MaxPermanentManaValue,
    ("Companion", "MinManaValue"): T_Companion__MinManaValue,
    ("Companion", "NoRepeatedManaSymbols"): T_Companion__NoRepeatedManaSymbols,
    ("Companion", "OddManaValues"): T_Companion__OddManaValues,
    (
        "Companion",
        "PermanentsHaveActivatedAbilities",
    ): T_Companion__PermanentsHaveActivatedAbilities,
    ("Companion", "SharedCardType"): T_Companion__SharedCardType,
    ("CumulativeUpkeep", "Discard"): T_CumulativeUpkeep__Discard,
    ("CumulativeUpkeep", "EffectCost"): T_CumulativeUpkeep__EffectCost,
    ("CumulativeUpkeep", "Exile"): T_CumulativeUpkeep__Exile,
    ("CumulativeUpkeep", "Mana"): T_CumulativeUpkeep__Mana,
    ("CumulativeUpkeep", "OneOf"): T_CumulativeUpkeep__OneOf,
    ("CumulativeUpkeep", "PayLife"): T_CumulativeUpkeep__PayLife,
    ("CumulativeUpkeep", "Sacrifice"): T_CumulativeUpkeep__Sacrifice,
    ("Cycling", "Mana"): T_Cycling__Mana,
    ("Cycling", "NonMana"): T_Cycling__NonMana,
    ("Dash", "Cost"): T_Dash__Cost,
    ("Disguise", "Cost"): T_Disguise__Cost,
    ("Disturb", "Cost"): T_Disturb__Cost,
    ("Echo", "Mana"): T_Echo__Mana,
    ("Echo", "NonMana"): T_Echo__NonMana,
    ("Embalm", "Mana"): T_Embalm__Mana,
    ("Emerge", "Cost"): T_Emerge__Cost,
    ("Enchant", "Any"): T_Enchant__Any,
    ("Enchant", "Or"): T_Enchant__Or,
    ("Enchant", "ParentTarget"): T_Enchant__ParentTarget,
    ("Enchant", "Player"): T_Enchant__Player,
    ("Enchant", "Typed"): T_Enchant__Typed,
    ("Encore", "Cost"): T_Encore__Cost,
    ("Encore", "SelfManaCost"): T_Encore__SelfManaCost,
    ("Encore", "SelfManaValue"): T_Encore__SelfManaValue,
    ("Entwine", "Cost"): T_Entwine__Cost,
    ("EqualTo", "Fixed"): T_EqualTo__Fixed,
    ("EqualTo", "Ref"): T_EqualTo__Ref,
    ("Equip", "Cost"): T_Equip__Cost,
    ("Equip", "SelfManaValue"): T_Equip__SelfManaValue,
    ("Escalate", "Discard"): T_Escalate__Discard,
    ("Escalate", "Mana"): T_Escalate__Mana,
    ("Escalate", "TapCreatures"): T_Escalate__TapCreatures,
    ("Escape", "NonMana"): T_Escape__NonMana,
    ("Eternalize", "Mana"): T_Eternalize__Mana,
    ("Eternalize", "NonMana"): T_Eternalize__NonMana,
    ("Evoke", "Mana"): T_Evoke__Mana,
    ("Evoke", "NonMana"): T_Evoke__NonMana,
    ("Filter", "Typed"): T_Filter__Typed,
    ("Firebending", "Fixed"): T_Firebending__Fixed,
    ("Firebending", "Ref"): T_Firebending__Ref,
    ("Flashback", "Mana"): T_Flashback__Mana,
    ("Flashback", "NonMana"): T_Flashback__NonMana,
    ("Foretell", "Cost"): T_Foretell__Cost,
    ("Foretell", "SelfManaCostReduced"): T_Foretell__SelfManaCostReduced,
    ("Fortify", "Cost"): T_Fortify__Cost,
    ("Freerunning", "Cost"): T_Freerunning__Cost,
    ("Gift", "Card"): T_Gift__Card,
    ("Gift", "Food"): T_Gift__Food,
    ("Gift", "TappedFish"): T_Gift__TappedFish,
    ("Gift", "Treasure"): T_Gift__Treasure,
    ("Harmonize", "Cost"): T_Harmonize__Cost,
    ("Harmonize", "SelfManaCost"): T_Harmonize__SelfManaCost,
    ("HexproofFrom", "CardType"): T_HexproofFrom__CardType,
    ("HexproofFrom", "ChosenColor"): T_HexproofFrom__ChosenColor,
    ("HexproofFrom", "Color"): T_HexproofFrom__Color,
    ("HexproofFrom", "Quality"): T_HexproofFrom__Quality,
    ("KeywordAbilityActivated", "Boast"): T_KeywordAbilityActivated__Boast,
    ("KeywordAbilityActivated", "Exhaust"): T_KeywordAbilityActivated__Exhaust,
    ("KeywordAbilityActivated", "Outlast"): T_KeywordAbilityActivated__Outlast,
    ("KeywordAbilityActivated", "PowerUp"): T_KeywordAbilityActivated__PowerUp,
    ("Kicker", "Cost"): T_Kicker__Cost,
    ("LevelUp", "Cost"): T_LevelUp__Cost,
    ("Madness", "Cost"): T_Madness__Cost,
    ("Mayhem", "Cost"): T_Mayhem__Cost,
    ("Mayhem", "SelfManaCost"): T_Mayhem__SelfManaCost,
    ("Megamorph", "Cost"): T_Megamorph__Cost,
    ("Miracle", "Cost"): T_Miracle__Cost,
    ("Miracle", "SelfManaCostReduced"): T_Miracle__SelfManaCostReduced,
    ("Mobilize", "Fixed"): T_Mobilize__Fixed,
    ("Mobilize", "Ref"): T_Mobilize__Ref,
    ("MoreThanMeetsTheEye", "Cost"): T_MoreThanMeetsTheEye__Cost,
    ("Morph", "Cost"): T_Morph__Cost,
    ("Mutate", "Cost"): T_Mutate__Cost,
    ("Ninjutsu", "Cost"): T_Ninjutsu__Cost,
    ("Offspring", "Cost"): T_Offspring__Cost,
    ("Outlast", "Cost"): T_Outlast__Cost,
    ("Overload", "Cost"): T_Overload__Cost,
    ("Partner", "CharacterSelect"): T_Partner__CharacterSelect,
    ("Partner", "ChooseABackground"): T_Partner__ChooseABackground,
    ("Partner", "DoctorsCompanion"): T_Partner__DoctorsCompanion,
    ("Partner", "FriendsForever"): T_Partner__FriendsForever,
    ("Partner", "Generic"): T_Partner__Generic,
    ("Partner", "With"): T_Partner__With,
    ("Plot", "Cost"): T_Plot__Cost,
    ("Prowl", "Cost"): T_Prowl__Cost,
    ("Quality", "Any"): T_Quality__Any,
    ("Quality", "Or"): T_Quality__Or,
    ("Quality", "Typed"): T_Quality__Typed,
    ("Reconfigure", "Cost"): T_Reconfigure__Cost,
    ("Recover", "Cost"): T_Recover__Cost,
    ("Replicate", "Cost"): T_Replicate__Cost,
    ("Replicate", "SelfManaCost"): T_Replicate__SelfManaCost,
    ("Scavenge", "Cost"): T_Scavenge__Cost,
    ("Scavenge", "SelfManaCost"): T_Scavenge__SelfManaCost,
    ("Sneak", "Cost"): T_Sneak__Cost,
    ("Specialize", "Cost"): T_Specialize__Cost,
    ("Spectacle", "Cost"): T_Spectacle__Cost,
    ("Squad", "Cost"): T_Squad__Cost,
    ("Surge", "Cost"): T_Surge__Cost,
    ("Transfigure", "Cost"): T_Transfigure__Cost,
    ("Transmute", "Cost"): T_Transmute__Cost,
    ("Unearth", "Cost"): T_Unearth__Cost,
    ("Ward", "Compound"): T_Ward__Compound,
    ("Ward", "DiscardCard"): T_Ward__DiscardCard,
    ("Ward", "Mana"): T_Ward__Mana,
    ("Ward", "PayLife"): T_Ward__PayLife,
    ("Ward", "Sacrifice"): T_Ward__Sacrifice,
    ("Ward", "Waterbend"): T_Ward__Waterbend,
    ("Warp", "Cost"): T_Warp__Cost,
    ("WebSlinging", "Cost"): T_WebSlinging__Cost,
    ("ability_tag", "Augment"): T_ability_tag__Augment,
    ("ability_tag", "Backup"): T_ability_tag__Backup,
    ("ability_tag", "Boast"): T_ability_tag__Boast,
    ("ability_tag", "Cycling"): T_ability_tag__Cycling,
    ("ability_tag", "Equip"): T_ability_tag__Equip,
    ("ability_tag", "Evolve"): T_ability_tag__Evolve,
    ("ability_tag", "Exhaust"): T_ability_tag__Exhaust,
    ("ability_tag", "Outlast"): T_ability_tag__Outlast,
    ("ability_tag", "PowerUp"): T_ability_tag__PowerUp,
    ("action", "exile_from_pool"): T_action__exile_from_pool,
    ("action", "put_counter"): T_action__put_counter,
    ("activation_restrictions", "AsInstant"): T_activation_restrictions__AsInstant,
    ("activation_restrictions", "AsSorcery"): T_activation_restrictions__AsSorcery,
    (
        "activation_restrictions",
        "BeforeAttackersDeclared",
    ): T_activation_restrictions__BeforeAttackersDeclared,
    (
        "activation_restrictions",
        "BeforeCombatDamage",
    ): T_activation_restrictions__BeforeCombatDamage,
    (
        "activation_restrictions",
        "ClassLevelIs",
    ): T_activation_restrictions__ClassLevelIs,
    (
        "activation_restrictions",
        "CounterThreshold",
    ): T_activation_restrictions__CounterThreshold,
    (
        "activation_restrictions",
        "DuringCombat",
    ): T_activation_restrictions__DuringCombat,
    (
        "activation_restrictions",
        "DuringYourTurn",
    ): T_activation_restrictions__DuringYourTurn,
    (
        "activation_restrictions",
        "DuringYourUpkeep",
    ): T_activation_restrictions__DuringYourUpkeep,
    ("activation_restrictions", "IsSolved"): T_activation_restrictions__IsSolved,
    (
        "activation_restrictions",
        "LevelCounterRange",
    ): T_activation_restrictions__LevelCounterRange,
    (
        "activation_restrictions",
        "MatchesCardCastTiming",
    ): T_activation_restrictions__MatchesCardCastTiming,
    (
        "activation_restrictions",
        "MaxTimesEachTurn",
    ): T_activation_restrictions__MaxTimesEachTurn,
    ("activation_restrictions", "OnlyOnce"): T_activation_restrictions__OnlyOnce,
    (
        "activation_restrictions",
        "OnlyOnceEachTurn",
    ): T_activation_restrictions__OnlyOnceEachTurn,
    (
        "activation_restrictions",
        "RequiresCondition",
    ): T_activation_restrictions__RequiresCondition,
    ("activation_source_filter", "Typed"): T_activation_source_filter__Typed,
    ("activator", "Controller"): T_activator__Controller,
    ("activator_filter", "All"): T_activator_filter__All,
    ("activator_filter", "Opponent"): T_activator_filter__Opponent,
    ("activity", "ActivateAbilities"): T_activity__ActivateAbilities,
    ("activity", "Attack"): T_activity__Attack,
    ("activity", "CastOnlyFromZones"): T_activity__CastOnlyFromZones,
    ("activity", "CastSpells"): T_activity__CastSpells,
    ("activity", "ProhibitPlayFromZone"): T_activity__ProhibitPlayFromZone,
    ("additional_cost", "Choice"): T_additional_cost__Choice,
    ("additional_cost", "Kicker"): T_additional_cost__Kicker,
    ("additional_cost", "Optional"): T_additional_cost__Optional,
    ("additional_cost", "Required"): T_additional_cost__Required,
    ("additional_filter", "Cmc"): T_additional_filter__Cmc,
    (
        "additional_filter",
        "IsChosenCreatureType",
    ): T_additional_filter__IsChosenCreatureType,
    (
        "additional_filter",
        "MatchesLastChosenCardPredicate",
    ): T_additional_filter__MatchesLastChosenCardPredicate,
    ("additional_modifications", "AddColor"): T_additional_modifications__AddColor,
    (
        "additional_modifications",
        "AddCounterOnEnter",
    ): T_additional_modifications__AddCounterOnEnter,
    ("additional_modifications", "AddKeyword"): T_additional_modifications__AddKeyword,
    (
        "additional_modifications",
        "AddStaticMode",
    ): T_additional_modifications__AddStaticMode,
    ("additional_modifications", "AddSubtype"): T_additional_modifications__AddSubtype,
    (
        "additional_modifications",
        "AddSupertype",
    ): T_additional_modifications__AddSupertype,
    ("additional_modifications", "AddType"): T_additional_modifications__AddType,
    (
        "additional_modifications",
        "GrantAbility",
    ): T_additional_modifications__GrantAbility,
    (
        "additional_modifications",
        "GrantStaticAbility",
    ): T_additional_modifications__GrantStaticAbility,
    (
        "additional_modifications",
        "GrantTrigger",
    ): T_additional_modifications__GrantTrigger,
    (
        "additional_modifications",
        "RemoveAllSubtypes",
    ): T_additional_modifications__RemoveAllSubtypes,
    (
        "additional_modifications",
        "RemoveManaCost",
    ): T_additional_modifications__RemoveManaCost,
    (
        "additional_modifications",
        "RemoveSupertype",
    ): T_additional_modifications__RemoveSupertype,
    (
        "additional_modifications",
        "RetainPrintedAbilityFromSource",
    ): T_additional_modifications__RetainPrintedAbilityFromSource,
    (
        "additional_modifications",
        "RetainPrintedTriggerFromSource",
    ): T_additional_modifications__RetainPrintedTriggerFromSource,
    (
        "additional_modifications",
        "SetCardTypes",
    ): T_additional_modifications__SetCardTypes,
    ("additional_modifications", "SetColor"): T_additional_modifications__SetColor,
    ("additional_modifications", "SetName"): T_additional_modifications__SetName,
    ("additional_modifications", "SetPower"): T_additional_modifications__SetPower,
    (
        "additional_modifications",
        "SetPowerDynamic",
    ): T_additional_modifications__SetPowerDynamic,
    (
        "additional_modifications",
        "SetStartingLoyalty",
    ): T_additional_modifications__SetStartingLoyalty,
    (
        "additional_modifications",
        "SetToughness",
    ): T_additional_modifications__SetToughness,
    (
        "additional_modifications",
        "SetToughnessDynamic",
    ): T_additional_modifications__SetToughnessDynamic,
    ("affected", "And"): T_affected__And,
    ("affected", "Any"): T_affected__Any,
    ("affected", "AttachedTo"): T_affected__AttachedTo,
    ("affected", "Controller"): T_affected__Controller,
    ("affected", "HasChosenName"): T_affected__HasChosenName,
    ("affected", "LastCreated"): T_affected__LastCreated,
    ("affected", "Or"): T_affected__Or,
    ("affected", "OriginalSource"): T_affected__OriginalSource,
    ("affected", "ParentTarget"): T_affected__ParentTarget,
    ("affected", "Player"): T_affected__Player,
    ("affected", "PlayerWhoChoseLabel"): T_affected__PlayerWhoChoseLabel,
    ("affected", "SelfRef"): T_affected__SelfRef,
    ("affected", "SourceOrPaired"): T_affected__SourceOrPaired,
    ("affected", "TrackedSet"): T_affected__TrackedSet,
    ("affected", "TriggeringPlayer"): T_affected__TriggeringPlayer,
    ("affected", "TriggeringSource"): T_affected__TriggeringSource,
    ("affected", "Typed"): T_affected__Typed,
    ("affected_players", "AllPlayers"): T_affected_players__AllPlayers,
    ("affected_players", "DefendingPlayer"): T_affected_players__DefendingPlayer,
    (
        "affected_players",
        "OpponentsOfSourceController",
    ): T_affected_players__OpponentsOfSourceController,
    (
        "affected_players",
        "ParentObjectTargetController",
    ): T_affected_players__ParentObjectTargetController,
    (
        "affected_players",
        "ParentTargetedPlayer",
    ): T_affected_players__ParentTargetedPlayer,
    ("affected_players", "ScopedPlayer"): T_affected_players__ScopedPlayer,
    ("affected_players", "TargetedPlayer"): T_affected_players__TargetedPlayer,
    ("alt_ability_cost", "Discard"): T_alt_ability_cost__Discard,
    (
        "alt_ability_cost",
        "KeywordCostOfCastSpell",
    ): T_alt_ability_cost__KeywordCostOfCastSpell,
    ("alt_ability_cost", "PayLife"): T_alt_ability_cost__PayLife,
    ("alt_cost", "PayLife"): T_alt_cost__PayLife,
    ("amount", "ClampMin"): T_amount__ClampMin,
    ("amount", "Cost"): T_amount__Cost,
    ("amount", "Difference"): T_amount__Difference,
    ("amount", "DivideRounded"): T_amount__DivideRounded,
    ("amount", "Fixed"): T_amount__Fixed,
    ("amount", "Max"): T_amount__Max,
    ("amount", "Multiply"): T_amount__Multiply,
    ("amount", "Offset"): T_amount__Offset,
    ("amount", "Ref"): T_amount__Ref,
    ("amount", "Sum"): T_amount__Sum,
    ("amount_dynamic", "Ref"): T_amount_dynamic__Ref,
    ("attach_to", "ParentTarget"): T_attach_to__ParentTarget,
    ("attach_to", "Typed"): T_attach_to__Typed,
    ("attachment", "Any"): T_attachment__Any,
    ("attachment", "Or"): T_attachment__Or,
    ("attachment", "ParentTarget"): T_attachment__ParentTarget,
    ("attachment", "ParentTargetSlot"): T_attachment__ParentTargetSlot,
    ("attachment", "SelfRef"): T_attachment__SelfRef,
    ("attachment", "TriggeringSource"): T_attachment__TriggeringSource,
    ("attachment", "Typed"): T_attachment__Typed,
    ("attacker_restriction", "ParentTarget"): T_attacker_restriction__ParentTarget,
    ("attacker_restriction", "Typed"): T_attacker_restriction__Typed,
    ("attr", "BattlefieldEntriesThisTurn"): T_attr__BattlefieldEntriesThisTurn,
    ("attr", "CardsDrawnThisTurn"): T_attr__CardsDrawnThisTurn,
    ("attr", "HandSize"): T_attr__HandSize,
    ("attr", "LifeLostThisTurn"): T_attr__LifeLostThisTurn,
    ("attr", "LifeTotal"): T_attr__LifeTotal,
    ("attr", "PlayerCounter"): T_attr__PlayerCounter,
    ("base", "Discard"): T_base__Discard,
    ("base", "Exile"): T_base__Exile,
    ("base", "Mana"): T_base__Mana,
    ("base", "OneOf"): T_base__OneOf,
    ("base", "PayLife"): T_base__PayLife,
    ("base", "Sacrifice"): T_base__Sacrifice,
    ("blockers", "Typed"): T_blockers__Typed,
    ("by", "Typed"): T_by__Typed,
    ("candidate_filter", "Typed"): T_candidate_filter__Typed,
    ("cap", "OnlyOnceEachTurn"): T_cap__OnlyOnceEachTurn,
    ("card_filter", "Any"): T_card_filter__Any,
    ("card_filter", "None"): T_card_filter__None,
    ("card_filter", "Or"): T_card_filter__Or,
    ("card_filter", "Typed"): T_card_filter__Typed,
    ("cast_cost_raise", "Cost"): T_cast_cost_raise__Cost,
    (
        "casting_restrictions",
        "AfterBlockersDeclared",
    ): T_casting_restrictions__AfterBlockersDeclared,
    ("casting_restrictions", "AfterCombat"): T_casting_restrictions__AfterCombat,
    (
        "casting_restrictions",
        "BeforeAttackersDeclared",
    ): T_casting_restrictions__BeforeAttackersDeclared,
    (
        "casting_restrictions",
        "BeforeBlockersDeclared",
    ): T_casting_restrictions__BeforeBlockersDeclared,
    (
        "casting_restrictions",
        "BeforeCombatDamage",
    ): T_casting_restrictions__BeforeCombatDamage,
    (
        "casting_restrictions",
        "DeclareAttackersStep",
    ): T_casting_restrictions__DeclareAttackersStep,
    (
        "casting_restrictions",
        "DeclareBlockersStep",
    ): T_casting_restrictions__DeclareBlockersStep,
    ("casting_restrictions", "DuringCombat"): T_casting_restrictions__DuringCombat,
    (
        "casting_restrictions",
        "DuringOpponentsTurn",
    ): T_casting_restrictions__DuringOpponentsTurn,
    (
        "casting_restrictions",
        "DuringOpponentsUpkeep",
    ): T_casting_restrictions__DuringOpponentsUpkeep,
    (
        "casting_restrictions",
        "DuringYourEndStep",
    ): T_casting_restrictions__DuringYourEndStep,
    ("casting_restrictions", "DuringYourTurn"): T_casting_restrictions__DuringYourTurn,
    (
        "casting_restrictions",
        "RequiresCondition",
    ): T_casting_restrictions__RequiresCondition,
    ("choose_filter", "Typed"): T_choose_filter__Typed,
    ("chooser", "ChosenPlayer"): T_chooser__ChosenPlayer,
    ("chooser", "Controller"): T_chooser__Controller,
    ("chooser", "DefendingPlayer"): T_chooser__DefendingPlayer,
    ("chooser", "Opponent"): T_chooser__Opponent,
    (
        "chooser",
        "ParentObjectTargetController",
    ): T_chooser__ParentObjectTargetController,
    ("chooser", "ParentObjectTargetOwner"): T_chooser__ParentObjectTargetOwner,
    ("chooser", "PlayerAttribute"): T_chooser__PlayerAttribute,
    ("chooser", "TriggeringPlayer"): T_chooser__TriggeringPlayer,
    ("colors", "ChosenColor"): T_colors__ChosenColor,
    ("colors", "Fixed"): T_colors__Fixed,
    ("condition", "ActivatedAbilityIsNonMana"): T_condition__ActivatedAbilityIsNonMana,
    ("condition", "AdditionalCostPaid"): T_condition__AdditionalCostPaid,
    ("condition", "AdditionalCostPaidInstead"): T_condition__AdditionalCostPaidInstead,
    ("condition", "AlternativeManaCostPaid"): T_condition__AlternativeManaCostPaid,
    ("condition", "And"): T_condition__And,
    ("condition", "AtNextPhase"): T_condition__AtNextPhase,
    ("condition", "AtNextPhaseForPlayer"): T_condition__AtNextPhaseForPlayer,
    ("condition", "AttackersDeclaredCount"): T_condition__AttackersDeclaredCount,
    (
        "condition",
        "BattlefieldEntriesThisTurn",
    ): T_condition__BattlefieldEntriesThisTurn,
    ("condition", "BeenAttackedThisStep"): T_condition__BeenAttackedThisStep,
    ("condition", "CastDuringPhase"): T_condition__CastDuringPhase,
    ("condition", "CastFromZone"): T_condition__CastFromZone,
    ("condition", "CastTimingPermission"): T_condition__CastTimingPermission,
    ("condition", "CastVariantPaid"): T_condition__CastVariantPaid,
    ("condition", "CastVariantPaidInstead"): T_condition__CastVariantPaidInstead,
    ("condition", "CastVariantPaidPersistent"): T_condition__CastVariantPaidPersistent,
    ("condition", "CastViaEscape"): T_condition__CastViaEscape,
    ("condition", "CastViaKicker"): T_condition__CastViaKicker,
    ("condition", "CastingAsVariant"): T_condition__CastingAsVariant,
    ("condition", "ChosenLabelIs"): T_condition__ChosenLabelIs,
    ("condition", "ClassLevelGE"): T_condition__ClassLevelGE,
    ("condition", "CompletedADungeon"): T_condition__CompletedADungeon,
    ("condition", "CompletedDungeon"): T_condition__CompletedDungeon,
    ("condition", "ConditionInstead"): T_condition__ConditionInstead,
    (
        "condition",
        "ControllerControlledMatchingAsCast",
    ): T_condition__ControllerControlledMatchingAsCast,
    (
        "condition",
        "ControllerControlsMatching",
    ): T_condition__ControllerControlsMatching,
    ("condition", "ControlsCommander"): T_condition__ControlsCommander,
    (
        "condition",
        "ControlsCreatureWithKeyword",
    ): T_condition__ControlsCreatureWithKeyword,
    ("condition", "ControlsNone"): T_condition__ControlsNone,
    ("condition", "ControlsType"): T_condition__ControlsType,
    (
        "condition",
        "CostPaidObjectMatchesFilter",
    ): T_condition__CostPaidObjectMatchesFilter,
    ("condition", "CreatureDiedThisTurn"): T_condition__CreatureDiedThisTurn,
    (
        "condition",
        "CreaturesYouControlTotalPowerAtLeast",
    ): T_condition__CreaturesYouControlTotalPowerAtLeast,
    (
        "condition",
        "DamagedPlayerIsEventSourceOwner",
    ): T_condition__DamagedPlayerIsEventSourceOwner,
    ("condition", "DayNightIs"): T_condition__DayNightIs,
    ("condition", "DayNightIsNeither"): T_condition__DayNightIsNeither,
    (
        "condition",
        "DealtDamageBySourceThisTurn",
    ): T_condition__DealtDamageBySourceThisTurn,
    (
        "condition",
        "DealtDamageThisTurnBySource",
    ): T_condition__DealtDamageThisTurnBySource,
    ("condition", "DefendingPlayerControls"): T_condition__DefendingPlayerControls,
    (
        "condition",
        "DefendingPlayerControlsNone",
    ): T_condition__DefendingPlayerControlsNone,
    ("condition", "DevotionGE"): T_condition__DevotionGE,
    ("condition", "DuringPlayersTurn"): T_condition__DuringPlayersTurn,
    ("condition", "DuringUntapStep"): T_condition__DuringUntapStep,
    ("condition", "DuringYourTurn"): T_condition__DuringYourTurn,
    ("condition", "EchoDue"): T_condition__EchoDue,
    ("condition", "EffectCausedDiscard"): T_condition__EffectCausedDiscard,
    ("condition", "EffectOutcome"): T_condition__EffectOutcome,
    ("condition", "EnchantedIsFaceDown"): T_condition__EnchantedIsFaceDown,
    ("condition", "EnteredFromZone"): T_condition__EnteredFromZone,
    (
        "condition",
        "EventDamageSourceMatchesFilter",
    ): T_condition__EventDamageSourceMatchesFilter,
    ("condition", "EventObjectMatchesFilter"): T_condition__EventObjectMatchesFilter,
    ("condition", "EventOutcomeWon"): T_condition__EventOutcomeWon,
    ("condition", "EventSourceControlledBy"): T_condition__EventSourceControlledBy,
    ("condition", "ExceptFirstDrawInDrawStep"): T_condition__ExceptFirstDrawInDrawStep,
    ("condition", "FirstCombatPhaseOfTurn"): T_condition__FirstCombatPhaseOfTurn,
    ("condition", "FirstEndStepOfTurn"): T_condition__FirstEndStepOfTurn,
    ("condition", "FirstSpellThisGame"): T_condition__FirstSpellThisGame,
    (
        "condition",
        "FirstTimeObjectTappedThisTurn",
    ): T_condition__FirstTimeObjectTappedThisTurn,
    (
        "condition",
        "FirstTokenCreationEachTurn",
    ): T_condition__FirstTokenCreationEachTurn,
    ("condition", "HadCounters"): T_condition__HadCounters,
    ("condition", "HandSizeExact"): T_condition__HandSizeExact,
    ("condition", "HandSizeOneOf"): T_condition__HandSizeOneOf,
    ("condition", "HasCityBlessing"): T_condition__HasCityBlessing,
    ("condition", "HasCounters"): T_condition__HasCounters,
    ("condition", "HasMaxSpeed"): T_condition__HasMaxSpeed,
    ("condition", "IfControlsMatching"): T_condition__IfControlsMatching,
    ("condition", "IsInitiative"): T_condition__IsInitiative,
    ("condition", "IsMonarch"): T_condition__IsMonarch,
    ("condition", "IsPresent"): T_condition__IsPresent,
    ("condition", "IsRenowned"): T_condition__IsRenowned,
    ("condition", "IsRingBearer"): T_condition__IsRingBearer,
    ("condition", "IsTapped"): T_condition__IsTapped,
    ("condition", "IsYourTurn"): T_condition__IsYourTurn,
    ("condition", "ManaColorSpent"): T_condition__ManaColorSpent,
    ("condition", "ManaSpentCondition"): T_condition__ManaSpentCondition,
    ("condition", "MinCoAttackers"): T_condition__MinCoAttackers,
    ("condition", "NoMonarch"): T_condition__NoMonarch,
    ("condition", "Not"): T_condition__Not,
    ("condition", "NthResolutionThisTurn"): T_condition__NthResolutionThisTurn,
    ("condition", "ObjectsShareQuality"): T_condition__ObjectsShareQuality,
    ("condition", "OnlyExtraTurn"): T_condition__OnlyExtraTurn,
    ("condition", "OnlyIfQuantity"): T_condition__OnlyIfQuantity,
    ("condition", "OpponentDamagedThisTurn"): T_condition__OpponentDamagedThisTurn,
    ("condition", "OpponentPoisonAtLeast"): T_condition__OpponentPoisonAtLeast,
    (
        "condition",
        "OpponentSearchedLibraryThisTurn",
    ): T_condition__OpponentSearchedLibraryThisTurn,
    ("condition", "Or"): T_condition__Or,
    ("condition", "PlacedByAbilitySource"): T_condition__PlacedByAbilitySource,
    ("condition", "PlayerCountAtLeast"): T_condition__PlayerCountAtLeast,
    ("condition", "PreviousEffectAmount"): T_condition__PreviousEffectAmount,
    ("condition", "QuantityCheck"): T_condition__QuantityCheck,
    ("condition", "QuantityComparison"): T_condition__QuantityComparison,
    ("condition", "QuantityVsEachOpponent"): T_condition__QuantityVsEachOpponent,
    (
        "condition",
        "RecipientAttackingOwnerTarget",
    ): T_condition__RecipientAttackingOwnerTarget,
    ("condition", "RecipientHasCounters"): T_condition__RecipientHasCounters,
    ("condition", "RecipientMatchesFilter"): T_condition__RecipientMatchesFilter,
    ("condition", "RevealedHasCardType"): T_condition__RevealedHasCardType,
    (
        "condition",
        "SharesColorWithMostCommonColorAmongPermanents",
    ): T_condition__SharesColorWithMostCommonColorAmongPermanents,
    ("condition", "SolveConditionMet"): T_condition__SolveConditionMet,
    ("condition", "SourceAttachedTo"): T_condition__SourceAttachedTo,
    ("condition", "SourceAttachedToCreature"): T_condition__SourceAttachedToCreature,
    ("condition", "SourceAttackedThisTurn"): T_condition__SourceAttackedThisTurn,
    ("condition", "SourceAttackingAlone"): T_condition__SourceAttackingAlone,
    ("condition", "SourceEnteredThisTurn"): T_condition__SourceEnteredThisTurn,
    ("condition", "SourceHasCounterAtLeast"): T_condition__SourceHasCounterAtLeast,
    ("condition", "SourceHasDealtDamage"): T_condition__SourceHasDealtDamage,
    ("condition", "SourceHasNoCounter"): T_condition__SourceHasNoCounter,
    ("condition", "SourceInZone"): T_condition__SourceInZone,
    ("condition", "SourceIsAttacking"): T_condition__SourceIsAttacking,
    ("condition", "SourceIsBlocked"): T_condition__SourceIsBlocked,
    ("condition", "SourceIsColor"): T_condition__SourceIsColor,
    ("condition", "SourceIsCreature"): T_condition__SourceIsCreature,
    ("condition", "SourceIsEnchanted"): T_condition__SourceIsEnchanted,
    ("condition", "SourceIsEquipped"): T_condition__SourceIsEquipped,
    ("condition", "SourceIsHarnessed"): T_condition__SourceIsHarnessed,
    ("condition", "SourceIsMonstrous"): T_condition__SourceIsMonstrous,
    ("condition", "SourceIsPaired"): T_condition__SourceIsPaired,
    ("condition", "SourceIsTapped"): T_condition__SourceIsTapped,
    ("condition", "SourceLacksKeyword"): T_condition__SourceLacksKeyword,
    ("condition", "SourceMatchesFilter"): T_condition__SourceMatchesFilter,
    ("condition", "SourcePowerAtLeast"): T_condition__SourcePowerAtLeast,
    ("condition", "SourceTappedState"): T_condition__SourceTappedState,
    ("condition", "SourceUntappedAttachedTo"): T_condition__SourceUntappedAttachedTo,
    ("condition", "SpeedGE"): T_condition__SpeedGE,
    ("condition", "SpellTargetsFilter"): T_condition__SpellTargetsFilter,
    ("condition", "Static"): T_condition__Static,
    ("condition", "TargetHasKeywordInstead"): T_condition__TargetHasKeywordInstead,
    ("condition", "TargetMatchesFilter"): T_condition__TargetMatchesFilter,
    (
        "condition",
        "TargetSharesNameWithOtherExiledThisWay",
    ): T_condition__TargetSharesNameWithOtherExiledThisWay,
    ("condition", "TokenCoreTypeMatches"): T_condition__TokenCoreTypeMatches,
    ("condition", "TokenSubtypeMatches"): T_condition__TokenSubtypeMatches,
    ("condition", "TributeNotPaid"): T_condition__TributeNotPaid,
    (
        "condition",
        "TriggeringSpellTargetsFilter",
    ): T_condition__TriggeringSpellTargetsFilter,
    (
        "condition",
        "UnlessControlsCountMatching",
    ): T_condition__UnlessControlsCountMatching,
    ("condition", "UnlessControlsMatching"): T_condition__UnlessControlsMatching,
    ("condition", "UnlessControlsOtherLeq"): T_condition__UnlessControlsOtherLeq,
    ("condition", "UnlessControlsSubtype"): T_condition__UnlessControlsSubtype,
    ("condition", "UnlessMultipleOpponents"): T_condition__UnlessMultipleOpponents,
    ("condition", "UnlessPay"): T_condition__UnlessPay,
    ("condition", "UnlessPlayerLifeAtMost"): T_condition__UnlessPlayerLifeAtMost,
    ("condition", "UnlessQuantity"): T_condition__UnlessQuantity,
    ("condition", "UnlessYourTurn"): T_condition__UnlessYourTurn,
    ("condition", "Unrecognized"): T_condition__Unrecognized,
    ("condition", "WasCast"): T_condition__WasCast,
    ("condition", "WasPlayed"): T_condition__WasPlayed,
    ("condition", "WasStartingPlayer"): T_condition__WasStartingPlayer,
    ("condition", "WasType"): T_condition__WasType,
    ("condition", "WhenDies"): T_condition__WhenDies,
    ("condition", "WhenDiesOrExiled"): T_condition__WhenDiesOrExiled,
    ("condition", "WhenEntersBattlefield"): T_condition__WhenEntersBattlefield,
    ("condition", "WhenLeavesPlayFiltered"): T_condition__WhenLeavesPlayFiltered,
    ("condition", "WhenNextEvent"): T_condition__WhenNextEvent,
    ("condition", "WhenYouDo"): T_condition__WhenYouDo,
    ("condition", "WheneverEvent"): T_condition__WheneverEvent,
    ("condition", "YouAttackedThisTurn"): T_condition__YouAttackedThisTurn,
    ("condition", "YouAttackedWithAtLeast"): T_condition__YouAttackedWithAtLeast,
    ("condition", "YouCastSpellCountAtLeast"): T_condition__YouCastSpellCountAtLeast,
    ("condition", "YouCastSpellThisTurn"): T_condition__YouCastSpellThisTurn,
    (
        "condition",
        "YouControlAnotherColorlessCreature",
    ): T_condition__YouControlAnotherColorlessCreature,
    (
        "condition",
        "YouControlColorPermanentCountAtLeast",
    ): T_condition__YouControlColorPermanentCountAtLeast,
    (
        "condition",
        "YouControlCoreTypeCountAtLeast",
    ): T_condition__YouControlCoreTypeCountAtLeast,
    (
        "condition",
        "YouControlCreatureWithPowerAtLeast",
    ): T_condition__YouControlCreatureWithPowerAtLeast,
    ("condition", "YouControlCreatureWithPt"): T_condition__YouControlCreatureWithPt,
    (
        "condition",
        "YouControlDifferentPowerCreatureCountAtLeast",
    ): T_condition__YouControlDifferentPowerCreatureCountAtLeast,
    ("condition", "YouControlLandSubtypeAny"): T_condition__YouControlLandSubtypeAny,
    (
        "condition",
        "YouControlLandsWithSameNameAtLeast",
    ): T_condition__YouControlLandsWithSameNameAtLeast,
    (
        "condition",
        "YouControlLegendaryCreature",
    ): T_condition__YouControlLegendaryCreature,
    (
        "condition",
        "YouControlNamedPlaneswalker",
    ): T_condition__YouControlNamedPlaneswalker,
    ("condition", "YouControlNoCreatures"): T_condition__YouControlNoCreatures,
    (
        "condition",
        "YouControlSnowPermanentCountAtLeast",
    ): T_condition__YouControlSnowPermanentCountAtLeast,
    (
        "condition",
        "YouControlSubtypeCountAtLeast",
    ): T_condition__YouControlSubtypeCountAtLeast,
    ("condition", "YouCreatedTokenThisTurn"): T_condition__YouCreatedTokenThisTurn,
    ("condition", "YouDiscardedCardThisTurn"): T_condition__YouDiscardedCardThisTurn,
    ("condition", "YouGainedLifeThisTurn"): T_condition__YouGainedLifeThisTurn,
    (
        "condition",
        "YouHadArtifactEnterThisTurn",
    ): T_condition__YouHadArtifactEnterThisTurn,
    ("condition", "YouPlayedLandThisTurn"): T_condition__YouPlayedLandThisTurn,
    (
        "condition",
        "YouSacrificedArtifactThisTurn",
    ): T_condition__YouSacrificedArtifactThisTurn,
    ("condition", "ZoneCardCountAtLeast"): T_condition__ZoneCardCountAtLeast,
    ("condition", "ZoneCardTypeCountAtLeast"): T_condition__ZoneCardTypeCountAtLeast,
    ("condition", "ZoneChangeObjectIsTapped"): T_condition__ZoneChangeObjectIsTapped,
    (
        "condition",
        "ZoneChangeObjectMatchesFilter",
    ): T_condition__ZoneChangeObjectMatchesFilter,
    ("condition", "ZoneChangedThisWay"): T_condition__ZoneChangedThisWay,
    (
        "condition",
        "ZoneCoreTypeCardCountAtLeast",
    ): T_condition__ZoneCoreTypeCardCountAtLeast,
    (
        "condition",
        "ZoneSubtypeCardCountAtLeast",
    ): T_condition__ZoneSubtypeCardCountAtLeast,
    (
        "conditional_enter_with_counters",
        "Fixed",
    ): T_conditional_enter_with_counters__Fixed,
    (
        "conditional_enter_with_counters",
        "Typed",
    ): T_conditional_enter_with_counters__Typed,
    ("conditions", "AdditionalCostPaid"): T_conditions__AdditionalCostPaid,
    ("conditions", "And"): T_conditions__And,
    ("conditions", "AttackersDeclaredCount"): T_conditions__AttackersDeclaredCount,
    ("conditions", "CastFromZone"): T_conditions__CastFromZone,
    ("conditions", "CastVariantPaid"): T_conditions__CastVariantPaid,
    (
        "conditions",
        "CastVariantPaidPersistent",
    ): T_conditions__CastVariantPaidPersistent,
    ("conditions", "ChosenLabelIs"): T_conditions__ChosenLabelIs,
    ("conditions", "ClassLevelGE"): T_conditions__ClassLevelGE,
    ("conditions", "ControlCount"): T_conditions__ControlCount,
    (
        "conditions",
        "ControllerControlsMatching",
    ): T_conditions__ControllerControlsMatching,
    ("conditions", "ControlsType"): T_conditions__ControlsType,
    ("conditions", "CurrentPhaseIs"): T_conditions__CurrentPhaseIs,
    ("conditions", "DuringPlayersTurn"): T_conditions__DuringPlayersTurn,
    ("conditions", "DuringYourTurn"): T_conditions__DuringYourTurn,
    ("conditions", "EffectOutcome"): T_conditions__EffectOutcome,
    ("conditions", "FirstCombatPhaseOfTurn"): T_conditions__FirstCombatPhaseOfTurn,
    ("conditions", "HasCounters"): T_conditions__HasCounters,
    ("conditions", "HasObjectTarget"): T_conditions__HasObjectTarget,
    ("conditions", "IsPresent"): T_conditions__IsPresent,
    ("conditions", "IsYourTurn"): T_conditions__IsYourTurn,
    ("conditions", "ManaColorSpent"): T_conditions__ManaColorSpent,
    ("conditions", "ManaSpentCondition"): T_conditions__ManaSpentCondition,
    ("conditions", "Not"): T_conditions__Not,
    ("conditions", "OpponentPoisonAtLeast"): T_conditions__OpponentPoisonAtLeast,
    ("conditions", "Or"): T_conditions__Or,
    ("conditions", "QuantityCheck"): T_conditions__QuantityCheck,
    ("conditions", "QuantityComparison"): T_conditions__QuantityComparison,
    ("conditions", "ScopedPlayerMatches"): T_conditions__ScopedPlayerMatches,
    ("conditions", "SourceEnteredThisTurn"): T_conditions__SourceEnteredThisTurn,
    ("conditions", "SourceInZone"): T_conditions__SourceInZone,
    ("conditions", "SourceIsAttacking"): T_conditions__SourceIsAttacking,
    ("conditions", "SourceIsBlocking"): T_conditions__SourceIsBlocking,
    ("conditions", "SourceIsTapped"): T_conditions__SourceIsTapped,
    ("conditions", "SourceLacksKeyword"): T_conditions__SourceLacksKeyword,
    ("conditions", "SourceMatchesFilter"): T_conditions__SourceMatchesFilter,
    (
        "conditions",
        "SpellCastWithVariantThisTurn",
    ): T_conditions__SpellCastWithVariantThisTurn,
    ("conditions", "TargetHasKeywordInstead"): T_conditions__TargetHasKeywordInstead,
    ("conditions", "TargetMatchesFilter"): T_conditions__TargetMatchesFilter,
    (
        "conditions",
        "TriggeringSpellMatchesFilter",
    ): T_conditions__TriggeringSpellMatchesFilter,
    ("conditions", "UnlessPay"): T_conditions__UnlessPay,
    ("conditions", "Unrecognized"): T_conditions__Unrecognized,
    ("conditions", "WasCast"): T_conditions__WasCast,
    (
        "conditions",
        "YouControlSubtypeCountAtLeast",
    ): T_conditions__YouControlSubtypeCountAtLeast,
    (
        "conditions",
        "ZoneChangeObjectMatchesFilter",
    ): T_conditions__ZoneChangeObjectMatchesFilter,
    ("conditions", "ZoneChangedThisWay"): T_conditions__ZoneChangedThisWay,
    ("constraint", "AtClassLevel"): T_constraint__AtClassLevel,
    ("constraint", "DistinctCardTypes"): T_constraint__DistinctCardTypes,
    ("constraint", "EventSourceControlledBy"): T_constraint__EventSourceControlledBy,
    ("constraint", "ManaValue"): T_constraint__ManaValue,
    ("constraint", "MaxTimesPerTurn"): T_constraint__MaxTimesPerTurn,
    ("constraint", "NthDrawThisTurn"): T_constraint__NthDrawThisTurn,
    ("constraint", "NthSpellThisTurn"): T_constraint__NthSpellThisTurn,
    ("constraint", "OncePerGame"): T_constraint__OncePerGame,
    ("constraint", "OncePerOpponentPerTurn"): T_constraint__OncePerOpponentPerTurn,
    ("constraint", "OncePerTurn"): T_constraint__OncePerTurn,
    ("constraint", "OnlyDuringOpponentsTurn"): T_constraint__OnlyDuringOpponentsTurn,
    ("constraint", "OnlyDuringYourMainPhase"): T_constraint__OnlyDuringYourMainPhase,
    ("constraint", "OnlyDuringYourTurn"): T_constraint__OnlyDuringYourTurn,
    ("constraints", "ConditionalMaxChoices"): T_constraints__ConditionalMaxChoices,
    ("constraints", "DifferentTargetPlayers"): T_constraints__DifferentTargetPlayers,
    ("constraints", "NoRepeatThisGame"): T_constraints__NoRepeatThisGame,
    ("constraints", "NoRepeatThisTurn"): T_constraints__NoRepeatThisTurn,
    ("copy_modifications", "RemoveSupertype"): T_copy_modifications__RemoveSupertype,
    ("cost", "Behold"): T_cost__Behold,
    ("cost", "Blight"): T_cost__Blight,
    ("cost", "CollectEvidence"): T_cost__CollectEvidence,
    ("cost", "Composite"): T_cost__Composite,
    ("cost", "Cost"): T_cost__Cost,
    ("cost", "Discard"): T_cost__Discard,
    ("cost", "EffectCost"): T_cost__EffectCost,
    ("cost", "Exile"): T_cost__Exile,
    ("cost", "ExileWithAggregate"): T_cost__ExileWithAggregate,
    ("cost", "Loyalty"): T_cost__Loyalty,
    ("cost", "Mana"): T_cost__Mana,
    ("cost", "ManaDynamic"): T_cost__ManaDynamic,
    ("cost", "Mill"): T_cost__Mill,
    ("cost", "NinjutsuFamily"): T_cost__NinjutsuFamily,
    ("cost", "OneOf"): T_cost__OneOf,
    ("cost", "PayEnergy"): T_cost__PayEnergy,
    ("cost", "PayLife"): T_cost__PayLife,
    ("cost", "PaySpeed"): T_cost__PaySpeed,
    ("cost", "PerCounter"): T_cost__PerCounter,
    ("cost", "RemoveCounter"): T_cost__RemoveCounter,
    ("cost", "ReturnToHand"): T_cost__ReturnToHand,
    ("cost", "Reveal"): T_cost__Reveal,
    ("cost", "Sacrifice"): T_cost__Sacrifice,
    ("cost", "SelfManaCost"): T_cost__SelfManaCost,
    ("cost", "Tap"): T_cost__Tap,
    ("cost", "TapCreatures"): T_cost__TapCreatures,
    ("cost", "Unimplemented"): T_cost__Unimplemented,
    ("cost", "Waterbend"): T_cost__Waterbend,
    ("costs", "Behold"): T_costs__Behold,
    ("costs", "Blight"): T_costs__Blight,
    ("costs", "CollectEvidence"): T_costs__CollectEvidence,
    ("costs", "Composite"): T_costs__Composite,
    ("costs", "Cost"): T_costs__Cost,
    ("costs", "Discard"): T_costs__Discard,
    ("costs", "EffectCost"): T_costs__EffectCost,
    ("costs", "Exert"): T_costs__Exert,
    ("costs", "Exile"): T_costs__Exile,
    ("costs", "ExileMaterials"): T_costs__ExileMaterials,
    ("costs", "Mana"): T_costs__Mana,
    ("costs", "Mill"): T_costs__Mill,
    ("costs", "OneOf"): T_costs__OneOf,
    ("costs", "PayEnergy"): T_costs__PayEnergy,
    ("costs", "PayLife"): T_costs__PayLife,
    ("costs", "RemoveCounter"): T_costs__RemoveCounter,
    ("costs", "ReturnToHand"): T_costs__ReturnToHand,
    ("costs", "Reveal"): T_costs__Reveal,
    ("costs", "Sacrifice"): T_costs__Sacrifice,
    ("costs", "Tap"): T_costs__Tap,
    ("costs", "TapCreatures"): T_costs__TapCreatures,
    ("costs", "Unattach"): T_costs__Unattach,
    ("costs", "UnattachFrom"): T_costs__UnattachFrom,
    ("costs", "Unimplemented"): T_costs__Unimplemented,
    ("costs", "Untap"): T_costs__Untap,
    ("costs", "Waterbend"): T_costs__Waterbend,
    ("count", "AtLeast"): T_count__AtLeast,
    ("count", "ClampMin"): T_count__ClampMin,
    ("count", "Difference"): T_count__Difference,
    ("count", "DivideRounded"): T_count__DivideRounded,
    ("count", "Exactly"): T_count__Exactly,
    ("count", "Fixed"): T_count__Fixed,
    ("count", "Max"): T_count__Max,
    ("count", "Multiply"): T_count__Multiply,
    ("count", "Offset"): T_count__Offset,
    ("count", "Power"): T_count__Power,
    ("count", "Ref"): T_count__Ref,
    ("count", "Sum"): T_count__Sum,
    ("count", "UpTo"): T_count__UpTo,
    ("counter_match", "OfType"): T_counter_match__OfType,
    ("counter_type", "Any"): T_counter_type__Any,
    ("counter_type", "OfType"): T_counter_type__OfType,
    ("countered_spell_zone", "Hand"): T_countered_spell_zone__Hand,
    ("countered_spell_zone", "Library"): T_countered_spell_zone__Library,
    ("counters", "Any"): T_counters__Any,
    ("counters", "OfType"): T_counters__OfType,
    ("damage_modification", "Double"): T_damage_modification__Double,
    ("damage_modification", "LifeFloor"): T_damage_modification__LifeFloor,
    ("damage_modification", "Minus"): T_damage_modification__Minus,
    ("damage_modification", "Plus"): T_damage_modification__Plus,
    (
        "damage_modification",
        "SetToSourcePower",
    ): T_damage_modification__SetToSourcePower,
    ("damage_modification", "Triple"): T_damage_modification__Triple,
    ("damage_source_filter", "And"): T_damage_source_filter__And,
    ("damage_source_filter", "AttachedTo"): T_damage_source_filter__AttachedTo,
    (
        "damage_source_filter",
        "ChosenDamageSource",
    ): T_damage_source_filter__ChosenDamageSource,
    ("damage_source_filter", "Or"): T_damage_source_filter__Or,
    ("damage_source_filter", "ParentTarget"): T_damage_source_filter__ParentTarget,
    ("damage_source_filter", "SelfRef"): T_damage_source_filter__SelfRef,
    ("damage_source_filter", "StackSpell"): T_damage_source_filter__StackSpell,
    ("damage_source_filter", "Typed"): T_damage_source_filter__Typed,
    ("data", "Any"): T_data__Any,
    ("data", "Behold"): T_data__Behold,
    ("data", "Blight"): T_data__Blight,
    ("data", "Composite"): T_data__Composite,
    ("data", "Cost"): T_data__Cost,
    ("data", "Discard"): T_data__Discard,
    ("data", "DiscardCard"): T_data__DiscardCard,
    ("data", "EffectCost"): T_data__EffectCost,
    ("data", "Exile"): T_data__Exile,
    ("data", "Mana"): T_data__Mana,
    ("data", "OneOf"): T_data__OneOf,
    ("data", "ParentTarget"): T_data__ParentTarget,
    ("data", "PayLife"): T_data__PayLife,
    ("data", "ReturnToHand"): T_data__ReturnToHand,
    ("data", "Reveal"): T_data__Reveal,
    ("data", "Sacrifice"): T_data__Sacrifice,
    ("data", "SelfManaCost"): T_data__SelfManaCost,
    ("data", "TapCreatures"): T_data__TapCreatures,
    ("data", "TriggeringSource"): T_data__TriggeringSource,
    ("data", "Unimplemented"): T_data__Unimplemented,
    ("data", "Waterbend"): T_data__Waterbend,
    ("deck_copy_limit", "Unlimited"): T_deck_copy_limit__Unlimited,
    ("deck_copy_limit", "UpTo"): T_deck_copy_limit__UpTo,
    ("depth", "Ref"): T_depth__Ref,
    ("destination_constraint", "NotEquals"): T_destination_constraint__NotEquals,
    ("direction", "Decrease"): T_direction__Decrease,
    ("direction", "Left"): T_direction__Left,
    ("direction", "Right"): T_direction__Right,
    ("distribute", "Counters"): T_distribute__Counters,
    ("distribute", "Damage"): T_distribute__Damage,
    ("distribute", "EvenSplitDamage"): T_distribute__EvenSplitDamage,
    ("duplicate_of", "And"): T_duplicate_of__And,
    ("duplicate_of", "ParentTarget"): T_duplicate_of__ParentTarget,
    ("duplicate_of", "StackSpell"): T_duplicate_of__StackSpell,
    ("duplicate_of", "Typed"): T_duplicate_of__Typed,
    ("dynamic_count", "Aggregate"): T_dynamic_count__Aggregate,
    ("dynamic_count", "AttackedThisTurn"): T_dynamic_count__AttackedThisTurn,
    ("dynamic_count", "BasicLandTypeCount"): T_dynamic_count__BasicLandTypeCount,
    (
        "dynamic_count",
        "CardsDiscardedThisTurn",
    ): T_dynamic_count__CardsDiscardedThisTurn,
    ("dynamic_count", "CardsDrawnThisTurn"): T_dynamic_count__CardsDrawnThisTurn,
    ("dynamic_count", "CountersOn"): T_dynamic_count__CountersOn,
    ("dynamic_count", "DamageDealtThisTurn"): T_dynamic_count__DamageDealtThisTurn,
    ("dynamic_count", "Devotion"): T_dynamic_count__Devotion,
    ("dynamic_count", "DistinctCardTypes"): T_dynamic_count__DistinctCardTypes,
    (
        "dynamic_count",
        "DistinctColorsAmongPermanents",
    ): T_dynamic_count__DistinctColorsAmongPermanents,
    (
        "dynamic_count",
        "FilteredTrackedSetSize",
    ): T_dynamic_count__FilteredTrackedSetSize,
    ("dynamic_count", "LifeGainedThisTurn"): T_dynamic_count__LifeGainedThisTurn,
    ("dynamic_count", "LifeLostThisTurn"): T_dynamic_count__LifeLostThisTurn,
    ("dynamic_count", "ObjectCount"): T_dynamic_count__ObjectCount,
    ("dynamic_count", "ObjectCountDistinct"): T_dynamic_count__ObjectCountDistinct,
    ("dynamic_count", "PartySize"): T_dynamic_count__PartySize,
    ("dynamic_count", "PlayerCount"): T_dynamic_count__PlayerCount,
    ("dynamic_count", "PlayerCounter"): T_dynamic_count__PlayerCounter,
    ("dynamic_count", "Power"): T_dynamic_count__Power,
    ("dynamic_count", "PreviousEffectAmount"): T_dynamic_count__PreviousEffectAmount,
    ("dynamic_count", "Speed"): T_dynamic_count__Speed,
    ("dynamic_count", "SpellsCastThisTurn"): T_dynamic_count__SpellsCastThisTurn,
    ("dynamic_count", "TrackedSetSize"): T_dynamic_count__TrackedSetSize,
    ("dynamic_count", "ZoneCardCount"): T_dynamic_count__ZoneCardCount,
    (
        "dynamic_count",
        "ZoneChangeCountThisTurn",
    ): T_dynamic_count__ZoneChangeCountThisTurn,
    ("dynamic_max_choices", "Ref"): T_dynamic_max_choices__Ref,
    ("effect", "Adapt"): T_effect__Adapt,
    ("effect", "AddPendingETBCounters"): T_effect__AddPendingETBCounters,
    (
        "effect",
        "AddPendingEntersModifications",
    ): T_effect__AddPendingEntersModifications,
    ("effect", "AddRestriction"): T_effect__AddRestriction,
    ("effect", "AddTargetReplacement"): T_effect__AddTargetReplacement,
    ("effect", "AdditionalPhase"): T_effect__AdditionalPhase,
    ("effect", "Amass"): T_effect__Amass,
    ("effect", "Animate"): T_effect__Animate,
    ("effect", "ApplyPerpetual"): T_effect__ApplyPerpetual,
    ("effect", "AssembleContraptions"): T_effect__AssembleContraptions,
    ("effect", "Attach"): T_effect__Attach,
    ("effect", "BecomeBlocked"): T_effect__BecomeBlocked,
    ("effect", "BecomeCopy"): T_effect__BecomeCopy,
    ("effect", "BecomeMonarch"): T_effect__BecomeMonarch,
    ("effect", "BecomePrepared"): T_effect__BecomePrepared,
    ("effect", "BecomeSaddled"): T_effect__BecomeSaddled,
    ("effect", "BecomeUnprepared"): T_effect__BecomeUnprepared,
    ("effect", "Behold"): T_effect__Behold,
    ("effect", "BlightEffect"): T_effect__BlightEffect,
    ("effect", "Bolster"): T_effect__Bolster,
    ("effect", "Bounce"): T_effect__Bounce,
    ("effect", "BounceAll"): T_effect__BounceAll,
    ("effect", "CastCopyOfCard"): T_effect__CastCopyOfCard,
    ("effect", "CastFromZone"): T_effect__CastFromZone,
    ("effect", "ChangeSpeed"): T_effect__ChangeSpeed,
    ("effect", "ChangeTargets"): T_effect__ChangeTargets,
    ("effect", "ChangeZone"): T_effect__ChangeZone,
    ("effect", "ChangeZoneAll"): T_effect__ChangeZoneAll,
    ("effect", "ChaosEnsues"): T_effect__ChaosEnsues,
    ("effect", "Choose"): T_effect__Choose,
    ("effect", "ChooseAndSacrificeRest"): T_effect__ChooseAndSacrificeRest,
    (
        "effect",
        "ChooseAugmentAndCombineWithHost",
    ): T_effect__ChooseAugmentAndCombineWithHost,
    ("effect", "ChooseCounterAdjustment"): T_effect__ChooseCounterAdjustment,
    ("effect", "ChooseCounterKind"): T_effect__ChooseCounterKind,
    (
        "effect",
        "ChooseDrawnThisTurnPayOrTopdeck",
    ): T_effect__ChooseDrawnThisTurnPayOrTopdeck,
    ("effect", "ChooseFromZone"): T_effect__ChooseFromZone,
    ("effect", "ChooseObjectsIntoTrackedSet"): T_effect__ChooseObjectsIntoTrackedSet,
    ("effect", "ChooseOneOf"): T_effect__ChooseOneOf,
    ("effect", "Clash"): T_effect__Clash,
    ("effect", "Cloak"): T_effect__Cloak,
    ("effect", "CollectEvidence"): T_effect__CollectEvidence,
    ("effect", "CombineHost"): T_effect__CombineHost,
    ("effect", "Conjure"): T_effect__Conjure,
    ("effect", "Connive"): T_effect__Connive,
    ("effect", "ControlNextTurn"): T_effect__ControlNextTurn,
    ("effect", "CopySpell"): T_effect__CopySpell,
    ("effect", "CopyTokenBlockingAttacker"): T_effect__CopyTokenBlockingAttacker,
    ("effect", "CopyTokenOf"): T_effect__CopyTokenOf,
    ("effect", "Counter"): T_effect__Counter,
    ("effect", "CounterAll"): T_effect__CounterAll,
    ("effect", "CreateDamageReplacement"): T_effect__CreateDamageReplacement,
    ("effect", "CreateDelayedTrigger"): T_effect__CreateDelayedTrigger,
    ("effect", "CreateDrawReplacement"): T_effect__CreateDrawReplacement,
    ("effect", "CreateEmblem"): T_effect__CreateEmblem,
    ("effect", "CreatePlaneswalkReplacement"): T_effect__CreatePlaneswalkReplacement,
    ("effect", "DamageAll"): T_effect__DamageAll,
    ("effect", "DamageEachPlayer"): T_effect__DamageEachPlayer,
    ("effect", "DealDamage"): T_effect__DealDamage,
    ("effect", "Destroy"): T_effect__Destroy,
    ("effect", "DestroyAll"): T_effect__DestroyAll,
    ("effect", "Detain"): T_effect__Detain,
    ("effect", "Dig"): T_effect__Dig,
    ("effect", "Discard"): T_effect__Discard,
    ("effect", "DiscardCard"): T_effect__DiscardCard,
    ("effect", "Discover"): T_effect__Discover,
    ("effect", "Double"): T_effect__Double,
    ("effect", "DoublePT"): T_effect__DoublePT,
    ("effect", "DoublePTAll"): T_effect__DoublePTAll,
    ("effect", "DraftFromSpellbook"): T_effect__DraftFromSpellbook,
    ("effect", "Draw"): T_effect__Draw,
    ("effect", "EachDealsDamageEqualToPower"): T_effect__EachDealsDamageEqualToPower,
    ("effect", "EachPlayerCopyChosen"): T_effect__EachPlayerCopyChosen,
    ("effect", "EachSourceDealsDamage"): T_effect__EachSourceDealsDamage,
    ("effect", "Encore"): T_effect__Encore,
    ("effect", "EndCombatPhase"): T_effect__EndCombatPhase,
    ("effect", "EndTheTurn"): T_effect__EndTheTurn,
    ("effect", "Endure"): T_effect__Endure,
    ("effect", "ExchangeControl"): T_effect__ExchangeControl,
    ("effect", "ExchangeLifeTotals"): T_effect__ExchangeLifeTotals,
    ("effect", "ExchangeLifeWithStat"): T_effect__ExchangeLifeWithStat,
    ("effect", "ExileFromTopUntil"): T_effect__ExileFromTopUntil,
    ("effect", "ExileHaunting"): T_effect__ExileHaunting,
    (
        "effect",
        "ExileResolvingSpellInsteadOfGraveyard",
    ): T_effect__ExileResolvingSpellInsteadOfGraveyard,
    ("effect", "ExileTop"): T_effect__ExileTop,
    ("effect", "Explore"): T_effect__Explore,
    ("effect", "ExploreAll"): T_effect__ExploreAll,
    ("effect", "ExtraTurn"): T_effect__ExtraTurn,
    ("effect", "Fight"): T_effect__Fight,
    ("effect", "FlipCoin"): T_effect__FlipCoin,
    ("effect", "FlipCoinUntilLose"): T_effect__FlipCoinUntilLose,
    ("effect", "FlipCoins"): T_effect__FlipCoins,
    ("effect", "ForEachCategory"): T_effect__ForEachCategory,
    ("effect", "Forage"): T_effect__Forage,
    ("effect", "ForceAttack"): T_effect__ForceAttack,
    ("effect", "ForceBlock"): T_effect__ForceBlock,
    ("effect", "FreeCastFromZones"): T_effect__FreeCastFromZones,
    (
        "effect",
        "GainActivatedAbilitiesOfTarget",
    ): T_effect__GainActivatedAbilitiesOfTarget,
    ("effect", "GainControl"): T_effect__GainControl,
    ("effect", "GainControlAll"): T_effect__GainControlAll,
    ("effect", "GainEnergy"): T_effect__GainEnergy,
    ("effect", "GainLife"): T_effect__GainLife,
    ("effect", "GenericEffect"): T_effect__GenericEffect,
    ("effect", "GiftDelivery"): T_effect__GiftDelivery,
    ("effect", "GiveControl"): T_effect__GiveControl,
    ("effect", "GivePlayerCounter"): T_effect__GivePlayerCounter,
    ("effect", "Goad"): T_effect__Goad,
    ("effect", "GoadAll"): T_effect__GoadAll,
    ("effect", "GrantCastingPermission"): T_effect__GrantCastingPermission,
    ("effect", "GrantExtraLoyaltyActivations"): T_effect__GrantExtraLoyaltyActivations,
    ("effect", "GrantNextSpellAbility"): T_effect__GrantNextSpellAbility,
    ("effect", "Harness"): T_effect__Harness,
    ("effect", "Heist"): T_effect__Heist,
    ("effect", "HideawayConceal"): T_effect__HideawayConceal,
    ("effect", "Incubate"): T_effect__Incubate,
    ("effect", "Intensify"): T_effect__Intensify,
    ("effect", "Investigate"): T_effect__Investigate,
    ("effect", "Learn"): T_effect__Learn,
    ("effect", "LoseAllPlayerCounters"): T_effect__LoseAllPlayerCounters,
    ("effect", "LoseLife"): T_effect__LoseLife,
    ("effect", "LoseTheGame"): T_effect__LoseTheGame,
    ("effect", "MadnessCast"): T_effect__MadnessCast,
    ("effect", "Mana"): T_effect__Mana,
    ("effect", "Manifest"): T_effect__Manifest,
    ("effect", "ManifestDread"): T_effect__ManifestDread,
    ("effect", "Meld"): T_effect__Meld,
    ("effect", "Mill"): T_effect__Mill,
    ("effect", "Monstrosity"): T_effect__Monstrosity,
    ("effect", "MoveCounters"): T_effect__MoveCounters,
    ("effect", "MultiplyCounter"): T_effect__MultiplyCounter,
    ("effect", "Myriad"): T_effect__Myriad,
    ("effect", "NoOp"): T_effect__NoOp,
    ("effect", "OpenAttractions"): T_effect__OpenAttractions,
    ("effect", "OpponentGuess"): T_effect__OpponentGuess,
    ("effect", "PairWith"): T_effect__PairWith,
    ("effect", "PayCost"): T_effect__PayCost,
    ("effect", "PhaseIn"): T_effect__PhaseIn,
    ("effect", "PhaseOut"): T_effect__PhaseOut,
    ("effect", "Planeswalk"): T_effect__Planeswalk,
    ("effect", "Populate"): T_effect__Populate,
    ("effect", "PreventDamage"): T_effect__PreventDamage,
    ("effect", "Proliferate"): T_effect__Proliferate,
    ("effect", "ProliferateTarget"): T_effect__ProliferateTarget,
    ("effect", "Pump"): T_effect__Pump,
    ("effect", "PumpAll"): T_effect__PumpAll,
    ("effect", "PutAtLibraryPosition"): T_effect__PutAtLibraryPosition,
    ("effect", "PutChosenCounter"): T_effect__PutChosenCounter,
    ("effect", "PutCounter"): T_effect__PutCounter,
    ("effect", "PutCounterAll"): T_effect__PutCounterAll,
    ("effect", "PutOnTopOrBottom"): T_effect__PutOnTopOrBottom,
    ("effect", "PutSticker"): T_effect__PutSticker,
    ("effect", "ReassembleContraption"): T_effect__ReassembleContraption,
    ("effect", "RedistributeLifeTotals"): T_effect__RedistributeLifeTotals,
    ("effect", "ReduceNextSpellCost"): T_effect__ReduceNextSpellCost,
    ("effect", "Regenerate"): T_effect__Regenerate,
    ("effect", "RegisterBending"): T_effect__RegisterBending,
    ("effect", "RememberCard"): T_effect__RememberCard,
    ("effect", "RemoveAllDamage"): T_effect__RemoveAllDamage,
    ("effect", "RemoveCounter"): T_effect__RemoveCounter,
    ("effect", "RemoveFromCombat"): T_effect__RemoveFromCombat,
    ("effect", "Renown"): T_effect__Renown,
    ("effect", "ReturnAsAura"): T_effect__ReturnAsAura,
    ("effect", "Reveal"): T_effect__Reveal,
    ("effect", "RevealFromHand"): T_effect__RevealFromHand,
    ("effect", "RevealHand"): T_effect__RevealHand,
    ("effect", "RevealTop"): T_effect__RevealTop,
    ("effect", "RevealUntil"): T_effect__RevealUntil,
    ("effect", "ReverseTurnOrder"): T_effect__ReverseTurnOrder,
    ("effect", "RingTemptsYou"): T_effect__RingTemptsYou,
    ("effect", "RollDie"): T_effect__RollDie,
    ("effect", "RollToVisitAttractions"): T_effect__RollToVisitAttractions,
    ("effect", "RuntimeHandled"): T_effect__RuntimeHandled,
    ("effect", "Sacrifice"): T_effect__Sacrifice,
    ("effect", "Scry"): T_effect__Scry,
    ("effect", "SearchLibrary"): T_effect__SearchLibrary,
    ("effect", "SearchOutsideGame"): T_effect__SearchOutsideGame,
    ("effect", "Seek"): T_effect__Seek,
    ("effect", "SeparateIntoPiles"): T_effect__SeparateIntoPiles,
    ("effect", "SetClassLevel"): T_effect__SetClassLevel,
    ("effect", "SetDayNight"): T_effect__SetDayNight,
    ("effect", "SetLifeTotal"): T_effect__SetLifeTotal,
    ("effect", "SetRoomDoorLock"): T_effect__SetRoomDoorLock,
    ("effect", "SetTapState"): T_effect__SetTapState,
    ("effect", "Shuffle"): T_effect__Shuffle,
    ("effect", "SkipNextStep"): T_effect__SkipNextStep,
    ("effect", "SkipNextTurn"): T_effect__SkipNextTurn,
    ("effect", "SolveCase"): T_effect__SolveCase,
    ("effect", "Specialize"): T_effect__Specialize,
    ("effect", "StartYourEngines"): T_effect__StartYourEngines,
    ("effect", "Surveil"): T_effect__Surveil,
    ("effect", "Suspect"): T_effect__Suspect,
    ("effect", "SwapChosenLabels"): T_effect__SwapChosenLabels,
    ("effect", "SwitchPT"): T_effect__SwitchPT,
    ("effect", "TakeTheInitiative"): T_effect__TakeTheInitiative,
    ("effect", "TargetOnly"): T_effect__TargetOnly,
    ("effect", "TimeTravel"): T_effect__TimeTravel,
    ("effect", "Token"): T_effect__Token,
    ("effect", "Transform"): T_effect__Transform,
    ("effect", "Tribute"): T_effect__Tribute,
    ("effect", "TurnFaceDown"): T_effect__TurnFaceDown,
    ("effect", "TurnFaceUp"): T_effect__TurnFaceUp,
    ("effect", "UnattachAll"): T_effect__UnattachAll,
    ("effect", "Unimplemented"): T_effect__Unimplemented,
    ("effect", "Unsuspect"): T_effect__Unsuspect,
    ("effect", "VentureIntoDungeon"): T_effect__VentureIntoDungeon,
    ("effect", "Vote"): T_effect__Vote,
    ("effect", "WinTheGame"): T_effect__WinTheGame,
    ("enchant_filter", "Typed"): T_enchant_filter__Typed,
    ("enter_with_counters", "ClampMin"): T_enter_with_counters__ClampMin,
    ("enter_with_counters", "Fixed"): T_enter_with_counters__Fixed,
    ("enter_with_counters", "Offset"): T_enter_with_counters__Offset,
    ("enter_with_counters", "Ref"): T_enter_with_counters__Ref,
    ("enters_modified_if", "Typed"): T_enters_modified_if__Typed,
    ("entwine_cost", "Cost"): T_entwine_cost__Cost,
    ("excess", "TargetController"): T_excess__TargetController,
    ("exclude", "CreatureTypes"): T_exclude__CreatureTypes,
    (
        "exclude",
        "ParentObjectTargetController",
    ): T_exclude__ParentObjectTargetController,
    ("exclude", "TriggeringPlayer"): T_exclude__TriggeringPlayer,
    ("expiry", "EndOfTurn"): T_expiry__EndOfTurn,
    ("exponent", "Ref"): T_exponent__Ref,
    ("exprs", "Fixed"): T_exprs__Fixed,
    ("exprs", "Multiply"): T_exprs__Multiply,
    ("exprs", "Ref"): T_exprs__Ref,
    ("extra_source", "Typed"): T_extra_source__Typed,
    ("filter", "All"): T_filter__All,
    ("filter", "And"): T_filter__And,
    ("filter", "Any"): T_filter__Any,
    ("filter", "Controller"): T_filter__Controller,
    ("filter", "ControlsCount"): T_filter__ControlsCount,
    ("filter", "ExiledBySource"): T_filter__ExiledBySource,
    ("filter", "GrantingObject"): T_filter__GrantingObject,
    ("filter", "HasChosenName"): T_filter__HasChosenName,
    ("filter", "HasLostTheGame"): T_filter__HasLostTheGame,
    ("filter", "Named"): T_filter__Named,
    ("filter", "Not"): T_filter__Not,
    ("filter", "Opponent"): T_filter__Opponent,
    ("filter", "OpponentAttacked"): T_filter__OpponentAttacked,
    ("filter", "OpponentDealtDamage"): T_filter__OpponentDealtDamage,
    ("filter", "OpponentGainedLife"): T_filter__OpponentGainedLife,
    ("filter", "OpponentLostLife"): T_filter__OpponentLostLife,
    (
        "filter",
        "OpponentOfTriggeringPlayerNotAttacked",
    ): T_filter__OpponentOfTriggeringPlayerNotAttacked,
    ("filter", "Or"): T_filter__Or,
    ("filter", "ParentTarget"): T_filter__ParentTarget,
    ("filter", "PerformedActionThisWay"): T_filter__PerformedActionThisWay,
    ("filter", "Player"): T_filter__Player,
    ("filter", "PlayerAttribute"): T_filter__PlayerAttribute,
    ("filter", "SelfRef"): T_filter__SelfRef,
    ("filter", "Typed"): T_filter__Typed,
    ("filters", "And"): T_filters__And,
    ("filters", "Any"): T_filters__Any,
    ("filters", "AttachedTo"): T_filters__AttachedTo,
    ("filters", "Controller"): T_filters__Controller,
    ("filters", "ExiledBySource"): T_filters__ExiledBySource,
    ("filters", "HasChosenName"): T_filters__HasChosenName,
    ("filters", "LastCreated"): T_filters__LastCreated,
    ("filters", "Not"): T_filters__Not,
    ("filters", "Or"): T_filters__Or,
    ("filters", "ParentTarget"): T_filters__ParentTarget,
    ("filters", "ParentTargetSlot"): T_filters__ParentTargetSlot,
    ("filters", "Player"): T_filters__Player,
    ("filters", "SelfRef"): T_filters__SelfRef,
    ("filters", "StackAbility"): T_filters__StackAbility,
    ("filters", "StackSpell"): T_filters__StackSpell,
    ("filters", "TrackedSet"): T_filters__TrackedSet,
    ("filters", "TriggeringPlayer"): T_filters__TriggeringPlayer,
    ("filters", "TriggeringSource"): T_filters__TriggeringSource,
    ("filters", "Typed"): T_filters__Typed,
    ("flipper", "Any"): T_flipper__Any,
    ("flipper", "TriggeringPlayer"): T_flipper__TriggeringPlayer,
    ("forced_to", "ParentTarget"): T_forced_to__ParentTarget,
    ("forced_to", "SelfRef"): T_forced_to__SelfRef,
    ("grantee", "ObjectOwner"): T_grantee__ObjectOwner,
    ("grantee", "ParentTargetController"): T_grantee__ParentTargetController,
    ("grants", "GrantAbility"): T_grants__GrantAbility,
    ("grants", "RemoveAllAbilities"): T_grants__RemoveAllAbilities,
    ("host", "TriggeringSource"): T_host__TriggeringSource,
    ("host", "Typed"): T_host__Typed,
    ("inner", "And"): T_inner__And,
    ("inner", "CastDuringPhase"): T_inner__CastDuringPhase,
    ("inner", "CastFromZone"): T_inner__CastFromZone,
    ("inner", "CastVariantPaid"): T_inner__CastVariantPaid,
    ("inner", "ClampMin"): T_inner__ClampMin,
    (
        "inner",
        "ControllerControlledMatchingAsCast",
    ): T_inner__ControllerControlledMatchingAsCast,
    ("inner", "CostPaidObjectMatchesFilter"): T_inner__CostPaidObjectMatchesFilter,
    ("inner", "DayNightIs"): T_inner__DayNightIs,
    ("inner", "EventOutcomeWon"): T_inner__EventOutcomeWon,
    ("inner", "Fixed"): T_inner__Fixed,
    ("inner", "HasCityBlessing"): T_inner__HasCityBlessing,
    ("inner", "IsMonarch"): T_inner__IsMonarch,
    ("inner", "ManaColorSpent"): T_inner__ManaColorSpent,
    ("inner", "Multiply"): T_inner__Multiply,
    ("inner", "Not"): T_inner__Not,
    ("inner", "NthResolutionThisTurn"): T_inner__NthResolutionThisTurn,
    ("inner", "Offset"): T_inner__Offset,
    ("inner", "Or"): T_inner__Or,
    ("inner", "QuantityCheck"): T_inner__QuantityCheck,
    ("inner", "Ref"): T_inner__Ref,
    ("inner", "RevealedHasCardType"): T_inner__RevealedHasCardType,
    ("inner", "SourceMatchesFilter"): T_inner__SourceMatchesFilter,
    ("inner", "Sum"): T_inner__Sum,
    ("inner", "TargetMatchesFilter"): T_inner__TargetMatchesFilter,
    ("inner", "ZoneChangeObjectMatchesFilter"): T_inner__ZoneChangeObjectMatchesFilter,
    ("inner", "ZoneChangedThisWay"): T_inner__ZoneChangedThisWay,
    (
        "invalidation",
        "UntilNextGrantFromSameSource",
    ): T_invalidation__UntilNextGrantFromSameSource,
    (
        "iteration_kind_binding",
        "RebindToIteratedKind",
    ): T_iteration_kind_binding__RebindToIteratedKind,
    ("keep_count_expr", "Ref"): T_keep_count_expr__Ref,
    ("kind", "Card"): T_kind__Card,
    ("kind", "Food"): T_kind__Food,
    ("kind", "TappedFish"): T_kind__TappedFish,
    ("kind", "Treasure"): T_kind__Treasure,
    ("land_filter", "Typed"): T_land_filter__Typed,
    ("left", "Ref"): T_left__Ref,
    ("lhs", "Difference"): T_lhs__Difference,
    ("lhs", "HandSize"): T_lhs__HandSize,
    ("lhs", "ObjectCount"): T_lhs__ObjectCount,
    ("lhs", "Ref"): T_lhs__Ref,
    ("library_position", "Bottom"): T_library_position__Bottom,
    ("library_position", "Top"): T_library_position__Top,
    ("life_payment", "Fixed"): T_life_payment__Fixed,
    ("mana_cost", "Cost"): T_mana_cost__Cost,
    ("mana_cost", "NoCost"): T_mana_cost__NoCost,
    ("mana_modification", "Multiply"): T_mana_modification__Multiply,
    ("mana_modification", "ReplaceWith"): T_mana_modification__ReplaceWith,
    ("mana_reduction", "Cost"): T_mana_reduction__Cost,
    (
        "mana_replacement_scope",
        "TappedForMana",
    ): T_mana_replacement_scope__TappedForMana,
    ("mana_value_limit", "Fixed"): T_mana_value_limit__Fixed,
    ("mana_value_limit", "Ref"): T_mana_value_limit__Ref,
    ("matched_disposition", "ChooseAnyNumber"): T_matched_disposition__ChooseAnyNumber,
    ("matched_disposition", "RevealOnly"): T_matched_disposition__RevealOnly,
    ("materials", "Or"): T_materials__Or,
    ("max", "Fixed"): T_max__Fixed,
    ("max", "Offset"): T_max__Offset,
    ("max", "Ref"): T_max__Ref,
    ("max_ticket_cost", "Ref"): T_max_ticket_cost__Ref,
    ("metric", "DistinctColors"): T_metric__DistinctColors,
    ("metric", "FromSource"): T_metric__FromSource,
    ("metric", "Total"): T_metric__Total,
    ("min", "Ref"): T_min__Ref,
    ("mode", "Mandatory"): T_mode__Mandatory,
    ("mode", "MayCost"): T_mode__MayCost,
    ("mode", "Optional"): T_mode__Optional,
    ("mode_costs", "Cost"): T_mode_costs__Cost,
    ("modification", "Double"): T_modification__Double,
    ("modifications", "AddAllBasicLandTypes"): T_modifications__AddAllBasicLandTypes,
    ("modifications", "AddAllCreatureTypes"): T_modifications__AddAllCreatureTypes,
    ("modifications", "AddAllLandTypes"): T_modifications__AddAllLandTypes,
    ("modifications", "AddChosenColor"): T_modifications__AddChosenColor,
    ("modifications", "AddChosenKeyword"): T_modifications__AddChosenKeyword,
    ("modifications", "AddChosenSubtype"): T_modifications__AddChosenSubtype,
    ("modifications", "AddColor"): T_modifications__AddColor,
    ("modifications", "AddDynamicKeyword"): T_modifications__AddDynamicKeyword,
    ("modifications", "AddDynamicPower"): T_modifications__AddDynamicPower,
    ("modifications", "AddDynamicToughness"): T_modifications__AddDynamicToughness,
    ("modifications", "AddKeyword"): T_modifications__AddKeyword,
    ("modifications", "AddPower"): T_modifications__AddPower,
    ("modifications", "AddStaticMode"): T_modifications__AddStaticMode,
    ("modifications", "AddSubtype"): T_modifications__AddSubtype,
    ("modifications", "AddSupertype"): T_modifications__AddSupertype,
    ("modifications", "AddToughness"): T_modifications__AddToughness,
    ("modifications", "AddType"): T_modifications__AddType,
    (
        "modifications",
        "AssignDamageAsThoughUnblocked",
    ): T_modifications__AssignDamageAsThoughUnblocked,
    (
        "modifications",
        "AssignDamageFromToughness",
    ): T_modifications__AssignDamageFromToughness,
    ("modifications", "AssignNoCombatDamage"): T_modifications__AssignNoCombatDamage,
    ("modifications", "ChangeController"): T_modifications__ChangeController,
    ("modifications", "GrantAbility"): T_modifications__GrantAbility,
    (
        "modifications",
        "GrantAllActivatedAbilitiesOf",
    ): T_modifications__GrantAllActivatedAbilitiesOf,
    (
        "modifications",
        "GrantAllTriggeredAbilitiesOf",
    ): T_modifications__GrantAllTriggeredAbilitiesOf,
    ("modifications", "GrantStaticAbility"): T_modifications__GrantStaticAbility,
    ("modifications", "GrantTrigger"): T_modifications__GrantTrigger,
    ("modifications", "RemoveAllAbilities"): T_modifications__RemoveAllAbilities,
    ("modifications", "RemoveAllSubtypes"): T_modifications__RemoveAllSubtypes,
    ("modifications", "RemoveKeyword"): T_modifications__RemoveKeyword,
    ("modifications", "RemoveSupertype"): T_modifications__RemoveSupertype,
    ("modifications", "RemoveType"): T_modifications__RemoveType,
    ("modifications", "SetBasicLandType"): T_modifications__SetBasicLandType,
    ("modifications", "SetCardTypes"): T_modifications__SetCardTypes,
    (
        "modifications",
        "SetChosenBasicLandType",
    ): T_modifications__SetChosenBasicLandType,
    ("modifications", "SetChosenName"): T_modifications__SetChosenName,
    ("modifications", "SetColor"): T_modifications__SetColor,
    ("modifications", "SetDynamicPower"): T_modifications__SetDynamicPower,
    ("modifications", "SetDynamicToughness"): T_modifications__SetDynamicToughness,
    ("modifications", "SetName"): T_modifications__SetName,
    ("modifications", "SetPower"): T_modifications__SetPower,
    ("modifications", "SetPowerDynamic"): T_modifications__SetPowerDynamic,
    ("modifications", "SetToughness"): T_modifications__SetToughness,
    ("modifications", "SetToughnessDynamic"): T_modifications__SetToughnessDynamic,
    ("modifier", "Add"): T_modifier__Add,
    ("modifier", "CantBeCountered"): T_modifier__CantBeCountered,
    ("modifier", "CastAsThoughFlash"): T_modifier__CastAsThoughFlash,
    ("modifier", "HasKeyword"): T_modifier__HasKeyword,
    ("modifier", "Subtract"): T_modifier__Subtract,
    ("modifier", "WithoutPayingManaCost"): T_modifier__WithoutPayingManaCost,
    ("object_filter", "Any"): T_object_filter__Any,
    ("object_filter", "Typed"): T_object_filter__Typed,
    ("object_source", "ParentTarget"): T_object_source__ParentTarget,
    ("object_source", "TrackedSet"): T_object_source__TrackedSet,
    ("once_per_turn", "OnlyOnceEachTurn"): T_once_per_turn__OnlyOnceEachTurn,
    ("only_tag", "PowerUp"): T_only_tag__PowerUp,
    ("op", "LockOrUnlock"): T_op__LockOrUnlock,
    ("op", "Unlock"): T_op__Unlock,
    ("origin", "Equals"): T_origin__Equals,
    ("origin", "NotEquals"): T_origin__NotEquals,
    ("origin", "OneOf"): T_origin__OneOf,
    ("origin_constraint", "Equals"): T_origin_constraint__Equals,
    ("owner", "Any"): T_owner__Any,
    ("owner", "Controller"): T_owner__Controller,
    ("owner", "OriginalController"): T_owner__OriginalController,
    ("owner", "ParentTarget"): T_owner__ParentTarget,
    ("owner", "ParentTargetController"): T_owner__ParentTargetController,
    ("owner", "ParentTargetOwner"): T_owner__ParentTargetOwner,
    ("owner", "Player"): T_owner__Player,
    ("owner", "ScopedPlayer"): T_owner__ScopedPlayer,
    ("owner", "TriggeringPlayer"): T_owner__TriggeringPlayer,
    ("owner", "TriggeringSource"): T_owner__TriggeringSource,
    ("owner", "Typed"): T_owner__Typed,
    ("parity", "LastNamedChoice"): T_parity__LastNamedChoice,
    ("parse_warnings", "IgnoredRemainder"): T_parse_warnings__IgnoredRemainder,
    ("parse_warnings", "SwallowedClause"): T_parse_warnings__SwallowedClause,
    ("parse_warnings", "TargetFallback"): T_parse_warnings__TargetFallback,
    ("partition_subject", "AnOpponent"): T_partition_subject__AnOpponent,
    ("partition_subject", "EachOpponent"): T_partition_subject__EachOpponent,
    ("payer", "AllPlayers"): T_payer__AllPlayers,
    ("payer", "Controller"): T_payer__Controller,
    ("payer", "ParentTargetController"): T_payer__ParentTargetController,
    ("payer", "Player"): T_payer__Player,
    ("payer", "ScopedPlayer"): T_payer__ScopedPlayer,
    ("payer", "TriggeringPlayer"): T_payer__TriggeringPlayer,
    ("payer", "TriggeringSpellController"): T_payer__TriggeringSpellController,
    ("payer", "Typed"): T_payer__Typed,
    (
        "per_player_condition",
        "YouAttackedSourceControllerThisTurn",
    ): T_per_player_condition__YouAttackedSourceControllerThisTurn,
    (
        "per_player_condition",
        "YouAttackedThisTurn",
    ): T_per_player_condition__YouAttackedThisTurn,
    (
        "per_player_condition",
        "YouCastSpellThisTurn",
    ): T_per_player_condition__YouCastSpellThisTurn,
    ("permission", "ExileWithAltCost"): T_permission__ExileWithAltCost,
    ("permission", "ExileWithEnergyCost"): T_permission__ExileWithEnergyCost,
    ("permission", "Foretold"): T_permission__Foretold,
    ("permission", "PlayFromExile"): T_permission__PlayFromExile,
    ("permission", "Plotted"): T_permission__Plotted,
    ("pile_source", "Battlefield"): T_pile_source__Battlefield,
    ("pile_source", "ExiledThisWay"): T_pile_source__ExiledThisWay,
    ("pile_source", "RevealedFromLibraryTop"): T_pile_source__RevealedFromLibraryTop,
    ("player", "AllPlayers"): T_player__AllPlayers,
    ("player", "Any"): T_player__Any,
    ("player", "AnyTurn"): T_player__AnyTurn,
    ("player", "Controller"): T_player__Controller,
    ("player", "DefendingPlayer"): T_player__DefendingPlayer,
    ("player", "Opponent"): T_player__Opponent,
    ("player", "OpponentDealtDamage"): T_player__OpponentDealtDamage,
    ("player", "ParentObjectTargetController"): T_player__ParentObjectTargetController,
    ("player", "ParentTarget"): T_player__ParentTarget,
    ("player", "ParentTargetController"): T_player__ParentTargetController,
    ("player", "ParentTargetOwner"): T_player__ParentTargetOwner,
    ("player", "Player"): T_player__Player,
    ("player", "PostReplacementDamageTarget"): T_player__PostReplacementDamageTarget,
    ("player", "RecipientController"): T_player__RecipientController,
    ("player", "ScopedPlayer"): T_player__ScopedPlayer,
    ("player", "SourceChosenPlayer"): T_player__SourceChosenPlayer,
    ("player", "Target"): T_player__Target,
    ("player", "TriggeringPlayer"): T_player__TriggeringPlayer,
    ("player", "Typed"): T_player__Typed,
    ("player_a", "Controller"): T_player_a__Controller,
    ("player_a", "Player"): T_player_a__Player,
    ("player_b", "Player"): T_player_b__Player,
    ("player_b", "Typed"): T_player_b__Typed,
    ("player_filter", "All"): T_player_filter__All,
    ("player_filter", "Opponent"): T_player_filter__Opponent,
    (
        "player_filter",
        "OpponentOtherThanTriggering",
    ): T_player_filter__OpponentOtherThanTriggering,
    ("player_scope", "All"): T_player_scope__All,
    ("player_scope", "AllExcept"): T_player_scope__AllExcept,
    ("player_scope", "ChosenPlayer"): T_player_scope__ChosenPlayer,
    ("player_scope", "ControlsCount"): T_player_scope__ControlsCount,
    ("player_scope", "DefendingPlayer"): T_player_scope__DefendingPlayer,
    ("player_scope", "HighestSpeed"): T_player_scope__HighestSpeed,
    ("player_scope", "Opponent"): T_player_scope__Opponent,
    ("player_scope", "OpponentAttacked"): T_player_scope__OpponentAttacked,
    (
        "player_scope",
        "OpponentAttackingEnchantedPlayer",
    ): T_player_scope__OpponentAttackingEnchantedPlayer,
    (
        "player_scope",
        "OpponentOfTriggeringPlayer",
    ): T_player_scope__OpponentOfTriggeringPlayer,
    (
        "player_scope",
        "OwnersOfCardsExiledBySource",
    ): T_player_scope__OwnersOfCardsExiledBySource,
    (
        "player_scope",
        "ParentObjectTargetController",
    ): T_player_scope__ParentObjectTargetController,
    ("player_scope", "PlayerAttribute"): T_player_scope__PlayerAttribute,
    ("player_scope", "TriggeringPlayer"): T_player_scope__TriggeringPlayer,
    ("player_scope", "VotedFor"): T_player_scope__VotedFor,
    ("position", "BeneathTop"): T_position__BeneathTop,
    ("position", "Bottom"): T_position__Bottom,
    ("position", "NthFromTop"): T_position__NthFromTop,
    ("position", "Top"): T_position__Top,
    ("power", "Fixed"): T_power__Fixed,
    ("power", "Quantity"): T_power__Quantity,
    ("power", "Variable"): T_power__Variable,
    ("produced", "AnyCombination"): T_produced__AnyCombination,
    (
        "produced",
        "AnyCombinationOfObjectColors",
    ): T_produced__AnyCombinationOfObjectColors,
    (
        "produced",
        "AnyInCommandersColorIdentity",
    ): T_produced__AnyInCommandersColorIdentity,
    ("produced", "AnyOneColor"): T_produced__AnyOneColor,
    ("produced", "AnyOneColorAmongPermanents"): T_produced__AnyOneColorAmongPermanents,
    ("produced", "AnyTypeProduceableBy"): T_produced__AnyTypeProduceableBy,
    ("produced", "ChoiceAmongCombinations"): T_produced__ChoiceAmongCombinations,
    ("produced", "ChoiceAmongExiledColors"): T_produced__ChoiceAmongExiledColors,
    ("produced", "ChosenColor"): T_produced__ChosenColor,
    ("produced", "Colorless"): T_produced__Colorless,
    (
        "produced",
        "DistinctColorsAmongPermanents",
    ): T_produced__DistinctColorsAmongPermanents,
    ("produced", "Fixed"): T_produced__Fixed,
    ("produced", "Mixed"): T_produced__Mixed,
    ("produced", "OpponentLandColors"): T_produced__OpponentLandColors,
    ("produced", "TriggerEventManaType"): T_produced__TriggerEventManaType,
    ("prop", "AttackedThisTurn"): T_prop__AttackedThisTurn,
    ("prop", "EnteredThisTurn"): T_prop__EnteredThisTurn,
    ("prop", "InTrackedSet"): T_prop__InTrackedSet,
    ("prop", "SameName"): T_prop__SameName,
    ("prop", "SharesQuality"): T_prop__SharesQuality,
    ("prop", "WasPlayed"): T_prop__WasPlayed,
    ("properties", "Another"): T_properties__Another,
    ("properties", "AnyOf"): T_properties__AnyOf,
    ("properties", "AttachedToRecipient"): T_properties__AttachedToRecipient,
    ("properties", "AttachedToSource"): T_properties__AttachedToSource,
    (
        "properties",
        "AttackedOrBlockedThisTurn",
    ): T_properties__AttackedOrBlockedThisTurn,
    ("properties", "AttackedThisTurn"): T_properties__AttackedThisTurn,
    ("properties", "Attacking"): T_properties__Attacking,
    ("properties", "AttackingAlone"): T_properties__AttackingAlone,
    ("properties", "BlockedThisTurn"): T_properties__BlockedThisTurn,
    ("properties", "Blocking"): T_properties__Blocking,
    ("properties", "BlockingSource"): T_properties__BlockingSource,
    ("properties", "CanEnchant"): T_properties__CanEnchant,
    ("properties", "Cmc"): T_properties__Cmc,
    ("properties", "ColorCount"): T_properties__ColorCount,
    ("properties", "CombatRelation"): T_properties__CombatRelation,
    (
        "properties",
        "ControlledContinuouslySinceTurnBegan",
    ): T_properties__ControlledContinuouslySinceTurnBegan,
    ("properties", "ControllerChoseLabel"): T_properties__ControllerChoseLabel,
    ("properties", "ControllerMatches"): T_properties__ControllerMatches,
    ("properties", "ConvokedSource"): T_properties__ConvokedSource,
    (
        "properties",
        "CouldBeTargetedByTriggeringSpell",
    ): T_properties__CouldBeTargetedByTriggeringSpell,
    ("properties", "Counters"): T_properties__Counters,
    ("properties", "CountersPutOnThisTurn"): T_properties__CountersPutOnThisTurn,
    ("properties", "DifferentNameFrom"): T_properties__DifferentNameFrom,
    ("properties", "DistinctFrom"): T_properties__DistinctFrom,
    ("properties", "EnchantedBy"): T_properties__EnchantedBy,
    ("properties", "EnteredThisTurn"): T_properties__EnteredThisTurn,
    ("properties", "EquippedBy"): T_properties__EquippedBy,
    ("properties", "FaceDown"): T_properties__FaceDown,
    ("properties", "Foretold"): T_properties__Foretold,
    ("properties", "HasAnyAttachmentOf"): T_properties__HasAnyAttachmentOf,
    ("properties", "HasAttachment"): T_properties__HasAttachment,
    ("properties", "HasColor"): T_properties__HasColor,
    ("properties", "HasKeywordKind"): T_properties__HasKeywordKind,
    ("properties", "HasManaAbility"): T_properties__HasManaAbility,
    ("properties", "HasNoAbilities"): T_properties__HasNoAbilities,
    ("properties", "HasSingleTarget"): T_properties__HasSingleTarget,
    ("properties", "HasSupertype"): T_properties__HasSupertype,
    ("properties", "HasXInActivationCost"): T_properties__HasXInActivationCost,
    ("properties", "HasXInManaCost"): T_properties__HasXInManaCost,
    ("properties", "Historic"): T_properties__Historic,
    ("properties", "InAnyZone"): T_properties__InAnyZone,
    ("properties", "InZone"): T_properties__InZone,
    ("properties", "IsChosenCardType"): T_properties__IsChosenCardType,
    ("properties", "IsChosenColor"): T_properties__IsChosenColor,
    ("properties", "IsChosenCreatureType"): T_properties__IsChosenCreatureType,
    ("properties", "IsCommander"): T_properties__IsCommander,
    ("properties", "IsSaddled"): T_properties__IsSaddled,
    ("properties", "ManaCostIn"): T_properties__ManaCostIn,
    ("properties", "ManaSymbolCount"): T_properties__ManaSymbolCount,
    ("properties", "ManaValueParity"): T_properties__ManaValueParity,
    (
        "properties",
        "MatchesLastChosenCardPredicate",
    ): T_properties__MatchesLastChosenCardPredicate,
    ("properties", "Modal"): T_properties__Modal,
    ("properties", "Modified"): T_properties__Modified,
    (
        "properties",
        "MostPrevalentCreatureTypeIn",
    ): T_properties__MostPrevalentCreatureTypeIn,
    ("properties", "NameMatchesAnyPermanent"): T_properties__NameMatchesAnyPermanent,
    ("properties", "Named"): T_properties__Named,
    ("properties", "NonToken"): T_properties__NonToken,
    ("properties", "Not"): T_properties__Not,
    ("properties", "NotColor"): T_properties__NotColor,
    ("properties", "NotHistoric"): T_properties__NotHistoric,
    ("properties", "NotSupertype"): T_properties__NotSupertype,
    ("properties", "OtherThanTriggerObject"): T_properties__OtherThanTriggerObject,
    ("properties", "Owned"): T_properties__Owned,
    ("properties", "PowerExceedsBase"): T_properties__PowerExceedsBase,
    ("properties", "PowerGTSource"): T_properties__PowerGTSource,
    ("properties", "ProtectorMatches"): T_properties__ProtectorMatches,
    ("properties", "PtComparison"): T_properties__PtComparison,
    ("properties", "Renowned"): T_properties__Renowned,
    ("properties", "SaddledSource"): T_properties__SaddledSource,
    ("properties", "SameName"): T_properties__SameName,
    ("properties", "SameNameAsParentTarget"): T_properties__SameNameAsParentTarget,
    ("properties", "SharesQuality"): T_properties__SharesQuality,
    ("properties", "Suspected"): T_properties__Suspected,
    ("properties", "Tapped"): T_properties__Tapped,
    ("properties", "Targets"): T_properties__Targets,
    ("properties", "TargetsOnly"): T_properties__TargetsOnly,
    ("properties", "Token"): T_properties__Token,
    ("properties", "ToughnessGTPower"): T_properties__ToughnessGTPower,
    ("properties", "Transformed"): T_properties__Transformed,
    ("properties", "Unblocked"): T_properties__Unblocked,
    ("properties", "Unpaired"): T_properties__Unpaired,
    ("properties", "Untapped"): T_properties__Untapped,
    ("properties", "WasDealtDamageThisTurn"): T_properties__WasDealtDamageThisTurn,
    ("properties", "WasKicked"): T_properties__WasKicked,
    ("properties", "WasPlayed"): T_properties__WasPlayed,
    ("properties", "WithKeyword"): T_properties__WithKeyword,
    ("properties", "WithoutKeyword"): T_properties__WithoutKeyword,
    ("properties", "WithoutKeywordKind"): T_properties__WithoutKeywordKind,
    ("properties", "ZoneChangedThisTurn"): T_properties__ZoneChangedThisTurn,
    ("props", "AttackingAlone"): T_props__AttackingAlone,
    ("props", "BlockingAlone"): T_props__BlockingAlone,
    ("props", "Cmc"): T_props__Cmc,
    ("props", "HasColor"): T_props__HasColor,
    ("props", "PtComparison"): T_props__PtComparison,
    ("qty", "AdditionalCostPaymentCountFor"): T_qty__AdditionalCostPaymentCountFor,
    ("qty", "Aggregate"): T_qty__Aggregate,
    ("qty", "AttachmentsOnLeavingObject"): T_qty__AttachmentsOnLeavingObject,
    ("qty", "AttackedThisTurn"): T_qty__AttackedThisTurn,
    ("qty", "BasicLandTypeCount"): T_qty__BasicLandTypeCount,
    ("qty", "BattlefieldEntriesThisTurn"): T_qty__BattlefieldEntriesThisTurn,
    ("qty", "BendTypesThisTurn"): T_qty__BendTypesThisTurn,
    ("qty", "CardsDiscardedThisTurn"): T_qty__CardsDiscardedThisTurn,
    ("qty", "CardsDrawnThisTurn"): T_qty__CardsDrawnThisTurn,
    ("qty", "CardsExiledBySource"): T_qty__CardsExiledBySource,
    ("qty", "ChosenNumber"): T_qty__ChosenNumber,
    ("qty", "ColorsInCommandersColorIdentity"): T_qty__ColorsInCommandersColorIdentity,
    (
        "qty",
        "CommanderCastFromCommandZoneCount",
    ): T_qty__CommanderCastFromCommandZoneCount,
    ("qty", "CommanderManaValue"): T_qty__CommanderManaValue,
    ("qty", "ControlledByEachPlayer"): T_qty__ControlledByEachPlayer,
    ("qty", "ConvokedCreatureCount"): T_qty__ConvokedCreatureCount,
    ("qty", "CostXPaid"): T_qty__CostXPaid,
    ("qty", "CounterAddedThisTurn"): T_qty__CounterAddedThisTurn,
    ("qty", "CountersOn"): T_qty__CountersOn,
    ("qty", "CountersOnObjects"): T_qty__CountersOnObjects,
    ("qty", "CrimesCommittedThisTurn"): T_qty__CrimesCommittedThisTurn,
    ("qty", "DamageDealtThisTurn"): T_qty__DamageDealtThisTurn,
    ("qty", "DescendedThisTurn"): T_qty__DescendedThisTurn,
    ("qty", "Devotion"): T_qty__Devotion,
    ("qty", "DistinctCardTypes"): T_qty__DistinctCardTypes,
    ("qty", "DistinctColorsAmongPermanents"): T_qty__DistinctColorsAmongPermanents,
    ("qty", "DistinctCounterKindsAmong"): T_qty__DistinctCounterKindsAmong,
    ("qty", "DistinctSubtypes"): T_qty__DistinctSubtypes,
    ("qty", "EnteredThisTurn"): T_qty__EnteredThisTurn,
    ("qty", "EventContextAmount"): T_qty__EventContextAmount,
    ("qty", "ExiledCardPower"): T_qty__ExiledCardPower,
    ("qty", "ExiledFromHandThisResolution"): T_qty__ExiledFromHandThisResolution,
    ("qty", "FilteredTrackedSetSize"): T_qty__FilteredTrackedSetSize,
    ("qty", "GraveyardSize"): T_qty__GraveyardSize,
    ("qty", "HandSize"): T_qty__HandSize,
    ("qty", "Intensity"): T_qty__Intensity,
    ("qty", "KickerCount"): T_qty__KickerCount,
    ("qty", "LandsPlayedThisTurn"): T_qty__LandsPlayedThisTurn,
    ("qty", "LifeAboveStarting"): T_qty__LifeAboveStarting,
    ("qty", "LifeGainedThisTurn"): T_qty__LifeGainedThisTurn,
    ("qty", "LifeLostThisTurn"): T_qty__LifeLostThisTurn,
    ("qty", "LifeTotal"): T_qty__LifeTotal,
    (
        "qty",
        "LoyaltyAbilitiesActivatedThisTurn",
    ): T_qty__LoyaltyAbilitiesActivatedThisTurn,
    ("qty", "ManaSpentToCast"): T_qty__ManaSpentToCast,
    ("qty", "ManaSymbolsInManaCost"): T_qty__ManaSymbolsInManaCost,
    ("qty", "ObjectColorCount"): T_qty__ObjectColorCount,
    ("qty", "ObjectCount"): T_qty__ObjectCount,
    ("qty", "ObjectCountBySharedQuality"): T_qty__ObjectCountBySharedQuality,
    ("qty", "ObjectCountDistinct"): T_qty__ObjectCountDistinct,
    ("qty", "ObjectManaValue"): T_qty__ObjectManaValue,
    ("qty", "ObjectNameWordCount"): T_qty__ObjectNameWordCount,
    ("qty", "ObjectTypelineComponentCount"): T_qty__ObjectTypelineComponentCount,
    ("qty", "PartySize"): T_qty__PartySize,
    ("qty", "PlayerActionsThisTurn"): T_qty__PlayerActionsThisTurn,
    ("qty", "PlayerCount"): T_qty__PlayerCount,
    ("qty", "PlayerCounter"): T_qty__PlayerCounter,
    ("qty", "Power"): T_qty__Power,
    ("qty", "PreviousEffectAmount"): T_qty__PreviousEffectAmount,
    ("qty", "SacrificedThisTurn"): T_qty__SacrificedThisTurn,
    ("qty", "SelfManaValue"): T_qty__SelfManaValue,
    ("qty", "Speed"): T_qty__Speed,
    ("qty", "SpellsCastLastTurn"): T_qty__SpellsCastLastTurn,
    ("qty", "SpellsCastThisGame"): T_qty__SpellsCastThisGame,
    ("qty", "SpellsCastThisTurn"): T_qty__SpellsCastThisTurn,
    ("qty", "StartingLifeTotal"): T_qty__StartingLifeTotal,
    ("qty", "TargetControllerCounter"): T_qty__TargetControllerCounter,
    ("qty", "TargetObjectManaValue"): T_qty__TargetObjectManaValue,
    ("qty", "TargetZoneCardCount"): T_qty__TargetZoneCardCount,
    ("qty", "TimesCostPaidThisResolution"): T_qty__TimesCostPaidThisResolution,
    ("qty", "TokensCreatedThisTurn"): T_qty__TokensCreatedThisTurn,
    ("qty", "Toughness"): T_qty__Toughness,
    ("qty", "TrackedSetAggregate"): T_qty__TrackedSetAggregate,
    ("qty", "TrackedSetSize"): T_qty__TrackedSetSize,
    ("qty", "TriggeringDiscoverValue"): T_qty__TriggeringDiscoverValue,
    ("qty", "TurnsTaken"): T_qty__TurnsTaken,
    ("qty", "UnspentMana"): T_qty__UnspentMana,
    ("qty", "Variable"): T_qty__Variable,
    ("qty", "VoteCount"): T_qty__VoteCount,
    ("qty", "ZoneCardCount"): T_qty__ZoneCardCount,
    ("qty", "ZoneChangeAggregateThisTurn"): T_qty__ZoneChangeAggregateThisTurn,
    ("qty", "ZoneChangeCountThisTurn"): T_qty__ZoneChangeCountThisTurn,
    ("quantity", "BasicLandTypeCount"): T_quantity__BasicLandTypeCount,
    ("quantity", "CountersOn"): T_quantity__CountersOn,
    ("quantity", "Multiply"): T_quantity__Multiply,
    ("quantity", "ObjectCount"): T_quantity__ObjectCount,
    ("quantity", "Ref"): T_quantity__Ref,
    ("quantity", "Sum"): T_quantity__Sum,
    ("quantity", "ZoneCardCount"): T_quantity__ZoneCardCount,
    ("quantity_modification", "Half"): T_quantity_modification__Half,
    ("quantity_modification", "Minus"): T_quantity_modification__Minus,
    ("quantity_modification", "Plus"): T_quantity_modification__Plus,
    ("quantity_modification", "Prevent"): T_quantity_modification__Prevent,
    ("quantity_modification", "Times"): T_quantity_modification__Times,
    ("recipient", "Any"): T_recipient__Any,
    ("recipient", "EachController"): T_recipient__EachController,
    ("recipient", "Neighbor"): T_recipient__Neighbor,
    ("recipient", "ParentTarget"): T_recipient__ParentTarget,
    ("recipient", "ParentTargetController"): T_recipient__ParentTargetController,
    ("recipient", "Player"): T_recipient__Player,
    ("recipient", "ScopedPlayer"): T_recipient__ScopedPlayer,
    ("recipient", "SelfRef"): T_recipient__SelfRef,
    ("recipient", "Shared"): T_recipient__Shared,
    ("recipient", "TriggeringPlayer"): T_recipient__TriggeringPlayer,
    (
        "recipient",
        "TriggeringSourceController",
    ): T_recipient__TriggeringSourceController,
    ("recipient", "Typed"): T_recipient__Typed,
    ("recipient_object_filter", "SelfRef"): T_recipient_object_filter__SelfRef,
    ("recipient_object_filter", "Typed"): T_recipient_object_filter__Typed,
    ("redirect_object_filter", "Typed"): T_redirect_object_filter__Typed,
    ("redirect_target", "SelfRef"): T_redirect_target__SelfRef,
    ("redirect_to", "ChosenObjectTarget"): T_redirect_to__ChosenObjectTarget,
    ("redirect_to", "Controller"): T_redirect_to__Controller,
    ("redirect_to", "SourceObject"): T_redirect_to__SourceObject,
    ("reference", "CostPaidObject"): T_reference__CostPaidObject,
    ("reference", "ExiledBySource"): T_reference__ExiledBySource,
    ("reference", "Or"): T_reference__Or,
    ("reference", "ParentTarget"): T_reference__ParentTarget,
    ("reference", "SelfRef"): T_reference__SelfRef,
    ("reference", "TrackedSet"): T_reference__TrackedSet,
    ("reference", "TriggeringSource"): T_reference__TriggeringSource,
    ("reference", "Typed"): T_reference__Typed,
    ("relation", "All"): T_relation__All,
    ("relation", "Opponent"): T_relation__Opponent,
    ("repeat_for", "Difference"): T_repeat_for__Difference,
    ("repeat_for", "Fixed"): T_repeat_for__Fixed,
    ("repeat_for", "Multiply"): T_repeat_for__Multiply,
    ("repeat_for", "Offset"): T_repeat_for__Offset,
    ("repeat_for", "Ref"): T_repeat_for__Ref,
    ("repeat_until", "ControllerChoice"): T_repeat_until__ControllerChoice,
    ("repeat_until", "UntilStopConditions"): T_repeat_until__UntilStopConditions,
    ("repeat_until", "WhileCondition"): T_repeat_until__WhileCondition,
    ("replacement_effect", "ChaosEnsues"): T_replacement_effect__ChaosEnsues,
    ("replacement_effect", "DealDamage"): T_replacement_effect__DealDamage,
    ("replacement_effect", "GainLife"): T_replacement_effect__GainLife,
    ("replacement_effect", "Token"): T_replacement_effect__Token,
    ("required_player", "Controller"): T_required_player__Controller,
    ("required_player", "Typed"): T_required_player__Typed,
    (
        "restriction",
        "CantEnterBattlefieldFrom",
    ): T_restriction__CantEnterBattlefieldFrom,
    (
        "restriction",
        "DamagePreventionDisabled",
    ): T_restriction__DamagePreventionDisabled,
    ("restriction", "PlayerAttribute"): T_restriction__PlayerAttribute,
    ("restriction", "ProhibitActivity"): T_restriction__ProhibitActivity,
    ("retarget", "KeepOriginalTargets"): T_retarget__KeepOriginalTargets,
    ("retarget", "MayChooseNewTargets"): T_retarget__MayChooseNewTargets,
    (
        "retarget",
        "RetargetEachCopyToIterationMember",
    ): T_retarget__RetargetEachCopyToIterationMember,
    ("rhs", "DivideRounded"): T_rhs__DivideRounded,
    ("rhs", "Fixed"): T_rhs__Fixed,
    ("rhs", "HandSize"): T_rhs__HandSize,
    ("rhs", "ObjectCount"): T_rhs__ObjectCount,
    ("rhs", "Offset"): T_rhs__Offset,
    ("rhs", "Ref"): T_rhs__Ref,
    ("right", "Fixed"): T_right__Fixed,
    ("right", "Ref"): T_right__Ref,
    ("sacrifice_filter", "Typed"): T_sacrifice_filter__Typed,
    ("scale", "Ref"): T_scale__Ref,
    ("scaling", "PerAffectedAndQuantityRef"): T_scaling__PerAffectedAndQuantityRef,
    ("scaling", "PerAffectedCreature"): T_scaling__PerAffectedCreature,
    ("scaling", "PerAffectedWithRef"): T_scaling__PerAffectedWithRef,
    ("scaling", "PerQuantityRef"): T_scaling__PerQuantityRef,
    ("scope", "All"): T_scope__All,
    ("scope", "AmassedArmy"): T_scope__AmassedArmy,
    ("scope", "Anaphoric"): T_scope__Anaphoric,
    ("scope", "CostPaidObject"): T_scope__CostPaidObject,
    ("scope", "Demonstrative"): T_scope__Demonstrative,
    ("scope", "EventSource"): T_scope__EventSource,
    ("scope", "EventTarget"): T_scope__EventTarget,
    ("scope", "OtherRevealedCard"): T_scope__OtherRevealedCard,
    ("scope", "OwnedSameName"): T_scope__OwnedSameName,
    ("scope", "OwnedSubtype"): T_scope__OwnedSubtype,
    ("scope", "Recipient"): T_scope__Recipient,
    ("scope", "Single"): T_scope__Single,
    ("scope", "Source"): T_scope__Source,
    ("scope", "SourcesControlledBy"): T_scope__SourcesControlledBy,
    ("scope", "Target"): T_scope__Target,
    ("selection", "Random"): T_selection__Random,
    (
        "selection_constraint",
        "DistinctQualities",
    ): T_selection_constraint__DistinctQualities,
    (
        "selection_constraint",
        "MatchEachFilter",
    ): T_selection_constraint__MatchEachFilter,
    ("selection_constraint", "TotalManaValue"): T_selection_constraint__TotalManaValue,
    ("solve_condition", "Condition"): T_solve_condition__Condition,
    ("solve_condition", "ObjectCount"): T_solve_condition__ObjectCount,
    ("solve_condition", "Text"): T_solve_condition__Text,
    ("source", "And"): T_source__And,
    ("source", "Any"): T_source__Any,
    ("source", "AttachedTo"): T_source__AttachedTo,
    ("source", "ChosenCard"): T_source__ChosenCard,
    ("source", "ExiledBySource"): T_source__ExiledBySource,
    ("source", "Objects"): T_source__Objects,
    ("source", "Or"): T_source__Or,
    ("source", "SelfRef"): T_source__SelfRef,
    ("source", "ThisObject"): T_source__ThisObject,
    ("source", "TrackedSet"): T_source__TrackedSet,
    ("source", "TriggeringSource"): T_source__TriggeringSource,
    ("source", "Typed"): T_source__Typed,
    ("source", "Zone"): T_source__Zone,
    ("source_filter", "ChosenDamageSource"): T_source_filter__ChosenDamageSource,
    ("source_filter", "HasChosenName"): T_source_filter__HasChosenName,
    ("source_filter", "Or"): T_source_filter__Or,
    ("source_filter", "SelfRef"): T_source_filter__SelfRef,
    ("source_filter", "Typed"): T_source_filter__Typed,
    ("source_pool", "SideboardAndFaceUpExile"): T_source_pool__SideboardAndFaceUpExile,
    ("source_rider", "Destroy"): T_source_rider__Destroy,
    ("source_rider", "LosesAbilities"): T_source_rider__LosesAbilities,
    ("sources", "Typed"): T_sources__Typed,
    ("spell_cast_origin", "Equals"): T_spell_cast_origin__Equals,
    ("spell_cast_origin", "NotEquals"): T_spell_cast_origin__NotEquals,
    ("spell_filter", "HasChosenName"): T_spell_filter__HasChosenName,
    ("spell_filter", "Or"): T_spell_filter__Or,
    ("spell_filter", "Typed"): T_spell_filter__Typed,
    ("state", "Tap"): T_state__Tap,
    ("state", "Untap"): T_state__Untap,
    ("step", "CombatPhase"): T_step__CombatPhase,
    ("step", "Step"): T_step__Step,
    ("strive_cost", "Cost"): T_strive_cost__Cost,
    ("subject", "AttackTarget"): T_subject__AttackTarget,
    ("subject", "CommittedChoice"): T_subject__CommittedChoice,
    ("subject", "Controller"): T_subject__Controller,
    ("subject", "LastRevealed"): T_subject__LastRevealed,
    ("subject", "Named"): T_subject__Named,
    ("subject", "Objects"): T_subject__Objects,
    ("subject", "Or"): T_subject__Or,
    ("subject", "ParentTarget"): T_subject__ParentTarget,
    ("subject", "Proposition"): T_subject__Proposition,
    ("subject", "SelfRef"): T_subject__SelfRef,
    ("subject", "Target"): T_subject__Target,
    ("subject", "TriggeringSource"): T_subject__TriggeringSource,
    ("subject", "Typed"): T_subject__Typed,
    ("subtype_filter", "Or"): T_subtype_filter__Or,
    ("subtype_filter", "Typed"): T_subtype_filter__Typed,
    ("tag", "Backup"): T_tag__Backup,
    ("tally_mode", "PerVote"): T_tally_mode__PerVote,
    ("tally_mode", "TopVotes"): T_tally_mode__TopVotes,
    ("target", "AllPlayers"): T_target__AllPlayers,
    ("target", "And"): T_target__And,
    ("target", "Any"): T_target__Any,
    ("target", "AttachedTo"): T_target__AttachedTo,
    ("target", "Controller"): T_target__Controller,
    ("target", "CostPaidObject"): T_target__CostPaidObject,
    ("target", "DefendingPlayer"): T_target__DefendingPlayer,
    ("target", "EventTarget"): T_target__EventTarget,
    ("target", "ExiledBySource"): T_target__ExiledBySource,
    ("target", "ExiledCardByIndex"): T_target__ExiledCardByIndex,
    ("target", "GrantingObject"): T_target__GrantingObject,
    ("target", "LastCreated"): T_target__LastCreated,
    ("target", "None"): T_target__None,
    ("target", "Or"): T_target__Or,
    ("target", "OriginalController"): T_target__OriginalController,
    ("target", "Owner"): T_target__Owner,
    ("target", "ParentTarget"): T_target__ParentTarget,
    ("target", "ParentTargetController"): T_target__ParentTargetController,
    ("target", "ParentTargetOwner"): T_target__ParentTargetOwner,
    ("target", "ParentTargetSlot"): T_target__ParentTargetSlot,
    ("target", "Player"): T_target__Player,
    ("target", "PostReplacementDamageTarget"): T_target__PostReplacementDamageTarget,
    (
        "target",
        "PostReplacementDamageTargetOwner",
    ): T_target__PostReplacementDamageTargetOwner,
    (
        "target",
        "PostReplacementSourceController",
    ): T_target__PostReplacementSourceController,
    ("target", "ScopedPlayer"): T_target__ScopedPlayer,
    ("target", "SelfRef"): T_target__SelfRef,
    ("target", "SourceChosenPlayer"): T_target__SourceChosenPlayer,
    ("target", "StackAbility"): T_target__StackAbility,
    ("target", "StackSpell"): T_target__StackSpell,
    ("target", "TrackedSet"): T_target__TrackedSet,
    ("target", "TrackedSetFiltered"): T_target__TrackedSetFiltered,
    ("target", "TriggeringPlayer"): T_target__TriggeringPlayer,
    ("target", "TriggeringSource"): T_target__TriggeringSource,
    ("target", "TriggeringSourceController"): T_target__TriggeringSourceController,
    ("target", "TriggeringSpellController"): T_target__TriggeringSpellController,
    ("target", "Typed"): T_target__Typed,
    ("target_a", "And"): T_target_a__And,
    ("target_a", "Or"): T_target_a__Or,
    ("target_a", "SelfRef"): T_target_a__SelfRef,
    ("target_a", "Typed"): T_target_a__Typed,
    ("target_b", "Or"): T_target_b__Or,
    ("target_b", "TriggeringSource"): T_target_b__TriggeringSource,
    ("target_b", "Typed"): T_target_b__Typed,
    ("target_chooser", "ScopedPlayer"): T_target_chooser__ScopedPlayer,
    (
        "target_constraints",
        "DifferentObjectControllers",
    ): T_target_constraints__DifferentObjectControllers,
    ("target_constraints", "SameZoneOwner"): T_target_constraints__SameZoneOwner,
    ("target_constraints", "TotalManaValue"): T_target_constraints__TotalManaValue,
    ("target_kind", "Counters"): T_target_kind__Counters,
    ("target_kind", "LifeTotal"): T_target_kind__LifeTotal,
    ("target_kind", "ManaPool"): T_target_kind__ManaPool,
    (
        "target_player",
        "ParentTargetController",
    ): T_target_player__ParentTargetController,
    ("target_player", "Player"): T_target_player__Player,
    ("target_player", "Typed"): T_target_player__Typed,
    ("target_selection_mode", "Random"): T_target_selection_mode__Random,
    ("threshold", "Fixed"): T_threshold__Fixed,
    ("tie", "AllTied"): T_tie__AllTied,
    ("tie", "Breaker"): T_tie__Breaker,
    ("total_power_cap", "Fixed"): T_total_power_cap__Fixed,
    ("toughness", "Fixed"): T_toughness__Fixed,
    ("toughness", "Quantity"): T_toughness__Quantity,
    ("toughness", "Variable"): T_toughness__Variable,
    ("unless_filter", "Or"): T_unless_filter__Or,
    ("unless_filter", "Typed"): T_unless_filter__Typed,
    ("until", "CumulativeThreshold"): T_until__CumulativeThreshold,
    ("until", "NextMatches"): T_until__NextMatches,
    ("valid_card", "And"): T_valid_card__And,
    ("valid_card", "Any"): T_valid_card__Any,
    ("valid_card", "AttachedTo"): T_valid_card__AttachedTo,
    ("valid_card", "Or"): T_valid_card__Or,
    ("valid_card", "ParentTarget"): T_valid_card__ParentTarget,
    ("valid_card", "ParentTargetSlot"): T_valid_card__ParentTargetSlot,
    ("valid_card", "SelfRef"): T_valid_card__SelfRef,
    ("valid_card", "Typed"): T_valid_card__Typed,
    ("valid_source", "And"): T_valid_source__And,
    ("valid_source", "AttachedTo"): T_valid_source__AttachedTo,
    ("valid_source", "Or"): T_valid_source__Or,
    ("valid_source", "ParentTarget"): T_valid_source__ParentTarget,
    ("valid_source", "Player"): T_valid_source__Player,
    ("valid_source", "SelfRef"): T_valid_source__SelfRef,
    ("valid_source", "StackAbility"): T_valid_source__StackAbility,
    ("valid_source", "StackSpell"): T_valid_source__StackSpell,
    ("valid_source", "Typed"): T_valid_source__Typed,
    ("valid_subject_player", "Controller"): T_valid_subject_player__Controller,
    ("valid_subject_player", "Player"): T_valid_subject_player__Player,
    ("valid_target", "AttachedTo"): T_valid_target__AttachedTo,
    ("valid_target", "Controller"): T_valid_target__Controller,
    ("valid_target", "Or"): T_valid_target__Or,
    ("valid_target", "ParentTargetController"): T_valid_target__ParentTargetController,
    ("valid_target", "Player"): T_valid_target__Player,
    ("valid_target", "SelfRef"): T_valid_target__SelfRef,
    ("valid_target", "SourceChosenPlayer"): T_valid_target__SourceChosenPlayer,
    ("valid_target", "TriggeringPlayer"): T_valid_target__TriggeringPlayer,
    ("valid_target", "Typed"): T_valid_target__Typed,
    ("value", "Difference"): T_value__Difference,
    ("value", "DivideRounded"): T_value__DivideRounded,
    ("value", "Fixed"): T_value__Fixed,
    ("value", "Max"): T_value__Max,
    ("value", "Multiply"): T_value__Multiply,
    ("value", "Offset"): T_value__Offset,
    ("value", "Ref"): T_value__Ref,
    ("value", "Sum"): T_value__Sum,
    ("visibility", "Open"): T_visibility__Open,
    ("visibility", "Secret"): T_visibility__Secret,
    ("voter_scope", "AllPlayers"): T_voter_scope__AllPlayers,
    ("voter_scope", "ControllerLabels"): T_voter_scope__ControllerLabels,
    ("voter_scope", "EachOpponent"): T_voter_scope__EachOpponent,
}

GENERATED_BY_CKEY: dict[str, type[TypedMirrorNode]] = {
    "<root>": S_Root,
    "AddKeywordUntilEndOfTurn": S_AddKeywordUntilEndOfTurn,
    "Affinity": S_Affinity,
    "AlternativeKeywordCost": S_AlternativeKeywordCost,
    "Awaken": S_Awaken,
    "BattlefieldTransition": S_BattlefieldTransition,
    "CantActivateDuring": S_CantActivateDuring,
    "CantBeActivated": S_CantBeActivated,
    "CantCastDuring": S_CantCastDuring,
    "CantPayCost": S_CantPayCost,
    "CastFromHandFree": S_CastFromHandFree,
    "CastWithAlternativeCost": S_CastWithAlternativeCost,
    "CombatAlone": S_CombatAlone,
    "Craft": S_Craft,
    "Crew": S_Crew,
    "CrewContribution": S_CrewContribution,
    "DefilerCostReduction": S_DefilerCostReduction,
    "EntersWithAdditionalCounters": S_EntersWithAdditionalCounters,
    "ExileCastPermission": S_ExileCastPermission,
    "GraveyardCastPermission": S_GraveyardCastPermission,
    "Impending": S_Impending,
    "ImposeAdditionalCost": S_ImposeAdditionalCost,
    "Keyword": S_Keyword,
    "ManaValue": S_ManaValue,
    "MaxAttackersEachCombat": S_MaxAttackersEachCombat,
    "MaxUntapPerType": S_MaxUntapPerType,
    "ModifyActivationLimit": S_ModifyActivationLimit,
    "ModifyCost": S_ModifyCost,
    "MustBeBlockedByAll": S_MustBeBlockedByAll,
    "NumberRange": S_NumberRange,
    "OnlyForSpellWithManaValue": S_OnlyForSpellWithManaValue,
    "PerTurnCastLimit": S_PerTurnCastLimit,
    "PerTurnDrawLimit": S_PerTurnDrawLimit,
    "Prototype": S_Prototype,
    "ReduceAbilityCost": S_ReduceAbilityCost,
    "ReduceActionCost": S_ReduceActionCost,
    "Reinforce": S_Reinforce,
    "RestrictLibrarySearchToTop": S_RestrictLibrarySearchToTop,
    "SpellFromZone": S_SpellFromZone,
    "SpellMatchingCostCriteria": S_SpellMatchingCostCriteria,
    "SpellTypeOrAbilityActivation": S_SpellTypeOrAbilityActivation,
    "SpellWithColorCount": S_SpellWithColorCount,
    "SpellWithKeywordKindFromZone": S_SpellWithKeywordKindFromZone,
    "SpellWithManaValue": S_SpellWithManaValue,
    "SpendManaAsAnyColor": S_SpendManaAsAnyColor,
    "Splice": S_Splice,
    "StepEndUnspentMana": S_StepEndUnspentMana,
    "SuppressTriggers": S_SuppressTriggers,
    "Suspend": S_Suspend,
    "TopOfLibraryCastPermission": S_TopOfLibraryCastPermission,
    "TriggerOnSpend": S_TriggerOnSpend,
    "Typecycling": S_Typecycling,
    "UntilNextStepOf": S_UntilNextStepOf,
    "abilities": S_abilities,
    "ability": S_ability,
    "additional_token_spec": S_additional_token_spec,
    "bracket_signals": S_bracket_signals,
    "branches": S_branches,
    "card_type": S_card_type,
    "cards": S_cards,
    "casting_options": S_casting_options,
    "characteristics": S_characteristics,
    "chosen_pile_effect": S_chosen_pile_effect,
    "cleave_variant": S_cleave_variant,
    "cost_reduction": S_cost_reduction,
    "counter_filter": S_counter_filter,
    "data": S_data,
    "decline": S_decline,
    "definition": S_definition,
    "effect": S_effect,
    "else_ability": S_else_ability,
    "ensure_token_specs": S_ensure_token_specs,
    "execute": S_execute,
    "extra_cost": S_extra_cost,
    "face_down_profile": S_face_down_profile,
    "filter": S_filter,
    "legalities": S_legalities,
    "lose_effect": S_lose_effect,
    "metadata": S_metadata,
    "modal": S_modal,
    "mode_abilities": S_mode_abilities,
    "modification": S_modification,
    "multi_target": S_multi_target,
    "on_decline": S_on_decline,
    "or_trigger": S_or_trigger,
    "outcome_template": S_outcome_template,
    "per_choice_effect": S_per_choice_effect,
    "profile": S_profile,
    "replacement": S_replacement,
    "replacements": S_replacements,
    "requirement": S_requirement,
    "results": S_results,
    "rulings": S_rulings,
    "scale": S_scale,
    "split": S_split,
    "static_abilities": S_static_abilities,
    "static_def": S_static_def,
    "statics": S_statics,
    "sub_ability": S_sub_ability,
    "trigger": S_trigger,
    "triggers": S_triggers,
    "unchosen_pile_effect": S_unchosen_pile_effect,
    "unless_pay": S_unless_pay,
    "win_effect": S_win_effect,
    "zone_change_clauses": S_zone_change_clauses,
}

JSON_TO_PY: dict[str, str] = {
    "from": "from_",
}
