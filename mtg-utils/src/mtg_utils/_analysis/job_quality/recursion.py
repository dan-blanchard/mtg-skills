"""Recursion — how well a card brings cards back out of a graveyard (the
Commander template's Recursion row).

A card is in the job when one of its abilities returns a card from a graveyard
to the battlefield, to your hand or onto the top of your library, or lets you
cast or play cards from your graveyard, or when the card brings ITSELF back out
of a graveyard or exile. Every other card scores ``None`` (Buried Alive puts
cards INTO a graveyard: a tutor, not recursion).

The walks are the lanes' own, run per ability unit on a one-unit view:

- ``crosswalk.graveyard_recursion`` (the ``creature_recursion`` and
  ``permanent_recast`` lanes' read), its typing ``recursion_card_types`` (Animate
  Dead's Enchant keyword), and ``crosswalk.chosen_graveyard_recursion`` for a
  return bound to a card an earlier clause chose in a graveyard (Meren of Clan
  Nel Toth, Victimize — which ``graveyard_recursion`` can't see);
- Living Death's exile-then-return (``card_advantage._exiled_set_reanimation``);
- a recovered reanimate / graveyard-return residue
  (``_shared.recovered_card_recursion``) and the ``graveyard-return`` preset's
  ``graveyard_return_direction`` (its modal, opponent-chooses and cost arms);
- a ``GraveyardCastPermission`` static for other cards (Muldrotha, Lurrus,
  Crucible of Worlds);
- the card's own return (``card_advantage.self_return_routes`` — Bloodghast,
  Gravecrawler; undying and persist, CR 702.93a / 702.79a: "When this permanent
  is put into a graveyard from the battlefield, ... return it to the
  battlefield") and a dies-return granted to another (the ``dies_recursion``
  lane: Feign Death).

The read's own calls (not rules):

- A shuffle into the library (Timetwister, Elixir of Immortality, Gaea's
  Blessing) or a put on the bottom (Reito Lantern) returns no card to use: not
  recursion. Only a put on TOP of the library is, at a lower rate than hand.
- A spell's own second cast (flashback, jumpstart, retrace) is that spell's
  reuse, not recursion; a permanent cast from its graveyard (Gravecrawler, an
  escape creature) is. A return of itself from the battlefield or the stack
  (a bounce, buyback) never left play.
- A return that names no card it chose (a bare back-reference, phase's
  ``Any``) is not read: Desertion's countered spell is a stack move phase types
  as from a graveyard.

Per unit the read takes where the card goes, what may come back (any card or
a permanent card; a creature card; a typed or conditioned card; only itself),
whether its mana value or power is capped, whether it returns every matching
card (a mass reanimation), whether every player gets theirs (Exhume, Living
Death), whether it repeats (a trigger other than the
card's own entering or dying, an activation that doesn't spend the card or
its loyalty, a static), its speed (an instant or flash, CR 702.8a; an
activation, CR 117.1b, not held to sorcery speed, CR 602.5d, nor a loyalty
ability, CR 606.3) and its cost.

Fitted (2026-10-31) by ridge regression against -log10(EDHREC rank) on the
1,802 commander-legal nonland cards the read scores: cross-validated Spearman
0.36 (0.38 in sample). The precon guides' recursion adds sit at the 80th
percentile of their color identity's recursion by this read (top decile 0.30),
the 88th by play-rate (0.47) and the 86th by the blend with play-rate (0.45;
n=53). On the cut side, the bottom two recursion cards of each precon hold 6
of the guides' 20 cuts among the precons' 92 recursion cards, as by play-rate
(6; mana value 5). The blend trails
play-rate, so the read GATES an upgrade's candidates and doesn't order them.
Against the lanes' keys (``creature_recursion``, ``reanimator``,
``dies_recursion``, ``self_recurring``'s graveyard routes, ``permanent_recast``'s
reanimate and land subjects, the ``graveyard-return`` preset) it scores 90 cards
none carries (Victimize, Meren, Muldrotha, Lurrus, Noxious Revival) and misses
20: the shuffles above and the residues below.

Measured, dropped as reading the card wrong or not at all:

- a life cost (Reanimate's "lose life equal to its mana value", Phyrexian
  Reclamation's 2 life): +0.27, a cost scored as a gain — Reanimate's
  play-rate;
- a sacrifice (Victimize): +0.09, likewise;
- several cards ("up to two target creature cards"): 0.00;
- the mana value itself: 0.00 (a cast cost of 2 or less is kept, +0.08);
- a typed or conditioned card below a creature card: 0.00 (both 0);
- any card above a permanent card: -0.03 (both read as broad, +0.09);
- a creature: -0.02;
- flashback on a recursion spell: 0.00.

A modal double-faced spell // land is kept (+0.90, 11 cards: Malakir Rebirth,
Agadeem's Awakening), as the protection read's is.

Known misreads: Cleansing Meditation, which phase parses as returning every
card in your graveyard (0.49, among the read's top scores); Phyrexian Reclamation and
Whip of Erebos, engines whose per-use mana (-0.04 a mana) puts them near the
middle; Rancor and Spine of Ish Sah, whose own return is a rider on another job.
Phase leaves some returns as residues the read can't type (Custodi Soulcaller,
Venerable Warsinger, Liliana's Talent, All Hallow's Eve): they score ``None``.

The deck context (:func:`deck_fit`, ``JobRead.fit``): a return of creature
cards only needs creature cards in the deck — a token is no card to return, it
ceases to exist in the graveyard (CR 111.7) — and is full at a third of the
nonland deck; graveyard fillers (self-mill, a sacrifice outlet, a discard
outlet) lift it the last quarter, full at a tenth. Any-card, permanent and
self recursion run in any deck. The read's own reference shares, as card
draw's are: on the 25 precons Reanimate's fit runs from 0.75 (Planeswalker
Party, Blame Game) to 1.0 (Blood Rites, Graveyard Overdrive, Sultai Arisen).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from mtg_utils._analysis.job_quality._common import (
    JOB_READS,
    activation_mana,
    cast_cost,
    faces,
    land_back,
    one_unit,
    unit_kind,
)
from mtg_utils._analysis.lanes import graveyard_return_direction
from mtg_utils._analysis.lanes._shared import recovered_card_recursion
from mtg_utils._analysis.lanes.card_advantage import (
    _dies_recursion,
    _exiled_set_reanimation,
    _own_nodes,
    self_return_routes,
)
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._analysis.write_back import MISSING
from mtg_utils._card_ir.crosswalk import (
    chosen_graveyard_recursion,
    controller_paid_cost_leaves,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    graveyard_recursion,
    is_self_discard_cost,
    iter_typed_nodes,
    recursion_card_types,
    static_mode_tag,
    tag_of,
    watches_itself,
)
from mtg_utils._card_ir.recovery import CARD
from mtg_utils.theme_presets import matches, signal_keys_for

if TYPE_CHECKING:
    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

Dest = Literal["battlefield", "cast", "hand", "library"]
#: What may come back: any card or a permanent card (``broad``), a creature
#: card, a typed or conditioned card (``narrow``), or only the card itself.
What = Literal["broad", "creature", "narrow", "self"]

_DEST_RANK: dict[Dest, int] = {"battlefield": 3, "cast": 2, "hand": 1, "library": 0}
_WHAT_RANK: dict[What, int] = {"broad": 3, "creature": 2, "narrow": 1, "self": 0}
#: The card's own return out of a graveyard or exile, by where it lands
#: (``card_advantage.SelfReturnRoute``): a token copy (embalm, eternalize) and a
#: transformed return come back to the battlefield too.
_SELF_ROUTE_DEST: dict[str, Dest] = {
    "graveyard_to_battlefield": "battlefield",
    "graveyard_to_battlefield_transformed": "battlefield",
    "graveyard_to_battlefield_as_aura": "battlefield",
    "graveyard_to_token": "battlefield",
    "exile_to_battlefield": "battlefield",
    "graveyard_to_hand": "hand",
    "exile_to_hand": "hand",
    "graveyard_to_stack": "cast",
    "graveyard_to_stack_transformed": "cast",
}
#: The core types of a permanent card (Sun Titan's ruling: an artifact,
#: creature, enchantment, land or planeswalker card), and the filter word.
_PERMANENT_TYPES = frozenset(
    {"Permanent", "Artifact", "Creature", "Enchantment", "Land", "Planeswalker"}
)
#: Filter predicates that cap a returned card's size, not its kind.
_CAP_PREDICATES = frozenset({"Cmc", "PtComparison"})
#: Filter predicates that say where the card is or whose it is.
_PLACE_PREDICATES = frozenset({"InZone", "Owned", "Another", "Other", "NonToken"})
#: A filter naming an object an earlier clause produced, or none (``Any``).
_BACK_REFS = frozenset({"ParentTarget", "TrackedSet", "TrackedSetFiltered", "Any"})
#: The trigger events that fire once per time the card itself enters or leaves:
#: on the card's own such trigger the return happens once (Gravedigger, undying).
_ONCE_EVENTS = frozenset({"enters", "dies", "leaves", "entersorhauntedcreaturedies"})
_LOYALTY_LEAVES = frozenset({"Loyalty", "RemoveLoyalty", "AddLoyalty"})


@dataclass(frozen=True)
class _Return:
    """One recursion an ability carries."""

    dest: Dest
    what: What
    creature: bool = False  # only creature cards come back (the deck must hold them)
    capped: bool = False  # the returned card's mana value or power is capped
    mass: bool = False  # every matching card ("all creature cards")
    symmetric: bool = False  # every player gets theirs back
    repeat: bool = False
    instant: bool = False
    use_mana: int | None = None  # an activation's mana per use
    discard: bool = False  # a discard paid as a cost


@dataclass(frozen=True)
class _Hit:
    """One return of another card: where, what, and the moving node."""

    dest: Dest
    what: What
    creature: bool
    capped: bool
    node: object


def _list(x: object) -> list:
    return x if isinstance(x, list) else []


def _what(types: Sequence[str], filt: object) -> tuple[What, bool, bool]:
    """How broad a returned card's filter is, whether it is creature cards only,
    and whether it caps the card's mana value or power (Sun Titan's "mana value
    3 or less")."""
    preds = set(filter_predicates(filt)) - _PLACE_PREDICATES
    capped = bool(preds & _CAP_PREDICATES)
    cores = set(types) - {"Card"}
    creature = cores == {"Creature"}
    if filter_subtypes(filt) or preds - _CAP_PREDICATES:
        return "narrow", creature, capped
    if not cores or "Permanent" in cores:
        return "broad", False, capped
    if creature:
        return "creature", True, capped
    if "Creature" in cores and cores <= _PERMANENT_TYPES:
        return "broad", False, capped  # "artifact or creature card"
    return "narrow", False, capped


