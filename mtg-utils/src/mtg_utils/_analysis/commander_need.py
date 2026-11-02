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

import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._analysis._subtypes import LAND_SUBTYPES
from mtg_utils._analysis.card_reads import plays_extra_lands
from mtg_utils._analysis.multipliers import Commander, multiplier_reasons
from mtg_utils._analysis.signal_keys import TOKEN_MAKER
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    counter_kind,
    effect_player_reach,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_mana_value_floor,
    filter_non_types,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    iter_condition_sites,
    iter_typed_nodes,
    or_arms,
    requires_condition_inner,
    tag_of,
    trigger_def_event,
    trigger_scope,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.type_line import split_type_line

if TYPE_CHECKING:
    from mtg_utils._analysis.signal_specs import Serve
    from mtg_utils._card_ir.crosswalk import ConceptTree

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
#: Keys whose emitters put cards INTO your graveyard from outside the battlefield
#: (what a "put into your graveyard from anywhere" trigger is fed by). The
#: umbrella ``graveyard_makers`` is left out (:data:`_UMBRELLA_KEYS`): with it the
#: need is 12% of the pool and never specific; the fill is mill and discard.
_GRAVEYARD_FILL_KEYS: frozenset[str] = frozenset(
    {"mill_makers", "discard_makers", "discard_outlet"}
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
#: Keys whose emitters grow or keep the counters already on your creatures, the
#: commander's own among them: proliferate, a counter doubler or bonus, a counter
#: mover, and the payoffs that read a creature's counters. What a commander whose
#: text counts the counters on itself (Zimone, Infinite Analyst's "costs {1} less
#: for each +1/+1 counter on ~") asks the deck for; the makers that put a counter
#: on a creature are left out (a sixth of a green pool).
_COUNTER_GROWTH_KEYS: frozenset[str] = frozenset(
    {
        "proliferate_makers",
        "counter_doubling",
        "counter_replace_bonus",
        "counter_move",
        "plus_one_matters",
    }
)
#: A doer key → the consumers ``metrics._cares_keys`` doesn't name, and the
#: idents among them:
#:
#: * ``plus_one_makers``: the payoffs that read your creatures' counters (a
#:   keyword for each creature with a counter — Chocobo Knights, Bramblewood
#:   Paragon; CR 122.1) and the movers that keep the counters a creature had
#:   when it leaves (The Ozolith, Resourceful Defense; CR 122.8).
#: * ``token_copy_makers``: the token payoffs, since "create a token that's a
#:   copy" puts a token onto the battlefield (CR 111.1 — Satya's attacker):
#:   Junk Winder's "Whenever a token you control enters", Ojer Taq's tripling.
#: * ``land_sacrifice_makers``: the cards that return lands from your graveyard,
#:   where a sacrificed land goes (CR 701.21a) — Life from the Loam, Crucible of
#:   Worlds, Ramunap Excavator (``permanent_recast|you|land``).
#: * ``land_sacrifice_makers`` also wants the extra land drops that replay the
#:   sacrificed lands and keep the drops coming — a land put from the hand
#:   (``extra_land_drop``: Burgeoning) or an additional land play
#:   (``card_reads.plays_extra_lands``: Exploration, Azusa, Oracle of Mul Daya,
#:   which the landfall lane folds into its umbrella key). The first adds Desert
#:   Bloom's guides make, while the tuner trimmed Oracle of Mul Daya as surplus
#:   ramp (2026-11-01).
#: * ``plus_one_makers`` also: the doublers, the replacement bonuses and the
#:   proliferators, which multiply the counters the commander places (a
#:   proliferate adds a counter of a kind already there, CR 701.34a) — the
#:   adds every +1/+1 counters guide makes (Doubling Season, Hardened Scales,
#:   Evolution Sage), which Bright-Palm's consumers need left out while its
#:   two-need obscurities led his page (Call for Backup, 2026-11-02).
_EXTRA_CONSUMER_KEYS: Mapping[str, frozenset[str]] = {
    "plus_one_makers": frozenset(
        {
            "counter_grants_kw",
            "counter_move",
            "counter_doubling",
            "counter_replace_bonus",
            "proliferate_makers",
        }
    ),
    "token_copy_makers": frozenset({"tokens_matter", "token_doubling"}),
    "land_sacrifice_makers": frozenset({"extra_land_drop"}),
}
_EXTRA_CONSUMER_IDENTS: Mapping[str, frozenset[str]] = {
    "land_sacrifice_makers": frozenset({"permanent_recast|you|land"}),
}
_EXTRA_CONSUMER_PREDICATES: Mapping[str, Callable[[dict], bool]] = {
    "land_sacrifice_makers": plays_extra_lands,
}

#: Payoff keys with no maker lane behind them: the payoff is the doing, so a
#: commander carrying one asks for cards with the same key
#: (``_redundancy_needs``).
_PAYOFF_REDUNDANCY_KEYS: frozenset[str] = frozenset({"graveyard_leave_matters"})

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
    #: The mana value the need's spells start at, when it asks for big ones
    #: (Zhulodok's colorless spells at 7+, Bello's artifacts at 4+): a plan
    #: whose top end is the point, which the tuner reads before trimming ramp.
    mana_floor: int | None = None
    #: Whether the need may lead a theme page's order and gate an upgrade
    #: (``swaps.propose_swaps``' ``built_needs``). A need that is a property of
    #: the card, not a role in the plan — "cheap spells", "instants and
    #: sorceries" — is counted on the scoreboard but leads no page: under Ms.
    #: Bumbleflower it put Forget and Martyr's Cry over the group-hug payoffs
    #: (2026-11-01).
    leads: bool = True

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

#: The toughness a body needs to supply a toughness-reading commander: four,
#: where the walls Felothar's guides add sit (Wall of Souls, Giant Ox, Flumph
#: 0/4; Shield Sphere 0/6) and every Dinosaur Pantlaza's guides add clears.
#: This read's own line, no rule's.
HIGH_TOUGHNESS = 4

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


def is_broad(need: Need, share: float, *, floor: float = BROAD_SHARE) -> bool:
    """Whether a need ``share`` of the pool supplies is broad (over ``floor``).
    A need with a mana-value floor never is: it is read off the commander's own
    filter — the types it names at the mana value it names — so its page is the
    plan's top end, however many such cards the pool holds (Bello's artifacts
    and enchantments at 4+ mana are 10.5% of a Gruul pool, and over the line
    his page never led, gated or trimmed by his need; Animated Army,
    2026-11-01). The line is for the umbrella needs: every enchantment under
    an enchantress, every instant under a spellslinger."""
    return need.mana_floor is None and share > floor


def specific_needs(
    needs: Sequence[Need], pool: Sequence[Mapping], *, floor: float = BROAD_SHARE
) -> tuple[Need, ...]:
    """The needs that are not :func:`is_broad` over ``pool``."""
    return tuple(
        n for n in needs if not is_broad(n, need_pool_share(n, pool), floor=floor)
    )


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
    return Need("payoff", label, desc, predicate=holds, mana_floor=int(floor))


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


#: The line a sacrificed creature's power must reach, at most what mana value,
#: for a commander whose effect scales with that power (Dina, Essence Brewer's
#: "where X is the sacrificed creature's power"): a body that pays it off well
#: for what it costs. The read's own line, not a rule's.
FODDER_POWER = 5
FODDER_MV = 4


def _sacrifices_a_creature(unit_node: object) -> bool:
    """Whether the unit's own cost sacrifices a creature ("{2}, {T}, Sacrifice
    another creature:" — Dina, Essence Brewer)."""
    cost = getattr(unit_node, "cost", None)
    return _present(cost) and any(
        tag_of(n) == "Sacrifice"
        and "Creature" in filter_core_types(getattr(n, "target", None))
        for n in iter_typed_nodes(cost)
    )


def _sacrificed_power_need(desc: str) -> Need:
    """A commander effect scaled by the power of the creature its cost
    sacrifices — phase's ``Power`` of ``CostPaidObject``, the sacrificed creature
    as it last existed on the battlefield (Dina's ruling): the need is cheap
    bodies with a high printed power (CR 208.1)."""
    return Need(
        "payoff",
        f"sacrifice fodder with power {FODDER_POWER}+ "
        f"at mana value {FODDER_MV} or less",
        desc,
        predicate=lambda c: (
            "creature" in _type_words(c)
            and _stat(c, "power") >= FODDER_POWER
            and float(c.get("cmc") or 0) <= FODDER_MV
        ),
    )


#: The mana value a permanent card reaches to be a target worth a commander's
#: graveyard-to-battlefield effect: the top end a deck cheats in rather than
#: casts — Death Toll's guides add Overlord of the Balemurk (7) and Hoarding
#: Broodlord (8) and keep Hornet Queen (7), and the deck's own Vile Mutilator,
#: Giant Adephage and Moldgraf Monstrosity sit there. At six the need is a tenth
#: of a two-colour pool (broad, :data:`BROAD_SHARE`), at seven a twenty-fifth.
#: This read's own line, no rule's.
REANIMATION_MV = 7

#: The card types a card has once it is on the battlefield (the permanent types
#: among :data:`CARD_TYPES`).
_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"artifact", "battle", "creature", "enchantment", "planeswalker"}
)


