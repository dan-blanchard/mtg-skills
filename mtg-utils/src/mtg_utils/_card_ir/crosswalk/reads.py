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
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, get_args

from mtg_utils._card_ir.creature_types import CREATURE_TYPES
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk.core import AbilityUnit, ConceptTree


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
_OPPONENT_ACTOR_TAGS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent"}
)
_EACH_ACTOR_TAGS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})


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


def _scope_from_player_node(node: object) -> str | None:
    """Map a player-reference typed node to a Signal scope, or None if unknown.

    Reads the node's discriminator tag (``Controller`` / ``Opponent`` / …) and,
    for a ``Typed`` filter, its ``controller`` — never oracle text.
    """
    t = tag_of(node)
    if t in ("Controller", "SelfRef", "You"):
        return "you"
    if t in _OPPONENT_ACTOR_TAGS:
        return "opponents"
    if t in _EACH_ACTOR_TAGS:
        return "each"
    # A chosen/targeted player (``ParentTarget`` / ``Player`` / ``Any``) is NOT a
    # self resource — "target player draws, then discards" is a targeted effect,
    # not a self-loot outlet; the live self-loot lane scopes it out. Map to "any"
    # so a maker lane gated to you/each does not over-fire on it.
    if t in ("ParentTarget", "Player", "Any", "Target"):
        return "any"
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
_DIRECTED_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "ParentTargetController",
        "EventTargetController",
        "TriggeringPlayer",
        "ParentTarget",
        "Player",
        "Target",
        "Any",
    }
)


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
    | _OPPONENT_ACTOR_TAGS
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
    return any(
        tag_of(n) == "ScopedPlayer" or getattr(n, "controller", None) == "ScopedPlayer"
        for n in _iter_typed_nodes(node)
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


def filter_admits(filt: object, facts: ObjectFacts) -> bool | None:
    """Whether a phase object filter can describe the card ``facts`` describes.

    Reads the type words (``Permanent`` and ``Card`` admit any type), the negated
    ones ("noncreature"), subtypes, the
    supertype / token / colorless properties, and recurses ``Or`` (any) / ``And``
    (all). ``SelfRef`` (the filter's own card) is ``False``. ``None`` when the filter
    is a reference this read can't resolve (``ParentTarget``, ``AttachedTo``, …) —
    the caller resolves those against their own context."""
    tag = tag_of(filt)
    if tag == "SelfRef":
        return False
    if tag == "StackSpell":
        return True  # "a spell" — the And beside it carries the constraint
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


def effect_reaches_player(node: TypedMirrorNode, root: object | None = None) -> bool:
    """Whether a damage EFFECT reaches a PLAYER (CR 120.1), read structurally.

    The direct-damage / burn gate: a creature-only bite ("4 damage to target
    creature" — Flame Slash; "2 to each creature" — Pyroclasm) is removal, not burn.

    * ``DamageEachPlayer`` always hits players.
    * ``DamageAll`` hits players iff it carries a ``player_filter`` (Pestilence pings
      creatures AND each player; Pyroclasm-as-``DamageAll`` has none) OR its
      ``target`` reaches one via the SAME :func:`_damage_target_reaches_player`
      discriminator ``DealDamage`` uses (ADR-0038 W6 endgame: a multi-target
      "any number of target creatures and/or players" burn spell — Firestorm,
      Meteor Blast, Comet Storm — and a "deals N damage to each of your
      opponents" ability with no fixed permanent-type restriction — Aurelia,
      the Law Above, Chandra planeswalkers — both serialize their recipient
      into ``target`` rather than ``player_filter``; a creature-only sweep
      (Pyroclasm's own ``target=Typed(type_filters=['Creature'])``) stays
      excluded via the SAME non-empty-filter/no-"Player"-word rule that
      excludes creature-only ``DealDamage``. Full-corpus scan: 253 commander-
      legal ``DamageAll`` nodes with no ``player_filter``, 238 correctly stay
      excluded (creature-typed sweeps), 15 gain — CR 120.1).
    * ``DealDamage`` defers to :func:`_damage_target_reaches_player` on its
      ``target`` (empty when absent, per the pre-existing gate). ``root`` —
      the enclosing ability unit's node, when the caller has it — resolves a
      bare ``ParentTarget`` recipient (see that function's docstring);
      omitting it is conservative (a ``ParentTarget`` recipient never reaches).
    """
    t = tag_of(node)
    if t == "DamageEachPlayer":
        return True
    if t == "DamageAll":
        if _present(getattr(node, "player_filter", MISSING)):
            return True
        tgt = getattr(node, "target", MISSING)
        if not _present(tgt):
            return False
        return _damage_target_reaches_player(tgt, root)
    if t == "DealDamage":
        tgt = getattr(node, "target", MISSING)
        if not _present(tgt):
            return False
        return _damage_target_reaches_player(tgt, root)
    if t == "EachSourceDealsDamage":
        rec = damage_recipient(node)
        if rec is None:
            return False
        if tag_of(rec) == "EachController":
            return True  # each source hits its own controller — a player
        if tag_of(rec) == "OtherBatchSource":
            return False  # another creature in the batch
        return _damage_target_reaches_player(rec, root)
    return False


def _damage_target_reaches_player(tgt: object, root: object | None = None) -> bool:
    """Whether a ``DealDamage`` TARGET node names a recipient that reaches a
    PLAYER (CR 120.1 / 115.4), recursing through an ``Or`` alternation.

    * ``Typed`` with a NON-EMPTY ``type_filters`` is a creature/permanent/
      battle-typed bite ("target creature" — Flame Slash; "target
      attacking creature" — Femeref Archers) — removal, NOT direct,
      UNLESS the words include "Player" explicitly. An EMPTY
      ``type_filters`` carries NO card-type restriction at all — phase
      uses this bare shape both for a controller-scoped player ("target
      opponent" — controller='Opponent'; Lava Axe's sibling Aragorn, the
      Uniter) and for a fully unrestricted recipient ("any other
      target" — Self-Destruct, Screaming Nemesis; controller=None).
      Both reach a player; only a POSITIVE type word ever excludes.
    * ``Any`` / ``Target`` (bare "any target") always reach.
    * ``SourceChosenPlayer`` / ``TriggeringPlayer`` chosen/triggering
      player forms (CR 120.1) reach — the pre-existing chosen-player
      gate.
    * ``ScopedPlayer`` ("that player" — a per-player-loop back-reference,
      Ancient Runes "each player's upkeep ... deals damage to that
      player"), ``ParentTargetController`` ("that creature's/permanent's/
      land's controller" — a controller is always a player, CR 102.1;
      Ankh of Mishra, Backfire), and ``DefendingPlayer`` ("defending
      player" — the attacked player, CR 506.4c; Falkenrath Perforator)
      are bare zero-field player-designator marker tags: always reach.
      A bare ``Controller`` (the SOURCE's OWN controller — "deals 2
      damage to you", Voltaic Visionary) stays the incidental
      SELF-damage exclusion (``_scope_from_player_node`` maps it "you",
      excluded below) — distinct from ``ParentTargetController``, which
      names a DIFFERENT (targeted/tracked) object's controller.
    * ``ParentTarget`` (bare — no ``Controller`` suffix) is
      POSITION-relative (the ADR-0038 boundary lesson): it binds to
      whatever EARLIER clause in the SAME ability produced the target, so
      the tag is ambiguous read alone. A modal "instead" amendment clause
      that re-quotes an earlier "target creature" (Fiery Impulse "deals 2
      damage to target creature. ... it deals 3 damage instead", Thermal
      Blast, Unholy Heat — pure creature removal) carries the SAME
      ``ParentTarget`` tag as a genuine player back-reference (Aggressive
      Sabotage's "Target player discards two cards. If this spell was
      kicked, it deals 3 damage to that player."; Curse of Shaken Faith's
      "Enchant player" + "... deals 2 damage to them"). When ``root`` (the
      enclosing ability unit) is supplied, resolve it by asking whether
      that SAME ability establishes an explicit (non-``ParentTarget``)
      player target anywhere else (:func:`_unit_has_player_target`) — the
      producer a genuine back-reference binds to. With no ``root``,
      conservative: never reaches (matches every corpus member that
      DOESN'T need it — the creature-removal modal tail above).
    * ``Or`` recurses into each alternative filter ("target player or
      planeswalker" — Lava Axe's post-2020 template, CR 115.4): the
      whole target reaches iff ANY alternative does.
    """
    tt = tag_of(tgt)
    if tt == "Typed":
        words = _filter_type_words(tgt)
        if words:
            return "Player" in words  # creature/permanent typed → removal
        return True  # no type restriction at all → names a player
    if tt in ("Any", "Target"):
        return True
    if tt in _CHOSEN_PLAYER_TARGETS:
        return True
    if tt in (
        "ScopedPlayer",
        "ParentTargetController",
        "EventTargetController",
        "DefendingPlayer",
    ):
        return True
    if tt == "Or":
        return any(
            _damage_target_reaches_player(f, root)
            for f in (getattr(tgt, "filters", None) or ())
        )
    if tt == "ParentTarget":
        # Deliberately excluded from the generic ``_scope_from_player_node``
        # fallback: that helper maps bare ``ParentTarget`` to scope "any"
        # for OTHER lanes' purposes (a chosen/targeted-object read), which
        # would silently readmit the position-relative over-fire this
        # function's docstring documents. Resolved via sibling context when
        # available; conservative (no reach) otherwise.
        return root is not None and _unit_has_player_target(root)
    sc = _scope_from_player_node(tgt)  # a direct player node
    return sc in ("opponents", "each", "any")


# Player-reference target tags that name a specific chosen / triggering player —
# a valid direct-damage recipient (CR 120.1) though not a fixed-scope node.
_CHOSEN_PLAYER_TARGETS: frozenset[str] = frozenset(
    {"SourceChosenPlayer", "TriggeringPlayer"}
)


def _unit_has_player_target(root: object) -> bool:
    """Whether ability ``root`` establishes an explicit (non-``ParentTarget``)
    player-reaching TARGET anywhere in its own structure — the producer a
    bare ``ParentTarget`` damage recipient can legitimately bind back to
    within the SAME ability (Aggressive Sabotage's "Target player discards
    two cards. If this spell was kicked, it deals 3 damage to that player.";
    Blood Oath's "Target opponent reveals their hand. ... deals 3 damage to
    that player ..."). Scans every ``_SCOPE_FIELDS`` slot on every typed node
    reachable under ``root`` (:func:`_iter_typed_nodes`) — cost/target/static
    fields alike, since the producer can be a non-damage effect (Discard,
    RevealHand) or the ability's own enchant/attach target.

    ADR-0039 W7: also recognizes a bare ``optional_for`` STRING marker
    ("AnyOpponent" / "AnyPlayer") a sibling node carries — phase's "may have
    you <effect>" optional-choice shape (Sin Prodder's "Any opponent may
    have you put that card into your graveyard. If a player does, ~ deals
    damage to that player...") names the CHOOSING player only as this raw
    string, never a typed player node, so it never populates any
    ``_SCOPE_FIELDS`` slot. Corpus-verified: 26 commander-legal nodes carry
    ``optional_for`` (18 ``AnyPlayer`` / 8 ``AnyOpponent``), and Sin Prodder
    is the ONLY one whose ``direct_damage`` membership actually turns on
    this read — every other hit is already served via its own explicit
    typed target. A bare string always names a player (never a creature/
    permanent), so no further discrimination is needed.
    """
    for n in _iter_typed_nodes(root):
        for fname in _SCOPE_FIELDS:
            sub = getattr(n, fname, MISSING)
            if (
                _present(sub)
                and tag_of(sub) != "ParentTarget"
                and _damage_target_reaches_player(sub)
            ):
                return True
        opt = getattr(n, "optional_for", MISSING)
        if _present(opt) and opt in _OPTIONAL_FOR_PLAYER_VALUES:
            return True
    return False


# The two observed string values of a bare ``optional_for`` marker (a raw
# str field, never a typed player node) — both always name a player.
_OPTIONAL_FOR_PLAYER_VALUES = frozenset({"AnyOpponent", "AnyPlayer"})


def has_nested_damage_reaching_player(node: object) -> bool:
    """Whether a ``DealDamage``/``DamageAll``/``DamageEachPlayer`` node
    reaching a PLAYER (CR 120.1) is reachable ANYWHERE under ``node`` — a
    damage effect buried inside a granted activated/static ability's
    ``GrantAbility``/``GrantStaticAbility`` ``.definition`` (Barbed Field's
    "Enchanted land has '{T}: ... deals 1 damage to any target.'", Acidic
    Sliver's lord-granted "All Slivers have '{2}, Sacrifice ...: ... deals
    2 damage to any target.'") or a ``CreateToken`` token-ability
    definition (Dance with Devils's "When this token dies, it deals 1
    damage to any target") — none of which the flat per-unit
    ``effect_concepts`` walk ever surfaces as its own top-level concept.
    The ``direct_damage`` lane's structural fallback, the
    :func:`has_nested_fight` sibling. ``node`` doubles as the ``root``
    :func:`effect_reaches_player` resolves a bare ``ParentTarget`` recipient
    against (the SAME ability owns both the grant and its nested damage).
    """
    return any(
        tag_of(n) in DAMAGE_EFFECT_TAGS and effect_reaches_player(n, node)
        for n in _iter_typed_nodes(node)
    )


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


def _trigger_event(trig: TypedMirrorNode) -> str:
    """Derive a normalized trigger event from a phase trigger's typed shape.

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


def filter_controller(filt: object) -> str | None:
    """The phase ``controller`` of a typed filter (``"You"`` / ``"Opponent"`` /
    ``None``), recursing ``Or`` / ``And`` to the first that names one.
    """
    t = tag_of(filt)
    if t == "Typed":
        c = getattr(filt, "controller", None)
        return c if isinstance(c, str) else None
    if t in ("Or", "And"):
        for sub in getattr(filt, "filters", ()) or ():
            c = filter_controller(sub)
            if c is not None:
                return c
    return None


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


def count_operand_qty(node: TypedMirrorNode) -> object | None:
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
    """
    for fname in ("amount", "count", "value", "announced_x"):
        q = getattr(node, fname, MISSING)
        if not _present(q):
            continue
        if tag_of(q) == "Multiply":
            q = getattr(q, "inner", None)
        if tag_of(q) == "Ref":
            qty = getattr(q, "qty", None)
            if isinstance(qty, TypedMirrorNode):
                return qty
    dc = getattr(node, "dynamic_count", MISSING)
    if isinstance(dc, TypedMirrorNode):
        return dc
    return None


# Recipient tags marking a discard DIRECTED at another player (CR 701.9): a targeted
# player ("target player / opponent discards" — Mind Rot, Stupor), or an explicit
# opponent. A you/controller recipient is a self-loot (the ported ``discard_makers``
# lane), not this hand-attack.
_DISCARD_OPP_TAGS: frozenset[str] = _OPPONENT_ACTOR_TAGS | frozenset(
    {
        "Player",
        "Target",
        "ParentTarget",
        "Any",
        "TargetPlayer",
        "TriggeringPlayer",
        "ParentTargetController",
    }
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
    :func:`_trigger_event` reads on the trigger side.

    Reanimation is ``(Graveyard, Battlefield)``; a blink exile is
    ``(_, Exile)`` and its return ``(_, Battlefield)``. Exposing them on the effect
    side lets the GY-engine / flicker lanes read the zone change STRUCTURALLY rather
    than from a post-hoc recovered field.
    """
    return (
        getattr(node, "origin", None),
        getattr(node, "destination", None),
    )


def additional_phase_kind(node: TypedMirrorNode) -> str:
    """The lowercased ``phase`` of an ``AdditionalPhase`` effect (CR 505 / 506), or
    ``""`` when absent.

    Phase carries the granted extra phase on ``AdditionalPhase.phase``
    (``"BeginCombat"`` — Aurelia, Moraug, Combat Celebrant). The ``extra_combats``
    lane gates on it being a combat phase, mirroring ``project._EXTRA_PHASE``: phase
    v0.9.0 only structurally emits a combat phase here (it mis-routes
    extra-upkeep/draw/end to combat, recovered by a separate ``project`` marker), so
    the combat read mirrors the live ``extra_combats`` exactly.
    """
    p = getattr(node, "phase", MISSING)
    return p.lower() if isinstance(p, str) else ""


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
        t in _OPPONENT_ACTOR_TAGS
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
_EFFECT_CHILD_FIELDS = (
    "effect",
    "sub_ability",
    "execute",
    "chosen_pile_effect",
    "unchosen_pile_effect",
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
        for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities", "static_abilities"):
            child = getattr(node, fname, MISSING)
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
    kw = getattr(mod, "keyword", MISSING)
    if isinstance(kw, str):
        return kw
    if isinstance(kw, MirrorVariant):
        return kw.key
    if isinstance(kw, TypedMirrorNode):
        return tag_of(kw)
    return None


def token_profile_keywords(node: object) -> tuple[str, ...]:
    """The keyword NAMES a ``Token`` effect's profile carries (CR 111.4).

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
        if isinstance(kw, str):
            out.append(kw)
        elif isinstance(kw, MirrorVariant):
            out.append(kw.key)
        elif isinstance(kw, TypedMirrorNode):
            t = tag_of(kw)
            if t is not None:
                out.append(t)
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
      — Dragon Broodmother's Dragon token's ``{Devour: 2}``, CR 111.4).

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
    :func:`mod_keyword_name` reads (CR 702.51 / 601.3e).
    """
    if not isinstance(node, TypedMirrorNode) or tag_of(node) != "GrantNextSpellAbility":
        return None
    modifier = getattr(node, "modifier", MISSING)
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


def iter_static_defs(root: object) -> Iterator[TypedMirrorNode]:
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
    """
    yield from _static_defs(root)


def _static_defs(root: object) -> tuple[TypedMirrorNode, ...]:
    if isinstance(root, TypedMirrorNode):
        cached = root.__dict__.get(_STATIC_DEFS_CACHE_ATTR)
        if cached is None:
            cached = tuple(_walk_static_defs(root))
            object.__setattr__(root, _STATIC_DEFS_CACHE_ATTR, cached)
        return cached
    return tuple(_walk_static_defs(root))


def _walk_static_defs(root: object) -> Iterator[TypedMirrorNode]:
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        if _is_static_def(node):
            yield node
        for fname in (
            *_EFFECT_CHILD_FIELDS,
            "mode_abilities",
            "static_abilities",
            "statics",
        ):
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif _present(child) and isinstance(child, list):
                stack.extend(child)


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


def has_nested_flip_coin(node: object) -> bool:
    """Whether a ``FlipCoin`` tag (CR 705.1) is reachable ANYWHERE under
    ``node`` — a coin flip buried inside a granted activated ability's
    ``GrantAbility.definition`` (Frenetic Sliver's "All Slivers have
    '{0}: ... flip a coin ...'") that the flat per-unit concept-node walk
    never surfaces as its own node (the concept node IS the GrantAbility
    modification itself, carrying no ``flip_coin``-mapped tag of its own).
    The ``coin_flip`` lane's structural fallback, the
    :func:`has_nested_roll_die` sibling.
    """
    return any(tag_of(n) == "FlipCoin" for n in _iter_typed_nodes(node))


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
    vote outcome), a ``FlipCoin``/``FlipCoins`` ``win_effect`` (Stitch in
    Time, Ral Zarek's -7), or a static ability's ``GrantAbility.
    definition`` (Ichormoon Gauntlet's granted planeswalker loyalty
    ability) — none of which ``_walk_effects``'s narrow
    ``_EFFECT_CHILD_FIELDS`` walk (``effect`` / ``sub_ability`` /
    ``execute`` / ``mode_abilities``) ever reaches, since ``per_choice_
    effect`` / ``win_effect`` / a modification's ``definition`` aren't
    among those fields. The ``extra_turns`` lane's structural fallback,
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
# (:func:`_walk_effect_chain`) — so a granted trigger's ``execute.effect``
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
def iter_delayed_trigger_condition_defs(node: object) -> Iterator[TypedMirrorNode]:
    """Every trigger DEFINITION node reachable under ``node`` via a
    ``CreateDelayedTrigger`` effect's ``condition {WheneverEvent: trigger}``
    watcher field."""
    for n in _iter_typed_nodes(node):
        if tag_of(n) != "CreateDelayedTrigger":
            continue
        cond = getattr(n, "condition", MISSING)
        if not (isinstance(cond, TypedMirrorNode) and tag_of(cond) == "WheneverEvent"):
            continue
        trig = getattr(cond, "trigger", MISSING)
        if isinstance(trig, TypedMirrorNode):
            yield trig


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
    if _trigger_event(trig) not in ("cast_spell", "spellcastorcopy"):
        return False
    vt = getattr(trig, "valid_target", None)
    return tag_of(vt) in _OPPONENT_ACTOR_TAGS or (
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
    if _trigger_event(trig) != "cast_spell":
        return False
    return "Creature" in filter_core_types(getattr(trig, "valid_card", None))


def is_creature_etb_trigger_def(trig: object) -> bool:
    """Whether a trigger DEFINITION node — a top-level trigger unit's own
    ``.node`` OR a nested def from :func:`iter_nested_trigger_defs` /
    :func:`iter_delayed_trigger_condition_defs` — is CR 603.6a's creature-ETB
    payoff shape: a ``ChangesZone``/``ChangesZoneAll`` mode landing on the
    battlefield (``_trigger_event`` normalizes both to ``"enters"``) whose
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
    if _trigger_event(trig) not in ENTERS_EVENTS:
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
    if _trigger_event(trig) != "deals_damage":
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

    Reads ``mode``/``execute`` directly — bypassing :func:`_trigger_event`'s
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
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, static_def)`` pairs for every
    ``affected_tag``-affected (default ``ParentTarget``) nested static in one
    ability/trigger chain, the target THREADED through the chain.

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
            if tag_of(eff) == "GenericEffect" and tracked is not None:
                nested = getattr(eff, "static_abilities", MISSING)
                sts = nested if _present(nested) and isinstance(nested, list) else []
                for st in sts:
                    if tag_of(getattr(st, "affected", None)) == affected_tag:
                        yield tracked, st
            sub2 = getattr(eff, "sub_ability", MISSING)
            if isinstance(sub2, TypedMirrorNode):
                queue.append(sub2)
        sub = getattr(node, "sub_ability", MISSING)
        if isinstance(sub, TypedMirrorNode):
            queue.append(sub)


def iter_single_target_grants(
    ability_like: object,
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
            if tag_of(mod) == "AddKeyword":
                yield tracked, mod


def iter_deep_target_grants(
    root: object,
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
                if tag_of(mod) == "AddKeyword":
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


def _find_owner_wrapper(
    node: object, target: object, depth: int, seen: set[int]
) -> TypedMirrorNode | None:
    """The ability wrapper whose ``.effect`` IS ``target`` (same walk as
    :func:`effect_owner_player_scope`'s), or ``None``."""
    if depth > 40 or not isinstance(node, TypedMirrorNode) or id(node) in seen:
        return None
    seen.add(id(node))
    if getattr(node, "effect", MISSING) is target:
        return node
    for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities"):
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            r = _find_owner_wrapper(child, target, depth + 1, seen)
            if r is not None:
                return r
        elif _present(child) and isinstance(child, list):
            for m in child:
                r = _find_owner_wrapper(m, target, depth + 1, seen)
                if r is not None:
                    return r
    return None


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
    owner = _find_owner_wrapper(root, effect_node, 0, set())
    return _node_raw(owner) if owner is not None else ""


def effect_owner_targets_per_opponent(root: object, effect_node: object) -> bool:
    """Whether the wrapper that DIRECTLY owns ``effect_node`` carries a
    ``multi_target`` count that scales by opponent count — phase's
    structural form of "for each opponent, <single-target effect>" (Juvenile
    Mist Dragon: ``multi_target.max`` is a ``PlayerCount`` qty filtered to
    ``Opponent``). This is a DIFFERENT tell from the effect's own target
    filter's ``controller`` (which reads the loop's bound iteration
    variable, e.g. ``TargetPlayer`` — ambiguous on its own); the wrapper's
    per-opponent CARDINALITY is unambiguous. CR 506.4's "each opponent"
    multiplayer default.
    """
    owner = _find_owner_wrapper(root, effect_node, 0, set())
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


def effect_owner_duration(root: object, effect_node: object) -> str | None:
    """The ``duration`` tag on the wrapper that DIRECTLY owns ``effect_node``
    (Banisher Priest's exile execute carries ``UntilHostLeavesPlay`` on the
    Spell wrapper, not on the ``ChangeZone`` node itself), or ``None``.
    CR 611.2b.
    """
    owner = _find_owner_wrapper(root, effect_node, 0, set())
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
    owner = _find_owner_wrapper(root, effect_node, 0, set())
    actor = (
        _player_scope_tag(getattr(owner, "player_scope", MISSING))
        if owner is not None
        else None
    )
    if actor in _OPPONENT_ACTOR_TAGS:
        return "opponents"
    if actor in _EACH_ACTOR_TAGS or actor == "All":
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
    # Phase-misparse workaround: phase v0.94.0 parses Predictive Preparations'
    # "each of one or two target creatures" as a ``PutCounterAll`` over a
    # typeless filter, which would read as every permanent. Retire the
    # ``filter_core_types`` condition when test_typeless_mass_filter_canary
    # fails RETIRE-READY.
    if tag_of(effect_node) in _MASS_REACH_TAGS and filter_core_types(filt):
        ctrl = filter_controller(filt)
        if ctrl is None:
            return "each"
        if ctrl in _OPPONENT_ACTOR_TAGS:
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

_TUTOR_DIRECTED_PLAYER_TAGS = frozenset(
    {
        "ParentTarget",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
        "ParentTargetController",
        "ParentObjectTargetController",
    }
)
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
        and getattr(n, "enters_under", None) == "You"
        for n in nodes
    )
    library_onto_yours = any(
        tag_of(n) == "ChangeZone"
        and getattr(n, "origin", None) == "Library"
        and getattr(n, "destination", None) == "Battlefield"
        and getattr(n, "enters_under", None) == "You"
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


def _unit_own_mana(
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
    """The ``Mana`` effects the card's own abilities resolve (:func:`_unit_own_mana`
    over every unit)."""
    for unit in tree.units:
        for eff, _ability in _unit_own_mana(unit):
            yield eff


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
    ability the card grants itself is one entry (:func:`_unit_own_mana`). A fact
    about the card, no policy: the tuner's ramp SOURCING reads it
    (``_tuner.issues._reliable_ramp``); COUNTING a deck's ramp (``roles.is_ramp``)
    deliberately doesn't."""
    out: list[bool] = []
    for unit in tree.units:
        abilities = {id(ab): ab for _eff, ab in _unit_own_mana(unit)}
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

#: Phase v0.94.0 drops the narrowing clause from three "permanents" sweeps and
#: parses each as every permanent: End Hostilities ("all permanents attached to
#: creatures"), Eye of Singularity ("each permanent with the same name as another
#: permanent, except for basic lands") and Herald of Vengeance ("each permanent you
#: don't control that has the same name as …"). Every other all-permanents sweep in
#: the legal corpus is a true one (Apocalypse, Upheaval, Worldfire, Worldpurge,
#: Dimensional Breach, Soulscour, Bearer of the Heavens). An every-permanent sweep
#: on a card whose text names one of these narrowings is vetoed. Guarded by
#: ``test_narrowed_permanent_sweeps_canary``.
NARROWED_PERMANENT_SWEEPS = ("permanents attached to", "same name as")


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
    arms = (getattr(filt, "filters", None) or ()) if tag_of(filt) == "Or" else (filt,)
    return any(
        _land_class_arm(
            f,
            battlefield_default=battlefield_default,
            own_ok=own_ok,
            permanents=permanents,
        )
        for f in arms
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
    (:data:`_SHORT_DURATIONS`). An instant's or sorcery's top-level static is its
    one-shot effect (CR 113.6: its abilities function on the stack) — phase
    v0.94.0 parses Exhaustion's and Mana Vapors' "don't untap during their next
    untap step" that way, without the duration; guarded by
    ``test_one_shot_untap_statics_canary``."""
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
        affected = getattr(sdef, "affected", None)
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
    owner = _find_owner_wrapper(root, node, 0, set())
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

# Evergreen team-anthem keywords (CR 702) — mirrors the deleted ``_signals_ir``'s
# identically-named ``_TEAM_BUFF_GRANT_KW`` (phase's spaceless spelling normalized via
# lower+strip).
_TEAM_BUFF_GRANT_KW: frozenset[str] = frozenset(
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


def _is_team_buff_filter(filt: object) -> bool:
    """The team_buff anthem subject (CR 604.3): GENERIC creatures YOU control
    — no subtypes (tribal is type_matters), predicates at most
    NonToken/Another/Other (Always Watching stays in; an Attacking/color/
    equipped narrowing fails). Mirrors the deleted ``_signals_ir``'s
    ``_is_team_buff_grant``."""
    return (
        filter_controller(filt) == "You"
        and "Creature" in filter_core_types(filt)
        and not filter_subtypes(filt)
        and set(filter_predicates(filt)) <= _TEAM_BUFF_OK_PREDS
    )


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
            if kw.lower().replace(" ", "") not in _TEAM_BUFF_GRANT_KW:
                continue
            if _is_team_buff_filter(getattr(sdef, "affected", None)):
                yield unit, sdef


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
# Every ``*All`` Effect variant phase declares (v0.94.0) — each acts on EVERY
# object its filter matches, never on a chosen target, so a "those creatures"
# after one names a board filter, not the chain's targets. Wider than
# :data:`MASS_EFFECT_TAGS` (the mass effects whose object filter decides who a
# removal / reach read hits): this set only ends a target thread.
_ALL_VARIANT_EFFECT_TAGS: frozenset[str] = frozenset(
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
    _TRACKED_SET_PRODUCER_TAGS | _ALL_VARIANT_EFFECT_TAGS
)


def ends_target_thread(eff: TypedMirrorNode) -> bool:
    """A token producer or a mass effect ends the chosen-target thread."""
    return tag_of(eff) in _THREAD_ENDING_TAGS


def iter_tracked_set_target_grants(
    ability_like: object,
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
            if tag_of(mod) == "AddKeyword":
                yield tracked, mod


def unit_keyword_grants(
    unit: AbilityUnit,
) -> list[tuple[object, TypedMirrorNode]]:
    """``(chosen_target_filter, AddKeyword_mod)`` for every keyword grant to a
    chosen target in one unit: the DEEP local-target leaf on any unit (a
    trigger, a modal arm, a Saga chapter — :func:`iter_deep_target_grants`),
    plus, on an ability or trigger, the threaded "It gains X" walk
    (:func:`iter_single_target_grants`) and the "those creatures" walk
    (:func:`iter_tracked_set_target_grants`). The ``keyword_grant_target`` /
    ``protection_grant`` lane and ``crosswalk.protection`` read this one walk.
    CR 613.1f (layer 6, ability-adding effects)."""
    grants = list(iter_deep_target_grants(unit.node))
    if unit.origin in ("ability", "trigger"):
        grants.extend(iter_single_target_grants(unit.node))
        grants.extend(iter_tracked_set_target_grants(unit.node))
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
        and _trigger_event(trig) == "deals_damage"
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