def _onto_top(node: object) -> bool:
    """A put on top of its owner's library: drawn again."""
    return (
        tag_of(node) == "PutAtLibraryPosition"
        and tag_of(getattr(node, "position", None)) == "Top"
    )


def _graveyard_hits(tree: ConceptTree, u: AbilityUnit) -> list[_Hit]:
    """The returns of another card from a graveyard among ``u``'s own nodes."""
    out: list[_Hit] = []
    itself = u.origin == "trigger" and watches_itself(u.node)
    for n in _own_nodes(u):
        hit = graveyard_recursion(n) or chosen_graveyard_recursion(u, n)
        if hit is None:
            continue
        if hit.dest == "library" and not _onto_top(n):
            continue  # a shuffle or a bottom: no card comes back to use
        filt = hit.filter
        ref = tag_of(filt)
        if ref == "SelfRef" or (ref == "TriggeringSource" and itself):
            continue  # the card itself: its self-return
        if ref == "TriggeringSource":
            # "Whenever another creature you control dies, return it": the
            # watched card.
            filt = getattr(u.node, "valid_card", None)
            types = filter_core_types(filt)
        else:
            types = recursion_card_types(tree, n, filt, u)
            if not types and ref in _BACK_REFS:
                continue  # names no graveyard card it chose (Desertion's spell)
        what, creature, capped = _what(types, filt)
        out.append(
            _Hit(cast("Dest", hit.dest), what, creature=creature, capped=capped, node=n)
        )
    return out


