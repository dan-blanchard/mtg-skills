"""The "a creature dies" family: links and waits read off a card's trees.

CR 700.4: "The term dies means 'is put into a graveyard from the battlefield.'"

* :func:`death_links` — every way a card's own text can put a creature into a
  graveyard from the battlefield, each a :class:`DeathLink` with the facts that
  make it strong or weak: the route and its rule, certain or needing a big
  enough number, whose creature, one or all, cost or effect, how it is
  delivered, whether it repeats.
* :func:`death_waits` — every trigger of the card that waits for a creature
  dying (or being sacrificed), a :class:`DeathWait` with whose creature it
  watches.
* :func:`feeds` — whether a link can make the creature a wait watches die.

Nothing here rules a card in or out. The rows are rules steps and phase
vocabulary, each checked against ``rules-lookup``; no row names a card.
:data:`EFFECT_ROUTES`, :data:`UNREAD_DEATH_EFFECTS` and :data:`NO_DEATH_EFFECTS`
partition phase's closed ``Effect`` enum (the roster gate in
``test_links_deaths``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.card_reads import card_read
from mtg_utils._analysis.lanes._shared import sacrificing_side
from mtg_utils._card_ir.crosswalk.reads import (
    acts_on_a_group,
    corrected_scope,
    counter_kind_any,
    effect_decided_by_another,
    filter_can_name_creature,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    iter_cost_leaves,
    iter_static_defs,
    list_field,
    negative_pt_field,
    static_affected,
    tag_of,
    trigger_zone_changes,
    unit_repeats,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk.core import AbilityUnit, ConceptNode, ConceptTree

#: route -> (rule, certain). Every route ends in CR 700.4 ("dies" means "is put
#: into a graveyard from the battlefield"). A route is certain when the
#: instruction itself moves the creature there, and uncertain when a
#: state-based action does it only if a number is big enough.
ROUTES: dict[str, tuple[str, bool]] = {
    # 701.8a: "To destroy a permanent, move it from the battlefield to its
    # owner's graveyard."
    "destroy": ("CR 701.8a + 700.4", True),
    # 701.21a: "To sacrifice a permanent, its controller moves it from the
    # battlefield directly to its owner's graveyard."
    "sacrifice": ("CR 701.21a + 700.4", True),
    # A move from the battlefield to a graveyard is the definition itself.
    "move": ("CR 700.4", True),
    # 704.5g: a creature with damage marked on it at least equal to its
    # toughness "has been dealt lethal damage and is destroyed".
    "damage": ("CR 704.5g + 701.8a + 700.4", False),
    # 701.14a: "Each of those creatures deals damage equal to its power to the
    # other creature."
    "fight": ("CR 701.14a + 704.5g + 700.4", False),
    # 704.5f: "If a creature has toughness 0 or less, it's put into its
    # owner's graveyard."
    "shrink": ("CR 704.5f + 700.4", False),
}

#: phase effect tag -> (route, reach). The reach is the tag's own; an effect
#: phase types as one object but the recovery stage marks as a population
#: (``reads.acts_on_a_group``) reaches all.
EFFECT_ROUTES: dict[str, tuple[str, str]] = {
    "Destroy": ("destroy", "one"),
    "DestroyAll": ("destroy", "all"),
    "Sacrifice": ("sacrifice", "one"),
    "ChooseAndSacrificeRest": ("sacrifice", "all"),
    "DealDamage": ("damage", "one"),
    "DamageAll": ("damage", "all"),
    "EachSourceDealsDamage": ("damage", "all"),
    "EachDealsDamageEqualToPower": ("damage", "all"),
    "Fight": ("fight", "one"),
    "Pump": ("shrink", "one"),
    "PumpAll": ("shrink", "all"),
    "PutCounter": ("shrink", "one"),
    "PutCounterAll": ("shrink", "all"),
    "ChangeZone": ("move", "one"),
    "ChangeZoneAll": ("move", "all"),
}

#: phase effect tags that can make a creature die but that no route above reads,
#: each with how. Gaps, not verdicts: a row moves to :data:`EFFECT_ROUTES` once a
#: read for it lands. ``test_links_deaths``'s roster gate keeps these, the routes
#: and :data:`NO_DEATH_EFFECTS` a partition of phase's ``Effect`` enum.
UNREAD_DEATH_EFFECTS: dict[str, str] = {
    # Damage steps phase's engine runs (no card emits them at the pin).
    "ApplyPostReplacementDamage": "damage dealt after replacement (CR 704.5g)",
    "ResumeDamageBatch": "a resumed batch of damage (CR 704.5g)",
    # Toughness lowered by counters (CR 704.5f; CR 122.1: a counter modifies
    # its object's characteristics).
    "RemoveCounter": "removing +1/+1 counters lowers toughness",
    "Proliferate": "another -1/-1 counter (CR 701.34a)",
    "ProliferateTarget": "another -1/-1 counter of a kind already there",
    "MultiplyCounter": "doubling -1/-1 counters",
    "Double": "doubling each kind of counter (Deepglow Skate)",
    "ChooseCounterAdjustment": "removing a chosen counter (Clockspinning)",
    "MoveCounters": "moving +1/+1 counters off, or -1/-1 counters on",
    "PutChosenCounter": "a chosen kind of counter, -1/-1 among them",
    "ReproduceEventCounters": "the same kind of counters, -1/-1 among them",
    "BlightEffect": "-1/-1 counters on a creature you control (CR 701.68a)",
    # Toughness set or switched.
    "SwitchPT": "a 0-power creature's toughness becomes 0 (CR 613.4d)",
    "ExchangeLifeWithStat": "toughness set to a life total (CR 701.12g)",
    # Containers whose contents this read doesn't open.
    "GenericEffect": "a conferred continuous effect: -N/-N, a granted ability",
    "ApplyPerpetual": "a perpetual -N/-N (on the battlefield, read as its Pump view)",
    "CreateEmblem": "an emblem's abilities (a known gap)",
    "CreateBoon": "a boon's one-time trigger",
    "PayCost": "a cost paid on resolution: sacrifice a creature (Crypt Lurker)",
    # A sacrifice the keyword's own rule makes.
    "Encore": "the token copies are sacrificed at the next end step (CR 702.141a)",
    "Exploit": "you may sacrifice a creature (CR 702.110a)",
    # A clause phase left unparsed; RECOVERED_ROUTES reads the ones recovered.
    "Unimplemented": "an unparsed clause (a known gap)",
}

#: phase effect tags that make no creature die by themselves: what they do never
#: puts a creature into a graveyard from the battlefield or lowers a toughness.
#: A container's contents (a vote's outcomes, a delayed trigger's body, a coin
#: flip's results) are read as their own nodes.
NO_DEATH_EFFECTS: frozenset[str] = frozenset(
    {
        # draw, life, mana, library, hand and graveyard cards
        "Draw",
        "GainLife",
        "LoseLife",
        "SetLifeTotal",
        "ExchangeLifeTotals",
        "RedistributeLifeTotals",
        "DamageEachPlayer",  # players only
        "Mana",
        "DiscardCard",
        "Discard",
        "Mill",
        "Scry",
        "Surveil",
        "Dig",
        "Shuffle",
        "SearchLibrary",
        "SearchOutsideGame",
        "RevealHand",
        "RevealFromHand",
        "Reveal",
        "RevealChosenNumbers",
        "RevealTop",
        "RevealUntil",
        "ExileTop",
        "ExileFromTopUntil",
        "ExileFaceDownPile",
        "ExileTopCardContest",
        "PutAtLibraryPosition",
        "PutOnTopOrBottom",
        "ChooseDrawnThisTurnPayOrTopdeck",
        "ChooseFromZone",
        "CollectEvidence",
        "Learn",
        "Seek",
        "Conjure",
        "CreateCardCopyByName",
        "DraftFromSpellbook",
        "OpenBoosterPack",
        "Discover",
        "Cascade",
        "Ripple",
        "Heist",
        "HeistExile",
        "HideawayConceal",
        "SeparateIntoPiles",
        # casting and copying spells
        "Counter",  # a countered spell leaves the stack, not the battlefield
        "CounterAll",
        "CopySpell",
        "EpicCopy",
        "CastCopyOfCard",
        "CastFromZone",
        "FreeCastFromZones",
        "MiracleCast",
        "MadnessCast",
        "ExileResolvingSpellInsteadOfGraveyard",
        "GrantCastingPermission",
        "ReduceNextSpellCost",
        "GrantNextSpellAbility",
        "ChangeTargets",
        "ModifyAnnouncedX",
        # objects made or brought in
        "Token",
        "CopyTokenOf",  # "sacrifice it at end step" is its own delayed trigger
        "CreateTokenCopyFromPool",
        "Populate",
        "Myriad",  # its tokens are exiled, not put into a graveyard
        "Investigate",
        "Incubate",
        "Amass",
        "Manifest",
        "ManifestDread",
        "Cloak",
        "Endure",
        "CopyTokenBlockingAttacker",
        "EachPlayerCopyChosen",
        # counters that only raise, and their bookkeeping
        "ChooseCounterKind",
        "Tribute",
        "Monstrosity",
        "Renown",
        "Bolster",
        "Adapt",
        "Connive",
        "TimeTravel",
        "AddPendingETBCounters",
        "GainEnergy",
        "GivePlayerCounter",
        "LoseAllPlayerCounters",
        "ProcessRadCounters",
        "DoublePT",
        "DoublePTAll",
        # zones other than a graveyard, control, state
        "Bounce",
        "BounceAll",
        "PhaseOut",
        "PhaseIn",
        "GainControl",
        "GainControlAll",
        "ExchangeControl",
        "GiveControl",
        "ControlNextTurn",
        "SetTapState",
        "Regenerate",
        "RemoveAllDamage",
        "PreventDamage",
        "CreateDamageReplacement",  # changes damage another source deals
        "CreateDrawReplacement",
        "CreatePlaneswalkReplacement",
        "AddTargetReplacement",
        "AddRestriction",
        "AddPendingEntersModifications",
        "Explore",
        "ExploreAll",
        "PairWith",
        "Attach",
        "UnattachAll",
        "ReturnAsAura",
        "Meld",
        "CombineHost",
        "ChooseAugmentAndCombineWithHost",
        "ExileHaunting",
        "BecomeCopy",
        "Animate",
        "Transform",
        "FlipPermanent",
        "TurnFaceUp",
        "TurnFaceDown",
        "GainActivatedAbilitiesOfTarget",
        "RegisterBending",
        "Specialize",
        "Intensify",
        "Harness",
        "Suspect",
        "Unsuspect",
        "Goad",
        "GoadAll",
        "Detain",
        "ForceBlock",
        "ForceAttack",
        "RemoveFromCombat",
        "BecomeBlocked",
        "BecomeSaddled",
        "BecomePrepared",
        "BecomeUnprepared",
        "SetClassLevel",
        "SolveCase",
        "SetRoomDoorLock",
        "Forage",  # a Food is an artifact type (CR 205.3g), as the filter read has it
        # choices, notes, containers (their contents are read as their own nodes)
        "TargetOnly",
        "Choose",
        "ChoosePermanent",
        "ChooseCard",
        "ChooseDamageSource",
        "ChooseObjectsIntoTrackedSet",
        "ChooseOneOf",
        "OpponentGuess",
        "SwapChosenLabels",
        "NoteNumber",
        "NoteManaSpent",
        "RememberCard",
        "ForEachCategory",
        "Vote",
        "RollDie",
        "FlipCoins",
        "Clash",
        "PhysicalContest",
        "CreateDelayedTrigger",
        "GiftDelivery",
        "Behold",
        "NoOp",
        "RuntimeHandled",
        "CompletePlayerAction",
        "Cleanup",
        # turns, the game, and other game zones
        "StartYourEngines",
        "ChangeSpeed",
        "BecomeMonarch",
        "TakeTheInitiative",
        "RingTemptsYou",
        "VentureIntoDungeon",
        "VentureInto",
        "EndTheTurn",
        "EndCombatPhase",
        "ExtraTurn",
        "SkipNextTurn",
        "SkipNextStep",
        "AdditionalPhase",
        "GrantExtraLoyaltyActivations",
        "ReverseTurnOrder",
        "SetDayNight",
        "LoseTheGame",  # its objects leave the game (CR 800.4a)
        "WinTheGame",
        "EmpowerJace",
        "HordePlayCard",
        "ArrangePlanarDeckTop",
        "Planeswalk",
        "AbandonScheme",
        "ChaosEnsues",
        "OpenAttractions",
        "RollToVisitAttractions",
        "AssembleContraptions",
        "AssembleContraptionsFromRollDifference",
        "CrankContraptions",
        "ReassembleContraption",
        "AssembleContraptionOnSprocket",
        "ReassembleContraptionOnSprocket",
        "PutSticker",
        "ApplySticker",
    }
)

#: Keyword abilities whose own rule has a creature sacrificed; phase leaves these
#: to its engine, so no effect node carries them. keyword -> (defining subrule,
#: whose, delivery, repeatable).
KEYWORD_SACRIFICES: dict[str, tuple[str, str, str, bool]] = {
    # "When this creature enters, you may sacrifice a creature."
    "Exploit": ("CR 702.110a", "yours", "triggered:enters", False),
    # "As this object enters, you may sacrifice any number of creatures."
    "Devour": ("CR 702.82a", "yours", "replacement", False),
    # "As an additional cost to cast this spell, you may sacrifice a creature
    # with power N or greater."
    "Casualty": ("CR 702.153a", "yours", "cost", False),
    # "As an additional cost to cast this spell, you may sacrifice an artifact,
    # enchantment, or token": a token creature, or an artifact or enchantment
    # creature.
    "Bargain": ("CR 702.166a", "yours", "cost", False),
}

#: A node phase left unparsed, by the concept the repo's recovery stage read off
#: its description -> route.
RECOVERED_ROUTES: dict[str, str] = {
    "destroy": "destroy",
    "sacrifice": "sacrifice",
    "deal_damage": "damage",
    "fight": "fight",
}

#: The zone change a death is (CR 700.4), as ``reads.trigger_zone_changes`` spells it.
_DIES: tuple[str, str] = ("Battlefield", "Graveyard")

#: The ``properties`` tags that name the one creature an Aura or Equipment is on.
_ATTACHED_HOST_PREDICATES: frozenset[str] = frozenset({"EquippedBy", "EnchantedBy"})

#: A filter controller (``You`` / ``Opponent``) or a concept scope (``you`` /
#: ``opponents``) as the side whose creature it is.
_SIDES: dict[str, str] = {
    "You": "yours",
    "Opponent": "theirs",
    "you": "yours",
    "opponents": "theirs",
}


def _side(value: str | None, default: str) -> str:
    """``yours`` / ``theirs`` for a controller or a scope naming one, else
    ``default`` (``either`` for a link, ``any`` for a wait)."""
    return _SIDES.get(value or "", default)


@dataclass(frozen=True)
class DeathLink:
    """One way a card's text can make a creature die. Facts, never a verdict."""

    card: str
    route: str  # a ROUTES key
    rule: str
    certain: bool
    whose: str  # self | yours | theirs | either
    reach: str  # one | all
    role: str  # effect | cost | static
    delivery: str  # spell | activated | triggered:<event> | static | granted:<kind>
    repeatable: bool
    verb: str  # phase's effect tag, the keyword, or the modification


