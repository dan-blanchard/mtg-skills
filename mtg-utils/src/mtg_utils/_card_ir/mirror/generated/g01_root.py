"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``<root>`` ..
``MustBeBlockedByAll`` (74 keys).

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
    from mtg_utils._card_ir.mirror.generated.g02_mutate import (
        S_abilities,
        U_additional_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        S_bracket_signals,
        S_card_type,
        S_casting_options,
        U_amount,
        U_casting_restrictions,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        S_cleave_variant,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
        U_costs,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_count,
        U_data,
        U_deck_copy_limit,
        U_dynamic_count,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_extra_cost,
        S_legalities,
        U_filter,
        U_filters,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_metadata,
        S_modal,
        U_mana_cost,
        U_mana_reduction,
        U_materials,
        U_once_per_turn,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_parse_warnings,
        U_power,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        S_reduction,
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_replacements,
        S_requirement,
        S_rulings,
        S_static_abilities,
        U_solve_condition,
        U_source_filter,
        U_spell_filter,
        U_strive_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_triggers,
        U_target,
        U_toughness,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_Root(TypedMirrorNode):
    abilities: list[S_abilities]
    card_type: S_card_type
    color_override: list[object] | None
    defense: str | None
    flavor_name: None
    keywords: list[MirrorVariant]
    legalities: S_legalities
    loyalty: str | None
    mana_cost: U_mana_cost
    name: str
    non_ability_text: None
    oracle_text: str | None
    power: U_power | None
    printings: list[object]
    replacements: list[S_replacements]
    scryfall_oracle_id: str
    static_abilities: list[S_static_abilities]
    toughness: U_toughness | None
    triggers: list[S_triggers]
    additional_cost: U_additional_cost = MISSING
    bracket_signals: S_bracket_signals = MISSING
    brawl_commander: bool = MISSING
    casting_options: list[S_casting_options | MirrorVariant] = MISSING
    casting_restrictions: list[U_casting_restrictions] = MISSING
    cleave_variant: S_cleave_variant = MISSING
    color_identity: list[object] = MISSING
    deck_copy_limit: U_deck_copy_limit = MISSING
    face_index: int = MISSING
    is_commander: bool = MISSING
    is_oathbreaker: bool = MISSING
    layout: str = MISSING
    metadata: S_metadata | MirrorVariant = MISSING
    modal: S_modal = MISSING
    parse_warnings: list[U_parse_warnings] = MISSING
    rarities: list[object] = MISSING
    rulings: list[S_rulings] = MISSING
    solve_condition: U_solve_condition = MISSING
    strive_cost: U_strive_cost = MISSING


@dataclass(frozen=True)
class S_AddKeywordUntilEndOfTurn(TypedMirrorNode):
    duration: str
    keyword: str
    restriction: MirrorVariant


@dataclass(frozen=True)
class S_Affinity(TypedMirrorNode):
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class S_AlternativeKeywordCost(TypedMirrorNode):
    cost: U_cost
    keyword: str
    frequency: str = MISSING


@dataclass(frozen=True)
class S_Awaken(TypedMirrorNode):
    cost: U_cost
    count: int


@dataclass(frozen=True)
class S_BattlefieldTransition(TypedMirrorNode):
    enter: bool
    leave: bool
    qualifiers: list[MirrorVariant]


@dataclass(frozen=True)
class S_CantActivateDuring(TypedMirrorNode):
    exemption: str
    when: str
    who: str


@dataclass(frozen=True)
class S_CantBeActivated(TypedMirrorNode):
    exemption: str
    kind: str | None
    source_filter: U_source_filter
    who: str


@dataclass(frozen=True)
class S_CantCastDuring(TypedMirrorNode):
    when: str
    who: str


@dataclass(frozen=True)
class S_CantPayCost(TypedMirrorNode):
    cost: str | MirrorVariant
    who: str


@dataclass(frozen=True)
class S_CastFromHandFree(TypedMirrorNode):
    frequency: str
    origin: str


@dataclass(frozen=True)
class S_CastWithAlternativeCost(TypedMirrorNode):
    cost: U_cost
    frequency: str = MISSING
    timing_permission: str = MISSING


@dataclass(frozen=True)
class S_CombatAlone(TypedMirrorNode):
    action: str
    requirement: str


@dataclass(frozen=True)
class S_Craft(TypedMirrorNode):
    cost: U_cost
    count: U_count
    materials: U_materials


@dataclass(frozen=True)
class S_Crew(TypedMirrorNode):
    once_per_turn: U_once_per_turn | None
    power: int


@dataclass(frozen=True)
class S_CrewContribution(TypedMirrorNode):
    actions: list[object]
    kind: str | MirrorVariant


@dataclass(frozen=True)
class S_DefilerCostReduction(TypedMirrorNode):
    color: str
    life_cost: int
    mana_reduction: U_mana_reduction


@dataclass(frozen=True)
class S_Devour(TypedMirrorNode):
    n: int
    quality: str | MirrorVariant


@dataclass(frozen=True)
class S_Disguise(TypedMirrorNode):
    cost: U_cost
    reduction: S_reduction


@dataclass(frozen=True)
class S_EntersWithAdditionalCounters(TypedMirrorNode):
    count: int
    counter_type: str


@dataclass(frozen=True)
class S_ExileCastPermission(TypedMirrorNode):
    cost: str
    frequency: str
    play_mode: str
    pool: str
    timing: str
    enters_with_counter: str = MISSING
    extra_cost: S_extra_cost = MISSING
    grants_flash: bool = MISSING
    mana_spend_permission: str = MISSING


@dataclass(frozen=True)
class S_GraveyardCastPermission(TypedMirrorNode):
    frequency: str
    play_mode: str
    enters_with_counter: str = MISSING
    extra_cost: S_extra_cost = MISSING
    graveyard_destination_replacement: str = MISSING


@dataclass(frozen=True)
class S_Impending(TypedMirrorNode):
    cost: U_cost
    counters: int


@dataclass(frozen=True)
class S_ImposeAdditionalCost(TypedMirrorNode):
    action: str
    cost: U_cost
    spell_filter: U_spell_filter


@dataclass(frozen=True)
class S_Keyword(TypedMirrorNode):
    count: int
    options: list[MirrorVariant]


@dataclass(frozen=True)
class S_ManaValue(TypedMirrorNode):
    comparator: str
    value: int


@dataclass(frozen=True)
class S_MaxAttackersEachCombat(TypedMirrorNode):
    defender: str | None
    max: int


@dataclass(frozen=True)
class S_MaxUntapPerType(TypedMirrorNode):
    filter: U_filter
    max: int


@dataclass(frozen=True)
class S_ModifyActivationLimit(TypedMirrorNode):
    keyword: str
    new_limit: int


@dataclass(frozen=True)
class S_ModifyCost(TypedMirrorNode):
    amount: U_amount
    mode: str
    spell_filter: U_spell_filter | None
    dynamic_count: U_dynamic_count = MISSING


@dataclass(frozen=True)
class S_MustBeBlockedByAll(TypedMirrorNode):
    pass


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_ActivateTagged__Equip(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Equip"


@dataclass(frozen=True)
class T_ActivateTagged__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_Bestow__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Bestow__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Blitz__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Blitz__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Bloodthirst__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    data: int


@dataclass(frozen=True)
class T_Bloodthirst__X(TypedMirrorNode):
    _tag: ClassVar[str | None] = "X"


@dataclass(frozen=True)
class T_Buyback__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Buyback__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Cleave__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_CommanderNinjutsu__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Companion__EvenManaValues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EvenManaValues"


@dataclass(frozen=True)
class T_Companion__MaxPermanentManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MaxPermanentManaValue"
    data: int


@dataclass(frozen=True)
class T_Companion__MinManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MinManaValue"
    data: int


@dataclass(frozen=True)
class T_Companion__NoRepeatedManaSymbols(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoRepeatedManaSymbols"


@dataclass(frozen=True)
class T_Companion__OddManaValues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OddManaValues"


@dataclass(frozen=True)
class T_Companion__PermanentsHaveActivatedAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PermanentsHaveActivatedAbilities"


@dataclass(frozen=True)
class T_Companion__SharedCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharedCardType"


@dataclass(frozen=True)
class T_CumulativeUpkeep__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_CumulativeUpkeep__EffectCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCost"
    effect: U_effect


@dataclass(frozen=True)
class T_CumulativeUpkeep__Exile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exile"
    count: int
    filter: None
    zone: str


@dataclass(frozen=True)
class T_CumulativeUpkeep__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_CumulativeUpkeep__OneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OneOf"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_CumulativeUpkeep__PayLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayLife"
    amount: U_amount


@dataclass(frozen=True)
class T_CumulativeUpkeep__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_Cycling__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Cycling__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Dash__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Disguise__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Disturb__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Echo__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Echo__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Embalm__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Emerge__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Enchant__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_Enchant__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_Enchant__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_Enchant__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_Enchant__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Encore__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Encore__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Encore__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_Entwine__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_EqualTo__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_EqualTo__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_Equip__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Equip__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_Escalate__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    filter: None
    random: bool
    self_ref: bool


@dataclass(frozen=True)
class T_Escalate__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    cost: U_cost


@dataclass(frozen=True)
class T_Escalate__TapCreatures(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TapCreatures"
    filter: U_filter
    requirement: S_requirement


@dataclass(frozen=True)
class T_Escape__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Eternalize__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Eternalize__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Evoke__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Evoke__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_Firebending__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_Firebending__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_Flashback__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    data: U_data


@dataclass(frozen=True)
class T_Flashback__NonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonMana"
    data: U_data


@dataclass(frozen=True)
class T_Foretell__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Foretell__SelfManaCostReduced(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCostReduced"
    reduction: int


@dataclass(frozen=True)
class T_Fortify__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Freerunning__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Gift__Card(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Card"


@dataclass(frozen=True)
class T_Gift__Food(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Food"


@dataclass(frozen=True)
class T_Gift__TappedFish(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TappedFish"


@dataclass(frozen=True)
class T_Gift__Treasure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Treasure"


@dataclass(frozen=True)
class T_Harmonize__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Harmonize__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_HexproofFrom__CardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardType"
    data: str


@dataclass(frozen=True)
class T_HexproofFrom__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"


@dataclass(frozen=True)
class T_HexproofFrom__Color(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Color"
    data: str


@dataclass(frozen=True)
class T_HexproofFrom__Quality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Quality"
    data: str


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Boast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Boast"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Exhaust(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Exhaust"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__Outlast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Outlast"


@dataclass(frozen=True)
class T_KeywordAbilityActivated__PowerUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerUp"


@dataclass(frozen=True)
class T_Kicker__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_LevelUp__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Madness__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Mayhem__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Mayhem__SelfManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCost"


@dataclass(frozen=True)
class T_Megamorph__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Miracle__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Miracle__SelfManaCostReduced(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaCostReduced"
    reduction: int


@dataclass(frozen=True)
class T_Mobilize__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_Mobilize__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_MoreThanMeetsTheEye__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


@dataclass(frozen=True)
class T_Morph__Cost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cost"
    generic: int
    shards: list[object]


# --- discriminated-union aliases (one per tagged content_key) ---

type U_ActivateTagged = T_ActivateTagged__Equip | T_ActivateTagged__PowerUp
type U_Bestow = T_Bestow__Mana | T_Bestow__NonMana
type U_Blitz = T_Blitz__Cost | T_Blitz__SelfManaCost
type U_Bloodthirst = T_Bloodthirst__Fixed | T_Bloodthirst__X
type U_Buyback = T_Buyback__Mana | T_Buyback__NonMana
type U_Cleave = T_Cleave__Cost
type U_CommanderNinjutsu = T_CommanderNinjutsu__Cost
type U_Companion = (
    T_Companion__EvenManaValues
    | T_Companion__MaxPermanentManaValue
    | T_Companion__MinManaValue
    | T_Companion__NoRepeatedManaSymbols
    | T_Companion__OddManaValues
    | T_Companion__PermanentsHaveActivatedAbilities
    | T_Companion__SharedCardType
)
type U_CumulativeUpkeep = (
    T_CumulativeUpkeep__Discard
    | T_CumulativeUpkeep__EffectCost
    | T_CumulativeUpkeep__Exile
    | T_CumulativeUpkeep__Mana
    | T_CumulativeUpkeep__OneOf
    | T_CumulativeUpkeep__PayLife
    | T_CumulativeUpkeep__Sacrifice
)
type U_Cycling = T_Cycling__Mana | T_Cycling__NonMana
type U_Dash = T_Dash__Cost
type U_Disguise = T_Disguise__Cost
type U_Disturb = T_Disturb__Cost
type U_Echo = T_Echo__Mana | T_Echo__NonMana
type U_Embalm = T_Embalm__Mana
type U_Emerge = T_Emerge__Cost
type U_Enchant = (
    T_Enchant__Any
    | T_Enchant__Or
    | T_Enchant__ParentTarget
    | T_Enchant__Player
    | T_Enchant__Typed
)
type U_Encore = T_Encore__Cost | T_Encore__SelfManaCost | T_Encore__SelfManaValue
type U_Entwine = T_Entwine__Cost
type U_EqualTo = T_EqualTo__Fixed | T_EqualTo__Ref
type U_Equip = T_Equip__Cost | T_Equip__SelfManaValue
type U_Escalate = T_Escalate__Discard | T_Escalate__Mana | T_Escalate__TapCreatures
type U_Escape = T_Escape__NonMana
type U_Eternalize = T_Eternalize__Mana | T_Eternalize__NonMana
type U_Evoke = T_Evoke__Mana | T_Evoke__NonMana
type U_Filter = T_Filter__Typed
type U_Firebending = T_Firebending__Fixed | T_Firebending__Ref
type U_Flashback = T_Flashback__Mana | T_Flashback__NonMana
type U_Foretell = T_Foretell__Cost | T_Foretell__SelfManaCostReduced
type U_Fortify = T_Fortify__Cost
type U_Freerunning = T_Freerunning__Cost
type U_Gift = T_Gift__Card | T_Gift__Food | T_Gift__TappedFish | T_Gift__Treasure
type U_Harmonize = T_Harmonize__Cost | T_Harmonize__SelfManaCost
type U_HexproofFrom = (
    T_HexproofFrom__CardType
    | T_HexproofFrom__ChosenColor
    | T_HexproofFrom__Color
    | T_HexproofFrom__Quality
)
type U_KeywordAbilityActivated = (
    T_KeywordAbilityActivated__Boast
    | T_KeywordAbilityActivated__Exhaust
    | T_KeywordAbilityActivated__Outlast
    | T_KeywordAbilityActivated__PowerUp
)
type U_Kicker = T_Kicker__Cost
type U_LevelUp = T_LevelUp__Cost
type U_Madness = T_Madness__Cost
type U_Mayhem = T_Mayhem__Cost | T_Mayhem__SelfManaCost
type U_Megamorph = T_Megamorph__Cost
type U_Miracle = T_Miracle__Cost | T_Miracle__SelfManaCostReduced
type U_Mobilize = T_Mobilize__Fixed | T_Mobilize__Ref
type U_MoreThanMeetsTheEye = T_MoreThanMeetsTheEye__Cost
type U_Morph = T_Morph__Cost
