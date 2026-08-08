"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``parse_warnings`` .. ``prop``
(18 keys).

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
        U_attr,
        U_card_filter,
        U_cast_cost_raise,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        U_colors,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_count,
        U_depth,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_exclude,
        U_filter,
        U_invalidation,
        U_land_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_multi_target,
        U_lhs,
    )
    from mtg_utils._card_ir.mirror.generated.g11_properties import (
        U_properties,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_reference,
        U_relation,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_sub_ability,
        U_rhs,
        U_scope,
        U_source,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_unit_span,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_per_choice_effect(TypedMirrorNode):
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
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    target_choice_timing: str = MISSING


@dataclass(frozen=True)
class S_profile(TypedMirrorNode):
    extra_core_types: list[object] = MISSING
    power: int = MISSING
    subtypes: list[object] = MISSING
    toughness: int = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_parse_warnings__IgnoredRemainder(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IgnoredRemainder"
    line_index: int
    parser: str
    text: str


@dataclass(frozen=True)
class T_parse_warnings__SwallowedClause(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwallowedClause"
    description: str
    detector: str
    line_index: int
    unit_span: S_unit_span
    items: list[object] = MISSING


@dataclass(frozen=True)
class T_parse_warnings__TargetFallback(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetFallback"
    context: str
    line_index: int
    text: str


@dataclass(frozen=True)
class T_partition_subject__AnOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnOpponent"


@dataclass(frozen=True)
class T_partition_subject__EachOpponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachOpponent"


@dataclass(frozen=True)
class T_partner_filter__Any(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Any"


@dataclass(frozen=True)
class T_partner_filter__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_payer__AllPlayers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllPlayers"


@dataclass(frozen=True)
class T_payer__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_payer__ParentTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentTargetController"


@dataclass(frozen=True)
class T_payer__Player(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Player"


@dataclass(frozen=True)
class T_payer__ScopedPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ScopedPlayer"


@dataclass(frozen=True)
class T_payer__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_payer__TriggeringSpellController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellController"


@dataclass(frozen=True)
class T_payer__Typed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Typed"
    controller: str | None
    properties: list[U_properties]
    type_filters: list[MirrorVariant]


@dataclass(frozen=True)
class T_per_player_condition__QuantityComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityComparison"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_per_player_condition__YouAttackedSourceControllerThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedSourceControllerThisTurn"


@dataclass(frozen=True)
class T_per_player_condition__YouAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedThisTurn"


@dataclass(frozen=True)
class T_per_player_condition__YouCastSpellThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouCastSpellThisTurn"


@dataclass(frozen=True)
class T_permission__ExileWithAltCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileWithAltCost"
    cost: U_cost


@dataclass(frozen=True)
class T_permission__ExileWithEnergyCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileWithEnergyCost"


@dataclass(frozen=True)
class T_permission__Foretold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Foretold"
    cost: U_cost
    turn_foretold: int


@dataclass(frozen=True)
class T_permission__PlayFromExile(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayFromExile"
    duration: str | MirrorVariant
    granted_to: int
    card_filter: U_card_filter = MISSING
    cast_cost_raise: U_cast_cost_raise = MISSING
    frequency: str = MISSING
    invalidation: U_invalidation = MISSING
    land_enter_tapped: str = MISSING
    mana_spend_permission: str = MISSING
    single_use: bool = MISSING


@dataclass(frozen=True)
class T_permission__Plotted(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Plotted"
    turn_plotted: int


@dataclass(frozen=True)
class T_pile_source__Battlefield(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Battlefield"


@dataclass(frozen=True)
class T_pile_source__ExiledThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExiledThisWay"


@dataclass(frozen=True)
class T_pile_source__RevealedFromLibraryTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealedFromLibraryTop"
    data: MirrorVariant


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
class T_player__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


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
class T_player__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


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
class T_player_filter__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_player_filter__OpponentOtherThanTriggering(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentOtherThanTriggering"


@dataclass(frozen=True)
class T_player_scope__All(TypedMirrorNode):
    _tag: ClassVar[str | None] = "All"


@dataclass(frozen=True)
class T_player_scope__AllExcept(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AllExcept"
    exclude: U_exclude


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
class T_player_scope__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_player_scope__VotedFor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VotedFor"
    choice_index: int


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
class T_produced__OpponentLandColors(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentLandColors"
    count: U_count


@dataclass(frozen=True)
class T_produced__TriggerEventManaType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggerEventManaType"


@dataclass(frozen=True)
class T_prop__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"


@dataclass(frozen=True)
class T_prop__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"


@dataclass(frozen=True)
class T_prop__InTrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InTrackedSet"
    id: int


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


# --- discriminated-union aliases (one per tagged content_key) ---

type U_parse_warnings = (
    T_parse_warnings__IgnoredRemainder
    | T_parse_warnings__SwallowedClause
    | T_parse_warnings__TargetFallback
)
type U_partition_subject = (
    T_partition_subject__AnOpponent | T_partition_subject__EachOpponent
)
type U_partner_filter = T_partner_filter__Any | T_partner_filter__Typed
type U_payer = (
    T_payer__AllPlayers
    | T_payer__Controller
    | T_payer__ParentTargetController
    | T_payer__Player
    | T_payer__ScopedPlayer
    | T_payer__TriggeringPlayer
    | T_payer__TriggeringSpellController
    | T_payer__Typed
)
type U_per_player_condition = (
    T_per_player_condition__QuantityComparison
    | T_per_player_condition__YouAttackedSourceControllerThisTurn
    | T_per_player_condition__YouAttackedThisTurn
    | T_per_player_condition__YouCastSpellThisTurn
)
type U_permission = (
    T_permission__ExileWithAltCost
    | T_permission__ExileWithEnergyCost
    | T_permission__Foretold
    | T_permission__PlayFromExile
    | T_permission__Plotted
)
type U_pile_source = (
    T_pile_source__Battlefield
    | T_pile_source__ExiledThisWay
    | T_pile_source__RevealedFromLibraryTop
)
type U_player = (
    T_player__AllPlayers
    | T_player__Any
    | T_player__AnyTurn
    | T_player__Controller
    | T_player__DefendingPlayer
    | T_player__Opponent
    | T_player__OpponentDealtDamage
    | T_player__ParentObjectTargetController
    | T_player__ParentTarget
    | T_player__ParentTargetController
    | T_player__ParentTargetOwner
    | T_player__Player
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
    | T_player_filter__Opponent
    | T_player_filter__OpponentOtherThanTriggering
)
type U_player_scope = (
    T_player_scope__All
    | T_player_scope__AllExcept
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
    | T_player_scope__TriggeringPlayer
    | T_player_scope__VotedFor
)
type U_position = (
    T_position__BeneathTop
    | T_position__Bottom
    | T_position__NthFromTop
    | T_position__Top
)
type U_power = T_power__Fixed | T_power__Quantity | T_power__Variable
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
    | T_produced__OpponentLandColors
    | T_produced__TriggerEventManaType
)
type U_prop = (
    T_prop__AttackedThisTurn
    | T_prop__EnteredThisTurn
    | T_prop__InTrackedSet
    | T_prop__SameName
    | T_prop__SharesQuality
    | T_prop__WasPlayed
)
