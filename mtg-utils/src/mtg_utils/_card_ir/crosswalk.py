"""Layer-2 concept overlay over the lossless typed substrate (ADR-0035, Stage 2).

The crosswalk is a **tree-preserving** decoration over the codegen'd typed mirror
(``_card_ir/mirror``): it reads the typed substrate by ``isinstance`` / typed
attribute access — never re-greps oracle text, never bypasses to a stringly-keyed
dict — and hangs a :class:`ConceptNode` off every effect's preserved tree
position. Each concept-node is either a **recognized concept** (``draw`` /
``discard`` / ``make_token`` / ``win_game`` / …) or an ``other`` concept **carrying
the verbatim typed node** (the lossless hatch — categorically different from a
verbatim-*text* ``raw`` that forces re-regex; the structured node is preserved).

It is **additive / shadow-only** (ADR-0035 Stage 2): nothing in production reads
this. The live regex+IR detection path (``_deck_forge.signals``) is untouched; the
crosswalk runs alongside it for the shadow ``Signal``-diff.

The overlay preserves the **three join granularities** the lanes depend on, so a
flat-overlay regression fails loud:

* **(a) per-ability sibling co-occurrence** — :meth:`AbilityUnit.effect_concepts`
  scopes effects to ONE ability unit. ``discard_makers`` fires only when a ``draw``
  *and* a ``discard`` effect coexist in the SAME unit (Faithless Looting), never
  across two abilities (Psychic Frog / Nezahal — a combat-damage draw *trigger* and
  a separate ``Discard a card:`` *cost* live in different units, and a cost is not
  an effect).
* **(b) per-ability effect/raw aggregation** — :meth:`AbilityUnit.iter_concepts`
  exposes a unit's effects *and* static modifications together, so the animate-land
  split-subject (a Land subject + a becomes-creature modification spread across one
  static ability) reconstructs as one decision.
* **(c) whole-card / cross-face merged-key joins** — :meth:`ConceptTree.has_effect`
  / :meth:`ConceptTree.iter_concepts` scan every unit, the surface the four
  ``signals.py`` reconciliations read.

Stays self-contained within ``_card_ir`` (Layer-2 framework only — no
``_deck_forge`` import); the ``Signal``-lane derivation that *uses* this overlay
lives at Layer 3 in ``_deck_forge.crosswalk_signals``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)

# ── Effect tag → concept map (the stable Layer-2 vocabulary) ──────────────────
# Phase ``Effect`` discriminator tag (the node's ``_tag``) → recognized concept
# name. An effect whose tag is absent here decorates as ``other`` CARRYING the
# verbatim typed node — the lossless tail. Grown per ported batch; everything
# else stays ``other`` (never silently dropped).
EFFECT_CONCEPTS: dict[str, str] = {
    "Draw": "draw",
    "Discard": "discard",
    "Token": "make_token",
    "CopySpell": "copy_spell",
    "WinTheGame": "win_game",
    "LoseTheGame": "lose_game",
    "Pump": "pump",
    "PumpAll": "pump",
    # Batch 2 (ADR-0035 Stage 2):
    "GainLife": "gain_life",  # lifegain_makers / matters
    "LoseLife": "lose_life",  # lifegain_matters self-loss sustain
    "DealDamage": "deal_damage",  # direct_damage (single-target / "any target")
    "DamageEachPlayer": "deal_damage",  # direct_damage (each/opp player)
    "DamageAll": "deal_damage",  # direct_damage (mass; players when player_filter)
    "Sacrifice": "sacrifice",  # sacrifice_outlets (effect + cost) / edict
    "PutCounter": "place_counter",  # plus_one_makers (counter_type discriminates)
    "PutCounterAll": "place_counter",
    "AddPendingETBCounters": "place_counter",
    "ExtraTurn": "extra_turn",  # extra_turns (CR 500.7)
    "ChangeZone": "change_zone",  # reanimator (GY→bf) / blink (exile+return)
    "ChangeZoneAll": "change_zone",
    "Mana": "ramp",  # mana production (lane splits land base vs accel/fixing)
}

OTHER = "other"


@dataclass(frozen=True)
class ConceptNode:
    """A per-node decoration hanging off a preserved typed-tree position.

    ``node`` is the **verbatim** typed substrate instance (an ``other`` concept
    carries it losslessly — its ``to_dict`` still round-trips). ``role`` records
    the structural slot the node occupies within its ability unit (``effect`` for
    a resolved effect / sub-effect, ``cost`` for an activation cost, ``static``
    for a continuous-ability modification) — the per-ability granularity gate that
    keeps a *discard cost* from reading as a *discard effect*.
    """

    concept: str  # recognized concept name, or ``OTHER``
    node: TypedMirrorNode  # the verbatim typed node (lossless)
    role: str  # "effect" | "cost" | "static"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: tuple[str, ...]  # type/subtype strings the node names ("" → empty)
    raw: str  # a grounding clause (node description / "") — not identity-bearing


@dataclass(frozen=True)
class AbilityUnit:
    """One ability of the card — the per-ability join scope (granularities a/b).

    A unit is one entry of phase's ``abilities`` (activated/spell/static-on-an-
    ability), ``triggers`` (a triggered ability — ``trigger_event`` derived from
    its ``mode`` + zone/recipient), ``static_abilities`` (a continuous ability —
    its ``modifications`` become ``static``-role concepts), or ``replacements``.
    ``node`` is the verbatim typed ability node (the preserved tree position).
    """

    origin: str  # "ability" | "trigger" | "static" | "replacement"
    index: int
    node: TypedMirrorNode
    kind: str | None  # phase ability ``kind`` (Activated/Spell/Static/…) or None
    trigger_event: str | None  # derived event for a trigger unit, else None
    effects: tuple[ConceptNode, ...]  # role=effect (the effect+sub_ability chain)
    costs: tuple[ConceptNode, ...]  # role=cost (activation costs)
    statics: tuple[ConceptNode, ...]  # role=static (continuous modifications)

    def iter_concepts(self) -> Iterator[ConceptNode]:
        """Every concept-node in this unit (effects, costs, statics)."""
        yield from self.effects
        yield from self.costs
        yield from self.statics

    def effect_concepts(self, concept: str) -> tuple[ConceptNode, ...]:
        """The role=effect concept-nodes in THIS unit matching ``concept``.

        The per-ability sibling-co-occurrence gate (granularity a): reads only
        resolved effects, so an activation *cost* of the same kind never counts.
        """
        return tuple(c for c in self.effects if c.concept == concept)

    def has_effect(self, concept: str) -> bool:
        """Whether THIS unit has a role=effect concept-node named ``concept``."""
        return any(c.concept == concept for c in self.effects)


@dataclass(frozen=True)
class ConceptTree:
    """The whole-card overlay: the card's ability units, tree position preserved.

    ``units`` is the per-ability join surface (granularities a/b). The whole-card
    joins (granularity c) read across all units via :meth:`iter_concepts` /
    :meth:`has_effect`.
    """

    name: str
    oracle_id: str
    units: tuple[AbilityUnit, ...] = field(default_factory=tuple)
    card_types: tuple[str, ...] = ()  # the card's own core types (Creature / Land …)

    def is_type(self, core: str) -> bool:
        """Whether the card itself has core type ``core`` (Creature / Land / …).

        The whole-card type gate the reanimator (is-creature) and ramp (is-land)
        lanes read off the typed ``card_type`` — never a re-grepped type line.
        """
        return core in self.card_types

    def iter_concepts(self) -> Iterator[ConceptNode]:
        """Every concept-node across every unit (the whole-card scan)."""
        for unit in self.units:
            yield from unit.iter_concepts()

    def effect_concepts(self, concept: str) -> tuple[ConceptNode, ...]:
        """Every role=effect concept-node named ``concept``, whole-card."""
        out: list[ConceptNode] = []
        for unit in self.units:
            out.extend(unit.effect_concepts(concept))
        return tuple(out)

    def has_effect(self, concept: str) -> bool:
        """Whether ANY unit has a role=effect concept named ``concept``."""
        return any(u.has_effect(concept) for u in self.units)


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


def effect_reaches_player(node: TypedMirrorNode) -> bool:
    """Whether a damage EFFECT reaches a PLAYER (CR 120.1), read structurally.

    The direct-damage / burn gate: a creature-only bite ("4 damage to target
    creature" — Flame Slash; "2 to each creature" — Pyroclasm) is removal, not burn.

    * ``DamageEachPlayer`` always hits players.
    * ``DamageAll`` hits players iff it carries a ``player_filter`` (Pestilence pings
      creatures AND each player; Pyroclasm-as-``DamageAll`` has none).
    * ``DealDamage`` hits a player iff its target is "any target"/a player node, or a
      ``Player``-typed filter — NOT a creature/permanent-typed filter, and NOT a
      bare self target ("deals 1 damage to you" painland).
    """
    t = tag_of(node)
    if t == "DamageEachPlayer":
        return True
    if t == "DamageAll":
        return _present(getattr(node, "player_filter", MISSING))
    if t == "DealDamage":
        tgt = getattr(node, "target", MISSING)
        if not _present(tgt):
            return False
        tt = tag_of(tgt)
        if tt == "Typed":
            words = _filter_type_words(tgt)
            return "Player" in words  # creature/permanent typed → removal
        if tt in ("Any", "Target", "ParentTarget"):
            return True
        sc = _scope_from_player_node(tgt)  # a direct player node
        return sc in ("opponents", "each", "any")
    return False


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
    if mode == "ChangesZone":
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
        "Attacks": "attacks",
        "YouAttack": "attacks",
        "SpellCast": "cast_spell",
        "DamageDone": "deals_damage",
        "CounterAdded": "counter_added",
        "LifeGained": "life_gained",
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


# ── overlay construction ──────────────────────────────────────────────────────


def _decorate_effect(node: object, role: str) -> ConceptNode | None:
    """Decorate one effect/cost typed node as a :class:`ConceptNode`.

    Returns ``None`` for an absent/scalar slot. An unrecognized tag decorates as
    ``OTHER`` carrying the verbatim node.
    """
    if not isinstance(node, TypedMirrorNode):
        return None
    t = tag_of(node)
    concept = EFFECT_CONCEPTS.get(t or "", OTHER)
    return ConceptNode(
        concept=concept,
        node=node,
        role=role,
        scope=_effect_scope(node),
        subject=_effect_subject(node),
        raw=_node_raw(node),
    )


# Effect-bearing child fields a node nests further effects through. Phase chains
# sequential siblings ("draw two cards, then discard two") via ``sub_ability``,
# wraps a delayed/granted effect in ``effect`` / ``execute`` (a replacement's
# ``execute``, Final Fortune's nested end-step loss), and branches modes through
# ``mode_abilities`` (Demonic Pact). A faithful unit aggregates them all — the same
# flattening the old projection's ``ab.effects`` did.
_EFFECT_CHILD_FIELDS = ("effect", "sub_ability", "execute")


def _walk_effect_chain(ability_like: TypedMirrorNode) -> Iterator[ConceptNode]:
    """Yield role=effect concepts reachable from one ability unit, depth-first.

    Decorates every tagged effect node reached through an effect-bearing field
    (``effect`` / ``sub_ability`` / ``execute`` / ``mode_abilities``) so a deeply
    nested terminal effect (a replacement's ``execute.effect`` win, a modal arm's
    loss) is still one of the unit's effects — the whole-unit aggregation the
    co-occurrence and whole-card lanes read. Cycle-safe (id-set + depth cap).
    """
    yield from _walk_effects(ability_like, 0, set())


def _walk_effects(node: object, depth: int, seen: set[int]) -> Iterator[ConceptNode]:
    if depth > 40 or not isinstance(node, TypedMirrorNode):
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    # A tagged node reached via an effect position IS an effect — decorate it.
    if tag_of(node) is not None:
        cn = _decorate_effect(node, "effect")
        if cn is not None:
            yield cn
    for fname in _EFFECT_CHILD_FIELDS:
        child = getattr(node, fname, MISSING)
        if isinstance(child, TypedMirrorNode):
            yield from _walk_effects(child, depth + 1, seen)
    modes = getattr(node, "mode_abilities", MISSING)
    if _present(modes) and isinstance(modes, list):
        for m in modes:
            if isinstance(m, TypedMirrorNode):
                yield from _walk_effects(m, depth + 1, seen)


def _cost_concepts(ability: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=cost concepts for an ability's activation cost (a single typed node)."""
    cost = getattr(ability, "cost", MISSING)
    cn = _decorate_effect(cost, "cost")
    return (cn,) if cn is not None else ()


# Modification tag → a coarse static-concept the land/anthem lanes read.
_MOD_CONCEPTS: dict[str, str] = {
    "AddPower": "pump",
    "AddToughness": "pump",
    "SetPower": "set_pt",
    "SetToughness": "set_pt",
    "AddType": "add_type",
    "AddKeyword": "grant_keyword",
}


def _static_concepts(static_ab: TypedMirrorNode) -> tuple[ConceptNode, ...]:
    """Role=static concepts for a continuous ability's ``modifications``.

    Each modification carries the ability's ``affected`` filter as its subject so a
    per-ability aggregation (granularity b) can read the subject + the
    modification kind together (animate-land: a Land subject + an ``AddType
    Creature``).
    """
    affected = getattr(static_ab, "affected", MISSING)
    subject = _filter_type_words(affected) if _present(affected) else ()
    scope = "any"
    if _present(affected):
        sc = _scope_from_player_node(affected)
        if sc is not None:
            scope = sc
    out: list[ConceptNode] = []
    mods = getattr(static_ab, "modifications", MISSING)
    if _present(mods) and isinstance(mods, list):
        for mod in mods:
            if not isinstance(mod, TypedMirrorNode):
                continue
            concept = _MOD_CONCEPTS.get(tag_of(mod) or "", OTHER)
            out.append(
                ConceptNode(
                    concept=concept,
                    node=mod,
                    role="static",
                    scope=scope,
                    subject=subject,
                    raw=_node_raw(static_ab),
                )
            )
    return tuple(out)


def _nested_static_concepts(
    ability_like: TypedMirrorNode,
) -> tuple[ConceptNode, ...]:
    """Static-role concepts from a ``GenericEffect`` nested inside an ability.

    Phase wraps a one-shot / activated animate ("target land you control becomes a
    4/4 creature") as a ``GenericEffect`` effect carrying its ``target`` (the
    animated permanent's filter) plus nested ``static_abilities`` whose
    modifications confer the creature-ness. Harvesting them as ``static`` concepts
    — subject + scope taken from the ``GenericEffect``'s ``target`` — lets the
    per-ability aggregation (granularity b) reconstruct the animate-land split
    through a nested effect, the dominant animator shape.
    """
    out: list[ConceptNode] = []
    seen: set[int] = set()
    stack: list[object] = [ability_like]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        for fname in (*_EFFECT_CHILD_FIELDS, "mode_abilities"):
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif _present(child) and isinstance(child, list):
                stack.extend(child)
        if tag_of(node) != "GenericEffect":
            continue
        target = getattr(node, "target", MISSING)
        subject = _filter_type_words(target) if _present(target) else ()
        scope = "any"
        if _present(target):
            sc = _scope_from_player_node(target)
            if sc is not None:
                scope = sc
        nested = getattr(node, "static_abilities", MISSING)
        if not (_present(nested) and isinstance(nested, list)):
            continue
        for st in nested:
            mods = getattr(st, "modifications", MISSING)
            if not (_present(mods) and isinstance(mods, list)):
                continue
            for mod in mods:
                if not isinstance(mod, TypedMirrorNode):
                    continue
                out.append(
                    ConceptNode(
                        concept=_MOD_CONCEPTS.get(tag_of(mod) or "", OTHER),
                        node=mod,
                        role="static",
                        scope=scope,
                        subject=subject,
                        raw=_node_raw(node),
                    )
                )
    return tuple(out)


def build_concept_tree(
    root: TypedMirrorNode, *, name: str = "", oracle_id: str = ""
) -> ConceptTree:
    """Build the tree-preserving concept overlay for one typed card root.

    ``root`` is an ``S_Root`` from ``strict_load_card(record, schema)``. Every
    ability of the card becomes an :class:`AbilityUnit` whose effects/costs/statics
    are decorated concept-nodes; unrecognized effects carry their verbatim node as
    ``other``.
    """
    oid = oracle_id or getattr(root, "scryfall_oracle_id", "") or ""
    nm = name or getattr(root, "name", "") or ""
    ct = getattr(root, "card_type", None)
    cores = getattr(ct, "core_types", None) if ct is not None else None
    card_types = tuple(c for c in cores if isinstance(c, str)) if cores else ()
    units: list[AbilityUnit] = []

    abilities = getattr(root, "abilities", ()) or ()
    for i, ab in enumerate(abilities):
        if not isinstance(ab, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="ability",
                index=i,
                node=ab,
                kind=getattr(ab, "kind", None),
                trigger_event=None,
                effects=tuple(_walk_effect_chain(ab)),
                costs=_cost_concepts(ab),
                statics=_nested_static_concepts(ab),
            )
        )

    triggers = getattr(root, "triggers", ()) or ()
    for i, trig in enumerate(triggers):
        if not isinstance(trig, TypedMirrorNode):
            continue
        execute = getattr(trig, "execute", MISSING)
        effects = (
            tuple(_walk_effect_chain(execute))
            if isinstance(execute, TypedMirrorNode)
            else ()
        )
        units.append(
            AbilityUnit(
                origin="trigger",
                index=i,
                node=trig,
                kind=getattr(execute, "kind", None)
                if isinstance(execute, TypedMirrorNode)
                else None,
                trigger_event=_trigger_event(trig),
                effects=effects,
                costs=(),
                statics=_nested_static_concepts(execute)
                if isinstance(execute, TypedMirrorNode)
                else (),
            )
        )

    statics = getattr(root, "static_abilities", ()) or ()
    for i, st in enumerate(statics):
        if not isinstance(st, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="static",
                index=i,
                node=st,
                kind="static",
                trigger_event=None,
                effects=(),
                costs=(),
                statics=_static_concepts(st),
            )
        )

    replacements = getattr(root, "replacements", ()) or ()
    for i, rp in enumerate(replacements):
        if not isinstance(rp, TypedMirrorNode):
            continue
        units.append(
            AbilityUnit(
                origin="replacement",
                index=i,
                node=rp,
                kind="replacement",
                trigger_event=None,
                effects=tuple(_walk_effect_chain(rp)),
                costs=(),
                statics=_nested_static_concepts(rp),
            )
        )

    return ConceptTree(
        name=nm, oracle_id=oid, units=tuple(units), card_types=card_types
    )
