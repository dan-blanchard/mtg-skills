"""Commander needs — what a commander's own text asks the deck for, read off its
concept trees, and whether a card supplies it.

The upgrade guides' adds satisfy the commander's own conditions 44-83% of the
time; the tuner's adds 0-10% (``docs/plans/tuner-holistic-review-2026-10-30.md``
§2). The tuner reads the commander only through its lane idents, which project
"whenever you surveil" and "four or more card types among cards in your
graveyard" onto the same umbrella lane as every other graveyard card. This
module reads the commander's trees for three kinds of need:

* **events** — the trigger modes its abilities fire on (``S_triggers.mode``:
  Surveil, LifeLost, a creature token leaving, an enchantment entering): the
  need is the cards that MAKE that event (surveil outlets, drain, token makers,
  enchantments). Read through ``crosswalk.reads.trigger_def_event`` and the
  trigger's typed filters, never the description.
* **conditions** — the quantity a condition node compares (``DistinctCardTypes``
  of the graveyard, a zone's card count, an object count by filter): the need
  is the cards that raise it (a two-type permanent or a self-mill under Winter's
  delirium, a card of the counted type).
* **resources** — what the commander's doer idents produce (tokens of a kind,
  energy, +1/+1 counters, Treasure): the need is the payoffs that consume them
  (``metrics._cares_keys``, the token-doubler lever generalised).

Plus the commander's static payoff idents with no trigger of their own (a
tribal payoff, Felothar's toughness-as-power), whose need is a card of the type
or with the stat.

Three reads go past the trigger's mode (added 2026-10-30, after the plan):

* **mana-value bounds** — a filter with a ``Cmc`` floor on a static ability's
  ``affected`` (Zhulodok: colorless spells with mana value 7 or greater have
  cascade) or on a cast trigger's ``valid_card``, and an effect scaled by the
  GREATEST mana value among spells cast this turn (Rootha's X/X token: a
  ``PropertyAggregate`` ``Max`` of ``ManaValue`` over the turn's ``SpellsCast``),
  whose floor is :data:`BIG_SPELL_MV`. The need is a spell of the filter's types
  (and colour: ``ColorCount == 0`` is colorless, CR 105.2c) at or above the
  floor; an X spell counts, since X is the number chosen while it is on the
  stack (CR 202.3e).
* **spells-per-turn conditions** — a condition or an "activate only if"
  restriction comparing ``SpellsCastThisTurn`` to two or more (Stella Lee's
  copy), or a cast trigger's "second time this ability has resolved this turn"
  (``AbilityUseCountThisTurn``, Ms. Bumbleflower): the need is cheap spells,
  the same read as the ``second_spell_matters`` payoff.
* **opponents drawing** — a ``Draw`` effect whose recipient is a chosen or
  every player, an opponent included (``effect_player_reach``; Ms.
  Bumbleflower's "target opponent draws a card"): the need is the payoffs that
  watch opponents draw (``opponent_draw_matters``: Smothering Tithe,
  Consecrated Sphinx) and the cards that make opponents draw like the
  commander (``target_player_draws``, ``group_hug_draw``).

A :class:`Need` is a set of ident / key / type-line tests and an optional
record predicate; :func:`satisfies` is the one test, and
:func:`need_predicate` the "any need" predicate the scoreboard's
plan-consistency line and the tune's need pages read (ADR: the 2026-10-30 plan,
``docs/plans/tuner-plan-2026-10-30.md``). Partner / background commanders
contribute the union of their needs; a transform commander is read across all
of its faces (``trees_for`` yields every face's tree).

Pure: the record and the trees in, a verdict out. No play-rate, no deck
context beyond the commander's own records.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    effect_player_reach,
    filter_controller,
    filter_core_types,
    filter_mana_value_floor,
    filter_non_types,
    filter_predicates,
    filter_subtypes,
    iter_condition_sites,
    iter_typed_nodes,
    or_arms,
    requires_condition_inner,
    tag_of,
    trigger_def_event,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.type_line import split_type_line

if TYPE_CHECKING:
    from mtg_utils._analysis.signal_specs import Serve

# ── vocabulary ──────────────────────────────────────────────────────────────

#: The card types a type-count condition or a two-type graveyard need counts
#: (CR 205.2a; the ones that appear on Commander-legal cards).
CARD_TYPES: tuple[str, ...] = (
    "artifact",
    "battle",
    "creature",
    "enchantment",
    "instant",
    "kindred",
    "land",
    "planeswalker",
    "sorcery",
)

#: Keys whose emitters put the commander's OWN cards into the graveyard (a
#: self-mill, a surveil, a loot, a sacrifice): what a graveyard-count or
#: card-type condition is raised by.
_LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(s.lower() for s in LAND_SUBTYPES)
_GRAVEYARD_FILL_KEYS: frozenset[str] = frozenset(
    {"graveyard_makers", "mill_makers", "discard_makers", "discard_outlet"}
)
#: Keys whose emitters take cards OUT of the commander's graveyard (what a
#: "whenever one or more cards leave your graveyard" trigger is fed by).
_GRAVEYARD_LEAVE_KEYS: frozenset[str] = frozenset(
    {
        "creature_recursion",
        "reanimator",
        "permanent_recast",
    }
)
#: Umbrella keys a tenth of the pool carries: never a need's test on their own
#: (``graveyard_matters`` under Quintorius made "cards leaving your graveyard"
#: a 1,240-card page topped by Faithless Looting and Farewell, a hair under the
#: broad cutoff, so a graveyard commander's theme cuts went to it).
_UMBRELLA_KEYS: frozenset[str] = frozenset(
    {
        "graveyard_matters",
        "graveyard_makers",
        "permanent_etb",
        "enchantments_matter",
        "artifacts_matter",
        "creatures_matter",
        "attack_matters",
    }
)
#: Keys whose emitters make a creature of yours die or leave (fodder and the
#: outlets that spend it) — what a dies / leaves / sacrificed trigger is fed by.
_DEATH_FEED_KEYS: frozenset[str] = frozenset(
    {"sacrifice_outlets", "edict_makers", TOKEN_MAKER, "mass_token_makers"}
)
#: Keys whose emitters let your creatures connect — what a "deals combat damage
#: to a player" trigger is fed by.
_EVASION_KEYS: frozenset[str] = frozenset(
    {"evasion_self", "team_evasion_grant", "keyword_grant_target", "lure_makers"}
)
_EVASION_KEYWORDS: frozenset[str] = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "unblockable",
        "skulk",
        "fear",
        "intimidate",
        "shadow",
    }
)

#: Trigger event → the keys of the cards that make the event happen. An event
#: not listed here opens no need (an "attacks" trigger is fed by every creature;
#: a "phase" trigger carries its condition instead).
_EVENT_MAKER_KEYS: Mapping[str, frozenset[str]] = {
    "surveil": frozenset({"topdeck_selection"}),  # subject-checked below
    "scry": frozenset({"topdeck_selection"}),
    "explored": frozenset({"explore_makers"}),
    "life_gained": frozenset({"lifegain_makers"}),
    "life_lost": frozenset({"lifeloss_makers", "direct_damage"}),
    "discarded": frozenset({"discard_makers", "discard_outlet"}),
    "sacrificed": _DEATH_FEED_KEYS,
    "exploited": _DEATH_FEED_KEYS,
    "dies": _DEATH_FEED_KEYS,
    "leaves": _DEATH_FEED_KEYS | frozenset({"blink_flicker"}),
    "counter_added": frozenset(
        {"plus_one_makers", "any_counter_makers", "proliferate_makers"}
    ),
    "drawn": frozenset(
        {"card_draw_engine", "cantrip", "draw_for_each", "activated_draw"}
    ),
    "deals_damage": _EVASION_KEYS,
    "taps": frozenset({"tapper_engine", "untap_engine"}),
    "rolled_die": frozenset({"dice_makers"}),
    "cast_spell": frozenset(),  # the filter's types decide (below)
    "enters": frozenset(),  # the filter's types decide (below)
    "changes_zone": frozenset(),  # origin / destination decide (below)
    "investigated": frozenset({"clue_makers"}),
    "energy_paid": frozenset({"energy_makers"}),
}

#: A commander payoff ident with no trigger mode of its own → the type-line
#: words a card needs to satisfy it.
_TYPE_PAYOFF_KEYS: Mapping[str, frozenset[str]] = {
    "artifacts_matter": frozenset({"artifact"}),
    "enchantments_matter": frozenset({"enchantment"}),
    "superfriends_matters": frozenset({"planeswalker"}),
    "voltron_matters": frozenset({"aura", "equipment"}),
    "lands_matter": frozenset({"land"}),
    "historic_matters": frozenset({"legendary", "artifact", "saga"}),
}

#: Core type → the token-maker keys that also put that type onto the
#: battlefield (an artifact-token maker enters an artifact).
_TYPE_TOKEN_KEYS: Mapping[str, frozenset[str]] = {
    "creature": frozenset({TOKEN_MAKER, "mass_token_makers"}),
    "artifact": frozenset(
        {"treasure_makers", "clue_makers", "food_makers", "blood_makers"}
    ),
    "enchantment": frozenset(),
}


# ── the need ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Need:
    """One thing the commander asks the deck for.

    ``kind`` is ``"event"`` / ``"condition"`` / ``"resource"`` / ``"redundancy"``
    / ``"payoff"``;
    ``source`` the commander ability (its description) the need was read from.
    A card satisfies the need when any arm holds: it emits one of ``idents``
    (exact ``key|scope|subject``), one of ``keys`` (any scope / subject), its
    type line holds every word of one of ``types`` (each a frozenset of words:
    ``{"aura"}``, ``{"artifact", "creature"}``), or ``predicate`` holds on its
    record."""

    kind: str
    label: str
    source: str
    idents: frozenset[str] = frozenset()
    keys: frozenset[str] = frozenset()
    types: frozenset[frozenset[str]] = frozenset()
    predicate: Callable[[dict], bool] | None = field(default=None, compare=False)

    @property
    def empty(self) -> bool:
        return not (self.idents or self.keys or self.types or self.predicate)


def _card_idents(card: Mapping, *, membership: bool = True) -> frozenset[str]:
    from mtg_utils.theme_presets import _signal_idents_for

    record = card if isinstance(card, dict) else dict(card)
    return _signal_idents_for(record, include_membership=membership)


def _type_words(card: Mapping) -> frozenset[str]:
    """Every type-line word across the card's faces, lower-cased."""
    faces = card.get("card_faces") or [card]
    words: set[str] = set()
    for face in faces:
        types, subs = split_type_line(face.get("type_line") or "")
        words.update(types)
        words.update(subs)
    return frozenset(words)