def _unit_hits(tree: ConceptTree, u: AbilityUnit, *, has_self: bool) -> list[_Hit]:
    """Every return of a card other than this one ``u`` carries; the fallbacks
    (a recovered residue, the graveyard-return preset's arms, a graveyard cast
    permission) only where the typed walk finds none."""
    out = _graveyard_hits(tree, u)
    if _exiled_set_reanimation(u):
        node = next(
            (
                n
                for n in _own_nodes(u)
                if tag_of(n) == "ChangeZoneAll"
                and getattr(n, "destination", None) == "Battlefield"
            ),
            u.node,
        )
        out.append(
            _Hit("battlefield", "creature", creature=True, capped=False, node=node)
        )
    if out:
        return out
    for c in u.effects:
        if recovered_card_recursion(c, (CARD,)):
            dest: Dest = "battlefield" if c.recovered_by == "reanimate" else "hand"
            types = [t for t in c.subject if t in _PERMANENT_TYPES]
            what: What = "creature" if types == ["Creature"] else "broad"
            out.append(
                _Hit(
                    dest,
                    what,
                    creature=what == "creature",
                    capped=False,
                    node=c.node,
                )
            )
    if not out and not has_self and graveyard_return_direction(one_unit(tree, u)):
        out.append(_Hit("hand", "narrow", creature=False, capped=False, node=u.node))
    if out:
        return out
    for sdef in u.static_defs():
        aff = getattr(sdef, "affected", None)
        if static_mode_tag(sdef) == "GraveyardCastPermission" and tag_of(aff) != (
            "SelfRef"
        ):
            what, creature, capped = _what(filter_core_types(aff), aff)
            out.append(_Hit("cast", what, creature=creature, capped=capped, node=sdef))
    return out


