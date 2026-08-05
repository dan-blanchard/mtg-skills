"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``Mutate`` ..
``additional_filter`` (60 keys).

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
        U_alt_cost,
        U_announced_x,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        S_cost_reduction,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        S_data,
        U_count,
        U_data,
        U_distribute,
        U_dynamic_count,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_else_ability,
        U_filter,
        U_filters,
        U_land_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_modal,
        S_mode_abilities,
        S_multi_target,
        U_only_tag,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_sub_ability,
        U_repeat_for,
        U_repeat_until,
        U_source_filter,
        U_spell_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_unless_pay,
        U_target,
        U_target_chooser,
        U_target_constraints,
        U_target_selection_mode,
        U_timing,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_NumberRange(TypedMirrorNode):
    max: int
    min: int
    distinctness: str = MISSING


@dataclass(frozen=True)
class S_PerTurnCastLimit(TypedMirrorNode):
    max: int
    spell_filter: None | U_spell_filter
    who: str


@dataclass(frozen=True)
class S_PerTurnDrawLimit(TypedMirrorNode):
    max: int
    who: str


@dataclass(frozen=True)
class S_PlayerOrPermanentsControlledBy(TypedMirrorNode):
    permanent_type: None
    player: U_player


@dataclass(frozen=True)
class S_Prototype(TypedMirrorNode):
    cost: U_cost
    power: int
    toughness: int


@dataclass(frozen=True)
class S_ReduceAbilityCost(TypedMirrorNode):
    amount: int
    exemption: str
    keyword: str
    mode: str
    activator: U_activator = MISSING
    dynamic_count: U_dynamic_count = MISSING
    minimum_mana: int = MISSING


@dataclass(frozen=True)
class S_ReduceActionCost(TypedMirrorNode):
    action: str
    amount: int
    mode: str