def card_type_count(card: Mapping) -> int:
    """How many card types (CR 205.2a) the card holds across its faces — what
    it adds to a "card types among cards in your graveyard" count. A battle's
    back face is a creature, an artifact creature two types; a modal
    double-faced card's land face counts (both faces are the card)."""
    return len(_type_words(card) & set(CARD_TYPES))


def satisfies(card: Mapping, need: Need) -> bool:
    """Whether ``card`` supplies ``need``."""
    if need.predicate is not None and need.predicate(dict(card)):
        return True
    if need.types:
        words = _type_words(card)
        if any(t <= words for t in need.types):
            return True
    if need.idents or need.keys:
        idents = _card_idents(card)
        if need.idents & idents:
            return True
        if need.keys and any(i.split("|", 1)[0] in need.keys for i in idents):
            return True
    return False


def need_predicate(needs: Sequence[Need]) -> Callable[[dict], bool]:
    """The "supplies any of the commander's needs" test."""

    def holds(card: dict) -> bool:
        return any(satisfies(card, n) for n in needs)

    return holds


#: A need more than this share of the pool supplies is BROAD ("instants and
#: sorceries" under a spellslinger, "enchantments" under an enchantress: every
#: fourth or eighth card); the plan-consistency line counts
#: the specific needs and reports the broad ones beside them.
BROAD_SHARE = 0.10

