"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``additional_modifications``
.. ``choose_scope`` (30 keys).

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
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
        U_costs,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_definition,
        U_count,
        U_direction,
        U_duplicate_of,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_enter_with_counters,
        U_exprs,
        U_filter,
        U_filters,
        U_inner,
        U_iteration_kind_binding,
        U_left,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_static_abilities,
        S_sub_ability,
        U_right,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_trigger,
        U_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


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
    description: str | None
    duration: str | None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: S_sub_ability | None
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
    power: int | None
    subtypes: list[object]
    supertypes: list[object]
    toughness: int | None


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_additional_modifications__AddColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddColor"
    color: str


@dataclass(frozen=True)
class T_additional_modifications__AddCounterOnEnter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddCounterOnEnter"
    count: U_count
    counter_type: str
    if_type: str | None


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
class T_additional_modifications__RetainAllOtherAbilitiesFromSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RetainAllOtherAbilitiesFromSource"


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
    controller: str | None
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
class T_announced_x__Offset(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Offset"
    inner: U_inner
    offset: int


@dataclass(frozen=True)
class T_announced_x__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_attach_to__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_attach_to__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_attachment__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_attachment__LastCreated(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastCreated"


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
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_attacker__EventSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventSource"


@dataclass(frozen=True)
class T_attacker__Source(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Source"


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
    controller: str | None
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
class T_casting_restrictions__CantSpendMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CantSpendMana"


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
class T_choose_scope__Chooser(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Chooser"


@dataclass(frozen=True)
class T_choose_scope__Neighbor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Neighbor"
    direction: U_direction


# --- discriminated-union aliases (one per tagged content_key) ---

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
    | T_additional_modifications__RetainAllOtherAbilitiesFromSource
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
type U_announced_x = T_announced_x__Offset | T_announced_x__Ref
type U_attach_to = T_attach_to__ParentTarget | T_attach_to__Typed
type U_attachment = (
    T_attachment__Any
    | T_attachment__LastCreated
    | T_attachment__Or
    | T_attachment__ParentTarget
    | T_attachment__ParentTargetSlot
    | T_attachment__SelfRef
    | T_attachment__TriggeringSource
    | T_attachment__Typed
)
type U_attacker = T_attacker__EventSource | T_attacker__Source
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
    | T_casting_restrictions__CantSpendMana
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
type U_choose_scope = T_choose_scope__Chooser | T_choose_scope__Neighbor
