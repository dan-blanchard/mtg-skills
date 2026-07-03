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

from mtg_utils._card_ir.crosswalk import (
    ARTIFACT_TOKEN_SUBTYPES,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    additional_phase_kind,
    amount_factor,
    amount_is_scaling,
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
    damage_recipient_is_player,
    discard_recipient_scope,
    effect_filter,
    effect_owner_player_scope,
    effect_reaches_player,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    filter_without_keywords,
    iter_cost_leaves,
    iter_mod_sites,
    lifeloss_recipient_scope,
    mana_replacement_multiplier,
    mod_value,
    modify_cost_mode,
    node_lure_mode,
    permission_tag,
    player_counter_kind,
    power_threshold_preds,
    produced_contribution,
    pump_is_negative,
    recipient_tag,
    ref_qty_tag,
    static_mode_tag,
    tag_of,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.mirror.runtime import TypedMirrorNode
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._signals_regex import Signal, _resolve_subject
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

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


def _is_creature_animator(unit: object) -> bool:
    """A static ability that turns its Land subject into a creature (animate-land).

    Granularity (b) per-ability aggregation: the unit's ``affected`` Land subject
    and an ``AddType Creature`` (or a base-P/T set that makes it a creature) modi-
    fication are read TOGETHER off one continuous ability — the split-subject the
    old projection drops to ``None`` and spreads across effects (Natural
    Emergence). Scope-gated to YOUR lands (``_signals_ir`` passes ``("you",)``), so
    a symmetric all-lands animate (Living Plane) does not open a your-lands build.
    """
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    if statics[0].scope != "you":  # the affected-filter controller (you-gate)
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
    * **not a self-discount** — the ``affected`` filter must NOT be ``SelfRef`` ("this
      spell costs {X} less" — Cavern-Hoard Dragon carries no static here anyway, and
      the few that model it as a static ``SelfRef``-affected reducer — A-Demilich —
      are the self-discount the live ``_COST_SELF_DISCOUNT`` raw screen drops).

    A flat ramp rock (no ``ModifyCost``) never reaches the gate. The activated
    "next spell you cast costs less" synth form (``reducenextspellcost`` — no native
    static node) is a documented ``live_only`` tail. Scope "you".
    """
    for unit in tree.units:
        if modify_cost_mode(unit.node) != "Reduce":
            continue
        if tag_of(getattr(unit.node, "affected", None)) == "SelfRef":
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
# SearchLibrary target_player tags directing the search at ANOTHER player —
# a punisher's compensation fetch (Settle the Wreckage), never YOUR cheat.
_DIRECTED_SEARCHERS: frozenset[str] = frozenset(
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
            if not cores or cores <= {"Land"}:
                continue  # land carve-out / no type evidence — never guess
            if _directed_search_sibling(unit):
                continue  # another player's compensation fetch, not yours
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


def _directed_search_sibling(unit: AbilityUnit) -> bool:
    """Whether a sibling ``SearchLibrary`` directs ANOTHER player to search
    (``target_player`` a directed-PLAYER tag — Settle the Wreckage's
    ``ParentTargetController`` "that player may search"). A ``Typed`` library
    OWNER (Bribery — YOU search target opponent's library) is not directed:
    the controller performs the search and the put stays yours."""
    for c in unit.effects:
        if c.concept != "tutor":
            continue
        if tag_of(getattr(c.node, "target_player", None)) in _DIRECTED_SEARCHERS:
            return True
    return False


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

    # Whole-card reconciliation (granularity c): cross-open spellcast_matters LOW
    # from a spell-copier that has no native spellcast signal in this batch.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        add(Signal("spellcast_matters", "you", "", "", tree.name, "low"))

    return out
