"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``repeat_for`` .. ``subject``
(36 keys).

Class naming: ``S_<ckey>`` for a struct shape, ``T_<ckey>__<tag>`` for a tagged
shape, ``U_<ckey>`` for the union of all tagged shapes at one content_key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.mirror.generated.g02_mutate import (
        U_ability_tag,
        U_activation_restrictions,
        U_activity,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        S_additional_token_spec,
        U_affected,
        U_affected_players,
        U_amount,
        U_announced_x,
        U_attr,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_data,
        U_count,
        U_counter_match,
        U_damage_modification,
        U_damage_source_filter,
        U_distribute,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        S_effect,
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_else_ability,
        S_ensure_token_specs,
        S_execute,
        U_expiry,
        U_filter,
        U_filters,
        U_inner,
        U_left,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_modal,
        S_mode_abilities,
        S_multi_target,
        U_lhs,
        U_mana_modification,
        U_mana_replacement_scope,
        U_mode,
        U_modifications,
        U_owner,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_per_player_condition,
        U_player_scope,
        U_power,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
        U_quantity_modification,
        U_redirect_target,
        U_relation,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_unless_pay,
        U_target,
        U_target_chooser,
        U_target_constraints,
        U_target_selection_mode,
        U_toughness,
        U_valid_card,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_replacement(TypedMirrorNode):
    condition: U_condition | None
    description: str | None
    event: str
    execute: S_execute | None
    mode: U_mode
    valid_card: U_valid_card | None
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
    condition: U_condition | None
    description: str | None
    event: str
    execute: S_execute | None
    mode: U_mode
    valid_card: U_valid_card | None
    additional_token_spec: S_additional_token_spec = MISSING
    combat_scope: str = MISSING
    counter_match: U_counter_match = MISSING
    counter_replacement_subject: str = MISSING
    damage_modification: U_damage_modification = MISSING
    damage_source_filter: U_damage_source_filter = MISSING
    damage_target_filter: str | MirrorVariant = MISSING
    destination_zone: str = MISSING
    draw_scope: str = MISSING
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
    affected: U_affected | None
    affected_zone: str | None
    characteristic_defining: bool
    condition: U_condition | None
    description: str | None
    effect_zone: None
    mode: str | MirrorVariant
    modifications: list[U_modifications]
    attack_defended: str = MISSING
    bypass_beneficiary: str = MISSING
    per_player_condition: U_per_player_condition = MISSING
    protection_does_not_remove: str = MISSING


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
    affected: U_affected | None
    affected_zone: None
    characteristic_defining: bool
    condition: U_condition | None
    description: str
    effect_zone: None
    mode: str | MirrorVariant
    modifications: list[U_modifications]


@dataclass(frozen=True)
class S_sub_ability(TypedMirrorNode):
    condition: U_condition | None
    cost: U_cost | None
    description: str | None
    duration: str | MirrorVariant | None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: S_sub_ability | None
    target_prompt: None
    ability_tag: U_ability_tag = MISSING
    activation_restrictions: list[U_activation_restrictions] = MISSING
    announced_x: U_announced_x = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    is_mana_ability: bool = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    sibling_condition: str = MISSING
    starting_with: str = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_chooser: U_target_chooser = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


# --- tagged shapes (discriminated enum nodes) ---


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
class T_scope__OwnedLinkedExileCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OwnedLinkedExileCard"


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
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_source__Zone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Zone"
    scope: str
    zone: str


@dataclass(frozen=True)
class T_source_filter__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


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
    controller: str | None
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
    duration: str
    static_def: S_static_def


@dataclass(frozen=True)
class T_sources__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
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
class T_spell_filter__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


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
    controller: str | None
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
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


# --- discriminated-union aliases (one per tagged content_key) ---

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
type U_rhs = T_rhs__DivideRounded | T_rhs__Fixed | T_rhs__Offset | T_rhs__Ref
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
    | T_scope__OwnedLinkedExileCard
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
    T_source_filter__And
    | T_source_filter__ChosenDamageSource
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
    T_spell_filter__And
    | T_spell_filter__HasChosenName
    | T_spell_filter__Or
    | T_spell_filter__Typed
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
