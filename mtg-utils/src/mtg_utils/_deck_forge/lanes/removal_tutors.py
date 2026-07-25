"""Crosswalk signal lanes — the b13/b14 keyword-field tables, type matters,
removal + answer types, tutors, and assorted "matters" lanes (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptTree,
    cast_with_keyword_name,
    change_zone_dirs,
    effect_filter,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    has_filter_property,
    iter_cost_leaves,
    iter_mod_sites,
    iter_nested_granted_effect_concepts,
    iter_static_defs,
    iter_typed_nodes,
    mod_keyword_name,
    static_mode_field,
    static_mode_tag,
    tag_of,
    token_profile_keywords,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import _LIB_SEARCH_PLAYER_ACTIONS
from mtg_utils._card_ir.tree_synthesis import (
    has_own_target_spell,
    has_permanent_recast,
    has_repeatable_engine,
    has_self_dies_value,
    has_self_etb_payload,
    has_self_etb_value,
    has_structural_color_hoser,
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
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge.lanes._shared import (
    _PERMANENT_TYPES,
    _RETURN_TARGET_TAGS,
    _negative_pt_field,
    _site_raw,
    _tuck_preceded_by_selection,
)
from mtg_utils._deck_forge.signal_base import Signal
from mtg_utils._deck_forge.text_reads import (
    _ACTIVATED_ABILITY_DROP_EFFECTS,
    _EVERGREEN_CK,
)
from mtg_utils._deck_forge.text_reads import (
    _LAND_SUBTYPES as _LIVE_LAND_SUBTYPES,
)

# ── Batch 13 lanes (ADR-0035 Stage 2): the field-lookup wholesale batch ──────

# (island_matters / suspend_matters / curse_matters were ADR-0036/0037
# folded to bucket-B ``tree_synthesis`` arms; see ``_arm_island_matters`` /
# ``_arm_suspend_matters`` / ``_arm_curse_matters``.)

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
    * token-PROFILE keywords — Dragon Broodmother's ``{Devour: 2}`` token,
      Maskwood Nexus's Changeling Shapeshifter (CR 111.4);
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
    structural read) — zero oracle text/regex at LANE time."""
    if has_structural_suspend_matters(tree):
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
# (clue_matters / flash_matters / opponent_exile_matters were ADR-0036/0037
# folded to bucket-B ``tree_synthesis`` arms; see ``_arm_clue_matters`` /
# ``_arm_flash_matters`` / ``_arm_opponent_exile_matters``.)
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
    the same subject test — a player-only burn (target ``Any`` / Player) has
    no permanent-typed subject and stays direct_damage. Cost-role Destroy
    never fires (effects-only read, granularity a).

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
        return bool(subs) and any(s.lower() not in _LIVE_LAND_SUBTYPES for s in subs)

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
            if tag_of(c.node) != "Destroy":
                continue
            target = getattr(c.node, "target", None)
            if _perm_subject(target):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
            if _target_type_unresolved(target):
                desc = getattr(unit.node, "description", "") or ""
                if _qualified_destroy_target_type(desc):
                    return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("deal_damage"):
        if tag_of(c.node) != "DealDamage":
            continue
        if _perm_subject(getattr(c.node, "target", None)):
            return [Signal("removal", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in iter_nested_granted_effect_concepts(unit.node):
            if tag_of(c.node) not in ("Destroy", "DealDamage"):
                continue
            if _perm_subject(getattr(c.node, "target", None)):
                return [Signal("removal", "you", "", c.raw, tree.name, "high")]
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
    if subs and subs & _LIVE_LAND_SUBTYPES:
        return frozenset({"Land"})
    return frozenset()


def _removal_answer_types(tree: ConceptTree) -> frozenset[str]:
    """Every permanent-type "answer" a REMOVAL effect (destroy/exile/burn/
    fight/shrink — never a forced sacrifice, see :func:`_edict_answer_types`
    for that shape) in TREE can give — the UNION of :func:`_perm_answer_types`
    over every matching target filter, plus the synthetic ``Any`` member for
    an UNRESTRICTED damage target (Lightning Bolt's "any target" — a
    ``deal_damage`` node whose filter names no permanent type at all: it
    can't name a permanent core type, but it CAN still kill a creature or a
    planeswalker, matching the deliberately generous legacy creature-
    removal / planeswalker-removal presets).

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
    * ``deal_damage`` (``DealDamage``/``DamageAll``, CR 119) — the target
      filter's answer types, or ``Any`` when it names none;
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
      via :func:`_negative_pt_field` on EITHER field — covers a FIXED
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
    out: set[str] = set()
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
                out |= types
            elif c.concept == "deal_damage":
                types = _perm_answer_types(effect_filter(c.node))
                out |= types or {"Any"}
            elif c.concept == "fight" or (
                c.concept == "pump"
                and (
                    _negative_pt_field(c.node, "power")
                    or _negative_pt_field(c.node, "toughness")
                )
            ):
                out.add("Creature")
            elif c.concept == "put_library_position":
                if tag_of(c.node) not in (
                    "PutAtLibraryPosition",
                    "PutOnTopOrBottom",
                ):
                    continue
                if _tuck_preceded_by_selection(effects, idx):
                    continue  # card-selection idiom, not removal (#88)
                sub = effect_filter(c.node)
                if filter_controller(sub) == "You" or (
                    filter_owned_controller(sub) in ("You", "ScopedPlayer")
                ):
                    continue  # self-only tuck utility, not removal (#88)
                if set(filter_inzone_zones(sub)) & {"Graveyard", "Hand"}:
                    continue  # card-flow, never on the battlefield
                out |= _perm_answer_types(sub)
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
                out |= _perm_answer_types(sub)
            elif dest == "Library":
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
                out |= _perm_answer_types(sub)
    for unit in tree.units:
        for c in iter_nested_granted_effect_concepts(unit.node):
            if c.concept == "destroy":
                out |= _perm_answer_types(effect_filter(c.node))
            elif c.concept == "deal_damage":
                out |= _perm_answer_types(effect_filter(c.node)) or {"Any"}
    return frozenset(out)


def _edict_answer_types(tree: ConceptTree) -> frozenset[str]:
    """Every permanent-type "answer" a forced-sacrifice (edict, CR 701.21a)
    effect in TREE can give — the UNION of :func:`_perm_answer_types` over
    every ``sacrifice`` concept node's sacrificed filter (the SAME shape
    ``_edict_makers`` reads for its own key), unfiltered — a type-scoped
    view only asks WHAT gets sacrificed, not WHO is forced (no actor-scope
    gate). Deliberately SEPARATE from :func:`_removal_answer_types`: a
    destroy/exile/damage effect is never an edict (Armageddon's "destroy
    all lands" must not satisfy a land-EDICT view — CR 701.8 vs 701.21a are
    distinct zone-change verbs).
    """
    out: set[str] = set()
    for c in tree.iter_concepts():
        if c.role == "effect" and c.concept == "sacrifice":
            out |= _perm_answer_types(effect_filter(c.node))
    return frozenset(out)


def _removal_edict_types_for(card: dict, family: str) -> frozenset[str]:
    """CARD's UNION answer types across every face, for FAMILY ("removal" ->
    :func:`_removal_answer_types`; "edict" -> :func:`_edict_answer_types`).
    ``trees_for`` (the per-oracle_id tree resolution) already memoizes the
    expensive part — see ``theme_presets._signal_keys_for``'s docstring for
    the two-layer memo this seam piggybacks on — so no separate cache is
    needed here.
    """
    from mtg_utils._deck_forge._ir_lookup import trees_for

    walk = _removal_answer_types if family == "removal" else _edict_answer_types
    out: set[str] = set()
    for tree in trees_for(card, bulk=card):
        out |= walk(tree)
    return frozenset(out)


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
      RAMP, never tutor (mirrors ``card_classify.is_ramp``'s fetch branch).
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
    for c in tree.iter_concepts():
        if c.concept == "synth_untap_engine":
            return [Signal("untap_engine", "you", "", "", tree.name, "high")]
    return []


def _theft_makers_lane(tree: ConceptTree) -> list[Signal]:
    """theft_makers (§6) — CR DD9 (heist, digital supplement) + CR 613.1b:
    the steal-and-cast/mill/play DOER, Tier-1 (ADR-0036/0037 Stage 5 fold —
    the ``THEFT_MATTERS_REGEX`` kept-oracle mirror is deleted; the LOW
    wants-side is the unrelated wants_theft facade). Five structural arms,
    each gated to an explicit opponent player-scope (never a bare/ambiguous
    tag) so the [P5] direction trap — a self-exile impulse-draw dig (Light
    Up the Stage) reads NEAR-IDENTICALLY to an opponent steal — stays
    correctly out (:func:`has_structural_theft_makers`): a ``Heist`` effect
    (Grenzo, Crooked Jailer), an ``ExileFromTopUntil`` opponent dig (Chaos
    Wand, Nicol Bolas, Umbris, Dream Harvest, Tasha's Hideous Laughter), a
    directed ``SearchLibrary`` (Bribery, Ancient Vendetta), a triple-zone
    ``ChangeZoneAll`` hate-piece (Cranial Extraction, Stain the Mind), or a
    Hand-zone ``CastFromZone`` beside an opponent target (Sen Triplets). A
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
    """
    if has_permanent_recast(tree):
        return [Signal("permanent_recast", "you", "", "", tree.name, "high")]
    return []


def _self_etb_payload(tree: ConceptTree) -> list[Signal]:
    """self_etb_payload — a self-ETB trigger with a VALUE payload (CR
    603.6a: enters triggers fire on every entry, so each recast/reanimate/
    bounce re-delivers the clause). The recast-loop pair row's candidate
    class (iteration-3): Shriekmaw's destroy, Mulldrifter's draw, Fleshbag
    Marauder's edict — :func:`has_self_etb_payload`, the wider sibling of
    wants_cloning's clone-worthy gate. Scope "you", HIGH.
    """
    if has_self_etb_payload(tree):
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
    decoration types ``other``)."""
    out = [c.node for c in unit.effects if tag_of(c.node) == "Sacrifice"]
    for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
        if tag_of(leaf) == "Sacrifice":
            out.append(leaf)
    return out


def _token_subtype_payoff(tree: ConceptTree, sub: str) -> list[Signal]:
    """Shared food/clue cares-about arms (§9/§10) — CR 111.10b Food /
    701.16a+111.10f Clue; one subtype-parameterized function, all "you"
    HIGH. Tier-1 (ADR-0036/0037 Stage 5 T9-finalize fold — the
    ``_TOKEN_SUBTYPE_OWN_REF`` lane-time read is RETIRED to a shared
    bucket-B synth arm):

    (1) a ``Sacrifice`` of the subtype (effect OR cost role — Gyome probed
    verbatim; Gilded Goose's "{T}, Sacrifice a Food: Add…" is a LIVE member,
    polarity from the banked pop);
    (2) the ``synth_token_subtype_own_ref`` node
    (:func:`_arm_token_subtype_own_ref`) — the ``_TOKEN_SUBTYPE_OWN_REF``
    marker re-derivation ("Foods you control" — Honored Dreyleader), gated
    to subtypes the face does not already make/sacrifice (the same
    made/sacd exclusion the arm recomputes structurally — a bare maker is
    <sub>_makers' country, never matters);
    (3) a ``Sacrificed``-mode trigger whose ``valid_card`` names the subtype
    (Experimental Confectioner probed verbatim).
    """
    key = f"{sub.lower()}_matters"
    subl = sub.lower()
    for unit in tree.units:
        for node in _unit_sacrifice_nodes(unit):
            subs = {s.lower() for s in filter_subtypes(getattr(node, "target", None))}
            if subl in subs:
                return [Signal(key, "you", "", "", tree.name, "high")]
        if unit.origin == "trigger" and _trigger_mode_tag(unit) == "Sacrificed":
            vc = getattr(unit.node, "valid_card", None)
            if subl in {s.lower() for s in filter_subtypes(vc)}:
                return [Signal(key, "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_token_subtype_own_ref" and subl in c.subject:
            return [Signal(key, "you", "", "", tree.name, "high")]
    return []


def _food_matters_lane(tree: ConceptTree) -> list[Signal]:
    """food_matters (§9) — see :func:`_token_subtype_payoff`."""
    return _token_subtype_payoff(tree, "Food")


def _clue_matters_lane(tree: ConceptTree) -> list[Signal]:
    """clue_matters (§10) — the three shared arms (sacrifice-of-Clue, a
    Sacrificed-mode trigger naming Clue, the ``synth_token_subtype_own_ref``
    bucket-B marker — :func:`_token_subtype_payoff`, shared with
    food_matters, Tier-1 since the T9-finalize fold) plus, Tier-1
    (ADR-0036/0037 fold), the ``synth_clue_matters`` bucket-B RESIDUE node
    (:func:`_arm_clue_matters` — the retired ``CLUE_MATTERS_REGEX``,
    ``clue|investigate``) carrying the modal-vote folds (Tivit), delayed
    triggers, token replacements and becomes-Clue statics (In Too Deep).
    Breadth intended: bare investigate DOERS fire matters too via the word
    (live behavior, the b13 suspend_matters precedent — port as-is). Zero
    oracle text/regex at LANE time.
    """
    hits = _token_subtype_payoff(tree, "Clue")
    if hits:
        return hits
    for c in tree.iter_concepts():
        if c.concept == "synth_clue_matters":
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
    """
    if tree.is_type("Land"):
        return []
    for unit in tree.units:
        if unit.origin != "ability" or unit.kind != "Activated":
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


def _color_hoser(tree: ConceptTree) -> list[Signal]:
    """color_hoser (§19) — CR 105.2 + 613.1e-adjacent: removal/restriction/
    bounce keyed on a SPECIFIC color. Tier-1 (ADR-0036/0037 fold — the
    ``_COLOR_HOSER_RE`` kept-mirror is RETIRED):

    * **Structural:** :func:`has_structural_color_hoser` — the live single-
      target ``Destroy``/``Counter``/``ChangeZone→Exile`` direct-``HasColor``
      carrier arm widened to the MASS forms (``DestroyAll``,
      ``ChangeZoneAll``→Exile, ``BounceAll`` — a ``You``-controlled bounce
      target excluded) and the ``And``-composite ``Counter`` target shape
      (``[StackSpell, Typed{HasColor}]`` — Gainsay, Deathgrip), still gated
      NOT a your-graveyard subject (Kaervek's self-recursion, [P5]
      direction). **Logged GAP** (untouched by this fold): two-color
      disjunctions (Deathmark, Celestial Purge) carry NO direct HasColor —
      a candidate adjudicated widen, NOT parity (pinned by the Deathmark
      negative).
    * **bucket-B synth:** the ``tree_synthesis`` stage's ``synth_color_hoser``
      node — the anthem-debuff ("nonblack creatures get -1/-1"), can't-cast/
      can't-block restriction (Gibbering Hyenas's ``CantBlock`` static
      carries the color qualifier ONLY in ``description`` — a genuine phase
      gap), and choose-a-color residue.

    Scope "you", HIGH.
    """
    if has_structural_color_hoser(tree):
        return [Signal("color_hoser", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_color_hoser":
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


LANES = (
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
    _coven_matters_lane,
    _crimes_matter,
    _outlaw_matters_lane,
)
