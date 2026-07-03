"""Minimal old-IR compat adapter over the crosswalk ConceptTree (ADR-0035 S2).

Builds a **real** ``mtg_utils.card_ir`` ``Card`` from the Layer-2 concept
overlay (:func:`mtg_utils._card_ir.crosswalk.build_concept_tree`) so the four
non-Signal consumers of the Effect/Ability/Card dataclass API — ``ranking`` /
``budgets`` / ``cut_check`` / the tuner (``metrics`` + ``bracket``) — can be
run UNCHANGED against the typed substrate for the Stage-2 output-diff
harness (``_deck_forge.crosswalk_consumer_diff``).

MINIMAL by design (grow-on-demand): only the fields those consumers actually
read are populated —

* ``Effect``: ``category`` / ``scope`` / ``subject`` / ``amount`` /
  ``toughness`` / ``counter_kind`` (the ``"all"`` mass marker) / ``zones`` /
  ``raw``
* ``Ability``: ``kind`` / ``effects`` / ``trigger``
* ``Trigger``: ``event`` / ``subject``
* ``Card``: ``all_abilities()`` (one Face)

Where the crosswalk cannot yet populate a read (an unported effect tag, an
unmapped concept, a dynamic pump P/T), the adapter says so EXPLICITLY:
the effect degrades to ``category="other"`` (the old IR's own escape hatch)
and the miss is tallied in a :class:`CompatCoverage` bucket — never a silent
guess. The harness report surfaces those buckets so divergence on unported
categories is legible as the porting worklist, not noise.

Shadow-only / additive: nothing in production imports this.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    tag_of,
    trigger_subject,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, TypedMirrorNode
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter, Quantity, Trigger

if TYPE_CHECKING:
    from collections.abc import Iterable

# ── coverage accounting ───────────────────────────────────────────────────────


@dataclass
class CompatCoverage:
    """Explicit per-node accounting of what the adapter could (not) populate.

    ``ported`` counts effect nodes that landed in a real old-IR category,
    keyed by that category. ``unported`` counts the explicit misses, keyed by
    bucket: ``tag:<PhaseTag>`` (an effect tag the crosswalk itself has not
    ported — concept ``other``), ``concept:<name>`` (a crosswalk concept with
    no faithful old-category mapping yet), ``mod:<Tag>`` (a static
    modification kind outside the anthem set), and ``gap:<name>`` field-level
    gaps (a dynamic pump P/T whose sign the adapter refuses to guess).
    """

    ported: Counter[str] = field(default_factory=Counter)
    unported: Counter[str] = field(default_factory=Counter)

    def coverage_rows(self) -> list[tuple[str, int, int]]:
        """``(bucket, ported, unported)`` rows over every seen bucket."""
        keys = sorted(set(self.ported) | set(self.unported))
        return [(k, self.ported.get(k, 0), self.unported.get(k, 0)) for k in keys]


# ── vocabulary maps (crosswalk → old-IR) ──────────────────────────────────────

# ConceptNode.scope → old Effect.scope ("opponents" is the only rename).
_SCOPE = {"you": "you", "opponents": "opp", "each": "each", "any": "any"}

# phase filter ``controller`` → old Filter.controller.
_CONTROLLER = {"You": "you", "Opponent": "opp"}

# Core card-type words (CR 300.1 + the Permanent/Player umbrella words the old
# Filter carries) — the split key for a flattened type-word tuple.
_CORE_TYPE_WORDS = frozenset(
    {
        "Artifact",
        "Battle",
        "Creature",
        "Enchantment",
        "Instant",
        "Land",
        "Planeswalker",
        "Sorcery",
        "Kindred",
        "Tribal",
        "Permanent",
        "Player",
        "Card",
        "Spell",
    }
)

# Crosswalk concept → old-IR Effect.category, for the concepts whose mapping
# is faithful (same mechanic, and either consumer-read or name-identical).
# A concept ABSENT here maps to "other" + an explicit ``concept:`` coverage
# bucket — never a silent guess. ``change_zone`` and ``pump`` are structural
# splits handled in :func:`_effect_category`.
_CONCEPT_CATEGORY: dict[str, str] = {
    "draw": "draw",
    "deal_damage": "damage",
    "gain_life": "gain_life",
    "lose_life": "lose_life",
    "destroy": "destroy",
    "bounce": "bounce",
    "place_counter": "place_counter",
    "remove_counter": "remove_counter",
    "make_token": "make_token",
    "win_game": "win_game",
    "lose_game": "lose_game",
    "extra_turn": "extra_turn",
    "sacrifice": "sacrifice",
    "connive": "connive",
    "discard": "discard",
    "mill": "mill",
    "ramp": "ramp",
    "tutor": "tutor",
    "proliferate": "proliferate",
    "gain_control": "gain_control",
    "fight": "fight",
    "cast_from_zone": "cast_from_zone",
}

# Static modification concept → old-IR category (the ranking anthem set).
_STATIC_CATEGORY: dict[str, str] = {
    "pump": "pump",
    "grant_keyword": "grant_keyword",
    "set_pt": "base_pt_set",
}

# Trigger events already named identically on both sides pass through; these
# are the crosswalk→old renames (the cut_check-read six are the load-bearing
# rows: etb / dies / attacks / upkeep / end_step / combat_damage).
_EVENT_RENAME: dict[str, str] = {
    "enters": "etb",
    "changes_zone": "leaves",
    "leavesbattlefield": "leaves",
    "destroyed": "dies",
    "attackerunblocked": "attacks",
    "youattackunblocked": "attacks",
    "attackersdeclared": "attacks",
    "attackersdeclaredonetarget": "attacks",
    "spellcopy": "cast_spell",
    "spellcastorcopy": "cast_spell",
    "spellabilitycast": "cast_spell",
    "tapsformana": "taps",
}
# phase Phase-trigger ``phase`` → old event (project.py's mode=="phase" arm).
_PHASE_EVENT: dict[str, str] = {
    "upkeep": "upkeep",
    "end": "end_step",
    "draw": "draw_step",
    "begincombat": "begin_combat",
    "combat": "begin_combat",
}
# Trigger modes that carry the combat-vs-any ``damage_kind`` discriminator.
_DAMAGE_MODES = frozenset(
    {"deals_damage", "damagedoneonce", "damagedealtonce", "damagedoneoncebycontroller"}
)

# Unit origin/kind → old Ability.kind (consumers test only triggered/activated).
_ABILITY_KIND: dict[str, str] = {"Activated": "activated", "Spell": "spell"}


def _present(v: object) -> bool:
    return v is not MISSING and v is not None


# ── field builders ────────────────────────────────────────────────────────────


def _split_type_words(words: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split a flattened type-word tuple into (core types, subtypes)."""
    cores: list[str] = []
    subs: list[str] = []
    for w in words:
        (cores if w in _CORE_TYPE_WORDS else subs).append(w)
    return tuple(cores), tuple(subs)