_SHARE_MEMO: dict[tuple, float] = {}


def need_pool_share(need: Need, pool: Sequence[Mapping]) -> float:
    """The share of ``pool`` that supplies ``need`` (memoized per need shape
    and pool size; a predicate need keys on its label)."""
    key = (need.kind, need.label, need.idents, need.keys, need.types, len(pool))
    hit = _SHARE_MEMO.get(key)
    if hit is None:
        hit = sum(1 for c in pool if satisfies(c, need)) / max(1, len(pool))
        _SHARE_MEMO[key] = hit
    return hit


def specific_needs(
    needs: Sequence[Need], pool: Sequence[Mapping], *, floor: float = BROAD_SHARE
) -> tuple[Need, ...]:
    """The needs at most ``floor`` of ``pool`` supplies."""
    return tuple(n for n in needs if need_pool_share(n, pool) <= floor)


def needs_met(card: Mapping, needs: Sequence[Need]) -> tuple[Need, ...]:
    """The needs ``card`` supplies, in ``needs`` order."""
    return tuple(n for n in needs if satisfies(card, n))


# ── reading the commander ───────────────────────────────────────────────────


def _walk(node: object, depth: int = 0) -> Iterator[object]:
    """Every ability-wrapper node under ``node`` (the node itself first)."""
    if depth > 40 or not isinstance(node, TypedMirrorNode):
        return
    yield node
    for fname in (
        "effect",
        "sub_ability",
        "execute",
        "mode_abilities",
        "static_abilities",
        "else_ability",
    ):
        child = getattr(node, fname, None)
        if not _present(child):
            continue
        if isinstance(child, list):
            for m in child:
                yield from _walk(m, depth + 1)
        else:
            yield from _walk(child, depth + 1)


