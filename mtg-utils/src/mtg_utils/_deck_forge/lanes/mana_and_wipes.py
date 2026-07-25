"""Crosswalk signal lanes — mana amplifiers / group mana, draw-for-each,
discard outlets, mass removal / bounce / exile, anthem & pump scaling, and
cheat-into-play (split from crosswalk_signals.py)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import fields

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptTree,
    change_zone_dirs,
    count_operand_filter,
    counter_kind,
    discard_recipient_scope,
    double_target_kind,
    effect_filter,
    effect_owner_player_scope,
    effect_owner_raw,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    filter_without_keywords,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_nested_trigger_defs,
    iter_typed_nodes,
    mana_replacement_multiplier,
    mod_value,
    produced_contribution,
    recipient_tag,
    ref_count_qty,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import _SINGLE_PERMANENT_GRANT_PREDS
from mtg_utils._card_ir.tree_synthesis import has_structural_extra_land_drop
from mtg_utils._deck_forge._sweep_detectors import DISCARD_OUTLET_REGEX
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _DEBUFF_SINGLE_AURA_PREDS,
    _DYNAMIC_PT_MODS,
    _GRANT_ABILITY_MOD_TAGS,
    _LAND_SUBTYPES,
    _OPP_DISCARD_ACTORS,
    _PERMANENT_TYPES,
    _RETURN_TARGET_TAGS,
    _is_generic_creature_filter,
    _kept,
    _negative_pt_field,
    _sac_is_edict,
    _site_raw,
    _target_owner_beneficiary_scope,
    _tuck_preceded_by_selection,
)
from mtg_utils._deck_forge.signal_base import (
    Signal,
    _clauses,
)

# Board-wipe subject types (CR 115.10) — mirrors the deleted ``_signals_ir``'s
# identically-named ``_MASS_REMOVAL_TYPES``. Land is deliberately ABSENT: "destroy all
# lands" is land
# destruction (Armageddon), a different lane.
_MASS_REMOVAL_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker"}
)


# Evergreen team-anthem keywords (CR 702) — mirrors the deleted ``_signals_ir``'s
# identically-named ``_TEAM_BUFF_GRANT_KW`` (phase's spaceless spelling normalized via
# lower+strip).
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
        # ADR-0038 W3 batch-3 — a MAX/MIN aggregate over a filtered population
        # ("+X/+0, where X is the greatest power among creature cards in your
        # graveyard" — Carrion Grub, Coram; "greatest mana value among other
        # artifacts" — Emissary Escort) is a board-state-driven scaler by
        # construction (CR 107.3) — the same category as a bare count, just a
        # MAX instead of a COUNT of the same population.
        "Aggregate",
        # ADR-0038 W3 batch-4 (single-target Pump adjudication) — a ZONE card
        # count ("for each card in your graveyard/hand/library" — Gran Pulse
        # Ochu, Ral's Staticaster, Bonehoard, Knight of the Reliquary) is the
        # SAME board-state-scaler category as ``ObjectCount``, just counting a
        # zone's contents instead of the battlefield; CR 107.3 draws no
        # distinction between the two populations.
        #
        # NOTE (ADR-0038 W3 batch 4, draw-etb-tokens cluster, rebase note):
        # this makes ``ZoneCardCount`` UNCONDITIONALLY scaling for every
        # ``_is_scaling_count`` caller, including ``draw_for_each``. Verified
        # against the draw_for_each corpus at rebase time — no card pairs a
        # bare-X *draw* cast magnitude with ``ZoneCardCount`` (the bare-X
        # "draw N where N is..." shapes in the corpus, e.g. Lucid Dreams, are
        # tagged ``DistinctCardTypes``/``Variable``, never ``ZoneCardCount``),
        # so the landmine the original comment warned about does not fire
        # for this tag; see ``_draw_for_each``'s own docstring for the
        # narrower ``_DRAW_FOR_EACH_PHRASE_RE`` fallback that still covers
        # tags NOT admitted here.
        "ZoneCardCount",
        # A TARGET OBJECT's own typeline-component count ("+1/+1 for each
        # supertype, card type, and subtype it has" — Embiggen) is still a
        # value "defined by the text of th[e] ability" per CR 107.3 — the
        # counted quantity is the target's own characteristics rather than a
        # population, but it is exactly as dynamic/non-fixed as any other
        # accepted tag (CR 205.1 types are a countable game quantity).
        "ObjectTypelineComponentCount",
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


def _sum_expr_qty(expr: object) -> str | None:
    """The qty tag of one ``Sum.exprs`` entry, unwrapping a ``Multiply``
    scalar the same way :func:`ref_count_qty` does for a bare field.

    A dynamic value combining TWO separate board counts ("+1/+0 for each
    other Assassin you control and each Assassin card in your graveyard" —
    Desmond Miles, Cid) projects ``Sum(exprs=[Ref(ObjectCount), Ref(
    ZoneCardCount)])`` — a tag ``ref_count_qty`` never reaches (it only
    unwraps a bare/``Multiply``-scaled ``Ref``, not a ``Sum``'s per-expr
    list). CR 107.3.
    """
    e = expr
    if tag_of(e) == "Multiply":
        e = getattr(e, "inner", None)
    if tag_of(e) == "Ref":
        return tag_of(getattr(e, "qty", None))
    return None


def _field_qty(node: TypedMirrorNode, field: str) -> str | None:
    """The board-count qty tag of ``node.field``, peeling a ``Quantity``
    wrapper (a single-target ``Pump``/``PumpAll``'s ``power``/``toughness``
    is ``U_power``/``U_toughness`` — ``T_power__Quantity(value=…)`` for a
    dynamic value, ``T_power__Fixed(value=int)`` for a literal — a DIFFERENT
    top-level shape from a dynamic-mod site's bare ``value`` field, which
    ``ref_count_qty`` already handles) before delegating to
    :func:`ref_count_qty`'s ``Multiply``/``Ref`` unwrap. A ``Fixed`` value
    peels to an ``int``, which fails the ``Ref`` check and correctly yields
    ``None`` (no false scale on a literal +2/+2). CR 107.3.
    """
    v = getattr(node, field, None)
    if isinstance(v, TypedMirrorNode) and tag_of(v) == "Quantity":
        return ref_count_qty(v, "value")
    return ref_count_qty(node, field)


def _is_scaling_count(node: TypedMirrorNode, fields: tuple[str, ...], raw: str) -> bool:
    """Whether one of ``node``'s ``fields`` is a genuine BOARD-COUNT scaler
    ("for each <X>", CR 107.3), not a bare X-spell whose X is the cast cost.

    Mirrors the deleted ``_signals_ir``'s identically-named ``_is_scaling_count`` over
    the typed substrate: a
    counted-population / named-count qty tag (:data:`_SCALING_QTY_TAGS`) is
    always a scale; a bare-X tag (:data:`_BARE_X_QTY_TAGS` — Braingeyser)
    never is; any OTHER dynamic tag (CommanderCastFromCommandZoneCount,
    GraveyardSize, …) scales only when the node's raw names the count ("for
    each" / "equal to the number of" — Commander's Insignia).

    :func:`_field_qty` (not ``ref_qty_tag``) unwraps a ``Quantity`` wrapper
    then a ``Multiply`` scalar, so a "twice the number of X" scaler
    (Champion of the Flame's dynamic self-pump ``Multiply(2,
    Ref(ObjectCount))``) and a ``PumpAll`` mass anthem whose power/toughness
    is ``Quantity``-wrapped (Alistair, Jazal Goldmane — ``PumpAll.power =
    Quantity(Ref(…))``, previously silently missed) both read as a genuine
    count. A ``Sum`` of two board counts (Desmond Miles, Cid —
    :func:`_sum_expr_qty`) is checked per-expr, ANY scaling member
    qualifying the whole value.

    A complex COUNT CONDITION phase can't structure at all (Strata Scythe —
    "for each land on the battlefield with the SAME NAME AS the exiled card";
    Nyxathid — "-1/-1 for each card in the CHOSEN PLAYER'S hand") degrades
    the modification to a flat literal ``value`` (``AddPower(value=1)``,
    indistinguishable node-shape-wise from a genuine fixed anthem) — so
    ``qt is None`` does NOT short-circuit before the ``phrase`` check; the
    node's OWN ``raw`` (its ``description`` — never a sibling's, never the
    whole card's) is the only surviving residue and is authoritative when
    the structural qty is absent. A genuinely fixed anthem with no "for
    each" wording still fails ``phrase`` and stays excluded. CR 107.3.
    """
    low = (raw or "").lower()
    phrase = "for each" in low or "equal to the number of" in low
    for f in fields:
        val = getattr(node, f, None)
        if tag_of(val) == "Sum":
            for expr in getattr(val, "exprs", None) or []:
                qt = _sum_expr_qty(expr)
                if qt in _BARE_X_QTY_TAGS:
                    continue
                if qt in _SCALING_QTY_TAGS or phrase:
                    return True
            continue
        qt = _field_qty(node, f)
        if qt in _BARE_X_QTY_TAGS:
            continue
        if qt in _SCALING_QTY_TAGS or phrase:
            return True
    return False


# ADR-0038 W3 batch 2 — the mana_amplifier dork-support word mirror (the
# EXACT deleted live ``_MANA_DORK_SUPPORT_MIRROR`` regex, CR 605.1). See the
# "Last-resort word mirror" note on ``_mana_amplifier`` for the corpus-
# uniqueness verification (Raggadragga, Goreguts Boss only).
_MANA_DORK_SUPPORT_RX = re.compile(
    r"creatures?[^.]*\bwith a mana abilit", re.IGNORECASE
)


def _mana_amplifier(tree: ConceptTree) -> list[Signal]:
    """mana_amplifier — a mana DOUBLER (CR 106.4 / 605 / 614.1). Four arms:

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
    * (ADR-0038 W3 batch 2) the SAME ``TapsForMana`` TRIGGER whose ``Mana``
      effect's ``produced`` is tagged ``TriggerEventManaType`` — "add one
      mana of any type that [land/permanent] produced" (Mirari's Wake,
      Zendikar Resurgent, Vorinclex, Nikya of the Old Ways, Kinnan, Bonder
      Prodigy, Roxanne, Starfall Savant, Sasaya's Essence). This is a
      DISTINCT typed shape from the ``Additional``-contribution arm above
      (``contribution`` is unset on this variant — the doubling is carried
      by the "matches what was produced" tag itself, not a contribution
      marker), so it needs its own check rather than widening
      ``produced_contribution``'s single string comparison.
    * (ADR-0038 W3 batch 2) a whole-card ``double_quantity`` concept (any
      ``Double`` effect, any origin — CR 106.4) whose ``target_kind`` is
      ``ManaPool`` (Doubling Cube's "{3}, {T}: Double the amount of each
      type of unspent mana you have" activated ability) — mirrors the
      sibling ``life_total_set`` / counter-doubling ``Double{target_kind}``
      reads (``double_target_kind``), just for the mana-pool target.

    Last-resort word mirror (ADR-0038 W3 batch 2, the Perch Protection
    precedent): Raggadragga, Goreguts Boss's "Each creature you control with
    a mana ability gets +2/+2" is a filtered team-pump whose filter
    ("with a mana ability" — CR 605) phase's static parser cannot express
    (it lands as a role=effect ``Unimplemented`` residue with no
    filter-shaped node to recover structurally; the pump target has no
    subject at all). Corpus-verified singleton: the whole commander-legal
    bulk corpus has exactly one card with the literal singular phrase
    "with a mana ability" (grepped 2026-07 — Power Sink's "lands with mana
    abilities" is the plural form and an unrelated tax effect, so this
    idiom is never the deciding vote for an over-fire class).

    The generic ramp lane keeps co-firing where applicable (additive, matching
    the live path). Scope "you".
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
                produced = getattr(c.node, "produced", None)
                if (
                    produced_contribution(c.node) == "Additional"
                    or tag_of(produced) == "TriggerEventManaType"
                ):
                    return [
                        Signal("mana_amplifier", "you", "", c.raw, tree.name, "high")
                    ]
    for c in tree.effect_concepts("double_quantity"):
        if double_target_kind(c.node) == "ManaPool":
            return [Signal("mana_amplifier", "you", "", c.raw, tree.name, "high")]
    if _MANA_DORK_SUPPORT_RX.search(_kept(tree)):
        return [Signal("mana_amplifier", "you", "", "", tree.name, "high")]
    return []


def _extra_land_drop(tree: ConceptTree) -> list[Signal]:
    """extra_land_drop — a land PUT onto the battlefield (CR 305.2 / 116.2a /
    305.4: a put is not a play, so it bypasses the land-per-turn limit). Two
    typed arms mirroring the live structural pair (:func:`has_structural_
    extra_land_drop`, moved to tree_synthesis.py so it shares ONE source with
    the idiom-bridge synthesis arm below):

    * a ``ChangeZone`` Hand→Battlefield whose moved subject is Land-only,
      controller you (Burgeoning's "put a land card from your hand onto the
      battlefield");
    * a ``Dig`` whose ``destination`` is Battlefield with a Land filter
      (Elvish Rejuvenator's look-at-top-five put) — the ``to:hand`` dig
      (Planar Genesis) is card selection, NOT a land drop (checklist #2).

    A card whose land-into-play PUT phase leaves wholly/partially
    unstructured (Aminatou's Augury, Averna, Journey to the Lost City,
    Planar Genesis's own gap, plus the "from hand OR graveyard"
    controller-any disjunction — Bonny Pall, Dread Tiller, Riveteers
    Confluence) is covered by ``tree_synthesis._arm_extra_land_drop``'s
    idiom bridge, ALSO read here via its "extra_land_drop" concept — no
    lane special-case. The extra-land STATIC (Exploration's "play an
    additional land") is a different mechanic this lane also excludes.
    Scope "you".
    """
    if has_structural_extra_land_drop(tree):
        return [Signal("extra_land_drop", "you", "", "", tree.name, "high")]
    for c in tree.effect_concepts("extra_land_drop"):
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


# ADR-0038 W3 batch 4 (draw-etb-tokens cluster) — draw_for_each's LOCAL
# clause-scoped phrase fallback (see ``_draw_for_each``'s docstring):
# "draw(s)" and the scaling phrase must share one comma/period/semicolon-
# delimited clause, so a sibling cost-reduction or life-gain rider on the
# SAME multi-clause ability text never bleeds in.
#
# ADR-0038 W5 tails: a SECOND alternative admits the REVERSED word order —
# "for each ~, ... draw(s) [up to N] a/the card(s)" (Tempt with Bunnies'
# "For each opponent who does, you draw a card ..."; Braids, Arisen
# Nightmare's "For each opponent who doesn't, ... you draw a card"; Seize
# the Spotlight's "For each player who chose fortune, you draw a card
# ..."; Nahiri's Lithoforming's "For each land sacrificed this way, draw a
# card."; Culmination of Studies' "For each blue card exiled this way,
# draw a card."; Refurbished Familiar's "For each opponent who can't, you
# draw a card."; Hollow Marauder's "For each of those opponents who didn't
# discard ..., draw a card."; Mob Verdict's "For each vote you received,
# draw a card."). The FORWARD form (Grim Flowering's "Draw a card for each
# creature ...") stays comma/period/semicolon-scoped (unchanged). The
# REVERSED form must cross the SINGLE internal comma every "For each X,
# <main clause>" idiom carries (CR grammar puts the conditional ahead of
# the main clause) — only period/semicolon (a genuine sentence boundary)
# stop it. ``draws?`` is further REQUIRED to be immediately followed by a
# "card(s)" object (optionally "up to N"/"a/the") — Truce/Temporary
# Truce's "For each card less than two a player draws this way, that
# player gains 2 life." would otherwise false-match on "draws" as a BACK-
# REFERENCE to an EARLIER already-resolved Fixed(2) draw (feeding a LIFE
# GAIN, not a new scaling draw); "draws this way" fails the object check
# and correctly stays excluded (corpus-verified: this object gate was the
# ONLY false-positive class the reversed alternative introduced, 0 others
# across the full corpus).
_DRAW_FOR_EACH_PHRASE_RE = re.compile(
    r"draws?\b[^.,;]*?(?:for each|equal to the number of)"
    r"|for each\b[^.;]*?draws?\s+(?:up to \d+\s+)?(?:an?\s+|the\s+)?cards?\b",
    re.IGNORECASE,
)

# ADR-0038 W3 batch 6 — draw_for_each-SCOPED qty tags (LOCAL to this lane,
# NOT the shared ``_SCALING_QTY_TAGS``/``_BARE_X_QTY_TAGS`` every OTHER
# ``_is_scaling_count`` caller reads — a shared-constant widening would hit
# scaling_pump too, corpus-verified to add 30+ ``FilteredTrackedSetSize``
# Pump/PumpAll cards there, an unaudited blast radius this batch's time
# budget doesn't cover). Every tag here is a delayed/tracked count of
# something that happened AS A RESULT of a preceding clause in the SAME
# ability ("draw a card for each X [discarded/destroyed/exiled/…] this
# way" — Syphon Mind, Reprocess, Decree of Pain, Change of Fortune) or a
# population count (``PlayerCount`` — Inspired Sphinx's "for each
# opponent"), self-evidently a board-defined value (CR 107.3) with no
# non-scaling reading, so no text-phrase gate is needed.
# ``EventContextAmount``/``PreviousEffectAmount`` are DELIBERATELY ABSENT
# here (unlike an early draft of this set) — corpus re-measure showed they
# are AMBIGUOUS between two idioms that share the SAME tag: "draw a card
# for each card drawn this way" (Struggle for Project Purity — genuine
# draw_for_each) and "whenever ~ deals combat damage to a player, draw
# that many cards" (Cold-Eyed Selkie, Robe of the Archmagi, a damage-scaled
# draw ENGINE, not a board-count scale — legacy does NOT tag these
# draw_for_each, confirmed live). The tag alone can't discriminate; both
# stay on the EXISTING ``_DRAW_FOR_EACH_PHRASE_RE`` text gate below
# (widened to also read the unit's own top-level description when the
# closer wrapper carries none — see :func:`_draw_for_each`'s ``scaling``
# closure) — "for each"/"equal to the number of" wording correctly keeps
# the genuine members and excludes the "that many" engines.
_DRAW_FOR_EACH_TRACKED_TAGS: frozenset[str] = frozenset(
    {
        "FilteredTrackedSetSize",
        "ZoneChangeCountThisTurn",
        "TrackedSetSize",
        "ExiledFromHandThisResolution",
        "CardsDiscardedThisTurn",
        "PlayerCount",
        "ObjectColorCount",
        "DistinctColorsAmongPermanents",
        "DistinctCardTypes",
        "HandSize",
    }
)


def _draw_for_each(tree: ConceptTree) -> list[Signal]:
    """draw_for_each — a draw SCALING with a board count (CR 120 / 107.3):
    "draw a card for each creature you control" (Shamanic Revelation). The
    ``count`` is read structurally per draw NODE (granularity a): a fixed draw
    sharing an ability with a for-each rider (Tamiyo's Logbook — the for-each
    lives on ``cost_reduction``, not the draw) carries ``Fixed`` and never
    fires; a bare X-draw (Braingeyser — ``Ref → Variable``) is the cast cost,
    not a board scale (split-lane #4).

    ADR-0038 W3 batch 4 (draw-etb-tokens cluster): the structural qty-tag
    arm is unchanged (``c.raw`` stays the Draw node's OWN text, almost
    always "" — never widened, so :func:`_is_scaling_count`'s generic
    ``phrase`` fallback here keeps behaving exactly as every OTHER
    ``_is_scaling_count`` caller, e.g. ``scaling_pump``, expects). A
    SEPARATE, LOCAL, narrowly-scoped phrase check
    (:data:`_DRAW_FOR_EACH_PHRASE_RE`) covers the genuine remaining gap: a
    "for each"/"equal to the number of" clause that names the DRAW itself
    but whose qty tag isn't (yet) an unconditional ``_SCALING_QTY_TAGS``
    entry. The regex requires "draw(s)" and the phrase to share ONE
    comma/period/semicolon-delimited clause (:func:`effect_owner_raw`'s
    direct-wrapper text, never a sibling's) — Grim Flowering's "Draw a
    card for each creature card in your graveyard." matches (no punctuation
    between); an ability-level cost-reduction rider sharing the SAME
    description (Tamiyo's Logbook, Deepwood Denizen — "Draw a card. This
    ability costs {1} less to activate for each ...") does NOT, because the
    period stops the search before "for each" is reached; nor does a
    sibling life-gain rider on the SAME sentence (Union of the Third Path
    — "Draw a card, then you gain life equal to the number of cards in
    your hand." — the comma stops it).

    Nested-grant descent (mechanism b — the ``_GRANT_ABILITY_MOD_TAGS``
    ``.definition`` precedent :func:`_self_pump`'s sibling scan
    establishes): a granted TRIGGER's own draw also fires (Blitzball
    Stadium's "Go for the Goal!" grants a creature "whenever ~ deals
    combat damage to a player, draw a card for each kind of counter on
    it" — the Draw lives under ``GrantTrigger.trigger.execute.effect``,
    not the granting unit's own effect chain). Scope "you".

    ADR-0038 W3 batch 6 (draw-etb-tokens cluster, NOT YET PROMOTED — see
    below): corpus re-measure 196 both / 17 live_only (down from 74) / 15
    cw_only. Two widenings: (1) :data:`_DRAW_FOR_EACH_TRACKED_TAGS`, a
    LOCAL (draw_for_each-only, never the shared ``_SCALING_QTY_TAGS``) qty
    set for tags that are UNAMBIGUOUSLY a delayed/tracked count of
    something that happened as a result of a preceding clause in the SAME
    ability (Syphon Mind's ``FilteredTrackedSetSize`` "for each card
    discarded this way", Change of Fortune's ``CardsDiscardedThisTurn``,
    Inspired Sphinx's ``PlayerCount`` "for each opponent") — no text gate
    needed, corpus-verified no ambiguous member. (2) the phrase-fallback
    now ALSO reads the owning UNIT's own top-level ``description`` when
    the closer wrapper (:func:`effect_owner_raw`) carries none — recovers
    a Draw nested in a ``sub_ability`` chain (Syphon Mind's "Each other
    player discards a card. You draw a card for each card discarded this
    way." lives on the OUTER Discard unit, the Draw itself on an
    ``S_sub_ability`` with no description of its own). Both widenings
    STAY OFF ``EventContextAmount``/``PreviousEffectAmount`` — corpus
    re-measure showed these two tags are AMBIGUOUS between "draw a card
    for each card drawn this way" (genuine) and "whenever ~ deals combat
    damage to a player, draw that many cards" (Cold-Eyed Selkie, Robe of
    the Archmagi — a damage-scaled draw ENGINE legacy does NOT tag
    draw_for_each); the tag alone can't discriminate the two, so both stay
    gated on the (widened) ``_DRAW_FOR_EACH_PHRASE_RE`` text check, which
    correctly keeps the "for each"/"equal to the number of" wording and
    excludes the "that many" idiom (:data:`_DRAW_FOR_EACH_TRACKED_TAGS`'s
    own comment has the full corpus citations).

    ADR-0038 W5 tails (2026-07-11, corpus re-measure at fresh HEAD: 210
    both / 3 live_only, down from 16): three fixes. (1)
    :data:`_DRAW_FOR_EACH_PHRASE_RE` admits a SECOND alternative — the
    REVERSED word order "for each X, ... draw(s) a card" (Tempt with
    Bunnies, Braids Arisen Nightmare, Mob Verdict's "For each vote you
    received, draw a card.", Hollow Marauder, Bladecoil Serpent, Mutalith
    Vortex Beast), which crosses the SINGLE internal comma the "for each
    X, <main clause>" idiom carries but REQUIRES ``draws?`` to be
    immediately followed by a "card(s)" object — Truce/Temporary Truce's
    "For each card less than two a player draws this way, that player
    gains 2 life." would otherwise false-match on "draws" as a BACK-
    REFERENCE to an EARLIER already-resolved Fixed(2) draw, not a new
    scaling instruction; this was the ONE false-positive class the
    reversed alternative introduced, corpus-verified. (2)/(3) a
    ``CreateDelayedTrigger``'s own ``.effect.effect`` and a ``Vote``'s
    ``per_choice_effect[i].effect`` are BOTH separate branches
    ``effect_concepts`` never reaches (same shape as the GrantTrigger
    descent above) — the Vote descent closes Truth or Consequences ("You
    draw cards equal to the number of truth votes." — reachable via the
    existing FORWARD phrase on the owning unit's top-level description,
    once the node itself is found); the CreateDelayedTrigger descent is
    structural-only this batch (Vivien's Stampede's "draw a card for each
    player who was dealt combat damage this turn" carries NO raw text
    ANYWHERE in its tree — the delayed trigger's own description, its
    wrapped trigger's description, AND the ``S_effect`` wrapper's
    description are all ``None`` — confirmed via direct tree dump; needs
    a card-level ``_kept(tree)`` last-resort read, out of scope this
    session, still residual). CR 107.3 / 603.7 (delayed triggered
    abilities) / 701.38 (Vote) — verified via rules-lookup this session.

    ADR-0038 W5b tail closes Mouth // Feed's "Feed" back-half (Aftermath):
    phase emits a MATCHED but EMPTY (``units=0``) record for this face
    (its top-level ``oracle_text`` is ``None``, the normal Scryfall/
    MTGJSON DFC shape), so the W2c text-only-face fallback (task #76)
    never synthesizes a substitute TREE (its gate is "no name-matched
    phase record", not "an empty one") — but the ``ConceptTree`` it DOES
    produce still carries the real face text on ``tree.oracle`` ("Draw a
    card for each creature you control with power 3 or greater."). A
    units-empty fallback below reads that text through the SAME
    ``_DRAW_FOR_EACH_PHRASE_RE`` clause-scoped gate the structural arm's
    own text fallback already trusts, scoped strictly to ``not
    tree.units`` so a typed face's structural miss never silently falls
    back to a blind whole-oracle scan. Aclazotz, Deepest Betrayal shares
    Mouth // Feed's blank top-level ``oracle_text`` but is NOT a
    units-empty case (3 real typed units on its front face) — its "for
    each opponent who can't, you draw a card" is the SAME per-opponent-
    modal shape as Refurbished Familiar, so the fallback correctly does
    not fire for it.

    STILL NOT PROMOTED — 2 genuine live_only remain, neither adjudicable
    as a shed (both ARE real draw_for_each cards, just structurally
    unreachable): Vivien's Stampede (above); Nexus Mentality's "Remove all
    counters from target nonland permanent you control. Draw a card for
    each counter removed this way." (a plain ``sub_ability`` chain with NO
    owner text anywhere either — the SAME no-raw-text gap, not a Vote
    node). Two of the cw_only gains this batch (Peer Past the Veil / Lucid
    Dreams's "draw X cards, where X is the number of card types among
    cards in your graveyard") are genuine beyond-legacy recalls — legacy's
    regex only recognizes "for each"/"equal to the number of" wording,
    missing "where X is the number of", a narrower net than the CR 107.3
    concept.
    """

    def scaling(node: TypedMirrorNode, owner: object) -> bool:
        if _is_scaling_count(node, ("count", "amount"), ""):
            return True
        if any(
            _field_qty(node, f) in _DRAW_FOR_EACH_TRACKED_TAGS
            for f in ("count", "amount")
        ):
            return True
        raw = effect_owner_raw(owner, node) or (
            getattr(owner, "description", None) or ""
        )
        return bool(raw) and bool(_DRAW_FOR_EACH_PHRASE_RE.search(raw))

    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if scaling(c.node, unit.node):
                # task #91 — Deadly Cover-Up's scaling draw recipient is the
                # OWNER of the earlier-exiled opponent-graveyard card
                # (:func:`_target_owner_beneficiary_scope`, CR 108.3): the
                # root filter's ``Owned: Opponent`` constraint makes the
                # drawer ALWAYS an opponent, never "you".
                scope = "you"
                if recipient_tag(c.node) == "ParentTargetOwner":
                    override = _target_owner_beneficiary_scope(unit)
                    if override is not None:
                        scope = override
                return [Signal("draw_for_each", scope, "", c.raw, tree.name, "high")]
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) not in _GRANT_ABILITY_MOD_TAGS:
                continue
            trig = getattr(n, "trigger", None)
            execute = getattr(trig, "execute", None) if trig is not None else None
            for m in iter_typed_nodes(execute) if execute is not None else ():
                if tag_of(m) != "Draw":
                    continue
                if scaling(m, execute):
                    return [Signal("draw_for_each", "you", "", "", tree.name, "high")]
        # ADR-0038 W5 tails: a ``CreateDelayedTrigger``'s own ``.effect``
        # (an ``S_effect`` wrapper, "At the beginning of the next main
        # phase this turn, draw a card for each player who was dealt
        # combat damage this turn" — Vivien's Stampede) and a ``Vote``'s
        # per-choice branches (``per_choice_effect[i].effect`` — "You draw
        # cards equal to the number of truth votes." — Truth or
        # Consequences) are BOTH separate branches ``effect_concepts``
        # never reaches (same shape as the GrantTrigger descent above —
        # neither field is in the ability's own top-level effect chain).
        # CR 603.7 (delayed triggered abilities) / 701.38 (Vote).
        for n in iter_typed_nodes(unit.node):
            tag = tag_of(n)
            if tag == "CreateDelayedTrigger":
                inner = getattr(n, "effect", None)
                draw = getattr(inner, "effect", None) if inner is not None else None
                if isinstance(draw, TypedMirrorNode) and tag_of(draw) == "Draw":
                    if scaling(draw, unit.node):
                        return [
                            Signal("draw_for_each", "you", "", "", tree.name, "high")
                        ]
                    # ADR-0038 W6 endgame: Vivien's Stampede's delayed-
                    # trigger Draw carries NO raw text ANYWHERE in its
                    # tree — the delayed trigger's own description, its
                    # wrapped trigger's description, AND the ``S_effect``
                    # wrapper's description are all ``None`` (confirmed
                    # via direct tree dump), so ``scaling``'s two raw-text
                    # reads both come up empty and the structural qty-tag
                    # check finds nothing either (a bare ``Fixed(1)``
                    # count). The card-level ``_kept(tree)`` last-resort
                    # read is the ONLY possible text source — gated
                    # STRICTLY to this structurally-confirmed
                    # CreateDelayedTrigger-wraps-an-unscaled-Draw shape
                    # (never a blind whole-oracle scan for a card that
                    # doesn't carry one), so a card with an UNRELATED
                    # "for each"/"equal to" clause elsewhere never
                    # false-fires through this arm. CR 603.7 (delayed
                    # triggered abilities) / 107.3 (scaling values).
                    if _DRAW_FOR_EACH_PHRASE_RE.search(_kept(tree)):
                        return [
                            Signal("draw_for_each", "you", "", "", tree.name, "high")
                        ]
            elif tag == "Vote":
                for pce in getattr(n, "per_choice_effect", None) or []:
                    draw = getattr(pce, "effect", None)
                    if not isinstance(draw, TypedMirrorNode) or tag_of(draw) != "Draw":
                        continue
                    if scaling(draw, unit.node):
                        return [
                            Signal("draw_for_each", "you", "", "", tree.name, "high")
                        ]
        # ADR-0038 W6 endgame: a Draw's ``count`` reading
        # ``Ref(PreviousEffectAmount)`` stays OFF the shared
        # ``_DRAW_FOR_EACH_TRACKED_TAGS`` set (Windfall / Jace's Archivist
        # / Whispering Madness's "draws cards equal to the GREATEST number
        # ... discarded" wheel effect ALSO carries this exact tag, off a
        # symmetric per-player Discard->Draw chain, and is NOT a
        # draw_for_each build-around — legacy fires nothing for it
        # either), but a Draw IMMEDIATELY chained (``SequentialSibling``,
        # unrolled into this unit's own ``effects`` tuple) right after a
        # ``RemoveCounter`` in the SAME unit is unambiguously "draw a card
        # for each counter removed this way" (Nexus Mentality's "Remove
        # all counters from target nonland permanent you control... Draw
        # a card for each counter removed this way." — no raw text
        # anywhere on this modal bullet's own nodes to satisfy
        # ``scaling``'s text gate, the SAME no-owner-text shape as
        # Vivien's Stampede above, just a plain ``sub_ability`` chain
        # rather than a delayed trigger). A POSITIVE gate on the
        # PRECEDING sibling's own tag (``RemoveCounter``, never a bare
        # "reached via PreviousEffectAmount") never reaches the
        # Discard-wheel shape, whose preceding sibling is a ``Discard``.
        # CR 121.1 (counters) / 107.3 (scaling values).
        effs = unit.effects
        for i, c in enumerate(effs):
            if i == 0 or tag_of(c.node) != "Draw":
                continue
            if tag_of(effs[i - 1].node) != "RemoveCounter":
                continue
            qty = getattr(getattr(c.node, "count", None), "qty", None)
            if tag_of(qty) == "PreviousEffectAmount":
                return [Signal("draw_for_each", "you", "", "", tree.name, "high")]
    # ADR-0038 W5b tail: a TEXT-ONLY face tree (task #76 — the bulk oracle
    # is the source of record for a face phase's card-data.json never
    # parsed at all, e.g. Mouth // Feed's Aftermath back half) carries
    # ``tree.units == ()`` — zero typed nodes, so the loop above never
    # runs. ``tree.oracle`` still holds the real text ("Draw a card for
    # each creature you control with power 3 or greater."), so the SAME
    # ``_DRAW_FOR_EACH_PHRASE_RE`` clause-scoped gate the structural
    # arm's own text fallback already trusts is the ONLY possible read —
    # scoped to the units-empty case so a typed face's structural miss
    # never silently falls back to a blind whole-oracle scan.
    if not tree.units and _DRAW_FOR_EACH_PHRASE_RE.search(_kept(tree)):
        return [Signal("draw_for_each", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W4 giants — the discard_outlet KEPT MIRROR. The byte-identical
# deleted SWEEP regex (_sweep_detectors.DISCARD_OUTLET_REGEX), run PER-
# CLAUSE over the reminder-stripped kept oracle (its "draw … then discard"
# arms span a sentence over the whole oracle, so — like self_blink /
# impulse_top_play in the old IR — it MUST scan clauses, not flat text).
# Recovers what the structural + cost-descent arms below still can't reach:
# an "as an additional cost to cast this spell, discard …" (Devastating
# Dreams, Kaervek's Spite — the Spell ability's own ``cost`` field is
# ``None`` for an additional cast cost, mirroring ``_CAST_ADD_SAC_RX``'s
# documented sacrifice_outlets gap: no Discard node exists ANYWHERE in the
# typed tree for it), and a cross-clause "draw N cards. Then discard a
# card unless …" whose "unless" rider phase parks as a whole-clause
# ``Unimplemented`` residue with NO typed Discard node at all (Timeline
# Inquiry, Katara, Seeking Revenge, Waterbending Lesson, Tainted
# Indulgence). None of the regex's arms mention "opponent"/"target" (CR
# 701.8a's forced-attack family never phrases as a self-referential
# "discard …:" cost or a "draw … then discard" sequence), so the opp-
# hand-attack cards stay out of this arm exactly as they did in the
# deleted SWEEP era.
_DISCARD_OUTLET_SWEEP_RE = re.compile(DISCARD_OUTLET_REGEX, re.IGNORECASE)

# Fields the discard_outlet cost/effect descent does NOT walk through — every
# one is a DIFFERENT-payer or ambiguous-chooser shape corpus-verified to
# over-fire when read structurally (probed this session, +60 crosswalk_only):
# ``unless_pay`` (Torment of Hailfire's "each opponent loses 3 life unless
# that player discards", Reality Smasher's "unless its controller discards" —
# the SAME shape sacrifice_outlets deliberately excludes, since CR 602.1a's
# "paid by the activator" default does not extend past an ``unless`` escape
# hatch whose payer may be a DIFFERENT player; even a self-paid one
# — Balduvian Horde's "sacrifice it unless you discard" — stays out to match
# legacy, which reads none of this shape either); ``branches``/
# ``per_choice_effect`` (a ``ChooseOneOf`` modal's alternatives — K'un-Lun
# Warrior's "you may discard a card or sacrifice a Room" is a genuine
# self-outlet, but Osseous Sticktwister's "each opponent may sacrifice a
# permanent or discard a card" is the SAME branch shape with an opponent
# chooser :func:`effect_owner_player_scope` can't reach through — the modal
# wrapper's ``player_scope`` lives OUTSIDE ``_EFFECT_CHILD_FIELDS``'s reach,
# so the two can't be told apart structurally without new machinery; both
# stay out, matching legacy, which reads neither); ``mode`` (Mox Diamond's
# replacement ``MayCost`` alternative — "you may discard a land instead" is
# a REPLACEMENT's decline-cost, not a discretionary value engine, and legacy
# doesn't read it either).
_DISCARD_OUTLET_SKIP_FIELDS: frozenset[str] = frozenset(
    {"unless_pay", "branches", "per_choice_effect", "mode"}
)


def _iter_discard_cost_nodes(root: object) -> Iterator[TypedMirrorNode]:
    """Deep walk collecting every ``Discard``-tagged node reachable from
    ``root``, skipping :data:`_DISCARD_OUTLET_SKIP_FIELDS` subtrees. Mirrors
    :func:`~mtg_utils._card_ir.crosswalk.iter_typed_nodes`'s generic
    field/variant/list walk exactly, narrowed for this one lane."""
    seen: set[int] = set()
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, TypedMirrorNode):
            if tag_of(node) == "Discard":
                yield node
            for f in fields(node):
                if f.name in _DISCARD_OUTLET_SKIP_FIELDS:
                    continue
                stack.append(getattr(node, f.name))
        elif isinstance(node, MirrorVariant):
            stack.append(node.inner)
        elif isinstance(node, list):
            stack.extend(node)


# Recovered-discard direction gate (see the recovered_by branch inside
# _discard_outlet): a recovered node's raw is a TRUNCATED clause, so an
# opponent-directed discard can LOOK imperative ("discard all cards with
# that name revealed this way" — the "Target opponent reveals ..." subject
# lives in a different clause). These residues carry tell-tale
# subject/backref words; a genuine self-loot clause carries none of them.
_RECOVERED_OPP_DISCARD_RE = re.compile(
    r"\b(?:target (?:player|opponent)|each opponent|that player|the player"
    r"|its controller|their hand|revealed this way|spliced|can't)\b"
)


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

    ADR-0038 W4 giants — the DOMINANT gap this key carried was cost-position:
    "Discard a card: <effect>" (Seismic Assault, the Spellshaper cycle) never
    surfaces through :meth:`AbilityUnit.effect_concepts` at all (a COST, not
    an effect). A single deep :func:`_iter_discard_cost_nodes` descent over
    the unit's own node finds EVERY ``Discard``-tagged node reachable from
    it — a bare top-level cost (Seismic Assault), a leaf folded into a
    Composite/OneOf activation cost (Insolent Neonate's "Discard a card,
    Sacrifice this creature:", the Grandeur "Discard another card named
    ~:" cost — Oriss, Korlash, Tarox Bladewing), a GRANTED "Discard a
    card:" ability's own cost living inside a static's
    ``GrantAbility.definition`` (Tin Street Market, Prophetic Ravings,
    Hollowhead Sliver's tribal grant), AND an EFFECT-position discard
    phase nests past ``effect_concepts``'s ``_EFFECT_CHILD_FIELDS`` reach —
    a conditional-replacement's ``sub_ability.else_ability.effect`` (The
    Destined Thief's "draw a card, then discard a card. If you have a
    full party, instead draw three cards.") — one generic walk, same two
    gates as the structural arm above (a cost leaf carries no recipient
    field, so :func:`discard_recipient_scope` trivially reads ``None`` and
    passes; CR 602.1a's "paid by the activator" default needs no
    controller check here, matching :func:`_sac_leaf_is_you_outlet`'s same
    reasoning for sacrifice_outlets). The walk skips
    :data:`_DISCARD_OUTLET_SKIP_FIELDS` — ``unless_pay``/``branches``/
    ``per_choice_effect``/``mode`` alternative-payer and ambiguous-chooser
    shapes corpus-verified to over-fire when read this deeply (+60
    crosswalk_only, reverted this session; see that constant's docstring).

    Scope "you" (the lane convention — it fuels the controller's engine).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("discard"):
            if discard_recipient_scope(c.node) not in ("you", "each", None):
                continue
            owner = effect_owner_player_scope(getattr(unit, "node", None), c.node)
            if owner in _OPP_DISCARD_ACTORS:
                continue
            # A RECOVERED discard node (ADR-0038 post-giants batch) keeps
            # the Unimplemented wrapper as ``.node`` — no typed recipient,
            # so both gates above pass trivially and the clause's own
            # words are the only direction carrier. Reject the
            # opponent-directed / protection residues (census: 22
            # recovered discards; "Target player discards" — Tainted
            # Specter, "each opponent discards" — Bladecoil Serpent,
            # subject-truncated backrefs like Nebuchadnezzar's "discard
            # all cards with that name revealed this way", Tamiyo's
            # "can't cause you to discard" protection). What remains is
            # the self-loot class (CR 701.8a): the period-split "Then
            # discard a card unless <cond>" tail (Timeline Inquiry class)
            # + bare self imperatives (Breakthrough) + the symmetric
            # each-player wheel (Noxious Vapors — the Dark Deal
            # precedent: a wheel hits you too).
            if c.recovered_by == "discard" and _RECOVERED_OPP_DISCARD_RE.search(
                (c.raw or "").lower()
            ):
                continue
            return [Signal("discard_outlet", "you", "", c.raw, tree.name, "high")]
        for n in _iter_discard_cost_nodes(unit.node):
            # A ``self_ref`` COST leaf ("Discard THIS card:") is Cycling /
            # Eternalize / Unearth-style alt-cost fodder, not an outlet —
            # mirrors the old IR's cost-part split ("discardself" vs
            # "discard") that keeps a pure-cycling card (Krosan Tusker) OUT
            # (an effect-position Discard node carries no ``self_ref``
            # field at all, so this is a no-op there).
            if getattr(n, "self_ref", False):
                continue
            if discard_recipient_scope(n) not in ("you", "each", None):
                continue
            owner = effect_owner_player_scope(unit.node, n)
            if owner in _OPP_DISCARD_ACTORS:
                continue
            return [Signal("discard_outlet", "you", "", "", tree.name, "high")]
    if any(_DISCARD_OUTLET_SWEEP_RE.search(cl) for cl in _clauses(_kept(tree))):
        return [Signal("discard_outlet", "you", "", "", tree.name, "high")]
    return []


def _mass_removal(tree: ConceptTree) -> list[Signal]:
    """mass_removal — a BOARD WIPE (CR 115.10 / 701.8 / 701.21a / 406.1). Five
    typed arms, each anchored on phase's first-class mass tag (the
    counter_kind=='all' discriminator of the old IR, carried structurally):

    * ``DestroyAll`` over a battlefield permanent type (Wrath of God);
    * ``ChangeZoneAll`` → Exile with no graveyard origin (Merciless
      Eviction) — a graveyard-zone mass exile (Living Death) is GY
      recursion, NOT a wipe (checklist #2); task #88 widens the SAME tag
      to a Library destination too (Terminus, Hallowed Burial, Harmonic
      Convergence's "put all enchantments on top of their owners'
      libraries") — a mass TUCK (CR 401.4) is the same "clears the board"
      result as a mass exile, just a different zone-change verb, gated by
      the SAME graveyard-origin veto (a mass graveyard-to-library shuffle-
      back — Repopulate's "shuffle all creature cards from target
      player's graveyard into that player's library" — is GY recursion,
      not a wipe, corpus-verified);
    * ``DamageAll`` over a Creature/Permanent subject (Blasphemous Act,
      Pyroclasm);
    * a NEGATIVE symmetric ``PumpAll`` over creatures (Languish's "all
      creatures get -4/-4"; Toxic Deluge / Drown in Sorrow's dynamic "-X/-X"
      — :func:`_negative_pt_field` reads BOTH the FIXED magnitude and the
      Variable's sign-only string) — the typed substrate carries the
      negative amount, so the live ``_MASS_DEBUFF_RAW`` raw arm reads
      structurally here (a fidelity gain over the spec's live-only
      expectation). Three sub-gates keep the sweep genuine: the
      controller-less gate mirrors the live raw's "ALL creatures" anchor (a
      one-sided "creatures your opponents control get -1/-1" dip — Cower in
      Fear, and the STATIC opponent-scoped Massacre Wurm/Elesh Norn shape —
      is debuff_makers, an adjudicated boundary predating this arm, not a
      gap: CR draws no "board wipe" line, but the deck-building distinction
      between a SYMMETRIC sweep and a one-sided punisher is real and this is
      where it lives); the NEGATIVE-TOUGHNESS gate is the lethality tell (CR
      704.5f — a "-2/-0" combat dip like Hydrolash never kills); and the
      attachment-predicate veto drops the single-Aura "+1/-1" shifter
      (Flowstone Blade's enchanted creature — one target, not a board);
    * ``ChooseAndSacrificeRest`` (Tragic Arrogance, Cataclysm, Cataclysmic
      Gearhulk, Slaughter the Strong, Liliana Dreadhorde General's -6, Ajani
      Nacatl Avenger, Mythos of Snapdax, Destined Confrontation) — "each
      player sacrifices all OTHER nonland permanents [they don't keep]".
      Corpus-exhaustive (8 commander-legal cards carry this tag; every one is
      a genuine symmetric sweep). SACRIFICE (CR 701.21a) is a distinct
      zone-change verb from DESTROY (CR 701.8) — the permanent moves to the
      graveyard by its controller's own action, not the effect's — but the
      RESULT (the board is swept) is the same "clears the battlefield" shape
      as the other three arms, so it belongs in this lane, not a new one.
      The tag's own ``sacrifice_filter`` core-types gate (never ``Land`` —
      matches the type gate below) is the only guard needed: unlike the
      DestroyAll/ChangeZoneAll arms there is no ``ctrl == "You"``-only shape
      to veto (the tag is inherently "each player", never a single-player
      grab).

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
            # CHOSEN-SET sweep (task #84): "starting with you, each player
            # chooses …; Destroy each [creature/permanent] chosen this way"
            # — phase v0.23.0 fixed the destroy target from a bare type
            # POPULATION (which the arm above read as a wipe, accidentally
            # right) to the honest ``TrackedSet`` back-reference holding the
            # per-player picks. The set scales with the player count (one+
            # pick per player, every player's board exposed), so the table
            # result IS a multi-permanent sweep (CR 701.8 destroy; CR 101.4
            # APNAP each-player choice loop) — corpus-exhaustive at the
            # v0.23.0 census: DestroyAll-over-TrackedSet is exactly Call to
            # the Void, Druid of Purification, Grenzo's Rebuttal, and The
            # Horus Heresy's chapter III, the four members the population
            # fix would otherwise shed.
            if t == "DestroyAll" and tag_of(getattr(c.node, "target", None)) == (
                "TrackedSet"
            ):
                return hit
            if t == "ChangeZoneAll" and ctrl != "You":
                origin, dest = change_zone_dirs(c.node)
                gy = origin == "Graveyard" or ("Graveyard" in filter_inzone_zones(sub))
                if dest == "Exile" and not gy and cores & _MASS_REMOVAL_TYPES:
                    return hit
                # task #88 — mass TUCK (Terminus, Hallowed Burial, Harmonic
                # Convergence): the same graveyard/hand-origin veto as the
                # Exile arm above (a mass graveyard-to-library shuffle-back
                # — Repopulate — is GY recursion, not a wipe), plus the
                # SAME card-selection-precedence veto :func:`_removal`'s
                # own tuck arm applies (:data:`_TUCK_SELECTION_SIBLINGS`)
                # — no corpus mass member needs it today, kept for parity
                # so a future reveal/mill-then-mass-tuck card can't slip
                # through unguarded.
                non_bf = origin in ("Graveyard", "Hand") or (
                    set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}
                )
                idx = next((i for i, e in enumerate(unit.effects) if e is c), None)
                preceded = idx is not None and _tuck_preceded_by_selection(
                    unit.effects, idx
                )
                if (
                    dest == "Library"
                    and not non_bf
                    and not preceded
                    and cores & _MASS_REMOVAL_TYPES
                ):
                    return hit
            if t == "DamageAll" and cores & {"Creature", "Permanent"}:
                return hit
            if (
                t == "PumpAll"
                and _negative_pt_field(c.node, "toughness")
                and "Creature" in cores
                and ctrl is None
                and not combat_scope
                and "Flanking" not in filter_without_keywords(sub)
                and not (set(filter_predicates(sub)) & _DEBUFF_SINGLE_AURA_PREDS)
            ):
                return hit
            if t == "ChooseAndSacrificeRest":
                sac = getattr(c.node, "sacrifice_filter", None)
                if set(filter_core_types(sac)) & _MASS_REMOVAL_TYPES:
                    return hit
    return []


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
    # Stage-A recovery: the ``synth_token_subtype_own_ref`` bucket-B marker (a
    # "cares about Treasure/Blood without making it" own-ref — Evereth's "if the
    # sacrificed permanent was a Treasure"), the SAME arm the parallel food/clue
    # lane (:func:`_token_subtype_payoff`) already reads. The synth is gated to
    # subtypes the face does not itself make/sacrifice, so a pure maker stays out.
    for c in tree.iter_concepts():
        if c.concept == "synth_token_subtype_own_ref":
            for st in c.subject:
                key = _SAC_TOKEN_MATTERS.get(st.lower())
                if key:
                    fire(key, "")
    return out


def _is_anthem_group_filter(filt: object) -> bool:
    """A creature-GROUP anthem subject (CR 604.3 / 613.4): Creature in core
    types AND (controller you OR ``Another`` OR subtyped) AND not an
    opponent-board debuff target. A single-target pump (controller any, no
    Another/subtype) fails the group test. An ``EquippedBy``/``EnchantedBy``
    predicate names ONE permanent (CR 301.5c / 303.4d — an Equipment/Aura
    can't be attached to more than one object), so a
    conditional equip bonus phase v0.23.0 now parses with a SUBTYPED
    equipped-creature filter ("As long as equipped creature is a Human, it
    gets an additional +1/+0" — True-Faith Censer, Silver-Inlaid Dagger,
    Heavy Mattock) fails the group test on the predicate, not the subtype
    (task #84; the same single-permanent veto _global_ability_grant runs)."""
    if filt is None or filter_controller(filt) == "Opponent":
        return False
    if "Creature" not in filter_core_types(filt):
        return False
    if set(filter_predicates(filt)) & _SINGLE_PERMANENT_GRANT_PREDS:
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
        affected = getattr(unit.node, "affected", None)
        if _is_anthem_group_filter(affected):
            # Subject: the group's single subtype (Goblin King, Crucible of
            # Fire), else its single NON-CREATURE core type lowercased
            # (Chrome Dome's "artifact creatures" -> "artifact", Weaver of
            # Harmony's "enchantment creatures" -> "enchantment"; both
            # killed under Zaxara, iteration-1b) — the pair ledger's
            # scoped_subject_gate compares either against the commander's
            # swarm. A plain creature-group anthem (Heraldic Banner,
            # Eldrazi Monument) stays "".
            subs = set(filter_subtypes(affected))
            subject = next(iter(subs)) if len(subs) == 1 else ""
            if not subject:
                cores = {c.lower() for c in filter_core_types(affected)} - {"creature"}
                subject = next(iter(cores)) if len(cores) == 1 else ""
            return [Signal("anthem_static", "you", subject, "", tree.name, "high")]
    return []


def _pump_scaling_lanes(tree: ConceptTree) -> list[Signal]:
    """scaling_pump / count_anthem — a +X/+X that SCALES with a board count
    (CR 107.3 / 613.4c). Two typed surfaces:

    * a mass ``PumpAll`` OR single-target ``Pump`` whose power/toughness is a
      scaling ``Ref``;
    * a dynamic P/T modification site (``AddDynamicPower`` — Craterhoof's
      nested one-shot static, Commander's Insignia's continuous anthem) whose
      ``value`` scales; the ``Set*`` forms are */* CDA bodies, excluded.

    ``count_anthem`` is the TEAM-subject subset (the site's ``affected`` /
    the pump's subject is a generic creatures-you-control filter — Hold the
    Gates, Commander's Insignia); a symmetric controller-any global (Coat of
    Arms) or single-target firebreathing stays scaling_pump-or-nothing
    (checklist #6). Bare-X pumps (a "-X/-X" activation — ``Variable``) never
    scale (split-lane #4). Both scope "you".

    ADR-0038 W3 batch-4 — the single-target ``Pump`` class (Goblin
    Piledriver's SelfRef self-buff, Herald of Amity's Typed-target grant,
    General Marhault Elsdragon's TriggeringSource team-enabler) is a genuine
    scaling_pump member by the SAME CR 107.3 / 613.4c contract as a mass
    ``PumpAll``: a "+X/+0 ... for each other attacking Goblin" one-shot
    buff on a single creature scales exactly like a board anthem, it just
    lands on one object instead of every object a filter names. The lane's
    typed target (SelfRef / Typed / TriggeringSource / ParentTarget /
    Player) never gates ``scaling_pump`` — a mass anthem and a firebreather
    are the SAME "does the amount scale" question, and phase's own
    ``target`` tagging is a positional artifact of the effect shape (a
    scoped "-1/-1 for each Zombie THAT PLAYER controls" pump still tags
    ``target=Player`` on Dark Salvation even though the actual object
    receiving the pump is a target creature) — never the deciding signal
    here. ``count_anthem`` stays PumpAll-only: a single-target Pump, however
    it scales, is never a "creatures you control" anthem subject (checklist
    #6).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.effect_concepts("pump"):
        # ADR-0038 W3 batch-3: ``PumpAll``'s ``power``/``toughness`` is
        # ``U_power``/``U_toughness`` — ``T_power__Quantity(value=…)`` for a
        # genuine dynamic scale (a wrapper :func:`_field_qty` now peels),
        # ``T_power__Fixed(value=int)`` for a literal. This was previously
        # silently under-served (Alistair, Cloudkill, Jazal Goldmane —
        # ``PumpAll.power = Quantity(Ref(…))`` fell through the un-peeled
        # ``ref_count_qty`` check as if fixed).
        #
        # ADR-0038 W3 batch-4: single-target ``Pump`` is now ADMITTED
        # alongside ``PumpAll`` (see docstring) — re-corpus-verified this
        # session across the full ~130-card single-target dynamic-Pump
        # class (every sub-shape by target tag: SelfRef firebreathers,
        # Typed target-creature grants, TriggeringSource team-enablers,
        # ParentTarget same-object chains, and the one Player-mistagged
        # Dark Salvation) plus 2 widened ``_SCALING_QTY_TAGS`` entries
        # (``ZoneCardCount``, ``ObjectTypelineComponentCount``) needed to
        # recover Gran Pulse Ochu / Ral's Staticaster (graveyard/hand zone
        # counts) and Embiggen (target's own typeline-component count) —
        # the 3 of the 5 originally-missing cards whose qty tag wasn't yet
        # in the accepted set. No card-count veto (a creature-population
        # split was tried and does not separate a genuine class); the tag
        # itself is the boundary. CR 107.3, 613.4c.
        if tag_of(c.node) in ("PumpAll", "Pump") and _is_scaling_count(
            c.node, ("power", "toughness"), c.raw
        ):
            fire("scaling_pump", c.raw)
            if tag_of(c.node) == "PumpAll" and _is_generic_creature_filter(
                effect_filter(c.node)
            ):
                fire("count_anthem", c.raw)

    def scan_mod_sites(root: object) -> None:
        for sdef, mod in iter_mod_sites(root):
            # A count condition too complex for phase to structure at all
            # (Strata Scythe — "for each land … with the SAME NAME AS the
            # exiled card"; Nyxathid — "for each card in the CHOSEN
            # PLAYER'S hand") degrades to a plain fixed ``AddPower``/
            # ``AddToughness`` (the SAME tag a genuine fixed anthem carries)
            # rather than ``AddDynamicPower``/``AddDynamicToughness`` — so
            # this admits BOTH tag families; ``_is_scaling_count``'s
            # ``phrase`` fallback (the node's OWN description) is what still
            # excludes a real fixed anthem with no "for each" wording.
            if tag_of(mod) not in _DYNAMIC_PT_MODS | {"AddPower", "AddToughness"}:
                continue
            raw = _site_raw(sdef)
            if not _is_scaling_count(mod, ("value",), raw):
                continue
            fire("scaling_pump", raw)
            if _is_generic_creature_filter(getattr(sdef, "affected", None)):
                fire("count_anthem", raw)

    for unit in tree.units:
        scan_mod_sites(unit.node)
        # A token's OWN self-pump can live TWO hops deep — a Saga chapter /
        # activated-ability's ``GrantAbility``/``GrantStaticAbility``
        # MODIFICATION wraps a granted ability whose ``definition`` (or
        # ``definition.effect``) is the ``Token`` that carries the dynamic
        # pump (Urza's Saga Chapter II: "gain '{2}, {T}: Create a …
        # Construct … with {this token pump}'"; Sound the Call's granted
        # ``GrantStaticAbility`` directly wraps the pump modifications).
        # ``iter_mod_sites`` never descends into a modification's OWN
        # ``definition`` field (by design — a modification is a LEAF, not a
        # further traversal root), so each grant tag found via the generic
        # deep walk (:func:`iter_typed_nodes`, :data:`_GRANT_ABILITY_MOD_TAGS`)
        # re-roots a FRESH ``iter_mod_sites`` scan at its ``definition`` (the
        # same ``GrantAbility.definition`` descent
        # :func:`has_structural_power_tap_engine` establishes).
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) not in _GRANT_ABILITY_MOD_TAGS:
                continue
            d = getattr(n, "definition", None)
            if d is not None:
                scan_mod_sites(d)
    return out


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
    equipped narrowing fails). Mirrors the deleted ``_signals_ir``'s
    ``_is_team_buff_grant``."""
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


# Fix (e)'s reveal-producer allow-list (a unit that actually REVEALS/
# imprints a card before the conditional put — reveal_top / reveal_until /
# dig / turn_face_up / exile_top). Hoisted to module scope so
# :func:`_cheat_negated_reveal_else_put` (ADR-0039 W7) can gate on the SAME
# producer set fix (e) uses, rather than re-deriving a parallel list.
_CHEAT_REVEAL_PRODUCERS = (
    "reveal_top",
    "reveal_until",
    "dig",
    "turn_face_up",
    "exile_top",
)


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

    ADR-0038 W3 batch 5 widens four more shapes, all typed / zero-guess:

    * **ChangeZoneAll** (fix c) — the SYMMETRIC "each player puts revealed
      permanent cards onto the battlefield" idiom (Warp World, Over the Top)
      rides ``ChangeZoneAll``, not ``ChangeZone`` — same effect family (both
      share the ``destination`` / ``target`` shape), just multi-object;
    * **the RevealUntil arm** (fix d) — a ``RevealUntil`` whose
      ``kept_destination`` is Battlefield IS the reveal-until-a-match-then-put
      engine (Polymorph, Jalira, Audacious Reshapers — CR 701.15); the same
      core/subtype type-evidence gate as the ChangeZone arm (never guess);
    * **the RevealedHasCardType-conditioned put** (fix e) — Call of the Wild
      ("Reveal the top card. If it's a creature card, put it onto the
      battlefield.") and the imprint-then-reveal cycle (Clone Shell,
      Summoner's Egg — CR 400.7, extending the dies_recursion boundary
      adjudication) structure the type check as a typed ``Condition``
      (``RevealedHasCardType{card_types}``) on the SAME sub-ability as a
      ``ChangeZone{Battlefield}`` targeting ``ParentTarget``/``SelfRef`` (the
      revealed/turned-up card), not as a filter ON the ChangeZone itself —
      :func:`iter_condition_sites` reaches the nested condition the flat
      effect walk misses;
    * **the named-tutor arm** (fix f) — a ``SearchLibrary`` naming a SPECIFIC
      card (a ``Named`` filter property) carries NO type_filters at all (CR
      201.4 — a name isn't a type), so the existing core/subtype fallbacks
      both come up empty for the "Herald" cycle (Angel's Herald et al.),
      Kassandra/Shaun & Rebecca's named-companion tutors, and self-tutors
      (Llanowar Sentinel, Elvish Clancaller). Corpus census (2026-07, every
      commander-legal named+coreless tutor paired with a ``ChangeZone
      {Battlefield}``): zero target a land — every hit names a creature —
      so a Named property alone is sufficient type evidence for THIS narrow
      shape (still zero-guess for every other coreless case).

    A Graveyard origin is reanimation (a different lane, checklist #2). Scope
    "you".

    ADR-0038 W3 batch 6 widens the ChangeZoneAll/origin=None reanimation
    exclusion two more ways (both zero-guess, CR 400.1 / 400.3 / 610.3c):

    * **exile-as-graveyard-workaround, target-filter form** — Boneyard
      Parley's "Exile up to five target creature cards from graveyards...
      Put all cards from the pile of your choice onto the battlefield"
      ALSO exiles a graveyard-standing pile first, but (unlike Living
      Death's tracked ``origin='Graveyard'``) the EARLIER ``ChangeZone``
      leaves ``origin=None`` and carries the ``InZone: Graveyard`` evidence
      on its own TARGET filter instead — the sibling scan now reads that
      filter too, not just the origin field;
    * **direct graveyard ChooseFromZone** — Rejoin the Fight's "Mill three
      cards... each opponent chooses a creature card in your graveyard...
      Return each card chosen this way to the battlefield" reanimates via a
      ``ChooseFromZone{zone: Graveyard}`` selector, no ``ChangeZone`` at
      all — the sibling scan also excludes on that shape.

    A THIRD gate closes a distinct false-positive class: Livio, Oathsworn
    Sentinel's "Return all exiled cards with aegis counters on them to the
    battlefield under their owners' control" reads the SAME ChangeZoneAll
    shape as Warp World, but its filter carries a ``Counters`` property (an
    "exiled WITH a counter" persistent-pile marker — the SAME structural
    signature the exile_matters lane's "exiled with ~" arm reads) sourced
    from a TARGETED battlefield creature (its own EARLIER activated ability
    exiles "another target creature", not a hand/library/graveyard/reveal
    source) that explicitly returns to its OWNER, not the caster — a
    temporary-exile REMOVAL effect (Banisher-Priest class), not a cheat
    build-around; no "you" benefit at all (CR 610.3c — a returned object
    defaults to its owner's control absent an explicit transfer). A
    Counters-gated filter is a NARROW, corpus-verified tell (2026-07 census
    of every commander-legal ``ChangeZoneAll{Battlefield, origin: None}``:
    Livio is the SOLE Counters-bearing filter in the population — Warp
    World / Over the Top / Manabond / Tezzeret, Master of the Bridge / Pyxis
    of Pandemonium all carry EMPTY filter properties, so gating narrowly on
    Counters-presence (rather than a blanket "prove you-benefit" rule, which
    regressed those five in an earlier attempt this session) leaves every
    other gain untouched — still zero-guess: a Counters-gated pile that DOES
    explicitly return under "you" stays included.

    ADR-0038 W5 tails (77 live_only at session start) adds SIX more typed,
    zero-guess arms (each detailed inline at its own site below): (g) a
    same-unit ``tutor``/``reveal_hand`` sibling is search-and-put evidence
    even when the put's own origin is untracked (None), gated to reject a
    sibling tutor's Land-mixed-with-nonland filter unless the put carries
    an explicit ``enters_under: You``; (h) the Dig arm gains the SAME
    subtype-only fallback fix (a) already gives the ChangeZone arm; (i) a
    ``ChangeZoneAll{Battlefield, origin: Exile}`` with a bare, untyped
    ``TrackedSet`` target reads its type evidence off the SAME unit's
    earlier LIBRARY-sourced exile producer, narrowly excluding a self-blink
    shape (Sword of Hearth and Home) that shares the outer node shape; (j)
    ``ExileFromTopUntil`` (mutate's exile-until-match idiom, CR 702.140a)
    reads its ``NextMatches`` condition; (k) ``exile_top`` joins the fix
    (e) reveal-producer gate; (l) the planeswalker "you get an emblem
    with...search your library...put it onto the battlefield" idiom is
    read via the SAME ``iter_nested_trigger_defs`` descent every other
    granted-ability lane uses. Post-fix: both=373, live_only=54.

    ADR-0038 W5b adds a sibling nested-descent pair
    (:func:`_nested_grant_reveal_or_hand_put`, called alongside
    :func:`_nested_emblem_tutor_put` at the bottom of this function): a
    ``GrantTrigger``/``CreateEmblem`` granted trigger's OWN raw chain
    carrying a ``RevealUntil{kept_destination: Battlefield}`` (Shifting
    Shadow, Time Lord Regeneration) or a Hand-origin ``ChangeZone
    {Battlefield}`` (Hunting Grounds, Summoner's Grimoire) — the SAME two
    shapes the top-level arms already read, just nested inside a granted
    ability's construct (CR 603.1 / 400.7). Narrowly gated to origin
    ``'Hand'`` for the ChangeZone half: a 2026-07 corpus census of every
    commander-legal nested-granted-trigger chain found a large
    self-reanimation class (Feign Death, Undying Malice, Rekindling
    Phoenix, Liliana, Waker of the Dead, …) riding the SAME outer shape,
    but every one carries either an explicit ``origin: 'Graveyard'`` or an
    untyped, subject-less filter (a back-reference to the just-died/
    exiled creature, not a type search) — so gating the origin allow-list
    to ``'Hand'`` alone (Library-origin nested ChangeZone is already the
    SearchLibrary+ChangeZone tutor pair :func:`_nested_emblem_tutor_put`
    reads) plus the existing never-guess type-evidence gate excludes the
    whole reanimation class with zero extra carve-outs, verified corpus-
    wide (0 false hits). Post-fix: both=377, live_only=50 — the remaining
    50 are genuinely diverse: planeswalker loot engines with a swallowed
    "or" condition, several Unimplemented parse-failure residues needing
    clause-grammar growth this session explicitly avoided, position-
    relative reveal/put idioms with no recoverable type evidence, a phase
    ``kept_destination`` mis-parse (Chaos Mutation — upstream candidate,
    not coded around), a genuine no-type-evidence SELF-put shed shape
    ("put THIS card from your hand onto the battlefield", a self-reference
    with no core/subtype filter at all rather than a type search — Talon
    Gates of Madara, Gaea's Touch; both correctly never-guess, confirmed
    ``cores=()`` at their ChangeZone node), and modal reveal-choice idioms
    whose type check lives inside a swallowed Unimplemented clause
    (Selective Adaptation, Guild Feud) — beyond this session's budget. Key
    stays in _STAGE4_RESIDUAL.
    """
    for unit in tree.units:
        if unit.kind == "BeginGame":
            continue
        for c in unit.effect_concepts("change_zone"):
            node_tag = tag_of(c.node)
            if node_tag not in ("ChangeZone", "ChangeZoneAll"):
                continue
            origin, dest = change_zone_dirs(c.node)
            if dest != "Battlefield":
                continue
            # Fix (c): ChangeZoneAll (the SYMMETRIC "each player puts
            # revealed permanent cards onto the battlefield" idiom — Warp
            # World, Over the Top) is reveal-sourced with an UNTRACKED origin
            # (None), not "Hand"/"Library" like a tracked search/discard — so
            # it additionally accepts None, GATED on mass-REANIMATION tells
            # (checklist #2; CR 400.1 / 400.3) phase leaves origin=None for
            # too: the target filter carrying an ``InZone: Graveyard``
            # property (Faith's Reward / Second Sunrise read a
            # Graveyard-standing pile DIRECTLY), an EARLIER Graveyard-origin
            # zone change in the SAME unit (Living Death / Scrap Mastery
            # exile their graveyard FIRST, then put the just-exiled pile
            # onto the battlefield), an earlier untracked-origin ``exile``
            # whose OWN target filter carries the Graveyard evidence instead
            # (batch 6 — Boneyard Parley), or an earlier direct
            # ``ChooseFromZone{zone: Graveyard}`` selector (batch 6 — Rejoin
            # the Fight) — the exile is a rules workaround for the symmetric
            # wording / an intermediate staging step, not a genuine cheat
            # build-around; all four are the classic EDH "reanimator" shape.
            if node_tag == "ChangeZoneAll" and origin is None:
                if "Graveyard" in filter_inzone_zones(effect_filter(c.node)):
                    continue
                if any(
                    change_zone_dirs(other.node)[0] == "Graveyard"
                    for other in unit.effects
                    if other.concept == "change_zone"
                ):
                    continue
                if any(
                    tag_of(other.node) == "ChangeZone"
                    and getattr(other.node, "destination", None) == "Exile"
                    and "Graveyard" in filter_inzone_zones(effect_filter(other.node))
                    for other in unit.effects
                ):
                    continue
                if any(
                    tag_of(other.node) == "ChooseFromZone"
                    and getattr(other.node, "zone", None) == "Graveyard"
                    for other in unit.effects
                ):
                    continue
                # Batch 6 — the Livio "temporary-exile removal" gate: a
                # Counters-gated filter (an "exiled WITH a counter"
                # persistent pile) that does NOT explicitly return under
                # "you" is a targeted removal-and-release, not a cheat (CR
                # 610.3c — defaults to the OWNER's control). Narrow: only
                # bites when the filter itself carries a Counters property.
                own_filter = effect_filter(c.node)
                own_props = getattr(own_filter, "properties", None) or []
                has_counters_gate = any(tag_of(p) == "Counters" for p in own_props)
                enters_under = getattr(c.node, "enters_under", None)
                if has_counters_gate and enters_under != "You":
                    continue
                allowed_origins: tuple[str | None, ...] = (None,)
            elif (
                node_tag == "ChangeZoneAll"
                and origin == "Exile"
                and tag_of(getattr(c.node, "target", None)) == "TrackedSet"
            ):
                # ADR-0038 W5 tails — a ChangeZoneAll{Battlefield, origin:
                # Exile} whose target is a BARE TrackedSet (no filter of its
                # own) is the "reveal/dig/search a pile, exile it, then put
                # the whole pile onto the battlefield" idiom (Indomitable
                # Creativity, Dubious Challenge, Thunderous Debut — CR
                # 400.7), reading its type evidence off the SAME unit's
                # earlier exile-populating producer (see
                # :func:`_sibling_exile_producer_cores`). Narrowly gated to
                # the bare ``TrackedSet`` tag: a filtered/marker target
                # (``TrackedSetFiltered``, ``ExiledBySource``, an ``And``
                # combining them) is the DIFFERENT persistent-pile /
                # self-blink shape (Livio's Counters-gated removal-and-
                # release, Cold Storage's self-protect blink, Parallax
                # Wave's delayed-trigger flicker) this widening never
                # touches — those either fall through to the existing
                # Counters gate above or stay excluded (no code path
                # reaches them via this ``elif``, since it requires the
                # EXACT ``TrackedSet`` tag).
                allowed_origins = ("Exile",)
            else:
                allowed_origins = ("Hand", "Library")
                # ADR-0038 W5 tails — a plain ChangeZone{Battlefield} whose
                # origin is untracked (None) is STILL the search-and-put
                # idiom when the SAME unit carries a sibling ``tutor``
                # (SearchLibrary — Finale of Devastation, Boonweaver Giant,
                # Runed Crown, Vision Quest: "search your library[, hand,
                # graveyard] for X and put it onto the battlefield") or
                # ``reveal_hand`` (Zara, Treacherous Urge, Wild Evocation:
                # "look at/reveal [a] hand... put a card from it onto the
                # battlefield") producer — phase leaves the put's origin
                # untracked for these idioms far more often than "Hand"/
                # "Library" (only Bribery-shaped single-zone searches carry
                # a tracked origin). Multi-zone tutors (source_zones
                # touching Graveyard ALONGSIDE Hand/Library) stay included
                # here too — CR 400.7 makes no distinction by source zone;
                # a PURE graveyard-only return is a different shape
                # (ChangeZone{origin: Graveyard} directly, the reanimation
                # lane, checklist #2) that this widening never touches
                # (origin is still gated to None, never 'Graveyard').
                # Corpus census (2026-07, every commander-legal same-unit
                # tutor/reveal_hand + ChangeZone{Battlefield, origin: None}
                # pair): 46 tutor hits, 5 reveal_hand hits, zero pure-
                # graveyard-only tutors among them (every Graveyard-touching
                # one also searches Hand and/or Library) — the downstream
                # cores/subs type-evidence gate (unchanged) still declines
                # to guess on the no-evidence ones (Retraced Image,
                # Eladamri's ambiguous hand-or-library reveal).
                #
                # ADR-0038 W6 endgame — the SAME untracked-origin trust
                # extends to a ``dig``/``reveal_top``/``exile_top`` sibling
                # (Call to the Kindred's tribal ``Dig``, Lord of the Void's
                # ``ExileTop``, Lonis's opponent-library ``RevealTop``,
                # Anzrag's Rampage's artifact-count ``ExileTop``): these
                # producers ALSO populate a library/exile-top TrackedSet the
                # ChangeZone's own ``target=TrackedSetFiltered`` names by
                # its OWN core type (read by :func:`_change_zone_all_cores`
                # below — never borrowed from the sibling), so admitting
                # ``None`` here only ever lets the DOWNSTREAM cores read
                # proceed; it never manufactures type evidence on its own.
                # Corpus-verified narrow (2026-07 census of every
                # commander-legal ``dig``/``reveal_top``/``exile_top`` +
                # ChangeZone{Battlefield, origin: None} pair, 63 hits):
                # Zimone's Experiment's land-only ``TrackedSetFiltered``
                # still excludes via the unchanged ``cores <= {"Land"}``
                # gate below; Sword of Hearth and Home / Cold Storage /
                # Parallax Wave class self-blinks never reach this branch
                # at all (a bare back-reference target carries no filter,
                # so cores/subs both stay empty and the never-guess gate
                # holds).
                _untracked_producers = (
                    "tutor",
                    "reveal_hand",
                    "dig",
                    "reveal_top",
                    "exile_top",
                )
                if origin is None and (
                    any(c.concept in _untracked_producers for c in unit.effects)
                    # CR 607.2a: a "put a creature card EXILED THIS WAY onto
                    # the battlefield" put declares its exile provenance ON
                    # ITS OWN TARGET — a TrackedSetFiltered stamped
                    # ``caused_by: Exiled`` / an ``ExiledBySource`` filter
                    # predicate is phase's typed form of that linked-exile
                    # reference. Needed since v0.35.2 for Anzrag's Rampage:
                    # its "exile the top X cards ... where X is ..." producer
                    # clause now fails honestly (an Unimplemented
                    # ``where_x_binding`` residue, the v0.24.0 bind-or-fail
                    # policy), so no exile_top sibling survives — but the
                    # put's own target still carries the linkage. Only ever
                    # ADMITS the pair; the downstream cores gate is
                    # unchanged and still never manufactures type evidence.
                    or _tracked_target_exile_caused(c.node)
                ):
                    allowed_origins = ("Hand", "Library", None)
            if origin not in allowed_origins:
                # Fix (f): a named tutor with no type evidence still pairs
                # with a target-less put (origin untracked — Kassandra's
                # ANY-zone search) — the Kassandra / Shaun & Rebecca shape.
                if _sibling_named_tutor_no_core(unit):
                    return [
                        Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")
                    ]
                continue
            cores = set(_change_zone_all_cores(c.node))
            if not cores and node_tag == "ChangeZoneAll" and origin == "Exile":
                cores = _sibling_exile_producer_cores(unit)
            if not cores:
                cores = _sibling_selector_cores(unit)
                # ADR-0038 W5 tails — a sibling tutor's filter MIXING Land
                # with a non-Land core (Archdruid's Charm: "search for a
                # creature OR LAND card... put it onto the battlefield
                # TAPPED if it's a land card. Otherwise, put it into your
                # hand.") is a MODAL type-conditional the substrate
                # collapsed onto ONE unconditional ChangeZone — phase drops
                # the "otherwise hand" branch entirely, so the mixed set
                # can't be trusted as "this exact set enters the
                # battlefield" (never guess). Require the stronger
                # ``enters_under: You`` marker (an EXPLICIT "under your
                # control" grant) to trust a mixed set — Eternal Dominion's
                # genuine unconditional multi-type Bribery-class cheat
                # ("Search target opponent's library for an artifact,
                # creature, enchantment, or land card. Put that card onto
                # the battlefield under your control.") carries it; the
                # modal-collapse shape never does.
                if (
                    "Land" in cores
                    and len(cores) > 1
                    and getattr(c.node, "enters_under", None) != "You"
                ):
                    cores = set()
            if not cores:
                # Fix (a): subtype-only type evidence (cores empty on both the
                # effect's own filter and the sibling selector).
                subs = {s.lower() for s in filter_subtypes(effect_filter(c.node))}
                if not subs:
                    subs = {s.lower() for s in _sibling_selector_subtypes(unit)}
                if not subs or subs & _LAND_SUBTYPES:
                    # Fix (f): a Library-origin named tutor with no type
                    # evidence at all — the "Herald" cycle / Llanowar
                    # Sentinel / self-tutor shape (origin IS tracked here,
                    # unlike Kassandra's ANY-zone search above).
                    if _sibling_named_tutor_no_core(unit):
                        return [
                            Signal(
                                "cheat_into_play", "you", "", c.raw, tree.name, "high"
                            )
                        ]
                    continue  # no type evidence / a land put — never guess
            elif cores <= {"Land"}:
                continue  # land carve-out (ramp, not a cheat)
            if _directed_search_sibling(unit):
                continue  # another player's compensation fetch, not yours
            return [Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")]
        # Fix (b): the non-land Dig→Battlefield arm (mirrors _extra_land_drop's
        # dig arm with the complementary type gate). ADR-0038 W5 tails adds
        # the SAME subtype-only fallback fix (a) already gives the ChangeZone
        # arm: a Dig filter naming ONLY a subtype (Armored Skyhunter's Aura-
        # or-Equipment cheat, Gilgamesh's Equipment-only, Nine-Fingers
        # Keene's Gate, Nick Fury's Hero/Equipment/Vehicle) carries no CORE
        # type at all (CR 205.3 — a subtype isn't a core type), so the
        # core-only read came up empty and never guessed; the subtype read
        # is still zero-guess (a land-subtype filter is still excluded).
        for c in unit.effect_concepts("dig"):
            if getattr(c.node, "destination", None) != "Battlefield":
                continue
            filt = getattr(c.node, "filter", None)
            cores = set(filter_core_types(filt))
            if not cores:
                subs = {s.lower() for s in filter_subtypes(filt)}
                if not subs or subs & _LAND_SUBTYPES:
                    continue  # no type evidence / a land put — never guess
            elif cores <= {"Land"}:
                continue  # land put (extra_land_drop) / no evidence — no guess
            return [Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")]
        # Fix (d): the RevealUntil→Battlefield arm. ADR-0038 W6 endgame
        # widens the destination read to ALSO accept ``kept_optional_to ==
        # "Battlefield"`` — phase's typed field for the "you may put that
        # card onto the battlefield [otherwise it stays with the rest]"
        # OPTIONAL idiom (Hei Bai's Shrine dig, Songbirds' Blessing's Aura
        # dig, Genesis Storm's nonland-permanent dig): the default
        # ``kept_destination`` there is "Hand"/"Library" (where the card
        # goes if you DON'T exercise the option), while the real put site is
        # the separate ``kept_optional_to`` field fix (d) never read. Same
        # never-guess core/subtype type-evidence gate either way.
        for c in unit.effects:
            if c.concept != "reveal_until":
                continue
            kept_to = getattr(c.node, "kept_destination", None)
            kept_optional_to = getattr(c.node, "kept_optional_to", None)
            if kept_to != "Battlefield" and kept_optional_to != "Battlefield":
                continue
            filt = getattr(c.node, "filter", None)
            cores = set(filter_core_types(filt))
            if not cores:
                subs = {s.lower() for s in filter_subtypes(filt)}
                if not subs or subs & _LAND_SUBTYPES:
                    continue  # no type evidence / a land put — never guess
            elif cores <= {"Land"}:
                continue
            return [Signal("cheat_into_play", "you", "", c.raw, tree.name, "high")]
        # Fix (e): the RevealedHasCardType-conditioned put — gated to a unit
        # that actually REVEALS/imprints a card (reveal_top / reveal_until /
        # dig / turn_face_up). ``RevealedHasCardType`` is reused by phase for
        # an unrelated "is the TARGETED card an artifact creature" check too
        # (Brilliance Unleashed's graveyard reanimation target) — a bare
        # condition match with no reveal producer is that lane, not this one;
        # a Graveyard-sourced return stays reanimation (checklist #2).
        # ``TriggeringSource`` is accepted ONLY here, immediately following a
        # ``turn_face_up`` in the SAME sub-ability chain (Clone Shell /
        # Summoner's Egg's imprint cycle: "turn the exiled card face up... put
        # it onto the battlefield" — the back-reference names the
        # just-revealed card in this position, CR 701.36c; landmine #7i —
        # corpus-verified card-by-card against the two named imprint cards,
        # not a blanket TriggeringSource read). Batch 6 widens the condition
        # tag accepted: a ``TargetMatchesFilter`` on the SAME reveal-then-put
        # chain is the SAME "if it's a permanent/creature/land card" check
        # phase sometimes structures as a target-match instead of a
        # ``RevealedHasCardType`` (Chaos Warp — "reveals the top card...If
        # it's a permanent card, they put it onto the battlefield"); corpus
        # census (2026-07, every commander-legal reveal-producing unit with a
        # Battlefield-destined ParentTarget/SelfRef/TriggeringSource put):
        # every ``TargetMatchesFilter`` hit besides Yarus (see below) is this
        # exact reveal-then-put idiom (Aid from the Cowl, Skirk Drill
        # Sergeant, N'Yami-Class Mother Ship, Bison Whistle) — no unrelated
        # reuse, so the same reveal-producer + type-evidence gate is
        # sufficient (still zero-guess: a subtype-only match like Bison
        # Whistle's "Bison card" still never fires, no core type evidence).
        # Yarus, Roar of the Old Gods closes a DISTINCT false-positive the
        # widening exposed in the TriggeringSource+turn_face_up carve-out
        # itself: "Whenever a face-down creature you control DIES, return it
        # to the battlefield... if it's a permanent card, then turn it face
        # up" is dies_recursion (checklist #2 — CR 700.4), not a cheat. The
        # ORIGINAL carve-out required merely "a turn_face_up somewhere in the
        # unit" — too loose: landmine #7i's back-reference is
        # POSITION-relative, so what matters is CHAIN ORDER, not presence.
        # Clone Shell / Summoner's Egg chain ``turn_face_up`` FIRST, then the
        # ``change_zone`` (the put reads the JUST-turned-face-up imprinted
        # card via the forwarded ``TriggeringSource``); Yarus chains the
        # ``change_zone`` FIRST (returning the just-DIED creature itself),
        # THEN turns it face up — the put's ``TriggeringSource`` there is the
        # ORIGINAL dies-trigger subject, not a forwarded turn_face_up result.
        # ``unit.effects`` preserves the linear sub_ability chain order
        # (verified 2026-07), so requiring the turn_face_up's index precede
        # the change_zone's index is a precise, zero-guess chain-order read.
        _reveal_producers = _CHEAT_REVEAL_PRODUCERS
        if any(c.concept in _reveal_producers for c in unit.effects):
            effects_list = list(unit.effects)
            turn_face_up_idx = next(
                (i for i, c in enumerate(effects_list) if c.concept == "turn_face_up"),
                None,
            )
            for idx, c in enumerate(effects_list):
                if c.concept != "change_zone":
                    continue
                if getattr(c.node, "destination", None) != "Battlefield":
                    continue
                tgt = getattr(c.node, "target", None)
                tgt_tag = tag_of(tgt)
                turn_face_up_precedes = (
                    turn_face_up_idx is not None and turn_face_up_idx < idx
                )
                if tgt_tag not in ("ParentTarget", "SelfRef") and not (
                    tgt_tag == "TriggeringSource" and turn_face_up_precedes
                ):
                    continue
                # task #91 — Chaos Warp's put rides THIS exact branch (a
                # reveal_top producer + a TargetMatchesFilter condition,
                # below): "The owner of target permanent shuffles it into
                # their library, then reveals the top card...they put it
                # onto the battlefield" — the beneficiary is the OWNER of
                # the shuffled permanent, not the caster
                # (:func:`_target_owner_beneficiary_scope`, CR 108.3). Gated
                # on a same-unit ``ParentTargetOwner`` recipient (the
                # Shuffle/RevealTop siblings) — corpus-verified the ONLY
                # commander-legal card reaching this branch with that
                # pairing; every other named card here (Aid from the Cowl,
                # Call of the Wild, Clone Shell, Polymorph, …) keeps "you".
                cheat_scope = "you"
                if any(
                    recipient_tag(c2.node) == "ParentTargetOwner" for c2 in unit.effects
                ):
                    override = _target_owner_beneficiary_scope(unit)
                    if override is not None:
                        cheat_scope = override
                # ADR-0038 W5 tails — ``ExileFromTopUntil`` (phase's mutate
                # "exile cards from the top of your library until you
                # exile a [type] card" idiom — Illuna, Apex of Wishes'
                # "Whenever this creature mutates, exile cards from the top
                # of your library until you exile a nonland permanent
                # card. Put that card onto the battlefield or into your
                # hand" — CR 702.140a) carries its OWN type evidence on a
                # ``NextMatches`` condition wrapping its ``until`` field,
                # not as a separate unit-level Condition site the
                # ``RevealedHasCardType`` / ``TargetMatchesFilter`` walk
                # below finds (crosswalk.py already maps the phase tag to
                # the ``reveal_until`` concept, so it already satisfies the
                # producer gate above — only the type-evidence SITE
                # differs).
                until_types: set[str] = set()
                for sib in unit.effects:
                    if tag_of(sib.node) != "ExileFromTopUntil":
                        continue
                    until = getattr(sib.node, "until", None)
                    if tag_of(until) == "NextMatches":
                        until_types |= set(
                            filter_core_types(getattr(until, "filter", None))
                        )
                if until_types and not until_types <= {"Land"}:
                    return [
                        Signal(
                            "cheat_into_play", cheat_scope, "", c.raw, tree.name, "high"
                        )
                    ]
                found_condition_evidence = False
                for cond in iter_condition_sites(unit.node):
                    cond_tag = tag_of(cond)
                    if cond_tag == "RevealedHasCardType":
                        types = set(getattr(cond, "card_types", None) or [])
                    elif cond_tag == "TargetMatchesFilter":
                        types = set(filter_core_types(getattr(cond, "filter", None)))
                    else:
                        continue
                    found_condition_evidence = True
                    if not types or types <= {"Land"}:
                        continue  # no type evidence / a land put — never guess
                    return [
                        Signal(
                            "cheat_into_play", cheat_scope, "", c.raw, tree.name, "high"
                        )
                    ]
                # ADR-0038 W6 endgame — when the chain carries NO type-
                # checking condition at all (Whiskervale Forerunner's
                # "if it's your turn" is a TIMING gate, not a type gate;
                # Break Out's "if that card has mana value 2 or less" is
                # swallowed with no residue), the SAME reveal-producer's OWN
                # filter (:func:`_reveal_producer_cores` /
                # :func:`_reveal_producer_subtypes` — the ``dig``/
                # ``reveal_top``/``exile_top`` counterpart of
                # :func:`_sibling_selector_cores`) is still real type
                # evidence. Only tried when the condition walk found NOTHING
                # type-shaped (never overrides an explicit land-only
                # condition that already declined to guess).
                if not found_condition_evidence:
                    cores = _reveal_producer_cores(unit)
                    if cores and not cores <= {"Land"}:
                        return [
                            Signal(
                                "cheat_into_play", "you", "", c.raw, tree.name, "high"
                            )
                        ]
                    if not cores:
                        subs = {s.lower() for s in _reveal_producer_subtypes(unit)}
                        if subs and not subs & _LAND_SUBTYPES:
                            return [
                                Signal(
                                    "cheat_into_play",
                                    "you",
                                    "",
                                    c.raw,
                                    tree.name,
                                    "high",
                                )
                            ]
    # ADR-0038 W5 tails — the planeswalker "you get an emblem with 'At the
    # beginning of your end step, search your library for a [type] card,
    # put it onto the battlefield, then shuffle'" idiom (Tezzeret, Artifice
    # Master; Garruk, Unleashed; Kaito Shizuki — CR 400.7 / 121.4a): the
    # SAME search-and-put pair the main ChangeZone arm above already reads,
    # just nested inside the emblem's OWN granted trigger definition
    # (``CreateEmblem.triggers[].execute`` / a linear ``S_execute`` →
    # ``S_sub_ability`` chain of raw phase effect nodes, not a flat
    # ``unit.effects`` ConceptNode list) — reached via the SAME
    # ``iter_nested_trigger_defs`` shared descent every other
    # granted-ability lane uses (module note above :func:`iter_nested_
    # trigger_defs`).
    for unit in tree.units:
        if _nested_emblem_tutor_put(unit):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
    # ADR-0038 W5b — a NESTED ``GrantTrigger`` (a static ability granting a
    # triggered ability, CR 603.1 — Shifting Shadow's Aura "At the
    # beginning of your upkeep, destroy this creature. Reveal cards...put
    # that card onto the battlefield...", Hunting Grounds's Threshold
    # "Whenever an opponent casts a spell, you may put a creature card
    # from your hand onto the battlefield.") carries the SAME reveal-until
    # / hand-put shapes the top-level arms above already read, just on the
    # UN-flattened granted-trigger chain (:func:`iter_nested_trigger_defs`,
    # the same descent :func:`_nested_emblem_tutor_put` uses for the tutor
    # shape). A 2026-07 corpus census of every commander-legal nested
    # granted-trigger chain found the SAME reanimation contamination risk
    # the top-level arm's Graveyard carve-out already guards (Feign Death /
    # Undying Malice / Rekindling Phoenix / Liliana, Waker of the Dead
    # class "return this creature to the battlefield" self-reanimation) —
    # every one of those carries origin ``'Graveyard'`` OR an untyped,
    # subject-less ``ChangeZone`` (no core/subtype filter at all, since the
    # reanimated card is a back-reference to the JUST-exiled/died creature,
    # not a type search), so the SAME never-guess type-evidence gate
    # already excludes them with no extra carve-out needed — verified: 0
    # false hits across the full census when gated to (Hand-origin ChangeZone
    # WITH type evidence) / (Battlefield-kept RevealUntil WITH type
    # evidence). CR 400.7.
    for unit in tree.units:
        if _nested_grant_reveal_or_hand_put(unit):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
    # ADR-0039 W7 endgame — two scan-scope closers. crosswalk.py's
    # ``_EFFECT_CHILD_FIELDS`` (``effect``/``sub_ability``/``execute``/
    # ``mode_abilities``) never walks a ``ChooseOneOf``'s ``branches`` list
    # or any node's ``else_ability`` field — every OTHER consumer wants the
    # CHOSEN branch / the TAKEN arm, not every possibility, so ``unit.
    # effects`` silently drops a Battlefield put that lives in either
    # container. cheat_into_play is a "may put"/"otherwise put" possibility
    # lane, so descending into both is correct here (see each helper's
    # docstring for the corpus-verified narrow blast radius).
    for unit in tree.units:
        if _cheat_choose_one_of_battlefield_put(unit):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
        if _cheat_negated_reveal_else_put(unit):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
        if _cheat_reveal_until_you_enters_put(unit):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
    # ADR-0039 grammar sprint (task #82) — the tree-synthesis closer for the
    # three retired grammar-straggler bridges (former bridge_ledger.py rows
    # ``cheat_player_prefix_battlefield_put`` / ``cheat_choose_from_among_
    # graveyard_origin`` / ``cheat_synthetic_destiny_delayed_reveal``): each
    # tree_synthesis arm ports the bridge's own verbatim regex onto a
    # SHARED marker concept (tree_synthesis.py), so membership is provably
    # unchanged — a structural read of the synthesized node, not a widened
    # text match.
    if tree.has_effect("synth_cheat_reveal_or_put_battlefield"):
        return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
    # ADR-0039 W7 ledgered bridges — the residual grammar-straggler /
    # dropped-clause / upstream-parse-failure bucket (bridge_ledger.py rows,
    # docstring there for the full corpus accounting):
    for bridge_id in (
        "cheat_dropped_clause_zero_residue",
        "cheat_kept_destination_hand_misparse",
        "cheat_modal_mode_unsupported_qualifier",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("cheat_into_play", "you", "", "", tree.name, "high")]
    return []


def _cheat_reveal_until_you_enters_put(unit: AbilityUnit) -> bool:
    """ADR-0039 W7 — a ``reveal_until`` sibling earns the SAME None-origin
    trust :data:`_untracked_producers` gives ``tutor``/``dig``/etc, but ONLY
    for a put that ALSO carries an explicit ``enters_under: You`` marker
    (Telemin Performance: "Target opponent reveals cards from the top of
    their library until they reveal a creature card. That player puts all
    noncreature cards revealed this way into their graveyard, THEN YOU put
    the creature card onto the battlefield UNDER YOUR CONTROL" — a SEPARATE
    ``ChangeZone`` sentence trailing the ``RevealUntil``, unlike fix (d)'s
    own ``kept_destination`` read, so it needs its own arm). Type evidence
    is the ``RevealUntil`` sibling's OWN filter (Creature) — read here
    rather than widening the shared :func:`_sibling_selector_cores` (which
    the MAIN arm also calls for every other ChangeZone case), keeping the
    blast radius to this one arm. Gated narrow to ``enters_under: You``
    specifically: a bare ``reveal_until`` sibling with no such marker
    (Illuna, Apex of Wishes' mutate trigger — a DIFFERENT node the
    existing ``until_types`` arm above already reads via its own
    ``ExileFromTopUntil`` condition) stays excluded — corpus-verified sole
    hit (2026-07, every commander-legal ``reveal_until`` sibling + Change-
    Zone{Battlefield, origin: None} pair): Telemin Performance.
    """
    revealers = [c for c in unit.effects if c.concept == "reveal_until"]
    if not revealers:
        return False
    for c in unit.effects:
        if c.concept != "change_zone" or tag_of(c.node) != "ChangeZone":
            continue
        if getattr(c.node, "destination", None) != "Battlefield":
            continue
        if getattr(c.node, "origin", None) is not None:
            continue
        if getattr(c.node, "enters_under", None) != "You":
            continue
        cores: set[str] = set()
        subs: set[str] = set()
        for rv in revealers:
            filt = effect_filter(rv.node)
            cores |= set(filter_core_types(filt))
            subs |= set(filter_subtypes(filt))
        if cores and not cores <= {"Land"}:
            return True
        if not cores and subs and not subs & _LAND_SUBTYPES:
            return True
    return False


def _cheat_choose_one_of_battlefield_put(unit: AbilityUnit) -> bool:
    """ADR-0039 W7 — a modal ``ChooseOneOf`` branch's OWN effect chain
    carrying a Hand/Library-origin ``ChangeZone``/``ChangeZoneAll``
    {Battlefield} (Dr. Eggman's villainous-choice: "That player discards a
    card, or you may put a Construct, Robot, or Vehicle card from your hand
    onto the battlefield" — the SECOND branch is a genuine cheat, CR 700.2 /
    400.7). Reads each branch's own filter with the SAME core/subtype +
    land-carve-out gate the top-level ChangeZone arm uses
    (:func:`_change_zone_all_cores` / :func:`filter_subtypes`); origin
    restricted to Hand/Library only — no ``None``-origin sibling-tutor trust
    extension, since this narrow shape never needs one. Corpus-verified
    sole hit (2026-07, every commander-legal ``ChooseOneOf`` branch chain
    carrying a Battlefield-destined ChangeZone/ChangeZoneAll): Dr. Eggman.
    """
    for n in iter_typed_nodes(unit.node):
        if tag_of(n) != "ChooseOneOf":
            continue
        for br in getattr(n, "branches", None) or []:
            for bn in iter_typed_nodes(br):
                if not (
                    tag_of(bn) in ("ChangeZone", "ChangeZoneAll")
                    and getattr(bn, "destination", None) == "Battlefield"
                    and getattr(bn, "origin", None) in ("Hand", "Library")
                ):
                    continue
                cores = set(_change_zone_all_cores(bn))
                if cores:
                    if not cores <= {"Land"}:
                        return True
                    continue
                subs = {s.lower() for s in filter_subtypes(effect_filter(bn))}
                if subs and not subs & _LAND_SUBTYPES:
                    return True
    return False


def _cheat_negated_reveal_else_put(unit: AbilityUnit) -> bool:
    """ADR-0039 W7 — the "otherwise, put it onto the battlefield" arm of a
    reveal-then-branch idiom whose gating condition is NEGATED (Impromptu
    Raid: "Reveal the top card of your library. If it isn't a creature
    card, put it into your graveyard. Otherwise, put that card onto the
    battlefield." — phase structures this as ``condition=Not
    (RevealedHasCardType(Creature))`` on the GRAVEYARD branch's own node,
    with the BATTLEFIELD put living on that SAME node's ``else_ability`` —
    the field :func:`_cheat_choose_one_of_battlefield_put`'s docstring
    explains ``unit.effects`` never reaches). Fix (e)'s existing reveal-
    producer arm only searches ``unit.effects`` for the ChangeZone site, so
    it never finds this one even though its producer gate
    (:data:`_CHEAT_REVEAL_PRODUCERS`) is satisfied — this helper is the
    narrow ``else_ability`` complement of that arm, gated on the SAME
    producer set so it never fires standalone on an unrelated else_ability
    shape. Type evidence is the INNER (un-negated) condition's card types —
    the else fires exactly when that inner condition IS true (CR 726 "if"/
    "otherwise" phrasing — De Morgan's law read off the typed ``Not``
    wrapper, not a guess). Corpus-verified sole hit (2026-07, every
    commander-legal reveal-producing unit whose node carries ``condition=
    Not(RevealedHasCardType)`` and an ``else_ability`` Battlefield put
    targeting ``ParentTarget``/``SelfRef``): Impromptu Raid.
    """
    if not any(c.concept in _CHEAT_REVEAL_PRODUCERS for c in unit.effects):
        return False
    for n in iter_typed_nodes(unit.node):
        cond = getattr(n, "condition", None)
        if tag_of(cond) != "Not":
            continue
        inner = getattr(cond, "condition", None)
        if tag_of(inner) != "RevealedHasCardType":
            continue
        ea = getattr(n, "else_ability", None)
        if not isinstance(ea, TypedMirrorNode):
            continue
        eff = getattr(ea, "effect", None)
        if not (
            isinstance(eff, TypedMirrorNode)
            and tag_of(eff) == "ChangeZone"
            and getattr(eff, "destination", None) == "Battlefield"
            and tag_of(getattr(eff, "target", None)) in ("ParentTarget", "SelfRef")
        ):
            continue
        types = set(getattr(inner, "card_types", None) or [])
        if types and not types <= {"Land"}:
            return True
    return False


def _nested_grant_reveal_or_hand_put(unit: AbilityUnit) -> bool:
    """Whether ``unit`` grants a trigger (:func:`iter_nested_trigger_defs`)
    whose OWN raw effect chain carries a ``RevealUntil{kept_destination:
    Battlefield}`` (Shifting Shadow) or a ``ChangeZone{Battlefield,
    origin: Hand}`` (Hunting Grounds, Summoner's Grimoire) — the nested
    sibling of fix (d)'s top-level RevealUntil arm and the main arm's
    Hand-origin ChangeZone read, applied to the granted trigger's own
    chain. Library-origin nested ChangeZone stays out of scope here — that
    shape is the SearchLibrary+ChangeZone tutor pair
    :func:`_nested_emblem_tutor_put` already reads (Tezzeret, Artifice
    Master; Garruk, Unleashed); a Graveyard-origin nested ChangeZone is
    reanimation (checklist #2) and is never admitted by this narrower
    origin allow-list. Same land carve-out / never-guess type-evidence
    gate (core, else subtype) as every other arm.
    """
    for trig in iter_nested_trigger_defs(unit.node):
        execute = getattr(trig, "execute", None)
        node = execute
        while node is not None:
            eff = getattr(node, "effect", None)
            if isinstance(eff, TypedMirrorNode):
                t = tag_of(eff)
                if t == "RevealUntil" and (
                    getattr(eff, "kept_destination", None) == "Battlefield"
                ):
                    filt = effect_filter(eff)
                    cores = set(filter_core_types(filt))
                    if cores and not cores <= {"Land"}:
                        return True
                    if not cores:
                        subs = {s.lower() for s in filter_subtypes(filt)}
                        if subs and not subs & _LAND_SUBTYPES:
                            return True
                elif (
                    t == "ChangeZone"
                    and getattr(eff, "destination", None) == "Battlefield"
                    and getattr(eff, "origin", None) == "Hand"
                ):
                    cores = set(_change_zone_all_cores(eff))
                    if cores and not cores <= {"Land"}:
                        return True
                    if not cores:
                        subs = {s.lower() for s in filter_subtypes(effect_filter(eff))}
                        if subs and not subs & _LAND_SUBTYPES:
                            return True
            node = getattr(node, "sub_ability", None)
    return False


def _nested_emblem_tutor_put(unit: AbilityUnit) -> bool:
    """Whether ``unit`` grants an emblem/trigger whose OWN raw effect chain
    is a SearchLibrary immediately (before any further Battlefield-destined
    ChangeZone) followed by a ChangeZone{Battlefield} — the nested sibling
    of the main arm's tutor + ``ChangeZone{Battlefield, origin: None}``
    widening, applied to the UN-flattened ``S_execute``/``S_sub_ability``
    chain a granted trigger definition carries (see :func:`iter_nested_
    trigger_defs`). Same land carve-out / never-guess type-evidence gate as
    the main arm, read off the SearchLibrary's own filter (core, else
    subtype) since these raw nodes never route through :func:`effect_
    concepts`.
    """
    for trig in iter_nested_trigger_defs(unit.node):
        execute = getattr(trig, "execute", None)
        chain: list[TypedMirrorNode] = []
        node = execute
        while node is not None:
            eff = getattr(node, "effect", None)
            if isinstance(eff, TypedMirrorNode):
                chain.append(eff)
            node = getattr(node, "sub_ability", None)
        tutor_cores: set[str] = set()
        tutor_subs: set[str] = set()
        found_tutor = False
        for eff in chain:
            t = tag_of(eff)
            if t == "SearchLibrary":
                found_tutor = True
                filt = effect_filter(eff)
                tutor_cores |= set(filter_core_types(filt))
                tutor_subs |= set(filter_subtypes(filt))
            elif (
                found_tutor
                and t == "ChangeZone"
                and getattr(eff, "destination", None) == "Battlefield"
            ):
                cores = set(_change_zone_all_cores(eff)) or tutor_cores
                if cores:
                    if not cores <= {"Land"}:
                        return True
                    continue
                subs = {s.lower() for s in filter_subtypes(effect_filter(eff))}
                if not subs:
                    subs = tutor_subs
                if subs and not subs & _LAND_SUBTYPES:
                    return True
    return False


def _change_zone_all_cores(node: TypedMirrorNode) -> tuple[str, ...]:
    """The CORE types a ``ChangeZone`` / ``ChangeZoneAll`` effect names.

    :func:`effect_filter` reads a plain ``Typed``/``Or``/``And`` filter off
    ``node.target``, but a ``ChangeZoneAll``'s ``target`` is often a
    ``TrackedSetFiltered`` wrapper (Warp World, Over the Top — "each player
    puts all artifact, creature, and land cards revealed this way onto the
    battlefield") carrying the REAL filter one level deeper, on its OWN
    ``.filter`` attribute. Falls back to that nested filter when the direct
    read comes up empty.
    """
    cores = filter_core_types(effect_filter(node))
    if cores:
        return cores
    tgt = getattr(node, "target", None)
    if tag_of(tgt) == "TrackedSetFiltered":
        cores = filter_core_types(getattr(tgt, "filter", None))
    return cores


def _filter_all_named(filt: object) -> bool:
    """Whether every leaf of ``filt`` (recursing ``Or``/``And``) is a
    ``Typed`` filter carrying a ``Named`` property and no core types.

    ADR-0038 W6 endgame generalization of fix (f)'s single-filter check to
    an Or-of-named-alternatives (Agency Outfitter's "search... for a card
    named Magnifying Glass and/or a card named Thinking Cap" —
    ``Or[Typed(Named='magnifying glass'), Typed(Named='thinking cap')]``,
    neither branch carrying a core type of its own). Requires EVERY branch
    to be Named (never trusts a mixed Or with a bare/core-typed branch
    alongside a Named one — that branch carries its own real type evidence
    or none at all, which the ordinary core/subtype gate already reads).
    """
    t = tag_of(filt)
    if t == "Typed":
        if filter_core_types(filt):
            return False
        props = getattr(filt, "properties", None) or []
        return any(tag_of(p) == "Named" for p in props)
    if t in ("Or", "And"):
        subs = getattr(filt, "filters", None) or []
        return bool(subs) and all(_filter_all_named(sub) for sub in subs)
    return False


def _tracked_target_exile_caused(node: TypedMirrorNode) -> bool:
    """Does this ChangeZone's OWN target declare exile provenance — a
    ``TrackedSetFiltered`` stamped ``caused_by: Exiled`` or whose filter
    carries an ``ExiledBySource`` predicate? CR 607.2a: "put a creature card
    exiled this way onto the battlefield" is a linked-exile reference, and
    this tracked-set stamp is phase's typed form of the linkage. Corpus
    census (v0.35.2, 2026-07-24, every commander-legal ChangeZone{
    Battlefield, origin: None} with such a target): exactly 1 hit —
    Anzrag's Rampage, whose exile_top producer clause now fails honestly
    upstream (a ``where_x_binding`` Unimplemented residue) so no sibling
    survives to scan."""
    tgt = getattr(node, "target", None)
    if tag_of(tgt) != "TrackedSetFiltered":
        return False
    if getattr(tgt, "caused_by", None) == "Exiled":
        return True
    filt = getattr(tgt, "filter", None)
    return filt is not None and "ExiledBySource" in filter_predicates(filt)


def _sibling_named_tutor_no_core(unit: AbilityUnit) -> bool:
    """Fix (f): does this unit carry EXACTLY ONE ``SearchLibrary``, naming a
    SPECIFIC card (or an Or of specific cards) with NO type_filters at all
    (:func:`_filter_all_named`) — the "Herald" cycle / Llanowar Sentinel /
    Kassandra / Agency Outfitter shape the existing sibling-core fallback
    can't read (a name isn't a type). Gated to a SINGLE tutor: a unit with
    two-plus tutor calls (Verdant Crescendo's land search + a SEPARATE named
    search that goes to hand, not the battlefield) can't be reliably paired
    to whichever ``ChangeZone`` the caller found — phase leaves no tracked
    link between a specific tutor and its own put, and a second modal
    search's ``ChangeZone`` sometimes carries a mis-tagged ``destination``
    (Verdant Crescendo's hand-bound second search parses ``destination:
    Battlefield`` — a phase-side gap, not fixable from here); one tutor per
    unit is unambiguous."""
    tutors = [c for c in unit.effects if c.concept == "tutor"]
    if len(tutors) != 1:
        return False
    return _filter_all_named(effect_filter(tutors[0].node))


def _sibling_exile_producer_cores(unit: AbilityUnit) -> set[str]:
    """ADR-0038 W5 tails — type evidence for a ``ChangeZoneAll{Battlefield,
    origin: Exile}`` whose own target is a bare, untyped ``TrackedSet``: the
    SAME unit's earlier LIBRARY-sourced exile step that populated the pile
    (Indomitable Creativity's ``RevealUntil{kept_destination: Exile}``,
    Thunderous Debut's ``Dig`` whose own filter carries the type, Dubious
    Challenge's ``ChangeZone{destination: Exile}`` chained after a ``Dig``).

    A bare ``'Card'`` core type — every card in the game, so zero real
    restriction — is EXCLUDED (Auspicious Starrix's mutate "exile... X
    PERMANENT cards" projects as an untyped ``Card`` filter, an upstream
    parse degradation; never guess on it).

    The ``ChangeZone{destination: Exile}`` arm is gated to a LIBRARY-sourced
    exile: either its own ``origin`` is ``'Library'`` (a direct search-and-
    exile, Auspicious Starrix's shape) or the unit ALSO carries a ``dig`` /
    ``reveal_until`` sibling (Dubious Challenge's "look at the top ten
    cards... exile up to two creature cards from among them" — the exile's
    own origin is untracked, but the preceding ``Dig`` proves it's a
    library-top pile). Un-gated, this arm would also catch Sword of Hearth
    and Home's "exile equipped creature [already on the battlefield], then
    return it... under its owner's control" self-blink (origin=None, no
    dig/reveal_until sibling, the exiled object is an EXISTING permanent,
    not a fresh library pile) — corpus-verified narrow (2026-07 census of
    every commander-legal ``ChangeZoneAll{Battlefield, origin: Exile,
    target: TrackedSet}``): only Indomitable Creativity / Dubious Challenge
    / Thunderous Debut / Auspicious Starrix match this whole arm, and
    Starrix's cores still come up empty via the 'Card' exclusion.
    """
    has_reveal_producer = any(
        c.concept in ("reveal_until", "dig") for c in unit.effects
    )
    cores: set[str] = set()
    for c in unit.effects:
        if c.concept == "dig" or (
            c.concept == "reveal_until"
            and getattr(c.node, "kept_destination", None) == "Exile"
        ):
            cores |= set(filter_core_types(effect_filter(c.node)))
        elif (
            c.concept == "change_zone"
            and tag_of(c.node) == "ChangeZone"
            and getattr(c.node, "destination", None) == "Exile"
            and (getattr(c.node, "origin", None) == "Library" or has_reveal_producer)
        ):
            cores |= set(_change_zone_all_cores(c.node))
    return cores - {"Card"}


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


# ADR-0038 W6 endgame — the ``dig``/``reveal_top``/``exile_top`` counterpart
# of :func:`_sibling_selector_cores` / :func:`_sibling_selector_subtypes`,
# used ONLY by the fix-(e) reveal-producer walk (Whiskervale Forerunner's
# own-turn-gated ``Dig``, Break Out's swallowed mv-condition ``Dig``): when
# no ``RevealedHasCardType``/``TargetMatchesFilter`` condition survives on
# the chain, the SAME reveal producer that gates entry into that walk
# already carries real type evidence on its own filter — reading it here
# (rather than widening the shared tutor/dig-only helper, which the MAIN
# ChangeZone arm also calls) keeps the blast radius to fix (e) alone.
def _reveal_producer_cores(unit: AbilityUnit) -> set[str]:
    """The CORE types a sibling ``dig``/``reveal_top``/``exile_top``
    producer names on its own filter."""
    cores: set[str] = set()
    for c in unit.effects:
        if c.concept in ("dig", "reveal_top", "exile_top"):
            cores |= set(filter_core_types(effect_filter(c.node)))
    return cores


def _reveal_producer_subtypes(unit: AbilityUnit) -> set[str]:
    """The SUBTYPE words a sibling ``dig``/``reveal_top``/``exile_top``
    producer names on its own filter."""
    subs: set[str] = set()
    for c in unit.effects:
        if c.concept in ("dig", "reveal_top", "exile_top"):
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


LANES = (
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
)
