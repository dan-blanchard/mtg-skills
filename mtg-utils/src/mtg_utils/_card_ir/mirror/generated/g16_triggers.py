"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``triggers`` ..
``zone_change_clauses`` (16 keys).

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
        U_attack_cost_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_constraint,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        S_counter_filter,
        S_damage_amount,
        U_count,
        U_destination_constraint,
    )
    from mtg_utils._card_ir.mirror.generated.g07_dynamic_count import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_execute,
        U_exprs,
        U_filter,
        U_filters,
    )
    from mtg_utils._card_ir.mirror.generated.g09_inner import (
        U_inner,
        U_left,
        U_mana_ability_produced,
    )
    from mtg_utils._card_ir.mirror.generated.g10_modifications import (
        U_origin,
        U_payer,
    )
    from mtg_utils._card_ir.mirror.generated.g11_player import (
        U_player,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        U_right,
        U_spell_cast_origin,
    )
    from mtg_utils._card_ir.mirror.generated.g15_spell_filter import (
        S_sub_ability,
        U_tag,
        U_threshold,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_triggers(TypedMirrorNode):
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
    attack_cost_condition: U_attack_cost_condition = MISSING
    attack_target_filter: str = MISSING
    clash_result: str = MISSING
    coin_flip_result: str = MISSING
    counter_filter: S_counter_filter | MirrorVariant = MISSING
    damage_amount: S_damage_amount | list[S_damage_amount] = MISSING
    destination_constraint: U_destination_constraint = MISSING
    die_result: MirrorVariant = MISSING
    expend_threshold: int = MISSING
    life_amount: list[object] = MISSING
    mana_ability_produced: U_mana_ability_produced = MISSING
    origin_zones: list[object] = MISSING
    player_actions: list[object] = MISSING
    saga_chapter: int = MISSING
    scry_bottom_count: list[object] = MISSING
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
class S_value(TypedMirrorNode):
    denominator: int
    numerator: int
    rounding: str


@dataclass(frozen=True)
class S_win_effect(TypedMirrorNode):
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
    is_mana_ability: bool = MISSING
    sub_link: str = MISSING


@dataclass(frozen=True)
class S_winner_effect(TypedMirrorNode):
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
class S_zone_change_clauses(TypedMirrorNode):
    origin: U_origin
    valid_card: U_valid_card
    destination: str = MISSING


# --- tagged shapes (discriminated enum nodes) ---


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
    count: U_count = MISSING


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
class T_valid_card__ChosenCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenCard"


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
    controller: str | None
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
class T_valid_source__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


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
    kind: str = MISSING
    tag: U_tag = MISSING


@dataclass(frozen=True)
class T_valid_source__StackSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StackSpell"


@dataclass(frozen=True)
class T_valid_source__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
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
class T_valid_target__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


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
class T_valid_target__PlayerMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerMatching"
    player: U_player


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
    controller: str | None
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

type U_unless_filter = T_unless_filter__Or | T_unless_filter__Typed
type U_until = T_until__CumulativeThreshold | T_until__NextMatches
type U_valid_card = (
    T_valid_card__And
    | T_valid_card__Any
    | T_valid_card__AttachedTo
    | T_valid_card__ChosenCard
    | T_valid_card__Or
    | T_valid_card__ParentTarget
    | T_valid_card__ParentTargetSlot
    | T_valid_card__SelfRef
    | T_valid_card__Typed
)
type U_valid_source = (
    T_valid_source__And
    | T_valid_source__AttachedTo
    | T_valid_source__Controller
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
    | T_valid_target__Opponent
    | T_valid_target__Or
    | T_valid_target__ParentTargetController
    | T_valid_target__Player
    | T_valid_target__PlayerMatching
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
