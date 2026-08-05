"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content keys ``properties`` .. ``props`` (2
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
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_costs,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_count,
        U_counters,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        U_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g09_lhs import (
        U_parity,
    )
    from mtg_utils._card_ir.mirror.generated.g10_parse_warnings import (
        U_player,
        U_prop,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_reference,
    )
    from mtg_utils._card_ir.mirror.generated.g14_subtype_filter import (
        U_target,
        U_value,
    )


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_properties__Another(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Another"


@dataclass(frozen=True)
class T_properties__AnyOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AnyOf"
    props: list[U_props]


@dataclass(frozen=True)
class T_properties__AttachedToRecipient(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedToRecipient"


@dataclass(frozen=True)
class T_properties__AttachedToSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttachedToSource"


@dataclass(frozen=True)
class T_properties__AttackedOrBlockedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedOrBlockedThisTurn"


@dataclass(frozen=True)
class T_properties__AttackedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackedThisTurn"
    defender: str = MISSING


@dataclass(frozen=True)
class T_properties__Attacking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attacking"
    defender: str = MISSING


@dataclass(frozen=True)
class T_properties__AttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackingAlone"


@dataclass(frozen=True)
class T_properties__BlockedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockedThisTurn"


@dataclass(frozen=True)
class T_properties__Blocking(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Blocking"


@dataclass(frozen=True)
class T_properties__BlockingSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockingSource"


@dataclass(frozen=True)
class T_properties__CanEnchant(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CanEnchant"
    target: U_target


@dataclass(frozen=True)
class T_properties__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_properties__ColorCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ColorCount"
    comparator: str
    count: int


@dataclass(frozen=True)
class T_properties__CombatRelation(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CombatRelation"
    relation: str
    subject: str


@dataclass(frozen=True)
class T_properties__ControlledContinuouslySinceTurnBegan(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlledContinuouslySinceTurnBegan"


@dataclass(frozen=True)
class T_properties__ControllerChoseLabel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerChoseLabel"
    label: str


@dataclass(frozen=True)
class T_properties__ControllerMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControllerMatches"
    player: U_player


@dataclass(frozen=True)
class T_properties__ConvokedSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ConvokedSource"


@dataclass(frozen=True)
class T_properties__CouldBeTargetedByTriggeringSpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CouldBeTargetedByTriggeringSpell"


@dataclass(frozen=True)
class T_properties__Counters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counters"
    comparator: str
    count: U_count
    counters: U_counters


@dataclass(frozen=True)
class T_properties__CountersPutOnThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CountersPutOnThisTurn"
    actor: str
    comparator: str
    count: int
    counters: U_counters


@dataclass(frozen=True)
class T_properties__DealtDamageThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealtDamageThisTurn"


@dataclass(frozen=True)
class T_properties__DifferentNameFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DifferentNameFrom"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__DistinctFrom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DistinctFrom"
    reference: U_reference


@dataclass(frozen=True)
class T_properties__EnchantedBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnchantedBy"


@dataclass(frozen=True)
class T_properties__EnteredThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EnteredThisTurn"


@dataclass(frozen=True)
class T_properties__EquippedBy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EquippedBy"


@dataclass(frozen=True)
class T_properties__FaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FaceDown"


@dataclass(frozen=True)
class T_properties__Foretold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Foretold"


@dataclass(frozen=True)
class T_properties__Goaded(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Goaded"


@dataclass(frozen=True)
class T_properties__HasAdventure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAdventure"


@dataclass(frozen=True)
class T_properties__HasAnyAttachmentOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAnyAttachmentOf"
    kinds: list[object]


@dataclass(frozen=True)
class T_properties__HasAttachment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasAttachment"
    kind: str
    controller: str = MISSING
    exclude_source: bool = MISSING


@dataclass(frozen=True)
class T_properties__HasColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasColor"
    color: str


@dataclass(frozen=True)
class T_properties__HasKeywordKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasKeywordKind"
    value: str


@dataclass(frozen=True)
class T_properties__HasManaAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasManaAbility"


@dataclass(frozen=True)
class T_properties__HasNoAbilities(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasNoAbilities"


@dataclass(frozen=True)
class T_properties__HasSingleTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasSingleTarget"


@dataclass(frozen=True)
class T_properties__HasSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasSupertype"
    value: str


@dataclass(frozen=True)
class T_properties__HasXInActivationCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasXInActivationCost"


@dataclass(frozen=True)
class T_properties__HasXInManaCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasXInManaCost"


@dataclass(frozen=True)
class T_properties__Historic(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Historic"


@dataclass(frozen=True)
class T_properties__InAnyZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InAnyZone"
    zones: list[object]


@dataclass(frozen=True)
class T_properties__InZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "InZone"
    zone: str


@dataclass(frozen=True)
class T_properties__IsChosenCardType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCardType"


@dataclass(frozen=True)
class T_properties__IsChosenColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenColor"


@dataclass(frozen=True)
class T_properties__IsChosenCreatureType(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsChosenCreatureType"


@dataclass(frozen=True)
class T_properties__IsCommander(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsCommander"


@dataclass(frozen=True)
class T_properties__IsSaddled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "IsSaddled"


@dataclass(frozen=True)
class T_properties__ManaCostIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaCostIn"
    costs: list[U_costs]


@dataclass(frozen=True)
class T_properties__ManaSymbolCount(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaSymbolCount"
    color: str
    comparator: str
    value: int


@dataclass(frozen=True)
class T_properties__ManaValueParity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManaValueParity"
    parity: U_parity


@dataclass(frozen=True)
class T_properties__MatchesLastChosenCardPredicate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MatchesLastChosenCardPredicate"


@dataclass(frozen=True)
class T_properties__Modal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Modal"


@dataclass(frozen=True)
class T_properties__Modified(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Modified"


@dataclass(frozen=True)
class T_properties__MostPrevalentCreatureTypeIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MostPrevalentCreatureTypeIn"
    scope: str
    zone: str


@dataclass(frozen=True)
class T_properties__NameMatchesAnyPermanent(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NameMatchesAnyPermanent"
    controller: None


@dataclass(frozen=True)
class T_properties__Named(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Named"
    name: str


@dataclass(frozen=True)
class T_properties__NonToken(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NonToken"


@dataclass(frozen=True)
class T_properties__Not(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Not"
    prop: U_prop


@dataclass(frozen=True)
class T_properties__NotColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotColor"
    color: str


@dataclass(frozen=True)
class T_properties__NotHistoric(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotHistoric"


@dataclass(frozen=True)
class T_properties__NotSupertype(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NotSupertype"
    value: str


@dataclass(frozen=True)
class T_properties__OtherThanTriggerObject(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OtherThanTriggerObject"


@dataclass(frozen=True)
class T_properties__Owned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Owned"
    controller: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__PowerExceedsBase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerExceedsBase"


@dataclass(frozen=True)
class T_properties__PowerGTSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PowerGTSource"


@dataclass(frozen=True)
class T_properties__ProtectorMatches(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProtectorMatches"
    controller: str


@dataclass(frozen=True)
class T_properties__PtComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PtComparison"
    comparator: str
    scope: str
    stat: str
    value: U_value


@dataclass(frozen=True)
class T_properties__Renowned(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Renowned"


@dataclass(frozen=True)
class T_properties__RepresentedByCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RepresentedByCard"


@dataclass(frozen=True)
class T_properties__SaddledSource(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SaddledSource"


@dataclass(frozen=True)
class T_properties__SameName(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameName"


@dataclass(frozen=True)
class T_properties__SameNameAsParentTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SameNameAsParentTarget"


@dataclass(frozen=True)
class T_properties__SharesCreatureTypeWithCommander(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesCreatureTypeWithCommander"


@dataclass(frozen=True)
class T_properties__SharesQuality(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SharesQuality"
    quality: str
    reference: U_reference = MISSING
    relation: str = MISSING


@dataclass(frozen=True)
class T_properties__Suspected(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Suspected"


@dataclass(frozen=True)
class T_properties__Tapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tapped"


@dataclass(frozen=True)
class T_properties__Targets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Targets"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__TargetsOnly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetsOnly"
    filter: U_filter


@dataclass(frozen=True)
class T_properties__Token(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Token"


@dataclass(frozen=True)
class T_properties__ToughnessGTPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ToughnessGTPower"


@dataclass(frozen=True)
class T_properties__Transformed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Transformed"


@dataclass(frozen=True)
class T_properties__Unblocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unblocked"


@dataclass(frozen=True)
class T_properties__Unpaired(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unpaired"


@dataclass(frozen=True)
class T_properties__Untapped(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Untapped"


@dataclass(frozen=True)
class T_properties__WasDealtDamageThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasDealtDamageThisTurn"


@dataclass(frozen=True)
class T_properties__WasKicked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasKicked"


@dataclass(frozen=True)
class T_properties__WasPlayed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WasPlayed"


@dataclass(frozen=True)
class T_properties__WithKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithKeyword"
    value: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__WithoutKeyword(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithoutKeyword"
    value: str | MirrorVariant


@dataclass(frozen=True)
class T_properties__WithoutKeywordKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WithoutKeywordKind"
    value: str


@dataclass(frozen=True)
class T_properties__ZoneChangedThisTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ZoneChangedThisTurn"
    from_: str = field(metadata={"json": "from"})
    to: str


@dataclass(frozen=True)
class T_props__AttackingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AttackingAlone"


@dataclass(frozen=True)
class T_props__BlockingAlone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlockingAlone"


@dataclass(frozen=True)
class T_props__Cmc(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cmc"
    comparator: str
    value: U_value


@dataclass(frozen=True)
class T_props__HasColor(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HasColor"
    color: str


@dataclass(frozen=True)
class T_props__PtComparison(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PtComparison"
    comparator: str
    scope: str
    stat: str
    value: U_value


# --- discriminated-union aliases (one per tagged content_key) ---

type U_properties = (
    T_properties__Another
    | T_properties__AnyOf
    | T_properties__AttachedToRecipient
    | T_properties__AttachedToSource
    | T_properties__AttackedOrBlockedThisTurn
    | T_properties__AttackedThisTurn
    | T_properties__Attacking
    | T_properties__AttackingAlone
    | T_properties__BlockedThisTurn
    | T_properties__Blocking
    | T_properties__BlockingSource
    | T_properties__CanEnchant
    | T_properties__Cmc
    | T_properties__ColorCount
    | T_properties__CombatRelation
    | T_properties__ControlledContinuouslySinceTurnBegan
    | T_properties__ControllerChoseLabel
    | T_properties__ControllerMatches
    | T_properties__ConvokedSource
    | T_properties__CouldBeTargetedByTriggeringSpell
    | T_properties__Counters
    | T_properties__CountersPutOnThisTurn
    | T_properties__DealtDamageThisTurn
    | T_properties__DifferentNameFrom
    | T_properties__DistinctFrom
    | T_properties__EnchantedBy
    | T_properties__EnteredThisTurn
    | T_properties__EquippedBy
    | T_properties__FaceDown
    | T_properties__Foretold
    | T_properties__Goaded
    | T_properties__HasAdventure
    | T_properties__HasAnyAttachmentOf
    | T_properties__HasAttachment
    | T_properties__HasColor
    | T_properties__HasKeywordKind
    | T_properties__HasManaAbility
    | T_properties__HasNoAbilities
    | T_properties__HasSingleTarget
    | T_properties__HasSupertype
    | T_properties__HasXInActivationCost
    | T_properties__HasXInManaCost
    | T_properties__Historic
    | T_properties__InAnyZone
    | T_properties__InZone
    | T_properties__IsChosenCardType
    | T_properties__IsChosenColor
    | T_properties__IsChosenCreatureType
    | T_properties__IsCommander
    | T_properties__IsSaddled
    | T_properties__ManaCostIn
    | T_properties__ManaSymbolCount
    | T_properties__ManaValueParity
    | T_properties__MatchesLastChosenCardPredicate
    | T_properties__Modal
    | T_properties__Modified
    | T_properties__MostPrevalentCreatureTypeIn
    | T_properties__NameMatchesAnyPermanent
    | T_properties__Named
    | T_properties__NonToken
    | T_properties__Not
    | T_properties__NotColor
    | T_properties__NotHistoric
    | T_properties__NotSupertype
    | T_properties__OtherThanTriggerObject
    | T_properties__Owned
    | T_properties__PowerExceedsBase
    | T_properties__PowerGTSource
    | T_properties__ProtectorMatches
    | T_properties__PtComparison
    | T_properties__Renowned
    | T_properties__RepresentedByCard
    | T_properties__SaddledSource
    | T_properties__SameName
    | T_properties__SameNameAsParentTarget
    | T_properties__SharesCreatureTypeWithCommander
    | T_properties__SharesQuality
    | T_properties__Suspected
    | T_properties__Tapped
    | T_properties__Targets
    | T_properties__TargetsOnly
    | T_properties__Token
    | T_properties__ToughnessGTPower
    | T_properties__Transformed
    | T_properties__Unblocked
    | T_properties__Unpaired
    | T_properties__Untapped
    | T_properties__WasDealtDamageThisTurn
    | T_properties__WasKicked
    | T_properties__WasPlayed
    | T_properties__WithKeyword
    | T_properties__WithoutKeyword
    | T_properties__WithoutKeywordKind
    | T_properties__ZoneChangedThisTurn
)
type U_props = (
    T_props__AttackingAlone
    | T_props__BlockingAlone
    | T_props__Cmc
    | T_props__HasColor
    | T_props__PtComparison
)
