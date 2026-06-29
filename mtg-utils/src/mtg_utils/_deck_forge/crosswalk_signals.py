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
    ConceptTree,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    count_operand_filter,
    counter_kind,
    counter_pred_kinds,
    effect_filter,
    effect_reaches_player,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    tag_of,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
)
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
    }
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
        # the resolving ability's actor is NOT an opponent (the player_scope guard
        # below catches the "each opponent sacrifices" edicts phase mislabels as a
        # you-controlled sacrificed subject — Grave Pact, Dictate of Erebos).
        if _edict_actor(unit):
            continue
        for c in unit.effects:
            if c.concept == "sacrifice" and _is_you_sac_subject(c, cost=False):
                return [
                    Signal("sacrifice_outlets", "you", "", c.raw, tree.name, "high")
                ]
    return []


# player_scope actor tags that are NOT the ability's controller (an edict makes
# someone ELSE sacrifice; the controller never does). CR 701.21a / 800.4a.
_EDICT_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "All", "EachPlayer", "Each"}
)


def _edict_actor(unit: object) -> bool:
    """Whether the ability whose effect resolves names a NON-controller actor.

    Phase tags "each opponent / each other player sacrifices" edicts with a
    ``player_scope`` of ``Opponent`` / ``All`` on the resolving ability (a trigger's
    ``execute``, or the activated/replacement ability itself), while MISLABELING the
    sacrificed creature's filter ``controller: You`` — but per CR 701.21a a player
    can only sacrifice a permanent THEY control, so an "each opponent sacrifices"
    effect is an EDICT, not a self-sac outlet. Reading the actor here rejects the
    edict (Grave Pact, Dictate of Erebos, Butcher of Malakir, Dusk Mangler) while a
    genuine self-sac (Mycoloth's Devour — no opponents ``player_scope``) still fires.
    """
    node = getattr(unit, "node", None)
    for holder in (node, getattr(node, "execute", None)):
        if tag_of(getattr(holder, "player_scope", None)) in _EDICT_ACTORS:
            return True
    return False


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
    # you-controlled subject; ``_edict_actor`` rejects it (CR 701.21a). The sac subject
    # must be genuinely you-controlled; the Permanent-symmetric-list gate (CR 702.166a)
    # drops the Bargain alt-cost.
    for unit in tree.units:
        if _edict_actor(unit):
            continue
        for c in unit.effects:
            if c.concept != "sacrifice" or c.scope == "opponents":
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


def _gain_control(tree: ConceptTree) -> list[Signal]:
    """gain_control — THEFT (you take control of a permanent you don't own, CR 110.2 /
    720). Mirrors ``_signals_ir`` line ~9270: a ``GainControl`` / ``GainControlAll``
    effect (Threaten, Control Magic's reset-free theft), EXCLUDING a control-RESET
    (an ``Owned`` predicate on the target — "each player gains control of permanents
    they own", Brooding Saurian, CR 110.2a). A donate (``GiveControl`` — you give
    your OWN away) is a SEPARATE phase tag, never reaching this arm. A ``Control
    Magic`` enchant rides a ``ChangeController`` STATIC modification. Scope "you".
    """
    for c in tree.effect_concepts("gain_control"):
        sub = effect_filter(c.node)
        if sub is not None and "Owned" in filter_predicates(sub):
            continue  # control-RESET, not theft
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


def _mill_makers(tree: ConceptTree) -> list[Signal]:
    """mill_makers — a mill DOER (CR 701.17a). A ``Mill`` effect (Stitcher's Supplier
    self-mill, Maddening Cacophony opponent-mill). The live lane fires the keyword
    array scoped "any"; the structural ``Mill`` effect is broader (catches the
    keyword-less millers). Scope mirrors the live preset's "any".

    Gated to ``destination == "Graveyard"`` (CR 701.17a — mill puts cards into a
    graveyard): drops Scroll Rack (phase mislabels its library↔hand swap ``Mill`` with
    a Hand destination). Two phase reanimation/recycle mislabels (Bone Dancer, Soldevi
    Digger) keep a Graveyard destination and stay ``crosswalk_only``.
    """
    for c in tree.effect_concepts("mill"):
        if getattr(c.node, "destination", None) == "Graveyard":
            return [Signal("mill_makers", "any", "", c.raw, tree.name, "high")]
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
    _mill_makers,
    _proliferate_makers,
    _energy_makers,
    _voltron_makers,
    _voltron_matters,
)


def extract_crosswalk_signals(
    tree: ConceptTree, *, keys: frozenset[str] = PORTED_KEYS
) -> list[Signal]:
    """Run the ported crosswalk lanes over one concept tree; dedupe by ident.

    Returns the ``Signal`` list for the ported batch, sliced to ``keys``, with the
    whole-card ``spell_copy_makers`` → ``spellcast_matters`` reconciliation applied
    (granularity c — mirrors ``signals.py`` lines 185-188: a spell-copier wants a
    dense instant/sorcery base, so a ``spellcast_matters`` LOW is cross-opened when
    absent).
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

    # Whole-card reconciliation (granularity c): cross-open spellcast_matters LOW
    # from a spell-copier that has no native spellcast signal in this batch.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        add(Signal("spellcast_matters", "you", "", "", tree.name, "low"))

    return out
