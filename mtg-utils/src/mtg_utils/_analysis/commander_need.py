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

The module is the facade (``commander_needs``, ``need_serve``) over three
parts, re-exported here so every old import path holds: ``need_model`` (the
``Need`` and ``satisfies``), ``need_reads`` (the supplier reads) and
``need_builders`` (the commander's text read into needs).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING

from mtg_utils._analysis.multipliers import Commander, multiplier_reasons
from mtg_utils._analysis.signal_base import ident_key
from mtg_utils._card_ir.crosswalk.reads import (
    _present,
    iter_condition_sites,
    requires_condition_inner,
    tag_of,
    trigger_def_event,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._card_ir.trees import trees_for

if TYPE_CHECKING:
    from mtg_utils._analysis.signal_specs import Serve
from mtg_utils._analysis.need_builders import (  # noqa: F401 — re-exported: the old import path
    _COUNTER_GROWTH_KEYS,
    _DEATH_KEYS,
    _EXTRA_CONSUMER_IDENTS,
    _EXTRA_CONSUMER_KEYS,
    _EXTRA_CONSUMER_PREDICATES,
    _GRAVEYARD_FILL_KEYS,
    _GRAVEYARD_LEAVE_KEYS,
    _LAND_SUBTYPE_WORDS,
    _MAKER_PREDICATES,
    _OPPONENT_TURN_GATES,
    _PAYOFF_REDUNDANCY_KEYS,
    _PERMANENT_TYPES,
    _SIZE_TAGS,
    _SPENDER_SKIP_KINDS,
    _TYPE_EVENT_SUBJECTS,
    _TYPE_PAYOFF_KEYS,
    _TYPE_TOKEN_KEYS,
    _UMBRELLA_KEYS,
    BIG_SPELL_MV,
    FODDER_MV,
    FODDER_POWER,
    REANIMATION_MV,
    _cast_power_need,
    _cheap_spells_need,
    _condition_need,
    _counted_counter_needs,
    _counter_filter_kind,
    _counter_kind_needs,
    _counter_placement,
    _doer_name,
    _effect_needs,
    _event_need,
    _filter_colorless,
    _graveyard_fill_need,
    _graveyard_return_filters,
    _graveyard_take_needs,
    _has_pred,
    _loyalty_need,
    _own_damage_grant_need,
    _payoff_needs,
    _reanimation_target_need,
    _redundancy_needs,
    _resource_needs,
    _sacrificed_power_need,
    _self_life_payment,
    _served_keys,
    _sizes_the_card,
    _spell_floor_need,
    _spells_cast_filter,
    _static_needs,
    _token_kind_needs,
    _tribe_payoff_needs,
    _type_need,
    _walk,
)
from mtg_utils._analysis.need_model import (  # noqa: F401 — re-exported: the old import path
    _SHARE_MEMO,
    BROAD_SHARE,
    CARD_TYPES,
    HIGH_TOUGHNESS,
    Need,
    _card_idents,
    _type_words,
    card_type_count,
    is_broad,
    need_pool_share,
    need_predicate,
    needs_met,
    satisfies,
    specific_needs,
)
from mtg_utils._analysis.need_reads import (  # noqa: F401 — re-exported: the old import path
    _ATTACKER_SUPPORT_KEYS,
    _CREATURE_TYPE_WORDS,
    _DEATH_FEED_KEYS,
    _ENTERS_WITH_COUNTERS,
    _EVASION_KEYS,
    _EVASION_KEYWORDS,
    _EVENT_MAKER_KEYS,
    _HALF_CAST_LAYOUTS,
    _OWN_COMBAT_KEYS,
    _OWN_DAMAGE_KEYWORDS,
    _PLAYER_ACTION_EVENTS,
    _RIDER_KEYS,
    _TYPAL_PAYOFF_KEYS,
    CHEAP_SPELL_MV,
    _animates_attackers,
    _cheap_spell,
    _cost_string_value,
    _drains_on_opponents_turns,
    _drains_only_on_own_combat,
    _evasion_for,
    _grants_all_creature_types_node,
    _grants_the_commander,
    _has_x_cost,
    _holds_counters,
    _lifelink_only,
    _makes_tokens_of,
    _mana_value_reaches,
    _places_counters,
    _puts_minus_counters,
    _sacrifices_a_creature,
    _sacrifices_artifacts,
    _sacrifices_lands,
    _spends_counters,
    _stat,
    _supports_attackers,
    _takes_from_your_graveyard,
    _typal_payoff,
    grants_all_creature_types,
    typal_payoff_for,
)

# ── vocabulary ──────────────────────────────────────────────────────────────


# ── the need ────────────────────────────────────────────────────────────────


# ── reading the commander ───────────────────────────────────────────────────


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
        if _lifelink_only(trees):
            # Its own lifelink (CR 702.15b) is a gain per hit of one body, no
            # lifegain plan: Olivia, Opulent Outlaw's lifelink drew Sanguine
            # Bond and Vito where her guides say lifegain "only works with
            # Olivia's lifelink" and cut it (Most Wanted, 2026-11-02).
            idents = [i for i in idents if not i.startswith("lifegain_makers|")]
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
        for need in _tribe_payoff_needs(idents, rec.get("name", "")):
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
        keys = {ident_key(i) for i in _card_idents(card)}
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
