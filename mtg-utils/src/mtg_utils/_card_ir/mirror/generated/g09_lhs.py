"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``lhs`` .. ``parity`` (38
keys).

Class naming: ``S_<ckey>`` for a struct shape, ``T_<ckey>__<tag>`` for a tagged
shape, ``U_<ckey>`` for the union of all tagged shapes at one content_key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_amount,
        U_cap,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_chooser,
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_constraints,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_data,
        S_decline,
        S_definition,
        U_data,
        U_dynamic_max_choices,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_entwine_cost,
        U_exprs,
        U_filters,
        U_inner,
        U_left,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_replacement,
        S_sub_ability,
        U_repeat_for,
        U_right,
        U_selection,
        U_source,
        U_source_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_trigger,
        S_unless_pay,
        U_target_constraints,
        U_valid_card,
        U_valid_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_lose_effect(TypedMirrorNode):
    condition: None
    cost: None
    description: None
    duration: str | None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: S_sub_ability | None
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
    condition: U_condition | None
    cost: None
    description: None
    duration: str | MirrorVariant | None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: S_sub_ability | None
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
    max: U_max | None
    min: int | U_min


@dataclass(frozen=True)
class S_on_decline(TypedMirrorNode):
    condition: U_condition | None
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
    valid_target: U_valid_target | None


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


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_lhs__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


@dataclass(frozen=True)
class T_lhs__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_lhs__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_lhs__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_library_players__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_library_position__Bottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bottom"


@dataclass(frozen=True)
class T_library_position__RandomWithinTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RandomWithinTop"
    n: U_n


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
class T_max__Difference(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Difference"
    left: U_left
    right: U_right


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
class T_max__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


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
class T_metric__OfColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OfColor"
    color: str


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
    decline: S_decline | None


@dataclass(frozen=True)
class T_mode__Optional(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Optional"
    decline: S_decline | None


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
    mode: str


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
class T_modifications__CopyChosen(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopyChosen"


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
class T_modifications__GrantReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantReplacement"
    replacement: S_replacement


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
class T_modifications__SetTextName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetTextName"
    name: str


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
class T_n__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


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
    controller: str | MirrorVariant | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_parity__LastNamedChoice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastNamedChoice"


# --- discriminated-union aliases (one per tagged content_key) ---

type U_lhs = T_lhs__Difference | T_lhs__Fixed | T_lhs__Ref | T_lhs__Sum
type U_library_players = T_library_players__All
type U_library_position = (
    T_library_position__Bottom
    | T_library_position__RandomWithinTop
    | T_library_position__Top
)
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
type U_max = T_max__Difference | T_max__Fixed | T_max__Offset | T_max__Ref | T_max__Sum
type U_max_ticket_cost = T_max_ticket_cost__Ref
type U_metric = (
    T_metric__DistinctColors
    | T_metric__FromSource
    | T_metric__OfColor
    | T_metric__Total
)
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
    | T_modifications__CopyChosen
    | T_modifications__GrantAbility
    | T_modifications__GrantAllActivatedAbilitiesOf
    | T_modifications__GrantAllTriggeredAbilitiesOf
    | T_modifications__GrantReplacement
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
    | T_modifications__SetTextName
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
type U_n = T_n__Fixed
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