def _subject(cnode: ConceptNode) -> Filter | None:
    """The old-IR subject Filter of one effect node, or ``None`` when bare.

    Reads the typed filter node when the effect carries one (controller +
    core-vs-subtype split); a ``Token`` effect's flat ``types`` tuple (already
    surfaced as ``ConceptNode.subject``) splits by the core-type word set.
    """
    filt = effect_filter(cnode.node)
    if filt is not None:
        cores = filter_core_types(filt)
        subs = filter_subtypes(filt)
        ctrl = _CONTROLLER.get(filter_controller(filt) or "", "any")
        if cores or subs or ctrl != "any":
            return Filter(card_types=cores, subtypes=subs, controller=ctrl)
    if cnode.subject:
        cores, subs = _split_type_words(cnode.subject)
        ctrl = "you" if cnode.scope == "you" else "any"
        return Filter(card_types=cores, subtypes=subs, controller=ctrl)
    return None


def _quantity_from(q: object) -> Quantity | None:
    """One amount-position typed node → the old Quantity (None when absent).

    ``Fixed`` → ``op="fixed"``; a ``Ref`` over an ``ObjectCount`` → ``op=
    "count"`` with the counted filter as subject; any other present shape is
    ``op="variable"`` (an X / dynamic scaler — honest "not fixed", the same
    non-parseable verdict the consumers give it).
    """
    if not _present(q) or not isinstance(q, TypedMirrorNode):
        return None
    t = tag_of(q)
    if t == "Fixed":
        v = getattr(q, "value", None)
        if isinstance(v, int):
            return Quantity(op="fixed", factor=v)
        return Quantity(op="variable")
    if t == "Ref":
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None:
                cores = filter_core_types(filt)
                subs = filter_subtypes(filt)
                ctrl = _CONTROLLER.get(filter_controller(filt) or "", "any")
                return Quantity(
                    op="count",
                    subject=Filter(card_types=cores, subtypes=subs, controller=ctrl),
                )
    return Quantity(op="variable")


def _amount(node: TypedMirrorNode) -> Quantity | None:
    """The effect's amount read off its first present amount-position field."""
    for fname in ("amount", "count", "value"):
        q = getattr(node, fname, MISSING)
        if _present(q):
            return _quantity_from(q)
    return None


