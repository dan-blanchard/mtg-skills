"""Stax/control and targeting/restriction bucket-B synthesis arms.

Part of the :mod:`mtg_utils._card_ir.tree_synthesis` package; see that
package's ``__init__.py`` for the stage-level overview and the full
re-exported public surface.
"""

from __future__ import annotations

import dataclasses
import re

from mtg_utils._card_ir.crosswalk import (
    ConceptNode,
    ConceptTree,
    change_zone_dirs,
    counter_kind,
    counter_kind_any,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_predicates,
    iter_condition_sites,
    iter_static_defs,
    iter_typed_nodes,
    modify_cost_mode,
    replacement_event_tag,
    replacement_shield_kind,
    settap_state,
    static_mode_field,
    static_mode_tag,
    tag_of,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.supplement import (
    _EACH_PLAYER_P,
    _TAP_OPP_CONTROL_P,
)
from mtg_utils._card_ir.text_idioms import (
    _CANT_BLOCK_GRANT_QUOTE,
    _CANT_BLOCK_MODAL_BULLET,
    _CANT_BLOCK_REF,
    _CANT_BLOCK_TAX,
)
from mtg_utils._card_ir.tree_synthesis._shared import (
    _REMINDER,
    _synthetic_concept,
)
from mtg_utils._deck_forge._sweep_detectors import VOID_WARP_MAKERS_REGEX
from mtg_utils._deck_forge.signal_base import clauses
from mtg_utils._deck_forge.text_reads import (
    _COLOR_HOSER_RE,
    _OPP_COUNTER_BENEFICIAL,
    _STAX_TAXES_RESIDUE_RE,
    _SYMMETRIC_STAX_RESIDUE_RE,
    _restriction_pacifies_single_creature,
)

# ── stax_taxes / symmetric_stax structural census (ADR-0036 fold) ─────────────
# CR 101.2/604.1. Moved here VERBATIM from the ``_stax_lanes`` lane (minus the
# residue-mirror tail below) so the lane AND this stage's two synth gap gates
# read the SAME predicate -- GAP-GATE-ALIGNMENT, no drift. Pacify veto
# (EnchantedBy/EquippedBy) is LOAD-BEARING: a single-target Aura/Equipment
# lock (Pacifism, Arrest) opens NEITHER lane.
_PACIFY_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})
_STAX_SIMPLE_RESTRICTIONS: frozenset[str] = frozenset(
    {
        "CantAttack",
        "CantBlock",
        "CantAttackOrBlock",
        "CantUntap",
        "CantGainLife",
        "MustAttack",
        "CantPlayLand",
        "MustBlock",
        "BlockRestriction",
    }
)
_STAX_LOCK_MODES: frozenset[str] = frozenset(
    {
        "CantBeActivated",
        "CantBeCast",
        "CantCastDuring",
        "CantActivateDuring",
        "PerTurnCastLimit",
        "CantCastFrom",
    }
)
# A filter's controller reads "Opponent" for "an opponent controls" but
# "TargetOpponent" for "target opponent controls" (Exhaustion, Icebreaker
# Kraken) -- both name the same opponent-directed lock, CR 604.1.
_OPPONENT_CTRL: frozenset[str] = frozenset({"Opponent", "TargetOpponent"})
# A SelfRef combat restriction ("This creature can't attack/block ...") is
# normally a drawback, never a lock on opponents. But when its own CONDITION
# clause names a THIRD PARTY's zone ("...unless an opponent has eight or
# more cards in THEIR graveyard" -- Relic Golem; "...unless defending player
# has seven or more cards in THEIR graveyard" -- Vantress Gargoyle) it is a
# "punisher" whose usefulness is gated on an opponent's resource. Mirrors
# old-IR's own broad third-party-possessive scope repair
# (supplement._BROAD_THIRD_PARTY, applied post-structural-projection to any
# unscoped restriction) byte-for-byte so the crosswalk draws the same line.
_THIRD_PARTY_POSSESSIVE_RE = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)
# ADR-0038 AddRestriction (a one-shot ProhibitActivity effect -- Silence's
# "your opponents can't cast spells this turn", Permission Denied, Mandate
# of Peace, Sphinx's Decree, Lavinia's ETB-scoped granted lock, Ranger-
# Captain of Eos's sacrifice ability) carries WHOM it hobbles on
# ``restriction.affected_players``, a DIFFERENT shape than the continuous
# static census above (no ``affected``/``modifications`` pair, so
# :func:`iter_static_defs` never yields it) -- mirrors old-IR's
# ``project._add_restriction_scope``. CR 604.1 / 720.
_ADD_RESTRICTION_STAX: frozenset[str] = frozenset(
    {"OpponentsOfSourceController", "TargetedPlayer"}
)


def _stax_site_raw(sdef: object) -> str:
    """A static-def site's grounding clause (its ``description``, else "")."""
    desc = getattr(sdef, "description", None)
    return desc if isinstance(desc, str) else ""