@dataclass(frozen=True)
class DeathWait:
    """One trigger of a card that waits for a creature dying or being sacrificed."""

    card: str
    event: str  # dies | sacrificed | exploited
    whose: str  # self | yours | theirs | any
    another: bool
    types: tuple[str, ...]
    #: The subtypes the watched creature has to have ("a nontoken Elemental"):
    #: any one of them. Empty: any creature.
    subtypes: tuple[str, ...] = ()
    #: ``True`` when it watches only tokens ("Whenever a creature token dies"),
    #: ``False`` when only nontokens, ``None`` either.
    tokens: bool | None = None


def _death_link(
    tree: ConceptTree,
    route: str,
    *,
    whose: str,
    reach: str,
    role: str,
    delivery: str,
    repeatable: bool,
    verb: str,
    rule: str | None = None,
    certain: bool = True,
) -> DeathLink:
    """A link by ``route``: its rule and certainty from :data:`ROUTES` (a
    keyword row names its own rule); ``certain=False`` makes a certain route
    uncertain, never the reverse."""
    route_rule, route_certain = ROUTES[route]
    return DeathLink(
        card=tree.name,
        route=route,
        rule=rule or route_rule,
        certain=route_certain and certain,
        whose=whose,
        reach=reach,
        role=role,
        delivery=delivery,
        repeatable=repeatable,
        verb=verb,
    )


