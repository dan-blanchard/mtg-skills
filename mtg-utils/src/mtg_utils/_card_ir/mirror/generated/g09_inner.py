"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``inner`` .. ``modification``
(39 keys).

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
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        U_chooser,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_conditions,
        U_constraints,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        S_decline,
        U_count,
    )
    from mtg_utils._card_ir.mirror.generated.g07_dynamic_count import (
        U_dynamic_max_choices,
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_entwine_cost,
        U_exprs,
        U_filter,
        U_filters,
    )
    from mtg_utils._card_ir.mirror.generated.g10_modifications import (
        S_multi_target,
        U_modifications,
        U_n,
    )
    from mtg_utils._card_ir.mirror.generated.g11_player import (
        U_player_scope,
        U_power,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        U_repeat_for,
        U_rhs,
        U_right,
        U_selection,
        U_source_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g15_spell_filter import (
        S_sub_ability,
        U_subtype_filter,
        U_target_constraints,
        U_toughness,
    )
    from mtg_utils._card_ir.mirror.generated.g16_triggers import (
        S_unless_pay,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_keeper_counter(TypedMirrorNode):
    count: U_count
    counter_type: str


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
    declares_chosen_group: int = MISSING
    entry_onset: str = MISSING
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
    modifications: list[U_modifications] = MISSING
    power: int | U_power = MISSING
    toughness: int | U_toughness = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_inner__AbilityUseCountThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AbilityUseCountThisTurn"
    n: int


@dataclass(frozen=True)
class T_inner__AdditionalCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaid"
    origin: str


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
class T_inner__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_inner__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    condition: U_condition


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
class T_journal__SpellsCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCast"


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
class T_kept_destination_if__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_keyword__Equip(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equip"


@dataclass(frozen=True)
class T_kind__Card(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Card"


@dataclass(frozen=True)
class T_kind__ExtraTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExtraTurn"


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
class T_letters__Letter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Letter"
    letter: str


@dataclass(frozen=True)
class T_letters__UniqueVowels(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UniqueVowels"


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
class T_library_shuffle__TerminalShuffle(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TerminalShuffle"


@dataclass(frozen=True)
class T_life_payment__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_mana_ability_produced__SourceChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceChosenColor"


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
class T_modification__Times(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Times"
    factor: int


# --- discriminated-union aliases (one per tagged content_key) ---

type U_inner = (
    T_inner__AbilityUseCountThisTurn
    | T_inner__AdditionalCostPaid
    | T_inner__And
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
    | T_inner__Multiply
    | T_inner__Not
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
type U_journal = T_journal__SpellsCast
type U_keep_count_expr = T_keep_count_expr__Ref
type U_keep_on_top = T_keep_on_top__Fixed
type U_keeper_constraint = T_keeper_constraint__exact_count
type U_kept_destination_if = T_kept_destination_if__Typed
type U_keyword = T_keyword__Equip
type U_kind = (
    T_kind__Card
    | T_kind__ExtraTurn
    | T_kind__Food
    | T_kind__TappedFish
    | T_kind__Treasure
)
type U_land_filter = T_land_filter__HasChosenName | T_land_filter__Typed
type U_left = T_left__Ref
type U_letters = T_letters__Letter | T_letters__UniqueVowels
type U_lhs = T_lhs__Difference | T_lhs__Fixed | T_lhs__Ref | T_lhs__Sum
type U_library_players = T_library_players__All
type U_library_position = (
    T_library_position__Bottom
    | T_library_position__RandomWithinTop
    | T_library_position__Top
)
type U_library_shuffle = T_library_shuffle__TerminalShuffle
type U_life_payment = T_life_payment__Fixed
type U_mana_ability_produced = T_mana_ability_produced__SourceChosenColor
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
type U_modification = T_modification__Double | T_modification__Times