def _sizes_the_card(node: object) -> bool:
    """Whether the node bounds the card's own size — its mana value, power or
    toughness, as a filter property (Alesha's "power 2 or less") or a quantity
    checked of the target (Meren's "mana value is less than or equal to the
    number of experience counters": ``ObjectManaValue`` of ``Target``): the
    commander states its own line, which the payload read leaves to it."""
    return any(tag_of(n) in _SIZE_TAGS for n in iter_typed_nodes(node))


#: A size bound in a unit's description: "with power less than", "mana value 3
#: or less".
_DESC_SIZE_BOUND = re.compile(
    r"\bwith (?:power|toughness|mana value) (?:less|greater) than\b"
    r"|\b(?:power|toughness|mana value) \d+ or (?:less|greater)\b",
    re.IGNORECASE,
)


def _desc_sizes_the_card(desc: str) -> bool:
    """Whether the unit's phase description states a size bound on the card.

    The one text read in this module, a phase gap: v0.118.0 silently drops
    Mirko, Obsessive Theorist's "with power less than Mirko's" (the target
    filter keeps only InZone Graveyard, Owned You and Creature, no residue
    node), so :func:`_sizes_the_card` sees no bound. Retired when
    ``test_mirko_size_bound_canary`` fails."""
    return bool(_DESC_SIZE_BOUND.search(desc))


#: The typed tags that read a card's size: the filter properties and the
#: object quantities.
_SIZE_TAGS: frozenset[str] = frozenset(
    {"Cmc", "Power", "Toughness", "ObjectManaValue", "ObjectPower", "ObjectToughness"}
)


