"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``modifications`` ..
``pile_source`` (26 keys).

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
        S_cast_cost_modifier,
        U_alt_ability_cost,
        U_cap,
        U_card_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        S_data,
        S_definition,
        U_data,
    )
    from mtg_utils._card_ir.mirror.generated.g07_dynamic_count import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_gap,
    )
    from mtg_utils._card_ir.mirror.generated.g09_inner import (
        U_invalidation,
        U_lhs,
        U_max,
        U_min,
    )
    from mtg_utils._card_ir.mirror.generated.g11_player import (
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        S_replacement,
        U_rhs,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g15_spell_filter import (
        S_sub_ability,
        S_trigger,
        U_substitution,
    )
    from mtg_utils._card_ir.mirror.generated.g16_triggers import (
        S_unit_span,
        U_valid_card,
        U_valid_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


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


@dataclass(frozen=True)
class S_per_choice_effect(TypedMirrorNode):
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
    declares_chosen_group: int = MISSING
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    target_choice_timing: str = MISSING


# --- tagged shapes (discriminated enum nodes) ---


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
class T_modifications__SubstituteTextWord(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SubstituteTextWord"
    substitution: U_substitution


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
class T_noun__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


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
class T_optional_player__DeclaredPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredPlayer"
    group: int


@dataclass(frozen=True)
class T_optional_player__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_optional_player__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_optional_player__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_optional_player__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


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
class T_owner__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_owner__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_owner__DeclaredPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredPlayer"
    group: int


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
    unit_span: S_unit_span
    gap: S_gap = MISSING
    items: list[object] = MISSING


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
class T_partner_filter__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_partner_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_payer__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_payer__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_payer__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_payer__EventTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventTargetController"


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
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_per_player_condition__QuantityComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityComparison"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


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
    alt_ability_cost: U_alt_ability_cost = MISSING
    card_filter: U_card_filter = MISSING
    cast_cost_modifier: S_cast_cost_modifier = MISSING
    frequency: str = MISSING
    invalidation: U_invalidation = MISSING
    land_enter_tapped: str = MISSING
    mana_spend_permission: str = MISSING
    mode: str = MISSING
    single_use: bool = MISSING
    without_paying_mana_cost: bool = MISSING


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


# --- discriminated-union aliases (one per tagged content_key) ---

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
    | T_modifications__SetPower
    | T_modifications__SetPowerDynamic
    | T_modifications__SetTextName
    | T_modifications__SetToughness
    | T_modifications__SetToughnessDynamic
    | T_modifications__SubstituteTextWord
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
type U_noun = T_noun__Typed
type U_object_filter = T_object_filter__Any | T_object_filter__Typed
type U_object_source = T_object_source__ParentTarget | T_object_source__TrackedSet
type U_once_per_turn = T_once_per_turn__OnlyOnceEachTurn
type U_only_tag = T_only_tag__PowerUp
type U_op = T_op__LockOrUnlock | T_op__Unlock
type U_optional_player = (
    T_optional_player__DeclaredPlayer
    | T_optional_player__DefendingPlayer
    | T_optional_player__ParentTargetController
    | T_optional_player__ScopedPlayer
    | T_optional_player__TriggeringPlayer
)
type U_origin = T_origin__Equals | T_origin__NotEquals | T_origin__OneOf
type U_origin_constraint = T_origin_constraint__Equals
type U_owner = (
    T_owner__AttachedTo
    | T_owner__Controller
    | T_owner__DeclaredPlayer
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
type U_partner_filter = T_partner_filter__Any | T_partner_filter__Typed
type U_payer = (
    T_payer__AllPlayers
    | T_payer__Controller
    | T_payer__DefendingPlayer
    | T_payer__EventTargetController
    | T_payer__ParentTargetController
    | T_payer__Player
    | T_payer__ScopedPlayer
    | T_payer__TriggeringPlayer
    | T_payer__TriggeringSpellController
    | T_payer__Typed
)
type U_per_player_condition = (
    T_per_player_condition__QuantityComparison
    | T_per_player_condition__YouAttackedSourceControllerThisTurn
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
