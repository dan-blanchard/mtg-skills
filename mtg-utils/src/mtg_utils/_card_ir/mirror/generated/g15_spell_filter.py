"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``spell_filter`` ..
``trigger_source_filter`` (33 keys).

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
        U_activation_restrictions,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_affected,
        U_announced_x,
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_constraint,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        S_data,
        U_count_source,
        U_distribute,
    )
    from mtg_utils._card_ir.mirror.generated.g07_dynamic_count import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_else_ability,
        S_execute,
        U_filter,
        U_filters,
    )
    from mtg_utils._card_ir.mirror.generated.g09_inner import (
        S_modal,
        S_mode_abilities,
        U_lhs,
    )
    from mtg_utils._card_ir.mirror.generated.g10_modifications import (
        S_multi_target,
        U_modifications,
        U_optional_player,
        U_per_player_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g11_player import (
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_qty import (
        S_reads_return_result,
        U_qty,
        U_recipient,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        U_repeat_for,
        U_rhs,
        U_scope,
        U_spell_cast_origin,
    )
    from mtg_utils._card_ir.mirror.generated.g16_triggers import (
        S_unless_pay,
        S_zone_change_clauses,
        U_valid_card,
        U_valid_source,
        U_valid_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


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
    declares_chosen_group: int = MISSING
    declares_return_result: int = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    entry_onset: str = MISSING
    face_down_in_exile: bool = MISSING
    is_mana_ability: bool = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    optional_player: U_optional_player = MISSING
    player_scope: U_player_scope = MISSING
    reads_chosen_group: int = MISSING
    reads_return_result: list[S_reads_return_result] = MISSING
    repeat_for: U_repeat_for = MISSING
    sibling_condition: str = MISSING
    starting_with: str = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_chooser: U_target_chooser = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_reads: str = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_target(TypedMirrorNode):
    role: str
    count_source: U_count_source = MISSING
    recipient: U_recipient = MISSING


@dataclass(frozen=True)
class S_target_condition(TypedMirrorNode):
    comparator: str
    rhs: U_rhs


@dataclass(frozen=True)
class S_trigger(TypedMirrorNode):
    batched: bool
    condition: U_condition | None
    constraint: U_constraint | None
    damage_kind: str
    description: str | None
    destination: str | None
    execute: S_execute | None
    mode: str | MirrorVariant
    optional: bool
    origin: str | None
    phase: str | None
    secondary: bool
    trigger_zones: list[object]
    valid_card: U_valid_card | None
    valid_source: U_valid_source | None
    valid_target: U_valid_target | None
    attack_target_filter: str = MISSING
    coin_flip_result: str = MISSING
    counter_filter: MirrorVariant = MISSING
    spell_cast_origin: U_spell_cast_origin = MISSING
    unless_pay: S_unless_pay = MISSING
    zone_change_clauses: list[S_zone_change_clauses] = MISSING


# --- tagged shapes (discriminated enum nodes) ---


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
class T_stickers__OnObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnObject"
    scope: U_scope


@dataclass(frozen=True)
class T_stickers__ThatSticker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ThatSticker"


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
    filter: U_filter = MISSING


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


@dataclass(frozen=True)
class T_substitution__Chosen(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Chosen"
    data: MirrorVariant


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
class T_target__AmassedArmy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AmassedArmy"


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
class T_target__AttackedPlayerOrPlaneswalker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedPlayerOrPlaneswalker"


@dataclass(frozen=True)
class T_target__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_target__ControllerAndControlledPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerAndControlledPermanents"
    permanent_type: str | None


@dataclass(frozen=True)
class T_target__CostPaidObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObject"


@dataclass(frozen=True)
class T_target__DeclaredPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredPlayer"
    group: int


@dataclass(frozen=True)
class T_target__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_target__EventTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventTarget"


@dataclass(frozen=True)
class T_target__EventTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventTargetController"


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
class T_target__LastRevealed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastRevealed"


@dataclass(frozen=True)
class T_target__LastZoneChanged(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LastZoneChanged"


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
class T_target__SourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceController"


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
class T_target__TriggeringSpellController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellController"


@dataclass(frozen=True)
class T_target__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | MirrorVariant | None
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
    controller: str | None
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
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_chooser__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_target_chooser__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


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
class T_target_player__DeclaredPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredPlayer"
    group: int


@dataclass(frozen=True)
class T_target_player__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_target_player__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_target_player__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_target_player__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_target_player__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_target_selection_mode__Random(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Random"


@dataclass(frozen=True)
class T_targets__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_targets__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


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
class T_to__DeclaredTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredTarget"
    slot: int


@dataclass(frozen=True)
class T_to__Host(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Host"
    filter: U_filter


@dataclass(frozen=True)
class T_to__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"
    player: str


@dataclass(frozen=True)
class T_to__Recipient(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Recipient"


@dataclass(frozen=True)
class T_to__Source(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Source"


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
class T_toughness__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_toughness__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    value: str


@dataclass(frozen=True)
class T_trigger_source_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


# --- discriminated-union aliases (one per tagged content_key) ---

type U_spell_filter = (
    T_spell_filter__And
    | T_spell_filter__HasChosenName
    | T_spell_filter__Or
    | T_spell_filter__Typed
)
type U_state = T_state__Tap | T_state__Untap
type U_step = T_step__CombatPhase | T_step__Step
type U_stickers = T_stickers__OnObject | T_stickers__ThatSticker
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
type U_substitution = T_substitution__Chosen
type U_subtype_filter = T_subtype_filter__Or | T_subtype_filter__Typed
type U_tag = T_tag__Backup
type U_tally_mode = T_tally_mode__PerVote | T_tally_mode__TopVotes
type U_target = (
    T_target__AllPlayers
    | T_target__AmassedArmy
    | T_target__And
    | T_target__Any
    | T_target__AttachedTo
    | T_target__AttackedPlayerOrPlaneswalker
    | T_target__Controller
    | T_target__ControllerAndControlledPermanents
    | T_target__CostPaidObject
    | T_target__DeclaredPlayer
    | T_target__DefendingPlayer
    | T_target__EventTarget
    | T_target__EventTargetController
    | T_target__ExiledBySource
    | T_target__ExiledCardByIndex
    | T_target__GrantingObject
    | T_target__LastCreated
    | T_target__LastRevealed
    | T_target__LastZoneChanged
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
    | T_target__SourceController
    | T_target__StackAbility
    | T_target__StackSpell
    | T_target__TrackedSet
    | T_target__TrackedSetFiltered
    | T_target__TriggeringPlayer
    | T_target__TriggeringSource
    | T_target__TriggeringSpellController
    | T_target__Typed
)
type U_target_a = (
    T_target_a__And | T_target_a__Or | T_target_a__SelfRef | T_target_a__Typed
)
type U_target_b = T_target_b__Or | T_target_b__TriggeringSource | T_target_b__Typed
type U_target_chooser = (
    T_target_chooser__Opponent
    | T_target_chooser__ParentTargetController
    | T_target_chooser__ScopedPlayer
)
type U_target_constraints = (
    T_target_constraints__DifferentObjectControllers
    | T_target_constraints__SameZoneOwner
    | T_target_constraints__TotalManaValue
)
type U_target_kind = (
    T_target_kind__Counters | T_target_kind__LifeTotal | T_target_kind__ManaPool
)
type U_target_player = (
    T_target_player__DeclaredPlayer
    | T_target_player__ParentTarget
    | T_target_player__ParentTargetController
    | T_target_player__Player
    | T_target_player__ScopedPlayer
    | T_target_player__Typed
)
type U_target_selection_mode = T_target_selection_mode__Random
type U_targets = T_targets__SelfRef | T_targets__Typed
type U_threshold = T_threshold__Fixed
type U_tie = T_tie__AllTied | T_tie__Breaker
type U_timing = T_timing__AtNextPhase
type U_to = (
    T_to__DeclaredTarget | T_to__Host | T_to__Player | T_to__Recipient | T_to__Source
)
type U_total_power_cap = T_total_power_cap__Fixed
type U_toughness = (
    T_toughness__Fixed
    | T_toughness__Quantity
    | T_toughness__Ref
    | T_toughness__Variable
)
type U_trigger_source_filter = T_trigger_source_filter__Typed