def _delivery(unit: AbilityUnit, tree: ConceptTree) -> str:
    """How a unit's instructions are delivered."""
    if unit.origin == "trigger":
        return f"triggered:{unit.trigger_event or 'other'}"
    if unit.origin == "ability" and unit.kind == "Activated":
        return "activated"
    if unit.origin == "ability":
        spell = tree.is_type("Instant") or tree.is_type("Sorcery")
        return "spell" if spell else "on_resolution"
    return unit.origin


def _shrinks(tag: str, node: object) -> bool:
    """Whether a pump or a counter lowers toughness: a negative toughness
    (``reads.negative_pt_field``) or a -1/-1 counter."""
    if tag in ("Pump", "PumpAll"):
        return isinstance(node, TypedMirrorNode) and negative_pt_field(
            node, "toughness"
        )
    return isinstance(node, TypedMirrorNode) and counter_kind_any(node) == "M1M1"


def _instructions(
    nodes: tuple[ConceptNode, ...],
) -> Iterator[tuple[ConceptNode, TypedMirrorNode]]:
    """Each concept node's typed instruction; a composite cost opened into its
    leaves ("{B}, Sacrifice a creature" is one ``Composite`` node)."""
    for cnode in nodes:
        if cnode.role == "cost":
            for leaf in iter_cost_leaves(cnode.node):
                yield cnode, leaf
        else:
            yield cnode, cnode.node


