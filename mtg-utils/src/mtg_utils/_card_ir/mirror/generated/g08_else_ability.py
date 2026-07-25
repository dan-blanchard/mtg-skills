"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``else_ability`` ..
``library_players`` (35 keys).

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
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        S_characteristics,
        U_attr,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_conditions,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_definition,
        U_count,
        U_distribute,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g09_library_position import (
        S_modal,
        S_mode_abilities,
        S_multi_target,
    )
    from mtg_utils._card_ir.mirror.generated.g10_payer import (
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
        U_relation,
        U_repeat_for,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_until import (
        S_static_abilities,
        S_sub_ability,
        U_repeat_until,
        U_rhs,
        U_right,
        U_source,
        U_subtype_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g14_target import (
        S_unless_pay,
        U_target_chooser,
        U_target_constraints,
        U_target_selection_mode,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


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


# --- tagged shapes (discriminated enum nodes) ---


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
class T_entry__Normal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Normal"


@dataclass(frozen=True)
class T_entry__TappedAndAttacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TappedAndAttacking"
    data: MirrorVariant


@dataclass(frozen=True)
class T_entwine_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_excess__TargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetController"
    source_keyword: str = MISSING


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
class T_filter__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


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
class T_filter__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


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
class T_grants__GrantStaticAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantStaticAbility"
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
class T_inner__CastVariantPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaid"
    variant: str


@dataclass(frozen=True)
class T_inner__ClampMin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClampMin"
    inner: U_inner
    minimum: int


@dataclass(frozen=True)
class T_inner__CompletedDungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CompletedDungeon"


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
class T_inner__WasCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasCast"
    zone: str


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
class T_keep_on_top__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_keeper_constraint__exact_count(TypedMirrorNode):
    _tag: ClassVar[str | None] = "exact_count"
    count: U_count


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
class T_land_filter__HasChosenName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasChosenName"


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


# --- discriminated-union aliases (one per tagged content_key) ---

type U_enchant_filter = T_enchant_filter__Typed
type U_enter_with_counters = (
    T_enter_with_counters__ClampMin
    | T_enter_with_counters__Fixed
    | T_enter_with_counters__Offset
    | T_enter_with_counters__Ref
)
type U_enters_modified_if = T_enters_modified_if__Typed
type U_entry = T_entry__Normal | T_entry__TappedAndAttacking
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
    | T_filter__AttachedTo
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
    | T_filter__OpponentLostLife
    | T_filter__OpponentOfTriggeringPlayerNotAttacked
    | T_filter__Or
    | T_filter__ParentTarget
    | T_filter__PerformedActionThisWay
    | T_filter__Player
    | T_filter__PlayerAttribute
    | T_filter__SelfRef
    | T_filter__TrackedSet
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
type U_grants = (
    T_grants__GrantAbility | T_grants__GrantStaticAbility | T_grants__RemoveAllAbilities
)
type U_host = T_host__TriggeringSource | T_host__Typed
type U_inner = (
    T_inner__And
    | T_inner__CastDuringPhase
    | T_inner__CastVariantPaid
    | T_inner__ClampMin
    | T_inner__CompletedDungeon
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
    | T_inner__WasCast
    | T_inner__ZoneChangeObjectMatchesFilter
    | T_inner__ZoneChangedThisWay
)
type U_invalidation = T_invalidation__UntilNextGrantFromSameSource
type U_iteration_kind_binding = T_iteration_kind_binding__RebindToIteratedKind
type U_keep_count_expr = T_keep_count_expr__Ref
type U_keep_on_top = T_keep_on_top__Fixed
type U_keeper_constraint = T_keeper_constraint__exact_count
type U_kind = T_kind__Card | T_kind__Food | T_kind__TappedFish | T_kind__Treasure
type U_land_filter = T_land_filter__HasChosenName | T_land_filter__Typed
type U_left = T_left__Ref
type U_lhs = T_lhs__Difference | T_lhs__Ref | T_lhs__Sum
type U_library_players = T_library_players__All