def _self_dests(tree: ConceptTree, u: AbilityUnit) -> list[Dest]:
    """Where ``u`` brings the card itself back to out of a graveyard or exile —
    ``self_return_routes`` on ``u`` alone (the card's keyword routes are read
    once, by :func:`_returns`), or a granted dies-return (Feign Death)."""
    view = dataclasses.replace(tree, units=(u,), card_keywords=())
    spell = tree.is_type("Instant") or tree.is_type("Sorcery")
    dests = [
        _SELF_ROUTE_DEST[r]
        for r in self_return_routes(view)
        if r in _SELF_ROUTE_DEST and not (spell and _SELF_ROUTE_DEST[r] == "cast")
    ]
    if not dests and _dies_recursion(view):
        return ["battlefield"]
    return dests


def _count(u: AbilityUnit, node: object) -> tuple[bool, bool]:
    """(mass, symmetric): a ``ChangeZoneAll`` returns every matching card; every
    player gets theirs under an each-player scope (Exhume's ``player_scope``) or
    a mass return not limited to your graveyard (Living Death)."""
    mass = tag_of(node) == "ChangeZoneAll"
    symmetric = (
        mass
        and filter_controller(effect_filter(cast("TypedMirrorNode", node))) != "You"
    )
    for n in u.iter_typed():
        if tag_of(getattr(n, "player_scope", None)) == "All" and any(
            x is node for x in iter_typed_nodes(n)
        ):
            symmetric = True
    return mass, symmetric


