"""Crosswalk signal lanes — graveyard makers/matters, fight/goad, lifeloss,
edicts, debuffs, clones, and the monarch/venture whole-card makers (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    EFFECT_CONCEPTS,
    AbilityUnit,
    ConceptTree,
    change_zone_dirs,
    condition_tags,
    cost_has_paylife,
    counter_kind,
    damage_to_player_trigger_kind,
    effect_filter,
    effect_owner_player_scope,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    has_nested_connive,
    has_nested_fight,
    iter_cost_leaves,
    iter_delayed_trigger_condition_defs,
    iter_nested_trigger_defs,
    iter_static_defs,
    iter_typed_nodes,
    lifeloss_recipient_is_degraded_typed,
    lifeloss_recipient_scope,
    mod_value,
    node_lure_mode,
    pump_is_negative,
    static_mode_tag,
    tag_of,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.mirror.runtime import (
    MISSING,
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _GOAD_REWARD_REF,
    _LURE_ABLE,
    _LURE_MUST,
    _copied_type_from_text,
    combat_damage_recipients_from_text,
)
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge._sweep_detectors import COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _DEBUFF_SINGLE_AURA_PREDS,
    _EDICT_ACTORS,
    _YOU_EACH,
    _attack_compulsion_hit,
    _kept,
    _negative_pt_field,
    _unknown_mode_combat_damage_to_player,
    _whole_card_maker,
)
from mtg_utils._deck_forge.signal_base import (
    Signal,
    _clauses,
    _resolve_subject,
)
from mtg_utils._deck_forge.text_reads import (
    _GOAD_STYLE_FORCE,
    _graveyard_matters_clauses,
)

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


# np_boons task #3: a recovered "bounce" node's direction gate (see
# ``_graveyard_makers``'s own docstring) — the grammar token fires on ANY
# "return ... to hand/owner" clause regardless of origin zone, so the raw
# text itself must confirm a graveyard ORIGIN before the lane counts it as
# a graveyard_makers recursion (never a battlefield tempo bounce). A bare
# "graveyard" mention isn't enough (Soulfire Grand Master's replacement
# "put that card into your hand instead of into your graveyard as it
# resolves" mentions "graveyard" too, but as the AVOIDED destination, with
# no "hand" reference following it) — every genuine recursion clause names
# "graveyard" BEFORE "hand" (the CR 400.7 origin-then-destination order:
# "from your graveyard to your hand", "leave ... in your graveyard and put
# the rest into your hand"), so require "hand" to appear somewhere AFTER
# "graveyard", not merely present anywhere in the clause.
_GY_RECOVERED_BOUNCE_RE = re.compile(r"\bgraveyard\b[\s\S]*?\bhand\b", re.IGNORECASE)


def _graveyard_makers(tree: ConceptTree) -> list[Signal]:
    """graveyard_makers — the card PERFORMS a graveyard interaction (CR 404 /
    603.6e / 701.17a). Structural arms over the typed substrate:

    * a ``ChangeZone`` reanimation (``(Graveyard, Battlefield)``) or recursion
      (``(Graveyard, Hand)``) — the typed ``change_zone_dirs`` reads the origin
      HONESTLY, so an exile-return (origin=Exile — Banisher Priest) is excluded
      structurally without the live path's ``_EXILE_RETURN_RE`` (the substrate is
      strictly better here);
    * a ``Mill`` effect (self / any / symmetric scope) — self-mill fills your own
      graveyard;
    * an enchant-reanimation ``GrantAbility`` static whose granted
      ``Unimplemented`` definition carries the CR 303.4h "put onto the
      battlefield with ~" reminder text (Necromancy — the reanimation clause
      itself is dropped entirely from the effect chain; see the arm's own
      comment);
    * a ``graveyard_return``-recovered node (:mod:`~mtg_utils._card_ir.
      recovery`'s ALLOWLIST) — a for-each-loop graveyard recursion phase
      drops entirely (All Suns' Dawn / Rogues' Gallery's "for each color,
      return ... from your graveyard to your hand"; Travel Through
      Caradhras's per-vote "For each Mines of Moria vote, return a card
      from your graveyard to your hand");
    * a ``Mill`` unit whose OWN ``unless_pay`` field carries a return-
      unless-pay rider phase attaches NO effect node for at all (Sivriss,
      Nightmare Speaker: "you mill a card, then return that card from your
      graveyard to your hand unless that player pays 3 life" — ``S_
      unless_pay`` structurally carries only ``cost``/``payer``, no
      ``effect`` field for what happens on a decline, so the "return" half
      is invisible to any node walk; the unit's own description is the only
      surviving trace). Gated on the SAME unit ALSO carrying the mill
      effect (granularity a) and the description naming all three of
      "return"/"graveyard"/"hand" — corpus-swept (every mill unit
      carrying ANY ``unless_pay``): Broken Ambitions is the one other hit,
      whose ``unless_pay`` belongs to an unrelated Counter effect several
      sentences before its OWN "mills four cards" clash payoff and names
      none of those three words, so the text gate excludes it cleanly.

    The cast-from-GY keyword family (flashback / escape / …) rides a keyword
    field-lookup in :func:`extract_crosswalk_signals` (no effect node to read).
    The broad zone-tag-recovered arms (GY-cast grants, GY-hate exile, ``in:graveyard``
    bounce) the lossy IR reconstructed from recovered zone strings are a documented
    ``live_only`` residue (the typed substrate exposes zones only on ``ChangeZone``).

    np_boons task #3 (Comet, Stellar Pup) adds a RECOVERED-node arm: each
    numbered die outcome on a die-roll planeswalker is its own Unimplemented
    node with a full description (never a shared multi-outcome raw blob —
    each outcome is its OWN ability unit), so a recovered "bounce" token
    (the recovery ALLOWLIST's ``change_zone`` row, CR 400.4/404 — "return a
    card ... from your graveyard to your hand") carries no typed
    ``origin``/``destination`` for :func:`change_zone_dirs` to read (the same
    gap ``discard``/``draw``/``damage`` already document) — direction/origin
    is decided from the recovered node's OWN raw text instead (the
    recovered-node raw-read precedent), gated to require the literal word
    "graveyard" so a battlefield-bounce recovery (unrelated to this lane)
    never fires it.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("graveyard_makers", scope, "", raw, tree.name, "high"))

    for c in tree.effect_concepts("change_zone"):
        origin, dest = change_zone_dirs(c.node)
        gy_direct = origin == "Graveyard" and dest in ("Battlefield", "Hand")
        gy_recovered = c.recovered_by == "bounce" and _GY_RECOVERED_BOUNCE_RE.search(
            c.raw or ""
        )
        if gy_direct or gy_recovered:
            fire(_gy_scope(c.scope), c.raw)
    # PILE-TO-GRAVEYARD maker (task #84): phase v0.23.0 restructured the
    # Fact or Fiction family ("reveal the top five…, an opponent separates
    # …, put one pile into your hand and the other into your graveyard" —
    # FoF, Sphinx of Uthuun / Clear Skies, Unesh) from a mis-tagged
    # ``origin: Graveyard`` recursion chain into a typed
    # ``SeparateIntoPiles`` whose ``unchosen_pile_effect`` is a
    # ``ChangeZone`` to Graveyard. The rejected pile fills YOUR graveyard
    # from your own library reveal — the same self-fill value the Mill arm
    # serves (CR 404.1; the reveal source is your library, CR 401.4-family
    # information + selection). Gated on the pile SOURCE being your own
    # library reveal: ``pile_source: RevealedFromLibraryTop`` directly
    # (Fact or Fiction, Unesh), or the ``ExiledThisWay`` back-reference
    # tag phase ALSO stamps on a "reveal the top X … those cards" chain
    # (Sphinx of Clear Skies — nothing is exiled; the tag is the generic
    # previous-set back-ref), accepted ONLY when the same unit carries a
    # ``reveal_top`` effect naming that revealed set. A battlefield
    # partition (Make an Example — an edict, CR 701.21) or a genuine
    # graveyards-exile partition (Boneyard Parley — reanimation raw
    # material returning where it started, no RevealTop sibling) never
    # fires a self-fill it doesn't perform.
    for unit in tree.units:
        unit_reveals = any(c.concept == "reveal_top" for c in unit.effects)
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "SeparateIntoPiles":
                continue
            src = tag_of(getattr(n, "pile_source", None))
            if src != "RevealedFromLibraryTop" and not (
                src == "ExiledThisWay" and unit_reveals
            ):
                continue
            for arm_field in ("chosen_pile_effect", "unchosen_pile_effect"):
                arm = getattr(n, arm_field, None)
                eff = getattr(arm, "effect", None) if arm is not None else None
                if (
                    isinstance(eff, TypedMirrorNode)
                    and tag_of(eff) == "ChangeZone"
                    and change_zone_dirs(eff)[1] == "Graveyard"
                ):
                    fire("you", "")
    # ENCHANT-REANIMATION maker (task #np_gyfam): the "cast as a plain
    # enchantment, then become an Aura and reanimate" idiom (CR 303.4h /
    # 400.7 / 701.17a — Necromancy: no printed "Enchant creature card in a
    # graveyard" restriction up front, unlike Animate Dead / Dance of the
    # Dead, whose static Enchant keyword lets phase parse the ETB trigger's
    # reanimation as a direct top-level ``ChangeZone(Graveyard, Battlefield)``
    # effect the arm above already reads). Necromancy's ETB trigger instead
    # drops the "Put target creature card from a graveyard onto the
    # battlefield ... and attach ~ to it" clause ENTIRELY out of the effect
    # chain — the only surviving trace is the ``GrantAbility`` STATIC (role=
    # static, never reached by ``effect_concepts``) whose granted-ability
    # ``definition.effect`` is an ``Unimplemented`` node carrying the CR
    # 303.4h reminder text verbatim ("enchant creature put onto the
    # battlefield with ~"). That reminder phrasing is unique to this exact
    # reanimation-Aura idiom (corpus swept: 1 hit — Necromancy — out of every
    # commander/brawl/standardbrawl-legal card; Scryfall rulings confirm "the
    # bringing of the creature onto the battlefield and then putting
    # Necromancy on it is all done as part of the resolution"), so a
    # structural read gated on the exact GrantAbility/Unimplemented shape +
    # phrase is safe with no oracle-text idiom scan of its own.
    for unit in tree.units:
        for c in unit.statics:
            if tag_of(c.node) != "GrantAbility":
                continue
            definition = getattr(c.node, "definition", None)
            granted = getattr(definition, "effect", None) if definition else None
            if tag_of(granted) != "Unimplemented":
                continue
            desc = (getattr(granted, "description", "") or "").lower()
            if "put onto the battlefield with" in desc:
                fire("you", desc)
    # graveyard_return-recovered for-each-loop recursion (task #np_gyfam) —
    # trusted unconditionally, matching the "reveal_hand"/"dig_until" recovery
    # precedent (see recovery.ALLOWLIST's own comment for this token).
    for c in tree.effect_concepts("graveyard_return"):
        fire("you", c.raw)
    # Mill-then-return-unless-pay (task #np_gyfam): the "return" half has no
    # effect node — see the docstring's own note — so this is a whole-UNIT
    # (never whole-card) structural+text gate: the SAME unit's Mill effect
    # plus its own ``unless_pay`` plus its own description naming the
    # return.
    for unit in tree.units:
        if not any(c.concept == "mill" for c in unit.effects):
            continue
        up = getattr(unit.node, "unless_pay", None)
        if not isinstance(up, TypedMirrorNode):
            continue
        desc = (getattr(unit.node, "description", "") or "").lower()
        if "return" in desc and "graveyard" in desc and "hand" in desc:
            fire("you", desc)
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


def graveyard_return_direction(tree: ConceptTree) -> bool:
    """True when TREE carries a ``ChangeZone`` reading Graveyard->Hand (CR
    400.7 recursion — Regrowth, Eternal Witness), as opposed to the OTHER
    two GY-interaction directions :func:`_graveyard_makers` also folds into
    its single ``graveyard_makers`` key: reanimation (Graveyard->
    Battlefield) and self-mill (a ``Mill`` into Graveyard). The merged
    Signal carries no ``subject`` distinguishing them (empty string — see
    :func:`_graveyard_makers`'s own docstring), so a preset VIEW wanting
    ONLY the hand-return direction (task #83 'graveyard-return') can't
    filter on ``signal_keys`` alone; this predicate re-runs the SAME
    ``change_zone_dirs`` read :func:`_graveyard_makers` itself performs on
    the SAME ``ChangeZone`` concepts, just keeping the destination that
    lane's ``fire()`` helper collapses away.

    task #87 (preset-membership only — this predicate feeds ONLY the
    ``graveyard-return`` preset concept arm, never a corpus Signal) adds
    FOUR structural arms for a #85-census residue tail, each a genuine
    ``ChangeZone``/keyword-grant the flat top-level ``effect_concepts``
    walk never reaches:

    * a MODAL/branch/die-roll-table descent — a Graveyard->Hand
      ``ChangeZone`` sitting inside a ``ChooseMode``'s ``branches[]``
      (Ghostly Dancers's "return an enchantment card from your graveyard
      to your hand OR unlock a Room") or a ``RollDie``'s ``results[]``
      (The Deck of Many Things's "1-9: return a card at random from your
      graveyard to your hand" table entry) — neither field is among
      ``_EFFECT_CHILD_FIELDS``, so raw :func:`iter_typed_nodes` (a true
      generic deep walk, the :func:`has_nested_extra_turn` precedent) is
      the fallback rather than widening that curated walk's field list
      (which would touch every OTHER lane built on it);
    * the OPPONENT-CHOOSES idiom (Tasigur, the Golden Fang's Delve
      ability; Mausoleum Turnkey's ETB) — phase models "return a
      creature card OF AN OPPONENT'S CHOICE from your graveyard to your
      hand" as a ``ChooseFromZone(zone=Graveyard, chooser=Opponent)``
      immediately chained (``.sub_ability``) into a ``ChangeZone(
      destination=Hand, origin=None, target=Any)`` — the selection
      already resolved the source zone, so ``change_zone_dirs``' own
      ``origin`` read is honestly ``None`` here (not a bug), and this
      predicate's ONLY job is recognizing the immediately-preceding
      ``ChooseFromZone`` as the true origin;
    * a COST-shaped return rider (Harvest Wurm's "sacrifice it unless
      you return a basic land card from your graveyard to your hand") —
      phase models the "unless" alternative as an ``unless_pay.cost``
      whose tag is ``ReturnToHand`` (a distinct tag from ``ChangeZone``,
      carrying its own ``from_zone``), never an effect node at all —
      cost-shaped, so :func:`_graveyard_makers`'s own effect-role walk
      structurally can't reach it either;
    * a Soulshift grant with a DYNAMIC value (Kodama of the Center
      Tree's "soulshift X, where X is the number of Spirits you
      control") — CR 702.46a: "When this permanent is put into a
      graveyard from the battlefield, you may return target Spirit card
      ... from your graveyard to your hand." A FIXED-N soulshift
      (Burr Grafter's "Soulshift 3") already carries a real ``triggers``
      entry phase fully expands (reachable via the ordinary top-level
      arm above — corpus-swept 2026-07, 26/27 soulshift carriers), but
      the dynamic-X variant carries ONLY a static's ``AddKeyword({
      Soulshift: N})`` grant with no accompanying trigger node at all —
      the keyword declaration IS the only surviving residue, read
      generically off ANY static's keyword-grant modification (mirrors
      the mill_makers-family keyword-array precedent, just off the
      phase-native tag rather than the Scryfall ``keywords`` array).
      Corpus-narrow: 1/27 soulshift carriers needs this (the census's
      other named probe, Garza's Assassin's Recover, has NO phase-level
      residue at all — its whole "Recover—Pay half your life..." clause
      is a ``SwallowedClause`` parse_warning with zero surviving nodes,
      not even a keyword tag; the ``graveyard-return`` Preset's own
      ``keywords=("Soulshift", "Recover")`` arm catches it instead, off
      the MTGJSON/Scryfall ``keywords`` array — a separate, independent
      data source from phase's own parse).

    task #np_gyfam adds a ``graveyard_return``-recovered node (a for-each
    loop's "return ... from your graveyard to your hand" phase drops
    entirely — All Suns' Dawn, Rogues' Gallery, Travel Through Caradhras's
    Mines-of-Moria vote): trusted unconditionally, the same recovery-
    provenance trust :func:`_graveyard_makers`'s own arm extends it; and a
    Mill-then-return-unless-pay unit (Sivriss, Nightmare Speaker) — the SAME
    whole-unit structural+text gate :func:`_graveyard_makers` runs for it.

    np_boons task #3 (Comet, Stellar Pup): a recovered "bounce" node (see
    ``_graveyard_makers``'s own recovered-node arm) joins this preset
    predicate too, same raw-gated direction check — the corpus signal and
    the preset membership stay in lockstep for this class rather than
    silently diverging. In practice this arm is reached only by a bounce
    clause that never mentions "graveyard" at all is impossible for THIS
    predicate (it requires the word "graveyard"), so it is reached only when
    the clause-grammar's ``graveyard_return`` arm (tried first in
    ``_RETURN``'s alt chain) did NOT already claim the token — a for-each/
    modal wrapper phase peels differently than the flat clauses that arm
    targets. Kept as a second, independent path rather than pruned, per the
    no-postponement integration's "prove disjointness, don't delete" rule.
    """
    if any(
        change_zone_dirs(c.node) == ("Graveyard", "Hand")
        for c in tree.effect_concepts("change_zone")
    ):
        return True
    if tree.effect_concepts("graveyard_return"):
        return True
    for unit in tree.units:
        if not any(c.concept == "mill" for c in unit.effects):
            continue
        up = getattr(unit.node, "unless_pay", None)
        if not isinstance(up, TypedMirrorNode):
            continue
        desc = (getattr(unit.node, "description", "") or "").lower()
        if "return" in desc and "graveyard" in desc and "hand" in desc:
            return True
    if any(
        c.recovered_by == "bounce" and _GY_RECOVERED_BOUNCE_RE.search(c.raw or "")
        for c in tree.effect_concepts("change_zone")
    ):
        return True
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "ChangeZone":
                if change_zone_dirs(n) == ("Graveyard", "Hand"):
                    return True
                continue
            if t == "ReturnToHand":
                if getattr(n, "from_zone", None) == "Graveyard":
                    return True
                continue
            if t == "AddKeyword":
                kw = getattr(n, "keyword", None)
                if isinstance(kw, MirrorVariant) and kw.key == "Soulshift":
                    return True
                continue
            # Opponent-chooses idiom: an ability WRAPPER (untagged —
            # ``ChooseFromZone``/``ChangeZone`` are its ``.effect``/
            # ``.sub_ability.effect``, not fields of its own) whose
            # ``.effect`` is a ``ChooseFromZone(zone=Graveyard)`` chained
            # directly into a ``ChangeZone(destination=Hand)``.
            eff = getattr(n, "effect", MISSING)
            if not (
                isinstance(eff, TypedMirrorNode)
                and tag_of(eff) == "ChooseFromZone"
                and getattr(eff, "zone", None) == "Graveyard"
            ):
                continue
            sub = getattr(n, "sub_ability", None)
            sub_eff = getattr(sub, "effect", None) if sub is not None else None
            if (
                isinstance(sub_eff, TypedMirrorNode)
                and tag_of(sub_eff) == "ChangeZone"
                and getattr(sub_eff, "destination", None) == "Hand"
            ):
                return True
    return False


# Rowan's Grim Search's exact phrasing for a Dig's dropped rest-destination
# (task #np_gyfam) — see ``self_mill_fill``'s Dig arm.
_DIG_REST_GRAVEYARD_RE = re.compile(r"\brest into your graveyard\b", re.IGNORECASE)


def self_mill_fill(tree: ConceptTree) -> bool:
    """True when TREE puts cards from YOUR OWN library into YOUR OWN
    graveyard (CR 701.17a self-mill) — the task #83 'self-mill' preset
    view. THREE structural shapes, all re-reading node families
    :func:`_graveyard_makers` / :func:`_topdeck_selection` already read
    rather than hand-rolling a new scan:

    * a bare ``Mill`` effect (:func:`_graveyard_makers`'s own arm) whose
      ``destination`` is Graveyard and whose scope isn't opponents-only
      (Stitcher's Supplier — self or symmetric-each mill both count, the
      SAME scope gate that lane's Mill arm runs);
    * a filter effect (Satyr Wayfinder / Grisly Salvage / Ransack the Lab —
      "look at/reveal the top N, put a card to hand, the rest into your
      graveyard") — a ``Dig`` node (the SAME tag :func:`_topdeck_selection`'s
      own target-tag set reads) whose ``player`` is Controller (self) and
      whose ``rest_destination`` is Graveyard. ``rest_destination`` is a
      DIFFERENT field than the ``destination`` gate ``_topdeck_selection``
      itself inspects (that lane fires on the SELECTED card's destination,
      never the discarded rest), so reading it here doesn't duplicate or
      contradict that lane's own membership — a Contingency-Plan-style
      "put the rest on the BOTTOM of your library" Dig has no
      ``rest_destination`` of Graveyard and correctly stays excluded
      (Contingency Plan itself actually parses as a bare ``Surveil`` node
      with no ``rest_destination`` field at all, so it never reaches this
      branch either way);
    * a THIRD phrasing (Mulch / Beast Hunt / Winding Way / Chromescale
      Drake — "reveal the top N cards of your library, put all cards of
      TYPE X into your hand and the rest into your graveyard") that phase
      structures differently than the ``Dig`` shape above: a ``reveal_top``
      effect (:func:`_topdeck_selection`'s own arm) followed by TWO SIBLING
      ``ChangeZone`` effects in the same unit — one to Hand, one to
      Graveyard — each targeting a ``TrackedSet``/``TrackedSetFiltered``
      back-reference into the revealed group (the SAME back-reference tag
      :func:`_blink_flicker` / :func:`_topdeck_selection`'s mill-then-cheat
      arm already read for an analogous "consume the earlier group" shape).
      A ``ChangeZone`` to Graveyard whose target is that back-reference tag
      IS the "rest of a revealed group" by construction — self-mill by
      definition — corpus-confirmed against every task #83 scoping-pass
      preset-only example (Mulch, Winding Way, Wrenn and Seven, Borborygmos
      Enraged, Underrealm Lich).

    Deliberately NOT a raw ``signal_keys`` union of ``mill_makers`` /
    ``graveyard_makers`` / ``topdeck_selection``: ``topdeck_selection``'s
    Scry/Surveil arm fires unconditionally (no graveyard-destination gate
    at all), which would match Contingency Plan under a raw union — the
    task #83 preset-scoping pass's own recorded ``fixture_flips`` for this
    preset. ``mill_makers`` is a keyword-only field lookup with scope
    "any" (self OR opponent, undiscriminated — CANNOT tell self-mill from
    opponent-mill at all), so it isn't reused here either; the three arms
    above are the precise, self-scoped shape.

    task #87 (preset-membership only) adds TWO more structural arms for a
    #85-census residue tail:

    * a BRANCH-nested bare ``Mill`` (HYDRA Troopers's "create a token if
      [condition]. Otherwise, mill two cards.") — the ``Mill`` sits inside
      a trigger's ``else_ability`` field, which ``_EFFECT_CHILD_FIELDS``'s
      curated walk never follows (unlike ``chosen_pile_effect`` /
      ``mode_abilities``, added for other shapes); raw
      :func:`iter_typed_nodes` reaches it directly (the
      :func:`has_nested_extra_turn` precedent) with the SAME destination/
      scope gate the bare-``Mill`` arm above already runs;
    * a "look/reveal-then-keep-one" idiom whose surviving structural
      residue is a single marker field rather than an explicit rest-
      destination: a ``Dig`` (Underrealm Lich's draw-replacement "look at
      the top three... put one into your hand and the rest into your
      graveyard") or ``RevealTop`` (Animal Magnetism / Selective
      Adaptation's "reveal the top N... put one onto the battlefield/
      hand and the rest into your graveyard") node whose immediate
      "keep one" step — followed through ``.sub_ability``, skipping past
      any ``Unimplemented`` placeholder hop for an unparsed "choose"
      clause (Animal Magnetism / Selective Adaptation's chosen-from-
      revealed-set selection) — resolves to a ``ChangeZone`` tagged
      ``origin="Graveyard"``. Both ``Dig``/``RevealTop`` are LIBRARY-only
      actions (neither tag ever reads from a graveyard), so this
      ``origin`` value can never be a truthful move-origin for the kept
      card; corpus-consistent across all three known carriers, it is
      phase's own marker that the un-kept remainder of this look/reveal
      goes to the graveyard — the "rest into your graveyard" clause the
      parse otherwise drops as unrepresented. Bounded to a short
      ``Unimplemented``-only hop chain (not an unbounded downstream
      walk) so an UNRELATED later reanimation effect chained via
      ``SequentialSibling`` after a genuinely rest-elsewhere Dig can't
      be mistaken for this marker.

    task #np_gyfam adds a SIXTH arm for a mis-tagged ``RevealHand`` node
    (Corpse Appraiser's "look at the top three cards of your library, then
    put one of those cards into your hand and the rest into your graveyard"
    parses as a ``RevealHand`` EFFECT, not the ``Dig``/``RevealTop`` shape
    above — WRONG-CONTENT, see the arm's own comment for the structural
    tell + corpus sweep), and extends the ``Dig``/Controller arm with a
    text-confirmed fallback for a DROPPED ``rest_destination`` (Rowan's Grim
    Search — phase leaves the field ``None`` rather than "Graveyard", though
    the Dig node itself parses correctly; see that arm's own comment for the
    exact-phrase gate + 155-card corpus sweep).
    """
    for c in tree.effect_concepts("mill"):
        if getattr(c.node, "destination", None) != "Graveyard":
            continue
        if c.scope == "opponents":
            continue
        return True
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Dig":
                continue
            if tag_of(getattr(n, "player", None)) != "Controller":
                continue
            if getattr(n, "rest_destination", None) == "Graveyard":
                return True
            # task #np_gyfam: Rowan's Grim Search's Dig carries NO
            # ``rest_destination`` at all (None, not "Graveyard") — the
            # "and the rest into your graveyard" clause is dropped from the
            # typed field entirely, though the Dig node itself (count/
            # keep_count/player) parses correctly. Text-confirmed fallback
            # on the SAME unit's own description (never whole-card), gated
            # on the exact phrase so an unrelated Dig whose "rest" goes
            # elsewhere (155-card corpus sweep of every ``rest_destination
            # is None`` Controller-scoped Dig: most put the rest on top/
            # bottom of library or exile it; only Underrealm Lich shares
            # this exact phrase, already covered by the look/keep-one arm
            # above) can't misfire.
            if getattr(n, "rest_destination", None) is None:
                desc = getattr(unit.node, "description", "") or ""
                if _DIG_REST_GRAVEYARD_RE.search(desc):
                    return True
    for c in tree.effect_concepts("change_zone"):
        if getattr(c.node, "destination", None) != "Graveyard":
            continue
        if c.scope == "opponents":
            continue
        tgt = tag_of(getattr(c.node, "target", None))
        if tgt in ("TrackedSet", "TrackedSetFiltered"):
            return True
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "Mill":
                if getattr(n, "destination", None) != "Graveyard":
                    continue
                # ``target`` is a bare PlayerRef tag for a self-mill
                # (``{"type": "Controller"}``) but a ``Typed`` filter
                # carrying ``controller: "Opponent"`` for a TARGETED
                # opponent mill ("Target opponent mills seven cards" —
                # Mind Sculpt) — :func:`explicit_recipient_scope` is the
                # general reader for both shapes (the SAME one
                # :func:`_effect_scope`/``_decorate_effect`` uses to
                # compute the DECORATED ``c.scope`` the bare-``Mill`` arm
                # above reads); a bare ``tag_of`` read here would miss
                # the ``Typed`` shape entirely and over-fire on every
                # targeted-opponent mill card.
                if explicit_recipient_scope(n) == "opponents":
                    continue
                # A GRANTED trigger's ``target: Controller`` is REBOUND
                # by the OWNING wrapper's own ``player_scope: Opponent``
                # (Imperious Mindbreaker's paired-creature grant: "each
                # opponent mills cards equal to its toughness" — the
                # Mill's own ``target`` reads "Controller" relative to
                # the per-opponent rotation, not this card's controller).
                # This Mill is reachable ONLY via the raw deep walk (a
                # GrantTrigger body nested inside a static's
                # ``modifications`` list — not one of ``_EFFECT_CHILD_
                # FIELDS``, so :func:`effect_owner_player_scope`'s own
                # ancestor walk can't reach it either); a direct identity
                # scan for the wrapper whose ``.effect`` IS this node is
                # the narrow fallback.
                owner_scope = None
                for w in iter_typed_nodes(unit.node):
                    if getattr(w, "effect", None) is n:
                        owner_scope = tag_of(getattr(w, "player_scope", None))
                        break
                if owner_scope == "Opponent":
                    continue
                return True
            if t is not None:
                continue
            # Dig/RevealTop -> (skip Unimplemented hops) -> ChangeZone(
            # origin=Graveyard) marker (see module docstring): ``n`` here
            # is the untagged ability WRAPPER (``Dig``/``RevealTop`` are
            # its ``.effect``, the chain continues on the WRAPPER's own
            # ``.sub_ability``, never a field of the ``Dig``/``RevealTop``
            # payload itself).
            eff = getattr(n, "effect", MISSING)
            if not (
                isinstance(eff, TypedMirrorNode) and tag_of(eff) in ("Dig", "RevealTop")
            ):
                continue
            if tag_of(getattr(eff, "player", None)) != "Controller":
                continue
            step = getattr(n, "sub_ability", None)
            hops = 0
            while (
                isinstance(step, TypedMirrorNode)
                and tag_of(getattr(step, "effect", None)) == "Unimplemented"
                and hops < 3
            ):
                step = getattr(step, "sub_ability", None)
                hops += 1
            step_eff = getattr(step, "effect", None) if step is not None else None
            if (
                isinstance(step_eff, TypedMirrorNode)
                and tag_of(step_eff) == "ChangeZone"
                and getattr(step_eff, "origin", None) == "Graveyard"
            ):
                return True
    # task #np_gyfam: a MIS-TAGGED ``RevealHand`` node (Corpse Appraiser's
    # "look at the top three cards of your library, then put one of those
    # cards into your hand and the rest into your graveyard" — phase parses
    # this Dig-shaped look/keep-one/mill-rest idiom as a ``RevealHand``
    # effect, WRONG-CONTENT: its own ``target`` names an ``InZone(Library)``
    # filter, which a genuine hand-reveal (CR 402.3, always a HAND-zone
    # recipient) can never carry — that mismatch IS the tell. Gated on BOTH
    # the structural mismatch AND the unit's own description naming
    # "graveyard" (corpus-swept: every ``RevealHand`` targeting a Library
    # filter — Descendant of Soramaro's unrelated "look at the top X ...
    # put them back in any order" scry-adjacent ability is the one other
    # hit, and its description never mentions a graveyard at all, so the
    # text gate excludes it cleanly).
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) != "RevealHand":
                continue
            if "Library" not in filter_inzone_zones(getattr(c.node, "target", None)):
                continue
            desc = (getattr(unit.node, "description", "") or "").lower()
            if "graveyard" in desc:
                return True
    return False


