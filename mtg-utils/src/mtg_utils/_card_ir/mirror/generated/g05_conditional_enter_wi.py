"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys
``conditional_enter_with_counters`` .. ``costs`` (8 keys).

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
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_amount,
        U_base,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_data,
        U_count,
        U_counter_type,
        U_counters,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_filter,
        U_lhs,
    )
    from mtg_utils._card_ir.mirror.generated.g09_library_position import (
        U_mana_cost,
        U_materials,
    )
    from mtg_utils._card_ir.mirror.generated.g10_payer import (
        U_player,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_quantity,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_until import (
        S_requirement,
        U_rhs,
        U_scaling,
        U_subject,
    )
    from mtg_utils._card_ir.mirror.generated.g14_target import (
        U_target,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_cost_reduction(TypedMirrorNode):
    amount_per: int
    count: U_count
    condition: U_condition = MISSING
    mode: str = MISSING


# --- tagged shapes (discriminated enum nodes) ---


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
class T_conditions__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"
    comparator: str
    rhs: U_rhs


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
class T_conditions__SourceIsEquipped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsEquipped"


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
class T_conditions__TokenSubtypeMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokenSubtypeMatches"
    subtypes: list[object]


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
class T_copy_modifications__AddKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddKeyword"
    keyword: str


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


# --- discriminated-union aliases (one per tagged content_key) ---

type U_conditional_enter_with_counters = (
    T_conditional_enter_with_counters__Fixed | T_conditional_enter_with_counters__Typed
)
type U_conditions = (
    T_conditions__AdditionalCostPaid
    | T_conditions__And
    | T_conditions__AttackersDeclaredCount
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
    | T_conditions__PreviousEffectAmount
    | T_conditions__QuantityCheck
    | T_conditions__QuantityComparison
    | T_conditions__ScopedPlayerMatches
    | T_conditions__SourceEnteredThisTurn
    | T_conditions__SourceInZone
    | T_conditions__SourceIsAttacking
    | T_conditions__SourceIsBlocking
    | T_conditions__SourceIsEquipped
    | T_conditions__SourceIsTapped
    | T_conditions__SourceLacksKeyword
    | T_conditions__SourceMatchesFilter
    | T_conditions__SpellCastWithVariantThisTurn
    | T_conditions__TargetHasKeywordInstead
    | T_conditions__TargetMatchesFilter
    | T_conditions__TokenSubtypeMatches
    | T_conditions__TriggeringSpellMatchesFilter
    | T_conditions__UnlessPay
    | T_conditions__Unrecognized
    | T_conditions__WasCast
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
type U_copy_modifications = (
    T_copy_modifications__AddKeyword | T_copy_modifications__RemoveSupertype
)
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