def _conditions(node: object) -> Iterator[object]:
    """Every condition leaf under a unit: its ``condition`` fields and the
    conditions its "activate only if" restrictions carry (Stella Lee's "if
    you've cast three or more spells this turn", CR 602.5)."""
    for site in iter_condition_sites(node):
        cond = site
        if tag_of(site) == "RequiresCondition":
            cond = requires_condition_inner(site)
        if _present(cond) and tag_of(cond) is not None:
            yield from _condition_leaves(cond, 0)


#: The mana value from which a spell is "big" for a commander whose effect
#: scales with the greatest mana value among the spells cast this turn (Rootha's
#: X/X flier with haste: a five-mana spell makes a top-end body). The read's own
#: line, not a rule's.
BIG_SPELL_MV = 5
#: The mana value up to which a spell is "cheap" for a commander counting
#: spells per turn (the ``second_spell_matters`` payoff's line).
CHEAP_SPELL_MV = 2


def _mana_value_reaches(card: Mapping, floor: int) -> bool:
    """Whether the card's spell can have mana value ``floor`` or more: its
    printed mana value (CR 202.3), or an {X} in its cost, since X is the number
    chosen while the spell is on the stack (CR 202.3e)."""
    if float(card.get("cmc") or 0) >= floor:
        return True
    return any(
        "X" in (face.get("mana_cost") or "")
        for face in card.get("card_faces") or [card]
    )


def _cheap_spell(card: Mapping) -> bool:
    return float(card.get("cmc") or 0) <= CHEAP_SPELL_MV and bool(
        _type_words(card) & {"instant", "sorcery"}
    )


def _filter_colorless(filt: object) -> bool:
    """Whether the filter admits colorless objects only (a ``ColorCount``
    equal to zero — Zhulodok; CR 105.2c)."""
    for n in iter_typed_nodes(filt):
        if (
            tag_of(n) == "ColorCount"
            and getattr(n, "comparator", None) == "EQ"
            and int(getattr(n, "count", -1) or 0) == 0
        ):
            return True
    return False


def _spell_floor_need(filt: object, floor: int, desc: str) -> Need | None:
    """The need for spells the filter admits at mana value ``floor`` or more:
    the filter's types and colour, the floor from its ``Cmc`` bound or the
    caller's line."""
    if floor <= 0:
        return None

    def arm_words(arm: object) -> tuple[frozenset[str], frozenset[str]]:
        """The type words an arm asks for and the ones it negates (Bello's
        "non-Equipment artifact" → {artifact}, {equipment})."""
        core = filter_core_types(arm) if _present(arm) else ()
        subs = filter_subtypes(arm) if _present(arm) else ()
        non = filter_non_types(arm) if _present(arm) else ()
        return (
            frozenset(
                w.lower() for w in (*core, *subs) if w.lower() not in ("card", "spell")
            ),
            frozenset(w.lower() for w in non),
        )

    # An ``Or`` filter admits a card of any arm's types ("instant or sorcery
    # spells": either); an arm naming no type admits every spell.
    arms = tuple(arm_words(arm) for arm in or_arms(filt)) if _present(filt) else ()
    arms = () if any(not a for a, _non in arms) else arms
    words = frozenset().union(*(a for a, _non in arms)) if arms else frozenset()
    colorless = _filter_colorless(filt)

    def holds(c: dict) -> bool:
        tw = _type_words(c)
        if "land" in tw:
            return False
        if arms and not any(a <= tw and not (non & tw) for a, non in arms):
            return False
        if colorless and c.get("colors"):
            return False
        return _mana_value_reaches(c, floor)

    kinds = (" or ".join(sorted(words)) + " ") if words else ""
    label = f"{'colorless ' if colorless else ''}{kinds}spells at {floor}+ mana"
    return Need("payoff", label, desc, predicate=holds)


def _spells_cast_filter(qty: object) -> object | None:
    """The spell filter of a ``SpellsCastThisTurn`` quantity or a ``TurnJournal``
    of ``SpellsCast`` (``None`` when it counts every spell)."""
    tag = tag_of(qty)
    if tag == "SpellsCastThisTurn":
        filt = getattr(qty, "filter", None)
        return filt if _present(filt) else None
    if tag == "TurnJournal" and tag_of(getattr(qty, "journal", None)) == "SpellsCast":
        filt = getattr(qty, "filter", None)
        return filt if _present(filt) else None
    return None