def _host_side(tree: ConceptTree, affected: object) -> str | None:
    """Whose the creature an Equipment or Aura is attached to is, when the
    filter names it: an Equipment's is yours (CR 702.6a: equip attaches it to
    "target creature you control"; another effect or a change of control can
    move it, which this read doesn't follow); an Aura's is the side its printed
    enchant restriction names ("Enchant creature you control"), else ``None``
    (CR 303.4a: its target is defined by its enchant ability)."""
    preds = set(filter_predicates(affected))
    if "EquippedBy" in preds or (
        tag_of(affected) == "AttachedTo" and "Equipment" in tree.card_subtypes
    ):
        return "yours"
    if "EnchantedBy" in preds or tag_of(affected) == "AttachedTo":
        return _SIDES.get(filter_controller(tree.card_enchant_filter) or "")
    return None


def _link(
    tree: ConceptTree,
    node: TypedMirrorNode,
    role: str,
    *,
    delivery: str,
    repeatable: bool,
    unit: AbilityUnit | None = None,
    root: object = None,
    cnode: ConceptNode | None = None,
) -> DeathLink | None:
    """The death link one instruction makes, if any. ``cnode`` is the tree's own
    reading of the node: its subject and scope stand in where the filter is a
    back-reference ("it") the filter read can't place, and an overlay stage's
    corrected scope (``reads.corrected_scope``) anywhere; ``root`` is the
    ability whose wrappers name who acts and who decides."""
    tag = tag_of(node) or ""
    if tag not in EFFECT_ROUTES:
        return None
    route, reach = EFFECT_ROUTES[tag]
    if route == "shrink" and not _shrinks(tag, node):
        return None
    if route == "move" and not (
        getattr(node, "origin", None) == "Battlefield"
        and getattr(node, "destination", None) == "Graveyard"
    ):
        return None
    target = getattr(node, "sacrifice_filter", None) or getattr(node, "target", None)
    if tag == "ChooseAndSacrificeRest":
        hit: bool | None = "Creature" in list_field(node, "categories")
    else:
        hit = filter_can_name_creature(
            target, self_is_creature=tree.is_type("Creature")
        )
    side = cnode.scope if cnode is not None else ""
    if hit is None:  # a back-reference, or a filter phase left empty
        hit = cnode is not None and "Creature" in cnode.subject
    elif cnode is not None:
        # The filter names the object; the substrate's scope for one with no
        # controller is a default, not a reading ("target legendary permanent").
        side = corrected_scope(cnode) or ""
    if not hit:
        return None
    if reach == "one" and acts_on_a_group(node, unit):
        reach = "all"
    if tag_of(target) == "SelfRef":
        whose = "self"
    elif route == "sacrifice":
        whose = "yours" if role == "cost" else sacrificing_side(unit, node)
    elif route == "fight":
        whose = "either"  # both creatures are dealt damage (CR 701.14a)
    else:
        whose = _side(filter_controller(target, unit), "") or _side(side, "either")
    decided = (
        role == "effect" and root is not None and effect_decided_by_another(root, node)
    )
    return _death_link(
        tree,
        route,
        whose=whose,
        reach=reach,
        role=role,
        delivery=delivery,
        repeatable=repeatable,
        verb=tag,
        certain=not decided,
    )