def _costs(u: AbilityUnit) -> tuple[bool, bool]:
    """(a discard cost, a use that spends the card: a sacrifice or exile of
    itself, or a loyalty ability that removes loyalty)."""
    discard = spends = False
    for pc in controller_paid_cost_leaves(u):
        t = tag_of(pc.leaf)
        itself = (
            t == "Sacrifice" and tag_of(getattr(pc.leaf, "target", None)) == "SelfRef"
        ) or (t == "Exile" and tag_of(getattr(pc.leaf, "filter", None)) == "SelfRef")
        if itself or (
            t in _LOYALTY_LEAVES and (getattr(pc.leaf, "amount", 0) or 0) < 0
        ):
            spends = True
        elif is_self_discard_cost(pc.leaf):
            discard = True
    return discard, spends


def _repeats(u: AbilityUnit, kind: str, *, spends: bool) -> bool:
    """A static, an activation that doesn't spend the card, or a trigger other
    than the card's own entering or leaving (Sun Titan's attacks, Meren's end
    step, Bloodghast's landfall)."""
    if kind == "activated":
        return not spends
    if kind == "static":
        return True
    if u.origin == "trigger":
        return not (u.trigger_event in _ONCE_EVENTS and watches_itself(u.node))
    return False


def _instant(tree: ConceptTree, u: AbilityUnit, kind: str) -> bool:
    """An instant or flash spell (CR 702.8a), or an activation not held to
    sorcery speed (CR 602.5d) and not a loyalty ability (CR 606.3)."""
    if kind == "spell":
        return tree.is_type("Instant") or "Flash" in tree.card_keywords
    if kind != "activated":
        return False
    restrictions = {
        tag_of(r) for r in _list(getattr(u.node, "activation_restrictions", None))
    }
    leaves = {tag_of(pc.leaf) for pc in controller_paid_cost_leaves(u)}
    return "AsSorcery" not in restrictions and not leaves & _LOYALTY_LEAVES


def _returns(card: dict) -> list[_Return]:
    """Every recursion ``card`` carries, on every face."""
    out: list[_Return] = []
    for tree in signal_trees_for(card, bulk=card):
        for u in tree.units:
            dests = _self_dests(tree, u)
            hits = _unit_hits(tree, u, has_self=bool(dests))
            if not (hits or dests):
                continue
            kind = unit_kind(u)
            discard, spends = _costs(u)
            unit = _Return(
                dest="hand",
                what="self",
                repeat=_repeats(u, kind, spends=spends),
                instant=_instant(tree, u, kind),
                use_mana=activation_mana(u),
                discard=discard,
            )
            for h in hits:
                mass, symmetric = _count(u, h.node)
                out.append(
                    dataclasses.replace(
                        unit,
                        dest=h.dest,
                        what=h.what,
                        creature=h.creature,
                        capped=h.capped,
                        mass=mass,
                        symmetric=symmetric,
                    )
                )
            out.extend(dataclasses.replace(unit, dest=d) for d in dests)
        if tree.is_type("Instant") or tree.is_type("Sorcery"):
            continue
        # A keyword return phase leaves to its rules engine (embalm, escape,
        # disturb — ``card_advantage.RECURSION_KEYWORDS``): once.
        if not any(r.what == "self" for r in out):
            keyword = self_return_routes(dataclasses.replace(tree, units=()))
            out.extend(
                _Return(dest=_SELF_ROUTE_DEST[r], what="self")
                for r in sorted(keyword)
                if r in _SELF_ROUTE_DEST
            )
    return out


#: Recursion's weights, log10 play-rate per unit (ridge fit, 2026-10-31,
#: standardised weight / feature sd, rounded).
WEIGHTS: dict[str, float] = {
    "battlefield": 0.19,  # onto the battlefield
    "cast": 0.23,  # cast or played from the graveyard (Muldrotha, Crucible)
    "library": -0.05,  # only onto the top of the library
    "broad": 0.09,  # any card, or any permanent card
    "self_only": -0.15,  # only the card itself (undying, Bloodghast)
    "capped": -0.10,  # a capped mana value or power (Sun Titan's 3)
    "mass": 0.21,  # every matching card (Living Death, Rise of the Dark Realms)
    "symmetric": -0.13,  # every player gets theirs (Exhume, Living Death)
    "repeat": 0.10,  # a trigger, activation or static that repeats
    "use_mana": -0.04,  # per mana an engine's activation asks
    "instant": 0.03,  # instant speed
    "cheap": 0.08,  # cast cost 2 or less
    "discard": -0.14,  # a discard paid as a cost
    "land_back": 0.90,  # a modal double-faced card whose back is a land
}


