"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``qty`` .. ``relation`` (11
keys).

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
        U_colors,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_count,
        U_counters,
        U_data,
        U_direction,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_exclude,
        U_exprs,
        U_filter,
        U_filters,
        U_inner,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        U_metric,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        U_scope,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        U_target,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_reduction(TypedMirrorNode):
    amount_per: int
    count: U_count


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_qty__AdditionalCostPaymentCountFor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaymentCountFor"
    origin: str
    origin_ordinal: int


@dataclass(frozen=True)
class T_qty__Aggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Aggregate"
    filter: U_filter
    function: str
    property: str | MirrorVariant


@dataclass(frozen=True)
class T_qty__AttachmentsOnLeavingObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachmentsOnLeavingObject"
    controller: str
    kind: str


@dataclass(frozen=True)
class T_qty__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__BasicLandTypeCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BasicLandTypeCount"
    controller: str


@dataclass(frozen=True)
class T_qty__BattlefieldEntriesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BattlefieldEntriesThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__BendTypesThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BendTypesThisTurn"


@dataclass(frozen=True)
class T_qty__CardsDiscardedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDiscardedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__CardsDrawnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsDrawnThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__CardsExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CardsExiledBySource"


@dataclass(frozen=True)
class T_qty__ChosenNumber(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenNumber"


@dataclass(frozen=True)
class T_qty__ColorsInCommandersColorIdentity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ColorsInCommandersColorIdentity"


@dataclass(frozen=True)
class T_qty__CommanderCastFromCommandZoneCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CommanderCastFromCommandZoneCount"


@dataclass(frozen=True)
class T_qty__CommanderManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CommanderManaValue"
    owner: str


@dataclass(frozen=True)
class T_qty__ControlledByEachPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlledByEachPlayer"
    aggregate: str
    filter: U_filter


@dataclass(frozen=True)
class T_qty__ConvokedCreatureCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConvokedCreatureCount"


@dataclass(frozen=True)
class T_qty__CostXPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostXPaid"


@dataclass(frozen=True)
class T_qty__CounterAddedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterAddedThisTurn"
    actor: str
    counters: U_counters
    target: U_target


@dataclass(frozen=True)
class T_qty__CountersOn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOn"
    scope: U_scope
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_qty__CountersOnObjects(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOnObjects"
    filter: U_filter
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_qty__CrimesCommittedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CrimesCommittedThisTurn"


@dataclass(frozen=True)
class T_qty__DamageDealtThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageDealtThisTurn"
    source: U_source
    target: U_target
    aggregate: str = MISSING
    channel: str = MISSING
    damage_kind: str = MISSING
    group_by: str = MISSING


@dataclass(frozen=True)
class T_qty__DescendedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DescendedThisTurn"


@dataclass(frozen=True)
class T_qty__Devotion(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Devotion"
    colors: U_colors


@dataclass(frozen=True)
class T_qty__DistinctCardTypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCardTypes"
    source: U_source


@dataclass(frozen=True)
class T_qty__DistinctColorsAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColorsAmongPermanents"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__DistinctCounterKindsAmong(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctCounterKindsAmong"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__DistinctSubtypes(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctSubtypes"
    exclude: U_exclude
    source: U_source


@dataclass(frozen=True)
class T_qty__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__EventContextAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventContextAmount"


@dataclass(frozen=True)
class T_qty__EventContextPlayerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventContextPlayerCount"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__EventContextSourceModesChosen(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventContextSourceModesChosen"


@dataclass(frozen=True)
class T_qty__ExiledCardPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledCardPower"
    index: int


@dataclass(frozen=True)
class T_qty__ExiledFromHandThisResolution(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledFromHandThisResolution"


@dataclass(frozen=True)
class T_qty__FilteredTrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FilteredTrackedSetSize"
    filter: U_filter
    caused_by: str = MISSING


@dataclass(frozen=True)
class T_qty__GraveyardSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GraveyardSize"
    player: U_player


@dataclass(frozen=True)
class T_qty__HandSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HandSize"
    player: U_player


@dataclass(frozen=True)
class T_qty__Intensity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Intensity"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__KickerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "KickerCount"


@dataclass(frozen=True)
class T_qty__LandsPlayedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LandsPlayedThisTurn"
    player: U_player
    from_zones: list[object] = MISSING


@dataclass(frozen=True)
class T_qty__LifeAboveStarting(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeAboveStarting"


@dataclass(frozen=True)
class T_qty__LifeGainedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeGainedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__LifeLostThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeLostThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__LifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LifeTotal"
    player: U_player


@dataclass(frozen=True)
class T_qty__LoyaltyAbilitiesActivatedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoyaltyAbilitiesActivatedThisTurn"
    player: U_player


@dataclass(frozen=True)
class T_qty__ManaSpentToCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSpentToCast"
    metric: U_metric
    scope: str


@dataclass(frozen=True)
class T_qty__ManaSymbolsInManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSymbolsInManaCost"
    color: None | str
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectColorCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectColorCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__ObjectCountBySharedQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCountBySharedQuality"
    aggregate: str
    filter: U_filter
    quality: str


@dataclass(frozen=True)
class T_qty__ObjectCountDistinct(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCountDistinct"
    filter: U_filter
    qualities: list[object]


@dataclass(frozen=True)
class T_qty__ObjectManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectManaValue"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectNameWordCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectNameWordCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__ObjectTypelineComponentCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectTypelineComponentCount"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__PartySize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PartySize"
    player: U_player


@dataclass(frozen=True)
class T_qty__PlayerActionsThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerActionsThisTurn"
    action: str
    player: U_player


@dataclass(frozen=True)
class T_qty__PlayerCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCount"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__PlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerCounter"
    kind: str
    scope: str


@dataclass(frozen=True)
class T_qty__Power(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Power"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"
    channel: str = MISSING


@dataclass(frozen=True)
class T_qty__SacrificedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SacrificedThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__SelfManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfManaValue"


@dataclass(frozen=True)
class T_qty__Speed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Speed"
    player: U_player


@dataclass(frozen=True)
class T_qty__SpellsCastLastTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastLastTurn"


@dataclass(frozen=True)
class T_qty__SpellsCastThisGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastThisGame"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__SpellsCastThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellsCastThisTurn"
    scope: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__StartingLifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StartingLifeTotal"


@dataclass(frozen=True)
class T_qty__TargetControllerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetControllerCounter"
    kind: str


@dataclass(frozen=True)
class T_qty__TargetObjectManaValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetObjectManaValue"
    filter: U_filter


@dataclass(frozen=True)
class T_qty__TargetZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetZoneCardCount"
    zone: str


@dataclass(frozen=True)
class T_qty__TimesCostPaidThisResolution(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TimesCostPaidThisResolution"


@dataclass(frozen=True)
class T_qty__TokensCreatedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokensCreatedThisTurn"
    filter: U_filter
    player: U_player


@dataclass(frozen=True)
class T_qty__Toughness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Toughness"
    scope: U_scope


@dataclass(frozen=True)
class T_qty__TrackedSetAggregate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetAggregate"
    function: str
    property: str
    source: str = MISSING


@dataclass(frozen=True)
class T_qty__TrackedSetSize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetSize"


@dataclass(frozen=True)
class T_qty__TriggeringDiscoverValue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringDiscoverValue"


@dataclass(frozen=True)
class T_qty__TriggeringScryBottomCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringScryBottomCount"


@dataclass(frozen=True)
class T_qty__TriggeringScryLookCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringScryLookCount"


@dataclass(frozen=True)
class T_qty__TurnsTaken(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnsTaken"


@dataclass(frozen=True)
class T_qty__UnspentMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnspentMana"
    color: None | str


@dataclass(frozen=True)
class T_qty__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    name: str


@dataclass(frozen=True)
class T_qty__VoteCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VoteCount"
    choice_index: int


@dataclass(frozen=True)
class T_qty__ZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCount"
    card_types: list[MirrorVariant]
    scope: str
    zone: str
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_qty__ZoneChangeAggregateThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeAggregateThisTurn"
    filter: U_filter
    from_: str = field(metadata={"json": "from"})
    function: str
    property: str
    to: str


@dataclass(frozen=True)
class T_qty__ZoneChangeCountThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeCountThisTurn"
    filter: U_filter
    from_: str = field(default=MISSING, metadata={"json": "from"})
    to: str = MISSING


@dataclass(frozen=True)
class T_quantity__BasicLandTypeCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BasicLandTypeCount"
    controller: str


@dataclass(frozen=True)
class T_quantity__CountersOn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersOn"
    scope: U_scope
    counter_type: str = MISSING


@dataclass(frozen=True)
class T_quantity__Multiply(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Multiply"
    factor: int
    inner: U_inner


@dataclass(frozen=True)
class T_quantity__ObjectCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectCount"
    filter: U_filter


@dataclass(frozen=True)
class T_quantity__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_quantity__Sum(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sum"
    exprs: list[U_exprs]


@dataclass(frozen=True)
class T_quantity__ZoneCardCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCardCount"
    card_types: list[MirrorVariant]
    scope: str
    zone: str


@dataclass(frozen=True)
class T_quantity_modification__Half(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Half"


@dataclass(frozen=True)
class T_quantity_modification__Minus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Minus"
    value: int


@dataclass(frozen=True)
class T_quantity_modification__Plus(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Plus"
    value: int


@dataclass(frozen=True)
class T_quantity_modification__Prevent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Prevent"


@dataclass(frozen=True)
class T_quantity_modification__Times(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Times"
    factor: int


@dataclass(frozen=True)
class T_recipient__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_recipient__AttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedTo"


@dataclass(frozen=True)
class T_recipient__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_recipient__EachController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachController"


@dataclass(frozen=True)
class T_recipient__Neighbor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Neighbor"
    direction: U_direction


@dataclass(frozen=True)
class T_recipient__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_recipient__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_recipient__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_recipient__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_recipient__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_recipient__Shared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Shared"
    data: U_data


@dataclass(frozen=True)
class T_recipient__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_recipient__TriggeringSourceController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSourceController"


@dataclass(frozen=True)
class T_recipient__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str | MirrorVariant
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_recipient_object_filter__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_recipient_object_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_redirect_object_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_redirect_target__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_redirect_to__ChosenObjectTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenObjectTarget"


@dataclass(frozen=True)
class T_redirect_to__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_redirect_to__SourceObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceObject"


@dataclass(frozen=True)
class T_reference__CostPaidObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObject"


@dataclass(frozen=True)
class T_reference__ExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledBySource"


@dataclass(frozen=True)
class T_reference__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_reference__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_reference__SelfRef(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SelfRef"


@dataclass(frozen=True)
class T_reference__TrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSet"
    id: int


@dataclass(frozen=True)
class T_reference__TriggeringSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSource"


@dataclass(frozen=True)
class T_reference__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: None | str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_relation__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_relation__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


# --- discriminated-union aliases (one per tagged content_key) ---

type U_qty = (
    T_qty__AdditionalCostPaymentCountFor
    | T_qty__Aggregate
    | T_qty__AttachmentsOnLeavingObject
    | T_qty__AttackedThisTurn
    | T_qty__BasicLandTypeCount
    | T_qty__BattlefieldEntriesThisTurn
    | T_qty__BendTypesThisTurn
    | T_qty__CardsDiscardedThisTurn
    | T_qty__CardsDrawnThisTurn
    | T_qty__CardsExiledBySource
    | T_qty__ChosenNumber
    | T_qty__ColorsInCommandersColorIdentity
    | T_qty__CommanderCastFromCommandZoneCount
    | T_qty__CommanderManaValue
    | T_qty__ControlledByEachPlayer
    | T_qty__ConvokedCreatureCount
    | T_qty__CostXPaid
    | T_qty__CounterAddedThisTurn
    | T_qty__CountersOn
    | T_qty__CountersOnObjects
    | T_qty__CrimesCommittedThisTurn
    | T_qty__DamageDealtThisTurn
    | T_qty__DescendedThisTurn
    | T_qty__Devotion
    | T_qty__DistinctCardTypes
    | T_qty__DistinctColorsAmongPermanents
    | T_qty__DistinctCounterKindsAmong
    | T_qty__DistinctSubtypes
    | T_qty__EnteredThisTurn
    | T_qty__EventContextAmount
    | T_qty__EventContextPlayerCount
    | T_qty__EventContextSourceModesChosen
    | T_qty__ExiledCardPower
    | T_qty__ExiledFromHandThisResolution
    | T_qty__FilteredTrackedSetSize
    | T_qty__GraveyardSize
    | T_qty__HandSize
    | T_qty__Intensity
    | T_qty__KickerCount
    | T_qty__LandsPlayedThisTurn
    | T_qty__LifeAboveStarting
    | T_qty__LifeGainedThisTurn
    | T_qty__LifeLostThisTurn
    | T_qty__LifeTotal
    | T_qty__LoyaltyAbilitiesActivatedThisTurn
    | T_qty__ManaSpentToCast
    | T_qty__ManaSymbolsInManaCost
    | T_qty__ObjectColorCount
    | T_qty__ObjectCount
    | T_qty__ObjectCountBySharedQuality
    | T_qty__ObjectCountDistinct
    | T_qty__ObjectManaValue
    | T_qty__ObjectNameWordCount
    | T_qty__ObjectTypelineComponentCount
    | T_qty__PartySize
    | T_qty__PlayerActionsThisTurn
    | T_qty__PlayerCount
    | T_qty__PlayerCounter
    | T_qty__Power
    | T_qty__PreviousEffectAmount
    | T_qty__SacrificedThisTurn
    | T_qty__SelfManaValue
    | T_qty__Speed
    | T_qty__SpellsCastLastTurn
    | T_qty__SpellsCastThisGame
    | T_qty__SpellsCastThisTurn
    | T_qty__StartingLifeTotal
    | T_qty__TargetControllerCounter
    | T_qty__TargetObjectManaValue
    | T_qty__TargetZoneCardCount
    | T_qty__TimesCostPaidThisResolution
    | T_qty__TokensCreatedThisTurn
    | T_qty__Toughness
    | T_qty__TrackedSetAggregate
    | T_qty__TrackedSetSize
    | T_qty__TriggeringDiscoverValue
    | T_qty__TriggeringScryBottomCount
    | T_qty__TriggeringScryLookCount
    | T_qty__TurnsTaken
    | T_qty__UnspentMana
    | T_qty__Variable
    | T_qty__VoteCount
    | T_qty__ZoneCardCount
    | T_qty__ZoneChangeAggregateThisTurn
    | T_qty__ZoneChangeCountThisTurn
)
type U_quantity = (
    T_quantity__BasicLandTypeCount
    | T_quantity__CountersOn
    | T_quantity__Multiply
    | T_quantity__ObjectCount
    | T_quantity__Ref
    | T_quantity__Sum
    | T_quantity__ZoneCardCount
)
type U_quantity_modification = (
    T_quantity_modification__Half
    | T_quantity_modification__Minus
    | T_quantity_modification__Plus
    | T_quantity_modification__Prevent
    | T_quantity_modification__Times
)
type U_recipient = (
    T_recipient__Any
    | T_recipient__AttachedTo
    | T_recipient__Controller
    | T_recipient__EachController
    | T_recipient__Neighbor
    | T_recipient__ParentTarget
    | T_recipient__ParentTargetController
    | T_recipient__Player
    | T_recipient__ScopedPlayer
    | T_recipient__SelfRef
    | T_recipient__Shared
    | T_recipient__TriggeringPlayer
    | T_recipient__TriggeringSourceController
    | T_recipient__Typed
)
type U_recipient_object_filter = (
    T_recipient_object_filter__SelfRef | T_recipient_object_filter__Typed
)
type U_redirect_object_filter = T_redirect_object_filter__Typed
type U_redirect_target = T_redirect_target__SelfRef
type U_redirect_to = (
    T_redirect_to__ChosenObjectTarget
    | T_redirect_to__Controller
    | T_redirect_to__SourceObject
)
type U_reference = (
    T_reference__CostPaidObject
    | T_reference__ExiledBySource
    | T_reference__Or
    | T_reference__ParentTarget
    | T_reference__SelfRef
    | T_reference__TrackedSet
    | T_reference__TriggeringSource
    | T_reference__Typed
)
type U_relation = T_relation__All | T_relation__Opponent