@dataclass(frozen=True)
class S_Reinforce(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_RestrictLibrarySearchToTop(TypedMirrorNode):
    count: int
    who: str


@dataclass(frozen=True)
class S_ReturnTo(TypedMirrorNode):
    destination: str
    timing: U_timing


@dataclass(frozen=True)
class S_SpellFromZone(TypedMirrorNode):
    polarity: str
    zone: str


@dataclass(frozen=True)
class S_SpellMatchingCostCriteria(TypedMirrorNode):
    criteria: list[MirrorVariant]
    spell_type: str


@dataclass(frozen=True)
class S_SpellTypeOrAbilityActivation(TypedMirrorNode):
    ability: str
    spell_type: str


@dataclass(frozen=True)
class S_SpellWithColorCount(TypedMirrorNode):
    comparator: str
    count: int


@dataclass(frozen=True)
class S_SpellWithKeywordKindFromZone(TypedMirrorNode):
    kind: str
    zone: str


@dataclass(frozen=True)
class S_SpellWithManaValue(TypedMirrorNode):
    comparator: str
    value: int


@dataclass(frozen=True)
class S_SpendManaAsAnyColor(TypedMirrorNode):
    pass


@dataclass(frozen=True)
class S_Splice(TypedMirrorNode):
    cost: U_cost
    subtype: str


@dataclass(frozen=True)
class S_StepEndUnspentMana(TypedMirrorNode):
    action: str | MirrorVariant
    filter: None | str


@dataclass(frozen=True)
class S_SuppressTriggers(TypedMirrorNode):
    events: list[object]
    source_filter: U_source_filter


@dataclass(frozen=True)
class S_Suspend(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_TopOfLibraryCastPermission(TypedMirrorNode):
    alt_cost: None | U_alt_cost
    frequency: str
    play_mode: str


@dataclass(frozen=True)
class S_TriggerOnSpend(TypedMirrorNode):
    ability: S_ability
    filter: U_filter


@dataclass(frozen=True)
class S_Typecycling(TypedMirrorNode):
    cost: U_cost
    subtype: str


@dataclass(frozen=True)
class S_UntilNextStepOf(TypedMirrorNode):
    player: U_player
    step: str


@dataclass(frozen=True)
class S_abilities(TypedMirrorNode):
    condition: None | U_condition
    cost: None | U_cost
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
    activation_mana_payment_restriction: str = MISSING
    activation_restrictions: list[U_activation_restrictions] = MISSING
    activation_zone: str = MISSING
    activator_filter: U_activator_filter = MISSING
    announced_x: U_announced_x = MISSING
    cant_be_copied: bool = MISSING
    consumes_source: bool = MISSING
    cost_reduction: S_cost_reduction = MISSING
    distribute: U_distribute = MISSING
    else_ability: S_else_ability = MISSING
    is_mana_ability: bool = MISSING
    min_x_value: int = MISSING
    modal: S_modal = MISSING
    mode_abilities: list[S_mode_abilities] = MISSING
    multi_target: S_multi_target = MISSING
    optional_for: str = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    repeat_until: U_repeat_until = MISSING
    starting_with: str = MISSING
    sub_link: str = MISSING
    target_choice_timing: str = MISSING
    target_chooser: U_target_chooser = MISSING
    target_constraints: list[U_target_constraints] = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


@dataclass(frozen=True)
class S_ability(TypedMirrorNode):
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


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_Mutate__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Ninjutsu__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Offspring__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Outlast__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Overload__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Partner__CharacterSelect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CharacterSelect"


@dataclass(frozen=True)
class T_Partner__ChooseABackground(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseABackground"


@dataclass(frozen=True)
class T_Partner__DoctorsCompanion(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoctorsCompanion"


@dataclass(frozen=True)
class T_Partner__FriendsForever(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FriendsForever"


@dataclass(frozen=True)
class T_Partner__Generic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Generic"


@dataclass(frozen=True)
class T_Partner__With(TypedMirrorNode):
    _tag: ClassVar[str | None] = "With"
    data: str


@dataclass(frozen=True)
class T_Plot__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Prowl__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Quality__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_Quality__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_Quality__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Reconfigure__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Recover__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Replicate__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Replicate__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Scavenge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Scavenge__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Sneak__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Specialize__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Spectacle__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Squad__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Surge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Transfigure__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Transmute__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Unearth__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Ward__Compound(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Compound"
    data: list[U_data | S_data | MirrorVariant]


@dataclass(frozen=True)
class T_Ward__DiscardCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DiscardCard"


@dataclass(frozen=True)
class T_Ward__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Ward__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    data: int


@dataclass(frozen=True)
class T_Ward__PayLifeEqualToPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLifeEqualToPower"


@dataclass(frozen=True)
class T_Ward__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    data: S_data


@dataclass(frozen=True)
class T_Ward__Waterbend(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Waterbend"
    data: U_data


@dataclass(frozen=True)
class T_Warp__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_WebSlinging__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_ability_tag__Augment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Augment"


@dataclass(frozen=True)
class T_ability_tag__Backup(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Backup"


@dataclass(frozen=True)
class T_ability_tag__Boast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Boast"


@dataclass(frozen=True)
class T_ability_tag__Cycling(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cycling"


@dataclass(frozen=True)
class T_ability_tag__Equip(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equip"


@dataclass(frozen=True)
class T_ability_tag__Evolve(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Evolve"


@dataclass(frozen=True)
class T_ability_tag__Exhaust(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exhaust"


@dataclass(frozen=True)
class T_ability_tag__Outlast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Outlast"


@dataclass(frozen=True)
class T_ability_tag__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_action__exile_from_pool(TypedMirrorNode):
    _tag: ClassVar[str | None] = "exile_from_pool"
    up_to: bool
    zone: str


@dataclass(frozen=True)
class T_action__put_counter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "put_counter"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_activation_restrictions__AsInstant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AsInstant"


@dataclass(frozen=True)
class T_activation_restrictions__AsSorcery(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AsSorcery"


@dataclass(frozen=True)
class T_activation_restrictions__BeforeAttackersDeclared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeAttackersDeclared"


@dataclass(frozen=True)
class T_activation_restrictions__BeforeCombatDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeforeCombatDamage"


@dataclass(frozen=True)
class T_activation_restrictions__ClassLevelIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClassLevelIs"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__CounterThreshold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterThreshold"
    data: S_data


@dataclass(frozen=True)
class T_activation_restrictions__DuringCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringCombat"


@dataclass(frozen=True)
class T_activation_restrictions__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_activation_restrictions__DuringYourUpkeep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourUpkeep"


@dataclass(frozen=True)
class T_activation_restrictions__IsSolved(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsSolved"


@dataclass(frozen=True)
class T_activation_restrictions__LevelCounterRange(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LevelCounterRange"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__MatchesCardCastTiming(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesCardCastTiming"


@dataclass(frozen=True)
class T_activation_restrictions__MaxTimesEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MaxTimesEachTurn"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_restrictions__OnlyOnce(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnce"


@dataclass(frozen=True)
class T_activation_restrictions__OnlyOnceEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyOnceEachTurn"


@dataclass(frozen=True)
class T_activation_restrictions__RequiresCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RequiresCondition"
    data: MirrorVariant


@dataclass(frozen=True)
class T_activation_source_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_activator__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_activator__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_activator_filter__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_activator_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_activity__ActivateAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ActivateAbilities"
    exemption: str
    only_tag: U_only_tag = MISSING


@dataclass(frozen=True)
class T_activity__Attack(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attack"
    defended: str


@dataclass(frozen=True)
class T_activity__CastOnlyFromZones(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastOnlyFromZones"
    allowed_zones: list[object]


@dataclass(frozen=True)
class T_activity__CastSpells(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastSpells"
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_activity__PlayLands(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayLands"
    land_filter: U_land_filter


@dataclass(frozen=True)
class T_activity__ProhibitPlayFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProhibitPlayFromZone"
    zone: str


@dataclass(frozen=True)
class T_additional_cost__Choice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Choice"
    data: list[U_data | S_data | MirrorVariant]


@dataclass(frozen=True)
class T_additional_cost__Kicker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Kicker"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_additional_cost__Optional(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Optional"
    data: S_data | MirrorVariant


@dataclass(frozen=True)
class T_additional_cost__Required(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Required"
    data: U_data


@dataclass(frozen=True)
class T_additional_filter__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_additional_filter__IsChosenCreatureType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCreatureType"


@dataclass(frozen=True)
class T_additional_filter__MatchesLastChosenCardPredicate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesLastChosenCardPredicate"


# --- discriminated-union aliases (one per tagged content_key) ---

type U_Mutate = T_Mutate__Cost
type U_Ninjutsu = T_Ninjutsu__Cost
type U_Offspring = T_Offspring__Cost
type U_Outlast = T_Outlast__Cost
type U_Overload = T_Overload__Cost
type U_Partner = (
    T_Partner__CharacterSelect
    | T_Partner__ChooseABackground
    | T_Partner__DoctorsCompanion
    | T_Partner__FriendsForever
    | T_Partner__Generic
    | T_Partner__With
)
type U_Plot = T_Plot__Cost
type U_Prowl = T_Prowl__Cost
type U_Quality = T_Quality__Any | T_Quality__Or | T_Quality__Typed
type U_Reconfigure = T_Reconfigure__Cost
type U_Recover = T_Recover__Cost
type U_Replicate = T_Replicate__Cost | T_Replicate__SelfManaCost
type U_Scavenge = T_Scavenge__Cost | T_Scavenge__SelfManaCost
type U_Sneak = T_Sneak__Cost
type U_Specialize = T_Specialize__Cost
type U_Spectacle = T_Spectacle__Cost
type U_Squad = T_Squad__Cost
type U_Surge = T_Surge__Cost
type U_Transfigure = T_Transfigure__Cost
type U_Transmute = T_Transmute__Cost
type U_Unearth = T_Unearth__Cost
type U_Ward = (
    T_Ward__Compound
    | T_Ward__DiscardCard
    | T_Ward__Mana
    | T_Ward__PayLife
    | T_Ward__PayLifeEqualToPower
    | T_Ward__Sacrifice
    | T_Ward__Waterbend
)
type U_Warp = T_Warp__Cost
type U_WebSlinging = T_WebSlinging__Cost
type U_ability_tag = (
    T_ability_tag__Augment
    | T_ability_tag__Backup
    | T_ability_tag__Boast
    | T_ability_tag__Cycling
    | T_ability_tag__Equip
    | T_ability_tag__Evolve
    | T_ability_tag__Exhaust
    | T_ability_tag__Outlast
    | T_ability_tag__PowerUp
)
type U_action = T_action__exile_from_pool | T_action__put_counter
type U_activation_restrictions = (
    T_activation_restrictions__AsInstant
    | T_activation_restrictions__AsSorcery
    | T_activation_restrictions__BeforeAttackersDeclared
    | T_activation_restrictions__BeforeCombatDamage
    | T_activation_restrictions__ClassLevelIs
    | T_activation_restrictions__CounterThreshold
    | T_activation_restrictions__DuringCombat
    | T_activation_restrictions__DuringYourTurn
    | T_activation_restrictions__DuringYourUpkeep
    | T_activation_restrictions__IsSolved
    | T_activation_restrictions__LevelCounterRange
    | T_activation_restrictions__MatchesCardCastTiming
    | T_activation_restrictions__MaxTimesEachTurn
    | T_activation_restrictions__OnlyOnce
    | T_activation_restrictions__OnlyOnceEachTurn
    | T_activation_restrictions__RequiresCondition
)
type U_activation_source_filter = T_activation_source_filter__Typed
type U_activator = T_activator__Controller | T_activator__Opponent
type U_activator_filter = T_activator_filter__All | T_activator_filter__Opponent
type U_activity = (
    T_activity__ActivateAbilities
    | T_activity__Attack
    | T_activity__CastOnlyFromZones
    | T_activity__CastSpells
    | T_activity__PlayLands
    | T_activity__ProhibitPlayFromZone
)
type U_additional_cost = (
    T_additional_cost__Choice
    | T_additional_cost__Kicker
    | T_additional_cost__Optional
    | T_additional_cost__Required
)
type U_additional_filter = (
    T_additional_filter__Cmc
    | T_additional_filter__IsChosenCreatureType
    | T_additional_filter__MatchesLastChosenCardPredicate
)
