"""Crosswalk signal lanes — the b15/b16/w4g keyword-field tables, protection /
grant lanes, bending & station, the Stage-2 closeout sweep, and the W8 tail
(split from crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    counter_kind_any,
    counter_pred_kinds,
    filter_controller,
    filter_core_types,
    filter_non_types,
    filter_predicates,
    filter_subtypes,
    has_filter_property,
    iter_cost_leaves,
    iter_mod_sites,
    iter_typed_nodes,
    mod_keyword_name,
    modify_cost_mode,
    static_mode_field,
    tag_of,
    trigger_constraint_tag,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _SINGLE_PERMANENT_GRANT_PREDS,
    _counter_kind_token,
)
from mtg_utils._card_ir.tree_synthesis import (
    _ANTHEM_PUMP_MODS,
    has_structural_arcane,
    has_structural_cant_block_grant,
    has_structural_firebending_grant,
    has_structural_legend_rule_off,
    has_structural_lessons_matter,
    has_structural_life_payment_insurance,
    has_structural_meld_pair,
    has_structural_miracle_grant,
    has_structural_opponent_counter_grant,
    has_structural_power_tap_engine,
    has_structural_snow_matters,
    has_structural_station_charge,
    has_structural_station_reference,
    has_structural_toughness_combat,
)
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import _GRANT_ABILITY_MOD_TAGS
from mtg_utils._deck_forge.signal_base import Signal
from mtg_utils._deck_forge.text_reads import (
    _COUNTER_KIND_KEYS,
    _EVERGREEN_CK,
    _NAMED_COUNTER_KINDS,
    _SELF_PROTECTION_GRANT_KW,
)

# ── Batch-15 mirror constants + census sets ──────────────────────────────────

# Compiled forms of the pinned shared regex sources (byte-identical by import;
# the same IGNORECASE the live kept-detector loop compiles with).
# (void_warp_makers's ``_VOID_WARP_MAKERS_RX`` kept-mirror was ADR-0036/0037
# folded to Tier-1 — see ``_arm_void_warp_makers``. station's
# ``_STATION_GUARD_RX``/``_STATION_CHARGE_RE`` kept-mirrors were ADR-0036/0037
# folded to Tier-1 — see ``_station_lanes`` + ``_arm_station_matters``.)

# (sacrifice_protection's ``_SAC_PROTECTION_MIRROR`` kept-mirror was
# ADR-0036/0037 folded to Tier-1 — see ``_arm_sacrifice_protection``.)

# speed_makers doer tags (CR 702.179): the keyword-less speed CHANGERS.
# ``IncreaseSpeed`` is a dead map row at v0.9.0 (0 corpus nodes) carried
# anyway — free and version-robust (the live projection maps all three).
_SPEED_DOER_TAGS: frozenset[str] = frozenset(
    {"ChangeSpeed", "StartYourEngines", "IncreaseSpeed"}
)

# Station's typed type-line discriminant (CR 702.184b — station cards are
# Spacecraft/Planet bodies). Prefers ``tree.card_subtypes`` (phase carries
# them as subtypes) over re-reading the bulk type_line; the shadow diff
# showed 0 drift vs the live ``_STATION_TL_RE`` split.
_STATION_SUBTYPES: frozenset[str] = frozenset({"Spacecraft", "Planet"})

# The batch-15 Scryfall-keyword rows (the live ``_IR_KEYWORD_MAP`` b15
# survivors — keyword compares are lowercase; the "start your engines!"
# bang and the "max speed" space are load-bearing). station / firebending
# keywords are SPLIT DISCRIMINANTS inside their mirror lanes, not rows.
_B15_KEYWORD_LANES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"airbend"}), "airbend_makers"),
    (frozenset({"earthbend"}), "earthbend_makers"),
    (frozenset({"waterbend"}), "waterbend_makers"),
    (
        frozenset(
            {
                "menace",
                "fear",
                "intimidate",
                "skulk",
                "horsemanship",
                "shadow",
                # ADR-0036 evasion_self fold (bucket-A): the landwalk family
                # (CR 702.14) also rides Scryfall's own keyword field — a
                # genuine structural recovery over the deleted
                # ``_EVASION_SELF_REGEX`` mirror's landwalk-word branch.
                "islandwalk",
                "swampwalk",
                "forestwalk",
                "mountainwalk",
                "plainswalk",
                "landwalk",
            }
        ),
        "evasion_self",
    ),
    (frozenset({"start your engines!"}), "speed_makers"),
    (frozenset({"max speed"}), "speed_matters"),
    (frozenset({"saddle"}), "saddle_matters"),
)


def _keyword_field_signals_b15(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-15 Scryfall-keyword field-lookups (checklist #3 survivors).

    evasion_self's six keywords: menace CR 702.111, fear 702.36, intimidate
    702.13, skulk 702.118, horsemanship 702.31, shadow 702.28 (the live
    comment's "skulk 702.72 / horsemanship 702.30" numbers are STALE —
    corrected from the 20260619 CR CLI output), PLUS the five landwalk
    keywords + the "landwalk" umbrella row (CR 702.14 — a genuine
    ADR-0036 bucket-A structural recovery: 122 corpus cards carry a
    landwalk keyword in their OWN Scryfall ``keywords`` field). flying is
    DELIBERATELY absent (soft evasion). speed: "start your engines!"
    initializes speed and installs the per-turn increase = MAKER (CR
    702.179a); "max speed" only functions AT speed 4 = PAYOFF (CR 702.178a
    — the ADR-0034 split). saddle (CR 702.171a) is ONE lane, no
    maker/matters split live.
    """
    low = {k.lower() for k in keywords}
    return [
        Signal(key, "you", "", "", name, "high")
        for kws, key in _B15_KEYWORD_LANES
        if low & kws
    ]


# ── Batch 15 lanes (ADR-0035 Stage 2 — second structural-remainder batch) ────


# Base-P/T-set modification tags the projection LIFTS out of a GenericEffect
# (→ base_pt_set) — the fixed and BOTH dynamic phase spellings, spelled out
# (the module's `_DYNAMIC_PT_MODS` name is shadowed by a later batch-14
# AddDynamic* redefinition, so the Set* spellings are pinned here). A
# Waterbend-cost ability whose GenericEffect carries one projects
# structurally and is never re-parsed (Flexible Waterbender, Katara Water
# Tribe's Hope — pop False).
_WB_PT_SET_MODS: frozenset[str] = frozenset(
    {
        "SetPower",
        "SetToughness",
        "SetDynamicPower",
        "SetDynamicToughness",
        "SetPowerDynamic",
        "SetToughnessDynamic",
    }
)


def _wb_dropped_other(c: ConceptNode) -> bool:
    """Whether an effect node is one the PROJECTION dropped-and-re-parsed —
    the live producer of a Waterbend-cost ability's ``bending`` Effect.

    The projection re-parses a clause only when its structural read failed.
    Two dropped-node families (the exact 4-member activated-cost residue,
    shadow-diff-tuned to the banked pop):

    * a ``GenericEffect`` whose nested statics the projection does NOT
      lift — Giant Koi / Waterbender Ascension's ``CantBeBlocked``,
      Invasion Submersible's become-artifact ``AddType``. A base-P/T-set
      modification IS lifted (→ base_pt_set: Flexible Waterbender, Katara
      Water Tribe's Hope — pop False), as is a structural node like
      Transform (Aang, Swift Savior — pop False) or Draw (Katara, Bending
      Prodigy — the spec's polarity pin);
    * the owner-library TUCK (``ChangeZone`` destination Library — Watery
      Grasp's "shuffles it into their library"), which the projection has
      no category for.
    """
    if c.concept == "change_zone" and change_zone_dirs(c.node)[1] == "Library":
        return True
    if c.concept != OTHER or tag_of(c.node) != "GenericEffect":
        return False
    mods = {tag_of(m) for _sd, m in iter_mod_sites(c.node)}
    return not (mods & _WB_PT_SET_MODS)


