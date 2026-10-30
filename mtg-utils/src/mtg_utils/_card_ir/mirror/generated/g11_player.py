"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``player`` .. ``prop`` (11
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
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_attr,
    )
    from mtg_utils._card_ir.mirror.generated.g04_casting_restrictions import (
        U_colors,
    )
    from mtg_utils._card_ir.mirror.generated.g06_costs import (
        U_count,
        U_depth,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_exclude,
        U_filter,
        U_filters,
    )
    from mtg_utils._card_ir.mirror.generated.g09_inner import (
        U_land_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g12_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g13_qty import (
        U_qty,
    )
    from mtg_utils._card_ir.mirror.generated.g14_redirect_target import (
        U_reference,
        U_relation,
        U_scope,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g16_triggers import (
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_profile(TypedMirrorNode):
    cause: str
    power: int
    subtypes: list[object]
    toughness: int
    extra_core_types: list[object] = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_player__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"
    aggregate: str
    exclude: U_exclude = MISSING


@dataclass(frozen=True)
class T_player__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_player__AnyTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyTurn"


@dataclass(frozen=True)
class T_player__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_player__ControlsCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCount"
    comparator: str
    count: U_count
    filter: U_filter
    relation: U_relation


@dataclass(frozen=True)
class T_player__DeclaredPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DeclaredPlayer"
    group: int


@dataclass(frozen=True)
class T_player__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_player__GrantingObjectCaster(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantingObjectCaster"


@dataclass(frozen=True)
class T_player__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"
    aggregate: str = MISSING


@dataclass(frozen=True)
class T_player__OpponentDealtDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentDealtDamage"
    kind: str
    min_sources: int
    source: U_source


@dataclass(frozen=True)
class T_player__OpponentOfTriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOfTriggeringPlayer"


@dataclass(frozen=True)
class T_player__ParentObjectTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTarget"
    possession: str


@dataclass(frozen=True)
class T_player__ParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTarget"


@dataclass(frozen=True)
class T_player__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_player__ParentTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetOwner"


@dataclass(frozen=True)
class T_player__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_player__PostReplacementDamageTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageTarget"


@dataclass(frozen=True)
class T_player__RecipientController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientController"


@dataclass(frozen=True)
class T_player__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_player__SourceChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceChosenPlayer"


@dataclass(frozen=True)
class T_player__Target(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Target"


@dataclass(frozen=True)
class T_player__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_player__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | MirrorVariant | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_player_a__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_player_a__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player_b__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_player_b__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_player_filter__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_player_filter__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_player_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_player_filter__OpponentOtherThanTriggering(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOtherThanTriggering"


@dataclass(frozen=True)
class T_player_filter__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_player_scope__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_player_scope__AllExcept(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllExcept"
    exclude: U_exclude


@dataclass(frozen=True)
class T_player_scope__AnyOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOf"
    filters: list[U_filters]


@dataclass(frozen=True)
class T_player_scope__ChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenPlayer"
    index: int


@dataclass(frozen=True)
class T_player_scope__ControlsCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCount"
    comparator: str
    count: U_count
    filter: U_filter
    relation: U_relation


@dataclass(frozen=True)
class T_player_scope__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_player_scope__HighestSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HighestSpeed"


@dataclass(frozen=True)
class T_player_scope__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_player_scope__OpponentAttacked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttacked"
    scope: str
    subject: str


@dataclass(frozen=True)
class T_player_scope__OpponentAttackingEnchantedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentAttackingEnchantedPlayer"


@dataclass(frozen=True)
class T_player_scope__OpponentOfTriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOfTriggeringPlayer"


@dataclass(frozen=True)
class T_player_scope__OwnersOfCardsExiledBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OwnersOfCardsExiledBySource"


@dataclass(frozen=True)
class T_player_scope__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_player_scope__PerformedActionThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PerformedActionThisWay"
    action: str
    relation: U_relation


@dataclass(frozen=True)
class T_player_scope__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_player_scope__TrackedSetPossessor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TrackedSetPossessor"
    caused_by: str
    filter: U_filter
    possession: str
    relation: U_relation


@dataclass(frozen=True)
class T_player_scope__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_player_scope__VotedFor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VotedFor"
    choice_index: int


@dataclass(frozen=True)
class T_players__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_players__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_position__BeneathTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeneathTop"
    depth: U_depth


@dataclass(frozen=True)
class T_position__Bottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bottom"


@dataclass(frozen=True)
class T_position__NthFromTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthFromTop"
    n: int


@dataclass(frozen=True)
class T_position__Top(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Top"


@dataclass(frozen=True)
class T_power__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: int


@dataclass(frozen=True)
class T_power__Quantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Quantity"
    value: U_value


@dataclass(frozen=True)
class T_power__Ref(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Ref"
    qty: U_qty


@dataclass(frozen=True)
class T_power__Variable(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Variable"
    value: str


@dataclass(frozen=True)
class T_produced__AnyCombination(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyCombination"
    color_options: list[object]
    count: U_count


@dataclass(frozen=True)
class T_produced__AnyCombinationOfObjectColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyCombinationOfObjectColors"
    count: U_count
    scope: U_scope


@dataclass(frozen=True)
class T_produced__AnyInCommandersColorIdentity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyInCommandersColorIdentity"
    count: U_count


@dataclass(frozen=True)
class T_produced__AnyOneColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOneColor"
    color_options: list[object]
    count: U_count
    contribution: str = MISSING


@dataclass(frozen=True)
class T_produced__AnyOneColorAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOneColorAmongPermanents"
    count: U_count
    filter: U_filter


@dataclass(frozen=True)
class T_produced__AnyTypeProduceableBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyTypeProduceableBy"
    count: U_count
    land_filter: U_land_filter


@dataclass(frozen=True)
class T_produced__ChoiceAmongCombinations(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChoiceAmongCombinations"
    options: list[MirrorVariant]


@dataclass(frozen=True)
class T_produced__ChoiceAmongExiledColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChoiceAmongExiledColors"
    source: U_source


@dataclass(frozen=True)
class T_produced__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"
    count: U_count
    contribution: str = MISSING
    fixed_alternative: str = MISSING


@dataclass(frozen=True)
class T_produced__Colorless(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Colorless"
    count: U_count


@dataclass(frozen=True)
class T_produced__DistinctColorsAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctColorsAmongPermanents"
    filter: U_filter


@dataclass(frozen=True)
class T_produced__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    colors: list[U_colors]
    contribution: str = MISSING


@dataclass(frozen=True)
class T_produced__Mixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mixed"
    colorless_count: int
    colors: list[U_colors]


@dataclass(frozen=True)
class T_produced__NotedType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotedType"
    count: U_count


@dataclass(frozen=True)
class T_produced__OpponentLandColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentLandColors"
    count: U_count


@dataclass(frozen=True)
class T_produced__TriggerEventManaType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggerEventManaType"


@dataclass(frozen=True)
class T_prop__Another(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Another"


@dataclass(frozen=True)
class T_prop__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"


@dataclass(frozen=True)
class T_prop__EnchantedBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnchantedBy"


@dataclass(frozen=True)
class T_prop__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"


@dataclass(frozen=True)
class T_prop__HasAttachment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAttachment"
    kind: str


@dataclass(frozen=True)
class T_prop__InTrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InTrackedSet"
    id: int


@dataclass(frozen=True)
class T_prop__Named(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Named"
    name: str


@dataclass(frozen=True)
class T_prop__SameName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameName"


@dataclass(frozen=True)
class T_prop__SharesQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesQuality"
    quality: str
    reference: U_reference


@dataclass(frozen=True)
class T_prop__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_prop__ZoneChangedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisTurn"
    from_: str = field(metadata={"json": "from"})
    to: str


# --- discriminated-union aliases (one per tagged content_key) ---

type U_player = (
    T_player__AllPlayers
    | T_player__Any
    | T_player__AnyTurn
    | T_player__Controller
    | T_player__ControlsCount
    | T_player__DeclaredPlayer
    | T_player__DefendingPlayer
    | T_player__GrantingObjectCaster
    | T_player__Opponent
    | T_player__OpponentDealtDamage
    | T_player__OpponentOfTriggeringPlayer
    | T_player__ParentObjectTarget
    | T_player__ParentTarget
    | T_player__ParentTargetController
    | T_player__ParentTargetOwner
    | T_player__Player
    | T_player__PlayerAttribute
    | T_player__PostReplacementDamageTarget
    | T_player__RecipientController
    | T_player__ScopedPlayer
    | T_player__SourceChosenPlayer
    | T_player__Target
    | T_player__TriggeringPlayer
    | T_player__Typed
)
type U_player_a = T_player_a__Controller | T_player_a__Player
type U_player_b = T_player_b__Player | T_player_b__Typed
type U_player_filter = (
    T_player_filter__All
    | T_player_filter__Controller
    | T_player_filter__Opponent
    | T_player_filter__OpponentOtherThanTriggering
    | T_player_filter__PlayerAttribute
)
type U_player_scope = (
    T_player_scope__All
    | T_player_scope__AllExcept
    | T_player_scope__AnyOf
    | T_player_scope__ChosenPlayer
    | T_player_scope__ControlsCount
    | T_player_scope__DefendingPlayer
    | T_player_scope__HighestSpeed
    | T_player_scope__Opponent
    | T_player_scope__OpponentAttacked
    | T_player_scope__OpponentAttackingEnchantedPlayer
    | T_player_scope__OpponentOfTriggeringPlayer
    | T_player_scope__OwnersOfCardsExiledBySource
    | T_player_scope__ParentObjectTargetController
    | T_player_scope__PerformedActionThisWay
    | T_player_scope__PlayerAttribute
    | T_player_scope__TrackedSetPossessor
    | T_player_scope__TriggeringPlayer
    | T_player_scope__VotedFor
)
type U_players = T_players__All | T_players__Controller
type U_position = (
    T_position__BeneathTop
    | T_position__Bottom
    | T_position__NthFromTop
    | T_position__Top
)
type U_power = T_power__Fixed | T_power__Quantity | T_power__Ref | T_power__Variable
type U_produced = (
    T_produced__AnyCombination
    | T_produced__AnyCombinationOfObjectColors
    | T_produced__AnyInCommandersColorIdentity
    | T_produced__AnyOneColor
    | T_produced__AnyOneColorAmongPermanents
    | T_produced__AnyTypeProduceableBy
    | T_produced__ChoiceAmongCombinations
    | T_produced__ChoiceAmongExiledColors
    | T_produced__ChosenColor
    | T_produced__Colorless
    | T_produced__DistinctColorsAmongPermanents
    | T_produced__Fixed
    | T_produced__Mixed
    | T_produced__NotedType
    | T_produced__OpponentLandColors
    | T_produced__TriggerEventManaType
)
type U_prop = (
    T_prop__Another
    | T_prop__AttackedThisTurn
    | T_prop__EnchantedBy
    | T_prop__EnteredThisTurn
    | T_prop__HasAttachment
    | T_prop__InTrackedSet
    | T_prop__Named
    | T_prop__SameName
    | T_prop__SharesQuality
    | T_prop__WasPlayed
    | T_prop__ZoneChangedThisTurn
)