def _zones(cnode: ConceptNode) -> tuple[str, ...]:
    """Directional/positional zone strings in the old-IR spelling.

    A ``change_zone`` concept carries phase's origin/destination directly;
    every effect's target/filter contributes its ``InZone`` predicates
    (Raise Dead's "from your graveyard" bounce → ``in:graveyard``).
    """
    out: list[str] = []
    if cnode.concept == "change_zone":
        origin, dest = change_zone_dirs(cnode.node)
        if isinstance(origin, str):
            out.append(f"from:{origin.lower()}")
        if isinstance(dest, str):
            out.append(f"to:{dest.lower()}")
    filt = effect_filter(cnode.node)
    if filt is not None:
        out.extend(f"in:{z.lower()}" for z in filter_inzone_zones(filt))
    return tuple(out)


def _pump_pt(
    node: TypedMirrorNode, cov: CompatCoverage
) -> tuple[Quantity | None, Quantity | None]:
    """(amount=power, toughness) of a Pump/PumpAll effect, fixed values only.

    A dynamic "-X/-X" has no fixed sign the adapter can read without guessing;
    it stays ``None`` and is tallied as ``gap:pump_dynamic_pt``.
    """
    out: list[Quantity | None] = []
    for fname in ("power", "toughness"):
        sub = getattr(node, fname, MISSING)
        if not _present(sub):
            out.append(None)
            continue
        v = getattr(sub, "value", None)
        if tag_of(sub) == "Fixed" and isinstance(v, int):
            out.append(Quantity(op="fixed", factor=v))
        else:
            cov.unported["gap:pump_dynamic_pt"] += 1
            out.append(None)
    return out[0], out[1]


def _effect_category(cnode: ConceptNode, cov: CompatCoverage) -> str:
    """The old-IR category for one effect concept-node, coverage-tallied.

    Structural splits the flat concept map can't carry:

    * ``change_zone`` routes on origin/destination (graveyard→battlefield =
      ``reanimate``; →exile = ``exile``; →hand = ``bounce``); any other pair
      is an explicit ``concept:change_zone`` miss, not a guess.
    * ``pump`` routes single-vs-class on the target node: a ``PumpAll`` or a
      class-filter target (``Typed``/``Or``/``And`` — Languish, Overrun,
      Bile Blight) is the mass ``pump``; a specific-object target
      (ParentTarget — "target creature gets -3/-3") is ``pump_target``.
    """
    tag = tag_of(cnode.node) or ""
    if cnode.concept == OTHER:
        cov.unported[f"tag:{tag or 'scalar'}"] += 1
        return "other"
    if cnode.concept == "change_zone":
        origin, dest = change_zone_dirs(cnode.node)
        cat = None
        if origin == "Graveyard" and dest == "Battlefield":
            cat = "reanimate"
        elif dest == "Exile":
            cat = "exile"
        elif dest == "Hand":
            cat = "bounce"
        if cat is not None:
            cov.ported[cat] += 1
            return cat
        cov.unported["concept:change_zone"] += 1
        return "other"
    if cnode.concept == "pump":
        target = getattr(cnode.node, "target", MISSING)
        mass = tag.endswith("All") or tag_of(target) in ("Typed", "Or", "And")
        cat = "pump" if mass else "pump_target"
        cov.ported[cat] += 1
        return cat
    cat = _CONCEPT_CATEGORY.get(cnode.concept)
    if cat is None:
        cov.unported[f"concept:{cnode.concept}"] += 1
        return "other"
    cov.ported[cat] += 1
    return cat


def _effect(cnode: ConceptNode, cov: CompatCoverage) -> Effect:
    """One role=effect concept-node → the minimal old-IR Effect."""
    category = _effect_category(cnode, cov)
    node = cnode.node
    amount = _amount(node)
    toughness: Quantity | None = None
    if category in ("pump", "pump_target"):
        amount, toughness = _pump_pt(node, cov)
    tag = tag_of(node) or ""
    return Effect(
        category=category,
        amount=amount,
        toughness=toughness,
        scope=_SCOPE.get(cnode.scope, "any"),
        subject=_subject(cnode),
        raw=cnode.raw,
        counter_kind="all" if tag.endswith("All") else "",
        zones=_zones(cnode),
    )