def features(card: dict) -> dict[str, float] | None:
    """The recursion read's features for ``card``, or ``None`` when it returns
    no card from a graveyard and never itself."""
    rets = _returns(card)
    if not rets:
        return None
    dest = max((r.dest for r in rets), key=_DEST_RANK.__getitem__)
    what = max((r.what for r in rets), key=_WHAT_RANK.__getitem__)
    uses = [r.use_mana for r in rets if r.repeat and r.use_mana is not None]
    return {
        "battlefield": float(dest == "battlefield"),
        "cast": float(dest == "cast"),
        "library": float(dest == "library"),
        "broad": float(what == "broad"),
        "self_only": float(what == "self"),
        "capped": float(all(r.capped for r in rets if r.what == what)),
        "mass": float(any(r.mass for r in rets)),
        "symmetric": float(any(r.symmetric for r in rets)),
        "repeat": float(any(r.repeat for r in rets)),
        "use_mana": float(min(uses)) if uses else 0.0,
        "instant": float(any(r.instant for r in rets)),
        "cheap": float(cast_cost(card) <= 2),
        "discard": float(any(r.discard for r in rets)),
        "land_back": float(land_back(card)),
    }


# ── Deck context: the cards a creature recursion needs in its deck ──────────

#: A creature recursion is full at this share of creature cards in the nonland
#: deck, and its graveyard fillers' last quarter at this share of fillers.
_CREATURE_REFERENCE = 1 / 3
_FILL_REFERENCE = 1 / 10
_FILL_PART = 0.25
#: oracle_id -> whether the card returns only creature cards (persisted by the
#: job-read sidecar).
_CREATURE_ONLY = JOB_READS.memo("recursion_creature_only")


def creature_only(card: dict) -> bool:
    """Whether every card ``card`` brings back is a creature card from a
    graveyard (Reanimate, Gravedigger): the recursion its deck must feed."""
    oid = card.get("oracle_id")
    if oid and (hit := _CREATURE_ONLY.get(oid)) is not MISSING:
        return cast("bool", hit)
    rets = _returns(card)
    out = bool(rets) and all(r.creature for r in rets)
    if oid and signal_trees_for(card, bulk=card):
        _CREATURE_ONLY.put(oid, out)
    return out


def _fills(record: dict) -> bool:
    """A graveyard filler: self-mill, a sacrifice outlet or a discard outlet
    (the presets and the lane key)."""
    return (
        matches("self-mill", record)
        or matches("sacrifice-outlet", record)
        or "discard_outlet" in signal_keys_for(record)
    )


def deck_fit(card: dict, deck_records: Sequence[dict]) -> float:
    """The share of ``card``'s recursion its deck (one record per copy) can
    feed, in [0, 1]: for a creature recursion, the deck's share of creature
    cards among its nonland cards against :data:`_CREATURE_REFERENCE`, its last
    quarter scaled by the share of graveyard fillers. 1.0 for any other
    recursion, or with no deck."""
    if not deck_records or not creature_only(card):
        return 1.0
    nonland = [r for r in deck_records if "Land" not in faces(r)[0]]
    if not nonland:
        return 0.0
    creatures = sum("Creature" in faces(r)[0] for r in nonland) / len(nonland)
    fill = sum(map(_fills, nonland)) / len(nonland)
    body = min(1.0, creatures / _CREATURE_REFERENCE)
    return body * (1 - _FILL_PART + _FILL_PART * min(1.0, fill / _FILL_REFERENCE))