def _graveyard_return_filters(unit_node: object) -> Iterator[object]:
    """The filter of each card the unit puts from a graveyard onto the
    battlefield: a ``ChangeZone`` to the battlefield whose target sits in a
    graveyard (``InZone: Graveyard``) or whose origin is one, or whose
    ``ParentTarget`` is a card an earlier effect of the unit took from one
    (Winter's exile-then-return)."""
    nodes = list(iter_typed_nodes(unit_node))
    from_graveyard = [
        target
        for n in nodes
        for target in (getattr(n, "target", None),)
        if _present(target) and "Graveyard" in filter_inzone_zones(target)
    ]
    for n in nodes:
        if tag_of(n) != "ChangeZone" or getattr(n, "destination", None) != (
            "Battlefield"
        ):
            continue
        target = getattr(n, "target", None)
        if _present(target) and (
            "Graveyard" in filter_inzone_zones(target)
            or getattr(n, "origin", None) == "Graveyard"
        ):
            yield target
        elif tag_of(target) == "ParentTarget" and from_graveyard:
            yield from_graveyard[0]


def _reanimation_target_need(filt: object, desc: str) -> Need | None:
    """What a commander's graveyard-to-battlefield effect is FOR: a permanent
    card of the filter's types at :data:`REANIMATION_MV` or more, the payload
    the deck fills its graveyard to return. A land is no payload (Teval's
    "return a land card": the lands reads' own), nor a card of a creature type
    (the tribe's page); another player's graveyard is not the deck's. The
    caller skips a unit that sizes the card itself (:func:`_sizes_the_card`:
    Meren, Alesha)."""
    if filter_controller(filt) not in (None, "You"):
        return None
    core = {w.lower() for w in filter_core_types(filt)} - {"card", "permanent"}
    subs = {w.lower() for w in filter_subtypes(filt)}
    if "land" in core or subs:
        # A land is no payload; a return filtered to a creature type is the
        # tribe's — its members are the payload whatever they cost (Sidar
        # Jabari's Knights; Admiral Brass's Pirates, which come back as 4/4s),
        # and the tribal page holds them.
        return None
    non = frozenset(w.lower() for w in filter_non_types(filt))
    words = frozenset(core)

    def holds(c: dict) -> bool:
        tw = _type_words(c)
        if not tw & _PERMANENT_TYPES or "land" in tw:
            return False
        if words and not words <= tw:
            return False
        if non & tw:
            return False
        return float(c.get("cmc") or 0) >= REANIMATION_MV

    what = " ".join(sorted(words)) or "permanent"
    return Need(
        "payoff",
        f"{what} cards worth returning at {REANIMATION_MV}+ mana",
        desc,
        predicate=holds,
    )


