"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``count`` ..
``dynamic_max_choices`` (21 keys).

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
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_affected,
        U_amount,
        U_candidate_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        S_cost_reduction,
        U_cost,
        U_costs,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_exponent,
        U_exprs,
        U_filter,
        U_filters,
        U_inner,
        U_left,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_multi_target,
        S_outcome_template,
        U_max,
        U_modifications,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
        U_player_scope,
        U_position,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_requirement,
        S_sub_ability,
        U_right,
        U_scope,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_unless_pay,
        U_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


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


# --- tagged shapes (discriminated enum nodes) ---


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
class T_count_source__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


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
class T_damage_modification__PreventionMinus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreventionMinus"
    value: int


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
class T_damage_source_filter__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


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
class T_destination__AnyDefender(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyDefender"


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
    filter: U_filter = MISSING


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


# --- discriminated-union aliases (one per tagged content_key) ---

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
type U_count_source = T_count_source__Typed
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
    | T_damage_modification__PreventionMinus
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
    | T_damage_source_filter__TrackedSet
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
type U_destination = T_destination__AnyDefender
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