def _recovered_link(
    tree: ConceptTree,
    cnode: ConceptNode,
    role: str,
    *,
    delivery: str,
    repeatable: bool,
) -> DeathLink | None:
    """The link of a node phase left unparsed (``Unimplemented``), read off the
    recovery stage's concept, subject and scope for it."""
    if "Creature" not in cnode.subject:
        return None
    return _death_link(
        tree,
        RECOVERED_ROUTES[cnode.concept],
        whose=_side(cnode.scope, "either"),
        reach="all" if "Mass" in cnode.subject else "one",
        role=role,
        delivery=delivery,
        repeatable=repeatable,
        verb="Unimplemented",
    )


def _static_links(tree: ConceptTree, unit: AbilityUnit) -> Iterator[DeathLink]:
    """The links a static ability makes: a toughness reduction it applies (CR
    704.5f), and the abilities it grants ("... has '{T}: Destroy target black
    creature.'" — CR 113.1a: "Abilities can also be granted to objects by rules
    or effects")."""
    if unit.origin != "static":
        return
    for sdef in iter_static_defs(unit.node):
        affected = static_affected(sdef, unit)
        for mod in list_field(sdef, "modifications"):
            value = getattr(mod, "value", None)
            if (
                tag_of(mod) == "AddToughness"
                and isinstance(value, int)
                and value < 0
                and filter_can_name_creature(
                    affected, self_is_creature=tree.is_type("Creature")
                )
            ):
                yield _static_shrink(tree, affected, unit)
            definition = getattr(mod, "definition", None)
            if isinstance(definition, TypedMirrorNode):
                yield from _granted_links(tree, definition)