def _effect_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """Needs read off a unit's EFFECTS, whatever its origin: an effect scaled by
    the greatest mana value among the turn's spells (Rootha), and a draw given
    to an opponent (Ms. Bumbleflower)."""
    for n in iter_typed_nodes(unit_node):
        tag = tag_of(n)
        if (
            tag == "PropertyAggregate"
            and getattr(n, "function", None) == "Max"
            and getattr(n, "property", None) == "ManaValue"
        ):
            source = getattr(n, "source", None)
            if (
                tag_of(source) == "TurnJournal"
                and tag_of(getattr(source, "journal", None)) == "SpellsCast"
            ):
                need = _spell_floor_need(
                    _spells_cast_filter(source), BIG_SPELL_MV, desc
                )
                if need is not None:
                    yield need
        elif tag == "Draw" and effect_player_reach(unit_node, n) in (
            "target",
            "opponents",
            "per_opponent",
            "each",
        ):
            yield Need(
                "payoff",
                "opponents drawing payoffs",
                desc,
                keys=frozenset({"opponent_draw_matters"}),
            )
            yield Need(
                "redundancy",
                "opponents draw like the commander",
                desc,
                idents=frozenset({"target_player_draws|any|", "group_hug_draw|each|"}),
            )


def _static_needs(node: object, desc: str) -> Iterator[Need]:
    """Needs read off a static ability's ``affected`` filter: your spells or
    permanents at a mana-value floor (Zhulodok's colorless spells with mana
    value 7 or greater)."""
    aff = getattr(node, "affected", None)
    if not _present(aff) or filter_controller(aff) != "You":
        return
    floor = filter_mana_value_floor(aff)
    if floor is not None:
        need = _spell_floor_need(aff, floor, desc)
        if need is not None:
            yield need


def _condition_leaves(cond: object, depth: int) -> Iterator[object]:
    if depth > 20 or not isinstance(cond, TypedMirrorNode):
        return
    yield cond
    for fname in ("inner", "condition", "conditions"):
        child = getattr(cond, fname, None)
        if not _present(child):
            continue
        if isinstance(child, list):
            for c in child:
                yield from _condition_leaves(c, depth + 1)
        else:
            yield from _condition_leaves(child, depth + 1)


def _has_pred(filt: object, name: str) -> bool:
    return name in filter_predicates(filt)


def _type_need(
    core: Iterable[str], subs: Iterable[str]
) -> tuple[frozenset[frozenset[str]], frozenset[str]]:
    """The type-line tests and token-maker keys for a filter's types."""
    words = {c.lower() for c in core if c.lower() != "card"}
    words |= {s.lower() for s in subs}
    if not words:
        return frozenset(), frozenset()
    keys: set[str] = set()
    for w in words:
        keys |= _TYPE_TOKEN_KEYS.get(w, frozenset())
    return frozenset({frozenset(words)}), frozenset(keys)


def _event_need(node: TypedMirrorNode, desc: str) -> Need | None:
    event = trigger_def_event(node)
    scope = trigger_scope(node)
    valid = getattr(node, "valid_card", None)
    core = filter_core_types(valid) if _present(valid) else ()
    subs = filter_subtypes(valid) if _present(valid) else ()
    preds = filter_predicates(valid) if _present(valid) else ()
    label = f"{event} makers"
    if event in ("surveil", "scry"):
        return Need(
            "event",
            f"{event} outlets",
            desc,
            idents=frozenset({f"topdeck_selection|you|{event}"}),
        )
    if event == "enters":
        types, keys = _type_need(core, subs)
        if "Token" in preds:
            keys = keys | _TYPE_TOKEN_KEYS.get("creature", frozenset())
            types = frozenset()
        if types or keys:
            return Need(
                "event",
                f"{' '.join(sorted(core + subs)) or 'permanent'} enters",
                desc,
                keys=keys,
                types=types,
            )
        return None
    if event == "cast_spell":
        floor = filter_mana_value_floor(valid) if _present(valid) else None
        if floor is not None:
            return _spell_floor_need(valid, floor, desc)
        types, _keys = _type_need(core, subs)
        return (
            Need("event", f"cast {' '.join(sorted(core + subs))}", desc, types=types)
            if types
            else None
        )
    if event == "changes_zone":
        origin = getattr(node, "origin", None)
        dest = getattr(node, "destination", None)
        if origin == "Graveyard":
            return Need(
                "event",
                "cards leaving your graveyard",
                desc,
                keys=_GRAVEYARD_LEAVE_KEYS,
            )
        if dest == "Graveyard":
            # "put into your graveyard from anywhere" (CR 603.6c: never a
            # leaves-the-battlefield ability): fed by every way a card reaches
            # the graveyard, and by the way the watched type usually does — a
            # land card by land sacrifice (The Gitrog Monster), a creature card
            # by dying (Sefris of the Hidden Ways).
            keys = set(_GRAVEYARD_FILL_KEYS)
            if "Land" in core or {s.lower() for s in subs} & _LAND_SUBTYPE_WORDS:
                keys.add("land_sacrifice_makers")
            if "Creature" in core:
                keys |= _DEATH_FEED_KEYS
            words = tuple(w for w in core if w not in ("Card", "Permanent")) + subs
            what = " ".join(sorted(words)) or None
            return Need(
                "event",
                f"{what} cards reaching your graveyard"
                if what
                else "cards reaching your graveyard",
                desc,
                keys=frozenset(keys),
            )
        return None
    if event == "attacks":
        # "creatures enchanted by an Aura you control attack" (Killian): the
        # attachment is the need; a bare attack trigger is fed by every creature.
        if "HasAttachment" in preds or "EnchantedBy" in preds:
            # "enchanted by an Aura you control" names Auras alone (CR 303.4a:
            # an Aura enchants; Equipment is attached, CR 301.5); a bare
            # attachment filter admits both.
            aura_only = "aura" in desc.lower()
            words = {"aura"} if aura_only else {"aura", "equipment"}
            return Need(
                "event",
                "attachments",
                desc,
                types=frozenset({frozenset({w}) for w in words}),
                keys=frozenset() if aura_only else frozenset({"voltron_makers"}),
            )
        return None
    if event in ("dies", "leaves", "sacrificed", "exploited"):
        keys = set(_EVENT_MAKER_KEYS[event])
        if "Token" in preds:
            keys = set(_TYPE_TOKEN_KEYS["creature"]) | {"sacrifice_outlets"}
        return Need(
            "event",
            f"creatures that {event.replace('_', ' ')}",
            desc,
            keys=frozenset(keys),
        )
    if event == "deals_damage":
        return Need(
            "event",
            "evasion for your attackers",
            desc,
            keys=_EVASION_KEYS,
            idents=frozenset({f"keyword_bodies|you|{k}" for k in _EVASION_KEYWORDS}),
        )
    keys = _EVENT_MAKER_KEYS.get(event)
    if not keys:
        return None
    if event == "life_lost" and scope == "you":
        return None  # a self-life-loss watcher is fed by its own costs; not a need
    return Need("event", label, desc, keys=keys)


