"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``else_ability`` ..
``illegal_targets_disposition`` (31 keys).

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
    from mtg_utils._card_ir.mirror.generated.g02_modifyactivationlimi import (
        U_ability_tag,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_attr,
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        S_characteristics,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        S_definition,
        U_count,
        U_distribute,
    )
    from mtg_utils._card_ir.mirror.generated.g07_dynamic_count import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g09_inner import (
        S_modal,
        S_mode_abilities,
        U_inner,
    )
    from mtg_utils._card_ir.mirror.generated.g10_modifications import (
        S_multi_target,
        U_optional_player,
    )
    from mtg_utils._card_ir.mirror.generated.g11_player import (
        U_player,
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        U_relation,
        U_repeat_for,
        U_repeat_until,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g15_spell_filter import (
        S_static_abilities,
        S_sub_ability,
        U_target_chooser,
        U_target_constraints,
        U_target_selection_mode,
    )
    from mtg_utils._card_ir.mirror.generated.g16_triggers import (
        S_unless_pay,
        U_valid_card,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_else_ability(TypedMirrorNode):
    condition: U_condition | None
    cost: None
    description: str | None
    duration: str | MirrorVariant | None
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: S_sub_ability | None
    target_prompt: None
    multi_target: S_multi_target = MISSING
    optional_player: U_optional_player = MISSING
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
class S_event(TypedMirrorNode):
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
    valid_target: None


@dataclass(frozen=True)
class S_execute(TypedMirrorNode):
    condition: U_condition | None
    cost: None
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
    declares_chosen_group: int = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    entry_onset: str = MISSING
    illegal_targets_disposition: U_illegal_targets_disposition = MISSING
    is_mana_ability: bool = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    optional_player: U_optional_player = MISSING
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
    cause: str
    extra_core_types: list[object]
    subtypes: list[object]
    body: str = MISSING
    power: int = MISSING
    toughness: int = MISSING


@dataclass(frozen=True)
class S_filter(TypedMirrorNode):
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class S_gap(TypedMirrorNode):
    kind: str
    antecedent: str = MISSING
    guard: str = MISSING
    operand: str = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_enchant_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_end_cost__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


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
class T_entry_payment_max__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


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
class T_exclude__None(TypedMirrorNode):
    _tag: ClassVar[str | None] = "None"


@dataclass(frozen=True)
class T_exclude__ParentObjectTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTarget"
    possession: str


@dataclass(frozen=True)
class T_exclude__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_exclude__ParentObjectTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetOwner"


@dataclass(frozen=True)
class T_exclude__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_expiry__EndOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndOfTurn"


@dataclass(frozen=True)
class T_expiry__UntilHostLeavesPlay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UntilHostLeavesPlay"


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
class T_filter__ChosenCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenCard"


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
class T_filter__LastZoneChanged(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastZoneChanged"


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
class T_filter__TrackedSetFiltered(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetFiltered"
    caused_by: str
    filter: U_filter
    id: int


@dataclass(frozen=True)
class T_filter__TrackedSetPossessor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetPossessor"
    filter: U_filter
    possession: str
    relation: U_relation


@dataclass(frozen=True)
class T_filter__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | MirrorVariant | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_filters__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filters__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_filters__ChosenCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenCard"


@dataclass(frozen=True)
class T_filters__ChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenPlayer"
    index: int


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
class T_filters__OpponentAttacked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttacked"
    scope: str
    subject: str


@dataclass(frozen=True)
class T_filters__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_filters__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


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
class T_filters__PlayerMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerMatching"
    player: U_player


@dataclass(frozen=True)
class T_filters__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_filters__SpecificObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpecificObject"
    id: int


@dataclass(frozen=True)
class T_filters__StackAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackAbility"
    controller: str = MISSING
    kind: str = MISSING


@dataclass(frozen=True)
class T_filters__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_filters__TargetPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetPlayer"


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
    controller: str | MirrorVariant | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_flipper__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_flips__Exactly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exactly"
    count: U_count


@dataclass(frozen=True)
class T_flips__UntilLoss(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UntilLoss"


@dataclass(frozen=True)
class T_followed_by__Phase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Phase"
    data: str


@dataclass(frozen=True)
class T_forced_to__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_forced_to__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_grantee__AbilityController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AbilityController"


@dataclass(frozen=True)
class T_grantee__ObjectOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectOwner"


@dataclass(frozen=True)
class T_grantee__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_grantee__TriggeringSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSourceController"


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
class T_graveyard_replacement__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"


@dataclass(frozen=True)
class T_host__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_host__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_illegal_targets_disposition__StillResolves(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StillResolves"


# --- discriminated-union aliases (one per tagged content_key) ---

type U_enchant_filter = T_enchant_filter__Typed
type U_end_cost = T_end_cost__Cost
type U_enter_with_counters = (
    T_enter_with_counters__ClampMin
    | T_enter_with_counters__Fixed
    | T_enter_with_counters__Ref
)
type U_enters_modified_if = T_enters_modified_if__Typed
type U_entry = T_entry__Normal | T_entry__TappedAndAttacking
type U_entry_payment_max = T_entry_payment_max__Sum
type U_entwine_cost = T_entwine_cost__Cost
type U_excess = T_excess__TargetController
type U_exclude = (
    T_exclude__CreatureTypes
    | T_exclude__None
    | T_exclude__ParentObjectTarget
    | T_exclude__ParentObjectTargetController
    | T_exclude__ParentObjectTargetOwner
    | T_exclude__TriggeringPlayer
)
type U_expiry = T_expiry__EndOfTurn | T_expiry__UntilHostLeavesPlay
type U_exponent = T_exponent__Ref
type U_exprs = T_exprs__Fixed | T_exprs__Multiply | T_exprs__Ref
type U_extra_source = T_extra_source__Typed
type U_filter = (
    T_filter__All
    | T_filter__And
    | T_filter__Any
    | T_filter__AttachedTo
    | T_filter__ChosenCard
    | T_filter__Controller
    | T_filter__ControlsCount
    | T_filter__ExiledBySource
    | T_filter__GrantingObject
    | T_filter__HasChosenName
    | T_filter__HasLostTheGame
    | T_filter__LastZoneChanged
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
    | T_filter__TrackedSetFiltered
    | T_filter__TrackedSetPossessor
    | T_filter__TriggeringSource
    | T_filter__Typed
)
type U_filters = (
    T_filters__And
    | T_filters__AttachedTo
    | T_filters__ChosenCard
    | T_filters__ChosenPlayer
    | T_filters__Controller
    | T_filters__ExiledBySource
    | T_filters__HasChosenName
    | T_filters__LastCreated
    | T_filters__Not
    | T_filters__OpponentAttacked
    | T_filters__Or
    | T_filters__ParentObjectTargetController
    | T_filters__ParentTarget
    | T_filters__ParentTargetSlot
    | T_filters__Player
    | T_filters__PlayerMatching
    | T_filters__SelfRef
    | T_filters__SpecificObject
    | T_filters__StackAbility
    | T_filters__StackSpell
    | T_filters__TargetPlayer
    | T_filters__TrackedSet
    | T_filters__TriggeringPlayer
    | T_filters__TriggeringSource
    | T_filters__Typed
)
type U_flipper = T_flipper__TriggeringPlayer
type U_flips = T_flips__Exactly | T_flips__UntilLoss
type U_followed_by = T_followed_by__Phase
type U_forced_to = T_forced_to__ParentTarget | T_forced_to__SelfRef
type U_grantee = (
    T_grantee__AbilityController
    | T_grantee__ObjectOwner
    | T_grantee__ParentTargetController
    | T_grantee__TriggeringSourceController
)
type U_grants = (
    T_grants__GrantAbility | T_grants__GrantStaticAbility | T_grants__RemoveAllAbilities
)
type U_graveyard_replacement = T_graveyard_replacement__Exile
type U_host = T_host__TriggeringSource | T_host__Typed
type U_illegal_targets_disposition = T_illegal_targets_disposition__StillResolves
