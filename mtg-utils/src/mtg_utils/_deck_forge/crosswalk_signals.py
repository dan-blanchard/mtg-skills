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
    ConceptTree,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    counter_kind,
    effect_reaches_player,
    explicit_recipient_scope,
    filter_predicates,
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
    }
)

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
        if not trigger_subject(unit.node):  # bare SelfRef self-death
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
        # An EFFECT-role sac is an edict UNLESS its subject is explicitly you.
        for c in unit.effects:
            if c.concept == "sacrifice" and _is_you_sac_subject(c, cost=False):
                return [
                    Signal("sacrifice_outlets", "you", "", c.raw, tree.name, "high")
                ]
    return []


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