def _stax_structural_walk(tree: ConceptTree) -> tuple[bool, bool, str, str]:
    """The ENTIRE stax_taxes / symmetric_stax Tier-1 structural census.

    Returns ``(stax_fired, sym_fired, stax_raw, sym_raw)``. Scope from each
    static's OWN who/affected node:

    * **plain restrictions** (CantAttack / CantBlock / CantAttackOrBlock /
      CantUntap / CantGainLife / MustAttack / CantPlayLand / MustBlock /
      BlockRestriction): affected controller Opponent/TargetPlayer -> stax
      (Propaganda, Fumiko); unscoped board filter -> symmetric (Warmonger
      Hellkite, Meekstone, Bedlam, An-Zerrin Ruins). A SelfRef affected (a
      drawback) or an EnchantedBy/EquippedBy-predicated subject (Pacifism,
      Arrest, the stun-Auras) opens NEITHER lane.
    * **cost taxes** (ModifyCost{Raise}): affected Opponent -> stax (Aura of
      Silence); a You/SelfRef direction is a self-cost quirk (skip); an
      unscoped tax is symmetric AND co-fires stax (Sphere of Resistance).
    * **cast/activation locks** (CantBeActivated / CantBeCast /
      CantCastDuring / CantActivateDuring / PerTurnCastLimit / CantCastFrom):
      ``who`` Opponents -> stax (Alhammarret, A-Teferi); ``who`` Controller
      -> skip (Colfenor's Plans); else BOTH lanes (Stony Silence, Arcane
      Laboratory, Karn GC, Curse of Exhaustion). The Arrest-shape lock
      (EnchantedBy source_filter) is pacified out.
    * **library-search locks** (CantSearchLibrary): the mode's OWN ``cause``
      field routes direction -- Opponents -> stax (Stranglehold, Ashiok
      Dream Render); AllPlayers -> symmetric only (Mindlock Orb).
    * **attack ceilings** (MaxAttackersEachCombat): defender Controller ->
      stax (Crawlspace); else symmetric (Dueling Grounds).
    * **step skips** (SkipStep): affected Player -> symmetric (Stasis).
    * **trigger suppression** (SuppressTriggers): symmetric (Hushbringer /
      Torpor Orb).
    * **hand-size reducers** (MaximumHandSize, affected Opponent): stax
      co-fire (Gnat Miser, Jin-Gitaxias).
    * **opponents-enter-tapped** (a Moved->Battlefield replacement whose
      SetTapState{Tap} valid_card is NOT SelfRef): controller Opponent ->
      stax (Authority of the Consuls, Kismet); unscoped -> symmetric (Root
      Maze). A SelfRef valid_card ("this land enters tapped") is membership.
    * **one-shot cast/activate locks** (a role=effect ``AddRestriction``
      whose ``restriction`` is ``ProhibitActivity`` -- Silence, Permission
      Denied, Mandate of Peace, Sphinx's Decree): ``affected_players``
      OpponentsOfSourceController/TargetedPlayer -> stax; AllPlayers ->
      symmetric.
    * **punisher combat restrictions** (a SelfRef CantAttack/CantBlock/
      CantAttackOrBlock whose own clause names a third party's zone --
      Relic Golem, Vantress Gargoyle): stax (the ADR-0038
      third-party-possessive mirror).

    An untap BLESSING (Seedborn Muse's UntapsDuringEachOtherPlayersUntapStep)
    is not in any census set.
    """
    stax_fired = False
    sym_fired = False
    stax_raw = ""
    sym_raw = ""

    def stax(raw: str) -> None:
        nonlocal stax_fired, stax_raw
        if not stax_fired:
            stax_fired = True
            stax_raw = raw

    def sym(raw: str) -> None:
        nonlocal sym_fired, sym_raw
        if not sym_fired:
            sym_fired = True
            sym_raw = raw

    # The census walks EVERY static def reachable from a unit (a top-level
    # continuous ability AND the one-shot GenericEffect-nested defs a spell
    # confers -- Falter's "creatures without flying can't block this turn" is
    # a live symmetric member). A ParentTarget affected is a single-target
    # combat trick / pacify (Sleep's rider, Basandra's {R} force) -- skipped.
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) != "AddRestriction":
                continue
            restr = getattr(c.node, "restriction", None)
            if tag_of(restr) != "ProhibitActivity":
                continue
            ap = tag_of(getattr(restr, "affected_players", None))
            if ap in _ADD_RESTRICTION_STAX:
                stax(c.raw)
            elif ap == "AllPlayers":
                sym(c.raw)
        defs = iter_static_defs(unit.node) if unit.origin != "replacement" else ()
        for node in defs:
            mt = static_mode_tag(node)
            affected = getattr(node, "affected", None)
            atag = tag_of(affected)
            ctrl = filter_controller(affected)
            raw = _stax_site_raw(node)
            if atag in ("SelfRef", "ParentTarget"):
                if (
                    atag == "SelfRef"
                    and mt in _STAX_SIMPLE_RESTRICTIONS
                    and _THIRD_PARTY_POSSESSIVE_RE.search(raw)
                ):
                    stax(raw)
                continue  # a drawback / single-target trick, never a lock
            if mt in _STAX_SIMPLE_RESTRICTIONS:
                if set(filter_predicates(affected)) & _PACIFY_PREDS:
                    continue
                if ctrl in _OPPONENT_CTRL:
                    stax(raw)
                elif ctrl == "TargetPlayer":
                    # live scopes the directed one-shot board lock (Mana
                    # Vapors, Aggravate) "each", not "opponents" -- parity.
                    sym(raw)
                elif ctrl is None and atag in ("Typed", "Or", "And"):
                    sym(raw)
            elif mt == "ModifyCost" and modify_cost_mode(node) == "Raise":
                if atag == "SelfRef" or ctrl == "You":
                    continue
                if ctrl in _OPPONENT_CTRL:
                    stax(raw)
                else:
                    sym(raw)
                    stax(raw)
            elif (
                mt == "ReduceAbilityCost"
                and static_mode_field(node, "mode") == "Raise"
                and ctrl in _OPPONENT_CTRL
            ):
                # A keyword-scoped cost tax explicitly naming an opponent
                # (Eidolon of Obstruction's "loyalty abilities of
                # planeswalkers YOUR OPPONENTS control cost {1} more") --
                # the ModifyCost{Raise} sibling for a NAMED-ability-kind
                # cost raise. Unlike ModifyCost{Raise}, an unscoped one
                # (Suppression Field's "activated abilities cost {2}
                # more", Skyseer's Chariot's chosen-name tax) does NOT
                # co-fire here -- measured cw_only over-fires, and a
                # single-target Aura tax (Oppressive Rays' "activated
                # abilities of ENCHANTED creature cost {3} more") has no
                # controller tag at all, so the same narrow gate excludes
                # it without a separate pacify check. CR 601.2f.
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
            elif mt == "CantSearchLibrary":
                cause = static_mode_field(node, "cause")
                if cause == "Opponents":
                    stax(raw)
                elif cause == "AllPlayers":
                    sym(raw)
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

    return stax_fired, sym_fired, stax_raw, sym_raw