# ADR-0038 W4 giant (graveyard_matters): the opponent-owned-graveyard tell
# legacy's OWN raw-text zone recovery reads (byte-identical to the deleted
# ``_GY_OPP`` producer in the deleted _signals_ir.py). Phase sometimes DROPS the
# ownership qualifier entirely off a graveyard-target filter it otherwise
# parses identically to a self-graveyard reference (Scion of Darkness /
# Ink-Eyes, Servant of Oni / Sepulchral Primordial's "target creature card
# from THAT PLAYER's graveyard" carries the SAME bare
# ``{controller: None}`` typed filter shape as Reya Dawnbringer's "…from
# YOUR graveyard") — an unrecoverable phase-parse gap this text veto
# patches at the unit-description granularity (CR 400.7).
_GY_OPP_RE = re.compile(
    r"\b(?:opponent'?s?|their|each (?:player|opponent)'?s?|that player'?s?"
    r"|target (?:player|opponent)'?s?) graveyard\b",
    re.IGNORECASE,
)

# ADR-0038 W5b — byte-identical to the deleted ``_graveyard_count_markers``
# producer's own oracle-fallback anchor (``_card_ir/project.py``): the
# ALL-GRAVEYARDS count idiom (CR 400.1 — the value scales with the
# graveyard population), NOT a recursion ("return a card from your
# graveyard" has no "number of"). The leading "number of" can be preceded
# by "equal to the" / "plus the" / "one plus the"; an intervening "named
# X" / type clause (creature cards, cards named Y) is allowed before
# "in … graveyard".
_GY_COUNT_PHRASE_RE = re.compile(
    r"\bnumber of\b[^.]*?\bcards?\b[^.]*?\bin (?:all|your|their|its owner's|each "
    r"player'?s?|a|the)? ?graveyards?\b"
    r"|\b(?:ten|two|three|four|five|six|seven|eight|nine|\d+) or more [^.]*?cards?"
    r"[^.]*?\bin (?:all|your|their|each player'?s?|a|the)? ?graveyards?\b",
    re.IGNORECASE,
)


