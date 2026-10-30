"""Layer-2 crosswalk — pure reader helpers over the typed mirror substrate.

Split out of the former monolithic ``crosswalk.py`` (package split, pure
mechanical move — see ``core.py``'s module docstring for the crosswalk's
design). This module holds the pure reader family: functions that read the
typed substrate (``isinstance`` / typed attribute access) and return scalars,
tuples, or ``Iterator``s over the substrate's OWN typed nodes — never
construct a :class:`~mtg_utils._card_ir.crosswalk.core.ConceptNode` /
:class:`~mtg_utils._card_ir.crosswalk.core.AbilityUnit` /
:class:`~mtg_utils._card_ir.crosswalk.core.ConceptTree`. ``core.py`` imports
from this module (one-directional); this module imports nothing from
``core.py`` at runtime — the return-type annotations that mention those
three classes are inert strings under ``from __future__ import annotations``
(PEP 563), guarded here under ``TYPE_CHECKING`` for static-analysis only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import fields
from functools import cache, partial
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast, get_args

from mtg_utils._card_ir.branches import (
    BRANCH_LISTS,
    natural_top_only,
    uncertain_list,
)
from mtg_utils._card_ir.card_subtypes import (
    ARTIFACT_TYPES,
    BATTLE_TYPES,
    ENCHANTMENT_TYPES,
    PLANESWALKER_TYPES,
)
from mtg_utils._card_ir.creature_types import CREATURE_TYPES
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk.core import AbilityUnit, ConceptNode, ConceptTree


#: "The object or player an earlier clause named" — a :class:`FieldCorrection`
#: value for a field phase stamped as the card itself or as you, and the
#: ``ConceptNode.subject`` mark the overlay corrections put on an effect whose
#: ``SelfRef`` target is such an object (phase's own ``Anaphoric`` quantity scope
#: is the same back-reference).
ANAPHORIC = "Anaphoric"
#: The ``ConceptNode.subject`` mark for an effect whose target also admits a
#: suspended card (CR 702.62b), the alternative phase dropped.
SUSPENDED_CARD = "suspended card"


# ── scalar/typed-node helpers ─────────────────────────────────────────────────


def _present(v: object) -> bool:
    """A built optional field that is neither absent (MISSING) nor JSON-null."""
    return v is not MISSING and v is not None


def tag_of(node: object) -> str | None:
    """The discriminator tag of a typed tagged node (``None`` for struct/scalar)."""
    if isinstance(node, TypedMirrorNode):
        # ``_tag`` is the generated node's documented discriminator ClassVar (the
        # same field ``to_dict`` re-emits as ``"type"``) — the intended read.
        return type(node)._tag  # noqa: SLF001
    return None


def residue_is(node: object, name: str) -> bool:
    """Whether an ``Unimplemented`` residue is the one a read keys on by ``name``.

    Through v0.66.0 phase named a parked clause by its HEAD WORD ("turn", "flip",
    "look", "create", "reveal", "creatures" …) or by a structural category
    ("static_structure", "unbound_subject", "Unsupported unless clause"). v0.86.0
    keeps the categories but files every head-word residue under a generic one
    (``unrecognized_clause_head`` / ``unparsed_verb_arguments`` / ``unparsed_quantity``
    …), so a verb-keyed read matches the phase name OR the description's first word —
    the same word the old name was. ``~`` (the card's own name) is a head word too."""
    if tag_of(node) != "Unimplemented":
        return False
    if getattr(node, "name", None) == name:
        return True
    desc = str(getattr(node, "description", "") or "")
    head = desc.split(None, 1)[0].lower() if desc.strip() else ""
    return head == name


# Recipient-bearing sub-fields an effect/trigger uses to name a player. Read in
# order; the first present one decides scope.
_SCOPE_FIELDS = ("target", "player", "owner", "recipient", "valid_target")

# The player-reference tags naming the opponents, and every player, on a
# recipient or a wrapper's ``player_scope``. A ``player_scope`` may also read
# ``All`` (Garruk, Veiled Butcher's -2), which only :func:`effect_player_reach`
# accepts.
OPPONENT_ACTOR_TAGS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent"}
)
_EACH_ACTOR_TAGS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})
#: "That player": the player an earlier clause of the ability named ("Target
#: player discards a card. ~ deals damage to that player …" — Hellhole Rats).
#: A player slot (a sub-ability's ``target`` / ``player`` / ``owner`` /
#: ``optional_player``) carries ``DeclaredPlayer{group}``, the group pointing at
#: the clause's ``declares_chosen_group``; other slots keep ``ParentTarget``. A
#: player set that holds the one holds the other.
PLAYER_BACK_REFERENCES: frozenset[str] = frozenset({"ParentTarget", "DeclaredPlayer"})
#: A group's controller whose effect you direct: yours, or the target player's
#: (you choose the target, CR 601.2c — Early Harvest's "Target player untaps all
#: basic lands they control").
YOUR_CHOSEN_CONTROLLERS: frozenset[str] = frozenset({"You", "TargetPlayer"})
#: A player the card picks out on a player slot: a target player (``Player`` /
#: ``Target``) or a back-reference to one (:data:`PLAYER_BACK_REFERENCES`). Not
#: ``TargetPlayer``, the tag a filter's ``controller`` takes for "target player's
#: creatures" — a set reading filter controllers adds it itself.
TARGETED_PLAYER_TAGS: frozenset[str] = PLAYER_BACK_REFERENCES | {"Player", "Target"}


def _unwrap_role_target(sub: object) -> object:
    """A scope field's effective player node.

    Since phase v0.40.0 reified targeting intent, an effect's ``target`` may be
    an untagged role-wrapper struct instead of the player node itself — at
    v0.45.0 exactly ``{role: "Recipient", recipient: <player>}`` (54 corpus
    nodes; Mana Flare's "that player adds") and ``{role: "CountSource",
    count_source: …}`` (4 nodes, not a recipient). Descend into ``recipient``
    when present; any other wrapper passes through unchanged and stays
    tag-less, so the walkers skip it as before.
    """
    if tag_of(sub) is None:
        rec = getattr(sub, "recipient", MISSING)
        if _present(rec):
            return rec
    elif tag_of(sub) == "Shared":
        # v0.66.0: an ``EachSourceDealsDamage`` recipient shared by every
        # source in the batch wraps the player/filter node under ``data``.
        data = getattr(sub, "data", MISSING)
        if _present(data):
            return data
    return sub


def _scope_from_player_tag(t: object) -> str | None:
    """Map a player-reference tag to a Signal scope, or None if unknown — the
    node's discriminator (:func:`_scope_from_player_node`) or the bare player
    string some fields carry (``ZoneCardCount.scope``, a search restriction's
    ``cause`` / ``who``)."""
    if t in ("Controller", "SelfRef", "You"):
        return "you"
    if t in OPPONENT_ACTOR_TAGS:
        return "opponents"
    if t in _EACH_ACTOR_TAGS:
        return "each"
    # A chosen/targeted player (``ParentTarget`` / ``Player`` / ``Any``) is NOT a
    # self resource — "target player draws, then discards" is a targeted effect,
    # not a self-loot outlet; the live self-loot lane scopes it out. Map to "any"
    # so a maker lane gated to you/each does not over-fire on it.
    if t in TARGETED_PLAYER_TAGS or t == "Any":
        return "any"
    return None


def _scope_from_player_node(node: object) -> str | None:
    """Map a player-reference typed node to a Signal scope, or None if unknown.

    Reads the node's discriminator tag (``Controller`` / ``Opponent`` / …,
    :func:`_scope_from_player_tag`) and, for a ``Typed`` filter, its
    ``controller`` — never oracle text.
    """
    t = tag_of(node)
    if (scope := _scope_from_player_tag(t)) is not None:
        return scope
    if t == "Typed":
        ctrl = getattr(node, "controller", None)
        if ctrl == "You":
            return "you"
        if ctrl == "Opponent":
            return "opponents"
        return "each"
    return None


def _effect_scope(node: TypedMirrorNode) -> str:
    """Derive a concept-node scope from an effect's recipient sub-fields."""
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            sc = _scope_from_player_node(_unwrap_role_target(sub))
            if sc is not None:
                return sc
    return "you"


def explicit_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The scope of an effect's EXPLICIT recipient field, or ``None`` if none present.

    Distinct from :func:`_effect_scope` (which defaults to "you" when phase carries
    no recipient): the self-loss-sustain lane must NOT read a default-"you" as a
    genuine self target (Gray Merchant's ``LoseLife`` has no ``target`` — the "each
    opponent loses" recipient lives on the trigger, not the node — so its scope is
    *unknown*, not self). ``None`` here means "no recipient on the node".
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            return _scope_from_player_node(_unwrap_role_target(sub))
    return None


# Recipient tags naming a player OTHER than the ability's controller: the
# triggering object's controller (``ParentTargetController``; phase v0.86.0 also
# emits ``EventTargetController`` — "that creature's controller" resolved off the
# TRIGGERING EVENT's target, Bellowing Fiend), the triggering player
# (``TriggeringPlayer``), or a chosen/targeted player (``ParentTarget`` / ``Player``
# / ``Target`` / ``Any``). A loss aimed at one of these is a DIRECTED loss at
# another player (CR 119.3), never a self-loss.
_DIRECTED_PLAYER_TAGS: frozenset[str] = TARGETED_PLAYER_TAGS | {
    "ParentTargetController",
    "EventTargetController",
    "TriggeringPlayer",
    "Any",
}


def lifeloss_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The DIRECTION of a life-loss effect (who loses) from its recipient node.

    Reads a ``LoseLife`` node's recipient/target player STRUCTURALLY (CR 119.3), so
    direction never rides phase's ``trigger_scope`` — which it MIS-scopes to ``you``
    for an ability triggered off an OPPONENT's object (Archfiend of the Dross
    "whenever a creature an opponent controls dies, its controller loses 2 life" —
    recipient ``ParentTargetController``; Ashenmoor Liege "that player loses 4 life"
    — recipient ``TriggeringPlayer``; phase bug [P5]). A controller/self recipient →
    ``you``; an each/all-player recipient → ``each``; an opponent recipient, or a
    RELATIVE/targeted one (the triggering object's controller / the triggering
    player / a targeted player) → ``opponents`` (a directed loss). ``None`` when the
    node carries NO recipient field — a bare self-loss (Agent Venom "you draw a card
    and lose 1 life", Dark Confidant's upkeep self-loss), so the caller falls back to
    the wrapper ``player_scope`` (Gray Merchant's "each opponent loses").
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        if tag_of(sub) in _DIRECTED_PLAYER_TAGS:
            return "opponents"
        sc = _scope_from_player_node(sub)
        if sc == "you":
            return "you"
        if sc == "each":
            return "each"
        return "opponents"
    return None


def lifeloss_recipient_is_degraded_typed(node: TypedMirrorNode) -> bool:
    """Whether :func:`lifeloss_recipient_scope`'s ``"each"`` read for ``node``
    rests on a COMPLETELY uninformative ``Typed`` recipient filter
    (``controller=None``, no ``properties``, no ``type_filters`` — ADR-0038
    W5b). A genuine each/all-player ``LoseLife`` never reaches phase's
    ``Typed`` branch at all (its recipient field is MISSING entirely, the
    each-scope living on the wrapping ability's ``player_scope`` instead —
    corpus-verified across 43 unconditional "each opponent loses" instances,
    all ``target=MISSING``); this exact empty shape is instead phase's
    degraded structuring of "each opponent loses N life" when the clause
    sits under a CONDITION or optional "you may have" wrapper (Baba Lysaga,
    Night Witch's "If there were three or more card types ..., each opponent
    loses 3 life"; Vohar, Vodalian Desecrator's "If you discarded ..., each
    opponent loses 1 life"; Faerie Tauntings' "you may have each opponent
    lose 1 life") — corpus-verified narrow (9 of 252 Typed-recipient
    instances, ALL under this exact ``(None, (), ())`` shape). The lane
    calling this should treat an ``"each"`` read backed by this shape as
    UNRESOLVED and fall through to its own text-based disambiguation rather
    than trust the shared :func:`_scope_from_player_node` Typed-filter
    default (which stays ``"each"`` for every OTHER caller — this function
    changes no existing caller's behavior, it only lets the lifeloss lane
    distrust its own already-narrow recipient read for this one shape)."""
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        if tag_of(sub) != "Typed":
            return False
        return (
            getattr(sub, "controller", None) is None
            and not (getattr(sub, "properties", None) or None)
            and not (getattr(sub, "type_filters", None) or None)
        )
    return False


# The union of every "names a player other than the controller" tag family
# independently rediscovered by :func:`lifeloss_recipient_scope`
# (``_DIRECTED_PLAYER_TAGS``) and :func:`discard_recipient_scope`
# (``_DISCARD_OPP_TAGS``, defined further below), plus the explicit
# opponent/defending-player tags (CR 506.2 — the b11 tap_down precedent).
_DETRIMENT_DIRECTED_TAGS: frozenset[str] = (
    _DIRECTED_PLAYER_TAGS
    | OPPONENT_ACTOR_TAGS
    | frozenset({"DefendingPlayer", "TargetPlayer", "TargetOpponent"})
)


def detriment_directed_scope(node: TypedMirrorNode) -> str | None:
    """The DIRECTION of an unambiguously DETRIMENTAL effect from its recipient
    node — Dan's **detriment-directed-targeting** principle (2026-07-10):
    a "target player" / "target creature's controller" recipient on an
    unambiguously detrimental effect (skip-untap/tap-down, life loss,
    discard/reveal-strip, sacrifice — grows per consumer, never assume
    beyond what's measured) is OPPONENT-DIRECTED for deck-building SIGNAL
    purposes. CR 603.3d's targeting freedom (a spell/ability's controller
    may legally target themself) is acknowledged, never contradicted —
    this is a deck-building read of intent, not a rules claim about legal
    targets. "each player" stays a DIFFERENT, symmetric signal class
    (``"each"``), never folded into ``"opponents"``; a beneficial
    self-target COMBO shape (a card that WANTS its own detriment) is its
    own structural pattern elsewhere, never a reason to mute this mainline
    read.

    Generalizes the identical ad-hoc dispatch independently grown by
    :func:`lifeloss_recipient_scope` and :func:`discard_recipient_scope`
    into one reusable predicate for NEW consumers (tap_down's
    ``SkipNextStep``, hand_disruption's ``RevealHand``) — those two keep
    their own bespoke tag sets (a few extra structural-recipient tags each
    doesn't share), so this is additive, not a replacement.

    Returns ``"you"`` for a controller/self recipient, ``"each"`` for a
    symmetric all-player recipient, ``"opponents"`` for everything else
    present (an explicit opponent tag OR a targeted/relative recipient),
    ``None`` when the node carries NO recipient field at all (the caller
    falls back to the wrapper ``player_scope``). See
    ``deck-forge/CONTEXT.md``'s "Detriment-directed targeting" entry.
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        if tag_of(sub) in _DETRIMENT_DIRECTED_TAGS:
            return "opponents"
        sc = _scope_from_player_node(sub)
        if sc == "you":
            return "you"
        if sc == "each":
            return "each"
        return "opponents"
    return None


def trigger_constraint_tag(trig: TypedMirrorNode) -> str | None:
    """The discriminator tag of a trigger's ``constraint`` node, or ``None``.

    phase gates a trigger with a typed ``constraint``: the per-turn restrictions
    (``OnlyDuringYourTurn`` / ``OnlyDuringOpponentsTurn``) and the spell-velocity
    ``NthSpellThisTurn`` ("whenever you cast your second spell each turn" —
    Cori-Steel Cutter; the qualifier the OLD lossy projection dropped, forcing
    the live path onto a byte word-mirror). The batch-10 second-spell lane reads
    this tag + :func:`trigger_constraint_n` — a pure typed read (CR 603.2).
    """
    return tag_of(getattr(trig, "constraint", None))


def trigger_constraint_n(trig: TypedMirrorNode) -> int | None:
    """The ``n`` of a trigger's constraint (``NthSpellThisTurn`` → 2 for the
    second-spell form, 1 for "your first spell during each opponent's turn" —
    Alela, Cunning Conqueror, which the second-spell lane must NOT read as a
    velocity payoff). ``None`` when the constraint carries no ``n``.
    """
    n = getattr(getattr(trig, "constraint", None), "n", None)
    return n if isinstance(n, int) else None


def trigger_turn_constraint(trig: TypedMirrorNode) -> str | None:
    """The turn-restriction tag of a trigger's ``constraint`` (``OnlyDuringYourTurn``
    / ``OnlyDuringOpponentsTurn`` / ``None``).

    phase gates a per-turn trigger with a ``constraint`` node: an "each opponent's
    upkeep" trigger carries ``OnlyDuringOpponentsTurn`` (Sheoldred, Whispering One),
    a "your upkeep" trigger ``OnlyDuringYourTurn`` (Archfiend of the Dross), and an
    "each player's upkeep" trigger no constraint (Braids, Cabal Minion; Smokestack).
    The edict scope of a ``ScopedPlayer`` ("that player sacrifices") reads it to tell
    a symmetric each-player wrath from an opponent-only edict (CR 701.21a).
    """
    return trigger_constraint_tag(trig)


def trigger_phase(trig: TypedMirrorNode) -> str | None:
    """The step / phase a phase-trigger fires at the beginning of (``"Upkeep"`` /
    ``"Draw"`` / ``"BeginCombat"`` / ``"End"`` …), or ``None`` for any other
    trigger. phase carries it as a bare string on the trigger's ``phase`` field
    beside ``mode: "Phase"`` (the ``trigger_event == "phase"`` units)."""
    p = getattr(trig, "phase", MISSING)
    return p if isinstance(p, str) else None


def scoped_player_scope(unit: AbilityUnit | None) -> str | None:
    """Resolve a ``ScopedPlayer`` reference ("that player") to a lane scope via the
    owning trigger's turn constraint (CR 701.21a for the edict case).

    phase tags a triggered "that player sacrifices / draws / is dealt damage" with
    ``ScopedPlayer`` — the scoped player is whoever the trigger references, which
    the constraint disambiguates: ``OnlyDuringOpponentsTurn`` (Sheoldred — "each
    opponent's upkeep") → opponents; no constraint (Braids, Cabal Minion;
    Smokestack — "each player's upkeep, that player sacrifices") → each, a
    SYMMETRIC self-inclusive effect that hits YOU too; ``OnlyDuringYourTurn`` (a
    "your upkeep, you sacrifice" self-sac) → ``None``. A non-trigger ScopedPlayer
    keeps the opponent default.
    """
    if unit is None or getattr(unit, "origin", None) != "trigger":
        return "opponents"
    c = trigger_turn_constraint(unit.node)
    if c == "OnlyDuringOpponentsTurn":
        return "opponents"
    if c == "OnlyDuringYourTurn":
        return None
    return "each"


def refers_to_scoped_player(node: object) -> bool:
    """Whether anything under ``node`` (a trigger unit's node: its condition,
    effect chain and operands) refers to the trigger's ``ScopedPlayer`` — "that
    player" / "that opponent" bound by an "each player's / each opponent's
    [step]" trigger. A deep walk, so an intervening-if on the scoped player
    (Lavaborn Muse: "if that player has two or fewer cards in hand") counts, as
    does a filter controlled by them (Braids: "that player sacrifices"). CR
    805.4d keys a Two-Headed Giant step trigger's per-player firing on exactly
    this reference."""
    return any(_names_scoped_player(n) for n in _iter_typed_nodes(node))


def _names_scoped_player(n: TypedMirrorNode) -> bool:
    """Whether one node is the ``ScopedPlayer`` or a filter they control."""
    return (
        tag_of(n) == "ScopedPlayer" or getattr(n, "controller", None) == "ScopedPlayer"
    )


def trigger_damage_kind(trig: TypedMirrorNode) -> str:
    """The ``damage_kind`` of a damage trigger (``"CombatOnly"`` / ``"Any"``),
    ``""`` when absent.

    phase stamps every trigger with a ``damage_kind`` (default ``"Any"``); it is
    meaningful only on a ``DamageDone``-mode trigger, where it discriminates the
    combat-connect payoff ("deals combat damage to an opponent" — Coastal Piracy,
    CR 510.1b) from the any-damage connect ("deals damage to an opponent" —
    Hypnotic Specter, CR 120.3). The caller gates on the mode first.
    """
    dk = getattr(trig, "damage_kind", MISSING)
    return dk if isinstance(dk, str) else ""


def mana_restrictions(node: TypedMirrorNode) -> tuple[str, ...]:
    """The spend-restriction strings of a ``Mana`` effect (CR 106.4 / 106.6).

    phase carries "Spend this mana only …" as ``Mana.restrictions`` —
    ``"XCostOnly"`` (Rosheen Meanderer's "only on costs that contain {X}", the
    xspell-enabler arm), ``"ActivateOnly"``, ``"ChosenCreatureType"``,
    ``"SpellOnly"``. Empty when unrestricted.
    """
    rs = getattr(node, "restrictions", MISSING)
    if _present(rs) and isinstance(rs, (list, tuple)):
        return tuple(r for r in rs if isinstance(r, str))
    return ()


def mana_spell_type_restriction(node: TypedMirrorNode) -> str:
    """The spell type a ``Mana`` effect's mana is limited to (CR 106.6), or ``""``.

    phase carries the typed restrictions as variants beside the string ones
    :func:`mana_restrictions` reads: ``SpellTypeOrAbilityActivation`` with a
    ``spell_type`` ("Artifact": The Mightstone and Weakstone's "can't be spent to
    cast nonartifact spells"; "Colorless Eldrazi": Eldrazi Temple), and
    ``SpellType`` with a bare string ("Multicolored": Pillar of the Paruns).
    """
    rs = getattr(node, "restrictions", MISSING)
    if not (_present(rs) and isinstance(rs, (list, tuple))):
        return ""
    for r in rs:
        if not isinstance(r, MirrorVariant):
            continue
        if r.key == "SpellTypeOrAbilityActivation":
            spell_type = getattr(r.inner, "spell_type", None)
        elif r.key == "SpellType":
            spell_type = r.inner
        else:
            continue
        if isinstance(spell_type, str) and spell_type:
            return spell_type
    return ""


def mana_spell_types(node: TypedMirrorNode, *, any_of: bool = False) -> tuple[str, ...]:
    """The spell types a ``Mana`` effect's mana may be spent on (CR 106.6), one
    entry per alternative: ``("Artifact",)`` (Grand Architect), ``("Artifact",
    "Creature")`` for "artifact or creature spells" (Geosurge), ``()`` when
    unrestricted (:func:`mana_spell_type_restriction`'s string, split at its
    "or"). With ``any_of`` a spell type that is one choice of an ``Any`` list
    reads too ("Spend this mana only to cast an enchantment spell, unlock a
    door, or turn a permanent face up" — Creeping Peeper): the mana MAY go to
    that type, though it isn't limited to it."""
    spell_type = mana_spell_type_restriction(node)
    if spell_type:
        return tuple(t.strip() for t in spell_type.split(" or "))
    rs = getattr(node, "restrictions", MISSING)
    if not (any_of and _present(rs) and isinstance(rs, (list, tuple))):
        return ()
    for r in rs:
        if (
            isinstance(r, MirrorVariant)
            and r.key == "Any"
            and isinstance(r.inner, list)
        ):
            for alt in r.inner:
                if (
                    isinstance(alt, MirrorVariant)
                    and alt.key == "SpellType"
                    and isinstance(alt.inner, str)
                    and alt.inner
                ):
                    return (alt.inner,)
    return ()


def mana_spend_criteria(node: TypedMirrorNode) -> tuple[str, ...]:
    """The bare criteria of a ``Mana`` effect's ``SpellMatchingCostCriteria``
    restriction (CR 106.6): the spells its mana may be spent on, any one
    sufficing — ``"HasXInCost"`` for Troyan, Gutsy Explorer's "spells with mana
    value 5 or greater or spells with {X} in their mana costs" (the mana-value
    criterion is a struct, not a string, and is left out)."""
    rs = getattr(node, "restrictions", MISSING)
    if not (_present(rs) and isinstance(rs, (list, tuple))):
        return ()
    out: list[str] = []
    for r in rs:
        if not (isinstance(r, MirrorVariant) and r.key == "SpellMatchingCostCriteria"):
            continue
        # A bare list (Troyan) or a struct beside a ``spell_type`` (Helga,
        # Skittish Seer's "creature spells with …").
        crit = r.inner
        if isinstance(crit, MirrorVariant):
            crit = crit.inner
        elif isinstance(crit, TypedMirrorNode):
            crit = getattr(crit, "criteria", None)
        if isinstance(crit, (list, tuple)):
            out.extend(c for c in crit if isinstance(c, str))
    return tuple(out)


def cost_mana_value(cost: object) -> int | None:
    """Mana value (CR 202.3) of a phase ``Cost`` node: its ``generic`` plus one per
    shard, an ``X`` shard counting 0 (CR 202.3e). ``None`` for anything else."""
    if tag_of(cost) != "Cost":
        return None
    generic = getattr(cost, "generic", MISSING)
    shards = getattr(cost, "shards", MISSING)
    if not (isinstance(generic, int) and isinstance(shards, (list, tuple))):
        return None
    return generic + sum(1 for s in shards if s != "X")


def mana_value_paying_life(parts: Iterable[tuple[str, int | None]]) -> int | None:
    """The mana value of a cost made of mana and life payments, or ``None`` when a
    part is neither (an exile or sacrifice is a condition a deck can't always
    meet). ``parts`` are ``("mana", mana value)`` / ``("life", None)`` /
    ``("other", None)`` — Infestation's "Evoke—{1}{B}{B}, Pay 3 life" is 3."""
    total = 0
    for kind, mv in parts:
        if kind == "mana" and mv is not None:
            total += mv
        elif kind != "life":
            return None
    return total


def _composite_mana_value(cost: object) -> int | None:
    """:func:`mana_value_paying_life` over a ``Composite`` cost node."""
    parts = getattr(cost, "costs", MISSING)
    if tag_of(cost) != "Composite" or not isinstance(parts, (list, tuple)):
        return None
    return mana_value_paying_life(
        ("mana", cost_mana_value(getattr(part, "cost", MISSING)))
        if tag_of(part) == "Mana"
        else ("life" if tag_of(part) == "PayLife" else "other", None)
        for part in parts
    )


# The keywords that cast the card itself, from hand, for a different payment that
# takes effect now — the cost a deck plays the card for on curve. Evoke (CR 702.74a),
# dash (702.109a), blitz (702.152a), warp (702.185a) and impending (702.176a) are paid
# instead of the mana cost; prototype (702.160a) casts it with an alternative set of
# characteristics, mana cost included. Suspend and plot are not here: their payment
# exiles the card to cast it on a later turn.
CURVE_COST_KEYWORDS = frozenset(
    {"Warp", "Evoke", "Dash", "Blitz", "Prototype", "Impending"}
)


def keyword_cost(keyword: object) -> object | None:
    """The cost node a parameterized keyword carries, unwrapped, or ``None``.

    Phase's keyword payloads come in four shapes: the ``Cost`` itself (Warp, Dash,
    Foretell, Morph …); a ``Mana`` / ``NonMana`` wrapper whose ``data`` is a
    ``Cost`` or a non-mana cost such as a ``Composite`` (Evoke, Flashback,
    Escape, Buyback); a struct with a ``cost`` field beside its other parameters
    (Suspend's ``count``, Prototype's power and toughness, Impending's
    ``counters``); or Emerge's ``mana_cost`` beside its ``sacrifice_filter``."""
    if not isinstance(keyword, MirrorVariant):
        return None
    inner = keyword.inner
    tag = tag_of(inner)
    if tag == "Cost":
        return inner
    if tag in ("Mana", "NonMana"):
        data = getattr(inner, "data", MISSING)
        return data if _present(data) else None
    for field in ("cost", "mana_cost"):
        sub = getattr(inner, field, MISSING)
        if _present(sub):
            return sub
    return None


def keyword_curve_cost(keyword: object) -> int | None:
    """The mana value of a :data:`CURVE_COST_KEYWORDS` keyword's cost, or ``None``.

    Read off :func:`keyword_cost`: a ``Cost`` (Warp, Dash, Blitz, Prototype,
    Impending, a mana Evoke), or a mana-and-life ``Composite`` (Infestation's
    evoke). Fury's "Exile a red card from your hand" has no mana cost to plan on."""
    if not isinstance(keyword, MirrorVariant) or keyword.key not in CURVE_COST_KEYWORDS:
        return None
    cost = keyword_cost(keyword)
    if tag_of(cost) == "Composite":
        return _composite_mana_value(cost)
    return cost_mana_value(cost)


class ObjectFacts(NamedTuple):
    """What a card IS, for asking whether a filter can describe it: its own core
    types, subtypes and supertypes (phase's capitalized words), its colors
    (``W``/``U``/``B``/``R``/``G``), and whether it is every creature type
    (:func:`is_every_creature_type` — changeling, CR 702.73a), which no printed
    ``subtypes`` set spells out. Built from a card's trees by
    ``_card_ir.trees.object_facts``. Ask it through :meth:`has_type` /
    :meth:`has_supertype` / :meth:`has_subtype` (any case), never the raw sets:
    only :meth:`has_subtype` knows what changeling adds."""

    types: frozenset[str]
    subtypes: frozenset[str]
    supertypes: frozenset[str]
    colors: frozenset[str]
    every_creature_type: bool = False
    #: Its mana value (CR 202.3), ``None`` when unknown; and whether its mana cost
    #: has {X} (CR 107.3).
    mana_value: int | None = None
    x_cost: bool = False
    #: Its printed keywords, folded (:func:`normalised_keyword_name`) — for what a
    #: filter asks of a spell's casting ("a kicked spell" needs kicker).
    keywords: frozenset[str] = frozenset()
    #: The core types and subtypes its own static adds only while it isn't on the
    #: battlefield (:func:`off_battlefield_types` — Grist, the Hunger Tide), which
    #: :meth:`off_battlefield` folds in.
    off_battlefield_types: frozenset[str] = frozenset()
    off_battlefield_subtypes: frozenset[str] = frozenset()

    def off_battlefield(self) -> ObjectFacts:
        """The object as a card or a spell — anywhere but the battlefield, where
        the types :func:`off_battlefield_types` reads are its own too. Grist's
        ruling: "Anywhere but on the battlefield, Grist is a Legendary
        Planeswalker Creature — Grist Insect" (a creature spell Essence Scatter
        counters, a creature card Chord of Calling finds)."""
        if not (self.off_battlefield_types or self.off_battlefield_subtypes):
            return self
        return self._replace(
            types=self.types | self.off_battlefield_types,
            subtypes=self.subtypes | self.off_battlefield_subtypes,
            off_battlefield_types=frozenset(),
            off_battlefield_subtypes=frozenset(),
        )

    def has_type(self, word: str) -> bool:
        return _fold(word) in {_fold(t) for t in self.types}

    def has_supertype(self, word: str) -> bool:
        return _fold(word) in {_fold(t) for t in self.supertypes}

    def has_subtype(self, word: str) -> bool:
        """Whether the object has subtype ``word``: printed, or — for an object
        that is every creature type — any of CR 205.3m's creature types. A
        changeling is no Equipment, Aura or Forest."""
        w = _fold(word)
        if w in {_fold(t) for t in self.subtypes}:
            return True
        return self.every_creature_type and w in CREATURE_TYPES


def _fold(word: str) -> str:
    return word.lower().replace("\u2019", "'")


def _is_off_battlefield_condition(cond: object) -> bool:
    """A static's ``Not(SourceInZone Battlefield)`` condition — "as long as ~
    isn't on the battlefield"."""
    if tag_of(cond) != "Not":
        return False
    inner = getattr(cond, "condition", None)
    return tag_of(inner) == "SourceInZone" and getattr(inner, "zone", None) == (
        "Battlefield"
    )


def off_battlefield_types(tree: ConceptTree) -> tuple[frozenset[str], frozenset[str]]:
    """``(core types, subtypes)`` the card's own static adds to it while it isn't
    on the battlefield: Grist, the Hunger Tide's "As long as Grist isn't on the
    battlefield, it's a 1/1 Insect creature in addition to its other types" —
    ``Creature`` and ``Insect``. An ability that states which zones it functions
    in functions only there (CR 113.6b), so on the battlefield Grist is "just a
    planeswalker" (its ruling) and these types aren't its own."""
    types: set[str] = set()
    subtypes: set[str] = set()
    for unit in tree.iter_units("static"):
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
                continue
            if not _is_off_battlefield_condition(getattr(sdef, "condition", None)):
                continue
            tag = tag_of(mod)
            if tag == "AddType" and isinstance(
                core := getattr(mod, "core_type", None), str
            ):
                types.add(core)
            elif tag == "AddSubtype" and isinstance(
                sub := getattr(mod, "subtype", None), str
            ):
                subtypes.add(sub)
    return frozenset(types), frozenset(subtypes)


#: Where :func:`object_facts_of` reads a card: ``"battlefield"`` (printed types
#: only — a permanent), ``"elsewhere"`` (a card or a spell, with the types it has
#: only off the battlefield folded in — :meth:`ObjectFacts.off_battlefield`), or
#: ``"any"`` (both kept apart, so :func:`filter_admits` picks per filter).
FactsZone = Literal["any", "battlefield", "elsewhere"]


def object_facts_of(
    trees: Iterable[ConceptTree],
    *,
    zone: FactsZone = "any",
    colors: frozenset[str] = frozenset(),
    mana_value: int | None = None,
    x_cost: bool = False,
) -> ObjectFacts:
    """The :class:`ObjectFacts` a card's trees (every face) say: its types,
    subtypes and supertypes, whether it is every creature type
    (:func:`is_every_creature_type`), its keywords, and — unless ``zone`` is
    ``"battlefield"`` — the types it has only off the battlefield
    (:func:`off_battlefield_types`), folded in for ``"elsewhere"``. Colors, mana
    value and {X} come from the record (``_card_ir.trees.object_facts``) when the
    caller has one."""
    trees = tuple(trees)
    elsewhere = (
        [] if zone == "battlefield" else [off_battlefield_types(t) for t in trees]
    )
    facts = ObjectFacts(
        types=frozenset(t for tree in trees for t in tree.card_types),
        subtypes=frozenset(t for tree in trees for t in tree.card_subtypes),
        supertypes=frozenset(t for tree in trees for t in tree.card_supertypes),
        colors=colors,
        every_creature_type=any(is_every_creature_type(tree) for tree in trees),
        mana_value=mana_value,
        x_cost=x_cost,
        keywords=frozenset(
            normalised_keyword_name(k) for tree in trees for k in tree.card_keywords
        ),
        off_battlefield_types=frozenset(t for types, _ in elsewhere for t in types),
        off_battlefield_subtypes=frozenset(t for _, subs in elsewhere for t in subs),
    )
    return facts.off_battlefield() if zone == "elsewhere" else facts


def _describes_off_battlefield(filt: object) -> bool:
    """Whether a filter describes an object off the battlefield: a spell (an
    ``And`` holding ``StackSpell`` — Double Major's "target creature spell you
    control") or a card in a zone its ``InZone`` property names. Reading the
    filter's zone as the card's is this read's own decision, so a card whose type
    holds only off the battlefield (Grist's ruling: "Anywhere but on the
    battlefield, Grist is a Legendary Planeswalker Creature"; CR 113.6b) is
    judged as it is there."""
    tag = tag_of(filt)
    if tag == "And" and any(
        tag_of(f) == "StackSpell" for f in getattr(filt, "filters", ()) or ()
    ):
        return True
    zones = filter_inzone_zones(filt) if tag == "Typed" else ()
    return bool(zones) and "Battlefield" not in zones


def filter_admits(filt: object, facts: ObjectFacts) -> bool | None:
    """Whether a phase object filter can describe the card ``facts`` describes.

    Reads the type words (``Permanent`` and ``Card`` admit any type), the negated
    ones ("noncreature"), subtypes, the
    supertype / token / colorless properties, and recurses ``Or`` (any) / ``And``
    (all). ``SelfRef`` (the filter's own card) is ``False``. ``None`` when the filter
    is a reference this read can't resolve (``ParentTarget``, ``AttachedTo``, …) —
    the caller resolves those against their own context. A filter describing a
    spell or a card in another zone (:func:`_describes_off_battlefield`) sees the
    card as it is there (:meth:`ObjectFacts.off_battlefield`)."""
    tag = tag_of(filt)
    if tag == "SelfRef":
        return False
    if tag == "StackSpell":
        return True  # "a spell" — the And beside it carries the constraint
    if (
        facts.off_battlefield_types or facts.off_battlefield_subtypes
    ) and _describes_off_battlefield(filt):
        facts = facts.off_battlefield()
    if tag in ("Or", "And"):
        answers = [filter_admits(f, facts) for f in getattr(filt, "filters", ()) or ()]
        if not answers or None in answers:
            return None
        return any(answers) if tag == "Or" else all(answers)
    if tag != "Typed":
        return None
    cores = set(filter_core_types(filt))
    if cores and not (
        {"Permanent", "Card"} & cores or any(facts.has_type(c) for c in cores)
    ):
        return False
    for word in filter_non_types(filt):  # "noncreature permanent" (Astral Dragon)
        if facts.has_type(word) or facts.has_supertype(word) or facts.has_subtype(word):
            return False
    subtypes = set(filter_subtypes(filt))
    if subtypes and not any(facts.has_subtype(s) for s in subtypes):
        return False
    for prop in getattr(filt, "properties", ()) or ():
        ptag = tag_of(prop)
        value = getattr(prop, "value", MISSING)
        if ptag == "Token":
            return False  # a card is never a token
        if ptag == "HasSupertype" and not facts.has_supertype(str(value)):
            return False
        if ptag == "NotSupertype" and facts.has_supertype(str(value)):
            return False
        if ptag == "WasKicked" and not facts.keywords & {"kicker", "multikicker"}:
            return False  # "a kicked spell" (Verazol): only one with kicker, 702.33a
        if ptag == "HasXInManaCost" and not facts.x_cost:
            return False  # "a spell with {X} in its mana cost" (Owlin Spiralmancer)
        if ptag == "Cmc" and not _mana_value_admits(prop, facts.mana_value):
            return False  # "a spell with mana value 5 or greater" (Gandalf)
        if (
            ptag == "ColorCount"
            and getattr(prop, "comparator", MISSING) == "EQ"
            and getattr(prop, "count", MISSING) == 0
            and facts.colors
        ):
            return False  # "colorless" (CR 105.2c)
    return True


def filter_takes_in_card(filt: object, tree: ConceptTree) -> bool:
    """Whether a group or target filter takes in the card itself: "All Slivers" on
    a Sliver, "target creature you control" on a creature (CR 115.5: only a spell
    or ability is an illegal target for itself) — never "other Slivers", "another
    target creature" or an opponent's. The read a grant the card falls under goes
    through (Hibernation Sliver's ruling: a Sliver is affected by its own
    ability); an ``Or`` takes it in when an arm does ("Henry Wu and other Human
    creatures you control")."""
    tag = tag_of(filt)
    if tag == "SelfRef":
        return True
    if tag == "Or":
        return any(
            filter_takes_in_card(f, tree) for f in getattr(filt, "filters", ()) or ()
        )
    if filter_controller(filt) == "Opponent":
        return False
    if {"Another", "Other"} & set(filter_predicates(filt)):
        return False
    return filter_admits(filt, object_facts_of((tree,))) is True


_COMPARE: dict[str, Callable[[int, int], bool]] = {
    "EQ": lambda a, b: a == b,
    "NE": lambda a, b: a != b,
    "GE": lambda a, b: a >= b,
    "GT": lambda a, b: a > b,
    "LE": lambda a, b: a <= b,
    "LT": lambda a, b: a < b,
}


def _mana_value_admits(prop: object, mana_value: int | None) -> bool:
    """A ``Cmc`` filter property (:func:`_fixed_cmc`) against a known mana value;
    a bound the read can't fix (X, a chosen number) admits."""
    bound = _fixed_cmc(prop)
    if mana_value is None or bound is None or bound[0] not in _COMPARE:
        return True
    return _COMPARE[bound[0]](mana_value, bound[1])


def copied_ability_kind(node: object) -> str | None:
    """Which abilities a ``CopySpell`` of a ``StackAbility`` copies (CR 707.10):
    ``"Triggered"`` (Strionic Resonator: "Copy target triggered ability you
    control"), ``"Activated"``, or ``"Any"`` when the target names no kind
    (Lithoform Engine: "Copy target activated or triggered ability"). ``None`` for
    anything else — a spell copier (Twincast) copies no ability."""
    if tag_of(node) != "CopySpell":
        return None
    target = getattr(node, "target", MISSING)
    if tag_of(target) != "StackAbility":
        return None
    kind = getattr(target, "kind", MISSING)
    return kind if isinstance(kind, str) else "Any"


#: The trigger events of an ability being activated (CR 602.2): a copy of
#: "that ability" in such a trigger copies the activated ability (Rings of
#: Brighthearth, Illusionist's Bracers; Rowan's Talent's loyalty ability).
ACTIVATION_TRIGGER_EVENTS = frozenset({"abilityactivated", "loyaltyabilityactivated"})


def unit_copied_ability_kind(unit: AbilityUnit, node: object) -> str | None:
    """:func:`copied_ability_kind`, and ``"Activated"`` for a ``CopySpell`` in a
    trigger on an ability being activated (:data:`ACTIVATION_TRIGGER_EVENTS`),
    whose "copy that ability" names the ability that triggered it — Rings of
    Brighthearth's "Whenever you activate an ability, if it isn't a mana
    ability, … copy that ability" (CR 707.10: a copy of an ability is an
    ability, never a spell). ``None`` for a spell copy (Twincast)."""
    kind = copied_ability_kind(node)
    if kind is not None:
        return kind
    if tag_of(node) == "CopySpell" and unit.trigger_event in ACTIVATION_TRIGGER_EVENTS:
        return "Activated"
    return None


def double_triggers_cause(node: object) -> tuple[str, tuple[str, ...]] | None:
    """The cause a ``DoubleTriggers`` static scopes its doubling to, or ``None``.

    ``("Any", ())`` doubles every trigger of the affected permanents (Roaming
    Throne, Echoes of Eternity); ``("EntersBattlefield", core types)`` only those an
    entering object of those types causes (Panharmonicon: Artifact, Creature;
    Ancient Greenwarden: Land); ``("CreatureDying", ())`` (Teysa Karlov) and
    ``("CreatureAttacking", ())`` (Isshin) the dying / attacking ones."""
    if static_mode_tag(node) != "DoubleTriggers":
        return None
    cause = static_mode_field(node, "cause")
    if isinstance(cause, str):
        return cause, ()
    if isinstance(cause, MirrorVariant):
        inner = cause.inner
        types = inner.inner if isinstance(inner, MirrorVariant) else inner
        if not isinstance(types, (list, tuple)):
            types = ()
        return cause.key, tuple(t for t in types if isinstance(t, str))
    return None


def produced_kind(node: TypedMirrorNode) -> str:
    """The tag of a ``Mana`` effect's ``produced`` spec, or ``""`` when absent.

    ``Colorless`` / ``AnyOneColor`` / ``ChosenColor`` / ``OpponentLandColors``, and
    the deck-colored kinds: ``AnyInCommandersColorIdentity`` (Arcane Signet),
    ``AnyOneColorAmongPermanents`` (Mox Amber), ``ChoiceAmongExiledColors``
    (Chrome Mox).
    """
    p = getattr(node, "produced", MISSING)
    if not _present(p):
        return ""
    return tag_of(p) or ""


# phase v0.66.0 pin bump: the per-source batch damage effect. "Each <X> you
# control deals damage equal to its power to target creature" (Moonlight
# Hunt, Bartz and Boko, Kamahl's Will; Sarkhan the Mad's "… to target
# player") is an ``EachSourceDealsDamage{sources: <filter>, amount:
# Ref(Power, scope: BatchSource), recipient: Shared{data: <target>}}`` since
# v0.53.0 (#7322) — a ``DealDamage{amount: Ref(Power, Anaphoric)}`` through
# v0.45.0 (7 fixed-amount nodes then, 17 nodes / 14 commander-legal cards
# now). The recipient sits under a ``Shared`` wrapper (one target shared by
# every source; ``EachController`` / ``OtherBatchSource`` for the
# each-creature-hits-its-controller / another-batch-member forms).
DAMAGE_EFFECT_TAGS: frozenset[str] = frozenset(
    {"DealDamage", "DamageAll", "DamageEachPlayer", "EachSourceDealsDamage"}
)


def damage_recipient(node: object) -> object:
    """The recipient node of a damage effect — ``target`` for the
    ``DealDamage`` / ``DamageAll`` shapes, the ``Shared``-unwrapped
    ``recipient`` of an ``EachSourceDealsDamage`` — or ``None``."""
    if tag_of(node) == "EachSourceDealsDamage":
        rec = getattr(node, "recipient", MISSING)
        if not _present(rec):
            return None
        if tag_of(rec) == "Shared":
            data = getattr(rec, "data", MISSING)
            return data if _present(data) else None
        return rec
    tgt = getattr(node, "target", MISSING)
    return tgt if _present(tgt) else None


#: Which side of CR 120.1 a damage read asks about: a ``"player"`` (CR 120.3a —
#: loses life) or a ``"permanent"`` (a battle, creature or planeswalker — CR
#: 120.3c/e/h — the removal half).
DamageRecipient = Literal["player", "permanent"]

# The permanents damage can be dealt to (CR 120.1: "battles, creatures,
# planeswalkers, and players"), plus phase's generic ``Permanent`` word — the one
# board-type set every damage-reach read (and the removal walks) shares.
DAMAGE_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Battle", "Creature", "Planeswalker", "Permanent"}
)


def _effect_reaches(
    node: TypedMirrorNode, root: object | None, recipient: DamageRecipient
) -> bool:
    """Whether a damage EFFECT can reach RECIPIENT (CR 120.1), read structurally —
    the one dispatch :func:`effect_reaches_player` and
    :func:`effect_reaches_permanent` share.

    * ``DamageEachPlayer`` hits players only.
    * ``DamageAll`` hits players when it carries a ``player_filter`` (Pestilence
      pings creatures AND each player; Pyroclasm-as-``DamageAll`` has none);
      otherwise, and for the permanent side always, its ``target`` decides via
      :func:`_damage_target_reaches` (ADR-0038 W6 endgame: a multi-target "any
      number of target creatures and/or players" burn spell — Firestorm, Meteor
      Blast, Comet Storm — and a "deals N damage to each of your opponents"
      ability with no fixed permanent-type restriction — Aurelia, the Law Above,
      Chandra planeswalkers — both serialize their recipient into ``target``
      rather than ``player_filter``; Pyroclasm's own
      ``target=Typed(type_filters=['Creature'])`` reaches only permanents).
      Full-corpus scan at W6: 253 commander-legal ``DamageAll`` nodes with no
      ``player_filter``, 238 creature-typed sweeps, 15 player-reaching.
    * ``DealDamage`` defers to :func:`_damage_target_reaches` on its ``target``
      (no reach when absent). ``root`` — the enclosing ability unit's node, when
      the caller has it — resolves a bare ``ParentTarget`` recipient (see that
      function's docstring); omitting it is conservative (never reaches).
    * ``EachSourceDealsDamage``: ``EachController`` (each source hits its own
      controller) is a player, ``OtherBatchSource`` (another creature in the
      batch) a permanent; any other recipient defers to the target read.
    """
    player = recipient == "player"
    t = tag_of(node)
    if t == "DamageEachPlayer":
        return player
    if t in ("DamageAll", "DealDamage"):
        if (
            player
            and t == "DamageAll"
            and _present(getattr(node, "player_filter", MISSING))
        ):
            return True
        tgt = getattr(node, "target", MISSING)
        return _present(tgt) and _damage_target_reaches(tgt, root, recipient)
    if t == "EachSourceDealsDamage":
        rec = damage_recipient(node)
        if rec is None:
            return False
        if tag_of(rec) == "EachController":
            return player
        if tag_of(rec) == "OtherBatchSource":
            return not player
        return _damage_target_reaches(rec, root, recipient)
    return False


def effect_reaches_player(node: TypedMirrorNode, root: object | None = None) -> bool:
    """Whether a damage EFFECT reaches a PLAYER (CR 120.1) — the direct-damage /
    burn gate: a creature-only bite ("4 damage to target creature" — Flame Slash;
    "2 to each creature" — Pyroclasm) is removal, not burn. See
    :func:`_effect_reaches`."""
    return _effect_reaches(node, root, "player")


def effect_reaches_permanent(node: TypedMirrorNode, root: object | None = None) -> bool:
    """Whether a damage EFFECT can reach a PERMANENT — a battle, creature or
    planeswalker (CR 120.1) — the removal half of a damage effect: "any target"
    (CR 115.4 — Lightning Bolt), a creature / planeswalker bite, a sweep, as
    against damage that only ever reaches a player ("each opponent" —
    Guttersnipe; "that player" — Mogis; "that creature's controller" —
    Repercussion), which makes that player lose life (CR 120.3a) and removes
    nothing. See :func:`_effect_reaches`."""
    return _effect_reaches(node, root, "permanent")


def _damage_target_reaches(
    tgt: object, root: object | None, recipient: DamageRecipient
) -> bool:
    """Whether a damage TARGET node names a recipient that can be RECIPIENT
    (CR 120.1 / 115.4), recursing through an ``Or`` alternation — the one target
    read :func:`effect_reaches_player` and :func:`effect_reaches_permanent` share.

    * ``Typed`` with a NON-EMPTY ``type_filters`` is a creature/permanent/
      battle-typed bite ("target creature" — Flame Slash; "target attacking
      creature" — Femeref Archers): it reaches a permanent, and a player only
      when the words include "Player" explicitly. An EMPTY ``type_filters``
      carries NO card-type restriction at all — phase uses this bare shape both
      for a controller-scoped player ("target opponent" — controller='Opponent';
      Lava Axe's sibling Aragorn, the Uniter) and for a fully unrestricted
      recipient ("any other target" — Self-Destruct, Screaming Nemesis;
      controller=None). Both reach a player; only the unrestricted one reaches a
      permanent.
    * ``Any`` / ``Target`` (bare "any target") reach both.
    * ``SourceChosenPlayer`` / ``TriggeringPlayer`` chosen/triggering player
      forms (CR 120.1), ``ScopedPlayer`` ("that player" — a per-player-loop
      back-reference, Ancient Runes "each player's upkeep ... deals damage to
      that player"), ``ParentTargetController`` ("that creature's/permanent's/
      land's controller" — a controller is always a player, CR 102.1; Ankh of
      Mishra, Backfire), and ``DefendingPlayer`` ("defending player" — the
      attacked player, CR 506.2; Falkenrath Perforator) are bare zero-field
      player-designator marker tags: a player, never a permanent. A bare
      ``Controller`` (the SOURCE's OWN controller — "deals 2 damage to you",
      Voltaic Visionary) stays the incidental SELF-damage exclusion
      (``_scope_from_player_node`` maps it "you", excluded below) — distinct
      from ``ParentTargetController``, which names a DIFFERENT (targeted/
      tracked) object's controller.
    * ``ParentTarget`` (bare — no ``Controller`` suffix) is POSITION-relative
      (the ADR-0038 boundary lesson): it binds to whatever EARLIER clause in the
      SAME ability produced the target, so the tag is ambiguous read alone. A
      modal "instead" amendment clause that re-quotes an earlier "target
      creature" (Fiery Impulse "deals 2 damage to target creature. ... it deals
      3 damage instead", Thermal Blast, Unholy Heat — pure creature removal)
      carries the SAME ``ParentTarget`` tag as a genuine player back-reference
      (Aggressive Sabotage's "Target player discards two cards. If this spell
      was kicked, it deals 3 damage to that player."; Curse of Shaken Faith's
      "Enchant player" + "... deals 2 damage to them"), and as Comet Storm's
      "Choose any target … deals X damage to each of them". When ``root`` (the
      enclosing ability unit) is supplied, resolve it by asking whether that
      SAME ability establishes an explicit (non-``ParentTarget``) RECIPIENT
      target anywhere else (:func:`_unit_has_target`) — the producer a genuine
      back-reference binds to. With no ``root``, conservative: never reaches
      (matches every corpus member that DOESN'T need it — the creature-removal
      modal tail above).
    * ``Or`` recurses into each alternative filter ("target player or
      planeswalker" — Lava Axe's post-2020 template, CR 115.4): the whole
      target reaches iff ANY alternative does.
    """
    player = recipient == "player"
    tt = tag_of(tgt)
    if tt == "Typed":
        words = _filter_type_words(tgt)
        if words:
            # creature/permanent typed → removal; "Player" → a player
            return ("Player" in words) if player else any(map(_damageable_word, words))
        # no type restriction: a player either way; a permanent only unrestricted
        return player or getattr(tgt, "controller", None) is None
    if tt in ("Any", "Target"):
        return True
    if tt == "AttackedPlayerOrPlaneswalker":
        # "the player or planeswalker it's attacking" (Hellrider, Myr
        # Battlesphere): whichever the creature attacks (CR 508.1b), the
        # recipient its combat damage has anyway. It reaches a player; as the
        # removal half (``effect_reaches_permanent``) it reaches no permanent:
        # the card picks none, it hits what the attack already does.
        return player
    if tt in _CHOSEN_PLAYER_TARGETS or tt in (
        "ScopedPlayer",
        "ParentTargetController",
        "EventTargetController",
        "DefendingPlayer",
    ):
        return player
    if tt == "Or":
        return any(
            _damage_target_reaches(f, root, recipient)
            for f in (getattr(tgt, "filters", None) or ())
        )
    if tt in PLAYER_BACK_REFERENCES:
        # Deliberately excluded from the generic ``_scope_from_player_node``
        # fallback: that helper maps bare ``ParentTarget`` to scope "any"
        # for OTHER lanes' purposes (a chosen/targeted-object read), which
        # would silently readmit the position-relative over-fire documented
        # in the docstring. Resolved via sibling context when available; conservative
        # (no reach) otherwise.
        return root is not None and _unit_has_target(root, recipient)
    if not player:
        return False
    sc = _scope_from_player_node(tgt)  # a direct player node
    return sc in ("opponents", "each", "any")


#: The subtypes of the permanent types damage can be dealt to (CR 120.1; CR
#: 205.3m creature, 205.3j planeswalker and 205.3q battle types), lowercased.
_DAMAGEABLE_SUBTYPES: frozenset[str] = (
    CREATURE_TYPES | PLANESWALKER_TYPES | BATTLE_TYPES
)


def _damageable_word(word: str) -> bool:
    """Whether a filter type word names a permanent damage can be dealt to (CR
    120.1: "battles, creatures, planeswalkers, and players") — one of those
    types, phase's generic ``Permanent``, or one of their subtypes ("target
    Goblin"). A land, artifact or enchantment word alone names none: Monsoon's
    "tap all untapped Islands that player controls" chain, whose "deals X damage
    to the player" phase binds back to the Islands, deals no damage to a land."""
    return word in DAMAGE_PERMANENT_TYPES or word.lower() in _DAMAGEABLE_SUBTYPES


# Player-reference target tags that name a specific chosen / triggering player —
# a valid direct-damage recipient (CR 120.1) though not a fixed-scope node.
_CHOSEN_PLAYER_TARGETS: frozenset[str] = frozenset(
    {"SourceChosenPlayer", "TriggeringPlayer"}
)


def _unit_has_target(root: object, recipient: DamageRecipient) -> bool:
    """Whether ability ``root`` establishes an explicit (non-``ParentTarget``)
    RECIPIENT-reaching TARGET anywhere in its own structure — the producer a bare
    ``ParentTarget`` damage recipient can legitimately bind back to within the
    SAME ability (a player: Aggressive Sabotage's "Target player discards two
    cards. If this spell was kicked, it deals 3 damage to that player."; Blood
    Oath's "Target opponent reveals their hand. ... deals 3 damage to that player
    ..."; a permanent: Comet Storm's "Choose any target"). Scans every
    ``_SCOPE_FIELDS`` slot on every typed node reachable under ``root``
    (:func:`_iter_typed_nodes`) — cost/target/static fields alike, since the
    producer can be a non-damage effect (Discard, RevealHand) or the ability's
    own enchant/attach target.

    ADR-0039 W7 (the player side only): also recognizes a bare ``optional_for``
    STRING marker ("AnyOpponent" / "AnyPlayer") a sibling node carries — phase's
    "may have you <effect>" optional-choice shape (Sin Prodder's "Any opponent
    may have you put that card into your graveyard. If a player does, ~ deals
    damage to that player...") names the CHOOSING player only as this raw
    string, never a typed player node, so it never populates any
    ``_SCOPE_FIELDS`` slot. Corpus-verified: 26 commander-legal nodes carry
    ``optional_for`` (18 ``AnyPlayer`` / 8 ``AnyOpponent``), and Sin Prodder is
    the ONLY one whose ``direct_damage`` membership actually turns on this read
    — every other hit is already served via its own explicit typed target. A
    bare string always names a player (never a creature/permanent).
    """
    for n in _iter_typed_nodes(root):
        for fname in _SCOPE_FIELDS:
            sub = getattr(n, fname, MISSING)
            if (
                _present(sub)
                and tag_of(sub) not in PLAYER_BACK_REFERENCES
                and _damage_target_reaches(sub, None, recipient)
            ):
                return True
        if recipient == "player":
            opt = getattr(n, "optional_for", MISSING)
            if _present(opt) and opt in _OPTIONAL_FOR_PLAYER_VALUES:
                return True
    return False


# The two observed string values of a bare ``optional_for`` marker (a raw
# str field, never a typed player node) — both always name a player.
_OPTIONAL_FOR_PLAYER_VALUES = frozenset({"AnyOpponent", "AnyPlayer"})


def has_nested_damage_reaching(
    node: object,
    recipient: DamageRecipient,
    *,
    tags: frozenset[str] = DAMAGE_EFFECT_TAGS,
) -> bool:
    """Whether a damage node (one of TAGS) that can reach RECIPIENT (CR 120.1)
    is reachable ANYWHERE under ``node`` — a damage effect buried inside a
    granted activated/static ability's ``GrantAbility``/``GrantStaticAbility``
    ``.definition`` (Barbed Field's "Enchanted land has '{T}: ... deals 1
    damage to any target.'", Acidic Sliver's lord-granted "All Slivers have
    '{2}, Sacrifice ...: ... deals 2 damage to any target.'"), a
    ``CreateToken`` token-ability definition (Dance with Devils's "When this
    token dies, it deals 1 damage to any target") or a coin-flip / modal
    branch (Goblin Bangchuckers) — none of which the flat per-unit
    ``effect_concepts`` walk ever surfaces as its own top-level concept. The
    :func:`has_nested_fight` sibling. ``node`` doubles as the ``root``
    :func:`_effect_reaches` resolves a bare ``ParentTarget`` recipient against
    (the SAME ability owns both the grant and its nested damage).
    """
    return any(
        tag_of(n) in tags and _effect_reaches(n, node, recipient)
        for n in _iter_typed_nodes(node)
    )


def has_nested_damage_reaching_player(node: object) -> bool:
    """:func:`has_nested_damage_reaching` a PLAYER — the ``direct_damage``
    lane's structural fallback."""
    return has_nested_damage_reaching(node, "player")


def _type_filter_words(entries: object) -> list[str]:
    """Flatten one ``type_filters`` list to plain positive type words.

    Handles each entry kind: a bare ``str`` (``"Creature"``); a ``{Subtype: X}``
    wrapper (surfaced as ``X``); a ``{AnyOf: [...]}`` disjunction (recursed, so an
    "Assassin, Mercenary, … you control dies" — Rakish Crew — surfaces its inner
    creature subtypes, parallel to the ``Or`` recursion below); and a ``{Non: X}``
    NEGATION (CR 207.2c type words / 400.7), whose inner word is DROPPED — never
    flattened to the positive it negates (the reanimator-on-Astelli-Reclaimer,
    landfall-on-Brainstealer-Dragon / Builder's-Talent over-fires all stemmed from
    flattening ``{Non: Land}`` / ``{Non: Creature}`` to the positive type word).
    """
    out: list[str] = []
    if not isinstance(entries, (list, tuple)):
        return out
    for tf in entries:
        if isinstance(tf, str):
            out.append(tf)
        elif isinstance(tf, MirrorVariant):
            if tf.key == "Non":
                continue  # negation — drop the inner word
            if tf.key == "AnyOf" and isinstance(tf.inner, list):
                out.extend(_type_filter_words(tf.inner))  # disjunction — recurse
                continue
            inner = tf.inner
            out.append(inner if isinstance(inner, str) else tf.key)
    return out


def _filter_type_words(filt: object) -> tuple[str, ...]:
    """Flatten a typed filter's ``type_filters`` (str / ``{Subtype: X}`` / ``{AnyOf:
    [...]}`` / ``{Non: X}``) words.

    Recurses through ``Or`` / ``And`` filter nodes so a dual ``Creature``+``Land``
    or a ``{Subtype: Goblin}`` is surfaced as plain strings — the type-membership
    granularity reads these, not oracle text. Per-entry handling (Subtype / AnyOf /
    Non) lives in :func:`_type_filter_words`.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        out.extend(_type_filter_words(getattr(filt, "type_filters", ())))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(_filter_type_words(sub))
    return tuple(out)


def _effect_subject(node: TypedMirrorNode) -> tuple[str, ...]:
    """The type/subtype words an effect names (its filter or token types).

    A ``Token`` effect carries the token's ``types`` directly; other effects carry
    a ``subject`` / ``filter`` / ``target`` typed filter. Empty when none.
    """
    types = getattr(node, "types", MISSING)
    if _present(types) and isinstance(types, list):
        return tuple(t for t in types if isinstance(t, str))
    for fname in ("subject", "filter", "target", "affected"):
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            words = _filter_type_words(sub)
            if words:
                return words
    return ()


def _node_raw(node: TypedMirrorNode) -> str:
    """A grounding clause for a node — its ``description`` if present, else ``""``.

    Not identity-bearing (the diff keys on key/scope/subject); kept so a lane can
    surface a human-readable quote.
    """
    desc = getattr(node, "description", MISSING)
    return desc if isinstance(desc, str) else ""


# ── trigger-event derivation (provenance: phase ``mode`` + zone/recipient) ─────


#: The derived trigger events that fire as a permanent enters (CR 603.6a: "When
#: [this object] enters, ..." / "Whenever a [type] enters, ..."): a plain enters
#: event, and the compound ``entersorattacks`` ("Whenever this creature enters or
#: attacks" -- its enters event is an ETB per 603.6a).
ENTERS_EVENTS: frozenset[str] = frozenset({"enters", "entersorattacks"})


def trigger_def_event(trig: TypedMirrorNode) -> str:
    """Derive a normalized trigger event from a phase trigger DEFINITION's typed
    shape — the spelling ``AbilityUnit.trigger_event`` carries for a unit's own
    trigger, read here for any definition (a granted or a delayed one too).

    Reads ``mode`` (a string discriminator) plus ``destination`` / ``origin`` for
    the overloaded ``ChangesZone`` mode — never oracle text.
    """
    mode = getattr(trig, "mode", None)
    mode = mode if isinstance(mode, str) else tag_of(mode) or "other"
    # ``ChangesZoneAll`` is the mass form of the same watcher ("whenever one
    # or more … are put into …" — The Gitrog Monster's land-dies trigger);
    # the zone derivation is identical (CR 603.6c).
    if mode in ("ChangesZone", "ChangesZoneAll"):
        dest = getattr(trig, "destination", None)
        origin = getattr(trig, "origin", None)
        if dest == "Battlefield":
            return "enters"
        if dest == "Graveyard" and origin in ("Battlefield", None):
            return "dies"
        return "changes_zone"
    return {
        "Drawn": "drawn",
        "Discarded": "discarded",
        # CR 702.29a: cycling IS "[Cost], Discard this card: Draw a card" —
        # a cycle is a discard, so the combined mode joins the discard event
        # (Archfiend of Ifnir); ``DiscardedAll`` is the mass watcher.
        "CycledOrDiscarded": "discarded",
        "DiscardedAll": "discarded",
        "LeavesBattlefield": "leaves",  # CR 603.6c — broader than dies
        "Explored": "explored",  # CR 701.44 — the explore PAYOFF watcher
        "RolledDie": "rolled_die",  # CR 706 — the roll PAYOFF watcher
        "RolledDieOnce": "rolled_die",
        "Attacks": "attacks",
        "YouAttack": "attacks",
        "SpellCast": "cast_spell",
        "DamageDone": "deals_damage",
        # CR 510.1b batched form — "whenever one or more [creatures you
        # control] deal (combat) damage to …" (Anowon, the Ruin Thief). Same
        # valid_target / valid_source / damage_kind shape as ``DamageDone``;
        # the live path fires the same combat-connect lanes on it (b10
        # follow-up d).
        "DamageDoneOnceByController": "deals_damage",
        "DamageReceived": "damage_received",  # the "is dealt damage" reflector
        "CounterAdded": "counter_added",
        "LifeGained": "life_gained",
        "LifeLost": "life_lost",  # lifeloss_matters (CR 119.3)
        "Taps": "taps",
        "Sacrificed": "sacrificed",
        "Exploited": "exploited",  # CR 702.110 — exploit IS a sacrifice payoff
        "BecomesTarget": "becomes_target",
        "BecomesBlocked": "becomes_blocked",
        "Blocks": "blocks",
    }.get(mode, mode.lower())


def trigger_zone_changes(trig: object) -> tuple[tuple[str | None, str | None], ...]:
    """The ``(origin, destination)`` of each zone change a ``ChangesZone`` trigger
    watches. Phase v0.104.0 folds "whenever a creature dies or a creature card is
    put into a graveyard from a library" (Dreadhound) into one trigger whose
    ``zone_change_clauses`` each carry an origin predicate: ``Equals`` names the
    zone; ``NotEquals`` / ``OneOf`` ("from anywhere other than the battlefield")
    read as an unrestricted ``None``, phase's own shape for "from anywhere". A
    single-move trigger is its own ``origin`` / ``destination``."""
    clauses = getattr(trig, "zone_change_clauses", MISSING)
    if not (_present(clauses) and isinstance(clauses, list) and clauses):
        return ((getattr(trig, "origin", None), getattr(trig, "destination", None)),)
    out: list[tuple[str | None, str | None]] = []
    for clause in clauses:
        pred = getattr(clause, "origin", None)
        origin = getattr(pred, "data", None) if tag_of(pred) == "Equals" else None
        dest = getattr(clause, "destination", None)
        out.append(
            (
                origin if isinstance(origin, str) else None,
                dest if isinstance(dest, str) else None,
            )
        )
    return tuple(out)


def trigger_scope(trig: TypedMirrorNode) -> str:
    """The scope a trigger watches (you/opponents/each) from its recipient field.

    For a player-event trigger (Drawn / Discarded / …) phase carries the watched
    player on ``valid_target``; ``you`` is the default when unmarked.
    """
    vt = getattr(trig, "valid_target", MISSING)
    if _present(vt):
        sc = _scope_from_player_node(vt)
        if sc is not None:
            return sc
    return "you"


def _names_itself(filt: object, *, among_others: bool) -> bool:
    tag = tag_of(filt)
    if among_others and tag in ("Or", "And"):
        return any(
            _names_itself(f, among_others=True)
            for f in getattr(filt, "filters", ()) or ()
        )
    return tag == "SelfRef"


def watches_itself(trig: object, *, among_others: bool = False) -> bool:
    """Whether a trigger or replacement watches the card itself: its
    ``valid_card`` is ``SelfRef`` ("When ~ dies"), or — ``among_others`` — a
    ``SelfRef`` branch of an ``Or`` / ``And`` beside other objects (Forgeborn
    Phoenix's "Whenever ~ or equipped creature dies"). Without ``among_others``
    a shared watcher (Blood Artist's "~ or another creature") doesn't count."""
    return _names_itself(getattr(trig, "valid_card", None), among_others=among_others)


def trigger_subject(trig: TypedMirrorNode) -> tuple[str, ...]:
    """Type-words of the OBJECT a trigger watches (its ``valid_card`` filter).

    Parallel to :func:`trigger_scope` (which reads the watched *player*): the
    death/landfall/token-ETB lanes need the watched OBJECT's types — "a creature
    dies", "a land you control enters", "a token you control enters". A bare
    ``SelfRef`` (When THIS dies) yields ``()`` so the self-death payoff stays out of
    the aristocrats lane. Recurses ``Or`` / ``And`` (Blood Artist's "this or another
    creature") so the real creature filter surfaces past the SelfRef arm.
    """
    vc = getattr(trig, "valid_card", MISSING)
    return _filter_type_words(vc) if _present(vc) else ()


def trigger_subject_scope(trig: TypedMirrorNode) -> str:
    """The watched OBJECT's controller scope (you/opponents/any) for a trigger.

    Reads ``valid_card``'s ``controller`` (a creature-you-control death vs an
    opponent's creature vs the symmetric any). An ``Or``/``And`` (Blood Artist —
    SelfRef OR another creature) or an unscoped filter is "any". Mirrors the old
    projection's ``trig.scope`` for the death lane (You→you, Opponent→opponents,
    null/mixed→any).
    """
    vc = getattr(trig, "valid_card", MISSING)
    if _present(vc):
        t = tag_of(vc)
        if t == "Typed":
            ctrl = getattr(vc, "controller", None)
            if ctrl == "You":
                return "you"
            if ctrl == "Opponent":
                return "opponents"
    return "any"


def filter_predicates(filt: object) -> tuple[str, ...]:
    """The PREDICATE tags of a typed filter (``Token`` / ``Counters`` / ``Tapped`` /
    ``Attacking`` / ``Another`` / ``NonToken`` …), read off its ``properties`` list.

    Distinct from :func:`_filter_type_words` (which flattens ``type_filters`` —
    Creature / Land): the token / go-wide lanes gate on the *property* a filter
    carries, not its card type ("Creature tokens you control", "creatures with a
    +1/+1 counter"). Recurses ``Or`` / ``And`` like the type-word read. Generic and
    reusable (the Tapped / Attacking / Counters predicates land here for later
    batches).
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            pt = tag_of(prop)
            if pt == "AttachedTo":
                # ``AttachedTo{to}`` names what the object is attached to
                # (Champion of the Flame's
                # "each Aura and Equipment attached to it"): the predicate keeps
                # its per-object name — ``AttachedTo`` + the ``to`` tag (new
                # objects: ``Host``, ``DeclaredTarget``).
                pt = "AttachedTo" + (tag_of(getattr(prop, "to", None)) or "")
            if pt is not None:
                out.append(pt)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_predicates(sub))
    return tuple(out)


def filter_without_keywords(filt: object) -> tuple[str, ...]:
    """The keyword names a typed filter EXCLUDES via ``WithoutKeyword``
    properties ("creature without flanking" — the flanking template's blocker
    filter, CR 702.25a). The value-level companion to
    :func:`filter_predicates`, which returns only the property TAGS. Recurses
    ``Or`` / ``And`` like the other filter reads.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "WithoutKeyword":
                v = getattr(prop, "value", None)
                if isinstance(v, str):
                    out.append(v)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_without_keywords(sub))
    return tuple(out)


def filter_keywords(filt: object) -> tuple[str, ...]:
    """The ability-keyword names a typed filter REQUIRES via ``WithKeyword``
    properties ("creatures you control with flying" → ``("Flying",)``; the
    keyword-tribe payoff population, CR 109.3 / 702). The mirror of
    :func:`filter_without_keywords` (which reads the ``WithoutKeyword``
    exclusion side). Recurses ``Or`` / ``And`` like the other filter reads.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "WithKeyword":
                v = getattr(prop, "value", None)
                if isinstance(v, str):
                    out.append(v)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_keywords(sub))
    return tuple(out)


def effect_filter(node: TypedMirrorNode) -> object | None:
    """The typed FILTER node an effect names (``subject`` / ``filter`` / ``target`` /
    ``affected``), or ``None``.

    Distinct from :func:`_effect_subject` (which flattens a filter to plain type
    words and special-cases a token's ``types`` list): the type-payoff / predicate
    lanes need the filter NODE itself to read its controller, core-vs-subtype split,
    and predicates (:func:`filter_controller` / :func:`filter_core_types` /
    :func:`filter_subtypes` / :func:`filter_predicates`).
    """
    for fname in ("subject", "filter", "target", "affected"):
        sub = getattr(node, fname, MISSING)
        if _present(sub):
            return sub
    return None


def count_operand_filter(node: TypedMirrorNode) -> object | None:
    """The FILTER of an effect's dynamic count operand (``Ref`` → ``ObjectCount``).

    A scaling value ("draw a card for each artifact you control" — Inspiring Call;
    "+X/+X where X is the number of creatures you control" — Craterhoof) carries the
    counted population on ``amount`` / ``count`` / ``value`` as a ``Ref`` whose
    ``qty`` is an ``ObjectCount`` with a ``filter``. The type/counter-matters lanes
    read that counted set's filter — the operand the old projection dropped.
    ``announced_x`` joins the field list at phase v0.35.2: an announce-locked X
    (CR 601.2b / 602.2b, the v0.25.0 channel) moves the computed operand off
    ``amount`` (now a bare ``Variable`` Ref) onto its own field.
    """
    for fname in ("amount", "count", "value", "announced_x"):
        q = getattr(node, fname, MISSING)
        if not _present(q) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                return filt
    return None


def count_distinct_operand_filter(node: TypedMirrorNode) -> object | None:
    """The FILTER of a DISTINCT-count operand (``Ref`` → ``ObjectCountDistinct``).

    The sibling of :func:`count_operand_filter` for the "for each **differently
    named** ~ you control" scaler (Audience with Trostani — draw = the number of
    differently-named creature tokens you control). phase carries the counted
    population on the same ``amount`` / ``count`` / ``value`` ``Ref`` but under an
    ``ObjectCountDistinct`` qty (a distinct ``qualities`` dimension). Kept a SEPARATE
    helper so widening it never moves the lanes that read the plain ObjectCount form.
    """
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if not _present(q) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCountDistinct":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                return filt
    return None


def filter_controller(filt: object, unit: AbilityUnit | None = None) -> str | None:
    """The phase ``controller`` of a typed filter (``"You"`` / ``"Opponent"`` /
    ``None``), recursing ``Or`` / ``And`` to the first that names one. A chosen
    player's permanents ("Choose an opponent. That player sacrifices a creature"
    — Myrkul's Edict's d20 row) carry a variant controller, read as its key
    (``"ChosenPlayer"``), never as unset. Given the filter's ``unit``, a
    controller the overlay corrections re-read wins (:data:`ANAPHORIC` for
    Delirium's "that player controls", which phase stamps ``You``).
    """
    t = tag_of(filt)
    if t == "Typed":
        fc = unit.correction(filt, "controller") if unit is not None else None
        c = fc.value if fc is not None else getattr(filt, "controller", None)
        if isinstance(c, MirrorVariant):
            return c.key
        return c if isinstance(c, str) else None
    if t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            c = filter_controller(sub, unit)
            if c is not None:
                return c
    return None


def filter_owners(filt: object) -> list[str | None]:
    """The owner each part of a graveyard filter names — its ``Owned`` property,
    else its controller — one per ``Or`` / ``And`` arm ("… from your graveyard and
    … from an opponent's graveyard" — Spelltwine), ``None`` where an arm names
    none."""
    parts = getattr(filt, "filters", None) if tag_of(filt) in ("Or", "And") else None
    return [
        filter_owned_controller(p) or filter_controller(p) for p in (parts or (filt,))
    ]


#: Filter predicates naming the one object an Equipment or Aura is attached to:
#: "equipped creature" (CR 301.5a), "enchanted creature" (an Aura is attached
#: to one object, CR 303.4).
ATTACHED_OBJECT_PREDICATES: frozenset[str] = frozenset({"EquippedBy", "EnchantedBy"})


def names_attached_object(filt: object) -> bool:
    """Whether a filter is the object its Equipment or Aura is attached to
    (:data:`ATTACHED_OBJECT_PREDICATES`) — one creature, never a population. An
    ``And`` is when any member is (the intersection is that one object); an
    ``Or`` only when every member is ("enchanted creature or each creature that
    shares a type with it" is a population)."""
    tag = tag_of(filt)
    if tag in ("Or", "And"):
        parts = getattr(filt, "filters", None) or ()
        test = all if tag == "Or" else any
        return bool(parts) and test(names_attached_object(p) for p in parts)
    return not ATTACHED_OBJECT_PREDICATES.isdisjoint(filter_predicates(filt))


def static_affected(sdef: object, unit: AbilityUnit | None = None) -> object:
    """A static def's ``affected`` set — the one the overlay corrections re-read
    when its ``unit`` carries one (Tsabo's Web's "each land …" phase stamps
    ``SelfRef``): a filter node or a tag string."""
    if unit is not None:
        return unit.corrected(sdef, "affected")
    return getattr(sdef, "affected", None)


def affected_tag(sdef: object, unit: AbilityUnit | None = None) -> str | None:
    """The tag of :func:`static_affected` (a corrected tag string as is)."""
    value = static_affected(sdef, unit)
    return value if isinstance(value, str) else tag_of(value)


def corrected_scope(cnode: ConceptNode) -> str | None:
    """The ``scope`` an overlay stage re-read for an effect concept, or ``None``
    when the scope is the substrate's own derivation from the node's recipient
    (:func:`_effect_scope`) — so a reader can honour a correction without
    mistaking the substrate's default for one (Skullsnatcher's ownerless "from
    that player's graveyard" exile: substrate ``each``, corrected
    ``opponents``)."""
    return None if cnode.scope == _effect_scope(cnode.node) else cnode.scope


def targets_the_card(cnode: ConceptNode) -> bool:
    """Whether an effect concept's target is the card itself: phase's ``SelfRef``,
    unless the overlay corrections marked it the object an earlier clause named
    (:data:`ANAPHORIC` — Jace, Architect of Thought's "whenever a creature an
    opponent controls attacks, it gets -1/-0")."""
    return (
        tag_of(getattr(cnode.node, "target", None)) == "SelfRef"
        and ANAPHORIC not in cnode.subject
    )


def _fixed_cmc(prop: object) -> tuple[str, int] | None:
    """A ``Cmc`` filter property's ``(comparator, value)`` when the value is a
    fixed number (``"GE"``, 5 — "mana value 5 or greater"), else ``None`` (X, a
    chosen number)."""
    if tag_of(prop) != "Cmc":
        return None
    value = getattr(prop, "value", None)
    n = getattr(value, "value", None) if tag_of(value) == "Fixed" else None
    comparator = getattr(prop, "comparator", None)
    if not isinstance(n, int) or not isinstance(comparator, str):
        return None
    return comparator, n


def filter_mana_value_floor(filt: object) -> int | None:
    """The lowest mana value a typed filter admits, from its ``Cmc`` ``GE`` / ``GT``
    predicates ("target creature or planeswalker with mana value 3 or greater" —
    Your Fate Ends Here → 3), or ``None`` when it sets no floor. An ``Or`` floors
    at its lowest arm (any arm without a floor → ``None``); an ``And`` at its
    highest. A ceiling (``LE`` — Solitary Cell's "3 or less") is not a floor."""
    t = tag_of(filt)
    if t == "Typed":
        floors: list[int] = []
        for prop in getattr(filt, "properties", ()) or ():
            bound = _fixed_cmc(prop)
            if bound is None:
                continue
            comparator, n = bound
            if comparator == "GE":
                floors.append(n)
            elif comparator == "GT":
                floors.append(n + 1)
        return max(floors) if floors else None
    if t in ("Or", "And"):
        arms = [filter_mana_value_floor(s) for s in getattr(filt, "filters", ()) or ()]
        if not arms:
            return None
        if t == "Or":
            return None if None in arms else min(a for a in arms if a is not None)
        present = [a for a in arms if a is not None]
        return max(present) if present else None
    return None


def or_arms(filt: object) -> tuple[object, ...]:
    """An ``Or`` filter's member filters (none for an empty one); any other
    filter, ``None`` included, as its one arm. One level: a nested ``Or`` is
    one arm."""
    if tag_of(filt) == "Or":
        return tuple(getattr(filt, "filters", None) or ())
    return (filt,)


def filter_core_types(filt: object) -> tuple[str, ...]:
    """The CORE card-type words of a typed filter (bare strings — ``Creature`` /
    ``Artifact`` / ``Permanent``), EXCLUDING subtype / ``Non`` / ``AnyOf`` wrappers.

    The complement of :func:`filter_subtypes`. The generic-board / type-matters gates
    read core types (no subtype) — a ``{Subtype: Equipment}`` entry is NOT a core
    type. Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, str):
                out.append(tf)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_core_types(sub))
    return tuple(out)


def filter_subtypes(filt: object) -> tuple[str, ...]:
    """The SUBTYPE words of a typed filter (``{Subtype: Equipment}`` → ``Equipment``;
    ``{AnyOf: [...]}`` recursed), EXCLUDING bare core types and ``Non`` negations.

    The voltron / tribal gates read subtypes; the generic-board gate requires the
    subtype set EMPTY. Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, MirrorVariant):
                if tf.key == "Subtype":
                    inner = tf.inner
                    out.append(inner if isinstance(inner, str) else tf.key)
                elif tf.key == "AnyOf" and isinstance(tf.inner, list):
                    for e in tf.inner:
                        if isinstance(e, MirrorVariant) and e.key == "Subtype":
                            out.append(e.inner if isinstance(e.inner, str) else e.key)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_subtypes(sub))
    return tuple(out)


def named_filter_subtypes(root: object) -> frozenset[str]:
    """The lowercased subtypes named by the filters under ``root`` (a unit node)
    that no ``Sacrifice`` consumes and no opponent controls (an ``Opponent`` or
    ``DefendingPlayer`` controller — the defending player is the one attacked,
    CR 506.2: Bloodvial Purveyor's "for each Blood token defending player
    controls" counts an opponent's tokens) — the token kinds a
    card counts, watches or grants to ("for each Clue you control", "Clues you
    control have exalted", "whenever you sacrifice a Food"'s watched subject).
    A sacrificed filter is left to the caller's sacrifice read, which knows who
    pays. One pass over the unit, memoized on the node."""
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_NAMED_FILTER_SUBTYPES_ATTR)
        if cached is not None:
            return cached
    typed: list[TypedMirrorNode] = []
    consumed: set[int] = set()
    for n in iter_typed_nodes(root):
        tag = tag_of(n)
        if tag == "Typed":
            typed.append(n)
        elif tag == "Sacrifice":
            consumed.update(map(id, iter_typed_nodes(getattr(n, "target", None))))
    out = frozenset(
        st.lower()
        for n in typed
        if id(n) not in consumed and filter_controller_side(n) != "opponents"
        for st in filter_subtypes(n)
    )
    if isinstance(root, TypedMirrorNode):
        object.__setattr__(root, _NAMED_FILTER_SUBTYPES_ATTR, out)
    return out


_NAMED_FILTER_SUBTYPES_ATTR = "_xw_named_filter_subtypes"


def counter_pred_kinds(filt: object) -> tuple[str, ...]:
    """The counter KINDS a filter's ``Counters`` predicates reference (``"P1P1"`` /
    ``"M1M1"`` / ``"Any"`` …), EXCLUDING the ``EQ 0`` "with NO counter" inverse.

    Mirrors the legacy regex engine's counter-kind read over the typed
    predicate: a ``Counters`` property carries ``comparator`` + ``count`` + ``counters``
    (``{OfType: <kind>}`` for a named kind, else the kind-agnostic "any counter"
    form → ``"Any"``). The +1/+1 / -1/-1 / any-counter payoff lanes route by kind.
    Recurses ``Or`` / ``And``.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "Counters":
                continue
            cmp_ = getattr(prop, "comparator", None)
            cnt = getattr(prop, "count", None)
            val = getattr(cnt, "value", None) if cnt is not None else None
            if cmp_ == "EQ" and val == 0:
                continue  # "with NO counter" — the inverse, not a payoff
            counters = getattr(prop, "counters", None)
            if tag_of(counters) == "OfType":
                data = getattr(counters, "data", None)
                out.append(data if isinstance(data, str) else "Any")
            else:
                out.append("Any")
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(counter_pred_kinds(sub))
    return tuple(out)


def _counter_kind_refs(root: object, kind: str) -> tuple[str, ...]:
    """Every ``kind`` counter reference reachable ANYWHERE under ``root``
    (deep walk) — the structural-read sibling of :func:`counter_pred_kinds`
    for a counter-kind reference phase buries inside a scaling operand
    (Kuldotha Cackler's ``Pump.power`` Ref->ObjectCount), a cost-reduction
    ``dynamic_count`` (Cinderslash Ravager's ``ModifyCost``), a sub-
    ability's gating ``QuantityCheck`` (Oil-Gorger Troll's conditional
    draw), or an ability's OWN ``condition`` (Armored Scrapgorger / Ichor
    Synthesizer's static "as long as it has N oil counters" self-check;
    the Kamigawa flip cycle's triggered "if there are two or more ki
    counters on ~" self-check — Faithful Squire, Callow Jushi, Hired
    Muscle, Cunning Bandit, Budoka Pupil) — none of which the flat
    per-concept-node walk reaches (that node IS the AddPower/AddToughness
    modification or the trigger's own effect, never the containing
    ability, whose ``condition``/``affected`` fields live one level up).

    Two typed shapes, kind-filtered to ``kind``: a ``Typed`` filter's
    ``Counters`` property (controller-gated — an Opponent-controlled
    filter is excluded, checklist #6), OR a ``HasCounters`` CONDITION
    (always self-referencing to the ability's own permanent, so no
    controller gate applies). CR 122.1.
    """
    out: list[str] = []
    for n in _iter_typed_nodes(root):
        t = tag_of(n)
        if t == "Typed":
            if getattr(n, "controller", None) == "Opponent":
                continue
            out.extend(k for k in counter_pred_kinds(n) if k.lower() == kind)
        elif t == "HasCounters":
            counters = getattr(n, "counters", None)
            if tag_of(counters) == "OfType" and getattr(counters, "data", None) == kind:
                out.append(kind)
    return tuple(out)


def oil_counter_kind_refs(root: object) -> tuple[str, ...]:
    """Every "oil" counter reference reachable ANYWHERE under ``root``
    (deep walk). This key's ADR-0038 batch-2 scope — see
    :func:`_counter_kind_refs` for the shared deep-walk shapes. shield/rad
    stay on :func:`counter_pred_kinds`'s narrower flat read until their own
    corpus measurement widens them; ki has its own
    :func:`ki_counter_kind_refs` sibling (ADR-0039 W8)."""
    return _counter_kind_refs(root, "oil")


def ki_counter_kind_refs(root: object) -> tuple[str, ...]:
    """Every "ki" counter reference reachable ANYWHERE under ``root``
    (deep walk) — the ADR-0039 W8 sibling of :func:`oil_counter_kind_refs`,
    added for the Kamigawa flip cycle's triggered ``HasCounters`` self-check
    ("At the beginning of the end step, if there are two or more ki
    counters on ~, you may flip it." — Faithful Squire, Callow Jushi,
    Hired Muscle, Cunning Bandit, Budoka Pupil), which lives on the
    TRIGGER's own ``condition`` field, one level above the flat
    per-concept-node walk's ``Unimplemented(name='flip')`` effect node.
    CR 122.1."""
    return _counter_kind_refs(root, "ki")


def color_count_preds(filt: object) -> tuple[tuple[str, int], ...]:
    """The ``(comparator, count)`` pairs of a filter's ``ColorCount`` predicates.

    Mirrors the OLD-IR ``ColorCount:<CMP>:<N>`` predicate string (CR 105.2): a
    ``ColorCount`` property carries ``comparator`` (``GE`` / ``EQ`` / …) + ``count``
    (an int). The multicolor (``GE``≥2 / ``EQ``≥2) and colorless (``EQ`` 0)
    build-around lanes route by it. Recurses ``Or`` / ``And``.
    """
    out: list[tuple[str, int]] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "ColorCount":
                continue
            cmp_ = getattr(prop, "comparator", None)
            cnt = getattr(prop, "count", None)
            if isinstance(cmp_, str) and isinstance(cnt, int):
                out.append((cmp_, cnt))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(color_count_preds(sub))
    return tuple(out)


def power_threshold_preds(filt: object) -> tuple[tuple[str, str, int], ...]:
    """The ``(stat, comparator, value)`` triples of a filter's FIXED ``PtComparison``
    predicates (CR 208.1).

    Mirrors the OLD-IR ``PtComparison:Power:GE:4`` predicate string but EXCLUDES the
    dynamic form (the old ``:*`` tail — a relative "power less than this creature's"
    fight-style check, whose ``value`` is a ``Ref``/``Difference``, not a ``Fixed``).
    Only a ``Fixed`` value yields a triple; the high-power (GE/GT) and low-power
    (LE/LT) lanes split on the comparator direction. Recurses ``Or`` / ``And``.
    """
    out: list[tuple[str, str, int]] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) != "PtComparison":
                continue
            val = getattr(prop, "value", None)
            if tag_of(val) != "Fixed":
                continue  # dynamic / relative comparison — not a fixed theme floor
            stat = getattr(prop, "stat", None)
            cmp_ = getattr(prop, "comparator", None)
            v = getattr(val, "value", None)
            if isinstance(stat, str) and isinstance(cmp_, str) and isinstance(v, int):
                out.append((stat, cmp_, v))
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(power_threshold_preds(sub))
    return tuple(out)


def player_counter_kind(node: TypedMirrorNode) -> str:
    """The ``counter_kind`` of a ``GivePlayerCounter`` effect (``"Rad"`` /
    ``"Experience"`` / ``"Poison"`` …), normalized to a string (``""`` when absent).

    A player-resource counter (CR 122.1 / 728) is given to a PLAYER, not placed on a
    permanent — phase carries the kind directly on ``GivePlayerCounter.counter_kind``.
    The rad / experience maker lanes route by it (the OLD lossy IR split the giver
    into per-kind effect categories; this reads the kind off the typed node).
    """
    ck = getattr(node, "counter_kind", MISSING)
    return ck if isinstance(ck, str) else ""


def count_operand_qty(
    node: TypedMirrorNode,
    *,
    fields: tuple[str, ...] = ("amount", "count", "value", "announced_x"),
    wrappers: tuple[str, ...] = ("Multiply",),
) -> object | None:
    """The QTY node of an effect's dynamic count operand, or ``None``.

    Two shapes carry a named scaler (CR 700.5 devotion / 700.6 domain / 700.8 party,
    or a player-counter count): a ``Ref``-wrapped operand on ``amount`` / ``count`` /
    ``value`` (``Ref.qty`` — the same path :func:`count_operand_filter` reads, but
    returning the qty itself rather than its ``ObjectCount`` filter), and a direct
    ``dynamic_count`` on a static P/T modification (``AddDynamicPower`` — "+X/+X where
    X is your devotion"). A scaled multiplier ("-1/-1 for each EACH of N counters" —
    Withering Hex, Toxrill's ``AddDynamicPower(value=Multiply(factor, inner=Ref(qty=
    …)))``) wraps the ``Ref`` one level deeper under ``Multiply.inner``; unwrapped the
    same way (ADR-0038 W3 batch 3). Returns the qty node so a lane can read its
    discriminator tag (:func:`tag_of`) plus its ``controller`` / ``player`` / ``kind``
    fields. ``announced_x`` joins the field list at phase v0.35.2: an
    announce-locked X (CR 601.2b / 602.2b, the v0.25.0 channel) moves the computed
    operand off ``amount`` (now a bare ``Variable`` Ref) onto its own field
    (Monstrous Onslaught's Max-Power Aggregate).

    ``fields`` names the operand fields read (a P/T change reads ``toughness``);
    ``wrappers`` the scalar wrappers stepped through, in order, each at most once:
    a mass shrink's "-X/-X where X is …" is ``Quantity(value=Multiply(-1,
    inner=Ref(…)))``, and Drag to the Bottom's "1 plus" puts an ``Offset`` inside
    that (``("Quantity", "Multiply", "Offset")``).
    """
    for fname in fields:
        q = getattr(node, fname, MISSING)
        if not _present(q):
            continue
        for wrapper in wrappers:
            if tag_of(q) == wrapper:
                q = getattr(q, "value" if wrapper == "Quantity" else "inner", None)
        if tag_of(q) == "Ref":
            qty = getattr(q, "qty", None)
            if isinstance(qty, TypedMirrorNode):
                return qty
    dc = getattr(node, "dynamic_count", MISSING)
    if isinstance(dc, TypedMirrorNode):
        return dc
    return None


def quantity_scope(qty: object) -> str | None:
    """Whose things a count quantity counts, as a Signal scope (``"you"`` /
    ``"opponents"`` / ``"each"`` / ``"any"``), or ``None`` when it names no player
    (a tracked set, the source's own power). An ``ObjectCount`` reads its filter's
    controller (``"each"`` for no controller: every player's); a player-resource
    or zone count its ``player`` / ``controller`` / ``scope`` field or its
    source's (``HandSize.player``, ``BasicLandTypeCount.controller``,
    ``ZoneCardCount.scope``, ``DistinctCardTypes``' graveyard ``Zone.scope``),
    through :func:`_scope_from_player_tag`."""
    if tag_of(qty) == "ObjectCount":
        return _scope_from_player_node(getattr(qty, "filter", None))
    for fname in ("player", "controller", "scope"):
        v = getattr(qty, fname, MISSING)
        if _present(v):
            scope = _scope_from_player_tag(v if isinstance(v, str) else tag_of(v))
            if scope is not None:
                return scope
    source = getattr(qty, "source", MISSING)
    return quantity_scope(source) if _present(source) else None


# Recipient tags marking a discard DIRECTED at another player (CR 701.9): a targeted
# player ("target player / opponent discards" — Mind Rot, Stupor), or an explicit
# opponent. A you/controller recipient is a self-loot (the ported ``discard_makers``
# lane), not this hand-attack.
_DISCARD_OPP_TAGS: frozenset[str] = (
    TARGETED_PLAYER_TAGS
    | OPPONENT_ACTOR_TAGS
    | {"Any", "TargetPlayer", "TriggeringPlayer", "ParentTargetController"}
)


def recipient_tag(node: TypedMirrorNode) -> str | None:
    """The discriminator tag of an effect's FIRST present recipient sub-field, or
    ``None``.

    The raw tag (``ParentTarget`` / ``Player`` / ``Controller`` / ``Opponent`` …)
    behind :func:`_effect_scope` — exposed so a lane can tell a directed-player loot
    (a "target player draws, then discards" whose draw + discard share the SAME
    targeted player — Cephalid Looter) from a one-sided hand attack.
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub):
            continue
        sub = _unwrap_role_target(sub)
        if tag_of(sub) is not None:
            return tag_of(sub)
    return None


def modal_mode_description(
    unit: AbilityUnit, node: TypedMirrorNode, tree: ConceptTree
) -> str:
    """The REAL per-mode English for a typed node living inside a modal
    ability (CR 700.2 "choose one"), when the owning unit's own (frozen,
    unwritable) ``description`` field carries nothing usable — ``None`` for
    a modal SPELL's per-mode ability entry (Fatal Lore, Season of the
    Burrow), or a synthetic trigger-condition label ("When ~ enters" /
    "Whenever ~ attacks") for a modal TRIGGER (Ertai Resurrected, Balor).
    Phase carries the real text in two positionally-paired shapes:

    * a modal SPELL's card-ROOT ``modal.mode_descriptions``, paired with
      ``root.abilities`` by INDEX — the caller's own ``unit`` IS one
      ``abilities[i]`` entry, so ``unit.index`` is the position;
      :data:`ConceptTree.card_modal_mode_descriptions` carries the
      card-root list (populated at build time — no root access needed
      here).
    * a modal TRIGGER's ``execute.modal.mode_descriptions``, paired with
      ``execute.mode_abilities`` by INDEX — reachable directly off
      ``unit.node`` (the trigger carries its own ``execute``), so this
      branch walks ``mode_abilities`` looking for the ONE mode whose typed
      subtree contains ``node`` (object IDENTITY — the same frozen node
      the caller is asking about) and returns its paired description.

    Returns ``""`` when neither modal shape is present or ``node`` isn't
    found inside either — never a guess (CR 121.1/608.2h still needs a
    REAL same-clause attribution, not an inference).
    """
    if unit.origin == "ability" and tree.card_modal_mode_descriptions:
        descs = tree.card_modal_mode_descriptions
        if 0 <= unit.index < len(descs):
            return descs[unit.index]
        return ""
    execute = getattr(unit.node, "execute", MISSING)
    modal = getattr(execute, "modal", MISSING) if _present(execute) else MISSING
    mode_abilities = (
        getattr(execute, "mode_abilities", MISSING) if _present(execute) else MISSING
    )
    if (
        not _present(modal)
        or not _present(mode_abilities)
        or not isinstance(mode_abilities, list)
    ):
        return ""
    descs2 = getattr(modal, "mode_descriptions", None)
    if not isinstance(descs2, list):
        return ""
    for j, mode_ab in enumerate(mode_abilities):
        if j >= len(descs2):
            break
        if any(n is node for n in _iter_typed_nodes(mode_ab)):
            d = descs2[j]
            return d if isinstance(d, str) else ""
    return ""


def discard_is_random(node: object) -> bool:
    """Whether a ``Discard`` node discards at random (CR 701.9b: by default the
    discarding player chooses the card; some effects require a random discard).

    Phase carries the choice on the node's own ``random`` flag, on an effect
    (Goblin Lore's "discard three cards at random") and a cost (Flowstone Flood's
    "Buyback—Pay 3 life, Discard a card at random") alike; an absent flag is a
    chosen discard.
    """
    return getattr(node, "random", False) is True


def discard_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The DIRECTION of a ``Discard`` effect (who discards) from its recipient node.

    The ``opponent_discard`` gate (CR 701.9). Mirrors the OLD-IR ``_discard_player_
    scope`` promotion: a targeted "target player discards" (recipient ``Player``) is a
    forced opponent-hand attack → ``opponents``; an explicit opponent recipient →
    ``opponents``; a symmetric "each player discards" wheel → ``each`` (it hits
    opponents too); a you/controller recipient (a self-loot — Faithless Looting) →
    ``you`` (NOT this lane); ``None`` when the node carries no recipient field. Reads
    the discard's OWN recipient STRUCTURALLY, never phase's mis-scoped trigger scope.
    """
    for fname in _SCOPE_FIELDS:
        sub = getattr(node, fname, MISSING)
        if not _present(sub) or tag_of(sub) is None:
            continue
        t = tag_of(sub)
        if t in _EACH_ACTOR_TAGS:
            return "each"
        if t in _DISCARD_OPP_TAGS:
            return "opponents"
        if t == "Typed":
            ctrl = getattr(sub, "controller", None)
            if ctrl == "Opponent":
                return "opponents"
            if ctrl == "You":
                return "you"
            return "each"
        sc = _scope_from_player_node(sub)
        if sc == "you":
            return "you"
        if sc == "each":
            return "each"
        return "opponents"
    return None


def change_zone_dirs(node: TypedMirrorNode) -> tuple[str | None, str | None]:
    """``(origin, destination)`` of a ``ChangeZone`` EFFECT, the same fields
    :func:`trigger_def_event` reads on the trigger side.

    Reanimation is ``(Graveyard, Battlefield)``; a blink exile is
    ``(_, Exile)`` and its return ``(_, Battlefield)``. Exposing them on the effect
    side lets the GY-engine / flicker lanes read the zone change STRUCTURALLY rather
    than from a post-hoc recovered field.
    """
    return (
        getattr(node, "origin", None),
        getattr(node, "destination", None),
    )


#: The zones a graveyard recursion puts the card into; the recursion's subject
#: is the zone, lower-cased.
GRAVEYARD_RECURSION_ZONES: frozenset[str] = frozenset(
    {"Battlefield", "Hand", "Library"}
)


def enters_under_you(node: object) -> bool:
    """Whether an effect says its object enters "under your control"
    (``enters_under: You``)."""
    return getattr(node, "enters_under", None) == "You"


def puts_under_your_control(node: object, *, actor: str | None = None) -> bool:
    """Whether an object ``node`` puts onto the battlefield enters under your
    control. CR 110.2a: "If an effect instructs a player to put an object onto
    the battlefield, that object enters the battlefield under that player's
    control unless the effect states otherwise" — so an effect you perform puts
    it under yours whoever owns it (Ashen Powder's "from an opponent's
    graveyard"), "under your control" says so outright (``enters_under: You``),
    and a stated other player (``enters_under`` another player — Xantcha) or
    an ``actor`` the effect names among your opponents (``OPPONENT_ACTOR_TAGS``)
    does not."""
    if enters_under_you(node):
        return True
    entering = getattr(node, "enters_under", None)
    if _present(entering) and entering is not None:
        return False
    return actor not in OPPONENT_ACTOR_TAGS


#: The effects that put a card onto the battlefield face down (CR 701.40a
#: manifest, 701.62a manifest dread, 701.58a cloak).
FACE_DOWN_PUT_TAGS: frozenset[str] = frozenset({"Manifest", "ManifestDread", "Cloak"})


def manifests_for_you(node: object) -> bool:
    """Whether a manifest / cloak effect puts the card onto the battlefield under
    YOUR control: "manifest the top card of your library" (``target:
    Controller``; Whisperwood Elemental), "manifest dread" (always yours), or
    one stated so (``enters_under: You``) — not Reality Shift's "Its controller
    manifests the top card of their library" (``ParentTargetController``)."""
    tag = tag_of(node)
    if tag not in FACE_DOWN_PUT_TAGS:
        return False
    if tag == "ManifestDread" or enters_under_you(node):
        return True
    return tag_of(getattr(node, "target", None)) in (None, "Controller")


class RecursionHit(NamedTuple):
    """A :func:`graveyard_recursion`: where the card goes (``"battlefield"``,
    ``"hand"``, ``"library"``) and the moved filter."""

    dest: str
    filter: object


def graveyard_recursion(node: object) -> RecursionHit | None:
    """The :class:`RecursionHit` of an effect that returns a card from a
    graveyard, or ``None``. The shared walk the recursion lanes type-gate
    (``creature_recursion``'s creature cards, ``permanent_recast``'s permanent
    and land cards).

    * a ``ChangeZone`` / ``ChangeZoneAll`` out of a graveyard: the node's
      ``origin``, or, where phase leaves it unset, the moved filter's
      ``InZone`` (Ashen Powder's "Put target creature card from an opponent's
      graveyard onto the battlefield under your control"), to the battlefield,
      a hand or a library;
    * the legacy shapes (the Advocate cycle): a ``Bounce`` (→ hand) or
      ``PutAtLibraryPosition`` (→ library) whose subject carries ``InZone:
      Graveyard``.

    A pull of an opponent's card is graveyard hate, not a recursion of yours:
    an ``Opponent``-controlled filter, or opponent owners for a return to a
    hand or library (it goes to its owner's). One put onto the battlefield is
    yours unless the effect says otherwise (:func:`puts_under_your_control`)."""
    if not isinstance(node, TypedMirrorNode):
        return None
    sub = effect_filter(node)
    if filter_controller(sub) == "Opponent":
        return None
    tag = tag_of(node)
    if tag in ("Bounce", "PutAtLibraryPosition"):
        dest = "Hand" if tag == "Bounce" else "Library"
        if "Graveyard" not in filter_inzone_zones(sub):
            return None
    elif tag in ("ChangeZone", "ChangeZoneAll"):
        origin, dest = change_zone_dirs(node)
        # "from your hand or graveyard" (Swift Warkite) is an ``InAnyZone``
        # choice that a graveyard is among.
        if origin is None and "Graveyard" in (
            *filter_inzone_zones(sub),
            *filter_inanyzone_zones(sub),
        ):
            origin = "Graveyard"
        if origin != "Graveyard" or dest not in GRAVEYARD_RECURSION_ZONES:
            return None
    else:
        return None
    if dest == "Battlefield":
        if not puts_under_your_control(node):
            return None
    else:
        owners = filter_owners(sub)
        if owners and all(o == "Opponent" for o in owners):
            return None
    return RecursionHit(str(dest).lower(), sub)


#: The node tags an object filter takes: one population (``Typed``) or a list
#: of them (``Or`` / ``And``) — the shapes a filter the reads type-gate takes.
OBJECT_FILTER_TAGS: frozenset[str] = frozenset({"Typed", "Or", "And"})


@cache
def _field_names(cls: type) -> tuple[str, ...]:
    return tuple(f.name for f in fields(cast("Any", cls)))


def iter_node_filters(node: object) -> Iterator[tuple[str, object]]:
    """Each object filter ONE node holds directly, as ``(field, filter)``: a
    count's ``filter``, a static's ``affected``, a trigger's ``valid_card``, an
    effect's ``target``, a restriction's ``source_filter`` (an
    :data:`OBJECT_FILTER_TAGS` node). A variant-wrapped or listed filter is
    unwrapped; a filter nested inside another (an ``Or``'s arms) is that node's
    own, reached by walking it. An ``AttachedTo`` back-reference ("enchanted
    creature") is out: it names the one object the card is attached to, not a
    population, and carries no type of its own."""
    if not isinstance(node, TypedMirrorNode):
        return
    for name in _field_names(type(node)):
        val = getattr(node, name, MISSING)
        for item in val if isinstance(val, list) else (val,):
            v = item.inner if isinstance(item, MirrorVariant) else item
            if isinstance(v, TypedMirrorNode) and tag_of(v) in OBJECT_FILTER_TAGS:
                yield name, v


def recursion_card_types(
    tree: ConceptTree, node: object, sub: object, unit: AbilityUnit | None = None
) -> tuple[str, ...]:
    """The card types a :func:`graveyard_recursion` moves: its filter's core
    types; for a reanimation Aura's own reattach (Animate Dead's "Return
    enchanted creature card to the battlefield", an ``AttachedTo()`` target
    naming no type of its own), the card types the Aura's printed Enchant
    keyword names (:attr:`ConceptTree.card_enchant_core_types`) — the read's
    own decision; and, given its ``unit``, for a typeless filter that names the
    card an earlier clause chose ("Choose up to one target artifact or creature
    card in your graveyard … return it" — Jolted Awake; "Return those cards" —
    Revivify: an ``And`` holding a ``ParentTarget`` / ``TrackedSet``, or one
    alone), the types of the graveyard card that clause chose."""
    types = filter_core_types(sub)
    if types:
        return types
    if tag_of(node) in ("ChangeZone", "ChangeZoneAll") and tag_of(sub) == "AttachedTo":
        return tuple(tree.card_enchant_core_types)
    if unit is None:
        return types
    # "Return any number of artifact creature cards with total mana value 6 or
    # less from your graveyard to the battlefield" (Technomancer): a
    # ``ChooseFromZone`` picks the cards and the ``ChangeZone`` moves its bare
    # ``ParentTarget``.
    arms = getattr(sub, "filters", None) or () if tag_of(sub) == "And" else (sub,)
    if not any(tag_of(arm) in ("ParentTarget", "TrackedSet") for arm in arms):
        return types
    for other in unit.iter_typed():
        if other is node:
            continue
        for _field, filt in iter_node_filters(other):
            chosen = filter_core_types(filt)
            if chosen and "Graveyard" in filter_inzone_zones(filt):
                return chosen
    return types


#: A whole added PHASE (``segment: Phase``) → the step-name kind the readers key
#: on: an added combat phase is ``"begincombat"`` (its first step), an added
#: beginning phase ``"untap"`` (CR 501.1: untap, upkeep, draw), an added ending
#: phase ``"end"``.
_ADDED_PHASE_KIND: dict[str, str] = {
    "combat": "begincombat",
    "beginning": "untap",
    "ending": "end",
}


def additional_phase_kind(node: TypedMirrorNode) -> str:
    """The lowercased kind of an ``AdditionalPhase`` effect's added phase or step
    (CR 500.8), or ``""`` when absent: ``"begincombat"`` for an added combat phase
    (Aurelia, Moraug, Combat Celebrant), ``"untap"`` for an added beginning phase
    (Sphinx of the Second Sun), ``"upkeep"`` / ``"draw"`` / ``"end"`` for an added
    step (Paradox Haze, Y'shtola Rhul).

    Phase v0.104.0 replaced the flat ``phase: "BeginCombat"`` string with a tagged
    ``segment``: ``Phase`` (a whole phase — ``Combat`` / ``Beginning`` / ``Ending``),
    ``Step`` (one step — ``Upkeep`` / ``End`` …) or ``CreatedPhase`` (Obeka's
    "additional upkeep steps"), each carrying its name on ``data``. Both read to the
    same step-name kinds the ``extra_combats`` and extra-phase lanes key on.
    """
    seg = getattr(node, "segment", MISSING)
    data = getattr(seg, "data", None)
    if isinstance(data, str):
        name = data.lower()
        if tag_of(seg) == "Phase":
            return _ADDED_PHASE_KIND.get(name, name)
        return name
    return ""


def modify_cost_mode(static_node: TypedMirrorNode) -> str | None:
    """The ``mode`` of a static ability's ``ModifyCost`` (``"Reduce"`` / ``"Raise"`` /
    ``"Minimum"``), or ``None`` when the static is not a cost modifier.

    Phase models a cost modifier (CR 601.2f / 118.7) as a ``static_ability`` whose
    ``mode`` field is a ``{ModifyCost: S_ModifyCost}`` variant (the ``modifications``
    list is empty — the cost change rides ``mode``, not a P/T modification). The
    ``cost_reduction`` lane reads the inner ``S_ModifyCost.mode`` STRUCTURALLY to
    gate direction — a ``Raise`` tax (Thalia) is excluded without the live path's raw
    ``_COST_INCREASE`` screen. ``None`` for any non-``ModifyCost`` static.
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "ModifyCost":
        inner_mode = getattr(mode.inner, "mode", None)
        return inner_mode if isinstance(inner_mode, str) else None
    return None


# Dynamically-bound player-reference tags a ``GiveControl.recipient`` carries
# that :func:`_scope_from_player_node` doesn't resolve (that resolver is
# shared by 13 OTHER call sites — a corpus-wide behavior change is out of
# THIS key's scope, so the mapping is local to :func:`control_recipient_scope`
# only). All three are "that player" back-references bound by the ability's
# OWN context, never "you" — CR 110.2 lets control pass to any other player:
#   * ``ScopedPlayer`` — "each player's upkeep, THAT PLAYER gains control"
#     (Alexios, Risky Move's hot-potato cycle) — symmetric, "each".
#   * ``TriggeringPlayer`` — "whenever X deals damage to/is triggered by A
#     PLAYER, THAT PLAYER gains control" (Blim, Drooling Ogre, Kain) — the
#     triggering player is context-dependent, "any".
#   * ``ParentTargetController`` — "choose a/another player. THAT PLAYER
#     gains control" (Discerning Financier, Goblin Festival) — the chosen
#     player, "any".
_DONATE_RECIPIENT_SCOPES: dict[str, str] = {
    "ScopedPlayer": "each",
    "TriggeringPlayer": "any",
    "ParentTargetController": "any",
}


def control_recipient_scope(node: TypedMirrorNode) -> str | None:
    """The scope of a control-change effect's ``recipient`` (who GAINS control), or
    ``None`` when the node carries no recipient.

    A ``GiveControl`` (CR 110.2) hands a permanent YOU control to ``recipient`` — a
    targeted player (``Player`` → ``"any"`` — Donate, Bazaar Trader), an explicit
    opponent (``Typed controller=Opponent`` → ``"opponents"`` — Harmless Offering),
    or a dynamically-bound "that player" back-reference (:data:`_DONATE_RECIPIENT_
    SCOPES`). The ``donate_makers`` give-away gate (checklist #2) reads the
    ``recipient`` node directly — NOT :func:`explicit_recipient_scope`, which reads
    the donated permanent's own ``target`` filter first and mis-returns ``"you"``.
    Reading the recipient SPECIFICALLY isolates the beneficiary the OLD lossy IR
    dropped.
    """
    rcp = getattr(node, "recipient", MISSING)
    if not _present(rcp):
        return None
    t = tag_of(rcp)
    if t in _DONATE_RECIPIENT_SCOPES:
        return _DONATE_RECIPIENT_SCOPES[t]
    return _scope_from_player_node(rcp)


def counter_kind(node: TypedMirrorNode) -> str:
    """The ``counter_type`` of a counter-placing effect (``"P1P1"`` / ``"Loyalty"`` /
    ``"Oil"`` …), normalized to a string (``""`` when absent).

    The discriminator that keeps a +1/+1 placement (``plus_one_makers``) apart from
    loyalty / oil / shield / charge placements (their own lanes). CR 122.1.
    """
    ck = getattr(node, "counter_type", MISSING)
    return ck if isinstance(ck, str) else ""


def amount_is_scaling(node: TypedMirrorNode, field: str = "amount") -> bool:
    """Whether an effect's ``field`` (``amount`` / ``count``) is a DYNAMIC quantity.

    A ``Fixed`` value is a constant magnitude; anything else (``Ref`` over a
    devotion / power / object-count / multiply) scales with the board — the
    "significant engine" signal a one-shot fixed rider lacks (Dark Confidant's
    lose-life-equal-to-mana-value vs Infernal Grasp's fixed "lose 2 life").
    """
    q = getattr(node, field, MISSING)
    if not _present(q):
        return False
    return tag_of(q) not in ("Fixed", None)


def amount_factor(node: TypedMirrorNode, field: str = "amount") -> int:
    """The fixed magnitude of an effect's ``field`` (``1`` when dynamic/absent).

    The acceleration / upkeep-bleed gates read it (Sol Ring's ``{C}{C}`` count 2,
    a recurring upkeep loss ≥ 2). A dynamic quantity returns ``1`` (its magnitude
    is read via :func:`amount_is_scaling` instead).
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Fixed":
        v = getattr(q, "value", None)
        if isinstance(v, int):
            return v
    return 1


def has_fixed_count(node: TypedMirrorNode, field: str = "amount") -> bool:
    """Whether ``field`` is EXPLICITLY present and tagged ``Fixed`` — the
    presence check :func:`amount_factor`/:func:`amount_is_scaling`
    deliberately don't make (both fold "field absent" into the same
    default their genuine-``Fixed(1)`` case returns: ``amount_factor``
    defaults to ``1``, ``amount_is_scaling`` defaults to ``False`` — the
    same numbers a real ``Fixed(1)`` produces). That conflation is
    harmless for the acceleration/upkeep-bleed callers (an absent count
    correctly reads as "no extra magnitude"), but a gate that needs to
    tell "genuinely draws exactly one card" (Illusion of Choice's typed
    ``Draw`` with ``count=Fixed(1)``) apart from "an Unimplemented
    residue with NO count field at all" (Arcane Endeavor's "Draw cards
    equal to that result" — a die-roll-computed amount phase's grammar
    never structures, recovered via ``recovery.py``'s ``"draw"`` ALLOWLIST
    row with no count of its own) needs the field's PRESENCE, not just its
    resolved magnitude — see :func:`mtg_utils._deck_forge.crosswalk_
    signals._cantrip`, whose "draws exactly one card" gate this closes.
    """
    q = getattr(node, field, MISSING)
    return _present(q) and tag_of(q) == "Fixed"


#: The effects whose fixed number a trigger multiplier multiplies: damage, life
#: gained, tokens made, cards drawn — tag → the field holding the number.
_MULTIPLIABLE_FIELDS: dict[str, str] = {
    "LoseLife": "amount",
    "DealDamage": "amount",
    "DamageEachPlayer": "amount",
    "DamageAll": "amount",
    "GainLife": "amount",
    "Token": "count",
    "Draw": "count",
}


class FixedAmount(NamedTuple):
    """The first fixed number an ability yields (:func:`fixed_amount`): ``value``,
    and ``per_opponent`` when it is damage or life loss dealt to each opponent."""

    value: int
    per_opponent: bool


def fixed_amount(unit: AbilityUnit) -> FixedAmount | None:
    """The first fixed damage, life loss dealt to opponents, life gain, token or card
    count an ability yields (:func:`has_fixed_count` + :func:`amount_factor`), or
    ``None``. Kokusho's "each opponent loses 5 life" is 5 per opponent. An amount that
    scales — "gain life equal to the life lost this way" (Kokusho), "tokens equal
    to its power" — isn't a fixed number. Damage that reaches each opponent
    (:func:`effect_player_reach`) is marked, so a caller can count it per opponent
    (Purphoros, God of the Forge's 2)."""
    for concept in unit.effects:
        node = concept.node
        tag = tag_of(node) or ""
        field = _MULTIPLIABLE_FIELDS.get(tag)
        if field is None or not has_fixed_count(node, field):
            continue
        reach = effect_player_reach(unit.node, node)
        per_opponent = reach in ("opponents", "per_opponent")
        if tag == "LoseLife" and not (per_opponent or reach == "target"):
            continue  # your own life payment (Phyrexian Arena) is no yield
        if tag not in DAMAGE_EFFECT_TAGS and tag != "LoseLife":
            per_opponent = False
        return FixedAmount(amount_factor(node, field), per_opponent)
    return None


def pump_is_negative(node: TypedMirrorNode) -> bool:
    """Whether a ``Pump`` / ``PumpAll`` effect is a SHRINK (CR 613.4c) — a negative
    fixed ``power`` or ``toughness`` (Bile Blight's -3/-3, a -X/-X mass shrink).

    The ``Pump`` effect carries ``power`` / ``toughness`` as ``Fixed`` sub-nodes
    (distinct from the static ``AddPower`` mod's plain-int ``value``); a negative
    value is a debuff (CR 613.4c), a positive one a buff (an anthem). A dynamic /
    variable amount is NOT read here (it has no fixed sign to gate on).
    """
    for fname in ("power", "toughness"):
        sub = getattr(node, fname, MISSING)
        if _present(sub) and tag_of(sub) == "Fixed":
            v = getattr(sub, "value", None)
            if isinstance(v, int) and v < 0:
                return True
    return False


def negative_pt_field(node: TypedMirrorNode, field: str) -> bool:
    """Whether a Pump-style node's P/T ``field`` (``toughness``) is NEGATIVE —
    a shrink's lethality tell (CR 704.5f: a creature with toughness 0 or less
    dies; a "-2/-0" power dip never kills). Reads THREE shapes phase emits for a
    shrink: ``Fixed N`` (Languish's "-4/-4", Drown in Sorrow's "-2/-2" — the
    literal magnitude); ``Variable "-X"`` (Toxic Deluge's "-X/-X" — the
    magnitude is unknown at parse time, but the Variable's own string carries
    the sign); and ``Quantity`` wrapping a ``Multiply`` whose OUTERMOST
    ``factor`` is negative (Cloudkill / Mutilate / Olivia's Wrath's mass "-X/-X
    where X is <count>", Death Wind / Nightmarish End / Flunk's single-target
    kill class — a genuinely negative sign whatever the inner expression, since
    every corpus ``inner`` resolves a non-negative count; Flunk's clamp under a
    second ``Multiply(-1, ...)`` only floors the count at 0, it never flips the
    outer sign). Reading only the outermost factor is deliberately shallow: no
    corpus card double-negates via nested ``Multiply`` factors."""
    p = getattr(node, field, None)
    tag = tag_of(p)
    if tag == "Fixed":
        v = getattr(p, "value", None)
        return isinstance(v, int) and v < 0
    if tag == "Quantity":
        val = getattr(p, "value", None)
        if tag_of(val) == "Multiply":
            factor = getattr(val, "factor", None)
            if isinstance(factor, int) and factor < 0:
                return True
    if tag == "Variable":
        v = getattr(p, "value", None)
        return isinstance(v, str) and v.strip().startswith("-")
    return False


def mod_value(node: TypedMirrorNode) -> int | None:
    """The plain-int ``value`` of a static P/T modification (``AddPower`` /
    ``SetToughness`` …), or ``None`` when absent/dynamic.

    The static mods carry a bare-int ``value`` (Glorious Anthem's +1, Humility's
    set-to-1), unlike the ``Pump`` effect's ``Fixed``-wrapped ``power``/``toughness``.
    The base-P/T-shrink debuff gate (a SET ≤ 2 on opponents/symmetric) reads it.
    """
    v = getattr(node, "value", MISSING)
    return v if isinstance(v, int) else None


# Cost component tags that constitute a self life-payment (CR 118.8) — "Pay N life".
_PAYLIFE_COST_TAGS: frozenset[str] = frozenset({"PayLife"})


def cost_has_paylife(node: object, *, depth: int = 0) -> bool:
    """Whether an activation-cost node pays life (CR 118.8), recursing ``Composite``.

    Phase nests a ``Pay N life`` cost as a ``PayLife`` node, often inside a
    ``Composite`` cost (mana + life — Erebos's ``{1}{B}, Pay 2 life``). The
    lifeloss-maker cost arm reads it through the composite the single top-level
    cost-concept decoration does not flatten.
    """
    if depth > 8 or not isinstance(node, TypedMirrorNode):
        return False
    if tag_of(node) in _PAYLIFE_COST_TAGS:
        return True
    costs = getattr(node, "costs", MISSING)
    if _present(costs) and isinstance(costs, list):
        return any(cost_has_paylife(c, depth=depth + 1) for c in costs)
    return False


def damage_recipient_is_player(vt: object, *, aimed: bool = False) -> bool:
    """Whether a combat-damage TRIGGER's recipient (``valid_target``) is a PLAYER an
    aggressor reaches — an OPPONENT / generic / targeted player (CR 510.1c).

    The ``combat_damage_to_opp`` gate. A ``Player`` / planeswalker / opponent / generic
    targeted player IS a reachable player; a ``Typed`` filter naming ``Creature`` (or
    any core type that is not Player/Planeswalker) is a CREATURE recipient (Ohran
    Viper's first trigger → the to-creature lane). A ``Controller`` / ``You`` /
    ``SelfRef`` recipient is "deals combat damage to YOU" — a DEFENSIVE trigger
    (Contested War Zone, Norn's Decree; phase also MISLABELS some "to a player"
    triggers as ``Controller``, a phase-parse bug the live path excludes too), NOT this
    aggressive lane. A bare ``Typed`` filter with no core type words (a controller-only
    reference — Coastal Piracy's "an opponent") IS a reachable player.

    ``aimed`` asks the narrower question of a damage EFFECT's target (the reach
    read, :func:`reach_amount`): can the effect be pointed at a player? A
    ``ParentTarget`` / ``Target`` is "that creature" an earlier clause targeted
    (Abyssal Hunter's tapped creature), and a planeswalker arm is not a player
    (Bite Down's "creature or planeswalker"); "target player" (``TargetPlayer``)
    is one.
    """
    t = tag_of(vt)
    back_reference = t in ("Target", "ParentTarget")
    if aimed and back_reference:
        return False
    if (
        t in OPPONENT_ACTOR_TAGS
        or t in _EACH_ACTOR_TAGS
        or t in ("Player", "Any")
        or back_reference
        or (aimed and t == "TargetPlayer")
    ):
        return True
    if t == "Typed":
        ctrl = getattr(vt, "controller", None)
        if ctrl == "You":
            return False
        cores = filter_core_types(vt)
        if not cores:
            return True
        return "Player" in cores or (not aimed and "Planeswalker" in cores)
    if t == "Or":
        # ADR-0038 W3 batch 2 unit 6: "deals combat damage to a player or
        # planeswalker/battle" (Flitterwing Nuisance, Zurgo and Ojutai)
        # reaches a player in the Player branch even though the OTHER
        # branch is object-typed; ANY reachable branch is enough.
        return any(
            damage_recipient_is_player(f, aimed=aimed)
            for f in getattr(vt, "filters", ()) or ()
        )
    return False


# Static-restriction modes that force a creature to be blocked (CR 509.1c lure).
_LURE_MODES: frozenset[str] = frozenset({"MustBeBlocked", "MustBeBlockedByAll"})


def permission_tag(node: TypedMirrorNode) -> str | None:
    """The tag of a ``GrantCastingPermission`` effect's ``permission`` sub-node.

    Phase models "you may play those cards" / plot as a ``GrantCastingPermission``
    effect carrying a ``permission`` node — ``PlayFromExile`` (impulse exile-and-
    play — Act on Impulse, Abbot of Keral Keep) or ``Plotted`` (CR 702.170 plot —
    Aloe Alchemist). The cast-from-exile lane reads that tag STRUCTURALLY (the live
    path kept a byte-identical word-mirror; this is the fidelity gain of batch 5).
    """
    return tag_of(getattr(node, "permission", None))


# Condition-wrapper fields that nest an inner condition (CR boolean glue):
# ``Not`` carries ``condition``; ``ConditionInstead`` carries ``inner``; an
# ``And`` / ``Or`` of conditions carries ``conditions``. Walked so a leaf
# condition tag (``IsMonarch`` …) buried under a wrapper still surfaces.
_CONDITION_INNER_FIELDS = ("inner", "condition", "conditions")
# Ability-wrapper fields a ``condition`` can hang off, recursively: a trigger's
# ``execute`` Spell, a sequential ``sub_ability``, a nested ``effect``, modal
# ``mode_abilities`` arms, a ``GenericEffect``'s ``static_abilities``.
_CONDITION_CARRIER_FIELDS = ("effect", "sub_ability", "execute")


def _walk_condition_subtree(cond: object, depth: int, seen: set[int]) -> Iterator[str]:
    """Yield every condition-node tag reachable from one ``condition`` value."""
    if depth > 20 or not isinstance(cond, TypedMirrorNode) or id(cond) in seen:
        return
    seen.add(id(cond))
    t = tag_of(cond)
    if t is not None:
        yield t
    for fname in _CONDITION_INNER_FIELDS:
        child = getattr(cond, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_condition_subtree(child, depth + 1, seen)
        elif _present(child) and isinstance(child, list):
            for c in child:
                yield from _walk_condition_subtree(c, depth + 1, seen)


def _walk_unit_conditions(node: object, depth: int, seen: set[int]) -> Iterator[str]:
    """Yield condition-node tags from every ``condition`` field under one unit node.

    Descends the ability-wrapper chain (``effect`` / ``sub_ability`` / ``execute``
    / ``mode_abilities`` / nested ``static_abilities``) so a condition on a
    trigger's ``execute`` Spell (Court of Ambition, Sauron) or a continuous
    ability (Gloom Stalker, Nadaar) surfaces alongside one on the wrapper itself
    (Brimstone Vandal, Imoen). Cycle-safe (id-set + depth cap).
    """
    if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
        return
    seen.add(id(node))
    cond = getattr(node, "condition", MISSING)
    if isinstance(cond, TypedMirrorNode):
        yield from _walk_condition_subtree(cond, 0, set())
    for fname in (*_CONDITION_CARRIER_FIELDS, "mode_abilities", "static_abilities"):
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_unit_conditions(child, depth + 1, seen)
        elif _present(child) and isinstance(child, list):
            for m in child:
                yield from _walk_unit_conditions(m, depth + 1, seen)


def condition_tags(tree: ConceptTree) -> frozenset[str]:
    """Every condition-node tag present anywhere on the card (whole-card scan).

    The additive primitive the batch-5 ``*_matters`` lanes read: a payoff GATED on
    a designation/state (``IsMonarch`` / ``CompletedADungeon`` / ``IsInitiative`` /
    ``IsRingBearer`` …) carries a typed ``condition`` node the crosswalk's
    effect/cost/static decoration does not surface. These leaf tags are unique to
    conditions (no effect shares the name), so a tag-membership scan is precise.
    """
    out: set[str] = set()
    for unit in tree.units:
        out.update(_walk_unit_conditions(unit.node, 0, set()))
    return frozenset(out)


def node_lure_mode(node: object) -> bool:
    """Whether a typed node carries a "must be blocked" lure mode (CR 509.1c).

    Phase encodes Lure as a static ability whose ``mode`` is ``MustBeBlockedByAll``,
    conferred via an ``AddStaticMode`` modification carrying the same ``mode``. Either
    surface marks the all-creatures-must-block requirement the lure lane reads (a
    single-creature ``ForceBlock`` — Academic Dispute — is a narrower provoke-style
    effect, NOT this lane).
    """
    if not isinstance(node, TypedMirrorNode):
        return False
    mode = getattr(node, "mode", None)
    return isinstance(mode, str) and mode in _LURE_MODES


# ── Batch-8 typed accessors (removal / card-flow / library-top cluster) ──────


def static_mode_tag(node: object) -> str | None:
    """The MODE discriminator of a static ability (CR 604.3), across shapes.

    Phase's static ``mode`` is a plain string for the common forms
    (``"Continuous"`` / ``"MayLookAtTopOfLibrary"``) and a variant wrapper for
    the parameterized ones (``{TopOfLibraryCastPermission: …}`` — Bolas's
    Citadel, Future Sight; ``{ModifyCost: …}`` — the cost_reduction seam). The
    play_from_top lane reads the variant KEY so the ongoing top-play permission
    is a pure typed read (the live path needed a recovered ``from:library``
    zone marker).
    """
    mode = getattr(node, "mode", MISSING)
    if isinstance(mode, str):
        return mode
    if isinstance(mode, MirrorVariant):
        return mode.key
    if isinstance(mode, TypedMirrorNode):
        return tag_of(mode)
    return None


def mana_replacement_multiplier(node: TypedMirrorNode) -> int:
    """The ``Multiply`` factor of a ``ProduceMana`` replacement's
    ``mana_modification`` (CR 106.4 / 614.1) — Mana Reflection x2, Virtue of
    Strength x3. ``0`` when the node is not a mana-multiplier replacement, so
    the mana_amplifier lane can gate on ``>= 2``.
    """
    mm = getattr(node, "mana_modification", MISSING)
    if _present(mm) and tag_of(mm) == "Multiply":
        f = getattr(mm, "factor", None)
        return f if isinstance(f, int) else 2
    return 0


def produced_contribution(node: TypedMirrorNode) -> str:
    """The ``contribution`` of a ``Mana`` effect's ``produced`` spec (CR 106.4).

    Phase marks the triggered "whenever you tap a <land> for mana, add an
    additional {B}" doublers (Crypt Ghast, Nirkana Revenant) with
    ``produced.contribution == "Additional"`` — the extra mana rides ON TOP of
    the tap's own production. ``""`` when absent (a plain producer).
    """
    p = getattr(node, "produced", MISSING)
    if not _present(p):
        return ""
    c = getattr(p, "contribution", MISSING)
    return c if isinstance(c, str) else ""


def counter_kind_any(node: TypedMirrorNode) -> str:
    """``counter_type`` normalized UPPER across BOTH phase shapes (CR 122.1).

    An EFFECT-side counter node carries a plain string kind (``"M1M1"`` /
    ``"fade"``); a COST-side ``RemoveCounter`` carries a tagged node —
    ``{OfType: "P1P1"}`` (Walking Ballista's remove-as-cost) or the kindless
    ``{Any}`` (Power Conduit) → ``"ANY"``. ``""`` when absent. The
    counter_manipulation lane routes by the normalized kind.
    """
    ck = getattr(node, "counter_type", MISSING)
    if isinstance(ck, str):
        return ck.upper()
    if isinstance(ck, TypedMirrorNode):
        t = tag_of(ck)
        if t == "OfType":
            data = getattr(ck, "data", None)
            return data.upper() if isinstance(data, str) else ""
        return (t or "").upper()
    return ""


def iter_cost_leaves(node: object, *, depth: int = 0) -> Iterator[TypedMirrorNode]:
    """Leaf cost nodes of an activation cost, recursing ``Composite`` /
    ``OneOf`` ``costs`` lists (the same nesting :func:`cost_has_paylife`
    walks). A ``{B}, Remove a -1/-1 counter from ~:`` composite (Carnifex
    Demon) yields its ``Mana`` AND ``RemoveCounter`` leaves; a bare cost
    yields itself.
    """
    if depth > 8 or not isinstance(node, TypedMirrorNode):
        return
    costs = getattr(node, "costs", MISSING)
    if _present(costs) and isinstance(costs, list):
        for c in costs:
            yield from iter_cost_leaves(c, depth=depth + 1)
        return
    yield node


def self_graveyard_fills(unit: AbilityUnit) -> tuple[TypedMirrorNode, ...]:
    """The nodes of one unit that put your own cards into your graveyard
    without a ``Mill`` effect: the shapes the graveyard lane's effect walk
    can't see.

    * a ``Surveil`` action anywhere under the unit, a granted ability's
      included (Tocasia's "{T}: Surveil 1"). CR 701.25a: to surveil N is to
      look at the top N cards of *your* library and put any number of them
      into your graveyard, so phase's ``Controller`` target (or none) is the
      only reading.
    * a ``ManifestDread`` action: CR 701.62a looks at the top two cards of
      your library, manifests one and puts the other into your graveyard.
    * a ``Mill`` leaf of a cost the unit's controller pays
      (:func:`controller_paid_cost_leaves`): the unit's own activation cost
      (Millikin's "{T}, Mill a card:"), a granted ability's cost, a spell's
      merged additional cost (``unit.costs``), or a "you may pay" cost. A
      milled card goes from the top of that player's library into their
      graveyard (CR 701.17a); counting a mill paid as a cost as filling your
      graveyard is this read's decision. A tax is left out: Deep Spawn's
      "sacrifice ~ unless you mill two cards" and Masticore's "unless you
      discard a card" are payments to keep the permanent, not an engine a
      deck builds on (Dan's upkeep-payment verdict). A cost another player
      pays mills *their* library, so it is skipped.
    * a ``Discard`` leaf of such a cost: "{G}, {T}, Discard a creature card:"
      (Fauna Shaman), "Discard your hand, Sacrifice ~:" (Lion's Eye
      Diamond). CR 701.9a: to discard a card is to move it from its owner's
      hand to that player's graveyard. Two leaves are left out, as
      ``discard_outlet`` leaves them out: a random discard (CR 701.9b — the
      card isn't yours to choose) and a ``self_ref`` "Discard this card"
      (cycling and channel fodder, not a graveyard engine).
    """
    out: dict[int, TypedMirrorNode] = {}
    for n in unit.iter_typed():
        if tag_of(n) == "Surveil":
            if tag_of(getattr(n, "target", None)) in (None, "Controller"):
                out[id(n)] = n
        elif tag_of(n) == "ManifestDread":
            out[id(n)] = n
    for leaf, how in controller_paid_cost_leaves(unit):
        if how != "tax" and (
            tag_of(leaf) == "Mill" or is_self_discard_cost(leaf, random=False)
        ):
            out[id(leaf)] = leaf
    return tuple(out.values())


# The MAX/MIN-over-a-population quantity node, across phase shapes. Through
# v0.45.0 phase emitted ``Aggregate{function, property, filter}``; the v0.65.0
# "opponent controlled count extrema" rework (#7967) reified it as
# ``PropertyAggregate{function, property, source}`` where ``source`` is either
# ``Objects{filter}`` (the same filtered population, one level deeper — 245
# corpus nodes at v0.66.0) or ``TrackedSet{id}`` (an aggregate over an earlier
# effect's tracked objects, no filter at all — 25 nodes). Every reader that
# used to test ``tag_of(qty) == "Aggregate"`` and read ``qty.filter`` goes
# through this pair so the rename lands in ONE place.
AGGREGATE_QTY_TAGS: frozenset[str] = frozenset({"Aggregate", "PropertyAggregate"})


def aggregate_filter(qty: object) -> object | None:
    """The population filter of an ``Aggregate`` / ``PropertyAggregate`` qty
    node (Monstrous Onslaught's "greatest power among creatures you control"),
    or ``None`` when ``qty`` is neither, or aggregates a ``TrackedSet`` rather
    than a filtered population. CR 107.3."""
    t = tag_of(qty)
    if t == "Aggregate":
        filt = getattr(qty, "filter", MISSING)
        return filt if _present(filt) else None
    if t == "PropertyAggregate":
        source = getattr(qty, "source", MISSING)
        if tag_of(source) == "Objects":
            filt = getattr(source, "filter", MISSING)
            return filt if _present(filt) else None
    return None


def ref_qty_tag(node: TypedMirrorNode, field: str) -> str | None:
    """The qty-node discriminator tag of a ``Ref``-wrapped ``field``, or
    ``None`` when the field is absent / not a ``Ref``.

    The scaling-count lanes (draw_for_each / scaling_pump / count_anthem) read
    the tag to tell a board-count scaler (``ObjectCount`` — Shamanic
    Revelation, Craterhoof) from a bare X-spell (``Variable`` — Braingeyser,
    CR 107.3).
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Ref":
        qty = getattr(q, "qty", None)
        return tag_of(qty)
    return None


def ref_count_qty(node: TypedMirrorNode, field: str) -> str | None:
    """The board-count qty tag of a ``Ref`` value, unwrapping a ``Multiply``.

    A dynamic P/T modification can hide its counted-object ``Ref`` under a
    ``Multiply`` scalar: "gets +2/+2 for each Aura attached to it" projects
    ``Multiply(factor=2, inner=Ref(ObjectCount(...)))`` (Champion of the Flame,
    Auramancer's Guise). :func:`ref_qty_tag` reads only a bare ``Ref``; this
    variant unwraps the scalar first so the scaling-pump read reaches the count.
    ``None`` when ``field`` is not a (possibly scaled) ``Ref``.
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Multiply":
        q = getattr(q, "inner", None)
    if _present(q) and tag_of(q) == "Ref":
        return tag_of(getattr(q, "qty", None))
    return None


def ref_count_filter(node: object, field: str) -> object | None:
    """The counted-object filter inside a (``Multiply``-wrapped) ``Ref`` →
    ``ObjectCount`` value at ``node.field``, or ``None``.

    The voltron read of a dynamic self-pump ("+X/+X for each Aura/Equipment
    attached to it" — Champion of the Flame) needs the ``AttachedToRecipient``
    ``ObjectCount`` filter, which the value's ``Multiply`` scalar hides from
    :func:`effect_filter` / :func:`count_operand_filter`. Returns ``None``
    unless the value resolves to a ``Ref`` over an ``ObjectCount``.
    """
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "Multiply":
        q = getattr(q, "inner", None)
    if _present(q) and tag_of(q) == "Ref":
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            return getattr(qty, "filter", None)
    return None


# Effect-bearing child fields a node nests further effects through. Phase chains
# sequential siblings ("draw two cards, then discard two") via ``sub_ability``,
# wraps a delayed/granted effect in ``effect`` / ``execute`` (a replacement's
# ``execute``, Final Fortune's nested end-step loss), and branches modes through
# ``mode_abilities`` (Demonic Pact). A faithful unit aggregates them all — the same
# flattening the old projection's ``ab.effects`` did.
# ``chosen_pile_effect`` / ``unchosen_pile_effect``: phase v0.23.0's
# ``SeparateIntoPiles`` restructure (task #84) moved the Fact or Fiction
# family's per-pile outcomes (the chosen pile → hand, the rest → graveyard)
# out of the old ``sub_ability`` chain into these two dedicated
# ability-shaped fields — same flattening rationale, 6 carriers at the bump
# census (Fact or Fiction, Sphinx of Clear Skies, Sphinx of Uthuun, Unesh,
# Boneyard Parley, Make an Example).
# ``else_ability``: phase v0.94.0's "Otherwise, …" branch of a conditional
# (Bogardan Phoenix's "Otherwise, return it to the battlefield"; Sphinx
# Sovereign's "Otherwise, each opponent loses 3 life") — one of the two
# outcomes the ability can have, so a faithful unit aggregates it too.
# ``win_effect`` / ``lose_effect``: a ``FlipCoins`` outcome — The
# Gold Saucer's Treasure, Invert Polarity's theft or counter, Winter Sky's sweep.
# Like a die-roll row, each is one possible outcome; the walk skips an outcome
# that is the card's own drawback (:func:`is_own_drawback`).
_FLIP_OUTCOME_FIELDS = ("win_effect", "lose_effect")
_EFFECT_CHILD_FIELDS = (
    "effect",
    "sub_ability",
    "execute",
    "chosen_pile_effect",
    "unchosen_pile_effect",
    "else_ability",
    *_FLIP_OUTCOME_FIELDS,
)
# The LIST-valued branch fields, each entry one alternative outcome of the
# node that carries it: a modal ability's ``mode_abilities`` (Demonic Pact), a
# ``ChooseOneOf``'s ``branches`` (an unbulleted "X or Y" choice — Endling's "~
# gets +1/-1 or -1/+1", fabricate's counters or Servos), a ``Vote``'s
# ``per_choice_effect`` (Tyrant's Choice, CR 701.38a), and a ``RollDie``'s
# ``results`` table rows (Farideh's Fireball's d20, CR 706 — each row an
# untyped ``{min, max, effect}`` struct whose ``effect`` is the row's ability).
_EFFECT_LIST_FIELDS = ("mode_abilities", *BRANCH_LISTS.values())
# Every field a walk over an ability's effects descends, single and list alike.
_EFFECT_WALK_FIELDS = (*_EFFECT_CHILD_FIELDS, *_EFFECT_LIST_FIELDS)


def effect_child_items(
    node: object, *, cast_by_you: bool = False
) -> Iterator[tuple[str, int | None, object]]:
    """``(field, list index or None, child)`` for each child a walk over the card's
    OWN effects descends from ``node``: every "otherwise" branch, choice branch,
    vote outcome and die-roll row. (The certain trees leave out the branches the
    controller doesn't decide by pruning them from the records before load —
    ``_card_ir.branches.certain_records`` — so no walk needs to know.)

    A "sacrifice it unless you …" choice is always skipped, the choice and its
    "otherwise, sacrifice it" branch: champion's "sacrifice it unless you exile
    another [object] you control" (CR 702.72a — Changeling Hero, Mistbind
    Clique) is a drawback the controller pays to keep the card, so neither
    alternative is something the card does for them."""
    tag = tag_of(node)
    for fname in _EFFECT_WALK_FIELDS:
        child = getattr(node, fname, MISSING)
        if fname == "else_ability" and is_self_sacrifice(child):
            continue
        if fname in _FLIP_OUTCOME_FIELDS and is_own_drawback(
            child, node, cast_by_you=cast_by_you
        ):
            continue
        if (
            fname == BRANCH_LISTS["ChooseOneOf"]
            and tag == "ChooseOneOf"
            and _present(child)
            and isinstance(child, list)
            and any(is_self_sacrifice(b) for b in child)
        ):
            continue
        if isinstance(child, TypedMirrorNode):
            yield fname, None, child
        elif _present(child) and isinstance(child, list):
            for i, m in enumerate(child):
                yield fname, i, m


def effect_children(node: object, *, cast_by_you: bool = False) -> Iterator[object]:
    """The child nodes :func:`effect_child_items` names. ``cast_by_you``: the
    walk started at a trigger watching spells you cast, so its triggering spell
    is yours (:func:`is_own_drawback`)."""
    for _fname, _i, child in effect_child_items(node, cast_by_you=cast_by_you):
        yield child


#: Effects that take the card itself out of play or out of combat when aimed at
#: ``SelfRef``: sacrificing, bouncing, exiling or moving it, turning it face down,
#: removing it from combat.
_SELF_DRAWBACK_TAGS: frozenset[str] = frozenset(
    {"Sacrifice", "Bounce", "ChangeZone", "TurnFaceDown", "RemoveFromCombat"}
)
#: Effects that cost you when aimed at you (``Controller``).
_SELF_HARM_TAGS: frozenset[str] = frozenset({"DealDamage", "LoseLife"})


#: Effects that answer or move the objects their filter names — a drawback
#: when every one they name is yours.
_OBJECT_ANSWER_TAGS: frozenset[str] = frozenset(
    {"Counter", "Bounce", "Destroy", "DestroyAll", "Sacrifice", "ChangeZone"}
)


def is_own_drawback(
    ability_like: object, flip: object = None, *, cast_by_you: bool = False
) -> bool:
    """Whether a coin flip's outcome branch works against the card's controller —
    the effect walk's own decision: a drawback outcome is not what the card does
    for you, so it adds nothing to the unit's effects. Three shapes:

    * it sacrifices, bounces, exiles or otherwise removes the card itself
      (Scoria Wurm's and Viashino Sandswimmer's return to hand, Ral, Monsoon
      Mage's and Frenetic Sliver's exile-and-return);
    * it damages you or makes you lose life (Mana Crypt);
    * it counters, bounces, destroys or moves only objects that are yours:
      every object filter it names is controlled by you (Goblin Artisans'
      "counter target artifact spell you control") or names a token the same
      flip's other outcome creates (Wirefly Hive's "destroy all permanents named
      Wirefly"), or it aims at the triggering spell of a trigger that watches
      spells you cast (``cast_by_you`` — Krark, the Thumbless's "return that
      spell to its owner's hand"). Invert Polarity's "counter that spell" names
      anyone's spell, so it stays."""
    eff = getattr(ability_like, "effect", None)
    tag = tag_of(eff)
    target = getattr(eff, "target", None)
    if tag in _SELF_DRAWBACK_TAGS and tag_of(target) == "SelfRef":
        return True
    if tag in _SELF_HARM_TAGS and tag_of(target) == "Controller":
        return True
    if tag not in _OBJECT_ANSWER_TAGS:
        return False
    if tag_of(target) == "TriggeringSource":
        return cast_by_you
    own_tokens = {
        getattr(n, "name", None)
        for field in _FLIP_OUTCOME_FIELDS
        if getattr(flip, field, None) is not ability_like
        for n in _iter_typed_nodes(getattr(flip, field, None))
        if tag_of(n) == "Token"
    }
    filters = [n for n in _iter_typed_nodes(target) if tag_of(n) == "Typed"]
    return bool(filters) and all(
        getattr(f, "controller", None) == "You"
        or any(
            tag_of(p) == "Named" and getattr(p, "name", None) in own_tokens
            for p in getattr(f, "properties", None) or ()
        )
        for f in filters
    )


def is_self_sacrifice(ability_like: object) -> bool:
    """Whether an ability wrapper's effect is "sacrifice this permanent" (a
    ``Sacrifice`` of ``SelfRef``) — the drawback half of "sacrifice it unless"."""
    eff = getattr(ability_like, "effect", None)
    return (
        tag_of(eff) == "Sacrifice" and tag_of(getattr(eff, "target", None)) == "SelfRef"
    )


_MOD_SITES_CACHE_ATTR = "_xw_mod_sites"


def iter_mod_sites(
    root: object, *, deep: bool = False
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    """``(static_def, modification)`` pairs reachable from one unit node.

    ``deep`` widens the walk to EVERY typed node under ``root`` (the generic
    deep walk, :func:`iter_typed_nodes`): a ``ChooseOneOf``'s ``branches``
    (Apostle's Blessing's and Giver of Runes' protection choices), a token's
    definition, a granted ability's body, an emblem — the board-protection
    reads (``crosswalk.protection``) need every grant wherever phase nests it;
    the default walk stays the anthem / team-buff lanes' narrower one.

    Covers BOTH continuous-ability shapes: a top-level static (the unit node
    itself carries ``modifications`` — Glorious Anthem, Commander's Insignia)
    and the one-shot ``GenericEffect``-nested static defs a spell/trigger
    confers (Craterhoof's "gain trample and get +X/+X" — nested
    ``static_abilities`` whose defs carry their OWN ``affected``). The
    anthem / scaling-pump / team-buff lanes read the def's ``affected`` filter
    together with each modification (granularity b). Cycle-safe, depth-capped.
    Iterates a per-root memoized walk like :func:`_iter_typed_nodes` — many
    lanes re-scan the same unit node.
    """
    if deep:
        yield from _deep_mod_sites(root)
        return
    yield from _mod_sites(root)


_DEEP_MOD_SITES_CACHE_ATTR = "_xw_deep_mod_sites"


def _deep_mod_sites(
    root: object,
) -> tuple[tuple[TypedMirrorNode, TypedMirrorNode], ...]:
    def walk() -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
        for node in _iter_typed_nodes(root):
            mods = getattr(node, "modifications", MISSING)
            if _present(mods) and isinstance(mods, list):
                for mod in mods:
                    if isinstance(mod, TypedMirrorNode):
                        yield node, mod

    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_DEEP_MOD_SITES_CACHE_ATTR)
        if cached is None:
            cached = tuple(walk())
            object.__setattr__(root, _DEEP_MOD_SITES_CACHE_ATTR, cached)
        return cached
    return tuple(walk())


def _mod_sites(
    root: object,
) -> tuple[tuple[TypedMirrorNode, TypedMirrorNode], ...]:
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_MOD_SITES_CACHE_ATTR)
        if cached is None:
            cached = tuple(_walk_mod_sites(root))
            object.__setattr__(root, _MOD_SITES_CACHE_ATTR, cached)
        return cached
    return tuple(_walk_mod_sites(root))


def _walk_mod_sites(
    root: object,
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        mods = getattr(node, "modifications", MISSING)
        if _present(mods) and isinstance(mods, list):
            for mod in mods:
                if isinstance(mod, TypedMirrorNode):
                    yield node, mod
        stack.extend(effect_children(node))
        child = getattr(node, "static_abilities", MISSING)
        if isinstance(child, TypedMirrorNode):
            stack.append(child)
        elif _present(child) and isinstance(child, list):
            stack.extend(child)


def filter_inzone_zones(filt: object) -> tuple[str, ...]:
    """The zones named by a filter's ``InZone`` properties (CR 400.7),
    recursing ``Or`` / ``And``. The exile_removal zone gate reads them: an
    "exile … from a graveyard" subject carries ``InZone: Graveyard`` — GY-hate,
    not battlefield removal.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "InZone":
                z = getattr(prop, "zone", None)
                if isinstance(z, str):
                    out.append(z)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_inzone_zones(sub))
    return tuple(out)


# The card types a ``Typed`` filter must not carry for its ``Named`` property to name a
# permanent: ``Card`` is a card in a zone (a tutor, a grandeur discard, a graveyard
# count), and an empty type list is the "a card named X" of a search or seek.
_NAMED_CARD_TYPES = frozenset({"Card"})


def named_permanent_refs(nodes: Iterable[object]) -> tuple[str, ...]:
    """The names the typed ``nodes`` (a tree's or unit's ``iter_typed()``) refer to
    as permanents on the battlefield: each positive ``Named`` property of a
    ``Typed`` filter over a permanent type with no ``InZone`` outside the
    battlefield ("each other creature named Brothers Yamazaki", "if you control a
    creature named Bogbrew Witch", "artifacts named Crown of Empires", a meld
    partner). Such a filter matches every object with that name, unlike a
    self-reference by name (CR 201.5). Not a card named in a library, graveyard or
    hand (a tutor, a grandeur discard, "cards named Kindle in all graveyards"), a
    spell named in a cast count, nor a ``Not`` wrapper ("a creature not named
    Ebondeath")."""
    out: list[str] = []
    for n in nodes:
        if tag_of(n) != "Typed":
            continue
        types = getattr(n, "type_filters", ()) or ()
        if not types or _NAMED_CARD_TYPES.intersection(filter_core_types(n)):
            continue
        if any(z != "Battlefield" for z in filter_inzone_zones(n)):
            continue
        for prop in getattr(n, "properties", ()) or ():
            name = getattr(prop, "name", None) if tag_of(prop) == "Named" else None
            if isinstance(name, str) and name not in out:
                out.append(name)
    return tuple(out)


def filter_inanyzone_zones(filt: object) -> tuple[str, ...]:
    """The zones named by a filter's ``InAnyZone`` properties, recursing
    ``Or`` / ``And``. Parameterized since phase v0.35.2: the same-is-true
    type-changer rider spans ``[Library, Hand, Graveyard, Stack, Exile,
    Command]`` while Ashes of the Fallen's graveyard grant carries exactly
    ``[Graveyard]`` — the payload, not the property's presence, decides the
    reach."""
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "InAnyZone":
                for z in getattr(prop, "zones", ()) or ():
                    if isinstance(z, str):
                        out.append(z)
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_inanyzone_zones(sub))
    return tuple(out)


def filter_owned_controller(filt: object) -> str | None:
    """The ``controller`` of a filter's ``Owned`` property (CR 108.3), or
    ``None``. ``Owned: You`` marks an exile of YOUR OWN object — the
    blink-your-own tell the exile_removal lane must exclude (the object comes
    back, CR 603.6e). Recurses ``Or`` / ``And``.
    """
    t = tag_of(filt)
    if t == "Typed":
        for prop in getattr(filt, "properties", ()) or ():
            if tag_of(prop) == "Owned":
                c = getattr(prop, "controller", None)
                return c if isinstance(c, str) else ""
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            c = filter_owned_controller(sub)
            if c is not None:
                return c
    return None


def mod_keyword_name(mod: TypedMirrorNode) -> str | None:
    """The keyword NAME of an ``AddKeyword`` modification, across both shapes.

    A plain evergreen grant carries a bare string (``"Trample"`` — the
    team_buff read); a PARAMETERIZED grant carries a variant wrapper whose key
    is the keyword name (``{Flashback: <cost>}`` — Snapcaster Mage's targeted
    flashback grant, CR 702.34). ``None`` when absent / not a keyword node.
    """
    return _keyword_entry_name(getattr(mod, "keyword", MISSING))


def _keyword_entry_name(kw: object) -> str | None:
    """The keyword NAME of one keyword entry: a bare string (``"Flying"``) or a
    parameterized variant's key (``{Ward: <cost>}``); ``None`` for anything
    else."""
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def token_profile_keywords(node: object) -> tuple[str, ...]:
    """The keyword NAMES a ``Token`` effect's profile carries (CR 111.3: the
    spell or ability that creates a token defines its characteristics, its
    abilities among them).

    A token profile's ``keywords`` list mixes bare strings (``"Flying"``)
    with parameterized variants whose KEY is the keyword name (Dragon
    Broodmother's ``{Devour: 2}``, Chromanticore's bestow token) — the same
    two shapes :func:`mod_keyword_name` normalizes. ``()`` for a non-Token
    node. The has_devour / has_changeling token-profile tails read this
    (grow-on-demand: only the batch-13 lanes consume it today).
    """
    if not isinstance(node, TypedMirrorNode) or tag_of(node) != "Token":
        return ()
    kws = getattr(node, "keywords", MISSING)
    if not _present(kws) or not isinstance(kws, list):
        return ()
    out: list[str] = []
    for kw in kws:
        name = _keyword_entry_name(kw)
        if name is not None:
            out.append(name)
    return tuple(out)


# task #87 — the keyword-mechanic names whose placement effect is ONLY ever
# a +1/+1 counter when it places one at all (CR 702.54 Bloodthirst, 702.82
# Devour, 702.97 Scavenge, 702.103 Dethrone, 702.106 Evolve, 702.134 Mentor,
# 702.149 Training — each verified via ``rules-lookup``). Sunburst (CR
# 702.44) is deliberately EXCLUDED — it branches +1/+1 vs CHARGE counters
# depending on whether the affected permanent is a creature, a fork the
# granting site (a bare ``TriggeringSource``/``ParentTarget`` affected-ref,
# no type filter of its own) can't resolve reliably. Riot (CR 702.136) is
# also EXCLUDED — a haste-OR-counter CHOICE, never a guaranteed placement
# (and native Riot isn't in the plus-one-counters Preset's own keyword list
# either — this set doesn't reopen that call). The other seven mirror the
# Preset's existing native-keyword precedent (Devour/Dethrone/Training/
# Scavenge/Evolve/Mentor already listed there as sufficient-on-their-own).
_PLUS_ONE_KEYWORD_NAMES = frozenset(
    {"Bloodthirst", "Devour", "Scavenge", "Dethrone", "Evolve", "Training", "Mentor"}
)


def nested_plus_one_keyword_grant(unit_node: object) -> bool:
    """True if ``unit_node`` grants one of :data:`_PLUS_ONE_KEYWORD_NAMES`
    to something other than the card's own top-level keyword list (which
    Scryfall/MTGJSON's ``keywords`` field already exposes directly) — task
    #87's ``plus_one_makers`` token-body/granted-keyword gap. Three
    corpus-verified shapes, all read via already-established shared
    descents (no new traversal):

    * a static's ``AddKeyword`` modification, top-level or nested inside a
      one-shot ``GenericEffect`` (:func:`iter_mod_sites` — Twins of
      Discord's "Each other colorless creature you control has
      bloodthirst 2", Varolz / Young Deathclaws's "creature cards in your
      graveyard have scavenge", Propagator Drone's "Creature tokens you
      control have evolve", Elder Arthur Maxson's "Creature tokens you
      control have training", Aegis of the Legion's Equip-granted
      "Equipped creature gets +1/+1 and has mentor" — the ``EquippedBy``
      predicate isn't excluded here the way the SEPARATE ``pacify_makers``
      concept excludes it; a granted keyword is a maker fact regardless of
      the attach mechanism, CR 301/303 both read the same);
    * a ``BecomeCopy``/``CopyTokenOf`` replacement's ``additional_
      modifications`` list — a copy-EXCEPTION grant riding the copy node
      itself, not its ``modifications`` field (Dack's Duplicate's "...
      except it has haste and dethrone" — the SAME field
      ``crosswalk_signals._b13_conferred_grant_lanes`` already reads for
      its Myriad copy-exception, generalized to this keyword set here);
    * a CREATED TOKEN's OWN keyword profile (:func:`token_profile_keywords`
      — Dragon Broodmother's Dragon token's ``{Devour: 2}``; CR 111.3: the
      effect that creates a token defines its abilities).

    The Mutagen-token cycle (April O'Neil, Mutagen Man, Genghis Frog, ...)
    and the Young Hero Role cycle (Cut In, Embereth Veteran, ...) stay OUT
    — verified against the raw phase record: a predefined token's OWN
    activated/triggered ability carries NO body at all in card-data.json
    (Mutagen Man's ``Token`` effect node has an empty ``keywords`` list
    and no ``static_abilities`` field; same for Cut In's Young Hero Role).
    The actual reminder-text ability lives only in phase's engine-side
    ``known-tokens.toml``, a different data source this crosswalk never
    reads — a genuine substrate gap, not a missed structural read.
    """
    for _sdef, mod in iter_mod_sites(unit_node):
        if (
            tag_of(mod) == "AddKeyword"
            and mod_keyword_name(mod) in _PLUS_ONE_KEYWORD_NAMES
        ):
            return True
    for n in iter_typed_nodes(unit_node):
        amods = getattr(n, "additional_modifications", None)
        if isinstance(amods, list):
            for m in amods:
                if (
                    isinstance(m, TypedMirrorNode)
                    and tag_of(m) == "AddKeyword"
                    and mod_keyword_name(m) in _PLUS_ONE_KEYWORD_NAMES
                ):
                    return True
        if any(k in _PLUS_ONE_KEYWORD_NAMES for k in token_profile_keywords(n)):
            return True
    return False


#: The keyword ACTIONS whose own definition puts counters on a permanent, by
#: phase's effect tag, with the counter kind each places (``counter_kind``'s
#: spelling). Each verified via ``rules-lookup``: bolster (CR 701.39a, "Put N
#: +1/+1 counters on that creature"), adapt (701.46a), monstrosity (701.37a),
#: explore (701.44a, when the revealed card isn't a land), connive (701.50a,
#: when a nonland card is discarded), endure (701.63a, unless its controller
#: creates the Spirit instead), amass (701.47a, on an Army), incubate (701.53a,
#: the Incubator token enters with them), empower Jace (701.71a, loyalty
#: counters on a Jace token), and the renown trigger (702.112a). phase types
#: each as its own effect node, never a ``PutCounter`` the counter lanes read.
KEYWORD_ACTION_COUNTER_KINDS: dict[str, str] = {
    "Bolster": "P1P1",
    "Adapt": "P1P1",
    "Monstrosity": "P1P1",
    "Explore": "P1P1",
    "ExploreAll": "P1P1",
    "Connive": "P1P1",
    "Endure": "P1P1",
    "Amass": "P1P1",
    "Incubate": "P1P1",
    "Renown": "P1P1",
    "EmpowerJace": "Loyalty",
}
#: Printed keyword abilities phase keeps on ``root.keywords`` with no effect
#: node, folded (:func:`normalised_keyword_name`): awaken's spell ability puts
#: N +1/+1 counters on target land you control (CR 702.113a); a ravenous
#: permanent enters with X +1/+1 counters on it (702.156a). Tribute (702.104a)
#: stays out: the opponent chooses whether its counters are put.
KEYWORD_ABILITY_COUNTER_KINDS: dict[str, str] = {"awaken": "P1P1", "ravenous": "P1P1"}
#: What a recovered residue (``ConceptNode.recovered_by``, the recovery stage's
#: allowlisted token) means to the three keyword reads, by token:
#: ``("action", phase tag)`` — a keyword action :func:`keyword_action_events`
#: counts like phase's typed node; ``("counter", counter kind)`` — a keyword
#: ability :func:`keyword_counter_placements` counts like a printed one;
#: ``("resource", resource, side)`` — a :class:`ResourceEvent` of
#: :func:`keyword_resource_events`. Each event sits in the residue's own unit.
_RECOVERED_TOKEN_READS: dict[str, tuple[str, ...]] = {
    "connive": ("action", "Connive"),
    "amass": ("action", "Amass"),
    "devour": ("counter", "P1P1"),
    "gain_energy": ("resource", "energy", "makers"),
    "energy_payment": ("resource", "energy", "matters"),
    "foretell": ("resource", "foretell", "makers"),
}


def _recovered_reads(
    unit: AbilityUnit, kind: str
) -> Iterator[tuple[ConceptNode, tuple[str, ...]]]:
    """Each recovered effect of ``unit`` whose token reads as ``kind``
    (:data:`_RECOVERED_TOKEN_READS`), with the rest of its entry."""
    for c in unit.effects:
        read = _RECOVERED_TOKEN_READS.get(c.recovered_by)
        if read is not None and read[0] == kind:
            yield c, read[1:]


def keyword_counter_placements(
    tree: ConceptTree, *, granted: bool = True
) -> tuple[tuple[str, str], ...]:
    """Every counter placement a keyword action you perform or a keyword ability
    puts on the card: ``(keyword, counter kind)`` per occurrence, the keyword as
    phase tags it (``"Bolster"``, ``"EmpowerJace"``; ``"awaken"`` folded, read
    off ``card_keywords``) and the kind in :func:`counter_kind`'s spelling
    (``"P1P1"``, ``"Loyalty"``). A view over :func:`keyword_action_events`.

    With ``granted`` (the default) a keyword action inside an ability the card
    grants counts (Gleam of Authority's granted bolster, Security Bypass's
    granted connive); ``granted=False`` reads only each unit's own effect chain.
    Explore is read off its effect node only: phase's ``Explore`` keyword also
    marks the "whenever a creature you control explores" payoffs (Wildgrowth
    Walker).
    """
    printed = tuple(
        (folded, KEYWORD_ABILITY_COUNTER_KINDS[folded])
        for folded in map(normalised_keyword_name, tree.card_keywords)
        if folded in KEYWORD_ABILITY_COUNTER_KINDS
    )
    actions = tuple(
        (e.tag, KEYWORD_ACTION_COUNTER_KINDS[e.tag])
        for e in keyword_action_events(tree)
        if e.tag in KEYWORD_ACTION_COUNTER_KINDS and e.yours and (granted or e.own)
    )
    recovered = tuple(
        (c.recovered_by, kind)
        for unit in tree.units
        for c, (kind,) in _recovered_reads(unit, "counter")
    )
    return actions + printed + recovered


def cast_with_keyword_name(static_node: TypedMirrorNode) -> str | None:
    """The keyword a ``CastWithKeyword`` static confers on casts, or ``None``.

    Phase models "you may cast spells as though they had flash" / "<class>
    spells you cast have <keyword>" as a static whose ``mode`` is a
    ``{CastWithKeyword: {keyword: …}}`` variant (Leyline of Anticipation —
    ``Flash``; Chief Engineer — ``Convoke``). The keyword itself is a plain
    string or a parameterized variant (``{Affinity: …}``) — the KEY is the
    name. ``None`` for any other static mode (CR 601.3e).
    """
    mode = getattr(static_node, "mode", MISSING)
    if not (isinstance(mode, MirrorVariant) and mode.key == "CastWithKeyword"):
        return None
    kw = _variant_field(mode.inner, "keyword")
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def granted_next_spell_keyword(node: object) -> str | None:
    """The keyword name a ``GrantNextSpellAbility`` effect confers on the
    NEXT spell a player casts this turn, or ``None`` — Wand of the
    Worldsoul's "The next spell you cast this turn has convoke." (a
    ONE-SHOT ability grant, distinct from :func:`cast_with_keyword_name`'s
    always-on static form). ``modifier`` carries a ``HasKeyword`` node
    whose own ``keyword`` field is the same bare-string/variant shape
    :func:`mod_keyword_name` reads (CR 702.51 / 601.3e). The flash form phase
    writes as its own modifier — "The next sorcery spell you cast this turn
    can be cast as though it had flash" (Quicken), a ``CastAsThoughFlash``
    modifier — reads ``"Flash"`` (CR 702.8a).
    """
    if not isinstance(node, TypedMirrorNode) or tag_of(node) != "GrantNextSpellAbility":
        return None
    modifier = getattr(node, "modifier", MISSING)
    if tag_of(modifier) == "CastAsThoughFlash":
        return "Flash"
    if not (isinstance(modifier, TypedMirrorNode) and tag_of(modifier) == "HasKeyword"):
        return None
    kw = getattr(modifier, "keyword", None)
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def cast_keyword_type_words(node: object) -> tuple[str | None, tuple[str, ...]]:
    """``(keyword, type words)`` of a keyword a node confers on spells: an
    always-on ``CastWithKeyword`` static (:func:`cast_with_keyword_name` —
    "Spells you cast have affinity for artifacts", Sami, Wildcat Captain) or the
    next spell's (:func:`granted_next_spell_keyword` — Archway of Innovation's
    improvise). The type words are a parameterized keyword's own filter
    (affinity's "for artifacts" / "for Equipment", CR 702.41a); ``()`` for a
    bare keyword. ``(None, ())`` when the node confers none."""
    if not isinstance(node, TypedMirrorNode):
        return None, ()
    name = cast_with_keyword_name(node)
    if name is not None:
        mode = getattr(node, "mode", MISSING)
        kw = _variant_field(getattr(mode, "inner", None), "keyword")
    else:
        name = granted_next_spell_keyword(node)
        if name is None:
            return None, ()
        kw = getattr(getattr(node, "modifier", None), "keyword", None)
    param = kw.inner if isinstance(kw, MirrorVariant) else None
    return name, tuple(_type_filter_words(getattr(param, "type_filters", None)))


def yours_cast_keywords(tree: ConceptTree) -> frozenset[str]:
    """The keywords the card's always-on ``CastWithKeyword`` statics give spells
    that aren't an opponent's (:func:`cast_with_keyword_name`), normalised
    (:func:`normalised_keyword_name`) — Zhulodok, Void Gorger's ``cascade``."""
    return frozenset(
        normalised_keyword_name(name)
        for unit in tree.iter_units("static")
        if (name := cast_with_keyword_name(unit.node))
        and filter_controller(getattr(unit.node, "affected", None)) != "Opponent"
    )


def plays_lands_from_graveyard(unit: AbilityUnit) -> bool:
    """Whether a unit lets you play land cards from your graveyard (CR 116.2a:
    playing a land puts it onto the battlefield "from the zone it was in" —
    Crucible of Worlds, Ramunap Excavator): a ``GraveyardCastPermission``
    naming lands, on the static unit itself or a concept node it holds (a
    granted or chapter permission)."""
    nodes = [c.node for c in unit.iter_concepts()]
    if unit.origin == "static":
        nodes.append(unit.node)
    return any(
        static_mode_tag(n) == "GraveyardCastPermission"
        and "Land" in filter_core_types(getattr(n, "affected", None))
        for n in nodes
    )


def replays_own_permanent(unit: AbilityUnit, c: ConceptNode) -> bool:
    """Whether a ``bounce`` concept returns a permanent you control other than
    this one from the battlefield to its owner's hand (CR 400.7: cast again,
    it is a new object): Whitemane Lion's "return a creature you control",
    Chulane's activated bounce. The card returning only itself is a self-bounce
    (``SelfRef``), a graveyard card is a recall, and a foe returning a
    permanent they control (Zndrsplt's Judgment) replays nothing of yours."""
    if c.concept != "bounce" or not isinstance(c.node, TypedMirrorNode):
        return False
    target = effect_filter(c.node)
    if tag_of(target) == "SelfRef" or filter_controller(target) != "You":
        return False
    if set(filter_inzone_zones(target)) - {"Battlefield"}:
        return False
    return effect_owner_player_scope(unit.node, c.node) not in OPPONENT_ACTOR_TAGS


def _variant_field(inner: object, field: str) -> object:
    """One named field of a variant's INNER payload, across both loads.

    A single-field payload loads as a nested ``MirrorVariant`` whose key IS
    the field name (``{RevealHand: {who: "Opponents"}}`` →
    ``MirrorVariant(key="who", inner="Opponents")``); a multi-field payload
    loads as a typed struct read by attribute. ``None`` when absent.
    """
    if isinstance(inner, MirrorVariant):
        return inner.inner if inner.key == field else None
    v = getattr(inner, field, MISSING)
    return v if _present(v) else None


def static_reveal_who(static_node: TypedMirrorNode) -> str | None:
    """The revealed PLAYER of a ``RevealHand`` static mode, or ``None``.

    Phase models "players play with their hands revealed" as a static whose
    ``mode`` is ``{RevealHand: {who: …}}`` — ``who`` ∈ ``Controller`` (Enduring
    Renewal's self-reveal) / ``Opponents`` (Telepathy) / ``AllPlayers`` (Zur's
    Weirding). The hand_disruption lane gates on the reveal reaching an
    opponent's hand (CR 402.3).
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "RevealHand":
        who = _variant_field(mode.inner, "who")
        return who if isinstance(who, str) else None
    return None


# ── Batch-10 typed accessors (trigger-event / grant / static-mode cluster) ───


def double_triggers_cause_core_types(
    static_node: TypedMirrorNode,
) -> tuple[str, ...] | None:
    """The ``core_types`` of a ``DoubleTriggers`` static's ``EntersBattlefield``
    cause, or ``None`` when the static is not an ETB-cause trigger doubler.

    phase models "an [artifact or creature / permanent] entering … causes a
    triggered ability … to trigger an additional time" as a static whose ``mode``
    is ``{DoubleTriggers: {cause: {EntersBattlefield: {core_types: […]}}}}``
    (Panharmonicon — ``["Artifact", "Creature"]``; Yarok / Elesh Norn — ``[]``,
    the any-PERMANENT form, which subsumes creatures). A non-ETB cause (``Any`` —
    Strionic Resonator; ``CreatureDying`` — Teysa Karlov) and any other static
    return ``None`` — those still open ``trigger_doubling`` via
    :func:`static_mode_tag`, but carry no creature-ETB evidence. CR 603.2 +
    Panharmonicon's 2021-03-19 ruling.
    """
    mode = getattr(static_node, "mode", MISSING)
    if not (isinstance(mode, MirrorVariant) and mode.key == "DoubleTriggers"):
        return None
    cause = _variant_field(mode.inner, "cause")
    if not (isinstance(cause, MirrorVariant) and cause.key == "EntersBattlefield"):
        return None
    cores = _variant_field(cause.inner, "core_types")
    if isinstance(cores, (list, tuple)):
        return tuple(c for c in cores if isinstance(c, str))
    return ()


def _is_static_def(node: object) -> bool:
    """Whether a typed node is a static-ability DEF (carries the ``affected`` +
    ``modifications`` field pair — a trigger/ability wrapper carries neither)."""
    return (
        isinstance(node, TypedMirrorNode)
        and getattr(node, "affected", MISSING) is not MISSING
        and getattr(node, "modifications", MISSING) is not MISSING
    )


_STATIC_DEFS_CACHE_ATTR = "_xw_static_defs"
_EMBLEM_STATIC_DEFS_CACHE_ATTR = "_xw_emblem_static_defs"


def iter_static_defs(
    root: object, *, emblem: bool = False, granted: bool = False
) -> Iterator[TypedMirrorNode]:
    """Every static-ability DEF node reachable from one unit node.

    Yields the unit node itself when it IS a def (a top-level continuous
    ability — Warmonger Hellkite's "All creatures attack each combat if able")
    plus every def inside a nested ``GenericEffect.static_abilities`` list (the
    one-shot conferred form) or a ``CreateEmblem.statics`` list (an emblem's
    granted continuous ability — Narset Transcendent's "Your opponents can't
    cast noncreature spells" ultimate). The modification-less MODE statics
    (``MustAttack`` / ``DoubleTriggers`` / ``CantBeCountered``) never surface
    through :func:`iter_mod_sites` (no modifications to pair with), so the
    mode-read lanes walk defs directly via :func:`static_mode_tag`.
    Cycle-safe, same traversal as :func:`iter_mod_sites`; iterates a per-root
    memoized walk.

    ``emblem`` keeps only the defs an emblem carries (Elspeth, Sun's
    Champion's "You get an emblem with 'Creatures you control get +2/+2 and
    have flying.'"). CR 114.4: "Abilities of emblems function in the command
    zone", so an emblem's static lasts the rest of the game, unlike a one-shot
    ``GenericEffect`` grant (CR 611.2a: those last "as long as stated").
    ``granted`` adds the static defs a ``GrantAbility`` / ``GrantStaticAbility``
    grants inside the walk (:func:`iter_nested_granted_bodies` — The Book of
    Exalted Deeds' "It gains 'You can't lose the game …'"), which the plain
    walk does not descend.
    """
    defs = _static_defs(root, emblem=emblem)
    yield from defs
    if granted:
        seen = {id(d) for d in defs}
        for kind, body in iter_nested_granted_bodies(root):
            if kind == "ability" and _is_static_def(body) and id(body) not in seen:
                seen.add(id(body))
                yield body


def adds_creature_type(static_def: object) -> bool:
    """Whether a continuous effect's modifications make its objects creatures
    (CR 613.1d, layer 4): an ``AddType{core_type: Creature}`` ("is a creature in
    addition to its other types"), or a ``SetCardTypes`` naming Creature
    ("becomes a green Elk creature" — Oko, Thief of Crowns's +1, which replaces
    the other types). The animation read; an anthem over the same set is not a
    payoff of its card type."""
    for mod in getattr(static_def, "modifications", None) or ():
        tag = tag_of(mod)
        if tag == "AddType" and getattr(mod, "core_type", None) == "Creature":
            return True
        if tag == "SetCardTypes" and "Creature" in (
            getattr(mod, "core_types", None) or ()
        ):
            return True
    return False


def granted_card_types(static_def: object) -> tuple[str, ...]:
    """The card types a continuous effect gives its objects without making them
    creatures: an ``AddType`` keeping the prior types (CR 205.1b: "becomes an
    artifact in addition to its other types" — Memnarchitect, Neurok
    Transmuter), or a ``SetCardTypes`` replacing them (CR 205.1a: a Licid's
    "becomes an Aura enchantment", Vraska, Betrayal's Sting's Treasure
    artifact). Empty for an animation (:func:`adds_creature_type`,
    CR 613.1d — Karn's Touch's "becomes an artifact creature"), which this read
    leaves to the animation lanes."""
    if adds_creature_type(static_def):
        return ()
    out: list[str] = []
    for mod in getattr(static_def, "modifications", None) or ():
        tag = tag_of(mod)
        if tag == "AddType":
            types = [getattr(mod, "core_type", None)]
        elif tag == "SetCardTypes":
            types = list(getattr(mod, "core_types", None) or ())
        else:
            continue
        out.extend(t for t in types if isinstance(t, str) and t not in out)
    return tuple(out)


def _static_defs(root: object, *, emblem: bool = False) -> tuple[TypedMirrorNode, ...]:
    if isinstance(root, TypedMirrorNode):
        attr = _EMBLEM_STATIC_DEFS_CACHE_ATTR if emblem else _STATIC_DEFS_CACHE_ATTR
        cached = root.__dict__.get(attr)
        if cached is None:
            cached = tuple(_walk_static_defs(root, emblem=emblem))
            object.__setattr__(root, attr, cached)
        return cached
    return tuple(_walk_static_defs(root, emblem=emblem))


def _walk_static_defs(
    root: object, *, emblem: bool = False
) -> Iterator[TypedMirrorNode]:
    """The static-def walk; with ``emblem``, only the defs under a
    ``CreateEmblem.statics`` list."""
    seen: set[int] = set()
    stack: list[tuple[object, bool]] = [(root, False)]
    while stack:
        node, in_emblem = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        if _is_static_def(node) and (in_emblem or not emblem):
            yield node
        stack.extend((child, in_emblem) for child in effect_children(node))
        for fname in ("static_abilities", "statics"):
            child = getattr(node, fname, MISSING)
            under = in_emblem or (fname == "statics" and tag_of(node) == "CreateEmblem")
            if isinstance(child, TypedMirrorNode):
                stack.append((child, under))
            elif _present(child) and isinstance(child, list):
                stack.extend((c, under) for c in child)


# ``dataclasses.fields()`` rebuilds its tuple on every call; the deep walk
# visits millions of nodes across the 256-lane extraction, so field names are
# cached per node class.
_FIELD_NAMES_BY_CLS: dict[type, tuple[str, ...]] = {}


def _field_names(cls: type[Any]) -> tuple[str, ...]:
    names = _FIELD_NAMES_BY_CLS.get(cls)
    if names is None:
        names = tuple(f.name for f in fields(cls))
        _FIELD_NAMES_BY_CLS[cls] = names
    return names


# Memoized flat walk, stored OUTSIDE the dataclass fields so ``to_dict`` /
# ``__eq__`` / the sidecar JSON never see it. Sound because a mirror tree is
# frozen after build — corrections/synthesis produce new nodes via ``replace``
# rather than mutating, so a subtree's walk can never go stale.
_WALK_CACHE_ATTR = "_xw_typed_walk"


def _typed_nodes(root: object) -> tuple[TypedMirrorNode, ...]:
    """The flat walk behind :func:`_iter_typed_nodes`, as a memoized tuple:
    computed once per ``TypedMirrorNode`` root — the lane extraction
    re-queries the same immutable subtree hundreds of times per card, so the
    repeat traversals collapse to a cached-tuple read."""
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_WALK_CACHE_ATTR)
        if cached is None:
            cached = tuple(_walk_typed_nodes(root))
            object.__setattr__(root, _WALK_CACHE_ATTR, cached)
        return cached
    return tuple(_walk_typed_nodes(root))


def _iter_typed_nodes(root: object) -> Iterator[TypedMirrorNode]:
    """Every typed node reachable from ``root`` via dataclass fields /
    variant payloads / lists — the generic deep walk behind the narrow
    unique-tag scans (cycle-safe, field-order agnostic). Iterates the
    memoized flat walk (see :func:`_typed_nodes`)."""
    yield from _typed_nodes(root)


def _walk_typed_nodes(root: object) -> Iterator[TypedMirrorNode]:
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, TypedMirrorNode):
            yield node
            for fname in _field_names(type(node)):
                child = getattr(node, fname)
                # Scalar leaves can't recurse — keep them off the stack.
                if isinstance(child, (TypedMirrorNode, MirrorVariant, list)):
                    stack.append(child)
        elif isinstance(node, MirrorVariant):
            stack.append(node.inner)
        elif isinstance(node, list):
            stack.extend(
                c for c in node if isinstance(c, (TypedMirrorNode, MirrorVariant, list))
            )


def has_nested_roll_die(node: object) -> bool:
    """Whether a ``RollDie`` tag (CR 706) is reachable ANYWHERE under
    ``node`` — a die roll buried inside a ``Composite`` cost's
    ``EffectCost`` (Clay Golem's "{6}, Roll a d8: Monstrosity X") or a
    granted quoted ability's chained ``sub_ability`` (Captain Rex Nebula's
    "Crash Land — … roll a six-sided die …" grant) that the flat per-unit
    concept-node walk never surfaces as its own node (both cards' OWN
    top-level nodes decorate ``other`` with no grounding raw). The
    dice_makers lane's structural fallback; :func:`_iter_typed_nodes`'s
    deep field-walk reaches the nested node regardless of which container
    (cost / static / granted-ability chain) carries it.
    """
    return any(tag_of(n) == "RollDie" for n in _iter_typed_nodes(node))


#: The effect tags phase types a coin flip with (CR 705.1):
#: ``FlipCoins{flips: Exactly{count} | UntilLoss}``. The concept map
#: (``core.EFFECT_CONCEPTS``) maps each to ``flip_coin``.
FLIP_COIN_TAGS: frozenset[str] = frozenset({"FlipCoins"})


def is_flip_coin(node: object) -> bool:
    """Whether ``node`` is a coin flip (:data:`FLIP_COIN_TAGS`)."""
    return tag_of(node) in FLIP_COIN_TAGS


def has_nested_flip_coin(node: object) -> bool:
    """Whether a ``FlipCoins`` tag (CR 705.1) is reachable ANYWHERE under
    ``node`` — a coin flip buried inside a granted activated ability's
    ``GrantAbility.definition`` (Frenetic Sliver's "All Slivers have
    '{0}: ... flip a coin ...'") that the flat per-unit concept-node walk
    never surfaces as its own node (the concept node IS the GrantAbility
    modification itself, carrying no ``flip_coin``-mapped tag of its own).
    The ``coin_flip`` lane's structural fallback, the
    :func:`has_nested_roll_die` sibling.
    """
    return any(is_flip_coin(n) for n in _iter_typed_nodes(node))


def iter_flip_outcomes(node: object) -> Iterator[TypedMirrorNode]:
    """Each outcome of every coin flip under ``node`` (a
    ``FlipCoins`` ``win_effect`` / ``lose_effect``, CR 705.2), granted bodies
    included — the drawback outcomes too, which the effect walk leaves out
    (:func:`is_own_drawback`: Frenetic Sliver's "If you win the flip, exile ~
    and return it to the battlefield")."""
    for n in _iter_typed_nodes(node):
        if not is_flip_coin(n):
            continue
        for field in _FLIP_OUTCOME_FIELDS:
            outcome = getattr(n, field, None)
            if isinstance(outcome, TypedMirrorNode):
                yield outcome


def has_nested_fight(node: object) -> bool:
    """Whether a ``Fight`` tag (CR 701.12) is reachable ANYWHERE under
    ``node`` — a fight buried inside a granted trigger (Cherished
    Hatchling's cast-a-Dinosaur grant, Grothama's "Other creatures have
    '... it fights Grothama.'"), a granted activated ability (Setessan
    Tactics' "gain '{T}: ... fights ...'"), a ``CreateEmblem`` (Kiora,
    Master of the Depths' -8), or a token-copy EXCEPTION clause
    (Aggressive Biomancy / Mythos of Illuna's "... except they have
    'When this token enters, ... it fights ...'") — none of which the
    flat per-unit concept-node walk ever surfaces as its own node. The
    ``fight_makers`` lane's structural fallback, the
    :func:`has_nested_roll_die` sibling.
    """
    return any(tag_of(n) == "Fight" for n in _iter_typed_nodes(node))


def has_nested_extra_turn(node: object) -> bool:
    """Whether an ``ExtraTurn`` tag (CR 500.7) is reachable ANYWHERE under
    ``node`` — an extra-turn grant buried inside a ``Vote``'s
    ``per_choice_effect`` branch (Expropriate, Plea for Power's "time"
    vote outcome), a ``FlipCoins`` ``win_effect`` (Stitch in
    Time, Ral Zarek's -7), or a static ability's ``GrantAbility.
    definition`` (Ichormoon Gauntlet's granted planeswalker loyalty
    ability) — a modification's ``definition`` is past the reach of
    ``_walk_effects`` (:data:`_EFFECT_WALK_FIELDS`), and the deep walk
    covers every nesting at once. The ``extra_turns`` lane's structural fallback,
    the :func:`has_nested_roll_die` sibling (task #85, phase v0.23.0).

    Also a ``ControlNextTurn`` whose ``grant_extra_turn_after`` is set: Emrakul,
    the Promised End's "After that turn, that player takes an extra turn" rides
    the control effect as a flag, not an ``ExtraTurn`` node. Its rulings confirm
    the extra turn is real ("each ability's effect will create an extra turn"),
    added after the controlled turn (CR 500.7).
    """
    return any(
        tag_of(n) == "ExtraTurn"
        or (
            tag_of(n) == "ControlNextTurn"
            and getattr(n, "grant_extra_turn_after", None) is True
        )
        for n in _iter_typed_nodes(node)
    )


# ── ADR-0037/0038 W1 batch-3 / task #86 — the granted-ability shared descent ─
# ``connive_makers`` and ``opponent_cast_matters`` share one gap shape: the
# card's real trigger lives NESTED inside a GRANTED-ability construct the
# flat per-unit ``AbilityUnit`` walk never surfaces as its own unit. Two
# corpus-verified shapes carry a trigger DEFINITION this way (a node with the
# same ``S_trigger``/``S_triggers`` field shape as a top-level trigger unit's
# own ``.node``, so any predicate written for a top-level trigger — e.g.
# :func:`is_dies_return_trigger`'s sibling — applies unchanged):
#
# * a ``GrantTrigger`` modification's ``trigger`` field — a static ability's
#   granted triggered ability (Security Bypass's Aura grant, Hunting
#   Grounds's Threshold grant, Copycrook's copy-exception grant, Blink's
#   Alien Angel token grant, Tyrant's Familiar's Lieutenant-granted attack
#   trigger, Showstopper's until-end-of-turn dies-trigger grant);
# * a ``CreateEmblem`` effect's ``triggers`` list (Jace, Unraveler of
#   Secrets's -8 ultimate, Garruk, Caller of Beasts's -7 ultimate).
#
# task #86 adds the SIBLING shape a bare ``GrantAbility``/``GrantStaticAbility``
# modification carries — an ABILITY-shaped body (its own ``.definition``
# field, never a trigger def) that phase v0.23.0 now emits fully typed: Arc
# Spitter's Equip-granted "{1}: ~ deals 1 damage to target creature that's
# blocking it.", Deadeye Navigator's soulbond-granted "{1}{U}: Exile ~, then
# return it to the battlefield under your control." Both shapes (trigger and
# ability) now share ONE deep walk + tag dispatch
# (:func:`iter_nested_granted_bodies`) instead of two independent tag-scans —
# :func:`iter_nested_trigger_defs` is now a thin filter over it (the trigger-
# shaped bodies only), and :func:`iter_nested_granted_effect_concepts` walks
# EVERY yielded body (trigger AND ability alike) through the same effect/
# sub_ability/execute chain a top-level unit's own effects walk uses
# (:func:`walk_effect_chain`) — so a granted trigger's ``execute.effect``
# and a granted ability's ``definition.effect`` decorate identically, tagged
# "granted" only by way of never appearing in ``unit.effects`` otherwise.
#
# Soulbond with NO node at all (Thundering Mightmare's soulbond-paired
# grant — ``modifications: []``) stays a no-residue synthesis case, not a
# structural one; see ``tree_synthesis.has_structural_opponent_cast_matters``.
_GRANTED_TRIGGER_TAGS = frozenset({"GrantTrigger"})
_GRANTED_ABILITY_TAGS = frozenset({"GrantAbility", "GrantStaticAbility"})


def iter_nested_granted_bodies(
    node: object,
) -> Iterator[tuple[str, TypedMirrorNode]]:
    """Every ``(kind, body)`` pair reachable under ``node`` via a granted-
    ability-shaped modification (see module note above): ``kind`` is
    ``"trigger"`` for a ``GrantTrigger``'s ``trigger`` field or a
    ``CreateEmblem``'s ``triggers`` list entries (trigger-DEFINITION shaped
    — the same ``.mode``/``.execute`` field shape as a top-level trigger
    unit's own node), or ``"ability"`` for a ``GrantAbility``/
    ``GrantStaticAbility``'s ``definition`` field (ability-DEFINITION
    shaped — ``.effect``/``.cost``/``.sub_ability``, never a trigger's
    ``.mode``). ONE deep walk (:func:`_iter_typed_nodes`), ONE tag dispatch
    — every "read something buried inside a static's grant" lane in this
    module shares this single descent (:func:`iter_nested_trigger_defs`,
    :func:`iter_nested_granted_effect_concepts`) instead of re-deriving its
    own tag-scan.
    """
    for n in _iter_typed_nodes(node):
        t = tag_of(n)
        if t in _GRANTED_TRIGGER_TAGS:
            trig = getattr(n, "trigger", None)
            if isinstance(trig, TypedMirrorNode):
                yield ("trigger", trig)
        elif t == "CreateEmblem":
            trigs = getattr(n, "triggers", MISSING)
            if _present(trigs) and isinstance(trigs, list):
                for trig in trigs:
                    if isinstance(trig, TypedMirrorNode):
                        yield ("trigger", trig)
        elif t in _GRANTED_ABILITY_TAGS:
            definition = getattr(n, "definition", None)
            if isinstance(definition, TypedMirrorNode):
                yield ("ability", definition)


def iter_nested_trigger_defs(node: object) -> Iterator[TypedMirrorNode]:
    """Every trigger DEFINITION node reachable under ``node`` via a
    ``GrantTrigger``/``CreateEmblem`` granted-ability shape (see module note
    above). The connive_makers / opponent_cast_matters shared descent — each
    lane applies its own predicate to the yielded nested trigger defs, the
    same predicate it already applies to a top-level trigger unit's node.
    A thin filter over :func:`iter_nested_granted_bodies` — deliberately
    excludes the ``"ability"`` bodies a bare ``GrantAbility``/
    ``GrantStaticAbility`` yields (no corpus card in the original W1 batch-3
    census wires a TRIGGER through one — only activated/static abilities;
    see :func:`iter_nested_granted_effect_concepts` for the sibling lane
    that DOES want those).
    """
    for kind, body in iter_nested_granted_bodies(node):
        if kind == "trigger":
            yield body


# ADR-0038 W3 batch 2 unit 5 — a NARROW sibling of
# :func:`iter_nested_trigger_defs`, scoped separately (not folded into
# that shared helper — it feeds 4 OTHER already-promoted lanes this batch
# must not perturb) for the ``CreateDelayedTrigger.condition.trigger``
# watcher shape (:func:`is_damage_reflect_trigger_def`'s module note):
# Subira, Tulzidi Caravanner's "Until end of turn, whenever a creature you
# control with power 2 or less deals combat damage to a player, draw a
# card" — the delayed ability's WATCHER trigger def, not co-located with
# its top-level activated-ability unit.
def iter_delayed_trigger_condition_defs(
    node: object, *, next_event: bool = False
) -> Iterator[TypedMirrorNode]:
    """Every trigger DEFINITION node reachable under ``node`` via a
    ``CreateDelayedTrigger`` effect's ``condition {WheneverEvent: trigger}``
    watcher field — with ``next_event`` the one-shot ``WhenNextEvent`` watcher
    too ("When you next cast a spell with {X} in its mana cost this turn" —
    Brass Infiniscope)."""
    tags = ("WheneverEvent", "WhenNextEvent") if next_event else ("WheneverEvent",)
    for n in _iter_typed_nodes(node):
        if tag_of(n) != "CreateDelayedTrigger":
            continue
        cond = getattr(n, "condition", MISSING)
        if not (isinstance(cond, TypedMirrorNode) and tag_of(cond) in tags):
            continue
        trig = getattr(cond, "trigger", MISSING)
        if isinstance(trig, TypedMirrorNode):
            yield trig


def iter_unit_trigger_defs(
    unit: AbilityUnit, *, delayed: bool = False
) -> Iterator[TypedMirrorNode]:
    """Every trigger DEFINITION ``unit`` carries: its own node when the unit is
    a trigger, each trigger it grants (:func:`iter_nested_trigger_defs` — an
    Aura's or Equipment's "Whenever … ", an emblem's), and with ``delayed``
    each delayed trigger's watcher (:func:`iter_delayed_trigger_condition_defs`
    — "Until your next turn, whenever you cast an instant or sorcery spell"). A
    lane applies the same predicate to each."""
    if unit.origin == "trigger":
        yield unit.node
    yield from iter_nested_trigger_defs(unit.node)
    if delayed:
        yield from iter_delayed_trigger_condition_defs(unit.node)


class GrantedTrigger(NamedTuple):
    """A trigger one unit grants, with the object(s) it is granted to."""

    trigger: TypedMirrorNode  # the granted trigger definition
    grantee: object  # the granting def's ``affected``: a filter node or a tag
    chosen: bool  # the grantee is a target the ability chooses


def iter_granted_triggers(unit: AbilityUnit) -> Iterator[GrantedTrigger]:
    """Every trigger ``unit`` grants through a ``GrantTrigger`` modification
    (CR 113.1a: "Abilities can also be granted to objects by rules or
    effects"), paired with who gets it: the granting def's ``affected`` set
    ("Creatures you control gain '…'" — Showstopper; "Enchanted creature has
    '…'" — Infernal Scarring; a soulbond pair — Doom Weaver), or, for "It gains
    '…'" / "those creatures gain '…'", the chosen target the chain threads to it
    (:func:`iter_threaded_target_statics` — Clavileño's attacking Vampire, Rabid
    Attack's "target creatures you control"; ``chosen`` marks those). A
    back-reference the thread can't follow stays its tag. The deep mod-site walk
    (:func:`iter_mod_sites`), so a modal arm's or a created token's grant is
    read too (a Pest token's own "When this creature dies" — ``SelfRef``)."""
    chosen: dict[int, object] = {}
    for tag, resets in (("ParentTarget", None), ("TrackedSet", ends_target_thread)):
        for tgt, sdef in iter_threaded_target_statics(
            unit.node, affected_tag=tag, resets_thread=resets
        ):
            chosen.setdefault(id(sdef), tgt)
    for sdef, mod in iter_mod_sites(unit.node, deep=True):
        if tag_of(mod) not in _GRANTED_TRIGGER_TAGS:
            continue
        trig = getattr(mod, "trigger", None)
        if not isinstance(trig, TypedMirrorNode):
            continue
        target = chosen.get(id(sdef))
        if target is not None:
            yield GrantedTrigger(trig, target, chosen=True)
        else:
            yield GrantedTrigger(trig, static_affected(sdef, unit), chosen=False)


# ADR-0038 W3 batch 2 unit 2 — the typed_spellcast lane's shared nested-mode
# descent. A tribal cast-cost-modifier static (CR 601.2f / 702.2's
# keyword-spell grants: Freerunning, Prowl, Cascade, "costs {N} less") can
# live at three tree positions phase carries with the SAME ``S_static_
# abilities``/``S_definition`` field shape (``.mode`` / ``.affected``):
# top-level (the plain Banneret family — Ballyrush Banneret), nested inside
# a ``GrantStaticAbility`` modification's ``.definition`` (Acolyte of
# Bahamut's "Commander creatures you own have '... Dragon spell ... costs
# {2} less ...'"), or nested inside a created TOKEN's own
# ``static_abilities`` list (The Eleventh Hour's Human token granting
# "Doctor spells you cast cost {1} less"). One predicate over
# :func:`_iter_typed_nodes`'s deep walk covers all three tree positions.
def iter_nested_spellcast_static_modes(node: object) -> Iterator[TypedMirrorNode]:
    """Every node reachable under ``node`` whose ``.mode`` field is a
    ``CastWithKeyword`` or ``ModifyCost`` variant — the typed_spellcast
    lane's structural source (see module note above)."""
    for n in _iter_typed_nodes(node):
        mode = getattr(n, "mode", MISSING)
        if isinstance(mode, MirrorVariant) and mode.key in (
            "CastWithKeyword",
            "ModifyCost",
        ):
            yield n


def has_nested_connive(node: object) -> bool:
    """Whether a ``Connive`` tag (CR 701.50a) is reachable inside a nested
    trigger definition under ``node`` — :func:`iter_nested_trigger_defs`'s
    Security Bypass ("Enchanted creature has '... it connives.'") / Copycrook
    (the copy-exception grant) shape, a granted "it connives" trigger the
    flat per-unit concept-node walk never surfaces as its own node. The
    connive_makers lane's structural fallback.
    """
    return any(
        tag_of(m) == "Connive"
        for trig in iter_nested_trigger_defs(node)
        for m in _iter_typed_nodes(trig)
    )


def is_opponent_cast_trigger_def(trig: object) -> bool:
    """Whether a trigger DEFINITION node — a top-level trigger unit's own
    ``.node`` OR a nested def from :func:`iter_nested_trigger_defs` — is CR
    102.2/102.3's opponent-cast punisher shape: a ``SpellCast`` /
    ``SpellCastOrCopy`` mode whose recipient names an opponent. One
    predicate for both tree positions (the opponent_cast_matters lane's own
    top-level read, reused unchanged on the nested shape — Hunting Grounds's
    Threshold grant, Jace's -8 emblem, Blink's Alien Angel token grant).
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if trigger_def_event(trig) not in ("cast_spell", "spellcastorcopy"):
        return False
    vt = getattr(trig, "valid_target", None)
    return tag_of(vt) in OPPONENT_ACTOR_TAGS or (
        tag_of(vt) == "Typed" and filter_controller(vt) == "Opponent"
    )


def is_creature_cast_trigger_def(trig: object) -> bool:
    """Whether a trigger DEFINITION node — a top-level trigger unit's own
    ``.node`` OR a nested def from :func:`iter_nested_trigger_defs` — is CR
    701.5a/603.2's creature-spell cast payoff shape: a ``SpellCast`` mode
    whose watched-spell filter carries the Creature core type. One
    predicate for both tree positions (the creature_cast_trigger lane's own
    top-level read, reused unchanged on the nested shape — Garruk, Caller
    of Beasts's -7 emblem, Blink's Alien Angel token grant). Scope-blind by
    design (an opponent-cast watcher and a self-cast watcher both count —
    the lane hard-emits scope "any").
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if trigger_def_event(trig) != "cast_spell":
        return False
    return "Creature" in filter_core_types(getattr(trig, "valid_card", None))


def is_creature_etb_trigger_def(trig: object) -> bool:
    """Whether a trigger DEFINITION node — a top-level trigger unit's own
    ``.node`` OR a nested def from :func:`iter_nested_trigger_defs` /
    :func:`iter_delayed_trigger_condition_defs` — is CR 603.6a's creature-ETB
    payoff shape: a ``ChangesZone``/``ChangesZoneAll`` mode landing on the
    battlefield (``trigger_def_event`` normalizes both to ``"enters"``) whose
    watched-object filter carries the Creature core type, OR the compound
    ``entersorattacks`` event (Kindred Discovery's "enters or attacks" —
    still genuinely an ETB payoff for the enters half; CR 603.2's "whenever"
    condition names two alternative events, and this predicate only asserts
    the entering one applies). One predicate for FOUR tree positions
    (mirroring :func:`is_creature_cast_trigger_def`'s shared-descent
    precedent): a top-level trigger unit, a ``GrantTrigger``/``CreateEmblem``
    nested def (Nurturing Presence's Aura grant; Kiora/Huatli/Mila's
    emblems), and a ``CreateDelayedTrigger``'s ``WheneverEvent`` watcher
    (First Day of Class/Rite of Harmony/Theoretical Duplication's "this
    turn" delayed trigger — an Instant/Sorcery installing a temporary ETB
    watcher, not itself an enters event).
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if trigger_def_event(trig) not in ENTERS_EVENTS:
        return False
    return "Creature" in filter_core_types(getattr(trig, "valid_card", None))


def damage_to_player_trigger_kind(trig: object) -> str | None:
    """Whether a trigger DEFINITION node — a top-level trigger unit's own
    ``.node`` OR a nested def from :func:`iter_nested_trigger_defs` — is CR
    119.3/510.1b's damage-connect payoff shape: a ``DamageDone`` mode whose
    recipient (:func:`damage_recipient_is_player`) reaches a player, no
    SUBTYPE-carrying recipient (an object, not a player). ``None`` when not
    this shape; else the typed ``damage_kind`` (``"CombatOnly"`` routes
    combat_damage_matters, anything else damage_to_opp_matters — the SAME
    split :func:`~mtg_utils._analysis.lanes._combat_damage_lanes`
    applies at its top-level read, now shared with the granted-ability
    nested position (Snake Umbra's Aura grant, Talon of Pain's static
    grant, Sword of War and Peace's Equipment grant, Stormbreath Dragon's
    monstrosity grant).
    """
    if not isinstance(trig, TypedMirrorNode):
        return None
    if trigger_def_event(trig) != "deals_damage":
        return None
    vt = getattr(trig, "valid_target", None)
    if vt is None or not damage_recipient_is_player(vt):
        return None
    if filter_subtypes(vt):
        return None  # a SUBTYPE-carrying recipient is an object, not a player
    return trigger_damage_kind(trig)


# ``DamageReceived``-shaped trigger DEFS carry a "reflection" execute tag
# (CR 120.3): ``DealDamage`` (a single target) or ``DamageAll`` (Arcbond's
# "each other creature and each player"). ``DamageEachPlayer`` is excluded —
# a distinct "everyone loses life together" edict, not a reflection.
_DAMAGE_REFLECT_EXECUTE_TAGS: frozenset[str] = frozenset({"DealDamage", "DamageAll"})


def _is_damage_received_mode(mode: object) -> bool:
    """Whether a trigger def's ``mode`` field is CR 120.3's "is dealt
    damage" watcher — the native ``DamageReceived`` tag (Boros Reckoner) OR
    phase's own ``Unknown``-mode fallback wrapping the raw phrase (Donna
    Noble's compound "~ or a creature it's paired with" subject defeats
    phase's mode derivation)."""
    return mode == "DamageReceived" or (
        isinstance(mode, MirrorVariant)
        and mode.key == "Unknown"
        and isinstance(mode.inner, str)
        and "dealt damage" in mode.inner.lower()
    )


def is_damage_reflect_trigger_def(node: object) -> bool:
    """Whether ``node`` is CR 120.3 damage-reflection: "whenever [it] is
    dealt damage, it deals that much damage to X", in either of the two
    shapes phase carries it in:

    * A trigger DEF whose OWN ``mode``/``execute`` are co-located — a
      top-level trigger unit's own node (Donna Noble; the SAME shape
      Boros Reckoner's native top-level form already reads) or a static's
      ``GrantTrigger`` modification's ``trigger`` field (Spiteful Sliver's
      tribal grant).
    * A ``CreateDelayedTrigger`` EFFECT node, whose watcher (``mode``) lives
      on ``condition.trigger`` and whose resulting ability lives on a
      SIBLING ``effect`` field, not co-located with the watcher (Arcbond's
      targeted "whenever THAT creature is dealt damage, it deals that much
      damage to each other creature and each player" — a delayed trigger
      the spell creates, not a trigger the permanent itself carries).

    Reads ``mode``/``execute`` directly — bypassing :func:`trigger_def_event`'s
    normalization (which folds the ``Unknown``-mode case to ``"other"``) —
    so the SAME predicate applies at any nesting depth via
    :func:`_iter_typed_nodes`'s deep walk.
    """
    if not isinstance(node, TypedMirrorNode):
        return False
    if tag_of(node) == "CreateDelayedTrigger":
        cond = getattr(node, "condition", MISSING)
        if not (isinstance(cond, TypedMirrorNode) and tag_of(cond) == "WheneverEvent"):
            return False
        trig = getattr(cond, "trigger", MISSING)
        if not (
            isinstance(trig, TypedMirrorNode)
            and _is_damage_received_mode(getattr(trig, "mode", MISSING))
        ):
            return False
        wrapper = getattr(node, "effect", MISSING)
        if not isinstance(wrapper, TypedMirrorNode):
            return False
        return tag_of(getattr(wrapper, "effect", None)) in _DAMAGE_REFLECT_EXECUTE_TAGS
    if not _is_damage_received_mode(getattr(node, "mode", MISSING)):
        return False
    execute = getattr(node, "execute", MISSING)
    if not isinstance(execute, TypedMirrorNode):
        return False
    return tag_of(getattr(execute, "effect", None)) in _DAMAGE_REFLECT_EXECUTE_TAGS


def mana_restricted_to_multicolored(node: object) -> bool:
    """Whether a ``Mana`` effect's mana is restricted to multicolored spells (CR
    105.2b) — "Spend this mana only to cast a multicolored spell" (Obsidian Obelisk,
    Pillar of the Paruns): :func:`mana_spell_type_restriction` reads ``SpellType:
    Multicolored``."""
    return (
        tag_of(node) == "Mana"
        and isinstance(node, TypedMirrorNode)
        and mana_spell_type_restriction(node) == "Multicolored"
    )


def iter_threaded_target_statics(
    ability_like: object,
    *,
    affected_tag: str = "ParentTarget",
    resets_thread: Callable[[TypedMirrorNode], bool] | None = None,
    effect_tags: frozenset[str] = frozenset(),
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, static_def)`` pairs for every
    ``affected_tag``-affected (default ``ParentTarget``) nested static in one
    ability/trigger chain, the target THREADED through the chain.

    ``effect_tags`` also yields ``(resolved_target_filter, effect)`` for each
    effect of one of those tags whose own ``target`` is ``affected_tag`` — an
    effect's back-reference resolved by the same thread ("Target creature you
    control gets +2/+2 until end of turn. Return it to its owner's hand at the
    beginning of the next end step" — Dragon Mask). The thread is followed into a
    delayed trigger's effect ("Whenever that creature attacks the monarch this
    turn, it gains double strike" — Okoye, Mighty and Adored).

    Mirrors the live v14 tracked-target walk over the typed substrate: phase
    parses "target creature gains <kw> / becomes a 1/1" as a ``GenericEffect``
    whose nested static's ``affected`` is ``ParentTarget``, with the real
    target riding the ``GenericEffect``'s own ``target`` (Jump, Gods Willing)
    or an EARLIER effect's target the static re-references — the "It gains X"
    / "It becomes a 0/0" idiom ("Untap target creature. It gains reach" — Aim
    High; Cyclone Sire's land animate), resolved by threading the most recent
    non-ParentTarget filter through the ``effect`` / ``sub_ability`` /
    ``execute`` chain. Callers apply their own gates on the resolved filter.

    ``affected_tag="TrackedSet"`` reads the plural back-reference instead —
    "those creatures gain X" over the chain's own targets (phase v0.94.0's
    Arm the Cathars). ``resets_thread`` names the effects that END the thread
    (the caller's call: e.g. a token producer or a mass effect, after which
    "it" / "those" no longer names a chosen target); such an effect clears
    the tracked target instead of supplying one.
    """
    tracked: object | None = None
    seen: set[int] = set()
    queue: list[object] = [ability_like]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        execute = getattr(node, "execute", MISSING)
        if isinstance(execute, TypedMirrorNode):
            queue.append(execute)
        eff = getattr(node, "effect", MISSING)
        if isinstance(eff, TypedMirrorNode) and id(eff) not in seen:
            seen.add(id(eff))
            tgt = getattr(eff, "target", MISSING)
            if resets_thread is not None and resets_thread(eff):
                tracked = None
            elif _present(tgt) and tag_of(tgt) in ("Typed", "Or", "And"):
                tracked = tgt
            if (
                tag_of(eff) in effect_tags
                and tracked is not None
                and tag_of(tgt) == affected_tag
            ):
                yield tracked, eff
            if tag_of(eff) == "CreateDelayedTrigger":
                delayed = getattr(eff, "effect", MISSING)
                if isinstance(delayed, TypedMirrorNode):
                    queue.append(delayed)
            if tag_of(eff) == "GenericEffect" and tracked is not None:
                nested = getattr(eff, "static_abilities", MISSING)
                sts = nested if _present(nested) and isinstance(nested, list) else []
                for st in sts:
                    if tag_of(getattr(st, "affected", None)) == affected_tag:
                        yield tracked, st
            sub2 = getattr(eff, "sub_ability", MISSING)
            if isinstance(sub2, TypedMirrorNode):
                queue.append(sub2)
            # "Target creature gains your choice of vigilance, lifelink, or
            # indestructible" (Gideon Blackblade, Orcish Medicine): each choice
            # is a ``ChooseOneOf`` branch granting to the threaded target.
            if tag_of(eff) == "ChooseOneOf":
                branches = getattr(eff, "branches", MISSING)
                if _present(branches) and isinstance(branches, list):
                    queue.extend(branches)
        sub = getattr(node, "sub_ability", MISSING)
        if isinstance(sub, TypedMirrorNode):
            queue.append(sub)


#: The modifications that hand an object a quoted ability (CR 613.1f: layer 6,
#: ability-adding effects): a triggered one (Feign Death's "When this creature
#: dies, return it …") or an activated / static one ("{T}: Return target nonland
#: permanent …"). The ``mod_tags`` a caller hands :func:`unit_keyword_grants` for
#: a quoted ability rather than a keyword.
ABILITY_GRANT_MOD_TAGS: frozenset[str] = _GRANTED_TRIGGER_TAGS | _GRANTED_ABILITY_TAGS
_ADD_KEYWORD: frozenset[str] = frozenset({"AddKeyword"})


def iter_single_target_grants(
    ability_like: object, *, mod_tags: frozenset[str] = _ADD_KEYWORD
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, AddKeyword_mod)`` pairs for the SINGLE-TARGET
    keyword grants of one SPELL/ability node (CR 700.2) — the AddKeyword
    projection of :func:`iter_threaded_target_statics`, mirroring the live v14
    ``_single_target_keyword_grant_markers`` emit. The caller applies the live
    gates (Creature core on the resolved filter; abilities only — the
    trigger-conferred grants ride the DEEP local-target arm).
    """
    for tracked, st in iter_threaded_target_statics(ability_like):
        mods = getattr(st, "modifications", MISSING)
        for mod in mods if _present(mods) and isinstance(mods, list) else []:
            if tag_of(mod) in mod_tags:
                yield tracked, mod


def iter_deep_target_grants(
    root: object, *, mod_tags: frozenset[str] = _ADD_KEYWORD
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(local_target_filter, AddKeyword_mod)`` pairs for every
    ``GenericEffect`` leaf under ``root`` with a LOCAL Typed target and a
    ``ParentTarget``-affected AddKeyword static.

    Mirrors the live DEEP marker (``project._deep_single_target_grant``
    shapes): the same leaf phase structures for a trigger-conferred grant
    ("target artifact creature you control … gains indestructible" —
    Aethershield Artificer), a modal arm, a Saga chapter, or a quoted
    GrantAbility definition — the flat threaded walk
    (:func:`iter_single_target_grants`) never descends there. LOCAL target
    only (the "It gains X" tracked idiom stays with the flat walk, exactly
    the live split). CR 700.2.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "GenericEffect":
            continue
        tgt = getattr(n, "target", MISSING)
        if not _present(tgt) or tag_of(tgt) not in ("Typed", "Or", "And"):
            continue
        nested = getattr(n, "static_abilities", MISSING)
        for st in nested if _present(nested) and isinstance(nested, list) else []:
            if tag_of(getattr(st, "affected", None)) != "ParentTarget":
                continue
            mods = getattr(st, "modifications", MISSING)
            for mod in mods if _present(mods) and isinstance(mods, list) else []:
                if tag_of(mod) in mod_tags:
                    yield tgt, mod


def spell_count_at_least(root: object) -> int:
    """The largest ``count`` of any ``YouCastSpellCountAtLeast`` condition on
    the card (``0`` when none).

    phase gates "Activate only if you've cast two or more spells this turn"
    (Xerex Strobe-Knight) as an activation-restriction condition ``{type:
    YouCastSpellCountAtLeast, count: 2}`` — the CONDITION form of the
    second-spell velocity payoff (the trigger form rides the
    ``NthSpellThisTurn`` constraint, :func:`trigger_constraint_tag`). The tag
    is unique to conditions, so the deep typed scan is precise. CR 601.
    """
    best = 0
    for n in _iter_typed_nodes(root):
        if tag_of(n) == "YouCastSpellCountAtLeast":
            c = getattr(n, "count", None)
            if isinstance(c, int) and c > best:
                best = c
    return best


def counts_behind_another_player(root: object) -> frozenset[int]:
    """The ids of the ``ObjectCount`` nodes under ``root`` that count your own
    objects in a comparison another player wins: "each opponent who controls
    more artifacts than you" (Ward of Bones), "if an opponent controls more
    lands than you". The check is for having FEWER of them, so the count is no
    reason to play more."""
    out: set[int] = set()
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "QuantityComparison":
            continue
        sides = []
        for side in (getattr(n, "lhs", None), getattr(n, "rhs", None)):
            qty = getattr(side, "qty", None) if tag_of(side) == "Ref" else None
            if tag_of(qty) != "ObjectCount":
                break
            sides.append((qty, filter_controller(getattr(qty, "filter", None))))
        if len(sides) != 2:
            continue
        (lq, lc), (rq, rc) = sides
        comp = getattr(n, "comparator", None)
        if comp in ("GT", "GE") and rc == "You" and lc not in (None, "You"):
            out.add(id(rq))
        elif comp in ("LT", "LE") and lc == "You" and rc not in (None, "You"):
            out.add(id(lq))
    return frozenset(out)


def spell_velocity_static_two(root: object) -> bool:
    """True when a ``QuantityComparison`` (or the ``OnlyIfQuantity`` replacement-
    condition variant sharing the identical comparator/lhs/rhs shape — Effortless
    Master's ETB "enters with two +1/+1 counters if you've cast two or more spells
    this turn") gates a payoff on "you've cast two or more spells this turn" —
    ``lhs`` a ``Ref`` over ``SpellsCastThisTurn`` (``scope: Controller``), comparator
    ``GE`` with ``rhs == 2`` (or the equivalent ``GT`` / ``rhs == 1``).

    The STATIC-CONDITION form of second_spell_matters (b3 recall): Brightspear
    Zealot's "gets +2/+0 as long as you've cast two or more spells this turn"
    hangs the count on a continuous-ability ``condition`` — a
    ``QuantityComparison`` — distinct from the ``YouCastSpellCountAtLeast``
    activation restriction (:func:`spell_count_at_least`, the Xerex Strobe-Knight
    "activate only if" form) and the ``NthSpellThisTurn`` trigger constraint
    (:func:`trigger_constraint_tag`, the Cori-Steel Cutter "your second spell"
    form). The threshold is pinned to exactly two-or-more so a "three or more
    spells" velocity payoff (Arclight Phoenix — a broader lane, not the
    second-spell counter) never fires, and the ``Controller`` scope excludes an
    opponent-cast watcher (Captain Mar-Vell). CR 603.2.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) not in ("QuantityComparison", "OnlyIfQuantity"):
            continue
        lhs = getattr(n, "lhs", None)
        qty = getattr(lhs, "qty", None) if lhs is not None else None
        if qty is None or tag_of(qty) != "SpellsCastThisTurn":
            continue
        if getattr(qty, "scope", None) != "Controller":
            continue
        comp = getattr(n, "comparator", None)
        rhs = getattr(n, "rhs", None)
        rv = getattr(rhs, "value", None) if rhs is not None else None
        if (comp == "GE" and rv == 2) or (comp == "GT" and rv == 1):
            return True
    return False


# ── Batch-11 typed accessors (replacement / damage-trigger / tap / library) ──


def replacement_event_tag(node: TypedMirrorNode) -> str:
    """The ``event`` of a replacement node (``"CreateToken"`` / ``"AddCounter"``
    / ``"DamageDone"`` / ``"Moved"`` …), ``""`` when absent. CR 614.1a — the
    event discriminator splits the token / counter / damage doubler lanes.
    """
    ev = getattr(node, "event", MISSING)
    return ev if isinstance(ev, str) else ""


def replacement_qty_mod(node: TypedMirrorNode) -> tuple[str, int] | None:
    """``(kind, n)`` of a replacement's ``quantity_modification``, or ``None``.

    phase types the CR 614 quantity rewrites as a tagged node — ``Times``
    (factor: Doubling Season x2), ``Plus`` (value: Hardened Scales +1),
    ``Minus`` (Vizier of Remedies), ``Prevent``, ``Half``. The doubler lanes
    gate on the INCREASE kinds; a reducer/denial never fires.
    """
    qm = getattr(node, "quantity_modification", MISSING)
    if not _present(qm):
        return None
    t = tag_of(qm)
    if t is None:
        return None
    f = getattr(qm, "factor", None)
    v = getattr(qm, "value", None)
    n = f if isinstance(f, int) else (v if isinstance(v, int) else 0)
    return (t, n)


def replacement_damage_mod(node: TypedMirrorNode) -> str | None:
    """The tag of a replacement's ``damage_modification`` (``Double`` /
    ``Triple`` / ``Plus`` / ``Minus`` / ``LifeFloor`` …), or ``None`` when the
    node carries none (a pure prevention/redirect shield — Palisade Giant).
    CR 614.1a + 120.3.
    """
    return tag_of(getattr(node, "damage_modification", None))


def replacement_counter_match(node: TypedMirrorNode) -> str:
    """The counter KIND a replacement's ``counter_match`` names (``"P1P1"`` /
    ``"M1M1"``), ``""`` when kindless/absent. CR 122.1.
    """
    cm = getattr(node, "counter_match", MISSING)
    if _present(cm) and tag_of(cm) == "OfType":
        d = getattr(cm, "data", None)
        return d if isinstance(d, str) else ""
    return ""


def replacement_shield_kind(node: TypedMirrorNode) -> str | None:
    """The tag of a replacement's ``shield_kind`` (``Prevention`` — the CR 615
    prevention-shield membership on a DamageDone replacement, Palisade Giant
    family), or ``None``. Deliberately does NOT read ``redirect_target`` —
    the redirect lane is a settled KEPT (phase drops the redirect side on all
    but 8 corpus replacements).
    """
    sk = getattr(node, "shield_kind", MISSING)
    if isinstance(sk, MirrorVariant):
        return sk.key
    if isinstance(sk, TypedMirrorNode):
        return tag_of(sk)
    return None


def replacement_token_owner_scope(node: TypedMirrorNode) -> str:
    """The ``token_owner_scope`` of a ``CreateToken`` replacement (``"You"``
    — Doubling Season / Parallel Lives; ``""`` for the symmetric Primal
    Vigor form). The give-away gate (checklist #2) reads it.
    """
    s = getattr(node, "token_owner_scope", MISSING)
    return s if isinstance(s, str) else ""


#: The ``quantity_modification`` kinds that raise a replacement's count (CR
#: 614.1a): Doubling Season's ``Times 2``, Hardened Scales' ``Plus 1``. A
#: ``Minus`` reducer (Vizier of Remedies, Halving Season) is none.
INCREASE_QTY_MODS: frozenset[str] = frozenset({"Times", "Plus"})


def token_doubler_kinds(
    tree: ConceptTree,
) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """The token kinds each of a card's token-count increases is restricted to
    (:func:`replacement_token_types`): one entry per ``CreateToken`` replacement
    with an increase (:data:`INCREASE_QTY_MODS`) that no opponent alone gets
    (CR 111.2: the creator owns the token). ``((), ())`` doubles every token
    (Doubling Season, Primal Vigor), ``((), ("Creature",))`` creature tokens only
    (Ojer Taq), ``(("Treasure",), ())`` one subtype. Empty for a card with none:
    a doubler an effect sets up for a turn (Kaya, Geist Hunter's -2) is an
    effect, not a static replacement, and names no kind; Xorn's extra Treasure
    carries no count change."""
    out: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for unit in tree.units:
        if unit.origin != "replacement":
            continue
        node = unit.node
        if (
            replacement_event_tag(node) != "CreateToken"
            or replacement_token_owner_scope(node) == "Opponent"
        ):
            continue
        qm = replacement_qty_mod(node)
        if qm is not None and qm[0] in INCREASE_QTY_MODS:
            out.append(replacement_token_types(node))
    return tuple(out)


def replacement_token_types(
    node: TypedMirrorNode,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(subtypes, core_types)`` a ``CreateToken`` replacement is restricted to,
    read off its ``condition``: the ``TokenSubtypeMatches`` subtypes ("If you would
    create a Treasure token" — Xorn; Academy Manufactor's Clue / Food / Treasure)
    and the ``TokenCoreTypeMatches`` core types ("one or more artifact tokens" —
    Stridehangar Automaton), through ``And`` / ``Or`` (Fisher's Talent's
    ``And[ClassLevelGE, TokenSubtypeMatches]``). A ``Not`` is not entered: a negated
    kind is not the kind the card watches. Both empty for an unrestricted
    replacement (Doubling Season), which watches every token. (Not
    ``lanes._shared._condition_leaves``: the lanes import this module, and that
    walk keeps ``Not``-wrapped leaves.)
    """
    subtypes: list[str] = []
    cores: list[str] = []

    def walk(cond: object) -> None:
        t = tag_of(cond)
        if t in ("And", "Or"):
            for c in getattr(cond, "conditions", ()) or ():
                walk(c)
            return
        if t == "TokenSubtypeMatches":
            acc, vals = subtypes, getattr(cond, "subtypes", ())
        elif t == "TokenCoreTypeMatches":
            acc, vals = cores, getattr(cond, "core_types", ())
        else:
            return
        for v in vals or ():
            if isinstance(v, str) and v not in acc:
                acc.append(v)

    walk(getattr(node, "condition", None))
    return tuple(subtypes), tuple(cores)


def damage_filter_scope(node: TypedMirrorNode, field: str) -> str | None:
    """The player scope of a DamageDone replacement's ``damage_target_filter``
    / ``damage_source_filter``, or ``None`` when absent.

    Three phase shapes: a bare string (``"CreatureOnly"`` — Blind Fury) →
    ``"objects"`` (no player reach); a variant ``{Player: {player}}`` /
    ``{PlayerOrPermanentsControlledBy: {player}}`` → the named player's scope
    (Gisela: Opponent → ``"opponents"``; Ali from Cairo: Controller →
    ``"you"``); a ``Typed`` object filter (Gratuitous Violence's creature
    source) → ``"objects"``. Checklist #5: direction reads the filter's OWN
    player node, never a summary scope.
    """
    f = getattr(node, field, MISSING)
    if not _present(f):
        return None
    if isinstance(f, str):
        return "objects"
    if isinstance(f, MirrorVariant):
        if f.key in ("Player", "PlayerOrPermanentsControlledBy"):
            ply = _variant_field(f.inner, "player")
            return _scope_from_player_node(ply) or "any"
        return "objects"
    if isinstance(f, TypedMirrorNode):
        if tag_of(f) in ("Typed", "Or", "And"):
            return "objects"
        return _scope_from_player_node(f) or "objects"
    return None


def redirects_damage_from_you(node: TypedMirrorNode) -> bool:
    """Whether ``node`` is a redirection effect shielding you (CR 614.9: a
    redirection effect replaces damage dealt to one battle, creature,
    planeswalker or player with the same damage dealt to another). Two
    phase shapes:

    * a ``CreateDamageReplacement`` effect whose ``target_filter`` names you
      (alone, or you and permanents you control) and whose ``redirect_to``
      sends the damage elsewhere — Gideon's Sacrifice, Harm's Way, Saving
      Grace, Nova Pentacle;
    * the static form, a ``DamageDone`` replacement whose
      ``damage_target_filter`` names you and whose ``redirect_target`` is the
      new recipient — "All damage that would be dealt to you is dealt to
      enchanted creature instead" (Pariah, Pariah's Shield, With Great
      Power . . .), "… to you and other permanents you control is dealt to ~
      instead" (Palisade Giant, Ancient Adamantoise), the Bodyguard
      soldiers. phase also stamps a ``Prevention`` shield kind on it, which
      is why ``damage_prevention`` reads it too.

    A redirect watching an opponent (Soltari Guerrillas' "would deal combat
    damage to an opponent") or a creature (Treacherous Link's curse) is not
    one. A life floor (Worship: "damage that would reduce your life total to
    less than 1 reduces it to 1 instead") moves no damage anywhere — its
    rulings say the damage is still dealt — so it is ``board_protection``,
    never a redirect.
    """
    if tag_of(node) == "CreateDamageReplacement":
        return (
            _present(getattr(node, "redirect_to", MISSING))
            and damage_filter_scope(node, "target_filter") == "you"
        )
    return (
        replacement_event_tag(node) == "DamageDone"
        and _present(getattr(node, "redirect_target", MISSING))
        and damage_filter_scope(node, "damage_target_filter") == "you"
    )


def trigger_counter_filter(trig: TypedMirrorNode) -> tuple[str, int]:
    """``(counter_type, threshold)`` of a ``CounterAdded`` trigger's
    ``counter_filter`` (``("lore", 3)`` — a Saga chapter, CR 714.2b;
    ``("P1P1", 0)`` — Scurry Oak; ``("", 0)`` when kindless/absent).

    The typed Saga gate: 723 of the 798 CounterAdded triggers are Saga
    chapters, and the ``lore`` counter_type is a CLEANER discriminator than
    live's type_line sniff.

    ADR-0038 W4 giant batch: a THRESHOLD-less filter (no chapter number —
    a bare "whenever a +1/+1 counter is put on ~" trigger, Fathom Mage /
    Enduring Scalelord / Knighted Myr) loads the mirror runtime's untagged
    single-field collapse (:class:`MirrorVariant`, ``key="counter_type"``)
    instead of the full ``counter_filter`` struct — the struct shape only
    survives loading when a SECOND field (``threshold``) is also present.
    Both encodings are read here so the P1P1-specific placement-trigger arm
    (``_plus_one_matters``) and the Saga gate see the SAME kind regardless
    of which shape a given filter loaded as.
    """
    cf = getattr(trig, "counter_filter", MISSING)
    if not _present(cf):
        return ("", 0)
    if isinstance(cf, MirrorVariant):
        if cf.key == "counter_type" and isinstance(cf.inner, str):
            return (cf.inner, 0)
        return ("", 0)
    ct = getattr(cf, "counter_type", None)
    th = getattr(cf, "threshold", None)
    return (
        ct if isinstance(ct, str) else "",
        th if isinstance(th, int) else 0,
    )


def trigger_caster_scope(trig: TypedMirrorNode) -> str | None:
    """The cast-PLAYER scope of a ``SpellCast`` trigger's ``valid_target`` —
    ``"you"`` for the "whenever YOU cast" form (Lys Alana — ``Controller``),
    ``"opponents"`` for the opponent punisher, ``None`` for the symmetric
    "a player casts" hoser (Elvish Handservant — no valid_target). The typed
    you-cast discriminator that replaces live's ``_self_cast_oracle`` regex
    gate. CR 603.2 + 102.2.
    """
    vt = getattr(trig, "valid_target", MISSING)
    if not _present(vt):
        return None
    return _scope_from_player_node(vt)


def settap_state(node: TypedMirrorNode) -> str | None:
    """The ``state`` tag of a ``SetTapState`` effect (``Tap`` / ``Untap``),
    or ``None``. CR 701.26a.
    """
    return tag_of(getattr(node, "state", None))


def player_filter_tag(node: TypedMirrorNode) -> str | None:
    """The ``player_filter`` tag of a ``DamageAll`` / ``DamageEachPlayer``
    effect (``All`` — the symmetric Pestilence form; ``Opponent`` — the
    one-sided Witty Roastmaster form), or ``None`` when the sweep never
    reaches players (Pyroclasm). CR 102.2/102.3 — the each-PLAYER vs
    each-OPPONENT split is the whole gate.
    """
    return tag_of(getattr(node, "player_filter", None))


def double_target_kind(node: TypedMirrorNode) -> str | None:
    """The ``target_kind`` tag of a one-shot ``Double`` effect (``Counters``
    — Vorel; ``LifeTotal``; ``ManaPool``; ``None`` for the power doublers).
    The counter_doubling arm gates on ``Counters`` exactly. CR 122.1.
    """
    return tag_of(getattr(node, "target_kind", None))


def node_duration(node: object) -> str | None:
    """The ``duration`` of an ability/effect wrapper, normalized to its tag
    string (``"UntilHostLeavesPlay"`` — the O-Ring exile duration, CR 611.2b;
    ``"UntilEndOfTurn"``; the parameterized ``{UntilNextStepOf: …}`` → its
    KEY). ``None`` when absent.
    """
    d = getattr(node, "duration", MISSING)
    if isinstance(d, str):
        return d
    if isinstance(d, MirrorVariant):
        return d.key
    if isinstance(d, TypedMirrorNode):
        return tag_of(d)
    return None


def _player_scope_tag(ps: object) -> str | None:
    """The actor tag of a ``player_scope`` value (tagged node / variant / string)."""
    if isinstance(ps, TypedMirrorNode):
        return tag_of(ps)
    if isinstance(ps, MirrorVariant):
        return ps.key
    return ps if isinstance(ps, str) else None


#: ``AllExcept.exclude`` tags naming the ability's own controller.
_SELF_EXCLUDE_TAGS: frozenset[str] = frozenset({"Controller", "You"})


#: "each other player": an ``AllExcept`` ``player_scope`` that excludes the
#: ability's controller. CR 102.3 makes a teammate one of the other players, so
#: each read decides what it means (reach: ``"each"``).
OTHERS_SCOPE = "Others"

#: "You and that player each …": a ``player_scope`` naming you and one other
#: player (``AnyOf[Controller, X]``; the other is an opponent on every card that
#: prints it — "you and target opponent", "you and that player" off combat
#: damage to a player, "an opponent" — Farsight Adept, Black Widow, Intel
#: Expert, Infernal Offering). Two players act, never every player: its reach
#: (:func:`effect_player_reach`) is an opponent's, and you act too
#: (:data:`YOUR_ACTORS`).
YOU_AND_OPPONENT_SCOPE = "YouAndOpponent"

#: every player's option ("any player may …"): reach reads it as ``"each"``; no
#: one is forced, so it is no edict actor.
ANY_PLAYER_SCOPE = "AnyPlayer"

#: a player the card picks out — the players who chose a vote's outcome (Master of
#: Ceremonies' "for each player who chose money"), a villainous choice's "that
#: player" (Damocles Base). Nobody is targeted; reach reads it as ``"target"`` (a
#: player the card chooses) and an edict as opponents.
CHOSEN_PLAYER_SCOPE = "ChosenPlayer"


def _any_of_members(ps: object) -> tuple[str, ...]:
    """The players an ``AnyOf`` ``player_scope`` names, each as its tag ("you and
    target opponent each draw a card" — Farsight Adept: one effect on
    ``ScopedPlayer`` under ``AnyOf[Controller, TargetPlayer]``), else ``()``."""
    if tag_of(ps) != "AnyOf":
        return ()
    return tuple(
        t for f in getattr(ps, "filters", None) or () if (t := _player_scope_tag(f))
    )


def _owner_scope_tag(ps: object, root: object) -> str | None:
    """A wrapper's ``player_scope`` tag, with "each other player" — an
    ``AllExcept`` that excludes the ability's controller — resolved to
    ``"Others"``. Phase v0.104.0 writes Oft-Nabbed Goat's "its owner draws … and
    each other player loses that much life" as ``AllExcept{exclude:
    ParentObjectTargetOwner}`` on the card's own dies trigger, whose parent
    object is the card itself; on any other trigger that object is a target
    (Fractured Identity), so it stays ``AllExcept``."""
    if isinstance(ps, str):  # an actor the owner walk resolved (a choice, a label)
        return None if ps == "You" else ps
    members = _any_of_members(ps)
    if len(members) == 2 and any(m in _SELF_EXCLUDE_TAGS for m in members):
        return YOU_AND_OPPONENT_SCOPE  # "you and that player each draw two cards"
    tag = _player_scope_tag(ps)
    if tag == "VotedFor":
        # the players who chose a vote's outcome, outside friend-or-foe (whose
        # side the owner walk reads off its label).
        return CHOSEN_PLAYER_SCOPE
    if tag != "AllExcept":
        return tag
    excluded = tag_of(getattr(ps, "exclude", None))
    if excluded in _SELF_EXCLUDE_TAGS or (
        excluded == "ParentObjectTargetOwner"
        and tag_of(getattr(root, "valid_card", None)) == "SelfRef"
    ):
        return OTHERS_SCOPE
    return tag


# Effect nodes that pick one of several alternatives (``_EFFECT_LIST_FIELDS``
# minus the modes): the alternatives are still the clause that holds the node,
# so a branch wrapper with no ``player_scope`` of its own is done by whoever
# does that clause.
_BRANCHING_EFFECT_TAGS = frozenset(BRANCH_LISTS)
_BRANCH_LIST_FIELDS = tuple(f for f in _EFFECT_LIST_FIELDS if f != "mode_abilities")

_OWNER_INDEX_CACHE_ATTR = "_xw_owner_index"


class _OwnerIndex(NamedTuple):
    """id(effect node) → (owner wrapper, its actor: a ``player_scope`` node or an
    actor tag string); id(any node) → the alternatives it sits in ({id of the
    choosing node: which alternative})."""

    owners: dict[int, tuple[TypedMirrorNode, object]]
    paths: dict[int, dict[int, object]]
    #: ids of the nodes inside a branch the controller doesn't decide, or only a
    #: natural top die face reaches (``branches.uncertain_list`` /
    #: ``branches.natural_top_only`` — the branches the certain records prune).
    uncertain: set[int]
    #: id(node) → the actor facing the choice it sits in, when another player
    #: makes that choice (:data:`_CHOOSER_ACTORS`).
    facing: dict[int, str]
    #: id(a ``sub_ability`` wrapper) → the clause it continues.
    sub_parents: dict[int, TypedMirrorNode]


# The player facing a choice another player makes — a ``ChooseOneOf``'s
# non-controller ``chooser`` (a villainous choice, CR 701.55a). Its branches name
# that player as ``ScopedPlayer`` ("They sacrifice a nontoken creature of their
# choice" — Damocles Base); :func:`effect_facing_player` hands the reads that
# resolve ``ScopedPlayer`` this side. Damocles Base's "that player" and a target's
# controller or owner are a player the card picks out (:data:`CHOSEN_PLAYER_SCOPE`);
# a defending player (CR 506.2) and "each opponent who lost 3 or more life"
# (Davros's ``PlayerAttribute``) are opponents.
_CHOOSER_ACTORS: dict[str, str] = {
    "Opponent": "Opponent",
    "DefendingPlayer": "Opponent",
    "PlayerAttribute": "Opponent",
    "ChosenPlayer": CHOSEN_PLAYER_SCOPE,
    "ParentObjectTargetController": CHOSEN_PLAYER_SCOPE,
    "ParentObjectTargetOwner": CHOSEN_PLAYER_SCOPE,
}
# The actor of a choice its holding wrapper offers to more players than the
# controller (``optional_for``): "any player may sacrifice two lands … or have this
# deal 5 damage to that player" (Worms of the Earth) — every player's option, not an
# each-player instruction (:data:`ANY_PLAYER_SCOPE`).
_OPTION_ACTORS: dict[str, str] = {
    "AnyPlayer": ANY_PLAYER_SCOPE,
    "AnyOpponent": "Opponent",
    "AnyOtherPlayer": OTHERS_SCOPE,
}


def _option_actor(holder: object, scope: object) -> object:
    """The actor a ``ChooseOneOf``'s branches inherit: the "any player" option of
    the wrapper holding it (:data:`_OPTION_ACTORS`), else the holding clause's."""
    option = getattr(holder, "optional_for", None)
    if isinstance(option, str) and option in _OPTION_ACTORS:
        return _OPTION_ACTORS[option]
    return scope


def _owner_index(root: object) -> _OwnerIndex:
    """One walk over ``root``'s effects (:func:`effect_child_items` — the same
    branches and champion skip as every other effect walk), noting for each
    effect node the wrapper that owns it (the one whose ``.effect`` IS it) with
    that wrapper's actor, and for every node the alternatives it sits in.
    Memoized on ``root``.

    The actor is the wrapper's own ``player_scope`` or — for a branch wrapper that
    carries none — the one of the clause whose ``effect`` holds the branching
    node: Osseous Sticktwister's "each opponent may sacrifice a nonland permanent
    or discard a card" hangs ``player_scope: Opponent`` on the trigger's
    ``execute``, and its two branches carry none. A choice offered to "any player"
    hands its branches that option (:func:`_option_actor`); a choice another player
    makes notes the facing player (:func:`effect_facing_player`); a friend-or-foe
    outcome its label's side (:func:`_friend_or_foe_actor`). A sequential
    ``sub_ability`` or an ``else_ability`` is its own clause and inherits nothing.
    An alternative is a conditional wrapper's ``"then"`` (its ``effect``) or
    ``"else"`` (its ``else_ability``), or a branching node's list index."""
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_OWNER_INDEX_CACHE_ATTR)
        if cached is not None:
            return cached
    owners: dict[int, tuple[TypedMirrorNode, object]] = {}
    paths: dict[int, dict[int, object]] = {}
    uncertain: set[int] = set()
    facing: dict[int, str] = {}
    sub_parents: dict[int, TypedMirrorNode] = {}
    seen: set[int] = set()

    def walk(
        node: object,
        inherited: object,
        path: dict,
        depth: int,
        *,
        row: bool,
        vote: object = None,
        holder: object = None,
        in_uncertain: bool = False,
        facing_actor: str | None = None,
    ) -> None:
        if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
            return
        seen.add(id(node))
        paths.setdefault(id(node), path)
        if in_uncertain:
            uncertain.add(id(node))
        if facing_actor is not None:
            facing.setdefault(id(node), facing_actor)
        own = getattr(node, "player_scope", MISSING)
        scope = own if _present(own) else inherited
        if vote is not None:
            scope = _friend_or_foe_actor(vote, scope)
        eff = getattr(node, "effect", MISSING)
        if not row and isinstance(eff, TypedMirrorNode):
            owners.setdefault(id(eff), (node, scope))
        tag = tag_of(node)
        branching = tag in _BRANCHING_EFFECT_TAGS
        branch_scope = _option_actor(holder, scope) if tag == "ChooseOneOf" else scope
        chooser = (
            tag_of(getattr(node, "chooser", None)) if tag == "ChooseOneOf" else None
        )
        branch_facing = (
            _CHOOSER_ACTORS.get(chooser, CHOSEN_PLAYER_SCOPE)
            if tag == "ChooseOneOf" and chooser not in (None, "Controller")
            else facing_actor
        )
        others_pick = branching and uncertain_list(node, holder)
        has_else = isinstance(getattr(node, "else_ability", MISSING), TypedMirrorNode)
        for fname, i, child in effect_child_items(node):
            if fname == "sub_ability" and isinstance(child, TypedMirrorNode):
                sub_parents.setdefault(id(child), node)
            if fname == "effect":
                # a d20 row's ``effect`` is the row's ability wrapper
                keep = row or tag_of(child) in _BRANCHING_EFFECT_TAGS
                passed = scope if keep else None
            else:
                in_branch = branching and fname in _BRANCH_LIST_FIELDS
                passed = branch_scope if in_branch else None
            step = path
            if has_else and fname in ("effect", "else_ability"):
                step = {**path, id(node): "else" if fname == "else_ability" else "then"}
            elif branching and i is not None and fname in _BRANCH_LIST_FIELDS:
                step = {**path, id(node): i}
            walk(
                child,
                passed,
                step,
                depth + 1,
                row=branching and fname == BRANCH_LISTS["RollDie"],
                vote=node if fname == BRANCH_LISTS["Vote"] else None,
                holder=node if fname == "effect" else None,
                facing_actor=branch_facing
                if branching and fname in _BRANCH_LIST_FIELDS
                else facing_actor,
                in_uncertain=in_uncertain
                or (
                    branching
                    and fname in _BRANCH_LIST_FIELDS
                    and (
                        others_pick
                        or (
                            fname == BRANCH_LISTS["RollDie"]
                            and natural_top_only(node, child)
                        )
                    )
                ),
            )

    walk(root, None, {}, 0, row=False)
    out = _OwnerIndex(owners, paths, uncertain, facing, sub_parents)
    if isinstance(root, TypedMirrorNode):
        object.__setattr__(root, _OWNER_INDEX_CACHE_ATTR, out)
    return out


# Friend-or-foe's two labels (``Vote.choices`` under ``voter_scope:
# ControllerLabels``) and the side each lands on. The controller labels every
# player, themselves included — "You make this choice for yourself as well as each
# other player" (Pir's Whim's ruling) — so a friend reads as the controller and a
# foe as an opponent: the lane's own decision (a friend "doesn't become your
# teammate", the same ruling set says).
_FRIEND_OR_FOE_ACTORS = {"friend": "You", "foe": "Opponent"}


def _friend_or_foe_actor(vote: object, scope: object) -> object:
    """A friend-or-foe outcome's actor: the branch's ``player_scope: VotedFor``
    names its label by ``choice_index`` into the vote's ``choices`` (Pir's
    Whim: ``["friend", "foe"]`` — the friends search for a land, the foes
    sacrifice). Any other scope or vote is returned unchanged."""
    if tag_of(getattr(vote, "voter_scope", None)) != "ControllerLabels":
        return scope
    if tag_of(scope) != "VotedFor":
        return scope
    index = getattr(scope, "choice_index", None)
    choices = getattr(vote, "choices", None)
    if not isinstance(choices, list):
        return scope
    i = index if isinstance(index, int) else 0
    label = choices[i] if 0 <= i < len(choices) else None
    return _FRIEND_OR_FOE_ACTORS.get(label, scope) if isinstance(label, str) else scope


def _find_owner_wrapper(root: object, target: object) -> TypedMirrorNode | None:
    """The ability wrapper whose ``.effect`` IS ``target``, or ``None``."""
    found = _owner_index(root).owners.get(id(target))
    return found[0] if found is not None else None


def effect_owner_player_scope(root: object, effect_node: object) -> str | None:
    """The actor tag on the ability wrapper that DIRECTLY owns ``effect_node``
    (the wrapper whose ``.effect`` IS it — :func:`_owner_index`), or ``None``
    when that wrapper names none (the controller).

    phase hangs ``player_scope`` ("each player / an opponent <does X>") on the
    wrapper whose ``effect`` is the resolving action — a trigger ``execute``, a
    sequential ``sub_ability``, a modal ``mode_abilities`` arm, a vote's or a
    ``ChooseOneOf``'s branch (which takes the actor of the choice when it carries
    none: "each opponent may sacrifice … or discard …"), an "otherwise"
    ``else_ability`` — NOT on the inner effect node the overlay decorates.
    Reading the scope of the wrapper that owns THIS effect (not a sibling's)
    tells a give-away / edict ("each player gains control", "each opponent
    sacrifices an enchantment") from a you-effect that merely shares a unit with
    an unrelated each-player action — Nihiloor's per-opponent tap loop (a
    ``repeat_for`` on the OUTER trigger, not the gain-control's wrapper),
    Garland's monarch vote. ``OTHERS_SCOPE`` == "each other player" and
    ``CHOSEN_PLAYER_SCOPE`` == a player the card picks out
    (:func:`_owner_scope_tag`): each lane decides what they mean."""
    found = _owner_index(root).owners.get(id(effect_node))
    return _owner_scope_tag(found[1], root) if found is not None else None


#: Wrapper actors (:func:`effect_owner_player_scope`) naming the opponents: the
#: opponent ``player_scope`` tags plus "each other player".
OPPONENT_WRAPPER_ACTORS: frozenset[str] = frozenset(
    {*OPPONENT_ACTOR_TAGS, OTHERS_SCOPE}
)
#: Wrapper actors (:func:`effect_owner_player_scope`) under which you act: none
#: named (the controller), or you beside an opponent.
YOUR_ACTORS: frozenset[str | None] = frozenset({None, YOU_AND_OPPONENT_SCOPE})

#: An Aura's enchanted player. CR 303.4: an Aura enters the battlefield attached
#: to an object or player, so it names no side; each read decides what it means.
ENCHANTED_PLAYER_SCOPE = "EnchantedPlayer"


def effect_actor_scope(unit: AbilityUnit, node: object) -> str | None:
    """The player a player-recipient effect ``node`` of ``unit`` (a mill, a
    discard, a draw) really acts on, when phase names it outside the effect's
    own recipient — else ``None``, and the caller keeps its own scope (the
    concept's, or :func:`explicit_recipient_scope`). phase writes these effects
    Controller-relative, so the recipient alone reads "you":

    * the owning wrapper's ``player_scope``: "Each opponent mills eight cards"
      (Maddening Cacophony) hangs ``Opponent`` on the wrapper and targets the
      mill at ``Controller`` → ``"opponents"`` (a granted trigger's wrapper
      too — Imperious Mindbreaker);
    * a replacement's ``valid_player``: "If an opponent would mill one or more
      cards, they mill twice that many cards instead" (Bruvac the
      Grandiloquent) → ``"opponents"``;
    * an Aura's enchanted player: an ``AttachedTo`` recipient ("enchanted
      player mills X cards" — Fraying Sanity), or the ``TriggeringPlayer`` of
      a trigger watching ``AttachedTo`` ("At the beginning of enchanted
      player's upkeep, that player mills two cards" — Curse of the Bloody
      Tome) → :data:`ENCHANTED_PLAYER_SCOPE`;
    * the ``TriggeringPlayer`` of a trigger watching opponents ("Whenever an
      opponent loses life, that player mills that many cards" — Mindcrank)
      → ``"opponents"`` (:func:`triggering_player_side`).
    """
    owner = effect_owner_player_scope(unit.node, node)
    if owner is None and id(node) not in _owner_index(unit.node).owners:
        # A granted trigger's body (Imperious Mindbreaker's "each opponent mills
        # cards equal to its toughness") sits in a static's ``modifications``,
        # past the owner index's walk: find the wrapper whose ``.effect`` IS it.
        wrapper = next(
            (
                w
                for w in iter_typed_nodes(unit.node)
                if getattr(w, "effect", None) is node
            ),
            None,
        )
        if wrapper is not None:
            owner = _owner_scope_tag(getattr(wrapper, "player_scope", None), unit.node)
    if owner in OPPONENT_WRAPPER_ACTORS:
        return "opponents"
    if unit.origin == "replacement" and (
        _player_scope_tag(getattr(unit.node, "valid_player", None))
        in OPPONENT_ACTOR_TAGS
    ):
        return "opponents"
    recipient = tag_of(getattr(node, "target", None))
    if recipient == "AttachedTo" or (
        recipient == "TriggeringPlayer"
        and tag_of(getattr(unit.node, "valid_target", None)) == "AttachedTo"
    ):
        return ENCHANTED_PLAYER_SCOPE
    if recipient == "TriggeringPlayer" and triggering_player_side(unit) == "opponents":
        return "opponents"
    return None


def optional_clause_actor(root: object, effect_node: object) -> str | None:
    """The actor of an optional "each player may <X> and <Y>" clause, read for
    its second action ``effect_node`` — the wrapper actor tag
    (:func:`effect_owner_player_scope`'s vocabulary) — or ``None`` when
    ``effect_node`` is not that shape.

    phase v0.104.0 writes "Each player may discard their hand and draw seven
    cards" (Ruin Grinder, Snort, Will of the Jeskai) as an ``optional`` wrapper
    carrying ``player_scope: All`` over the ``Discard``, whose ``sub_ability``
    holds the ``Draw`` with no ``player_scope`` and no ``sub_link`` of its own,
    so :func:`effect_owner_player_scope` reads the draw as the controller's.
    The mandatory wheel (Wheel of Fortune) repeats ``player_scope: All`` on the
    sub-ability. The draw is the second half of the one choice each player
    makes, so it takes the optional wrapper's actor. A sub-ability that names
    its own actor or carries a ``sub_link`` (a separate sentence — Snort's
    "Then ~ deals 5 damage") is not this shape. Guarded by a
    ``retirement_canary`` test: once phase writes the actor on the
    sub-ability, the owner read answers directly. Read off the owner index
    (:func:`_owner_index`): the wrapper owning ``effect_node`` and the clause
    that wrapper continues."""
    index = _owner_index(root)
    found = index.owners.get(id(effect_node))
    if found is None:
        return None
    sub = found[0]
    n = index.sub_parents.get(id(sub))
    if (
        n is None
        or _present(getattr(sub, "player_scope", MISSING))
        or _present(getattr(sub, "sub_link", MISSING))
        or getattr(n, "optional", None) is not True
    ):
        return None
    return _owner_scope_tag(getattr(n, "player_scope", None), root)


def effect_owner_is_friend(root: object, effect_node: object) -> bool:
    """Whether ``effect_node`` is a friend-or-foe outcome labelled friend — the
    controller's side (:func:`_friend_or_foe_actor`): Pir's Whim's "each friend
    searches their library for a land card"."""
    found = _owner_index(root).owners.get(id(effect_node))
    if found is None:
        return False
    owner, actor = found
    return actor == "You" and tag_of(getattr(owner, "player_scope", None)) == "VotedFor"


def effect_facing_player(root: object, node: object) -> str | None:
    """The actor tag of the player facing the choice ``node`` sits in, when
    another player makes it — the player a branch's ``ScopedPlayer`` names
    ("That player sacrifices a creature of their choice" — Midnight Crusader
    Shuttle's defending player, an opponent) — else ``None``."""
    return _owner_index(root).facing.get(id(node))


def in_uncertain_branch(root: object, node: object) -> bool:
    """Whether ``node`` sits in a branch under ``root`` the controller doesn't
    decide, or only a natural top die face reaches — what the certain records
    prune (``_card_ir.branches``), read on a full tree."""
    return id(node) in _owner_index(root).uncertain


def effects_exclusive(root: object, a: object, b: object) -> bool:
    """Whether two effects under ``root`` are alternatives that can't both
    happen: one in a conditional's main branch and one in its "otherwise"
    branch (Search for Survivors' "If it's a creature card, put it onto the
    battlefield. Otherwise, exile it."), or in different branches of one
    ``ChooseOneOf`` / vote / die-roll row. A lane pairing two effects of one
    unit (an exile with its return) checks this now that the effect walk reads
    every branch. ``False`` when either isn't under ``root``."""
    paths = _owner_index(root).paths
    pa, pb = paths.get(id(a)), paths.get(id(b))
    if pa is None or pb is None:
        return False
    return any(k in pb and pb[k] != v for k, v in pa.items())


def effect_owner_rebinds_kind(root: object, effect_node: object) -> bool:
    """Whether the wrapper that owns ``effect_node`` carries phase's
    ``iteration_kind_binding`` marker: a "for each kind of counter on target
    permanent, put another counter of that kind on it or remove one from it"
    branch (Quarry Hauler, Dramatist's Puppet), whose typed counter kind is a
    loop placeholder, not the kind the card names."""
    owner = _find_owner_wrapper(root, effect_node)
    return _present(getattr(owner, "iteration_kind_binding", MISSING))


def effect_owner_optional(root: object, effect_node: object) -> bool:
    """Whether the wrapper that owns ``effect_node`` is optional — "that
    permanent's controller MAY sacrifice a land" (Chain of Vapor), a choice the
    actor can decline, not a forced action."""
    owner = _find_owner_wrapper(root, effect_node)
    return getattr(owner, "optional", None) is True


def sacrifice_names_no_player(root: object, node: TypedMirrorNode) -> bool:
    """Whether a ``Sacrifice`` effect of a typed permanent names no player at all:
    no controller on the sacrificed filter, no ``player_scope`` on the wrapper
    that owns it — the shape of a sacrifice you make yourself, and the shape phase
    leaves when it drops the forcing player ("each opponent … sacrifices",
    "…, then sacrifices")."""
    return (
        tag_of(getattr(node, "target", None)) == "Typed"
        and filter_controller(effect_filter(node)) is None
        and effect_owner_player_scope(root, node) is None
    )


def effect_owner_raw(root: object, effect_node: object) -> str:
    """The ``description`` grounding clause on the wrapper that DIRECTLY owns
    ``effect_node`` (mirrors :func:`effect_owner_duration`'s walk, but reads
    the CLAUSE text instead of the duration tag) — the isolated single-clause
    text a ``ParentTarget``/``TrackedSet`` backreference's real target
    filter is described by, one level closer than the unit's own top-level
    description (which spans every sibling clause and so cannot
    disambiguate WHICH one names an opponent — Mind Spiral / Snaremaster
    Sprite / Stunning Shot / Crashing Wave's stun-counter tail: "tap target
    creature an opponent controls and put a stun counter on it" lives on
    the wrapper owning the ``SetTapState``, not on a sibling "you control"
    clause elsewhere in the same ability). ``""`` when the owner is
    unresolvable or carries no description of its own.
    """
    owner = _find_owner_wrapper(root, effect_node)
    return _node_raw(owner) if owner is not None else ""


def effect_owner_targets_per_opponent(root: object, effect_node: object) -> bool:
    """Whether the wrapper that DIRECTLY owns ``effect_node`` carries a
    ``multi_target`` count that scales by opponent count — phase's
    structural form of "for each opponent, <single-target effect>" (Juvenile
    Mist Dragon: ``multi_target.max`` is a ``PlayerCount`` qty filtered to
    ``Opponent``). This is a DIFFERENT tell from the effect's own target
    filter's ``controller`` (which reads the loop's bound iteration
    variable, e.g. ``TargetPlayer`` — ambiguous on its own); the wrapper's
    per-opponent CARDINALITY is unambiguous: one target per opponent,
    the lane's own reading.
    """
    owner = _find_owner_wrapper(root, effect_node)
    if owner is None:
        return False
    mt = getattr(owner, "multi_target", MISSING)
    if not isinstance(mt, TypedMirrorNode):
        return False
    mx = getattr(mt, "max", None)
    if not isinstance(mx, TypedMirrorNode) or tag_of(mx) != "Ref":
        return False
    qty = getattr(mx, "qty", None)
    if not isinstance(qty, TypedMirrorNode) or tag_of(qty) != "PlayerCount":
        return False
    return tag_of(getattr(qty, "filter", None)) == "Opponent"


def effect_owner_reads_chosen_group(root: object, effect_node: object) -> bool:
    """Whether the wrapper that DIRECTLY owns ``effect_node`` acts on a group an
    earlier clause chose (phase's ``reads_chosen_group`` index — The Eagles Are
    Coming!'s "return each chosen creature")."""
    owner = _find_owner_wrapper(root, effect_node)
    return isinstance(getattr(owner, "reads_chosen_group", None), int)


def effect_owner_duration(root: object, effect_node: object) -> str | None:
    """The ``duration`` tag on the wrapper that DIRECTLY owns ``effect_node``
    (Banisher Priest's exile execute carries ``UntilHostLeavesPlay`` on the
    Spell wrapper, not on the ``ChangeZone`` node itself), or ``None``.
    CR 611.2b.
    """
    owner = _find_owner_wrapper(root, effect_node)
    return node_duration(owner) if owner is not None else None


# A chosen player the caster may aim anywhere — at an opponent, themself or
# (in Two-Headed Giant) their teammate. ``TargetOpponent`` is deliberately
# absent: "target opponent" can't be pointed at a teammate.
_TARGET_PLAYER_TAGS = frozenset({"Player", "TargetPlayer"})
# The mass/symmetric effect tags: "all"/"each" names no single chosen object
# (the lanes read these through ``_analysis/lanes/_shared.py``).
MASS_EFFECT_TAGS: frozenset[str] = frozenset(
    {"DestroyAll", "ChangeZoneAll", "PutCounterAll", "DamageAll", "DamageEachPlayer"}
)
# The mass-effect tags whose object filter's controller decides who is hit —
# :data:`MASS_EFFECT_TAGS` plus ``PumpAll`` ("creatures your opponents control
# get -2/-2"; "all creatures get -3/-3").
_MASS_REACH_TAGS = MASS_EFFECT_TAGS | {"PumpAll"}


def effect_player_reach(root: object, effect_node: TypedMirrorNode) -> str | None:
    """WHICH players an effect reaches, read from the structure around it:
    ``"per_opponent"`` (a "for each opponent, <targeted effect>" loop),
    ``"opponents"`` (each opponent / your opponents' permanents), ``"each"``
    (each player / every permanent), ``"target"`` (a player the caster chooses),
    ``"scoped"`` (a trigger's "that player" — resolve with
    :func:`scoped_player_scope`), or ``None`` (you, or no player reach).

    The concept node's own ``scope`` is unreliable for this question (Rank Rat's
    discard and Gray Merchant's drain read "you"; Murder reads "each"), so the
    read checks, in order: the owner wrapper's per-opponent ``multi_target``
    (:func:`effect_owner_targets_per_opponent` — first, because the loop's
    bound player reads ``TargetPlayer``); the owner wrapper's ``player_scope``
    (Rank Rat → Opponent, Garruk's -2 → All); a ``player_filter`` (Pestilence
    All, Witty Roastmaster Opponent); the recipient (target player / scoped
    player); an object filter controlled by a target or scoped player (Twisted
    Fates' "each creature target player controls", Face Yourself's
    ``source_filter``, Braids); and, for a mass effect only, its object
    filter's controller (Wrath of God → each; Massacre Wurm → opponents).
    phase can't yet tell "each other player" from "each opponent" — both are
    ``player_scope: Opponent`` (Grave Pact, Syphon Mind)."""
    if effect_owner_targets_per_opponent(root, effect_node):
        return "per_opponent"
    actor = effect_owner_player_scope(root, effect_node)
    if actor == CHOSEN_PLAYER_SCOPE:
        return "target"
    if actor == ANY_PLAYER_SCOPE:
        return "each"
    if actor in OPPONENT_ACTOR_TAGS or actor == YOU_AND_OPPONENT_SCOPE:
        return "opponents"  # (beside you, for the pair)
    # "each other player" (``Others``) reaches your teammate too (CR 102.3), the
    # same call as twohg_scan's veto on phase's ``Opponent`` reading of it.
    if actor in _EACH_ACTOR_TAGS or actor in ("All", OTHERS_SCOPE):
        return "each"
    pf = player_filter_tag(effect_node)
    if pf == "All":
        return "each"
    if pf == "Opponent":
        return "opponents"
    rt = recipient_tag(effect_node)
    if rt in _TARGET_PLAYER_TAGS:
        return "target"
    if rt == "ScopedPlayer":
        return "scoped"
    filt = effect_filter(effect_node)
    for f in (filt, getattr(effect_node, "source_filter", None)):
        ctrl = filter_controller(f)
        if ctrl == "ScopedPlayer":
            return "scoped"
        if ctrl in _TARGET_PLAYER_TAGS:
            return "target"
    # Phase-misparse workaround: phase drops the narrowing clause of some mass
    # effects and leaves a typeless filter, which would read as every
    # permanent — v0.94.0's Predictive Preparations ("each of one or two target
    # creatures"; a ``put_counter_tail`` residue since v0.104.0) and Saproling
    # Burst's "destroy all tokens created with this enchantment" (a bare
    # ``Token`` filter). Retire the ``filter_core_types`` condition when
    # test_typeless_mass_filter_canary fails RETIRE-READY.
    if tag_of(effect_node) in _MASS_REACH_TAGS and filter_core_types(filt):
        ctrl = filter_controller(filt)
        if ctrl is None:
            return "each"
        if ctrl in OPPONENT_ACTOR_TAGS:
            return "opponents"
    return None


def reveal_until_player(node: TypedMirrorNode) -> str | None:
    """The DIGGER of a ``RevealUntil`` effect from its ``player`` node —
    ``"you"`` for an own-library dig (Hermit Druid — ``Controller``); the
    opponent-library digs carry ``ParentTargetController`` /
    ``TriggeringPlayer`` / ``Typed`` → not-you ([P16]-adjacent direction
    gate). ``None`` when unresolvable. CR 701.20a.
    """
    return _scope_from_player_node(getattr(node, "player", None))


def filter_non_types(filt: object) -> tuple[str, ...]:
    """The words a typed filter NEGATES via ``{Non: X}`` entries ("noncreature
    spell" — Ruric Thar → ``("Creature",)``; "non-Zombie" → ``("Zombie",)``).

    The complement of :func:`_type_filter_words` (which DROPS the negation):
    the noncreature-cast punisher gates on the ``Non`` entry itself being
    present. Recurses ``Or`` / ``And``. CR 207.2c / 400.7.
    """
    out: list[str] = []
    t = tag_of(filt)
    if t == "Typed":
        for tf in getattr(filt, "type_filters", ()) or ():
            if isinstance(tf, MirrorVariant) and tf.key == "Non":
                inner = tf.inner
                if isinstance(inner, str):
                    out.append(inner)
                elif isinstance(inner, MirrorVariant):
                    out.append(
                        inner.inner if isinstance(inner.inner, str) else inner.key
                    )
    elif t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            out.extend(filter_non_types(sub))
    return tuple(out)


def has_filter_property(root: object, tag: str, value: str | None = None) -> bool:
    """Whether ANY typed node under ``root`` carries the property ``tag``
    (optionally with ``value``) — the whole-card predicate scan behind the
    legends_matter / historic_matters build-arounds (``HasSupertype:
    Legendary`` — Reki; ``Historic`` — Jhoira). The property tags are unique
    to filter ``properties`` entries, so the deep scan is precise. CR 205.4d
    / 700.6.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != tag:
            continue
        if value is None or getattr(n, "value", None) == value:
            return True
    return False


def zone_change_count_reads(
    root: object,
) -> Iterator[tuple[str | None, str | None, object]]:
    """``(from, to, filter)`` for every ``ZoneChangeCountThisTurn`` qty node
    under ``root`` — the "a permanent left the battlefield this turn"
    condition family (CR 603.10-adjacent state checks). Revolt carries
    ``from: Battlefield`` with NO ``to`` (Airdrop Aeronauts); Morbid carries
    ``to: Graveyard`` (Tragic Slip) — zone-precise, the two must not blur.
    """
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "ZoneChangeCountThisTurn":
            continue
        frm = getattr(n, "from_", MISSING)
        to = getattr(n, "to", MISSING)
        yield (
            frm if isinstance(frm, str) else None,
            to if isinstance(to, str) else None,
            getattr(n, "filter", None),
        )


def entered_this_turn_filters(root: object) -> Iterator[object]:
    """The ``filter`` of every entered-this-turn QTY node under ``root`` —
    the "if a creature entered the battlefield under your control this turn"
    condition family (Bellowing Elk; CR 603.6a-adjacent state check). A
    filterless node (Cactuar's self-check) yields nothing.

    Two shapes: the legacy ``EnteredThisTurn`` qty (controller rides the
    filter itself), and phase v0.32.0's entry-ledger ``BattlefieldEntries
    ThisTurn`` (BB-FU10 — the controller moved to the qty's own ``player``
    field, the filter's controller is null). The ledger shape yields only
    when ``player`` is the Controller, so consumers may accept a None
    filter-controller for it.
    """
    for n in _iter_typed_nodes(root):
        t = tag_of(n)
        if t == "EnteredThisTurn":
            f = getattr(n, "filter", MISSING)
            if _present(f):
                yield f
        elif t == "BattlefieldEntriesThisTurn":
            if tag_of(getattr(n, "player", None)) != "Controller":
                continue
            f = getattr(n, "filter", MISSING)
            if _present(f):
                yield f


# ── Batch-12 typed accessors (life / stax / protection / condition cluster) ──


def protection_cardtype(mod: TypedMirrorNode) -> str | None:
    """The CardType ARGUMENT of an ``AddKeyword {Protection: {CardType: X}}``
    modification (Gor Muldrak — ``"salamanders"``), or ``None`` for any other
    keyword / a protection-from-COLOR payload (White Knight). CR 702.16: the
    type_change lane vocab-validates the argument upstream.
    """
    kw = getattr(mod, "keyword", MISSING)
    if not (isinstance(kw, MirrorVariant) and kw.key == "Protection"):
        return None
    arg = _variant_field(kw.inner, "CardType")
    return arg if isinstance(arg, str) else None


def modify_cost_spell_filter(static_node: TypedMirrorNode) -> object | None:
    """The ``spell_filter`` of a ``{ModifyCost: …}`` static mode, or ``None``.

    The typed_spellcast static arm (b11 follow-up a) reads its subtypes: a
    "<Subtype> spells you cast cost {N} less" static (Goblin Warchief) carries
    the tribe on ``spell_filter`` — CR 601.2f couples the discount to the cast
    event, so the tribal reducer is a cast payoff, subject-bearing.
    """
    mode = getattr(static_node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "ModifyCost":
        return _variant_field(mode.inner, "spell_filter")
    return None


def cost_reduction_count_filters(node: object) -> Iterator[object]:
    """The filters of the objects a cost reduction counts (CR 601.2f, 602.2b):
    a ``ModifyCost`` static's ``dynamic_count`` ("costs {1} less to cast for
    each creature you control with a +1/+1 counter on it" — Hamza, Guardian of
    Arashin), and an activated ability's own ``cost_reduction`` — its scaling
    ``count`` or the ``condition`` that turns it on ("costs {2} less to activate
    if you control a creature with a +1/+1 counter on it" — Starport
    Security)."""
    mode = getattr(node, "mode", MISSING)
    if isinstance(mode, MirrorVariant) and mode.key == "ModifyCost":
        count = _variant_field(mode.inner, "dynamic_count")
        if tag_of(count) == "ObjectCount":
            filt = getattr(count, "filter", None)
            if filt is not None:
                yield filt
    reduction = getattr(node, "cost_reduction", MISSING)
    if not isinstance(reduction, TypedMirrorNode):
        return
    cond = getattr(reduction, "condition", None)
    for site, field in ((reduction, "count"), (cond, "lhs"), (cond, "rhs")):
        filt = ref_count_filter(site, field)
        if filt is not None:
            yield filt


def static_mode_field(node: object, field: str) -> object:
    """One named field of a parameterized static MODE's payload, or ``None``.

    The stax census reads discriminating sub-fields off the variant modes the
    b12 port added — ``who`` (``CantBeActivated`` / ``CantBeCast`` /
    ``PerTurnCastLimit`` …), ``source_filter`` (the Arrest pacify veto),
    ``defender`` (``MaxAttackersEachCombat``). ``None`` for a plain-string
    mode or an absent field.
    """
    mode = getattr(node, "mode", MISSING)
    if isinstance(mode, MirrorVariant):
        return _variant_field(mode.inner, field)
    return None


def distribute_counter_kind(node: TypedMirrorNode) -> str:
    """The counter kind of a ``PutCounter`` effect's ``distribute`` marker
    (Verdurous Gearhulk — ``{Counters: "P1P1"}`` → ``"P1P1"``), ``""`` when the
    placement is not a distribute-among (CR 601.2d). v0.9.0 DOES carry the
    marker — the earlier "[P-fold]" note was stale.
    """
    d = getattr(node, "distribute", MISSING)
    if _present(d) and tag_of(d) == "Counters":
        data = getattr(d, "data", None)
        return data if isinstance(data, str) else ""
    return ""


def iter_typed_nodes(root: object) -> Iterator[TypedMirrorNode]:
    """Public deep walk over every typed node reachable from ``root`` (the
    generic scan behind narrow unique-tag reads — the b12 saga CountersOn
    and big-hand HandSize operand arms). Cycle-safe, field-order agnostic.
    Iterates the memoized flat walk (see :func:`_typed_nodes`).
    """
    yield from _typed_nodes(root)


def iter_condition_sites(root: object) -> Iterator[TypedMirrorNode]:
    """Every CONDITION-site subtree root under one unit node: each ``condition``
    field plus each ``activation_restrictions`` entry (Companion of the Trials'
    ``RequiresCondition``). The superfriends lane scans ONLY these sites — an
    effect TARGET filter naming a Planeswalker is removal, not synergy
    (checklist gate; CR 306.5).
    """
    for n in _iter_typed_nodes(root):
        cond = getattr(n, "condition", MISSING)
        if isinstance(cond, TypedMirrorNode):
            yield cond
        ars = getattr(n, "activation_restrictions", MISSING)
        if _present(ars) and isinstance(ars, list):
            for ar in ars:
                if isinstance(ar, TypedMirrorNode):
                    yield ar


def requires_condition_inner(node: object) -> object | None:
    """The condition a ``RequiresCondition`` activation restriction carries ("Activate
    only if …", CR 602.5), unwrapped from its ``data`` variant; ``None`` for the
    empty marker phase leaves when it couldn't structure the condition."""
    data = getattr(node, "data", None)
    return data.inner if isinstance(data, MirrorVariant) else data


def activation_restriction_conditions(node: object) -> Iterator[object | None]:
    """The condition of each ``RequiresCondition`` activation restriction on one
    ability node (:func:`requires_condition_inner`; ``None`` for an empty marker).
    Timing and per-turn restrictions ("as a sorcery", "once each turn") aren't
    conditions and are skipped."""
    ars = getattr(node, "activation_restrictions", MISSING)
    if not (_present(ars) and isinstance(ars, list)):
        return
    for ar in ars:
        if tag_of(ar) == "RequiresCondition":
            yield requires_condition_inner(ar)


def hand_size_scopes(root: object) -> tuple[str, ...]:
    """The player scope of every ``HandSize`` / ``HandSizeExact`` /
    ``HandSizeOneOf`` QTY operand under one unit node (Maro's dynamic-P/T
    pair, Akki Underling's threshold condition). The big_hand_matters lane
    fires only on a ``"you"`` scope ([P5] — an opponent-hand count is not
    your grip payoff). A player-less operand reports ``"you"`` (phase's
    implicit controller). CR 402.2.
    """
    out: list[str] = []
    for n in _iter_typed_nodes(root):
        if tag_of(n) in ("HandSize", "HandSizeExact", "HandSizeOneOf"):
            player = getattr(n, "player", MISSING)
            if not _present(player):
                out.append("you")
                continue
            out.append(_scope_from_player_node(player) or "any")
    return tuple(out)


# ── self searches (CR 701.23a) ────────────────────────────────────────────────
# The shared search-your-library walks: the tutor / ramp lanes
# (``tree_synthesis.mana_ramp_lands``) and card_classify's land-search reads both
# go through them.

_TUTOR_DIRECTED_PLAYER_TAGS = TARGETED_PLAYER_TAGS | {
    "Opponent",
    "Opponents",
    "EachOpponent",
    "TriggeringPlayer",
    "ScopedPlayer",
    "ParentTargetController",
    "ParentObjectTargetController",
}
_TUTOR_NON_SELF_ABILITY_SCOPE = frozenset(
    {
        "All",
        "AllExcept",
        "EachPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
_TUTOR_SIBLING_RECIPIENT_CONCEPTS = frozenset(
    {"gain_life", "lose_life", "draw", "discard"}
)
# A bespoke non-SearchLibrary effect tag phase uses for a still-genuine own-
# library search (Teacher's Pet's Augment-combine); mapped to concept "tutor"
# in the crosswalk (crosswalk.EFFECT_CONCEPTS) alongside SearchLibrary.
TUTOR_EFFECT_TAGS = frozenset({"SearchLibrary", "ChooseAugmentAndCombineWithHost"})


def tutor_ability_body(unit: AbilityUnit) -> TypedMirrorNode | None:
    """The execute-shaped ability body carrying ``ability_tag`` /
    ``player_scope`` -- a trigger/replacement unit wraps its real ability body
    one level down in ``.execute`` (``AbilityUnit.node`` is the OUTER trigger/
    replacement wrapper for those origins); an ``ability``-origin unit's own
    node already IS that body."""
    if unit.origin in ("trigger", "replacement"):
        ex = getattr(unit.node, "execute", MISSING)
        return ex if isinstance(ex, TypedMirrorNode) else None
    return unit.node


def _searcher_is_self(tp: object) -> bool | None:
    """Whose library a ``SearchLibrary``'s own ``target_player`` names: ``True``
    for you (``Typed`` You/Controller), ``False`` for another player (Player/
    Target/Opponent(s)/TriggeringPlayer/ScopedPlayer/ParentTarget(Controller)),
    ``None`` when it names nobody (absent -- the default searcher is you) or an
    unknown shape."""
    if tp is MISSING or tp is None:
        return None
    t = tag_of(tp)
    if t in _TUTOR_DIRECTED_PLAYER_TAGS:
        return False
    if t == "Typed":
        return getattr(tp, "controller", None) in ("You", "Controller")
    return None


def _unit_search_vetoed(unit: AbilityUnit) -> bool:
    """The whole-unit vetoes on a self search: a symmetric/opponent-scoped
    ability (``player_scope`` on the execute body -- Old-Growth Dryads'
    ``Opponent``, Weird Harvest's ``All``), or a sibling gain_life/lose_life/
    draw/discard effect naming another player (Restorative Technique's "target
    player gains 2 life, then searches their library" -- the search itself
    carries no recipient, inheriting the preceding effect's)."""
    body = tutor_ability_body(unit)
    ps_tag = tag_of(getattr(body, "player_scope", None)) if body else None
    if ps_tag in _TUTOR_NON_SELF_ABILITY_SCOPE:
        return True
    return any(
        c.concept in _TUTOR_SIBLING_RECIPIENT_CONCEPTS
        and explicit_recipient_scope(c.node) in ("opponents", "each", "any")
        for c in unit.effects
    )


def _is_cycling_search(unit: AbilityUnit) -> bool:
    """A Cycling/Landcycling/Typecycling reminder-granted search (``ability_tag``
    Cycling -- CR 702.29e: "[Type]cycling" searches for a [type] card and puts it
    into your hand; CR 702.29a: it functions only from your hand)."""
    return tag_of(getattr(tutor_ability_body(unit), "ability_tag", None)) == "Cycling"


def unit_is_self_tutor(unit: AbilityUnit) -> bool | None:
    """Whether THIS unit's tutor concept(s) search YOUR OWN library (CR
    701.23a), or ``None`` if the unit carries no tutor concept at all.

    Four vetoes, all typed: (1) a Cycling/Landcycling/Typecycling reminder-
    granted search (:func:`_is_cycling_search` -- a keyword reminder is not a
    deliberate tutor); (2)/(3) :func:`_unit_search_vetoed`; (4) the search's
    own ``target_player`` (:func:`_searcher_is_self`). A unit MAY carry more
    than one SearchLibrary (Sadistic Sacrament's directed find-and-exile chains
    a second, recipient-less SearchLibrary for "the rest") -- if ANY search in
    the unit is directed, the WHOLE unit is (they share one targeted-player
    action chain). :func:`land_searches` judges each search on its own."""
    tutors = [
        c
        for c in unit.effects
        if c.concept == "tutor" and tag_of(c.node) in TUTOR_EFFECT_TAGS
    ]
    if not tutors:
        return None
    if _is_cycling_search(unit) or _unit_search_vetoed(unit):
        return False
    saw_self = False
    for c in tutors:
        tp = getattr(c.node, "target_player", MISSING)
        verdict = _searcher_is_self(tp)
        if verdict is False:
            return False
        if verdict is True or tp is MISSING or tp is None:
            saw_self = True
        # unknown target_player shape -- never guess either way for THIS node
    return saw_self or None


def self_tutor_found_types(tree: ConceptTree) -> tuple[str, ...]:
    """The card types the card's own-library searches find, sorted: in a self
    tutor's unit (:func:`unit_is_self_tutor`), each search of your library
    (:func:`_self_searches`) by its filter's card types (CR 205.2a; CR 701.23a:
    a search finds "a card that matches the given description") — Fabricate
    ``("Artifact",)``, Enlightened Tutor ``("Artifact", "Enchantment")``, Call
    the Gatewatch ``("Planeswalker",)``. A search for any card (Demonic Tutor)
    names none."""
    card_types = PERMANENT_CARD_TYPES | {"Instant", "Sorcery"}
    found: set[str] = set()
    for unit in tree.units:
        if unit_is_self_tutor(unit) is not True:
            continue
        for search in _self_searches(unit):
            found.update(
                t
                for t in filter_core_types(getattr(search, "filter", None))
                if t in card_types
            )
    return tuple(sorted(found))


#: CR 205.3i's full land-type list, lowercased. The one copy: the land-animate
#: lanes' narrower set (``lanes/_shared._LAND_SUBTYPE_WORDS``) is derived from it.
LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(
    {
        "cave",
        "desert",
        "forest",
        "gate",
        "island",
        "lair",
        "locus",
        "mine",
        "mountain",
        "plains",
        "planet",
        "power-plant",
        "sphere",
        "swamp",
        "tower",
        "town",
        "urza's",
    }
)


def _has_basic_supertype(filt: object) -> bool:
    return any(
        tag_of(p) == "HasSupertype" and getattr(p, "value", None) == "Basic"
        for p in (getattr(filt, "properties", None) or ())
    )


def search_filter_land_facts(f: object) -> tuple[bool, bool] | None:
    """``(can_fetch_land, fetches_only_lands)`` for a ``SearchLibrary``
    filter, or ``None`` when phase left the filter unresolved (a bare ``Any``
    -- Planar Engineering's "four basic land cards"; an empty ``Typed`` --
    Wild Endeavor's dice-scaled count). Landish = a ``Land`` core type, a CR
    205.3i land-subtype word, or a ``HasSupertype Basic`` property (CR
    305.6); land-ONLY additionally requires no nonland core type / nonland
    subtype disjunct (Archdruid's Charm's Or(Creature, Land) can fetch a
    creature, so it is landish but never land-only)."""
    t = tag_of(f)
    if t in ("Or", "And"):
        subs = [
            search_filter_land_facts(x) for x in (getattr(f, "filters", None) or ())
        ]
        subs = [s for s in subs if s is not None]
        if not subs:
            return None
        can = any(c for c, _ in subs)
        only = all(o for _, o in subs) if t == "Or" else any(o for _, o in subs)
        return can, only
    if t != "Typed":
        return None
    cores = set(filter_core_types(f))
    subtys = {s.lower() for s in filter_subtypes(f)}
    basic = _has_basic_supertype(f)
    if not cores and not subtys and not basic:
        return None
    landish = bool("Land" in cores or (subtys & LAND_SUBTYPE_WORDS) or basic)
    only = (
        landish and not (cores - {"Land", "Card"}) and not (subtys - LAND_SUBTYPE_WORDS)
    )
    return landish, only


def iter_search_landings(unit: AbilityUnit) -> Iterator[tuple[str, bool]]:
    """``(destination, enters_tapped)`` for every place the UNIT's searched
    card(s) can land: the search node's own ``split`` (Cultivate's
    one-to-battlefield-tapped / rest-to-hand) plus every ``ChangeZone`` in the
    unit whose origin is ``Library`` (the plain "put that card into X"
    continuation) or absent with an ``Any`` / ``ParentTarget`` target (the
    conditional-continuation shape phase emits for "put it onto the battlefield
    tapped if it's a land card" -- an origin-less ChangeZone chained onto the
    search's own result)."""
    for n in iter_typed_nodes(unit.node):
        t = tag_of(n)
        if t == "SearchLibrary":
            split = getattr(n, "split", MISSING)
            if split is not MISSING and split is not None:
                primary = getattr(split, "primary_destination", None)
                if isinstance(primary, str):
                    yield primary, getattr(split, "primary_enter_tapped", None) is True
                rest = getattr(split, "rest_destination", None)
                if isinstance(rest, str):
                    yield rest, False
        elif t == "ChangeZone":
            origin = getattr(n, "origin", MISSING)
            if origin is not MISSING and origin is not None:
                if origin != "Library":
                    continue
            elif tag_of(getattr(n, "target", None)) not in (
                "Any",
                "ParentTarget",
            ):
                continue
            d = getattr(n, "destination", None)
            if isinstance(d, str):
                yield d, getattr(n, "enter_tapped", None) is True


# ── land searches and mana colours (card_classify's IR reads) ─────────────────
# ``card_classify.color_sources`` / ``land_fetch_profile`` / ``is_fixing_land``
# and the tuner's fixing read go through these, never oracle text.

#: The basic land types and the mana each one's intrinsic ability adds (CR 305.6:
#: "An object with the land card type and a basic land type has the intrinsic
#: ability '{T}: Add [mana symbol]'" -- Plains {W}, Island {U}, Swamp {B},
#: Mountain {R}, Forest {G}).
BASIC_LAND_TYPE_COLORS: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}
_MANA_COLOR_LETTER: dict[str, str] = {
    "White": "W",
    "Blue": "U",
    "Black": "B",
    "Red": "R",
    "Green": "G",
    "Colorless": "C",
}
_FIVE_COLORS: frozenset[str] = frozenset("WUBRG")

#: What a land search can find, colour-wise: the colours its basic land types
#: name, ``"any_basic"`` for a basic land of any type (resolved against the
#: deck's own basics), or ``"any"`` for any land card.
type LandColors = frozenset[str] | Literal["any", "any_basic"]


def _merge_land_colors(
    parts: Iterable[LandColors],
) -> LandColors:
    """The union of several :data:`LandColors` (``"any"`` > ``"any_basic"`` > the
    named colours)."""
    named: set[str] = set()
    basic = False
    for p in parts:
        if p == "any":
            return "any"
        if p == "any_basic":
            basic = True
        elif isinstance(p, frozenset):
            named |= p
    return "any_basic" if basic else frozenset(named)


def land_search_colors(filt: object) -> LandColors | None:
    """The colours of mana a land found by a ``SearchLibrary`` filter can make,
    or ``None`` when the filter can't find a land (or phase left it unresolved
    -- see :func:`search_filter_land_facts`).

    A filter naming basic land types (Wood Elves' "Forest card", Farseek's
    "Plains, Island, Swamp, or Mountain card", Krosan Verge's "a Forest card and
    a Plains card") reads those types' colours (CR 305.6); a basic land with no
    type named (Evolving Wilds, Cultivate) is ``"any_basic"`` (CR 205.4c: a basic
    land is one with the basic supertype); any land card (Sylvan Scrying, Knight
    of the Reliquary) is ``"any"``. A filter naming only non-basic land types
    (a Gate, a Desert) names no colour: an empty set. ``Or`` / ``And`` widen to
    the broadest arm (Archdruid's Charm's creature-or-land reads its land arm)."""
    t = tag_of(filt)
    if t in ("Or", "And"):
        arms = [land_search_colors(x) for x in (getattr(filt, "filters", None) or ())]
        found = [a for a in arms if a is not None]
        return _merge_land_colors(found) if found else None
    facts = search_filter_land_facts(filt)
    if facts is None or not facts[0]:
        return None
    subtypes = filter_subtypes(filt)
    if subtypes:
        return frozenset(
            BASIC_LAND_TYPE_COLORS[s] for s in subtypes if s in BASIC_LAND_TYPE_COLORS
        )
    return "any_basic" if _has_basic_supertype(filt) else "any"


#: Phase's "any number" search count is i32::MAX (Nissa, Who Shakes the World's
#: -8: "any number of Forest cards"); a read caps it at a whole deck's worth.
SEARCH_COUNT_CAP = 99


def _count_value(node: object, field: str = "count") -> int | None:
    """``field``'s fixed magnitude (:func:`amount_factor`), unwrapping an ``UpTo``
    to its ``max``; None when dynamic or absent."""
    if not isinstance(node, TypedMirrorNode):
        return None
    if has_fixed_count(node, field):
        return amount_factor(node, field)
    q = getattr(node, field, MISSING)
    if _present(q) and tag_of(q) == "UpTo":
        return _count_value(q, "max")
    return None


def search_count(node: TypedMirrorNode) -> int:
    """How many cards a ``SearchLibrary`` puts where it puts them: a ``split``'s
    primary count when only the primary pile goes to the battlefield (Cultivate's
    one of two), else the search's own count (``Fixed`` / ``UpTo`` max). A
    dynamic count (Settle the Wreckage's "that many") reads 1; "any number"
    reads :data:`SEARCH_COUNT_CAP`."""
    split = getattr(node, "split", MISSING)
    if _present(split) and getattr(split, "rest_destination", None) != getattr(
        split, "primary_destination", None
    ):
        primary = getattr(split, "primary_count", None)
        if isinstance(primary, int) and getattr(split, "primary_destination", None) == (
            "Battlefield"
        ):
            return min(primary, SEARCH_COUNT_CAP)
    n = _count_value(node)
    return min(n, SEARCH_COUNT_CAP) if n is not None and n > 0 else 1


def is_self_enters_trigger(unit: AbilityUnit) -> bool:
    """Whether UNIT is a trigger that fires when the card ITSELF enters: an
    enters event watching ``SelfRef`` -- never another permanent entering (Deep
    Gnome Terramancer's "whenever one or more lands enter under an opponent's
    control", a landfall trigger)."""
    if unit.origin != "trigger" or unit.trigger_event not in ENTERS_EVENTS:
        return False
    return tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"


class LandSearch(NamedTuple):
    """One of YOUR land searches (CR 701.23a), one per ability unit."""

    colors: LandColors  # what it can find (see land_search_colors)
    count: int  # lands it puts onto your battlefield (see _battlefield_count)
    to_battlefield: bool  # some found land can enter the battlefield
    enters_tapped: bool  # a land it puts onto the battlefield enters tapped
    on_self_etb: bool  # it rides the card's own enters trigger
    cycling: bool  # a landcycling search: from your hand, into your hand


def _self_searches(unit: AbilityUnit) -> list[TypedMirrorNode]:
    """The unit's ``SearchLibrary`` effects that search YOUR library, judged one
    search at a time along the effect chain. A search's own ``target_player``
    decides (:func:`_searcher_is_self`); a recipient-less search is read off the
    ``Shuffle`` that closes its leg (Demolition Field's "You may search your
    library ..., then shuffle" closes on ``Controller``, after the opponent's
    ``ParentTargetController`` leg); with neither it continues the leg before it
    (Sadistic Sacrament's kicked "instead search that player's library" -- the
    whole-unit continuation :func:`unit_is_self_tutor` describes). The first leg
    with no recipient defaults to you."""
    out: list[TypedMirrorNode] = []
    verdict = True
    current: TypedMirrorNode | None = None
    pending: bool | None = None

    def close() -> None:
        nonlocal verdict
        if current is None:
            return
        verdict = verdict if pending is None else pending
        if verdict:
            out.append(current)

    for c in unit.effects:
        t = tag_of(c.node)
        if t == "SearchLibrary":
            close()
            current = c.node
            pending = _searcher_is_self(getattr(c.node, "target_player", MISSING))
        elif t == "Shuffle" and current is not None and pending is None:
            tgt = tag_of(getattr(c.node, "target", None))
            if tgt in _TUTOR_DIRECTED_PLAYER_TAGS:
                pending = False
            elif tgt in ("Controller", "You"):
                pending = True
    close()
    return out


def _rolled_battlefield_count(roll: TypedMirrorNode, found: int) -> int:
    """The EXPECTED number of found lands a die roll's result rows put onto the
    battlefield, rounded (Druid of the Emerald Grove's d20: 1-9 none, 10-19 one,
    20 both -- 0.45x0 + 0.50x1 + 0.05x2 = 0.6, so 1). A row's single-card
    ``ChangeZone`` moves one land, a ``ChangeZoneAll`` every land found. Rows
    phase left unreadable count 1."""
    sides = getattr(roll, "sides", None)
    rows = getattr(roll, "results", None)
    if not isinstance(sides, int) or sides <= 0 or not isinstance(rows, list):
        return 1
    expected = 0.0
    for row in rows:
        lo, hi = getattr(row, "min", MISSING), getattr(row, "max", MISSING)
        lo = lo if isinstance(lo, int) else 1
        if not isinstance(hi, int):
            return 1
        faces = max(0, min(hi, sides) - max(lo, 1) + 1)
        landed = 0
        for n in iter_typed_nodes(getattr(row, "effect", None)):
            if getattr(n, "destination", None) != "Battlefield":
                continue
            if tag_of(n) == "ChangeZoneAll":
                landed += found
            elif tag_of(n) == "ChangeZone":
                landed += 1
        expected += faces / sides * min(landed, found)
    return round(expected)


#: Phase v0.94.0 loses Verdant Mastery's piles: "Put one of them onto the
#: battlefield tapped under an opponent's control if the {3}{G} cost was paid.
#: Put two of them onto the battlefield tapped under your control and the rest
#: into your hand" parses as uncounted battlefield moves plus a ``ChangeZoneAll``
#: of the revealed cards onto YOUR battlefield (the hand pile). The size of your
#: pile survives only in the ability's own text. Gated on that shape;
#: guarded by ``test_verdant_mastery_piles_are_still_lost_canary``.
_YOUR_PILE_RE = re.compile(
    r"\bput (one|two|three|four|five) of them onto the battlefield tapped "
    r"under your control",
    re.IGNORECASE,
)
_PILE_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def lost_pile_count(unit: AbilityUnit) -> int | None:
    """Your battlefield pile's size where phase lost it (see ``_YOUR_PILE_RE``):
    a ``ChangeZoneAll`` of the revealed cards (``TrackedSet``) onto the
    battlefield under you, beside a library ``ChangeZone`` onto the battlefield
    under you, read from the ability's own description. None otherwise."""
    nodes = list(iter_typed_nodes(unit.node))
    rest_onto_yours = any(
        tag_of(n) == "ChangeZoneAll"
        and tag_of(getattr(n, "target", None)) == "TrackedSet"
        and getattr(n, "destination", None) == "Battlefield"
        and enters_under_you(n)
        for n in nodes
    )
    library_onto_yours = any(
        tag_of(n) == "ChangeZone"
        and getattr(n, "origin", None) == "Library"
        and getattr(n, "destination", None) == "Battlefield"
        and enters_under_you(n)
        for n in nodes
    )
    if not (rest_onto_yours and library_onto_yours):
        return None
    m = _YOUR_PILE_RE.search(str(getattr(unit.node, "description", "") or ""))
    return _PILE_WORDS[m.group(1).lower()] if m else None


def _battlefield_count(unit: AbilityUnit, search: TypedMirrorNode) -> int:
    """How many found lands ``search`` puts onto YOUR battlefield: a die roll's
    expected rows (:func:`_rolled_battlefield_count`), a pile phase lost
    (:func:`lost_pile_count`), else :func:`search_count`."""
    found = search_count(search)
    roll = next(
        (n for n in iter_typed_nodes(unit.node) if tag_of(n) == "RollDie"), None
    )
    if roll is not None:
        return _rolled_battlefield_count(roll, found)
    pile = lost_pile_count(unit)
    return pile if pile is not None else found


def land_searches(tree: ConceptTree) -> tuple[LandSearch, ...]:
    """Every unit of TREE that searches YOUR library for a land.

    Each search is judged on its own (:func:`_self_searches`): an opponent's
    compensation search (Path to Exile, Assassin's Trophy, Ghost Quarter, Settle
    the Wreckage) is not yours, while Demolition Field's own search after the
    opponent's is. A symmetric or another-player-scoped ability is vetoed whole
    (:func:`_unit_search_vetoed`). A landcycling search is yours but flagged
    ``cycling`` (CR 702.29a/e: from your hand, into your hand). The count is the
    unit's FIRST self search, the base clause: Primal Growth's "if this spell was
    kicked, instead search for up to two" rides a later, condition-gated search."""
    out: list[LandSearch] = []
    for unit in tree.units:
        if not any(tag_of(c.node) == "SearchLibrary" for c in unit.effects):
            continue
        if _unit_search_vetoed(unit):
            continue
        found = [
            (node, colors)
            for node in _self_searches(unit)
            if (colors := land_search_colors(getattr(node, "filter", None))) is not None
        ]
        if not found:
            continue
        landings = list(iter_search_landings(unit))
        out.append(
            LandSearch(
                colors=_merge_land_colors(colors for _n, colors in found),
                count=_battlefield_count(unit, found[0][0]),
                to_battlefield=any(d == "Battlefield" for d, _t in landings),
                enters_tapped=any(d == "Battlefield" and t for d, t in landings),
                on_self_etb=is_self_enters_trigger(unit),
                cycling=_is_cycling_search(unit),
            )
        )
    return tuple(out)


def produced_colors(node: TypedMirrorNode) -> frozenset[str] | Literal["any"]:
    """The mana a ``Mana`` effect's ``produced`` spec can add, as colour letters
    (``"C"`` for colorless -- CR 106.1b's six types), or ``"any"``.

    ``Fixed`` / ``Mixed`` name their colours; ``AnyOneColor`` / ``AnyCombination``
    their ``color_options`` (Arcane Sanctum's {W}, {U}, or {B}; all five reads
    ``"any"``); a filter land's ``ChoiceAmongCombinations`` (Cascade Bluffs'
    {U}{U}, {U}{R}, or {R}{R}) the union of its options. A chosen colour and
    every deck- or board-dependent kind (Command Tower's commander identity,
    Exotic Orchard, Mox Amber, Chrome Mox, Reflecting Pool) read ``"any"``.
    ``TriggerEventManaType`` (Mana Flare's "one mana of any type that land
    produced") only repeats the triggering mana, so it names no colour."""
    p = getattr(node, "produced", MISSING)
    if not _present(p):
        return frozenset()
    t = tag_of(p)

    def letters(names: object) -> frozenset[str]:
        out = {
            _MANA_COLOR_LETTER[n]
            for n in (names if isinstance(names, list) else ())
            if isinstance(n, str) and n in _MANA_COLOR_LETTER
        }
        return frozenset(out)

    if t == "Fixed":
        return letters(getattr(p, "colors", None))
    if t == "Mixed":
        cl = getattr(p, "colorless_count", 0)
        return letters(getattr(p, "colors", None)) | (
            frozenset("C") if isinstance(cl, int) and cl > 0 else frozenset()
        )
    if t == "Colorless":
        return frozenset("C")
    if t in ("AnyOneColor", "AnyCombination"):
        got = letters(getattr(p, "color_options", None))
        return "any" if got >= _FIVE_COLORS else got
    if t == "ChoiceAmongCombinations":
        opts = getattr(p, "options", None) or []
        got = frozenset().union(*(letters(o) for o in opts if isinstance(o, list)))
        return "any" if got >= _FIVE_COLORS else got
    if t == "TriggerEventManaType":
        return frozenset()
    return "any"


def mana_colors(tree: ConceptTree) -> frozenset[str] | Literal["any"]:
    """Every colour of mana the card's own ``Mana`` effects add (see
    :func:`produced_colors`). Reads each unit's resolved effects only, so an
    activation cost's ``Mana`` payment (Cascade Bluffs' {U/R}) and a created
    token's own ability are never the card's: a Treasure maker (Smothering Tithe,
    Dockside Extortionist) is not a mana source of its own -- CR 111.10a: the
    Treasure token is the object with the "Add one mana of any color" ability.
    See :func:`_own_mana_effects`."""
    out: set[str] = set()
    for node in _own_mana_effects(tree):
        got = produced_colors(node)
        if got == "any":
            return "any"
        out |= got
    if not out and any(CIRCLED_COLORS_RESIDUE in r for r in tree.residues()):
        return "any"
    return frozenset(out)


#: Phase v0.94.0 parks Cryptic Spires' mana ability ("Add one mana of either of the
#: circled colors") as an ``Unimplemented`` residue, so its trees carry no ``Mana``
#: node. Its rulings: "You circle two colors as you put Cryptic Spires into your deck
#: before any games begin" — a deck-dependent producer, read ``"any"`` like Command
#: Tower. Guarded by ``test_cryptic_spires_mana_is_still_a_residue_canary``.
CIRCLED_COLORS_RESIDUE = "Add one mana of either of the circled colors"


def unit_own_mana(
    unit: AbilityUnit,
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    """``(Mana effect, the ability node carrying it)`` for one unit: the unit's own
    effect chain (carried by ``unit.node``), plus a mana ability the card grants
    ITSELF (a static def ``affected: SelfRef`` -- Urza's Saga's chapter I "This
    Saga gains '{T}: Add {C}.'", carried by the granted body). A grant to other
    permanents (The World Tree's lands, Sachi's Shamans) is theirs, not the
    card's."""
    for c in unit.effects:
        if tag_of(c.node) == "Mana":
            yield c.node, unit.node
    for sdef in unit.static_defs():
        if tag_of(getattr(sdef, "affected", None)) != "SelfRef":
            continue
        for kind, body in iter_nested_granted_bodies(sdef):
            eff = getattr(body, "effect", None)
            if (
                kind == "ability"
                and isinstance(eff, TypedMirrorNode)
                and tag_of(eff) == "Mana"
            ):
                yield eff, body


def _own_mana_effects(tree: ConceptTree) -> Iterator[TypedMirrorNode]:
    """The ``Mana`` effects the card's own abilities resolve (:func:`unit_own_mana`
    over every unit)."""
    for unit in tree.units:
        for eff, _ability in unit_own_mana(unit):
            yield eff


#: Phase v0.104.0 stops modelling a prevention whose TARGET is the damage source
#: (or both source and recipient) and parks the effect as a residue named for the
#: shape — Resistance Fighter's "Prevent all combat damage target creature would
#: deal" (``prevent_damage_recipient_target_role``), Safeguard's "… dealt by
#: target creature" (``prevent_damage_dealt_by_target``), Dovin, Hand of
#: Control's "… dealt to and dealt by target permanent an opponent controls"
#: (``bidirectional_prevent_declared_target``), and one whose damage source is
#: scoped to a relation (``prevention_source_scope``: Wall of Shadows'
#: "… dealt to ~ by creatures it's blocking", Chromatic Armor's "… by sources of
#: the last chosen color"). Each is still a prevention effect
#: (CR 615.1a: effects that use the word "prevent"), so the ``damage_prevention``
#: lane and ``protection.protective_saves`` read the residue's name. Guarded by
#: ``test_parked_prevention_residues_canary``.
PARKED_PREVENTION_RESIDUES: frozenset[str] = frozenset(
    {
        "prevent_damage_recipient_target_role",
        "prevent_damage_dealt_by_target",
        "bidirectional_prevent_declared_target",
        "prevention_source_scope",
    }
)


def parked_prevention(node: object) -> str | None:
    """The :data:`PARKED_PREVENTION_RESIDUES` name ``node`` is parked under, or
    ``None``."""
    if tag_of(node) != "Unimplemented":
        return None
    name = getattr(node, "name", None)
    return name if name in PARKED_PREVENTION_RESIDUES else None


#: Phase v0.94.0 parks Boxing Ring's "Activate only if you control a creature that
#: fought this turn" as an ``unparsed_condition`` residue in the ability's effect
#: chain instead of an ``activation_restrictions`` entry, so the gate is invisible
#: to the typed read. Guarded by ``test_boxing_ring_gate_is_still_a_residue_canary``.
UNPARSED_ACTIVATION_GATE = "Activate only if"


def _unit_activation_gated(unit: AbilityUnit) -> bool:
    """Whether an ability may be activated only while a condition holds ("Activate
    only if you control three or more artifacts", "… during an opponent's turn"):
    a ``RequiresCondition`` activation restriction (CR 602.5 — a player can't begin
    to activate a prohibited ability), or the residue phase parks one as
    (:data:`UNPARSED_ACTIVATION_GATE`). Phase files a max speed ability the same
    way; by the rules it is a static that grants the ability only while your speed
    is 4 (CR 702.178a), which comes to the same thing here. Timing-only and per-turn
    limits ("as a sorcery", "once each turn") aren't conditions."""
    if next(activation_restriction_conditions(unit.node), MISSING) is not MISSING:
        return True
    return any(
        tag_of(c.node) == "Unimplemented"
        and residue_is(c.node, "unparsed_condition")
        and (getattr(c.node, "description", "") or "").startswith(
            UNPARSED_ACTIVATION_GATE
        )
        for c in unit.effects
    )


def mana_ability_gates(tree: ConceptTree) -> tuple[bool, ...]:
    """One entry per ability of the card's that adds mana or makes a Treasure: whether
    it is gated on a condition (:func:`_unit_activation_gated` — Mox Opal's
    metalcraft, Mox Jasper's Dragon, Tablet of Compleation's oil counters). A card
    whose every entry is gated (Mox Opal) ramps only when the condition holds; one
    with an ungated sibling (Fanatic of Rhonas' {T}: Add {G}) always ramps. A mana
    ability the card grants itself is one entry (:func:`unit_own_mana`). A fact
    about the card, no policy: the tuner's ramp SOURCING reads it
    (``roles.is_reliable_ramp``); COUNTING a deck's ramp (``roles.is_ramp``)
    deliberately doesn't."""
    out: list[bool] = []
    for unit in tree.units:
        abilities = {id(ab): ab for _eff, ab in unit_own_mana(unit)}
        if any(
            c.concept == "make_token" and "Treasure" in c.subject for c in unit.effects
        ):
            abilities.setdefault(id(unit.node), unit.node)
        out.extend(
            _unit_activation_gated(unit)
            if ab is unit.node
            else next(activation_restriction_conditions(ab), MISSING) is not MISSING
            for ab in abilities.values()
        )
    return tuple(out)


# ── Mass land denial (Commander Brackets) ──────────────────────────────────────
# Wizards' Commander Brackets define mass land denial as "cards that regularly
# destroy, exile, and bounce other lands, keep lands tapped, or change what mana
# is produced by four or more lands per player without replacing them" (examples:
# Armageddon, Ruination, Sunder, Winter Orb, Blood Moon). The CR has no bracket
# rule; this read is the definition's shapes over phase's trees, and its calls
# (four lands, "regularly", "without replacing them") are the lane's own reading
# of that definition.

#: How a card denies lands in bulk — the ``mass_land_denial`` signal's subject.
LandDenialKind = Literal[
    "destroy", "exile", "bounce", "sacrifice", "untap_lock", "mana_change"
]
LAND_DENIAL_KINDS: tuple[LandDenialKind, ...] = get_args(LandDenialKind)

#: The basic land types (CR 205.3i, 305.6).
_BASIC_LAND_TYPES: frozenset[str] = frozenset(BASIC_LAND_TYPE_COLORS)
# The filter properties a "lands as a class" filter may carry: a basic or
# nonbasic restriction (Ruination's nonbasic lands) and the battlefield zone.
# Anything narrower (Wake of Destruction's "same name", Tsabo's Web's lands
# with an activated ability, Freyalise's Radiance's snow permanents) is not
# every land a player controls.
_MASS_LAND_SUPERTYPE_PROPS = frozenset({"NotSupertype", "HasSupertype"})
_MASS_LAND_REMOVAL_KIND: dict[str, LandDenialKind] = {
    "DestroyAll": "destroy",
    "BounceAll": "bounce",
    "ChangeZoneAll": "exile",
}
# The players a land sacrifice can reach and still be "other lands": every
# player, each opponent, a chosen player (Epicenter's "target player").
_DENIAL_REACH = frozenset({"each", "opponents", "per_opponent", "target", "scoped"})
# The durations that end by the next turn (CR 514.2's "until end of turn", a next
# step or turn): a lock that short is not "regularly" keeping lands tapped
# (Nightcreep's one turn of Swamps). Any other duration lasts — and a resolving
# effect that states none "lasts until the end of the game" (CR 611.2a).
_SHORT_DURATIONS = frozenset(
    {
        "UntilEndOfTurn",
        "UntilNextStepOf",
        "UntilNextTurnOf",
        "UntilControllersNextTurn",
        "UntilEndOfNextTurnOf",
    }
)

#: Phase drops the narrowing clause from two "permanents" sweeps and parses each as
#: every permanent: Eye of Singularity ("each permanent with the same name as
#: another permanent, except for basic lands") and Herald of Vengeance ("each
#: permanent you don't control that has the same name as …"). (End Hostilities'
#: "all permanents attached to creatures" was the third until v0.104.0, which
#: parks it as an ``attached_to_qualifier`` residue.) Every other all-permanents
#: sweep in the legal corpus is a true one (Apocalypse, Upheaval, Worldfire,
#: Worldpurge, Dimensional Breach, Soulscour, Bearer of the Heavens). An
#: every-permanent sweep on a card whose text names one of these narrowings is
#: vetoed. Guarded by
#: ``test_narrowed_permanent_sweeps_canary``.
NARROWED_PERMANENT_SWEEPS = ("same name as",)


def _land_class_arm(
    filt: object, *, battlefield_default: bool, own_ok: bool, permanents: bool
) -> bool:
    """Whether one ``Typed`` filter arm names lands as a class: a ``Land`` core
    type, a basic land type (Choke's Islands), or, with ``permanents``, every
    permanent (Apocalypse, Upheaval) unless it excludes lands (a "nonland
    permanent" sweep). ``battlefield_default``: whether an arm without an
    ``InZone`` reads the battlefield (the effect's own origin is the battlefield
    or unset)."""
    if tag_of(filt) != "Typed":
        return False
    if not own_ok and getattr(filt, "controller", None) == "You":
        return False
    zone: object = None
    for prop in getattr(filt, "properties", None) or ():
        ptag = tag_of(prop)
        if ptag == "InZone":
            zone = getattr(prop, "zone", None)
        elif not (
            ptag in _MASS_LAND_SUPERTYPE_PROPS
            and getattr(prop, "value", None) == "Basic"
        ):
            return False
    if zone is None and not battlefield_default:
        return False
    if zone is not None and zone != "Battlefield":
        return False
    cores = set(filter_core_types(filt))
    if "Land" in cores or set(filter_subtypes(filt)) & _BASIC_LAND_TYPES:
        return True
    return permanents and "Permanent" in cores and "Land" not in filter_non_types(filt)


def _names_land_class(
    filt: object,
    *,
    battlefield_default: bool = True,
    own_ok: bool = False,
    permanents: bool = True,
) -> bool:
    """Whether ``filt`` (or any arm of an ``Or``) names lands as a class on the
    battlefield, not limited to your own (``own_ok`` lifts that last check for a
    sacrifice whose player scope already says who sacrifices). ``permanents``
    admits "all permanents", which take the lands with them (Apocalypse, Static
    Orb); a sacrifice turns it off, since each player picks which permanents
    (Smokestack). See :func:`_land_class_arm`."""
    return any(
        _land_class_arm(
            f,
            battlefield_default=battlefield_default,
            own_ok=own_ok,
            permanents=permanents,
        )
        for f in or_arms(filt)
    )


def _sacrifices_four_or_more(count: object) -> bool:
    """Whether a sacrifice's ``count`` reaches the definition's "four or more
    lands per player": a fixed four or more (Wildfire's four, not Ember
    Swallower's three), or a count that grows with the board — X (Death Cloud,
    Tectonic Break), every land (Epicenter's threshold, Keldon Firebombers), the
    rest after a choice (Restore Balance). A fraction is not: Pox's "a third of
    the lands they control, rounded up" reaches four only at ten lands."""
    if isinstance(count, int):
        return count >= 4
    if tag_of(count) == "Fixed":
        value = getattr(count, "value", 0)
        return isinstance(value, int) and value >= 4
    return tag_of(count) not in (None, "DivideRounded")


def _gives_lands_back(unit: AbilityUnit) -> bool:
    """Whether the same ability lets the players who lost lands search for lands
    to put back (From the Ashes, Wave of Vitriol: "its controller may search
    their library for a basic land card") — the definition's "without replacing
    them". Fall of the Thran's returns sit on later chapters, two lands each,
    and do not count."""
    for n in unit.iter_typed():
        if tag_of(n) != "SearchLibrary":
            continue
        facts = search_filter_land_facts(getattr(n, "filter", None))
        searcher = _searcher_is_self(getattr(n, "target_player", MISSING))
        if facts is not None and facts[0] and searcher is False:
            return True
    return False


def _lasting_static_defs(
    unit: AbilityUnit, *, permanent_card: bool
) -> Iterator[TypedMirrorNode]:
    """The static defs of ``unit`` that last: a permanent's own statics, and a
    resolving effect's statics unless its duration ends by the next turn
    (:data:`_SHORT_DURATIONS`). An instant's or sorcery's top-level static never
    lasts: an instant or sorcery spell's abilities usually function only while it
    is on the stack (CR 113.6), so a static one prints is a one-shot effect it
    applies as it resolves (Ethereal Grasp's perpetual "doesn't untap" grant)."""
    if unit.origin == "static":
        if permanent_card:
            yield from unit.static_defs()
        return
    for n in unit.iter_typed():
        if tag_of(n) != "GenericEffect" or node_duration(n) in _SHORT_DURATIONS:
            continue
        for sdef in getattr(n, "static_abilities", None) or ():
            if isinstance(sdef, TypedMirrorNode):
                yield sdef


def _unit_land_denial(
    unit: AbilityUnit, *, permanent_card: bool, oracle: str
) -> LandDenialKind | None:
    """The mass-land-denial shape one ability carries, or ``None``."""
    for sdef in _lasting_static_defs(unit, permanent_card=permanent_card):
        mode = static_mode_tag(sdef)
        affected = static_affected(sdef, unit)
        if mode == "CantUntap" and _names_land_class(affected):
            return "untap_lock"  # Back to Basics, Choke, Mist of Stagnation
        if mode == "MaxUntapPerType" and _names_land_class(
            static_mode_field(sdef, "filter")
        ):
            return "untap_lock"  # Winter Orb, Static Orb
        if (
            mode == "SkipStep"
            and static_mode_field(sdef, "step") == "Untap"
            and _present(affected)
            and _scope_from_player_node(affected) != "you"
        ):
            return "untap_lock"  # Stasis: players skip their untap steps
        if mode == "Continuous" and _names_land_class(affected, permanents=False):
            mods = getattr(sdef, "modifications", None) or ()
            if any(tag_of(m) == "SetBasicLandType" for m in mods):
                # Blood Moon: a land set to a basic land type loses its other
                # abilities and makes only that type's mana (CR 305.7).
                return "mana_change"
    if (
        unit.origin == "replacement"
        and permanent_card
        and replacement_event_tag(unit.node) == "ProduceMana"
        and tag_of(getattr(unit.node, "mana_modification", None)) == "ReplaceWith"
        and _names_land_class(getattr(unit.node, "valid_card", None), permanents=False)
    ):
        return "mana_change"  # Contamination, Ritual of Subdual
    if _gives_lands_back(unit):
        return None
    narrowed = any(phrase in oracle for phrase in NARROWED_PERMANENT_SWEEPS)
    found: list[LandDenialKind] = []
    for n in unit.iter_typed():
        tag = tag_of(n)
        if tag in _MASS_LAND_REMOVAL_KIND:
            destination = getattr(n, "destination", None)
            if destination == "Battlefield":
                continue  # Planar Birth, Second Sunrise put lands back
            target = getattr(n, "target", None)
            origin_ok = getattr(n, "origin", None) in (None, "Battlefield")
            if _names_land_class(
                target, battlefield_default=origin_ok, permanents=not narrowed
            ):
                if tag == "ChangeZoneAll" and destination == "Hand":
                    found.append("bounce")
                else:
                    found.append(_MASS_LAND_REMOVAL_KIND[tag])
        elif tag == "Sacrifice":
            if (
                effect_player_reach(unit.node, n) in _DENIAL_REACH
                and _names_land_class(
                    getattr(n, "target", None), own_ok=True, permanents=False
                )
                and _sacrifices_four_or_more(getattr(n, "count", None))
            ):
                found.append("sacrifice")
        elif tag == "ChooseAndSacrificeRest":
            if "Land" in (getattr(n, "categories", None) or ()):
                found.append("sacrifice")  # Cataclysm: one land kept, the rest go
    # The removal first, in LAND_DENIAL_KINDS order (the deep walk's order is not
    # the card's): Omen of Fire bounces every Island before its Plains sacrifice.
    return min(found, key=LAND_DENIAL_KINDS.index, default=None)


def mass_land_denial(tree: ConceptTree) -> LandDenialKind | None:
    """How the card denies lands in bulk, per the Commander Brackets' definition
    of mass land denial (see the section comment), or ``None``:

    * ``"destroy"`` / ``"exile"`` / ``"bounce"`` — removes lands as a class, not
      only your own (Armageddon, Ruination, Boil, Ajani Vengeant's "all lands
      target player controls"; Apocalypse's and Worldfire's exile; Sunder's,
      Upheaval's and Omen of Fire's bounce);
    * ``"sacrifice"`` — makes players sacrifice four or more lands each, or every
      land but a few (Wildfire, Death Cloud's X, Cataclysm, Restore Balance);
    * ``"untap_lock"`` — keeps lands tapped, lastingly (Winter Orb, Static Orb,
      Back to Basics, Choke, Stasis) — not for one untap step (Exhaustion);
    * ``"mana_change"`` — changes the mana lands produce, lastingly (Blood Moon,
      Contamination) — not for one turn (Nightcreep).

    The lane's own readings of the definition: a one-land edict is not mass
    denial (Yawning Fissure, Tremble), nor a destruction its own ability gives
    back (From the Ashes), nor a lock on your own lands only (Mungha Wurm,
    Celestial Dawn)."""
    permanent_card = not is_spell_card(tree)
    for unit in tree.units:
        kind = _unit_land_denial(
            unit, permanent_card=permanent_card, oracle=tree.oracle or ""
        )
        if kind is not None:
            return kind
    return None


# ── Closers: game wins and reach ───────────────────────────────────────────────


def ends_the_game(tree: ConceptTree) -> bool:
    """Whether the card can end the game in your favour by its own effect: you win
    (CR 104.2b — Felidar Sovereign, Thassa's Oracle, Laboratory Maniac) or
    another player loses (CR 104.3e — Door to Nothingness, Phage's combat-damage
    trigger). A loss aimed at you is a drawback (Pact of Negation's upkeep
    payment, Phage's own enters trigger), and "can't win / can't lose" statics
    (Platinum Angel) are protection, not effects."""
    for n in tree.iter_typed():
        tag = tag_of(n)
        if tag not in ("WinTheGame", "LoseTheGame"):
            continue
        target = getattr(n, "target", MISSING)
        who = _scope_from_player_node(target) if _present(target) else "you"
        if (tag == "WinTheGame") == (who == "you"):
            return True
    return False


def _hits_one_other_player(node: TypedMirrorNode) -> bool:
    """Whether a life loss is directed at another player (a target or relative
    player — :func:`lifeloss_recipient_scope`) or a damage effect can be aimed at a
    player (:func:`damage_recipient_is_player` with ``aimed``)."""
    if tag_of(node) == "LoseLife":
        return lifeloss_recipient_scope(node) == "opponents"
    if tag_of(node) == "DealDamage":
        target = _unwrap_role_target(getattr(node, "target", MISSING))
        return damage_recipient_is_player(target, aimed=True)
    return False


#: The effects that take life from players: life loss (CR 119.3) and damage.
_REACH_EFFECT_TAGS: frozenset[str] = frozenset(
    {"LoseLife", "DealDamage", "DamageEachPlayer", "DamageAll"}
)


def reach_amount(
    root: object, node: TypedMirrorNode
) -> tuple[Literal["group", "single"], int | None] | None:
    """Who a burn / drain effect reaches and how much it takes, or ``None``.

    ``"group"`` — each opponent (Exsanguinate, Gray Merchant of Asphodel,
    Kokusho, Fanatic of Mogis); ``"single"`` — one chosen player or any target
    (Blood Artist, Sanguine Bond's target opponent, Aetherflux Reservoir,
    Fireball). A symmetric "each player" effect (Earthquake, Crypt Rats) and a
    loss you take are neither. The amount is the fixed number, or ``None`` when
    it scales — X, a count, a devotion, a doubled X (Debt to the Deathless), or a
    fixed loss repeated X times (Torment of Hailfire)."""
    tag = tag_of(node)
    if tag not in _REACH_EFFECT_TAGS:
        return None
    scope: Literal["group", "single"]
    if effect_player_reach(root, node) in ("opponents", "per_opponent"):
        scope = "group"
    elif _hits_one_other_player(node):
        scope = "single"
    else:
        return None
    owner = _find_owner_wrapper(root, node)
    repeated = owner is not None and _present(getattr(owner, "repeat_for", MISSING))
    if repeated or amount_is_scaling(node):
        return scope, None
    return scope, amount_factor(node)


#: Phase v0.94.0 replaces an effect whose amount is "X, where X is <a count>" with
#: a ``where_x_binding`` residue that keeps only the binding (Insatiable
#: Hemophage's "each opponent loses X life …, where X is the number of times ~ has
#: mutated", Zenith Flare's "deals X damage to any target …"), so no LoseLife /
#: DealDamage node is left to read. Gated on that residue, the card's own "where X
#: is" line says who loses the X; its amount scales. Guarded by
#: ``test_unbound_x_reach_canary``.
_UNBOUND_X_GROUP_RE = re.compile(
    r"each opponent loses X life|deals X damage to each opponent", re.IGNORECASE
)
_UNBOUND_X_SINGLE_RE = re.compile(
    r"deals X damage to (?:any target|target (?:player|opponent))"
    r"|target (?:player|opponent) loses X life",
    re.IGNORECASE,
)


def unbound_x_reach(tree: ConceptTree) -> Literal["group", "single"] | None:
    """The reach scope of an effect phase parked as a ``where_x_binding`` residue
    (see :data:`_UNBOUND_X_GROUP_RE`), or ``None``; its amount always scales."""
    if next(tree.effect_residues("where_x_binding"), None) is None:
        return None
    lines = [ln for ln in (tree.oracle or "").splitlines() if "where X is" in ln]
    if any(_UNBOUND_X_GROUP_RE.search(ln) for ln in lines):
        return "group"
    if any(_UNBOUND_X_SINGLE_RE.search(ln) for ln in lines):
        return "single"
    return None


def parked_search_puts_onto_battlefield(tree: ConceptTree) -> bool:
    """Whether phase parked a library search as a ``where_x_binding`` residue and
    kept only its put: an ability holding the residue whose searched card lands
    on the battlefield (:func:`iter_search_landings`). Surveyor's Scope's "Search
    your library for up to X basic land cards, where X is … Put those cards onto
    the battlefield" (phase v0.104.0): the ``SearchLibrary`` node is gone, so the
    put is the only structure left. A workaround: ``test_parked_search_put_canary``
    fails once phase reads the search."""
    if next(tree.effect_residues("where_x_binding"), None) is None:
        return False
    return any(
        any(residue_is(c.node, "where_x_binding") for c in unit.effects)
        and any(dest == "Battlefield" for dest, _ in iter_search_landings(unit))
        for unit in tree.iter_units()
    )


#: The blocking restrictions an attacker can carry on itself — evasion abilities
#: in CR 509.1b's sense: "can't be blocked" (Phantom Warrior), "can't be blocked
#: except by three or more creatures" (Pathrazer of Ulamog), "can't be blocked
#: unless all creatures defending player controls block it" (Tromokratis).
_SELF_EVASION_MODES: frozenset[str] = frozenset(
    {"CantBeBlocked", "CantBeBlockedExceptBy", "CantBeBlockedUnlessAllBlock"}
)


def is_evasive_body(tree: ConceptTree) -> bool:
    """Whether the card restricts what can block it by a static on itself (see
    :data:`_SELF_EVASION_MODES`) — the static half of "an evasive body"; the keyword
    half is ``card_classify.EVASION_KEYWORDS``. Not the ``evasion_self`` lane: that
    one also fires on cards that GRANT evasion to others, and leaves flying out as
    soft evasion, so it can't say whether the card itself is hard to block."""
    return any(
        static_mode_tag(sdef) in _SELF_EVASION_MODES
        and tag_of(getattr(sdef, "affected", None)) == "SelfRef"
        for unit in tree.units
        for sdef in unit.static_defs()
    )


# ── Team buffs ──────────────────────────────────────────────────────────────

# Evergreen team-anthem keywords (CR 702), in phase's spaceless lowercase spelling
# (a keyword name normalized via lower + strip spaces: "doublestrike").
TEAM_BUFF_GRANT_KW: frozenset[str] = frozenset(
    {
        "flying",
        "trample",
        "menace",
        "hexproof",
        "indestructible",
        "protection",
        "deathtouch",
        "lifelink",
        "doublestrike",
        "firststrike",
        "vigilance",
        "haste",
        "ward",
        "reach",
    }
)
# Predicates a GENERIC your-team anthem subject may carry (Always Watching's
# NonToken, "each OTHER creature you control") — mirrors ``_TEAM_BUFF_OK_PREDS``.
_TEAM_BUFF_OK_PREDS: frozenset[str] = frozenset({"NonToken", "Another", "Other"})


def _names_every_creature(filt: object) -> bool:
    """Whether a filter holds creatures as a whole: a ``Typed`` whose only core
    type is Creature, or an ``Or`` with such an arm ("creatures and
    planeswalkers you control" — Sorin, Vengeful Bloodlord). A second core type
    in the same ``Typed`` narrows it ("artifact creatures" — Tempered Steel,
    Thopter Engineer)."""
    if tag_of(filt) == "Or":
        return any(_names_every_creature(f) for f in getattr(filt, "filters", ()) or ())
    return tag_of(filt) == "Typed" and filter_core_types(filt) == ("Creature",)


def is_team_buff_filter(filt: object) -> bool:
    """The team_buff anthem subject (CR 604.3): GENERIC creatures YOU control
    — every creature, not a card-type subset (:func:`_names_every_creature`),
    no subtypes (tribal is type_matters), predicates at most
    NonToken/Another/Other (Always Watching stays in; an Attacking / colour /
    chosen-type / keyword / equipped narrowing fails). The one whole-team test,
    for a keyword grant and a static anthem alike."""
    return (
        filter_controller(filt) == "You"
        and _names_every_creature(filt)
        and not filter_subtypes(filt)
        and set(filter_predicates(filt)) <= _TEAM_BUFF_OK_PREDS
    )


def is_attacking_team_filter(filt: object) -> bool:
    """The attacking part of your team as a group (CR 508.1k: a declared attacker
    "remains an attacking creature until" it leaves combat): "attacking creatures
    you control" (Jazal Goldmane, Tears of Rage), "other attacking creatures"
    (Qala, Ajani's Pridemate), "attacking tokens you control" (Waystone's
    Guidance, Neyali, Suns' Vanguard) — no subtype, colour or other narrowing
    (:func:`is_team_buff_filter`'s whole team, attacking)."""
    return _team_part_filter(filt, "Attacking")


def is_token_team_filter(filt: object) -> bool:
    """Your creature tokens as a group: "creature tokens you control"
    (Intangible Virtue), "tokens you control" — no subtype, colour or other
    narrowing (:func:`is_team_buff_filter`'s whole team, its tokens)."""
    return _team_part_filter(filt, "Token")


def _team_part_filter(filt: object, part: str) -> bool:
    """Whether a filter is your whole team narrowed only by ``part`` (a
    predicate: ``Attacking``, ``Token``) — tokens of no named type count, a
    token being a creature or not."""
    preds = set(filter_predicates(filt))
    if (
        filter_controller(filt) != "You"
        or part not in preds
        or filter_subtypes(filt)
        or not preds - {part, "Token"} <= _TEAM_BUFF_OK_PREDS
    ):
        return False
    if "Token" in preds and not filter_core_types(filt):
        return True
    return _names_every_creature(filt)


def team_buff_sites(
    tree: ConceptTree,
) -> Iterator[tuple[AbilityUnit, TypedMirrorNode]]:
    """Every ``(unit, static def)`` granting the team an evergreen keyword — the
    one walk behind the ``team_buff`` lane and the tuner's closer read, which asks
    the unit's ``origin`` (a one-shot pump vs a static anthem)."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("AddKeyword", "AddKeywordUntilEndOfTurn"):
                continue
            kw = getattr(mod, "keyword", None)
            if not isinstance(kw, str):
                continue
            if kw.lower().replace(" ", "") not in TEAM_BUFF_GRANT_KW:
                continue
            if is_team_buff_filter(getattr(sdef, "affected", None)):
                yield unit, sdef


def pump_keyword_grants(
    tree: ConceptTree,
) -> Iterator[tuple[AbilityUnit, ConceptNode, str]]:
    """``(unit, pump concept, keyword)`` per keyword a pump's own description
    grants that phase dropped beside it — the recovery stage's partly-read grant
    on a ``Pump`` / ``PumpAll`` (``ConceptNode.body_keywords``): "creatures you
    control gain trample and get +1/+1 for each basic land type" typed as a bare
    ``PumpAll`` (Tromp the Domains), "other Elves you control gain vigilance and
    get +1/+1" (Haldir, Lórien Lieutenant). The grantee is the pump's own object
    (:func:`effect_filter`); the keyword is in :func:`keyword_subject` spelling."""
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) in ("Pump", "PumpAll"):
                for kw in c.body_keywords:
                    yield unit, c, kw


def static_def_adds_power(sdef: object) -> bool:
    """Whether a static def's modifications raise power: a positive ``AddPower``
    (Overrun's +3, Triumph of the Hordes' +1) or an ``AddDynamicPower``
    (Craterhoof Behemoth's +X, X the number of creatures you control) — CR
    613.4c's power-changing effects."""
    for mod in getattr(sdef, "modifications", None) or ():
        tag = tag_of(mod)
        if tag == "AddDynamicPower":
            return True
        if tag == "AddPower" and (mod_value(mod) or 0) > 0:
            return True
    return False


# ── Keyword grants and protective keywords ─────────────────────────────────────
# Shared by the AddKeyword grant lanes (``lanes.triggers_damage``) and the
# board-protection reads (``crosswalk.protection``), so the two walk one way.

#: The protective keywords (normalised — :func:`normalised_keyword_name`):
#: hexproof (CR 702.11b-c), shroud (702.18a), indestructible (702.12b),
#: protection (702.16b) and ward (702.21a).
PROTECTIVE_KEYWORDS: frozenset[str] = frozenset(
    {"hexproof", "shroud", "indestructible", "ward", "protection"}
)


def normalised_keyword_name(kw: str) -> str:
    """A phase keyword spelling folded for set membership: lower case, no
    spaces, no hyphens (``JumpStart`` → ``jumpstart``, ``TotemArmor`` →
    ``totemarmor``)."""
    return kw.lower().replace(" ", "").replace("-", "")


def normalised_keyword(mod: object) -> str:
    """The normalised keyword name an ``AddKeyword`` modification carries (``""``
    for none) — :func:`mod_keyword_name` folded by
    :func:`normalised_keyword_name`."""
    if not isinstance(mod, TypedMirrorNode) or tag_of(mod) != "AddKeyword":
        return ""
    return normalised_keyword_name(mod_keyword_name(mod) or "")


def protective_keyword(mod: object) -> str | None:
    """The protective keyword an ``AddKeyword`` modification grants (one of
    :data:`PROTECTIVE_KEYWORDS`), or ``None``. "Hexproof from [quality]" is a
    hexproof ability (CR 702.11d), so it reads as ``"hexproof"``."""
    name = normalised_keyword(mod)
    if name == "hexprooffrom":
        name = "hexproof"
    return name if name in PROTECTIVE_KEYWORDS else None


_TRACKED_SET_PRODUCER_TAGS: frozenset[str] = frozenset({"Token", "CopyTokenOf"})
#: Every ``*All`` Effect variant phase declares (v0.94.0) — each acts on EVERY
# object its filter matches, never on a chosen target, so a "those creatures"
# after one names a board filter, not the chain's targets. Wider than
# :data:`MASS_EFFECT_TAGS` (the mass effects whose object filter decides who a
# removal / reach read hits): this set only ends a target thread.
ALL_VARIANT_EFFECT_TAGS: frozenset[str] = frozenset(
    {
        "BounceAll",
        "ChangeZoneAll",
        "CounterAll",
        "DamageAll",
        "DestroyAll",
        "DoublePTAll",
        "ExploreAll",
        "GainControlAll",
        "GoadAll",
        "PumpAll",
        "PutCounterAll",
        "UnattachAll",
    }
)
_THREAD_ENDING_TAGS: frozenset[str] = (
    _TRACKED_SET_PRODUCER_TAGS | ALL_VARIANT_EFFECT_TAGS
)


def ends_target_thread(eff: TypedMirrorNode) -> bool:
    """A token producer or a mass effect ends the chosen-target thread."""
    return tag_of(eff) in _THREAD_ENDING_TAGS


def iter_tracked_set_target_grants(
    ability_like: object, *, mod_tags: frozenset[str] = _ADD_KEYWORD
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(threaded_target_filter, AddKeyword_mod)`` pairs for a keyword grant
    whose nested static's ``affected`` is ``TrackedSet`` — "those creatures
    gain X" back-referencing the chain's own TARGETS.

    phase v0.94.0 parses Arm the Cathars ("target creature gets +3/+3, up to
    one other target creature gets +2/+2, … Those creatures gain vigilance")
    as a Pump chain ending in a ``GenericEffect`` whose static is
    ``TrackedSet``-affected; v0.86.0 wrote ``ParentTarget``, which
    :func:`iter_single_target_grants` threads. Same thread
    (:func:`iter_threaded_target_statics`), but a token producer or a mass
    effect ends it (:func:`ends_target_thread`) — "create a token. It gains
    haste" tracks the made token, and "put a +1/+1 counter on each creature
    you control. Those creatures gain vigilance" (Ajani Goldmane, a
    ``PutCounterAll``) tracks a board filter, never a chosen target.
    CR 115.1 / 613.1f.
    """
    for tracked, st in iter_threaded_target_statics(
        ability_like, affected_tag="TrackedSet", resets_thread=ends_target_thread
    ):
        for mod in getattr(st, "modifications", None) or ():
            if tag_of(mod) in mod_tags:
                yield tracked, mod


def unit_keyword_grants(
    unit: AbilityUnit, *, mod_tags: frozenset[str] = _ADD_KEYWORD
) -> list[tuple[object, TypedMirrorNode]]:
    """``(chosen_target_filter, AddKeyword_mod)`` for every keyword grant to a
    chosen target in one unit: the DEEP local-target leaf on any unit (a
    trigger, a modal arm, a Saga chapter — :func:`iter_deep_target_grants`),
    plus, on an ability or trigger, the threaded "It gains X" walk
    (:func:`iter_single_target_grants`) and the "those creatures" walk
    (:func:`iter_tracked_set_target_grants`). The ``keyword_grant_target`` /
    ``protection_grant`` lane and ``crosswalk.protection`` read this one walk;
    ``mod_tags`` projects it to another grant (:data:`ABILITY_GRANT_MOD_TAGS`:
    a quoted ability — Feign Death, Retraction Helix). CR 613.1f (layer 6,
    ability-adding effects)."""
    grants = list(iter_deep_target_grants(unit.node, mod_tags=mod_tags))
    if unit.origin in ("ability", "trigger"):
        grants.extend(iter_single_target_grants(unit.node, mod_tags=mod_tags))
        grants.extend(iter_tracked_set_target_grants(unit.node, mod_tags=mod_tags))
    return grants


def is_spell_card(tree: ConceptTree) -> bool:
    """Whether the card is an instant or sorcery (no permanent face)."""
    return bool(tree.card_types) and set(tree.card_types) <= {"Instant", "Sorcery"}


def redirects_stack_object(node: object) -> bool:
    """Whether a ``ChangeTargets`` node retargets a spell or ability on the stack
    (CR 115.7: "Some effects allow a player to change the target(s) of a spell
    or ability"): Misdirection, Deflecting Swat, Spellskite, Reroute's "Change
    the target of target activated ability with a single target". A follow-on
    retarget of a stolen spell (Commandeer — its target is a back-reference, no
    stack leaf; :func:`steals_stack_spell` reads that case) and
    copy-with-new-targets (Fork — a field on its ``CopySpell``, CR 707.10c) are
    not."""
    if tag_of(node) != "ChangeTargets":
        return False
    return any(
        tag_of(x) in ("StackSpell", "StackAbility")
        for x in iter_typed_nodes(getattr(node, "target", None))
    )


def steals_stack_spell(unit: AbilityUnit) -> bool:
    """Whether a unit takes control of a spell on the stack — "Gain control of
    target noncreature spell. You may choose new targets for it" (Commandeer;
    its ruling: "After Commandeer resolves, you control the targeted spell"),
    Aethersnatch's "Gain control of target spell", and Perplexing Chimera's
    "exchange control of ~ and that spell" off its opponent-casts trigger, and
    Invert Polarity's "Choose target spell … gain control of that spell" (a
    back-reference to the spell the unit chose). A removal spell aimed at your
    board is answered by taking it."""
    nodes = list(iter_typed_nodes(unit.node))
    chooses_spell = any(
        tag_of(getattr(n, "target", None)) == "StackSpell" for n in nodes
    )
    for n in nodes:
        tag = tag_of(n)
        target = getattr(n, "target", None)
        if tag == "GainControl" and (
            any(tag_of(x) == "StackSpell" for x in iter_typed_nodes(target))
            or (
                chooses_spell and tag_of(target) in ("ParentTarget", "TriggeringSource")
            )
        ):
            return True
        if (
            tag == "ExchangeControl"
            and unit.origin == "trigger"
            and getattr(unit.node, "mode", None) == "SpellCast"
            and "TriggeringSource"
            in (
                tag_of(getattr(n, "target_a", None)),
                tag_of(getattr(n, "target_b", None)),
            )
        ):
            return True
    return False


# ── Activated abilities, blocking limits, combat-damage triggers ────────────────


def activation_zone(node: object) -> str | None:
    """The zone an activated ability says it works from (``activation_zone``:
    ``"Hand"`` for cycling, ``"Graveyard"`` for unearth or embalm), or ``None``
    when it names none — CR 113.6b: "An ability that states which zones it
    functions in functions only from those zones"."""
    zone = getattr(node, "activation_zone", MISSING)
    return zone if isinstance(zone, str) else None


def unit_zones(unit: AbilityUnit) -> frozenset[str]:
    """The zones a unit functions from when it says so (:func:`ability_zones` of
    its node)."""
    return ability_zones(unit.node)


def ability_zones(node: object) -> frozenset[str]:
    """The zones an ability functions from when it says so (CR 113.6b): a
    trigger's ``trigger_zones``, an activated ability's :func:`activation_zone`,
    and an "if this card is in your graveyard" ``SourceInZone`` condition
    (Ichorid) — on the ability, or as an activation restriction (Loathsome Troll's
    "Activate only if this card is in your graveyard"). Takes a granted ability's
    body as well as a unit's node."""
    zones: set[str] = set()
    tz = getattr(node, "trigger_zones", None)
    if isinstance(tz, list):
        for raw in tz:
            z = raw.key if isinstance(raw, MirrorVariant) else raw
            if isinstance(z, str):
                zones.add(z)
    if (az := activation_zone(node)) is not None:
        zones.add(az)
    for cond in (
        getattr(node, "condition", None),
        *activation_restriction_conditions(node),
    ):
        zone = getattr(cond, "zone", None)
        if tag_of(cond) == "SourceInZone" and isinstance(zone, str):
            zones.add(zone)
    return frozenset(zones)


def _functions_on_battlefield(unit: AbilityUnit) -> bool:
    """Whether an activated ability can be activated while its object is on the
    battlefield: no other :func:`activation_zone` (cycling, CR 702.29a, "functions
    only while the card with cycling is in a player's hand"), and not ninjutsu,
    which names no zone but "functions only while the card with ninjutsu is in a
    player's hand" (CR 702.49a). Phase's synthesized suspend unit is a special
    action, not an ability at all (CR 116.2f), and carries the hand zone too."""
    if activation_zone(unit.node) not in (None, "Battlefield"):
        return False
    return tag_of(getattr(unit.node, "cost", None)) != "NinjutsuFamily"


def activated_ability_units(
    tree: ConceptTree, *, include_mana: bool = True
) -> Iterator[AbilityUnit]:
    """The card's activated abilities ("[Cost]: [Effect.]", CR 602.1) that work on
    the battlefield (:func:`_functions_on_battlefield`) — what a copier of the
    object's abilities or a commander borrowing them can use. Loyalty abilities are
    activated abilities (CR 606.1) and Equip is one (CR 702.6a), so both stay in.
    ``include_mana=False`` leaves out mana abilities (CR 605.1a), the caller's
    choice: an ability copier can't copy one (Rings of Brighthearth: "if it isn't
    a mana ability"), while a borrowed mana ability is often the best tool."""
    for unit in tree.iter_units("ability"):
        if unit.kind != "Activated" or not _functions_on_battlefield(unit):
            continue
        if not include_mana and getattr(unit.node, "is_mana_ability", None) is True:
            continue
        yield unit


def limits_blockers_to_one(tree: ConceptTree) -> bool:
    """Whether the card says a creature "can't be blocked by more than one
    creature" — on itself (Charging Rhino) or granted (Full Steam Ahead's
    quoted grant). Beside menace ("can't be blocked except by two or more
    creatures", CR 702.111b) no block is legal: the restrictions are cumulative
    (CR 509.1b)."""
    for unit in tree.units:
        for sdef in unit.static_defs():
            if (
                static_mode_tag(sdef) == "CantBeBlockedByMoreThan"
                and static_mode_field(sdef, "max") == 1
            ):
                return True
        for _sdef, mod in iter_mod_sites(unit.node, deep=True):
            if (
                tag_of(mod) == "AddStaticMode"
                and static_mode_tag(mod) == "CantBeBlockedByMoreThan"
                and static_mode_field(mod, "max") == 1
            ):
                return True
    return False


def _is_combat_damage_trigger(trig: object) -> bool:
    """Whether a trigger definition fires on combat damage ("whenever ~ deals
    combat damage"): a ``DamageDone`` event phase marks ``CombatOnly``."""
    return (
        isinstance(trig, TypedMirrorNode)
        and trigger_def_event(trig) == "deals_damage"
        and trigger_damage_kind(trig) == "CombatOnly"
    )


def has_combat_damage_trigger(tree: ConceptTree) -> bool:
    """Whether the card has, or grants (Sword of Fire and Ice's equipped creature
    trigger, a quoted grant), a combat-damage trigger — the trigger double strike
    fires twice, since a double striker deals combat damage in both combat damage
    steps (CR 702.4b)."""
    for unit in tree.units:
        if unit.origin == "trigger" and _is_combat_damage_trigger(unit.node):
            return True
        if any(
            _is_combat_damage_trigger(d) for d in iter_nested_trigger_defs(unit.node)
        ):
            return True
    return False


#: Every name :func:`trigger_kinds` gives (cut-check's ``--trigger-type`` choices).
TRIGGER_KINDS: tuple[str, ...] = (
    "upkeep",
    "attack",
    "combat-damage",
    "death",
    "etb",
    "endstep",
)
#: The step a "beginning of [step]" trigger fires at (:func:`trigger_phase`) → its
#: :func:`trigger_kinds` name.
_STEP_KINDS = {"Upkeep": "upkeep", "End": "endstep"}


def trigger_kinds(unit: AbilityUnit) -> tuple[str, ...]:
    """What a trigger unit fires on, in cut-check's words: an enters trigger
    (CR 603.6a, :data:`ENTERS_EVENTS`) is ``etb``, "enters or attacks" (Sun Titan)
    both ``etb`` and ``attack``; a dies trigger (CR 700.4: put into a graveyard from
    the battlefield) is ``death``; a combat-damage trigger ``combat-damage``; "at
    the beginning of [your / each] upkeep / end step" ``upkeep`` / ``endstep``."""
    event = unit.trigger_event
    out: list[str] = []
    if event in ENTERS_EVENTS:
        out.append("etb")
    if event in ("attacks", "entersorattacks"):
        out.append("attack")
    if event == "dies":
        out.append("death")
    if _is_combat_damage_trigger(unit.node):
        out.append("combat-damage")
    if event == "phase":
        step = _STEP_KINDS.get(trigger_phase(unit.node) or "")
        if step:
            out.append(step)
    return tuple(out)


def has_structural_legend_rule_off(tree: ConceptTree) -> bool:
    """CR 704.5j: a ``LegendRuleDoesntApply`` static mode phase types directly
    (Mirror Gallery, Mirror Box, Sakashima; the Cadric-style bounded forms too)."""
    return tree.has_static_mode("LegendRuleDoesntApply")


def bypasses_legend_rule(tree: ConceptTree) -> bool:
    """Whether the card gets around the legend rule (CR 704.5j) for a copy: a copy
    "except it isn't legendary" (Helm of the Host, Spark Double, Double Major — a
    ``RemoveSupertype`` of Legendary, which becomes part of the copiable values,
    CR 707.9b), or a static saying the legend rule doesn't apply
    (:func:`has_structural_legend_rule_off`)."""
    if has_structural_legend_rule_off(tree):
        return True
    return any(
        tag_of(n) == "RemoveSupertype" and getattr(n, "supertype", None) == "Legendary"
        for n in tree.iter_typed()
    )


def is_every_creature_type(tree: ConceptTree) -> bool:
    """Whether the card is every creature type by its own static ability:
    changeling ("This object is every creature type", CR 702.73a — phase expands
    the keyword to this static) or Mistform Ultimus's printed ability. A
    characteristic-defining ability, so it works in every zone (CR 604.3) — a
    changeling card in a graveyard is an Elf card too. The card itself only: the
    ``has_changeling`` and ``type_changers`` lanes also read grants of every
    creature type to other objects (Maskwood Nexus, Mirror Entity's ability)."""
    for unit in tree.iter_units("static"):
        for sdef, mod in iter_mod_sites(unit.node):
            if (
                tag_of(mod) == "AddAllCreatureTypes"
                and tag_of(getattr(sdef, "affected", None)) == "SelfRef"
            ):
                return True
    return False


# ── Costs you pay ─────────────────────────────────────────────────────────────
# One walk over the costs a unit's controller pays, each leaf with the kind of
# payment it is, shared by ``self_graveyard_fills`` (a discard or mill cost fills
# your graveyard), the discard lanes and ``keyword_resource_events``' energy
# payments. Each caller gates on the kind.

#: How a cost is paid: ``"activation"`` (an activated ability's cost, a granted
#: one's included); ``"additional"`` (a cost of casting a spell — its additional
#: or keyword cost, an alternative cost, or the extra cost of casting it from a
#: graveyard); ``"optional"`` (a "you may pay …" the effect offers: a ``PayCost``
#: effect, a ``MayCost`` replacement); ``"tax"`` (an ``unless_pay`` the effect
#: imposes to keep a permanent or a board: echo, CR 702.30a; cumulative upkeep,
#: CR 702.24a; Masticore's upkeep; "sacrifice it unless you discard a card" on
#: entering).
CostKind = Literal["activation", "additional", "optional", "tax"]
_OPTIONAL_COST_TAGS = frozenset({"PayCost", "MayCost"})


class PaidCost(NamedTuple):
    """One leaf (:func:`iter_cost_leaves`) of a cost the controller pays."""

    leaf: TypedMirrorNode
    how: CostKind


def controller_paid_cost_leaves(unit: AbilityUnit) -> tuple[PaidCost, ...]:
    """Every leaf of a cost the unit's controller pays, with how it is paid
    (:data:`CostKind`): the unit's own activation cost, a granted ability's
    cost, a spell's merged additional and keyword costs (``unit.costs``), a
    graveyard-cast or alternative casting cost, and an ``unless_pay`` /
    ``PayCost`` / ``MayCost`` whose ``payer`` is the controller or unnamed. A
    cost another player pays is skipped: its discard or mill is theirs. A leaf
    two routes reach keeps the first kind found (the unit's own activation cost
    is also among ``unit.costs``)."""
    nodes = tuple(unit.iter_typed())
    taxes = {id(getattr(n, "unless_pay", None)) for n in nodes} - {id(None)}
    out: dict[int, PaidCost] = {}
    # Nodes inside a cost already read: a ``Mana`` cost carries its own
    # ``cost`` field (the mana symbols), which is no second cost.
    inside: set[int] = set()

    def add(cost: object, how: CostKind) -> None:
        inside.update(map(id, iter_typed_nodes(cost)))
        for leaf in iter_cost_leaves(cost):
            out.setdefault(id(leaf), PaidCost(leaf, how))

    for n in nodes:
        if id(n) in inside:
            continue
        cost = getattr(n, "cost", MISSING)
        if not _present(cost) or tag_of(getattr(n, "payer", None)) not in (
            None,
            "Controller",
        ):
            continue
        if id(n) in taxes:
            add(cost, "tax")
        elif tag_of(n) in _OPTIONAL_COST_TAGS:
            add(cost, "optional")
        elif getattr(n, "kind", None) == "Activated":
            add(cost, "activation")
        else:
            add(cost, "additional")
    for c in unit.costs:
        add(c.node, "additional")
    return tuple(out.values())


def is_self_discard_cost(leaf: object, *, random: bool = True) -> bool:
    """Whether a cost leaf discards cards from your hand other than the card
    itself (CR 701.9a: a discarded card moves from its owner's hand to that
    player's graveyard). A ``self_ref`` "Discard this card" is left out: it is
    the card's own keyword cost (cycling, CR 702.29a; channel), read by those
    lanes. ``random=False`` also leaves out a random discard (CR 701.9b), which
    the player can't aim: an outlet or a graveyard fill wants the card you
    choose; a "whenever you discard" payoff fires either way."""
    return (
        tag_of(leaf) == "Discard"
        and not getattr(leaf, "self_ref", False)
        and (random or not discard_is_random(leaf))
    )


# ── keyword action events (one walk: counters, tokens, connive) ──────────────

#: The keyword ACTIONS whose own definition creates a creature token, by phase's
#: effect tag, with the token's subtype as the token-maker lane spells a subject:
#: amass (CR 701.47a, "create a 0/0 black [subtype] Army creature token" when you
#: control no Army; Army is the token's last subtype), endure (701.63a, "creates
#: an N/N white Spirit creature token unless they put N +1/+1 counters on that
#: permanent"), populate (701.36a, a copy of a creature token you control: no
#: subtype of its own). The +1/+1 side is :data:`KEYWORD_ACTION_COUNTER_KINDS`.
KEYWORD_ACTION_TOKEN_SUBTYPES: dict[str, str] = {
    "Amass": "Army",
    "Endure": "Spirit",
    "Populate": "",
}

#: The keyword ABILITIES whose own definition creates a creature token, read
#: where a card grants them: afterlife (CR 702.135a: "create N 1/1 white and
#: black Spirit creature tokens with flying") and mobilize (CR 702.181a: "create
#: N 1/1 red Warrior creature tokens"). phase expands a PRINTED one into its own
#: trigger and Token node (Ministrant of Obligation); a GRANTED one stays the
#: keyword on an ``AddKeyword`` / ``AddDynamicKeyword`` modification.
GRANTED_KEYWORD_TOKEN_SUBTYPES: dict[str, str] = {
    "Afterlife": "Spirit",
    "Mobilize": "Warrior",
}

#: Every keyword-action tag :func:`keyword_action_events` reads.
KEYWORD_ACTION_TAGS: frozenset[str] = frozenset(
    {*KEYWORD_ACTION_COUNTER_KINDS, *KEYWORD_ACTION_TOKEN_SUBTYPES}
)

_UNSET = object()

#: Every attribute a read memoizes on a node or tree beside its fields
#: (:func:`memo_on` and the walks that cache the same way) is named with this
#: prefix: a memo is a pure function of its object, recomputed on demand, so the
#: trees store pickles a tree without them (``_card_ir.tree_store``) — some are
#: keyed by the ``id()`` of the nodes they index, which a loaded copy doesn't share.
MEMO_ATTR_PREFIX = "_xw_"


def memo_on[T](obj: object, attr: str, fn: Callable[[Any], T]) -> T:
    """``fn(obj)``, computed once and kept on ``obj`` under ``attr`` (set through
    ``object.__setattr__``, so a frozen tree or node takes it too). A re-seeded
    tree is a new object, so a memo never goes stale. THE per-tree cache: a
    lane walk that several readers share keeps its result here."""
    if not attr.startswith(MEMO_ATTR_PREFIX):
        msg = f"memo attribute {attr!r} must start with {MEMO_ATTR_PREFIX!r}"
        raise ValueError(msg)
    cached = obj.__dict__.get(attr, _UNSET)
    if cached is _UNSET:
        cached = fn(obj)
        object.__setattr__(obj, attr, cached)
    return cached


class KeywordActionEvent(NamedTuple):
    """One keyword-action node on a card."""

    tag: str
    unit: AbilityUnit
    #: In the unit's own effect chain; ``False`` inside an ability it grants.
    own: bool
    #: :func:`effect_actor_scope`: the player who really performs the action
    #: when phase names them outside the node (``"opponents"`` for "each
    #: opponent amasses"), else ``None`` — the unit's controller.
    actor_scope: str | None

    @property
    def yours(self) -> bool:
        """Whether the unit's controller (or a player they choose) performs it."""
        return self.actor_scope != "opponents"


def keyword_action_events(tree: ConceptTree) -> tuple[KeywordActionEvent, ...]:
    """Every keyword action on the card (:data:`KEYWORD_ACTION_TAGS`), one event
    per node, in walk order; granted abilities included. Memoized on the tree.
    The counter, token and connive reads are projections of it."""
    return memo_on(tree, "_xw_keyword_action_events", _keyword_action_events)


def _keyword_action_events(tree: ConceptTree) -> tuple[KeywordActionEvent, ...]:
    typed = tree.has_typed(*KEYWORD_ACTION_TAGS)
    out: list[KeywordActionEvent] = []
    for unit in tree.units:
        own = {id(c.node) for c in unit.effects}
        for n in unit.iter_typed() if typed else ():
            tag = tag_of(n) or ""
            if tag in KEYWORD_ACTION_TAGS:
                out.append(
                    KeywordActionEvent(
                        tag, unit, id(n) in own, effect_actor_scope(unit, n)
                    )
                )
        out.extend(
            KeywordActionEvent(
                tag, unit, own=True, actor_scope=effect_actor_scope(unit, c.node)
            )
            for c, (tag,) in _recovered_reads(unit, "action")
        )
    return tuple(out)


def keyword_token_creations(
    tree: ConceptTree, *, granted: bool = False
) -> tuple[tuple[str, str], ...]:
    """``(keyword, token subtype)`` per keyword action you perform that creates
    a creature token (:data:`KEYWORD_ACTION_TOKEN_SUBTYPES`). ``granted`` adds
    each token-making keyword ability the card grants to a permanent that isn't
    an opponent's (:data:`GRANTED_KEYWORD_TOKEN_SUBTYPES` — Afterlife
    Insurance's "Creatures you control gain afterlife 1", Infantry Shield's
    "Equipped creature has … mobilize X"); the token goes to that permanent's
    controller (CR 111.2). A grant is read wherever it sits (a spell's one-shot
    ``GenericEffect`` static, a static, a granted body)."""
    out = [
        (e.tag, KEYWORD_ACTION_TOKEN_SUBTYPES[e.tag])
        for e in keyword_action_events(tree)
        if e.tag in KEYWORD_ACTION_TOKEN_SUBTYPES and e.yours
    ]
    if granted:
        for name in yours_granted_keywords(tree):
            subtype = GRANTED_KEYWORD_TOKEN_SUBTYPES.get(name)
            if subtype is not None:
                out.append((name, subtype))
    return tuple(out)


def yours_granted_keywords(tree: ConceptTree) -> Iterator[str]:
    """The name of each keyword the card grants to a permanent or card that isn't
    an opponent's, in phase's spelling (``"Mobilize"``, ``"Encore"``), one per
    ``AddKeyword`` / ``AddDynamicKeyword`` modification, wherever it sits (a
    spell's one-shot ``GenericEffect`` static, a static, a granted body)."""
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node, deep=True):
            tag = tag_of(mod)
            if tag == "AddKeyword":
                name = mod_keyword_name(mod) or ""
            elif tag == "AddDynamicKeyword":
                name = getattr(mod, "kind", None) or ""
            else:
                continue
            if (
                name
                and filter_controller(getattr(sdef, "affected", None)) != "Opponent"
            ):
                yield name


# ── end keyword action events ────────────────────────────────────────────────


# ── end-step sacrifices and ending the turn (CR 603.7, 724.1) ────────────────

#: The keyword abilities whose definition sets up a one-shot "at the beginning of
#: the next end step" sacrifice or exile of what the keyword puts onto the
#: battlefield (normalised, :func:`normalised_keyword_name`): mobilize (CR
#: 702.181a), encore (702.141a), blitz (702.152a), unearth (702.84a). phase
#: expands a printed mobilize or unearth into its own delayed trigger; a granted
#: one, an encore and a blitz stay the keyword. Dash returns its permanent to
#: hand (702.109a) and myriad exiles its tokens at end of combat (702.116a):
#: neither is one.
END_STEP_SACRIFICE_KEYWORDS = frozenset({"mobilize", "encore", "blitz", "unearth"})


def _end_step_sacrifice_node(node: object) -> bool:
    """A ``CreateDelayedTrigger`` that fires at the beginning of the next end step
    (``AtNextPhase`` ``End``) and sacrifices or exiles a permanent, its own
    controller doing it: Saheeli, Radiant Creator's and Kiki-Jiki's token copies,
    Sneak Attack's creature, an unearthed card."""
    if tag_of(node) != "CreateDelayedTrigger":
        return False
    cond = getattr(node, "condition", None)
    if tag_of(cond) != "AtNextPhase" or getattr(cond, "phase", None) != "End":
        return False
    ability = getattr(node, "effect", None)
    if tag_of(getattr(ability, "player_scope", None)) in ("Opponent", "All"):
        return False
    for n in iter_typed_nodes(ability):
        tag = tag_of(n)
        if tag == "Sacrifice" or (
            tag == "ChangeZone"
            and getattr(n, "origin", None) == "Battlefield"
            and getattr(n, "destination", None) == "Exile"
        ):
            return True
    return False


def end_step_sacrifices(tree: ConceptTree) -> bool:
    """Whether the card makes or returns permanents of yours that a one-shot
    delayed trigger sacrifices or exiles at the beginning of the next end step
    (CR 603.7: an effect creates it; 603.7b: it triggers only once): its own
    delayed trigger (:func:`_end_step_sacrifice_node`), or a printed or granted
    keyword whose definition holds one (:data:`END_STEP_SACRIFICE_KEYWORDS` —
    Sliver Gravemother's encore, Infantry Shield's mobilize). Ending the turn
    while that trigger waits on the stack exiles it (CR 724.1b) and the
    permanent stays (Sundial of the Infinite). A trigger printed on the
    permanent ("At the beginning of the end step, sacrifice ~" — Ball
    Lightning) fires again every turn, so it is not one. Memoized on the tree."""
    return memo_on(tree, "_xw_end_step_sacrifices", _end_step_sacrifices)


def _end_step_sacrifices(tree: ConceptTree) -> bool:
    if any(
        normalised_keyword_name(k) in END_STEP_SACRIFICE_KEYWORDS
        for k in tree.card_keywords
    ):
        return True
    if tree.has_typed("CreateDelayedTrigger") and any(
        _end_step_sacrifice_node(n) for n in tree.iter_typed()
    ):
        return True
    return any(
        normalised_keyword_name(k) in END_STEP_SACRIFICE_KEYWORDS
        for k in yours_granted_keywords(tree)
    )


def instant_end_turn_unit(
    tree: ConceptTree, *, repeatable: bool = False
) -> AbilityUnit | None:
    """The ability that lets the card end the turn (CR 724.1) while an ability
    waits on the stack, or ``None``: an ``end_the_turn`` effect in an activated
    ability that isn't sorcery-timed (CR 117.1b, 602.5d — Sundial of the
    Infinite) or in an instant or flash spell (CR 117.1a, 702.8a — Time Stop). A
    sorcery (Day's Undoing) can only be cast with the stack empty (CR 307.1).
    ``repeatable`` keeps the activated abilities only, usable again each turn: a
    spell is gone once it resolves (CR 608.2n) or the turn it ends exiles it (CR
    724.1b). An activation limited to your own turn (Sundial's "Activate only
    during your turn") still counts: the end step it acts in is yours, where your
    own next-end-step triggers wait — on the stack (exiled, CR 724.1b) or not yet
    put there (they cease to exist, 724.1a)."""
    for unit in tree.units:
        if not any(c.concept == "end_the_turn" for c in unit.effects):
            continue
        if unit.kind == "Activated":
            restrictions = getattr(unit.node, "activation_restrictions", None)
            if not isinstance(restrictions, list) or not any(
                tag_of(r) == "AsSorcery" for r in restrictions
            ):
                return unit
        elif (
            not repeatable
            and unit.kind == "Spell"
            and (
                tree.is_type("Instant")
                or "flash" in {normalised_keyword_name(k) for k in tree.card_keywords}
            )
        ):
            return unit
    return None


def ends_turn_at_instant_speed(tree: ConceptTree, *, repeatable: bool = False) -> bool:
    """Whether the card has an :func:`instant_end_turn_unit`."""
    return instant_end_turn_unit(tree, repeatable=repeatable) is not None


# ── keyword_resource_events (the energy / venture / foretell serve slice) ──────


class ResourceEvent(NamedTuple):
    """One place a card makes or uses a keyword resource
    (:func:`keyword_resource_events`): ``resource`` is ``"energy"``,
    ``"venture"`` or ``"foretell"``; ``side`` is ``"makers"`` or ``"matters"``.
    ``unit`` is the unit it sits in (``None`` for a printed keyword); the
    energy lane reads it to skip a payment that buys only mana."""

    resource: str
    side: str
    unit: AbilityUnit | None


#: Node tags that make or use a resource, wherever they sit under a unit (a
#: granted ability's included). ``GainEnergy`` gets you {E};
#: ``ExileWithEnergyCost`` lets you cast a card by paying {E} (Amped Raptor) —
#: CR 107.14: to pay {E}, a player removes one energy counter from themselves.
#: ``VentureIntoDungeon`` (CR 701.49a) and ``TakeTheInitiative`` (CR 726.2: taking
#: the initiative makes that player venture into Undercity) move a venture marker.
#: ``Foretold`` is the filter property naming foretold cards (CR 702.143c —
#: Niko Defies Destiny, Alrund).
_RESOURCE_NODE_TAGS: dict[str, tuple[str, str]] = {
    "GainEnergy": ("energy", "makers"),
    "ExileWithEnergyCost": ("energy", "matters"),
    "VentureIntoDungeon": ("venture", "makers"),
    "TakeTheInitiative": ("venture", "makers"),
    "Foretold": ("foretell", "matters"),
}
#: Trigger modes that watch a resource event of the trigger's controller (a
#: ``Controller`` ``valid_target``). ``DungeonCompleted``: "whenever you complete a
#: dungeon" (CR 309.7).
_RESOURCE_TRIGGER_MODES: dict[str, tuple[str, str]] = {
    "DungeonCompleted": ("venture", "matters"),
}
#: The counter kinds a ``CounterPlayerAddedAll`` trigger ("whenever you get one
#: or more {E}" — Territorial Gorger) watches that are a resource. Phase drops the
#: kind from the trigger; the overlay's ``player_counter_kind`` arm re-reads it
#: off the trigger's clause (CR 107.14: {E} is an energy counter).
_PLAYER_COUNTER_RESOURCES: dict[str, tuple[str, str]] = {
    "energy": ("energy", "matters"),
}
#: Condition tags a venture payoff is gated on: "if you've completed a dungeon"
#: (Gloom Stalker), "if you completed <a named dungeon>" (Acererak), "if you have
#: the initiative" (Passageway Seer).
_VENTURE_CONDITION_TAGS: frozenset[str] = frozenset(
    {"CompletedADungeon", "CompletedDungeon", "IsInitiative"}
)

_RESOURCE_EVENTS_CACHE_ATTR = "_xw_keyword_resource_events"


def keyword_resource_events(tree: ConceptTree) -> tuple[ResourceEvent, ...]:
    """Every place the card makes or uses energy, the dungeon or foretell: the
    node tags, trigger modes and conditions in the tables above, a
    room-ability doubler (a ``DoubleTriggers`` caused by entering a room —
    Hama Pashar; CR 309.4c), the printed foretell keyword (CR 702.143a) or a
    grant of it (Bohn, Beguiling Balladeer), and a ``PayEnergy`` leaf of a cost
    the controller pays (:func:`controller_paid_cost_leaves`, ``unless_pay``
    included: a deck must hold energy to pay Lathnu Hellion's or Rush of
    Inspiration's "unless you pay {E}{E}", so the card wants energy makers).
    The caller decides what a payment buys. Memoized on the tree."""
    return memo_on(tree, _RESOURCE_EVENTS_CACHE_ATTR, _keyword_resource_events)


def _keyword_resource_events(tree: ConceptTree) -> tuple[ResourceEvent, ...]:
    out: list[ResourceEvent] = []
    if any(normalised_keyword_name(kw) == "foretell" for kw in tree.card_keywords):
        out.append(ResourceEvent("foretell", "makers", None))
    for unit in tree.units:
        out.extend(
            ResourceEvent(resource, side, unit)
            for _c, (resource, side) in _recovered_reads(unit, "resource")
        )
        for n in unit.iter_typed():
            tag = tag_of(n) or ""
            if tag in _RESOURCE_NODE_TAGS:
                out.append(ResourceEvent(*_RESOURCE_NODE_TAGS[tag], unit))
            elif tag == "AddKeyword" and mod_keyword_name(n) == "Foretell":
                out.append(ResourceEvent("foretell", "makers", unit))
            mode = getattr(n, "mode", None)
            if (
                isinstance(mode, str)
                and tag_of(getattr(n, "valid_target", None)) == "Controller"
            ):
                kind = unit.corrected(n, "counter_kind")
                if mode in _RESOURCE_TRIGGER_MODES:
                    out.append(ResourceEvent(*_RESOURCE_TRIGGER_MODES[mode], unit))
                elif (
                    mode == "CounterPlayerAddedAll"
                    and isinstance(kind, str)
                    and kind in _PLAYER_COUNTER_RESOURCES
                ):
                    out.append(ResourceEvent(*_PLAYER_COUNTER_RESOURCES[kind], unit))
            cause = double_triggers_cause(n)
            if cause is not None and cause[0] == "RoomEntered":
                out.append(ResourceEvent("venture", "matters", unit))
        if any(
            tag_of(leaf) == "PayEnergy"
            for leaf, _how in controller_paid_cost_leaves(unit)
        ):
            out.append(ResourceEvent("energy", "matters", unit))
        if _VENTURE_CONDITION_TAGS.intersection(
            _walk_unit_conditions(unit.node, 0, set())
        ):
            out.append(ResourceEvent("venture", "matters", unit))
    return tuple(out)


# ── end keyword_resource_events ──────────────────────────────────────────────


# ── answers_its_target / controller_side ────────────────────────────────────


def answers_its_target(node: TypedMirrorNode) -> bool:
    """Whether effect ``node`` answers the object its filter names: counters it
    (CR 701.6a — cancels it, removing it from the stack), destroys it (CR
    701.8a), or exiles it (a ``ChangeZone`` / ``ChangeZoneAll`` whose
    destination is Exile — :func:`change_zone_dirs`).

    The filter on such an effect describes what the card removes, not what it
    rewards: "Counter target colorless spell" (Ceremonious Rejection) is
    colorless hate, and "exile target player's graveyard" (Bojuka Bog) is
    graveyard hate. A lane that reads a filter as a build-around asks this
    first, and reads the filter's controller for the exception (exiling your
    own permanent is a blink, not an answer)."""
    tag = tag_of(node)
    if tag in ("Counter", "Destroy", "DestroyAll"):
        return True
    if tag in ("ChangeZone", "ChangeZoneAll"):
        return change_zone_dirs(node)[1] == "Exile"
    return False


ControllerSide = Literal["you", "opponents", "chosen"]

#: The controller / owner tags naming the opponents' side: the opponent actor
#: tags, a target opponent, and the players :data:`_CHOOSER_ACTORS` reads as an
#: opponent (a defending player, CR 506.2).
_OPPONENT_SIDE_TAGS: frozenset[str] = (
    OPPONENT_ACTOR_TAGS
    | {"TargetOpponent"}
    | {tag for tag, side in _CHOOSER_ACTORS.items() if side == "Opponent"}
)
#: The tags naming a player the card picks out, who may be you or an opponent:
#: a target player, a chosen player (now, or as the source entered), a
#: target's controller or owner.
_CHOSEN_SIDE_TAGS: frozenset[str] = frozenset(
    {"TargetPlayer", "SourceChosenPlayer"}
) | {tag for tag, side in _CHOOSER_ACTORS.items() if side == CHOSEN_PLAYER_SCOPE}


def controller_side(tag: str | None) -> ControllerSide | None:
    """The side a controller or owner tag names: ``"you"``, ``"opponents"``
    (an opponent, each opponent, a target opponent, the defending player), or
    ``"chosen"`` (a target / chosen player, a target's controller or owner —
    either side). ``None`` for no tag, or one this read can't place (``Any``,
    ``ScopedPlayer``, a triggering player)."""
    if tag == "You":
        return "you"
    if tag in _OPPONENT_SIDE_TAGS:
        return "opponents"
    if tag in _CHOSEN_SIDE_TAGS:
        return "chosen"
    return None


def filter_controller_side(filt: object) -> ControllerSide | None:
    """:func:`controller_side` of a filter's controller
    (:func:`filter_controller`) — the one read for "is this filter an
    opponent's?", so a ``DefendingPlayer`` filter never reads as yours."""
    return controller_side(filter_controller(filt))


def triggering_player_side(unit: AbilityUnit) -> ControllerSide | None:
    """The side of a trigger's "that player" (phase's ``TriggeringPlayer``):
    the player the trigger watches, read off its ``valid_target``
    (:func:`trigger_scope`). "Whenever an opponent loses life, that player
    mills that many cards" (Mindcrank) and "Whenever an opponent casts a
    spell, that player creates a Blood token" (Bloodvial Purveyor) name an
    opponent; ``None`` when the unit isn't a trigger that names its player."""
    if unit.origin != "trigger" or not _present(
        getattr(unit.node, "valid_target", MISSING)
    ):
        return None
    scope = trigger_scope(unit.node)
    return scope if scope in ("you", "opponents") else None


# ── end answers_its_target / controller_side ─────────────────────────────────


# ── Tappers, tap triggers and P/T shrinks (the tapper_engine /
# ── tap_untap_matters / debuff_makers serve-ident pass) ─────────────────────

#: The target shapes of a ``SetTapState`` that name an object to tap (a filter
#: the controller chooses from), as opposed to a ``SelfRef`` self-tap or a
#: back-reference to an object an earlier clause chose.
_TAP_OBJECT_TARGET_TAGS: frozenset[str] = OBJECT_FILTER_TAGS


def taps_target_object(node: object) -> bool:
    """Whether ``node`` taps a permanent its controller picks: a ``SetTapState``
    whose state is ``Tap`` and whose target is an object filter (CR 701.26a: to
    tap a permanent is to turn it sideways). A self-tap (``SelfRef``) and an
    untap never count. A filter phase stamps ``controller: You`` still counts
    here: phase writes "tap target creature that player controls" (Delirium;
    Yosei, the Morning Star) that way too, and the overlay's
    ``tap_other_player`` correction (``AbilityUnit.corrected``) is what tells
    the two apart."""
    return (
        isinstance(node, TypedMirrorNode)
        and tag_of(node) == "SetTapState"
        and settap_state(node) == "Tap"
        and tag_of(getattr(node, "target", None)) in _TAP_OBJECT_TARGET_TAGS
    )


def granted_target_taps(node: object) -> tuple[TypedMirrorNode, ...]:
    """The :func:`taps_target_object` effects inside the abilities and triggers
    an ability under ``node`` grants (:func:`iter_nested_granted_bodies`, CR
    113.1a): an Equipment's "Equipped creature has '{2}, {T}: Tap target
    creature'" (Siren Song Lyre), a lord's "All Slivers have '{T}: Tap target
    permanent'" (Telekinetic Sliver), a token's own granted ability (Goldmeadow
    Lookout's Goldmeadow Harrier), a granted attack trigger (Web-Shooters)."""
    return tuple(
        n
        for _kind, body in iter_nested_granted_bodies(node)
        for n in _iter_typed_nodes(body)
        if taps_target_object(n)
    )


def granted_trigger_events(node: object) -> frozenset[str]:
    """The trigger events (:func:`trigger_def_event`'s spelling — ``"taps"``,
    ``"untaps"``, ``"attacks"`` …) of every trigger an ability under ``node``
    grants (:func:`iter_nested_trigger_defs`): "Elves you control have
    'Whenever this creature becomes tapped …'" (Dionus, Elvish Archdruid), an
    Aura's "Enchanted creature has 'Whenever this creature becomes untapped …'"
    (Well Rested), a token's granted trigger (Wildfire Awakener's Elementals),
    an emblem's (Tezzeret, Betrayer of Flesh). A top-level trigger unit's own
    event is :attr:`AbilityUnit.trigger_event`."""
    return frozenset(trigger_def_event(trig) for trig in iter_nested_trigger_defs(node))


#: The continuous P/T modifications (CR 613.4c, layer 7c) by the stat each
#: changes: a plain-int ``value`` (Clinging Darkness's -4/-1), or a dynamic
#: quantity (Kagemaro's Clutch's "-X/-X, where X is …").
_PT_MOD_FIELDS: dict[str, str] = {
    "AddPower": "power",
    "AddToughness": "toughness",
    "AddDynamicPower": "power",
    "AddDynamicToughness": "toughness",
}


def _pt_mod_sign(mod: object) -> int:
    value = getattr(mod, "value", MISSING)
    if isinstance(value, int):
        return (value > 0) - (value < 0)
    if tag_of(value) == "Multiply":
        factor = getattr(value, "factor", None)
        if isinstance(factor, int) and factor < 0:
            return -1
    # A dynamic quantity phase doesn't negate is a count: a raise.
    return 1 if _present(value) else 0


def pt_mod_signs(static_def: object) -> tuple[int, int]:
    """The direction of a continuous effect's P/T modifications (CR 613.4c,
    layer 7c) as ``(power, toughness)``: ``-1`` lowers the stat, ``1`` raises
    it, ``0`` leaves it (or the effect both raises and lowers it). Reads the
    plain-int ``AddPower`` / ``AddToughness`` mods and their dynamic forms, which
    phase writes negative as a ``Multiply`` with a negative ``factor``
    ("Creatures you don't control get -1/-1 for each slime counter on them" —
    Toxrill, the Corrosive; "All creatures get -X/-0, where X is …" — Meishin,
    the Mind Cage)."""
    signs: dict[str, set[int]] = {"power": set(), "toughness": set()}
    for mod in getattr(static_def, "modifications", None) or ():
        stat = _PT_MOD_FIELDS.get(tag_of(mod) or "")
        if stat is not None:
            signs[stat].add(_pt_mod_sign(mod))

    def net(found: set[int]) -> int:
        found = found - {0}
        return next(iter(found)) if len(found) == 1 else 0

    return net(signs["power"]), net(signs["toughness"])


# ── Granted alternative costs, time-counter references, modified permanents ──


def granted_alt_cost_kinds(unit: AbilityUnit) -> tuple[str, ...]:
    """The alternative-cost keywords one unit GRANTS, by
    :data:`~mtg_utils._card_ir.crosswalk.cost_text.ALT_COST_KEYWORDS` kind
    (``"sneak"``, ``"mayhem"``, ``"web-slinging"``, ``"flashback"`` …): an
    ``AddKeyword`` modification anywhere under the unit (Ninja Teen's "Creature
    cards in your graveyard have sneak {3}{B}", Green Goblin's "Each nonland card
    in your graveyard has mayhem") and a ``CastWithKeyword`` static ("Each
    legendary spell you cast … has web-slinging {G}{W}{U}" — Amazing
    Spider-Man). The printed keyword is :attr:`ConceptTree.card_alt_costs`'
    read; this is the grant of one, which phase keeps on the granting node."""
    from mtg_utils._card_ir.crosswalk.cost_text import ALT_COST_KEYWORDS

    out: list[str] = []
    for n in unit.iter_typed():
        if tag_of(n) == "AddKeyword":
            row = ALT_COST_KEYWORDS.get(mod_keyword_name(n) or "")
            if row is not None:
                out.append(row[0])
    for sdef in unit.static_defs():
        row = ALT_COST_KEYWORDS.get(cast_with_keyword_name(sdef) or "")
        if row is not None:
            out.append(row[0])
    return tuple(out)


def time_counter_kind_refs(root: object) -> tuple[str, ...]:
    """Every "time" counter reference reachable anywhere under ``root`` — the
    :func:`oil_counter_kind_refs` sibling for time counters: a filter naming a
    permanent with a time counter, or a suspended card (CR 702.62b: a card is
    suspended if it's in exile, has suspend and has a time counter on it —
    Clockspinning's "target permanent or suspended card"), or a ``HasCounters``
    condition on one. See :func:`_counter_kind_refs` for the shapes."""
    return _counter_kind_refs(root, "time")


def references_modified(unit: AbilityUnit) -> bool:
    """Whether one unit cares about modified permanents of yours (CR 700.9: a
    permanent is modified if it has a counter on it, is equipped, or is enchanted
    by an Aura its controller controls), read off phase's ``Modified`` filter
    predicate: on a filter you control at any depth, on the card's own condition
    ("as long as it's modified" — Skyward Spider), or on a continuous effect's
    unscoped affected set (Iron Man's "other attacking modified creatures"). An
    opponent's filter, or an unscoped effect target ("destroy target modified
    creature"), is not a payoff of your own modified creatures."""
    for n in unit.iter_typed():
        if (
            tag_of(n) == "Typed"
            and filter_controller(n) == "You"
            and "Modified" in filter_predicates(n)
        ):
            return True
    for site in iter_condition_sites(unit.node):
        for n in iter_typed_nodes(site):
            if (
                tag_of(n) == "Typed"
                and filter_controller_side(n) != "opponents"
                and "Modified" in filter_predicates(n)
            ):
                return True
    for sdef in unit.static_defs():
        aff = getattr(sdef, "affected", None)
        if filter_controller(aff) in (None, "You") and "Modified" in filter_predicates(
            aff
        ):
            return True
    return False


# ── CR 110.2: a permanent seated from an opponent's library ──────────────────
#: Library-access effects whose player field can name an opponent: a search
#: (``SearchLibrary.target_player`` — Bribery) and a reveal-until
#: (``RevealUntil.player`` — Telemin Performance).
_LIBRARY_ACCESS_PLAYER_FIELDS: dict[str, str] = {
    "SearchLibrary": "target_player",
    "RevealUntil": "player",
}


def seats_opponent_library_card(unit: AbilityUnit) -> bool:
    """Whether ``unit`` takes a card from an OPPONENT's library and puts it onto
    the battlefield under YOUR control — Bribery, Acquire, Inevitable Betrayal,
    Eternal Dominion, Dichotomancy (a search of that player's library), Telemin
    Performance (they reveal until a creature). You control a permanent you
    don't own (CR 110.2: a permanent's controller is, by default, the player
    under whose control it entered the battlefield; Bribery's ruling: "You put
    the creature onto the battlefield, so you control it").

    Two typed facts in the same ability: a library access whose player is a
    ``Typed`` opponent filter, and a ``ChangeZone`` / ``ChangeZoneAll`` onto
    the battlefield with ``enters_under: You``. A reanimation from any
    graveyard (Animate Dead) is not one: no opponent's library is accessed.
    """
    nodes = _typed_nodes(unit.node)

    def opponents_library(n: TypedMirrorNode) -> bool:
        field = _LIBRARY_ACCESS_PLAYER_FIELDS.get(tag_of(n) or "")
        ply = getattr(n, field, None) if field else None
        # Never a target player: "target player's library" may be your own.
        return tag_of(ply) == "Typed" and filter_controller_side(ply) == "opponents"

    return any(opponents_library(n) for n in nodes) and any(
        tag_of(n) in ("ChangeZone", "ChangeZoneAll")
        and getattr(n, "destination", None) == "Battlefield"
        and enters_under_you(n)
        for n in nodes
    )


def animates(static_def: object, root: object, *, retype: bool = True) -> bool:
    """Whether a continuous effect makes its objects creatures (CR 613.1d, layer
    4: type-changing effects): an ``AddType{core_type: Creature}`` over objects
    that aren't creatures already — "All Forests are 1/1 creatures that are
    still lands" (Living Lands), "Target snow land you control becomes a 4/4
    Elemental creature with hexproof and haste" (Avalanche Caller). Adding the
    Creature type to a creature ("target creature becomes a white Rabbit with
    base power and toughness 0/1" — Metamorphic Blast; Secret Identity's
    Citizen) animates nothing.

    With ``retype`` (the default) a ``SetCardTypes`` naming Creature counts
    whatever it applies to: the effect rewrites the object's card types
    outright (Darksteel Mutation's "is an Insect artifact creature"; Turn to
    Frog's "becomes a blue Frog"). A read that cares only whether a
    noncreature became a creature passes ``retype=False``.

    The objects are the def's ``affected`` filter, or — for a back-reference
    (``ParentTarget`` / ``TrackedSet``) — the target threaded through ``root``'s
    effect chain (:func:`iter_threaded_target_statics`); ``root`` is the unit
    node holding the def."""
    mods = getattr(static_def, "modifications", None) or ()
    if retype and any(
        tag_of(mod) == "SetCardTypes"
        and "Creature" in (getattr(mod, "core_types", None) or ())
        for mod in mods
    ):
        return True
    if not any(
        tag_of(mod) == "AddType" and getattr(mod, "core_type", None) == "Creature"
        for mod in mods
    ):
        return False
    objects = getattr(static_def, "affected", None)
    back_ref = tag_of(objects)
    if back_ref in ("ParentTarget", "TrackedSet"):
        objects = next(
            (
                target
                for target, st in iter_threaded_target_statics(
                    root,
                    affected_tag=back_ref,
                    resets_thread=(
                        ends_target_thread if back_ref == "TrackedSet" else None
                    ),
                )
                if st is static_def
            ),
            objects,
        )
    return "Creature" not in filter_core_types(objects)


def static_pt_mods_on_others(
    unit: AbilityUnit,
) -> Iterator[tuple[TypedMirrorNode, object, tuple[int, int]]]:
    """``(static def, its affected filter, (power, toughness) signs)`` for each
    continuous P/T modification (CR 613.4c, layer 7c) the unit applies to
    creatures other than the card itself and not only yours (:func:`pt_mod_signs`
    gives the signs). An animation is skipped: the P/T it sets is the new
    creature's (CR 613.1d, 613.4b), never a shrink of one. The debuff walks start
    here — ``debuff_makers``' static arm, and the board-wipe role's population
    shrink, which further drops one object (an Equipment's or Aura's creature, a
    spell's target)."""
    for sdef in iter_static_defs(unit.node):
        if not animates(sdef, unit.node, retype=False) and static_on_others(sdef, unit):
            yield sdef, static_affected(sdef, unit), pt_mod_signs(sdef)


def static_on_others(sdef: object, unit: AbilityUnit) -> bool:
    """Whether a static def applies to objects other than the card itself and not
    only yours — :func:`static_pt_mods_on_others`' gate, for a walk over the
    unit's static defs that reads more than their P/T (``debuff_makers``)."""
    return (
        affected_tag(sdef, unit) != "SelfRef"
        and filter_controller(static_affected(sdef, unit), unit) != "You"
    )


def _overloaded(tree: ConceptTree) -> bool:
    """The card has overload (CR 702.96a): paying it changes every "target" in
    the spell's text to "each". phase v0.104.0 keeps overload as an alternative
    cost (``card_alt_costs``) and types only the targeted base mode — the
    overloaded sweep is the base mode's own effect on every object matching its
    description, legal target or not (CR 702.96b). Retires when phase types the
    overloaded mode (``retirement_canary``:
    ``test_overload_sweep_is_read_from_the_base_mode``)."""
    return any(alt.kind == "overload" for alt in tree.card_alt_costs)


#: The six permanent types (CR 110.4); a "permanent card" is a card of one
#: (CR 110.4a).
PERMANENT_CARD_TYPES: frozenset[str] = frozenset(
    {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
)
#: The permanent types a destroy or exile sweep reads as clearing — a sweep
#: affects every object it describes without targeting one (CR 115.10). Leaving
#: lands out is the lanes' own decision: a land sweep is land destruction, a
#: different job.
SWEPT_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker"}
)
#: The core types a damage, bounce or shrink effect reaches creatures through:
#: "creature", or "permanent", which includes them.
CREATURE_OR_PERMANENT: frozenset[str] = frozenset({"Creature", "Permanent"})


def overload_sweep(tree: ConceptTree, unit: AbilityUnit, c: ConceptNode) -> str | None:
    """The sweep an overloaded spell's targeted effect becomes (CR 702.96a-b:
    "target" reads "each", legal target or not) — ``"destroy"`` (Damn),
    ``"exile"`` (Winds of Abandon), ``"damage"`` (Mizzium Mortars), ``"bounce"``
    (Cyclonic Rift) or ``"shrink"`` (a negative-toughness pump, CR 704.5f) —
    or ``None``: the card has no overload (:func:`_overloaded`), ``c`` isn't the
    spell's own, it reaches only your permanents, or it is no removal (a
    "+1/+0" pump, an exile from a graveyard). THE one read of "overload makes
    this a sweep": the ``mass_removal`` / ``mass_bounce`` lanes, the mass-death
    read and the board-wipe job read all ask it."""
    if unit.kind != "Spell" or not _overloaded(tree):
        return None
    sub = effect_filter(c.node)
    if filter_controller(sub) == "You":
        return None
    cores = set(filter_core_types(sub))
    tag = tag_of(c.node)
    if tag == "Destroy" and cores & SWEPT_PERMANENT_TYPES:
        return "destroy"
    if tag == "DealDamage" and cores & CREATURE_OR_PERMANENT:
        return "damage"
    if tag == "Bounce" and cores & CREATURE_OR_PERMANENT:
        return "bounce"
    if tag == "Pump" and "Creature" in cores and negative_pt_field(c.node, "toughness"):
        return "shrink"
    if tag == "ChangeZone":
        origin, dest = change_zone_dirs(c.node)
        if origin in ("Graveyard", "Hand"):
            return None
        if dest == "Exile" and cores & SWEPT_PERMANENT_TYPES:
            return "exile"
        if dest == "Hand" and cores & CREATURE_OR_PERMANENT:
            return "bounce"
    return None


# ── resource-token serve slice (Treasure / Food / Clue / Blood) ──────────────


def replacement_added_token_subtypes(node: TypedMirrorNode) -> tuple[str, ...]:
    """The subtypes of the tokens a ``CreateToken`` replacement creates on top of
    (or in place of) the replaced creation, read off its token specs: an
    ``additional_token_spec`` ("instead create those tokens plus an additional
    Food token" — Tippy-Toe, Terrific Partner; Bilbo, Fellow Conspirator's
    Treasure; Xorn's extra Treasure) and each ``ensure_token_specs`` entry
    ("instead create one of each" — Academy Manufactor's Clue, Food and
    Treasure). Empty for a replacement that only multiplies (Doubling Season)
    or swaps in copies. Pair with :func:`replacement_token_types` to tell a
    replacement that creates a kind it doesn't watch (a maker of that kind)
    from one that adds to the kind it watches (a payoff)."""
    out: list[str] = []
    for chars in replacement_token_specs(node):
        for st in getattr(chars, "subtypes", None) or ():
            if isinstance(st, str) and st not in out:
                out.append(st)
    return tuple(out)


def replacement_token_specs(node: object) -> Iterator[object]:
    """The ``characteristics`` of each token a ``CreateToken`` replacement
    creates beside or instead of the replaced creation: its
    ``additional_token_spec`` and each ``ensure_token_specs`` entry
    (:func:`replacement_added_token_subtypes`)."""
    for field in ("additional_token_spec", "ensure_token_specs"):
        specs = getattr(node, field, MISSING)
        if not _present(specs):
            continue
        for spec in specs if isinstance(specs, list) else (specs,):
            yield getattr(spec, "characteristics", None)


def forages(unit: AbilityUnit) -> bool:
    """Whether ``unit`` forages or watches you forage — the two forage shapes
    with no ``Sacrifice`` of a Food for a Food read to see. CR 701.61a: to
    forage means "Exile three cards from your graveyard or sacrifice a Food."

    * a ``Forage`` action anywhere under the unit, a granted ability's
      included ("At the beginning of combat on your turn, you may forage" —
      Corpseberry Cultivator);
    * a ``PlayerPerformedAction`` trigger watching ``Forage`` by its
      controller ("Whenever you forage, …").

    phase writes most forage costs and "you may forage. If you do" riders as a
    ``PayCost{OneOf[Exile three from your graveyard, Sacrifice a Food]}``
    (Treetop Sentries); that shape is a Food sacrifice the caller's sacrifice
    read already sees, so it is not repeated here."""
    for n in unit.iter_typed():
        if tag_of(n) == "Forage":
            return True
    node = unit.node
    actions = getattr(node, "player_actions", MISSING)
    return (
        unit.origin == "trigger"
        and isinstance(actions, list)
        and "Forage" in actions
        and tag_of(getattr(node, "valid_target", None)) in (None, "Controller")
    )


# ── end resource-token serve slice ───────────────────────────────────────────


# ── Token creators, damage drains and life lost this turn ──

#: The target tags a chain's root-target walk (:func:`root_target_filter`)
#: skips: back-references to an earlier object (``ParentTarget``, a tracked
#: set, the triggering source), the card itself, and player references — none
#: is the chain's own single-object choice.
TARGET_BACKREF_TAGS: frozenset[str] = PLAYER_BACK_REFERENCES | frozenset(
    {
        "ParentTargetOwner",
        "ParentTargetController",
        "SelfRef",
        "TriggeringSource",
        "TriggeringPlayer",
        "TrackedSet",
        "TrackedSetFiltered",
        "Any",
        "Controller",
        "OriginalController",
        "Player",
        "TargetPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "ScopedPlayer",
        "AllPlayers",
        "Each",
        "EachPlayer",
    }
)


def root_target_filter(unit: AbilityUnit) -> object | None:
    """The FIRST real object-filter target in ``unit``'s effect chain — the
    object ``ParentTarget`` / ``ParentTargetOwner`` / ``ParentTargetController``
    resolve through — skipping a mass/symmetric effect
    (:data:`MASS_EFFECT_TAGS`, CR 601.2c: "all"/"each" names no single chosen
    object, so a later back-reference in the SAME chain can't mean IT) and any
    back-reference tag (:data:`TARGET_BACKREF_TAGS`). ``None`` when no unit
    effect names a genuine filter (Or/And/Typed) — a self-referencing chain
    (Mirror-Mad Phantasm's "this creature's owner shuffles IT into their
    library" — the SAME card, never a variable target)."""
    for c in unit.effects:
        if tag_of(c.node) in MASS_EFFECT_TAGS:
            continue
        tgt = getattr(c.node, "target", None)
        if tgt is None:
            continue
        tt = tag_of(tgt)
        if tt is None or tt in TARGET_BACKREF_TAGS:
            continue
        return tgt
    return None


#: Who creates a token (:func:`token_creator_side`).
TokenCreatorSide = Literal["you", "opponents", "each", "chosen", "any"]
#: Token ``owner`` back-references to the object the chain targets: "its
#: controller / its owner / they create".
_TARGET_OWNER_REFS: frozenset[str] = PLAYER_BACK_REFERENCES | {
    "ParentTargetController",
    "ParentTargetOwner",
}


def token_creator_side(unit: AbilityUnit, node: object) -> TokenCreatorSide | None:
    """The side of the player who creates the token a ``Token`` /
    ``CopyTokenOf`` effect ``node`` of ``unit`` makes — its owner and
    controller (CR 111.2: "The player who creates a token is its owner. The
    token enters the battlefield under that player's control."). Read off the
    effect's ``owner``, never its ``target``, which for a copy is the COPIED
    object, not its creator:

    * ``"you"`` — the controller (phase's default when the field is absent), a
      copied permanent's ``OriginalController``, and "that player" on a
      trigger that doesn't watch only opponents (Gonti, Night Minister; Jolene,
      Pain Distributor: a trigger you fire too);
    * ``"opponents"`` — a target opponent (Wedding Ring), and "that player" on
      a trigger that watches only opponents ("Whenever an opponent casts a
      spell, that player creates a Blood token" — Bloodvial Purveyor,
      :func:`triggering_player_side`);
    * ``"chosen"`` — a target player the card picks, who may be you
      (Prismari Command, Echocasting Symposium);
    * "its controller / owner creates" (:data:`_TARGET_OWNER_REFS`): the side
      of the object the chain targets (:func:`root_target_filter` — Vraska,
      the Cutting Glare's "target permanent an opponent controls. They create
      a Treasure token" is ``"opponents"``), and ``"any"`` for an unrestricted
      target or none (Get Lost, An Offer You Can't Refuse, Saw in Half: the
      removed object's controller — whoever that is);
    * otherwise the owner filter's own scope (``"each"`` for an unrestricted
      player filter), and ``None`` for an owner this read can't place (an
      Aura's enchanted player — Overencumbered's ``AttachedTo``).

    The wrapper's actor is not read: "each opponent creates" (Life of the
    Party) and "target opponent may have you create" (Terrapact Intimidator)
    hang the same opponent ``player_scope`` on it. Each lane decides what a
    side means for it."""
    owner = getattr(node, "owner", MISSING)
    if not _present(owner):
        return "you"
    tag = tag_of(owner)
    if tag in ("Controller", "OriginalController"):
        return "you"
    if (
        tag == "ScopedPlayer"
        and effect_owner_player_scope(unit.node, node) == YOU_AND_OPPONENT_SCOPE
    ):
        return "you"  # "you and target opponent each create" (Thran Spider)
    if tag == "TriggeringPlayer":
        return "opponents" if triggering_player_side(unit) == "opponents" else "you"
    if tag in ("Player", "TargetPlayer"):
        return "chosen"
    if tag in _TARGET_OWNER_REFS:
        side = filter_controller_side(root_target_filter(unit))
        return side if side in ("you", "opponents") else "any"
    scope = _scope_from_player_node(owner)
    if scope in ("you", "opponents", "each", "any"):
        return cast("TokenCreatorSide", scope)
    return None


# A damage recipient a caster may point at a creature as readily as at a
# player: "any target" (CR 115.4 — ``Any`` / ``Target``), or an unrestricted
# ``Typed`` ("any other target"). Such damage is burn / removal (the
# ``direct_damage`` lane), not a drain.
_ANY_TARGET_RECIPIENT_TAGS: frozenset[str] = frozenset({"Any", "Target"})
_CREATURE_RECIPIENT_WORDS: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Battle"}
)


def _recipient_can_be_own_board(rec: object) -> bool:
    """Whether a damage recipient filter may be a creature / battle / permanent
    of any side, or an unrestricted target — an ``Or`` when any alternative
    may be (Lightning Bolt's "any target"; "target creature or player"; Blast of
    Genius's "that permanent or player", a ``ParentTarget`` back to "any
    target")."""
    t = tag_of(rec)
    if t in _ANY_TARGET_RECIPIENT_TAGS or t == "ParentTarget":
        return True
    if t in ("Or", "And"):
        return any(
            _recipient_can_be_own_board(f) for f in getattr(rec, "filters", ()) or ()
        )
    if t == "Typed":
        words = _filter_type_words(rec)
        if not words:
            return getattr(rec, "controller", None) is None
        return any(w in _CREATURE_RECIPIENT_WORDS for w in words)
    return False


def _rides_a_targeted_object_effect(unit: AbilityUnit, node: TypedMirrorNode) -> bool:
    """Whether damage ``node`` to "that object's controller" follows an earlier
    effect of ``unit`` aimed at a target object — a rider on a removal spell or
    bite (Burn the Impure, Detonate, Blur of Blades), not a drain engine."""
    for c in unit.effects:
        if c.node is node:
            return False
        tgt = getattr(c.node, "target", None)
        if tag_of(tgt) == "Typed" and any(
            w != "Player" for w in _filter_type_words(tgt)
        ):
            return True
    return False


def damage_drains_opponent(unit: AbilityUnit, node: TypedMirrorNode) -> bool:
    """Whether a damage effect ``node`` of ``unit`` makes an opponent lose life
    — CR 120.3a: "Damage dealt to a player by a source without infect causes
    that player to lose that much life." The damage must reach a player
    (:func:`effect_reaches_player`) other than its controller alone:

    * a mass form (``DamageEachPlayer`` / ``DamageAll``) whose player reach
      (:func:`effect_player_reach`, its ``player_filter``) is the opponents, a
      target player, or every player ("each opponent" — Guttersnipe; "each
      player" — Sulfuric Vortex; "each opponent and each creature they
      control" — End the Festivities); not "you" (Hail Storm's ``Controller``),
      nor a symmetric sweeper whose player damage is a rider that hits you as
      hard ("each creature and each player" — Pestilence, Volcanic Fallout:
      mass removal);
    * a single recipient that is an opponent (``Typed{Opponent}`` — "target
      opponent", "target opponent or planeswalker"), a player ("target player
      or planeswalker" — Lava Axe), a player the trigger or effect names ("that
      player" — Eidolon of the Great Revel, Mogis; "that creature's controller"
      — Repercussion, Magnetic Mine, unless it rides a removal spell or bite
      on that object: Burn the Impure; the defending player), or a trigger's
      scoped player
      unless it is only you (:func:`scoped_player_scope` — Barbed Wire's "each
      player's upkeep").

    Not "any target" or another recipient that may be a creature of any side
    (Lightning Bolt, Arc Trail — burn / removal, ``direct_damage``'s), a back-
    reference to such a target (Burst Lightning's kicked "instead"), nor
    damage dealt to you (a painland's "deals 1 damage to you")."""
    if tag_of(node) not in DAMAGE_EFFECT_TAGS or not effect_reaches_player(
        node, unit.node
    ):
        return False
    if tag_of(node) in ("DamageEachPlayer", "DamageAll"):
        reach = effect_player_reach(unit.node, node)
        if reach == "each" and effect_reaches_permanent(node, unit.node):
            return False
        if reach is not None:
            return reach != "scoped" or scoped_player_scope(unit) is not None
        pf = player_filter_tag(node) or ""
        return pf == "All" or pf.startswith("Opponent")
    rec = damage_recipient(node)
    t = tag_of(rec)
    if t in ("Controller", "You", "SelfRef"):
        return False
    if t == "ScopedPlayer":
        # "for each player, ~ deals 1 damage to that player" (Lim-Dûl's Hex): the
        # loop's wrapper names the players even on your own upkeep.
        actor = effect_owner_player_scope(unit.node, node)
        if actor is not None and actor not in ("Controller", "You", "SelfRef"):
            return True
        return scoped_player_scope(unit) is not None
    if t == "ParentTarget":
        return not effect_reaches_permanent(node, unit.node)
    if t == "DeclaredPlayer":  # "that player" — a player, never a permanent
        return True
    if t in ("ParentTargetController", "EventTargetController"):
        return not _rides_a_targeted_object_effect(unit, node)
    if t in ("Typed", "Or", "And"):
        side = filter_controller_side(rec)
        if side == "you":
            return False
        return side == "opponents" or not _recipient_can_be_own_board(rec)
    return t not in _ANY_TARGET_RECIPIENT_TAGS


def life_lost_this_turn_sides(node: object) -> frozenset[str]:
    """The sides whose "life lost this turn" ``node`` reads (CR 119.3): every
    ``LifeLostThisTurn`` quantity under it, by its ``player`` — ``"you"``
    ("the life you've lost this turn" — Children of Korlis), ``"opponents"``
    ("if an opponent lost life this turn" — Stromkirk Bloodthief, Bat
    Whisperer; "for each 1 life your opponents have lost this turn" — Rakdos,
    Lord of Riots), ``"each"`` for any other player — plus an
    ``OpponentLostLife`` player filter ("for each of your opponents who lost
    life this turn" — Belbe) → ``"opponents"``. A deep walk: the quantity sits
    in a trigger's intervening-if, a replacement's condition, an activation
    restriction, an effect amount or a cost reduction's count alike."""
    negated: set[int] = set()
    for n in _iter_typed_nodes(node):
        if _is_none_comparison(n):
            negated.update(id(q) for q in _iter_typed_nodes(getattr(n, "lhs", None)))
    out: set[str] = set()
    for n in _iter_typed_nodes(node):
        t = tag_of(n)
        if t == "OpponentLostLife":
            out.add("opponents")
        elif t == "LifeLostThisTurn" and id(n) not in negated:
            out.add(_scope_from_player_node(getattr(n, "player", None)) or "each")
    return frozenset(out)


def _is_none_comparison(n: object) -> bool:
    """Whether ``n`` is a quantity comparison that holds only when its left
    side is zero — "if you didn't lose life this turn" (Luminarch Ascension:
    ``EQ 0``; also ``LE 0`` / ``LT 1``): a reward for NOT losing life."""
    comparator = getattr(n, "comparator", MISSING)
    rhs = getattr(n, "rhs", MISSING)
    if not isinstance(comparator, str) or tag_of(rhs) != "Fixed":
        return False
    value = getattr(rhs, "value", None)
    if not isinstance(value, int):
        return False
    return (comparator in ("EQ", "LE") and value <= 0) or (
        comparator == "LT" and value <= 1
    )


# ── end token creators, damage drains and life lost this turn ──


# ── Spell classes, granted keywords, land-type grants, graveyard exiles ──

#: What a spell filter names, as :func:`spell_filter_class` sorts it.
SpellClass = Literal[
    "instant_sorcery",
    "noncreature",
    "permanent_type",
    "subtype",
    "color",
    "historic",
    "mana_value",
    "other",
    "any",
]

#: Spell-filter predicates by the class they narrow a spell to: its colours
#: ("a white spell", "a multicolored spell"), being historic (CR 700.6), its
#: mana value or an X in its cost.
_SPELL_PRED_CLASSES: dict[str, SpellClass] = {
    "HasColor": "color",
    "ColorCount": "color",
    "NotColor": "color",
    "Historic": "historic",
    "Cmc": "mana_value",
    "HasXInManaCost": "mana_value",
}


def spell_filter_class(filt: object) -> SpellClass:
    """The class of spell a cast trigger watches or a cost reducer discounts,
    read off its spell filter (CR 601.2):

    * ``"instant_sorcery"`` — the filter names instant or sorcery, alone or
      beside another type or subtype ("an instant, sorcery, or Wizard spell" —
      Windrider Wizard; "artifact, instant, and sorcery spells" — Urza, Lord
      Protector);
    * ``"noncreature"`` — it negates creature and names no other type (the
      prowess idiom, CR 702.108a; "a noncreature or Otter spell");
    * ``"permanent_type"`` — permanent card types only (a creature,
      enchantment or artifact spell);
    * ``"subtype"`` — subtypes only (a Dragon spell, a Spirit or Arcane spell);
    * ``"color"`` / ``"historic"`` / ``"mana_value"`` — any spell narrowed by
      its colours, by being historic, or by its mana value or X;
    * ``"other"`` — any spell narrowed by another quality (kicked, a keyword,
      targeting, a legendary spell, a spell you don't own);
    * ``"any"`` — no filter, or none of the above ("whenever you cast a
      spell")."""
    cores = set(filter_core_types(filt)) - {"Card", "Any"}
    if cores & {"Instant", "Sorcery"}:
        return "instant_sorcery"
    if "Creature" in filter_non_types(filt) and not cores:
        return "noncreature"
    if cores:
        return "permanent_type"
    if filter_subtypes(filt):
        return "subtype"
    preds = filter_predicates(filt)
    for pred in preds:
        if pred in _SPELL_PRED_CLASSES:
            return _SPELL_PRED_CLASSES[pred]
    return "other" if preds else "any"


_GRANTED_KEYWORDS_CACHE_ATTR = "_xw_granted_keyword_names"


def granted_keyword_names(node: object) -> frozenset[str]:
    """The lower-cased keyword names every grant under ``node`` hands out: an
    ``AddKeyword`` modification anywhere below it (a static, an Aura's or
    Equipment's grant, a one-shot "gains rebound" — CR 613.1f) and a created
    token's own keywords (Goblin Wizardry's prowess Wizards — CR 111.3: the
    effect that creates a token defines its characteristics, its abilities
    among them). The card's own printed keywords are the bulk keyword array's,
    not read here. Memoized on ``node``: several lanes ask it of each unit."""
    if isinstance(node, TypedMirrorNode):
        cached = node.__dict__.get(_GRANTED_KEYWORDS_CACHE_ATTR)
        if cached is not None:
            return cached
    out: set[str] = set()
    for _sdef, mod in iter_mod_sites(node, deep=True):
        if tag_of(mod) == "AddKeyword":
            name = mod_keyword_name(mod)
            if name:
                out.add(name.lower())
    for n in iter_typed_nodes(node):
        out.update(kw.lower() for kw in token_profile_keywords(n))
    result = frozenset(out)
    if isinstance(node, TypedMirrorNode):
        object.__setattr__(node, _GRANTED_KEYWORDS_CACHE_ATTR, result)
    return result


#: The modifications that give a land basic land types in addition to its own
#: (CR 305.7: "If a land gains one or more land types in addition to its own,
#: it keeps its land types and rules text, and it gains the new land types").
_ADDS_BASIC_LAND_TYPES: frozenset[str] = frozenset({"AddAllBasicLandTypes"})


def _adds_basic_land_types(mod: object) -> bool:
    tag = tag_of(mod)
    if tag in _ADDS_BASIC_LAND_TYPES:
        return True
    return tag == "AddChosenSubtype" and getattr(mod, "kind", None) == "BasicLandType"


def basic_land_type_grants(node: object) -> tuple[str | None, ...]:
    """The side of the lands each grant of basic land types under ``node``
    reaches: "Lands you control are every basic land type in addition to their
    other types" (Prismatic Omen, Dryad of the Ilysian Grove) and "target land
    you control becomes the basic land type of your choice in addition to its
    other types" (Navigator's Compass) read ``"you"``; an Aura's "Enchanted
    land is every basic land type" (Nylea's Presence) reads ``"attached"``; a
    land typing itself ("This land is the chosen type" — Thran Portal,
    Multiversal Passage) reads ``"self"``; otherwise
    :func:`filter_controller_side` of the affected lands (``None`` for every
    land). A one-shot grant to its effect's target
    (``ParentTarget``) reads that target. A type SET (Blood Moon's
    ``SetBasicLandType``) replaces the land's types and is not a grant."""
    parent: dict[int, object] = {}
    for n in iter_typed_nodes(node):
        if tag_of(n) == "GenericEffect":
            for sdef in getattr(n, "static_abilities", None) or ():
                parent[id(sdef)] = getattr(n, "target", None)
    out: list[str | None] = []
    for sdef, mod in iter_mod_sites(node, deep=True):
        if not _adds_basic_land_types(mod):
            continue
        affected = getattr(sdef, "affected", None)
        if tag_of(affected) == "ParentTarget":
            affected = parent.get(id(sdef))
        if tag_of(affected) == "SelfRef":
            out.append("self")
        elif set(filter_predicates(affected)) & ATTACHED_OBJECT_PREDICATES:
            out.append("attached")
        else:
            out.append(filter_controller_side(affected))
    return tuple(out)


def graveyard_exile_replacement_side(
    unit: AbilityUnit,
) -> Literal["you", "opponents", "any"] | None:
    """Whose graveyard a "would be put into a graveyard … exile it instead"
    replacement empties (CR 614.1a): "If a card would be put into an
    opponent's graveyard from anywhere, exile it instead" (Leyline of the
    Void, Dauthi Voidwalker) reads ``"opponents"``; any card's (Rest in
    Peace) ``"any"``; your own cards' ``"you"``. A graveyard is its owner's
    (CR 404.1), so the side is the card filter's ``Owned`` property: a "would
    die" replacement naming only the creature's CONTROLLER ("If a creature an
    opponent controls would die, exile it instead" — Kalitas, Gisa) keeps a
    creature off the battlefield-to-graveyard path, not out of a graveyard,
    and reads ``None``, as does any other unit and the card's own "if this
    would be put into a graveyard" replacement (a ``SelfRef`` card filter)."""
    if unit.origin != "replacement" or replacement_event_tag(unit.node) != "Moved":
        return None
    if getattr(unit.node, "destination_zone", None) != "Graveyard":
        return None
    if not any(
        tag_of(c.node) in ("ChangeZone", "ChangeZoneAll")
        and getattr(c.node, "destination", None) == "Exile"
        for c in unit.effects
    ):
        return None
    filt = getattr(unit.node, "valid_card", None)
    if not _present(filt) or filt is None:
        return "any"
    if tag_of(filt) not in ("Typed", "Or", "And"):
        return None
    parts = getattr(filt, "filters", None) if tag_of(filt) in ("Or", "And") else None
    owners = [filter_owned_controller(p) for p in (parts or (filt,))]
    if not any(owners):
        return None
    sides = {controller_side(o) for o in owners if o}
    if "you" in sides:
        return "you"
    if sides & {"opponents", "chosen"}:
        return "opponents"
    return "any"


#: What an exile out of a graveyard reads as (:func:`graveyard_exile_kind`):
#: graveyard hate at a scope, or an exile out of your own graveyard.
GraveyardExile = Literal["opponents", "any", "own"]


#: An ownerless graveyard exile's ``ConceptNode.scope`` the overlay's
#: ``graveyard_owner`` arm re-read off its clause, as what the exile reads as.
_GY_OWNER_SCOPE: dict[str, GraveyardExile] = {
    "you": "own",
    "opponents": "opponents",
    "any": "any",
}


def graveyard_exile_kind(
    node: TypedMirrorNode, scope: str | None = None
) -> GraveyardExile | None:
    """What an effect that answers its target (:func:`answers_its_target`)
    reads as when it exiles out of a graveyard, or ``None`` when it doesn't:

    * ``"opponents"`` — hate on an opponent's graveyard, or a player's the
      card picks ("exile target player's graveyard" — Bojuka Bog, Angel of
      Finality; "exile all cards from target player's graveyard" —
      Necromancer's Covenant);
    * ``"any"`` — hate on a card from a graveyard, or all of them ("exile up
      to one target card from a graveyard" — Afterthought Sentry,
      Necrogenesis; "exile all graveyards" — Rest in Peace);
    * ``"own"`` — no hate: your own graveyard, a card an earlier clause named
      (the discarded card Necropotence exiles), or each player exiling from
      their own (Living Death's mass reanimation).

    Each half of a compound target names its own graveyard (Spelltwine: "…
    from your graveyard and … from an opponent's graveyard"); a half that is
    yours makes the exile ``"own"``. The owner is the filter's ``Owned``
    property, else its controller (:func:`controller_side`). A filter naming no
    owner reads ``scope``, its concept's corrected scope (:func:`corrected_scope`):
    the overlay's ``graveyard_owner`` re-read of the owner phase dropped ("from
    that player's graveyard" — Skullsnatcher; "from defending player's
    graveyard" — Grime Gorger; "from a graveyard" — Savior of Ollenbock)."""
    filt = effect_filter(node)
    origin, _ = change_zone_dirs(node)
    in_gy = "Graveyard" in filter_inzone_zones(filt)
    if origin != "Graveyard" and not in_gy:
        return None
    if tag_of(filt) == "Player":
        return "opponents"
    owners = filter_owners(filt)
    if not any(owners) and scope in _GY_OWNER_SCOPE:
        return _GY_OWNER_SCOPE[scope]
    sides = {controller_side(o) for o in owners}
    if "you" in sides:
        return "own"
    if sides & {"opponents", "chosen"}:
        return "opponents"
    if (
        not any(owners)
        and tag_of(filt) in ("Typed", "Or", "And")
        and (in_gy or tag_of(node) == "ChangeZoneAll")
    ):
        return "any"
    return "own"


def cast_trigger_origin(trig: object) -> tuple[str, str] | None:
    """The zone condition a cast trigger puts on where the spell was cast from,
    as ``(comparator, zone)``: "Whenever you cast a spell from exile" (Faldorn,
    Dread Wolf Herald) is ``("Equals", "Exile")``; paradox's "from anywhere
    other than your hand" (Vega, the Watcher) ``("NotEquals", "Hand")``.
    ``None`` when the trigger names no origin. CR 601.2a."""
    origin = getattr(trig, "spell_cast_origin", MISSING)
    if not _present(origin) or origin is None:
        return None
    zone = getattr(origin, "data", None)
    comparator = tag_of(origin)
    if isinstance(zone, str) and comparator is not None:
        return comparator, zone
    return None


# ── end spell classes, granted keywords, land-type grants, graveyard exiles ──


# ── Keyword subjects, damage amplifiers, triggering-player punishers ──


def keyword_subject(kw: str) -> str:
    """phase's keyword spelling as a signal subject — lower case, one space
    between words (``DoubleStrike`` → ``"double strike"``, ``Haste`` →
    ``"haste"``): the granted keyword a keyword-grant ident names. ``""`` for
    none."""
    out: list[str] = []
    for i, ch in enumerate(kw):
        if ch.isupper() and i and kw[i - 1].islower():
            out.append(" ")
        out.append(ch.lower())
    return "".join(out).strip()


def effect_damage_amplifier(
    node: object,
) -> tuple[str, str | None, str | None] | None:
    """``(modification, recipient scope, source controller)`` of a damage
    replacement an EFFECT sets up for later (CR 614.1a: "Effects that use the
    word 'instead' are replacement effects"), or ``None``. Two phase shapes:

    * an ``AddTargetReplacement`` whose ``replacement`` is a ``DamageDone``
      replacement — the one-shot "this turn" doubler a spell or ability
      creates (Isengard Unleashed's triple, Goblin Goliath's activated
      double, a Saga chapter's);
    * a ``CreateDamageReplacement`` carrying a ``modification`` (Desperate
      Gambit's won flip: "the next time that source would deal damage this
      turn, it deals double that damage instead").

    The modification is the tag (``Double`` / ``Triple`` / ``Plus`` …), the
    recipient scope :func:`damage_filter_scope` of the recipient filter, the
    source controller :func:`filter_controller` of the source filter. A
    replacement with no modification (a redirect or prevention shield) is
    ``None``.
    """
    t = tag_of(node)
    if t == "AddTargetReplacement":
        rep = getattr(node, "replacement", None)
        if not isinstance(rep, TypedMirrorNode):
            return None
        if replacement_event_tag(rep) != "DamageDone":
            return None
        mod = replacement_damage_mod(rep)
        if mod is None:
            return None
        return (
            mod,
            damage_filter_scope(rep, "damage_target_filter"),
            filter_controller(getattr(rep, "damage_source_filter", None)),
        )
    if t == "CreateDamageReplacement":
        mod = tag_of(getattr(node, "modification", None))
        if mod is None or not isinstance(node, TypedMirrorNode):
            return None
        return (
            mod,
            damage_filter_scope(node, "target_filter"),
            filter_controller(getattr(node, "source_filter", None)),
        )
    return None


#: Player tags naming "that player" — a player an ability picked out of its
#: trigger event or its wrapper's player loop, resolved against the unit.
THAT_PLAYER_TAGS: frozenset[str] = frozenset({"TriggeringPlayer", "ScopedPlayer"})
#: The effects that hurt the player they name — damage (CR 120.3a: damage to
#: a player makes them lose that much life), life loss (119.3), a discard
#: (701.9a) and a mill (701.17a).
_HURTS_PLAYER_TAGS: frozenset[str] = frozenset(
    {"DealDamage", "LoseLife", "Discard", "Mill"}
)


def hurts_triggering_player(node: object) -> bool:
    """Whether an effect anywhere under ``node`` (a trigger's ``execute``) hurts
    the player the trigger names, phase's ``TriggeringPlayer``: damage, life
    loss, a discard or a mill aimed at that player
    (:data:`_HURTS_PLAYER_TAGS` — Eidolon of the Great Revel's damage,
    Phyrexian Tyranny's life loss), or "that player sacrifices" (a
    ``Sacrifice`` whose filter "that player" controls, :data:`THAT_PLAYER_TAGS`
    — Liesa, Oppression). The caller gates which trigger event it reads."""
    for n in _iter_typed_nodes(node):
        t = tag_of(n)
        if t in _HURTS_PLAYER_TAGS and recipient_tag(n) == "TriggeringPlayer":
            return True
        if t == "Sacrifice" and (
            filter_controller(getattr(n, "target", None)) in THAT_PLAYER_TAGS
        ):
            return True
    return False


def punishes_triggering_caster(trig: object) -> bool:
    """Whether a trigger DEFINITION is the SYMMETRIC cast punisher: a
    ``SpellCast`` / ``SpellCastOrCopy`` trigger with no player restriction
    ("whenever a player casts …", no ``valid_target``) whose effect hurts the
    player who cast — damage, life loss, a discard or a mill aimed at
    ``TriggeringPlayer``, or "that player sacrifices" (Eidolon of the Great
    Revel, Pyrostatic Pillar, Liesa, Oppression, Aether Barrier). A
    symmetric trigger that pays you (Niv-Mizzet, Parun; the lifegain
    trinkets), helps the caster (Glademuse) or costs you (Ebon Drake) is
    not one (:func:`hurts_triggering_player`). The opponent-restricted form
    is :func:`is_opponent_cast_trigger_def`.
    """
    if not isinstance(trig, TypedMirrorNode):
        return False
    if trigger_def_event(trig) not in ("cast_spell", "spellcastorcopy"):
        return False
    vt = getattr(trig, "valid_target", None)
    if _present(vt) and tag_of(vt) is not None:
        return False
    return hurts_triggering_player(getattr(trig, "execute", None))


#: The combat-status predicates only a creature carries (CR 508.1a: creatures
#: attack; CR 506.4: an attacking, blocking or blocked object is a creature).
_COMBAT_CREATURE_PREDICATES: frozenset[str] = frozenset(
    {"Attacking", "Blocking", "Blocked", "Unblocked"}
)


def filter_names_creatures(filt: object) -> bool:
    """Whether a filter names creatures: the Creature core type, a creature type
    alone ("Other Spiders you control" — Cosmic Spider-Man; CR 205.3m: creatures
    and kindreds share their subtypes, the creature types), or a combat status
    only a creature has ("Attacking tokens you control" — Neyali, Suns'
    Vanguard; :data:`_COMBAT_CREATURE_PREDICATES`)."""
    if "Creature" in filter_core_types(filt):
        return True
    if any(s.lower() in CREATURE_TYPES for s in filter_subtypes(filt)):
        return True
    return bool(_COMBAT_CREATURE_PREDICATES & set(filter_predicates(filt)))


def attacks_your_opponents(filt: object) -> bool:
    """Whether a filter is the creatures attacking your opponents ("Creatures
    attacking your opponents have double strike" — Blast-Furnace Hellkite): an
    ``Attacking`` property whose defender is an opponent. Your attackers are
    among them, whoever else's are (CR 508.1a)."""
    return any(
        tag_of(prop) == "Attacking" and getattr(prop, "defender", None) == "Opponent"
        for prop in list_field(filt, "properties")
    )


# ── end keyword subjects, damage amplifiers, triggering-player punishers ──


# ── Borrow-and-cast theft and untap riders ──
# Two joins over one ability unit's effect chain. ``steals_card_to_cast``:
# the borrow-and-cast theft — a card another player owns leaves its zone into
# exile and the same unit lets YOU cast or play it (Court of Locthwain,
# Brainstealer Dragon, Daxos of Meletis, Gonti, Psychic Theft, Hostage Taker,
# Spelljack). CR 108.3: the card keeps its owner, so this is casting what you
# don't own, never a control change (CR 110.2). ``untap_rider_targets``: the
# untap of ONE creature the effect itself names — the enchanted / equipped
# creature (Freed from the Real, Instill Energy) or "untap it" after the
# effect's own pump / counter / attach on a target (Bull's Strength, Stony
# Strength), the shapes ``_iter_untap_targets`` leaves to its TargetOnly
# threading.

#: Library-to-exile effects whose ``player`` names whose library the card
#: leaves (:func:`exiled_library_side`): an exile from the top, a
#: look-and-exile dig, an exile-until.
LIBRARY_EXILE_TAGS: frozenset[str] = frozenset({"ExileTop", "Dig", "ExileFromTopUntil"})
#: ``player`` tags naming a player the card picks out, who may be you: a target
#: player, a back-reference to a target or its controller.
_PICKED_PLAYER_TAGS: frozenset[str] = TARGETED_PLAYER_TAGS | {"ParentTargetController"}
#: A ``GrantCastingPermission`` grantee that is not the controller: "its owner
#: may cast it" (Release to the Wind, Elite Spellbinder) returns the card.
_OTHER_PLAYER_GRANTEES: frozenset[str] = frozenset(
    {"ObjectOwner", "OriginalController"}
)


def _that_player_is_other(unit: AbilityUnit, node: object, tag: str | None) -> bool:
    """Whether a "that player" tag names someone other than you: a trigger
    watching opponents (:func:`triggering_player_side` — Mind's Dilation), a
    combat-damage-to-a-player trigger with no player restriction (a source of
    yours damages an opponent — Daxos, Ragavan, Thief of Sanity), or a
    ``ScopedPlayer`` bound by a wrapper's player loop
    (:func:`effect_owner_player_scope` — Ixhel's "each opponent who …")."""
    if tag == "TriggeringPlayer":
        side = triggering_player_side(unit)
        if side is not None:
            return side == "opponents"
        return unit.trigger_event == "deals_damage"
    if tag == "ScopedPlayer":
        return (
            unit.trigger_event == "deals_damage"
            or effect_owner_player_scope(unit.node, node) is not None
        )
    return False


#: Whose library a library-to-exile effect takes from (:func:`exiled_library_side`).
LibrarySide = Literal["you", "opponents", "each", "chosen"]


def exiled_library_side(
    root: object, node: object, unit: AbilityUnit | None = None
) -> LibrarySide:
    """Whose library a library-to-exile effect ``node`` (:data:`LIBRARY_EXILE_TAGS`)
    owned by ``root`` takes from, read off its ``player`` and the actor of the
    wrapper that owns it (:func:`effect_owner_player_scope`):

    * ``"opponents"`` — an opponent filter or actor tag ("the top card of
      target opponent's library" — Court of Locthwain, Gonti), "that player"
      when ``unit`` places them on the opponents' side
      (:func:`_that_player_is_other` — Thief of Sanity, Daxos), or a
      controller-relative ``player`` under an opponent wrapper (Brainstealer
      Dragon's "each opponent", phase v0.86.0);
    * ``"each"`` — a controller-relative ``player`` under an every-player
      wrapper (Extract Power, Share the Spoils): yours among the rest;
    * ``"chosen"`` — a player the card picks out, who may be you: a target
      player or a back-reference to a target (:data:`_PICKED_PLAYER_TAGS`), a
      target-player wrapper, a player filter naming no controller, or "that
      player" the unit doesn't place (no ``unit`` for a granted body);
    * ``"you"`` — your own library (Valakut Exploration, Act on Impulse).

    An impulse read wants ``"you"`` / ``"each"``; a theft read
    ``"opponents"`` / ``"each"``."""
    player = getattr(node, "player", None)
    tag = tag_of(player)
    if tag in THAT_PLAYER_TAGS:
        if unit is not None and _that_player_is_other(unit, node, tag):
            return "opponents"
        return "chosen"
    if tag == "Typed":
        side = filter_controller_side(player) or "chosen"
    else:
        side = controller_side(tag) or (
            "chosen" if tag in _PICKED_PLAYER_TAGS else "you"
        )
    if side != "you":
        return side
    wrapper = effect_owner_player_scope(root, node)
    if wrapper is None:
        return "you"
    if wrapper in OPPONENT_WRAPPER_ACTORS or controller_side(wrapper) == "opponents":
        return "opponents"
    return "chosen" if controller_side(wrapper) == "chosen" else "each"


def _picks_other_players_card(unit: AbilityUnit) -> bool:
    """Whether a sibling of the unit picks the card a back-referenced exile
    takes out of another player's hidden zone or off the stack: a hand reveal
    of a target / opposing player (Psychic Theft, Covetous Urge), a choice
    from a targeted player's or an opponent's zone, or a counterspell whose
    countered spell is then exiled (Spelljack, Kheru Spellsnatcher)."""
    for c in unit.effects:
        tag = tag_of(c.node)
        if tag == "RevealHand":
            target = getattr(c.node, "target", None)
            if tag_of(target) in ("Player", "TargetPlayer") or (
                filter_controller_side(target) in ("opponents", "chosen")
            ):
                return True
        if tag == "ChooseFromZone" and getattr(c.node, "zone_owner", None) in (
            "TargetedPlayer",
            "Opponent",
        ):
            return True
        if tag in ("Counter", "CounterAll"):
            return True
    return False


def _exiles_other_players_card(unit: AbilityUnit, node: TypedMirrorNode) -> bool:
    """Whether a ``ChangeZone`` / ``ChangeZoneAll`` to exile takes a card you
    don't own (or needn't own): out of an opponent's hand, graveyard or
    library (Author of Shadows, Fiend of the Shadows' "that player exiles a
    card from their hand"), a back-referenced card a sibling picked
    (:func:`_picks_other_players_card`), or a battlefield permanent the
    target filter doesn't restrict to yours (Hostage Taker, Abstruse
    Appropriation, Heartless Conscription). The source itself, a card in
    your own graveyard or hand (Savvy Trader) and the triggering spell
    (Possibility Storm) are not."""
    origin, dest = change_zone_dirs(node)
    if dest != "Exile":
        return False
    target = getattr(node, "target", None)
    tag = tag_of(target)
    if tag == "ParentTarget":
        return _picks_other_players_card(unit)
    if tag not in ("Typed", "Or", "And"):
        return False
    owner = filter_controller(target)
    if owner in THAT_PLAYER_TAGS:
        return _that_player_is_other(unit, node, owner)
    side = filter_controller_side(target)
    if side == "you":
        return False
    if origin in ("Hand", "Graveyard", "Library") or filter_inzone_zones(target):
        return side in ("opponents", "chosen")
    return origin in (None, "Battlefield")


def lets_you_play_exiled(c: ConceptNode) -> bool:
    """Whether an effect lets the CONTROLLER play or cast a card an effect of
    the same ability exiled: a ``PlayFromExile`` casting permission no other
    player is granted (:data:`_OTHER_PLAYER_GRANTEES` — not Release to the
    Wind's "its owner may cast it"), or a cast-from-zone permission ("you may
    cast a spell from among them" — Etali, Primal Storm) that doesn't name
    your own hand or graveyard (CR 601.2: casting a spell; the card exiled
    keeps its owner, CR 108.3). Typed nodes only: a permission phase parked
    as a residue doesn't say who may play the card ("that creature's
    controller may play that card" — Curse of Hospitality)."""
    tag = tag_of(c.node)
    if tag == "GrantCastingPermission":
        grantee = getattr(c.node, "grantee", MISSING)
        return permission_tag(c.node) == "PlayFromExile" and (
            not _present(grantee) or tag_of(grantee) not in _OTHER_PLAYER_GRANTEES
        )
    if tag == "CastFromZone":
        return filter_controller_side(getattr(c.node, "target", None)) != "you"
    return False


def steals_card_to_cast(unit: AbilityUnit) -> ConceptNode | None:
    """The effect of ``unit`` that takes a card another player owns into exile
    when the same unit lets you cast or play it — the borrow-and-cast theft
    (CR 108.3: you cast a card you don't own; no control change). The exile
    is a dig of a library that isn't yours alone (:func:`exiled_library_side`)
    or a zone change of a card you don't own
    (:func:`_exiles_other_players_card`); the permission is
    :func:`lets_you_play_exiled`. ``None`` for a self-impulse (Valakut
    Exploration: your own library), a "its owner may cast it" exile (Release
    to the Wind) and a cast from your own graveyard (Goblin Dark-Dwellers)."""
    if not any(lets_you_play_exiled(c) for c in unit.effects):
        return None
    for c in unit.effects:
        tag = tag_of(c.node)
        if tag in LIBRARY_EXILE_TAGS and exiled_library_side(
            unit.node, c.node, unit
        ) in ("opponents", "each"):
            return c
        if tag in ("ChangeZone", "ChangeZoneAll") and _exiles_other_players_card(
            unit, c.node
        ):
            return c
    return None


#: Effects on a target that an "untap it" (``ParentTarget``) rider follows:
#: a pump, a counter, an attach, a removal from combat (Reconnaissance), an
#: animation (Avatar Kyoshi, Earthbender's "earthbend 8, then untap that land").
_UNTAP_RIDER_HOSTS: frozenset[str] = frozenset(
    {"Pump", "GenericEffect", "PutCounter", "Attach", "RemoveFromCombat", "Animate"}
)
#: The static modifications a ``GenericEffect`` host carries besides a pump or a
#: keyword: a color change ("Target creature becomes blue" — Cerulean Wisps) or
#: an animation ("target noncreature artifact you control becomes a 0/0 artifact
#: creature … Untap it" — Living Brain, Mechanical Marvel).
_UNTAP_RIDER_HOST_MODS: frozenset[str] = frozenset(
    {"SetColor", "AddColor", "SetPower", "SetToughness", "AddType"}
)


def untap_rider_targets(unit: AbilityUnit) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(target filter, SetTapState node)`` for each Untap in ``unit`` whose
    target is ONE creature the effect names itself: the enchanted or
    equipped creature (Freed from the Real, Pemmin's Aura, Instill Energy —
    an ``EnchantedBy`` / ``EquippedBy`` filter), or "untap it" back-referring
    to the preceding host effect's target (:data:`_UNTAP_RIDER_HOSTS` —
    Bull's Strength's pump, Stony Strength's counter; a ``GenericEffect``
    host must carry a pump or keyword grant in the unit's statics). The
    caller decides what an opponent's creature means; a self-untap
    (``SelfRef`` — Thermo-Alchemist) is not one of these.

    Any rider back on the same object keeps the host ("Prevent all damage that
    would be dealt to it this turn. If it's renowned, untap it." — Enshrouding
    Mist), a color change hosts like a pump ("Target creature becomes blue
    until end of turn. Untap that creature." — Cerulean Wisps), and a "you may
    tap or untap that creature" choice untaps it too (Vedalken Anatomist's
    ``ChooseOneOf``)."""
    grants = any(
        c.concept in ("pump", "grant_keyword")
        or tag_of(c.node) in _UNTAP_RIDER_HOST_MODS
        for c in unit.statics
    )
    host: object | None = None
    for c in unit.effects:
        node = c.node
        tag = tag_of(node)
        target = getattr(node, "target", None)
        choices = (getattr(b, "effect", None) for b in list_field(node, "branches"))
        untap = next(
            (
                n
                for n in (node, *choices)
                if isinstance(n, TypedMirrorNode)
                and tag_of(n) == "SetTapState"
                and settap_state(n) == "Untap"
            ),
            None,
        )
        if untap is not None:
            utarget = getattr(untap, "target", None)
            if tag_of(utarget) == "Typed" and names_attached_object(utarget):
                yield utarget, untap
            elif tag_of(utarget) == "ParentTarget" and host is not None:
                yield host, untap
            continue
        if tag_of(target) not in ("Typed", "Or", "And"):
            # A second rider on the same object ("It gains reach … Untap it."
            # — Biosynthic Burst), or an effect naming no new object (a delayed
            # trigger, a draw, a back-reference), keeps the host.
            continue
        if tag in _UNTAP_RIDER_HOSTS and (tag != "GenericEffect" or grants):
            host = target
        else:
            host = None


# ── end borrow-and-cast theft and untap riders ──


# ── Evasion sites, land-type changers, subtype payoffs ──

#: The evasion keyword abilities (CR 509.1b: "a static ability an attacking
#: creature has that restricts what can block it") the ``evasion_self`` lane
#: names by kind, folded by :func:`normalised_keyword_name`: menace (CR
#: 702.111b), fear (702.36b), intimidate (702.13b), skulk (702.118b),
#: horsemanship (702.31b), shadow (702.28b) and landwalk in every spelling
#: phase writes (702.14c). Flying (702.9b) is left out as soft evasion.
EVASION_KEYWORD_KINDS: frozenset[str] = frozenset(
    {"menace", "fear", "intimidate", "skulk", "horsemanship", "shadow", "landwalk"}
)
#: The blocking-restriction static modes an attacker can carry, by kind:
#: "can't be blocked" is ``unblockable``; "can't be blocked except by …" /
#: "by …" / "unless all creatures defending player controls block it" leave
#: some blockers, so ``partial``. ``CantBeBlockedByMoreThan`` ("can't be
#: blocked by more than one creature") limits how MANY block, not what can, so
#: it maps to ``None``: seen, but no evasion.
_EVASION_MODE_KINDS: dict[str, str | None] = {
    "CantBeBlocked": "unblockable",
    "CantBeBlockedExceptBy": "partial",
    "CantBeBlockedBy": "partial",
    "CantBeBlockedUnlessAllBlock": "partial",
    "CantBeBlockedByMoreThan": None,
}
#: The ``affected`` shapes that name ONE creature: the card itself, a chosen
#: target, the triggering object, the tokens just made (each one a body of its
#: own). Any other filter is a population — a team, tribal or symmetric grant
#: (``team_evasion_grant`` / ``all_creatures_kw_grant``) — unless it is the
#: object an Equipment or Aura is attached to (:data:`ATTACHED_OBJECT_PREDICATES`).
_ONE_CREATURE_AFFECTED: frozenset[str] = frozenset(
    {"SelfRef", "ParentTarget", "TriggeringSource", "LastCreated", "TrackedSet"}
)
#: Conditions that never gate an attack: a creature only attacks during its
#: controller's turn (CR 506.2), so "During your turn, equipped creature … can't
#: be blocked" (Bilbo's Ring) is unconditional evasion.
_ATTACK_TURN_CONDITIONS: frozenset[str] = frozenset({"DuringYourTurn"})
#: Random-outcome nodes: evasion granted in one branch is chance, not a plan.
_CHANCE_TAGS: frozenset[str] = FLIP_COIN_TAGS | {"RollDie"}


class EvasionSite(NamedTuple):
    """One evasion a card carries or grants. ``kind`` is an
    :data:`EVASION_KEYWORD_KINDS` member, ``"unblockable"`` or ``"partial"``
    (``None`` for a blocking restriction that is not evasion); ``team`` marks a
    grant to a population rather than one creature; ``conditional`` marks one
    that holds only while a condition is met (an intervening-if trigger, a
    static's ``condition``, a level, a coin flip)."""

    kind: str | None
    team: bool
    conditional: bool


def list_field(node: object, name: str) -> list[Any]:
    """A node's list field, ``[]`` when absent or null — an absent optional field
    loads as the truthy :data:`MISSING` sentinel, so ``getattr(…) or ()`` would
    iterate it (``extra_keywords`` and some ``modifications`` default to it)."""
    value = getattr(node, name, None)
    return value if isinstance(value, list) else []


def evasion_keyword_kind(name: str) -> str | None:
    """The :data:`EVASION_KEYWORD_KINDS` kind a keyword spelling names — phase's
    or Scryfall's, folded by :func:`normalised_keyword_name` — or ``None``:
    every landwalk spelling ("Islandwalk", "Snow swampwalk", "Nonbasic
    landwalk", "Desertwalk" — CR 702.14c: a land type, or a type or supertype
    and "land") is ``"landwalk"``. A "… Walk" ability word (Bane's Invoker's
    "Wind Walk") names no land and is no landwalk."""
    kw = normalised_keyword_name(name)
    if kw in EVASION_KEYWORD_KINDS:
        return kw
    land = kw.removesuffix("walk")
    if land != kw and (
        land.endswith("land") or any(land.endswith(t) for t in LAND_SUBTYPE_WORDS)
    ):
        return "landwalk"
    return None


def _evasion_mode_kinds(sdef: TypedMirrorNode) -> list[str | None]:
    """The evasion kinds one static def confers: its own blocking-restriction
    mode, an ``AddStaticMode`` of one, and every evasion keyword it adds."""
    out: list[str | None] = []
    mode = static_mode_tag(sdef)
    if mode in _EVASION_MODE_KINDS:
        out.append(_EVASION_MODE_KINDS[mode])
    for mod in list_field(sdef, "modifications"):
        tag = tag_of(mod)
        if tag == "AddStaticMode":
            added = static_mode_tag(mod)
            if added in _EVASION_MODE_KINDS:
                out.append(_EVASION_MODE_KINDS[added])
        elif tag == "AddKeyword":
            kind = evasion_keyword_kind(mod_keyword_name(mod) or "")
            if kind is not None:
                out.append(kind)
    return out


def is_creature_population(affected: object) -> bool:
    """Whether a static def's ``affected`` set (a filter node, or a corrected tag
    string — :func:`static_affected`) is a population of creatures rather than
    one: none of :data:`_ONE_CREATURE_AFFECTED`, and not the object an Equipment
    or Aura is attached to (:func:`names_attached_object`)."""
    tag = affected if isinstance(affected, str) else tag_of(affected)
    return tag not in _ONE_CREATURE_AFFECTED and not names_attached_object(affected)


def _gating_condition(node: object) -> bool:
    cond = getattr(node, "condition", MISSING)
    return _present(cond) and tag_of(cond) not in _ATTACK_TURN_CONDITIONS


def evasion_sites(tree: ConceptTree) -> tuple[EvasionSite, ...]:
    """Every evasion the card carries or grants (CR 509.1b), read off phase's
    tree: its printed evasion keywords (``card_keywords``), every
    blocking-restriction or evasion-keyword static def at any depth — a
    printed static, a one-shot or activated "can't be blocked this turn", a
    token's own static —, the evasion keywords a created token or token copy
    is made with, and a keyword counter put on one creature (CR 122.1b).

    Each site says who gets it (one creature, or a population) and whether a
    condition gates it: the def's own ``condition`` (Relic Runner, Rayami), a
    trigger's intervening-if (Rapid Augmenter), or a coin flip / die roll.
    The ``evasion_self`` lane turns these into one subject per kind."""
    sites: list[EvasionSite] = [
        EvasionSite(kind, team=False, conditional=False)
        for name in tree.card_keywords
        if (kind := evasion_keyword_kind(name)) is not None
    ]
    for unit in tree.units:
        nodes = list(unit.iter_typed())
        chance: set[int] = set()
        for n in nodes:
            if tag_of(n) in _CHANCE_TAGS:
                chance.update(id(x) for x in iter_typed_nodes(n) if x is not n)
        unit_gated = unit.origin == "trigger" and _gating_condition(unit.node)
        for n in nodes:
            tag = tag_of(n)
            if tag in ("Token", "CopyTokenOf"):
                names = (
                    token_profile_keywords(n)
                    if tag == "Token"
                    else tuple(
                        k if isinstance(k, str) else getattr(k, "key", "")
                        for k in list_field(n, "extra_keywords")
                    )
                )
                gated = unit_gated or id(n) in chance
                sites.extend(
                    EvasionSite(kind, team=False, conditional=gated)
                    for name in names
                    if (kind := evasion_keyword_kind(name)) is not None
                )
                continue
            if tag in ("PutCounter", "PutCounterAll"):
                kind = evasion_keyword_kind(str(getattr(n, "counter_type", "")))
                if kind is not None:
                    gated = unit_gated or id(n) in chance
                    sites.append(
                        EvasionSite(
                            kind, team=tag == "PutCounterAll", conditional=gated
                        )
                    )
                continue
            if tag == "AddStaticMode":
                continue  # read through its owning def
            kinds = _evasion_mode_kinds(n)
            if not kinds:
                continue
            affected = getattr(n, "affected", MISSING)
            # A conferred def with no ``affected`` applies to the object its
            # chain already names ("target creature gets +1/+0 and can't be
            # blocked this turn" — Distortion Strike's Pump target): one
            # creature, unless the chain is a mass effect.
            team = (
                is_creature_population(affected)
                if _present(affected)
                else any(tag_of(x) in ALL_VARIANT_EFFECT_TAGS for x in nodes)
            )
            gated = unit_gated or _gating_condition(n) or id(n) in chance
            sites.extend(
                EvasionSite(kind, team=team, conditional=gated) for kind in kinds
            )
    return tuple(sites)


def makes_lands_type(tree: ConceptTree, land_type: str) -> bool:
    """Whether the card makes lands into ``land_type`` (CR 305.7: an effect that
    sets a land's subtype, or adds one "in addition to its other types"): a
    continuous effect over lands — a printed static, an Aura's enchanted land,
    a one-shot on a target land — whose modification is ``SetBasicLandType``
    or ``AddSubtype`` of that type. "Nonbasic lands are Islands" (Harbinger of
    the Seas), "Enchanted land is an Island" (Spreading Seas), "target land
    becomes an Island" (Tide Shaper), "All lands are Islands in addition to
    their other types" (Stormtide Leviathan). A set of the lands you control
    only is left out: it reshapes your mana, not the opponents' board."""
    for unit in tree.units:
        for n in unit.iter_typed():
            affected = getattr(n, "affected", MISSING)
            if not _present(affected):
                continue
            changes = any(
                (
                    tag_of(m) == "SetBasicLandType"
                    and getattr(m, "land_type", None) == land_type
                )
                or (
                    tag_of(m) == "AddSubtype"
                    and getattr(m, "subtype", None) == land_type
                )
                for m in list_field(n, "modifications")
            )
            if not changes:
                continue
            if tag_of(affected) == "ParentTarget" or (
                "Land" in filter_core_types(affected)
                and filter_controller(affected) != "You"
            ):
                return True
    return False


def counts_opponents_land_type(tree: ConceptTree, land_type: str) -> bool:
    """Whether the card rewards OTHER players controlling lands of ``land_type``:
    a count of them that is not limited to your own ("deals damage to each
    opponent equal to the number of Islands that player controls" — Typhoon;
    "five or more Islands on the battlefield" — Harbor Serpent) or a condition
    that an opponent controls one ("as long as an opponent controls an Island"
    — Tide Shaper). A count of your own lands of that type (Spectral Deluge,
    Vedalken Shackles) is a land-density payoff, not one an opponent's land
    of that type feeds."""
    for n in tree.iter_typed():
        tag = tag_of(n)
        if tag == "ObjectCount":
            filt = getattr(n, "filter", None)
            if land_type in filter_subtypes(filt) and filter_controller(filt) != "You":
                return True
        elif tag == "IsPresent":
            filt = getattr(n, "filter", None)
            if (
                land_type in filter_subtypes(filt)
                and filter_controller_side(filt) == "opponents"
            ):
                return True
    return False


#: Effects whose object filter names what the card takes from another player:
#: a revealed hand's pick (Psychic Spear's "You choose a Spirit or Arcane card
#: from it"), beside the answers :func:`answers_its_target` reads.
_TAKES_FROM_FILTER_FIELDS: dict[str, str] = {"RevealHand": "card_filter"}


def names_subtype_payoff(tree: ConceptTree, subtype: str) -> bool:
    """Whether the card rewards objects of spell or card ``subtype`` (CR 205.3k
    — Arcane is a spell type): a filter naming it on a cast trigger, a tutor, a
    recursion or cost reducer (Tallowisp, Eerie Procession, Hana Kami,
    Long-Forgotten Gohei), or a count of such cards in your graveyard (Ire of
    Kaminari's ``ZoneCardCount``). Left out: a filter an effect answers —
    counters, destroys or exiles (Hisoka's Defiance, CR 701.6a) — or takes from
    another player's hand (Psychic Spear), and a trigger watching an opponent's
    spells (Ishi-Ishi, Akki Crackshot): each is a hoser of that subtype."""
    for unit in tree.units:
        if triggering_player_side(unit) == "opponents":
            continue
        nodes = list(unit.iter_typed())
        hosed: set[int] = set()
        for n in nodes:
            if answers_its_target(n):
                hosed.update(
                    id(x) for x in iter_typed_nodes(getattr(n, "target", None))
                )
            field = _TAKES_FROM_FILTER_FIELDS.get(tag_of(n) or "")
            if field is not None:
                hosed.update(id(x) for x in iter_typed_nodes(getattr(n, field, None)))
        for n in nodes:
            if id(n) in hosed:
                continue
            tag = tag_of(n)
            if tag == "Typed" and subtype in filter_subtypes(n):
                return True
            if tag == "ZoneCardCount" and any(
                isinstance(ct, MirrorVariant)
                and ct.key == "Subtype"
                and ct.inner == subtype
                for ct in list_field(n, "card_types")
            ):
                return True
            if tag == "Splice" and getattr(n, "subtype", None) == subtype:
                return True
    return False


# ── end evasion sites, land-type changers, subtype payoffs ──


# ── Trigger reads ──

#: Filter tags naming an object (never a player) — the shapes a trigger's
#: ``valid_target`` / ``valid_card`` / ``valid_source`` take for "that creature",
#: the enchanted / equipped object among them ("When enchanted creature attacks,
#: return it" — Contempt).
_TRIGGER_OBJECT_TAGS: frozenset[str] = OBJECT_FILTER_TAGS | {"AttachedTo"}

#: What an effect's back-reference names (:func:`effect_back_reference`).
BackReferenceKind = Literal["chosen", "event", "self", "linked", "unknown"]

#: The back-reference targets :func:`effect_back_reference` resolves: "it" /
#: "those cards", and a trigger's "it" / "that permanent".
_BACK_REFERENCE_TARGETS: frozenset[str] = frozenset(
    {"ParentTarget", "TrackedSet", "TriggeringSource", "EventTarget"}
)


def filter_names_only_stack_objects(filt: object) -> bool:
    """Whether every object ``filt`` can name is a spell or an ability on the
    stack (CR 112.1: "A spell is a card on the stack"): ``StackSpell`` /
    ``StackAbility``, an ``And`` narrowing one ("target creature spell"), or an
    ``Or`` all of whose arms do. "Target spell or creature" (Unsubstantiate)
    names a permanent too, so it is not."""
    tag = tag_of(filt)
    if tag in ("StackSpell", "StackAbility"):
        return True
    filters = getattr(filt, "filters", None) or ()
    if tag == "And":
        return any(filter_names_only_stack_objects(f) for f in filters)
    if tag == "Or":
        return bool(filters) and all(
            filter_names_only_stack_objects(f) for f in filters
        )
    return False


def effect_back_reference(
    unit: AbilityUnit, node: TypedMirrorNode
) -> tuple[BackReferenceKind, object | None] | None:
    """What an effect's back-reference target (``ParentTarget`` "it" / "that
    creature", ``TrackedSet`` "those cards", a trigger's ``TriggeringSource`` /
    ``EventTarget`` — "whenever a creature you control becomes blocked, … return
    it", Cunning Evasion) names, as ``(kind, filter)``, or ``None`` when its
    target is no back-reference:

    * ``("chosen", filt)`` — a target the unit's chain chose earlier, threaded
      by :func:`iter_threaded_target_statics` (Dragon Mask's "Target creature
      you control … Return it", Narset's Reversal's copied spell);
    * ``("event", filt)`` — a trigger's or replacement's event object other
      than the card: the creature it blocks (Kaijin of the Vanishing Touch's
      "return that creature"), the creatures it watches deal damage (Kaito,
      Dancing Shadow's "one of them");
    * ``("self", None)`` — the card itself: a trigger or replacement that
      watches only the card, or a phase trigger with no event object (Cactuar's
      "return it to its owner's hand" at your end step);
    * ``("linked", None)`` — a ``TrackedSet`` no target of the unit fills: the
      cards another of the card's abilities set aside (Tidehollow Sculler's
      "return the exiled card"; CR 607.2a: "The second ability refers only to
      cards in the exile zone that were put there as a result of an
      instruction to exile them in the first ability");
    * ``("unknown", None)`` — an ability whose chain chose nothing the thread
      follows (Decoy Gambit's per-opponent choice)."""
    target = getattr(node, "target", None)
    tag = tag_of(target) or ""
    if tag not in _BACK_REFERENCE_TARGETS:
        return None
    if tag in ("ParentTarget", "TrackedSet"):
        for tracked, eff in iter_threaded_target_statics(
            unit.node, affected_tag=tag, effect_tags=frozenset({tag_of(node) or ""})
        ):
            if eff is node:
                return "chosen", tracked
    if tag == "TrackedSet":
        return "linked", None
    if unit.origin not in ("trigger", "replacement"):
        return "unknown", None
    # The watched object first, then a damage trigger's source, then the object
    # the card's own event touches ("Whenever this creature blocks a creature").
    for field in ("valid_card", "valid_source", "valid_target"):
        watched = getattr(unit.node, field, None)
        if tag_of(watched) in _TRIGGER_OBJECT_TAGS:
            return "event", watched
    return "self", None


# ── Board-keyword reads ──

#: The aggregate functions a board-power threshold compares: the total power
#: ("creatures you control have total power 10 or greater" — Mosswort Bridge)
#: or the greatest power of the population.
_BOARD_POWER_FUNCTIONS: frozenset[str] = frozenset({"Sum", "Max"})


def _your_board_power(qty: object) -> bool:
    """Whether ``qty`` is the total or greatest power of YOUR creatures on the
    battlefield, or of the creatures a batched trigger watches (pack tactics'
    "you attacked with creatures with total power 6 or greater this combat"
    is a ``Sum`` over the ``TriggeringBatch`` — the attackers you declared)."""
    if tag_of(qty) not in AGGREGATE_QTY_TAGS:
        return False
    if getattr(qty, "property", None) != "Power":
        return False
    if getattr(qty, "function", None) not in _BOARD_POWER_FUNCTIONS:
        return False
    source = getattr(qty, "source", MISSING)
    if tag_of(source) == "TrackedSet":
        return getattr(source, "set", None) == "TriggeringBatch"
    filt = aggregate_filter(qty)
    return (
        filt is not None
        and filter_controller(filt) == "You"
        and "Graveyard" not in filter_inzone_zones(filt)
    )


def quantity_threshold(
    root: object, lhs_pred: Callable[[object], bool], floor: int | None = None
) -> bool:
    """True when a condition under ``root`` asks that a quantity reach a fixed
    floor: a trigger's intervening ``QuantityComparison`` or an ability's
    ``QuantityCheck`` comparing ``GE`` / ``GT`` an ``lhs`` that passes
    ``lhs_pred`` against a ``Fixed`` value — of at least ``floor`` when one is
    given. A quantity compared against another variable is a scaler, not a
    threshold."""
    for n in _iter_typed_nodes(root):
        if tag_of(n) not in ("QuantityComparison", "QuantityCheck"):
            continue
        if getattr(n, "comparator", None) not in ("GE", "GT"):
            continue
        rhs = getattr(n, "rhs", None)
        if tag_of(rhs) != "Fixed":
            continue
        if floor is not None:
            value = getattr(rhs, "value", None)
            if not isinstance(value, int) or value < floor:
                continue
        if lhs_pred(getattr(n, "lhs", None)):
            return True
    return False


def _is_your_board_power_ref(lhs: object) -> bool:
    return tag_of(lhs) == "Ref" and _your_board_power(getattr(lhs, "qty", None))


def board_power_threshold(root: object) -> bool:
    """True when a condition under ``root`` asks that the total or greatest
    power of your creatures reach a fixed floor (:func:`quantity_threshold`
    over a :func:`_your_board_power` aggregate). Pack tactics (Gnoll Hunter,
    Werewolf Pack Leader — an ability word, CR 207.2c), Owlbear Shepherd's
    end-step draw and Mosswort Bridge's hideaway gate. An aggregate compared
    against another variable (Vulpine Harvester's "mana value … less than or
    equal to their total power") is a scaler, not a threshold, and an
    aggregate over a graveyard (Carrion Grub) is not your board."""
    return quantity_threshold(root, _is_your_board_power_ref)


# ── Removal reads ──

#: A filter's colour predicates (CR 105.2): ``"has"`` for one naming objects of
#: a colour ("black creatures"), ``"not"`` for one naming objects that lack it
#: ("nonblack creatures"), ``"chosen"`` for one naming objects of a colour chosen
#: as the card resolves or enters ("permanents of the color of your choice" —
#: Wash Out; "creatures of the chosen color" — Gauntlet of Power).
ColorPredicate = Literal["has", "not", "chosen"]

_COLOR_PREDICATE_TAGS: dict[str, ColorPredicate] = {
    "HasColor": "has",
    "NotColor": "not",
    "IsChosenColor": "chosen",
}


def filter_color_predicates(filt: object) -> frozenset[ColorPredicate]:
    """The colour predicates a filter names anywhere inside it — a ``Typed``
    filter's own ``HasColor`` / ``NotColor`` / ``IsChosenColor`` properties and
    those of every ``And`` / ``Or`` member ("target green or white creature" —
    Deathmark). A filter naming no colour is empty."""
    return frozenset(
        _COLOR_PREDICATE_TAGS[t]
        for n in iter_typed_nodes(filt)
        if (t := tag_of(n)) in _COLOR_PREDICATE_TAGS
    )


#: The mass effects (CR 115.10's untargeted "each" / "all") that act on every
#: object their filter matches: destroy, exile or tuck, bounce, damage and a P/T
#: change. Unlike :data:`MASS_EFFECT_TAGS` (who a mass effect reaches, players
#: included), every member here moves or changes the objects its filter names, so
#: the filter alone decides what is hit.
MASS_FILTER_EFFECT_TAGS: frozenset[str] = frozenset(
    {"DestroyAll", "ChangeZoneAll", "BounceAll", "DamageAll", "PumpAll"}
)


class ColorKeyedSite(NamedTuple):
    """One place a card keys on colour (CR 105.2: an object's colour is a
    characteristic an effect can check): an ``"effect"`` whose object filter names
    a colour (``node`` is its :class:`ConceptNode`) or a ``"static"`` whose
    ``affected`` filter does (``node`` is the static def), on ``unit``. ``colors``
    is the filter's :func:`filter_color_predicates`."""

    unit: AbilityUnit
    kind: Literal["effect", "static"]
    node: Any
    filter: object
    colors: frozenset[ColorPredicate]


def color_keyed_sites(tree: ConceptTree) -> Iterator[ColorKeyedSite]:
    """Every effect and continuous effect of TREE's own abilities whose object
    filter names a colour (:class:`ColorKeyedSite`) — Perish's "destroy all green
    creatures", Light of Day's "Black creatures can't attack or block", Bad
    Moon's "Black creatures get +1/+1". The caller decides which sites it wants
    (a hoser's answer or restriction, a colour changer's mass payoff); an ability
    a card grants is not walked."""
    for unit in tree.units:
        for c in unit.effects:
            filt = effect_filter(c.node)
            colors = filter_color_predicates(filt)
            if colors:
                yield ColorKeyedSite(unit, "effect", c, filt, colors)
        for sdef in iter_static_defs(unit.node):
            affected = getattr(sdef, "affected", None)
            colors = filter_color_predicates(affected)
            if colors:
                yield ColorKeyedSite(unit, "static", sdef, affected, colors)


#: The spell properties of a cast trigger that make it watch a TARGETING spell:
#: "a spell that targets …" and "a spell that targets only …".
_TARGETS_PROPERTY_TAGS: frozenset[str] = frozenset({"Targets", "TargetsOnly"})

TargetingSide = Literal["you", "opponents", "any"]


def _object_side(filt: object) -> TargetingSide:
    """Whose object a filter names: the card itself or one you control is
    ``you``, an opponent's ``opponents``, anyone's ``any``."""
    if tag_of(filt) == "SelfRef":
        return "you"
    side = filter_controller_side(filt)
    return side if side in ("you", "opponents") else "any"


def _source_side(filt: object) -> TargetingSide:
    """Whose spell or ability a becomes-target trigger's source filter names."""
    sides = {
        _object_side(n)
        for n in iter_typed_nodes(filt)
        if tag_of(n) == "Typed" and getattr(n, "controller", None)
    }
    if "opponents" in sides:
        return "opponents"
    return "you" if sides == {"you"} else "any"


def targeting_trigger_side(trig: TypedMirrorNode) -> TargetingSide | None:
    """Whose targeting a trigger rewards, or ``None`` when it doesn't watch a
    target being chosen (CR 115.1: targets are chosen as a spell or ability is
    put on the stack):

    * ``"you"`` — your spell targets the card itself or your own permanent: a
      cast trigger (heroic's "a spell that targets this creature", Feather's "an
      instant or sorcery spell that targets a creature you control", Zada's
      "targets only Zada") or a becomes-target trigger on your object whose
      source is yours (valiant's "a spell or ability you control");
    * ``"opponents"`` — the target is an opponent's permanent (Legolas, Master
      Archer's second trigger, Willbreaker), or an opponent's spell or ability
      does the targeting (Reparations, Frost Titan);
    * ``"any"`` — either side (repartee's "targets a creature", Phantasmal
      Bear's "a spell or ability")."""
    mode = getattr(trig, "mode", None)
    if mode == "BecomesTarget":
        watched = _object_side(getattr(trig, "valid_card", None))
        source = _source_side(getattr(trig, "valid_source", None))
        if "opponents" in (watched, source):
            return "opponents"
        return "you" if watched == "you" and source == "you" else "any"
    if mode != "SpellCast":
        return None
    sides = {
        _object_side(getattr(n, "filter", None))
        for n in iter_typed_nodes(getattr(trig, "valid_card", None))
        if tag_of(n) in _TARGETS_PROPERTY_TAGS
    }
    if not sides:
        return None
    if trigger_scope(trig) == "opponents" or "opponents" in sides:
        return "opponents"
    return "you" if sides == {"you"} else "any"


# ── Protection reads ──
# The feeder reads behind four payoff lanes whose serves named cards no lane
# read: the players a "can't lose the game" static protects (Platinum Angel,
# Angel's Grace), your commander put into your hand from the command zone
# (Command Beacon), a static that stops entering creatures from triggering
# abilities (Torpor Orb), a spell whose number of targets is variable (Aurelia's
# Fury, Distorting Wake), and a {0} activation that targets your own creature
# (the en-Kor cycle, Shuko's equip {0}).

#: The player sets a player-affecting static mode names, by side: phase writes
#: "you" as ``Controller`` or a ``Typed`` filter whose controller is ``You``,
#: "your opponents" as ``Opponent``, and "players" as ``Player``. A ``Typed``
#: player filter with no controller and no type reads as every player
#: (``"each"``): Cloudsteel Kirin's quoted "You can't lose the game" granted to
#: the equipped creature is one phase leaves unscoped.
StaticPlayerSide = Literal["you", "opponents", "chosen", "each"]


def _player_static_side(sdef: object) -> StaticPlayerSide | None:
    affected = getattr(sdef, "affected", None)
    atag = tag_of(affected)
    if atag == "Typed":
        side = filter_controller_side(affected)
        if side is not None:
            return side
        if filter_controller(affected) is None and not filter_core_types(affected):
            return "each"
        return None
    if atag == "Player":
        return "each"  # a static chooses no player: its "players" are all of them
    scope = _scope_from_player_node(affected)
    return scope if scope in ("you", "opponents", "each") else None


def static_mode_player_sides(
    tree: ConceptTree, *modes: str
) -> frozenset[StaticPlayerSide]:
    """The sides of the players a player-affecting static of one of ``modes``
    applies to (:data:`StaticPlayerSide`), wherever the card carries it: a
    permanent's own static (Platinum Angel's ``CantLoseTheGame``), one a spell
    confers for a duration (Angel's Grace, Everybody Lives!), an emblem's
    (Gideon of the Trials), and one granted inside another ability (The Book of
    Exalted Deeds' "It gains 'You can't lose the game …'" — a
    ``GrantStaticAbility`` definition, which only :func:`iter_static_defs`'s
    ``granted`` walk descends). ``CantLoseTheGame`` for you is the can't-lose
    read (``life_payment_insurance|you|cant_lose``)."""
    wanted = set(modes)
    out: set[StaticPlayerSide] = set()
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node, granted=True):
            if static_mode_tag(sdef) not in wanted:
                continue
            side = _player_static_side(sdef)
            if side is not None:
                out.add(side)
    return frozenset(out)


def puts_commander_into_hand(tree: ConceptTree) -> bool:
    """Whether the card puts your commander into your hand from the command
    zone (Command Beacon, Netherborn Altar, Road of Return's second mode,
    Campfire): a ``ChangeZone`` / ``ChangeZoneAll`` to ``Hand`` whose filter
    names a commander (``IsCommander``) and whose origin is the command zone —
    the node's ``origin``, or an ``InZone: Command`` on the filter (Campfire's
    "from the command zone and from your graveyard", which phase writes with a
    graveyard origin). A commander put onto the battlefield from the command
    zone (Derevi, Hellkite Courser) is not cast, so it is not this read."""
    for node in tree.iter_typed():
        if tag_of(node) not in ("ChangeZone", "ChangeZoneAll"):
            continue
        if getattr(node, "destination", None) != "Hand":
            continue
        filt = getattr(node, "target", None)
        if "IsCommander" not in filter_predicates(filt):
            continue
        if getattr(node, "origin", None) == "Command" or "Command" in (
            filter_inzone_zones(filt)
        ):
            return True
    return False


def silences_own_enter_triggers(tree: ConceptTree) -> bool:
    """Whether a static stops creatures entering the battlefield from triggering
    YOUR permanents' abilities: a ``SuppressTriggers`` mode over the
    ``EntersBattlefield`` event whose source filter admits creatures (Torpor
    Orb, Hushwing Gryff, Hushbringer; Karn, Argent Defender's "artifacts and
    creatures") and whose trigger-source filter does not limit it to an
    opponent's permanents (Elesh Norn, Mother of Machines silences only theirs).
    """
    for unit in tree.units:
        for sdef in unit.static_defs():
            if static_mode_tag(sdef) != "SuppressTriggers":
                continue
            events = static_mode_field(sdef, "events")
            if (
                not isinstance(events, (list, tuple))
                or "EntersBattlefield" not in events
            ):
                continue
            source = static_mode_field(sdef, "source_filter")
            types = set(filter_core_types(source))
            if types and not types & {"Creature", "Permanent"}:
                continue
            owner = static_mode_field(sdef, "trigger_source_filter")
            if filter_controller_side(owner) == "opponents":
                continue
            return True
    return False


def _fixed_count(qty: object) -> int | None:
    if isinstance(qty, int):
        return qty
    if tag_of(qty) == "Fixed":
        value = getattr(qty, "value", None)
        return value if isinstance(value, int) else None
    return None


#: Effects whose count is a choice made without targeting: "each player
#: chooses any number of creatures …, then sacrifices the rest" (Destined
#: Confrontation, Slaughter the Strong).
_CHOSEN_NOT_TARGETED_EFFECTS = frozenset({"ChooseAndSacrificeRest"})
#: An effect over the objects an earlier clause named ("exile any number of
#: those cards" — Dimir Machinations) picks among them; it targets nothing.
_TRACKED_SET_TAGS = frozenset({"TrackedSet", "TrackedSetFiltered"})


def has_variable_target_count(node: object) -> bool:
    """Whether one ability node's targets are a VARIABLE number of two or more
    (CR 601.2c: "If the spell has a variable number of targets, the player
    announces how many targets they will choose"): phase's ``multi_target``
    range with no maximum ("any number of target creatures" — Descent of the
    Dragons), a maximum or minimum that is a quantity ("X target nonland
    permanents" — Distorting Wake), or a fixed range of two or more ("one, two,
    or three targets" — Flames of the Firebrand; "up to two target creatures").
    A division among targets (CR 601.2d — Aurelia's Fury) rides the same range.
    A fixed count ("two target creatures") and "up to one" are not variable,
    and neither is a count chosen without targeting — phase puts the same
    range on "untap up to three lands" (Frantic Search) and "return any number
    of Plains you control" (Plow Through Reito), marking the choice as made on
    resolution (``target_choice_timing`` on the ability, ``selection`` on the
    effect), and a choice among the objects an earlier clause named or a
    choose-then-sacrifice is no target either."""
    rng = getattr(node, "multi_target", MISSING)
    if not isinstance(rng, TypedMirrorNode):
        return False
    effect = getattr(node, "effect", None)
    if (
        getattr(node, "target_choice_timing", None) == "Resolution"
        or getattr(effect, "selection", None) == "at_resolution"
        or tag_of(effect) in _CHOSEN_NOT_TARGETED_EFFECTS
        or tag_of(getattr(effect, "target", None)) in _TRACKED_SET_TAGS
    ):
        return False
    hi = getattr(rng, "max", None)
    lo = getattr(rng, "min", None)
    if hi is None:
        return True
    hi_n, lo_n = _fixed_count(hi), _fixed_count(lo)
    if hi_n is None or (lo is not None and lo_n is None):
        return True
    return hi_n >= 2 and (lo_n or 0) < hi_n


def spell_has_variable_target_count(tree: ConceptTree) -> bool:
    """Whether an instant or sorcery's own spell ability targets a variable
    number of objects or players (:func:`has_variable_target_count`), a later
    sentence or a mode of it included. A permanent's triggered or activated
    ability is not a spell, so a "cost {1} less for each target" spell
    discount (Hinata, Dawn-Crowned) never reaches it."""
    if not (tree.is_type("Instant") or tree.is_type("Sorcery")):
        return False
    return any(
        unit.origin == "ability"
        and getattr(unit.node, "kind", None) == "Spell"
        and any(has_variable_target_count(n) for n in unit.iter_typed())
        for unit in tree.units
    )


def _zero_mana_cost(cost: object) -> bool:
    if tag_of(cost) == "Mana":
        mana = getattr(cost, "cost", None)
        # {X} counts 0 toward mana value (CR 202.3e) but is no free activation.
        return cost_mana_value(mana) == 0 and not getattr(mana, "shards", None)
    parts = getattr(cost, "costs", MISSING)
    if tag_of(cost) == "Composite" and isinstance(parts, list) and parts:
        return all(_zero_mana_cost(p) for p in parts)
    return False


def targets_own_creature(effect: object, unit: AbilityUnit | None = None) -> bool:
    """Whether ``effect`` targets a creature or permanent you control on the
    battlefield — never a mass ``*All`` effect, never a card in a graveyard or
    hand. Given the effect's ``unit``, the overlay-corrected controller reads
    (:func:`filter_controller`)."""
    if not _single_effect(effect):
        return False
    chosen = tag_of(getattr(effect, "redirect_to", None)) == "ChosenTarget"
    for field in ("target", "redirect_object_filter") if chosen else ("target",):
        filt = getattr(effect, field, None)
        if tag_of(filt) != "Typed" or filter_controller(filt, unit) != "You":
            continue
        # A card in a graveyard or hand is no creature you control (CR 110.1).
        if set(filter_inzone_zones(filt)) - {"Battlefield"}:
            continue
        if set(filter_core_types(filt)) & {"Creature", "Permanent"}:
            return True
    return False


class QuantityReferent(NamedTuple):
    """The object a size quantity (a ``Ref`` of ``Power``, ``Toughness``, …)
    reads off, resolved from phase's ``scope`` tag by :func:`quantity_referent`.

    ``kind`` is ``"self"`` (the card itself: ``Source``, or an ``Anaphoric``
    "its" with no earlier object in the ability), ``"target"`` (an object an
    earlier effect of the ability targets: ``Target``, or an ``Anaphoric`` "it"
    back to it — Chandra's Ignition, Nibelheim Aflame, Delirium), ``"that"`` (the
    object an earlier effect acts on: ``Demonstrative``, Rupture's "that
    creature's power" after its sacrifice), ``"cost"`` (an object paid as a cost
    — Fling), ``"event"`` (the triggering event's object — Warstorm Surge),
    ``"batch"`` (each source of a batch — Moonlight Hunt), else ``"other"``.
    ``scope`` is phase's tag and ``effect`` the earlier effect naming the
    object, for ``"target"`` and ``"that"`` when the ability holds one."""

    kind: str
    scope: str | None
    effect: ConceptNode | None


_REFERENT_KINDS: dict[str, str] = {
    "Source": "self",
    "CostPaidObject": "cost",
    "EventSource": "event",
    "BatchSource": "batch",
}


def _single_effect(node: object) -> bool:
    """Whether ``node`` is an effect on one object, never a mass ``*All`` one."""
    tag = tag_of(node)
    return tag is not None and not tag.endswith("All")


def _targets_one(node: object) -> bool:
    """Whether an effect targets a single object (a ``Typed`` filter)."""
    return _single_effect(node) and tag_of(getattr(node, "target", None)) == "Typed"


def quantity_referent(
    qty: object, unit: AbilityUnit | None = None, *, holder: object = None
) -> QuantityReferent:
    """Which object a size quantity reads off (:class:`QuantityReferent`): its
    ``scope`` tag, with a ``Target`` / ``Anaphoric`` / ``Demonstrative`` resolved
    to the earlier effect of ``unit`` that names the object — the first effect
    before ``holder`` (the effect the quantity sits in; every effect when it is
    not given) that targets one object, or for a ``Demonstrative`` also one that
    sacrifices."""
    scope = tag_of(getattr(qty, "scope", None))
    kind = _REFERENT_KINDS.get(scope or "")
    if kind is not None:
        return QuantityReferent(kind, scope, None)
    if scope not in ("Target", "Anaphoric", "Demonstrative"):
        return QuantityReferent("other", scope, None)
    named = "that" if scope == "Demonstrative" else "target"
    for c in unit.effects if unit is not None else ():
        if c.node is holder:
            break  # only an effect before the quantity's own names its object
        if _targets_one(c.node) or (
            scope == "Demonstrative" and c.concept == "sacrifice"
        ):
            return QuantityReferent(named, scope, c)
    return QuantityReferent("self" if scope == "Anaphoric" else named, scope, None)


def picked_by_caster(
    qty: object,
    unit: AbilityUnit,
    holder: object,
    *,
    sacrifice_actor: Callable[[AbilityUnit, TypedMirrorNode], str | None],
) -> bool:
    """Whether the caster picks the object a size quantity reads off
    (:func:`quantity_referent`): one paid as a cost; a target among the creatures
    they control, or "it" back to one (:func:`targets_own_creature` — Chandra's
    Ignition's "Target creature you control deals damage equal to its power",
    Nibelheim Aflame, Nova Flame): the target is chosen as the spell is put on
    the stack (CR 115.1) and its size read as it resolves (Chandra's Ignition's
    ruling); or "that creature" a sacrifice in the ability's own instructions
    takes (Rupture's "Sacrifice a creature"), when you are the one sacrificing:
    a player sacrifices only a permanent they control (CR 701.21a), and an
    instruction that names no player is the controller's to follow (CR 608.2c).
    ``sacrifice_actor`` is the lanes' actor read
    (``lanes._shared.sacrifice_actor_scope``, ``None`` for you), which every
    caller passes, so one card gets one answer."""
    ref = quantity_referent(qty, unit, holder=holder)
    if ref.kind == "cost":
        return True
    if ref.effect is None:
        return False
    if ref.kind == "target":
        return targets_own_creature(ref.effect.node, unit)
    if ref.kind != "that" or ref.effect.concept != "sacrifice":
        return False
    return sacrifice_actor(unit, ref.effect.node) is None


def deals_its_own_power(node: TypedMirrorNode, unit: AbilityUnit | None = None) -> bool:
    """Whether a damage effect deals damage equal to its dealer's own power ("deals
    damage equal to its power"): a ``Power``
    amount, bare or multiplied, read off the object that deals the damage — the
    card itself when no other object deals it (``damage_source`` unset), a
    target that deals it (``damage_source`` ``Target`` / ``EachTarget``: Ram
    Through, Chandra's Ignition), the triggering object (Warstorm Surge), each
    source of a batch (Moonlight Hunt), or an ``Anaphoric`` "its", the pronoun's
    own subject (Delirium's "That creature deals damage equal to its power",
    where phase drops the dealer). Never another object's power: a cost's (Fling)
    or the one an earlier effect sacrificed (Rupture)."""
    qty = count_operand_qty(node, fields=("amount",))
    if tag_of(qty) != "Power":
        return False
    ref = quantity_referent(qty, unit, holder=node)
    dealer = getattr(node, "damage_source", None)
    dealer = dealer if isinstance(dealer, str) else None
    if ref.kind == "self":
        return dealer is None or ref.scope == "Anaphoric"
    if ref.kind == "target":
        return ref.scope == "Anaphoric" or dealer in ("Target", "EachTarget")
    if ref.kind == "event":
        return dealer in (None, "TriggeringSource")
    return ref.kind == "batch"


def is_bite(node: TypedMirrorNode, unit: AbilityUnit) -> bool:
    """Whether a power-sized damage effect (:func:`iter_power_damage`) is a bite:
    a creature of yours deals damage equal to its own power to another object
    ("Target creature you control deals damage equal to its power to target
    creature you don't control" — Bite Down, Rocky Rebuke, Sylvan Smite's "that
    creature", Polliwallop's twice its power; Band Together's two biters; Abyssal
    Hunter, the card itself). The dealer is the creature, not the spell (Bite
    Down's ruling: "the creature you control won't deal damage"), so whatever
    the dealer has — deathtouch above all (CR 702.2b) — applies to the damage.

    Never a dealer an opponent controls (Mutiny), one dealing damage to itself
    (Repentance, Solar Blaze: a ``ParentTarget`` recipient of the targeted
    dealer), another object's power (Fling's cost, Dead Reckoning's card), nor a
    triggering or batch dealer, whose side this read doesn't place. The caller
    judges the recipient (a creature, not a player)."""
    if tag_of(node) in POWER_DAMAGE_TAGS:
        return filter_controller_side(getattr(node, "sources", None)) == "you"
    if not deals_its_own_power(node, unit):
        return False
    qty = count_operand_qty(node, fields=("amount",))
    ref = quantity_referent(qty, unit, holder=node)
    if ref.kind == "self":
        return True
    if ref.kind != "target" or ref.effect is None:
        return False
    if tag_of(damage_recipient(node)) == "ParentTarget":
        return False
    dealer = getattr(ref.effect.node, "target", None)
    return filter_controller_side(dealer) == "you"


def free_own_target_activations(tree: ConceptTree) -> bool:
    """Whether the card has (or grants) an activated ability that costs {0} and
    targets a creature or permanent you control — a free, repeatable way to
    target your own creature: the en-Kor cycle's "{0}: The next 1 damage … is
    dealt to target creature you control instead", equip {0} (Shuko, Lightning
    Greaves; CR 702.6a: "Attach to target creature you control"), and equip {0}
    granted to your Equipment (Puresteel Paladin's metalcraft) or to a token
    (Nahiri, the Lithomancer's Stoneforged Blade). A cost with any other part
    (tapping, sacrificing) or an {X} is not free. Equip is an ability of
    Equipment (CR 702.6a), so an equip ability on the card itself counts only
    when the card is an Equipment: phase writes Auriok Steelshaper's "Equip
    costs you pay cost {1} less" as an equip {0} of its own."""
    equipment = "Equipment" in tree.card_subtypes
    for unit in tree.units:
        for node in unit.iter_typed():
            if getattr(node, "kind", None) != "Activated":
                continue
            if (
                node is unit.node
                and not equipment
                and tag_of(getattr(node, "ability_tag", None)) == "Equip"
            ):
                continue
            if not _zero_mana_cost(getattr(node, "cost", None)):
                continue
            if targets_own_creature(getattr(node, "effect", None)):
                return True
    return False


# ── Stax reads ──

#: The modifications that SET power / toughness to a computed value — a
#: characteristic-defining */* (CR 604.3), in both phase spellings: Maro's
#: ``SetDynamicPower`` pair, Titania's Song's ``SetPowerDynamic`` pair.
DYNAMIC_PT_SET_MODS: frozenset[str] = frozenset(
    {
        "SetDynamicPower",
        "SetDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
    }
)
#: Every dynamic P/T modification: the setting pair plus the computed bonus
#: ("+1/+1 for each card in your hand" — Empyrial Armor).
DYNAMIC_PT_MODS: frozenset[str] = DYNAMIC_PT_SET_MODS | {
    "AddDynamicPower",
    "AddDynamicToughness",
}


def dynamic_pt_mod_sites(
    root: object, *, setting_only: bool = False
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    """The ``(static_def, modification)`` pairs (:func:`iter_mod_sites`) under
    ``root`` whose modification is a dynamic P/T one (:data:`DYNAMIC_PT_MODS`,
    or only the setting pair with ``setting_only``)."""
    mods = DYNAMIC_PT_SET_MODS if setting_only else DYNAMIC_PT_MODS
    for sdef, mod in iter_mod_sites(root):
        if tag_of(mod) in mods:
            yield sdef, mod


def hand_count_scopes(root: object) -> tuple[str, ...]:
    """:func:`hand_size_scopes` widened to the ``ZoneCardCount{zone: Hand}``
    qty phase writes for "for each card in your hand" (Empyrial Armor's
    dynamic pump, Spontaneous Generation's token count, Gerrard's Wisdom's
    life gain), whose player is a bare ``scope`` string: ``"you"`` for your
    own hand, ``"opponents"`` / ``"any"`` otherwise. CR 402.1 (a player's
    hand)."""
    out = list(hand_size_scopes(root))
    for n in _iter_typed_nodes(root):
        if tag_of(n) != "ZoneCardCount" or getattr(n, "zone", None) != "Hand":
            continue
        scope = getattr(n, "scope", None)
        if not _present(scope):
            out.append("you")
        else:
            out.append(_scope_from_player_tag(scope) or "any")
    return tuple(out)


def own_hand_signs(operand: object, sign: int = 1) -> frozenset[int]:
    """The directions your own hand count moves an operand: ``1`` where a
    bigger hand makes it bigger, ``-1`` under a negative ``Multiply`` or a
    ``Subtract`` ("minus the number of cards in your hand" — Dark
    Suspicions, Mr. Foxglove; a die roll's "subtract", The Deck of Many
    Things), and both under a ``Difference`` (Damia's refill to seven, which
    shrinks as the hand grows toward it). Empty when the operand never reads
    your hand. CR 402.1 (a player's hand)."""
    tag = tag_of(operand)
    if tag == "Multiply":
        factor = getattr(operand, "factor", None)
        flip = -1 if isinstance(factor, int) and factor < 0 else 1
        return own_hand_signs(getattr(operand, "inner", None), sign * flip)
    if tag == "Subtract":
        return own_hand_signs(getattr(operand, "value", None), -sign)
    if tag == "Sum":
        out: frozenset[int] = frozenset()
        for expr in getattr(operand, "exprs", None) or ():
            out |= own_hand_signs(expr, sign)
        return out
    if tag == "Difference":
        if own_hand_signs(getattr(operand, "left", None)) or own_hand_signs(
            getattr(operand, "right", None)
        ):
            return frozenset({1, -1})
        return frozenset()
    if tag in ("Quantity", "Add"):
        return own_hand_signs(getattr(operand, "value", None), sign)
    if tag == "Offset":
        return own_hand_signs(getattr(operand, "inner", None), sign)
    if isinstance(operand, list):
        out = frozenset()
        for item in operand:
            out |= own_hand_signs(item, sign)
        return out
    if operand is None or "you" not in hand_count_scopes(operand):
        return frozenset()
    return frozenset({sign})


#: The modifications a pure color change may carry beside its color mods: a
#: keyword rider (the -Wisps cycle's haste). Any other modification makes the
#: color a rider on an animation or a reanimation ("is a black Zombie in
#: addition", "becomes a 0/4 Wall").
_COLOR_CHANGE_RIDER_MODS: frozenset[str] = frozenset({"AddKeyword", "RemoveKeyword"})


def _substitution_domains(mod: object) -> tuple[str, ...]:
    """The word domains a ``SubstituteTextWord`` lets you swap (``ColorWord``,
    ``BasicLandType``, ``CreatureType``)."""
    data = getattr(getattr(mod, "substitution", None), "data", None)
    if isinstance(data, MirrorVariant) and data.key == "domains":
        inner = data.inner
        if isinstance(inner, list):
            return tuple(d for d in inner if isinstance(d, str))
    return ()


def color_change_kinds(static_def: object) -> tuple[str, ...]:
    """How one continuous effect changes colors (CR 105.3: "Effects may change
    an object's color"): ``"set"`` (a new color replaces the old — Purelace,
    the -Wisps cycle, Shifting Sky), ``"add"`` ("in addition to its other
    colors" — Painter's Servant, Indigo Faerie) and ``"text"`` (a color word
    swapped in its rules text — Sleight of Mind, Mind Bend). Empty for a
    characteristic-defining color (devoid, CR 604.3), a change to colorless
    (Ancient Kavu — no new color), and a color that is a rider on another
    change (an animation, a base P/T or subtype set —
    :data:`_COLOR_CHANGE_RIDER_MODS`)."""
    if getattr(static_def, "characteristic_defining", None) is True:
        return ()
    kinds: list[str] = []
    for mod in getattr(static_def, "modifications", None) or ():
        tag = tag_of(mod)
        if tag == "SetColor":
            if not getattr(mod, "colors", None):
                return ()
            kinds.append("set")
        elif tag == "AddColor":
            kinds.append("add")
        elif tag == "AddChosenColor":
            kinds.append("set" if getattr(mod, "mode", None) == "Set" else "add")
        elif tag == "SubstituteTextWord":
            if "ColorWord" in _substitution_domains(mod):
                kinds.append("text")
        elif tag not in _COLOR_CHANGE_RIDER_MODS:
            return ()
    return tuple(kinds)


def creature_type_change_kinds(
    static_def: object,
) -> tuple[Literal["chosen", "all"], ...]:
    """How one continuous effect changes its objects' creature types, one entry
    per modification: ``"chosen"`` for the creature type you choose (CR 205.1a:
    a set subtype replaces the old ones) — "Target creature becomes the creature
    type of your choice" (Imagecrafter, Mistform Mutant, Unnatural Selection),
    "Each creature becomes that type" (Standardize); an ``AddChosenSubtype`` with
    no ``RemoveAllSubtypes`` keeps the old types ("in addition", CR 205.1b) and
    counts too — and ``"all"`` for every creature type ("gains all creature
    types" — Amoeboid Changeling; a granted changeling, CR 702.73a — Mirror
    Entity). The caller decides whose creatures it reaches."""
    kinds: list[Literal["chosen", "all"]] = []
    for mod in getattr(static_def, "modifications", None) or ():
        tag = tag_of(mod)
        if tag == "AddChosenSubtype" and getattr(mod, "kind", None) == "CreatureType":
            kinds.append("chosen")
        elif tag == "AddAllCreatureTypes" or (
            tag == "AddKeyword" and mod_keyword_name(mod) == "Changeling"
        ):
            kinds.append("all")
    return tuple(kinds)


def library_search_restriction_side(static_def: object) -> str | None:
    """Whom a library-search restriction binds (CR 701.23a): ``"opponents"`` or
    ``"each"``. ``CantSearchLibrary`` carries the player on ``cause``
    (Stranglehold, Ashiok, Dream Render: opponents; Mindlock Orb: every
    player); ``RestrictLibrarySearchToTop`` on ``who`` (Aven Mindcensor's "if
    an opponent would search a library, that player searches the top four
    cards of that library instead"). ``None`` for any other static."""
    mode = static_mode_tag(static_def)
    if mode == "CantSearchLibrary":
        who = static_mode_field(static_def, "cause")
    elif mode == "RestrictLibrarySearchToTop":
        who = static_mode_field(static_def, "who")
    else:
        return None
    side = _scope_from_player_tag(who)
    return side if side in ("opponents", "each") else None


# ── Voltron and counters reads ──

#: ``Mill`` recipients naming a player other than the effect's controller: the
#: defending player (Nemesis of Reason), the controller of an object an earlier
#: clause chose ("Counter target spell. Its controller mills four cards" —
#: Countermand; Grisly Spectacle), a target player (Millstone, Glimpse the
#: Unthinkable) and a back-reference to one (Demogorgon's Clutches' "Target
#: opponent discards two cards, mills two cards").
_OTHER_PLAYER_MILL_RECIPIENTS: frozenset[str] = PLAYER_BACK_REFERENCES | {
    "DefendingPlayer",
    "ParentTargetController",
    "Player",
}
#: :func:`effect_player_reach` answers that take in another player's library:
#: each opponent, each player (Extract from Darkness), a target player, a
#: per-player loop ("At the beginning of each player's upkeep, that player
#: mills" — Worry Beads).
_OPPONENT_MILL_REACH: frozenset[str] = frozenset(
    {"opponents", "per_opponent", "each", "target", "scoped"}
)


def mill_reaches_opponent(unit: AbilityUnit, node: TypedMirrorNode) -> bool:
    """Whether a ``Mill`` effect ``node`` of ``unit`` can mill a library other
    than its controller's (CR 701.17a: "For a player to mill a number of cards,
    that player puts that many cards from the top of their library into their
    graveyard" — the player named mills, into their own graveyard). phase
    writes most mills Controller-relative, so the recipient alone reads "you";
    the reach is read off the structure around it:

    * the actor :func:`effect_actor_scope` names — an opponent (Maddening
      Cacophony, Mindcrank, Bruvac) or an Aura's enchanted player (Fraying
      Sanity, Curse of the Bloody Tome);
    * the player reach :func:`effect_player_reach` names (each opponent, each
      player, a target player, a per-player loop);
    * the recipient itself (:data:`_OTHER_PLAYER_MILL_RECIPIENTS`), a
      ``Typed`` opponent ("target opponent mills" — Helm of Obedience), or a
      trigger's "that player" unless the trigger watches only you (combat
      damage to a player — Sword of Body and Mind, Captain N'ghathrod).

    A mill whose destination is not the graveyard is no mill (phase labels
    Scroll Rack's library↔hand swap ``Mill``)."""
    if tag_of(node) != "Mill" or getattr(node, "destination", None) != "Graveyard":
        return False
    if effect_actor_scope(unit, node) in ("opponents", ENCHANTED_PLAYER_SCOPE):
        return True
    if effect_player_reach(unit.node, node) in _OPPONENT_MILL_REACH:
        return True
    recipient = recipient_tag(node)
    if recipient in _OTHER_PLAYER_MILL_RECIPIENTS:
        return True
    if recipient == "TriggeringPlayer":
        return triggering_player_side(unit) != "you"
    return filter_controller(getattr(node, "target", None)) == "Opponent"


def blight_placements(unit: AbilityUnit) -> tuple[TypedMirrorNode, ...]:
    """The blight actions of one unit (CR 701.68a: "To 'blight N' means to put
    N -1/-1 counters on a creature you control"): phase's ``BlightEffect``
    anywhere under the unit, a granted ability's included — "each opponent
    blights 1" (High Perfect Morcant) too, whose counters land on that
    player's creature — and a ``Blight`` leaf of a cost the unit's controller
    pays (:func:`controller_paid_cost_leaves`: Gristle Glutton's "{T}, Blight
    1:", Evershrike's Gift's graveyard ability, a spell's merged additional
    cost). phase types neither as the ``PutCounter`` the counter lanes read."""
    out: dict[int, TypedMirrorNode] = {
        id(n): n for n in unit.iter_typed() if tag_of(n) == "BlightEffect"
    }
    for paid in controller_paid_cost_leaves(unit):
        if tag_of(paid.leaf) == "Blight":
            out.setdefault(id(paid.leaf), paid.leaf)
    return tuple(out.values())


def role_tokens_attached(unit: AbilityUnit) -> tuple[TypedMirrorNode, ...]:
    """The Role tokens one unit makes you create attached to a creature (CR
    303.7: "Some Aura enchantments also have the subtype 'Role'"; CR 111.10j-r
    define the predefined Role tokens): a ``Token`` effect whose types name
    ``Role``, with an ``attach_to``, created by you (:func:`token_creator_side`
    — Monstrous Rage, Royal Treatment, Ellivere of the Wild Court). A Role put
    on a creature an opponent controls (a ``Typed`` opponent ``attach_to``) is
    left out. Which Role it is stays the caller's read: the token's ``name``."""
    return tuple(
        n
        for n in unit.iter_typed()
        if tag_of(n) == "Token"
        and "Role" in (getattr(n, "types", None) or ())
        and _present(getattr(n, "attach_to", None))
        and filter_controller(getattr(n, "attach_to", None)) != "Opponent"
        and token_creator_side(unit, n) == "you"
    )


def own_token_filters(unit: AbilityUnit) -> tuple[object, ...]:
    """The filters naming tokens YOU control that one unit cares about beyond
    an anthem's pump and a token-watching trigger (CR 111.1: a token is a
    marker used to represent a permanent that isn't a card) — each a filter
    carrying phase's ``Token`` predicate and controller you:

    * a static's ``affected`` set, whatever it does to them — a granted
      ability ("Tokens you control have '{T}: Add {G}.'" — Jaheira, Friend of
      the Forest; Insidious Roots), a rule change ("The 'legend rule' doesn't
      apply to tokens you control" — Cadric, Soul Kindler), damage prevention
      (Emmara Tandris); a granted static's included (Inspiring Leader);
    * a ``TapCreatures`` leaf of a cost you pay ("Tap two untapped tokens you
      control:" — Baylen, the Haymaker; Hazel of the Rootbloom);
    * a trigger's ``valid_source`` ("Whenever a creature token you control
      deals combat damage to a player" — Curiosity Crafter);
    * a cost reduction's count (:func:`cost_reduction_count_filters` —
      "cost {1} less to cast for each creature token you control", Magnus
      the Red).

    The caller turns each into the payoff signal of the kind it names."""

    def mine(filt: object) -> bool:
        return (
            filt is not None
            and "Token" in filter_predicates(filt)
            and filter_controller(filt) == "You"
        )

    out: list[object] = []
    for sdef in iter_static_defs(unit.node):
        aff = getattr(sdef, "affected", None)
        if mine(aff):
            out.append(aff)
    for paid in controller_paid_cost_leaves(unit):
        if tag_of(paid.leaf) == "TapCreatures":
            filt = getattr(paid.leaf, "filter", None)
            if mine(filt):
                out.append(filt)
    if unit.origin == "trigger":
        src = getattr(unit.node, "valid_source", None)
        if mine(src):
            out.append(src)
    out.extend(f for f in cost_reduction_count_filters(unit.node) if mine(f))
    return tuple(out)


# ── Card-advantage reads ──


#: The steps an added step of the same name re-runs (CR 500.9; an added beginning
#: phase holds an upkeep and a draw step, CR 501.1), whose
#: "at the beginning of …" triggers an extra-step card multiplies: upkeep (CR
#: 503), draw (CR 504) and end (CR 513).
EXTRA_STEP_TRIGGER_PHASES: tuple[str, ...] = ("Upkeep", "Draw", "End")


def own_turn_step_triggers(unit: AbilityUnit) -> frozenset[str]:
    """The steps (:data:`EXTRA_STEP_TRIGGER_PHASES`) at whose beginning a trigger
    the unit carries or grants (:func:`iter_unit_trigger_defs`) fires on your own
    turn — "at the beginning of your upkeep" (Phyrexian Arena), "… of each end
    step" (Wound Reflection), "… of your draw step" (Sylvan Library): a
    ``Phase``-mode trigger (:func:`trigger_phase`) not limited to an opponent's
    turn (:func:`trigger_turn_constraint`). An "each player's [step]" or
    "enchanted player's [step]" trigger whose effect falls on the player whose
    step it is (:func:`_aims_at_step_player` — Braids, Cabal Minion; Howling
    Mine) is left out: it treats every player alike rather than paying you
    off; so is one at a NAMED player's step (:data:`_NAMED_STEP_PLAYERS` — the
    enchanted creature's controller, an enchanted or chosen player: Soul Bleed,
    Curse of Thirst, Black Vise) and a pure drawback an added step makes worse
    (:func:`_only_costs_you` — Ball Lightning's end-step sacrifice, Juzám
    Djinn's ping). Keyword
    upkeep costs (cumulative upkeep, echo) are their own trigger modes, never
    ``Phase``; suspend's time-counter removal is one, and an added upkeep
    speeds it up."""
    steps: set[str] = set()
    for trig in iter_unit_trigger_defs(unit):
        if getattr(trig, "mode", None) != "Phase":
            continue
        step = trigger_phase(trig)
        if step not in EXTRA_STEP_TRIGGER_PHASES:
            continue
        constraint = trigger_turn_constraint(trig)
        if constraint == "OnlyDuringOpponentsTurn":
            continue
        if constraint is None and _aims_at_step_player(trig):
            continue
        if tag_of(getattr(trig, "valid_target", None)) in _NAMED_STEP_PLAYERS:
            continue
        if _only_costs_you(trig):
            continue
        steps.add(step)
    return frozenset(steps)


#: A step trigger's ``valid_target`` that names whose step it watches when that
#: is one player the card points at, not you: the enchanted permanent's
#: controller (Soul Bleed), the enchanted player (Curse of Thirst, Paradox Haze),
#: the chosen player (Black Vise).
_NAMED_STEP_PLAYERS: frozenset[str] = frozenset(
    {"ParentTargetController", "AttachedTo", "SourceChosenPlayer"}
)


#: The moves by which a step trigger takes its own card away — the "at the
#: beginning of the end step, sacrifice / return this" drawback (Ball Lightning,
#: Viashino Sandscout, Arc Runner).
_SELF_LEAVE_TAGS: frozenset[str] = frozenset(
    {"Sacrifice", "Bounce", "ChangeZone", "Destroy", "Exile", "ShuffleIntoLibrary"}
)


def _only_costs_you(trig: TypedMirrorNode) -> bool:
    """Whether a step trigger is a pure drawback — every effect of its chain
    (``execute`` and its ``sub_ability`` links) only costs you
    (:func:`_step_effect_cost`) or is bookkeeping on the card itself, so an
    added step makes it WORSE: the card taking itself away ("sacrifice ~ unless
    you pay" — Masticore; Ball Lightning), damage or life loss to you (Juzám
    Djinn; Force of Nature's "pay {G}{G}{G}{G} or take 8"), sacrificing or
    discarding your own things (Leviathan), handing the card over (Wild Dogs),
    a -1/-1 counter on itself (Magmaroth). A symmetric "each player discards"
    counts as a cost; an "each opponent loses" link is a drain. Any effect
    with an upside — a draw, a token, any other counter it builds up (a
    Thallid's spore, a Shrine's charge, Lotus Blossom's petal), a drain, mana
    — keeps the trigger (Phyrexian Arena, Bitterblossom). A trigger that
    works from the graveyard or exile (:func:`ability_zones`) brings the card
    BACK (Squee, Goblin Nabob; Nether Spirit) and stays."""
    if ability_zones(trig) & {"Graveyard", "Exile"}:
        return False
    kinds: list[str | None] = []
    ability = getattr(trig, "execute", None)
    while isinstance(ability, TypedMirrorNode):
        kind = _step_effect_cost(getattr(ability, "effect", None))
        if tag_of(getattr(ability, "player_scope", None)) == "Opponent":
            kind = None  # "each opponent loses …" is a drain, not a cost
        kinds.append(kind)
        ability = getattr(ability, "sub_ability", None)
    return bool(kinds) and all(kinds) and "cost" in kinds


#: Who an effect's ``target`` names when it hits you: the controller, or no
#: recipient at all (Phyrexian Arena's "lose 1 life" carries none).
_YOU_TARGETS: frozenset[str | None] = frozenset({None, "Controller"})


def _step_effect_cost(e: object) -> str | None:
    """``"cost"`` when an effect only costs you, ``"inert"`` when it is
    bookkeeping on the card itself (a shuffle, tapping or untapping it),
    ``None`` when it may help you."""
    t = tag_of(e)
    tgt = getattr(e, "target", None)
    ttag = tag_of(tgt)
    if t in _SELF_LEAVE_TAGS and ttag == "SelfRef":
        return "cost"
    if t in ("DealDamage", "LoseLife", "PayLife") and ttag in _YOU_TARGETS:
        return "cost"
    if t in ("Sacrifice", "Discard") and (
        ttag in ("SelfRef", "Controller") or filter_controller(tgt) == "You"
    ):
        return "cost"
    if t == "GiveControl" and ttag in (None, "SelfRef"):
        return "cost"
    if t == "Shuffle" or (t == "SetTapState" and ttag == "SelfRef"):
        return "inert"
    if t == "PutCounter" and ttag == "SelfRef":
        return "cost" if getattr(e, "counter_type", None) == "M1M1" else None
    return None


def _aims_at_step_player(trig: TypedMirrorNode) -> bool:
    """Whether a per-player step trigger acts on the player whose step it is —
    "that player sacrifices / draws / is dealt damage" (Braids, Cabal Minion;
    Howling Mine; Sulfuric Vortex): a :func:`refers_to_scoped_player` reference
    outside a counted quantity. One only inside a ``Ref`` amount counts the
    players an effect walks (Wound Reflection's "the life they lost this turn",
    Smuggler's Share's "each opponent who drew two or more cards") and keeps the
    trigger."""
    scoped = {id(n) for n in _iter_typed_nodes(trig) if _names_scoped_player(n)}
    if not scoped:
        return False
    counted = {
        id(n)
        for ref in _iter_typed_nodes(trig)
        if tag_of(ref) == "Ref"
        for n in _iter_typed_nodes(ref)
        if _names_scoped_player(n)
    }
    return bool(scoped - counted)


# ── Choices and ability-stripping statics ──


class Choice(NamedTuple):
    """What a ``Choose`` effect chooses (CR 608.2d / 614.12 — a choice made as
    the effect resolves or as a permanent enters): its ``kind`` (``"Opponent"``,
    ``"CreatureType"``, ``"CardType"``, ``"LandType"``, ``"CardName"`` …) and,
    for a restricted choice, the printed ``options`` (Dawn-Blessed Pennant's
    eight creature types); an open choice has none."""

    kind: str
    options: tuple[str, ...] = ()


def choice_of(node: object) -> Choice | None:
    """The :class:`Choice` a ``Choose`` effect node makes, or ``None`` for any
    other node. Phase carries an open choice as a bare tag ("choose a creature
    type": Door of Destinies) and a listed one as a keyed variant whose payload
    lists the options."""
    if tag_of(node) != "Choose":
        return None
    choice = getattr(node, "choice_type", None)
    if isinstance(choice, str):
        return Choice(choice)
    if not isinstance(choice, MirrorVariant):
        return None
    # a bare option list, or one beside a count ("choose two abilities from
    # among first strike, vigilance, and lifelink" — Greymond, Avacyn's Stalwart)
    listed = getattr(choice.inner, "inner", None)
    if not isinstance(listed, list):
        listed = getattr(choice.inner, "options", None)
    options = tuple(str(t) for t in listed) if isinstance(listed, list) else ()
    return Choice(str(choice.key), options)


def chooses(node: object, kind: str) -> bool:
    """Whether ``node`` is a ``Choose`` effect of ``kind`` (an opponent: Fervent
    Mastery, Fateful Handoff; a card name: Garth One-Eye)."""
    choice = choice_of(node)
    return choice is not None and choice.kind == kind


# ── Chosen creature type payoffs (task B-1; backlog (o)) ─────────────────────
# The chosen-type reference markers phase stamps into filters. A CreatureType
# choice made as the permanent enters (CR 614.12 — the Voice of All as-enters
# replacement shape) persists, and every payoff site that cares carries one of
# these filter properties. IsChosenCardType is the spell-cast form (Door of
# Destinies watches CAST SPELLS of the chosen type, a Card filter).
_CHOSEN_TYPE_PREDS = frozenset({"IsChosenCreatureType", "IsChosenCardType"})
#: The creature-type marker alone, for the sites a card type can't fill.
_CHOSEN_CREATURE_PRED = frozenset({"IsChosenCreatureType"})
# Static modes admitted by the marked-static arm: a plain continuous payload
# (Door's dynamic anthem, Adaptive Automaton's lord line) or a trigger-doubler
# over the chosen type (Roaming Throne). Default-deny keeps punisher-shaped
# statics out (An-Zerrin Ruins' marked "CantUntap" static).
_CHOSEN_STATIC_MODES = frozenset({"Continuous", "DoubleTriggers"})
#: The type choices that are not a creature type (CR 205.2a card types; land
#: types): a chosen-type marker read off one of these names no tribe.
_NON_CREATURE_TYPE_CHOICES = frozenset({"CardType", "LandType"})
#: Effects over your own cards that a chosen-type filter narrows: a dig, a
#: reveal-until, a library search, a grant to your next spell.
_CHOSEN_TYPE_SELF_EFFECTS: frozenset[str] = frozenset(
    {"Dig", "RevealUntil", "SearchLibrary", "GrantNextSpellAbility"}
)
#: The answers beside :func:`answers_its_target`'s (destroy, exile, counter)
#: whose filter names what they remove, not what they reward: a chosen-type
#: filter of yours under one is a sweeper's or a misparsed "that player
#: controls" (Tsabo's Decree's destroy), never a payoff.
_CHOSEN_TYPE_ANSWERS: frozenset[str] = frozenset(
    {"Sacrifice", "Bounce", "BounceAll", "DamageAll"}
)


class ChosenTypePayoffs(NamedTuple):
    """Where a card pays off a creature type chosen as it's cast, enters or
    resolves (:func:`chosen_type_payoffs`)."""

    #: The types a restricted chooser may pick (Dawn-Blessed Pennant's eight),
    #: else ``("",)``: an open choice serves whatever tribe a deck fields.
    subjects: tuple[str, ...]
    #: ``(scope, clause)`` per payoff site: ``"you"`` for your own objects or
    #: spells, ``"each"`` for a filter of every player's.
    sites: tuple[tuple[str, str], ...]


def _marked(filt: object, preds: frozenset[str] = _CHOSEN_TYPE_PREDS) -> bool:
    return bool(set(filter_predicates(filt)) & preds)


def _chosen_type_serve_statics(tree: ConceptTree) -> list[tuple[str, str]]:
    """(scope, raw) per marked static that SERVES the chosen type.

    Serve-vs-punish gates, in order: controller ``Opponent`` skips (Plague
    Engineer projects -1/-1 onto an opponent's chosen tribe); a mode outside
    ``_CHOSEN_STATIC_MODES`` skips (An-Zerrin Ruins' CantUntap); a negative
    literal AddPower/AddToughness payload skips (the valence gate — phase
    drops Engineered Plague's marker today, but once its parser structures
    the "-1/-1 to the chosen type" static this gate keeps it out). Controller
    You → scope "you"; unscoped (Cover of Darkness's symmetric Fear grant,
    Urza's-Incubator-style neutral filters) → "each"."""
    out: list[tuple[str, str]] = []
    for unit in tree.units:
        for node in iter_static_defs(unit.node):
            mode = static_mode_tag(node)
            affected = getattr(node, "affected", None)
            if affected is None:
                continue
            ctrl = filter_controller(affected)
            if ctrl == "Opponent":
                continue
            scope = "you" if ctrl == "You" else "each"
            # Cost-reduction rides the ModifyCost static mode: a Reduce whose
            # spell_filter is marked serves the chosen type (Herald's Horn /
            # Urza's Incubator); an Increase would be a tax, never a serve.
            if mode == "ModifyCost":
                inner = getattr(getattr(node, "mode", None), "inner", None)
                if getattr(inner, "mode", None) == "Reduce" and _marked(
                    getattr(inner, "spell_filter", None)
                ):
                    out.append((scope, _node_raw(node)))
                continue
            if not _marked(affected) or mode not in _CHOSEN_STATIC_MODES:
                continue
            if any(
                tag_of(m) in ("AddPower", "AddToughness")
                and isinstance(getattr(m, "value", None), int)
                and getattr(m, "value", 0) < 0
                for m in list_field(node, "modifications")
            ):
                continue
            out.append((scope, _node_raw(node)))
    return out


def _chosen_type_payoffs(tree: ConceptTree) -> ChosenTypePayoffs:
    """The card's payoffs for a chosen creature type (task B-1): Door of
    Destinies, Kindred Discovery, Herald's Horn, Urza's Incubator. The type is
    chosen at runtime, so the payoff serves whatever tribe the deck fields.

    The read keys on the payoff sites that REFERENCE the choice — the
    ``IsChosenCreatureType`` / ``IsChosenCardType`` filter properties — never
    on the ``Choose`` itself (punishers like Engineered Plague choose too).
    Type-GRANTS are the type changers' (CR 613.1d layer 4: granting membership
    is the enabler side; referencing the choice in a reward filter is the
    payoff side). The sites:

    * marked STATICS (:func:`_chosen_type_serve_statics`: continuous payloads,
      trigger-doublers, ModifyCost reductions);
    * marked TRIGGERS: a trigger whose watched card carries the marker
      (Kindred Discovery's enters-or-attacks draw) — scope "you" when the
      watched filter is yours or the trigger is a SpellCast (Door counts the
      spells you cast), "each" for an any-player watch (Species Specialist);
    * the one-shot value of an ability over your permanents of the type
      (Distant Melody), your library or next spell of the type (For the
      Ancestors' dig, Progenitor's Icon's flash), the top card put into your
      hand if it's of the type (Bloodline Shaman), and chosen-type mana
      (Cavern of Souls);
    * a count of creatures of the type, anyone's but an opponent's alone
      (Caller of the Hunt's power and toughness);
    * a creature of the type you sacrifice or tap as a cost (Doom Cannon);
    * damage your sources of the type deal, doubled or raised (Collective
      Inferno) — a prevention (Circle of Solace) guards against the type;
    * a mass effect that spares the type (:func:`spared_types`: Kindred
      Dominance).

    Replacement payoffs over entering creatures (Metallic Mimic) are a known
    not-served-yet class. A card that chooses a card or land type and no
    creature type (Cloud Key, Umori, Shimmer) is no tribal payoff, whatever its
    filter's marker reads. A RESTRICTED chooser (Dawn-Blessed Pennant picks from
    eight printed types) serves only those tribes."""
    choices = [
        choice
        for unit in tree.units
        for eff in unit.effects
        if (choice := choice_of(eff.node)) is not None
    ]
    kinds = {kind for kind, _ in choices}
    if kinds & _NON_CREATURE_TYPE_CHOICES and "CreatureType" not in kinds:
        # CR 205.3m: a card or land type chosen names no creature type.
        return ChosenTypePayoffs(("",), ())
    listed: list[str] = []
    for kind, options in choices:
        if kind != "CreatureType":
            continue
        if not options:
            listed = []
            break
        listed.extend(options)
    subjects = tuple(dict.fromkeys(listed)) or ("",)
    sites = _chosen_type_serve_statics(tree)
    for unit in tree.units:
        node = unit.node
        valid_card = getattr(node, "valid_card", None)
        if unit.origin == "trigger" and valid_card is not None and _marked(valid_card):
            ctrl = filter_controller(valid_card)
            if ctrl != "Opponent":
                mode = getattr(node, "mode", None)
                mode_tag = mode if isinstance(mode, str) else tag_of(mode)
                you = ctrl == "You" or mode_tag == "SpellCast"
                sites.append(("you" if you else "each", _node_raw(node)))
        # Damage your sources of the type would deal, raised (CR 614.1a).
        source = getattr(node, "damage_source_filter", None)
        if (
            unit.origin == "replacement"
            and _marked(source, _CHOSEN_CREATURE_PRED)
            and filter_controller(source) == "You"
        ):
            sites.append(("you", _node_raw(node)))
        # Every count of the type that isn't an opponent's alone.
        for n in unit.iter_typed():
            if (
                tag_of(n) == "ObjectCount"
                and _marked(filt := getattr(n, "filter", None))
                and filter_controller(filt) != "Opponent"
            ):
                sites.append(("you", _node_raw(node)))
                break
    for unit in tree.units if "CreatureType" in kinds else ():
        raw = _node_raw(unit.node)
        answered = {
            id(getattr(n, "target", None))
            for n in iter_typed_nodes(unit.node)
            if answers_its_target(n) or tag_of(n) in _CHOSEN_TYPE_ANSWERS
        }
        # A creature of the chosen type you sacrifice or tap as a cost.
        if any(
            _marked(getattr(leaf, "target", None), _CHOSEN_CREATURE_PRED)
            for c in unit.costs
            for leaf in iter_cost_leaves(c.node)
        ):
            sites.append(("you", raw))
        for n in iter_typed_nodes(unit.node):
            tag = tag_of(n)
            if (
                # Your library or your next spell, of the chosen type.
                (
                    tag in _CHOSEN_TYPE_SELF_EFFECTS
                    and any(
                        _marked(getattr(n, field, None), _CHOSEN_CREATURE_PRED)
                        for field in ("filter", "spell_filter")
                    )
                )
                # The revealed top card to your hand if it's of the type.
                or (
                    tag == "TargetMatchesFilter"
                    and _marked(getattr(n, "filter", None), _CHOSEN_CREATURE_PRED)
                )
                or (tag == "Mana" and "ChosenCreatureType" in mana_restrictions(n))
                or (
                    unit.origin in ("ability", "trigger")
                    and tag == "Typed"
                    and _marked(n, _CHOSEN_CREATURE_PRED)
                    and filter_controller(n) == "You"
                    and id(n) not in answered
                )
            ):
                sites.append(("you", raw))
                break
    if spared_types(tree).chosen:
        sites.append(("you", ""))
    return ChosenTypePayoffs(subjects, tuple(sites))


def chosen_type_payoffs(tree: ConceptTree) -> ChosenTypePayoffs:
    """:func:`_chosen_type_payoffs`, read once per tree."""
    return memo_on(tree, "_xw_chosen_type_payoffs", _chosen_type_payoffs)


def strips_abilities(static_def: object) -> bool:
    """Whether a static removes the abilities its affected object has from its
    rules text (CR 613.1f, layer 6): an explicit "loses all abilities"
    (Imprisoned in the Moon, Minimus Containment) or a land type set to a basic
    land type, which takes them with it (CR 305.7 — Song of the Dryads'
    "colorless Forest land"). A retype that leaves them (One with the Stars,
    Swift Reconfiguration — each keeps all its abilities, per its rulings) does
    not."""
    return any(
        tag_of(m) in ("RemoveAllAbilities", "SetBasicLandType")
        for m in getattr(static_def, "modifications", None) or ()
    )


# ── Planeswalkers named beside creatures ──


def _creature_or_planeswalker_pair(node: object) -> tuple[int, ...]:
    """The ids of the planeswalker arm of ``node`` when it is the bare pair
    "creature or planeswalker" — an ``Or`` of exactly a ``Typed`` Creature and a
    ``Typed`` Planeswalker under one controller and no qualifier past "another"
    ("target creature or planeswalker you control", "another creature or
    planeswalker you control enters", "creatures and/or planeswalkers you
    control"); ``()`` otherwise. A qualified pair ("legendary creatures and
    planeswalkers" — Mox Amber) or a wider list ("artifact, creature, land, or
    planeswalker" — Soul Diviner) is not the pair."""
    if tag_of(node) != "Or":
        return ()
    arms = getattr(node, "filters", None) or ()
    if len(arms) != 2 or any(tag_of(a) != "Typed" for a in arms):
        return ()
    words = [list(getattr(a, "type_filters", None) or ()) for a in arms]
    if not all(len(w) == 1 and isinstance(w[0], str) for w in words):
        return ()  # a subtype or a second type word qualifies the arm
    if sorted(w[0] for w in words) != ["Creature", "Planeswalker"]:
        return ()
    if len({filter_controller(a) for a in arms}) != 1:
        return ()
    for a in arms:
        if any(tag_of(p) != "Another" for p in getattr(a, "properties", None) or ()):
            return ()
    return tuple(id(a) for a in arms if "Planeswalker" in filter_core_types(a))


def planeswalkers_only_beside_creatures(tree: ConceptTree) -> bool:
    """Whether the card names planeswalkers only as half of "creature or
    planeswalker" and never their loyalty: every typed filter naming Planeswalker
    is an arm of the bare pair (:func:`_creature_or_planeswalker_pair`) or the
    card's ``Enchant`` restriction is that pair, and no node counts, adds or
    removes loyalty counters. Such a card protects, recurs or watches your board
    with planeswalkers on it — Angelic Intervention's protection, Kaya's
    Ghostform's return, Fey Steed's targeting trigger, The Western Cloud's
    prevention — rather than rewarding planeswalkers as a group. One that also
    touches loyalty keeps the planeswalker half (Spark Double's copy enters with
    an extra loyalty counter); one phase types no planeswalker filter for
    (Lae'zel, Vlaakith's Champion's counter replacement) is not this read's to
    decide."""
    planeswalker_arms: set[int] = set()
    paired: set[int] = set()
    for n in tree.iter_typed():
        if counter_kind_any(n) == "LOYALTY":
            return False
        if tag_of(n) == "Typed" and "Planeswalker" in filter_core_types(n):
            planeswalker_arms.add(id(n))
        paired.update(_creature_or_planeswalker_pair(n))
    enchants_pair = sorted(tree.card_enchant_core_types) == [
        "Creature",
        "Planeswalker",
    ]
    if not (paired or enchants_pair):
        return False
    return planeswalker_arms <= paired


# ── Theme-page reads (backlog (o), 2026-10-25) ───────────────────────────────
# The structures the last pattern-paged theme sub-avenues needed an ident for.


def _extra_blockers_count(mode: object) -> tuple[bool, int | None]:
    """Whether a static ``mode`` is ``ExtraBlockers``, and its count: N for "can
    block N additional creatures", ``None`` for "any number of creatures"."""
    if not (isinstance(mode, MirrorVariant) and mode.key == "ExtraBlockers"):
        return False, None
    count = mode.inner
    n = count.inner if isinstance(count, MirrorVariant) else count
    return True, n if isinstance(n, int) else None


def _extra_blocker_counts(sdef: object) -> Iterator[int | None]:
    """The ``ExtraBlockers`` counts one static definition carries: its own mode
    (Wall of Glare) or an ``AddStaticMode`` it hands the affected creature
    (Entangler, Echo Circlet)."""
    hit, n = _extra_blockers_count(getattr(sdef, "mode", MISSING))
    if hit:
        yield n
    for mod in list_field(sdef, "modifications"):
        if tag_of(mod) == "AddStaticMode":
            hit, n = _extra_blockers_count(getattr(mod, "mode", MISSING))
            if hit:
                yield n


def iter_static_grant_sites(
    unit: AbilityUnit,
) -> Iterator[tuple[TypedMirrorNode, object]]:
    """``(static_def, host_target)`` for every static def one unit carries or
    hands out: its own (a static unit, a granted static list — ``host_target``
    ``None``) and a one-shot grant's (a ``GenericEffect``'s
    ``static_abilities`` — ``host_target`` the effect's ``target``, which a
    def's ``ParentTarget`` names: "Target creature can block any number of
    creatures this turn" — Valor Made Real; Touch of Vitae). Each def once."""
    granted: set[int] = set()
    for n in unit.iter_typed():
        statics = getattr(n, "static_abilities", None)
        if isinstance(statics, list):
            for sdef in statics:
                granted.add(id(sdef))
                yield sdef, getattr(n, "target", None)
        elif id(n) not in granted and _present(getattr(n, "affected", MISSING)):
            yield n, None


def _blocker_side(affected: object, target: object) -> str:
    """The side of the creature an extra-blockers static reaches: the card
    itself and the creature its Aura or Equipment is attached to are yours (you
    choose what it enchants or equips); a one-shot grant's ``ParentTarget`` is
    its target's controller's ("target creature defending player controls" —
    Blaze of Glory), a target with no controller yours (CR 601.2c: you choose
    the target); a group its filter's, ``"each"`` with no controller."""
    tag = tag_of(affected)
    if tag == "SelfRef" or names_attached_object(affected):
        return "you"
    if tag == "ParentTarget":
        return filter_controller_side(target) or "you"
    return filter_controller_side(affected) or "each"


class ExtraBlockers(NamedTuple):
    """One "can block additional creatures" the card has or grants."""

    side: str  # the blocker's side: "you" | "opponents" | "chosen" | "each"
    count: int | None  # the additional blocks; ``None`` for any number


def extra_blocker_grants(tree: ConceptTree) -> tuple[ExtraBlockers, ...]:
    """Every "can block an additional creature" / "can block any number of
    creatures" the card has or grants (CR 509.1a has each blocker block one
    attacker; these abilities let it block more): a static of the card's own
    (Wall of Glare), one it gives the creature it's attached to (Entangler, Echo
    Circlet), and a one-shot grant to a target (Valor Made Real, Give No
    Ground). The side is the blocker's (:func:`_blocker_side`)."""
    return tuple(
        ExtraBlockers(_blocker_side(getattr(sdef, "affected", None), host), c)
        for unit in tree.units
        for sdef, host in iter_static_grant_sites(unit)
        for c in _extra_blocker_counts(sdef)
    )


# The comparisons a "has N or fewer cards in hand" condition writes, as
# ``(comparator, largest N)`` with the hand count on the left: "no cards" (EQ 0),
# "one or fewer" (LE 1), "fewer than two" (LT 2).
_SMALL_HAND_BOUNDS: dict[str, int] = {"EQ": 0, "LE": 1, "LT": 2}
# The same comparison with the hand count on the right ("0 is at least …").
_FLIPPED_COMPARATORS: dict[str, str] = {"EQ": "EQ", "GE": "LE", "GT": "LT"}


def _hand_count_player(qty: object) -> object | None:
    """The player whose hand a quantity counts — ``HandSize``'s ``player``, or
    the target player of a ``TargetZoneCardCount`` over the hand (Bulwark's
    "the number of cards in that player's hand") — else ``None``."""
    tag = tag_of(qty)
    if tag in ("HandSize", "HandSizeExact"):
        return getattr(qty, "player", None)
    if tag == "TargetZoneCardCount" and getattr(qty, "zone", None) == "Hand":
        return "TargetPlayer"
    return None


#: The player recipients a "their hand" with no target of its own can mean.
_HAND_RECIPIENT_TAGS: frozenset[str] = frozenset(
    {"ScopedPlayer", "TriggeringPlayer", "SourceChosenPlayer", "DefendingPlayer"}
)


def _hand_player_side(
    player: object, unit: AbilityUnit, tree: ConceptTree
) -> str | None:
    """The side of the player whose hand is counted: an opponent, the each-
    opponent (or each-player) loop's "that player" (:func:`scoped_player_scope`),
    a trigger's player (:func:`triggering_player_side`), the opponent the card
    chose as it entered (The Rack: "choose an opponent"), and a target player by
    the side the unit's target filter names (Bulwark's "target opponent"). A
    "their hand" with no target to name is the player the unit deals with
    (Rackling's "deals X damage to that player, where X is 3 minus the number of
    cards in their hand")."""
    tag = player if isinstance(player, str) else tag_of(player)
    if tag == "TargetPlayer" and root_target_filter(unit) is None:
        recipient = next(
            (
                tag_of(t)
                for n in iter_typed_nodes(unit.node)
                if (t := getattr(n, "target", None)) is not None
                and tag_of(t) in _HAND_RECIPIENT_TAGS
            ),
            None,
        )
        if recipient is not None:
            return _hand_player_side(recipient, unit, tree)
    if tag in OPPONENT_ACTOR_TAGS or tag in ("DefendingPlayer", "TargetOpponent"):
        return "opponents"
    if tag == "ScopedPlayer":
        return scoped_player_scope(unit)
    if tag == "TriggeringPlayer":
        return triggering_player_side(unit)
    if tag == "SourceChosenPlayer":
        chooses_opponent = any(
            tag_of(n) == "Choose" and getattr(n, "choice_type", None) == "Opponent"
            for n in tree.iter_typed()
        )
        return "opponents" if chooses_opponent else None
    if tag in TARGETED_PLAYER_TAGS or tag == "TargetPlayer":
        return filter_controller_side(root_target_filter(unit))
    return None


def _small_hand_qtys(node: object) -> Iterator[object]:
    """The hand counts one node reads as small or negated: a condition "has N or
    fewer cards in hand" (:data:`_SMALL_HAND_BOUNDS`) and an amount "N minus the
    number of cards in their hand" (a ``Multiply`` by -1)."""
    tag = tag_of(node)
    if tag in ("QuantityComparison", "QuantityCheck"):
        comp = getattr(node, "comparator", None)
        lhs, rhs = getattr(node, "lhs", None), getattr(node, "rhs", None)
        if tag_of(lhs) != "Ref" and tag_of(rhs) == "Ref":
            lhs, rhs = rhs, lhs
            comp = _FLIPPED_COMPARATORS.get(comp) if isinstance(comp, str) else None
        bound = _SMALL_HAND_BOUNDS.get(comp) if isinstance(comp, str) else None
        value = getattr(rhs, "value", None) if tag_of(rhs) == "Fixed" else None
        if (
            tag_of(lhs) == "Ref"
            and bound is not None
            and isinstance(value, int)
            and value <= bound
        ):
            yield getattr(lhs, "qty", None)
    elif tag == "Multiply" and getattr(node, "factor", None) == -1:
        inner = getattr(node, "inner", None)
        if tag_of(inner) == "Ref":
            yield getattr(inner, "qty", None)


def rewards_opponent_small_hand(tree: ConceptTree) -> bool:
    """Whether the card pays off an opponent's small or empty hand (CR 402.1: a
    player's hand): a condition that an opponent has one or fewer / no cards in
    hand (Shrieking Affliction, Guul Draz Specter, Avatar of Will's discount), or
    damage scaled by "N minus the number of cards in their hand" (The Rack,
    Bulwark). An each-player loop counts its opponents too (Asylum Visitor),
    unless it hands "that player" the cards it checked for: a refill is no
    punisher (Ghirapur Orrery's "that player draws three cards")."""
    for unit in tree.units:
        nodes = list(iter_typed_nodes(unit.node))
        refill = any(
            tag_of(n) == "Draw" and tag_of(getattr(n, "target", None)) == "ScopedPlayer"
            for n in nodes
        )
        for n in nodes:
            for qty in _small_hand_qtys(n):
                player = _hand_count_player(qty)
                if player is None:
                    continue
                side = _hand_player_side(player, unit, tree)
                if side == "opponents" or (side == "each" and not refill):
                    return True
    return False


#: The predefined artifact tokens that make mana or fetch a land: Treasure, Gold
#: and Powerstone sacrifice or tap for mana, a Lander searches for a basic land
#: (CR 111.10a / 111.10c / 111.10h / 111.10u).
RAMP_TOKEN_SUBTYPES: frozenset[str] = frozenset(
    {"Treasure", "Gold", "Powerstone", "Lander"}
)


def _token_ramps(node: object) -> bool:
    """Whether a ``Token`` effect makes a mana source: a predefined ramp token
    (:data:`RAMP_TOKEN_SUBTYPES`), or one whose own abilities add mana (Kibo's
    Banana)."""
    types = list_field(node, "types")
    if RAMP_TOKEN_SUBTYPES & {t for t in types if isinstance(t, str)}:
        return True
    return any(tag_of(n) == "Mana" for n in iter_typed_nodes(node))


def gives_each_player_ramp(tree: ConceptTree) -> bool:
    """Whether the card gives EVERY player a land or a mana source, as one
    ability every player performs (the wrapper's ``player_scope`` is ``All`` —
    :func:`effect_owner_player_scope`): each player searches for a land (New
    Frontiers, Collective Voyage's join forces, Jungle Wayfinder) or creates a
    Treasure-like token (Marching Duodrone, Descent into Avernus, Edge Rover's
    Lander, Kibo's Banana). The symmetric group-ramp half of a group-mana deck."""
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            tag = tag_of(n)
            if tag not in ("Token", "SearchLibrary"):
                continue
            if effect_owner_player_scope(unit.node, n) != "All":
                continue
            if tag == "Token" and _token_ramps(n):
                return True
            if (
                tag == "SearchLibrary"
                and land_search_colors(getattr(n, "filter", None)) is not None
            ):
                return True
    return False


def watches_each_players_land_taps(unit: AbilityUnit) -> bool:
    """Whether a trigger watches ANY player tapping a land for mana (CR 106.12a):
    "Whenever a player taps a land for mana" — the shared doublers and punishers (Mana
    Flare, Manabarbs, Price of Glory, Storm Cauldron's "a land is tapped for
    mana"). One limited to your lands or to an opponent's is one-sided."""
    if unit.origin != "trigger" or unit.trigger_event != "tapsformana":
        return False
    watched = getattr(unit.node, "valid_card", None)
    return "Land" in filter_core_types(watched) and filter_controller(watched) is None


#: The trigger events a token LEAVING the battlefield fires (CR 603.6c).
_TOKEN_LEAVE_EVENTS: frozenset[str] = frozenset({"sacrificed", "leaves", "dies"})


def watches_your_tokens(unit: AbilityUnit) -> bool:
    """Whether a trigger watches your tokens being made or leaving: "Whenever
    you create a token" (Mirkwood Bats — phase's ``TokenCreated`` with you as
    its player) or "whenever a token you control leaves the battlefield / you
    sacrifice a token" (Nadier's Nightblade, Sanguine Brushstroke's Blood
    tokens) — a ``Token`` property on a watched filter that's not an
    opponent's."""
    if unit.origin != "trigger":
        return False
    event = unit.trigger_event
    if event == "tokencreated":
        return trigger_scope(unit.node) == "you"
    if event in _TOKEN_LEAVE_EVENTS:
        watched = getattr(unit.node, "valid_card", None)
        return has_filter_property(watched, "Token") and (
            filter_controller_side(watched) != "opponents"
        )
    return False


def drains_opponents(
    unit: AbilityUnit, root: object = None, *, any_player_damage: bool = False
) -> bool:
    """Whether anything under ``root`` (default: the whole unit) makes an
    opponent lose life (CR 119.3): a ``LoseLife`` whose recipient is an opponent
    (:func:`lifeloss_recipient_scope`), or whose wrapper an opponent (or every
    player) performs ("each opponent loses 1 life" — Gray Merchant's shape), or
    damage that drains an opponent (:func:`damage_drains_opponent`) — with
    ``any_player_damage``, any damage that can reach a player ("any target")."""
    for n in iter_typed_nodes(unit.node if root is None else root):
        tag = tag_of(n)
        if tag in DAMAGE_EFFECT_TAGS:
            if damage_drains_opponent(unit, n) or (
                any_player_damage and effect_reaches_player(n, unit.node)
            ):
                return True
            continue
        if tag == "LoseLife":
            rs = lifeloss_recipient_scope(n)
            if rs == "opponents":
                return True
            if rs in (None, "each"):
                owner = effect_owner_player_scope(unit.node, n)
                if owner in OPPONENT_WRAPPER_ACTORS or owner == "All":
                    return True
    return False


def makes_creature_tokens_at_once(node: TypedMirrorNode) -> bool:
    """Whether a ``Token`` effect creates two or more CREATURE tokens at once
    — the read's own line for a go-wide maker: a fixed count that high, or a
    variable one (X, "for each …" — Secure the Wastes, Grand Crescendo)."""
    return (
        tag_of(node) == "Token"
        and "Creature" in list_field(node, "types")
        and (amount_is_scaling(node, "count") or amount_factor(node, "count") >= 2)
    )


def _amount_is_power_scaled(amount: object) -> bool:
    """Whether a damage amount is a creature's power, however scaled: its power
    (Fling), twice it (Polliwallop's ``Multiply``), or the greatest power among
    a group (Mega Flare's ``PropertyAggregate``, :data:`AGGREGATE_QTY_TAGS`) —
    CR 208.1 power."""
    return any(
        tag_of(n) == "Power"
        or (tag_of(n) in AGGREGATE_QTY_TAGS and getattr(n, "property", None) == "Power")
        for n in iter_typed_nodes(amount)
    )


def repeats_damage_to_players(unit: AbilityUnit) -> bool:
    """Whether a trigger on damage a source of yours deals deals THAT MUCH damage
    again to players (CR 120.3a: damage to a player makes them lose that much
    life): "whenever ~ deals combat damage to an opponent, it deals that much
    damage to each other opponent" (Hydra Omnivore, Kediss, Super State), "that
    Archer deals that much damage to that creature's controller" (Greatbow
    Doyen), "~ deals that much damage to each opponent" (Imodane). The amount
    is the triggering event's (``EventContextAmount``); a watched source of an
    opponent's never counts. The damage trigger may be one the unit grants
    (Kosei, Penitent Warlord's) or sets up for a turn (Human Torch's)."""
    if not any(
        trigger_def_event(n) == "deals_damage"
        and filter_controller_side(getattr(n, "valid_source", None)) != "opponents"
        for n in iter_unit_trigger_defs(unit, delayed=True)
    ):
        return False
    for n in iter_typed_nodes(unit.node):
        if tag_of(n) not in DAMAGE_EFFECT_TAGS:
            continue
        amount = getattr(n, "amount", None)
        if tag_of(amount) != "Ref" or tag_of(getattr(amount, "qty", None)) != (
            "EventContextAmount"
        ):
            continue
        if effect_reaches_player(n, unit.node):
            return True
    return False


def doubles_opponents_life_loss(unit: AbilityUnit) -> bool:
    """Whether a unit makes an opponent lose life equal to the life they already
    lost this turn — "each opponent loses life equal to the life they lost this
    turn" (Wound Reflection, Archfiend of Despair; CR 119.3): the loss pushed
    through is lost again."""
    for n in iter_typed_nodes(unit.node):
        if tag_of(n) != "LoseLife":
            continue
        if not life_lost_this_turn_sides(getattr(n, "amount", None)):
            continue
        rs = lifeloss_recipient_scope(n)
        owner = effect_owner_player_scope(unit.node, n)
        if rs == "opponents" or owner in OPPONENT_WRAPPER_ACTORS:
            return True
    return False


#: Damage effects whose amount IS the sources' power, with no amount field to
#: read: "Up to two target creatures you control each deal damage equal to their
#: power to another target creature" (Band Together, Allies at Last).
POWER_DAMAGE_TAGS: frozenset[str] = frozenset({"EachDealsDamageEqualToPower"})


def iter_power_damage(root: object) -> Iterator[tuple[TypedMirrorNode, object]]:
    """``(damage effect, recipient)`` for every damage under ``root`` a creature's
    power sizes (:func:`_amount_is_power_scaled`, :data:`POWER_DAMAGE_TAGS`) —
    nested ones included: a delayed trigger's (Judgment of Alexander), an
    ability a card grants (Burning Anger's "{T}: This creature deals damage equal
    to its power to any target")."""
    for n in iter_typed_nodes(root):
        if is_power_damage(n):
            yield (
                n,
                (
                    getattr(n, "recipient", None)
                    if tag_of(n) in POWER_DAMAGE_TAGS
                    else damage_recipient(n)
                ),
            )


def is_power_damage(n: object) -> bool:
    """Whether one node is damage a creature's power sizes
    (:func:`iter_power_damage`'s test)."""
    tag = tag_of(n)
    return tag in POWER_DAMAGE_TAGS or (
        tag in DAMAGE_EFFECT_TAGS
        and _amount_is_power_scaled(getattr(n, "amount", None))
    )


# ── Self drawbacks (backlog (o)) ─────────────────────────────────────────────
# A permanent's own downside: what an ability strip turns off (Abigale), what an
# enlist creature that can't attack anyway is tapped for (Aradesh), what a
# donate deck hands an opponent (Abyssal Persecutor, Demonic Taskmaster).

#: The static modes that keep the card itself out of combat (CR 508.1c / 509.1b:
#: restrictions on attacking and blocking).
COMBAT_RESTRICTION_MODES: frozenset[str] = frozenset(
    {"CantAttack", "CantBlock", "CantAttackOrBlock"}
)


#: The fields a node names a zone in.
_ZONE_FIELDS: tuple[str, ...] = ("zone", "origin", "destination")


def _reads_a_graveyard(tree: ConceptTree) -> bool:
    """Whether a node of the card beyond a mill names the graveyard: a count of
    its cards (Splinterfright's power), a card put there (Sidisi, Brood
    Tyrant's trigger)."""
    return any(
        tag_of(n) != "Mill"
        and any(getattr(n, f, None) == "Graveyard" for f in _ZONE_FIELDS)
        for n in tree.iter_typed()
    )


#: The effects that can hurt their controller (:func:`_harms_you`).
_HARM_TAGS: frozenset[str] = frozenset(
    {"Sacrifice", "LoseLife", "DealDamage", "LoseTheGame", "Discard", "Mill"}
)


def _harms_you(
    unit: AbilityUnit,
    n: TypedMirrorNode,
    *,
    mill_is_fuel: Callable[[], bool] = lambda: False,
) -> bool:
    """Whether one effect hurts the ability's controller beyond the card itself:
    you sacrifice another permanent you pick, lose life, are dealt damage,
    discard, mill or lose the game (CR 701.21a / 119.3 / 120.3 / 701.9a /
    701.17a / 104.3). A self-mill on a card that reads the graveyard is its
    fuel (``mill_is_fuel``, asked only on a mill — Splinterfright), not a
    drawback, the read's own call; what a trigger watching an opponent makes
    "that player" do (Ob Nixilis, Unshackled's sacrifice and life loss) is
    theirs, as is an enchanted player's (:func:`effect_actor_scope`)."""
    tag = tag_of(n)
    if tag not in _HARM_TAGS:
        return False
    owner = effect_owner_player_scope(unit.node, n)
    if owner in OPPONENT_WRAPPER_ACTORS or owner == "All":
        return False
    if effect_actor_scope(unit, n) is not None:
        return False
    theirs = triggering_player_side(unit) == "opponents"
    target = getattr(n, "target", None)
    if tag == "Sacrifice":
        # A permanent of yours you pick — never the card itself (its own
        # fragility, :func:`self_drawbacks`' restriction) or one an effect made
        # and names back ("Sacrifice that token" — Firion).
        return (
            tag_of(target) in OBJECT_FILTER_TAGS
            and filter_controller_side(target) not in ("opponents", "chosen")
            and not (theirs and filter_controller(target) == "ScopedPlayer")
        )
    if tag == "LoseLife":
        scope = lifeloss_recipient_scope(n)
        return scope == "you" or (scope is None and not theirs)
    if tag in ("DealDamage", "LoseTheGame", "Discard") or (
        tag == "Mill" and not mill_is_fuel()
    ):
        return tag_of(target) in ("Controller", None)
    return False


def _loses_you_the_game(root: object) -> bool:
    """A "you lose the game" anywhere under ``root`` (a modal arm — Demonic
    Pact's last mode — included), never inside a token the ability makes."""
    losses = [
        n
        for n in iter_typed_nodes(root)
        if tag_of(n) == "LoseTheGame"
        and tag_of(getattr(n, "target", None)) in ("Controller", None)
    ]
    if not losses:
        return False
    tokens = {
        id(m)
        for t in iter_typed_nodes(root)
        if tag_of(t) == "Token"
        for m in iter_typed_nodes(t)
    }
    return any(id(n) not in tokens for n in losses)


#: The keyword abilities that make a permanent pay to stay or arrive.
_UPKEEP_COST_KEYWORDS: frozenset[str] = frozenset({"CumulativeUpkeep", "Champion"})


class SelfDrawbacks(NamedTuple):
    """The drawbacks a permanent puts on itself or its controller."""

    restriction: bool  # it fights, stays or arrives only on a condition
    harm: bool  # it hurts its controller


def self_drawbacks(tree: ConceptTree) -> SelfDrawbacks:
    """A permanent's own drawbacks.

    ``restriction`` — the card is held back: it can't attack or block unless a
    condition holds ("can't attack unless defending player controls an Island"
    — Sea Serpent; "can't attack or block unless you have seven or more cards in
    hand" — Kefnet the Mindful), it shrinks itself ("gets -1/-1 for each card in
    your hand" — Grim Strider), it has cumulative upkeep (CR 702.24a — Aboroth),
    it sacrifices itself unless you pay (Arcades Sabboth's upkeep, Balduvian
    Horde's enters cost, "When you control no Islands, sacrifice ~"), or it
    costs you a permanent as it enters (Spined Fluke).

    ``harm`` — it hurts its controller every turn or on an event: a mandatory
    trigger that makes you sacrifice another permanent, lose life, take damage,
    discard or mill (Demonic Taskmaster's upkeep sacrifice, Benthic Djinn, Flesh
    Reaver's "deals that much damage to you", Jackal Pup), a "you lose the game"
    (Phage the Untouchable, Demonic Pact, Forbidden Crypt's replacement), or
    "You can't win the game" (Abyssal Persecutor). A loss that pays for a card
    drawn beside it (Dark Confidant's kin) is card advantage, not a drawback; a
    trigger watching another object enter is an engine's cost; an instant or
    sorcery (a pact's next-upkeep payment) is no permanent to strip or hand
    over; a downside the card hands other permanents (Pillory of the Sleepless,
    Magus of the Tabernacle) is a curse or a stax piece, not its own."""
    if not set(tree.card_types) & PERMANENT_CARD_TYPES:
        return SelfDrawbacks(restriction=False, harm=False)
    # Cumulative upkeep (CR 702.24a) and champion (CR 702.72a: sacrifice it
    # unless you exile another) — keyword costs phase may type only as a keyword.
    restriction = bool(_UPKEEP_COST_KEYWORDS & set(tree.card_keywords))
    harm = False
    mill_is_fuel = cache(partial(_reads_a_graveyard, tree))
    for unit in tree.units:
        node = unit.node
        if unit.origin == "static":
            affected = getattr(node, "affected", None)
            if (
                tag_of(affected) == "SelfRef"
                and static_mode_tag(node) in COMBAT_RESTRICTION_MODES
                and _present(getattr(node, "condition", MISSING))
            ):
                restriction = True
            if tag_of(affected) == "SelfRef" and min(pt_mod_signs(node)) < 0:
                restriction = True
            if static_mode_tag(node) == "CantWinTheGame" and (
                filter_controller(affected) == "You"
            ):
                harm = True
            continue
        if unit.origin == "replacement":
            harm = harm or _loses_you_the_game(node)
            continue
        if unit.origin != "trigger" or getattr(node, "optional", False) is True:
            continue
        if getattr(node, "mode", None) == "PayCumulativeUpkeep":
            restriction = True
            continue
        if unit.trigger_event == "enters" and (
            tag_of(getattr(node, "valid_card", None)) != "SelfRef"
        ):
            continue  # another object entering: an engine's cost, not the card's
        if _loses_you_the_game(node):
            harm = True
            continue
        if any(tag_of(c.node) == "Draw" for c in unit.effects):
            continue
        if any(
            _harms_you(unit, c.node, mill_is_fuel=mill_is_fuel) for c in unit.effects
        ):
            if unit.trigger_event in ("enters", "statecondition"):
                restriction = True
            else:
                harm = True
        elif any(
            tag_of(c.node) == "Sacrifice"
            and tag_of(getattr(c.node, "target", None)) == "SelfRef"
            for c in unit.effects
        ):
            restriction = True
    return SelfDrawbacks(restriction, harm)


# ── Subtype references (backlog (o)) ─────────────────────────────────────────


#: The card-type words a keyword's type parameter may carry beside a subtype.
_CORE_TYPE_WORDS: frozenset[str] = frozenset(
    {*PERMANENT_CARD_TYPES, "Instant", "Sorcery", "Kindred", "Card", "Permanent"}
)


class SparedTypes(NamedTuple):
    """The creature types a card's mass effects leave out (CR 205.3m)."""

    subtypes: frozenset[str]  # "Non-Elf creatures get -2/-2" (Eyeblight Massacre)
    chosen: bool  # "creatures that aren't of the chosen type" (Kindred Dominance)


def _excluded_creature_types(filt: object) -> tuple[set[str], bool]:
    """The creature types an object filter excludes — a ``Non`` subtype entry
    (:func:`filter_non_types`: "each non-Dragon creature") or a ``Not`` arm over
    a subtype or the chosen creature type — and whether the chosen type is one
    of them."""
    subs = {w for w in filter_non_types(filt) if w.lower() in CREATURE_TYPES}
    chosen = False
    for n in iter_typed_nodes(filt):
        if tag_of(n) == "Not":
            negated = getattr(n, "filter", None)
            chosen = chosen or "IsChosenCreatureType" in filter_predicates(negated)
            subs.update(
                s for s in filter_subtypes(negated) if s.lower() in CREATURE_TYPES
            )
    return subs, chosen


def _spared_types(tree: ConceptTree) -> SparedTypes:
    """The creature types the card's harmful mass effects spare: a sweeper, a
    mass shrink or a mass bounce over every object but a type
    (:data:`MASS_FILTER_EFFECT_TAGS`: "Non-Elf creatures get -2/-2 until end of
    turn" — Eyeblight Massacre; "deals 2 damage to each non-Dragon creature" —
    Breath Weapon; "Destroy all creatures that aren't of the chosen type" —
    Kindred Dominance) and an edict every player obeys ("each player sacrifices
    a non-Vampire creature" — Anowon, the Ruin Sage; "that player sacrifices a
    non-Zombie creature" at each player's upkeep — Call to the Grave). Each is
    one-sided against every other type, so a board of that type is what it
    rewards (the lane's call). Left out: a mass effect over an opponent's
    objects alone, which spares their tribe; a targeted effect that can't hit the
    type (Victim of Night's "destroy target non-Vampire, non-Werewolf,
    non-Zombie creature"), which spares no board; a mass pump ("Non-Human
    creatures you control get +3/+3" — Return of the Wildspeaker), which
    rewards the other types; a sacrifice only you make, as a cost or an
    upkeep drawback (Veko, Death's Doorkeeper; Archdemon of Unx); and a
    library dig's "put the rest on the bottom", which moves no permanent
    (Goblin Ringleader)."""
    subs: set[str] = set()
    chosen = False
    for unit in tree.units:
        for n in unit.iter_typed():
            tag = tag_of(n)
            if tag == "PumpAll":
                harms = pump_is_negative(n) or negative_pt_field(n, "toughness")
            elif tag == "ChangeZoneAll":
                harms = getattr(n, "origin", None) == "Battlefield"
            elif tag == "Sacrifice":
                reach = effect_player_reach(unit.node, n)
                if reach == "scoped":
                    reach = scoped_player_scope(unit)
                harms = reach == "each"
            else:
                harms = tag in MASS_FILTER_EFFECT_TAGS
            target = getattr(n, "target", None)
            # A sweep of an opponent's objects alone spares their tribe.
            if not harms or filter_controller_side(target) == "opponents":
                continue
            found, by_choice = _excluded_creature_types(target)
            subs |= found
            chosen = chosen or by_choice
    return SparedTypes(frozenset(subs), chosen)


def spared_types(tree: ConceptTree) -> SparedTypes:
    """:func:`_spared_types`, read once per tree."""
    return memo_on(tree, "_xw_spared_types", _spared_types)


#: Every subtype word a type grant may hand an object (CR 205.3): a misparsed
#: grant's stray word ("except it's a 4/4 Dragon creature with flying" read as
#: the subtypes ``With`` and ``Flying`` — Will of the Temur) names none.
_SUBTYPE_WORDS: frozenset[str] = (
    CREATURE_TYPES
    | ARTIFACT_TYPES
    | ENCHANTMENT_TYPES
    | PLANESWALKER_TYPES
    | BATTLE_TYPES
    | LAND_SUBTYPE_WORDS
)


class SubtypeRefs(NamedTuple):
    """The subtypes a card's object filters name (CR 205.3: subtypes)."""

    any_side: frozenset[str]  # named by any filter ("Destroy target Goblin")
    yours: frozenset[str]  # named by a filter that isn't an opponent's
    shares_type: bool  # "shares a creature type" (Coat of Arms)


def _subtype_refs(tree: ConceptTree) -> SubtypeRefs:
    """The subtypes the card's object filters name, wherever they sit — a lord's
    affected set ("Other Goblin creatures get +1/+1" — Goblin King; "Goblins you
    control have haste" — Goblin Warchief), a count ("for each Elf you
    control"), a cost ("Sacrifice a Goblin" — Skirk Prospector; "behold a
    Goblin" — Champion of the Weird), a spell filter ("Goblin spells you cast
    cost {1} less"), a search ("for a Goblin card"), a trigger's watched
    object, a casting condition ("Cast this spell only if you control two or
    more Vampires" — Feast of Blood), mana spendable only on a type's spells
    ("Spend this mana only to cast Dragon spells" — Crucible of the Spirit
    Dragon, CR 106.6), a creature type it adds to an object, a type its mass
    effects spare (:func:`spared_types`) — and whether a filter asks for a
    creature that shares a creature type with another (Coat of Arms, Shared
    Animosity, a kinship trigger's "If it shares a creature type with this
    creature" — Mudbutton Clanger, Path of Ancestry's commander: a payoff for
    any tribe). ``yours`` leaves out a filter of an opponent's objects
    ("creatures your opponents control"), which names their tribe, not yours,
    and a type the card grants, the tribe's enabler rather than its payoff.
    A token the card makes names its types on the token, not a filter
    (``token_maker``'s subject)."""
    # A keyword's own type parameter names its subtype too ("Goblin offering" —
    # Patron of the Akki; "Champion an Elf"), and so does a spell's additional or
    # kicker cost ("sacrifice a Goblin" — Goblin Grenade), which sits beside the
    # units.
    keyword_types = {w for _kw, words in tree.card_keyword_types for w in words}
    keyword_subs = {w for w in keyword_types if w not in _CORE_TYPE_WORDS}
    spared = spared_types(tree).subtypes
    # Named on every side alike; ``theirs`` only by an opponent's filter.
    named: set[str] = keyword_subs | spared
    theirs: set[str] = set()
    # A type the card hands an object names it too, on the main page only: a
    # grant is the tribe's enabler, not a payoff for a board of it.
    granted: set[str] = set()
    cost_nodes = [
        m for unit in tree.units for c in unit.costs for m in iter_typed_nodes(c.node)
    ]
    cast_nodes = [
        m for cond in tree.card_cast_conditions for m in iter_typed_nodes(cond)
    ]
    for n in (*tree.iter_typed(), *cost_nodes, *cast_nodes):
        tag = tag_of(n)
        # A creature type the card hands an object ("That creature is a black
        # Zombie in addition to its other colors and types" — Rise from the
        # Grave; "this artifact becomes a 4/4 … Dragon artifact creature" — the
        # Monuments; a token copy "except it's a 4/4 black Zombie").
        if tag == "AddSubtype":
            sub_type = getattr(n, "subtype", None)
            if isinstance(sub_type, str) and sub_type.lower() in _SUBTYPE_WORDS:
                granted.add(sub_type)
        elif tag == "Mana":
            named.update(
                w
                for w in mana_spell_type_restriction(n).split()
                if w.lower() in CREATURE_TYPES
            )
        elif tag == "Typed" and (subs := filter_subtypes(n)):
            if filter_controller_side(n) == "opponents":
                theirs.update(subs)
            else:
                named.update(subs)
    shares = any(
        (
            tag_of(n) in ("SharesQuality", "ObjectsShareQuality")
            and getattr(n, "quality", None) == "CreatureType"
        )
        or tag_of(n) == "SharesCreatureTypeWithCommander"
        for n in tree.iter_typed()
    )
    return SubtypeRefs(frozenset(named | theirs | granted), frozenset(named), shares)


def subtype_refs(tree: ConceptTree) -> SubtypeRefs:
    """:func:`_subtype_refs`, read once per tree."""
    return memo_on(tree, "_xw_subtype_refs", _subtype_refs)


def _watches_creatures(watched: object) -> bool:
    """Whether a trigger's watched filter names creatures, an ``Or`` arm included
    ("Whenever this creature or another Ally you control enters" — Kalastria
    Healer)."""
    return any(
        tag_of(f) in OBJECT_FILTER_TAGS and filter_names_creatures(f)
        for f in or_arms(watched)
    )


def punishes_creatures_entering(unit: AbilityUnit) -> bool:
    """Whether one unit has an enters trigger that burns or drains a player as a
    creature of yours (or any player's) enters — Impact Tremors, Purphoros,
    Corpse Knight, a tribe's (Vigilante Justice's Humans, Scourge of Valkas's
    Dragons) — the trigger's own payload (:func:`drains_opponents`, any player
    reached by damage). The unit's own trigger, a granted or an emblem's one,
    and one an effect sets up for a turn (a ``CreateDelayedTrigger`` —
    Thunder of Unity's chapters) each count; an opponent's creature entering
    (Suture Priest's second trigger) is a punisher of theirs, and so is a
    curse's, watching its enchanted player's creatures (Trespasser's Curse)."""
    for n in unit.iter_typed():
        if tag_of(n) == "CreateDelayedTrigger":
            cond = getattr(n, "condition", None)
            trig, body = getattr(cond, "trigger", None), n
        elif _present(getattr(n, "trigger_zones", MISSING)):
            trig, body = n, n
        else:
            continue
        if not isinstance(trig, TypedMirrorNode) or trigger_def_event(trig) != "enters":
            continue
        watched = getattr(trig, "valid_card", None)
        if (
            filter_controller_side(watched) == "opponents"
            or getattr(watched, "controller", None) == ENCHANTED_PLAYER_SCOPE
        ):
            continue
        if _watches_creatures(watched) and drains_opponents(
            unit, body, any_player_damage=True
        ):
            return True
    return False


def keyword_bodies(tree: ConceptTree) -> frozenset[str]:
    """The keywords (:func:`keyword_subject` spelling) the card puts on bodies of
    yours: a grant to anything not an opponent's — itself, always or on a
    condition ("has flying as long as you control an artifact" — Aeronaut
    Tinkerer), but never by its own activated ability ("{2}: This creature
    gains deathtouch until end of turn" — Poison Dart Frog: an effect grants it,
    CR 113.1a, and counting a body only by a keyword it carries without paying
    is the lane's own call), what it animates ("It's a 1/1 Spirit
    creature with flying" — Abuelo's Awakening), a target or a team — a keyword
    you choose for it ("choose flying, first strike, trample, or rampage 3.
    This creature gains that ability" — Gabriel Angelfire; an Alchemy perpetual
    grant — Second Little Pig), a creature token it makes with the keyword
    (Battle Screech's Birds; a token copy "except it has flying" — Haunting
    Imitation; the Thopter Stridehangar Automaton adds to your tokens) or a
    Vehicle token with it (CR 702.122a: crewed, it becomes an artifact
    creature — Lita, Mechanical Engineer's Zeppelin), and a keyword counter it
    puts on itself or a creature of yours, one chosen at random included (CR
    122.1b — Agent's Toolkit's flying counter, Crystalline Giant) or one a
    creature enters with (Ascent of the Worthy's returned creature). Also a copy
    "except it has haste" (Dack's Duplicate, a copied creature spell —
    Choreographed Sparks), the creature spell a mana ability's mana is spent on
    (Generator Servant's haste), a creature it suspects (menace, CR 701.60c),
    the keyword a printed or granted keyword ability confers
    (:data:`KEYWORD_ABILITY_KEYWORDS`: dash's haste), and what a residue phase
    parked puts on a body (``ConceptNode.body_keywords``). The bodies a keyword
    deck counts."""
    return memo_on(tree, "_xw_keyword_bodies", _keyword_bodies)


def made_keyword_bodies(tree: ConceptTree) -> frozenset[str]:
    """The :func:`keyword_bodies` of the bodies the card is or makes — itself
    (a self-grant, its printed keyword abilities' conferred keyword, its
    animation), a creature token, a copy, a permanent it animates or cloaks —
    without its grants onto another permanent (an Aura's "Enchanted creature
    has defender", a target's counter). A body with defender of yours (CR
    702.3b) where a grant of defender is a drawback ("Enchanted creature has
    defender" — Guard Duty)."""
    return memo_on(
        tree, "_xw_made_keyword_bodies", partial(_keyword_bodies, made_only=True)
    )


def own_keyword_bodies(tree: ConceptTree) -> frozenset[str]:
    """The :func:`made_keyword_bodies` of the card's own body alone: a grant to
    itself, always or on a condition (Noble Banneret's "this creature and those
    creatures … have lifelink"; never by its own activated ability, as
    :func:`keyword_bodies` reads it), and its printed keyword
    abilities' conferred keyword — never a token, copy or other permanent it
    makes. Like the rest of the family it leaves the printed keywords themselves
    to the record's ``keywords``."""
    return memo_on(
        tree, "_xw_own_keyword_bodies", partial(_keyword_bodies, own_only=True)
    )


def _keyword_bodies(
    tree: ConceptTree, *, made_only: bool = False, own_only: bool = False
) -> frozenset[str]:
    out: set[str] = set()
    creature = "Creature" in tree.card_types
    printed = {normalised_keyword_name(k) for k in tree.card_keywords}
    if ("suspend" in printed and creature) or any(
        suspends_own_card(u) for u in tree.units
    ):
        out.add("haste")  # CR 702.62a: a creature spell cast this way gains haste
    out.update(
        KEYWORD_ABILITY_KEYWORDS[k] for k in printed & KEYWORD_ABILITY_KEYWORDS.keys()
    )
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node, deep=True):
            affected = getattr(sdef, "affected", None)
            if filter_controller_side(affected) == "opponents":
                continue
            if made_only and not _makes_body(unit, sdef):
                continue
            if own_only and tag_of(affected) != "SelfRef":
                continue
            if unit.kind == "Activated" and tag_of(affected) == "SelfRef":
                continue  # an activated self-grant (Poison Dart Frog's {2})
            if tag_of(mod) == "AddKeyword":
                kw = mod_keyword_name(mod) or ""
                out |= _keyword_with_conferred(kw)
                # a creature card suspending itself (Epochrasite) is cast with
                # haste (CR 702.62a)
                if (
                    creature
                    and normalised_keyword_name(kw) == "suspend"
                    and (tag_of(affected) == "SelfRef")
                ):
                    out.add("haste")
            elif tag_of(mod) == "AddChosenKeyword":
                # the choice is the unit's own, or one the card makes as it
                # enters ("As ~ enters, choose two abilities from among first
                # strike, vigilance, and lifelink" — Greymond, Avacyn's Stalwart)
                out.update(
                    _chosen_keyword_options(unit)
                    or {k for u in tree.units for k in _chosen_keyword_options(u)}
                )
        if own_only:
            continue  # the node and effect arms are bodies the card makes
        for n in unit.iter_typed():
            if not made_only or not _grants_or_unowned(unit, n):
                out |= _keyword_body_node(unit, n)
        for c in unit.effects:
            out.update(c.made_body_keywords if made_only else c.body_keywords)
    out.discard("")
    return frozenset(out)


#: The :func:`_keyword_body_node` arms that grant a keyword to a body already
#: there — a spell the mana is spent on, a creature suspected, a keyword counter
#: on a target, a perpetual grant. Every other arm's body is one the card makes:
#: a token, a copy, an animation, a cloaked card, a creature entering with a
#: counter.
_GRANT_BODY_TAGS = frozenset(
    {
        "Mana",
        "Suspect",
        "PutCounter",
        "PutCounterAll",
        "ChooseCounterKind",
        "ApplyPerpetual",
    }
)


def _grants_or_unowned(unit: AbilityUnit, n: TypedMirrorNode) -> bool:
    """Whether a :func:`_keyword_body_node` arm puts its keyword on no body the
    card makes for you: a grant arm (:data:`_GRANT_BODY_TAGS`), or a token whose
    creator could be anyone ("its controller creates" — Basalt Golem's blocker's
    controller, CR 111.2)."""
    tag = tag_of(n)
    if tag in _GRANT_BODY_TAGS:
        return True
    return tag in ("Token", "CopyTokenOf") and token_creator_side(unit, n) == "any"


def _makes_body(unit: AbilityUnit, sdef: object) -> bool:
    """Whether a static def of ``unit`` is the card's own body (``SelfRef``) or
    one it makes: its modifications make its object a creature ("Enchanted land is
    a 2/6 white Wall creature with defender" — Guardian Zendikon), a target of
    yours when the object is the chain's target (never "target noncreature
    artifact they control becomes a 0/4 Wall artifact creature with defender" —
    Welcome to . . .)."""
    affected = getattr(sdef, "affected", None)
    if tag_of(affected) == "SelfRef":
        return True
    if not adds_creature_type(sdef):
        return False
    if tag_of(affected) == "ParentTarget":
        return filter_controller_side(root_target_filter(unit)) == "you"
    return True


def suspends_own_card(unit: AbilityUnit) -> bool:
    """Whether ``unit`` gives suspend to a card of yours it exiles, one that may be
    a creature card: from your hand (Jhoira of the Ghitu's cost), the top of your
    library (The Tenth Doctor, Sibylline Soothsayer), your graveyard (Doom's Time
    Platform) or the spell you cast (Taigam, Master Opportunist). CR 702.62a: you
    may cast it as its last time counter is removed, and a creature spell cast
    this way gains haste. The card the chain exiles is read by the first effect
    that picks it: a library exile by whose library it takes
    (:func:`exiled_library_side`), an exile by whether it may take another
    player's card (:func:`_exiles_other_players_card` — never Delay's countered
    spell or Suspend's target creature), a counter on the card a cost exiled by
    that cost's filter. A watched spell that can't be a creature (Gandalf of the
    Secret Fire's instants and sorceries) gains no haste."""
    if not any(
        tag_of(mod) == "AddKeyword"
        and normalised_keyword_name(mod_keyword_name(mod) or "") == "suspend"
        and tag_of(getattr(sdef, "affected", None))
        in ("ParentTarget", "TriggeringSource")
        for sdef, mod in iter_mod_sites(unit.node, deep=True)
    ):
        return False
    watched = getattr(unit.node, "valid_card", None)
    cores = set(filter_core_types(watched))
    if cores and "Creature" not in cores:
        return False
    for c in unit.effects:
        n = c.node
        tag = tag_of(n)
        if tag in LIBRARY_EXILE_TAGS:
            return exiled_library_side(unit.node, n, unit) == "you"
        if tag in ("ChangeZone", "ChangeZoneAll") and change_zone_dirs(n)[1] == "Exile":
            return not _exiles_other_players_card(unit, n)
        target = getattr(n, "target", None)
        if tag == "PutCounter" and tag_of(target) == "CostPaidObject":
            return any(
                tag_of(leaf) == "Exile"
                and filter_controller_side(getattr(leaf, "filter", None)) == "you"
                for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
            )
    return False


def lets_defenders_attack(unit: AbilityUnit) -> bool:
    """Whether ``unit`` lets creatures that aren't an opponent's attack as though
    they didn't have defender — a payoff for creatures with defender (CR 702.3b:
    "A creature with defender can't attack"): a ``CanAttackWithDefender`` static
    (High Alert's team, Rolling Stones' Walls, Warmonger's Chariot's equipped
    creature) or the mode a grant adds (``AddStaticMode`` — Assault Formation's
    target, Teyo, Aegis Adept's perpetual one). A creature letting only itself
    attack (Backstreet Bruiser, "as long as it's enchanted or equipped")
    rewards no population."""

    def others(sdef: object) -> bool:
        affected = getattr(sdef, "affected", None)
        return (
            tag_of(affected) != "SelfRef"
            and filter_controller_side(affected) != "opponents"
        )

    if any(
        static_mode_tag(sdef) == "CanAttackWithDefender" and others(sdef)
        for sdef in iter_static_defs(unit.node, granted=True)
    ):
        return True
    return any(
        tag_of(mod) == "AddStaticMode"
        and getattr(mod, "mode", None) == "CanAttackWithDefender"
        and others(sdef)
        for sdef, mod in iter_mod_sites(unit.node, deep=True)
    )


#: The keyword a keyword ability confers on the permanent it puts onto the
#: battlefield (folded, :func:`normalised_keyword_name`): dash "As long as this
#: permanent's dash cost was paid, it has haste" (CR 702.109a), blitz likewise
#: (702.152a), encore's tokens "gain haste" (702.141a), unearth's returned card
#: "gains haste" (702.84a), awaken's land "becomes a 0/0 Elemental creature with
#: haste" (702.113a), riot's "If you don't, it gains haste" (702.136a — a
#: granted riot, Domri, Chaos Bringer's), afterlife's "Spirit creature tokens
#: with flying" (702.135a — a granted afterlife, Afterlife Insurance's),
#: disguise's "2/2 face-down creature with ward {2}" (702.168a — Fugitive
#: Codebreaker). Suspend's haste is a creature spell's only (702.62a), read off a
#: creature card's own suspend.
KEYWORD_ABILITY_KEYWORDS: dict[str, str] = {
    "dash": "haste",
    "blitz": "haste",
    "encore": "haste",
    "unearth": "haste",
    "awaken": "haste",
    "riot": "haste",
    "afterlife": "flying",
    "disguise": "ward",
}


#: A keyword variant that is the keyword itself (folded): "A 'hexproof from
#: [quality]' ability is a hexproof ability" (CR 702.11d).
KEYWORD_VARIANTS: dict[str, str] = {"hexprooffrom": "hexproof"}


def _keyword_with_conferred(kw: str) -> set[str]:
    """A granted keyword (:func:`keyword_subject` spelling), the keyword it
    confers (:data:`KEYWORD_ABILITY_KEYWORDS`: a granted encore's haste —
    Araumi of the Dead Tide) and the keyword it is a variant of
    (:data:`KEYWORD_VARIANTS`: hexproof from blue is hexproof)."""
    folded = normalised_keyword_name(kw)
    return {
        keyword_subject(kw),
        KEYWORD_ABILITY_KEYWORDS.get(folded, ""),
        KEYWORD_VARIANTS.get(folded, ""),
    }


def _chosen_keyword_options(unit: AbilityUnit) -> set[str]:
    """The keywords a ``Choose`` of a keyword on ``unit`` offers (Gabriel
    Angelfire's "flying, first strike, trample, or rampage 3")."""
    out: set[str] = set()
    for n in unit.iter_typed():
        choice = choice_of(n)
        if choice is not None and choice.kind == "Keyword":
            out.update(keyword_subject(k) for k in choice.options if k.isalpha())
    return out


def counter_keyword(kind: object) -> str:
    """A counter kind's keyword (:data:`_KEYWORD_COUNTERS`), or ``""``."""
    if not isinstance(kind, str):
        return ""
    return _KEYWORD_COUNTERS.get(normalised_keyword_name(kind).replace("_", ""), "")


def _keyword_names(node: object, field: str) -> set[str]:
    """The keywords in ``node``'s keyword list ``field``, in
    :func:`keyword_subject` spelling: a plain one (``"Flying"``) or a
    parameterized one by its name (a token's ``{Ward: {2}}`` — Fugitive of the
    Judoon), each with what it confers (:func:`_keyword_with_conferred`)."""
    out: set[str] = set()
    for k in list_field(node, field):
        name = _keyword_entry_name(k)
        if name is not None:
            out |= _keyword_with_conferred(name)
    out.discard("")
    return out


def _copy_keywords(n: TypedMirrorNode) -> set[str]:
    """The keywords a copy effect's exceptions add (``additional_modifications``'
    ``AddKeyword``\\ s — "except it has haste")."""
    return {
        keyword_subject(mod_keyword_name(m) or "")
        for m in list_field(n, "additional_modifications")
        if tag_of(m) == "AddKeyword"
    }


def _keyword_body_node(unit: AbilityUnit, n: TypedMirrorNode) -> set[str]:
    """The keywords one node of ``unit`` puts on a body of yours
    (:func:`keyword_bodies`' node-level arms)."""
    tag = tag_of(n)
    if tag in ("Token", "CopyTokenOf"):
        if token_creator_side(unit, n) == "opponents":
            return set()
        if tag == "CopyTokenOf":
            return _keyword_names(n, "extra_keywords") | _copy_keywords(n)
        types = list_field(n, "types")
        if "Creature" in types or "Vehicle" in types:
            return _keyword_names(n, "keywords")
        return set()
    # A copy "except it has haste" (CR 707.9b): the copy is what the effect makes
    # yours — a clone entering (Dack's Duplicate), a copied spell (Choreographed
    # Sparks), a creature becoming a copy (Oko, the Ringleader).
    if tag in ("BecomeCopy", "CopySpell"):
        return _copy_keywords(n)
    # The creature spell a mana ability's mana is spent on "gains haste until end
    # of turn" (Generator Servant).
    if tag == "Mana":
        return {
            conferred
            for g in list_field(n, "grants")
            if isinstance(g, MirrorVariant) and g.key == "AddKeywordUntilEndOfTurn"
            for kw in (getattr(g.inner, "keyword", None),)
            if isinstance(kw, str)
            for conferred in _keyword_with_conferred(kw)
        }
    if filter_controller_side(getattr(n, "target", None)) == "opponents":
        return set()
    if tag == "Suspect":
        return {"menace"}  # CR 701.60c: a suspected permanent has menace
    # What an animation makes the permanent: earthbend's "becomes a 0/0 land
    # creature with haste" (CR 701.66a — Toph, the Blind Bandit).
    if tag == "Animate":
        return _keyword_names(n, "keywords")
    # A card you cloak "becomes a 2/2 face-down creature card with ward {2}" (CR
    # 701.58a — Vannifar, Evolved Enigma).
    if tag == "Cloak":
        return {"ward"} if getattr(n, "enters_under", None) == "You" else set()
    if tag in ("PutCounter", "PutCounterAll"):
        return {counter_keyword(counter_kind(n))}
    if tag == "ChooseCounterKind":
        domain = getattr(n, "domain", None)
        return {counter_keyword(k) for k in list_field(domain, "kinds")}
    if tag in ("ChangeZone", "ChangeZoneAll"):
        if getattr(n, "destination", None) != "Battlefield":
            return set()
        return {
            counter_keyword(entry[0])
            for entry in list_field(n, "enter_with_counters")
            if isinstance(entry, list) and entry
        }
    if tag == "ApplyPerpetual":
        return _keyword_names(getattr(n, "modification", None), "keywords")
    # A replacement adding a creature token to the ones you create (Stridehangar
    # Automaton's Thopter, CR 614.1a).
    if getattr(n, "token_owner_scope", None) != "You":
        return set()
    return {
        kw
        for chars in replacement_token_specs(n)
        if "Creature" in list_field(chars, "core_types")
        for kw in _keyword_names(chars, "keywords")
    }


def made_token_subtypes(tree: ConceptTree) -> tuple[tuple[str, str], ...]:
    """``(subtype, how)`` per creature type a token the card makes gets beside
    the ones its ``Token`` node types (``token_maker``'s subjects): a token
    copy you create "except it's a Spirit in addition to its other types"
    (``"copy"`` — Hofri Ghostforge), the Army of an "amass Goblins N" you
    perform (``"amass"``, CR 701.47a), and a creature type you choose from a
    printed list for the tokens it makes ("choose white Citizen, … red Goblin,
    or green Saproling. {3}, {T}: Create a 1/1 creature token of the chosen
    color and type" — ``"chosen"``, Sarpadian Empires, Vol. VII). Raw
    spelling; the caller resolves it against its creature-type vocabulary."""
    out: list[tuple[str, str]] = []
    for unit in tree.units:
        for n in unit.iter_typed():
            if tag_of(n) != "CopyTokenOf" or token_creator_side(unit, n) == "opponents":
                continue
            out.extend(
                (sub, "copy")
                for mod in list_field(n, "additional_modifications")
                if tag_of(mod) == "AddSubtype"
                and isinstance(sub := getattr(mod, "subtype", None), str)
            )
    for event in keyword_action_events(tree):
        if event.tag == "Amass" and event.yours:
            out.extend(
                (sub, "amass")
                for n in event.unit.iter_typed()
                if tag_of(n) == "Amass"
                and isinstance(sub := getattr(n, "subtype", None), str)
            )
    # A creature token of yours with no creature type beside a choice from a
    # printed list ("Red goblin"): the token takes the chosen option's type.
    # Phase-misparse workaround: phase v0.104.0 types no "of the chosen color and
    # type" on the token, so the choice and the token are joined card-wide.
    # Retire when test_chosen_token_type_canary fails RETIRE-READY.
    labeled = [
        word
        for n in tree.iter_typed()
        if (choice := choice_of(n)) is not None and choice.kind == "Labeled"
        for option in choice.options
        for word in option.split()
        if word.lower() in CREATURE_TYPES
    ]
    if labeled and any(
        tag_of(n) == "Token"
        and "Creature" in (types := list_field(n, "types"))
        and not any(t.lower() in CREATURE_TYPES for t in types if isinstance(t, str))
        and token_creator_side(unit, n) != "opponents"
        for unit in tree.units
        for n in unit.iter_typed()
    ):
        out.extend((word, "chosen") for word in labeled)
    return tuple(out)


def makes_equipment(tree: ConceptTree, sides: frozenset[str]) -> bool:
    """Whether the card makes an Equipment (CR 301.5): a token whose types
    include Equipment, created by a player on one of ``sides``
    (:func:`token_creator_side` — Iron Hills Blacksmith, U.S.Agent's Sturdy
    Shield), or a static that adds the Equipment subtype to your artifacts (Dan
    Lewis, Gemcutter Buccaneer, Arterial Alchemy) — that grant arm reads no
    side, ``sides`` gates the tokens only."""
    for unit in tree.units:
        for n in unit.iter_typed():
            tag = tag_of(n)
            if (
                tag == "Token"
                and "Equipment" in list_field(n, "types")
                and token_creator_side(unit, n) in sides
            ):
                return True
            if tag == "AddSubtype" and getattr(n, "subtype", None) == "Equipment":
                return True
    return False


#: The keyword counters (CR 122.1b: "flying, first strike, double strike,
#: deathtouch, decayed, exalted, haste, hexproof, indestructible, lifelink,
#: menace, reach, shadow, trample, and vigilance"), squashed spelling → the
#: :func:`keyword_subject` spelling.
_KEYWORD_COUNTERS: dict[str, str] = {
    kw.replace(" ", ""): kw
    for kw in (
        "flying",
        "first strike",
        "double strike",
        "deathtouch",
        "decayed",
        "exalted",
        "haste",
        "hexproof",
        "indestructible",
        "lifelink",
        "menace",
        "reach",
        "shadow",
        "trample",
        "vigilance",
    )
}
#: The keyword counter kinds by their squashed spelling (``firststrike``).
KEYWORD_COUNTER_KINDS: frozenset[str] = frozenset(_KEYWORD_COUNTERS)
