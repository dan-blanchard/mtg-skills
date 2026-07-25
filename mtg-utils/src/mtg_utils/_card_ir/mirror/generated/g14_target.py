"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``target`` ..
``zone_change_clauses`` (29 keys).

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
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_constraint,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_counter_filter,
        U_destination_constraint,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_execute,
        U_exprs,
        U_filter,
        U_filters,
        U_inner,
        U_left,
    )
    from mtg_utils._card_ir.mirror.generated.g09_library_position import (
        U_origin,
    )
    from mtg_utils._card_ir.mirror.generated.g10_payer import (
        U_payer,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_until import (
        S_sub_ability,
        U_right,
        U_spell_cast_origin,
        U_tag,
    )


# --- struct shapes (untagged records, one per content_key) ---


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
class S_unit_span(TypedMirrorNode):
    end_byte: int
    first_line: int
    last_line: int
    ordinal_within_span: int
    precision: str
    start_byte: int


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
    sub_ability: None | S_sub_ability
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
class T_target__ControllerAndControlledPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerAndControlledPermanents"
    permanent_type: None | str


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
class T_target__PostReplacementDamageSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageSource"


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
class T_target_chooser__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


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
class T_timing__AtNextPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtNextPhase"
    phase: str


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

type U_target = (
    T_target__AllPlayers
    | T_target__And
    | T_target__Any
    | T_target__AttachedTo
    | T_target__Controller
    | T_target__ControllerAndControlledPermanents
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
    | T_target__PostReplacementDamageSource
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
type U_target_chooser = T_target_chooser__Opponent | T_target_chooser__ScopedPlayer
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
type U_timing = T_timing__AtNextPhase
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