def _cheap_spells_need(desc: str) -> Need:
    return Need("payoff", "cheap spells", desc, predicate=_cheap_spell)


def _condition_need(
    cond: object, desc: str, *, cast_trigger: bool = False
) -> Need | None:
    tag = tag_of(cond)
    if tag == "AbilityUseCountThisTurn" and cast_trigger:
        # "If this is the second time this ability has resolved this turn" on
        # a cast trigger (Ms. Bumbleflower): two spells a turn.
        if int(getattr(cond, "n", 0) or 0) >= 2:
            return _cheap_spells_need(desc)
        return None
    if tag != "QuantityComparison":
        return None
    lhs = getattr(cond, "lhs", None)
    qty = getattr(lhs, "qty", None) if _present(lhs) else None
    if qty is None:
        return None
    qtag = tag_of(qty)
    if qtag == "SpellsCastThisTurn":
        rhs = getattr(cond, "rhs", None)
        n = int(getattr(rhs, "value", 0) or 0) if tag_of(rhs) == "Fixed" else 0
        if n >= 2:
            return _cheap_spells_need(desc)
        filt = _spells_cast_filter(qty)
        core = filter_core_types(filt) if filt is not None else ()
        subs = filter_subtypes(filt) if filt is not None else ()
        types, _keys = _type_need(core, subs)
        return (
            Need("event", f"cast {' '.join(sorted(core + subs))}", desc, types=types)
            if types
            else None
        )
    if qtag == "DistinctCardTypes":
        # Raised by a card that is two types at once, or by a self-mill /
        # surveil that puts several cards (and so several types) in at once.
        return Need(
            "condition",
            "card types in your graveyard",
            desc,
            keys=frozenset({"mill_makers"}),
            idents=frozenset({"topdeck_selection|you|surveil"}),
            predicate=lambda c: card_type_count(c) >= 2,
        )
    if qtag == "ZoneCardCount":
        zone = getattr(qty, "zone", None)
        if zone == "Graveyard":
            return Need(
                "condition", "cards in your graveyard", desc, keys=_GRAVEYARD_FILL_KEYS
            )
        if zone == "Hand":
            return Need(
                "condition",
                "cards in hand",
                desc,
                keys=frozenset({"card_draw_engine", "big_hand_makers"}),
            )
        return None
    if qtag == "ObjectCount":
        filt = getattr(qty, "filter", None)
        core = filter_core_types(filt) if _present(filt) else ()
        subs = filter_subtypes(filt) if _present(filt) else ()
        types, keys = _type_need(core, subs)
        if types or keys:
            return Need(
                "condition",
                f"{' '.join(sorted(core + subs))} you control",
                desc,
                types=types,
                keys=keys,
            )
        preds = filter_predicates(filt) if _present(filt) else ()
        if "Token" in preds:
            return Need(
                "condition",
                "tokens you control",
                desc,
                keys=_TYPE_TOKEN_KEYS["creature"],
            )
    if qtag in ("Devotion", "DevotionCount"):
        return None
    return None


