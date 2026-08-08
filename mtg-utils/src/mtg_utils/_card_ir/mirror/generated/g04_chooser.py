"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``chooser`` .. ``condition``
(5 keys).

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
        U_additional_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        U_attr,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_conditions,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_counters,
    )
    from mtg_utils._card_ir.mirror.generated.g07_effect import (
        U_effect,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_filter,
        U_filter,
        U_inner,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        S_or_trigger,
        U_lhs,
        U_origin_constraint,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
        U_player_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_reference,
        U_relation,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_for import (
        S_replacements,
        S_static_abilities,
        U_rhs,
        U_scaling,
        U_scope,
        U_source,
        U_subject,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        S_trigger,
        S_triggers,
        U_subtype_filter,
        U_target,
        U_value,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_chosen_pile_effect(TypedMirrorNode):
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
    player_scope: U_player_scope = MISSING


@dataclass(frozen=True)
class S_cleave_variant(TypedMirrorNode):
    abilities: list[S_abilities]
    replacements: list[S_replacements]
    static_abilities: list[S_static_abilities]
    triggers: list[S_triggers]


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_chooser__ChosenPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenPlayer"
    index: int


@dataclass(frozen=True)
class T_chooser__Controller(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Controller"


@dataclass(frozen=True)
class T_chooser__DefendingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayer"


@dataclass(frozen=True)
class T_chooser__Opponent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Opponent"


@dataclass(frozen=True)
class T_chooser__ParentObjectTargetController(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetController"


@dataclass(frozen=True)
class T_chooser__ParentObjectTargetOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ParentObjectTargetOwner"


@dataclass(frozen=True)
class T_chooser__PlayerAttribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlayerAttribute"
    attr: U_attr
    comparator: str
    relation: U_relation
    value: U_value


@dataclass(frozen=True)
class T_chooser__TriggeringPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringPlayer"


@dataclass(frozen=True)
class T_colors__ChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenColor"


@dataclass(frozen=True)
class T_colors__Fixed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fixed"
    value: list[U_value | MirrorVariant]


@dataclass(frozen=True)
class T_condition__ActivatedAbilityIsNonMana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ActivatedAbilityIsNonMana"


@dataclass(frozen=True)
class T_condition__AdditionalCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaid"
    min_count: int = MISSING
    origin: str = MISSING
    origin_ordinal: int = MISSING
    source: str = MISSING
    subject: U_subject = MISSING
    variant: str = MISSING


@dataclass(frozen=True)
class T_condition__AdditionalCostPaidInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalCostPaidInstead"


@dataclass(frozen=True)
class T_condition__AlternativeManaCostPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AlternativeManaCostPaid"


@dataclass(frozen=True)
class T_condition__And(TypedMirrorNode):
    _tag: ClassVar[str | None] = "And"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_condition__AtNextPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtNextPhase"
    phase: str


@dataclass(frozen=True)
class T_condition__AtNextPhaseForPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AtNextPhaseForPlayer"
    phase: str
    player: int
    gate: str = MISSING


@dataclass(frozen=True)
class T_condition__AttackersDeclaredCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackersDeclaredCount"
    comparator: str
    count: int
    subject: U_subject


@dataclass(frozen=True)
class T_condition__BeenAttackedThisStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BeenAttackedThisStep"


@dataclass(frozen=True)
class T_condition__CastDuringPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastDuringPhase"
    phases: list[object]


@dataclass(frozen=True)
class T_condition__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    zone: str


@dataclass(frozen=True)
class T_condition__CastTimingPermission(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastTimingPermission"
    permission: str


@dataclass(frozen=True)
class T_condition__CastVariantPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaid"
    variant: str
    subject: U_subject = MISSING


@dataclass(frozen=True)
class T_condition__CastVariantPaidInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaidInstead"
    variant: str


@dataclass(frozen=True)
class T_condition__CastVariantPaidPersistent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastVariantPaidPersistent"
    variant: str


@dataclass(frozen=True)
class T_condition__CastViaEscape(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastViaEscape"


@dataclass(frozen=True)
class T_condition__CastViaKicker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastViaKicker"
    variant: str = MISSING


@dataclass(frozen=True)
class T_condition__CastingAsVariant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastingAsVariant"
    variant: str


@dataclass(frozen=True)
class T_condition__ChosenLabelIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChosenLabelIs"
    label: str


@dataclass(frozen=True)
class T_condition__ClassLevelGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ClassLevelGE"
    level: int


@dataclass(frozen=True)
class T_condition__CoinFlipOutcome(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CoinFlipOutcome"
    result: str


@dataclass(frozen=True)
class T_condition__CompletedADungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CompletedADungeon"


@dataclass(frozen=True)
class T_condition__CompletedDungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CompletedDungeon"
    specific: str = MISSING


@dataclass(frozen=True)
class T_condition__ConditionInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConditionInstead"
    inner: U_inner


@dataclass(frozen=True)
class T_condition__ControllerControlledMatchingAsCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlledMatchingAsCast"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControllerControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerControlsMatching"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControlsCommander(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsCommander"
    ownership: str


@dataclass(frozen=True)
class T_condition__ControlsNone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsNone"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ControlsType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlsType"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__CostPaidObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CostPaidObjectMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__DamagedPlayerIsEventSourceOwner(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamagedPlayerIsEventSourceOwner"


@dataclass(frozen=True)
class T_condition__DayNightIs(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DayNightIs"
    state: str


@dataclass(frozen=True)
class T_condition__DayNightIsNeither(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DayNightIsNeither"


@dataclass(frozen=True)
class T_condition__DealtDamageBySourceThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealtDamageBySourceThisTurn"


@dataclass(frozen=True)
class T_condition__DealtDamageThisTurnBySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealtDamageThisTurnBySource"
    source: U_source


@dataclass(frozen=True)
class T_condition__DefendingPlayerControls(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayerControls"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__DefendingPlayerControlsNone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DefendingPlayerControlsNone"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__DevotionGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DevotionGE"
    colors: list[U_colors]
    threshold: int


@dataclass(frozen=True)
class T_condition__DuringPlayersTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringPlayersTurn"
    player: U_player


@dataclass(frozen=True)
class T_condition__DuringUntapStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringUntapStep"


@dataclass(frozen=True)
class T_condition__DuringYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DuringYourTurn"


@dataclass(frozen=True)
class T_condition__EchoDue(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EchoDue"


@dataclass(frozen=True)
class T_condition__EffectCausedDiscard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectCausedDiscard"


@dataclass(frozen=True)
class T_condition__EffectOutcome(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EffectOutcome"
    signal: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__EnchantedIsFaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnchantedIsFaceDown"


@dataclass(frozen=True)
class T_condition__EnteredFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredFromZone"
    cast_origin: str
    origin_constraint: U_origin_constraint


@dataclass(frozen=True)
class T_condition__EventDamageSourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventDamageSourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__EventObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventObjectMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__EventOutcomeWon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventOutcomeWon"


@dataclass(frozen=True)
class T_condition__EventSourceControlledBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EventSourceControlledBy"
    controller: str


@dataclass(frozen=True)
class T_condition__ExceptFirstDrawInDrawStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExceptFirstDrawInDrawStep"


@dataclass(frozen=True)
class T_condition__FirstCombatPhaseOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstCombatPhaseOfTurn"


@dataclass(frozen=True)
class T_condition__FirstEndStepOfTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstEndStepOfTurn"


@dataclass(frozen=True)
class T_condition__FirstTimeObjectCountersAddedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstTimeObjectCountersAddedThisTurn"


@dataclass(frozen=True)
class T_condition__FirstTimeObjectTappedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstTimeObjectTappedThisTurn"


@dataclass(frozen=True)
class T_condition__FirstTokenCreationEachTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FirstTokenCreationEachTurn"
    player: str


@dataclass(frozen=True)
class T_condition__HadCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HadCounters"
    counter_type: str | None


@dataclass(frozen=True)
class T_condition__HasCityBlessing(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCityBlessing"


@dataclass(frozen=True)
class T_condition__HasCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasCounters"
    counters: U_counters
    minimum: int
    maximum: int = MISSING


@dataclass(frozen=True)
class T_condition__HasMaxSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasMaxSpeed"


@dataclass(frozen=True)
class T_condition__IfControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IfControlsMatching"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_condition__IsInitiative(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsInitiative"


@dataclass(frozen=True)
class T_condition__IsMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsMonarch"


@dataclass(frozen=True)
class T_condition__IsOpponentsTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsOpponentsTurn"


@dataclass(frozen=True)
class T_condition__IsPresent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsPresent"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__IsRenowned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsRenowned"
    subject: str


@dataclass(frozen=True)
class T_condition__IsRingBearer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsRingBearer"


@dataclass(frozen=True)
class T_condition__IsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsTapped"
    scope: U_scope


@dataclass(frozen=True)
class T_condition__IsYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsYourTurn"


@dataclass(frozen=True)
class T_condition__ManaColorSpent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaColorSpent"
    color: str
    minimum: int


@dataclass(frozen=True)
class T_condition__ManaSpentCondition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSpentCondition"
    text: str


@dataclass(frozen=True)
class T_condition__MinCoAttackers(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MinCoAttackers"
    minimum: int
    filter: U_filter = MISSING


@dataclass(frozen=True)
class T_condition__NoMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoMonarch"


@dataclass(frozen=True)
class T_condition__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    condition: U_condition


@dataclass(frozen=True)
class T_condition__NthResolutionThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NthResolutionThisTurn"
    n: int


@dataclass(frozen=True)
class T_condition__ObjectsShareQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ObjectsShareQuality"
    quality: str
    reference: U_reference
    subject: U_subject


@dataclass(frozen=True)
class T_condition__OnlyExtraTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyExtraTurn"


@dataclass(frozen=True)
class T_condition__OnlyIfQuantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OnlyIfQuantity"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs
    active_player_req: str = MISSING


@dataclass(frozen=True)
class T_condition__OpponentDamagedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentDamagedThisTurn"


@dataclass(frozen=True)
class T_condition__OpponentPoisonAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentPoisonAtLeast"
    count: int


@dataclass(frozen=True)
class T_condition__Or(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Or"
    conditions: list[U_conditions]


@dataclass(frozen=True)
class T_condition__PlacedByAbilitySource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PlacedByAbilitySource"


@dataclass(frozen=True)
class T_condition__PostReplacementDamageSourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PostReplacementDamageSourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__PreviousEffectAmount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreviousEffectAmount"
    comparator: str
    rhs: U_rhs
    channel: str = MISSING


@dataclass(frozen=True)
class T_condition__QuantityCheck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityCheck"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__QuantityComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "QuantityComparison"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs


@dataclass(frozen=True)
class T_condition__RecipientAttackingOwnerTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientAttackingOwnerTarget"
    target: str


@dataclass(frozen=True)
class T_condition__RecipientHasCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientHasCounters"
    counters: U_counters
    minimum: int


@dataclass(frozen=True)
class T_condition__RecipientMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RecipientMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__RevealedHasCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealedHasCardType"
    card_types: list[MirrorVariant]
    additional_filter: U_additional_filter = MISSING
    subtype_filter: U_subtype_filter = MISSING


@dataclass(frozen=True)
class T_condition__SharesColorWithMostCommonColorAmongPermanents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesColorWithMostCommonColorAmongPermanents"


@dataclass(frozen=True)
class T_condition__SolveConditionMet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SolveConditionMet"


@dataclass(frozen=True)
class T_condition__SourceAttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttachedTo"
    required_type: str


@dataclass(frozen=True)
class T_condition__SourceAttachedToCreature(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttachedToCreature"


@dataclass(frozen=True)
class T_condition__SourceAttackedThisCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttackedThisCombat"


@dataclass(frozen=True)
class T_condition__SourceAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttackedThisTurn"


@dataclass(frozen=True)
class T_condition__SourceAttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceAttackingAlone"


@dataclass(frozen=True)
class T_condition__SourceEnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceEnteredThisTurn"


@dataclass(frozen=True)
class T_condition__SourceHasDealtDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceHasDealtDamage"


@dataclass(frozen=True)
class T_condition__SourceInZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceInZone"
    zone: str


@dataclass(frozen=True)
class T_condition__SourceIsAttacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsAttacking"


@dataclass(frozen=True)
class T_condition__SourceIsBlocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsBlocked"


@dataclass(frozen=True)
class T_condition__SourceIsColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsColor"
    color: str


@dataclass(frozen=True)
class T_condition__SourceIsEnchanted(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsEnchanted"


@dataclass(frozen=True)
class T_condition__SourceIsEquipped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsEquipped"


@dataclass(frozen=True)
class T_condition__SourceIsFaceUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsFaceUp"


@dataclass(frozen=True)
class T_condition__SourceIsHarnessed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsHarnessed"


@dataclass(frozen=True)
class T_condition__SourceIsMonstrous(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsMonstrous"


@dataclass(frozen=True)
class T_condition__SourceIsPaired(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsPaired"


@dataclass(frozen=True)
class T_condition__SourceIsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceIsTapped"


@dataclass(frozen=True)
class T_condition__SourceLacksKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceLacksKeyword"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__SourceMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceMatchesFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__SourcePowerAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourcePowerAtLeast"
    minimum: int


@dataclass(frozen=True)
class T_condition__SourceTappedState(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceTappedState"
    tapped: bool


@dataclass(frozen=True)
class T_condition__SourceUntappedAttachedTo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SourceUntappedAttachedTo"
    required_type: str


@dataclass(frozen=True)
class T_condition__SpeedGE(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpeedGE"
    threshold: int


@dataclass(frozen=True)
class T_condition__SpellTargetsFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SpellTargetsFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__Static(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Static"
    condition: U_condition


@dataclass(frozen=True)
class T_condition__TargetHasKeywordInstead(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetHasKeywordInstead"
    keyword: str | MirrorVariant


@dataclass(frozen=True)
class T_condition__TargetMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetMatchesFilter"
    filter: U_filter
    use_lki: bool
    subject_slot: int = MISSING


@dataclass(frozen=True)
class T_condition__TargetSharesNameWithOtherExiledThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetSharesNameWithOtherExiledThisWay"
    target: U_target


@dataclass(frozen=True)
class T_condition__TokenCoreTypeMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokenCoreTypeMatches"
    core_types: list[object]


@dataclass(frozen=True)
class T_condition__TokenSubtypeMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TokenSubtypeMatches"
    subtypes: list[object]


@dataclass(frozen=True)
class T_condition__TopOfLibraryMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TopOfLibraryMatches"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__TributeNotPaid(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TributeNotPaid"


@dataclass(frozen=True)
class T_condition__TriggeringSpellTargetsFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TriggeringSpellTargetsFilter"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsCountMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsCountMatching"
    filter: U_filter
    minimum: int


@dataclass(frozen=True)
class T_condition__UnlessControlsMatching(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsMatching"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsOtherLeq(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsOtherLeq"
    count: int
    filter: S_filter


@dataclass(frozen=True)
class T_condition__UnlessControlsSubtype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessControlsSubtype"
    subtypes: list[object]


@dataclass(frozen=True)
class T_condition__UnlessMultipleOpponents(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessMultipleOpponents"


@dataclass(frozen=True)
class T_condition__UnlessPay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessPay"
    cost: U_cost
    defended: str = MISSING
    scaling: U_scaling = MISSING


@dataclass(frozen=True)
class T_condition__UnlessPlayerLifeAtMost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessPlayerLifeAtMost"
    amount: int


@dataclass(frozen=True)
class T_condition__UnlessQuantity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessQuantity"
    comparator: str
    lhs: U_lhs
    rhs: U_rhs
    active_player_req: str = MISSING


@dataclass(frozen=True)
class T_condition__UnlessYourTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnlessYourTurn"


@dataclass(frozen=True)
class T_condition__Unrecognized(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unrecognized"
    text: str


@dataclass(frozen=True)
class T_condition__WasCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasCast"
    controller: str = MISSING
    owner: str = MISSING
    zone: str = MISSING


@dataclass(frozen=True)
class T_condition__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_condition__WasStartingPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasStartingPlayer"
    controller: str


@dataclass(frozen=True)
class T_condition__WasType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasType"
    card_type: str


@dataclass(frozen=True)
class T_condition__WhenDies(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenDies"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenDiesOrExiled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenDiesOrExiled"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenEntersBattlefield(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenEntersBattlefield"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenLeavesPlayFiltered(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenLeavesPlayFiltered"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__WhenNextEvent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenNextEvent"
    or_trigger: S_or_trigger | None
    trigger: S_trigger
    lifetime: str = MISSING


@dataclass(frozen=True)
class T_condition__WhenYouDo(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WhenYouDo"


@dataclass(frozen=True)
class T_condition__WheneverEvent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WheneverEvent"
    trigger: S_trigger
    expiry: MirrorVariant = MISSING


@dataclass(frozen=True)
class T_condition__YouAttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouAttackedThisTurn"


@dataclass(frozen=True)
class T_condition__YouHadArtifactEnterThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "YouHadArtifactEnterThisTurn"


@dataclass(frozen=True)
class T_condition__ZoneChangeObjectIsTapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectIsTapped"


@dataclass(frozen=True)
class T_condition__ZoneChangeObjectMatchesFilter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangeObjectMatchesFilter"
    destination: str
    filter: U_filter
    origin: str = MISSING


@dataclass(frozen=True)
class T_condition__ZoneChangedThisWay(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisWay"
    filter: U_filter


@dataclass(frozen=True)
class T_condition__ZoneCoreTypeCardCountAtLeast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneCoreTypeCardCountAtLeast"
    core_type: str
    count: int
    zone: str


# --- discriminated-union aliases (one per tagged content_key) ---

type U_chooser = (
    T_chooser__ChosenPlayer
    | T_chooser__Controller
    | T_chooser__DefendingPlayer
    | T_chooser__Opponent
    | T_chooser__ParentObjectTargetController
    | T_chooser__ParentObjectTargetOwner
    | T_chooser__PlayerAttribute
    | T_chooser__TriggeringPlayer
)
type U_colors = T_colors__ChosenColor | T_colors__Fixed
type U_condition = (
    T_condition__ActivatedAbilityIsNonMana
    | T_condition__AdditionalCostPaid
    | T_condition__AdditionalCostPaidInstead
    | T_condition__AlternativeManaCostPaid
    | T_condition__And
    | T_condition__AtNextPhase
    | T_condition__AtNextPhaseForPlayer
    | T_condition__AttackersDeclaredCount
    | T_condition__BeenAttackedThisStep
    | T_condition__CastDuringPhase
    | T_condition__CastFromZone
    | T_condition__CastTimingPermission
    | T_condition__CastVariantPaid
    | T_condition__CastVariantPaidInstead
    | T_condition__CastVariantPaidPersistent
    | T_condition__CastViaEscape
    | T_condition__CastViaKicker
    | T_condition__CastingAsVariant
    | T_condition__ChosenLabelIs
    | T_condition__ClassLevelGE
    | T_condition__CoinFlipOutcome
    | T_condition__CompletedADungeon
    | T_condition__CompletedDungeon
    | T_condition__ConditionInstead
    | T_condition__ControllerControlledMatchingAsCast
    | T_condition__ControllerControlsMatching
    | T_condition__ControlsCommander
    | T_condition__ControlsNone
    | T_condition__ControlsType
    | T_condition__CostPaidObjectMatchesFilter
    | T_condition__DamagedPlayerIsEventSourceOwner
    | T_condition__DayNightIs
    | T_condition__DayNightIsNeither
    | T_condition__DealtDamageBySourceThisTurn
    | T_condition__DealtDamageThisTurnBySource
    | T_condition__DefendingPlayerControls
    | T_condition__DefendingPlayerControlsNone
    | T_condition__DevotionGE
    | T_condition__DuringPlayersTurn
    | T_condition__DuringUntapStep
    | T_condition__DuringYourTurn
    | T_condition__EchoDue
    | T_condition__EffectCausedDiscard
    | T_condition__EffectOutcome
    | T_condition__EnchantedIsFaceDown
    | T_condition__EnteredFromZone
    | T_condition__EventDamageSourceMatchesFilter
    | T_condition__EventObjectMatchesFilter
    | T_condition__EventOutcomeWon
    | T_condition__EventSourceControlledBy
    | T_condition__ExceptFirstDrawInDrawStep
    | T_condition__FirstCombatPhaseOfTurn
    | T_condition__FirstEndStepOfTurn
    | T_condition__FirstTimeObjectCountersAddedThisTurn
    | T_condition__FirstTimeObjectTappedThisTurn
    | T_condition__FirstTokenCreationEachTurn
    | T_condition__HadCounters
    | T_condition__HasCityBlessing
    | T_condition__HasCounters
    | T_condition__HasMaxSpeed
    | T_condition__IfControlsMatching
    | T_condition__IsInitiative
    | T_condition__IsMonarch
    | T_condition__IsOpponentsTurn
    | T_condition__IsPresent
    | T_condition__IsRenowned
    | T_condition__IsRingBearer
    | T_condition__IsTapped
    | T_condition__IsYourTurn
    | T_condition__ManaColorSpent
    | T_condition__ManaSpentCondition
    | T_condition__MinCoAttackers
    | T_condition__NoMonarch
    | T_condition__Not
    | T_condition__NthResolutionThisTurn
    | T_condition__ObjectsShareQuality
    | T_condition__OnlyExtraTurn
    | T_condition__OnlyIfQuantity
    | T_condition__OpponentDamagedThisTurn
    | T_condition__OpponentPoisonAtLeast
    | T_condition__Or
    | T_condition__PlacedByAbilitySource
    | T_condition__PostReplacementDamageSourceMatchesFilter
    | T_condition__PreviousEffectAmount
    | T_condition__QuantityCheck
    | T_condition__QuantityComparison
    | T_condition__RecipientAttackingOwnerTarget
    | T_condition__RecipientHasCounters
    | T_condition__RecipientMatchesFilter
    | T_condition__RevealedHasCardType
    | T_condition__SharesColorWithMostCommonColorAmongPermanents
    | T_condition__SolveConditionMet
    | T_condition__SourceAttachedTo
    | T_condition__SourceAttachedToCreature
    | T_condition__SourceAttackedThisCombat
    | T_condition__SourceAttackedThisTurn
    | T_condition__SourceAttackingAlone
    | T_condition__SourceEnteredThisTurn
    | T_condition__SourceHasDealtDamage
    | T_condition__SourceInZone
    | T_condition__SourceIsAttacking
    | T_condition__SourceIsBlocked
    | T_condition__SourceIsColor
    | T_condition__SourceIsEnchanted
    | T_condition__SourceIsEquipped
    | T_condition__SourceIsFaceUp
    | T_condition__SourceIsHarnessed
    | T_condition__SourceIsMonstrous
    | T_condition__SourceIsPaired
    | T_condition__SourceIsTapped
    | T_condition__SourceLacksKeyword
    | T_condition__SourceMatchesFilter
    | T_condition__SourcePowerAtLeast
    | T_condition__SourceTappedState
    | T_condition__SourceUntappedAttachedTo
    | T_condition__SpeedGE
    | T_condition__SpellTargetsFilter
    | T_condition__Static
    | T_condition__TargetHasKeywordInstead
    | T_condition__TargetMatchesFilter
    | T_condition__TargetSharesNameWithOtherExiledThisWay
    | T_condition__TokenCoreTypeMatches
    | T_condition__TokenSubtypeMatches
    | T_condition__TopOfLibraryMatches
    | T_condition__TributeNotPaid
    | T_condition__TriggeringSpellTargetsFilter
    | T_condition__UnlessControlsCountMatching
    | T_condition__UnlessControlsMatching
    | T_condition__UnlessControlsOtherLeq
    | T_condition__UnlessControlsSubtype
    | T_condition__UnlessMultipleOpponents
    | T_condition__UnlessPay
    | T_condition__UnlessPlayerLifeAtMost
    | T_condition__UnlessQuantity
    | T_condition__UnlessYourTurn
    | T_condition__Unrecognized
    | T_condition__WasCast
    | T_condition__WasPlayed
    | T_condition__WasStartingPlayer
    | T_condition__WasType
    | T_condition__WhenDies
    | T_condition__WhenDiesOrExiled
    | T_condition__WhenEntersBattlefield
    | T_condition__WhenLeavesPlayFiltered
    | T_condition__WhenNextEvent
    | T_condition__WhenYouDo
    | T_condition__WheneverEvent
    | T_condition__YouAttackedThisTurn
    | T_condition__YouHadArtifactEnterThisTurn
    | T_condition__ZoneChangeObjectIsTapped
    | T_condition__ZoneChangeObjectMatchesFilter
    | T_condition__ZoneChangedThisWay
    | T_condition__ZoneCoreTypeCardCountAtLeast
)