def _static_shrink(tree: ConceptTree, affected: object, unit: AbilityUnit) -> DeathLink:
    """A static toughness reduction's link: on the card itself, on the one
    creature an Aura or Equipment is attached to (:func:`_host_side`), or on
    every creature its filter names."""
    is_self = tag_of(affected) == "SelfRef"
    one = is_self or bool(_ATTACHED_HOST_PREDICATES & set(filter_predicates(affected)))
    if is_self:
        whose = "self"
    else:
        whose = (one and _host_side(tree, affected)) or _side(
            filter_controller(affected, unit), "either"
        )
    return _death_link(
        tree,
        "shrink",
        whose=whose,
        reach="one" if one else "all",
        role="static",
        delivery="static",
        repeatable=True,
        verb="AddToughness",
    )


def _granted_links(
    tree: ConceptTree, definition: TypedMirrorNode
) -> Iterator[DeathLink]:
    """The links of an ability a static grants: its first effect and its cost."""
    kind = getattr(definition, "kind", None)
    kind = kind if isinstance(kind, str) else "ability"
    again = kind == "Activated"
    how = f"granted:{kind.lower()}"
    effect = getattr(definition, "effect", None)
    if isinstance(effect, TypedMirrorNode):
        link = _link(
            tree, effect, "effect", delivery=how, repeatable=again, root=definition
        )
        if link:
            yield link
    for leaf in iter_cost_leaves(getattr(definition, "cost", None)):
        link = _link(tree, leaf, "cost", delivery=how, repeatable=again)
        if link:
            yield link