def _resource_needs(idents: Iterable[str], desc: str) -> Iterator[Need]:
    """What the commander produces → the payoffs that consume it."""
    from mtg_utils._tuner.metrics import _cares_keys

    seen: set[str] = set()
    idents = tuple(idents)
    # A commander that grows itself (Mirko's "+1/+1 counter on ~") makes no
    # counters the deck's counter payoffs could use.
    self_grow = any(i.startswith("self_counter_grow|") for i in idents)
    # Every kind of creature token the commander makes feeds that kind's
    # payoffs (Clavileño's Vampires AND Demons): one consumers need over all
    # of them, whatever order the idents came in.
    token_kinds = frozenset(
        ident.split("|", 2)[2]
        for ident in idents
        if ident.startswith(f"{TOKEN_MAKER}|") and ident.split("|", 2)[2]
    )
    for ident in idents:
        key = ident.split("|", 1)[0]
        if key == "plus_one_makers" and self_grow:
            continue
        if _self_life_payment(ident):
            continue
        if key in _UMBRELLA_KEYS:
            continue  # the umbrella's consumers are the umbrella
        if key == TOKEN_MAKER or key.endswith("_makers"):
            consumers = {k for k in _cares_keys(key) if k != key}
            consumers -= _UMBRELLA_KEYS
            if key == TOKEN_MAKER:
                consumers |= {"sacrifice_outlets", "death_matters"}
            if not consumers or key in seen:
                continue
            seen.add(key)
            idents_ = (
                frozenset(f"type_matters|you|{kind}" for kind in token_kinds)
                if key == TOKEN_MAKER
                else frozenset()
            )
            yield Need(
                "resource",
                f"{key.replace('_makers', '').replace('_', ' ')} consumers",
                desc,
                keys=frozenset(consumers),
                idents=idents_,
            )


def _self_life_payment(ident: str) -> bool:
    """A ``lifeloss_makers`` ident scoped to the commander's own controller
    (Hazel's "pay 2 life"): a cost the commander pays, not life loss the
    deck's drain payoffs consume or a drain to make more of — the same call
    :func:`_event_need` makes for a self-life-loss watcher."""
    return ident.startswith("lifeloss_makers|you|")


def _doer_name(key: str) -> str:
    return key.replace("_makers", "").replace("_", " ")


def _redundancy_needs(idents: Iterable[str], desc: str) -> Iterator[Need]:
    """Cards that do what the commander itself does (its doer idents): the
    frameworks' "redundancy of the commander's key effect" (goad under Nelly,
    mill under Winter, Warrior tokens under Zurgo). The specificity floor
    keeps a generic doer (an attack trigger) from becoming a need."""
    for ident in idents:
        key, _scope, subject = ident.split("|", 2)
        if key in _UMBRELLA_KEYS or _self_life_payment(ident):
            continue
        if key == TOKEN_MAKER or key.endswith("_makers"):
            yield Need(
                "redundancy",
                f"{_doer_name(key)}{(' ' + subject) if subject else ''} "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )


