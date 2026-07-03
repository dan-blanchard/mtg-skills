"""Layer-3 ``Signal`` lanes derived from the Layer-2 concept overlay (ADR-0035).

The first ported concept batch. Each lane reads the tree-preserving concept
overlay (``_card_ir.crosswalk.ConceptTree``) — typed reads only, no oracle re-grep
— and emits the frozen ``Signal(key, scope, subject)`` contract, mirroring the live
``_deck_forge._signals_ir`` arm closely enough that the shadow diff reproduces it
(or improves on a known lossy case). **Shadow-only / additive**: production
detection (``signals.py`` / ``_signals_ir.py``) is untouched; this runs alongside
for the diff.

The batch spans every concept kind the framework must prove:

* ``win_lose_game`` — a terminal **effect category** (whole-card scan, scope "any").
* ``discard_makers`` — a **join-dependent** maker: a ``draw`` + ``discard`` effect
  in the SAME ability unit (granularity *a*; never across abilities, never a cost).
* ``spell_copy_makers`` — a structural **effect**, plus the whole-card
  ``spellcast_matters`` reconciliation (granularity *c*).
* ``token_maker`` — a structural effect that is **subject-bearing** (the token's
  creature subtype, vocab-validated).
* ``draw_matters`` — a **trigger event** (Drawn), scope-discriminated.
* ``land_creatures_matter`` — a **per-ability aggregation** of a Land(+Creature)
  subject with a pump/animate modification (granularity *b*; the animate-land
  split-subject).

``PORTED_KEYS`` is the batch's Signal-key set — the shadow diff slices both paths
to it.
"""

from __future__ import annotations

import re
from dataclasses import fields as dc_fields

from mtg_utils._card_ir.crosswalk import (
    ARTIFACT_TOKEN_SUBTYPES,
    OTHER,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    additional_phase_kind,
    amount_factor,
    amount_is_scaling,
    cast_with_keyword_name,
    change_zone_dirs,
    color_count_preds,
    condition_tags,
    control_recipient_scope,
    cost_has_paylife,
    count_operand_filter,
    count_operand_qty,
    counter_kind,
    counter_kind_any,
    counter_pred_kinds,
    damage_filter_scope,
    damage_recipient_is_player,
    discard_recipient_scope,
    distribute_counter_kind,
    double_target_kind,
    double_triggers_cause_core_types,
    effect_filter,
    effect_owner_duration,
    effect_owner_player_scope,
    effect_reaches_player,
    entered_this_turn_filters,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_non_types,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    filter_without_keywords,
    hand_size_scopes,
    has_filter_property,
    is_dies_return_trigger,
    iter_condition_sites,
    iter_cost_leaves,
    iter_deep_target_grants,
    iter_mod_sites,
    iter_single_target_grants,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    lifeloss_recipient_scope,
    mana_replacement_multiplier,
    mana_restrictions,
    mod_keyword_name,
    mod_value,
    modify_cost_mode,
    modify_cost_spell_filter,
    node_lure_mode,
    permission_tag,
    player_counter_kind,
    player_filter_tag,
    power_threshold_preds,
    produced_contribution,
    protection_cardtype,
    pump_is_negative,
    recipient_tag,
    ref_qty_tag,
    replacement_damage_mod,
    replacement_event_tag,
    replacement_qty_mod,
    replacement_shield_kind,
    replacement_token_owner_scope,
    reveal_until_player,
    settap_state,
    spell_count_at_least,
    static_mode_field,
    static_mode_tag,
    static_reveal_who,
    tag_of,
    token_profile_keywords,
    trigger_caster_scope,
    trigger_constraint_n,
    trigger_constraint_tag,
    trigger_counter_filter,
    trigger_damage_kind,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
    trigger_turn_constraint,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant, TypedMirrorNode

# The b13 conferred-grant / condition-payoff raw anchors import the LIVE
# projection constants (project.py's _narrow_* marker sources — the same
# b12-sanctioned single-source pattern): the marker effects those anchors
# produce exist only in the LOSSY projection, so the crosswalk re-derives
# their populations from the same pinned regexes over the kept oracle.
from mtg_utils._card_ir.project import (
    _AFFINITY_GRANT,
    _CASCADE_GRANT,
    _CHANGELING_REF,
    _MADNESS_GRANT,
    _MUTATE_COND,
    _SOULBOND_REF,
    _UNDYING_PERSIST_GRANT,
)
from mtg_utils._deck_forge import signal_keys

# The b12 SANCTIONED byte-identical mirror ports import the LIVE constants
# (never re-typed copies): the pinned shared sources from _sweep_detectors,
# and the private live mirrors/kind-sets from _signals_ir / _signals_regex
# (the _resolve_subject precedent) — one source, zero drift.
from mtg_utils._deck_forge._signals_ir import (
    _BIG_HAND_MAKERS_MIRROR,
    _BIG_HAND_MATTERS_MIRROR,
    _CONVOKE_RAW,
    _COUNTER_DISTRIBUTE_MIRROR,
    _KEYWORD_COUNTER_KINDS,
    _SAME_TRUE_KW_RE,
    _STAX_TAXES_RESIDUE_RE,
    _SYMMETRIC_STAX_RESIDUE_RE,
    _restriction_pacifies_single_creature,
)
from mtg_utils._deck_forge._signals_regex import (
    _EVERGREEN_CK,
    _REPEATABLE_KILL_RE,
    Signal,
    _detect_keyword_tribe,
    _resolve_subject,
    _type_hoser_clause,
    clauses,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge._sweep_detectors import (
    ANIMATE_ARTIFACT_REGEX,
    COLOR_CHANGE_REGEX,
    ENTERED_ATTACKER_REGEX,
    ISLAND_MATTERS_REGEX,
    KEYWORD_COUNTER_REGEX,
    SUPERFRIENDS_MATTERS_REGEX,
    UNSPENT_MANA_REGEX,
    VEHICLES_MATTER_REGEX,
)

# The Signal keys this batch derives from the typed substrate. The shadow harness
# slices BOTH the crosswalk and the live hybrid path to exactly this set.
PORTED_KEYS: frozenset[str] = frozenset(
    {
        # Batch 1 (already landed):
        "win_lose_game",
        "discard_makers",
        "spell_copy_makers",
        "spellcast_matters",
        signal_keys.TOKEN_MAKER,
        "draw_matters",
        "land_creatures_matter",
        # Batch 2 (ADR-0035 Stage 2, this increment):
        "death_matters",
        "extra_turns",
        "lifegain_makers",
        "reanimator",
        "plus_one_makers",
        "direct_damage",
        "landfall",
        "sacrifice_outlets",
        "lifegain_matters",
        "blink_flicker",
        "tokens_matter",
        "ramp",
        # Batch 3 (ADR-0035 Stage 2, big over-fire lanes + doer cluster):
        "creatures_matter",
        "artifacts_matter",
        "enchantments_matter",
        "attack_matters",
        "tapped_matters",
        "any_counter_makers",
        "any_counter_matters",
        "plus_one_matters",
        "minus_counters_matter",
        "gain_control",
        "treasure_makers",
        "food_makers",
        "clue_makers",
        "blood_makers",
        "mill_makers",
        "proliferate_makers",
        "energy_makers",
        "voltron_makers",
        "voltron_matters",
        # Batch 4 (ADR-0035 Stage 2, this increment):
        "graveyard_makers",
        "graveyard_matters",
        "fight_makers",
        "goad_makers",
        "regenerate_makers",
        "lifeloss_makers",
        "lifeloss_matters",
        "edict_makers",
        "land_sacrifice_makers",
        "debuff_makers",
        "lure_makers",
        "copy_permanent",
        "clone_makers",
        "token_copy_makers",
        "connive_makers",
        "explore_makers",
        "suspect_makers",
        "combat_damage_to_opp",
        # Batch 5 (ADR-0035 Stage 2, the named-mechanic long tail):
        "monarch_makers",
        "monarch_matters",
        "discover_makers",
        "venture_makers",
        "venture_matters",
        "daynight_makers",
        "daynight_matters",
        "phasing_makers",
        "voting_makers",
        "ring_tempters",
        "ring_matters",
        "amass_makers",
        "incubate_makers",
        "facedown_makers",
        "dice_makers",
        "cast_from_exile",
        "foretell_makers",
        "cascade_makers",
        "suspend_makers",
        "poison_makers",
        # Batch 6 (ADR-0035 Stage 2): the counter-KIND / count-operand / property
        # build-around cluster.
        "oil_counter_makers",
        "oil_counter_matters",
        "ki_counter_makers",
        "rad_counter_makers",
        "shield_counter_makers",
        "experience_makers",
        "experience_matters",
        "devotion_matters",
        "party_matters",
        "domain_matters",
        "modified_matters",
        "multicolor_matters",
        "colorless_matters",
        "power_matters",
        "low_power_matters",
        "coin_flip",
        "opponent_discard",
        "vanilla_matters",
        # Batch 7 (ADR-0035 Stage 2): the phase / control / terminal-effect cluster
        # + four Scryfall-keyword maker survivors.
        "extra_combats",
        "cost_reduction",
        "donate_makers",
        "conjure_makers",
        "blocked_matters",
        "initiative_makers",
        "initiative_matters",
        "end_the_turn",
        "opponent_exile_makers",
        "boast_makers",
        "exhaust_makers",
        "convoke_makers",
        "magecraft_matters",
        # Batch 8 (ADR-0035 Stage 2): the mana / card-flow / removal-sub-lane /
        # pump-sub-lane / library-top cluster.
        "mana_amplifier",
        "extra_land_drop",
        "group_mana",
        "draw_for_each",
        "discard_outlet",
        "mass_removal",
        "mass_bounce",
        "exile_removal",
        "lands_matter",
        "treasure_matters",
        "blood_matters",
        "anthem_static",
        "count_anthem",
        "scaling_pump",
        "self_pump",
        "team_buff",
        "cheat_into_play",
        "impulse_top_play",
        "play_from_top",
        "counter_manipulation",
        # Batch 9 (ADR-0035 Stage 2): the discard/draw payoff, death-loop,
        # card-advantage-engine, library-top, combat-pump, and grant cluster.
        "discard_matters",
        "opponent_draw_matters",
        "self_death_payoff",
        "dies_recursion",
        "creature_recursion",
        "card_draw_engine",
        "group_hug_draw",
        "target_player_draws",
        "activated_draw",
        "topdeck_selection",
        "topdeck_stack",
        "combat_buff_engine",
        "land_sacrifice_matters",
        "exile_matters",
        "energy_matters",
        "counter_move",
        "explore_matters",
        "dice_matters",
        "extra_upkeep",
        "extra_end_step",
        "facedown_matters",
        "spell_keyword_grant",
        "flash_grant",
        "flash_makers",
        "hand_disruption",
        # Batch 10 (ADR-0035 Stage 2): the trigger-event cluster, effect-tag
        # cluster, keyword-grant/mod-site cluster, P/T-characteristic cluster,
        # static-mode cluster, and three probed bonus ports.
        "creature_etb",
        "permanent_etb",
        "ltb_matters",
        "creature_cast_trigger",
        "opponent_cast_matters",
        "combat_damage_matters",
        "damage_to_opp_matters",
        "second_spell_matters",
        "xspell_matters",
        "counter_control",
        "bounce_tempo",
        "power_double",
        "keyword_grant_target",
        "protection_grant",
        "all_creatures_kw_grant",
        "team_evasion_grant",
        "aura_equip_kw_grant",
        "base_pt_set",
        "variable_pt",
        "trigger_doubling",
        "forced_attack",
        "damage_prevention",
        "damage_equal_power",
        # Batch 11 (ADR-0035 Stage 2): the replacement-doubler cluster, the
        # damage-trigger cluster, the counter/ETB/cast trigger-event cluster,
        # the tap cluster, the library/zone cluster, and four probed bonus
        # ports (§F).
        "token_doubling",
        "counter_doubling",
        "counter_replace_bonus",
        "damage_doubling",
        "damage_reflect",
        "damage_to_you_punish",
        "combat_damage_to_creature",
        "tribe_damage_trigger",
        "symmetric_damage_each",
        "aoe_ping",
        "creature_ping",
        "counter_place_trigger",
        "tribal_etb_multi",
        "typed_enters_punish",
        "noncreature_cast_punish",
        "tap_down",
        "tapper_engine",
        "tap_untap_matters",
        "dig_until",
        "exile_until_leaves",
        signal_keys.TYPED_SPELLCAST,
        "legends_matter",
        "historic_matters",
        "self_blink",
        # Batch 12 (ADR-0035 Stage 2): the trigger-event payoff cluster, the
        # effect-node lanes, the control/land cluster, the mirror-parity
        # lanes, the statics/taxes/counters cluster, and the reference/
        # condition lanes (+ 2 batch-11 adjudicated follow-ups riding the
        # already-ported typed_spellcast / tap_down lanes).
        "scry_surveil_matters",
        "cycling_matters",
        "exert_matters",
        "entered_attacker",
        "saga_matters",
        "life_total_set",
        "unspent_mana",
        "opp_top_exile",
        "kill_engine",
        "control_exchange",
        "land_exchange",
        "land_denial",
        "land_protection",
        "evasion_denial",
        "animate_artifact",
        "color_change",
        "type_change",
        "stax_taxes",
        "symmetric_stax",
        "keyword_counter",
        "counter_grants_kw",
        "counter_distribute",
        "superfriends_matters",
        "commander_matters",
        "big_hand_matters",
        "big_hand_makers",
        "vehicles_matter",
        # Batch 13 (ADR-0035 Stage 2): the field-lookup wholesale batch — 7
        # pure Scryfall-keyword rows, 11 keyword+top-up membership lanes, 5
        # structural payoff arms, 4 kept-mirror ports (keyword_tribe is
        # SUBJECT-carrying).
        "companion_keyword",
        "has_banding",
        "has_dash",
        "has_enlist",
        "specialize_matters",
        "alt_cost_keyword",
        "partner_background",
        "madness_matters",
        "affinity_type",
        "scavenge_fuel",
        "has_soulbond",
        "has_mutate",
        "has_ninjutsu",
        "has_undying_persist",
        "has_devour",
        "has_changeling",
        "myriad_grant",
        "boast_matters",
        "cascade_matters",
        "convoke_matters",
        "curse_matters",
        "foretell_matters",
        "keyword_soup",
        "island_matters",
        "poison_matters",
        "suspend_matters",
        signal_keys.KEYWORD_TRIBE,
        # NB: damage_redirect stays KEPT (spec §G): `redirect_target` exists
        # on only 8 corpus replacements and Pariah itself parses with NO
        # redirect_target (shield Prevention only — structurally identical to
        # a pure prevention shield). SUPPLEMENT-RECOVERABLE ("is dealt to [X]
        # instead" carries the signal); the live word mirrors stay.
        # NB: land_destruction stays KEPT (batch-8 reclassification upheld):
        # the membership-gated structural arm reproduces the live 23-card set
        # 23/23 but adds 2 non-byte-identical extras (Goblin Grenadiers,
        # Orcish Settlers — a pure-Land Destroy the live "destroy … target
        # land(s)" literal never matched), failing the spec's byte-match
        # condition for superseding the KEPT verdict.
    }
)

# Cast-from-graveyard keyword family (CR 601.3 / 702.62a …) — a card that re-casts
# ITSELF from a graveyard PERFORMS self-recursion → ``graveyard_makers`` you. A
# Scryfall keyword field-lookup (the live ``_IR_KEYWORD_MAP`` survivors): these are
# NOT a ``ChangeZone`` effect (phase carries them on castable-zone metadata, no
# effect node), so the structural substrate cannot read them — re-introducing them
# structurally is impossible, dropping them a regression (checklist #3).
_GY_CAST_KEYWORDS: frozenset[str] = frozenset(
    {
        "flashback",
        "escape",
        "disturb",
        "embalm",
        "eternalize",
        "encore",
        "aftermath",
        "retrace",
        "jump-start",
        "recover",
        "unearth",
    }
)

# Graveyard-payoff keyword family (CR 702.51 dredge / 702.66 delve / 702.91
# scavenge) — a card that CONSUMES a stocked graveyard as fuel → ``graveyard_matters``
# you. Keyword field-lookup, same survivor rationale.
_GY_MATTERS_KEYWORDS: frozenset[str] = frozenset({"dredge", "delve", "scavenge"})

# Attachment predicates that mark a SINGLE-Aura / single-target shrink (CR 303) — the
# affected creature is the one enchanted, not a mass population. A base-P/T-shrink
# debuff carrying one is a neutralize, not a -1/-1 enabler.
_DEBUFF_SINGLE_AURA_PREDS: frozenset[str] = frozenset(
    {"EnchantedBy", "AttachedToRecipient", "HasAnyAttachmentOf"}
)

# Equipment / Aura / Role subtypes that mark a voltron build-around (CR 301.5 /
# 303.4 / 702.5). Mirrors ``_signals_regex._EQUIP_AURA_SUBTYPES`` (+ Role, a Aura
# subtype phase carries on Virtuous Role tokens).
_VOLTRON_SUBTYPES: frozenset[str] = frozenset({"aura", "equipment", "role"})

# Attachment-STATE predicate tags (CR 301.5c / 303). Mirrors
# ``_signals_regex._ATTACHMENT_PREDICATES``.
_ATTACHMENT_PREDS: frozenset[str] = frozenset(
    {"AttachedToRecipient", "HasAnyAttachmentOf"}
)

# Core-type → matters lane. A composite (Artifact AND/OR Enchantment) subject fires
# BOTH. Mirrors ``_signals_ir._TYPE_MATTERS_LANE`` for this batch's two types.
_TYPE_MATTERS_LANE: dict[str, str] = {
    "Artifact": "artifacts_matter",
    "Enchantment": "enchantments_matter",
}

# Effect/owner scopes that count as "your" resource for a maker lane.
_YOU_EACH = ("you", "each")

# Phase ``produced.type`` values that are intrinsically FIXING (a choice of ≥2
# colors / any-color / any-type) — mirrors ``project._FIXING_PRODUCED_TYPES``. A
# land whose ramp is fixing is real ramp, not the mana base. CR 106.1 / 605.1a.
_FIXING_PRODUCED_TYPES: frozenset[str] = frozenset(
    {
        "AnyInCommandersColorIdentity",
        "AnyTypeProduceableBy",
        "ChoiceAmongCombinations",
        "ChosenColor",
        "OpponentLandColors",
        "DistinctColorsAmongPermanents",
        "AnyOneColorAmongPermanents",
        "ChoiceAmongExiledColors",
    }
)


# ── Batch-12 mirror constants + census sets ──────────────────────────────────

# Compiled forms of the pinned live regex sources (byte-identical by import;
# same IGNORECASE flag the live kept-detectors compile with).
_ENTERED_ATTACKER_RX = re.compile(ENTERED_ATTACKER_REGEX, re.IGNORECASE)
_ANIMATE_ARTIFACT_RX = re.compile(ANIMATE_ARTIFACT_REGEX, re.IGNORECASE)
_COLOR_CHANGE_RX = re.compile(COLOR_CHANGE_REGEX, re.IGNORECASE)
_UNSPENT_MANA_RX = re.compile(UNSPENT_MANA_REGEX, re.IGNORECASE)
_VEHICLES_MATTER_RX = re.compile(VEHICLES_MATTER_REGEX, re.IGNORECASE)
_KEYWORD_COUNTER_RX = re.compile(KEYWORD_COUNTER_REGEX, re.IGNORECASE)
_SUPERFRIENDS_RX = re.compile(SUPERFRIENDS_MATTERS_REGEX, re.IGNORECASE)

# Johan + manland mirrors: byte-identical copies of the two INLINE (unnamed)
# ``_IR_KEPT_DETECTORS`` rows in ``_signals_ir`` (exert_matters ~line 2343,
# land_protection ~line 2411) — the only two b12 mirrors with no importable
# name.
_JOHAN_MIRROR = re.compile(
    r"attacking doesn'?t cause (?:creatures|them)[^.]*to tap", re.IGNORECASE
)
_MANLAND_MIRROR = re.compile(
    r"land[^.]*becomes? a[^.]*creature|lands? you control are[^.]*creatures"
    r"|that land becomes",
    re.IGNORECASE,
)

# Reminder-text strip — the same paren-substitution the live path applies to
# build ``kept_oracle`` (_signals_ir line ~11091).
_REMINDER_RX = re.compile(r"\([^)]*\)")

# Trigger events that fire AT MOST ONCE per object (crosswalk event names) —
# NOT a repeatable kill frame. Mirrors live's ``_KILL_ENGINE_ONESHOT_EVENTS``
# {etb, ltb, dies, death, leaves, transformed, turn_face_up} + the monstrous
# one-shot (CR 701.37b) live screens by raw.
_KILL_ONESHOT_EVENTS: frozenset[str] = frozenset(
    {
        "enters",
        "dies",
        "leaves",
        "changes_zone",
        "transformed",
        "transforms",
        "turnedfaceup",
        "turnfaceup",
        "becomemonstrous",
        "becomesmonstrous",
    }
)

# Stax census (spec §E): plain-restriction static modes whose direction rides
# the AFFECTED filter's controller, and parameterized cast/activation LOCK
# modes whose direction rides the mode's own ``who`` field. CR 101.2 + 604.1.
_STAX_SIMPLE_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "CantAttack",
        "CantBlock",
        "CantAttackOrBlock",
        "CantUntap",
        "CantGainLife",
        "MustAttack",
        "CantPlayLand",
    }
)
_STAX_LOCK_MODES: frozenset[str] = frozenset(
    {
        "CantBeActivated",
        "CantBeCast",
        "CantCastDuring",
        "CantActivateDuring",
        "PerTurnCastLimit",
    }
)

# Predicates that mark a single-Aura pacify subject (gate i — Pacifism/Arrest).
_PACIFY_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})

# Land subtype words the land-animate arms accept when the animated filter
# names the land by SUBTYPE ("target Forest" — Awakener Druid). CR 205.3i.
_LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "desert",
        "gate",
        "lair",
        "locus",
        "cave",
        "mine",
        "power-plant",
        "sphere",
        "tower",
        "urza's",
    }
)

# Dynamic P/T modification tags (both phase spellings — Maro's
# ``SetDynamicPower`` pair and Titania's Song's ``SetPowerDynamic`` pair):
# the big_hand_matters CDA site.
_DYNAMIC_PT_MODS: frozenset[str] = frozenset(
    {
        "SetDynamicPower",
        "SetDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
    }
)


def _kept(tree: ConceptTree) -> str:
    """The reminder-stripped face oracle — the b12 mirror ports' scan text."""
    return _REMINDER_RX.sub(" ", tree.oracle or "")


def _win_lose_game(tree: ConceptTree) -> list[Signal]:
    """Terminal alt-win / alt-loss (CR 104.2). Whole-card; scope "any" (HIGH).

    Mirrors ``_signals_ir`` line ~7330: any ``win_game`` / ``lose_game`` effect →
    one ``win_lose_game`` firing scoped "any" (the behavior-neutral merge of
    self-wins and opponent-losses the deleted SWEEP row used).
    """
    for concept in ("win_game", "lose_game"):
        hits = tree.effect_concepts(concept)
        if hits:
            return [Signal("win_lose_game", "any", "", hits[0].raw, tree.name, "high")]
    return []


def _discard_makers(tree: ConceptTree) -> list[Signal]:
    """Loot / rummage / connive OUTLET — a draw + discard in the SAME ability unit.

    Granularity (a), per-ability sibling co-occurrence. Mirrors ``_signals_ir``
    line ~7535: an ability carrying BOTH a ``draw`` effect AND a ``discard`` effect
    scoped you/each is a self-loot outlet. The per-unit gate (``effect_concepts``
    reads role=effect only, scoped to one unit) is load-bearing: Psychic Frog and
    Nezahal carry a combat-damage draw *trigger* and a separate ``Discard a card:``
    *cost* in DIFFERENT units, so they must NOT fire here.
    """
    for unit in tree.units:
        if not unit.has_effect("draw"):
            continue
        disc = next(
            (c for c in unit.effect_concepts("discard") if c.scope in _YOU_EACH),
            None,
        )
        if disc is not None:
            return [Signal("discard_makers", "you", "", disc.raw, tree.name, "high")]
    return []


def _spell_copy_makers(tree: ConceptTree) -> list[Signal]:
    """A spell-copier (Twincast / Fork — "copy target spell"). Whole-card (HIGH).

    Mirrors ``_signals_ir`` line ~8684: a ``copy_spell`` effect → spell_copy_makers
    you. Distinct from clone (creatures-on-battlefield) and token-copy.
    """
    hits = tree.effect_concepts("copy_spell")
    if hits:
        return [Signal("spell_copy_makers", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _token_maker(tree: ConceptTree) -> list[Signal]:
    """A creature-token MAKER — subject-bearing (the token's kindred subtype).

    Mirrors ``_signals_ir`` line ~8072: a ``make_token`` effect scoped you/each
    whose token is a creature → ``token_maker`` with the vocab-resolved subtype
    subject ("" when none resolves). The owner-scope gate drops opponent-gift
    tokens (Hunted Dragon). Reads the token's ``types`` from the typed node, never
    oracle text.
    """
    seen: set[str] = set()
    out: list[Signal] = []
    for concept in tree.effect_concepts("make_token"):
        if concept.scope not in _YOU_EACH:
            continue
        types = concept.subject
        if "Creature" not in types:
            continue
        subject = ""
        for word in reversed(types):
            resolved = _resolve_subject(word, CREATURE_SUBTYPES)
            if resolved:
                subject = resolved
                break
        if subject in seen:
            continue
        seen.add(subject)
        out.append(
            Signal(
                signal_keys.TOKEN_MAKER, "you", subject, concept.raw, tree.name, "high"
            )
        )
    return out


def _draw_matters(tree: ConceptTree) -> list[Signal]:
    """ "Whenever you draw a card" payoff (The Locust God, Chasm Skulker).

    A trigger-event lane. Mirrors ``_signals_ir`` line ~10653: a ``Drawn`` trigger
    whose watched scope is not the opponent → ``draw_matters`` you (HIGH). The
    opponent-draw punisher (Bowmasters, Nekusar) is a SEPARATE lane and does not
    fire here.
    """
    for unit in tree.units:
        if unit.trigger_event != "drawn":
            continue
        if trigger_scope(unit.node) != "opponents":
            return [Signal("draw_matters", "you", "", "", tree.name, "high")]
    return []


def _is_creature_animator(unit: object, scopes: tuple[str, ...] = ("you",)) -> bool:
    """A static ability that turns its Land subject into a creature (animate-land).

    Granularity (b) per-ability aggregation: the unit's ``affected`` Land subject
    and an ``AddType Creature`` (or a base-P/T set that makes it a creature) modi-
    fication are read TOGETHER off one continuous ability — the split-subject the
    old projection drops to ``None`` and spreads across effects (Natural
    Emergence). ``scopes`` mirrors the live controller tuple: ``("you",)`` for
    land_creatures_matter (a symmetric all-lands animate — Living Plane — does
    not open a your-lands build), widened to ``("you", "any")`` by the b12
    land_protection lane (live passes the same widened tuple).
    """
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    if statics[0].scope not in scopes:  # the affected-filter controller gate
        return False
    subject = statics[0].subject  # all mods share the ability's affected subject
    if "Land" not in subject or "Creature" in subject:
        return False
    for concept in statics:
        if (
            concept.concept == "add_type"
            and getattr(concept.node, "core_type", None) == "Creature"
        ):
            return True
        # A Land made into a 1/1 via base-P/T set + AddType handled above; a bare
        # set_pt with no AddType is not an animator (it stays a land).
    return False


def _has_land_and_creature(subject: tuple[str, ...]) -> bool:
    """A dual Land+Creature subject (the anthem/maker shape — Sylvan Advocate)."""
    return "Land" in subject and "Creature" in subject


def _land_creatures_matter(tree: ConceptTree) -> list[Signal]:
    """A land-creatures build — anthem over Land+Creature, or a land-animator.

    Mirrors ``_signals_ir`` line ~7720. Two arms read off the typed substrate:

    * **anthem** — a pump / grant-keyword / set-P/T modification (static) OR a
      ``make_token`` effect whose subject is a dual Land+Creature (Sylvan Advocate,
      Jyoti).
    * **animator** — a static ability turning a Land subject into a creature
      (Living Plane), via :func:`_is_creature_animator` (granularity b).
    """
    for unit in tree.units:
        for concept in unit.statics:
            if concept.concept in (
                "pump",
                "grant_keyword",
                "set_pt",
            ) and _has_land_and_creature(concept.subject):
                return [
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                ]
        for concept in unit.effect_concepts("make_token"):
            if _has_land_and_creature(concept.subject):
                return [
                    Signal(
                        "land_creatures_matter",
                        "you",
                        "",
                        concept.raw,
                        tree.name,
                        "high",
                    )
                ]
        if _is_creature_animator(unit):
            return [Signal("land_creatures_matter", "you", "", "", tree.name, "high")]
    return []


# ── Batch 2 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────


def _is_creature_death_subject(subject: tuple[str, ...]) -> bool:
    """Whether a ``dies`` trigger's watched OBJECT is a CREATURE (CR 700.4).

    "Dies" is defined only for creatures (a creature put into a graveyard from the
    battlefield); a watcher of a non-creature graveyard-arrival (Scrapheap —
    "an artifact or enchantment is put into your graveyard from the battlefield")
    is a different lane, NOT a death payoff. True when the watched subject names
    ``Creature`` OR resolves to a real creature subtype (Kithkin Mourncaller — "an
    attacking Kithkin or Elf"); a pure ``Artifact`` / ``Enchantment`` subject is
    rejected. The subtype check routes through ``_resolve_subject`` so it shares the
    vocab's case-folding + the card-type / non-creature-token (Treasure / Clue)
    denylists rather than a raw membership test against the lowercased vocab.
    """
    return "Creature" in subject or any(
        _resolve_subject(w, CREATURE_SUBTYPES) for w in subject
    )


def _death_matters(tree: ConceptTree) -> list[Signal]:
    """Aristocrats payoff — a ``dies`` trigger watching OTHER creatures (CR 700.4).

    Mirrors ``_signals_ir`` line ~10383 (``trig.event=="dies" and
    trig.subject is not None``): a bare SelfRef "When THIS dies" carries no watched
    subject (``trigger_subject`` empty) → it is ``self_death_payoff``, a different
    lane, excluded here. Blood Artist / Zulaport / Midnight Reaper carry a real
    creature filter (the ``Or[SelfRef, Typed Creature]`` surfaces ``Creature`` past
    the self arm). Scope = the watched object's controller (Blood Artist → "any",
    Grave Pact → "you", Massacre Wurm → "opponents").
    """
    out: list[Signal] = []
    for unit in tree.units:
        if unit.trigger_event != "dies":
            continue
        # CR 700.4: "dies" is put into a graveyard FROM THE BATTLEFIELD. A
        # "put into a graveyard from anywhere" trigger (origin unset — Planar Void,
        # Countryside Crusher) is a graveyard-arrival payoff, not a death payoff.
        if getattr(unit.node, "origin", None) != "Battlefield":
            continue
        subj = trigger_subject(unit.node)
        if not subj:  # bare SelfRef self-death
            continue
        # CR 700.4: only CREATURES die. A non-creature GY-arrival watcher (Scrapheap
        # — artifact/enchantment) is not a death payoff, even though phase emits the
        # same battlefield→graveyard trigger shape.
        if not _is_creature_death_subject(subj):
            continue
        out.append(
            Signal(
                "death_matters",
                trigger_subject_scope(unit.node),
                "",
                "",
                tree.name,
                "high",
            )
        )
    return out


def _extra_turns(tree: ConceptTree) -> list[Signal]:
    """An extra-turn grant (Time Warp, Nexus of Fate — CR 500.7). Whole-card, "you".

    Mirrors the ``extra_turn`` doer (``_DOER_EFFECT_KEYS`` → ("extra_turns","you")):
    any ``ExtraTurn`` effect, regardless of who takes it ("that player takes an
    extra turn" is still a build-around). The 5-card raw-fold tail phase buries in a
    sibling category is a known ``live_only`` residue (no ``_EXTRA_TURN_RAW`` here).
    """
    if tree.has_effect("extra_turn"):
        return [Signal("extra_turns", "you", "", "", tree.name, "high")]
    return []


def _lifegain_makers(tree: ConceptTree) -> list[Signal]:
    """A life-gain SOURCE — a ``gain_life`` effect, or a granted ``lifelink``.

    Mirrors ``_signals_ir`` lines ~7843 / ~7862. (a) a ``GainLife`` effect scoped
    you/any (Gray Merchant, Kitchen Finks); (b) a static ``AddKeyword(Lifelink)``
    grant (Basilisk Collar, Talus Paladin, Vault of the Archangel — CR 702.15b), the
    grantee NOT opponent-only. The card's OWN printed lifelink keyword rides the
    keyword path (out of this typed-effect arm). Scope "you".
    """
    for c in tree.effect_concepts("gain_life"):
        if c.scope in ("you", "any"):
            return [Signal("lifegain_makers", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.statics:
            if (
                c.concept == "grant_keyword"
                and getattr(c.node, "keyword", None) == "Lifelink"
                and c.scope != "opponents"
            ):
                return [Signal("lifegain_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _reanimator(tree: ConceptTree) -> list[Signal]:
    """A creature that returns creatures GY→battlefield (the archetype, not a spell).

    Mirrors ``_signals_ir`` line ~8095 (``cat=="reanimate" and is_creature(card)
    and _reanimates_creature``). Structural: the card is a Creature AND a
    ``ChangeZone`` effect with origin=Graveyard / destination=Battlefield whose
    moved subject is a Creature (Sheoldred, Chainer). Excludes GY→hand recursion and
    exile-return (those are different ``ChangeZone`` zone pairs). CR 700.4 / 603.6e.
    """
    if not tree.is_type("Creature"):
        return []
    for c in tree.effect_concepts("change_zone"):
        origin, dest = change_zone_dirs(c.node)
        if origin == "Graveyard" and dest == "Battlefield" and "Creature" in c.subject:
            return [Signal("reanimator", "you", "", c.raw, tree.name, "high")]
    return []


def _plus_one_makers(tree: ConceptTree) -> list[Signal]:
    """A +1/+1 counter PLACEMENT source (Forgotten Ancient, Avenger — CR 122.1).

    Mirrors ``_signals_ir`` line ~8472: a ``place_counter`` effect whose
    ``counter_type`` is ``P1P1`` (the discriminator phase isolates from loyalty /
    oil / shield placements), plus the blank-kind enters-with/modal form whose raw
    literally names "+1/+1 counter". Counter DOUBLERS are a separate lane. Scope
    "you".
    """
    for c in tree.effect_concepts("place_counter"):
        ck = counter_kind(c.node).upper()
        if ck == "P1P1" or (not ck and "+1/+1 counter" in (c.raw or "")):
            return [Signal("plus_one_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _direct_damage(tree: ConceptTree) -> list[Signal]:
    """Burn that reaches a PLAYER (Fanatic of Mogis, Lightning Bolt — CR 120.1).

    Mirrors ``_signals_ir`` line ~8237 (``cat=="damage"`` + ``_ir_damage_reaches_
    player``). Structural: a ``DealDamage`` / ``DamageEachPlayer`` / ``DamageAll``
    effect whose recipient reaches a player (``effect_reaches_player`` — each/opp
    player, or "any target", NOT a creature/permanent-only bite, NOT incidental
    self-damage). Damage DOUBLERS are a separate lane. Scope "you" (the burn
    controller).
    """
    for c in tree.effect_concepts("deal_damage"):
        if effect_reaches_player(c.node):
            return [Signal("direct_damage", "you", "", c.raw, tree.name, "high")]
    return []


def _landfall(tree: ConceptTree) -> list[Signal]:
    """A land entering as a trigger (Lotus Cobra, Tireless Tracker — CR 305 / 603.6e).

    Mirrors ``_signals_ir`` line ~10750 (``ev=="etb" and "Land" in tsubs``): an
    enters trigger whose watched subject names ``Land``. Scope "you" (forced). The
    ability-word-condition / extra-land-static / land-recursion forms are a known
    ``live_only`` mirror tail. CR 207.2c (landfall = flavor ability word).
    """
    for unit in tree.units:
        if unit.trigger_event == "enters" and "Land" in trigger_subject(unit.node):
            return [Signal("landfall", "you", "", "", tree.name, "high")]
    return []


def _sacrifice_outlets(tree: ConceptTree) -> list[Signal]:
    """A sac outlet / sac payoff (Ashnod's Altar, Mortician Beetle — CR 701.21).

    Mirrors ``_signals_ir`` triggers ~10472/10483 + effect outlet ~9226. Three
    inputs: (a) a ``sacrificed`` trigger (you sacrifice → reward); (b) an
    ``exploited`` trigger (CR 702.110); (c) a YOU-sac outlet — an activation COST
    (the cost IS the outlet, paid by the controller — Viscera Seer, Ashnod's Altar,
    Spawning Pit) OR a ``Sacrifice`` EFFECT whose sacrificed subject is explicitly
    YOU-controlled (Greven, Cabal Therapist). An effect that makes ANOTHER player
    sacrifice (``TargetPlayer`` — Diabolic Edict; ``null``/each — Barter in Blood,
    Fleshbag Marauder; ``ScopedPlayer`` — Sheoldred) is an edict → ``edict_makers``,
    excluded. A bare-self ("sacrifice this") or Land-only sac is excluded too. Scope
    "you".
    """
    for unit in tree.units:
        if unit.trigger_event in ("sacrificed", "exploited"):
            return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        # A COST is always paid by the controller → a you-sac outlet.
        for c in unit.costs:
            if c.concept == "sacrifice" and _is_you_sac_subject(c, cost=True):
                return [
                    Signal("sacrifice_outlets", "you", "", c.raw, tree.name, "high")
                ]
        # An EFFECT-role sac is an edict UNLESS its subject is explicitly you AND
        # the sac's OWN ability wrapper does not name a non-controller actor (the
        # per-effect player_scope guard catches the "each opponent sacrifices" edicts
        # phase mislabels as a you-controlled sacrificed subject — Grave Pact, Dictate
        # of Erebos, Baleful Beholder's modal mode arm).
        for c in unit.effects:
            if (
                c.concept == "sacrifice"
                and _is_you_sac_subject(c, cost=False)
                and not _sac_is_edict(unit, c.node)
            ):
                return [
                    Signal("sacrifice_outlets", "you", "", c.raw, tree.name, "high")
                ]
    return []


# player_scope actor tags that are NOT the ability's controller (an edict makes
# someone ELSE sacrifice; the controller never does). CR 701.21a / 800.4a.
_EDICT_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "All", "EachPlayer", "Each"}
)


def _sac_is_edict(unit: AbilityUnit, sac_node: TypedMirrorNode) -> bool:
    """Whether a ``Sacrifice`` EFFECT is an EDICT (someone ELSE sacrifices their own).

    Phase tags "each opponent / each other player sacrifices" edicts with a
    ``player_scope`` of ``Opponent`` / ``All`` on the ability WRAPPER that OWNS the
    sacrifice — a trigger's ``execute``, a sequential ``sub_ability``, or a modal
    ``mode_abilities`` arm (Baleful Beholder's "Each opponent sacrifices an
    enchantment") — while MISLABELING the sacrificed permanent's filter
    ``controller: You``. Per CR 701.21a a player can only sacrifice a permanent THEY
    control, so the effect is an EDICT, not a self-sac outlet. Reading the scope of
    the sacrifice's OWN wrapper (not a sibling's) rejects the edict (Grave Pact,
    Dictate of Erebos, Baleful Beholder's modal arm) while a genuine self-sac
    (Mycoloth's Devour — no non-controller scope on the sac's wrapper) still fires.
    """
    return effect_owner_player_scope(getattr(unit, "node", None), sac_node) in (
        _EDICT_ACTORS
    )


def _is_you_sac_subject(c: object, *, cost: bool) -> bool:
    """Whether a ``sacrifice`` concept-node is a YOU-sac outlet (not an edict).

    The sacrificed subject must be present and not Land-only (a bare-self / land sac
    is a different lane). For an EFFECT (``cost=False``) the sacrificed filter's
    ``controller`` must be explicitly ``You`` — a ``null``/``TargetPlayer``/
    ``ScopedPlayer`` controller is another player sacrificing (an edict). A COST is
    always paid by the controller, so its subject controller is not consulted.
    """
    subj = tuple(getattr(c, "subject", ()))
    if not subj or subj == ("Land",):
        return False
    if cost:
        return True
    target = getattr(getattr(c, "node", None), "target", None)
    return (
        getattr(target, "controller", None) == "You"
        if tag_of(target) == "Typed"
        else False
    )


def _is_upkeep_unit(unit: object) -> bool:
    """Whether ``unit`` is a beginning-of-upkeep trigger (recurring bleed gate)."""
    return getattr(getattr(unit, "node", None), "phase", None) == "Upkeep"


def _lifegain_matters(tree: ConceptTree) -> list[Signal]:
    """A life-gain payoff / significant self-life-loss engine (CR 119.3).

    Mirrors ``_signals_ir`` trigger ~10417 + draw-bleed ~10430 + self-loss ~7883.
    Three structural inputs: (a) a ``life_gained`` trigger (Archangel of Thune);
    (b) a ``dies`` trigger whose SAME ability carries BOTH a ``draw`` AND a self
    ``lose_life`` (the Necropotence draw-for-life engine — Taborax); (c) a
    significant self-life-LOSS engine — a ``lose_life`` effect with EXPLICIT self
    recipient that SCALES (dynamic amount — Dark Confidant) OR a recurring upkeep
    bleed ≥ 2 (Xathrid Demon). A one-shot fixed "you lose 2 life" rider is NOT an
    engine (excluded). Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "life_gained":
            return [Signal("lifegain_matters", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if unit.trigger_event == "dies" and unit.has_effect("draw"):
            for c in unit.effect_concepts("lose_life"):
                if explicit_recipient_scope(c.node) == "you":
                    return [
                        Signal("lifegain_matters", "you", "", "", tree.name, "high")
                    ]
    for unit in tree.units:
        for c in unit.effect_concepts("lose_life"):
            if explicit_recipient_scope(c.node) != "you":
                continue
            if amount_is_scaling(c.node) or (
                _is_upkeep_unit(unit) and amount_factor(c.node) >= 2
            ):
                return [Signal("lifegain_matters", "you", "", c.raw, tree.name, "high")]
    return []


def _blink_flicker(tree: ConceptTree) -> list[Signal]:
    """Exile-and-return-to-battlefield (Flickerwisp, Cloudshift — CR 400.7 / 603.6e).

    The structural-improvement marquee (granularity *a*). The old IR recovered a
    ``returns_to`` field post-hoc; the crosswalk reconstructs it from the sibling
    structure: ONE ability unit carrying BOTH a ``ChangeZone`` to Exile AND a
    ``ChangeZone`` to Battlefield whose target is the previously-exiled object
    (``ParentTarget`` / ``TrackedSet``). This excludes exile-as-resource with no
    return (Chrome Mox — exile only) and a battlefield put of a DIFFERENT object
    (Path to Exile — the searched land's target is ``Any``, not ``ParentTarget``).
    Scope "you".
    """
    for unit in tree.units:
        czs = [c for c in unit.effects if c.concept == "change_zone"]
        if not any(change_zone_dirs(c.node)[1] == "Exile" for c in czs):
            continue
        for c in czs:
            if change_zone_dirs(c.node)[1] != "Battlefield":
                continue
            tgt = tag_of(getattr(c.node, "target", None))
            if tgt in ("ParentTarget", "TrackedSet"):  # the SAME exiled object
                return [Signal("blink_flicker", "you", "", "", tree.name, "high")]
    return []


def _tokens_matter(tree: ConceptTree) -> list[Signal]:
    """Go-wide token payoff — an anthem or ETB-token trigger (CR 111.1).

    Mirrors ``_signals_ir`` anthem ~9831 + etb ~10373. Two arms read the ``Token``
    filter PREDICATE: (A) a pump / grant-keyword / set-P/T static whose affected
    filter carries ``Token`` AND controller you (Intangible Virtue) — a symmetric
    controller-any token anthem (Virulent Plague's -2/-2 hoser) is correctly scoped
    out; (B) an enters trigger whose watched subject carries ``Token`` AND
    controller you (Anointer Priest). Scope "you".
    """
    for unit in tree.units:
        anthem = [
            c for c in unit.statics if c.concept in ("pump", "grant_keyword", "set_pt")
        ]
        if (
            anthem
            and anthem[0].scope == "you"
            and "Token" in filter_predicates(getattr(unit.node, "affected", None))
        ):
            return [Signal("tokens_matter", "you", "", "", tree.name, "high")]
        if (
            unit.trigger_event == "enters"
            and "Token" in filter_predicates(getattr(unit.node, "valid_card", None))
            and trigger_subject_scope(unit.node) == "you"
        ):
            return [Signal("tokens_matter", "you", "", "", tree.name, "high")]
    return []


def _mana_accel(node: object) -> bool:
    """A ``Mana`` effect that produces MORE than one mana (factor>1 / variable)."""
    produced = getattr(node, "produced", None)
    if produced is None:
        return False
    count = getattr(produced, "count", None)
    if count is not None:
        if tag_of(count) == "Fixed":
            v = getattr(count, "value", None)
            return isinstance(v, int) and v > 1
        return True  # dynamic count (Cabal Coffers, Gaea's Cradle) → variable
    colors = getattr(produced, "colors", None)  # Fixed-colors shape (no count)
    return isinstance(colors, list) and len(colors) > 1


def _mana_fixing(node: object) -> bool:
    """A ``Mana`` effect that FIXES — a choice of ≥2 colors / any-color / any-type."""
    produced = getattr(node, "produced", None)
    if produced is None:
        return False
    if tag_of(produced) in _FIXING_PRODUCED_TYPES:
        return True
    opts = getattr(produced, "color_options", None)
    if isinstance(opts, list):
        return len(set(opts)) >= 2
    colors = getattr(produced, "colors", None)
    return isinstance(colors, list) and len(set(colors)) >= 2


def _ramp(tree: ConceptTree) -> list[Signal]:
    """Mana acceleration (Sol Ring, Command Tower — CR 106.1 / 605.1a / 305).

    Mirrors ``_signals_ir`` line ~8601. A ``Mana`` effect: a NONLAND ramp doer
    (rock / dork / ritual) is always acceleration → fire; a LAND splits — a
    basic-equivalent single-color / single-{C} tap is the MANA BASE (not ramp), but
    a land whose ramp is ACCELERATION (factor>1 / variable) OR FIXING (multi-color /
    any-color / any-type) IS ramp → fire. Scope "you".
    """
    is_land = tree.is_type("Land")
    for c in tree.effect_concepts("ramp"):
        if not is_land or _mana_accel(c.node) or _mana_fixing(c.node):
            return [Signal("ramp", "you", "", c.raw, tree.name, "high")]
    return []


# ── Batch 3 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────


def _typed_matters_lanes(filt: object) -> list[str]:
    """The artifacts/enchantments lane(s) for a YOUR-permanents filter (CR 702.41 /
    604.3). Mirrors ``_signals_ir._typed_matters_lanes``: a non-opponent filter naming
    Artifact / Enchantment in its CORE types fires that type's lane; a composite fires
    both. The SYMMETRIC-LIST GATE (CR 702.166a): a filter that ALSO carries the
    catch-all ``Permanent`` (Bargain's "an artifact, enchantment, or token") is a
    generic alt-cost, not a build-around — fire no lane.
    """
    if filt is None or filter_controller(filt) == "Opponent":
        return []
    cores = filter_core_types(filt)
    if "Permanent" in cores:
        return []
    return [lane for ct, lane in _TYPE_MATTERS_LANE.items() if ct in cores]


def _is_artifact_token_types(types: tuple[str, ...]) -> bool:
    """Whether a token's ``types`` name an Artifact — the Artifact card-type OR a
    predefined artifact-token subtype (Treasure/Clue/Food/… CR 205.3g), which phase
    carries with an empty card-type list.
    """
    if "Artifact" in types:
        return True
    return any(t.lower() in ARTIFACT_TOKEN_SUBTYPES for t in types)


def _generic_board_lanes(filt: object) -> list[str]:
    """artifacts/enchantments lane(s) for a GENERIC own-board anthem subject — a
    static buff/grant over your whole artifact/enchantment board (Padeem; Fountain
    Watch composite). Mirrors ``_signals_ir._generic_board_subject``: controller you,
    NO subtype (a subtyped buff is a narrower tribal care), Artifact/Enchantment in
    core types.
    """
    if filter_controller(filt) != "You" or filter_subtypes(filt):
        return []
    cores = filter_core_types(filt)
    if "Permanent" in cores:
        return []
    return [lane for ct, lane in _TYPE_MATTERS_LANE.items() if ct in cores]


def _artifacts_enchantments_matter(tree: ConceptTree) -> list[Signal]:
    """artifacts_matter / enchantments_matter — the broad type-payoff lanes (CR 301 /
    303). Mirrors ``_signals_ir`` six structural arms over the typed substrate:

    * **count operand** — a value scaling with your artifacts/enchantments
      (Affinity payoffs, "for each artifact you control");
    * **tutor** — a ``SearchLibrary`` whose CORE filter type is Artifact/Enchantment
      with NO subtype (Fabricate, Idyllic Tutor; Enlightened Tutor → both);
    * **generic-board anthem** — a static pump/grant over the whole own-board set
      (Padeem);
    * **token maker** — a ``make_token`` of an Artifact (incl. Treasure/Clue/Food
      resource subtypes) / Enchantment subject, scope you/any;
    * **sac payoff** — a ``Sacrifice`` of an Artifact/Enchantment subject (Atog-style
      fodder), non-opponent, with the Permanent-symmetric-list gate (CR 702.166a).

    The ``Permanent``-in-list gate drops the Bargain alt-cost over-fires.
    """
    out: list[str] = []
    for c in tree.iter_concepts():
        node = c.node
        # count operand (scaling value over your artifacts/enchantments)
        out.extend(_typed_matters_lanes(count_operand_filter(node)))
        if c.role != "effect":
            continue
        if c.concept == "tutor":
            sub = effect_filter(node)
            if sub is not None and not filter_subtypes(sub):
                out.extend(_typed_matters_lanes(sub))
        if c.concept == "make_token" and c.scope in ("you", "any"):
            types = c.subject
            if _is_artifact_token_types(types):
                out.append("artifacts_matter")
            if "Enchantment" in types:
                out.append("enchantments_matter")
    # SAC PAYOFF — your-fodder artifact/enchantment sac (Atog-style). Per-unit so the
    # edict guard applies: "each opponent sacrifices an artifact/enchantment" (Tribute
    # to the Wild, Mire in Misery, Vile Mutilator) is an EDICT phase mislabels with a
    # you-controlled subject; ``_sac_is_edict`` (per-effect player_scope, incl. modal
    # arms) rejects it (CR 701.21a). The sac subject must be genuinely you-controlled;
    # the Permanent-symmetric-list gate (CR 702.166a) drops the Bargain alt-cost.
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "sacrifice" or c.scope == "opponents":
                continue
            if _sac_is_edict(unit, c.node):
                continue
            sub = effect_filter(c.node)
            if sub is None or filter_controller(sub) != "You":
                continue
            cores = filter_core_types(sub)
            if "Permanent" in cores:
                continue
            if _is_artifact_token_types(c.subject):
                out.append("artifacts_matter")
            if "Enchantment" in cores:
                out.append("enchantments_matter")
    # generic-board static anthem/grant (Padeem) — read the static's affected filter
    for unit in tree.units:
        for c in unit.statics:
            if c.concept in ("pump", "grant_keyword", "set_pt"):
                out.extend(_generic_board_lanes(getattr(unit.node, "affected", None)))
    seen: set[str] = set()
    sigs: list[Signal] = []
    for lane in out:
        if lane not in seen:
            seen.add(lane)
            sigs.append(Signal(lane, "you", "", "", tree.name, "high"))
    return sigs


def _is_generic_creature_filter(filt: object) -> bool:
    """A GENERIC "creatures you control" filter (CR 604.3) — Creature in core types,
    NO subtype, controller you. A tribal (subtyped) filter is ``type_matters``, a
    different lane; a single-target removal/buff (controller any) fails the gate.
    """
    return (
        filter_controller(filt) == "You"
        and "Creature" in filter_core_types(filt)
        and not filter_subtypes(filt)
    )


def _creatures_matter(tree: ConceptTree) -> list[Signal]:
    """creatures_matter — a go-wide payoff scaling with / antheming the GENERIC
    creature population you control (CR 604.3). Mirrors ``_signals_ir`` line ~7686:

    * a **count operand** that is a generic creature count (Craterhoof's +X/+X, a
      "for each creature you control" value);
    * a **team anthem** — a top-level pump / grant-keyword / set-P/T static over the
      generic own-board creature set (Intangible-Virtue-class team buff).

    A SUBTYPE filter (Goblin King's "other Goblins") fails the no-subtype gate (it is
    ``type_matters``). A single-target removal/buff (controller any) never reaches
    here. The LOW regex floor (token-maker → creatures_matter) stays a ``live_only``
    mirror, not ported.
    """
    for c in tree.iter_concepts():
        if _is_generic_creature_filter(count_operand_filter(c.node)):
            return [Signal("creatures_matter", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.statics:
            if c.concept in ("pump", "grant_keyword", "set_pt") and (
                _is_generic_creature_filter(getattr(unit.node, "affected", None))
            ):
                return [Signal("creatures_matter", "you", "", c.raw, tree.name, "high")]
    return []


def _attack_tapped_matters(tree: ConceptTree) -> list[Signal]:
    """attack_matters / tapped_matters — a combat-state payoff over YOUR creatures
    (CR 508.4 attacking / 301 tapped). Mirrors ``_signals_ir`` line ~8259: an effect
    whose subject (or count operand) filter has controller you AND carries the
    ``Attacking`` / ``Tapped`` predicate ("attacking creatures you control get
    +1/+0"; "for each tapped creature you control"). The controller gate is
    load-bearing — "destroy target attacking creature" (controller any) is removal,
    not an aggro lane. Tapped is creature-gated (a tapped LAND bounce is mana, not
    aggro).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) != "You":
                continue
            preds = filter_predicates(filt)
            cores = filter_core_types(filt)
            if "Tapped" in preds and ("Creature" in cores or not cores):
                fire("tapped_matters", c.raw)
            if "Attacking" in preds:
                fire("attack_matters", c.raw)
    return out


def _any_counter_makers(tree: ConceptTree) -> list[Signal]:
    """any_counter_makers — a kind-AGNOSTIC counter DOER (CR 122.1 / 701.34a).
    Mirrors ``_signals_ir`` lines ~8548/8566: a ``proliferate`` (adds one counter of
    EACH kind already there), a counter MOVE (relocates counters — Bioshift, The
    Ozolith), OR a ``remove_counter`` with NO specified kind (Aether Snap, Hex
    Parasite). A KIND-SPECIFIC remove (fade/time/oil — a card spending its own niche
    counter) is excluded. Scope "you".
    """
    for c in tree.effect_concepts("proliferate"):
        return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("move_counters"):
        return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("remove_counter"):
        if not counter_kind(c.node):
            return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _minus_counters_matter(tree: ConceptTree) -> list[Signal]:
    """minus_counters_matter — a -1/-1 counter PLACEMENT maker (CR 122.1 / 122.6 /
    702.90 wither). Mirrors ``_signals_ir`` ``_COUNTER_KIND_KEYS['m1m1']`` on the
    ``place_counter`` maker arm: a ``PutCounter`` / ``PutCounterAll`` whose
    ``counter_type`` is ``M1M1`` (Hapatra, Blight Mamba). The kind gate is the whole
    discriminator vs +1/+1 (split-lane principle). persist/wither keyword arms stay
    keyword-derived (out of this typed arm). Scope "you".
    """
    for c in tree.effect_concepts("place_counter"):
        if counter_kind(c.node).upper() == "M1M1":
            return [
                Signal("minus_counters_matter", "you", "", c.raw, tree.name, "high")
            ]
    return []


def _plus_one_matters(tree: ConceptTree) -> list[Signal]:
    """plus_one_matters — a +1/+1 counter PAYOFF (CR 122.1). The structural arms
    (``_signals_ir`` ~8556 / ~8278): a ``move_counters`` whose kind is ``P1P1`` (a
    p1p1 move relocates the engine — Bioshift), OR a subject / count-operand filter
    carrying a ``Counters`` predicate of kind ``P1P1`` ("creatures you control with a
    +1/+1 counter", "for each creature with a +1/+1 counter on it" — Inspiring Call).
    The raw-``"+1/+1 counter"`` idiom arms stay ``live_only`` raw-fold mirrors. Scope
    "you".
    """
    for c in tree.effect_concepts("move_counters"):
        if counter_kind(c.node).upper() == "P1P1":
            return [Signal("plus_one_matters", "you", "", c.raw, tree.name, "high")]
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            if "P1P1" in counter_pred_kinds(filt):
                return [Signal("plus_one_matters", "you", "", c.raw, tree.name, "high")]
    return []


def _any_counter_matters(tree: ConceptTree) -> list[Signal]:
    """any_counter_matters — a kind-AGNOSTIC counter PAYOFF (CR 122.1). The structural
    arm only (``_signals_ir`` ~9694 arm b): a subject / count-operand filter carrying
    a ``Counters`` predicate of the kind-agnostic ``Any`` form ("for each counter on
    ~", "a permanent with a counter on it"). The amount-raw "counter"-discriminator
    arm (a) is a documented ``live_only`` raw-fold (phase drops the counted-object).
    Scope "you".
    """
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            if "Any" in counter_pred_kinds(filt):
                return [
                    Signal("any_counter_matters", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _chooses_opponent(node: object) -> bool:
    """Whether a ``Choose`` effect picks an OPPONENT (the give-away beneficiary).

    Fateful Handoff / Rogue Skycaptain resolve "an opponent gains control of it" as
    a ``Choose`` of ``choice_type: Opponent`` feeding the gain-control's
    ``ParentTarget``. A directional / random ``Choose`` (Order of Succession's
    Left/Right, Scrambleverse's random Player) is instead caught by the player_scope
    arm; only the literal Opponent choice is read here.
    """
    return getattr(node, "choice_type", None) == "Opponent"


def _gives_control_to_other(node: TypedMirrorNode, unit: AbilityUnit) -> bool:
    """Whether a gain-control effect hands control to a NON-you player (CR 110.2 /
    603.10d) — a give-away / chaos swap, not a you-theft payoff. The beneficiary of a
    control change is structural; three typed markers say "not you":

    * a MASS give-away of your OWN board — ``GainControlAll`` whose target is
      ``controller: You`` ("target opponent gains control of all permanents YOU
      control": Sky Swallower). Restricted to the *mass* form: a single
      ``GainControl`` of ``controller: You`` is a phase MISLABEL of "target creature
      that <opponent> controls" (Nihiloor), a genuine you-theft, not a give-away;
    * a ``Choose`` of an OPPONENT in the unit feeding the gain-control's ``SelfRef`` /
      ``ParentTarget`` ("an opponent gains control of it / this" — Fateful Handoff,
      Rogue Skycaptain, Wishclaw Talisman, Rainbow Vale). Gaining control of THIS
      card / the just-targeted thing for an opponent is never a you-theft;
    * a non-controller ``player_scope`` on the gain-control's OWN ability wrapper
      ("each player gains control …": Order of Succession, Inniaz, Scrambleverse,
      Aminatou) — read per-effect (:func:`effect_owner_player_scope`), so an unrelated
      each-player action sharing the unit (Nihiloor's per-opponent tap loop) does NOT
      veto a genuine you-theft.
    """
    if tag_of(node) == "GainControlAll":
        sub = effect_filter(node)
        if sub is not None and filter_controller(sub) == "You":
            return True
    if tag_of(effect_filter(node)) in ("SelfRef", "ParentTarget") and any(
        tag_of(c.node) == "Choose" and _chooses_opponent(c.node) for c in unit.effects
    ):
        return True
    return effect_owner_player_scope(getattr(unit, "node", None), node) in (
        _EDICT_ACTORS
    )


def _gain_control(tree: ConceptTree) -> list[Signal]:
    """gain_control — YOU-THEFT (you take control of a permanent you don't own,
    CR 110.2 / 720). Mirrors ``_signals_ir`` line ~9270: a ``GainControl`` /
    ``GainControlAll`` effect (Threaten, Control Magic's reset-free theft), EXCLUDING:

    * a control-RESET — an ``Owned`` predicate on the target ("each player gains
      control of permanents they own", Brooding Saurian, CR 110.2a);
    * a GIVE-AWAY / chaos swap whose new controller is NOT you
      (:func:`_gives_control_to_other`): "target opponent gains control of all
      permanents you control" (Sky Swallower), "an opponent gains control of it"
      (Fateful Handoff, Rogue Skycaptain), "each player gains control …" (Order of
      Succession, Inniaz, Scrambleverse, Aminatou). The beneficiary being an opponent
      is structural (CR 110.2 / 603.10d), so these are NOT a you-gain payoff.

    A donate (``GiveControl`` — you give your OWN away) is a SEPARATE phase tag,
    never reaching this arm. A ``Control Magic`` enchant rides a ``ChangeController``
    STATIC modification (the new controller is you). Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("gain_control"):
            sub = effect_filter(c.node)
            if sub is not None and "Owned" in filter_predicates(sub):
                continue  # control-RESET, not theft
            if _gives_control_to_other(c.node, unit):
                continue  # give-away — the new controller is an opponent, not you
            return [Signal("gain_control", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.statics:
            if tag_of(c.node) == "ChangeController":
                return [Signal("gain_control", "you", "", c.raw, tree.name, "high")]
    return []


def _resource_token_makers(tree: ConceptTree) -> list[Signal]:
    """treasure_makers / food_makers / clue_makers / blood_makers — a predefined
    artifact-token maker (CR 111.10 / 205.3g / 701.16a investigate). Mirrors
    ``_signals_ir`` ~12297: a ``make_token`` whose token subtype is Treasure / Food /
    Clue / Blood, scope you/each; ``Investigate`` is a first-class Clue maker. The
    structural read improves on the raw-fallback (the resource subtype rides the
    token's typed ``types``). Scope "you".
    """
    keys = {
        "Treasure": "treasure_makers",
        "Food": "food_makers",
        "Clue": "clue_makers",
        "Blood": "blood_makers",
    }
    out: list[str] = []
    for c in tree.effect_concepts("make_token"):
        if c.scope not in _YOU_EACH:
            continue
        for sub, key in keys.items():
            if sub in c.subject:
                out.append(key)
    if tree.has_effect("investigate"):
        out.append("clue_makers")
    seen: set[str] = set()
    sigs: list[Signal] = []
    for key in out:
        if key not in seen:
            seen.add(key)
            sigs.append(Signal(key, "you", "", "", tree.name, "high"))
    return sigs


def _mill_makers(keywords: frozenset[str], name: str) -> list[Signal]:
    """mill_makers — a FIELD-LOOKUP on the Scryfall ``Mill`` keyword, NOT a structural
    port (ADR-0027 / CR 701.17a). The live survivor (``_signals_ir``
    ``_IR_KEYWORD_MAP['mill']``) was DELIBERATELY moved to the keyword array to drop
    three phase mislabels of the ``Mill`` effect category — Bone Dancer (opp-GY →
    battlefield REANIMATION), Scroll Rack (library↔hand swap), Soldevi Digger (GY →
    library bottom) — none a CR 701.17a mill, none carrying the ``Mill`` keyword. Every
    genuine mill DOES carry it (0 keyword-less commander-legal fires), so the keyword
    route reproduces the deleted regex producer exactly. Scope "any" (self- or
    opponent-mill — the deleted preset's scope).
    """
    if any(k.lower() == "mill" for k in keywords):
        return [Signal("mill_makers", "any", "", "", name, "high")]
    return []


def _proliferate_makers(tree: ConceptTree) -> list[Signal]:
    """proliferate_makers — a proliferate DOER (CR 701.34a). A native ``Proliferate``
    effect (Atraxa, Evolution Sage; the keyword-less proliferators the Scryfall regex
    missed). The ``station`` keyword is a proliferate_matters payoff, not a doer —
    routed elsewhere. Scope "you".
    """
    for c in tree.effect_concepts("proliferate"):
        return [Signal("proliferate_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _energy_makers(tree: ConceptTree) -> list[Signal]:
    """energy_makers — an energy producer (CR 107.14 / 122.1). A ``GainEnergy`` effect
    (Aetherworks Marvel, Dynavolt Tower). phase models energy as a first-class effect
    (NOT a kind-dropped ``GivePlayerCounter``), so the structural read is clean. Scope
    "you".
    """
    for c in tree.effect_concepts("gain_energy"):
        return [Signal("energy_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _voltron_makers(tree: ConceptTree) -> list[Signal]:
    """voltron_makers — gear-attaching / Equipment-Aura tutor (CR 301.5 / 303.4 /
    701.23). Mirrors ``_signals_regex._detect_voltron_maker_ir``: (a) an ``Attach``
    effect moving ANOTHER typed Equipment/Aura onto a creature (the ``attachment``
    field is a separate typed gear, NOT absent — Kor Outfitter, Balan), scope not
    opponent; (b) a ``SearchLibrary`` whose searched filter SUBTYPE is Equipment/Aura
    (Stoneforge Mystic, Godo, Three Dreams). Self-attach (Bonesplitter's equip —
    ``attachment`` absent) is the payload, not a maker. Scope "you".
    """
    for c in tree.effect_concepts("attach"):
        if c.scope == "opponents":
            continue
        attachment = getattr(c.node, "attachment", None)
        if attachment is not None and (
            {s.lower() for s in filter_subtypes(attachment)} & _VOLTRON_SUBTYPES
        ):
            return [Signal("voltron_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("tutor"):
        sub = effect_filter(c.node)
        if sub is not None and (
            {s.lower() for s in filter_subtypes(sub)} & _VOLTRON_SUBTYPES
        ):
            return [Signal("voltron_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _voltron_matters(tree: ConceptTree) -> list[Signal]:
    """voltron_matters — an Aura/Equipment PAYOFF build-around (CR 301.5c / 303).
    Mirrors ``_signals_regex._detect_voltron_payoff_ir``: (a) a ``cast_spell`` trigger
    whose watched subject SUBTYPE is Equipment/Aura (Sram, Kor Spiritdancer); (b) an
    attachment-STATE predicate (``AttachedToRecipient`` / ``HasAnyAttachmentOf`` — "for
    each Aura attached to it", "enchanted or equipped creatures" — Reyav, Koll) on any
    effect / count-operand subject. NOT the bare subtype on an effect subject (covers
    Aura hate), NOT an ``EquippedBy`` payload-pump. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "cast_spell":
            vc = getattr(unit.node, "valid_card", None)
            if {s.lower() for s in filter_subtypes(vc)} & _VOLTRON_SUBTYPES:
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # an attachment-STATE watched subject ("enchanted or equipped creature you
        # control attacks" — Reyav) carries the predicate on the trigger's valid_card.
        for fname in ("valid_card", "valid_source"):
            wf = getattr(unit.node, fname, None)
            if wf is not None and set(filter_predicates(wf)) & _ATTACHMENT_PREDS:
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            for filt in (effect_filter(c.node), count_operand_filter(c.node)):
                if filt is not None and (
                    set(filter_predicates(filt)) & _ATTACHMENT_PREDS
                ):
                    return [
                        Signal("voltron_matters", "you", "", c.raw, tree.name, "high")
                    ]
    return []


# ── Batch 4 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────


def _gy_scope(scope: str) -> str:
    """The graveyard lane scope (CR 400.7): an EXPLICIT opponent's-GY interaction →
    ``opponents`` (GY-hate / opponent mill); else the self-graveyard default ``you``.
    There is no ``…/any`` GY avenue. A structurally-"each" / "any" effect (a recursion
    TARGET whose card-in-a-graveyard filter carries no player controller — Reanimate's
    "creature card from a graveyard" — which the overlay scopes ``each``) maps to
    ``you``: it enables YOUR self-graveyard build, matching the live ``_gy_scope`` else
    branch (CR 701.17a)."""
    return "opponents" if scope == "opponents" else "you"


def _graveyard_makers(tree: ConceptTree) -> list[Signal]:
    """graveyard_makers — the card PERFORMS a graveyard interaction (CR 404 /
    603.6e / 701.17a). Structural arms over the typed substrate:

    * a ``ChangeZone`` reanimation (``(Graveyard, Battlefield)``) or recursion
      (``(Graveyard, Hand)``) — the typed ``change_zone_dirs`` reads the origin
      HONESTLY, so an exile-return (origin=Exile — Banisher Priest) is excluded
      structurally without the live path's ``_EXILE_RETURN_RE`` (the substrate is
      strictly better here);
    * a ``Mill`` effect (self / any / symmetric scope) — self-mill fills your own
      graveyard.

    The cast-from-GY keyword family (flashback / escape / …) rides a keyword
    field-lookup in :func:`extract_crosswalk_signals` (no effect node to read).
    The broad zone-tag-recovered arms (GY-cast grants, GY-hate exile, ``in:graveyard``
    bounce) the lossy IR reconstructed from recovered zone strings are a documented
    ``live_only`` residue (the typed substrate exposes zones only on ``ChangeZone``).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("graveyard_makers", scope, "", raw, tree.name, "high"))

    for c in tree.effect_concepts("change_zone"):
        origin, dest = change_zone_dirs(c.node)
        if origin == "Graveyard" and dest in ("Battlefield", "Hand"):
            fire(_gy_scope(c.scope), c.raw)
    for c in tree.effect_concepts("mill"):
        # The ``Mill`` effect carries a ``destination``; only a Graveyard destination
        # is a CR-701.17a mill (Stitcher's Supplier). A library↔hand swap phase
        # MISLABELS as ``Mill`` with destination=Hand (Scroll Rack) — a phase-parse
        # bug [P2], excluded structurally by the dest gate.
        if getattr(c.node, "destination", None) != "Graveyard":
            continue
        if c.scope in ("you", "any", "each"):
            fire(_gy_scope(c.scope), c.raw)
    return out


def _graveyard_matters(tree: ConceptTree) -> list[Signal]:
    """graveyard_matters — the cares-about PAYOFF (CR 404 / 701.17a). The cleanly
    typed arm: a trigger watching cards ENTERING a graveyard from a non-battlefield
    zone, or LEAVING a graveyard (Syr Konrad-class), read off the trigger's typed
    ``origin`` / ``destination``. The battlefield→graveyard ``dies`` movement is a
    death payoff (a different lane), excluded. The dredge / delve / scavenge keyword
    payoffs ride a keyword field-lookup. The count-operand-over-cards-in-a-graveyard
    arm + the delirium/threshold CONDITION arm depend on zone tags the substrate does
    not expose uniformly, so a LOW reproduce rate here is EXPECTED (documented
    ``live_only`` residue), not a gap.
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        node = unit.node
        origin = getattr(node, "origin", None)
        dest = getattr(node, "destination", None)
        gy_arrival = dest == "Graveyard" and origin not in ("Battlefield", None)
        gy_departure = origin == "Graveyard"
        if gy_arrival or gy_departure:
            sc = _gy_scope(trigger_subject_scope(node))
            return [Signal("graveyard_matters", sc, "", "", tree.name, "high")]
    return []


def _fight_makers(tree: ConceptTree) -> list[Signal]:
    """fight_makers — a fight / bite DOER (CR 701.14a). Any ``Fight`` effect (Prey
    Upon, Ulvenwald Tracker). Scope "you" (the lane convention). The Aftermath DFC
    back-face fallback phase never projects stays a ``live_only`` byte-mirror.
    """
    for c in tree.effect_concepts("fight"):
        return [Signal("fight_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _goad_makers(tree: ConceptTree) -> list[Signal]:
    """goad_makers — a goad DOER (CR 701.15a). A ``Goad`` / ``GoadAll`` effect
    (Disrupt Decorum, Bloodthirster). Pure political force directed AT opponents →
    scope "opponents". The ``force_attack``→goad single-target bridge
    (``_GOAD_STYLE_FORCE``) stays a ``live_only`` survivor.
    """
    for c in tree.effect_concepts("goad"):
        return [Signal("goad_makers", "opponents", "", c.raw, tree.name, "high")]
    return []


def _regenerate_makers(tree: ConceptTree) -> list[Signal]:
    """regenerate_makers — a regeneration shield (CR 701.19a). A ``Regenerate`` effect
    (River Boa, Troll Ascetic). A "can't be regenerated" clause is the INVERSE (a flag
    on a ``Destroy``, NOT a ``Regenerate`` effect — Pongify), so it never reaches here.
    Scope "you".
    """
    for c in tree.effect_concepts("regenerate"):
        return [Signal("regenerate_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _lifeloss_scope(unit: AbilityUnit, node: TypedMirrorNode) -> str:
    """The lifeloss-maker scope split (CR 119.3): a self-loss ("you lose N") → you; a
    drain ("each opponent / its controller / that player loses N") → opponents.

    Direction comes from the ``LoseLife`` node's RECIPIENT, read structurally
    (:func:`lifeloss_recipient_scope`) — NOT from ``trigger_scope``, which phase
    MIS-scopes to ``you`` for an ability triggered off an OPPONENT's object (Archfiend
    of the Dross, Ashenmoor Liege — phase bug [P5]). When the node carries no
    recipient (Gray Merchant — the "each opponent loses" lives as ``player_scope`` on
    the trigger wrapper), reads the wrapper actor that OWNS this effect
    (:func:`effect_owner_player_scope`); a bare self-loss with no wrapper actor (Agent
    Venom, Dark Confidant) stays ``you``."""
    rs = lifeloss_recipient_scope(node)
    if rs is not None:
        return rs
    owner = effect_owner_player_scope(getattr(unit, "node", None), node)
    if owner in _EDICT_ACTORS:
        return "opponents"
    return "you"


def _lifeloss_makers(tree: ConceptTree) -> list[Signal]:
    """lifeloss_makers — the card PERFORMS life loss (CR 119.3). (a) a ``LoseLife``
    effect, scope-split self/drain; (b) a pay-life ACTIVATION COST that buys a
    non-ramp effect (Erebos's ``Pay 2 life`` → draw) — the card pays/loses life. The
    cost arm is gated HARD against the lane's land trap: a Land card (Horizon Canopy's
    ``Pay 1 life: draw``) is excluded (CR 118.8), and a paylife ability whose only
    effect is mana fixing (``ramp``) is a painland, excluded by the non-ramp gate.
    Combat damage (CR 120) is a sibling category that never tags ``LoseLife``.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("lifeloss_makers", scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.effect_concepts("lose_life"):
            fire(_lifeloss_scope(unit, c.node), c.raw)
    if not tree.is_type("Land"):
        for unit in tree.units:
            paylife = any(cost_has_paylife(cc.node) for cc in unit.costs)
            non_ramp = any(e.concept != "ramp" for e in unit.effects)
            if paylife and non_ramp:
                fire("you", "")
    return out


def _lifeloss_matters(tree: ConceptTree) -> list[Signal]:
    """lifeloss_matters — the life-loss PAYOFF (CR 119.3). A ``life_lost`` trigger
    (Exquisite Blood, Vilis): an opp-scoped watcher is the drain payoff (opponents),
    else you. The ``spectacle`` keyword (a "cast cheaper if an opponent lost life"
    condition stripped to reminder text — no structural ``LoseLife``) rides a keyword
    field-lookup in :func:`extract_crosswalk_signals`.
    """
    for unit in tree.units:
        if unit.trigger_event == "life_lost":
            sc = "opponents" if trigger_scope(unit.node) == "opponents" else "you"
            return [Signal("lifeloss_matters", sc, "", "", tree.name, "high")]
    return []


def _edict_scope(owner_tag: str | None) -> str:
    """An edict actor tag → lane scope (CR 701.21a). An opponent actor → opponents; a
    symmetric each-player actor → each (mirrors ``_ir_scope`` opp/each)."""
    if owner_tag in ("Opponent", "Opponents", "EachOpponent"):
        return "opponents"
    return "each"


def _scoped_player_scope(unit: AbilityUnit | None) -> str | None:
    """Resolve a ``ScopedPlayer`` sacrifice controller to a lane scope via the owning
    trigger's turn constraint (CR 701.21a).

    phase tags a triggered "that player sacrifices" edict ``controller: ScopedPlayer``
    — the scoped player is whoever the trigger references, which the constraint
    disambiguates: ``OnlyDuringOpponentsTurn`` (Sheoldred — "each opponent's upkeep")
    → opponents; no constraint (Braids, Cabal Minion; Smokestack — "each player's
    upkeep, that player sacrifices") → each, a SYMMETRIC self-inclusive wrath that
    hits YOU too (matching the live edict_makers /each scope, NOT a clean opponent
    edict); ``OnlyDuringYourTurn`` (a "your upkeep, you sacrifice" self-sac) → ``None``
    (a you-sac, not an edict). A non-trigger ScopedPlayer keeps the opponent default.
    """
    if unit is None or getattr(unit, "origin", None) != "trigger":
        return "opponents"
    c = trigger_turn_constraint(unit.node)
    if c == "OnlyDuringOpponentsTurn":
        return "opponents"
    if c == "OnlyDuringYourTurn":
        return None
    return "each"


def _sac_actor_scope(
    node: TypedMirrorNode, unit: AbilityUnit | None = None
) -> str | None:
    """The edict scope of a ``Sacrifice`` effect from its sacrificed filter's
    CONTROLLER (CR 701.21a — a player only sacrifices a permanent THEY control, so the
    controller IS the forced actor). An opponent / target-player controller →
    opponents; an each/all-player controller → each; a ``ScopedPlayer`` ("that player
    sacrifices") resolves by the trigger's turn constraint
    (:func:`_scoped_player_scope`) so a symmetric each-player upkeep edict (Braids,
    Smokestack) scopes /each, not /opponents; a ``You`` controller (a you-sac outlet —
    Mycoloth) or none (an unscoped/bare-self sac) → ``None`` (not an edict via this
    arm)."""
    ctrl = filter_controller(effect_filter(node))
    if ctrl == "ScopedPlayer":
        return _scoped_player_scope(unit)
    if ctrl in ("Opponent", "Opponents", "EachOpponent", "TargetPlayer"):
        return "opponents"
    if ctrl in ("All", "EachPlayer", "Each"):
        return "each"
    return None


def _edict_makers(tree: ConceptTree) -> list[Signal]:
    """edict_makers — a FORCED player sacrifice (CR 701.21a / 800.4a). The INVERSE of
    the ``sacrifice_outlets`` you-sac gate. Two structural tells, each reading the
    sacrifice's OWN node/wrapper (never a sibling's):

    * the wrapper ``player_scope`` names a non-controller actor
      (:func:`_sac_is_edict`, modal arms included) — phase MISLABELS the sacrificed
      permanent ``controller: You`` while tagging the wrapper ``player_scope:
      Opponent`` (Grave Pact, Dictate of Erebos), so the wrapper is load-bearing;
    * the sacrificed filter's CONTROLLER is itself a non-you player
      (:func:`_sac_actor_scope`) — "target player sacrifices a creature" carries
      ``controller: TargetPlayer`` (Diabolic Edict); a triggered "that player
      sacrifices" carries ``controller: ScopedPlayer``, scoped by the trigger's turn
      constraint so an "each opponent's upkeep" edict is /opponents (Sheoldred) but a
      symmetric "each player's upkeep" wrath is /each (Braids, Smokestack — it hits
      YOU too, so it is not a clean opponent edict).

    A you-sac outlet (Mycoloth — ``controller: You``; Viscera Seer — a COST, never an
    effect) is excluded.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str | None, raw: str) -> None:
        if scope and scope not in seen:
            seen.add(scope)
            out.append(Signal("edict_makers", scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "sacrifice":
                continue
            owner = effect_owner_player_scope(getattr(unit, "node", None), c.node)
            if owner in _EDICT_ACTORS:
                fire(_edict_scope(owner), c.raw)
            else:
                fire(_sac_actor_scope(c.node, unit), c.raw)
    return out


# Actor tags that name an OPPONENT or a targeted player (never the controller). A
# land sacrifice directed at one of these is land DESTRUCTION / an opponent edict
# on lands (Yawning Fissure, Din of the Fireherd, Epicenter), NOT a self land-sac
# engine (CR 701.21a). ``ScopedPlayer`` ("that player") is deliberately ABSENT — it
# is symmetric (each player, including you) UNLESS the owning trigger is
# OnlyDuringOpponentsTurn, handled separately. The ``All`` / ``EachPlayer`` / ``Each``
# actors are absent too: they include you (Smallpox, Death Cloud, Keldon Firebombers,
# Pox — you sac your own lands), keeping the lane.
_OPP_SAC_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "TargetPlayer"}
)


def _sac_targets_opponent(unit: AbilityUnit, node: TypedMirrorNode) -> bool:
    """Whether a land ``Sacrifice`` in ``unit`` is directed at an OPPONENT (CR
    701.21a) — the opponent land-edict the self-land-sac lane must exclude.

    Works around two phase mislabels the land-sac node's own filter controller can't
    be trusted through: [P1] Yawning Fissure ("Each opponent sacrifices a land") —
    phase tags the Sacrifice filter ``controller: You`` but hangs ``player_scope:
    Opponent`` on the wrapper; [P3] Din of the Fireherd (a chained "then sacrifices a
    land of their choice") — the chained land Sacrifice drops its own controller, but
    its parent "target opponent sacrifices a creature" carries ``controller:
    TargetPlayer``. Reading BOTH the wrapper ``player_scope`` and every sibling
    Sacrifice's filter controller catches the opponent direction the mislabeled node
    hides. A ``ScopedPlayer`` ("that player sacrifices") counts only when the trigger
    is ``OnlyDuringOpponentsTurn`` (a Sheoldred-style "each opponent's upkeep" edict)
    — a symmetric "each player's upkeep" land sac (Mana Vortex, Stoneshaker Shaman)
    and the ``All`` / ``EachPlayer`` wraths (Smallpox, Keldon Firebombers, Pox) are
    NOT opponent-directed (you sac your own lands too)."""
    owner = effect_owner_player_scope(getattr(unit, "node", None), node)
    if owner in _OPP_SAC_ACTORS:
        return True
    opp_scoped = (
        getattr(unit, "origin", None) == "trigger"
        and trigger_turn_constraint(unit.node) == "OnlyDuringOpponentsTurn"
    )
    for c in unit.effects:
        if c.concept != "sacrifice":
            continue
        ctrl = filter_controller(effect_filter(c.node))
        if ctrl in _OPP_SAC_ACTORS or (ctrl == "ScopedPlayer" and opp_scoped):
            return True
    return False


def _land_sacrifice_makers(tree: ConceptTree) -> list[Signal]:
    """land_sacrifice_makers — a SELF land-sacrifice engine (CR 701.21 / 305.6): a
    ``Sacrifice`` effect OR cost whose subject is LAND-ONLY where YOU sacrifice your
    OWN lands (Zuran Orb's "Sacrifice a land:", Scapeshift; symmetric "each player
    sacrifices a land" — Smallpox, Death Cloud — counts, you sac too). The Land-only
    branch ``sacrifice_outlets`` deliberately EXCLUDES
    (:func:`_is_you_sac_subject` returns False on a ``("Land",)`` subject), so it is a
    clean complement; a mixed "creature or land" sac (Reprocess) is
    ``sacrifice_outlets``, not this. An OPPONENT land-edict (land destruction —
    Yawning Fissure "each opponent sacrifices a land", Din of the Fireherd "target
    opponent ... sacrifices a land") is NOT a self engine and is gated out by
    :func:`_sac_targets_opponent`, working around phase's [P1]/[P3] direction
    mislabels.
    """
    for unit in tree.units:
        for c in (*unit.effects, *unit.costs):
            if (
                c.concept == "sacrifice"
                and tuple(c.subject) == ("Land",)
                and c.scope != "opponents"
                and not _sac_targets_opponent(unit, c.node)
            ):
                return [
                    Signal("land_sacrifice_makers", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _debuff_makers(tree: ConceptTree) -> list[Signal]:
    """debuff_makers — a -X/-X / -1/-1 enabler (CR 613.4c / 704.5g). Three anchors:

    * a NEGATIVE ``Pump`` / ``PumpAll`` EFFECT (Bile Blight's -3/-3) — scope "any";
    * a ``-1/-1`` (``M1M1``) counter PLACEMENT whose scope is NOT you (an opponent /
      symmetric debuff — Black Sun's Zenith), distinct from the you-maker
      ``minus_counters_matter`` — scope "any";
    * a mass base-toughness SET ≤ 2 on opponents / symmetric creatures (Humility,
      Overwhelming Splendor) — a 0-toughness enabler — scope "you".

    A scope-you base-P/T set is a BUFF (Biomass Mutation), excluded; a single-target
    neutralize (scope any) is removal, not a -1/-1 payoff.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("debuff_makers", scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.effects:
            if c.concept == "pump" and pump_is_negative(c.node):
                fire("any", c.raw)
            if (
                c.concept == "place_counter"
                and counter_kind(c.node).upper() == "M1M1"
                and c.scope != "you"
            ):
                fire("any", c.raw)
        for c in unit.statics:
            if c.concept != "set_pt" or c.scope not in ("opponents", "each"):
                continue
            # A single-Aura / single-target shrink (Darksteel Mutation, Frogify —
            # affected carries an ``EnchantedBy`` / attachment predicate) is a
            # neutralize, NOT a mass -1/-1 enabler (checklist #6 — the live path
            # scopes it "any" via its single-target read; the overlay scopes the
            # controller-less Aura filter "each", so the attachment predicate is the
            # discriminator). A genuine mass shrink (Humility — "all creatures") carries
            # no attachment predicate.
            aff = getattr(unit.node, "affected", None)
            if set(filter_predicates(aff)) & _DEBUFF_SINGLE_AURA_PREDS:
                continue
            v = mod_value(c.node)
            if v is not None and v <= 2:
                fire("you", c.raw)
    return out


def _lure_makers(tree: ConceptTree) -> list[Signal]:
    """lure_makers — a forced-block / lure requirement (CR 509.1c). A
    ``MustBeBlockedByAll`` / ``MustBeBlocked`` static mode (Lure, Nemesis Mask),
    conferred via an ``AddStaticMode`` modification (:func:`node_lure_mode`). A
    single-target ``ForceBlock`` (Academic Dispute) is a narrower provoke-style effect
    that does NOT carry the mode, correctly excluded. Scope "you".
    """
    for unit in tree.units:
        if node_lure_mode(unit.node):
            return [Signal("lure_makers", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            if node_lure_mode(c.node):
                return [Signal("lure_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _copy_clone(tree: ConceptTree) -> list[Signal]:
    """copy_permanent / clone_makers / token_copy_makers — the copy cluster (CR 707 /
    701.36). Three structural surfaces (Dan's clone-vs-token-copy boundary):

    * a ``BecomeCopy`` effect — the copied filter (its ``target``) drives the lane: a
      generic ``Permanent`` copy (Crystalline Resonance) fans to ``copy_permanent`` +
      ``clone_makers``; a ``Creature`` core type or a resolved creature SUBTYPE
      (Sunfrill Imitator's Dinosaur) → ``clone_makers``;
    * a ``CopyTokenOf`` / ``CopyTokenBlockingAttacker`` / ``Populate`` effect →
      ``token_copy_makers``. The Embalm / Eternalize / … reminder self-copies carry a
      ``SelfRef`` target (a copy of THIS card, not a copy-others payoff — Adorned
      Pouncer) and are EXCLUDED structurally, the discriminator fully in the IR.

    The token-doubling cross-open (Doubling Season forks copy-tokens) and the
    clone-self idiom veto (Progenitor Mimic) stay ``live_only``. Scope "you".
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.effect_concepts("become_copy"):
        sub = effect_filter(c.node)
        cores = filter_core_types(sub) if sub is not None else ()
        if "Permanent" in cores:
            fire("copy_permanent", c.raw)
            fire("clone_makers", c.raw)
        if "Creature" in cores:
            fire("clone_makers", c.raw)
        subtypes = filter_subtypes(sub) if sub is not None else ()
        if any(_resolve_subject(w, CREATURE_SUBTYPES) for w in subtypes):
            fire("clone_makers", c.raw)
    for unit in tree.units:
        for c in unit.effects:
            if c.concept not in ("copy_token", "populate"):
                continue
            if c.scope not in _YOU_EACH:
                continue
            tgt = getattr(c.node, "target", None)
            if c.concept == "copy_token" and tag_of(tgt) == "SelfRef":
                continue  # a copy of THIS card (Embalm / Eternalize / Squad / Myriad)
            fire("token_copy_makers", c.raw)
    return out


def _connive_makers(tree: ConceptTree) -> list[Signal]:
    """connive_makers — a connive DOER (CR 701.50a). A ``Connive`` effect (Shipwreck
    Sifters, Old Rutstein; the granted Aura form — Security Bypass — also carries a
    structural ``Connive`` effect, so no keyword field-lookup is needed). A pure
    connive-STATE payoff is a different lane. Scope "you".
    """
    for c in tree.effect_concepts("connive"):
        return [Signal("connive_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _explore_makers(tree: ConceptTree) -> list[Signal]:
    """explore_makers — an explore DOER (CR 701.44a). An ``Explore`` / ``ExploreAll``
    effect (Merfolk Branchwalker, Jadelight Ranger). Read STRUCTURALLY only — the
    Scryfall ``Explore`` keyword array ALSO tags the explore PAYOFF Wildgrowth Walker
    ("whenever a creature you control explores"), which has NO ``Explore`` effect
    (only a watch-trigger), so a keyword field-lookup would over-fire (CR 701.44a — the
    maker performs the explore; the payoff merely watches). Scope "you".
    """
    for c in tree.effect_concepts("explore"):
        return [Signal("explore_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _suspect_makers(tree: ConceptTree) -> list[Signal]:
    """suspect_makers — a suspect DOER (CR 701.60a). A ``Suspect`` effect (Nelly
    Borca, Case of the Stashed Skeleton). A ``Suspected`` PROPERTY reference (the
    payoff — "whenever a suspected creature …") is a distinct phase tag, never an
    ``Suspect`` effect, so it is correctly excluded. Scope "you".
    """
    for c in tree.effect_concepts("suspect"):
        return [Signal("suspect_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _combat_damage_to_opp(tree: ConceptTree) -> list[Signal]:
    """combat_damage_to_opp — a "deals combat damage to a player" trigger (CR 510.1c).
    A ``DamageDone`` trigger whose ``damage_kind`` is ``CombatOnly`` AND whose
    recipient (``valid_target``) reaches a PLAYER (Coastal Piracy, Bident of Thassa).
    A creature recipient (Ohran Viper's first trigger) is ``combat_damage_to_creature``
    (a different lane); a non-combat "deals damage" trigger never reaches here. The
    quoted-in-an-activated-ability text-fold residue stays ``live_only``. Scope
    "opponents".
    """
    for unit in tree.units:
        node = unit.node
        if unit.trigger_event != "deals_damage":
            continue
        if getattr(node, "damage_kind", None) != "CombatOnly":
            continue
        if damage_recipient_is_player(getattr(node, "valid_target", None)):
            return [
                Signal("combat_damage_to_opp", "opponents", "", "", tree.name, "high")
            ]
    return []


# ── Batch 5 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# Condition-node tags the batch-5 ``*_matters`` payoff lanes gate on (whole-card,
# read via :func:`condition_tags`). A designation/state PAYOFF ("if you're the
# monarch", "if you've completed a dungeon", "as long as ~ is the Ring-bearer")
# carries one of these typed conditions; the bare MAKER (BecomeMonarch / venture /
# RingTemptsYou effect) carries none.
_MONARCH_CONDITIONS: frozenset[str] = frozenset({"IsMonarch", "NoMonarch"})
_VENTURE_CONDITIONS: frozenset[str] = frozenset(
    {"CompletedADungeon", "CompletedDungeon", "IsInitiative"}
)
_RING_CONDITIONS: frozenset[str] = frozenset({"IsRingBearer"})
# Permission tags marking a cast/play-FROM-EXILE build-around (CR 116 / 702.170).
_CAST_FROM_EXILE_PERMS: frozenset[str] = frozenset({"PlayFromExile", "Plotted"})


def _whole_card_maker(
    tree: ConceptTree, concept: str, key: str, scope: str
) -> list[Signal]:
    """A whole-card presence maker (granularity c): the first ``concept`` effect →
    one ``Signal(key, scope)``. The shared shape for the batch-5 phase-native
    makers (discover / venture / amass / incubate / dice / facedown / day-night /
    phasing) — each a clean structural read off a first-class effect node.
    """
    for c in tree.effect_concepts(concept):
        return [Signal(key, scope, "", c.raw, tree.name, "high")]
    return []


def _monarch(tree: ConceptTree) -> list[Signal]:
    """monarch_makers / monarch_matters — The Monarch (CR 725).

    MAKER: a ``BecomeMonarch`` effect that makes YOU (not an opponent) the monarch
    — the give-away gate (checklist #2) reads the wrapper ``player_scope`` via
    :func:`effect_owner_player_scope`; an "each opponent / an opponent becomes the
    monarch" wrapper is excluded. phase carries a BARE ``BecomeMonarch`` for "target
    opponent becomes the monarch" (it drops the direction — Jared Carthalion), so
    the gate is a no-op there and the lane fires you, MATCHING the live ``monarch``
    doer's identical limitation (a shared phase gap, not a crosswalk over-fire).
    MATTERS: an ``IsMonarch`` / ``NoMonarch`` payoff condition (Throne Warden,
    Garrulous Sycophant) — the bare maker carries none. Both scope "you".
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "become_monarch":
                continue
            if effect_owner_player_scope(getattr(unit, "node", None), c.node) in (
                _EDICT_ACTORS
            ):
                continue
            fire("monarch_makers", c.raw)
    if condition_tags(tree) & _MONARCH_CONDITIONS:
        fire("monarch_matters", "")
    return out


def _venture(tree: ConceptTree) -> list[Signal]:
    """venture_makers / venture_matters — Dungeons + the Initiative (CR 309 / 701.49).

    MAKER: a ``VentureIntoDungeon`` or ``TakeTheInitiative`` effect (the card
    PERFORMS the venture / takes the Initiative — Bar the Gate, Avenging Hunter).
    MATTERS: a ``CompletedADungeon`` / ``CompletedDungeon`` / ``IsInitiative``
    payoff condition (Gloom Stalker, Imoen, Nadaar) — read structurally off the
    typed ``condition``. A maker-only card carries no condition; a matters-only
    card carries no venture effect. Both scope "you".
    """
    out: list[Signal] = []
    out += _whole_card_maker(tree, "venture", "venture_makers", "you")
    if condition_tags(tree) & _VENTURE_CONDITIONS:
        out.append(Signal("venture_matters", "you", "", "", tree.name, "high"))
    return out


def _ring(tree: ConceptTree) -> list[Signal]:
    """ring_tempters / ring_matters — The Ring Tempts You (CR 701.54).

    MAKER: a ``RingTemptsYou`` effect (the card performs the tempt — Boromir,
    Warden of the Tower) → ``ring_tempters`` (the live maker key). MATTERS: an
    ``IsRingBearer`` payoff condition (Sauron, the Necromancer — a buried
    Ring-bearer reference with NO tempt trigger, which the typed condition recovers
    STRUCTURALLY where the live path needed a raw "ring-bearer" marker). Both scope
    "you".
    """
    out: list[Signal] = []
    out += _whole_card_maker(tree, "ring_tempt", "ring_tempters", "you")
    if condition_tags(tree) & _RING_CONDITIONS:
        out.append(Signal("ring_matters", "you", "", "", tree.name, "high"))
    return out


def _discover_makers(tree: ConceptTree) -> list[Signal]:
    """discover_makers — a ``Discover N`` DOER (CR 701.57). Read STRUCTURALLY off the
    typed ``Discover`` effect (Geological Appraiser; the keyword-LESS re-trigger
    "whenever you discover, discover again" also carries a second ``Discover``
    effect). A discover-PAYOFF trigger with no ``Discover`` effect is a separate
    lane (out of batch). Scope "you".
    """
    return _whole_card_maker(tree, "discover", "discover_makers", "you")


def _daynight_makers(tree: ConceptTree) -> list[Signal]:
    """daynight_makers — a ``SetDayNight`` transition DOER (CR 731). The card itself
    flips the day/night state ("it becomes day/night" — Brimstone Vandal, The
    Celestus). The daybound/nightbound transforming werewolves (the PAYOFF that
    flips ON the state) ride a ``daynight_matters`` keyword field-lookup, NOT this
    arm — a daybound werewolf carries no ``SetDayNight`` effect. Scope "you".
    """
    return _whole_card_maker(tree, "set_daynight", "daynight_makers", "you")


def _phasing_makers(tree: ConceptTree) -> list[Signal]:
    """phasing_makers — a ``PhaseOut`` / ``PhaseIn`` DOER (CR 702.26). Matching the
    live ``phasing`` doer, this is a BLANKET maker (scope "you") that does NOT split
    by direction: a self phase-out (protection — Blink Dog) and an opponent-directed
    phase-out (denial — Divine Smite's "creature an opponent controls phases out")
    both fire. The direction split checklist gate (#6) is moot because the live
    target lane is a single undirected key; collapsing the two directions matches
    it. Scope "you".
    """
    return _whole_card_maker(tree, "phasing", "phasing_makers", "you")


def _voting_makers(tree: ConceptTree) -> list[Signal]:
    """voting_makers — a council/dilemma VOTE the card instructs (CR 701.38). Fires
    on a ``Vote`` effect whose ``voter_scope`` is ``AllPlayers`` ("each player votes"
    — Coercive Portal, Expropriate, Tivit). phase OVER-TAGS the Battlebond
    "for each player, choose friend or foe" mechanic (``voter_scope:
    ControllerLabels`` — Pir's Whim, Zndrsplt's Judgment) and the "each opponent
    chooses X" cards (``voter_scope: EachOpponent`` — Seize the Spotlight, Master of
    Ceremonies) as ``Vote`` too; the ``AllPlayers`` gate excludes them STRUCTURALLY
    — a clean improvement over the live ``_VOTE_EFFECT_GUARD`` raw-idiom regex.
    Scope "each" (every player votes), matching the live structural maker arm.
    """
    for c in tree.effect_concepts("vote"):
        if tag_of(getattr(c.node, "voter_scope", None)) == "AllPlayers":
            return [Signal("voting_makers", "each", "", c.raw, tree.name, "high")]
    return []


def _amass_makers(tree: ConceptTree) -> list[Signal]:
    """amass_makers — an ``Amass N`` DOER (CR 701.47): grow / create a Zombie or
    Orc Army (Aven Eternal, Eternal Taskmaster). A NEW dedicated lane (the live path
    routes amass into the broad ``tokens_matter`` keyword arm); the typed ``Amass``
    effect gives it its own Army-population key. Scope "you".
    """
    return _whole_card_maker(tree, "amass", "amass_makers", "you")


def _incubate_makers(tree: ConceptTree) -> list[Signal]:
    """incubate_makers — an ``Incubate N`` DOER (CR 701.53): make an Incubator token
    with N +1/+1 counters that transforms into a 0/0 artifact creature (Brimaz,
    Blight of Oreskos, Chrome Host Seedshark). A NEW dedicated lane (the live path
    has no incubate key). The Incubator co-feeds ``artifacts_matter`` only when a
    card MAKES the token via ``make_token``; the ``Incubate`` effect is its own
    maker. Scope "you".
    """
    return _whole_card_maker(tree, "incubate", "incubate_makers", "you")


def _facedown_makers(tree: ConceptTree) -> list[Signal]:
    """facedown_makers — a ``Manifest`` / ``Cloak`` DOER (CR 701.40 / 701.58 / 708):
    put a card onto the battlefield face down as a 2/2 (Cloudform, Cryptic Coat).
    The ``TurnFaceUp`` effect REFERENCES an existing face-down permanent (a payoff →
    ``facedown_matters``, out of batch) and the ``FaceDown`` filter PREDICATE
    ("face-down creature spells you cast cost less" — Dream Chisel) is the
    cares-about state, NOT a maker — neither surfaces as the ``facedown`` effect
    concept, so both are excluded structurally. The morph / megamorph / disguise /
    manifest-dread printed keywords (no ``Manifest`` / ``Cloak`` effect node — they
    are CAST face down) ride the keyword field-lookup in
    :func:`_keyword_field_signals_b5`. Scope "you".
    """
    return _whole_card_maker(tree, "facedown", "facedown_makers", "you")


def _dice_makers(tree: ConceptTree) -> list[Signal]:
    """dice_makers — a ``RollDie`` DOER (CR 706): the card instructs a die roll
    (Adorable Kitten, the d20 Dungeons & Dragons engines). A "whenever you roll"
    PAYOFF trigger is a separate lane (out of batch). Scope "you".
    """
    return _whole_card_maker(tree, "roll_die", "dice_makers", "you")


def _cast_from_exile(tree: ConceptTree) -> list[Signal]:
    """cast_from_exile — a play/cast-FROM-EXILE build-around (CR 116 / 601.3b /
    702.170). Reads the ``GrantCastingPermission`` effect's ``permission`` node
    STRUCTURALLY (:func:`permission_tag`): ``PlayFromExile`` (impulse exile-and-play
    — Act on Impulse, Abbot of Keral Keep) or ``Plotted`` (plot — Aloe Alchemist).
    This is the batch's marquee fidelity gain — the live path kept a byte-identical
    word-mirror because the OLD lossy IR dropped the from-exile zone off the cast.
    Keyword cast-from-exile mechanics (foretell / suspend) are kept OUT of this lane
    (they have their own maker field-lookups), avoiding double counting; the
    self-recast cards phase represents without a ``GrantCastingPermission`` (Eternal
    Scourge) stay a documented ``live_only`` residue. A plain ``Exile`` removal
    (Banisher Priest, Path to Exile) carries no permission → no fire. Scope "you".
    """
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "grant_cast_permission":
                continue
            if permission_tag(c.node) in _CAST_FROM_EXILE_PERMS:
                return [Signal("cast_from_exile", "you", "", c.raw, tree.name, "high")]
    return []


# Batch-5 Scryfall-keyword field-lookups (checklist #3 — NO typed effect tag for
# these; the live path keeps them as keyword survivors). Each keyword tags the
# BEARER / enabler (the maker), NOT a payoff (unlike Explore / Connive whose
# keyword also tags payoffs), so a clean keyword array read is precise.
_FORETELL_KEYWORDS: frozenset[str] = frozenset({"foretell"})
_CASCADE_KEYWORDS: frozenset[str] = frozenset({"cascade"})
_SUSPEND_KEYWORDS: frozenset[str] = frozenset({"suspend"})
# infect / toxic / poisonous (CR 702.90 / 702.164) — the poison-counter DEALERS.
_POISON_KEYWORDS: frozenset[str] = frozenset({"infect", "toxic", "poisonous"})
# daybound / nightbound (CR 702.145) — the transforming werewolves REWARDED by the
# day↔night flip (the daynight_matters payoff side).
_DAYNIGHT_KEYWORDS: frozenset[str] = frozenset({"daybound", "nightbound"})
# The face-down 2/2 KEYWORD makers (CR 708): morph / megamorph (702.37) and
# disguise (702.168) are CAST face down and ride the Scryfall keyword array (phase
# emits no Manifest/Cloak effect for them); manifest dread (701.55) likewise.
# manifest / cloak ALSO carry the keyword (the structural ``facedown`` effect arm
# dedups the overlap). Every keyword puts a face-down permanent on the battlefield
# → the maker lane. Exact-key match keeps "Ceremorphosis" (morph substring) out.
_FACEDOWN_KEYWORDS: frozenset[str] = frozenset(
    {"morph", "megamorph", "disguise", "manifest", "cloak", "manifest dread"}
)


def _keyword_field_signals_b5(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-5 Scryfall-keyword field-lookups (checklist #3 survivors):

    * ``foretell`` → ``foretell_makers`` you (CR 702.143);
    * ``cascade`` → ``cascade_makers`` you (CR 702.85);
    * ``suspend`` → ``suspend_makers`` you (CR 702.62);
    * ``infect`` / ``toxic`` / ``poisonous`` → ``poison_makers`` opponents (CR
      702.90 / 702.164 — the poison-counter dealers; a ``OpponentPoisonAtLeast``
      Corrupted PAYOFF with no such keyword stays out, the typed condition being a
      separate ``poison_matters`` lane);
    * ``daybound`` / ``nightbound`` → ``daynight_matters`` you (CR 702.145);
    * morph / megamorph / disguise / manifest / cloak / manifest dread →
      ``facedown_makers`` you (CR 708 — every face-down 2/2 maker; the
      keyword-only morph / disguise bodies carry NO ``Manifest`` / ``Cloak``
      effect, so the keyword array is the uniform anchor over all six, deduped
      against the structural :func:`_facedown_makers` arm).

    Reading the STRUCTURED keyword array (not oracle text) makes the lanes immune to
    the name / ability-word collisions the deleted regex floors suffered (a card
    naming the mechanic only in its title can never carry the keyword). The poison
    GRANTERS ("gains infect") and the structural ``GivePlayerCounter:poison`` givers
    phase carries off the keyword array are a documented ``live_only`` residue
    (checklist #6).
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _FORETELL_KEYWORDS:
        out.append(Signal("foretell_makers", "you", "", "", name, "high"))
    if low & _CASCADE_KEYWORDS:
        out.append(Signal("cascade_makers", "you", "", "", name, "high"))
    if low & _SUSPEND_KEYWORDS:
        out.append(Signal("suspend_makers", "you", "", "", name, "high"))
    if low & _POISON_KEYWORDS:
        out.append(Signal("poison_makers", "opponents", "", "", name, "high"))
    if low & _DAYNIGHT_KEYWORDS:
        out.append(Signal("daynight_matters", "you", "", "", name, "high"))
    if low & _FACEDOWN_KEYWORDS:
        out.append(Signal("facedown_makers", "you", "", "", name, "high"))
    return out


def _keyword_field_signals(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-4 Scryfall-keyword field-lookups — survivor routes the live path
    DELIBERATELY keeps because phase carries no effect node (checklist #3):

    * cast-from-GY family (flashback / escape / …) → ``graveyard_makers`` you;
    * dredge / delve / scavenge → ``graveyard_matters`` you;
    * ``spectacle`` (the condition is reminder-text-only, no structural ``LoseLife``)
      → ``lifeloss_matters`` opponents;
    * ``goad`` → ``goad_makers`` opponents — UNLIKE explore / connive (whose keyword is
      ALSO carried by PAYOFFS — Wildgrowth Walker, Copycrook — forcing structural-only
      there), the Scryfall ``Goad`` keyword marks only the ACTION's makers (every
      goader, incl. the Impetus / Bloodthirsty-Blade auras that goad the enchanted
      creature), so the field-lookup is precise (CR 701.15a).
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _GY_CAST_KEYWORDS:
        out.append(Signal("graveyard_makers", "you", "", "", name, "high"))
    if low & _GY_MATTERS_KEYWORDS:
        out.append(Signal("graveyard_matters", "you", "", "", name, "high"))
    if "spectacle" in low:
        out.append(Signal("lifeloss_matters", "opponents", "", "", name, "high"))
    if "goad" in low:
        out.append(Signal("goad_makers", "opponents", "", "", name, "high"))
    return out


# ── Batch 6 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# place_counter ``counter_type`` (upper-cased) → its off-+1/+1 MAKER lane (CR
# 122.1). The card PERFORMS the placement. p1p1 / m1m1 are ported elsewhere.
_PLACE_COUNTER_MAKER_KINDS: dict[str, str] = {
    "OIL": "oil_counter_makers",
    "KI": "ki_counter_makers",
    "SHIELD": "shield_counter_makers",
}
# Predicate-side counter-KIND payoff routing (CR 122.1) — mirrors the live
# ``_COUNTER_KIND_KEYS`` dispatch a "creature WITH an X counter" subject filter
# rides. Only ``oil`` has a structural payoff filter in the v0.9.0 substrate
# (the ki / shield counter PAYOFFS are cost-side "remove an X counter" or
# un-structured → a documented ``live_only`` residue); the full map is kept for
# fidelity (the unported ki_counter_matters key slices out in the extractor).
_COUNTER_PRED_LANES: dict[str, tuple[str, str]] = {
    "oil": ("oil_counter_matters", "you"),
    "shield": ("shield_counter_makers", "you"),
    "rad": ("rad_counter_makers", "opponents"),
    "ki": ("ki_counter_matters", "you"),
}
# GivePlayerCounter ``counter_kind`` (lower-cased) → its player-resource MAKER
# lane + the FIXED lane scope (CR 122.1 / 728). rad lands on opponents (a kill
# clock — the live ``_PLAYER_COUNTER_KEYS`` scopes it ``opponents`` regardless of
# the giver's recipient); experience is a personal resource (scope ``you``). The
# poison giver is ported elsewhere (the ``poison_makers`` keyword lane).
_PLAYER_COUNTER_MAKER: dict[str, tuple[str, str]] = {
    "rad": ("rad_counter_makers", "opponents"),
    "experience": ("experience_makers", "you"),
}
# Player-reference tags naming an opponent — the only direction that takes a
# party/poison-style count off YOUR resource (CR 700.8 — "your party").
_OPP_PLAYER_TAGS: frozenset[str] = frozenset({"Opponent", "Opponents", "EachOpponent"})


def _counter_kind_lanes(tree: ConceptTree) -> list[Signal]:
    """oil / ki / shield counter lanes (CR 122.1). Two structural arms:

    * **MAKER** — a ``place_counter`` (``PutCounter`` / ``PutCounterAll``) whose
      ``counter_type`` is an off-+1/+1 ported kind (oil / ki / shield), mirroring
      ``plus_one_makers`` / ``minus_counters_matter``. The card PERFORMS the
      placement (Glistener Seer's oil, Petalmane Baku's ki, Boon of Safety's
      shield). The kind discriminates — a +1/+1 / loyalty placement never fires.
    * **MATTERS** — a non-cost subject / count-operand filter carrying a
      ``Counters`` predicate of a ported kind (Urabrask's Anointer scales off "oil
      counters on creatures you control"). Routed via :data:`_COUNTER_PRED_LANES`,
      controller-gated against an opponent filter (checklist #6). Only oil has a
      structural payoff filter in v0.9.0; ki / shield payoffs are cost-side and
      stay ``live_only``.
    """
    out: list[Signal] = []
    seen: set[tuple[str, str]] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if (key, scope) not in seen:
            seen.add((key, scope))
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for c in tree.effect_concepts("place_counter"):
        key = _PLACE_COUNTER_MAKER_KINDS.get(counter_kind(c.node).upper())
        if key:
            fire(key, "you", c.raw)
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            for kind in counter_pred_kinds(filt):
                lane = _COUNTER_PRED_LANES.get(kind.lower())
                if lane:
                    fire(lane[0], lane[1], c.raw)
    return out


def _player_counter_makers(tree: ConceptTree) -> list[Signal]:
    """rad_counter_makers / experience_makers — a ``GivePlayerCounter`` DOER (CR
    122.1 / 728). The card gives a player a rad (a mill-and-bleed kill clock,
    fixed scope ``opponents``) or an experience counter (a personal resource,
    scope ``you``) — read off the typed ``counter_kind``, the kind the OLD lossy
    IR split into per-kind effect categories. Tato Farmer → rad; Mizzix / Ezuri →
    experience. The poison giver routes to its own ``poison_makers`` lane.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for c in tree.effect_concepts("give_player_counter"):
        lane = _PLAYER_COUNTER_MAKER.get(player_counter_kind(c.node).lower())
        if lane and lane[0] not in seen:
            seen.add(lane[0])
            out.append(Signal(lane[0], lane[1], "", c.raw, tree.name, "high"))
    return out


def _count_operand_lanes(tree: ConceptTree) -> list[Signal]:
    """devotion / party / domain / experience_matters — a NAMED count-operand
    SCALER payoff (CR 700.5 / 700.6 / 700.8 / 122.1). Reads the qty tag of an
    effect's (or static P/T mod's) dynamic count operand
    (:func:`count_operand_qty`):

    * ``Devotion`` / ``DevotionGE`` → ``devotion_matters`` (Gray Merchant, a
      "lose life equal to your devotion" scaler) — intrinsically your permanents
      (CR 700.5), no extra gate;
    * ``PartySize`` → ``party_matters`` (Burakos), gated off an opponent's-party
      reference (checklist #6);
    * ``BasicLandTypeCount`` → ``domain_matters`` (Tribal Flames), controller-
      gated against an opponent's lands (the old "not modeled" classification was
      wrong — the substrate carries ``BasicLandTypeCount``);
    * ``PlayerCounter`` with ``kind == experience`` → ``experience_matters``
      (Ezuri's "+1/+1 counter for each experience counter you have"); a ``Poison``
      PlayerCounter (Mycosynth Fiend) is gated out by the kind check (it is a
      separate ``poison_matters`` lane). All scope ``you``.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        qty = count_operand_qty(c.node)
        if qty is None:
            continue
        t = tag_of(qty)
        if t in ("Devotion", "DevotionGE"):
            fire("devotion_matters", c.raw)
        elif t == "PartySize" and (
            tag_of(getattr(qty, "player", None)) not in _OPP_PLAYER_TAGS
        ):
            fire("party_matters", c.raw)
        elif t == "BasicLandTypeCount" and (
            getattr(qty, "controller", None) != "Opponent"
        ):
            fire("domain_matters", c.raw)
        elif t == "PlayerCounter" and (
            str(getattr(qty, "kind", "")).lower() == "experience"
        ):
            fire("experience_matters", c.raw)
    return out


def _modified_matters(tree: ConceptTree) -> list[Signal]:
    """modified_matters — a Kamigawa-NEO "modified creature" payoff (CR 700.9: a
    permanent is modified if it has a counter, is equipped, or is enchanted by an
    Aura its controller controls). phase DERIVES the CR-700.9 union as a single
    ``Modified`` predicate, so the lane reads that tag off a non-cost subject /
    count-operand / static-affected filter, controller-gated to ``You`` (Chishiro,
    Thundering Raiju). A removal "destroy target modified creature" (controller
    any) is NOT a build-around. The bare ``\\bmodified\\b`` word references stay a
    ``live_only`` mirror. Scope ``you``.
    """
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if (
                filt is not None
                and "Modified" in filter_predicates(filt)
                and filter_controller(filt) == "You"
            ):
                return [Signal("modified_matters", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if not unit.statics:
            continue
        aff = getattr(unit.node, "affected", None)
        if (
            aff is not None
            and "Modified" in filter_predicates(aff)
            and filter_controller(aff) == "You"
        ):
            return [Signal("modified_matters", "you", "", "", tree.name, "high")]
    return []


def _predicate_build_around(tree: ConceptTree) -> list[Signal]:
    """multicolor / colorless / power / low_power / vanilla matters — color- and
    P/T-property BUILD-AROUND lanes (CR 105.2 / 208.1 / 113.3). Mirrors
    ``_signals_ir._predicate_build_around_lanes`` over a non-cost subject /
    count-operand / static-affected filter, scope ``you``:

    * **multicolor_matters** — a ``ColorCount`` ``GE``≥2 / ``EQ``≥2 predicate
      (Knight of New Alara's "other multicolored creatures you control"),
      controller ``You`` (a single-color / hoser reference is not a build-around);
    * **colorless_matters** — a ``ColorCount`` ``EQ 0`` predicate (Forsaken
      Monument; Ancient Stirrings' unscoped reveal), controller ``You`` or
      unscoped (the regex reads colorless unscoped too);
    * **power_matters** / **low_power_matters** — a FIXED ``PtComparison`` on
      Power, split by comparator direction (``GE``/``GT`` high — Shaman of the
      Great Hunt; ``LE``/``LT`` low — Arabella), controller ``You``. A relative /
      dynamic comparison (the old ``:*``) is a fight-style check, excluded by
      :func:`power_threshold_preds`. A "destroy target creature with power 4 or
      greater" removal (controller any — Big Game Hunter) never fires;
    * **vanilla_matters** — a ``HasNoAbilities`` predicate (Muraganda, Ruxa),
      controller ``You`` or unscoped (a shared-board static is unscoped).

    The condition-subject power gate (Challenger Troll's Ferocious "as long as you
    control a creature with power 4+") and the trigger-subject sites the substrate
    does not surface through ``iter_concepts`` are a documented ``live_only``
    residue.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    def handle(filt: object, raw: str) -> None:
        if filt is None:
            return
        ctrl = filter_controller(filt)
        you = ctrl == "You"
        shared = ctrl in ("You", "Any", None)  # you or an unscoped global
        for cmp_, cnt in color_count_preds(filt):
            if cmp_ == "EQ" and cnt == 0:
                if shared:
                    fire("colorless_matters", raw)
            elif you and ((cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)):
                fire("multicolor_matters", raw)
        if you:
            for stat, cmp_, _v in power_threshold_preds(filt):
                if stat != "Power":
                    continue
                if cmp_ in ("GE", "GT"):
                    fire("power_matters", raw)
                elif cmp_ in ("LE", "LT"):
                    fire("low_power_matters", raw)
        if shared and "HasNoAbilities" in filter_predicates(filt):
            fire("vanilla_matters", raw)

    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        handle(effect_filter(c.node), c.raw)
        handle(count_operand_filter(c.node), c.raw)
    for unit in tree.units:
        if unit.statics:
            handle(getattr(unit.node, "affected", None), "")
    return out


def _coin_flip(tree: ConceptTree) -> list[Signal]:
    """coin_flip — a ``FlipCoin`` / ``FlipCoins`` / ``FlipCoinUntilLose`` DOER (CR
    705.1). The card instructs a coin flip (Krark, the Thumbless). A die roll
    (``RollDie`` → ``dice_makers``, CR 706) is a SEPARATE lane — kept split. Scope
    ``you``.
    """
    for c in tree.effect_concepts("flip_coin"):
        return [Signal("coin_flip", "you", "", c.raw, tree.name, "high")]
    return []


def _opponent_discard(tree: ConceptTree) -> list[Signal]:
    """opponent_discard — a forced OPPONENT discard / hand attack (CR 701.9). A
    ``Discard`` effect whose recipient is a targeted / opponent player ("target
    player discards two cards" — Mind Rot → ``opponents``) or a symmetric
    each-player wheel (``each`` — it hits opponents too). Direction is read off the
    discard's OWN recipient node (:func:`discard_recipient_scope`), NOT phase's
    mis-scoped trigger scope ([P5]). A you-scoped self-loot ("draw, then discard"
    — Faithless Looting) is the ported ``discard_makers`` lane, NOT this one.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for unit in tree.units:
        for c in unit.effect_concepts("discard"):
            sc = discard_recipient_scope(c.node)
            if sc not in ("opponents", "each") or sc in seen:
                continue
            if _is_target_player_loot(unit, c):
                continue
            seen.add(sc)
            out.append(Signal("opponent_discard", sc, "", c.raw, tree.name, "high"))
        # Batch 9 — the PUNISHER trigger arm: "whenever an opponent discards
        # a card, …" (Megrim, Liliana's Caress). phase watches the discarder
        # on the trigger's ``valid_card`` controller (Megrim — Opponent) or
        # ``valid_target``; the self/any-scope complement is the disjoint
        # ``discard_matters`` lane (checklist #5 — the discarder scope is
        # read off the trigger's own recipient nodes, never the mislabeled
        # trigger_scope). CR 701.8a / 102.2.
        if (
            unit.trigger_event == "discarded"
            and _discard_watch_is_opponent(unit)
            and "opponents" not in seen
        ):
            seen.add("opponents")
            out.append(
                Signal("opponent_discard", "opponents", "", "", tree.name, "high")
            )
    return out


# Recipient tags naming a SINGLE targeted player (not an explicit opponent / each).
_TARGETED_PLAYER_TAGS: frozenset[str] = frozenset({"ParentTarget", "Player", "Target"})


def _is_target_player_loot(unit: AbilityUnit, discard: ConceptNode) -> bool:
    """Whether a discard is a "target player draws, then discards" LOOT, not a hand
    attack (CR 701.9 / 701.8a).

    Cephalid Looter / Cephalid Broker resolve "target player draws a card, then
    discards a card": phase tags the discard recipient ``ParentTarget`` (the
    just-targeted player), so :func:`discard_recipient_scope` reads ``opponents`` —
    but a SIBLING draw targets the SAME single player, so the controller points it
    at THEMSELVES to filter cards (the ported ``discard_makers`` role), never at an
    opponent. The gate fires only when BOTH the discard AND a sibling draw name a
    single targeted player; a one-sided attack with no draw (Mind Rot, Blightning)
    and a wheel whose draw is for YOU while an opponent discards (Cruel Ultimatum —
    draw recipient ``Controller``) are correctly NOT loots.
    """
    if recipient_tag(discard.node) not in _TARGETED_PLAYER_TAGS:
        return False
    return any(
        recipient_tag(d.node) in _TARGETED_PLAYER_TAGS
        for d in unit.effect_concepts("draw")
    )


# ── Batch 7 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# AdditionalPhase.phase values (lowercased) that are a COMBAT phase (CR 505 / 506)
# — the only phase the live ``extra_combats`` lane reads (project._EXTRA_PHASE). An
# extra upkeep / draw / end phase is mis-routed by phase to combat and recovered by
# a separate ``project`` marker (a documented KEPT-DETECTOR), so the combat gate
# mirrors the live ``extra_combats`` exactly.
_COMBAT_PHASES: frozenset[str] = frozenset({"begincombat", "combat"})

# GiveControl recipient scopes that are a give-AWAY (the beneficiary is NOT you —
# checklist #2): a targeted player ("any"), an opponent, or each player. A
# you-recipient (no real card) is excluded.
_GIVE_AWAY_SCOPES: frozenset[str] = frozenset({"any", "opponents", "each"})


def _extra_combats(tree: ConceptTree) -> list[Signal]:
    """extra_combats — an ADDITIONAL combat phase (CR 505 / 506). Mirrors the live
    ``_DOER_EFFECT_KEYS["extra_combat"]`` doer: an ``AdditionalPhase`` effect whose
    ``phase`` is a combat phase (Aurelia, Moraug, Combat Celebrant). Distinct from
    ``extra_turns`` (``ExtraTurn`` — Time Warp): a different effect tag, never read
    here. The phase gate discriminates against the mis-routed extra-upkeep/draw/end
    forms (a documented KEPT-DETECTOR ``project`` marker). Scope "you" — the active
    player takes the phase (the live forces "you").
    """
    for c in tree.effect_concepts("extra_phase"):
        if additional_phase_kind(c.node) in _COMBAT_PHASES:
            return [Signal("extra_combats", "you", "", c.raw, tree.name, "high")]
    return []


def _cost_reduction(tree: ConceptTree) -> list[Signal]:
    """cost_reduction — a static spell-cost REDUCER build-around (CR 601.2f / 118.7).
    Mirrors the live ``cost_reduction`` doer: a ``static_ability`` whose ``mode`` is a
    ``ModifyCost`` of direction ``Reduce`` (Goblin Electromancer, Helm of Awakening,
    Ruby Medallion). Two structural gates replace the live path's raw screens:

    * **direction** — :func:`modify_cost_mode` reads the typed ``mode``; a ``Raise``
      tax (Thalia) / ``Minimum`` floor is excluded (the live ``_COST_INCREASE`` raw
      screen);
    * **not a self-discount** — two screens. The ``affected`` filter must NOT be
      ``SelfRef`` — phase's canonical self-discount shape, 220/226 of the "this
      spell costs" statics (A-Demilich). Six residual self-discounts instead
      parse as ``Typed[Card]`` + ``spell_filter=null`` — byte-identical to the
      symmetric Helm-of-Awakening reducer, distinguishable only by the static's
      own ``description`` ([P8], refined 2026-07-02) — so a node-local
      "this spell costs" description screen (the live ``_COST_SELF_DISCOUNT``
      mirror; node-local raw precedent ``_is_scaling_count``) drops them
      (Discontinuity, Hierophant Bio-Titan).

    A flat ramp rock (no ``ModifyCost``) never reaches the gate. The activated
    "next spell you cast costs less" synth form (``reducenextspellcost`` — no native
    static node) is a documented ``live_only`` tail. Scope "you".
    """
    for unit in tree.units:
        if modify_cost_mode(unit.node) != "Reduce":
            continue
        if tag_of(getattr(unit.node, "affected", None)) == "SelfRef":
            continue
        desc = getattr(unit.node, "description", None) or ""
        if "this spell costs" in desc.lower():
            continue
        return [Signal("cost_reduction", "you", "", "", tree.name, "high")]
    return []


def _donate_makers(tree: ConceptTree) -> list[Signal]:
    """donate_makers — give a permanent YOU control to ANOTHER player (CR 110.2).
    Mirrors the live ``donate_makers`` doer (which folds the recipient from raw
    because the OLD lossy IR dropped it): a ``GiveControl`` effect whose ``recipient``
    is a non-you player (Donate, Bazaar Trader, Harmless Offering) — the give-away
    direction read STRUCTURALLY off the recipient node (checklist #2,
    :func:`control_recipient_scope`). Theft (``GainControl`` / ``GainControlAll`` →
    ``gain_control``) and a control-RESET ("each player gains control of permanents
    they own" — Brooding Saurian, a ``GainControlAll``) are a different concept,
    never read here. Scope "you" (the controller performs the gift).
    """
    for c in tree.effect_concepts("give_control"):
        if control_recipient_scope(c.node) in _GIVE_AWAY_SCOPES:
            return [Signal("donate_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _conjure_makers(tree: ConceptTree) -> list[Signal]:
    """conjure_makers — a ``Conjure`` DOER (DD2 / DD5): create a real card from
    outside the deck into a zone (an Alchemy mechanic; NOT a token, NOT a copy).
    Mirrors the live ``\\bconjure\\b`` regex but reads the typed ``Conjure`` effect —
    a fidelity GAIN: the regex over-fires on a card whose ABILITY NAME contains
    "Conjure" (Silvanus's Invoker — "Conjure Elemental — {8}: …", an animate-land
    with no ``Conjure`` effect node), which the structural read correctly drops. A
    token maker (``make_token`` — Krenko) is a different effect tag. Scope "you".
    """
    for c in tree.effect_concepts("conjure"):
        return [Signal("conjure_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _blocked_matters(tree: ConceptTree) -> list[Signal]:
    """blocked_matters — a combat-block payoff (CR 509). Mirrors the live
    ``_PAYOFF_TRIGGER_KEYS`` ``becomes_blocked`` / ``blocks`` rows: a trigger whose
    derived event is ``becomes_blocked`` (the attacker-side "whenever ~ becomes
    blocked" — CR 509.1h) or ``blocks`` (the blocker-side "whenever ~ blocks" — CR
    509.1g). An ``attacks`` trigger is a different lane (``attack_matters``). The
    disjunctive "attacks or blocks" membership fold (phase → event='other') stays a
    ``live_only`` mirror. Scope "you" (the live forces it; no opponent-side ``blocks``
    trigger exists to over-fire).
    """
    for unit in tree.units:
        if unit.trigger_event in ("becomes_blocked", "blocks"):
            return [Signal("blocked_matters", "you", "", "", tree.name, "high")]
    return []


def _initiative(tree: ConceptTree) -> list[Signal]:
    """initiative_makers / initiative_matters — The Initiative (CR 726). Mirrors the
    live ``\\btake the initiative\\b`` / ``\\bhave the initiative\\b`` regex pair,
    read structurally:

    * **MAKER** — a ``TakeTheInitiative`` effect node (Caves of Chaos Adventurer,
      White Plume Adventurer, Seasoned Dungeoneer). Read off the typed ``_tag``
      DISTINCTLY from ``VentureIntoDungeon`` (both fold to the ``venture`` concept),
      so ``venture_makers`` keeps co-firing — matching the live DOUBLE-fire (an
      initiative card fires both ``venture_makers`` structurally AND
      ``initiative_makers``). A pure-venture card (Acererak — ``VentureIntoDungeon``)
      fires ``venture_makers`` only, NEVER ``initiative_makers``;
    * **MATTERS** — an ``IsInitiative`` payoff CONDITION ("as long as / if you have
      the initiative" — Passageway Seer, Sarevok's Tome), read via
      :func:`condition_tags`. A maker that only TAKES the initiative carries no such
      condition. A monarch-gated card (``IsMonarch`` → ``monarch_matters``) is a
      different designation.

    Both scope "you".
    """
    out: list[Signal] = []
    for c in tree.effect_concepts("venture"):
        if tag_of(c.node) == "TakeTheInitiative":
            out.append(Signal("initiative_makers", "you", "", c.raw, tree.name, "high"))
            break
    if "IsInitiative" in condition_tags(tree):
        out.append(Signal("initiative_matters", "you", "", "", tree.name, "high"))
    return out


def _end_the_turn(tree: ConceptTree) -> list[Signal]:
    """end_the_turn — an ``EndTheTurn`` DOER (CR 724): expedite the rest of the turn,
    exiling whatever is on the stack (Time Stop, Sundial of the Infinite). Mirrors
    the live ``_DOER_EFFECT_KEYS["end_the_turn"]`` doer. Distinct from ``ExtraTurn``
    (``extra_turns`` — Time Warp) and an ``EndCombatPhase`` fog: different effect
    tags, never read here. Scope "you" (the build-around marker the live forces).
    """
    for c in tree.effect_concepts("end_the_turn"):
        return [Signal("end_the_turn", "you", "", c.raw, tree.name, "high")]
    return []


def _opponent_exile_makers(tree: ConceptTree) -> list[Signal]:
    """opponent_exile_makers — GRAVEYARD HATE the card PERFORMS (CR 406 / 701.17a).
    Mirrors the live ``opponent_exile_makers`` doer (a kept word-mirror over phase's
    scattered exile forms), ported as the CLEAN structural arm: a role=effect
    ``ChangeZone`` moving cards ``(Graveyard → Exile)`` that targets a whole PLAYER's
    graveyard (``target`` is a ``Player`` node — Bojuka Bog, Angel of Finality,
    Tormod's Crypt) OR is explicitly opponent-scoped (Author of Shadows). The
    player-target gate is the discriminator that isolates graveyard HATE from a
    self-graveyard-exile-for-value (an escape/fuel ``(Graveyard → Exile)`` of a
    specific CARD — controller you / a single Typed card), which it must NOT fire on.
    Self-blink (Cloudshift — origin not Graveyard), Leyline of the Void (a
    ``replacement``, origin not Graveyard), and an any-graveyard single-card exile
    (Scavenging Ooze — target a Typed card, not a player) are all naturally excluded;
    the replacement / mass-all-graveyards forms stay a documented ``live_only`` tail.
    Scope "opponents" (the live's fixed lane scope).
    """
    for c in tree.effect_concepts("change_zone"):
        if change_zone_dirs(c.node) != ("Graveyard", "Exile"):
            continue
        if (
            tag_of(getattr(c.node, "target", None)) == "Player"
            or c.scope == "opponents"
        ):
            return [
                Signal(
                    "opponent_exile_makers", "opponents", "", c.raw, tree.name, "high"
                )
            ]
    return []


# Batch-7 Scryfall-keyword field-lookups (checklist #3 — the live path keeps these
# as keyword survivors via ``_IR_KEYWORD_MAP`` / ``_PRESET_KEYWORD_SIGNALS``). Each
# keyword tags the BEARER (the maker), not a payoff, so a clean keyword-array read is
# precise. NB: the Scryfall keyword array (the bulk record) carries these — phase's
# OWN ``keywords`` does NOT (Boast / Magecraft / Exhaust are absent from the phase
# record), so the caller supplies the bulk array (the same source ``mill_makers``
# reads). ``flash`` is deliberately ABSENT: the live ``flash_makers`` fires from a
# grant-regex + a ``cast_with_keyword{flash}`` synth (both zero-node in v0.9.0), NOT
# the own ``Flash`` keyword (Snapcaster Mage fires nothing) — so it has no clean
# hook and stays a KEPT-DETECTOR.
_BOAST_KEYWORDS: frozenset[str] = frozenset({"boast"})
_EXHAUST_KEYWORDS: frozenset[str] = frozenset({"exhaust"})
_CONVOKE_KEYWORDS: frozenset[str] = frozenset({"convoke"})
_MAGECRAFT_KEYWORDS: frozenset[str] = frozenset({"magecraft"})


def _keyword_field_signals_b7(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-7 Scryfall-keyword field-lookups (checklist #3 survivors):

    * ``boast`` → ``boast_makers`` you + ``attack_matters`` you (CR 702.142 — the
      Scryfall ``Boast`` keyword is the DOER; the live preset co-fires
      ``attack_matters`` because a boast creature attacks to use the ability —
      ``_IR_KEYWORD_MAP["boast"]``);
    * ``exhaust`` → ``exhaust_makers`` you (CR 702.177 — the once-only activated
      ability maker, ``_IR_KEYWORD_MAP["exhaust"]``);
    * ``convoke`` → ``convoke_makers`` you (CR 702.51 — the BEARER of convoke; the
      "spells you cast have convoke" GRANTER (Chief Engineer — no ``Convoke``
      keyword) fires the live lane from a separate grant detector, a documented
      ``live_only`` tail);
    * ``magecraft`` → ``magecraft_matters`` you (CR 207.2c — an ability WORD; the
      "whenever you cast or copy" trigger lives in stripped reminder text, so the
      Scryfall ``Magecraft`` keyword is the only reachable anchor. A plain
      "whenever you cast an instant or sorcery" creature WITHOUT the keyword (Young
      Pyromancer) carries none → ``spellcast_matters``, not this).

    Reading the STRUCTURED keyword array (not oracle text) makes the lanes immune to
    name / ability-word collisions.
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _BOAST_KEYWORDS:
        out.append(Signal("boast_makers", "you", "", "", name, "high"))
        out.append(Signal("attack_matters", "you", "", "", name, "high"))
    if low & _EXHAUST_KEYWORDS:
        out.append(Signal("exhaust_makers", "you", "", "", name, "high"))
    if low & _CONVOKE_KEYWORDS:
        out.append(Signal("convoke_makers", "you", "", "", name, "high"))
    if low & _MAGECRAFT_KEYWORDS:
        out.append(Signal("magecraft_matters", "you", "", "", name, "high"))
    return out


# ── Batch 8 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# Battlefield permanent types a single-target exile/removal subject may name
# (CR 115.1 / 406.1) — mirrors ``_signals_ir._PERMANENT_TYPES``.
_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)
# Board-wipe subject types (CR 115.10) — mirrors ``_signals_ir._MASS_REMOVAL_
# TYPES``. Land is deliberately ABSENT: "destroy all lands" is land
# destruction (Armageddon), a different lane.
_MASS_REMOVAL_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker"}
)
# Evergreen team-anthem keywords (CR 702) — mirrors ``_signals_ir._TEAM_BUFF_
# GRANT_KW`` (phase's spaceless spelling normalized via lower+strip).
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
# Ref-qty tags that are a BOARD-COUNT scaler by construction (CR 107.3) — a
# counted object population or a named game count. The scaling gate admits
# them structurally; every other non-bare-X tag needs the "for each" raw.
_SCALING_QTY_TAGS: frozenset[str] = frozenset(
    {
        "ObjectCount",
        "ObjectCountDistinct",
        "ObjectCountBySharedQuality",
        "CountersOn",
        "CountersOnObjects",
        "Devotion",
        "PartySize",
        "BasicLandTypeCount",
        "PlayerCounter",
    }
)
# Ref-qty tags that are a bare X / cost-derived magnitude (CR 107.3) — NEVER a
# board scale (Braingeyser's "draw X cards", a "-X/-X" activation).
_BARE_X_QTY_TAGS: frozenset[str] = frozenset(
    {
        "Variable",
        "CostXPaid",
        "ChosenNumber",
        "EventContextAmount",
        "PreviousEffectAmount",
        "TimesCostPaidThisResolution",
    }
)
# Mana-effect recipient tags naming a NON-controller player (CR 106.4) — the
# group_mana direction: "whenever a player taps … THAT PLAYER adds" (Mana
# Flare — TriggeringPlayer), "each player's upkeep, that player adds" (Magus
# of the Vineyard — ScopedPlayer), "target player adds" (Player/Target).
_GROUP_MANA_RECIPIENTS: frozenset[str] = frozenset(
    {
        "TriggeringPlayer",
        "ScopedPlayer",
        "Player",
        "Target",
        "ParentTarget",
        "Each",
        "AllPlayers",
        "EachPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
    }
)
# Discard-owning wrapper actors that mark an OPPONENT-directed discard (CR
# 701.9): phase mislabels a modal/saga/per-opponent "each opponent discards"
# recipient ``Controller`` but hangs ``player_scope: Opponent`` on the wrapper
# (The Eldest Reborn ch. 2, Aclazotz). ``All``/``Each`` are deliberately
# ABSENT — a symmetric wheel (Dark Deal) hits YOU too and stays loot fuel.
_OPP_DISCARD_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "TargetPlayer"}
)
# Sibling-return target tags marking the SAME exiled object coming back (CR
# 603.6e) — the blink tell the exile_removal lane vetoes on.
_RETURN_TARGET_TAGS: frozenset[str] = frozenset(
    {"ParentTarget", "TrackedSet", "TrackedSetFiltered"}
)
# Counted-population controllers naming an OPPONENT-directed count (checklist
# #6): an explicit opponent, a targeted/defending player, or the ETB-chosen
# opponent (Pallimud / Skyshroud War Beast's ``SourceChosenPlayer``).
_OPP_COUNT_CONTROLLERS: frozenset[str] = frozenset(
    {
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TargetPlayer",
        "DefendingPlayer",
        "SourceChosenPlayer",
    }
)
# ExileTop owners naming ANOTHER player's library (a theft-impulse — Gonti,
# Night Minister exiles from the damaged OPPONENT's library): not the
# your-library impulse engine.
_OPP_TOP_OWNERS: frozenset[str] = frozenset(
    {
        "ParentTarget",
        "ParentTargetController",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
    }
)
# SearchLibrary target_player tags UNCONDITIONALLY directing the search at
# ANOTHER player — never YOUR cheat. ``ParentTargetController`` is NOT here
# (batch-9 follow-up c): it resolves through the parent TARGET, which may be
# an OBJECT you chose (Arcum Dagsson's "target artifact creature's controller
# … may search" — CR 115.1 puts the target choice with the ability's
# controller, so the directed player is routinely YOU) or a targeted PLAYER
# (Settle the Wreckage's wiped-player compensation). The conditional veto in
# :func:`_directed_search_sibling` splits the two on the unit's player-target
# marker.
_DIRECTED_SEARCHERS: frozenset[str] = frozenset(
    {
        "ParentTarget",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
    }
)
# +1/+1 / -1/-1 counter kinds (upper) — the counter_manipulation discriminator
# vs charge/oil/loyalty/fade (split-lane #4, CR 122.1 / 122.6).
_PT_COUNTER_KINDS: frozenset[str] = frozenset({"P1P1", "M1M1"})
# Dynamic-P/T modification tags (a +X/+X anthem/pump whose X is computed) —
# the scaling_pump / count_anthem mod-site anchor. The ``Set*`` forms are
# characteristic-defining */* bodies (variable_pt), NOT a pump — excluded.
_DYNAMIC_PT_MODS: frozenset[str] = frozenset({"AddDynamicPower", "AddDynamicToughness"})


def _is_scaling_count(node: TypedMirrorNode, fields: tuple[str, ...], raw: str) -> bool:
    """Whether one of ``node``'s ``fields`` is a genuine BOARD-COUNT scaler
    ("for each <X>", CR 107.3), not a bare X-spell whose X is the cast cost.

    Mirrors ``_signals_ir._is_scaling_count`` over the typed substrate: a
    counted-population / named-count qty tag (:data:`_SCALING_QTY_TAGS`) is
    always a scale; a bare-X tag (:data:`_BARE_X_QTY_TAGS` — Braingeyser)
    never is; any OTHER dynamic tag (CommanderCastFromCommandZoneCount,
    GraveyardSize, …) scales only when the node's raw names the count ("for
    each" / "equal to the number of" — Commander's Insignia).
    """
    low = (raw or "").lower()
    phrase = "for each" in low or "equal to the number of" in low
    for f in fields:
        qt = ref_qty_tag(node, f)
        if qt is None or qt in _BARE_X_QTY_TAGS:
            continue
        if qt in _SCALING_QTY_TAGS or phrase:
            return True
    return False


def _mana_amplifier(tree: ConceptTree) -> list[Signal]:
    """mana_amplifier — a mana DOUBLER (CR 106.4 / 605.1 / 614.1). Two typed
    arms:

    * a ``ProduceMana`` REPLACEMENT whose ``mana_modification`` is a
      ``Multiply`` ("it produces twice/three times as much … instead" — Mana
      Reflection x2, Virtue of Strength x3), beneficiary-gated (checklist #2:
      the replaced production must not be opponent-only);
    * a ``TapsForMana`` TRIGGER whose ``Mana`` effect carries
      ``produced.contribution == "Additional"`` ("whenever you tap a Swamp
      for mana, add an additional {B}" — Crypt Ghast) — the typed substrate
      carries the additional-contribution marker the OLD lossy IR folded into
      raw (the live ``_MANA_AMPLIFY_RAW`` tail), so this arm is a structural
      fidelity gain, not a port of the regex. The watched producer must be a
      ``Typed`` CLASS of permanents (every Swamp / every Mountain — Gauntlet
      of Might); a single ENCHANTED land's tap (``AttachedTo`` — Wild Growth,
      Utopia Sprawl) is a ramp Aura, not a doubling engine.

    The generic ramp lane keeps co-firing where applicable (additive, matching
    the live path). Doubling Cube's "double the amount of unspent mana" stays
    a ``live_only`` residue. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "replacement":
            vc = getattr(unit.node, "valid_card", None)
            if (
                mana_replacement_multiplier(unit.node) >= 2
                and filter_controller(vc) != "Opponent"
            ):
                return [Signal("mana_amplifier", "you", "", "", tree.name, "high")]
        if unit.origin == "trigger" and unit.trigger_event == "tapsformana":
            if tag_of(getattr(unit.node, "valid_card", None)) != "Typed":
                continue  # AttachedTo single-land Aura — ramp, not a doubler
            for c in unit.effect_concepts("ramp"):
                if produced_contribution(c.node) == "Additional":
                    return [
                        Signal("mana_amplifier", "you", "", c.raw, tree.name, "high")
                    ]
    return []


def _land_only_filter(filt: object) -> bool:
    """A filter whose CORE types are Land and nothing else (the ramp-vs-cheat
    carve-out, CR 305)."""
    cores = set(filter_core_types(filt))
    return bool(cores) and cores <= {"Land"}


def _extra_land_drop(tree: ConceptTree) -> list[Signal]:
    """extra_land_drop — a land PUT onto the battlefield (CR 305.2 / 116.2a /
    305.9: a put is not a play, so it bypasses the land-per-turn limit). Two
    typed arms mirroring the live structural pair:

    * a ``ChangeZone`` Hand→Battlefield whose moved subject is Land-only,
      controller you (Burgeoning's "put a land card from your hand onto the
      battlefield"); the "from hand OR graveyard" controller-any recovery
      stays ``live_only`` (checklist #6 keeps the you-gate);
    * a ``Dig`` whose ``destination`` is Battlefield with a Land filter
      (Elvish Rejuvenator's look-at-top-five put) — the ``to:hand`` dig
      (Planar Genesis) is card selection, NOT a land drop (checklist #2).

    The extra-land STATIC (Exploration's "play an additional land") is a
    different mechanic the live lane also excludes. Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("change_zone"):
            origin, dest = change_zone_dirs(c.node)
            sub = effect_filter(c.node)
            if (
                tag_of(c.node) == "ChangeZone"
                and origin == "Hand"
                and dest == "Battlefield"
                and _land_only_filter(sub)
                and filter_controller(sub) == "You"
            ):
                return [Signal("extra_land_drop", "you", "", c.raw, tree.name, "high")]
        for c in unit.effect_concepts("dig"):
            if getattr(c.node, "destination", None) == "Battlefield" and (
                "Land" in filter_core_types(getattr(c.node, "filter", None))
            ):
                return [Signal("extra_land_drop", "you", "", c.raw, tree.name, "high")]
    return []


def _group_mana(tree: ConceptTree) -> list[Signal]:
    """group_mana — mana given to a NON-controller player (CR 106.4): "each /
    that / target player adds …" (Mana Flare, Magus of the Vineyard, Heartbeat
    of Spring). The typed substrate carries the recipient the OLD lossy IR
    dropped (its ``Effect`` had no recipient field, so the live path fell back
    to the ``_GROUP_MANA_RAW`` regex): a ``Mana`` effect whose recipient tag
    names another player (:data:`_GROUP_MANA_RECIPIENTS` — ``TriggeringPlayer``
    for the taps-for-mana mirrors, ``ScopedPlayer`` for the each-player-upkeep
    forms, ``Player`` for a targeted gift). A controller-only producer (Sol
    Ring — no recipient field) never fires (checklist #5). Scope "each".
    """
    for c in tree.effect_concepts("ramp"):
        if recipient_tag(c.node) in _GROUP_MANA_RECIPIENTS:
            return [Signal("group_mana", "each", "", c.raw, tree.name, "high")]
    return []


def _draw_for_each(tree: ConceptTree) -> list[Signal]:
    """draw_for_each — a draw SCALING with a board count (CR 120 / 107.3):
    "draw a card for each creature you control" (Shamanic Revelation). The
    ``count`` is read structurally per draw NODE (granularity a): a fixed draw
    sharing an ability with a for-each rider (Tamiyo's Logbook — the for-each
    lives on ``cost_reduction``, not the draw) carries ``Fixed`` and never
    fires; a bare X-draw (Braingeyser — ``Ref → Variable``) is the cast cost,
    not a board scale (split-lane #4). Scope "you".
    """
    for c in tree.effect_concepts("draw"):
        if _is_scaling_count(c.node, ("count", "amount"), c.raw):
            return [Signal("draw_for_each", "you", "", c.raw, tree.name, "high")]
    return []


def _discard_outlet(tree: ConceptTree) -> list[Signal]:
    """discard_outlet — a SELF-loot / symmetric discard outlet (CR 701.9):
    fuel for YOUR graveyard (Faithless Looting; Dark Deal's each-player
    wheel). A ``Discard`` effect whose recipient is you/each, MINUS the
    opponent-directed forms (checklist #1/#5):

    * a recipient naming a targeted/opponent player (Mind Rot) reads
      ``opponents`` off :func:`discard_recipient_scope` — hand attack, out;
    * phase MISLABELS the modal / saga / per-opponent "each opponent
      discards" recipient as ``Controller`` while hanging ``player_scope:
      Opponent`` on the wrapper that owns the discard (The Eldest Reborn
      ch. 2, Aclazotz) — the wrapper actor read
      (:func:`effect_owner_player_scope`) rejects it STRUCTURALLY, replacing
      the live path's two raw/oracle veto regexes. A symmetric ``All`` actor
      (Dark Deal) is NOT vetoed — the wheel hits you too.

    Scope "you" (the lane convention — it fuels the controller's engine).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("discard"):
            if discard_recipient_scope(c.node) not in ("you", "each", None):
                continue
            owner = effect_owner_player_scope(getattr(unit, "node", None), c.node)
            if owner in _OPP_DISCARD_ACTORS:
                continue
            return [Signal("discard_outlet", "you", "", c.raw, tree.name, "high")]
    return []


def _mass_removal(tree: ConceptTree) -> list[Signal]:
    """mass_removal — a BOARD WIPE (CR 115.10 / 701.8 / 406.1). Four typed
    arms, each anchored on phase's first-class ``*All`` mass tag (the
    counter_kind=='all' discriminator of the old IR, carried structurally):

    * ``DestroyAll`` over a battlefield permanent type (Wrath of God);
    * ``ChangeZoneAll`` → Exile with no graveyard origin (Merciless
      Eviction) — a graveyard-zone mass exile (Living Death) is GY
      recursion, NOT a wipe (checklist #2);
    * ``DamageAll`` over a Creature/Permanent subject (Blasphemous Act,
      Pyroclasm);
    * a NEGATIVE symmetric ``PumpAll`` over creatures (Languish's "all
      creatures get -4/-4") — the typed substrate carries the negative amount
      (``power: Fixed -4``), so the live ``_MASS_DEBUFF_RAW`` raw arm reads
      structurally here (a fidelity gain over the spec's live-only
      expectation). Three sub-gates keep the sweep genuine: the
      controller-less gate mirrors the live raw's "ALL creatures" anchor (a
      one-sided "creatures your opponents control get -1/-1" dip — Cower in
      Fear — is debuff_makers); the NEGATIVE-TOUGHNESS gate is the lethality
      tell (CR 704.5f — a "-2/-0" combat dip like Hydrolash never kills); and
      the attachment-predicate veto drops the single-Aura "+1/-1" shifter
      (Flowstone Blade's enchanted creature — one target, not a board).

    The type gate (:data:`_MASS_REMOVAL_TYPES`) keeps "destroy all LANDS"
    (Armageddon) in land_destruction; a controller-You mass exile (Day of the
    Dragons' own-board swap) is a drawback, not removal (checklist #6). Two
    COMBAT-SCOPE vetoes keep the debuff arm off one-combat tricks phase
    flattens to a bare board sweep by dropping the "blocking it" clause
    (phase_parse_bug [P12]): a ``becomes_blocked``/``blocks`` trigger unit
    (Baneblade Scoundrel) and a ``WithoutKeyword:Flanking`` blocker filter —
    the flanking template, whose -1/-1 hits only blocking creatures per CR
    702.25a (Knight of Valor). Scope "you".
    """
    for unit in tree.units:
        combat_scope = unit.trigger_event in ("becomes_blocked", "blocks")
        for c in unit.iter_concepts():
            if c.role != "effect":
                continue
            t = tag_of(c.node)
            sub = effect_filter(c.node)
            cores = set(filter_core_types(sub))
            ctrl = filter_controller(sub)
            raw = c.raw
            hit = [Signal("mass_removal", "you", "", raw, tree.name, "high")]
            if t == "DestroyAll" and ctrl != "You" and cores & _MASS_REMOVAL_TYPES:
                return hit
            if t == "ChangeZoneAll" and ctrl != "You":
                origin, dest = change_zone_dirs(c.node)
                gy = origin == "Graveyard" or ("Graveyard" in filter_inzone_zones(sub))
                if dest == "Exile" and not gy and cores & _MASS_REMOVAL_TYPES:
                    return hit
            if t == "DamageAll" and cores & {"Creature", "Permanent"}:
                return hit
            toughness = _fixed_pt(c.node, "toughness") if t == "PumpAll" else None
            if (
                toughness is not None
                and toughness < 0
                and "Creature" in cores
                and ctrl is None
                and not combat_scope
                and "Flanking" not in filter_without_keywords(sub)
                and not (set(filter_predicates(sub)) & _DEBUFF_SINGLE_AURA_PREDS)
            ):
                return hit
    return []


def _fixed_pt(node: TypedMirrorNode, field: str) -> int | None:
    """The fixed P/T component of a Pump-style node (``toughness: Fixed N``),
    ``None`` when absent/dynamic. The mass-debuff arm gates on a NEGATIVE
    toughness — the lethality tell (CR 704.5f: a creature with toughness 0 or
    less dies; a "-2/-0" power dip never kills)."""
    p = getattr(node, field, None)
    if tag_of(p) == "Fixed":
        v = getattr(p, "value", None)
        return v if isinstance(v, int) else None
    return None


def _mass_bounce(tree: ConceptTree) -> list[Signal]:
    """mass_bounce — a BOARD-WIDE bounce (CR 115.10): ``BounceAll`` over a
    generic Creature/Permanent subject (Evacuation, Devastation Tide). The
    single-target ``Bounce`` (Boomerang; Cyclonic Rift's base mode) is
    bounce_tempo, not this lane; a graveyard-recursion subject (``InZone`` /
    ``Owned`` predicate — "return all creature cards from graveyards") is
    recursion (CR 404), excluded (checklist #2). KNOWN RESIDUE: Cyclonic
    Rift's Overload each-mode is a phase modal-alt-cost parse drop
    (phase_parse_bug) — the crosswalk correctly reads only the targeted base
    mode. Scope "any" (the sweep convention).
    """
    for c in tree.effect_concepts("bounce"):
        if tag_of(c.node) != "BounceAll":
            continue
        sub = effect_filter(c.node)
        if not (set(filter_core_types(sub)) & {"Creature", "Permanent"}):
            continue
        preds = set(filter_predicates(sub))
        if "InZone" in preds or "Owned" in preds:
            continue
        return [Signal("mass_bounce", "any", "", c.raw, tree.name, "high")]
    return []


def _exile_removal(tree: ConceptTree) -> list[Signal]:
    """exile_removal — a SINGLE-TARGET exile of a battlefield permanent (CR
    406.1 "without any way to return" / 115.1): Swords to Plowshares, Path to
    Exile. A ``ChangeZone`` → Exile over a permanent-typed subject, with the
    live arm's five vetoes read STRUCTURALLY (granularity a — the sibling
    scans):

    * **blink** — exiling YOUR OWN (``Owned: You`` / controller-you subject —
      Cloudshift) OR a sibling battlefield RETURN of the SAME object
      (``ParentTarget``/``TrackedSet`` target — Eldrazi Displacer; checklist
      #9). A sibling put of a DIFFERENT object (Path to Exile's searched land
      — target ``Any``) does not veto;
    * **zone** — a Graveyard/Hand origin or ``InZone`` subject (GY-hate /
      cage setup — Bojuka Bog), not battlefield removal (checklist #2);
    * **mass** — the ``ChangeZoneAll`` wipe is mass_removal (a different
      tag, structurally disjoint);
    * **haunt** — ``ExileHaunting`` is its own phase tag, never this
      concept;
    * **clone-from-mill** — a sibling ``BecomeCopy`` marks a copy setup, not
      removal (Shadow Kin).

    Scope "you".
    """
    for unit in tree.units:
        czs = unit.effect_concepts("change_zone")
        sib_return = any(
            change_zone_dirs(s.node)[1] == "Battlefield"
            and tag_of(getattr(s.node, "target", None)) in _RETURN_TARGET_TAGS
            for s in czs
        )
        sib_clone = unit.has_effect("become_copy")
        for c in czs:
            if tag_of(c.node) != "ChangeZone":
                continue
            origin, dest = change_zone_dirs(c.node)
            if dest != "Exile":
                continue
            sub = effect_filter(c.node)
            if not (set(filter_core_types(sub)) & _PERMANENT_TYPES):
                continue
            if filter_controller(sub) == "You" or (
                filter_owned_controller(sub) == "You"
            ):
                continue  # blink-your-own (CR 603.6e), not removal
            if origin in ("Graveyard", "Hand") or (
                set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}
            ):
                continue  # GY-hate / cage setup (CR 406.2), not removal
            if sib_return or sib_clone:
                continue
            return [Signal("exile_removal", "you", "", c.raw, tree.name, "high")]
    return []


def _lands_matter(tree: ConceptTree) -> list[Signal]:
    """lands_matter — a payoff SCALING with lands (CR 305 / 604.3): a count
    operand whose counted population names Land ("create a Plant token for
    each land you control" — Avenger of Zendikar; a lands-count CDA). The
    live arm carries NO controller gate; per checklist #6 the crosswalk adds
    an opponent-direction veto proactively — a "power equal to the number of
    nonbasic lands your OPPONENTS / the chosen player controls" body
    (Wilderness Elemental, Pallimud's ``SourceChosenPlayer``) is a punisher,
    not a your-lands build-around. The parity cost is flagged for
    adjudication, not silently absorbed. Scope "you".
    """
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        cf = count_operand_filter(c.node)
        if cf is None or "Land" not in filter_core_types(cf):
            continue
        if filter_controller(cf) in _OPP_COUNT_CONTROLLERS:
            continue
        return [Signal("lands_matter", "you", "", c.raw, tree.name, "high")]
    return []


# Sacrificed-token subtype → the sacrifice-PAYOFF lane (role-split per
# ADR-0034 — the ``make_token`` MAKER halves are already ported).
_SAC_TOKEN_MATTERS: dict[str, str] = {
    "treasure": "treasure_matters",
    "blood": "blood_matters",
}


def _resource_token_matters(tree: ConceptTree) -> list[Signal]:
    """treasure_matters / blood_matters — the sacrifice-PAYOFF half of the
    predefined-token lanes (CR 111.10 / 701.21, role-split per ADR-0034): a
    ``Sacrifice`` whose sacrificed filter carries the Treasure/Blood subtype.
    Two roles fire:

    * a sacrifice EFFECT ("you may sacrifice a Blood token. If you do…" —
      Wedding Security), edict-gated (checklist #1: an "each opponent
      sacrifices" direction is not your payoff);
    * a sacrifice COST ("Sacrifice five Treasures: …" — Jolene, the Plunder
      Queen), read through ``Composite`` cost nesting — a cost is always paid
      by the controller (CR 701.21a), the cleanest payoff tell. The live path
      reads effects only, so the cost arm is a structural widening (flagged
      in the shadow diff, not silently absorbed).

    A pure token MAKER (Dockside Extortionist) fires ``*_makers``, never this.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "sacrifice" or _sac_is_edict(unit, c.node):
                continue
            for st in filter_subtypes(effect_filter(c.node)):
                key = _SAC_TOKEN_MATTERS.get(st.lower())
                if key:
                    fire(key, c.raw)
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) != "Sacrifice":
                continue
            for st in filter_subtypes(getattr(leaf, "target", None)):
                key = _SAC_TOKEN_MATTERS.get(st.lower())
                if key:
                    fire(key, "")
    return out


def _is_anthem_group_filter(filt: object) -> bool:
    """A creature-GROUP anthem subject (CR 604.3 / 613.4): Creature in core
    types AND (controller you OR ``Another`` OR subtyped) AND not an
    opponent-board debuff target. A single-target pump (controller any, no
    Another/subtype) fails the group test."""
    if filt is None or filter_controller(filt) == "Opponent":
        return False
    if "Creature" not in filter_core_types(filt):
        return False
    return (
        filter_controller(filt) == "You"
        or "Another" in filter_predicates(filt)
        or bool(filter_subtypes(filt))
    )


def _anthem_static(tree: ConceptTree) -> list[Signal]:
    """anthem_static — a STATIC +N/+N over a creature group (CR 604.3 / 613.4
    layer 7c): Glorious Anthem, Goblin King's subtyped "Other Goblins". Reads
    the top-level static units' plain-int P/T mods (granularity b — the
    ``affected`` subject and the mod values together): every present value
    must be non-negative (a -2/-2 token hoser — Virulent Plague — is a
    debuff, checklist #4), the subject must be a creature GROUP
    (:func:`_is_anthem_group_filter` — a single-target/activated pump is
    self_pump or a trick, and an opponent-board shrink is scoped out,
    checklist #6). One-shot until-end-of-turn pumps live on spell/trigger
    units, never on a ``static`` origin unit, so the origin gate mirrors the
    live ``ab.kind == 'static'``. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "static":
            continue
        pumps = [c for c in unit.statics if c.concept == "pump"]
        vals = [mod_value(c.node) for c in pumps]
        ints = [v for v in vals if v is not None]
        if not ints or any(v < 0 for v in ints):
            continue
        if _is_anthem_group_filter(getattr(unit.node, "affected", None)):
            return [Signal("anthem_static", "you", "", "", tree.name, "high")]
    return []


def _pump_scaling_lanes(tree: ConceptTree) -> list[Signal]:
    """scaling_pump / count_anthem — a +X/+X that SCALES with a board count
    (CR 107.3 / 613.4b). Two typed surfaces:

    * a mass ``PumpAll`` whose power/toughness is a scaling ``Ref``;
    * a dynamic P/T modification site (``AddDynamicPower`` — Craterhoof's
      nested one-shot static, Commander's Insignia's continuous anthem) whose
      ``value`` scales; the ``Set*`` forms are */* CDA bodies, excluded.

    ``count_anthem`` is the TEAM-subject subset (the site's ``affected`` /
    the pump's subject is a generic creatures-you-control filter — Hold the
    Gates, Commander's Insignia); a symmetric controller-any global (Coat of
    Arms) or single-target firebreathing stays scaling_pump-or-nothing
    (checklist #6). Bare-X pumps (a "-X/-X" activation — ``Variable``) never
    scale (split-lane #4). Both scope "you".
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.effect_concepts("pump"):
        if tag_of(c.node) == "PumpAll" and _is_scaling_count(
            c.node, ("power", "toughness"), c.raw
        ):
            fire("scaling_pump", c.raw)
            if _is_generic_creature_filter(effect_filter(c.node)):
                fire("count_anthem", c.raw)
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in _DYNAMIC_PT_MODS:
                continue
            raw = _site_raw(sdef)
            if not _is_scaling_count(mod, ("value",), raw):
                continue
            fire("scaling_pump", raw)
            if _is_generic_creature_filter(getattr(sdef, "affected", None)):
                fire("count_anthem", raw)
    return out


def _site_raw(sdef: object) -> str:
    """A static-def site's grounding clause (its ``description``, else "")."""
    desc = getattr(sdef, "description", None)
    return desc if isinstance(desc, str) else ""


def _self_pump(tree: ConceptTree) -> list[Signal]:
    """self_pump — a firebreather / self-grow mana-sink (CR 122.1 / 613): an
    ACTIVATED ability pumping SELF ("{R}: this creature gets +1/+0" — Shivan
    Dragon) or placing a +1/+1 counter on SELF ("{4}: Put a +1/+1 counter on
    this creature" — Walking Ballista). The activated-only gate is the
    mana-sink anchor (a static team anthem — Glorious Anthem — and a one-shot
    spell pump are different lanes); the self-anchor is the typed ``SelfRef``
    target (a "target creature" pump is a granted trick, not self). Scope
    "you".
    """
    for unit in tree.units:
        if unit.origin != "ability" or unit.kind != "Activated":
            continue
        for c in unit.effects:
            t = tag_of(c.node)
            tgt = tag_of(getattr(c.node, "target", None))
            if t == "Pump" and tgt in (None, "SelfRef"):
                return [Signal("self_pump", "you", "", c.raw, tree.name, "high")]
            if (
                t == "PutCounter"
                and counter_kind(c.node).upper() == "P1P1"
                and tgt == "SelfRef"
            ):
                return [Signal("self_pump", "you", "", c.raw, tree.name, "high")]
    return []


def _is_team_buff_filter(filt: object) -> bool:
    """The team_buff anthem subject (CR 604.3): GENERIC creatures YOU control
    — no subtypes (tribal is type_matters), predicates at most
    NonToken/Another/Other (Always Watching stays in; an Attacking/color/
    equipped narrowing fails). Mirrors ``_signals_ir._is_team_buff_grant``."""
    return (
        filter_controller(filt) == "You"
        and "Creature" in filter_core_types(filt)
        and not filter_subtypes(filt)
        and set(filter_predicates(filt)) <= _TEAM_BUFF_OK_PREDS
    )


def _team_buff(tree: ConceptTree) -> list[Signal]:
    """team_buff — the BROAD evergreen-keyword union anthem (CR 604.3 / 702):
    "creatures you control have/gain <evergreen keyword>" (Akroma's Memorial,
    Always Watching; Craterhoof's one-shot "gain trample"). Reads every
    modification site's ``AddKeyword`` whose keyword is a plain evergreen
    string (:data:`_TEAM_BUFF_GRANT_KW`) over a generic your-team subject
    (:func:`_is_team_buff_filter`) — a tribal grant ("Sliver creatures you
    control gain …") or a single-target grant (an effect target, never a
    generic your-team ``affected``) stays out (checklist #6). The variant-
    parameterized keywords (Protection-from-X, Ward-{N}) are non-string nodes
    — a documented residue. Scope "you".
    """
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
                return [
                    Signal("team_buff", "you", "", _site_raw(sdef), tree.name, "high")
                ]
    return []


def _cheat_into_play(tree: ConceptTree) -> list[Signal]:
    """cheat_into_play — put a card onto the battlefield WITHOUT casting it
    (CR 110.2 / 400.7): Sneak Attack (hand), Elvish Piper, Bribery (an
    opponent's library — control is orthogonal, the cheat is still yours). A
    ``ChangeZone`` Hand/Library→Battlefield, with three carve-outs:

    * **land / type evidence** — a Land-only put is ramp (extra_land_drop;
      checklist #4). The cheated TYPE is read off the effect's own filter,
      falling back to a sibling tutor/dig selector (Bribery's
      ``SearchLibrary`` names the Creature; a fetchland's names the Land).
      When NEITHER names a type (phase drops the "basic land" restriction to
      ``Any`` — Wild Endeavor, Planar Engineering), the lane does NOT guess —
      no fire (the drop is supplement-fixable, reported, never a heuristic);
    * **directed search** — a search whose ``target_player`` is ANOTHER
      player (Settle the Wreckage's compensation basics) is the punished
      player's fetch, not your cheat (checklist #1);
    * **opening hand** — the "begin the game with it on the battlefield"
      setup is a ``BeginGame`` ability kind (Leyline of Anticipation), a
      one-time pre-game action, not a cheat ENGINE — read structurally off
      the typed kind (the live path needed a raw regex).

    Two batch-9 follow-ups widen the type evidence, both typed / zero-guess:

    * **subtype-only filters** (fix a) — when cores are EMPTY, a non-empty
      SUBTYPE set that names no land subtype (:data:`_LAND_SUBTYPES`) is
      non-Land type evidence (Academy Researchers' ``{Subtype: Aura}`` filter
      — phase's filter is correct and complete, CR 205.3); a subtype set
      touching a land subtype still never fires (Nature's Lore is already
      excluded by its Land core);
    * **the Dig arm** (fix b) — a ``Dig`` whose ``destination`` is Battlefield
      with non-empty, non-Land-only cores is the look-at-top-N put
      (Aethermage's Touch's "put a creature card onto the battlefield" — a
      put, not a cast, CR 401.1); the destination gate keeps Aetherworks
      Marvel's dig-and-CAST (destination None) out, the core gate keeps
      Elvish Rejuvenator's land put in extra_land_drop, and a no-filter dig
      (filter ``Any``) has no type evidence — never guess.

    A Graveyard origin is reanimation (a different lane, checklist #2). Scope
    "you".
    """
    for unit in tree.units:
        if unit.kind == "BeginGame":
            continue
        for c in unit.effect_concepts("change_zone"):
            if tag_of(c.node) != "ChangeZone":
                continue
            origin, dest = change_zone_dirs(c.node)
            if dest != "Battlefield" or origin not in ("Hand", "Library"):
                continue
            cores = set(filter_core_types(effect_filter(c.node)))
            if not cores:
                cores = _sibling_selector_cores(unit)
            if not cores:
                # Fix (a): subtype-only type evidence (cores empty on both the
                # effect's own filter and the sibling selector).
                subs = {s.lower() for s in filter_subtypes(effect_filter(c.node))}
                if not subs:
                    subs = {s.lower() for s in _sibling_selector_subtypes(unit)}
                if not subs or subs & _LAND_SUBTYPES:
                    continue  # no type evidence / a land put — never guess
            elif cores <= {"Land"}:
                continue  # land carve-out (ramp, not a cheat)
            if _directed_search_sibling(unit):
                continue  # another player's compensation fetch, not yours
            return [Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")]
        # Fix (b): the non-land Dig→Battlefield arm (mirrors _extra_land_drop's
        # dig arm with the complementary type gate).
        for c in unit.effect_concepts("dig"):
            if getattr(c.node, "destination", None) != "Battlefield":
                continue
            cores = set(filter_core_types(getattr(c.node, "filter", None)))
            if not cores or cores <= {"Land"}:
                continue  # land put (extra_land_drop) / no evidence — no guess
            return [Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")]
    return []


def _sibling_selector_cores(unit: AbilityUnit) -> set[str]:
    """The CORE types a sibling tutor/dig selector names (the search half of a
    split search-into-play — Bribery's Creature, a fetchland's Land)."""
    cores: set[str] = set()
    for c in unit.effects:
        if c.concept in ("tutor", "dig"):
            cores |= set(filter_core_types(effect_filter(c.node)))
    return cores


def _sibling_selector_subtypes(unit: AbilityUnit) -> set[str]:
    """The SUBTYPE words a sibling tutor/dig selector names — the fallback
    type evidence when the put's own filter carries none (batch-9 follow-up
    a)."""
    subs: set[str] = set()
    for c in unit.effects:
        if c.concept in ("tutor", "dig"):
            subs |= set(filter_subtypes(effect_filter(c.node)))
    return subs


def _directed_search_sibling(unit: AbilityUnit) -> bool:
    """Whether a sibling ``SearchLibrary`` directs ANOTHER player to search.

    A ``target_player`` naming a directed-PLAYER tag (:data:`_DIRECTED_
    SEARCHERS`) always vetoes. ``ParentTargetController`` vetoes ONLY when the
    unit carries a player-TARGET marker (batch-9 follow-up c): Settle the
    Wreckage targets a PLAYER (its wipe filter carries ``controller:
    "TargetPlayer"``), so "that player may search" is the WIPED player's
    compensation fetch; Arcum Dagsson targets an OBJECT (the sacrificed
    artifact creature — no player-target anywhere in the unit), so the
    "controller" the search resolves through is routinely YOU (CR 115.1 — the
    ability's controller chooses the target) and the put is your cheat. A
    ``Typed`` library OWNER (Bribery — YOU search target opponent's library)
    is not directed: the controller performs the search and the put stays
    yours.
    """
    ptc = False
    for c in unit.effects:
        if c.concept != "tutor":
            continue
        t = tag_of(getattr(c.node, "target_player", None))
        if t in _DIRECTED_SEARCHERS:
            return True
        if t == "ParentTargetController":
            ptc = True
    return ptc and _unit_targets_player(unit)


def _unit_targets_player(unit: AbilityUnit) -> bool:
    """Whether any effect in the unit targets a PLAYER — a filter carrying
    ``controller: "TargetPlayer"`` (Settle the Wreckage's "all attacking
    creatures target player controls"). The marker that makes a sibling
    ``ParentTargetController`` search resolve through that targeted player,
    not you."""
    return any(
        filter_controller(effect_filter(c.node)) == "TargetPlayer" for c in unit.effects
    )


def _impulse_top_play(tree: ConceptTree) -> list[Signal]:
    """impulse_top_play — a one-shot "exile the top, you may play/cast it"
    engine (CR 601.3b / 116): Light Up the Stage, Act on Impulse, Etali. The
    typed anchor is granularity (a): ONE non-static unit carrying BOTH an
    ``ExileTop`` effect AND its play-permission sibling — a
    ``GrantCastingPermission`` of ``PlayFromExile`` (the impulse grant) or a
    ``CastFromZone`` (Etali's cast-from-among). The exiled library must be
    reachable as YOURS: an ``ExileTop`` whose ``player`` names another player
    only (``ParentTarget`` — Gonti, Night Minister steals from the damaged
    opponent's library) is a theft engine, not your impulse (checklist #5).
    The ONGOING top-play statics (Bolas's Citadel) are a static-mode unit,
    structurally disjoint → play_from_top (checklist #3: the static /
    non-static split is the discriminator). Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "static":
            continue
        tops = [c for c in unit.effects if c.concept == "exile_top"]
        if not tops or all(
            tag_of(getattr(c.node, "player", None)) in _OPP_TOP_OWNERS for c in tops
        ):
            # No exile-the-top, or another player's library only (Gonti,
            # Night Minister's theft — checklist #5): not YOUR impulse.
            continue
        for c in unit.effects:
            if c.concept == "cast_from_zone" or (
                c.concept == "grant_cast_permission"
                and permission_tag(c.node) == "PlayFromExile"
            ):
                return [Signal("impulse_top_play", "you", "", c.raw, tree.name, "high")]
    return []


def _play_from_top(tree: ConceptTree) -> list[Signal]:
    """play_from_top — the ONGOING permission to play/cast from the top of
    your library (CR 116 / 601.3b): Bolas's Citadel, Future Sight. Reads
    phase's dedicated ``TopOfLibraryCastPermission`` static MODE
    (:func:`static_mode_tag`) — a pure typed read where the live path needed
    a recovered ``from:library`` zone marker. A granted-impulse static
    (Capricious Sliver — a ``Continuous`` mode granting an exile-the-top
    trigger) carries a different mode and never fires; the one-shot impulse
    is the sibling lane. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "static" and (
            static_mode_tag(unit.node) == "TopOfLibraryCastPermission"
        ):
            return [Signal("play_from_top", "you", "", "", tree.name, "high")]
    return []


def _counter_manipulation(tree: ConceptTree) -> list[Signal]:
    """counter_manipulation — a +1/+1 / -1/-1 counter MOVE or REMOVE (CR
    122.1 / 122.6): Bioshift's p1p1 move; Walking Ballista's "Remove a +1/+1
    counter from this creature:" cost; Carnifex Demon's m1m1 remove-cost. The
    kind gate (:data:`_PT_COUNTER_KINDS`) is the whole discriminator vs
    charge/oil/loyalty/fade spends (split-lane #4 — Tangle Wire's fade
    remove, Power Conduit's kindless ``Any`` remove stay out). Three typed
    surfaces: a ``MoveCounters`` / ``RemoveCounter`` EFFECT, and a
    ``RemoveCounter`` activation COST (read through ``Composite`` nesting —
    the remove-as-cost the OLD lossy IR needed a supplement re-parse for).
    Scope "you".
    """
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) in ("MoveCounters", "RemoveCounter") and (
                counter_kind_any(c.node) in _PT_COUNTER_KINDS
            ):
                return [
                    Signal("counter_manipulation", "you", "", c.raw, tree.name, "high")
                ]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "RemoveCounter" and (
                counter_kind_any(leaf) in _PT_COUNTER_KINDS
            ):
                return [
                    Signal("counter_manipulation", "you", "", "", tree.name, "high")
                ]
    return []


# ── Batch 9 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# Land subtypes (CR 205.3i — basic + nonbasic): the fix-(a) membership test
# that keeps a SUBTYPE-only put from resurrecting a land put as a cheat.
_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "gate",
        "desert",
        "lair",
        "locus",
        "mine",
        "power-plant",
        "tower",
        "urza's",
        "cave",
        "sphere",
        "town",
    }
)
# Draw recipients naming EVERY player (CR 121.1) — the group_hug_draw
# direction. ``ScopedPlayer`` is deliberately ABSENT: an each-player Phase
# trigger's "that player draws" (Howling Mine) is the card_draw_engine
# each-arm, and the live path routes it to target_player_draws, not the
# group-hug gift.
_EACH_DRAW_RECIPIENTS: frozenset[str] = frozenset({"Each", "AllPlayers", "EachPlayer"})
# Draw recipients naming a DIRECTED single player (CR 121.1) — the
# target_player_draws forced-draw direction (Bloodgift Demon's ``Player``).
_TARGETED_DRAW_TAGS: frozenset[str] = frozenset({"Player", "ParentTarget", "Target"})
# Combat-frame trigger events (CR 508 / 509.3a) — the combat_buff_engine
# anchor. ``deals_damage`` is DELIBERATELY absent so Renown / the separate
# self_counter_grow shapes don't over-fire (mirrors the live exclusion).
_COMBAT_BUFF_EVENTS: frozenset[str] = frozenset(
    {"attacks", "blocks", "becomes_blocked"}
)
# Land-to-graveyard payoff trigger events (CR 701.21a / 603.6c).
_LAND_SAC_EVENTS: frozenset[str] = frozenset({"dies", "leaves", "sacrificed"})
# Effect targets naming the granted trigger's own source (mirrors
# ``crosswalk._SELF_RETURN_TARGETS`` for the self_death_payoff exclusion).
_SELF_RETURN_TAGS: frozenset[str] = frozenset({"SelfRef", "TriggeringSource"})
# Spell-cast keywords (CR 702 — flash 702.8, flashback 702.34, cascade
# 702.85, …): an ``AddKeyword`` grant of one of these is a grant to a SPELL /
# castable card, never a battlefield keyword anthem (team_buff). Normalized
# lower/spaceless/hyphenless (phase spells ``JumpStart``).
_SPELL_GRANT_KEYWORDS: frozenset[str] = frozenset(
    {
        "flashback",
        "flash",
        "cascade",
        "storm",
        "replicate",
        "conspire",
        "jumpstart",
        "retrace",
        "convoke",
        "improvise",
        "delve",
        "demonstrate",
        "casualty",
        "rebound",
        "escape",
        "affinity",
        "buyback",
        "madness",
    }
)
# RevealHand static ``who`` values that reach an OPPONENT's hand (CR 402.3):
# Telepathy's ``Opponents``, Zur's Weirding's symmetric ``AllPlayers`` (it
# reveals their hands too). A ``Controller`` self-reveal (Enduring Renewal)
# is not disruption.
_REVEAL_WHO_OPP: frozenset[str] = frozenset({"Opponents", "AllPlayers"})


def _discard_watch_is_opponent(unit: AbilityUnit) -> bool:
    """Whether a discarded-family trigger watches an OPPONENT's discard.

    phase carries the watched discarder on ``valid_target`` (Archfiend of
    Ifnir — ``Controller``) or on ``valid_card``'s controller (Megrim —
    ``Typed controller=Opponent``); either naming the opponent routes the
    trigger to the punisher lane (checklist #5 — the recipient nodes, never
    the mislabeled trigger_scope).
    """
    return (
        trigger_scope(unit.node) == "opponents"
        or trigger_subject_scope(unit.node) == "opponents"
    )


def _discard_matters(tree: ConceptTree) -> list[Signal]:
    """discard_matters — the SELF/any-scope discard PAYOFF (CR 702.29a:
    cycling IS "[Cost], Discard this card: Draw a card", so a cycle is a
    discard — phase's ``CycledOrDiscarded`` joins ``Discarded`` /
    ``DiscardedAll`` under the derived ``discarded`` event): "whenever you
    cycle or discard a card, …" (Archfiend of Ifnir). DISJOINT from the
    opponent-watching punisher (Megrim → the ``opponent_discard`` trigger
    arm) by the same watcher read. A loot OUTLET (Careful Study) has no
    discarded trigger — it stays discard_makers. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event != "discarded":
            continue
        if not _discard_watch_is_opponent(unit):
            return [Signal("discard_matters", "you", "", "", tree.name, "high")]
    return []


def _opponent_draw_matters(tree: ConceptTree) -> list[Signal]:
    """opponent_draw_matters — the wheel-punisher payoff (CR 121.1):
    "whenever an opponent draws a card, …" (Nekusar, Underworld Dreams). The
    complementary scope gate to the ported ``draw_matters`` (you/any-scope
    drawn watcher — Niv-Mizzet) — the two stay set-disjoint. Scope
    "opponents".
    """
    for unit in tree.units:
        if unit.trigger_event == "drawn" and trigger_scope(unit.node) == "opponents":
            return [
                Signal("opponent_draw_matters", "opponents", "", "", tree.name, "high")
            ]
    return []


def _is_self_return_effect(c: ConceptNode) -> bool:
    """A ``ChangeZone`` back to the battlefield targeting the trigger's own
    source — the dies_recursion return arm (Kitchen Finks' persist), NOT a
    death VALUE payoff."""
    return (
        tag_of(c.node) == "ChangeZone"
        and getattr(c.node, "destination", None) == "Battlefield"
        and tag_of(getattr(c.node, "target", None)) in _SELF_RETURN_TAGS
    )


def _is_shuffle_back_effect(c: ConceptNode) -> bool:
    """A zone move whose destination is the LIBRARY — the "shuffle it / your
    graveyard into its owner's library" self-protection rider (Kozilek,
    Serra Avatar — CR 701.19b), not a death VALUE payoff."""
    return (
        tag_of(c.node) in ("ChangeZone", "ChangeZoneAll")
        and getattr(c.node, "destination", None) == "Library"
    )


def _self_death_payoff(tree: ConceptTree) -> list[Signal]:
    """self_death_payoff — own-death VALUE (CR 700.4 dies / 603.6c): "when
    this creature dies, <payoff>" (Solemn Simulacrum's draw, Kokusho's
    drain). Four gates mirror the live split: the ``SelfRef`` watcher
    excludes the aristocrats lane (``death_matters`` — a subject-bearing
    watcher, Blood Artist); the recognized-effect gate drops unparsed
    bodies; the SELF-RETURN exclusion keeps the undying/persist return
    (Kitchen Finks — ``ChangeZone`` back to the battlefield) in
    ``dies_recursion``, not here; and the SHUFFLE-BACK exclusion drops the
    "shuffle … into its owner's library" protection rider (Kozilek — a
    dies-to-Library move is self-preservation, not value). Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "dies":
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) != "SelfRef":
            continue
        for c in unit.effects:
            if (
                c.concept == OTHER
                or _is_self_return_effect(c)
                or _is_shuffle_back_effect(c)
            ):
                continue
            return [Signal("self_death_payoff", "you", "", c.raw, tree.name, "high")]
    return []


def _dies_recursion(tree: ConceptTree) -> list[Signal]:
    """dies_recursion — SELF-recursion on death (CR 702.93a undying /
    702.79a persist: "when this permanent is put into a graveyard from the
    battlefield, … return it to the battlefield"). Fully structural, two
    arms sharing one predicate (:func:`is_dies_return_trigger`):

    * the card's OWN dies-return trigger — phase expands undying (Young
      Wolf) and persist (Kitchen Finks) to exactly this shape, so the
      keyword bearers read structurally (memory: mirror=backup — prefer the
      structural shape over a keyword field-lookup);
    * the GRANT form — a ``GrantTrigger`` modification whose granted trigger
      is that same dies-return shape (Feign Death), reached tree-preservingly
      through :func:`iter_mod_sites`.

    The destination gate (Battlefield) keeps a dies→hand return out; a
    GY→battlefield reanimate of OTHERS (Reanimate) has no SelfRef dies
    watcher and stays creature_recursion/reanimator. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and is_dies_return_trigger(unit.node):
            return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "GrantTrigger" and is_dies_return_trigger(
                getattr(mod, "trigger", None)
            ):
                return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
    return []


def _creature_recursion(tree: ConceptTree) -> list[Signal]:
    """creature_recursion — loop-a-creature (CR 700.4 / 401.4 / 404). Two
    typed arms mirroring the live structural pair:

    * **reanimation** — a ``ChangeZone`` / ``ChangeZoneAll`` Graveyard→
      Battlefield over a Creature-cored filter (Alesha's attack trigger;
      Reanimate — scope stays "you" even over an opponent's graveyard: you
      control the returned creature);
    * **recall** — a ``Bounce`` (→hand) or ``PutAtLibraryPosition``
      (→library) whose subject is a Creature card IN a graveyard (the
      ``InZone: Graveyard`` predicate — Soul Salvage); the graveyard-zone
      predicate is required (a battlefield bounce is tempo, not recursion).

    Gate #6: subject controller ≠ Opponent (an opponents'-graveyard-ONLY
    pull is graveyard hate, not your loop). A type-less "target card"
    (Regrowth) has no Creature core — no fire. Scope "you".
    """
    for unit in tree.units:
        for c in unit.effects:
            t = tag_of(c.node)
            sub = effect_filter(c.node)
            if filter_controller(sub) == "Opponent":
                continue
            if "Creature" not in filter_core_types(sub):
                continue
            if t in ("ChangeZone", "ChangeZoneAll"):
                origin, dest = change_zone_dirs(c.node)
                if origin == "Graveyard" and dest == "Battlefield":
                    return [
                        Signal(
                            "creature_recursion", "you", "", c.raw, tree.name, "high"
                        )
                    ]
            if t in ("Bounce", "PutAtLibraryPosition") and (
                "Graveyard" in filter_inzone_zones(sub)
            ):
                return [
                    Signal("creature_recursion", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _draw_engine_scope(unit: AbilityUnit, c: ConceptNode) -> str:
    """The card_draw_engine scope: "each" when the draw reaches every player
    (an each-player Phase trigger's ``ScopedPlayer`` — Howling Mine; an
    explicit each-player recipient; a ``player_scope: All`` wrapper — Temple
    Bell), else "you"."""
    if recipient_tag(c.node) == "ScopedPlayer":
        return "each"
    if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS:
        return "each"
    if effect_owner_player_scope(unit.node, c.node) == "All":
        return "each"
    return "you"


def _card_draw_engine(tree: ConceptTree) -> list[Signal]:
    """card_draw_engine — recurring / BULK card advantage, NOT a cantrip (CR
    121.1 / 121.2). The live path is a byte-identical kept mirror whose "no
    clean structural shape" justification is STALE for the lossless
    substrate: the tree preserves the Phase-mode trigger unit CONTAINING the
    Draw (granularity a — the anchor and the Draw share a unit). Three
    typed arms:

    * a ``Draw`` whose typed ``count`` is ≥2 or dynamic ("draw three cards"
      — Divination; "draw cards equal to …"), excluding a one-shot ETB unit
      (Elvish Visionary's enters-draw never fires, mirroring the live
      mirror's ETB skip) — a bare cantrip (Opt, count 1) never fires;
    * ANY ``Draw`` inside a ``Phase``-mode trigger unit ("at the beginning
      of …, draw" — Phyrexian Arena; Howling Mine's each-player draw step →
      scope "each" via the ``ScopedPlayer`` recipient);
    * a Draw-REPLACEMENT unit ("if you would draw a card, … draw two cards
      instead" — Alhammarret's Archive; the replacement's ``event`` field is
      the typed anchor).

    Expected shadow posture: recall gains over the mirror are the desired
    structural improvement — adjudicated via the harness, not drift.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for unit in tree.units:
        is_phase = unit.trigger_event == "phase"
        is_draw_repl = (
            unit.origin == "replacement" and getattr(unit.node, "event", None) == "Draw"
        )
        for c in unit.effect_concepts("draw"):
            bulk = amount_factor(c.node, "count") >= 2 or amount_is_scaling(
                c.node, "count"
            )
            if not (
                is_phase or is_draw_repl or (bulk and unit.trigger_event != "enters")
            ):
                continue
            scope = _draw_engine_scope(unit, c)
            if scope not in seen:
                seen.add(scope)
                out.append(
                    Signal("card_draw_engine", scope, "", c.raw, tree.name, "high")
                )
    return out


def _group_hug_draw(tree: ConceptTree) -> list[Signal]:
    """group_hug_draw — a draw GIVEN to everyone (CR 121.1): "each player
    draws a card" (Temple Bell — the ``player_scope: All`` wrapper on the
    ability that owns the Draw; an explicit each-player recipient). A
    controller-only draw (Divination) never fires. Scope "each".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS or (
                effect_owner_player_scope(unit.node, c.node) == "All"
            ):
                return [Signal("group_hug_draw", "each", "", c.raw, tree.name, "high")]
    return []


def _target_player_draws(tree: ConceptTree) -> list[Signal]:
    """target_player_draws — a DIRECTED / forced draw (CR 121.1): "target
    player draws a card" (Bloodgift Demon — the typed ``Player`` recipient).
    With the typed recipient present the live path's self-loot phantom
    exclusion is unnecessary in v0.9.0 (Careful Study's draw carries
    ``Controller``); the negative fixture pins it regardless. A REPLACEMENT
    unit's rewritten draw ("if a player would draw …, that player … instead"
    — Chains of Mephistopheles' draw-tax) is a rules rewrite, not a forced
    gift — replacement units are skipped (mirrors the live non-directed
    exclusion). The ``ScopedPlayer`` each-player draw ("at the beginning of
    each player's draw step, that player may draw" — Academy Loremaster) is
    a GROUP draw distributed by an each-player trigger, not a directed gift
    — batch-9 adjudicated OUT (group-draw territory; the live routing of it
    here is the documented divergence), enforced by ``ScopedPlayer``'s
    absence from :data:`_TARGETED_DRAW_TAGS`. Scope "any".
    """
    for unit in tree.units:
        if unit.origin == "replacement":
            continue
        for c in unit.effect_concepts("draw"):
            rt = recipient_tag(c.node)
            if rt == "ScopedPlayer":
                continue  # each-player group draw — never a directed gift
            if rt in _TARGETED_DRAW_TAGS:
                return [
                    Signal("target_player_draws", "any", "", c.raw, tree.name, "high")
                ]
    return []


def _activated_draw(tree: ConceptTree) -> list[Signal]:
    """activated_draw — a tap-to-draw engine (CR 121.1 / 601.2b): an
    ``Activated`` unit with ``Tap`` among its cost leaves and a ``Draw``
    effect (Sensei's Divining Top's ``{T}: Draw``). A cycling activation
    (Archfiend of Ifnir — ``Composite[Mana, Discard]``, no Tap) and a
    tap-for-mana ability (no Draw) stay out. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "ability" or unit.kind != "Activated":
            continue
        if not unit.has_effect("draw"):
            continue
        if any(
            tag_of(leaf) == "Tap"
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
        ):
            return [Signal("activated_draw", "you", "", "", tree.name, "high")]
    return []


def _topdeck_selection(tree: ConceptTree) -> list[Signal]:
    """topdeck_selection — OWN-library top curation (CR 701.22 scry / 701.25
    surveil / 401.1). Four first-class hooks: ``Scry`` / ``Surveil`` (the
    player is always the implicit controller — zero opponent over-fire), a
    ``Dig`` whose ``player`` is Controller and whose destination is NOT the
    battlefield (Sensei's Divining Top — a dig-to-battlefield is the
    cheat/ramp put, fix b), and a ``RevealTop`` whose ``player`` is
    Controller. Gate #5: the library OWNER is the boundary — an opponent
    peek (Orcish Spy — ``player: Player``) never fires. The RevealTop arm
    additionally vetoes a SAME-unit ``SearchLibrary`` sibling: phase
    mislabels a tutor's found-card reveal ("searches their library …
    reveals it" — Auditore Ambush) as ``RevealTop(Controller)``
    (phase_parse_bug — a found-card reveal is not a top reveal, CR 701.23).
    Scope "you".
    """
    for unit in tree.units:
        has_search = any(tag_of(c.node) == "SearchLibrary" for c in unit.effects)
        for c in unit.effects:
            t = tag_of(c.node)
            if t in ("Scry", "Surveil"):
                return [
                    Signal("topdeck_selection", "you", "", c.raw, tree.name, "high")
                ]
            player = tag_of(getattr(c.node, "player", None))
            if (
                t == "Dig"
                and player == "Controller"
                and (getattr(c.node, "destination", None) != "Battlefield")
            ):
                return [
                    Signal("topdeck_selection", "you", "", c.raw, tree.name, "high")
                ]
            if t == "RevealTop" and player == "Controller" and not has_search:
                return [
                    Signal("topdeck_selection", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _topdeck_stack(tree: ConceptTree) -> list[Signal]:
    """topdeck_stack — stack the top of YOUR library (CR 401.4): a
    ``PutAtLibraryPosition`` whose ``position`` is ``Top`` (Brainstorm's
    hand-to-top; Sensei's Divining Top's SelfRef top) or the
    ``PutOnTopOrBottom`` choice form, over YOUR object (filter controller
    You / ``SelfRef``) — or over a ``TrackedSet`` fed by a SAME-unit
    Controller ``Dig`` (batch-9 adjudicated: Ancestral Knowledge's "look at
    the top ten … put the rest back on top" — the tracked set IS your dug
    top-of-library, granularity a). The owner gate keeps the bounce-to-top
    REMOVAL out (Griptide — controller None), mirroring the live
    controller=='you' gate; the position gate keeps the ``NthFromTop``
    precise-insertion removal (Chronostutter) and the ``Bottom`` cleanup
    (Aethermage's Touch) out. Scope "you".
    """
    for unit in tree.units:
        own_dig = any(
            tag_of(c.node) == "Dig"
            and tag_of(getattr(c.node, "player", None)) == "Controller"
            for c in unit.effects
        )
        for c in unit.effect_concepts("put_library_position"):
            if tag_of(c.node) == "PutAtLibraryPosition" and (
                tag_of(getattr(c.node, "position", None)) != "Top"
            ):
                continue
            tgt = getattr(c.node, "target", None)
            if (
                tag_of(tgt) == "SelfRef"
                or filter_controller(tgt) == "You"
                or (tag_of(tgt) == "TrackedSet" and own_dig)
            ):
                return [Signal("topdeck_stack", "you", "", c.raw, tree.name, "high")]
    return []


def _combat_buff_engine(tree: ConceptTree) -> list[Signal]:
    """combat_buff_engine — combat-keyed pump (CR 508 / 509.3a): a trigger in
    the combat frame (attacks / blocks / becomes-blocked / begin-combat) with
    a ``pump`` / ``place_counter`` effect in the SAME unit (granularity a) —
    Anafenza's attack counter, Accorder Paladin's Battle-cry ``PumpAll``
    (the keyword expansion the deleted regex missed — checklist #3: the
    keyword tags payoffs, so the structural read wins). The batch-9
    adjudicated fix also reads the fully-typed ``AddPower``/``AddToughness``
    mod sites a ``GenericEffect`` confers ("target artifact creature you
    control gets +2/+2 and gains indestructible" — Aethershield Artificer:
    the pump is a nested static modification, not a ``Pump`` effect; the
    overlay surfaces it as a static-role ``pump`` concept in the SAME unit).
    ``deals_damage`` is DELIBERATELY excluded so Renown / self_counter_grow
    shapes (Skirk Commando) never over-fire. Scope "you".
    """
    for unit in tree.units:
        ev = unit.trigger_event
        combat = ev in _COMBAT_BUFF_EVENTS or (
            ev == "phase" and getattr(unit.node, "phase", None) == "BeginCombat"
        )
        if not combat:
            continue
        if any(c.concept in ("pump", "place_counter") for c in unit.effects) or any(
            c.concept == "pump" for c in unit.statics
        ):
            return [Signal("combat_buff_engine", "you", "", "", tree.name, "high")]
    return []


def _land_sacrifice_matters(tree: ConceptTree) -> list[Signal]:
    """land_sacrifice_matters — the lands-to-graveyard PAYOFF (CR 701.21a /
    603.6c): a dies / leaves / sacrificed trigger whose watched OBJECT is a
    Land you control (The Gitrog Monster's ``ChangesZoneAll`` → Graveyard
    land watcher — the mass mode joins via the §0.2 derivation). Gate #6:
    subject controller you (an opponent-land watcher is not your payoff); a
    land-ETB watcher is the landfall lane. The you-sacrifice-a-land OUTLET
    (Gitrog's upkeep unit) is the already-ported ``land_sacrifice_makers`` —
    keys disjoint. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event not in _LAND_SAC_EVENTS:
            continue
        if "Land" not in trigger_subject(unit.node):
            continue
        if trigger_subject_scope(unit.node) != "you":
            continue
        return [Signal("land_sacrifice_matters", "you", "", "", tree.name, "high")]
    return []


def _exile_matters(tree: ConceptTree) -> list[Signal]:
    """exile_matters — exile-as-resource payoff (CR 406.1): a trigger
    watching cards LAND in exile (``ChangesZone`` destination Exile) whose
    watched object is NOT the card itself (Ketramose's "whenever one or more
    cards leave the battlefield and/or graveyards … [to] exile"). The
    ``SelfRef`` gate keeps the suspend/foretell/blink SELF-state watcher
    (God-Eternal Bontu's "when this is exiled" shuffle-in) out — the live
    #24b boundary (CR 702.62a analog); the ``AttachedTo`` gate keeps the
    enchanted-object recursion Aura (Kaya's Ghostform — insurance on ONE
    object, not exile-as-resource) out. A dig-and-cast engine with no
    exile-watcher trigger (Aetherworks Marvel) never fires. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if change_zone_dirs(unit.node)[1] != "Exile":
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) in ("SelfRef", "AttachedTo"):
            continue
        return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    return []


def _energy_matters(tree: ConceptTree) -> list[Signal]:
    """energy_matters — an energy SINK payoff (CR 107.14: "to pay {E}, a
    player removes one energy counter"): a ``PayEnergy`` cost leaf
    (Whirler Virtuoso's ``Pay {E}{E}{E}: token``; Aetherworks Marvel's
    ``Composite[Tap, PayEnergy 6]``) buying a NON-mana effect. The non-ramp
    gate mirrors the live pay-life painland exclusion: a fixing land whose
    only pay-energy effect is mana (Aether Hub) is the mana base +
    energy_makers, not a sink engine. The "whenever you get {E}" doubler
    trigger has NO mode in v0.9.0 — SUPPLEMENT-FIXABLE (the oracle carries
    "you get {E}"; a Stage-3 re-categorizer arm can stamp the marker). Scope
    "you".
    """
    for unit in tree.units:
        if not any(
            tag_of(leaf) == "PayEnergy"
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
        ):
            continue
        if any(c.concept != "ramp" for c in unit.effects):
            return [Signal("energy_matters", "you", "", "", tree.name, "high")]
    return []


def _counter_move(tree: ConceptTree) -> list[Signal]:
    """counter_move — a counter RELOCATION engine (CR 122.1): a
    ``MoveCounters`` effect (Nesting Grounds). The kind-gated
    ``counter_manipulation`` and the kind-agnostic ``any_counter_makers``
    co-fire where already ported (additive); this adds only the dedicated
    key. A ``PutCounter`` placer (Renata) never fires. Scope "you".
    """
    hits = tree.effect_concepts("move_counters")
    if hits:
        return [Signal("counter_move", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _explore_matters(tree: ConceptTree) -> list[Signal]:
    """explore_matters — the explore PAYOFF (CR 701.44): a first-class
    ``Explored`` trigger mode ("whenever a creature you control explores" —
    Wildgrowth Walker; the live path reaches this via a raw discriminator on
    an event='other' marker, so the mode read is a structural fidelity
    gain). An explore DOER (Merfolk Branchwalker — ``Explore`` effect →
    explore_makers) never co-fires. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "explored":
            return [Signal("explore_matters", "you", "", "", tree.name, "high")]
    return []


def _dice_matters(tree: ConceptTree) -> list[Signal]:
    """dice_matters — the roll PAYOFF (CR 706.1): a ``RolledDie`` /
    ``RolledDieOnce`` trigger mode ("whenever you roll one or more dice" —
    Brazen Dwarf). A roller DOER (Adorable Kitten — ``RollDie`` effect →
    dice_makers) never co-fires. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "rolled_die":
            return [Signal("dice_matters", "you", "", "", tree.name, "high")]
    return []


def _extra_upkeep_end(tree: ConceptTree) -> list[Signal]:
    """extra_upkeep / extra_end_step — extra non-combat phases (CR 500.8): an
    ``AdditionalPhase`` whose ``phase`` is Upkeep (Paradox Haze, Obeka) or
    End (Y'shtola Rhul). Paradox Haze's recipient is ``TriggeringPlayer``
    under an Enchant-Player trigger — the lane fires scope "you" regardless,
    mirroring the live scope (an extra upkeep you distribute is the
    build-around). A combat phase is the disjoint ``extra_combats`` lane.
    Tiny lanes are deliberate (niche ≠ skip).
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for c in tree.effect_concepts("extra_phase"):
        kind = additional_phase_kind(c.node)
        key = {"upkeep": "extra_upkeep", "end": "extra_end_step"}.get(kind)
        if key and key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", c.raw, tree.name, "high"))
    return out


def _facedown_matters(tree: ConceptTree) -> list[Signal]:
    """facedown_matters — the face-down PAYOFF (CR 708.1). Three typed hooks:
    a ``TurnFaceUp`` EFFECT (the turner references existing face-down
    permanents — Break Open), the ``TurnFaceUp`` TRIGGER mode ("when this
    is turned face up" morph payoffs — CR 708.3: the event arises only from
    a face-down permanent turning up), and the first-class ``ManifestDread``
    node (batch-9 adjudicated: Abhorrent Oculus — CR 701.55, manifest dread
    both MAKES the face-down 2/2 and selects for the face-down theme, so
    live fires maker + matters together; the tag read keeps the plain
    Manifest/Cloak DOERS, which share the ``facedown`` concept, out of the
    payoff arm). Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "turnfaceup":
            return [Signal("facedown_matters", "you", "", "", tree.name, "high")]
    hits = tree.effect_concepts("turn_face_up")
    if hits:
        return [Signal("facedown_matters", "you", "", hits[0].raw, tree.name, "high")]
    for c in tree.effect_concepts("facedown"):
        if tag_of(c.node) == "ManifestDread":
            return [Signal("facedown_matters", "you", "", c.raw, tree.name, "high")]
    return []


def _norm_kw(kw: str) -> str:
    """Normalize a phase keyword spelling for set membership (lower,
    spaceless, hyphenless — ``JumpStart`` → ``jumpstart``)."""
    return kw.lower().replace(" ", "").replace("-", "")


def _spell_keyword_grant(tree: ConceptTree) -> list[Signal]:
    """spell_keyword_grant (+ flash_grant / flash_makers) — grants a keyword
    to spells / castable cards (CR 702.8 flash, 702.34 flashback, 601.3e).
    Two typed arms:

    * a ``CastWithKeyword`` STATIC ("you may cast spells as though they had
      flash" — Leyline of Anticipation; "<class> spells you cast have
      <keyword>" — Chief Engineer), read via
      :func:`cast_with_keyword_name`;
    * an ``AddKeyword`` modification whose keyword is a SPELL-CAST keyword
      (:data:`_SPELL_GRANT_KEYWORDS` — Snapcaster Mage's targeted Flashback
      grant); the curated set is the spell-vs-battlefield discriminator (an
      evergreen grant is team_buff territory, checklist #3).

    Gate #2: beneficiary you — the affected filter must not name an
    opponent. A Flash grant additionally opens flash_grant + flash_makers
    (the live structural ``cast_with_keyword{flash}`` pair); a PRINTED
    keyword bearer (Faithless Looting's own Flashback) carries no grant node
    and never fires. A conditional printed SELF-flash ("~ has flash as long
    as you control a Merfolk" — Crashing Tide) parses as ``AddKeyword`` with
    ``affected=SelfRef``: the card grants only ITSELF castability (CR
    702.8a), not your spells — the SelfRef veto keeps all three keys out.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    def grant(kw: str, affected: object, raw: str) -> None:
        if tag_of(affected) == "SelfRef":
            return  # a self-grant is castability of this card, not an engine
        if filter_controller(affected) == "Opponent":
            return  # a grant to the opponent's spells is not your engine
        fire("spell_keyword_grant", raw)
        if _norm_kw(kw) == "flash":
            fire("flash_grant", raw)
            fire("flash_makers", raw)

    for unit in tree.units:
        if unit.origin == "static":
            kw = cast_with_keyword_name(unit.node)
            if kw is not None:
                grant(kw, getattr(unit.node, "affected", None), "")
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = mod_keyword_name(mod)
            if kw is None or _norm_kw(kw) not in _SPELL_GRANT_KEYWORDS:
                continue
            grant(kw, getattr(sdef, "affected", None), _site_raw(sdef))
    return out


def _hand_disruption(tree: ConceptTree) -> list[Signal]:
    """hand_disruption — opponent hand reveal/peek (CR 402.3: "a player
    can't look at the cards in another player's hand"). Two typed arms:

    * a ``RevealHand`` EFFECT whose recipient EXPLICITLY names another
      player (Duress — ``Typed controller=Opponent``; Addle — a targeted
      ``Player``; checklist #5). A self-reveal (Goblin Secret Agent —
      ``Controller``) never fires; nor does a bare ``Any`` target — phase
      uses ``Any`` for the revealed CARDS of a "reveal … cards from your
      hand" SELF-reveal (Manabond, Cursed Scroll, Brine Seer), so ``Any``
      carries no player evidence — never guess;
    * the ``RevealHand`` STATIC mode ("your opponents play with their hands
      revealed" — Telepathy; the symmetric Zur's Weirding reaches their
      hands too), via :func:`static_reveal_who`.

    Scope "opponents" (the live lane's).
    """
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) != "RevealHand":
                continue
            if _reveal_names_other_player(c.node):
                return [
                    Signal("hand_disruption", "opponents", "", c.raw, tree.name, "high")
                ]
        if unit.origin == "static" and static_reveal_who(unit.node) in _REVEAL_WHO_OPP:
            return [Signal("hand_disruption", "opponents", "", "", tree.name, "high")]
    return []


# RevealHand recipient tags that EXPLICITLY name another player (CR 402.3).
# ``Any`` is deliberately absent — phase's self-reveal ("reveal any number of
# cards from your hand") carries a bare ``Any`` CARDS target, not a player.
_REVEAL_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "Player",
        "ParentTarget",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ParentTargetController",
        "Each",
        "AllPlayers",
        "EachPlayer",
    }
)


def _reveal_names_other_player(node: TypedMirrorNode) -> bool:
    """Whether a ``RevealHand`` effect's recipient names ANOTHER player —
    an explicit player tag or an opponent-controlled ``Typed`` filter."""
    t = recipient_tag(node)
    if t in _REVEAL_PLAYER_TAGS:
        return True
    return t == "Typed" and filter_controller(effect_filter(node)) == "Opponent"


# ── Batch 10 lanes (ADR-0035 Stage 2) ────────────────────────────────────────

# Evasion subset for the generic-team grant (live ``_EVASION_GRANT_KW``).
_TEAM_EVASION_KW: frozenset[str] = frozenset(
    {"flying", "intimidate", "shadow", "horsemanship", "fear", "menace", "skulk"}
)
# Protective keywords (live ``_PROTECTION_GRANT_KW`` — CR 702.11 hexproof /
# 702.12 indestructible / 702.16 protection / 702.18 shroud / 702.21 ward).
_PROTECTIVE_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "shroud", "indestructible", "ward", "protection"}
)
# Evergreen allowlist for the Aura/Equipment-subgroup grant (live
# ``_AURA_EQUIP_GRANT_KW`` — excludes equip{0}/crew cost grants).
_AURA_EQUIP_KW: frozenset[str] = frozenset(
    {
        "exalted",
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "vigilance",
        "haste",
        "firststrike",
        "doublestrike",
        "hexproof",
        "ward",
        "menace",
        "reach",
        "indestructible",
    }
)
# Suit-up predicates: the grant lands on the creature the Aura/Equipment is
# attached to (live ``_is_aura_equip_protection_subject`` — CR 303 / 301).
_SUIT_UP_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})
# ``DoublePT`` modes that double POWER (CR 613.4c; a toughness-only doubler is
# not the beater build-around).
_POWER_DOUBLE_MODES: frozenset[str] = frozenset({"Power", "PowerAndToughness"})
# Direct-player recipient tags for the damage_equal_power read (CR 120.3).
# ``Any`` is "any target" (a player is reachable); ``ParentTarget``/``Target``
# are DELIBERATELY absent — they re-reference an earlier (creature) target.
_DEP_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "Any",
        "Player",
        "TriggeringPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "Each",
        "AllPlayers",
        "EachPlayer",
    }
)
# Mass land/artifact animator core types the base-P/T-set lane carves out
# (Living Plane / March of the Machines — those are land_creatures_matter /
# animate_artifact themes, live ``_signals_ir`` base_pt_set history).
_BASE_PT_ANIMATE_CORES: frozenset[str] = frozenset({"Land", "Artifact"})


def _etb_trigger_lanes(tree: ConceptTree) -> list[Signal]:
    """creature_etb + permanent_etb — the ETB-payoff pair (CR 603.6a: "Whenever
    a [type] enters, …"). One shared trigger walk:

    * ``creature_etb`` — an ``enters`` trigger whose watched-object filter has
      the Creature core type (Soul Warden). Scope from the filter's controller
      (checklist #5 — the trigger's OWN ``valid_card`` node): null/You → "you",
      Opponent → "opponents" (the punisher row). A SelfRef watcher (Elvish
      Visionary's enters-draw) is ETB *value on itself*, not a payoff ENGINE —
      never fires. **Arm 2** (the known-lossy-case improvement over live, which
      NEUTRALIZED its structural arm and rides a byte mirror): a
      ``DoubleTriggers`` static whose cause is an ``EntersBattlefield`` whose
      core types include Creature — or are EMPTY, the any-permanent form that
      subsumes creatures (Panharmonicon / Yarok / Elesh Norn, per
      Panharmonicon's 2021-03-19 ruling). **Arm 3** (b10 follow-up b): the
      "if a creature entered the battlefield under your control this turn"
      CONDITION family carries a typed ``EnteredThisTurn`` qty whose filter
      names the population (Bellowing Elk — Creature core, controller You;
      the batch-10 "no phase condition node" comment was STALE for this
      slice). The Celebration nonland-permanent forms (Ash, Party Crasher)
      and the filterless self-check (Cactuar) fail the Creature/You gates
      (measured live parity); Ephara HERSELF still parses condition-less —
      that residue stays SUPPLEMENT, logged.
    * ``permanent_etb`` — the GENERIC permanent-ETB engine: a Permanent-cored
      watcher with controller You (Amareth; checklist #6 — an opp-scoped
      permanent-ETB punisher is excluded, mirroring live).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str) -> None:
        if key + scope not in seen:
            seen.add(key + scope)
            out.append(Signal(key, scope, "", "", tree.name, "high"))

    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event == "enters":
            vc = getattr(unit.node, "valid_card", None)
            cores = filter_core_types(vc)
            if "Creature" in cores:
                ctrl = filter_controller(vc)
                fire("creature_etb", "opponents" if ctrl == "Opponent" else "you")
            elif "Permanent" in cores and filter_controller(vc) == "You":
                fire("permanent_etb", "you")
        if unit.origin == "static":
            dt_cores = double_triggers_cause_core_types(unit.node)
            if dt_cores is not None and (not dt_cores or "Creature" in dt_cores):
                fire("creature_etb", "you")
        for filt in entered_this_turn_filters(unit.node):
            if "Creature" in filter_core_types(filt) and (
                filter_controller(filt) == "You"
            ):
                fire("creature_etb", "you")
    return out


def _ltb_matters(tree: ConceptTree) -> list[Signal]:
    """ltb_matters — the leaves-the-battlefield payoff (CR 603.6c). Two typed
    arms: the bare ``LeavesBattlefield`` mode (Luminous Phantom) and a
    ``ChangesZone`` FROM the battlefield to a non-graveyard zone. Gates: a
    SelfRef watcher (Thalakos Seer's own leave — the live self/other split)
    never fires, and neither does an ``AttachedTo`` watcher (Curator's Ward /
    Traveling Plague — insurance on the ONE enchanted object, the same
    boundary the exile_matters lane draws); a graveyard-ARRIVAL "from
    anywhere" watcher (Compost — dest Graveyard, no battlefield origin) is
    graveyard territory, and CR 603.6c explicitly de-classifies it as an LTB
    ability. Third arm (b10 follow-up a — the batch-10 "no phase node"
    comment was STALE): the "a permanent left the battlefield under your
    control this turn" CONDITION family carries a typed
    ``ZoneChangeCountThisTurn {from: Battlefield}`` qty (the Revolt shape —
    Airdrop Aeronauts / Aid from the Cowl; 33 corpus with controller You).
    Zone-precise: Morbid's ``to: Graveyard`` variant (Tragic Slip — a death
    check) and the bounce-precise ``to: Hand`` (Barrin, Tolarian Archmage)
    carry a ``to`` and never fire; the controller-less symmetric forms
    (Alpharael, Stonechosen) fail the You gate (measured live parity). Scope
    from the watched object's controller (trigger arms) / "you" (condition
    arm, matching live).
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) in ("SelfRef", "AttachedTo"):
            continue
        origin, dest = change_zone_dirs(unit.node)
        is_ltb = unit.trigger_event == "leaves" or (
            origin == "Battlefield" and dest not in ("Graveyard", "Battlefield")
        )
        if is_ltb:
            scope = trigger_subject_scope(unit.node)
            return [Signal("ltb_matters", scope, "", "", tree.name, "high")]
    for unit in tree.units:
        for frm, to, filt in zone_change_count_reads(unit.node):
            if frm == "Battlefield" and to is None and filter_controller(filt) == "You":
                return [Signal("ltb_matters", "you", "", "", tree.name, "high")]
    return []


def _creature_cast_trigger(tree: ConceptTree) -> list[Signal]:
    """creature_cast_trigger — the creature-spell cast payoff (CR 701.5a /
    603.2): a ``SpellCast`` trigger whose watched-spell filter carries the
    Creature core type (Beast Whisperer). An instant/sorcery watcher (Talrand
    → spellcast_matters) and a NONcreature watcher (Kambal — the ``{Non:
    Creature}`` entry is dropped by the negation-aware type read) never fire.
    Scope "any" (the live hard-emit).
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event == "cast_spell":
            vc = getattr(unit.node, "valid_card", None)
            if "Creature" in filter_core_types(vc):
                return [
                    Signal("creature_cast_trigger", "any", "", "", tree.name, "high")
                ]
    return []


def _opponent_cast_matters(tree: ConceptTree) -> list[Signal]:
    """opponent_cast_matters — the opponent-cast punisher (CR 102.2/102.3 +
    603.2): a ``SpellCast`` trigger whose cast-PLAYER recipient node names an
    opponent (Kambal — ``valid_target {Typed, controller: Opponent}``;
    checklist #5, the recipient node, never a summary scope). The SYMMETRIC "a
    player casts" punisher (Eidolon of the Great Revel — no recipient node) is
    CORRECTLY excluded: "a player" includes you (CR 102.1). A self-cast
    watcher (Beast Whisperer — ``Controller``) never fires. The batched
    ``SpellCastOrCopy`` mode ("whenever [a player] casts or copies …", 33
    corpus — b10 follow-up e) joins the same read: its opponent-scoped
    ``valid_target`` fires, its Controller-scoped form (Archmage Emeritus)
    stays out on the same gate. Scope "opponents".
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event not in (
            "cast_spell",
            "spellcastorcopy",
        ):
            continue
        vt = getattr(unit.node, "valid_target", None)
        opp = tag_of(vt) in ("Opponent", "Opponents", "EachOpponent") or (
            tag_of(vt) == "Typed" and filter_controller(vt) == "Opponent"
        )
        if opp:
            return [
                Signal("opponent_cast_matters", "opponents", "", "", tree.name, "high")
            ]
    return []


def _combat_damage_lanes(tree: ConceptTree) -> list[Signal]:
    """combat_damage_matters + damage_to_opp_matters — the damage-connect
    payoffs, split by the trigger's typed ``damage_kind`` (checklist #5 — the
    recipient node decides reach, the kind decides the lane):

    * ``combat_damage_matters`` — ``DamageDone`` with ``CombatOnly`` kind
      reaching a player/planeswalker (Coastal Piracy; CR 510.1b). A creature
      recipient (Serpentine Basilisk) is the to-creature lane, not this one.
    * ``damage_to_opp_matters`` — the ANY-damage connect ("deals damage to an
      opponent" — Hypnotic Specter; CR 120.3), same player-reach read.

    Both hard-scope "opponents" (live). Co-fires with the ported
    ``combat_damage_to_opp`` where live does — distinct keys, the diff slices
    per key.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "deals_damage":
            continue
        vt = getattr(unit.node, "valid_target", None)
        if vt is None or not damage_recipient_is_player(vt):
            continue
        if filter_subtypes(vt):
            continue  # a SUBTYPE-carrying recipient is an object ("deals
            # damage to a Dinosaur" — Dinosaur Hunter), never a player
        kind = trigger_damage_kind(unit.node)
        key = (
            "combat_damage_matters" if kind == "CombatOnly" else "damage_to_opp_matters"
        )
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "opponents", "", "", tree.name, "high"))
    return out


def _second_spell_matters(tree: ConceptTree) -> list[Signal]:
    """second_spell_matters — the spell-velocity payoff (CR 603.2), the
    reclassified-UP probe win: the "second spell each turn" qualifier the OLD
    projection dropped (forcing live onto a byte mirror) is a first-class
    ``constraint {NthSpellThisTurn, n}`` on the SpellCast trigger in v0.9.0
    (Cori-Steel Cutter, n=2). Two typed arms: the trigger constraint with
    n ≥ 2, and the CONDITION form ``YouCastSpellCountAtLeast count ≥ 2``
    ("Activate only if you've cast two or more spells this turn" — Xerex
    Strobe-Knight). A bare SpellCast trigger (Talrand) and the n=1
    first-spell form (Alela, Cunning Conqueror) never fire. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if (
            trigger_constraint_tag(unit.node) == "NthSpellThisTurn"
            and (trigger_constraint_n(unit.node) or 0) >= 2
        ):
            return [Signal("second_spell_matters", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if spell_count_at_least(unit.node) >= 2:
            return [Signal("second_spell_matters", "you", "", "", tree.name, "high")]
    return []


def _xspell_matters(tree: ConceptTree) -> list[Signal]:
    """xspell_matters — the {X}-spell payoff/enabler pair (CR 107.3 + 601.2b;
    checklist #4 — this IS the payoff lane, membership stays live): a
    ``SpellCast`` trigger whose watched-spell filter carries the
    ``HasXInManaCost`` predicate (Zaxara — the same predicate live reads), or
    a ``Mana`` effect restricted ``XCostOnly`` (Rosheen Meanderer's "Spend
    this mana only on costs that contain {X}"). A spell that merely HAS {X}
    in its own cost (Hydroid Krasis — a SelfRef cast watcher, no predicate)
    never fires. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event == "cast_spell":
            vc = getattr(unit.node, "valid_card", None)
            if "HasXInManaCost" in filter_predicates(vc):
                return [Signal("xspell_matters", "you", "", "", tree.name, "high")]
        for c in unit.effect_concepts("ramp"):
            if "XCostOnly" in mana_restrictions(c.node):
                return [Signal("xspell_matters", "you", "", c.raw, tree.name, "high")]
    return []


def _counter_control(tree: ConceptTree) -> list[Signal]:
    """counter_control — the stack counterspell (CR 701.6a): a ``Counter`` /
    ``CounterAll`` effect (Counterspell — ``target {StackSpell}``).
    Structurally DISJOINT from the other meaning of "counter"
    (``PutCounter``/``RemoveCounter`` — distinct tags) and from the "can't be
    countered" permission STATICS (Vexing Shusher — a ``CantBeCountered``
    mode, no Counter effect). Scope "you" (live).
    """
    hits = tree.effect_concepts("counter_spell")
    if hits:
        return [Signal("counter_control", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _bounce_tempo(tree: ConceptTree) -> list[Signal]:
    """bounce_tempo — battlefield→hand bounce as tempo (CR 402.1: Boomerang,
    Unsummon). Two live gates (checklist #2 — the bounced subject's controller
    is the direction): a graveyard-zone subject (``InZone: Graveyard`` — a
    GY→hand recall, the creature_recursion arm) and a your-own-permanent
    subject (Aviary Mechanic — self-bounce value, controller You) never fire.
    Phase ALSO emits a ZONE-LESS ``Bounce`` for graveyard-to-hand returns
    ([P21] — the InZone marker is dropped), so the [P8]-precedent node-local
    description screen restores the recursion/tempo boundary (CR 402.1 vs
    404.1), scoped two ways against the multi-sentence description blob:
    a SelfRef subject with a "from ... graveyard" description is a
    self-return (Abzan Devotee) — WITHOUT it, battlefield self-bounce
    (Blinking Spirit) keeps firing, matching live; a targeted bounce with
    that description is vetoed only when it is the unit's ONLY bounce
    (Aphetto Dredging, Greasefang's reanimate-loop return) — a unit that
    also carries a genuine tempo bounce (Aether Helix's two-sentence pair)
    still fires, matching live. A mass bounce co-fires with the ported
    ``mass_bounce`` (live keeps both). Scope "you".
    """

    def _gy(text: str) -> bool:
        return any(
            phrase in text
            for phrase in (
                "from your graveyard",
                "from a graveyard",
                "from their graveyard",
                "from graveyards",
                "from target player's graveyard",
            )
        )

    card_desc = " ".join(
        (getattr(u.node, "description", None) or "") for u in tree.units
    ).lower()
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        # a nested delayed-trigger unit carries no description of its own —
        # the oracle text stayed on the parent, so fall back to the card's.
        gy_return = _gy(desc) if desc else _gy(card_desc)
        bounces = [
            c
            for c in unit.iter_concepts()
            if c.role == "effect" and c.concept == "bounce"
        ]
        for c in bounces:
            sub = effect_filter(c.node)
            if tag_of(sub) == "SelfRef":
                if gy_return:
                    continue  # self GY-return — recursion, not tempo
            elif gy_return and len(bounces) == 1 and desc:
                continue  # the unit IS the graveyard recall
            if "Graveyard" in filter_inzone_zones(sub):
                continue
            if filter_controller(sub) == "You":
                continue
            return [Signal("bounce_tempo", "you", "", c.raw, tree.name, "high")]
    return []


def _power_double(tree: ConceptTree) -> list[Signal]:
    """power_double — the P/T-doubling payoff (CR 613.4c + Unleash Fury's
    ruling): a ``DoublePT`` / ``DoublePTAll`` effect whose ``mode`` doubles
    POWER (``Power`` / ``PowerAndToughness``). The typed tag is the fix for
    the Scryfall ``Double`` keyword's over-fire onto damage/token/counter
    doublers (checklist #3 — distinct tags, split lanes); a flat pump (Giant
    Growth — a ``Pump`` node) and a toughness-only doubler never fire. Scope
    "you".
    """
    for c in tree.effect_concepts("double_pt"):
        if getattr(c.node, "mode", None) in _POWER_DOUBLE_MODES:
            return [Signal("power_double", "you", "", c.raw, tree.name, "high")]
    return []


def _keyword_grant_lanes(tree: ConceptTree) -> list[Signal]:
    """The AddKeyword mod-site cluster (CR 613.1f layer 6) — one shared walk,
    per-ability aggregation (granularity b), direction gates per checklist #6
    (the AFFECTED filter's controller, read off the mod-site's own node):

    * ``keyword_grant_target`` — the single-target grant: an ``AddKeyword``
      whose affected is ``ParentTarget`` under a ``GenericEffect`` whose
      resolved target carries the Creature CORE type — live's two v14
      markers mirrored exactly: the DEEP local-target leaf on ANY unit
      (trigger / modal / Saga / quoted — Aethershield Artificer) via
      :func:`iter_deep_target_grants`, plus the flat threaded walk on
      abilities for the "It gains X" idiom via
      :func:`iter_single_target_grants` (Snakeskin Veil, Jump). A PERMANENT
      target (Aegis Angel) and a subtype-only target (a tribal grant) stay
      out on the creature-core gate, exactly as live. Scope "you".
    * ``protection_grant`` — a PROTECTIVE keyword (hexproof / shroud /
      indestructible / ward / protection, incl. the parameterized
      ``{Protection: …}`` variant whose KEY is the name — Gods Willing) to a
      single target (same v14 shape), your generic creature team, your
      permanents, or the suit-up equipped/enchanted recipient
      (CR 702.11/12/16/18/21).
    * ``all_creatures_kw_grant`` — the SYMMETRIC "all creatures [have/gain]
      X" (Concordant Crossroads; the one-shot Dirge of Dread): generic
      Creature filter, controller NULL / TargetPlayer (never You/Opponent),
      no subtypes/predicates. ANY granted keyword fires (the live arm is
      keyword-ungated). Scope "any" (it buffs opponents too, checklist #5).
    * ``team_evasion_grant`` — the evasion subset on your generic creature
      team (Levitation). Co-fires with the ported ``team_buff`` (a documented
      subset). A subtype/chosen-type-scoped grant (Cover of Darkness) fails
      the generic-team gate — the live mirror tail, SUPPLEMENT, logged.
    * ``aura_equip_kw_grant`` — an evergreen keyword to YOUR Aura/Equipment
      subgroup (Rashel, Fist of Torm). A name-scoped controller-null cycle
      (Shield of Kaldra) and the equipped-CREATURE recipient (Cori-Steel
      Cutter's haste — no Aura/Equipment subtype on the affected filter)
      never fire.

    A SelfRef affected (a card granting ITSELF a keyword) is vetoed
    throughout (the batch-9 self-grant lesson).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        grants = list(iter_deep_target_grants(unit.node))
        if unit.origin == "ability":
            grants.extend(iter_single_target_grants(unit.node))
        for resolved, mod in grants:
            if "Creature" not in filter_core_types(resolved):
                continue  # the live creature-core gate (no tribal/permanent)
            fire("keyword_grant_target", "you", "")
            if _norm_kw(mod_keyword_name(mod) or "") in _PROTECTIVE_GRANT_KW:
                fire("protection_grant", "you", "")
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = _norm_kw(mod_keyword_name(mod) or "")
            affected = getattr(sdef, "affected", None)
            atag = tag_of(affected)
            if atag in ("SelfRef", "ParentTarget"):
                continue  # self-grant / the single-target arm above
            raw = _site_raw(sdef)
            cores = set(filter_core_types(affected))
            ctrl = filter_controller(affected)
            subs = {s.lower() for s in filter_subtypes(affected)}
            preds = filter_predicates(affected)
            generic = not subs and not preds
            team = "Creature" in cores and ctrl == "You" and generic
            if team and kw in _TEAM_EVASION_KW:
                fire("team_evasion_grant", "you", raw)
            if "Creature" in cores and ctrl not in ("You", "Opponent") and generic:
                fire("all_creatures_kw_grant", "any", raw)
            if ctrl == "You" and subs & {"aura", "equipment"} and kw in _AURA_EQUIP_KW:
                fire("aura_equip_kw_grant", "you", raw)
            your_perms = "Permanent" in cores and ctrl == "You" and generic
            suit_up = set(preds) & _SUIT_UP_PREDS and cores & {"Creature", "Permanent"}
            if kw in _PROTECTIVE_GRANT_KW and (team or your_perms or suit_up):
                fire("protection_grant", "you", raw)
    return out


def _base_pt_set(tree: ConceptTree) -> list[Signal]:
    """base_pt_set — the fixed base-P/T-SET toolbox (CR 613.4b; 613.4d for the
    switch form): a mod site carrying BOTH ``SetPower`` and ``SetToughness``
    (Polymorphist's Jest — the "becomes a 1/1" neutralize), or a ``SwitchPT``
    effect (Merfolk Thaumaturgist). Per-site subject RESOLUTION (granularity
    b): a nested site whose affected is ``ParentTarget`` resolves through the
    owning ``GenericEffect``'s target — THE over-fire gates ride the resolved
    filter: a Land/Artifact-cored subject is a MASS/TARGET ANIMATOR (Living
    Plane, Animate Land — the land_creatures_matter / animate_artifact
    themes), and a SelfRef / subject-less site is a SELF-transform ("~
    becomes a 3/3 Angel" — Angel's Tomb, man-lands; the batch-9 SelfRef
    lesson), both carved out. The SwitchPT arm applies the same SelfRef veto
    (Aquamoeba's self-switch is a P/T trick, not the toolbox). Additive
    pumps (Giant Growth — layer 7c) are distinct tags. The dynamic
    set-equal-to form is :func:`_variable_pt`. Scope "any" (live).
    """

    def mod_tags(st: object) -> set[str]:
        stm = getattr(st, "modifications", None)
        if not isinstance(stm, list):
            return set()
        return {tag_of(m) or "" for m in stm}

    sites: list[tuple[object, set[str]]] = []
    for unit in tree.units:
        if unit.origin == "static":
            # raw modification tags (not the set_pt concept slice) so the
            # dynamic pair on a top-level static (Aettir and Priwen)
            # surfaces alongside SetPower/SetToughness.
            sites.append((getattr(unit.node, "affected", None), mod_tags(unit.node)))
        # Filter-affected nested statics (Polymorphist's Jest — the affected
        # IS the population) read directly; ParentTarget-affected ones
        # resolve through the THREADED target walk (Ovinize's local target,
        # Cyclone Sire's sibling land target).
        for c in unit.effects:
            if tag_of(c.node) != "GenericEffect":
                continue
            nested = getattr(c.node, "static_abilities", None)
            for st in nested if isinstance(nested, list) else []:
                affected = getattr(st, "affected", None)
                if tag_of(affected) != "ParentTarget":
                    sites.append((affected, mod_tags(st)))
        for resolved, st in iter_threaded_target_statics(unit.node):
            sites.append((resolved, mod_tags(st)))
    for resolved, mods in sites:
        # Fixed pair (Polymorphist's Jest) OR the DYNAMIC base-P/T-set pair
        # (b10 follow-up f): ``SetPowerDynamic`` + ``SetToughnessDynamic``
        # ("base power and toughness X/X" — Biomass Mutation; "…each equal
        # to your life total" — Aettir and Priwen). Distinct from the
        # ``SetDynamicPower`` CDA tags (:func:`_variable_pt` — Tarmogoyf).
        if not (
            {"SetPower", "SetToughness"} <= mods
            or {"SetPowerDynamic", "SetToughnessDynamic"} <= mods
        ):
            continue
        if tag_of(resolved) not in ("Typed", "Or", "And"):
            continue  # SelfRef self-transform, or an unresolvable ParentTarget
            # ("It becomes a 0/0 Elemental" over a SIBLING land target —
            # Cyclone Sire): no positive subject evidence, never fire
        if set(filter_core_types(resolved)) & _BASE_PT_ANIMATE_CORES:
            continue  # the land/artifact animator carve-out
        if {s.lower() for s in filter_subtypes(resolved)} & _LAND_SUBTYPES:
            continue  # a land-SUBTYPE subject ("enchanted Mountain becomes
            # a 7/7" — Awaken the Ancient) is the same animator family
        return [Signal("base_pt_set", "any", "", "", tree.name, "high")]
    for c in tree.effect_concepts("switch_pt"):
        tgt = getattr(c.node, "target", None)
        if tgt is None or tag_of(tgt) == "SelfRef":
            continue  # self-switch — a P/T trick on itself
        return [Signal("base_pt_set", "any", "", c.raw, tree.name, "high")]
    return []


def _variable_pt(tree: ConceptTree) -> list[Signal]:
    """variable_pt — the */* characteristic-defining P/T (CR 604.3 + 613.4a
    layer 7a): a static def with ``characteristic_defining == true`` carrying
    a ``SetDynamicPower`` / ``SetDynamicToughness`` modification (Tarmogoyf —
    value = a ``Ref``/``DistinctCardTypes`` count). A fixed-number set
    (Polymorphist's Jest — ``characteristic_defining`` false, plain
    ``SetPower``) is :func:`_base_pt_set`. The TOKEN-borne */* and triggered
    self-set tail phase can't structure — SUPPLEMENT, logged. Scope "any".
    """
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("SetDynamicPower", "SetDynamicToughness"):
                continue
            if getattr(sdef, "characteristic_defining", None) is True:
                raw = _site_raw(sdef)
                return [Signal("variable_pt", "any", "", raw, tree.name, "high")]
    return []


def _trigger_doubling(tree: ConceptTree) -> list[Signal]:
    """trigger_doubling — the trigger-doubling engine (grounded by
    Panharmonicon's 2021-03-19 ruling; ``rules-lookup --grep`` finds no
    dedicated CR term): a static whose mode variant is ``DoubleTriggers``
    (Panharmonicon, Yarok, Strionic-style ``Any`` causes). The REPLACEMENT
    doublers of tokens/counters (Doubling Season — ``quantity_modification``
    replacement nodes, NOT DoubleTriggers) are split lanes and never fire.
    The creature-ETB cause co-fires ``creature_etb`` via
    :func:`_etb_trigger_lanes` arm 2. Scope "you".
    """
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) == "DoubleTriggers":
                return [Signal("trigger_doubling", "you", "", "", tree.name, "high")]
    return []


def _forced_attack(tree: ConceptTree) -> list[Signal]:
    """forced_attack — the attack compulsion (CR 508.1d). Two typed arms
    mirroring the live ``force_attack`` category's two phase sources: a
    static def whose mode is ``MustAttack`` (Warmonger Hellkite's table-wide
    force; Juggernaut's SelfRef drawback stays IN to match live — the
    supplement recovers self/team statics), and the one-shot ``ForceAttack``
    EFFECT ("target creature … attacks … if able" — Alluring Siren). Goad is
    a distinct tag (Disrupt Decorum → ``goad_makers``, ported b4) and never
    fires. Scope "any" (live — a symmetric/table force, not a you-only
    payoff).
    """
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) == "MustAttack":
                return [Signal("forced_attack", "any", "", "", tree.name, "high")]
        for c in unit.effects:
            if tag_of(c.node) == "ForceAttack":
                return [Signal("forced_attack", "any", "", c.raw, tree.name, "high")]
    return []


def _damage_prevention(tree: ConceptTree) -> list[Signal]:
    """damage_prevention — the CR 615 prevention shield: a ``PreventDamage``
    effect (Fog — ``{amount: All, scope: CombatDamage}``; Story Circle's
    activated next-time shield). Second arm (b10 follow-up c, adjudicated):
    a ``DamageDone`` REPLACEMENT carrying ``shield_kind {Prevention}`` (the
    Palisade Giant family, 146 corpus) — prevention-shield MEMBERSHIP only;
    the redirect SEMANTICS deliberately stay uncaptured (``damage_redirect``
    is a settled KEPT — Pariah parses indistinguishably from a pure shield).
    Protection grants are a DIFFERENT node (Gods Willing →
    :func:`_keyword_grant_lanes`); the Aura/ward reminder-text tail rides
    the live byte mirror — SUPPLEMENT, logged. Scope "you" (live).
    """
    hits = tree.effect_concepts("prevent_damage")
    if hits:
        return [Signal("damage_prevention", "you", "", hits[0].raw, tree.name, "high")]
    for unit in tree.units:
        if (
            unit.origin == "replacement"
            and replacement_event_tag(unit.node) == "DamageDone"
            and replacement_shield_kind(unit.node) == "Prevention"
        ):
            raw = getattr(unit.node, "description", None) or ""
            # [P29]: an OFFENSIVE curse ("All damage that would be dealt to
            # enchanted creature is dealt to its controller instead" —
            # Treacherous Link) parses as a bare Prevention shield identical
            # to Pariah; the shielded SUBJECT in the node's own description
            # is the tell (adjudicated corpus scan: exactly two
            # redirect-to-controller shields; Mirror Strike shields YOU).
            if "dealt to enchanted creature is dealt to" in raw.lower():
                continue
            return [Signal("damage_prevention", "you", "", raw, tree.name, "high")]
    return []


def _damage_equal_power(tree: ConceptTree) -> list[Signal]:
    """damage_equal_power — the Fling shape (CR 120.3 recipient rules): a
    ``DealDamage`` whose amount is a ``Ref`` over a POWER qty
    (:func:`ref_qty_tag`) reaching a PLAYER recipient — the "any target"
    ``Any`` (Fling) or a DIRECT player node. A ``ParentTarget`` re-reference
    is NOT accepted: it names an earlier CREATURE target ("Tap target
    creature. ~ deals damage equal to its power to that creature" — Abyssal
    Hunter, the bite/creature_ping shape). A fixed amount (Prodigal
    Sorcerer) never fires. Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("deal_damage"):
            if tag_of(c.node) != "DealDamage":
                continue
            if ref_qty_tag(c.node, "amount") != "Power":
                continue
            tgt = getattr(c.node, "target", None)
            tt = tag_of(tgt)
            player = tt in _DEP_PLAYER_TAGS or (
                tt == "Typed" and "Player" in filter_core_types(tgt)
            )
            if player:
                return [
                    Signal("damage_equal_power", "you", "", c.raw, tree.name, "high")
                ]
    return []


# ── Batch 11 lanes (ADR-0035 Stage 2) ────────────────────────────────────────

# Replacement quantity-modification kinds that INCREASE the count (CR 614.1a).
# Live's counter_doubling category is event==addcounter + an increase mod — the
# measured live set fires BOTH counter_doubling and counter_replace_bonus on
# Times AND Plus (Hardened Scales carries counter_doubling live), so both arms
# read the same increase set; Minus (Vizier of Remedies) / Prevent never fire.
_INCREASE_QTY_MODS: frozenset[str] = frozenset({"Times", "Plus"})
# DamageDone replacement damage-modification kinds that AMPLIFY (CR 614.1a +
# 120.3): Double (Furnace of Rath), Triple (Fiery Emancipation), Plus (Torbran
# — live's damage_doubling category includes the +N amplifiers, measured).
# LifeFloor (Ali from Cairo) / Minus (Lashknife Barrier) are shields/reducers.
_DAMAGE_AMP_MODS: frozenset[str] = frozenset({"Double", "Triple", "Plus"})
# Trigger modes marking a tap/untap payoff (CR 701.26a): phase's ``Taps`` /
# ``TapsForMana`` (both "becomes tapped" family) + ``Untaps`` (Inspired).
_TAP_EVENTS: frozenset[str] = frozenset({"taps", "untaps", "tapsformana"})
# Self-return target tags for the self-blink return half (CR 611.2b): the
# delayed return names the exiled object as ParentTarget / TrackedSet
# (Aetherling) or SelfRef / TriggeringSource (granted-quote forms).
_SELF_BLINK_RETURN_TAGS: frozenset[str] = frozenset(
    {"ParentTarget", "TrackedSet", "SelfRef", "TriggeringSource"}
)


def _replacement_doubler_lanes(tree: ConceptTree) -> list[Signal]:
    """The CR 614.1a replacement-doubler cluster — one shared walk over the
    typed replacement units, split by ``event`` (granularity a):

    * ``token_doubling`` — a ``CreateToken`` replacement with an INCREASE
      ``quantity_modification`` (Doubling Season ``Times 2``, Parallel Lives;
      Primal Vigor's symmetric no-owner-scope form INCLUDED — the beneficiary
      includes you). Give-away gate (checklist #2): an Opponent-only
      ``token_owner_scope`` is excluded (zero corpus members; defensive).
      Co-fires ``token_copy_makers`` + ``tokens_matter`` (live's ADR-0027 C5
      read: a token doubler forks copies and is a go-wide payoff).
    * ``counter_doubling`` + ``counter_replace_bonus`` — an ``AddCounter``
      replacement with an INCREASE mod whose ``valid_card`` controller is
      You/null (checklist #6). Live subsumption reproduced: both keys co-fire
      on Times AND Plus (measured — Hardened Scales carries both). A
      ``Minus`` reducer (Vizier of Remedies) and the CreateToken event never
      fire. Case law: Vorel ruling "essentially double the counters".
    * ``counter_doubling`` arm b/c (the probe win — live's "phase mangles
      Vorel" byte-mirror complaint is STALE): the one-shot ``Double`` effect
      with ``target_kind {Counters}`` (Vorel, 12 corpus — LifeTotal/ManaPool/
      None target_kinds gated out) and the triggered ``MultiplyCounter``
      (Kalonian Hydra — live counter_doubling fires, measured).
    * ``damage_doubling`` — a ``DamageDone`` replacement carrying an AMPLIFY
      ``damage_modification`` (Double/Triple/Plus). Direction gate
      (checklist #2/#5, read off the replacement's OWN
      ``damage_target_filter``): a YOUR-side-only doubler (doubles damage TO
      you — a drawback) is vetoed; Gisela's opponent-side filter is the
      include case. Shield replacements with NO damage_modification
      (Palisade Giant) never fire. Co-fires ``direct_damage`` when the
      doubler reaches players (live ADR-0027 C7): a filterless doubler
      (Furnace of Rath) or a player-inclusive filter fires it; the
      creature-only ``"CreatureOnly"`` filter (Blind Fury) does not
      (measured live parity).

    All scope "you" (live).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for unit in tree.units:
        if unit.origin != "replacement":
            continue
        node = unit.node
        ev = replacement_event_tag(node)
        raw = getattr(node, "description", None) or ""
        if ev == "CreateToken":
            qm = replacement_qty_mod(node)
            if (
                qm is not None
                and qm[0] in _INCREASE_QTY_MODS
                and replacement_token_owner_scope(node) != "Opponent"
            ):
                fire("token_doubling", raw)
                fire("token_copy_makers", raw)
                fire("tokens_matter", raw)
        elif ev == "AddCounter":
            qm = replacement_qty_mod(node)
            vc = getattr(node, "valid_card", None)
            if (
                qm is not None
                and qm[0] in _INCREASE_QTY_MODS
                and filter_controller(vc) in (None, "You")
            ):
                fire("counter_doubling", raw)
                fire("counter_replace_bonus", raw)
        elif ev == "DamageDone":
            mod = replacement_damage_mod(node)
            if mod in _DAMAGE_AMP_MODS:
                tscope = damage_filter_scope(node, "damage_target_filter")
                if tscope != "you":  # the your-side-only drawback veto
                    fire("damage_doubling", raw)
                    if tscope in (None, "opponents", "each", "any"):
                        fire("direct_damage", raw)
    for c in tree.effect_concepts("double_quantity"):
        if double_target_kind(c.node) == "Counters":
            fire("counter_doubling", c.raw)
    for c in tree.effect_concepts("multiply_counter"):
        mult = getattr(c.node, "multiplier", None)
        if isinstance(mult, int) and mult >= 2:
            fire("counter_doubling", c.raw)
    return out


def _is_tribe_damage_source(vs: object) -> bool:
    """Whether a damage trigger's ``valid_source`` is a YOUR-controlled
    creature POPULATION (CR 510.1b): a Typed/Or filter with controller You
    and either the Creature core type (Coastal Piracy) or a vocab-validated
    creature subtype (Seshiro's Snakes; the AnyOf outlaw unions recurse). A
    ``SelfRef`` source (Hypnotic Specter — a single doer) is not a
    population."""
    if tag_of(vs) not in ("Typed", "Or", "And"):
        return False
    if filter_controller(vs) != "You":
        return False
    if "Creature" in filter_core_types(vs):
        return True
    return any(_resolve_subject(s, CREATURE_SUBTYPES) for s in filter_subtypes(vs))


def _damage_trigger_lanes(tree: ConceptTree) -> list[Signal]:
    """The damage-trigger cluster (CR 603.2 + 120.3 / 510.1b/c) — one shared
    trigger walk, direction read off each trigger's OWN ``valid_target`` /
    ``valid_source`` nodes (checklist #5):

    * ``damage_reflect`` — a ``DamageReceived`` trigger whose SAME unit deals
      damage back (Boros Reckoner; co-occurrence, granularity a). Phytohydra
      parses as a replacement with a PutCounter execute — out twice over.
      Case law: "Damage dealt by Boros Reckoner due to its first ability
      isn't combat damage."
    * ``damage_to_you_punish`` — ``DamageDone`` with ``valid_target
      {Controller}`` AND an Opponent-controlled ``valid_source`` (Michiko
      Konda — the exact probed shape; live's "no structural shape" comment
      was STALE). The ported ``damage_to_opp_matters`` direction (target
      Opponent/Player) and the You-controlled source never fire. Scope
      "opponents" (live's mirror scope).
    * ``combat_damage_to_creature`` — ``DamageDone`` + ``CombatOnly`` kind +
      a Creature-cored recipient (Serpentine Basilisk; CR 510.1c). A Player
      recipient (Seshiro) is the ported player-connect lanes. Scope "any".
    * ``tribe_damage_trigger`` — a player-reaching recipient AND a
      your-creature-population source (Seshiro / Coastal Piracy; both
      CombatOnly and Any damage kinds, live reads both; the batched
      ``DamageDoneOnceByController`` mode — Anowon — joins via the shared
      ``deals_damage`` event). Scope "you", bare key (live).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", "", tree.name, "high"))

    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if unit.trigger_event == "damage_received" and unit.has_effect("deal_damage"):
            fire("damage_reflect", "you")
        if unit.trigger_event != "deals_damage":
            continue
        node = unit.node
        vt = getattr(node, "valid_target", None)
        vs = getattr(node, "valid_source", None)
        if (
            tag_of(vt) == "Controller"
            and tag_of(vs) == "Typed"
            and filter_controller(vs) == "Opponent"
        ):
            fire("damage_to_you_punish", "opponents")
        if (
            trigger_damage_kind(node) == "CombatOnly"
            and tag_of(vt) == "Typed"
            and "Creature" in filter_core_types(vt)
            and "Player" not in filter_core_types(vt)
        ):
            fire("combat_damage_to_creature", "any")
        if (
            vt is not None
            and damage_recipient_is_player(vt)
            and _is_tribe_damage_source(vs)
        ):
            fire("tribe_damage_trigger", "you")
    return out


def _unit_is_repeatable(unit: AbilityUnit) -> bool:
    """The aoe_ping repeatable gate (mirrors live): an Activated ability whose
    cost leaves include Tap or Mana and do NOT include a Sacrifice
    (Pestilence's ``{B}``), or a trigger on a Phase (upkeep/end step) or
    SpellCast mode. A one-shot Spell (Pyroclasm), a sac-cost activation, and
    an ETB-trigger sweep (Chaos Maw — ChangesZone mode) all fail."""
    if unit.origin == "ability" and unit.kind == "Activated":
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(unit.node, "cost", None))}
        return bool(leaves & {"Tap", "Mana", "ManaDynamic"}) and (
            "Sacrifice" not in leaves
        )
    if unit.origin == "trigger":
        mode = getattr(unit.node, "mode", None)
        return mode in ("Phase", "SpellCast")
    return False


def _mass_damage_lanes(tree: ConceptTree) -> list[Signal]:
    """symmetric_damage_each + aoe_ping + creature_ping — the effect-side
    damage lanes, scope from each effect's OWN player_filter / target node
    (checklist #5):

    * ``symmetric_damage_each`` — a ``DamageAll`` / ``DamageEachPlayer``
      whose ``player_filter`` is ``All`` (Pestilence; Earthquake's X-form —
      the recall the deleted regex's literal ``\\d+`` missed). The one-sided
      ``Opponent`` filter (Witty Roastmaster — 259 corpus, THE over-fire
      mass) and a player-less creature sweep never fire. Scope "each"
      (CR 102.2/102.3 — the each-player/each-opponent split is the gate).
    * ``aoe_ping`` — a ``DamageAll`` with a Creature-cored target on a
      REPEATABLE unit (:func:`_unit_is_repeatable` mirrors live's gate).
      One-shot sweeps (Pyroclasm — Spell kind) are mass_removal country.
      Scope "you".
    * ``creature_ping`` — a ``DealDamage`` whose amount is a POWER-scaled
      ``Ref`` reaching a Creature-cored target (Ram Through; CR 120.3).
      Fixed amounts (Prodigal Sorcerer) and player recipients (Fling — the
      ported ``damage_equal_power``) never fire. Scope "you".
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        repeatable = _unit_is_repeatable(unit)
        for c in unit.effect_concepts("deal_damage"):
            t = tag_of(c.node)
            if t in ("DamageAll", "DamageEachPlayer") and (
                player_filter_tag(c.node) == "All"
            ):
                fire("symmetric_damage_each", "each", c.raw)
            if t == "DamageAll" and repeatable:
                tgt = getattr(c.node, "target", None)
                if "Creature" in filter_core_types(tgt):
                    fire("aoe_ping", "you", c.raw)
            if t == "DealDamage" and ref_qty_tag(c.node, "amount") == "Power":
                tgt = getattr(c.node, "target", None)
                if tag_of(tgt) in ("Typed", "Or", "And") and (
                    "Creature" in filter_core_types(tgt)
                ):
                    fire("creature_ping", "you", c.raw)
    return out


def _counter_place_trigger(tree: ConceptTree) -> list[Signal]:
    """counter_place_trigger — the counters-placed payoff (CR 122.1 + 603.2):
    a ``CounterAdded`` trigger whose typed ``counter_filter`` is NOT the lore
    kind. The typed Saga gate (CR 714.2b: a chapter IS a lore-CounterAdded
    trigger — 723 of 798 corpus) IMPROVES on live's type_line sniff; the
    card-subtype belt (``Saga`` in the card's own subtypes) rides over it.
    The opponent-side population punisher (Kros, Defense Contractor /
    Generous Patron — ``valid_card`` controller Opponent) is vetoed
    (checklist #6). Cards that PLACE counters via effect (Cathars' Crusade —
    a ChangesZone trigger + PutCounterAll, no CounterAdded mode) never fire.
    Scope "you" (live).
    """
    if "Saga" in tree.card_subtypes:
        return []
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "counter_added":
            continue
        ct, _threshold = trigger_counter_filter(unit.node)
        if ct == "lore":
            continue
        if filter_controller(getattr(unit.node, "valid_card", None)) == "Opponent":
            continue
        return [Signal("counter_place_trigger", "you", "", "", tree.name, "high")]
    return []


def _tribal_etb_multi(tree: ConceptTree) -> list[Signal]:
    """tribal_etb_multi — the tribal ETB-chain payoff (CR 603.6a): an
    ``enters`` trigger whose watched-object filter carries a vocab-validated
    CREATURE subtype, including Or-branch walks (Noxious Ghoul's
    ``Or[SelfRef, Typed[Zombie, Another]]``). The ``_subtypes`` vocab IS the
    precision gate: a generic Creature watcher (Soul Warden → the ported
    ``creature_etb``) and a non-creature-subtype watcher (an Aura/Equipment
    ETB) never fire. Scope "you" (live).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "enters":
            continue
        subs = filter_subtypes(getattr(unit.node, "valid_card", None))
        if any(_resolve_subject(s, CREATURE_SUBTYPES) for s in subs):
            return [Signal("tribal_etb_multi", "you", "", "", tree.name, "high")]
    return []


def _typed_enters_punish(tree: ConceptTree) -> list[Signal]:
    """typed_enters_punish — the "your things enter → burn the opponents"
    co-occurrence (CR 603.6a + 102.2/102.3, granularity a): an ``enters``
    trigger on a YOUR-controlled population whose SAME unit deals damage
    reaching opponents — the typed ``DamageEachPlayer {player_filter:
    Opponent}`` read (Witty Roastmaster — the shape live could only recover
    from raw "each opponent") or an opponent/each-scoped ``DealDamage``
    player recipient. Checklist #1/#5: the enterer's controller reads off
    the trigger's own ``valid_card``; the damage recipient off the effect's
    OWN player_filter/recipient node. The opponent-enterer punisher (Suture
    Priest's second trigger) and non-damage payoffs (Soul Warden) never
    fire. Scope "you" (live).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "enters":
            continue
        if filter_controller(getattr(unit.node, "valid_card", None)) != "You":
            continue
        for c in unit.effect_concepts("deal_damage"):
            if not effect_reaches_player(c.node):
                continue
            t = tag_of(c.node)
            if t in ("DamageEachPlayer", "DamageAll"):
                hit = player_filter_tag(c.node) in ("Opponent", "All")
            else:
                hit = explicit_recipient_scope(c.node) in ("opponents", "each")
            if hit:
                return [
                    Signal("typed_enters_punish", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _noncreature_cast_punish(tree: ConceptTree) -> list[Signal]:
    """noncreature_cast_punish — the noncreature-spell punisher (CR 603.2 +
    102.2 — deliberately scope "any": "a player" includes you): a
    ``SpellCast`` trigger whose watched-spell filter carries a
    ``{Non: Creature}`` entry (Ruric Thar — the entry IS the discriminator,
    read via the negation-aware :func:`filter_non_types`). A Creature-typed
    cast watcher (Beast Whisperer) and an instant/sorcery-only watcher
    (Talrand → the ported ``spellcast_matters``) never fire. Caster gate
    (checklist #5, corpus-measured: 126 prowess-family over-fires without
    it): a YOU-cast noncreature REWARD ("whenever you cast a noncreature
    spell, ~ gets +1/+0" — Burning Prophet, ``valid_target {Controller}``)
    is prowess, not a punisher — live fires only the symmetric
    (recipient-less "a player casts" — Ruric Thar) and opponent-scoped
    halves.
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "cast_spell":
            continue
        if trigger_caster_scope(unit.node) == "you":
            continue  # the prowess/you-cast reward family — not a punisher
        if "Creature" in filter_non_types(getattr(unit.node, "valid_card", None)):
            return [Signal("noncreature_cast_punish", "any", "", "", tree.name, "high")]
    return []


def _tap_lanes(tree: ConceptTree) -> list[Signal]:
    """tap_down + tapper_engine — the CR 701.26a tap-doer pair, one shared
    effect walk (a tap-as-COST emits no ``SetTapState`` effect — Prodigal
    Sorcerer — so pure-cost taps self-exclude, reproducing live's
    subject-is-not-None gate):

    * ``tap_down`` — (arm a) a ``SetTapState {state: Tap}`` whose target's
      controller is Opponent (Dungeon Geists; checklist #5 — the effect's
      own target node); (arm b) a ``Detain`` effect (Azorius Arrester —
      CR 701.35, all opponent-targeted corpus-wide). A controller-null tap
      (Master Decoy, Frost Titan) is arm-less here (live's strict opp gate).
      Scope "opponents".
    * ``tapper_engine`` — a ``SetTapState {state: Tap}`` with a REAL
      Typed/Or target, any controller (Master Decoy / Frost Titan), plus
      the typed ``CantUntap`` static-rider arm (live's raw-"untap"
      restriction arm — the mirror types it: Frost Titan / Dungeon Geists
      nested static ``mode: CantUntap``). Self-taps (SelfRef) and untap
      engines (state Untap) never fire. Scope "any".

    Logged SUPPLEMENT tails (live-documented, phase-confirmed): the
    anaphoric "tap target creature that player controls"; the "skips their
    next untap step" tempo-skip (no SkipStep node in v0.9.0); the aura/morph
    untap-lock statics.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.iter_concepts():
            if c.role != "effect":
                continue
            if c.concept == "tap_untap":
                if settap_state(c.node) != "Tap":
                    continue
                tgt = getattr(c.node, "target", None)
                if tag_of(tgt) not in ("Typed", "Or", "And"):
                    continue  # SelfRef self-tap / no real target
                fire("tapper_engine", "any", c.raw)
                ctrl = filter_controller(tgt)
                # b11 follow-up (b), adjudicated: DefendingPlayer is
                # opponent-directed BY RULE (CR 506.2 — the defending player
                # is an opponent of the attacker; 20/21 live-verified), so it
                # joins Opponent unconditionally. A TargetPlayer tap joins
                # ONLY under an attack/damage-trigger unit (Hammers of
                # Moradin's Myriad rider — ~25 of 44 live_only recovered);
                # the one-shot/activated TargetPlayer sweeps (Sleep,
                # Dawnglare Invoker) are the genuine supplement tail.
                if ctrl in ("Opponent", "DefendingPlayer") or (
                    ctrl == "TargetPlayer"
                    and unit.origin == "trigger"
                    and unit.trigger_event in ("attacks", "deals_damage")
                ):
                    fire("tap_down", "opponents", c.raw)
            elif c.concept == "detain":
                fire("tap_down", "opponents", c.raw)
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) == "CantUntap":
                fire("tapper_engine", "any", _site_raw(sdef))
        # b11 follow-up (b) continued: a GRANTED attack-tap trigger — an
        # Aura/Equipment conferring "Whenever this creature attacks, tap
        # target creature defending player controls" (Grasp of the
        # Hieromancer, Conformer Shuriken: a ``GrantTrigger`` modification
        # whose inner trigger's effect chain carries the SetTapState).
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "GrantTrigger":
                continue
            trig = getattr(mod, "trigger", None)
            tmode = getattr(trig, "mode", None)
            tmode = tmode if isinstance(tmode, str) else tag_of(tmode)
            if tmode not in ("Attacks", "YouAttack", "DamageDone"):
                continue
            for tnode in iter_typed_nodes(getattr(trig, "execute", None)):
                if tag_of(tnode) != "SetTapState":
                    continue
                if settap_state(tnode) != "Tap":
                    continue
                tctrl = filter_controller(getattr(tnode, "target", None))
                if tctrl in ("Opponent", "DefendingPlayer", "TargetPlayer"):
                    fire("tap_down", "opponents", "")
    return out


def _tap_untap_matters(tree: ConceptTree) -> list[Signal]:
    """tap_untap_matters — the becomes-tapped/untapped payoff (CR 603.2e +
    701.26a): a trigger whose mode is ``Taps`` / ``TapsForMana`` (both the
    becomes-tapped family — Attentive Sunscribe) or ``Untaps`` (the Inspired
    payoff — Pain Seer; a SelfRef subject is live-INCLUDED, a genuine untap
    payoff). Tap DOERS (Master Decoy — a SetTapState effect, no Taps
    trigger) never fire. The granted/quoted "becomes tapped" tail (~10
    cards) is SUPPLEMENT — logged, live keeps its word mirror. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in _TAP_EVENTS:
            return [Signal("tap_untap_matters", "you", "", "", tree.name, "high")]
    return []


def _dig_until(tree: ConceptTree) -> list[Signal]:
    """dig_until — the reveal-until-a-condition deep dig (CR 701.20a): a
    ``RevealUntil`` effect whose ``player`` is the Controller (Hermit Druid —
    90 of 115 corpus). The opponent-library digs (``player``
    ParentTargetController / TriggeringPlayer / Typed — Telemin
    Performance-family mill/theft, the [P16]-adjacent direction gate) and
    the FIXED-count reveals (Fact or Fiction — a ``RevealTop`` node →
    topdeck_selection) never fire. The draw-replacement / Saga / grandeur
    residue phase emits no dig structure for is SUPPLEMENT — logged, live's
    narrowed residue mirror stays. Scope "you".
    """
    for unit in tree.units:
        desc = (getattr(unit.node, "description", None) or "").lower()
        # [P28]: phase stamps player=Controller on "each opponent reveals
        # cards from the top of THEIR library" (Mind Grind family — the
        # [P17] mis-stamp on RevealUntil), so the digger gate alone passes
        # on opponent mills. All 69 both-members are "your library" digs
        # (parity-verified); the [P8]/[P21]-precedent screen is the fix.
        if "their library" in desc:
            continue
        for c in unit.iter_concepts():
            if c.role != "effect" or c.concept != "reveal_until":
                continue
            if reveal_until_player(c.node) == "you":
                return [Signal("dig_until", "you", "", c.raw, tree.name, "high")]
    return []


def _exile_until_leaves(tree: ConceptTree) -> list[Signal]:
    """exile_until_leaves — the O-Ring exile (CR 611.2b durations + 603.6c):
    a ``ChangeZone {destination: Exile}`` whose OWNING wrapper carries the
    ``UntilHostLeavesPlay`` duration (Banisher Priest; Oblivion Ring's ETB
    trigger — the duration on the FIRST trigger alone suffices, no
    cross-ability join). Checklist #5 zone/dest ([P2]/[P4] family): the
    destination must be Exile with the duration on the same node chain — a
    permanent exile (no duration → the ported ``exile_removal``) and the LTB
    return trigger alone (TrackedSet → Battlefield; CR 603.6c's
    from-anywhere caveat) never fire. Case law (Banisher Priest): "If a
    token is exiled this way, it will cease to exist." Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("change_zone"):
            if tag_of(c.node) != "ChangeZone":
                continue
            if change_zone_dirs(c.node)[1] != "Exile":
                continue
            if effect_owner_duration(unit.node, c.node) == "UntilHostLeavesPlay":
                return [
                    Signal("exile_until_leaves", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _typed_spellcast_lane(tree: ConceptTree) -> list[Signal]:
    """typed_spellcast (§F, SUBJECT-BEARING) — the tribal cast payoff
    (CR 603.2 + 102.2): a ``SpellCast`` trigger whose watched-spell filter
    carries a vocab creature subtype AND whose ``valid_target`` is the
    Controller — the TYPED you-cast discriminator (Lys Alana Huntmaster
    carries ``valid_target {Controller}``; the symmetric "a player casts a
    Giant spell" hoser — Elvish Handservant — carries none, and an
    opponent-punisher carries Opponent). REPLACES live's
    ``_self_cast_oracle`` "you cast" regex gate with a typed read (a
    documented improvement).

    b11 follow-up (a), adjudicated: the STATIC cost-reduction form is a cast
    payoff too — "<Subtype> spells you cast cost {N} less" (the Warchief /
    Banneret family; CR 601.2f couples the discount to the cast event, so the
    tribal reducer rewards CASTING the tribe). Read the already-ported
    cost-modification static's typed ``spell_filter`` subtypes
    (vocab-validated), gated to a ``Reduce`` direction and YOUR cards
    (``affected`` controller You; a SelfRef self-discount never fires).
    Scope "you", subject = the subtype.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def emit(subtype: str) -> None:
        sub = _resolve_subject(subtype, CREATURE_SUBTYPES)
        if sub and sub not in seen:
            seen.add(sub)
            out.append(
                Signal(signal_keys.TYPED_SPELLCAST, "you", sub, "", tree.name, "high")
            )

    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event == "cast_spell":
            if trigger_caster_scope(unit.node) != "you":
                continue
            for s in filter_subtypes(getattr(unit.node, "valid_card", None)):
                emit(s)
        elif unit.origin == "static":
            if modify_cost_mode(unit.node) != "Reduce":
                continue
            affected = getattr(unit.node, "affected", None)
            if tag_of(affected) == "SelfRef":
                continue  # a self-discount (A-Demilich) is not a cast payoff
            if filter_controller(affected) != "You":
                continue  # the "you cast" coupling (checklist #6)
            for s in filter_subtypes(modify_cost_spell_filter(unit.node)):
                emit(s)
    return out


def _legends_historic_matters(tree: ConceptTree) -> list[Signal]:
    """legends_matter + historic_matters (§F) — the supertype/historic
    build-arounds, whole-card granularity (c) mirroring live's
    ``ir_predicates`` collection:

    * ``legends_matter`` — any typed filter carrying ``HasSupertype:
      Legendary`` (Reki — CR 205.4d). Being legendary ITSELF (Ruric Thar) is
      not legends-matter — no Legendary-referencing filter, no fire.
    * ``historic_matters`` — any filter carrying the ``Historic`` property
      (Jhoira — CR 700.6: "legendary supertype, the artifact card type, or
      the Saga subtype"). A Legendary-only filter (Reki) does not cross-fire.

    Both scope "you" (live).
    """
    out: list[Signal] = []
    if any(
        has_filter_property(u.node, "HasSupertype", "Legendary") for u in tree.units
    ):
        out.append(Signal("legends_matter", "you", "", "", tree.name, "high"))
    if any(has_filter_property(u.node, "Historic") for u in tree.units):
        out.append(Signal("historic_matters", "you", "", "", tree.name, "high"))
    return out


def _self_blink_lane(tree: ConceptTree) -> list[Signal]:
    """self_blink (§F) — the self-exile-and-return engine (CR 611.2b
    durations; contrast 603.6c): an effect-role ``ChangeZone {target:
    SelfRef, destination: Exile}`` whose SAME unit chains a return —
    another ``ChangeZone`` to the Battlefield naming the exiled object
    (ParentTarget / TrackedSet through a ``CreateDelayedTrigger`` —
    Aetherling's probed shape; the effect-chain walk flattens the delayed
    trigger's inner return into the unit). Live is kept-mirror-ONLY ("no
    clean structural IR form" — STALE for the v0.9.0 mirror). Cost-exiles
    live in cost leaves and self-exclude; exiling ANOTHER target (Banisher
    Priest, Oblivion Ring) fails the SelfRef gate. The "~-substituted raw"
    residue tail live's fulltext detector catches is SUPPLEMENT — logged.
    Two corpus-measured gates (97 over-fires without them; SCOPED by
    per-shape live measurement, not blanket — the parity-before-veto
    lesson): a Saga LORE-CHAPTER unit never fires (the transforming-Saga
    chapter-III "Exile this Saga, then return it … transformed" — The
    Restoration of Eiganjo family, 29 corpus, live uniformly no-fire;
    CR 714.2b + 712 — a one-shot flip vehicle, not a blink engine), and a
    GRAVEYARD-origin return never counts as the return half (unearth's
    Graveyard→Battlefield self-return — Anathemancer; CR 702.84a —
    graveyard recursion whose exile is the delayed unearth cleanup). The
    NON-Saga transform flips stay IN: live fires the ability/dies forms
    (Clive / Elesh Norn / Liliana, Heretical Healer — measured), so a
    transform veto there would regress live members. Scope "you"
    (granularity a chain-join).
    """
    for unit in tree.units:
        if unit.origin not in ("ability", "trigger"):
            continue
        if trigger_counter_filter(unit.node)[0] == "lore":
            continue  # a Saga chapter (CR 714.2b) — a flip, not a blink
        czs = [
            c
            for c in unit.effect_concepts("change_zone")
            if tag_of(c.node) == "ChangeZone"
        ]
        if not any(
            change_zone_dirs(c.node)[1] == "Exile"
            and tag_of(getattr(c.node, "target", None)) == "SelfRef"
            for c in czs
        ):
            continue
        for c in czs:
            origin, dest = change_zone_dirs(c.node)
            if dest != "Battlefield" or origin == "Graveyard":
                continue  # the unearth-style graveyard self-return
            if tag_of(getattr(c.node, "target", None)) in _SELF_BLINK_RETURN_TAGS:
                return [Signal("self_blink", "you", "", c.raw, tree.name, "high")]
    return []


# ── Batch 12 lanes (ADR-0035 Stage 2) ────────────────────────────────────────


def _scry_surveil_matters(tree: ConceptTree) -> list[Signal]:
    """scry_surveil_matters (§A) — CR 701.22a / 701.25a: a Scry / Surveil
    TRIGGER mode is the payoff watcher (Arwen Undómiel, Whispering Snitch,
    Mirko). Gate #4 membership: a bare Scry/Surveil EFFECT node (Opt — a
    doer) never fires; doers ride the ported topdeck_selection. The
    conferral/reference residue live reaches via the ADR-0027 marker is
    SUPPLEMENT-FIXABLE (the oracle carries "you scry"), logged. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in ("scry", "surveil"):
            return [Signal("scry_surveil_matters", "you", "", "", tree.name, "high")]
    return []


def _cycling_matters(tree: ConceptTree) -> list[Signal]:
    """cycling_matters (§A) — CR 702.29a: a Cycled / CycledOrDiscarded
    trigger whose watched card is NOT SelfRef (Astral Slide — null watcher;
    Archfiend of Ifnir — Typed/Another). The "when you cycle THIS card"
    bonus (Agonasaur Rex — SelfRef, 58 corpus) is membership. Reads the RAW
    mode (not the derived event — CycledOrDiscarded shares the "discarded"
    event with plain Discarded watchers). The ReduceAbilityCost{Cycling}
    static family (Fluctuator, 26 corpus) is live-verified no-fire — logged,
    not ported. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode = getattr(unit.node, "mode", None)
        mode_s = mode if isinstance(mode, str) else tag_of(mode)
        if mode_s not in ("Cycled", "CycledOrDiscarded"):
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef":
            continue
        return [Signal("cycling_matters", "you", "", "", tree.name, "high")]
    return []


def _exert_matters(tree: ConceptTree) -> list[Signal]:
    """exert_matters (§A) — CR 701.43a + 702.20b (vigilance neutralizes
    exert's won't-untap): (a) a mass-vigilance grant onto your GENERIC
    creature board (Always Watching — AddKeyword{Vigilance}, affected
    Typed[Creature] controller You, no subtype scoping; Another/NonToken
    allowed, a Counters-predicated grant is counter_grants_kw's country);
    (b) the Johan word mirror, byte-identical. Gate #4: the Exerted trigger
    (28 corpus, all SelfRef riders — Combat Celebrant) is MEMBERSHIP and
    never fires. SELF-GRANT veto via the affected-tag check. Scope "you".
    """
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword" or mod_keyword_name(mod) != "Vigilance":
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) != "Typed":
                continue  # SelfRef / ParentTarget self- or single-grant
            if "Creature" not in filter_core_types(affected):
                continue
            if filter_controller(affected) != "You" or filter_subtypes(affected):
                continue
            return [
                Signal("exert_matters", "you", "", _site_raw(sdef), tree.name, "high")
            ]
    if _JOHAN_MIRROR.search(_kept(tree)):
        return [Signal("exert_matters", "you", "", "", tree.name, "high")]
    return []


def _entered_attacker(tree: ConceptTree) -> list[Signal]:
    """entered_attacker (§A) — CR 302.6 / 603.10a: kept-mirror-ONLY, the
    EXACT live ENTERED_ATTACKER_REGEX run PER-CLAUSE over the
    reminder-stripped oracle (Pick Up the Pace, Samut). The structural
    EnteredThisTurn read would ADD the no-combat-word Deathleaper family —
    PARITY-BEFORE-VETO: the mirror is the producer; the structural adds stay
    LOGGED only. Scope "you".
    """
    if any(_ENTERED_ATTACKER_RX.search(cl) for cl in clauses(_kept(tree))):
        return [Signal("entered_attacker", "you", "", "", tree.name, "high")]
    return []


def _saga_matters(tree: ConceptTree) -> list[Signal]:
    """saga_matters (§A) — CR 714.2 / 714.4 (case law Satsuki: a lore
    counter usually triggers the next chapter): on a NON-Saga card, (a) a
    lore-kind place/remove/move counter effect (Keldon Warcaller, Satsuki,
    Myth Realized's SelfRef build-up), or (b) a Saga-subtype AFFECTED filter
    on a top-level static (Barbara Wright's read-ahead grant — a documented
    crosswalk add; live's projection dropped it). Gate #4: a Saga's OWN
    chapter triggers / ETB lore replacement are membership — the whole-card
    Saga-subtype gate excludes them (An Unearthly Child, History of
    Benalia). [P16]: a multi-choice tutor that merely CAN fetch a Saga
    (Search for Glory — live-verified no-fire) never fires — search/reveal
    selector filters are not read. Scope "you".

    Arm (c) runs BEFORE the membership gate: a ``CountersOn{lore}`` COUNT
    operand (Genesis of the Daleks' "a Dalek for each lore counter") is a
    lore PAYOFF even on a Saga itself — scaling on the pile is caring,
    while chapters merely HAVING lore thresholds (``counter_filter``) is
    membership and is never read.
    """
    for unit in tree.units:
        for c in unit.iter_concepts():
            for q in iter_typed_nodes(c.node):
                ct = getattr(q, "counter_type", None)
                if (
                    tag_of(q) == "CountersOn"
                    and isinstance(ct, str)
                    and ct.lower() == "lore"
                ):
                    return [Signal("saga_matters", "you", "", c.raw, tree.name, "high")]
    if "Saga" in tree.card_subtypes:
        return []
    for unit in tree.units:
        for c in unit.iter_concepts():
            if c.role != "effect":
                continue
            if c.concept not in ("place_counter", "remove_counter", "move_counters"):
                continue
            kind = counter_kind(c.node) or counter_kind_any(c.node)
            if kind.lower() == "lore":
                return [Signal("saga_matters", "you", "", c.raw, tree.name, "high")]
        if unit.origin == "static":
            subs = {
                s.lower() for s in filter_subtypes(getattr(unit.node, "affected", None))
            }
            if "saga" in subs:
                return [
                    Signal(
                        "saga_matters",
                        "you",
                        "",
                        _site_raw(unit.node),
                        tree.name,
                        "high",
                    )
                ]
    return []


def _life_total_set(tree: ConceptTree) -> list[Signal]:
    """life_total_set (§B) — CR 119.5 + 701.12c (case law Magister Sphinx:
    becoming 10 IS gaining/losing the difference): a ``SetLifeTotal`` with a
    PLAYER-shaped target, an ``ExchangeLifeTotals`` / ``ExchangeLifeWithStat``,
    or a one-shot ``Double{LifeTotal}`` (Celestial Mantle). Gate: phase
    misparses perpetual P/T sets as SetLifeTotal onto CREATURE filters
    (Baffling Defenses / Teyo / Mortal Flesh Is Weak — live over-fires them
    from the same misparse; the spec's rules-lawyer gate vetoes any target
    with core card types). Scope "any" (a scope-agnostic build-around).
    """
    for c in tree.effect_concepts("set_life"):
        if tag_of(c.node) == "SetLifeTotal":
            if filter_core_types(getattr(c.node, "target", None)):
                continue  # a P/T-set misparse onto a permanent filter
            return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
        return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("double_quantity"):
        if double_target_kind(c.node) == "LifeTotal":
            return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
    return []


def _unspent_mana(tree: ConceptTree) -> list[Signal]:
    """unspent_mana (§B) — CR 106.4 / 500.5 (case law Kruphix: unspent mana
    becomes colorless as steps end): RECLASSIFIED structural+mirror union —
    the ``StepEndUnspentMana`` static mode (action Retain — Upwelling;
    Transform — Horizon Stone, Kruphix; live's "v0.1.19 drops it" note was
    STALE) plus the byte-identical UNSPENT_MANA_REGEX mirror for the
    burst-rider tail (all 10 mode carriers also match the mirror — expected
    structural-arm diff 0). Scope "you" (live's forced scope — parity).
    """
    for unit in tree.units:
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "StepEndUnspentMana"
        ):
            return [
                Signal(
                    "unspent_mana", "you", "", _site_raw(unit.node), tree.name, "high"
                )
            ]
    if _UNSPENT_MANA_RX.search(_kept(tree)):
        return [Signal("unspent_mana", "you", "", "", tree.name, "high")]
    return []


def _opp_top_exile(tree: ConceptTree) -> list[Signal]:
    """opp_top_exile (§B) — CR 406.1: an ``ExileTop`` whose exiled-library
    PLAYER is an opponent — the Typed{controller: Opponent} filter (Ashiok,
    Nightmare Weaver) or a directed ``Player`` target (Circu; the caster
    aims it at an opponent's library). Gates ([P5]/[P17]): a
    Controller-resolving player is self-mill / impulse territory (Ashiok,
    Wicked Manipulator's pay-life exile rides ChangeZone, not ExileTop —
    doubly out). Scope "you" (the engine controller, matching live).
    """
    for c in tree.effect_concepts("exile_top"):
        player = getattr(c.node, "player", None)
        ptag = tag_of(player)
        if ptag == "Typed" and filter_controller(player) == "Opponent":
            return [Signal("opp_top_exile", "you", "", c.raw, tree.name, "high")]
        if ptag in ("Player", "TriggeringPlayer"):
            return [Signal("opp_top_exile", "you", "", c.raw, tree.name, "high")]
    return []


def _kill_engine(tree: ConceptTree) -> list[Signal]:
    """kill_engine (§B) — CR 305.6 / 701.8: a REPEATABLE-frame single-target
    creature ``Destroy`` on a card that is itself a Creature — an activated
    unit (Visara, Avatar of Woe, Royal Assassin's qualified "tapped
    creature") or a recurring trigger (event outside the one-shot set;
    Nekrataal's ETB destroy is out). ``DestroyAll`` wipes never fire (the
    tag IS the mass discriminator). The Evil Twin quoted-grant fold rides
    the byte-identical _REPEATABLE_KILL_RE mirror. LOW confidence, scope
    "you" (the live producer's identity — never feeds has_other_plan).
    """
    if not tree.is_type("Creature"):
        return []
    for unit in tree.units:
        repeatable = (unit.origin == "ability" and unit.kind == "Activated") or (
            unit.origin == "trigger"
            and (unit.trigger_event or "") not in _KILL_ONESHOT_EVENTS
        )
        if not repeatable:
            continue
        for c in unit.effect_concepts("destroy"):
            if tag_of(c.node) != "Destroy":
                continue
            if "Creature" in filter_core_types(getattr(c.node, "target", None)):
                return [Signal("kill_engine", "you", "", c.raw, tree.name, "low")]
    if _REPEATABLE_KILL_RE.search(_kept(tree)):
        return [Signal("kill_engine", "you", "", "", tree.name, "low")]
    return []


def _control_exchange(tree: ConceptTree) -> list[Signal]:
    """control_exchange (§C) — CR 701.12b / 108.3: the exile-your-OWNED +
    sibling return-to-battlefield chain join (granularity a — Meneldor's
    "exile up to one target creature you own, then return it"). The
    mandatory parity check ran FIRST: live fires the 18 ``ExchangeControl``
    swaps (Gilded Drake, Daring Thief, Perplexing Chimera) under the PORTED
    gain_control lane, so ONLY the exile-Owned-return shape ports here.
    Oblivion Sower (Owned:TargetPlayer — theft-ramp) and a plain blink
    (controller-You filter, no Owned predicate — Cloudshift) never fire.
    An exile filter carrying Owned:You AND controller:You is a pure value
    blink (own+control leaves no steal to recover — CR 108.3 vs 701.12b;
    Yorion, rules-lawyer-adjudicated b12): the CONJUNCTION is vetoed while
    Meneldor's controller-null Owned:You keeps firing. Scope "you".
    """
    for unit in tree.units:
        czs = [
            c
            for c in unit.effect_concepts("change_zone")
            if tag_of(c.node) == "ChangeZone"
        ]

        def _steal_recovery(target: object) -> bool:
            return (
                filter_owned_controller(target) == "You"
                and filter_controller(target) != "You"
            )

        exile_owned = any(
            change_zone_dirs(c.node)[1] == "Exile"
            and _steal_recovery(getattr(c.node, "target", None))
            for c in czs
        )
        returns = any(change_zone_dirs(c.node)[1] == "Battlefield" for c in czs)
        if exile_owned and returns:
            return [Signal("control_exchange", "you", "", "", tree.name, "high")]
    return []


def _land_exchange(tree: ConceptTree) -> list[Signal]:
    """land_exchange (§C) — CR 701.12b: an ``ExchangeControl`` either of
    whose sides is a Land-cored filter (Political Trickery, Vedalken
    Plotter), or a ``gain_control`` effect over a Land filter (live's
    "Land in ftypes" rider). Gilded Drake's creature-for-creature swap
    never fires. Scope "you".
    """
    for c in tree.effect_concepts("exchange_control"):
        for side in ("target_a", "target_b"):
            if "Land" in filter_core_types(getattr(c.node, side, None)):
                return [Signal("land_exchange", "you", "", c.raw, tree.name, "high")]
    for concept in ("gain_control", "give_control"):
        for c in tree.effect_concepts(concept):
            if "Land" in filter_core_types(effect_filter(c.node)):
                return [Signal("land_exchange", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "ChangeController":
                continue
            if "Land" in filter_core_types(getattr(sdef, "affected", None)):
                return [
                    Signal(
                        "land_exchange", "you", "", _site_raw(sdef), tree.name, "high"
                    )
                ]
    return []


def _land_denial(tree: ConceptTree) -> list[Signal]:
    """land_denial (§C) — CR 702.26: a ``PhaseOut`` whose target is the pure
    Typed[Land] controller-You board (Taniwha's upkeep mass phase-out — the
    Taniwha probe verbatim). Reality Ripple's Or-filter one-shot and Clever
    Concealment's Non-Land permanent sweep never fire (checklist #5 — the
    effect's own target node). Scope "you".
    """
    for c in tree.effect_concepts("phasing"):
        if tag_of(c.node) != "PhaseOut":
            continue
        target = getattr(c.node, "target", None)
        if tag_of(target) != "Typed":
            continue
        if set(filter_core_types(target)) != {"Land"} or filter_non_types(target):
            continue
        if filter_controller(target) == "You":
            return [Signal("land_denial", "you", "", c.raw, tree.name, "high")]
    return []


def _is_protection_animator(unit: AbilityUnit) -> bool:
    """The land_protection-only WIDER animator read (the shared b1 helper is
    untouched so the settled land_creatures_matter lane cannot move): any
    static whose subject is land-ish — the ``Land`` core OR a land SUBTYPE
    word ("Enchanted Forest" — Genju of the Cedars) — carrying an ``AddType
    Creature`` OR the ``SetCardTypes [Creature]`` rewrite (the Zendikon
    family). All controllers (live passes ("you","any"))."""
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    subject = statics[0].subject
    landish = "Land" in subject or ({w.lower() for w in subject} & _LAND_SUBTYPE_WORDS)
    if not landish or "Creature" in subject:
        return False
    for concept in statics:
        node = concept.node
        if (
            concept.concept == "add_type"
            and getattr(node, "core_type", None) == "Creature"
        ):
            return True
        if tag_of(node) == "SetCardTypes":
            cores = getattr(node, "core_types", None) or ()
            if "Creature" in cores:
                return True
    return False


def _land_protection(tree: ConceptTree) -> list[Signal]:
    """land_protection (§C) — CR 613.1d / 305: a commander animating MANY
    lands wants them kept alive. Shares the b1 animator predicate widened
    past the you-gate (Living Plane — live passes ("you","any"); the
    crosswalk's controller-less scope maps to "each", so the widened tuple
    here is ("you","any","each")), plus the byte-identical manland
    self-animate mirror (the Restless lands — phase drops the self-animate
    clause). Scope "you".
    """
    for unit in tree.units:
        if _is_protection_animator(unit):
            return [Signal("land_protection", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            # The first-class Animate node (the TLA earthbend family — Bumi,
            # Badgermole: "Animate {types: [Creature], target: Land you
            # control}"): a mass/targeted land-animate the statics walk never
            # sees (no static def — the node carries the types directly).
            if c.role == "effect" and tag_of(c.node) == "Animate":
                tgt = getattr(c.node, "target", None)
                if "Land" in filter_core_types(tgt) or (
                    {t.lower() for t in filter_subtypes(tgt)} & _LAND_SUBTYPE_WORDS
                ):
                    return [
                        Signal("land_protection", "you", "", c.raw, tree.name, "high")
                    ]
        # The threaded one-shot animate ("target Forest becomes a 4/5 …
        # creature" — Awakener Druid: a GenericEffect whose resolved target is
        # the land, mods AddType Creature).
        for resolved, sdef in iter_threaded_target_statics(unit.node):
            landish = "Land" in filter_core_types(resolved) or (
                {t.lower() for t in filter_subtypes(resolved)} & _LAND_SUBTYPE_WORDS
            )
            if not landish:
                continue
            for _sd, mod in iter_mod_sites(sdef):
                if (
                    tag_of(mod) == "AddType"
                    and getattr(mod, "core_type", None) == "Creature"
                ):
                    return [Signal("land_protection", "you", "", "", tree.name, "high")]
        # The reverse animator (Ashaya: "creatures you control are Forest
        # lands in addition …" — an AddType Land over your board; both type
        # sets live on one permanent, the same keep-my-lands-alive care).
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddType" or getattr(mod, "core_type", None) != "Land":
                continue
            affected = getattr(sdef, "affected", None)
            if filter_controller(affected) == "You":
                return [
                    Signal(
                        "land_protection", "you", "", _site_raw(sdef), tree.name, "high"
                    )
                ]
    if _MANLAND_MIRROR.search(_kept(tree)):
        return [Signal("land_protection", "you", "", "", tree.name, "high")]
    return []


def _evasion_denial(tree: ConceptTree) -> list[Signal]:
    """evasion_denial (§C) — CR 702.14: the ``IgnoreLandwalkForBlocking``
    static mode (Great Wall's plainswalk, Crevasse's mountainwalk — 9 corpus
    statics on 8 cards). The Staff of the Ages conferral residue is
    SUPPLEMENT-FIXABLE (the grant survives in the carrier's oracle), logged.
    Scope "opponents" (live).
    """
    for unit in tree.units:
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "IgnoreLandwalkForBlocking"
        ):
            return [
                Signal(
                    "evasion_denial",
                    "opponents",
                    "",
                    _site_raw(unit.node),
                    tree.name,
                    "high",
                )
            ]
    return []


def _animate_artifact(tree: ConceptTree) -> list[Signal]:
    """animate_artifact (§D) — CR 613.1d + 702.122b: kept-mirror-PRIMARY
    (verdict upheld): the EXACT live ANIMATE_ARTIFACT_REGEX over the
    reminder-stripped oracle (Karn Silver Golem, Titania's Song). All 8
    clean AddType statics already match the regex (structural assist adds
    0 — LOG only); the Animate effect tag is TLA earthbend, not artifact
    animation. A bare becomes-an-ARTIFACT type conferral (Liquimetal
    Coating, Mycosynth Lattice) is a regex non-match. Scope "you".
    """
    if _ANIMATE_ARTIFACT_RX.search(_kept(tree)):
        return [Signal("animate_artifact", "you", "", "", tree.name, "high")]
    return []


def _color_change(tree: ConceptTree) -> list[Signal]:
    """color_change (§D) — CR 105.3: kept-mirror-PRIMARY (verdict upheld —
    raw structural SetColor fires on 391 corpus cards, ~94% over-fire from
    devoid CDAs / eternalize token colors / animate riders): the EXACT live
    COLOR_CHANGE_REGEX (Alchor's Tomb, Distorting Lens). The AddChosenColor
    structural assist adds 0 over the mirror — LOG only. "Becomes colorless"
    (Ancient Kavu) is a deliberate non-match. Scope "you".
    """
    if _COLOR_CHANGE_RX.search(_kept(tree)):
        return [Signal("color_change", "you", "", "", tree.name, "high")]
    return []


def _type_change(tree: ConceptTree) -> list[Signal]:
    """type_change (§D) — CR 702.16 + 613.1d: RECLASSIFIED structural+mirror
    union — the type-HOSER read. Structural: an ``AddKeyword`` whose keyword
    is ``Protection{CardType: <arg>}`` with the argument vocab-validated
    against the creature-subtype list (Gor Muldrak's Salamanders — the
    "phase drops the argument" note was STALE); protection from a COLOR
    (White Knight) fails the vocab gate. Mirror: the live per-clause
    ``protection from (\\w+)`` vocab-gated scan for parity. Scope "you".
    """
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            arg = protection_cardtype(mod)
            if arg is None:
                continue
            w = arg.lower()
            if w in CREATURE_SUBTYPES or w.rstrip("s") in CREATURE_SUBTYPES:
                return [Signal("type_change", "you", "", "", tree.name, "high")]
    if _type_hoser_clause(_kept(tree).lower()):
        return [Signal("type_change", "you", "", "", tree.name, "high")]
    return []


def _stax_lanes(tree: ConceptTree) -> list[Signal]:
    """stax_taxes (scope "opponents") + symmetric_stax (scope "each") — CR
    101.2 + 604.1. Scope from each static's OWN who/affected node
    (checklist #5), live-parity-calibrated over the census probes:

    * **plain restrictions** (CantAttack / CantBlock / CantAttackOrBlock /
      CantUntap / CantGainLife / MustAttack / CantPlayLand): affected
      controller Opponent/TargetPlayer → stax (Propaganda, Fumiko);
      unscoped board filter → symmetric (Warmonger Hellkite, Meekstone,
      Bedlam, An-Zerrin Ruins). Gate (i): the single-creature pacify veto is
      LOAD-BEARING — a SelfRef affected (a drawback) or an EnchantedBy/
      EquippedBy-predicated subject (Pacifism, Arrest, the stun-Auras)
      opens NEITHER lane.
    * **cost taxes** (ModifyCost{Raise}): affected Opponent → stax (Aura of
      Silence); gate (ii) — a You/SelfRef direction is a self-cost quirk;
      an unscoped tax is symmetric AND co-fires stax (Sphere of Resistance —
      live's stax_tax-kind co-fire).
    * **cast/activation locks** (CantBeActivated / CantBeCast /
      CantCastDuring / CantActivateDuring / PerTurnCastLimit): ``who``
      Opponents → stax (Alhammarret, A-Teferi); ``who`` Controller → skip
      (Colfenor's Plans); else BOTH lanes (Stony Silence, Arcane
      Laboratory, Karn GC, Curse of Exhaustion — live fires both; City of
      Solitude's extra stax co-fire is a logged uniform-rule cost). The
      Arrest-shape lock (EnchantedBy source_filter) is pacified out.
    * **attack ceilings** (MaxAttackersEachCombat): defender Controller →
      stax (Crawlspace — a logged add; live misses the family); else
      symmetric (Dueling Grounds).
    * **step skips** (SkipStep): affected Player → symmetric (Stasis — a
      logged add); affected Controller → skip (Damia's self-cost).
    * **trigger suppression** (SuppressTriggers): symmetric (Hushbringer /
      Torpor Orb — logged adds; hatebear stax live misses).
    * **hand-size reducers** (MaximumHandSize, affected Opponent): stax
      co-fire (Gnat Miser, Jin-Gitaxias — live parity; the big_hand_makers
      quirk fires separately).
    * **opponents-enter-tapped** (a Moved→Battlefield replacement whose
      SetTapState{Tap} valid_card is NOT SelfRef): controller Opponent →
      stax (Authority of the Consuls, Kismet); unscoped → symmetric (Root
      Maze). A SelfRef valid_card ("this land enters tapped") is membership.
    * **residue mirrors**: the EXACT live _STAX_TAXES_RESIDUE_RE /
      _SYMMETRIC_STAX_RESIDUE_RE per-clause with the live pacify veto
      (Winter Orb's unparsed "players can't untap" clause).

    Gate (iii): an untap BLESSING (Seedborn Muse's
    UntapsDuringEachOtherPlayersUntapStep) is not in any census set.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def stax(raw: str) -> None:
        if "stax_taxes" not in seen:
            seen.add("stax_taxes")
            out.append(Signal("stax_taxes", "opponents", "", raw, tree.name, "high"))

    def sym(raw: str) -> None:
        if "symmetric_stax" not in seen:
            seen.add("symmetric_stax")
            out.append(Signal("symmetric_stax", "each", "", raw, tree.name, "high"))

    # The census walks EVERY static def reachable from a unit (a top-level
    # continuous ability AND the one-shot GenericEffect-nested defs a spell
    # confers — Falter's "creatures without flying can't block this turn" is
    # a live symmetric member). A ParentTarget affected is a single-target
    # combat trick / pacify (Sleep's rider, Basandra's {R} force) — skipped.
    for unit in tree.units:
        defs = iter_static_defs(unit.node) if unit.origin != "replacement" else ()
        for node in defs:
            mt = static_mode_tag(node)
            affected = getattr(node, "affected", None)
            atag = tag_of(affected)
            ctrl = filter_controller(affected)
            raw = _site_raw(node)
            if atag in ("SelfRef", "ParentTarget"):
                continue  # a drawback / single-target trick, never a lock
            if mt in _STAX_SIMPLE_RESTRICTIONS:
                if set(filter_predicates(affected)) & _PACIFY_PREDS:
                    continue
                if ctrl == "Opponent":
                    stax(raw)
                elif ctrl == "TargetPlayer":
                    # live scopes the directed one-shot board lock (Mana
                    # Vapors, Aggravate) "each", not "opponents" — parity.
                    sym(raw)
                elif ctrl is None and atag in ("Typed", "Or", "And"):
                    sym(raw)
            elif mt == "ModifyCost" and modify_cost_mode(node) == "Raise":
                if atag == "SelfRef" or ctrl == "You":
                    continue
                if ctrl == "Opponent":
                    stax(raw)
                else:
                    sym(raw)
                    stax(raw)
            elif mt in _STAX_LOCK_MODES:
                src = static_mode_field(node, "source_filter")
                if set(filter_predicates(src)) & _PACIFY_PREDS:
                    continue
                if tag_of(src) == "SelfRef" or atag == "SelfRef":
                    continue  # an Aura's own-view lock (Detainment Spell)
                who = static_mode_field(node, "who")
                if who == "Opponents":
                    stax(raw)
                elif who == "Controller":
                    continue
                elif who == "EnchantedCreatureController":
                    # An enchant-player curse: live fires BOTH on the
                    # per-turn cast limit (Curse of Exhaustion) but stax
                    # only on the named cast-lock (Brand of Ill Omen).
                    stax(raw)
                    if mt == "PerTurnCastLimit":
                        sym(raw)
                else:
                    sym(raw)
                    stax(raw)
            elif mt == "MaxAttackersEachCombat":
                if static_mode_field(node, "defender") == "Controller":
                    stax(raw)
                else:
                    sym(raw)
            elif mt == "SkipStep":
                if atag == "Player":
                    sym(raw)
            elif mt == "SuppressTriggers":
                sym(raw)
            elif mt == "MaximumHandSize" and ctrl == "Opponent":
                stax(raw)
        if unit.origin == "replacement":
            node = unit.node
            if getattr(node, "destination_zone", None) != "Battlefield":
                continue
            vc = getattr(node, "valid_card", None)
            if tag_of(vc) not in ("Typed", "Or", "And"):
                continue  # SelfRef "this enters tapped" is membership
            taps = any(
                c.concept == "tap_untap"
                and settap_state(c.node) == "Tap"
                and tag_of(getattr(c.node, "target", None)) == "SelfRef"
                for c in unit.effects
            )
            if not taps:
                continue
            desc = getattr(node, "description", None) or ""
            if filter_controller(vc) == "Opponent":
                stax(desc)
            elif filter_controller(vc) is None:
                sym(desc)

    for cl in clauses(_kept(tree)):
        if _restriction_pacifies_single_creature(cl):
            continue
        if _STAX_TAXES_RESIDUE_RE.search(cl):
            stax("")
        if _SYMMETRIC_STAX_RESIDUE_RE.search(cl):
            sym("")
    return out


def _keyword_counter(tree: ConceptTree) -> list[Signal]:
    """keyword_counter (§E) — CR 122.1b: a place/remove of a counter whose
    kind is in the live ``_KEYWORD_COUNTER_KINDS`` closed set (imported, not
    widened — the full 122.1b list would need its own logged pass): Arwen,
    Mortal Queen's indestructible enters-with. The counter-kind-dropped
    choice/grant tail (Wingfold Pteron's ChooseOneOf branches phase nests
    outside the effect chain) rides the live KEYWORD_COUNTER_REGEX mirror.
    Gates: P1P1/loyalty/oil/shield/rad/lore route to their own ported lanes
    via the kind set; stun is NOT a 122.1b keyword counter (CR 122.1d — a
    replacement-maker, the b11 tap cluster's country). Scope "any".
    """
    for c in tree.iter_concepts():
        if c.role != "effect":
            continue
        if c.concept not in ("place_counter", "remove_counter"):
            continue
        kind = (counter_kind(c.node) or counter_kind_any(c.node)).lower()
        kind = kind.replace(" ", "")  # phase's "double strike" → doublestrike
        if kind in _KEYWORD_COUNTER_KINDS:
            return [Signal("keyword_counter", "any", "", c.raw, tree.name, "high")]
    if _KEYWORD_COUNTER_RX.search(_kept(tree)):
        return [Signal("keyword_counter", "any", "", "", tree.name, "high")]
    return []


def _counter_grants_kw(tree: ConceptTree) -> list[Signal]:
    """counter_grants_kw (§E) — a keyword granted to YOUR creatures that
    HAVE a counter (Bramblewood Paragon's P1P1-predicated trample; Cathedral
    Acolyte's kind-agnostic Any ward). Gates: an off-kind SPECIFIC grant
    (oil/stun) is keyword_counter's domain (the P1P1/Any kind gate);
    an opponent-side subject is the wrong direction (checklist #6 — the
    controller-You gate). Scope "you".
    """
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("AddKeyword", "GrantAbility"):
                continue
            affected = getattr(sdef, "affected", None)
            kinds = counter_pred_kinds(affected)
            if not ("P1P1" in kinds or "Any" in kinds):
                continue
            if filter_controller(affected) != "You":
                continue
            return [
                Signal(
                    "counter_grants_kw", "you", "", _site_raw(sdef), tree.name, "high"
                )
            ]
    return []


def _counter_distribute(tree: ConceptTree) -> list[Signal]:
    """counter_distribute (§E) — CR 115.7f + 601.2d, the board-wide +1/+1
    spread: (a) a mass ``PutCounterAll`` of kind P1P1 onto your creatures
    (Cathars' Crusade); (b) the typed ``distribute`` marker v0.9.0 DOES
    carry on the distribute-among PutCounter (Verdurous Gearhulk — the
    spec's "[P-fold]" claim was STALE; measured, the marker is present);
    (c) the EXACT live _COUNTER_DISTRIBUTE_MIRROR per-clause
    (enters-with-ADDITIONAL — Bramblewood Paragon; support N). The plain
    self-enters arm stays deliberately DROPPED (Endless One / Triskelion →
    self_counter_grow); a lore/loyalty PutCounterAll (Satsuki) fails the
    kind gate. Scope "you".
    """
    for c in tree.effect_concepts("place_counter"):
        kind = counter_kind(c.node).upper()
        if tag_of(c.node) == "PutCounterAll" and kind == "P1P1":
            return [Signal("counter_distribute", "you", "", c.raw, tree.name, "high")]
        if distribute_counter_kind(c.node) == "P1P1":
            tgt = getattr(c.node, "target", None)
            if filter_controller(tgt) == "You":
                return [
                    Signal("counter_distribute", "you", "", c.raw, tree.name, "high")
                ]
    if any(_COUNTER_DISTRIBUTE_MIRROR.search(cl) for cl in clauses(_kept(tree))):
        return [Signal("counter_distribute", "you", "", "", tree.name, "high")]
    return []


def _superfriends_matters(tree: ConceptTree) -> list[Signal]:
    """superfriends_matters (§F) — CR 306.5: a CONDITION-site Planeswalker
    reference with a non-Opponent controller (Historian of Zhalfir's
    ControlsType, Arisen Gorgon's IsPresent, the QuantityCheck family) plus
    the typed ``YouControlNamedPlaneswalker`` activation gate (Companion of
    the Trials — a documented add over live's projection carry). Gates: an
    effect TARGET filter naming a Planeswalker is removal (condition sites
    only — Hero's Downfall never fires); a ``TargetMatchesFilter`` condition
    references the spell's own target (Chandra's Defeat — removal, skipped
    subtree); BEING a planeswalker is membership. Loyalty-trigger /
    GrantExtraLoyaltyActivations adds stay LOGGED, unported. Scope "you".
    """

    def scan(node: object, depth: int) -> bool:
        if depth > 24:
            return False
        if isinstance(node, MirrorVariant):
            return scan(node.inner, depth + 1)
        if isinstance(node, list):
            return any(scan(e, depth + 1) for e in node)
        if not isinstance(node, TypedMirrorNode):
            return False
        t = tag_of(node)
        if t == "TargetMatchesFilter":
            return False  # a removal condition on the spell's own target
        if t == "WheneverEvent":
            # an event-watcher's recipient list (Or[Player, Planeswalker] —
            # an attacked opposing planeswalker per CR 506.2) is event
            # plumbing, not a planeswalker reference (adjudicated b12:
            # Hunter's Insight, Flitterwing Nuisance)
            return False
        if t == "YouControlNamedPlaneswalker":
            return True
        if (
            t == "Typed"
            and "Planeswalker" in filter_core_types(node)
            and filter_controller(node) != "Opponent"
        ):
            return True
        return any(scan(getattr(node, f.name), depth + 1) for f in dc_fields(node))

    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            if scan(site, 0):
                return [
                    Signal("superfriends_matters", "you", "", "", tree.name, "high")
                ]
    # The live producer is condition-arm + the SUPERFRIENDS_MATTERS_REGEX kept
    # WORD MIRROR (_signals_ir:1688 — the broad planeswalkers-as-a-group refs:
    # anthems, loyalty-counter payoffs, activate-loyalty engines, PW-ability
    # copiers). The spec cited only the condition arm; without the mirror the
    # lane reproduced 15% — port the pinned live constant flat, byte-identical.
    if _SUPERFRIENDS_RX.search(_kept(tree)):
        return [Signal("superfriends_matters", "you", "", "", tree.name, "high")]
    return []


def _commander_matters(tree: ConceptTree) -> list[Signal]:
    """commander_matters (§F) — CR 903.3: an ``IsCommander`` FILTER property
    anywhere on the card (Bastion Protector, Anara, Forge of Heroes).
    CRITICAL gate: the card-level is_commander / brawl_commander metadata
    flags are NEVER read — eligibility is not caring. The
    CommanderManaValue / commander-cast trigger tail stays LOGGED, unported.
    Scope "you".
    """
    if any(has_filter_property(u.node, "IsCommander") for u in tree.units):
        return [Signal("commander_matters", "you", "", "", tree.name, "high")]
    return []


def _big_hand_lanes(tree: ConceptTree) -> list[Signal]:
    """big_hand_makers + big_hand_matters (§F) — CR 402.2, one shared walk:

    * **makers** — the ``NoMaximumHandSize`` static mode (Reliquary Tower,
      Kruphix) or effect node, the ``MaximumHandSize{SetTo/AdjustedBy}``
      family (Cursed Rack, Gnat Miser, Jin-Gitaxias — live's mirror keeps
      the REDUCERS in the lane; the parity quirk is kept and logged for a
      future lane split), plus the byte-identical maker mirror.
    * **matters** — a ``HandSize``-family qty operand reading YOUR hand
      ([P5] gate — Maro's dynamic-P/T pair, Akki Underling's threshold
      condition; an opponent-hand count is vetoed), plus the byte-identical
      matters mirror (Body of Knowledge fires BOTH halves).

    Both scope "you" (the live pair's identity).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    kept = _kept(tree)
    for unit in tree.units:
        if unit.origin == "static":
            mt = static_mode_tag(unit.node)
            if mt in ("NoMaximumHandSize", "MaximumHandSize"):
                fire("big_hand_makers", _site_raw(unit.node))
        for c in unit.effect_concepts("no_max_handsize"):
            fire("big_hand_makers", c.raw)
        # matters SITE gate: only a CONDITION threshold (Akki Underling)
        # or a dynamic-P/T modification value (Maro) is a grip PAYOFF — a
        # raw count ref ("discard your hand" = Discard{count: HandSize})
        # is not, and the hellbent family (HandSize EQ 0 — Bloodhall
        # Priest) is the OPPOSITE payoff, so the condition arm requires a
        # GE/GT comparison against a full-grip bar (>= 4 — the live
        # mirror's "five or more" family, Akki's GE 7).
        for site in iter_condition_sites(unit.node):
            for q in iter_typed_nodes(site):
                if tag_of(q) != "QuantityComparison":
                    continue
                lhs = getattr(q, "lhs", None)
                if "you" not in hand_size_scopes(lhs):
                    continue
                if getattr(q, "comparator", None) not in ("GE", "GT"):
                    continue
                rhs = getattr(q, "rhs", None)
                val = getattr(rhs, "value", None) if tag_of(rhs) == "Fixed" else None
                if isinstance(val, int) and val >= 4:
                    fire("big_hand_matters", "")
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) in _DYNAMIC_PT_MODS and "you" in hand_size_scopes(mod):
                fire("big_hand_matters", "")
    if _BIG_HAND_MAKERS_MIRROR.search(kept):
        fire("big_hand_makers", "")
    if _BIG_HAND_MATTERS_MIRROR.search(kept):
        fire("big_hand_matters", "")
    return out


def _vehicles_matter(tree: ConceptTree) -> list[Signal]:
    """vehicles_matter (§F) — CR 301.7 + 702.122, the four-arm union:
    (a) a Crews / SaddlesOrCrews trigger (Gearshift Ace, Speedway Fanatic,
    Tiana — the crewING pilot's payoff, SelfRef watcher included);
    (b) a top-level static whose AFFECTED filter subtypes contain Vehicle,
    controller You (Aeronaut Admiral; Depala's "Each Vehicle you control" —
    a structural add over live's plural-literal miss, logged);
    (c) a graveyard→battlefield recursion over a Vehicle filter
    (Greasefang); (d) the EXACT live VEHICLES_MATTER_REGEX mirror.
    Gate #4 membership: a card that IS a Vehicle never fires from its own
    nodes (arms a-c gated; Smuggler's Copter/Peacewalker); ``BecomesCrewed``
    with a SelfRef watcher (Ghost Ark) is not a ``crews?`` payoff — its
    mode is outside arm (a)'s set. Scope "you".
    """
    kept = _kept(tree)
    if "Vehicle" not in tree.card_subtypes:
        for unit in tree.units:
            if unit.origin == "trigger" and unit.trigger_event in (
                "crews",
                "saddlesorcrews",
            ):
                return [Signal("vehicles_matter", "you", "", "", tree.name, "high")]
            if unit.origin == "static":
                affected = getattr(unit.node, "affected", None)
                # Word-token match: phase emits Depala's subject as the
                # multi-word subtype wart ``{Subtype: "Each Vehicle"}`` —
                # the probed v0.9.0 shape, so the gate matches the
                # ``vehicle`` TOKEN, not the raw string.
                subs = {w for s in filter_subtypes(affected) for w in s.lower().split()}
                if "vehicle" in subs and filter_controller(affected) == "You":
                    return [
                        Signal(
                            "vehicles_matter",
                            "you",
                            "",
                            _site_raw(unit.node),
                            tree.name,
                            "high",
                        )
                    ]
            for c in unit.effect_concepts("change_zone"):
                origin, dest = change_zone_dirs(c.node)
                if origin != "Graveyard" or dest != "Battlefield":
                    continue
                tsubs = {
                    s.lower() for s in filter_subtypes(getattr(c.node, "target", None))
                }
                if "vehicle" in tsubs:
                    return [
                        Signal("vehicles_matter", "you", "", c.raw, tree.name, "high")
                    ]
    if _VEHICLES_MATTER_RX.search(kept):
        return [Signal("vehicles_matter", "you", "", "", tree.name, "high")]
    return []


# ── Batch 13 lanes (ADR-0035 Stage 2): the field-lookup wholesale batch ──────

# Byte-identical compiled mirrors. island_matters imports the pinned shared
# source (_sweep_detectors.ISLAND_MATTERS_REGEX — the live row's own constant);
# poison / suspend / curse copy the three INLINE (unnamed) _IR_KEPT_DETECTORS
# rows (_signals_ir ~2324-2340 / ~2511-2519 — the _JOHAN_MIRROR precedent for
# rows with no importable name). Live runs them FLAT over the reminder-stripped
# kept oracle; so do these.
_ISLAND_MATTERS_RX = re.compile(ISLAND_MATTERS_REGEX, re.IGNORECASE)
_POISON_MATTERS_MIRROR = re.compile(r"poison counters?", re.IGNORECASE)
_SUSPEND_MATTERS_MIRROR = re.compile(
    r"\bsuspend\b|time counter|time travel|\bvanishing\b|\bimpending\b",
    re.IGNORECASE,
)
_CURSE_MATTERS_MIRROR = re.compile(
    r"curse spells?|curses? you (?:cast|control|own)"
    r"|(?:\ba|target|each|another|your) curse\b|curse cards?",
    re.IGNORECASE,
)

# The batch-13 Scryfall-keyword rows (lowercased-membership → lane key; every
# row scope "you", subject ""). These ARE membership lanes — the BEARER fires
# (checklist #4a): companion / specialize / madness / affinity / scavenge and
# the has_* keys tag the card that carries the mechanic. Byte-faithful to the
# live _IR_KEYWORD_MAP rows (:607); the MTGJSON string gotchas ('Choose a
# background' lowercase b, "Doctor's companion", 'Friends') are preserved by
# the lowercase membership gate. companion is deliberately NOT partner
# (CR 702.139 — a deckbuild constraint); "Friends" ∈ partner carries the
# Astarion source-data quirk (MTGJSON tags his modal label "Friends" as a
# keyword — live fires it, ported as-is + logged).
_B13_KEYWORD_LANES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"companion"}), "companion_keyword"),  # CR 702.139
    (frozenset({"banding"}), "has_banding"),  # CR 702.22
    (frozenset({"dash"}), "has_dash"),  # CR 702.109 (SOLE producer)
    (frozenset({"enlist"}), "has_enlist"),  # CR 702.154
    (frozenset({"specialize"}), "specialize_matters"),  # DD4 (digital)
    # CR 118/601 + 702.190a/.188a/.187a-c — the three alternative-cost
    # keyword abilities (sneak ALSO fires the unported recast_etb live-side;
    # only this row is batch-13's).
    (frozenset({"sneak", "web-slinging", "mayhem"}), "alt_cost_keyword"),
    # CR 702.124/.124a/.124k/.124m/.124i — the partner family (MTGJSON folds
    # "Friends forever" → 'Partner').
    (
        frozenset(
            {
                "partner",
                "partner with",
                "choose a background",
                "doctor's companion",
                "friends",
            }
        ),
        "partner_background",
    ),
    (frozenset({"madness"}), "madness_matters"),  # CR 702.35
    (frozenset({"affinity"}), "affinity_type"),  # CR 702.41
    # CR 702.97 — the scavenge_fuel arm only; the graveyard_matters +
    # plus_one_makers co-fires ride the already-ported b4/b3 keyword rows.
    (frozenset({"scavenge"}), "scavenge_fuel"),
    (frozenset({"soulbond"}), "has_soulbond"),  # CR 702.95
    (frozenset({"mutate"}), "has_mutate"),  # CR 702.140
    (frozenset({"ninjutsu", "commander ninjutsu"}), "has_ninjutsu"),  # CR 702.49
    # CR 702.93 undying / 702.79 persist (the sibling dies_recursion /
    # plus_one_makers fans are already-ported earlier-batch rows).
    (frozenset({"undying", "persist"}), "has_undying_persist"),
    # CR 702.82 (sacrifice_outlets / plus_one_makers fans ride earlier rows).
    (frozenset({"devour"}), "has_devour"),
    (frozenset({"changeling"}), "has_changeling"),  # CR 702.73
    # CR 702.116 (the attack_matters co-fire rides the b3 keyword row).
    (frozenset({"myriad"}), "myriad_grant"),
)


def _keyword_field_signals_b13(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-13 Scryfall-keyword field-lookups (checklist #3 survivors).

    Reading the STRUCTURED keyword array (not oracle text) keeps the lanes
    immune to name / ability-word collisions (Persistent Petitioners never
    fires has_undying_persist). The keyword-LESS granter / payoff tails ride
    :func:`_b13_conferred_grant_lanes` and the structural arms below.
    """
    low = {k.lower() for k in keywords}
    return [
        Signal(key, "you", "", "", name, "high")
        for kws, key in _B13_KEYWORD_LANES
        if low & kws
    ]


# AddKeyword-modification keyword name → the membership lane its keyword-less
# GRANTER opens (CR 702.97 / 702.49 / 702.93 / 702.79 / 702.73 / 702.116 /
# 702.85). The granter confers the mechanic on your creatures, so the card is
# lane MATERIAL exactly like the bearer (live's conferred-grant markers).
# banding is deliberately ABSENT: AddKeyword{Banding} granters (Baton of
# Morale) must NOT fire has_banding (the batch-13 reverse trap — the live pop
# is keyword-only).
_B13_MOD_GRANT_LANES: dict[str, str] = {
    "Scavenge": "scavenge_fuel",
    "Ninjutsu": "has_ninjutsu",
    "Undying": "has_undying_persist",
    "Persist": "has_undying_persist",
    "Changeling": "has_changeling",
    "Myriad": "myriad_grant",
    "Cascade": "cascade_matters",
}

# Raw-anchor → lane rows for the conferred/reference tails phase leaves
# un-typed (each anchor is the LIVE projection marker's own pinned regex —
# project.py's _narrow_* sources, imported single-source). Scanned FLAT over
# the reminder-stripped kept oracle, mirroring the marker's ability-raw scan.
_B13_RAW_ANCHOR_LANES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_MADNESS_GRANT, "madness_matters"),  # Anje, Falkenrath Gorger ([P20])
    (_AFFINITY_GRANT, "affinity_type"),  # Don & Raph / Saheeli / Mycosynthwave
    (_SOULBOND_REF, "has_soulbond"),  # Flowering Lumberknot
    (_MUTATE_COND, "has_mutate"),  # Pollywog Symbiote
    (_UNDYING_PERSIST_GRANT, "has_undying_persist"),  # Haunted One's quoted gain
    (_CHANGELING_REF, "has_changeling"),  # Belonging, Birthing Boughs, …
    (_CASCADE_GRANT, "cascade_matters"),  # Averna / Zhulodok ([P20]) / quirks
)


def _b13_conferred_grant_lanes(tree: ConceptTree) -> list[Signal]:
    """The batch-13 keyword-LESS granter / conferred-reference top-ups.

    Four typed reads + the pinned raw anchors (checklist #3 — structural
    where the spec's probes say so, raw-bridge where phase drops the grant):

    * ``AddKeyword`` mod-walk (:data:`_B13_MOD_GRANT_LANES`) — Varolz's
      Scavenge, Satoru's Ninjutsu, Mikaeus's Undying, Cauldron's Persist,
      Blade of Selves' Myriad, Yidris's sub-ability Cascade;
    * ``CastWithKeyword`` statics — Tezzeret's ``{Affinity: …}``, Maelstrom
      Nexus's ``Cascade`` (CR 601.3e);
    * token-PROFILE keywords — Dragon Broodmother's ``{Devour: 2}`` token,
      Maskwood Nexus's Changeling Shapeshifter (CR 111.4);
    * the ``AddAllCreatureTypes`` modification — Mistform Ultimus's "every
      creature type" static (CR 205.3c) → has_changeling;
    * the raw anchors (:data:`_B13_RAW_ANCHOR_LANES`) for the conferred /
      quoted residue whose grant phase folds into a carrier ([P20] family —
      supplement-fixable, logged).

    NO subject is emitted anywhere (live subject "" — affinity's "type"
    travels in serve prose only).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def add(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            tag = tag_of(mod)
            if tag == "AddKeyword":
                lane = _B13_MOD_GRANT_LANES.get(mod_keyword_name(mod) or "")
                if lane is not None:
                    add(lane, "")
            elif tag == "AddAllCreatureTypes":
                add("has_changeling", "")
        for sdef in iter_static_defs(unit.node):
            cw = cast_with_keyword_name(sdef)
            if cw == "Affinity":
                add("affinity_type", _site_raw(sdef))
            elif cw == "Cascade":
                add("cascade_matters", _site_raw(sdef))
        for q in iter_typed_nodes(unit.node):
            profile = token_profile_keywords(q)
            if "Devour" in profile:
                add("has_devour", "")
            if "Changeling" in profile:
                add("has_changeling", "")
            # Copy-EXCEPTION myriad conferral (CR 707.9a — "except it has
            # myriad": Auton Soldier's enters-as-a-copy, Muddle's becomes-a-
            # copy): the grant rides the copy node's ``additional_
            # modifications`` list, which the shared mod-walk (a
            # ``modifications`` reader) never reaches. Live carries these
            # via the projection's copy-exception marker; Myriad-only (the
            # banked pop has no other b13 copy-exception member).
            amods = getattr(q, "additional_modifications", None)
            if isinstance(amods, list) and any(
                isinstance(m, TypedMirrorNode)
                and tag_of(m) == "AddKeyword"
                and mod_keyword_name(m) == "Myriad"
                for m in amods
            ):
                add("myriad_grant", "")
    kept = _kept(tree)
    for pat, key in _B13_RAW_ANCHOR_LANES:
        if pat.search(kept):
            add(key, "")
    return out


def _boast_matters(tree: ConceptTree) -> list[Signal]:
    """boast_matters (§C) — CR 702.142: the boast PAYOFF arm, two typed
    nodes ONLY (no regex): the ``KeywordAbilityActivated{Boast}`` trigger
    mode (Frenzied Raider) and the ``ModifyActivationLimit{keyword:
    "boast"}`` static mode (Birgi). The ModifyActivationLimit guard is
    keyword=="boast" — Wonder Man's carries keyword "power-up" (checklist
    #4b: the BEARER — Varragoth — rides the ported boast_makers keyword
    row and must never fire here)."""
    for unit in tree.units:
        mode = getattr(unit.node, "mode", None)
        if (
            isinstance(mode, MirrorVariant)
            and mode.key == "KeywordAbilityActivated"
            and tag_of(mode.inner) == "Boast"
        ):
            return [Signal("boast_matters", "you", "", "", tree.name, "high")]
        if (
            static_mode_tag(unit.node) == "ModifyActivationLimit"
            and static_mode_field(unit.node, "keyword") == "boast"
        ):
            return [Signal("boast_matters", "you", "", "", tree.name, "high")]
    return []


def _convoke_matters(tree: ConceptTree) -> list[Signal]:
    """convoke_matters (§C) — CR 702.51: a cast-spell TRIGGER whose sentence
    carries "convoke" (the live in-loop arm's _CONVOKE_RAW over the
    consequence raws; the qualifier survives only in the description, phase
    tags a bare cast trigger). Pop = exactly 3 (Joyful Stormsculptor, Kasla,
    Saint Traft and Rem Karolus). Boundary (checklist #4b): bearers (Chord
    of Calling) ride convoke_makers; the CastWithKeyword{Convoke} granter
    (Chief Engineer) rides the b9 spell_keyword_grant — neither is routed
    here."""
    for unit in tree.units:
        if unit.trigger_event != "cast_spell":
            continue
        desc = getattr(unit.node, "description", None)
        if isinstance(desc, str) and _CONVOKE_RAW.search(desc):
            return [Signal("convoke_matters", "you", "", desc, tree.name, "high")]
    return []


def _curse_matters(tree: ConceptTree) -> list[Signal]:
    """curse_matters (§C) — CR 205.3h: a card that REFERENCES the Curse
    subtype — a trigger watching Curses (Lynde's dies filter), an effect
    acting on a Curse subject (Witchbane Orb's DestroyAll) — plus the
    byte-identical kept mirror for the search-filter drop (Curse of
    Misfortunes — [P11] family, still dropped in v0.9.0) and the
    acknowledged "a curse counter" quirk (Blue Screen of Death, not-cl).
    MEMBERSHIP stays OUT: BEING an Aura — Curse (Cruel Reality) never
    fires (the live :2509-2510 deferral)."""
    for unit in tree.units:
        vc = getattr(unit.node, "valid_card", None)
        if vc is not None and "Curse" in filter_subtypes(vc):
            return [Signal("curse_matters", "you", "", "", tree.name, "high")]
        for c in unit.effects:
            filt = effect_filter(c.node)
            if filt is not None and "Curse" in filter_subtypes(filt):
                return [Signal("curse_matters", "you", "", c.raw, tree.name, "high")]
    if _CURSE_MATTERS_MIRROR.search(_kept(tree)):
        return [Signal("curse_matters", "you", "", "", tree.name, "high")]
    return []


def _foretell_matters(tree: ConceptTree) -> list[Signal]:
    """foretell_matters (§C) — CR 702.143: the ``Foretold`` subject-
    predicate read, incl. count-operand subjects (Niko Defies Destiny —
    the property nests inside amount/inner/qty/filter/properties; Alrund's
    dynamic-P/T operand). Pop == the v0.9.0 Foretold property census
    (exactly 3 cards). Boundary (checklist #4b): bearers AND granters /
    payoff-triggers (Ranar, Dream Devourer) ride the ported
    foretell_makers keyword+marker rows, never this lane."""
    for unit in tree.units:
        for q in iter_typed_nodes(unit.node):
            for fname in ("subject", "filter", "target", "affected", "valid_card"):
                filt = getattr(q, fname, None)
                if filt is not None and "Foretold" in filter_predicates(filt):
                    return [
                        Signal("foretell_matters", "you", "", "", tree.name, "high")
                    ]
    return []


def _keyword_soup(tree: ConceptTree) -> list[Signal]:
    """keyword_soup (§C) — CR 702: the keyword-stacking granter, two arms.

    (a) ≥5 DISTINCT evergreen ``AddKeyword`` keyword names WITHIN ONE
    ability site (per-unit, never per-card — two separate 3-keyword grants
    must not sum to 6): Cairn Wanderer's one static with 10 mods, Odric /
    Concerted Effort's per-keyword statics under ONE trigger execute,
    Soulflayer's under one spell GenericEffect, Chromanticore's bestow
    static's 5. The evergreen vocabulary is the LIVE ``_EVERGREEN_CK``
    (space-stripped lower — "FirstStrike" → "firststrike").

    (b) the "same is true" absorb arm: an evergreen grant / place_counter
    site plus the live ``_SAME_TRUE_KW_RE`` anchor in the granting UNIT's
    OWN text — description + effect raws, never the whole kept oracle
    (Urborg Scavengers, Escaped Shapeshifter — phase collapses the
    conferred list to one lead-keyword grant, defeating the count; Roshan's
    same-true extends an Assassin SUBTYPE grant on a different sentence and
    must not absorb through his menace unit — adjudicated b13, CR
    205.1b/205.3m vs 702.111a)."""
    for unit in tree.units:
        unit_text = " ".join(
            [getattr(unit.node, "description", None) or ""]
            + [c.raw for c in unit.iter_concepts() if c.raw]
        )
        same_true = bool(_SAME_TRUE_KW_RE.search(unit_text))
        kinds: set[str] = set()
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = (mod_keyword_name(mod) or "").replace(" ", "").lower()
            if kw:
                kinds.add(kw)
        if len(kinds & _EVERGREEN_CK) >= 5:
            return [Signal("keyword_soup", "you", "", "", tree.name, "high")]
        if same_true and kinds & _EVERGREEN_CK:
            return [Signal("keyword_soup", "you", "", "", tree.name, "high")]
        if same_true and any(
            c.concept == "place_counter"
            and (counter_kind(c.node) or "").replace(" ", "").lower() in _EVERGREEN_CK
            for c in unit.effects
        ):
            return [Signal("keyword_soup", "you", "", "", tree.name, "high")]
    return []


def _island_matters(tree: ConceptTree) -> list[Signal]:
    """island_matters (§D) — CR 702.14c: the pinned ISLAND_MATTERS_REGEX
    kept mirror (Dandân, the serpents, Zhou Yu — present in phase v0.9.0
    and firing; an implement-time "absent entirely" claim was retracted by
    the b13 adjudication). Bearers/granters of islandwalk are
    island_MAKERS material (Segovian Leviathan never fires here)."""
    if _ISLAND_MATTERS_RX.search(_kept(tree)):
        return [Signal("island_matters", "you", "", "", tree.name, "high")]
    return []


def _poison_matters(tree: ConceptTree) -> list[Signal]:
    """poison_matters (§D) — CR 122 + 704.5c, scope "opponents": the
    "poison counter" reference mirror (the ADR-0034 partition: the
    infect/toxic/poisonous keyword BEARERS ride poison_makers). Includes
    the poison-GIVERS that spell out "poison counter" (Fynn, Caress of
    Phyrexia, Vraska) — live behavior, ported byte-identically; a
    reminder-only Infect bearer (Glistener Elf) is stripped and stays
    out."""
    if _POISON_MATTERS_MIRROR.search(_kept(tree)):
        return [Signal("poison_matters", "opponents", "", "", tree.name, "high")]
    return []


def _suspend_matters(tree: ConceptTree) -> list[Signal]:
    """suspend_matters (§D) — CR 702.62: the five-arm time-counter mirror.
    Deliberately BROAD (live's SWEEP_LABELS breadth, ported as-is +
    logged): fires bearers (un-parenthesized "Suspend 4—{1}{U}" survives
    stripping), Vanishing, Impending, and every time-counter manipulator.
    "suspended card" does NOT match ``\\bsuspend\\b`` (Clockspinning — the
    sharpest boundary)."""
    if _SUSPEND_MATTERS_MIRROR.search(_kept(tree)):
        return [Signal("suspend_matters", "you", "", "", tree.name, "high")]
    return []


def _keyword_tribe(tree: ConceptTree) -> list[Signal]:
    """keyword_tribe (§D) — CR 109.3 + 702: the SUBJECT-CARRYING
    byte-identical mirror — re-run the EXACT live producer
    (``_detect_keyword_tribe``, imported like live does) PER-CLAUSE over
    the reminder-stripped kept oracle, emitting the capitalized ability
    keyword as the Signal SUBJECT (checklist #6 — the subject is
    LOAD-BEARING; the per-subject serve spec interpolates it). NOT
    structural: phase's WithKeyword covers ~70 but loses the tutor
    (Isperia), play-from-top (Errant and Giada), keyword-count scalers and
    granted-fly riders. Face-join caveat: the crosswalk runs per face
    record; the shadow diff unions faces by oracle_id (Henrika fires from
    the back face)."""
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()
    for clause in clauses(_kept(tree)):
        for key, scope, subject in _detect_keyword_tribe(clause):
            ident = (key, scope, subject)
            if ident not in seen:
                seen.add(ident)
                out.append(Signal(key, scope, subject, clause, tree.name, "high"))
    return out


_LANES = (
    _win_lose_game,
    _discard_makers,
    _spell_copy_makers,
    _token_maker,
    _draw_matters,
    _land_creatures_matter,
    _death_matters,
    _extra_turns,
    _lifegain_makers,
    _reanimator,
    _plus_one_makers,
    _direct_damage,
    _landfall,
    _sacrifice_outlets,
    _lifegain_matters,
    _blink_flicker,
    _tokens_matter,
    _ramp,
    _artifacts_enchantments_matter,
    _creatures_matter,
    _attack_tapped_matters,
    _any_counter_makers,
    _minus_counters_matter,
    _plus_one_matters,
    _any_counter_matters,
    _gain_control,
    _resource_token_makers,
    _proliferate_makers,
    _energy_makers,
    _voltron_makers,
    _voltron_matters,
    _graveyard_makers,
    _graveyard_matters,
    _fight_makers,
    _goad_makers,
    _regenerate_makers,
    _lifeloss_makers,
    _lifeloss_matters,
    _edict_makers,
    _land_sacrifice_makers,
    _debuff_makers,
    _lure_makers,
    _copy_clone,
    _connive_makers,
    _explore_makers,
    _suspect_makers,
    _combat_damage_to_opp,
    _monarch,
    _venture,
    _ring,
    _discover_makers,
    _daynight_makers,
    _phasing_makers,
    _voting_makers,
    _amass_makers,
    _incubate_makers,
    _facedown_makers,
    _dice_makers,
    _cast_from_exile,
    _counter_kind_lanes,
    _player_counter_makers,
    _count_operand_lanes,
    _modified_matters,
    _predicate_build_around,
    _coin_flip,
    _opponent_discard,
    _extra_combats,
    _cost_reduction,
    _donate_makers,
    _conjure_makers,
    _blocked_matters,
    _initiative,
    _end_the_turn,
    _opponent_exile_makers,
    _mana_amplifier,
    _extra_land_drop,
    _group_mana,
    _draw_for_each,
    _discard_outlet,
    _mass_removal,
    _mass_bounce,
    _exile_removal,
    _lands_matter,
    _resource_token_matters,
    _anthem_static,
    _pump_scaling_lanes,
    _self_pump,
    _team_buff,
    _cheat_into_play,
    _impulse_top_play,
    _play_from_top,
    _counter_manipulation,
    _discard_matters,
    _opponent_draw_matters,
    _self_death_payoff,
    _dies_recursion,
    _creature_recursion,
    _card_draw_engine,
    _group_hug_draw,
    _target_player_draws,
    _activated_draw,
    _topdeck_selection,
    _topdeck_stack,
    _combat_buff_engine,
    _land_sacrifice_matters,
    _exile_matters,
    _energy_matters,
    _counter_move,
    _explore_matters,
    _dice_matters,
    _extra_upkeep_end,
    _facedown_matters,
    _spell_keyword_grant,
    _hand_disruption,
    _etb_trigger_lanes,
    _ltb_matters,
    _creature_cast_trigger,
    _opponent_cast_matters,
    _combat_damage_lanes,
    _second_spell_matters,
    _xspell_matters,
    _counter_control,
    _bounce_tempo,
    _power_double,
    _keyword_grant_lanes,
    _base_pt_set,
    _variable_pt,
    _trigger_doubling,
    _forced_attack,
    _damage_prevention,
    _damage_equal_power,
    _replacement_doubler_lanes,
    _damage_trigger_lanes,
    _mass_damage_lanes,
    _counter_place_trigger,
    _tribal_etb_multi,
    _typed_enters_punish,
    _noncreature_cast_punish,
    _tap_lanes,
    _tap_untap_matters,
    _dig_until,
    _exile_until_leaves,
    _typed_spellcast_lane,
    _legends_historic_matters,
    _self_blink_lane,
    _scry_surveil_matters,
    _cycling_matters,
    _exert_matters,
    _entered_attacker,
    _saga_matters,
    _life_total_set,
    _unspent_mana,
    _opp_top_exile,
    _kill_engine,
    _control_exchange,
    _land_exchange,
    _land_denial,
    _land_protection,
    _evasion_denial,
    _animate_artifact,
    _color_change,
    _type_change,
    _stax_lanes,
    _keyword_counter,
    _counter_grants_kw,
    _counter_distribute,
    _superfriends_matters,
    _commander_matters,
    _big_hand_lanes,
    _vehicles_matter,
    _b13_conferred_grant_lanes,
    _boast_matters,
    _convoke_matters,
    _curse_matters,
    _foretell_matters,
    _keyword_soup,
    _island_matters,
    _poison_matters,
    _suspend_matters,
    _keyword_tribe,
)


def extract_crosswalk_signals(
    tree: ConceptTree,
    *,
    keys: frozenset[str] = PORTED_KEYS,
    keywords: frozenset[str] = frozenset(),
) -> list[Signal]:
    """Run the ported crosswalk lanes over one concept tree; dedupe by ident.

    Returns the ``Signal`` list for the ported batch, sliced to ``keys``, with the
    whole-card ``spell_copy_makers`` → ``spellcast_matters`` reconciliation applied
    (granularity c — mirrors ``signals.py`` lines 185-188: a spell-copier wants a
    dense instant/sorcery base, so a ``spellcast_matters`` LOW is cross-opened when
    absent).

    ``keywords`` is the card's Scryfall keyword array (the bulk record's
    ``keywords``), the field-lookup source ``mill_makers`` gates on — it is NOT in
    the phase typed substrate (phase carries no ``Mill`` keyword), so the caller
    supplies it (the shadow diff from the bulk record, the tests from the fixture).
    """
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(sig: Signal) -> None:
        if sig.key not in keys:
            return
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(sig)

    for lane in _LANES:
        for sig in lane(tree):
            add(sig)
    for sig in _mill_makers(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b5(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b7(frozenset(keywords), tree.name):
        add(sig)
    for sig in _keyword_field_signals_b13(frozenset(keywords), tree.name):
        add(sig)

    # Whole-card reconciliation (granularity c): cross-open spellcast_matters LOW
    # from a spell-copier that has no native spellcast signal in this batch.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        add(Signal("spellcast_matters", "you", "", "", tree.name, "low"))

    return out
