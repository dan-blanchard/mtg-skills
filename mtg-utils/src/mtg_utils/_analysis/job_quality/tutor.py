"""Tutor — how well a card finds a card from your library (the ``tutor`` lane's
nonland half: the Commander template's Tutors row).

To search for a card in a zone is to look at all cards in that zone and find one
that matches the given description (CR 701.23a). A member is a card with the
``tutor`` signal key one of whose own-library searches can find a nonland card
(``crosswalk.self_searches`` per tutor unit, ``unit_is_self_tutor``; a filter
phase leaves unresolved inherits its card's resolved searches, as Tithe's
"instead ... two Plains cards" does). A card whose every search finds only
lands (``search_filter_land_facts``: Sylvan Scrying, Expedition Map, Bushwhack)
scores ``None``, as does a land fetch to the battlefield (Cultivate: the
``ramp`` lane, no ``tutor`` key at all).

A search that puts the card into your graveyard (Entomb, Buried Alive) is a
tutor here, the lane's call: it finds the one card a reanimation or flashback
deck wants, where the deck uses it, and three precon guides add one. It reads
level with the hand; an exile (Foresight, Selective Memory) reads below.

Each tutor ability is read off its own unit, and the card scores its best one:

- breadth: any card, a card type (creature, artifact, enchantment, instant or
  sorcery, a permanent; or any card of one exact mana value, a transmute's), or
  narrower (a subtype, a named card, the same name);
  a search whose arms include a land reads its nonland arms (Archdruid's Charm's
  creature);
- destination: the battlefield (or cast for free: Sunforger), the hand, the top
  of the library, the graveyard, exile;
- how many: two or more cards found (Buried Alive, Gifts Ungiven);
- repeatability: an activated ability that doesn't pay the card itself away, or
  a trigger that recurs (Razaketh, Sunforger, Birthing Pod). A transmute
  (CR 702.53a: functions only from your hand, "Discard this card"), a "sacrifice
  this" activation, a dies trigger, a Saga chapter and an exploit trigger (CR
  702.110a: "When this creature enters, you may sacrifice a creature", so
  Sidisi, Undead Vizier's tutor fires once) are one-shots;
- speed: an instant, a flash card, an activated ability without "activate only
  as a sorcery" (CR 602.5d);
- cost: the cast cost (``_common.cast_cost``; none for a free alternative cost),
  an activation from hand at its own mana, a repeatable activation's mana per
  use; a sacrifice of another permanent, a discard, and life (paid as a cost,
  Razaketh; or lost on resolution, Vampiric Tutor — CR 119.4: paying life is
  losing it).

Fitted on the 475 commander-legal nonland cards the read scores (ridge,
2026-10-31). Play-rate rewards breadth (any card or a card type over a subtype
or a name, +0.40), a low cost, instant speed and a noncreature, and punishes an
exile. It is silent or contrary on the rest of the agreed design (Dan,
2026-10-31), so those weights are hand-set (ADR-0060's 2026-10-20 amendment),
not fitted:

- any card over a card type, +0.1 (fitted +0.01: the any-card pool runs to
  seven-mana Demons);
- the battlefield over the hand, +0.1 (fitted -0.02: the battlefield tutors run
  to mana-value-bounded ones);
- two or more found and a repeatable tutor, +0.1 each (fitted -0.01, -0.04);
- a sacrifice of another permanent, -0.1, and life, -0.05 (fitted +0.03 and
  +0.42: Diabolic Intent, Natural Order and Vampiric Tutor are played despite
  them).

Each costs the fit at most 0.01 of cross-validated Spearman: 0.52 against
play-rate (0.53 fitted alone); 0.53 over every card the read scores. The top of
the library and the graveyard read level with the hand: the fit put them above
it (+0.24, +0.15 — Vampiric, Mystical, Enlightened and Worldly Tutor, Entomb and
Buried Alive are staples for their speed and their decks), and ranking them
below lowered the guides' adds. The precon guides' tutor adds (n=36) sit at the
76th percentile of their color identity's tutors by this read, 84th by
play-rate, 77th by the blend of the two (in the top ten 5, 11 and 7): it GATES
(``JobRead.orders`` False).
The adds it read lowest were tribal tutors in tribal decks (Sliver Overlord,
Faerie Harbinger, Forerunner of the Empire): a subtype search is narrow to any
deck but the tribe's, so given its deck (``JobRead.in_deck``,
:func:`deck_features`) a subtype search is broad where the deck's creature cards
share the subtype at :data:`_TRIBE_REFERENCE`. An X tutor costs its X
(``_common.cast_cost``'s ``X_ASSUMED``: Chord of Calling 6, Green Sun's Zenith
4) and a Pact its upkeep payment (:func:`_pact_mana`: Summoner's Pact 4), both
since 2026-10-31.

What it can't read, phase parse gaps to report upstream
(``docs/plans/phase-upstream-reports.md``): an opponent's say (Rhystic Tutor's
"unless any player pays {2}" sits on an ``Unimplemented`` head); Grim Reminder's
revealed card read as put into the hand. What it leaves by design: a search
inside an emblem a planeswalker's ultimate makes (Kaito Shizuki's, Garruk,
Unleashed's — typed inside ``CreateEmblem``'s triggers, but an ultimate's emblem
is no tutor slot), which scores ``None``. Distant Memories (search, exile, an
opponent may hand it over, else draw three) reads as a tutor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._analysis.job_quality._common import (
    activation_mana,
    cast_cost,
    faces,
    free_cast,
    land_back,
    mana_in,
    unit_kind,
    unpriced,
)
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    activation_zone,
    at_instant_speed,
    filter_core_types,
    filter_subtypes,
    iter_cost_leaves,
    iter_search_landings,
    iter_typed_nodes,
    search_count,
    search_filter_land_facts,
    self_searches,
    tag_of,
    unit_is_self_tutor,
)
from mtg_utils.theme_presets import signal_keys_for
from mtg_utils.type_line import split_type_line

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
    from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode

#: Filter properties that pin a search to one card or a few: a name, the same
#: name as another object, a shared quality.
_NARROW_PROPS = frozenset(
    {"Named", "SameNameAsParentTarget", "SharesQuality", "DifferentNameFrom"}
)
#: Destinations, best first (the read's ordering of where a found card lands).
_DESTS = ("battlefield", "hand", "top", "graveyard", "exile")
_ZONE_DEST = {
    "Battlefield": "battlefield",
    "Hand": "hand",
    "Library": "top",
    "Graveyard": "graveyard",
    "Exile": "exile",
}
#: Trigger events that fire once in a permanent's life: it dies or leaves, a
#: Saga chapter (a lore counter added), its own cast, an exploit (CR 702.110a).
_ONCE_EVENTS = frozenset({"dies", "leaves", "exploited", "counter_added", "cast"})


@dataclass(frozen=True)
class _Unit:
    """One tutor ability: what it finds, where it puts it, how often, at what
    cost."""

    breadth: int  # 2 any card, 1 a card type, 0 a subtype or a named card
    dest: str  # one of _DESTS
    count: int  # cards found
    kind: str  # spell | etb | repeat | once
    instant: bool
    act_mana: int | None  # an activated ability's mana cost
    from_hand: bool  # an activation from hand (transmute)
    sacrifice: bool  # sacrifices another permanent
    discard: bool  # discards another card
    life: bool  # pays or loses life
    subtypes: frozenset[str] = frozenset()  # the subtypes a narrow search names


def _list(x: object) -> list:
    return x if isinstance(x, list) else []


def _breadth(filt: object) -> int | None:
    """What a search filter can find: 2 any card, 1 a card type, 0 narrower (a
    subtype, a name); ``None`` when phase left it unresolved. An ``Or``'s land
    arms are skipped while a nonland arm remains."""
    t = tag_of(filt)
    if t in ("Or", "And"):
        subs = _list(getattr(filt, "filters", None))
        nonland = [f for f in subs if search_filter_land_facts(f) != (True, True)]
        arms = [b for f in nonland or subs if (b := _breadth(f)) is not None]
        return max(arms) if arms else None
    if t != "Typed":
        return None
    plist = _list(getattr(filt, "properties", None))
    props = {tag_of(p) for p in plist}
    if filter_subtypes(filt) or props & _NARROW_PROPS:
        return 0
    if not _list(getattr(filt, "type_filters", None)) and not props:
        return None
    exact_mv = any(
        tag_of(p) == "Cmc" and getattr(p, "comparator", None) == "EQ" for p in plist
    )
    # A card of one exact mana value (transmute, CR 702.53a: "the same mana
    # value as the discarded card") is no broader than a card type.
    return 1 if exact_mv or set(filter_core_types(filt)) - {"Card"} else 2


def _dest(unit: AbilityUnit) -> str:
    """The best place the unit puts a found card: a ``ChangeZone`` off the
    search (``iter_search_landings``), a ``PutAtLibraryPosition`` (the top), or a
    free cast (``CastFromZone``, read as the battlefield). The hand when it
    names none."""
    found = {_ZONE_DEST.get(d) for d, _tapped in iter_search_landings(unit)}
    for n in iter_typed_nodes(unit.node):
        if tag_of(n) == "CastFromZone":
            found.add("battlefield")
        elif tag_of(n) == "PutAtLibraryPosition":
            found.add("top")
    return next((d for d in _DESTS if d in found), "hand")


def _self_paid(leaf: object) -> bool:
    """A cost leaf that pays the card itself away: discard this card, sacrifice
    or exile it."""
    t = tag_of(leaf)
    if t == "Discard":
        return getattr(leaf, "self_ref", None) is True
    if t in ("Sacrifice", "Exile"):
        target = getattr(leaf, "target", None) or getattr(leaf, "filter", None)
        return tag_of(target) == "SelfRef"
    return False


def _read_unit(
    tree: ConceptTree, unit: AbilityUnit, searches: Sequence[TypedMirrorNode]
) -> _Unit:
    reads = [
        b for s in searches if (b := _breadth(getattr(s, "filter", None))) is not None
    ]
    subtypes = frozenset(
        st for s in searches for st in filter_subtypes(getattr(s, "filter", None))
    )
    leaves = [
        *iter_cost_leaves(getattr(unit.node, "cost", None)),
        *(leaf for c in unit.costs for leaf in iter_cost_leaves(c.node)),
    ]
    from_hand = activation_zone(unit.node) in ("Hand", "Graveyard")
    once = (
        from_hand
        or any(_self_paid(x) for x in leaves)
        or (unit.trigger_event or "") in _ONCE_EVENTS
        or any(
            tag_of(c.node) == "Sacrifice"
            and tag_of(getattr(c.node, "target", None)) == "SelfRef"
            for c in unit.effects
        )
    )
    kind = unit_kind(unit)
    if kind in ("activated", "trigger"):
        kind = "once" if once else "repeat"
    elif kind not in ("spell", "etb"):
        kind = "once"
    return _Unit(
        breadth=max(reads, default=0),
        dest=_dest(unit),
        count=max(search_count(s) for s in searches),
        kind=kind,
        # The one instant-speed read: an activation not held to sorcery speed,
        # or a spell or enters trigger of an instant or flash card.
        instant=(unit.kind == "Activated" or kind in ("spell", "etb"))
        and at_instant_speed(tree, unit),
        act_mana=activation_mana(unit),
        from_hand=from_hand,
        sacrifice=unit.trigger_event == "exploited"
        or any(tag_of(x) == "Sacrifice" and not _self_paid(x) for x in leaves),
        discard=any(tag_of(x) == "Discard" and not _self_paid(x) for x in leaves),
        life=any(tag_of(x) == "PayLife" for x in leaves)
        or any(
            tag_of(c.node) == "LoseLife"
            and tag_of(getattr(c.node, "target", None)) in ("Controller", None)
            for c in unit.effects
        ),
        subtypes=subtypes,
    )


def _units(card: dict) -> list[_Unit]:
    """Every tutor ability of ``card`` that can find a nonland card."""
    if "tutor" not in signal_keys_for(card):
        return []
    found = [
        (tree, u, searches)
        for tree in signal_trees_for(card, bulk=card)
        for u in tree.units
        if unit_is_self_tutor(u) is True and (searches := self_searches(u))
    ]
    facts = {
        id(s): search_filter_land_facts(getattr(s, "filter", None))
        for _t, _u, ss in found
        for s in ss
    }
    resolved = [f for f in facts.values() if f is not None]
    inherit = bool(resolved) and all(only for _can, only in resolved)
    return [
        _read_unit(tree, u, ss)
        for tree, u, ss in found
        if not all(
            inherit if (f := facts[id(s)]) is None else f[1] for s in ss
        )  # a unit that finds only lands
    ]


def _pact_mana(card: dict) -> int:
    """The mana a Pact asks at the next upkeep, or lose the game (Summoner's
    Pact: a delayed trigger paying {2}{G}{G}, else ``LoseTheGame``): the card's
    real cost, paid a turn late. 0 for any other card."""
    total = 0
    for tree in signal_trees_for(card, bulk=card):
        for u in tree.units:
            for n in iter_typed_nodes(u.node):
                if tag_of(n) != "CreateDelayedTrigger":
                    continue
                inner = list(iter_typed_nodes(n))
                if any(tag_of(x) == "LoseTheGame" for x in inner):
                    total += sum(
                        mana_in(getattr(x, "cost", None))
                        for x in inner
                        if tag_of(x) == "PayCost"
                    )
    return total


#: A narrow (subtype) search is as broad as a card type in a deck whose creature
#: cards share that subtype at this rate (a tribal deck: Sliver Overlord's
#: Slivers, Faerie Harbinger's Faeries) — the deck fit the read had none of.
_TRIBE_REFERENCE = 1 / 3


#: Tutor's weights, log10 play-rate per unit (ridge fit, 2026-10-31,
#: standardised weight / feature sd, fitted beside the hand-set ones held
#: fixed, rounded).
WEIGHTS: dict[str, float] = {
    "broad": 0.40,  # any card or a card type, not a subtype or a name
    "cost": -0.06,  # per mana to cast (an activation from hand: its own)
    "cheap": 0.07,  # costs 2 or less
    "instant": 0.05,  # an instant, flash, or an activated ability
    "act_mana": -0.10,  # per mana of a repeatable activation (cap 4)
    "body": -0.07,  # a creature: the tutor rides a body that dies to a sweeper
    "exile": -0.30,  # the found card is exiled
    "discard": -0.10,  # discards another card
    "land_back": 0.44,  # a modal double-faced card whose back is a land
    # Hand-set (see the module docstring): the agreed design, play-rate silent.
    "any_card": 0.1,
    "battlefield": 0.1,  # onto the battlefield, or cast for free
    "multi": 0.1,  # two or more cards found
    "repeat": 0.1,  # a repeatable tutor on a permanent
    "sacrifice": -0.1,  # sacrifices another permanent
    "life": -0.05,  # pays or loses life
}


def _unit_features(
    card: dict, u: _Unit, *, pact: int = 0, tribe_fits: bool = False
) -> dict[str, float]:
    if free_cast(card):
        cost = 0.0
    elif u.from_hand and u.act_mana is not None:
        cost = float(u.act_mana)  # a transmute: cast never, activated from hand
    else:
        cost = cast_cost(card)
        if u.kind == "once" and u.act_mana is not None and not unpriced(card):
            cost += u.act_mana  # cast, then paid once more (Sterling Grove)
    cost += pact  # a Pact's upkeep payment
    return {
        "broad": float(u.breadth >= 1 or tribe_fits),
        "cost": min(cost, 7.0),
        "cheap": float(cost <= 2),
        "instant": float(u.instant),
        "act_mana": float(min(u.act_mana or 0, 4)) if u.kind == "repeat" else 0.0,
        "body": float("Creature" in faces(card)[0]),
        "exile": float(u.dest == "exile"),
        "discard": float(u.discard),
        "land_back": float(land_back(card)),
        "any_card": float(u.breadth == 2),
        "battlefield": float(u.dest == "battlefield"),
        "multi": float(u.count >= 2),
        "repeat": float(u.kind == "repeat"),
        "sacrifice": float(u.sacrifice),
        "life": float(u.life),
    }


def _best(feats: Sequence[dict[str, float]]) -> dict[str, float] | None:
    if not feats:
        return None
    return max(feats, key=lambda f: sum(WEIGHTS[k] * v for k, v in f.items()))


def features(card: dict) -> dict[str, float] | None:
    """The tutor read's features for ``card``'s best tutor ability, or ``None``
    when it has none that can find a nonland card."""
    units = _units(card)
    if not units:
        return None
    pact = _pact_mana(card)
    return _best([_unit_features(card, u, pact=pact) for u in units])


def _tribe_fits(subtypes: frozenset[str], deck: Sequence[dict]) -> bool:
    """Whether ``deck``'s creature cards share one of ``subtypes`` at
    :data:`_TRIBE_REFERENCE` or more."""
    if not subtypes:
        return False
    creatures = [faces(r)[0] for r in deck if "Creature" in faces(r)[0]]
    if not creatures:
        return False
    words = {s.lower() for s in subtypes}  # the split lower-cases its words
    hits = sum(bool(words & set(split_type_line(front)[1])) for front in creatures)
    return hits / len(creatures) >= _TRIBE_REFERENCE


def deck_features(card: dict, deck: Sequence[dict]) -> dict[str, float] | None:
    """The read's features in ``deck`` (``JobRead.in_deck``): a subtype search
    is broad where the deck's creature cards share the subtype (a tribal deck's
    tribal tutor — Sliver Overlord, Faerie Harbinger — finds a card as surely
    as a creature tutor does). ``None`` when the card has no tutor ability."""
    units = _units(card)
    if not units:
        return None
    pact = _pact_mana(card)
    return _best(
        [
            _unit_features(card, u, pact=pact, tribe_fits=_tribe_fits(u.subtypes, deck))
            for u in units
        ]
    )
