"""Crosswalk signal lanes — the b13/b14 keyword-field tables, type matters,
removal + answer types, tutors, and assorted "matters" lanes (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from itertools import chain

from mtg_utils._analysis import signal_keys
from mtg_utils._analysis._subtypes import LAND_SUBTYPES, subtype_card_type
from mtg_utils._analysis.lanes._shared import (
    _PERMANENT_TYPES,
    _RETURN_TARGET_TAGS,
    _root_target_filter,
    _site_raw,
    _tuck_preceded_by_selection,
    recovered_card_recursion,
    sacrifice_actor_scope,
)
from mtg_utils._analysis.signal_base import Signal
from mtg_utils._analysis.text_reads import (
    _ACTIVATED_ABILITY_DROP_EFFECTS,
    _EVERGREEN_CK,
)
from mtg_utils._analysis.tree_synthesis import (
    ETB_TRIGGER_EVENTS,
    has_own_target_spell,
    has_permanent_recast,
    has_repeatable_engine,
    has_self_dies_value,
    has_self_etb_payload,
    has_self_etb_value,
    has_structural_crimes_matter,
    has_structural_curse_matters,
    has_structural_outlaw,
    has_structural_proliferate,
    has_structural_pump_makers,
    has_structural_self_counter_grow,
    has_structural_suspend_matters,
    has_structural_theft_makers,
    has_structural_tutor,
    has_structural_untap_engine,
    has_value_tap_ability,
    mass_death_amount,
    structural_keyword_subjects,
    structural_land_fetch_split,
    structural_type_subjects,
    structural_untap_scope,
    structural_untap_subject,
)
from mtg_utils._card_ir.crosswalk import (
    _OPPONENT_ACTOR_TAGS,
    CREATURE_OR_PERMANENT,
    MASS_FILTER_EFFECT_TAGS,
    SUSPENDED_CARD,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    affected_tag,
    cast_with_keyword_name,
    change_zone_dirs,
    color_keyed_sites,
    controller_paid_cost_leaves,
    counter_kind,
    damage_recipient,
    effect_filter,
    effect_owner_player_scope,
    effect_player_reach,
    effect_reaches_permanent,
    filter_color_predicates,
    filter_controller,
    filter_controller_side,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    forages,
    granted_alt_cost_kinds,
    granted_keyword_names,
    graveyard_recursion,
    has_filter_property,
    has_nested_damage_reaching,
    iter_cost_leaves,
    iter_mod_sites,
    iter_nested_granted_effect_concepts,
    iter_static_defs,
    iter_typed_nodes,
    iter_unit_trigger_defs,
    keyword_resource_events,
    mod_keyword_name,
    mod_value,
    named_filter_subtypes,
    negative_pt_field,
    overload_sweep,
    pt_mod_signs,
    recipient_tag,
    recursion_card_types,
    sacrifice_names_no_player,
    static_mode_field,
    static_mode_tag,
    tag_of,
    targeting_trigger_side,
    time_counter_kind_refs,
    token_profile_keywords,
    trigger_scope,
    untap_rider_targets,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.recovery import (
    ANY_TARGET,
    ON_SELF,
    TARGET_OBJECT,
    YOUR_TARGET,
)
from mtg_utils._card_ir.text_idioms import _LIB_SEARCH_PLAYER_ACTIONS

# ── Batch 13 lanes (ADR-0035 Stage 2): the field-lookup wholesale batch ──────

# (island_matters / suspend_matters / curse_matters were ADR-0036/0037
# folded to bucket-B ``tree_synthesis`` arms; see ``_arm_island_matters`` /
# ``_arm_suspend_matters`` / ``_arm_curse_matters``.)

# The batch-13 Scryfall-keyword rows (lowercased-membership → lane key; every
# row scope "you", subject ""). These ARE membership lanes — the BEARER fires
# (checklist #4a): companion / specialize / madness / affinity / scavenge and
# the has_* keys tag the card that carries the mechanic. Byte-faithful to the
# live _IR_KEYWORD_MAP rows (:607); the MTGJSON string gotchas ('Choose a
# background' lowercase b, "Doctor's companion") are preserved by the
# lowercase membership gate. companion is deliberately NOT partner
# (CR 702.139 — a deckbuild constraint). MTGJSON tags Astarion, the
# Decadent's modal flavor word "Friends" as a keyword; it is not a partner
# ability, so the partner row leaves it out.
# The alternative-cost keywords the alt_cost_keyword lane opens on, by
# ``crosswalk.ALT_COST_KEYWORDS`` kind: printed (the row below) or granted
# (``_b13_conferred_grant_lanes``).
_ALT_COST_KEYWORD_KINDS: frozenset[str] = frozenset({"sneak", "web-slinging", "mayhem"})
_B13_KEYWORD_LANES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"companion"}), "companion_keyword"),  # CR 702.139
    (frozenset({"banding"}), "has_banding"),  # CR 702.22
    (frozenset({"dash"}), "has_dash"),  # CR 702.109 (SOLE producer)
    (frozenset({"enlist"}), "has_enlist"),  # CR 702.154
    (frozenset({"specialize"}), "specialize_matters"),  # DD4 (digital)
    # CR 118/601 + 702.190a/.188a/.187a-c — the three alternative-cost
    # keyword abilities (sneak ALSO fires the unported recast_etb live-side;
    # only this row is batch-13's).
    (_ALT_COST_KEYWORD_KINDS, "alt_cost_keyword"),
    # CR 702.124/.124a/.124k/.124m/.124i — the partner family (MTGJSON folds
    # "Partner—Friends forever" → 'Partner'). A bare "Friends" keyword is
    # Astarion, the Decadent's "Friends —" modal flavor word (CR 207.2d), not
    # a partner ability, so it is not in the set.
    (
        frozenset(
            {
                "partner",
                "partner with",
                "choose a background",
                "doctor's companion",
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
    # CR 702.14c (islandwalk evasion): the island_makers BEARER row (ADR-0036
    # fold) — the granter/neutralizer/token-maker arms live in
    # :func:`_island_makers` (structural ``Landwalk``/``Island`` reads).
    (frozenset({"islandwalk"}), "island_makers"),
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


def _b13_conferred_grant_lanes(tree: ConceptTree) -> list[Signal]:
    """The batch-13 keyword-LESS granter / conferred-reference top-ups.

    Four typed reads, Tier-1 (ADR-0036/0037 Stage 5 T9-finalize fold — the
    two lane-time regex passes are RETIRED to gap-free bucket-B synth
    arms):

    * ``AddKeyword`` mod-walk (:data:`_B13_MOD_GRANT_LANES`) — Varolz's
      Scavenge, Satoru's Ninjutsu, Mikaeus's Undying, Cauldron's Persist,
      Blade of Selves' Myriad, Yidris's sub-ability Cascade;
    * ``CastWithKeyword`` statics — Tezzeret's ``{Affinity: …}``, Maelstrom
      Nexus's ``Cascade`` (CR 601.3e);
    * a granted sneak / mayhem / web-slinging, either shape
      (:func:`~mtg_utils._card_ir.crosswalk.reads.granted_alt_cost_kinds`)
      → alt_cost_keyword;
    * token-PROFILE keywords — Dragon Broodmother's ``{Devour: 2}`` token,
      Maskwood Nexus's Changeling Shapeshifter (CR 111.3: the effect that
      creates a token defines its abilities);
    * the ``AddAllCreatureTypes`` modification — Mistform Ultimus's "every
      creature type" static (CR 205.3c) → has_changeling;
    * the ``synth_b13_raw_anchor`` node (:func:`_arm_b13_raw_anchor`) for
      the conferred/quoted residue whose grant phase folds into a carrier
      ([P20] family — supplement-fixable, logged);
    * the ``synth_b13_node_anchor`` node (:func:`_arm_b13_node_anchor`) —
      the three pure-(a) re-categorizers (madness / affinity / mutate,
      Stage 3b) read off the retained node description rather than the
      reconstructed oracle.

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
                # Wider than ``reads.is_every_creature_type`` (the card itself):
                # has_changeling also serves a static making other creatures every
                # type, so this walk keeps every mod site.
                add("has_changeling", "")
        for sdef in iter_static_defs(unit.node):
            cw = cast_with_keyword_name(sdef)
            if cw == "Affinity":
                add("affinity_type", _site_raw(sdef))
            elif cw == "Cascade":
                add("cascade_matters", _site_raw(sdef))
        # A grant of sneak / mayhem / web-slinging (Ninja Teen, Green Goblin,
        # Amazing Spider-Man): the same alternative cost the bearer row reads
        # off the printed keyword (CR 702.190a / 702.187b / 702.188a).
        if _ALT_COST_KEYWORD_KINDS.intersection(granted_alt_cost_kinds(unit)):
            add("alt_cost_keyword", "")
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
    for c in tree.iter_concepts():
        if c.concept in ("synth_b13_raw_anchor", "synth_b13_node_anchor"):
            for key in c.subject:
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
    carries "convoke" (the qualifier survives only in the description,
    phase tags a bare cast trigger). Pop = exactly 3 (Joyful Stormsculptor,
    Kasla, Saint Traft and Rem Karolus). Tier-1 (ADR-0036/0037 T10-finalize2
    fold): the deleted lane-time ``_CONVOKE_RAW`` scan is relocated
    verbatim to the bucket-B ``synth_convoke_matters`` node
    (:func:`_arm_convoke_matters`) — no competing structural predicate
    exists, so this is the lane's SOLE source, zero oracle text/regex at
    LANE time. Boundary (checklist #4b): bearers (Chord of Calling) ride
    convoke_makers; the CastWithKeyword{Convoke} granter (Chief Engineer)
    rides the b9 spell_keyword_grant — neither is routed here."""
    for c in tree.iter_concepts():
        if c.concept == "synth_convoke_matters":
            return [Signal("convoke_matters", "you", "", "", tree.name, "high")]
    return []


def _curse_matters(tree: ConceptTree) -> list[Signal]:
    """curse_matters (§C) — CR 205.3h: a card that REFERENCES the Curse
    subtype — a trigger watching Curses (Lynde's dies filter), an effect
    acting on a Curse subject (Witchbane Orb's DestroyAll). Tier-1
    (ADR-0036/0037 fold): the residual bare-reference idiom ("curse
    spells", "curses you cast/control/own", the search-filter drop — Curse
    of Misfortunes [P11]; the acknowledged "a curse counter" quirk, Blue
    Screen of Death, not-cl) reads the ``synth_curse_matters`` bucket-B
    node (:func:`_arm_curse_matters`), gap-gated against the SAME two
    structural arms below — zero oracle text/regex at LANE time.
    MEMBERSHIP stays OUT: BEING an Aura — Curse (Cruel Reality) never
    fires (the live :2509-2510 deferral)."""
    if has_structural_curse_matters(tree):
        return [Signal("curse_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_curse_matters":
            return [Signal("curse_matters", "you", "", "", tree.name, "high")]
    return []


def _foretell_matters(tree: ConceptTree) -> list[Signal]:
    """foretell_matters (§C) — CR 702.143c: a filter naming foretold cards,
    incl. count-operand subjects (Niko Defies Destiny — the property nests
    inside amount/inner/qty/filter/properties; Alrund's dynamic-P/T operand),
    read by :func:`~mtg_utils._card_ir.crosswalk.keyword_resource_events`.
    Boundary (checklist #4b): bearers AND granters ride foretell_makers, never
    this lane."""
    if any(
        e.resource == "foretell" and e.side == "matters"
        for e in keyword_resource_events(tree)
    ):
        return [Signal("foretell_matters", "you", "", "", tree.name, "high")]
    return []


def _foretell_makers(tree: ConceptTree) -> list[Signal]:
    """foretell_makers — a card that grants foretell (CR 702.143a): Bohn,
    Beguiling Balladeer and Dream Devourer's "Each nonland card in your hand
    without foretell has foretell", an ``AddKeyword`` grant read by
    :func:`~mtg_utils._card_ir.crosswalk.keyword_resource_events`. The printed
    keyword rides ``_keyword_field_signals_b5``'s keyword-array row. Boundary:
    an enabler that lets the deck foretell more — a foretell discount, foretell-
    only mana (Ranar the Ever-Watchful, Karfell Harbinger) — is a maker too;
    foretell_matters keeps the payoffs that name foretold cards (CR 702.143c).
    Scope "you"."""
    if any(
        e.resource == "foretell" and e.side == "makers"
        for e in keyword_resource_events(tree)
    ):
        return [Signal("foretell_makers", "you", "", "", tree.name, "high")]
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
    205.1b/205.3m vs 702.111a). Tier-1 (ADR-0036/0037 T10-finalize2 fold):
    arm (b)'s deleted lane-time ``_SAME_TRUE_KW_RE`` scan is relocated
    verbatim to the bucket-B ``synth_keyword_soup`` node
    (:func:`_arm_keyword_soup_same_true`) — arm (a) stays a pure typed
    ``AddKeyword`` count, zero oracle text/regex at LANE time."""
    for unit in tree.units:
        kinds: set[str] = set()
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = (mod_keyword_name(mod) or "").replace(" ", "").lower()
            if kw:
                kinds.add(kw)
        if len(kinds & _EVERGREEN_CK) >= 5:
            return [Signal("keyword_soup", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_keyword_soup":
            return [Signal("keyword_soup", "you", "", "", tree.name, "high")]
    return []


def _island_matters(tree: ConceptTree) -> list[Signal]:
    """island_matters (§D) — CR 702.14c: the attack restriction "can't attack
    unless defending player controls an Island" (Dandân, the serpents, Zhou
    Yu). Tier-1 (ADR-0036/0037 fold): reads the ``tree_synthesis`` bucket-B
    ``synth_island_matters`` node (the deleted ``_ISLAND_MATTERS_RX``
    relocated verbatim) — no competing Tier-1 predicate exists, so this is
    the lane's SOLE source, zero oracle text/regex at LANE time.
    Bearers/granters of islandwalk are island_MAKERS material (Segovian
    Leviathan never fires here)."""
    for c in tree.iter_concepts():
        if c.concept == "synth_island_matters":
            return [Signal("island_matters", "you", "", "", tree.name, "high")]
    return []


def _poison_matters(tree: ConceptTree) -> list[Signal]:
    """poison_matters (§D) — CR 122 + 704.5c, scope "opponents": the
    "poison counter" reference/giver (the ADR-0034 partition: the
    infect/toxic/poisonous keyword BEARERS ride poison_makers). Includes
    the poison-GIVERS that spell out "poison counter" (Fynn, Caress of
    Phyrexia, Vraska); a reminder-only Infect bearer (Glistener Elf) is
    stripped and stays out. Tier-1 (ADR-0036/0037 fold): reads the
    ``tree_synthesis`` bucket-B ``synth_poison_matters`` node (the deleted
    ``_POISON_MATTERS_MIRROR`` relocated verbatim) — no competing Tier-1
    predicate exists (the celebration/coven no-competing-predicate
    precedent), so this is the lane's SOLE source, zero oracle text/regex at
    LANE time."""
    for c in tree.iter_concepts():
        if c.concept == "synth_poison_matters":
            return [Signal("poison_matters", "opponents", "", "", tree.name, "high")]
    return []


def _suspend_matters(tree: ConceptTree) -> list[Signal]:
    """suspend_matters (§D) — CR 702.62: deliberately BROAD (live's
    SWEEP_LABELS breadth, ported as-is + logged) — fires bearers
    (un-parenthesized "Suspend 4—{1}{U}" survives stripping), Vanishing,
    Impending, and every time-counter manipulator. "suspended card" does
    NOT match ``\\bsuspend\\b`` (Clockspinning — the sharpest boundary).
    Tier-1 (ADR-0036/0037 fold): a ``PutCounter{counter_type=Time}``
    structural node (CR 122.1) OR the ``synth_suspend_matters`` bucket-B
    residue (:func:`_arm_suspend_matters`, gap-gated against the same
    structural read) — zero oracle text/regex at LANE time.

    A filter or condition naming time counters is the third arm
    (:func:`~mtg_utils._card_ir.crosswalk.reads.time_counter_kind_refs`):
    Clockspinning's "target permanent or suspended card" carries a time-counter
    predicate (CR 702.62b: a suspended card is in exile, has suspend and has a
    time counter on it), with no ``PutCounter{time}`` of its own. Venser's
    Diffusion's same "or suspended card" target phase drops; the overlay's
    ``suspended_card_target`` arm re-reads it."""
    if (
        has_structural_suspend_matters(tree)
        or any(time_counter_kind_refs(unit.node) for unit in tree.units)
        or any(SUSPENDED_CARD in c.subject for c in tree.iter_concepts())
    ):
        return [Signal("suspend_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_suspend_matters":
            return [Signal("suspend_matters", "you", "", "", tree.name, "high")]
    return []


def _keyword_tribe(tree: ConceptTree) -> list[Signal]:
    """keyword_tribe (§D, SUBJECT-CARRYING) — CR 109.3 / 702: a payoff /
    reference that CARES about creatures WITH an ability keyword (Favorable
    Winds' "creatures you control with flying get +1/+1"; Winged Portent's
    "for each creature you control with flying"; Isperia's keyword tutor).
    The captured SUBJECT (the capitalized ability keyword, vocab-gated
    through ``_ABILITY_KEYWORDS``) is LOAD-BEARING — the per-subject serve
    spec interpolates it. A pure Tier-1 UNION (ADR-0036/0037 fold — the
    ``_detect_keyword_tribe`` text mirror is RETIRED to subject-carrying
    ``tree_synthesis`` arms):

    * **Arm B (structural):** the ability keyword of every controller-``You``
      ``WithKeyword`` filter at an effect subject / count-operand / trigger
      valid_card / static affected / condition site
      (:func:`structural_keyword_subjects` — the SHARED source the synth's
      per-keyword gap gate also reads), scope "you", HIGH.
    * **bucket-B synth (ADR-0037, subject-carrying, per-scope):** the
      ``tree_synthesis`` stage's ``synth_keyword_tribe`` nodes carry a TUPLE
      of the keywords phase leaves keyword-less (tutor / play-from-top /
      symmetric anthem / granted-fly) — the "you"-scope node per-keyword
      gap-gated against Arm B, the "any"-scope node (symmetric anthems)
      ungated. The lane emits one Signal per element at ``node.scope``.

    A bare "this creature has flying" (self-granted keyword) mints no
    subject — it references no keyworded POPULATION (CR 702). Dedupe by
    (scope, subject)."""
    out: list[Signal] = []
    seen: set[tuple[str, str]] = set()

    def emit(scope: str, subject: str) -> None:
        ident = (scope, subject)
        if subject and ident not in seen:
            seen.add(ident)
            out.append(
                Signal(signal_keys.KEYWORD_TRIBE, scope, subject, "", tree.name, "high")
            )

    for subject in structural_keyword_subjects(tree):
        emit("you", subject)
    for c in tree.iter_concepts():
        if c.concept == "synth_keyword_tribe":
            for subject in c.subject:
                emit(c.scope, subject)
    return out


# ── Batch-14 mirror constants + census sets ──────────────────────────────────

# (pump_makers's ``_PUMP_MAKERS_RX`` kept-mirror was ADR-0036/0037 folded to
# Tier-1 — see ``has_structural_pump_makers`` / ``_arm_pump_makers``.)

# Byte-identical copies of the INLINE (unnamed) ``_IR_KEPT_DETECTORS`` rows —
# the _JOHAN_MIRROR precedent (no importable name exists for these).
# (flash_matters / opponent_exile_matters were ADR-0036/0037 folded to
# bucket-B ``tree_synthesis`` arms; see ``_arm_flash_matters`` /
# ``_arm_opponent_exile_matters``.)
# (The signals.py wants_theft hybrid FACADE's don't-own tell was
# ADR-0036/0037 T10-finalize2 folded to a bucket-B ``tree_synthesis`` arm —
# see ``_arm_dont_own``; the gain_control/wants_theft reconciliation below
# reads its ``synth_dont_own`` node, zero oracle text/regex at LANE time.)

# activated_ability cost census (b14 §14 — CR 602.1): phase COST-leaf tags.
# Tap/Untap = the {T}/{Q} branch (overrides an extra cost, like live's
# tap-anchor override); a generic-only Mana leaf (generic>0, shards empty) =
# the {N}: branch, vetoed by an extra-cost leaf. The extra set deliberately
# EXCLUDES ReturnToHand / TapCreatures / Mill / RevealHand — the Meloku
# cost-vocabulary parity pin: the old projection never emitted 'return', so
# mapping ReturnToHand here would move live_only (PARITY-BEFORE-VETO; tune
# only against the shadow diff). A Loyalty cost is neither branch → no fire
# (planeswalker loyalty abilities stay out, matching live).
_AA_TAP_COST_TAGS: frozenset[str] = frozenset({"Tap", "Untap"})
_AA_EXTRA_COST_TAGS: frozenset[str] = frozenset(
    {"Sacrifice", "Discard", "Exile", "PayLife", "RemoveCounter"}
)

# opponent_search_matters raw trigger modes (CR 701.23 search / shuffle).
_OPP_SEARCH_MODES: frozenset[str] = frozenset({"SearchedLibrary", "Shuffled"})

# The batch-14 Scryfall-keyword row: a `station` bearer ACCRUES charge
# counters the deck wants to proliferate (CR 702.184 — the ADR-0034
# cares-about side, distinct from the ported proliferate_makers doer row).
_B14_KEYWORD_LANES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"station"}), "proliferate_matters"),
)


def _keyword_field_signals_b14(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-14 Scryfall-keyword field-lookups (checklist #3 survivors)."""
    low = {k.lower() for k in keywords}
    return [
        Signal(key, "you", "", "", name, "high")
        for kws, key in _B14_KEYWORD_LANES
        if low & kws
    ]


# ── Batch 14 lanes (ADR-0035 Stage 2 — first structural-remainder batch) ─────


def _trigger_mode_tag(unit: AbilityUnit) -> str | None:
    """A trigger unit's RAW phase mode tag (plain string or variant key)."""
    mode = getattr(unit.node, "mode", None)
    return mode if isinstance(mode, str) else tag_of(mode)


def _type_matters_lane(tree: ConceptTree) -> list[Signal]:
    """type_matters (§1, SUBJECT-CARRYING) — CR 205.3 / 109.3: a card that
    CARES about a creature subtype / names a kindred population; the captured
    subject (vocab-validated through ``_resolve_subject``, which carries the
    ``NON_CREATURE_TOKEN`` denylist — CR 111.10 / 205.3g) is LOAD-BEARING. A
    pure Tier-1 UNION (ADR-0036/0037 fold — the four kept-oracle producers'
    text mirror is RETIRED to a subject-carrying ``tree_synthesis`` arm):

    * **Arm B (structural kindred):** the subtype of every non-opponent Typed
      filter at an effect subject / count-operand / trigger valid_card /
      static affected / condition site (:func:`structural_type_subjects` — the
      SHARED source the synth's per-subject gap gate also reads), forced scope
      "you", HIGH.
    * **bucket-B synth (ADR-0037, subject-carrying):** the ``tree_synthesis``
      stage's ``synth_type_matters`` node carries a TUPLE of the resolved
      subtypes phase leaves subject-less (type-grant / keyword-implied tribe /
      multi-tribe anthem / two-tribe & comma lists / description-only tribal),
      per-subject gap-gated against Arm B — the lane emits one Signal per
      element.

    The MEMBERSHIP arms (own type_line race/class tribes + token-profile
    subtypes, LOW) run as a granularity-c reconciliation in
    :func:`extract_crosswalk_signals` — the class-tribe go_wide gate needs
    the MERGED out-key set. No subject → no signal (the silent-drop
    precision gate); dedupe by (key, scope, subject).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def emit(subject: str) -> None:
        if subject and subject not in seen:
            seen.add(subject)
            out.append(
                Signal(signal_keys.TYPE_MATTERS, "you", subject, "", tree.name, "high")
            )

    for subject in structural_type_subjects(tree):
        emit(subject)
    for c in tree.iter_concepts():
        if c.concept == "synth_type_matters":
            for subject in c.subject:
                emit(subject)
    return out


# ─── Task #85: qualified-target Destroy raw-text type bridge ──────────────
#
# phase's typed target node drops the ``Creature`` core type ENTIRELY when
# the target carries a combat-state or color QUALIFIER phase can't (or
# doesn't) structure — "Destroy target blocked creature" (Smite) and
# "Destroy target nonblack attacking creature" (Assassin's Blade) both
# project ``Typed(type_filters=[], properties=[...])`` (Assassin's Blade at
# least keeps the color ``NotColor`` property; Smite's "blocked" qualifier
# vanishes with no residue at all) — a genuine phase-parse gap (verified
# against phase's own ``card-data-v0.23.0.json``, not a crosswalk
# mistranslation), corpus-exhaustive at 5 commander-legal cards, 2 of which
# (Smite, Assassin's Blade) recover via this bridge; the other 3 (Knight of
# the Mists' subtype self-ref "target Knight", Kraul Whipcracker / The
# Ruinous Wrecking Crew's typeless "target token") are a DIFFERENT residual
# shape this narrow bridge deliberately does not chase (no "creature" word
# in their text for it to find — a silent, correct no-op, not a suppressed
# match). Per ADR-0038's bucket-B doctrine (a genuine phase gap gets a
# regex bridge NOW, a parser-substrate fix LATER): reads the literal
# permanent-type WORD straight out of the ability's own English right after
# "destroy target" (the SAME last-resort word-scan idiom
# :func:`_clone_words_from_raw` uses for a sibling-selector clone target),
# anchored on the "destroy target" phrase itself (not a bare "target") so an
# unrelated later "target" in a multi-effect ability can't bleed in. "land"
# is DELIBERATELY excluded from the word list — Land is land_destruction's
# country (CR 305.6), the same veto ``_perm_subject`` applies to a
# STRUCTURALLY-resolved Land core type; corpus-caught via Rancid Earth
# ("Destroy target land[.] Threshold — ... instead destroy THAT land ...")
# whose Threshold-mode second ``Destroy`` targets a typeless
# back-reference (``ParentTarget``, no type info of its own) sharing the
# SAME unit description as the base "Destroy target land." sentence — an
# un-excluded "land" match would have bridged the back-reference to a
# false ``removal`` membership for a spell that is ENTIRELY land
# destruction, base mode and Threshold mode alike.
_QUALIFIED_DESTROY_TYPE_RE = re.compile(
    r"destroy\s+target\b[^.]*?\b"
    r"(creature|artifact|enchantment|planeswalker|permanent)\b",
    re.IGNORECASE,
)


def _qualified_destroy_target_type(raw: str) -> str | None:
    """The permanent-type word right after "destroy target" in RAW (an
    ability's own English), or ``None``. See the module comment above this
    function for the phase-parse gap it bridges."""
    m = _QUALIFIED_DESTROY_TYPE_RE.search(raw or "")
    return m.group(1).title() if m else None


# CR 701.24a's "put on your choice of the top or bottom of its owner's
# library" idiom, the ONE ``countered_spell_zone`` shape phase can't
# structure (Hinder) — see ``_removal``'s fifth arm.
_COUNTER_TUCK_CHOICE_RE = re.compile(
    r"\btop or bottom\b[^.]*?\blibrary\b", re.IGNORECASE
)


# phase v0.104.0 fails closed: a destroy / burn clause it can't fully parse is
# parked as an ``Unimplemented`` residue the recovery stage re-decorates
# (tokens ``destroy`` / ``damage``), with no typed target to read; the seam's
# reading of the clause stands in for it, beside ``_removal``'s typed arms.
# Destroy only ever moves a permanent (CR 701.8a), so a targeted destroy is
# removal unless the target is a land (land_destruction's country, the same
# veto ``_perm_subject`` applies to a typed Land target).
_RECOVERED_BURN_TYPES: frozenset[str] = frozenset(
    {"Creature", "Planeswalker", "Battle", "Permanent"}
)
_CLAUSE_TYPE_WORDS: frozenset[str] = frozenset(
    {
        "Creature",
        "Artifact",
        "Enchantment",
        "Land",
        "Planeswalker",
        "Permanent",
        "Battle",
        "Aura",
        "Equipment",
    }
)


def _recovered_removal(c: ConceptNode) -> bool:
    """A recovered destroy / burn residue (phase v0.104.0's fail-closed
    ``Unimplemented``, tokens ``destroy`` / ``damage``) whose own object is a
    target permanent (the seam's ``TARGET_OBJECT``): a destroy of anything but
    only a land; a burn to "any target" (a creature, planeswalker or battle among
    them, CR 115.4) or to a target naming a permanent type, but not one you
    control (Simulacrum's redirect onto your own creature)."""
    subject = c.subject
    if TARGET_OBJECT not in subject:
        return False
    if c.recovered_by == "destroy":
        types = {t for t in subject if t in _CLAUSE_TYPE_WORDS}
        return types != {"Land"}
    if c.recovered_by == "damage":
        return YOUR_TARGET not in subject and (
            ANY_TARGET in subject or any(t in _RECOVERED_BURN_TYPES for t in subject)
        )
    return False


#: The single-target damage shapes (never a ``DamageAll`` / ``DamageEachPlayer``
#: mass form, CR 115.10's untargeted "each").
_SINGLE_TARGET_DAMAGE_TAGS = frozenset({"DealDamage", "EachSourceDealsDamage"})


def _untyped_burn_reaches_board(
    c: ConceptNode, recipient: object, root: object
) -> bool:
    """A damage effect whose recipient names no permanent type that can still
    reach one (:func:`~mtg_utils._card_ir.crosswalk.effect_reaches_permanent`):
    "any target" (CR 115.4 — Lightning Bolt, Shock), "any other target"
    (Screaming Nemesis), the chosen targets of a multi-target burn (Comet Storm's
    "Choose any target … deals X damage to each of them"). Player-only damage
    ("each opponent", "that player" — CR 120.3a: the player loses life) never
    does, and a typed sweep ("each creature") is ``mass_removal``'s, not this
    single-target lane's."""
    if filter_core_types(recipient) or filter_subtypes(recipient):
        return False
    return effect_reaches_permanent(c.node, root)


def _removal(tree: ConceptTree) -> list[Signal]:
    """removal (§2) — CR 701.8/701.8a: single-target destroy or burn of a
    permanent. Two structural arms, scope "you", HIGH:

    (a) effect-role ``Destroy`` (the tag — NOT ``DestroyAll``; ``tag_of`` is
    the CR 115.10 mass discriminator, the b8 mass_removal precedent) whose
    target names a permanent core type (``_PERMANENT_TYPES``, imported live
    — Land excluded: "destroy target Island" is land_destruction's country,
    CR 305.6) OR a non-land permanent SUBTYPE only ("destroy target Wall /
    Equipment" — the live ``_is_permanent_subtype_destroy`` mirror), OR (task
    #85) a raw-text permanent-type word recovered by
    :func:`_qualified_destroy_target_type` when the structural target names
    NO type information AT ALL — no core type, no subtype (Smite / Assassin's
    Blade's combat-state/color-qualified target — see that function's
    docstring). The bridge is gated on total structural silence, not merely
    on ``_perm_subject`` returning ``False``: a target phase DID resolve to a
    DELIBERATELY-EXCLUDED type (Sinkhole's "destroy target land" resolves
    ``type_filters=['Land']`` — real structural data, just routed to
    land_destruction instead) must never fall through to the bridge, which
    can't tell "phase found land_destruction's own type" from "phase found
    nothing" — a land-destruction spell corpus-verified false-positive this
    gate closes;
    (b) effect-role ``DealDamage`` (not DamageAll / DamageEachPlayer) with
    the same subject test, OR any damage effect whose recipient names no
    permanent type but can still reach a battle, creature or planeswalker (CR
    120.1) — "any target" (CR 115.4 — Lightning Bolt), "any other target", a
    multi-target burn's chosen targets (Comet Storm's ``DamageAll`` over a
    ``ParentTarget``) — :func:`_untyped_burn_reaches_board`. Player-only damage
    (Guttersnipe's "each opponent", Mogis's "that player") reaches no permanent
    and stays ``direct_damage`` alone. Cost-role Destroy never fires
    (effects-only read, granularity a).

    task #86 adds a third arm: a ``Destroy``/``DealDamage`` reachable inside
    a static's ``GrantAbility``/``GrantStaticAbility``/``GrantTrigger`` body
    (:func:`~mtg_utils._card_ir.crosswalk.iter_nested_granted_effect_concepts`
    — phase v0.23.0 now emits these fully typed) — an Equip/Enchant/
    Lieutenant/soulbond-granted "deals N damage to target creature" ability
    (Arc Spitter, Lavamancer's Skill, Pathway Arrows, Shuriken's Equipment/
    Aura grants; Tyrant's Familiar's Lieutenant-granted attack trigger;
    Showstopper's until-end-of-turn dies-trigger grant) is a targeted-kill
    ANSWER for deck-building purposes the same way a top-level DealDamage
    is — the GRANTER (the Equipment/Aura/commander-matters card) is the
    enabler here, CR 113.3/605/611. Every one of the named cards targets a
    creature only (never a player), so none of them also join
    ``direct_damage`` — that lane's own granted-ability fallback
    (:func:`~mtg_utils._card_ir.crosswalk.has_nested_damage_reaching_player`)
    already generically descends the same grant shapes for a PLAYER-reaching
    recipient (Barbed Field, Acidic Sliver) and needs no change here. A
    granted ``Destroy`` body rides the same descent for symmetry (no named
    corpus card yet, but the shape is real — an Equipment/Aura granting
    "{2}: Destroy target creature." is exactly as much a removal answer as
    a top-level one).

    task #88 adds a FOURTH arm: a single-target TUCK — a battlefield
    permanent moved into a library (CR 400 zone-change / 401 library; a
    library-destined move that also shuffles is CR 701.24/701.24a — a
    SEPARATE action layered on top of the zone change, not what makes it a
    removal fact). phase carries this as ``ChangeZone`` (Chaos Warp,
    Oblation) or ``PutAtLibraryPosition``/``PutOnTopOrBottom`` (Condemn,
    Temporal Spring, Spin into Myth, Unexpectedly Absent, Terminus's
    single-target cousins) whose destination/position names the library,
    regardless of WHERE in the library (top/bottom/beneath-top-N/Nth-from-
    top all leave the battlefield the same way — CR 110.1: a permanent
    "stops being a permanent as it's moved to ANOTHER ZONE", the position
    WITHIN that zone is irrelevant to the "did it leave play" question).
    A tuck is genuinely a DIFFERENT removal verb from Destroy, not a
    disguised synonym: "dies" is defined as put into a GRAVEYARD from the
    battlefield specifically (CR 700.4), so a permanent tucked into a
    library never dies — no death trigger, no aristocrats payoff; and
    Regenerate's replacement effect only intercepts a would-be DESTROY (CR
    701.19a "the next time [it] would be DESTROYED"), so it does nothing
    against a tuck — a tuck is thus STRICTLY BETTER removal against a
    regenerating/recursive-from-graveyard threat, the same intuition that
    makes Condemn/Terminus format staples.
    The SAME ``_perm_subject`` test as the Destroy arm gates the target: no
    zone-origin field exists on ``PutAtLibraryPosition`` at all, but none
    is needed — "target creature"/"target permanent" with no ``InZone``
    override is UNAMBIGUOUSLY a battlefield object (CR 109.2/110.1 — an
    object in any OTHER zone is addressed as a "___ CARD", never the bare
    type word). THREE vetoes:

    * **card-selection precedence** (:data:`_TUCK_SELECTION_SIBLINGS` /
      :func:`_tuck_preceded_by_selection`, corpus-verified — NOT merely
      defensive): a reveal/mill/dig producer (``reveal_top``/
      ``reveal_until``/``mill``/``dig``/``exile_top``) appearing BEFORE
      the change_zone/put_library_position concept in the SAME unit's
      ``effects`` chain means the target filter describes a card among
      the just-revealed/milled population ("Put all Elf cards revealed
      this way into your hand and the rest on the bottom of your
      library" — Sylvan Messenger's whole tribal-reveal cycle; "mill four
      cards, then... put a creature or land card from among the milled
      cards on top" — Lluwen), never a targeted BATTLEFIELD permanent —
      even though the filter can carry a bare permanent core type
      (Creature/Land) or a creature-race SUBTYPE (Elf/Goblin/Merfolk/
      Zombie/Kavu/Soldier) ``_perm_subject`` would otherwise read as a
      permanent tell. The REVERSE order (a genuine tuck FOLLOWED BY a
      reveal — Chaos Warp, Audacious Swap, Proteus Staff) is unaffected;
    * **not-battlefield** (a Graveyard/Hand ``ChangeZone.origin`` or an
      ``InZone`` Graveyard/Hand property on the target — Gaea's
      Blessing's graveyard shuffle-back, Brainstorm's hand-to-top — is
      card-flow, not removal, matching ``_exile_removal``'s own zone-
      origin convention);
    * **self-only utility** — a target restricted to "you control"
      (``filter_controller`` == ``"You"`` — the Guildmage/Apprentice
      cycle's "put target creature you control on top of its owner's
      library", Rishadan Pawnshop) or "a permanent you own" (``Owned:
      You``/``Owned:ScopedPlayer`` — Reality Scramble, Tel-Jilad Stylus,
      and the symmetric "each player shuffles all permanents THEY own"
      full-reset idiom: The Great Aurora, Warp World, Collision of
      Realms) is a protective/reset UTILITY effect, never removal — it
      can't touch an opponent's permanent at all. UNLIKE the exile-lane's
      blink veto, an UNRESTRICTED single target that CAN (but need not)
      hit your own permanent is NOT excluded: exile+return (CR 603.6e
      "blink") is vetoed there because the SAME object is guaranteed back
      this turn; a tuck has no such guarantee (CR 701.24a shuffles the
      library immediately), so Oblation's "target nonland permanent" (no
      controller restriction) and Chaos Warp's "target permanent" (ditto)
      stay removal regardless of whose permanent — the same generosity
      the Destroy arm already extends to an unrestricted "destroy target
      permanent". A ``PutAtLibraryPosition``/``PutOnTopOrBottom`` whose
      target is a bare ``SelfRef`` (a COUNTERED SPELL tucking ITSELF while
      still on the stack — Spell Crumple) never matches either arm:
      ``SelfRef`` carries no type filter, so ``_perm_subject`` is false —
      a spell on the stack is not a battlefield permanent (CR 111.1)
      regardless, no special case needed.

    task #np_gyfam adds a FIFTH arm: the countered-spell "choice of top or
    bottom" tuck (CR 701.24a) phase can't structure via ``Counter.
    countered_spell_zone`` (that field only carries a FIXED ``Library``
    position — Memory Lapse/Lapse of Certainty's ``Top``, Spell Crumple's
    ``Bottom`` — never a player CHOICE between the two). Hinder's "put that
    card on your choice of the top or bottom of its owner's library instead
    of into that player's graveyard" clause is WRONG-CONTENT, not dropped: it
    parses as a bare sibling ``ChangeZone`` to ``Graveyard`` (the vanilla-
    counterspell default) with the Counter node's own ``countered_spell_zone``
    left unset — the exact tell that distinguishes it from a genuine
    graveyard-bound counter (which has no such sibling ``ChangeZone`` at all;
    Counterspell/Negate carry only the bare ``Counter`` node). Gated on BOTH
    that structural tell AND the unit's own description naming the "top or
    bottom ... library" choice (CR 701.24a's idiom) so a real graveyard-bound
    counter can never misfire; corpus-swept (every commander/brawl/
    standardbrawl-legal ``Counter`` node with no ``countered_spell_zone``,
    joined to a same-unit ``ChangeZone(Graveyard)`` sibling and this text) —
    Hinder is the ONLY hit, so the "class" this arm serves is exactly one
    card today, self-retiring the moment phase's ``countered_spell_zone``
    grows a choice-of-position variant.
    """

    def _perm_subject(target: object) -> bool:
        ftypes = frozenset(filter_core_types(target))
        if ftypes & _PERMANENT_TYPES:
            return True
        subs = filter_subtypes(target)
        return bool(subs) and any(s.lower() not in LAND_SUBTYPES for s in subs)

    def _target_type_unresolved(target: object) -> bool:
        return not filter_core_types(target) and not filter_subtypes(target)

    def _not_battlefield_origin(origin: object, target: object) -> bool:
        return origin in ("Graveyard", "Hand") or bool(
            set(filter_inzone_zones(target)) & {"Graveyard", "Hand"}
        )

    def _self_only_tuck(target: object) -> bool:
        return filter_controller(target) == "You" or filter_owned_controller(
            target
        ) in ("You", "ScopedPlayer")

    for unit in tree.units:
        for c in unit.effect_concepts("destroy"):
            if c.recovered_by:
                # phase v0.104.0 fail-closed residue, token ``destroy``.
                if _recovered_removal(c):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
                continue
            if tag_of(c.node) != "Destroy":
                continue
            target = getattr(c.node, "target", None)
            if _perm_subject(target):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
            if _target_type_unresolved(target):
                desc = getattr(unit.node, "description", "") or ""
                if _qualified_destroy_target_type(desc):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.effects:
            # A toughness set to 0 or lowered on the target can kill outright
            # (CR 704.5f): Multiply by Zero's 0/0 and Nameless Inversion's
            # +3/-3 are removal, Turn to Frog's 1/1 only the 2HG scan's soft read.
            if _toughness_kill(c, unit):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.effect_concepts("deal_damage"):
            if c.recovered_by:
                # phase v0.104.0 fail-closed residue, token ``damage``.
                if _recovered_removal(c):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
                continue
            # v0.66.0: the per-source batch burn ("each Bird you control deals
            # damage equal to its power to target creature an opponent
            # controls" — Bartz and Boko) is an ``EachSourceDealsDamage`` whose
            # shared target ``damage_recipient`` unwraps; same single-target
            # burn (CR 701.8a territory) as the ``DealDamage`` shape.
            tag = tag_of(c.node)
            if tag not in ("DealDamage", "EachSourceDealsDamage", "DamageAll"):
                continue
            recipient = damage_recipient(c.node)
            if tag != "DamageAll" and _perm_subject(recipient):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
            if _untyped_burn_reaches_board(c, recipient, unit.node):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in iter_nested_granted_effect_concepts(unit.node):
            if c.recovered_by:
                # a granted body's fail-closed residue (Shackles of Treachery)
                if _recovered_removal(c):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
                continue
            if tag_of(c.node) not in ("Destroy", "DealDamage"):
                continue
            target = getattr(c.node, "target", None)
            if _perm_subject(target):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
            if tag_of(c.node) == "DealDamage" and _untyped_burn_reaches_board(
                c, target, unit.node
            ):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    # Single-target burn the flat walk can't see — a coin-flip / modal branch
    # (Goblin Bangchuckers), a replacement (Words of War), a token's ability
    # (Dance with Devils): the shared deep damage walk, single-target tags only
    # (a nested ``DamageAll`` sweep is ``mass_removal``'s).
    for unit in tree.units:
        if has_nested_damage_reaching(
            unit.node, "permanent", tags=_SINGLE_TARGET_DAMAGE_TAGS
        ):
            return [Signal("removal", "you", "", "", tree.name, "high")]
    # task #88 — single-target TUCK (battlefield permanent -> library)
    for unit in tree.units:
        effects = unit.effects
        for idx, c in enumerate(effects):
            if c.concept == "change_zone":
                if tag_of(c.node) != "ChangeZone":
                    continue
                origin, dest = change_zone_dirs(c.node)
                if dest != "Library":
                    continue
                if _tuck_preceded_by_selection(effects, idx):
                    continue
                target = getattr(c.node, "target", None)
                if _not_battlefield_origin(origin, target):
                    continue
                if _self_only_tuck(target):
                    continue
                if _perm_subject(target):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
            elif c.concept == "put_library_position":
                if tag_of(c.node) not in ("PutAtLibraryPosition", "PutOnTopOrBottom"):
                    continue
                if _tuck_preceded_by_selection(effects, idx):
                    continue
                target = getattr(c.node, "target", None)
                if _not_battlefield_origin(None, target):
                    continue
                if _self_only_tuck(target):
                    continue
                if _perm_subject(target):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    # task #np_gyfam — countered-spell "choice of top or bottom" tuck (see
    # the docstring's fifth-arm note). Gated on the Counter node's OWN
    # ``countered_spell_zone`` being unset (a real graveyard-bound counter —
    # Counterspell, Negate — never carries a sibling ChangeZone at all, so
    # this can't misfire there) AND a same-unit ``ChangeZone`` sibling phase
    # defaulted to Graveyard AND the unit's own description naming the
    # library-choice idiom (never a whole-card scan — no SequentialSibling
    # bleed risk since this is one ability's own text).
    for unit in tree.units:
        has_bare_counter = any(
            tag_of(c.node) == "Counter"
            and getattr(c.node, "countered_spell_zone", None) in (None, MISSING)
            for c in unit.effects
        )
        if not has_bare_counter:
            continue
        desc = getattr(unit.node, "description", "") or ""
        if not _COUNTER_TUCK_CHOICE_RE.search(desc):
            continue
        for c in unit.effects:
            if tag_of(c.node) != "ChangeZone":
                continue
            if change_zone_dirs(c.node)[1] != "Graveyard":
                continue
            return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    return []


# ─── Task #83 structural-view helper: removal/edict TARGET TYPE ───────────
#
# The 10 type-scoped theme-preset views (creature/artifact/enchantment/land/
# planeswalker/universal x removal/edict — see ``theme_presets.py``) need a
# fact the lanes above deliberately DON'T carry: the PERMANENT CORE TYPE (CR
# 109.3) a removal/exile/burn/edict effect's target or sacrifice filter
# names. ``removal``/``exile_removal``/``mass_removal``/``edict_makers`` all
# emit ``Signal.subject == ""`` (see each lane's own docstring above) — a
# card matching one of them tells a caller "this is removal" or "this is an
# edict", never WHICH permanent type it answers. This helper reuses the SAME
# target-filter primitives those lanes read (:func:`effect_filter` /
# :func:`filter_core_types` / :func:`filter_subtypes` / :func:`
# change_zone_dirs`) to answer that one extra question, so a preset view
# never re-derives it with a new text scan (ADR-0035/0039, Dan 2026-07-12 —
# presets are declarative VIEWS over the crosswalk, never a third detector
# system).


_ANY: frozenset[str] = frozenset({"Any"})
_CREATURE: frozenset[str] = frozenset({"Creature"})


def _perm_answer_types(filt: object) -> frozenset[str]:
    """A target/sacrifice FILTER's permanent-type answer set (CR 109.3): the
    bare core-type word(s) (:func:`filter_core_types`), or the synthetic
    ``Land`` member when the filter names only a BASIC land subtype ("target
    Island" — ``filter_core_types`` carries no bare ``Land`` word for those;
    mirrors ``_removal``'s own ``_perm_subject`` land-subtype recognition
    above). A non-land SUBTYPE-only filter ("target Wall" / "target
    Equipment") is UNRESOLVED (empty) — no baked subtype -> core-type map
    exists at this seam; ``_perm_subject`` papers over the same gap with a
    bare "is this a permanent at all" bool a type-scoped view can't reuse,
    so this helper returns empty rather than guessing. A small, documented
    recall gap (task #83 membership-diff notes), not a silent guess.
    """
    cores = set(filter_core_types(filt))
    if cores:
        return frozenset(cores)
    subs = {s.lower() for s in filter_subtypes(filt)}
    if subs and subs & LAND_SUBTYPES:
        return frozenset({"Land"})
    return frozenset()


def _toughness_kill(c: ConceptNode, unit: AbilityUnit) -> bool:
    """A one-shot continuous effect that can put a creature the caster doesn't
    control to 0 toughness (CR 704.5f: it goes to its owner's graveyard, and
    regeneration can't replace that): a base-toughness SET to 0 or less
    (Multiply by Zero's 0/0), or toughness LOWERED on the spell's or ability's
    target (Nameless Inversion's "+3/-3" — the target's own shrink, not a
    creature lowering itself: Argivian Avenger's "-1/-1" is SelfRef). An "it"
    resolves to the ability's chosen target (:func:`_root_target_filter`), so
    Does Machines' "target artifact you control … becomes a 0/0 Robot
    creature" animates your own artifact, never a kill."""
    filt = effect_filter(c.node)
    if tag_of(filt) == "ParentTarget":
        filt = _root_target_filter(unit) or filt
    if filter_controller(filt) == "You" or recipient_tag(c.node) == "SelfRef":
        return False
    if tag_of(c.node) != "GenericEffect":
        return False
    for sdef, m in iter_mod_sites(c.node):
        v = mod_value(m)
        if v is None:
            continue
        if tag_of(m) == "SetToughness" and v <= 0:
            return True
        if (
            tag_of(m) == "AddToughness"
            and v < 0
            and affected_tag(sdef) == "ParentTarget"
        ):
            return True
    return False


def _soft_answer_types(c: ConceptNode) -> frozenset[str] | None:
    """The answer types of a SOFT-removal effect aimed at a permanent the caster
    doesn't control — a filter not controlled by ``You`` and not the card
    itself — or ``None`` when ``c`` isn't one:

    * a bounce to hand (Unsummon, The Theorist's -2; CR 400.7 — it comes back a
      new object);
    * a base power/toughness SET to toughness 1 or less (Multiply by Zero's 0/0,
      Perfected Theory's 1/1 mode — not its 4/5 mode; CR 613.4b, 704.5f);
    * -1/-1 counters placed on it (Hapatra, the Desert Fang; CR 122.1a).
    """
    filt = effect_filter(c.node)
    if filter_controller(filt) == "You" or recipient_tag(c.node) == "SelfRef":
        return None
    if c.concept == "bounce":
        return _perm_answer_types(filt)
    if c.concept == "place_counter" and counter_kind(c.node).upper() == "M1M1":
        return _perm_answer_types(filt)
    if tag_of(c.node) == "GenericEffect" and any(
        tag_of(m) == "SetToughness" and (v := mod_value(m)) is not None and v <= 1
        for _, m in iter_mod_sites(c.node)
    ):
        return _perm_answer_types(filt)
    return None


def _tuck_filter(unit: AbilityUnit, node: TypedMirrorNode, *, soft: bool) -> object:
    """A tuck effect's object filter. In ``soft`` mode a ``ParentTarget`` tuck
    (Clash of Elements: "choose target… its owner puts it on top or bottom")
    resolves to the ability's earlier chosen target."""
    sub = effect_filter(node)
    if soft and tag_of(sub) == "ParentTarget":
        sub = _root_target_filter(unit) or sub
    return sub


def _damage_answer_types(c: ConceptNode, root: object) -> frozenset[str]:
    """A damage effect's answer types: its target filter's permanent types, else
    ``Any`` when it can still reach a permanent (CR 120.1 — "any target", CR
    115.4; :func:`~mtg_utils._card_ir.crosswalk.effect_reaches_permanent`, or a
    recovered residue :func:`_recovered_removal` reads as a burn), else none —
    damage that only reaches players (CR 120.3a) answers no permanent."""
    types = _perm_answer_types(effect_filter(c.node))
    if types:
        return types
    if c.recovered_by:
        if not _recovered_removal(c):
            return frozenset()
        # the permanent types the clause names ("you and target creature" —
        # Volcano Hellion), else any target
        named = frozenset(c.reading) & _RECOVERED_BURN_TYPES
        return named if named and ANY_TARGET not in c.reading else _ANY
    return _ANY if effect_reaches_permanent(c.node, root) else frozenset()


_RemovalAnswers = tuple[tuple[ConceptNode, frozenset[str]], ...]
#: Where :func:`_removal_answers` caches its walk on a tree, one attribute per
#: ``soft`` value (the :data:`_EDICT_CACHE_ATTR` precedent: a frozen tree, so its
#: answers never change, and a re-seeded tree is a new object).
_REMOVAL_CACHE_ATTRS: dict[bool, str] = {
    False: "_removal_answers_cache",
    True: "_removal_answers_soft_cache",
}


def _removal_answers(tree: ConceptTree, *, soft: bool = False) -> _RemovalAnswers:
    """Each REMOVAL effect in TREE with its permanent-type "answer" set (see
    :func:`_removal_answer_types`, the union every type-scoped preset reads).
    A caller that needs the effect itself (its filter's mana-value floor, its
    recipient — ``twohg_scan``'s removal reach) walks this instead. Cached on
    the tree per ``soft`` value (:func:`_walk_removal_answers` is the walk).
    """
    attr = _REMOVAL_CACHE_ATTRS[soft]
    cached = tree.__dict__.get(attr)
    if cached is None:
        cached = tuple(_walk_removal_answers(tree, soft=soft))
        object.__setattr__(tree, attr, cached)
    return cached


def _walk_removal_answers(
    tree: ConceptTree, *, soft: bool
) -> Iterator[tuple[ConceptNode, frozenset[str]]]:
    """The walk behind :func:`_removal_answers`.

    ``soft`` (opt-in; every preset keeps the default) also yields the soft
    removal :func:`_soft_answer_types` reads, and resolves a tuck whose target
    is a ``ParentTarget`` back-reference through the chain's root target
    (:func:`_root_target_filter` — Clash of Elements' "choose target nonland
    permanent … put it on the top of their library").

    Every permanent-type "answer" a REMOVAL effect (destroy/exile/burn/
    fight/shrink — never a forced sacrifice, see :func:`_edict_answer_types`
    for that shape) in TREE can give — the UNION of :func:`_perm_answer_types`
    over every matching target filter, plus the synthetic ``Any`` member for
    an UNRESTRICTED damage target (Lightning Bolt's "any target" — a
    ``deal_damage`` node whose filter names no permanent type at all: it
    can't name a permanent core type, but it CAN still kill a creature or a
    planeswalker, matching the deliberately generous legacy creature-
    removal / planeswalker-removal presets) — never damage that only reaches
    players (:func:`_damage_answer_types`).

    Four effect concepts, mirroring the shapes ``_removal``, ``_exile_
    removal``, ``_mass_removal``, and ``_debuff_makers`` each read for their
    OWN key — UNLIKE those lanes this walk does not exclude Land
    (``_removal``/``_mass_removal`` deliberately route a Land target to the
    separate ``land_destruction`` floor lane; a type-scoped view needs Land
    too — Sinkhole, Armageddon) or gate on single-vs-mass (a type-scoped
    view wants every shape that can answer a permanent of a given type,
    board wipe included):

    * ``destroy`` (``Destroy``/``DestroyAll``, CR 701.8) — the target
      filter's answer types, unfiltered, falling back to
      :func:`_qualified_destroy_target_type`'s raw-text bridge (task #85)
      when the structural answer is EMPTY (Smite / Assassin's Blade's
      combat-state/color-qualified target — the same phase-parse gap
      ``_removal`` bridges for its own key, ported here so the 10 type-
      scoped presets recover it too);
    * ``deal_damage`` (``DealDamage``/``DamageAll``, CR 120) — the target
      filter's answer types, or ``Any`` when it names none but can still reach a
      permanent (:func:`_damage_answer_types` — player-only damage answers
      nothing);
    * ``change_zone`` reaching ``Exile`` (CR 406.1) — the SAME three vetoes
      ``_exile_removal`` applies (blink-your-own controller/owned-
      controller check, graveyard/hand origin, a sibling battlefield-return
      or ``become_copy`` — none of those are removal);
    * ``change_zone``/``put_library_position`` reaching a ``Library`` (CR
      401.4, task #88) — the SAME two vetoes :func:`_removal`'s own tuck
      arm applies (self-only controller/owned check, graveyard/hand
      origin); unfiltered on ``ChangeZone`` vs ``ChangeZoneAll`` (a
      type-scoped view wants a mass tuck's answer types too — Terminus ->
      {Creature}, Harmonic Convergence -> {Enchantment});
    * ``fight`` (CR 701.14a) and a P/T-shrinking ``pump`` (CR 613.4c, read
      via :func:`negative_pt_field` on EITHER field — covers a FIXED
      shrink, a ``Variable`` dynamic ``-X/-X``, and a ``Quantity``/
      ``Multiply``-scaled dynamic shrink, the SAME three shapes
      ``debuff_makers``'s toughness-side gate now reads per task #85) both
      always answer ``Creature`` (CR 704 — P/T and fighting only ever apply
      to creatures).

    task #86: a ``destroy``/``deal_damage`` reachable inside a static's
    granted-ability body (:func:`~mtg_utils._card_ir.crosswalk.
    iter_nested_granted_effect_concepts` — the SAME descent
    :func:`_removal`'s own third arm reads) joins the same two answer-type
    reads, no raw-text bridge (no named corpus card needs one for a granted
    body yet) — kept in lockstep with ``_removal`` so a card that gains
    ``removal`` membership from the granted descent always answers its
    permanent type too (Arc Spitter -> {Creature}).
    """
    for unit in tree.units:
        effects = unit.effects
        for idx, c in enumerate(effects):
            if c.concept == "destroy":
                types = _perm_answer_types(effect_filter(c.node))
                if not types:
                    desc = getattr(unit.node, "description", "") or ""
                    bridged = _qualified_destroy_target_type(desc)
                    if bridged:
                        types = frozenset({bridged})
                yield c, types
            elif c.concept == "deal_damage":
                yield c, _damage_answer_types(c, unit.node)
            elif c.concept == "fight" or (
                c.concept == "pump"
                and (
                    negative_pt_field(c.node, "power")
                    or negative_pt_field(c.node, "toughness")
                )
            ):
                yield c, _CREATURE
            elif _toughness_kill(c, unit):
                # A toughness set to 0 or lowered on the target can kill outright
                # (CR 704.5f) — Multiply by Zero's 0/0, Nameless Inversion's
                # +3/-3 — so it is removal in its own right, where a 1/1 set
                # (Turn to Frog) is only the soft read.
                yield c, _CREATURE
            elif c.concept == "put_library_position":
                if tag_of(c.node) not in (
                    "PutAtLibraryPosition",
                    "PutOnTopOrBottom",
                ):
                    continue
                if _tuck_preceded_by_selection(effects, idx):
                    continue  # card-selection idiom, not removal (#88)
                sub = _tuck_filter(unit, c.node, soft=soft)
                if filter_controller(sub) == "You" or (
                    filter_owned_controller(sub) in ("You", "ScopedPlayer")
                ):
                    continue  # self-only tuck utility, not removal (#88)
                if set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}:
                    continue  # card-flow, never on the battlefield
                yield c, _perm_answer_types(sub)
            elif soft:
                types = _soft_answer_types(c)
                if types is not None:
                    yield c, types
        czs = unit.effect_concepts("change_zone")
        sib_return = any(
            change_zone_dirs(s.node)[1] == "Battlefield"
            and tag_of(getattr(s.node, "target", None)) in _RETURN_TARGET_TAGS
            for s in czs
        )
        sib_clone = unit.has_effect("become_copy")
        for c in czs:
            _origin, dest = change_zone_dirs(c.node)
            sub = effect_filter(c.node)
            if dest == "Exile":
                if filter_controller(sub) == "You" or (
                    filter_owned_controller(sub) == "You"
                ):
                    continue  # blink-your-own (CR 603.6e), not removal
                if _origin in ("Graveyard", "Hand") or (
                    set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}
                ):
                    continue  # GY-hate / cage setup (CR 406.2), not removal
                if sib_return or sib_clone:
                    continue
                yield c, _perm_answer_types(sub)
            elif dest == "Library":
                sub = _tuck_filter(unit, c.node, soft=soft)
                idx = next((i for i, e in enumerate(effects) if e is c), None)
                if idx is not None and _tuck_preceded_by_selection(effects, idx):
                    continue  # card-selection idiom, not removal (#88)
                if filter_controller(sub) == "You" or (
                    filter_owned_controller(sub) in ("You", "ScopedPlayer")
                ):
                    continue  # self-only tuck utility, not removal (#88)
                if _origin in ("Graveyard", "Hand") or (
                    set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}
                ):
                    continue  # card-flow, never on the battlefield
                yield c, _perm_answer_types(sub)
    for unit in tree.units:
        for c in iter_nested_granted_effect_concepts(unit.node):
            if c.concept == "destroy":
                yield c, _perm_answer_types(effect_filter(c.node))
            elif c.concept == "deal_damage":
                yield c, _damage_answer_types(c, unit.node)


def _removal_answer_types(tree: ConceptTree) -> frozenset[str]:
    """Every permanent-type "answer" TREE's removal can give — the UNION of
    :func:`_removal_answers` (whose docstring holds the shapes it reads)."""
    return frozenset().union(*(types for _, types in _removal_answers(tree)))


_EdictAnswers = tuple[tuple[ConceptNode, frozenset[str]], ...]
#: Where :func:`_tree_edict_answers` caches its walk on a tree (the owner-index
#: precedent: a frozen tree, so its answers never change, and a re-seeded tree is
#: a new object).
_EDICT_CACHE_ATTR = "_edict_answers_cache"


def _tree_edict_answers(tree: ConceptTree) -> tuple[_EdictAnswers, _EdictAnswers]:
    """TREE's sacrifice effects with their sacrificed filter's
    :func:`_perm_answer_types`, split in two: the ones another player is forced to
    make (:func:`sacrifice_actor_scope`, the actor read ``edict_makers`` scopes by
    — CR 701.21a: a player only sacrifices a permanent they control), and the ones
    naming no player at all (``sacrifice_names_no_player``), which
    :func:`removal_edict_answers` promotes only when phase dropped the forcing
    player. A sacrifice whose permanent "shares a card type with" the one
    sacrificed before it answers that one's types (Braids, Arisen Nightmare's
    ruling: an opponent "may choose to sacrifice any permanent they control that
    shares any card type with it"). Cached on the tree."""
    cached = tree.__dict__.get(_EDICT_CACHE_ATTR)
    if cached is not None:
        return cached
    forced: list[tuple[ConceptNode, frozenset[str]]] = []
    actorless: list[tuple[ConceptNode, frozenset[str]]] = []
    for unit in tree.units:
        previous: frozenset[str] = frozenset()
        for c in unit.effects:
            if c.concept != "sacrifice":
                continue
            filt = effect_filter(c.node)
            types = _perm_answer_types(filt)
            if "SharesQuality" in filter_predicates(filt) and previous:
                types = previous
            previous = types
            if sacrifice_actor_scope(unit, c.node):
                forced.append((c, types))
            elif sacrifice_names_no_player(unit.node, c.node):
                actorless.append((c, types))
    out = (tuple(forced), tuple(actorless))
    object.__setattr__(tree, _EDICT_CACHE_ATTR, out)
    return out


def _edict_answers(tree: ConceptTree) -> Iterator[tuple[ConceptNode, frozenset[str]]]:
    """Each ``sacrifice`` effect in TREE another player is forced to make, with its
    answer types (:func:`_tree_edict_answers`). A sacrifice you make yourself — a
    "you may sacrifice a creature or planeswalker" choice (Winter, Tormented
    Loner), a devour or a sac outlet (Mycoloth) — answers nothing of theirs."""
    yield from _tree_edict_answers(tree)[0]


def _edict_answer_types(tree: ConceptTree) -> frozenset[str]:
    """Every permanent-type "answer" a forced-sacrifice (edict, CR 701.21a)
    effect in TREE can give — the UNION of :func:`_edict_answers`.
    Deliberately SEPARATE from :func:`_removal_answer_types`: a destroy/exile/
    damage effect is never an edict (Armageddon's "destroy all lands" must not
    satisfy a land-EDICT view — CR 701.8 vs 701.21a are distinct zone-change
    verbs).
    """
    return frozenset().union(*(types for _, types in _edict_answers(tree)))


#: The served ident a ledgered bridge emits when phase drops the forcing player of
#: "each opponent … sacrifices" (``bridge_ledger``'s
#: ``_sacrifice_actor_dropped_gap`` row).
_OPPONENT_EDICT_IDENT = "edict_makers|opponents|"


def removal_edict_answers(
    card: dict,
    family: str = "removal",
    *,
    soft: bool = False,
    trees: Sequence[ConceptTree] | None = None,
) -> list[tuple[ConceptNode, frozenset[str]]]:
    """CARD's removal (FAMILY="removal" -> :func:`_removal_answers`, with its
    ``soft`` opt-in) or forced-sacrifice (FAMILY="edict" ->
    :func:`_tree_edict_answers`) effects across every face, each with its answer
    types.

    An edict card with no forced sacrifice phase can read, only sacrifices naming
    no player, whose served signals still say an opponent is forced (the ledger
    reads "each opponent … sacrifices" off the oracle — Papalymo Totolymo,
    Variable Solutions), answers with those sacrifices. The served ident is read
    lazily, only for such a card.

    ``trees`` are the card's trees to walk: its corrected trees by default; a
    signal-path reader (the job reads) passes its signal trees.
    """
    if trees is None:
        from mtg_utils._card_ir.trees import trees_for

        trees = trees_for(card, bulk=card)
    if family == "removal":
        return [a for tree in trees for a in _removal_answers(tree, soft=soft)]
    split = [_tree_edict_answers(tree) for tree in trees]
    forced = [a for f, _ in split for a in f]
    actorless = [a for _, n in split for a in n]
    if forced or not actorless:
        return forced
    from mtg_utils.theme_presets import _signal_idents_for

    return actorless if _OPPONENT_EDICT_IDENT in _signal_idents_for(card) else []


def _removal_edict_types_for(card: dict, family: str) -> frozenset[str]:
    """CARD's UNION answer types across every face, for FAMILY (see
    :func:`removal_edict_answers`)."""
    return frozenset().union(
        *(types for _, types in removal_edict_answers(card, family))
    )


def removal_edict_targets_type(
    card: dict,
    core_type: str,
    *,
    family: str = "removal",
    generous_any: bool = False,
) -> bool:
    """Task #83 preset-view predicate: does CARD's removal (FAMILY=
    "removal") or forced-sacrifice (FAMILY="edict") answer CORE_TYPE
    ("Creature" / "Artifact" / "Enchantment" / "Land" / "Planeswalker" /
    "Permanent")? ``generous_any`` also accepts the synthetic ``Any``
    member (an unrestricted "any target" burn spell, removal-family only —
    a burn spell never forces a sacrifice) — set for the creature/
    planeswalker scopes only, matching the legacy regex presets' deliberate
    generosity (a burn spell CAN kill either); left ``False`` for artifact/
    enchantment/land/universal, which a burn spell can never answer. The
    public entry point ``theme_presets.py`` imports (see that module's
    "Structural views" docstring section).
    """
    types = _removal_edict_types_for(card, family)
    if core_type in types:
        return True
    return generous_any and "Any" in types


def _tutor_lane(tree: ConceptTree) -> list[Signal]:
    """tutor (§3) — CR 701.23/701.23a: your-library search (Demonic Tutor,
    Vampiric Tutor). A pure Tier-1 read (ADR-0036/0037 fold — the
    ``TUTOR_MATTERS_REGEX`` kept-word mirror is RETIRED):

    * **Structural (bucket-A):** :func:`has_structural_tutor` — a self
      ``SearchLibrary``/Augment-combine search, minus the opponent-directed
      / compensation-search / symmetric-ability / Cycling-reminder over-
      fires phase's ``SearchLibrary`` node carries for EVERY search
      (Bribery, Path to Exile, Weird Harvest, landcycling).
    * **bucket-B veto (ADR-0037):** the ``synth_tutor_directed`` node — a
      directed/symmetric search phase's structure carries NO typed marker
      for at all (Head Games, Rootwater Thief, Oath of Lieges, Scheming
      Symmetry — only the reminder-stripped "that/target player's library"
      / "their library" wording reveals it). The arm never fires on a card
      that ALSO says "your library" anywhere (Demolition Field pairs a
      genuine self clause with an unrelated opponent compensation clause),
      so the veto never suppresses a confirmed self search.
    * **bucket-B rescue (ADR-0037):** the ``synth_tutor`` node — a
      description-only self-tutor phase's ``SearchLibrary`` never
      structurally reaches at all (an emblem-granted future search — Kaito
      Shizuki, Garruk Unleashed, Tezzeret Artifice Master; a vote/dice-
      table/repeat-for per-outcome body — Travel Through Caradhras,
      Treasure Chest; a bare ``Unimplemented`` effect — Rampant Growth,
      Mr. Wiggles, "Ach! Hans, Run!"; a self clause paired with an
      unrelated directed sibling — Demolition Field, Tempt with Discovery,
      I Call on the Ancient Magics).
    * **lf_ramp reroute (2026-07-13 convention change):** a NONLAND card's
      clause that searches for a LAND and puts it ONTO THE BATTLEFIELD is
      RAMP, never tutor (the template's ramp convention; ``roles.is_ramp``
      reads the ``ramp`` key this reroute feeds).
      :func:`structural_land_fetch_split` classifies every confirmed self
      search per clause: Rampant Growth / Cultivate / Wood Elves lose tutor
      (the ``_ramp`` lane picks them up from the SAME split), Sylvan
      Scrying / Demonic Tutor keep it, Archdruid's Charm (a creature-or-
      land mode) fires both. The bucket-B side mirrors the boundary in
      ``tree_synthesis._arm_tutor`` (a pure land-fetch text synthesizes a
      real ``ramp`` node via ``_arm_land_fetch_ramp`` instead of
      ``synth_tutor``). LAND cards (Evolving Wilds, Krosan Verge) keep the
      pre-reroute behavior verbatim.

    Scope "you", HIGH.
    """
    if any(c.concept == "synth_tutor_directed" for c in tree.iter_concepts()):
        return []
    if has_structural_tutor(tree):
        if not tree.is_type("Land"):
            land_fetch, other = structural_land_fetch_split(tree)
            if land_fetch and not other:
                return []  # pure land fetch: the ramp lane serves it
        return [Signal("tutor", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_tutor":
            return [Signal("tutor", "you", "", "", tree.name, "high")]
    return []


def _proliferate_matters_lane(tree: ConceptTree) -> list[Signal]:
    """proliferate_matters (§4) — CR 701.34/701.34a proliferate + CR
    702.184/702.184a station + 721.1. The `station` Scryfall-keyword row
    rides :func:`_keyword_field_signals_b14`. Tier-1 (ADR-0036/0037 Stage 5
    T9-finalize fold — the LOW remove-counter-activation-cost mirror is
    RETIRED to a bucket-B synth arm; the divinity/indestructible-enters +
    charge/experience-resource text mirrors were already RETIRED):

    * **Structural (HIGH):** :func:`has_structural_proliferate` — a
      ``place_counter``/``remove_counter`` effect's kind, OR a
      ``give_player_counter`` effect's OWN ``counter_kind`` field (Ezuri's
      "you get an experience counter"), in {divinity, indestructible,
      charge, experience} — the Myojin cycle, Aether Vial, Ezuri, Mizzix.
    * **bucket-B synth (HIGH):** the ``tree_synthesis`` stage's
      ``synth_proliferate_matters`` node — the Station counter-scaling
      reference / choice-branch increment / pure-reference residue (Ion
      Storm, Atreus, Dismantle) phase does not type this batch, gated
      against the same structural read.
    * **bucket-B synth (LOW):** the ``synth_proliferate_remove_cost`` node
      (:func:`_arm_proliferate_remove_cost`) — spending a counter as an
      ACTIVATION COST (Migloz, Rasputin, Tayam) signals proliferate fuel,
      fired independent of (never suppressed by) the HIGH arms above.

    **Logged live GAP (do NOT port):** v0.9.0 carries a first-class
    "whenever you proliferate" payoff family (``PlayerPerformedAction
    {player_actions: ['Proliferate']}`` — Ezuri Stalker of Spheres, Voidwing
    Hybrid) with NONE in the live pop — a candidate adjudicated widen for a
    fix batch (the has_mutate precedent), pinned by the Ezuri negative
    fixture.
    """
    out: list[Signal] = []
    if has_structural_proliferate(tree):
        out.append(Signal("proliferate_matters", "you", "", "", tree.name, "high"))
    else:
        for c in tree.iter_concepts():
            if c.concept == "synth_proliferate_matters":
                out.append(
                    Signal("proliferate_matters", "you", "", "", tree.name, "high")
                )
                break
    for c in tree.iter_concepts():
        if c.concept == "synth_proliferate_remove_cost":
            out.append(Signal("proliferate_matters", "you", "", "", tree.name, "low"))
            break
    return out


def _untaps_named_creature(tree: ConceptTree) -> bool:
    """Whether the card untaps ONE creature it names itself
    (:func:`~mtg_utils._card_ir.crosswalk.untap_rider_targets`): the
    enchanted / equipped creature (Freed from the Real, Pemmin's Aura,
    Instill Energy) or "untap it" after its own pump / counter on a target
    (Bull's Strength, Shore Up, Stony Strength). Each untaps a tapped
    creature (CR 701.26b) so its {T} ability can be paid again — a tapped
    permanent can't be tapped to pay a {T} cost (CR 107.5) — the untap a
    power-tap commander (Mona Lisa) or a {T}: engine re-taps with. Out: an
    opponent's creature (Provoke-style tricks), a card that gains control of
    what it untaps (Threaten's "untap that creature", Abduction's
    ``ChangeController`` static), and a self-untap trigger (Thermo-Alchemist,
    Nettle Sentinel): it re-enables only the card's own tap ability, never
    another permanent — that card's value is its own tap ability."""
    if any(
        c.concept == "gain_control" or tag_of(c.node) == "ChangeController"
        for c in tree.iter_concepts()
    ):
        return False
    for unit in tree.units:
        for target, _node in untap_rider_targets(unit):
            if filter_controller_side(target) != "opponents":
                return True
    return False


def _untap_engine(tree: ConceptTree) -> list[Signal]:
    """untap_engine (§5) — CR 701.26/701.26b: a DELIBERATE untap engine
    (Seedborn Muse, Candelabra, Turnabout). A pure Tier-1 UNION (ADR-0036/
    0037 fold — the engine-words + Ashaya-lands text mirror is RETIRED):

    * **Structural (bucket-A):** :func:`has_structural_untap_engine` — a
      direct/Twiddle-carrier/granted-trigger/activation-cost Untap
      ``SetTapState`` (mass ``scope == 'All'`` or a real card core-type/
      subtype single target), OR the untap-during-each-other-player's-
      untap-step static mode (board-wide — Seedborn Muse — or self-scoped
      — Bender's Waterskin), minus the opponent-directed / ``gain_control``
      Threaten-variant / provoke-sibling / attach-rider over-fires.
    * **bucket-B synth (ADR-0037):** the ``tree_synthesis`` stage's
      ``synth_untap_engine`` node — a "tap or untap" choice phase folds to
      a bare Tap (Curse of Inertia), a granted emblem ability phase leaves
      unstructured (Zariel), or a conditional untap branch phase drops
      (Lightning Runner, Quest for Renewal) — gated against the SAME
      structural read + vetoes (SYNTH-EXCLUSION-PARITY). Ashaya's
      "creatures you control are lands" is NOT ported: a pure CR 205.1a
      type-change untaps nothing itself — lands_matter synergy, not a
      genuine untap_engine member (adjudicated shed).

    HIGH. Subject: the engine's single-subtype scope when every structural
    surface agrees (:func:`structural_untap_subject` — Myr Galvanizer's
    ``Myr``, Merrow Reejerey's Merfolk-cast rate gate), "" for a universal
    engine; the iteration-1 precision panel killed subtype-scoped untappers
    ranked into off-tribe decks unanimously, and the pair ledger's
    scoped_subject_gate reads this segment. Scope: "you" for a your-side
    engine, "each" when every surface is a SYMMETRIC board-wide untap
    (:func:`structural_untap_scope` — Intruder Alarm, iteration-1b kill),
    which drops it out of the your-side pair row's ``untap_engine|you|*``
    pattern. bucket-B synth stays unscoped "you" (no typed filter survives
    in that tail).
    """
    if has_structural_untap_engine(tree):
        subject = structural_untap_subject(tree)
        scope = structural_untap_scope(tree)
        return [Signal("untap_engine", scope, subject, "", tree.name, "high")]
    if _untaps_named_creature(tree):
        return [Signal("untap_engine", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_untap_engine":
            return [Signal("untap_engine", "you", "", "", tree.name, "high")]
    return []


def _theft_makers_lane(tree: ConceptTree) -> list[Signal]:
    """theft_makers (§6) — CR DD9 (heist, digital supplement) + CR 613.1b:
    the steal-and-cast/mill/play DOER, Tier-1 (ADR-0036/0037 Stage 5 fold —
    the ``THEFT_MATTERS_REGEX`` kept-oracle mirror is deleted; the LOW
    wants-side is the unrelated wants_theft facade). Six structural arms,
    each gated to an explicit opponent player-scope (never a bare/ambiguous
    tag) so the [P5] direction trap — a self-exile impulse-draw dig (Light
    Up the Stage) reads NEAR-IDENTICALLY to an opponent steal — stays
    correctly out (:func:`has_structural_theft_makers`): a ``Heist`` effect
    (Grenzo, Crooked Jailer), an ``ExileFromTopUntil`` opponent dig (Chaos
    Wand, Nicol Bolas, Umbris, Dream Harvest, Tasha's Hideous Laughter), a
    directed ``SearchLibrary`` (Bribery, Ancient Vendetta), a triple-zone
    ``ChangeZoneAll`` hate-piece (Cranial Extraction, Stain the Mind), or a
    Hand-zone ``CastFromZone`` beside an opponent target (Sen Triplets), or
    a borrow-and-cast steal — a card another player owns exiled in the same
    unit that lets you cast it (Court of Locthwain, Gonti, Daxos, Hostage
    Taker, Spelljack; ``crosswalk.steals_card_to_cast``). A
    ``synth_theft_makers`` node covers the genuine bucket-B tail (a compound
    sentence phase drops entirely — Axavar, Fate Thief's "discard a card,
    then heist…"; a bare "conjure…from an opponent's library" — Lae'zel,
    Illithid Thrall; a triple-zone search phase leaves ``Unimplemented`` —
    Lobotomy). Scope "opponents", HIGH.
    """
    if has_structural_theft_makers(tree):
        return [Signal("theft_makers", "opponents", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_theft_makers":
            return [Signal("theft_makers", "opponents", "", "", tree.name, "high")]
    return []


def _own_target_spell(tree: ConceptTree) -> list[Signal]:
    """own_target_spell — an instant/sorcery whose printed target filter is
    YOUR permanent (:func:`has_own_target_spell` — Ephemerate, Feat of
    Resistance; strict controller==You, the Infuriate any-target class is a
    documented recall gap). The own-target pair row's candidate class
    (iteration-4): Feather rebates these every turn. Scope "you", HIGH.
    """
    if has_own_target_spell(tree):
        return [Signal("own_target_spell", "you", "", "", tree.name, "high")]
    return []


def _permanent_recast(tree: ConceptTree) -> list[Signal]:
    """permanent_recast — a repeatable engine re-delivering your own
    permanents to a castable/battlefield zone (Muldrotha's graveyard-cast
    permission static, Meren's reanimation trigger, Chulane's activated
    self-bounce — :func:`has_permanent_recast`, three structural arms).
    The recast-loop pair row's ANCHOR class (iteration-3): each re-entry
    re-fires a self-ETB payload (CR 603.6a). Scope "you", HIGH.

    Beside the engine, the one-shot re-deliveries it is made of carry a doer
    subject (``signal_keys.PAGE_ONLY_SUBJECTS``: a self-ETB card's page counts
    them, and none opens an avenue): ``reanimate`` puts a permanent card other
    than this one from a graveyard onto the battlefield (Sun Titan, Argivian
    Restoration — :func:`_reanimates_permanent`), ``replay`` returns a permanent
    you control other than this one to your hand to cast again (Whitemane Lion,
    Kor Skyfisher, the bounce lands — :func:`_replays_own_permanent`), and
    ``land`` returns a land card from your graveyard to the battlefield or your
    hand, or lets you play lands from it (Life from the Loam, Crucible of
    Worlds — :func:`_recurs_land`): what keeps a land-animation deck's lands.
    """
    out: list[Signal] = []
    if has_permanent_recast(tree):
        out.append(Signal("permanent_recast", "you", "", "", tree.name, "high"))
    for subject in _recast_doer_subjects(tree):
        out.append(Signal("permanent_recast", "you", subject, "", tree.name, "high"))
    return out


#: The permanent card types (CR 110.4a) a reanimation's filter can name.
_PERMANENT_CARD_TYPES: frozenset[str] = frozenset(
    {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
)


def _names_permanent_card(cores: Sequence[str], subtypes: Sequence[str]) -> bool:
    """A recursion filter's type evidence names a permanent card: a permanent
    card type or ``Permanent`` itself ("target permanent card"), or, with no
    core type, a subtype of a permanent type ("target Aura card", "Phoenix
    card"; CR 205.3). A bare "target card" (Regrowth) may be an instant."""
    if cores:
        return any(t in _PERMANENT_CARD_TYPES or t == "Permanent" for t in cores)
    return any(
        subtype_card_type(s) in _PERMANENT_CARD_TYPES or s.lower() in LAND_SUBTYPES
        for s in subtypes
    )


def _reanimates_permanent(tree: ConceptTree, c: ConceptNode) -> bool:
    """A ``graveyard_recursion`` onto the battlefield of a permanent card
    (:func:`_names_permanent_card`). The card's own return names itself
    (``SelfRef`` — Reassembling Skeleton), with no type of its own."""
    if c.recovered_by == "reanimate":
        return recovered_card_recursion(c, ("Permanent", *_PERMANENT_CARD_TYPES))
    hit = graveyard_recursion(c.node)
    if hit is None or hit[0] != "battlefield":
        return False
    sub = hit[1]
    return _names_permanent_card(
        recursion_card_types(tree, c.node, sub), filter_subtypes(sub)
    )


def _recurs_land(tree: ConceptTree, c: ConceptNode) -> bool:
    """A ``graveyard_recursion`` of a land card to the battlefield or your hand
    (Life from the Loam, Soul of Windgrace, Splendid Reclamation): a land lost
    to removal comes back. A land card named by subtype only ("a Cave card")
    counts; a tuck to the library does not."""
    if c.recovered_by in ("reanimate", "graveyard_return"):
        return recovered_card_recursion(c, ("Land",))
    hit = graveyard_recursion(c.node)
    if hit is None or hit[0] == "library":
        return False
    sub = hit[1]
    cores = recursion_card_types(tree, c.node, sub)
    if cores:
        return "Land" in cores
    return any(s.lower() in LAND_SUBTYPES for s in filter_subtypes(sub))


def _plays_lands_from_graveyard(unit: AbilityUnit) -> bool:
    """A static letting you play land cards from your graveyard (CR 305.1 —
    Crucible of Worlds, Ramunap Excavator): its ``GraveyardCastPermission``
    names lands."""
    return static_mode_tag(unit.node) == "GraveyardCastPermission" and (
        "Land" in filter_core_types(getattr(unit.node, "affected", None))
    )


def _replays_own_permanent(unit: AbilityUnit, c: ConceptNode) -> bool:
    """A return of a permanent you control from the battlefield to its owner's
    hand (CR 400.7: cast again, it is a new object whose enters triggers fire
    anew): Whitemane Lion's "return a creature you control", Kor Skyfisher's
    "a permanent you control", a bounce land's "a land you control". The card
    returning only itself is a self-bounce (Blinking Spirit — ``SelfRef``), a
    graveyard card is a recall, and a foe returning a permanent they control
    (Zndrsplt's Judgment) replays nothing of yours."""
    if c.concept != "bounce":
        return False
    target = effect_filter(c.node)
    if tag_of(target) == "SelfRef" or filter_controller(target) != "You":
        return False
    if set(filter_inzone_zones(target)) - {"Battlefield"}:
        return False
    return effect_owner_player_scope(unit.node, c.node) not in _OPPONENT_ACTOR_TAGS


def _pays_by_replaying(unit: AbilityUnit) -> bool:
    """A cost the unit's controller pays by returning a permanent they control
    to its owner's hand (CR 118.1: a cost "to stop another action from taking
    place", too): Coral Atoll's "sacrifice it unless you return an untapped
    Island you control", Urban Retreat's activation. The returned permanent is
    cast again, as a replay's is."""
    return any(
        tag_of(paid.leaf) == "ReturnToHand"
        and filter_controller(getattr(paid.leaf, "filter", None)) == "You"
        for paid in controller_paid_cost_leaves(unit)
    )


def _recast_doer_subjects(tree: ConceptTree) -> list[str]:
    """The ``permanent_recast`` doer subjects the card's effects carry."""
    found: set[str] = set()
    for unit in tree.units:
        if unit.origin == "static" and _plays_lands_from_graveyard(unit):
            found.add("land")
        if _pays_by_replaying(unit):
            found.add("replay")
        # An emblem's or a granted ability's (Teyo's end-step reanimation).
        granted = iter_nested_granted_effect_concepts(unit.node)
        for c in chain(unit.effects, granted):
            if _reanimates_permanent(tree, c):
                found.add("reanimate")
            if _recurs_land(tree, c):
                found.add("land")
            if _replays_own_permanent(unit, c):
                found.add("replay")
    return [s for s in ("reanimate", "replay", "land") if s in found]


#: Self-ETB payload effects phase types with no ``EFFECT_CONCEPTS`` row (they
#: decorate as ``other``), each value on every entry: a one-shot restriction or
#: grant on a target ("target creature can't block this turn" — Fervent Cathar;
#: "target creature an opponent controls doesn't untap" — Fogwalker; Quicksmith
#: Spy's granted draw), empower Jace (Way of the Mind Sculptor), a
#: choose-and-sacrifice-the-rest sweep (Cataclysmic Gearhulk), a life total set
#: (Magister Sphinx), a damage fog (Dawnfluke).
_SELF_ETB_OTHER_VALUE_TAGS: frozenset[str] = frozenset(
    {
        "GenericEffect",
        "EmpowerJace",
        "ChooseAndSacrificeRest",
        "SetLifeTotal",
        "PreventDamage",
    }
)


def _self_etb_other_value(unit: AbilityUnit) -> bool:
    """A self-ETB trigger (CR 603.6a — "When this enters") whose payload is one of
    :data:`_SELF_ETB_OTHER_VALUE_TAGS`, or player counters handed to another
    player (Mirelurk Queen's rad counters, Ichor Rats's poison — not the tickets
    you get yourself)."""
    if not (
        unit.origin == "trigger"
        and unit.trigger_event in ETB_TRIGGER_EVENTS
        and tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
    ):
        return False
    for c in unit.effects:
        tag = tag_of(c.node)
        if tag in _SELF_ETB_OTHER_VALUE_TAGS:
            return True
        if tag == "GivePlayerCounter" and effect_player_reach(unit.node, c.node):
            return True
    return False


def _self_etb_payload(tree: ConceptTree) -> list[Signal]:
    """self_etb_payload — a self-ETB trigger with a VALUE payload (CR
    603.6a: enters triggers fire on every entry, so each recast/reanimate/
    bounce re-delivers the clause). The recast-loop pair row's candidate
    class (iteration-3): Shriekmaw's destroy, Mulldrifter's draw, Fleshbag
    Marauder's edict — :func:`has_self_etb_payload`, the wider sibling of
    wants_cloning's clone-worthy gate — plus the payloads phase types with no
    concept row (:func:`_self_etb_other_value`). Scope "you", HIGH.
    """
    if has_self_etb_payload(tree) or any(_self_etb_other_value(u) for u in tree.units):
        return [Signal("self_etb_payload", "you", "", "", tree.name, "high")]
    return []


def _wants_cloning(tree: ConceptTree) -> list[Signal]:
    """wants_cloning (§8) — CR 707.1 / 704.5j (legend rule) / 603.6: the
    card-as-CLONE-TARGET benefit lane (NOT a clone doer — clone_makers is
    ported). A LOW membership heuristic, Tier-1 (ADR-0036 fold — the
    ``_PER_TURN_ENGINE_RE`` / ``_TAP_ABILITY_RE`` / ``_MANA_TAP_RE`` /
    ``_self_etb_value`` / ``_self_dies_value`` kept-oracle mirrors are deleted).
    Two arms, both on typed fields:

    (1) a LEGENDARY CREATURE (``card_supertypes`` + ``is_type`` — already
    structural) whose value is a repeatable engine
    (:func:`has_repeatable_engine` — a per-turn / Nth-each-turn / extra-turn
    trigger, Koma) OR a non-mana tap ability (:func:`has_value_tap_ability`);
    (2) a HIGH-CMC card (``tree.cmc >= 5`` — already structural) with a strong
    self-ETB (:func:`has_self_etb_value`) or self-dies
    (:func:`has_self_dies_value`, reusing the death fold's value predicate)
    trigger — Gyruda, Kokusho — plus the ``tree_synthesis`` bucket-B synth node
    for the modal / conditional-count ETB tail phase leaves ``other``.

    The live pops are measured with ``include_membership`` True, so the arms
    run unconditionally. Scope "you", LOW.
    """
    legend_creature = "Legendary" in tree.card_supertypes and tree.is_type("Creature")
    if legend_creature and (has_repeatable_engine(tree) or has_value_tap_ability(tree)):
        return [Signal("wants_cloning", "you", "", "", tree.name, "low")]
    if tree.cmc >= 5 and (has_self_etb_value(tree) or has_self_dies_value(tree)):
        return [Signal("wants_cloning", "you", "", "", tree.name, "low")]
    for c in tree.iter_concepts():
        if c.concept == "synth_wants_cloning":
            return [Signal("wants_cloning", "you", "", "", tree.name, "low")]
    return []


def _unit_sacrifice_nodes(unit: AbilityUnit) -> list[TypedMirrorNode]:
    """Every ``Sacrifice`` node of one unit — effect role AND activation-cost
    leaves (a sacrifice COST is always the controller's, CR 701.21a; Gyome /
    Gilded Goose carry theirs inside a ``Composite`` cost the top-level cost
    decoration types ``other``), plus the cost leaves of an effect-role
    ``PayCost`` YOU pay (``payer`` Controller or unset): a reflexive payment
    (CR 603.12 — Nimble Hobbit's "you may sacrifice a Food or pay {2}{W}. When
    you do, …", a ``PayCost{cost: OneOf[Sacrifice(Food), Mana]}``). A payment
    another player makes (a ``TriggeringPlayer`` / ``ParentTargetController``
    payer) sacrifices THEIR permanent, which is no payoff of yours. A spell's
    merged additional cost (``unit.costs`` — Feed the Cycle's "As an additional
    cost to cast this spell, forage or pay {B}", whose Food half phase keeps)
    is the caster's too (CR 118.8: its controller pays it)."""
    out = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
    costs = [getattr(unit.node, "cost", None), *(c.node for c in unit.costs)] + [
        getattr(c.node, "cost", None)
        for c in unit.effects
        if tag_of(c.node) == "PayCost"
        and tag_of(getattr(c.node, "payer", None)) in (None, "Controller")
    ]
    for cost in costs:
        for leaf in iter_cost_leaves(cost):
            if tag_of(leaf) == "Sacrifice":
                out.append(leaf)
    return out


_SACRIFICED_SUBTYPES_ATTR = "_xw_sacrificed_subtypes"


def _unit_sacrificed_subtypes(unit: AbilityUnit) -> frozenset[str]:
    """The lowercased subtypes the unit's own sacrifices name
    (:func:`_unit_sacrifice_nodes`' targets), memoized on the unit's node so the
    Food and Clue payoff lanes share one pass."""
    node = unit.node
    cached = node.__dict__.get(_SACRIFICED_SUBTYPES_ATTR)
    if cached is None:
        cached = frozenset(
            st.lower()
            for sac in _unit_sacrifice_nodes(unit)
            for st in filter_subtypes(getattr(sac, "target", None))
        )
        object.__setattr__(node, _SACRIFICED_SUBTYPES_ATTR, cached)
    return cached


def _token_subtype_payoff(tree: ConceptTree, sub: str) -> list[Signal]:
    """Shared food/clue cares-about arms (§9/§10) — CR 111.10b Food /
    701.16a+111.10f Clue; one subtype-parameterized function, all "you"
    HIGH. Tier-1 (ADR-0036/0037 Stage 5 T9-finalize fold — this lane no
    longer reads the ``_TOKEN_SUBTYPE_OWN_REF`` marker (``text_idioms``)
    itself; the shared bucket-B synth arm reads it at synthesis time):

    (1) a ``Sacrifice`` of the subtype (effect OR cost role — Gyome probed
    verbatim; Gilded Goose's "{T}, Sacrifice a Food: Add…" is a LIVE member,
    polarity from the banked pop);
    (2) the ``synth_token_subtype_own_ref`` node
    (:func:`_arm_token_subtype_own_ref`) — the ``_TOKEN_SUBTYPE_OWN_REF``
    marker re-derivation ("Foods you control" — Honored Dreyleader), gated
    to subtypes the face does not already make/sacrifice (the same
    made/sacd exclusion the arm recomputes structurally — a bare maker is
    <sub>_makers' country, never matters);
    (3) any other filter naming the subtype that is not an opponent's — a
    watched trigger subject (Experimental Confectioner's "whenever you
    sacrifice a Food", Daring Sleuth's Clue), a count ("for each Clue you
    control" — Five Hundred Year Diary; "if you sacrificed three or more Clues
    this turn" — Briarbridge Patrol), an anthem / grant subject ("Clues you
    control have exalted" — Merchant of Truth). A sacrificed filter is arm
    (1)'s, which knows who pays; a card that only MAKES the token names it in
    no filter (a ``Token`` effect carries a type list), so a bare maker stays
    ``<sub>_makers``.
    """
    key = f"{sub.lower()}_matters"
    subl = sub.lower()
    for unit in tree.units:
        if subl in _unit_sacrificed_subtypes(unit):
            return [Signal(key, "you", "", "", tree.name, "high")]
        if subl in named_filter_subtypes(unit.node):
            return [Signal(key, "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_token_subtype_own_ref" and subl in c.subject:
            return [Signal(key, "you", "", "", tree.name, "high")]
    return []


def _food_matters_lane(tree: ConceptTree) -> list[Signal]:
    """food_matters (§9) — see :func:`_token_subtype_payoff` — plus a forage
    (:func:`~mtg_utils._card_ir.crosswalk.forages`): CR 701.61a's forage is
    "Exile three cards from your graveyard or sacrifice a Food", so a card that
    forages, or pays off foraging, is a Food payoff. phase writes most forages
    as a Food sacrifice the shared arms read already (Treetop Sentries); the
    read adds the bare ``Forage`` action and the "whenever you forage" trigger
    (Corpseberry Cultivator)."""
    hits = _token_subtype_payoff(tree, "Food")
    if hits:
        return hits
    if any(forages(unit) for unit in tree.units):
        return [Signal("food_matters", "you", "", "", tree.name, "high")]
    return []


def _clue_matters_lane(tree: ConceptTree) -> list[Signal]:
    """clue_matters (§10) — a card that pays off Clues: the shared arms of
    :func:`_token_subtype_payoff` (a Clue sacrifice, a filter naming Clue, the
    ``synth_token_subtype_own_ref`` marker) plus an ``Investigated`` trigger
    ("Whenever you investigate for the first time each turn" — Erdwal
    Illuminator; CR 701.16a). A card that only investigates or makes Clues is
    ``clue_makers``, never this payoff. A typed Clue token replacement
    (Academy Manufactor) fires this key from ``_replacement_doubler_lanes``.
    """
    hits = _token_subtype_payoff(tree, "Clue")
    if hits:
        return hits
    for unit in tree.iter_units("trigger"):
        if _trigger_mode_tag(unit) == "Investigated":
            return [Signal("clue_matters", "you", "", "", tree.name, "high")]
    return []


def _pump_makers_lane(tree: ConceptTree) -> list[Signal]:
    """pump_makers (§11) — CR 611.2c: the duration-scoped combat-trick BUFF.
    Tier-1 (ADR-0036/0037 fold — the ``_PUMP_MAKERS_RX`` kept-mirror is
    RETIRED):

    * **Structural:** :func:`has_structural_pump_makers` — a duration-scoped
      ``Pump``/``PumpAll`` effect with a positive fixed power OR toughness
      (widened from power-only — Affa Guard Hound's "+0/+3"), a "+"-grounded
      dynamic amount, or a nested ``GenericEffect``/``Continuous``-static
      ``AddPower``/``AddToughness`` grant (Adamant Will, Cavalier of Flame's
      team pump) — the firebreathing self-buff excluded via the
      ``SelfRef``-affected veto (Clickslither, Shivan Dragon — self_pump's
      country).
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_pump_makers`` node — the X-based/dynamic-amount residue
      (Kessig Wolf Run's "+X/+0", Liliana of the Dark Realms's "+X/+X") with
      no raw text to ground a positive/negative dynamic-amount tell.

    Scope "you", HIGH.
    """
    if has_structural_pump_makers(tree):
        return [Signal("pump_makers", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_pump_makers":
            return [Signal("pump_makers", "you", "", "", tree.name, "high")]
    return []


def _self_counter_grow(tree: ConceptTree) -> list[Signal]:
    """self_counter_grow (§12) — CR 122.1 + the adapt/monstrosity/renown
    keyword actions (CR 701.46 / 701.37 / 702.104): the grow-ITSELF lane.
    Tier-1 (ADR-0036/0037 fold — the ``_SELF_COUNTER_GROW_MIRROR`` text
    mirror was already RETIRED; T9-finalize also retires the separate
    ``self_power_scale_match`` cross-open to its own gap-gated synth arm):

    * **Structural:** :func:`has_structural_self_counter_grow` — an
      effect-role ``PutCounter{counter_type: P1P1, target: SelfRef}``
      (Scavenging Ooze), a replacement-origin unit additionally requiring
      the replacement's OWN ``valid_card`` SelfRef so "each other creature
      enters with…" board grants (Master Biomancer) stay out (and a Devour
      chain vetoed by a sibling ``sacrifice`` effect — Mycoloth); OR
      ``tag_of`` ∈ {Adapt, Monstrosity, Renown} (Arbor Colossus).
      ``PutCounterAll`` board spreads stay counter_distribute's country.
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_self_counter_grow`` node — the narrowed self-anchored text
      residue (the loose "on it" arm stays deliberately EXCLUDED — 103
      over-fires), gated against the same structural read.
    * **bucket-B synth (cross-open):** the ``synth_self_power_scale`` node
      (:func:`_arm_self_power_scale`) — the self-power-SCALING text idiom
      ("equal to this creature's power" — Esper Sentinel), gap-gated
      against BOTH arms above.

    Scope "you", HIGH.
    """
    if has_structural_self_counter_grow(tree):
        return [Signal("self_counter_grow", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept in ("synth_self_counter_grow", "synth_self_power_scale"):
            return [Signal("self_counter_grow", "you", "", "", tree.name, "high")]
        # phase v0.104.0 fails closed on a conditional self-counter clause,
        # parking it as an Unimplemented residue (recovery token
        # ``place_counter``, or ``scry`` when a scry leads the clause —
        # Taeko); the seam marks +1/+1 counters put on the card itself.
        if c.recovered_by and ON_SELF in c.subject and "+1/+1 counter" in c.subject:
            return [Signal("self_counter_grow", "you", "", "", tree.name, "high")]
    return []


def self_counter_grow_narrow(tree: ConceptTree) -> bool:
    """task #85 (plus-one-counters preset): the ``self_counter_grow`` KEY
    minus its ``synth_self_power_scale`` cross-open. That cross-open fires
    on ANY "value scales with this creature's OWN power" text idiom
    (Esper Sentinel's opponent-tax X, the Khenra cycle's ETB pump/token/
    ward-cost scalers) — a genuine deck-building SYNERGY signal for
    ``self_counter_grow`` (a counter-growth deck wants its own power to
    matter), but ZERO of those cards place, remove, or reference a +1/+1
    counter themselves. The preset's definition is "puts +1/+1 counters
    OR cares about creatures WITH one" — a card whose value merely scales
    with its own power fails both halves, so this predicate reads only
    the structural PutCounter{P1P1,SelfRef} arm and the narrowed
    ``synth_self_counter_grow`` text-idiom arm, never the power-scale
    cross-open. Used ONLY by the plus-one-counters preset's ``concept``
    arm — every OTHER ``self_counter_grow`` consumer (ranking, budgets)
    keeps the full key including the cross-open."""
    if has_structural_self_counter_grow(tree):
        return True
    return any(c.concept == "synth_self_counter_grow" for c in tree.iter_concepts())


def _flash_matters_lane(tree: ConceptTree) -> list[Signal]:
    """flash_matters (§13) — CR 702.8/702.8a, ADR-0034 branch B: ONLY the
    opponent-turn cast PAYOFF (makers/grant are ported flash_makers /
    flash_grant). **Structural is a trap (probed):** phase carries
    ``SpellCast + {OnlyDuringOpponentsTurn}`` for the plain form (Faerie
    Tauntings) but DROPS the qualifier on the "first spell" form (Alela,
    Wavebreak Hippocamp = ``NthSpellThisTurn{n:1}`` only — indistinguishable
    from ported second_spell_matters) AND over-fires on unrelated
    opponent-turn triggers, so there is no competing Tier-1 predicate.
    Tier-1 (ADR-0036/0037 fold): reads the ``synth_flash_matters`` bucket-B
    node (:func:`_arm_flash_matters`) — the lane's SOLE source, zero oracle
    text/regex at LANE time. Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_flash_matters":
            return [Signal("flash_matters", "you", "", "", tree.name, "high")]
    return []


def _activated_ability(tree: ConceptTree) -> list[Signal]:
    """activated_ability (§14) — CR 602.1: the tap/generic-mana value-engine
    census. Units of kind "Activated" on a NON-Land card whose flattened
    cost (``iter_cost_leaves``) carries a Tap/Untap leaf OR a generic-only
    Mana leaf with no extra-cost leaf (``_AA_EXTRA_COST_TAGS`` — see the
    Meloku parity pin there), with at least one effect concept outside the
    live drop set ({ramp, attach} — a mana rock / dork never fires: Sol
    Ring, Llanowar Elves, both live-verified non-members). Fires once per
    card, scope "you", HIGH. NO kept mirror (live's own note: a mirror
    re-floods on dorks).

    A mana ability is never an engine, whatever rider it carries: CR 605.1a
    makes an activated ability that could add mana a mana ability (no target,
    not a loyalty ability, no card to or from a library), and phase marks it
    ``is_mana_ability``. Talisman of Dominance's "{T}: Add {U} or {B}. This
    artifact deals 1 damage to you." is a mana rock, not an activated-ability
    engine, though its damage rider sits outside the drop set.
    """
    if tree.is_type("Land"):
        return []
    for unit in tree.units:
        if unit.origin != "ability" or unit.kind != "Activated":
            continue
        if getattr(unit.node, "is_mana_ability", None) is True:
            continue
        leaves = list(iter_cost_leaves(getattr(unit.node, "cost", None)))
        tags = {tag_of(leaf) for leaf in leaves}
        tapish = bool(tags & _AA_TAP_COST_TAGS)
        genmana = False
        for leaf in leaves:
            if tag_of(leaf) != "Mana":
                continue
            cost = getattr(leaf, "cost", None)
            generic = getattr(cost, "generic", 0) if cost is not None else 0
            shards = getattr(cost, "shards", None) if cost is not None else ()
            # A GENERIC component anywhere in the cost ({2}{U} counts —
            # live's cost token fired on any generic part; an {X} shard is
            # generic too). A pure colored cost ({R} firebreathing) has
            # neither → no fire (Shivan Dragon, live-verified absent).
            # Shadow-diff-tuned: a shards-empty draft left 1229 live
            # members behind (PARITY-BEFORE-VETO).
            if (isinstance(generic, int) and generic > 0) or "X" in (shards or ()):
                genmana = True
        if not (tapish or (genmana and not (tags & _AA_EXTRA_COST_TAGS))):
            continue
        if any(c.concept not in _ACTIVATED_ABILITY_DROP_EFFECTS for c in unit.effects):
            return [Signal("activated_ability", "you", "", "", tree.name, "high")]
    return []


def _mass_death_payoff(tree: ConceptTree) -> list[Signal]:
    """mass_death_payoff (§15) — CR 700.4: the AGGREGATE board-wipe payoff. Tier-1.

    A value/effect that SCALES with the NUMBER of creatures that died this turn
    ("a Treasure for each nontoken creature that died this turn" — Gadrak / Mahadi,
    "draw a card for each creature that died under your control this turn" — Body
    Count, "connive X, where X is the number of creatures that died" — Spymaster's
    Vault). DISTINCT from the single-death morbid conditional ("if a creature died
    this turn" — Bone Picker, Tragic Slip), which is death_matters (checklist #4).

    Two structural arms, zero oracle text / regex at lane time (ADR-0036 fold — the
    ``_MASS_DEATH_REF`` mirror over ``_kept`` is deleted):

    * :func:`mass_death_amount` — phase carries the creatures-died
      ``ZoneChangeCountThisTurn`` in an effect AMOUNT position (a ``Ref.qty`` in a
      ``count`` / ``amount`` / ``value`` field, NEVER a comparison ``lhs`` / ``rhs``).
      The comparison position is the morbid CONDITION — death_matters reads it via
      ``creature_death_condition``; this lane reads only the AMOUNT position, so the
      amount-vs-condition boundary partitions the two lanes cleanly.
    * the ``tree_synthesis`` bucket-B synth node (:data:`synth_mass_death_payoff`) —
      the cost-reduction ("costs {N} less … for each creature that died this turn")
      and Unimplemented tail phase drops the operand for.

    Scope "you", HIGH.
    """
    if mass_death_amount(tree):
        return [Signal("mass_death_payoff", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_mass_death_payoff":
            return [Signal("mass_death_payoff", "you", "", "", tree.name, "high")]
    return []


def _destroy_legendary(tree: ConceptTree) -> list[Signal]:
    """destroy_legendary (§16) — CR 205.4 + 701.8a: a destroy whose target
    filter carries the ``HasSupertype: Legendary`` property (probed
    verbatim: exactly 5 corpus carriers == the exact live 5). ``Destroy`` OR
    ``DestroyAll`` (the mass form fires HERE though not `removal` — Invasion
    of Fiora). "Nonlegendary" (NotSupertype — Cast Down) is the OPPOSITE and
    never fires. Scope "any" (live's forced scope).
    """
    for c in tree.effect_concepts("destroy"):
        target = getattr(c.node, "target", None)
        if target is not None and has_filter_property(
            target, "HasSupertype", "Legendary"
        ):
            return [Signal("destroy_legendary", "any", "", c.raw, tree.name, "high")]
    return []


def _opponent_exile_matters_lane(tree: ConceptTree) -> list[Signal]:
    """opponent_exile_matters (§17) — CR 406.1: the REFERENCES-their-exile
    payoff (ADR-0034 split; the graveyard-hate DOER is ported
    opponent_exile_makers — Bojuka Bog never fires here). Tier-1
    (ADR-0036/0037 fold — the ``_OPP_EXILE_MATTERS_MIRROR`` kept-mirror is
    RETIRED): a 2-card population (Umbris, Fear Manifest; That Which Was
    Compleated) with no competing Tier-1 predicate (Umbris's own static
    carries the base grant but phase never structures the "for each card
    your opponents own in exile" scaling reference at all — a genuine gap,
    not a dropped read), so the ``tree_synthesis`` stage's
    ``synth_opponent_exile_matters`` bucket-B node is the lane's SOLE
    source. Scope "opponents", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_opponent_exile_matters":
            return [
                Signal("opponent_exile_matters", "opponents", "", "", tree.name, "high")
            ]
    return []


def _opponent_search_matters(tree: ConceptTree) -> list[Signal]:
    """opponent_search_matters (§18) — CR 701.23 / 701.22 / 701.25: punish
    opponents' library manipulation. Trigger units with raw mode ∈
    {SearchedLibrary, Shuffled} OR a ``PlayerPerformedAction`` whose
    ``player_actions`` NAME the library search and are ⊆ the
    scry/surveil/search set (the imported live
    ``_LIB_SEARCH_PLAYER_ACTIONS`` frozenset + subset test — River Song's
    composite probed verbatim; Proliferate composites excluded), AND
    ``trigger_scope == "opponents"`` (valid_target Opponent). The YOU/any-
    scoped forms (Matoya / Planetarium — §R(c)'s country; Search Elemental —
    scope any, not commander-legal) are EXCLUDED. Scope "opponents", HIGH.
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode_s = _trigger_mode_tag(unit)
        is_search = mode_s in _OPP_SEARCH_MODES
        if not is_search and mode_s == "PlayerPerformedAction":
            actions = getattr(unit.node, "player_actions", None)
            norm = {a.lower() for a in actions or () if isinstance(a, str)}
            is_search = bool(
                norm
                and "searchedlibrary" in norm
                and norm <= _LIB_SEARCH_PLAYER_ACTIONS
            )
        if is_search and trigger_scope(unit.node) == "opponents":
            return [
                Signal(
                    "opponent_search_matters", "opponents", "", "", tree.name, "high"
                )
            ]
    return []


#: The effects that answer one permanent or spell — destroy (CR 701.8a), counter,
#: a zone move off the battlefield, damage, a shrink.
_SINGLE_ANSWER_TAGS: frozenset[str] = frozenset(
    {"Destroy", "Counter", "ChangeZone", "Bounce", "DealDamage", "Pump"}
)
#: The static restrictions that hold back permanents or spells of a colour
#: ("Black creatures can't attack or block" — Light of Day; "Your opponents can't
#: cast blue spells" — Llawan; Elephant Grass's attack tax).
_COLOR_RESTRICTION_MODES: frozenset[str] = frozenset(
    {
        "CantAttack",
        "CantBlock",
        "CantAttackOrBlock",
        "CantBeCast",
        "CantUntap",
        "BlockRestriction",
    }
)


def _hostile_color_filter(filt: object, *, mass: bool) -> bool:
    """A filter naming a colour that can reach another player's objects: not one
    you control or own, and not cards in a graveyard, hand or library (Call to
    the Netherworld's own creature card). A single answer must name the colour
    it hits ("target black creature"); a mass answer may name the one it spares
    too ("all nonwhite creatures" — Mass Calcify), while Terror's "nonblack"
    lets one target be almost anything and hoses no colour. A colour chosen as
    the card resolves (Wash Out) names none."""
    preds = filter_color_predicates(filt) - {"chosen"}
    if not preds or (not mass and "has" not in preds):
        return False
    if filter_controller(filt) == "You" or filter_owned_controller(filt) == "You":
        return False
    return not set(filter_inzone_zones(filt)) & {"Graveyard", "Hand", "Library"}


def _color_answer(c: ConceptNode) -> bool:
    """An effect answering permanents or spells of a colour (see
    :func:`_hostile_color_filter`): destroy, counter, exile / bounce / tuck off the
    battlefield, damage or a shrink, each single or mass."""
    tag = tag_of(c.node)
    mass = tag in MASS_FILTER_EFFECT_TAGS
    if not mass and tag not in _SINGLE_ANSWER_TAGS:
        return False
    if tag in ("ChangeZone", "ChangeZoneAll"):
        origin, dest = change_zone_dirs(c.node)
        if dest not in ("Exile", "Hand", "Library") or origin in ("Graveyard", "Hand"):
            return False
    if tag in ("Pump", "PumpAll") and not (
        negative_pt_field(c.node, "power") or negative_pt_field(c.node, "toughness")
    ):
        return False
    return _hostile_color_filter(effect_filter(c.node), mass=mass)


def _color_restriction(sdef: TypedMirrorNode) -> bool:
    """A static holding back or shrinking the permanents or spells of a colour:
    a restriction (:data:`_COLOR_RESTRICTION_MODES`), a negative P/T or an
    ability strip ("Nonwhite creatures get -1/-1" — Crovax; "Enchanted red
    creature loses all abilities" — Ray of Frost). An anthem for a colour (Bad
    Moon) is a payoff, not a hoser."""
    affected = getattr(sdef, "affected", None)
    if affected is None or not _hostile_color_filter(affected, mass=True):
        return False
    if static_mode_tag(sdef) in _COLOR_RESTRICTION_MODES:
        return True
    return any(
        tag_of(mod) == "RemoveAllAbilities" or -1 in pt_mod_signs(sd)
        for sd, mod in iter_mod_sites(sdef)
    )


def _checks_target_color(unit: AbilityUnit) -> bool:
    """An answer that checks its target's colour as it resolves ("Counter target
    spell if it's blue" — Pyroblast; Ray of Enfeeblement's bigger shrink on a
    white creature): a ``TargetMatchesFilter`` condition naming a colour on a unit
    that destroys, counters, burns or shrinks."""
    if not any(
        tag_of(c.node) in _SINGLE_ANSWER_TAGS | MASS_FILTER_EFFECT_TAGS
        for c in unit.effects
    ):
        return False
    return any(
        tag_of(n) == "TargetMatchesFilter"
        and "has" in filter_color_predicates(getattr(n, "filter", None))
        for n in iter_typed_nodes(unit.node)
    )


def hoses_a_color(tree: ConceptTree) -> bool:
    """Whether the card answers, restricts or shrinks the permanents or spells of
    a colour (CR 105.2: an object's colour is a characteristic an effect can
    check) — :func:`_color_answer` (Red Elemental Blast, Perish, Mass Calcify,
    Holy Light), :func:`_color_restriction` (Light of Day, Crovax, Llawan) or
    :func:`_checks_target_color` (Pyroblast), on the card's own abilities or the
    ones it grants (Possessed Aven's threshold "Destroy target blue
    creature"). A colour your own permanents need (a bounce of "a white creature
    you control" — Eiganjo Free-Riders' upkeep cost) and a card-in-graveyard
    filter are not hosing. The card's own abilities are read off the shared
    colour-keyed sites (:func:`color_keyed_sites`)."""
    if any(
        _color_answer(site.node)
        if site.kind == "effect"
        else _color_restriction(site.node)
        for site in color_keyed_sites(tree)
    ):
        return True
    return any(
        _checks_target_color(unit)
        or any(_color_answer(c) for c in iter_nested_granted_effect_concepts(unit.node))
        for unit in tree.units
    )


def _color_hoser(tree: ConceptTree) -> list[Signal]:
    """color_hoser (§19) — CR 105.2: removal, restriction or a shrink keyed on a
    SPECIFIC colour (:func:`hoses_a_color`). Read off the card's filters alone:
    printed protection from a colour (CR 702.16) is a shield, not hate, and a
    colour your own permanents need is a drawback. Scope "you", HIGH.
    """
    if hoses_a_color(tree):
        return [Signal("color_hoser", "you", "", "", tree.name, "high")]
    return []


def _coven_matters_lane(tree: ConceptTree) -> list[Signal]:
    """coven_matters (§20) — CR 207.2c (coven IS an ability word; ability
    words have no rules meaning — the word IS the mechanic's only stable
    anchor). Tier-1 (ADR-0036 fold): reads the ``synth_coven_matters``
    bucket-B node (:func:`_arm_coven_matters` in ``tree_synthesis``) — zero
    oracle text / regex at LANE time. **Structural is a trap (probed):**
    phase renders coven as generic ``QuantityCheck``/``ObjectCountDistinct``
    (+ one misparse — Sungold Sentinel), shapes that also serve non-coven
    distinct-count cards, so there is no competing Tier-1 predicate — this
    is the lane's SOLE source (the evasion_self/theft_makers no-gate
    precedent). The Hourglass Coven fires via its own name-reference in
    oracle text — an acknowledged quirk, ported as-is + LOGGED (the b13
    Blue Screen of Death precedent). Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_coven_matters":
            return [Signal("coven_matters", "you", "", "", tree.name, "high")]
    return []


def _crimes_matter(tree: ConceptTree) -> list[Signal]:
    """crimes_matter (§21) — CR 700.13 + glossary "Crime": (a) trigger units
    with raw mode ``CommitCrime`` (probed: 21 corpus carriers, ALL in live,
    0 extra) — the SAME structural arm :func:`has_structural_crimes_matter`
    checks. Tier-1 (ADR-0036/0037 fold): the keyword-less CONDITION form
    ([P20]-adjacent condition-kind phase gap) reads the
    ``synth_crimes_matter`` bucket-B node (:func:`_arm_crimes_matter`,
    gap-gated against the same trigger check — the exact live marker gate,
    21 + 7 = 28 = the whole pop) — zero oracle text/regex at LANE time.
    Scope "you", HIGH.
    """
    if has_structural_crimes_matter(tree):
        return [Signal("crimes_matter", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_crimes_matter":
            return [Signal("crimes_matter", "you", "", "", tree.name, "high")]
    return []


def _outlaw_matters_lane(tree: ConceptTree) -> list[Signal]:
    """outlaw_matters (§22) — CR 700.12/700.12a: Tier-1 (ADR-0036 fold).
    Direct/bucket-A: phase's typed filter naming the outlaw group — the
    CR 700.12 five-subtype AnyOf (Olivia, Jasper Flint, At Knifepoint) OR
    the literal "Outlaw" pseudo-subtype token phase stamps for a NEGATED
    reference ("non-outlaw creature" — Shoot the Sheriff) —
    :func:`has_structural_outlaw` in ``tree_synthesis``. bucket-B: the
    residual "Affinity for outlaws" cost reducer phase drops ENTIRELY
    (Hellspur Brute — zero units for the whole card), read off the
    ``synth_outlaw_matters`` node (:func:`_arm_outlaw_matters`). An
    outlaw-TYPED creature without the word or group filter (Anowon — Rogue
    tribal) deliberately does NOT fire (the CR 700.12 membership direction
    the lane does not open; checklist #4). Scope "you", HIGH.
    """
    if has_structural_outlaw(tree):
        return [Signal("outlaw_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_outlaw_matters":
            return [Signal("outlaw_matters", "you", "", "", tree.name, "high")]
    return []


#: How a one-shot land answer removes the land, by the zone it leaves for.
_LAND_ANSWER_DEST: dict[str, str] = {
    "Exile": "exile",
    "Library": "tuck",
    "Hand": "bounce",
}


def _land_answer_kind(c: ConceptNode) -> str | None:
    """The land-destruction kind of a removal effect: ``destroy`` (CR 701.8a),
    ``exile``, ``bounce`` (to its owner's hand) or ``tuck`` (into a library)."""
    if c.concept == "destroy":
        return "destroy"
    if c.concept == "bounce":
        return "bounce"
    if c.concept == "put_library_position":
        return "tuck"
    if c.concept == "change_zone":
        return _LAND_ANSWER_DEST.get(change_zone_dirs(c.node)[1] or "")
    return None


def _land_destruction(tree: ConceptTree) -> list[Signal]:
    """land_destruction — what the card does to lands, one signal per kind: its
    removal (:func:`_removal_answers`, the bounce read included) answers a land —
    ``destroy`` (Stone Rain, Strip Mine, Wasteland, Armageddon), ``exile``
    (Crumble to Dust), ``bounce`` (Aven Fogbringer), ``tuck`` (Plow Under) —
    or another player is forced to sacrifice one (:func:`_edict_answers` —
    ``sacrifice``: Wildfire, Epicenter, Hurloon Shaman). A land you control is
    a cost or a drawback, not land destruction (Return of the Nightstalkers).
    The membership floor's subject-less ident stays the repeatable-LD
    commander's (Numot), and ``mass_land_denial`` the brackets' read (ADR-0030).
    Scope "you", HIGH.
    """
    kinds: set[str] = set()
    for c, types in _removal_answers(tree, soft=True):
        if "Land" not in types or filter_controller(effect_filter(c.node)) == "You":
            continue
        kind = _land_answer_kind(c)
        if kind is not None:
            kinds.add(kind)
    if any("Land" in types for _c, types in _edict_answers(tree)):
        kinds.add("sacrifice")
    return [
        Signal("land_destruction", "you", kind, "", tree.name, "high")
        for kind in sorted(kinds)
    ]


#: The removal tags that kill creatures en masse — they die (CR 700.4: put into
#: a graveyard from the battlefield): destroy all, damage to each, -X/-X to all.
_MASS_KILL_TAGS: frozenset[str] = frozenset({"DestroyAll", "DamageAll", "PumpAll"})
#: The overloaded sweeps (``crosswalk.overload_sweep``) whose creatures die.
_OVERLOAD_KILLS: frozenset[str] = frozenset({"destroy", "damage", "shrink"})


def _sacrifices_all(c: ConceptNode) -> bool:
    """A forced sacrifice of EVERY matching permanent ("Each player sacrifices
    all creatures they control" — Living Death, All Is Dust): the count is the
    number of them, never a fixed number (Innocent Blood) or a share (Pox)."""
    count = getattr(c.node, "count", None)
    return tag_of(count) == "Ref" and tag_of(getattr(count, "qty", None)) == (
        "ObjectCount"
    )


def kills_creatures_en_masse(tree: ConceptTree) -> bool:
    """Whether the card's sweep makes creatures die (CR 700.4) — the board
    wipe a mass-death payoff wants: a creature-answering mass destroy, damage or
    toughness shrink not limited to yours, or damage to each creature
    (:func:`_removal_answers` — Wrath of God, Blasphemous Act, Toxic Deluge,
    Planar Cleansing), an overloaded
    targeted kill (CR 702.96a — Damn), or every player sacrificing all their
    creatures or all but chosen ones (Living Death, Cataclysm). An exile or
    bounce sweep moves creatures without their dying (Farewell, Evacuation),
    and an artifact or enchantment sweep kills none (Shatterstorm). The
    ``mass_removal`` lane asks this only of a card it already reads as a sweep
    (whose vetoes — a combat-only shrink, an Aura's own creature — stand), and
    emits ``mass_removal|you|creature`` from it, so the subject refines that key
    and never widens it."""
    for c, types in _removal_answers(tree):
        tag = tag_of(c.node)
        if not types & CREATURE_OR_PERMANENT:
            continue
        # Damage to each creature dies whoever controls it (and phase stamps
        # "each creature that player controls" as ``You`` — Radiating Lightning).
        if tag != "DamageAll" and filter_controller(effect_filter(c.node)) == "You":
            continue
        if tag == "PumpAll" and not negative_pt_field(c.node, "toughness"):
            continue
        if tag in _MASS_KILL_TAGS:
            return True
    for c, types in _edict_answers(tree):
        if types & CREATURE_OR_PERMANENT and _sacrifices_all(c):
            return True
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) == "ChooseAndSacrificeRest" and (
                set(filter_core_types(getattr(c.node, "sacrifice_filter", None)))
                & CREATURE_OR_PERMANENT
            ):
                return True
            if overload_sweep(tree, unit, c) in _OVERLOAD_KILLS and (
                set(filter_core_types(effect_filter(c.node))) & CREATURE_OR_PERMANENT
            ):
                return True
    return False


def _returns_graveyard_creatures_en_masse(unit: AbilityUnit) -> bool:
    """A return of EVERY matching creature card from a graveyard to the
    battlefield (CR 700.4's reverse — the board refill after a wipe): a
    ``ChangeZoneAll`` graveyard → battlefield of creature cards not limited to an
    opponent's (Storm of Souls, Raise the Past, Patriarch's Bidding), or of the
    set an earlier clause exiled from graveyards (Living Death, Living End)."""
    exiled_creatures = False
    for c in unit.effects:
        if tag_of(c.node) != "ChangeZoneAll":
            continue
        origin, dest = change_zone_dirs(c.node)
        sub = effect_filter(c.node)
        from_gy = origin == "Graveyard" or "Graveyard" in filter_inzone_zones(sub)
        creatures = bool(set(filter_core_types(sub)) & CREATURE_OR_PERMANENT)
        if from_gy and dest == "Exile" and creatures:
            exiled_creatures = True
        elif (
            dest == "Battlefield"
            and filter_controller(sub) != "Opponent"
            and (
                (from_gy and creatures)
                or (exiled_creatures and not filter_core_types(sub))
            )
        ):
            return True
    return False


def _mass_death_support(tree: ConceptTree) -> list[Signal]:
    """The board-refill half of a mass-death turn: a whole-graveyard creature
    return (:func:`_returns_graveyard_creatures_en_masse`) is
    ``creature_recursion|you|mass``. The sweep half, ``mass_removal|you|
    creature`` (:func:`kills_creatures_en_masse`), is the ``mass_removal``
    lane's own subject; the serve of ``mass_death_payoff`` reads both. Scope
    "you", HIGH.
    """
    if any(_returns_graveyard_creatures_en_masse(u) for u in tree.units):
        return [Signal("creature_recursion", "you", "mass", "", tree.name, "high")]
    return []


#: The banding keywords a grant hands out (CR 702.22a banding, 702.22b "bands
#: with other" — phase names it ``BandsWithOther``).
_BANDING_NAMES: frozenset[str] = frozenset({"banding", "bandswithother"})


def _granted_banding(tree: ConceptTree) -> list[Signal]:
    """has_banding — a card that hands out banding or "bands with other" (CR
    702.22b), to itself or others (:func:`granted_keyword_names`): Battering
    Ram's combat banding, Dire Wolves's conditional banding, Baton of Morale,
    Cooperation, the Legends lands' "bands with other legendary creatures",
    Errand of Duty's banding Knight. The printed keyword is the field row's.
    Scope "you", HIGH."""
    for unit in tree.units:
        if granted_keyword_names(unit.node) & _BANDING_NAMES:
            return [Signal("has_banding", "you", "", "", tree.name, "high")]
    return []


def _targeting_side(tree: ConceptTree) -> list[Signal]:
    """targeting_matters, by side (:func:`targeting_trigger_side`): ``you`` for a
    trigger rewarding your own spell or ability that targets the card or your
    permanent (heroic, Feather, Zada, Colleen Wing, valiant), ``opponents`` for
    one on an opponent's object or an opponent's targeting (Legolas, Master
    Archer's second trigger, Willbreaker, Frost Titan, Reparations). A trigger
    on either side's targeting (repartee, Phantasmal Bear) takes none. Scope
    "any", HIGH."""
    sides: set[str] = set()
    for unit in tree.units:
        for trig in iter_unit_trigger_defs(unit):
            side = targeting_trigger_side(trig)
            if side in ("you", "opponents"):
                sides.add(side)
    return [
        Signal("targeting_matters", "any", side, "", tree.name, "high")
        for side in sorted(sides)
    ]


LANES = (
    _b13_conferred_grant_lanes,
    _boast_matters,
    _convoke_matters,
    _curse_matters,
    _foretell_matters,
    _foretell_makers,
    _keyword_soup,
    _island_matters,
    _poison_matters,
    _suspend_matters,
    _keyword_tribe,
    _type_matters_lane,
    _removal,
    _tutor_lane,
    _proliferate_matters_lane,
    _untap_engine,
    _theft_makers_lane,
    _own_target_spell,
    _permanent_recast,
    _self_etb_payload,
    _wants_cloning,
    _food_matters_lane,
    _clue_matters_lane,
    _pump_makers_lane,
    _self_counter_grow,
    _flash_matters_lane,
    _activated_ability,
    _mass_death_payoff,
    _destroy_legendary,
    _opponent_exile_matters_lane,
    _opponent_search_matters,
    _color_hoser,
    _land_destruction,
    _mass_death_support,
    _granted_banding,
    _targeting_side,
    _coven_matters_lane,
    _crimes_matter,
    _outlaw_matters_lane,
)
