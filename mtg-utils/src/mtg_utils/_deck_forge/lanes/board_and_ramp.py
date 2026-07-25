"""Crosswalk signal lanes — sacrifice outlets, blink, ramp / big mana, and the
board-presence "matters" families (artifacts/enchantments, creatures, type
go-wide, spellcast) (split from crosswalk_signals.py)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from mtg_utils._card_ir.crosswalk import (
    ARTIFACT_TOKEN_SUBTYPES,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    _is_static_def,
    change_zone_dirs,
    count_distinct_operand_filter,
    count_operand_filter,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_predicates,
    filter_subtypes,
    iter_condition_sites,
    iter_cost_leaves,
    iter_nested_granted_effect_concepts,
    iter_static_defs,
    iter_typed_nodes,
    ref_count_filter,
    static_mode_tag,
    tag_of,
    trigger_caster_scope,
    trigger_subject_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _BECOMES_TYPE_RE,
    _TOKEN_SUBTYPE_OWN_REF,
)
from mtg_utils._card_ir.tree_synthesis import (
    SynthesizedNode,
    _iter_untap_targets,
    attack_raid_condition,
    has_attack_trigger,
    has_gain_life_amplifier,
    has_high_life_total_payoff,
    has_life_gained_this_turn,
    has_life_gained_trigger,
    has_selfloss_engine,
    has_structural_spellcast,
    has_structural_tutor,
    has_trigger_draw_bleed,
    structural_land_fetch_split,
    structural_token_maker_type_subjects,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _FIXING_PRODUCED_TYPES,
    _LAND_SUBTYPE_WORDS,
    _LAND_SUBTYPES,
    _TYPE_MATTERS_LANE,
    _condition_leaves,
    _is_generic_creature_filter,
    _kept,
    _sac_is_edict,
)
from mtg_utils._deck_forge.lanes.mana_and_wipes import _anthem_static
from mtg_utils._deck_forge.signal_base import (
    Signal,
    _clauses,
    _resolve_subject,
)
from mtg_utils._deck_forge.text_reads import (
    _ARTIFACTS_MATTER_MIRROR,
    _ENCHANTMENTS_MATTER_MIRROR,
    _TOKEN_SUBJECT_WORDS,
)


def _sac_subject_present(tgt: object) -> bool:
    """Whether a sacrifice target filter names a present, non-land(-subtype)
    subject — shared by the cost-leaf arm and the effect arm (ADR-0038 W5
    tails).

    Reads BOTH the bare core type (``Land``) and the CR 205.3i subtype
    vocabulary (:data:`_LAND_SUBTYPES`) — Alpine Guide / Landslide / The
    First Eruption's "sacrifice a Mountain" stays ``land_sacrifice_makers``
    territory. A ``Token`` PREDICATE-only subject ("sacrifice a token" —
    Hardened Tactician, Rat King, Pale Piper; CR 111.1 tokens are
    permanents) is ALSO a present subject even though it carries no core
    type or subtype word — :func:`filter_core_types` /
    :func:`filter_subtypes` only read ``type_filters``, never the
    ``properties`` predicate list, so a bare ``{Token}`` filter previously
    fell through the ``not core and not sub`` empty-subject gate.
    """
    core = filter_core_types(tgt)
    sub = filter_subtypes(tgt)
    if not core and not sub:
        return "Token" in filter_predicates(tgt)
    non_land_core = [w for w in core if w != "Land"]
    non_land_sub = [w for w in sub if w.lower() not in _LAND_SUBTYPES]
    return bool(non_land_core or non_land_sub)


def _sac_leaf_is_you_outlet(leaf: TypedMirrorNode) -> bool:
    """Whether a cost-position ``Sacrifice`` LEAF (:func:`iter_cost_leaves`) is a
    you-sac outlet: a present, non-land(-subtype) subject
    (:func:`_sac_subject_present`).

    A COST is ALWAYS paid by the activator (CR 602.1a — "activation cost must
    be paid by the player who is activating it"), so no controller/edict read
    applies here, unlike the EFFECT arm below.
    """
    return _sac_subject_present(getattr(leaf, "target", None))


# ADR-0038 W4 giants: "As an additional cost to cast this spell, sacrifice
# <subject>." (CR 601.2f) is phase's cleanest structural gap in this key —
# probed byte-for-byte on Bone Splinters / Abjure: the Spell ability's own
# ``cost`` field is ``None``, no Sacrifice node exists ANYWHERE in the typed
# tree for the additional cost (the mana cost lives outside ``abilities``
# entirely). A last-resort ``tree.oracle`` idiom over the templated Oracle
# boilerplate (last-resort tier — :func:`_sacrifice_outlets`'s docstring
# tracked this exact gap as documented residue before this session). The
# clause is isolated to the SAME sentence (``[^.]*?`` never crosses a
# period) so a LATER sentence's unrelated "sacrifice" (Feed the Cycle's
# forage reminder, a different paragraph) never bleeds in; the land-only
# exclusion mirrors the leaf/effect arms above (Tectonic Split's "sacrifice
# half the lands you control" stays out).
_CAST_ADD_SAC_RX = re.compile(
    r"as an additional cost to cast this spell,[^.]*?\bsacrifice\s+([^.]*)\.",
    re.IGNORECASE,
)
# The captured subject clause is land-only when EVERY word in it is a
# quantifier / article / "land(s)" / "you control" / "rounded up" filler word
# — a token-set test (not a phrase regex) so "sacrifice a land." / "sacrifice
# five lands." / "sacrifice X lands." / "sacrifice half the lands you
# control, rounded up." (Crop Rotation, Harrow, Gaea's Balance, Devastating
# Summons, Tectonic Split) all match while "a creature or land" (mixed —
# Merciless Resolve) and anything naming a non-land type keeps a real word
# outside this set and stays IN (fires).
_CAST_ADD_SAC_LAND_ONLY_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "half",
        "all",
        "x",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "rounded",
        "up",
        "down",
        "you",
        "control",
        "land",
        "lands",
    }
)


def _cast_add_sac_clause_is_land_only(clause: str) -> bool:
    words = re.findall(r"[a-zA-Z]+", clause.lower())
    return bool(words) and all(w in _CAST_ADD_SAC_LAND_ONLY_WORDS for w in words)


def _sacrifice_outlets(tree: ConceptTree) -> list[Signal]:
    """A sac outlet / sac payoff (Ashnod's Altar, Mortician Beetle — CR 701.21).

    Mirrors the deleted ``_signals_ir``'s triggers ~10472/10483 + effect outlet ~9226.
    Five
    inputs: (a) a ``sacrificed`` trigger (you sacrifice → reward); (b) an
    ``exploited`` trigger (CR 702.110); (c) a YOU-sac outlet — an activation COST
    (the cost IS the outlet, paid by the controller — Viscera Seer, Ashnod's Altar,
    Spawning Pit), including a Sacrifice leaf folded into a Composite/OneOf
    activation cost (:func:`_sac_leaf_is_you_outlet`, ADR-0038 W4 giants —
    Siege-Gang Commander's "{1}{R}, Sacrifice a Goblin:"; the DOMINANT gap
    this key carried — phase decorates a Composite cost as ONE opaque
    concept, never surfacing the nested Sacrifice leaf the top-level
    ``unit.costs`` walk reads). A trigger's ``unless_pay`` alternative
    (Cosmic Larva's land-only "sacrifice X unless you sacrifice a land" —
    ``land_sacrifice_makers`` territory) is DELIBERATELY NOT read here: the
    SAME node shape also carries "deals damage unless THAT PLAYER
    sacrifices" (Tomb Blade, Demanding Dragon) — the alt-cost payer there is
    the effect's TARGET, not this ability's controller, and CR 602.1a's
    "paid by the activator" default does not extend to an ``unless``
    escape-hatch on a non-activated ability; probed +17 crosswalk_only
    over-fires when tried, reverted this session. (d) a
    ``Sacrifice`` EFFECT whose sacrificed subject is explicitly YOU-controlled
    (Greven, Cabal Therapist — :func:`_is_you_sac_subject`'s controller read
    now recurses ``Or``/``And`` filters via :func:`filter_controller` rather
    than a bare-``Typed``-only ``getattr``, ADR-0038 W4 giants bugfix —
    Boilerbilges Ripper's "another creature or enchantment"); (e)
    the "additional cost to cast" text idiom (:data:`_CAST_ADD_SAC_RX`) and
    the Casualty / Bargain keyword rows (CR 702.153a / 702.166a — see
    :data:`_SWEEP_KEYWORD_LANES`), the two shapes phase's typed tree carries
    NO node for at all (probed: Bone Splinters' Spell ability's ``cost`` is
    ``None``).

    ADR-0038 W5 tails: the cost-leaf and effect-subject arms now share ONE
    subject-presence read, :func:`_sac_subject_present`, fixing two gaps.
    (1) A land-SUBTYPE-only sacrifice ("sacrifice a Swamp" — Akuta, Born of
    Ash) previously slipped past the EFFECT arm's exclusion, which only
    tested the bare core type tuple ``("Land",)`` — the cost-leaf arm
    already read :data:`_LAND_SUBTYPES`, the effect arm did not; both now
    share the one land check. (2) A ``Token`` PREDICATE-only subject
    ("sacrifice a token" — Hardened Tactician, Rat King Pale Piper,
    Fountainport, Chitterspitter, Glimmer Bairn, Combine Chrysalis, Izoni)
    carries no core type or subtype word (:func:`filter_core_types` /
    :func:`filter_subtypes` only read ``type_filters``; ``Token`` lives in
    the filter's ``properties`` list), so it previously fell through the
    ``not core and not sub`` empty-subject gate on BOTH arms — a real
    outlet either way a token comes from a permanent you control (CR
    111.1, CR 701.21a).

    An effect that makes ANOTHER player sacrifice (``TargetPlayer`` — Diabolic
    Edict; ``null``/each — Barter in Blood, Fleshbag Marauder; ``ScopedPlayer``
    — Sheoldred; a wrapper ``player_scope`` naming Opponent/All/Each — Grave
    Pact, Dictate of Erebos, Baleful Beholder's modal mode arm, and the wider
    modal-charm family: Sheoldred's Edict, Kaya's Guile, Riveteers Charm,
    Umbral Juke — CR 701.21a) is an edict → ``edict_makers``, excluded (a
    legacy-IR over-fire class this session adjudicated as a SHED: the old
    flat-parsed IR mis-scopes several of these modal "each opponent
    sacrifices" arms to "any", firing sacrifice_outlets where the structural
    wrapper/controller read here correctly does not). A bare-self ("sacrifice
    this/it") or Land-only sac (:data:`_LAND_SUBTYPES`) is excluded too; the
    bare-self / subject-dropped raw fallback stays a documented residue (see
    the recall-completion b1 note below).

    ADR-0038 W6 endgame — the unset-controller class (Lord of the Pit,
    Disciple of Bolas, Desecration Elemental: the DOMINANT residual class
    this wave, ~80 cards). A sac EFFECT whose target carries NO ``controller``
    tag at all (neither ``You`` nor an edict actor) now DEFAULTS to you
    (CR 109.5 — "you"/"your" on an object means its controller; Magic's
    templating omits an explicit "you" subject on a bare imperative
    addressed to the ability's own controller) UNLESS the owning unit's own
    templated text heads the sacrifice clause with a non-controller actor
    (:func:`_sac_effect_names_other_actor` — "defending player sacrifices",
    "each opponent sacrifices", "any player may sacrifice" — Witch-king
    Bringer of Ruin, Nefarox, Labyrinth Raptor, Prowling Pangolin, Brain
    Gorgers). A prior probe defaulted blindly and reverted after a +10
    over-fire on exactly those third-party shapes (phase leaves their
    ``controller`` EQUALLY unset); the clause-head disambiguator is what
    makes the default safe — see :func:`_sac_effect_names_other_actor`'s own
    docstring for the compound-predicate corpus misses (Nicol Bolas
    Planeswalker, Undercity Plague) a naive proximity window hit first. Two
    shapes remain OUT even with the default: Last Voyage of the _____'s
    "sacrifice enchanted creature" (an ``EnchantedBy`` target, a forced
    Aura-death consequence, not a discretionary outlet — MANDATORY SHED,
    recorded session adjudication) carries a present, non-land, non-Token
    subject (``type_filters=['Creature']`` alongside the ``EnchantedBy``
    predicate — :func:`_sac_subject_present` returns ``True``) and an
    unset controller with NO other-actor phrase in its text either, so a
    blind unset-to-you default DOES fire on it — :func:`_is_you_sac_subject`
    carries an explicit ``EnchantedBy``-predicate guard alongside the
    other-actor check, catching a TRACKED REFERENCE to a specific object as
    a fundamentally different shape from a freely-chosen "a creature"; "any
    player may sacrifice" (Prowling Pangolin, Brain Gorgers) is caught by
    the clause-head test (neither you nor an opponent specifically — a true
    coin-flip actor, correctly excluded).

    ADR-0038 W6 endgame — a GRANTED activated-ability outlet
    (:func:`_sac_outlet_granted_cost` — Lunarch Mantle, Fallen Ideal, Street
    Urchin, Clan Crafter, Animal Boneyard, Consecrated by Blood: an Aura /
    Equipment / static ``GrantAbility`` whose granted ability's OWN
    activation cost is a non-land, non-Ward Sacrifice leaf). A ``GrantTrigger``-
    conferred sac (a curse-shaped TRIGGERED grant — "Enchanted creature has
    'At the beginning of your upkeep, sacrifice a creature.'" — Wayward
    Angel, Cultist of the Absolute, Inevitable End) is a DIFFERENT wrapper
    tag and stays OUT, deliberately: that shape is overwhelmingly an
    opponent-facing curse, not a self-outlet. Scope "you".

    ADR-0039 W7 — PROMOTED, three closers on top of the W6 base. (1) The
    ``ParentTargetController`` you-outlet split (:func:`_sac_ptc_you_eligible`
    — "for each creature, its controller sacrifices" fires "you" when the
    referenced parent is an UNRESTRICTED trigger subject (Tainted Aether,
    Phyrexian Obliterator, Fade Away, Maarika, Funeral March, Vengeful
    Strangler // Strangling Grasp) and stays excluded when the same unit
    anchors the parent to an explicit non-you actor (Liliana of the Veil's
    -6, Michiko Konda). (2) Three real structural reads: Exploit/Devour join
    Casualty/Bargain's keyword-array lane (:data:`_SWEEP_KEYWORD_LANES`,
    Silumgar Scavenger / Thromok the Insatiable) and a created-token Devour
    read (:func:`_has_created_token_devour`, Dragon Broodmother's typed
    ``MirrorVariant(key='Devour')``). (3) Two remaining ledgered bridges
    (``bridge_ledger.py``) close the residual NO-typed-Sacrifice-node-
    anywhere bucket: ``sac_casualty_granted_onto_other_spell`` covers the
    Anhelo/Silverquill GRANT shape; ``sac_emblem_activated_cost`` covers Ob
    Nixilis of the Black Oath's emblem — an opaque-description residue,
    gap-gated so a future phase bump or grammar verb retires the row
    automatically.

    ADR-0039 task #82 grammar sprint — three more graduated OFF the ledger.
    A CR 118.9 alternative-cost pitch ("you may sacrifice ... rather than
    pay this spell's mana cost" — Salvage Titan), a keyworded alternative
    cost whose own cost is a Sacrifice leaf ("Flashback—Sacrifice three
    creatures" — Dread Return; CR 702.34a/702.37a), and Devour's
    un-keyworded written-out ETB sibling (Dracoplasm; CR 614.12/701.21a)
    now synthesize a typed ``synth_sac_outlet_dropped_cost`` marker node
    (``tree_synthesis``'s ``sac_alt_cost_pitch`` / ``sac_keyword_cost`` /
    ``sac_etb_self_sac_unimplemented`` arms — the regex runs ONCE at
    synthesis, gated on the SAME no-typed-Sacrifice-node absence proof the
    ledgered bridges shared), and the lane reads it structurally below —
    no ``bridge_ledger`` involvement, no per-idiom lane special-casing.
    Devour ON THE CARD'S OWN BODY (as opposed to a created token's) simply
    joins the Scryfall-keyword sweep alongside Casualty/Bargain/Exploit,
    since the keyword itself is the structured source (Thromok the
    Insatiable — formerly the ``sac_devour_unimplemented`` bridge).
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
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice" and _sac_leaf_is_you_outlet(leaf):
                return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
        # An EFFECT-role sac is an edict UNLESS its subject is explicitly you AND
        # the sac's OWN ability wrapper does not name a non-controller actor (the
        # per-effect player_scope guard catches the "each opponent sacrifices" edicts
        # phase mislabels as a you-controlled sacrificed subject — Grave Pact, Dictate
        # of Erebos, Baleful Beholder's modal mode arm).
        for c in unit.effects:
            if (
                c.concept == "sacrifice"
                and _is_you_sac_subject(c, cost=False, unit=unit)
                and not _sac_is_edict(unit, c.node)
            ):
                return [
                    Signal("sacrifice_outlets", "you", "", c.raw, tree.name, "high")
                ]
    m = _CAST_ADD_SAC_RX.search(_kept(tree))
    if m and not _cast_add_sac_clause_is_land_only(m.group(1)):
        return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    if _sac_outlet_granted_cost(tree):
        return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    if _has_created_token_devour(tree):
        return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    # ADR-0039 task #82 grammar sprint — the CR 118.9 alt-cost pitch / CR
    # 702.34/702.37 keyword alt-cost / Devour's un-keyworded ETB sibling
    # dropped-cost idioms now synthesize a typed marker node
    # (``tree_synthesis``'s ``sac_alt_cost_pitch`` / ``sac_keyword_cost`` /
    # ``sac_etb_self_sac_unimplemented`` arms) the lane reads structurally —
    # graduated OFF the ledgered-bridge mechanism (formerly three
    # bridge_ledger rows; see the module's own git history for the retired
    # text). Devour ON THE CARD'S OWN BODY (Thromok the Insatiable) is a
    # separate graduation: it joins the Casualty/Bargain/Exploit Scryfall-
    # keyword sweep (:data:`_SWEEP_KEYWORD_LANES`) instead, since the
    # keyword itself IS the structured source, same as those three.
    for c in tree.iter_concepts():
        if c.concept == "synth_sac_outlet_dropped_cost":
            return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    # ADR-0039 W7 ledgered bridges — the NO-typed-Sacrifice-node residual
    # bucket (dropped clauses / grammar stragglers; bridge_ledger.py rows,
    # docstring there for the full corpus accounting):
    for bridge_id in (
        "sac_casualty_granted_onto_other_spell",
        "sac_emblem_activated_cost",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("sacrifice_outlets", "you", "", "", tree.name, "high")]
    # recall-completion b1: the subject-dropped / modal you-sac raw fallback
    # (_SAC_OUTLET_RAW) is DELIBERATELY NOT ported. The IR gates it PER-EFFECT
    # (``cat in (sacrifice, choose)`` AND the SAME effect's ``e.raw`` matches), but
    # the crosswalk substrate carries NO per-effect raw (``c.raw`` is empty for a
    # subject-dropped sacrifice). A card-level gate (has a sacrifice/choose concept)
    # + an oracle-clause match over-fires (+11 crosswalk_only: Braids, Serendib Djinn,
    # Phyrexian War Beast — "sacrifice unless" downsides and upkeep saccers), so it
    # stays a documented ``live_only`` residue (ADR-0035 convergence tail). CR
    # 701.16 / 701.21. The ``ParentTargetController`` symmetric-sac class and the
    # Casualty-GRANT shape are CLOSED (ADR-0039 W7 — :func:`_sac_ptc_you_eligible`
    # and the ``sac_casualty_granted_onto_other_spell`` bridge, this docstring's own
    # W7 paragraph). Still-deferred: a ``GrantTrigger``-conferred sac (a TRIGGERED,
    # not activated, granted ability — "Enchanted creature has 'At the beginning of
    # your upkeep, sacrifice a creature.'" — Wayward Angel, Cultist of the Absolute,
    # Inevitable End: this shape is overwhelmingly a CURSE Aura meant for an
    # OPPONENT's creature, not a self-outlet, so :func:`_sac_outlet_granted_cost`
    # deliberately scopes to ``GrantAbility`` — an ACTIVATED grant — only) and a
    # phase parse gap where a cost quantifier shape ("up to three permanents", "one
    # or more artifacts" — Baba Lysaga, Radiant Lotus) decorates a wholly EMPTY
    # target filter (no type info recoverable structurally) — see the ADR-0038 W4
    # giants / W5 tails session reports.
    return []


def _sac_outlet_granted_cost(tree: ConceptTree) -> bool:
    """Whether TREE grants (via ``GrantAbility``) an ACTIVATED ability whose
    OWN activation cost carries a non-land, non-Ward Sacrifice leaf (ADR-0038
    W6 endgame — Lunarch Mantle "Sacrifice a permanent: gains flying",
    Fallen Ideal, Street Urchin, Clan Crafter, Animal Boneyard, Consecrated
    by Blood).

    A COST is always paid by the ability's ACTIVATOR (CR 602.1a) — for a
    GRANTED activated ability that's whoever controls the permanent it's
    granted to. Deck-signal purposes treat that as "you": a beneficial
    Aura/Equipment/static granting a NEW activated outlet is overwhelmingly
    attached to your OWN permanent (unlike a curse-shaped TRIGGERED grant —
    see the caller's docstring), so the same CR 109.5 "you" convention
    applies in practice. :func:`iter_typed_nodes` reaches the granted
    ability's ``.definition.cost`` even though it sits behind a field
    outside the fixed unit/effect walk (the same generic-descent precedent
    ``opponent_discard``'s Mindlash Sliver read and the discard/draw
    GrantAbility arms use elsewhere in this module).

    A ``Ward`` cost (Mishra, Tamer of Mak Fawa's "Ward—Sacrifice a
    permanent") is EXCLUDED by class name, not tag — phase's ``tag_of``
    collapses ``T_Ward__Sacrifice`` to the SAME ``"Sacrifice"`` string as a
    regular cost leaf, but a Ward cost is paid by the OPPONENT who targeted
    the warded permanent (CR 702.21a: "counter that spell or ability unless
    THAT PLAYER pays [cost]"), never the ability's own controller.
    """
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            defn = getattr(n, "definition", None)
            cost = getattr(defn, "cost", None)
            for leaf in iter_cost_leaves(cost):
                if (
                    tag_of(leaf) == "Sacrifice"
                    and not type(leaf).__name__.startswith("T_Ward__")
                    and _sac_leaf_is_you_outlet(leaf)
                ):
                    return True
    return False


def _has_created_token_devour(tree: ConceptTree) -> bool:
    """Whether TREE creates a token whose OWN keyword array carries Devour
    (CR 702.82a — "As this creature enters, you may sacrifice any number
    of creatures") — Dragon Broodmother's "create a 1/1 ... Dragon
    creature token with flying and devour 2" (ADR-0039 W7).

    Devour is a sac COST paid by the token's own controller as it enters
    — for a token YOU create, that's "you" (the same CR 109.5/602.1a
    convention :func:`_sac_outlet_granted_cost` applies to a granted
    activated cost). Phase decorates the created token's Devour as a
    typed ``MirrorVariant(key='Devour', inner=<N>)`` entry on the
    ``Token`` effect's own ``keywords`` list — reachable directly (no
    text-idiom needed) once the walk descends into that specific list;
    :func:`iter_typed_nodes` does NOT surface it on its own (a
    ``MirrorVariant`` unwraps to its ``inner`` scalar on the generic
    walk, never yielding the variant node itself), so this reads the
    ``Token`` node's ``keywords`` field directly. Corpus-verified: the
    ONLY commander-legal created-token Devour instance is Dragon
    Broodmother (phase v0.20.0, 2026-07-11); Thromok the Insatiable's
    Devour is on its OWN body, parked as an ``Unimplemented`` residue
    instead, and its OWN printed Scryfall keyword array carries "Devour"
    regardless — the ``devour`` row in :data:`_SWEEP_KEYWORD_LANES` covers
    it (ADR-0039 task #82, formerly the ``sac_devour_unimplemented``
    ledgered bridge).
    """
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Token":
                continue
            for kw in getattr(n, "keywords", None) or []:
                if isinstance(kw, MirrorVariant) and kw.key == "Devour":
                    return True
    return False


# ADR-0038 W6 endgame: a Sacrifice EFFECT whose target filter carries NO
# ``controller`` tag at all (``None`` — Lord of the Pit, Disciple of Bolas,
# Desecration Elemental, the dominant live_only class this wave) is
# genuinely ambiguous in phase's own structure — CR 109.5 defines "you" as
# an object's controller and Magic's templating omits an explicit "you"
# subject on a bare imperative addressed to the ability's own controller
# ("sacrifice a creature", no actor named — self, CR 109.5) while ALWAYS
# spelling out a THIRD-PARTY subject at the head of its own clause when
# someone else is meant ("defending player sacrifices", "each opponent
# sacrifices", "any player may sacrifice" — Witch-king Bringer of Ruin,
# Nefarox, Labyrinth Raptor, Prowling Pangolin, Brain Gorgers). Phase
# leaves the target ``controller`` EQUALLY unset for both shapes (probed:
# Labyrinth Raptor's "defending player sacrifices" carries the identical
# ``controller=None`` as Lord of the Pit's bare "sacrifice a creature"), so
# a blind unset-to-you default over-fires on the third-party shapes (a
# prior W5 probe hit exactly this and reverted). :func:`_sac_effect_names_
# other_actor` reads the owning unit's ``description`` (verified populated
# with the FULL multi-clause ability text on the outer trigger/activated
# node, even when the Sacrifice sits on a nested ``sub_ability`` — Lord of
# the Pit, Disciple of Bolas), isolates the SENTENCE naming "sacrific-",
# strips a leading dependent/trigger clause ("Whenever ~ attacks," / "When
# ~ enters,") and an activated-ability cost prefix ("{4}, {T}, Sacrifice
# ~:"), and checks whether the REMAINING main clause's own SUBJECT (its
# leading words) is a non-controller actor. A clause-HEAD test (not a bare
# proximity window) is required because Magic's compound predicates share
# one subject across several comma-joined verbs — "Target player loses 1
# life, discards a card, then sacrifices a permanent" and "That player or
# that planeswalker's controller discards seven cards, then sacrifices
# seven permanents" (Undercity Plague, Nicol Bolas Planeswalker) both put
# real distance between the actor and "sacrifices"; a first-attempt
# proximity-window probe missed both and over-fired. The clause-head test
# also correctly REJECTS a later, unrelated clause naming an opponent
# (Lord of Tresserhorn's "you sacrifice two creatures, and target opponent
# draws two cards" — "target opponent" heads its OWN clause after "and",
# not the sacrifice clause). Corpus-verified against the full
# unset-controller class: 79/81 default to you, exactly the 2 "any player
# may sacrifice" cards (Prowling Pangolin, Brain Gorgers — neither you nor
# an opponent specifically, a true coin-flip actor) exclude.
_SAC_DEPENDENT_CLAUSE_RX = re.compile(
    r"^(when|whenever|at the beginning of|if|as|before|during)\b",
    re.IGNORECASE,
)
_SAC_OTHER_ACTOR_HEAD_RX = re.compile(
    r"^\s*(defending player|that player|target player|target opponent|"
    r"each opponent|another player|its controller|their controller|"
    r"a player other than you|any player|each player|an opponent|"
    r"that planeswalker.s controller)\b",
    re.IGNORECASE,
)


def _sac_effect_names_other_actor(unit: AbilityUnit) -> bool:
    """Whether UNIT's own templated ability text HEADS the sacrifice clause
    with a non-controller actor (:data:`_SAC_OTHER_ACTOR_HEAD_RX`, after
    stripping a leading dependent clause / activated-ability cost prefix) —
    the CR 109.5 "you" default does NOT apply (ADR-0038 W6 endgame).
    """
    desc = getattr(getattr(unit, "node", None), "description", "") or ""
    for sentence in re.split(r"(?<=[.!?])\s+", desc):
        if "sacrific" not in sentence.lower():
            continue
        clause = sentence
        while _SAC_DEPENDENT_CLAUSE_RX.match(clause) and "," in clause:
            clause = clause.split(",", 1)[1]
        if ":" in clause and not _SAC_DEPENDENT_CLAUSE_RX.match(clause.strip()):
            clause = clause.rsplit(":", 1)[-1]
        if _SAC_OTHER_ACTOR_HEAD_RX.match(clause):
            return True
    return False


# ADR-0039 W7: controller tags that anchor a ``ParentTargetController``
# Sacrifice effect's referenced "parent" to an explicit non-you actor
# elsewhere in the SAME unit — a targeted player (To the Slaughter,
# Dispense Justice, Choice of Damnations all carry a sibling/ancestor
# ``controller: TargetPlayer`` node in the SAME ability chain the
# sacrifice descends from) or an opponent-restricted trigger source
# (Michiko Konda's "a source AN OPPONENT controls deals damage to you" —
# ``valid_source: Typed(controller='Opponent')``). CR 701.21a.
_SAC_PTC_OTHER_ACTOR_CONTROLLERS: frozenset[str] = frozenset(
    {"TargetPlayer", "Opponent", "Opponents", "EachOpponent"}
)
# Liliana of the Veil's -6 ("Separate all permanents TARGET PLAYER
# controls into two piles. That player sacrifices...") locks the "target
# player" actor inside an opaque ``Unimplemented`` node's description —
# no structured ``TargetPlayer`` controller tag survives anywhere in the
# unit for the controller-tag scan above to catch. A same-unit
# Unimplemented residue naming a non-you actor is the same tell.
_SAC_PTC_UNIMPL_OTHER_ACTOR_RX = re.compile(
    r"\b(target player|target opponent|each opponent|defending player|"
    r"another player|any player|an opponent)\b",
    re.IGNORECASE,
)


def _sac_ptc_you_eligible(unit: AbilityUnit) -> bool:
    """Whether a ``ParentTargetController``-scoped Sacrifice effect's
    referenced parent is genuinely AMBIGUOUS as to controller (so the CR
    109.5 "you" convention applies) rather than anchored to an explicit
    opponent/targeted-player actor elsewhere in the owning unit (ADR-0039
    W7 — Funeral March, Tainted Aether, Phyrexian Obliterator, Vengeful
    Strangler // Strangling Grasp, Fade Away, Maarika, Brutal Gladiator:
    the "its controller sacrifices" / "that source's controller
    sacrifices" idiom over an UNRESTRICTED trigger subject — "a creature
    enters", "a source deals damage to this creature", "for each
    creature" — carries no other controller tag AND no
    ``Unimplemented``-residue other-actor phrase anywhere in the unit).

    Corpus-verified against every commander-legal ``ParentTargetController``
    Sacrifice-effect hit (16 cards, phase v0.20.0, 2026-07-11): this rule
    reproduces the exact 6-card you-outlet / 10-card edict-or-land split by
    hand adjudication (5 of the 10 are land-only and excluded upstream by
    the land check regardless; Liliana of the Veil's -6 needs the
    Unimplemented-residue arm specifically — its own controller-tag scan
    alone false-fired, +1 crosswalk_only caught and fixed this session).
    """
    for n in iter_typed_nodes(unit.node):
        ctrl = getattr(n, "controller", None)
        if isinstance(ctrl, str) and ctrl in _SAC_PTC_OTHER_ACTOR_CONTROLLERS:
            return False
        if tag_of(n) == "Unimplemented" and _SAC_PTC_UNIMPL_OTHER_ACTOR_RX.search(
            getattr(n, "description", "") or ""
        ):
            return False
    return True


def _is_you_sac_subject(
    c: object, *, cost: bool, unit: AbilityUnit | None = None
) -> bool:
    """Whether a ``sacrifice`` concept-node is a YOU-sac outlet (not an edict).

    The sacrificed subject must be present and not land-only (a bare-self / land sac
    is a different lane — :func:`_sac_subject_present`, reading the TARGET filter
    directly rather than the pre-flattened ``c.subject`` tuple). For an EFFECT
    (``cost=False``) the sacrificed filter's ``controller`` must be explicitly
    ``You``, OR unset with no other-actor phrase in the owning ``unit``'s own text
    (:func:`_sac_effect_names_other_actor`, ADR-0038 W6 endgame — CR 109.5) — a
    ``TargetPlayer``/``ScopedPlayer`` controller, an unset controller whose text
    DOES name another actor, or an unset controller on an ``EnchantedBy``-tracked
    subject (Last Voyage of the _____'s "sacrifice enchanted creature" — a forced
    Aura-death consequence per CR 303.4b, not a discretionary outlet; a tracked
    REFERENCE to a specific object is a fundamentally different shape than a
    freely-chosen "a creature", so the ``you`` default does not extend to it,
    MANDATORY SHED) is edict/non-outlet territory. A COST is always paid by the
    controller, so its subject controller is not consulted.

    ADR-0038 W5 tails bugfix: the land exclusion now reads the CR 205.3i subtype
    vocabulary too (:data:`_LAND_SUBTYPES`), not just the bare core type ``Land`` —
    the OLD ``subj == ("Land",)`` check let a land-SUBTYPE-only sacrifice ("sacrifice
    a Swamp" — Akuta, Born of Ash) slip through as a false ``sacrifice_outlets``
    fire (land_sacrifice_makers territory, CR 701.21a); the cost-leaf arm already
    carried this precision (:func:`_sac_leaf_is_you_outlet`), the effect arm did not.

    ADR-0038 W4 giants bugfix: the controller read uses :func:`filter_controller`
    (recurses ``Or``/``And``) rather than a bare ``getattr`` gated to ``tag_of ==
    "Typed"`` — a multi-type target ("another creature OR enchantment" —
    Boilerbilges Ripper) is an ``Or`` filter at the top, so the OLD inline check
    always returned ``False`` even when a sub-arm carried ``controller: You``.

    ADR-0039 W7: a ``ParentTargetController`` controller — the sacrificed
    filter's controller is whoever controls a REFERENCED object, not a
    plain unset gap — now also qualifies when the reference is genuinely
    ambiguous (:func:`_sac_ptc_you_eligible`, CR 701.21a): "for each
    creature, its controller sacrifices" (Tainted Aether, Fade Away),
    "whenever a source deals damage to this creature, that source's
    controller sacrifices" (Phyrexian Obliterator) and the analogous
    enchant/combat-damage idioms are symmetric — they hit YOU whenever
    YOUR OWN creature/source is the one referenced, a genuine (if
    involuntary) self-outlet — while a targeted-player idiom (Liliana of
    the Veil's -6, To the Slaughter, Dispense Justice, Choice of
    Damnations) or an opponent-restricted trigger source (Michiko Konda)
    stays excluded.
    """
    target = getattr(getattr(c, "node", None), "target", None)
    if not _sac_subject_present(target):
        return False
    if cost:
        return True
    ctrl = filter_controller(target)
    if ctrl == "You":
        return True
    if (
        ctrl is None
        and unit is not None
        and "EnchantedBy" not in filter_predicates(target)
    ):
        return not _sac_effect_names_other_actor(unit)
    if ctrl == "ParentTargetController" and unit is not None:
        return _sac_ptc_you_eligible(unit)
    return False


def _lifegain_matters(tree: ConceptTree) -> list[Signal]:
    """A your-lifegain PAYOFF / significant self-life-loss engine (CR 119). Tier-1.

    Six structural arms + the bucket-B synth node, zero oracle text / regex at lane
    time (ADR-0036/0037 fold — the ``_LIFEGAIN_MATTERS_MIRROR`` is deleted). All
    scope "you"; the shared predicates live in ``tree_synthesis`` so the lane and the
    synth gap gate read ONE source (gap-gate-alignment, no drift):

    * a native ``life_gained`` trigger (:func:`has_life_gained_trigger` — Archangel
      of Thune, Ajani's Pridemate).
    * a triggered draw-and-self-bleed engine (:func:`has_trigger_draw_bleed` — the
      Phyrexian Arena / Necropotence idiom, Taborax, Kothophed; ANY trigger event,
      the recall-completion of the mirror's dies/leaves/graveyard-only draw-bleed).
    * a significant recurring self-life-LOSS engine (:func:`has_selfloss_engine` —
      scaling amount / big upkeep bleed, Xathrid Demon).
    * a "life gained this turn" typed operand/gate (:func:`has_life_gained_this_turn`
      — Accomplished Alchemist, Angelic Accord; bucket-A the mirror missed on
      Voracious Wurm).
    * a CR-614 gain-life REPLACEMENT amplifier (:func:`has_gain_life_amplifier` —
      Alhammarret's Archive, Boon Reflection; bucket-A).
    * a HIGH-life-total win-condition / static payoff
      (:func:`has_high_life_total_payoff` — ADR-0036/0037 Stage 5 #60: life as a
      RESOURCE, not just a one-time gain. Felidar Sovereign / Test of Endurance's
      "win the game" upkeep threshold — CR 104.2; the "as long as you have N or
      more life" static pump/keyword-grant family — Divinity of Pride, Serra
      Ascendant, Blood Baron of Vizkopa, Caduceus Staff of Hermes, Glorious
      Enforcer's relative comparison, Path of Bravery's vs-starting-life gate).
    * the ``tree_synthesis`` bucket-B synth node — the description-only / granted
      "whenever you gain (or lose) life" trigger + "gained life this turn" text-only
      gate phase emits no typed node for.

    A pure lifegain SOURCE ("whenever ~ dies, you gain 1 life" — Blood Artist) is
    ``lifegain_makers``, not this lane; a loose lose-life / pay-life clause, a
    LOW-life ("5 or less") near-death payoff, and an opponent-lifegain hoser are
    shed (the mirror's cross-clause over-fires; the LOW-life polarity is a
    different signal, not read here).
    """
    if (
        has_life_gained_trigger(tree)
        or has_trigger_draw_bleed(tree)
        or has_selfloss_engine(tree)
        or has_life_gained_this_turn(tree)
        or has_gain_life_amplifier(tree)
        or has_high_life_total_payoff(tree)
    ):
        return [Signal("lifegain_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_lifegain_matters":
            return [Signal("lifegain_matters", "you", "", "", tree.name, "high")]
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
    Scope "you", confidence HIGH — this lane is the MAKER half only (see
    :func:`blink_flicker_is_maker`).

    A SECOND, unrelated producer shares this key: :func:`apply_membership_floor`
    (called once per card by ``signals.extract_signals`` when its
    ``include_membership`` flag is set — the commander-only deck-aggregate path,
    default True) opens a LOW-confidence "cares about being blinked" cross-open
    off a card's OWN strong ETB value (Academy Journeymage, Mulldrifter — CR
    603.6 "flicker fodder", not a literal exile+return). That is the task #83
    preset-scoping "blink_flicker payoff" noise (prec .06 over the raw corpus
    dump, which ran ``include_membership=True`` uniformly): a 'blink' preset
    VIEW selecting flicker MAKERS only should either query with
    ``include_membership=False`` or use :func:`blink_flicker_is_maker` to
    filter the merged signal list.

    task #86 adds a granted-ability descent
    (:func:`~mtg_utils._card_ir.crosswalk.iter_nested_granted_effect_concepts`)
    to the per-unit ``change_zone`` gather: Deadeye Navigator's soulbond
    static grants each paired creature "{1}{U}: Exile ~, then return it to
    the battlefield under your control." — a ``GrantAbility`` whose
    ``definition.effect`` is ``ChangeZone(Exile, target=SelfRef)`` and whose
    ``definition.sub_ability.effect`` is ``ChangeZone(Battlefield,
    target=TrackedSet, enters_under='You')`` — the EXACT top-level shape
    this lane already recognizes, now reachable inside the grant body too.
    CR 702.95a / 400.7.
    """

    def _battlefield_exile(c: ConceptNode, unit: AbilityUnit) -> bool:
        # A blink exiles a BATTLEFIELD object (CR 400.7 — the return is a
        # new object on the battlefield it left). A graveyard-sourced exile
        # (Boneyard Parley's "exile up to five target creature cards from
        # graveyards", visible in one unit since the task #84
        # ``SeparateIntoPiles`` pile-arm descent) is exile-assisted
        # REANIMATION, not a flicker of your own board — excluded on the
        # exile subject's own graveyard evidence (origin field or the
        # target filter's ``InZone: Graveyard`` predicate).
        if change_zone_dirs(c.node)[0] == "Graveyard":
            return False
        if "Graveyard" in filter_inzone_zones(effect_filter(c.node)):
            return False
        # task #86: a "dies" trigger's own "exile it" (``TriggeringSource``
        # — CR 700.4, the triggering object is ALREADY in the graveyard by
        # the time a dies trigger resolves) is graveyard-sourced too, even
        # though phase carries no explicit origin/InZone tag on a bare
        # ``TriggeringSource`` target — the granted-ability descent
        # surfaces this for the first time (Timothar, Baron of Bats: the
        # dying Vampire is exiled from the graveyard, then a CAUSALLY
        # DISCONNECTED later token combat-damage trigger MAY return it —
        # delayed reanimation, not a blink of a live permanent; the
        # ``dies_recursion`` lane's own :func:`~mtg_utils._card_ir.crosswalk.
        # is_dies_return_trigger` documents the same "dies" = already-in-
        # graveyard fact).
        return not (
            unit.trigger_event == "dies"
            and tag_of(getattr(c.node, "target", None)) == "TriggeringSource"
        )

    for unit in tree.units:
        czs = [c for c in unit.effects if c.concept == "change_zone"]
        czs += [
            c
            for c in iter_nested_granted_effect_concepts(unit.node)
            if c.concept == "change_zone"
        ]
        if not any(
            change_zone_dirs(c.node)[1] == "Exile" and _battlefield_exile(c, unit)
            for c in czs
        ):
            continue
        for c in czs:
            if change_zone_dirs(c.node)[1] != "Battlefield":
                continue
            tgt = tag_of(getattr(c.node, "target", None))
            if tgt in ("ParentTarget", "TrackedSet"):  # the SAME exiled object
                return [Signal("blink_flicker", "you", "", "", tree.name, "high")]
    return []


def blink_flicker_is_maker(signal: Signal) -> bool:
    """True when a ``blink_flicker`` :class:`Signal` is the MAKER half (the
    card performs the exile-and-return ITSELF — Flickerwisp, Ephemerate,
    Soulherder) rather than :func:`apply_membership_floor`'s "own ETB value"
    PAYOFF cross-open (Academy Journeymage, Mulldrifter — "worth blinking",
    never a literal blink). :func:`_blink_flicker` always emits HIGH; the
    floor always emits LOW — a task #83 preset view wanting MAKERS ONLY
    (never the "wants to be blinked" membership tell) filters on this. The
    minimal mechanism: no new tree read, just the existing confidence split
    this pair of producers already carries."""
    return signal.key == "blink_flicker" and signal.confidence == "high"


def blink_flicker_maker_present(card: dict) -> bool:
    """A CARD-level (not tree-level) concept predicate: true when CARD
    carries a MAKER-half ``blink_flicker`` signal (:func:`blink_flicker_is_maker`),
    excluding :func:`apply_membership_floor`'s "worth blinking" payoff
    cross-open. Queries ``extract_signals`` with
    ``include_membership=False`` so the floor producer never runs at all —
    the simpler of the two filtering strategies :func:`_blink_flicker`'s
    own docstring names (the other being a post-hoc filter over the merged
    list, which :func:`blink_flicker_is_maker` alone also supports for a
    caller that already has a merged Signal list). task #83 'blink' preset
    view (``mtg_utils.theme_presets``) — see that preset's own conversion
    note for why ``self_blink`` (a genuinely different self-flicker engine,
    CR 611.2b) unions in as a separate ``signal_keys`` arm instead of
    routing through this predicate too.

    Lazily imports ``mtg_utils._deck_forge.signals`` (not at module scope):
    importing it at THIS module's top level would risk the same import-time
    cycle ``mtg_utils.theme_presets._signal_keys_for`` already documents and
    avoids the same way.
    """
    from mtg_utils._deck_forge.signals import extract_signals

    sigs = extract_signals(card, include_membership=False)
    return any(blink_flicker_is_maker(s) for s in sigs)


def _tokens_matter(tree: ConceptTree) -> list[Signal]:
    """Go-wide token payoff — an anthem or ETB-token trigger (CR 111.1).

    Mirrors the deleted ``_signals_ir``'s anthem ~9831 + etb ~10373. Two arms read the
    ``Token``
    filter PREDICATE: (A) a pump / grant-keyword / set-P/T static whose affected
    filter carries ``Token`` AND controller you (Intangible Virtue) — a symmetric
    controller-any token anthem (Virulent Plague's -2/-2 hoser) is correctly scoped
    out; (B) an enters trigger whose watched subject carries ``Token`` AND
    controller you (Anointer Priest). Scope "you".

    recall-completion b1 (ADR-0034) adds two structural arms the live path only got
    via the ``TOKENS_MATTER_REGEX`` mirror: (C) a ``TokenCreated`` trigger ("whenever
    you create one or more tokens" — Akim); (D) a count-operand carrying the ``Token``
    predicate + controller you ("draw = differently-named creature tokens you
    control" — Audience with Trostani), reading the plain AND distinct count forms.
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
        if unit.trigger_event == "tokencreated":
            return [Signal("tokens_matter", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (
            count_operand_filter(c.node),
            count_distinct_operand_filter(c.node),
        ):
            if (
                filt is not None
                and filter_controller(filt) == "You"
                and "Token" in filter_predicates(filt)
            ):
                return [Signal("tokens_matter", "you", "", c.raw, tree.name, "high")]
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


def _granted_mana_defs(
    tree: ConceptTree,
) -> list[tuple[object, object]]:
    """``(ability_def, recipient_filter)`` for every GRANTED mana-producing
    ability reachable anywhere in the tree — a ``GrantAbility`` (CR 605.1a /
    702) OR ``GrantTrigger`` (a granted TRIGGERED "whenever X, add mana"
    body — Mark of Sakiko's "Whenever ~ deals combat damage to a player, add
    that much {G}") modification inside a static def :func:`iter_static_defs`
    reaches, whose definition/execute node carries a ``Mana`` effect. Covers
    three tree positions with ONE walk (mirrors the b12 nested-mode descent
    precedent): a top-level static's granted keyword-ability text (Joiner
    Adept's "Lands you control have '{T}: Add …'", Rishkar's counter-
    conferred grant), a CREATED TOKEN's own ``static_abilities`` (Awakening
    Zone / every Eldrazi Scion-Spawn maker's "It has 'Sacrifice this token:
    Add {C}.'" — :func:`iter_static_defs` already deep-walks a ``Token``
    effect node's nested list), and a granted ability nested inside ANOTHER
    modification's chain. ``recipient_filter`` is the granting static's
    ``affected`` field — ``None``/``SelfRef`` for a self-referential grant
    (the token grants itself the ability), a ``Typed``/``Or``/``And`` filter
    naming who else receives it (Citanul Hierophants' "Creatures you
    control", Joiner Adept's "Lands you control").

    ADR-0039 W7: the ``is_mana_ability`` flag alone under-serves — it is
    ``MISSING`` (not True) for a granted ability that structurally produces
    mana but fails CR 605.1a's own "doesn't require a target" clause (Bigger
    on the Inside's "Target player adds two mana of any one color" — a
    genuine ramp source for deck-forge's build-around purposes regardless of
    the CR technicality that makes it a non-mana ability under the rules).
    The OR-relaxed gate below (``is_mana_ability is True OR the def's own
    effect tag is 'Mana'``) reads the STRUCTURE directly, matching the
    top-level nonland-doer arm's own "always acceleration" philosophy for a
    nonland recipient (no controller/targeting check either).
    """
    out: list[tuple[object, object]] = []
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            aff = getattr(sdef, "affected", None)
            for m in getattr(sdef, "modifications", None) or []:
                tag = tag_of(m)
                if tag == "GrantAbility":
                    d = getattr(m, "definition", None)
                elif tag == "GrantTrigger":
                    trig = getattr(m, "trigger", None)
                    d = getattr(trig, "execute", None) if trig is not None else None
                else:
                    continue
                if d is None:
                    continue
                if (
                    getattr(d, "is_mana_ability", None) is True
                    or tag_of(getattr(d, "effect", None)) == "Mana"
                ):
                    out.append((d, aff))
    return out


# Treasure-conversion ramp accessor (ADR-0039 W7): "Target creature becomes
# a Treasure artifact with '{T}, Sacrifice ~: Add one mana of any color,'
# and loses all other abilities" (Vraska's ultimates, Kitesail Larcenist)
# structures the TYPE change (SetCardTypes[Artifact] + AddSubtype[Treasure])
# but drops the quoted sac-for-mana ability entirely — no GrantAbility/
# GrantTrigger node survives, only the raw description string. Every
# printed "Treasure" permanent carries the SAME sac-for-mana ability by
# design convention (CR 111.4/205.3g); corpus-verified narrow (4/4 corpus
# AddSubtype(Treasure) static hits share the identical quoted text), so
# reading the AddSubtype(Treasure) modification itself as ramp evidence is
# a safe, bounded nested-descent read, not a whole-card regex guess.
def _has_animate_treasure_grant(tree: ConceptTree) -> bool:
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            for m in getattr(sdef, "modifications", None) or []:
                if tag_of(m) == "AddSubtype" and getattr(m, "subtype", None) == (
                    "Treasure"
                ):
                    return True
    return False


def _iter_returnasaura_mana_defs(
    tree: ConceptTree,
) -> list[tuple[object, object]]:
    """``(ability_def, enchant_filter)`` for a mana-producing ability granted
    by a ``ReturnAsAura`` effect's own ``grants`` list (Old-Growth Troll /
    Harold and Bob, First Numens: "It's an Aura enchantment with enchant
    Forest you control and 'Enchanted Forest has "{T}: Add {G}{G}"...'").
    ``grants`` is NOT one of :func:`iter_static_defs`'s traversal fields
    (``_EFFECT_CHILD_FIELDS`` = effect/sub_ability/execute only — a
    ``ReturnAsAura`` node's grants list sits one field over), so the
    GENERIC :func:`iter_typed_nodes` walk (every dataclass field) is the
    read here instead; the recipient is the ``ReturnAsAura``'s own
    ``enchant_filter`` (the SAME land/nonland accel-or-fixing gate the
    top-level :func:`_granted_mana_defs` recipient reads applies)."""
    out: list[tuple[object, object]] = []
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "ReturnAsAura":
                continue
            enchant = getattr(n, "enchant_filter", None)
            for g in getattr(n, "grants", None) or []:
                tag = tag_of(g)
                defs: list[object] = []
                if tag == "GrantAbility":
                    defs.append(getattr(g, "definition", None))
                elif tag == "GrantTrigger":
                    trig = getattr(g, "trigger", None)
                    defs.append(
                        getattr(trig, "execute", None) if trig is not None else None
                    )
                elif tag == "GrantStaticAbility":
                    # phase v0.29.0's return-as-aura pipeline wraps the
                    # granted body one level deeper: grants carries a
                    # GrantStaticAbility whose static definition's
                    # modifications hold the GrantAbility defs ("Enchanted
                    # Forest has '{T}: Add {G}{G}'" — Old-Growth Troll,
                    # Harold and Bob).
                    sdef = getattr(g, "definition", None)
                    for m in getattr(sdef, "modifications", None) or []:
                        if tag_of(m) == "GrantAbility":
                            defs.append(getattr(m, "definition", None))
                else:
                    continue
                for d in defs:
                    if d is None:
                        continue
                    if (
                        getattr(d, "is_mana_ability", None) is True
                        or tag_of(getattr(d, "effect", None)) == "Mana"
                    ):
                        out.append((d, enchant))
    return out


def _ramp(tree: ConceptTree) -> list[Signal]:
    """Mana acceleration (Sol Ring, Command Tower — CR 106.1 / 605.1a / 305).

    Mirrors the deleted ``_signals_ir``'s line ~8601. A ``Mana`` effect: a NONLAND ramp
    doer
    (rock / dork / ritual) is always acceleration → fire; a LAND splits — a
    basic-equivalent single-color / single-{C} tap is the MANA BASE (not ramp), but
    a land whose ramp is ACCELERATION (factor>1 / variable) OR FIXING (multi-color /
    any-color / any-type) IS ramp → fire. Scope "you".

    ADR-0038 W3 batch 4 (lands-and-ramp cluster): a GRANTED mana ability
    (:func:`_granted_mana_defs` — the dominant residual shape, ~150 corpus
    cards) applies the SAME land/nonland split to the RECIPIENT the grant
    names, not the granting card's own type: a nonland recipient (creatures,
    tokens, artifacts, permanents) is always acceleration, matching the
    top-level nonland-doer rule (Citanul Hierophants, Manaweft Sliver, Jaheira,
    every Eldrazi Scion/Spawn token maker); a LAND recipient (Joiner Adept,
    Nexos, Toxicrene) needs the same accel/fixing gate the card's-own-land
    branch above applies.

    Four ADR-0039 W7 closers extend the granted-mana reach:

    * :func:`_granted_mana_defs` now ALSO reads a granted TRIGGERED mana
      body (a ``GrantTrigger`` modification — Mark of Sakiko's "Whenever ~
      deals combat damage to a player, add that much {G}") and relaxes the
      ``is_mana_ability`` gate to an OR against the definition's own effect
      tag (Bigger on the Inside's "Target player adds two mana..." fails CR
      605.1a's own no-target clause but still structurally produces mana).
    * :func:`_iter_returnasaura_mana_defs` reads a mana ability granted via
      a ``ReturnAsAura`` effect's ``grants`` list (Harold and Bob, First
      Numens's "It's an Aura enchantment with enchant Forest ... 'Enchanted
      Forest has "{T}: Add three mana of any one color..."'") — a tree
      position :func:`iter_static_defs`'s narrow field walk never reaches.
    * :func:`_has_animate_treasure_grant` reads a static that turns a
      permanent into a Treasure artifact (Vraska's ultimates, Kitesail
      Larcenist, Minimus Containment) whose quoted sac-for-mana ability text
      never structures into a node at all (CR 111.4/205.3g — every printed
      Treasure carries the identical ability by design convention).
    * a LAND-recipient grant whose OWN cost is a ``Sacrifice`` (not the
      land's existing ``{T}``) is ACCELERATION regardless of the produced
      shape (Rain of Filth's "lands you control gain 'Sacrifice ~: Add
      {B}.'" — single, non-fixing {B}, so the bare accel/fixing gate below
      would read it as basic-equivalent MANA BASE): the grant is a BONUS
      mana source layered on top of the land's own tap ability, not the
      land's identity, so it is never the "mana base" case the top-level
      arm's basic-equivalent carve-out exists for (CR 106.1/605.1a).

    ADR-0039 task #82 grammar sprint: two former ledgered bridges (bridge_
    ledger.py) closed the residual "Add mana" clause-grammar tail this
    session. ``ramp_grant_unimplemented_body`` (a GrantAbility whose OWN
    definition parked as Unimplemented — Katilda, Old-Growth Troll, Tazri)
    RETIRED into ``tree_synthesis._arm_ramp_grant_unimplemented_body`` — the
    synthesized "ramp" concept node is read by the FIRST branch below
    (``effect_concepts("ramp")``), no lane code here at all.
    ``ramp_dropped_add_mana_clause`` (the scaling/restricted/note-type/die-
    roll "Add {mana}" residue class) NARROWED: 22 of its former 24 names
    graduated the same way; the 2 left (a mana-ability-HAVER support card
    with no add-mana clause of its own, and a keywords-field Mana effect no
    ability-unit walk reaches) stay a name-keyed bridge below.
    """
    is_land = tree.is_type("Land")
    for c in tree.effect_concepts("ramp"):
        if not is_land or _mana_accel(c.node) or _mana_fixing(c.node):
            return [Signal("ramp", "you", "", c.raw, tree.name, "high")]
    for d, aff in (*_granted_mana_defs(tree), *_iter_returnasaura_mana_defs(tree)):
        eff = getattr(d, "effect", None)
        if tag_of(aff) in ("Typed", "Or", "And"):
            landish = "Land" in filter_core_types(aff) or (
                {t.lower() for t in filter_subtypes(aff)} & _LAND_SUBTYPE_WORDS
            )
        else:
            landish = False
        sac_bonus = landish and tag_of(getattr(d, "cost", None)) == "Sacrifice"
        if not landish or sac_bonus or _mana_accel(eff) or _mana_fixing(eff):
            return [Signal("ramp", "you", "", "", tree.name, "high")]
    if _has_animate_treasure_grant(tree):
        return [Signal("ramp", "you", "", "", tree.name, "high")]
    # lf_ramp (2026-07-13 convention change): a NONLAND card's confirmed
    # self search that fetches a LAND to the BATTLEFIELD is ramp (mirrors
    # ``card_classify.is_ramp``'s fetch branch; CR 701.23/701.23a) — the
    # same :func:`structural_land_fetch_split` read the ``_tutor_lane``
    # reroute consults, so a clause can never lose tutor without this arm
    # firing from identical facts. The ``synth_tutor_directed`` veto is
    # mirrored for strict population parity with the tutor lane's baseline
    # (a vetoed tree never fired tutor, so it must not gain ramp here); the
    # bucket-B text tail rides ``tree_synthesis._arm_land_fetch_ramp``'s
    # real ``ramp`` node through the FIRST branch above instead. LAND cards
    # keep the mana-base carve-out (CR 305.6) — never this arm.
    if (
        not is_land
        and not any(c.concept == "synth_tutor_directed" for c in tree.iter_concepts())
        and has_structural_tutor(tree)
        and structural_land_fetch_split(tree)[0]
    ):
        return [Signal("ramp", "you", "", "", tree.name, "high")]
    if bridge_fires("ramp_dropped_add_mana_clause", tree):
        return [Signal("ramp", "you", "", "", tree.name, "high")]
    return []


def _is_big_mana_tree(tree: ConceptTree) -> bool:
    """Tree-native equivalent of the legacy ``_is_big_mana_ir`` structural arm
    (ADR-0039 task #80 step 3 — the membership-floor rewire off the OLD
    projected ``Card``): true when a mana-producing effect structurally
    produces MORE than one mana — reusing the SAME :func:`_mana_accel`
    predicate the ``ramp`` key lane's own acceleration gate applies (Sol
    Ring's ``{C}{C}``, Gilded Lotus's "three mana", Selvala / Cabal Coffers'
    dynamic count; Dark Ritual's ``{B}{B}{B}`` via the Fixed-colors-list
    shape ``_mana_accel`` already handles), over BOTH of the ``ramp`` lane's
    magnitude-bearing effect sources: a direct ``ramp`` effect concept on the
    card's own ability (``tree.effect_concepts("ramp")``), and a GRANTED mana
    ability (:func:`_granted_mana_defs` / :func:`_iter_returnasaura_mana_defs`
    — an Aura's "Enchanted land/creature/artifact has '{T}: Add two mana...'"
    body: Discreet Retreat, Tectonic Split, Mark of Sakiko, Bigger on the
    Inside — corpus-verified this session against the OLD IR's
    ``ir.all_abilities()`` walk). A factor==1 producer (Llanowar Elves'
    ``{G}``) is exactly ONE mana and is NOT big mana. Excludes the ``ramp``
    lane's remaining two arms (:func:`_has_animate_treasure_grant`, the
    per-card ledgered bridges) — neither carries a magnitude at all (a
    Treasure sac is always exactly one mana of any color). CR 106.4.

    GENUINE recall gains over ``_is_big_mana_ir`` (full commander-legal
    corpus re-measure, ADR-0039 task #80 step 3, adjudicated — not silent
    drift): Food Chain / Metamorphosis's "Add X mana... where X is 1 plus
    the exiled/sacrificed creature's mana value" is a dynamically-scaling
    amount phase's typed ``count`` correctly reads as non-Fixed, which the
    OLD projection's ``Quantity`` heuristic left ``op='fixed', factor=1``
    for (missing the "1 plus X" scaling entirely) — a genuine CR 106.4 big-
    mana source the old regex mirror ALSO never caught (neither "for each"
    nor "{}{}" literally appears). Harold and Bob, First Numens's granted
    "{T}: Add three mana of any one color" (via ``ReturnAsAura``) is factor
    3 — the OLD projection does not structure this ``ReturnAsAura``-granted
    ability into a ramp-category Effect at all, so ``_is_big_mana_ir``'s walk
    finds nothing to check; ``_iter_returnasaura_mana_defs`` reads it
    directly."""
    for c in tree.effect_concepts("ramp"):
        if _mana_accel(c.node):
            return True
    for d, _aff in (*_granted_mana_defs(tree), *_iter_returnasaura_mana_defs(tree)):
        if _mana_accel(getattr(d, "effect", None)):
            return True
    return False


# The membership floor's OWN token-maker raw mirror (ADR-0039 task #80 step 3):
# widens the pinned ``_TOKEN_MAKER_PATTERN`` (which requires the literal
# imperative "create ") to also match the third-person "creates" phase's own
# raw-slice preserves for a DIRECTED token maker ("Each player OTHER THAN
# target player creates ...", "its controller creates ..."). Deliberately NOT
# scoped by who receives the token (unlike the ``token_maker`` KEY lane's own
# ``_EACH_PLAYER_TOKEN_MAKER_RE`` widening, which excludes exactly those two
# phrasings because THAT lane claims a "you get a token too" self-benefit) —
# the floor's semantics only care that the card's own ability NAMES a
# creature-token subtype at all, matching the OLD IR's own ``ir.all_abilities()``
# walk (which read every ``make_token`` effect's subject regardless of
# ``controller`` — "any" fired identically to "you").
_FLOOR_TOKEN_MAKER_RAW = re.compile(
    r"\bcreates?\b[^.]*?\bcreature tokens?\b", re.IGNORECASE
)


def _floor_token_maker_subjects(tree: ConceptTree, vocab: frozenset[str]) -> set[str]:
    """The membership floor's token-maker -> type_matters cross-open subject
    set (CR 111.2 "The player who creates a token is its owner"; CR 205.3
    tribal subtypes): the structural :func:`structural_token_maker_type_
    subjects` set, widened with a per-concept raw mirror for a
    ``make_token`` effect phase leaves under-typed (an ``Unimplemented``
    node / an empty ``types`` tuple — Death by Dragons, Soul of
    Emancipation, Elephant Resurgence; verified this session against the OLD
    IR's ``e.subject`` Filter reads, which resolved these three
    structurally regardless of phase's own gap). Also
    reused by :func:`_type_matters_go_wide` arm (ii) — Cybernetica Datasmith's
    "Another target player creates a...Robot...token" now opens its own
    Artificer class tribe, a genuine recall gain the un-widened
    ``structural_token_maker_type_subjects`` never reached (verified against
    the OLD IR's SAME structural walk, which also resolves "Robot" — this
    isn't novel, just newly reachable).

    NARROW, ACCEPTED per-face gap (ADR-0039 task #80 step 3 corpus
    adjudication, 5 commander-legal cards): a two-face card whose token-maker
    ability lives on a NON-creature face (an Adventure spell / Saga chapter
    / the other half of a creature//creature pair) never widens the
    CREATURE face's own class-tribe go-wide, because ``extract_crosswalk_
    signals`` runs — and this function is scoped — per FACE tree, never a
    merged multi-face view (the documented ``_crosswalk_merge`` invariant:
    "never a merged multi-face tree, which would corrupt card-level reads
    like is_type / cmc"). Flaxen Intruder // Welcome Home, Huatli, Poet of
    Unity // Roar of the Fifth People, Kianne, Dean of Substance // Imbraham
    Dean of Theory, Jadzi, Steward of Fate // Oracle's Gift, and Eccentric
    Pestfinder // Turn Stones each lose ONLY their class tribe (their race
    tribe fires unconditionally regardless) — the SAME per-face isolation
    trait every other ported lane already has, not a regression unique to
    this rewire; closing it would require threading sibling-face trees
    through the whole ``extract_crosswalk_signals`` call chain, an
    architecture change out of this step's re-plumbing scope. See
    :func:`_apply_membership_floor`'s ``is_kill_engine`` docstring for the
    identical root cause on Sheoldred // The True Scriptures."""
    subjects = set(structural_token_maker_type_subjects(tree))
    for c in tree.effect_concepts("make_token"):
        types = [t for t in getattr(c.node, "types", None) or [] if isinstance(t, str)]
        if types:
            continue  # already resolved structurally above
        m = _FLOOR_TOKEN_MAKER_RAW.search(c.raw or "")
        if not m:
            continue
        head = re.split(r"creature tokens?", m.group(0), flags=re.IGNORECASE)[0]
        for word in reversed(_TOKEN_SUBJECT_WORDS.findall(head)):
            sub = _resolve_subject(word, vocab)
            if sub and sub.lower() != "human":
                subjects.add(sub)
                break
    return subjects


# ── Batch 3 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────


def _typed_matters_lanes(filt: object) -> list[str]:
    """The artifacts/enchantments lane(s) for a YOUR-permanents filter (CR 702.41 /
    604.3). Mirrors the deleted ``_signals_ir``'s identically-named
    ``_typed_matters_lanes``: a non-opponent filter naming
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


# Recovered make_token raw reads (see the recovered-node fallback inside
# _artifacts_enchantments_matter): the type word must sit in the SAME
# create-clause as the "token" noun ([^.]* keeps it inside one sentence),
# mirroring the typed arm's vocabulary — the Artifact card-type word or a
# predefined artifact-token subtype (CR 205.3g), and the Enchantment
# card-type word (covers "Aura enchantment token" / "enchantment creature
# token" phrasings).
_RECOVERED_ARTIFACT_TOKEN_RE = re.compile(
    r"\b(?:artifact|"
    + "|".join(sorted(ARTIFACT_TOKEN_SUBTYPES))
    + r")\b[^.]*\btokens?\b"
)
_RECOVERED_ENCHANT_TOKEN_RE = re.compile(r"\benchantment\b[^.]*\btokens?\b")


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
    Watch composite). Mirrors the deleted ``_signals_ir``'s ``_generic_board_subject``:
    controller you,
    NO subtype (a subtyped buff is a narrower tribal care), Artifact/Enchantment in
    core types.
    """
    if filter_controller(filt) != "You" or filter_subtypes(filt):
        return []
    cores = filter_core_types(filt)
    if "Permanent" in cores:
        return []
    return [lane for ct, lane in _TYPE_MATTERS_LANE.items() if ct in cores]


def _type_recursion_lanes(filt: object) -> list[str]:
    """The GY-recursion sibling of :func:`_typed_matters_lanes`, ADDING the
    Aura-SUBTYPE fallback (ADR-0038 W4 giant, byte-mirrors
    the deleted ``_signals_ir``'s identically-named ``_type_recursion_lanes``): "return
    target Aura card from
    your graveyard to your hand" (Ironclad Slayer), "return each Aura card
    …" (Retether), "put target Aura card … onto the battlefield" (Iridescent
    Drake) filter on the SUBTYPE ``Aura``, not the core type ``Enchantment``
    — phase's recursion target filter carries ``card_types=()`` for a bare
    subtype-named card ("Aura or Equipment card"), so
    :func:`_typed_matters_lanes` alone returns nothing. CR 205.3 / 303.4:
    Aura is an Enchantment subtype, so a subtype-only recursion target still
    opens a LOOSE ``enchantments_matter`` member — but ONLY when no broader
    CORE-type lane already fired (a composite "artifact or enchantment card"
    target names ``Enchantment`` directly and needs no fallback), and only
    for a non-opponent-controlled filter (the same exclusion
    ``_typed_matters_lanes`` applies to the core-type read).
    """
    lanes = _typed_matters_lanes(filt)
    if lanes:
        return lanes
    if filt is None or filter_controller(filt) == "Opponent":
        return []
    if any(s.lower() == "aura" for s in filter_subtypes(filt)):
        return ["enchantments_matter"]
    return []


def _artifacts_enchantments_matter(tree: ConceptTree) -> list[Signal]:
    """artifacts_matter / enchantments_matter — the broad type-payoff lanes (CR 301 /
    303). Mirrors the deleted ``_signals_ir``'s six structural arms over the typed
    substrate:

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
        if c.concept in ("tutor", "dig") or tag_of(node) == "SearchOutsideGame":
            # ADR-0038 W4 giant: ``dig`` ("look at the top N cards …, put
            # an artifact card into your hand/battlefield" — Commune with
            # Beavers, Forging the Anchor, Kayla's Reconstruction) is the
            # SAME type-restricted-library-search shape as ``tutor``
            # (CR 701.23), just not a literal "search your library" —
            # phase distinguishes the two only by whether the whole
            # library is searched vs a fixed top-N window. Both read the
            # SAME NO-subtype-restricted-filter gate.
            #
            # ADR-0038 W5 tails: ``SearchOutsideGame`` (the Wish idiom, CR
            # 108.3 — a card brought into the game from outside it —
            # "You may reveal an artifact or enchantment card you own from
            # outside the game and put it into your hand" — Golden Wish)
            # is the SAME type-restricted-search shape again, over a THIRD
            # zone (outside the game, not library/top-N) — read LOCALLY
            # here by its own typed tag (never routed through the
            # ``tutor`` CONCEPT_MAP, which would also open the dedicated
            # ``tutor`` SIGNAL lane for every Wish card — CR 701.23's
            # "search your library" is a distinct action from the Wish
            # idiom, so conflating the two concepts would be a genuine
            # membership error for that OTHER lane, not just an
            # artifacts_matter widening).
            sub = effect_filter(node)
            if sub is not None and not filter_subtypes(sub):
                out.extend(_typed_matters_lanes(sub))
        if c.concept == "become_copy":
            # ADR-0038 W5 tails: a self-transform that becomes a copy of a
            # TYPE-RESTRICTED card (Spirit of Resilience's "you may have
            # this creature become a copy of an artifact or creature card
            # from among those cards" — target = Or[Artifact, Creature]) is
            # the SAME type-restricted-search-target shape as tutor/dig
            # (CR 707 copy effects, layered over CR 701.23's philosophy) —
            # an ORDINARY Clone's "becomes a copy of TARGET CREATURE" (a
            # single bland Creature-only filter) stays silent by
            # construction (``_typed_matters_lanes`` only fires on an
            # Artifact/Enchantment CORE type, never bare Creature).
            sub = effect_filter(node)
            if sub is not None and not filter_subtypes(sub):
                out.extend(_typed_matters_lanes(sub))
        if c.concept == "make_token" and c.scope in ("you", "any"):
            types = c.subject
            if _is_artifact_token_types(types):
                out.append("artifacts_matter")
            if "Enchantment" in types:
                out.append("enchantments_matter")
            # Recovered-node fallback (ADR-0038 post-giants batch): a
            # make_token recovered off an Unimplemented residue keeps the
            # phase wrapper as its ``.node`` — no typed token subject to
            # read — so the create-clause's own type words are the only
            # carrier (the dig_until / hand_revealed recovered-node
            # precedent). Corpus census at introduction: 38 recovered
            # make_token nodes total; the artifact/enchantment hits are
            # all genuine (Smoke Spirits' Aid's named-Aura shape, Circuits
            # Act / Yawgmoth Merfolk Soul's Clown Robots, the Treasure /
            # Food resource-token class — CR 111.4/205.3g).
            if not types and c.recovered_by == "make_token" and c.raw:
                low = c.raw.lower()
                if _RECOVERED_ARTIFACT_TOKEN_RE.search(low):
                    out.append("artifacts_matter")
                if _RECOVERED_ENCHANT_TOKEN_RE.search(low):
                    out.append("enchantments_matter")
        # COPY-TOKEN doer (ADR-0038 W4 giant): "create a token that's a
        # copy of target artifact/creature" (Molten Duplication, Echo
        # Storm, Saheeli's Artistry). A copy token's creator is its owner
        # and it enters under that player's control (CR 111.2) regardless
        # of who controls the copied source, so — unlike ``make_token`` —
        # this concept is NOT scope-gated: ``CopyTokenOf``'s ``c.scope``
        # reflects the copied OBJECT's controller (often "any"/"each" for
        # a "target artifact" with no controller restriction), not the
        # token's recipient, which is always you (the caster).
        if c.concept == "copy_token":
            types = c.subject
            if _is_artifact_token_types(types):
                out.append("artifacts_matter")
            if "Enchantment" in types:
                out.append("enchantments_matter")
        # TYPE-RECURSION doer (ADR-0038 W4 giant): a graveyard recursion
        # (reanimate / GY→hand bounce / GY→library) whose target is
        # FILTERED to the card type — single ("return target artifact
        # card" — Refurbish) or mass ("return all enchantment cards" —
        # Replenish); a composite ("artifact or creature card" — Argivian
        # Find, Open the Vaults) fires both. Mirrors the deleted ``_signals_ir``'s
        # ``_type_recursion_lanes`` (CR 115.1/115.10 — the discriminator is
        # the TYPE, not mass-vs-single), INCLUDING its Aura-subtype
        # fallback (:func:`_type_recursion_lanes` above — "return target
        # Aura card" — Ironclad Slayer, Retether — CR 205.3/303.4). ANY
        # graveyard qualifies (Beacon of Unrest's "a graveyard" — no
        # explicit controller); the exclusion is an opponent-owned filter
        # (``_typed_matters_lanes``' own Opponent gate), never a
        # generic-target recursion ("return target card" — Regrowth) which
        # fires no core type at all.
        if c.concept == "change_zone":
            origin, dest = change_zone_dirs(node)
            gy_recursion = origin == "Graveyard" and dest in (
                "Battlefield",
                "Hand",
                "Library",
            )
            # ADR-0038 W5 tails: a BATTLEFIELD-sourced library-bounce ("put
            # target artifacts on top of their owners' libraries" —
            # Rebuking Ceremony) is a DIFFERENT CR provision (401.4's
            # library-position "tuck" removal, not graveyard recursion)
            # but the SAME broad "cares about the Artifact type" tell (an
            # artifact-hate spell targeting the type specifically, same as
            # the graveyard-recursion arm's philosophy — CR 301). A
            # targeted spell's origin is ``None`` (wherever the object
            # currently is, implicitly the battlefield for a permanent-
            # only filter) or explicit ``Battlefield``; ``Graveyard``
            # origin is excluded here — that shape is ALREADY ``gy_
            # recursion`` above (a genuinely different CR 400.7 recursion
            # idiom, not double-counted). MANDATORY EXCLUSION: gated to
            # the TARGETED ``ChangeZone`` tag only, never ``ChangeZoneAll``
            # — Harmonic Convergence's "Put ALL enchantments on top of
            # their owners' libraries" is the SAME MASS/symmetric-reset
            # shed the enchantments_matter sibling already adjudicates (CR
            # 205.2, no controller restriction at all — a board-wide reset
            # affecting every player equally, never a "my deck wants this
            # type" build-around, same philosophy as the TYPE-DIES doer's
            # symmetric-punisher exclusion elsewhere in this lane); a
            # TARGETED tuck (a specific chosen count) is a genuine
            # build-around tell a mass reset is not.
            bf_library_bounce = (
                tag_of(node) == "ChangeZone"
                and origin in (None, "Battlefield")
                and dest == "Library"
            )
            if gy_recursion or bf_library_bounce:
                out.extend(_type_recursion_lanes(effect_filter(node)))
        # The library-TOP/BOTTOM sibling of the same recursion shape
        # ("put target artifact card from a graveyard on the bottom/top of
        # its owner's library" — Keeper of the Cadence, Dukhara Scavenger)
        # is a SEPARATE ``PutAtLibraryPosition`` typed node, not a
        # ``ChangeZone`` — no ``origin`` field of its own, so the "from a
        # graveyard" gate reads the target filter's ``InZone: Graveyard``
        # property instead (CR 400.7).
        if c.concept == "put_library_position":
            filt = effect_filter(node)
            if "Graveyard" in filter_inzone_zones(filt):
                out.extend(_type_recursion_lanes(filt))
        # A third recursion sibling: casting the card DIRECTLY from the
        # graveyard ("you may cast target artifact, instant, or sorcery
        # card … from your graveyard without paying its mana cost" —
        # Victor Timely) is a ``CastFromZone`` typed node — same
        # ``InZone: Graveyard`` property gate as the library-position arm
        # above (neither carries a ``ChangeZone``-style bare ``origin``).
        if c.concept == "cast_from_zone":
            filt = effect_filter(node)
            if "Graveyard" in filter_inzone_zones(filt):
                out.extend(_type_recursion_lanes(filt))
    # SAC PAYOFF — your-fodder artifact/enchantment sac (Atog-style). Per-unit so the
    # edict guard applies: "each opponent sacrifices an artifact/enchantment" (Tribute
    # to the Wild, Mire in Misery, Vile Mutilator) is an EDICT phase mislabels with a
    # you-controlled subject; ``_sac_is_edict`` (per-effect player_scope, incl. modal
    # arms) rejects it (CR 701.21a). The Permanent-symmetric-list gate (CR 702.166a)
    # drops the Bargain alt-cost.
    #
    # ADR-0038 W4 giant bugfix: the subject-controller gate ACCEPTS
    # ``None`` (not just explicit "You") — mirrors the deleted ``_signals_ir``'s
    # own gate for this arm (``esub.controller != "opp"``, not ``== "you"``).
    # "Sacrifice any number of artifacts, creatures, and/or lands" (an
    # implicit-you self-sac cost/effect, no "target"/other-player wording —
    # Reprocess, Nyssa of Traken, Malevolent Witchkite, Lich-Knights'
    # Conquest) carries ``controller: None`` on the sacrificed filter, not
    # "You"; ``_sac_is_edict``'s wrapper player_scope read is the edict
    # guard, so a bare-None subject here is a genuine self-sac, not an
    # under-caught edict. The gate still REJECTS any explicit non-You
    # controller, not just "Opponent" — "target opponent sacrifices a
    # nontoken artifact of their choice" (Balor, Rootcast Apprenticeship)
    # tags the filter controller ``TargetPlayer`` (a chosen/targeted
    # player, CR 701.21a's edict-target), which ``_sac_is_edict``'s modal
    # wrapper-scope read does not catch on these two — a bare exclusion of
    # "Opponent" alone would leak the edict through.
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "sacrifice" or c.scope == "opponents":
                continue
            if _sac_is_edict(unit, c.node):
                continue
            sub = effect_filter(c.node)
            if sub is None:
                continue
            ctrl = filter_controller(sub)
            if ctrl is not None and ctrl != "You":
                continue
            cores = filter_core_types(sub)
            if "Permanent" in cores:
                continue
            if _is_artifact_token_types(c.subject):
                out.append("artifacts_matter")
            if "Enchantment" in cores:
                out.append("enchantments_matter")
        # ADR-0038 W5 tails: a ``ChooseOneOf``-wrapped sac ("you may
        # sacrifice a Food or pay {2}{W}" — Nimble Hobbit) is an ORDINARY
        # resolution-time effect branch (CR 701.21a — the sacrifice still
        # just moves a permanent the controller controls to their
        # graveyard, same rule as any other Sacrifice), not an activation
        # cost, so ``_walk_effect_chain`` collapses the whole
        # ``ChooseOneOf`` to one opaque ``other`` concept — the unit's own
        # ``effects`` list never decomposes into per-branch concepts the
        # way ``unit.costs``/``unit.statics`` do. Deep-scan for a
        # ``Sacrifice`` inside any branch directly; the SAME edict/
        # controller/core-type gates apply (a branch is just as capable of
        # naming an opponent-directed or Permanent-list sac as a top-level
        # effect).
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "ChooseOneOf":
                continue
            for branch in getattr(n, "branches", None) or ():
                beff = getattr(branch, "effect", None)
                if not isinstance(beff, TypedMirrorNode) or tag_of(beff) != "Sacrifice":
                    continue
                if _sac_is_edict(unit, beff):
                    continue
                sub = effect_filter(beff)
                if sub is None:
                    continue
                ctrl = filter_controller(sub)
                if ctrl is not None and ctrl != "You":
                    continue
                cores = filter_core_types(sub)
                if "Permanent" in cores:
                    continue
                types = cores + filter_subtypes(sub)
                if _is_artifact_token_types(types):
                    out.append("artifacts_matter")
                if "Enchantment" in cores:
                    out.append("enchantments_matter")
    # SAC-COST PAYOFF — an artifact/enchantment sac paid as a COST: a bare
    # activated-ability cost (Atog, Priest of Yawgmoth), a Composite-wrapped
    # cost leaf (Shattergang Brothers' "{2}{R}, Sacrifice an artifact:"), or a
    # spell's ``additional_cost`` (merged onto the Spell unit's ``costs`` by
    # ``build_concept_tree`` — Costly Plunder, Trash for Treasure, Kuldotha
    # Rebirth). A COST is always paid by the ACTIVATOR (CR 601.2b / 602.2), so
    # no opponent/edict gate applies here, unlike the effect arm above. The
    # Permanent-in-list gate still drops the OPTIONAL Bargain alt-cost (CR
    # 702.166a — Ice Out's "sacrifice an artifact, enchantment, or token").
    for unit in tree.units:
        leaves = [c.node for c in unit.costs if c.concept == "sacrifice"] + [
            leaf
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
            if tag_of(leaf) == "Sacrifice"
        ]
        for leaf in leaves:
            filt = effect_filter(leaf)
            cores = filter_core_types(filt)
            if "Permanent" in cores:
                continue
            if _is_artifact_token_types(cores + filter_subtypes(filt)):
                out.append("artifacts_matter")
            if "Enchantment" in cores:
                out.append("enchantments_matter")
    # generic-board static anthem/grant (Padeem) — read the static's affected filter
    for unit in tree.units:
        for c in unit.statics:
            if c.concept in ("pump", "grant_keyword", "set_pt"):
                aff = getattr(unit.node, "affected", None)
                out.extend(_generic_board_lanes(aff))
                # One-level Or/And descent (CR 604.3: "some static abilities
                # apply to more than one type of object" — the Silkguard
                # precedent, :func:`_or_wrapped_generic_creature_filter`):
                # re-apply the SAME per-branch gate, so a subtype-scoped or
                # opponent branch still fails for the reason it would
                # un-wrapped. This is the STRUCTURAL read that graduated the
                # ``bello_static_animate_artifacts`` ledgered bridge (task
                # #84): phase v0.23.0 now parses Bello, Bard of the
                # Brambles' whole animation line as one Continuous static
                # over ``Or(Typed(You, non-Equipment Artifact, cmc>=4),
                # Typed(You, non-Aura Enchantment, cmc>=4))`` with SetPower/
                # SetToughness + AddType + GrantTrigger + AddKeyword
                # modifications, so the anthem arm's set_pt/grant_keyword
                # concepts reach it and the branch read replaces the
                # bridge's bounded parse-failure-residue scan.
                if tag_of(aff) in ("Or", "And"):
                    for br in getattr(aff, "filters", None) or ():
                        out.extend(_generic_board_lanes(br))
    # BECOMES-TYPE doer (ADR-0038 W4 giant) — a SANCTIONED byte-identical
    # port of legacy's ``_BECOMES_TYPE_RE`` (the LIVE constant, imported
    # not re-typed): a "becomes a/an artifact" type-grant (Relic's Roar's
    # "target artifact or creature becomes a Dinosaur artifact creature";
    # Captain Rex Nebula's Vehicle animate). phase drops the granted type
    # to an ``AddType`` mod carrying no back-link to the ORIGINAL clause
    # shape the regex discriminates on (a lone-target "becomes a/an
    # <adj>* artifact" vs a plural/no-article board grant — "Vehicles you
    # control BECOME artifact creatures" — or a self-animate manland whose
    # own P/T digits between "becomes a" and "artifact" break the anchor —
    # Blinkmoth Nexus's "becomes a 1/1 … artifact creature" — deliberately
    # excluded, matching legacy exactly). Run PER-CLAUSE over
    # ``_kept(tree)`` like the main mirror. A "becomes a COPY of" (True
    # Polymorph, Absorbing Man) is a clone effect, not a type-grant —
    # legacy's ``e.category not in (make_token, clone)`` guard excludes
    # it structurally; the per-clause text scan has no category to read,
    # so it excludes on the "copy" word instead (never the deciding vote
    # for a real type-grant clause, which never says "copy"). CR 205.1b.
    for cl in _clauses(_kept(tree)):
        bt_m = _BECOMES_TYPE_RE.search(cl)
        if bt_m and "copy" not in bt_m.group(0).lower():
            out.append(_TYPE_MATTERS_LANE[bt_m.group(1).capitalize()])
    # TOKEN-SUBTYPE cares-about reference (ADR-0038 W4 giant) — a
    # SANCTIONED byte-identical port of legacy's ``_TOKEN_SUBTYPE_OWN_REF``
    # (the LIVE constant): a cares-about mention of a named artifact-token
    # subtype WITHOUT making/sacrificing it — "Foods you control" (Hobbit's
    # Sting, Rent Is Due, Honored Dreyleader), "Treasures you control"
    # become (Vihaan) — a count operand / anthem subject phase carries no
    # structural filter for (the subtype rides bare prose, not a Filter
    # node). Blood/Clue/Food/Treasure are ALL artifact tokens (CR 205.3g),
    # so any match feeds artifacts_matter directly (no enchantment
    # counterpart — none of the four are ever enchantments).
    if any(_TOKEN_SUBTYPE_OWN_REF.search(cl) for cl in _clauses(_kept(tree))):
        out.append("artifacts_matter")
    # CAST-TRIGGER doer (recall gap): "whenever you cast an artifact/enchantment
    # spell, <payoff>" (Argothian Enchantress, Enchantress's Presence, Sythis,
    # Mishra). Mirrors the deleted ``_signals_ir``'s line ~10974 — the watched-spell
    # filter's
    # core type feeds the type lane, gated to a non-opponent caster (an
    # opponent-cast punisher — Citanul Druid — is not a type deck). This is the
    # ROUTING HOME for the enchantment/artifact-only cast watcher that
    # ``_spellcast_matters`` deliberately excludes (the payoff body — a Draw — is
    # never itself a type tell, so the is-enchantment membership floor misses
    # it). CR 603.2.
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "cast_spell":
            continue
        if trigger_caster_scope(unit.node) == "opponents":
            continue
        out.extend(_typed_matters_lanes(getattr(unit.node, "valid_card", None)))
    # SACRIFICE-TRIGGER payoff DOER (ADR-0038 W4 giant): "whenever you
    # sacrifice a Clue/Food/artifact, <payoff>" (Graf Mole, Curious
    # Cadaver, Jenny Flint's "Clue or Food"). The same trigger-own-subject
    # read as the CAST-TRIGGER doer above, but Artifact-token SUBTYPES
    # (Clue/Food/Treasure/… CR 205.3g) carry an EMPTY core-type list, so
    # this checks core+subtype words together (mirrors the ``copy_token``/
    # ``make_token`` arms), not the core-only ``_typed_matters_lanes``
    # gate. Excludes an opponent-scoped watched sac (not your build-around).
    # CR 701.16 (Sacrifice) / 603.2.
    for unit in tree.units:
        if unit.trigger_event != "sacrificed":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or filter_controller(vc) == "Opponent":
            continue
        words = filter_core_types(vc) + filter_subtypes(vc)
        if _is_artifact_token_types(words):
            out.append("artifacts_matter")
        if "Enchantment" in words:
            out.append("enchantments_matter")
    # CONDITION type-gate DOER (ADR-0038 W4 giant): a static/triggered
    # ability's "as long as you control an artifact/enchantment, …" gate
    # (``IsPresent`` / ``ControlsType``) or a threshold count ("… two or
    # more artifacts" — ``QuantityComparison``/``QuantityCheck`` over an
    # ``ObjectCount`` ref). Mirrors the deleted ``_signals_ir``'s condition-gate arm
    # (``cond.kind in controlstype/quantitycomparison/quantitycheck/
    # ispresent``) — ANY comparator direction counts (a "control NO
    # artifacts" floor punisher — Glimmervoid's sac trigger — still wants
    # an artifacts deck, same as a "two or more" threshold gate).
    # ``iter_condition_sites`` reaches both a unit's own ``condition`` and
    # its ``activation_restrictions`` entries; :func:`_condition_leaves`
    # (ADR-0038 W4 giant) then descends any And/Or compound to its leaf
    # checks — "if you control an artifact AND an enchantment" (When We
    # Were Young, Okiba Salvage, Banishing Slash) types as ONE
    # ``T_condition__And`` wrapping two ``QuantityCheck`` leaves, which the
    # flat tag switch below can't read without the descent. CR 603.2
    # (static abilities with a continuously-checked condition) / 608.2b
    # (compound conditions read leaf-by-leaf).
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for cond in _condition_leaves(site):
                tag = tag_of(cond)
                if tag in ("IsPresent", "ControlsType"):
                    out.extend(_typed_matters_lanes(getattr(cond, "filter", None)))
                elif tag in ("QuantityComparison", "QuantityCheck"):
                    lhs = getattr(cond, "lhs", None)
                    if tag_of(lhs) == "Ref":
                        qty = getattr(lhs, "qty", None)
                        # ObjectCount ("two or more artifacts") and
                        # ZoneChangeCountThisTurn ("an artifact was put into
                        # a graveyard from the battlefield this turn" —
                        # Ichor Shade) share the SAME ``filter`` field
                        # shape.
                        if tag_of(qty) in ("ObjectCount", "ZoneChangeCountThisTurn"):
                            out.extend(
                                _typed_matters_lanes(getattr(qty, "filter", None))
                            )
    # TYPE-ETB doer (ADR-0038 W4 giant): "whenever an artifact/creature/
    # enchantment enters, <payoff>" (Era of Innovation, Confusion in the
    # Ranks — a SYMMETRIC any-player watcher, not gated to you). Reads
    # the trigger's OWN ``valid_card`` watched-subject filter, the same
    # shape the CAST-TRIGGER doer below reads for a cast event. CR 603.2.
    #
    # TYPE-DIES doer, narrower: "…dies/is put into a graveyard from the
    # battlefield, <payoff>" fires ONLY for a YOUR-controlled watched
    # subject (Pia's Revolution, Seer of Stolen Sight's "artifacts and/or
    # creatures you control"). Unlike the ETB doer, a SYMMETRIC death
    # watcher ("whenever AN artifact is put into a graveyard from the
    # battlefield" — Disciple of the Vault, Fangren Marauder, Molder
    # Beast) is an ARTIFACT-DEATH PUNISHER that profits off ANY artifact
    # dying, including an opponent's own removal — not a "my deck wants
    # artifacts" build-around, so it's deliberately excluded (mirrors
    # legacy, which routes these to a different death-payoff lane, not
    # artifacts_matter). CR 700.4.
    for unit in tree.units:
        if unit.trigger_event == "enters":
            out.extend(_typed_matters_lanes(getattr(unit.node, "valid_card", None)))
        elif unit.trigger_event == "dies":
            vc = getattr(unit.node, "valid_card", None)
            if filter_controller(vc) == "You":
                out.extend(_typed_matters_lanes(vc))
    # ADR-0038 W4 giant — a SANCTIONED byte-identical port of legacy's
    # ``_ARTIFACTS_MATTER_MIRROR`` (the LIVE constant, imported not re-typed):
    # phase carries no clean structural shape for this oracle-idiom family —
    # Affinity/Improvise/Metalcraft keyword payoffs (CR 702.41/702.126/207.2c),
    # artifact tutors and graveyard recursion, "abilities of artifacts",
    # "becomes an artifact" — so the legacy per-clause reminder-stripped-
    # oracle scan is the last-resort mechanism. Corpus-verified in the legacy
    # path (regex_only==22, ALL affinity-for-non-artifact over-fire, 0
    # genuine recall lost by the narrowed `affinity for artifacts` branch).
    # Run PER-CLAUSE over ``_kept(tree)`` to match the legacy clause loop.
    if any(_ARTIFACTS_MATTER_MIRROR.search(cl) for cl in _clauses(_kept(tree))):
        out.append("artifacts_matter")
    # ADR-0038 W4 giant — a SANCTIONED byte-identical port of legacy's
    # ``_ENCHANTMENTS_MATTER_MIRROR`` (the LIVE constant, imported not
    # re-typed): the enchantment sibling of the artifacts mirror above. phase
    # carries no clean structural shape for this oracle-idiom family either —
    # enchantment tutors / graveyard recursion phrased as "enchantment card"
    # (Auramancer), "enchantment card in your hand" miracle-grants (Aminatou),
    # Role-token makers (Roles are Aura enchantments, CR 303.7), constellation
    # ("whenever an enchantment enters"), and enchantress cast triggers — so
    # the legacy per-clause reminder-stripped-oracle scan is the last-resort
    # mechanism, same as the artifacts sibling. Corpus-verified in the legacy
    # path (regex_only EMPTY after the mirror — 0 genuine recall lost). Run
    # PER-CLAUSE over ``_kept(tree)`` to match the legacy clause loop.
    if any(_ENCHANTMENTS_MATTER_MIRROR.search(cl) for cl in _clauses(_kept(tree))):
        out.append("enchantments_matter")
    # AFFINITY-FOR-EQUIPMENT doer (ADR-0038 W4 giant): Equipment IS an
    # Artifact subtype (CR 301.5), so "Affinity for Equipment" (Nahiri,
    # Forged in Fury; Goldwardens' Gambit; Oxidda Finisher; Rebel Salvo) is
    # a genuine artifact-count cost reducer — phase's own raw keyword node
    # tags it with the implied ``Artifact`` core type alongside the
    # ``Equipment`` subtype (mirrors legacy's ``_affinity_improvise_
    # markers``), but that raw ``root.keywords`` array isn't in the typed
    # substrate's unit walk. The narrowed mirror above deliberately keeps
    # `affinity for artifacts` (not bare ``\baffinity\b``) to drop the 22
    # affinity-for-non-artifact over-fires (Icebreaker Kraken's snow
    # affinity, Argivian Phalanx's creature affinity) — this is the ONE
    # additional affinity spelling that IS an artifact tell, checked
    # separately so the mirror stays byte-identical to the live constant.
    # CR 702.41a / 301.5.
    if "affinity for equipment" in _kept(tree).lower():
        out.append("artifacts_matter")
    # AFFINITY-FOR-ENCHANTMENTS doer (ADR-0038 W4 giant): "Affinity for
    # enchantments" (Brine Giant) is a bare KEYWORD LINE, not a
    # ``you control`` phrase — the reminder text carrying "for each
    # enchantment you control" is stripped by ``_kept`` (parenthetical), so
    # ``_ENCHANTMENTS_MATTER_MIRROR``'s ``\benchantments? you control\b``
    # branch never sees it, unlike the sibling ``_ARTIFACTS_MATTER_MIRROR``
    # which bakes an explicit ``affinity for artifacts`` alternation in
    # (ARTIFACTS_MATTER_REGEX) — ENCHANTMENTS_MATTER_REGEX carries no such
    # branch. legacy fires this structurally (its own projector turns the
    # bare ``Affinity`` keyword into a synthetic count-operand effect), but
    # phase's raw keyword node isn't in the typed substrate's unit walk —
    # same gap the AFFINITY-FOR-EQUIPMENT arm above papers over for
    # artifacts. CR 702.41a / 303.
    if "affinity for enchantments" in _kept(tree).lower():
        out.append("enchantments_matter")
    # ADR-0039 W7 ledgered bridge — the v0.35.2 reflexive-payment
    # regression (bridge_ledger.py row, docstring there for the CR 603.12
    # / CR 205.3g grounding and full census): Nimble Hobbit's "you may
    # sacrifice a Food or pay {2}{W}" trigger body parks WHOLE as an
    # Unimplemented residue, dropping the typed Food Sacrifice branch the
    # deep scan read at v0.23.0.
    if bridge_fires("artifact_sac_reflexive_payment_unparsed", tree):
        out.append("artifacts_matter")
    seen: set[str] = set()
    sigs: list[Signal] = []
    for lane in out:
        if lane not in seen:
            seen.add(lane)
            sigs.append(Signal(lane, "you", "", "", tree.name, "high"))
    return sigs


def _or_wrapped_generic_creature_filter(filt: object) -> object | None:
    """A generic creature-you-control filter reachable off an ``Or``/``And``
    wrapper's branches (ADR-0039 W8 closer) — a static ability's ``affected``
    field can name multiple qualifying object types disjunctively (CR 604.3:
    "some static abilities apply to more than one type of object" — the
    Silkguard shape, "Auras, Equipment, and modified creatures you control
    gain hexproof": ``Or(Aura, Equipment, Typed(You, no-subtype, Modified,
    Creature))``). :func:`_is_generic_creature_filter` fails on the WHOLE
    ``Or`` node (``filter_controller``/``filter_core_types`` don't recurse
    into branches), so this descends exactly ONE level and re-applies the
    SAME gate per branch — no separate zone/subtype/predicate logic, so a
    graveyard- or subtype-scoped branch (Emergency Weld's "artifact or
    creature card from your graveyard", Rukarumel's Sliver-subtype branch)
    still fails for the SAME reason it would un-wrapped.

    Scoped as a lane-local helper used ONLY on
    :func:`_iter_creatures_matter_static_defs`'s ``affected`` field (the
    team-anthem arm) — never on a spell/ability ``target`` field, where an
    ``Or``-wrapped choice is TARGET context (CR 115.1, the Divine Resilience
    precedent: a preselected object, not a population filter), corpus-
    verified as the shape carried by every OTHER ``Or``-wrapped-affected/
    target family member (Emergency Weld's ``ChangeZone.target``, Battle for
    Bretagard's ``TargetOnly.target``, Back on Track / Takenuma / Pestilent
    Cauldron / Tymaret Calls the Dead's ``ChangeZone.target``, Churning
    Reservoir's ``PutCounter.target``) — none of those nodes are static defs
    :func:`_iter_creatures_matter_static_defs` yields at all, so this helper
    never reaches them by construction.

    The descent recurses nested ``Or``/``And`` wrappers (phase v0.35.2's
    structured same-is-true rider groups the battlefield branches one level
    deeper — Rukarumel's ``Or(Or(Sliver, Creature-NonToken), Stack-span,
    owned-cards-span)``); the SAME per-leaf gate applies at every depth, so
    the safety argument is unchanged.
    """
    if _is_generic_creature_filter(filt):
        return filt
    if tag_of(filt) in ("Or", "And"):
        for sub in getattr(filt, "filters", None) or ():
            found = _or_wrapped_generic_creature_filter(sub)
            if found is not None:
                return found
    return None


# Modification tags the ``creatures_matter`` team-anthem arm treats as a payoff
# over the ``affected`` filter — mirrors ``_MOD_CONCEPTS``' pump/set_pt/
# grant_keyword coarse buckets (CR 613.4c layer-7 P/T + CR 702.1 keyword
# abilities) plus the two SCALING P/T mod tags (``_DYNAMIC_PT_MODS`` below,
# at line ~6023 — module-level forward reference, safe at call time) a
# continuous counter-scaled anthem uses instead of the fixed ``Add*`` pair
# (Call for Unity's "+1/+1 for each unity counter" — CR 107.3/613.4c), plus
# ``GrantAbility``/``GrantTrigger`` — granting your creatures a whole new
# ability (Lightning Volley's "have '{T}: deal 1 damage'", Kira's granted
# spell-fizzle trigger) is the same team-payoff shape as granting a bare
# keyword, just carrying a nested ability def instead of a keyword string
# (CR 113.10 — "an effect that adds an ability will state that the object
# 'gains' or 'has' that ability"; verified via rules-lookup), plus
# ``SetPowerDynamic``/``SetToughnessDynamic`` — the SET-to-a-dynamic-value
# pair (Biomass Mutation's "have base power and toughness X/X", CR 613.4b
# "effects that refer to the BASE power and/or toughness ... apply in this
# layer") a team-wide base-P/T rewrite uses instead of the fixed ``Set*``
# pair. ADR-0038 W5 tails: these two tags map to ``base_pt_set`` only
# 77%/79% corpus-wide (``compat._MOD_TAG_CATEGORY`` comment — under the 90%
# auto-map bar), so they are NOT added to the general mapping; scoped here
# behind the SAME ``_is_generic_creature_filter`` gate a corpus scan
# confirmed is clean — every corpus hit with a generic "you"/no-subtype
# ``affected`` filter is a genuine team anthem (Biomass Mutation, Mirror
# Entity, Jolrael, Sita Varma, Dollmaker's Shop), and every non-generic hit
# is a self-referential CDA (March of the Machines, Animate Artifact) that
# ``_is_generic_creature_filter`` already excludes on ``controller``/core-
# type grounds — the ambiguity lives entirely outside this gate.
_CREATURES_MATTER_MOD_TAGS = frozenset(
    {
        "AddPower",
        "AddToughness",
        "SetPower",
        "SetToughness",
        "AddKeyword",
        "AddDynamicPower",
        "AddDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
        "GrantAbility",
        "GrantTrigger",
        # ADR-0039 W7: two more team-payoff modification tags a corpus
        # census (8 cards: Angelic Skirmisher, Linvala Shield of Sea Gate,
        # Garruk Savage Herald, ...) proved are the SAME "whole-team gets
        # an ability" shape as GrantAbility/AddKeyword, just a distinct
        # typed spelling — a CHOSEN keyword grant (Angelic Skirmisher's
        # "choose a keyword ... creatures you control gain it", CR
        # 113.10) and a granted STATIC ability specifically (Garruk's
        # "Creatures you control have '... {T}: This creature fights...'"
        # — GrantAbility grants an activated/triggered ability; a granted
        # STATIC carries its own typed tag, CR 604.1/113.10).
        "AddChosenKeyword",
        "GrantStaticAbility",
        # ADR-0039 W7: three type-changing (CR 613.4d layer 4) tags plus a
        # combat-math rewrite, each verified on its OWN card as the card's
        # OWN static (never a granted-to-a-token/opponent context, where
        # the filter's "You" would resolve to the WRONG controller —
        # Goblin Spymaster / Pursued Whale's MustAttack mode lives on an
        # OPPONENT-controlled token they grant it to, so that mode is
        # deliberately NOT added here): Biotransference ("creatures you
        # control are artifacts"), Roshan ("other creatures you control
        # are Assassins"), Maskwood Nexus ("creatures you control are
        # every creature type"), Rasaad yn Bashir ("each creature you
        # control assigns combat damage equal to its toughness" — CR
        # 510.1c-adjacent combat-damage-assignment rewrite).
        "AddType",
        "AddSubtype",
        "AddAllCreatureTypes",
        "AssignDamageFromToughness",
        # ADR-0039 W8 closer: the CHOSEN-type sibling of ``AddSubtype`` —
        # Rukarumel, Biologist's "nontoken creatures you control are the
        # chosen [creature] type in addition to their other creature
        # types" (an as-enters ``Choose`` feeding a granted subtype, CR
        # 613.4d layer 4 / 205.3) is the SAME team type-changing payoff as
        # Roshan's fixed "are Assassins", just parameterized by an earlier
        # choice instead of a literal subtype string — reached via the
        # ``Or``-wrapped ``affected`` descent (:func:`_or_wrapped_generic_
        # creature_filter`), whose OTHER branch (Sliver subtype) already
        # fails the generic gate on its own (tribal, type_matters).
        "AddChosenSubtype",
    }
)

# ADR-0039 W7: a team EVASION/UNTAP-PERMISSION static-ability MODE (phase
# encodes "can't be blocked (by X)" and "untaps during another player's
# untap step" as a MODE, never a modifications-list tag — no Add/Set/Grant
# entry exists to pair with _CREATURES_MATTER_MOD_TAGS at all) over the
# generic creature-you-control population is the SAME team-payoff shape as
# an anthem, just a different CR layer: CR 113.12 ("can't be blocked" is a
# stated quality, CR 604.3 static ability) for the evasion trio, CR 502 +
# CR 611.1 (a continuous effect modifying the untap-step rules) for the
# untap-permission mode. Keeper of Keys / Jace, Arcane Strategist / Dread
# Charge / Champion of Lambholt / Delney / Drumbellower / Quest for
# Renewal-class cards, corpus-verified (11 CantBeBlocked-family + 2
# untap-permission hits at introduction, 0 over-fire — every hit's
# ``affected`` passes the SAME no-subtype/You-controller gate).
_CREATURES_MATTER_EVASION_MODES = frozenset(
    {
        "CantBeBlocked",
        "CantBeBlockedBy",
        "CantBeBlockedExceptBy",
        "UntapsDuringEachOtherPlayersUntapStep",
    }
)

# ADR-0039 W7: local deep static-def descent — a STRICT SUPERSET of the
# shared :func:`iter_static_defs`'s field-limited walk, additionally
# following "modifications" (a GrantTrigger/GrantAbility modification
# entry nests its OWN granted trigger/ability body one level further —
# Haunted One / Centaur Chieftain / Teroh's Vanguard's granted trigger
# carrying its OWN nested static, corpus-verified 8-card recovery) and
# "definition" (Dragon Throne of Tarkir / Garruk's GrantAbility.definition
# nesting). Scoped to THIS lane only (never widening the shared
# ``iter_static_defs``, which many other lanes read and which the
# ADR-0038 landmine requires a full-corpus sibling check to widen) —
# mirrors the ``_pump_scaling_creature_filter`` / ``_creature_count_
# operand_filter`` precedent of a lane-local deep-read helper.
_CM_STATIC_DEF_CHILD_FIELDS = (
    "effect",
    "sub_ability",
    "execute",
    "mode_abilities",
    "static_abilities",
    "statics",
    "modifications",
    "definition",
    "trigger",
)


def _iter_creatures_matter_static_defs(
    root: object,
) -> Iterator[TypedMirrorNode]:
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        if _is_static_def(node):
            yield node
        for fname in _CM_STATIC_DEF_CHILD_FIELDS:
            child = getattr(node, fname, MISSING)
            if isinstance(child, TypedMirrorNode):
                stack.append(child)
            elif child is not MISSING and isinstance(child, list):
                stack.extend(child)


def _creatures_matter_condition_filter(unit_node: object) -> object | None:
    """A generic creature-you-control filter reachable from a CONDITION
    site of this unit (ADR-0039 W7) — an existence/threshold gate wrapping
    an ARBITRARY effect (Chronicler of Heroes' "if you control a creature
    with a +1/+1 counter on it, draw a card"; the Ferocious ability word
    idiom — Temur Battle Rage, Crater's Claws, Force Away). CR 603.4
    (static/triggered conditions), 608.2b (compound conditions read
    leaf-by-leaf — a deep :func:`iter_typed_nodes` scan of the whole
    condition subtree reads through And/Or/QuantityComparison/Aggregate
    wrappers alike, no per-tag switch needed).

    EXCLUDES a cost-reduction's OWN condition (``static_mode_tag ==
    "ModifyCost"``) — "this spell costs {N} less if you control a
    creature with power 4+" (Avatar of Might, Synchronized Eviction,
    Arwen's Gift, Orysa) is a narrower, DIFFERENT care (CR 601.2f) than a
    go-wide creature payoff, corpus-verified as the only 4 cards among
    117 raw hits carrying this shape — the W6 boundary worry this arm was
    built to resolve. ALSO EXCLUDES a Soulbond ``Unpaired`` predicate
    (Nearheath Pilgrim's ETB "you may pair this creature with another
    UNPAIRED creature" trigger condition, CR 702.95b) — a keyword-
    mechanic bookkeeping check for ONE specific pairing partner, not a
    population-scale care, corpus-verified as the only predicate class
    riding this shape.
    """
    if static_mode_tag(unit_node) == "ModifyCost":
        return None
    for site in iter_condition_sites(unit_node):
        for n in iter_typed_nodes(site):
            if _is_generic_creature_filter(n) and "Unpaired" not in filter_predicates(
                n
            ):
                return n
    return None


def _creatures_matter_formidable_condition(unit_node: object) -> bool:
    """A Formidable-style "Activate only if creatures you control have
    total power 8 or greater" activation restriction (ADR-0039 W8 finisher)
    — phase names this exact population check its OWN bespoke condition
    tag, ``CreaturesYouControlTotalPowerAtLeast`` (an aggregate-threshold
    node carrying only a ``minimum`` int, NOT a ``Typed`` creature filter —
    the reason :func:`_creatures_matter_condition_filter`'s
    ``_is_generic_creature_filter`` scan never reaches it), read via the
    SAME :func:`iter_condition_sites` site walk that function uses (a
    unit's own ``condition`` field plus each ``activation_restrictions``
    entry — Atarka Beastbreaker / Circle of Elders / Dragon-Scarred Bear /
    Glade Watcher wrap the tag in a ``RequiresCondition`` activation
    restriction, not a plain ``condition`` field).

    A go-wide payoff gated on the board's total power is the SAME
    CONDITION-gate shape :func:`_creatures_matter_condition_filter` already
    covers (Chronicler of Heroes / Epic Struggle, CR 603.4), just reached
    through an ACTIVATED ability's own restriction instead — "Formidable"
    itself is an ability word with no independent rules meaning (CR
    207.2c); the restriction it introduces is a plain "can't begin to
    activate a prohibited ability" gate (CR 602.5). Corpus-verified narrow:
    9 commander-legal cards carry this tag ANYWHERE (phase v0.20.0,
    2026-07-12: Atarka Beastbreaker, Atarka Pummeler, Circle of Elders,
    Crater Elemental, Dragon Whisperer, Dragon-Scarred Bear, Glade Watcher,
    Lurking Arynx, Shaman of Forgotten Ways), every one the Dragons-of-
    Tarkir Formidable cycle gating an otherwise-unrelated activated effect
    (menace grant, regenerate, base-power set, token maker, blocks-if-able,
    life-total reset) — no cost-reduction sibling exists for this tag, so
    (unlike the plain condition-filter arm) no ``ModifyCost`` guard is
    needed.
    """
    for site in iter_condition_sites(unit_node):
        for n in iter_typed_nodes(site):
            if tag_of(n) == "CreaturesYouControlTotalPowerAtLeast":
                return True
    return False


def _pump_scaling_creature_filter(node: object) -> object | None:
    """The FILTER feeding a ``Pump``/``PumpAll``/``Token`` node's scaling
    ``power``/``toughness`` operand (CR 107.3), unwrapping a ``Quantity``
    wrapper the same way :func:`_field_qty` does.

    :func:`count_operand_filter` only reads ``amount``/``count``/``value`` —
    a scaling Pump's dynamic magnitude lives on ``power``/``toughness``
    instead (Might of the Masses: ``Pump(power=Quantity(Ref(ObjectCount(
    filter=...))))``), so that shared helper never sees it. Scoped to this
    lane rather than widening the shared helper (ADR-0038 landmine: a
    shared-helper widening needs a full-corpus sibling check this lane
    doesn't have budget for). ADR-0039 W7: also accepts an ``Aggregate``
    (Max/Min) qty on the SAME power/toughness site — a created TOKEN's
    scaling P/T (Miming Slime / Kin-Tree Invocation / Tumbleweed Rising /
    Abzan Monument's "create an X/X ... token, where X is the greatest
    power/toughness among creatures you control") rides this exact field
    pair too (``Token(power=Quantity(Ref(Aggregate(...))))`` — CR 208.1),
    the token-creation sibling of :func:`_aggregate_creature_filter`'s
    amount/count/value read. This function has exactly ONE caller
    (creatures_matter's own first arm), so widening it needs no sibling
    corpus check.
    """
    for fname in ("power", "toughness"):
        v = getattr(node, fname, None)
        if isinstance(v, TypedMirrorNode) and tag_of(v) == "Quantity":
            v = getattr(v, "value", None)
        if tag_of(v) != "Ref":
            continue
        qty = getattr(v, "qty", None)
        if tag_of(qty) in ("ObjectCount", "Aggregate"):
            filt = getattr(qty, "filter", None)
            if filt is not None:
                return filt
    return None


def _creature_count_operand_filter(node: TypedMirrorNode) -> object | None:
    """A generic-creature-count operand :func:`count_operand_filter` misses:
    a ``Multiply``-scaled ``amount``/``count``/``value`` (Peach Garden Oath's
    "gain 2 life for each creature you control" — ``GainLife(amount=Multiply(
    factor=2, inner=Ref(ObjectCount(...))))``, via the shared
    :func:`ref_count_filter`), or a ``Mana`` effect's count nested one level
    deeper on ``produced`` (Circle of Dreams Druid / Battle Hymn's "Add X for
    each creature you control" — ``Mana(produced=AnyOneColor(count=Ref(
    ObjectCount(...))))``). CR 107.3.
    """
    for fname in ("amount", "count", "value"):
        filt = ref_count_filter(node, fname)
        if filt is not None:
            return filt
    produced = getattr(node, "produced", None)
    if isinstance(produced, TypedMirrorNode):
        filt = ref_count_filter(produced, "count")
        if filt is not None:
            return filt
    return None


def _aggregate_creature_filter(node: TypedMirrorNode) -> object | None:
    """A generic-creature ``Aggregate`` operand (Max/Min over Power/Toughness)
    :func:`count_operand_filter` / :func:`_creature_count_operand_filter`
    both miss: an ``amount``/``count``/``value`` ``Ref`` whose ``qty`` is an
    ``Aggregate`` (Monstrous Onslaught's "deals X damage ... where X is the
    greatest power among creatures you control", Rishkar's Expertise's "draw
    cards equal to the greatest power among creatures you control", Essence
    Harvest, Peema Aether-Seer's "get {E} equal to the greatest power among
    creatures you control") — ``Ref(qty=Aggregate(filter=Typed(controller=
    'You', type_filters=['Creature']), function='Max', property='Power'))``.
    A "greatest power AMONG creatures you control" reads the exact GENERIC
    population an anthem/count scaler does, just via a max/min reduction
    instead of a sum (CR 107.3 computed value; CR 208.1 power/toughness
    characteristic) — scoped as its OWN lane-local helper (not a widening of
    the SHARED :func:`ref_count_filter`, which many other lanes reuse and
    which the ADR-0038 landmine requires a full-corpus sibling check to
    widen) so this fix cannot perturb any other consumer. A "creature
    BLOCKING it" / "creature attacking you" Aggregate (none observed in the
    corpus at introduction — Craw Giant / Blessed Reversal's own board
    counts use plain ``ObjectCount`` with ``controller=None`` + a
    ``BlockingSource``/``Attacking`` predicate, not ``Aggregate``) would
    still fail the SAME :func:`_is_generic_creature_filter` controller=="You"
    gate the caller applies, so the boundary holds by construction even if
    such a card exists. Distinct from a CONDITION-shaped "if you control the
    creature with the greatest power" gate (Triumph of Cruelty/Ferocity) —
    that is a boolean existence check wrapping a DIFFERENT effect entirely,
    not a value operand, and is NOT read here (deferred as its own,
    un-adjudicated shape).

    The CALLER gates this helper to ``c.role == "effect"`` — a
    self-referential base-power CDA (Towering Gibbon / Dodgy Jalopy:
    "~'s power is equal to the greatest mana value among creatures you
    control", a ``SetDynamicPower`` STATIC modification, ``role ==
    "static"``) reads the SAME generic-filter Aggregate shape but computes
    the permanent's OWN characteristic (CR 613.4b), not a payoff distributed
    to the team — corpus-verified regression at introduction (2 cw_only
    over-fires) fixed by the role gate, mirroring the team-anthem arm's own
    self-referential-CDA exclusion (this docstring, two paragraphs up) for
    the STATIC-role shape the affected-filter check alone cannot reach here.
    """
    # announced_x: phase v0.25.0's announce-locked-X channel moves the
    # computed operand off ``amount`` (now a bare Variable Ref) onto its
    # own field (Monstrous Onslaught at the v0.35.2 pin).
    for fname in ("amount", "count", "value", "announced_x"):
        q = getattr(node, fname, None)
        if isinstance(q, TypedMirrorNode) and tag_of(q) == "Ref":
            qty = getattr(q, "qty", None)
            if tag_of(qty) == "Aggregate":
                filt = getattr(qty, "filter", None)
                if filt is not None:
                    return filt
    return None


def _creatures_matter_wrapped_count_filter(node: TypedMirrorNode) -> object | None:
    """A generic-creature ``ObjectCount``/``Aggregate`` operand hiding behind
    a field ``count_operand_filter``/:func:`_creature_count_operand_filter`/
    :func:`_aggregate_creature_filter` all miss because it isn't named
    ``amount``/``count``/``value`` (ADR-0039 W8 closer, CR 107.3): a
    ``quantity`` field (Fettergeist's ``ManaDynamic(quantity=Ref(ObjectCount(
    Typed(You,Another,Creature))))`` ramp trigger, Protect the Negotiators'
    equivalent), an ``amount_dynamic`` field (Shield of the Avatar's
    ``PreventDamage(amount_dynamic=Ref(ObjectCount(Typed(You,no-subtype,
    Creature))))``), or a nested ``UpTo.max`` inside ``count`` (Harvest
    Season's ``SearchLibrary(count=UpTo(max=Ref(ObjectCount(Typed(You,
    Tapped,Creature)))))``).

    EXCLUDES a ``Sacrifice`` node's identical ``count.max`` wrapper —
    Devour's own "as this creature enters, you may sacrifice any number of
    creatures" replacement cost (CR 702.82a) rides the SAME field-wrapper
    shape but is a DIFFERENT, self-consuming population (the creatures
    sacrificed, not the team), already adjudicated as a shed
    (``DEVOUR_KEYWORD_NO_QTY_NODE``, ADR-0038 W6 Bloodspore Thrinax pin) —
    corpus-verified node-shape distinction (not a keyword check): every
    genuine member's wrapper lives on ``SearchLibrary``/``ManaDynamic``/
    ``PreventDamage``, every Devour hit's on ``Sacrifice``, so gating on the
    node's own tag is exact and needs no keyword thread. 22 of 27 corpus
    hits for this wrapper shape are Devour riding this exact gap, so the
    exclusion is load-bearing — see
    ``/Users/danblanchard/.claude/jobs/097c2256/tmp/w8_creatures_reclass/
    family_map.json``'s WRAPPED_COUNT_FIELD family for the full census.
    """
    if tag_of(node) == "Sacrifice":
        return None
    for fname in ("quantity", "amount_dynamic"):
        v = getattr(node, fname, None)
        if isinstance(v, TypedMirrorNode) and tag_of(v) == "Ref":
            qty = getattr(v, "qty", None)
            if tag_of(qty) in ("ObjectCount", "Aggregate"):
                filt = getattr(qty, "filter", None)
                if filt is not None:
                    return filt
    cnt = getattr(node, "count", None)
    if isinstance(cnt, TypedMirrorNode) and tag_of(cnt) == "UpTo":
        mx = getattr(cnt, "max", None)
        if isinstance(mx, TypedMirrorNode) and tag_of(mx) == "Ref":
            qty = getattr(mx, "qty", None)
            if tag_of(qty) in ("ObjectCount", "Aggregate"):
                filt = getattr(qty, "filter", None)
                if filt is not None:
                    return filt
    return None


def _creatures_matter_scaled_target_filter(unit_node: object) -> object | None:
    """The ``target`` filter of a ``DoublePTAll``/``PutCounterAll`` node
    reachable anywhere in one unit's tree (ADR-0039 W8 closer) — the SAME
    fixed-team-pump/counter-grant shape :data:`_CREATURES_MATTER_MOD_TAGS`'s
    ``PumpAll``/``AddKeyword`` siblings already cover, just a DIFFERENT
    typed spelling phase reserves for a MULTIPLIER (``DoublePTAll`` —
    Unnatural Growth / Double Trouble / God-Eternal Rhonas / Zopandrel,
    Hunger Dominus / Roar of Endless Song's "creatures you control get
    double their power" — CR 107.3 fixed multiplier of a computed value,
    613.4c layer-7 P/T) or a mass counter GRANT (``PutCounterAll`` — Ajani
    Goldmane's "put a +1/+1 counter on each creature you control", Song of
    Eärendil's "each creature you control without flying gets a flying
    counter on it" — CR 121.1/122.1 counters, 613.4c). ``counter_type`` is
    NOT restricted to ``P1P1`` (Song of Eärendil's is a ``flying`` keyword
    counter, CR 702.x) — matches the existing philosophy of accepting any
    ``AddKeyword``/``GrantAbility`` team payoff regardless of which specific
    ability it grants.

    :func:`iter_typed_nodes` (the FULLY GENERIC deep walk, no curated field
    list) over the WHOLE unit finds these regardless of which container
    field nests them — God-Eternal Rhonas wraps its ``DoublePTAll`` inside
    the SAME ``GenericEffect.static_abilities`` shape a granted trample
    modification uses elsewhere, and a trigger-origin unit (Unnatural
    Growth, Song of Eärendil) carries it directly. This function has
    exactly ONE caller (creatures_matter's own arm), so a full-unit walk
    needs no sibling corpus check (ADR-0038 landmine).
    """
    for n in iter_typed_nodes(unit_node):
        if tag_of(n) in ("DoublePTAll", "PutCounterAll"):
            filt = getattr(n, "target", None)
            if filt is not None:
                return filt
    return None


def _mass_untap_creature_filter(unit: object) -> object | None:
    """The TARGET filter of a mass (``scope == 'All'``) Untap ``SetTapState``
    reachable from one unit's node, threaded through the same
    effect/sub_ability/execute/branches/mode_abilities/GrantTrigger chain
    :func:`has_structural_untap_engine` walks (:func:`_iter_untap_targets`).
    "Untap ALL creatures you control" (Vitalize, Aurelia's attack trigger,
    Reins of Power's own-side clause, Ahn-Crop Champion / Combat Celebrant's
    exert-untap of "all OTHER creatures you control" — the ``Another``
    filter property lives outside ``type_filters``/subtypes so it doesn't
    perturb :func:`_is_generic_creature_filter`'s read) is a board-wide
    pseudo-vigilance payoff over the GENERIC creature population, same shape
    as a team anthem — CR 701.26/701.26b. A SINGLE-target untap ("untap
    target creature you control") never reaches here: the mass gate
    (``scope == 'All'``) is load-bearing, mirroring the OLD-IR's own
    ``counter_kind == "all"`` tell (:mod:`_card_ir.project`'s
    ``settapstate`` projection comment — "the `scope` rides in counter_kind
    so a MASS untap ... is distinguishable from a single-target untap").
    """
    for target, node in _iter_untap_targets(unit):
        if tag_of(getattr(node, "scope", None)) == "All":
            return target
    return None


def _creatures_matter_flip_coin_win_filter(node: object) -> object | None:
    """A generic-creature count operand nested inside a ``FlipCoin`` node's
    OWN win/lose branch (ADR-0039 W8 finisher) — Goblin Lyre's "If you win
    the flip, ~ deals damage to target opponent or planeswalker equal to
    the number of creatures you control": the branch's own
    ``DealDamage.amount`` is a fully typed ``Ref(qty=ObjectCount(filter=
    Typed[You, Creature]))`` (CR 107.3), but :meth:`ConceptTree.
    iter_concepts` decorates only the OUTER ``FlipCoin`` node as a concept
    — the win/lose sub-effects never get their own concept entry — so the
    main loop's :func:`count_operand_filter` check (called on the FlipCoin
    node itself, which has no ``amount``/``count``/``value`` field of its
    own) never reaches it. A tiny container descent, not a bridge: the
    data is already fully typed, the crosswalk just wasn't looking one
    field deeper. Corpus-verified sole hit (phase v0.20.0, 2026-07-12):
    the ONLY ``FlipCoin`` card corpus-wide whose win OR lose branch
    carries a generic creature-count operand — this function has exactly
    ONE caller (creatures_matter's own arm), so widening it needs no
    sibling corpus check (the ADR-0038 landmine).
    """
    if tag_of(node) != "FlipCoin":
        return None
    for branch_name in ("win_effect", "lose_effect"):
        branch = getattr(node, branch_name, None)
        eff = getattr(branch, "effect", None) if branch is not None else None
        if eff is None:
            continue
        filt = count_operand_filter(eff)
        if filt is not None:
            return filt
    return None


def _creatures_matter_cmc_property_count_filter(node: object) -> object | None:
    """A generic-creature count operand nested inside a target filter's OWN
    ``Cmc`` property (ADR-0039 W8 finisher) — Unforgiving One's "return
    target creature card with mana value X or less from your graveyard to
    the battlefield, where X is the number of MODIFIED CREATURES YOU
    CONTROL": the reanimation ``ChangeZone.target`` is a ``Typed`` filter
    whose ``properties`` list carries a ``Cmc(comparator='LE', value=Ref(
    qty=ObjectCount(filter=Typed[You, Modified, Creature])))`` — a fully
    typed count operand, just nested one level deeper than the top-level
    ``amount``/``count``/``value`` fields :func:`count_operand_filter`
    reads (CR 107.3 computed value; a "modified creatures" population is
    still a generic "creatures you control" filter per
    :func:`_is_generic_creature_filter` — a boolean-property gate, the
    SAME shape the Ferocious power-threshold idiom already accepts, not a
    subtype/zone restriction). Corpus-verified narrow: 2 commander-legal
    cards carry this exact nested shape (phase v0.20.0, 2026-07-12:
    Unforgiving One, Kinscaer Sentry — a beyond-legacy gain, corpus-
    verified genuine, not adjudicated separately since it shares the
    identical typed shape).
    """
    filt = getattr(node, "target", None)
    if tag_of(filt) != "Typed":
        return None
    for prop in getattr(filt, "properties", None) or ():
        if tag_of(prop) != "Cmc":
            continue
        val = getattr(prop, "value", None)
        if tag_of(val) != "Ref":
            continue
        qty = getattr(val, "qty", None)
        if tag_of(qty) != "ObjectCount":
            continue
        inner = getattr(qty, "filter", None)
        if inner is not None:
            return inner
    return None


def _creatures_matter(tree: ConceptTree) -> list[Signal]:
    """creatures_matter — a go-wide payoff scaling with / antheming the GENERIC
    creature population you control (CR 604.1 static ability; CR 611.1 the
    continuous effect it or a resolving spell generates). Mirrors the deleted
    legacy IR engine's line ~7686. ADR-0038 W4 giant-key batch widened the arm
    from two shapes to five; ADR-0038 W5 tails added a sixth and widened the
    team-anthem mod-tag set; ADR-0038 W6 endgame added the ``Aggregate``
    (Max/Min) count-operand shape below, all sharing the SAME
    :func:`_is_generic_creature_filter` gate:

    * a **count operand** that is a generic creature count (Craterhoof's +X/+X, a
      "for each creature you control" value) — the standard ``amount``/``count``/
      ``value`` site (:func:`count_operand_filter`), a ``Multiply``-scaled or
      ``Mana``-nested count site (:func:`_creature_count_operand_filter` — Peach
      Garden Oath's lifegain, Circle of Dreams Druid / Battle Hymn's ramp), an
      ``Aggregate`` (Max/Min Power/Toughness) site (:func:`_aggregate_creature_filter`
      — Monstrous Onslaught / Rishkar's Expertise / Essence Harvest / Peema
      Aether-Seer's "the greatest power among creatures you control" — CR 208.1),
      or a scaling ``Pump``/``PumpAll``'s ``power``/``toughness`` site (Might of
      the Masses — :func:`_pump_scaling_creature_filter`), all CR 107.3 / 613.4c;
    * a **team anthem** — a pump / set-P/T / keyword-or-ability-grant static-
      ability DEF over the generic own-board creature set (Intangible-Virtue-
      class continuous team buff), read via :func:`iter_static_defs` so a
      top-level ``static``-origin unit (the DEF is the unit's own node) and a
      ONE-SHOT ``GenericEffect``-nested or ``CreateEmblem``-nested DEF
      (Overrun's granted "until end of turn" trample, Capitoline Triad's
      emblem, Lightning Volley's granted ability, Biomass Mutation's
      ``SetPowerDynamic``/``SetToughnessDynamic`` base-P/T rewrite — CR
      611.2c "the set of objects [a resolving effect] affects is determined
      when that continuous effect begins", 613.4b, 113.10 ability-grant)
      share one arm;
    * a **fixed team pump spell/trigger** — a plain (non-``GenericEffect``-
      wrapped) ``PumpAll`` role=effect over the generic filter (Warrior's Honor,
      Fortify: "Creatures you control get +N/+N until end of turn" IS the whole
      effect, no nested static def to descend into — CR 611.2c/613.4c);
    * a **mass untap** — "untap all creatures you control"
      (:func:`_mass_untap_creature_filter` — Vitalize, Aurelia, the
      Warleader's attack trigger, Ahn-Crop Champion's exert-untap of "all
      OTHER creatures you control" — CR 701.26/701.26b), the board-wide
      pseudo-vigilance sibling of a team anthem.

    A SUBTYPE filter (Goblin King's "other Goblins") fails the no-subtype gate (it is
    ``type_matters``). A single-target removal/buff (controller any) never reaches
    here. A SYMMETRIC "on the battlefield" count (Blasphemous Act's per-creature
    cost reduction, Coat of Arms' shared-type count) fails the "You" controller
    gate — a genuinely different, broader population than "creatures you control"
    (:func:`_is_generic_creature_filter`'s own controller=="You" gate; ADR-0038
    boundary lesson (ii): never fold two inherently different properties into one
    lane). A "creatures BLOCKING it" / "creatures attacking you" count (Rampage,
    Blessed Reversal) fails the same gate for the same reason — a different
    subject, not "creatures you control". The LOW regex floor (token-maker,
    Devour's sacrifice count → creatures_matter) stays a ``live_only`` mirror,
    not ported (ADR-0038 W4: corpus-verified — legacy's floor is a bare
    "creature" mention count, not a structural cares-about read).

    ADR-0039 W7 BRIDGES wave added three more shapes, all corpus-verified
    against a live re-measure and sharing the SAME gate philosophy:

    * a **buried team anthem** — the team-anthem descent above now walks
      :func:`_iter_creatures_matter_static_defs` (a STRICT SUPERSET of
      :func:`iter_static_defs`'s reach, additionally following a
      modification entry's OWN ``modifications``/``definition`` nesting —
      Haunted One / Centaur Chieftain / Teroh's Vanguard's granted
      TRIGGER carrying its own nested static def, Dragon Throne of
      Tarkir / Garruk's ``GrantAbility.definition`` nesting) plus two
      widened mod tags (:data:`_CREATURES_MATTER_MOD_TAGS` — see that
      constant's own docstring);
    * a **team evasion/untap-permission static MODE** — "creatures you
      control can't be blocked (this turn)" / "... can't be blocked by
      creatures with power 3+" / "untap all creatures you control during
      each other player's untap step" (Keeper of Keys, Jace Arcane
      Strategist's ultimate, Dread Charge, Delney, Drumbellower) rides a
      bare ``mode`` with NO modifications-list entry at all (see
      :data:`_CREATURES_MATTER_EVASION_MODES`'s own docstring) — the SAME
      team-payoff shape as an anthem, just a different CR layer;
    * a **CONDITION-gate arbitrary payoff** — a boolean existence/
      threshold gate over the generic population wrapping an otherwise
      UNRELATED effect (:func:`_creatures_matter_condition_filter` —
      Chronicler of Heroes / the Ferocious ability word / Epic Struggle's
      "if you control twenty or more creatures, you win"), excluding a
      cost-reduction's own condition (that function's own docstring).

    ADR-0039 W8 reclassification (RECLASSIFY + ADJUDICATE ONLY — no new
    arm that session): a full :func:`iter_typed_nodes` corpus re-walk
    (no curated field list, so no node path is missed) over the WHOLE
    live_only=2404 set found the W7 "162 heterogeneous" residue
    collapses to 30 once every node path is actually read — the other
    132 were already-adjudicated shed shapes (token-maker/blocking-
    attacking/symmetric/devour/tribal) a field-limited scan simply
    missed, producing an exact family map (/Users/danblanchard/.claude/
    jobs/097c2256/tmp/w8_creatures_reclass/family_map.json).

    ADR-0039 W8 CLOSER wave landed four of that map's true-gap families,
    all sharing the SAME :func:`_is_generic_creature_filter` gate:

    * a **mass P/T multiplier and mass counter grant** — ``DoublePTAll``
      (Unnatural Growth / Double Trouble / God-Eternal Rhonas / Zopandrel,
      Hunger Dominus / Roar of Endless Song's "creatures you control get
      double their power" — CR 107.3/613.4c) and ``PutCounterAll`` (Ajani
      Goldmane's mass +1/+1 counter, Song of Eärendil's mass flying
      counter — CR 121.1/122.1) are DIFFERENT typed spellings of the SAME
      fixed-team-pump/counter-grant shape :func:`_pump_scaling_creature_
      filter`/:data:`_CREATURES_MATTER_MOD_TAGS` already cover, read via
      :func:`_creatures_matter_scaled_target_filter`'s full-unit
      :func:`iter_typed_nodes` walk;
    * a **count operand behind an unread field wrapper** — ``quantity``
      (Fettergeist / Protect the Negotiators' ramp), ``amount_dynamic``
      (Shield of the Avatar's damage prevention), or ``UpTo.max`` nested
      inside ``count`` (Harvest Season's search) — CR 107.3, read via
      :func:`_creatures_matter_wrapped_count_filter`, which EXCLUDES a
      ``Sacrifice`` node's identical wrapper (Devour's own sacrifice
      count, already an adjudicated shed — see that function's own
      docstring for the corpus-verified node-shape distinction);
    * an **``Or``-wrapped team-anthem ``affected`` filter** — a static
      ability's scope can name multiple qualifying object types
      disjunctively (CR 604.3 — Silkguard's "Auras, Equipment, and
      modified creatures you control gain hexproof"), read via
      :func:`_or_wrapped_generic_creature_filter`'s one-level Or/And
      descent, scoped ONLY to the team-anthem arm's ``affected`` field
      (never a spell/ability ``target`` field, which is TARGET context —
      CR 115.1 — not population context, the Divine Resilience/Emergency
      Weld precedent; see that helper's own docstring for the full
      per-member family accounting), plus one new team-payoff mod tag
      (``AddChosenSubtype`` — Rukarumel, Biologist's chosen-type grant,
      the parameterized sibling of ``AddSubtype``).

    Corpus-verified 43 genuine members closed (5 DoublePTAll + 22
    PutCounterAll + 5 genuine WRAPPED_COUNT_FIELD + 11 Or-wrapped, one of
    which — Rukarumel — needed the mod-tag addition to fire).

    ADR-0039 W8 FINISHER (2026-07-12) — PROMOTED. A per-card node-path
    classifier bucketed the whole live_only set into six ADJUDICATED SHED
    classes (token-maker cross-open / symmetric-any-controller /
    blocking-or-attacking / subtype-tribal-you / devour / tribal-shares-
    quality, all W4-W7 established) plus one final 53-card true-gap tail,
    fully adjudicated per-card this session:

    * a **Formidable activation-restriction condition**
      (:func:`_creatures_matter_formidable_condition`) — phase's OWN
      bespoke ``CreaturesYouControlTotalPowerAtLeast`` condition tag
      (reached via :func:`iter_condition_sites`, the SAME site walk
      :func:`_creatures_matter_condition_filter` uses) — CR 602.5 ("a
      player can't begin to activate an ability that's prohibited from
      being activated"); "Formidable" itself is an ability word with no
      independent rules meaning (CR 207.2c);
    * a **FlipCoin win-branch count operand**
      (:func:`_creatures_matter_flip_coin_win_filter`) — a fully typed
      ``DealDamage.amount`` one field deeper than
      :meth:`ConceptTree.iter_concepts` decorates (Goblin Lyre, CR
      107.3);
    * a **reanimation target filter's nested Cmc-property count operand**
      (:func:`_creatures_matter_cmc_property_count_filter`) — "return
      target creature card with mana value X or less ..., where X is the
      number of MODIFIED CREATURES YOU CONTROL" (Unforgiving One, CR
      107.3 — a "modified creatures" population reads as generic the
      same way a power-threshold filter does).

    Five ADR-0039 ledgered bridges (bridge_ledger.py, the
    ``creatures_matter`` section) close the residual dropped-clause /
    mis-scoped-grant tail — Lightning Runner's absence-proof "untap all
    creatures you control" (CR 701.26), Duskana's dropped per-base-2/2
    draw count, Moku's mis-scoped SelfRef haste grant, Siege Behemoth's
    empty-modifications static, and Candlekeep Inspiration's mass
    base-P/T-setter residue (sharing its gap/match with the
    ``base_pt_set`` sibling row, CR 613.4b).

    ADR-0039 task #82 (post-deletion grammar sprint) retired three
    grammar-straggler bridges into a typed ``tree_synthesis`` sweep row
    (the "creatures_matter grammar-sprint stragglers" section in
    ``tree_synthesis.py``) instead — Superior Numbers' excess-count
    comparator (CR 107.3), Sovereign Okinec Ahau's per-creature counter
    distribution (CR 122.1/613.4b), and Whisperwood Elemental's face-up
    team-grant residue (CR 113.10/702.164). Same three pins, now firing
    via ``synth_creatures_matter_excess_count`` /
    ``synth_creatures_matter_diff_counters`` /
    ``synth_creatures_matter_faceup_grant`` above instead of a bridge.

    The remaining true residue stays an adjudicated shed, NOT ported —
    cost-reduction's OWN dynamic/scaled condition (CR 601.2f, the Avatar
    of Might boundary — Arwen's Gift / Boseiju / Ghalta / Khalni Hydra /
    Mirror of Galadriel / Mobilized District / Orysa / Spectral Denial /
    Takenuma / Temur Battlecrier / The Pride of Hull Clade / Towashi
    Guide-Bot / Walking Skyscraper); self-CDA / self-only scaling (CR
    604.3/613.4a-c, the Towering Gibbon precedent — Ancient Ooze, Carrion
    Grub, Moon-Vigil Adherents); graveyard-zone population (CR 400.2, the
    Wire Surgeons/Kathril precedent — Crypt of Agadeem); chosen-type-
    restricted population (CR 205.3 tribal philosophy, contrast Rukarumel
    where the chosen type is GRANTED to a generic population rather than
    restricting what's COUNTED — Kindred Charge); the pre-existing
    target-context (Divine Resilience) and you-pay-tax (Fettergeist)
    sheds; and the token-maker cross-open class's own dropped/
    Unimplemented-token-node subset (CR 111.1/111.2, 18 members — legacy
    fires on ITS OWN token-maker cross-open regardless of what this
    tree's token node contains). Landfall rule met: both 1421 -> 1440,
    live_only 2373 -> 2354, cw_only=281 unchanged — every remaining
    live_only member decomposes into one of the shed classes above (a
    per-card classifier re-walk confirmed zero unexplained residue). See
    ``test_creatures_matter_w8_finisher_batch`` for every pin.
    """
    for c in tree.iter_concepts():
        if (
            _is_generic_creature_filter(count_operand_filter(c.node))
            or _is_generic_creature_filter(_pump_scaling_creature_filter(c.node))
            or _is_generic_creature_filter(_creature_count_operand_filter(c.node))
            or _is_generic_creature_filter(
                _creatures_matter_wrapped_count_filter(c.node)
            )
            or _is_generic_creature_filter(
                _creatures_matter_flip_coin_win_filter(c.node)
            )
            or _is_generic_creature_filter(
                _creatures_matter_cmc_property_count_filter(c.node)
            )
            or (
                c.role == "effect"
                and _is_generic_creature_filter(_aggregate_creature_filter(c.node))
            )
        ):
            return [Signal("creatures_matter", "you", "", c.raw, tree.name, "high")]
    # announced_x (phase v0.25.0's announce-locked-X channel, CR 601.2b /
    # 602.2b): the computed operand moves off the EFFECT node's ``amount``
    # (now a bare Variable Ref) onto the owning cast/activation WRAPPER's
    # own ``announced_x`` field (Monstrous Onslaught's "where X is the
    # greatest power among creatures you control AS YOU CAST THIS SPELL" at
    # the v0.35.2 pin) — a field position no effect-node concept walk
    # reaches. Ability-origin units only: a static's CDA never carries an
    # announced X, so the Towering Gibbon role-gate concern doesn't arise.
    for unit in tree.units:
        if unit.origin != "ability":
            continue
        for n in iter_typed_nodes(unit.node):
            q = getattr(n, "announced_x", None)
            if tag_of(q) != "Ref":
                continue
            qty = getattr(q, "qty", None)
            if tag_of(qty) in ("ObjectCount", "Aggregate") and (
                _is_generic_creature_filter(getattr(qty, "filter", None))
            ):
                return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        for sdef in _iter_creatures_matter_static_defs(unit.node):
            if (
                _or_wrapped_generic_creature_filter(getattr(sdef, "affected", None))
                is None
            ):
                continue
            mods = getattr(sdef, "modifications", None) or ()
            if any(tag_of(m) in _CREATURES_MATTER_MOD_TAGS for m in mods):
                return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
            if static_mode_tag(sdef) in _CREATURES_MATTER_EVASION_MODES:
                return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    for c in tree.effect_concepts("pump"):
        if tag_of(c.node) == "PumpAll" and _is_generic_creature_filter(
            effect_filter(c.node)
        ):
            return [Signal("creatures_matter", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if _is_generic_creature_filter(_mass_untap_creature_filter(unit.node)):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
        if _is_generic_creature_filter(
            _creatures_matter_scaled_target_filter(unit.node)
        ):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if _creatures_matter_condition_filter(unit.node) is not None:
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
        if _creatures_matter_formidable_condition(unit.node):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    # ADR-0039 task #82 grammar sprint: three former ledgered bridges
    # (Superior Numbers' excess-count comparator, Sovereign Okinec Ahau's
    # per-creature counter difference, Whisperwood Elemental's face-up
    # team-grant) now read a bucket-B ``tree_synthesis`` sweep row instead
    # of a text-anchored bridge — see the "creatures_matter grammar-sprint
    # stragglers" section in ``tree_synthesis.py`` for the CR citations +
    # node-shape rationale. Retired from bridge_ledger.py; the membership
    # is unchanged (same three pins, now firing structurally).
    for c in tree.iter_concepts():
        if c.concept in (
            "synth_creatures_matter_excess_count",
            "synth_creatures_matter_diff_counters",
            "synth_creatures_matter_faceup_grant",
        ):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    # ADR-0039 W8 finisher — the last of the 53-card true-gap tail:
    # ledgered bridges (bridge_ledger.py, docstring there for the full
    # corpus accounting).
    for bridge_id in (
        "lightning_runner_untap_all_dropped",
        "duskana_draw_per_base_pt_creature_dropped",
        "moku_haste_grant_misscoped_selfref",
        "siege_behemoth_unblocked_assign_empty_mods",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    # ADR-0039 task #82 grammar sprint: Candlekeep Inspiration's mass
    # "creatures you control have base power and toughness X/X, where X
    # is ..." idiom (CR 613.4b) — a go-wide team base-P/T setter is a
    # creatures_matter payoff too. Graduated off the
    # ``candlekeep_inspiration_mass_where_x_creatures_matter`` ledgered-
    # bridge row: shares the SAME tree_synthesis.py arm
    # (``base_pt_mass_where_x``) the ``_base_pt_set`` lane reads, keyed
    # off that arm's id specifically so this never widens to the sibling
    # single-target base_pt_set arms (have_become / is_a_type_with).
    for c in tree.effect_concepts("base_pt_set"):
        if (
            isinstance(c.node, SynthesizedNode)
            and c.node.arm_id == "base_pt_mass_where_x"
        ):
            return [Signal("creatures_matter", "you", "", "", tree.name, "high")]
    return []


# Modification tags that mirror the pump / grant_keyword / set_pt CONCEPTS
# ``_MOD_CONCEPTS`` (``crosswalk.py``) decorates a static-ability def's
# ``modifications`` into — the ADD_TYPE tag is deliberately excluded (a
# different concept, not a go-wide anthem shape).
_TYPE_MATTERS_GOWIDE_MOD_TAGS: frozenset[str] = frozenset(
    {"AddPower", "AddToughness", "AddKeyword", "SetPower", "SetToughness"}
)

# ADR-0038 W5 tails: the combat-keyword block legacy's ``_IR_KEYWORD_MAP``
# routes straight to ``attack_matters`` (battle cry / battalion / melee /
# exert / bushido / annihilator / flanking / frenzy — CR 702.91/702.44/
# 702.121/701.43/702.45/702.86/702.25/702.68, each verified via
# rules-lookup this session), read here as an independent go-wide tell:
# the crosswalk's OWN ``attack_matters`` lane is a structural trigger/
# count read (CR 508) that never reaches for the bare PRINTED keyword, so
# it stays absent from ``out_keys`` for a vanilla keyword body (Ahn-Crop
# Crasher, Glory-Bound Initiate) even though legacy opens go-wide on the
# keyword alone (each keyword's own reminder text carries an attack
# condition phase never structuralizes into a Typed filter).
# Deliberately EXCLUDES ``rampage`` (CR 702.23) — it is NOT in legacy's
# own ``_IR_KEYWORD_MAP`` either; every Rampage-only live_only card's
# legacy firing traces to a SYNTHETIC old-IR artifact, not this keyword
# route (see :func:`_type_matters_go_wide`'s docstring for the full
# adjudication). Verified this session: phase's Rampage trigger carries a
# ``BlockingSource`` Typed filter with ``controller=None``, never "You".
_TYPE_MATTERS_GOWIDE_KEYWORDS: frozenset[str] = frozenset(
    {
        "battle cry",
        "battalion",
        "melee",
        "exert",
        "bushido",
        "annihilator",
        "flanking",
        "frenzy",
    }
)


def _type_matters_go_wide(
    tree: ConceptTree,
    keywords: frozenset[str] = frozenset(),
    vocab: frozenset[str] = CREATURE_SUBTYPES,
) -> bool:
    """Is this card ALSO a generic (non-tribal) creatures payoff, so a CLASS
    tribe (Warrior/Cleric/... — ``CLASS_TRIBES``) is worth noting alongside a
    RACE tribe (CR 205.3)? The class-tribe MEMBERSHIP floor's go-wide gate
    (the b14 §1 arm C reconciliation in ``extract_crosswalk_signals``) — FIVE
    STRUCTURAL, CR-grounded arms:

    (i) ``creatures_matter`` / ``attack_matters`` / ``anthem_static`` fire
    STRUCTURALLY — calling each lane function directly (:func:`_creatures_
    matter` / :func:`_attack_tapped_matters` / :func:`_anthem_static`), NOT
    an ``out_keys`` intersection (all three are now PORTED, so ``add()``
    would otherwise dedupe a same-ident re-firing rather than skip it — a
    direct call is the honest read either way);
    (ii) a creature-type TOKEN MAKER (a captured kindred subject —
    :func:`_floor_token_maker_subjects`, the SAME structural-plus-raw-mirror
    read the membership floor's own token-maker cross-open uses, ADR-0039
    task #80 step 3 — widened past the bare
    :func:`structural_token_maker_type_subjects` so a directed / under-typed
    maker phase leaves ``Unimplemented`` still opens go-wide: Kalitas,
    Bloodchief of Ghet's variable-P/T "create a black Vampire creature
    token", Daxos the Returned's "create a...Spirit...token" — both
    corpus-verified regressions found via the full commander-legal re-measure
    this session, closed by reusing the floor's own widened reader instead of
    the un-widened structural predicate directly): Krenko/Bear's Companion/
    Talrand-class — a typed-creature-token engine is itself a go-wide
    creature payoff (mirrors legacy's line ~11394 "token-maker →
    creatures_matter" cross-open, the LOW-conf arm the ported
    ``_creatures_matter`` lane deliberately excludes — ADR-0038 W4);
    (iii) a **count operand** that is a generic creature count (Circle of
    Dreams Druid's "Add {G} for each creature you control") — mirrors
    ``_creatures_matter``'s own first arm exactly, applied here unfiltered
    by ``keys`` (ADR-0038 W4);
    (iv) a pump / grant_keyword / set_pt static-ability DEF
    (:func:`iter_static_defs` — reaches a temporary "until end of turn"
    static a TRIGGER's own effect confers, e.g. Gempalm Sorcerer's cycling
    anthem, not just a top-level continuous ability) whose ``affected`` is
    the GENERIC (no-subtype) own-board creature filter — Raff, Weatherlight
    Stalwart's granted pump; Selesnya Guildmage's activated-cost team pump;
    Leonin Armorguard's ETB pump — origin-agnostic, unlike
    ``_creatures_matter``'s own ``unit.statics``-only scan (ADR-0038 W4);
    (v) ADR-0038 W5 tails — a combat KEYWORD tell
    (:data:`_TYPE_MATTERS_GOWIDE_KEYWORDS` — battle cry / battalion / melee /
    exert / bushido / annihilator / flanking / frenzy, CR 702.91/702.44/
    702.121/701.43/702.45/702.86/702.25/702.68): each carries its own attack
    condition in stripped reminder text that never structuralizes into a
    Typed filter at all (a bare "you may exert this creature as it attacks"
    has no board-state reference to read — arm (iii)/(iv) can't reach it),
    so the printed keyword is the only anchor (mirrors legacy's
    ``_IR_KEYWORD_MAP`` combat block, which routes the SAME keyword set
    straight to ``attack_matters`` — Ahn-Crop Crasher, Glory-Bound
    Initiate). Rampage is deliberately EXCLUDED from this table (unlike
    the 8 keywords above, it is NOT in legacy's ``_IR_KEYWORD_MAP`` either).

    ADR-0039 task #80 step 3 (deletion phase) DROPPED the former arm (vi) —
    a FLOOR-exact reproduction of legacy's OWN go-wide computation via a
    direct call to the deleted ``extract_signals_ir`` on the OLD projected ``Card``.
    That arm existed ONLY to catch a tail old-IR's supplement fabricates a
    SYNTHETIC "static board_count" ability for (subject/amount = a bare
    ``Filter(Creature, controller="you")``) whenever the oracle carries ANY
    own-board count/condition operand phase's raw parse exposes, REGARDLESS
    of the real population — Rampage's "for each creature blocking it" (CR
    702.23), Devour's sacrifice count (CR 702.82), Formidable-style
    total-power conditions, tapped-creature-count conditions, and a nested
    "when you do" mass-untap consequence all traced to this ONE hallucination
    (verified: Elvish Berserker's Rampage trigger's REAL phase filter carries
    ``BlockingSource`` with ``controller=None``, never "You" — old-IR
    fabricates the "you" scope anyway). This is the EXACT same artifact
    :func:`_creatures_matter`'s own docstring already adjudicates as a
    ``live_only`` shed for the standalone ``creatures_matter`` key (not
    ported), and ``test_type_matters_go_wide_rampage_shed_not_ported``
    already pins the identical adjudication one layer up (Elvish Berserker's
    RACE tribe Elf surfaces unconditionally; its CLASS tribe Berserker must
    NOT) — so reproducing the hallucination here, just for the include_
    membership=True commander path, would have been internally inconsistent
    with that precedent. Dropping it removes the LAST ``old_ir_for`` read
    from this gate; the deck-forge cutover gate's cascade-allowance
    (``test_membership_floor_reproduced_in_flag_on_commander``) already
    tolerates a crosswalk go_wide narrower than legacy's for exactly this
    reason. LOW confidence throughout — this never upgrades a genuine HIGH
    Arm-B subject read (:func:`structural_type_subjects`). CR 205.3/604.3.
    """
    if (
        _creatures_matter(tree)
        or any(s.key == "attack_matters" for s in _attack_tapped_matters(tree))
        or _anthem_static(tree)
    ):
        return True
    if _floor_token_maker_subjects(tree, vocab):
        return True
    for c in tree.iter_concepts():
        if _is_generic_creature_filter(count_operand_filter(c.node)):
            return True
    for unit in tree.units:
        for static_def in iter_static_defs(unit.node):
            mods = getattr(static_def, "modifications", None) or []
            if not any(tag_of(m) in _TYPE_MATTERS_GOWIDE_MOD_TAGS for m in mods):
                continue
            if _is_generic_creature_filter(getattr(static_def, "affected", None)):
                return True
    return bool({k.lower() for k in keywords} & _TYPE_MATTERS_GOWIDE_KEYWORDS)


def _attack_tapped_matters(tree: ConceptTree) -> list[Signal]:
    """attack_matters / tapped_matters — a combat-state payoff over YOUR creatures
    (CR 508 attacking / 301 tapped). Tier-1 structural reads (ADR-0036 fold — the
    ``_ATTACK_MATTERS_MIRROR`` is deleted):

    * an offensive attack-declaration trigger (:func:`has_attack_trigger` — the typed
      compound-event set, CR 508.1a).
    * a positive Raid condition (:func:`attack_raid_condition` — "if you attacked this
      turn", CR 508.1a/508.4).
    * an effect over YOUR ``Attacking`` / ``Tapped`` creatures ("attacking creatures
      you control get +1/+0"; "for each tapped creature you control"). The controller
      gate is load-bearing — "destroy target attacking creature" (controller any) is
      removal, not an aggro lane. Tapped is creature-gated.
    * a static anthem over your tapped creatures (``tapped_matters``).
    * the ``tree_synthesis`` bucket-B synth node — the description-only attack payoff /
      "attacking causes" / untyped Raid-count tail phase emits no typed node for
      (over-fires vetoed there: attacks-alone / exalted, defensive attacks-you,
      can't-attack hosers).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    # An offensive attack-DECLARATION trigger (CR 508.1a) — a "whenever ~ attacks"
    # reward (Accorder Paladin, Adeline, Aurelia). ADR-0036 fold: broadened from the
    # bare ``attacks`` event to the full typed compound-event set
    # (:data:`tree_synthesis.ATTACK_TRIGGER_EVENTS` — "enters or attacks", "attacks
    # and isn't blocked", "whenever you attack with an unblocked …", "one or more
    # creatures attack"), read structurally off the derived ``trigger_event`` (never
    # oracle text). Scope forced "you". Shared with the synth gap gate so the two
    # agree on which triggers phase structuralizes.
    if has_attack_trigger(tree):
        fire("attack_matters", "")
    # A positive Raid state check ("if you attacked this turn" — CR 508.1a/508.4;
    # Mardu Hordechief, Bellowing Saddlebrute), read off the typed ``condition``
    # family (:func:`attack_raid_condition`), never text. The negated "creatures
    # that DIDN'T attack this turn" filter family is deliberately not read.
    if attack_raid_condition(tree):
        fire("attack_matters", "")

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

    # recall-completion b1 (ADR-0034): a static ANTHEM over your tapped creatures
    # ("other tapped creatures you control have indestructible" — Adept Watershaper,
    # Alibou). The effect loop above skips statics (``c.role != "effect"``); read the
    # static's affected filter for Tapped + controller you. The deleted ``_signals_ir``
    # fired this
    # via the effect-subject arm (~8267). CR 301 / 604.3.
    for unit in tree.units:
        if not unit.statics:
            continue
        aff = getattr(unit.node, "affected", None)
        if (
            aff is not None
            and filter_controller(aff) == "You"
            and "Tapped" in filter_predicates(aff)
            and ("Creature" in filter_core_types(aff) or not filter_core_types(aff))
        ):
            fire("tapped_matters", "")

    # bucket-B tail (ADR-0036/0037 fold — the ``_ATTACK_MATTERS_MIRROR`` is deleted):
    # the ``tree_synthesis`` stage's synthesized attack node, for the description-only
    # payoffs phase emits no typed attack node for — a "whenever ~ attacks / attacks
    # or blocks" trigger left description-only (granted/quoted abilities), "attacking
    # causes [extra combat]" (Isshin), and the untyped Raid count ("you attacked with
    # two or more creatures" — Windbrisk Heights). Over-fires (attacks-alone /
    # exalted, defensive attacks-you, can't-attack hosers) are vetoed there. CR 508.
    for c in tree.iter_concepts():
        if c.concept == "synth_attack_matters":
            fire("attack_matters", "")
    return out


def _spellcast_matters(tree: ConceptTree) -> list[Signal]:
    """spellcast_matters — the you-cast (Spellslinger) PAYOFF (CR 601.2 / 603.2).
    Tier-1 structural read (ADR-0036 fold — the ``_detect_spellcast_matters`` /
    ``_IS_BUILDAROUND_RE`` / ``_spellcast_main_clause`` / ``_SPELLCAST_RECASTER_RE``
    mirror is deleted). Two arms, both requiring ``trigger_caster_scope == "you"``:

    * :func:`has_structural_spellcast` — a TYPED (Instant/Sorcery core, or
      ``Non: Creature`` — the Prowess idiom) or UNTYPED (Aetherflux Reservoir —
      no restrictive core type, no subtype, no self-target restriction) you-cast
      trigger (also the compound "cast or copy" magecraft event — Archmage
      Emeritus, Storm-Kiln Artist, Veyran). An enchantment/artifact-only or
      subtype/self-target-restricted watched spell routes elsewhere (excluded),
      matching the deleted regex's carve-outs.
    * the ``tree_synthesis`` bucket-B synth node — the description-only
      granted/emblem/Saga cast trigger, cost reducers (Baral), build-arounds /
      recursion granters (Lier, Kess), recaster/copiers, and past-tense spell
      counts / the delayed next-cast copy rider phase emits no typed cast node
      for.

    The symmetric "a player casts" punishers (Eidolon, Ruric Thar) carry no you
    caster-scope AND no "you cast" clause, so neither arm opens a you build-around
    (they stay ``opponent_cast_matters`` / ``noncreature_cast_punish``).
    """
    if has_structural_spellcast(tree):
        return [Signal("spellcast_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_spellcast_matters":
            return [Signal("spellcast_matters", "you", "", "", tree.name, "high")]
    return []


LANES = (
    _sacrifice_outlets,
    _lifegain_matters,
    _blink_flicker,
    _tokens_matter,
    _ramp,
    _artifacts_enchantments_matter,
    _creatures_matter,
    _attack_tapped_matters,
    _spellcast_matters,
)