def _static_effect(cnode: ConceptNode, cov: CompatCoverage) -> Effect:
    """One role=static modification concept-node → the minimal old-IR Effect.

    An ``AddPower``/``AddToughness`` carries a plain-int ``value``; it lands
    on ``amount`` (power) or ``toughness`` respectively so the budgets mass-
    debuff read (Elesh Norn's -2/-2) sees the signed toughness. A dynamic /
    absent value stays ``None`` (tallied), never a guessed sign.
    """
    concept = cnode.concept
    cat = _STATIC_CATEGORY.get(concept)
    tag = tag_of(cnode.node) or ""
    if cat is None:
        bucket = f"mod:{tag or 'scalar'}" if concept == OTHER else f"concept:{concept}"
        cov.unported[bucket] += 1
        cat = "other"
    else:
        cov.ported[cat] += 1
    v = getattr(cnode.node, "value", MISSING)
    qty = Quantity(op="fixed", factor=v) if isinstance(v, int) else None
    if qty is None and cat in ("pump", "base_pt_set"):
        cov.unported["gap:static_dynamic_value"] += 1
    amount: Quantity | None = None
    toughness: Quantity | None = None
    if tag in ("AddToughness", "SetToughness"):
        toughness = qty
    else:
        amount = qty
    cores, subs = _split_type_words(cnode.subject)
    ctrl = {"you": "you", "opponents": "opp"}.get(cnode.scope, "any")
    subject = (
        Filter(card_types=cores, subtypes=subs, controller=ctrl)
        if (cores or subs)
        else None
    )
    return Effect(
        category=cat,
        amount=amount,
        toughness=toughness,
        scope=_SCOPE.get(cnode.scope, "any"),
        subject=subject,
        raw=cnode.raw,
    )


def _trigger_event(unit: AbilityUnit) -> str:
    """The old-IR trigger event for one trigger unit, read structurally.

    The crosswalk's derived event is renamed into the old vocabulary; the two
    overloaded modes re-read the typed node's own discriminator field —
    a ``Phase`` trigger's ``phase`` (upkeep / end_step / draw_step /
    begin_combat) and a damage trigger's ``damage_kind`` (``CombatOnly`` →
    ``combat_damage``, else ``deals_damage``) — exactly the two splits the
    old projection made (project.py ``_trigger_event``).
    """
    ev = unit.trigger_event or "other"
    if ev == "phase":
        ph = getattr(unit.node, "phase", None)
        ph = ph.lower() if isinstance(ph, str) else ""
        return _PHASE_EVENT.get(ph, "other")
    if ev in _DAMAGE_MODES:
        dk = getattr(unit.node, "damage_kind", None)
        dk = dk.lower() if isinstance(dk, str) else ""
        return "combat_damage" if dk == "combatonly" else "deals_damage"
    return _EVENT_RENAME.get(ev, ev)


def _trigger(unit: AbilityUnit) -> Trigger:
    """The minimal old-IR Trigger for one trigger unit (event + subject)."""
    words = trigger_subject(unit.node)
    subject: Filter | None = None
    if words:
        cores, subs = _split_type_words(words)
        subject = Filter(card_types=cores, subtypes=subs)
    return Trigger(event=_trigger_event(unit), subject=subject)


def _ability_kind(unit: AbilityUnit) -> str:
    """The old Ability.kind for one unit (triggered/activated are the reads)."""
    if unit.origin == "trigger":
        return "triggered"
    if unit.origin in ("static", "replacement"):
        return "static"
    kind = unit.kind or ""
    return _ABILITY_KIND.get(kind, kind.lower() or "static")


def _ability(unit: AbilityUnit, cov: CompatCoverage) -> Ability:
    """One AbilityUnit → the minimal old-IR Ability.

    Effects = the unit's role=effect concepts plus its static-modification
    concepts mapped to anthem effects (the old projection folded a static
    ability's modifications into its ``effects``). Costs are excluded — the
    old IR carries an activation cost as a string, never as an Effect.
    """
    effects = [_effect(c, cov) for c in unit.effects]
    effects.extend(_static_effect(c, cov) for c in unit.statics)
    kind = _ability_kind(unit)
    return Ability(
        kind=kind,
        effects=tuple(effects),
        trigger=_trigger(unit) if kind == "triggered" else None,
    )


def compat_card(tree: ConceptTree, cov: CompatCoverage | None = None) -> Card:
    """Build the minimal old-IR ``Card`` for one concept tree.

    ``cov`` (caller-owned, aggregatable across a corpus) tallies every effect
    node into ported / explicitly-unported buckets; pass ``None`` to discard
    the accounting.
    """
    cov = cov if cov is not None else CompatCoverage()
    abilities = tuple(_ability(u, cov) for u in tree.units)
    return Card(
        oracle_id=tree.oracle_id,
        name=tree.name,
        faces=(Face(name=tree.name, abilities=abilities),),
    )