def death_links(tree: ConceptTree) -> list[DeathLink]:
    """Every way the card's own text can make a creature die (CR 700.4). A
    link repeats when its ability can go off again while the card stays on the
    battlefield (``reads.unit_repeats``, an "enters or attacks" trigger firing
    on each attack)."""
    links: list[DeathLink] = []
    for unit in tree.units:
        delivery = _delivery(unit, tree)
        repeatable = unit_repeats(unit, tree, attacks_again=True)
        for role, nodes in (("effect", unit.effects), ("cost", unit.costs)):
            for cnode, node in _instructions(nodes):
                recovered = cnode.concept in RECOVERED_ROUTES
                if recovered and tag_of(node) == "Unimplemented":
                    # phase could not parse it; the recovery stage's reading
                    # stands in
                    link = _recovered_link(
                        tree, cnode, role, delivery=delivery, repeatable=repeatable
                    )
                else:
                    link = _link(
                        tree,
                        node,
                        role,
                        delivery=delivery,
                        repeatable=repeatable,
                        unit=unit,
                        root=unit.node,
                        cnode=cnode,
                    )
                if link:
                    links.append(link)
        links.extend(_static_links(tree, unit))
    for keyword in tree.card_keywords:
        if keyword in KEYWORD_SACRIFICES:
            rule, whose, how, again = KEYWORD_SACRIFICES[keyword]
            links.append(
                _death_link(
                    tree,
                    "sacrifice",
                    rule=f"{rule} + 701.21a + 700.4",
                    whose=whose,
                    reach="one",
                    role="cost" if how == "cost" else "effect",
                    delivery=how,
                    repeatable=again,
                    verb=keyword,
                )
            )
    return links


def unit_death_waits(tree: ConceptTree, unit: AbilityUnit) -> list[DeathWait]:
    """The waits of one trigger of the card: a creature dying, or a sacrifice
    (``sacrificed`` / ``exploited``, which a sacrifice alone feeds). A sacrifice
    wait is kept whatever it watches ("Whenever you sacrifice a permanent"):
    its ``types`` say what that is. Empty for any other unit."""
    if unit.origin != "trigger":
        return []
    trig = unit.node
    event = unit.trigger_event or ""
    clauses = list_field(trig, "zone_change_clauses")
    # One clause of several can watch a death (Syr Konrad, the Grim).
    dying = [
        getattr(clause, "valid_card", None)
        for clause, move in zip(clauses, trigger_zone_changes(trig), strict=False)
        if move == _DIES
    ]
    if dying:
        valids, event = dying, "dies"
    elif (
        event == "dies"
        or (
            getattr(trig, "origin", None),
            getattr(trig, "destination", None),
        )
        == _DIES
    ):
        valids, event = [getattr(trig, "valid_card", None)], "dies"
    elif event in ("sacrificed", "exploited"):
        valids = [getattr(trig, "valid_card", None)]
    else:
        return []
    waits: list[DeathWait] = []
    for valid in valids:
        if (
            event != "sacrificed"
            and filter_can_name_creature(
                valid, self_is_creature=tree.is_type("Creature")
            )
            is False
        ):
            continue
        waits.append(
            DeathWait(
                tree.name,
                event,
                *_wait_scope(tree, valid, unit),
                subtypes=filter_subtypes(valid),
                tokens=_watches_tokens(valid),
            )
        )
    return waits


