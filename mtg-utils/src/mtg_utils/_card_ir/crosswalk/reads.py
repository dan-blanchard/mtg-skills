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

from collections.abc import Iterator
from dataclasses import fields
from typing import TYPE_CHECKING, Any

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


# Recipient-bearing sub-fields an effect/trigger uses to name a player. Read in
# order; the first present one decides scope.
_SCOPE_FIELDS = ("target", "player", "owner", "recipient", "valid_target")


def _scope_from_player_node(node: object) -> str | None:
    """Map a player-reference typed node to a Signal scope, or None if unknown.

    Reads the node's discriminator tag (``Controller`` / ``Opponent`` / …) and,
    for a ``Typed`` filter, its ``controller`` — never oracle text.
    """
    t = tag_of(node)
    if t in ("Controller", "SelfRef", "You"):
        return "you"
    if t in ("Opponent", "Opponents", "EachOpponent"):
        return "opponents"
    if t in ("Each", "AllPlayers", "EachPlayer"):
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
            sc = _scope_from_player_node(sub)
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
            return _scope_from_player_node(sub)
    return None


# Recipient tags naming a player OTHER than the ability's controller: the
# triggering object's controller (``ParentTargetController``), the triggering
# player (``TriggeringPlayer``), or a chosen/targeted player (``ParentTarget`` /
# ``Player`` / ``Target`` / ``Any``). A loss aimed at one of these is a DIRECTED
# loss at another player (CR 119.3), never a self-loss.
_DIRECTED_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "ParentTargetController",
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
_DETRIMENT_DIRECTED_TAGS: frozenset[str] = _DIRECTED_PLAYER_TAGS | frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "DefendingPlayer",
        "TargetPlayer",
        "TargetOpponent",
    }
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
    if tt in ("ScopedPlayer", "ParentTargetController", "DefendingPlayer"):
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
        tag_of(n) in ("DealDamage", "DamageAll", "DamageEachPlayer")
        and effect_reaches_player(n, node)
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
_DISCARD_OPP_TAGS: frozenset[str] = frozenset(
    {
        "Player",
        "Target",
        "ParentTarget",
        "Any",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TargetPlayer",
        "TriggeringPlayer",
        "ParentTargetController",
    }
)
_DISCARD_EACH_TAGS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})


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
        if _present(sub) and tag_of(sub) is not None:
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
        if t in _DISCARD_EACH_TAGS:
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


def damage_recipient_is_player(vt: object) -> bool:
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
    """
    t = tag_of(vt)
    if t in (
        "Player",
        "Any",
        "Target",
        "ParentTarget",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "Each",
        "AllPlayers",
        "EachPlayer",
    ):
        return True
    if t == "Typed":
        ctrl = getattr(vt, "controller", None)
        if ctrl == "You":
            return False
        cores = filter_core_types(vt)
        if not cores:
            return True
        return "Player" in cores or "Planeswalker" in cores
    if t == "Or":
        # ADR-0038 W3 batch 2 unit 6: "deals combat damage to a player or
        # planeswalker/battle" (Flitterwing Nuisance, Zurgo and Ojutai)
        # reaches a player in the Player branch even though the OTHER
        # branch is object-typed; ANY reachable branch is enough.
        return any(
            damage_recipient_is_player(f) for f in getattr(vt, "filters", ()) or ()
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


def ref_count_filter(node: TypedMirrorNode, field: str) -> object | None:
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
    root: object,
) -> Iterator[tuple[TypedMirrorNode, TypedMirrorNode]]:
    """``(static_def, modification)`` pairs reachable from one unit node.

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
    yield from _mod_sites(root)


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
    """
    return any(tag_of(n) == "ExtraTurn" for n in _iter_typed_nodes(node))


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
    return tag_of(vt) in ("Opponent", "Opponents", "EachOpponent") or (
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
    if _trigger_event(trig) not in ("enters", "entersorattacks"):
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
    split :func:`~mtg_utils._deck_forge.lanes._combat_damage_lanes`
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
    """Whether a ``Mana`` effect's ``restrictions`` carry a
    ``SpellType: Multicolored`` entry (CR 105.2c) — "Spend this mana only
    to cast a multicolored spell" (Obsidian Obelisk, Pillar of the
    Paruns)."""
    if tag_of(node) != "Mana":
        return False
    restrictions = getattr(node, "restrictions", MISSING)
    if not (_present(restrictions) and isinstance(restrictions, list)):
        return False
    return any(
        isinstance(r, MirrorVariant)
        and r.key == "SpellType"
        and r.inner == "Multicolored"
        for r in restrictions
    )


def iter_threaded_target_statics(
    ability_like: object,
) -> Iterator[tuple[object, TypedMirrorNode]]:
    """``(resolved_target_filter, static_def)`` pairs for every
    ``ParentTarget``-affected nested static in one ability/trigger chain, the
    target THREADED through the chain.

    Mirrors the live v14 tracked-target walk over the typed substrate: phase
    parses "target creature gains <kw> / becomes a 1/1" as a ``GenericEffect``
    whose nested static's ``affected`` is ``ParentTarget``, with the real
    target riding the ``GenericEffect``'s own ``target`` (Jump, Gods Willing)
    or an EARLIER effect's target the static re-references — the "It gains X"
    / "It becomes a 0/0" idiom ("Untap target creature. It gains reach" — Aim
    High; Cyclone Sire's land animate), resolved by threading the most recent
    non-ParentTarget filter through the ``effect`` / ``sub_ability`` /
    ``execute`` chain. Callers apply their own gates on the resolved filter.
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
            if _present(tgt) and tag_of(tgt) in ("Typed", "Or", "And"):
                tracked = tgt
            if tag_of(eff) == "GenericEffect" and tracked is not None:
                nested = getattr(eff, "static_abilities", MISSING)
                sts = nested if _present(nested) and isinstance(nested, list) else []
                for st in sts:
                    if tag_of(getattr(st, "affected", None)) == "ParentTarget":
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