def _bending_lanes(tree: ConceptTree, keywords: frozenset[str]) -> list[Signal]:
    """The TLA bending node arm + the firebending mirror split (§1).

    CR 701.65a airbend / 701.66a earthbend / 701.67a waterbend (keyword
    ACTIONS) vs 702.189a firebending (a TRIGGERED ability). Each bend is a
    SEPARATE mechanic — no unifying "bending" CR rule (the deleted legacy
    IR engine's never-conflate ruling, at its :1036-1050). Keyword-bearer rows
    ride :func:`_keyword_field_signals_b15`; this is the node arm the live
    ``bending``-Effect arm (:8177-8191) reads, re-derived from the typed
    v0.9.0 producers of cat=='bending':

    * a ``RegisterBending`` node (49 corpus cards — every airbend/
      earthbend maker and no others; project.py:554);
    * an ``ElementalBend`` trigger mode (exactly 1 card — Avatar Aang's
      cross-bend payoff; the SIDECAR-v68 marker, project.py:3098-3109);
    * a ``Waterbend`` cost leaf on an Activated unit whose effect chain
      carries an OTHER-concept node — the live bending Effect for these is
      the supplement's re-parse of a clause the structural projection
      DROPPED (Giant Koi's GenericEffect statics), so a clean structural
      projection never re-parses and never fires (Katara's Waterbend→Draw:
      pop False — the 5-member matters set is exact, NOT "all
      activated-waterbend cards").

    Routing is EXACTLY live's: "airbend" in raw → airbend_makers (airbend
    has NO matters lane — the cross-bend payoff lands in makers, live's
    firing identity); "earthbend" in raw AND keyword-less → earthbend_
    matters (Earthen Ally carries the keyword AND a bending node — the
    gate); "waterbend" in raw → waterbend_matters (deliberately UNgated —
    Giant Koi double-fires makers via keyword AND matters via the node
    arm, live's exact behavior, ported as-is + LOGGED). firebend is NOT
    routed here (Avatar Aang's ElementalBend raw contains "firebend"; a
    naive route would double-fire past the mirror+kw split below).

    Firebending (ADR-0036/0037 Stage 5 fold, Tier-1): bearers (Fire Lord
    Azula, Avatar Aang) ride the caller-supplied Scryfall keyword array
    (structural, "firebending" in ``low``) → makers. A keyword-less GRANT
    (Sozin's Comet, Iroh Dragon of the West, Fire Nation Cadets/Palace/
    Turret) structures as a typed ``AddKeyword`` static naming Firebending
    (:func:`has_structural_firebending_grant`) → matters. The residual
    bucket-B tail — a grant baked into a make_token spec's own body (Fire
    Nation Attacks/Occupation, Firebender Ascension, Cruel Administrator) —
    reads the ``tree_synthesis`` ``synth_firebending_matters`` node
    (:func:`_arm_firebending_matters`) → matters. The deleted flat
    ``_FIREBEND_RE`` mirror double-counted Firebending Lesson (the card's
    OWN NAME contains "Firebending", zero mechanic relevance) — the bucket-B
    arm's narrower anchor sheds that adjudicated over-fire. makers ==
    26 commander, matters == 9 (5 AddKeyword + 4 bucket-B).
    """
    out: list[Signal] = []
    seen: set[str] = set()
    low = {k.lower() for k in keywords}

    def emit(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    # Tier-1 (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2 fold): the
    # deleted lane-time ``route(desc)`` text scan is split into two fully
    # structural reads — the ``RegisterBending`` node's own typed ``kind``
    # field ("Air"/"Earth") and the Waterbend cost-leaf TAG, neither needs
    # text — plus the ``synth_bending_cross`` bucket-B union for the
    # ``ElementalBend`` trigger residual (:func:`_arm_bending_cross`, Avatar
    # Aang's cross-bend payoff, which carries no per-element typed payload).
    for unit in tree.units:
        desc = getattr(unit.node, "description", None) or ""
        for q in iter_typed_nodes(unit.node):
            if tag_of(q) != "RegisterBending":
                continue
            kind = getattr(q, "kind", None)
            if kind == "Air":
                emit("airbend_makers", desc)
            elif kind == "Earth" and "earthbend" not in low:
                emit("earthbend_matters", desc)
        if unit.kind == "Activated":
            cost = getattr(unit.node, "cost", None)
            if any(
                tag_of(leaf) == "Waterbend" for leaf in iter_cost_leaves(cost)
            ) and any(_wb_dropped_other(c) for c in unit.effects):
                emit("waterbend_matters", desc)
    for c in tree.iter_concepts():
        if c.concept != "synth_bending_cross":
            continue
        for word in c.subject:
            if word == "airbend":
                emit("airbend_makers", "")
            elif word == "earthbend" and "earthbend" not in low:
                emit("earthbend_matters", "")
            elif word == "waterbend":
                emit("waterbend_matters", "")
    if "firebending" in low:
        out.append(Signal("firebending_makers", "you", "", "", tree.name, "high"))
    elif has_structural_firebending_grant(tree):
        out.append(Signal("firebending_matters", "you", "", "", tree.name, "high"))
    else:
        for c in tree.iter_concepts():
            if c.concept == "synth_firebending_matters":
                out.append(
                    Signal("firebending_matters", "you", "", "", tree.name, "high")
                )
                break
    return out


def _station_lanes(tree: ConceptTree, keywords: frozenset[str]) -> list[Signal]:
    """station_makers / station_matters (§2, ADR-0036/0037 Stage 5 fold,
    Tier-1) — CR 702.184a/702.184b. A card PERFORMS station when it (a)
    BEARS the Scryfall Station keyword, (b) IS a Spacecraft/Planet body —
    the typed ``tree.card_subtypes`` read, or (c) CHARGES one — a typed
    ``PutCounter`` charge-counter node co-occurring, in the SAME ability
    unit, with a typed filter naming Spacecraft/Planet
    (:func:`has_structural_station_charge` — Drill Too Deep, Systems
    Override) → station_makers. Else it NAMES Spacecraft/Planet to
    count/destroy/gate — a typed filter read
    (:func:`has_structural_station_reference` — Focus Fire, Gravkill,
    8/9 of the live non-bearer set) → station_matters. The residual
    bucket-B tail — Tractor Beam's own printed "Enchant creature or
    Spacecraft" restriction, which phase drops entirely — reads the
    ``tree_synthesis`` ``synth_station_matters`` node
    (:func:`_arm_station_matters`) → station_matters. Loading Zone
    RECLASSIFIES makers → matters vs the deleted flat mirror (it's a
    generic ANY-counter doubler naming Spacecraft/Planet among other
    permanent types, not a station-specific charge effect — a genuine
    "cares about" support card, not a "performs station" card; adjudicated
    improvement). makers == 33 commander, matters == 11 (10 typed + 1
    bucket-B) per the Loading Zone reclass.

    Documented live GAP (pinned negative, NOT parity): Tapestry Warden —
    the plural verb "stations" (CR 702.184c's own Example names it) —
    phase structures it as ``CrewContribution/ToughnessInsteadOfPower``,
    no Spacecraft/Planet typed filter anywhere on the card — a candidate
    widen for a later fix batch (parity-first, the Essence Symbiote
    precedent).
    """
    low = {k.lower() for k in keywords}
    makers = (
        "station" in low
        or any(s in _STATION_SUBTYPES for s in tree.card_subtypes)
        or has_structural_station_charge(tree)
    )
    if makers:
        return [Signal("station_makers", "you", "", "", tree.name, "high")]
    if has_structural_station_reference(tree):
        return [Signal("station_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_station_matters":
            return [Signal("station_matters", "you", "", "", tree.name, "high")]
    return []


def _evasion_self(tree: ConceptTree) -> list[Signal]:
    """A card that CARRIES or GRANTS evasion (CR 509.1b evasion
    blocking-restriction abilities + 702.14 landwalk). Tier-1: zero oracle
    text / regex at lane time (ADR-0036 fold — ``_EVASION_SELF_REGEX`` is
    deleted).

    The six keyword rows (menace/fear/intimidate/skulk/horsemanship/shadow)
    PLUS the five landwalk keywords (CR numbers at
    :func:`_keyword_field_signals_b15`) ride the Scryfall keyword-field arm;
    flying is DELIBERATELY absent (soft evasion). Do NOT key the
    ``CantBeBlocked`` static tag structurally — phase hangs it under
    activated GenericEffects (Giant Koi) and reading it would drift the
    1646-row population; the ``tree_synthesis`` bucket-B arm
    (:func:`_arm_evasion_self`) relocates the deleted mirror's can't-be-
    blocked / unblockable / granted-keyword / granted-landwalk tail instead
    (the hoser / keyword-tribe-reference / mode-label / evasion-denial
    over-fires it shed are documented there). Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_evasion_self":
            return [Signal("evasion_self", "you", "", "", tree.name, "high")]
    return []


def _cant_block_grant(tree: ConceptTree) -> list[Signal]:
    """cant_block_grant (§4) — CR 509.1b + 101.2: forcing blockers off
    clears an attack path. Tier-1 (ADR-0036/0037 Stage 5 T9-finalize fold
    — both marker passes are RETIRED to a gap-gated bucket-B synth arm).
    Structural: a ``CantBlock``-mode static def (top-level or nested under
    a spell's GenericEffect — Blindblast's ``ParentTarget``), gated to the
    projection's themeable affected shapes (a SelfRef affected is the
    Arco-Flagellant SELF-drawback, pop False), minus the pacify shape (a
    single-attached CantBlock whose cant-attack SIBLING covers the SAME
    affected — Pacifism's split statics are single-target removal, the
    project :2325-2374 suppression). Symmetric table statics (Bedlam) ARE
    members — no opponent-only scope gate. The ``synth_cant_block_grant``
    node (:func:`_arm_cant_block_grant`) covers the two marker passes phase
    drops the grant for ENTIRELY: a per-unit raw scan (make_token units
    excluded — a created token's own "can't block" drawback is not a
    grant, project's ``_CANT_BLOCK_CARRIERS``) and the dropped-static
    modal-bullet / grant-quote segments over the whole oracle. Scope
    "you", HIGH (the lane sits in ``_VOLTRON_HAS_OTHER_PLAN_COMPAT`` — a
    signals.py concern the port does not touch).
    """
    if has_structural_cant_block_grant(tree):
        return [Signal("cant_block_grant", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_cant_block_grant":
            return [Signal("cant_block_grant", "you", "", "", tree.name, "high")]
    return []


def _global_ability_grant(tree: ConceptTree) -> list[Signal]:
    """global_ability_grant (§5) — CR 113.3 (the four ability categories) /
    604.3 / 613.1f (Layer 6): a QUOTED activated/triggered/static ability
    granted to your whole creature board or an all-permanents set; the
    QUOTE (a Grant* modification carrying a structured definition) splits
    it from a bare AddKeyword anthem (grant_keyword's lane — Archetype of
    Imagination never fires). The FOUR project gates verbatim
    (project.py:5997-6075): opponent-controller exclusion; the
    single-permanent EnchantedBy/EquippedBy exclusion (without it every
    "Enchanted creature has '…'" Aura floods in); creature-board =
    "Creature" core type + (controller You OR an Owned predicate);
    all-permanents = bare set (controller null, no subtypes, no
    predicates — so "All Slivers have '…'" subtype sets stay out).
    TOP-LEVEL statics only (the marker's own read — Mathas's nested
    per-target GrantTrigger is not a board grant). Scope "any" (the
    deleted SWEEP detector hard-fired "any" — live's firing identity).
    """
    for unit in tree.units:
        if unit.origin != "static":
            continue
        sdef = unit.node
        mods = getattr(sdef, "modifications", None) or []
        if not any(
            isinstance(m, TypedMirrorNode) and tag_of(m) in _GRANT_ABILITY_MOD_TAGS
            for m in mods
        ):
            continue
        aff = getattr(sdef, "affected", None)
        tag = tag_of(aff)
        if tag == "Typed":
            ctrl = filter_controller(aff)
            preds = set(filter_predicates(aff))
            # A {Non: X} composite is a narrowing predicate in the
            # projection (_composite_predicates), so a "Non-Spirit
            # creatures have '…'" set is NOT a bare all-set (Clash of
            # Realities, shadow-diff-tuned).
            non_narrowed = bool(filter_non_types(aff))
        elif tag == "Or":
            # The projection's ``_merge_filters`` Or semantics: types
            # union, controller kept only when all members agree,
            # PREDICATES DROPPED (Callaphe's "creatures and enchantments
            # you control", Great Divide Guide's "each land and Ally";
            # Essence Leak's enchanted-permanent Or merges to a bare
            # Permanent all-set — live's own firing, reproduced as-is).
            members = [
                s
                for s in getattr(aff, "filters", ()) or ()
                if isinstance(s, TypedMirrorNode)
            ]
            ctrls = {filter_controller(s) for s in members}
            ctrl = next(iter(ctrls)) if len(ctrls) == 1 else None
            preds = set()
            non_narrowed = False
        else:
            continue
        if ctrl == "Opponent":
            continue
        if preds & _SINGLE_PERMANENT_GRANT_PREDS:
            continue
        owned = any(p == "Owned" or p.startswith("Owned") for p in preds)
        creature_board = "Creature" in filter_core_types(aff) and (
            ctrl == "You" or owned
        )
        all_permanents = (
            ctrl is None and not filter_subtypes(aff) and not preds and not non_narrowed
        )
        # YOUR-permanents board grant (task #84): "Permanents you control
        # have '…'" — phase v0.23.0 fixed Cursed Wombat's affected filter
        # from the nonsense ``[Creature, Subtype:Permanent]`` (which the
        # creature_board arm read, accidentally right) to the honest bare
        # ``[Permanent]`` + controller You. A quoted ability granted to
        # your WHOLE permanent board is a board grant a fortiori (the set
        # is a superset of the creature board — CR 613.1f layer 6);
        # corpus-exhaustive at the v0.23.0 census: Cursed Wombat is the
        # sole carrier of this shape.
        your_permanents = (
            "Permanent" in filter_core_types(aff)
            and ctrl == "You"
            and not filter_subtypes(aff)
            and not preds
            and not non_narrowed
        )
        if creature_board or all_permanents or your_permanents:
            raw = getattr(sdef, "description", None) or ""
            return [Signal("global_ability_grant", "any", "", raw, tree.name, "high")]
    return []


def _opponent_counter_grant(tree: ConceptTree) -> list[Signal]:
    """opponent_counter_grant (§6) — CR 122.1 / 122.1d (the stun-counter
    untap replacement — the canonical detrimental mark): a DETRIMENTAL
    counter placed on an OPPONENT's permanent. Tier-1 (ADR-0036/0037
    Stage 5 T9-finalize fold — the co-tap anaphora whole-oracle FALLBACK
    is RETIRED to a gap-gated bucket-B synth arm; the per-unit join
    itself, :func:`has_structural_opponent_counter_grant`, is untouched):
    a ``place_counter`` whose kind is NOT beneficial (the imported live
    ``_OPP_COUNTER_BENEFICIAL`` — p1p1/shield/keyword counters HELP the
    recipient: Hunter of Eyeblights places a +1/+1 to enable its own
    removal, the wrong direction, pop False) AND either (A) the counter's
    own target controller is Opponent (Mathas's bounty), or (B) kind ==
    "stun" with a co-occurring same-unit tap of an opp-controller subject
    read off the unit's OWN ``description``. The
    ``synth_opponent_counter_grant`` node
    (:func:`_arm_opponent_counter_grant`) covers the cases where that
    field is empty and only a whole-oracle anaphora-recovery scan finds
    the co-tap (Freeze in Place's "tap … and put a stun counter on IT" —
    the pronoun-loss recovery). Self-stun drawbacks have no opp recipient
    and no co-tap (Pugnacious Hammerskull stuns ITSELF, pop False). Scope
    "opponents", HIGH.
    """
    key = "opponent_counter_grant"
    if has_structural_opponent_counter_grant(tree):
        return [Signal(key, "opponents", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_opponent_counter_grant":
            return [Signal(key, "opponents", "", "", tree.name, "high")]
    return []


def _conditional_self_protection(tree: ConceptTree) -> list[Signal]:
    """conditional_self_protection (§7) — the protective-keyword subset
    (hexproof CR 702.11, indestructible 702.12, protection 702.16, shroud
    702.18, ward 702.21): a top-level STATIC with a condition granting a
    protective keyword to ITSELF. Three discriminators, matching the live
    :8834-8849 read: (1) the def carries a condition (Dragonlord Ojutai's
    ``Not(SourceIsTapped)``, Fleecemane Lion's ``SourceIsMonstrous``) —
    intrinsic printed hexproof rides the keyword array, never a
    conditioned grant (Sigarda, pop False); (2) affected SelfRef —
    team/aura/equipment conditioned grants are other lanes; (3) an
    ``AddKeyword`` whose name lowercases into the imported live
    ``_SELF_PROTECTION_GRANT_KW`` — a conditional combat buff ("during
    your turn, ~ has deathtouch/flying") stays out. Scope "you", HIGH
    (the lane sits in the regex-side ``_VOLTRON_COMPAT_KEYS`` — a
    signals.py concern the port does not touch).
    """
    for unit in tree.units:
        if unit.origin != "static":
            continue
        sdef = unit.node
        if not isinstance(getattr(sdef, "condition", None), TypedMirrorNode):
            continue
        # SourceOrPaired == the soulbond self-pair grant (Elgaud Shieldmate)
        # — the projection folds it to a SelfRef subject (a live member).
        if tag_of(getattr(sdef, "affected", None)) not in (
            "SelfRef",
            "SourceOrPaired",
        ):
            continue
        for mod in getattr(sdef, "modifications", None) or []:
            if not isinstance(mod, TypedMirrorNode) or tag_of(mod) != "AddKeyword":
                continue
            # PLAIN-string keywords only — the live projection drops the
            # PARAMETERIZED variants ({Protection: from-X}, {Ward: cost}),
            # so Etched Champion / Hexdrinker / Iymrith / Pristine Angel
            # never fire live (shadow-diff-tuned, 9 over-fires). The
            # parameterized Protection/Ward conditioned self-grant is a
            # LOGGED candidate adjudicated widen, NOT parity.
            kw = getattr(mod, "keyword", None)
            if not isinstance(kw, str):
                continue
            if kw.lower() in _SELF_PROTECTION_GRANT_KW:
                raw = getattr(sdef, "description", None) or ""
                return [
                    Signal(
                        "conditional_self_protection",
                        "you",
                        "",
                        raw,
                        tree.name,
                        "high",
                    )
                ]
    return []


def _sacrifice_protection(tree: ConceptTree) -> list[Signal]:
    """sacrifice_protection (§8) — CR 701.21a (a sacrifice is the
    controller's move; "can't cause you to sacrifice" wins by 101.2). Tier-1
    (ADR-0036/0037 fold — the ``_SAC_PROTECTION_MIRROR`` kept-mirror is
    RETIRED): the verdict RE-CONFIRMED against v0.9.0 — Sigarda still parses
    as ``abilities/Spell.effect/Unimplemented`` ([P42], SUPPLEMENT-
    RECOVERABLE), so the two literal phrases stay the only full-coverage
    tell and there is no competing Tier-1 predicate — the ``tree_synthesis``
    stage's ``synth_sacrifice_protection`` node is the lane's SOLE source. A
    stax EDICT ("sacrifice a creature") never contains either phrase
    (Ghostly Prison, pop False). Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_sacrifice_protection":
            return [Signal("sacrifice_protection", "you", "", "", tree.name, "high")]
    return []


def _life_payment_insurance(tree: ConceptTree) -> list[Signal]:
    """life_payment_insurance (§9) — CR 119.4 (a pay-life cost subtracts
    from the total only if life ≥ amount — a repeatable pay-life COST
    wants lifegain insurance). Tier-1 (ADR-0036/0037 fold — the lane-time
    ``_PAY_LIFE_REF`` kept-oracle read is RETIRED):

    * **Structural:** :func:`has_structural_life_payment_insurance` — the
      cost census, any Activated unit whose flattened cost carries a
      ``PayLife`` leaf (unconditional; the sibling lifeloss_makers arm adds
      the non-ramp/non-land gates, NOT this lane).
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_life_payment_insurance`` node — the granted-ability text
      residue ("Other Caves have '…Pay N life:…'" — Forgotten Monument)
      phase never structures onto THIS card (an ``AddAbility`` text
      payload, not a typed leaf), gated against the same structural cost
      census. Arco-Flagellant NOW parses ``Activated.cost/PayLife`` at
      v0.9.0 — the marker→structural arm shift inside an unchanged union is
      the expected (LOGGED) divergence.

    A one-shot cast cost (Toxic Deluge) and effect-side life loss (Sign in
    Blood) never fire either arm. Scope "you", HIGH.
    """
    if has_structural_life_payment_insurance(tree):
        return [Signal("life_payment_insurance", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_life_payment_insurance":
            return [Signal("life_payment_insurance", "you", "", "", tree.name, "high")]
    return []


def _speed_doer(tree: ConceptTree) -> list[Signal]:
    """speed_makers doer arm (§10) — CR 702.179a: a keyword-less
    speed-CHANGER PERFORMS a speed change (Spikeshell Harrier's
    ``ChangeSpeed``, Ghirapur Grand Prix's ``StartYourEngines``-as-effect)
    → MAKER. The keyword rows (both lanes) ride
    :func:`_keyword_field_signals_b15`; speed_matters takes NO structural
    arm — parity is the keyword set alone (the live migration measured
    41==41). LOGGED, not taken: ``HasMaxSpeed`` condition/replacement
    reads (Vnwxt) would over-fire onto max-speed CONDITION references
    beyond the printed-keyword identity. Scope "you", HIGH.
    """
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) in _SPEED_DOER_TAGS:
                return [Signal("speed_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _exhaust_matters(tree: ConceptTree) -> list[Signal]:
    """exhaust_matters (§11) — CR 702.177a/702.177b: the exhaust PAYOFF
    (triggers/conditions on ACTIVATING exhaust abilities; the DOER rides
    the ported b13 exhaust_makers keyword row — Bitter Work, pop False
    here). Two arms: (a) a trigger whose mode is
    ``KeywordAbilityActivated`` with keyword parameter ``Exhaust`` (Sala —
    the parameter gate keeps Outlast/other modes out: Herald of Anafenza
    never fires); (b) the project raw anchor (``_EXHAUST_TRIG``,
    project.py:1597-1599) over unit raws — the live marker fires
    REGARDLESS of trigger event, reaching the
    delayed-trigger-inside-activated payoff (Pit Automaton —
    ``Activated.effect/Unimplemented``, [P44]) and the permission static
    (Elvish Refueler — fires BOTH lanes: makers via keyword, matters via
    the anchor). Tier-1 (ADR-0036/0037 T10-finalize2 fold): arm (b)'s
    deleted lane-time ``_EXHAUST_TRIG`` scan is relocated verbatim to the
    bucket-B ``synth_exhaust_matters`` node (:func:`_arm_exhaust_matters`);
    arm (a) stays a pure typed mode/keyword-parameter read, zero oracle
    text/regex at LANE time. Scope "you", HIGH.
    """
    for unit in tree.units:
        mode = getattr(unit.node, "mode", None)
        if (
            isinstance(mode, MirrorVariant)
            and mode.key == "KeywordAbilityActivated"
            and tag_of(mode.inner) == "Exhaust"
        ):
            return [Signal("exhaust_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_exhaust_matters":
            return [Signal("exhaust_matters", "you", "", "", tree.name, "high")]
    return []


def _saddle_matters_lane(tree: ConceptTree) -> list[Signal]:
    """saddle_matters typed arms (§12) — CR 702.171a (one lane, no
    maker/matters split live: bearers + granters + payoffs). The keyword
    row rides :func:`_keyword_field_signals_b15`; the typed arms cover the
    keyword-less granters/payoffs: a ``BecomeSaddled`` node (Kolodin,
    Alacrian Armory, Guidelight Matrix — the exact keyword-less live
    residue) or a ``SaddledSource`` property filter (The Gitrog's
    sacrifice rider). The ``_SADDLE_REF`` raw anchor is deliberately NOT
    ported: the live marker is carrier-category-gated
    (project.py:1503-1545) and the crosswalk's unit raws cannot reproduce
    that gate — an ungated anchor over unit descriptions over-fires the
    saddles-or-crews trigger cards live excludes (Back on Track); the
    keyword row + typed arms already reproduce the live pop 36/36
    (PARITY-BEFORE-VETO — the current-corpus anchor residue is empty).
    Crew alone never fires (Smuggler's Copter — Vehicles are not Mounts).
    Scope "you", HIGH.
    """
    for unit in tree.units:
        if any(
            tag_of(q) == "BecomeSaddled" for q in iter_typed_nodes(unit.node)
        ) or has_filter_property(unit.node, "SaddledSource"):
            return [Signal("saddle_matters", "you", "", "", tree.name, "high")]
    return []


def _suspect_matters_lane(tree: ConceptTree) -> list[Signal]:
    """suspect_matters (§13) — CR 701.60a/701.60b (suspected is a
    DESIGNATION, not an ability; the ADR-0034 boundary: the suspect VERB =
    maker, ported b4; the pure "suspected"-STATE reference = matters).
    Nelly Borca's raw carries BOTH forms and the verb wins (pop False —
    polarity-from-pop pin); Agency Coroner (the swallowed rider, [P43]) and
    Airtight Alibi (Unsuspect/``CantBecomeSuspected`` carriers project no
    suspect concept) both fire via the marker re-derivation route. LOGGED,
    not taken: the ``Suspected`` property — a structural upgrade candidate
    that would over-fire Nelly today.

    Tier-1 (ADR-0036/0037 fold): no clean structural separation from the
    suspect VERB exists without reading the carrying unit's own raw text,
    so both original arms (the native-effect raw check, the
    ``_SUSPECT_REF`` marker fallback) relocate verbatim into the
    ``synth_suspect_matters`` bucket-B node (:func:`_arm_suspect_matters`)
    — the lane's SOLE source, zero oracle text/regex at LANE time. Scope
    "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_suspect_matters":
            return [Signal("suspect_matters", "you", "", "", tree.name, "high")]
    return []


def _void_warp_makers(tree: ConceptTree) -> list[Signal]:
    """void_warp_makers (§14) — CR 702.185a Warp (two statics while on the
    stack: cast from hand for [cost], exile at next end step with a
    re-cast permission; alternative-cost rules 601.2b/f-h) + CR 207.2c
    (void is an ABILITY WORD — no rules meaning, hence no phase keyword).
    Tier-1 (ADR-0036/0037 fold — the ``_VOID_WARP_MAKERS_RX`` kept-mirror is
    RETIRED): the three PERFORM/GRANT forms (keyword bearers — "Warp {1}{U}"
    — Starfield Vocalist; granters — "have warp {2}{R}" — Tannuk; the
    em-dash + graveyard self-cast forms — "Warp—{B}" / "using its warp
    ability" — Timeline Culler) have no competing Tier-1 predicate (v0.9.0's
    parameterized ``{Warp: cost}`` keyword array under-fires the granters,
    and a synth arm sees only the tree, never the Scryfall keyword array
    that WOULD need a second keyword-blind gap-check), so the
    ``tree_synthesis`` stage's ``synth_void_warp_makers`` node is the
    lane's SOLE source. The PAYOFF arm (void_warp_matters) is the batch-12
    skip-sweep lane — NOT this batch, never absorbed (Alpharael's "a spell
    was warped this turn" Void payoff, pop False here). Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_void_warp_makers":
            return [Signal("void_warp_makers", "you", "", "", tree.name, "high")]
    return []


# ── Batch 16 lanes (ADR-0035 Stage 2 — THE FINAL structural batch) ───────────

# Byte-identical inline copies of the live INLINE (unnamed) kept-detector rows
# (_IR_KEPT_DETECTORS / the deleted-producer patterns) — the b12 _JOHAN_MIRROR
# precedent for rows with no importable name. Named live constants are imported
# above (one source, zero drift):
# _TYPED_ANTHEM_MULTI_RAW. (island_makers, ability_copy,
# noncombat_damage_payoff, per_target_payoff, power_tap_engine,
# starting_life_matters, meld_pair, and toughness_combat were ADR-0036/0037
# folded to Tier-1 structural / bucket-B synth reads — see
# ``_island_makers``, ``_ability_copy``, ``_noncombat_damage_payoff``,
# ``_per_target_payoff``, ``_power_tap_engine``, ``_starting_life_matters``,
# ``_meld_pair``, ``_toughness_combat``.)

# Counter-placement effect tags (the live place_counter category's producers)
# for the ability_strip same-unit join (§2).
_B16_PLACE_COUNTER_TAGS: frozenset[str] = frozenset(
    {"PutCounter", "PutCounterAll", "AddPendingETBCounters"}
)
# (``_ANTHEM_PUMP_MODS`` moved to ``tree_synthesis`` — ADR-0036/0037
# T10-finalize2, the ``_DEATH_PAYOFF_EFFECTS`` neutral-home precedent —
# and imported back below.)
# Static modification families the OLD projection kept as subject-bearing
# effects (pump / base-P/T-set / strip) — the named_counter_misc static
# sub-arm's gate: an affected-filter counter pred on one of these (or on a
# plain-string restriction mode with no modifications — CantUntap) fired
# live via the projected effect subject; the dropped-static families
# (AddAllLandTypes, ModifyCost) never did. CR 122.1 / 613.4c.
_B16_STATIC_KEPT_MODS: frozenset[str] = (
    _WB_PT_SET_MODS | _ANTHEM_PUMP_MODS | frozenset({"RemoveAllAbilities"})
)


def _keyword_field_signals_b16(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-16 Scryfall-keyword field-lookup: exalted (CR 702.83a — "a
    creature you control attacks alone, that creature gets +1/+1").

    The row emits BOTH ``exalted_lone_attacker`` AND the already-ported
    ``voltron_matters`` — an exalted commander pumps a LONE attacker (itself),
    the canonical single-big-threat suit-up. This mirrors the live
    ``_IR_KEYWORD_MAP['exalted']`` tuple byte-identically; emitting only one
    half would drift the sibling. Scope "you", HIGH.
    """
    if "exalted" in {k.lower() for k in keywords}:
        return [
            Signal("exalted_lone_attacker", "you", "", "", name, "high"),
            Signal("voltron_matters", "you", "", "", name, "high"),
        ]
    return []


def _keyword_field_signals_w4g(keywords: frozenset[str], name: str) -> list[Signal]:
    """ADR-0038 W4 giant — Investigate (CR 701.27) IS "create a Clue token", a
    colorless ARTIFACT (CR 205.3g). phase tags the keyword but drops the Clue
    subtype off the ``make_token`` subject (the keyword-action's reminder
    text isn't structured — Declaration in Stone, No Witnesses, Fateful
    Absence all carry ``make_token`` subject=None or no make_token node at
    all for a modal/rider investigate), so the keyword array is the
    structural anchor. Mirrors the deleted ``_signals_ir``'s
    ``_IR_KEYWORD_MAP["investigate"]``
    byte-identically (``artifacts_matter`` you, high). The dedicated
    ``clue_matters`` lane reads investigate off its own path; this opens
    ``artifacts_matter``, which has no other tell for these.
    """
    if "investigate" in {k.lower() for k in keywords}:
        return [Signal("artifacts_matter", "you", "", "", name, "high")]
    return []


def _ability_copy(tree: ConceptTree) -> list[Signal]:
    """ability_copy (§1) — CR 707.10 ("To copy a spell, activated ability, or
    triggered ability means to put a copy of it onto the stack; … A copy of an
    ability is itself an ability.") + 113.2b. (The live docstrings' "CR
    706.10 / 706.2" cites are STALE — 706 is now die-rolling; corrected here.)

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_ABILITY_COPY_MIRROR``
    kept-oracle read is RETIRED): the ``tree_synthesis`` stage's
    ``synth_ability_copy`` node — the ability-copiers (Strionic Resonator,
    Rings of Brighthearth), the "you may copy it" self-copiers (Chancellor
    of Tales), and the whole-suite importers ("has all activated abilities
    of" — Necrotic Ooze) — is the lane's SOLE source (no competing Tier-1
    predicate: phase's CopySpell flattens ability-copy and spell-copy into
    one category, so a ``category == "spell_copy"`` arm 90%-over-fires onto
    Twincast/Fork/Reiterate — pop-verified False — while still missing the
    ability-granters). LOGGED widen (closeout §C): the v0.9.0
    CopySpell.target StackAbility-vs-StackSpell discriminator +
    GrantAllActivatedAbilitiesOf, when they land, structure this lane — a
    candidate structural split. Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_ability_copy":
            return [Signal("ability_copy", "you", "", "", tree.name, "high")]
    return []


def _ability_strip_payoff(tree: ConceptTree) -> list[Signal]:
    """ability_strip_payoff (§2) — CR 613.1f (layer 6: ability-removing
    effects) + 122.1b (keyword counters — Abigale's flying / first strike /
    lifelink counters are exactly the CR's keyword-counter set).

    Granularity (a) same-ability join, fully typed: ONE unit carries a
    ``RemoveAllAbilities`` modification (the live "loses all abilities" raw
    anchor is its projection) AND a counter-placement concept — a PutCounter
    node (Abigale's SequentialSibling chain of three keyword counters) OR a
    ``ChangeZone`` with non-empty ``enter_with_counters`` (Hellcat, whose
    record carries NO PutCounter node — the live place_counter comes from the
    enter-with-counters recovery) — AND no base-P/T-set modification
    (:data:`_WB_PT_SET_MODS` — the shrinker veto: Turn to Frog / Ovinize turn
    the target into a small body, not a kept beater). The SequentialSibling
    chain is ONE unit (the tree walk descends sub_ability — the v76 per-arm
    rule needs no raw read here). Retched Wretch's counter ref is the trigger
    CONDITION, never a placement — pop-verified False. Scope "you", HIGH.
    """
    for unit in tree.units:
        has_strip = False
        has_counter = False
        has_shrink = False
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "RemoveAllAbilities":
                has_strip = True
            elif t in _B16_PLACE_COUNTER_TAGS:
                has_counter = True
            elif t in _WB_PT_SET_MODS:
                has_shrink = True
            elif t == "ChangeZone":
                ewc = getattr(n, "enter_with_counters", None)
                if isinstance(ewc, list) and ewc:
                    has_counter = True
        if has_strip and has_counter and not has_shrink:
            return [Signal("ability_strip_payoff", "you", "", "", tree.name, "high")]
    return []


def _arcane_matters(tree: ConceptTree) -> list[Signal]:
    """arcane_matters (§3) — CR 205.3k (Arcane is a SPELL type) + 304.3/307.3
    + 702.47a (Splice onto Arcane). Tier-1 (ADR-0036 fold): direct — a
    typed filter naming the Arcane spell subtype (a payoff — Tallowisp,
    Sideswipe), :func:`has_structural_arcane` in ``tree_synthesis``.
    bucket-B: the residual "Splice onto Arcane" tail phase drops ENTIRELY
    (Glacial Ray — zero units for the whole card), read off the
    ``synth_arcane_matters`` node (:func:`_arm_arcane_matters`). Being
    Arcane-TYPED is NOT itself membership (probed: 66 of 95 corpus
    Arcane-typed cards carry no arcane-caring text at all). Scope "you",
    HIGH.
    """
    if has_structural_arcane(tree):
        return [Signal("arcane_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_arcane_matters":
            return [Signal("arcane_matters", "you", "", "", tree.name, "high")]
    return []


def _celebration_matters(tree: ConceptTree) -> list[Signal]:
    """celebration_matters (§4) — CR 207.2c: celebration is an ABILITY WORD
    ("no special rules meaning and no individual entries in the Comprehensive
    Rules") — there is no structured rules object for phase to parse (probed:
    Ash, Party Crasher carries "Celebration —" only in strings), so this is
    the lane's SOLE source — Tier-1 (ADR-0036 fold): reads the
    ``synth_celebration_matters`` bucket-B node (:func:`_arm_celebration_matters`
    in ``tree_synthesis``), zero oracle text / regex at LANE time. Scope
    "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_celebration_matters":
            return [Signal("celebration_matters", "you", "", "", tree.name, "high")]
    return []


def _cmdzone_ability(tree: ConceptTree) -> list[Signal]:
    """cmdzone_ability (§5) — CR 113.6 (abilities usually function on the
    battlefield; the command-zone-stated abilities are the exceptions) +
    207.2c (eminence is an ability word) + 903.6. (The live "113.6k" cite is
    STALE — per the current CR that is the multi-zone trigger-condition rule,
    still apt for the Oloro trigger half but not the lane's grounding.)

    A recursive condition-tree read: any ``SourceInZone`` node with zone
    ``Command`` under the unit (Oloro's trigger condition; The Ur-Dragon's
    Eminence static ``Or[SourceInZone Command, SourceInZone Battlefield]``).
    Deliberately NOT the raw ``trigger_zones``/``active_zones`` lists: phase
    stamps 'Command' into every plane/scheme trigger_zones and every
    on-stack cost-static active_zones (Thrasta), which the live projection
    never surfaced — the condition tree is the live-parity discriminator
    (over-fire == 0; Command Beacon's EFFECT moves the commander FROM the
    zone and carries no zone condition, pop-verified False). Scope "you",
    HIGH.
    """
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "SourceInZone" and getattr(n, "zone", None) == "Command":
                return [Signal("cmdzone_ability", "you", "", "", tree.name, "high")]
    return []


def _exalted_textual(tree: ConceptTree) -> list[Signal]:
    """exalted_lone_attacker textual arm (§6) — CR 702.83a/702.83b + 506.5
    ("A creature attacks alone if it's the only creature declared as an
    attacker"). Tier-1 (ADR-0036 fold): reads the
    ``synth_exalted_lone_attacker`` bucket-B node
    (:func:`_arm_exalted_lone_attacker` in ``tree_synthesis``) for the
    textual grants/payoffs ("X have exalted", Agents of S.H.I.E.L.D.'s
    attacks-alone trigger). **Not** the phase ``SourceAttackingAlone`` /
    ``AttackingAlone`` / ``BlockingAlone`` / ``CombatAlone`` tags — probed
    and REJECTED, those structure the UNRELATED "can't be blocked while
    attacking alone" evasion family (Dream Prowler), a genuine 4-card
    over-fire on the corpus — so this arm has no competing structural gate,
    the lane's SOLE source. The keyword-bearer row rides
    :func:`_keyword_field_signals_b16` (emitting the voltron pair); the
    synth node is a strict superset of the bearers (every bearer carries the
    word) — ``add()`` dedups. Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_exalted_lone_attacker":
            return [Signal("exalted_lone_attacker", "you", "", "", tree.name, "high")]
    return []


def _flip_self(tree: ConceptTree) -> list[Signal]:
    """flip_self (§7) — CR 710.1/710.2 (flip cards; live cite CORRECT): the
    Kamigawa flip fronts (Nezumi Graverobber, Bushi Tenderfoot). Tier-1
    structural (ADR-0036 mirror fold): since the v0.45.0 pin phase parses
    every creature-flip to a typed ``FlipPermanent`` node (the v0.37.0
    flip-card arrival; 19 corpus nodes) — read it directly, a superset of
    the ``\\bflip this creature\\b`` mirror that uniformly closes the
    documented Akki Lavarunner ("flip it") / Erayo ("flip Erayo") /
    Rune-Tail ("flip Rune-Tail") wording gap (+10 real Kamigawa flips). The
    pre-v0.45.0 ``Unimplemented{name=='flip'}`` residue read is kept as a
    fallback arm (nothing emits it at the current pin; it self-retires if a
    future corpus regen proves it dead). Gate: a coin-flip card's "flip
    again" was the residue read's collision (Game of Chaos) — a card
    carrying a ``FlipCoin`` node is coin-flip recursion, not a
    creature-flip, and is excluded (CR 705). Scope "you", HIGH.
    """
    if any(
        tag_of(n) == "FlipCoin"
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
    ):
        return []
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "FlipPermanent" or (
                tag_of(n) == "Unimplemented" and getattr(n, "name", None) == "flip"
            ):
                return [Signal("flip_self", "you", "", "", tree.name, "high")]
    return []


def _free_creature_payoff(tree: ConceptTree) -> list[Signal]:
    """free_creature_payoff (§8) — CR 601.2f-h + 118.7 ("If the mana
    component of a cost is reduced to nothing … it's considered to be {0}" —
    a 0-cost creature is CAST with no mana spent). (The live "CR 712 /
    601.2h" cite is STALE — 712 is now Double-Faced Cards; corrected here.)

    An etb-event trigger unit with a ``ManaSpentCondition`` anywhere in its
    condition tree (Satoru nests it under ``Or[Not(WasCast), …]``). The etb
    gate is the discriminator vs the cast_spell-triggered anti-free-spell
    punishers (Lavinia / Boromir / Roiling Vortex / Vexing Bauble — pop
    False); 'WasCast' alone is NOT the tell. Scope "you", HIGH.
    """
    for unit in tree.units:
        if unit.trigger_event != "enters":
            continue
        if any(tag_of(n) == "ManaSpentCondition" for n in iter_typed_nodes(unit.node)):
            return [Signal("free_creature_payoff", "you", "", "", tree.name, "high")]
    return []


def _free_spell_storm(tree: ConceptTree) -> list[Signal]:
    """free_spell_storm (§9) — CR 601.2f / 118.7: a per-spell SCALING
    self-discount (the SelfRef static is rules-excluded from the
    build-around cost_reduction lane — it cheapens no OTHER spell).

    Re-derives the live project marker's gate VERBATIM over the mirror
    nodes (never re-implemented from scratch): a ``ModifyCost{Reduce}``
    static whose ``affected`` is SelfRef AND whose ``dynamic_count`` is one
    of the two corpus-unique cast-this-turn shapes — ``SpellsCastThisTurn{
    scope: Controller}`` (Demilich) or an ``ObjectCount`` whose filter
    carries an ``Another`` property (Thrasta). An opponent-cast scaler
    (Delightful Discovery — ObjectCount with NO Another) is excluded by the
    same gate, pop-verified False. Scope "you", HIGH.
    """
    for unit in tree.units:
        if unit.origin != "static":
            continue
        if modify_cost_mode(unit.node) != "Reduce":
            continue
        if tag_of(getattr(unit.node, "affected", None)) != "SelfRef":
            continue
        dc = static_mode_field(unit.node, "dynamic_count")
        t = tag_of(dc)
        if t == "SpellsCastThisTurn" and getattr(dc, "scope", None) == "Controller":
            return [Signal("free_spell_storm", "you", "", "", tree.name, "high")]
        if t == "ObjectCount" and has_filter_property(
            getattr(dc, "filter", None), "Another"
        ):
            return [Signal("free_spell_storm", "you", "", "", tree.name, "high")]
    return []


def _is_island_landwalk_kw(kw: object) -> bool:
    """Whether a keyword value (bare string or parameterized variant) IS
    islandwalk — the ``{"Landwalk": "Island"}`` phase shape (Thada Adel's
    OWN ``keywords`` array) or a defensive bare-string fallback."""
    if isinstance(kw, MirrorVariant):
        return kw.key == "Landwalk" and kw.inner == "Island"
    return isinstance(kw, str) and kw.lower() == "islandwalk"


def _island_makers(tree: ConceptTree) -> list[Signal]:
    """island_makers (§10) — CR 702.14a/702.14b/702.14c (landwalk is an
    evasion ability; "can't be blocked as long as the defending player
    controls … an Island"): Tier-1 (ADR-0036/0037 fold — the
    ``ISLAND_MAKERS_REGEX`` mirror is DELETED), the ADR-0034 MAKER union of
    granter / neutralizer / token-maker, every arm reading the
    ``{"Landwalk": "Island"}`` phase shape structurally. The BEARER row
    (Thada Adel) rides the Scryfall keyword-field arm — see
    ``_B13_KEYWORD_LANES``'s ``island_makers`` row, the same field-lookup
    mechanism evasion_self's landwalk family already uses.

    * **granter / neutralizer** — an ``AddKeyword``/``RemoveKeyword``
      modification whose keyword is the ``Landwalk``/``Island`` variant
      (Lord of Atlantis grants it structurally now — no more Scryfall-array
      gap; Mystic Decree's ``RemoveKeyword`` neutralizer).
    * **token-maker** — a ``make_token`` effect whose token profile's own
      ``keywords`` list carries the same variant (Chasm Skulker, Coral
      Barrier, The Sea Devils — a STRUCTURAL recovery over the mirror,
      which never saw the token's nested keyword list).

    Adjudicated mirror over-fires SHED (not bearers/granters/makers, a bare
    REFERENCE to islandwalk creatures): the evasion-DENIAL idiom "creatures
    with islandwalk can be blocked as though they didn't have islandwalk"
    (Gosta Dirk, Undertow — the sibling ``evasion_denial`` lane's
    ``IgnoreLandwalkForBlocking`` territory), a removal spell targeting
    islandwalk creatures (Merfolk Assassin), and a symmetric-protection
    reference (Island Sanctuary). The Zhou Yu attack-restriction PAYOFF is
    the sibling ``island_matters`` lane. Scope "you", HIGH.
    """
    for unit in tree.units:
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("AddKeyword", "RemoveKeyword"):
                continue
            if _is_island_landwalk_kw(getattr(mod, "keyword", None)):
                return [Signal("island_makers", "you", "", "", tree.name, "high")]
        for c in unit.effect_concepts("make_token"):
            kws = getattr(c.node, "keywords", None)
            if not isinstance(kws, list):
                continue
            for kw in kws:
                if _is_island_landwalk_kw(kw):
                    return [Signal("island_makers", "you", "", "", tree.name, "high")]
    return []


def _keyword_soup_makers(tree: ConceptTree) -> list[Signal]:
    """keyword_soup_makers (§11) — CR 122.1b (the CR's evergreen-keyword
    inventory) + 613.1f (keyword grants apply in layer 6): Tier-1 structural
    (ADR-0036 mirror fold). Count DISTINCT evergreen (``_EVERGREEN_CK``)
    ``AddKeyword`` keyword names across ALL units whose grant is
    TEAM-affected — the granting static def's ``affected`` filter names
    You-controlled creatures (``iter_mod_sites`` yields ``(sdef, mod)``; the
    per-keyword ``AddKeyword`` mod carries no ``affected``, the scope lives on
    ``sdef``) — >= 5 fires. The CARD-LEVEL union survives the modal split a
    per-site count fails (Akroma's Will's two arms), and the team-affected
    gate excludes the single-creature ABSORBERS the ``keyword_soup`` lane owns
    (Cairn Wanderer's self-grants carry ``affected: SelfRef``, not You-typed)
    — exactly the maker/absorber split the deleted ``_KEYWORD_SOUP_CONTEXT_RE``
    team-grant phrasing drew. Corpus-verified set-equal to the old mirror.
    Live is include_membership-gated; the crosswalk runs it unconditionally
    (live pops measured with the flag True — the b12 kill_engine precedent).
    Scope "you", **LOW** (the live producer's identity; never feeds
    voltron).
    """
    names: set[str] = set()
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = (mod_keyword_name(mod) or "").replace(" ", "").lower()
            if kw not in _EVERGREEN_CK:
                continue
            affected = getattr(sdef, "affected", None)
            if filter_controller(affected) == "You" and (
                "Creature" in filter_core_types(affected)
            ):
                names.add(kw)
    if len(names) >= 5:
        return [Signal("keyword_soup_makers", "you", "", "", tree.name, "low")]
    return []


def _meld_pair(tree: ConceptTree) -> list[Signal]:
    """meld_pair (§12, SUBJECT-carrying — signal_keys.MELD_PAIR) — CR
    701.42a/701.42b (meld pairs; "See rule 712, 'Double-Faced Cards.'") +
    201.4e + 712.1.

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_MELD_FULLTEXT_RE``
    UN-stripped-oracle read is RETIRED):

    (a) STRUCTURAL — :func:`has_structural_meld_pair` — a ``Meld`` effect
    node anywhere in the tree (the trigger-front's own meld — Gisela, Graf
    Rat).
    (b) the ``tree_synthesis`` stage's ``synth_meld_pair`` bucket-B node —
    the reminder-text-only partner residual ("(Melds with X.)") for the
    other 12/14 commander-legal partners phase never structures (the RESULT
    face — Brisela — names no partner), gated against (a).

    Subject = THIS card's name (the partner names it back; the subject-spec
    branch serves exactly the one partner), gated ``if name``. Scope "you",
    HIGH.
    """
    if not tree.name:
        return []
    if has_structural_meld_pair(tree):
        return [Signal(signal_keys.MELD_PAIR, "you", tree.name, "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_meld_pair":
            return [
                Signal(signal_keys.MELD_PAIR, "you", tree.name, "", tree.name, "high")
            ]
    return []


def _named_counter_misc(tree: ConceptTree) -> list[Signal]:
    """named_counter_misc (§13) — CR 122.1 ("Counters with the same name or
    description are interchangeable" — the NAME is the mechanic
    discriminant). Three live arms:

    (a) EFFECT arm — a role=effect place/remove of a kind in the CLOSED
    12-kind ``_NAMED_COUNTER_KINDS`` set (imported; deliberately POSITIVE —
    time/lore/charge own their own mechanics, a negative catch-all floods).
    Tetzimoc's ``PutCounter{counter_type: 'prey'}``. **Cost-role arm** (Tier-1
    structural, ADR-0036 mirror fold): Mazemind Tome's page ``PutCounter``
    rides an ``EffectCost`` (COST role) — the effect arm reads role=effect
    only, so a second scan digs each cost-role concept's subtree for a
    named-counter ``PutCounter``/``RemoveCounter`` (v0.9.0+ carries the kind
    inside the activation cost), replacing the flat page/study text mirror.
    (b) PREDICATE arm — the broad catch-all is CORRECT on the payoff side
    (niche≠skip): a "WITH an X counter" predicate whose live-normalized
    kind token (:func:`_counter_kind_token` — the projection's own
    normalization, imported) is NOT owned by a ported sibling (P1P1 →
    plus_one_matters, Any → any_counter_matters, ``_COUNTER_KIND_KEYS``
    kinds → their lanes — all prior-batch ports, sibling zero-drift). Three
    read sites, mirroring live's e.subject / amount.subject / trig.subject
    union: (i) every Typed filter UNDER a non-cost effect-concept node —
    the deep scan reaches the Sum-wrapped count operand the flat
    Ref-only helper misses (Rose Tyler's "for each suspended card you own
    with a time counter"); an ability WRAPPER's condition is not an effect
    node's subtree, so a condition-side pred never enters (Brood
    Astronomer's Planet-with-charge instead-gate, Phylactery Lich —
    pop-verified False; live's hascounters dispatch never feeds this lane);
    (ii) a trigger's watched subject (Sporogenesis' "nontoken creature with
    a fungus counter" dies-watcher); (iii) a STATIC def's affected filter,
    gated to the modification families the old projection KEPT as
    subject-bearing effects — P/T mods / strips (Time of Heroes' level
    anthem, Sludge Monster / Spark Rupture strips) and plain-string
    restriction modes (Rimescale Dragon / Temporal Distortion CantUntap) —
    while the dropped-static families stay out (Omo's AddAllLandTypes,
    Eluge's ModifyCost scaler — pop-verified False). Bomb Squad's fuse
    predicate rides (i). All scope "you", HIGH. (Pursuit of Knowledge's
    study counter is an effect-role placement caught by arm (a); Mazemind
    Tome's page cost is caught by the cost-role arm — the page/study text
    mirror is retired.)
    """
    for concept in ("place_counter", "remove_counter"):
        for c in tree.effect_concepts(concept):
            if counter_kind_any(c.node).lower() in _NAMED_COUNTER_KINDS:
                return [
                    Signal("named_counter_misc", "you", "", c.raw, tree.name, "high")
                ]
    # Tier-1 structural (ADR-0036 mirror fold): the page/study COST-role fold
    # (Mazemind Tome's page ``PutCounter`` rides an ``EffectCost``; arm (a)
    # reads role=effect only). v0.9.0+ carries the counter kind INSIDE the
    # activation cost, so dig the cost subtrees for a named-counter
    # ``PutCounter``/``RemoveCounter`` — replaces the flat page/study text
    # mirror (Pursuit of Knowledge already rides arm (a)'s effect-role study).
    for c in tree.iter_concepts():
        if c.role != "cost":
            continue
        for n in iter_typed_nodes(c.node):
            if tag_of(n) in ("PutCounter", "RemoveCounter") and (
                counter_kind_any(n).lower() in _NAMED_COUNTER_KINDS
            ):
                return [
                    Signal("named_counter_misc", "you", "", c.raw, tree.name, "high")
                ]

    def _misc_kind(filt: object) -> bool:
        if filt is None or filter_controller(filt) == "Opponent":
            return False
        for kind in counter_pred_kinds(filt):
            tok = "Any" if kind == "Any" else _counter_kind_token(kind)
            if tok in ("P1P1", "Any"):
                continue
            if tok.lower() in _COUNTER_KIND_KEYS:
                continue
            return True
        return False

    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for n in iter_typed_nodes(c.node):
            if tag_of(n) == "Typed" and _misc_kind(n):
                return [
                    Signal("named_counter_misc", "you", "", c.raw, tree.name, "high")
                ]
    for unit in tree.units:
        if unit.origin == "trigger" and _misc_kind(
            getattr(unit.node, "valid_card", None)
        ):
            return [Signal("named_counter_misc", "you", "", "", tree.name, "high")]
        if unit.origin != "static":
            continue
        if not _misc_kind(getattr(unit.node, "affected", None)):
            continue
        mods = getattr(unit.node, "modifications", None)
        tags = {tag_of(m) for m in mods} if isinstance(mods, list) else set()
        mode = getattr(unit.node, "mode", None)
        if (tags & _B16_STATIC_KEPT_MODS) or (isinstance(mode, str) and not tags):
            return [Signal("named_counter_misc", "you", "", "", tree.name, "high")]
    return []


def _noncombat_damage_payoff(tree: ConceptTree) -> list[Signal]:
    """noncombat_damage_payoff (§14) — CR 510.1a ("each attacking creature
    and each blocking creature assigns combat damage equal to its power") +
    510.2 set the combat/noncombat boundary; 702.19a (trample "… is dealing
    noncombat damage") is the CR's literal term witness.

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_NONCOMBAT_DAMAGE_RX``
    kept-oracle read is RETIRED): the ``tree_synthesis`` stage's
    ``synth_noncombat_damage_payoff`` node is the lane's SOLE source (no
    competing Tier-1 predicate: the ``Double`` effect's ``target_kind``
    never carries a ``"Damage"`` member, and phase leaves the "deals exactly
    N damage" family an Unknown-mode blob — Ghyrson Starn, known
    event-other flattening, not a new bug): the doublers (Solphim),
    reflectors (Boros Reckoner). A COMBAT damage payoff never fires
    (Cold-Eyed Selkie, pop False). LOGGED widen: v0.9.0's first-class
    ``combat_scope=='NoncombatOnly'`` on the doubler/preventer replacements.
    Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_noncombat_damage_payoff":
            return [Signal("noncombat_damage_payoff", "you", "", "", tree.name, "high")]
    return []


def _nonhuman_attackers(tree: ConceptTree) -> list[Signal]:
    """nonhuman_attackers (§15) — CR 508.3 (attack-declaration triggers) +
    205.3m (Human is a CR creature type): an attacks-trigger unit whose
    watched subject filter carries the first-class Non:Subtype:Human entry
    with controller you (Winota's ``Typed[Creature, {Non: {Subtype:
    Human}}]``, the Batch-12-origin lane). A plain attack trigger without
    the Non-Human subject stays out (Hanweir Garrison, pop False). Scope
    "you", HIGH.
    """
    for unit in tree.units:
        if unit.trigger_event != "attacks":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if "Human" in filter_non_types(vc) and filter_controller(vc) == "You":
            return [Signal("nonhuman_attackers", "you", "", "", tree.name, "high")]
    return []


def _one_punch(tree: ConceptTree) -> list[Signal]:
    """one_punch (§16) — CR 903.10a (21 combat damage from one commander) +
    702.90a (infect: power → poison) / 702.4a-b (double strike: a second
    combat damage step) — the two amplifiers the serve credits.

    Granularity (c) field-numeric membership: a creature with FIXED printed
    power >= 8 AND power >= 2x its mana value connects ONCE for lethal
    (Phyrexian Dreadnought 12/12 mv 1, Death's Shadow 13/13 mv 1); the ratio
    gate excludes big-mana fatties (Emrakul 15/15 mv 15, pop False). Reads
    the tree's typed ``power`` / ``cmc`` / ``has_printed_cost`` — the same
    card-record fields the live producer reads off Scryfall (phase-
    independent by design; NO absence claim made). The ``has_printed_cost``
    gate keeps phase ``NoCost`` transform backs / meld results (mana value
    belongs to the FRONT face, CR 202.3b) out of the numeric gate — the
    live path reads the merged bulk record and never sees them. Live is
    include_membership-gated, fired AFTER has_other_plan and never feeds
    voltron; the crosswalk runs it unconditionally (the b12 precedent).
    Scope "you", **LOW**.
    """
    if (
        tree.is_type("Creature")
        and tree.has_printed_cost
        and tree.power is not None
        and tree.power >= 8
        and tree.power >= 2 * tree.cmc
    ):
        return [
            Signal(
                "one_punch",
                "you",
                "",
                "extreme power-for-cost beater",
                tree.name,
                "low",
            )
        ]
    return []


def _per_target_payoff(tree: ConceptTree) -> list[Signal]:
    """per_target_payoff (§17) — CR 601.2c (targets announced and locked as
    part of casting) + 601.2f (the locked-in total cost): Hinata's YOUR-side
    per-target cost reduction, corpus population exactly 1. Tier-1
    (ADR-0036/0037 fold — the lane-time ``_PER_TARGET_RX`` kept-oracle read
    is RETIRED): the ``tree_synthesis`` stage's ``synth_per_target_payoff``
    node is the lane's SOLE source (no competing Tier-1 predicate: [P49]
    phase parses the reduction but degrades the "for each TARGET"
    discriminator to an ``ObjectCount`` over an EMPTY filter — only the
    node ``description`` string carries it, and a node-scoped description
    regex is the Tier-2 waypoint ADR-0036 rejects). Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_per_target_payoff":
            return [Signal("per_target_payoff", "you", "", "", tree.name, "high")]
    return []


def _power_tap_engine(tree: ConceptTree) -> list[Signal]:
    """power_tap_engine (§18) — CR 602.1 ("Activated abilities have a cost
    and an effect. They are written as '[Cost]: [Effect.]'"): the repeatable
    {T} power-scaling engine.

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_POWER_SCALING_RAW`` /
    ``_POWER_TAP_CONFERRED_RX`` kept-oracle reads are RETIRED):
    :func:`has_structural_power_tap_engine` — an Activated tap-cost unit's
    own effect (or a granted ability's ``GrantAbility.definition`` — the
    conferred/DFC-back form, Predatory Urge, Dragon Throne of Tarkir) scaling
    an ``amount``/``count`` operand off a self ``Power`` ref — PLUS the
    ``tree_synthesis`` stage's ``synth_power_tap_engine`` bucket-B node for
    the other-creature-power / modification-``value`` residual (Kalitas,
    Sword of the Ages, Rabble-Rouser). One-shot power-scaling with NO
    activation cost never fires (Soul's Majesty, pop False). Scope "you",
    HIGH.
    """
    if has_structural_power_tap_engine(tree):
        return [Signal("power_tap_engine", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_power_tap_engine":
            return [Signal("power_tap_engine", "you", "", "", tree.name, "high")]
    return []


def _starting_life_matters(tree: ConceptTree) -> list[Signal]:
    """starting_life_matters (§19) — CR 103.4 ("Each player begins the game
    with a starting life total of 20") / 103.4c (Commander: 40).

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_STARTING_LIFE_REF``
    kept-oracle read is RETIRED): the ``tree_synthesis`` stage's
    ``synth_starting_life_matters`` node — phase carries no StartingLife
    structure (probed, a genuine long-logged representation gap), so this
    bucket-B arm is the lane's SOLE source. Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_starting_life_matters":
            return [Signal("starting_life_matters", "you", "", "", tree.name, "high")]
    return []


def _toughness_combat(tree: ConceptTree) -> list[Signal]:
    """toughness_combat (§20) — CR 510.1a (the assign-combat-damage-equal-
    to-POWER default the Doran statics override; the live "CR 510.1c" cite
    is STALE — 510.1c is lethal-assignment ordering) + 613.4c (layer 7c) +
    604.3 (CDAs).

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_TOUGHNESS_VALUE_MIRROR``
    kept-oracle read is RETIRED):

    (a) STRUCTURAL — :func:`has_structural_toughness_combat` — an
    ``AssignDamageFromToughness`` modification anywhere (Doran; Assault
    Formation) OR a Toughness-typed quantity in a node's ``amount``/``count``
    (a ``Ref{qty: Toughness}`` — Angelic Chorus; a ``Ref{qty:
    Aggregate{property: 'Toughness'}}`` — Loxodon Lifechanter). Deliberately
    NOT a whole-tree Toughness-tag scan: the evolve/comparison predicates
    carry Toughness refs in ``value`` fields (Hulkling — NOT a combat-
    toughness payoff). ``AssignNoCombatDamage`` is NOT a hit (Master of
    Cruelties, pop-verified False).
    (b) the ``tree_synthesis`` stage's ``synth_toughness_combat`` bucket-B
    node — the toughness-as-VALUE residue phase folds to fixed/None operands
    (token P/T, pump-X, mana/cost = toughness), gated against (a). Scope
    "you", HIGH.
    """
    if has_structural_toughness_combat(tree):
        return [Signal("toughness_combat", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_toughness_combat":
            return [Signal("toughness_combat", "you", "", "", tree.name, "high")]
    return []


def _typed_anthem_multi(tree: ConceptTree) -> list[Signal]:
    """typed_anthem_multi (§21) — CR 205.3m (the creature-type list) +
    613.4c (layer 7c P/T anthems) + 105.2a (colors are NOT subtypes — the
    Glistening Deluge exclusion).

    STRUCTURAL: a pump — an :data:`_ANTHEM_PUMP_MODS` modification (fixed
    AND dynamic spellings — Hancock) read via ``iter_mod_sites``, or a mass
    ``PumpAll`` effect (the single-target ``Pump`` is NOT an anthem —
    Grassland Crusader stays out) — over a Creature filter naming >= 2
    subtypes. ``filter_subtypes`` recurses the flat tuple (Brenard's
    Food-or-Golem), the ``AnyOf``-of-subtypes entry (Dead Before Sunrise)
    AND the Or-of-Typed disjunction (Lovisa — v0.9.0 structures what the
    old projection dropped to subject=None; treat Or-of-single-subtype-Typed
    as the AnyOf equivalent), while a color-only disjunction contributes NO
    subtypes (HasColor rides properties, not type_filters — Glistening
    Deluge, pop False) and a keyword GRANT with no pump never enters
    (Paladin Danse, pop False). Tier-1 (ADR-0036/0037 T10-finalize2 fold):
    the two deleted lane-time CASE-SENSITIVE ``_TYPED_ANTHEM_MULTI_RAW``
    raw-fallback reads (for any remaining subject-less pump) are relocated
    verbatim to the bucket-B ``synth_typed_anthem_multi`` node
    (:func:`_arm_typed_anthem_multi`), read below. Scope "you", HIGH.
    """

    def _hits(f: object) -> bool:
        return (
            f is not None
            and "Creature" in filter_core_types(f)
            and len(set(filter_subtypes(f))) >= 2
        )

    for unit in tree.units:
        for sd, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in _ANTHEM_PUMP_MODS:
                continue
            aff = getattr(sd, "affected", None)
            if _hits(aff):
                return [Signal("typed_anthem_multi", "you", "", "", tree.name, "high")]
        for c in unit.effects:
            if tag_of(c.node) != "PumpAll":
                continue
            tgt = getattr(c.node, "target", None)
            if _hits(tgt):
                return [
                    Signal("typed_anthem_multi", "you", "", c.raw, tree.name, "high")
                ]
    for c in tree.iter_concepts():
        if c.concept == "synth_typed_anthem_multi":
            return [Signal("typed_anthem_multi", "you", "", "", tree.name, "high")]
    return []


# ── Stage-2 closeout sweep lanes (the 23 skip-lane dispositions) ──────────────

# Byte-identical inline copies of the live kept-detector rows with NO importable
# name (the b12 _JOHAN_MIRROR precedent — _IR_KEPT_DETECTORS rows are unnamed
# tuple entries). Every mirror runs FLAT over the reminder-stripped kept oracle —
# the exact live application (`pat.search(kept_oracle)`).
# (The 9 FORMAL KEPT-MIRROR rows — attractions_matter / draft_spellbook /
# free_plot / secret_writedown / stickers_matter / tap_down_blockers /
# timing_control / villainous_choice / void_warp_matters — were ADR-0036/0037
# folded to bucket-B ``tree_synthesis`` arms; see ``_sweep_kept_mirrors``
# below and the ``_SWEEP_SYNTH_ROWS`` CR-grounding table in
# ``tree_synthesis.py`` for the per-lane structural-absence re-probe. The 5
# structural+residue UNION lanes below them — legend_rule_off / lessons_matter
# / miracle_grant / snow_matters / targeting_matters — were T9-finalize folded
# the same way; their regex defs now live in ``tree_synthesis.py`` as
# ``_LEGEND_RULE_OFF_SYNTH_RX`` / ``_LESSONS_SYNTH_RX`` /
# ``_MIRACLE_GRANT_SYNTH_RX`` / ``_SNOW_SYNTH_RX`` /
# ``_TARGETING_RESIDUE_SYNTH_RX``.)
_VOTING_MATTERS_RX = re.compile(r"\bfinish(?:ed)? voting\b", re.IGNORECASE)

# The 9 sweep-row synth concept names (:data:`SYNTHESIS_ARM_IDS`, the
# ``tree_synthesis._SWEEP_SYNTH_ROWS`` table) — key + scope only; the CR
# grounding + per-lane structural-absence re-probe lives with the arms.
_SWEEP_SYNTH_KEYS: tuple[tuple[str, str], ...] = (
    ("attractions_matter", "you"),
    ("draft_spellbook", "you"),
    ("free_plot", "you"),
    ("secret_writedown", "you"),
    ("stickers_matter", "you"),
    ("tap_down_blockers", "you"),
    ("timing_control", "any"),
    ("villainous_choice", "you"),
    ("void_warp_matters", "you"),
)

# Sweep Scryfall-keyword field-lookups (checklist #3 survivors — both rows
# MUST read the caller-supplied Scryfall array, not phase keywords):
#   • power-up → powerup_matters (CR 702.193 — a one-time activated ability,
#     cheaper the turn the permanent entered; the mapping row's "Unfinity
#     acorn … not commander-buildable" was FLAT WRONG: 37 commander-legal
#     members). Phase DROPS Power-up from Face.keywords (Extremis Elite
#     probed), so the Scryfall array is the ONLY structured source. The
#     payoff-granter (Wonder Man) carries the keyword too — covered.
#   • sneak → recast_etb (CR 702.190 — Sneak is a real CR keyword now; the
#     row's "no rules meaning" note was STALE; + 118.9 alternative costs).
#     b13 already ports alt_cost_keyword off the same keyword and its
#     comment leaves recast_etb to this sweep. The keyword drops the old
#     `\bsneak\b` over-fires (Cheatyface, Lightfoot Rogue).
#   • casualty / bargain / exploit → sacrifice_outlets (ADR-0038 W4 giants
#     + ADR-0039 W7; CR 702.153a / 702.166a / 702.110a). Casualty/Bargain
#     ARE "As an additional cost to cast this spell, you may sacrifice a
#     <creature/artifact/enchantment/token>", the exact you-sac-cost shape
#     phase's typed tree carries NO node for at all — Light 'Em Up /
#     Xander's Pact's Casualty, High Fae Negotiator / Johann's Stopgap's
#     Bargain. Exploit ("When this creature enters, you may sacrifice a
#     creature") is the SAME shape — mirrors legacy's
#     ``_DIRECT_KEYWORD_SIGNALS["exploit"]`` unconditional keyword-array
#     read; covers the keyword-only tail with no ``exploited`` trigger
#     reachable (Silumgar Scavenger — its Exploit reminder text sits
#     entirely inside stripped parens, so no "sacrifice" word survives
#     ANY oracle-text idiom either; the printed keyword is the ONLY
#     structured source). Native exploiters that DO carry an ``exploited``
#     trigger_event already open this key via the first arm in
#     :func:`_sacrifice_outlets`; this row is additive, never conflicting.
#     The GRANTED form (Anhelo, the Painter's "the first spell you cast
#     each turn has casualty 2" — the keyword lives on the GRANT, not this
#     card's own array) is NOT covered by this row — see the
#     ``casualty_granted_onto_other_spell`` ledgered bridge instead.
#   • devour → sacrifice_outlets (ADR-0039 task #82 grammar sprint; CR
#     702.82a — "As this creature enters, you may sacrifice any number of
#     creatures. This creature enters with N +1/+1 counters ..."). ALWAYS
#     a you-sac ETB cost, unconditionally, for EVERY Devour card — the
#     SAME shape as Casualty/Bargain/Exploit above. The 23 OTHER
#     commander-legal Devour creatures (Mycoloth, Skullmulcher, Bloodspore
#     Thrinax, ...) already carry a typed Sacrifice cost node for their own
#     Devour and already fire this key structurally — this row is additive
#     there (dedupe absorbs it, the Ashad-precedent harmless re-fire) and
#     closes the ONE genuine gap (Thromok the Insatiable, whose own Devour
#     parks as a bare ``Unimplemented`` residue — graduated OFF the
#     ``sac_devour_unimplemented`` ledgered bridge). A CREATED TOKEN's OWN
#     Devour (Dragon Broodmother) is a DIFFERENT card-level keyword array —
#     Dragon Broodmother's own printed keywords never include Devour, so
#     this row does not double-cover :func:`_has_created_token_devour`'s
#     typed ``MirrorVariant`` read.
_SWEEP_KEYWORD_LANES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"power-up"}), "powerup_matters"),
    (frozenset({"sneak"}), "recast_etb"),
    (frozenset({"casualty", "bargain", "exploit", "devour"}), "sacrifice_outlets"),
)


def _keyword_field_signals_sweep(keywords: frozenset[str], name: str) -> list[Signal]:
    """The sweep Scryfall-keyword field-lookups (:data:`_SWEEP_KEYWORD_LANES`).

    Same channel shape as :func:`_keyword_field_signals_b13`: the structured
    keyword array read keeps the lanes immune to name / reminder collisions,
    and phase's keyword drops (Power-up gone from Face.keywords entirely)
    make the caller-supplied array the single usable source.
    """
    low = {k.lower() for k in keywords}
    return [
        Signal(key, "you", "", "", name, "high")
        for kws, key in _SWEEP_KEYWORD_LANES
        if low & kws
    ]


def _sweep_kept_mirrors(tree: ConceptTree) -> list[Signal]:
    """The 9 FORMAL KEPT-MIRROR sweep dispositions (ADR-0036/0037 Stage 5
    fold, Tier-1) — NONE has a competing structural read (re-probed at
    v0.9.0: double tag/mode census + substring scan, the celebration_matters/
    coven_matters sole-source precedent), so each is a plain bucket-B synth
    relocation of the deleted flat mirror, gap-free. See the
    ``_SWEEP_SYNTH_ROWS`` table in ``tree_synthesis.py`` for the per-lane
    CR grounding + structural-absence re-probe. Zero oracle text / regex at
    lane time — reads the synthetic ``synth_<key>`` concept node.
    """
    concepts = {c.concept for c in tree.iter_concepts()}
    return [
        Signal(key, scope, "", "", tree.name, "high")
        for key, scope in _SWEEP_SYNTH_KEYS
        if f"synth_{key}" in concepts
    ]


def _each_mode_player(tree: ConceptTree) -> list[Signal]:
    """each_mode_player (sweep §3) — CR 700.2d (the "same player or object
    may be chosen as the target for each" default these 8 cards override):
    a ``DifferentTargetPlayers`` modal-constraint node anywhere on the card
    (it rides ``execute.modal.constraints`` — Vindictive Lich probed). The
    v0.9.0 holder set is SET-EQUAL to the live 8, so no mirror is needed —
    the "IR does not capture per-mode target legality" skip note was STALE.
    Scope "each" (the live row's scope), HIGH.
    """
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            if tag_of(node) == "DifferentTargetPlayers":
                return [Signal("each_mode_player", "each", "", "", tree.name, "high")]
    return []


def _legend_rule_off(tree: ConceptTree) -> list[Signal]:
    """legend_rule_off (sweep §5) — CR 704.5j: the ``LegendRuleDoesntApply``
    static mode (9 holders, ALL ⊆ live 13 — v0.9.0 now structures the
    BOUNDED forms too: Cadric / Sliver Gravemother / Spider-Verse, so the
    β "bounded is DROPPED entirely" note is STALE), Tier-1 UNION
    (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-identical mirror is
    RETIRED to a bucket-B synth arm) the ``synth_legend_rule_off`` node
    (:func:`_arm_legend_rule_off`) for the 4-card residue phase keeps
    textual (the Yamazaki family, Syr Joshua and Syr Saxon, The Herald of
    Numot — parse-gap candidate, adjudicator-logged). Scope "you", HIGH.
    Read via the SHARED :func:`has_structural_legend_rule_off` predicate
    (GAP-GATE-ALIGNMENT — ADR-0036/0037 Stage 5 #58 hardening; this used
    to re-derive the same static-mode check inline, a drift risk).
    """
    if has_structural_legend_rule_off(tree):
        return [Signal("legend_rule_off", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_legend_rule_off":
            return [Signal("legend_rule_off", "you", "", "", tree.name, "high")]
    return []


def _lessons_matter(tree: ConceptTree) -> list[Signal]:
    """lessons_matter (sweep §6) — CR 701.48 (Learn — "add a Lesson card to
    their hand from outside the game"; Lesson is the subtype the mechanic
    names): a ``{"Subtype": "Lesson"}`` filter anywhere on the card (Uncle
    Iroh's ModifyCost spell_filter probed; 24 holders ALL ⊆ live 31),
    Tier-1 UNION (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-
    identical mirror is RETIRED to a bucket-B synth arm) the
    ``synth_lessons_matter`` node (:func:`_arm_lessons_matter`) for the
    7-card word residue (Twenty Lessons, …). Gate #4 membership: the 21 STX
    Learn DOERS never fire ("Lesson" only in stripped reminder text — both
    arms naturally exclude; the lane must NOT read ``Learn`` nodes), and a
    Lesson CARD whose own oracle never says "lesson" stays out
    (Environmental Sciences). Scope "you", HIGH. Read via the SHARED
    :func:`has_structural_lessons_matter` predicate (GAP-GATE-ALIGNMENT —
    ADR-0036/0037 Stage 5 #58 hardening; this used to re-derive the same
    Lesson-subtype filter walk inline, a drift risk).
    """
    if has_structural_lessons_matter(tree):
        return [Signal("lessons_matter", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_lessons_matter":
            return [Signal("lessons_matter", "you", "", "", tree.name, "high")]
    return []


def _lose_unless_hand(tree: ConceptTree) -> list[Signal]:
    """lose_unless_hand (sweep §7) — CR 104.3e ("An effect may state that a
    player loses the game" — refining the live comment's 104.3a concede
    cite): the cast-from-hand-or-lose drawback, corpus-unique to Phage the
    Untouchable. A self-etb trigger unit (``ChangesZone{destination:
    Battlefield, valid_card: SelfRef}``) carrying a Controller-recipient
    ``lose_game`` effect — the 2-field join has exactly one holder, so the
    ``Not(WasCast{zone: Hand})`` condition (typed at v0.9.0 — the "no
    cast-zone-condition modeling" skip note was STALE) is not re-gated.
    The end-step delayed self-lose (Final Fortune) and the opponent-lose
    payoffs are excluded by the etb event. Scope "you", HIGH.
    """
    for unit in tree.units:
        if unit.trigger_event != "enters":
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) != "SelfRef":
            continue
        for c in unit.effect_concepts("lose_game"):
            if tag_of(getattr(c.node, "target", None)) == "Controller":
                return [Signal("lose_unless_hand", "you", "", "", tree.name, "high")]
    return []


def _miracle_grant(tree: ConceptTree) -> list[Signal]:
    """miracle_grant (sweep §8) — CR 702.94 (Miracle): the ``AddKeyword{
    Miracle}`` modification walk (the b13 _B13_MOD_GRANT_LANES precedent —
    Lorehold, the Historian; Molecule Man; both ⊆ live 4), Tier-1 UNION
    (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-identical mirror is
    RETIRED to a bucket-B synth arm) the ``synth_miracle_grant`` node
    (:func:`_arm_miracle_grant`) for the folded grants (Aminatou, Veil
    Piercer; Topdeck the Halls — parse-gap candidate, adjudicator-logged).
    Gate #4 membership: the 18 intrinsic ``Miracle {cost}`` bearers
    (Bonfire of the Damned, …) never fire — the AddKeyword walk reads
    GRANTS, not own keywords, and a keyword line doesn't match the grant
    phrasing. Scope "you", HIGH. Read via the SHARED
    :func:`has_structural_miracle_grant` predicate (GAP-GATE-ALIGNMENT —
    ADR-0036/0037 Stage 5 #58 hardening; this used to re-derive the same
    ``AddKeyword{Miracle}`` walk inline, a drift risk).
    """
    if has_structural_miracle_grant(tree):
        return [Signal("miracle_grant", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_miracle_grant":
            return [Signal("miracle_grant", "you", "", "", tree.name, "high")]
    return []


def _recast_etb_bleed(tree: ConceptTree) -> list[Signal]:
    """recast_etb SERVE arm (sweep §10, arm b) — the aggressive-ETB payoff a
    Sneak engine recasts (CR 702.190 / 118.9): an enters-trigger unit whose
    sibling effects include a discard / lose_life / sacrifice concept AND
    whose trigger text names "each opponent" (Burglar Rat "each opponent
    discards", Skirmish Rhino "each opponent loses 2 life"). Phase tags the
    controller scope, not the recipient (Burglar Rat's Discard decorates
    scope 'you' — probed), so the opponent bleed has no competing Tier-1
    predicate — ADR-0036/0037 Stage 5 fold: the deleted lane-time
    ``_RECAST_UNIMPL_BLEED_RX`` scan (unit description + modal
    ``mode_descriptions`` + a for-each ``Unimplemented`` node's own raw +
    a GRANT-flattened bleed anchor) is relocated verbatim to the bucket-B
    ``synth_recast_etb`` node (:func:`_arm_recast_etb_bleed`), read below —
    zero oracle text/regex at lane time. The unit join (etb + bleed in the
    SAME ability) is the lane's anti-goodstuff point — a value etb (Wood
    Elves) never fires. The Sneak keyword arm (a) rides
    :data:`_SWEEP_KEYWORD_LANES`. Scope "you", HIGH.
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_recast_etb":
            return [Signal("recast_etb", "you", "", "", tree.name, "high")]
    return []


def _seek_matters(tree: ConceptTree) -> list[Signal]:
    """seek_matters (sweep §12) — DD3 (Seek — "the game randomly chooses a
    card matching given criteria from your library"): the first-class
    ``Seek`` effect node (120 holders at v0.9.0), riding the new sweep
    ``EFFECT_CONCEPTS`` row. The "phase has a Seek EffectKind but it is
    unmapped in project.py" skip note was STALE (project.py:506 maps it and
    the live lane fires through it); Arena-only is a LEGALITY property, not
    a skip — deck-forge serves historic_brawl (bl=98). A library SEARCH is
    a different node family (``SearchLibrary`` → tutor) — no gate needed.
    Scope "you", HIGH.
    """
    hits = tree.effect_concepts("seek")
    if hits:
        return [Signal("seek_matters", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _snow_matters(tree: ConceptTree) -> list[Signal]:
    """snow_matters (sweep §13) — CR 205.4 (Snow is a real supertype — the
    live comment itself calls the old skip wrong): two typed reads, Tier-1
    UNION (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-identical
    ``\\bsnow\\b`` mirror is RETIRED to a bucket-B synth arm) the
    ``synth_snow_matters`` node (:func:`_arm_snow_matters`, the producer —
    snow-mana payoffs and prose references phase leaves textual):

    * a ``{HasSupertype: Snow}`` filter property on any subject filter
      (52 holders, 48 ⊆ live; the 3 outliers are documented DFC name-join
      artifacts — the b13 island_matters precedent, NOT chased);
    * a ``YouControlSnowPermanentCountAtLeast`` condition (Heidar /
      Rimewind Cryomancer / Rimewind Taskmage).

    Gate #4 membership: a Snow-SUPERTYPE card itself never fires off its
    type line (parity: live reads oracle only — NO card_supertypes read;
    Boreal Druid pinned). Scope "you", HIGH. Read via the SHARED
    :func:`has_structural_snow_matters` predicate (GAP-GATE-ALIGNMENT —
    ADR-0036/0037 Stage 5 #58 hardening; this used to re-derive the same
    two-arm walk inline, a drift risk).
    """
    if has_structural_snow_matters(tree):
        return [Signal("snow_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_snow_matters":
            return [Signal("snow_matters", "you", "", "", tree.name, "high")]
    return []


def _stickers_structural(tree: ConceptTree) -> list[Signal]:
    """stickers_matter typed corroboration (sweep §14) — CR 123: the
    ``PutSticker`` effect node (43 holders, ALL ⊆ the mirror's live 107 —
    phase-only == 0, probed), included per the fidelity-direction memory
    (a structural read the substrate already carries adds zero members but
    grounds the lane in the typed tree). The mirror in
    :func:`_sweep_kept_mirrors` is the producer; ``add()`` dedups.
    """
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) == "PutSticker":
                return [Signal("stickers_matter", "you", "", "", tree.name, "high")]
    return []


def _sweep_watched_owner_scope(trig: TypedMirrorNode) -> str:
    """The creature-owner scope of a ``BecomesTarget`` trigger — mirrors the
    live projection's ``_trigger_scope`` over the TYPED node: ``valid_card``
    SelfRef → you; a Typed controller You/Opponent → you/opp; otherwise fall
    through to ``valid_target``'s controller; default "any". CR 702.21a.
    """
    for fname in ("valid_card", "valid_target"):
        sub = getattr(trig, fname, None)
        if not isinstance(sub, TypedMirrorNode):
            continue
        if fname == "valid_card" and tag_of(sub) == "SelfRef":
            return "you"
        c = getattr(sub, "controller", None)
        if isinstance(c, str):
            cl = c.lower()
            if cl == "you":
                return "you"
            if "opponent" in cl:
                return "opp"
    return "any"


def _sweep_source_is_opp(trig: TypedMirrorNode) -> bool:
    """Whether a ``BecomesTarget`` trigger's targeting SOURCE is
    opponent-restricted — mirrors the live ``_becomes_target_src_zones``
    "src:opp" derivation: collect every ``controller`` string under
    ``valid_source`` (Shapers' Sanctuary / Battle Mammoth carry
    ``Or[And[StackSpell, Typed{controller: Opponent}], StackAbility]`` —
    probed); all-Opponent → redirect. Tier-1 (ADR-0036/0037 T10-finalize2
    fold): PURE typed read only — a bare no-controller source (no
    structural evidence either way) returns False here; the deleted
    lane-time ``_BECOMES_TARGET_SRC_OPP`` text-fallback (the Reality
    Smasher / Swarm Shambler / Tectonic Giant parse gap) is relocated
    verbatim to the bucket-B ``synth_becomes_target_src_opp`` node
    (:func:`_arm_becomes_target_src_opp`), read at the call site. CR
    702.21a / 108.3.
    """
    ctrls: set[str] = set()
    vs = getattr(trig, "valid_source", None)
    if isinstance(vs, TypedMirrorNode):
        for node in iter_typed_nodes(vs):
            c = getattr(node, "controller", None)
            if isinstance(c, str) and c:
                ctrls.add(re.sub(r"[^a-z0-9]", "", c.lower()))
    return bool(ctrls) and ctrls <= {"opponent"}


def _becomes_target_lanes(tree: ConceptTree) -> list[Signal]:
    """The BECOMES-TARGET payoff split (sweep §16/§17/§18) — live-STRUCTURAL
    since SIDECAR v40; the "no BecomesTarget projection; single-card Monk
    Gyatso lane" skip notes were doubly STALE (v0.9.0 carries 122
    ``BecomesTarget`` trigger modes; crosswalk.py already maps the event).
    CR 702.21a (Ward — the CR's own becomes-target-punish template) +
    207.2c (heroic / valiant are ability words — NB the live comments'
    "CR 702.83" heroic cite is a miscite; 207.2c is carried here) + 603.2.

    Three lanes off each native trigger unit's OWN fields (scope/direction
    gate — never zone-tag re-derivation):

    * ``targeting_matters`` "any" — EVERY becomes_target trigger (the broad
      lane; Willbreaker's opponent-creature subject counts too), Tier-1
      UNION (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-identical
      residue mirror is RETIRED to a bucket-B synth arm) the
      ``synth_targeting_matters`` node (:func:`_arm_targeting_matters`) for
      the granted/quoted/player-targeted forms phase emits no native
      trigger for (Kira / Opaline Sliver / Dormant Gomazoa / heroic).
      LOGGED widen (closeout (c) #21): a GrantTrigger{BecomesTarget}
      deep-grant read — v0.9.0 structures Kira's grant, but
      PARITY-BEFORE-VETO keeps the synth arm the producer.
    * ``target_own_payoff`` "you" — the creature is yours/any
      (:func:`_sweep_watched_owner_scope` ∈ {you, any} — Willbreaker / Shay
      Cormac's opp-subject excluded) and the source is NOT
      opponent-restricted (heroic/valiant + "you may" reactions).
    * ``target_redirect`` "you" — same owner gate, opponent-restricted
      source (:func:`_sweep_source_is_opp` — Shapers' Sanctuary, Battle
      Mammoth). The v40 double-fire fix holds: Shapers' fires redirect,
      NEVER own-payoff. Tier-1 (ADR-0036/0037 T10-finalize2 fold):
      ``_sweep_source_is_opp`` is now PURE typed (no text fallback); the
      deleted lane-time text residue (Reality Smasher / Swarm Shambler /
      Tectonic Giant's no-controller source) is relocated verbatim to the
      bucket-B ``synth_becomes_target_src_opp`` node
      (:func:`_arm_becomes_target_src_opp`), read here as a per-card OR
      (the residue's pop is a strict 1-trigger-per-card census).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def add(key: str, scope: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", "", tree.name, "high"))

    src_opp_residue = any(
        c.concept == "synth_becomes_target_src_opp" for c in tree.iter_concepts()
    )
    for unit in tree.units:
        if unit.trigger_event != "becomes_target":
            continue
        add("targeting_matters", "any")
        owner = _sweep_watched_owner_scope(unit.node)
        if owner in ("you", "any"):
            if _sweep_source_is_opp(unit.node) or src_opp_residue:
                add("target_redirect", "you")
            else:
                add("target_own_payoff", "you")
    if "targeting_matters" not in seen:
        for c in tree.iter_concepts():
            if c.concept == "synth_targeting_matters":
                add("targeting_matters", "any")
                break
    return out


def _theft_protection(tree: ConceptTree) -> list[Signal]:
    """theft_protection (sweep §19) — CR 702.21a (Ward — the intrinsic
    counter-when-targeted form the CR itself templates): ``BecomesTarget``
    + ``OncePerTurn`` constraint + a ``Counter`` execute — native trigger
    units (Glyph Keeper, Jetting Glasskite, Shimmering Glasskite) AND the
    ``GrantTrigger`` modification walk (Kira, Great Glass-Spinner's quoted
    grant). Census-probed EXACTLY the live 4; the Counter-exec gate cuts
    the 19-card OncePerTurn+BecomesTarget family (Heartfire Hero
    exec=PutCounter, Loki exec=Draw — pinned negatives). The "once-per-turn
    gate is NOT structured" skip note was STALE
    (:func:`trigger_constraint_tag` reads it today); no mirror needed
    (set-equal). Scope "you", HIGH.
    """
    for unit in tree.units:
        if (
            unit.trigger_event == "becomes_target"
            and trigger_constraint_tag(unit.node) == "OncePerTurn"
            and any(tag_of(c.node) == "Counter" for c in unit.effects)
        ):
            return [Signal("theft_protection", "you", "", "", tree.name, "high")]
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "GrantTrigger":
                continue
            trig = getattr(mod, "trigger", None)
            if not isinstance(trig, TypedMirrorNode):
                continue
            if (
                getattr(trig, "mode", None) == "BecomesTarget"
                and trigger_constraint_tag(trig) == "OncePerTurn"
                and any(
                    tag_of(n) == "Counter"
                    for n in iter_typed_nodes(getattr(trig, "execute", None))
                )
            ):
                return [Signal("theft_protection", "you", "", "", tree.name, "high")]
    return []


def _voting_matters(tree: ConceptTree) -> list[Signal]:
    """voting_matters (sweep §23) — CR 701.38 (Vote — fixes the mapping
    row's stale 701.32 cite): the ``Vote`` TRIGGER mode ("Whenever players
    finish voting" — Erestor probed verbatim), readable TODAY as
    ``trigger_event == "vote"`` via ``_trigger_event``'s ``mode.lower()``
    fall-through. Census-probed EXACTLY the live 3 (Erestor, Grudge Keeper,
    Model of Unity) — the ADR-0034 split's mirror residue retires into a
    structural read. The 25 ``Vote`` EFFECT nodes (Expropriate, Magister of
    Worth, …) stay :func:`_voting_makers` — the trigger-vs-effect split
    keeps the maker/matters partition exact (gate #4 satisfied
    structurally). Scope "each" (every player votes), HIGH.
    """
    for unit in tree.units:
        if unit.trigger_event == "vote":
            return [Signal("voting_matters", "each", "", "", tree.name, "high")]
    return []


def _named_synergy(tree: ConceptTree) -> list[Signal]:
    """named_synergy (ADR-0039 W8) — CR 201.4 / 201.5: a card whose ability
    references a specific permanent by name, self or other. Entirely
    served by the :data:`named_synergy_overloaded_named_node
    <mtg_utils._deck_forge.bridge_ledger.BRIDGES>` bridge — see that
    row's module comment for why the typed ``Named`` node this key's
    idiom carries is too overloaded (partner pairs, copy-limit swarms,
    named-card tutoring, planeswalker-uncoupled callbacks) to read
    directly yet. Scope "you", HIGH (the legacy producer's own scope/
    conf — it never fed has_other_plan).
    """
    if bridge_fires("named_synergy_overloaded_named_node", tree):
        return [Signal("named_synergy", "you", "", "", tree.name, "high")]
    return []


LANES = (
    _evasion_self,
    _cant_block_grant,
    _global_ability_grant,
    _opponent_counter_grant,
    _conditional_self_protection,
    _sacrifice_protection,
    _life_payment_insurance,
    _speed_doer,
    _exhaust_matters,
    _saddle_matters_lane,
    _suspect_matters_lane,
    _void_warp_makers,
    _ability_copy,
    _ability_strip_payoff,
    _arcane_matters,
    _celebration_matters,
    _cmdzone_ability,
    _exalted_textual,
    _flip_self,
    _free_creature_payoff,
    _free_spell_storm,
    _island_makers,
    _keyword_soup_makers,
    _meld_pair,
    _named_counter_misc,
    _noncombat_damage_payoff,
    _nonhuman_attackers,
    _one_punch,
    _per_target_payoff,
    _power_tap_engine,
    _starting_life_matters,
    _toughness_combat,
    _typed_anthem_multi,
    # Stage-2 closeout sweep (the 23 skip-lane dispositions):
    _sweep_kept_mirrors,
    _each_mode_player,
    _legend_rule_off,
    _lessons_matter,
    _lose_unless_hand,
    _miracle_grant,
    _recast_etb_bleed,
    _seek_matters,
    _snow_matters,
    _stickers_structural,
    _becomes_target_lanes,
    _theft_protection,
    _voting_matters,
)


# ADR-0039 W8 (KEPT-twelve wave):
LANES_TAIL = (_named_synergy,)