def death_waits(tree: ConceptTree) -> list[DeathWait]:
    """Every trigger of the card that waits for a creature dying, or for a
    sacrifice (:func:`unit_death_waits`)."""
    return [wait for unit in tree.units for wait in unit_death_waits(tree, unit)]


def _watches_tokens(valid: object) -> bool | None:
    """``True`` when every part of the watched filter names only tokens, ``False``
    when every part names only nontokens, else ``None`` (the card itself, the
    creature an Aura or Equipment is on, a filter that says neither)."""
    if tag_of(valid) not in ("Typed", "Or", "And"):
        return None
    parts = list_field(valid, "filters") if tag_of(valid) in ("Or", "And") else [valid]
    marks = {
        ("Token" in preds) - ("NonToken" in preds)
        for part in parts
        for preds in (set(filter_predicates(part)),)
    }
    if marks == {1}:
        return True
    return False if marks == {-1} else None


def _wait_scope(
    tree: ConceptTree, valid: object, unit: AbilityUnit
) -> tuple[str, bool, tuple[str, ...]]:
    """Whose creature a wait watches, whether it says "another", and the core
    types it names."""
    tag = tag_of(valid)
    if tag is None:
        return "any", False, ()
    if tag == "SelfRef":
        return "self", False, ()
    if tag == "AttachedTo":  # the creature this Aura or Equipment is on
        return _host_side(tree, valid) or "any", False, ("Creature",)
    parts = list_field(valid, "filters") if tag in ("Or", "And") else [valid]
    whose: set[str] = set()
    another = False
    types: list[str] = []
    for part in parts:
        if not isinstance(part, TypedMirrorNode):
            continue
        if tag_of(part) == "SelfRef":
            whose.add("self")
            continue
        whose.add(_side(filter_controller(part, unit), "any"))
        another |= "Another" in filter_predicates(part)
        types += filter_core_types(part)
    wide = whose - {"self"}
    if "any" in wide or len(wide) > 1:
        return "any", another, tuple(dict.fromkeys(types))
    return (wide.pop() if wide else "self"), another, tuple(dict.fromkeys(types))


def feeds(link: DeathLink, wait: DeathWait) -> bool:
    """Can this link make the creature that wait watches die? ``yours`` /
    ``theirs`` are read from one player's seat: the card with the link and the
    card with the wait are in the same deck."""
    if wait.event in ("sacrificed", "exploited") and link.route != "sacrifice":
        # A sacrifice is its own act, its controller moving the permanent (CR
        # 701.21a); destruction comes only from a "destroy" effect or the
        # lethal-damage and deathtouch state-based actions (CR 701.8b).
        return False
    if wait.whose == "any":
        return True
    if wait.whose in ("self", "yours"):  # one of your own has to die
        return link.whose in ("yours", "either", "self") and (
            wait.whose == "yours" or link.whose != "self"
        )
    return link.whose in ("theirs", "either")


@card_read("death_links")
def card_death_links(card: dict) -> tuple[DeathLink, ...]:
    """:func:`death_links` over every face's tree of ``card``."""
    return tuple(link for tree in trees_for(dict(card)) for link in death_links(tree))


@card_read("death_waits")
def card_death_waits(card: dict) -> tuple[DeathWait, ...]:
    """:func:`death_waits` over every face's tree of ``card``."""
    return tuple(wait for tree in trees_for(dict(card)) for wait in death_waits(tree))