def has_structural_stax_taxes(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``stax_taxes`` structural census fires (shared by
    the ``_stax_lanes`` lane and the ``synth_stax_taxes`` gap gate)."""
    return _stax_structural_walk(tree)[0]


def has_structural_symmetric_stax(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``symmetric_stax`` structural census fires (shared
    by the ``_stax_lanes`` lane and the ``synth_symmetric_stax`` gap gate)."""
    return _stax_structural_walk(tree)[1]


# ── arm: stax_taxes / symmetric_stax bucket-B (ADR-0036/0037 fold) ───────────
# CR 101.2/604.1. The unstructurable residue tail phase drops WHOLLY (a
# player-lock idiom Unimplemented -- Winter Orb's "players can't untap more
# than one land", Static Orb; a split/aftermath dropped face -- Failure //
# Comply's "your opponents can't cast spells with the chosen name") or
# structures with no typed field the census reads (Archfiend of Despair /
# Platinum Angel's "opponents can't gain life" / "can't win the game",
# Stranglehold's opponent search-lock on a body phase drops wholly).
# Relocates the EXACT deleted _STAX_TAXES_RESIDUE_RE / _SYMMETRIC_STAX_
# RESIDUE_RE per-clause scan (with the SAME pacify veto) to projection time,
# gap-gated against has_structural_stax_taxes / has_structural_symmetric_stax
# -- SYNTH-EXCLUSION-PARITY: every over-fire exclusion the regex itself
# encodes (the `(?<!target )` single-target guard, the `(?! cast)` defer to
# a structurally-caught CantBeCast/CantCastDuring cast-lock, the pacify veto,
# the dropped `creatures your opponents control` / `doesn't/don't/does not
# untap during` over-fire branches) rides along unchanged -- no new code, no
# new drift, just relocated to gap-gated projection time.
def _stax_residue_hits(tree: ConceptTree) -> tuple[bool, bool]:
    """``(stax_residue, sym_residue)`` -- the deleted per-clause regex scan,
    reminder-stripped, pacify-vetoed. One shared scan for both synth arms."""
    stax_r = False
    sym_r = False
    for cl in clauses(_REMINDER.sub(" ", tree.oracle or "")):
        if _restriction_pacifies_single_creature(cl):
            continue
        if _STAX_TAXES_RESIDUE_RE.search(cl):
            stax_r = True
        if _SYMMETRIC_STAX_RESIDUE_RE.search(cl):
            sym_r = True
    return stax_r, sym_r


def _arm_stax_taxes(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``stax_taxes`` node for the description-only bucket-B
    tail phase's static census doesn't reach at all -- gap-gated by
    ``has_structural_stax_taxes`` (never double-counts a card Tier-1
    already reads)."""
    if has_structural_stax_taxes(tree):
        return None
    if not _stax_residue_hits(tree)[0]:
        return None
    return _synthetic_concept(
        arm_id="stax_taxes",
        concept="synth_stax_taxes",
        scope="opponents",
        subject=(),
        desc="bucket-B stax tax (phase emits no typed lock/tax node)",
    )


def _arm_symmetric_stax(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``symmetric_stax`` node for the description-only
    bucket-B tail phase's static census doesn't reach at all -- gap-gated
    by ``has_structural_symmetric_stax`` (never double-counts a card
    Tier-1 already reads)."""
    if has_structural_symmetric_stax(tree):
        return None
    if not _stax_residue_hits(tree)[1]:
        return None
    return _synthetic_concept(
        arm_id="symmetric_stax",
        concept="synth_symmetric_stax",
        scope="each",
        subject=(),
        desc="bucket-B symmetric stax (phase emits no typed lock node)",
    )


# ── superfriends_matters structural reads (ADR-0036/0037 fold) ───────────────
# CR 306.5: caring about the planeswalker TYPE/GROUP (anthems, loyalty-counter
# payoffs, activate-loyalty engines, PW-ability copiers) — not merely BEING a
# planeswalker, and not a removal spell's target filter happening to name one
# (Hero's Downfall never fires; a ``TargetMatchesFilter`` condition on the
# spell's own target — Chandra's Defeat — is removal, skipped subtree). Shared
# by the ``_superfriends_matters`` lane (its entire Tier-1 structural read) and
# this stage's synth gap gate — one source, no drift.
_PW_ATTACK_RECIPIENTS: frozenset[str] = frozenset(
    {"PlayerOrPlaneswalker", "OwnerOrPlaneswalker", "Planeswalker"}
)
_SUPERFRIENDS_COUNTER_EFFECTS: frozenset[str] = frozenset(
    {"place_counter", "remove_counter", "move_counters", "multiply_counter"}
)


def _superfriends_typed_ref(node: object, depth: int = 0) -> bool:
    """A Planeswalker group-reference at ANY site reachable from ``node``.

    A ``Typed`` filter naming Planeswalker with a non-Opponent controller, OR
    the typed ``YouControlNamedPlaneswalker`` gate (Companion of the Trials).
    Three exclusions ride along at every depth: a ``TargetMatchesFilter``
    condition (a removal spell's own target — Chandra's Defeat), an
    ``UnlessPay``/``AttackTarget`` node whose ``defended``/``attacked`` +
    ``controller`` fields resolve the "can't attack you or planeswalkers you
    control" tax/restriction family (Archangel of Tithes, Mangara), and a
    ``WheneverEvent`` — vetoed UNLESS its wrapped trigger carries the SAME
    "attacks you or a planeswalker you control" recipient shape (Tamiyo Meets
    the Story Circle's delayed trigger), so the generic damage-recipient
    event-plumbing family (Hunter's Insight — "player or planeswalker", no
    controller gate) stays excluded.
    """
    if depth > 24:
        return False
    if isinstance(node, MirrorVariant):
        return _superfriends_typed_ref(node.inner, depth + 1)
    if isinstance(node, list):
        return any(_superfriends_typed_ref(e, depth + 1) for e in node)
    if not isinstance(node, TypedMirrorNode):
        return False
    t = tag_of(node)
    if t == "TargetMatchesFilter":
        return False
    if t == "WheneverEvent":
        trig = getattr(node, "trigger", None)
        if not isinstance(trig, TypedMirrorNode):
            return False
        atf = getattr(trig, "attack_target_filter", None)
        return atf in _PW_ATTACK_RECIPIENTS and trigger_scope(trig) == "you"
    if t == "UnlessPay" and getattr(node, "defended", None) in _PW_ATTACK_RECIPIENTS:
        return True
    if t == "AttackTarget" and (
        getattr(node, "attacked", None) in _PW_ATTACK_RECIPIENTS
        and getattr(node, "controller", None) != "Opponent"
    ):
        return True
    if t == "YouControlNamedPlaneswalker":
        return True
    if (
        t == "Typed"
        and "Planeswalker" in filter_core_types(node)
        and filter_controller(node) != "Opponent"
    ):
        return True
    return any(
        _superfriends_typed_ref(getattr(node, f.name), depth + 1)
        for f in dataclasses.fields(node)
    )


def _superfriends_count_operand_ref(effect_or_static: ConceptNode) -> bool:
    """A Planeswalker group-reference in a dynamic scaling operand.

    ``amount``/``count``/``value`` (life gain, damage, mana — Ajani, Strength
    of the Pride) or ``cost_reduction`` (Mobilized District, Tomik's
    "Affinity for planeswalkers") holding a ``Ref`` over an ``ObjectCount``
    whose filter names Planeswalker.
    """
    node = effect_or_static.node
    for fname in ("amount", "count", "value", "cost_reduction"):
        q = getattr(node, fname, MISSING)
        if not isinstance(q, TypedMirrorNode) or tag_of(q) != "Ref":
            continue
        qty = getattr(q, "qty", None)
        if tag_of(qty) == "ObjectCount":
            filt = getattr(qty, "filter", None)
            if filt is not None and _superfriends_typed_ref(filt):
                return True
    return False


def has_structural_superfriends(tree: ConceptTree) -> bool:
    """Whether the Tier-1 ``superfriends_matters`` structural union fires.

    Shared by the ``_superfriends_matters`` lane and this stage's synth gap
    gate — one source, no drift (CR 306.5):

    * a CONDITION-site Planeswalker group-reference (:func:`_superfriends_
      typed_ref` over :func:`iter_condition_sites` — Historian of Zhalfir /
      Arisen Gorgon / Companion of the Trials).
    * an ATTACK-RECIPIENT trigger watching YOUR side (Blood Reckoning,
      Isperia — a unit's own ``attack_target_filter``).
    * a static ``CantAttack``/``CantBlock`` ``attack_defended`` recipient
      (Combat Calligrapher, the Vow cycle) or a Planeswalker-group ``affected``
      filter (an anthem/grant static — Ichormoon Gauntlet, Sorin).
    * a battlefield ``dies`` trigger whose subject includes Planeswalker,
      non-opponent scope (Carth the Lion, Cruel Celebrant — CR 700.4-adjacent).
    * a ``loyaltyabilityactivated`` trigger event (Chandra's Regulator, Keral
      Keep Disciples) or a ``GrantExtraLoyaltyActivations`` effect anywhere
      (The Chain Veil).
    * a dynamic count/cost-reduction operand naming Planeswalker
      (:func:`_superfriends_count_operand_ref`).
    * a loyalty-counter EFFECT (not the ability's own activation cost) whose
      target is non-Opponent (Chandra, Acolyte of Flame — "put a loyalty
      counter on each red planeswalker you control").
    """
    for unit in tree.units:
        node = unit.node
        for site in iter_condition_sites(node):
            if _superfriends_typed_ref(site):
                return True
        atf = getattr(node, "attack_target_filter", None)
        if atf in _PW_ATTACK_RECIPIENTS and trigger_scope(node) == "you":
            return True
        for sdef in iter_static_defs(node):
            if getattr(sdef, "attack_defended", None) in _PW_ATTACK_RECIPIENTS:
                return True
            aff = getattr(sdef, "affected", None)
            if aff is not None and _superfriends_typed_ref(aff):
                return True
        if (
            unit.trigger_event == "dies"
            and getattr(node, "origin", None) == "Battlefield"
            and "Planeswalker" in trigger_subject(node)
            and trigger_subject_scope(node) != "opponents"
        ):
            return True
        if unit.trigger_event == "loyaltyabilityactivated":
            return True
        for c in (*unit.effects, *unit.statics):
            if _superfriends_count_operand_ref(c):
                return True
        for c in unit.effects:
            if (
                c.concept in _SUPERFRIENDS_COUNTER_EFFECTS
                and counter_kind_any(c.node) == "LOYALTY"
                and filter_controller(getattr(c.node, "target", None)) != "Opponent"
            ):
                return True
        for n in iter_typed_nodes(node):
            if tag_of(n) == "GrantExtraLoyaltyActivations":
                return True
    return False


# ── arm: superfriends_matters bucket-B (ADR-0036/0037 fold) ──────────────────
# The description-only tail: phase leaves several genuine idiom families
# wholly unstructured (an Unimplemented static census failure — Shalai's "you,
# planeswalkers you control, ... have hexproof", Kasmina, Enigma Sage's
# "each other planeswalker you control has the loyalty abilities of ~"; a
# CantAttack/CantBlock static with no ``attack_defended`` payload at all —
# Onakke Oathkeeper, Promise of Loyalty, Assault Suit, Varchild; an "activate
# loyalty abilities of planeswalkers you control" permission ability with no
# ``GrantExtraLoyaltyActivations`` typed node — Oath of Teferi, Teferi,
# Temporal Archmage's emblem; a replacement/tax effect scoped to "planeswalkers
# you control" with no typed carrier — Pyromancer's Gauntlet, Kasmina,
# Enigmatic Mentor, Lae'zel). Read PER-CLAUSE (reminder-stripped) so a match is
# confined to ONE clause — the cross-clause false-positive class the deleted
# whole-card ``_SUPERFRIENDS_RX.search`` mirror carried.
#
# SYNTH-EXCLUSION-PARITY, three vetoes over the SAME clause (adjudicated
# b-batch): an OPPONENT-controlled planeswalker reference — "planeswalker...
# an opponent controls" (Eidolon of Obstruction's tax, Confront the Past's
# loyalty-drain mode) — a superfriends HOSER, not a your-payoff; a SELF-ONLY
# loyalty reference — "loyalty counters on him/Chandra/The Aetherspark" with
# NO group marker in the same clause (Chandra, Fire Artisan; Comet, Stellar
# Pup; Garruk Relentless; Grand Master of Flowers; Jace, Mirror Mage; Kaito,
# Bane of Nightmares; Kaito, Dancing Shadow; Nissa, Steward of Elements;
# Teferi, Master of Time; The Aetherspark) — CR 306.5 "being/running itself"
# is not caring about the GROUP, the same membership-not-caring principle the
# condition arm applies to bare Planeswalker typing, extended to a
# planeswalker's own loyalty total/threshold; and a generic incidental mention
# — "activate a loyalty ability this turn" with no group marker (Repeated
# Reverberation's copy-anything trigger) is likewise excluded (no group hook).
# Deliberately NOT clause-lookback-joined: a 1-clause lookback recovers Elspeth
# Conquers Death's split "Return target creature or planeswalker card... /
# Put... a loyalty counter on it" but ALSO re-admits Kaito, Dancing Shadow's
# unrelated prior "creatures you control" clause bleeding onto its self-only
# "activate loyalty abilities of Kaito" clause (the SequentialSibling bleed
# lesson) — that reintroduced over-fire outweighs the one-card recovery, so
# Elspeth Conquers Death's recursion mode (and Forge of Heroes' commander-type
# counter utility, which names no group marker at all) stay residual, logged.
_SUPERFRIENDS_PWUC_RX = re.compile(r"planeswalkers? you control", re.IGNORECASE)
_SUPERFRIENDS_LOYALTY_CTR_RX = re.compile(r"loyalty counters?", re.IGNORECASE)
_SUPERFRIENDS_ACTIVATE_LOYALTY_RX = re.compile(
    r"activate (?:a |one )?loyalty|one or more loyalty", re.IGNORECASE
)
_SUPERFRIENDS_PW_TYPE_RX = re.compile(r"planeswalker type", re.IGNORECASE)
_SUPERFRIENDS_ABILITIES_OF_RX = re.compile(
    r"abilit(?:y|ies) of (?:a |target |another |each )?planeswalker", re.IGNORECASE
)
_SUPERFRIENDS_OPPONENT_VETO_RX = re.compile(
    r"planeswalkers?\b[\s\w]{0,15}\bopponents?\b[\s\w]{0,10}\bcontrols?\b",
    re.IGNORECASE,
)
_SUPERFRIENDS_GROUP_MARKER_RX = re.compile(
    r"you control|planeswalkers|another|each|target planeswalker"
    r"|among|creatures? (?:and/or|or) planeswalkers?",
    re.IGNORECASE,
)


def _matches_superfriends_idiom(oracle: str) -> bool:
    """Whether a reminder-stripped oracle carries a bucket-B superfriends
    idiom, per-clause, minus the opponent/self-only/incidental vetoes."""
    for cl in clauses(_REMINDER.sub(" ", oracle or "")):
        if _SUPERFRIENDS_OPPONENT_VETO_RX.search(cl):
            continue
        if _SUPERFRIENDS_PWUC_RX.search(cl):
            return True
        if _SUPERFRIENDS_ACTIVATE_LOYALTY_RX.search(
            cl
        ) and _SUPERFRIENDS_GROUP_MARKER_RX.search(cl):
            return True
        if _SUPERFRIENDS_LOYALTY_CTR_RX.search(
            cl
        ) and _SUPERFRIENDS_GROUP_MARKER_RX.search(cl):
            return True
        if _SUPERFRIENDS_PW_TYPE_RX.search(cl):
            return True
        if _SUPERFRIENDS_ABILITIES_OF_RX.search(cl):
            return True
    return False


def _arm_superfriends_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``superfriends_matters`` node for a description-only
    planeswalker/loyalty payoff (CR 306.5) phase leaves wholly unstructured."""
    if has_structural_superfriends(tree):
        return None
    if not _matches_superfriends_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="superfriends_matters",
        concept="synth_superfriends_matters",
        scope="you",
        subject=(),
        desc="bucket-B superfriends payoff (phase emits no typed PW node)",
    )


# ── batch T5-niche-a: opponent_exile_matters (full relocation, no gate) ─────
# CR 406.1: the REFERENCES-their-exile payoff (ADR-0034 split; the
# graveyard-hate DOER is opponent_exile_makers). A 2-card population over the
# whole corpus (Umbris, Fear Manifest; That Which Was Compleated, not
# commander-legal): Umbris's own static carries the base ``AddPower{value:
# 1}``/``AddToughness{value: 1}`` grant but phase does NOT structure the "for
# each card your opponents own in exile" SCALING reference at all (no count
# operand on the modification — a genuine phase-parse gap, not a dropped
# read); no competing Tier-1 predicate exists. Relocates the deleted
# ``_OPP_EXILE_MATTERS_MIRROR`` verbatim — SOLE source (the flash_matters/
# suspect_matters no-competing-predicate precedent). Measured byte-identical
# (2/2 union, 0 drops, 0 adds).
_OPP_EXILE_MATTERS_SYNTH_RX = re.compile(
    r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
    r"|for each card your opponents own in exile|opponents own in exile",
    re.IGNORECASE,
)


def _matches_opponent_exile_matters_idiom(oracle: str) -> bool:
    return bool(_OPP_EXILE_MATTERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_opponent_exile_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_exile_matters`` node (the deleted
    ``_OPP_EXILE_MATTERS_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_opponent_exile_matters_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="opponent_exile_matters",
        concept="synth_opponent_exile_matters",
        scope="opponents",
        subject=(),
        desc="bucket-B opponent-exile-zone reference (CR 406.1)",
    )


# ── batch T5-niche-a: color_hoser (bucket-A widen + bucket-B tail) ─────────
# CR 105.2 / 613.1e: removal/restriction/bounce keyed on a NAMED color. The
# live lane already carries a single-target (Destroy/Counter/ChangeZone-
# Exile) structural arm; three bucket-A widenings (each a genuine phase-typed
# shape the live arm's narrower tag set missed, probed over the commander-
# legal corpus):
#
# (a) the MASS forms — ``DestroyAll`` (Anarchy), ``ChangeZoneAll`` to Exile
#     (Martyr's Cry), ``BounceAll`` (Hibernation, Llawan) — carry the SAME
#     direct top-level ``Typed``/``HasColor`` target the singular forms do;
#     ``BounceAll`` additionally excludes a ``You``-controlled target (no
#     self-bounce-synergy false read; none observed in the corpus, kept as a
#     defensive gate).
# (b) ``Counter`` effects phase frequently types as an ``And`` composite —
#     ``[StackSpell, Typed{HasColor}]`` (Gainsay, Deathgrip, Lifeforce) —
#     rather than a bare ``Typed`` target; the direct-carrier read now also
#     descends one level into an ``And``'s member filters.
#
# The residual tail (the "non<color> creatures get -X/-X" anthem-debuff,
# "can't cast/block <color>" restrictions — Gibbering Hyenas's ``CantBlock``
# static carries the qualifier ONLY in ``description``, a genuine phase gap —
# choose-a-color forms, and colorless-subject counterspells) has no
# structural home; relocated verbatim as the bucket-B tail via the deleted
# ``_COLOR_HOSER_RE`` kept-mirror, gap-gated against the widened structural
# read. Measured over the commander-legal corpus: structural 22 -> 30, 37
# residual cards still need the synth (mirror parity preserved, 0 drops).
def _has_direct_has_color(target: object) -> bool:
    if tag_of(target) == "Typed":
        return any(
            tag_of(p) == "HasColor" for p in getattr(target, "properties", ()) or ()
        )
    if tag_of(target) == "And":
        return any(
            _has_direct_has_color(f) for f in getattr(target, "filters", ()) or ()
        )
    return False


def _is_self_owned_bounce_target(target: object) -> bool:
    """Whether a ``BounceAll`` target names YOUR OWN permanents — either a
    top-level ``controller: You`` or an ``Owned{controller: You}`` PROPERTY
    (Word of Undoing's "all white Auras you own" — the ownership rides a
    property, not the plain ``controller`` field). Either shape is a
    self-service bounce-combo, not color hosing."""
    if filter_controller(target) == "You":
        return True
    if tag_of(target) == "Typed":
        for p in getattr(target, "properties", ()) or ():
            if tag_of(p) == "Owned" and getattr(p, "controller", None) == "You":
                return True
    return False


# ── arm: opponent_counter_grant text-fallback (ADR-0036/0037 Stage 5,
# T9-finalize) ────────────────────────────────────────────────────────────────
# CR 122.1/122.1d: a DETRIMENTAL counter placed on an OPPONENT's permanent —
# per-unit join, a ``place_counter`` whose kind is not beneficial AND either
# the counter's own target controller is Opponent, or kind == "stun" with a
# co-occurring same-unit tap of an opp-controller subject. The co-tap's own
# opp direction is READ off the counting unit's own ``description`` when
# present; only when that field is EMPTY does the live lane fall back to a
# whole-oracle scan (the anaphora-recovery combinators ``_TAP_OPP_CONTROL_P``/
# ``_EACH_PLAYER_P`` — phase loses the target to ParentTarget/DefendingPlayer
# on "tap target creature an opponent controls …" chains: Freeze in Place,
# Snaremaster Sprite, Mjölnir, Sensational Spider-Man, Omega, Mind Spiral,
# Stunning Shot). :func:`_opponent_counter_grant_fires` takes the fallback
# text as a parameter so the SAME per-unit walk serves both the structural
# gate (fallback="") and the arm (fallback=kept oracle) — one source, no
# drift.
def has_structural_opponent_counter_grant(tree: ConceptTree) -> bool:
    """A ``place_counter`` effect (non-beneficial kind) whose OWN typed
    target controller is directly Opponent (Mathas's bounty) — the ONLY
    pure-typed-field read. The stun+co-tap join always requires a text
    parse of a unit's own ``description`` (or, when empty, the whole
    oracle) via the anaphora-recovery combinators, so it is deliberately
    NOT included here — see :func:`_arm_opponent_counter_grant`, the
    lane's sole source for that join."""
    for unit in tree.units:
        for c in unit.effect_concepts("place_counter"):
            kind = counter_kind(c.node).lower()
            if kind in _OPP_COUNTER_BENEFICIAL:
                continue
            if filter_controller(getattr(c.node, "target", None)) == "Opponent":
                return True
    return False


def _arm_opponent_counter_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize an ``opponent_counter_grant`` node for the stun+co-tap
    join (Freeze in Place / Mind Spiral's "tap … and put a stun counter on
    IT" pronoun-loss recovery) — the deleted lane-time computation
    relocated verbatim, gap-gated against
    :func:`has_structural_opponent_counter_grant` (the direct-recipient
    case that gate covers is a strict subset of this join, so re-firing
    here would only ever duplicate it — the gate keeps the arm's role to
    genuine residue)."""
    if has_structural_opponent_counter_grant(tree):
        return None
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for unit in tree.units:
        raw = getattr(unit.node, "description", None) or kept
        opp_tap_here = any(
            settap_state(c.node) == "Tap"
            and (
                filter_controller(getattr(c.node, "target", None)) == "Opponent"
                or (
                    _TAP_OPP_CONTROL_P.run(raw) is not None
                    and _EACH_PLAYER_P.run(raw) is None
                )
            )
            for c in unit.effect_concepts("tap_untap")
        )
        for c in unit.effect_concepts("place_counter"):
            kind = counter_kind(c.node).lower()
            if kind in _OPP_COUNTER_BENEFICIAL:
                continue
            recip_opp = filter_controller(getattr(c.node, "target", None)) == "Opponent"
            if recip_opp or (kind == "stun" and opp_tap_here):
                return _synthetic_concept(
                    arm_id="opponent_counter_grant",
                    concept="synth_opponent_counter_grant",
                    scope="opponents",
                    subject=(),
                    desc="bucket-B stun+co-tap join (CR 122.1/122.1d)",
                )
    return None


# ── arm: cant_block_grant residue (ADR-0036/0037 Stage 5, T9-finalize) ────────
# CR 509.1b + 101.2: forcing blockers off clears an attack path. The typed
# structural gate (:func:`has_structural_cant_block_grant`) — a ``CantBlock``
# static def (top-level or nested under a spell's GenericEffect), gated to
# the themeable affected shapes, minus the Pacifism single-target-removal
# shape — covers most members. The two residual marker passes phase drops
# the grant for ENTIRELY (no typed CantBlock static at all) are relocated
# verbatim: (1) a per-unit node-scoped scan of the unit's own
# ``description``/concept raws (make_token units excluded — a created
# token's own drawback is not a grant; a multi-ability card's SILENT
# top-level SelfRef static excluded — no carrier raw survives), and (2) a
# whole-oracle scan for the dropped-static modal-bullet / quoted-grant
# segments.
_PACIFY_SIBLING_MODES: frozenset[str] = frozenset({"CantAttack", "CantAttackOrBlock"})
_CANT_BLOCK_THEMEABLE: frozenset[str] = frozenset({"Typed", "ParentTarget"})


def has_structural_cant_block_grant(tree: ConceptTree) -> bool:
    """A ``CantBlock``-mode static def with a themeable affected shape,
    minus the Pacifism single-target-removal sibling shape — the lane's
    ONLY pure-typed-field read; the two marker passes always require a
    text scan, so they are NOT included here (:func:`_arm_cant_block_grant`
    is the lane's sole source for those)."""
    ca_dicts = [
        aff.to_dict()
        for u in tree.units
        if u.origin == "static" and static_mode_tag(u.node) in _PACIFY_SIBLING_MODES
        for aff in (getattr(u.node, "affected", None),)
        if isinstance(aff, TypedMirrorNode)
    ]
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) != "CantBlock":
                continue
            aff = getattr(sdef, "affected", None)
            if tag_of(aff) not in _CANT_BLOCK_THEMEABLE:
                continue
            single = bool(set(filter_predicates(aff)) & _PACIFY_PREDS)
            if (
                unit.origin == "static"
                and single
                and isinstance(aff, TypedMirrorNode)
                and aff.to_dict() in ca_dicts
            ):
                continue
            return True
    return False


def _arm_cant_block_grant(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``cant_block_grant`` node for the two marker-pass
    residues (the deleted per-unit raw scan + whole-oracle modal-bullet/
    quote scan relocated verbatim), gap-gated against
    :func:`has_structural_cant_block_grant`."""
    if has_structural_cant_block_grant(tree):
        return None
    for unit in tree.units:
        if unit.has_effect("make_token"):
            continue
        if (
            unit.origin == "static"
            and len(tree.units) > 1
            and any(
                static_mode_tag(sd) == "CantBlock"
                and tag_of(getattr(sd, "affected", None)) == "SelfRef"
                for sd in iter_static_defs(unit.node)
            )
        ):
            continue
        raws = [getattr(unit.node, "description", None) or ""] + [
            c.raw for c in unit.iter_concepts() if c.raw
        ]
        for raw in raws:
            if _CANT_BLOCK_REF.search(raw) and not _CANT_BLOCK_TAX.search(raw):
                return _synthetic_concept(
                    arm_id="cant_block_grant",
                    concept="synth_cant_block_grant",
                    scope="you",
                    subject=(),
                    desc="bucket-B per-unit raw cant-block grant residue (CR 509.1b)",
                )
    kept = _REMINDER.sub(" ", tree.oracle or "")
    for pat in (_CANT_BLOCK_MODAL_BULLET, _CANT_BLOCK_GRANT_QUOTE):
        for m in pat.finditer(kept):
            seg = m.group(0)
            if _CANT_BLOCK_REF.search(seg) and not _CANT_BLOCK_TAX.search(seg):
                return _synthetic_concept(
                    arm_id="cant_block_grant",
                    concept="synth_cant_block_grant",
                    scope="you",
                    subject=(),
                    desc="bucket-B dropped-static modal/quote cant-block "
                    "residue (CR 509.1b)",
                )
    return None


def has_structural_color_hoser(tree: ConceptTree) -> bool:
    """A Destroy/Counter/mass-Destroy/mass-Exile/mass-Bounce effect whose
    target (or, for Counter, an ``And``-composite member) directly names a
    color via ``HasColor`` — the live single-target arm widened to the mass
    forms and the ``And``-wrapped Counter-target shape."""
    for unit in tree.units:
        for c in unit.effects:
            t = tag_of(c.node)
            target = getattr(c.node, "target", None)
            hosing = (
                t in ("Destroy", "Counter", "DestroyAll")
                or (t == "ChangeZone" and change_zone_dirs(c.node)[1] == "Exile")
                or (
                    t == "ChangeZoneAll"
                    and getattr(c.node, "destination", None) == "Exile"
                )
                or (t == "BounceAll" and not _is_self_owned_bounce_target(target))
            )
            if not hosing or not _has_direct_has_color(target):
                continue
            if "Graveyard" in filter_inzone_zones(target) and (
                filter_controller(target) != "Opponent"
            ):
                continue  # your-graveyard self-recursion, not hosing
            return True
    return False


def _matches_color_hoser_idiom(oracle: str) -> bool:
    return bool(_COLOR_HOSER_RE.search(_REMINDER.sub(" ", oracle or "")))


def _arm_color_hoser(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``color_hoser`` node for the anthem-debuff / can't-cast /
    can't-block / choose-a-color residue (the deleted ``_COLOR_HOSER_RE``
    kept-mirror relocated, gap-gated against
    :func:`has_structural_color_hoser`)."""
    if has_structural_color_hoser(tree):
        return None
    if not _matches_color_hoser_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="color_hoser",
        concept="synth_color_hoser",
        scope="you",
        subject=(),
        desc="bucket-B color-hate debuff/restriction residue (CR 105.2)",
    )


# ── batch T5-niche-a: void_warp_makers (full relocation, no gate) ──────────
# CR 702.185a Warp (two statics while on the stack: cast from hand for
# [cost], exile at next end step with a re-cast permission) + CR 207.2c
# (void is an ABILITY WORD — no rules meaning, no phase keyword): the three
# PERFORM/GRANT arms (keyword bearers, granters, em-dash/graveyard self-cast
# forms). LOGGED, not taken: v0.9.0 carries a parameterized ``{Warp: cost}``
# keyword array, a ``variant: Warp`` cast permission, and the structured
# ``AddKeyword.keyword.Warp`` grant — but the Scryfall keyword array
# UNDER-FIRES the granters (Tannuk-shaped "have warp" text carries no card-
# level Warp keyword), so no competing Tier-1 predicate reproduces the full
# population without a second, keyword-blind gap-check this stage cannot run
# (synth arms see only the tree, never the Scryfall keyword array). Relocates
# the deleted ``_VOID_WARP_MAKERS_RX`` verbatim — SOLE source (the
# flash_matters/opponent_exile_matters no-competing-predicate precedent).
# Measured byte-identical (33/33 union, 0 drops, 0 adds).
_VOID_WARP_MAKERS_SYNTH_RX = re.compile(VOID_WARP_MAKERS_REGEX, re.IGNORECASE)


def _matches_void_warp_makers_idiom(oracle: str) -> bool:
    return bool(_VOID_WARP_MAKERS_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_void_warp_makers(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``void_warp_makers`` node (the deleted
    ``_VOID_WARP_MAKERS_RX`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_void_warp_makers_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="void_warp_makers",
        concept="synth_void_warp_makers",
        scope="you",
        subject=(),
        desc="bucket-B Warp keyword bearer/grant/recast residue (CR 702.185a)",
    )


# ── batch T5-niche-a: sacrifice_protection (full relocation, no gate) ──────
# CR 701.21a (a sacrifice is the controller's move; "can't cause you to
# sacrifice" wins by 101.2): the verdict RE-CONFIRMED against v0.9.0 —
# Sigarda still parses as ``abilities/Spell.effect/Unimplemented`` ([P42],
# SUPPLEMENT-RECOVERABLE), so the two literal phrases stay the only
# full-coverage tell; no competing Tier-1 predicate exists. Relocates the
# deleted (inline, no importable name) ``_SAC_PROTECTION_MIRROR`` verbatim —
# SOLE source (the flash_matters/opponent_exile_matters no-competing-
# predicate precedent). Measured byte-identical.
_SAC_PROTECTION_SYNTH_RX = re.compile(
    r"can't cause you to sacrifice|can't be sacrificed", re.IGNORECASE
)


def _matches_sacrifice_protection_idiom(oracle: str) -> bool:
    return bool(_SAC_PROTECTION_SYNTH_RX.search(_REMINDER.sub(" ", oracle or "")))


def _arm_sacrifice_protection(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``sacrifice_protection`` node (the deleted
    ``_SAC_PROTECTION_MIRROR`` relocated verbatim — no competing Tier-1
    predicate exists, so this is the lane's SOLE source)."""
    if not _matches_sacrifice_protection_idiom(tree.oracle or ""):
        return None
    return _synthetic_concept(
        arm_id="sacrifice_protection",
        concept="synth_sacrifice_protection",
        scope="you",
        subject=(),
        desc=(
            "bucket-B can't-be-sacrificed / can't-cause-sacrifice residue (CR 701.21a)"
        ),
    )


# ── T9-finalize bucket-B: 5 sweep-closeout structural+residue UNION folds ─────
# Each of these five lanes was already a Tier-1 structural read UNION a
# byte-identical residue mirror; T9-finalize relocates the residue mirror
# into a gap-gated synth arm so the union itself becomes lane-time-text-free.

_LEGEND_RULE_OFF_SYNTH_RX = re.compile(
    r"the .legend rule. doesn't apply", re.IGNORECASE
)
_TARGETING_RESIDUE_SYNTH_RX = re.compile(
    r"becomes the target of a spell or ability"
    r"|whenever [^.]{0,60}?becomes? the target of|\bheroic\b"
    r"|whenever you cast (?:an instant or sorcery spell |a spell )?"
    r"that targets",
    re.IGNORECASE,
)


def has_structural_legend_rule_off(tree: ConceptTree) -> bool:
    """CR 704.5j: a ``LegendRuleDoesntApply`` static mode phase types
    directly (the unbounded AND the Cadric-style bounded forms)."""
    return any(
        unit.origin == "static"
        and static_mode_tag(unit.node) == "LegendRuleDoesntApply"
        for unit in tree.units
    )


def _arm_legend_rule_off(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``legend_rule_off`` node for the 4-card residue phase
    keeps textual (the Yamazaki family, Syr Joshua/Syr Saxon, The Herald
    of Numot) — the deleted ``_LEGEND_RULE_OFF_RX`` mirror relocated
    verbatim, gap-gated against :func:`has_structural_legend_rule_off`."""
    if has_structural_legend_rule_off(tree):
        return None
    if not _LEGEND_RULE_OFF_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="legend_rule_off",
        concept="synth_legend_rule_off",
        scope="you",
        subject=(),
        desc="bucket-B legend-rule-off residue (CR 704.5j)",
    )


def has_structural_targeting_matters(tree: ConceptTree) -> bool:
    """CR 702.21a: ANY native ``becomes_target`` trigger unit."""
    return any(unit.trigger_event == "becomes_target" for unit in tree.units)


def _arm_targeting_matters(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``targeting_matters`` node for the granted/quoted/
    player-targeted forms phase emits no native trigger for (Kira / Opaline
    Sliver / Dormant Gomazoa / heroic) — the deleted ``_TARGETING_RESIDUE_RX``
    mirror relocated verbatim, gap-gated against
    :func:`has_structural_targeting_matters`."""
    if has_structural_targeting_matters(tree):
        return None
    if not _TARGETING_RESIDUE_SYNTH_RX.search(_REMINDER.sub(" ", tree.oracle or "")):
        return None
    return _synthetic_concept(
        arm_id="targeting_matters",
        concept="synth_targeting_matters",
        scope="any",
        subject=(),
        desc="bucket-B granted/quoted/heroic becomes-target residue (CR 702.21a)",
    )


# The wants_theft/gain_control hybrid-FACADE "don't own" tell (CR 800.4a) —
# moved here from crosswalk_signals (the _DEATH_PAYOFF_EFFECTS neutral-home
# precedent: crosswalk_signals only ever imports FROM tree_synthesis, never
# the reverse). Runs over the RAW oracle (NOT reminder-stripped — byte-
# parity with the deleted reconciliation-body read; phase oracle_text
# occasionally differs from bulk oracle in whitespace/name-substitution,
# shadow-diff data, logged not normalized).
_DONT_OWN_RX = re.compile(
    r"you (?:cast|control|own)?[^.]{0,25}?(?:do not|don't) own", re.IGNORECASE
)


def _arm_dont_own(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``dont_own`` node for the wants_theft/gain_control
    hybrid-facade "don't own" tell (CR 800.4a) — the live ``_DONT_OWN_RX``
    whole-oracle scan relocated verbatim (byte-parity: the RAW oracle,
    NOT reminder-stripped, matching the deleted reconciliation-body
    read). No competing Tier-1 predicate exists for this specific tell —
    it is the reconciliation's SOLE source, unchanged from the deleted
    read."""
    if _DONT_OWN_RX.search(tree.oracle or ""):
        return _synthetic_concept(
            arm_id="dont_own",
            concept="synth_dont_own",
            scope="opponents",
            subject=(),
            desc="bucket-B wants_theft/gain_control don't-own tell (CR 800.4a)",
        )
    return None


# ── damage_prevention bucket-B (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2) ─
# The CR 615 prevention-shield MEMBERSHIP replacement arm ([P29]): a
# ``DamageDone`` REPLACEMENT with ``shield_kind {Prevention}`` (the Palisade
# Giant family) parses IDENTICALLY for an OFFENSIVE curse ("All damage that
# would be dealt to enchanted creature is dealt to its controller instead" —
# Treacherous Link) — a redirect-to-controller shield, not a real prevention
# shield (Mirror Strike, which shields YOU, is the genuine member). The
# shielded SUBJECT tell lives only in the replacement's own description
# (adjudicated: exactly two redirect-to-controller shields in the corpus).
def _arm_damage_prevention(tree: ConceptTree) -> ConceptNode | None:
    """Synthesize a ``damage_prevention`` node for the replacement-shield
    MEMBERSHIP arm, vetoing the OFFENSIVE-curse redirect shape
    (Treacherous Link) via the node's own description — the deleted
    lane-time veto relocated verbatim. CR 615."""
    for unit in tree.units:
        if not (
            unit.origin == "replacement"
            and replacement_event_tag(unit.node) == "DamageDone"
            and replacement_shield_kind(unit.node) == "Prevention"
        ):
            continue
        raw = getattr(unit.node, "description", None) or ""
        if "dealt to enchanted creature is dealt to" in raw.lower():
            continue
        return _synthetic_concept(
            arm_id="damage_prevention",
            concept="synth_damage_prevention",
            scope="you",
            subject=(),
            desc="bucket-B prevention-shield replacement (CR 615)",
        )
    return None
