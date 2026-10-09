"""Board protection reads (``roles.protects``, ADR-0051).

What protects YOUR board or you: a protective keyword given to something other
than the card itself (:func:`protective_grant_recipients`), a save for
something other than the card itself (:func:`protective_saves`), and attack
deterrents (:func:`attack_deterrent`). A permanent that protects only itself
(Dragonlord Ojutai's hexproof, Thrun's regeneration) protects nothing else on
your board.

Most of the module resolves WHO an effect protects: ``affected`` / ``target``
filters, the back-references phase leaves (``ParentTarget``, ``TrackedSet``,
``TriggeringSource``), and the "this" inside a granted ability. One of those
resolutions reads past a phase misbinding and is canary-guarded rather than
corrected where the tree is built: a spell's ``SelfRef`` (the read's own
decision — ``test_spell_selfref_misbinding_canary``). (An Aura's enters trigger
aimed at its ``TriggeringSource`` was the other until phase v0.104.0, which
parks Maze's Mantle's grant as a residue instead.) The overlay-correction stage
can't own it: it decorates the concept overlay (``scope`` / ``subject`` /
``zones``) and never rewrites a Layer-1 mirror node (the substrate-purity
invariant), while the misbinding lives in a mirror field (a nested static's
``affected``) these reads walk directly. A prevention phase parks by shape is
read off the residue's name (``reads.PARKED_PREVENTION_RESIDUES``).

Pure readers over the typed substrate, like ``reads``: nothing here constructs
a concept tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Literal

from mtg_utils._card_ir.crosswalk.reads import (
    _GRANTED_ABILITY_TAGS,
    _GRANTED_TRIGGER_TAGS,
    _OPPONENT_ACTOR_TAGS,
    _present,
    _variant_field,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    is_spell_card,
    iter_mod_sites,
    iter_typed_nodes,
    normalised_keyword,
    parked_prevention,
    protective_keyword,
    static_mode_field,
    static_mode_tag,
    tag_of,
    unit_keyword_grants,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk.core import AbilityUnit, ConceptTree

#: A player's own protective static modes: "You have hexproof" (Leyline of
#: Sanctity, CR 702.11c), "You have shroud" (True Believer, 702.18a), "you have
#: protection from …" (Runed Halo, 702.16b).
_PLAYER_PROTECTION_MODES: dict[str, str] = {
    "Hexproof": "hexproof",
    "Shroud": "shroud",
    "PlayerProtection": "protection",
}
#: Filter controllers that make a recipient someone else's — the opponent actor
#: tags plus a targeted opponent: a protective effect aimed only at an
#: opponent's object is not protecting your board.
_HOSTILE_CONTROLLERS: frozenset[str] = _OPPONENT_ACTOR_TAGS | {"TargetOpponent"}
#: Recipient tags naming you, or you and your permanents.
_PLAYER_RECIPIENT_TAGS: frozenset[str] = frozenset(
    {"Controller", "Player", "ControllerAndControlledPermanents"}
)
#: Recipient tags naming some other object: "any target" (Samite Healer), the
#: enchanted / equipped permanent, a soulbond pair (CR 702.95a).
_OTHER_OBJECT_TAGS: frozenset[str] = frozenset({"Any", "AttachedTo", "SourceOrPaired"})
_CHOSEN_TARGET_TAGS: frozenset[str] = frozenset({"Typed", "Or", "And"})
#: The modifications that give a permanent an ability of its own.
_GRANT_TAGS: frozenset[str] = (
    _GRANTED_TRIGGER_TAGS | _GRANTED_ABILITY_TAGS | {"GrantReplacement"}
)
#: Umbra armor (CR 702.89a; "totem armor" on older printings, 702.89b): on an
#: Aura it shields the enchanted permanent, not the Aura.
_UMBRA_ARMOR_KEYWORDS: frozenset[str] = frozenset({"umbraarmor", "totemarmor"})

ProtectionRecipient = Literal["player", "permanent"]


# ── Who a filter names ──────────────────────────────────────────────────────────


def _filter_recipient(tree: ConceptTree, filt: object) -> ProtectionRecipient | None:
    """What a protective effect's recipient filter names: you (``"player"``),
    some permanent other than the card itself (``"permanent"``), or ``None`` —
    the card itself, only an opponent's objects, or a shape this read doesn't
    know.

    ``SelfRef`` on an instant or sorcery is phase binding the spell's "it" /
    "those creatures" to the card (Blizzard Brawl's "the creature you control …
    gains indestructible", Promise of Loyalty's "each of those creatures can't
    attack you"). A spell grants nothing lasting to itself, so this read takes
    the effect to mean the object the spell chose — the read's own decision, not
    a rule. Guarded by ``test_spell_selfref_misbinding_canary``."""
    tag = tag_of(filt)
    if tag == "SelfRef":
        return "permanent" if is_spell_card(tree) else None
    if tag in _PLAYER_RECIPIENT_TAGS:
        return "player"
    if tag in _OTHER_OBJECT_TAGS:
        return "permanent"
    if tag not in _CHOSEN_TARGET_TAGS:
        return None
    if filter_controller(filt) in _HOSTILE_CONTROLLERS:
        return None
    if (
        tag == "Typed"
        and filter_controller(filt) == "You"
        and not getattr(filt, "type_filters", None)
        and not filter_predicates(filt)
    ):
        return "player"  # "You have hexproof": a typed filter naming only you
    return "permanent"


_EFFECT_TARGETS_CACHE_ATTR = "_xw_effect_targets"


def _effect_targets(root: object) -> tuple[object, ...]:
    """The ``target`` filters of the effects under ``root``, skipping its costs
    (Mossbridge Troll taps other creatures to pay; it chooses none of them).
    Memoized per root node, like ``reads.iter_mod_sites``."""
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_EFFECT_TARGETS_CACHE_ATTR)
        if cached is not None:
            return cached
    in_cost: set[int] = set()
    nodes = list(iter_typed_nodes(root))
    for n in nodes:
        cost = getattr(n, "cost", MISSING)
        if isinstance(cost, TypedMirrorNode):
            in_cost.update(id(c) for c in iter_typed_nodes(cost))
    out = tuple(
        sub
        for n in nodes
        if id(n) not in in_cost and _present(sub := getattr(n, "target", MISSING))
    )
    if isinstance(root, TypedMirrorNode):
        object.__setattr__(root, _EFFECT_TARGETS_CACHE_ATTR, out)
    return out


def _chooses_other_object(root: object) -> bool:
    """Whether the effects under ``root`` choose an object other than the card:
    a typed target no opponent owns, or the enchanted permanent."""
    return any(
        tag_of(t) == "AttachedTo"
        or (
            tag_of(t) in _CHOSEN_TARGET_TAGS
            and filter_controller(t) not in _HOSTILE_CONTROLLERS
        )
        for t in _effect_targets(root)
    )


def _puts_onto_battlefield(root: object) -> bool:
    """Whether the effects under ``root`` put some other card onto the
    battlefield (a ``ChangeZone`` to the battlefield whose object isn't the
    card itself)."""
    return any(
        tag_of(n) == "ChangeZone"
        and getattr(n, "destination", None) == "Battlefield"
        and tag_of(getattr(n, "target", None)) != "SelfRef"
        for n in iter_typed_nodes(root)
    )


def _back_reference_recipient(
    tree: ConceptTree, unit: AbilityUnit
) -> ProtectionRecipient | None:
    """Who an unresolved ``ParentTarget`` ("it", "that creature", "those
    creatures") names when the threaded walks can't follow it: the object the
    unit itself chooses ("Another target creature you control gains protection
    from colorless or from the color of your choice" — Giver of Runes'
    ``ChooseOneOf`` branches) or puts onto the battlefield (Doors of Durin: "put
    it onto the battlefield tapped and attacking. Until your next turn, it gains
    … hexproof"); for a replacement, the permanent it
    watches (the enchanted land Crackling Emergence saves; Mossbridge Troll's own
    "regenerate it" watches itself); for a trigger on the card itself with no
    target of its own, the card ("Whenever ~ attacks … it gains indestructible"
    — Estwald Shieldbasher); else what another of the card's abilities chooses
    (Break of Day's fateful-hour "those creatures", Efflorescence's infusion
    "that creature")."""
    if _chooses_other_object(unit.node) or _puts_onto_battlefield(unit.node):
        return "permanent"
    if unit.origin in ("replacement", "trigger"):
        watched = getattr(unit.node, "valid_card", MISSING)
        if tag_of(watched) == "AttachedTo":
            return "permanent"
        if tag_of(watched) == "SelfRef":
            return None
    if any(_chooses_other_object(u.node) for u in tree.units if u is not unit):
        return "permanent"
    return None


def _triggering_recipient(
    tree: ConceptTree, unit: AbilityUnit
) -> ProtectionRecipient | None:
    """The object a trigger's "it" names: the permanent the trigger watches
    ("Whenever another creature you control attacks, it gains … indestructible"
    — Stonehoof Chieftain), never a spell (a cast trigger's "it" is the card
    itself — Pristine Skywise) and never the card itself."""
    if unit.origin != "trigger" or getattr(unit.node, "mode", None) == "SpellCast":
        return None
    watched = getattr(unit.node, "valid_card", MISSING)
    if not _present(watched) or tag_of(watched) not in _CHOSEN_TARGET_TAGS:
        return None
    return _filter_recipient(tree, watched)


def _recipient(
    tree: ConceptTree,
    unit: AbilityUnit,
    filt: object,
    resolved: object | None = None,
) -> ProtectionRecipient | None:
    """Who an effect's recipient (an ``affected`` or a ``target``) names,
    resolving the back-references: ``ParentTarget`` / ``TrackedSet`` through the
    threaded target ``resolved`` or :func:`_back_reference_recipient`,
    ``TriggeringSource`` / ``EventTarget`` through the trigger
    (:func:`_triggering_recipient`)."""
    tag = tag_of(filt)
    if tag in ("ParentTarget", "TrackedSet"):
        if resolved is not None:
            return _filter_recipient(tree, resolved)
        return _back_reference_recipient(tree, unit)
    if tag in ("TriggeringSource", "EventTarget"):
        return _triggering_recipient(tree, unit)
    return _filter_recipient(tree, filt)


# ── Per-unit context: tokens and granted abilities ──────────────────────────────


def _token_nodes(root: object) -> tuple[set[int], set[int]]:
    """The ids of the nodes inside a ``Token`` effect's definition, and the
    subset inside an AURA token. A created token's own abilities protect the
    token (Skeletonize's Skeleton, "{B}: Regenerate this creature") — its
    self-protection, not the card's — except an Aura token's umbra armor, which
    shields the permanent it's attached to (Estrid, the Masked's Mask)."""
    inside: set[int] = set()
    inside_aura: set[int] = set()
    for n in iter_typed_nodes(root):
        if tag_of(n) != "Token":
            continue
        ids = {id(m) for m in iter_typed_nodes(n) if m is not n}
        inside |= ids
        if "Aura" in (getattr(n, "types", None) or ()):
            inside_aura |= ids
    return inside, inside_aura


def _granted_recipients(
    tree: ConceptTree, unit: AbilityUnit
) -> dict[int, ProtectionRecipient | None]:
    """``id(node) -> recipient`` for every node inside a granted ability ("Other
    Zombie creatures have '{B}: Regenerate this permanent'" — Zombie Master;
    "Equipped creature … has 'This creature has hexproof as long as it's
    untapped'" — Giant's Amulet): a granted ability's "this" is the permanent
    it is granted to, so its recipient is the granting effect's ``affected`` (the
    read's own decision)."""
    out: dict[int, ProtectionRecipient | None] = {}
    for sdef, mod in iter_mod_sites(unit.node, deep=True):
        if tag_of(mod) not in _GRANT_TAGS or not _present(
            getattr(sdef, "affected", MISSING)
        ):
            continue
        who = _recipient(tree, unit, getattr(sdef, "affected", None))
        for inner in iter_typed_nodes(mod):
            out.setdefault(id(inner), who)
    return out


def _self_or_granted(
    tree: ConceptTree,
    unit: AbilityUnit,
    node: TypedMirrorNode,
    filt: object,
    granted: dict[int, ProtectionRecipient | None],
    resolved: object | None = None,
) -> ProtectionRecipient | None:
    """:func:`_recipient`, except that "itself" inside a granted ability is the
    permanent the ability is granted to (:func:`_granted_recipients`)."""
    if tag_of(filt) == "SelfRef" and id(node) in granted:
        return granted[id(node)]
    return _recipient(tree, unit, filt, resolved)


# ── Protective keyword grants ───────────────────────────────────────────────────


def _umbra_armored_aura(sdef: object, mod: object, *, aura: bool) -> bool:
    """Whether ``mod`` gives umbra armor to an Aura — the def's own object when
    ``aura`` says that object is an Aura (Dog Umbra's "Otherwise, this Aura has
    umbra armor"; Estrid's Mask token), or your Auras. Umbra armor shields the
    ENCHANTED permanent (CR 702.89a: "If enchanted permanent would be destroyed,
    instead … destroy this Aura")."""
    if normalised_keyword(mod) not in _UMBRA_ARMOR_KEYWORDS:
        return False
    affected = getattr(sdef, "affected", None)
    if tag_of(affected) == "SelfRef":
        return aura
    return "Aura" in filter_subtypes(affected) and (
        filter_controller(affected) not in _HOSTILE_CONTROLLERS
    )


def _animates(sdef: object, recipient: object) -> bool:
    """Whether a static def turns its object into a creature (Avalanche Caller's
    "Target snow land you control becomes a 4/4 Elemental creature with hexproof
    and haste"; Sylvan Awakening; Sparkshaper Visionary's planeswalkers) or
    rewrites its card types outright (Darksteel Mutation's "is an Insect artifact
    creature … has indestructible, and loses all other abilities"). A protective
    keyword in the same def is part of the object it makes, not a shield for an
    existing permanent of yours — the read's own decision. Adding the Creature
    type to a creature (Secret Identity's "target creature you control becomes a
    Citizen … and gains hexproof") animates nothing; ``recipient`` is the
    resolved filter the def affects."""
    for mod in getattr(sdef, "modifications", None) or ():
        if tag_of(mod) == "SetCardTypes" and "Creature" in (
            getattr(mod, "core_types", None) or ()
        ):
            return True
        if (
            tag_of(mod) == "AddType"
            and getattr(mod, "core_type", None) == "Creature"
            and "Creature" not in filter_core_types(recipient)
        ):
            return True
    return False


def protective_grant_recipients(
    tree: ConceptTree,
) -> Iterator[tuple[str, ProtectionRecipient]]:
    """``(keyword, recipient)`` for every protective keyword the card gives to
    something other than itself (``reads.PROTECTIVE_KEYWORDS``, plus umbra armor
    on an Aura): a static grant ("Other permanents you control have
    indestructible" — Avacyn; "Artifacts you control have indestructible" —
    Darksteel Forge; "Equipped creature has hexproof" — Swiftfoot Boots), a
    one-shot grant to a target or your team (Tamiyo's Safekeeping, Apostle's
    Blessing's chosen branch, Heroic Intervention), and a player's own
    protective mode ("You have hexproof" — Leyline of Sanctity; Teferi's
    Protection's "you gain protection from everything"). The recipient is
    ``"player"`` (you) or ``"permanent"``. Lazy: ``next()`` on it is the
    existence test the ``board_protection`` lane makes; the pairs are what the
    tests pin.

    Dropped: a grant to the card itself ("~ has hexproof as long as it's
    untapped" — Dragonlord Ojutai; "Sacrifice another creature: ~ gains
    indestructible" — Yahenni), a grant only an opponent's objects take, and a
    keyword that comes with animating the object (:func:`_animates`)."""
    card_is_aura = "Aura" in tree.card_subtypes
    for unit in tree.units:
        threaded: dict[int, object] = {}
        for tgt, mod in unit_keyword_grants(unit):
            threaded.setdefault(id(mod), tgt)
        granted = _granted_recipients(tree, unit)
        in_token, in_aura_token = _token_nodes(unit.node)
        for n in iter_typed_nodes(unit.node):
            mode = static_mode_tag(n)
            if (
                mode in _PLAYER_PROTECTION_MODES
                and id(n) not in in_token
                and _filter_recipient(tree, getattr(n, "affected", None)) == "player"
            ):
                yield _PLAYER_PROTECTION_MODES[mode], "player"
        for sdef, mod in iter_mod_sites(unit.node, deep=True):
            affected = getattr(sdef, "affected", MISSING)
            if not _present(affected):
                continue
            aura = id(sdef) in in_aura_token or (
                card_is_aura and id(sdef) not in in_token
            )
            if _umbra_armored_aura(sdef, mod, aura=aura):
                yield "umbra armor", "permanent"
                continue
            kw = protective_keyword(mod)
            if kw is None or id(sdef) in in_token:
                continue
            resolved = threaded.get(id(mod))
            if _animates(sdef, resolved if resolved is not None else affected):
                continue
            who = _self_or_granted(tree, unit, sdef, affected, granted, resolved)
            if who is not None:
                yield kw, who


# ── Saves ───────────────────────────────────────────────────────────────────────

#: The save effects (CR 701.19a regeneration, 702.26b phasing out, 615.1
#: prevention) by their typed tag.
_SAVE_TAGS: dict[str, str] = {
    "Regenerate": "regenerate",
    "PhaseOut": "phase_out",
    "PreventDamage": "prevent_damage",
}


def _symmetric_static_shield(node: TypedMirrorNode, *, static: bool) -> bool:
    """Whether a permanent's own prevention shield covers every player's objects
    alike: mandatory, watching no object, and naming every player or no
    recipient at all (Crumbling Sanctuary's "If damage would be dealt to a
    player, that player exiles that many cards … instead" — its ruling: "The
    ability affects all players"; Plated Pegasus's "If a spell would deal damage
    to a permanent or player, prevent 1 damage"). Protection is protecting YOUR
    board (Dan, 2026-10-08), so such a shield isn't — the read's own decision. A
    one-shot fog a spell or ability creates (Fog, Undergrowth) is timed by you,
    so it stays; so does an optional shield you aim ("you may prevent" —
    Battletide Alchemist)."""
    if not static or tag_of(getattr(node, "mode", None)) != "Mandatory":
        return False
    if _present(getattr(node, "valid_card", MISSING)):
        return False
    source = getattr(node, "damage_source_filter", MISSING)
    if _present(source) and (
        tag_of(source) == "AttachedTo"
        or filter_controller(source) in (*_HOSTILE_CONTROLLERS, "You")
    ):
        return False
    damaged = getattr(node, "damage_target_filter", MISSING)
    if not isinstance(damaged, MirrorVariant):
        # No recipient named: symmetric only when a class of SOURCES defines the
        # shield ("damage that spells would deal" — Plated Pegasus, Energy
        # Storm). With neither, phase dropped the recipient ("If damage would be
        # dealt to you" — Delaying Shield, Nefarious Lich), so it isn't read as
        # symmetric.
        return not _present(damaged) and _present(source)
    return damaged.key == "Player" and tag_of(
        _variant_field(damaged.inner, "player")
    ) in ("Any", "AllPlayers")


def _prevention_shield_recipient(
    tree: ConceptTree, node: TypedMirrorNode, *, static: bool = False
) -> ProtectionRecipient | None:
    """Who a damage-prevention REPLACEMENT shields (CR 615.1: prevention effects
    "act like shields around whatever they're affecting"), or ``None``: a shield
    around the card itself ("Prevent all damage that would be dealt to ~" —
    Cho-Manno; "dealt to and dealt by ~" — Fog Bank); a shield defined only by
    the enchanted creature's damage ("Prevent all damage that would be dealt by
    enchanted creature" — Temporal Isolation, a pacifying Aura whose static
    ability's continuous effect, CR 611.3, neutralises that creature rather than
    protecting yours); a prevention of damage to an opponent (Hostility turns
    its spells' damage into tokens); or a shield over every player's objects
    alike (:func:`_symmetric_static_shield`). ``static`` says ``node`` is the
    card's own replacement ability; it may instead be one the card creates
    (Ajani Steadfast's emblem, a fog spell)."""
    shield = getattr(node, "shield_kind", MISSING)
    minus = getattr(node, "damage_modification", MISSING)
    is_prevention = (
        isinstance(shield, MirrorVariant) and shield.key == "Prevention"
    ) or (_present(minus) and tag_of(minus) == "PreventionMinus")
    if not is_prevention or _symmetric_static_shield(node, static=static):
        return None
    watched = getattr(node, "valid_card", MISSING)
    source = getattr(node, "damage_source_filter", MISSING)
    if tag_of(watched) == "SelfRef" or tag_of(source) == "SelfRef":
        return None
    damaged = getattr(node, "damage_target_filter", MISSING)
    if isinstance(damaged, MirrorVariant):
        player = _variant_field(damaged.inner, "player")
        if tag_of(player) in _HOSTILE_CONTROLLERS:
            return None
    if _present(watched):
        return _filter_recipient(tree, watched)
    if tag_of(source) == "AttachedTo":
        return None
    return "player" if not _present(source) else "permanent"


def _returning_death_shield(node: TypedMirrorNode) -> bool:
    """A replacement (CR 614.1a) that keeps your permanents out of the graveyard
    and returns them to the battlefield — Cosmic Intervention's "If a permanent
    you control would be put into a graveyard from the battlefield this turn,
    exile it instead. Return it to the battlefield …" (its rulings: each exiled
    permanent "creates its own triggered ability to return itself"). A
    graveyard-hate exile with no return (Leyline of the Void, Void Maw) is not a
    save."""
    if getattr(node, "event", None) != "Moved":
        return False
    if getattr(node, "destination_zone", None) != "Graveyard":
        return False
    watched = getattr(node, "valid_card", MISSING)
    if tag_of(watched) not in _CHOSEN_TARGET_TAGS or filter_controller(watched) != (
        "You"
    ):
        return False
    return any(
        tag_of(n) == "ChangeZone" and getattr(n, "destination", None) == "Battlefield"
        for n in iter_typed_nodes(node)
    )


def _life_floor_for_you(node: TypedMirrorNode) -> bool:
    """A replacement that keeps damage from taking your life below 1 — Angel's
    Grace's and Angel of Grace's "damage that would reduce your life total to
    less than 1 reduces it to 1 instead" (a replacement, CR 614.1a; their
    rulings: it "doesn't prevent damage. It only changes the result of damage
    dealt to you")."""
    modification = getattr(node, "damage_modification", MISSING)
    if tag_of(modification) != "LifeFloor":
        return False
    damaged = getattr(node, "damage_target_filter", MISSING)
    return isinstance(damaged, MirrorVariant) and (
        tag_of(_variant_field(damaged.inner, "player")) == "Controller"
    )


def _hostile_damage_source(node: TypedMirrorNode) -> bool:
    """Whether a prevention names the damage an OPPONENT's object would deal
    (Dovin, Hand of Control's and Kiora, the Crashing Wave's "prevent all damage
    that would be dealt … by target permanent an opponent controls"): a shield
    for you and your permanents against it."""
    source = getattr(node, "damage_source_filter", MISSING)
    return _present(source) and filter_controller(source) in _HOSTILE_CONTROLLERS


def _held_phased_out(root: object) -> bool:
    """Whether a unit keeps what it phases out from phasing in ("until ~ leaves
    the battlefield" — Oubliette, its ruling: it "doesn't phase in during its
    controller's untap step as normal", where CR 702.26a would phase it in)."""
    return any(static_mode_tag(n) == "CantPhaseIn" for n in iter_typed_nodes(root))


def protective_saves(tree: ConceptTree) -> Iterator[tuple[str, ProtectionRecipient]]:
    """``(kind, recipient)`` for every save the card performs or grants for
    something other than itself: ``"regenerate"`` (CR 701.19a — Regenerate,
    Golgari Charm, Zombie Master's granted regeneration), ``"phase_out"``
    (702.26b — Teferi's Protection, Clever Concealment), ``"prevent_damage"``
    (615.1 — Fog, Samite Healer, Circle of Protection: Red, Security Blockade's
    granted shield, Urza's Armor), ``"life_floor"`` (Angel's Grace,
    :func:`_life_floor_for_you`) and ``"return"`` (a death replacement that
    returns your permanents — Cosmic Intervention). Lazy, like
    :func:`protective_grant_recipients`. A stack redirect (CR 115.7 — Reroute)
    is the ``spell_redirect`` lane's (``reads.redirects_stack_object``).

    Defensive neutralisers count, removal doesn't. Damage prevention scoped to
    the damage an opponent's object would deal shields you and your board, like
    a fog or a pillowfort (CR 615.1 — Dovin, Hand of Control; Kiora, the Crashing
    Wave; Resistance Fighter's "Prevent all combat damage target creature would
    deal", whose target phase records as the prevention's object). Phasing out
    or exiling an opponent's object is removal: a phase-out aimed only at an
    opponent's object (Sapphire Charm), or one held by "can't phase in" until
    the source leaves (Oubliette, :func:`_held_phased_out`), is not a save. Nor
    is a permanent's shield over every player's objects alike
    (:func:`_symmetric_static_shield` — Crumbling Sanctuary, Plated Pegasus).

    Dropped too: a save of the card itself ("{1}{G}: Regenerate ~" — Thrun, the
    Last Troll; Frenetic Efreet's coin-flip phase-out), and a pacifying
    prevention (:func:`_prevention_shield_recipient`)."""
    for unit in tree.units:
        granted = _granted_recipients(tree, unit)
        in_token, _ = _token_nodes(unit.node)
        held: bool | None = None
        for n in iter_typed_nodes(unit.node):
            if id(n) in in_token:
                continue
            static = (
                n is unit.node
                and unit.origin == "replacement"
                and not is_spell_card(tree)  # Undergrowth: a fog spell's shield
            )
            who = _prevention_shield_recipient(tree, n, static=static)
            if who is not None:
                yield "prevent_damage", who
            parked = parked_prevention(n)
            if parked is not None:
                # Read off the residue's name (reads.PARKED_PREVENTION_RESIDUES):
                # a two-way shield names an opponent's permanent (Dovin, Kiora),
                # the source-role preventions neutralise an attacker or blocker.
                both = parked == "bidirectional_prevent_declared_target"
                yield "prevent_damage", "player" if both else "permanent"
            if _life_floor_for_you(n):
                yield "life_floor", "player"
            if _returning_death_shield(n):
                yield "return", "permanent"
            kind = _SAVE_TAGS.get(tag_of(n) or "")
            target = getattr(n, "target", MISSING)
            if kind is None or not _present(target):
                continue
            if kind == "phase_out":
                if held is None:
                    held = _held_phased_out(unit.node)
                if held:
                    continue  # held phased out: removal (Oubliette), not a save
            if kind == "prevent_damage" and _hostile_damage_source(n):
                yield kind, "player"
                continue
            who = _self_or_granted(tree, unit, n, target, granted)
            if who is not None:
                yield kind, who


# ── Attack deterrents ───────────────────────────────────────────────────────────

AttackDeterrentKind = Literal["attack_tax", "attack_ban", "attack_limit"]
#: Who "can't attack" defends when it names you: you, you and your
#: planeswalkers, or you and your permanents.
_DEFENDED_YOU: frozenset[str] = frozenset(
    {"Player", "PlayerOrPlaneswalker", "PlayerOrPermanents"}
)


def _taxes_attacks_on_you(cond: object) -> bool:
    """Whether an attack restriction's condition is "unless their controller
    pays" for attacking you, alone or beside another condition (Archangel of
    Tithes' "as long as this creature is untapped")."""
    if tag_of(cond) == "UnlessPay":
        return getattr(cond, "defended", None) in _DEFENDED_YOU
    if tag_of(cond) == "And":
        return any(
            _taxes_attacks_on_you(c) for c in getattr(cond, "conditions", None) or ()
        )
    return False


def attack_deterrent(tree: ConceptTree) -> AttackDeterrentKind | None:
    """How the card keeps creatures from attacking you (pillowfort), or ``None``:

    * ``"attack_tax"`` — creatures can't attack you unless their controller pays
      (Ghostly Prison, Propaganda, Sphere of Safety, Norn's Annex): an attack
      restriction with a cost (CR 508.1c, 508.1h);
    * ``"attack_ban"`` — creatures can't attack you (Blazing Archon), or a
      creature can't (the Vow cycle's "can't attack you or planeswalkers you
      control"), or a player's creatures can't for a turn (The Second Doctor,
      Orzhov Advokist, Willie Lumpkin — a ``ProhibitActivity`` on attacking you);
    * ``"attack_limit"`` — no more than N creatures can attack (Crawlspace's
      "attack you", Silent Arbiter's "each combat").

    Not a deterrent: a restriction on the card's own attacks (Alexios, Deimos of
    Kosmos — :func:`_filter_recipient` keeps a spell's misbound ``SelfRef``,
    Promise of Loyalty), or a limit on attacking the card itself (The Eternal
    Wanderer, a planeswalker that only protects itself). Inside a granted ability
    "this planeswalker" is the permanent it is granted to (Tomik, Orzhov
    Lawmage's "Planeswalkers you control have 'No more than one creature can
    attack this planeswalker each combat'")."""
    granted: dict[int, ProtectionRecipient | None] = {}
    for unit in tree.units:
        granted.update(_granted_recipients(tree, unit))
    for n in tree.iter_typed():
        mode = static_mode_tag(n)
        if mode == "MaxAttackersEachCombat":
            if static_mode_field(n, "defender") != "ThisPermanent" or granted.get(
                id(n)
            ):
                return "attack_limit"
            continue
        if tag_of(n) == "ProhibitActivity":
            activity = getattr(n, "activity", None)
            if (
                tag_of(activity) == "Attack"
                and getattr(activity, "defended", None) in _DEFENDED_YOU
            ):
                return "attack_ban"
            continue
        if mode not in ("CantAttack", "CantAttackOrBlock"):
            continue
        affected = getattr(n, "affected", None)
        if (
            tag_of(affected) == "SelfRef"
            and not is_spell_card(tree)
            and not granted.get(id(n))
        ):
            continue
        if _taxes_attacks_on_you(getattr(n, "condition", MISSING)):
            return "attack_tax"
        if getattr(n, "attack_defended", None) in _DEFENDED_YOU:
            return "attack_ban"
    return None