def _gy_player_scope(player_tag: str | None) -> str | None:
    """The you/opponents/ambiguous read of a count operand's player-scope
    tag. ``Opponent``/``Opponents`` -> 'opponents' (``GraveyardSize.player``
    carries a nested singular ``Opponent`` tag read via :func:`tag_of`;
    ``ZoneCardCount.scope`` / ``DistinctCardTypes``'s ``Zone.scope`` carry
    the PLURAL bare string ``'Opponents'`` — Wight of Precinct Six,
    Consuming Aberration, Nighthawk Scavenger, Detritivore all use the
    plural form); ``None``/``Controller``/``All`` (no explicit owner, or
    an explicit "all graveyards" — Mortivore) -> the self-graveyard
    default 'you'; any OTHER tag (``ScopedPlayer`` — Angrath, the
    Flame-Chained's "[-8]: each opponent loses life equal to the number
    of cards in THEIR graveyard", scoped by the ability's own
    ``player_scope: Opponent``, not this operand; ``TargetPlayer``) is a
    genuinely AMBIGUOUS owner this narrow structural read can't resolve on
    its own -> ``None``, deferring to the byte-mirror's clause-text scope
    resolution.
    """
    if player_tag in ("Opponent", "Opponents"):
        return "opponents"
    if player_tag in (None, "Controller", "All"):
        return "you"
    return None


def _gy_unwrap_scalar(node: object) -> object:
    """Unwraps a scaling-scalar wrapper (``Offset`` — Nighthawk Scavenger's
    "1 plus the number of card types…"; ``Multiply`` — Silent-Chant
    Zubera's "2 life for each Zubera that died") down to the ``Ref`` it
    wraps, so a count-operand arm can read the SAME ``Ref`` shape
    regardless of whether the value carries a flat modifier. Returns
    ``node`` unchanged when it isn't one of these two wrapper tags
    (already a bare ``Ref``, or unrelated)."""
    t = tag_of(node)
    if t in ("Offset", "Multiply"):
        return getattr(node, "inner", None)
    return node


def _gy_count_ref_scope(node: object) -> str | None:
    """The player scope of a graveyard-zone COUNT/THRESHOLD operand tag
    (``ZoneCardCount`` / ``GraveyardSize`` / ``DistinctCardTypes`` /
    ``ZoneCardCountAtLeast`` / ``ZoneChangeCountThisTurn``), or ``None``
    when ``node`` isn't one or its zone isn't ``Graveyard``.
    Delve/threshold/delirium/"X = cards in a graveyard" key off one of the
    first four (CR 400.7): a dynamic P/T scaler (Mortivore, Splinterfright
    — ``SetDynamicPower``/``…Toughness`` ``value``), a scaling effect
    amount (Ancestor's Chosen's ``GainLife``), a Delirium condition
    (``DistinctCardTypes`` over a graveyard ``Zone`` source — Grim
    Flayer), or a Threshold activation/condition gate
    (``ZoneCardCountAtLeast`` / a bare ``GraveyardSize`` comparison —
    Nantuko Monastery, Mindwhisker). Morbid ("if a creature died this
    turn") keys off ``ZoneChangeCountThisTurn`` with ``to: Graveyard``
    (CR 700.4's "dies" IS a battlefield→graveyard move — Scavenging
    Ghoul, Morkrut Banshee) — carries no scope/player field, always
    'you' (the state is board-wide, but the payoff is the controller's).
    An explicit ``Opponent`` scope/player on the other four routes to
    'opponents' (GY-hate count); else the self-graveyard default 'you'
    (``ZoneCardCountAtLeast`` carries no scope field at all — CR
    Threshold templating is always about YOUR graveyard).
    """
    t = tag_of(node)
    if t == "ZoneCardCount":
        if getattr(node, "zone", None) != "Graveyard":
            return None
        return _gy_player_scope(getattr(node, "scope", None))
    if t == "GraveyardSize":
        return _gy_player_scope(tag_of(getattr(node, "player", None)))
    if t == "DistinctCardTypes":
        src = getattr(node, "source", None)
        if tag_of(src) != "Zone" or getattr(src, "zone", None) != "Graveyard":
            return None
        return _gy_player_scope(getattr(src, "scope", None))
    if t == "ZoneCardCountAtLeast":
        if getattr(node, "zone", None) != "Graveyard":
            return None
        return "you"
    if t == "ZoneChangeCountThisTurn":
        if getattr(node, "to", None) != "Graveyard":
            return None
        return "you"
    return None


def _gy_filter_scope(filt: object) -> str | None:
    """The graveyard-ownership scope of a target/count filter (CR 400.7),
    or ``None`` when no scope can be read off it structurally. A
    graveyard-restricted filter names its owner via the ``Owned`` property
    (Ashen Powder, Puppeteer Clique, Agadeem Occultist all carry
    ``Owned: Opponent`` — the "from an opponent's graveyard" tell), NOT the
    top-level ``controller`` field (which for many of these is ``None`` —
    "under YOUR control" describes the DESTINATION, not the graveyard's
    owner); ``controller`` is the fallback for a filter with no ``Owned``
    property (Reya Dawnbringer's ``controller: You``). An ``Owned`` value
    OTHER than You/Opponent (``TargetPlayer`` — Krosan Reclamation's
    "target player['s graveyard]"; ``ScopedPlayer`` — Exhume's "each
    player['s graveyard]") is a genuinely AMBIGUOUS owner no explicit scope
    can be read off structurally — returns ``None``, deferring to the
    LAST-RESORT byte-mirror's own clause-text scope resolution. A filter
    with NEITHER an ``Owned`` property NOR a ``controller`` at all defaults
    to the self-graveyard 'you' (Reito Lantern/Phyrexian Archivist's bare
    "target card from a graveyard", no possessive) — UNLESS the filter is
    an ``Or``/``And`` compound (Pulse of Murasa's "creature OR land card
    from a graveyard"): legacy's own zone-tag recovery doesn't reach a
    compound filter's implicit ownership, so a compound filter with no
    EXPLICIT owner also returns ``None`` here, matching that gap rather
    than manufacturing a 'you' legacy never emits.
    """
    owned = filter_owned_controller(filt)
    if owned == "Opponent":
        return "opponents"
    if owned == "You":
        return "you"
    if owned is not None:
        return None
    ctrl = filter_controller(filt)
    if ctrl == "Opponent":
        return "opponents"
    if ctrl == "You":
        return "you"
    return "you" if tag_of(filt) == "Typed" else None