def _token_kind_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A token effect that treats one kind of token better — Hazel's "If that
    token is a Squirrel, instead create two": a ``ConditionInstead`` over a
    ``TargetMatchesFilter`` naming the subtype, on an effect whose target is a
    token — asks for makers of THAT kind of token, beyond the token makers of
    any kind her "copy target token" asks for (Squirreled Away's guides add Nut
    Collector, Drey Keeper and Deranged Hermit; the tuner swapped Squirrel Nest
    for Fanatic of Rhonas, 2026-11-01)."""
    nodes = list(iter_typed_nodes(unit_node))
    if not any(
        tag_of(n) == "CopyTokenOf"
        and "Token" in filter_predicates(getattr(n, "target", None))
        for n in nodes
    ):
        return
    for n in nodes:
        if tag_of(n) != "TargetMatchesFilter":
            continue
        for sub in filter_subtypes(getattr(n, "filter", None)):
            yield Need(
                "payoff",
                f"{sub} token makers",
                desc,
                idents=frozenset({f"{TOKEN_MAKER}|you|{sub}"}),
            )


def _effect_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """Needs read off a unit's EFFECTS, whatever its origin: an effect scaled by
    the greatest mana value among the turn's spells (Rootha), a draw given to an
    opponent (Ms. Bumbleflower), an effect scaled by the power of the creature
    its cost sacrifices (Dina), a typed card taken from the graveyard (Anikthea:
    that type put there, :func:`_graveyard_take_needs`), a card put from the
    graveyard onto the battlefield (Winter: the payload,
    :func:`_reanimation_target_need`), and a token effect that favours one kind
    of token (Hazel's Squirrels, :func:`_token_kind_needs`)."""
    yield from _graveyard_take_needs(unit_node, desc)
    if not (_sizes_the_card(unit_node) or _desc_sizes_the_card(desc)):
        for filt in _graveyard_return_filters(unit_node):
            need = _reanimation_target_need(filt, desc)
            if need is not None:
                yield need
                break
    yield from _token_kind_needs(unit_node, desc)
    sacrifices = _sacrifices_a_creature(unit_node)
    for n in iter_typed_nodes(unit_node):
        if (
            sacrifices
            and tag_of(n) == "Power"
            and tag_of(getattr(n, "scope", None)) == "CostPaidObject"
        ):
            yield _sacrificed_power_need(desc)
            sacrifices = False  # one need per unit
            continue
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
    value 7 or greater); and, when the static makes your permanents creatures
    and sends them into combat — an ``AddType`` of Creature beside a granted
    combat-damage trigger or haste (Bello's 4/4 Elementals that draw on
    combat damage) — the support those attackers want
    (:data:`_ATTACKER_SUPPORT_KEYS`): the anthems, the team protection and the
    evasion grants Animated Army's guides add (Asceticism, Glorious Sunrise,
    Sight of the Scalelords, Akroma's Memorial) where play-rate gave
    Panharmonicon and Mystic Forge (2026-11-02)."""
    aff = getattr(node, "affected", None)
    if not _present(aff) or filter_controller(aff) != "You":
        return
    floor = filter_mana_value_floor(aff)
    if floor is not None:
        need = _spell_floor_need(aff, floor, desc)
        if need is not None:
            yield need
    if _animates_attackers(node):
        yield Need(
            "event",
            "support for the attackers the commander makes",
            desc,
            predicate=_supports_attackers,
        )


#: What a deck whose commander turns its permanents into attackers wants for
#: them: team pumps and anthems, team protection, and the evasion grants a
#: "deals combat damage to a player" trigger already asks for.
_ATTACKER_SUPPORT_KEYS: frozenset[str] = frozenset(
    {"team_buff", "anthem_static", "board_protection", "team_evasion_grant"}
)


def _supports_attackers(card: dict) -> bool:
    """A card with one of :data:`_ATTACKER_SUPPORT_KEYS` that is not an
    Equipment: a piece of gear helps one creature at a time (Hammer of Nazahn
    led Bello's page as "support" for its indestructible), where the deck
    animates a board."""
    if "equipment" in _type_words(card):
        return False
    return any(i.split("|", 1)[0] in _ATTACKER_SUPPORT_KEYS for i in _card_idents(card))


def _animates_attackers(node: object) -> bool:
    """Whether a static's ``modifications`` make the affected permanents
    creatures (``AddType`` Creature) and send them into combat: a granted
    trigger on combat damage (``GrantTrigger`` with ``DamageDone``) or haste
    (``AddKeyword``)."""
    mods = getattr(node, "modifications", None) or ()
    becomes_creature = False
    attacks = False
    for mod in mods:
        tag = tag_of(mod)
        if tag == "AddType" and getattr(mod, "core_type", None) == "Creature":
            becomes_creature = True
        elif (
            tag == "AddKeyword" and str(getattr(mod, "keyword", "")).lower() == "haste"
        ):
            attacks = True
        elif tag == "GrantTrigger":
            trig = getattr(mod, "trigger", None)
            if getattr(trig, "mode", None) == "DamageDone":
                attacks = True
    return becomes_creature and attacks


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


def _counter_filter_kind(node: TypedMirrorNode) -> str | None:
    """The counter kind a ``CounterAdded`` trigger watches (its
    ``counter_filter.counter_type``: ``M1M1``, ``P1P1``), ``None`` when it
    watches every kind. A bare ``{counter_type: …}`` strict-loads as a
    ``MirrorVariant`` keyed ``counter_type``."""
    filt = getattr(node, "counter_filter", None)
    if isinstance(filt, MirrorVariant) and filt.key == "counter_type":
        kind = filt.inner
    else:
        kind = getattr(filt, "counter_type", None) if _present(filt) else None
    return kind if isinstance(kind, str) else None


def _graveyard_fill_need(
    core: Sequence[str], subs: Sequence[str], desc: str, *, typed_only: bool = False
) -> Need | None:
    """The need for cards of the filter's types reaching your graveyard: fed by
    every way a card gets there, and by the way the type usually does — a land
    card by land sacrifice (The Gitrog Monster), a creature card by a sacrifice
    outlet or an edict (Sefris of the Hidden Ways). Not by token makers: a
    token is not a card (CR 108.2), so a token dying is no "creature card put
    into your graveyard". ``typed_only``: no need for an untyped card."""
    keys = set(_GRAVEYARD_FILL_KEYS)
    if "Land" in core or {s.lower() for s in subs} & _LAND_SUBTYPE_WORDS:
        keys.add("land_sacrifice_makers")
    if "Creature" in core:
        keys |= {"sacrifice_outlets", "edict_makers"}
    words = tuple(w for w in core if w not in ("Card", "Permanent")) + tuple(subs)
    what = " ".join(sorted(words)) or None
    if what is None and typed_only:
        return None
    label = (
        f"{what} cards reaching your graveyard"
        if what
        else "cards reaching your graveyard"
    )
    return Need("event", label, desc, keys=frozenset(keys))


def _graveyard_take_needs(unit_node: object, desc: str) -> Iterator[Need]:
    """A commander that takes a card of a type from its own graveyard — the
    target of an effect sits there (``InZone: Graveyard``) and is typed:
    Anikthea's "non-Aura enchantment card from your graveyard", Meren's and
    Mirko's creature card, Teval's land card — wants that type put there
    (:func:`_graveyard_fill_need`): Enduring Enchantments' guides add the
    discard outlets and self-mill that drop enchantments, where the tuner paged
    every popular enchantment (2026-11-01). An untyped card (Winter's "any
    number of cards") asks nothing the condition read does not."""
    seen: set[str] = set()
    for n in iter_typed_nodes(unit_node):
        filt = getattr(n, "target", None)
        if not _present(filt) or "Graveyard" not in filter_inzone_zones(filt):
            continue
        if filter_controller(filt) not in (None, "You"):
            continue
        if filter_owned_controller(filt) not in (None, "You"):
            continue
        need = _graveyard_fill_need(
            filter_core_types(filt), filter_subtypes(filt), desc, typed_only=True
        )
        if need is not None and need.label not in seen:
            seen.add(need.label)
            yield need


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
            # leaves-the-battlefield ability).
            return _graveyard_fill_need(core, subs, desc)
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
        if "Land" in core:
            # "Whenever you sacrifice a land" (Hearthhull, the Worldseed) is fed
            # by land sacrifice, which the commander's own land-sacrifice idents
            # page (``_payoff_needs``, ``_redundancy_needs``); never by creature
            # fodder.
            return None
        keys = set(_EVENT_MAKER_KEYS[event])
        if "Token" in preds:
            keys = set(_TYPE_TOKEN_KEYS["creature"]) | {"sacrifice_outlets"}
        elif "NonToken" in preds:
            # "Whenever you sacrifice a nontoken Elemental" (Ashling, the
            # Limitless): a token is no nontoken creature, so the token makers
            # feed nothing; the outlets and edicts do.
            keys -= _TYPE_TOKEN_KEYS["creature"]
        return Need(
            "event",
            f"creatures that {event.replace('_', ' ')}",
            desc,
            keys=frozenset(keys),
        )
    if event == "counter_added" and _counter_filter_kind(node) == "M1M1":
        # "Whenever one or more -1/-1 counters are put on a creature" (Auntie
        # Ool, Cursewretch): fed by the -1/-1 counter lane's cards, a
        # proliferate, and a mover — moving a counter puts it onto the second
        # object (CR 122.5: The Ozolith's counters onto a target creature). A
        # -X/-X effect (``debuff_makers``: Disfigure) puts no counter.
        return Need(
            "event",
            "-1/-1 counters put on creatures",
            desc,
            keys=frozenset(
                {"minus_counters_matter", "proliferate_makers", "counter_move"}
            ),
        )
    if event == "deals_damage" and tag_of(getattr(node, "valid_source", None)) == (
        "SelfRef"
    ):
        return _own_damage_grant_need(desc)
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
    if event == "life_lost" and trigger_turn_constraint(node) in _OPPONENT_TURN_GATES:
        # "Whenever an opponent loses life for the first time during each of
        # their turns" (Valgavoth, Harrower of Souls): the makers that fire on
        # an OPPONENT'S turn — a trigger watching what opponents do (Rug of
        # Smothering's spells, Razorkin Needlehead's draws, Roiling Vortex's
        # upkeeps) — not your own spells' and artifacts' riders (Guttersnipe,
        # Reckless Fireweaver), which the tuner added where Endless
        # Punishment's guides add the punishers (2026-11-01).
        return Need(
            "event",
            "life loss on opponents' turns",
            desc,
            predicate=_drains_on_opponents_turns,
        )
    return Need("event", label, desc, keys=keys)


#: A trigger's turn gates that fire on opponents' turns (phase's ``constraint``).
_OPPONENT_TURN_GATES = frozenset({"OncePerOpponentPerTurn", "OnlyDuringOpponentsTurn"})


def _drains_on_opponents_turns(card: dict) -> bool:
    """A life-loss or damage maker whose trigger watches what other players do:
    an ``opponent_*`` watcher key, a tax, a payoff lane scoped past "you"
    (``*_matters|opponents|`` / ``|each|`` / ``|any|``), a watcher ident scoped
    to opponents or every player (Blood Seeker's ``creature_etb|opponents|``,
    Stormfist Crusader's ``group_hug_draw|each|``), or on the card's own tree a
    trigger on a player action by opponents or every player
    (:data:`_PLAYER_ACTION_EVENTS` at ``crosswalk.trigger_scope`` past "you":
    Harsh Mentor's "whenever an opponent activates an ability", Kaervek's
    "whenever an opponent casts a spell") or on a permanent an opponent
    controls (Blood Seeker's "enters under an opponent's control"). Not the
    card's own attack or cast (Myr Battlesphere, Crypt Ghast's extort), nor a
    removal spell's "any" scope (Toxic Deluge) — the first widening admitted
    them (2026-11-01)."""
    idents = _card_idents(card)
    keys = {i.split("|", 1)[0] for i in idents}
    if not keys & _EVENT_MAKER_KEYS["life_lost"]:
        return False
    for ident in idents:
        key, scope, _subject = ident.split("|", 2)
        if key.startswith("opponent_") or key == "stax_taxes":
            return True
        if key in _OWN_COMBAT_KEYS:
            continue  # the card's own attack connecting is your turn's work
        if key.endswith("_matters") and scope in ("opponents", "each", "any"):
            return True
        if key not in _EVENT_MAKER_KEYS["life_lost"] and scope in ("opponents", "each"):
            return True
    for tree in trees_for(dict(card)):
        for unit in tree.units:
            if unit.origin != "trigger" or not isinstance(unit.node, TypedMirrorNode):
                continue
            event = trigger_def_event(unit.node)
            if event in _PLAYER_ACTION_EVENTS and trigger_scope(unit.node) in (
                "opponents",
                "each",
            ):
                return True
            valid = getattr(unit.node, "valid_card", None)
            if _present(valid) and filter_controller(valid) == "Opponent":
                return True
    return False


#: Payoff keys for the card's OWN combat damage to opponents (Sword of Fire and
#: Ice, Rankle): scoped "opponents" by the victim, fired on your turn.
_OWN_COMBAT_KEYS: frozenset[str] = frozenset(
    {"combat_damage_matters", "combat_damage_to_opp", "damage_to_opp_matters"}
)

#: The trigger events that are a player's own action (``trigger_def_event``):
#: one by an opponent happens on their turn, as a rule.
_PLAYER_ACTION_EVENTS: frozenset[str] = frozenset(
    {
        "cast_spell",
        "abilityactivated",
        "drawn",
        "discarded",
        "life_gained",
        "surveil",
        "scry",
        "explored",
        "investigated",
        "sacrificed",
        "taps",
        "tapsformana",
        "phase",
    }
)


#: The keywords a "whenever ~ deals combat damage to a player" commander wants
#: put on itself: evasion to connect, and double strike, with which it deals
#: combat damage in both combat damage steps (CR 702.4b) and so triggers twice.
_OWN_DAMAGE_KEYWORDS: frozenset[str] = _EVASION_KEYWORDS | {"double strike"}


def _grants_the_commander(card: dict) -> bool:
    """Whether the card gives your commander one of :data:`_OWN_DAMAGE_KEYWORDS`
    ("Commander creatures you own have 'Whenever this creature attacks a player,
    … this creature can't be blocked this turn'" — Sword Coast Sailor; "… it
    gains double strike" — Flaming Fist)."""
    idents = _card_idents(card)
    if "commander_matters|you|" not in idents:
        return False
    return any(
        f"{prefix}|you|{kw}" in idents
        for kw in _OWN_DAMAGE_KEYWORDS
        for prefix in ("keyword_bodies", "evasion_self")
    )


def _own_damage_grant_need(desc: str) -> Need:
    """A combat-damage trigger of the commander's own ("Whenever Sidar Jabari
    deals combat damage to a player"): only what reaches the commander feeds
    it — a grant to a target or the team of evasion or double strike (Duelist's
    Heritage), a grant to your commander, a lure. Another creature's own flying
    does not."""
    return Need(
        "event",
        "evasion and double strike for the commander",
        desc,
        keys=frozenset({"team_evasion_grant", "lure_makers"}),
        idents=frozenset(
            f"{prefix}|you|{kw}"
            for kw in _OWN_DAMAGE_KEYWORDS
            for prefix in ("keyword_grant_target", "team_buff")
        ),
        predicate=_grants_the_commander,
    )


def _cheap_spells_need(desc: str) -> Need:
    return Need("payoff", "cheap spells", desc, predicate=_cheap_spell, leads=False)


def _cast_power_need(cond: object, desc: str) -> Need | None:
    """A cast trigger's check of the cast spell's power ("If that spell's power
    is 4 or greater, draw a card. If that spell's power is 6 or greater, …" —
    Eshki, Temur's Roar): phase reads the triggering spell as ``CostPaidObject``
    in a ``SpellCast`` trigger (Cabaretti Revels' and Jodah's "lesser mana value"
    the same way). The need is creature cards whose printed power reaches the
    floor (CR 208.1: a creature card's power is printed in its lower right);
    a ``*`` power reads 0."""
    if getattr(cond, "comparator", None) not in ("GE", "GT"):
        return None
    lhs = getattr(cond, "lhs", None)
    qty = getattr(lhs, "qty", None) if _present(lhs) else None
    if tag_of(qty) != "Power" or tag_of(getattr(qty, "scope", None)) != (
        "CostPaidObject"
    ):
        return None
    rhs = getattr(cond, "rhs", None)
    if tag_of(rhs) != "Fixed":
        return None
    floor = int(getattr(rhs, "value", 0) or 0) + (
        1 if getattr(cond, "comparator", None) == "GT" else 0
    )
    if floor <= 0:
        return None
    return Need(
        "payoff",
        f"creature spells with power {floor}+",
        desc,
        predicate=lambda c, floor=floor: (
            "creature" in _type_words(c) and _stat(c, "power") >= floor
        ),
    )


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
    if tag == "QuantityCheck" and cast_trigger:
        return _cast_power_need(cond, desc)
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


def _counter_placement(trees: Sequence[ConceptTree]) -> tuple[bool, bool]:
    """Two facts about the commander's +1/+1 counters: whether any land on
    something other than itself (Captain America, Team Leader's "a +1/+1 counter
    on that Hero and a +1/+1 counter on ~"), and whether its own text counts the
    counters on itself (Zimone, Infinite Analyst's "for each +1/+1 counter on ~":
    a ``CountersOn`` operand scoped to the source)."""
    elsewhere = counts_own = False
    for tree in trees:
        for unit in tree.units:
            for c in unit.effect_concepts("place_counter"):
                node = c.node
                if tag_of(node) not in ("PutCounter", "PutCounterAll"):
                    continue
                if counter_kind(node) != "P1P1":
                    continue
                if tag_of(getattr(node, "target", None)) != "SelfRef":
                    elsewhere = True
            for n in iter_typed_nodes(unit.node):
                if (
                    tag_of(n) == "CountersOn"
                    and tag_of(getattr(n, "scope", None)) == "Source"
                ):
                    counts_own = True
    return elsewhere, counts_own


def _resource_needs(
    idents: Iterable[str], desc: str, *, trees: Sequence[ConceptTree] = ()
) -> Iterator[Need]:
    """What the commander produces → the payoffs that consume it."""
    from mtg_utils._tuner.metrics import _cares_keys

    seen: set[str] = set()
    idents = tuple(idents)
    # A commander that grows ONLY itself (Mirko's "+1/+1 counter on ~") makes no
    # counters the deck's counter payoffs could use; one that also grows others
    # (Captain America's Heroes) does. When its own text counts the counters on
    # itself (Zimone), the deck wants them grown and kept: proliferate, doublers,
    # the counter movers (``_COUNTER_GROWTH_KEYS``) — the upgrade guides' adds
    # for her (Branching Evolution, Evolution Sage, The Ozolith), none of which a
    # Mirko or Valgavoth guide reaches for.
    elsewhere, counts_own = _counter_placement(trees)
    self_grow = (
        any(i.startswith("self_counter_grow|") for i in idents) and not elsewhere
    )
    if self_grow and counts_own:
        yield Need(
            "resource",
            "counters on the commander",
            desc,
            keys=_COUNTER_GROWTH_KEYS,
        )
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
            consumers |= _EXTRA_CONSUMER_KEYS.get(key, frozenset())
            if key == TOKEN_MAKER:
                consumers |= {"sacrifice_outlets", "death_matters"}
            extra_idents = _EXTRA_CONSUMER_IDENTS.get(key, frozenset())
            if not (consumers or extra_idents) or key in seen:
                continue
            seen.add(key)
            idents_ = (
                frozenset(f"type_matters|you|{kind}" for kind in token_kinds)
                if key == TOKEN_MAKER
                else frozenset()
            ) | extra_idents
            yield Need(
                "resource",
                f"{key.replace('_makers', '').replace('_', ' ')} consumers",
                desc,
                keys=frozenset(consumers),
                idents=idents_,
                predicate=_EXTRA_CONSUMER_PREDICATES.get(key),
            )


def _loyalty_need(rec: Mapping) -> Need | None:
    """A planeswalker commander's loyalty is the loyalty counters on it (CR
    306.5c), and a proliferate gives it one more (CR 701.34a): the deck wants
    proliferate (Quintorius, History Chaser — Patrolling Peacemaker)."""
    if "planeswalker" not in _type_words(rec):
        return None
    return Need(
        "resource",
        "loyalty on the commander",
        rec.get("name", ""),
        keys=frozenset({"proliferate_makers"}),
    )


def _self_life_payment(ident: str) -> bool:
    """A ``lifeloss_makers`` ident scoped to the commander's own controller
    (Hazel's "pay 2 life"): a cost the commander pays, not life loss the
    deck's drain payoffs consume or a drain to make more of — the same call
    :func:`_event_need` makes for a self-life-loss watcher."""
    return ident.startswith("lifeloss_makers|you|")


def _doer_name(key: str) -> str:
    return key.replace("_makers", "").replace("_", " ")


#: The subject a type payoff ident carries for the event its trigger watches
#: (``lanes.board_and_ramp``'s type-payoff watchers: ``etb`` an enters trigger,
#: ``cast`` a cast trigger) → the label word.
_TYPE_EVENT_SUBJECTS: Mapping[str, str] = {"etb": "entering", "cast": "cast"}


def _redundancy_needs(idents: Iterable[str], desc: str) -> Iterator[Need]:
    """Cards that do what the commander itself does (its doer idents): the
    frameworks' "redundancy of the commander's key effect" (goad under Nelly,
    mill under Winter, Warrior tokens under Zurgo). The specificity floor
    keeps a generic doer (an attack trigger) from becoming a need."""
    for ident in idents:
        key, _scope, subject = ident.split("|", 2)
        if key in _UMBRELLA_KEYS and subject in _TYPE_EVENT_SUBJECTS:
            # The commander's own trigger on a card type entering or being cast
            # ("Whenever an enchantment you control enters" — Killian: the
            # ``enchantments_matter|you|etb`` ident): the cards with that same
            # trigger do what it does (Grim Guardian's constellation, Victor's
            # eerie, Ondu Spiritdancer). The umbrella key alone stays out.
            yield Need(
                "redundancy",
                f"{_TYPE_EVENT_SUBJECTS[subject]} "
                f"{key.removesuffix('s_matter').replace('_', ' ')} payoffs "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )
            continue
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
        elif key in _PAYOFF_REDUNDANCY_KEYS:
            # A payoff that IS the doing — Teval's "whenever one or more cards
            # leave your graveyard" has no maker lane behind it; the cards that
            # do what he does carry the same key (Desecrated Tomb, Chalk
            # Outline, Tormod, the Desecrator: Sultai Arisen's guides' adds).
            yield Need(
                "redundancy",
                f"{key.removesuffix('_matters').replace('_', ' ')} payoffs "
                "like the commander",
                desc,
                idents=frozenset({ident}),
            )


def _payoff_needs(
    idents: Iterable[str], desc: str, *, floor_read: bool = False
) -> Iterator[Need]:
    """A commander payoff with no trigger of its own → what feeds it.

    ``floor_read``: the commander's trees already gave a mana-value-floor need
    (:func:`_spell_floor_need` off its own filter). That read keeps the filter's
    negations — Bello's "non-Equipment artifact" — where the ``animate_makers``
    ident's subject (``Artifact>=4``) drops them, so the ident's need is skipped:
    with both, Hammer of Nazahn and Leyline Axe led Animated Army's page as
    artifacts at 4+ mana Bello never animates (2026-11-01)."""
    idents = list(idents)
    keys_held = {ident.split("|", 1)[0] for ident in idents}
    # The commander's own suit is Auras: an ``aura_*`` ident and no equipment one.
    aura_only = any(k.startswith("aura_") for k in keys_held) and not any(
        "equip" in k for k in keys_held
    )
    for ident in idents:
        key, _scope, subject = ident.split("|", 2)
        if key == "type_matters":
            # A tribe the commander pays off is the tribal avenue's page already
            # (its members, plus changelings); a need page of it would add the
            # same cards twice over.
            continue
        if key in _TYPE_PAYOFF_KEYS:
            words = _TYPE_PAYOFF_KEYS[key]
            if key == "voltron_matters" and aura_only:
                # A voltron commander whose own suit is Auras (Ellivere's
                # Virtuous Roles) asks for Auras: an Equipment is a suit it
                # never wears (Virtue and Valor's guides add Auras and
                # enchantress draw; its pages led with Hammer of Nazahn and
                # Thran Power Suit, 2026-11-01).
                words = frozenset({"aura"})
            keys: set[str] = set()
            for w in words:
                keys |= _TYPE_TOKEN_KEYS.get(w, frozenset())
            if subject == "token":
                # A payoff for the type's TOKENS (Gimbal's "artifact tokens you
                # control with different names"): the token makers alone, never
                # every card of the type — a mana rock is an artifact, not what
                # Gimbal counts. Measured 2026-11-01 on Tinker Time: the
                # Artifacts page led with Fellwar Stone, Mind Stone and Thought
                # Vessel over Big Score and Idol of Oblivion.
                if keys:
                    yield Need(
                        "payoff",
                        f"{' '.join(sorted(words))} token makers",
                        desc,
                        keys=frozenset(keys),
                    )
                continue
            yield Need(
                "payoff",
                f"{key.replace('_', ' ')}",
                desc,
                types=frozenset({frozenset({w}) for w in words}),
                keys=frozenset(keys),
            )
        elif key == "keyword_tribe" and subject:
            # A lord of a keyword wants bodies with the keyword. Only a few
            # keywords are a ``keyword_bodies`` lane (evasion, haste); the
            # rest (defender — Felothar's walls) are read off the card's own
            # keyword list, the bodies lane's source too.
            kw = subject.lower()
            yield Need(
                "payoff",
                f"{kw} bodies",
                desc,
                idents=frozenset({f"keyword_bodies|you|{kw}"}),
                predicate=lambda c, kw=kw: (
                    kw in {k.lower() for k in c.get("keywords") or ()}
                ),
            )
        elif key == "animate_makers" and ">=" in subject and not floor_read:
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
                mana_floor=n,
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
            # A commander that reads toughness (Felothar assigns combat damage
            # by it, Pantlaza discovers for it) wants a HIGH toughness, not a
            # butt: Ghalta, Primal Hunger's 12 serves Pantlaza as Wall of Souls'
            # 4 serves Felothar. "Toughness over power" put Snubhorn Sentry and
            # Looming Altisaur ahead of Ghalta and Gishath on the Dinosaur page
            # (2026-11-01).
            yield Need(
                "payoff",
                "high toughness",
                desc,
                predicate=lambda c: (
                    _stat(c, "toughness") >= HIGH_TOUGHNESS
                    and "creature" in _type_words(c)
                ),
            )
        elif key == "energy_matters":
            # Energy is a counter on a player (CR 107.14), so a proliferate
            # gives you one more (CR 701.34a: "permanents and/or players that
            # have a counter") — Metastatic Evangel under Satya.
            yield Need(
                "payoff",
                "energy makers",
                desc,
                keys=frozenset({"energy_makers", "proliferate_makers"}),
            )
        elif key == "spellcast_matters":
            yield Need(
                "payoff",
                "instants and sorceries",
                desc,
                types=frozenset({frozenset({"instant"}), frozenset({"sorcery"})}),
                leads=False,
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
        trees = trees_for(dict(rec))
        tree_start = len(out)
        for tree in trees:
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
        for need in _resource_needs(idents, rec.get("name", ""), trees=trees):
            add(need)
        add(_loyalty_need(rec))
        for need in _redundancy_needs(idents, rec.get("name", "")):
            add(need)
        # A mana-value floor read off the commander's own filter keeps the
        # filter's negations; the ident's does not (``_payoff_needs``).
        floor_read = any(need.mana_floor for need in out[tree_start:])
        for need in _payoff_needs(idents, rec.get("name", ""), floor_read=floor_read):
            add(need)
        add(_multiplier_need(rec))
    # A trigger's refined read stands in for the payoff read of the same
    # ability: Valgavoth's "life loss on opponents' turns" beside the
    # ``lifeloss_matters`` payoff's generic "lifeloss makers", which would admit
    # Guttersnipe again.
    labels = {need.label for need in out}
    if "life loss on opponents' turns" in labels:
        out = [need for need in out if need.label != "lifeloss makers"]
    return tuple(out)


#: The :data:`multipliers.KIND_FAMILY` families a multiplier need counts: a copy
#: of the commander and a copy or an extra firing of its abilities. ``keep``
#: (Sundial of the Infinite under Saheeli) is the ``commander_keeps`` issue's own
#: page; a zone grant's cards (Thranduil's Elves) are the tribe's.
_MULTIPLIER_FAMILIES = frozenset({"copy", "ability"})
#: The signal keys every commander multiplier carries (census 2026-10-31 over the
#: legal pool under three commanders: 643 of 644 multiplier hits carry one — the
#: miss is The Enigma Jewel's Locus face, whose "copy that ability" the
#: ``ability_copy`` lane doesn't read). A cheap gate before the tree walk, which
#: a tune would otherwise run for every card of every need page (12,000 a tune).
_MULTIPLIER_KEYS = frozenset(
    {
        "token_copy_makers",
        "clone_makers",
        "copy_permanent",
        "ability_copy",
        "spell_copy_makers",
        "trigger_doubling",
    }
)


def _multiplier_need(rec: Mapping) -> Need | None:
    """What multiplies the commander (``multipliers.multiplier_reasons``): a
    trigger doubler or an ability copier of an ability it has — a copy of an
    ability is an ability (CR 707.10) — or a clone or token copy of it. Read for
    a commander with a trigger or an activated ability to multiply, or a
    creature body to copy; ``None`` otherwise. A predicate need: the card's
    reasons are read against this commander, not off a key."""
    cmd = Commander(rec)
    if not (cmd.copyable_triggers or cmd.activated or "Creature" in cmd.facts.types):
        return None

    def multiplies(card: dict) -> bool:
        keys = {i.split("|", 1)[0] for i in _card_idents(card)}
        if not keys & _MULTIPLIER_KEYS:
            return False
        return any(
            r.family in _MULTIPLIER_FAMILIES for r in multiplier_reasons(card, cmd)
        )

    return Need(
        "payoff",
        "multipliers of the commander",
        rec.get("name", ""),
        predicate=multiplies,
    )


def need_serve(need: Need) -> Serve:
    """The ``Serve`` that pages ``need`` (``signal_specs.Serve``'s predicate arm):
    the cards that supply it, for the tune's need pages."""
    from mtg_utils._analysis.signal_specs import Serve

    return Serve(
        predicate=lambda card: satisfies(card, need),
        predicate_id=f"need:{need.kind}:{need.label}",
    )