def _payoff_needs(idents: Iterable[str], desc: str) -> Iterator[Need]:
    """A commander payoff with no trigger of its own → what feeds it."""
    for ident in idents:
        key, _scope, subject = ident.split("|", 2)
        if key == "type_matters":
            # A tribe the commander pays off is the tribal avenue's page already
            # (its members, plus changelings); a need page of it would add the
            # same cards twice over.
            continue
        if key in _TYPE_PAYOFF_KEYS:
            words = _TYPE_PAYOFF_KEYS[key]
            types = frozenset({frozenset({w}) for w in words})
            keys: set[str] = set()
            for w in words:
                keys |= _TYPE_TOKEN_KEYS.get(w, frozenset())
            yield Need(
                "payoff",
                f"{key.replace('_', ' ')}",
                desc,
                types=types,
                keys=frozenset(keys),
            )
        elif key == "keyword_tribe" and subject:
            kw = subject.lower()
            yield Need(
                "payoff",
                f"{kw} bodies",
                desc,
                idents=frozenset({f"keyword_bodies|you|{kw}"}),
            )
        elif key == "animate_makers" and ">=" in subject:
            word, _sep, floor = subject.partition(">=")
            w, n = word.lower(), int(floor or 0)
            yield Need(
                "payoff",
                f"noncreature {w} at {n}+ mana",
                desc,
                predicate=lambda c, w=w, n=n: (
                    w in _type_words(c)
                    and "creature" not in _type_words(c)
                    and float(c.get("cmc") or 0) >= n
                ),
            )
        elif key == "colorless_matters":
            yield Need(
                "payoff",
                "colorless spells",
                desc,
                predicate=lambda c: (
                    not c.get("colors") and "land" not in _type_words(c)
                ),
            )
        elif key == "toughness_combat":
            yield Need(
                "payoff",
                "toughness over power",
                desc,
                predicate=lambda c: (
                    _stat(c, "toughness") - _stat(c, "power") >= 2
                    and "creature" in _type_words(c)
                ),
            )
        elif key == "energy_matters":
            yield Need(
                "payoff", "energy makers", desc, keys=frozenset({"energy_makers"})
            )
        elif key == "spellcast_matters":
            yield Need(
                "payoff",
                "instants and sorceries",
                desc,
                types=frozenset({frozenset({"instant"}), frozenset({"sorcery"})}),
            )
        elif key == "second_spell_matters":
            yield _cheap_spells_need(desc)
        elif key.startswith("wants_"):
            base = key[len("wants_") :]
            makers = (
                {TOKEN_MAKER, "mass_token_makers"}
                if base == "fodder"
                else {f"{base}_makers"}
            )
            makers &= _served_keys()
            if makers:
                yield Need("payoff", f"{base} makers", desc, keys=frozenset(makers))
        elif key == "tokens_matter":
            # A token payoff (Hazel's "tap X untapped tokens", "copy target
            # token you control") is fed by token makers of any kind — the
            # ``wants_fodder`` keys, since no ``tokens_makers`` key is served.
            yield Need(
                "payoff",
                "token makers",
                desc,
                keys=frozenset({TOKEN_MAKER, "mass_token_makers"}),
            )
        elif key.endswith("_matters"):
            base = key[: -len("_matters")]
            maker = f"{base}_makers"
            if maker in _served_keys() and maker not in _UMBRELLA_KEYS:
                yield Need("payoff", f"{base} makers", desc, keys=frozenset({maker}))


def _served_keys() -> frozenset[str]:
    from mtg_utils._analysis.lanes import SERVED_SIGNAL_KEYS

    return frozenset(SERVED_SIGNAL_KEYS)


def _stat(card: Mapping, name: str) -> int:
    faces = card.get("card_faces") or [card]
    best = 0
    for face in faces:
        raw = face.get(name)
        try:
            best = max(best, int(str(raw).replace("*", "0") or 0))
        except ValueError:
            continue
    return best


def commander_needs(commanders: Sequence[Mapping]) -> tuple[Need, ...]:
    """Every need the commander(s) express, deduplicated, in reading order:
    triggers' events, conditions, then the resource and payoff reads off the
    commanders' idents."""
    out: list[Need] = []
    seen: set[tuple] = set()

    def add(need: Need | None) -> None:
        if need is None or need.empty:
            return
        # A predicate need is one per label (the same "cheap spells" from a
        # second-spell trigger and an "activate only if" count).
        key = (
            (need.kind, need.idents, need.keys, need.types)
            if need.predicate is None
            else ("predicate", need.label)
        )
        if key in seen:
            return
        seen.add(key)
        out.append(need)

    for rec in commanders:
        # Without the membership floor: a commander's own creature types and
        # card types are what it IS, not what it asks for. Sorted: the needs
        # come out in one order whatever the process's hash seed.
        idents = sorted(_card_idents(rec, membership=False))
        for tree in trees_for(dict(rec)):
            for unit in tree.units:
                node = unit.node
                desc = str(getattr(node, "description", "") or "")
                cast_trigger = False
                if unit.origin == "trigger" and isinstance(node, TypedMirrorNode):
                    add(_event_need(node, desc))
                    cast_trigger = trigger_def_event(node) == "cast_spell"
                if unit.origin == "static":
                    for need in _static_needs(node, desc):
                        add(need)
                for cond in _conditions(node):
                    add(_condition_need(cond, desc, cast_trigger=cast_trigger))
                for need in _effect_needs(node, desc):
                    add(need)
        for need in _resource_needs(idents, rec.get("name", "")):
            add(need)
        for need in _redundancy_needs(idents, rec.get("name", "")):
            add(need)
        for need in _payoff_needs(idents, rec.get("name", "")):
            add(need)
    return tuple(out)


def need_serve(need: Need) -> Serve:
    """The ``Serve`` that pages ``need`` (``signal_specs.Serve``'s predicate arm):
    the cards that supply it, for the tune's need pages."""
    from mtg_utils._analysis.signal_specs import Serve

    return Serve(
        predicate=lambda card: satisfies(card, need),
        predicate_id=f"need:{need.kind}:{need.label}",
    )