def _graveyard_matters(tree: ConceptTree) -> list[Signal]:
    """graveyard_matters — the cares-about PAYOFF (CR 404 / 701.17a). Nine
    arms, structural-first:

    * **trigger zone-movement** — a trigger watching cards ENTERING a
      graveyard from a non-battlefield zone (including an EXPLICITLY
      unrestricted "from anywhere" arrival, ``origin is None`` — Kozilek,
      Tezzeret's Touch), or LEAVING a graveyard (Syr Konrad-class), read
      off the trigger's typed ``origin`` / ``destination``. Only the
      EXPLICIT battlefield→graveyard ``dies`` movement
      (``origin == 'Battlefield'``) is a death payoff (a different
      lane), excluded (CR 700.4).
    * **trigger subject-in-graveyard** — a trigger whose own watched
      SUBJECT is restricted IN a graveyard ("whenever a card in your
      graveyard is turned face up" — Veteran Ghoulcaller), read off the
      trigger node's own filter.
    * **effect target/origin in a graveyard** — any effect (reanimate,
      recursion, a copy/return/cast/count TARGET restricted to a
      graveyard — Reya Dawnbringer, Gravedigger, Surgical Extraction,
      Daring Waverider's ``cast_from_zone``) EXCEPT a ``ChangeZone``/
      ``ChangeZoneAll`` whose destination is Exile — a graveyard-hate
      exile or blink stays ``graveyard_makers`` only (CR 406.2), never
      this lane.
    * **graveyard-fuel activation cost** — "Exile this card from your
      graveyard: …" (Seasoned Pyromancer's 2nd ability, Renew) — a typed
      ``Exile`` cost leaf whose zone is Graveyard (CR 702.66a's delve
      idiom, generalized to any activation cost); OR a Craft
      ``ExileMaterials`` cost (CR 702.167a) whose ``materials`` filter
      names a graveyard card as valid fuel (Ore-Rich Stalactite, Tetzin,
      Braided Net).
    * **graveyard-zone count/threshold operand** — :func:`_gy_count_ref_scope`
      over an effect's own amount/count/value field (never forces 'you'
      on its own); the SAME read over a static's P/T-scaling
      ``modifications`` field ALWAYS ALSO forces 'you' (a static value
      never reaches the legacy per-effect zone-tagging pass this lane
      mirrors, so its raw fallback separately, unconditionally fires
      'you' even for an opponents'-graveyard scaler — Wight of Precinct
      Six, Consuming Aberration, Nighthawk Scavenger, Detritivore); a
      condition/activation-restriction gate ALSO always forces 'you'
      (Grim Flayer, Nantuko Monastery) — a cost-REDUCTION
      (``ModifyCost``) or evasion-GRANT (``CanAttackWithDefender``)
      static is excluded here (the mirrored old IR never builds a
      ``Condition`` object for either static-mode at all).
    * **``_graveyard_count_markers`` deep-scan fallback** (CR 400.1) —
      GATED on no earlier arm having fired anything for this card: a
      genuine typed count node (``ZoneCardCount``/``GraveyardSize``/
      ``DistinctCardTypes``/``ZoneCardCountAtLeast``) reachable ANYWHERE
      on the card, even a site the condition-gate arm above structurally
      excludes (Avatar of Woe's ModifyCost condition resolves 'you';
      Expedition Lookout's CanAttackWithDefender condition resolves
      'opponents'), fires its OWN resolved scope; failing that,
      :data:`_GY_COUNT_PHRASE_RE` over the whole face oracle — the
      Shrine cycle's "X is the number of cards in all graveyards with
      the same name as that spell" strands the count in a free-text
      ``Variable`` with no typed node at all — fires 'you'.
    * **LAST RESORT — the byte-identical deleted-producer per-clause
      mirror** (:func:`_graveyard_matters_clauses`) over the
      reminder-stripped oracle, for the broad "graveyard"-word narrative
      mention the typed substrate carries no node for at all (Unfinity
      sticker idioms — Clandestine Chameleon, Roxi, Publicist to the
      Stars — park as ``Unimplemented`` residue with no allowlisted
      grammar token). No per-clause exclusion for '"Name Sticker"
      Goblin's "enters from anywhere OTHER THAN a graveyard or exile"
      idiom (ADR-0038 W5b re-adjudication, corpus-verified): legacy's
      own mirror invocation carries no such filter and DOES fire
      ``you`` for it.

    The dredge / delve / scavenge keyword payoffs ride the shared
    ``_keyword_field_signals`` field-lookup (CR 702.52a / 702.66a),
    upstream of this function.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("graveyard_matters", scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        node = unit.node
        if unit.origin == "trigger":
            origin = getattr(node, "origin", None)
            dest = getattr(node, "destination", None)
            # ADR-0038 W5b: ``origin is None`` is phase's shape for an
            # EXPLICITLY unrestricted "from anywhere" arrival (Kozilek /
            # Ulamog's "is put into a graveyard from anywhere", Tezzeret's
            # Touch's "enchanted artifact is put into a graveyard" — no
            # origin qualifier at all) — the OPPOSITE of a plain "dies"
            # trigger, which phase tags with an EXPLICIT
            # ``origin='Battlefield'`` (Silent-Chant Zubera; CR 700.4). Only
            # the explicit-battlefield shape is a pure death payoff (a
            # different lane), excluded here; ``origin is None`` is
            # unrestricted and thus INCLUDES a battlefield-to-graveyard
            # move, so it stays in (CR 400.7).
            gy_arrival = dest == "Graveyard" and origin != "Battlefield"
            gy_departure = origin == "Graveyard"
            if gy_arrival or gy_departure:
                fire(_gy_scope(trigger_subject_scope(node)), "")
            subj = effect_filter(node)
            if subj is not None and "Graveyard" in filter_inzone_zones(subj):
                fire(_gy_scope(trigger_subject_scope(node)), "")

        for c in unit.effects:
            enode = c.node
            if tag_of(enode) in ("ChangeZone", "ChangeZoneAll"):
                _, dest = change_zone_dirs(enode)
                if dest == "Exile":
                    continue
            # ADR-0038 W6 endgame: a ``ChooseFromZone`` reading a graveyard
            # (Dawnbreak Reclaimer's "choose a creature card in an
            # opponent's graveyard, then that player chooses a creature
            # card in your graveyard") carries its zone on its OWN
            # top-level ``zone``/``zone_owner`` fields, not inside a
            # ``.filter``/``.target`` sub-node ``effect_filter`` reads (its
            # own ``.filter`` is a bare type-only filter with no ``InZone``
            # property at all) — an UNAMBIGUOUS owner tag (``Opponent`` —
            # the SAME ``_gy_player_scope`` mapper the count-operand arms
            # already use), so this reads cleanly with no text-fallback
            # needed. CR 404.1.
            if (
                tag_of(enode) == "ChooseFromZone"
                and getattr(enode, "zone", None) == "Graveyard"
            ):
                sc = _gy_player_scope(getattr(enode, "zone_owner", None))
                if sc is not None:
                    fire(sc, c.raw)
                continue
            filt = effect_filter(enode)
            # A GENUINE target/origin-in-graveyard read is ALWAYS carried on
            # a TARGET FILTER's ``InZone`` property (Reya Dawnbringer,
            # Gravedigger, Extract from Darkness all carry one) — a bare
            # ``SelfRef`` target (Unearth/Fatestitcher's own "return THIS
            # card" self-recursion, no search involved) carries no filter to
            # read, so it correctly stays OUT (that keyword rides
            # ``graveyard_makers`` only, never this lane — matching the
            # keyword-table split).
            if filt is None or "Graveyard" not in filter_inzone_zones(filt):
                continue
            sc = _gy_filter_scope(filt)
            if sc == "you" and _GY_OPP_RE.search(
                getattr(node, "description", "") or ""
            ):
                sc = "opponents"
            if sc is not None:
                fire(sc, c.raw)

        for c in unit.costs:
            for leaf in iter_cost_leaves(c.node):
                if (
                    tag_of(leaf) == "Exile"
                    and getattr(leaf, "zone", None) == "Graveyard"
                ):
                    fire("you", "")
                # ADR-0038 W5b (CR 702.167a) — Craft: "Craft with
                # [materials] [cost]" means "…, Exile [materials] from
                # among permanents you control and/or cards in your
                # graveyard: Return this card to the battlefield
                # transformed…". phase models this as an
                # ``ExileMaterials`` cost whose ``materials`` is a filter
                # tree (an Or-of-Ors on Ore-Rich Stalactite / Tetzin,
                # Gnome Champion) — the SAME ``InZone`` shape
                # ``filter_inzone_zones`` already reads for a target
                # filter. A materials filter naming a graveyard card as
                # valid crafting fuel is a genuine graveyard-fuel
                # activation cost, the same lane the bare ``Exile`` leaf
                # above covers for delve/escape/Renew; a Craft whose
                # materials are battlefield-only never reaches this arm.
                elif tag_of(leaf) == "ExileMaterials":
                    mats = getattr(leaf, "materials", None)
                    if "Graveyard" in filter_inzone_zones(mats):
                        fire("you", "")

        # A graveyard-zone count operand on a DIRECT effect's own
        # amount-bearing field (Scavenging Ghoul's ``PutCounter.count`` =
        # Ref(ZoneChangeCountThisTurn); Ancestor's Chosen's
        # ``GainLife.amount``; Silent-Chant Zubera's ``GainLife.amount`` =
        # Multiply(2, Ref(ZoneChangeCountThisTurn)) — unwrapped by
        # :func:`_gy_unwrap_scalar`). Checked on the node's OWN field
        # only — NOT the whole ability subtree — so a value-SELECTOR
        # nested under a sibling effect (Brimstone Volley/Life Goes On's
        # Morbid "instead" alternate value) never reaches this arm.
        for c in unit.effects:
            for fname in ("amount", "count", "value"):
                q = _gy_unwrap_scalar(getattr(c.node, fname, None))
                if tag_of(q) != "Ref":
                    continue
                sc = _gy_count_ref_scope(getattr(q, "qty", None))
                if sc is not None:
                    fire(sc, c.raw)

        # ADR-0038 W5b — the SAME count-operand read, over a STATIC's own
        # P/T-scaling ``modifications`` field (Mortivore/Splinterfright's
        # ``SetDynamicPower.value``; Wight of Precinct Six's
        # ``AddDynamicPower.value``; Consuming Aberration / Detritivore's
        # opponents'-graveyard scalers; Nighthawk Scavenger's
        # ``SetDynamicPower.value`` = Offset(1, Ref(DistinctCardTypes))
        # for the "1 plus …" phrasing — unwrapped). ALWAYS ALSO fires
        # 'you' — a static ability's continuous P/T value never reaches
        # legacy's per-effect zone-tagging pass at all (only an EFFECT's
        # amount/count/value keys are scanned, never a static
        # MODIFICATION's), so legacy's own raw graveyard-mention fallback
        # separately, unconditionally fires 'you' for a P/T scaler — even
        # an opponents'-graveyard one (Wight / Consuming Aberration /
        # Nighthawk / Detritivore all fire BOTH 'you' (forced) and
        # 'opponents' (the field's own scope) in legacy). CR 400.7.
        for c in unit.statics:
            for fname in ("amount", "count", "value"):
                q = _gy_unwrap_scalar(getattr(c.node, fname, None))
                if tag_of(q) != "Ref":
                    continue
                sc = _gy_count_ref_scope(getattr(q, "qty", None))
                if sc is not None:
                    fire("you", "")
                    fire(sc, c.raw)

        # A graveyard-zone count/threshold tag GATING this unit (Threshold/
        # Delirium/Morbid CONDITION — Grim Flayer, Nantuko Monastery,
        # Mindwhisker, Descend upon the Sinful) — the unit's OWN top-level
        # ``condition`` / ``activation_restrictions`` field, un-nested (so a
        # sibling sub-ability's alternate-value "instead" condition never
        # reaches this arm either, nor does a REPLACEMENT effect's own
        # ``OnlyIfQuantity`` Morbid gate — Festerhide Boar's "enters with
        # two +1/+1 counters if a creature died this turn" is a
        # ``replacement`` unit; legacy's condition-zone arm reads only
        # ``Ability.condition``, which a replacement effect never carries).
        # ALWAYS also fires 'you' — legacy's condition-zone arm carries no
        # opponent branch at all (a STATE CHECK over an opponent's
        # graveyard still enables YOUR OWN payoff — Jace's Phantasm's
        # "+4/+4 as long as an opponent has ten or more cards in their
        # graveyard" fires BOTH 'you' (forced) and 'opponents' (the
        # field's own scope)). A cost-REDUCTION static (``ModifyCost`` —
        # Bone Picker's "costs {3} less … if a creature died this turn")
        # or an evasion-GRANT static (``CanAttackWithDefender`` —
        # Expedition Lookout) is excluded from THIS arm specifically: the
        # old IR this lane mirrors never builds an ``Ability``/
        # ``.condition`` object for either static-mode at all (a
        # structural blind spot in the mirrored substrate, not a
        # content-based exclusion). Bone Picker's Morbid marker carries no
        # literal "graveyard" word, so it never fires graveyard_matters at
        # all — but Expedition Lookout's condition DOES carry a genuine
        # graveyard count (``GraveyardSize``), which legacy's SEPARATE
        # ``_graveyard_count_markers`` raw deep-scan (unlike this arm,
        # gated on no PRECEDING ``.condition`` object rather than on the
        # static's kind) still reaches directly — verified against a
        # direct run of the deleted ``extract_signals_ir``: legacy fires
        # ``('graveyard_matters', 'opponents')`` for it, via the SAME
        # marker single-scope read the deep-scan arm below reproduces.
        # Avatar of Woe's ModifyCost gate over a LITERAL graveyard-count
        # ("ten or more creature cards total in all graveyards") resolves
        # 'you' (not 'opponents') through that identical deep-scan arm.
        if unit.origin != "replacement" and static_mode_tag(node) not in (
            "ModifyCost",
            "CanAttackWithDefender",
        ):
            ars = getattr(node, "activation_restrictions", None)
            cond = getattr(node, "condition", None)
            for site in (ars, cond):
                for n in iter_typed_nodes(site):
                    sc = _gy_count_ref_scope(n)
                    if sc is not None:
                        fire("you", "")
                        fire(sc, "")

    # ADR-0038 W5b — the deleted ``_graveyard_count_markers`` producer's
    # raw fallback (CR 400.1): a count/cost gate over "cards … in all
    # graveyards" phase left stranded with NO typed count node the
    # arms above can reach at all — the Shrine cycle's "X is the number
    # of cards in all graveyards with the same name as that spell"
    # strands the count in a free-text ``Variable`` qty (no InZone node
    # to read); Avatar of Woe's ModifyCost / Expedition Lookout's
    # CanAttackWithDefender conditions carry a genuine ``ZoneCardCount``/
    # ``GraveyardSize`` the condition-gate arm above structurally
    # excludes for BOTH static-modes (matching the old IR's own blind
    # spot for that arm specifically) — this deep-scan walks the WHOLE
    # unit node (not gated on static-mode at all), matching the
    # producer's own raw-record walk, so it still reaches both: Avatar
    # of Woe resolves 'you' (``scope='All'``), Expedition Lookout
    # resolves 'opponents' (``player=Opponent``) — a single scope each,
    # verified against a direct run of the deleted ``extract_signals_ir`` for both.
    # GATED
    # on ``not seen`` (mirrors the producer's own
    # ``has_struct`` gate — it returns NOTHING when any OTHER effect on
    # the card already carries an in:graveyard zone tag, i.e. when an
    # earlier arm in this function already fired): Into the Story's
    # GraveyardSize(player=Opponent) ModifyCost condition resolves
    # 'opponents' ONLY here (a single scope, matching the producer's
    # own ``_graveyard_count_player`` read) — never ALSO 'you', unlike
    # the unconditional double-fire a genuine ``Ability.condition`` raw
    # zone-tag carries in the arm above. A card whose graveyard
    # reference the earlier arms already covered (Geth, Lord of the
    # Vault's Owned=Opponent target filter) never reaches this one.
    # The oracle-regex fallback additionally requires ``not gy_covered``
    # (no count-SHAPED node anywhere at all, resolved or not):
    # ``TargetZoneCardCount`` (Eldritch Pact / Riverchurn Monument's "X
    # is the number of cards in THEIR graveyard", target-dependent —
    # unresolvable here, CR 400.7) and a ``ScopedPlayer``-owned
    # ``ZoneCardCount`` (Angrath, the Flame-Chained's "-8", scoped by
    # the ability's own player_scope, not this operand — genuinely
    # ambiguous) both carry a REAL count node the mirrored old IR's own
    # per-effect zone-tagging ALSO reaches (``has_struct`` — matching
    # the producer's actual gate, not just its narrower typed
    # discriminator), so the oracle fallback must stay silent for them
    # too, even though neither resolves a concrete scope on its own.
    if not seen:
        gy_scope: str | None = None
        gy_covered = False
        for u2 in tree.units:
            for n in iter_typed_nodes(u2.node):
                if tag_of(n) not in (
                    "ZoneCardCount",
                    "GraveyardSize",
                    "DistinctCardTypes",
                    "ZoneCardCountAtLeast",
                    "TargetZoneCardCount",
                ):
                    continue
                gy_covered = True
                sc = _gy_count_ref_scope(n)
                if sc == "opponents":
                    gy_scope = "opponents"
                    break
                if sc == "you" and gy_scope is None:
                    gy_scope = "you"
            if gy_scope == "opponents":
                break
        if (
            gy_scope is None
            and not gy_covered
            and _GY_COUNT_PHRASE_RE.search(tree.oracle or "")
        ):
            gy_scope = "you"
        if gy_scope is not None:
            fire(gy_scope, "")

    # ADR-0038 W5b (session re-adjudication, corpus-verified): the W4
    # giant's own per-clause exclusion of '"Name Sticker" Goblin's
    # "enters from anywhere OTHER THAN a graveyard or exile" clause was
    # an UNVERIFIED judgment call — legacy's actual mirror invocation
    # (the deleted ``_signals_ir.py``'s call to :func:`_graveyard_matters_clauses`)
    # passes the WHOLE ``kept_oracle`` with no such exclusion filter at
    # all, and a direct run of the deleted ``extract_signals_ir`` over the real card
    # confirms legacy DOES fire ``('graveyard_matters', 'you')`` for it
    # (CR 400.7: a card whose own ETB trigger is gated on NOT arriving
    # from a graveyard still mechanically references the zone). No
    # exclusion filter, matching legacy byte-for-byte.
    for _gy_key, _gy_scope_v in _graveyard_matters_clauses(
        " ".join(_clauses(_kept(tree))), tree.name
    ):
        fire(_gy_scope_v, "")

    return out


def _fight_makers(tree: ConceptTree) -> list[Signal]:
    """fight_makers — a fight DOER (CR 701.12 -- the shared 701.14a "each
    other" wording is the OLD number). Three structural arms, then a
    whole-card residue fallback:

    * **typed (flat)** — a top-level ``Fight`` effect (Prey Upon, Ulvenwald
      Tracker).
    * **allowlisted residue** — an Unimplemented "~ fights ..." clause the
      grammar's "fight" ``SIMPLE_VERB`` token recovers (Gimli, Mournful
      Avenger's third-resolution rider; Summon: Magus Sisters' "Fight!"
      modal bullet), via :data:`recovery.ALLOWLIST`.
    * **nested (granted)** — a ``Fight`` tag buried inside a GRANTED
      trigger (Cherished Hatchling, Grothama's "Other creatures have"),
      a granted activated ability (Setessan Tactics), a ``CreateEmblem``
      (Kiora, Master of the Depths), a token-copy exception clause
      (Aggressive Biomancy, Mythos of Illuna), or a chained sub_ability's
      "Otherwise" branch (Tunnel of Love's "the chosen creatures fight
      each other", a ``ParentTarget``-scoped Fight the flat concept-node
      walk never surfaces) — :func:`has_nested_fight`.
    * **whole-card residue (no node at all)** — a fight clause phase drops
      WHOLLY (Tolsimir's "that creature fights up to one target creature"
      — the trigger's ``execute`` is a bare ``GainLife``, no sub_ability
      chain at all) reads ``tree_synthesis._arm_fight_makers``'s
      synthesized "fight" node (the legacy ``_FIGHT_RAW`` mirror
      relocated to gap-gated projection time, emitting the REAL concept
      per ADR-0038 — no synth_* marker, so the typed
      ``effect_concepts("fight")`` read above already covers it) — also
      the Aftermath-DFC single-face fallback, though a genuine SPLIT-card
      second half (Prepare // Fight) needs task #74's face union first;
      ``tree.oracle`` is single-face.

    Scope "you" (the lane convention)."""
    for c in tree.effect_concepts("fight"):
        return [Signal("fight_makers", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if has_nested_fight(unit.node):
            return [Signal("fight_makers", "you", "", "", tree.name, "high")]
    return []


def _goad_makers(tree: ConceptTree) -> list[Signal]:
    """goad_makers — a goad DOER (CR 701.15a). A ``Goad`` / ``GoadAll`` effect
    (Disrupt Decorum, Bloodthirster). Pure political force directed AT opponents →
    scope "opponents".

    Two W3 batch-3 (ADR-0038) bucket-B text-idiom bridges, both imported
    single-source (no new grammar) and read off ``_kept(tree)`` — phase
    carries no dedicated node for either surface, only the raw clause:

    * ``_GOAD_STYLE_FORCE`` (CR 701.15b) — the force_attack→goad
      single-target bridge ("target creature … attacks … if able" —
      Alluring Siren, Boiling Blood, Basandra's activated form): a targeted
      compulsion is the goad mechanic's doer even when phase types it as a
      generic ``ForceAttack``/Unimplemented clause, not a dedicated Goad
      effect. Gated per-clause by :func:`_attack_compulsion_hit` — the SAME
      ForceBlock false positive :func:`_forced_attack` excludes (Avalanche
      Tusker's "attacks, target creature … blocks it … if able" is CR
      509.1c provoke, not goad).
    * ``_GOAD_REWARD_REF`` (CR 701.15b's "attacks a player other than …"
      redirect) — the goad REWARD/payoff idiom ("whenever a(nother) player
      attacks one of your opponents …" — Gahiji, Breena, Frontier
      Warmonger, Kazuul): a card that REWARDS a goaded-style redirect wants
      goad effects, so it rides the same key (legacy's
      ``_DOER_EFFECT_KEYS["goad_all"] -> ("goad_makers", "opponents")``).
    """
    for c in tree.effect_concepts("goad"):
        return [Signal("goad_makers", "opponents", "", c.raw, tree.name, "high")]
    kept = _kept(tree)
    if _attack_compulsion_hit(kept, _GOAD_STYLE_FORCE):
        return [Signal("goad_makers", "opponents", "", "", tree.name, "high")]
    if _GOAD_REWARD_REF.search(kept):
        return [Signal("goad_makers", "opponents", "", "", tree.name, "high")]
    return []


# ADR-0038 W3 batch 2 unit 7 — the regenerate_makers last-resort mirror
# (see the "Last-resort fallback" note on ``_regenerate_makers``).
_REGENERATE_WORD_RX = re.compile(r"\bregenerate", re.IGNORECASE)
_CANT_REGENERATE_RX = re.compile(r"can't[^.]{0,30}regenerate", re.IGNORECASE)


def _regenerate_makers(tree: ConceptTree) -> list[Signal]:
    """regenerate_makers — a regeneration shield (CR 701.19a). A ``Regenerate`` effect
    (River Boa, Troll Ascetic). A "can't be regenerated" clause is the INVERSE (a flag
    on a ``Destroy``, NOT a ``Regenerate`` effect — Pongify), so it never reaches here.

    ADR-0038 W3 batch 2 unit 7: a GRANTED "'{cost}: Regenerate this
    creature/permanent'" — a ``GrantAbility`` modification whose
    ``definition.effect`` is a ``Regenerate`` — at ANY nesting depth
    (:func:`iter_typed_nodes`'s generic deep walk): a tribal lord static
    (Clot Sliver's "All Slivers have …"), an Aura's static (Trollhide's
    "Enchanted creature … has …"), a spell's one-shot GenericEffect grant
    (Resuscitate's "creatures you control gain … until end of turn"), a
    conditional static (Villainous Ogre's "as long as you control a
    Demon"), or an animated land (Spawning Pool). The bearer's OWN
    top-level ``Regenerate`` effect (River Boa) stays covered by the
    existing ``effect_concepts`` read.

    Last-resort fallback (checked only when the structural arms above find
    nothing): a bare "regenerate" mirror over the reminder-stripped
    oracle, excluding the "can't … regenerate" inverse (Pongify). Covers
    the residue phase drops entirely with no GrantAbility node at all —
    a kicker-conditional ETB grant whose execute chain captures only the
    counter half, silently dropping the "and with '{cost}: Regenerate …'"
    tail (Anavolver, Degavolver), a compound "become <color>, gets +X/+Y,
    and gains <ability>" clause phase can't parse (Defiling Tears — an
    Unimplemented residue with no typed Regenerate node), and a
    multi-conditional static whose trailing conjunct phase folds into an
    ``Unrecognized`` condition-text tail (Tribal Golem). Corpus-verified
    safe as a FALLBACK ONLY: nearly every "regenerate"-bearing
    commander-legal card already fires the structural arms above (267 of
    ~268 non-"can't"-excluded corpus hits), so this mirror only ever
    reaches the residual tail, never overrides a structural miss into a
    wrong key. Scope "you".
    """
    for c in tree.effect_concepts("regenerate"):
        return [Signal("regenerate_makers", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "GrantAbility":
                continue
            definition = getattr(n, "definition", None)
            if tag_of(getattr(definition, "effect", None)) == "Regenerate":
                return [Signal("regenerate_makers", "you", "", "", tree.name, "high")]
    kept = _kept(tree)
    if _REGENERATE_WORD_RX.search(kept) and not _CANT_REGENERATE_RX.search(kept):
        return [Signal("regenerate_makers", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W4 giants — a LAST-RESORT scope read off the CARD's own
# reminder-stripped oracle text, per-clause gated (boundary lesson iii — never
# whole-tree), for a ``LoseLife`` node that carries NO recipient field of its
# own AND no wrapper-owner edict actor: "Target player loses 1 life for each
# tapped artifact THEY control" (Burden of Greed), "that player loses 1 life
# for each artifact they control" (Emissary of Despair), "Target opponent
# loses 1 life for each attacking creature YOU control" (Foul-Tongue Shriek),
# a die-roll-table branch ("1—9 | Each opponent loses 2 life" — Herald of
# Hadar) — the recipient lives ONLY inside the amount's nested count filter (a
# sub-field neither :func:`lifeloss_recipient_scope` nor
# :func:`effect_owner_player_scope` reads) or inside a per-branch clause the
# OWNING unit's top-level ``description`` never repeats; the count filter's OWN
# controller is unreliable as a stand-in (Foul-Tongue Shriek's count filter
# names YOU, the caster, not the opponent who loses). Dan's
# detriment-directed-targeting convention (the same principle
# :func:`detriment_directed_scope` encodes elsewhere): an explicit "target/that
# opponent" or "target/that player" subject on an unambiguously detrimental
# effect (life loss, CR 119.3) reads opponent-directed for deck-building signal
# purposes; a clause opening with a bare "You" is a genuine self-loss. Scans
# the WHOLE card (not just the owning unit) because a nested LoseLife (a
# die-roll/modal branch) has no clause text of its own reachable from the
# node — the first LOSE-clause match wins, a narrow risk only for the rare
# card mixing a genuine self-loss AND an unresolved drain in different
# abilities.
_LIFELOSS_OPPONENT_TEXT_RX = re.compile(
    r"\b(?:target opponent|each opponent|that opponent|an opponent"
    r"|target player|that player)\b",
    re.IGNORECASE,
)
_LIFELOSS_SELF_TEXT_RX = re.compile(r"^\s*you\b", re.IGNORECASE)
_LIFELOSS_CLAUSE_RX = re.compile(r"\bloses?\b[^.|\n]*\blife\b", re.IGNORECASE)


def _lifeloss_text_scope(tree: ConceptTree, skip: int = 0) -> str | None:
    """The last-resort whole-card, per-clause scope fallback (see module
    comment above ``_LIFELOSS_OPPONENT_TEXT_RX``), or ``None`` when fewer than
    ``skip + 1`` clauses carry a self/opponent-directed marker.

    ``skip`` disambiguates a card with TWO structurally-unresolved LoseLife
    nodes of genuinely DIFFERENT scope (Feed the Infection: "you lose 3 life"
    self + a separate Corrupted rider "each opponent … loses 3 life" drain) —
    :func:`_lifeloss_makers` counts how many prior nodes already fell through
    to this fallback on the SAME tree and passes that count, so each node
    claims the NEXT unclaimed matching clause in oracle order rather than
    every node racing to the first."""
    kept = _kept(tree)
    seen = 0
    for clause in re.split(r"[.\n|]", kept):
        if not _LIFELOSS_CLAUSE_RX.search(clause):
            continue
        stripped = clause.strip()
        if _LIFELOSS_SELF_TEXT_RX.match(stripped):
            resolved = "you"
        elif _LIFELOSS_OPPONENT_TEXT_RX.search(stripped):
            resolved = "opponents"
        else:
            continue
        if seen == skip:
            return resolved
        seen += 1
    return None


def _lifeloss_scope(
    unit: AbilityUnit, node: TypedMirrorNode, tree: ConceptTree, text_skip: int = 0
) -> tuple[str, bool]:
    """The lifeloss-maker scope split (CR 119.3): a self-loss ("you lose N") → you; a
    drain ("each opponent / its controller / that player loses N") → opponents.
    Returns ``(scope, used_text_fallback)`` — the caller advances its running
    ``text_skip`` counter for EVERY node regardless of the second element (a
    structurally-resolved node still occupies its OWN clause's position in
    oracle order — Feed the Infection's first "you lose 3 life", target=
    Controller — so a LATER node's text search must skip past it); the flag
    is informational only.

    Direction comes from the ``LoseLife`` node's RECIPIENT, read structurally
    (:func:`lifeloss_recipient_scope`) — NOT from ``trigger_scope``, which phase
    MIS-scopes to ``you`` for an ability triggered off an OPPONENT's object (Archfiend
    of the Dross, Ashenmoor Liege — phase bug [P5]). When the node carries no
    recipient (Gray Merchant — the "each opponent loses" lives as ``player_scope`` on
    the trigger wrapper), reads the wrapper actor that OWNS this effect
    (:func:`effect_owner_player_scope`); when that ALSO carries nothing, the
    whole-card per-clause text idiom (:func:`_lifeloss_text_scope`, ``text_skip``
    claiming the Nth node's own clause in oracle order) is the final read; a bare
    self-loss with no wrapper actor and no text marker (Agent Venom, Dark
    Confidant) stays ``you``. An ``"each"`` recipient read backed ONLY by a
    completely uninformative ``Typed`` filter (ADR-0038 W5b —
    :func:`lifeloss_recipient_is_degraded_typed`) is DISTRUSTED and falls
    through to the wrapper/text chain instead: phase degrades a condition- or
    optional-wrapped "each opponent loses N life" to this exact empty shape
    (Baba Lysaga, Night Witch; Vohar, Vodalian Desecrator; Faerie Tauntings),
    losing the "opponent" distinction an UNCONDITIONAL "each opponent loses"
    never loses (that shape carries no recipient field at all, resolved via
    the wrapper/text fallback already)."""
    rs = lifeloss_recipient_scope(node)
    if rs is not None and not (
        rs == "each" and lifeloss_recipient_is_degraded_typed(node)
    ):
        return rs, False
    owner = effect_owner_player_scope(getattr(unit, "node", None), node)
    if owner in _EDICT_ACTORS:
        return "opponents", False
    text_scope = _lifeloss_text_scope(tree, skip=text_skip)
    if text_scope is not None:
        return text_scope, True
    return "you", True


def _lifeloss_self_paid_cost(node: TypedMirrorNode) -> bool:
    """Whether a ``payer``/``cost``-bearing wrapper (an ``unless_pay`` site, or a
    ``PayCost`` effect) is paid by the CONTROLLER, with a ``PayLife`` leaf
    anywhere in its cost sub-tree (CR 119.4). Rejects a non-controller payer —
    Vectis Dominator / Killing Wave's ``ParentTargetController`` ("unless ITS
    CONTROLLER pays"), Cleansing's ``AllPlayers`` ("unless ANY PLAYER pays"),
    Tyrannize's targeted ``Player`` ("unless THEY pay") — those cards TAX
    someone else; the card itself doesn't pay/lose life."""
    payer = getattr(node, "payer", None)
    if tag_of(payer) not in ("Controller", "SelfRef", "You"):
        return False
    cost = getattr(node, "cost", None)
    return any(tag_of(n) == "PayLife" for n in iter_typed_nodes(cost))


def _unit_has_non_ramp_effect(unit: AbilityUnit) -> bool:
    """Whether ``unit`` carries a non-ramp payoff ANYWHERE in its tree (CR
    119.4's painland exclusion), not just at its own top-level
    ``unit.effects`` — a paylife cost buried in a GRANTED trigger's
    ``unless_pay`` (Vile Consumption's "sacrifice this creature unless you
    pay 1 life", Morgul-Knife Wound's "exile ~ unless you pay 2 life") lives
    on a STATIC-origin unit whose OWN top-level ``unit.effects`` is empty
    (the grant modification itself is the only role=effect/static concept at
    THIS unit's surface — the granted trigger's Sacrifice/ChangeZone payoff
    is reachable only by walking INTO the grant, same blind spot the
    granted-ability LoseLife descent above already walks past). A unit-wide
    ``EFFECT_CONCEPTS`` tag scan (rather than the top-level ``unit.effects``
    concept-node list) reaches the granted payoff regardless of nesting
    depth; still excludes a painland-shaped grant whose ONLY reachable
    effect tag maps to ``ramp`` (Lithoform Blight's granted "Pay 1 life: Add
    one mana of any color" — the sibling ``{T}: Add {C}`` grant is ALSO
    ``ramp``, so the whole unit maps to ramp-only and stays excluded)."""
    if any(e.concept != "ramp" for e in unit.effects):
        return True
    for n in iter_typed_nodes(unit.node):
        concept = EFFECT_CONCEPTS.get(tag_of(n))
        if concept is not None and concept != "ramp":
            return True
    return False


def _granted_ability_paylife(unit: AbilityUnit) -> bool:
    """Whether ``unit`` GRANTS another permanent an activated ability whose
    OWN cost pays life (CR 118.8/119.4) — Underworld Connections's "Enchanted
    land has '{T}, Pay 1 life: Draw a card.'", Hibernation Sliver's "All
    Slivers have 'Pay 2 life: Return this permanent to its owner's hand.'".
    A ``GrantAbility.definition`` carries no ``payer`` field of its own (the
    payer is implicitly whoever controls the granted-to permanent, matching
    the OLD-IR ``life_payment`` marker's unconditional-``you`` convention
    this arm mirrors) — so this reads the definition's cost directly via
    :func:`cost_has_paylife` rather than :func:`_lifeloss_self_paid_cost`
    (which requires a ``payer`` field the definition doesn't have). Excludes
    a granted ability whose OWN effect is ``ramp`` (Lithoform Blight's
    granted painland "Add one mana of any color") — the exclusion reads the
    SAME definition's ``effect`` field, not the whole unit, so a card mixing
    a ramp grant with an unrelated non-ramp grant elsewhere still correctly
    excludes the ramp one specifically."""
    for n in iter_typed_nodes(unit.node):
        if tag_of(n) != "GrantAbility":
            continue
        definition = getattr(n, "definition", None)
        if definition is None:
            continue
        if not cost_has_paylife(getattr(definition, "cost", None)):
            continue
        eff_concept = EFFECT_CONCEPTS.get(tag_of(getattr(definition, "effect", None)))
        if eff_concept != "ramp":
            return True
    return False


def _has_paylife_as_colored_mana(unit: AbilityUnit) -> bool:
    """Whether ``unit`` carries the Phyrexian-mana-substitute static idiom
    (CR 118.9/107.4f — "For each {X} in a cost, you may pay 2 life rather
    than pay that mana.") — K'rrik, Son of Yawgmoth's own rules text (the
    ability that lets K'rrik's OWNER pay 2 life for any {B} in a cost, not
    the printed Phyrexian-mana symbols on other cards' costs, which the
    core substrate already resolves without a card-level static). Phase
    tags this ``S_static_abilities``'s ``mode`` field a
    ``PayLifeAsColoredMana`` variant (corpus-verified singleton: 1 card,
    K'rrik, phase v0.20.0), no ``payer``/``cost`` field at all to read
    through :func:`cost_has_paylife` — mirrors the OLD-IR ``life_payment``
    marker's unconditional-``you`` convention the sibling grant arms above
    already follow."""
    for n in iter_typed_nodes(unit.node):
        mode = getattr(n, "mode", None)
        if isinstance(mode, MirrorVariant) and mode.key == "PayLifeAsColoredMana":
            return True
    return False


def _has_defiler_cost_reduction(unit: AbilityUnit) -> bool:
    """Whether ``unit`` carries the Defiler-cycle static idiom (CR
    118.9-adjacent — Defiler of Faith's "As an additional cost to cast
    white permanent spells, you may pay 2 life. Those spells cost {W}
    less to cast if you paid life this way.") — a bespoke typed static
    (``S_DefilerCostReduction``, its own ``life_cost`` int field) phase
    models distinctly from the generic ``PayLife`` cost tag, so
    :func:`cost_has_paylife` never matches it. The Defiler grants this
    OPTIONAL life-cost to OTHER spells the controller casts (a card
    naming its OWN cost, not a tax on someone else) — mirrors the
    sibling grant arms' unconditional-``you`` convention. Phase tags this
    ``S_static_abilities``'s ``mode`` field a ``DefilerCostReduction``
    variant (corpus-verified: exactly the 5-card Defiler cycle, phase
    v0.20.0)."""
    for n in iter_typed_nodes(unit.node):
        mode = getattr(n, "mode", None)
        if isinstance(mode, MirrorVariant) and mode.key == "DefilerCostReduction":
            return True
    return False


def _token_attach_opponent_bleed_ids(unit: AbilityUnit) -> frozenset[int]:
    """Object-ids of ``LoseLife`` nodes to DISTRUST — a known phase mis-parse
    class (the SequentialSibling raw-bleed family, mtg-utils/CONTEXT.md)
    where a QUOTED granted ability nested inside a created token's own text
    gets flattened onto the token-creation trigger's OWN execute chain as a
    same-level ``sub_ability`` sibling, losing the fact that the clause
    belonged to the TOKEN's granted ability (whose "its controller" refers
    to the token's ENCHANTED permanent, not the trigger's own actor) —
    Scriv, the Obligator's Contract token: the quoted "...Otherwise, its
    controller loses 2 life." (meaning the OPPONENT the Aura attached to,
    CR 303.4c) surfaces as a target-less top-level ``LoseLife`` sibling of
    the ``Token`` effect, which the ordinary self-loss default (Agent
    Venom's "no wrapper actor, no text marker stays you" convention) would
    misattribute to Scriv's OWN controller. Corpus-verified narrow: exactly
    this ``Token`` + target-less-``LoseLife``-sibling + ``attach_to.
    controller == "Opponent"`` shape occurs once in the commander-legal
    corpus (Rotwidow Pack's structurally similar sibling shape carries no
    ``attach_to`` controller restriction at all, so stays OUT of this
    narrow gate — a real ambiguity for another wave, not this one)."""
    out: set[int] = set()
    for n in iter_typed_nodes(unit.node):
        effect = getattr(n, "effect", MISSING)
        sub = getattr(n, "sub_ability", MISSING)
        if effect is MISSING or sub is MISSING or tag_of(effect) != "Token":
            continue
        attach_to = getattr(effect, "attach_to", MISSING)
        if attach_to is MISSING or getattr(attach_to, "controller", None) != "Opponent":
            continue
        sub_effect = getattr(sub, "effect", MISSING)
        if sub_effect is MISSING or tag_of(sub_effect) != "LoseLife":
            continue
        target = getattr(sub_effect, "target", MISSING)
        if target is MISSING:
            out.add(id(sub_effect))
    return frozenset(out)


def _lifeloss_makers(tree: ConceptTree) -> list[Signal]:
    """lifeloss_makers — the card PERFORMS life loss (CR 119.3). (a) a ``LoseLife``
    effect, scope-split self/drain — including one nested inside a GRANTED
    ability/trigger a top-level ``unit.effects``/``.statics`` scan never flattens
    (Caustic Tar / Claim of Erebos / Relic Bane's "Enchanted X has '…Target player
    loses N life.'"; Pillory of the Sleepless's granted self-loss upkeep trigger) —
    an ``iter_typed_nodes`` deep walk of the WHOLE unit finds the ``LoseLife`` leaf
    either way, and :func:`_lifeloss_scope` reads its recipient the same way
    regardless of nesting depth; (b) a pay-life COST that buys a non-ramp effect
    (Erebos, Bleak-Hearted's ``Pay 2 life`` → draw; Gallowbraid's cumulative-upkeep
    ``unless_pay``; Wand of Denial / Shessra's optional "you may pay N life. If you
    do, …" trigger body) — CR 119.4: paying life IS a cost, but it causes the payer
    to lose that much life, so the card pays/loses life regardless of which
    sub-field nests the ``PayLife`` leaf (a top-level Activated ``unit.costs``
    Composite, or an ``unless_pay.cost`` / optional ``PayCost`` effect deep in a
    trigger chain whose OWN ``payer`` resolves to the controller — see
    :func:`_lifeloss_self_paid_cost`; a non-controller payer is a TAX on someone
    else, not this card's own life payment); (c) a GRANTED activated ability
    whose OWN cost pays life (Underworld Connections's "Enchanted land has
    '{T}, Pay 1 life: Draw a card.'", Hibernation Sliver's "All Slivers have
    'Pay 2 life: Return this permanent to its owner's hand.'") — see
    :func:`_granted_ability_paylife`, mirroring the OLD-IR ``life_payment``
    marker's unconditional-``you`` convention for a grant phase structures
    cleanly but the flat top-level cost/effect scan never reaches (ADR-0038
    W5b). The cost arms are gated HARD against the lane's land trap: a Land
    card (Horizon Canopy's ``Pay 1 life: draw``) is excluded (CR 118.8), and a
    paylife ability whose only reachable effect is mana fixing (``ramp``) is a
    painland, excluded by the non-ramp gate — :func:`_unit_has_non_ramp_effect`
    widens that gate to a unit-WIDE tag scan (not just top-level
    ``unit.effects``) so a paylife ``unless_pay`` nested in a granted trigger
    (Vile Consumption, Morgul-Knife Wound — a STATIC-origin unit whose own
    top-level ``unit.effects`` is empty) still resolves its granted payoff's
    ramp-ness correctly (ADR-0038 W5b). A Spell-kind unit's OWN casting cost
    (arms (d)/(e) below) is EXEMPT from the non-ramp gate outright — the
    painland shape (CR 118.8) is inherently a permanent's own activated
    ability, never a spell's casting cost, so a bare cost-only carrier unit
    with no effects field of its own (Phyrexian Scuta's "Kicker—Pay 3 life",
    ADR-0039 W7) is never wrongly excluded for lacking an unrelated non-ramp
    effect to point at. Combat damage (CR 120) is a sibling category that
    never tags ``LoseLife``.

    ADR-0039 W7 additions — two more root-level cost surfaces the flat
    per-ability walk never reaches, both closed the SAME way arm (b) reads
    an ``additional_cost``: (d) the card's OWN spell-level ``additional_cost``
    (CR 601.2b — Toxic Deluge's "As an additional cost to cast this spell,
    pay X life.") merges via :func:`_spell_additional_cost_concepts`'s
    PayLife carve-out (a ``PayLife`` leaf has no ``EFFECT_CONCEPTS`` entry —
    a cost primitive, not a named effect — so the general OTHER filter
    there admits it explicitly, verified corpus-safe: every OTHER consumer
    of ``unit.costs`` filters by an explicit ``concept ==`` name); (e) an
    ALTERNATIVE casting cost (CR 118.9 — Force of Will's "You may pay 1
    life ... rather than pay this spell's mana cost.") rides a SEPARATE
    root field, ``casting_options`` (``kind='AlternativeCost'``), that NO
    prior crosswalk reader touched at all — see
    :func:`_spell_alt_cost_paylife_concepts`. Both merge onto every
    Spell-kind unit's ``costs`` (with a Dargo-class carrier fallback for a
    hypothetical Spell-less card) in ``build_concept_tree``, so this lane's
    existing cost arm sees them with no lane-local change. (f) the
    Phyrexian-mana-substitute static (K'rrik, Son of Yawgmoth's "For each
    {B} in a cost, you may pay 2 life rather than pay that mana.") carries
    no ``payer``/``cost`` field to read through :func:`cost_has_paylife` at
    all — see :func:`_has_paylife_as_colored_mana` (corpus-verified
    singleton).
    """
    out: list[Signal] = []
    seen: set[str] = set()
    text_skip = 0

    def fire(scope: str, raw: str) -> None:
        if scope not in seen:
            seen.add(scope)
            out.append(Signal("lifeloss_makers", scope, "", raw, tree.name, "high"))

    def scoped_fire(unit: AbilityUnit, node: TypedMirrorNode, raw: str) -> None:
        # ``text_skip`` advances for EVERY LoseLife node processed, not just
        # ones that end up USING the text fallback: a structurally-resolved
        # node (Feed the Infection's first "you lose 3 life", target=
        # Controller) still consumes its OWN clause's position in oracle
        # order, so a LATER node's text-fallback search must skip past it —
        # otherwise the later node's search restarts at clause 0 and
        # re-matches the EARLIER (already-claimed) clause instead of its own.
        nonlocal text_skip
        scope, _used_text = _lifeloss_scope(unit, node, tree, text_skip)
        text_skip += 1
        fire(scope, raw)

    for unit in tree.units:
        bled_ids = _token_attach_opponent_bleed_ids(unit)
        top_level_ids = set()
        for c in unit.effect_concepts("lose_life"):
            if id(c.node) in bled_ids:
                continue
            top_level_ids.add(id(c.node))
            scoped_fire(unit, c.node, c.raw)
        for n in iter_typed_nodes(unit.node):
            # Skip a node already handled via the top-level concept read above
            # — a LoseLife reachable BOTH through ``unit.effect_concepts``
            # AND this deep walk (the ordinary, non-nested case) must not be
            # scored twice, which would falsely advance ``text_skip`` and
            # steal the NEXT card's clause for a phantom second node.
            if (
                tag_of(n) == "LoseLife"
                and id(n) not in top_level_ids
                and id(n) not in bled_ids
            ):
                scoped_fire(unit, n, "")
    if not tree.is_type("Land"):
        for unit in tree.units:
            paylife = any(cost_has_paylife(cc.node) for cc in unit.costs) or any(
                _lifeloss_self_paid_cost(n) for n in iter_typed_nodes(unit.node)
            )
            # The painland trap (CR 118.8) is inherently a PERMANENT's own
            # activated ability ("{T}, Pay 1 life: Add ...") — never a
            # Spell-kind unit's casting cost (additional/kicker/alternative,
            # CR 118.8/118.9/601.2b). Phyrexian Scuta's bare "Kicker—Pay 3
            # life" carrier unit (ADR-0039 W7) has NO effects field of its
            # own at all (the "if kicked, +1/+1 counters" lives in a
            # SEPARATE replacement, not this unit) — the general non-ramp
            # scan would find nothing to prove non-ramp and wrongly exclude
            # it. A Spell unit's own casting cost never needs that proof.
            non_ramp_ok = unit.kind == "Spell" or _unit_has_non_ramp_effect(unit)
            if (
                (paylife and non_ramp_ok)
                or _granted_ability_paylife(unit)
                or _has_paylife_as_colored_mana(unit)
                or _has_defiler_cost_reduction(unit)
            ):
                fire("you", "")
    # ADR-0039 W7 ledgered bridges — genuine phase-drop stragglers with no
    # typed-node path (bridge_ledger.BRIDGES): Degavolver/Anavolver's
    # zero-trace kicker-granted paylife regen, Withercrown's Unimplemented
    # "Unsupported unless clause" residue nested outside the recovery
    # stage's unit.effects-only scan, and the Warp/Blitz/Morph life-cost
    # cycle phase drops wholesale (no keyword entry at all).
    if bridge_fires("degavolver_kicker_paylife_regen", tree):
        fire("you", "")
    if bridge_fires("withercrown_unless_lose_life", tree):
        fire("you", "")
    if bridge_fires("keyword_dropped_paylife", tree):
        fire("you", "")
    if bridge_fires("night_shift_optional_paylife_dieroll", tree):
        fire("you", "")
    if bridge_fires("zuko_modal_unconditional_paylife", tree):
        fire("you", "")
    # ADR-0025 folded objects (2026-07-25): a wholly phase-uncovered folded
    # object (the dungeon Tomb of Annihilation) gets ONLY a zero-unit
    # text-only tree — no LoseLife node exists for the typed reads above,
    # so the bounded symmetric "each player loses N life" room idiom rides
    # a missing_face bridge (scope "each" — the CR 309 room resolves for
    # every player). Full row in ``bridge_ledger.BRIDGES``.
    if bridge_fires("folded_object_text_only_each_player_loses", tree):
        fire("each", "")
    # task #95 — the ``synth_lifeloss_makers_opponents`` bucket-B marker
    # (see :func:`~mtg_utils._card_ir.tree_synthesis.
    # _arm_known_token_lifeloss_opponents`'s own docstring): the Wicked
    # predefined-token cycle's "each opponent loses 1 life" (when the Aura
    # leaves the battlefield) rides a zero-unit text-only tree with no
    # ``LoseLife`` node to walk structurally.
    for c in tree.iter_concepts():
        if c.concept == "synth_lifeloss_makers_opponents":
            fire("opponents", "")
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
    arm).

    b3 recall — two more forced-actor controllers, both gated on a TRIGGER origin
    (the adjudicated "trigger-wrapped true edict" the direct opp/each arm misses):
    ``DefendingPlayer`` (Annihilator N — CR 702.85a, the defending player
    sacrifices N permanents of their choice: Breaker of Creation, Artisan of
    Kozilek) → opponents; ``ParentTargetController`` ("that [dying creature]'s
    controller sacrifices …" — Burning Sands) → each, matching the live IR scope
    (symmetric across whoever's permanent left). The trigger gate excludes an
    activated/spell OPTIONAL "may sacrifice a land" downside (Chain of Vapor —
    ParentTargetController, an optional bounce rider, not an edict)."""
    ctrl = filter_controller(effect_filter(node))
    if ctrl == "ScopedPlayer":
        return _scoped_player_scope(unit)
    if ctrl in ("Opponent", "Opponents", "EachOpponent", "TargetPlayer"):
        return "opponents"
    if ctrl in ("All", "EachPlayer", "Each"):
        return "each"
    if unit is not None and getattr(unit, "origin", None) == "trigger":
        if ctrl == "DefendingPlayer":
            return "opponents"
        if ctrl == "ParentTargetController":
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
            # task B-3 (keep_n_wrath disjointness): a TrackedSet target is a
            # back-reference to permanents ALREADY chosen upstream ("choose
            # N, sacrifice the rest" — Single Combat) — never the fresh
            # CR 701.21a sacrifice choice an edict forces. keep_n_wrath owns
            # the shape; firing edict_makers here poisoned both reads.
            if tag_of(getattr(c.node, "target", None)) == "TrackedSet":
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


def _in_condition_instead_branch(top: object, target_effect: object) -> bool:
    """Whether ``target_effect`` sits inside a ``sub_ability`` branch gated by
    a CR 614.1 ``ConditionInstead`` REPLACEMENT — Epicenter's Threshold
    "instead" body ("Each player sacrifices all lands they control instead
    if there are seven or more cards in your graveyard") REPLACES the
    top-level "Target player sacrifices a land" body; it is a separate
    resolution, not a continuation of the same actor's chain (contrast Din
    of the Fireherd's ``sub_link='SequentialSibling'`` — a genuine same-actor
    sequence, CR 601.2h)."""
    node = top
    while node is not None:
        eff = getattr(node, "effect", None)
        if eff is target_effect:
            cond = getattr(node, "condition", None)
            return tag_of(cond) == "ConditionInstead"
        node = getattr(node, "sub_ability", None)
    return False


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
    NOT opponent-directed (you sac your own lands too).

    Epicenter per-clause fix (ADR-0039 W7): the sibling-scan below poisoned a
    CR 614.1 ``ConditionInstead`` replacement clause with its SUPERSEDED
    top-level sibling's opponent direction — Epicenter's own Threshold body
    ("Each player sacrifices all lands they control instead...") is
    ``ScopedPlayer``/``All`` (symmetric, you sac too), but the un-thresholded
    "Target player sacrifices a land" body it REPLACES is ``TargetPlayer``
    (opponent-directed); the old flat scan let that superseded sibling's
    direction leak across the replacement boundary. :func:`_in_condition_
    instead_branch` skips the sibling scan for a node inside its OWN
    ``ConditionInstead`` branch — it already passed the ``owner`` check above
    (not itself opponent-directed), so borrowing a DIFFERENT branch's
    direction would be wrong."""
    owner = effect_owner_player_scope(getattr(unit, "node", None), node)
    if owner in _OPP_SAC_ACTORS:
        return True
    if _in_condition_instead_branch(getattr(unit, "node", None), node):
        return False
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


# Attack-requirement land-sac accessor (ADR-0039 W7): "~ can't attack unless
# you sacrifice a land" (Exalted Dragon, CR 508.1d — an attack-requirement
# whose cost is paid as attackers are declared) types as a ``CantAttack``
# static whose restriction lifts under a NOT-wrapped condition phase's
# clause grammar can't structure into a typed cost — it parks the verbatim
# clause as a ``T_condition__Unrecognized.text`` fallback field instead
# (still a TYPED field, not a whole-card regex). Anchored to the EXACT
# legacy phrasing (singular "a land" — legacy's own regex never matched
# Leviathan's "sacrifice two Islands" sibling either, corpus-verified) and
# to a SelfRef affected (excludes Flooded Woodlands / Reclamation's "Green/
# Black creatures can't attack unless THEIR CONTROLLER sacrifices..." —
# controller=None Typed[Creature] affected, a symmetric per-color tax, not
# a single card's own attack-cost).
_ATTACK_REQ_LAND_SAC_RE = re.compile(r"^unless you sacrifice a land$")


def _attack_requirement_land_sac(tree: ConceptTree) -> bool:
    for unit in tree.units:
        node = unit.node
        if getattr(node, "mode", None) not in ("CantAttack", "CantAttackOrBlock"):
            continue
        if tag_of(getattr(node, "affected", None)) != "SelfRef":
            continue
        cond = getattr(node, "condition", None)
        inner = getattr(cond, "condition", None) if tag_of(cond) == "Not" else cond
        text = getattr(inner, "text", None) if tag_of(inner) == "Unrecognized" else None
        if text and _ATTACK_REQ_LAND_SAC_RE.match(text):
            return True
    return False


def _granted_land_sac_unless_pay(tree: ConceptTree) -> bool:
    """A land-Sacrifice ``unless_pay`` alternative cost on a GRANTED trigger
    (Custody Battle's Aura: "Enchanted creature has 'At the beginning of your
    upkeep, target opponent gains control of ~ unless you sacrifice a
    land.'") — the same upkeep-tax idiom :func:`_land_sacrifice_makers`
    already reads off the card's OWN top-level ``unit.node.unless_pay``, one
    level deeper: the alternative cost lives on the GrantTrigger
    modification's OWN nested ``trigger.unless_pay``, a tree position the
    per-unit walk never reaches directly. CR 601.2h / 701.21."""
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            for m in getattr(sdef, "modifications", None) or []:
                if tag_of(m) != "GrantTrigger":
                    continue
                trig = getattr(m, "trigger", None)
                unless_pay = getattr(trig, "unless_pay", None) if trig else None
                if unless_pay is None:
                    continue
                for leaf in iter_cost_leaves(getattr(unless_pay, "cost", None)):
                    if tag_of(leaf) == "Sacrifice" and filter_core_types(
                        getattr(leaf, "target", None)
                    ) == ("Land",):
                        return True
    return False


def _land_sacrifice_makers(tree: ConceptTree) -> list[Signal]:
    """land_sacrifice_makers — a SELF land-sacrifice engine (CR 701.21 / 305.6): a
    ``Sacrifice`` effect OR cost whose subject is LAND-ONLY where YOU sacrifice your
    OWN lands (Zuran Orb's "Sacrifice a land:", Scapeshift; symmetric "each player
    sacrifices a land" — Smallpox, Death Cloud — counts, you sac too). The Land-only
    branch ``sacrifice_outlets`` deliberately EXCLUDES
    (:func:`_is_you_sac_subject` returns False on a ``("Land",)`` subject), so it is a
    clean complement; a mixed "creature or land" sac (Reprocess, Larval Scoutlander's
    "sacrifice a land OR Lander") is ``sacrifice_outlets``, not this. An OPPONENT
    land-edict (land destruction — Yawning Fissure "each opponent sacrifices a land",
    Din of the Fireherd "target opponent ... sacrifices a land") is NOT a self engine
    and is gated out by :func:`_sac_targets_opponent`, working around phase's
    [P1]/[P3] direction mislabels.

    Two ADR-0038 W3 batch 4 additions read a Sacrifice-cost LEAF phase buries where
    the top-level per-ability concept walk never surfaces it:

    * a ``Sacrifice`` cost folded into a ``Composite`` activation cost (Tap +
      Sacrifice, Mana + Tap + Sacrifice — Soldevi Sage, Dust Bowl, Copper-Leaf
      Angel's X-cost sac, Excavator): the Composite wrapper decorates as ONE
      opaque concept, never surfacing the individual Sacrifice leaf.
      :func:`iter_cost_leaves` walks the same Composite/OneOf nesting
      :func:`cost_has_paylife` already reads. A COST is always paid by the
      ACTIVATOR, so no opponent gate applies here (unlike the effect arm above).
    * a trigger's ``unless_pay`` alternative cost (the "sacrifice PERMANENT
      unless you sacrifice a land" upkeep-tax shape — Cosmic Larva, The Gitrog
      Monster, Territorial Dispute, Bog Elemental, Scythe Tiger, Jokulmorder):
      the alternative cost lives on the trigger's own ``unless_pay.cost``, a
      tree position the per-ability effects/costs walk never reaches.

    Two ADR-0039 W7 pre-deletion accessor fixes (both flagged pre-W6, no legacy
    impact, pure crosswalk reads — CR-grounded, zero corpus over-fire risk):

    * :func:`_attack_requirement_land_sac` — a sacrifice cost attached to an
      ATTACK REQUIREMENT (Exalted Dragon: "~ can't attack unless you sacrifice
      a land", CR 508.1d) reads the cost off the ``CantAttack`` static's own
      condition-fallback text, a tree position the cost-leaf/unless_pay walks
      above never reach (there is no ``cost``/``unless_pay`` field on an
      attack-requirement static at all — the cost lives only in the
      unstructured condition text).
    * :func:`_granted_land_sac_unless_pay` — Custody Battle's Aura grants the
      SAME "unless you sacrifice a land" upkeep-tax trigger, one level
      deeper: the ``unless_pay`` lives on a GRANTED trigger's own
      definition (a ``GrantTrigger`` modification), not the card's own
      top-level ``unit.node.unless_pay`` the bare arm above reads.

    Deliberately EXCLUDED (adjudicated legacy over-fires, CR 701.21 / 400.7): a
    "land is put into a graveyard from the battlefield" TRIGGER (Dingus Egg, Akki
    Raider, Centaur Vinecrasher) watches the land DYING by ANY means (destroy,
    sacrifice, or otherwise) — it is a payoff/punisher, not the actor performing a
    sacrifice, and phase's own controller-less trigger subject ("a land" — not "a
    land YOU control") is what lets legacy's regex-driven
    ``supplement._recover_land_sacrifice`` synthesis over-fire here (verified this
    session via direct legacy-signal inspection: the trigger's
    ``subject.controller`` gate in ``_land_sac_trigger_present`` requires "you",
    which these three fail, so the synth cost fires instead of the correct
    ``land_sacrifice_matters`` payoff read); "whenever you sacrifice a land"
    (Scouring Swarm) is the PAYOFF side of the SAME sac
    (``land_sacrifice_matters``), not the engine performing it — the SAME
    legacy-synthesis over-fire (the trigger-shaped payoff wording matches the
    synth pattern's OWN "whenever you sacrifice a land" arm too); a MIXED
    "sacrifice a land or Lander" subject (Larval Scoutlander) is
    ``sacrifice_outlets`` territory (the docstring's own mixed-subject
    exclusion above), but the synth regex still matches the "sacrifice a
    land" substring inside the composite phrase and double-fires a bogus
    Land-only cost on top of the genuine structured ``Or[Land, Lander]``
    effect — the SAME substring-match-regardless-of-true-subject over-fire
    class.
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
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "Sacrifice" and filter_core_types(
                getattr(leaf, "target", None)
            ) == ("Land",):
                return [
                    Signal("land_sacrifice_makers", "you", "", "", tree.name, "high")
                ]
        unless_pay = getattr(unit.node, "unless_pay", None)
        if unless_pay is not None:
            for leaf in iter_cost_leaves(getattr(unless_pay, "cost", None)):
                if tag_of(leaf) == "Sacrifice" and filter_core_types(
                    getattr(leaf, "target", None)
                ) == ("Land",):
                    return [
                        Signal(
                            "land_sacrifice_makers", "you", "", "", tree.name, "high"
                        )
                    ]
    if _attack_requirement_land_sac(tree) or _granted_land_sac_unless_pay(tree):
        return [Signal("land_sacrifice_makers", "you", "", "", tree.name, "high")]
    return []


def _debuff_makers(tree: ConceptTree) -> list[Signal]:
    """debuff_makers — a -X/-X / -1/-1 enabler (CR 613.4c / 704.5g). Three anchors:

    * a NEGATIVE ``Pump`` / ``PumpAll`` EFFECT (Bile Blight's -3/-3) — scope
      "any"; reads BOTH a FIXED shrink (either field negative, via
      :func:`pump_is_negative`) and a dynamic ``Variable "-X"`` TOUGHNESS
      shrink (Death Wind / Flunk's single-target "-X/-X", Toxic Deluge's mass
      "-X/-X" — task #85: the single-target kill class fell through here
      because ``pump_is_negative`` only reads ``Fixed`` sub-nodes; the mass
      arm's own :func:`_negative_pt_field` already covered the dynamic case
      in ``_mass_removal`` per the CR 704.5f lethality tell, so this mirrors
      that precedent — toughness only, same as the mass arm, not power: a
      dynamic "-X/+0" power-only dip has no toughness tell to key on and
      stays unread here, matching the Fixed arm's silence on that shape too
      since ``pump_is_negative`` gates on EITHER field but no corpus card
      pairs a dynamic power shrink with a static positive toughness);
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
            if c.concept == "pump" and (
                pump_is_negative(c.node) or _negative_pt_field(c.node, "toughness")
            ):
                fire("any", c.raw)
            if (
                c.concept == "place_counter"
                and counter_kind(c.node).upper() == "M1M1"
                and c.scope != "you"
            ):
                fire("any", c.raw)
        # STATIC negative-POWER pump (recall gap — the biggest silent tail): a
        # continuous ``AddPower`` with a NEGATIVE plain-int value — the debuff
        # Aura (Clinging Darkness -4/-1, Chant of the Skifsang -13/-0, Animate
        # Dead -1/-0). Keyed on the POWER sign to mirror the live path, which
        # reads the projected pump Effect's ``amount`` (the power value, scope
        # "any"): a +X/-Y combat Equipment/Aura (Barbed Battlegear +4/-1, Boon
        # of Emrakul +3/-3) is a BUFF whose power is positive, so it stays out
        # (the ``AddToughness`` shrink alone is a tradeoff downside, not a -1/-1
        # enabler). The ``Pump``-EFFECT arm above reads the ``Fixed``
        # power/toughness sub-nodes; a STATIC mod carries a bare-int ``value``
        # (:func:`mod_value`). A dynamic ``AddDynamicPower`` value has no int →
        # skipped. CR 613.4c.
        for c in unit.statics:
            if tag_of(c.node) != "AddPower":
                continue
            v = mod_value(c.node)
            if v is not None and v < 0:
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
    """lure_makers — a forced-block / lure requirement (CR 509.1c/h). A
    ``MustBeBlockedByAll`` / ``MustBeBlocked`` static mode (Lure, Nemesis Mask),
    conferred via an ``AddStaticMode`` modification (:func:`node_lure_mode`). A
    single-target ``ForceBlock`` (Academic Dispute) is a narrower provoke-style effect
    that does NOT carry the mode, correctly excluded. Scope "you".

    Bucket-B fallback (W3 batch-3, ADR-0038): phase swallows the requirement
    into a compound pump/grant clause (Indrik Umbra, Revenge of the Hunted),
    drops it into a conditional static (Seton's Desire, Stone-Tongue
    Basilisk), folds an equip rider ("must be blocked by a Dalek/Eldrazi if
    able" — Ace's Baseball Bat, Slayer's Cleaver), or buries it in a modal
    bullet (Glorfindel) — a full-residue Unimplemented clause the SAME two
    idioms project.py's own card-level marker recovery already tokenizes,
    imported single-source (no new grammar): "able to block … do so"
    (:data:`_LURE_ABLE`, force ALL able blockers) and "must be blocked [by
    <type>] if able" (:data:`_LURE_MUST`, force a block on the attacker).
    Read off ``_kept(tree)`` when no structural node fired.
    """
    for unit in tree.units:
        if node_lure_mode(unit.node):
            return [Signal("lure_makers", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            if node_lure_mode(c.node):
                return [Signal("lure_makers", "you", "", c.raw, tree.name, "high")]
    kept = _kept(tree)
    if _LURE_ABLE.search(kept) or _LURE_MUST.search(kept):
        return [Signal("lure_makers", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W3 batch 3 — a BecomeCopy ``target`` naming a BACK-REFERENCE (no filter
# of its own) points at whatever object this SAME ability already selected — Dimir
# Doppelganger's exiled creature card (``ParentTarget``), Curie's exiled artifact
# creature (``TrackedSet``), The Ever-Changing 'Dane's sacrificed creature
# (``CostPaidObject``), The Everflowing Well's triggering object
# (``TriggeringSource``), The Mimeoplasm's exiled card (``ExiledCardByIndex``).
# ``SelfRef`` (Permeating Mass, The Flood of Mars — "becomes a copy of ~") instead
# names the ability's OWN host card, no lookup needed. A core-type word literally
# named in a clause's own text — never a whole-card scan — is the LAST-RESORT read
# for a sibling selector phase leaves Unimplemented (Kaya, Spirits' Justice's
# "choose a CREATURE CARD from among them"; Valki's "Choose a CREATURE CARD exiled
# with Valki").
_CLONE_TYPE_WORD_RE = re.compile(
    r"\b(creature|artifact|enchantment|planeswalker|land|permanent)\b",
    re.IGNORECASE,
)


def _clone_words_from_raw(raw: str) -> tuple[str, ...]:
    out: list[str] = []
    for w in _CLONE_TYPE_WORD_RE.findall(raw or ""):
        title = w.title()
        if title not in out:
            out.append(title)
    return tuple(out)


def _clone_copied_words(
    tree: ConceptTree, unit: AbilityUnit, node: TypedMirrorNode
) -> tuple[str, ...]:
    """The copied permanent's type/subtype words for a ``BecomeCopy`` effect (CR
    707.2) — the same recovery chain the legacy ``_recover_clone_subjects``
    (project.py) runs, ported onto the mirror tree instead of re-derived, plus two
    arms the legacy fallback never needed (a real mirror tree exposes the sibling
    NODES the legacy text-only recovery couldn't): a direct ``Typed``/``Or``/``And``
    filter on ``target`` names the type outright (Clone, Spark Double). A back-
    reference target instead recovers it, in order: (1) THIS SAME unit's other
    concept's own structured subject words — the producing selector's type (Dimir
    Doppelganger's Exile-target Creature filter, Brudiclad's created-token types,
    Curie's exiled-artifact-creature cost); (2) for a trigger-origin unit with no
    such sibling, the trigger's OWN watched-object filter (Sarkhan, Soul Aflame's "a
    Dragon you control enters", Lazav's "a creature card is put into an opponent's
    graveyard" — the copy has no sibling EFFECT to borrow from, the type lives on
    the trigger node itself); (3) the clause's own "copy of <type>" text (Cytoshape,
    Cemetery Puca — the printed reminder already names the type); (4) a core-type
    word ANYWHERE in this SAME unit's own generated description (Vesuvan Drifter,
    The Mimeoplasm — "If you reveal a CREATURE card this way, ~ becomes a copy of
    THAT CARD"; the qualifier precedes "copy of" instead of following it, so the
    narrower "copy of <type>" text-scan misses it, but the type word is still
    THIS unit's own, never a whole-card scan); (5) a core-type word literally
    named in a sibling's own raw clause text (:func:`_clone_words_from_raw` — Kaya,
    Spirits' Justice / Valki's "choose a CREATURE CARD"); (6) the true last resort,
    a core-type word ANYWHERE in the whole-card oracle (Volatile Chimera — the
    "creature cards you drafted" qualifier lives on a WHOLLY SEPARATE deckbuilding
    ability, cross-unit) — safe only because it is gated behind a real structural
    ``BecomeCopy`` node already existing (never widens WHICH cards fire, only
    WHICH type they fire as).
    """
    sub = effect_filter(node)
    words = (filter_core_types(sub) + filter_subtypes(sub)) if sub is not None else ()
    if words:
        return words
    ttag = tag_of(getattr(node, "target", None))
    if ttag == "SelfRef":
        return tree.card_types + tree.card_subtypes
    for oc in unit.iter_concepts():
        if oc.node is node or not oc.subject:
            continue
        # A bare "Card" filter ("exile A CARD", no type restriction) carries no
        # permanent-type info — skip it so a later, more specific tier (the
        # unit's own description text) gets a chance (Lazav, Familiar Stranger).
        sib_words = tuple(w for w in oc.subject if w != "Card")
        if sib_words:
            return sib_words
    if unit.origin == "trigger":
        trig_words = trigger_subject(unit.node)
        if trig_words:
            return trig_words
    unit_desc = getattr(unit.node, "description", "") or ""
    recovered = _copied_type_from_text(unit_desc)
    if recovered is not None:
        return recovered.card_types
    found = _clone_words_from_raw(unit_desc)
    if found:
        return found
    for oc in unit.iter_concepts():
        if oc.node is node:
            continue
        found = _clone_words_from_raw(oc.raw)
        if found:
            return found
    return _clone_words_from_raw(tree.oracle)


# ADR-0038 W3 batch 4 (clone_makers) — bucket-B text-idiom bridge for phase
# static-parser failures that emit NO ``BecomeCopy`` node at all (not even a
# mis-typed one ``_clone_copied_words`` could descend into): Blade of Shared
# Souls / Essence of the Wild / Metamorphic Alteration / The Fourteenth
# Doctor / Vesuvan Shapeshifter are phase ``Unimplemented`` "have X become a
# copy" clauses; Ludevic, Necrogenius has no BecomeCopy node anywhere on
# either face. CR 707.2 (the general copy-effect rule) and 707.5 ("enters
# the battlefield 'as a copy'... becomes a copy as it enters") both describe
# the SAME become-a-copy-of relationship regardless of which surface verb
# the card prints, so a single per-clause text scan for the idiom stands in
# for the missing node. Two per-CLAUSE exclusions (boundary lesson (iii) —
# scoped to the period-delimited clause, never the whole tree/card):
# "token" (the much larger ``token_copy_makers`` "create a token that's a
# copy of ~" family — Dance of Many, Splitting Slime, Dual Nature, … — is a
# different structural surface with its own ``CopyTokenOf`` node and stays
# on that lane) and "land card" (Echoing Deeps copies a LAND, not a
# Permanent/Creature; legacy agrees this isn't clone_makers). Corpus-verified
# (2026-07) against every commander-legal card matching the idiom: the only
# card beyond the 7 known live_only members this arm also reaches is
# Paleontologist's Pick-Axe // Dinosaur Headdress ("Equipped creature is a
# copy of the last chosen card") — a genuine CR 707.2 clone effect legacy's
# regex never covered either, so it's an adjudicated GAIN, not an over-fire.
_CLONE_BECOME_COPY_RX = re.compile(
    r"\b(?:becomes?|is|are|enters?)\b[^.]{0,80}\bcopy of\b[^.]{0,60}"
    r"\b(?:creature|card)\b",
    re.IGNORECASE,
)
_CLONE_TOKEN_EXCLUDE_RX = re.compile(r"\btoken\b", re.IGNORECASE)
_CLONE_LAND_EXCLUDE_RX = re.compile(r"\bland card\b", re.IGNORECASE)


def _clone_text_idiom(tree: ConceptTree) -> str | None:
    """The become-a-copy-of clause text, per-clause gated (CR 707.2/707.5).

    Returns the matching clause (stripped) as the signal's ``raw``, or
    ``None`` if no clause in this face survives the token/land exclusions
    and matches the idiom.
    """
    for clause in _kept(tree).split("."):
        if _CLONE_TOKEN_EXCLUDE_RX.search(clause):
            continue
        if _CLONE_LAND_EXCLUDE_RX.search(clause):
            continue
        if _CLONE_BECOME_COPY_RX.search(clause):
            return clause.strip()
    return None


def _copy_clone(tree: ConceptTree) -> list[Signal]:
    """copy_permanent / clone_makers / token_copy_makers — the copy cluster (CR 707 /
    701.36). Three structural surfaces (Dan's clone-vs-token-copy boundary):

    * a ``BecomeCopy`` effect — the copied type (:func:`_clone_copied_words`) drives
      the lane: a generic ``Permanent`` copy (Crystalline Resonance) fans to
      ``copy_permanent`` + ``clone_makers``; a ``Creature`` core type or a resolved
      creature SUBTYPE (Sunfrill Imitator's Dinosaur) → ``clone_makers``. A
      ``BecomeCopy`` BURIED inside a granted ability's own quoted definition
      (Shameless Charlatan — "Commander creatures you own have '{2}{U}: This
      creature becomes a copy of another target creature.'") carries no top-level
      unit effect at all, so the unit's own already-decorated ``GrantAbility``
      static concept is descended one level (``.definition.effect`` — O(1), never a
      full tree walk) to catch it too;
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

    for unit in tree.units:
        found_nodes: set[int] = set()
        become_copies: list[tuple[TypedMirrorNode, str]] = []
        for c in unit.effect_concepts("become_copy"):
            found_nodes.add(id(c.node))
            become_copies.append((c.node, c.raw))
        for sc in unit.statics:
            if tag_of(sc.node) != "GrantAbility":
                continue
            definition = getattr(sc.node, "definition", None)
            geffect = (
                getattr(definition, "effect", None) if definition is not None else None
            )
            if (
                isinstance(geffect, TypedMirrorNode)
                and tag_of(geffect) == "BecomeCopy"
                and id(geffect) not in found_nodes
            ):
                found_nodes.add(id(geffect))
                gdesc = getattr(definition, "description", "") or ""
                become_copies.append((geffect, gdesc))
        for node, raw in become_copies:
            words = _clone_copied_words(tree, unit, node)
            if "Permanent" in words:
                fire("copy_permanent", raw)
                fire("clone_makers", raw)
            if "Creature" in words:
                fire("clone_makers", raw)
            if any(_resolve_subject(w, CREATURE_SUBTYPES) for w in words):
                fire("clone_makers", raw)
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
    if "clone_makers" not in seen:
        idiom = _clone_text_idiom(tree)
        if idiom is not None:
            fire("clone_makers", idiom)
    return out


def _connive_makers(tree: ConceptTree) -> list[Signal]:
    """connive_makers — a connive DOER (CR 701.50a). A ``Connive`` effect
    (Shipwreck Sifters, Old Rutstein) reads through the ordinary flat
    ``effect_concepts`` walk — including an ADR-0038 no-residue synthesis
    hit (``tree_synthesis._arm_connive_makers``, Unstable Experiment's
    "target creature you control connives" clause, which phase drops
    entirely with no node at all). A ``Connive`` tag buried inside a
    GRANTED trigger (Security Bypass's Aura grant "Enchanted creature has
    '... it connives.'", Copycrook's copy-exception grant) is never its
    own concept node — :func:`has_nested_connive` (the
    ``iter_nested_trigger_defs`` shared descent, ADR-0037/0038 W1 batch-3)
    reaches it.

    A pure connive-STATE PAYOFF ("whenever a creature you control connives,
    ..." — Glorious Purpose, Iron Monger, Sadistic Tycoon) is a SEPARATE key
    (CR 701.50a: connive is an instruction TO a permanent; a card merely
    watching for that instruction elsewhere is not the doer) — Scryfall's
    ``connive`` keyword field tags both roles, which is why legacy's
    keyword-field lookup over-fires on the payoff pair; this structural
    read stays doer-only by construction (no keyword-field fallback).
    Scope "you".
    """
    for c in tree.effect_concepts("connive"):
        return [Signal("connive_makers", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if has_nested_connive(unit.node):
            return [Signal("connive_makers", "you", "", "", tree.name, "high")]
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
    Borca; Case of the Stashed Skeleton's dropped "suspect it" token-creation
    rider — phase emits NO residue node at all for it, so a
    ``tree_synthesis._arm_suspect_makers`` synth node fills the gap, emitting
    the REAL "suspect" concept per ADR-0037/0038, no marker special-case
    needed here). A ``Suspected`` PROPERTY reference (the payoff — "whenever a
    suspected creature …") is a distinct phase tag, never a ``Suspect``
    effect, so it is correctly excluded. Scope "you".
    """
    for c in tree.effect_concepts("suspect"):
        return [Signal("suspect_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _combat_damage_to_opp_fires(node: object) -> bool:
    """Whether trigger DEFINITION ``node`` is combat_damage_to_opp's exact shape:
    :func:`damage_to_player_trigger_kind` confirms ``CombatOnly`` AND the
    recipient reaches an ACTUAL player, not merely a planeswalker (CR 102.1 — a
    planeswalker is not a player). Zagras, Thief of Heartbeats's "Whenever a
    creature you control deals combat damage to a PLANESWALKER, destroy that
    planeswalker" satisfies ``combat_damage_matters`` (CR 510.1b's
    player-OR-planeswalker read, shared with ``damage_recipient_is_player``'s
    broader gate) but not this PLAYER-specific lane — legacy's own
    recipient-tuple read requires "player" in the recipient tuple, not merely
    "planeswalker" (CR 510.1c). Also accepts the
    :func:`_unknown_mode_combat_damage_to_player` Unknown-mode fallback
    (Kang Dynasty's Saga-granted delayed trigger) — that mirror only ever
    matches an explicit "... to a player" phrasing, so it never needs the
    planeswalker exclusion itself.
    """
    kind = damage_to_player_trigger_kind(node)
    if kind is None and _unknown_mode_combat_damage_to_player(node):
        return True
    if kind != "CombatOnly":
        return False
    vt = getattr(node, "valid_target", None)
    if tag_of(vt) == "Typed":
        cores = filter_core_types(vt)
        if cores and "Player" not in cores and "Planeswalker" in cores:
            return False
    return True


def _combat_damage_to_opp(tree: ConceptTree) -> list[Signal]:
    """combat_damage_to_opp — a "deals combat damage to a player" trigger (CR 510.1c).
    A ``DamageDone`` trigger whose ``damage_kind`` is ``CombatOnly`` AND whose
    recipient (``valid_target``) reaches a PLAYER (Coastal Piracy, Bident of Thassa).
    A creature recipient (Ohran Viper's first trigger) is ``combat_damage_to_creature``
    (a different lane); a planeswalker-ONLY recipient (Zagras) is
    ``combat_damage_matters`` only (see :func:`_combat_damage_to_opp_fires`); a
    non-combat "deals damage" trigger never reaches here.

    ADR-0038 W3 batch 4 (combat-damage cluster): shares :func:`damage_to_player_
    trigger_kind`'s three-position descent with ``_combat_damage_lanes`` — a
    top-level trigger unit's own node, a ``GrantTrigger``/``CreateEmblem``
    granted def (:func:`iter_nested_trigger_defs` — Sokrates's "target
    creature gains" quote, Fire Giant's Fury's pump-target grant), and a
    ``CreateDelayedTrigger`` watcher def (:func:`iter_delayed_trigger_condition_
    defs` — Subira, Tulzidi Caravanner's "Until end of turn, whenever a
    creature you control ... deals combat damage to a player, draw a card").
    The bare top-level-only read left every granted/delayed form
    ``live_only`` (the sibling ``combat_damage_matters``/``damage_to_opp_
    matters`` lanes already had this descent; this lane didn't). Scope
    "opponents".

    ADR-0038 W3 batch 6: two fallbacks for the tail no typed trigger def
    reaches at all — a bare quoted grant (Sokrates's activated-ability-
    granted replacement, Predators' Hour's AddKeyword-modification quote,
    Steel Hellkite's passive "was dealt combat damage by ~" activated-
    ability filter, the Unfinity Sticker Sheet TK-templates whose {TK} mana
    cost defeats phase's cost parser entirely, leaving the WHOLE triggered
    line as one opaque Unimplemented residue): :func:`combat_damage_
    recipients_from_text` over the FACE's own oracle (never the bulk
    top-level field — a DFC's real per-face text, recovering Optimus
    Prime's "Autobot Leader" face). And a LOW-confidence double-strike-
    grant heuristic (:data:`COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX` — Raphael,
    Blade Historian, Berserkers' Onslaught grant attacking creatures double
    strike, connecting with a player TWICE; a disjoint, corpus-bounded
    3-card class whose oracle never says "combat damage" at all). Both
    fallback-only — never override a structural miss into a wrong key.
    """
    for unit in tree.units:
        if unit.origin == "trigger" and _combat_damage_to_opp_fires(unit.node):
            return [
                Signal("combat_damage_to_opp", "opponents", "", "", tree.name, "high")
            ]
        for trig in iter_nested_trigger_defs(unit.node):
            if _combat_damage_to_opp_fires(trig):
                return [
                    Signal(
                        "combat_damage_to_opp", "opponents", "", "", tree.name, "high"
                    )
                ]
        for trig in iter_delayed_trigger_condition_defs(unit.node):
            if _combat_damage_to_opp_fires(trig):
                return [
                    Signal(
                        "combat_damage_to_opp", "opponents", "", "", tree.name, "high"
                    )
                ]
    if "player" in combat_damage_recipients_from_text(tree.oracle):
        return [Signal("combat_damage_to_opp", "opponents", "", "", tree.name, "high")]
    if re.search(COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX, _kept(tree), re.IGNORECASE):
        return [Signal("combat_damage_to_opp", "opponents", "", "", tree.name, "low")]
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


LANES = (
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
)
