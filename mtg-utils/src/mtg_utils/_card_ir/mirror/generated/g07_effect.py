"""GENERATED — DO NOT EDIT BY HAND (ADR-0035, Stage 2).

Codegen'd from ``tests/fixtures/phase_mirror_schema.json`` by
``mtg_utils._card_ir.mirror.codegen`` (run via ``build-card-ir-substrate``).

Part of the generated typed-mirror package (see this directory's
``__init__.py``). This module holds content key ``effect``.

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
        U_action,
    )
    from mtg_utils._card_ir.mirror.generated.g03_additional_modificat import (
        S_branches,
        S_cards,
        U_additional_modifications,
        U_alt_ability_cost,
        U_amount,
        U_amount_dynamic,
        U_attach_to,
        U_attachment,
        U_attacker_restriction,
        U_card_filter,
        U_choose_filter,
        U_choose_scope,
    )
    from mtg_utils._card_ir.mirror.generated.g04_chooser import (
        S_chosen_pile_effect,
        U_chooser,
        U_colors,
        U_condition,
    )
    from mtg_utils._card_ir.mirror.generated.g05_conditional_enter_wi import (
        U_conditional_enter_with_counters,
        U_constraint,
        U_copy_modifications,
        U_cost,
    )
    from mtg_utils._card_ir.mirror.generated.g06_count import (
        U_count,
        U_countered_spell_zone,
        U_damage_source_filter,
        U_direction,
    )
    from mtg_utils._card_ir.mirror.generated.g08_else_ability import (
        S_face_down_profile,
        U_enchant_filter,
        U_enter_with_counters,
        U_enters_modified_if,
        U_entry,
        U_excess,
        U_extra_source,
        U_filter,
        U_flipper,
        U_forced_to,
        U_grantee,
        U_grants,
        U_host,
        U_keep_count_expr,
        U_keep_on_top,
        U_keeper_constraint,
        U_kind,
        U_library_players,
    )
    from mtg_utils._card_ir.mirror.generated.g09_library_position import (
        S_lose_effect,
        S_modification,
        S_multi_target,
        S_on_decline,
        U_library_position,
        U_life_payment,
        U_mana_value_limit,
        U_matched_disposition,
        U_max_ticket_cost,
        U_modification,
        U_modifications,
        U_modifier,
        U_object_filter,
        U_object_source,
        U_op,
        U_owner,
        U_partition_subject,
        U_partner_filter,
    )
    from mtg_utils._card_ir.mirror.generated.g10_payer import (
        S_per_choice_effect,
        S_profile,
        U_payer,
        U_permission,
        U_pile_source,
        U_player,
        U_player_a,
        U_player_b,
        U_player_filter,
        U_player_scope,
        U_position,
        U_power,
        U_produced,
    )
    from mtg_utils._card_ir.mirror.generated.g12_qty import (
        U_recipient,
        U_recipient_object_filter,
        U_redirect_object_filter,
        U_redirect_to,
        U_repeat_for,
    )
    from mtg_utils._card_ir.mirror.generated.g13_repeat_until import (
        S_replacement,
        S_results,
        S_scale,
        S_split,
        S_static_abilities,
        S_statics,
        S_sub_ability,
        U_replacement_effect,
        U_required_player,
        U_restriction,
        U_retarget,
        U_sacrifice_filter,
        U_scale,
        U_scope,
        U_selection,
        U_selection_constraint,
        U_source,
        U_source_filter,
        U_source_pool,
        U_source_rider,
        U_sources,
        U_spell_filter,
        U_state,
        U_step,
        U_subject,
        U_tally_mode,
    )
    from mtg_utils._card_ir.mirror.generated.g14_target import (
        S_triggers,
        S_unchosen_pile_effect,
        S_unless_pay,
        S_win_effect,
        U_target,
        U_target_a,
        U_target_b,
        U_target_kind,
        U_target_player,
        U_target_selection_mode,
        U_total_power_cap,
        U_toughness,
        U_unless_filter,
        U_until,
        U_visibility,
        U_voter_scope,
    )


# --- struct shapes (untagged records, one per content_key) ---


@dataclass(frozen=True)
class S_effect(TypedMirrorNode):
    condition: None | U_condition
    cost: None
    description: None | str
    duration: None | str | MirrorVariant
    effect: U_effect
    forward_result: bool
    kind: str
    optional: bool
    optional_targeting: bool
    sub_ability: None | S_sub_ability
    target_prompt: None
    is_mana_ability: bool = MISSING
    multi_target: S_multi_target = MISSING
    player_scope: U_player_scope = MISSING
    repeat_for: U_repeat_for = MISSING
    target_choice_timing: str = MISSING
    target_selection_mode: U_target_selection_mode = MISSING
    unless_pay: S_unless_pay = MISSING


# --- tagged shapes (discriminated enum nodes) ---


@dataclass(frozen=True)
class T_effect__Adapt(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Adapt"
    count: U_count


@dataclass(frozen=True)
class T_effect__AddPendingETBCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddPendingETBCounters"
    count: U_count
    counter_type: str


@dataclass(frozen=True)
class T_effect__AddPendingEntersModifications(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddPendingEntersModifications"
    modifications: list[U_modifications]


@dataclass(frozen=True)
class T_effect__AddRestriction(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddRestriction"
    restriction: U_restriction


@dataclass(frozen=True)
class T_effect__AddTargetReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AddTargetReplacement"
    replacement: S_replacement
    target: U_target


@dataclass(frozen=True)
class T_effect__AdditionalPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AdditionalPhase"
    after: str
    attacker_restriction: None | U_attacker_restriction
    count: U_count
    followed_by: list[object]
    phase: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Amass(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Amass"
    count: U_count
    subtype: str


@dataclass(frozen=True)
class T_effect__Animate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Animate"
    power: None | U_power
    target: U_target
    toughness: None | U_toughness
    types: list[object]
    keywords: list[MirrorVariant] = MISSING
    remove_types: list[object] = MISSING


@dataclass(frozen=True)
class T_effect__ApplyPerpetual(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ApplyPerpetual"
    modification: S_modification
    target: U_target


@dataclass(frozen=True)
class T_effect__ArrangePlanarDeckTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ArrangePlanarDeckTop"
    count: U_count
    keep_on_top: U_keep_on_top


@dataclass(frozen=True)
class T_effect__AssembleContraptions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "AssembleContraptions"
    count: U_count


@dataclass(frozen=True)
class T_effect__Attach(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Attach"
    target: U_target
    attachment: U_attachment = MISSING


@dataclass(frozen=True)
class T_effect__BecomeBlocked(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeBlocked"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeCopy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeCopy"
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    duration: str | MirrorVariant = MISSING
    mana_value_limit: str = MISSING
    recipient: U_recipient = MISSING


@dataclass(frozen=True)
class T_effect__BecomeMonarch(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeMonarch"


@dataclass(frozen=True)
class T_effect__BecomePrepared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomePrepared"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeSaddled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeSaddled"
    target: U_target


@dataclass(frozen=True)
class T_effect__BecomeUnprepared(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BecomeUnprepared"
    target: U_target


@dataclass(frozen=True)
class T_effect__Behold(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Behold"
    filter: U_filter


@dataclass(frozen=True)
class T_effect__BlightEffect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BlightEffect"
    count: int
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__Bolster(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bolster"
    count: U_count


@dataclass(frozen=True)
class T_effect__Bounce(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Bounce"
    destination: None
    target: U_target
    selection: str = MISSING


@dataclass(frozen=True)
class T_effect__BounceAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "BounceAll"
    target: U_target
    count: U_count = MISSING


@dataclass(frozen=True)
class T_effect__CastCopyOfCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastCopyOfCard"
    cost: U_cost
    count: None | U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__CastFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CastFromZone"
    mode: str
    target: U_target
    without_paying_mana_cost: bool
    alt_ability_cost: U_alt_ability_cost = MISSING
    cast_transformed: bool = MISSING
    constraint: U_constraint = MISSING
    driver: str = MISSING
    duration: str | MirrorVariant = MISSING
    mana_spend_permission: str = MISSING


@dataclass(frozen=True)
class T_effect__ChangeSpeed(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeSpeed"
    amount: U_amount
    direction: U_direction
    floor: int
    player_scope: U_player_scope


@dataclass(frozen=True)
class T_effect__ChangeTargets(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeTargets"
    forced_to: None | U_forced_to
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__ChangeZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeZone"
    destination: str
    enter_tapped: bool
    enter_transformed: bool
    enters_attacking: bool
    origin: None | str
    owner_library: bool
    target: U_target
    conditional_enter_with_counters: list[U_conditional_enter_with_counters] = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    enters_modified_if: U_enters_modified_if = MISSING
    enters_under: str = MISSING
    face_down_profile: S_face_down_profile = MISSING
    up_to: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChangeZoneAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChangeZoneAll"
    destination: str
    origin: None | str
    target: U_target
    enter_tapped: bool = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    enters_under: str = MISSING
    face_down_profile: S_face_down_profile = MISSING
    library_position: U_library_position = MISSING
    random_order: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChaosEnsues(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChaosEnsues"


@dataclass(frozen=True)
class T_effect__Choose(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Choose"
    choice_type: str | MirrorVariant
    persist: bool
    selection: U_selection = MISSING


@dataclass(frozen=True)
class T_effect__ChooseAndSacrificeRest(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseAndSacrificeRest"
    categories: list[object]
    choose_filter: U_choose_filter
    chooser_scope: str
    sacrifice_filter: U_sacrifice_filter
    keeper_constraint: U_keeper_constraint = MISSING
    total_power_cap: U_total_power_cap = MISSING


@dataclass(frozen=True)
class T_effect__ChooseAugmentAndCombineWithHost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseAugmentAndCombineWithHost"
    filter: U_filter
    host: U_host
    zones: list[object]


@dataclass(frozen=True)
class T_effect__ChooseCounterAdjustment(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseCounterAdjustment"
    adjustment: str
    count: U_count


@dataclass(frozen=True)
class T_effect__ChooseCounterKind(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseCounterKind"
    target: U_target


@dataclass(frozen=True)
class T_effect__ChooseDrawnThisTurnPayOrTopdeck(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseDrawnThisTurnPayOrTopdeck"
    count: U_count
    life_payment: U_life_payment
    player: U_player


@dataclass(frozen=True)
class T_effect__ChooseFromZone(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseFromZone"
    chooser: str
    count: int
    up_to: bool
    zone: str
    zone_owner: str
    additional_zones: list[object] = MISSING
    constraint: U_constraint = MISSING
    filter: U_filter = MISSING
    random: bool = MISSING


@dataclass(frozen=True)
class T_effect__ChooseObjectsIntoTrackedSet(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseObjectsIntoTrackedSet"
    chooser: U_chooser
    filter: U_filter
    max: None | int
    min: int


@dataclass(frozen=True)
class T_effect__ChooseOneOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ChooseOneOf"
    branches: list[S_branches]
    chooser: U_chooser


@dataclass(frozen=True)
class T_effect__Clash(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Clash"


@dataclass(frozen=True)
class T_effect__Cloak(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Cloak"
    count: U_count
    enters_under: str
    target: U_target
    object_source: U_object_source = MISSING


@dataclass(frozen=True)
class T_effect__CollectEvidence(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CollectEvidence"
    amount: int


@dataclass(frozen=True)
class T_effect__CombineHost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CombineHost"
    host: U_host
    source: str


@dataclass(frozen=True)
class T_effect__Conjure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Conjure"
    cards: list[S_cards]
    destination: str
    tapped: bool
    library_players: U_library_players = MISSING
    library_position: U_library_position = MISSING


@dataclass(frozen=True)
class T_effect__Connive(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Connive"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__ControlNextTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ControlNextTurn"
    grant_extra_turn_after: bool
    target: U_target
    window: str


@dataclass(frozen=True)
class T_effect__CopySpell(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopySpell"
    retarget: U_retarget
    starting_loyalty_from_casualty_sacrifice: bool
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    copier: str = MISSING


@dataclass(frozen=True)
class T_effect__CopyTokenBlockingAttacker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopyTokenBlockingAttacker"
    owner: U_owner
    source_filter: U_source_filter


@dataclass(frozen=True)
class T_effect__CopyTokenOf(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CopyTokenOf"
    count: U_count
    enters_attacking: bool
    owner: U_owner
    tapped: bool
    target: U_target
    additional_modifications: list[U_additional_modifications] = MISSING
    extra_keywords: list[MirrorVariant] = MISSING
    source_filter: U_source_filter = MISSING


@dataclass(frozen=True)
class T_effect__Counter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Counter"
    target: U_target
    countered_spell_zone: U_countered_spell_zone = MISSING
    source_rider: U_source_rider = MISSING


@dataclass(frozen=True)
class T_effect__CounterAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CounterAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__CreateDamageReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDamageReplacement"
    combat_scope: str = MISSING
    modification: U_modification = MISSING
    recipient_object_filter: U_recipient_object_filter = MISSING
    redirect_amount: MirrorVariant = MISSING
    redirect_object_filter: U_redirect_object_filter = MISSING
    redirect_to: U_redirect_to = MISSING
    source_filter: U_source_filter = MISSING
    target_filter: MirrorVariant = MISSING


@dataclass(frozen=True)
class T_effect__CreateDelayedTrigger(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDelayedTrigger"
    condition: U_condition
    effect: S_effect
    uses_tracked_set: bool


@dataclass(frozen=True)
class T_effect__CreateDrawReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateDrawReplacement"
    replacement_effect: U_replacement_effect


@dataclass(frozen=True)
class T_effect__CreateEmblem(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreateEmblem"
    statics: list[S_statics]
    triggers: list[S_triggers]


@dataclass(frozen=True)
class T_effect__CreatePlaneswalkReplacement(TypedMirrorNode):
    _tag: ClassVar[str | None] = "CreatePlaneswalkReplacement"
    replacement_effect: U_replacement_effect


@dataclass(frozen=True)
class T_effect__DamageAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageAll"
    amount: U_amount
    target: U_target
    damage_source: str = MISSING
    player_filter: U_player_filter = MISSING


@dataclass(frozen=True)
class T_effect__DamageEachPlayer(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DamageEachPlayer"
    amount: U_amount
    player_filter: U_player_filter


@dataclass(frozen=True)
class T_effect__DealDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DealDamage"
    amount: U_amount
    target: U_target
    damage_source: str = MISSING
    excess: U_excess = MISSING


@dataclass(frozen=True)
class T_effect__Destroy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Destroy"
    cant_regenerate: bool
    target: U_target


@dataclass(frozen=True)
class T_effect__DestroyAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DestroyAll"
    cant_regenerate: bool
    target: U_target


@dataclass(frozen=True)
class T_effect__Detain(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Detain"
    target: U_target


@dataclass(frozen=True)
class T_effect__Dig(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Dig"
    count: U_count
    destination: None | str
    enter_tapped: bool
    filter: U_filter
    keep_count: None | int
    player: U_player
    rest_destination: None | str
    reveal: bool
    up_to: bool
    keep_count_expr: U_keep_count_expr = MISSING
    source: str = MISSING


@dataclass(frozen=True)
class T_effect__Discard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discard"
    count: U_count
    target: U_target
    filter: U_filter = MISSING
    random: bool = MISSING
    unless_filter: U_unless_filter = MISSING


@dataclass(frozen=True)
class T_effect__DiscardCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DiscardCard"
    count: int
    target: U_target


@dataclass(frozen=True)
class T_effect__Discover(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Discover"
    mana_value_limit: U_mana_value_limit
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__Double(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Double"
    target: U_target
    target_kind: U_target_kind


@dataclass(frozen=True)
class T_effect__DoublePT(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoublePT"
    factor: int
    mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__DoublePTAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DoublePTAll"
    factor: int
    mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__DraftFromSpellbook(TypedMirrorNode):
    _tag: ClassVar[str | None] = "DraftFromSpellbook"
    destination: str
    random: bool
    tapped: bool


@dataclass(frozen=True)
class T_effect__Draw(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Draw"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__EachDealsDamageEqualToPower(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachDealsDamageEqualToPower"
    recipient: U_recipient
    sources: U_sources
    extra_source: U_extra_source = MISSING


@dataclass(frozen=True)
class T_effect__EachPlayerCopyChosen(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachPlayerCopyChosen"
    choose_filter: U_choose_filter
    choose_scope: U_choose_scope
    copy_modifications: list[U_copy_modifications]
    max: int
    min: int
    scale: S_scale = MISSING


@dataclass(frozen=True)
class T_effect__EachSourceDealsDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EachSourceDealsDamage"
    amount: U_amount
    recipient: U_recipient
    sources: U_sources


@dataclass(frozen=True)
class T_effect__Encore(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Encore"


@dataclass(frozen=True)
class T_effect__EndCombatPhase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndCombatPhase"


@dataclass(frozen=True)
class T_effect__EndTheTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "EndTheTurn"


@dataclass(frozen=True)
class T_effect__Endure(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Endure"
    amount: U_amount
    subject: U_subject


@dataclass(frozen=True)
class T_effect__ExchangeControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeControl"
    target_a: U_target_a
    target_b: U_target_b


@dataclass(frozen=True)
class T_effect__ExchangeLifeTotals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeLifeTotals"
    player_a: U_player_a
    player_b: U_player_b


@dataclass(frozen=True)
class T_effect__ExchangeLifeWithStat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExchangeLifeWithStat"
    player: U_player
    stat: str


@dataclass(frozen=True)
class T_effect__ExileFromTopUntil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileFromTopUntil"
    player: U_player
    until: U_until


@dataclass(frozen=True)
class T_effect__ExileHaunting(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileHaunting"
    target: U_target


@dataclass(frozen=True)
class T_effect__ExileResolvingSpellInsteadOfGraveyard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileResolvingSpellInsteadOfGraveyard"
    on_exile: str | MirrorVariant = MISSING


@dataclass(frozen=True)
class T_effect__ExileTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExileTop"
    count: U_count
    player: U_player
    face_down: bool = MISSING


@dataclass(frozen=True)
class T_effect__Explore(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Explore"


@dataclass(frozen=True)
class T_effect__ExploreAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExploreAll"
    filter: U_filter


@dataclass(frozen=True)
class T_effect__ExtraTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ExtraTurn"
    target: U_target


@dataclass(frozen=True)
class T_effect__Fight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Fight"
    subject: U_subject
    target: U_target


@dataclass(frozen=True)
class T_effect__FlipCoin(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoin"
    lose_effect: None | S_lose_effect
    win_effect: None | S_win_effect
    flipper: U_flipper = MISSING


@dataclass(frozen=True)
class T_effect__FlipCoinUntilLose(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoinUntilLose"
    win_effect: S_win_effect


@dataclass(frozen=True)
class T_effect__FlipCoins(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FlipCoins"
    count: U_count
    lose_effect: None
    win_effect: None | S_win_effect


@dataclass(frozen=True)
class T_effect__ForEachCategory(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForEachCategory"
    action: U_action
    category: str
    chooser: str


@dataclass(frozen=True)
class T_effect__Forage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Forage"


@dataclass(frozen=True)
class T_effect__ForceAttack(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForceAttack"
    duration: str
    required_player: U_required_player
    target: U_target


@dataclass(frozen=True)
class T_effect__ForceBlock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ForceBlock"
    target: U_target


@dataclass(frozen=True)
class T_effect__FreeCastFromZones(TypedMirrorNode):
    _tag: ClassVar[str | None] = "FreeCastFromZones"
    count: int
    filter: U_filter
    zones: list[object]
    exile_instead_of_graveyard: bool = MISSING
    max_total_mv: int = MISSING


@dataclass(frozen=True)
class T_effect__GainActivatedAbilitiesOfTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainActivatedAbilitiesOfTarget"
    duration: str
    recipient: U_recipient
    scope: str
    target: U_target


@dataclass(frozen=True)
class T_effect__GainControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainControl"
    target: U_target


@dataclass(frozen=True)
class T_effect__GainControlAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainControlAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__GainEnergy(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainEnergy"
    amount: U_amount


@dataclass(frozen=True)
class T_effect__GainLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GainLife"
    amount: U_amount
    player: U_player = MISSING


@dataclass(frozen=True)
class T_effect__GenericEffect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GenericEffect"
    duration: None | str | MirrorVariant
    static_abilities: list[S_static_abilities]
    target: None | U_target


@dataclass(frozen=True)
class T_effect__GiftDelivery(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GiftDelivery"
    kind: U_kind


@dataclass(frozen=True)
class T_effect__GiveControl(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GiveControl"
    recipient: U_recipient
    target: U_target


@dataclass(frozen=True)
class T_effect__GivePlayerCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GivePlayerCounter"
    count: U_count
    counter_kind: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Goad(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Goad"
    target: U_target


@dataclass(frozen=True)
class T_effect__GoadAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GoadAll"
    target: U_target


@dataclass(frozen=True)
class T_effect__GrantCastingPermission(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantCastingPermission"
    permission: U_permission
    target: U_target
    grantee: U_grantee = MISSING


@dataclass(frozen=True)
class T_effect__GrantExtraLoyaltyActivations(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantExtraLoyaltyActivations"
    amount: U_amount
    target: U_target


@dataclass(frozen=True)
class T_effect__GrantNextSpellAbility(TypedMirrorNode):
    _tag: ClassVar[str | None] = "GrantNextSpellAbility"
    modifier: U_modifier
    player: U_player
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_effect__Harness(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Harness"


@dataclass(frozen=True)
class T_effect__Heist(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Heist"
    look_count: int
    target: U_target


@dataclass(frozen=True)
class T_effect__HideawayConceal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "HideawayConceal"
    target: U_target


@dataclass(frozen=True)
class T_effect__Incubate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Incubate"
    count: U_count


@dataclass(frozen=True)
class T_effect__Intensify(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Intensify"
    amount: U_amount
    scope: U_scope


@dataclass(frozen=True)
class T_effect__Investigate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Investigate"


@dataclass(frozen=True)
class T_effect__Learn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Learn"


@dataclass(frozen=True)
class T_effect__LoseAllPlayerCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseAllPlayerCounters"
    target: U_target


@dataclass(frozen=True)
class T_effect__LoseLife(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseLife"
    amount: U_amount
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__LoseTheGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "LoseTheGame"
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__MadnessCast(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MadnessCast"
    cost: U_cost


@dataclass(frozen=True)
class T_effect__Mana(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mana"
    produced: U_produced
    expiry: str = MISSING
    grants: list[U_grants | MirrorVariant] = MISSING
    restrictions: list[MirrorVariant] = MISSING
    target: U_target = MISSING


@dataclass(frozen=True)
class T_effect__Manifest(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Manifest"
    count: U_count
    target: U_target
    enters_under: str = MISSING
    profile: S_profile = MISSING


@dataclass(frozen=True)
class T_effect__ManifestDread(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ManifestDread"


@dataclass(frozen=True)
class T_effect__Meld(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Meld"
    entry: U_entry
    partner: str
    partner_filter: U_partner_filter
    result: str
    source: str
    source_filter: U_source_filter


@dataclass(frozen=True)
class T_effect__Mill(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Mill"
    count: U_count
    destination: str
    target: U_target


@dataclass(frozen=True)
class T_effect__Monstrosity(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Monstrosity"
    count: U_count


@dataclass(frozen=True)
class T_effect__MoveCounters(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MoveCounters"
    count: None | U_count
    counter_type: None | str
    mode: str
    selection: str
    source: U_source
    target: U_target


@dataclass(frozen=True)
class T_effect__MultiplyCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "MultiplyCounter"
    counter_type: str
    multiplier: int
    target: U_target


@dataclass(frozen=True)
class T_effect__Myriad(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Myriad"


@dataclass(frozen=True)
class T_effect__NoOp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "NoOp"


@dataclass(frozen=True)
class T_effect__OpenAttractions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpenAttractions"
    count: int


@dataclass(frozen=True)
class T_effect__OpponentGuess(TypedMirrorNode):
    _tag: ClassVar[str | None] = "OpponentGuess"
    guesser: str | MirrorVariant
    subject: U_subject


@dataclass(frozen=True)
class T_effect__PairWith(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PairWith"
    target: U_target


@dataclass(frozen=True)
class T_effect__PayCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PayCost"
    cost: U_cost
    payer: U_payer
    scale: U_scale = MISSING


@dataclass(frozen=True)
class T_effect__PhaseIn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PhaseIn"
    target: U_target


@dataclass(frozen=True)
class T_effect__PhaseOut(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PhaseOut"
    target: U_target


@dataclass(frozen=True)
class T_effect__Planeswalk(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Planeswalk"


@dataclass(frozen=True)
class T_effect__Populate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Populate"


@dataclass(frozen=True)
class T_effect__PreventDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PreventDamage"
    amount: str | MirrorVariant
    scope: str
    target: U_target
    amount_dynamic: U_amount_dynamic = MISSING
    damage_source_filter: U_damage_source_filter = MISSING
    prevention_duration: str = MISSING


@dataclass(frozen=True)
class T_effect__Proliferate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Proliferate"


@dataclass(frozen=True)
class T_effect__ProliferateTarget(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ProliferateTarget"
    target: U_target


@dataclass(frozen=True)
class T_effect__Pump(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Pump"
    power: U_power
    target: U_target
    toughness: U_toughness


@dataclass(frozen=True)
class T_effect__PumpAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PumpAll"
    power: U_power
    target: U_target
    toughness: U_toughness


@dataclass(frozen=True)
class T_effect__PutAtLibraryPosition(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutAtLibraryPosition"
    count: U_count
    position: U_position
    target: U_target


@dataclass(frozen=True)
class T_effect__PutChosenCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutChosenCounter"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__PutCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutCounter"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_effect__PutCounterAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutCounterAll"
    count: U_count
    counter_type: str
    target: U_target


@dataclass(frozen=True)
class T_effect__PutOnTopOrBottom(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutOnTopOrBottom"
    target: U_target


@dataclass(frozen=True)
class T_effect__PutSticker(TypedMirrorNode):
    _tag: ClassVar[str | None] = "PutSticker"
    count: U_count
    target: U_target
    kind: str = MISSING
    max_ticket_cost: U_max_ticket_cost = MISSING
    ticket_cost_payment: str = MISSING


@dataclass(frozen=True)
class T_effect__ReassembleContraption(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReassembleContraption"
    control_mode: str
    target: U_target


@dataclass(frozen=True)
class T_effect__RedistributeLifeTotals(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RedistributeLifeTotals"


@dataclass(frozen=True)
class T_effect__ReduceNextSpellCost(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReduceNextSpellCost"
    amount: int
    spell_filter: U_spell_filter = MISSING


@dataclass(frozen=True)
class T_effect__Regenerate(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Regenerate"
    target: U_target


@dataclass(frozen=True)
class T_effect__RegisterBending(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RegisterBending"
    kind: str


@dataclass(frozen=True)
class T_effect__RememberCard(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RememberCard"
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveAllDamage(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveAllDamage"
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveCounter(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveCounter"
    count: U_count
    counter_type: None | str
    target: U_target


@dataclass(frozen=True)
class T_effect__RemoveFromCombat(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RemoveFromCombat"
    target: U_target


@dataclass(frozen=True)
class T_effect__Renown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Renown"
    count: U_count


@dataclass(frozen=True)
class T_effect__ReturnAsAura(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReturnAsAura"
    enchant_filter: U_enchant_filter
    grants: list[U_grants | MirrorVariant]


@dataclass(frozen=True)
class T_effect__Reveal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Reveal"
    target: U_target


@dataclass(frozen=True)
class T_effect__RevealFromHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealFromHand"
    filter: U_filter
    on_decline: S_on_decline


@dataclass(frozen=True)
class T_effect__RevealHand(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealHand"
    card_filter: U_card_filter
    count: None | U_count
    reveal: bool
    target: U_target
    choice_optional: bool = MISSING
    random: bool = MISSING


@dataclass(frozen=True)
class T_effect__RevealTop(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealTop"
    count: int
    player: U_player


@dataclass(frozen=True)
class T_effect__RevealUntil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RevealUntil"
    count: U_count
    filter: U_filter
    kept_destination: str
    player: U_player
    rest_destination: str
    enter_tapped: bool = MISSING
    enters_attacking: bool = MISSING
    enters_under: str = MISSING
    kept_optional_to: str = MISSING
    matched_disposition: U_matched_disposition = MISSING


@dataclass(frozen=True)
class T_effect__ReverseTurnOrder(TypedMirrorNode):
    _tag: ClassVar[str | None] = "ReverseTurnOrder"


@dataclass(frozen=True)
class T_effect__RingTemptsYou(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RingTemptsYou"


@dataclass(frozen=True)
class T_effect__RollDie(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RollDie"
    count: U_count
    results: list[S_results]
    sides: int
    modifier: U_modifier = MISSING


@dataclass(frozen=True)
class T_effect__RollToVisitAttractions(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RollToVisitAttractions"


@dataclass(frozen=True)
class T_effect__RuntimeHandled(TypedMirrorNode):
    _tag: ClassVar[str | None] = "RuntimeHandled"
    handler: str


@dataclass(frozen=True)
class T_effect__Sacrifice(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Sacrifice"
    count: U_count
    target: U_target
    min_count: int = MISSING


@dataclass(frozen=True)
class T_effect__Scry(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Scry"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__SearchLibrary(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SearchLibrary"
    count: U_count
    filter: U_filter
    reveal: bool
    selection_constraint: U_selection_constraint = MISSING
    source_zones: list[object] = MISSING
    split: S_split = MISSING
    target_player: U_target_player = MISSING


@dataclass(frozen=True)
class T_effect__SearchOutsideGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SearchOutsideGame"
    count: U_count
    destination: str
    filter: U_filter
    reveal: bool
    source_pool: U_source_pool = MISSING


@dataclass(frozen=True)
class T_effect__Seek(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Seek"
    count: U_count
    destination: str
    enter_tapped: bool
    filter: U_filter
    from_top: int = MISSING


@dataclass(frozen=True)
class T_effect__SeparateIntoPiles(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SeparateIntoPiles"
    chooser: U_chooser
    chosen_pile_effect: S_chosen_pile_effect
    object_filter: U_object_filter
    partition_subject: U_partition_subject
    pile_source: U_pile_source
    unchosen_pile_effect: None | S_unchosen_pile_effect


@dataclass(frozen=True)
class T_effect__SetClassLevel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetClassLevel"
    level: int


@dataclass(frozen=True)
class T_effect__SetDayNight(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetDayNight"
    to: str


@dataclass(frozen=True)
class T_effect__SetLifeTotal(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetLifeTotal"
    amount: U_amount
    target: U_target


@dataclass(frozen=True)
class T_effect__SetRoomDoorLock(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetRoomDoorLock"
    op: U_op
    target: U_target


@dataclass(frozen=True)
class T_effect__SetTapState(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SetTapState"
    scope: U_scope
    state: U_state
    target: U_target


@dataclass(frozen=True)
class T_effect__Shuffle(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Shuffle"
    target: U_target


@dataclass(frozen=True)
class T_effect__SkipNextStep(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SkipNextStep"
    count: U_count
    scope: str
    step: U_step
    target: U_target


@dataclass(frozen=True)
class T_effect__SkipNextTurn(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SkipNextTurn"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__SolveCase(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SolveCase"


@dataclass(frozen=True)
class T_effect__Specialize(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Specialize"


@dataclass(frozen=True)
class T_effect__StartYourEngines(TypedMirrorNode):
    _tag: ClassVar[str | None] = "StartYourEngines"
    player_scope: U_player_scope


@dataclass(frozen=True)
class T_effect__Surveil(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Surveil"
    count: U_count
    target: U_target


@dataclass(frozen=True)
class T_effect__Suspect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Suspect"
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__SwapChosenLabels(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwapChosenLabels"
    first: str
    second: str


@dataclass(frozen=True)
class T_effect__SwitchPT(TypedMirrorNode):
    _tag: ClassVar[str | None] = "SwitchPT"
    target: U_target


@dataclass(frozen=True)
class T_effect__TakeTheInitiative(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TakeTheInitiative"


@dataclass(frozen=True)
class T_effect__TargetOnly(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TargetOnly"
    target: U_target


@dataclass(frozen=True)
class T_effect__TimeTravel(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TimeTravel"


@dataclass(frozen=True)
class T_effect__Token(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Token"
    colors: list[U_colors]
    count: U_count
    enters_attacking: bool
    keywords: list[MirrorVariant]
    name: str
    owner: U_owner
    power: U_power
    tapped: bool
    toughness: U_toughness
    types: list[object]
    attach_to: U_attach_to = MISSING
    enter_with_counters: list[U_enter_with_counters] = MISSING
    static_abilities: list[S_static_abilities] = MISSING
    supertypes: list[object] = MISSING


@dataclass(frozen=True)
class T_effect__Transform(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Transform"
    target: U_target


@dataclass(frozen=True)
class T_effect__Tribute(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Tribute"
    count: int


@dataclass(frozen=True)
class T_effect__TurnFaceDown(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnFaceDown"
    profile: S_profile
    target: U_target


@dataclass(frozen=True)
class T_effect__TurnFaceUp(TypedMirrorNode):
    _tag: ClassVar[str | None] = "TurnFaceUp"
    target: U_target


@dataclass(frozen=True)
class T_effect__UnattachAll(TypedMirrorNode):
    _tag: ClassVar[str | None] = "UnattachAll"
    attachment: U_attachment
    target: U_target


@dataclass(frozen=True)
class T_effect__Unimplemented(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unimplemented"
    description: None | str
    name: str


@dataclass(frozen=True)
class T_effect__Unsuspect(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Unsuspect"
    scope: U_scope
    target: U_target


@dataclass(frozen=True)
class T_effect__VentureIntoDungeon(TypedMirrorNode):
    _tag: ClassVar[str | None] = "VentureIntoDungeon"


@dataclass(frozen=True)
class T_effect__Vote(TypedMirrorNode):
    _tag: ClassVar[str | None] = "Vote"
    choices: list[object]
    per_choice_effect: list[S_per_choice_effect]
    starting_with: str
    subject: U_subject
    tally_mode: U_tally_mode
    visibility: U_visibility
    voter_scope: U_voter_scope


@dataclass(frozen=True)
class T_effect__WinTheGame(TypedMirrorNode):
    _tag: ClassVar[str | None] = "WinTheGame"
    target: U_target = MISSING


# --- discriminated-union aliases (one per tagged content_key) ---

type U_effect = (
    T_effect__Adapt
    | T_effect__AddPendingETBCounters
    | T_effect__AddPendingEntersModifications
    | T_effect__AddRestriction
    | T_effect__AddTargetReplacement
    | T_effect__AdditionalPhase
    | T_effect__Amass
    | T_effect__Animate
    | T_effect__ApplyPerpetual
    | T_effect__ArrangePlanarDeckTop
    | T_effect__AssembleContraptions
    | T_effect__Attach
    | T_effect__BecomeBlocked
    | T_effect__BecomeCopy
    | T_effect__BecomeMonarch
    | T_effect__BecomePrepared
    | T_effect__BecomeSaddled
    | T_effect__BecomeUnprepared
    | T_effect__Behold
    | T_effect__BlightEffect
    | T_effect__Bolster
    | T_effect__Bounce
    | T_effect__BounceAll
    | T_effect__CastCopyOfCard
    | T_effect__CastFromZone
    | T_effect__ChangeSpeed
    | T_effect__ChangeTargets
    | T_effect__ChangeZone
    | T_effect__ChangeZoneAll
    | T_effect__ChaosEnsues
    | T_effect__Choose
    | T_effect__ChooseAndSacrificeRest
    | T_effect__ChooseAugmentAndCombineWithHost
    | T_effect__ChooseCounterAdjustment
    | T_effect__ChooseCounterKind
    | T_effect__ChooseDrawnThisTurnPayOrTopdeck
    | T_effect__ChooseFromZone
    | T_effect__ChooseObjectsIntoTrackedSet
    | T_effect__ChooseOneOf
    | T_effect__Clash
    | T_effect__Cloak
    | T_effect__CollectEvidence
    | T_effect__CombineHost
    | T_effect__Conjure
    | T_effect__Connive
    | T_effect__ControlNextTurn
    | T_effect__CopySpell
    | T_effect__CopyTokenBlockingAttacker
    | T_effect__CopyTokenOf
    | T_effect__Counter
    | T_effect__CounterAll
    | T_effect__CreateDamageReplacement
    | T_effect__CreateDelayedTrigger
    | T_effect__CreateDrawReplacement
    | T_effect__CreateEmblem
    | T_effect__CreatePlaneswalkReplacement
    | T_effect__DamageAll
    | T_effect__DamageEachPlayer
    | T_effect__DealDamage
    | T_effect__Destroy
    | T_effect__DestroyAll
    | T_effect__Detain
    | T_effect__Dig
    | T_effect__Discard
    | T_effect__DiscardCard
    | T_effect__Discover
    | T_effect__Double
    | T_effect__DoublePT
    | T_effect__DoublePTAll
    | T_effect__DraftFromSpellbook
    | T_effect__Draw
    | T_effect__EachDealsDamageEqualToPower
    | T_effect__EachPlayerCopyChosen
    | T_effect__EachSourceDealsDamage
    | T_effect__Encore
    | T_effect__EndCombatPhase
    | T_effect__EndTheTurn
    | T_effect__Endure
    | T_effect__ExchangeControl
    | T_effect__ExchangeLifeTotals
    | T_effect__ExchangeLifeWithStat
    | T_effect__ExileFromTopUntil
    | T_effect__ExileHaunting
    | T_effect__ExileResolvingSpellInsteadOfGraveyard
    | T_effect__ExileTop
    | T_effect__Explore
    | T_effect__ExploreAll
    | T_effect__ExtraTurn
    | T_effect__Fight
    | T_effect__FlipCoin
    | T_effect__FlipCoinUntilLose
    | T_effect__FlipCoins
    | T_effect__ForEachCategory
    | T_effect__Forage
    | T_effect__ForceAttack
    | T_effect__ForceBlock
    | T_effect__FreeCastFromZones
    | T_effect__GainActivatedAbilitiesOfTarget
    | T_effect__GainControl
    | T_effect__GainControlAll
    | T_effect__GainEnergy
    | T_effect__GainLife
    | T_effect__GenericEffect
    | T_effect__GiftDelivery
    | T_effect__GiveControl
    | T_effect__GivePlayerCounter
    | T_effect__Goad
    | T_effect__GoadAll
    | T_effect__GrantCastingPermission
    | T_effect__GrantExtraLoyaltyActivations
    | T_effect__GrantNextSpellAbility
    | T_effect__Harness
    | T_effect__Heist
    | T_effect__HideawayConceal
    | T_effect__Incubate
    | T_effect__Intensify
    | T_effect__Investigate
    | T_effect__Learn
    | T_effect__LoseAllPlayerCounters
    | T_effect__LoseLife
    | T_effect__LoseTheGame
    | T_effect__MadnessCast
    | T_effect__Mana
    | T_effect__Manifest
    | T_effect__ManifestDread
    | T_effect__Meld
    | T_effect__Mill
    | T_effect__Monstrosity
    | T_effect__MoveCounters
    | T_effect__MultiplyCounter
    | T_effect__Myriad
    | T_effect__NoOp
    | T_effect__OpenAttractions
    | T_effect__OpponentGuess
    | T_effect__PairWith
    | T_effect__PayCost
    | T_effect__PhaseIn
    | T_effect__PhaseOut
    | T_effect__Planeswalk
    | T_effect__Populate
    | T_effect__PreventDamage
    | T_effect__Proliferate
    | T_effect__ProliferateTarget
    | T_effect__Pump
    | T_effect__PumpAll
    | T_effect__PutAtLibraryPosition
    | T_effect__PutChosenCounter
    | T_effect__PutCounter
    | T_effect__PutCounterAll
    | T_effect__PutOnTopOrBottom
    | T_effect__PutSticker
    | T_effect__ReassembleContraption
    | T_effect__RedistributeLifeTotals
    | T_effect__ReduceNextSpellCost
    | T_effect__Regenerate
    | T_effect__RegisterBending
    | T_effect__RememberCard
    | T_effect__RemoveAllDamage
    | T_effect__RemoveCounter
    | T_effect__RemoveFromCombat
    | T_effect__Renown
    | T_effect__ReturnAsAura
    | T_effect__Reveal
    | T_effect__RevealFromHand
    | T_effect__RevealHand
    | T_effect__RevealTop
    | T_effect__RevealUntil
    | T_effect__ReverseTurnOrder
    | T_effect__RingTemptsYou
    | T_effect__RollDie
    | T_effect__RollToVisitAttractions
    | T_effect__RuntimeHandled
    | T_effect__Sacrifice
    | T_effect__Scry
    | T_effect__SearchLibrary
    | T_effect__SearchOutsideGame
    | T_effect__Seek
    | T_effect__SeparateIntoPiles
    | T_effect__SetClassLevel
    | T_effect__SetDayNight
    | T_effect__SetLifeTotal
    | T_effect__SetRoomDoorLock
    | T_effect__SetTapState
    | T_effect__Shuffle
    | T_effect__SkipNextStep
    | T_effect__SkipNextTurn
    | T_effect__SolveCase
    | T_effect__Specialize
    | T_effect__StartYourEngines
    | T_effect__Surveil
    | T_effect__Suspect
    | T_effect__SwapChosenLabels
    | T_effect__SwitchPT
    | T_effect__TakeTheInitiative
    | T_effect__TargetOnly
    | T_effect__TimeTravel
    | T_effect__Token
    | T_effect__Transform
    | T_effect__Tribute
    | T_effect__TurnFaceDown
    | T_effect__TurnFaceUp
    | T_effect__UnattachAll
    | T_effect__Unimplemented
    | T_effect__Unsuspect
    | T_effect__VentureIntoDungeon
    | T_effect__Vote
    | T_effect__WinTheGame
)
